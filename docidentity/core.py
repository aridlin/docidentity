from __future__ import annotations
import contextlib
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import threading
from functools import wraps
import xml.etree.ElementTree as ET
import zipfile

PREFIX = 'DocIdentity.'
MANAGED = 'DocIdentity.ManagedBarcode'
ID_RE = re.compile(r'^@\$[0-9A-F]{32}$')

def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()

def new_id():
    return '@$' + secrets.token_hex(16).upper()

def validate(value):
    if not isinstance(value, str) or not ID_RE.fullmatch(value):
        raise ValueError('Expected @$ followed by 32 uppercase hexadecimal characters')
    return value

def data_home():
    p = Path(os.environ.get('DOCIDENTITY_DATA_HOME', Path(os.environ.get('XDG_DATA_HOME', Path.home()/'.local/share'))/'docidentity'))
    p.mkdir(parents=True, exist_ok=True, mode=0o700)
    return p

def path_of(value):
    from urllib.parse import urlparse, unquote
    if str(value).startswith('file:'):
        u = urlparse(str(value))
        if u.netloc not in ('', 'localhost'):
            raise ValueError('Remote file authorities are unsupported')
        return Path(unquote(u.path)).absolute()
    if '://' in str(value):
        raise ValueError('Only local files are supported')
    return Path(value).absolute()

NS = {k:'urn:oasis:names:tc:opendocument:xmlns:'+v+':1.0' for k,v in [('meta','meta'),('draw','drawing'),('office','office'),('text','text'),('style','style'),('svg','svg-compatible')]}
XLINK = '{http://www.w3.org/1999/xlink}href'

def embedded(path):
    with zipfile.ZipFile(path) as z:
        root = ET.fromstring(z.read('meta.xml'))
    return {x.attrib.get('{%s}name'%NS['meta']): x.text or '' for x in root.iter('{%s}user-defined'%NS['meta']) if x.attrib.get('{%s}name'%NS['meta'],'').startswith(PREFIX)}

def hashes(path):
    """odf-v1: canonical XML + binary resources; excludes metadata, managed graphic,
    volatile view settings, thumbnails, manifest. Not semantic equivalence."""
    path = path_of(path)
    raw = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024), b''):
            raw.update(chunk)
    if path.suffix.lower() not in ('.odt','.ods','.odp'):
        return None, raw.hexdigest()
    h = hashlib.sha256(b'odf-v1\0')
    with zipfile.ZipFile(path) as z:
        removed = set()
        trees = {}
        managed_styles=set()
        referenced_styles=set()
        for name in ('content.xml','styles.xml'):
            if name not in z.namelist():
                continue
            root = ET.fromstring(z.read(name))
            for parent in root.iter():
                for child in list(parent):
                    if child.attrib.get('{%s}name'%NS['draw'],'').startswith(MANAGED):
                        for node in child.iter():
                            for attr,value in node.attrib.items():
                                if attr.endswith('}style-name'): managed_styles.add(value)
                        for image in child.iter('{%s}image'%NS['draw']):
                            removed.add(image.attrib.get(XLINK, '').lstrip('./'))
                        parent.remove(child)
            # Calc serializes empty rows to hold a cell-anchored drawing.
            # Remove only trailing rows that contain no cell attributes/content;
            # preserve gaps between data and explicitly formatted blank cells.
            table_ns='urn:oasis:names:tc:opendocument:xmlns:table:1.0'
            for table in root.iter('{%s}table'%table_ns):
                for row in reversed(list(table)):
                    if row.tag!='{%s}table-row'%table_ns: break
                    cells=list(row)
                    if not cells or any(c.tag!='{%s}table-cell'%table_ns or len(c) or any(not key.endswith('}number-columns-repeated') for key in c.attrib) or (c.text or '').strip() for c in cells): break
                    table.remove(row)
            trees[name] = root
        for root in trees.values():
            for node in root.iter():
                for attr,value in node.attrib.items():
                    if attr.endswith('}style-name'): referenced_styles.add(value)
        for root in trees.values():
            for parent in root.iter():
                for child in list(parent):
                    if child.tag=='{%s}style'%NS['style'] and child.attrib.get('{%s}name'%NS['style']) in managed_styles-referenced_styles:
                        parent.remove(child)
        for name in sorted(z.namelist()):
            if name.endswith('/') or name in removed or name in ('meta.xml','settings.xml','META-INF/manifest.xml') or name.startswith(('Thumbnails/','Configurations2/','META-INF/')):
                continue
            content = z.read(name)
            if name in trees:
                content = ET.canonicalize(ET.tostring(trees[name],encoding='unicode'), rewrite_prefixes=True).encode()
            h.update(name.encode()+b'\0'+content+b'\0')
    return h.hexdigest(), raw.hexdigest()

