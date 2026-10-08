"""Нижний край свитера сзади — как в NHL 10: веса края от NHL 10 на сетках свитера NHL 13.

    python jersey10.py build [--out DIR] [--only подстрока,…] [--no-fix]
                                     # 16 вариантов свитера полевых × 3 детализации → DIR (раскладка cache:, по
                                     # умолчанию game/work/models/jersey10/out) и manifest.json
    python jersey10.py check [--out DIR] [--only …]
                                     # перекодирование, что поменялось, швы, край против шорт и растяжение в позах
    python jersey10.py preview [--out DIR] [--png PATH]
                                     # лист game/work/models/preview/jersey10/sheet.png: посадка катания сзади и
                                     # сбоку — NHL 13 / NHL 10 / итог (PIT и TOR дома и в гостях)
    python jersey10.py info          # варианты свитера NHL 13 ↔ NHL 10

У всех команд — опция --game {nhl13,legacy} (или NHL_GAME, tools/gameprofile.py): чьи свитера, шорты и скелет брать и
куда писать по умолчанию (NHL 13 — game/work/models/jersey10, Legacy — game/work/legacy-data/models/jersey10). У NHL
Legacy сетки свитеров и скелет — байт в байт как у NHL 13, шорты _3 — те же вершины, но полосы вместо списка
треугольников. Лист превью у Legacy — «Legacy, оригинал / Legacy с модом / NHL 13 с модом» (готовые свитера NHL 13 —
game/work/models/jersey10/out, с текстурами и шортами NHL 13; --no-nhl13 — без этой колонки).

У NHL 10 и NHL 13 сетка свитера одна и та же (те же вершины, треугольники, UV; позиции основного варианта — до долей
мм), а веса нижнего края спины разные: у NHL 13 край на 30–60 % привязан к скруткам бёдер (кости 115/121) и в
посадке катания облегает зад, у NHL 10 — к тазу и позвоночнику и отстаёт. Сборка: сетка, UV, индексы, позиции —
NHL 13; веса заднего нижнего края — смесь с весами того же варианта NHL 10 (плавный переход по высоте и к бокам; у
заправленных вариантов — только висящая часть); затем край чуть отодвигается от шорт там, где в позах катания он ушёл
бы в них глубже исходного. NHL 10 — с диска game/other/nhl10 (BIG4 + RefPack, или распакованное game/other/nhl10/big).

Подробно — docs/player-models.md §10. Только стандартная библиотека (+ Chrome/Edge без окна — лист превью, как в
teamart); rw4mesh, czkit, kitpaint, teamart, playerhead — как библиотеки.
"""
import json, math, os, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rw4mesh as rm  # noqa: E402

V = rm.v_sub
dot, cross, norm = rm.v_dot, rm.v_cross, rm.v_norm


def vadd(a, b):
    return [a[0] + b[0], a[1] + b[1], a[2] + b[2]]


def vmul(a, s):
    return [a[0] * s, a[1] * s, a[2] * s]


def vlen(a):
    return math.sqrt(a[0] * a[0] + a[1] * a[1] + a[2] * a[2])


# ---------------------------------------------------------------- геометрия: ближайшая точка, сетка поиска

def closest_on_tri(p, a, b, c):
    """Ближайшая точка треугольника abc к p (Эриксон, «Real-Time Collision Detection», 5.1.5) → (точка, (u, v, w))."""
    ab, ac, ap = V(b, a), V(c, a), V(p, a)
    d1, d2 = dot(ab, ap), dot(ac, ap)
    if d1 <= 0 and d2 <= 0:
        return a, (1.0, 0.0, 0.0)
    bp = V(p, b)
    d3, d4 = dot(ab, bp), dot(ac, bp)
    if d3 >= 0 and d4 <= d3:
        return b, (0.0, 1.0, 0.0)
    vc = d1 * d4 - d3 * d2
    if vc <= 0 and d1 >= 0 and d3 <= 0:
        t = d1 / (d1 - d3)
        return vadd(a, vmul(ab, t)), (1 - t, t, 0.0)
    cp = V(p, c)
    d5, d6 = dot(ab, cp), dot(ac, cp)
    if d6 >= 0 and d5 <= d6:
        return c, (0.0, 0.0, 1.0)
    vb = d5 * d2 - d1 * d6
    if vb <= 0 and d2 >= 0 and d6 <= 0:
        t = d2 / (d2 - d6)
        return vadd(a, vmul(ac, t)), (1 - t, 0.0, t)
    va = d3 * d6 - d5 * d4
    if va <= 0 and (d4 - d3) >= 0 and (d5 - d6) >= 0:
        t = (d4 - d3) / ((d4 - d3) + (d5 - d6))
        return vadd(b, vmul(V(c, b), t)), (0.0, 1 - t, t)
    den = 1.0 / (va + vb + vc)
    v, w = vb * den, vc * den
    return vadd(a, vadd(vmul(ab, v), vmul(ac, w))), (1 - v - w, v, w)


class TriGrid:
    """Треугольники (pts — точки, tris — тройки номеров) в равномерной сетке ячеек: ближайшая точка поверхности и
    псевдонормаль в ней (грань / ребро / вершина — для знака стороны)."""

    def __init__(self, pts, tris, cell=0.03):
        self.pts, self.tris, self.cell = pts, list(tris), cell
        self.fn = []
        for a, b, c in self.tris:
            n = cross(V(pts[b], pts[a]), V(pts[c], pts[a]))
            self.fn.append(norm(n) or [0.0, 0.0, 0.0])
        # псевдонормали вершин и рёбер (взвешенные углом) — для знака стороны
        vn = {}
        en = {}
        for k, (a, b, c) in enumerate(self.tris):
            n = self.fn[k]
            for i, j, l in ((a, b, c), (b, c, a), (c, a, b)):
                e1, e2 = norm(V(pts[j], pts[i])), norm(V(pts[l], pts[i]))
                ang = math.acos(max(-1.0, min(1.0, dot(e1, e2)))) if e1 and e2 else 0.0
                s = vn.setdefault(i, [0.0, 0.0, 0.0])
                for q in range(3):
                    s[q] += ang * n[q]
                key = (min(i, j), max(i, j))
                s = en.setdefault(key, [0.0, 0.0, 0.0])
                for q in range(3):
                    s[q] += n[q]
        self.vn = {i: norm(v) or [0.0, 0.0, 0.0] for i, v in vn.items()}
        self.en = {k: norm(v) or [0.0, 0.0, 0.0] for k, v in en.items()}
        self.grid = {}
        for k, (a, b, c) in enumerate(self.tris):
            lo = [min(pts[a][q], pts[b][q], pts[c][q]) for q in range(3)]
            hi = [max(pts[a][q], pts[b][q], pts[c][q]) for q in range(3)]
            i0 = [int(math.floor(lo[q] / cell)) for q in range(3)]
            i1 = [int(math.floor(hi[q] / cell)) for q in range(3)]
            for x in range(i0[0], i1[0] + 1):
                for y in range(i0[1], i1[1] + 1):
                    for z in range(i0[2], i1[2] + 1):
                        self.grid.setdefault((x, y, z), []).append(k)

    def nearest(self, p, rmax=0.25):
        """→ (расстояние, точка, номер грани, (u, v, w)) или None, если ближе rmax ничего нет."""
        cell = self.cell
        c0 = [int(math.floor(p[q] / cell)) for q in range(3)]
        best = None
        r = 0
        seen = set()
        while True:
            for x in range(c0[0] - r, c0[0] + r + 1):
                for y in range(c0[1] - r, c0[1] + r + 1):
                    for z in range(c0[2] - r, c0[2] + r + 1):
                        if max(abs(x - c0[0]), abs(y - c0[1]), abs(z - c0[2])) != r:
                            continue
                        for k in self.grid.get((x, y, z), ()):
                            if k in seen:
                                continue
                            seen.add(k)
                            a, b, c = self.tris[k]
                            q, bc = closest_on_tri(p, self.pts[a], self.pts[b], self.pts[c])
                            d = vlen(V(p, q))
                            if best is None or d < best[0]:
                                best = (d, q, k, bc)
            # всё, что ближе r·cell, уже просмотрено
            if best is not None and best[0] <= r * cell:
                return best
            r += 1
            if r * cell > rmax + cell:
                return best if best is not None and best[0] <= rmax else None

    def side_normal(self, k, bc):
        """Псевдонормаль в точке грани k с барицентрическими bc (грань / ребро / вершина)."""
        a, b, c = self.tris[k]
        zero = [i for i, w in enumerate(bc) if w < 1e-7]
        ids = (a, b, c)
        if len(zero) == 2:
            return self.vn[ids[3 - zero[0] - zero[1]]]
        if len(zero) == 1:
            i, j = [ids[q] for q in range(3) if q != zero[0]]
            return self.en[(min(i, j), max(i, j))]
        return self.fn[k]


# ---------------------------------------------------------------- скелет: иерархия (выведена по суставам), позы

