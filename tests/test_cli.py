from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from docidentity.cli import main, make_pdf,register_generated_pdf
from docidentity.core import Registry

class CLITests(unittest.TestCase):
    def test_lookup_can_start_without_an_identity(self):
        with tempfile.TemporaryDirectory() as temp:
            for args in ([],['lookup']):
                with self.subTest(args=args),patch('docidentity.gui.show') as show:
                    self.assertEqual(0,main(['--database',str(Path(temp)/'db')]+args))
                    self.assertEqual('',show.call_args.args[1])

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

    def test_pdf_with_unmarked_second_page_is_rejected(self):
        import cairo
        from docidentity.barcode import modules
        from docidentity.core import new_id
        from docidentity.pdf_support import verify_barcode
        with tempfile.TemporaryDirectory() as temp:
            identity=new_id();path=Path(temp)/'negative-test.pdf'
            surface=cairo.PDFSurface(str(path),595.28,841.89);ctx=cairo.Context(surface)
            ctx.set_source_rgb(0,0,0)
            for index,bit in enumerate(modules(identity)):
                if bit:ctx.rectangle(36+index*.76,30,.76,40)
            ctx.fill();ctx.show_page()
            ctx.move_to(36,100);ctx.show_text('This page intentionally has no barcode');ctx.show_page();surface.finish()
            with self.assertRaisesRegex(ValueError,'page 2'):verify_barcode(path,identity)


if __name__=='__main__': unittest.main()
