"""Строки локализации EA (nhl_<язык>.db, таблица LanguageStrings): выгрузка, правка, проверка.

    python locdb.py dump  DB META [FILTER]          # stringid<TAB>текст (FILTER — подстрока)
    python locdb.py set   DB META OUT KEY=ТЕКСТ…    # правка по ключу, CRC пересчитываются
    python locdb.py put   DB META OUT KEY=ТЕКСТ…    # новая строка в конец пула (любой длины), ключ — на неё
                                                   # (нет такого ключа — запись добавляется)
    python locdb.py check DB META                  # нет ли двух записей с одним hashid (код 1 — есть)

Таблица типа 66: записи по 16 байт (stringid — varchar с 1-байтовой длиной,
sourcetext — с 2-байтовой, hashid), строки лежат в пуле за записями, сжатые
Хаффманом (nhl-modding-studio, tdb-v6-format-spec.md §3.1): в начале пула дерево —
обход в ширину по 2 байта [index, value] (index 0 — лист с байтом value), у
раскрытого узла правый потомок встаёт в очередь раньше левого; код: левый — 0,
правый — 1. Строка: длина в символах (BE) + биты от старшего.

Правка на месте: новый текст кодируется тем же деревом и пишется по старому
смещению, если влезает в прежний объём (иначе ошибка). Одна строка пула может
принадлежать нескольким ключам (дедупликация) — правка меняет их все, это выводится.
`put` дописывает строку в конец пула и переводит на неё только этот ключ: пул растёт,
в заголовке таблицы (+0x10) — занятый объём пула, файл (db_size @0x08) — на столько же
(область пула выровнена на 4). Нет ключа — `add`: имя ключа и текст в пул, запись (16 байт)
вставляется по порядку hashid — записи отсортированы по нему. hashid — тот
же CRC-32, что у имён таблиц базы (таблица 0x822C2398, у каждого байта снят бит 0x20,
начало 0). Текст — UTF-8 (® = C2 AE).

Ключ игра ищет по hashid: 82768FB8 (ключ строкой) → 826454A0 (хеш 826473A8) → 826454E0 →
запрос t3db 82638730 «hashid = X», без кэша. Регистр hashid не различает: TEAMLINE1_EAS и
Teamline1_EAS — для игры один ключ. Поэтому и здесь ключ ищется по hashid (set, put, add,
alias): `put Teamline1_EAS=…` меняет текст записи TEAMLINE1_EAS (имя записи прежнее), второй
записи с тем же hashid не появляется. Тот же hashid у ключа с другим именем (коллизия CRC,
не регистр) — ошибка. Индексов у таблицы нет (index_count 0, загрузчик их не строит), курсор
запроса (82643098) перебирает записи с начала: из записей с одним hashid игра видит первую,
остальные мертвы. `check` находит такие записи, hashid не от своего ключа и нарушенный порядок.
"""
import struct, sys
from collections import deque, defaultdict
from tdb import Tdb
from tdb_read import load_meta

MISSING = 0xFFFFFFFF  # у ключа нет строки (29 таких в nhl_eng_us.db)

_CRC = None

def key_hash(key):
    """hashid ключа: CRC-32 по таблице игры 0x822C2398 (как имена таблиц базы), у каждого
    байта снят бит 0x20, начальное значение 0 (сверено с записями nhl_eng_us.db)."""
    global _CRC
    if _CRC is None:
        _CRC = []
        for i in range(256):  # таблица 0x822C2398 — обычный отражённый CRC-32 (0xEDB88320)
            c = i
            for _ in range(8):
                c = (c >> 1) ^ 0xEDB88320 if c & 1 else c >> 1
            _CRC.append(c)
    h = 0
    for ch in key.encode('utf-8'):
        h = (h >> 8) ^ _CRC[(h ^ (ch & ~0x20)) & 0xFF]
    return h

def same_key(a, b):
    """Один ли это ключ для игры: hashid не различает байты, которые отличаются битом 0x20
    (регистр букв). Разные по этому правилу ключи с одним hashid — коллизия CRC."""
    return bytes(c & 0xDF for c in a.encode('utf-8')) == bytes(c & 0xDF for c in b.encode('utf-8'))

