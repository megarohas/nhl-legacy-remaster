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
    column(d, T['leaguerostertable'], 'team', live_only=True)   # сейв: только живые записи

Строк у таблиц alloc 2/6 — max (места); в сейвах игры записи из них — только live_rows: [0, current)
без удалённых (список свободных, tdb.py «Живые записи»). Командная строка считает только живые.
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

def live_rows(d, tinfo):
    """Номера живых записей таблицы: [0, current) без удалённых. Заголовок: +0x16 current, +0x18 число
    удалённых, +0x1A голова списка свободных (0xFFFF — пусто); у удалённой записи первые 16 бит — номер
    следующей. Список испорчен (цикл, номер за max, длина не та) — ValueError."""
    rows, reclen, rb, fds, fmeta = tinfo
    base = rb - 0x28 - 16 * len(fds)
    E = '>' if d[4] == 1 else '<'
    maxr, cur, n, r = struct.unpack(E + 'HHHH', d[base + 0x14:base + 0x1C])
    dead = set()
    while r != 0xFFFF:
        if r >= maxr or r in dead or len(dead) == n:
            raise ValueError(f'список удалённых записей испорчен (запись {r}, max {maxr}, счётчик {n})')
        dead.add(r)
        r = struct.unpack(E + 'H', d[rb + r * reclen:rb + r * reclen + 2])[0]
    if len(dead) != n:
        raise ValueError(f'в списке удалённых {len(dead)} записей, в счётчике {n}')
    return [x for x in range(cur) if x not in dead]

def column(d, tinfo, fname, live_only=False):
    """Значения поля по строкам range(rows); live_only — только живых записей (live_rows)."""
    rows, reclen, rb, fds, fmeta = tinfo
    for kind, bitoff, fid, w in fds:
        if fmeta.get(fid, (fid,))[0] == fname:
            vals = []
            for r in (live_rows(d, tinfo) if live_only else range(rows)):
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
        for name, tinfo in sorted(T.items()):
            rows, reclen = tinfo[:2]
            live = len(live_rows(d, tinfo))
            print(f'{name}\t{rows}\t{reclen}' + (f'\tживых {live}' if live != rows else ''))
    else:
        vals = column(d, T[sys.argv[3]], sys.argv[4], live_only=True)
        print(len(vals), 'значений; частые:', Counter(vals).most_common(20))
