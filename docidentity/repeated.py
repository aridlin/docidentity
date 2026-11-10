"""One managed barcode per printed page, using application-specific repetition."""
import json
import struct
import zlib
import uno
from .core import MANAGED, PREFIX, validate
from .barcode import modules

LAYOUT = 'CalcHeaders'

def _raw(doc):
    from .office import kind
    if kind(doc)=='writer':
        collection=doc.GraphicObjects
        return [collection.getByName(n) for n in collection.ElementNames if collection.getByName(n).Name.startswith(MANAGED)]
    return [page.getByIndex(i) for n in range(doc.DrawPages.Count) for page in [doc.DrawPages.getByIndex(n)] for i in range(page.Count) if page.getByIndex(i).Name.startswith(MANAGED)]

def _calc_records(doc):
    from .office import metadata
    value=json.loads(metadata(doc).get(PREFIX+LAYOUT) or '{}')
    if not isinstance(value,dict):raise ValueError('Invalid managed header metadata')
    return value

def _calc_styles(doc):
    family=doc.StyleFamilies.getByName('PageStyles')
    names=sorted({doc.Sheets.getByIndex(i).PageStyle for i in range(doc.Sheets.Count)})
    return [(name,family.getByName(name)) for name in names]

def _writer_styles(doc):
    family=doc.StyleFamilies.getByName('PageStyles')
    names={name for name in family.ElementNames if family.getByName(name).isInUse()}
    names.add(doc.Text.createTextCursor().PageStyleName or 'Standard')
    queue=list(names)
    while queue:
        follow=family.getByName(queue.pop()).FollowStyle
        if follow and family.hasByName(follow) and follow not in names:names.add(follow);queue.append(follow)
    return [(name,family.getByName(name)) for name in sorted(names)]

def _headers(style):
    result=[]
    for name in ('HeaderText','HeaderTextLeft','HeaderTextRight','HeaderTextFirst'):
        if style.PropertySetInfo.hasPropertyByName(name):
            text=style.getPropertyValue(name)
            if text is not None and all(text!=old for old in result):result.append(text)
    return result

def managed_objects(doc):
    from .office import kind
    raw=_raw(doc)
    if kind(doc)!='calc':return raw
    records=_calc_records(doc)
    return [CalcHeader(doc,name,style) for name,style in _calc_styles(doc) if name in records and style.HeaderBackGraphic is not None]+raw

def _anchor_text(obj):
    anchor=obj.getAnchor()
    return anchor.getText() if anchor is not None else None

def coverage_complete(doc):
    from .office import kind
    k=kind(doc)
    if k=='calc':
        records=_calc_records(doc)
        return not _raw(doc) and all(name in records and style.HeaderIsOn and style.HeaderBackGraphic is not None for name,style in _calc_styles(doc))
    raw=_raw(doc)
    if k=='writer':
        expected=[]
        for _,style in _writer_styles(doc):
            if not style.HeaderIsOn:return False
            expected.extend(_headers(style))
        return len(raw)==len(expected) and all(sum(_anchor_text(obj)==text for obj in raw)==1 for text in expected)
    return all(sum(page.getByIndex(i).Name.startswith(MANAGED) for i in range(page.Count))==1 for n in range(doc.DrawPages.Count) for page in [doc.DrawPages.getByIndex(n)])

def _remove(doc,obj):
    from .office import kind
    if kind(doc)=='writer':(_anchor_text(obj) or doc.Text).removeTextContent(obj)
    else:
        for n in range(doc.DrawPages.Count):
            page=doc.DrawPages.getByIndex(n)
            if any(page.getByIndex(i)==obj for i in range(page.Count)):page.remove(obj);break