SCHEMA = '''
CREATE TABLE identities(id TEXT PRIMARY KEY CHECK(length(id)=34 AND substr(id,1,2)='@$'), created TEXT NOT NULL, modified TEXT NOT NULL);
CREATE TABLE instances(instance_id INTEGER PRIMARY KEY, identity_id TEXT NOT NULL REFERENCES identities(id), path TEXT NOT NULL, kind TEXT NOT NULL, first_seen TEXT NOT NULL, last_seen TEXT NOT NULL, device INTEGER, inode INTEGER, UNIQUE(identity_id,path));
CREATE INDEX instance_path ON instances(path);
CREATE TABLE lineage(parent TEXT NOT NULL REFERENCES identities(id), child TEXT NOT NULL REFERENCES identities(id), created TEXT NOT NULL, PRIMARY KEY(parent,child), CHECK(parent<>child));
CREATE INDEX lineage_child ON lineage(child);
CREATE TABLE events(event_id INTEGER PRIMARY KEY, identity_id TEXT NOT NULL REFERENCES identities(id), type TEXT NOT NULL, path TEXT, previous_path TEXT, certainty TEXT NOT NULL CHECK(certainty IN ('confirmed','inferred','observed')), detail TEXT NOT NULL DEFAULT '', created TEXT NOT NULL);
CREATE INDEX event_identity ON events(identity_id,event_id);
CREATE TABLE observations(observation_id INTEGER PRIMARY KEY, identity_id TEXT NOT NULL REFERENCES identities(id), path TEXT NOT NULL, normalized TEXT, full_hash TEXT NOT NULL, algorithm TEXT NOT NULL, created TEXT NOT NULL);
CREATE INDEX observation_identity ON observations(identity_id,observation_id);
CREATE TABLE warnings(warning_id INTEGER PRIMARY KEY, identity_id TEXT NOT NULL REFERENCES identities(id), path TEXT, code TEXT NOT NULL, detail TEXT NOT NULL, created TEXT NOT NULL, resolved TEXT);
CREATE TABLE derivatives(source TEXT NOT NULL REFERENCES identities(id), path TEXT NOT NULL, kind TEXT NOT NULL, created TEXT NOT NULL, PRIMARY KEY(source,path));
PRAGMA user_version=1;
'''

def synchronized(method):
    @wraps(method)
    def guarded(self,*args,**kwargs):
        with self.lock: return method(self,*args,**kwargs)
    return guarded

