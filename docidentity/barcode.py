"""Code 128 subset B, ISO/IEC 15417 widths, 10-module quiet zones.
Opaque RGB PNG avoids palette-dependent barcode rendering in PDF print drivers.
"""
import struct
import zlib
from .core import validate
PATTERNS = '''212222 222122 222221 121223 121322 131222 122213 122312 132212 221213 221312 231212 112232 122132 122231 113222 123122 123221 223211 221132 221231 213212 223112 312131 311222 321122 321221 312212 322112 322211 212123 212321 232121 111323 131123 131321 112313 132113 132311 211313 231113 231311 112133 112331 132131 113123 113321 133121 313121 211331 231131 213113 213311 213131 311123 311321 331121 312113 312311 332111 314111 221411 431111 111224 111422 121124 121421 141122 141221 112214 112412 122114 122411 142112 142211 241211 221114 413111 241112 134111 111242 121142 121241 114212 124112 124211 411212 421112 421211 212141 214121 412121 111143 111341 131141 114113 114311 411113 411311 113141 114131 311141 411131 211412 211214 211232 2331112'''.split()

def modules(identity):
    validate(identity)
    codes=[104]+[ord(c)-32 for c in identity]
    codes += [(104+sum(i*c for i,c in enumerate(codes[1:],1)))%103,106]
    bits=[0]*10
    for code in codes:
        for i,width in enumerate(PATTERNS[code]): bits.extend([int(i%2==0)]*int(width))
    return bits+[0]*10

def png(identity, scale=12, height=600):
    bits=modules(identity)
    row=b'\0'+b''.join(bytes([0 if bit else 255])*3*scale for bit in bits)
    width=len(bits)*scale
    def chunk(kind,payload):
        return struct.pack('!I',len(payload))+kind+payload+struct.pack('!I',zlib.crc32(kind+payload)&0xffffffff)
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('!IIBBBBB',width,height,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(row*height))+chunk(b'IEND',b'')