def _writer(doc,ctx,identity,restore,update):
    from .office import graphic
    targets=[]
    for name,style in _writer_styles(doc):
        style.HeaderIsOn=True
        for index,text in enumerate(_headers(style)):targets.append((name,index,text))
    raw=_raw(doc);kept=[]
    for name,index,text in targets:
        matches=[obj for obj in raw if _anchor_text(obj)==text]
        fresh=not matches
        if fresh:
            obj=doc.createInstance('com.sun.star.text.TextGraphicObject')
            obj.Name=MANAGED+'.Writer.'+name+'.'+str(index)
            obj.Graphic=graphic(ctx,identity)
            obj.AnchorType=uno.Enum('com.sun.star.text.TextContentAnchorType','AT_PARAGRAPH')
            obj.Surround=uno.Enum('com.sun.star.text.WrapTextMode','THROUGH')
            text.insertTextContent(text.Start,obj,False)
        else:
            obj=matches[0]
            if update:obj.Graphic=graphic(ctx,identity)
        if fresh or restore:
            # Header graphics repeat automatically on every page, including new pages.
            style=doc.StyleFamilies.getByName('PageStyles').getByName(name)
            if style.TopMargin<2200:style.TopMargin=2200
            obj.Width=11000;obj.Height=1400
            obj.HoriOrient=0;obj.VertOrient=0;obj.HoriOrientRelation=7;obj.VertOrientRelation=7
            obj.HoriOrientPosition=max(0,style.Width-style.RightMargin-11000);obj.VertOrientPosition=400
        obj.Description='Document identity '+identity+' (managed Code 128)';kept.append(obj)
    for obj in raw:
        if all(obj!=item for item in kept):_remove(doc,obj)
    return kept[0]

def _canvas(identity,width,height,x,y):
    # AREA fills a physical header rectangle. A full canvas avoids Calc's image-DPI
    # dependent cropping, while preserving a dedicated blank area for header text.
    ppm=300/2540
    w,h=round(width*ppm),round(height*ppm);left,top=round(x*ppm),round(y*ppm)
    bits=modules(identity);bar_width=len(bits)*3;bar_height=round(1400*ppm)
    if left<0 or top<0 or left+bar_width>w or top+bar_height>h:raise ValueError('Barcode does not fit within the printed header')
    row=bytearray([255])*(w*3)
    for i,bit in enumerate(bits):
        if bit:row[(left+i*3)*3:(left+(i+1)*3)*3]=b'\0'*9
    white=b'\0'+bytes([255])*(w*3)
    pixels=white*top+(b'\0'+bytes(row))*bar_height+white*(h-top-bar_height)
    def chunk(kind,payload):return struct.pack('!I',len(payload))+kind+payload+struct.pack('!I',zlib.crc32(kind+payload)&0xffffffff)
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('!IIBBBBB',w,h,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(pixels))+chunk(b'IEND',b'')

def _graphic_bytes(ctx,data):
    from .office import prop
    stream=ctx.ServiceManager.createInstanceWithContext('com.sun.star.io.SequenceInputStream',ctx)
    stream.initialize((uno.ByteSequence(data),))
    provider=ctx.ServiceManager.createInstanceWithContext('com.sun.star.graphic.GraphicProvider',ctx)
    return provider.queryGraphic((prop('InputStream',stream),prop('LazyRead',False)))

def _header_content_height(style):
    height=max(750,style.HeaderHeight or 0)
    for field in ('RightPageHeaderContent','LeftPageHeaderContent','FirstPageHeaderContent'):
        if not style.PropertySetInfo.hasPropertyByName(field):continue
        content=style.getPropertyValue(field)
        for text in (content.LeftText,content.CenterText,content.RightText):
            cursor=text.createTextCursor();cursor.gotoStart(False);cursor.gotoEnd(True)
            points=cursor.CharHeight or 16
            height=max(height,int(max(1,len(text.String.splitlines()))*points*35.28*1.6))
    return height

class CalcHeader:
    """A managed repeated image belongs to a page style, not a sheet drawing."""
    def __init__(self,doc,name,style):self.doc=doc;self.name=name;self.style=style;self.Name=MANAGED+'.Calc.'+name
    @property
    def Graphic(self):return self.style.HeaderBackGraphic
    def getPosition(self):
        from .office import point
        return point(*_calc_records(self.doc)[self.name]['position'])
    def getSize(self):
        from .office import size
        return size(11000,1400)

def _apply_calc(doc,name,style,records,identity,ctx,update):
    from .office import set_meta
    record=records[name]
    width=style.Width-style.LeftMargin-style.RightMargin-style.HeaderLeftMargin-style.HeaderRightMargin
    x,y=record['position']
    if width<11000 or x<0 or y<0 or x+11000>width:raise ValueError('Page header is too narrow for a scannable 110 mm barcode; adjust page margins or orientation')
    height=2*(y+1400)+record['base_height']+400
    style.HeaderIsOn=True;style.HeaderIsDynamicHeight=False;style.HeaderHeight=height
    if update or style.HeaderBackGraphic is None:
        style.HeaderBackGraphic=_graphic_bytes(ctx,_canvas(identity,width,height,x,y))
        style.HeaderBackGraphicLocation=uno.Enum('com.sun.star.style.GraphicLocation','AREA')
    set_meta(doc,{LAYOUT:json.dumps(records,separators=(',',':'))})

