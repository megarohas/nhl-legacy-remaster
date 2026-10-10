"""Знаки ® и ™ из официальных SVG НХЛ (assets.nhle.com): у EA в логотипах их нет. Знак — отдельные подпути внутри
<path> (иногда целый <path>, иногда — часть контура, например чёрного кольца «Бостона»). Разбор атрибута d на подпути
(по командам M/m; координаты — абсолютные), поиск знака:
  * ® — почти круглый подпуть 16…34 единицы viewBox (официальный знак ~23…25 при viewBox 960×640) и всё, что в его
    рамке (кольцо, «R», дырки);
  * ™ и прочее — подпути целиком в рамке, заданной вручную (--box x,y,w,h в единицах viewBox).
Убранные подпути вырезаются, каждый оставшийся подпуть начинается с абсолютного M (иначе съехали бы относительные
m после вырезанных). Пустой <path> убирается целиком.

    python tools/logos/svgclean.py IN.svg OUT.svg [--box x,y,w,h[;…]] [--keep-r]
    python tools/logos/svgclean.py --list IN.svg        # подпути: номер пути.подпути, рамка, число команд
"""
import math
import re
import sys

NUM = re.compile(r'[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?')
PATH_RX = re.compile(r'<path\b[^>]*?(?:/>|>.*?</path>)', re.S)
D_RX = re.compile(r'\sd="([^"]*)"', re.S)
ARGS = {'M': 2, 'L': 2, 'H': 1, 'V': 1, 'C': 6, 'S': 4, 'Q': 4, 'T': 2, 'A': 7, 'Z': 0}


class Reader:
    def __init__(self, s):
        self.s, self.i = s, 0

    def skip(self):
        while self.i < len(self.s) and self.s[self.i] in ' \t\r\n,':
            self.i += 1

    def eof(self):
        self.skip()
        return self.i >= len(self.s)

    def peek_cmd(self):
        self.skip()
        return self.s[self.i] if self.i < len(self.s) and self.s[self.i].isalpha() else None

    def num(self):
        self.skip()
        m = NUM.match(self.s, self.i)
        if not m:
            raise ValueError(f'число ожидалось в {self.i}: {self.s[self.i:self.i + 20]!r}')
        self.i = m.end()
        return float(m.group(0))

    def flag(self):
        self.skip()
        c = self.s[self.i]
        if c not in '01':
            raise ValueError(f'флаг дуги ожидался в {self.i}: {self.s[self.i:self.i + 20]!r}')
        self.i += 1
        return float(c)


def _bez(p0, ctrl, n=12):
    """Точки кривой Безье (квадратичной или кубической: ctrl — контрольные точки и конец) для рамки."""
    out = []
    pts = [p0] + list(ctrl)
    for k in range(1, n + 1):
        t = k / n
        if len(pts) == 3:
            (x0, y0), (x1, y1), (x2, y2) = pts
            x = (1 - t) ** 2 * x0 + 2 * (1 - t) * t * x1 + t * t * x2
            y = (1 - t) ** 2 * y0 + 2 * (1 - t) * t * y1 + t * t * y2
        else:
            (x0, y0), (x1, y1), (x2, y2), (x3, y3) = pts
            x = (1 - t) ** 3 * x0 + 3 * (1 - t) ** 2 * t * x1 + 3 * (1 - t) * t * t * x2 + t ** 3 * x3
            y = (1 - t) ** 3 * y0 + 3 * (1 - t) ** 2 * t * y1 + 3 * (1 - t) * t * t * y2 + t ** 3 * y3
        out.append((x, y))
    return out


def _arc(p0, rx, ry, phi, fa, fs, p1, n=24):
    """Точки эллиптической дуги SVG (переход от концов к центру — SVG 1.1, F.6.5) для рамки."""
    (x1, y1), (x2, y2) = p0, p1
    if (x1, y1) == (x2, y2):
        return []
    rx, ry = abs(rx), abs(ry)
    if not rx or not ry:
        return [p1]
    c, s = math.cos(math.radians(phi)), math.sin(math.radians(phi))
    dx, dy = (x1 - x2) / 2, (y1 - y2) / 2
    xp, yp = c * dx + s * dy, -s * dx + c * dy
    lam = (xp / rx) ** 2 + (yp / ry) ** 2
    if lam > 1:
        rx, ry = rx * math.sqrt(lam), ry * math.sqrt(lam)
    num = rx * rx * ry * ry - rx * rx * yp * yp - ry * ry * xp * xp
    den = rx * rx * yp * yp + ry * ry * xp * xp
    k = math.sqrt(max(0.0, num / den)) if den else 0.0
    if fa == fs:
        k = -k
    cxp, cyp = k * rx * yp / ry, -k * ry * xp / rx
    cx, cy = c * cxp - s * cyp + (x1 + x2) / 2, s * cxp + c * cyp + (y1 + y2) / 2

    def ang(ux, uy, vx, vy):
        return math.atan2(ux * vy - uy * vx, ux * vx + uy * vy)
    t1 = ang(1, 0, (xp - cxp) / rx, (yp - cyp) / ry)
    dt = ang((xp - cxp) / rx, (yp - cyp) / ry, (-xp - cxp) / rx, (-yp - cyp) / ry)
    if not fs and dt > 0:
        dt -= 2 * math.pi
    elif fs and dt < 0:
        dt += 2 * math.pi
    out = []
    for i in range(1, n + 1):
        t = t1 + dt * i / n
        out.append((cx + rx * math.cos(t) * c - ry * math.sin(t) * s, cy + rx * math.cos(t) * s + ry * math.sin(t) * c))
    return out


