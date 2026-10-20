"""База EA TDB v6 и сейв RosterFile (NHL 12/13, NHL Legacy — ZlibV4): чтение, запись полей, пересчёт CRC.

    python tdb.py verify  FILE                          # все CRC базы и обёртки сейва
    python tdb.py live    FILE [TABLE …]                # записи таблиц: max, current, удалённые, живые
    python tdb.py states  FILE                          # leaguestates: type/key -> value
    python tdb.py setstate FILE OUT TYPE KEY VALUE [TYPE KEY VALUE …]
    python tdb.py set     FILE OUT TABLE FIELD ROW VALUE
    python tdb.py tables  FILE                          # таблицы: имя, id, живых записей, полей
    python tdb.py dump    FILE TABLE [--fields a,b] [--where f=v|f~regex|f!=v …] [--limit N] [--raw] [--csv OUT]
                                                        # записи таблицы (значения — с rangelow схемы; --raw — как в файле)
    python tdb.py diff    A B [--tables t1,t2] [--key ПОЛЕ] [--limit N] [--raw]
                                                        # разница двух баз/сейвов: записи по ключу (index, game_id …)

FILE — `.db` или внутренний файл сейва (`RosterFile`, `Dynasty`…: заголовок 0x2C байт,
база длиной u32@0x24, у франшизы после базы ещё хвост своих данных). Схема полей —
`nhlng-meta.xml` (по умолчанию из ref/nhl-modding-studio, анкер NHL 13 для Xbox 360).

Живые записи. Заголовок таблицы: +0x14 max (мест), +0x16 current (занято с начала, вместе с удалёнными),
+0x18 — число удалённых, +0x1A — голова списка свободных (0xFFFF — пусто), всё u16. У удалённой записи
первые 16 бит — номер следующей свободной; они накрывают поля начала записи (у leaguerostertable — team,
биты 4…10), остальные поля — от прежней записи. Записи — строки [0, current) без удалённых (`live_rows`);
[current, max) — запас: в сейвах игры там байты 0xDB или остатки прежних записей (франшиза в межсезонье).
`rows` таблиц alloc 2/6 = max (физические места: get/set по номеру, resize, widen); перебирать таблицы сейва
надо по `live_rows`, иначе считаются и фантомы. У баз игр и всех наших баз max = current и удалённых нет —
там `live_rows` = range(rows).

Суммы (nhl-modding-studio, docs/formats/tdb-v6-format-spec.md §2):
- внутри базы — CRC-32/MPEG-2: заголовок [0..0x14] → 0x14; у каждой таблицы prior_crc
  (+0) — тело предыдущей таблицы (у первой — каталог), header_crc (+0x24) — [+4..+0x24];
  последние 4 байта — тело последней таблицы. Тело таблицы — от +0x28 до начала
  следующей (у последней — до EOF−4). Пересчёт: prior_crc → header_crc → EOF → заголовок.
- обёртка сейва — checksum_b (CRC-32/BZIP2 по базе [0x2C..0x2C+размер]) → 0x28, затем
  checksum_a (CRC-32/IEEE по [0x1C..конец файла], с хвостом) → 0x10, оба big-endian.
  Для `Dynasty` NHL 13 проверено на своих сейвах; у `RosterFile` хвоста нет.
- сейв NHL Legacy (ZlibV4: база сжата zlib с 0x30) — класс ZlibV4 ниже; читается и пишется так же,
  схема — `--meta` с nhlng-meta.xml; без него — схема Legacy из распакованной игры (tools/gameprofile.py),
  иначе анкер NHL 13 из ref/ (не в git).
"""
import argparse, os, struct, sys, zlib
from tdb_read import load_meta

DEFAULT_META = os.path.join(os.path.dirname(__file__), '..', 'ref', 'nhl-modding-studio', 'anchors',
                            'xbox360', 'nhl13', 'databases', 'nhlng-meta.xml')
CONTAINER_HEADER = 0x2C


