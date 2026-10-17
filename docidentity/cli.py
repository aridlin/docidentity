import argparse
import json
from pathlib import Path
import sys
from .core import Registry, new_id, path_of, validate

def make_pdf(output,text,registry):
    # Only creates a new PDF; never rewrites arbitrary existing PDFs.
    import cairo
    from .barcode import modules
    dest=path_of(output)
    # Exclusive reservation prevents accidental overwrite.
    with dest.open('xb'): pass
    identity=new_id()
    try:
        surface=cairo.PDFSurface(str(dest),595.28,841.89)
        ctx=cairo.Context(surface)
        ctx.set_source_rgb(1,1,1); ctx.paint(); ctx.set_source_rgb(0,0,0)
        ctx.select_font_face('sans-serif'); ctx.set_font_size(11)
        for n,line in enumerate(text.splitlines()):
            if n>=52: raise ValueError('Text exceeds one-page PDF; use library for more complex layouts')
            ctx.move_to(48,110+13*n); ctx.show_text(line)
        bits=modules(identity); module=.76
        x=595.28-36-len(bits)*module
        for i,bit in enumerate(bits):
            if bit: ctx.rectangle(x+i*module,30,module,40)
        ctx.fill(); ctx.set_font_size(8); ctx.move_to(x+10*module,82); ctx.show_text(identity)
        surface.set_metadata(cairo.PDF_METADATA_SUBJECT,'DocIdentity '+identity)
        surface.set_metadata(cairo.PDF_METADATA_CREATOR,'docidentity')
        ctx.show_page(); surface.finish()
        registry.commit(identity,dest)
        return identity
    except Exception:
        # Keep a successfully written file on DB failure for diagnostic recovery.
        raise

def register_generated_pdf(path,registry):
    """Recover/register this tool's PDF output, without modifying its contents."""
    import re
    from .pdf_support import pdf_info,verify_barcode
    dest=path_of(path)
    info=pdf_info(dest)
    subject=re.search(r'^Subject:\s+DocIdentity (@\$[0-9A-F]{32})\s*$',info,re.M)
    creator=re.search(r'^Creator:\s+docidentity\s*$',info,re.M)
    if not subject or not creator: raise ValueError('Only PDFs created by docidentity can be registered with this recovery command')
    identity=validate(subject.group(1))
    verify_barcode(dest,identity,first_page_only=True)
    registry.commit(identity,dest)
    return identity

def main(argv=None):
    p=argparse.ArgumentParser(description='Local document identity and barcode tools')
    p.add_argument('--database',type=Path)
    p.add_argument('--pipe',help='Connect to an explicitly launched local UNO pipe instead of starting a one-shot process')
    sub=p.add_subparsers(dest='command',required=True)
    for command in ('lookup','info'):
        s=sub.add_parser(command); s.add_argument('identity')
    s=sub.add_parser('register'); s.add_argument('file')
    s=sub.add_parser('register-pdf'); s.add_argument('file')
    s=sub.add_parser('export'); s.add_argument('file'); s.add_argument('output')
    s=sub.add_parser('register-export'); s.add_argument('file'); s.add_argument('output')
    s=sub.add_parser('pdf'); s.add_argument('output'); s.add_argument('--text',required=True)
    s=sub.add_parser('reconcile'); s.add_argument('file')
    sub.add_parser('check')
    s=sub.add_parser('backup'); s.add_argument('output')
    args=p.parse_args(argv)
    try:
        registry=Registry(args.database)
        try:
            if args.command=='lookup':
                from .gui import show
                show(registry,validate(args.identity))
            elif args.command=='info': print(json.dumps(registry.info(args.identity),indent=2))
            elif args.command=='pdf': print(make_pdf(args.output,args.text,registry))
            elif args.command=='register-export':
                from .pdf_support import register_export
                print(register_export(args.file,args.output,registry))
            elif args.command=='register-pdf': print(register_generated_pdf(args.file,registry))
            elif args.command=='reconcile':
                from .core import embedded,PREFIX
                m=embedded(args.file)
                warnings=registry.reconcile(m[PREFIX+'ID'],args.file,m.get(PREFIX+'RegisteredURI',''),m.get(PREFIX+'Parent') or None)
                registry.recover_edges(json.loads(m.get(PREFIX+'RecoveryEdges') or '[]'))
                print(json.dumps(warnings,indent=2))
            elif args.command=='check':
                result=registry.db.execute('PRAGMA integrity_check').fetchone()[0]
                fk=registry.db.execute('PRAGMA foreign_key_check').fetchall()
                print(result)
                if result!='ok' or fk: return 1
            elif args.command=='backup':
                import sqlite3
                with Path(args.output).open('xb'): pass
                target=sqlite3.connect(args.output)
                try: registry.db.backup(target)
                finally: target.close()
            else:
                from .office import Office, isolated_office
                import contextlib
                with (contextlib.nullcontext(Office(args.pipe)) if args.pipe else isolated_office()) as office:
                    print(office.register(args.file,registry) if args.command=='register' else office.export(args.file,args.output,registry))
        finally: registry.close()
        return 0
    except Exception as exc:
        print('docidentity: '+str(exc),file=sys.stderr)
        return 1

if __name__=='__main__': raise SystemExit(main())