def parse(d):
    """→ список команд: dict(cmd, args, start, end — границы текста команды, p1 — точка после, pts — точки рамки
    (кривые и дуги — точками на них), moveto — True у явной команды M/m)."""
    r = Reader(d)
    out = []
    cx = cy = sx = sy = 0.0
    cmd = None
    last_c = last_q = None        # вторая контрольная точка прошлой C/S, контрольная прошлой Q/T (отражение у S, T)
    while not r.eof():
        start = r.i
        c = r.peek_cmd()
        explicit = False
        if c:
            r.i += 1
            cmd = c
            explicit = True
        elif cmd is None:
            raise ValueError('путь без команды')
        elif cmd in 'Mm':                      # повтор пар после moveto — lineto
            cmd = 'l' if cmd == 'm' else 'L'
        up = cmd.upper()
        rel = cmd.islower()
        if up == 'A':
            args = [r.num(), r.num(), r.num(), r.flag(), r.flag(), r.num(), r.num()]
        else:
            args = [r.num() for _ in range(ARGS[up])]
        pts = []
        p0 = (cx, cy)
        nc = nq = None
        if up == 'Z':
            cx, cy = sx, sy
            pts = [(cx, cy)]
        elif up in ('M', 'L'):
            x, y = args
            if rel:
                x, y = cx + x, cy + y
            cx, cy = x, y
            if up == 'M':
                sx, sy = x, y
            pts = [(x, y)]
        elif up == 'H':
            cx = args[0] + (cx if rel else 0)
            pts = [(cx, cy)]
        elif up == 'V':
            cy = args[0] + (cy if rel else 0)
            pts = [(cx, cy)]
        elif up in ('C', 'S', 'Q', 'T'):
            xs, ys = list(args[0::2]), list(args[1::2])
            if rel:
                xs, ys = [cx + v for v in xs], [cy + v for v in ys]
            ctrl = list(zip(xs, ys))
            if up == 'S':
                ctrl = [(2 * cx - last_c[0], 2 * cy - last_c[1]) if last_c else (cx, cy)] + ctrl
            if up == 'T':
                ctrl = [(2 * cx - last_q[0], 2 * cy - last_q[1]) if last_q else (cx, cy)] + ctrl
            pts = _bez(p0, ctrl)
            if up in ('C', 'S'):
                nc = ctrl[-2]
            else:
                nq = ctrl[0]
            cx, cy = ctrl[-1]
        elif up == 'A':
            x, y = args[5], args[6]
            if rel:
                x, y = cx + x, cy + y
            pts = _arc(p0, args[0], args[1], args[2], args[3], args[4], (x, y)) or [(x, y)]
            cx, cy = x, y
        last_c, last_q = nc, nq
        out.append(dict(cmd=cmd, args=args, start=start, end=r.i, p1=(cx, cy), pts=pts,
                        moveto=explicit and up == 'M'))
    return out


def subpaths(d):
    """→ [(текст подпути с абсолютным M в начале, рамка (x0, y0, x1, y1), число команд)]. Подпуть — от явной M/m до
    следующей явной M/m (команды после z без moveto остаются в том же подпути)."""
    cmds = parse(d)
    groups = []
    for c in cmds:
        if c['moveto'] or not groups:
            groups.append([])
        groups[-1].append(c)
    res = []
    for g in groups:
        first = g[0]
        if first['cmd'] not in 'Mm':
            raise ValueError('подпуть не с moveto')
        x, y = first['p1']
        text = f'M{x:.4f}'.rstrip('0').rstrip('.') + ' ' + f'{y:.4f}'.rstrip('0').rstrip('.')
        if len(g) > 1:
            nxt = g[1]
            tail = d[nxt['start']:g[-1]['end']]
            if not nxt['moveto'] and d[nxt['start']:nxt['end']].lstrip(' ,\t\r\n')[:1] not in tuple('MmLlHhVvCcSsQqTtAaZz'):
                # неявный lineto после первой пары moveto: та же «буква» — l у m, L у M
                tail = ('l' if first['cmd'] == 'm' else 'L') + tail
            text += tail
        xs = [p[0] for c in g for p in c['pts']]
        ys = [p[1] for c in g for p in c['pts']]
        res.append((text, (min(xs), min(ys), max(xs), max(ys)), len(g)))
    return res


