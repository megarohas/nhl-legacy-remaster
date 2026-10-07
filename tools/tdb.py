"""База EA TDB v6 и сейв RosterFile (NHL 12/13): чтение, запись полей, пересчёт CRC.

    python tdb.py verify  FILE                          # все CRC базы и обёртки сейва
    python tdb.py states  FILE                          # leaguestates: type/key -> value
    python tdb.py setstate FILE OUT TYPE KEY VALUE [TYPE KEY VALUE …]
    python tdb.py set     FILE OUT TABLE FIELD ROW VALUE

FILE — `.db` или внутренний файл сейва (`RosterFile`, `Dynasty`…: заголовок 0x2C байт,
база длиной u32@0x24, у франшизы после базы ещё хвост своих данных). Схема полей —
`nhlng-meta.xml` (по умолчанию из ref/nhl-modding-studio, анкер NHL 13 для Xbox 360).

Суммы (nhl-modding-studio, docs/formats/tdb-v6-format-spec.md §2):
- внутри базы — CRC-32/MPEG-2: заголовок [0..0x14] → 0x14; у каждой таблицы prior_crc
  (+0) — тело предыдущей таблицы (у первой — каталог), header_crc (+0x24) — [+4..+0x24];
  последние 4 байта — тело последней таблицы. Тело таблицы — от +0x28 до начала
  следующей (у последней — до EOF−4). Пересчёт: prior_crc → header_crc → EOF → заголовок.
- обёртка сейва — checksum_b (CRC-32/BZIP2 по базе [0x2C..0x2C+размер]) → 0x28, затем
  checksum_a (CRC-32/IEEE по [0x1C..конец файла], с хвостом) → 0x10, оба big-endian.
  Для `Dynasty` NHL 13 проверено на своих сейвах; у `RosterFile` хвоста нет.
"""
import argparse, os, struct, sys, zlib
from tdb_read import load_meta

DEFAULT_META = os.path.join(os.path.dirname(__file__), '..', 'ref', 'nhl-modding-studio', 'anchors',
                            'xbox360', 'nhl13', 'databases', 'nhlng-meta.xml')
CONTAINER_HEADER = 0x2C

_REV8 = bytes(int(f'{i:08b}'[::-1], 2) for i in range(256))

def crc32_bzip2(data):
    """CRC-32/BZIP2 через zlib: отражённый CRC от развёрнутых байтов, развёрнутый обратно."""
    r = zlib.crc32(bytes(data).translate(_REV8))
    return int(f'{r:032b}'[::-1], 2)

def crc32_mpeg2(data):
    return crc32_bzip2(data) ^ 0xFFFFFFFF

def crc32_ieee(data):
    return zlib.crc32(data) & 0xFFFFFFFF

assert crc32_bzip2(b'123456789') == 0xFC891918
assert crc32_mpeg2(b'123456789') == 0x0376E6E7
assert crc32_ieee(b'123456789') == 0xCBF43926

