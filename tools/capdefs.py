"""Финансы франшизы NHL 13: fe/resource_kernel/capdefs.brk (потолок, порог, минималка, новичок).

В NHL 13 (в отличие от NHL Legacy, где те же данные в fe/salarydata.bin) потолок зарплат
франшизы лежит в таблице «resource kernel» capdefs.brk (170 байт, хвост «BRK»). Игра сперва
ищет cache:\\fe\\resource_kernel\\capdefs.brk, потом архив — правленая копия в
userdata/cache/guest/fe/resource_kernel/ действует без перепаковки (docs/franchise-seasons.md).

Раскладка (числа 16 бит, little-endian):
  +0x39  начала столбцов [0, 2, 14, 26, 38] (индексы в массиве значений)
  +0x43  50 значений:
         столбец 0  [порог, потолок]                 × 100 000  (542, 702 → 54,2 / 70,2 млн)
         столбец 1  прибавка порога за год 0…11       × 1000
         столбец 2  прибавка потолка за год 0…11      × 1000
         столбец 3  минимальная зарплата, год 0…11    × 1000     (525 …)
         столбец 4  наибольшая зарплата новичка       × 1000     (925 …)
  +0xA7  «BRK»
Сезон франшизы n (0 — первый) берёт базу + Σ прибавок за годы 0…n (как 82BBCAE8 в NHL Legacy),
минималку и новичка — значение года n.

  python tools/capdefs.py show [ФАЙЛ]
  python tools/capdefs.py write ВХОД ВЫХОД [--cap 104000000] [--floor 76900000] [--min 850000]
       [--rookie N]    — первый сезон; рост по годам — как в игре (сдвиг всех лет на разницу)
"""
import argparse
import struct
import sys

COLSTART_AT = 0x39
VALUES_AT = 0x43
NCOLS = 5
SIZE = 170
DEFAULT = 'game/extracted/big/cache/fe/resource_kernel/capdefs.brk'


def parse(data):
    if len(data) != SIZE or data[-3:] != b'BRK':
        raise SystemExit(f'не capdefs.brk NHL 13: {len(data)} байт, хвост {data[-3:]!r}')
    starts = list(struct.unpack_from(f'<{NCOLS}h', data, COLSTART_AT))
    n = (len(data) - 3 - VALUES_AT) // 2
    values = list(struct.unpack_from(f'<{n}h', data, VALUES_AT))
    if starts != [0, 2, 14, 26, 38] or n != 50:
        raise SystemExit(f'неожиданная раскладка: столбцы {starts}, значений {n}')
    return starts, values


def columns(starts, values):
    bounds = starts + [len(values)]
    return [values[bounds[i]:bounds[i + 1]] for i in range(NCOLS)]


def show(path):
    starts, values = parse(open(path, 'rb').read())
    base, floor_inc, cap_inc, minsal, rookie = columns(starts, values)
    print(f'{path}')
    print(f'  порог {base[0] * 100000:,}  потолок {base[1] * 100000:,}  (× 100 000)')
    floor = base[0] * 100000
    cap = base[1] * 100000
    print('  сезон  порог         потолок       игрок макс    минималка  новичок')
    for n in range(len(cap_inc)):
        floor += floor_inc[n] * 1000
        cap += cap_inc[n] * 1000
        print(f'  {n:>5}  {floor:>12,}  {cap:>12,}  {cap // 5:>12,}  {minsal[n] * 1000:>9,}  {rookie[n] * 1000:>9,}')


def write(src, dst, cap, floor, minimum, rookie):
    data = bytearray(open(src, 'rb').read())
    starts, values = parse(bytes(data))
    base, floor_inc, cap_inc, minsal, rookie_col = columns(starts, values)
    # первый сезон (n = 0) = база + прибавка года 0; прибавка года 0 в игре — 0
    if floor is not None:
        values[starts[0] + 0] = (floor - floor_inc[0] * 1000) // 100000
    if cap is not None:
        values[starts[0] + 1] = (cap - cap_inc[0] * 1000) // 100000
    if minimum is not None:
        shift = minimum // 1000 - minsal[0]
        for i in range(len(minsal)):
            values[starts[3] + i] = minsal[i] + shift
    if rookie is not None:
        shift = rookie // 1000 - rookie_col[0]
        for i in range(len(rookie_col)):
            values[starts[4] + i] = rookie_col[i] + shift
    for v in values:
        if not -32768 <= v <= 32767:
            raise SystemExit(f'значение {v} не влезает в 16 бит')
    struct.pack_into(f'<{len(values)}h', data, VALUES_AT, *values)
    open(dst, 'wb').write(data)
    # проверка: первый сезон
    _, check = parse(bytes(data))
    b, fi, ci, ms, rk = columns(starts, check)
    got = (b[0] * 100000 + fi[0] * 1000, b[1] * 100000 + ci[0] * 1000, ms[0] * 1000, rk[0] * 1000)
    print(f'{dst}: первый сезон — порог {got[0]:,}, потолок {got[1]:,}, игрок макс {got[1] // 5:,}, '
          f'минималка {got[2]:,}, новичок {got[3]:,}')
    for name, want, have in (('потолок', cap, got[1]), ('порог', floor, got[0]), ('минималка', minimum, got[2]),
                             ('новичок', rookie, got[3])):
        if want is not None and want != have:
            raise SystemExit(f'{name}: {want:,} не представимо (база кратна 100 000, годы — 1000), вышло {have:,}')


def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    s = sub.add_parser('show')
    s.add_argument('file', nargs='?', default=DEFAULT)
    w = sub.add_parser('write')
    w.add_argument('src')
    w.add_argument('dst')
    w.add_argument('--cap', type=int)
    w.add_argument('--floor', type=int)
    w.add_argument('--min', type=int, dest='minimum')
    w.add_argument('--rookie', type=int)
    a = ap.parse_args()
    if a.cmd == 'show':
        show(a.file)
    else:
        write(a.src, a.dst, a.cap, a.floor, a.minimum, a.rookie)
        show(a.dst)


if __name__ == '__main__':
    sys.exit(main())
