"""Форма NHL 24 на сетке Edge Legacy «по элементам» — подход 19.10.2026 (MIN дом и выезд, по просьбе пользователя).

Гибрид (fb.jersey_hybrid: Edge + кусок сетки adidas) давал волны и лесенки: текстура переносилась с одной поверхности
на другую по ближайшей точке, поверхности расходятся на мм–см, и линии рисунка гуляют вслед. Здесь — одна сетка:

1. Сетка — копия Edge (стиль 1, установленная у пользователя), слегка изогнутая: перед ворота из глубокого V поднят
   до неглубокого выреза adidas (край ворота — к краю ворота NHL 24 по углу вокруг шеи; подворот — вместе с краем,
   грудь ниже — плавно). Треугольники и развёртка Edge — те же (карты номеров Legacy работают как есть).
2. Рисунок — по гладким координатам на самой сетке Edge, а не по ближайшей точке: у ворота — (угол θ вокруг шеи,
   расстояние от края ворота), туловище — (θ вокруг оси тела, высота), низ — (угол, высота над краем низа, fb.hem).
   Ровная у NHL 24 линия остаётся ровной.
3. Эмблемы (герб, нашивки, щит NHL) — наклейками (fb.kit_hybrid), как у форм NHL 24 на Edge.

  python -m fb.edge_kit build [--out DIR] [--style 0]   # сетки jersey_* → DIR/rendering/jersey/
  python -m fb.edge_kit preview OUT.png                  # ворот: Edge | изогнутая копия | NHL 24 (шашки)
"""
import argparse
import os
import sys

import numpy as np

from . import kit3d
from . import jersey_mesh as J
from . import jersey_hybrid as Hy
from .cas import REPO

sys.path.insert(0, os.path.join(REPO, "tools"))
import rw4mesh as rw  # noqa: E402

WORK = os.path.join(REPO, "game", "work", "nhl24", "edgekit")
OUT = os.path.join(REPO, "game", "work", "legacy-data", "models", "edgekit")

LIFT_TH = (40.0, 88.0)             # град: край ворота — как у adidas до 40° от середины переда, к 88° — как у Edge
LIFT_R = 0.075                     # м от края ворота вниз по груди: изгиб сходит на нет
SKATERS = [(t, p) for t in range(4) for p in range(2)]


def collar_target(zc, th, n24_ring):
    """Край ворота NHL 24 по углу: (r, y) в точках th (линейно по кругу)."""
    P = n24_ring
    t = Hy.theta_of(P, zc)
    r = np.hypot(P[:, 0], P[:, 2] - zc)
    o = np.argsort(t)
    xp = np.concatenate([t[o] - 360, t[o], t[o] + 360])
    return np.interp(th, xp, np.tile(r[o], 3)), np.interp(th, xp, np.tile(P[o, 1], 3))


def n24_ring_for(t, p, lod):
    """Край ворота NHL 24 (наружная оболочка) того же кроя — по позициям сетки NHL 24 (без подгонки к Edge)."""
    from scipy.sparse.csgraph import connected_components
    n24 = J.nhl24(J.N24.format(tuck=J.TUCK_OF[t], size=J.SIZE_OF[p], lod=J.LODS[lod]))
    w = Hy.Welded(n24)
    _, comp = connected_components(w.A, directed=False)
    main = np.bincount(comp).argmax()
    bnd = w.boundary()
    ring = w.neck(bnd[comp[bnd] == main])
    return Hy.ring_polyline(w, ring, k=4)


def collar_edge(w, band, lip, zc, win=3.0, gap=25.0):
    """Край ворота: сгиб (рёбра подворота и наружного слоя), сглаженный по углу; где сгиба нет на дуге больше gap° —
    губа (у ближней сетки вратаря подворот только спереди, ±100°: сглаживание там давало точку (0, 0, 0) под углом
    0° — сдвиг к краю NHL 24 «поднимал» перед на 1,6 м)."""
    fold = Hy.fold_polyline(w, band, k=1)
    lp = Hy.lip_polyline(lip)
    if fold is None:
        pts = lp
    else:
        tf, tl = Hy.theta_of(fold, zc), Hy.theta_of(lp, zc)
        far = np.abs(((tl[:, None] - tf[None, :] + 180) % 360) - 180).min(1) > gap / 2
        pts = np.vstack([fold, lp[far]])
    return Hy.smooth_curve(pts, zc, win=win)


def deform(E, ring_n24, info=None, shift=None):
    """Копия сетки Edge E с поднятым передом ворота. -> (сетка, сводка). Узлы края ворота (сгиб наружного слоя и
    подворота) — к краю NHL 24 с тем же углом, с весом w(θ) (LIFT_TH); подворот — тем же сдвигом, что и край над
    ним; наружный слой ниже — тем же сдвигом, тающим к LIFT_R от края. shift (вместо ring_n24): θ → (dr, dy) края —
    готовый сдвиг (вратарь: как у полевого, от своего края). Сдвиг края — в deform.last_shift (θ, dr, dy)."""
    info = {} if info is None else info
    w = Hy.Welded(E)
    ring = w.neck()
    zc = float(w.P[ring, 2].mean())
    band, lip = Hy.edge_layers(w, ring, zc)
    edge = collar_edge(w, band, lip, zc)
    th = Hy.theta_of(w.P, zc)
    # сдвиг края по углу: край Edge (сглаженный сгиб) → край NHL 24
    te = Hy.theta_of(edge, zc)
    re = np.hypot(edge[:, 0], edge[:, 2] - zc)
    if shift is None:
        rt, yt = collar_target(zc, te, ring_n24)
        w_e = Hy.smooth((LIFT_TH[1] - np.abs(te)) / (LIFT_TH[1] - LIFT_TH[0]))
        dr_e, dy_e = (rt - re) * w_e, (yt - edge[:, 1]) * w_e
    else:
        dr_e, dy_e = shift(te)
    deform.last_shift = (te, dr_e, dy_e)
    o = np.argsort(te)
    xp = np.concatenate([te[o] - 360, te[o], te[o] + 360])
    dr = np.interp(th, xp, np.tile(dr_e[o], 3))
    dy = np.interp(th, xp, np.tile(dy_e[o], 3))
    d = Hy.ring_dist(w.P, edge)
    fall = np.where(band, 1.0, 1.0 - Hy.smooth(d / LIFT_R))
    ang = np.radians(th)
    D = np.stack([dr * np.sin(ang), dy, dr * np.cos(ang)], -1) * fall[:, None]
    P1 = w.P + D
    N0 = J.node_normals(w.P, w.T, w.n)
    N1 = J.node_normals(P1, w.T, w.n)
    out = dict(E)
    out["pos"] = P1[w.g]
    out["nrm"] = kit3d._unit(J.rotate_onto(kit3d._unit(E["nrm"]), N0[w.g], N1[w.g]))
    fn0 = np.cross(w.P[w.T[:, 1]] - w.P[w.T[:, 0]], w.P[w.T[:, 2]] - w.P[w.T[:, 0]])
    fn1 = np.cross(P1[w.T[:, 1]] - P1[w.T[:, 0]], P1[w.T[:, 2]] - P1[w.T[:, 0]])
    info.update(zc=round(zc, 4), lift_front_cm=round(float(dy_e[np.argmin(np.abs(te))] * 100), 2),
                in_front_cm=round(float(-dr_e[np.argmin(np.abs(te))] * 100), 2),
                flipped=int(((fn0 * fn1).sum(1) <= 0).sum()), moved=int((np.linalg.norm(D, axis=1) > 1e-4).sum()))
    return out, info


def load(t, p, lod):
    rel = J.skater_rel(t, p, lod, 1)
    _, E = J.legacy(rel)
    return E


# ---------------------------------------------------------------- своя развёртка переда ворота (остров в углу)

# Перед ворота у развёртки Edge — 2,4–3 мм на тексель (у груди 1,5, у NHL 24 0,8): кромка, вставка и щит там
# размывались, края — «бахромой» (пользователь, 19.10: «вот тут прям говно» — у щита). Наружный слой переда ворота
# (до ISL_D от края ворота, |θ| < ISL_TH, и столбец шнуровки) получает свою развёртку — конформную (LSCM) по
# изогнутой сетке, в пустом верхнем левом углу текстуры (там нет треугольников ни одной сетки стиля 1 и зон карты
# номеров). Прежнее место в атласе больше не используется. Для прочих сеток (детализации, заправка, вратари — у всех
# та же раскладка развёртки) остров переносится по прежним UV (uv0).
ISL_ANCHOR_NEAR = 0.012            # м от сгиба ворота: ближе — не якорь
ISL_ANCHOR_TH = 35.0               # град: спереди посередине — якоря только дальше ISL_ANCHOR_D
ISL_ANCHOR_D = 0.045               # м от сгиба ворота: ближе — край острова не якорь решётки плетения (у ворота
#                                    развёртка Edge искажена — решётка шла веером)
ISL_FADE_PX = 10.0                 # текселей острова: у края — плетение прежнего места, внутрь — своё
ISL_CHEST_MM = 1.49                # мм на тексель у груди (плетение Edge — в этом масштабе)
ISL_FOLD_SIGMA = 8.0               # текселей: складки острова — только крупные
ISL_D = 0.075                      # м от края ворота (вся зона изгиба LIFT_R: за ней плетение Edge не растянуто —
#                                    край острова не виден)
ISL_TH = 88.0                      # град вокруг шеи (как LIFT_TH)
ISL_LACE = (0.048, 1.540)          # |x| и низ столбца шнуровки (м): вся планка — в острове (граница острова шла
#                                    по низу планки и нижнему шнурку: зубцы рельефа и цвета, 19.10; было 0,042, 1,57)
ISL_BOX = (0.006, 0.006, 0.252, 0.274)   # u0, v0, u1, v1 — куда класть остров (угол атласа)


def lscm(P, T):
    """Конформная развёртка (Lévy 2002) треугольной сетки-диска P (n,3), T (m,3) -> UV (n,2), масштаб произвольный."""
    import scipy.sparse as sp
    import scipy.sparse.linalg as sla
    n = len(P)
    rows, cols, vals = [], [], []
    for k, (a, b, c) in enumerate(T):
        e1, e2 = P[b] - P[a], P[c] - P[a]
        l1 = np.linalg.norm(e1)
        if l1 < 1e-12:
            continue
        x1, y1 = 0.0, 0.0
        x2, y2 = l1, 0.0
        x3 = float(e2 @ e1) / l1
        y3 = float(np.linalg.norm(np.cross(e1, e2))) / l1
        dT = abs(x2 * y3)
        if dT < 1e-14:
            continue
        s = 1.0 / np.sqrt(dT)
        W = [((x3 - x2), (y3 - y2)), ((x1 - x3), (y1 - y3)), ((x2 - x1), (y2 - y1))]
        for j, v in enumerate((a, b, c)):
            wr, wi = W[j][0] * s, W[j][1] * s
            # Re: wr*u - wi*v ; Im: wi*u + wr*v
            rows += [2 * k, 2 * k, 2 * k + 1, 2 * k + 1]
            cols += [v, n + v, v, n + v]
            vals += [wr, -wi, wi, wr]
    A = sp.coo_matrix((vals, (rows, cols)), shape=(2 * len(T), 2 * n)).tocsc()
    # закрепить две дальние вершины границы
    from scipy.spatial.distance import pdist, squareform
    bnd = np.unique(T)
    i0 = bnd[0]
    i1 = bnd[np.argmax(np.linalg.norm(P[bnd] - P[i0], axis=1))]
    i0 = bnd[np.argmax(np.linalg.norm(P[bnd] - P[i1], axis=1))]
    L = float(np.linalg.norm(P[i1] - P[i0]))
    fixed = {i0: (0.0, 0.0), i1: (L, 0.0)}
    fidx = [i0, n + i0, i1, n + i1]
    fval = np.array([0.0, 0.0, L, 0.0])
    free = np.setdiff1d(np.arange(2 * n), fidx)
    rhs = -A[:, fidx] @ fval
    x = sla.lsqr(A[:, free], rhs, atol=1e-12, btol=1e-12, iter_lim=20000)[0]
    out = np.zeros(2 * n)
    out[free] = x
    out[fidx] = fval
    return np.stack([out[:n], out[n:]], -1)


def island_region(M):
    """Треугольники острова на изогнутой сетке M (наружный слой переда ворота). -> маска треугольников."""
    w = Hy.Welded(M)
    ring = w.neck()
    zc = float(w.P[ring, 2].mean())
    band, lip = Hy.edge_layers(w, ring, zc)
    fold = Hy.fold_polyline(w, band)
    edge = Hy.smooth_curve(fold if fold is not None else Hy.lip_polyline(lip), zc, win=2.0)
    c = M["pos"][M["tri"]].mean(1)
    th = Hy.theta_of(c, zc)
    d = Hy.ring_dist(c, edge)
    tb = band[w.g[M["tri"]]].all(1)
    sel = (~tb) & (c[:, 2] > zc) & (((d < ISL_D) & (np.abs(th) < ISL_TH)) |
                                    ((np.abs(c[:, 0]) < ISL_LACE[0]) & (c[:, 1] > ISL_LACE[1])))
    # одна связная часть (без островков)
    import scipy.sparse as sp
    from scipy.sparse.csgraph import connected_components
    T = M["tri"][sel]
    g = w.g[T]
    e = np.concatenate([g[:, [0, 1]], g[:, [1, 2]]])
    _, lab = connected_components(sp.coo_matrix((np.ones(len(e)), (e[:, 0], e[:, 1])), shape=(w.n, w.n)),
                                  directed=False)
    tl = lab[g[:, 0]]
    keep = tl == np.bincount(tl).argmax()
    out = np.zeros(len(M["tri"]), bool)
    out[np.nonzero(sel)[0][keep]] = True
    return out


def split_island(M, sel, isl_uv_of):
    """Сетка M с треугольниками sel на новой развёртке: их вершины — копии (позиция, нормаль, кости те же), UV —
    isl_uv_of(индексы вершин M) ; прежние UV всех вершин — в "uv0". Неиспользуемые вершины — убраны."""
    T = M["tri"]
    isl_v = np.unique(T[sel])
    n = len(M["pos"])
    new_idx = np.full(n, -1, np.int64)
    new_idx[isl_v] = n + np.arange(len(isl_v))
    keys = [k for k, v in M.items() if isinstance(v, np.ndarray) and len(v) == n and k != "tri"]
    out = {k: np.concatenate([M[k], M[k][isl_v]]) for k in keys}
    uv_isl = isl_uv_of(isl_v)
    out["uv0"] = np.concatenate([M.get("uv0", M["uv"]), M.get("uv0", M["uv"])[isl_v]])
    out["uv"] = np.concatenate([M["uv"], uv_isl])
    tri = T.copy()
    tri[sel] = new_idx[T[sel]]
    used = np.unique(tri)
    remap = np.full(len(out["pos"]), -1, np.int64)
    remap[used] = np.arange(len(used))
    for k in list(out.keys()):
        out[k] = out[k][used]
    out["tri"] = remap[tri]
    out["island"] = np.zeros(len(used), bool)
    out["island"][remap[n + np.arange(len(isl_v))]] = True
    for k, v in M.items():
        if k not in out:
            out[k] = v
    return out


class Island:
    """Остров развёртки переда ворота: строится на сетке-образце (ближняя детализация, t0 p1) и переносится на любую
    сетку с той же раскладкой Edge — по прежним UV."""

    def __init__(self, M):
        sel = island_region(M)
        T = M["tri"][sel]
        v = np.unique(T)
        loc = np.full(len(M["pos"]), -1, np.int64)
        loc[v] = np.arange(len(v))
        # сварка по позиции внутри острова (дубли вершин по швам нормалей)
        w = Hy.Welded({"pos": M["pos"][v], "tri": loc[T], "uv": M["uv"][v], "nrm": M["nrm"][v]})
        uvw = lscm(w.P, w.T)
        uv = uvw[w.g]
        # поворот: длинная ось — по u; «верх» (к вороту) — вверх развёртки (−v)
        c0 = uv - uv.mean(0)
        evals, evecs = np.linalg.eigh(np.cov(c0.T))
        R = evecs[:, ::-1].T
        uv = c0 @ R.T
        y3 = M["pos"][v, 1]
        if np.corrcoef(uv[:, 1], y3)[0, 1] > 0:          # выше на свитере — меньше v
            uv[:, 1] *= -1
        x3 = M["pos"][v, 0]
        if np.corrcoef(uv[:, 0], x3)[0, 1] < 0:          # лево-право как на развёртке Edge спереди (+x — к +u)
            uv[:, 0] *= -1
        lo, hi = uv.min(0), uv.max(0)
        bw, bh = ISL_BOX[2] - ISL_BOX[0], ISL_BOX[3] - ISL_BOX[1]
        k = min(bw / (hi[0] - lo[0]), bh / (hi[1] - lo[1]))
        uv = (uv - lo) * k + np.array([ISL_BOX[0], ISL_BOX[1]])
        self.template_uv0 = M["uv"].copy()
        self.template_tri = M["tri"]
        self.sel = sel
        self.isl_uv = np.zeros((len(M["pos"]), 2))
        self.isl_uv[v] = uv
        # плотность: мм на тексель (1024)
        a3 = 0.5 * np.linalg.norm(np.cross(M["pos"][T[:, 1]] - M["pos"][T[:, 0]], M["pos"][T[:, 2]] - M["pos"][T[:, 0]]),
                                  axis=1).sum()
        U = self.isl_uv[T] * 1024
        a2 = 0.5 * np.abs((U[:, 1, 0] - U[:, 0, 0]) * (U[:, 2, 1] - U[:, 0, 1]) -
                          (U[:, 2, 0] - U[:, 0, 0]) * (U[:, 1, 1] - U[:, 0, 1])).sum()
        self.mm_per_texel = float(np.sqrt(a3 / a2) * 1000)
        U0 = M["uv"][T] * 1024
        a20 = 0.5 * np.abs((U0[:, 1, 0] - U0[:, 0, 0]) * (U0[:, 2, 1] - U0[:, 0, 1]) -
                           (U0[:, 2, 0] - U0[:, 0, 0]) * (U0[:, 1, 1] - U0[:, 0, 1])).sum()
        self.mm_per_texel_before = float(np.sqrt(a3 / a20) * 1000)
        # поиск по прежним UV: растр треугольников образца
        self.S = 2048
        self.tid, self.bar = kit3d.raster_uv({"uv": M["uv"], "tri": M["tri"]}, self.S)
        from scipy.spatial import cKDTree
        st = np.nonzero(sel)[0]
        self.sel_tris = st
        self.kd = cKDTree(M["uv"][M["tri"][st]].mean(1))

    def _lookup(self, uv0):
        """Прежние UV → (треугольник образца, барицентры); вне острова — ближайший треугольник острова (продолжение)."""
        x = np.clip((uv0[:, 0] * self.S).astype(int), 0, self.S - 1)
        y = np.clip((uv0[:, 1] * self.S).astype(int), 0, self.S - 1)
        t = self.tid[y, x]
        ins = (t >= 0) & self.sel[np.maximum(t, 0)]
        tri = np.where(ins, t, self.sel_tris[self.kd.query(uv0)[1]])
        Tt = self.template_tri[tri]
        a, b, c = (self.template_uv0[Tt[:, k]] for k in range(3))
        v0, v1, v2 = b - a, c - a, uv0 - a
        d00, d01, d11 = (v0 * v0).sum(1), (v0 * v1).sum(1), (v1 * v1).sum(1)
        d20, d21 = (v2 * v0).sum(1), (v2 * v1).sum(1)
        den = np.where(np.abs(d00 * d11 - d01 * d01) < 1e-18, 1e-18, d00 * d11 - d01 * d01)
        l1 = (d11 * d20 - d01 * d21) / den
        l2 = (d00 * d21 - d01 * d20) / den
        return tri, np.stack([1 - l1 - l2, l1, l2], -1), ins

    def apply(self, M):
        """Сетка M (та же раскладка Edge) → с островом: треугольники, чей центр по прежним UV — в острове образца."""
        uv0 = M.get("uv0", M["uv"])
        cen = uv0[M["tri"]].mean(1)
        tri, bary, ins = self._lookup(cen)
        sel = ins

        def uv_of(vids):
            t, b, _ = self._lookup(uv0[vids])
            return (b[:, :, None] * self.isl_uv[self.template_tri[t]]).sum(1)
        return split_island(M, sel, uv_of)


_ISLAND = {}


def island():
    if "x" not in _ISLAND:
        E = load(0, 1, 2)
        E2, _ = deform(E, n24_ring_for(0, 1, 2))
        _ISLAND["x"] = Island(E2)
    return _ISLAND["x"]


# Остров — только у ближней детализации (lod 2). У средней и дальней (lod 0, 3) треугольники у края острова крупные:
# остров по центрам треугольников и продолжение его развёртки за край давали клинья цвета у кокетки и шипы кромки
# (20.10); у них — прежняя развёртка Edge, а прежнее место острова в текстурах — тот же рисунок (fill_old_place).
ISLAND_LODS = (2,)


def mesh_for(t, p, lod):
    """Готовая сетка варианта: копия Edge, перед ворота поднят; у ближней — перед ворота на своей развёртке."""
    E = load(t, p, lod)
    E2, _ = deform(E, n24_ring_for(t, p, lod))
    return island().apply(E2) if lod in ISLAND_LODS else E2


def fill_old_place(od, M):
    """Прежнее место острова в jersey_cm / _nm / _sm (развёртка uv0 его треугольников) — тем же рисунком, что на
    острове (для сеток без острова, ISLAND_LODS); рельеф — с поворотом касательного базиса (остров → uv0).
    -> текселей."""
    from PIL import Image
    tri = M["tri"][M["island"][M["tri"]].all(1)]
    t_isl, b_isl = kit3d.vertex_tangents(M)
    t_old, b_old = kit3d.vertex_tangents(dict(M, uv=M["uv0"]))
    n = 0
    for name in ("jersey_cm.png", "jersey_sm.png", "jersey_nm.png"):
        path = os.path.join(od, name)
        im0 = Image.open(path)
        mode = im0.mode
        im = np.asarray(im0).astype(np.float64)
        if im.ndim == 2:
            im = im[..., None]
        S = im.shape[0]
        tid, bar = kit3d.raster_uv({"uv": M["uv0"], "tri": tri}, S)
        m = tid >= 0
        T = tri[tid[m]]
        b = bar[m]
        uvi = (b[:, :, None] * M["uv"][T]).sum(1)
        val = kit3d.sample_bilinear(im, uvi[:, 0], uvi[:, 1])
        if name == "jersey_nm.png":
            N = kit3d._unit((b[:, :, None] * kit3d._unit(M["nrm"])[T]).sum(1))
            Ti, Bi = kit3d._unit((b[:, :, None] * t_isl[T]).sum(1)), kit3d._unit((b[:, :, None] * b_isl[T]).sum(1))
            To, Bo = kit3d._unit((b[:, :, None] * t_old[T]).sum(1)), kit3d._unit((b[:, :, None] * b_old[T]).sum(1))
            v = val[:, :3] / 127.5 - 1.0
            wv = Ti * v[:, 0:1] + Bi * (-v[:, 1:2]) + N * v[:, 2:3]
            val[:, :3] = (np.stack([(wv * To).sum(1), -(wv * Bo).sum(1), (wv * N).sum(1)], -1) + 1.0) * 127.5
        ys, xs = np.nonzero(m)
        im[ys, xs] = val[:, :im.shape[2]]
        out = np.clip(np.round(im), 0, 255).astype(np.uint8)
        Image.fromarray(out[..., 0] if out.shape[2] == 1 else out, mode).save(path)
        n = int(m.sum())
    return n


def pad_island(od, M, px=6):
    """Рельеф и блик за краем острова (px текселей) — значениями самого края: иначе при фильтрации и мипах по краю
    острова — тонкая линия (видна на рельефе у нижних углов вставки)."""
    from PIL import Image
    from scipy import ndimage as ndi
    # все тексели вне треугольников сетки (вокруг острова и прежнее место острова) — значением ближайшего своего
    for name in ("jersey_nm.png", "jersey_sm.png"):
        path = os.path.join(od, name)
        im = np.asarray(Image.open(path).convert("RGBA")).astype(np.float64)
        S = im.shape[0]
        tid, _ = kit3d.raster_uv({"uv": M["uv"], "tri": M["tri"]}, S)
        inside = tid >= 0
        _, (iy, ix) = ndi.distance_transform_edt(~inside, return_indices=True)
        im = im[iy, ix]
        Image.fromarray(np.clip(np.round(im), 0, 255).astype(np.uint8), "RGBA").save(path)


def remap_island_maps(nm_path, sm_path, M):
    """jersey_nm / jersey_sm (рельеф и блик Legacy в прежней развёртке — как их кладёт fb.pilot) → в текселях острова
    — значения с прежнего места (uv0), рельеф — с поворотом касательного базиса (прежний → новый)."""
    from PIL import Image
    nm = np.asarray(Image.open(nm_path).convert("RGBA")).astype(np.float64)
    sm = np.asarray(Image.open(sm_path).convert("RGBA")).astype(np.float64)
    S = nm.shape[0]
    tri = M["tri"][M["island"][M["tri"]].all(1)]
    sub = {"uv": M["uv"], "tri": tri}
    tid, bar = kit3d.raster_uv(sub, S)
    m = tid >= 0
    T = tri[tid[m]]
    b = bar[m]
    uv0 = (b[:, :, None] * M["uv0"][T]).sum(1)
    n0 = kit3d.sample_bilinear(nm, uv0[:, 0], uv0[:, 1])
    s0 = kit3d.sample_bilinear(sm, uv0[:, 0], uv0[:, 1])
    t_new, b_new = kit3d.vertex_tangents(M)
    t_old, b_old = kit3d.vertex_tangents(dict(M, uv=M["uv0"]))
    N = kit3d._unit((b[:, :, None] * kit3d._unit(M["nrm"])[T]).sum(1))
    To, Bo = kit3d._unit((b[:, :, None] * t_old[T]).sum(1)), kit3d._unit((b[:, :, None] * b_old[T]).sum(1))
    Tn, Bn = kit3d._unit((b[:, :, None] * t_new[T]).sum(1)), kit3d._unit((b[:, :, None] * b_new[T]).sum(1))
    v = n0[:, :3] / 127.5 - 1.0
    wv = To * v[:, 0:1] + Bo * (-v[:, 1:2]) + N * v[:, 2:3]
    nv = np.stack([(wv * Tn).sum(1), -(wv * Bn).sum(1), (wv * N).sum(1)], -1)
    ys, xs = np.nonzero(m)
    nm[ys, xs, :3] = (nv + 1.0) * 127.5
    sm[ys, xs] = s0
    Image.fromarray(np.clip(np.round(nm), 0, 255).astype(np.uint8), "RGBA").save(nm_path)
    Image.fromarray(np.clip(np.round(sm), 0, 255).astype(np.uint8), "RGBA").save(sm_path)
    return int(m.sum())



# ---------------------------------------------------------------- перенос рисунка по гладким координатам