def parent_table():
    """Родитель каждой из 122 костей скелета игрока NHL 13. Иерархии в файле нет (только обратные матрицы позы
    привязки) — выведена по положению суставов: 0 таз; 1–4 позвоночник; 5 шея, 6–47 голова и лицо (жёстко с шеей);
    48 ключица → 49 плечо → 50 скрутка плеча, 51 локоть → 52, 53 скрутки предплечья, 54 кисть → 55–78 пальцы (жёстко с
    кистью); 79–109 — то же справа; 110 бедро → 115 скрутка бедра, 111 колено → 112 голеностоп → 113 → 114; 116–121 —
    справа."""
    P = {0: -1, 1: 0, 2: 1, 3: 2, 4: 3, 5: 4}
    for i in range(6, 48):
        P[i] = 5
    for base, spine in ((48, 4), (79, 4)):
        P[base] = spine
        P[base + 1] = base
        P[base + 2] = base + 1
        P[base + 3] = base + 1
        P[base + 4] = base + 3
        P[base + 5] = base + 3
        P[base + 6] = base + 3
        for i in range(base + 7, base + 31):
            P[i] = base + 6
    for th in (110, 116):
        P[th] = 0
        P[th + 5] = th
        P[th + 1] = th
        P[th + 2] = th + 1
        P[th + 3] = th + 2
        P[th + 4] = th + 3
    return [P[i] for i in range(122)]


PARENT = parent_table()


def rot_axis(axis, deg):
    """Матрица 3×3 поворота на deg вокруг оси axis (вектор, нормируется)."""
    x, y, z = norm(axis)
    a = math.radians(deg)
    c, s, C = math.cos(a), math.sin(a), 1 - math.cos(a)
    return [[c + x * x * C, x * y * C - z * s, x * z * C + y * s],
            [y * x * C + z * s, c + y * y * C, y * z * C - x * s],
            [z * x * C - y * s, z * y * C + x * s, c + z * z * C]]


def m3mul(A, B):
    return [[sum(A[i][k] * B[k][j] for k in range(3)) for j in range(3)] for i in range(3)]


def m3v(A, v):
    return [A[0][0] * v[0] + A[0][1] * v[1] + A[0][2] * v[2],
            A[1][0] * v[0] + A[1][1] * v[1] + A[1][2] * v[2],
            A[2][0] * v[0] + A[2][1] * v[1] + A[2][2] * v[2]]


I3 = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]

# позы для проверок: {кость: [(ось в системе позы привязки, градусы), …]} — поворот вокруг сустава кости, дети — вслед.
# Левая рука — x > 0. Ось z — вперёд: +угол поднимает левую руку, −угол — правую.
POSES = {
    'bind': {},
    'arms_up': {48: [((0, 0, 1), 20)], 79: [((0, 0, 1), -20)], 49: [((0, 0, 1), 95)], 80: [((0, 0, 1), -95)],
                51: [((1, 0, 0), 30)], 82: [((1, 0, 0), 30)]},
    'arms_side': {49: [((0, 0, 1), 40)], 80: [((0, 0, 1), -40)]},
    'arms_fwd': {49: [((1, 0, 0), -70)], 80: [((1, 0, 0), -70)]},
    'arms_down': {49: [((0, 0, 1), -30)], 80: [((0, 0, 1), 30)]},
    'reach': {49: [((1, 0, 0), -45), ((0, 1, 0), -50)], 80: [((1, 0, 0), -20), ((0, 1, 0), -30)],
              2: [((0, 1, 0), -12)], 3: [((0, 1, 0), -12)]},
    'bend': {1: [((1, 0, 0), 14)], 2: [((1, 0, 0), 14)], 3: [((1, 0, 0), 14)], 4: [((1, 0, 0), 10)]},
    'twist': {1: [((0, 1, 0), 10)], 2: [((0, 1, 0), 10)], 3: [((0, 1, 0), 10)], 4: [((0, 1, 0), 8)]},
    'side_bend': {1: [((0, 0, 1), 8)], 2: [((0, 0, 1), 8)], 3: [((0, 0, 1), 8)]},
    'stride': {110: [((1, 0, 0), -60)], 116: [((1, 0, 0), 25)], 111: [((1, 0, 0), 50)]},
    'crouch': {110: [((1, 0, 0), -50)], 116: [((1, 0, 0), -50)], 111: [((1, 0, 0), 60)], 117: [((1, 0, 0), 60)],
               1: [((1, 0, 0), 10)], 2: [((1, 0, 0), 10)], 3: [((1, 0, 0), 8)]},
}
POSE_NAMES = {'bind': 'поза привязки', 'arms_up': 'руки вверх', 'arms_side': 'руки в стороны',
              'arms_fwd': 'руки вперёд', 'arms_down': 'руки вниз, к телу', 'reach': 'бросок (руки к шайбе)',
              'bend': 'наклон вперёд', 'twist': 'поворот корпуса', 'side_bend': 'наклон вбок',
              'stride': 'шаг (бедро вперёд)', 'crouch': 'присед'}


class Pose:
    """Поза: для каждой кости — аффинное отображение поза привязки → поза (M, t), по иерархии PARENT; повороты —
    вокруг суставов позы привязки skel.joints. Вершина — смешивание по своим весам (как в игре, линейное)."""

    def __init__(self, skel, spec, parent=PARENT):
        J = skel.joints
        n = len(J)
        self.M = [None] * n
        self.t = [None] * n
        order = sorted(range(n), key=lambda i: self._depth(i, parent))
        for i in order:
            R = I3
            for ax, deg in spec.get(i, ()):
                R = m3mul(rot_axis(ax, deg), R)
            # A_i(x) = J + R (x − J)
            tA = V(J[i], m3v(R, J[i]))
            p = parent[i]
            if p < 0:
                self.M[i], self.t[i] = R, tA
            else:
                Mp, tp = self.M[p], self.t[p]
                self.M[i] = m3mul(Mp, R)
                self.t[i] = vadd(m3v(Mp, tA), tp)

    @staticmethod
    def _depth(i, parent):
        d = 0
        while parent[i] >= 0:
            i = parent[i]
            d += 1
        return d

    def point(self, p, bones, weights):
        acc = [0.0, 0.0, 0.0]
        sw = 0.0
        for b, w in zip(bones, weights):
            if w <= 0:
                continue
            q = vadd(m3v(self.M[b], p), self.t[b])
            acc[0] += w * q[0]
            acc[1] += w * q[1]
            acc[2] += w * q[2]
            sw += w
        if sw <= 0:
            return list(p)
        return [c / sw for c in acc]

    def mesh(self, m, pos=None):
        pos = pos or m.pos
        return [self.point(pos[i], m.bones[i], m.weights[i]) for i in range(m.nv)]


# ---------------------------------------------------------------- сетка «как есть» (несколько подсеток: головы)

class SubMesh:
    """Простая сетка для рисования/проверок: pos, nrm, tan, uv, bones, weights, tris (как у rw4mesh.Mesh)."""

    def __init__(self, pos, nrm, tan, uv, bones, weights, tris, name=''):
        self.pos, self.nrm, self.tan, self.uv = pos, nrm, tan, uv
        self.bones, self.weights, self.tris, self.name = bones, weights, tris, name
        self.nv = len(pos)