def _calc(doc,ctx,identity,restore,update):
    from .office import set_meta
    records=_calc_records(doc);targets=_calc_styles(doc)
    # Validate all styles before changing or deleting any previous managed drawing.
    for name,style in targets:
        if name not in records and style.HeaderBackGraphic is not None:
            raise ValueError('Existing header background on '+name+' must be moved before adding a managed repeating barcode')
        if style.Width-style.LeftMargin-style.RightMargin-style.HeaderLeftMargin-style.HeaderRightMargin<11000:
            raise ValueError('Printed page is too narrow for the barcode')
    for name,style in targets:
        fresh=name not in records
        if fresh:records[name]={'base_height':_header_content_height(style),'position':[0,0]}
        if fresh or restore:
            width=style.Width-style.LeftMargin-style.RightMargin-style.HeaderLeftMargin-style.HeaderRightMargin
            records[name]['position']=[width-11000,0]
        _apply_calc(doc,name,style,records,identity,ctx,update or fresh or restore)
    for obj in _raw(doc):_remove(doc,obj)
    return CalcHeader(doc,targets[0][0],targets[0][1])

def _impress(doc,ctx,identity,restore,update):
    from .office import graphic
    slots={}
    for n in range(doc.DrawPages.Count):
        page=doc.DrawPages.getByIndex(n)
        existing=[page.getByIndex(i) for i in range(page.Count) if page.getByIndex(i).Name.startswith(MANAGED)]
        if existing and not restore:continue
        width,height=11000,1400
        for x,y in ((page.Width-width-500,page.Height-height-500),(500,page.Height-height-500),(page.Width-width-500,500),(500,500)):
            if x<0 or y<0:continue
            occupied=False
            for i in range(page.Count):
                other=page.getByIndex(i)
                if other.Name.startswith(MANAGED):continue
                p,s=other.getPosition(),other.getSize()
                if x<p.X+s.Width and x+width>p.X and y<p.Y+s.Height and y+height>p.Y:occupied=True;break
            if not occupied:slots[n]=(x,y);break
        else:raise ValueError('No vacant corner for barcode on slide '+str(n+1)+'. Move content before registering.')
    first=None
    for n in range(doc.DrawPages.Count):
        page=doc.DrawPages.getByIndex(n)
        found=[page.getByIndex(i) for i in range(page.Count) if page.getByIndex(i).Name.startswith(MANAGED)]
        fresh=not found
        geometry=None
        if not fresh:
            current=found[0]
            geometry=(current.getSize(),current.getPosition())
        if fresh:
            obj=doc.createInstance('com.sun.star.drawing.GraphicObjectShape');obj.Name=MANAGED+'.Slide.'+str(n+1)
            obj.Graphic=graphic(ctx,identity);page.add(obj)
            try:
                from .office import size,point
                obj.setSize(size(11000,1400));obj.setPosition(point(*slots[n]))
            except Exception:page.remove(obj);raise
        else:
            obj=found[0]
            if update:obj.Graphic=graphic(ctx,identity)
            if restore:
                from .office import size,point
                obj.setSize(size(11000,1400));obj.setPosition(point(*slots[n]))
        for extra in found[1:]:page.remove(extra)
        obj.Description='Document identity '+identity+' (managed Code 128)'
        # Graphic replacement can reset a drawing's geometry. Apply dimensions
        # and final position after all graphic/property changes, also on edits.
        from .office import size,point
        if fresh or restore:
            obj.setSize(size(11000,1400));obj.setPosition(point(*slots[n]))
        elif update:
            obj.setSize(geometry[0]);obj.setPosition(geometry[1])
        if first is None:first=obj
    if first is None:raise ValueError('Document has no slides')
    return first

def ensure(doc,ctx,identity,restore=False,update=True):
    from .office import kind,set_meta
    validate(identity)
    result={'writer':_writer,'calc':_calc,'impress':_impress}[kind(doc)](doc,ctx,identity,restore,update)
    set_meta(doc,{'PageCoverage':'all-pages-v1','BarcodeID':identity})
    return result
