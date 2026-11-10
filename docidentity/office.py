"""UNO adapters. Import only inside a LibreOffice-enabled Python runtime."""
from __future__ import annotations
import contextlib
import logging
import json
from pathlib import Path
import tempfile
import time
import uno
import unohelper
from com.sun.star.util import XModifyListener
from com.sun.star.document import XDocumentEventListener
from .core import MANAGED, PREFIX, Registry, Session, embedded, new_id, now, path_of, validate
from .barcode import png

LOG=logging.getLogger('docidentity')

def prop(name,value):
    p=uno.createUnoStruct('com.sun.star.beans.PropertyValue'); p.Name=name; p.Value=value
    return p

def point(x,y):
    p=uno.createUnoStruct('com.sun.star.awt.Point'); p.X=int(x); p.Y=int(y); return p

def size(w,h):
    p=uno.createUnoStruct('com.sun.star.awt.Size'); p.Width=int(w); p.Height=int(h); return p

def properties(doc): return doc.DocumentProperties.UserDefinedProperties

def metadata(doc):
    p=properties(doc)
    return {x.Name:p.getPropertyValue(x.Name) for x in p.PropertySetInfo.Properties if x.Name.startswith(PREFIX)}

def set_meta(doc, values):
    p=properties(doc)
    for name,value in values.items():
        name=PREFIX+name
        if p.PropertySetInfo.hasPropertyByName(name): p.setPropertyValue(name,str(value))
        else: p.addProperty(name,128,str(value))  # REMOVABLE

def kind(doc):
    for service,k in [('com.sun.star.text.TextDocument','writer'),('com.sun.star.sheet.SpreadsheetDocument','calc'),('com.sun.star.presentation.PresentationDocument','impress')]:
        if doc.supportsService(service): return k
    raise ValueError('Only Writer ODT, Calc ODS and Impress ODP are supported')

def shapes(doc):
    from .repeated import managed_objects
    return managed_objects(doc)

def graphic(ctx, identity):
    # Pass owned bytes, not a short-lived URL: GraphicProvider may defer decoding.
    stream=ctx.ServiceManager.createInstanceWithContext('com.sun.star.io.SequenceInputStream',ctx)
    stream.initialize((uno.ByteSequence(png(identity)),))
    provider=ctx.ServiceManager.createInstanceWithContext('com.sun.star.graphic.GraphicProvider',ctx)
    return provider.queryGraphic((prop('InputStream',stream),prop('MimeType','image/png'),prop('LazyRead',False)))

def barcode(doc,ctx,identity,restore=False,update=True):
    from .repeated import ensure
    return ensure(doc,ctx,identity,restore,update)