COLLAR_W = (0.03, 0.05)            # м от края ворота: до 3 см — система ворота (кромка), к 5 см — переход к туловищу
#                                    (шире — сзади провал границы кокетки на 1,5 см: спина Edge и NHL 24 у ворота разные)
COLLAR_TOP = (0.12, 0.17)          # м: на верхе плеча (нормаль вверх) — система ворота дальше
TOP_NY = (0.72, 0.9)               # y нормали: от «наклонно» к «верх плеча» (ниже 0,72 — туловище: на наклонной груди
#                                    система ворота давала белые «глазки» на кокетке)
# Шов рукава NHL 24 (adidas): на развёртке рукава — слева и справа от столбца тела в полосе v SLEEVE_V, граница —
# u SEAM_U; кокетка выезда MIN кончается ровно на нём (тёмное на развёртке — u 0,356…0,6436). Рукав Edge
# — по шву NHL 24, перенесённому на Edge (поле seam_f, сглаженное): тело — с тела NHL 24, рукав — с рукава, без
# смешения (у угла кокетки у плечевого сустава были «хвостики», пользователь, 19.10)
SEAM_U = (0.3555, 0.6445)
SLEEVE_V = (0.33, 0.67)
TORSO_DELTA = None                 # (спереди, сзади), м: рисунок туловища выше на столько (задаётся сборкой кокетки)
DELTA_Y = (1.52, 1.58)             # м: сдвиг — выше этой высоты (ниже — плавно на нет)
SLEEVE_BY_BONES = False            # прежний способ (рукав — по весам костей) — выключен
SEAM_SMOOTH = 30                   # итераций сглаживания поля шва на сетке Edge
TOP_X, TOP_Z = (-0.6, 0.6), (-0.3, 0.3)   # м: сетка проекции сверху (верх плеч)
GRID_XZ = 0.001
TOPP_NY = (0.55, 0.8)              # y нормали: от «наклонно» к «верх» — проекция сверху
FRONT_TH = (-2.0, -1.0)            # град: у середины переда — система ворота только на кромке (выключено: кромка
#                                    рвалась у углов вставки; вставку рисует InsertPaint)
FRONT_CW = (0.0, 0.004)            # м: там она — до 0 … 4 мм от края (кромка и вставка у NHL 24 — одного цвета)
FRONT_PROJ = False                 # проекция спереди (проба 19.10) — выключена
FRONT_X, FRONT_Y = (-0.12, 0.12), (1.45, 1.75)  # м: сетка проекции спереди (перед ворота)
FRONT_XW = (0.055, 0.075)          # м от оси: вставка — спереди до 5,5 см, к 7,5 — на нет
FRONT_D = (0.006, 0.012)           # м от края ворота: кромка — по вороту, ниже — спереди
TRIM_K = 1.3                       # кромка ворота шире, чем у NHL 24 (пользователь, 19.10: «чуть побольше»)
TRIM_D = (0.012, 0.03)             # м: до 1,2 см от края — растяжение TRIM_K, к 3 см — снова 1:1
SLEEVE_W = (0.35, 0.75)            # доля весов костей рукава (SLEEVE_BONES): рукав — прежний перенос (правило
#                                    полос fb.sleeve); плечо — по туловищу (иначе у угла кокетки — «хвостики»)
# кости скелета Legacy (позиции суставов — rw4mesh.Skeleton): 48/79 — ключица, 49/80 — плечо (сустав 0,21 м от оси),
# 50/81 — поворот плеча (середина плеча), 51/82 — предплечье (локоть), 52–54/83–85 — предплечье и кисть
SLEEVE_BONES = (((51, 52, 53, 54, 82, 83, 84, 85), 1.0), ((50, 81), 0.6))
TORSO_YMAX = 1.80
TORSO_K = 8                        # кандидатов в клетке туловища (бока и руки на одной высоте) — берётся ближний по r
GRID_TH = 0.25                     # град — шаг сеток по углу
GRID_Y = 0.0005                    # м — шаг по высоте (ворот)
GRID_YT = 0.001                    # м — по высоте (туловище)


def _raster(tri, a, b, val, a0, a1, b0, b1, da, db, prio=None):
    """Сетка (a, b) → val по треугольникам (у каждого — свои значения в вершинах); prio (в вершинах) — при наложении
    берётся меньший (ближе к оси). a — угол (через ±180 — со сдвигом)."""
    na, nb = int(round((a1 - a0) / da)), int(np.ceil((b1 - b0) / db)) + 1
    out = np.zeros((na, nb, val.shape[1]))
    best = np.full((na, nb), np.inf)
    for t in tri:
        pa = a[t].copy()
        if pa.max() - pa.min() > 180:
            pa[pa < 0] += 360
        x = (pa - a0) / da
        y = (b[t] - b0) / db
        x0, x1 = int(np.floor(x.min())), int(np.ceil(x.max()))
        y0, y1 = max(int(np.floor(y.min())), 0), min(int(np.ceil(y.max())), nb - 1)
        if y1 < y0:
            continue
        den = (y[1] - y[2]) * (x[0] - x[2]) + (x[2] - x[1]) * (y[0] - y[2])
        if abs(den) < 1e-12:
            continue
        xs, ys = np.meshgrid(np.arange(x0, x1 + 1), np.arange(y0, y1 + 1))
        l0 = ((y[1] - y[2]) * (xs - x[2]) + (x[2] - x[1]) * (ys - y[2])) / den
        l1 = ((y[2] - y[0]) * (xs - x[2]) + (x[0] - x[2]) * (ys - y[2])) / den
        l2 = 1 - l0 - l1
        m = (l0 >= -1e-6) & (l1 >= -1e-6) & (l2 >= -1e-6)
        if not m.any():
            continue
        ix = xs[m] % na
        iy = ys[m]
        pr = 0.0 if prio is None else (l0[m] * prio[t[0]] + l1[m] * prio[t[1]] + l2[m] * prio[t[2]])
        v = l0[m, None] * val[t[0]] + l1[m, None] * val[t[1]] + l2[m, None] * val[t[2]]
        if prio is None:
            out[ix, iy] = v
            best[ix, iy] = 0
        else:
            better = pr < best[ix, iy]
            out[ix[better], iy[better]] = v[better]
            best[ix[better], iy[better]] = pr[better]
    return out, np.isfinite(best)


def _raster_multi(tri, a, b, r, val, a0, a1, b0, b1, da, db, k=TORSO_K):
    """Сетка (a, b) → до k кандидатов (r, val) на клетку: у туловища на одной высоте и угле бывают и бок, и рука, и на
    плече — несколько точек; при поиске берётся ближний по r (расстояние до оси тела)."""
    na, nb = int(round((a1 - a0) / da)), int(np.ceil((b1 - b0) / db)) + 1
    R = np.full((na, nb, k), np.inf, np.float32)
    V = np.zeros((na, nb, k, val.shape[1]), np.float32)
    cnt = np.zeros((na, nb), np.int8)
    for t in tri:
        pa = a[t].copy()
        if pa.max() - pa.min() > 180:
            pa[pa < 0] += 360
        x = (pa - a0) / da
        y = (b[t] - b0) / db
        x0, x1 = int(np.floor(x.min())), int(np.ceil(x.max()))
        y0, y1 = max(int(np.floor(y.min())), 0), min(int(np.ceil(y.max())), nb - 1)
        if y1 < y0:
            continue
        den = (y[1] - y[2]) * (x[0] - x[2]) + (x[2] - x[1]) * (y[0] - y[2])
        if abs(den) < 1e-12:
            continue
        xs, ys = np.meshgrid(np.arange(x0, x1 + 1), np.arange(y0, y1 + 1))
        l0 = ((y[1] - y[2]) * (xs - x[2]) + (x[2] - x[1]) * (ys - y[2])) / den
        l1 = ((y[2] - y[0]) * (xs - x[2]) + (x[0] - x[2]) * (ys - y[2])) / den
        l2 = 1 - l0 - l1
        m = (l0 >= -1e-6) & (l1 >= -1e-6) & (l2 >= -1e-6)
        if not m.any():
            continue
        ix, iy = xs[m] % na, ys[m]
        rr = l0[m] * r[t[0]] + l1[m] * r[t[1]] + l2[m] * r[t[2]]
        vv = l0[m, None] * val[t[0]] + l1[m, None] * val[t[1]] + l2[m, None] * val[t[2]]
        c = cnt[ix, iy]
        free = c < k
        ix, iy, c, rr, vv = ix[free], iy[free], c[free], rr[free], vv[free]
        R[ix, iy, c] = rr
        V[ix, iy, c] = vv
        cnt[ix, iy] = c + 1
    return R, V


def _lookup_multi(grid, a, b, r, a0, da, b0, db, seam=0.03):
    """По сетке _raster_multi: в каждой из четырёх соседних клеток — кандидат, ближний по r; двулинейно, если все
    четыре есть и в одном острове развёртки, иначе — ближайшая клетка."""
    R, V = grid
    na, nb, k = R.shape
    x = (a - a0) / da
    y = np.clip((b - b0) / db, 0, nb - 1.001)
    x0 = np.floor(x).astype(np.int64)
    y0 = np.floor(y).astype(np.int64)
    fx, fy = (x - x0)[:, None], (y - y0)[:, None]
    picks, oks = [], []
    for i, j in (((x0) % na, y0), ((x0 + 1) % na, y0), ((x0) % na, np.minimum(y0 + 1, nb - 1)),
                 ((x0 + 1) % na, np.minimum(y0 + 1, nb - 1))):
        dr = np.abs(R[i, j] - r[:, None])
        best = np.argmin(dr, 1)
        picks.append(V[i, j, best].astype(np.float64))
        oks.append(np.isfinite(R[i, j, best]) & (dr[np.arange(len(r)), best] < 0.08))
    v00, v10, v01, v11 = picks
    all4 = oks[0] & oks[1] & oks[2] & oks[3]
    spread = np.max(np.stack([np.abs(v - v00).max(1) for v in (v10, v01, v11)], 1), 1)
    lin = v00 * (1 - fx) * (1 - fy) + v10 * fx * (1 - fy) + v01 * (1 - fx) * fy + v11 * fx * fy
    q = (fx[:, 0] >= 0.5).astype(int) + 2 * (fy[:, 0] >= 0.5).astype(int)
    near = np.stack(picks, 1)[np.arange(len(r)), q]
    okn = np.stack(oks, 1)[np.arange(len(r)), q]
    use = all4 & (spread < seam)
    return np.where(use[:, None], lin, near), use | okn


def _lookup(grid, a, b, a0, da, b0, db, seam=0.03):
    """Двулинейно по сетке (если четыре соседа рядом по значению — один остров развёртки), иначе — ближайшая."""
    val, ok = grid
    na, nb = ok.shape
    x = (a - a0) / da
    y = np.clip((b - b0) / db, 0, nb - 1.001)
    x0 = np.floor(x).astype(np.int64)
    y0 = np.floor(y).astype(np.int64)
    fx, fy = (x - x0)[:, None], (y - y0)[:, None]
    i0, i1 = x0 % na, (x0 + 1) % na
    j0, j1 = y0, np.minimum(y0 + 1, nb - 1)
    v00, v10, v01, v11 = val[i0, j0], val[i1, j0], val[i0, j1], val[i1, j1]
    all4 = ok[i0, j0] & ok[i1, j0] & ok[i0, j1] & ok[i1, j1]
    spread = np.max(np.stack([np.abs(v - v00).max(1) for v in (v10, v01, v11)], 1), 1)
    lin = v00 * (1 - fx) * (1 - fy) + v10 * fx * (1 - fy) + v01 * (1 - fx) * fy + v11 * fx * fy
    ni = np.where(fx[:, 0] < 0.5, i0, i1)
    nj = np.where(fy[:, 0] < 0.5, j0, j1)
    near = val[ni, nj]
    use = all4 & (spread < seam)
    out = np.where(use[:, None], lin, near)
    return out, ok[ni, nj] | use


class CoordMap:
    """Соответствие «точка свитера Legacy → UV NHL 24» по гладким координатам (на сетке NHL 24 src и Legacy dst)."""

    def __init__(self, src, dst, dst_bones=None):
        from scipy.sparse.csgraph import connected_components
        from . import hem
        # У сетки NHL 24 ворот и рисунок груди (V-вставка, шнуровка) — на 3,5–4 мм левее оси тела (середина горловины
        # x = −0,0035, середина красной вставки −0,0041), тело — по оси. Рисунок переносится относительно середины
        # горловины: сетка-источник сдвигается так, чтобы она была на x = 0 (у Edge горловина — на оси); иначе вставка
        # и шнуровка уезжали влево на 4 мм (пользователь, 19.10)
        ws0 = Hy.Welded(src)
        _, comp0 = connected_components(ws0.A, directed=False)
        b0 = ws0.boundary()
        r0 = ws0.neck(b0[comp0[b0] == np.bincount(comp0).argmax()])
        self.x_fix = -float(ws0.P[r0, 0].mean())
        src = dict(src)
        src["pos"] = src["pos"] + np.array([self.x_fix, 0.0, 0.0])
        self.src, self.dst = src, dst
        # NHL 24: наружная оболочка, край ворота
        ws = Hy.Welded(src)
        _, comp = connected_components(ws.A, directed=False)
        main = np.bincount(comp).argmax()
        bnd = ws.boundary()
        ring = ws.neck(bnd[comp[bnd] == main])
        self.zc_s = float(ws.P[ring, 2].mean())
        ring_poly = Hy.ring_polyline(ws, ring)
        is_main = comp[ws.g[src["tri"][:, 0]]] == main
        cu = src["uv"][src["tri"]].mean(1)
        sleeve_t = is_main & ((cu[:, 0] < SEAM_U[0]) | (cu[:, 0] > SEAM_U[1])) & (cu[:, 1] > SLEEVE_V[0]) & \
            (cu[:, 1] < SLEEVE_V[1])
        body_t = is_main & ~sleeve_t
        self.src_body = dict(src, tri=src["tri"][body_t])
        self.src_sleeve = dict(src, tri=src["tri"][sleeve_t])
        self.src_outer = dict(src, tri=src["tri"][is_main])
        th = Hy.theta_of(src["pos"], self.zc_s)
        d = Hy.ring_dist(src["pos"], ring_poly)
        self.g_collar = _raster(src["tri"][is_main], th, d, src["uv"], -180, 180, 0, COLLAR_TOP[1] + 0.02, GRID_TH,
                                GRID_Y)
        self.g_lining = _raster(src["tri"][~is_main], th, d, src["uv"], -180, 180, 0, 0.10, GRID_TH, GRID_Y)
        tt = Hy.theta_of(src["pos"], 0.0)
        r = np.hypot(src["pos"][:, 0], src["pos"][:, 2])
        self.g_torso = _raster_multi(src["tri"][body_t], tt, src["pos"][:, 1], r, src["uv"], -180, 180, 0.85,
                                     TORSO_YMAX, GRID_TH, GRID_YT)
        self.g_hem = hem.hem_grid(src)
        # верх плеч — сверху (x, z): по (θ, высоте) почти горизонтальная ткань плеча неоднозначна (на одной высоте —
        # большой участок), граница кокетки у плечевого сустава шла вырезом (пользователь, 19.10)
        nrm_s = kit3d._unit(src["nrm"])
        up_t = body_t & (nrm_s[src["tri"]].mean(1)[:, 1] > 0.25)
        self.g_top = _raster(src["tri"][up_t], src["pos"][:, 0], src["pos"][:, 2], src["uv"], TOP_X[0], TOP_X[1],
                             TOP_Z[0], TOP_Z[1], GRID_XZ, GRID_XZ, prio=-src["pos"][:, 1])
        # перед ворота — проекция спереди (x, y): красная вставка под воротом у NHL 24 — с прямыми краями; по (угол,
        # расстояние от края ворота) края выгибались полукругами (пользователь, 19.10)
        fr_t = body_t & (nrm_s[src["tri"]].mean(1)[:, 2] > 0.3)
        self.g_front = _raster(src["tri"][fr_t], src["pos"][:, 0], src["pos"][:, 1], src["uv"], FRONT_X[0],
                               FRONT_X[1], FRONT_Y[0], FRONT_Y[1], GRID_XZ, GRID_XZ, prio=-src["pos"][:, 2])
        # Legacy: край ворота (сглаженный сгиб), подворот, край низа
        wd = Hy.Welded(dst)
        ring_d = wd.neck()
        self.zc_d = float(wd.P[ring_d, 2].mean())
        band, lip = Hy.edge_layers(wd, ring_d, self.zc_d)
        fold = Hy.fold_polyline(wd, band)
        self.edge_d = Hy.smooth_curve(fold if fold is not None else Hy.lip_polyline(lip), self.zc_d, win=2.0)
        self.band_v = band[wd.g]
        self.hem_curve = hem.hem_curve(dst)
        # поле шва рукава на Edge: ближайшая точка NHL 24 → её u до шва (> 0 — тело), сглаженное по сетке Edge
        t_, b_, _ = kit3d.project(wd.P, J.node_normals(wd.P, wd.T, wd.n), self.src_outer)
        uvn = (b_[:, :, None] * src["uv"][src["tri"][t_]]).sum(1)
        band_v = (uvn[:, 1] > SLEEVE_V[0]) & (uvn[:, 1] < SLEEVE_V[1])
        f = np.where(band_v, np.minimum(uvn[:, 0] - SEAM_U[0], SEAM_U[1] - uvn[:, 0]), 0.2)
        f = np.clip(f, -0.1, 0.1)
        deg = np.asarray(wd.A.sum(1)).ravel()
        for _ in range(SEAM_SMOOTH):
            f = 0.5 * f + 0.5 * (wd.A @ f) / np.maximum(deg, 1)
        self.seam_v = f[wd.g]
        self.sleeve = SleeveMap(self.src_outer, dst) if SLV_PARAM else None
        self.arm_v = None
        if dst_bones is not None and SLEEVE_BY_BONES:
            bones, weights = dst_bones
            # рукав — от середины плеча вниз: ключица и плечевой сустав — по туловищу (угол кокетки у сустава — внутри
            # одной системы; на стыке систем у угла были «хвостики»)
            wb = np.zeros(bones.shape)
            for bset, k in SLEEVE_BONES:
                wb += np.isin(bones, bset) * k
            self.arm_v = (weights * wb).sum(1)

    def uv(self, P, tri_v, bary, fallback, N=None):
        """UV NHL 24 в точках P свитера (tri_v — вершины их треугольников, bary — барицентры) и прежнее UV (рукава).
        -> (uv, веса систем для отчёта)."""
        from . import hem
        n = len(P)
        tt = Hy.theta_of(P, 0.0)
        rr = np.hypot(P[:, 0], P[:, 2])
        yq = P[:, 1]
        if TORSO_DELTA and N is not None:                # кокетка (и её шов в рельефе) спереди выше, сзади ниже
            df, db = TORSO_DELTA
            wf = Hy.smooth((N[:, 2] + 0.3) / 0.6)
            fade = Hy.smooth((P[:, 1] - DELTA_Y[0]) / (DELTA_Y[1] - DELTA_Y[0]))
            yq = P[:, 1] - (df * wf + db * (1 - wf)) * fade
        u_t, ok_t = _lookup_multi(self.g_torso, tt, yq, rr, -180, GRID_TH, 0.85, GRID_YT)
        out = np.where(ok_t[:, None], u_t, fallback)
        # ворот (у края — растяжение TRIM_K: кромка шире)
        thc = Hy.theta_of(P, self.zc_d)
        d_true = Hy.ring_dist(P, self.edge_d)
        d1, d2 = TRIM_D
        dc = np.where(d_true <= d1, d_true / TRIM_K,
                      np.where(d_true < d2, d1 / TRIM_K + (d_true - d1) * (d2 - d1 / TRIM_K) / (d2 - d1), d_true))
        inner = self.band_v[tri_v].all(1)
        u_c, ok_c = _lookup(self.g_collar, thc, dc, -180, GRID_TH, 0, GRID_Y)
        u_l, ok_l = _lookup(self.g_lining, thc, dc, -180, GRID_TH, 0, GRID_Y)
        # верх плеч (нормаль вверх) — по проекции сверху, поверх туловища
        if N is not None:
            u_p, ok_p = _lookup(self.g_top, P[:, 0], P[:, 2], TOP_X[0], GRID_XZ, TOP_Z[0], GRID_XZ)
            w_p = Hy.smooth((N[:, 1] - TOPP_NY[0]) / (TOPP_NY[1] - TOPP_NY[0])) * ok_p * (P[:, 1] > 1.55)
            out = _mix(out, u_p, w_p)
        u_c = np.where(inner[:, None], u_l, u_c)
        if N is not None and FRONT_PROJ:                  # перед ворота — спереди (выключено: туловище, см. FRONT_TH)
            u_f, ok_f = _lookup(self.g_front, P[:, 0], P[:, 1], FRONT_X[0], GRID_XZ, FRONT_Y[0], GRID_XZ)
            w_f = (Hy.smooth((FRONT_XW[1] - np.abs(P[:, 0])) / (FRONT_XW[1] - FRONT_XW[0]))
                   * Hy.smooth((d_true - FRONT_D[0]) / (FRONT_D[1] - FRONT_D[0]))
                   * Hy.smooth((N[:, 2] - 0.3) / 0.3) * ok_f * ~inner)
            u_c = _mix(u_c, u_f, w_f)
            ok_c = ok_c | (w_f > 0.5)
        ok_c = np.where(inner, ok_l, ok_c)
        # ширина зоны ворота — по наклону ткани: на отвесной груди и спине — COLLAR_W (дальше — туловище, по высоте),
        # на почти горизонтальном верхе плеча — COLLAR_TOP (там «угол и высота» попадали на кромку NHL 24 у шеи)
        top = Hy.smooth((N[:, 1] - TOP_NY[0]) / (TOP_NY[1] - TOP_NY[0])) if N is not None else np.zeros(n)
        c0 = COLLAR_W[0] + (COLLAR_TOP[0] - COLLAR_W[0]) * top
        c1 = COLLAR_W[1] + (COLLAR_TOP[1] - COLLAR_W[1]) * top
        # перед ворота (|θ| < FRONT_TH): от края — сразу туловище (по высоте): красная вставка NHL 24 под воротом —
        # с прямыми краями по высоте; по (углу, расстоянию от края) края выгибались полукругами (пользователь, 19.10)
        fr = Hy.smooth((FRONT_TH[1] - np.abs(thc)) / (FRONT_TH[1] - FRONT_TH[0])) * (P[:, 2] > self.zc_d)
        c0 = c0 * (1 - fr) + FRONT_CW[0] * fr
        c1 = c1 * (1 - fr) + FRONT_CW[1] * fr
        w_c = np.where(inner, 1.0, 1.0 - Hy.smooth((d_true - c0) / (c1 - c0))) * ok_c
        out = _mix(out, u_c, w_c)
        # низ
        phi, dh = hem.hem_coords(P, self.hem_curve)
        u_h, ok_h = hem.lookup(self.g_hem, phi, dh)
        w_h = Hy.smooth((hem.HEM_H - dh) / hem.HEM_BLEND) * ok_h * (dh < hem.HEM_H)
        out = _mix(out, u_h, w_h)
        # рукава — прежний перенос (правило полос рукава — на нём)
        w_s = np.zeros(n)
        if self.arm_v is not None:
            aw = (bary * self.arm_v[tri_v]).sum(1)
            w_s = Hy.smooth((aw - SLEEVE_W[0]) / (SLEEVE_W[1] - SLEEVE_W[0]))
            out = _mix(out, fallback, w_s)
        return out, {"collar": float((w_c > 0.5).mean()), "hem": float((w_h > 0.5).mean()),
                     "sleeve": float((w_s > 0.5).mean()), "torso_ok": float(ok_t.mean())}


# ---------------------------------------------------------------- рукав: перенос по координатам руки

# Пользователь (19.10): «полосы на руках — ровно по шву, сейчас криво, волной». Рукав переносился ближайшей точкой
# (поверхности рукавов Edge и NHL 24 разные — полосы и их швы шли волной). У обеих развёрток столбец рукава — плоское
# кольцо вокруг руки (u — вдоль руки), полосы NHL 24 — столбцы u. Здесь: вдоль — столбец Edge → ближайшая точка
# средней линии рукава NHL 24 (центры колец) → её u (гладко, монотонно); вокруг — угол точки в плоскости кольца
# (общий базис: «вверх» на плоскость кольца) → строка кольца NHL 24 с тем же углом. Полосы и их швы (рельеф NHL 24 —
# тем же переносом) ложатся ровными кольцами по развёртке Edge.
SLV_PARAM = True
SLV_U = (0.0, 0.234)               # u развёртки Edge: рукав (левый; правый — 1 − u), дальше — пройма
SLV_V = (0.30, 0.72)               # v развёртки Edge: рукав
SLV_U24 = (0.03, 0.30)             # u NHL 24: рукав (левый; правый — 1 − u), манжета — у 0,03 (пройма — 0,335)
SLV_U24_MIN = 0.042                # u NHL 24 — не ближе к манжете (у Edge рукав там уходит в краги)
SLV_BLEND = 0.007                  # u Edge: у проймы — плавно к прежнему переносу (полосы кончаются у 0,222)
SLV_X = 0.15                       # м: |x| больше — рукав
SLV_PHI = 0.5                      # град — шаг таблиц угла
# Полосы — ближе к кисти (правило пользователя 11.10, kit_rules.toml [sleeve]: сжатие рисунка к манжете в k раз, зазор
# до зоны номера на плече ≥ gap_min). У fb.pilot оно сдвигало уже готовую текстуру по строкам развёртки — у Edge в
# строках подмышки вместе с рукавом тянуло и грудную полосу туловища (бежевое на рукаве, пользователь, 19.10), а швы
# рельефа оставались на прежнем месте. Здесь — сжатие в самом переносе рукава (SleeveMap): цвет и рельеф вместе.
SLV_COMPRESS = None                # (k, d_top): задаётся сборкой (cmd_kit) по зоне номера шаблона; None — без сжатия
# Шов проймы Edge (рукав — реглан): правый край панели рукава EA-формы MIN 1_14_0 на развёртке Edge (левый рукав;
# правый — 1 − u), (v, u), сглажено. В строках подмышки рукав и туловище делятся по нему (а не по шву NHL 24, у
# которого рукав втачной: грудная полоса заходила на рукав), там же — шов рельефа.
ARMHOLE_UV = ((0.27, 0.2237), (0.28, 0.2274), (0.29, 0.2321), (0.30, 0.2383), (0.31, 0.2465), (0.32, 0.2576),
              (0.33, 0.2722), (0.34, 0.2883), (0.35, 0.3019), (0.36, 0.3126), (0.37, 0.3202), (0.38, 0.3262),
              (0.39, 0.3307), (0.40, 0.3344), (0.56, 0.3350), (0.57, 0.3447), (0.58, 0.3418), (0.59, 0.3364),
              (0.60, 0.3304), (0.61, 0.3231), (0.62, 0.3148), (0.63, 0.3042), (0.64, 0.2928), (0.65, 0.2806),
              (0.66, 0.2688), (0.67, 0.2586), (0.68, 0.2503), (0.69, 0.2435), (0.70, 0.2376), (0.71, 0.2339),
              (0.72, 0.2257), (0.73, 0.2029))
ARMHOLE_ZONES = ((0.27, 0.385), (0.575, 0.73))   # v: низ проймы (спина, грудь) — деление цвета и шов
ARMHOLE_FADE = 0.015               # v: к плечу шов сходит на нет
ARMHOLE_X = 0.15                   # м: |x| больше — сторона рукава/бока


def armhole_u(v):
    vs, us = zip(*ARMHOLE_UV)
    return np.interp(v, vs, us)


def armhole_sleeve(tu, tv, x):
    """Тексели (tu, tv) с точками x: (в зоне деления, сторона рукава)."""
    zone = np.zeros(len(tu), bool)
    for v0, v1 in ARMHOLE_ZONES:
        zone |= (tv >= v0) & (tv <= v1)
    zone &= np.abs(x) > ARMHOLE_X
    sE = np.where(x < 0, tu, 1.0 - tu)
    return zone, zone & (sE < armhole_u(tv))


def armhole_dist(G):
    """Расстояние (м) до шва проймы (обе стороны) на растре relief_geometry G; вне зон — inf; к плечу — + сход."""
    from scipy.ndimage import map_coordinates
    from scipy.spatial import cKDTree
    P, m = G["P"], G["m"]
    S = P.shape[0]
    pts, fade = [], []
    for v0, v1 in ARMHOLE_ZONES:
        vv = np.arange(v0, v1, 0.25 / S)
        shoulder_end = v1 if v0 < 0.5 else v0
        f = np.clip(np.abs(vv - shoulder_end) / ARMHOLE_FADE, 0, 1)
        for side in (0, 1):
            uu = armhole_u(vv)
            uu = uu if side == 0 else 1.0 - uu
            rr, cc = vv * S - 0.5, uu * S - 0.5
            ok = m[np.clip(np.round(rr).astype(int), 0, S - 1), np.clip(np.round(cc).astype(int), 0, S - 1)]
            q = np.stack([map_coordinates(P[..., i], [rr, cc], order=1) for i in range(3)], -1)
            pts.append(q[ok])
            fade.append(f[ok])
    pts, fade = np.concatenate(pts), np.concatenate(fade)
    tree = cKDTree(pts)
    d, j = tree.query(P[m], distance_upper_bound=0.03)
    D = np.full((S, S), np.inf)
    ok = np.isfinite(d)
    dd = np.full(len(d), np.inf)
    dd[ok] = d[ok] + (1.0 - fade[j[ok]]) * 0.01
    D[m] = dd
    return D


