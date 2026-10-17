from pathlib import Path
import subprocess
import tempfile
import unittest
from docidentity.cli import main, make_pdf,register_generated_pdf
from docidentity.core import Registry

class CLITests(unittest.TestCase):
    def test_pdf_generation_registration_render_decode(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);r=Registry(root/'registry.db');output=root/'generated.pdf'
            try:
                identity=make_pdf(output,'Local PDF with registered barcode',r)
                self.assertEqual(str(output),r.info(identity)['locations'][0]['path'])
                subprocess.run(['pdftoppm','-f','1','-singlefile','-scale-to','2500','-png',str(output),str(root/'render')],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
                result=subprocess.check_output(['zbarimg','--quiet','--raw',str(root/'render.png')],stderr=subprocess.DEVNULL).decode().strip()
                self.assertEqual(identity,result)
                recovery=Registry(root/'recovery.db')
                try:
                    self.assertEqual(identity,register_generated_pdf(output,recovery))
                    self.assertEqual(str(output),recovery.info(identity)['locations'][0]['path'])
                finally: recovery.close()
                with self.assertRaises(FileExistsError): make_pdf(output,'Do not overwrite',r)
            finally: r.close()
    def test_scanner_cli_rejects_command_protocol(self):
        with tempfile.TemporaryDirectory() as temp:
            self.assertEqual(1,main(['--database',str(Path(temp)/'db'),'lookup','@#COMMAND']))
    def test_backup(self):
        with tempfile.TemporaryDirectory() as temp:
            db=Path(temp)/'db';backup=Path(temp)/'backup'
            self.assertEqual(0,main(['--database',str(db),'backup',str(backup)]))
            self.assertEqual(0,main(['--database',str(backup),'check']))

if __name__=='__main__': unittest.main()
