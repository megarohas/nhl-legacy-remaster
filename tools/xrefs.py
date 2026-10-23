"""Перекрёстные ссылки по образу Xbox 360 (default.bin из tools/xex.py, база 0x82000000): кто берёт адрес,
кто зовёт функцию, кто пишет слово, где в данных лежит указатель.

    python xrefs.py IMAGE refs ADDR [END]     # код, который собирает адрес из [ADDR, END) парой lis + addi/lwz/stw…/ori
    python xrefs.py IMAGE calls FUNC          # места bl FUNC (и в какой функции)
    python xrefs.py IMAGE writes ADDR         # записи stw/stb/sth/stwu… ровно в ADDR (lis + смещение)
    python xrefs.py IMAGE ptrs ADDR [END]     # выровненные слова в образе, равные адресу из [ADDR, END)
    python xrefs.py IMAGE func ADDR           # начало и конец функции, которой принадлежит ADDR

IMAGE по умолчанию (если вместо него сразу команда) — game/work/heads-research/xex/default.bin (NHL Legacy).
Адреса — hex (0x можно не писать). Пример (docs/legacy-port.md, «Закрытое…»):

    python xrefs.py refs 83A29788        # кто читает таблицу имён закрытой экипировки
    python xrefs.py calls 82BC2238       # все проверки «вещь открыта?»

Как ищется: lis rX, HI запоминается до следующей lis в тот же регистр или blr (окно — 400 инструкций);
D-форма с базой rX даёт адрес HI<<16 + смещение. Переходы и затирание регистра между ними не отслеживаются —
бывают лишние находки, но адрес, собранный в одном линейном куске, не теряется. Код, который берёт адрес из
таблицы указателей (vtable, массивы структур), этим не найти — для него `ptrs`. Границы функций — из .pdata
(tools/xmatch.py, Image). Образ одной версии игры: для NHL 13 — свой default.bin.
"""
import bisect
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import xmatch  # noqa: E402

DEFAULT_IMAGE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'game', 'work', 'heads-research',
                             'xex', 'default.bin')
BASE = xmatch.BASE
DFORM = {14, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55}
STORES = {36: 'stw', 37: 'stwu', 38: 'stb', 39: 'stbu', 44: 'sth', 45: 'sthu', 47: 'stmw'}
MNEM = {14: 'addi', 32: 'lwz', 33: 'lwzu', 34: 'lbz', 35: 'lbzu', 40: 'lhz', 41: 'lhzu', 42: 'lha', 43: 'lhau',
        46: 'lmw', 48: 'lfs', 49: 'lfsu', 50: 'lfd', 51: 'lfdu', 52: 'stfs', 53: 'stfsu', 54: 'stfd', 55: 'stfdu',
        58: 'ld', 62: 'std', **STORES}
WINDOW = 400


def s16(v):
    return v - 0x10000 if v & 0x8000 else v


