import os
from pathlib import Path
import shutil
import tempfile
import unittest
import zipfile
from docidentity.core import Registry, Session, new_id, validate, hashes
from docidentity.barcode import png,modules

class CoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name)
        self.registry=Registry(self.root/'registry.db')
        self.file=self.root/'a.odt'
        self.odf(self.file)
    def tearDown(self): self.registry.close(); self.tmp.cleanup()
    def odf(self,path,text='hello',meta='metadata'):
        with zipfile.ZipFile(path,'w') as z:
            z.writestr('content.xml','<root><text>'+text+'</text></root>')
            z.writestr('meta.xml','<meta>'+meta+'</meta>')
    def test_registration(self):
        identity=new_id(); validate(identity)
        self.registry.commit(identity,self.file)
        self.assertEqual(self.registry.info(identity)['locations'][0]['path'],str(self.file))
    def test_copy_multiple_paths(self):
        identity=new_id(); self.registry.commit(identity,self.file)
        other=self.root/'b.odt'; shutil.copy(self.file,other)
        self.assertEqual([],self.registry.reconcile(identity,other))
        self.assertEqual(2,len(self.registry.info(identity)['locations']))
        self.assertEqual('inferred',self.registry.info(identity)['events'][0]['certainty'])
    def test_first_edit_subsequent_undo_discard(self):
        identity=new_id(); s=Session(identity)
        self.assertTrue(s.modified()); provisional=s.current
        self.assertNotEqual(identity,provisional); self.assertFalse(s.modified()); self.assertEqual(s.current,provisional)
        s.discard(); self.assertEqual(s.current,identity)
        self.assertEqual(0,self.registry.db.execute('SELECT count(*) FROM identities').fetchone()[0])
    def test_controlled_changes(self):
        s=Session(new_id())
        with s.controlled(): self.assertFalse(s.modified())
        self.assertIsNone(s.provisional)
    def test_save_and_save_as(self):
        a=new_id(); self.registry.commit(a,self.file); s=Session(a)
        s.modified(); b=s.current; s.saved(self.registry,self.file)
        self.assertEqual([{'id':a}],self.registry.info(b)['parents'])
        other=self.root/'other.odt'; shutil.copy(self.file,other)
        s.saved(self.registry,other,self.file)
        self.assertEqual(s.current,b); self.assertEqual('SAVE_AS',self.registry.info(b)['events'][0]['type'])
    def test_failed_save_commit_keeps_provisional(self):
        s=Session(new_id()); s.modified(); identity=s.current
        with self.assertRaises(FileNotFoundError): s.saved(self.registry,self.root/'missing.odt')
        self.assertEqual(identity,s.provisional)
    def test_move_rename_inferred(self):
        identity=new_id(); self.registry.commit(identity,self.file)
        other=self.root/'renamed.odt'; self.file.rename(other)
        self.registry.reconcile(identity,other,str(self.file))
        events=self.registry.info(identity)['events']
        self.assertTrue(any(e['type']=='RENAMED' and e['certainty']=='inferred' for e in events))
        self.assertEqual(2,len(self.registry.info(identity)['locations']))
    def test_hash_mismatch(self):
        identity=new_id(); self.registry.commit(identity,self.file)
        self.odf(self.file,'changed')
        self.assertTrue(self.registry.reconcile(identity,self.file))
        self.assertEqual('HASH_MISMATCH',self.registry.info(identity)['warnings'][0]['code'])
    def test_metadata_hash_exclusion(self):
        h=hashes(self.file); self.odf(self.file,meta='changed')
        self.assertEqual(h[0],hashes(self.file)[0]); self.assertNotEqual(h[1],hashes(self.file)[1])
    def test_recovery(self):
        a,b=new_id(),new_id(); self.registry.reconcile(b,self.file,parent=a)
        self.assertEqual([{'id':a}],self.registry.info(b)['parents'])
    def test_missing_file_atomicity(self):
        identity=new_id()
        with self.assertRaises(FileNotFoundError): self.registry.commit(identity,self.root/'missing.odt')
        with self.assertRaises(KeyError): self.registry.info(identity)
    def test_validation_scanner_protocol(self):
        for invalid in ('@#COMMAND','@$', '@$'+'a'*32,'@ $'+'A'*32,'@$'+'A'*32+';xdg-open /'):
            with self.assertRaises(ValueError): validate(invalid)
    def test_barcode_decode(self):
        import subprocess
        identity=new_id(); f=self.root/'code.png'; f.write_bytes(png(identity))
        out=subprocess.check_output(['zbarimg','--quiet','--raw',str(f)],stderr=subprocess.DEVNULL).decode().strip()
        self.assertEqual(identity,out)
    def test_current_path_not_ancestor(self):
        a,b=new_id(),new_id(); self.registry.commit(a,self.file); self.registry.commit(b,self.file,parent=a,event='MODIFIED')
        self.assertFalse(self.registry.info(a)['locations'][0]['current_at_path'])

if __name__=='__main__': unittest.main()
