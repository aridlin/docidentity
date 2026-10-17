from pathlib import Path
import zipfile
root=Path(__file__).resolve().parent.parent
(root/'dist').mkdir(exist_ok=True)
out=root/'dist/docidentity-0.2.0.oxt'
with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
    for p in sorted((root/'extension').rglob('*')):
        if p.is_file() and '__pycache__' not in p.parts: z.write(p,p.relative_to(root/'extension'))
    for p in sorted((root/'docidentity').glob('*.py')): z.write(p,'docidentity/'+p.name)
print(out)
import tarfile
archive=root/'dist/docidentity-0.2.0-source.tar.gz'
with tarfile.open(archive,'w:gz') as tar:
    for name in ('docidentity','extension','scripts','tests','docs','integration','AGENTS.md','README.md','pyproject.toml','.gitignore'):
        p=root/name
        if p.is_file(): tar.add(p,arcname='docidentity-0.2.0/'+name)
        else:
            for item in sorted(p.rglob('*')):
                if item.is_file() and '__pycache__' not in item.parts:
                    tar.add(item,arcname='docidentity-0.2.0/'+str(item.relative_to(root)))
print(archive)
