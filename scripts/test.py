"""Run core and real UNO tests in a disposable profile; no user documents touched."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from docidentity.office import Office
# Run the CLI and UNO domains in separate processes, matching installed usage.
if not sys.argv[1:]:
    for pattern in ('test_core.py','test_cli.py','test_scanner.py'):
        completed=subprocess.run([sys.executable,'-m','unittest','discover','-s','tests','-p',pattern,'-v'])
        if completed.returncode: raise SystemExit(completed.returncode)
with tempfile.TemporaryDirectory(prefix='docidentity-test-') as temp:
    root=Path(temp); pipe='docidentity_test_'+str(os.getpid())
    env=dict(os.environ,DOCIDENTITY_DATA_HOME=str(root/'data'),DOCIDENTITY_TEST_PIPE=pipe,SAL_USE_VCLPLUGIN='svp')
    env.pop('DISPLAY',None)
    proc=subprocess.Popen(['/usr/bin/soffice','-env:UserInstallation='+ (root/'profile').as_uri(),'--headless','--norestore','--nodefault','--nofirststartwizard','--accept=pipe,name='+pipe+';urp;StarOffice.ServiceManager'],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
    try:
        for _ in range(100):
            try: Office(pipe);break
            except Exception:
                if proc.poll() is not None: raise RuntimeError(proc.stderr.read().decode())
                time.sleep(.1)
        else: raise RuntimeError('LibreOffice pipe startup timeout')
        result=subprocess.run(([sys.executable,'-m','unittest']+sys.argv[1:]) if sys.argv[1:] else [sys.executable,'scripts/uno_tests.py'],env=env)
    finally:
        unexpected=proc.poll()
        proc.terminate()
        try: proc.wait(10)
        except subprocess.TimeoutExpired: proc.kill();proc.wait()
        stderr=proc.stderr.read().decode()
        if stderr: print('LibreOffice diagnostics:',stderr)
        if unexpected is not None: print('Unexpected LibreOffice exit:',unexpected)
    raise SystemExit(result.returncode)
