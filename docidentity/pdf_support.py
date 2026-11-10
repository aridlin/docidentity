"""Read-only PDF barcode verification; no arbitrary PDF rewriting."""
from pathlib import Path
import re
import subprocess
import tempfile
from .core import validate,path_of,embedded,PREFIX

def pdf_info(path):
    return subprocess.check_output(['pdfinfo',str(path_of(path))],text=True,stderr=subprocess.PIPE)

def verify_barcode(path,identity,first_page_only=False):
    validate(identity)
    path=path_of(path)
    info=pdf_info(path)
    pages=re.search(r'^Pages:\s+(\d+)',info,re.M)
    if not pages: raise ValueError('Cannot determine PDF page count')
    with tempfile.TemporaryDirectory(prefix='docidentity-pdf-verify-') as temp:
        out=Path(temp)/'page'
        for page in range(1,(1 if first_page_only else int(pages.group(1)))+1):
            subprocess.run(['pdftoppm','-f',str(page),'-l',str(page),'-singlefile','-scale-to','2500','-png',str(path),str(out)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
            scan=subprocess.run(['zbarimg','--quiet','--raw',str(out)+'.png'],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True)
            if identity not in scan.stdout.splitlines():
                raise ValueError(f'PDF page {page} has no decodable matching visible barcode. Output remains unregistered.')
    return 1 if first_page_only else int(pages.group(1))

def register_export(source,output,registry):
    m=embedded(path_of(source));identity=validate(m[PREFIX+'ID'])
    verify_barcode(output,identity)
    registry.reconcile(identity,source,m.get(PREFIX+'RegisteredURI',''),m.get(PREFIX+'Parent') or None)
    registry.commit(identity,output,event='PDF_EXPORTED',source=identity)
    return identity
