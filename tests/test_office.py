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
                a=c.register()
                if k=='impress':
                    initial=shapes(doc)[0].getPosition()
                    page=doc.DrawPages.getByIndex(0)
                    self.assertEqual((page.Width-11500,page.Height-1900),(initial.X,initial.Y))
                c.before_save(); doc.store(); c.after_save()
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

    def test_calc_print_range_keeps_repeating_header_barcode(self):
        doc,path=self.create('calc');c=Controller(doc,self.office.ctx,self.registry).attach()
        c.register();c.before_save();doc.store();c.after_save()
        area=uno.createUnoStruct('com.sun.star.table.CellRangeAddress')
        doc.Sheets.getByIndex(0).setPrintAreas((area,))
        doc.store();identity=c.session.current
        output=self.root/'excluded.pdf'
        self.office.export(path,output,self.registry)
        self.assertEqual(1,len(self.registry.info(identity)['derivatives']))

    def export_all_pages(self,doc,path,c,name):
        from docidentity.pdf_support import verify_barcode,pdf_info
        import re
        doc.store()
        output=self.root/(name+'.pdf')
        self.office.export(path,output,self.registry)
        pages=int(re.search(r'^Pages:\s+(\d+)',pdf_info(output),re.M).group(1))
        self.assertEqual(pages,verify_barcode(output,c.session.current))
        qa=Path('dist/qa/all-pages');qa.mkdir(parents=True,exist_ok=True)
        subprocess.run(['pdftoppm','-f',str(pages),'-l',str(pages),'-singlefile','-scale-to','1800','-png',str(output),str(qa/name)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
        return pages

    def test_writer_barcode_repeats_on_every_page_and_page_style(self):
        doc,path=self.create('writer')
        body='\n'.join('User paragraph '+str(n) for n in range(150))
        doc.Text.String=body
        family=doc.StyleFamilies.getByName('PageStyles')
        doc.Text.createTextCursor().PageDescName='First Page'
        standard=family.getByName('Standard');standard.HeaderIsOn=True
        standard.HeaderIsShared=False;standard.FirstIsShared=False
        standard.HeaderTextRight.String='Keep right header'
        standard.HeaderTextLeft.String='Keep left header'
        c=Controller(doc,self.office.ctx,self.registry).attach();identity=c.register();c.before_save();doc.store();c.after_save()
        self.assertEqual(body,doc.Text.String)
        self.assertEqual('Keep right header',standard.HeaderTextRight.String)
        self.assertEqual('Keep left header',standard.HeaderTextLeft.String)
        c.repair();c.repair();self.assertEqual(identity,c.session.current)
        pages=self.export_all_pages(doc,path,c,'writer-multiple-styles')
        self.assertGreaterEqual(pages,3)
        # Adding pages after the first dirty-session edit still repeats automatically.
        # Reopen to get a fresh independent model after the exporter closes its own.
        doc=self.office.open(path);self.docs.append(doc)
        c=Controller(doc,self.office.ctx,self.registry).attach();c.opened()
        doc.Text.insertString(doc.Text.End,'\n'+'\n'.join('More user content '+str(n) for n in range(140)),False)
        child=c.session.current;doc.Text.insertString(doc.Text.End,' final edit',False)
        self.assertEqual(child,c.session.current)
        self.assertGreater(self.export_all_pages(doc,path,c,'writer-added-pages'),pages)

    def test_calc_barcode_repeats_across_sheets_and_print_pages(self):
        doc,path=self.create('calc');doc.Sheets.insertNewByName('Second',1)
        for index,rows in ((0,145),(1,95)):
            sheet=doc.Sheets.getByIndex(index)
            for row in range(rows):sheet.getCellByPosition(0,row).String='Preserved row '+str(row)
            area=uno.createUnoStruct('com.sun.star.table.CellRangeAddress');area.Sheet=index;area.EndRow=rows-1
            sheet.setPrintAreas((area,))
        doc.Sheets.getByIndex(1).PageStyle='Report'
        styles=doc.StyleFamilies.getByName('PageStyles')
        for name in ('Default','Report'):
            style=styles.getByName(name)
            content=style.RightPageHeaderContent;content.CenterText.String='Preserved header '+name
            style.RightPageHeaderContent=content
        c=Controller(doc,self.office.ctx,self.registry).attach();identity=c.register();c.before_save();doc.store();c.after_save()
        self.assertEqual(2,len(shapes(doc)))
        self.assertEqual('Preserved row 100',doc.Sheets.getByIndex(0).getCellByPosition(0,100).String)
        for name in ('Default','Report'):
            style=styles.getByName(name);content=style.RightPageHeaderContent;text=content.CenterText
            self.assertEqual('Preserved header '+name,text.getString())
        before=hashes(path)[0];c.repair();c.repair();doc.store()
        self.assertEqual(identity,c.session.current);self.assertEqual(before,hashes(path)[0])
        self.assertGreaterEqual(self.export_all_pages(doc,path,c,'calc-multiple-sheets'),5)

    def test_impress_barcode_on_every_slide_and_new_slides(self):
        doc,path=self.create('impress')
        doc.DrawPages.insertNewByIndex(1);doc.DrawPages.insertNewByIndex(2)
        c=Controller(doc,self.office.ctx,self.registry).attach();identity=c.register();c.before_save();doc.store();c.after_save()
        self.assertEqual(3,len(shapes(doc)))
        c.repair();c.repair();self.assertEqual(3,len(shapes(doc)))
        self.assertEqual(identity,c.session.current)
        # Two new slides within one dirty session receive the same provisional ID.
        doc.DrawPages.insertNewByIndex(3);child=c.session.current
        doc.DrawPages.insertNewByIndex(4)
        self.assertNotEqual(identity,child);self.assertEqual(child,c.session.current)
        doc.store();self.assertEqual(5,len(shapes(doc)))
        self.assertEqual(5,self.export_all_pages(doc,path,c,'impress-five-slides'))

    def test_legacy_first_page_barcode_migrates_without_new_identity(self):
        from docidentity.office import set_meta
        from docidentity.core import new_id
        doc,path=self.create('writer');identity=new_id()
        obj=doc.createInstance('com.sun.star.text.TextGraphicObject');obj.Name='DocIdentity.ManagedBarcode'
        obj.Graphic=graphic(self.office.ctx,identity)
        obj.AnchorType=uno.Enum('com.sun.star.text.TextContentAnchorType','AT_PAGE');obj.AnchorPageNo=1
        doc.Text.insertTextContent(doc.Text.Start,obj,False)
        set_meta(doc,{'ID':identity,'Schema':'1'});doc.store();self.registry.commit(identity,path)
        c=Controller(doc,self.office.ctx,self.registry).attach();c.opened()
        self.assertEqual(identity,c.session.current);self.assertIsNone(c.session.provisional)
        self.assertTrue(all(item.Anchor.Text!=doc.Text for item in shapes(doc)))
        doc.store();self.assertEqual(identity,embedded(path)[PREFIX+'ID'])
        self.assertEqual([],self.registry.info(identity)['parents'])


if __name__=='__main__': unittest.main()
