"""Минимальная читалка баз EA TDB v6, только чтение.

Схему берёт из nhlng-meta.xml (nhl-modding-studio, anchors/xbox360/nhl13/).
Для записи нужно пересчитывать CRC, см. docs/formats/tdb-v6-format.md в студии.
База внутри сейва начинается с сигнатуры DB\\x00\\x08 по смещению 0x2C —
read_db находит её сама.

    python tdb_read.py META DB                # таблицы: имя, строк, длина записи
    python tdb_read.py META DB TABLE FIELD    # значения поля

Из кода:
    meta = load_meta(путь_к_meta); d, T = read_db(путь_к_db, meta)
    column(d, T['exhibitionplayerbiotable'], 'year')
"""
import struct, sys, xml.etree.ElementTree as ET
from collections import Counter

def load_meta(path):
    root = ET.parse(path).getroot()
    tables = {}
    for tb in root.iter('table'):
        fields = {f.get('shortname'): (f.get('name'), int(f.get('rangelow')), int(f.get('rangehigh'))) for f in tb.iter('field')}
        tables[tb.get('shortname')] = (tb.get('name'), fields)
    return tables

def read_db(path, meta):
    d = open(path, 'rb').read()
    if d[:2] != b'DB':
        d = d[d.index(b'DB\x00\x08'):]
    be = d[4] == 1
    E = '>' if be else '<'
    ntab = struct.unpack(E+'I', d[0x10:0x14])[0]
    out = {}
    for i in range(ntab):
        tid = d[0x18+8*i:0x18+8*i+4].decode('latin1')
        off = struct.unpack(E+'I', d[0x18+8*i+4:0x18+8*i+8])[0]
        base = 0x18 + 8*ntab + off
        h = d[base:base+0x28]
        alloc = struct.unpack(E+'I', h[4:8])[0]
        reclen = struct.unpack(E+'I', h[8:12])[0]
        maxr, curr = struct.unpack(E+'HH', h[0x14:0x18])
        nf = h[0x1C]
        rows = maxr if alloc in (2, 6) else curr
        fds = []
        for j in range(nf):
            fd = d[base+0x28+16*j: base+0x28+16*j+16]
            kind, bitoff = struct.unpack(E+'II', fd[:8]); fid = fd[8:12].decode('latin1'); w = struct.unpack(E+'I', fd[12:16])[0]
            fds.append((kind, bitoff, fid, w))
        rb = base + 0x28 + 16*nf
        tname, fmeta = meta.get(tid, (tid, {}))
        out[tname] = (rows, reclen, rb, fds, fmeta)
    return d, out

def column(d, tinfo, fname):
    rows, reclen, rb, fds, fmeta = tinfo
    for kind, bitoff, fid, w in fds:
        if fmeta.get(fid, (fid,))[0] == fname:
            vals = []
            for r in range(rows):
                rec = int.from_bytes(d[rb+r*reclen: rb+(r+1)*reclen], 'big')
                total = reclen*8
                vals.append((rec >> (total - bitoff - w)) & ((1 << w) - 1))
            return vals
    raise KeyError(fname)

if __name__ == '__main__':
    if len(sys.argv) not in (3, 5):
        sys.exit(__doc__)
    meta = load_meta(sys.argv[1])
    d, T = read_db(sys.argv[2], meta)
    if len(sys.argv) == 3:
        for name, (rows, reclen, *_ ) in sorted(T.items()):
            print(f'{name}\t{rows}\t{reclen}')
    else:
        vals = column(d, T[sys.argv[3]], sys.argv[4])
        print(len(vals), 'значений; частые:', Counter(vals).most_common(20))