class SleeveMap:
    """Рукав Edge → UV NHL 24 по координатам руки (см. выше)."""

    def __init__(self, src, dst):
        self.sides = {}
        for sgn in (-1, 1):
            e = self._rings(dst, 1024, sgn, SLV_U, SLV_V)
            n = self._rings(src, 2048, sgn, SLV_U24, (0.0, 1.0))
            # средняя линия: столбец Edge → ближайшая точка ломаной центров NHL 24 → её s
            C24, s24 = n["C"], n["s"]
            seg = C24[1:] - C24[:-1]
            L2 = np.maximum((seg * seg).sum(1), 1e-12)
            q = e["C"][:, None, :] - C24[None, :-1, :]
            t = np.clip((q * seg[None]).sum(-1) / L2[None], 0, 1)
            dist = np.linalg.norm(q - t[..., None] * seg[None], axis=-1)
            j = np.argmin(dist, axis=1)
            sm = s24[j] + t[np.arange(len(j)), j] * (s24[j + 1] - s24[j])
            from scipy.ndimage import gaussian_filter1d
            sm = gaussian_filter1d(sm, 3.0, mode="nearest")
            sm = np.clip(np.maximum.accumulate(sm), SLV_U24_MIN, s24[-1])
            self.sides[sgn] = dict(e=e, n=n, s24=sm)
        # симметрично: у NHL 24 после сдвига x_fix (горловина — на оси) руки на 3,5 мм несимметричны — полосы слева и
        # справа разошлись бы на 1–2 мм
        a, b = self.sides[-1], self.sides[1]
        if len(a["e"]["s"]) == len(b["e"]["s"]) and np.allclose(a["e"]["s"], b["e"]["s"], atol=1e-6):
            avg = (a["s24"] + b["s24"]) / 2
            a["s24"], b["s24"] = avg, avg.copy()

    @staticmethod
    def _rings(M, S, sgn, ur, vr):
        """Кольца рукава по столбцам развёртки, от манжеты к плечу: s (u левого / 1 − u правого), центр C, ось A (к
        плечу), базис e1 («вверх» на плоскость кольца), e2; для NHL 24 — и таблица v по углу."""
        from scipy.ndimage import gaussian_filter1d
        tid, bar = kit3d.raster_uv(M, S)
        m = tid >= 0
        P = np.zeros((S, S, 3))
        P[m] = (bar[m][:, :, None] * M["pos"][M["tri"][tid[m]]]).sum(1)
        c0, c1 = int(np.floor(ur[0] * S)), int(np.ceil(ur[1] * S))
        cols = np.arange(c0, c1) if sgn < 0 else np.arange(S - c1, S - c0)[::-1]
        rows_all = np.arange(S)
        vv = (rows_all + 0.5) / S
        out_s, C, A, pts = [], [], [], []
        for c in cols:
            k = m[:, c] & (vv > vr[0]) & (vv < vr[1]) & (P[:, c, 0] * sgn > SLV_X)
            if k.sum() < 12:
                continue
            p = P[k, c]
            cc = p.mean(0)
            _, _, vt = np.linalg.svd(p - cc, full_matrices=False)
            out_s.append((c + 0.5) / S if sgn < 0 else 1.0 - (c + 0.5) / S)
            C.append(cc)
            A.append(vt[2])
            pts.append((vv[k], p))
        s_, C, A = np.array(out_s), np.array(C), np.array(A)
        C = np.stack([gaussian_filter1d(C[:, i], 2.0, mode="nearest") for i in range(3)], -1)
        T = np.gradient(C, axis=0)
        A = np.where(((A * T).sum(1) < 0)[:, None], -A, A)
        A = np.stack([gaussian_filter1d(A[:, i], 2.0, mode="nearest") for i in range(3)], -1)
        A /= np.linalg.norm(A, axis=1, keepdims=True)
        up = np.array([0.0, 1.0, 0.0])
        e1 = up[None] - A * (A @ up)[:, None]
        e1 /= np.linalg.norm(e1, axis=1, keepdims=True)
        e2 = np.cross(A, e1)
        grid = np.arange(-180.0, 180.0, SLV_PHI)
        tab = np.zeros((len(s_), len(grid)))
        for i, (v_, p) in enumerate(pts):
            q = p - C[i]
            ph = np.degrees(np.arctan2(q @ e2[i], q @ e1[i]))
            o = np.argsort(ph)
            ph, v_ = ph[o], v_[o]
            # по углу — линейно между соседними строками, через разрез развёртки (скачок v) — ближайшая
            pe = np.concatenate([ph[-1:] - 360.0, ph, ph[:1] + 360.0])
            ve = np.concatenate([v_[-1:], v_, v_[:1]])
            ii = np.clip(np.searchsorted(pe, grid), 1, len(pe) - 1)
            a, b = pe[ii - 1], pe[ii]
            w = np.clip((grid - a) / np.maximum(b - a, 1e-9), 0, 1)
            lin = ve[ii - 1] * (1 - w) + ve[ii] * w
            near = np.where(w < 0.5, ve[ii - 1], ve[ii])
            tab[i] = np.where(np.abs(ve[ii] - ve[ii - 1]) > 0.02, near, lin)
        return dict(s=s_, C=C, A=A, e1=e1, e2=e2, tab=tab)

    @staticmethod
    def src_s(s):
        """Сжатие рисунка к манжете: s Edge → s, откуда брать рисунок (до колена knee = k·d_top — s/k, дальше —
        линейно до конца рукава SLV_U[1], где без сдвига)."""
        if SLV_COMPRESS is None:
            return s
        k, d_top = SLV_COMPRESS
        knee, u1 = k * d_top, SLV_U[1]
        return np.where(s <= knee, s / k, d_top + (s - knee) * (u1 - d_top) / max(u1 - knee, 1e-6))

    @staticmethod
    def dst_s(s_src):
        """Обратное к src_s: где на рукаве Edge окажется точка рисунка s_src."""
        if SLV_COMPRESS is None:
            return s_src
        k, d_top = SLV_COMPRESS
        knee, u1 = k * d_top, SLV_U[1]
        return np.where(s_src <= d_top, s_src * k, knee + (s_src - d_top) * (u1 - knee) / max(u1 - d_top, 1e-6))

    def stripes(self, tex):
        """Границы полос рукава NHL 24 (левый; правый — зеркально) — s NHL 24 и s Edge: профиль цвета по столбцам
        (медиана по кольцу через таблицу угла), смена цвета > 45 — граница (середина переходного столбца)."""
        nn = self.sides[-1]["n"]
        grid = np.arange(-180.0, 180.0, SLV_PHI)
        sel = np.arange(0, len(grid), 10)
        S = tex.shape[0]
        prof = []
        for j, s_ in enumerate(nn["s"]):
            v = nn["tab"][j, sel]
            cc = kit3d.sample_bilinear(tex, np.full(len(v), s_), v)[:, :3]
            prof.append(np.median(cc, 0))
        prof = np.array(prof)
        out = []
        i = 0
        n = len(prof)
        while i < n - 1:
            j = i + 1
            if np.abs(prof[j] - prof[i]).max() > 45:
                k = j                                     # переход — 1–2 столбца: граница — между устойчивыми
                while k + 1 < n and np.abs(prof[k + 1] - prof[k]).max() > 20:
                    k += 1
                out.append(0.5 * (nn["s"][i] + nn["s"][min(k, n - 1)]) if k > j else 0.5 * (nn["s"][i] + nn["s"][j]))
                i = k
            else:
                i = j
        b24 = np.array([b for b in out if SLV_U24_MIN + 0.01 < b < SLV_U24[1] - 0.01])
        e = self.sides[-1]
        bE = np.interp(b24, e["s24"], e["e"]["s"]) if len(b24) else np.zeros(0)
        return b24, self.dst_s(bE)

    def uv(self, tu, tv, P):
        """UV NHL 24 и вес (1 — рукав, к проёме — на нет, 0 — не рукав) для текселей развёртки Edge (tu, tv) с
        точками P."""
        n = len(tu)
        out = np.zeros((n, 2))
        wt = np.zeros(n)
        for sgn, d in self.sides.items():
            sE = tu if sgn < 0 else 1.0 - tu
            k = (sE >= SLV_U[0]) & (sE <= SLV_U[1]) & (tv > SLV_V[0]) & (tv < SLV_V[1]) & (P[:, 0] * sgn > SLV_X)
            if not k.any():
                continue
            e, nn = d["e"], d["n"]
            s = np.clip(sE[k], e["s"][0], e["s"][-1])
            C = np.stack([np.interp(s, e["s"], e["C"][:, i]) for i in range(3)], -1)
            ss = self.src_s(s)                           # к кисти (SLV_COMPRESS): откуда брать рисунок вдоль руки
            e1 = np.stack([np.interp(s, e["s"], e["e1"][:, i]) for i in range(3)], -1)
            e2 = np.stack([np.interp(s, e["s"], e["e2"][:, i]) for i in range(3)], -1)
            q = P[k] - C
            ph = np.degrees(np.arctan2((q * e2).sum(1), (q * e1).sum(1)))
            s24 = np.interp(ss, e["s"], d["s24"])
            # строка NHL 24: билинейно по столбцу (s) и углу
            fj = np.interp(s24, nn["s"], np.arange(len(nn["s"])))
            j0 = np.clip(np.floor(fj).astype(int), 0, len(nn["s"]) - 2)
            wj = np.clip(fj - j0, 0, 1)
            fp = (ph + 180.0) / SLV_PHI
            p0 = np.floor(fp).astype(int) % nn["tab"].shape[1]
            p1 = (p0 + 1) % nn["tab"].shape[1]
            wp = fp - np.floor(fp)

            def tv_(j):
                a, b = nn["tab"][j, p0], nn["tab"][j, p1]
                return np.where(np.abs(b - a) > 0.02, np.where(wp < 0.5, a, b), a * (1 - wp) + b * wp)
            va, vb = tv_(j0), tv_(j0 + 1)
            v24 = np.where(np.abs(vb - va) > 0.02, np.where(wj < 0.5, va, vb), va * (1 - wj) + vb * wj)
            u24 = s24 if sgn < 0 else 1.0 - s24
            out[k, 0], out[k, 1] = u24, v24
            wt[k] = Hy.smooth((SLV_U[1] - sE[k]) / SLV_BLEND)
        return out, wt


def _mix(a, b, w, close=0.03):
    """a → b с весом w: если UV рядом (один остров) — линейно, иначе — переключение на 0,5."""
    w = w[:, None]
    near = (np.abs(a - b).max(1) < close)[:, None]
    return np.where(near, a * (1 - w) + b * w, np.where(w > 0.5, b, a))


def coord_transfer(src_tex, src_mesh, dst_mesh, size=1024, ss=2, post=None, n_jersey_tri=None, cmap=None):
    """Как fb.kit3d.transfer (те же выходы и post), но UV NHL 24 у текселей свитера — по CoordMap (гладкие координаты);
    у «рубашки» (треугольники после n_jersey_tri) — как у kit3d.transfer (ближайшая точка)."""
    W, H = kit3d._wh(size)
    S = (W * ss, H * ss)
    T = dst_mesh["tri"]
    tid, bar = kit3d.raster_uv(dst_mesh, S)
    mask = tid >= 0
    t, b = tid[mask], bar[mask]
    Pm = (b[:, :, None] * dst_mesh["pos"][T[t]]).sum(1)
    Nm = kit3d._unit((b[:, :, None] * dst_mesh["nrm"][T[t]]).sum(1))

    def nearest(mesh, sel):
        """UV ближайшей точки mesh: по вершинам dst, внутри треугольников — линейно; на швах развёртки — по текселям."""
        vt, vb, _ = kit3d.project(dst_mesh["pos"], kit3d._unit(dst_mesh["nrm"]), mesh)
        vuv = (vb[:, :, None] * mesh["uv"][mesh["tri"][vt]]).sum(1)
        uv = (b[sel][:, :, None] * vuv[T[t[sel]]]).sum(1)
        tri_uv = vuv[T[t[sel]]]
        spread = np.max(np.linalg.norm(tri_uv[:, :, None, :] - tri_uv[:, None, :, :], axis=-1), axis=(1, 2))
        fb_ = spread > 0.04
        if fb_.any():
            idx = np.nonzero(sel)[0][fb_]
            st, sb, _ = kit3d.project(Pm[idx], Nm[idx], mesh)
            uv[fb_] = (sb[:, :, None] * mesh["uv"][mesh["tri"][st]]).sum(1)
        return uv, int(fb_.sum())
    UV = np.zeros((len(t), 2))
    jer = t < (n_jersey_tri if n_jersey_tri is not None else len(T))
    stats = {}
    if cmap is None:
        UV[:], seam_n = nearest(src_mesh, np.ones(len(t), bool))
    else:
        if (~jer).any():                                 # «рубашка» — как раньше
            UV[~jer], _ = nearest(cmap.src, ~jer)
        sv = (b * cmap.seam_v[np.minimum(T[t], len(cmap.seam_v) - 1)]).sum(1)
        sl = jer & (sv < 0)
        yy_a, xx_a = np.nonzero(mask)
        az, aside = armhole_sleeve((xx_a + 0.5) / S[0], (yy_a + 0.5) / S[1], Pm[:, 0])
        sl = np.where(jer & az, aside, sl)              # низ проймы — по шву Edge (грудная полоса — до него)
        bd = jer & ~sl
        seam_n = 0
        if sl.any():
            UV[sl], k = nearest(cmap.src_sleeve, sl)
            seam_n += k
        if bd.any():
            fbk, k = nearest(cmap.src_body, bd)
            seam_n += k
            UV[bd], stats = cmap.uv(Pm[bd], T[t[bd]], b[bd], fbk, Nm[bd])
        stats["sleeve_texels"] = float(sl.mean())
        if getattr(cmap, "sleeve", None) is not None:      # рукав — по координатам руки (SleeveMap)
            yy_, xx_ = np.nonzero(mask)
            uv_s, w_s = cmap.sleeve.uv((xx_ + 0.5) / S[0], (yy_ + 0.5) / S[1], Pm)
            ks = jer & (w_s > 0)
            if ks.any():
                UV[ks] = _mix(UV[ks], uv_s[ks], w_s[ks])
            stats["sleeve_param"] = float(ks.mean())
    col = kit3d.sample_bilinear(src_tex, UV[:, 0], UV[:, 1])
    img = np.zeros((S[1], S[0], src_tex.shape[2]))
    img[mask] = col
    if post is not None:
        img = post(img, mask, Pm, Nm, t, UV)
    if ss > 1:
        mk = mask.reshape(H, ss, W, ss).astype(np.float64)
        num = (img.reshape(H, ss, W, ss, -1) * mk[..., None]).sum((1, 3))
        cnt = mk.sum((1, 3))
        img = np.where(cnt[..., None] > 0, num / np.maximum(cnt, 1)[..., None], 0)
        mask = cnt > 0
    dist = np.zeros((H, W))
    info = {"seam_texels": seam_n, "tris": int(len(T)), **stats}
    return kit3d.push_pull(kit3d.fill_holes(img, mask, 8), mask), mask, dist, info


# ---------------------------------------------------------------- комплект: сборка fb.pilot с этой сеткой и переносом

KITS_OUT = os.path.join(WORK, "out")
# щит NHL (пользователь, 19.10): крупнее, по центру (у NHL 24 центр нашивки на 4 мм левее), чуть выше — чтобы не
# заходил на шнуровку
SHOULDER_IN_CM = 2.0               # нашивки на плечах — на 2 см к шее (пользователь, 19.10)
SHIELD_SCALE = 0.88                # меньше (пользователь, 19.10: «слишком большой»); у форм NHL 24 на Edge — 0,8 (под щит EA)
SHIELD_OFFSET_CM = [0.41, 0.6, 0.0]  # x: середина горловины NHL 24 — на 0,35–0,41 см левее оси (как CoordMap.x_fix)
RELIEF_CLEAR = [(0.468, 0.136, 0.532, 0.178, -0.05), (0.466, 0.386, 0.534, 0.401, -0.03)]   # u0, v0, u1, v1, сдвиг
#                                    источника по v: метка и черта над местом Reebok EA в чистом
#                                    рельефе T=4 на спине (под номером — прямоугольник, у EA-форм его нет)
REEBOK_BACK_UV = [0.5, 0.4183]  # 1,663 м — между 0,4205 (1,666: «чуть-чуть пониже») и 0,416 (1,66: «слишком
#                                    низко»), пользователь, 19.10; у EA — 0,4085 (1,648)
#                                        # у EA — 0,4085 (на 2,6 см ниже места логотипа adidas NHL 24, 1,674 м)


# Кокетка (цветной верх у светлых форм) — как у EA-формы Legacy того же клуба (пользователь, 19.10: «посмотри, как
# сделаны плечевые суставы и линии на них у Reebok-формы Legacy, и перенеси»): у EA кокетка на развёртке Edge —
# четырёхугольник с прямыми краями (бока — по плечевым суставам). Бока — с EA (прямые по краю её кокетки), верх
# (спина) и низ (грудь) — высоты NHL 24 (прямые на развёртке на высоте линии, перенесённой с NHL 24).
YOKE = {("MIN", "away"): {"from": "1_14_3"}}
YOKE_FLAT_X = 0.14                 # м от оси: дальше перед кокетки — ровной высоты
YOKE_BACK_FROM = "1_14_3"           # спина кокетки — по EA-форме (NHL 24 — 1,648 м: «зелёное кончается высоко»)
YOKE_MIX = 0.0                     # 0 — край кокетки на высотах NHL 24, 1 — перед и спина на средней
YOKE_SHIFT = 0.0                   # м: сдвиг края кокетки (обоих) по высоте
YOKE_PAD = 0.05                    # UV: за краем многоугольника — зона перекраски (там — ткань двух цветов;
#                                    0,02 — у плеч оставались тёмные следы прежнего угла кокетки)
YOKE_LACE_X, YOKE_LACE_Y = 0.032, 1.615  # м: спереди у середины ниже 1,615 — шнурки (вставку выше рисует InsertPaint)
YOKE_COLLAR = 0.0                  # (было 0,03) край кокетки — до самой кромки (кромку рисует TrimPaint поверх)
YOKE_COLLAR_OLD = 0.03                 # м от края ворота — не трогать (кромка, подкладка, вставка)


def _fit_side(mask, rows, left):
    """Край маски по строкам rows (крайний столбец слева/справа) → прямая u = a + b·v (UV)."""
    S = mask.shape[0]
    vs, us = [], []
    for y in rows:
        xs = np.nonzero(mask[y])[0]
        if len(xs):
            vs.append((y + 0.5) / S)
            us.append(((xs.min() if left else xs.max() + 1)) / S)
    b, a = np.polyfit(vs, us, 1)
    return a, b


def yoke_polygon(ea_png, ours_png):
    """Кокетка: бока — край кокетки EA по строкам (кривые, сглаженные), верх и низ — линии нашей текстуры (перенос
    NHL 24) по столбцам: у боков (u < U_IN) — продолжение прямой, подогнанной по столбцам U_FIT. Цвета — кокетка и
    ткань нашей текстуры."""
    from PIL import Image
    from scipy import ndimage as ndi
    from scipy.ndimage import median_filter
    S = 1024
    ea = np.asarray(Image.open(ea_png).convert("RGB").resize((S, S))).astype(np.float64)
    ours = np.asarray(Image.open(ours_png).convert("RGB").resize((S, S))).astype(np.float64)
    lum = ea.mean(-1)
    g_ea = (lum < 70) & (ea[..., 1] > ea[..., 0] + 15)
    lab, _ = ndi.label(g_ea)                             # только сама кокетка (не полосы рукавов)
    g_ea = lab == lab[int(0.53 * S), int(0.37 * S)]
    vv, ul, ur = [], [], []
    for y in range(S):
        xs = np.nonzero(g_ea[y])[0]
        if len(xs) > 20:
            vv.append((y + 0.5) / S)
            ul.append(xs.min() / S)
            ur.append((xs.max() + 1) / S)
    from scipy.ndimage import gaussian_filter1d
    left = (np.array(vv), gaussian_filter1d(median_filter(np.array(ul), 9, mode="nearest"), 3.0, mode="nearest"))
    right = (np.array(vv), gaussian_filter1d(median_filter(np.array(ur), 9, mode="nearest"), 3.0, mode="nearest"))
    lo = ours.mean(-1)
    g_o = (lo < 70) & (ours[..., 1] > ours[..., 0] + 15)
    green = np.median(ours[g_o & (np.abs(np.arange(S)[None, :] / S - 0.5) > 0.06)], axis=0)
    white = np.median(ours[(lo > 200)], axis=0)
    lines = {}
    for side, cols in (("l", range(int(U_FIT[0] * S), int(U_FIT[1] * S))),
                       ("r", range(int((1 - U_FIT[1]) * S), int((1 - U_FIT[0]) * S)))):
        uu, tt, bb = [], [], []
        for x in cols:
            ys = np.nonzero(g_o[int(0.35 * S):int(0.62 * S), x])[0] + int(0.35 * S)
            if len(ys):
                uu.append((x + 0.5) / S)
                tt.append(ys.min() / S)
                bb.append((ys.max() + 1) / S)
        lines[side] = (np.polyfit(uu, tt, 1), np.polyfit(uu, bb, 1))
    return {"left": left, "right": right, "lines": lines, "green": green, "white": white}


U_FIT = (0.375, 0.405)             # столбцы, где линии кокетки нашей текстуры ровные (мимо ворота и нашивок)
U_IN = 0.40                        # дальше к середине — кокетка как есть (перенос NHL 24)


def yoke_heights(code, kit):
    """Высота нижнего края кокетки NHL 24 по |x| (спереди и сзади): самый низ цвета кокетки на её сетке (середина
    горловины — x = 0), сглажено. -> {"front": (x, y), "back": (x, y)}."""
    n24 = kit3d.load_nhl24()
    src = Hy.clean_color(code, kit)
    tid, bar = kit3d.raster_uv(n24, src.shape[0])
    ys, xs = np.nonzero(tid >= 0)
    T = n24["tri"][tid[ys, xs]]
    b = bar[ys, xs]
    P = (b[:, :, None] * n24["pos"][T]).sum(1)
    P[:, 0] += 0.0035                                    # середина горловины NHL 24 — на оси (CoordMap.x_fix)
    N = kit3d._unit((b[:, :, None] * n24["nrm"][T]).sum(1))
    c = src[ys, xs]
    g = (c.mean(1) < 80) & (c[:, 1] > c[:, 0] + 15)
    out = {}
    for side, sel in (("front", (P[:, 2] > 0) & (N[:, 2] > 0.3)), ("back", (P[:, 2] < 0) & (N[:, 2] < -0.3))):
        xx, hh = [], []
        for x0 in np.arange(0.04, 0.27, 0.01):
            m = sel & g & (np.abs(np.abs(P[:, 0]) - x0) < 0.005) & (P[:, 1] > 1.5) & (P[:, 1] < 1.75)
            if m.sum() > 20:
                xx.append(x0)
                hh.append(float(np.percentile(P[m, 1], 1)))
        hh = np.convolve(np.pad(hh, 2, mode="edge"), np.ones(5) / 5, mode="valid")
        out[side] = (np.concatenate([[0.0], xx]), np.concatenate([[hh[0]], hh]))
    # пользователь (19.10): «зелёную полосу спереди поднять, сзади опустить — по швам не сходится»: у NHL 24 перед
    # на 1,8 см ниже спины, у Edge на боку они сходятся на разной высоте; обе — на средней
    x_all = np.union1d(out["front"][0], out["back"][0])
    hf, hb = np.interp(x_all, *out["front"]), np.interp(x_all, *out["back"])
    # Средняя высота (перед выше на 0,9 см, спина ниже) — проба 19.10: спереди кромка ворота (1,26 см) съедала почти
    # всю зелёную полосу между воротом и вставкой. Швы рельефа теперь с NHL 24 (rebuild_relief) и совпадают с линией
    # на её высотах — поэтому YOKE_MIX = 0 (высоты NHL 24); 1 — средняя
    mid_full = (hf + hb) / 2
    hf, hb = hf + (mid_full - hf) * YOKE_MIX + YOKE_SHIFT, hb + (mid_full - hb) * YOKE_MIX + YOKE_SHIFT
    mid = None
    core = (x_all >= 0.06) & (x_all <= 0.16)             # прямой участок (мимо вставки и рукава)
    f0, b0 = np.interp(x_all, *out["front"]), np.interp(x_all, *out["back"])
    delta = (float(np.median((hf - f0)[core])), float(np.median((hb - b0)[core])))
    # перед — ровно от YOKE_FLAT_X к бокам (у NHL 24 линия к рукаву опускается на 1,4 см: на сетке Edge у угла с кривой
    # стороны EA выходил «зубец»)
    hf = np.where(x_all > YOKE_FLAT_X, np.interp(YOKE_FLAT_X, x_all, hf), hf)
    res = {"front": (x_all, hf), "back": (x_all, hb), "delta": delta}
    if YOKE_BACK_FROM:                                   # спина — как у EA-формы клуба (её край ниже: 1,60 м)
        from . import pilot
        ea = ea_yoke_heights(os.path.join(pilot.unpack(YOKE_BACK_FROM), "jersey_cm.png"))
        res["back"] = ea["back"]
    return res


class YokePaint:
    """pre-правка основы (fb.kit_hybrid.decal_post), кокетка целиком заново: нижний край — на высоте края NHL 24
    (yoke_heights: прямая спереди 1,63 м и сзади 1,648, к рукаву — вниз), бока — по краю кокетки EA (развёртка, кривые
    yoke_polygon); край сглажен (≈ 1 тексель). Перекрашивается только ткань двух цветов (и их смесь) дальше
    YOKE_COLLAR от края ворота; нашивки ложатся потом (decal_post), Reebok и вставка — после (порядок pre)."""

    def __init__(self, poly, keep_mask, mesh, heights):
        self.poly, self.keep, self.mesh, self.h = poly, keep_mask, mesh, heights
        self._geo = {}

    def geo(self, shape):
        if shape not in self._geo:
            tid, bar = kit3d.raster_uv(self.mesh, shape[::-1])
            m = tid >= 0
            P = np.zeros(shape + (3,))
            P[m] = (bar[m][:, :, None] * self.mesh["pos"][self.mesh["tri"][tid[m]]]).sum(1)
            # бока кокетки EA заданы в прежней развёртке Edge: у острова — его прежние UV (uv0)
            uv0 = self.mesh.get("uv0", self.mesh["uv"])
            U0 = np.zeros(shape + (2,))
            U0[m] = (bar[m][:, :, None] * uv0[self.mesh["tri"][tid[m]]]).sum(1)
            self._geo[shape] = (P, m, px_size(P[..., 1], m), U0)
        return self._geo[shape]

    def __call__(self, out, msk):
        from PIL import Image
        Hs, Ws = msk.shape
        P, m, GY, U0 = self.geo((Hs, Ws))
        u, v = U0[..., 0], U0[..., 1]
        Q = self.poly
        px = 1.0 / Ws
        left_side = u < 0.5
        dl = (u - np.interp(v, *Q["left"])) / (px * AA_PX)
        dr = (np.interp(v, *Q["right"]) - u) / (px * AA_PX)
        dside = np.where(left_side, dl, dr)
        ax = np.abs(P[..., 0])
        h = np.where(P[..., 2] >= 0, np.interp(ax, *self.h["front"]), np.interp(ax, *self.h["back"]))
        dh = (P[..., 1] - h) / GY
        dmin = np.minimum(dside, dh)
        cov = np.clip(0.5 + dmin, 0, 1)
        lace = (P[..., 2] > 0) & (ax < YOKE_LACE_X) & (P[..., 1] < YOKE_LACE_Y)   # вставка и шнурки — как есть
        zone = m & msk & (P[..., 1] > 1.45) & (dside > -YOKE_PAD * Ws) & ~lace
        keep = np.asarray(Image.fromarray(self.keep.astype(np.uint8) * 255).resize((Ws, Hs), Image.NEAREST)) > 0
        c = out[..., :3]
        g, w = Q["green"], Q["white"]
        seg = w - g
        t = np.clip(((c - g) * seg).sum(-1) / (seg * seg).sum(), 0, 1)
        dseg = np.linalg.norm(c - (g + t[..., None] * seg), axis=-1)
        trimc = (c[..., 0] > c[..., 1] + 60) & (c[..., 0] > 80)   # прежняя кромка/вставка (перерисуются позже)
        cloth = ((dseg < 40) | trimc) & zone & ~keep
        new = w[None, None] * (1 - cov[..., None]) + g[None, None] * cov[..., None]
        out = out.copy()
        out[..., :3] = np.where(cloth[..., None], new, c)
        return out