class Registry:
    def __init__(self, path=None):
        self.path = Path(path) if path else data_home()/'registry.sqlite3'
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.lock=threading.RLock()
        self.db = sqlite3.connect(self.path, timeout=10, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA synchronous=FULL')
        version = self.db.execute('PRAGMA user_version').fetchone()[0]
        if version == 0:
            self.db.executescript('BEGIN IMMEDIATE;'+SCHEMA+'COMMIT;')
        elif version != 1:
            raise RuntimeError('Unsupported registry schema; upgrade docidentity')

    @synchronized
    def close(self):
        self.db.close()

    @synchronized
    def event(self, identity, kind, path=None, previous=None, certainty='observed', detail=''):
        self.db.execute('INSERT INTO events(identity_id,type,path,previous_path,certainty,detail,created) VALUES(?,?,?,?,?,?,?)', (identity,kind,str(path) if path else None,str(previous) if previous else None,certainty,detail,now()))

    @synchronized
    def warning(self, identity, path, code, detail):
        self.db.execute('INSERT INTO warnings(identity_id,path,code,detail,created) VALUES(?,?,?,?,?)',(identity,str(path),code,detail,now()))

    @synchronized
    def commit(self, identity, path, parent=None, event='REGISTERED', previous=None, source=None):
        validate(identity)
        if parent: validate(parent)
        path = path_of(path)
        normalized, full = hashes(path)  # no DB changes if hashing/read fails
        stat = path.stat()
        timestamp = now()
        with self.db:
            self.db.execute('INSERT OR IGNORE INTO identities VALUES(?,?,?)',(identity,timestamp,timestamp))
            if parent and parent != identity:
                self.db.execute('INSERT OR IGNORE INTO identities VALUES(?,?,?)',(parent,timestamp,timestamp))
                self.db.execute('INSERT OR IGNORE INTO lineage VALUES(?,?,?)',(parent,identity,timestamp))
            if event in ('REGISTERED','MODIFIED','IDENTITY_RECONCILED'):
                self.db.execute('UPDATE identities SET modified=? WHERE id=?',(timestamp,identity))
            self.db.execute('INSERT INTO instances(identity_id,path,kind,first_seen,last_seen,device,inode) VALUES(?,?,?,?,?,?,?) ON CONFLICT(identity_id,path) DO UPDATE SET last_seen=excluded.last_seen,device=excluded.device,inode=excluded.inode',(identity,str(path),path.suffix.lower(),timestamp,timestamp,stat.st_dev,stat.st_ino))
            self.db.execute('INSERT INTO observations(identity_id,path,normalized,full_hash,algorithm,created) VALUES(?,?,?,?,?,?)',(identity,str(path),normalized,full,'odf-v1' if normalized else 'sha256',timestamp))
            self.event(identity,event,path,previous,certainty='confirmed' if event in ('REGISTERED','MODIFIED','SAVE_AS','IDENTITY_RECONCILED','PDF_EXPORTED') else 'observed')
            if source:
                validate(source)
                self.db.execute('INSERT OR IGNORE INTO derivatives VALUES(?,?,?,?)',(source,str(path),'PDF',timestamp))
        return identity

    @synchronized
    def reconcile(self, identity, path, registered='', parent=None):
        validate(identity)
        path = path_of(path)
        normalized, full = hashes(path)
        known = self.db.execute('SELECT * FROM instances WHERE identity_id=?',(identity,)).fetchall()
        previous = self.db.execute('SELECT normalized FROM observations WHERE identity_id=? AND normalized IS NOT NULL ORDER BY observation_id DESC LIMIT 1',(identity,)).fetchone()
        existed = self.db.execute('SELECT 1 FROM identities WHERE id=?',(identity,)).fetchone()
        # Recover embedded ancestry after a successful save / failed SQLite commit.
        self.commit(identity,path,parent=parent,event=('OPENED' if any(x['path']==str(path) for x in known) else 'PATH_DISCOVERED') if existed else 'REGISTERED')
        messages=[]
        with self.db:
            if previous and normalized and previous[0] != normalized:
                msg='Same embedded ID has a different normalized content hash. Preserve or fork explicitly.'
                self.warning(identity,path,'HASH_MISMATCH',msg)
                self.event(identity,'HASH_MISMATCH',path)
                messages.append(msg)
            new_location = not any(x['path']==str(path) for x in known)
            if new_location and known:
                same = [x for x in known if Path(x['path']).exists()]
                if same and previous and normalized == previous[0]:
                    self.event(identity,'COPIED',path,certainty='inferred',detail='Matching normalized hash at another accessible location; copy operation not observed')
                missing=[x for x in known if not Path(x['path']).exists()]
                if missing:
                    old=missing[-1]
                    st=path.stat()
                    if old['device']==st.st_dev and old['inode']==st.st_ino and previous and normalized==previous[0]:
                        typ='RENAMED' if Path(old['path']).parent==path.parent else 'MOVED'
                        self.event(identity,typ,path,old['path'],'inferred','Missing prior path, matching device/inode and normalized hash; not proof')
                    else:
                        msg='Prior location missing; move versus copy cannot be determined.'
                        self.warning(identity,path,'AMBIGUOUS_LOCATION',msg)
                        messages.append(msg)
            if registered and str(path_of(registered)) != str(path):
                self.event(identity,'PATH_DISCOVERED',path,registered,detail='Embedded previous location differs; no move asserted')
        return messages

    @synchronized
    def recover_edges(self,edges):
        validated=[]
        for parent,child in edges:
            validate(parent);validate(child)
            if parent==child: raise ValueError('Invalid self-parent in embedded recovery metadata')
            validated.append((parent,child))
        with self.db:
            for parent,child in validated:
                cycle=self.db.execute('WITH RECURSIVE descendants(id) AS (SELECT child FROM lineage WHERE parent=? UNION SELECT lineage.child FROM lineage JOIN descendants ON lineage.parent=descendants.id) SELECT 1 FROM descendants WHERE id=? LIMIT 1',(child,parent)).fetchone()
                if cycle: raise ValueError('Embedded recovery lineage would introduce a cycle')
                for identity in (parent,child): self.db.execute('INSERT OR IGNORE INTO identities VALUES(?,?,?)',(identity,now(),now()))
                self.db.execute('INSERT OR IGNORE INTO lineage VALUES(?,?,?)',(parent,child,now()))

    @synchronized
    def info(self, identity):
        validate(identity)
        row=self.db.execute('SELECT * FROM identities WHERE id=?',(identity,)).fetchone()
        if not row: raise KeyError('Unknown document identity: '+identity)
        result=dict(row)
        for key,query in {
            'locations':'SELECT * FROM instances WHERE identity_id=? ORDER BY last_seen DESC',
            'parents':'SELECT parent AS id FROM lineage WHERE child=?',
            'children':'SELECT child AS id FROM lineage WHERE parent=?',
            'events':'SELECT * FROM events WHERE identity_id=? ORDER BY event_id DESC',
            'hashes':'SELECT * FROM observations WHERE identity_id=? ORDER BY observation_id DESC',
            'warnings':'SELECT * FROM warnings WHERE identity_id=? ORDER BY warning_id DESC',
            'derivatives':'SELECT * FROM derivatives WHERE source=?',
        }.items():
            result[key]=[dict(x) for x in self.db.execute(query,(identity,))]
        for loc in result['locations']:
            try:
                loc['available']=Path(loc['path']).is_file() and os.access(loc['path'],os.R_OK)
            except OSError:
                loc['available']=False
            latest=self.db.execute('SELECT identity_id FROM observations WHERE path=? ORDER BY observation_id DESC LIMIT 1',(loc['path'],)).fetchone()
            loc['current_at_path']=bool(latest and latest[0]==identity)
        return result

class Session:
    """In-memory allocation; disk/registry writes are explicit and save-success only."""
    def __init__(self, identity=None):
        self.committed=validate(identity) if identity else None
        self.provisional=None
        self.suppression=0

    @property
    def current(self): return self.provisional or self.committed

    @contextlib.contextmanager
    def controlled(self):
        self.suppression+=1
        try: yield
        finally: self.suppression-=1

    def modified(self):
        if self.suppression or not self.committed: return False
        if not self.provisional:
            self.provisional=new_id()
            return True
        return False

    def discard(self): self.provisional=None

    def saved(self, registry, path, previous=None):
        identity=self.current
        if not identity: raise ValueError('Unregistered session')
        registry.commit(identity,path,parent=self.committed if self.provisional else None,event='MODIFIED' if self.provisional else ('SAVE_AS' if previous and str(path_of(previous))!=str(path_of(path)) else 'PATH_DISCOVERED'),previous=previous)
        self.committed=identity
        self.provisional=None
