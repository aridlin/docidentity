"""Verify real OXT Python loader, startup jobs and automatic document lifecycle."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
import uno
from docidentity.office import Office,prop,shapes,metadata
from docidentity.core import PREFIX,Registry,embedded
root=Path(__file__).resolve().parent.parent
subprocess.run([sys.executable,str(root/'scripts/build.py')],check=True)
with tempfile.TemporaryDirectory(prefix='docidentity-oxt-') as temp:
    t=Path(temp); profile=(t/'profile').as_uri(); pipe='identity_extension_'+str(os.getpid())
    os.environ['DOCIDENTITY_DATA_HOME']=str(t/'data')
    env=dict(os.environ,DOCIDENTITY_DATA_HOME=str(t/'data'),SAL_USE_VCLPLUGIN='svp',QT_QPA_PLATFORM='xcb')
    subprocess.run(['/usr/bin/unopkg','-env:UserInstallation='+profile,'add','--force',str(root/'dist/docidentity-0.3.0.oxt')],env=env,check=True)
    proc=subprocess.Popen(['/usr/bin/soffice','-env:UserInstallation='+profile,'--headless','--norestore','--nodefault','--nofirststartwizard','--accept=pipe,name='+pipe+';urp;StarOffice.ServiceManager'],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
    try:
        for _ in range(100):
            try: office=Office(pipe); break
            except Exception: time.sleep(.1)
        else: raise RuntimeError('Office startup failed: '+proc.stderr.read().decode())
        # Disable the welcome wizard through the live configuration provider;
        # a fresh profile may reset preseeded settings during its initial setup.
        provider=office.ctx.ServiceManager.createInstanceWithContext('com.sun.star.configuration.ConfigurationProvider',office.ctx)
        settings=provider.createInstanceWithArguments('com.sun.star.configuration.ConfigurationUpdateAccess',(prop('nodepath','/org.openoffice.Office.Common/Misc'),))
        settings.setPropertyValue('FirstRun',False);settings.commitChanges()
        job=office.ctx.ServiceManager.createInstanceWithContext('org.aridlin.docidentity.Job',office.ctx)
        assert job is not None,'Python UNO component not registered'
        for k,factory,extension,filt in [('writer','swriter','odt','writer8'),('calc','scalc','ods','calc8'),('impress','simpress','odp','impress8')]:
            doc=office.desktop.loadComponentFromURL('private:factory/'+factory,'_blank',0,(prop('Hidden',False),))
            time.sleep(.3)
            a=metadata(doc).get(PREFIX+'ID')
            assert a and len(shapes(doc))==1,'New '+k+' document did not auto-register'
            path=t/('extension-test.'+extension)
            if k=='writer':doc.Text.String='Extension lifecycle test'
            elif k=='calc':doc.Sheets.getByIndex(0).getCellByPosition(0,0).String='Extension lifecycle test'
            doc.storeAsURL(path.as_uri(),(prop('FilterName',filt),))
            assert a==embedded(path)[PREFIX+'ID']
            registry=Registry(t/'data/registry.sqlite3')
            assert registry.info(a)['parents']==[]
            if k=='writer':
                # Exercise the actual OXT menu action: no JSON/modal message box.
                doc.CurrentController.Frame.activate()
                job.trigger('info')
                lookup=None
                try:
                    for attempt in range(50):
                        for cmdline in Path('/proc').glob('[0-9]*/cmdline'):
                            try: argv=cmdline.read_bytes().split(b'\0')
                            except (OSError,ProcessLookupError):continue
                            if b'docidentity.cli' in argv and str(registry.path).encode() in argv and a.encode() in argv:
                                lookup=int(cmdline.parent.name);break
                        if lookup:
                            time.sleep(.4)
                            os.kill(lookup,0);break
                        time.sleep(.1)
                    assert lookup,'Document Information did not launch the native lookup'
                    print('PASS: saved-document information launches native lookup from bundled OXT',flush=True)
                finally:
                    if lookup:
                        import signal
                        try:os.kill(lookup,signal.SIGTERM)
                        except ProcessLookupError:pass
            # The same dispatch used by Ctrl+N must auto-register another new document.
            dispatch=office.ctx.ServiceManager.createInstanceWithContext('com.sun.star.frame.DispatchHelper',office.ctx)
            def components():
                enum=office.desktop.Components.createEnumeration();result=[]
                while enum.hasMoreElements():result.append(enum.nextElement())
                return result
            before=components()
            doc.CurrentController.Frame.activate()
            dispatch.executeDispatch(doc.CurrentController.Frame,'.uno:AddDirect','',0,())
            second=None
            for attempt in range(50):
                fresh=[item for item in components() if all(item!=old for old in before)]
                if fresh:
                    second=fresh[0]
                    if metadata(second).get(PREFIX+'ID'):break
                time.sleep(.1)
            assert second is not None,'Ctrl+N did not create a second '+k+' document'
            second_id=metadata(second).get(PREFIX+'ID')
            assert second_id and second_id!=a and len(shapes(second))==1,'Ctrl+N did not auto-register '+k
            try:registry.info(second_id);raise AssertionError('Unsaved registration committed prematurely')
            except KeyError:pass
            second.dispose()
            if k=='writer':doc.Text.insertString(doc.Text.End,' user edit',False)
            elif k=='calc':doc.Sheets.getByIndex(0).getCellByPosition(0,0).String='user edit'
            else:
                shape=doc.createInstance('com.sun.star.drawing.RectangleShape');doc.DrawPages.getByIndex(0).add(shape)
            b=metadata(doc)[PREFIX+'ID'];assert a!=b,'First saved-state edit not detected in '+k
            doc.store();assert registry.info(b)['parents']==[{'id':a}]
            assert len(shapes(doc))==1
            doc.dispose();registry.close()
            print('PASS: '+k+' automatic new document + Ctrl+N, provisional registration, saved lineage',flush=True)
    finally:
        proc.terminate()
        try: proc.wait(10)
        except subprocess.TimeoutExpired: proc.kill();proc.wait()
        log=t/'data/extension.log'
        if log.exists() and log.stat().st_size: print(log.read_text())