def find_marks(paths, boxes=(), keep_r=False):
    """paths — [[(text, bbox, n)…] по каждому <path>] → множество (путь, подпуть) знаков.
    ® — пара концентрических почти круглых подпутей (внешний 10…36 единиц, внутренний 0,72…0,84 внешнего) и подпуть
    внутри внутреннего (буква R); убирается всё в рамке внешнего круга и обводка вокруг знака (подпуть, внутри
    рамки которого — только части знака, не больше 1,5 диаметра)."""
    marks = set()
    allsub = [(pi, si, b) for pi, sp in enumerate(paths) for si, (_, b, _) in enumerate(sp)]

    def circ(b):
        w, h = b[2] - b[0], b[3] - b[1]
        return w > 0 and abs(w - h) <= 0.08 * max(w, h)

    def inside(b, o, tol=0.8):
        return b[0] >= o[0] - tol and b[1] >= o[1] - tol and b[2] <= o[2] + tol and b[3] <= o[3] + tol
    if not keep_r:
        for pi, si, o in allsub:
            D = o[2] - o[0]
            if not (10 <= D <= 36 and circ(o)):
                continue
            ocx, ocy = (o[0] + o[2]) / 2, (o[1] + o[3]) / 2
            inner = [b for _, _, b in allsub if circ(b) and 0.72 <= (b[2] - b[0]) / D <= 0.84
                     and abs((b[0] + b[2]) / 2 - ocx) <= 0.06 * D and abs((b[1] + b[3]) / 2 - ocy) <= 0.06 * D]
            if not inner:
                continue
            letter = [b for _, _, b in allsub if inside(b, inner[0], 0.3) and (b[2] - b[0]) < 0.7 * D
                      and (b[3] - b[1]) > 0.45 * D]
            if not letter:
                continue
            part = {(pj, sj) for pj, sj, b in allsub if inside(b, o)}
            marks |= part
            for pj, sj, b in allsub:                  # обводка вокруг знака
                if (pj, sj) in part:
                    continue
                if inside(o, b, 0.0) and (b[2] - b[0]) <= 1.5 * D and (b[3] - b[1]) <= 1.5 * D:
                    if all((pk, sk) in part or (pk, sk) == (pj, sj) for pk, sk, c in allsub if inside(c, b, 0.3)):
                        marks.add((pj, sj))
    for bx, by, bw, bh in boxes:
        for pi, si, (a0, b0, a1, b1) in allsub:
            if a0 >= bx and b0 >= by and a1 <= bx + bw and b1 <= by + bh:
                marks.add((pi, si))
    return marks


def clean(svg, boxes=(), keep_r=False):
    """→ (SVG без знаков, [(номер пути, [(номер подпути, рамка)…])…])."""
    elems = list(PATH_RX.finditer(svg))
    parsed = []
    for m in elems:
        dm = D_RX.search(m.group(0))
        parsed.append(subpaths(dm.group(1)) if dm else [])
    marks = find_marks(parsed, boxes, keep_r)
    out, pos, removed = [], 0, []
    for pi, m in enumerate(elems):
        out.append(svg[pos:m.start()])
        pos = m.end()
        el = m.group(0)
        keep = [t for si, (t, b, n) in enumerate(parsed[pi]) if (pi, si) not in marks]
        gone = [(si, b) for si, (t, b, n) in enumerate(parsed[pi]) if (pi, si) in marks]
        if gone:
            removed.append((pi, gone))
        if not keep:
            continue                                  # путь целиком — знак
        if gone:
            dm = D_RX.search(el)
            el = el[:dm.start(1)] + ''.join(keep) + el[dm.end(1):]
        out.append(el)
    out.append(svg[pos:])
    return ''.join(out), removed


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    a = sys.argv[1:]
    if a and a[0] == '--list':
        svg = open(a[1], encoding='utf-8').read()
        for pi, m in enumerate(PATH_RX.finditer(svg)):
            dm = D_RX.search(m.group(0))
            for si, (t, b, n) in enumerate(subpaths(dm.group(1)) if dm else []):
                print(f'{pi}.{si}: {b[0]:.1f},{b[1]:.1f} {b[2] - b[0]:.1f}x{b[3] - b[1]:.1f} ({n} команд)')
        return
    if len(a) < 2:
        sys.exit(__doc__)
    boxes = []
    if '--box' in a:
        i = a.index('--box')
        boxes = [tuple(float(v) for v in b.split(',')) for b in a[i + 1].split(';') if b]
        del a[i:i + 2]
    keep_r = '--keep-r' in a
    svg = open(a[0], encoding='utf-8').read()
    res, removed = clean(svg, boxes, keep_r)
    open(a[1], 'w', encoding='utf-8').write(res)
    for pi, gone in removed:
        print(f'путь {pi}: убрано подпутей {len(gone)}: ' + '; '.join(
            f'{si} [{b[0]:.1f},{b[1]:.1f} {b[2] - b[0]:.1f}x{b[3] - b[1]:.1f}]' for si, b in gone))
    if not removed:
        print('знаков не найдено')


if __name__ == '__main__':
    main()