def default_meta():
    """Схема без --meta: NHL Legacy из распакованной игры (gameprofile), иначе анкер NHL 13 в ref/ (не в git)."""
    try:
        import gameprofile
        p = gameprofile.get('legacy').meta
        if p and os.path.isfile(p):
            return p
    except Exception:                                       # noqa: BLE001
        pass
    if os.path.isfile(DEFAULT_META):
        return DEFAULT_META
    sys.exit('нет схемы базы: укажите --meta nhlng-meta.xml (cacheboot/db распакованной игры, tools/big.py disc)')

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
            fields, kinds = {}, {}
            for j in range(nf):
                fd = h + 0x28 + 16 * j
                fid = bytes(self.d[fd + 8:fd + 12]).decode('latin1')
                fields[fid] = (self.u32(fd + 4), self.u32(fd + 12))
                kinds[fid] = self.u32(fd)                       # 0 — строка, 3 — целое (в базах NHL)
            name, fmeta = meta.get(tid, (tid, {}))
            fname = lambda fid: fmeta.get(fid, (fid,))[0]       # noqa: E731
            byname = {fname(fid): v for fid, v in fields.items()}
            rows = maxr if alloc in (2, 6) else curr
            self.tables.append(dict(id=tid, name=name, block=block, reclen=reclen, rows=rows,
                                    records=h + 0x28 + 16 * nf, fields=byname,
                                    kinds={fname(fid): k for fid, k in kinds.items()},
                                    lows={fname(fid): fmeta[fid][1] for fid in fields if fid in fmeta and
                                          len(fmeta[fid]) > 1}))
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

    def value(self, table, field, row, raw=False):
        """Значение поля: строка — текстом, целое — с rangelow схемы (как его видит игра); raw — как в файле."""
        t = self.by_name[table]
        if t['kinds'].get(field) == 0:
            return self.get_string(table, field, row)
        v = self.get(table, field, row)
        return v if raw else v + t['lows'].get(field, 0)

    def set_string(self, table, field, row, text):
        t = self.by_name[table]
        off, width = t['fields'][field]
        raw = text.encode('utf-8')
        if off % 8 or width % 8 or len(raw) >= width // 8:
            raise ValueError(f'{table}.{field}: строка «{text}» не влезает в {width // 8 - 1} байт')
        start = t['records'] + row * t['reclen'] + off // 8
        self.d[start:start + width // 8] = raw + bytes(width // 8 - len(raw))

    def counts(self, table):
        """Счётчики заголовка таблицы: (max, current, удалённых, голова списка свободных)."""
        b = self.by_name[table]['block']
        return struct.unpack(self.E + 'HHHH', self.d[b + 0x14:b + 0x1C])

    def deleted(self, table):
        """Номера удалённых записей таблицы (список свободных) в порядке цепочки: в заголовке +0x18 (u16) —
        их число, +0x1A — голова списка; у удалённой записи первые 16 бит — номер следующей (0xFFFF — конец),
        они перекрывают поля из начала записи (у leaguerostertable — team). В базах игр их нет, в сейвах
        франшизы есть: считая по таблицам сейва, эти строки надо пропускать (get и column их не отличают;
        перебирать — по live_rows). Цепочка проверяется: звеньев столько, сколько в счётчике, без повторов,
        номера < max; иначе ValueError (такой сейв читать как обычно нельзя)."""
        t = self.by_name[table]
        maxr, cur, n, r = self.counts(table)
        out, seen = [], set()
        while r != 0xFFFF:
            if r >= maxr or r in seen or len(out) == n:
                why = (f'номер {r} за max {maxr}' if r >= maxr else f'цикл на записи {r}' if r in seen
                       else f'звеньев больше счётчика {n}')
                raise ValueError(f'{table}: список удалённых записей испорчен — {why}')
            seen.add(r)
            out.append(r)
            s = t['records'] + r * t['reclen']
            r = struct.unpack(self.E + 'H', self.d[s:s + 2])[0]
        if len(out) != n:
            raise ValueError(f'{table}: в списке удалённых {len(out)} записей, в счётчике {n}')
        return out

    def live_rows(self, table):
        """Номера живых записей по возрастанию: [0, current) без удалённых. Индексы и подсчёты по сейву —
        только по ним; у баз игр и наших баз это все строки (range(rows))."""
        maxr, cur, n, head = self.counts(table)
        if not n:
            return list(range(cur))
        dead = set(self.deleted(table))
        return [r for r in range(cur) if r not in dead]

    def dead_rows(self, table):
        """Строки range(rows), которые не записи: удалённые и запас [current, max)."""
        live = set(self.live_rows(table))
        return [r for r in range(self.by_name[table]['rows']) if r not in live]

    def is_live(self, table, row):
        """Строка — живая запись (для одной строки; в цикле — live_rows один раз)."""
        maxr, cur, n, head = self.counts(table)
        return 0 <= row < cur and (not n or row not in self.deleted(table))

    def column(self, table, field, live_only=False):
        """Значения поля по строкам range(rows); live_only — только живых записей (по live_rows, номера строк
        тогда не совпадают с позицией в списке)."""
        rows = self.live_rows(table) if live_only else range(self.by_name[table]['rows'])
        return [self.get(table, field, r) for r in rows]

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
        и db_size — здесь; CRC — потом fix(). Только простые таблицы (тип 2/6, без индексов).
        Последний бит записи (reclen·8 − 1, он же +0x0C) полем не занимается: движок держит в нём флаг
        «запись свободна» (у живых 0, у удалённых 1 — legacy-port, все 134 таблицы сейва BE A GM Legacy; у баз
        EA этот бит свободен во всех таблицах). Если поля доходят до конца записи, запись растёт ещё на 4 байта
        (было: Legacy leaguerookiedata.draftteam 6 бит в битах 58…63 при reclen 8 — младший бит номера
        клуба становился флагом, и новички клубов с чётным номером для игры пропадали, 10.10.2026).
        `fields` пусто — только этот запас (починка уже собранной базы)."""
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
        new_len = max(old_len, (used + 1 + 31) // 32 * 4)    # +1: последний бит — флаг движка «свободна»
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

def is_zlibv4(data):
    """Обёртка ZlibV4 (NHL 14/15/Legacy): база не с 0x2C, а с 0x30 — поток zlib (78 xx)."""
    return len(data) > 0x32 and data[:2] != b'DB' and data[0x2C:0x2E] != b'DB' and data[0x30] == 0x78 \
        and (data[0x30] * 256 + data[0x31]) % 31 == 0


class SaveFile:
    """Внутренний файл сейва: заголовок 0x2C байт + база + хвост (у франшизы) — NHL 12/13;
    у NHL Legacy (ZlibV4) база сжата, устройство — в ZlibV4 ниже."""
    def __init__(self, data, meta):
        data = bytearray(data)
        self.zlib = None
        if data[:2] == b'DB':
            self.header, self.tail = None, b''
            self.db = Tdb(data, meta)
            return
        if is_zlibv4(data):
            self.zlib = ZlibV4(data)
            self.header, self.tail = self.zlib.header, self.zlib.tail
            self.db = Tdb(self.zlib.inflated[:self.zlib.db_size], meta)
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
        if self.zlib is not None:
            return self.zlib.pack(bytes(self.db.d))
        if self.header is None:
            return bytes(self.db.d)
        out = bytearray(self.header) + self.db.d + self.tail
        out[0x28:0x2C] = struct.pack('>I', self._sums(out)[0])
        out[0x10:0x14] = struct.pack('>I', self._sums(out)[1])
        return bytes(out)

    def verify(self):
        bad = [f'база @0x{o:X}: записано {a:08X}, должно {b:08X}' for o, a, b in self.db.verify()]
        if self.zlib is not None:
            bad += self.zlib.verify()
        elif self.header is not None:
            full = bytes(self.header) + bytes(self.db.d) + self.tail
            b_sum, a_sum = self._sums(full)
            if struct.unpack('>I', full[0x28:0x2C])[0] != b_sum:
                bad.append('обёртка: checksum_b не сходится')
            if struct.unpack('>I', full[0x10:0x14])[0] != a_sum:
                bad.append('обёртка: checksum_a не сходится')
        return bad


class ZlibV4:
    """Сейв NHL Legacy (и NHL 14/15): заголовок 0x2C байт как у NHL 13, дальше сжатая область.

    Сверено на анкерах nhl-modding-studio (ROSTER, DYNASTY, SEASON, BEAPRO Legacy для Xbox 360):
    - 0x10 checksum_a — CRC-32/IEEE по [0x1C..конец файла] (с хвостом), big-endian;
    - 0x14 версия: 4 — составы, 5 — франшиза, сезон, «Стань профи»;
    - 0x24 размер области (BE): область [0x2C, 0x2C + размер) — длина потока (u32 **LE**), с 0x30
      поток zlib, дальше нули; у составов размер = длине разжатого, у франшизы — ровно половине;
    - 0x28 checksum_b — CRC-32/BZIP2 по области [0x2C, 0x2C + размер), big-endian;
    - разжатое — база TDB (длина — db_size @0x08 базы) + 4 байта 0xDBDBDBDB;
    - после области — хвост своих данных (у франшизы 160–1300 КБ, у составов его нет).
    Запись: если база не изменилась — прежний поток байт в байт; иначе zlib уровня 6 (поток zlib-ng
    Python другой длины, чем у EA, игра разжимает любой), размер области — с тем же отношением к
    длине разжатого, что был (проверено в игре — docs/legacy-data.md)."""

    def __init__(self, data):
        data = bytes(data)
        self.header = bytearray(data[:CONTAINER_HEADER])
        self.region = struct.unpack('>I', data[0x24:0x28])[0]
        self.csize = struct.unpack('<I', data[0x2C:0x30])[0]
        if not 4 < self.csize <= self.region - 4 or CONTAINER_HEADER + self.region > len(data):
            raise ValueError(f'ZlibV4: длина потока {self.csize} или области {self.region} не сходится')
        self.stream = data[0x30:0x30 + self.csize]
        self.inflated = zlib.decompress(self.stream)
        if self.inflated[:2] != b'DB':
            raise ValueError('ZlibV4: внутри не база TDB')
        E = '>' if self.inflated[4] == 1 else '<'
        self.db_size = struct.unpack(E + 'I', self.inflated[8:12])[0]
        self.trailer = self.inflated[self.db_size:]
        self.pad = data[0x30 + self.csize:CONTAINER_HEADER + self.region]
        self.tail = data[CONTAINER_HEADER + self.region:]
        self.original = data
        self.ratio = (len(self.inflated), self.region)

    @property
    def version(self):
        return struct.unpack('>I', self.header[0x14:0x18])[0]

    def pack(self, db, level=6):
        inflated = bytes(db) + self.trailer
        if inflated == self.inflated:
            stream, region = self.stream, self.region
        else:
            stream = zlib.compress(inflated, level)
            n, r = self.ratio
            region = (len(inflated) * r + n - 1) // n
            region = max(region, 4 + len(stream))
        body = struct.pack('<I', len(stream)) + stream
        out = bytearray(self.header) + body + bytes(region - len(body)) + self.tail
        out[0x24:0x28] = struct.pack('>I', region)
        out[0x28:0x2C] = struct.pack('>I', crc32_bzip2(out[CONTAINER_HEADER:CONTAINER_HEADER + region]))
        out[0x10:0x14] = struct.pack('>I', crc32_ieee(out[0x1C:]))
        return bytes(out)

    def verify(self):
        d, bad = self.original, []
        if struct.unpack('>I', d[0x28:0x2C])[0] != crc32_bzip2(d[CONTAINER_HEADER:CONTAINER_HEADER + self.region]):
            bad.append('обёртка ZlibV4: checksum_b не сходится')
        if struct.unpack('>I', d[0x10:0x14])[0] != crc32_ieee(d[0x1C:]):
            bad.append('обёртка ZlibV4: checksum_a не сходится')
        if any(self.pad):
            bad.append('обёртка ZlibV4: после потока zlib в области не нули')
        if self.trailer != b'\xDB' * 4:
            bad.append(f'обёртка ZlibV4: после базы {self.trailer[:8].hex()} вместо DBDBDBDB')
        return bad

def states(db):
    """leaguestates: [(строка, type, key, value, tier)] — только живые записи (в сейве франшизы за current —
    запас 0xDB и остатки прежних состояний, их type/key игра не видит)."""
    t = 'leaguestates'
    if t not in db.by_name:
        sys.exit('нет таблицы leaguestates: она есть в сейвах франшизы (DYNASTY …), а не в базе и не в ROSTER')
    g = lambda f, r: db.get(t, f, r)
    return [(r, g('type', r), g('key', r), g('value', r), g('tier', r)) for r in db.live_rows(t)]

def live_report(db, tables=None):
    """Строки отчёта `live`: таблицы, где не все строки range(rows) — живые записи (или перечисленные)."""
    out = [f'{"таблица":34} {"alloc":>5} {"max":>6} {"current":>7} {"удалён.":>7} {"живых":>6}']
    total = dict(deleted=0, spare=0)
    for t in db.tables:
        name = t['name']
        maxr, cur, n, head = db.counts(name)
        live = len(db.live_rows(name))
        total['deleted'] += n
        total['spare'] += t['rows'] - cur
        if (tables and name in tables) or (not tables and live != t['rows']):
            out.append(f'{name:34} {db.u32(t["block"] + 4):5} {maxr:6} {cur:7} {n:7} {live:6}')
    out.append(f'итого: удалённых записей {total["deleted"]}, строк запаса за current {total["spare"]} '
               f'(у alloc 2/6 rows = max)')
    return out

KEY_FIELDS = ('index', 'game_id', 'key', 'teamid', 'playerid', 'id')


def _match(where):
    """--where f=v | f!=v | f~regex -> предикат по значениям строки."""
    import re
    tests = []
    for w in where or ():
        m = re.match(r'^([^=!~]+)(!=|=|~)(.*)$', w)
        if not m:
            sys.exit(f'--where: «{w}» — нужно поле=значение, поле!=значение или поле~regex')
        f, op, v = m.groups()
        tests.append((f, op, re.compile(v) if op == '~' else v))
    return tests


def dump(db, table, fields=None, where=None, limit=0, raw=False):
    """[(строка, {поле: значение})] живых записей таблицы с условиями --where."""
    if table not in db.by_name:
        sys.exit(f'нет таблицы {table} (python tdb.py tables FILE)')
    t = db.by_name[table]
    names = fields or sorted(t['fields'])
    bad = [f for f in names if f not in t['fields']]
    tests = _match(where)
    bad += [f for f, _, _ in tests if f not in t['fields']]
    if bad:
        sys.exit(f'{table}: нет полей {sorted(set(bad))}; есть: {", ".join(sorted(t["fields"]))}')
    out = []
    for r in db.live_rows(table):
        ok = True
        for f, op, v in tests:
            x = str(db.value(table, f, r, raw))
            ok = (x == v) if op == '=' else (x != v) if op == '!=' else bool(v.search(x))
            if not ok:
                break
        if ok:
            out.append((r, {f: db.value(table, f, r, raw) for f in names}))
            if limit and len(out) >= limit:
                break
    return names, out


def _keyed(db, table, key, fields, raw):
    """{ключ: {поле: значение}} живых записей; ключ — значение поля key (повторы — с номером), иначе номер строки."""
    out, seen = {}, {}
    for r in db.live_rows(table):
        vals = {f: db.value(table, f, r, raw) for f in fields}
        k = vals.get(key, r) if key else r
        n = seen.get(k, 0)
        seen[k] = n + 1
        out[k if n == 0 else (k, n)] = vals
    return out


def diff(a, b, tables=None, key=None, limit=20, raw=False):
    """Строки отчёта: таблицы, где различаются записи (добавлены, убраны, изменены поля) — по ключу."""
    lines = []
    for name in sorted(set(a.by_name) | set(b.by_name)):
        if tables and name not in tables:
            continue
        if name not in a.by_name or name not in b.by_name:
            lines.append(f'{name}: только в {"B" if name not in a.by_name else "A"}')
            continue
        fields = sorted(set(a.by_name[name]['fields']) & set(b.by_name[name]['fields']))
        k = key if key in fields else next((f for f in KEY_FIELDS if f in fields), None)
        ra, rb = _keyed(a, name, k, fields, raw), _keyed(b, name, k, fields, raw)
        added, removed = [x for x in rb if x not in ra], [x for x in ra if x not in rb]
        changed = []
        for x in ra:
            if x in rb and ra[x] != rb[x]:
                changed.append((x, [(f, ra[x][f], rb[x][f]) for f in fields if ra[x][f] != rb[x][f]]))
        extra = sorted(set(a.by_name[name]['fields']) ^ set(b.by_name[name]['fields']))
        if not (added or removed or changed or extra):
            continue
        lines.append(f'{name} (ключ {k or "номер строки"}): записей A {len(ra)}, B {len(rb)}; добавлено {len(added)}, '
                     f'убрано {len(removed)}, изменено {len(changed)}' + (f'; поля только в одной: {extra}' if extra
                                                                         else ''))
        for x, ch in changed[:limit]:
            lines.append(f'  {k or "строка"} {x}: ' + ', '.join(f'{f} {u!r} → {v!r}' for f, u, v in ch[:8]) +
                         (' …' if len(ch) > 8 else ''))
        if len(changed) > limit:
            lines.append(f'  … ещё {len(changed) - limit}')
        for lab, xs in (('добавлено', added), ('убрано', removed)):
            if xs:
                lines.append(f'  {lab}: ' + ', '.join(map(str, xs[:limit])) + (' …' if len(xs) > limit else ''))
    return lines or ['различий нет']


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('cmd', choices=['verify', 'live', 'states', 'setstate', 'set', 'tables', 'dump', 'diff'])
    ap.add_argument('file')
    ap.add_argument('args', nargs='*')
    ap.add_argument('--fields', default=None, help='dump: поля через запятую (по умолчанию — все)')
    ap.add_argument('--where', action='append', default=None, help='dump: условие поле=значение / != / ~regex')
    ap.add_argument('--limit', type=int, default=None, help='dump: сколько записей (0 — все); diff: строк на таблицу')
    ap.add_argument('--raw', action='store_true', help='значения как в файле (без rangelow схемы)')
    ap.add_argument('--csv', default=None, help='dump: записать в CSV')
    ap.add_argument('--tables', default=None, help='diff: только эти таблицы (через запятую)')
    ap.add_argument('--key', default=None, help=f'diff: поле-ключ записей (по умолчанию — первое из {KEY_FIELDS})')
    ap.add_argument('--meta', default=None,
                    help='nhlng-meta.xml игры (по умолчанию — схема NHL Legacy из распакованной игры, tools/gameprofile.py; '
                         'анкер NHL 13 из ref/, если он есть)')
    a = ap.parse_args()
    meta = load_meta(a.meta or default_meta())
    s = SaveFile(open(a.file, 'rb').read(), meta)
    if a.cmd == 'tables':
        print(f'{"таблица":36} {"id":5} {"живых":>6} {"полей":>5}')
        for t in sorted(s.db.tables, key=lambda t: t['name']):
            print(f'{t["name"]:36} {t["id"]:5} {len(s.db.live_rows(t["name"])):6} {len(t["fields"]):5}')
        return
    if a.cmd == 'dump':
        if not a.args:
            ap.error('dump FILE TABLE')
        names, rows = dump(s.db, a.args[0], a.fields.split(',') if a.fields else None, a.where,
                           a.limit or 0, a.raw)
        if a.csv:
            import csv
            with open(a.csv, 'w', newline='', encoding='utf-8') as f:
                w = csv.writer(f)
                w.writerow(['row'] + names)
                for r, v in rows:
                    w.writerow([r] + [v[n] for n in names])
            print(f'{len(rows)} записей → {a.csv}')
        else:
            print('\t'.join(['row'] + names))
            for r, v in rows:
                print('\t'.join([str(r)] + [str(v[n]) for n in names]))
            print(f'записей: {len(rows)}', file=sys.stderr)
        return
    if a.cmd == 'diff':
        if not a.args:
            ap.error('diff A B')
        b = SaveFile(open(a.args[0], 'rb').read(), meta)
        print('\n'.join(diff(s.db, b.db, a.tables.split(',') if a.tables else None, a.key,
                             20 if a.limit is None else a.limit, a.raw)))
        return
    if a.cmd == 'verify':
        bad = s.verify()
        kind = bytes(s.header[:16]).rstrip(b'\0').decode('latin1') if s.header is not None else ''
        z = f' ZlibV4 v{s.zlib.version}, поток {s.zlib.csize} байт' if s.zlib is not None else ''
        print('\n'.join(bad) if bad else f'OK: все CRC сходятся ({len(s.db.tables)} таблиц'
              + (f', обёртка {kind}{z}, хвост {len(s.tail)} байт)' if kind else ')'))
        sys.exit(1 if bad else 0)
    if a.cmd == 'live':
        print('\n'.join(live_report(s.db, set(a.args))))
        return
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
        if not s.db.is_live(table, int(row)):
            maxr, cur, n, head = s.db.counts(table)
            sys.exit(f'{table}: строка {row} — не запись (current {cur}, удалённых {n}): игра её не читает')
        s.db.set(table, field, int(row), int(value))
    open(out, 'wb').write(s.bytes())
    print(f'записано -> {out}')

if __name__ == '__main__':
    main()
