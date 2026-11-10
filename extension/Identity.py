import os
import sys
import logging
from pathlib import Path
sys.path.insert(0,os.path.dirname(__file__))
import uno
import unohelper
from com.sun.star.task import XJob, XJobExecutor
from com.sun.star.document import XDocumentEventListener
from docidentity.core import Registry, data_home
from docidentity.office import Controller, metadata, kind

IMPL='org.aridlin.docidentity.Job'
CONTROLLERS=[]
LISTENER=None

def controller(doc,ctx,auto_new=False):
    for c in CONTROLLERS:
        if c.doc==doc:
            if auto_new and not doc.URL and not c.session.current: c.register()
            return c
    c=Controller(doc,ctx).attach(); CONTROLLERS.append(c)
    if auto_new and not doc.URL and not c.session.current: c.register()
    if c.session.committed and doc.URL:
        warnings=c.opened()
        if warnings:
            logging.warning('\n'.join(warnings))
            if doc.CurrentController.Frame.ContainerWindow.isVisible():
                message(doc,'\n'.join(warnings)+'\nUse Document Identity > Reconcile Document Identity to choose whether to keep this identity.')
    return c

class GlobalListener(unohelper.Base,XDocumentEventListener):
    def __init__(self,ctx): self.ctx=ctx
    def documentEventOccured(self,event):
        try:
            if event.EventName in ('OnLoadFinished','OnNew'):
                controller(event.Source,self.ctx,auto_new=event.EventName=='OnNew')
            elif event.EventName=='OnUnload':
                for c in list(CONTROLLERS):
                    if c.doc==event.Source:
                        c.session.discard(); c.registry.close(); CONTROLLERS.remove(c)
        except ValueError: pass # unsupported document
        except Exception: logging.exception('Document attach failed')
    def disposing(self,event): pass

def start(ctx):
    global LISTENER
    if LISTENER is None:
        logging.basicConfig(filename=str(data_home()/'extension.log'),level=logging.WARNING)
        LISTENER=GlobalListener(ctx)
        ctx.ServiceManager.createInstanceWithContext('com.sun.star.frame.GlobalEventBroadcaster',ctx).addDocumentEventListener(LISTENER)

def message(doc,text,title='Document Identity',question=False):
    window=doc.CurrentController.Frame.ContainerWindow
    box=window.Toolkit.createMessageBox(window,uno.Enum('com.sun.star.awt.MessageBoxType','QUERYBOX' if question else 'INFOBOX'),3 if question else 1,title,text)
    return box.execute()

class Job(unohelper.Base,XJob,XJobExecutor):
    def __init__(self,ctx): self.ctx=ctx
    def execute(self,args):
        start(self.ctx)
        desktop=self.ctx.ServiceManager.createInstanceWithContext('com.sun.star.frame.Desktop',self.ctx)
        enum=desktop.Components.createEnumeration()
        while enum.hasMoreElements():
            doc=enum.nextElement()
            try: controller(doc,self.ctx,auto_new=not doc.URL)
            except ValueError: pass
            except Exception: logging.exception('Startup attach failed')
        return None
    def trigger(self,command):
        start(self.ctx)
        desktop=self.ctx.ServiceManager.createInstanceWithContext('com.sun.star.frame.Desktop',self.ctx)
        doc=desktop.CurrentComponent
        if doc is None: return
        try:
            c=controller(doc,self.ctx)
            if command=='register':
                c.register()
                if not doc.URL:
                    message(doc,'Identity and barcode prepared. Save as ODT, ODS or ODP to commit registration.')
                else:
                    c.before_save(); doc.store(); c.after_save()
                    if c.error: raise RuntimeError(c.error)
                    message(doc,'Registered: '+c.session.current)
            elif command=='info':
                if not c.session.current: raise ValueError('Register the document first')
                if c.session.provisional:
                    message(doc,'Unsaved document identity: '+c.session.current+
                        '\n\nSave this document as ODT, ODS or ODP to record its location and enable document lookup.')
                else:
                    from docidentity.desktop import launch_lookup
                    launch_lookup(c.session.current,c.registry.path)
            elif command=='restore': c.repair(True)
            elif command=='repair': c.repair()
            elif command=='reposition':
                c.repair()
                # Accessible UNO dialog with millimetre coordinates; controlled edits.
                sm=self.ctx.ServiceManager
                model=sm.createInstanceWithContext('com.sun.star.awt.UnoControlDialogModel',self.ctx)
                model.Width=180; model.Height=100
                model.Title='Barcode position (mm inside print header)' if kind(doc)=='calc' else 'Barcode position (mm from page origin)'
                for name,y,label in [('x',12,'Horizontal (mm)'),('y',40,'Vertical (mm)')]:
                    t=model.createInstance('com.sun.star.awt.UnoControlFixedTextModel'); t.PositionX=6;t.PositionY=y;t.Width=90;t.Height=14;t.Label=label;model.insertByName(name+'label',t)
                    field=model.createInstance('com.sun.star.awt.UnoControlNumericFieldModel');field.PositionX=105;field.PositionY=y;field.Width=65;field.Height=15;field.Value=10;field.ValueMin=0;field.ValueMax=1000;field.DecimalAccuracy=1;model.insertByName(name,field)
                for name,x,typ in [('OK',30,1),('Cancel',100,2)]:
                    b=model.createInstance('com.sun.star.awt.UnoControlButtonModel');b.PositionX=x;b.PositionY=75;b.Width=50;b.Height=16;b.Label=name;b.PushButtonType=typ;model.insertByName(name,b)
                dialog=sm.createInstanceWithContext('com.sun.star.awt.UnoControlDialog',self.ctx);dialog.setModel(model);dialog.createPeer(doc.CurrentController.Frame.ContainerWindow.Toolkit,doc.CurrentController.Frame.ContainerWindow)
                try:
                    if dialog.execute()==1: c.reposition(model.getByName('x').Value*100,model.getByName('y').Value*100)
                finally: dialog.dispose()
            elif command=='reconcile':
                if not c.session.current: raise ValueError('Register the document first')
                answer=message(doc,'Keep the embedded identity?\nYes: retain identity and record reconciliation.\nNo: create a new child identity on next save.\nCancel: leave unchanged.',question=True)
                if answer in (2,3): message(doc,'\n'.join(c.reconcile_choice(answer==3)) or 'Identity retained.')
        except Exception as exc:
            logging.exception('Command failed')
            message(doc,str(exc),'Document Identity - action failed')

helper=unohelper.ImplementationHelper()
helper.addImplementation(Job,IMPL,(IMPL,'com.sun.star.task.Job','com.sun.star.task.JobExecutor'))
g_ImplementationHelper=helper
