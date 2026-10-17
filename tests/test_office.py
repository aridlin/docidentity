"""Real UNO integration. Run under an isolated headless profile using scripts/test.py."""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile
import unittest
import uno
from docidentity.core import Registry,PREFIX,embedded,hashes
from docidentity.office import Office,Controller,kind,prop,metadata,shapes,graphic

@unittest.skipUnless(os.environ.get('DOCIDENTITY_TEST_PIPE'),'Run scripts/test.py for real LibreOffice integration')
class OfficeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.office=Office(os.environ['DOCIDENTITY_TEST_PIPE'])
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name)
        self.registry=Registry(self.root/'registry.db'); self.docs=[]
    def tearDown(self):
        for d in self.docs:
            try: d.close(True)
            except Exception: pass
        self.registry.close(); self.tmp.cleanup()
    def create(self,k):
        url={'writer':'swriter','calc':'scalc','impress':'simpress'}[k]
        doc=self.office.desktop.loadComponentFromURL('private:factory/'+url,'_blank',0,(prop('Hidden',True),))
        self.docs.append(doc)
        if k=='writer': doc.Text.String='Original content'
        elif k=='calc': doc.Sheets.getByIndex(0).getCellByPosition(0,0).String='Original content'
        # Impress default placeholders occupy corners; clear only in our test fixture.
        else:
            page=doc.DrawPages.getByIndex(0)
            for i in range(page.Count-1,-1,-1): page.remove(page.getByIndex(i))
        path=self.root/('sample.'+{'writer':'odt','calc':'ods','impress':'odp'}[k])
        doc.storeAsURL(uno.systemPathToFileUrl(str(path)),(prop('FilterName',{'writer':'writer8','calc':'calc8','impress':'impress8'}[k]),))
        return doc,path
    def edit(self,doc):
        k=kind(doc)
        if k=='writer': doc.Text.insertString(doc.Text.End,' changed',False)
        elif k=='calc': doc.Sheets.getByIndex(0).getCellByPosition(0,0).String='Changed content'
        else:
            s=doc.createInstance('com.sun.star.drawing.RectangleShape'); doc.DrawPages.getByIndex(0).add(s)
    def test_all_formats_registration_barcode_edit_save_reopen_export(self):
        for k in ('writer','calc','impress'):
            with self.subTest(format=k):
                doc,path=self.create(k)
                c=Controller(doc,self.office.ctx,self.registry).attach()
                a=c.register(); c.before_save(); doc.store(); c.after_save()
                self.assertIsNone(c.error)
                self.assertEqual(a,embedded(path)[PREFIX+'ID']); self.assertEqual(1,len(shapes(doc)))
                before_hash=hashes(path)[0]
                before_bytes=path.read_bytes()
                default=shapes(doc)[0]
                default_xy=(default.HoriOrientPosition,default.VertOrientPosition) if k=='writer' else (default.getPosition().X,default.getPosition().Y)
                c.repair(); c.repair(); c.reposition(1000,500); c.repair(True)
                restored=shapes(doc)[0]
                restored_xy=(restored.HoriOrientPosition,restored.VertOrientPosition) if k=='writer' else (restored.getPosition().X,restored.getPosition().Y)
                self.assertEqual(default_xy,restored_xy,'Restore did not return to default coordinates')
                self.assertEqual(a,c.session.current); self.assertEqual(1,len(shapes(doc)))
                doc.store(); c.after_save()
                if before_hash!=hashes(path)[0]:
                    qa=Path('dist/qa');qa.mkdir(exist_ok=True)
                    (qa/('before.'+path.suffix[1:])).write_bytes(before_bytes)
                    shutil.copy(path,qa/('after.'+path.suffix[1:]))
                self.assertEqual(before_hash,hashes(path)[0], 'Barcode repair/reposition changed normalized hash')
                self.assertEqual([],c.opened())
                self.edit(doc); b=c.session.current
                self.assertNotEqual(a,b); self.assertIsNotNone(c.session.provisional)
                self.edit(doc); self.assertEqual(b,c.session.current)
                doc.store()  # real OnSave/OnSaveDone listener, no manual save hooks
                self.assertIsNone(c.error); self.assertIsNone(c.session.provisional)
                self.assertEqual(b,embedded(path)[PREFIX+'ID'])
                self.assertEqual([{'id':a}],self.registry.info(b)['parents'])
                copy=self.root/('copy'+path.suffix); shutil.copy(path,copy)
                self.assertEqual(b,self.office.register(copy,self.registry))
                self.assertGreaterEqual(len(self.registry.info(b)['locations']),2)
                pdf=self.root/(k+'.pdf'); self.office.export(path,pdf,self.registry)
                self.assertTrue(pdf.stat().st_size>1000)
                out=self.root/(k+'render')
                subprocess.run(['pdftoppm','-f','1','-singlefile','-scale-to','2500','-png',str(pdf),str(out)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
                decoded=subprocess.check_output(['zbarimg','--quiet','--raw',str(out)+'.png'],stderr=subprocess.DEVNULL).decode().strip()
                self.assertIn(b,decoded)
                # Retain one rendered sample per format for visual QA.
                qa=Path('dist/qa'); qa.mkdir(exist_ok=True)
                shutil.copy(str(out)+'.png',qa/(k+'.png'))
    def test_discard_unsaved_edit(self):
        doc,path=self.create('writer'); c=Controller(doc,self.office.ctx,self.registry).attach()
        a=c.register(); c.before_save();doc.store();c.after_save(); self.edit(doc); b=c.session.current
        doc.setModified(False);doc.close(True);self.docs.remove(doc)
        self.assertEqual(a,embedded(path)[PREFIX+'ID'])
        with self.assertRaises(KeyError): self.registry.info(b)
    def test_readonly(self):
        doc,path=self.create('writer');doc.close(True);self.docs.remove(doc)
        other=self.office.desktop.loadComponentFromURL(uno.systemPathToFileUrl(str(path)),'_blank',0,(prop('Hidden',True),prop('ReadOnly',True)))
        self.docs.append(other)
        with self.assertRaises(PermissionError): Controller(other,self.office.ctx,self.registry).register()
    def test_save_as_unchanged(self):
        doc,path=self.create('writer'); c=Controller(doc,self.office.ctx,self.registry).attach()
        a=c.register();c.before_save();doc.store();c.after_save()
        out=self.root/'saveas.odt';doc.storeAsURL(uno.systemPathToFileUrl(str(out)),())
        self.assertEqual(a,c.session.current); self.assertEqual(a,embedded(out)[PREFIX+'ID'])
        self.assertEqual('SAVE_AS',self.registry.info(a)['events'][0]['type'])

    def test_formatting_cursor_undo_and_next_session(self):
        doc,path=self.create('writer');c=Controller(doc,self.office.ctx,self.registry).attach()
        a=c.register();c.before_save();doc.store();c.after_save()
        cursor=doc.CurrentController.ViewCursor
        cursor.gotoEnd(False);cursor.gotoStart(False)
        self.assertEqual(a,c.session.current)
        cursor.gotoEnd(True);cursor.CharWeight=150.0
        b=c.session.current;self.assertNotEqual(a,b)
        doc.UndoManager.undo()
        self.assertEqual(b,c.session.current)
        doc.store();self.assertEqual(b,c.session.current)
        self.edit(doc);self.assertNotEqual(b,c.session.current)

    def test_barcode_duplicates_removed(self):
        doc,path=self.create('calc');c=Controller(doc,self.office.ctx,self.registry).attach()
        a=c.register();c.before_save();doc.store();c.after_save()
        with c.controlled():
            obj=doc.createInstance('com.sun.star.drawing.GraphicObjectShape')
            obj.Name='DocIdentity.ManagedBarcode1';obj.Graphic=graphic(self.office.ctx,a)
            doc.DrawPages.getByIndex(0).add(obj)
        self.assertEqual(2,len(shapes(doc)))
        c.repair();self.assertEqual(1,len(shapes(doc)));self.assertEqual(a,c.session.current)

    def test_database_failure_reopen_recovery(self):
        doc,path=self.create('writer');c=Controller(doc,self.office.ctx,self.registry).attach()
        a=c.register();c.before_save();doc.store();c.after_save();self.edit(doc);b=c.session.current
        # A real SQLite connection closed before the save callback fails.
        c.registry.close();doc.store()
        self.assertIsNotNone(c.error)
        self.assertEqual(b,embedded(path)[PREFIX+'ID'])
        self.assertEqual(b,c.session.committed)
        self.edit(doc);d=c.session.current
        self.assertNotEqual(b,d)
        doc.store()
        self.assertEqual(d,embedded(path)[PREFIX+'ID'])
        self.registry=Registry(self.root/'registry.db')
        self.registry.reconcile(d,path,parent=b)
        import json
        self.registry.recover_edges(json.loads(embedded(path)[PREFIX+'RecoveryEdges']))
        self.registry.reconcile(b,path,parent=a)
        self.assertEqual([{'id':a}],self.registry.info(b)['parents'])
        self.assertEqual([{'id':b}],self.registry.info(d)['parents'])
        c.registry=self.registry


    def test_failed_save_as_allows_edit_retry(self):
        doc,path=self.create('writer');c=Controller(doc,self.office.ctx,self.registry).attach()
        a=c.register();c.before_save();doc.store();c.after_save()
        failed=False
        try: doc.storeAsURL('file:///proc/docidentity-no-write.odt',())
        except Exception: failed=True
        self.assertTrue(failed)
        self.assertFalse(c.saving,'Failed save left modification detection suppressed')
        self.edit(doc)
        self.assertNotEqual(a,c.session.current)
        doc.store()
        self.assertEqual(c.session.current,embedded(path)[PREFIX+'ID'])

    def test_calc_print_range_exclusion_refuses_pdf_registration(self):
        doc,path=self.create('calc');c=Controller(doc,self.office.ctx,self.registry).attach()
        c.register();c.before_save();doc.store();c.after_save()
        area=uno.createUnoStruct('com.sun.star.table.CellRangeAddress')
        doc.Sheets.getByIndex(0).setPrintAreas((area,))
        doc.store();identity=c.session.current
        output=self.root/'excluded.pdf'
        with self.assertRaises(ValueError): self.office.export(path,output,self.registry)
        self.assertEqual([],self.registry.info(identity)['derivatives'])

if __name__=='__main__': unittest.main()