class Controller(unohelper.Base,XModifyListener,XDocumentEventListener):
    def __init__(self,doc,ctx,registry=None):
        self.doc=doc; self.ctx=ctx; self.registry=registry or Registry()
        m=metadata(doc)
        if m.get(PREFIX+'Schema') not in (None,'','1'):
            raise ValueError('Unsupported embedded metadata schema; upgrade before editing tracking')
        self.session=Session(m.get(PREFIX+'ID'))
        self.previous=doc.URL
        self.pending_edges=json.loads(m.get(PREFIX+'RecoveryEdges') or '[]')
        if not isinstance(self.pending_edges,list) or len(self.pending_edges)>4096:
            raise ValueError('Invalid or excessive embedded recovery lineage')
        self.error=None
        self.attached=False
        self.saving=False
        from .repeated import coverage_complete
        self.rendered_id=m.get(PREFIX+'BarcodeID',self.session.current) if coverage_complete(doc) else None

    def attach(self):
        if not self.attached:
            self.doc.addModifyListener(self); self.doc.addDocumentEventListener(self); self.attached=True
        return self

    @contextlib.contextmanager
    def controlled(self):
        # Listener suppression is sufficient. Drawing controller locks can defer
        # layout across Graphic imports and are unsafe in headless Impress.
        with self.session.controlled():
            try: yield
            except Exception as exc: raise RuntimeError(str(exc)) from None

    def writable(self):
        if self.doc.isReadonly(): raise PermissionError('Read-only document: save an editable ODF copy first')
        if self.doc.URL and path_of(self.doc.URL).suffix.lower() not in ('.odt','.ods','.odp'):
            raise ValueError('Save an ODT, ODS or ODP copy before registration; other formats cannot retain tracking reliably')

    def sync(self):
        if self.session.provisional and self.session.committed:
            edge=[self.session.committed,self.session.provisional]
            if edge not in self.pending_edges: self.pending_edges.append(edge)
        values={'RecoveryEdges':json.dumps(self.pending_edges,separators=(',',':')),'ID':self.session.current,'Schema':'1','RegisteredURI':self.doc.URL,'Parent':(self.session.committed or '') if self.session.provisional else metadata(self.doc).get(PREFIX+'Parent',''),'Created':metadata(self.doc).get(PREFIX+'Created') or now()}
        set_meta(self.doc,values)
        barcode(self.doc,self.ctx,self.session.current,update=self.rendered_id!=self.session.current)
        self.rendered_id=self.session.current

    def register(self):
        self.writable()
        if self.session.current: return self.session.current
        # Registration refuses an already dirty tracked session only via caller;
        # untracked document content is preserved in its existing model.
        with self.controlled():
            identity=new_id()
            barcode(self.doc,self.ctx,identity)
            self.rendered_id=identity
            self.session.provisional=identity
            self.sync()
        return identity

    def opened(self):
        if self.session.provisional: return ['Save or discard pending edits before reconciliation.']
        if self.session.current and self.doc.URL:
            m=metadata(self.doc)
            warnings=self.registry.reconcile(self.session.current,self.doc.URL,m.get(PREFIX+'RegisteredURI',''),m.get(PREFIX+'Parent') or None)
            self.registry.recover_edges(self.pending_edges)
            self.pending_edges=[]
            from .repeated import coverage_complete
            if metadata(self.doc).get(PREFIX+'PageCoverage')!='all-pages-v1' or self.rendered_id!=self.session.current or not coverage_complete(self.doc):
                if self.doc.isReadonly():
                    return warnings+['Read-only document: save an editable copy to upgrade barcodes to every page.']
                with self.controlled():
                    barcode(self.doc,self.ctx,self.session.current)
                    self.rendered_id=self.session.current
            return warnings
        return []

    def modified(self,event):
        if self.session.suppression or self.saving or not self.session.committed: return
        if not self.doc.isModified(): return
        # UNO emits modification events for model edits, not cursor navigation.
        changed=self.session.modified()
        from .repeated import coverage_complete
        if changed or not coverage_complete(self.doc):
            try:
                with self.controlled(): self.sync()
            except Exception as exc:
                self.error=str(exc); LOG.exception('Identity update failed; save must be repaired')

    def before_save(self):
        if self.session.current:
            self.writable()
            with self.controlled(): self.sync()

    def after_save(self):
        if not self.session.current or not self.doc.URL: return
        # A valid embedded ID and Parent permit recovery if SQLite is unavailable.
        stored={}
        try:
            stored=embedded(path_of(self.doc.URL))
            if stored.get(PREFIX+'ID') != self.session.current:
                raise RuntimeError('Saved embedded identity does not match in-memory identity; repair and save again')
            from .repeated import coverage_complete
            if self.rendered_id!=self.session.current or not coverage_complete(self.doc):
                raise RuntimeError('Barcode coverage/update did not complete; repair and save again')
            self.registry.recover_edges(self.pending_edges)
            self.session.saved(self.registry,self.doc.URL,self.previous)
            self.pending_edges=[]
            self.previous=self.doc.URL
            self.error=None
        except Exception as exc:
            # The file is clean even if SQLite is unavailable. A subsequent edit
            # starts a new child; persisted RecoveryEdges retain unsynced ancestry.
            if stored.get(PREFIX+'ID')==self.session.current:
                self.session.committed=self.session.current
                self.session.provisional=None
            self.error='File saved, registry update failed; reopen to recover: '+str(exc)
            LOG.exception(self.error)

    def documentEventOccured(self,event):
        try:
            if event.EventName in ('OnSave','OnSaveAs'):
                self.saving=True
                self.before_save()
            elif event.EventName in ('OnSaveDone','OnSaveAsDone'):
                self.after_save()
                self.saving=False
            elif event.EventName in ('OnSaveFailed','OnSaveAsFailed'): self.saving=False
            elif event.EventName=='OnPrint' and self.session.current:
                with self.controlled(): self.sync()
            # Failed/cancelled saves keep the provisional ID for a retry.
        except Exception as exc:
            self.saving=False
            self.error=str(exc); LOG.exception('Document lifecycle error')

    def disposing(self,event):
        self.session.discard()  # no DB commit for discarded edits

    def repair(self,restore=False):
        self.writable()
        if not self.session.current: raise ValueError('Register the document first')
        with self.controlled():
            obj=barcode(self.doc,self.ctx,self.session.current,restore)
            self.rendered_id=self.session.current
            return obj

    def reposition(self,x,y):
        self.writable()
        with self.controlled():
            obj=self.repair()
            if kind(self.doc)=='writer':
                for item in shapes(self.doc):
                    item.HoriOrient=0; item.VertOrient=0
                    item.HoriOrientPosition=int(x); item.VertOrientPosition=int(y)
            elif kind(self.doc)=='calc':
                from .repeated import _calc_records,_calc_styles,_apply_calc
                records=_calc_records(self.doc)
                for name,style in _calc_styles(self.doc):
                    records[name]['position']=[int(x),int(y)]
                    _apply_calc(self.doc,name,style,records,self.session.current,self.ctx,True)
            else:
                for item in shapes(self.doc): item.setPosition(point(x,y))

    def reconcile_choice(self,fork=False):
        if fork:
            self.writable()
            if self.session.provisional: raise ValueError('Save or discard current edits before reconciliation')
            self.session.modified()
            with self.controlled(): self.sync()
            return ['New identity is provisional until you save.']
        warnings=self.opened()
        with self.registry.db:
            self.registry.event(self.session.current,'IDENTITY_RECONCILED',self.doc.URL,certainty='confirmed',detail='User explicitly retained embedded identity')
        return warnings

