#!/usr/bin/env python3
"""User-only install/upgrade/remove. No root and no running background service."""
import argparse
import hashlib
import datetime
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
root=Path(__file__).resolve().parent.parent
p=argparse.ArgumentParser()
p.add_argument('--remove',action='store_true')
p.add_argument('--global-policy',action='store_true')
p.add_argument('--skip-extension',action='store_true')
p.add_argument('--scanner-integration',action='store_true',help='Extend the existing device-specific scanner service with @$ lookup dispatch')
a=p.parse_args()
office_env=dict(os.environ,SAL_USE_VCLPLUGIN='svp');office_env.pop('DISPLAY',None)
base=Path(os.environ.get('XDG_DATA_HOME',Path.home()/'.local/share'))/'docidentity'
binpath=Path.home()/'.local/bin/docidentity'
desktop=base.parent/'applications/docidentity.desktop'
if a.remove:
    manifest=base/'scanner-integration.json'
    if manifest.exists():
        record=json.loads(manifest.read_text());target=Path(record['target'])
        if hashlib.sha256(target.read_bytes()).hexdigest()!=record['installed_sha256']:
            raise RuntimeError('Scanner handler has later changes; restore its saved backup before removal')
        shutil.copy2(record['backup'],target)
        subprocess.run(['systemctl','--user','restart','scanner-commands.service'],check=True)
        manifest.unlink();print('Restored scanner handler backup; existing scanner service retained.')
    if not a.skip_extension: subprocess.run(['/usr/bin/unopkg','remove','org.aridlin.docidentity'],env=office_env,check=True)
    if binpath.exists(): binpath.unlink()
    if desktop.exists(): desktop.unlink()
    shutil.rmtree(base/'app',ignore_errors=True)
    print('Removed application. Registry and global document policy retained.')
else:
    base.mkdir(parents=True,exist_ok=True,mode=0o700)
    destination=base/'app/docidentity'
    destination.mkdir(parents=True,exist_ok=True)
    for source in (root/'docidentity').glob('*.py'): shutil.copy2(source,destination/source.name)
    binpath.parent.mkdir(parents=True,exist_ok=True)
    launcher='#!/bin/sh\nPYTHONPATH='+shlex.quote(str(base/'app'))+'${PYTHONPATH:+:$PYTHONPATH} exec /usr/bin/python -m docidentity.cli "$@"\n'
    if binpath.exists() and binpath.read_text()!=launcher and 'docidentity.cli' not in binpath.read_text(): raise RuntimeError('Refusing to replace unrelated executable')
    binpath.write_text(launcher);binpath.chmod(0o755)
    desktop.parent.mkdir(parents=True,exist_ok=True)
    desktop.write_text('[Desktop Entry]\nType=Application\nName=Document Identity\n'
        'Comment=Find registered documents and open their folders\n'
        'Exec="'+str(binpath).replace('\\','\\\\').replace('"','\\"')+'" lookup\n'
        'Icon=document-properties\nTerminal=false\nCategories=Office;\n')
    if not a.skip_extension:
        subprocess.run([sys.executable,str(root/'scripts/build.py')],check=True)
        subprocess.run(['/usr/bin/unopkg','add','--force',str(root/'dist/docidentity-0.3.0.oxt')],env=office_env,check=True)
    if a.global_policy:
        target=Path(os.environ.get('CODEX_HOME',Path.home()/'.codex'))/'AGENTS.md'
        target.parent.mkdir(parents=True,exist_ok=True)
        snippet=(root/'docs/GLOBAL-AGENTS-snippet.md').read_text()
        existing=target.read_text() if target.exists() else ''
        if '## Registered document generation' not in existing:
            with target.open('a') as f: f.write('\n'+snippet+'\n')
        print('Global policy: '+str(target))
    print('Installed '+str(binpath)+'; restart all LibreOffice processes to activate the extension.')

if a.scanner_integration and not a.remove:
    import importlib.util
    spec=importlib.util.spec_from_file_location('scanner_adapter',root/'integration/scanner_adapter.py')
    adapter=importlib.util.module_from_spec(spec);spec.loader.exec_module(adapter)
    target=Path.home()/'.local/share/scanner-commands/scanner_commands.py'
    original=target.read_text();updated=adapter.patch_handler(original)
    if updated!=original:
        backup=target.with_name(target.name+'.before-docidentity-'+datetime.datetime.now().strftime('%Y%m%d%H%M%S'))
        shutil.copy2(target,backup);target.write_text(updated);target.chmod(0o700)
        record={'target':str(target),'backup':str(backup),'installed_sha256':hashlib.sha256(target.read_bytes()).hexdigest()}
        (base/'scanner-integration.json').write_text(json.dumps(record))
        print('Scanner handler backup: '+str(backup))
    subprocess.run(['systemctl','--user','restart','scanner-commands.service'],check=True)
    print('Existing scanner service updated and restarted; @# commands retained.')
