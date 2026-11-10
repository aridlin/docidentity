from pathlib import Path
import os
import unittest
from unittest.mock import patch
from docidentity.desktop import launch_lookup


class DesktopTests(unittest.TestCase):
    def test_launch_uses_bundled_package_database_and_separate_process(self):
        with patch.dict(os.environ,{'QT_PLUGIN_PATH':'office/plugins','QT_QPA_PLATFORM_PLUGIN_PATH':'office/platforms'}),patch('docidentity.desktop.subprocess.Popen') as launch:
            launch_lookup('@$'+'A'*32,Path('/tmp/registry with spaces.db'))
        args=launch.call_args.args[0]
        self.assertEqual(args,['/usr/bin/python','-m','docidentity.cli','--database','/tmp/registry with spaces.db','lookup','@$'+'A'*32])
        options=launch.call_args.kwargs
        self.assertTrue(options['start_new_session'])
        self.assertEqual(Path(options['env']['PYTHONPATH'])/'docidentity',Path(__file__).resolve().parents[1]/'docidentity')
        self.assertNotIn('QT_PLUGIN_PATH',options['env'])
        self.assertNotIn('QT_QPA_PLATFORM_PLUGIN_PATH',options['env'])