# Красная вставка под воротом (V-вырез adidas) — рисуется сама, по контуру NHL 24 в виде спереди: полуширина по
# высоте (м, середина горловины — x = 0), замер по текстуре NHL 24 на её сетке (выезд MIN, 19.10). Края — прямые
# (пользователь: «по краям должна быть ровная, а у тебя полукругами»): нижняя часть — узкий V между шнурками, выше —
# прямые расходящиеся края до самого широкого места (у линии кокетки), дальше — прямые сходящиеся к вороту.
INSERT_HW = ((1.583, 0.0), (1.610, 0.008), (1.629, 0.0426), (1.680, 0.0094))
# (угол — на высоте линии кокетки спереди у вставки, 1,629 м: на 1,625 между линией и углом торчал белый «зубец» —
# лесенка у стыка вставки и кокетки, пользователь, 19.10; верхний край — по-прежнему прямая от угла к вороту)
# (верх — продолжение той же прямой края к вороту, до кромки: раньше над 1,645 край шёл отвесно, и у угла с кромкой
# была ступенька — пользователь, 19.10, обведено кружками)
INSERT_LACE_Y = 1.617              # ниже — шнурки поверх вставки (тёмное не перекрашивается; 1,607 — верхний
#                                    шнурок прерывался)
INSERT_BAND = 0.015                # м за краем вставки — красное перекрашивается в ткань (там прежний перенос)
INSERT_KITS = {("MIN", "away"), ("MIN", "home")}
TRIM_SMOOTH = 25.0                 # град: сглаживание ширины кромки по углу
AA_PX = 2.0                        # ширина сглаживания краёв — в текселях сверхвыборки (×2): ≈ 1 тексель карты
TRIM_CLEAR = 0.008                  # м за кромкой — зубцы прежней кромки убираются
TRIM_INNER = 0.004                 # м: и на подвороте у края — кромкой
LACE_DIST = 70.0                   # |цвет − цвет шнурков| меньше — шнурок (не перекрашивается)
INSERT_TRIM = 0.0145                # м от края ворота — кромка (красная): вокруг вставки не перекрашивается


class InsertPaint:
    """pre-правка основы: вставка цветом red внутри контура INSERT_HW (по точке свитера в виде спереди), край сглажен
    по размеру текселя; рядом снаружи — красное → цвет ткани над/под линией кокетки (green/white, линия yoke_y)."""

    def __init__(self, mesh, red, green, white, yoke_y, lace):
        self.mesh, self.red, self.green, self.white, self.yoke_y, self.lace = mesh, red, green, white, yoke_y, lace
        self._geo = {}

    def geo(self, shape):
        if shape not in self._geo:
            tid, bar = kit3d.raster_uv(self.mesh, shape[::-1])
            m = tid >= 0
            P = np.zeros(shape + (3,))
            N = np.zeros(shape + (3,))
            P[m] = (bar[m][:, :, None] * self.mesh["pos"][self.mesh["tri"][tid[m]]]).sum(1)
            N[m] = kit3d._unit((bar[m][:, :, None] * self.mesh["nrm"][self.mesh["tri"][tid[m]]]).sum(1))
            w = Hy.Welded(self.mesh)
            ring = w.neck()
            zc = float(w.P[ring, 2].mean())
            band, lip = Hy.edge_layers(w, ring, zc)
            fold = Hy.fold_polyline(w, band)
            D = np.full(shape, 9.0)
            D[m] = Hy.ring_dist(P[m], Hy.smooth_curve(fold if fold is not None else Hy.lip_polyline(lip), zc, win=2.0))
            B = np.zeros(shape, bool)
            B[m] = band[w.g[self.mesh["tri"][tid[m]]]].all(1)
            # расстояние до края вставки — в пикселях развёртки: F / |∇F| (у пологих нижних краёв деление на размер
            # текселя по x давало переход в полтекселя — край шёл лесенкой)
            ys_, hs_ = zip(*INSERT_HW)
            F = np.interp(P[..., 1], ys_, hs_, left=-1.0, right=hs_[-1]) - np.abs(P[..., 0])
            front = m & ~B & (N[..., 2] > 0.2) & (P[..., 2] > 0.03)
            FP = F / px_size(F, front)
            self._geo[shape] = (P, N, m, D, B, FP)
        return self._geo[shape]

    def __call__(self, out, msk):
        Hs, Ws = msk.shape
        P, N, m, D, B, FP = self.geo((Hs, Ws))
        x, y = P[..., 0], P[..., 1]
        ys, hs = zip(*INSERT_HW)
        hw = np.interp(y, ys, hs, left=-1.0, right=hs[-1])
        cov = np.clip(0.5 + FP, 0, 1)
        front = m & msk & ~B & (N[..., 2] > 0.2) & (P[..., 2] > 0.03) & (y > ys[0] - 0.005) & (y < ys[-1])
        c = out[..., :3]
        # шнурки — поверх вставки (ниже INSERT_LACE_Y): по цвету шнурков NHL 24 (у выезда тёмно-зелёные, у дома
        # кремовые — раньше защищались только тёмные, и середину кремовых красило красным); только перекладины —
        # тонкие нити (1–2 текселя) уходят под красное
        from scipy import ndimage as ndi
        lace = (y < INSERT_LACE_Y) & (np.linalg.norm(c - self.lace[None, None], axis=-1) < LACE_DIST)
        lace = ndi.binary_opening(lace, structure=np.ones((3, 3), bool), iterations=1)
        # сначала красное прежнего переноса (и его смесь с тканью) вокруг и внутри контура → ткань, потом вставка с
        # мягким краем поверх чистой ткани: клин NHL 24 после переноса чуть правее нашего — справа край сглаживался
        # по красному и обрывался в ткань (ступенька у клина между шнурками, 19.10); кромку (у ворота) — не трогать
        redish = (c[..., 0] - np.maximum(c[..., 1], c[..., 2]) > 25) & (c[..., 0] > 60)
        zone = front & (np.abs(x) < hw + INSERT_BAND) & (D > INSERT_TRIM) & redish & ~lace
        bg = np.where((y > np.interp(np.abs(x), *self.yoke_y))[..., None], self.green[None, None], self.white[None, None])
        base = np.where(zone[..., None], bg, c)
        inside = front & (cov > 0) & ~lace
        new = base * (1 - cov[..., None]) + self.red[None, None] * cov[..., None]
        out = out.copy()
        out[..., :3] = np.where(inside[..., None], new, base)
        return out


def collar_keep_mask(mesh, size=1024):
    """Маска развёртки: ближе YOKE_COLLAR к краю ворота (кромка, подкладка, вставка) и «рубашка» вне свитера."""
    w = Hy.Welded(mesh)
    ring = w.neck()
    zc = float(w.P[ring, 2].mean())
    band, lip = Hy.edge_layers(w, ring, zc)
    fold = Hy.fold_polyline(w, band)
    tid, bar = kit3d.raster_uv(mesh, size)
    m = tid >= 0
    P = (bar[m][:, :, None] * mesh["pos"][mesh["tri"][tid[m]]]).sum(1)
    d = Hy.ring_dist(P, fold if fold is not None else Hy.lip_polyline(lip))
    keep = np.zeros(tid.shape, bool)
    keep[m] = (d < YOKE_COLLAR) | band[w.g[mesh["tri"][tid[m]]]].any(1)
    return keep


# Рельеф (пользователь, 19.10: «следы от старой текстуры — новая форма лежит поверх швов, прежде всего у переднего
# ворота»; кокетка «по швам не сходится»): у чистого рельефа Legacy T=4 — швы кроя Edge (V-вырез с планкой, кокетка,
# реглан). Новый рельеф туловища = складки Edge (рельеф без тонких линий: медиана + сглаживание) + плетение ткани Edge
# (ячейка 8 × 6 текселей, усреднена по спине и уложена в той же фазе) + швы NHL 24 (base_normal без спонсора, перенос по
# тем же координатам, что и рисунок, с пересчётом касательного базиса). Рукава — прежний рельеф (там швы Edge на месте).
RELIEF_REBUILD = True
Y_SUPPRESS = 1.50                  # м: выше — швы NHL 24 не берутся (там цвет рисуется здесь — свои швы по границам)
LACE_ZONE = (0.029, 1.580, 1.617)  # |x|, y от, y до: шнуровка — рельеф NHL 24 (шнурки, люверсы; 0,034 — в зону
#                                    попадал контур планки NHL 24: шов без смены цвета)
LACE_FADE = 0.003                  # м: край зоны — мягкий
# Планка под шнуровкой и обод вокруг шеи — как у NHL 24 (пользователь, 19.10, картинка 3.png: «шов вокруг шнуровки
# пусть будет вот такой; и такой же обод швов вокруг шеи, как в NHL 24»). У NHL 24 это одна линия: от плеч вниз по
# V (в ~3 см от края ворота), мимо угла вставки — в бок планки, по низу планки (пологий V к середине, углы скруглены)
# и вверх с другой стороны; посередине — шов от низа до нижнего шнурка. Замер — гребень карты швов NHL 24 (дом MIN,
# вид спереди, середина двойной линии; x — от середины горловины): половина планки от низа посередине до S —
# верха её бока (дальше — обод по расстоянию от края ворота, RING_KNOTS).
PLACKET_HALF = ((0.0, 1.5634), (0.0235, 1.5705), (0.0262, 1.5726), (0.0280, 1.5756), (0.0292, 1.5790),
                (0.0306, 1.5837), (0.0320, 1.5885), (0.0333, 1.5932), (0.0344, 1.5981), (0.0359, 1.6028),
                (0.0376, 1.6075), (0.0397, 1.6119))
PLACKET_CENTER = ((0.0, 1.5634), (0.0, 1.581))   # шов посередине — от низа до нижнего шнурка
# Обод: расстояние от края ворота (сглаженный сгиб) по |θ| — от S (свой угол и расстояние — по сетке) вверх по V:
# до ~36° — по линии NHL 24 в виде спереди (расстояния — её точки на нашей сетке), дальше — полоса за кромкой как у
# NHL 24 (кромка + 1,8–2,2 см: у Edge плечи не как у NHL 24, вид спереди там прижал бы обод к кромке), сзади — 3 см
RING = True
RING_KNOTS = ((23.7, 0.0502), (26.5, 0.0455), (32.0, 0.0355), (35.3, 0.0318), (40.0, 0.0305), (45.0, 0.0298),
              (50.0, 0.0295), (60.0, 0.0297), (75.0, 0.0300), (90.0, 0.0310), (120.0, 0.0320), (150.0, 0.0310),
              (180.0, 0.0305))


def placket_segments():
    """Отрезки планки в виде спереди (x, y): обе половины и шов посередине."""
    segs = []
    for sx in (-1.0, 1.0):
        pts = [(sx * x, y) for x, y in PLACKET_HALF]
        segs += list(zip(pts[:-1], pts[1:]))
    segs.append(PLACKET_CENTER)
    return segs
INSERT_SEAM_Y0 = 1.612             # м: ниже — край вставки у шнуровки (рельеф NHL 24)
SEAM_PROFILE = (0.30, 0.95, 0.12, 2.0, 0.8)   # глубина, ширина канавки, валик, его место, ширина — в текселях 1024
SEAM_GEN_GAIN = 1.0
FOLD_INPAINT = 4.0                 # текселей: складки под заглаженными швами — из соседних
N24_RELIEF_FLAT = [(0.465, 0.125, 0.535, 0.172),   # u0, v0, u1, v1 base_normal NHL 24: бирка на спине (под номером),
                   (0.398, 0.598, 0.462, 0.662),   # спонсор на груди (TRIA — у MIN; в цвете снят правилом [sponsor])
                   (0.538, 0.598, 0.602, 0.662)]   # и место второго спонсора
N24_SEAM_SIGMA = 6.0               # px (2048): что крупнее — складки NHL 24, не берутся
RELIEF_TOP_NY = (0.35, 0.6)        # y нормали: выше — прежний рельеф Edge (верх плеч)
WEAVE_CELL = (8, 6)                # период плетения в текселях (строки, столбцы) у карт 1024
WEAVE_SRC = (0.12, 0.30, 0.40, 0.60)   # v0, v1, u0, u1: участок спины без швов — по нему ячейка плетения
FOLD_MED, FOLD_SIGMA = 9, 3.0      # складки: медиана (убирает линии швов) и гаусс
SEAM_GAIN = 1.0                    # сила швов NHL 24


# Кокетка у NHL 24 (обе формы MIN) — сетчатая ткань: решётка ямок (шаг ~7 текселей 2048, ≈ 5–6 мм), только в рельефе,
# цвет ровный; внутри обода (полоса у шеи) ямок нет (пользователь, 19.10: «у погон решётчатая текстура, перенести»).
# Сила — как у NHL 24 (СКО наклона ямок ≈ 50 из 127, у плетения Edge — 6). Здесь — квадратная решётка с шагом
# PERF_CELL текселей карты 1024 (у Edge тексель ≈ 1,5–2 мм: шаг ≈ 6–8 мм; мельче 1024 не передаст), по решётке развёртки
# (на острове — island_weave: без шва через край острова).
PERF = True
PERF_CELL = (4, 4)                 # ячейка ямки (строки, столбцы), текселей
PERF_SIGMA = 0.85                  # радиус ямки (гаусс), текселей
PERF_RMS = 40.0                    # СКО наклона (xy карты, из 127,5)
PERF_SM = 6                        # блеск в ямке ниже на столько
SM_BASE = 18                       # блеск ткани: как у основных форм MIN (1_14_3/1_14_4: 16–18); прежний блеск Edge T=4
#                                    (медиана 30: V-вырез с молнией, реглан, сетка боков, Reebok) больше не берётся —
#                                    в игре он давал старые швы бликами (пользователь, 19.10)


def perf_tile(ss=8):
    """Ячейка ямки PERF_CELL (по кругу): наклон (xy, как у плетения; СКО — PERF_RMS) и глубина 0…1."""
    cy, cx = PERF_CELL
    yy, xx = np.mgrid[0:cy * ss, 0:cx * ss]
    fy, fx = (yy + 0.5) / ss, (xx + 0.5) / ss
    h = np.zeros(fy.shape)
    for oy in (-cy, 0, cy):
        for ox in (-cx, 0, cx):
            h -= np.exp(-((fy - cy / 2 - oy) ** 2 + (fx - cx / 2 - ox) ** 2) / (2 * PERF_SIGMA ** 2))
    gy, gx = np.gradient(h, 1.0 / ss)
    tile = np.stack([-gx, gy], -1).reshape(cy, ss, cx, ss, 2).mean((1, 3))
    tile *= PERF_RMS / np.sqrt((tile ** 2).sum(-1).mean())
    depth = ((h.max() - h) / (h.max() - h.min())).reshape(cy, ss, cx, ss).mean((1, 3))
    return tile, depth


def perf_mask(G, yk):
    """Тексели сетчатой ткани: кокетка (yoke_field > 0), вне полосы у шеи (за ободом), вне вставки и шнуровки."""
    P, N, m, D, B = G["P"], G["N"], G["m"], G["D"], G["B"]
    F = yoke_field(G, yk)
    R, _, _ = ring_field(G)
    x, y = P[..., 0], P[..., 1]
    ys_h, hs_h = (np.array(v) for v in zip(*INSERT_HW))
    hw = np.interp(y, ys_h, hs_h, left=-1.0, right=-1.0)
    front = (N[..., 2] > 0.2) & (P[..., 2] > 0.03)
    ins = front & (np.abs(x) < hw + 0.004)
    lace = front & (np.abs(x) < YOKE_LACE_X) & (y < YOKE_LACE_Y)
    out_band = np.isfinite(R) & (D > R + 0.002)
    return m & ~B & (F > 0.001) & out_band & ~ins & ~lace & (y > 1.45)


def perf_without_patches(pm, col, thr=40.0, max_hole=15000):
    """Маска сетки pm без нашивок (у NHL 24 на них ямок нет): тексели не цвета ткани кокетки (медиана по pm), закрытые и с
    залитыми дырами (внутри круглой нашивки — тот же зелёный; дыры больше max_hole — не нашивка), с запасом.
    -> (маска, сколько текселей убрано)."""
    from scipy import ndimage as ndi
    base = np.median(col[pm], axis=0)
    off = pm & (np.linalg.norm(col - base, axis=-1) > thr)
    off = ndi.binary_closing(off, iterations=2)
    holes = ndi.binary_fill_holes(off) & ~off
    lab, n = ndi.label(holes)
    if n:
        size = np.bincount(lab.ravel())
        small = size < max_hole
        small[0] = False
        off |= small[lab]
    off = ndi.binary_opening(off, iterations=1)         # одиночные тексели (край кокетки) — не нашивка
    off = ndi.binary_dilation(off, iterations=2)
    return pm & ~off, int((pm & off).sum())


def weave_tile(xy):
    """Ячейка плетения: высокие частоты рельефа (xy − складки) на участке WEAVE_SRC, усреднённые по остаткам
    (строка mod 8, столбец mod 6)."""
    from scipy import ndimage as ndi
    S = xy.shape[0]
    low = np.stack([ndi.gaussian_filter(ndi.median_filter(xy[..., c], FOLD_MED), FOLD_SIGMA) for c in range(2)], -1)
    hp = xy - low
    v0, v1, u0, u1 = (int(x * S) for x in WEAVE_SRC)
    cy, cx = WEAVE_CELL
    tile = np.zeros((cy, cx, 2))
    cnt = np.zeros((cy, cx, 1))
    for y in range(v0, v1):
        for x in range(u0, u1):
            tile[y % cy, x % cx] += hp[y, x]
            cnt[y % cy, x % cx] += 1
    return tile / np.maximum(cnt, 1), low


def island_folds(mesh, low, Tt, bb, Te, Be):
    """Складки (xy касательного пространства) в текселях острова: значения на краю острова — со складок прежнего
    места (uv0), в мировые векторы по прежнему базису; внутрь — гармонически по графу острова; в текселе — в базис
    острова (Te, Be)."""
    S = low.shape[0]
    isl_v = mesh["island"]
    tri_i = mesh["tri"][isl_v[mesh["tri"]].all(1)]
    w = Hy.Welded({"pos": mesh["pos"], "tri": tri_i, "uv": mesh["uv"], "nrm": mesh["nrm"]})
    # край острова: узлы, у которых есть вершина того же места вне острова
    from scipy.spatial import cKDTree
    out_v = np.nonzero(~isl_v)[0]
    kd = cKDTree(mesh["pos"][out_v])
    d, _ = kd.query(w.P)
    edge = d < 1e-6
    t_old, b_old = kit3d.vertex_tangents(dict(mesh, uv=mesh["uv0"]))
    uv0n = mesh["uv0"][w.first]
    lv = kit3d.sample_bilinear(low, uv0n[:, 0], uv0n[:, 1])
    To, Bo = t_old[w.first], b_old[w.first]
    world = To * lv[:, 0:1] + Bo * (-lv[:, 1:2])
    val = np.zeros((w.n, 3))
    val[edge] = world[edge]
    full = J.harmonic(w.A, val, edge)
    Wt = (bb[:, :, None] * full[w.g[Tt]]).sum(1)
    return np.stack([(Wt * Te).sum(1), -(Wt * Be).sum(1)], -1)


def cot_harmonic(P, T, val, known):
    """Гармоническое продолжение val (n, k) с узлов known по треугольникам T (котангенсные веса — без веера на
    сгущённых участках сетки, в отличие от равных весов графа)."""
    import scipy.sparse as sp
    import scipy.sparse.linalg as sla
    n = len(P)
    I, Jx, W = [], [], []
    for a_, b_, c_ in ((0, 1, 2), (1, 2, 0), (2, 0, 1)):
        i, j, k = T[:, a_], T[:, b_], T[:, c_]
        u, v = P[j] - P[i], P[k] - P[i]
        cot = (u * v).sum(1) / np.maximum(np.linalg.norm(np.cross(u, v), axis=1), 1e-12)
        cot = np.clip(cot, -1e3, 1e3) * 0.5
        I += [j, k]
        Jx += [k, j]
        W += [cot, cot]
    I, Jx, W = np.concatenate(I), np.concatenate(Jx), np.concatenate(W)
    Wm = sp.coo_matrix((W, (I, Jx)), shape=(n, n)).tocsr()
    L = sp.diags(np.asarray(Wm.sum(1)).ravel()) - Wm
    u = ~known & (np.asarray(np.abs(Wm).sum(1)).ravel() > 0)
    out = val.copy()
    if u.any():
        Luu = (L[u][:, u] + sp.identity(int(u.sum())) * 1e-9).tocsc()
        rhs = -(L[u][:, known] @ val[known])
        out[u] = np.stack([sla.spsolve(Luu, rhs[:, c]) for c in range(val.shape[1])], -1)
    return out


def island_weave(mesh, tile, Tt, bb, Te, Be, S, rpx=None):
    """Плетение в текселях острова: координаты решётки плетения q (тексели развёртки Edge, uv0·S) — на внешнем
    краю острова (с тканью свитера, дальше ISL_ANCHOR_D от ворота: там развёртка Edge не искажена) как у соседних
    текселей снаружи, внутрь — гармонически (котангенсные веса); плетение — из ячейки в точке q (по кругу,
    двулинейно), в базисе поля q → в базис острова. Через край острова — без шва: та же решётка."""
    from scipy.spatial import cKDTree
    isl_v = mesh["island"]
    tri_i = mesh["tri"][isl_v[mesh["tri"]].all(1)]
    vs = np.unique(tri_i)
    loc = -np.ones(len(mesh["pos"]), np.int64)
    loc[vs] = np.arange(len(vs))
    wi = Hy.Welded({"pos": mesh["pos"][vs], "tri": loc[tri_i], "uv": mesh["uv"][vs], "nrm": mesh["nrm"][vs]})
    node_v = vs[wi.first]                                # вершина острова в узле
    out_v = np.nonzero(~isl_v)[0]
    d, _ = cKDTree(mesh["pos"][out_v]).query(wi.P)
    wa = Hy.Welded(mesh)
    ring = wa.neck()
    zc = float(wa.P[ring, 2].mean())
    band, lip = Hy.edge_layers(wa, ring, zc)
    fold = Hy.fold_polyline(wa, band)
    dfold = Hy.ring_dist(wi.P, Hy.smooth_curve(fold if fold is not None else Hy.lip_polyline(lip), zc, win=2.0))
    # якоря: внешний край острова; у самого ворота (ISL_ANCHOR_NEAR) — нет, а спереди посередине (там развёртка Edge
    # растянута вдвое — бывшая полоса V-выреза) — только дальше ISL_ANCHOR_D; с боков шеи — и ближе (иначе решётка
    # у ворота сходилась веером)
    thn = Hy.theta_of(wi.P, zc)
    edge = (d < 1e-6) & (dfold > ISL_ANCHOR_NEAR) & ~((np.abs(thn) < ISL_ANCHOR_TH) & (dfold < ISL_ANCHOR_D))
    q = np.zeros((wi.n, 2))
    q[edge] = mesh["uv0"][node_v[edge]] * S
    q = cot_harmonic(wi.P, wi.T, q, edge)
    qv = np.zeros((len(mesh["pos"]), 2))
    qv[vs] = q[wi.g]
    qt = (bb[:, :, None] * qv[Tt]).sum(1)
    cy, cx = tile.shape[:2]
    fy, fx = qt[:, 1] - 0.5, qt[:, 0] - 0.5
    y0, x0 = np.floor(fy).astype(np.int64), np.floor(fx).astype(np.int64)
    ay, ax = (fy - y0)[:, None], (fx - x0)[:, None]

    def tl(r, c):
        return tile[r % cy, c % cx]
    wq = (tl(y0, x0) * (1 - ax) * (1 - ay) + tl(y0, x0 + 1) * ax * (1 - ay) + tl(y0 + 1, x0) * (1 - ax) * ay +
          tl(y0 + 1, x0 + 1) * ax * ay)
    t_q, b_q = kit3d.vertex_tangents(dict(mesh, uv=qv / S, tri=tri_i))
    Tq = kit3d._unit((bb[:, :, None] * t_q[Tt]).sum(1))
    Bq = kit3d._unit((bb[:, :, None] * b_q[Tt]).sum(1))
    world = Tq * wq[:, 0:1] + Bq * (-wq[:, 1:2])
    island_weave.resid = (int(edge.sum()), int(wi.n))
    return np.stack([(world * Te).sum(1), -(world * Be).sum(1)], -1)


def fourier_resample(a, shape):
    """Периодическая картинка a (h, w) → (H, W) той же формы периода (Фурье: дополнение нулями)."""
    h, w = a.shape
    H, W = shape
    F = np.fft.fftshift(np.fft.fft2(a))
    G = np.zeros((H, W), complex)
    y0, x0 = (H - h) // 2, (W - w) // 2
    G[y0:y0 + h, x0:x0 + w] = F
    return np.real(np.fft.ifft2(np.fft.ifftshift(G))) * (H * W) / (h * w)


def n24_tbn_normals(src, nmap24, UV):
    """Нормали NHL 24 (касательное пространство src, DirectX: зелёный — к −v) в точках развёртки UV → мир.
    -> (мир (N,3), найдено (N,))."""
    S = nmap24.shape[0]
    tid, bar = kit3d.raster_uv(src, S)
    x = np.clip((UV[:, 0] * S).astype(int), 0, S - 1)
    y = np.clip((UV[:, 1] * S).astype(int), 0, S - 1)
    t = tid[y, x]
    ok = t >= 0
    b = bar[y, x]
    tv, bv = kit3d.vertex_tangents(src)
    nv = kit3d._unit(src["nrm"])
    T = src["tri"][np.maximum(t, 0)]
    Tw = kit3d._unit((b[:, :, None] * tv[T]).sum(1))
    Bw = kit3d._unit((b[:, :, None] * bv[T]).sum(1))
    Nw = kit3d._unit((b[:, :, None] * nv[T]).sum(1))
    n = kit3d.sample_bilinear(nmap24, UV[:, 0], UV[:, 1])[:, :3] / 127.5 - 1.0
    w = Tw * n[:, 0:1] + Bw * (-n[:, 1:2]) + Nw * np.clip(n[:, 2:3], 0.05, 1)
    return kit3d._unit(w), ok


def relief_geometry(mesh, S):
    """Геометрия развёртки сетки (её UV) на S²: P, N, маска, D (до сглаженного сгиба ворота), TH, B (подворот), U0 (uv0),
    TS (м на тексель этого растра). Кешируется по (сетка, S)."""
    from scipy import ndimage as ndi
    key = (id(mesh), S)
    if key in _RGEO:
        return _RGEO[key]
    tid, bar = kit3d.raster_uv(mesh, S)
    m = tid >= 0
    T = mesh["tri"][tid[m]]
    b = bar[m]
    P = np.zeros((S, S, 3))
    N = np.zeros((S, S, 3))
    U0 = np.zeros((S, S, 2))
    P[m] = (b[:, :, None] * mesh["pos"][T]).sum(1)
    N[m] = kit3d._unit((b[:, :, None] * kit3d._unit(mesh["nrm"])[T]).sum(1))
    U0[m] = (b[:, :, None] * mesh.get("uv0", mesh["uv"])[T]).sum(1)
    w = Hy.Welded(mesh)
    ring = w.neck()
    zc = float(w.P[ring, 2].mean())
    band, lip = Hy.edge_layers(w, ring, zc)
    fold = Hy.fold_polyline(w, band)
    edge = Hy.smooth_curve(fold if fold is not None else Hy.lip_polyline(lip), zc, win=2.0)
    D = np.full((S, S), 9.0)
    D[m] = Hy.ring_dist(P[m], edge)
    TH = np.zeros((S, S))
    TH[m] = Hy.theta_of(P[m], zc)
    B = np.zeros((S, S), bool)
    B[m] = band[w.g[T]].all(1)
    # метров на тексель: по соседям внутри маски, медианой; пустое — ближайшим
    gx = np.full((S, S), np.nan)
    gy = np.full((S, S), np.nan)
    okx = m[:, 1:] & m[:, :-1]
    oky = m[1:, :] & m[:-1, :]
    dx = np.linalg.norm(P[:, 1:] - P[:, :-1], axis=-1)
    dy = np.linalg.norm(P[1:, :] - P[:-1, :], axis=-1)
    gx[:, :-1] = np.where(okx, dx, np.nan)
    gy[:-1, :] = np.where(oky, dy, np.nan)
    ts = np.sqrt(gx * gy)
    good = np.isfinite(ts) & (ts < np.nanpercentile(ts, 99.5) * 2)
    _, (iy, ix) = ndi.distance_transform_edt(~good, return_indices=True)
    ts = ts[iy, ix]
    ts = ndi.median_filter(ts, 5)
    # метров на единицу uv0 вдоль u (для расстояния до кривых сторон кокетки, заданных в uv0)
    du0 = np.full((S, S), np.nan)
    du0[:, :-1] = np.where(okx, np.abs(U0[:, 1:, 0] - U0[:, :-1, 0]), np.nan)
    mpu = gx / np.maximum(du0, 1e-9)
    good = np.isfinite(mpu) & (du0 > 1e-7)
    _, (iy, ix) = ndi.distance_transform_edt(~good, return_indices=True)
    mpu = ndi.median_filter(mpu[iy, ix], 5)
    _RGEO[key] = dict(P=P, N=N, m=m, U0=U0, D=D, TH=TH, B=B, TS=ts, MPU=mpu, zc=zc)
    return _RGEO[key]