class Tdb:
    def __init__(self, data, meta):
        self.meta = meta
        self.d = bytearray(data)
        if self.d[:2] != b'DB':
            raise ValueError('нет сигнатуры DB')
        self.E = '>' if self.d[4] == 1 else '<'
        n = self.u32(0x10)
        self.tables = []
        for i in range(n):
            tid = bytes(self.d[0x18 + 8 * i:0x1C + 8 * i]).decode('latin1')
            block = 0x18 + 8 * n + self.u32(0x1C + 8 * i)
            h = block
            reclen = self.u32(h + 8)
            maxr, curr = struct.unpack(self.E + 'HH', self.d[h + 0x14:h + 0x18])
            alloc, nf = self.u32(h + 4), self.d[h + 0x1C]
            fields = {}
            for j in range(nf):
                fd = h + 0x28 + 16 * j
                fid = bytes(self.d[fd + 8:fd + 12]).decode('latin1')
                fields[fid] = (self.u32(fd + 4), self.u32(fd + 12))
            name, fmeta = meta.get(tid, (tid, {}))
            byname = {fmeta.get(fid, (fid,))[0]: v for fid, v in fields.items()}
            rows = maxr if alloc in (2, 6) else curr
            self.tables.append(dict(id=tid, name=name, block=block, reclen=reclen, rows=rows,
                                    records=h + 0x28 + 16 * nf, fields=byname))
        self.by_name = {t['name']: t for t in self.tables}

    def u32(self, o):
        return struct.unpack(self.E + 'I', self.d[o:o + 4])[0]

    def put32(self, o, v):
        self.d[o:o + 4] = struct.pack(self.E + 'I', v)

    def get(self, table, field, row):
        t = self.by_name[table]
        off, width = t['fields'][field]
        rec = t['records'] + row * t['reclen']
        v = int.from_bytes(self.d[rec:rec + t['reclen']], 'big')
        return (v >> (t['reclen'] * 8 - off - width)) & ((1 << width) - 1)

    def set(self, table, field, row, value):
        t = self.by_name[table]
        off, width = t['fields'][field]
        if not 0 <= value < (1 << width):
            raise ValueError(f'{table}.{field}: {value} не влезает в {width} бит')
        rec = t['records'] + row * t['reclen']
        total = t['reclen'] * 8
        v = int.from_bytes(self.d[rec:rec + t['reclen']], 'big')
        shift = total - off - width
        v = (v & ~(((1 << width) - 1) << shift)) | (value << shift)
        self.d[rec:rec + t['reclen']] = v.to_bytes(t['reclen'], 'big')

    def get_string(self, table, field, row):
        """Строка фиксированной длины в записи (kind 0, UTF-8): байты до первого нуля."""
        t = self.by_name[table]
        off, width = t['fields'][field]
        start = t['records'] + row * t['reclen'] + off // 8
        return bytes(self.d[start:start + width // 8]).split(b'\0', 1)[0].decode('utf-8', errors='replace')

    def set_string(self, table, field, row, text):
        t = self.by_name[table]
        off, width = t['fields'][field]
        raw = text.encode('utf-8')
        if off % 8 or width % 8 or len(raw) >= width // 8:
            raise ValueError(f'{table}.{field}: строка «{text}» не влезает в {width // 8 - 1} байт')
        start = t['records'] + row * t['reclen'] + off // 8
        self.d[start:start + width // 8] = raw + bytes(width // 8 - len(raw))

    def column(self, table, field):
        return [self.get(table, field, r) for r in range(self.by_name[table]['rows'])]

    def record(self, table, row):
        t = self.by_name[table]
        start = t['records'] + row * t['reclen']
        return bytes(self.d[start:start + t['reclen']])

    def put_record(self, table, row, raw):
        t = self.by_name[table]
        if len(raw) != t['reclen']:
            raise ValueError(f'{table}: запись {len(raw)} байт вместо {t["reclen"]}')
        start = t['records'] + row * t['reclen']
        self.d[start:start + t['reclen']] = raw

    def resize(self, table, rows):
        """Число записей таблицы (max = current = rows): нули дописываются в конец или
        записи обрезаются с конца. Каталог следующих таблиц и db_size (@0x08) сдвигаются,
        структура перечитывается; CRC — потом fix(). Только простые таблицы (тип 2/6,
        без индексов): у них данные — ровно reclen · max_records."""
        t = self.by_name[table]
        blk = t['block']
        maxr = struct.unpack(self.E + 'H', self.d[blk + 0x14:blk + 0x16])[0]
        if self.u32(blk + 4) not in (2, 6) or self.d[blk + 0x1D]:
            raise ValueError(f'{table}: размер меняется только у простых таблиц без индексов')
        if not 0 <= rows <= 0xFFFF:
            raise ValueError(f'{table}: {rows} записей не влезает в u16')
        end = t['records'] + t['reclen'] * maxr
        delta = t['reclen'] * (rows - maxr)
        if delta >= 0:
            self.d[end:end] = bytes(delta)
        else:
            del self.d[end + delta:end]
        self.d[blk + 0x14:blk + 0x18] = struct.pack(self.E + 'HH', rows, rows)
        n = self.u32(0x10)
        for i in range(n):
            slot = 0x1C + 8 * i
            if 0x18 + 8 * n + self.u32(slot) > blk:
                self.put32(slot, self.u32(slot) + delta)
        self.put32(0x08, self.u32(0x08) + delta)
        self.__init__(bytes(self.d), self.meta)

    def widen(self, table, fields, width):
        """Поля `fields` таблицы — шириной `width` бит: переезжают в конец записи (старые биты
        остаются мёртвыми), запись удлиняется до кратного 4 байт. Значения сохраняются (сырые).
        Заголовок (+0x08 длина записи, +0x0C бит − 1, дескрипторы полей), сдвиг следующих таблиц
        и db_size — здесь; CRC — потом fix(). Только простые таблицы (тип 2/6, без индексов)."""
        t = self.by_name[table]
        blk, old_len = t['block'], t['reclen']
        if self.u32(blk + 4) not in (2, 6) or self.d[blk + 0x1D]:
            raise ValueError(f'{table}: только простые таблицы без индексов')
        maxr = struct.unpack(self.E + 'H', self.d[blk + 0x14:blk + 0x16])[0]
        values = {f: [self.get(table, f, r) for r in range(maxr)] for f in fields}
        used = max(o + w for o, w in t['fields'].values())
        place = {}
        for f in fields:
            place[f] = used
            used += width
        new_len = (used + 31) // 32 * 4
        nf = self.d[blk + 0x1C]
        for j in range(nf):
            fd = blk + 0x28 + 16 * j
            fid = bytes(self.d[fd + 8:fd + 12]).decode('latin1')
            name = self.meta.get(t['id'], (t['id'], {}))[1].get(fid, (fid,))[0]
            if name in place:
                self.put32(fd + 4, place[name])
                self.put32(fd + 12, width)
        # записи: старые байты + нули до новой длины
        rec0 = t['records']
        old = bytes(self.d[rec0:rec0 + old_len * maxr])
        new = bytearray()
        for r in range(maxr):
            new += old[r * old_len:(r + 1) * old_len] + bytes(new_len - old_len)
        self.d[rec0:rec0 + old_len * maxr] = new
        delta = (new_len - old_len) * maxr
        self.put32(blk + 0x08, new_len)
        self.put32(blk + 0x0C, new_len * 8 - 1)
        n = self.u32(0x10)
        for i in range(n):
            slot = 0x1C + 8 * i
            if 0x18 + 8 * n + self.u32(slot) > blk:
                self.put32(slot, self.u32(slot) + delta)
        self.put32(0x08, self.u32(0x08) + delta)
        self.__init__(bytes(self.d), self.meta)
        for f in fields:
            for r, v in enumerate(values[f]):
                self.set(table, f, r, v)

    def _layout(self):
        order = sorted(self.tables, key=lambda t: t['block'])
        ends = [t['block'] for t in order[1:]] + [len(self.d) - 4]
        return order, ends

    def crcs(self):
        """Ожидаемые значения всех CRC для текущего содержимого: [(смещение, crc)]."""
        out = []
        order, ends = self._layout()
        n = len(self.tables)
        prev_body = self.d[0x18:0x18 + 8 * n]
        for t, end in zip(order, ends):
            out.append((t['block'], crc32_mpeg2(prev_body)))
            out.append((t['block'] + 0x24, crc32_mpeg2(self.d[t['block'] + 4:t['block'] + 0x24])))
            prev_body = self.d[t['block'] + 0x28:end]
        out.append((len(self.d) - 4, crc32_mpeg2(prev_body)))
        return out

    def verify(self):
        bad = [(o, self.u32(o), c) for o, c in self.crcs() if self.u32(o) != c]
        if self.u32(0x14) != crc32_mpeg2(self.d[0:0x14]):
            bad.append((0x14, self.u32(0x14), crc32_mpeg2(self.d[0:0x14])))
        return bad

    def fix(self):
        for o, c in self.crcs():
            self.put32(o, c)
        self.put32(0x14, crc32_mpeg2(self.d[0:0x14]))

class SaveFile:
    """Внутренний файл сейва: заголовок 0x2C байт + база + хвост (у франшизы)."""
    def __init__(self, data, meta):
        data = bytearray(data)
        if data[:2] == b'DB':
            self.header, self.tail = None, b''
            self.db = Tdb(data, meta)
            return
        size = struct.unpack('>I', data[0x24:0x28])[0]
        self.header = data[:CONTAINER_HEADER]
        self.db = Tdb(data[CONTAINER_HEADER:CONTAINER_HEADER + size], meta)
        self.tail = bytes(data[CONTAINER_HEADER + size:])

    def _sums(self, out):
        db_end = CONTAINER_HEADER + len(self.db.d)
        return crc32_bzip2(out[0x2C:db_end]), crc32_ieee(out[0x1C:])

    def bytes(self, fix=True):
        if fix:
            self.db.fix()
        if self.header is None:
            return bytes(self.db.d)
        out = bytearray(self.header) + self.db.d + self.tail
        out[0x28:0x2C] = struct.pack('>I', self._sums(out)[0])
        out[0x10:0x14] = struct.pack('>I', self._sums(out)[1])
        return bytes(out)

    def verify(self):
        bad = [f'база @0x{o:X}: записано {a:08X}, должно {b:08X}' for o, a, b in self.db.verify()]
        if self.header is not None:
            full = bytes(self.header) + bytes(self.db.d) + self.tail
            b_sum, a_sum = self._sums(full)
            if struct.unpack('>I', full[0x28:0x2C])[0] != b_sum:
                bad.append('обёртка: checksum_b не сходится')
            if struct.unpack('>I', full[0x10:0x14])[0] != a_sum:
                bad.append('обёртка: checksum_a не сходится')
        return bad

def states(db):
    t = 'leaguestates'
    rows = zip(db.column(t, 'type'), db.column(t, 'key'), db.column(t, 'value'), db.column(t, 'tier'))
    return [(i, ty, k, v, tier) for i, (ty, k, v, tier) in enumerate(rows)]

def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('cmd', choices=['verify', 'states', 'setstate', 'set'])
    ap.add_argument('file')
    ap.add_argument('args', nargs='*')
    ap.add_argument('--meta', default=DEFAULT_META)
    a = ap.parse_args()
    s = SaveFile(open(a.file, 'rb').read(), load_meta(a.meta))
    if a.cmd == 'verify':
        bad = s.verify()
        kind = bytes(s.header[:16]).rstrip(b'\0').decode('latin1') if s.header is not None else ''
        print('\n'.join(bad) if bad else f'OK: все CRC сходятся ({len(s.db.tables)} таблиц'
              + (f', обёртка {kind}, хвост {len(s.tail)} байт)' if kind else ')'))
        sys.exit(1 if bad else 0)
    if a.cmd == 'states':
        for i, ty, k, v, tier in states(s.db):
            print(f'{i:4} type {ty:3} key {k:4} tier {tier}  value {v}')
        return
    out, rest = a.args[0], a.args[1:]
    if a.cmd == 'setstate':
        if len(rest) % 3:
            ap.error('нужны тройки TYPE KEY VALUE')
        rows = {(ty, k): i for i, ty, k, v, tier in states(s.db)}
        for ty, k, v in zip(*[iter(map(int, rest))] * 3):
            if (ty, k) not in rows:
                sys.exit(f'нет строки type {ty} key {k}')
            s.db.set('leaguestates', 'value', rows[(ty, k)], v)
    else:
        table, field, row, value = rest
        s.db.set(table, field, int(row), int(value))
    open(out, 'wb').write(s.bytes())
    print(f'записано -> {out}')

if __name__ == '__main__':
    main()
