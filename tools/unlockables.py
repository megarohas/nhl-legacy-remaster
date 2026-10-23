"""Закрытое в NHL Legacy по образу игры: экипировка (предзаказ, маски), каталоги редактора, бусты Pro Shop.

    python unlockables.py [IMAGE] items        # 132 вещи менеджера UNLOCKABLE::ExtraContentManager: номер, ключ, имя
    python unlockables.py [IMAGE] catalogs     # каталоги редактора (клюшки, перчатки, коньки, маски…) и закрытое в них
    python unlockables.py [IMAGE] boosts       # 163 буста: 0…122 бусты ×3 силы, 123…149 ячейки, 150…162 Max
    python unlockables.py [IMAGE] tasks        # задачи TXT_UNLOCK_TASK_N → какие бусты они открывают

IMAGE — default.bin NHL Legacy (tools/xex.py), по умолчанию game/work/heads-research/xex/default.bin. Имена из
локализации — с --loc DB META (nhl_eng_us.db и nhl_eng_us-meta.xml, tools/locdb.py), иначе только ключи.

Откуда адреса и что с ними делает порт — docs/legacy-port.md, «Закрытое: предзаказ, маски, бусты, коды формы»
(подмены — nhl-legacy-port/src/nhllegacy_unlock.cpp, cvar'ы nhl_unlock_*). Кратко:
- проверка «вещь открыта» — 82BC2238(менеджер, номер 0…131), «буст открыт» — 82BC2B48(менеджер, 0…162);
- каталоги — таблицы 82BC22D8: в записи номер закрытой вещи (−1 — свободно);
- имена вещей — таблица 0x83A29788 (12 байт: номер, 0, ключ), имена бустов — 82BC17D0.
Каталоги в образе — начальные значения (.data); игра их не переписывает, поэтому чтения образа хватает.
"""
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_IMAGE = os.path.join(HERE, '..', 'game', 'work', 'heads-research', 'xex', 'default.bin')
BASE = 0x82000000

ITEM_NAMES = 0x83A29788  # 132 × 12: номер, 0, ключ имени
# 82BC22D8: категория → (число записей, адрес, смещение номера, длина записи), что за вещи — по ключам
CATALOGS = [
    ('клюшки', 27, 0x83A2A5C0, 116, 124),
    ('перчатки', 20, 0x83A2BFF8, 20, 32),
    ('шлемы', 12, 0x83A2C2A8, 28, 36),
    ('маски вратаря', 87, 0x83A2C5D8, 28, 36),
    ('категория 4', 16, 0x83A2BDE0, 24, 32),
    ('категория 5', 32, 0x83A2A1C0, 20, 32),
    ('категория 6', 33, 0x83A29150, 20, 32),
    ('категория 7', 30, 0x83A29DE8, 20, 32),
    ('коньки', 11, 0x83A2B328, 20, 28),
]
# 82BC17D0: имена бустов (ключ — +12 для 0…122, +8 для 150…162)
BOOSTS = [(0, 72, 0x83A2B490, 32, 12), (72, 51, 0x83A28AC0, 32, 12), (150, 13, 0x83A29570, 20, 8)]
TASKS = 0x8208CB40  # 82BC2FA8: задача → 4 номера бустов (−1 — нет)
NTASKS = 160        # TXT_UNLOCK_TASK_0…159 в локализации; дальше в образе — другая таблица
GOLD = {20, 30, 43, 66, 76, 123, 131}  # 829F4650: редактор прячет всегда


