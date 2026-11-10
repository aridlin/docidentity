"""Launch Qt outside LibreOffice's Python and GUI event loop."""
import os
from pathlib import Path
import subprocess


def launch_lookup(identity, database):
    env = dict(os.environ)
    # Use the bundled package, including in an isolated OXT installation.
    env['PYTHONPATH'] = str(Path(__file__).resolve().parent.parent)
    # LibreOffice sets these for its own bundled Qt plugins. System Qt needs its own.
    for key in ('QT_QPA_PLATFORM_PLUGIN_PATH', 'QT_PLUGIN_PATH'):
        env.pop(key, None)
    return subprocess.Popen(
        ['/usr/bin/python', '-m', 'docidentity.cli', '--database', str(database), 'lookup', identity],
        env=env, stdin=subprocess.DEVNULL, start_new_session=True)