class LocDb:
    def __init__(self, data, meta):
        self.db = Tdb(data, meta)
        t = self.table = self.db.by_name['LanguageStrings']
        maxr = int.from_bytes(self.db.d[t['block'] + 0x14:t['block'] + 0x16], 'big')
        self.pool_start = t['records'] + t['reclen'] * maxr
        order = sorted(self.db.tables, key=lambda x: x['block'])
        i = order.index(t)
        self.pool_end = order[i + 1]['block'] if i + 1 < len(order) else len(self.db.d) - 4
        self.children, self.tree_size = self._parse_tree()
        self.codes = {}
        self._build_codes(0, '')

    def _byte(self, off):
        return self.db.d[self.pool_start + off]

    def _parse_tree(self):
        children, q, pos, next_id = {}, deque([0]), 0, 1
        while q:
            parent = q.popleft()
            li, lv, ri, rv = (self._byte(pos + k) for k in range(4))
            pos += 4
            kids = []
            for ix, val in ((li, lv), (ri, rv)):
                if ix == 0:
                    kids.append(('leaf', val))
                else:
                    kids.append(('node', next_id))
                    next_id += 1
            children[parent] = kids
            for kind, nid in (kids[1], kids[0]):
                if kind == 'node':
                    q.append(nid)
        return children, pos

    def _build_codes(self, node, prefix):
        for bit, (kind, v) in enumerate(self.children[node]):
            if kind == 'leaf':
                self.codes[v] = prefix + str(bit)
            else:
                self._build_codes(v, prefix + str(bit))

    def decode_at(self, off, prefix_len):
        n = self._byte(off) if prefix_len == 1 else (self._byte(off) << 8) | self._byte(off + 1)
        bitpos, out = (off + prefix_len) * 8, bytearray()
        while len(out) < n:
            node = 0
            while True:
                bit = (self._byte(bitpos >> 3) >> (7 - (bitpos & 7))) & 1
                bitpos += 1
                kind, v = self.children[node][bit]
                if kind == 'leaf':
                    out.append(v)
                    break
                node = v
        return bytes(out), (bitpos + 7) // 8 - off  # байты и занятый объём

    def _rec(self, r):
        return self.table['records'] + 16 * r

    def hash_at(self, r):
        return struct.unpack('>I', self.db.d[self._rec(r) + 8:self._rec(r) + 12])[0]

    def text_off_at(self, r):
        return struct.unpack('>I', self.db.d[self._rec(r) + 4:self._rec(r) + 8])[0]

    def key_at(self, r):
        sid_off = struct.unpack('>I', self.db.d[self._rec(r):self._rec(r) + 4])[0]
        return self.decode_at(sid_off, 1)[0].decode('utf-8', errors='replace')

    def rows(self):
        recs = self.table['records']
        for r in range(self.table['rows']):
            sid_off, txt_off = struct.unpack('>II', self.db.d[recs + r * 16:recs + r * 16 + 8])
            sid = self.decode_at(sid_off, 1)[0].decode('utf-8', errors='replace')
            yield r, sid, txt_off

    def text(self, txt_off):
        if txt_off == MISSING:
            return ''
        return self.decode_at(txt_off, 2)[0].decode('utf-8', errors='replace')

    def find_all(self, key):
        """Записи ключа key так, как их найдёт игра: по hashid, регистр не важен. Обычно одна или
        ни одной; больше — файл уже с дублями (check). Тот же hashid у ключа с другим именем
        (коллизия CRC) — KeyError: игра их не различает, правка задела бы чужую строку."""
        h = key_hash(key)
        found = [r for r in range(self.table['rows']) if self.hash_at(r) == h]
        for r in found:
            other = self.key_at(r)
            if not same_key(other, key):
                raise KeyError(f'у ключа {key} тот же hashid {h:08X}, что у {other} (коллизия CRC) — для игры это один ключ')
        return found

    def find(self, key):
        """Номер записи ключа (по hashid, как в игре) или None."""
        found = self.find_all(key)
        return found[0] if found else None

    def alias(self, dst_key, src_key):
        """Ключ dst_key показывает ту же строку пула, что src_key (меняется только указатель)."""
        found = {k: self.find_all(k) for k in (dst_key, src_key)}
        for k, rs in found.items():
            if not rs:
                raise KeyError(f'нет ключа {k}')
        src = self._rec(found[src_key][0]) + 4
        for r in found[dst_key]:
            dst = self._rec(r) + 4
            self.db.d[dst:dst + 4] = self.db.d[src:src + 4]

    def set_text(self, txt_off, text):
        if txt_off == MISSING:
            raise ValueError('у ключа нет строки (0xFFFFFFFF) — на место не записать')
        raw = text.encode('utf-8')
        missing = sorted({chr(b) for b in raw if b not in self.codes})
        if missing:
            raise ValueError(f'символов нет в дереве Хаффмана: {missing}')
        bits = ''.join(self.codes[b] for b in raw)
        encoded = len(raw).to_bytes(2, 'big') + int(bits.ljust((len(bits) + 7) // 8 * 8, '0'), 2).to_bytes((len(bits) + 7) // 8, 'big')
        old_size = self.decode_at(txt_off, 2)[1]
        if len(encoded) > old_size:
            raise ValueError(f'«{text}» не влезает: {len(encoded)} байт вместо {old_size}')
        start = self.pool_start + txt_off
        self.db.d[start:start + len(encoded)] = encoded

    def encode(self, text):
        raw = text.encode('utf-8')
        missing = sorted({chr(b) for b in raw if b not in self.codes})
        if missing:
            raise ValueError(f'символов нет в дереве Хаффмана: {missing}')
        bits = ''.join(self.codes[b] for b in raw)
        return len(raw).to_bytes(2, 'big') + int(bits.ljust((len(bits) + 7) // 8 * 8, '0') or '0', 2).to_bytes((len(bits) + 7) // 8, 'big')

    def _shift_after(self, delta):
        """Таблицы за этой — на delta байт дальше (каталог), файл (db_size @0x08) — длиннее."""
        blk, n = self.table['block'], self.db.u32(0x10)
        for i in range(n):
            slot = 0x1C + 8 * i
            if 0x18 + 8 * n + self.db.u32(slot) > blk:
                self.db.put32(slot, self.db.u32(slot) + delta)
        self.db.put32(0x08, self.db.u32(0x08) + delta)

    def _append(self, enc):
        """Байты в конец пула (растит область и файл); смещение строки в пуле."""
        blk = self.table['block']
        used = struct.unpack('>I', self.db.d[blk + 0x10:blk + 0x14])[0]
        region = self.pool_end - self.pool_start
        if used > region:
            raise ValueError(f'занято {used} байт пула при области {region}')
        new_used = used + len(enc)
        delta = (new_used + 3) // 4 * 4 - region
        if delta > 0:
            self.db.d[self.pool_end:self.pool_end] = bytes(delta)
            self._shift_after(delta)
            self.pool_end += delta
        self.db.d[self.pool_start + used:self.pool_start + used + len(enc)] = enc
        self.db.d[blk + 0x10:blk + 0x14] = struct.pack('>I', new_used)
        return used

    def _insert(self, key, text):
        """Новая запись: имя и текст в пул, запись (16 байт) — на своё место по hashid."""
        h = key_hash(key)
        n = self.table['rows']
        if any(self.hash_at(r) == h for r in range(n)):
            raise KeyError(f'hashid {h:08X} ключа {key} уже есть — вторую запись игра не увидит')
        raw_key = key.encode('utf-8')
        missing = sorted({chr(b) for b in raw_key if b not in self.codes})
        if missing:
            raise ValueError(f'символов ключа нет в дереве Хаффмана: {missing}')
        bits = ''.join(self.codes[b] for b in raw_key)
        enc_key = len(raw_key).to_bytes(1, 'big') + int(bits.ljust((len(bits) + 7) // 8 * 8, '0'), 2).to_bytes((len(bits) + 7) // 8, 'big')
        key_off = self._append(enc_key)
        txt_off = self._append(self.encode(text))
        recs, blk = self.table['records'], self.table['block']
        pos = next((r for r in range(n) if self.hash_at(r) > h), n)
        at = recs + 16 * pos
        self.db.d[at:at] = struct.pack('>IIII', key_off, txt_off, h, 0)
        self.db.d[blk + 0x14:blk + 0x18] = struct.pack('>HH', n + 1, n + 1)
        self._shift_after(16)
        self.pool_start += 16
        self.pool_end += 16
        self.table['rows'] = n + 1
        return pos

    def add(self, key, text):
        """Ключ с текстом; номер его записи. Ключа нет — новая запись (имя и текст в пул, запись —
        на своё место по hashid). Есть (по hashid, как ищет игра: регистр не важен) — замена
        текста, как put: имя записи прежнее, второй записи с тем же hashid не появляется."""
        found = self.find_all(key)
        if found:
            self.put(key, text)
            return found[0]
        return self._insert(key, text)

    def put(self, key, text):
        """Новая строка в конец пула; ключ key показывает её (другие ключи старой строки не меняются).
        Ключ ищется по hashid, как в игре (регистр не важен); нет такого — добавляется (add),
        возвращается None."""
        found = self.find_all(key)
        if not found:
            self._insert(key, text)
            return None
        used = self._append(self.encode(text))
        for r in found:
            self.db.d[self._rec(r) + 4:self._rec(r) + 8] = struct.pack('>I', used)
        return used

    def check(self):
        """Что в таблице не так для игры: записи с одним hashid (видна первая, остальные мертвы),
        hashid не от своего ключа (ключ не найдётся), нарушен порядок по hashid (у EA записи
        отсортированы, add вставляет по порядку). Пустой список — всё в порядке."""
        out, by_hash, prev = [], defaultdict(list), None
        for r, sid, off in self.rows():
            h = self.hash_at(r)
            by_hash[h].append((r, sid, off))
            if h != key_hash(sid):
                out.append(f'#{r} {sid}: hashid {h:08X}, а от ключа — {key_hash(sid):08X}')
            if prev is not None and h < prev:
                out.append(f'#{r} {sid}: hashid {h:08X} меньше предыдущего {prev:08X} — порядок нарушен')
            prev = h
        for h, group in by_hash.items():
            if len(group) > 1:
                out.append(f'hashid {h:08X} у {len(group)} записей, игра видит первую: '
                           + ', '.join(f'#{r} {sid} «{self.text(off)}»' for r, sid, off in group))
        return out

def main():
    cmd, db_path, meta_path = sys.argv[1:4]
    loc = LocDb(open(db_path, 'rb').read(), load_meta(meta_path))
    if cmd == 'dump':
        flt = sys.argv[4] if len(sys.argv) > 4 else ''
        for r, sid, off in loc.rows():
            t = loc.text(off)
            if flt in sid or flt in t:
                print(f'{sid}\t{t}')
        return
    if cmd == 'check':
        bad = loc.check()
        print('\n'.join(bad) if bad else f'OK: {loc.table["rows"]} записей, у каждой свой hashid')
        sys.exit(1 if bad else 0)
    out, edits = sys.argv[4], dict(a.split('=', 1) for a in sys.argv[5:])
    if cmd == 'put':
        for key, text in edits.items():
            found = loc.find_all(key)
            name = loc.key_at(found[0]) if found else key
            loc.put(key, text)
            note = 'новый ключ' if not found else 'новая строка' + (f', ключ {name}' if name != key else '')
            print(f'{key} -> «{text}» ({note})')
    elif cmd == 'set':
        by_offset = defaultdict(list)
        for r, sid, off in loc.rows():
            by_offset[off].append(sid)
        done, missing = set(), []
        for key, text in edits.items():
            found = loc.find_all(key)
            if not found:
                missing.append(key)
            for r in found:
                off, sid = loc.text_off_at(r), loc.key_at(r)
                if off in done:
                    continue
                loc.set_text(off, text)
                done.add(off)
                others = [s for s in by_offset[off] if s != sid]
                print(f'{sid} -> «{text}»' + (f' (та же строка у: {", ".join(others)})' if others else ''))
        if missing:
            sys.exit(f'нет ключей: {sorted(missing)}')
    else:
        sys.exit(f'нет команды {cmd}: dump, set, put, check')
    bad = loc.check()
    if bad:
        sys.exit('не записано — в базе ошибки (check):\n' + '\n'.join(bad))
    loc.db.fix()
    open(out, 'wb').write(loc.db.d)
    print(f'записано -> {out}')

if __name__ == '__main__':
    main()