def read_multi(data, path=''):
    """Все подсетки файла RW4 (буферы вершин и индексов — парами по порядку; объявление вершин — общее или своё у
    каждой пары по порядку) → [SubMesh]. Только для чтения (головы player_<N>: 4 подсетки)."""
    f = rm.Rw4File(data, path)
    decls = f.find(rm.TYPE_VDECL)
    vbs, ibs = f.find(rm.TYPE_VB), f.find(rm.TYPE_IB)
    shaders = f.find(rm.TYPE_SHADER)            # тип примитива подсетки — у её шейдера (по порядку, как rw4mesh.Mesh)
    out = []
    for k, (svb, sib) in enumerate(zip(vbs, ibs)):
        # объявление — с тем же шагом, что у буфера (у головы Legacy два: 32 и 36 — шапочка волос с двумя UV),
        # иначе — по порядку
        same = [d for d in decls if f.body(d)[9] == rm.u32(f.body(svb), 0x20) >> 16]
        sd = same[0] if len(same) == 1 else decls[min(k, len(decls) - 1)]
        db = f.body(sd)
        ne = db[8]
        els = [rm.Element(*struct.unpack_from('>3I', db, 16 + 12 * q)) for q in range(ne)]
        vb = f.body(svb)
        vsec = f.sections[rm.u32(vb, 0x18) >> 2]
        stride, nv = rm.u32(vb, 0x20) >> 16, rm.u32(vb, 0x24)
        vo = f.abs_off(vsec)
        ib = f.body(sib)
        isec = f.sections[rm.u32(ib, 0x18)]
        ni = rm.u32(ib, 0x20)
        idx = list(struct.unpack_from('>%dH' % ni, f.raw, f.abs_off(isec)))
        prim = rm.shader_prim(f.body(shaders[k])) if k < len(shaders) else rm.PRIM_TRIANGLESTRIP
        tris = rm.triangles(idx, prim)
        g = {e.usage: e for e in els}
        pos, nrm, tan, uv, bones, weights = [], [], [], [], [], []
        raw = f.raw
        for i in range(nv):
            b = vo + i * stride
            e = g.get(0)
            if e.type == rm.DECL_FLOAT16_4:
                pos.append([rm.half_dec(h) for h in struct.unpack_from('>3H', raw, b + e.off)])
            else:
                pos.append(list(struct.unpack_from('>3f', raw, b + e.off)))
            e = g.get(3)
            nrm.append(rm.dec3n_dec(rm.u32(raw, b + e.off)) if e is not None and e.type == rm.DECL_DEC3N
                       else [0.0, 0.0, 1.0])
            e = g.get(6)
            tan.append(rm.dec3n_dec(rm.u32(raw, b + e.off)) if e is not None and e.type == rm.DECL_DEC3N
                       else [1.0, 0.0, 0.0])
            e = g.get(5)
            if e is not None and e.type == rm.DECL_USHORT2N:
                uv.append([x / 65535.0 for x in struct.unpack_from('>2H', raw, b + e.off)])
            elif e is not None and e.type == 0x2C235F:
                uv.append([rm.half_dec(h) for h in struct.unpack_from('>2H', raw, b + e.off)])
            else:
                uv.append([0.0, 0.0])
            e = g.get(2)
            bones.append(tuple(x // 3 for x in struct.unpack_from('>4H', raw, b + e.off)) if e is not None
                         else (0, 0, 0, 0))
            e = g.get(1)
            weights.append(tuple(x / 255.0 for x in raw[b + e.off:b + e.off + 4][::-1]) if e is not None
                           else (1.0, 0.0, 0.0, 0.0))
        out.append(SubMesh(pos, nrm, tan, uv, bones, weights, tris, f'{path}#{k}'))
    return out


# ---------------------------------------------------------------- рисование игрока (превью)

class _View:
    """Вид сетки для czkit.draw_mesh: позиции/нормали/касательные (в позе), uv, треугольники."""

    def __init__(self, pos, nrm, tan, uv, tris):
        self.pos, self.nrm, self.tan, self.uv, self.tris = pos, nrm, tan, uv, tris


def posed_view(m, pose=None, pos=None):
    """Сетка (rw4mesh.Mesh или SubMesh) → _View в позе pose (нормали и касательные — смешанными поворотами костей)."""
    pos = pos or m.pos
    uv = m.uv if len(m.uv) == len(pos) else [[0.0, 0.0]] * len(pos)
    if pose is None:
        return _View(pos, m.nrm, m.tan or None, uv, m.tris)
    P, N, T = [], [], []
    for i in range(len(pos)):
        bs, ws = m.bones[i], m.weights[i]
        P.append(pose.point(pos[i], bs, ws))
        n = [0.0, 0.0, 0.0]
        t = [0.0, 0.0, 0.0]
        for b, w in zip(bs, ws):
            if w <= 0:
                continue
            nb = m3v(pose.M[b], m.nrm[i])
            n = vadd(n, vmul(nb, w))
            if m.tan:
                t = vadd(t, vmul(m3v(pose.M[b], m.tan[i]), w))
        N.append(norm(n) or m.nrm[i])
        T.append(norm(t) or (m.tan[i] if m.tan else [1.0, 0.0, 0.0]))
    return _View(P, N, T if m.tan else None, uv, m.tris)


# ---------------------------------------------------------------- открытые края; деталь как препятствие

def boundary_edges(tris):
    """Рёбра, входящие ровно в один треугольник (открытый край сетки) — по номерам вершин."""
    cnt = {}
    for a, b, c in tris:
        for i, j in ((a, b), (b, c), (c, a)):
            k = (min(i, j), max(i, j))
            cnt[k] = cnt.get(k, 0) + 1
    return {k for k, n in cnt.items() if n == 1}


def welded_tris(m):
    """Треугольники на точках сварки (rw4mesh.Weld) и представители точек: → (w, [(pa, pb, pc)], rep)."""
    w = rm.Weld(m)
    tris = [(w.point[a], w.point[b], w.point[c]) for a, b, c in w.faces]
    return w, tris, w.rep


class Obstacle:
    """Деталь (шорты, перчатки, шлем…) в позе: сетка поиска по точкам сварки и её открытые края. inside(p) —
    насколько точка p внутри детали (м, > 0 — внутри), только если ближайшая точка не на открытом крае."""

    def __init__(self, m, pos, cell=0.025):
        w, tris, rep = welded_tris(m)
        pts = [pos[rep[k]] for k in range(w.np)]
        self.grid = TriGrid(pts, tris, cell)
        self.border = boundary_edges(tris)
        self.tris = tris

    def depth(self, p, rmax=0.06):
        h = self.grid.nearest(p, rmax)
        if h is None:
            return None
        d, q, k, bc = h
        zero = [i for i, x in enumerate(bc) if x < 1e-7]
        a = self.tris[k]
        if len(zero) == 1:
            i, j = [a[t] for t in range(3) if t != zero[0]]
            if (min(i, j), max(i, j)) in self.border:
                return None
        elif len(zero) == 2:
            v = a[3 - zero[0] - zero[1]]
            if any(v in e for e in self.border):
                return None
        n = self.grid.side_normal(k, bc)
        s = dot(V(p, q), n)
        return -d if s >= 0 else d


# отрезки осей: (кость-область, сустав начала, сустав конца); для точки берётся ось её основной кости


# ---------------------------------------------------------------- точки сварки, гладкое поле сдвигов


class Points:
    """Точки сварки сетки m (позиции — по представителю), соседи по треугольникам, основная кость, часть тела."""

    def __init__(self, m, pos=None):
        pos = pos or m.pos
        self.m = m
        self.w = w = rm.Weld(m)
        self.rep = w.rep
        self.n = w.np
        self.P = [list(pos[w.rep[k]]) for k in range(w.np)]
        self.tris = [(w.point[a], w.point[b], w.point[c]) for a, b, c in w.faces]
        nb = [set() for _ in range(self.n)]
        for a, b, c in self.tris:
            nb[a].update((b, c))
            nb[b].update((a, c))
            nb[c].update((a, b))
        self.nb = [sorted(s) for s in nb]
        self.bone = [m.main_bone(w.rep[k]) for k in range(self.n)]

    def normals(self, P=None):
        P = P or self.P
        acc = [[0.0, 0.0, 0.0] for _ in range(self.n)]
        for a, b, c in self.tris:
            fn = cross(V(P[b], P[a]), V(P[c], P[a]))
            for i in (a, b, c):
                acc[i][0] += fn[0]
                acc[i][1] += fn[1]
                acc[i][2] += fn[2]
        return [norm(v) or [0.0, 0.0, 1.0] for v in acc]

    def to_vertices(self, P):
        """Позиции точек → позиции всех вершин RW (вершины вне треугольников — как были)."""
        out = [list(p) for p in self.m.pos]
        for i in range(self.m.nv):
            k = self.w.point[i]
            if k >= 0:
                out[i] = list(P[k])
        return out


def smooth_field(pts, D0, conf, lam=1.0, iters=40, fixed=None):
    """Гладкое поле сдвигов: итерации D_k = (c_k·D0_k + λ·среднее соседей) / (c_k + λ); fixed — точки с D = 0."""
    D = [list(d) for d in D0]
    n = pts.n
    for _ in range(iters):
        ND = []
        for k in range(n):
            if fixed is not None and fixed[k]:
                ND.append([0.0, 0.0, 0.0])
                continue
            nb = pts.nb[k]
            if nb:
                s = [0.0, 0.0, 0.0]
                for j in nb:
                    s[0] += D[j][0]
                    s[1] += D[j][1]
                    s[2] += D[j][2]
                avg = [s[0] / len(nb), s[1] / len(nb), s[2] / len(nb)]
            else:
                avg = D[k]
            c = conf[k]
            ND.append([(c * D0[k][q] + lam * avg[q]) / (c + lam) for q in range(3)])
        D = ND
    return D


# ---------------------------------------------------------------- другая игра серии: каталог, кости


def other_root(game):
    return os.path.join(rm.game_dir(), 'other', game)


def bone_map(skel_other, skel13, tol=0.02):
    """Кости другого скелета → кости NHL 13 по положению суставов (ближайший; при равенстве — меньший номер).
    → (map {кость: кость NHL 13}, отчёт: максимум и список далёких)."""
    out, far = {}, []
    J13 = skel13.joints
    for i, p in enumerate(skel_other.joints):
        d, j = min((vlen(V(p, q)), j) for j, q in enumerate(J13))
        out[i] = j
        if d > tol:
            far.append((i, j, round(d, 4)))
    return out, far


# ---------------------------------------------------------------- запись позиций


def write_positions(m, new_pos, eps=1e-6):
    """Позиции → в m (на месте; только сдвинутые вершины), нормали и касательные — rw4mesh.update_frames. → отчёт."""
    old = [p[:] for p in m.pos]
    moved, dmax = 0, 0.0
    for i in range(m.nv):
        if max(abs(new_pos[i][q] - old[i][q]) for q in range(3)) > eps:
            m.set_pos(i, new_pos[i])
            moved += 1
            dmax = max(dmax, vlen(V(m.pos[i], old[i])))
    frames = rm.update_frames(m, old)
    return {'moved_vertices': moved, 'max_shift_mm': round(dmax * 1000, 2), 'frames_rotated': frames}


# ---------------------------------------------------------------- превью: игрок целиком с текстурами комплекта

PREVIEW_KITS = (('PIT, дома', '1_23_0'), ('PIT, в гостях', '1_23_1'), ('TOR, дома', '1_27_4'), ('TOR, в гостях', '1_27_3'))
PREVIEW_HEAD = 10
_TX = {}


def ptex(rel, name):
    key = (rel, name) if rm.is_nhl13() else (rm.PROFILE.name, rel, name)
    if key not in _TX:
        import teamart as ta
        import kitpaint as kp
        rw = ta.Rw4(rm.source(rel), rel)
        ts = [t for t in rw.textures if name in t.name]
        if not ts:
            raise SystemExit(f'{rel}: нет текстуры {name}')
        _TX[key] = kp.Img(*kp.tex_decode(rw, ts[0], 0))
    return _TX[key]


_PM = {}


def pmesh(rel):
    key = rel if rm.is_nhl13() else (rm.PROFILE.name, rel)
    if key not in _PM:
        _PM[key] = rm.Mesh.game(rel)
    return _PM[key]


def kit_parts(kit, jersey_mesh=None, jersey_pos=None, jersey_tex=None, lod=2, sock_t=0, pant_type=0):
    """Части игрока для картинки: [(сетка, позиции или None, текстура, карта нормалей, цвет)]. Свитер —
    jersey_mesh/jersey_pos (по умолчанию — исходный jersey_0_1_2_0_1_L), текстура — комплект kit «S_A_V»
    (или jersey_tex — (cm, nm) своей раскладки)."""
    s, a, v = kit.split('_')
    jm = jersey_mesh or pmesh(f'rendering/jersey/jersey_0_{s}_2_0_1_{lod}.rx2')
    jt = jersey_tex or (ptex(f'rendering/jersey/texlib_{kit}.rx2', f'jersey_{kit}_cm'),
                        ptex(f'rendering/jersey/texlib_{kit}.rx2', f'jersey_{kit}_0_nm'))
    out = [(jm, jersey_pos, jt[0], jt[1], None),
           (pmesh(f'rendering/pant/pant_0_{pant_type}_0_{lod}.rx2'), None,
            ptex(f'rendering/pant/texlib_{kit}.rx2', f'pant_{kit}_cm'), None, None),
           (pmesh(f'rendering/sock/playersock_{sock_t}_{lod}.rx2'), None,
            ptex(f'rendering/sock/sock_{kit}_cm.rx2', 'sock_'), None, None),
           (pmesh(f'rendering/skate/playerskate_{lod}.rx2'), None,
            ptex('rendering/skate/texlib_23.rx2', 'skate_23_cm'), None, None),
           (pmesh(f'rendering/skate/skatelace_{lod}.rx2'), None,
            ptex('rendering/skate/texlib_999.rx2', 'skatelace_ccm'), None, None),
           (pmesh(f'rendering/glove/glove_{lod}.rx2'), None, None, None, (34, 34, 38)),
           (pmesh('rendering/helmet/helmet_11_2.rx2'), None, None, None, (28, 28, 32)),
           (pmesh('rendering/jersey/shirt_0_0_2.rx2'), None, None, None, (24, 24, 26))]
    if sock_t != 1:
        out.append((pmesh(f'rendering/skate/skatetongue_{sock_t}_{lod}.rx2'), None,
                    ptex('rendering/skate/texlib_23.rx2', 'skate_23_cm'), None, None))
    return out


_HEAD = {}


def head_parts():
    key = 'h' if rm.is_nhl13() else rm.PROFILE.name
    if key not in _HEAD:
        subs = read_multi(rm.source(f'rendering/player/player_{PREVIEW_HEAD}.rx2'), 'head')
        tx = ptex(f'rendering/player/texlib_{PREVIEW_HEAD}.rx2', 'head_')
        _HEAD[key] = [(sm, None, tx if sm.nv > 1000 else None, None, (60, 45, 35) if sm.nv <= 1000 else None)
                      for sm in subs]
    return _HEAD[key]


def render_player(parts, yaw, frame, w, h, pose=None, bg=(58, 60, 68, 255), with_head=True, mask_of=None):
    """Игрок (части kit_parts + голова) → Img; mask_of — номер части, чей видимый силуэт вернуть (bytearray)."""
    import czkit as cz
    cam = cz.Camera(yaw, frame, w, h)
    cv = cz.Canvas(w, h, bg)
    allp = list(parts) + (head_parts() if with_head else [])
    for k, (m, pos, tx, nm, col) in enumerate(allp):
        v = posed_view(m, pose, pos)
        cz.draw_mesh(cv, cam, v, tx, nm, color=col or (200, 200, 200))
    if mask_of is None:
        return cv.img()
    cv2 = cz.Canvas(w, h, (0, 0, 0, 255))
    for k, (m, pos, tx, nm, col) in enumerate(allp):
        v = posed_view(m, pose, pos)
        cz.draw_mesh(cv2, cam, v, None, None, color=(255, 0, 0) if k == mask_of else (0, 0, 255), flat=1.0)
    px = cv2.px
    vis = bytearray(1 if px[4 * i] > px[4 * i + 2] else 0 for i in range(w * h))
    bgm = bytearray(1 if cv2.z[i] <= -1e9 else 0 for i in range(w * h))
    return cv.img(), vis, bgm


def outline_pts(mask, bgm, w, h):
    out = []
    for y in range(1, h - 1):
        for x in range(1, w - 1):
            i = y * w + x
            if mask[i] and (bgm[i - 1] or bgm[i + 1] or bgm[i - w] or bgm[i + w] or not mask[i - 1] or not mask[i + 1]
                            or not mask[i - w] or not mask[i + w]):
                out.append((x, y))
    return out


def draw_pts(img, pts, col):
    for x, y in pts:
        o = (y * img.w + x) * 4
        img.px[o:o + 4] = bytes(col)


# ---------------------------------------------------------------- NHL 10: архивы BIG4 (имена внутри, сжатие RefPack)

NHL10_ARCS = ('rendernocache', 'rendercache', 'boot', 'player')
_N10 = {}


def _big4_index(path):
    with open(path, 'rb') as f:
        h = f.read(16)
        if h[:4] not in (b'BIG4', b'BIGF'):
            raise ValueError(f'{path}: не BIG4')
        n, hs = struct.unpack_from('>II', h, 8)
        f.seek(0)
        data = f.read(hs + 64)
    o, out = 16, {}
    for _ in range(n):
        off, size = struct.unpack_from('>II', data, o)
        o += 8
        e = data.index(b'\0', o)
        out[data[o:e].decode('latin1')] = (off, size)
        o = e + 1
    return out


def nhl10_source(rel):
    """Разжатый файл NHL 10: распакованное дерево game/other/nhl10/big/<архив>/…, кеш game/work/models/jersey10/src/
    nhl10/…, иначе — архивы диска game/other/nhl10/disc/<архив>.big (BIG4: оглавление с именами; файлы сжаты RefPack
    10 FB — playerhead.refpack_decompress)."""
    root = other_root('nhl10')
    for arc in NHL10_ARCS:
        p = os.path.join(root, 'big', arc, *rel.split('/'))
        if os.path.exists(p):
            return open(p, 'rb').read()
    cache = os.path.join(rm.models_dir(), 'jersey10', 'src', 'nhl10', *rel.split('/'))
    if os.path.exists(cache):
        return open(cache, 'rb').read()
    for arc in NHL10_ARCS:
        path = os.path.join(root, 'disc', arc + '.big')
        if not os.path.exists(path):
            continue
        if arc not in _N10:
            _N10[arc] = _big4_index(path)
        e = _N10[arc].get(rel)
        if e is None:
            continue
        with open(path, 'rb') as f:
            f.seek(e[0])
            blob = f.read(e[1])
        if blob[:2] == b'\x10\xfb':
            import playerhead as ph
            blob = ph.refpack_decompress(blob)
        os.makedirs(os.path.dirname(cache), exist_ok=True)
        open(cache, 'wb').write(blob)
        return blob
    raise SystemExit(f'NHL 10: {rel} не найден (game/other/nhl10/disc/*.big)')


def nhl10_mesh(rel):
    return rm.Mesh(nhl10_source(rel), 'nhl10:' + rel)


_SK10 = {}


def nhl10_bone_map():
    """Кости NHL 10 (123, порядок как у NHL 12) → кости NHL 13 по суставам позы привязки. Своего места нет у кости 80
    NHL 10 (перед ворота, 0; 1,614; 0,065 — у NHL 13 такой нет): она отдаётся кости 4 (верх позвоночника). У NHL
    Legacy скелет игрока — байт в байт как у NHL 13 (номера костей те же)."""
    key = 'map' if rm.is_nhl13() else (rm.PROFILE.name, 'map')
    if key not in _SK10:
        s10 = rm.Skeleton(nhl10_source(rm.SKELETON), 'nhl10:' + rm.SKELETON)
        mp, far = bone_map(s10, rm.Skeleton.game())
        mp[80] = 4
        _SK10[key], _SK10['far'] = mp, far
    return _SK10[key]


def nhl10_jersey_rel(rel13):
    """Путь свитера NHL 13 → путь того же варианта у NHL 10. Полевые: jersey_0_S_2_T_P_L → jersey_0_S_2_0_0_T_(1−P)_0_L
    (у NHL 10 флаг наплечников обратный: 0 — с наплечниками; проверено по высоте плеч и по совпадению стиля 0 до
    0,3 мм); вратари: jersey_1_S_C_0_0_L → jersey_1_S_C_0_0_0_0_0_L."""
    import re
    mm = re.match(r'rendering/jersey/jersey_(\d)_(\d)_(\d)_(\d)_(\d)_(\d)\.rx2$', rel13)
    if not mm:
        raise ValueError(rel13)
    g, s, c, t, p, lod = (int(x) for x in mm.groups())
    if g == 0:
        return f'rendering/jersey/jersey_0_{s}_2_0_0_{t}_{1 - p}_0_{lod}.rx2'
    return f'rendering/jersey/jersey_1_{s}_{c}_0_0_0_0_0_{lod}.rx2'


def jersey_rels(goalies=True):
    out = []
    for s in (0, 1):
        for t in range(4):
            for p in (0, 1):
                for lod in (2, 0, 3):
                    out.append(f'rendering/jersey/jersey_0_{s}_2_{t}_{p}_{lod}.rx2')
    if goalies:
        for s in (0, 1):
            for c in (0, 1):
                for lod in (2, 0, 3):
                    out.append(f'rendering/jersey/jersey_1_{s}_{c}_0_0_{lod}.rx2')
    return out


# посадка катания: таз наклонён вперёд, корпус — ещё вперёд, бёдра согнуты в тазобедренном (колени под корпусом),
# колени согнуты; skate_deep — ниже и глубже (разгон), skate_push — толчок одной ногой назад
POSES['skate'] = {0: [((1, 0, 0), 28)], 1: [((1, 0, 0), 8)], 2: [((1, 0, 0), 8)], 3: [((1, 0, 0), 6)],
                  4: [((1, 0, 0), -10)], 5: [((1, 0, 0), -30)],
                  110: [((1, 0, 0), -75)], 116: [((1, 0, 0), -75)], 111: [((1, 0, 0), 65)], 117: [((1, 0, 0), 65)],
                  112: [((1, 0, 0), -18)], 118: [((1, 0, 0), -18)],
                  49: [((0, 0, 1), -25), ((1, 0, 0), -35)], 80: [((0, 0, 1), 25), ((1, 0, 0), -35)]}
POSES['skate_deep'] = {0: [((1, 0, 0), 40)], 1: [((1, 0, 0), 10)], 2: [((1, 0, 0), 8)], 3: [((1, 0, 0), 6)],
                       4: [((1, 0, 0), -12)], 5: [((1, 0, 0), -38)],
                       110: [((1, 0, 0), -100)], 116: [((1, 0, 0), -100)], 111: [((1, 0, 0), 95)],
                       117: [((1, 0, 0), 95)], 112: [((1, 0, 0), -30)], 118: [((1, 0, 0), -30)],
                       49: [((0, 0, 1), -25), ((1, 0, 0), -45)], 80: [((0, 0, 1), 25), ((1, 0, 0), -45)]}
POSES['skate_push'] = {0: [((1, 0, 0), 30)], 1: [((1, 0, 0), 8)], 2: [((1, 0, 0), 8)], 3: [((1, 0, 0), 6)],
                       4: [((1, 0, 0), -10)], 5: [((1, 0, 0), -30)],
                       110: [((1, 0, 0), -85)], 111: [((1, 0, 0), 75)], 112: [((1, 0, 0), -20)],
                       116: [((1, 0, 0), -20), ((0, 0, 1), -25)], 117: [((1, 0, 0), 30)],
                       49: [((0, 0, 1), -25), ((1, 0, 0), -35)], 80: [((0, 0, 1), 25), ((1, 0, 0), -35)]}
POSE_NAMES.update({'skate': 'посадка катания', 'skate_deep': 'низкая посадка (разгон)',
                   'skate_push': 'толчок правой ногой'})


def remapped(m, mp):
    """Сетка m (другой игры) с костями, переведёнными в номера NHL 13 (mp) → SubMesh (для поз и картинок)."""
    bones = [tuple(mp.get(b, 0) for b in bs) for bs in m.bones]
    return SubMesh(m.pos, m.nrm, m.tan, m.uv, bones, m.weights, m.tris, getattr(m, 'path', ''))


# ---------------------------------------------------------------- веса заднего нижнего края свитера — от NHL 10

# область: ниже y_full — полностью веса NHL 10, к y_zero — плавно к весам NHL 13; по кругу от спины (0°) до ang_full —
# полностью, к ang_zero — плавно к NHL 13 (бока), спереди — NHL 13 без изменений
BACK = {'y_full': 1.10, 'y_zero': 1.22, 'ang_full': 75.0, 'ang_zero': 120.0}
# дальняя детализация (_3, 155 вершин): у бока крупные треугольники при повороте корпуса задевают шорты — там веса
# NHL 10 только на середине спины
BACK_FAR = {'y_full': 1.10, 'y_zero': 1.22, 'ang_full': 50.0, 'ang_zero': 80.0}
SKIN_DIST = 0.03          # точка NHL 10 для вершины без совпадения UV — не дальше, м


def back_factor(p, axis_z=0.014, cfg=BACK):
    """Доля весов NHL 10 в точке позы привязки: 1 — задний нижний край, 0 — остальной свитер."""
    fy = 1.0 - rm.smoothstep(cfg['y_full'], cfg['y_zero'], p[1])
    if fy <= 0:
        return 0.0
    ang = math.degrees(math.atan2(abs(p[0]), -(p[2] - axis_z)))     # 0 — спина, 90 — бок, 180 — грудь
    fa = 1.0 - rm.smoothstep(cfg['ang_full'], cfg['ang_zero'], ang)
    return fy * fa


def skin_dict(bones, weights, mp=None):
    d = {}
    for b, w in zip(bones, weights):
        if w > 0:
            bb = mp[b] if mp else b
            d[bb] = d.get(bb, 0.0) + w
    return d


class SkinSource:
    """Веса свитера NHL 10 (в номерах костей NHL 13) в любой точке: вершина с тем же UV (и рядом по положению) —
    её веса; иначе — ближайшая точка поверхности NHL 10 (позы привязки совпадают до долей мм), веса углов
    треугольника смешиваются барицентрически."""

    def __init__(self, m10, mp):
        self.m, self.mp = m10, mp
        self.by_uv = {(round(u * 65535), round(v * 65535)): i for i, (u, v) in enumerate(m10.uv)}
        self.grid = TriGrid(m10.pos, m10.tris, 0.03)

    def at(self, p, uv=None):
        if uv is not None:
            j = self.by_uv.get((round(uv[0] * 65535), round(uv[1] * 65535)))
            if j is not None and vlen(V(self.m.pos[j], p)) < 0.002:
                return skin_dict(self.m.bones[j], self.m.weights[j], self.mp), 'uv'
        h = self.grid.nearest(p, SKIN_DIST)
        if h is None:
            return None, 'нет'
        d, q, k, bc = h
        acc = {}
        for idx, w in zip(self.grid.tris[k], bc):
            for b, x in skin_dict(self.m.bones[idx], self.m.weights[idx], self.mp).items():
                acc[b] = acc.get(b, 0.0) + w * x
        return acc, 'поверхность'


def top4(d):
    items = sorted(((w, b) for b, w in d.items() if w > 1e-6), reverse=True)[:4]
    s = sum(w for w, _ in items) or 1.0
    return [b for _, b in items], [w / s for w, _ in items]


def transfer_back_skin(m, src, factor=back_factor):
    """Веса заднего нижнего края свитера m (NHL 13, на месте) — смесь (1 − β)·NHL 13 + β·NHL 10 (β = factor(позиция));
    у вершин в одной точке (швы UV) — одни и те же веса, чтобы в позе шов не разошёлся. → отчёт."""
    groups = {}
    for i in range(m.nv):
        groups.setdefault(tuple(m.pos[i]), []).append(i)
    changed, kinds, betas = 0, {}, []
    for pos, idx in groups.items():
        beta = factor(list(pos))
        if beta <= 1e-4:
            continue
        w10 = None
        for i in idx:
            w10, kind = src.at(list(pos), m.uv[i] if m.uv else None)
            if w10 is not None:
                break
        kinds[kind] = kinds.get(kind, 0) + len(idx)
        if w10 is None:
            continue
        w13 = skin_dict(m.bones[idx[0]], m.weights[idx[0]])
        mix = {}
        for b in set(w13) | set(w10):
            mix[b] = (1 - beta) * w13.get(b, 0.0) + beta * w10.get(b, 0.0)
        bones, weights = top4(mix)
        for i in idx:
            old = (m.bones[i], m.weights[i])
            m.set_skin(i, bones, weights)
            if (m.bones[i], m.weights[i]) != old:
                changed += 1
        betas.append(beta)
    return {'changed_vertices': changed, 'region_vertices': sum(kinds.values()), 'source': kinds,
            'full_region_points': sum(1 for b in betas if b > 0.999)}


MIRROR_BONES = {}
for _a, _b in ((48, 79), (110, 116)):
    for _k in range(31 if _a == 48 else 6):
        MIRROR_BONES[_a + _k] = _b + _k
        MIRROR_BONES[_b + _k] = _a + _k


def mirror_pose(spec):
    """Зеркальная поза (лево ↔ право): кости меняются местами, повороты вокруг x — те же, вокруг y и z — с обратным
    знаком."""
    out = {}
    for b, rots in spec.items():
        out[MIRROR_BONES.get(b, b)] = [((ax[0], ax[1], ax[2]), deg if (ax[1] == 0 and ax[2] == 0) else -deg)
                                       for ax, deg in rots]
    return out


POSES['skate_push_l'] = mirror_pose(POSES['skate_push'])
POSES['stride_r'] = mirror_pose(POSES['stride'])
POSE_NAMES.update({'skate_push_l': 'толчок левой ногой', 'stride_r': 'шаг (правое бедро вперёд)'})
# позы для поправки края против шорт: посадка катания и её варианты, присед, наклоны; шаг стоя (stride — бедро на 60°
# вперёд и на 25° назад при прямом корпусе) в поправку не входит — только в проверку: в нём и у исходного NHL 13 край
# сзади уходит в шорты до 37 мм
POSES['stride_mild'] = {110: [((1, 0, 0), -30)], 116: [((1, 0, 0), 15)], 111: [((1, 0, 0), 24)]}
POSES['stride_mild_r'] = mirror_pose(POSES['stride_mild'])
POSE_NAMES.update({'stride_mild': 'шаг стоя 30°/15°', 'stride_mild_r': 'шаг стоя 30°/15° (правой)'})
HEM_POSES = ('skate', 'skate_deep', 'skate_push', 'skate_push_l', 'crouch', 'bend', 'twist', 'side_bend', 'stride_mild',
             'stride_mild_r')
CHECK_HEM_POSES = HEM_POSES + ('stride', 'stride_r')
HEM_FIX_MAX = 0.012       # поправка края — не больше, м
HEM_Y = 1.30              # «низ свитера» для проверок и поправки — ниже этой высоты в позе привязки
HEM_MARGIN = 0.002        # край снаружи шорт — не ближе, м


def tuck_mask(m, pants):
    """Варианты с заправкой (jerseytuck ≠ 0): у них низ свитера — своя форма (заправленная часть поднята и ушла в
    шорты, по тем же UV вершины сдвинуты до 39 см), поэтому область берётся по их собственным позициям, а заправленная
    часть исключается: доля 0 — внутри шорт (заправленных, pant_0_x_1) или ближе 3 мм к их поверхности, 1 — дальше
    10 мм снаружи (висящая часть). → {позиция: доля}."""
    ob = Obstacle(pants, pants.pos)
    out = {}
    for i in range(m.nv):
        p = tuple(m.pos[i])
        if p in out or back_factor(list(p)) <= 0:
            continue
        d = ob.depth(list(p), 0.08)
        out[p] = 1.0 if d is None else rm.smoothstep(0.003, 0.010, -d)
    return out


def hem_clearance_fix(m, m_orig, pants, skel, poses=HEM_POSES, margin=HEM_MARGIN, mask=None, passes=3, log=None):
    """Вершины низа свитера m (веса уже от NHL 10), которые в позах ушли в шорты глубже, чем у исходного m_orig, —
    чуть наружу в позе привязки: сдвиг δ = (Σ w·M)ᵀ · n·(глубина + margin) по худшей позе, плавно по соседям (только
    в области mask > 0). Нормали — вслед (update_frames). → отчёт."""
    pts = Points(m)
    P0 = [list(p) for p in pts.P]
    region = [P0[k][1] < HEM_Y and (mask is None or mask(P0[k]) > 0) for k in range(pts.n)]
    pose_objs = {pn: Pose(skel, POSES[pn]) for pn in poses}
    obst = [(pn, pi, Obstacle(pm, pose_objs[pn].mesh(pm))) for pn in poses for pi, pm in enumerate(pants)]
    reps = pts.rep
    orig_depth = {}
    for pn, pi, ob in obst:
        pose = pose_objs[pn]
        for k in range(pts.n):
            if not region[k]:
                continue
            i = reps[k]
            q = pose.point(m_orig.pos[i], m_orig.bones[i], m_orig.weights[i])
            d = ob.depth(q, 0.05)
            orig_depth[(pn, pi, k)] = d if d is not None else -1.0
    total = [[0.0, 0.0, 0.0] for _ in range(pts.n)]
    fixed_pts = set()
    worst_left = 0.0
    for it in range(passes):
        corr = [[0.0, 0.0, 0.0] for _ in range(pts.n)]
        conf = [0.0] * pts.n
        bad = 0
        for pn, pi, ob in obst:
            pose = pose_objs[pn]
            for k in range(pts.n):
                if not region[k]:
                    continue
                i = reps[k]
                p = vadd(P0[k], total[k])
                q = pose.point(p, m.bones[i], m.weights[i])
                d = ob.depth(q, 0.05)
                if d is None:
                    continue
                allowed = max(-margin, orig_depth[(pn, pi, k)])  # было глубже — не хуже, чем было
                need = d - allowed
                if need <= 1e-4:
                    continue
                h = ob.grid.nearest(q, 0.06)
                if h is None:
                    continue
                n = ob.grid.side_normal(h[2], h[3])
                # δ в позе привязки: поворот обратно — транспонированная смесь поворотов костей
                Ms = [[0.0] * 3 for _ in range(3)]
                for b, w in zip(m.bones[i], m.weights[i]):
                    if w <= 0:
                        continue
                    for r in range(3):
                        for c in range(3):
                            Ms[r][c] += w * pose.M[b][r][c]
                d_pose = vmul(n, min(need + 0.0005, HEM_FIX_MAX))
                delta = [Ms[0][c] * d_pose[0] + Ms[1][c] * d_pose[1] + Ms[2][c] * d_pose[2] for c in range(3)]
                if vlen(delta) > vlen(corr[k]):
                    corr[k] = delta
                conf[k] = 1.0
                bad += 1
        if not bad:
            break
        D = smooth_field(pts, corr, [c * 3.0 for c in conf], 1.0, 6,
                         fixed=[not region[k] for k in range(pts.n)])
        for k in range(pts.n):
            if conf[k] > 0 and vlen(corr[k]) > vlen(D[k]):
                D[k] = corr[k]
            if vlen(D[k]) > 1e-6:
                t2 = vadd(total[k], D[k])
                if vlen(t2) > HEM_FIX_MAX:
                    t2 = vmul(t2, HEM_FIX_MAX / vlen(t2))
                total[k] = t2
                fixed_pts.add(k)
        if log:
            log(f'      поправка, проход {it + 1}: в шортах {bad} (вершина × поза)')
    newpos = pts.to_vertices([vadd(P0[k], total[k]) for k in range(pts.n)])
    rep = write_positions(m, newpos) if fixed_pts else {'moved_vertices': 0, 'max_shift_mm': 0.0}
    rep['fixed_points'] = len(fixed_pts)
    return rep


# ---------------------------------------------------------------- сборка

def jersey_out_dir():
    return os.path.join(rm.models_dir(), 'jersey10', 'out')


def parse_jersey(rel):
    import re
    mm = re.match(r'rendering/jersey/jersey_(\d)_(\d)_(\d)_(\d)_(\d)_(\d)\.rx2$', rel)
    return tuple(int(x) for x in mm.groups())


class MultiSource:
    """Веса NHL 10: сначала та же детализация, затем ближняя (_2)."""

    def __init__(self, srcs):
        self.srcs = srcs

    def at(self, p, uv=None):
        for s in self.srcs:
            w, kind = s.at(p, uv)
            if w is not None:
                return w, kind
        return None, 'нет'


def build_one(rel, skel=None, mp=None, fix=True, log=print):
    """Один свитер полевого игрока NHL 13: веса заднего нижнего края — от того же варианта NHL 10 (с плавным
    переходом), у вариантов с заправкой — только на висящей части; затем поправка края против шорт в позах.
    → (Mesh, отчёт)."""
    skel = skel or rm.Skeleton.game()
    mp = mp or nhl10_bone_map()
    g, s, c, t, p, lod = parse_jersey(rel)
    m = rm.Mesh.game(rel)
    m0 = rm.Mesh.game(rel)
    srcs = [SkinSource(nhl10_mesh(nhl10_jersey_rel(rel)), mp)]
    if lod != 2:
        srcs.append(SkinSource(nhl10_mesh(nhl10_jersey_rel(rel.replace(f'_{lod}.rx2', '_2.rx2'))), mp))
    cfg = BACK_FAR if lod == 3 else BACK
    if t:
        tm = tuck_mask(m, rm.Mesh.game(f'rendering/pant/pant_0_0_1_{lod}.rx2'))
        factor = (lambda q, tm=tm: back_factor(q, cfg=cfg) * tm.get(tuple(q), 0.0))
    else:
        factor = (lambda q: back_factor(q, cfg=cfg))
    rep = transfer_back_skin(m, MultiSource(srcs), factor)
    if fix:
        pants = [rm.Mesh.game(f'rendering/pant/pant_0_{pt}_{1 if t else 0}_{lod}.rx2') for pt in (0, 1)]
        rep['clearance'] = hem_clearance_fix(m, m0, pants, skel, mask=factor, log=None)
    rep['bytes_changed'] = m.bytes() != m0.bytes()
    if log:
        cl = rep.get('clearance', {})
        log(f'  {rel}: веса изменены у {rep["changed_vertices"]} вершин (область {rep["region_vertices"]}, '
            f'источник {rep["source"]}); поправка края: {cl.get("fixed_points", 0)} точек, '
            f'до {cl.get("max_shift_mm", 0)} мм')
    return m, rep


def cmd_build(args):
    out = rm.opt(args, '--out', jersey_out_dir())
    only = rm.opt(args, '--only')
    no_fix = rm.flag(args, '--no-fix')
    rels = [r for r in jersey_rels(goalies=False) if not only or any(o in r for o in only.split(','))]
    skel = rm.Skeleton.game()
    mp = nhl10_bone_map()
    import hashlib
    import time
    manifest = {'what': 'веса заднего нижнего края свитера — от NHL 10 (оттопыривается в посадке катания)',
                'back_region': BACK, 'hem_poses': list(HEM_POSES), 'margin_mm': HEM_MARGIN * 1000, 'files': {}}
    t0 = time.time()
    for rel in rels:
        m, rep = build_one(rel, skel, mp, fix=not no_fix)
        dst = os.path.join(out, *rel.split('/'))
        if rep['bytes_changed']:
            rm.write_out(out, rel, m)
            rep['sha1'] = hashlib.sha1(m.bytes()).hexdigest()
        elif os.path.exists(dst):
            os.remove(dst)
        manifest['files'][rel] = rep
    mpath = os.path.join(out, 'manifest.json')
    os.makedirs(out, exist_ok=True)
    old = {}
    if only and os.path.exists(mpath):
        old = json.load(open(mpath, encoding='utf-8')).get('files', {})
    old.update(manifest['files'])
    manifest['files'] = old
    json.dump(manifest, open(mpath, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(f'готово: {out} ({sum(1 for r in manifest["files"].values() if r.get("bytes_changed"))} файлов), '
          f'{time.time() - t0:.0f} с')


# ---------------------------------------------------------------- лист превью: посадка катания сзади и сбоку

SKATE_VIEWS = (('сзади', 180.0), ('сбоку', 90.0), ('сзади-сбоку', 140.0))
SKATE_FRAME = (-0.62, 0.50, 0.62, 1.55)


def pose_sheet(cards, notes, out_png, w=236, h=200, log=print, sheet_title='Нижний край свитера сзади — как в NHL 10'):
    """Лист: cards — [(заголовок, поза, виды [(имя, yaw)], кадр, [(подпись, parts)])]; на всех состояниях, кроме
    первого, — красный контур свитера первого (NHL 13) в той же позе и виде. Состояние (подпись, parts, игра) другой
    игры рисуется с её головой (rw4mesh.game_profile)."""
    import base64
    import teamart as ta
    outdir = os.path.dirname(out_png)
    os.makedirs(outdir, exist_ok=True)
    skel = rm.Skeleton.game()

    def uri(p):
        return 'data:image/png;base64,' + base64.b64encode(open(p, 'rb').read()).decode()
    html_cards = []
    ncols = 1
    for ci, (title, pname, views, frame, states) in enumerate(cards):
        pose = Pose(skel, POSES[pname]) if pname != 'bind' else None
        figs = []
        for vn, yaw in views:
            edge = None
            for si, st in enumerate(states):
                lab, parts = st[0], st[1]
                if si == 0:
                    img, vis, bgm = render_player(parts, yaw, frame, w, h, pose=pose, mask_of=0)
                    edge = outline_pts(vis, bgm, w, h)
                elif len(st) > 2 and st[2] != rm.PROFILE.name:
                    with rm.game_profile(st[2]):
                        img = render_player(parts, yaw, frame, w, h, pose=pose)
                    draw_pts(img, edge, (255, 70, 70, 255))
                else:
                    img = render_player(parts, yaw, frame, w, h, pose=pose)
                    draw_pts(img, edge, (255, 70, 70, 255))
                p = os.path.join(outdir, f'card{ci}_{int(yaw)}_s{si}.png')
                img.save(p)
                figs.append(f'<figure><img src="{uri(p)}"><figcaption>{lab}, {vn}</figcaption></figure>')
        ncols = max(ncols, len(views) * len(states))
        html_cards.append(f'<div class="card"><h2>{title} — {POSE_NAMES.get(pname, pname)}</h2>'
                          f'<div class="row">{"".join(figs)}</div></div>')
        log(f'  превью: {title}, {POSE_NAMES.get(pname, pname)}')
    html = ('<!doctype html><html><head><meta charset="utf-8"><style>'
            'body{margin:0;background:#26272c;color:#ddd;font:13px Segoe UI,Arial,sans-serif;padding:12px}'
            'h1{font-size:18px;margin:0 0 4px}h2{font-size:14px;margin:2px 0 6px}'
            '.card{background:#303138;padding:8px;border-radius:6px;margin-bottom:8px}'
            '.row{display:flex;gap:3px;flex-wrap:wrap}figure{margin:0}'
            'figcaption{font-size:11px;color:#aaa;text-align:center}p{margin:3px 0;font-size:12px;color:#bbb}'
            f'</style></head><body><h1>{sheet_title}</h1>'
            + ''.join(f'<p>{n}</p>' for n in notes) + ''.join(html_cards) + '</body></html>')
    width = 24 + 16 + ncols * (w + 3)
    height = 56 + 20 * len(notes) + len(cards) * (h + 58) + 30
    ta.render_html(html, out_png, width, height)
    log(f'  лист: {out_png}')


def nhl10_parts(kit, rel13, mp):
    """Игрок с свитером NHL 10 (его позиции и веса, кости — в номерах NHL 13) и текстурами NHL 13 (UV те же)."""
    jm = remapped(nhl10_mesh(nhl10_jersey_rel(rel13)), mp)
    return kit_parts(kit, jersey_mesh=jm)


def other_game_preview(out, png, with13=True):
    """Лист другой игры (Legacy): её свитер / её свитер с модом / NHL 13 с модом (готовые файлы NHL 13 из
    game/work/models/jersey10/out, с текстурами, шортами и головой NHL 13) — те же карточки, что у NHL 13."""
    gname = rm.PROFILE.title
    out13 = os.path.join(rm.nhl13_models_dir(), 'jersey10', 'out')
    with13 = with13 and os.path.isdir(out13)

    def result(rel, d):
        p = os.path.join(d, *rel.split('/'))
        return rm.Mesh.load(p) if os.path.exists(p) else rm.Mesh.game(rel)

    def states(kit, rel, pants=None):
        ps = [(f'{gname}, оригинал', kit_parts(kit, jersey_mesh=rm.Mesh.game(rel) if pants else None)),
              (f'{gname} с модом', kit_parts(kit, jersey_mesh=result(rel, out)))]
        if with13:
            with rm.game_profile('nhl13'):
                p13 = kit_parts(kit, jersey_mesh=result(rel, out13))
                pr13 = rm.Mesh.game(pants) if pants else None
            ps.append(('NHL 13 с модом', p13, 'nhl13'))
        if pants:
            pr = rm.Mesh.game(pants)
            for k, st in enumerate(ps):
                parts = list(st[1])
                parts[1] = (pr13 if len(st) > 2 else pr, None, parts[1][2], None, None)
                ps[k] = (st[0], parts) + tuple(st[2:])
        return ps
    base = 'rendering/jersey/jersey_0_1_2_0_1_2.rx2'
    cards = []
    for lab, kit in PREVIEW_KITS:
        cards.append((lab, 'skate', SKATE_VIEWS, SKATE_FRAME, states(kit, base)))
    kit = PREVIEW_KITS[3][1]
    for pn in ('skate_deep', 'skate_push', 'stride_mild'):
        cards.append((PREVIEW_KITS[3][0], pn, SKATE_VIEWS, SKATE_FRAME, states(kit, base)))
    cards.append((PREVIEW_KITS[3][0] + ', стоя', 'bind', (('сзади', 180.0), ('сбоку', 90.0)), (-0.62, 0.62, 0.62, 1.5),
                  states(kit, base)))
    for t in (1, 3):
        cards.append((f'{PREVIEW_KITS[3][0]}, заправка {t}', 'skate', SKATE_VIEWS[:2], SKATE_FRAME,
                      states(kit, f'rendering/jersey/jersey_0_1_2_{t}_1_2.rx2', 'rendering/pant/pant_0_0_1_2.rx2')))
    man = os.path.join(out, 'manifest.json')
    nfiles = 0
    if os.path.exists(man):
        nfiles = sum(1 for r in json.load(open(man, encoding='utf-8'))['files'].values() if r.get('bytes_changed'))
    notes = [f'{gname}: сетки свитеров и скелет — байт в байт как у NHL 13, веса заднего нижнего края — от NHL 10 '
             '(как в NHL 13); шорты дальней детализации у Legacy — те же вершины, но полосы, поэтому _3 пересобраны.',
             f'Красный контур — свитер «{gname}, оригинал» в той же позе. «NHL 13 с модом» — готовые свитера NHL 13 '
             '(game/work/models/jersey10/out) с текстурами, шортами и головой NHL 13.',
             f'Файлов: {nfiles} (16 вариантов полевых × 3 детализации, без изменений не пишутся); вратарские — без '
             'изменений.']
    pose_sheet(cards, notes, png, sheet_title=f'Нижний край свитера сзади — как в NHL 10: {gname}')


def cmd_preview(args):
    out = rm.opt(args, '--out', jersey_out_dir())
    png = rm.opt(args, '--png', os.path.join(rm.models_dir(), 'preview', 'jersey10', 'sheet.png'))
    if not rm.is_nhl13():
        return other_game_preview(out, png, with13=not rm.flag(args, '--no-nhl13'))
    mp = nhl10_bone_map()
    base = 'rendering/jersey/jersey_0_1_2_0_1_2.rx2'

    def result(rel):
        p = os.path.join(out, *rel.split('/'))
        return rm.Mesh.load(p) if os.path.exists(p) else build_one(rel, log=None)[0]
    res = result(base)
    cards = []
    for lab, kit in PREVIEW_KITS:
        cards.append((lab, 'skate', SKATE_VIEWS, SKATE_FRAME,
                      [('NHL 13', kit_parts(kit)), ('NHL 10', nhl10_parts(kit, base, mp)),
                       ('итог', kit_parts(kit, jersey_mesh=res))]))
    kit = PREVIEW_KITS[3][1]
    for pn in ('skate_deep', 'skate_push', 'stride_mild'):
        cards.append((PREVIEW_KITS[3][0], pn, SKATE_VIEWS, SKATE_FRAME,
                      [('NHL 13', kit_parts(kit)), ('NHL 10', nhl10_parts(kit, base, mp)),
                       ('итог', kit_parts(kit, jersey_mesh=res))]))
    cards.append((PREVIEW_KITS[3][0] + ', стоя', 'bind', (('сзади', 180.0), ('сбоку', 90.0)), (-0.62, 0.62, 0.62, 1.5),
                  [('NHL 13', kit_parts(kit)), ('итог', kit_parts(kit, jersey_mesh=res))]))
    for t in (1, 3):
        rel = f'rendering/jersey/jersey_0_1_2_{t}_1_2.rx2'
        pr = rm.Mesh.game(f'rendering/pant/pant_0_0_1_2.rx2')
        p13 = kit_parts(kit, jersey_mesh=rm.Mesh.game(rel))
        p10 = kit_parts(kit, jersey_mesh=remapped(nhl10_mesh(nhl10_jersey_rel(rel)), mp))
        pres = kit_parts(kit, jersey_mesh=result(rel))
        for ps in (p13, p10, pres):
            ps[1] = (pr, None, ps[1][2], None, None)
        cards.append((f'{PREVIEW_KITS[3][0]}, заправка {t}', 'skate', SKATE_VIEWS[:2], SKATE_FRAME,
                      [('NHL 13', p13), ('NHL 10', p10), ('итог', pres)]))
    man = os.path.join(out, 'manifest.json')
    nfiles = 0
    if os.path.exists(man):
        nfiles = sum(1 for r in json.load(open(man, encoding='utf-8'))['files'].values() if r.get('bytes_changed'))
    notes = ['Сетка, UV, позиции и индексы — NHL 13; веса заднего нижнего края — от NHL 10 (у NHL 13 край на 30–60 % '
             'привязан к скруткам бёдер и в посадке облегает зад, у NHL 10 — к тазу и позвоночнику и отстаёт). '
             f'Полностью — ниже {BACK["y_full"]:.2f} м и до {BACK["ang_full"]:.0f}° от спины, плавно — до '
             f'{BACK["y_zero"]:.2f} м и {BACK["ang_zero"]:.0f}°; спереди и выше — как было.',
             'Красный контур — свитер NHL 13 в той же позе. «NHL 10» — сетка и веса свитера NHL 10 (кости переведены '
             'в номера NHL 13), текстура NHL 13 (раскладка UV та же).',
             f'Файлов: {nfiles} (16 вариантов полевых × 3 детализации); вратарские — без изменений (у NHL 10 и NHL 13 '
             'веса края почти одинаковые).']
    pose_sheet(cards, notes, png)


def cmd_info(args):
    mp = nhl10_bone_map()
    print('кости NHL 10 → NHL 13 далёкие:', _SK10.get('far'))
    for rel in jersey_rels():
        r10 = nhl10_jersey_rel(rel)
        a, b = rm.Mesh.game(rel), nhl10_mesh(r10)
        print(f'{rel} ({a.nv}) ↔ {r10} ({b.nv}, шаг {b.stride})')


def check_file(rel, path, skel, poses=CHECK_HEM_POSES):
    """Проверка одного собранного свитера против исходного: перекодирование байт в байт, что поменялось (только
    веса и позиции низа; UV, индексы — как были), швы (вершины в одной точке — одни веса, в позах не расходятся),
    край против шорт в позах (новые проходы глубже 1 мм), растяжение рёбер низа в позах против исходного."""
    g, s_, c, t, p, lod = parse_jersey(rel)
    m0, m1 = rm.Mesh.game(rel), rm.Mesh.load(path)
    rep = {'reencode': rm.reencode_check(m1) or 'ok', 'layout_ok': m1.layout_ok()}
    rep['uv_same'] = m0.uv == m1.uv and m0.indices == m1.indices and m0.nv == m1.nv
    moved = [i for i in range(m0.nv) if m0.pos[i] != m1.pos[i]]
    reskin = [i for i in range(m0.nv) if (m0.bones[i], m0.weights[i]) != (m1.bones[i], m1.weights[i])]
    rep['moved'] = len(moved)
    rep['moved_above_hem'] = sum(1 for i in moved if m0.pos[i][1] >= HEM_Y)
    rep['reskinned'] = len(reskin)
    rep['reskinned_above'] = sum(1 for i in reskin if m0.pos[i][1] >= BACK['y_zero'])
    rep['max_shift_mm'] = round(max([vlen(V(m0.pos[i], m1.pos[i])) for i in moved] or [0.0]) * 1000, 2)
    groups = {}
    for i in range(m1.nv):
        groups.setdefault(tuple(m0.pos[i]), []).append(i)
    rep['seam_weight_mismatch'] = sum(1 for gr in groups.values()
                                      if len({(m1.bones[i], m1.weights[i]) for i in gr}) > 1)
    pants = [rm.Mesh.game(f'rendering/pant/pant_0_{pt}_{1 if t else 0}_{lod}.rx2') for pt in (0, 1)]
    edges = set()
    for a, b, cc in m0.tris:
        for i, j in ((a, b), (b, cc), (cc, a)):
            if m0.pos[i][1] < HEM_Y and m0.pos[j][1] < HEM_Y:
                edges.add((min(i, j), max(i, j)))
    rep['poses'] = {}
    seam_split = 0.0
    for pn in poses:
        pose = Pose(skel, POSES[pn])
        q0, q1 = pose.mesh(m0), pose.mesh(m1)
        for gr in groups.values():
            for i in gr[1:]:
                seam_split = max(seam_split, vlen(V(q1[i], q1[gr[0]])))
        row = {}
        for pi, pm in enumerate(pants):
            ob = Obstacle(pm, pose.mesh(pm))
            new, worst = 0, 0.0
            for i in range(m1.nv):
                if m0.pos[i][1] >= HEM_Y:
                    continue
                if vlen(V(q1[i], q0[i])) < 0.002:
                    continue                      # в позе почти там же, где у исходного, — не новое
                d1, d0 = ob.depth(q1[i], 0.05), ob.depth(q0[i], 0.05)
                d1 = -1.0 if d1 is None else d1
                d0 = -1.0 if d0 is None else d0
                if d1 > max(0.0, d0) + 0.001:
                    new += 1
                    worst = max(worst, d1 - max(0.0, d0))
            row[f'pant_0_{pi}'] = (new, round(worst * 1000, 1))
        # растяжение ребра в позе против позы привязки — у итога и у исходного; замечание — итог тянется сильнее
        # 1,6 раза (сжимается сильнее чем вдвое) и заметно сильнее исходного (×1,25)
        st_bad, st_worst = 0, 1.0
        for i, j in edges:
            b0, b1 = vlen(V(m0.pos[i], m0.pos[j])), vlen(V(m1.pos[i], m1.pos[j]))
            if b0 < 1e-5 or b1 < 1e-5:
                continue
            r0 = vlen(V(q0[i], q0[j])) / b0
            r1 = vlen(V(q1[i], q1[j])) / b1
            if (r1 > max(1.6, r0 * 1.25)) or (r1 < min(0.5, r0 / 1.25)):
                st_bad += 1
                st_worst = max(st_worst, r1 if r1 > 1 else 1 / r1)
        row['stretch'] = (st_bad, round(st_worst, 3))
        rep['poses'][pn] = row
    rep['seam_split_mm'] = round(seam_split * 1000, 3)
    return rep


def cmd_check(args):
    out = rm.opt(args, '--out', jersey_out_dir())
    only = rm.opt(args, '--only')
    skel = rm.Skeleton.game()
    res, bad = {}, 0
    for rel in jersey_rels(goalies=False):
        if only and not any(o in rel for o in only.split(',')):
            continue
        path = os.path.join(out, *rel.split('/'))
        if not os.path.exists(path):
            print(f'  {rel}: нет файла (без изменений)')
            continue
        r = check_file(rel, path, skel)
        res[rel] = r
        worst = {pn: v for pn, v in r['poses'].items()
                 if any(x[0] for k, x in v.items() if k.startswith('pant')) or v['stretch'][0]}
        flag = (r['reencode'] != 'ok' or not r['layout_ok'] or not r['uv_same'] or r['moved_above_hem']
                or r['reskinned_above'] or r['seam_weight_mismatch'] or r['seam_split_mm'] > 0.01
                or any(v[k][1] > 3.0 for pn, v in worst.items() for k in v if k.startswith('pant')
                       and pn not in ('stride', 'stride_r')))
        bad += bool(flag)
        print(f'  {rel}: сдвинуто {r["moved"]} (до {r["max_shift_mm"]} мм), веса — {r["reskinned"]}; швы: '
              f'{r["seam_weight_mismatch"]} / {r["seam_split_mm"]} мм; '
              + ('; '.join(f'{pn}: ' + ', '.join(f'{k} {v[0]}/{v[1]}' for k, v in row.items())
                           for pn, row in worst.items()) or 'в позах — как у NHL 13')
              + ('  ← ПРОВЕРИТЬ' if flag else ''))
    json.dump(res, open(os.path.join(out, 'check.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(f'итог: {"замечаний нет" if not bad else f"{bad} файлов проверить"} (резкий шаг стоя stride — справочно)')


def main():
    args = rm.take_game(sys.argv[1:])
    if not args:
        print(__doc__)
        return
    cmd = args.pop(0)
    if cmd == 'build':
        cmd_build(args)
    elif cmd == 'check':
        cmd_check(args)
    elif cmd == 'preview':
        cmd_preview(args)
    elif cmd == 'info':
        cmd_info(args)
    else:
        print(__doc__)
        sys.exit(2)


if __name__ == '__main__':
    main()