class Xrefs:
    def __init__(self, path):
        self.im = xmatch.Image(path)
        self.img = self.im.img
        t0, t1 = self.im.sections['.text']
        self.t0 = t0
        n = (t1 - t0) // 4
        self.words = struct.unpack(f'>{n}I', self.img[t0 - BASE:t0 - BASE + 4 * n])

    def func(self, a):
        i = bisect.bisect_right(self.im.starts, a) - 1
        if i >= 0 and self.im.starts[i] <= a < self.im.ends[i]:
            return self.im.starts[i], self.im.ends[i]
        return None, None

    def where(self, a):
        f, _ = self.func(a)
        return f'{a:08X}  (в функции {f:08X})' if f is not None else f'{a:08X}  (вне .pdata)'

    def cstr(self, a):
        o = a - BASE
        if not 0 <= o < len(self.img):
            return None
        end = self.img.find(b'\0', o, o + 128)
        s = self.img[o:end] if end > o else b''
        return s.decode('latin1') if s and all(32 <= c < 127 for c in s) else None

    def pairs(self, lo, hi, stores_only=False):
        """(место, адрес, место lis, мнемоника) для адресов из [lo, hi)."""
        W, out = self.words, []
        his = {h & 0xFFFF for h in range(((lo + 0x8000) >> 16) - 1, ((hi + 0x8000) >> 16) + 2)}
        for i, w in enumerate(W):
            if w >> 26 != 15 or (w >> 16) & 31 or (w & 0xFFFF) not in his:
                continue
            rd, high = (w >> 21) & 31, (w & 0xFFFF) << 16
            for j in range(i + 1, min(len(W), i + WINDOW)):
                x = W[j]
                op, ra, rt = x >> 26, (x >> 16) & 31, (x >> 21) & 31
                if ra == rd and (op in DFORM or op in (58, 62)) and (not stores_only or op in STORES):
                    lo16 = s16(x & 0xFFFC) if op in (58, 62) else s16(x & 0xFFFF)
                    a = (high + lo16) & 0xFFFFFFFF
                    if lo <= a < hi:
                        out.append((self.t0 + 4 * j, a, self.t0 + 4 * i, MNEM.get(op, f'op{op}')))
                elif op == 24 and rt == rd and not stores_only:            # ori rA, rX, lo
                    a = high | (x & 0xFFFF)
                    if lo <= a < hi:
                        out.append((self.t0 + 4 * j, a, self.t0 + 4 * i, 'ori'))
                if (op == 15 and rt == rd) or x == 0x4E800020:
                    break
        return sorted(set(out))

    def calls(self, f):
        out = []
        for i, w in enumerate(self.words):
            if w >> 26 == 18 and w & 1:
                li = w & 0x03FFFFFC
                if li & 0x02000000:
                    li -= 0x04000000
                a = self.t0 + 4 * i
                if ((li if w & 2 else a + li) & 0xFFFFFFFF) == f:
                    out.append(a)
        return out

    def ptrs(self, lo, hi):
        out = []
        img = self.img
        n = len(img) // 4
        words = struct.unpack(f'>{n}I', img[:4 * n])
        for i, v in enumerate(words):
            if lo <= v < hi:
                out.append((BASE + 4 * i, v))
        return out


def parse(x):
    return int(x, 16)


def main(argv):
    sys.stdout.reconfigure(encoding='utf-8')  # канал Windows — cp1251
    if len(argv) < 2 or argv[0] in ('-h', '--help'):
        sys.exit(__doc__)
    if argv[0] in ('refs', 'calls', 'writes', 'ptrs', 'func'):
        path, argv = DEFAULT_IMAGE, argv
    else:
        path, argv = argv[0], argv[1:]
    if not os.path.isfile(path):
        sys.exit(f'нет образа {path}: python tools/xex.py (docs/legacy-port-feasibility.md)')
    if not argv:
        sys.exit(__doc__)
    cmd, args = argv[0], [parse(a) for a in argv[1:]]
    if not args:
        sys.exit(f'{cmd}: нужен адрес')
    x = Xrefs(path)
    if cmd == 'refs':
        lo = args[0]
        hi = args[1] if len(args) > 1 else lo + 1
        rows = x.pairs(lo, hi)
        for p, a, l, m in rows:
            s = x.cstr(a)
            print(f'{x.where(p)}  {m:5} -> {a:08X}' + (f'  "{s}"' if s else '') + f'  (lis @{l:08X})')
        print(f'— {len(rows)} мест')
    elif cmd == 'calls':
        rows = x.calls(args[0])
        for p in rows:
            print(x.where(p))
        print(f'— {len(rows)} вызовов {args[0]:08X}')
    elif cmd == 'writes':
        rows = x.pairs(args[0], args[0] + 1, stores_only=True)
        for p, a, l, m in rows:
            print(f'{x.where(p)}  {m}')
        print(f'— {len(rows)} записей в {args[0]:08X}')
    elif cmd == 'ptrs':
        lo = args[0]
        hi = args[1] if len(args) > 1 else lo + 1
        rows = x.ptrs(lo, hi)
        for p, v in rows:
            sec = next((k for k, (s0, s1) in x.im.sections.items() if s0 <= p < s1), '?')
            print(f'{p:08X} ({sec}) = {v:08X}')
        print(f'— {len(rows)} слов')
    elif cmd == 'func':
        f, e = x.func(args[0])
        print(f'{f:08X}…{e:08X} ({(e - f) // 4} инструкций)' if f is not None else 'вне функций .pdata')
    else:
        sys.exit(f'нет команды {cmd}: refs, calls, writes, ptrs, func')


if __name__ == '__main__':
    main(sys.argv[1:])
