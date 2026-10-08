"""Ассемблер функции игры из сгенерированного кода порта (комментарии asm + метки).

    python genfn.py GENDIR ADDR [ADDR ...]       # asm функции, которой принадлежит ADDR
    python genfn.py GENDIR ADDR --c              # целиком C++ этой функции

GENDIR — папка сгенерированного кода ReXGlue (port/generated/default,
legacy-port/generated/default…): файлы *_recomp.N.cpp с DEFINE_REX_FUNC(sub_XXXXXXXX) и
комментарием с исходной инструкцией перед каждой строкой. Индекс начал функций кладётся в
GENDIR/_fnindex.txt (пересоздаётся, если старше register.cpp).
"""
import bisect, glob, os, re, sys


def index(gen):
    path = os.path.join(gen, '_fnindex.txt')
    reg = glob.glob(os.path.join(gen, '*_register.cpp'))
    stale = not os.path.exists(path) or (reg and os.path.getmtime(reg[0]) > os.path.getmtime(path))
    if stale:
        rows = []
        for f in glob.glob(os.path.join(gen, '*_recomp.*.cpp')):
            with open(f, encoding='utf-8', errors='replace') as fh:
                for i, line in enumerate(fh):
                    if line.startswith('DEFINE_REX_FUNC(sub_'):
                        rows.append((line[20:28], os.path.basename(f), i))
        rows.sort()
        with open(path, 'w') as o:
            for a, f, i in rows:
                o.write(f'{a} {f} {i}\n')
    return [l.split() for l in open(path)]


def show(gen, rows, starts, target, full):
    k = bisect.bisect_right(starts, target) - 1
    a, f, ln = rows[k]
    if starts[k] != target:
        print(f'# {target:08X} — внутри sub_{a}')
    lines = open(os.path.join(gen, f), encoding='utf-8', errors='replace').read().split('\n')
    i = int(ln)
    while i < len(lines):
        s = lines[i]
        if i > int(ln) and s.startswith('DEFINE_REX_FUNC('):
            break
        t = s.strip()
        if full:
            print(s)
        elif t.startswith('// '):
            print('    ' + t[3:])
        elif re.match(r'^loc_[0-9A-F]{8}:', t) or t.startswith('DEFINE_REX_FUNC'):
            print(t)
        elif 'REX_FATAL' in t:
            print('    ' + t)
        i += 1


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    gen = sys.argv[1]
    rows = index(gen)
    starts = [int(a, 16) for a, _, _ in rows]
    for arg in sys.argv[2:]:
        if arg.startswith('--'):
            continue
        show(gen, rows, starts, int(arg, 16), '--c' in sys.argv)


if __name__ == '__main__':
    main()
