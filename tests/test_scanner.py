import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch
from evdev import InputEvent,ecodes as E
spec=importlib.util.spec_from_file_location('scanner_commands',Path(__file__).resolve().parent.parent/'integration/scanner_adapter.py')
scanner=importlib.util.module_from_spec(spec);spec.loader.exec_module(scanner)

def key(code,value):return InputEvent(0,0,E.EV_KEY,code,value)
def events(text,terminator=E.KEY_ENTER):
    output=[]
    for char in text:
        shift=char in '@#$' or char.isupper()
        base={'@':'2','#':'3','$':'4'}.get(char,char.upper())
        code=getattr(E,'KEY_'+base)
        if shift:output.append(key(E.KEY_LEFTSHIFT,1))
        output.extend([key(code,1),key(code,0)])
        if shift:output.append(key(E.KEY_LEFTSHIFT,0))
    if terminator:output.extend([key(terminator,1),key(terminator,0)])
    return output

class ScannerTests(unittest.TestCase):
    def setUp(self):
        self.emitted=[];self.commands=[];self.lookups=[]
        self.filter=scanner.Filter(self.emitted.append,lambda:self.commands.append(True),self.lookups.append)
    def feed(self,value,terminator=E.KEY_ENTER):
        for event in events(value,terminator):self.filter.feed(event)
    def test_document_scan_consumed_and_dispatched_once(self):
        identity='@$0123456789ABCDEF0123456789ABCDEF'
        self.feed(identity);self.filter.idle()
        self.assertEqual([identity],self.lookups);self.assertEqual([],self.emitted);self.assertEqual([],self.commands)
    def test_existing_command_unchanged(self):
        self.feed('@#clipbin');self.filter.idle()
        self.assertEqual([True],self.commands);self.assertEqual([],self.lookups);self.assertEqual([],self.emitted)
    def test_unknown_command_still_reserved(self):
        self.feed('@#unknown');self.filter.idle()
        self.assertEqual([],self.emitted);self.assertEqual([],self.lookups);self.assertEqual([],self.commands)
    def test_regular_barcode_passthrough_exact(self):
        original=events('AbC0123456789')
        for event in original:self.filter.feed(event)
        self.filter.idle();self.assertEqual(original,self.emitted)
    def test_tab_and_idle_termination(self):
        identity='@$ABCDEF0123456789ABCDEF0123456789'
        self.feed(identity,E.KEY_TAB);self.feed(identity,None);self.filter.idle();self.filter.idle()
        self.assertEqual([identity,identity],self.lookups)
    def test_malformed_never_launched(self):
        self.feed('@$BAD');self.filter.idle();self.assertEqual([],self.lookups);self.assertEqual([],self.emitted)
    def test_launch_argument_list_no_shell(self):
        identity='@$'+'A'*32
        with patch.object(scanner.subprocess,'Popen') as launch:
            scanner.launch_lookup(identity)
            self.assertEqual([scanner.LOOKUP,'lookup',identity],launch.call_args.args[0])
            self.assertNotIn('shell',launch.call_args.kwargs)

if __name__=='__main__':unittest.main()