class Office:
    """Connect to an explicitly launched local pipe; never attach to a random profile."""
    def __init__(self,pipe='docidentity'):
        local=uno.getComponentContext()
        resolver=local.ServiceManager.createInstanceWithContext('com.sun.star.bridge.UnoUrlResolver',local)
        self.ctx=resolver.resolve('uno:pipe,name='+pipe+';urp;StarOffice.ComponentContext')
        self.desktop=self.ctx.ServiceManager.createInstanceWithContext('com.sun.star.frame.Desktop',self.ctx)

    def open(self,path):
        url=uno.systemPathToFileUrl(str(path_of(path)))
        doc=self.desktop.loadComponentFromURL(url,'_blank',0,(prop('Hidden',True),prop('UpdateDocMode',0),prop('MacroExecutionMode',uno.getConstantByName('com.sun.star.document.MacroExecMode.NEVER_EXECUTE'))))
        if doc is None: raise ValueError('LibreOffice could not open file')
        kind(doc)
        return doc

    def register(self,path,registry=None):
        doc=self.open(path)
        try:
            c=Controller(doc,self.ctx,registry)
            if c.session.current:
                c.opened()
                if doc.isModified():
                    c.before_save();doc.store();c.after_save()
                    if c.error:raise RuntimeError(c.error)
                return c.session.current
            c.register(); c.before_save(); doc.store(); c.after_save()
            if c.error: raise RuntimeError(c.error)
            return c.session.current
        finally: doc.close(True)

    def export(self,path,output,registry=None):
        doc=self.open(path)
        try:
            c=Controller(doc,self.ctx,registry)
            if not c.session.current: raise ValueError('Register source before exporting')
            c.opened()
            managed=shapes(doc)
            if not managed:
                raise ValueError('Managed barcode is missing. Repair and save the source before export.')
            # Regenerate from the validated embedded ID for this export. Some
            # UNO adapters do not persist Description reliably. Source bytes stay intact.
            c.repair()
            dest=path_of(output)
            if dest.exists(): raise FileExistsError(dest)
            filt={'writer':'writer_pdf_Export','calc':'calc_pdf_Export','impress':'impress_pdf_Export'}[kind(doc)]
            # PDF/A-1 flattens transparency; lossless, full-resolution RGB bars
            # avoid indexed palettes/soft masks that some print drivers turn black.
            # Use a typed sequence: an untyped Python tuple silently loses FilterData.
            options=uno.Any('[]com.sun.star.beans.PropertyValue',(
                prop('SelectPdfVersion',1),prop('UseLosslessCompression',True),
                prop('ReduceImageResolution',False)))
            doc.storeToURL(uno.systemPathToFileUrl(str(dest)),(
                prop('FilterName',filt),prop('Overwrite',False),prop('FilterData',options)))
            from .pdf_support import verify_barcode
            verify_barcode(dest,c.session.current)
            c.registry.commit(c.session.current,dest,event='PDF_EXPORTED',source=c.session.current)
            return c.session.current
        finally:
            doc.setModified(False)
            doc.close(True)

@contextlib.contextmanager
def isolated_office():
    """One-shot local LibreOffice process, with no network listener or daemon."""
    import os
    import secrets
    import subprocess
    with tempfile.TemporaryDirectory(prefix='docidentity-office-') as temp:
        root=Path(temp); pipe='docidentity_'+secrets.token_hex(8)
        env=dict(os.environ,SAL_USE_VCLPLUGIN='svp'); env.pop('DISPLAY',None)
        executable=os.environ.get('DOCIDENTITY_SOFFICE','/usr/bin/soffice')
        proc=subprocess.Popen([executable,'-env:UserInstallation='+(root/'profile').as_uri(),'--headless','--norestore','--nodefault','--nofirststartwizard','--accept=pipe,name='+pipe+';urp;StarOffice.ServiceManager'],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
        try:
            for _ in range(150):
                try: office=Office(pipe); break
                except Exception:
                    if proc.poll() is not None: raise RuntimeError('LibreOffice exited: '+proc.stderr.read().decode())
                    time.sleep(.1)
            else: raise RuntimeError('LibreOffice startup timed out')
            try: yield office
            except Exception as exc: raise RuntimeError(str(exc)) from None
        finally:
            proc.terminate()
            try: proc.wait(10)
            except subprocess.TimeoutExpired: proc.kill(); proc.wait()