_RGEO = {}


def seam_height(t):
    """Профиль шва по расстоянию t (тексели карты 1024) до линии: канавка посередине, валики по бокам."""
    a, s, lip, la, lw = SEAM_PROFILE
    return -a * np.exp(-(t / s) ** 2) + lip * np.exp(-((t - la) / lw) ** 2)


def ring_field(G):
    """Обод на растре relief_geometry G: R — расстояние обода от края ворота по |θ| (inf там, где обода нет: у
    середины переда, |θ| < θ_S, — там планка), dR — наклон по дуге (для расстояния по нормали), сводка θ_S/D_S."""
    from scipy.interpolate import PchipInterpolator
    P, N, m, D, TH, B = (G[k] for k in ("P", "N", "m", "D", "TH", "B"))
    x, y = P[..., 0], P[..., 1]
    pz = m & ~B & (N[..., 2] > 0.2) & (P[..., 2] > 0.03)
    r_xz = np.hypot(P[..., 0], P[..., 2] - G["zc"])
    Sx, Sy = PLACKET_HALF[-1]
    R = np.full(D.shape, np.inf)
    dR = np.zeros(D.shape)
    info = {}
    for sgn in (-1.0, 1.0):
        k_ = pz & (np.sign(x) == sgn)
        dd = np.where(k_, np.hypot(x - sgn * Sx, y - Sy), np.inf)
        i_ = np.unravel_index(np.argmin(dd), dd.shape)
        thS, DS = abs(float(TH[i_])), float(D[i_])
        kn = [(thS, DS)] + [(a, d_) for a, d_ in RING_KNOTS if a > thS + 1.0]
        f = PchipInterpolator([a for a, _ in kn], [d_ for _, d_ in kn])
        ta = np.clip(np.abs(TH), thS, 180.0)
        side = m & ~B & (TH * sgn > 0) & (np.abs(TH) >= thS)
        R = np.where(side, f(ta), R)
        dR = np.where(side, f.derivative()(ta) / np.maximum(r_xz * np.pi / 180.0, 0.02), dR)
        info["ring_S_%+d" % int(sgn)] = (round(thS, 1), round(DS * 100, 2))
    return R, dR, info


def yoke_field(G, yk):
    """Кокетка на растре G: F > 0 внутри (м до края: бока — кривые EA в uv0, низ — высоты yk.h), иначе < 0."""
    P, N, U0 = G["P"], G["N"], G["U0"]
    y, ax = P[..., 1], np.abs(P[..., 0])
    Q = yk.poly
    uL, uR = np.interp(U0[..., 1], *Q["left"]), np.interp(U0[..., 1], *Q["right"])
    dside = np.where(U0[..., 0] < 0.5, U0[..., 0] - uL, uR - U0[..., 0]) * G["MPU"]
    h = np.where(P[..., 2] >= 0, np.interp(ax, *yk.h["front"]), np.interp(ax, *yk.h["back"]))
    dh = (y - h) / np.maximum(np.sqrt(np.clip(1 - N[..., 1] ** 2, 0, 1)), 0.3)
    return np.minimum(dside, dh)