class Img:
    def __init__(self, path):
        self.d = open(path, 'rb').read()
        if self.d[:2] != b'MZ':
            sys.exit(f'{path}: не образ PE (нужен default.bin из tools/xex.py)')

    def u32(self, a):
        return struct.unpack_from('>I', self.d, a - BASE)[0]

    def s32(self, a):
        v = self.u32(a)
        return v - (1 << 32) if v & 0x80000000 else v

    def cstr(self, a):
        o = a - BASE
        if not 0 <= o < len(self.d):
            return None
        e = self.d.find(b'\0', o, o + 96)
        s = self.d[o:e] if e > o else b''
        return s.decode('latin1') if s and all(32 <= c < 127 for c in s) else None

    def key_in(self, rec, size):
        """Первый указатель на строку в записи (ключ имени)."""
        for k in range(0, size, 4):
            v = self.u32(rec + k)
            if 0x82000000 <= v < 0x823B0000:
                s = self.cstr(v)
                if s and len(s) > 2:
                    return s
        return None


def load_loc(argv):
    if '--loc' not in argv:
        return None
    i = argv.index('--loc')
    db, meta = argv[i + 1], argv[i + 2]
    del argv[i:i + 3]
    sys.path.insert(0, HERE)
    from locdb import LocDb
    from tdb_read import load_meta
    loc = LocDb(open(db, 'rb').read(), load_meta(meta))
    return {sid.lower(): loc.text(off) for _, sid, off in loc.rows()}


def name(loc, key):
    if not loc or not key:
        return ''
    t = loc.get(key.lower())
    return f'  «{t.strip()}»' if t else ''


def item_names(im):
    return [im.cstr(im.u32(ITEM_NAMES + 12 * i + 8)) for i in range(132)]


def cmd_items(im, loc):
    for i, k in enumerate(item_names(im)):
        print(f'{i:3}  {k}{name(loc, k)}' + ('  [золотая: редактор прячет]' if i in GOLD else ''))


def cmd_catalogs(im, loc):
    names = item_names(im)
    total = 0
    for title, n, base, uo, size in CATALOGS:
        locked = []
        for i in range(n):
            rec = base + size * i
            u = im.s32(rec + uo)
            if 0 <= u < 132:
                locked.append((i, im.key_in(rec, size), u))
        total += len(locked)
        print(f'{title}: {n} записей @{base:08X}, закрыто {len(locked)}')
        for i, k, u in locked:
            print(f'    #{i:2}  {k}{name(loc, k)}  ← вещь {u} ({names[u]})')
    print(f'— закрыто в каталогах: {total}')


def boost_rows(im):
    for first, n, base, size, ko in BOOSTS:
        for i in range(n):
            yield first + i, im.cstr(im.u32(base + size * i + ko))


def cmd_boosts(im, loc):
    for i, k in boost_rows(im):
        print(f'{i:3}  {k}{name(loc, k)}')
    print('123…149 — ячейки бустов: (вид экипировки + 41) × 3 + ячейка, 9 видов × 3')


def cmd_tasks(im, loc):
    boosts = dict(boost_rows(im))
    for t in range(NTASKS):
        ids = [im.s32(TASKS + 16 * t + 4 * k) for k in range(4)]
        key = f'TXT_UNLOCK_TASK_{t}'
        got = ', '.join(f'{x} {boosts.get(x) or "ячейка"}' for x in ids if x >= 0)
        print(f'{t:3}  {got}{name(loc, key)}')


def main(argv):
    sys.stdout.reconfigure(encoding='utf-8')
    if not argv or argv[0] in ('-h', '--help'):
        sys.exit(__doc__)
    loc = load_loc(argv)
    path = DEFAULT_IMAGE
    if argv and argv[0] not in ('items', 'catalogs', 'boosts', 'tasks'):
        path, argv = argv[0], argv[1:]
    if not argv:
        sys.exit(__doc__)
    if not os.path.isfile(path):
        sys.exit(f'нет образа {path}')
    im = Img(path)
    cmds = {'items': cmd_items, 'catalogs': cmd_catalogs, 'boosts': cmd_boosts, 'tasks': cmd_tasks}
    if argv[0] not in cmds:
        sys.exit(f'нет команды {argv[0]}: {", ".join(cmds)}')
    cmds[argv[0]](im, loc)


if __name__ == '__main__':
    main(sys.argv[1:])
