"""Opt-in adapter for an existing device-specific scanner handler.

This module contains no device selection, clipboard uploader or global input hook.
The installer preserves the host handler's private functions and configuration.
"""
import logging
import re
import subprocess
import time
from pathlib import Path
from evdev import ecodes as E
SHIFTS={E.KEY_LEFTSHIFT,E.KEY_RIGHTSHIFT}
LETTERS={getattr(E,'KEY_'+c.upper()):c for c in 'abcdefghijklmnopqrstuvwxyz'}
PLAIN={getattr(E,'KEY_'+c):c for c in '0123456789'}
PLAIN[E.KEY_SPACE]=' '
SHIFTED={E.KEY_2:'@',E.KEY_3:'#',E.KEY_4:'$'}
DOCUMENT_ID=re.compile(r'^@\$[0-9A-F]{32}$')
LOOKUP=str(Path.home()/'.local/bin/docidentity')

class Filter:
    def __init__(self, emit, command, lookup=None):
        self.emit, self.command = emit, command
        self.lookup=lookup or launch_lookup
        self.reset()
    def reset(self):
        self.mode, self.text, self.buffer, self.shift = 'prefix', '', [], set()
        self.last = None
        self.done = False
    def flush(self):
        for ev in self.buffer:
            self.emit(ev)
        self.buffer.clear()
    def finish(self):
        if self.mode == 'command' and not self.done:
            self.done = True
            if self.text.startswith('@$'):
                identity=self.text.upper()
                if DOCUMENT_ID.fullmatch(identity): self.lookup(identity)
                else: logging.warning('Ignored malformed document lookup scan')
            elif self.text.casefold() == '@#clipbin':
                self.command()
            else:
                logging.info('Ignored unknown reserved scanner command')
    def idle(self):
        if self.mode == 'prefix':
            self.flush()
        self.finish()
        self.reset()
    def feed(self, ev):
        self.last = time.monotonic()
        if self.mode == 'pass':
            self.emit(ev)
        elif self.mode == 'prefix':
            self.buffer.append(ev)
        if ev.type != E.EV_KEY:
            return
        if ev.code in (E.KEY_CAPSLOCK, E.KEY_NUMLOCK, E.KEY_SCROLLLOCK):
            return
        if ev.code in SHIFTS:
            if ev.value: self.shift.add(ev.code)
            else: self.shift.discard(ev.code)
            return
        if ev.code in (E.KEY_ENTER, E.KEY_KPENTER, E.KEY_TAB):
            if ev.value == 1:
                if self.mode == 'prefix':
                    self.flush()
                    self.mode = 'pass'
                self.finish()
            elif ev.value == 0:
                self.reset()
            return
        if ev.value != 1 or self.mode == 'pass' or self.done:
            return
        char = LETTERS.get(ev.code)
        if char is not None and self.shift: char=char.upper()
        if char is None:
            char = (SHIFTED if self.shift else PLAIN).get(ev.code, '\ufffd')
        self.text += char
        if self.mode == 'prefix':
            if self.text in ('@#','@$'):
                self.mode = 'command'
                self.buffer.clear()
            elif not any(prefix.startswith(self.text) for prefix in ('@#','@$')):
                self.mode = 'pass'
                self.flush()
        if len(self.text) > 128:
            self.done = True  # Reserve and discard oversized @# commands.


def launch_lookup(identity):
    if not DOCUMENT_ID.fullmatch(identity): return
    try:
        # Inherit the graphical user session; no shell and no extra input grab.
        subprocess.Popen([LOOKUP,'lookup',identity],stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL,stderr=None,start_new_session=True)
        logging.info('Document lookup window requested')
    except OSError:
        logging.exception('Document lookup could not start')
        logging.error('Check docidentity installation and the desktop session environment')


# Adapter patch helper
MARKER='# DocIdentity scanner adapter v1'
def patch_handler(source):
    """Replace only the recognized input parser; retain host-private functions."""
    import ast
    if MARKER in source:return source
    tree=ast.parse(source)
    nodes=[n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='Filter']
    if len(nodes)!=1:raise ValueError('Expected exactly one existing Filter class')
    node=nodes[0]
    methods={n.name for n in node.body if isinstance(n,ast.FunctionDef)}
    if methods!={'__init__','reset','flush','finish','idle','feed'}:
        raise ValueError('Unrecognized scanner Filter; integrate lookup explicitly instead')
    original=ast.get_source_segment(source,node)
    if '@#clipbin' not in original or 'self.command()' not in original:
        raise ValueError('Unrecognized command dispatch; refusing to replace it')
    adapter=Path(__file__).read_text().split('# Adapter patch helper')[0]
    replacements=[(node.lineno-1,node.end_lineno,MARKER+'\n'+adapter)]
    for item in tree.body:
        if isinstance(item,ast.FunctionDef) and item.name=='launch_lookup':
            replacements.append((item.lineno-1,item.end_lineno,''))
    lines=source.splitlines(keepends=True)
    for start,end,text in sorted(replacements,reverse=True):lines[start:end]=[text+'\n']
    patched=''.join(lines);compile(patched,'scanner_commands.py','exec')
    return patched