def design_seams(mesh, painters, S=2048, out_S=1024):
    """Швы по границам цветов, которые рисуются здесь же (кокетка, кромка ворота, вставка со щитом): высота по
    расстоянию до ближайшей границы → наклон нормали (касательное пространство карты out_S). -> (xy (out_S², 2),
    сводка). Границы (пользователь, 19.10: «границы цветов — по шву, лишних швов быть не должно»):
    - кромка: D = ширина кромки (TrimPaint.width), вне вставки;
    - вставка: |x| = INSERT_HW(y) от края ворота до INSERT_SEAM_Y0 (ниже — шнуровка: рельеф NHL 24);
    - кокетка: min(стороны по кривым EA в uv0, низ по высоте) вне кромки и вставки."""
    G = relief_geometry(mesh, S)
    P, N, m, U0, D, TH, B = (G[k] for k in ("P", "N", "m", "U0", "D", "TH", "B"))
    ts = G["TS"] * (S / out_S)                             # м на тексель карты out_S
    x, y = P[..., 0], P[..., 1]
    ax = np.abs(x)
    inf = np.full((S, S), np.inf)
    front = m & ~B & (N[..., 2] > 0.2) & (P[..., 2] > 0.03)
    ys_, hs_ = (np.array(v) for v in zip(*INSERT_HW))
    hw = np.interp(y, ys_, hs_, left=-1.0, right=-1.0)
    slope = np.interp(y, (ys_[1:] + ys_[:-1]) / 2, np.diff(hs_) / np.diff(ys_))
    F_i = hw - ax
    in_ins = front & (F_i > 0)
    d_i = np.where(front & (y > INSERT_SEAM_Y0) & (y < ys_[-1]) & (hw > 0), np.abs(F_i) / np.sqrt(1 + slope ** 2), inf)
    info = {}
    d_t = inf
    tr = painters.get("trim")
    if tr is not None:
        wid = np.interp(TH, tr.width[0], tr.width[1], period=360)
        d_t = np.where(m & ~B & ~in_ins, np.abs(wid - D), inf)
    else:
        wid = np.zeros((S, S))
    d_y = inf
    yk = painters.get("cur") or painters.get("yoke_shape")
    if yk is not None:
        F_y = yoke_field(G, yk)
        lace = (P[..., 2] > 0) & (ax < YOKE_LACE_X) & (y < YOKE_LACE_Y)
        d_y = np.where(m & ~B & ~in_ins & ~lace & (D > wid + 0.002) & (y > 1.45), np.abs(F_y), inf)
    # планка под шнуровкой (как у NHL 24: PLACKET_HALF) — отрезки в виде спереди (x, y), середина горловины — x = 0
    d_p = inf.copy()
    pz = m & ~B & (N[..., 2] > 0.2) & (P[..., 2] > 0.03)
    for (x0, y0), (x1, y1) in placket_segments():
        ex, ey = x1 - x0, y1 - y0
        L2 = ex * ex + ey * ey
        tt = np.clip(((x - x0) * ex + (y - y0) * ey) / L2, 0, 1)
        dd = np.hypot(x - (x0 + tt * ex), y - (y0 + tt * ey))
        d_p = np.where(pz, np.minimum(d_p, dd), d_p)
    # обод: от верха бока планки (S) — линия D = RING(|θ|) вокруг шеи (расстояние до неё — по нормали к ней: |D − R|
    # делится на √(1 + (dR/ds)²), у S линия круто уходит от ворота)
    d_r = inf.copy()
    if RING:
        R, dR, rinfo = ring_field(G)
        info.update(rinfo)
        side = np.isfinite(R) & ~in_ins & (D > wid + 0.004)
        d_r = np.where(side, np.abs(D - np.where(side, R, 0.0)) / np.sqrt(1.0 + dR ** 2), inf)
    # полосы рукава (пользователь, 19.10: «полосы на руках — ровно по шву»): швы по их границам — кольца по столбцам
    # развёртки рукава Edge (SleeveMap: полоса — столбец u)
    d_s = inf.copy()
    sb = painters.get("sleeve_bounds")
    if sb is not None and len(sb):
        u_, v_ = U0[..., 0], U0[..., 1]
        for sgn in (-1.0, 1.0):
            sE = u_ if sgn < 0 else 1.0 - u_
            k_ = m & (sE <= SLV_U[1]) & (v_ > SLV_V[0]) & (v_ < SLV_V[1]) & (x * sgn > SLV_X)
            dd = np.min(np.abs(sE[..., None] - np.asarray(sb)[None, None, :]), axis=-1) * G["MPU"]
            d_s = np.where(k_, np.minimum(d_s, dd), d_s)
    d_a = np.where(m & ~B, armhole_dist(G), inf)          # шов проймы Edge (низ, где делится цвет)
    d = np.minimum(np.minimum(np.minimum(np.minimum(np.minimum(np.minimum(d_i, d_t), d_y), d_p), d_r), d_s), d_a)
    t = d / np.maximum(ts, 1e-6)
    H = np.where(np.isfinite(t), seam_height(np.where(np.isfinite(t), t, 99.0)), 0.0)
    H = np.where(m, H, 0.0)
    design_seams.height = H.reshape(out_S, S // out_S, out_S, S // out_S).mean((1, 3))   # высота швов (превью меню)
    # наклон: dH на тексель out_S (тексель S — в S/out_S раз мельче)
    k = S / out_S
    gy_, gx_ = np.gradient(H)
    gx_, gy_ = gx_ * k, gy_ * k
    both = m.copy()
    both[:, 1:-1] &= m[:, 2:] & m[:, :-2]
    both[1:-1, :] &= m[2:, :] & m[:-2, :]
    gx_ = np.where(both, gx_, 0.0)
    gy_ = np.where(both, gy_, 0.0)
    xy = np.stack([-gx_, gy_], -1) * 127.5 * SEAM_GEN_GAIN
    f = S // out_S
    xy = xy.reshape(out_S, f, out_S, f, 2).mean((1, 3))
    for nm_, dd in (("insert", d_i), ("trim", d_t), ("yoke", d_y), ("placket", d_p), ("ring", d_r),
                    ("sleeve", d_s), ("armhole", d_a)):
        info[nm_] = int((np.isfinite(dd) & (dd < 0.002)).sum())
    return xy, info


def ea_yoke_heights(ea_png):
    """Высота нижнего края кокетки EA-формы (на сетке Edge) по |x|, спереди и сзади (самый низ её цвета), сглажено."""
    from PIL import Image
    from scipy import ndimage as ndi
    E = load(0, 1, 2)
    S = 1024
    ea = np.asarray(Image.open(ea_png).convert("RGB").resize((S, S))).astype(np.float64)
    g = (ea.mean(-1) < 90) & (ea[..., 1] > ea[..., 0] + 15)
    lab, _ = ndi.label(g)
    g = lab == lab[int(0.53 * S), int(0.37 * S)]
    tid, bar = kit3d.raster_uv(E, S)
    m = tid >= 0
    P = np.zeros((S, S, 3))
    N = np.zeros((S, S, 3))
    P[m] = (bar[m][:, :, None] * E["pos"][E["tri"][tid[m]]]).sum(1)
    N[m] = kit3d._unit((bar[m][:, :, None] * E["nrm"][E["tri"][tid[m]]]).sum(1))
    out = {}
    for side, sel in (("front", m & (P[..., 2] > 0.03) & (N[..., 2] > 0.3)),
                      ("back", m & (P[..., 2] < -0.03) & (N[..., 2] < -0.3))):
        xx, hh = [], []
        for x0 in np.arange(0.0, 0.27, 0.01):
            b_ = sel & g & (np.abs(np.abs(P[..., 0]) - x0) < 0.005) & (P[..., 1] > 1.5)
            if b_.sum() > 20:
                xx.append(x0)
                hh.append(float(np.percentile(P[..., 1][b_], 1)))
        hh = np.convolve(np.pad(hh, 2, mode="edge"), np.ones(5) / 5, mode="valid")
        out[side] = (np.array(xx), np.array(hh))
    return out


def rebuild_relief(nm_path, code, kit, mesh, cmap, n_jt, painters=None):
    """jersey_nm комплекта (рельеф Legacy T=4 после fb.pilot) → рельеф без лишних швов (пользователь, 19.10):
    - основа — складки Edge без швов (швы чистого рельефа T=4 — V-вырез, реглан, шов по верху плеча, линии кокетки —
      найдены детектором и заглажены) + плетение ткани Edge; в острове — гармонические складки и плетение под его
      плотность;
    - швы NHL 24 (тонкие, по тому же переносу, что и цвет) — только там, где цвет — тоже перенос NHL 24: ниже
      Y_SUPPRESS (полосы, низ, рукава) и шнуровка;
    - швы по границам цветов, нарисованных здесь (кокетка, кромка, вставка) — design_seams;
    - подворот ворота — прежний рельеф."""
    from PIL import Image
    from scipy import ndimage as ndi
    from . import kit_hybrid
    from .fonts import normal_map
    cur = np.asarray(Image.open(nm_path).convert("RGBA")).astype(np.float64)
    S = cur.shape[0]
    xy = cur[..., :2] - 127.5
    tile, low = weave_tile(xy)
    yy, xx = np.mgrid[0:S, 0:S]
    weave = tile[yy % WEAVE_CELL[0], xx % WEAVE_CELL[1]]
    # складки без швов: где детектор видит шов — складки дорисованы соседними (нормированная свёртка)
    det = seam_detector(xy)
    seam_m = ndi.binary_dilation(det > SEAM_THR, iterations=3)
    keep = (~seam_m).astype(np.float64)
    num = np.stack([ndi.gaussian_filter(low[..., c] * keep, FOLD_INPAINT) for c in range(2)], -1)
    den = ndi.gaussian_filter(keep, FOLD_INPAINT)[..., None]
    low = np.where(seam_m[..., None], num / np.maximum(den, 1e-6), low)
    # метки чистого рельефа T=4 на спине (RELIEF_CLEAR) — складками со строк рядом (плетение и сетка — свои, поверх)
    from . import kit_fix
    for u0, v0, u1, v1, dv in RELIEF_CLEAR:
        cm_ = ndi.gaussian_filter(ndi.binary_dilation(kit_fix._box(S, [u0, v0, u1, v1]), iterations=2).astype(np.float64),
                                  2.0)[..., None]
        low = low * (1 - cm_) + np.roll(low, -int(round(dv * S)), axis=0) * cm_
    # швы NHL 24: base_normal без спонсорских нашивок (как у цвета — clean_color)
    bn = normal_map(J.n24_tex(Hy.CLUB_NAME[code], kit, "base_normal"), 2048).astype(np.float64)
    defaults, rules = kit_hybrid.load_rules(kit_hybrid.RULES, code, kit, [])
    sp = tuple(k for k, r in rules.items() if r.get("sponsor"))
    bn, _, _ = kit_hybrid.standard_patches(bn, rules, defaults, names=sp)
    for u0, v0, u1, v1 in N24_RELIEF_FLAT:
        S2 = bn.shape[0]
        bn[int(v0 * S2):int(v1 * S2), int(u0 * S2):int(u1 * S2), :3] = (128, 128, 255)
    nxy = bn[..., :2] / 127.5 - 1.0
    nxy = nxy - np.stack([ndi.gaussian_filter(nxy[..., c], N24_SEAM_SIGMA) for c in range(2)], -1)
    bn = bn.copy()
    bn[..., :2] = (nxy + 1.0) * 127.5
    bn[..., 2] = (np.sqrt(np.clip(1 - (nxy ** 2).sum(-1), 0, 1)) + 1.0) * 127.5
    Sg = 2048
    gu, gv = np.meshgrid((np.arange(Sg) + 0.5) / Sg, (np.arange(Sg) + 0.5) / Sg)
    uvimg = np.dstack([gu, gv, np.zeros_like(gu)])
    uvmap, mask, _, _ = coord_transfer(uvimg, cmap.src, mesh, S, 1, None, len(mesh["tri"]), cmap)
    tid, bar = kit3d.raster_uv(mesh, S)
    m = tid >= 0
    T = mesh["tri"][tid[m]]
    b = bar[m]
    band = cmap.band_v[T].all(1)
    UV = uvmap[m][:, :2]
    nw, ok = n24_tbn_normals(cmap.src, bn, UV)
    te, be = kit3d.vertex_tangents(mesh)
    Te = kit3d._unit((b[:, :, None] * te[T]).sum(1))
    Be = kit3d._unit((b[:, :, None] * be[T]).sum(1))
    seam24 = np.stack([(nw * Te).sum(1), -(nw * Be).sum(1)], -1) * 127.5 * SEAM_GAIN
    seam24[~ok] = 0
    Pm = (b[:, :, None] * mesh["pos"][T]).sum(1)
    f = LACE_FADE
    lace = (Pm[:, 2] > 0.03) * Hy.smooth((LACE_ZONE[0] - np.abs(Pm[:, 0])) / f) *         Hy.smooth((Pm[:, 1] - LACE_ZONE[1]) / f) * Hy.smooth((LACE_ZONE[2] - Pm[:, 1]) / f)
    ins = (painters or {}).get("insert")
    cm_path = os.path.join(os.path.dirname(nm_path), "jersey_cm.png")
    if ins is not None and os.path.exists(cm_path):
        # внутри зоны — только шнурки и люверсы (не цвет вставки и не цвет ткани вокруг), с запасом 2 текселя
        col = np.asarray(Image.open(cm_path).convert("RGB")).astype(np.float64)
        img_l = np.zeros((S, S))
        yy_, xx_ = np.nonzero(m)
        cc = col[yy_, xx_]
        dr = np.linalg.norm(cc - ins.red[None], axis=1)
        dg = np.minimum(np.linalg.norm(cc - ins.green[None], axis=1), np.linalg.norm(cc - ins.white[None], axis=1))
        img_l[yy_, xx_] = ((dr > 60) & (dg > 60)).astype(np.float64)
        img_l = ndi.gaussian_filter(ndi.binary_dilation(img_l > 0.5, iterations=2).astype(np.float64), 1.0)
        lace = lace * np.clip(img_l[yy_, xx_] * 1.5, 0, 1)
    keep24 = np.maximum(1.0 - Hy.smooth((Pm[:, 1] - Y_SUPPRESS + 0.01) / 0.02), lace)
    painters = dict(painters or {})
    if getattr(cmap, "sleeve", None) is not None:
        tex24 = np.asarray(Image.open(J.n24_tex(Hy.CLUB_NAME[code], kit, "base_color")).convert("RGB")).astype(np.float64)
        b24, bE = cmap.sleeve.stripes(tex24)
        painters["sleeve_bounds"] = bE
        print("  полосы рукава: границы u NHL 24", np.round(b24, 4).tolist(), "→ Edge", np.round(bE, 4).tolist())
        if len(bE):
            G0 = relief_geometry(mesh, S)
            u_m, v_m = G0["U0"][m][:, 0], G0["U0"][m][:, 1]
            mpu = G0["MPU"][m]
            for sgn in (-1.0, 1.0):
                sE = u_m if sgn < 0 else 1.0 - u_m
                k_ = (sE <= SLV_U[1]) & (v_m > SLV_V[0]) & (v_m < SLV_V[1]) & (Pm[:, 0] * sgn > SLV_X)
                dd = np.min(np.abs(sE[:, None] - bE[None, :]), axis=1) * mpu
                keep24 = np.where(k_, keep24 * Hy.smooth((dd - 0.002) / 0.002), keep24)
    G0 = relief_geometry(mesh, S)
    da = armhole_dist(G0)[m]
    keep24 = keep24 * np.where(np.isfinite(da), Hy.smooth((da - 0.004) / 0.004), 1.0)
    new_xy = xy.copy()
    ys, xs = np.nonzero(m)
    wv = weave[ys, xs].copy()
    low_px = low[ys, xs].copy()
    it = np.zeros(len(ys), bool)
    rpx = None
    if "island" in mesh:
        it = mesh["island"][T].all(1)
        if it.any():
            # складки острова — складки Edge (уже без швов: детектор и дорисовка выше) с прежнего места (uv0), в
            # базисе острова: и значение, и наклон непрерывны через край острова (гармоническое продолжение давало
            # излом на краю — видимую линию)
            uv0i = (b[it][:, :, None] * mesh["uv0"][T[it]]).sum(1)
            lo = np.stack([kit3d.sample_bilinear(low[..., c:c + 1], uv0i[:, 0], uv0i[:, 1])[:, 0] for c in range(2)], -1)
            t_o, b_o = kit3d.vertex_tangents(dict(mesh, uv=mesh["uv0"]))
            To_ = kit3d._unit((b[it][:, :, None] * t_o[T[it]]).sum(1))
            Bo_ = kit3d._unit((b[it][:, :, None] * b_o[T[it]]).sum(1))
            wl = To_ * lo[:, 0:1] + Bo_ * (-lo[:, 1:2])
            low_px[it] = np.stack([(wl * Te[it]).sum(1), -(wl * Be[it]).sum(1)], -1)
            im = np.zeros((S, S), bool)
            im[ys[it], xs[it]] = True
            rpx = ndi.distance_transform_edt(im)[ys[it], xs[it]]
            wv[it] = island_weave(mesh, tile, T[it], b[it], Te[it], Be[it], S, rpx)
            print("  плетение острова: якорей / узлов", island_weave.resid)
    # сетчатая кокетка: ямки вместо плетения Edge (та же решётка; на острове — island_weave с ячейкой ямок)
    yk = painters.get("cur") or painters.get("yoke_shape")
    perf = np.zeros(len(ys), bool)
    pdepth = np.zeros(len(ys))
    if PERF and yk is not None:
        ptile, pdep = perf_tile()
        pm = perf_mask(relief_geometry(mesh, S), yk)
        if os.path.exists(cm_path):                     # нашивки и надписи (не цвет ткани кокетки) — без ямок
            col = np.asarray(Image.open(cm_path).convert("RGB").resize((S, S), Image.BILINEAR)).astype(np.float64)
            pm, n_patch = perf_without_patches(pm, col)
            print(f"  сетчатая кокетка: без нашивок — {n_patch} текселей")
        perf = pm[ys, xs]
        cy_, cx_ = PERF_CELL
        pw = ptile[ys % cy_, xs % cx_].copy()
        pdepth = pdep[ys % cy_, xs % cx_].copy()
        if it.any():
            pw[it] = island_weave(mesh, ptile, T[it], b[it], Te[it], Be[it], S, rpx)
            pd2 = np.stack([pdep, np.zeros_like(pdep)], -1)          # глубина — та же выборка (длина вектора)
            pdepth[it] = np.linalg.norm(island_weave(mesh, pd2, T[it], b[it], Te[it], Be[it], S, rpx), axis=1)
        wv = np.where(perf[:, None], pw, wv)
        print(f"  сетчатая кокетка: {int(perf.sum())} текселей")
    gen, ginfo = design_seams(mesh, painters, out_S=S)
    # кромка ворота и вставка со щитом — гладкая ткань (у NHL 24 на них нет сетки плетения; на кромке у ворота
    # решётка плетения к тому же сходилась веером): плетение — на нет, край — по шву
    G1 = relief_geometry(mesh, S)
    plain = np.zeros(len(ys))
    tr = (painters or {}).get("trim")
    if tr is not None:
        wid = np.interp(G1["TH"][ys, xs], tr.width[0], tr.width[1], period=360)
        plain = np.maximum(plain, Hy.smooth((wid + 0.001 - G1["D"][ys, xs]) / 0.002))
    yi_, xi_ = G1["P"][ys, xs, 1], np.abs(G1["P"][ys, xs, 0])
    ys_h, hs_h = (np.array(v) for v in zip(*INSERT_HW))
    hw = np.interp(yi_, ys_h, hs_h, left=-1.0, right=-1.0)
    fr_ = (G1["N"][ys, xs, 2] > 0.2) & (G1["P"][ys, xs, 2] > 0.03) & (yi_ > INSERT_SEAM_Y0)
    plain = np.maximum(plain, fr_ * Hy.smooth((hw + 0.001 - xi_) / 0.002))
    wv = wv * (1.0 - plain)[:, None]
    body_xy = low_px + wv + seam24 * keep24[:, None] + gen[ys, xs]
    new_xy[ys, xs] = np.where(band[:, None], xy[ys, xs], body_xy)
    # текселям вне треугольников (в т. ч. прежнее место острова — там старый рельеф V-выреза Edge) — значение
    # ближайшего своего: иначе фильтрация на краю соседних текселей подмешивала старое (тонкие «трещины»)
    _, (iy, ix) = ndi.distance_transform_edt(~m, return_indices=True)
    new_xy = new_xy[iy, ix]
    z = np.sqrt(np.clip(127.5 ** 2 - (new_xy ** 2).sum(-1), 0, None))
    out = cur.copy()
    out[..., 0], out[..., 1], out[..., 2] = new_xy[..., 0] + 127.5, new_xy[..., 1] + 127.5, z + 127.5
    Image.fromarray(np.clip(np.round(out), 0, 255).astype(np.uint8), "RGBA").save(nm_path)
    # блеск: ровная ткань, в ямках сетчатой кокетки — тусклее (Reebok сзади кладёт потом BrandSwap.relief)
    # глубина швов и ямок сетки (для превью меню: там рельеф 256² не различить — затенение по глубине)
    pd_map = np.zeros((S, S))
    pd_map[ys, xs] = np.clip(pdepth, 0, 1) * perf
    np.savez_compressed(os.path.join(os.path.dirname(nm_path), "relief_depth.npz"),
                        seam=design_seams.height.astype(np.float16), perf=pd_map.astype(np.float16))
    sm_path = os.path.join(os.path.dirname(nm_path), "jersey_sm.png")
    smv = np.full((S, S), float(SM_BASE))
    smv[ys, xs] = SM_BASE - PERF_SM * np.clip(pdepth, 0, 1) * perf
    sm = np.dstack([smv, smv, smv, np.full((S, S), 255.0)])
    Image.fromarray(np.clip(np.round(sm), 0, 255).astype(np.uint8), "RGBA").save(sm_path)
    return {"seams_removed_px": int(seam_m.sum()), "n24_kept": float((keep24 > 0.5).mean()),
            "design_seams": ginfo, "perf_texels": int(perf.sum())}


def px_size(F, m):
    """Размер текселя (в единицах поля F) по градиенту F на развёртке: для сглаживания края на ~AA_PX текселя по месту
    (у ворота Edge тексель — 1,2–3 мм, у груди — 2): с постоянной шириной края в метрах он местами выходил ступенькой."""
    from scipy import ndimage as ndi
    gy, gx = np.gradient(np.where(m, F, 0.0))
    g = np.hypot(gx, gy)
    g = np.where(m & (g < np.percentile(g[m], 99) * 3), g, np.nan)
    med = np.nanmedian(g)
    g = np.where(np.isnan(g), med, g)
    return ndi.median_filter(g, 5) * AA_PX


class TrimPaint:
    """pre-правка основы: кромка ворота — полоса постоянной (по углу — плавной) ширины от края ворота (сглаженный сгиб),
    цветом кромки NHL 24, край сглажен по текселю (пользователь, 19.10: «окантовка у шильдика неровная»). Ширина — как
    у NHL 24 по углу (сглажено ±TRIM_SMOOTH°) × TRIM_K."""

    def __init__(self, mesh, color, width, lining=None, body=None):
        self.mesh, self.color, self.width, self.lining, self.body = mesh, color, width, lining, body
        self._geo = {}

    def geo(self, shape):
        if shape not in self._geo:
            w = Hy.Welded(self.mesh)
            ring = w.neck()
            zc = float(w.P[ring, 2].mean())
            band, lip = Hy.edge_layers(w, ring, zc)
            fold = Hy.fold_polyline(w, band)
            edge = Hy.smooth_curve(fold if fold is not None else Hy.lip_polyline(lip), zc, win=2.0)
            tid, bar = kit3d.raster_uv(self.mesh, shape[::-1])
            m = tid >= 0
            P = (bar[m][:, :, None] * self.mesh["pos"][self.mesh["tri"][tid[m]]]).sum(1)
            D = np.full(shape, 9.0)
            D[m] = Hy.ring_dist(P, edge)
            TH = np.zeros(shape)
            TH[m] = Hy.theta_of(P, zc)
            B = np.zeros(shape, bool)
            B[m] = band[w.g[self.mesh["tri"][tid[m]]]].all(1)
            G = px_size(D, m & ~B)
            self._geo[shape] = (D, TH, B, m, G)
        return self._geo[shape]

    def __call__(self, out, msk):
        Hs, Ws = msk.shape
        D, TH, B, m, G = self.geo((Hs, Ws))
        th_w, w_w = self.width
        wid = np.interp(TH, th_w, w_w, period=360)
        texel = 0.0021 * 1024 / Ws
        cov = np.clip(0.5 + (wid - D) / G, 0, 1)
        cov = np.where(B, (D < TRIM_INNER).astype(float), cov)
        zone = m & msk & (D < wid + 3 * texel)
        out = out.copy()
        c = out[..., :3]
        # прежняя кромка шире новой (зубцы) — снаружи, до TRIM_CLEAR: цвет кромки → ближайший пиксель ткани
        from scipy import ndimage as ndi
        # за кромкой (до TRIM_CLEAR) — прежний перенос (растянутая кромка) → ровный цвет ткани (self.body; у формы с
        # кокеткой YokePaint там уже перекрасил — body = None). Раньше — копия ближайшего пикселя дальше: от неё
        # шли полосы «бахромой» (пользователь, 19.10: «вот тут прям говно»)
        if self.body is not None:
            bad = m & msk & ~B & (D > wid) & (D < wid + TRIM_CLEAR) &                 (np.linalg.norm(c - self.body[None, None], axis=-1) > 20)
            c = c.copy()
            c[bad] = self.body
        if self.lining is not None:                       # подворот ниже кромки — ровной подкладкой (были пятна)
            c = c.copy()
            c[m & msk & B] = self.lining
        new = c * (1 - cov[..., None]) + self.color[None, None] * cov[..., None]
        out[..., :3] = np.where((zone | (m & msk & B))[..., None], new, c)
        return out


def trim_rule(code, kit, mesh, with_yoke=False):
    """TrimPaint: цвет кромки — медиана у края ворота NHL 24, ширина по углу — замер на NHL 24, сглажено, × TRIM_K."""
    from scipy.sparse.csgraph import connected_components
    n24 = kit3d.load_nhl24()
    src = Hy.clean_color(code, kit)
    w = Hy.Welded(n24)
    _, comp = connected_components(w.A, directed=False)
    main = np.bincount(comp).argmax()
    bnd = w.boundary()
    ring = w.neck(bnd[comp[bnd] == main])
    zc = float(w.P[ring, 2].mean())
    poly = Hy.ring_polyline(w, ring)
    tid, bar = kit3d.raster_uv(n24, src.shape[0])
    ys, xs = np.nonzero(tid >= 0)
    T = n24["tri"][tid[ys, xs]]
    keep = comp[w.g[T[:, 0]]] == main
    ys, xs, T = ys[keep], xs[keep], T[keep]
    P = (bar[ys, xs][:, :, None] * n24["pos"][T]).sum(1)
    d = Hy.ring_dist(P, poly)
    th = Hy.theta_of(P, zc)
    c = src[ys, xs]
    near = d < 0.003
    col = np.median(c[near], axis=0)
    is_trim = np.linalg.norm(c - col, axis=1) < 60
    ths, wds = [], []
    for a in np.arange(-180, 180, 10.0):
        sel = (np.abs(((th - a) + 180) % 360 - 180) < 6) & (d < 0.03)
        r = sel & is_trim
        if r.sum() > 10 and not (abs(a) < 40):           # спереди у середины — вставка того же цвета: не в счёт
            ths.append(a)
            wds.append(float(np.percentile(d[r], 95)))
    ths, wds = np.array(ths), np.array(wds)
    full = np.arange(-180, 180, 1.0)
    wf = np.interp(full, ths, wds, period=360)
    k = int(TRIM_SMOOTH)
    ker = np.exp(-0.5 * (np.arange(-2 * k, 2 * k + 1) / k) ** 2)
    ker /= ker.sum()
    wf = np.convolve(np.concatenate([wf[-2 * k:], wf, wf[:2 * k]]), ker, mode="valid")
    print("  кромка: цвет", np.round(col).tolist(), "ширина, см:",
          {int(a): round(float(np.interp(a, full, wf)) * 100 * TRIM_K, 2) for a in (0, 45, 90, 135, 180)})
    tl, bl = kit3d.raster_uv(n24, src.shape[0])
    yl, xl = np.nonzero(tl >= 0)
    lin_t = comp[w.g[n24["tri"][tl[yl, xl], 0]]] != main
    lining = np.median(src[yl[lin_t], xl[lin_t]], axis=0)
    # ткань у ворота (под кромкой, сзади и с боков): у формы без кокетки — одним цветом
    body_c = np.median(c[(d > 0.02) & (d < 0.035) & (np.abs(np.abs(th) - 120) < 40)], axis=0)
    return TrimPaint(mesh, col, (full, wf * TRIM_K), lining, None if with_yoke else body_c)


def brand_alpha():
    """Форма надписи Reebok EA (как kit_fix.BrandSwap.src_a)."""
    from PIL import Image
    from . import kit_fix, pilot
    rule = kit_fix._rules()["brand"]
    ea = np.asarray(Image.open(os.path.join(pilot.unpack(rule["from"]), "jersey_cm.png")).convert("RGB")
                    .resize((1024, 1024))).astype(np.float64)
    u0, v0, u1, v1 = (int(round(x * 1024)) for x in rule["src_box"])
    win = ea[v0:v1, u0:u1] @ np.array([0.299, 0.587, 0.114])
    bg, fg = np.percentile(win, 10), np.percentile(win, 99)
    return np.clip((win - bg) / max(fg - bg, 1.0), 0, 1)


def insert_rule(ours_png, mesh, code, kit):
    """InsertPaint по первой сборке: красный — середина вставки NHL 24 (кромка ворота спереди), ткань и кокетка — с
    нашей текстуры, линия кокетки спереди — высота перехода цветов на нашей сетке (по |x|)."""
    from PIL import Image
    from scipy.sparse.csgraph import connected_components
    src = Hy.clean_color(code, kit)
    n24 = kit3d.load_nhl24()
    tid, bar = kit3d.raster_uv(n24, src.shape[0])
    wn = Hy.Welded(n24)
    _, comp = connected_components(wn.A, directed=False)
    main_t = comp[wn.g[n24["tri"][:, 0]]] == np.bincount(comp).argmax()
    ys, xs = np.nonzero((tid >= 0) & main_t[np.maximum(tid, 0)])      # только наружная оболочка (не подкладка)
    P = (bar[ys, xs][:, :, None] * n24["pos"][n24["tri"][tid[ys, xs]]]).sum(1)
    c = src[ys, xs]
    sel = (np.abs(P[:, 0] + 0.0035) < 0.045) & (np.abs(P[:, 1] - 1.625) < 0.012) & (P[:, 2] > 0.05)
    reds = sel & (c[:, 0] > c[:, 1] + 60)                # красное вставки (мимо щита)
    red = np.median(c[reds], axis=0)
    ours = np.asarray(Image.open(ours_png).convert("RGB")).astype(np.float64)
    lo = ours.mean(-1)
    white = np.median(ours[lo > 200], axis=0)
    g = (lo < 70) & (ours[..., 1] > ours[..., 0] + 15)
    green = np.median(ours[g], axis=0)
    # линия кокетки спереди на нашей сетке: по столбцам |x| 0,05…0,15 — высота перехода «кокетка → ткань»
    t2, b2 = kit3d.raster_uv(mesh, 1024)
    m = t2 >= 0
    Pm = (b2[m][:, :, None] * mesh["pos"][mesh["tri"][t2[m]]]).sum(1)
    cm = ours[m]
    isg = (cm.mean(-1) < 70) & (cm[:, 1] > cm[:, 0] + 15)
    front = (Pm[:, 2] > 0.05) & (Pm[:, 1] > 1.55) & (Pm[:, 1] < 1.70)
    xs_, ys_ = [], []
    for x0 in np.arange(0.04, 0.16, 0.01):
        sl = front & (np.abs(np.abs(Pm[:, 0]) - x0) < 0.005)
        gy = Pm[sl & isg, 1]
        if len(gy):
            xs_.append(x0)
            ys_.append(float(np.percentile(gy, 2)))
    yoke_y = (np.array(xs_), np.array(ys_))
    # цвет шнурков: у NHL 24 в столбце шнуровки — не цвет вставки и не ткани вокруг
    lz = (np.abs(P[:, 0] + 0.0035) < 0.03) & (P[:, 1] > 1.585) & (P[:, 1] < 1.612) & (P[:, 2] > 0.05)
    body = np.median(c[(np.abs(P[:, 0] + 0.0035) > 0.035) & (np.abs(P[:, 0] + 0.0035) < 0.05) & (P[:, 1] > 1.59) &
                       (P[:, 1] < 1.61) & (P[:, 2] > 0.05)], axis=0)
    cand = lz & (np.linalg.norm(c - red, axis=1) > 80) & (np.linalg.norm(c - body, axis=1) > 80)
    lace = np.median(c[cand], axis=0) if cand.sum() > 20 else body
    print("  вставка: красный", np.round(red).tolist(), "шнурки", np.round(lace).tolist(), "ткань", np.round(body).tolist(),
          "линия кокетки спереди", np.round(ys_, 3).tolist())
    return InsertPaint(mesh, red, green, white, yoke_y, lace)


# ---------------------------------------------------------------- швы Edge: что оставить, что стереть (19.10, вечер)

# Пользователь (19.10): «границы цветов должны проходить по шву, лишних швов быть не должно; на спине зелёное кончается
# слишком высоко» (раньше: «спереди поднимать, сзади опускать — по швам не сходится»). Швы кроя Edge в чистом рельефе
# T=4 (развёртка Edge, uv0): линии реглана — спереди v = 0,561 (≈ 1,65 м на |x| 0,14–0,18), сзади v = 0,3916
# (≈ 1,616) — прямые на развёртке, вдоль всей руки; шов по верху плеча v ≈ 0,48; диагонали от горловины сзади к линии
# реглана; V-вырез и его мысок спереди. Кокетка — между линиями реглана (по шву), бока — кривые EA (там шва у Edge нет —
# рисуется свой); шов по верху плеча, диагонали сзади и V-вырез — стираются (сдвигом ткани по решётке плетения).
RAGLAN_V = (0.3916, 0.561)         # uv0: линии реглана — спина, грудь (замер по рельефу T=4)
SEAM_THR = 4.0                     # |div − её сглаженная| (медиана 5): выше — шов (складки ниже)
SEAM_MIN_PX = 60                   # и связная часть не меньше
CLEAN_MARGIN = 0.008               # uv: от линий, которые остаются (реглан, кромка), — не стирать
SHIFTS = [(0, 6), (0, -6), (0, 12), (0, -12), (24, 0), (-24, 0), (0, 18), (0, -18), (24, 6), (24, -6), (-24, 6),
          (-24, -6), (0, 24), (0, -24), (48, 0), (-48, 0), (24, 12), (-24, 12), (24, -12), (-24, -12)]
# ↑ сдвиги по решётке плетения: у ткани Edge решётки (0, 2)/(2, 0), (0, 3)/(3, 0), (8, 0)/(4, 3) — сдвиги (0, 6k) и
#   (24k, 0) — общие для всех


def seam_detector(xy):
    """Где у рельефа швы (тонкие резкие линии): |дивергенция − её сглаженная| по медиане 5 (плетение подавлено)."""
    from scipy import ndimage as ndi
    sm = np.stack([ndi.median_filter(xy[..., c], 5) for c in range(2)], -1)
    div = np.gradient(sm[..., 0], axis=1) + np.gradient(-sm[..., 1], axis=0)
    return np.abs(div - ndi.gaussian_filter(div, 3))


def shift_fill(xy, mask, valid, shifts=SHIFTS):
    """Пиксели mask (шов) — тканью со сдвигом по решётке плетения: высокие частоты — из ближайшего по списку сдвигов
    пикселя вне mask (и внутри valid), низкие (складки) — свои, нормированной свёрткой без mask."""
    from scipy import ndimage as ndi
    keep = valid & ~mask
    k = keep.astype(np.float64)
    low = np.stack([ndi.gaussian_filter(xy[..., c] * k, 4) for c in range(2)], -1) / \
        np.maximum(ndi.gaussian_filter(k, 4), 1e-6)[..., None]
    hp = xy - low
    out = xy.copy()
    todo = mask & valid
    H, W = mask.shape
    for dy, dx in shifts:
        if not todo.any():
            break
        ys, xs = np.nonzero(todo)
        sy, sx = ys + dy, xs + dx
        ok = (sy >= 0) & (sy < H) & (sx >= 0) & (sx < W)
        ys, xs, sy, sx = ys[ok], xs[ok], sy[ok], sx[ok]
        good = keep[sy, sx]
        ys, xs, sy, sx = ys[good], xs[good], sy[good], sx[good]
        out[ys, xs] = low[ys, xs] + hp[sy, sx]
        todo[ys, xs] = False
    out[todo] = low[todo]                                  # что не нашлось — гладкой тканью
    return out


def edge_layout(E):
    """Геометрия развёртки Edge (uv0) на сетке E: позиции P, расстояние до сгиба ворота D, угол θ, подворот B — по
    текселям 1024. Кешируется."""
    key = id(E)
    if key in _LAYOUT:
        return _LAYOUT[key]
    S = 1024
    uv0 = E.get("uv0", E["uv"])
    tri = E["tri"]
    if "island" in E:                                     # остров — на прежнем месте (uv0)
        tri = tri
    tid, bar = kit3d.raster_uv({"uv": uv0, "tri": tri}, S)
    m = tid >= 0
    P = np.zeros((S, S, 3))
    P[m] = (bar[m][:, :, None] * E["pos"][tri[tid[m]]]).sum(1)
    w = Hy.Welded(E)
    ring = w.neck()
    zc = float(w.P[ring, 2].mean())
    band, lip = Hy.edge_layers(w, ring, zc)
    fold = Hy.fold_polyline(w, band)
    edge = Hy.smooth_curve(fold if fold is not None else Hy.lip_polyline(lip), zc, win=2.0)
    D = np.full((S, S), 9.0)
    D[m] = Hy.ring_dist(P[m], edge)
    TH = np.zeros((S, S))
    TH[m] = Hy.theta_of(P[m], zc)
    B = np.zeros((S, S), bool)
    B[m] = band[w.g[tri[tid[m]]]].all(1)
    _LAYOUT[key] = dict(P=P, m=m, D=D, TH=TH, B=B, zc=zc, edge=edge)
    return _LAYOUT[key]


_LAYOUT = {}


def ea_band_width(E):
    """Ширина воротника Edge (кромка EA 1_14_3 — она по шву воротника) по углу θ: 95-й процентиль D красного EA,
    сглажено ±15°. -> (θ, ширина, м)."""
    from PIL import Image
    from . import pilot
    L = edge_layout(E)
    ea = np.asarray(Image.open(os.path.join(pilot.unpack("1_14_3"), "jersey_cm.png")).convert("RGB")
                    .resize((1024, 1024))).astype(np.float64)
    red = (ea[..., 0] > ea[..., 1] + 50) & (ea[..., 0] > 90) & L["m"] & ~L["B"] & (L["D"] < 0.04)
    th, d = L["TH"][red], L["D"][red]
    full = np.arange(-180, 180, 1.0)
    wd = np.full(len(full), np.nan)
    for i, a in enumerate(full):
        s = np.abs(((th - a) + 180) % 360 - 180) < 3
        if s.sum() > 8:
            wd[i] = np.percentile(d[s], 95)
    ok = ~np.isnan(wd)
    wd = np.interp(full, full[ok], wd[ok], period=360)
    k = 15
    ker = np.exp(-0.5 * (np.arange(-2 * k, 2 * k + 1) / (k / 2)) ** 2)
    ker /= ker.sum()
    wd = np.convolve(np.concatenate([wd[-2 * k:], wd, wd[:2 * k]]), ker, mode="valid")
    return full, wd


def clean_edge_relief(xy, E, ea_curves, band_w):
    """Рельеф Edge (развёртка uv0, xy касательного пространства, 1024²) без лишних швов: шов по верху плеча и
    диагонали от горловины сзади (внутри кокетки, между линиями реглана и кривыми EA, вне воротника), V-вырез и его
    мысок спереди. Линии реглана и шов воротника — остаются. -> xy."""
    from scipy import ndimage as ndi
    L = edge_layout(E)
    S = xy.shape[0]
    yy, xx = np.mgrid[0:S, 0:S]
    u, v = (xx + 0.5) / S, (yy + 0.5) / S
    m = L["m"]
    det = seam_detector(xy)
    seam = (det > SEAM_THR) & m
    lab, n = ndi.label(ndi.binary_dilation(seam, iterations=1))
    sizes = ndi.sum(np.ones_like(lab), lab, index=np.arange(1, n + 1))
    seam = np.isin(lab, np.nonzero(sizes >= SEAM_MIN_PX)[0] + 1)
    bw = np.interp(L["TH"], band_w[0], band_w[1], period=360)
    out_band = L["D"] > bw + 0.004
    uL, uR = np.interp(v, *ea_curves["left"]), np.interp(v, *ea_curves["right"])
    yoke_in = (v > RAGLAN_V[0] + CLEAN_MARGIN) & (v < RAGLAN_V[1] - CLEAN_MARGIN) & (u > uL + CLEAN_MARGIN) & \
        (u < uR - CLEAN_MARGIN)
    P = L["P"]
    vneck = (P[..., 2] > L["zc"]) & (np.abs(P[..., 0]) < 0.11) & (P[..., 1] > 1.52) & (v > RAGLAN_V[1] + CLEAN_MARGIN)
    region = m & out_band & ~L["B"] & (yoke_in | vneck)
    mask = ndi.binary_dilation(seam & region, iterations=2) & region
    return shift_fill(xy, mask, m), mask


def _yoke_shape_path(code):
    return os.path.join(WORK, f"yoke_shape_{code}.json")


def save_yoke_shape(code, poly, heights):
    """Форма кокетки (бока — кривые EA в uv0, низ — высоты) — для форм клуба без цветной кокетки."""
    import json
    js = {"left": [list(map(float, a)) for a in poly["left"]], "right": [list(map(float, a)) for a in poly["right"]],
          "front": [list(map(float, a)) for a in heights["front"]], "back": [list(map(float, a)) for a in heights["back"]]}
    with open(_yoke_shape_path(code), "w", encoding="utf-8") as f:
        json.dump(js, f)


def load_yoke_shape(code):
    import json
    p = _yoke_shape_path(code)
    if not os.path.exists(p):
        return None
    js = json.load(open(p, encoding="utf-8"))
    poly = {"left": tuple(np.array(a) for a in js["left"]), "right": tuple(np.array(a) for a in js["right"]),
            "green": np.zeros(3), "white": np.zeros(3)}
    heights = {"front": tuple(np.array(a) for a in js["front"]), "back": tuple(np.array(a) for a in js["back"])}
    return poly, heights


def cmd_kit(a):
    """Свитер (и шрифт, шорты, гетры, превью) комплекта клуба по fb.pilot build, но: сетка — изогнутая копия Edge,
    перенос основы — coord_transfer; ворот со шнуровкой EA (collar_lace) — выключен (перед ворота — свой, adidas);
    щит NHL — на своём месте NHL 24 (без сдвига −4 см под вставку Edge). Папки — KITS_OUT/<КОД>_<форма>."""
    from types import SimpleNamespace
    from . import kit_fix, kit_hybrid, pilot
    E = load(0, 1, 2)
    E2, info = deform(E, n24_ring_for(0, 1, 2))
    print("сетка:", info)
    E2 = island().apply(E2)                              # перед ворота — на своей развёртке
    print("  остров развёртки: %d треугольников, %.2f → %.2f мм на тексель" %
          (int(island().sel.sum()), island().mm_per_texel_before, island().mm_per_texel))
    _, Em = J.legacy(J.skater_rel(0, 1, 2, 1))
    shirt = kit3d.load_legacy(kit_hybrid.LEGACY_SHIRT)
    dst = kit_hybrid.merge({k: E2[k] for k in ("pos", "uv", "nrm", "tri")}, shirt)
    n_jt = len(E2["tri"])
    orig_transfer = kit3d.transfer
    cmaps = {}

    def transfer(src_tex, src_mesh, dst_mesh, size=1024, ss=2, seam=0.04, post=None):
        if dst_mesh is not dst:                         # шорты, гетры — как были
            return orig_transfer(src_tex, src_mesh, dst_mesh, size, ss, seam, post)
        key = id(src_mesh)
        if key not in cmaps:
            cmaps[key] = CoordMap(src_mesh, {k: E2[k] for k in ("pos", "uv", "nrm", "tri")},
                                  (Em["bones"], Em["weights"]))
        img, mask, dist, inf = coord_transfer(src_tex, src_mesh, dst_mesh, size, ss, post, n_jt, cmaps[key])
        print("  перенос:", {k: (round(v, 3) if isinstance(v, float) else v) for k, v in inf.items()})
        return img, mask, dist, inf
    orig_rules = kit_hybrid.load_rules

    def load_rules(path, club=None, kit=None, profiles=()):
        d, r = orig_rules(path, club, kit, profiles)
        for nm_, sx in (("shoulder_r", 1.0), ("shoulder_l", -1.0)):   # ближе к шее (заходили на границу кокетки)
            if nm_ in r:
                r[nm_] = dict(r[nm_], offset_cm=[sx * SHOULDER_IN_CM, 0.0, 0.0])
        if "neck_shield" in r:                           # щит — где у NHL 24 (под краем ворота adidas), не у мыска V EA
            sh = {k: v for k, v in r["neck_shield"].items() if k != "legacy_uv"}
            r["neck_shield"] = dict(sh, offset_cm=SHIELD_OFFSET_CM, scale=SHIELD_SCALE)
        return d, r
    orig_fix_rules = kit_fix._rules

    def fix_rules(path=kit_fix.RULES):
        import copy
        t = copy.deepcopy(orig_fix_rules(path))
        if "brand" in t and "back" in t["brand"]:        # Reebok сзади — на высоте логотипа adidas NHL 24
            t["brand"]["back"] = dict(t["brand"]["back"], center=REEBOK_BACK_UV)
        return t
    kit_fix._rules = fix_rules
    orig_brand_relief = kit_fix.BrandSwap.relief

    def brand_relief(self, nm_path, sm_path):
        """Рельеф Reebok — туда же, куда цвет (REEBOK_BACK_UV), а не на место EA: иначе под логотипом — второй,
        выдавленный «Reebok»; и метка-прямоугольник в чистом рельефе спины (RELIEF_CLEAR) — заглажена."""
        from PIL import Image
        from scipy import ndimage as ndi
        sb = self.rule["src_box"]
        box = np.zeros((1024, 1024), bool)                 # только буквы (альфа надписи EA), не вся рамка: в рамке
        u0, v0 = int(round(sb[0] * 1024)), int(round(sb[1] * 1024))   # у EA — и край кокетки (давал черту)
        box[v0:v0 + self.src_a.shape[0], u0:u0 + self.src_a.shape[1]] = self.src_a > 0.25
        m = ndi.gaussian_filter(ndi.binary_dilation(box, iterations=2).astype(np.float64), 1.0)
        dy = int(round((REEBOK_BACK_UV[1] - (sb[1] + sb[3]) / 2) * 1024))
        for path, name in ((nm_path, "jersey_nm.png"), (sm_path, "jersey_sm.png")):
            mode = Image.open(path).mode
            cur = np.asarray(Image.open(path).convert(mode).resize((1024, 1024))).astype(np.float64)
            ea = np.asarray(Image.open(os.path.join(self.tpl_dir, name)).convert(mode).resize((1024, 1024),
                                                                                            Image.LANCZOS)).astype(np.float64)
            out = cur.copy()
            for u0, v0, u1, v1, dv in (() if RELIEF_REBUILD else RELIEF_CLEAR):   # метка — тканью со строк ниже
                #                                            (при RELIEF_REBUILD — в rebuild_relief, только складки:
                #                                            иначе в кокетке под Reebok — гладкий прямоугольник без сетки)
                cb = kit_fix._box(1024, [u0, v0, u1, v1])
                cm_ = ndi.gaussian_filter(ndi.binary_dilation(cb, iterations=2).astype(np.float64), 2.0)
                src_ = np.roll(cur, -int(round(dv * 1024)), axis=0)
                cm_ = cm_[..., None] if cur.ndim == 3 else cm_
                out = out * (1 - cm_) + src_ * cm_
            ea_s, m_s = np.roll(ea, dy, axis=0), np.roll(m, dy, axis=0)
            mm = m_s[..., None] if cur.ndim == 3 else m_s
            out = out * (1 - mm) + ea_s * mm
            Image.fromarray(np.clip(np.round(out), 0, 255).astype(np.uint8), mode).save(path)
    kit_fix.BrandSwap.relief = brand_relief
    # «рубашка» в вырезе — тёмной подкладкой NHL 24 (медиана её острова развёртки), а не цветом свитера: у ворота
    # adidas внутри — подкладка (у выездной белая рубашка торчала белым кольцом)
    from scipy.sparse.csgraph import connected_components
    n24 = kit3d.load_nhl24()
    wn = Hy.Welded(n24)
    _, comp = connected_components(wn.A, directed=False)
    lin_uv = n24["uv"][np.unique(n24["tri"][comp[wn.g[n24["tri"][:, 0]]] != np.bincount(comp).argmax()])]

    def collar_color(src_tex, rule):
        return np.median(kit3d.sample_bilinear(src_tex, lin_uv[:, 0], lin_uv[:, 1]), axis=0)
    orig_decal_post = kit_hybrid.decal_post
    yoke_rule = {}

    def decal_post(comp, placed, soft, n_jersey_tri, collar=None, pre=(), crest_fit=None, protect=None):
        pre = [r for r in (yoke_rule.get("cur"), yoke_rule.get("trim"), yoke_rule.get("insert")) if r is not None] \
            + list(pre)
        return orig_decal_post(comp, placed, soft, n_jersey_tri, collar, pre, crest_fit, protect)
    kit_hybrid.decal_post = decal_post
    orig_sleeve_rule = pilot.sleeve_rule
    sleeve_plan = {}

    def sleeve_rule(od, tpl=None):
        """Полосы к кисти — уже в переносе (SLV_COMPRESS): jersey_cm.png = jersey_cm_raw.png без сдвига; план — для
        info.json."""
        import shutil
        raw = os.path.join(od, "jersey_cm_raw.png")
        if os.path.exists(raw):
            shutil.copyfile(raw, os.path.join(od, "jersey_cm.png"))
        return dict(sleeve_plan)
    pilot.sleeve_rule = sleeve_rule
    keep = collar_keep_mask({k: E2[k] for k in ("pos", "uv", "nrm", "tri")}, 1024)
    kit3d.transfer = transfer
    kit_hybrid.collar_color = collar_color
    kit_hybrid.legacy_with_shirt = lambda: (dst, n_jt)
    kit_hybrid.load_rules = load_rules
    kit_fix.collar_lace_rule = lambda *args, **kw: None
    pilot.set_roots(KITS_OUT, os.path.join(WORK, "pack"))
    try:
        for kit in a.kits.split(","):
            yoke_rule.pop("cur", None)
            globals()["SLV_COMPRESS"] = None             # первая сборка комплекта — без сжатия (план — по ней)
            yr = YOKE.get((a.club, kit))
            global TORSO_DELTA
            TORSO_DELTA = None
            heights = None
            if yr is not None:
                heights = yoke_heights(a.club, kit)
                TORSO_DELTA = heights["delta"]
                print("  кокетка: сдвиг рисунка туловища (перед, спина), см:",
                      [round(d * 100, 2) for d in TORSO_DELTA])
            if yr is not None:                           # кокетка — по EA: сначала сборка без неё (линия NHL 24)
                pilot.cmd_build(SimpleNamespace(club=a.club, kits=kit, reuse=False))
                from .pilot import unpack
                ea_dir = unpack(yr["from"])
                poly = yoke_polygon(os.path.join(ea_dir, "jersey_cm.png"),
                                    os.path.join(KITS_OUT, f"{a.club}_{kit}", "jersey_cm.png"))
                print("  кокетка: цвета", np.round(poly["green"]).tolist(), np.round(poly["white"]).tolist())
                yoke_rule["cur"] = YokePaint(poly, keep, {k: E2[k] for k in ("pos", "uv", "nrm", "tri", "uv0")}, heights)
                save_yoke_shape(a.club, poly, heights)
            yoke_rule["trim"] = trim_rule(a.club, kit, {k: E2[k] for k in ("pos", "uv", "nrm", "tri")},
                                          with_yoke=yr is not None)
            if (a.club, kit) in INSERT_KITS:
                if "cur" not in yoke_rule:              # цвета — с первой сборки (как у кокетки)
                    pilot.cmd_build(SimpleNamespace(club=a.club, kits=kit, reuse=False))
                yoke_rule["insert"] = insert_rule(os.path.join(KITS_OUT, f"{a.club}_{kit}", "jersey_cm.png"), E2,
                                                  a.club, kit)
                if heights is not None:                  # линия кокетки — как у YokePaint (по первой сборке она
                    yoke_rule["insert"].yoke_y = heights["front"]   # 1,625 — у угла вставки был зелёный «прыщ»)
            global SLV_COMPRESS
            SLV_COMPRESS = None
            if SLV_PARAM and cmaps:                     # сжатие полос к кисти — по зоне номера шаблона (правило [sleeve])
                SLV_COMPRESS = sleeve_compress(next(iter(cmaps.values())), a.club, kit,
                                               os.path.join(KITS_OUT, f"{a.club}_{kit}"), sleeve_plan)
                print("  полосы рукава к кисти: k, верх рисунка", SLV_COMPRESS)
            pilot.cmd_build(SimpleNamespace(club=a.club, kits=kit, reuse=False))
            painters = dict(yoke_rule)
            if "cur" not in painters:                    # кокетка без цвета (дом MIN): шов и сетчатая ткань — как у
                sh = load_yoke_shape(a.club)             # выезда (у NHL 24 крой один)
                if sh is not None:
                    painters["yoke_shape"] = YokePaint(sh[0], keep, {k: E2[k] for k in ("pos", "uv", "nrm", "tri", "uv0")},
                                                       sh[1])
            yoke_rule.pop("insert", None)
            yoke_rule.pop("trim", None)
            od = os.path.join(KITS_OUT, f"{a.club}_{kit}")
            n_isl = remap_island_maps(os.path.join(od, "jersey_nm.png"), os.path.join(od, "jersey_sm.png"), E2)
            print("  рельеф и блик острова — с прежнего места:", n_isl, "текселей")
            if RELIEF_REBUILD:
                cmap = next(iter(cmaps.values()))
                info_r = rebuild_relief(os.path.join(od, "jersey_nm.png"), a.club, kit,
                                        {k: E2[k] for k in ("pos", "uv", "nrm", "tri", "uv0", "island")}, cmap, n_jt,
                                        painters)
                kit_fix.BrandSwap.relief(SimpleNamespace(rule=dict(kit_fix._rules()["brand"]),
                                                         tpl_dir=pilot.unpack(kit_fix._rules()["brand"]["from"]),
                                                         src_a=brand_alpha()),
                                         os.path.join(od, "jersey_nm.png"), os.path.join(od, "jersey_sm.png"))
                print("  рельеф:", info_r)
            pad_island(od, E2)
            print("  прежнее место острова (для lod 0, 3):", fill_old_place(od, E2), "текселей")
            J.fe_preview(od, {k: E2[k] for k in ("pos", "uv", "nrm", "tri")})   # превью меню — по своей сетке
    finally:
        pilot.sleeve_rule = orig_sleeve_rule
        kit_hybrid.decal_post = orig_decal_post
        kit3d.transfer = orig_transfer
        kit_hybrid.load_rules = orig_rules
        kit_fix._rules = orig_fix_rules
        kit_fix.BrandSwap.relief = orig_brand_relief


def sleeve_compress(cmap, code, kit, od, plan_out):
    """(k, d_top) сжатия полос рукава к кисти — как правило [sleeve] fb.sleeve (base_k, min_k, зазор gap_min до зоны
    номера шаблона), но по рисунку переноса рукава (верх полос — последняя граница SleeveMap.stripes без сжатия), k —
    общий для обоих рукавов (симметрично). plan_out — план для info.json."""
    import json
    from PIL import Image
    from . import pilot, sleeve
    global SLV_COMPRESS
    keep, SLV_COMPRESS = SLV_COMPRESS, None
    try:
        tex = np.asarray(Image.open(J.n24_tex(Hy.CLUB_NAME[code], kit, "base_color")).convert("RGB")).astype(np.float64)
        b24, bE = cmap.sleeve.stripes(tex)
    finally:
        SLV_COMPRESS = keep
    if not len(bE):
        return None
    r = sleeve.rule()
    kj = os.path.join(od, "kit.json")
    if not os.path.exists(kj):                           # нет первой сборки комплекта — шаблон неизвестен
        print("  ! полосы рукава: нет kit.json — без сжатия к кисти")
        return None
    tpl = json.load(open(kj, encoding="utf-8"))["template"]
    zones = sleeve.name_zones(os.path.join(pilot.unpack(tpl), "name_cm.png"), 1024)
    d_top = float(bE.max()) + 1.0 / 1024
    px = 2.0 / 1024
    ks = {}
    for z, zone in zones.items():
        left = zone[0] < 0.5
        d_zone = zone[0] if left else 1 - zone[2]
        want = min(d_top * r["base_k"], d_zone - r["gap_min"] - px)
        ks[z] = min(max(want / d_top, r["min_k"]), 1.0)
    k = min(ks.values()) if ks else r["base_k"]
    plan_out.clear()
    for z, zone in zones.items():
        left = zone[0] < 0.5
        d_zone = zone[0] if left else 1 - zone[2]
        plan_out[str(z)] = {"left": bool(left), "d_top": round(d_top, 4), "k": round(k, 3),
                            "gap_before": round(float(d_zone - d_top), 3), "gap_after": round(float(d_zone - d_top * k), 3),
                            "mode": "edge_kit: в переносе рукава"}
    return (k, d_top)


def cmd_preview(a):
    from PIL import Image, ImageDraw
    sys.path.insert(0, os.path.join(REPO, "game", "work", "nhl24", "hybrid"))
    from views import rot, checker  # noqa: E402 — рабочие скрипты
    E = load(0, 1, 2)
    E2, info = deform(E, n24_ring_for(0, 1, 2))
    print(info)
    n24 = J.nhl24(J.N24.format(tuck="notuck", size="large", lod=0))
    sh = Hy.mesh_d(rw.Mesh.load(os.path.join(J.OUT, *J.SHIRT[0].split("/"))))
    ch = checker()
    ch[-4:, -4:] = (40, 200, 60)

    def ws(m):
        n = len(m["pos"])
        return {"pos": np.vstack([m["pos"], sh["pos"]]), "nrm": np.vstack([m["nrm"], sh["nrm"]]),
                "uv": np.vstack([m["uv"], np.full((len(sh["pos"]), 2), 0.999)]), "tri": np.vstack([m["tri"], sh["tri"] + n])}
    views = [("прямо", []), ("сверху 45°", [("x", 45)]), ("сверху 80°", [("x", 80)]), ("3/4", [("y", -45), ("x", 15)]),
             ("сбоку", [("y", -90), ("x", 10)]), ("сзади сверху", [("y", 180), ("x", 35)])]
    rows = []
    for title, m in (("Edge (как у тебя)", E), ("копия Edge: перед ворота поднят", E2), ("NHL 24 adidas", n24)):
        mm = ws(m)
        ims = []
        for _, ops in views:
            x = mm
            for ax, dd in ops:
                x = rot(x, ax, dd, c=(0, 1.62, 0))
            ims.append(kit3d.render_lit(x, ch, "front", 280, frame=(-0.17, 0.17, 1.46, 1.80)))
        rows.append((title, ims))
    font = J.label_font(14)
    w_, h_ = rows[0][1][0].size
    sheet = Image.new("RGB", (len(views) * (w_ + 4) + 4, len(rows) * (h_ + 22) + 22), (24, 24, 28))
    dr = ImageDraw.Draw(sheet)
    for i, (vn, _) in enumerate(views):
        dr.text((8 + i * (w_ + 4), 3), vn, fill=(200, 200, 200), font=font)
    for j, (t_, ims) in enumerate(rows):
        y = 22 + j * (h_ + 22)
        dr.text((8, y + 2), t_, fill=(240, 240, 240), font=font)
        for i, im in enumerate(ims):
            sheet.paste(im, (4 + i * (w_ + 4), y + 20))
    sheet.save(a.out)
    print(a.out)


# ---------------------------------------------------------------- сетки и затенение в игру (слот стиля 0)

# Сетка свитера у игры одна на стиль (jersey_{g}_{s}_{h}_{t}_{p}_{lod}), а у этой формы она своя (поднятый ворот и
# остров развёртки). Поле style в базе — 1 бит, поэтому формы ставятся в слот стиля 0 (ретро; сейчас там сетки adidas
# — пользователь 19.10: «можешь поставить поверх ретро-комплектов, ничего страшного, что другие поплывут»).
SLOT_STYLE = 0
GOALIE_H = (0, 1)


def load_goalie(h, lod):
    _, E = J.legacy(J.goalie_rel(h, lod, 1))
    return E


def skater_shift(lod):
    """Сдвиг края ворота полевого (t0 p1, та же детализация) по углу: θ → (dr, dy), по кругу."""
    deform(load(0, 1, lod), n24_ring_for(0, 1, lod))
    te, dr, dy = deform.last_shift
    o = np.argsort(te)
    xp = np.concatenate([te[o] - 360, te[o], te[o] + 360])
    return lambda th: (np.interp(th, xp, np.tile(dr[o], 3)), np.interp(th, xp, np.tile(dy[o], 3)))


def goalie_mesh_for(h, lod):
    """Вратарь: перед ворота поднят так же, как у полевого той же детализации (тот же сдвиг края по углу — от своего
    края: горловина вратаря шире на ~2 см и ниже на 5–6 см, к краю NHL 24 её не тянуть), перед ворота — на развёртке
    острова (по uv0). Без подъёма рисунок ворота (кромка, вставка, щит — под поднятый ворот) ложился на V-вырез Edge
    (пользователь, 20.10: «вратарскую форму тоже нужно адаптировать»)."""
    info = {}
    E2, info = deform(load_goalie(h, lod), None, info, shift=skater_shift(lod))
    return (island().apply(E2) if lod in ISLAND_LODS else E2), info


def write_mesh(M, dst_rel, out_root):
    """Сетка M (поз., нормали, UV, кости, веса) → файл слота dst_rel (секции и шейдер — из файла слота в архиве, как у
    fb.jersey_mesh.build_one); касательная — вдоль +u своей развёртки (у острова — своя)."""
    import rw4mesh as rw
    base = rw.Mesh.game(dst_rel)
    tv, _ = kit3d.vertex_tangents(M)
    P, N, UV, T = M["pos"], kit3d._unit(M["nrm"]), np.clip(M["uv"], 0.0, 1.0), M["tri"]
    bones = [list(map(int, b)) for b in M["bones"]]
    weights = [list(map(float, w)) for w in M["weights"]]
    tmpl = base.vertex_raw(0)
    vb = bytearray()
    for i in range(len(P)):
        vb += base.pack_vertex(tmpl, pos=P[i], nrm=N[i], tan=tv[i], uv=UV[i], bones=bones[i], weights=None)
    tmp = rw.Mesh(base.rebuilt(bytes(vb), J.strips(T)), dst_rel)
    for i in range(tmp.nv):
        tmp.set_skin(i, bones[i], weights[i])
    data = tmp.bytes()
    chk = rw.Mesh(data, dst_rel)
    assert chk.nv == len(P) and len(chk.tris) == len(T), (chk.nv, len(chk.tris))
    J.write(out_root, dst_rel, data)
    return {"nv": chk.nv, "tris": len(chk.tris)}


def ao_for_slot(out_root):
    """Затенение свитера (rendering/jersey/texlib_S_999: jersey_S_g_t_am, 256²) для слота: копия Edge (стиль 1) с
    именами растров слота и островом — значениями прежнего места (uv0), иначе перед ворота брал ровный серый фон
    угла атласа (198 против ~225 у ткани — темнее)."""
    import teamart as ta
    import kitpaint as kp
    from scipy import ndimage as ndi
    src = os.path.join(REPO, "game", "other", "legacy", "big", "renderboot", "rendering", "jersey", "texlib_1_999.rx2")
    rwf = ta.Rw4.load(src)
    S = 256
    M = mesh_for(0, 1, 2)
    isl = M["island"][M["tri"]].all(1)
    Mi = {"uv": M["uv"], "tri": M["tri"][isl]}
    tid, bar = kit3d.raster_uv(Mi, S)
    m = tid >= 0
    U0 = np.zeros((S, S, 2))
    U0[m] = (bar[m][:, :, None] * M["uv0"][Mi["tri"][tid[m]]]).sum(1)
    grow = ndi.binary_dilation(m, iterations=3)
    _, (iy, ix) = ndi.distance_transform_edt(~m, return_indices=True)
    U0g = U0[iy, ix]
    for t in rwf.textures:
        w, h, px = rwf.decode(t)
        a = np.frombuffer(bytes(px), np.uint8).reshape(h, w, 4).astype(np.float64)
        v = kit3d.sample_bilinear(a, U0g[grow][:, 0], U0g[grow][:, 1])
        a[grow] = v
        kp.tex_replace(rwf, t, np.clip(np.round(a), 0, 255).astype(np.uint8).tobytes(), w, h)
    done = rwf.rename(1, SLOT_STYLE)
    rel = f"rendering/jersey/texlib_{SLOT_STYLE}_999.rx2"
    J.write(out_root, rel, bytes(rwf.raw))
    return rel, [d[1] for d in done]


# Комплекты в игру (пользователь, 19.10): шорты и шлемы — от нынешних основных форм клуба (дом — NHL 24 1_14_4, выезд —
# EA 1_14_3), гетры светлой — от основной выездной 1_14_3 (белые с зелёными полосами, ровные), тёмной — свои: полосы
# гетр NHL 24 (кремовая, красная, кремовая — доли 30:30:110) по месту полосы перенесённых гетр, ровными строками
# (у перенесённых 3D-переносом края полос волной). Карта номеров — та же, что у формы-образца шорт (зоны вне острова).
SLOT_KITS = {
    "home": {"kit": "edge_home", "legacy": "1_14_4", "sock": "flat", "label": "Home (Edge collar 24)"},
    "away": {"kit": "edge_away", "legacy": "1_14_3", "sock": "legacy", "label": "Away (Edge collar 24)"},
}
SOCK_PARTS = ((0.0, (24, 56, 46)), (30, (214, 203, 165)), (30, (159, 14, 10)), (110, (214, 203, 165)))
SOCK_TOP_V = 0.49                  # верх полос своих гетр (v развёртки гетр: 0 — у колена): у EA MIN 0,48–0,50;
#                                    перенесённые с NHL 24 — 0,576 (на ~6,5 см ниже — «повыше», пользователь, 19.10)
# гетры EA (светлая): полоса — в тех же строках, что у домашних (пользователь, 20.10: «линии на гетрах — на одном
# уровне, как на домашней»): place_sock растягивает её (74 → 81 строка из 512) на полосу flat_sock домашних


def flat_sock(src_png):
    """Гетры: полоса — там же, где у перенесённых (строки, где медиана строки не цвет ткани), разбита в долях NHL 24,
    края — с долей покрытия строки (без лесенки)."""
    from PIL import Image
    a = np.asarray(Image.open(src_png).convert("RGB")).astype(np.float64)
    H, W = a.shape[:2]
    base = np.array(SOCK_PARTS[0][1], np.float64)
    med = np.median(a, axis=1)
    band = np.nonzero(np.linalg.norm(med - base, axis=1) > 40)[0]
    y0, y1 = float(band.min()), float(band.max() + 1)
    if SOCK_TOP_V is not None:                           # своя высота полосы (ширина — как у перенесённых)
        y0, y1 = SOCK_TOP_V * H, SOCK_TOP_V * H + (y1 - y0)
    tot = sum(w for w, _ in SOCK_PARTS[1:])
    edges, cols = [y0], []
    for w_, c in SOCK_PARTS[1:]:
        edges.append(edges[-1] + (y1 - y0) * w_ / tot)
        cols.append(np.array(c, np.float64))
    out = np.zeros((H, 3))
    for y in range(H):
        acc = np.zeros(3)
        r0, r1 = y, y + 1.0
        rest = 1.0
        for (e0, e1), c in zip(zip(edges[:-1], edges[1:]), cols):
            cov = max(0.0, min(r1, e1) - max(r0, e0))
            acc += cov * c
            rest -= cov
        out[y] = acc + rest * base
    img = np.repeat(out[:, None, :], W, axis=1)
    return Image.fromarray(np.clip(np.round(img), 0, 255).astype(np.uint8)), (y0, y1, edges)


def place_sock(src_png, dst_png, top_v, bot_v):
    """Гетры EA: полоса (строки, где медиана — не цвет ткани) — в строки top_v…bot_v (доли высоты), растяжением по
    строкам (линейно, края — со сглаживанием); выше и ниже — ткань тем же сдвигом. -> (строки было, стало)."""
    from PIL import Image
    a = np.asarray(Image.open(src_png).convert("RGB")).astype(np.float64)
    H = a.shape[0]
    med = np.median(a[:, a.shape[1] // 4:3 * a.shape[1] // 4], axis=1)
    base = np.median(med, axis=0)
    band = np.nonzero(np.abs(med.mean(1) - base.mean()) > 40)[0]
    y0, y1 = float(band.min()), float(band.max() + 1)
    Y0, Y1 = top_v * H, bot_v * H
    yc = np.arange(H) + 0.5                              # центр строки назначения → строка источника
    src = np.where(yc < Y0, yc - (Y0 - y0), np.where(yc < Y1, y0 + (yc - Y0) * (y1 - y0) / (Y1 - Y0), yc - (Y1 - y1)))
    f = np.clip(src - 0.5, 0, H - 1)
    i0 = np.floor(f).astype(int)
    i1 = np.minimum(i0 + 1, H - 1)
    t = (f - i0)[:, None, None]
    out = a[i0] * (1 - t) + a[i1] * t
    Image.fromarray(np.clip(np.round(out), 0, 255).astype(np.uint8)).save(dst_png)
    return (y0, y1), (Y0, Y1)


def deislanded(cm_png, out_png):
    """Текстура в обычной развёртке Edge (перед ворота — на прежнем месте, uv0) — для превью меню в позе EA (модель
    позы снята с развёртки Edge)."""
    from PIL import Image
    tex = np.asarray(Image.open(cm_png).convert("RGB")).astype(np.float64)
    S = tex.shape[0]
    M = mesh_for(0, 1, 2)
    isl = M["island"][M["tri"]].all(1)
    T = M["tri"][isl]
    tid, bar = kit3d.raster_uv({"uv": M["uv0"], "tri": T}, S)
    m = tid >= 0
    UV = (bar[m][:, :, None] * M["uv"][T[tid[m]]]).sum(1)
    out = tex.copy()
    out[m] = kit3d.sample_bilinear(tex, UV[:, 0], UV[:, 1])[:, :3]
    Image.fromarray(np.clip(np.round(out), 0, 255).astype(np.uint8)).save(out_png)
    return int(m.sum())


FE_ITER = 12                       # итераций обратного сдвига (поле сдвига плавное: |∇Δ| < 0,4 — сходится)
FE_SS, FE_FOOT = 4, 1.25           # сглаживание превью — как у fb.pilot.fe_preview_ea
# Перед ворота на превью — проекцией своей сетки (камера модели позы — аффинно по точкам у ворота, ошибка ~0,6 px):
# карта UV модели позы EA у ворота шумная (подбор по корреляции), а вставка со щитом и шнуровка — 10–12 px: месиво
# (пользователь, 20.10: «шнуровка превращается в непонятное месиво»). Шнуровку на превью — убрать (ткань), вставка
# со щитом — как есть, со сглаживанием FE_SSR² точек на пиксель.
FE_ROI_D, FE_ROI_X = 0.065, 0.120  # м: до края ворота и от середины — зона своей проекции
FE_ROI_FADE = 0.012                # м: переход к модели позы
FE_SSR = 8                         # точек на пиксель (по стороне)
FE_NO_LACES = True
FE_LACE_X = 0.040                  # м: столбец шнуровки (как PLACKET_HALF)
FE_LACE_Y = (1.48, 1.616)          # м: шнуровка — ниже вставки (выше — кромка и кокетка: при 1,66 у верхних углов
#                                    вставки выходили блоки цвета ткани; при 1,612 оставались концы верхнего шнурка)
FE_LACES = ((1.596, 1.574), 0.024, 0.0100)   # шнурки на превью — крупнее настоящих (пользователь, 20.10: «хотя бы
#                                    пару шнурков, без них скудно»): высоты (м), полуширина, толщина; цвет — шнурков
FE_LACE_V = 0.0065                 # м: красный «V» между шнурками (полуширина вверху; пользователь, 20.10)
FE_SHIELD = (1.10, 0.004, 0.0055)  # щит на превью: крупнее во столько, ниже на столько (м), красная подложка вокруг
#                                    (м; пользователь, 20.10: «и сверху, и снизу от шильдика видно подложку») — спрайтом
#                                    в кадре: вырезан со сглаженным краем, место — красным вставки, вставлен заново (линза
#                                    по точкам сетки щит гнула, красное плыло)
FE_SHADE_SIGMA = 1.2               # px: затенение модели позы у ворота — сглаженное (в нём тени шнуровки EA)
FE_OUTLIER_PX = 6.0                # px: пиксель свитера модели, чья точка проецируется дальше, — выброс карты UV
# Швы и сетка кокетки на превью (пользователь, 20.10: «тот же рельеф, что в игре — швы на плечах, перфорация»): наклоны
# рельефа на 256² гасят друг друга (канавка шва — 1 тексель из 2,7 на пиксель), поэтому — затенение по глубине
# (relief_depth.npz от rebuild_relief: высота своих швов design_seams и ямки сетки): цвет × (1 + K_s·h − K_p·ямка).
FE_SEAM_K = 2.0
FE_PERF_K = 0.20
# Свет модели позы — со швами EA (кокетка поперёк груди, V-вырез, подол, «призраки» нашивок — тонкие линии в 1–2 px):
# со своими швами выходило «и новые, и старые» (пользователь, 20.10). На торсе и плечах свет — медианой FE_CLEAN_MED²
# по пикселям свитера (тонкие линии уходят, складки и края — нет); рукава — как есть (там складки позы).
FE_CLEAN_MED = 5
FE_CLEAN_X = (0.18, 0.22)          # м (|x| в позе привязки): торс — до первого, рукав — от второго
FE_CLEAN_SHOULDER = (0.36, 0.40, 1.40, 7)   # и плечо с верхом рукава выше подмышки (y > 1,40), медианой 7²: там
#                                    кольцо шва проймы рукава Edge (|x| 0,29–0,33, линия 2–3 px — дуга на плече;
#                                    пользователь, 20.10: «я про это, ничего не поправил»; в игре шва там нет)


def _pose_clean(m, Pp, fin):
    """gain/bias модели позы без тонких линий на торсе и плечах (медиана по соседям-пикселям свитера). -> (gain, bias)."""
    import warnings
    H, W_ = m["h"], m["w"]

    def med_of(arr, k):
        r = k // 2
        full = np.full((H, W_, arr.shape[1]), np.nan)
        full[m["ys"], m["xs"]] = arr
        pad = np.pad(full, ((r, r), (r, r), (0, 0)), constant_values=np.nan)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            med = np.nanmedian(np.stack([pad[dy:dy + H, dx:dx + W_] for dy in range(k) for dx in range(k)]), 0)
        med = med[m["ys"], m["xs"]]
        return np.where(np.isfinite(med), med, arr)
    ax = np.where(fin, np.abs(np.nan_to_num(Pp[:, 0])), 1.0)
    yy = np.where(fin, np.nan_to_num(Pp[:, 1]), 0.0)
    x0s, x1s, y0s, ks = FE_CLEAN_SHOULDER
    w_t = Hy.smooth((FE_CLEAN_X[1] - ax) / (FE_CLEAN_X[1] - FE_CLEAN_X[0]))[:, None]
    w_s = (Hy.smooth((x1s - ax) / (x1s - x0s)) * Hy.smooth((yy - y0s) / 0.03))[:, None] * (1 - w_t)
    out = []
    for arr in (m["gain"], m["bias"]):
        res = arr * (1 - w_t) + med_of(arr, FE_CLEAN_MED) * w_t
        out.append(res * (1 - w_s) + med_of(arr, ks) * w_s)
    return out


def _deisland_arrays(arrs, M):
    """Карты в развёртке с островом (S², как текстуры формы) → в развёртке Edge (uv0): прежнее место острова — значениями
    с острова (как fill_old_place, без поворота базиса)."""
    tri = M["tri"][M["island"][M["tri"]].all(1)]
    out = []
    for a in arrs:
        S = a.shape[0]
        tid, bar = kit3d.raster_uv({"uv": M["uv0"], "tri": tri}, S)
        m = tid >= 0
        T = tri[tid[m]]
        uvi = (bar[m][:, :, None] * M["uv"][T]).sum(1)
        b = a.astype(np.float64).copy()
        b[m] = kit3d.sample_bilinear(a.astype(np.float64)[..., None], uvi[:, 0], uvi[:, 1])[:, 0]
        out.append(b)
    return out


def _fe_collar(out, m, A, isl_png, Jmap, front, perr, depth=None):
    """Перед ворота превью (out, RGBA на месте) — проекцией сетки t0 p1 с островом (текстура isl_png — с островом)
    камерой A, затенение — gain/bias модели позы из пикселя-источника Jmap. Край ворота — только свой: где под ним
    (или над ним) была ткань переда модели позы (front — по пикселям свитера модели), фон — манекен (шея): иначе
    сквозь сглаженный край проступал пиксельный край модели — лесенкой (пользователь, 20.10). Выбросы карты UV модели
    у ворота (perr — px между пикселем свитера и проекцией его точки: у шеи пиксель показывал подол — белая точка) —
    цветом соседей. -> пикселей."""
    from PIL import Image
    from scipy import ndimage as ndi
    H, W_ = Jmap.shape
    M = mesh_for(0, 1, 2)
    w = Hy.Welded(M)
    ring = w.neck()
    zc = float(w.P[ring, 2].mean())
    band, lip = Hy.edge_layers(w, ring, zc)
    Dv = Hy.ring_dist(M["pos"], collar_edge(w, band, lip, zc, win=2.0))
    bandt = band[w.g[M["tri"]]].all(1)
    Q = np.c_[M["pos"], np.ones(len(M["pos"]))] @ A
    cam = np.cross(A[:3, 0], A[:3, 1])                  # направление проекции; к камере — +z
    cam = cam / np.linalg.norm(cam) * (1 if cam[2] > 0 else -1)
    T = M["tri"]
    nt = kit3d._unit(kit3d._unit(M["nrm"])[T].mean(1))
    c3 = M["pos"][T].mean(1)
    sel = ((nt @ cam) > 0.05) & ~bandt & (c3[:, 2] > zc - 0.02) &         ((Dv[T].min(1) < FE_ROI_D + 0.03) | (np.abs(c3[:, 0]) < FE_LACE_X + 0.04)) &         (np.abs(c3[:, 0]) < FE_ROI_X + 0.04) & (c3[:, 1] > 1.46)
    Ts = T[sel]
    Ts = Ts[np.argsort(M["pos"][Ts].mean(1) @ cam)]     # дальние — первыми: ближние ложатся поверх
    q = Q[Ts]
    x0, y0 = int(np.floor(q[..., 0].min())) - 1, int(np.floor(q[..., 1].min())) - 1
    x1, y1 = int(np.ceil(q[..., 0].max())) + 1, int(np.ceil(q[..., 1].max())) + 1
    Wp, Hp, ss = x1 - x0 + 1, y1 - y0 + 1, FE_SSR
    uvp = np.c_[(Q[:, 0] - x0 + 0.5) / Wp, (Q[:, 1] - y0 + 0.5) / Hp]
    tid, bar = kit3d.raster_uv({"uv": uvp, "tri": Ts}, (Wp * ss, Hp * ss))
    hit = tid >= 0
    TT, bb = Ts[tid[hit]], bar[hit]
    uvt = (bb[:, :, None] * M["uv"][TT]).sum(1)
    P3 = (bb[:, :, None] * M["pos"][TT]).sum(1)
    Dh = (bb * Dv[TT]).sum(1)
    tex = np.asarray(Image.open(isl_png).convert("RGB")).astype(np.float64)
    ys_h, hs_h = (np.array(v) for v in zip(*INSERT_HW))
    c = kit3d.sample_bilinear(tex, uvt[:, 0], uvt[:, 1])[:, :3]
    ax, y3 = np.abs(P3[:, 0]), P3[:, 1]
    hw = np.interp(y3, ys_h, hs_h, left=-1.0, right=-1.0)
    in_ins = (ax < hw - 0.002) & (y3 > 1.60)
    red = np.median(c[in_ins], 0) if in_ins.sum() > 20 else np.array([160.0, 15.0, 10.0])
    drawn = np.zeros(len(c), bool)                     # нарисованное на превью (шнурки, «V») — поверх щита
    if FE_NO_LACES:                                     # шнуровка и люверсы — ткань свитера, во вставке — красный
        body_m = (ax > FE_LACE_X + 0.006) & (ax < FE_LACE_X + 0.035) & (y3 > 1.52) & (y3 < 1.575)
        body = np.median(c[body_m], 0) if body_m.sum() > 20 else np.median(c, 0)
        col_z = (ax < FE_LACE_X) & (y3 > FE_LACE_Y[0]) & (y3 < FE_LACE_Y[1])
        cand = col_z & (ax > hw + 0.0015) & (np.linalg.norm(c - body, axis=1) > 60) &             (np.linalg.norm(c - red, axis=1) > 60)
        if cand.sum() > 10:                             # цвет шнурков — самые далёкие от ткани (без краёв со сглаживанием)
            dist = np.linalg.norm(c[cand] - body, axis=1)
            lace_col = np.median(c[cand][dist >= np.percentile(dist, 75)], 0)
        else:
            lace_col = 255.0 - body
        c[col_z & (ax > hw + 0.0015)] = body
        c[col_z & (ax <= hw + 0.0015)] = red
        if FE_LACES:
            ys_l, hw_l, th_l = FE_LACES
            # ниже верхнего шнурка — ткань, и кончик вставки тоже (торчал красным между шнурками)
            c[(ax < FE_LACE_X) & (y3 > FE_LACE_Y[0]) & (y3 < max(ys_l) - th_l / 2)] = body
            if FE_LACE_V and len(ys_l) > 1:              # «V» остриём вниз между верхним и следующим шнурком
                yt, yb = ys_l[0] - th_l / 2, ys_l[1] + th_l / 2
                f_v = np.clip((y3 - yb) / max(yt - yb, 1e-6), 0, 1)
                on = (y3 > yb) & (y3 <= yt) & (ax < FE_LACE_V * f_v) & (P3[:, 2] > zc)
                c[on] = red
                drawn |= on
            for yl in ys_l:
                on = (np.abs(y3 - yl) < th_l / 2) & (ax < hw_l) & (P3[:, 2] > zc)
                c[on] = lace_col
                drawn |= on
    # зона своей проекции: у края ворота (FE_ROI_D) и весь столбец шнуровки вниз до её низа
    w_sub = np.maximum(Hy.smooth((FE_ROI_D - Dh) / FE_ROI_FADE),
                       Hy.smooth((FE_LACE_X + 0.014 - ax) / 0.008) * Hy.smooth((y3 - 1.50) / 0.012))
    w_sub = w_sub * Hy.smooth((FE_ROI_X - ax) / FE_ROI_FADE)
    rel = np.ones(len(c))                               # затенение по глубине швов и ямок (depth — с островом)
    if depth is not None:
        dh = kit3d.sample_bilinear(np.dstack(depth), uvt[:, 0], uvt[:, 1])
        rel = np.where(drawn, 1.0, 1.0 + FE_SEAM_K * dh[:, 0] - FE_PERF_K * dh[:, 1])
    Cs = np.zeros((Hp * ss, Wp * ss, 5))
    Cs[hit] = np.c_[c, w_sub, rel]
    _fe_collar.shield = None
    if FE_SHIELD:                                       # щит — спрайтом: крупнее и ниже, на его месте — красный
        s_sh, d_sh, m_sh = FE_SHIELD
        sg = np.zeros(hit.shape, bool)
        sg[hit] = (ax < hw - 0.0005) & (y3 > 1.612) & ~drawn & (np.linalg.norm(c - red, axis=1) > 70)
        lab, nl = ndi.label(ndi.binary_closing(sg, iterations=2))
        if nl:
            sz = np.bincount(lab.ravel())
            sz[0] = 0
            sg = ndi.binary_fill_holes(lab == sz.argmax())   # сам щит — крупнейшая часть
            reg = ndi.binary_dilation(sg, iterations=3) & hit  # с краем сглаживания
            C3 = Cs[..., :3]
            dr = np.linalg.norm(C3 - red, axis=-1)
            al = np.where(reg, np.clip((dr - 12.0) / 50.0, 0, 1), 0.0)
            al[sg] = np.maximum(al[sg], 0.0)
            pre = (C3 - (1 - al[..., None]) * red) * reg[..., None]      # цвет щита, умноженный на долю
            gr, gc = np.argwhere(sg).mean(0)
            k_sh = d_sh * abs(A[1, 1]) * ss                 # вниз, точек сетки
            rr, cc = np.mgrid[0:hit.shape[0], 0:hit.shape[1]].astype(np.float64)
            sr, sc_ = gr + (rr - gr - k_sh) / s_sh, gc + (cc - gc) / s_sh
            a_n = ndi.map_coordinates(al, [sr, sc_], order=1, mode="constant")
            p_n = np.stack([ndi.map_coordinates(pre[..., i], [sr, sc_], order=1, mode="constant") for i in range(3)], -1)
            # место щита и подложка под новым (m_sh вокруг: низ щита ниже вставки — на красном) — красным
            halo = (ndi.distance_transform_edt(~(a_n > 0.05)) < m_sh * abs(A[1, 1]) * ss) & hit
            base3 = np.where((reg | halo)[..., None], red, C3)
            Cs[..., :3] = p_n + (1 - a_n[..., None]) * base3
            dg = np.zeros(hit.shape, bool)
            dg[hit] = drawn
            Cs[dg, :3] = c[drawn]
            Cs[~hit] = 0.0
            _fe_collar.shield = (int(sg.sum()), round(float(k_sh / ss), 2))
    _fe_collar.grid = (Cs[..., :3], hit, P3)            # отладка: точки кадра (цвет, попадание, где)
    agg = Cs.reshape(Hp, ss, Wp, ss, 5).sum((1, 3))
    n = hit.reshape(Hp, ss, Wp, ss).sum((1, 3)).astype(np.float64)
    cov = n / ss ** 2
    mean = agg / np.maximum(n, 1)[..., None]
    k = np.where(n > 0, cov * mean[..., 3], 0.0)
    gy, gx = np.mgrid[y0:y1 + 1, x0:x1 + 1]
    inside = (gy >= 0) & (gy < H) & (gx >= 0) & (gx < W_) & (k > 1e-3) & (cov > 0)
    _, (iy, ix) = ndi.distance_transform_edt(Jmap < 0, return_indices=True)
    py, px_ = gy[inside], gx[inside]
    j = Jmap[iy[py, px_], ix[py, px_]]
    # затенение — сглаженное по пикселям свитера (нормированный гаусс)
    jm = np.zeros((H, W_))
    jm[m["ys"], m["xs"]] = 1.0
    sm_ = []
    for arr in (m["gain"], m["bias"]):
        full = np.zeros((H, W_, 3))
        full[m["ys"], m["xs"]] = arr
        num = np.stack([ndi.gaussian_filter(full[..., c_] * jm, FE_SHADE_SIGMA) for c_ in range(3)], -1)
        den = ndi.gaussian_filter(jm, FE_SHADE_SIGMA)[..., None]
        sm_.append((num / np.maximum(den, 1e-6))[m["ys"][j], m["xs"][j]])
    col = np.clip((sm_[0] * mean[inside][:, :3] + sm_[1]) * mean[inside][:, 4:5], 0, 255)
    jc = Jmap[gy.clip(0, H - 1), gx.clip(0, W_ - 1)]
    # выбросы модели у ворота: цвет — средний по соседям без выбросов (2 прохода)
    okb = (gy >= 0) & (gy < H) & (gx >= 0) & (gx < W_)
    bad = okb & (jc >= 0) & (perr[np.maximum(jc, 0)] > FE_OUTLIER_PX)
    for _ in range(2):
        if not bad.any():
            break
        reg = out[y0:y1 + 1, x0:x1 + 1].astype(np.float64) if (y0 >= 0 and x0 >= 0 and y1 < H and x1 < W_) else None
        if reg is None:
            break
        good = (~bad).astype(np.float64)
        num = np.stack([ndi.uniform_filter(reg[..., c_] * good, 3) for c_ in range(4)], -1)
        den = ndi.uniform_filter(good, 3)[..., None]
        fix = bad & (den[..., 0] > 0.05)
        reg[fix] = (num / np.maximum(den, 1e-6))[fix]
        out[y0:y1 + 1, x0:x1 + 1] = np.round(reg).astype(np.uint8)
        bad &= ~fix
    # фон: ткань переда модели позы у края (своя ткань — только из проекции) → манекен
    was_front = (jc >= 0) & front[np.maximum(jc, 0)]
    above = ndi.binary_dilation(k > 0.3, iterations=3) & (n == 0) & was_front &         (gy >= 0) & (gy < H) & (gx >= 0) & (gx < W_)
    out[gy[above], gx[above]] = m["base"][gy[above], gx[above]]
    # доля своей сетки cov: из неё — доля своего рисунка wR (переход к модели позы — её же тканью), вне сетки — фон
    cv = cov[inside][:, None]
    wr = mean[inside][:, 3:4]
    cur = out[py, px_].astype(np.float64)
    bg = np.where(was_front[inside][:, None], m["base"][py, px_].astype(np.float64), cur)
    mine = np.c_[col, m["alpha"][j]]
    res = cv * (wr * mine + (1 - wr) * cur) + (1 - cv) * bg
    out[py, px_] = np.round(np.clip(res, 0, 255)).astype(np.uint8)
    return int((k[inside] > 0.5).sum())


def fe_preview_edge(jersey_png, isl_png=None, depth_npz=None):
    """Превью меню в позе EA (fb.pilot.fe_preview_ea: манекен, свет и кадр EA — по развёртке Edge), но с поднятым
    передом ворота: модель позы снята с V-выреза Edge, а у этой сетки перед ворота поднят (deform) — без сдвига
    кромка, вставка и щит садились в «галочку» V-выреза (пользователь, 20.10: «чтобы воротник отображался
    корректно»). Сдвиг точек свитера сетки t0 p1 (по uv) → в пиксели превью (аффинно, по точкам у ворота); пиксель
    превью q показывает точку p, для которой p + Δ(p) = q (итерации), если p — перед свитера; иначе — как у EA.
    jersey_png — текстура в развёртке Edge (deislanded); isl_png — она же с островом: перед ворота — проекцией сетки
    (_fe_collar). -> RGBA 256²."""
    from PIL import Image
    from scipy import ndimage as ndi
    from . import pilot
    m = pilot._pose()
    H, W_ = m["h"], m["w"]
    ys, xs = m["ys"], m["xs"]
    E = load(0, 1, 2)
    E2, _ = deform(E, n24_ring_for(0, 1, 2))
    zc = float(Hy.Welded(E).P[Hy.Welded(E).neck(), 2].mean())
    S = 1024
    tid, bar = kit3d.raster_uv(E, S)
    ok = tid >= 0
    P = np.full((S, S, 3), np.nan)
    D = np.zeros((S, S, 3))
    T = E["tri"][tid[ok]]
    b = bar[ok]
    P[ok] = (b[:, :, None] * E["pos"][T]).sum(1)
    D[ok] = (b[:, :, None] * (E2["pos"] - E["pos"])[T]).sum(1)
    N = np.zeros((S, S, 3))
    N[ok] = kit3d._unit((b[:, :, None] * kit3d._unit(E["nrm"])[T]).sum(1))
    xi = np.clip((m["u"] * S).astype(int), 0, S - 1)
    yi = np.clip((m["v"] * S).astype(int), 0, S - 1)
    Pp, Dp, Np = P[yi, xi], D[yi, xi], N[yi, xi]
    fin = np.isfinite(Pp[:, 0])
    if FE_CLEAN_MED:                                    # свет без швов EA на торсе
        g_c, b_c = _pose_clean(m, Pp, fin)
        m = dict(m, gain=g_c, bias=b_c)
    front = fin & (Pp[:, 2] > zc) & (Np[:, 2] > 0.1)
    # проекция у ворота: (x, y, z) → пиксель, аффинно по точкам переда у ворота
    near = front & (np.abs(Pp[:, 0]) < 0.16) & (Pp[:, 1] > 1.45) & (Pp[:, 1] < 1.72)
    X = np.c_[Pp[near], np.ones(near.sum())]
    A = np.linalg.lstsq(X, np.c_[xs[near], ys[near]], rcond=None)[0]
    err = np.linalg.norm(X @ A - np.c_[xs[near], ys[near]], axis=1)
    dpx = np.where(front[:, None], np.nan_to_num(Dp) @ A[:3], 0.0)
    # поле сдвига на всём кадре: перед — свой, прочее — от ближайшего пикселя переда (чтобы итерация из выреза
    # сходилась к переду), сглажено
    F = np.zeros((H, W_, 2))
    fm = np.zeros((H, W_), bool)
    F[ys[front], xs[front]] = dpx[front]
    fm[ys[front], xs[front]] = True
    _, (iy, ix) = ndi.distance_transform_edt(~fm, return_indices=True)
    F = F[iy, ix]
    F = np.stack([ndi.gaussian_filter(F[..., c], 0.7) for c in range(2)], -1)
    moved = np.hypot(F[..., 0], F[..., 1]) > 0.05

    def field(py, px_):
        y0, x0 = np.clip(np.floor(py).astype(int), 0, H - 2), np.clip(np.floor(px_).astype(int), 0, W_ - 2)
        fy, fx = (py - y0)[:, None], (px_ - x0)[:, None]
        return (F[y0, x0] * (1 - fy) * (1 - fx) + F[y0, x0 + 1] * (1 - fy) * fx + F[y0 + 1, x0] * fy * (1 - fx) +
                F[y0 + 1, x0 + 1] * fy * fx)

    # цели: пиксели, куда может попасть сдвинутый перед (у ворота), — источник p(q)
    reach = ndi.binary_dilation(moved & fm, iterations=int(np.ceil(np.abs(F).max())) + 2)
    qy, qx = np.nonzero(reach)
    py, px_ = qy.astype(np.float64), qx.astype(np.float64)
    for _ in range(FE_ITER):
        d = field(py, px_)
        px_, py = qx - d[:, 0], qy - d[:, 1]
    d = field(py, px_)
    resid = np.hypot(px_ + d[:, 0] - qx, py + d[:, 1] - qy)
    pr, pc = np.clip(np.round(py).astype(int), 0, H - 1), np.clip(np.round(px_).astype(int), 0, W_ - 1)
    good = (resid < 0.3) & fm[pr, pc] & moved[pr, pc]
    # источник каждого пикселя превью: свой (EA) или p(q)
    src_y = np.full((H, W_), np.nan)
    src_x = np.full((H, W_), np.nan)
    src_y[ys, xs], src_x[ys, xs] = ys, xs
    src_y[qy[good], qx[good]], src_x[qy[good], qx[good]] = py[good], px_[good]
    tgt = np.isfinite(src_y)
    ty, tx = np.nonzero(tgt)
    sy, sx = src_y[ty, tx], src_x[ty, tx]
    # затенение и прозрачность — из источника (ближайший пиксель свитера)
    idx = -np.ones((H, W_), np.int64)
    idx[ys, xs] = np.arange(len(ys))
    jr, jc = np.clip(np.round(sy).astype(int), 0, H - 1), np.clip(np.round(sx).astype(int), 0, W_ - 1)
    j = idx[jr, jc]
    lost = j < 0                                        # округление ушло с свитера — ближайший пиксель свитера
    if lost.any():
        _, (iy2, ix2) = ndi.distance_transform_edt(idx < 0, return_indices=True)
        j[lost] = idx[iy2[jr[lost], jc[lost]], ix2[jr[lost], jc[lost]]]
    tex = np.asarray(Image.open(jersey_png).convert("RGB")).astype(np.float64)
    depth = depth0 = None
    if depth_npz is not None and os.path.exists(depth_npz):
        dz = np.load(depth_npz)
        depth = (dz["seam"].astype(np.float64), dz["perf"].astype(np.float64))
        depth0 = np.dstack(_deisland_arrays(depth, mesh_for(0, 1, 2)))   # в развёртке Edge — для модели позы
    acc = np.zeros((len(ty), 3))
    accd = np.zeros((len(ty), 2))
    offs = ((np.arange(FE_SS) + 0.5) / FE_SS - 0.5) * FE_FOOT
    for oy in offs:
        for ox in offs:
            u, v = pilot._uv_at(m, sy + oy, sx + ox, home=(m["u"][j], m["v"][j]))
            acc += kit3d.sample_bilinear(tex, u, v)[:, :3]
            if depth0 is not None:
                accd += kit3d.sample_bilinear(depth0, u, v)[:, :2]
    rel = (1.0 + FE_SEAM_K * accd[:, 0:1] / FE_SS ** 2 - FE_PERF_K * accd[:, 1:2] / FE_SS ** 2)
    col = np.clip((m["gain"][j] * acc / FE_SS ** 2 + m["bias"][j]) * rel, 0, 255)
    out = m["base"].copy()
    out[ty, tx, :3] = np.round(col).astype(np.uint8)
    out[ty, tx, 3] = m["alpha"][j]
    n_roi = 0
    if isl_png is not None:
        Jmap = -np.ones((H, W_), np.int64)
        Jmap[ty, tx] = j
        perr = np.full(len(ys), np.inf)
        perr[fin] = np.linalg.norm(np.c_[Pp[fin], np.ones(fin.sum())] @ A - np.c_[xs[fin], ys[fin]], axis=1)
        n_roi = _fe_collar(out, m, A, isl_png, Jmap, front, perr, depth)
    fe_preview_edge.info = {"fit_px": [round(float(v), 2) for v in np.percentile(err, [50, 90])],
                            "max_shift_px": round(float(np.abs(F).max()), 2), "warped_px": int(good.sum()),
                            "collar_px": n_roi, "shield": getattr(_fe_collar, "shield", None)}
    return Image.fromarray(out, "RGBA")


def cmd_slot(a):
    """Комплекты формы в слот стиля SLOT_STYLE (номера — реестр nhl24_kits.json): слои → kitpaint pack → a.out
    (раскладка cache:), превью меню — в позе EA (fb.pilot.fe_preview_ea), наклейка на шлем — как у формы-образца."""
    import json
    import shutil
    import subprocess
    from PIL import Image
    from . import pilot
    reg = json.load(open(os.path.join(REPO, "tools", "legacy_data", "nhl24_kits.json"), encoding="utf-8"))
    regmap = {(k["club"], k["kit"]): k for k in reg["kits"]}
    cur = os.path.join(WORK, "cur_kits")
    flat_kit = next(k for k, sp in SLOT_KITS.items() if sp["sock"] == "flat")
    for kit, spec in SLOT_KITS.items():
        r = regmap.get((a.club, spec["kit"]))
        if r is None or r.get("style", 1) != SLOT_STYLE:
            sys.exit(f"{a.club} {spec['kit']}: нет в реестре со стилем {SLOT_STYLE} (nhl24.py alloc … --style 0)")
        new = f"{SLOT_STYLE}_{r['art']}_{r['variant']}"
        src = os.path.join(KITS_OUT, f"{a.club}_{kit}")
        leg = os.path.join(cur, spec["legacy"])
        if not os.path.exists(os.path.join(leg, "kit.json")):
            J.unpack_kit(spec["legacy"], leg)
        d = os.path.join(WORK, "slot", "kits", f"{a.club}_{kit}")
        os.makedirs(d, exist_ok=True)
        for f in ("jersey_cm", "jersey_nm", "jersey_sm", "font_cm", "font_nm", "font_sm"):
            shutil.copy2(os.path.join(src, f + ".png"), os.path.join(d, f + ".png"))
        for f in ("name_cm", "pant_cm", "pant_nm", "pant_sm"):
            shutil.copy2(os.path.join(leg, f + ".png"), os.path.join(d, f + ".png"))
        flat_src = os.path.join(KITS_OUT, f"{a.club}_{flat_kit}", "sock_cm.png")
        if spec["sock"] == "flat":
            im, info = flat_sock(flat_src)
            im.save(os.path.join(d, "sock_cm.png"))
            print(f"  гетры {kit}: полоса строк {info[0]:.1f}–{info[1]:.1f}, края {[round(e, 1) for e in info[2]]}")
        else:                                            # полоса — в строках своих гетр (flat_sock) другой формы
            im, info = flat_sock(flat_src)
            H_ = im.size[1]
            was, now = place_sock(os.path.join(leg, "sock_cm.png"), os.path.join(d, "sock_cm.png"),
                                  info[0] / H_, info[1] / H_)
            print(f"  гетры {kit}: полоса строк {was[0]:.0f}–{was[1]:.0f} → {now[0]:.1f}–{now[1]:.1f} (как у {flat_kit})")
        tmp = os.path.join(d, "_edge_layout_cm.png")
        n = deislanded(os.path.join(d, "jersey_cm.png"), tmp)
        fe_preview_edge(tmp, os.path.join(d, "jersey_cm.png"), os.path.join(src, "relief_depth.npz")).save(
            os.path.join(d, "fe.png"))                                        # поза EA, ворот —
        #                                                                     поднятый, перед — проекцией сетки
        os.remove(tmp)
        tpl = J.kit_template(new)
        tdir = os.path.join(cur, tpl)
        if not os.path.exists(os.path.join(tdir, "kit.json")):
            J.unpack_kit(tpl, tdir)
        shutil.copy2(os.path.join(tdir, "kit.json"), os.path.join(d, "kit.json"))
        cmd = [sys.executable, os.path.join(REPO, "tools", "kitpaint.py"), "--game", "legacy", "pack", d, new, a.out]
        rr = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        print(rr.stdout[-800:], rr.stderr[-800:])
        if rr.returncode:
            sys.exit(f"{kit}: kitpaint pack — ошибка")
        ls = spec["legacy"].split("_")
        h = J.helmet_copy(ls[1], ls[2], r["art"], r["variant"], a.out)
        print(f"{a.club} {spec['kit']} → {new}: шаблон {tpl}, превью (перед ворота на uv0: {n} текселей), "
              f"наклейка на шлем {h}")


PACK_BASE = os.path.join(REPO, "game", "work", "nhl24", "out", "pack-adidas")   # установленный пакет (16.10)


def cmd_pack(a):
    """Пакет NHL 24 (tools/legacy_data/nhl24.py build) = установленный пакет + сетки свитера слота стиля 0 и его
    затенение (вместо сеток adidas) + формы клуба SLOT_KITS (файлы из a.src, раскладка cache:)."""
    import hashlib
    import json
    import re
    import shutil
    reg = json.load(open(os.path.join(REPO, "tools", "legacy_data", "nhl24_kits.json"), encoding="utf-8"))
    regmap = {(k["club"], k["kit"]): k for k in reg["kits"]}
    if os.path.exists(a.out):
        sys.exit(f"{a.out} уже есть — уберите или укажите --out")
    shutil.copytree(os.path.join(PACK_BASE, "cache"), os.path.join(a.out, "cache"))
    man = json.load(open(os.path.join(PACK_BASE, "manifest.json"), encoding="utf-8"))
    cache = os.path.join(a.out, "cache")

    def put(rel):
        q = os.path.join(cache, *rel.split("/"))
        os.makedirs(os.path.dirname(q), exist_ok=True)
        shutil.copy2(os.path.join(a.src, *rel.split("/")), q)
        return hashlib.md5(open(q, "rb").read()).hexdigest(), os.path.getsize(q)

    mesh_re = re.compile(rf"rendering/jersey/jersey_[01]_{SLOT_STYLE}_\d_\d_\d_\d\.rx2")
    note_mesh = ("сетка свитера Edge с поднятым передом ворота и своей развёрткой переда (fb.edge_kit meshes) — "
                 "слот стиля 0 вместо сеток adidas (пользователь 19.10)")
    n_mesh = 0
    for e in man["files"]:
        if e["type"] == "other" and mesh_re.fullmatch(e["file"]):
            e["md5"], e["size"] = put(e["file"])
            e["note"] = note_mesh
            n_mesh += 1
    have = {e["file"] for e in man["files"]}
    extra = [f"rendering/jersey/texlib_{SLOT_STYLE}_999.rx2"]
    for rel in extra:
        md, sz = put(rel)
        e = {"file": rel, "type": "other", "md5": md, "size": sz, "action": "add",
             "note": "затенение свитера слота стиля 0 — Edge, перед ворота с прежнего места (fb.edge_kit meshes)"}
        if rel in have:
            man["files"] = [x for x in man["files"] if x["file"] != rel]
        man["files"].append(e)
    for kit, spec in SLOT_KITS.items():
        r = regmap[(a.club, spec["kit"])]
        new = f"{SLOT_STYLE}_{r['art']}_{r['variant']}"
        files = {"jersey": f"rendering/jersey/texlib_{new}.rx2", "name": f"rendering/jersey/name_{new}_cm.rx2",
                 "pant": f"rendering/pant/texlib_{new}.rx2", "sock": f"rendering/sock/sock_{new}_cm.rx2",
                 "fe": f"fe/ion/artassets/jerseys/jersey_{new}.big",
                 "helmet": f"rendering/logo/texlib_{r['art']}_{SLOT_STYLE}_{r['variant']}.rx2"}
        notes = {"jersey": "свитер Edge с передом ворота NHL 24 (fb.edge_kit) и шрифт NHL 24",
                 "name": f"карта номера и фамилии — как у формы {spec['legacy']}",
                 "pant": f"шорты — как у основной формы {spec['legacy']}",
                 "sock": ("гетры — полосы гетр NHL 24 ровными строками" if spec["sock"] == "flat"
                          else f"гетры — как у основной формы {spec['legacy']}"),
                 "fe": "превью меню в позе EA (fb.pilot.fe_preview_ea)",
                 "helmet": f"наклейка на шлем — как у формы {spec['legacy']}"}
        for typ, rel in files.items():
            if rel in have:
                sys.exit(f"{rel}: уже в пакете")
            md, sz = put(rel)
            man["files"].append({"file": rel, "type": typ, "md5": md, "size": sz, "action": "add", "note": notes[typ],
                                 "club": a.club, "kit": spec["kit"]})
        man["kits"].append({"club": a.club, "kit": spec["kit"], "variant": r["variant"],
                            "islightcolor": 0 if kit == "home" else 1, "label": spec["label"], "helmet": kit,
                            "phase": 2})    # nhl24.py: строки и шлемы — после adidas (сейв дописывается в конец)
    man["note"] = (man.get("note", "") + f" {a.club}: формы «{SLOT_KITS['home']['label']}» / «{SLOT_KITS['away']['label']}» "
                   "на своей сетке Edge с передом ворота NHL 24 в слоте стиля 0 (сетки adidas сняты, пользователь 19.10).")
    with open(os.path.join(a.out, "manifest.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(man, f, ensure_ascii=False, indent=1)
    print(f"{a.out}: сеток заменено {n_mesh}, форм {len(man['kits'])}, файлов {len(man['files'])}")


def cmd_meshes(a):
    """Сетки свитера (24 полевых, 6 вратарских) и затенение — в слот стиля SLOT_STYLE, раскладка cache: в a.out."""
    out = a.out
    n = 0
    for t, pp in SKATERS:
        for lod in (2, 0, 3):
            M = mesh_for(t, pp, lod)
            rel = J.skater_rel(t, pp, lod, SLOT_STYLE)
            info = write_mesh(M, rel, out)
            n += 1
            print(f"{rel}: {info}, остров {int(M.get('island', np.zeros(1)).sum())} вершин", flush=True)
    for h in GOALIE_H:
        for lod in (2, 0, 3):
            M, dinfo = goalie_mesh_for(h, lod)
            rel = J.goalie_rel(h, lod, SLOT_STYLE)
            info = write_mesh(M, rel, out)
            n += 1
            print(f"{rel}: {info}, остров {int(M.get('island', np.zeros(1)).sum())} вершин, ворот {dinfo}", flush=True)
    rel, names = ao_for_slot(out)
    print(f"{rel}: {names}")
    print(f"{n} сеток → {out}")


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("preview")
    p.add_argument("out")
    p = sub.add_parser("kit")
    p.add_argument("--club", default="MIN")
    p.add_argument("--kits", default="home,away")
    p = sub.add_parser("meshes")
    p.add_argument("--out", default=os.path.join(WORK, "slot", "cache"))
    p = sub.add_parser("slot")
    p.add_argument("--club", default="MIN")
    p.add_argument("--out", default=os.path.join(WORK, "slot", "cache"))
    p = sub.add_parser("pack")
    p.add_argument("--club", default="MIN")
    p.add_argument("--src", default=os.path.join(WORK, "slot", "cache"))
    p.add_argument("--out", default=os.path.join(REPO, "game", "work", "nhl24", "out", "pack-edge"))
    a = ap.parse_args()
    {"preview": cmd_preview, "kit": cmd_kit, "meshes": cmd_meshes, "slot": cmd_slot, "pack": cmd_pack}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
