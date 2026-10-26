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
  python -m fb.edge_kit kit --club NJD                    # текстуры формы клуба (профиль fb/edge_clubs.toml) → WORK/out
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


ISLAND_PAD_CM = False              # профиль island_pad_cm = true | { форма = true } (23.10, агент review-e, NYR выезд): поле
#                                    вокруг острова развёртки и в jersey_cm — цветом ближайшего текселя острова (pad_island). Без
#                                    поля там прежний цвет до правок после переноса (chest_bands): фильтрация и мипы на шве
#                                    острова тянули его на свитер — у NYR выезда синяя точка и черта под синей полосой у |x| 11 см,
#                                    белая чёрточка в синей кокетке у ±14 см (и прежнее место острова — fill_old_place — бралось
#                                    с ним же). Цвет поля — свитера в той же 3D-точке: развёртка ближайшего треугольника острова
#                                    продолжена за край, цвет — ближайшего по 3D текселя основной развёртки (не дальше
#                                    ISLAND_PAD_3D); ближайший тексель острова продолжал край полосы поперёк шва лесенкой — слабая
#                                    синяя черта оставалась. Нет — как было
ISLAND_PAD_CM_KITS = None          # island_pad_cm таблицей по форме (use_kit)
ISLAND_PAD_PX = 8                  # текселей 1024² за краем острова
ISLAND_PAD_3D = 0.006              # м: тексель основной развёртки дальше от 3D-точки поля — поле ближайшим текселем острова


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
    if ISLAND_PAD_CM:                                    # и цвет: поле острова — ближайшим текселем острова (NYR, 23.10)
        path = os.path.join(od, "jersey_cm.png")
        im0 = Image.open(path)
        mode = im0.mode
        im = np.asarray(im0).copy()
        tid, _ = kit3d.raster_uv({"uv": M["uv"], "tri": M["tri"]}, im.shape[0])
        inside = tid >= 0
        isl = inside & M["island"][M["tri"]].all(1)[np.maximum(tid, 0)]
        d, (iy, ix) = ndi.distance_transform_edt(~inside, return_indices=True)
        gut = ~inside & (d <= ISLAND_PAD_PX * im.shape[0] / 1024.0) & isl[iy, ix]
        gy, gx = np.nonzero(gut)
        T = M["tri"][tid[iy[gy, gx], ix[gy, gx]]]       # треугольник острова ближайшего текселя: барицентры вне его
        S_ = im.shape[0]
        a_, b_, c_ = (M["uv"][T[:, k]] for k in range(3))
        v0, v1 = b_ - a_, c_ - a_
        v2 = np.stack([(gx + 0.5) / S_, (gy + 0.5) / S_], -1) - a_
        d00, d01, d11 = (v0 * v0).sum(1), (v0 * v1).sum(1), (v1 * v1).sum(1)
        d20, d21 = (v2 * v0).sum(1), (v2 * v1).sum(1)
        den = np.where(np.abs(d00 * d11 - d01 * d01) < 1e-18, 1e-18, d00 * d11 - d01 * d01)
        l1, l2 = (d11 * d20 - d01 * d21) / den, (d00 * d21 - d01 * d20) / den
        P3 = (np.stack([1 - l1 - l2, l1, l2], -1)[:, :, None] * M["pos"][T]).sum(1)   # 3D-точка за краем острова
        tid_b, bar_b = kit3d.raster_uv({"uv": M["uv"], "tri": M["tri"]}, S_)
        my, mx = np.nonzero(inside & ~isl)
        Pm = (bar_b[my, mx][:, :, None] * M["pos"][M["tri"][tid_b[my, mx]]]).sum(1)
        Nm = (bar_b[my, mx][:, :, None] * M["nrm"][M["tri"][tid_b[my, mx]]]).sum(1)
        fr = Nm[:, 2] > -0.5                             # не подкладка переда (нормаль внутрь)
        my, mx, Pm = my[fr], mx[fr], Pm[fr]
        from scipy.spatial import cKDTree
        dist, j = cKDTree(Pm).query(P3)
        ok = dist < ISLAND_PAD_3D
        old = im.copy()
        im[gy[ok], gx[ok]] = old[my[j[ok]], mx[j[ok]]]
        im[gy[~ok], gx[~ok]] = old[iy[gy[~ok], gx[~ok]], ix[gy[~ok], gx[~ok]]]
        Image.fromarray(im, mode).save(path)
        print("  поле острова в jersey_cm (island_pad_cm):", int(gut.sum()), "текселей, по 3D-точке", int(ok.sum()))


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
TORSO_SHIFT = None                 # профиль torso_shift (23.10, пользователь, MTL дом: «полосу с логотипом опустить — в жизни
#                                    она проходит посередине номера, сейчас выше середины»): [см, y0, y1, y2, y3] — рисунок
#                                    туловища ниже на столько (точка на высоте y берёт источник с y + сдвиг): с y0 до y1
#                                    сдвиг плавно растёт, до y2 — весь, к y3 — на нет (м, высоты Edge; спад — не короче
#                                    1,5 × сдвига, иначе рисунок у спада повторяется). Герб (нашивка crest) — ниже на столько
#                                    же (torso_shift_crest: нашивки ставятся по 3D-точке, не по развёртке). Или { форма = [...] }
TORSO_SHIFT_KITS = None
SLEEVE_BY_BONES = False            # прежний способ (рукав — по весам костей) — выключен
SEAM_SMOOTH = 30                   # итераций сглаживания поля шва на сетке Edge
TOP_X, TOP_Z = (-0.6, 0.6), (-0.3, 0.3)   # м: сетка проекции сверху (верх плеч)
GRID_XZ = 0.001
TOPP_NY = (0.55, 0.8)              # y нормали: от «наклонно» к «верх» — проекция сверху
TOPP_NY_DEFAULT = TOPP_NY          # профиль top_proj = [от, до] (22.10, NYR выезд): у полос через плечи (белая, красная, белая,
#                                    синяя у края кокетки) на наклонном верхе груди смесь туловища и проекции сверху гнула их
#                                    петлями у ворота; выше — проекция только на самом верхе плеча
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
        self.g_hem = hem.hem_grid(src, hem.HEM_H + HEM_SHIFT + 0.01)
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
        if TORSO_SHIFT:                                  # полоса через туловище ниже (профиль torso_shift, MTL дом)
            yq = yq + torso_shift_dy(P[:, 1])
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
        u_h, ok_h = hem.lookup(self.g_hem, phi, dh + HEM_SHIFT)   # полосы ниже на HEM_SHIFT (профиль hem_shift_cm)
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
SLV_BLEND_DEFAULT = SLV_BLEND      # профиль sleeve_blend (u, 22.10, WSH): переход шире — у панели вдоль руки (белая / красная
#                                    WSH) на стыке карты рукава и ближайшей точки (u 0,234) край ступенькой ~1 см: карты
#                                    расходятся по углу; на ширине перехода UV меняется плавно — край идёт наклонно
HEM_H_DEFAULT = 0.09               # м: зона низа «от края» (fb.hem.HEM_H) без поля hem_h в профиле
HEM_SHIFT = 0.0                    # м: профиль hem_shift_cm — полосы низа ниже на столько (точка на высоте d над краем
#                                    берёт рисунок источника с d + сдвиг; LAK 22.10: «полоску внизу — пониже»)
FONT_NAME_SCALE = 1.0              # профиль font_name_scale: буквы фамилии в атласе крупнее в клетках (fb.fonts.scale_glyphs)
FONT_CAPTAIN_X = 1.0               # профиль font_captain_x: буквы капитана C и A шире
NAME_ZONE_SCALE = 1.0              # профиль name_zone_scale: зона фамилии в карте номеров ниже в столько раз (верх на месте)
FONT_NAME_FIT = None               # профиль font_name_fit = "auto": шрифт и зона фамилии — расчётом (name_font_fit)
NAME_ZONE_LIFT = 0.0               # см: профиль name_zone_lift_cm — зона фамилии выше на спине на столько (SEA 22.10)
FONT_NAME_ANCHOR = "center"        # профиль font_name_anchor: center | top — верх букв на месте (мельче — место до номера, LAK)
SLV_FILL_EXT_TOP = None            # sleeve_top24: заполнение тканью за концом рукава — до верха полос (+0,02), не меньше SLV_FILL_EXT
SLV_FILL_EXT = 0.035               # u Edge за концом рукава (у проймы): при заполнении тканью (SLV_FILL_S24) — тоже ткань:
SLV_FILL_BLEND = 0.01              # там ближайшая точка NHL 24 брала его верхнюю полосу — золотая дуга (BOS, 21.10)
SLV_X = 0.15                       # м: |x| больше — рукав
SLV_PHI = 0.5                      # град — шаг таблиц угла
# Полосы — ближе к кисти (правило пользователя 11.10, kit_rules.toml [sleeve]: сжатие рисунка к манжете в k раз, зазор
# до зоны номера на плече ≥ gap_min). У fb.pilot оно сдвигало уже готовую текстуру по строкам развёртки — у Edge в
# строках подмышки вместе с рукавом тянуло и грудную полосу туловища (бежевое на рукаве, пользователь, 19.10), а швы
# рельефа оставались на прежнем месте. Здесь — сжатие в самом переносе рукава (SleeveMap): цвет и рельеф вместе.
SLV_COMPRESS = None                # (k, d_top): задаётся сборкой (cmd_kit) по зоне номера шаблона; None — без сжатия
SLV_RING_FRAC = 0.8                # граница полосы рукава — смена цвета не меньше чем на такой доле кольца (21.10)
SLV_TOP_MARGIN = 0.01              # м по средней линии рукава Edge: верх полос ближе к концу рукава (SLV_U[1]) — выше
#                                    колена сжатия рукав — тканью над полосами (SLV_FILL_S24). 21.10, BOS выезд: верх полос
#                                    0,2339 при конце 0,234 — от колена до конца источник упирался в конец таблицы рукава
#                                    (s NHL 24 0,227 — граница золото / белое), верх рукава ~5,5 см заливался золотом
SLV_FILL_TEXELS = 3                # текселей NHL 24 (2048) над верхней границей полос — цвет ткани для заполнения
SLV_FILL_S24 = None                # задаёт sleeve_compress: s NHL 24, откуда брать ткань выше колена; None — как было
BRAND_WIN = None                   # профиль brand_win: окно (доля развёртки) замера цвета логотипа источника сзади у ворота
#                                    для своей надписи (kit_fix.BrandSwap, [brand] back.nhl24_win 0,02). 22.10, BUF выезд: в
#                                    окно попадала золотая полоса под кокеткой — надпись выходила розоватой (медиана белого и
#                                    золотого); 0,012 — только логотип. Нет — как было
SLEEVE_TOP24 = None                # профиль sleeve_top24 (22.10, агент plain, SJS): верх полос рукава источника, s NHL 24 — когда
#                                    блок полос выше конца рукава Edge (у SJS до 0,243 при конце карты рукава ~0,230: верхняя
#                                    полоса — чёрная дома, бирюзовая в гостях — пропадала, а «ткань над полосами» бралась
#                                    внутри неё — чёрный верх рукава) и граница не находится (дома доля кольца < 0,8: полосы
#                                    у верха острова NHL 24 загибаются). Соответствие s Edge → s NHL 24 за концом рукава —
#                                    продолжением по наклону (SleeveMap.s24_of), сжатие к кисти — до этого верха.
#                                    Число или { форма = число }; нет — как было
SLV_EXTRAP_W = 0.03                # s Edge: наклон s NHL 24 / s Edge для продолжения — по последним 0,03 карты рукава
SLEEVE_FILL = None                 # профиль sleeve_fill = "below": ткань над полосами — цвет рукава под ними (у кисти), не
#                                    над верхней границей (MTL дом 22.10: блок полос до конца рукава, над ним 1,5 мм красного —
#                                    бралась белая полоса, верх рукавов выходил белым); None — как BOS (над верхней)
SLEEVE_FILL_SIDE = False           # профиль sleeve_fill_side (23.10, агент fix-c, SEA выезд): ткань над полосами (SLV_FILL_S24) —
#                                    по верхней границе полос своей руки. Без поля граница мерится на левом рукаве, s
#                                    заполнения общий; у NHL 27 SEA выезда рукава несимметричны (справа низ полос на ~2,5 см
#                                    ближе к плечу, верх бирюзы — s 0,2385 против 0,2366 слева): s 0,2378 справа ещё в бирюзе —
#                                    выше колена сжатия правый рукав заливался ею, номер на правой руке — на бирюзе (kitport
#                                    audit: 31 % белого под зоной 3). true или { форма = true }; нет — как было
SLEEVE_FILL_SIDE_KITS = None       # sleeve_fill_side таблицей по форме — значение формы ставит use_kit
SLV_FILL_S24_R = None              # задаёт sleeve_compress при sleeve_fill_side: s NHL 24 ткани правого рукава; None — как левый
SLEEVE_MIRROR = None               # профиль sleeve_mirror (23.10, агент fix-c, SEA выезд; пользователь: «поправь — правая рука
#                                    как левая»): "left" — правый рукав от манжеты до верха полос — зеркалом левого. У NHL 27
#                                    SEA выезда рукава несимметричны (справа низ полос на ~2,5 см ближе к плечу, бирюза уже —
#                                    sleeve_fill_side выше); развёртка Edge симметрична (u → 1 − u — та же точка руки зеркально,
#                                    медиана 1,5 мм): после переноса тексели правого рукава берутся с левого — цвет (стадия kit,
#                                    после прочих правок рукава) и рельеф с бликом (после rebuild_relief; R нормали — с обратным
#                                    знаком: тангенс — по u). Зона — до колена сжатия к кисти + SLV_MIRROR_PAD, выше — переход
#                                    SLV_MIRROR_BLEND к своему (складки рук разные). "left" или { форма = "left" }; нет — как было
SLEEVE_MIRROR_KITS = None          # sleeve_mirror таблицей по форме — значение формы ставит use_kit
SLV_MIRROR_PAD = 0.006             # s Edge: зона зеркала — до верха полос (колено сжатия) + столько (~1 см ткани над ними)
SLV_MIRROR_BLEND = 0.008           # s Edge: над зоной — переход к своему (рельеф; цвет там — ткань с обеих сторон)
SLV_MIRROR_TOL = 0.02              # м: тексель правого рукава и зеркальный левого — одна точка руки (дальше — другой остров)
SLV_MIRROR_PADPX = 8               # текселей: поля острова (заливка за краем сетки) у зоны — тоже зеркалом (мип-уровни игры)
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
# деление цвета рукав / туловище по шву Edge — в этих зонах v; между ними (верх плеча) — по полю шва NHL 24 (seam_v).
# Профиль armhole_split = "full" — по шву Edge на всей пройме: у рукава другого цвета (VGK, 22.10: серые рукава на
# золоте и белом) граница по полю шва шла зубцами и ступеньками на стыке зон — «неровные линии на плече»
ARMHOLE_SPLIT_ZONES = ARMHOLE_ZONES
ARMHOLE_SPLIT_FULL = ((ARMHOLE_ZONES[0][0], ARMHOLE_ZONES[-1][1]),)


ARMHOLE_FULL_SIGMA = 0.012         # v: сглаживание шва проймы для armhole_split = "full" — у MIN 1_14_0 на 0,57 мыс (u
#                                    0,3350 → 0,3447 → 0,3418): спереди у верха плеча граница рукава шла углом (VGK 22.10)


def _armhole_full():
    from scipy.ndimage import gaussian_filter1d
    vs, us = zip(*ARMHOLE_UV)
    v = np.arange(vs[0], vs[-1] + 1e-9, 0.0025)
    return v, gaussian_filter1d(np.interp(v, vs, us), ARMHOLE_FULL_SIGMA / 0.0025, mode="nearest")


def armhole_u(v):
    if ARMHOLE_SPLIT_ZONES is ARMHOLE_SPLIT_FULL:      # рукав другого цвета: шов сглажен (граница цвета — по нему)
        vs, us = _armhole_full()
    else:
        vs, us = zip(*ARMHOLE_UV)
    return np.interp(v, vs, us)


def armhole_sleeve(tu, tv, x):
    """Тексели (tu, tv) с точками x: (в зоне деления, сторона рукава)."""
    zone = np.zeros(len(tu), bool)
    for v0, v1 in ARMHOLE_SPLIT_ZONES:
        zone |= (tv >= v0) & (tv <= v1)
    zone &= np.abs(x) > ARMHOLE_X
    sE = np.where(x < 0, tu, 1.0 - tu)
    return zone, zone & (sE < armhole_u(tv))


ARMHOLE_CLEAN = 0.02               # u: у armhole_split = "full" полоса у шва проймы, где цвет — с той же строки дальше от шва
ARMHOLE_AA = False                 # профиль armhole_aa = true (23.10, агент review-d, WSH): у шва — смесь цвета рукава и ткани
#                                    по доле текселя (иначе край панели рукава по шву — зубцами в тексель, у плеча ~3 мм)


def armhole_clean(png, mesh, du=ARMHOLE_CLEAN):
    """Граница рукава и туловища — ровно по шву проймы (armhole_u): у шва (|sE − шов| < du) цвет рукава — с той же строки
    на du от шва внутрь рукава, цвет ткани — на du внутрь туловища. Деление по шву (ARMHOLE_SPLIT_FULL) ставит сторону, а
    цвет у шва берётся ближайшей точкой источника — у края его острова рукава (VGK 22.10: золото верха плеча NHL 27
    заходит на кромку рукава) граница шла волной и зубцами. -> текселей перекрашено."""
    from PIL import Image
    a = np.asarray(Image.open(png).convert("RGB"))
    S = a.shape[0]
    tid, bar = kit3d.raster_uv(mesh, S)
    m = tid >= 0
    ys, xs = np.nonzero(m)
    P = (bar[ys, xs][:, :, None] * mesh["pos"][mesh["tri"][tid[ys, xs]]]).sum(1)
    tu, tv = (xs + 0.5) / S, (ys + 0.5) / S
    zone, _ = armhole_sleeve(tu, tv, P[:, 0])
    left = P[:, 0] < 0
    sE = np.where(left, tu, 1.0 - tu)
    au = armhole_u(tv)
    near = zone & (np.abs(sE - au) < du)
    tgt = np.where(sE < au, au - du - 1.5 / S, au + du + 1.5 / S)
    xs_src = np.clip(np.round(np.where(left, tgt, 1.0 - tgt) * S - 0.5).astype(int), 0, S - 1)
    ok = near & m[ys, xs_src]
    out = a.copy()
    out[ys[ok], xs[ok]] = a[ys[ok], xs_src[ok]]
    if ARMHOLE_AA:                                       # у самого шва — смесь по доле текселя на стороне рукава (WSH)
        cov = np.clip((au - sE) * S + 0.5, 0, 1)         # доля текселя до шва (рукав); шов — гладкая кривая armhole_u
        mid = near & (cov > 0) & (cov < 1)
        ts_ = au - du - 1.5 / S
        tb_ = au + du + 1.5 / S
        xs_s = np.clip(np.round(np.where(left, ts_, 1.0 - ts_) * S - 0.5).astype(int), 0, S - 1)
        xs_b = np.clip(np.round(np.where(left, tb_, 1.0 - tb_) * S - 0.5).astype(int), 0, S - 1)
        mid &= m[ys, xs_s] & m[ys, xs_b]
        w_ = cov[mid][:, None]
        out[ys[mid], xs[mid]] = np.round(a[ys[mid], xs_s[mid]] * w_ + a[ys[mid], xs_b[mid]] * (1 - w_)).astype(a.dtype)
    Image.fromarray(out).save(png)
    return int(ok.sum())


SLEEVE_STRIPES_KITS = None         # sleeve_stripes по формам: { away = "fit" } (STL выезд, 23.10: белые выемки полос у
#                                    манжеты на шве снизу рукава — лента NHL 27 со скошенными концами не доходит до шва Edge)
SLEEVE_STRIPES = None              # профиль sleeve_stripes = "fit" | "lines" ("lines" — ломаными, 26.10, ANA: sleeve_stripes_lines)
#                                    "fit" (22.10, агент review-b, OTT): края полос рукава — гладкими
#                                    кривыми (sleeve_stripes_fit). У OTT блок полос NHL 27 почти до плеча и наискосок, сжатия к
#                                    кисти нет (граница не находится, sleeve_top24 гнул полосы галочкой): у конца карты рукава
#                                    (SLV_U, переход SLV_BLEND к ближайшей точке) край полосы рвался — тонкий обрывок рядом с
#                                    полосой, в реглане — ступеньки края. Нет — как было
SLV_FIT_MIN_RUN = 4                # текселей: отрезок цвета в строке короче — сливается с соседом (обрывки)
SLV_FIT_NEAR = 16                  # текселей от гладкого края: перекраска только рядом с ним (дальше — как перенеслось)
SLV_FIT_DEG = 3                    # степень многочлена первого края по строке v; следующие — предыдущий + ширина (квадратика)
SLV_FIT_TRIM = 0.75                # доля строк в подгонке по лучшим (LTS): обрывки и ступеньки — выбросы
SLV_FIT_TOL = 2.0                  # текселей: строка ближе к кривой — своя
SLV_FIT_MIX = 40                   # цвет ближе к отрезку между двумя цветами палитры — смесь на краю, тоже «свой»


def _slv_palette(c, m, min_frac=0.04, merge=40):
    """Основные цвета рукава: ячейки 16³ с долей ≥ min_frac, медиана; ближе merge к уже взятому — не новый."""
    q = (c[m] // 16).astype(int)
    key = q[:, 0] * 256 + q[:, 1] * 16 + q[:, 2]
    keys, cnt = np.unique(key, return_counts=True)
    pal = []
    for i in np.argsort(-cnt):
        if cnt[i] < min_frac * m.sum():
            break
        col = np.median(c[m][key == keys[i]], 0)
        if all(np.abs(col - p).max() > merge for p in pal):
            pal.append(col)
    return np.array(pal)


def _slv_runs(lab):
    """Отрезки одной метки в строке [[метка, начало, конец)]; короче SLV_FIT_MIN_RUN — к соседу (с той же меткой по обе
    стороны — склейка, иначе — к длинному)."""
    out, s = [], 0
    for i in range(1, len(lab) + 1):
        if i == len(lab) or lab[i] != lab[s]:
            out.append([int(lab[s]), s, i])
            s = i
    while True:
        short = [j for j, r in enumerate(out) if r[2] - r[1] < SLV_FIT_MIN_RUN and 0 < j < len(out) - 1]
        if not short:
            return out
        j = min(short, key=lambda j: out[j][2] - out[j][1])
        L, R = out[j - 1], out[j + 1]
        if L[0] == R[0]:
            out[j - 1:j + 2] = [[L[0], L[1], R[2]]]
        elif L[2] - L[1] >= R[2] - R[1]:
            out[j - 1:j + 1] = [[L[0], L[1], out[j][2]]]
        else:
            out[j:j + 2] = [[R[0], out[j][1], R[2]]]


def _slv_robust(v, b, deg):
    """Многочлен b(v) с отсевом: сначала по доле SLV_FIT_TRIM лучших строк (LTS), потом — все ближе SLV_FIT_TOL (и 3σ)."""
    deg = min(deg, max(0, len(v) // 40))
    c = np.polyfit(v, b, deg)
    keep = np.ones(len(v), bool)
    for _ in range(8):
        res = np.abs(b - np.polyval(c, v))
        keep = res <= np.quantile(res, SLV_FIT_TRIM)
        c = np.polyfit(v[keep], b[keep], deg)
    for _ in range(4):
        res = np.abs(b - np.polyval(c, v))
        keep = res < max(SLV_FIT_TOL, 3.0 * (res[keep].std() + 1e-6))
        c = np.polyfit(v[keep], b[keep], deg)
    return c, keep


def _slv_fit_side(a, reg):
    """Один рукав (развёртка — как у левого: u вдоль руки, кольцо — строка v). -> (новый цвет, отчёт)."""
    S = a.shape[0]
    pal = _slv_palette(a, reg)
    if len(pal) < 2:
        return a, "один цвет — без изменений"
    dist = np.stack([np.abs(a - p).max(-1) for p in pal], -1)
    lab, dm = dist.argmin(-1), dist.min(-1)
    for i in range(len(pal)):                            # смесь двух цветов (сглаженный край) — тоже «свой» цвет
        for j in range(i + 1, len(pal)):
            e = pal[j] - pal[i]
            t = np.clip(((a - pal[i]) * e).sum(-1) / max((e * e).sum(), 1e-6), 0, 1)
            dm = np.minimum(dm, np.abs(a - (pal[i] + t[..., None] * e)).max(-1))
    ok = reg & (dm < SLV_FIT_MIX)
    rows = np.nonzero(reg.any(1))[0]
    data, seqs = {}, {}
    for r in rows:                                       # строки с чужим цветом (нашивка) — не в замер
        cols = np.nonzero(reg[r])[0]
        x0, x1 = cols.min(), cols.max() + 1
        if ok[r, x0:x1].all():
            rr = _slv_runs(lab[r, x0:x1])
            data[r] = (x0, rr)
            key = tuple(q[0] for q in rr)
            seqs[key] = seqs.get(key, 0) + 1
    if not data:
        return a, "нет строк без чужих цветов"
    pat = max(seqs, key=lambda k: (len(k), seqs[k]) if seqs[k] > 0.15 * len(data) else (0, 0))
    nb = len(pat) - 1
    obs = [([], []) for _ in range(nb)]
    for r, (x0, rr) in data.items():                     # весь рисунок или его начало (конец срезан проймой)
        key = tuple(q[0] for q in rr)
        if key == pat[:len(key)]:
            for k in range(len(key) - 1):
                obs[k][0].append(r)
                obs[k][1].append(rr[k][2] + x0)
    fits, rep = [], []
    for k in range(nb):
        v, b = np.array(obs[k][0], float), np.array(obs[k][1], float)
        if len(v) < 20 or (k and fits[k - 1] is None):
            fits.append(None)
            continue
        if k == 0:
            c, keep = _slv_robust(v / S, b, SLV_FIT_DEG)
            f = (lambda c: lambda t: np.polyval(c, t))(c)
        else:                                            # ширина полосы (промежутка) по кольцу — гладкая
            prev = fits[k - 1][0]
            c, keep = _slv_robust(v / S, b - prev(v / S), 2)
            f = (lambda c, prev: lambda t: prev(t) + np.polyval(c, t))(c, prev)
        fits.append((f, v.min() - 3, v.max() + 3))
        rep.append(f"край {k}: {int((~keep).sum())} из {len(v)} строк — выбросы, до {np.abs(b - f(v / S)).max():.0f} px")
    out, n = a.copy(), 0
    for r in rows:
        bs = [(k, float(f[0]((r + 0.5) / S))) for k, f in enumerate(fits) if f is not None and f[1] <= r <= f[2]]
        if not bs:
            continue
        cols = np.nonzero(reg[r])[0]
        x = cols + 0.5
        sel = ok[r, cols] & (np.min([np.abs(x - bv) for _, bv in bs], 0) < SLV_FIT_NEAR)
        for i in np.nonzero(sel)[0]:
            seg, frac = 0, None
            for k, bv in bs:
                if x[i] - 0.5 >= bv:
                    seg = k + 1
                elif x[i] + 0.5 > bv:
                    frac = (k, bv - (x[i] - 0.5))        # доля текселя до края — смесь цветов
            col = pal[pat[seg]] if frac is None else frac[1] * pal[pat[frac[0]]] + (1 - frac[1]) * pal[pat[frac[0] + 1]]
            if np.abs(col - a[r, cols[i]]).max() > 3:
                out[r, cols[i]] = col
                n += 1
    return out, (f"цвета {np.round(pal).astype(int).tolist()}, рисунок {pat}; " + "; ".join(rep) + f"; перекрашено {n}")


def sleeve_stripes_fit(png, mesh):
    """Профиль sleeve_stripes = "fit": края полос рукава — гладкие кривые по кольцу. Рукав развёртки Edge (SLV_V, до шва
    проймы armhole_u) — строки v (кольцо вокруг руки), полосы — отрезки цвета вдоль u. В каждой строке — отрезки основных
    цветов (обрывки короче SLV_FIT_MIN_RUN — к соседу), рисунок — самый частый их порядок; край k по строкам — многочлен с
    отсевом выбросов (обрывки у конца карты рукава, ступеньки в реглане), следующий край — предыдущий плюс гладкая
    ширина. Перекраска — только у кривых (SLV_FIT_NEAR) и только «своих» цветов (нашивки и прочее — как есть).
    -> отчёт по рукавам."""
    from PIL import Image
    a = np.asarray(Image.open(png).convert("RGB")).astype(np.float64)
    S = a.shape[0]
    tid, bar = kit3d.raster_uv(mesh, S)
    occ = tid >= 0
    ys, xs = np.nonzero(occ)
    X = np.zeros((S, S))
    X[ys, xs] = (bar[ys, xs] * mesh["pos"][mesh["tri"][tid[ys, xs]]][:, :, 0]).sum(1)
    vv = (np.arange(S) + 0.5) / S
    band = (vv[:, None] >= SLV_V[0]) & (vv[:, None] <= SLV_V[1])
    inner = vv[None, :] < armhole_u(vv)[:, None] + 0.5 / S   # столбец (как у левого рукава) — до шва проймы
    out, rep = a.copy(), []
    for side in (0, 1):
        A = a if side == 0 else a[:, ::-1]
        side_m = (occ & (X < 0)) if side == 0 else (occ & (X > 0))[:, ::-1]
        reg = band & inner & side_m
        res, r_ = _slv_fit_side(A, reg)
        if side == 0:
            out[reg] = res[reg]
        else:
            out[:, ::-1][reg] = res[reg]
        rep.append(("левый: " if side == 0 else "правый: ") + r_)
    Image.fromarray(np.clip(np.round(out), 0, 255).astype(np.uint8)).save(png)
    return rep


SLEEVE_LINES = None                # sleeve_stripes = "lines" — ломаные краёв полос текущей формы (sleeve_stripes_lines: {0 —
#                                    левый рукав, 1 — правый: [(f, r0, r1), …], "S": размер развёртки}): по ним в rebuild_relief
#                                    гасятся швы источника у краёв, свои швы — по ним
SLV_LINES_MAXSEG = 6               # "lines": отрезков ломаной края — не больше
SLV_LINES_PEN = 12.0               # "lines": штраф за узел ломаной — столько × строк (σ = 1 px). Излом «клина» ANA (наклон края
#                                    меняется на ~2 px/строку) — узел; волна переноса в 3–5 px на 20–40 строк и ступенька у конца
#                                    карты рукава — нет (26.10: при 3 узлы вставали и на ступеньки — белая полоса с изломом)
SLV_LINES_TOL = 3.0                # "lines": px — дальше от ломаной (и 3 MAD) — выброс (зубец, крючок), не в замер
SLV_LINES_TRIM = 0.8               # "lines": первый проход узлов — по доле лучших строк
SLV_LINES_MIN_ROWS = 20            # "lines": край, найденный в меньшем числе строк, — не ломаная (строки — как перенеслись)
SLV_LINES_SPECK = 40               # "lines": связная часть одного цвета (8-связность) не больше — не по ломаным (обрывок крючка
#                                    у острия клина ANA в 15 px от края — дальше SLV_FIT_NEAR) — цветом, который даёт рисунок
SLV_LINES_SPECK_TOL = 12.0         # "lines": цвет дальше от цвета рисунка (по каналу) — островок (тёмно-красный след крючка в чёрном)
SLV_LINES_CLEAR = 12.0             # "lines": тексели от ломаной — швы источника на нет (у ANA прежний край отходил до 11 px)


def _pl_segments(x, y, kmax, pen):
    """Разбиение точек (x по возрастанию) на ≤ kmax отрезков с прямой МНК на каждом — ДП по префиксным суммам, штраф pen
    за отрезок. -> концы отрезков (индексы, исключительно)."""
    n = len(x)
    S1 = np.arange(n + 1, dtype=float)
    Sx, Sy = np.concatenate([[0], np.cumsum(x)]), np.concatenate([[0], np.cumsum(y)])
    Sxx, Sxy = np.concatenate([[0], np.cumsum(x * x)]), np.concatenate([[0], np.cumsum(x * y)])
    Syy = np.concatenate([[0], np.cumsum(y * y)])

    def sse(i, j):
        m = S1[j] - S1[i]
        if m < 3:
            return 0.0
        sx, sy = Sx[j] - Sx[i], Sy[j] - Sy[i]
        vx = Sxx[j] - Sxx[i] - sx * sx / m
        cxy = Sxy[j] - Sxy[i] - sx * sy / m
        vy = Syy[j] - Syy[i] - sy * sy / m
        return max(vy - (cxy * cxy / vx if vx > 1e-9 else 0.0), 0.0)
    step = max(1, n // 150)                              # границы отрезков — через step точек
    cand = list(range(0, n, step)) + [n]
    m = len(cand)
    INF = 1e18
    best = np.full((kmax + 1, m), INF)
    arg = np.zeros((kmax + 1, m), int)
    best[0, 0] = 0.0
    for k in range(1, kmax + 1):
        for b in range(1, m):
            bv, ba = INF, 0
            for a_ in range(b):
                if cand[b] - cand[a_] < 6 or best[k - 1, a_] >= INF:
                    continue
                c_ = best[k - 1, a_] + sse(cand[a_], cand[b])
                if c_ < bv:
                    bv, ba = c_, a_
            best[k, b], arg[k, b] = bv, ba
    k = int(np.argmin([best[k, m - 1] + pen * k for k in range(1, kmax + 1)])) + 1
    ends, b = [], m - 1
    for kk in range(k, 0, -1):
        ends.append(cand[b])
        b = arg[kk, b]
    return sorted(ends)


def _pl_fit(x, y):
    """Непрерывная ломаная y(x) с отсевом: узлы — ДП (_pl_segments) по лучшим SLV_LINES_TRIM точкам, потом МНК по базе
    (x − узел)+; выбросы — дальше SLV_LINES_TOL и 3 MAD. -> (f, inliers, узлы)."""
    pen = SLV_LINES_PEN * len(x)
    keep = np.ones(len(x), bool)
    knots, c = [], None
    for it in range(6):
        xs, ys = x[keep], y[keep]
        ends = _pl_segments(xs, ys, SLV_LINES_MAXSEG, pen * keep.mean())
        knots = [0.5 * (xs[e - 1] + xs[e]) for e in ends[:-1]]
        A = np.stack([np.ones(len(x)), x] + [np.maximum(0, x - t) for t in knots], 1)
        c, *_ = np.linalg.lstsq(A[keep], y[keep], rcond=None)
        res = np.abs(A @ c - y)
        if it == 0:
            new = res <= np.quantile(res, SLV_LINES_TRIM)
        else:
            new = res < max(SLV_LINES_TOL, 3.0 * 1.4826 * np.median(res[keep]))
        if new.sum() < 10 or (it > 0 and (new == keep).all()):
            break
        keep = new
    kt = tuple(knots)

    def f(t, c=c, kt=kt):
        t = np.asarray(t, float)
        return c[0] + c[1] * t + sum(cj * np.maximum(0, t - kj) for cj, kj in zip(c[2:], kt))
    return f, keep, list(knots)


def _slv_lines_side(a, reg):
    """Один рукав (развёртка — как у левого): края полос — ломаные по строкам (sleeve_stripes = "lines"). Рисунок — как у
    _slv_fit_side (отрезки основных цветов в строке, самый частый порядок), но каждый край — своя ломаная с отсевом
    (_pl_fit): «клин» — острые изломы, не дуга многочлена. Перекраска — у ломаных (SLV_FIT_NEAR) и только «своих» цветов,
    потом — островки одного цвета до SLV_LINES_SPECK, не по рисунку ломаных. -> (новый цвет, отчёт, ломаные)."""
    from scipy import ndimage as ndi
    S = a.shape[0]
    pal = _slv_palette(a, reg)
    if len(pal) < 2:
        return a, "один цвет — без изменений", []
    dist = np.stack([np.abs(a - p).max(-1) for p in pal], -1)
    lab, dm = dist.argmin(-1), dist.min(-1)
    for i in range(len(pal)):                            # смесь двух цветов (сглаженный край) — тоже «свой» цвет
        for j in range(i + 1, len(pal)):
            e = pal[j] - pal[i]
            t = np.clip(((a - pal[i]) * e).sum(-1) / max((e * e).sum(), 1e-6), 0, 1)
            dm = np.minimum(dm, np.abs(a - (pal[i] + t[..., None] * e)).max(-1))
    ok = reg & (dm < SLV_FIT_MIX)
    rows = np.nonzero(reg.any(1))[0]
    data, seqs = {}, {}
    for r in rows:                                       # строки с чужим цветом (нашивка) — не в замер
        cols = np.nonzero(reg[r])[0]
        x0, x1 = cols.min(), cols.max() + 1
        if ok[r, x0:x1].all():
            rr = _slv_runs(lab[r, x0:x1])
            data[r] = (x0, rr)
            key = tuple(q[0] for q in rr)
            seqs[key] = seqs.get(key, 0) + 1
    if not data:
        return a, "нет строк без чужих цветов", []
    pat = max(seqs, key=lambda k: (len(k), seqs[k]) if seqs[k] > 0.15 * len(data) else (0, 0))
    obs = {}
    for r, (x0, rr) in data.items():                     # весь рисунок или его начало (конец срезан проймой)
        key = tuple(q[0] for q in rr)
        if key == pat[:len(key)]:
            for k in range(len(key) - 1):
                obs.setdefault(k, {})[r] = rr[k][2] + x0
    fits, rep = {}, []
    for k in range(len(pat) - 1):
        if len(obs.get(k, {})) < SLV_LINES_MIN_ROWS:
            continue
        v = np.array(sorted(obs[k]), float)
        b = np.array([obs[k][int(r)] for r in v], float)
        f, keep, knots = _pl_fit(v, b)
        if keep.mean() < 0.6:
            rep.append(f"край {k}: не ломаная ({int(keep.sum())} из {len(v)} строк)")
            continue
        fits[k] = (f, v.min() - 3, v.max() + 3)
        rep.append(f"край {k}: {len(knots) + 1} отр. (узлы v {[round(float(t) / S, 3) for t in knots]}), выбросов "
                   f"{int((~keep).sum())} из {len(v)}, до {np.abs(b - f(v)).max():.0f} px")
    out, n = a.copy(), 0
    want = np.full(a.shape[:2], -1)                      # метка цвета по ломаным (строки, где края без пропусков)
    dedge = np.full(a.shape[:2], np.inf)                 # тексели до ближайшего края по строке
    for r in rows:
        bs = [(k, float(fits[k][0](r))) for k in sorted(fits) if fits[k][1] <= r <= fits[k][2]]
        if not bs:
            continue
        ks = [k for k, _ in bs]
        if ks != list(range(ks[0], ks[-1] + 1)) or any(bs[i][1] >= bs[i + 1][1] for i in range(len(bs) - 1)):
            continue                                     # пропуск края или края перепутались — строку не трогать
        cols = np.nonzero(reg[r])[0]
        x = cols + 0.5
        seg = np.full(len(cols), ks[0])
        for k, bv in bs:
            seg = np.where(x >= bv, k + 1, seg)
        want[r, cols] = np.asarray(pat)[seg]
        dedge[r, cols] = np.min([np.abs(x - bv) for _, bv in bs], 0)
        sel = ok[r, cols] & (dedge[r, cols] < SLV_FIT_NEAR)
        for i in np.nonzero(sel)[0]:
            sg, frac = ks[0], None
            for k, bv in bs:
                if x[i] - 0.5 >= bv:
                    sg = k + 1
                elif x[i] + 0.5 > bv:
                    frac = (k, bv - (x[i] - 0.5))        # доля текселя до края — смесь цветов
            col = pal[pat[sg]] if frac is None else frac[1] * pal[pat[frac[0]]] + (1 - frac[1]) * pal[pat[frac[0] + 1]]
            if np.abs(col - a[r, cols[i]]).max() > 3:
                out[r, cols[i]] = col
                n += 1
    # остатки не по рисунку (обрывок крючка у острия клина ANA — дальше SLV_FIT_NEAR от края): связные части (8-связность)
    # до SLV_LINES_SPECK текселей, где цвет далеко от цвета рисунка по ломаным (не у самого края), — цветом рисунка
    wc = pal[np.clip(want, 0, None)]
    bad = ok & (want >= 0) & (dedge > 1.0) & (np.abs(out - wc).max(-1) > SLV_LINES_SPECK_TOL)
    cc, nc = ndi.label(bad, structure=np.ones((3, 3)))
    nsp = 0
    if nc:
        sizes = ndi.sum(np.ones_like(cc), cc, range(1, nc + 1))
        small = np.isin(cc, np.nonzero(sizes <= SLV_LINES_SPECK)[0] + 1)
        out[small] = wc[small]
        nsp = int(small.sum())
    return out, (f"цвета {np.round(pal).astype(int).tolist()}, рисунок {pat}; " + "; ".join(rep)
                 + f"; перекрашено {n}, островков — {nsp} текселей"), [fits[k] for k in sorted(fits)]


def sleeve_stripes_lines(png, mesh):
    """Профиль sleeve_stripes = "lines" (26.10, ANA; пользователь после игры: «кривые предплечья немного. полоски неровные
    в районе чёрного клина»): края полос рукава — ломаные по кольцу. У ANA полосы рукава — шеврон («клин»: прямые с острыми
    изломами наискосок через локоть) и заходят за конец карты рукава (SLV_U): перенос по координатам руки гнёт наклонные
    края волной (шум угла по столбцам), у конца карты — ступенька к ближайшей точке, крючки, зубцы. Многочлен «fit» дугой
    скругляет излом. Здесь — та же разбивка на отрезки цветов по строкам, что у sleeve_stripes_fit, край — ломаная
    (_pl_fit), перекраска — у ломаных. Ломаные — в SLEEVE_LINES (рельеф: швы по ним). -> отчёт по рукавам."""
    from PIL import Image
    global SLEEVE_LINES
    a = np.asarray(Image.open(png).convert("RGB")).astype(np.float64)
    S = a.shape[0]
    tid, bar = kit3d.raster_uv(mesh, S)
    occ = tid >= 0
    ys, xs = np.nonzero(occ)
    X = np.zeros((S, S))
    X[ys, xs] = (bar[ys, xs] * mesh["pos"][mesh["tri"][tid[ys, xs]]][:, :, 0]).sum(1)
    vv = (np.arange(S) + 0.5) / S
    band = (vv[:, None] >= SLV_V[0]) & (vv[:, None] <= SLV_V[1])
    inner = vv[None, :] < armhole_u(vv)[:, None] + 0.5 / S   # столбец (как у левого рукава) — до шва проймы
    out, rep, lines = a.copy(), [], {"S": S}
    for side in (0, 1):
        A = a if side == 0 else a[:, ::-1]
        side_m = (occ & (X < 0)) if side == 0 else (occ & (X > 0))[:, ::-1]
        reg = band & inner & side_m
        res, r_, fl = _slv_lines_side(A, reg)
        if side == 0:
            out[reg] = res[reg]
        else:
            out[:, ::-1][reg] = res[reg]
        lines[side] = fl
        rep.append(("левый: " if side == 0 else "правый: ") + r_)
    Image.fromarray(np.clip(np.round(out), 0, 255).astype(np.uint8)).save(png)
    SLEEVE_LINES = lines
    return rep


def sleeve_lines_dist(u, v, x, lines):
    """Расстояние (тексели развёртки lines["S"], на которой искались ломаные) от точек (u, v; x — сторона тела) до ломаных
    краёв полос рукава (SLEEVE_LINES, тексели как у левого рукава; у правого — зеркально), по нормали к ломаной. Вне рукава
    и строк ломаной — inf."""
    u, v, x = (np.asarray(q, float) for q in (u, v, x))
    d = np.full(u.shape, np.inf)
    S = lines["S"]
    rr = v * S - 0.5                                     # строка (центр текселя r — v = (r + 0,5) / S)
    for side, fits in lines.items():
        if side == "S":
            continue
        uu = u * S if side == 0 else S - u * S           # положение по строке, как у краёв ломаных (тексель j — [j, j + 1))
        sel = ((x < 0) if side == 0 else (x > 0)) & (v >= SLV_V[0]) & (v <= SLV_V[1]) & (uu / S < armhole_u(v) + 0.5 / S)
        for f, r0, r1 in fits:
            k = sel & (rr >= r0) & (rr <= r1)
            if not k.any():
                continue
            b = f(rr[k])
            db = f(rr[k] + 0.5) - f(rr[k] - 0.5)
            d[k] = np.minimum(d[k], np.abs(uu[k] - b) / np.sqrt(1.0 + db * db))
    return d


PIPING_FIT_KITS = None             # piping_fit таблицей по форме (use_kit)
PIPING_FIT = None                  # профиль piping_fit (23.10, агент review-d, CBJ, WSH): [u0, v0, u1, v1] — окно развёртки
#                                    (как у левого рукава; правый — зеркально), список окон (26.10, CBJ: и верхний кант ленты
#                                    со звездой — волной, вне окна 23.10) или { форма = [...] }: кант вдоль руки — гладкими
#                                    кривыми (piping_fit, окна — по очереди). Здесь — список окон; нет — как было


def piping_boxes(v):
    """piping_fit профиля: окно [u0, v0, u1, v1] или список окон -> [[u0, v0, u1, v1], …]."""
    if v is None:
        return None
    if len(v) and isinstance(v[0], (list, tuple)):
        return [[float(x) for x in b] for b in v]
    return [[float(x) for x in v]]
PIPING_NEAR = 12                   # текселей от гладкого края: перекраска только рядом с ним
PIPING_RAMP = 12                   # текселей у концов окна по u: край — от своего (как перенёсся) к гладкому, без ступеньки
PIPING_MIN_ROWS = 20               # столбцов с рисунком меньше — окно не трогается
PIPING_MIX = False                 # профиль piping_mix = true (23.10, агент review-e, WSH): смесь у края канта — не «чужое».
#                                    Фон над / под кантом в столбце — ближайший тексель, но если он смесь (не цвет палитры),
#                                    а следующий — чистый цвет другой метки, фон — этот цвет (WSH дом: у подмышки тексель
#                                    смеси канта и панели, ближе к красному, — фон «красный», край канта рисовался красной
#                                    чёрточкой 1–4 текселя на белой панели, на обеих руках); пограничный тексель канта —
#                                    «чужой» (как есть), только если он и не смесь фона с цветом канта (светлые зубцы в
#                                    тексель на краю канта). Нет — как было




def _piping_bg(rows, c, lab, pure):
    """piping_mix: метка фона столбца c — ближайшая из rows (от канта наружу); смесь, за которой чистый тексель другой
    метки, — не фон."""
    r0 = rows[0]
    if not pure[r0, c] and len(rows) > 1 and abs(int(rows[1]) - int(r0)) == 1 and pure[rows[1], c] and \
            lab[rows[1], c] != lab[r0, c]:
        return lab[rows[1], c]
    return lab[r0, c]


def _piping_mix(cur, bg, pc):
    """piping_mix: цвет cur — смесь фона bg и цвета канта pc (как «смесь с кантом» снаружи канта)."""
    e = pc - bg
    tt = float(np.clip(((cur - bg) * e).sum() / max((e * e).sum(), 1e-6), 0, 1))
    return tt > 0.15 and np.abs(cur - (bg + tt * e)).max() < SLV_FIT_MIX


def _piping_side(a, reg):
    """Один рукав (развёртка — как у левого). В столбце u (поперёк канта, по v) — отрезки основных цветов; кант — самый
    частый порядок внутренних отрезков (не первого и не последнего), фон над ним и под ним — соседние с кантом отрезки
    этого столбца (у WSH сверху красное, снизу — белая панель на рукаве и красное на туловище). Края канта — многочлен
    по u с отсевом, у концов окна — переход к своему краю. Перекраска у кривых: внутри канта — его цвета, снаружи —
    только цвет канта и его смесь (в соседний фон); прочее — как есть. -> (новый цвет, отчёт)."""
    S = a.shape[0]
    pal = _slv_palette(a, reg)
    if len(pal) < 2:
        return a, "один цвет — без изменений"
    dist = np.stack([np.abs(a - p).max(-1) for p in pal], -1)
    lab, dm = dist.argmin(-1), dist.min(-1)
    for i in range(len(pal)):                            # смесь двух цветов (сглаженный край) — тоже «свой» цвет
        for j in range(i + 1, len(pal)):
            e = pal[j] - pal[i]
            t = np.clip(((a - pal[i]) * e).sum(-1) / max((e * e).sum(), 1e-6), 0, 1)
            dm = np.minimum(dm, np.abs(a - (pal[i] + t[..., None] * e)).max(-1))
    ok = reg & (dm < SLV_FIT_MIX)
    pure = dist.min(-1) < SLV_FIT_MIX                    # цвет палитры, не смесь (piping_mix)
    cols = np.nonzero(reg.any(0))[0]                     # столбец u — поперёк канта (по v)
    data, seqs = {}, {}
    for c in cols:
        rows = np.nonzero(reg[:, c])[0]
        y0, y1 = rows.min(), rows.max() + 1
        if not ok[y0:y1, c].all():
            continue                                     # чужой цвет (нашивка) — не в замер
        rr = _slv_runs(lab[y0:y1, c])
        if len(rr) < 3:
            continue
        data[c] = (y0, rr)
        key = tuple(q[0] for q in rr[1:-1])
        seqs[key] = seqs.get(key, 0) + 1
    if not seqs:
        return a, "канта нет"
    pat = max(seqs, key=seqs.get)
    L = len(pat)
    use = {}                                             # столбец → (y0, отрезки, индекс первого отрезка канта)
    for c, (y0, rr) in data.items():
        labs = [q[0] for q in rr]
        hits = [i for i in range(1, len(rr) - L) if tuple(labs[i:i + L]) == pat]
        if len(hits) == 1:
            use[c] = (y0, rr, hits[0])
    if len(use) < PIPING_MIN_ROWS:
        return a, f"кант {pat}: столбцов {len(use)} — мало"
    cs = np.array(sorted(use), float)
    nb = L + 1                                           # края: начало канта, стыки его цветов, конец
    obs = np.array([[use[c][0] + use[c][1][use[c][2] + k - 1][2] for k in range(nb)] for c in sorted(use)], float)
    fits, rep = [], []
    for k in range(nb):
        if k == 0:
            cf, keep = _slv_robust(cs / S, obs[:, 0], SLV_FIT_DEG)
            f = (lambda cf: lambda t: np.polyval(cf, t))(cf)
        else:
            prev = fits[k - 1]
            cf, keep = _slv_robust(cs / S, obs[:, k] - prev(cs / S), 2)
            f = (lambda cf, prev: lambda t: prev(t) + np.polyval(cf, t))(cf, prev)
        fits.append(f)
        rep.append(f"край {k}: выбросов {int((~keep).sum())} из {len(cs)}, до {np.abs(obs[:, k] - f(cs / S)).max():.0f} px")
    pipe = np.zeros(len(pal), bool)
    pipe[list(pat)] = True
    c0, c1 = cs.min(), cs.max()
    out, n = a.copy(), 0
    for c in cols:
        if c < c0 or c > c1:
            continue
        own = use.get(c)
        w = float(np.clip(min(c - c0, c1 - c) / max(PIPING_RAMP, 1), 0, 1)) if own is not None else 1.0
        bs = [float(f((c + 0.5) / S)) for f in fits]
        if own is not None:                              # у концов окна — к своему краю
            y0, rr, i0 = own
            mine = [y0 + rr[i0 + k - 1][2] for k in range(nb)]
            bs = [w * b + (1 - w) * m_ for b, m_ in zip(bs, mine)]
        rows_ = np.nonzero(reg[:, c])[0]
        lr = lab[rows_, c]                               # фон по обе стороны канта — ближайший к нему не крайний цвет
        up = rows_[ok[rows_, c] & (lr != pat[0]) & (rows_ + 0.5 < bs[0] - 1) & (rows_ + 0.5 > bs[0] - PIPING_NEAR - 4)]
        dn = rows_[ok[rows_, c] & (lr != pat[-1]) & (rows_ + 0.5 > bs[-1] + 1) & (rows_ + 0.5 < bs[-1] + PIPING_NEAR + 4)]
        if not len(up) or not len(dn):
            continue
        if PIPING_MIX:                                   # тексель смеси у края — не фон (WSH дом, 23.10)
            top, bot = pal[_piping_bg(up[::-1], c, lab, pure)], pal[_piping_bg(dn, c, lab, pure)]
        else:
            top, bot = pal[lab[up.max(), c]], pal[lab[dn.min(), c]]
        seg_col = [top] + [pal[p] for p in pat] + [bot]
        rows = np.nonzero(reg[:, c])[0]
        y = rows + 0.5
        near = ok[rows, c] & (np.min([np.abs(y - b) for b in bs], 0) < PIPING_NEAR)
        for i in np.nonzero(near)[0]:
            r = rows[i]
            seg, frac = 0, None
            for k, b in enumerate(bs):
                if y[i] - 0.5 >= b:
                    seg = k + 1
                elif y[i] + 0.5 > b:
                    frac = (k, b - (y[i] - 0.5))
            inside = 0 < seg <= L or frac is not None
            if not inside:                               # снаружи канта — только его цвет и смесь с ним
                bg = seg_col[seg]
                cur = a[r, c]
                stray = pipe[lab[r, c]]
                if not stray:
                    for p in pat:
                        e = pal[p] - bg
                        tt = float(np.clip(((cur - bg) * e).sum() / max((e * e).sum(), 1e-6), 0, 1))
                        if tt > 0.15 and np.abs(cur - (bg + tt * e)).max() < SLV_FIT_MIX:
                            stray = True
                            break
                if not stray:
                    continue
                col = bg
            else:
                col = seg_col[seg] if frac is None else frac[1] * seg_col[frac[0]] + (1 - frac[1]) * seg_col[frac[0] + 1]
                if frac is not None and frac[0] in (0, L):  # пограничный тексель с фоном: фон чужой — как есть
                    bgk = 0 if frac[0] == 0 else L + 1
                    if not pipe[lab[r, c]] and np.abs(a[r, c] - seg_col[bgk]).max() > SLV_FIT_MIX and not (
                            PIPING_MIX and _piping_mix(a[r, c], seg_col[bgk], seg_col[1] if bgk == 0 else seg_col[L])):
                        continue
            if np.abs(col - a[r, c]).max() > 3:
                out[r, c] = col
                n += 1
    return out, f"цвета {np.round(pal).astype(int).tolist()}, кант {pat}; " + "; ".join(rep) + f"; перекрашено {n}"


def piping_fit(png, mesh, box):
    """Профиль piping_fit: кант вдоль руки у шва проймы (CBJ, WSH) — гладкими кривыми. На развёртке Edge кант там идёт
    вдоль u (по руке), поперёк шва проймы, а перенос ближайшей точкой (реглан Edge, втачной рукав NHL 24) и armhole_clean
    (цвет у шва — со строки дальше от шва) дают его краю ступеньки по 3–6 текселей — на свитере «лесенка» вдоль переда
    плеча. В окне box (u0, v0, u1, v1 — как у левого рукава, правый — зеркально) в каждом столбце u — отрезки основных
    цветов по v: кант — внутренние (самый частый их порядок), фон над и под ним — свой у столбца (панель рукава, ткань).
    Края — многочлен по u с отсевом (как sleeve_stripes_fit), у концов окна — переход к своему краю (PIPING_RAMP).
    Перекраска — только у кривых и только «своих» цветов. -> отчёт по рукавам."""
    from PIL import Image
    a = np.asarray(Image.open(png).convert("RGB")).astype(np.float64)
    S = a.shape[0]
    tid, bar = kit3d.raster_uv(mesh, S)
    occ = tid >= 0
    ys, xs = np.nonzero(occ)
    X = np.zeros((S, S))
    X[ys, xs] = (bar[ys, xs] * mesh["pos"][mesh["tri"][tid[ys, xs]]][:, :, 0]).sum(1)
    cc = (np.arange(S) + 0.5) / S
    u0, v0, u1, v1 = (float(x) for x in box)
    win = ((cc[:, None] >= v0) & (cc[:, None] <= v1)) & ((cc[None, :] >= u0) & (cc[None, :] <= u1))
    out, rep = a.copy(), []
    for side in (0, 1):
        A = a if side == 0 else a[:, ::-1]
        side_m = (occ & (X < 0)) if side == 0 else (occ & (X > 0))[:, ::-1]
        reg = win & side_m
        res, r_ = _piping_side(A, reg)
        if side == 0:
            out[reg] = res[reg]
        else:
            out[:, ::-1][reg] = res[reg]
        rep.append(("левый: " if side == 0 else "правый: ") + r_)
    Image.fromarray(np.clip(np.round(out), 0, 255).astype(np.uint8)).save(png)
    return rep


CHEST_BANDS = None                 # профиль chest_bands (23.10, агент review-d, NYR выезд): [x0, x1, y0, y1] (м: |x| и высота)
#                                    или { форма = [...] } — полосы через грудь у ворота прямыми, по источнику (chest_bands_fit)
CHEST_BANDS_KITS = None
CHEST_SRC_X = (0.11, 0.22)         # м по |x|: замер полос источника — прямой участок груди (ближе к середине — лацканы)
CHEST_BIN = 0.001                  # м: шаг по высоте при разборе столбца источника на отрезки
CHEST_MIN_RUN = 0.003              # м: отрезок цвета короче — к соседу (сглаженный край, строчка)
CHEST_NEAR = 0.025                 # м от края полос: перекраска только ближе (у NYR «глазок» — до 2,1 см над полосами)
CHEST_LAPEL_D = 0.037              # м от сгиба ворота: ближе — лацкан и кромка (NYR: красный лацкан до 3,6 см), не трогаются
CHEST_LAPEL_D_DEFAULT = CHEST_LAPEL_D   # профиль chest_bands_lapel: м (CBJ 0,034 — ворот без лацканов, до обода) или "ring"
#                                    — до края лацкана (шов обода, ring_field) + CHEST_RING_PAD: NYR, полосы до самого лацкана
CHEST_RING_PAD = -0.5               # текселя за краем лацкана (chest_bands_lapel = "ring"): −0,5 — переход полосы и лацкана
#                                    совпадает с мягким краем LapelPaint (иначе между ними — светлый шов в тексель: смесь с
#                                    прежним переносом)
CHEST_NZ = 0.1                     # нормаль вперёд больше — перед (и верх плеча у ворота: «глазок» NYR — 0,5; источник — тоже)
CHEST_SPECK_PX = 12                # текселей 1024²: точка не больше — цветом вокруг (концы лацканов NYR: 9 текселей смеси у правого;
#                                    люверсы — от 27, не трогаются)
CHEST_SPECK_RING = 0.9             # доля кольца вокруг точки одного цвета — тогда точка им
CHEST_SPECK_TOL = 25               # «тот же цвет» фона — ближе (max по каналам)
CHEST_SPECK_DY = 0.02              # м ниже окна — тоже (под концами лацканов)
CHEST_SPECK_D = 0.012              # м от края ворота: ближе — кромка, не трогается
CHEST_END_DX = 0.008               # м от начала окна (x0) к середине: хвосты полос у их конца — фоном (WSH, 23.10)
CHEST_END_MIN = 0.006              # м: крайний отрезок столбца источника короче — не фон (кромка ворота у верха окна)


def chest_bands_source(code, kit, box):
    """Полосы через грудь у источника (chest_bands): на сетке NHL 24 спереди (наружная оболочка, нормаль вперёд), в
    столбцах |x| из CHEST_SRC_X шагом 1 см — отрезки цвета по высоте (окно box по высоте), самый частый порядок; края —
    прямые по |x| (наименьшие квадраты). Перенос туловища — по высоте (TORSO_DELTA у формы без кокетки нет): высоты
    источника годятся и для Edge. -> {"colors": [[R, G, B]…] снизу вверх (фон, полосы, фон), "fits": [(k, b)…] — край
    i: y = k·θ + b, θ — угол от середины переда, град} или None."""
    from scipy.sparse.csgraph import connected_components
    n24 = kit3d.load_nhl24()
    src = Hy.clean_color(code, kit)
    tid, bar = kit3d.raster_uv(n24, src.shape[0])
    ys, xs = np.nonzero(tid >= 0)
    w_ = Hy.Welded(n24)
    _, comp = connected_components(w_.A, directed=False)
    shell = comp[w_.g[n24["tri"][tid[ys, xs], 0]]] == np.bincount(comp).argmax()
    ys, xs = ys[shell], xs[shell]
    T = n24["tri"][tid[ys, xs]]
    b = bar[ys, xs]
    P = (b[:, :, None] * n24["pos"][T]).sum(1)
    P[:, 0] += 0.0035                                    # середина горловины NHL 24 — на оси (CoordMap.x_fix)
    N = kit3d._unit((b[:, :, None] * n24["nrm"][T]).sum(1))
    c = src[ys, xs, :3].astype(np.float64)
    bnd = w_.boundary()                                  # край ворота NHL 24 (как CoordMap): ближе CHEST_LAPEL_D — кромка
    main = np.bincount(comp).argmax()                    # и лацканы, не полосы
    ring_poly = Hy.ring_polyline(w_, w_.neck(bnd[comp[bnd] == main]))
    Dn = Hy.ring_dist(P, ring_poly)
    x0, x1, y0, y1 = (float(v) for v in box)
    sel = (P[:, 2] > 0) & (N[:, 2] > CHEST_NZ) & (P[:, 1] >= y0) & (P[:, 1] <= y1) & \
        (Dn > (CHEST_LAPEL_D if not isinstance(CHEST_LAPEL_D, str) else CHEST_LAPEL_D_DEFAULT))
    xa = np.abs(P[:, 0])
    pal = _slv_palette(c, sel & (xa >= CHEST_SRC_X[0]) & (xa <= CHEST_SRC_X[1]))
    if len(pal) < 2:
        return None
    lab = np.stack([np.abs(c - p).max(-1) for p in pal], -1).argmin(-1)
    nmin = max(1, int(round(CHEST_MIN_RUN / CHEST_BIN)))
    th = np.degrees(np.arctan2(np.abs(P[:, 0] - 0.0035), P[:, 2]))   # угол θ — как у переноса туловища (без сдвига x)
    tsel = sel & (xa >= x0) & (xa <= x1)
    t0, t1 = np.percentile(th[tsel], 1), np.percentile(th[tsel], 99)
    cols, seqs = [], {}
    for xc in np.arange(t0, t1 + 1e-9, 2.0):
        for sg in (-1.0, 1.0):
            m = sel & (np.abs(th - xc) < 1.0) & (np.sign(P[:, 0]) == sg)
            if m.sum() < 30:
                continue
            yb = np.floor((P[m, 1] - y0) / CHEST_BIN).astype(int)
            n = int(round((y1 - y0) / CHEST_BIN)) + 1
            col = np.full(n, -1)
            for k in np.unique(yb):
                if 0 <= k < n:
                    col[k] = np.bincount(lab[m][yb == k]).argmax()
            for i in range(1, n):
                if col[i] < 0:
                    col[i] = col[i - 1]
            if col[0] < 0:
                continue
            rr = _slv_runs(col)
            while True:
                short = [j for j, r in enumerate(rr) if r[2] - r[1] < nmin and 0 < j < len(rr) - 1]
                if not short:
                    break
                j = short[0]
                if rr[j - 1][0] == rr[j + 1][0]:
                    rr[j - 1:j + 2] = [[rr[j - 1][0], rr[j - 1][1], rr[j + 1][2]]]
                else:
                    rr[j - 1:j + 1] = [[rr[j - 1][0], rr[j - 1][1], rr[j][2]]]
            if len(rr) > 2 and (rr[-1][2] - rr[-1][1]) * CHEST_BIN < CHEST_END_MIN:
                rr = rr[:-1]                             # у верха окна — край ворота (кромка): не полоса
            if len(rr) > 2 and (rr[0][2] - rr[0][1]) * CHEST_BIN < CHEST_END_MIN:
                rr = rr[1:]
            key = tuple(q[0] for q in rr)
            cols.append((xc, key, [y0 + q[2] * CHEST_BIN for q in rr[:-1]]))
            seqs[key] = seqs.get(key, 0) + 1
    if not seqs:
        return None
    pat = max(seqs, key=seqs.get)
    xe = np.array([q[0] for q in cols if q[1] == pat])
    he = np.array([q[2] for q in cols if q[1] == pat])
    if len(xe) < 4 or len(pat) < 3:
        return None
    tq = np.unique(xe)                                   # края по углу: медиана сторон, сглажено медианой по 3
    hq = np.array([np.median(he[xe == t], 0) for t in tq])
    if len(tq) >= 3:
        hq = np.stack([np.median(np.stack([np.r_[hq[:1, k], hq[:-1, k]], hq[:, k], np.r_[hq[1:, k], hq[-1:, k]]]), 0)
                       for k in range(hq.shape[1])], 1)
    return {"colors": [[round(float(v), 1) for v in pal[p]] for p in pat], "theta": tq.tolist(), "h": hq.tolist(),
            "n": int(len(xe))}


def chest_bands_fit(png, mesh, box, code, kit):
    """Профиль chest_bands (23.10, агент review-d, NYR выезд): полосы через грудь у ворота — прямыми, по источнику. У NHL 27
    NYR выезда под синей кокеткой — белая, красная, белая и синяя полосы, прямые по высоте до лацкана; переносом они у ворота
    гнулись петлями (на наклонном верхе груди и плеча — смесь переноса туловища по высоте и проекции сверху): кусок верхних
    белой и красной уходил вверх, в кокетку («глазок» на 1,68 м), у лацкана полосы опускались клином. Здесь края полос —
    замер источника (chest_bands_source: прямые по |x|), в окне box ([|x| от, до, высота от, до], м; перед: z > 0, нормаль
    вперёд > CHEST_NZ; дальше CHEST_LAPEL_D от сгиба ворота — лацкан, кромка и вставка не трогаются) тексели цветов полос и
    фона ближе CHEST_NEAR к краям — по краям (у края — долей текселя). Цвета — свои, ближайшие к цветам источника; нашивки
    (чужой цвет) не трогаются. -> отчёт."""
    from PIL import Image
    s_ = chest_bands_source(code, kit, box)
    if s_ is None:
        return ["полос у источника не нашлось — без изменений"]
    a = np.asarray(Image.open(png).convert("RGB")).astype(np.float64)
    G = relief_geometry(mesh, a.shape[0])
    P, N, m, D, ts = G["P"], G["N"], G["m"], G["D"], G["TS"]
    x0, x1, y0, y1 = (float(v) for v in box)
    ax = np.abs(P[..., 0])
    tx = np.maximum(ts, 1e-4)                            # у края окна у ворота (D) — переход в тексель, без ступенек
    if CHEST_LAPEL_D == "ring":                         # до края лацкана (шов обода; у середины — LAPEL_CENTER_D)
        R, _, _ = ring_field(G)
        dlim = np.where(np.isfinite(R), R, LAPEL_CENTER_D) + CHEST_RING_PAD * tx
    else:
        dlim = CHEST_LAPEL_D
    wD = np.clip((D - dlim) / tx + 0.5, 0, 1)
    win = m & (P[..., 2] > 0) & (N[..., 2] > CHEST_NZ) & (ax >= x0) & (ax <= x1) & (P[..., 1] >= y0) & \
        (P[..., 1] <= y1) & (wD > 0)
    pal = _slv_palette(a, win)
    if len(pal) < 2:
        return ["один цвет — без изменений"]
    dist = np.stack([np.abs(a - p).max(-1) for p in pal], -1)
    lab, dm = dist.argmin(-1), dist.min(-1)
    for i in range(len(pal)):                            # смесь двух цветов (сглаженный край) — тоже «свой» цвет
        for j in range(i + 1, len(pal)):
            e = pal[j] - pal[i]
            t = np.clip(((a - pal[i]) * e).sum(-1) / max((e * e).sum(), 1e-6), 0, 1)
            dm = np.minimum(dm, np.abs(a - (pal[i] + t[..., None] * e)).max(-1))
    seq = [int(np.abs(pal - np.asarray(cs)).max(-1).argmin()) for cs in s_["colors"]]   # свои цвета полос
    cols = pal[seq]
    ys, xs = np.nonzero(win & (dm < SLV_FIT_MIX) & np.isin(lab, seq))
    xx, yy = np.degrees(np.arctan2(ax[ys, xs], P[ys, xs, 2])), P[ys, xs, 1]   # угол θ, как у переноса туловища
    tq, hq = np.asarray(s_["theta"]), np.asarray(s_["h"])
    bs = np.stack([np.interp(xx, tq, hq[:, k]) for k in range(hq.shape[1])], 1)   # края снизу вверх в точке текселя
    near = np.abs(yy[:, None] - bs).min(1) < CHEST_NEAR
    ys, xs, yy, bs = ys[near], xs[near], yy[near], bs[near]
    h = np.maximum(ts[ys, xs], 1e-4)
    cov = np.clip((yy[:, None] - bs) / h[:, None] + 0.5, 0, 1)   # доля текселя выше края k
    out_c = cols[0][None, :] * (1 - cov[:, :1])
    nb = bs.shape[1]
    for k in range(nb):
        nxt = cov[:, k:k + 1] - (cov[:, k + 1:k + 2] if k + 1 < nb else 0)
        out_c = out_c + cols[k + 1][None, :] * nxt
    w_ = wD[ys, xs][:, None]
    out_c = a[ys, xs] * (1 - w_) + out_c * w_
    ch = np.abs(a[ys, xs] - out_c).max(-1) > 3
    out = a.copy()
    out[ys[ch], xs[ch]] = out_c[ch]
    # точки цвета полос у концов лацканов и под ними (1–4 текселя: хвост прежнего переноса вне окна) — цветом вокруг
    from scipy import ndimage as ndi
    zs = m & (P[..., 2] > 0) & (N[..., 2] > CHEST_NZ) & (ax <= x1) & (P[..., 1] >= y0 - CHEST_SPECK_DY) & \
        (P[..., 1] <= y1) & (D > CHEST_SPECK_D)
    n_sp, st = 0, np.ones((3, 3), bool)
    for col_ in np.unique(cols, axis=0):                 # фон-цвет: точки не его цвета, вокруг — почти только он
        same = np.abs(out - col_).max(-1) < CHEST_SPECK_TOL
        lb, n = ndi.label(zs & ~same, st)
        if not n:
            continue
        size = np.bincount(lb.ravel(), minlength=n + 1)
        small = size <= CHEST_SPECK_PX * (a.shape[0] / 1024.0) ** 2
        small[0] = False
        labc = np.where(small[lb], lb, 0)
        ring_lab = ndi.grey_dilation(labc, footprint=st)
        ring = (ring_lab > 0) & (labc == 0)
        tot = np.bincount(ring_lab[ring], minlength=n + 1)
        okr = np.bincount(ring_lab[ring & same & zs], minlength=n + 1)
        good = small & (tot > 0) & (okr >= CHEST_SPECK_RING * tot)
        sp = good[labc] & (labc > 0)
        out[sp] = col_
        n_sp += int(sp.sum())
    # хвост полос у их конца со стороны ворота (|x| от x0 − CHEST_END_DX до x0 — вне окна, прежний перенос): тексели ниже
    # нижнего края полос и выше верхнего (на полтекселя за краем) — цветом фона там (WSH, 23.10, пользователь: «артефакт, где
    # полоска по ключице втыкается в площадку для шильдика» — хвост синего в 6 текселей на 2–3 мм под концом правого канта,
    # |x| 4,1–4,4 см при окне от 4,5); сами полосы до края шаблона — как были
    tail = m & (P[..., 2] > 0) & (N[..., 2] > CHEST_NZ) & (ax < x0) & (ax >= x0 - CHEST_END_DX) & \
        (P[..., 1] >= y0) & (P[..., 1] <= y1) & (wD > 0)
    yt, xt = np.nonzero(tail)
    bt = np.stack([np.interp(np.degrees(np.arctan2(ax[yt, xt], P[yt, xt, 2])), tq, hq[:, k]) for k in range(hq.shape[1])], 1)
    yv, ht = P[yt, xt, 1], np.maximum(ts[yt, xt], 1e-4)
    n_end = 0
    for sel, col_ in ((yv < bt.min(1) - 0.5 * ht, cols[0]), (yv > bt.max(1) + 0.5 * ht, cols[-1])):
        diff = np.abs(out[yt[sel], xt[sel]] - col_).max(-1) > CHEST_SPECK_TOL
        out[yt[sel][diff], xt[sel][diff]] = col_
        n_end += int(diff.sum())
    Image.fromarray(np.clip(np.round(out), 0, 255).astype(np.uint8)).save(png)
    edges = ", ".join(f"{np.interp(60.0, tq, hq[:, k]):.3f}" for k in range(hq.shape[1]))
    return [f"полосы источника (снизу вверх) {s_['colors']}, θ {tq.min():.0f}…{tq.max():.0f}°, края на 60°: {edges} (столбцов {s_['n']}); "
            f"свои цвета {np.round(cols).astype(int).tolist()}; перекрашено {int(ch.sum())}, точек {n_sp}, у конца {n_end} текселей"]


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
    def s24_slope(e, sm):
        """Наклон s NHL 24 по s Edge у конца карты рукава (для продолжения за конец, SLEEVE_TOP24)."""
        k_ = e["s"] >= e["s"][-1] - SLV_EXTRAP_W
        slope = float(np.polyfit(e["s"][k_], sm[k_], 1)[0]) if k_.sum() >= 3 else 0.0
        if slope < 0.3:                                  # у конца карта сглажена и «упирается» — средний наклон
            slope = float((sm[-1] - sm[0]) / max(e["s"][-1] - e["s"][0], 1e-6))
        return slope

    def s24_of(self, ss, e, sm):
        """s Edge (рисунок) → s NHL 24; с SLEEVE_TOP24 за концом карты рукава — продолжение по наклону, иначе — упор."""
        out = np.interp(ss, e["s"], sm)
        if SLEEVE_TOP24 is not None:
            over = ss > e["s"][-1]
            out = np.where(over, sm[-1] + (ss - e["s"][-1]) * self.s24_slope(e, sm), out)
        return out

    def edge_of(self, s24, side=-1):
        """s NHL 24 → s Edge (обратное s24_of, с продолжением за конец карты рукава)."""
        d = self.sides[side]
        e, sm = d["e"], d["s24"]
        if s24 <= sm[-1]:
            return float(np.interp(s24, sm, e["s"]))
        return float(e["s"][-1] + (s24 - sm[-1]) / self.s24_slope(e, sm))

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

    def stripes(self, tex, side=-1):
        """Границы полос рукава NHL 24 (левый; правый — зеркально) — s NHL 24 и s Edge: профиль цвета по столбцам
        (медиана по кольцу через таблицу угла), смена цвета > 45 — граница (середина переходного столбца). side = 1 —
        по правому рукаву источника (sleeve_fill_side, SEA выезд 23.10: у NHL 27 рукава бывают несимметричны)."""
        nn = self.sides[side]["n"]
        grid = np.arange(-180.0, 180.0, SLV_PHI)
        sel = np.arange(0, len(grid), 10)
        S = tex.shape[0]
        prof, rings = [], []
        for j, s_ in enumerate(nn["s"]):
            v = nn["tab"][j, sel]
            cc = kit3d.sample_bilinear(tex, np.full(len(v), s_ if side < 0 else 1.0 - s_), v)[:, :3]
            prof.append(np.median(cc, 0))
            rings.append(cc)
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
                # граница полосы — смена цвета почти по всему кольцу (нашивка на части окружности — не полоса; 21.10,
                # BOS: у MIN, NJD, TBL, BOS у всех границ доля 1,00 — правило их не меняет)
                ring_frac = float((np.abs(rings[min(k, n - 1)] - rings[i]).max(1) > 45).mean())
                if ring_frac >= SLV_RING_FRAC:
                    out.append(0.5 * (nn["s"][i] + nn["s"][min(k, n - 1)]) if k > j else 0.5 * (nn["s"][i] + nn["s"][j]))
                i = k
            else:
                i = j
        b24 = np.array([b for b in out if SLV_U24_MIN + 0.01 < b < SLV_U24[1] - 0.01])
        e = self.sides[side]
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
            fill = SLV_FILL_S24 is not None and SLV_COMPRESS is not None
            ext = (SLV_FILL_EXT_TOP or SLV_FILL_EXT) if fill else 0.0
            k = (sE >= SLV_U[0]) & (sE <= SLV_U[1] + ext) & (tv > SLV_V[0]) & (tv < SLV_V[1]) & (P[:, 0] * sgn > SLV_X)
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
            s24 = self.s24_of(ss, e, d["s24"])
            if SLV_FILL_S24 is not None and SLV_COMPRESS is not None:   # над полосами места нет (BOS): выше колена — ткань
                fs = SLV_FILL_S24_R if (sgn > 0 and SLV_FILL_S24_R is not None) else SLV_FILL_S24   # своя рука (SEA)
                s24 = np.where(s > SLV_COMPRESS[0] * SLV_COMPRESS[1], fs, s24)   # над верхней границей
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
            w_ = Hy.smooth((SLV_U[1] - sE[k]) / SLV_BLEND)
            if fill:                                     # над полосами — ткань и у проймы (до SLV_FILL_EXT за концом)
                w_ = np.where(s > SLV_COMPRESS[0] * SLV_COMPRESS[1],
                              Hy.smooth((SLV_U[1] + ext - sE[k]) / SLV_FILL_BLEND), w_)
            wt[k] = w_
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
SHOULDER_SCALE = 0.9               # и на 10 % меньше (от центра): близко к соседним элементам (пользователь, 20.10)
SHIELD_SCALE = 0.88                # меньше (пользователь, 19.10: «слишком большой»); у форм NHL 24 на Edge — 0,8 (под щит EA)
SHIELD_OFFSET_CM = [0.41, 0.6, 0.0]  # x: середина горловины NHL 24 — на 0,35–0,41 см левее оси (как CoordMap.x_fix)
_SHIELD_DEFAULT = (list(SHIELD_OFFSET_CM), SHIELD_SCALE)   # профиль клуба: shield_offset_cm, shield_scale
RELIEF_CLEAR = [(0.468, 0.136, 0.532, 0.178, -0.05), (0.466, 0.386, 0.534, 0.401, -0.03)]   # u0, v0, u1, v1, сдвиг
#                                    источника по v: метка и черта над местом Reebok EA в чистом
#                                    рельефе T=4 на спине (под номером — прямоугольник, у EA-форм его нет)
# Надпись сзади у ворота — своя вместо Reebok (пользователь, 20.10: «в таком же стиле, но mgrhs»): шрифт —
# полужирный гротеск, как у Reebok EA (Arial Bold; x-высота 8,7 текселя 1024², базовая линия — 2,7 строки от верха
# рамки src_box, у развёртки текст повёрнут на 180°), рамка — src_box EA с запасом BRAND_PAD строк сверху и снизу
# (хвост g); цвет — как у Reebok (цвет adidas NHL 24), рельеф и блеск — по форме своих букв, сила рельефа —
# подбором по буквам Reebok EA (brand_relief_model). None — Reebok EA.
BRAND_TEXT = "mgrhs"
BRAND_FONT = r"C:\Windows\Fonts\arialbd.ttf"
BRAND_XH = 8.7
BRAND_BASE_ROW = 2.7
BRAND_PAD = 2
BRAND_SS = 16
BRAND_SM_UP = 4                    # блеск букв выше ткани (у EA: 20 при ткани 16)
BRAND_Y = None                     # профиль brand_y (м, 23.10, агент review-d, CBJ): центр надписи сзади на этой высоте —
#                                    у CBJ на 1,663 м (REEBOK_BACK_UV) — белая полоса под кокеткой (1,649–1,669), надпись
#                                    на ней; у NHL 27 логотип выше полос, в кокетке (~1,682). Нет — REEBOK_BACK_UV
# высота середины спины Edge → v развёртки (замер по сетке слота, x = 0, 23.10)
BRAND_Y_V = ((1.6169, 0.3911), (1.6381, 0.4028), (1.6571, 0.4146), (1.6632, 0.4185), (1.6754, 0.4263),
             (1.6808, 0.4302), (1.6845, 0.4341), (1.6882, 0.4380), (1.6955, 0.4438), (1.7001, 0.4478))


def brand_uv():
    """Центр надписи сзади (uv): REEBOK_BACK_UV или (профиль brand_y) — на высоте brand_y."""
    if BRAND_Y is None:
        return REEBOK_BACK_UV
    ys_, vs_ = zip(*BRAND_Y_V)
    return [REEBOK_BACK_UV[0], round(float(np.interp(BRAND_Y, ys_, vs_)), 4)]


REEBOK_BACK_UV = [0.5, 0.4183]  # 1,663 м — между 0,4205 (1,666: «чуть-чуть пониже») и 0,416 (1,66: «слишком
#                                    низко»), пользователь, 19.10; у EA — 0,4085 (1,648)
#                                        # у EA — 0,4085 (на 2,6 см ниже места логотипа adidas NHL 24, 1,674 м)


# Кокетка (цветной верх у светлых форм) — как у EA-формы Legacy того же клуба (пользователь, 19.10: «посмотри, как
# сделаны плечевые суставы и линии на них у Reebok-формы Legacy, и перенеси»): у EA кокетка на развёртке Edge —
# четырёхугольник с прямыми краями (бока — по плечевым суставам). Бока — с EA (прямые по краю её кокетки), верх
# (спина) и низ (грудь) — высоты NHL 24 (прямые на развёртке на высоте линии, перенесённой с NHL 24).
YOKE = {("MIN", "away"): {"from": "1_14_3"}}       # формы с кокеткой — из профиля клуба (use_club)
YOKE_KIND = "green"                # как узнавать кокетку по цвету (профиль: yoke_color)
YOKE_FLAT_X = 0.14                 # м от оси: дальше перед кокетки — ровной высоты
YOKE_BACK_FROM = "1_14_3"           # спина кокетки — по EA-форме (NHL 24 — 1,648 м: «зелёное кончается высоко»);
#                                    с профилями — EA-форма кокетки этой формы (YOKE[...]["from"])
YOKE_MIX = 0.0                     # 0 — край кокетки на высотах NHL 24, 1 — перед и спина на средней
YOKE_SHIFT = 0.0                   # м: сдвиг края кокетки (обоих) по высоте
YOKE_PAD = 0.05                    # UV: за краем многоугольника — зона перекраски (там — ткань двух цветов;
#                                    0,02 — у плеч оставались тёмные следы прежнего угла кокетки)
YOKE_LACE_X, YOKE_LACE_Y = 0.032, 1.615  # м: спереди у середины ниже 1,615 — шнурки (вставку выше рисует InsertPaint)
YOKE_COLLAR = 0.0                  # (было 0,03) край кокетки — до самой кромки (кромку рисует TrimPaint поверх)
YOKE_COLLAR_OLD = 0.03                 # м от края ворота — не трогать (кромка, подкладка, вставка)


CLUBS_TOML = os.path.join(os.path.dirname(os.path.abspath(__file__)), "edge_clubs.toml")


def club_profiles():
    import tomllib
    with open(CLUBS_TOML, "rb") as f:
        return tomllib.load(f)


def use_club(code):
    """Профиль клуба (edge_clubs.toml) → таблицы модуля: источник текстур (fb.kitsrc), кокетка, вставка, слот, гетры."""
    from . import kitsrc
    global YOKE, YOKE_KIND, INSERT_KITS, SLOT_KITS, LETTER_ZONES_FROM, SOCK_PARTS, BODY_KIND, COLLAR, YOKE_EA_KIND
    global YOKE_SIDE_BLEND, SHIELD_OFFSET_CM, SHIELD_SCALE, SLEEVE_ZONES_FROM, BASE_NM_DECALS, COLLAR_TRIM
    global SHIELD_GAP_MM, TRIM_WIDTH_FROM, FONT_NAME_SCALE, FONT_CAPTAIN_X, TRIM_MEASURE
    from . import hem
    from . import kit_hybrid
    prof = club_profiles().get(code)
    if prof is None:
        sys.exit(f"{code}: нет профиля клуба в {CLUBS_TOML}")
    kitsrc.use(prof.get("source", "nhl24"), prof.get("source_kits"))   # source_kits: метка → папка источника
    kit_hybrid.MERGE_PARTS = tuple(prof.get("merge_parts", ()))         # части одной нашивки (герб TBL) — одной
    BASE_NM_DECALS = prof.get("base_normal_decals")
    global BN_KEEP_LACE
    BN_KEEP_LACE = bool(prof.get("base_normal_keep_lace", False))   # шнуровка — рельеф источника (NYI, 23.10)
    global PLACKET_LIFT, LACE_ZONE, RELIEF_FLAT_UNDER
    global CREST_LEVEL
    CREST_LEVEL = list(prof.get("crest_level", []))                    # формы: герб — проекцией по высоте (MTL дом)
    global CREST_ROT
    CREST_ROT = {k: float(v) for k, v in prof.get("crest_rotate_deg", {}).items()}   # формы: доворот герба (MTL дом)
    global CREST_DROP
    CREST_DROP = {k: float(v) for k, v in prof.get("crest_drop_cm", {}).items()}   # формы: герб ниже полосы (MTL дом)
    RELIEF_FLAT_UNDER = list(prof.get("relief_flat_under", []))         # швы гладко под гербом и номерами (MTL, 23.10)
    if set(RELIEF_FLAT_UNDER) - {"crest", "numbers"}:
        sys.exit(f"[{code}] relief_flat_under = {RELIEF_FLAT_UNDER!r} — из \"crest\", \"numbers\"")
    PLACKET_LIFT = float(prof.get("placket_lift_cm", 0.0)) / 100     # планка под одну шнуровку (MTL, 23.10)
    LACE_ZONE = tuple(prof.get("lace_zone", LACE_ZONE_DEFAULT))       # зона рельефа шнуровки источника (MTL, 23.10)
    YOKE = {(code, k): {"from": v} for k, v in prof.get("yoke", {}).items()}
    YOKE_KIND = prof.get("yoke_color", "green")
    BODY_KIND = prof.get("body_color", "light")
    COLLAR = prof.get("collar", "lace")
    COLLAR_TRIM = prof.get("collar_trim", "auto")
    global COLLAR_TRIM_KITS                              # и таблицей по форме (22.10, агент yokes, STL выезд: кромка цвета
    COLLAR_TRIM_KITS = dict(COLLAR_TRIM) if isinstance(COLLAR_TRIM, dict) else None   # кокетки — «half», дома — auto)
    if COLLAR_TRIM_KITS:
        COLLAR_TRIM = "auto"
    TRIM_MEASURE = prof.get("trim_measure", "percentile")
    global SLV_BLEND
    SLV_BLEND = float(prof.get("sleeve_blend", SLV_BLEND_DEFAULT))   # переход карты рукава к ближайшей точке (WSH)
    global TOPP_NY
    TOPP_NY = tuple(map(float, prof.get("top_proj", TOPP_NY_DEFAULT)))   # проекция сверху — с какого наклона (NYR выезд)
    global TRIM_STEP_FROM
    TRIM_STEP_FROM = float(prof.get("trim_step_from", 0.0))   # вставка цвета кромки у середины — не кромка (NYI дом)
    global TRIM_CLEAR_MODE
    TRIM_CLEAR_MODE = prof.get("trim_clear")             # "angle": зачистка за кромкой — цветом источника по углу (CHI)
    if TRIM_CLEAR_MODE not in (None, "angle"):
        sys.exit(f"[{code}] trim_clear = {TRIM_CLEAR_MODE!r} — только \"angle\"")
    global COLLAR_BAND
    COLLAR_BAND = dict(prof.get("collar_band", {}))       # двухцветный ворот: форма → "full" (UTA выезд) | "back" (TOR)
    if any(v not in ("full", "back", "frame") for v in COLLAR_BAND.values()):
        sys.exit(f"[{code}] collar_band = {COLLAR_BAND!r} — {{ форма = \"full\" | \"back\" | \"frame\" }}")
    kit_hybrid.MERGE_NEAR = float(prof.get("merge_near", 0.0))   # буквы надписи-герба — одной нашивкой (UTA выезд)
    FONT_NAME_SCALE = prof.get("font_name_scale", 1.0)   # число или [ширина, высота] (LAK 22.10: мельче и плотнее)
    FONT_NAME_SCALE = float(FONT_NAME_SCALE) if np.isscalar(FONT_NAME_SCALE) else tuple(map(float, FONT_NAME_SCALE))
    from . import kit_fix                                # герб не на букву: свои поля [crest_fit] (gap_min …) клуба
    kit_fix.CREST_FIT_OVERRIDE = dict(prof.get("crest_fit", {}))
    global CREST_SIZE_CM
    CREST_SIZE_CM = prof.get("crest_size_cm")
    FONT_CAPTAIN_X = float(prof.get("font_captain_x", 1.0))
    global FONT_NAME_ANCHOR, NAME_ZONE_SCALE, NAME_ZONE_LIFT, FONT_NAME_FIT
    FONT_NAME_FIT = prof.get("font_name_fit")
    global FONT_PLATE
    FONT_PLATE = bool(prof.get("font_plate", False))     # фамилия на подложке (PHI): атлас букв — как у источника
    if FONT_NAME_FIT not in (None, "auto", "measured"):  # measured — auto и проверка по готовому атласу (SJS 22.10)
        sys.exit(f"[{code}] font_name_fit = {FONT_NAME_FIT!r} — только \"auto\" или \"measured\"")
    if FONT_NAME_FIT and ("font_name_scale" in prof or "name_zone_scale" in prof):
        sys.exit(f"[{code}] font_name_fit = \"auto\" считает font_name_scale и name_zone_scale сам — уберите их из профиля")
    FONT_NAME_ANCHOR = prof.get("font_name_anchor", "center")
    NAME_ZONE_SCALE = float(prof.get("name_zone_scale", 1.0))
    NAME_ZONE_LIFT = float(prof.get("name_zone_lift_cm", 0.0))
    # высота зоны низа «от края» (fb.hem.HEM_H): у NHL 27 BOS / TBL полосы низа — до 13–14 см, а зона — 9 см (переход
    # 6–9 см): белая полоса BOS попадала в переход и раздувалась посередине (пользователь, 21.10). Профиль hem_h — выше
    # полос, генератор (kitport profile) ставит по замеру; нет поля — как раньше
    hem.HEM_H = float(prof.get("hem_h", HEM_H_DEFAULT))
    global HEM_SHIFT
    HEM_SHIFT = float(prof.get("hem_shift_cm", 0.0)) / 100.0
    TRIM_WIDTH_FROM = dict(prof.get("trim_width_from", {}))    # кромка цвета ткани — ширина по другой форме
    YOKE_EA_KIND = prof.get("yoke_shape_color")
    YOKE_SIDE_BLEND = prof.get("yoke_side_blend")
    global BRAND_WIN
    BRAND_WIN = float(prof["brand_win"]) if "brand_win" in prof else None   # окно цвета логотипа сзади (BUF выезд)
    global SLEEVE_TOP24, SLEEVE_TOP24_KITS
    _t = prof.get("sleeve_top24")
    SLEEVE_TOP24_KITS = dict(_t) if isinstance(_t, dict) else None
    SLEEVE_TOP24 = None if (_t is None or SLEEVE_TOP24_KITS is not None) else float(_t)
    global SLEEVE_FILL
    global SLEEVE_STRIPES, SLEEVE_STRIPES_KITS
    _ss = prof.get("sleeve_stripes")                     # "fit": края полос рукава — гладкие кривые (OTT 22.10); "lines" —
    #                                                      ломаные (ANA 26.10)
    SLEEVE_STRIPES_KITS = dict(_ss) if isinstance(_ss, dict) else None   # или по формам (STL выезд, 23.10)
    SLEEVE_STRIPES = None if isinstance(_ss, dict) else _ss
    for _v in [SLEEVE_STRIPES] + list((SLEEVE_STRIPES_KITS or {}).values()):
        if _v not in (None, "fit", "lines"):
            sys.exit(f"[{code}] sleeve_stripes = {_v!r} — только \"fit\" или \"lines\" (или {{ форма = \"fit\" }})")
    global PIPING_FIT, PIPING_FIT_KITS, ARMHOLE_AA, YOKE_MIX_KEEP, BRAND_Y, PIPING_MIX
    _pf = prof.get("piping_fit")                         # кант вдоль руки у шва проймы — гладко (23.10, review-d: CBJ, WSH)
    PIPING_FIT_KITS = dict(_pf) if isinstance(_pf, dict) else None
    PIPING_FIT = None if (_pf is None or PIPING_FIT_KITS is not None) else piping_boxes(_pf)
    for _b in (PIPING_FIT or []) + [b for v in (PIPING_FIT_KITS or {}).values() for b in piping_boxes(v)]:
        if len(_b) != 4:
            sys.exit(f"[{code}] piping_fit = {_pf!r} — [u0, v0, u1, v1], список окон или {{ форма = [u0, v0, u1, v1] }}")
    ARMHOLE_AA = bool(prof.get("armhole_aa", False))     # шов проймы — со сглаживанием (23.10, review-d: WSH)
    PIPING_MIX = bool(prof.get("piping_mix", False))     # смесь у края канта — не «чужое» (23.10, review-e: WSH)
    global TORSO_SHIFT, TORSO_SHIFT_KITS
    _ts = prof.get("torso_shift")                        # полоса через туловище ниже (23.10, пользователь: MTL дом)
    TORSO_SHIFT_KITS = dict(_ts) if isinstance(_ts, dict) else None
    TORSO_SHIFT = None if (_ts is None or TORSO_SHIFT_KITS is not None) else [float(x) for x in _ts]
    for _b in ([TORSO_SHIFT] if TORSO_SHIFT else []) + list((TORSO_SHIFT_KITS or {}).values()):
        _yy = np.arange(0.9, 1.8, 0.001)
        if (len(_b) not in (5, 7) or not (_b[1] < _b[2] <= _b[3] < _b[4])
                or not (np.diff(_yy + torso_shift_dy(_yy, _b)) > 0).all()):
            sys.exit(f"[{code}] torso_shift = {_ts!r} — [см, y0, y1, y2, y3] или [см, y0, y1, y2, y3, k, yc] (y0 < y1 ≤ y2 "
                     "< y3; спад короче 1,5 × сдвига — рисунок у спада повторяется) или {{ форма = [...] }}")
    global CHEST_BANDS, CHEST_BANDS_KITS
    _cb = prof.get("chest_bands")                        # полосы через грудь у ворота — по источнику (23.10, NYR выезд)
    CHEST_BANDS_KITS = dict(_cb) if isinstance(_cb, dict) else None
    CHEST_BANDS = None if (_cb is None or CHEST_BANDS_KITS is not None) else [float(x) for x in _cb]
    for _b in ([CHEST_BANDS] if CHEST_BANDS else []) + list((CHEST_BANDS_KITS or {}).values()):
        if len(_b) != 4:
            sys.exit(f"[{code}] chest_bands = {_cb!r} — [|x| от, до, высота от, до] или {{ форма = [...] }}")
    global CHEST_LAPEL_D                                 # окно у ворота: дальше стольких м от края (CBJ — 0,034: до обода)
    _cl = prof.get("chest_bands_lapel", CHEST_LAPEL_D_DEFAULT)   # "ring" — до края лацкана (NYR)
    CHEST_LAPEL_D = _cl if _cl == "ring" else float(_cl)
    from . import pant_decals                            # нашивки шорт (23.10, review-d: WSH — три звезды, WPG — пояс)
    pant_decals.MERGE_PX = int(prof.get("pant_merge_px", 0))
    pant_decals.Y_MAX = (float(prof["pant_decal_ymax"]) if "pant_decal_ymax" in prof
                         else pant_decals.Y_MAX_DEFAULT)   # 24.10: и без поля — пояс под свитером не нашивка (DAL)
    pant_decals.HEM_H = float(prof["pant_hem"]) if "pant_hem" in prof else None   # низ шорт от края (23.10, NYR)
    from . import pilot                                  # буквы фамилии без перекраски (23.10, агент fix-a, NYR дом)
    _nc = prof.get("name_contrast", True)
    if isinstance(_nc, dict):
        pilot.NAME_CONTRAST_OFF = {k for k, v in _nc.items() if v is False}
    elif _nc is False:
        pilot.NAME_CONTRAST_OFF = {"home", "away"}
    elif _nc is True:
        pilot.NAME_CONTRAST_OFF = set()
    else:
        sys.exit(f"[{code}] name_contrast = {_nc!r} — true | false | {{ форма = false }}")
    YOKE_MIX_KEEP = bool(prof.get("yoke_mix_keep", False))   # смесь у полос рукава — как перенеслась (23.10, WPG выезд)
    BRAND_Y = float(prof["brand_y"]) if "brand_y" in prof else None   # надпись сзади на этой высоте (23.10, CBJ)
    SLEEVE_FILL = prof.get("sleeve_fill")                # "below": ткань над полосами рукава — цвет под ними (MTL дом)
    if SLEEVE_FILL not in (None, "below"):
        sys.exit(f"[{code}] sleeve_fill = {SLEEVE_FILL!r} — только \"below\"")
    global SLEEVE_FILL_SIDE, SLEEVE_FILL_SIDE_KITS       # ткань над полосами — по своей руке (SEA выезд, 23.10)
    _fs = prof.get("sleeve_fill_side", False)
    SLEEVE_FILL_SIDE_KITS = {str(k_): bool(v_) for k_, v_ in _fs.items()} if isinstance(_fs, dict) else None
    SLEEVE_FILL_SIDE = False if SLEEVE_FILL_SIDE_KITS is not None else bool(_fs)
    global SLEEVE_MIRROR, SLEEVE_MIRROR_KITS             # правый рукав — зеркалом левого (SEA выезд, 23.10)
    _sm = prof.get("sleeve_mirror")
    SLEEVE_MIRROR_KITS = {str(k_): v_ for k_, v_ in _sm.items()} if isinstance(_sm, dict) else None
    SLEEVE_MIRROR = None if SLEEVE_MIRROR_KITS is not None else _sm
    for v_ in ([SLEEVE_MIRROR] if SLEEVE_MIRROR_KITS is None else list(SLEEVE_MIRROR_KITS.values())):
        if v_ not in (None, "left"):
            sys.exit(f"[{code}] sleeve_mirror = {v_!r} — только \"left\" (или {{ форма = \"left\" }})")
    global YOKE_RGB_DIST                                # кокетка [R, G, B]: насколько близко к цвету (22.10, агент plain, CAR дом:
    YOKE_RGB_DIST = float(prof.get("yoke_rgb_dist", 60.0))   # тёмно-серая (38, 49, 51) на чёрном (27, 26, 27) — Δ 33 < 60)
    global YOKE_CLEAN_DEPTH                              # красное YokePaint — не ниже края кокетки на столько (CAR дом)
    YOKE_CLEAN_DEPTH = float(prof["yoke_clean_depth"]) if "yoke_clean_depth" in prof else None
    global YOKE_STRIPE, YOKE_BACK
    YOKE_STRIPE = prof.get("yoke_stripe")                # "source": полоса под кокеткой — по источнику (BUF выезд, 22.10);
    #                                                      "bands": полосы у края кокетки (над ним и под ним, STL выезд)
    if YOKE_STRIPE not in (None, "source", "bands"):
        sys.exit(f"[{code}] yoke_stripe = {YOKE_STRIPE!r} — \"source\" или \"bands\"")
    YOKE_BACK = prof.get("yoke_back")                    # "source": край кокетки сзади — как у источника, не EA
    global YOKE_FRONT
    YOKE_FRONT = prof.get("yoke_front")                  # "flat": край спереди ровный и у середины (COL: вставка цвета ткани)
    if YOKE_FRONT not in (None, "flat", "source"):      # "source": у середины ровно, к руке — край источника (COL, 22.10)
        sys.exit(f"[{code}] yoke_front = {YOKE_FRONT!r} — \"flat\" или \"source\"")
    global YOKE_SLEEVE
    YOKE_SLEEVE = prof.get("yoke_sleeve")                # "keep": рукав цвета кокетки — не трогать (WPG выезд, 22.10)
    if YOKE_SLEEVE not in (None, "keep", "band"):       # "band": кокетка переходит в полосу по верху рукава (COL, PHI)
        sys.exit(f"[{code}] yoke_sleeve = {YOKE_SLEEVE!r} — \"keep\" или \"band\"")
    if YOKE_BACK not in (None, "source"):
        sys.exit(f"[{code}] yoke_back = {YOKE_BACK!r} — только \"source\"")
    global YOKE_BACK_FROM_KITS                           # край спины — с другой EA-формы, чем бока (23.10, fix-b, NSH выезд)
    _bf = prof.get("yoke_back_from")
    YOKE_BACK_FROM_KITS = None
    if _bf is not None:
        if not (isinstance(_bf, dict) and all(isinstance(v, list) and len(v) == 2 and isinstance(v[0], str)
                                              and (v[1] in ("green", "dark") or (isinstance(v[1], list) and len(v[1]) == 3))
                                              for v in _bf.values())):
            sys.exit(f"[{code}] yoke_back_from = {_bf!r} — {{ форма = [\"EA-форма\", цвет кокетки: green | dark | [R, G, B]] }}")
        YOKE_BACK_FROM_KITS = {k: (v[0], v[1]) for k, v in _bf.items()}
    global NOTCH_SEAM, NOTCH_SEAM_KITS                   # шов у нижнего края мыса V над тканью (23.10, fix-b, NSH выезд)
    _ns = prof.get("notch_seam")
    NOTCH_SEAM_KITS = dict(_ns) if isinstance(_ns, dict) else None
    NOTCH_SEAM = None if (_ns is None or NOTCH_SEAM_KITS is not None) else _ns
    if any(v not in ("edge", "yoke") for v in ([NOTCH_SEAM] if NOTCH_SEAM else []) + list((NOTCH_SEAM_KITS or {}).values())):
        sys.exit(f"[{code}] notch_seam = {_ns!r} — \"edge\" | \"yoke\" или {{ форма = \"edge\" }}")
    global YOKE_BAND_SEAM, YOKE_BAND_SKIP                # замер полосы рукава (yoke_sleeve = "band"; 23.10, review-d, WPG)
    YOKE_BAND_SEAM = float(prof.get("yoke_band_seam", YOKE_BAND_SEAM_DEFAULT))
    YOKE_BAND_SKIP = tuple(map(float, prof["yoke_band_skip"])) if "yoke_band_skip" in prof else None
    global YOKE_SPECKS                                   # точки чужого цвета в перекрашенной ткани (22.10, агент review-c, EDM)
    YOKE_SPECKS = bool(prof.get("yoke_specks", False))
    # цвет кокетки по форме — таблица { home = [R, G, B], away = [R, G, B] } (22.10, агент yokes: EDM, COL, PHI — кокетка
    # у обеих форм разного цвета: дома оранжевая на синем, в гостях синяя на белом; один цвет-среднее не узнавал ни ту,
    # ни другую, а у COL — и ткань). Значение формы ставит use_kit(kit) на время её сборки; число — как раньше
    global YOKE_KIND_KITS, YOKE_EA_KIND_KITS
    YOKE_KIND_KITS = dict(YOKE_KIND) if isinstance(YOKE_KIND, dict) else None
    YOKE_EA_KIND_KITS = dict(YOKE_EA_KIND) if isinstance(YOKE_EA_KIND, dict) else None
    for k_, v_ in (("yoke_color", YOKE_KIND), ("yoke_shape_color", YOKE_EA_KIND)):
        for vv_ in (v_.values() if isinstance(v_, dict) else (v_,)):
            if vv_ is not None and not (vv_ in ("green", "dark") or (isinstance(vv_, list) and len(vv_) == 3)):
                sys.exit(f"[{code}] {k_} = {v_!r} — green, dark, [R, G, B] или {{ форма = … }}")
    if YOKE_KIND_KITS:
        YOKE_KIND = next(iter(YOKE_KIND_KITS.values()))
    if YOKE_EA_KIND_KITS:
        YOKE_EA_KIND = next(iter(YOKE_EA_KIND_KITS.values()))
    SHIELD_OFFSET_CM = list(prof.get("shield_offset_cm", _SHIELD_DEFAULT[0]))
    SHIELD_SCALE = float(prof.get("shield_scale", _SHIELD_DEFAULT[1]))
    # щит по зазору под кромкой (21.10): shield_gap_mm, а без него — у ворота без шнуровки SHIELD_GAP_DEFAULT_MM; задан
    # shield_offset_cm (MIN, NJD, TBL) — сдвиг как раньше, байт в байт
    SHIELD_GAP_MM = None if "shield_offset_cm" in prof else \
        prof.get("shield_gap_mm", SHIELD_GAP_DEFAULT_MM if COLLAR == "plain" else None)
    INSERT_KITS = {(code, k) for k in prof.get("insert", [])}
    global INSERT_COLOR
    INSERT_COLOR = prof.get("insert_color")
    global INSERT_CLEAN
    INSERT_CLEAN = prof.get("insert_clean")              # "blend": прежний перенос вокруг вставки — и смесь (NYI, 22.10)
    if INSERT_CLEAN not in (None, "blend"):
        sys.exit(f"[{code}] insert_clean = {INSERT_CLEAN!r} — только \"blend\"")
    if INSERT_COLOR not in (None, "source"):
        sys.exit(f"[{code}] insert_color = {INSERT_COLOR!r} — только \"source\"")
    SLOT_KITS = {k: dict(v) for k, v in prof.get("slot", {}).items()}
    LETTER_ZONES_FROM = dict(prof.get("letter_zones_from", {}))
    SLEEVE_ZONES_FROM = prof.get("sleeve_zones_from", SLEEVE_ZONES_REF)
    global SLEEVE_ZONES_AT
    SLEEVE_ZONES_AT = prof.get("sleeve_zones_at")       # "shoulder": номера на плечах у ворота (FLA, 22.10)
    global SLEEVE_ZONE_SHIFT, SLEEVE_ZONE_SHIFT_KITS, SLEEVE_ZONE_SCALE
    _zs = prof.get("sleeve_zone_shift_cm")               # зоны номеров рукава — сдвиг (23.10: ANA, OTT, WPG)
    SLEEVE_ZONE_SHIFT_KITS = dict(_zs) if isinstance(_zs, dict) else None
    SLEEVE_ZONE_SHIFT = None if (_zs is None or SLEEVE_ZONE_SHIFT_KITS is not None) else tuple(map(float, _zs))
    SLEEVE_ZONE_SCALE = float(prof.get("sleeve_zone_scale", 1.0))
    global CHEST_ZONE_SCALE
    CHEST_ZONE_SCALE = float(prof.get("chest_zone_scale", 1.0))   # номер на груди мельче (23.10, BUF)
    global NUMBER_H
    NUMBER_H = float(prof["number_h_cm"]) / 100.0 if "number_h_cm" in prof else None   # номер на спине (23.10)
    global DIGIT_GAPS, DIGIT_ASPECTS                     # цифры номера: промежуток и ширина (24.10, по фото настоящих форм)
    _dg, _da = prof.get("digit_gap"), prof.get("digit_aspect")
    DIGIT_GAPS = dict(_dg) if isinstance(_dg, dict) else ({"*": float(_dg)} if _dg is not None else {})
    DIGIT_ASPECTS = dict(_da) if isinstance(_da, dict) else ({"*": _da} if _da is not None else {})
    for _k, _v in DIGIT_ASPECTS.items():
        if _v != "keep" and not isinstance(_v, (int, float)):
            sys.exit(f"[{code}] digit_aspect {_k} = {_v!r} — \"keep\" или число")
    global SLEEVE_ZONE_AT, SLEEVE_ZONE_Z
    SLEEVE_ZONE_AT = tuple(map(float, prof["sleeve_zone_at"])) if "sleeve_zone_at" in prof else None
    SLEEVE_ZONE_Z = float(prof.get("sleeve_zone_z_cm", 0.0)) / 100.0
    if SLEEVE_ZONES_AT not in (None, "shoulder"):
        sys.exit(f"[{code}] sleeve_zones_at = {SLEEVE_ZONES_AT!r} — только \"shoulder\"")
    global NAME_ZONES_FROM, ARMHOLE_SPLIT_ZONES
    NAME_ZONES_FROM = prof.get("name_zones_from")
    global LETTER_SHIFT_CM, COLLAR_PANEL, LETTERING, INSERT_HW
    INSERT_HW = INSERT_HW_NHL27 if prof.get("insert_color") == "source" else INSERT_HW_MIN
    if prof.get("insert_contour") not in (None, "nhl27"):
        sys.exit(f"[{code}] insert_contour = {prof.get('insert_contour')!r} — только \"nhl27\"")
    global INSERT_CONTOUR
    INSERT_CONTOUR = prof.get("insert_contour")
    if prof.get("insert_contour") == "nhl27":           # контур вставки NHL 27 с язычком до 1,591 (FLA, 23.10)
        INSERT_HW = INSERT_HW_NHL27_FULL
    global ISLAND_PAD_CM, ISLAND_PAD_CM_KITS
    _ip = prof.get("island_pad_cm", False)              # поле острова в jersey_cm (23.10, review-e: NYR выезд)
    ISLAND_PAD_CM_KITS = {k_ for k_, v_ in _ip.items() if v_} if isinstance(_ip, dict) else None
    ISLAND_PAD_CM = bool(_ip) if ISLAND_PAD_CM_KITS is None else False
    LETTERING = prof.get("lettering", "standard")
    global NAME_ARCH
    NAME_ARCH = bool(prof.get("name_arch", False))
    if LETTERING not in ("standard", "own"):
        sys.exit(f"[{code}] lettering = {LETTERING!r} — standard или own")
    COLLAR_PANEL = bool(prof.get("collar_panel", False))
    global COLLAR_LINING
    COLLAR_LINING = prof.get("collar_lining", "source")
    global COLLAR_LAPEL, YOKE_MESH, LAPEL_CLEAN
    YOKE_MESH = bool(prof.get("yoke_mesh", True))
    LAPEL_CLEAN = bool(prof.get("lapel_clean", False))  # true: перенос лацкана за краем LapelPaint — тканью (MTL, DAL)
    COLLAR_LAPEL = prof.get("collar_lapel")             # "source": лацканы цвета источника (MTL, DAL — белые, 22.10)
    global COLLAR_LAPEL_KITS                             # { форма = "source" } — лацканы только у этих форм (NYI, 22.10:
    COLLAR_LAPEL_KITS = None                             # дома кромка ступенькой без лацканов, в гостях синие лацканы);
    if isinstance(COLLAR_LAPEL, dict):                   # COLLAR_LAPEL ставит цикл форм cmd_kit
        COLLAR_LAPEL_KITS = dict(COLLAR_LAPEL)
        COLLAR_LAPEL = "source" if any(COLLAR_LAPEL_KITS.values()) else None
        if any(v != "source" for v in COLLAR_LAPEL_KITS.values()):
            sys.exit(f"[{code}] collar_lapel = {COLLAR_LAPEL_KITS!r} — \"source\" или {{ форма = \"source\" }}")
    if COLLAR_LAPEL not in (None, "source"):
        sys.exit(f"[{code}] collar_lapel = {COLLAR_LAPEL!r} — только \"source\"")
    if COLLAR_LAPEL and COLLAR != "lace":
        sys.exit(f"[{code}] collar_lapel — только у ворота со шнуровкой (collar = \"lace\": швы лацканов — обод MIN)")
    if COLLAR_PANEL and COLLAR != "lace":                # шаблон ворота: щит как у NHL 27 — размер и место по V
        SHIELD_SCALE, SHIELD_GAP_MM = SHIELD_PANEL_SCALE, "panel"
    LETTER_SHIFT_CM = tuple(map(float, prof["letter_zone_shift_cm"])) if "letter_zone_shift_cm" in prof else None
    global LETTER7_SHIFT_CM                             # второе место буквы — отдельно (23.10, NYR)
    LETTER7_SHIFT_CM = tuple(map(float, prof["letter_zone7_shift_cm"])) if "letter_zone7_shift_cm" in prof else None
    global LETTER_ZONE_SCALE, HELMET_LOGO_X             # буква капитана мельче (DET), наклейка шлема у́же (ANA) — 26.10
    LETTER_ZONE_SCALE = float(prof.get("letter_zone_scale", 1.0))
    HELMET_LOGO_X = float(prof.get("helmet_logo_x", 1.0))
    split = prof.get("armhole_split", "zones")
    # по форме — таблица { away = "full" } (22.10, агент plain, CAR: в гостях красные рукава на белом — по шву Edge, дома
    # тёмная кокетка с красной полосой заходит с плеч на руку — шов по всей пройме резал её вертикальной красной чертой);
    # формы вне таблицы — zones. Значение формы ставит use_kit(kit); строка — как раньше, у всех форм
    global ARMHOLE_SPLIT_KITS
    ARMHOLE_SPLIT_KITS = dict(split) if isinstance(split, dict) else None
    for v_ in (ARMHOLE_SPLIT_KITS.values() if ARMHOLE_SPLIT_KITS is not None else (split,)):
        if v_ not in ("zones", "full"):
            sys.exit(f"[{code}] armhole_split = {split!r} — zones, full или {{ форма = \"full\" }}")
    if ARMHOLE_SPLIT_KITS is not None:
        split = "zones"
    ARMHOLE_SPLIT_ZONES = ARMHOLE_SPLIT_FULL if split == "full" else ARMHOLE_ZONES
    for kit, spec in SLOT_KITS.items():                  # подпись в меню — «Home (NHL 27)»: форма и источник
        spec.setdefault("label", f"{'Home' if kit == 'home' else 'Away'} ({SOURCE_NAME()})")
    SOCK_PARTS = tuple((float(w), tuple(c)) for w, c in prof.get("sock_parts", SOCK_PARTS))
    return prof


YOKE_KIND_KITS = None              # профиль yoke_color таблицей по форме (use_club) — значение формы ставит use_kit
COLLAR_TRIM_KITS = None            # профиль collar_trim таблицей по форме — то же
SLEEVE_TOP24_KITS = None           # профиль sleeve_top24 таблицей по форме — значение формы ставит use_kit
ARMHOLE_SPLIT_KITS = None          # профиль armhole_split таблицей по форме (CAR, 22.10) — значение формы ставит use_kit
YOKE_EA_KIND_KITS = None           # то же для yoke_shape_color


def torso_shift_dy(y, ts=None):
    """Сдвиг рисунка туловища на высоте y (профиль torso_shift), м: точка берёт источник с y + сдвиг. С [k, yc] — и
    полоса выше в k раз вокруг yc (высота Edge после сдвига): источник с yc + сдвиг + (y − yc) / k."""
    ts = TORSO_SHIFT if ts is None else ts
    cm, y0, y1, y2, y3 = ts[:5]
    k, yc = (ts[5], ts[6]) if len(ts) == 7 else (1.0, 0.0)
    w = Hy.smooth((y - y0) / (y1 - y0)) * (1.0 - Hy.smooth((y - y2) / (y3 - y2)))
    return w * (cm / 100.0 + (y - yc) * (1.0 / k - 1.0))


def crest_level(placed, kit):
    """Герб — проекцией по высоте (профиль crest_level, формы): kit_hybrid.decal_post берёт смещение точки от центра
    герба по горизонтали и по высоте, без глубины вдоль наклонной нормали (MTL дом, 23.10: нормаль груди 9,5° вверх,
    торс у концов «C» на 2,7 см глубже — рисунок герба ниже полосы на ~4,5 мм, «отросток синего не стыкуется»)."""
    for pl in placed:
        if pl["name"] != "crest":
            continue
        if kit in CREST_LEVEL:
            pl["level"] = True
            print("  герб: проекция по высоте (crest_level)")
        if CREST_ROT.get(kit):
            pl["rot_deg"] = CREST_ROT[kit]
            print(f"  герб: повёрнут на {CREST_ROT[kit]}° (crest_rotate_deg)")


def torso_shift_crest(placed):
    """Герб (нашивка crest) ниже на сдвиг torso_shift: нашивки ставятся по 3D-точке центра (кадр _frame), не по
    развёртке — без этого полоса уходила бы из-под герба."""
    for pl in placed:
        if pl["name"] != "crest":
            continue
        cL, nL, pinv, R, sc, rad, u_c, v_c = pl["_frame"]
        cL = np.asarray(cL, np.float64).copy()
        cL[1] -= TORSO_SHIFT[0] / 100.0
        pl["_frame"] = (cL, nL, pinv, R, sc, rad, u_c, v_c)
        print(f"  герб: ниже на {TORSO_SHIFT[0]} см вместе с полосой (torso_shift), центр {cL[1]:.3f} м")


def crest_drop(placed, kit):
    """Герб ниже на CREST_DROP[kit] см (профиль crest_drop_cm): MTL дом — сверх torso_shift, под куски полос в нашивке;
    WSH — вместе с местами литеры (letter_zone_shift_cm), литера ниже канта у ключицы (23.10)."""
    drop = CREST_DROP.get(kit, 0.0)
    if not drop:
        return
    for pl in placed:
        if pl["name"] != "crest":
            continue
        cL, nL, pinv, R, sc, rad, u_c, v_c = pl["_frame"]
        cL = np.asarray(cL, np.float64).copy()
        cL[1] -= drop / 100.0
        pl["_frame"] = (cL, nL, pinv, R, sc, rad, u_c, v_c)
        print(f"  герб: ниже ещё на {drop} см (crest_drop_cm), центр {cL[1]:.3f} м")


def use_kit(kit):
    """Поля профиля, заданные по форме (yoke_color, yoke_shape_color, collar_trim таблицей { home = …, away = … }), — на время
    сборки формы kit (cmd_kit, kitport yoke). У профиля без таблиц ничего не меняет."""
    global YOKE_KIND, YOKE_EA_KIND, ARMHOLE_SPLIT_ZONES, COLLAR_TRIM
    if COLLAR_TRIM_KITS:                                 # collar_trim по формам (STL): вне таблицы — auto
        COLLAR_TRIM = COLLAR_TRIM_KITS.get(kit, "auto")
    global SLEEVE_TOP24
    if SLEEVE_TOP24_KITS is not None:                    # sleeve_top24 по формам: вне таблицы — нет
        SLEEVE_TOP24 = float(SLEEVE_TOP24_KITS[kit]) if kit in SLEEVE_TOP24_KITS else None
    global SLEEVE_FILL_SIDE
    if SLEEVE_FILL_SIDE_KITS is not None:                # sleeve_fill_side по формам (SEA): вне таблицы — нет
        SLEEVE_FILL_SIDE = SLEEVE_FILL_SIDE_KITS.get(kit, False)
    global SLEEVE_MIRROR
    if SLEEVE_MIRROR_KITS is not None:                   # sleeve_mirror по формам (SEA): вне таблицы — нет
        SLEEVE_MIRROR = SLEEVE_MIRROR_KITS.get(kit)
    if ARMHOLE_SPLIT_KITS is not None:                  # armhole_split по формам (CAR): вне таблицы — zones
        ARMHOLE_SPLIT_ZONES = ARMHOLE_SPLIT_FULL if ARMHOLE_SPLIT_KITS.get(kit, "zones") == "full" else ARMHOLE_ZONES
    global PIPING_FIT
    if PIPING_FIT_KITS is not None:                      # piping_fit по формам: вне таблицы — нет
        PIPING_FIT = piping_boxes(PIPING_FIT_KITS[kit]) if kit in PIPING_FIT_KITS else None
    global ISLAND_PAD_CM
    if ISLAND_PAD_CM_KITS is not None:                   # island_pad_cm по формам: вне таблицы — нет
        ISLAND_PAD_CM = kit in ISLAND_PAD_CM_KITS
    global SLEEVE_ZONE_SHIFT
    if SLEEVE_ZONE_SHIFT_KITS is not None:               # sleeve_zone_shift_cm по формам: вне таблицы — нет
        SLEEVE_ZONE_SHIFT = tuple(map(float, SLEEVE_ZONE_SHIFT_KITS[kit])) if kit in SLEEVE_ZONE_SHIFT_KITS else None
    global SLEEVE_STRIPES
    if SLEEVE_STRIPES_KITS is not None:                  # sleeve_stripes по формам: вне таблицы — нет
        SLEEVE_STRIPES = SLEEVE_STRIPES_KITS.get(kit)
    global TORSO_SHIFT
    if TORSO_SHIFT_KITS is not None:                     # torso_shift по формам (MTL дом): вне таблицы — нет
        TORSO_SHIFT = [float(x) for x in TORSO_SHIFT_KITS[kit]] if kit in TORSO_SHIFT_KITS else None
    global CHEST_BANDS
    if CHEST_BANDS_KITS is not None:                     # chest_bands по формам: вне таблицы — нет
        CHEST_BANDS = [float(x) for x in CHEST_BANDS_KITS[kit]] if kit in CHEST_BANDS_KITS else None
    global NOTCH_SEAM
    if NOTCH_SEAM_KITS is not None:                      # notch_seam по формам (NSH выезд): вне таблицы — нет
        NOTCH_SEAM = NOTCH_SEAM_KITS.get(kit)
    if YOKE_KIND_KITS:
        YOKE_KIND = YOKE_KIND_KITS.get(kit, YOKE_KIND)
    if YOKE_EA_KIND_KITS:
        YOKE_EA_KIND = YOKE_EA_KIND_KITS.get(kit, YOKE_EA_KIND)


def yoke_mask(img, lum_max=70, kind=None):
    """Пиксели кокетки по цвету (img — (..., 3)): green — тёмно-зелёная (MIN), dark — чёрная (NJD), [R, G, B] — ближе
    YOKE_RGB_DIST к этому цвету (22.10: красная MTL и синяя BUF — ни green, ни dark; lum_max тогда не нужен)."""
    kind = kind or YOKE_KIND
    if isinstance(kind, (list, tuple)):
        return np.linalg.norm(img[..., :3] - np.asarray(kind, np.float64), axis=-1) < YOKE_RGB_DIST
    lum = img.mean(-1)
    if kind == "green":
        return (lum < lum_max) & (img[..., 1] > img[..., 0] + 15)
    return (lum < lum_max) & (img.max(-1) - img.min(-1) < 45)


BODY_BOX = (0.42, 0.12, 0.58, 0.28)  # u0, v0, u1, v1 развёртки: середина спины (без кокетки, надписи и номеров)
YOKE_EA_KIND = None                # профиль yoke_shape_color: цвет кокетки у EA-формы бокoв (None — как yoke_color)
YOKE_SIDE_BLEND = None             # профиль yoke_side_blend: полуширина (м по z) перехода высоты края кокетки от
#                                    переда к спине — у широкой кокетки на плечах (MTL, ANA?) край на руке — одна прямая
#                                    наискосок, без «лесенки» (пользователь, 21.10, рисунок); None — скачок на боку (z = 0)
YOKE_CLEAN_DEPTH = None            # профиль yoke_clean_depth, м (22.10, агент plain, CAR дом): красное (прежняя кромка и
#                                    вставка) YokePaint перекрашивает только не ниже края кокетки на столько. У кокетки
#                                    «на плечо» (yoke_side_blend: боков нет) зона перекраски — всё выше 1,45 м, и красные
#                                    полосы рукава у локтя (CAR дом — на 16 см ниже края) стирались линзой. Нет — как было
YOKE_ARM_DEPTH = 0.06              # м (26.10; пользователь после игры: «калгари — светлая форма — кривые предплечья»): у кокетки
#                                    «на плечо» (yoke_side_blend — боков нет) зона YokePaint — всё выше 1,45 м, и на руке туда
#                                    попадал верх локтя (1,45–1,46 м): полосы рукава цвета кокетки, ткани и их смеси (и красное
#                                    и золото — «прежняя кромка») перекрашивались. Белые выемки в полосах у CGY, BUF, DAL, EDM
#                                    выезда, синее пятно в оранжевой полосе EDM дома, белое пятно во всю полосу у ANA выезда.
#                                    Теперь на руке (за швом проймы, YokePaint.sleeve_side) — не ниже края кокетки на столько
#                                    (остатки шапки источника — в 1–4 см под краем, полоса под кокеткой и её зачистка — до 4 см);
#                                    у полосы по рукаву (yoke_sleeve = "band": COL, PHI, WPG выезд) — как было; 0 — как было
YOKE_RGB_DIST = 60.0               # yoke_color / yoke_shape_color списком [R, G, B]: ближе — кокетка (22.10, MTL, BUF, DAL)
# Полоса под кокеткой (профиль yoke_stripe = "source", 22.10, BUF выезд: золотая ~0,9 см под синей кокеткой спереди,
# сзади и на руке; у мыса со щитом её нет — кончается у V). Цвет и ширина — замер источника под краем кокетки
# (yoke_stripe_source); рисует YokePaint (под краем без мыса, у мыса — до линии V), шов по нижнему краю — design_seams
YOKE_STRIPE = None
YOKE_STRIPE_W = (0.004, 0.02)      # м: ширина полосы под кокеткой — иначе не полоса
YOKE_STRIPE_CLEAN = 0.03           # м под полосой: перенос полосы источника (и её смеси) — тоже ткань (у сустава ниже нашей)
YOKE_BACK = None                   # профиль yoke_back = "source": край кокетки сзади — замер источника (у NHL 27 MTL 1,65 м,
#                                    BUF 1,66 — выше переда), без поля — EA-формы yoke (как MIN и NJD: «зелёное кончается
#                                    высоко» у NHL 24 1,648 — пользователь, 19.10)
NOTCH_SEAM = None                  # профиль notch_seam = "edge" или { форма = "edge" } (23.10, агент fix-b, NSH выезд): шов у
#                                    нижнего края мыса V со щитом над тканью — канавка на краю цвета, но со стороны ткани без
#                                    валика и пологим склоном (design_seams, notch_edge_seam). Обычный шов (SEAM_PROFILE: канавка
#                                    и валики по бокам) на белом под золотым мысом давал при свете сверху светлую кайму вдоль
#                                    края (нижний склон и валик смотрят вверх). Нет — как было (BUF, ANA, EDM… — обычный шов)
NOTCH_SEAM_KITS = None
NOTCH_EDGE_SOFT = 0.006            # м: notch_seam — полуширина пологого склона канавки со стороны ткани (обычный — ~1,3 мм)
NOTCH_EDGE_W = 0.014               # м: notch_seam — полоса под краем мыса, где шов заменяется (склон там < 0,5 % глубины)
NOTCH_EDGE_FADE = 0.004            # м: notch_seam — к углу мыса (где V доходит до низа полосы или кокетки) — на нет
NOTCH_YOKE_X = 0.16                # м: notch_seam = "yoke" — по краю кокетки спереди до |x| (дальше — на нет за 2 см)
YOKE_BACK_FROM_KITS = None         # профиль yoke_back_from = { форма = ["EA-форма", цвет] } (23.10, агент fix-b, NSH выезд):
#                                    край кокетки сзади — по этой EA-форме (её цвет кокетки — green | dark | [R, G, B]), бока —
#                                    по yoke. NSH выезд у NHL 27 — кокетка «до плеча» (бока MIN 1_14_3, как NJD), а спина
#                                    1_14_3 — 1,60 м; край спины прежний — BUF 1_3_4 (1,62, как у прочих NHL 27). Нет — по yoke
COLLAR = "lace"                    # профиль collar: lace — ворот adidas MIN (шнуровка, красная вставка, планка: их
#                                    швы, зоны и превью), plain — без них (NJD: кромка по кокетке, мыс со щитом)
BODY_KIND = "light"                # профиль body_color: light — медиана светлого (lum > 200, как у MIN до 21.10),
#                                    back — середина спины (у NJD дома ткань красная)


def body_color(img, yoke=True):
    """Цвет ткани свитера (BODY_KIND): light — медиана текселей светлее 200, back — медиана середины спины. yoke — без
    цвета кокетки клуба (False — у формы без кокетки: 22.10, MTL дом — кокетка
    клуба красная, как ткань дома; без красного «тканью» выходила синяя полоса спины, и InsertPaint красил у вставки
    синий V у шнуровки)."""
    if BODY_KIND == "light":
        return np.median(img.reshape(-1, 3)[img.reshape(-1, 3).mean(-1) > 200], axis=0)
    S = img.shape[0]
    u0, v0, u1, v1 = BODY_BOX
    box = img[int(v0 * S):int(v1 * S), int(u0 * S):int(u1 * S)].reshape(-1, 3)
    if yoke:
        box = box[~yoke_mask(box)]
    if TORSO_SHIFT:                                      # полоса опущена (torso_shift, MTL дом 23.10) и заходит в середину
        box = img.reshape(-1, 3)                         # спины: медиана по каналам смеси красного, синего и белого давала
        q = np.round(box / 16.0).astype(np.int64)        # фиолетовый (134, 41, 101), самый частый цвет окна — синий
        key = (q[:, 0] * 64 + q[:, 1]) * 64 + q[:, 2]    # полосы (41 % против 40 % красного) — InsertPaint красил ими V
        ks, cnt = np.unique(key, return_counts=True)     # у вставки; здесь — самый частый цвет всей развёртки (ткань,
        box = box[key == ks[cnt.argmax()]]               # 53 %)
    return np.median(box, axis=0)


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
    g_ea = yoke_mask(ea, 70, YOKE_EA_KIND)
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
    g_o = yoke_mask(ours, 70)
    green = np.median(ours[g_o & (np.abs(np.arange(S)[None, :] / S - 0.5) > 0.06)], axis=0)
    white = body_color(ours)
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
    from scipy.sparse.csgraph import connected_components
    n24 = kit3d.load_nhl24()
    src = Hy.clean_color(code, kit)
    tid, bar = kit3d.raster_uv(n24, src.shape[0])
    ys, xs = np.nonzero(tid >= 0)
    w_ = Hy.Welded(n24)                                  # только наружная оболочка: тёмная подкладка ворота смотрит вперёд
    _, comp = connected_components(w_.A, directed=False)   # и у середины «удлиняла» мыс кокетки до живота (NJD, 21.10)
    shell = comp[w_.g[n24["tri"][tid[ys, xs], 0]]] == np.bincount(comp).argmax()
    ys, xs = ys[shell], xs[shell]
    T = n24["tri"][tid[ys, xs]]
    b = bar[ys, xs]
    P = (b[:, :, None] * n24["pos"][T]).sum(1)
    P[:, 0] += 0.0035                                    # середина горловины NHL 24 — на оси (CoordMap.x_fix)
    N = kit3d._unit((b[:, :, None] * n24["nrm"][T]).sum(1))
    c = src[ys, xs]
    g = yoke_mask(c, 80)
    if YOKE_KIND != "green":                             # чёрная кокетка — только своя связная часть (не контур герба,
        from scipy import ndimage as ndi                 # полосы, низ): та, в которой больше всего текселей выше 1,62 м
        lab, _ = ndi.label(yoke_mask(src, 80))
        lv = lab[ys, xs]
        hi = np.bincount(lv[g & (P[:, 1] > 1.62)], minlength=lab.max() + 1)
        hi[0] = 0
        g = g & (lv == hi.argmax())
    out = {}
    for side, sel in (("front", (P[:, 2] > 0) & (N[:, 2] > 0.3)), ("back", (P[:, 2] < 0) & (N[:, 2] < -0.3))):
        xx, hh = [], []
        tab = COLLAR != "lace" and side == "front"      # мыс кокетки спереди (NJD: щит на нём) — от самой середины
        grid = np.concatenate([np.arange(0.0, 0.04, 0.0025), np.arange(0.04, 0.27, 0.01)]) if tab else \
            np.arange(0.04, 0.27, 0.01)
        for x0 in grid:
            hwid = 0.00125 if x0 < 0.04 else 0.005
            m = sel & g & (np.abs(np.abs(P[:, 0]) - x0) < hwid) & (P[:, 1] > 1.5) & (P[:, 1] < 1.75)
            if m.sum() > (5 if x0 < 0.04 else 20):
                xx.append(x0)
                hh.append(float(np.percentile(P[m, 1], 1)))
        xx, hh = np.array(xx), np.array(hh)
        far = xx >= 0.04                                 # сглаживание — только по прямому участку (мыс — как есть)
        hh[far] = np.convolve(np.pad(hh[far], 2, mode="edge"), np.ones(5) / 5, mode="valid")
        if tab:
            out[side] = (xx, hh)
        else:
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
    if YOKE_FRONT != "source":                           # "source" (COL) — к руке край источника, ниже (yoke_front)
        hf = np.where(x_all > YOKE_FLAT_X, np.interp(YOKE_FLAT_X, x_all, hf), hf)
    res = {"front": (x_all, hf), "back": (x_all, hb), "delta": delta}
    back_from = YOKE.get((code, kit), {}).get("from") or YOKE_BACK_FROM
    back_kind = None
    if YOKE_BACK_FROM_KITS and kit in YOKE_BACK_FROM_KITS:   # спина — с другой EA-формы, чем бока (yoke_back_from, NSH)
        back_from, back_kind = YOKE_BACK_FROM_KITS[kit]
    if back_from and YOKE_BACK != "source":              # спина — как у EA-формы клуба (её край ниже: 1,60 м)
        from . import pilot
        global YOKE_EA_KIND
        kind0 = YOKE_EA_KIND
        if back_kind is not None:                        # цвет кокетки той формы (ea_yoke_heights узнаёт по YOKE_EA_KIND)
            YOKE_EA_KIND = back_kind
        try:
            ea = ea_yoke_heights(os.path.join(pilot.unpack(back_from), "jersey_cm.png"))
        finally:
            YOKE_EA_KIND = kind0
        res["back"] = ea["back"]
    print("  кокетка: край спереди / сзади у середины, м:", round(float(np.interp(0.08, *res["front"])), 3), "/",
          round(float(np.interp(0.08, *res["back"])), 3), "(сзади — " + ("источник" if YOKE_BACK == "source" else
                                                                         f"EA {back_from}") + ")")
    if COLLAR_LAPEL:                                     # лацканы (MTL, DAL): край кокетки спереди — ровный, на высоте угла
        xs_, hs_ = res["front"]                          # вставки, где кончается лацкан, как у NHL 27 (шов кокетки — прямая
        y_c, x_c = INSERT_CORNER                         # к углу). Был подъём на 3 мм у конца лацкана на 1 см (сборка 3
        y_k = y_c + LAPEL_YOKE_GAP                       # MTL: красная черта) — крючки шва и белый зубец у конца лацкана
        res["front"] = (xs_, np.full_like(hs_, y_k))     # (пользователь, 22.10, DAL и MTL)
    if YOKE_SLEEVE == "band":                            # полоса по верху рукава (COL, PHI): край — по источнику
        res["band_fit"] = sleeve_band_fit(P, c, YOKE_KIND, n24["pos"])
    if YOKE_FRONT == "flat":                             # край спереди ровный и у середины (22.10, агент yokes, COL): вставка
        xs_, hs_ = res["front"]                          # V цвета ткани врезана в кокетку — замер «низа кокетки» у неё
        core_ = (xs_ >= 0.07) & (xs_ <= 0.13)            # опускался на 2 см (1,630 у |x| 4 см), кант шёл вдоль сторон V
        res["front"] = (xs_, np.full_like(hs_, float(np.median(hs_[core_]))))
    elif YOKE_FRONT == "source":                         # у середины ровно (как "flat": вставка V цвета ткани опускала
        xs_, hs_ = res["front"]                          # замер), с YOKE_FLAT_X к руке — край источника, не выше (22.10,
        core_ = (xs_ >= 0.07) & (xs_ <= 0.13)            # агент review-c, COL: у NHL 27 кант к пройме опускается — 1,654
        lvl = float(np.median(hs_[core_]))               # на |x| 0,12 → 1,613 на 0,24 и 1,600 на 0,26; ровный край на
        hn_ = np.where(xs_ < YOKE_FLAT_X, lvl, np.minimum(hs_, lvl))   # 1,653 давал «квадратные плечи»)
        # за концом замера (|x| 0,26) — тем же наклоном ещё YOKE_FRONT_EXT: ровный 1,600 дальше с полосой рукава (smooth_max)
        # давал на канте у подмышки «горб» (сборка 1 review-c, вид 30–45°); с наклоном кант — одна дуга, как у NHL 27
        k_ = min(float((hn_[-1] - hn_[-3]) / max(xs_[-1] - xs_[-3], 1e-6)), 0.0)
        xe_ = np.arange(xs_[-1] + 0.01, xs_[-1] + YOKE_FRONT_EXT + 1e-9, 0.01)
        res["front"] = (np.concatenate([xs_, xe_]), np.concatenate([hn_, hn_[-1] + k_ * (xe_ - xs_[-1])]))
    if COLLAR_PANEL and COLLAR != "lace":                # мыс со щитом — V шаблона ворота (BUF выезд, 22.10)
        notch_on_v(res)
    if YOKE_STRIPE == "source":                          # полоса под кокеткой (BUF выезд): цвет и ширина источника
        res["stripe"] = yoke_stripe_source(P, N, c, g, out)
        print("  полоса под кокеткой (yoke_stripe):", res["stripe"])
    elif YOKE_STRIPE == "bands":                         # полосы у края кокетки (STL выезд): профиль источника
        res["bands"] = yoke_bands_source(P, N, c, g, out)
        print("  полосы у края кокетки (yoke_stripe = bands), см от края:",
              [(b["color"], round(b["lo"] * 100, 2), round(b["hi"] * 100, 2)) for b in res["bands"] or ()])
    return res


def notch_on_v(res):
    """Мыс кокетки спереди — по V шаблона ворота (collar_panel, 22.10, BUF выезд): у NHL 27 мыс со щитом — та же вставка
    V, что у шаблона (у BUF острие 1,606 м, наклон 0,40; шаблон — PANEL_TIP_Y 1,605, PANEL_SLOPE 0,44), замер мыса по
    текстуре расходился бы со швом V на 1–2 мм — двойная линия. Мыс есть, если середина ниже прямого участка (|x|
    0,07–0,13) на 1 см. Край без мыса ("front_flat": дальше стыка — как есть, ближе — высота у стыка) — для полосы под
    кокеткой; край с мысом ("front") — ниже из него и V. Шаг у середины — 2,5 мм. -> res."""
    xs, hs = res["front"]
    core = (xs >= 0.07) & (xs <= 0.13)
    if not core.any():
        return res
    lvl = float(np.median(hs[core]))
    if hs[0] > lvl - 0.01:
        print(f"  кокетка: мыса спереди нет (середина {hs[0]:.3f} м, край {lvl:.3f}) — V шаблона не нужен")
        return res
    j = int(np.argmax(hs > lvl - 0.002))
    x2 = np.union1d(xs, np.arange(0.0, 0.12, 0.0025))
    flat = np.where(x2 < xs[j], hs[j], np.interp(x2, xs, hs))
    res["front_flat"] = (x2, flat)
    res["front"] = (x2, np.minimum(flat, PANEL_TIP_Y + PANEL_SLOPE * x2))
    res["notch"] = True
    print(f"  кокетка: мыс спереди — V шаблона ворота (острие {PANEL_TIP_Y} м, наклон {PANEL_SLOPE}), край "
          f"{hs[j]:.3f} м с |x| {xs[j]:.3f}")
    return res


def yoke_stripe_source(P, N, c, g, edges):
    """Полоса другого цвета под нижним краем кокетки у источника (yoke_stripe = "source"; BUF выезд: золотая под синей).
    Цвет — медиана в 1,5–6 мм под краем (столбцы спереди |x| 0,07–0,13, сзади 0,02–0,13; край — замер yoke_heights без
    спины EA), ширина — до нижнего текселя её цвета в 2,5 см под краем (2-й процентиль), медиана столбцов. Полоса цвета
    ткани или кокетки, ширина вне YOKE_STRIPE_W — нет (None). -> {"color": [R, G, B], "width": м}."""
    cols, cells = [], []
    for side, sel, xr in (("front", (P[:, 2] > 0) & (N[:, 2] > 0.3), (0.07, 0.13)),
                          ("back", (P[:, 2] < 0) & (N[:, 2] < -0.3), (0.02, 0.13))):
        for x0 in np.arange(xr[0], xr[1] + 1e-9, 0.01):
            h0 = float(np.interp(x0, *edges[side]))
            cm_ = sel & (np.abs(np.abs(P[:, 0]) - x0) < 0.004)
            m = cm_ & (P[:, 1] < h0 - 0.0015) & (P[:, 1] > h0 - 0.006)
            if m.sum() >= 5:
                cols.append(np.median(c[m], axis=0))
                cells.append((cm_, h0))
    if not cols:
        return None
    sc = np.median(cols, axis=0)
    yc = np.median(c[g], axis=0)
    body = np.median(np.concatenate([c[cm_ & (P[:, 1] < h0 - 0.03) & (P[:, 1] > h0 - 0.05)] for cm_, h0 in cells]), axis=0)
    ws = []
    for cm_, h0 in cells:
        m = cm_ & (P[:, 1] < h0) & (P[:, 1] > h0 - 0.025) & (np.linalg.norm(c - sc, axis=1) < 60)
        if m.sum() >= 5:
            ws.append(h0 - float(np.percentile(P[m, 1], 2)))
    w = float(np.median(ws)) if ws else 0.0
    if np.abs(sc - yc).max() < 45 or np.abs(sc - body).max() < 45 or not (YOKE_STRIPE_W[0] < w < YOKE_STRIPE_W[1]):
        print(f"  полосы под кокеткой нет: цвет {np.round(sc).astype(int).tolist()} (кокетка "
              f"{np.round(yc).astype(int).tolist()}, ткань {np.round(body).astype(int).tolist()}), ширина {w * 100:.2f} см")
        return None
    # на руке (22.10, агент yokes, NSH выезд): у NHL 27 полоса бывает только на туловище — у проймы кончается, на шапке
    # рукава её нет (у BUF — есть). Замер: под нижним краем цвета кокетки на боку руки (|x| 0,24–0,30, |z| < 0,06)
    fr = []
    for x0 in (0.25, 0.27, 0.29):
        col = (np.abs(np.abs(P[:, 0]) - x0) < 0.005) & (np.abs(P[:, 2]) < 0.06)
        ga = col & g & (P[:, 1] > 1.5)
        if ga.sum() > 20:
            h_ = float(np.percentile(P[ga, 1], 1))
            mm = col & (P[:, 1] < h_ - 0.0015) & (P[:, 1] > h_ - 0.006)
            if mm.sum() >= 5:
                fr.append(float((np.linalg.norm(c[mm] - sc, axis=1) < 60).mean()))
    arm = bool(np.median(fr) > 0.4) if fr else True
    out = {"color": [round(float(v), 1) for v in sc], "width": round(w, 4)}
    if not arm:
        out["arm"] = False
        print(f"  полоса под кокеткой — только на туловище (на руке у источника её нет: доля {np.round(fr, 2).tolist()})")
    return out


def stripe_torso(U0, P, scale):
    """Сторона туловища у шва проймы Edge (сглаженный, как armhole_split = "full"): > 0 — туловище, < 0 — рукав, в
    единицах scale (доля развёртки → пиксели или метры); вне зоны шва — +inf. Для полосы под кокеткой только на
    туловище (yoke_stripe, "arm": false)."""
    vs, us = _armhole_full()
    u, v = U0[..., 0], U0[..., 1]
    sE = np.where(P[..., 0] < 0, u, 1.0 - u)
    zone = (v >= vs[0]) & (v <= vs[-1]) & (np.abs(P[..., 0]) > ARMHOLE_X)
    return np.where(zone, (sE - np.interp(v, vs, us)) * scale, np.inf)


def yoke_stripe_band(P, hts):
    """Полоса под кокеткой в точках P: (высота края без мыса, низ полосы, линия V мыса — или None)."""
    st = hts["stripe"]
    hfl = yoke_edge_h(P, {"front": hts.get("front_flat", hts["front"]), "back": hts["back"]})
    vline = PANEL_TIP_Y + PANEL_SLOPE * np.abs(P[..., 0]) if hts.get("notch") else None
    return hfl, hfl - st["width"], vline


# Полосы у края кокетки (профиль yoke_stripe = "bands"; 22.10, агент yokes, STL выезд): у NHL 27 в синей кокетке над
# краем — синяя 1,1 см, золотая 0,9, синяя 1,0, белая 0,7, выше — синяя (у каждой полосы — два шва в base_normal);
# YokePaint красил белую полосу в кокетке цветом кокетки (белое — «ткань»), золотую оставлял переносом (на месте
# NHL 24, не параллельно своему краю). Полоса под краем (BUF, "source") — частный случай. Профиль цвета источника по
# расстоянию от края (yoke_bands_source) → отрезки одного цвета; YokePaint рисует их параллельно краю без мыса (под краем —
# до линии V, как "source"), перенос их цветов у края — перекрашивается; швы — по краям полос (design_seams)
YOKE_BANDS_D = (-0.025, 0.05)      # м от края кокетки (− под ней, + в ней): где искать полосы
YOKE_BANDS_STEP = 0.001            # м: шаг профиля
YOKE_BANDS_MIN = 0.003             # м: отрезок уже — переход между цветами, не полоса
YOKE_BANDS_TOL = 40.0              # max |Δ канала| до медианы отрезка: тот же цвет
YOKE_BANDS_GAP_MAX = 0.08          # м: разрыв полосы сзади посередине (у логотипа) — не шире; дальше — полоса без разрыва


def yoke_bands_source(P, N, c, g, edges):
    """Полосы у края кокетки источника (yoke_stripe = "bands"): профиль цвета по расстоянию d от края (шаг
    YOKE_BANDS_STEP, медиана столбцов спереди |x| 0,07–0,13 и сзади 0,02–0,13; край — замер yoke_heights без спины EA),
    отрезки одного цвета не уже YOKE_BANDS_MIN, граница — середина перехода. Над краем — отрезки не цвета кокетки ниже
    последнего её отрезка, под краем — не цвета ткани выше первого её отрезка (как yoke_stripe_source: ткань — 3–5 см
    под краем). -> [{"color": [R, G, B], "lo": м, "hi": м}] (от края, + — вверх; у края — ровно 0) или None."""
    ds = np.arange(YOKE_BANDS_D[0], YOKE_BANDS_D[1] + 1e-9, YOKE_BANDS_STEP)
    prof, body, prof_side = [], [], {"front": [], "back": []}
    for side, sel, xr in (("front", (P[:, 2] > 0) & (N[:, 2] > 0.3), (0.07, 0.13)),
                          ("back", (P[:, 2] < 0) & (N[:, 2] < -0.3), (0.02, 0.13))):
        for x0 in np.arange(xr[0], xr[1] + 1e-9, 0.01):
            h0 = float(np.interp(x0, *edges[side]))
            cm_ = sel & (np.abs(np.abs(P[:, 0]) - x0) < 0.004)
            col = np.full((len(ds), 3), np.nan)
            for i, d in enumerate(ds):
                mm = cm_ & (np.abs(P[:, 1] - (h0 + d)) < YOKE_BANDS_STEP * 0.6)
                if mm.sum() >= 2:
                    col[i] = np.median(c[mm], axis=0)
            prof.append(col)
            prof_side[side].append(col)
            mb = cm_ & (P[:, 1] < h0 - 0.03) & (P[:, 1] > h0 - 0.05)
            if mb.sum() >= 5:
                body.append(np.median(c[mb], axis=0))
    prof = np.stack(prof)
    ok = (~np.isnan(prof).any(-1)).sum(0) >= 3
    p = np.full((len(ds), 3), np.nan)
    p[ok] = np.nanmedian(prof[:, ok], axis=0)
    yc = np.median(c[g], axis=0)
    wc = np.median(body, axis=0) if body else None
    runs, i = [], 0                                      # отрезки: подряд точки ближе YOKE_BANDS_TOL к медиане отрезка
    while i < len(ds):
        if not ok[i]:
            i += 1
            continue
        j = i + 1
        while j < len(ds) and ok[j] and np.abs(p[j] - np.median(p[i:j], 0)).max() < YOKE_BANDS_TOL:
            j += 1
        if (j - i) * YOKE_BANDS_STEP >= YOKE_BANDS_MIN:
            runs.append([i, j, np.median(p[i:j], 0)])
        i = j
    if not runs:
        return None
    lo = [YOKE_BANDS_D[0]] + [(ds[a[1] - 1] + ds[b[0]]) / 2 for a, b in zip(runs, runs[1:])]
    hi = lo[1:] + [YOKE_BANDS_D[1]]
    same = lambda a, b: b is not None and np.abs(a - b).max() < YOKE_BANDS_TOL
    out = []
    top_y = max((k for k, r in enumerate(runs) if same(r[2], yc)), default=None)    # последний отрезок кокетки
    bot_w = min((k for k, r in enumerate(runs) if same(r[2], wc) and hi[k] <= 0.002), default=None)
    for k, r in enumerate(runs):
        mid = (lo[k] + hi[k]) / 2
        if mid > 0 and top_y is not None and k < top_y and not same(r[2], yc):
            out.append({"color": [round(float(v), 1) for v in r[2]], "lo": max(lo[k], 0.0), "hi": hi[k]})
        elif mid < 0 and bot_w is not None and k > bot_w and not same(r[2], wc) and not same(r[2], yc):
            out.append({"color": [round(float(v), 1) for v in r[2]], "lo": lo[k], "hi": min(hi[k], 0.0)})
    for b in out:                                        # у края — ровно по краю кокетки
        b["lo"] = 0.0 if abs(b["lo"]) < 0.002 else round(float(b["lo"]), 4)
        b["hi"] = 0.0 if abs(b["hi"]) < 0.002 else round(float(b["hi"]), 4)
        # разрыв сзади посередине (STL выезд: полосы прерваны у логотипа — у нас там «mgrhs»): полуширина — от середины
        # спины до первого столбца с цветом полосы на её средней высоте
        sel = (P[:, 2] < 0) & (N[:, 2] < -0.3)
        dc, gap = (b["lo"] + b["hi"]) / 2, None
        for x0 in np.arange(0.0, YOKE_BANDS_GAP_MAX + 1e-9, 0.0025):
            h0 = float(np.interp(x0, *edges["back"]))
            mm = sel & (np.abs(np.abs(P[:, 0]) - x0) < 0.00125) & (np.abs(P[:, 1] - (h0 + dc)) < 0.0015)
            if mm.sum() >= 2:
                if np.abs(np.median(c[mm], axis=0) - np.asarray(b["color"])).max() < YOKE_BANDS_TOL:
                    gap = x0
                    break
        b["gap_back"] = round(float(gap), 4) if gap else 0.0
    gmax = max((b["gap_back"] for b in out), default=0.0)   # разрыв у логотипа — общий (замер узкой белой полосы STL
    for b in out:                                        # попадал на сам логотип, белый)
        b["gap_back"] = gmax
    # границы полос — и по сторонам (22.10, агент review-c, STL выезд): у NHL 27 спереди белая 3,3–3,9 см над краем, сзади
    # 3,0–3,5 — медиана столбцов переда и спины вместе давала их пересечение, 3,2–3,6 (на свитере белая вдвое тоньше
    # источника, сзади — волосок 2 мм). Спереди и сзади — свои lo/hi (тот же разбор на отрезки по столбцам своей стороны),
    # между ними на плече — переход, как у края кокетки (band_lohi); у края (0) — ровно 0
    for sd, key in (("front", "f"), ("back", "b")):
        if len(prof_side[sd]) < 3:
            continue
        pr = np.stack(prof_side[sd])
        ok_s = (~np.isnan(pr).any(-1)).sum(0) >= 2
        ps = np.full((len(ds), 3), np.nan)
        ps[ok_s] = np.nanmedian(pr[:, ok_s], axis=0)
        rs, i = [], 0
        while i < len(ds):
            if not ok_s[i]:
                i += 1
                continue
            j = i + 1
            while j < len(ds) and ok_s[j] and np.abs(ps[j] - np.median(ps[i:j], 0)).max() < YOKE_BANDS_TOL:
                j += 1
            if (j - i) * YOKE_BANDS_STEP >= YOKE_BANDS_MIN:
                rs.append([i, j, np.median(ps[i:j], 0)])
            i = j
        lo_s = [YOKE_BANDS_D[0]] + [(ds[a[1] - 1] + ds[b_[0]]) / 2 for a, b_ in zip(rs, rs[1:])]
        hi_s = lo_s[1:] + [YOKE_BANDS_D[1]]
        for b in out:
            mid = (b["lo"] + b["hi"]) / 2
            cand = [k for k, r in enumerate(rs) if np.abs(r[2] - np.asarray(b["color"])).max() < YOKE_BANDS_TOL]
            if not cand:
                continue
            k = min(cand, key=lambda k: abs((lo_s[k] + hi_s[k]) / 2 - mid))
            lo_k, hi_k = (0.0 if b["lo"] == 0 else lo_s[k]), (0.0 if b["hi"] == 0 else hi_s[k])
            if abs((lo_k + hi_k) / 2 - mid) < 0.01 and hi_k > lo_k:
                b["lo_" + key], b["hi_" + key] = round(float(lo_k), 4), round(float(hi_k), 4)
    for b in out:                                        # обе стороны или ни одной
        if not all(k_ in b for k_ in ("lo_f", "hi_f", "lo_b", "hi_b")):
            for k_ in ("lo_f", "hi_f", "lo_b", "hi_b"):
                b.pop(k_, None)
    return out or None


def band_lohi(b, P):
    """Границы полосы yoke_stripe = "bands" в точках P: спереди — lo_f / hi_f, сзади — lo_b / hi_b, на плече — переход
    по z, как у края кокетки (yoke_edge_h: YOKE_SIDE_BLEND, с плеча — YOKE_BLEND_X); без них — lo / hi. -> (lo, hi)."""
    if "lo_f" not in b:
        return b["lo"], b["hi"]
    zb = YOKE_SIDE_BLEND or 0.1
    w = np.clip((P[..., 2] + zb) / (2 * zb), 0, 1)
    ax = np.abs(P[..., 0])
    wx = np.clip((ax - YOKE_BLEND_X[0]) / (YOKE_BLEND_X[1] - YOKE_BLEND_X[0]), 0, 1)
    wx = wx * wx * (3 - 2 * wx)
    w = (P[..., 2] >= 0) * (1 - wx) + w * wx
    return b["lo_b"] + (b["lo_f"] - b["lo_b"]) * w, b["hi_b"] + (b["hi_f"] - b["hi_b"]) * w


def yoke_bands_ref(P, hts):
    """Полосы у края кокетки в точках P: (высота края без мыса, линия V мыса — или None)."""
    hfl = yoke_edge_h(P, {"front": hts.get("front_flat", hts["front"]), "back": hts["back"]})
    vline = PANEL_TIP_Y + PANEL_SLOPE * np.abs(P[..., 0]) if hts.get("notch") else None
    return hfl, vline


YOKE_BANDS_REACH = 0.07            # м от края: дальше — расстояние по высоте (полос там нет)
YOKE_BANDS_3D_X = (0.20, 0.28)     # м по |x|: ближе к середине — высота над краем, дальше — по поверхности (переход). Было
#                                    (0,10; 0,15): у |x| ≈ 0,125 спереди расстояние по поверхности давало белой и золотой полосе STL
#                                    «горб» на 2–3 мм (22.10, агент review-c; при любом весе 3D там — горб, высота — ровно); купол
#                                    плеча (петля по высоте) — дальше 0,2 м. Поле только у yoke_stripe = "bands" (STL)
YOKE_BANDS_TRAP_GAP = 0.004        # м: полосы в кокетке спереди кончаются на столько от боковины вставки V (как у NHL 27)


def yoke_band_dist(P, m, hfl, tol):
    """Знаковое расстояние (м) от края кокетки без мыса — по поверхности (3D до ближайшей точки края, + — в кокетке): у
    полос yoke_stripe = "bands" по высоте над краем на куполе плеча (поверхность почти горизонтальна) контур полосы
    шёл петлёй — крючок у переда плеча и ступенька сзади (STL выезд, сборка 1). Точки края — растр, |P_y − hfl| < tol
    (полтекселя); дальше YOKE_BANDS_REACH — высота над краем."""
    from scipy.spatial import cKDTree
    dy = np.where(m, P[..., 1] - hfl, 0.0)
    edge = m & (np.abs(dy) < tol) & (np.abs(P[..., 0]) > YOKE_BANDS_3D_X[0])
    s = dy.copy()
    near = m & (np.abs(dy) < YOKE_BANDS_REACH) & (np.abs(P[..., 0]) > YOKE_BANDS_3D_X[0])
    if edge.sum() > 10:
        d, _ = cKDTree(P[edge]).query(P[near])
        # у ворота (|x| < YOKE_BANDS_3D_X[0]) — высота: там поверхность почти отвесна, а ближайшая точка края в 3D уводила
        # белую полосу STL крючком вверх к вороту (сборка 4); к плечу — по поверхности, переход плавный
        wx = np.clip((np.abs(P[near][:, 0]) - YOKE_BANDS_3D_X[0]) / (YOKE_BANDS_3D_X[1] - YOKE_BANDS_3D_X[0]), 0, 1)
        wx = wx * wx * (3 - 2 * wx)
        s[near] = dy[near] * (1 - wx) + np.sign(dy[near]) * d * wx
    return s


def yoke_bands_paint(new_out, new_in, c, P, GY, dside, cov, zone, keep, cloth, hts, g, w):
    """Полосы yoke_stripe = "bands" поверх кокетки (new_in — цвет кокетки, new_out — ткани под ней) → (цвет, cloth):
    у полосы над краем, начинающейся от края, — только верхняя граница (нижняя — край кокетки, cov), под краем — так же
    верхняя; спереди под краем — до линии V мыса. Перенос цветов кокетки, ткани и полос (и смесей) у края — перекраска."""
    bands = hts.get("bands") or ()
    hfl, vline = yoke_bands_ref(P, hts)
    m_ = GY > 0
    s = yoke_band_dist(P, m_, hfl, 0.6 * GY / AA_PX)     # по поверхности (GY — м на тексель × AA_PX)
    GS = px_size(s, m_)                                  # сглаживание края полосы — по полю расстояния
    lo_all = min(min(b["lo"], b.get("lo_f", b["lo"]), b.get("lo_b", b["lo"])) for b in bands)
    hi_all = max(max(b["hi"], b.get("hi_f", b["hi"]), b.get("hi_b", b["hi"])) for b in bands)
    near = s > lo_all - YOKE_STRIPE_CLEAN
    pal = [g, w] + [np.asarray(b["color"], np.float64) for b in bands]
    for i_ in range(len(pal)):
        for j_ in range(i_ + 1, len(pal)):
            a_, sg = pal[i_], pal[j_] - pal[i_]
            ts = np.clip(((c - a_) * sg).sum(-1) / max(float((sg * sg).sum()), 1e-6), 0, 1)
            cloth = cloth | ((np.linalg.norm(c - (a_ + ts[..., None] * sg), axis=-1) < 40) & near & zone & ~keep)
    # у самих полос (± YOKE_STRIPE_CLEAN) — всё: смесь трёх цветов переноса полос источника (не на отрезке двух) оставалась
    # светлыми точками над белой полосой сзади (STL, сборка 2); нашивки и надпись ложатся потом
    band_zone = (s > lo_all - YOKE_STRIPE_CLEAN) & (s < hi_all + YOKE_STRIPE_CLEAN)
    cloth = cloth | (band_zone & zone & ~keep)
    trap = hts.get("trap")
    tcut = None
    if trap is not None:                                 # шаблон ворота: полосы спереди — до боковины вставки V (STL выезд:
        y_top, y_bot = trap                              # иначе у щита — золотые капли и белый крючок к вороту, сборка 4)
        tt_ = np.clip((y_top - P[..., 1]) / max(y_top - y_bot, 1e-6), 0, 1)
        xs_ = TRAP_X[0] + (TRAP_X[1] - TRAP_X[0]) * tt_ + YOKE_BANDS_TRAP_GAP
        tcut = np.where(P[..., 2] > 0.03, (np.abs(P[..., 0]) - xs_) / GS, np.inf)
    for b in bands:
        col = np.asarray(b["color"], np.float64)[None, None]
        lo_, hi_ = band_lohi(b, P)                       # по сторонам (STL выезд, 22.10) или как было
        up = (hi_ - s) / GS
        gp = dside if tcut is None else np.minimum(dside, tcut)
        if b.get("gap_back"):                            # разрыв сзади посередине (у логотипа, STL выезд)
            gp = np.where(P[..., 2] < 0, np.minimum(gp, (np.abs(P[..., 0]) - b["gap_back"]) / GY), gp)
        if b["lo"] >= 0:                                 # в кокетке
            db = up if b["lo"] == 0 else np.minimum(up, (s - lo_) / GS)
            cb = np.clip(0.5 + np.minimum(db, gp), 0, 1)[..., None]
            new_in = new_in * (1 - cb) + col * cb
        else:                                            # под краем
            db = (s - lo_) / GS if b["hi"] == 0 else np.minimum(up, (s - lo_) / GS)
            if vline is not None:
                db = np.where(P[..., 2] > 0, np.minimum(db, (vline - P[..., 1]) / GY), db)
            cb = np.clip(0.5 + np.minimum(db, gp), 0, 1)[..., None]
            new_out = new_out * (1 - cb) + col * cb
    return new_out * (1 - cov[..., None]) + new_in * cov[..., None], cloth


def yoke_bands_field(G, yk):
    """Швы по краям полос yoke_stripe = "bands" на растре G: м до ближайшего края полосы (кроме края кокетки — его шов
    и так есть), где полоса видна; None — полос нет."""
    bands = yk.h.get("bands")
    if not bands:
        return None
    P, N, U0 = G["P"], G["N"], G["U0"]
    Q = yk.poly
    uL, uR = np.interp(U0[..., 1], *Q["left"]), np.interp(U0[..., 1], *Q["right"])
    dside = yoke_open(np.where(U0[..., 0] < 0.5, U0[..., 0] - uL, uR - U0[..., 0]) * G["MPU"])
    hfl, vline = yoke_bands_ref(P, yk.h)
    s = yoke_band_dist(P, G["m"], hfl, 0.6 * G["TS"])   # по поверхности, как YokePaint
    d = np.full(s.shape, np.inf)
    for b in bands:
        lo_, hi_ = band_lohi(b, P)                       # по сторонам (STL выезд, 22.10) или как было
        for e0, e in ((b["lo"], lo_), (b["hi"], hi_)):
            if e0 == 0:
                continue
            de = np.abs(s - e)
            if b.get("gap_back"):                        # разрыв сзади посередине — без шва
                de = np.where((P[..., 2] < 0) & (np.abs(P[..., 0]) < b["gap_back"]), np.inf, de)
            if e0 < 0 and vline is not None:
                de = np.where((P[..., 2] > 0) & (P[..., 1] > vline), np.inf, de)
            d = np.minimum(d, de)
    if yk.h.get("trap") is not None:                     # спереди — до боковин вставки V (как YokePaint)
        y_top, y_bot = yk.h["trap"]
        tt_ = np.clip((y_top - P[..., 1]) / max(y_top - y_bot, 1e-6), 0, 1)
        xs_ = TRAP_X[0] + (TRAP_X[1] - TRAP_X[0]) * tt_ + YOKE_BANDS_TRAP_GAP
        d = np.where((P[..., 2] > 0.03) & (np.abs(P[..., 0]) < xs_), np.inf, d)
    return np.where(dside > 0, d, np.inf)


# Кокетка, переходящая в полосу по верху рукава (профиль yoke_sleeve = "band"; 22.10, агент yokes, COL и PHI): у NHL 27
# кокетка (синяя / бордовая COL, белая / оранжевая PHI) кончается на груди и спине прямым краем, а на руке продолжается
# полосой по верху рукава до манжеты — край идёт вдоль руки спереди и сзади, низ рукава — цвета ткани; серебряный кант
# COL — по всему краю. Перенос как есть (сборка 1 COL) давал на стыке туловища и рукава ступеньки канта и зубцы (там, где
# туловище и рукав переносятся по-разному). Здесь край — два поля в метрах: туловище — высота над краем кокетки (как
# YokePaint), рукав — дуга до края полосы в кадре оси руки (угол края полосы — прямая по длине руки, замер по переносу
# рукава вдали от проймы и манжеты), полоса рукава кончается у шва проймы Edge; кокетка — их гладкое объединение
# (smooth_max, скругление YOKE_BAND_R), кант — полоса ширины источника вдоль всего края
YOKE_BAND_SEAM = 0.18              # м по оси руки от плеча (|x| 0,30 у NHL 24) — ближе замер полосы рукава не берётся: там полоса
#                                    сливается с кокеткой и расширяется (COL: 10° → 41°) — на руке выходил горб края; у плеча
#                                    край — крайний замер, дальше — объединение с кокеткой (smooth_max)
YOKE_BAND_CUFF = 0.05              # м от конца рукава — тоже
YOKE_BAND_SEAM_DEFAULT = YOKE_BAND_SEAM   # профиль yoke_band_seam (м; 23.10, агент review-d, WPG выезд — 0,06)
YOKE_BAND_SKIP = None              # профиль yoke_band_skip = [d от, до] (м от манжеты; 23.10, review-d, WPG выезд): зона полос
#                                    рукава — не в замер полосы (между соседями — интерполяция). У WPG в полосах рукава есть
#                                    тёмно-синяя (цвета кокетки) — замер там рвался (край сзади…спереди −40…−24°), а сглаживание
#                                    (медиана 5 см) тянуло и соседей: выше полос до плеча (замер кончался на 0,27 м от манжеты,
#                                    YOKE_BAND_SEAM 0,18) полоса выходила −40…40° вместо −120…40° у NHL 27 — белый клин на
#                                    переде плеча. Нет — как было
YOKE_BAND_R = 0.06                 # м: скругление угла кокетки и полосы рукава (3 см — угол заметен, у NHL 27 — плавная дуга)
YOKE_BAND_Y0 = 0.9                 # м: зона перекраски на рукаве (за швом проймы) — вся рука; туловище — от 1,45, как обычно
YOKE_BAND_SEAM_IN = 0.03           # м: полоса рукава кончается за швом проймы на туловище (мягко, YOKE_BAND_R) — без угла
YOKE_BAND_CLEAN = 0.12             # м под краем: перенос канта источника (у проймы он уходит вниз) — перекраска (сборка 1 COL:
#                                    серебряные крючки на груди у плеча)


def smooth_max(a, b, r):
    """Гладкий максимум полей (объединение областей «> 0» со скруглением r)."""
    h = np.clip(0.5 + 0.5 * (a - b) / r, 0, 1)
    return b + (a - b) * h + r * h * (1 - h)


def arm_axes(pos):
    """Оси рук Edge: {−1: …, +1: …} — (центр, ось наружу, «вверх», «вперёд», конец рукава t) по вершинам |x| > 0,30."""
    out = {}
    for sg in (-1.0, 1.0):
        a = pos[pos[:, 0] * sg > 0.30]
        c0 = a.mean(0)
        _, _, vt = np.linalg.svd(a - c0, full_matrices=False)
        ax = vt[0] * np.sign(vt[0][0] * sg)
        up = np.array([0.0, 1.0, 0.0]) - ax[1] * ax
        up /= np.linalg.norm(up)
        fr = np.cross(ax, up)
        fr *= np.sign(fr[2])
        out[sg] = (c0, ax, up, fr, float(((a - c0) @ ax).max()))
    return out


def arm_coords(P, axes):
    """(t вдоль оси руки, φ — угол от верха, + к переду, ρ — до оси) точек P по стороне x."""
    t, ph, rho = (np.zeros(P.shape[:-1]) for _ in range(3))
    for sg, (c0, ax, up, fr, _) in axes.items():
        sel = P[..., 0] * sg > 0
        d = P[sel] - c0
        tt = d @ ax
        r = d - tt[:, None] * ax
        t[sel], ph[sel], rho[sel] = tt, np.arctan2(r @ fr, r @ up), np.linalg.norm(r, axis=1)
    return t, ph, rho


def armhole_side_dist(P, m, U):
    """Знаковое расстояние (м, 3D) до шва проймы Edge (сглаженный, как armhole_split = "full"): + — рукав. P, m, U —
    точки, маска и развёртка растра. -> (поле, маска рукава, точки шва)."""
    from scipy.spatial import cKDTree
    vs, us = _armhole_full()
    u, v = U[..., 0], U[..., 1]
    sE = np.where(P[..., 0] < 0, u, 1.0 - u)
    au = np.interp(v, vs, us)
    inz = m & (v >= vs[0]) & (v <= vs[-1]) & (np.abs(P[..., 0]) > ARMHOLE_X)
    sleeve = inz & (sE < au)
    edge = inz & (np.abs(sE - au) < 1.5 / P.shape[1])
    d = np.full(P.shape[:2], 1.0)
    d[m], _ = cKDTree(P[edge]).query(P[m])
    return np.where(sleeve, d, -d), sleeve, P[edge]


YOKE_BAND_FOREIGN = 0.3            # yoke_sleeve = "band" (26.10): в кольце руки источника доля чужого цвета (не кокетки и не ткани)
#                                    больше — строка не в замер (манжета другого цвета, полосы рукава). Было «кокетки нет» —
#                                    пустое кольцо, и сглаживание (медиана, гаусс) сужало полосу к манжете на 3–5 см: у WPG выезда
#                                    лента кончалась у манжеты скруглённо, у PHI снизу до чёрной манжеты шёл белый клин
YOKE_BAND_PART = 0.5               # yoke_sleeve = "band" (26.10): кольцо с числом точек меньше этой доли медианы — неполное (край
#                                    рукава у манжеты: у COL крайняя строка давала полосу вдвое уже — «рожки» канта), не в замер


def sleeve_band_fit(P, c, kind, pos24):
    """Край полосы по верху рукава — по источнику (P, c — точки наружной оболочки сетки NHL 24 и цвет, pos24 — её
    вершины для оси руки): углы φ кокетки по длине руки (шаг 1 см) от конца рукава d = t_end − t; углы — от середины
    полосы (у PHI белое у манжеты — кольцом, низ полосы — через ±180°), 1-й / 99-й процентиль; кольцо целиком (ткани в
    кольце нет) — ±180°, без кокетки — пусто. Не в замер (26.10): строки с чужим цветом больше YOKE_BAND_FOREIGN (манжета
    другого цвета, полосы) и неполные кольца у края рукава (YOKE_BAND_PART) — полоса там по соседним строкам (за краями
    замера — крайние значения). Ткань — самый частый цвет туловища не цвета кокетки. Сглажено по длине (медиана 5 см).
    Замер по переносу на Edge (сборка 1 PHI) у проймы путался: плечо выходило оранжевым. На Edge d берётся по карте
    рукава (band_dmap). -> {сторона: (d, φ_back(d), φ_front(d), φ0)} или None."""
    from scipy.ndimage import median_filter
    axes = arm_axes(pos24)
    t, ph, _ = arm_coords(P, axes)
    yk = yoke_mask(c, 80, kind)
    torso = (np.abs(P[:, 0]) < 0.15) & (P[:, 1] > 1.10) & (P[:, 1] < 1.45) & ~yk
    q = (c[torso] // 16).astype(int)
    key = q[:, 0] * 256 + q[:, 1] * 16 + q[:, 2]
    ks, cnt = np.unique(key, return_counts=True)
    cloth = np.median(c[torso][key == ks[cnt.argmax()]], 0)
    isc = np.abs(c - cloth).max(-1) < 60
    out = {}
    for sg, (c0, ax, *_r, t_end) in axes.items():
        arm = P[:, 0] * sg > 0.30
        d = t_end - t
        d_max = float(d[arm].max())
        rng = arm & yk & (d < d_max - YOKE_BAND_SEAM)
        if rng.sum() < 100:
            return None
        ph0 = float(np.angle(np.exp(1j * ph[rng]).mean()))
        ps = np.angle(np.exp(1j * (ph - ph0)))
        bins = np.arange(0.0, d_max - YOKE_BAND_SEAM, 0.01)
        ns = [int((arm & (np.abs(d - d0 - 0.005) < 0.005)).sum()) for d0 in bins]
        n_ok = [n for n in ns if n >= 30]
        n_med = float(np.median(n_ok)) if n_ok else 0.0
        db, lo, hi, skipped = [], [], [], 0
        for d0, n in zip(bins, ns):
            if YOKE_BAND_SKIP and YOKE_BAND_SKIP[0] <= d0 + 0.005 <= YOKE_BAND_SKIP[1]:
                continue                                 # зона полос рукава (yoke_band_skip, WPG) — без замера
            if n < 30 or n < YOKE_BAND_PART * n_med:     # неполное кольцо у края рукава (COL: «рожки» у манжеты)
                skipped += 1
                continue
            sel = arm & (np.abs(d - d0 - 0.005) < 0.005)
            yy = sel & yk
            ny, nc = int(yy.sum()), int((sel & isc & ~yk).sum())
            if 1.0 - (ny + nc) / n > YOKE_BAND_FOREIGN:  # манжета другого цвета, полосы — не полоса и не ткань
                skipped += 1
                continue
            db.append(d0 + 0.005)
            if ny >= 0.97 * (ny + nc):                   # кольцо целиком: ткани нет
                lo.append(-np.pi - 0.5)
                hi.append(np.pi + 0.5)
            elif ny < 30:                                # кокетки нет
                lo.append(0.5)
                hi.append(-0.5)
            else:
                lo.append(float(np.percentile(ps[yy], 1)))
                hi.append(float(np.percentile(ps[yy], 99)))
        if len(db) < 4:
            return None
        from scipy.ndimage import gaussian_filter1d
        lo = gaussian_filter1d(median_filter(np.array(lo), 5, mode="nearest"), 2.0, mode="nearest") + ph0
        hi = gaussian_filter1d(median_filter(np.array(hi), 5, mode="nearest"), 2.0, mode="nearest") + ph0
        out[sg] = (np.array(db), lo, hi, ph0)
        k = np.linspace(0, len(db) - 1, 6).astype(int)
        print(f"  полоса рукава ({'левый' if sg < 0 else 'правый'}, источник): от манжеты, м / край сзади…спереди, ° — "
              + ", ".join(f"{db[i]:.2f}: {np.degrees(lo[i]):.0f}…{np.degrees(hi[i]):.0f}" for i in k)
              + (f"; не в замер (манжета другого цвета, полосы, край рукава) — {skipped} строк" if skipped else "")
              + f"; ткань {np.round(cloth).astype(int).tolist()}")
    return out


_BAND_SM = {}
_BAND_DMAP = {}


def band_dmap(mesh):
    """yoke_sleeve = "band" (26.10): d Edge (м от конца рукава по оси руки, arm_coords) → d источника так же, как переносит
    рукав карта рукава (SleeveMap: столбец Edge → s NHL 24, со сжатием полос к кисти SLV_COMPRESS). Без неё полоса по верху
    рукава ложилась по d Edge, а манжета и полосы — по карте: рукав Edge у манжеты на 2–4 см длиннее, манжета и полосы
    сжаты к кисти (PHI: k 0,85) — у PHI оранжевое кольцо над чёрной манжетой выходило вдвое короче NHL 27, излом края
    COL — на 3 см ближе к кисти. -> {сторона: (d Edge по столбцам карты, d источника)}; за концами — сдвиг на разницу."""
    key = (mesh["pos"].shape, round(float(mesh["pos"].sum()), 4), mesh["tri"].shape, SLV_COMPRESS)
    if key in _BAND_DMAP:
        return _BAND_DMAP[key]
    if key[:3] not in _BAND_SM:
        n24 = kit3d.load_nhl24()
        src = dict(n24, pos=n24["pos"] + np.array([0.0035, 0.0, 0.0]))   # середина горловины — на оси (CoordMap.x_fix)
        _BAND_SM[key[:3]] = (SleeveMap(src, {k: mesh[k] for k in ("pos", "uv", "nrm", "tri")}), arm_axes(n24["pos"]))
    sm, ax24 = _BAND_SM[key[:3]]
    axE = arm_axes(mesh["pos"])
    out = {}
    for sg, dd in sm.sides.items():
        e, n = dd["e"], dd["n"]
        c0, ax, *_r, t_end = axE[sg]
        dE = t_end - (e["C"] - c0) @ ax                  # столбцы Edge (от манжеты к плечу) → d по оси руки Edge
        dE = np.minimum.accumulate(dE[::-1])[::-1]       # монотонно (у самой манжеты кольца загибаются)
        c0n, axn, *_rn, t_endn = ax24[sg]
        d24n = t_endn - (n["C"] - c0n) @ axn              # столбцы NHL 24 → d по оси руки источника
        s24 = sm.s24_of(sm.src_s(e["s"]), e, dd["s24"])   # столбец Edge → s NHL 24, как у переноса (со сжатием)
        out[sg] = (dE, np.interp(s24, n["s"], d24n))
    _BAND_DMAP[key] = out
    return out


def band_d(tt, dm):
    """d Edge → d источника по таблице band_dmap (за краями — сдвиг на разницу у края)."""
    dE, d24 = dm
    return np.where(tt < dE[0], tt + (d24[0] - dE[0]),
                    np.where(tt > dE[-1], tt + (d24[-1] - dE[-1]), np.interp(tt, dE, d24)))


YOKE_BAND_FOLD = 0.03              # yoke_sleeve = "band" (26.10): s Edge от конца развёртки рукава — тут ищется край рукава
#                                    (минимум d по оси руки): у сетки Edge первые ~0,013 развёртки — подгиб, изнанка манжеты
#                                    уходит внутрь рукава на ~7 см (d там растёт обратно)
YOKE_BAND_RIM = 0.012              # s Edge за краем рукава к локтю: до сюда рукав у манжеты загибается — поле полосы на загибе
#                                    и подгибе берётся со столбца края + YOKE_BAND_RIM (band_cuff_clamp)


def band_rim(P, m, U, axes):
    """Край рукава Edge у манжеты: s столбца растра с наименьшим d по оси руки (медиана столбца в строках рукава SLV_V,
    s < YOKE_BAND_FOLD). -> {сторона: s края}."""
    H, W = m.shape
    out = {}
    for sg, (c0, ax, *_r, t_end) in axes.items():
        sE = U[..., 0] if sg < 0 else 1.0 - U[..., 0]
        sel = m & (P[..., 0] * sg > 0.30) & (U[..., 1] > SLV_V[0]) & (U[..., 1] < SLV_V[1]) & (sE < YOKE_BAND_FOLD)
        cols = np.unique(np.nonzero(sel)[1])
        if len(cols) < 4:
            continue
        dmed = np.array([np.median(t_end - (P[sel[:, c], c] - c0) @ ax) for c in cols])
        s_c = (cols + 0.5) / W if sg < 0 else 1.0 - (cols + 0.5) / W
        out[sg] = float(s_c[int(np.argmin(dmed))])
    return out


def band_cuff_clamp(F, P, m, U, axes, fit):
    """Поле полосы у манжеты (26.10, COL): от столбца края рукава + YOKE_BAND_RIM до конца развёртки — как у этого
    столбца, по строкам v (полоса и кант идут к краю рукава прямо). На загибе и подгибе ось руки не по центру рукава:
    кант COL сзади в последних 2–3 см выходил 2,9 см вместо 1,7 (у NHL 27 — 1,8), край полосы и кант загибались вдоль
    края манжеты — «рожки». -> F (на месте)."""
    H, W = m.shape
    for sg, s_rim in band_rim(P, m, U, axes).items():
        if sg not in fit:
            continue
        s_c = s_rim + YOKE_BAND_RIM
        cc = int(np.clip(np.round((s_c if sg < 0 else 1.0 - s_c) * W - 0.5), 0, W - 1))
        ok = m[:, cc] & (P[:, cc, 0] * sg > 0.30)
        for c in (np.arange(0, cc) if sg < 0 else np.arange(cc + 1, W)):
            k = m[:, c] & ok & (P[:, c, 0] * sg > 0.30)
            F[k, c] = F[k, cc]
    return F


def sleeve_band_field(P, m, U, axes, fit, dmap=None):
    """Поле полосы по верху рукава (м, + внутри): дуга до ближайшего края полосы; на туловище — не дальше
    YOKE_BAND_SEAM_IN за швом проймы (мягкое пересечение: прямой срез по шву давал угол «<» у подмышки). dmap
    (band_dmap, 26.10) — d Edge → d источника, как у переноса рукава (без него — d Edge, как было). У манжеты — по
    столбцу за загибом (band_cuff_clamp, 26.10). -> (поле, расстояние до шва со знаком: + рукав)."""
    s_dist, _, _ = armhole_side_dist(P, m, U)
    t, ph, rho = arm_coords(P, axes)
    F = np.full(P.shape[:2], -1.0)
    for sg, (db, lo, hi, ph0) in fit.items():
        sel = m & (P[..., 0] * sg > 0)
        tt = axes[sg][4] - t[sel]                        # от конца рукава Edge (за краями замера — крайние значения)
        if dmap is not None:
            tt = band_d(tt, dmap[sg])
        ps = np.angle(np.exp(1j * (ph[sel] - ph0))) + ph0   # угол — около середины полосы (без скачка у ±180° под ней)
        F[sel] = rho[sel] * np.minimum(ps - np.interp(tt, db, lo), np.interp(tt, db, hi) - ps)
    F = band_cuff_clamp(F, P, m, U, axes, fit)
    return -smooth_max(-F, -(s_dist + YOKE_BAND_SEAM_IN), YOKE_BAND_R), s_dist


def yoke_open(dside):
    """Бока кокетки: у кокетки «на плечо» (YOKE_SIDE_BLEND) их нет — шапка на руке кончается краем yoke_edge_h (прямая
    наискосок в виде сбоку). Бока EA (кривые в её развёртке) обрезали бы шапку у острова рукава и полосу под кокеткой
    сзади (за верхней строкой линзы EA — только её середину; BUF, 22.10). Иначе (MIN, NJD — «до плеча») — как есть."""
    return np.full_like(dside, 1e6) if YOKE_SIDE_BLEND else dside


def yoke_edge_h(P, hts):
    """Высота нижнего края кокетки в точках P (..., 3): спереди — hts["front"](|x|), сзади — hts["back"](|x|); между ними
    на боку — скачок при z = 0 или (YOKE_SIDE_BLEND) линейно по z: в виде сбоку — прямая от переда к спине."""
    ax = np.abs(P[..., 0])
    hf, hb = np.interp(ax, *hts["front"]), np.interp(ax, *hts["back"])
    if YOKE_SIDE_BLEND:
        w = np.clip((P[..., 2] + YOKE_SIDE_BLEND) / (2 * YOKE_SIDE_BLEND), 0, 1)
        # переход — только на плече и руке (YOKE_BLEND_X): у ворота грудь и спина неглубокие (z ≈ ±0,07), и край переда
        # там опускался к спине на 15 % разницы (MTL выезд, сборка 4: на 4 мм — красная черта под концами лацканов)
        wx = np.clip((ax - YOKE_BLEND_X[0]) / (YOKE_BLEND_X[1] - YOKE_BLEND_X[0]), 0, 1)
        wx = wx * wx * (3 - 2 * wx)
        w = (P[..., 2] >= 0) * (1 - wx) + w * wx
        return hb + (hf - hb) * w
    return np.where(P[..., 2] >= 0, hf, hb)


YOKE_BLEND_X = (0.12, 0.18)        # м по |x|: переход края кокетки «на плечо» по z — с плеча (у ворота — перед / спина)
YOKE_FRONT = None                  # профиль yoke_front = "flat": край кокетки спереди — ровный до середины; "source" (COL, 22.10,
#                                    review-c): у середины ровный, с YOKE_FLAT_X к руке — край источника (вниз)
YOKE_FRONT_EXT = 0.10              # м: yoke_front = "source" — край спереди за концом замера продолжается наклоном у конца
YOKE_SPECKS = False                # профиль yoke_specks = true (22.10, агент review-c, EDM): точки чужого цвета внутри ткани,
#                                    которую перекрашивает YokePaint, — тоже перекрашиваются (yoke_specks)
YOKE_SPECK_PX = 16                 # тексели на 1024² (по площади): часть не больше — «точка»
YOKE_SPECK_RING = 0.9              # доля кольца вокруг точки (1 тексель), что перекрашивается: меньше — деталь рисунка


def yoke_specks(cloth, zone, width):
    """Одиночные точки в перекрашиваемой ткани (yoke_specks, 22.10, агент review-c, EDM): связные части зоны YokePaint не
    цвета ткани / кокетки (cloth = False) не больше YOKE_SPECK_PX текселей 1024², вокруг которых (кольцо в 1 тексель) почти
    всё перекрашивается (≥ YOKE_SPECK_RING), — тоже перекрашиваются. У EDM сзади в кокетке на 1,654 м оставался пунктир
    строчки источника (у NHL 27 — шов по краю белой / оранжевой полосы под кокеткой, у нас кокетка ниже): серые и розовые
    чёрточки 1–6 текселей, крупно видны (сборка 2 агента yokes: 12 / 33 точки). Детали рисунка крупнее или не окружены
    тканью (нашивки — keep, вне зоны), надпись сзади ложится позже. -> cloth | точки."""
    from scipy import ndimage as ndi
    rest = zone & ~cloth
    st = np.ones((3, 3), bool)
    lab, n = ndi.label(rest, st)
    if not n:
        return cloth
    size = np.bincount(lab.ravel(), minlength=n + 1)
    small = size <= YOKE_SPECK_PX * (width / 1024.0) ** 2
    small[0] = False
    labc = np.where(small[lab], lab, 0)
    ring_lab = ndi.grey_dilation(labc, footprint=st)
    ring = (ring_lab > 0) & (labc == 0)
    tot = np.bincount(ring_lab[ring], minlength=n + 1)
    ok = np.bincount(ring_lab[ring & cloth], minlength=n + 1)
    good = small & (tot > 0) & (ok >= YOKE_SPECK_RING * tot)
    sp = good[labc] & (labc > 0)
    print(f"  кокетка: точки чужого цвета в ткани (yoke_specks) — {int(good.sum())} шт., {int(sp.sum())} текселей")
    return cloth | sp
YOKE_MIX_KEEP = False              # профиль yoke_mix_keep = true (23.10, агент review-d, WPG выезд): yoke_mix_keep
YOKE_MIX_T = (0.1, 0.9)            # доля пути «кокетка — ткань»: смесь (не сам цвет кокетки или ткани)
YOKE_MIX_PX = 5                    # текселей 1024²: смесь не дальше стольких от пикселя чужого цвета (полосы) — каёмка полосы


def yoke_mix_keep(cloth, t, dseg, zone, width):
    """Каёмки полос (yoke_mix_keep, 23.10, агент review-d, WPG выезд): YokePaint перекрашивает ткань двух цветов и их смесь —
    а серебристые каёмки голубых полос рукава WPG (серое между тёмно-синим и белым) и есть такая «смесь»: на полосе по верху
    рукава (yoke_sleeve = "band") они пропадали, полосы — голые голубые. С полем смесь (YOKE_MIX_T, ближе 40 к отрезку
    «кокетка — ткань») не дальше YOKE_MIX_PX от пикселя чужого цвета (полосы: дальше 40 от отрезка) остаётся как перенеслась;
    сглаженный край самой кокетки (смесь без чужого цвета рядом) перекрашивается, как раньше. -> cloth без каёмок."""
    from scipy import ndimage as ndi
    mix = cloth & (dseg < 40) & (t > YOKE_MIX_T[0]) & (t < YOKE_MIX_T[1])
    other = zone & (dseg >= 40)
    r = max(1, int(round(YOKE_MIX_PX * width / 1024.0)))
    near = ndi.binary_dilation(other, iterations=r)
    kept = mix & near
    print(f"  кокетка: смесь у полос другого цвета — как перенеслась (yoke_mix_keep), текселей {int(kept.sum())}")
    return cloth & ~kept


YOKE_SLEEVE = None                 # профиль yoke_sleeve = "keep" (22.10, WPG выезд: рукав целиком цвета кокетки) — YokePaint
#                                    не трогает рукав за швом проймы; без поля под краем кокетки на руке — ткань (MTL, BUF, DAL)


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

    def sleeve_side(self, shape):
        """Тексели рукава — за швом проймы Edge (armhole_u, деление «full»): |x| > ARMHOLE_X, ближе к краю развёртки."""
        P, m, _, _ = self.geo(shape)
        Hs, Ws = shape
        tu = np.broadcast_to((np.arange(Ws) + 0.5) / Ws, shape)
        tv = np.broadcast_to(((np.arange(Hs) + 0.5) / Hs)[:, None], shape)
        sE = np.where(P[..., 0] < 0, tu, 1.0 - tu)
        vs, us = _armhole_full()
        au = np.interp(np.clip(tv, ARMHOLE_ZONES[0][0], ARMHOLE_ZONES[-1][1]), vs, us)
        return m & (np.abs(P[..., 0]) > ARMHOLE_X) & (sE < au)

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
        dside = yoke_open(np.where(left_side, dl, dr))
        ax = np.abs(P[..., 0])
        h = yoke_edge_h(P, self.h)
        dh = (P[..., 1] - h) / GY
        Fs = None
        if YOKE_SLEEVE == "band":                        # кокетка и полоса по верху рукава (COL, PHI): гладкое объединение
            self.band_fit = self.h.get("band_fit")      # замер по источнику (yoke_heights)
            self.axes = arm_axes(self.mesh["pos"])
            if self.band_fit is not None:
                Fs, s_arm = sleeve_band_field(P, m, U0, self.axes, self.band_fit, band_dmap(self.mesh))
                Fu = smooth_max(P[..., 1] - h, Fs, YOKE_BAND_R)
                dh = Fu / px_size(Fu, m)
        dmin = np.minimum(dside, dh)
        cov = np.clip(0.5 + dmin, 0, 1)
        lace = (P[..., 2] > 0) & (ax < YOKE_LACE_X) & (P[..., 1] < YOKE_LACE_Y)   # вставка и шнурки — как есть
        if COLLAR != "lace":
            lace = np.zeros_like(lace)
        high = P[..., 1] > 1.45
        if Fs is not None:                               # полоса рукава: и весь рукав (за швом проймы, без низа туловища)
            high = high | ((s_arm > -YOKE_BAND_SEAM_IN) & (P[..., 1] > YOKE_BAND_Y0))
        zone = m & msk & high & (dside > -YOKE_PAD * Ws) & ~lace
        if YOKE_SLEEVE == "keep":                        # рукав цвета кокетки (WPG выезд): рукав за швом проймы — как
            zone &= ~self.sleeve_side((Hs, Ws))          # перенёсся (иначе под краем кокетки на руке — белая ткань)
        if YOKE_SIDE_BLEND and YOKE_SLEEVE != "band" and YOKE_ARM_DEPTH:   # «на плечо»: на руке — только у края (26.10:
            zone &= ~(self.sleeve_side((Hs, Ws)) & (P[..., 1] < h - YOKE_ARM_DEPTH))   # полосы у локтя — как перенеслись)
        keep = np.asarray(Image.fromarray(self.keep.astype(np.uint8) * 255).resize((Ws, Hs), Image.NEAREST)) > 0
        c = out[..., :3]
        g, w = Q["green"], Q["white"]
        seg = w - g
        t = np.clip(((c - g) * seg).sum(-1) / (seg * seg).sum(), 0, 1)
        dseg = np.linalg.norm(c - (g + t[..., None] * seg), axis=-1)
        trimc = (c[..., 0] > c[..., 1] + 60) & (c[..., 0] > 80)   # прежняя кромка/вставка (перерисуются позже)
        if YOKE_CLEAN_DEPTH is not None:                 # у кокетки «на плечо» зона — вся рука выше 1,45 м: красные полосы
            trimc &= P[..., 1] > h - YOKE_CLEAN_DEPTH     # рукава там — не кромка (CAR дом, 22.10: разрыв полос на предплечье)
        cloth = ((dseg < 40) | trimc) & zone & ~keep
        st = self.h.get("stripe")
        if self.h.get("bands"):                          # полосы у края кокетки (yoke_stripe = "bands", STL выезд)
            new, cloth = yoke_bands_paint(w[None, None] + 0 * c, g[None, None] + 0 * c, c, P, GY, dside, cov, zone, keep,
                                          cloth, self.h, g, w)
        elif st:                                           # полоса под кокеткой (yoke_stripe): под краем без мыса, у мыса —
            sc = np.asarray(st["color"], np.float64)     # ниже V; перенос полосы источника (и её смеси) — тоже ткань
            hfl, hlo, vline = yoke_stripe_band(P, self.h)
            ds_ = np.minimum(dside, (P[..., 1] - hlo) / GY)
            yfl = P[..., 1] - hfl                        # высота над краем без мыса (м)
            if Fs is not None:                           # кант — и вдоль полосы рукава (COL): ширина по полю объединения
                yfl = smooth_max(yfl, Fs, YOKE_BAND_R)
                ds_ = np.minimum(dside, (yfl + st["width"]) / px_size(yfl, m))
                hlo = P[..., 1] - yfl - st["width"] - (YOKE_BAND_CLEAN - YOKE_STRIPE_CLEAN)   # near ниже: под краем — до
                #                                          YOKE_BAND_CLEAN по тому же полю
            if vline is not None:
                ds_ = np.where(P[..., 2] > 0, np.minimum(ds_, (vline - P[..., 1]) / GY), ds_)
            if st.get("arm") is False:                   # только на туловище (NSH выезд): у шва проймы кончается
                ds_ = np.minimum(ds_, stripe_torso(U0, P, Ws / AA_PX))
            cs = np.clip(0.5 + ds_, 0, 1)
            near = P[..., 1] > hlo - YOKE_STRIPE_CLEAN   # и выше: полоса источника (у BUF сзади на 4 см выше нашей)
            #                                              оставалась золотыми чёрточками в синей кокетке (сборка 1, 22.10),
            #                                              у сустава спереди — на 1,5–2,5 см ниже (сборка 2: штрихи под полосой)
            for a_ in (g, w):
                sg = sc - a_
                ts = np.clip(((c - a_) * sg).sum(-1) / (sg * sg).sum(), 0, 1)
                cloth |= (np.linalg.norm(c - (a_ + ts[..., None] * sg), axis=-1) < 40) & near & zone & ~keep
            base = w[None, None] * (1 - cs[..., None]) + sc[None, None] * cs[..., None]
            new = base * (1 - cov[..., None]) + g[None, None] * cov[..., None]
        else:
            new = w[None, None] * (1 - cov[..., None]) + g[None, None] * cov[..., None]
        if YOKE_SPECKS:                                  # точки чужого цвета в перекрашиваемой ткани (EDM, 22.10)
            cloth = yoke_specks(cloth, zone & ~keep, Ws)
        if YOKE_MIX_KEEP:                                # смесь ткани и кокетки у полос другого цвета — как перенеслась
            cloth = yoke_mix_keep(cloth, t, dseg, zone & ~keep & ~trimc, Ws)
        out = out.copy()
        out[..., :3] = np.where(cloth[..., None], new, c)
        return out


# Красная вставка под воротом (V-вырез adidas) — рисуется сама, по контуру NHL 24 в виде спереди: полуширина по
# высоте (м, середина горловины — x = 0), замер по текстуре NHL 24 на её сетке (выезд MIN, 19.10). Края — прямые
# (пользователь: «по краям должна быть ровная, а у тебя полукругами»): нижняя часть — узкий V между шнурками, выше —
# прямые расходящиеся края до самого широкого места (у линии кокетки), дальше — прямые сходящиеся к вороту.
INSERT_HW = ((1.583, 0.0), (1.610, 0.008), (1.629, 0.0426), (1.680, 0.0094))
INSERT_HW_MIN = INSERT_HW
INSERT_CORNER = (1.629, 0.0426)    # y, |x| самого широкого угла вставки — у MIN и у NHL 27 (замер DAL: 1,628, 3,8 см)
# вставка NHL 27 (insert_color = "source": TOR, MTL, DAL) — язычок под шнурками короче, чем у MIN: острие на 1,604
# (у MIN — 1,583, у DAL выезда зелёный клин до низа шнуровки — пользователь, 22.10); замер — контур чёрной вставки DAL
# дома и зелёной DAL выезда в виде спереди (сетка NHL 24): 1,608 — 0,35 см, 1,612 — 0,5, 1,616 — 1,25, 1,620 — 2,25,
# 1,624 — 3,15; угол и верх — как у MIN (с ними сходятся швы планки и лацканы)
INSERT_HW_NHL27 = ((1.604, 0.0), (1.608, 0.0035), (1.612, 0.005), (1.616, 0.0125), (1.620, 0.0225), (1.624, 0.0315),
                   INSERT_CORNER, (1.680, 0.0094))
# Профиль insert_contour = "nhl27" (23.10, агент review-e, FLA): контур вставки — как у шаблона adidas NHL 27 (замер
# основы FLA дома на сетке NHL 24, вид спереди, qa/review-e/insert_meas.py; у DAL дома тот же): язычок до 1,591 м между
# нижними шнурками (0,9 мм на 1,594, 3 мм на 1,598), под верхними шнурками — шейка ±0,7–0,8 см (1,606–1,6135); выше —
# стороны V INSERT_HW_NHL27 (наложение на рендер NHL 27, qa/review-e/tongue.py --contour: край золота V — по ним; замер
# цвета там шире на 0,4–0,7 см — тёмная строчка шва за краем), угол и верх — общие (с ними сходятся лацканы и швы).
# У INSERT_HW_NHL27 острие на 1,604 (решение по DAL) — у FLA язычок на 1,3 см короче NHL 27, острие вместо шейки (ревью 23.10)
INSERT_HW_NHL27_FULL = (((1.591, 0.0), (1.598, 0.0030), (1.606, 0.0068), (1.6135, 0.0080))
                        + tuple(p for p in INSERT_HW_NHL27 if p[0] >= 1.616))
INSERT_CONTOUR = None              # профиль insert_contour (use_club)
INSERT_OWN_TOL = 40.0              # insert_contour: ближе к отрезку «ткань — вставка» — своё (ниже INSERT_LACE_Y красится)
# (угол — на высоте линии кокетки спереди у вставки, 1,629 м: на 1,625 между линией и углом торчал белый «зубец» —
# лесенка у стыка вставки и кокетки, пользователь, 19.10; верхний край — по-прежнему прямая от угла к вороту)
# (верх — продолжение той же прямой края к вороту, до кромки: раньше над 1,645 край шёл отвесно, и у угла с кромкой
# была ступенька — пользователь, 19.10, обведено кружками)
INSERT_LACE_Y = 1.617              # ниже — шнурки поверх вставки (тёмное не перекрашивается; 1,607 — верхний
#                                    шнурок прерывался)
INSERT_BAND = 0.015                # м за краем вставки — красное перекрашивается в ткань (там прежний перенос)
INSERT_CLEAN = None                # профиль insert_clean = "blend" (22.10, NYI): за краем вставки — и смесь её цвета с тканью
INSERT_BLEND_T = 0.15              # доля цвета вставки в смеси — от стольких (меньше — ткань с шумом)
INSERT_KITS = {("MIN", "away"), ("MIN", "home")}
# Вставка не красная (22.10, TOR: у NHL 27 ворот со шнуровкой, как у MIN, но вставка — цвета ткани: синяя дома, белая в
# гостях; insert_rule искал только красное — у TOR его нет). Профиль insert_color = "source": цвет вставки — медиана
# источника внутри контура INSERT_HW (на INSERT_SRC_PAD от края) на высотах INSERT_SRC_Y; у формы без кокетки ткань
# вокруг — одним цветом (линии кокетки нет); прежний перенос вокруг вставки перекрашивается, только если вставка не
# цвета ткани; рельеф шнуровки (LACE_ZONE) — источника целиком (фильтр «только шнурки» по цвету снимал шнурки цвета
# вставки: у TOR в гостях белые на белом). Без поля — как у MIN (красное, байт в байт)
INSERT_COLOR = None
INSERT_SRC_Y = (1.617, 1.637)      # м: высоты замера цвета вставки (над шнуровкой, у щита; щит у NHL 27 — в основе нет)
INSERT_SRC_PAD = 0.003             # м: внутрь от края контура INSERT_HW
TRIM_SMOOTH = 25.0                 # град: сглаживание ширины кромки по углу
# Кромка «ступенькой» (пользователь, 21.10, TBL; «таких форм в НХЛ много»): спереди узкая (часто с разрывом посередине),
# сбоку — ступенька, сзади широкая — во всю ширину до шва обода (RING_KNOTS), не шире. Профиль collar_trim:
# auto — по замеру источника (trim_profile: широкая / узкая ≥ TRIM_STEP_RATIO), step, smooth (как у MIN и NJD).
COLLAR_TRIM = "auto"
TRIM_MEASURE = "percentile"        # профиль trim_measure: percentile — прежний замер ширины кромки (MIN, NJD, TBL, BOS),
#                                    contiguous — сплошная полоса от края по углу (trim_profile; генератор — с DET 22.10)
TRIM_K_MAX_ADD = 0.004             # м: прибавка TRIM_K при contiguous — не больше (узкой «чуть шире», широкой — нет)
TRIM_STEP_RATIO = 2.0              # широкая часть во столько раз шире узкой — «ступенька»
TRIM_STEP_FROM = 0.0               # профиль trim_step_from (град): узкая часть кромки и ступенька — замер с этого |θ|
#                                    (22.10, NYI дом: оранжевая вставка шнуровки цвета кромки у середины давала «узкую»
#                                    1,4 см и ступеньку на 15° вместо ~80° — кромка до обода по всему переду); 0 — как было
TRIM_STEP_SOFT = 1.5               # град: переход ступеньки и концов у разрыва (≈ 1–2 текселя)
AA_PX = 2.0                        # ширина сглаживания краёв — в текселях сверхвыборки (×2): ≈ 1 тексель карты
TRIM_CLEAR = 0.008                  # м за кромкой — зубцы прежней кромки убираются
# профиль trim_clear = "angle" (22.10, CHI, UTA дом): цвет зачистки за кромкой — по углу, как у источника сразу за
# кромкой (trim_body_by_angle). У NHL 27 CHI за чёрной кромкой сбоку и сзади — вторая полоса (дом белая, выезд красная)
# до шва обода, спереди её нет; одна «ткань у ворота» (2–3,5 см сбоку) — цвет этой полосы, и зачистка красила её по
# всему переду (белая / красная черта у вставки). Нет поля — одним цветом, как раньше
TRIM_CLEAR_MODE = None
# профиль collar_band = { форма = "full" | "back" } — двухцветный ворот: у края полоса шаблона (BAND_KNOTS) цветом края
# источника, за ней — второй цвет источника: "full" — во всю ширину кромки, "back" — только в широкой части сзади.
# "full" (22.10, UTA выезд): двухцветный ворот — у края полоса шаблона (BAND_KNOTS)
# цветом источника у края (белая), за ней — кромка во весь V и обод (голубая; вставка со щитом — тоже: щит на голубом,
# как у NHL 27). Цвет кромки — медиана источника в COLLAR_BAND_D от края при |θ| > 60°, ширина — сплошной полосой
# «полоса, потом кромка» от края (trim_rule). Было: полоса цвета ткани (trim_width_from), вставка и низ V — белые
COLLAR_BAND = {}
# collar_band = { форма = "back" } (22.10, TOR дом; ворот со шнуровкой): второй цвет — только сзади. У NHL 27 TOR полоса
# у края синяя по всему кругу, а сзади от ступеньки (~78°) между ней и швом обода — белая (у выезда та же ступенька
# синим). Тот же механизм: полоса у края (BAND_KNOTS, цвет края) поверх кромки; кромка — только широкая часть ступеньки
# (step_width без узкой: спереди нет, после ступеньки — до обода), цвет — по ней (|θ| ≥ COLLAR_BAND_BACK_TH). Швы — полоса
# по кругу и край широкой части (обод, ступенька от полосы до обода): края цветов — по швам. Было (одним цветом):
# кромка ступенькой синяя красила белое, белая полоса пропадала (светлые точки по краю — её остатки)
COLLAR_BAND_BACK_TH = 100.0        # град: цвет широкой части collar_band = "back" — сзади и сбоку от |θ| (мимо ступеньки)
COLLAR_BAND_D = (0.014, 0.025)     # м от края: за полосой источника (у UTA выезда белая — 0,6–0,9 см), внутри кромки (до ~3)
TRIM_CLEAR_WIN = 3.0               # град (±): окно угла замера ткани за кромкой
TRIM_CLEAR_GAP = 0.002             # м: замер — с 2 мм за кромкой (нашей или источника, что шире) и на TRIM_CLEAR дальше
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
            if getattr(self, "trim_w", None) is not None:   # угол — только для защиты кромки (trim_w, лацканы DAL)
                TH_ = np.zeros(shape)
                TH_[m] = Hy.theta_of(P[m], zc)
                self._th = getattr(self, "_th", {})
                self._th[shape] = TH_
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
        if INSERT_CONTOUR:                               # insert_contour (FLA, 23.10): у шнуровки — только ткань, вставка
            own = np.zeros(lace.shape, bool)             # и их смесь; края шнурков (смесь с тканью) и тени — как есть: язычок
            for a_ in {tuple(self.white), tuple(self.green)}:   # NHL 27 под перекрестьем перекрашивал их (выезд —
                a_ = np.asarray(a_, np.float64)          # белым: шнурки у перекрестья тоньше и светлее)
                sg = self.red - a_
                ts = np.clip(((c - a_) * sg).sum(-1) / max((sg * sg).sum(), 1e-6), 0, 1)
                own |= np.linalg.norm(c - (a_ + ts[..., None] * sg), axis=-1) < INSERT_OWN_TOL
            lace = lace | ((y < INSERT_LACE_Y) & ~own)
        # сначала красное прежнего переноса (и его смесь с тканью) вокруг и внутри контура → ткань, потом вставка с
        # мягким краем поверх чистой ткани: клин NHL 24 после переноса чуть правее нашего — справа край сглаживался
        # по красному и обрывался в ткань (ступенька у клина между шнурками, 19.10); кромку (у ворота) — не трогать
        redish = (c[..., 0] - np.maximum(c[..., 1], c[..., 2]) > 25) & (c[..., 0] > 60)
        if INSERT_COLOR:                                 # вставка не красная (insert_color): прежний перенос — её цвета,
            redish = (np.linalg.norm(c - self.red[None, None], axis=-1) < 40) & \
                bool(np.abs(self.red - self.white).max() >= 45)   # у вставки цвета ткани (TOR) — ничего
            if INSERT_CLEAN == "blend" and np.abs(self.red - self.white).max() >= 45:
                # и смесь цвета вставки с тканью / кокеткой (22.10, NYI: оранжевый пунктир под нижним краем вставки и
                # «крючок» под её углом — сглаженный край прежнего переноса, до цвета вставки дальше 40)
                for a_ in {tuple(self.white), tuple(self.green)}:
                    a_ = np.asarray(a_, np.float64)
                    sg = self.red - a_
                    if np.abs(sg).max() < 45:
                        continue
                    ts = np.clip(((c - a_) * sg).sum(-1) / (sg * sg).sum(), 0, 1)
                    redish |= (np.linalg.norm(c - (a_ + ts[..., None] * sg), axis=-1) < 30) & (ts > INSERT_BLEND_T)
        zone = front & (np.abs(x) < hw + INSERT_BAND) & (D > INSERT_TRIM) & redish & ~lace
        lp = getattr(self, "lapel", None)                # лацкан цвета вставки (NYR выезд, 22.10: красные) — не «прежний
        if lp is not None and getattr(lp, "last_cov", None) is not None and lp.last_cov.shape == zone.shape:
            zone = zone & ~(lp.last_cov > 0.02)          # перенос»: у вставки лацкан перекрашивался в ткань — белая плашка
        tw = getattr(self, "trim_w", None)
        if tw is not None:                               # кромка цвета вставки (DAL дом: чёрные) — не «прежний перенос»:
            zone = zone & (D > np.interp(self._th[(Hs, Ws)], tw[0], tw[1], period=360) + 0.002)   # её ширина — по углу
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
Y_SUPPRESS_FADE = 0.08             # м: переход «рельеф источника → свой» (1,44–1,52); при 2 см на груди была видна
#                                    поперечная черта (пользователь, 21.10, NJD; у MIN — та же)
LACE_ZONE = (0.029, 1.580, 1.617)  # |x|, y от, y до: шнуровка — рельеф NHL 24 (шнурки, люверсы; 0,034 — в зону
#                                    попадал контур планки NHL 24: шов без смены цвета)
LACE_ZONE_DEFAULT = LACE_ZONE      # профиль lace_zone = [|x|, y от, y до] (23.10, MTL): у NHL 27 MTL один шнурок (1,594 м)
#                                    и своя короткая панель (бока ±3,2 см, низ 1,57): в зону по умолчанию она входила и
#                                    ложилась рядом с нашей планкой — «швы двоятся» (пользователь). [0.027, 1.586, 1.617] —
#                                    только шнурок, люверсы и язычок (проба: без зоны контур панели NHL 27 пропадает)
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
RELIEF_FLAT_UNDER = []             # профиль relief_flat_under = ["crest", "numbers"] (23.10, MTL дом): швы (источника и свои)
#                                    гаснут под гербом (маска нашивки этой сборки — crest_alpha.png) и в зонах номеров 1–3
#                                    карты номеров (спина, рукава): пользователь — «швы полосы видны на логотипе, нарисованном
#                                    поверх», «на номерах виднеется рельеф полосы». Складки и плетение ткани — как были
CREST_DROP = {}                    # профиль crest_drop_cm = { форма = см } (23.10): герб ниже на столько. MTL дом — сверх
#                                    torso_shift (тот двигает герб вместе с полосой): куски полос в нашивке герба выше нашей
#                                    полосы; WSH — вместе с местами литеры (letter_zone_shift_cm), литера ниже канта у ключицы
CREST_ROT = {}                     # профиль crest_rotate_deg = { форма = ° } (23.10, MTL дом): герб повёрнут на столько (против
#                                    часовой на виде спереди) — куски полос в нашивке слева выше полосы, справа ниже (~1,5 мм
#                                    на 27 см: рамка нашивки повёрнута против полосы на ~0,3°)
CREST_LEVEL = []                   # профиль crest_level = ["home"] (23.10, MTL): герб проекцией по высоте (crest_level)
RELIEF_FLAT_ZONES = (1, 2, 3)      # зоны карты номеров: номер на спине, номера на рукавах
RELIEF_FLAT_GROW = 2               # текселей рельефа: запас за краем герба / зоны
RELIEF_FLAT_FEATHER = 2.0          # текселей: мягкий край
PLACKET_LIFT = 0.0                 # профиль placket_lift_cm (23.10, MTL): шнурков меньше, чем у MIN (у MIN нижний — 1,580,
#                                    низ планки на 1,66 см ниже) — низ на столько выше: у MTL один шнурок на 1,594 → 1,4 см
#                                    (пользователь: «был стежок, и снизу всё заканчивалось так же, как после последнего
#                                    стежка у Миннесоты»)
# Обод: расстояние от края ворота (сглаженный сгиб) по |θ| — от S (свой угол и расстояние — по сетке) вверх по V:
# до ~36° — по линии NHL 24 в виде спереди (расстояния — её точки на нашей сетке), дальше — полоса за кромкой как у
# NHL 24 (кромка + 1,8–2,2 см: у Edge плечи не как у NHL 24, вид спереди там прижал бы обод к кромке), сзади — 3 см
RING = True
# Ворот adidas NHL 27 спереди — V: шов от острия посередине переда прямыми к ободу, щит NHL — внутри (у всех клубов
# одинаково: DET, TBL, LAK, BOS, VGK — замер по рельефу base_normal на сетке NHL 24, вид спереди: острие y 1,603–1,607,
# стороны — dy/d|x| 0,43–0,45). У узкой кромки (VGK, LAK, BOS, TBL) шва не было (пользователь, 22.10, VGK: «проебались
# швы вокруг зоны с шильдиком»), у широкой (DET выезд, SEA) край кромки шёл по углу плоским «корытом» — первая
# попытка (по мысу DET) вышла кривой: «зона со щитом слишком широкая, нет заострённости внизу». Профиль
# collar_panel = true: обод спереди — по V (ring_field, panel_v); у широкой кромки спереди и край цвета — по V (trim_rule)
PANEL_TIP_Y = 1.605                # м: острие V посередине переда
PANEL_SLOPE = 0.44                 # dy/d|x| сторон V в виде спереди
PANEL_BLEND = (22.0, 45.0)         # град: переход V → обод (стороны V к плечам загибаются вверх, как у NHL 27)
COLLAR_PANEL = False
# Шаблон ворота без шнуровки — один у всех клубов (пользователь, 22.10: «швы должны быть у всех одинаковые»): полоса
# ворота (шов вдоль края, сужается к спине — замер узких кромок VGK и BOS: 1,41/1,26 спереди, 0,88/0,79 сзади), боковины
# вставки со щитом (от конца полосы у |x| 3 см вниз-наружу к V у |x| 4,4 см — NHL 27, все клубы), V, обод. Края цвета
# кромки — на эти швы (trim_rule: ближе к полосе — по полосе, иначе — по V/ободу), внутри вставки полосы нет
BAND_KNOTS = ((0.0, 0.0133), (45.0, 0.0127), (90.0, 0.0113), (135.0, 0.0094), (180.0, 0.0083))
TRAP_X = (0.030, 0.044)            # м: |x| боковин вставки — вверху (у шва полосы) и внизу (у V)
# «половинчатый» ворот (collar_trim = "half"): спереди узкая полоса, сзади — до обода, переход скосом на HALF_STEP_AT
# (пользователь, 22.10, VGK: «скосы — как у Лос-Анджелеса и Тампы», у них ступенька кромки источника на 79°)
HALF_STEP_AT = 79.0
# щит NHL в шаблоне ворота — как у NHL 27 (пользователь, 22.10: «увеличить шильдик, чтобы подходил под NHL 27»): размер
# источника (масштаб 1 — у NHL 27 VGK 3,3 × 2,6 см; прежние 0,68 — под узкую кромку без вставки) и верх на 3,8 см выше
# острия V (NHL 27: острие 1,607, верх щита 1,645 на сетке NHL 24). Профильные shield_scale / shield_offset_cm у шаблона
# не действуют
SHIELD_PANEL_SCALE = 1.0
COLLAR_LINING = "source"           # профиль collar_lining: source | trim — подворот ворота цветом кромки
SHIELD_PANEL_TOP = 0.038           # м: верх щита над острием V


def band_w(th):
    return np.interp(np.abs(th), *zip(*BAND_KNOTS))


def trap_geometry(P, D, TH, front):
    """Боковины вставки в виде спереди: (y верха — шов полосы у |x| = TRAP_X[0], y низа — V у TRAP_X[1])."""
    x, y = P[..., 0], P[..., 1]
    k = front & (np.abs(np.abs(x) - TRAP_X[0]) < 0.002) & (np.abs(D - band_w(TH)) < 0.001)
    y_top = float(np.median(y[k])) if k.any() else PANEL_TIP_Y + 0.035
    return y_top, PANEL_TIP_Y + PANEL_SLOPE * TRAP_X[1]


def trap_cover(P, front, geo, texel):
    """Доля текселя внутри вставки (0…1, край — сглажен по текселю): по боковинам (|x| против боковины на этой высоте)
    и по V снизу."""
    x, y = P[..., 0], P[..., 1]
    y_top, y_bot = geo
    t = np.clip((y_top - y) / max(y_top - y_bot, 1e-6), 0, 1)
    xs = TRAP_X[0] + (TRAP_X[1] - TRAP_X[0]) * t
    k = np.hypot(1.0, (TRAP_X[1] - TRAP_X[0]) / max(y_top - y_bot, 1e-6))   # расстояние по нормали к боковине
    side = (xs - np.abs(x)) / k
    above = (y - (PANEL_TIP_Y + PANEL_SLOPE * np.abs(x))) / np.hypot(1.0, PANEL_SLOPE)
    return np.where(front, np.clip(0.5 + np.minimum(side, above) / texel, 0, 1), 0.0)


def trap_inside(P, front, geo):
    """Внутри вставки (вид спереди): |x| меньше боковины на этой высоте, выше V."""
    x, y = P[..., 0], P[..., 1]
    y_top, y_bot = geo
    t = np.clip((y_top - y) / max(y_top - y_bot, 1e-6), 0, 1)
    xs = TRAP_X[0] + (TRAP_X[1] - TRAP_X[0]) * t
    return front & (np.abs(x) < xs) & (y > PANEL_TIP_Y + PANEL_SLOPE * np.abs(x))


def edge_collar_geo(mesh, S=1024):
    """Растр сетки Edge: P, D (от края ворота), TH, перед без подворота — для шаблона ворота в trim_rule."""
    tE, bE = kit3d.raster_uv(mesh, S)
    mE = tE >= 0
    PE = (bE[mE][:, :, None] * mesh["pos"][mesh["tri"][tE[mE]]]).sum(1)
    wE = Hy.Welded(mesh)
    rE = wE.neck()
    zE = float(wE.P[rE, 2].mean())
    bandE, lipE = Hy.edge_layers(wE, rE, zE)
    foldE = Hy.fold_polyline(wE, bandE)
    edgeE = Hy.smooth_curve(foldE if foldE is not None else Hy.lip_polyline(lipE), zE, win=2.0)
    DE, THE = Hy.ring_dist(PE, edgeE), Hy.theta_of(PE, zE)
    frontE = (PE[:, 2] > 0.03) & ~bandE[wE.g[mesh["tri"][tE[mE]]]].all(1)
    return PE, DE, THE, frontE


# Лацканы ворота со шнуровкой (collar_lapel, MTL и DAL дома и в гостях) — как у NHL 27 (22.10, пользователь: «ворота у
# Далласа и Монреаля кривые, выравнивай»). Было: край лацкана — обод MIN (у шнуровки он спускается к верху планки S, и у
# угла вставки лацкан резался по горизонтали — ступенька, к плечу обод круто уходил с 4,8 до 3,0 см — излом). Стало:
# от угла вставки (INSERT_HW, 1,629 м) — коротко прямой до θ LAPEL_JOIN_TH, дальше — ровная полоса ширины лацкана NHL 27
# по углу (замер DAL и MTL дома — крой один: 50° 3,5 см, 60° 3,3, 90° 3,1), сзади — обод; шов рельефа — по тому же краю.
# Проба вариантов без сборки — game/work/nhl24/qa/lapel_try.py: прямая до 50° давала горб у плеча (D 32,6 → 36 мм)
LAPEL_KNOTS = ((50.0, 0.0355), (60.0, 0.033), (75.0, 0.032))
LAPEL_JOIN_TH = 30.0


def lapel_edge(P, D, TH, front):
    """Край лацкана спереди на растре: прямая (вид спереди) от угла вставки до точки LAPEL_JOIN_TH на ширине
    LAPEL_KNOTS → D по |θ| (медиана по 1°). -> (θ, D)."""
    x, y, ax = P[..., 0], P[..., 1], np.abs(P[..., 0])
    yc, xc = INSERT_CORNER
    th = np.abs(TH)
    d1 = float(np.interp(LAPEL_JOIN_TH, *zip(*LAPEL_KNOTS)))
    k = front & (np.abs(th - LAPEL_JOIN_TH) < 0.75) & (np.abs(D - d1) < 0.001)
    x1, y1 = float(np.median(ax[k])), float(np.median(y[k]))
    seg = (ax - xc) / max(x1 - xc, 1e-6)
    yl = yc + (y1 - yc) * seg
    on = front & (seg >= 0) & (seg <= 1) & (np.abs(y - yl) < 0.0012)
    t_, d_ = th[on], D[on]
    ths, ds = [], []
    for b in np.arange(np.floor(t_.min()), LAPEL_JOIN_TH, 1.0):
        sel = (t_ >= b) & (t_ < b + 1.0)
        if sel.sum() >= 3:
            ths.append(b + 0.5)
            ds.append(float(np.median(d_[sel])))
    return np.array(ths), np.array(ds)


def panel_v(P, D, TH, front):
    """V ворота на растре (P, D — от края ворота, TH — угол): тексели у линии y = PANEL_TIP_Y + PANEL_SLOPE·|x| (вид
    спереди) → D по |θ| (медиана по 1°); с PANEL_BLEND[0] до PANEL_BLEND[1] — плавно (smoothstep) к ободу: у NHL 27
    стороны V к плечам загибаются вверх и переходят в обод (22.10: стык V на 4 см и обода 3,2 см давал ступеньку).
    V дальше замера — прямая по 15–33°. -> (θ, D, θ_J — дальше обод RING_KNOTS)."""
    x, y = P[..., 0], P[..., 1]
    on = front & (np.abs(y - (PANEL_TIP_Y + PANEL_SLOPE * np.abs(x))) < 0.0015)
    th, d = np.abs(TH[on]), D[on]
    ths, ds = [], []
    for b in np.arange(0.0, 40.0, 1.0):
        k = (th >= b - 0.5) & (th < b + 0.5)
        if k.sum() >= 3:
            ths.append(b)
            ds.append(float(np.median(d[k])))
    ths, ds = np.array(ths), np.array(ds)
    fit = (ths >= 15) & (ths <= 33)
    kf = np.polyfit(ths[fit], ds[fit], 1)
    a = np.arange(0.0, PANEL_BLEND[1] + 0.5, 1.0)
    v = np.where(a <= ths.max(), np.interp(a, ths, ds), np.polyval(kf, a))
    ring = np.interp(np.maximum(a, RING_PLAIN_TH), *zip(*RING_KNOTS))   # обод ворота без шнуровки — с 35° (ближе к
    #                                                  середине RING_KNOTS — спуск к планке шнуровки, 5 см)
    t = np.clip((a - PANEL_BLEND[0]) / (PANEL_BLEND[1] - PANEL_BLEND[0]), 0, 1)
    sm = t * t * (3 - 2 * t)
    return a, v * (1 - sm) + ring * sm, float(PANEL_BLEND[1])

RING_PLAIN_TH = 35.0               # град: у ворота без шнуровки обод — только дальше от середины переда (там он встречает
#                                    шов кокетки); спуск к верху планки (S) — «отросточки» (пользователь, 21.10, NJD)
RING_KNOTS = ((23.7, 0.0502), (26.5, 0.0455), (32.0, 0.0355), (35.3, 0.0318), (40.0, 0.0305), (45.0, 0.0298),
              (50.0, 0.0295), (60.0, 0.0297), (75.0, 0.0300), (90.0, 0.0310), (120.0, 0.0320), (150.0, 0.0310),
              (180.0, 0.0305))

def placket_segments():
    """Отрезки планки в виде спереди (x, y): обе половины и шов посередине. PLACKET_LIFT — низ планки и шов посередине
    выше на столько (верх S — на месте, там начинается обод; бока сжаты по высоте)."""
    y0, yS = PLACKET_HALF[0][1], PLACKET_HALF[-1][1]
    k = (yS - y0 - PLACKET_LIFT) / (yS - y0)
    half = [(x, yS - (yS - y) * k) for x, y in PLACKET_HALF]
    segs = []
    for sx in (-1.0, 1.0):
        pts = [(sx * x, y) for x, y in half]
        segs += list(zip(pts[:-1], pts[1:]))
    (cx, cy0), (_, cy1) = PLACKET_CENTER
    segs.append(((cx, cy0 + PLACKET_LIFT), (cx, cy1 + PLACKET_LIFT)))
    return segs
INSERT_SEAM_Y0 = 1.612             # м: ниже — край вставки у шнуровки (рельеф NHL 24)
SEAM_PROFILE = (0.30, 0.95, 0.12, 2.0, 0.8)   # глубина, ширина канавки, валик, его место, ширина — в текселях 1024
SEAM_GEN_GAIN = 1.0
FOLD_INPAINT = 4.0                 # текселей: складки под заглаженными швами — из соседних
N24_RELIEF_FLAT = [(0.465, 0.125, 0.535, 0.172),   # u0, v0, u1, v1 base_normal NHL 24: бирка на спине (под номером),
                   (0.398, 0.598, 0.462, 0.662),   # спонсор на груди (TRIA — у MIN; в цвете снят правилом [sponsor])
                   (0.538, 0.598, 0.602, 0.662)]   # и место второго спонсора
BN_KEEP_LACE = False               # профиль base_normal_keep_lace = true (23.10, агент review-d, NYI): base_normal_decals не
#                                    выравнивает шнуровку (LACE_ZONE на сетке источника). У NYI маска нашивок (выпуклые оболочки
#                                    щита и оранжевой вставки + DECAL_FLAT_GROW) накрывала всю шнуровку: люверсы и шнурки без
#                                    рельефа, белые шнурки выезда на белом не видны. Нет — как было


def lace_zone_src(src, size):
    """Зона шнуровки (LACE_ZONE, мягкий край LACE_FADE) на развёртке сетки источника size² — вес 0…1 (base_normal_keep_lace).
    Середина горловины NHL 24 — на 0,35 см левее оси (CoordMap.x_fix)."""
    tid, bar = kit3d.raster_uv(src, size)
    m = tid >= 0
    P = np.zeros((size, size, 3))
    P[m] = (bar[m][:, :, None] * src["pos"][src["tri"][tid[m]]]).sum(1)
    f = LACE_FADE
    x = np.abs(P[..., 0] + 0.0035)
    z = m & (P[..., 2] > 0.03)
    return z * Hy.smooth((LACE_ZONE[0] + f - x) / f) * Hy.smooth((P[..., 1] - LACE_ZONE[1] + f) / f) * \
        Hy.smooth((LACE_ZONE[2] + f - P[..., 1]) / f)


BASE_NM_DECALS = None              # профиль base_normal_decals: "flat" — рельеф нашивок, которые EA «запекла» в
#                                    _base_normal (TBL ten, 21.10: молния герба и YMCA), выравнивается по маске
#                                    «готовый − основа»: цвет герба [crest_fit] сдвигает и уменьшает, а рельеф стоял бы на
#                                    старом месте — двойной контур. None — как было (у MIN и NJD основа рельефа чистая)
DECAL_FLAT_GROW = 20               # текселей 2048 (≈ 1,6 см): рельеф нашивки шире её цвета (TBL ten: фаска — до 8 px, след
#                                    тени — до ~20; при 6 и 12 у герба оставался контур, 21.10)
DECAL_FLAT_FEATHER = 10            # текселей: дальше — плавный переход к рельефу источника (без ступеньки по контуру)


CREST_SIZE_CM = None               # профиль crest_size_cm: герб не меньше (√(ширина × высота) рамки, см); [crest_fit] после —
#                                    не на букву. Правило 22.10 (замер kitport/docs: EA-гербы NHL 13 — 23–29 см, медиана 27;
#                                    у TBL, DET, VGK ~22–23 — пользователь просил крупнее; NJD 26, BOS 27, LAK 28,5 — норм)


def crest_to_size(placed):
    """Герб (нашивка crest) — не меньше CREST_SIZE_CM: рамка нашивки источника (pl["_box"], uv NHL 24) через якобиан у
    центра (обратный к pinv) → ширина и высота в см; меньше — масштаб рамки (sc и радиус) больше. Только крупнее."""
    for pl in placed:
        if pl["name"] != "crest":
            continue
        cL, nL, pinv, R, sc, rad, u_c, v_c = pl["_frame"]
        JL = np.linalg.pinv(pinv)
        b0, b1, b2, b3 = pl["_box"]
        w = np.linalg.norm(JL[:, 0]) * (b2 - b0) * sc * 100
        h = np.linalg.norm(JL[:, 1]) * (b3 - b1) * sc * 100
        size = float(np.sqrt(w * h))
        k = max(1.0, CREST_SIZE_CM / max(size, 1e-6))
        pl["_frame"] = (cL, nL, pinv, R, sc * k, rad * k, u_c, v_c)
        pl["crest_size_cm"] = [round(w, 1), round(h, 1), round(size, 1), round(k, 3)]
        print(f"  герб: {w:.1f} × {h:.1f} см (√ {size:.1f}) → ×{k:.3f} (не меньше {CREST_SIZE_CM} см)")


def decal_mask(code, kit, size):
    """Нашивки источника на развёртке size²: |готовый − основа| > 30 (порог find_patches), замкнуто; -> вес 0…1:
    1 — до DECAL_FLAT_GROW текселей от нашивки, дальше спад до 0 за DECAL_FLAT_FEATHER."""
    from PIL import Image
    from scipy import ndimage as ndi
    club = Hy.CLUB_NAME[code]
    c, b = (np.asarray(Image.open(J.n24_tex(club, kit, layer)).convert("RGB").resize((size, size))).astype(np.float64)
            for layer in ("color", "base_color"))
    m = ndi.binary_fill_holes(ndi.binary_closing(np.abs(c - b).sum(-1) > 30, iterations=3))
    # каждая нашивка — выпуклой оболочкой: у герба TBL кольцо открыто (буква C), внутри между молнией и кольцом рельеф
    # фаски источника шире запаса — оставались линии (21.10)
    from PIL import ImageDraw
    from scipy.spatial import ConvexHull
    lab, n = ndi.label(m)
    hull = Image.new("L", (size, size), 0)
    dr = ImageDraw.Draw(hull)
    for i, sl in enumerate(ndi.find_objects(lab)):
        ys, xs = np.nonzero(lab[sl] == i + 1)
        if len(ys) < 3:
            continue
        pts = np.stack([xs + sl[1].start, ys + sl[0].start], 1)
        try:
            dr.polygon([tuple(map(float, pts[k])) for k in ConvexHull(pts).vertices], fill=255)
        except Exception:                                # вырожденный участок (линия) — как есть
            continue
    m |= np.asarray(hull) > 0
    d = ndi.distance_transform_edt(~m)
    return np.clip((DECAL_FLAT_GROW + DECAL_FLAT_FEATHER - d) / DECAL_FLAT_FEATHER, 0.0, 1.0)


N24_SEAM_SIGMA = 6.0               # px (2048): что крупнее — складки NHL 24, не берутся
RELIEF_TOP_NY = (0.35, 0.6)        # y нормали: выше — прежний рельеф Edge (верх плеч)
WEAVE_CELL = (8, 6)                # период плетения в текселях (строки, столбцы) у карт 1024
WEAVE_SRC = (0.12, 0.30, 0.40, 0.60)   # v0, v1, u0, u1: участок спины без швов — по нему ячейка плетения
FOLD_MED, FOLD_SIGMA = 9, 3.0      # складки: медиана (убирает линии швов) и гаусс
SEAM_GAIN = 1.0                    # сила швов NHL 24
BN_FLAKE_SP = 8.0                  # «блёстки» рельефа источника: |xy − медиана 3×3|, сглажено σ 8 px (2048), выше — шум
BN_FLAKE_FRAC = 0.2                # доля развёртки в шуме, выше которой рельеф чинится (VGK ten 0,50; у остальных 0,01 —
#                                    вязка обода ворота, LAK ten 0,075 — фактура белых полос: не трогаются)


def flake_mask(bn):
    """Где рельеф (normal map 2048, RGB 0–255) — мелкий шум «блёстками», а не швы и складки. -> bool H×W."""
    from scipy import ndimage as ndi
    xy = bn[..., :2]
    return ndi.gaussian_filter(np.abs(xy - ndi.median_filter(xy, size=(3, 3, 1))).mean(-1), 8.0) > BN_FLAKE_SP


# Кокетка у NHL 24 (обе формы MIN) — сетчатая ткань: решётка ямок (шаг ~7 текселей 2048, ≈ 5–6 мм), только в рельефе,
# цвет ровный; внутри обода (полоса у шеи) ямок нет (пользователь, 19.10: «у погон решётчатая текстура, перенести»).
# Сила — как у NHL 24 (СКО наклона ямок ≈ 50 из 127, у плетения Edge — 6). Здесь — квадратная решётка с шагом
# PERF_CELL текселей карты 1024 (у Edge тексель ≈ 1,5–2 мм: шаг ≈ 6–8 мм; мельче 1024 не передаст), по решётке развёртки
# (на острове — island_weave: без шва через край острова).
PERF = True
YOKE_MESH = True                   # профиль yoke_mesh = false: без сетки (у NHL 27 MTL, DAL, BUF её нет — 22.10, «волнистая
#                                    хуетень вокруг белой обводки»: край сетки у лацкана шёл ступеньками по решётке ямок)
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
    if COLLAR != "lace":
        ins, lace = np.zeros_like(ins), np.zeros_like(lace)
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
        if COLLAR != "lace":                             # без планки: обод — с RING_PLAIN_TH по таблице, без спуска
            thS, DS = RING_PLAIN_TH, float(np.interp(RING_PLAIN_TH, *zip(*RING_KNOTS)))
        kn = [(thS, DS)] + [(a, d_) for a, d_ in RING_KNOTS if a > thS + 1.0]
        if COLLAR == "lace" and COLLAR_LAPEL:            # лацканы: край — прямая от угла вставки, дальше — как у NHL 27
            if "lapel" not in G:
                G["lapel"] = lapel_edge(P, D, TH, pz)
            lth, ld = G["lapel"]
            thS, DS = float(lth[0]), float(ld[0])
            kn = (list(zip(lth, ld)) + [(a, d_) for a, d_ in LAPEL_KNOTS if a > lth[-1] + 1.0]
                  + [(a, d_) for a, d_ in RING_KNOTS if a > LAPEL_KNOTS[-1][0] + 1.0])
        if COLLAR != "lace" and COLLAR_PANEL:            # ворот V: обод спереди — по V (острие посередине)
            if "panel" not in G:
                G["panel"] = panel_v(P, D, TH, pz)
            pth, pd, thJ = G["panel"]
            thS = 0.0
            kn = list(zip(pth, pd)) + [(a, d_) for a, d_ in RING_KNOTS if a > thJ + 1.0]   # V до θ_J, дальше обод
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
    dside = yoke_open(np.where(U0[..., 0] < 0.5, U0[..., 0] - uL, uR - U0[..., 0]) * G["MPU"])
    h = yoke_edge_h(P, yk.h)
    dh = (y - h) / np.maximum(np.sqrt(np.clip(1 - N[..., 1] ** 2, 0, 1)), 0.3)
    if yk.h.get("band_fit") is not None:                 # полоса по верху рукава (yoke_sleeve = "band", COL, PHI)
        dh = smooth_max(dh, sleeve_band_field(P, G["m"], U0, arm_axes(yk.mesh["pos"]), yk.h["band_fit"],
                                              band_dmap(yk.mesh))[0], YOKE_BAND_R)
    return np.minimum(dside, dh)


def yoke_stripe_field(G, yk):
    """Полоса под кокеткой (yoke_stripe) на растре G: F > 0 внутри полосы вместе с кокеткой (м до края: бока, низ
    полосы, у мыса — V), иначе < 0; None — полосы нет. Шов — по нижнему краю полосы (у NHL 27 BUF — кант с двумя швами)."""
    if not yk.h.get("stripe"):
        return None
    P, N, U0 = G["P"], G["N"], G["U0"]
    Q = yk.poly
    uL, uR = np.interp(U0[..., 1], *Q["left"]), np.interp(U0[..., 1], *Q["right"])
    dside = yoke_open(np.where(U0[..., 0] < 0.5, U0[..., 0] - uL, uR - U0[..., 0]) * G["MPU"])
    hfl, hlo, vline = yoke_stripe_band(P, yk.h)
    k = np.maximum(np.sqrt(np.clip(1 - N[..., 1] ** 2, 0, 1)), 0.3)
    F = np.minimum(dside, (P[..., 1] - hlo) / k)
    if yk.h.get("band_fit") is not None:                 # кант и вдоль полосы рукава (COL)
        F = np.minimum(dside, smooth_max((P[..., 1] - hfl) / k, sleeve_band_field(P, G["m"], U0, arm_axes(yk.mesh["pos"]),
                                                                                   yk.h["band_fit"], band_dmap(yk.mesh))[0],
                                         YOKE_BAND_R) + yk.h["stripe"]["width"])
    if vline is not None:
        F = np.where(P[..., 2] > 0, np.minimum(F, (vline - P[..., 1]) / k), F)
    if yk.h["stripe"].get("arm") is False:               # полоса только на туловище: на рукаве шва низа полосы нет
        F = np.where(stripe_torso(U0, P, 1.0) < 0, np.inf, F)
    return F


def notch_edge_seam(H, P, N, zone, hts, ts, mode="edge"):
    """notch_seam = "edge" (23.10, агент fix-b, NSH выезд): у нижнего края мыса V со щитом (V шаблона, notch_on_v), где
    под ним ткань (выше низа полосы под кокеткой или кокетки), высота швов со стороны ткани — пологий склон от дна канавки
    на самом крае (seam_height(0) · exp(−(s / NOTCH_EDGE_SOFT)²), s — м по высоте от края) вместо обычного профиля:
    обычный (канавка ~1,3 мм и валик на 2 текселя) на белом под золотом при свете сверху — светлая кайма вдоль края.
    Край цвета и дно канавки — на линии V, сторона мыса — как было. К углу мыса (V доходит до низа полосы) — на нет
    (NOTCH_EDGE_FADE). -> H."""
    y, ax = P[..., 1], np.abs(P[..., 0])
    k = np.maximum(np.sqrt(np.clip(1 - N[..., 1] ** 2, 0, 1)), 0.3)
    if mode == "yoke":                                   # "yoke" (NJD, 23.10): мыс — край самой кокетки (V кокетки, не
        vline = np.interp(ax, *hts["front"])            # шаблона ворота): шов — по краю кокетки спереди до NOTCH_YOKE_X
        w = np.clip((NOTCH_YOKE_X - ax) / 0.02, 0, 1)
    else:
        vline = PANEL_TIP_Y + PANEL_SLOPE * ax
        hfl = np.interp(ax, *hts.get("front_flat", hts["front"]))
        lo = hfl - (hts["stripe"]["width"] if hts.get("stripe") else 0.0)   # низ полосы под кокеткой (или кокетки)
        w = np.clip((lo - vline) / NOTCH_EDGE_FADE, 0, 1)
    s = (y - vline) / k                                  # м: + в мысе, − в ткани под ним
    w = w * w * (3 - 2 * w)
    band = zone & (s < 0) & (s > -NOTCH_EDGE_W) & (w > 0)
    soft = float(seam_height(np.array(0.0))) * np.exp(-(s / NOTCH_EDGE_SOFT) ** 2)
    out = np.where(band, H * (1 - w) + soft * w, H)
    print(f"  шов у края мыса V (notch_seam = edge): {int(band.sum())} текселей, склон {NOTCH_EDGE_SOFT * 1000:.0f} мм")
    return out


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
    if COLLAR != "lace":
        in_ins, d_i = np.zeros_like(in_ins), inf
    info = {}
    d_t = inf
    tr = painters.get("trim")
    if tr is not None:
        wid = np.interp(TH, tr.width[0], tr.width[1], period=360)
        d_t = np.where(m & ~B & ~in_ins, np.abs(wid - D), inf)
        if getattr(tr, "no_seam", False):                # лацканы цвета кромки (lapel_trim_band): шва по краю кромки нет
            d_t = inf
        if getattr(tr, "band_back", False):              # collar_band = "back": шов полосы у края — по кругу, широкой
            wb = band_w(TH)                              # части — где она шире полосы (обод, ступенька от полосы)
            d_t = np.where(m & ~B & ~in_ins, np.minimum(np.where(wid > wb + 0.001, np.abs(wid - D), inf),
                                                        np.abs(wb - D)), inf)
            wid = np.maximum(wid, wb)
    else:
        wid = np.zeros((S, S))
    d_tz = inf
    template = COLLAR_PANEL and COLLAR != "lace"
    if template:                                         # шаблон ворота: шов полосы (не по кромке клуба), боковины вставки
        geo = trap_geometry(P, D, TH, front)
        inside = trap_inside(P, front, geo)
        d_t = np.where(m & ~B & ~inside, np.abs(band_w(TH) - D), inf)
        y_top, y_bot = geo
        d_tz = inf.copy()
        for sgn in (-1.0, 1.0):
            x0, y0, x1, y1 = sgn * TRAP_X[0], y_top, sgn * TRAP_X[1], y_bot
            ex, ey = x1 - x0, y1 - y0
            tt = np.clip(((x - x0) * ex + (y - y0) * ey) / (ex * ex + ey * ey), 0, 1)
            d_tz = np.where(front, np.minimum(d_tz, np.hypot(x - (x0 + tt * ex), y - (y0 + tt * ey))), d_tz)
    d_y = inf
    yk = painters.get("cur") or painters.get("yoke_shape")
    if yk is not None:
        F_y = yoke_field(G, yk)
        lace = (P[..., 2] > 0) & (ax < YOKE_LACE_X) & (y < YOKE_LACE_Y) & (COLLAR == "lace")
        d_y = np.where(m & ~B & ~in_ins & ~lace & (D > wid + 0.002) & (y > 1.45), np.abs(F_y), inf)
        F_s = yoke_stripe_field(G, yk)                   # полоса под кокеткой: шов и по её нижнему краю (BUF, 22.10)
        if F_s is not None:
            d_y = np.minimum(d_y, np.where(m & ~B & ~in_ins & (D > wid + 0.002) & (y > 1.45), np.abs(F_s), inf))
        F_b = yoke_bands_field(G, yk)                    # полосы у края кокетки (STL выезд): швы по их краям
        if F_b is not None:
            bmask = m & ~B & ~in_ins & (D > wid + 0.002) & (y > 1.45)
            if template:
                bmask &= ~inside
            d_y = np.minimum(d_y, np.where(bmask, F_b, inf))
    # планка под шнуровкой (как у NHL 24: PLACKET_HALF) — отрезки в виде спереди (x, y), середина горловины — x = 0
    d_p = inf.copy()
    pz = m & ~B & (N[..., 2] > 0.2) & (P[..., 2] > 0.03)
    for (x0, y0), (x1, y1) in (placket_segments() if COLLAR == "lace" else ()):
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
        side = np.isfinite(R) & ~in_ins & (D > (band_w(TH) if template else wid) + 0.004)
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
    sl = painters.get("sleeve_lines")                   # ломаные краёв полос рукава (sleeve_stripes = "lines", ANA)
    if sl:
        d_s = np.minimum(d_s, np.where(m, sleeve_lines_dist(U0[..., 0], U0[..., 1], x, sl) / sl["S"] * G["MPU"], inf))
    d_a = np.where(m & ~B, armhole_dist(G), inf)          # шов проймы Edge (низ, где делится цвет)
    d = np.minimum(np.minimum(np.minimum(np.minimum(np.minimum(np.minimum(np.minimum(d_i, d_t), d_y), d_p), d_r), d_s), d_a),
                   d_tz)
    t = d / np.maximum(ts, 1e-6)
    H = np.where(np.isfinite(t), seam_height(np.where(np.isfinite(t), t, 99.0)), 0.0)
    H = np.where(m, H, 0.0)
    if NOTCH_SEAM == "edge" and yk is not None and yk.h.get("notch"):   # мыс V над тканью — без светлой каймы (NSH выезд)
        H = notch_edge_seam(H, P, N, m & ~B & front, yk.h, ts)
    elif NOTCH_SEAM == "yoke" and yk is not None:       # край кокетки V (NJD, 23.10: та же светлая кайма под мысом)
        H = notch_edge_seam(H, P, N, m & ~B & front, yk.h, ts, mode="yoke")
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
                    ("sleeve", d_s), ("armhole", d_a), ("panel_sides", d_tz)):
        info[nm_] = int((np.isfinite(dd) & (dd < 0.002)).sum())
    return xy, info


def ea_yoke_heights(ea_png):
    """Высота нижнего края кокетки EA-формы (на сетке Edge) по |x|, спереди и сзади (самый низ её цвета), сглажено."""
    from PIL import Image
    from scipy import ndimage as ndi
    E = load(0, 1, 2)
    S = 1024
    ea = np.asarray(Image.open(ea_png).convert("RGB").resize((S, S))).astype(np.float64)
    g = yoke_mask(ea, 90, YOKE_EA_KIND)
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


PANT_TINT_TOL = (20.0, 45.0)       # pant_tint: отступ цвета от луча основного цвета Legacy (max по каналам): до 20 — его оттенок,
#                                    от 45 — чужой цвет (полосы, нашивки), между — плавно


def _dominant(rgb):
    q = np.round(rgb.reshape(-1, 3) / 12).astype(int)
    key = (q[:, 0] * 64 + q[:, 1]) * 64 + q[:, 2]
    ks, cnt = np.unique(key, return_counts=True)
    return np.median(rgb.reshape(-1, 3)[key == ks[np.argmax(cnt)]], axis=0)


def tint_pant(png, src_png):
    """Шорты Legacy (слот pant = "legacy") — оттенком шорт источника (поле слота pant_tint = "source"; NYR, 23.10,
    пользователь: «шорты как раньше — хорошо, только оттенок розово-красный, как в NHL 27»): основной цвет шорт Legacy и
    его оттенки (тот же цвет темнее и светлее: луч основного цвета) → основной цвет шорт источника (перенос kit, pant_cm)
    с той же долей яркости; полосы, нашивки и прочие цвета — как были. -> отчёт."""
    from PIL import Image
    a = np.asarray(Image.open(png).convert("RGBA")).astype(np.float64)
    rgb = a[..., :3]
    main_l = _dominant(rgb)
    main_s = _dominant(np.asarray(Image.open(src_png).convert("RGB")).astype(np.float64))
    t = (rgb @ main_l) / max(float(main_l @ main_l), 1e-6)
    resid = np.abs(rgb - t[..., None] * main_l).max(-1)
    lo, hi = PANT_TINT_TOL
    w = np.clip((hi - resid) / (hi - lo), 0, 1) * (t > 0.3)
    a[..., :3] = rgb * (1 - w[..., None]) + np.clip(t[..., None] * main_s, 0, 255) * w[..., None]
    Image.fromarray(np.clip(np.round(a), 0, 255).astype(np.uint8), "RGBA").save(png)
    return f"{np.round(main_l).astype(int).tolist()} → {np.round(main_s).astype(int).tolist()}, {int((w > 0.5).sum())} текселей"


def save_crest_alpha(placed, od):
    """Где лёг герб в этой сборке (kit_hybrid.decal_post: pl["_alpha"]) → od/crest_alpha.png (для relief_flat_under)."""
    from PIL import Image
    for pl in placed or ():
        if pl["name"] != "crest" or "_alpha" not in pl:
            continue
        msk, sel, a = pl["_alpha"]
        f = np.zeros(int(msk.sum()))
        f[sel] = a
        M = np.zeros(msk.shape)
        M[msk] = f
        Image.fromarray(np.clip(np.round(M * 255), 0, 255).astype(np.uint8), "L").save(os.path.join(od, "crest_alpha.png"))
        return int((M > 0.5).sum())
    return 0


def relief_flat_weight(code, kit, od, S):
    """Вес 0…1 на развёртке S²: где швы рельефа гаснут (профиль relief_flat_under). crest — маска герба этой сборки
    (crest_alpha.png), numbers — зоны RELIEF_FLAT_ZONES карты номеров собранного слота (номера там уже на своих местах;
    слота ещё нет — карта образца Legacy)."""
    from PIL import Image
    from scipy import ndimage as ndi
    w = np.zeros((S, S))
    cp = os.path.join(od, "crest_alpha.png")
    if "crest" in RELIEF_FLAT_UNDER and os.path.exists(cp):
        c = np.asarray(Image.open(cp).convert("L").resize((S, S), Image.BILINEAR)) / 255.0
        # весь герб целиком (как рамка нашивки): замкнуть и залить — швы гаснут и в дырах маски
        c = np.maximum(c, ndi.binary_fill_holes(ndi.binary_closing(c > 0.5, iterations=4)))
        w = np.maximum(w, c)
    if "numbers" in RELIEF_FLAT_UNDER:
        p = os.path.join(WORK, "slot", "kits", f"{code}_{kit}", "name_cm.png")
        if not os.path.exists(p) and kit in SLOT_KITS:
            p = os.path.join(WORK, "cur_kits", SLOT_KITS[kit]["legacy"], "name_cm.png")
        if os.path.exists(p):
            n = np.asarray(Image.open(p).convert("RGBA"))
            z = (n[..., 0] > 128) & (n[..., 1] > 128) & np.isin(n[..., 2], RELIEF_FLAT_ZONES)
            w = np.maximum(w, np.asarray(Image.fromarray(z.astype(np.uint8) * 255).resize((S, S), Image.NEAREST)) / 255.0)
        else:
            print(f"  relief_flat_under numbers: нет карты номеров {p} — номера без правки")
    if w.max() > 0:
        w = np.maximum(w, ndi.binary_dilation(w > 0.5, iterations=RELIEF_FLAT_GROW))
        w = ndi.gaussian_filter(w.astype(np.float64), RELIEF_FLAT_FEATHER)
    return np.clip(w, 0, 1)


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
    def src_bn(k):
        b_ = normal_map(J.n24_tex(Hy.CLUB_NAME[code], k, "base_normal"), 2048).astype(np.float64)
        defaults, rules = kit_hybrid.load_rules(kit_hybrid.RULES, code, k, [])
        sp = tuple(n for n, r in rules.items() if r.get("sponsor"))
        b_, _, _ = kit_hybrid.standard_patches(b_, rules, defaults, names=sp)
        for u0, v0, u1, v1 in N24_RELIEF_FLAT:
            S2 = b_.shape[0]
            b_[int(v0 * S2):int(v1 * S2), int(u0 * S2):int(u1 * S2), :3] = (128, 128, 255)
        return b_
    bn = src_bn(kit)
    # фактура ткани «блёстками» в рельефе источника (VGK ten, 22.10: золотая ткань NHL 27 — шум по всему торсу и верху
    # рукавов, в швы NHL 24 он проходил целиком — свитер «в крошку»; медиана и гаусс оставляют пятна). Если шумно больше
    # BN_FLAKE_FRAC развёртки — там рельеф другой формы клуба (тот же крой: швы те же), где у неё чисто; иначе ровно
    fl = flake_mask(bn)
    if fl.mean() > BN_FLAKE_FRAC:
        other = {"home": "away", "away": "home"}.get(kit)
        ob = src_bn(other) if other and os.path.exists(J.n24_tex(Hy.CLUB_NAME[code], other, "base_normal")) else None
        ok = ~flake_mask(ob) if ob is not None else np.zeros_like(fl)
        w_o = ndi.gaussian_filter((fl & ok).astype(np.float64), 2.0)[..., None]
        w_f = ndi.gaussian_filter((fl & ~ok).astype(np.float64), 2.0)[..., None]
        if ob is not None:
            bn[..., :3] = bn[..., :3] * (1 - w_o) + ob[..., :3] * w_o
        bn[..., :3] = bn[..., :3] * (1 - w_f) + np.array([128.0, 128.0, 255.0]) * w_f
        print(f"  рельеф источника: «блёстки» на {fl.mean():.0%} развёртки — рельеф {other} на {(fl & ok).mean():.0%}, "
              f"ровно на {(fl & ~ok).mean():.0%}")
    if BASE_NM_DECALS == "flat":                         # профиль base_normal_decals: нашивки, «запечённые» в рельеф
        w = decal_mask(code, kit, bn.shape[0])[..., None]
        if BN_KEEP_LACE and COLLAR == "lace":            # шнуровка — рельеф источника (NYI, 23.10): не выравнивать
            w = w * (1 - lace_zone_src(cmap.src, bn.shape[0]))[..., None]
        bn[..., :3] = bn[..., :3] * (1 - w) + np.array([128.0, 128.0, 255.0]) * w
        print(f"  рельеф источника: нашивки выровнены (base_normal_decals), {int((w > 0.5).sum())} текселей 2048")
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
    if COLLAR != "lace":
        lace = np.zeros_like(lace)
    ins = (painters or {}).get("insert")
    cm_path = os.path.join(os.path.dirname(nm_path), "jersey_cm.png")
    if ins is not None and os.path.exists(cm_path) and not INSERT_COLOR:   # insert_color: рельеф шнуровки — целиком
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
    keep24 = np.maximum(1.0 - Hy.smooth((Pm[:, 1] - Y_SUPPRESS + Y_SUPPRESS_FADE * 0.75) / Y_SUPPRESS_FADE), lace)
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
    if SLEEVE_LINES:                                     # sleeve_stripes = "lines": швы источника шли по краям до правки
        dl = sleeve_lines_dist(G0["U0"][m][:, 0], G0["U0"][m][:, 1], Pm[:, 0], SLEEVE_LINES)   # (у ANA до 11 px от
        keep24 = keep24 * np.where(np.isfinite(dl), Hy.smooth((dl - SLV_LINES_CLEAR) / 3.0), 1.0)   # ломаной) — на нет,
        painters["sleeve_lines"] = SLEEVE_LINES          # свой шов — по ломаной (design_seams)
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
    if PERF and YOKE_MESH and yk is not None:
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
        if getattr(tr, "band_back", False):              # collar_band = "back": полоса у края — тоже гладкая
            wid = np.maximum(wid, band_w(G1["TH"][ys, xs]))
        plain = np.maximum(plain, Hy.smooth((wid + 0.001 - G1["D"][ys, xs]) / 0.002))
    yi_, xi_ = G1["P"][ys, xs, 1], np.abs(G1["P"][ys, xs, 0])
    ys_h, hs_h = (np.array(v) for v in zip(*INSERT_HW))
    hw = np.interp(yi_, ys_h, hs_h, left=-1.0, right=-1.0)
    fr_ = (G1["N"][ys, xs, 2] > 0.2) & (G1["P"][ys, xs, 2] > 0.03) & (yi_ > INSERT_SEAM_Y0) & (COLLAR == "lace")
    plain = np.maximum(plain, fr_ * Hy.smooth((hw + 0.001 - xi_) / 0.002))
    wv = wv * (1.0 - plain)[:, None]
    flat_w = relief_flat_weight(code, kit, os.path.dirname(nm_path), S)[ys, xs] if RELIEF_FLAT_UNDER else 0.0
    if RELIEF_FLAT_UNDER:
        print(f"  швы гладко под {'/'.join(RELIEF_FLAT_UNDER)}: {int((flat_w > 0.5).sum())} текселей")
    body_xy = low_px + wv + (seam24 * keep24[:, None] + gen[ys, xs]) * (1.0 - np.asarray(flat_w))[..., None]         if RELIEF_FLAT_UNDER else low_px + wv + seam24 * keep24[:, None] + gen[ys, xs]
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

    def __init__(self, mesh, color, width, lining=None, body=None, clear_to=None, trap=None):
        self.mesh, self.color, self.width, self.lining, self.body = mesh, color, width, lining, body
        self.clear_to = clear_to                       # (|θ|, м): зачистка за кромкой — не ближе этого (кромка источника)
        self.trap = trap                               # шаблон ворота: вставка со щитом (trap_geometry) — без полосы
        self._P = {}
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
            PP = np.zeros(shape + (3,))
            PP[m] = P
            self._geo[shape] = (D, TH, B, m, G)
            self._P[shape] = PP
        return self._geo[shape]

    def __call__(self, out, msk):
        Hs, Ws = msk.shape
        D, TH, B, m, G = self.geo((Hs, Ws))
        th_w, w_w = self.width
        wid = np.interp(TH, th_w, w_w, period=360)
        texel = 0.0021 * 1024 / Ws
        cov = np.clip(0.5 + (wid - D) / G, 0, 1)
        cov = np.where(B, ((D < TRIM_INNER) & (wid > 1e-4)).astype(float), cov)   # в разрыве кромки — и подворот без неё
        a_in = None
        if self.trap is not None:                       # шаблон ворота: во вставке со щитом полосы нет (как у NHL 27)
            PP = self._P[(Hs, Ws)]
            narrow = wid < band_w(TH) + 0.002
            if getattr(self, "band_frame", False):      # collar_band = "frame" (NSH дом): вставка — цветом ткани и у
                narrow = np.ones_like(narrow)            # широкой кромки (кромка — рамкой вокруг вставки)
            a_in = trap_cover(PP, m & ~B & (PP[..., 2] > 0.03), self.trap, texel) * narrow
            cov = cov * (1 - a_in)                      # край полосы по боковине — сглажен
        zone = m & msk & (D < wid + 3 * texel)
        out = out.copy()
        c = out[..., :3]
        # прежняя кромка шире новой (зубцы) — снаружи, до TRIM_CLEAR: цвет кромки → ближайший пиксель ткани
        from scipy import ndimage as ndi
        # за кромкой (до TRIM_CLEAR) — прежний перенос (растянутая кромка) → ровный цвет ткани (self.body; у формы с
        # кокеткой YokePaint там уже перекрасил — body = None). Раньше — копия ближайшего пикселя дальше: от неё
        # шли полосы «бахромой» (пользователь, 19.10: «вот тут прям говно»)
        if self.body is not None:
            lim = wid + TRIM_CLEAR
            if self.clear_to is not None:                 # у ступеньки мыса (DET выезд, 22.10: красная чёрточка за
                lim = np.maximum(lim, np.interp(np.abs(TH), *self.clear_to))   # углом) кромка источника шире 8 мм зачистки
            if isinstance(self.body, tuple):              # по углу (trim_clear = "angle"): (углы, цвета [n, 3])
                ang, cols = self.body
                bpx = np.stack([np.interp(TH, ang, cols[:, k], period=360) for k in range(3)], axis=-1)
                # только остатки кромки — пиксели ближе к цвету кромки, чем к ткани за ней: вторая полоса и ткань — как
                # перенеслись (у NHL 27 CHI полоса кончается наискосок, сужаясь с 80° к 70°; замена всего, что не цвета
                # угла, рвала этот скос — CHI, сборка 2: красный зазор и белый обрывок на 78°)
                near_trim = np.linalg.norm(c - self.color[None, None], axis=-1) < np.linalg.norm(c - bpx, axis=-1)
                bad = m & msk & ~B & (D > wid) & (D < lim) & near_trim & (np.linalg.norm(c - bpx, axis=-1) > 20)
                c = c.copy()
                c[bad] = bpx[bad]
            else:
                bad = m & msk & ~B & (D > wid) & (D < lim) &                 (np.linalg.norm(c - self.body[None, None], axis=-1) > 20)
                c = c.copy()
                c[bad] = self.body
        if self.lining is not None:                       # подворот ниже кромки — ровной подкладкой (были пятна)
            c = c.copy()
            c[m & msk & B] = self.lining
        pc = getattr(self, "panel_c", None)
        if a_in is not None and pc is not None:         # вставка — цветом ткани: у источника полоса кончается не там, где
            c = c * (1 - a_in[..., None]) + pc[None, None] * a_in[..., None]   # у шаблона (VGK выезд, 22.10:
            zone = zone | (msk & (a_in > 0))            # чёрный хвост полосы во вставке и ступенька у её края)
        new = c * (1 - cov[..., None]) + self.color[None, None] * cov[..., None]
        bc = getattr(self, "band_col", None)
        if bc is not None:                              # двухцветный ворот (collar_band, UTA выезд): поверх кромки во
            PP = self._P[(Hs, Ws)]                       # весь V — полоса шаблона своим цветом, кроме вставки со щитом
            a_tr = trap_cover(PP, m & ~B & (PP[..., 2] > 0.03), self.trap, texel) if self.trap is not None else 0.0
            cov_b = np.clip(0.5 + (band_w(TH) - D) / G, 0, 1) * (1 - a_tr)
            cov_b = np.where(B, (D < TRIM_INNER).astype(float), cov_b)   # на подвороте у края — цветом полосы
            new = new * (1 - cov_b[..., None]) + bc[None, None] * cov_b[..., None]
        if bc is not None and getattr(self, "band_back", False):   # collar_band = "back": спереди кромки нет —
            zone = zone | (m & msk & (D < band_w(TH) + 3 * texel))  # полоса у края красится по своей ширине
        out[..., :3] = np.where((zone | (m & msk & B))[..., None], new, c)
        return out


COLLAR_LAPEL_KITS = None           # профиль collar_lapel = { форма = "source" }: лацканы только у этих форм (NYI, 22.10)
COLLAR_LAPEL = None                # профиль collar_lapel = "source" (22.10, MTL, DAL): ворот со шнуровкой (крой MIN), но
#                                    между кромкой и швом обода — лацканы другого цвета (у MTL и DAL — белые; у MIN — цвета
#                                    ткани). Рисует LapelPaint: от края до шва обода (ring_field; у середины — от верха
#                                    планки S), поверх — кромка (TrimPaint) и вставка (InsertPaint): края цветов — по швам
LAPEL_SRC = ((50.0, 150.0), (0.020, 0.026))   # |θ|°, м от края ворота (сетка NHL 24): замер цвета лацкана у источника —
#                                    между кромкой (MTL 1 см, DAL сзади до 1,8) и ободом (3 см), сбоку и сзади


class LapelPaint:
    """pre-правка основы (collar_lapel): лацканы — от края ворота до шва обода (ring_field: по |θ| от верха планки S)
    цветом источника, край у обода сглажен по текселю; кромку и вставку рисуют потом TrimPaint и InsertPaint (их края —
    тоже по швам: вставка поверх лацкана — без каймы прежнего цвета). Подворот не трогается."""

    def __init__(self, mesh, color, yoke=None, body=None, fabric=None):
        self.mesh, self.color = mesh, np.asarray(color, np.float64)
        self.yoke, self.body = yoke, body                # у формы с кокеткой — её цвет и ткань (островки у концов)
        self.fabric = fabric                             # ткань за лацканом (lapel_clean): у кокетки — body, иначе за ободом

    def clean(self, out, msk, G, R, cov):
        """lapel_clean (22.10, агент review-a, MTL и DAL дом): перенос лацкана источника за краем LapelPaint — тканью.
        LapelPaint только докрашивает лацкан до своего края, а белый лацкан источника после переноса ложится на сетку Edge
        иначе: у угла вставки он на 5 мм ниже угла (1,624 при угле 1,629) и вдоль нижнего края на 2–5 мм ниже шва — конец
        лацкана выходил тупым «сапожком» с вертикальным срезом по боку вставки (у NHL 27 — острый угол в угол вставки), край
        цвета — не по шву. Перекрашиваются цвет лацкана и его смесь с тканью (ближе LAPEL_CLEAN_TOL к отрезку «ткань —
        лацкан», доля лацкана от INSERT_BLEND_T) спереди у концов лацканов: |θ| < LAPEL_CLEAN_TH, не дальше LAPEL_CLEAN_D
        за краем лацкана, выше угла вставки − LAPEL_CLEAN_DY (ниже — планка и шнурки), у середины — только у угла вставки
        (там щит и вставка). И под концом лацкана (ниже угла вставки на LAPEL_CLEAN_DY, |x| от угла − 5 мм до
        LAPEL_TIP_X за ним) — всё не цвета ткани: там у NHL 27 только ткань, вставку InsertPaint рисует потом поверх (сборка 1
        DAL дом: тёмная вертикальная черта 7 мм под углом — смесь ткани с чёрной вставкой источника). Лацкан цвета ткани
        (выезды MTL, DAL — белые на белом) — ничего."""
        fab = np.asarray(self.fabric, np.float64)
        if np.abs(self.color - fab).max() < 45:
            return out
        m, D, B, P, TH = G["m"], G["D"], G["B"], G["P"], G["TH"]
        ok = np.isfinite(R)
        y_c, x_c = INSERT_CORNER
        c = out[..., :3]
        sg = self.color - fab
        ts = np.clip(((c - fab) * sg).sum(-1) / (sg * sg).sum(), 0, 1)
        lapish = (np.linalg.norm(c - (fab + ts[..., None] * sg), axis=-1) < LAPEL_CLEAN_TOL) & (ts > INSERT_BLEND_T)
        front = m & msk & ~B & (P[..., 2] > 0.03)
        zone = (front & (np.abs(TH) < LAPEL_CLEAN_TH)
                & (D < np.where(ok, R, LAPEL_CENTER_D) + LAPEL_CLEAN_D) & (P[..., 1] > y_c - LAPEL_CLEAN_DY)
                & (ok | (np.abs(P[..., 0]) > x_c - 0.003)) & lapish & (cov < 0.98))
        ax = np.abs(P[..., 0])
        under = (front & (P[..., 1] < y_c) & (P[..., 1] > y_c - LAPEL_CLEAN_DY) & (ax > x_c - 0.005)
                 & (ax < x_c + LAPEL_TIP_X) & (cov < 0.02) & (np.abs(c - fab).max(-1) > LAPEL_CLEAN_TOL))
        zone |= under
        out[..., :3] = np.where(zone[..., None], fab[None, None], c)
        print(f"  лацканы (lapel_clean): перенос лацкана за краем у концов — {int(zone.sum())} текселей → ткань "
              f"{np.round(fab).astype(int).tolist()}")
        return out

    def __call__(self, out, msk):
        from scipy import ndimage as ndi
        Hs, Ws = msk.shape
        G = relief_geometry(self.mesh, Hs)
        m, D, B, P, TH = G["m"], G["D"], G["B"], G["P"], G["TH"]
        R, _, _ = ring_field(G)
        ok = np.isfinite(R)
        texel = px_size(D, m & ~B)
        # у середины (|θ| меньше верха планки S, обода нет) — тоже лацкан, снизу его режет угол вставки (ниже), внутри —
        # вставка (InsertPaint поверх): иначе край лацкана шёл по лучу θ_S лесенкой (без сглаживания)
        cov = np.clip(0.5 + (np.where(ok, R, LAPEL_CENTER_D) - D) / texel, 0, 1)
        # конец лацкана — у самого широкого угла вставки (INSERT_HW, 1,629 м): ниже шов обода идёт к верху планки S — это
        # уже планка (у NHL 27 MTL цвета ткани; сборка 2 MTL дом: белая ступенька у углов вставки)
        y_c, x_c = INSERT_CORNER
        gy = px_size(P[..., 1], m)
        tip = (P[..., 2] > 0.03) & (np.abs(P[..., 0]) < x_c + LAPEL_TIP_X)
        cov = np.where(tip, cov * np.clip(0.5 + (P[..., 1] - y_c) / gy, 0, 1), cov)
        cov = np.where(m & msk & ~B, cov, 0.0)
        self.last_cov = cov                              # для InsertPaint: лацкан цвета вставки не «прежний перенос»
        out = out.copy()
        if LAPEL_CLEAN and self.fabric is not None:      # перенос лацкана за краем — тканью (MTL, DAL дом)
            out = self.clean(out, msk, G, R, cov)
        out[..., :3] = out[..., :3] * (1 - cov[..., None]) + self.color[None, None] * cov[..., None]
        if self.yoke is not None:                        # кокетка у конца лацкана (MTL выезд, сборка 1: красные точки у
            # углов вставки): между швом обода (он у планки уходит вниз, к S) и краем кокетки — клин тоньше 2–3 текселей,
            # на развёртке 1024 он рвётся в точки. Тонкое (открытие маски) и мелкие части цвета кокетки у ворота спереди,
            # у концов лацканов (|θ| < LAPEL_TIP_TH), — тканью
            zone_t = m & msk & ~B & (P[..., 2] > 0.03) & (np.abs(TH) < LAPEL_TIP_TH) & (D < 0.08) & ok
            #                                              (ok — где лацкан: середина между ними — вставка, у DAL выезда
            #                                              она цвета кокетки — её не трогать)
            yk = m & msk & ~B & (np.linalg.norm(out[..., :3] - np.asarray(self.yoke)[None, None], axis=-1) < 60)
            it = max(1, int(round(Hs / 1024.0)))         # открытие — по всей кокетке (обрезка зоной дала бы тонкие
            thin = yk & ~ndi.binary_opening(yk, structure=np.ones((3, 3), bool), iterations=it)   # края), правка — в зоне
            lab, n = ndi.label(yk & ~thin, structure=np.ones((3, 3), bool))
            size = np.bincount(lab.ravel())
            small = size < LAPEL_ISLAND_PX * (Hs / 1024.0) ** 2
            small[0] = False
            fix = (thin | small[lab]) & zone_t
            out[..., :3] = np.where(fix[..., None], np.asarray(self.body)[None, None], out[..., :3])
            if fix.any():
                print(f"  лацканы: тонкий клин и островки кокетки у концов лацканов — {int(fix.sum())} текселей → ткань")
        return out


LAPEL_ISLAND_PX = 300              # текселей (1024²): часть цвета кокетки у ворота меньше — островок, не кокетка
LAPEL_TIP_TH = 40.0                # град: у концов лацканов (|θ| меньше) — тонкий клин кокетки убирается
LAPEL_TIP_X = 0.02                 # м за углом вставки (|x|): до сюда лацкан кончается на высоте угла (ниже — планка)
LAPEL_CENTER_D = 0.06              # м от края: у середины переда (обода нет) лацкан — до угла вставки (режет LAPEL_TIP_X)
LAPEL_YOKE_GAP = 0.003             # м: край кокетки у концов лацканов — выше среза лацкана на столько (без черты на стыке)
LAPEL_TRIM_TH = 26.0               # град: у лацканов ширина кромки ближе к середине — как здесь (там вставка, у DAL дома — тоже
#                                    чёрная: замер «сплошной полосой» давал 5 см и с ±25° сглаживания — кромку на лацканах)
LAPEL_CLEAN = False                # профиль lapel_clean = true (22.10, MTL, DAL): перенос лацкана за краем LapelPaint — тканью
LAPEL_CLEAN_TH = 50.0              # град: зона чистки — концы лацканов спереди (|θ| меньше; дальше перенос и край совпадают)
LAPEL_CLEAN_D = 0.012              # м за краем лацкана (ring_field; у середины — LAPEL_CENTER_D): перенос шёл ниже на 2–5 мм
LAPEL_CLEAN_DY = 0.010             # м ниже угла вставки — не ниже (там планка и белые шнурки)
LAPEL_CLEAN_TOL = 30.0             # |ΔRGB| до отрезка «ткань — лацкан»: смесь (сглаженный край переноса)


def lapel_trim_band(lapel, trim):
    """Лацканы цвета кромки (22.10, NYI выезд — синие, кромки другого цвета у края нет): замер кромки «сплошной полосой»
    брал весь лацкан (4,4 см у вставки), и у середины переда кромка шла ниже угла вставки — синий хвостик под её нижним
    краем (лацкан там срезан, LapelPaint). Тогда кромка — только полоса у края (BAND_KNOTS), лацкан — LapelPaint (края по
    швам), шва рельефа по краю кромки нет (у NHL 27 его нет: лацкан и полоса — один цвет). У MTL, DAL (белые лацканы,
    кромка синяя / чёрная) — как было."""
    if lapel is None or trim is None:
        return
    if np.abs(np.asarray(lapel.color, np.float64) - np.asarray(trim.color, np.float64)).max() >= LAPEL_SAME_COLOR:
        return
    f_, w_ = trim.width
    trim.width = (f_, np.minimum(w_, band_w(f_)))
    trim.no_seam = True
    print("  лацканы цвета кромки: кромка — полоса у края (BAND_KNOTS), без шва по её краю")


LAPEL_SAME_COLOR = 45.0            # max |ΔRGB|: лацкан и кромка одного цвета (lapel_trim_band)


def lapel_rule(code, kit, mesh, yoke=None, body=None):
    """LapelPaint: цвет лацкана — медиана основы источника (без нашивок) в LAPEL_SRC (сетка NHL 24, наружная оболочка,
    расстояние — от края ворота, как у trim_rule). Цвет тот же, что за ободом (4,5–6 см), — лацканов нет (None)."""
    from scipy.sparse.csgraph import connected_components
    n24 = kit3d.load_nhl24()
    bfn = J.n24_tex(Hy.CLUB_NAME[code], kit, "base_color")
    src = kit3d.load_tex(bfn)[..., :3] if os.path.exists(bfn) else Hy.clean_color(code, kit)
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
    th = np.abs(Hy.theta_of(P, zc))
    c = src[ys, xs]
    (a0, a1), (d0, d1) = LAPEL_SRC
    sel = (th > a0) & (th < a1)
    lap = np.median(c[sel & (d > d0) & (d < d1)], axis=0)
    beyond = np.median(c[sel & (d > 0.045) & (d < 0.06)], axis=0)
    print("  лацканы (collar_lapel): цвет", np.round(lap).astype(int).tolist(), "— за ободом",
          np.round(beyond).astype(int).tolist())
    if np.abs(lap - beyond).max() < 45:
        print("  лацканы цвета ткани за ободом — не рисуются")
        return None
    return LapelPaint(mesh, lap, yoke, body, fabric=body if body is not None else beyond)


TRIM_WIDTH_FROM = {}               # профиль trim_width_from: форма → форма клуба, по чьей кромке мерить ширину. Нужен,
#                                    когда кромка цвета ткани (BOS дом, 21.10: чёрная на чёрном) — замер по цвету давал
#                                    3,7 см (вся ткань «кромка»): шов рельефа там же, щит по зазору — на 2 см ниже. Нет
#                                    поля — как было


def trim_rule(code, kit, mesh, with_yoke=False):
    """TrimPaint: цвет кромки — медиана у края ворота NHL 24, ширина по углу — замер на NHL 24, сглажено, × TRIM_K
    (у формы из TRIM_WIDTH_FROM — по кромке другой формы клуба)."""
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
    band_col = None
    if COLLAR_BAND.get(kit):                             # двухцветный ворот (UTA выезд): у края — полоса своего цвета,
        band_col = col                                   # за ней — кромка во весь V / обод
        col = np.median(c[(d > COLLAR_BAND_D[0]) & (d < COLLAR_BAND_D[1]) & (np.abs(th) > 60)], axis=0)
        print(f"  двухцветный ворот (collar_band): полоса {np.round(band_col).tolist()}, кромка во весь V "
              f"{np.round(col).tolist()}")
    two_tone = (lambda cc: (np.linalg.norm(cc - col, axis=1) < 60) |
                ((np.linalg.norm(cc - band_col, axis=1) < 60) & (d < COLLAR_BAND_D[0]))) if band_col is not None else None
    wkit = None if band_col is not None else TRIM_WIDTH_FROM.get(kit)
    if two_tone is not None:                             # полоса и кромка — одной сплошной от края
        is_trim = two_tone(c)
    elif wkit:                                           # кромка цвета ткани: ширина — по кромке другой формы клуба
        cw = Hy.clean_color(code, wkit)[ys, xs]
        is_trim = np.linalg.norm(cw - np.median(cw[near], axis=0), axis=1) < 60
        print(f"  кромка цвета ткани: ширина — по форме {wkit} (trim_width_from), цвет — свой")
    else:
        is_trim = np.linalg.norm(c - col, axis=1) < 60
    prof = trim_profile(d, th, is_trim, TRIM_STEP_FROM)
    back = COLLAR_BAND.get(kit) == "back"                # collar_band = "back" (TOR дом): второй цвет — только сзади от
    if back:                                             # ступеньки до обода; цвет — по широкой части
        col = np.median(c[(d > COLLAR_BAND_D[0]) & (d < COLLAR_BAND_D[1]) & (np.abs(th) >= COLLAR_BAND_BACK_TH)], axis=0)
        if not prof["step"]:                             # ступенька — где ширина за серединой узкой и широкой части
            k_ = (prof["angles"] > prof["gap"]) & (prof["width"] > (prof["narrow"] + prof["wide"]) / 2)
            if not k_.any():
                sys.exit(f"[{code}] collar_band = \"back\" ({kit}): у источника нет широкой части сзади")
            prof = dict(prof, step=True, step_at=float(prof["angles"][k_][0]))
    mode = COLLAR_TRIM if COLLAR_TRIM != "auto" else ("step" if prof["step"] else "smooth")
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
    wf = wf * TRIM_K
    if TRIM_MEASURE == "contiguous" and mode != "step":   # сплошная полоса от края по углу (trim_profile), как у источника:
        # по основе без нашивок (base_color): в clean_color щит у середины стёрт вместе с кромкой под ним (у DET мыс
        # обрывался на 1,3 см вместо 5,9)
        bfn = J.n24_tex(Hy.CLUB_NAME[code], kit, "base_color")
        if os.path.exists(bfn):
            bt = kit3d.load_tex(bfn, src.shape[0])[..., :3]
            cb = bt[ys, xs]
            prof_b = trim_profile(d, th, two_tone(cb) if two_tone is not None else
                                  np.linalg.norm(cb - np.median(cb[near], axis=0), axis=1) < 60)
        else:
            prof_b = prof
        a_, w_ = prof_b["angles"], prof_b["width"].copy()   # у DET спереди мыс 5,9 см, по бокам и сзади 3 см; старый
        nz = np.nonzero(w_ > 0.003)[0]                    # (95-й процентиль цвета кромки в 3 см) — 3,7 по кругу
        if len(nz):
            w_[: nz[0]] = w_[nz[0]]                       # «разрыв» у середины (вырез adidas у сетки NHL 24) — соседним
            if COLLAR_LAPEL:                              # лацканы (DAL дом, 22.10): у середины — вставка цвета кромки
                w_[a_ < LAPEL_TRIM_TH] = np.interp(LAPEL_TRIM_TH, a_, w_)   # (чёрная, до 5 см) — не кромка: сглаженная
                #                                           ±25° ширина тянула кромку на лацканы у вставки («чёрный нагрудник»)
            wf_ = np.interp(np.abs(full), a_, w_)
            k_ = int(TRIM_SMOOTH)
            ker = np.exp(-0.5 * (np.arange(-2 * k_, 2 * k_ + 1) / k_) ** 2)
            ker /= ker.sum()
            wf_ = np.convolve(np.concatenate([wf_[-2 * k_:], wf_, wf_[:2 * k_]]), ker, mode="valid")
            wf = wf_ + np.minimum(wf_ * (TRIM_K - 1), TRIM_K_MAX_ADD)   # узкой — «чуть шире» (TRIM_K), широкой — нет
    # кромка не шире шва обода (пользователь, 21.10, TBL: «не шире обода»; 22.10, DET: у широкой кромки выезда старый
    # замер давал 3,7 см при ободе 3,0) — там, где обод есть (у ворота без шнуровки — с RING_PLAIN_TH, спереди мыс
    # кромки не ограничен). У узких кромок (MIN, NJD — до 1,3 см) ничего не меняется
    ring_w = np.interp(np.abs(full), *zip(*RING_KNOTS))
    if COLLAR != "lace":
        ring_w = np.where(np.abs(full) >= RING_PLAIN_TH, ring_w, np.inf)
    wf = np.minimum(wf, ring_w)
    if mode == "step":
        full, wf = step_width(prof)
        print(f"  кромка ступенькой ({COLLAR_TRIM}): узкая {prof['narrow'] * 100:.2f} см "
              f"× {TRIM_K}, ступенька {prof['step_at']:.0f}°, сзади — до обода (RING_KNOTS)")
    if back:                                             # collar_band = "back": кромка — только широкая часть ступеньки
        full, wf = step_width(dict(prof, narrow=0.0))
        print(f"  двухцветный ворот сзади (collar_band = back): полоса у края {np.round(band_col).astype(int).tolist()} "
              f"(BAND_KNOTS) по кругу, с {prof['step_at']:.0f}° до обода — {np.round(col).astype(int).tolist()}")
    trap = None
    if COLLAR_PANEL and COLLAR != "lace":                # шаблон ворота: край кромки — на шов (полоса или V/обод)
        PE, DE, THE, frontE = edge_collar_geo(mesh)
        pth, pd, thJ = panel_v(PE, DE, THE, frontE)
        a_full = np.abs(full)
        outer = np.where(a_full < thJ, np.interp(a_full, pth, pd), np.interp(a_full, *zip(*RING_KNOTS)))
        band = band_w(full)
        if COLLAR_TRIM == "half":                        # половинчатый: полоса спереди, скос на HALF_STEP_AT, сзади — обод
            sm_ = np.clip(0.5 + (a_full - HALF_STEP_AT) / (2 * TRIM_STEP_SOFT), 0, 1)
            wf = band + (outer - band) * sm_
        else:
            wf = np.where(wf < (band + outer) / 2, band, outer)
        trap = trap_geometry(PE, DE, THE, frontE)
        print(f"  кромка по шаблону ворота: полоса {band.max() * 100:.2f}–{band.min() * 100:.2f} см, V — острие "
              f"{PANEL_TIP_Y} м, до {thJ:.0f}°, дальше обод; вставка — y {trap[0]:.3f}…{trap[1]:.3f}")
    print("  кромка: цвет", np.round(col).tolist(), "ширина, см:",
          {int(a): round(float(np.interp(a, full, wf, period=360)) * 100, 2) for a in (0, 45, 90, 135, 180)})
    tl, bl = kit3d.raster_uv(n24, src.shape[0])
    yl, xl = np.nonzero(tl >= 0)
    lin_t = comp[w.g[n24["tri"][tl[yl, xl], 0]]] != main
    lining = np.median(src[yl[lin_t], xl[lin_t]], axis=0)
    if COLLAR_LINING == "trim":                          # подворот — цветом кромки (VGK, 22.10: «воротник, как у выездной
        lining = col                                     # LAK» — у VGK подворот NHL 27 серый, у полосы выходила вторая
        print("  подворот ворота — цветом кромки (collar_lining)")   # полоска и двухцветный срез у вставки)
    # ткань у ворота (под кромкой, сзади и с боков): у формы без кокетки — одним цветом
    body_c = np.median(c[(d > 0.02) & (d < 0.035) & (np.abs(np.abs(th) - 120) < 40)], axis=0)
    wide = mode == "step" or (TRIM_MEASURE == "contiguous" and float(np.max(wf)) > 0.02)
    if wide:                                             # у широкой кромки (TBL сзади 2,9 см, DET выезд 3,0) на 2–3,5 см —
        pr = prof if mode == "step" else prof_b          # сама кромка: «ткань» была её цветом, и зачистка за кромкой
        wloc = np.interp(np.abs(th), pr["angles"], pr["width"])   # (TRIM_CLEAR) красила ещё 8 мм — у TBL белым
        body_c = np.median(c[(d > 0.06) & (d < 0.10) & (np.abs(th) > 140)], axis=0)
        #                                                  (21.10: «сзади широкий»), у DET выезда — красным за швом;
        #                                                  мера — спина в 6–10 см от ворота: сбоку у VGK серый рукав,
        #                                                  за кромкой — серая полоса NHL 27 (22.10: «внешняя полоска»)
        #                                                  обода (пользователь, 22.10: «красная обводка за швами»)
    clear_to = (pr["angles"], pr["width"] + TRIM_CLEAR) if wide else None
    panel_c = None
    if trap is not None:                                 # вставка — цветом груди под острием V (сбоку у ворота бывает
        fr_ = (P[:, 2] > 0.03) & (np.abs(P[:, 0]) < 0.03) & (P[:, 1] > 1.57) & (P[:, 1] < 1.595)   # рукав: VGK выезд
        panel_c = np.median(c[fr_], axis=0) if fr_.any() else body_c                               # — серый, 22.10)
        bfn_p = J.n24_tex(Hy.CLUB_NAME[code], kit, "base_color")
        if with_yoke and os.path.exists(bfn_p):          # у формы с кокеткой вставка — мыс кокетки (BUF выезд, 22.10: под
            cbp = kit3d.load_tex(bfn_p, src.shape[0])[..., :3][ys, xs]   # острием V — белое, мыс со щитом — синий): цвет
            fin = (P[:, 2] > 0.03) & (np.abs(P[:, 0]) < 0.015) & (P[:, 1] > PANEL_TIP_Y + 0.006) & \
                (P[:, 1] < PANEL_TIP_Y + 0.016)                            # внутри V над острием, по основе (щита нет)
            if fin.any():
                panel_c = np.median(cbp[fin], axis=0)
                print("  вставка шаблона у формы с кокеткой — цвет внутри V:", np.round(panel_c).astype(int).tolist())
    body_arg = body_c
    if TRIM_CLEAR_MODE == "angle" and not with_yoke:     # ткань за кромкой — по углу, как у источника (CHI, 22.10)
        pw = prof_b if (TRIM_MEASURE == "contiguous" and mode != "step") else prof
        bfn_ = J.n24_tex(Hy.CLUB_NAME[code], kit, "base_color")
        cb_ = kit3d.load_tex(bfn_, src.shape[0])[..., :3][ys, xs] if os.path.exists(bfn_) else c
        got = trim_body_by_angle(d, th, cb_, full, wf, (pw["angles"], pw["width"]), col, body_c)
        if got is not None:
            body_arg = got
            print("  зачистка за кромкой — по углу (trim_clear):", {a: [int(round(float(np.interp(
                a, got[0], got[1][:, k], period=360)))) for k in range(3)] for a in (0, 45, 90, 135, 180)})
    # лацканы (collar_lapel): от края до шва обода уже закрашены LapelPaint — зачистка за кромкой не нужна (её «ткань
    # у ворота» — цвет лацкана или ткани, смотря где мерить)
    tp = TrimPaint(mesh, col, (full, wf), lining, None if (with_yoke or COLLAR_LAPEL) else body_arg, clear_to, trap)
    tp.panel_c = panel_c
    tp.band_back = back                                  # collar_band = "back": спереди — одна полоса у края
    tp.band_col = band_col                               # двухцветный ворот (collar_band): полоса у края своим цветом
    tp.band_frame = COLLAR_BAND.get(kit) == "frame"      # "frame" — как "full", но вставка со щитом цветом ткани (NSH дом)
    return tp


def trim_body_by_angle(d, th, c, full, wf, w_src, trim_col=None, body_c=None):
    """Ткань сразу за кромкой — по углу (профиль trim_clear = "angle"): медиана источника (сетка NHL 24, основа без
    нашивок) от TRIM_CLEAR_GAP за кромкой (нашей wf или источника w_src — что шире) и на TRIM_CLEAR дальше, в
    ±TRIM_CLEAR_WIN°. CHI (22.10): сбоку и сзади — вторая полоса до шва обода (белая / красная), спереди — ткань.
    Цвет кромки (trim_col) за кромкой — не ткань: там кромка источника шире шва шаблона (UTA выезд, 22.10: голубой V
    у ±38–43° — до 3,9 см при шве 3,1; голубые зубцы за швом оставались) — вместо него body_c. ->
    (углы full, цвета [len(full), 3]) или None; угол без замера — по соседним."""
    near = d < 0.08
    d, th, c = d[near], th[near], c[near]
    cols = np.full((len(full), 3), np.nan)
    for i, a in enumerate(full):
        w0 = max(float(wf[i]), float(np.interp(abs(a), *w_src))) + TRIM_CLEAR_GAP
        s = (np.abs(((th - a) + 180) % 360 - 180) < TRIM_CLEAR_WIN) & (d > w0) & (d < w0 + TRIM_CLEAR)
        if s.sum() >= 10:
            cols[i] = np.median(c[s], axis=0)
    ok = ~np.isnan(cols[:, 0])
    if not ok.any():
        return None
    for k in range(3):
        cols[:, k] = np.interp(full, full[ok], cols[ok, k], period=360)
    if trim_col is not None and body_c is not None:
        own = np.linalg.norm(cols - np.asarray(trim_col, np.float64), axis=1) < 60
        cols[own] = body_c
    return np.asarray(full, dtype=np.float64), cols


def trim_profile(d, th, is_trim, skip=0.0):
    """Ширина кромки источника по углу от середины переда (|θ|, шаг 1°): сплошная полоса цвета кромки от края ворота —
    до первого миллиметра, где кромки меньше половины (ткань того же цвета ниже кокетки, NJD дома, — не кромка), и
    её вид: разрыв спереди (до какого угла кромки нет), узкая и широкая части, угол ступеньки. skip — град: ближе к
    середине узкая часть и ступенька не ищутся (профиль trim_step_from: вставка шнуровки цвета кромки, NYI дом). -> dict."""
    a_ = np.arange(0, 181, 1.0)
    wd = np.zeros(len(a_))
    ath = np.abs(th)
    for i, a in enumerate(a_):
        r = (np.abs(ath - a) < 1.5) & (d < 0.06)
        if r.sum() < 10:
            continue
        mm = (d[r] / 0.001).astype(int)
        cnt = np.bincount(mm, minlength=60)
        hit = np.bincount(mm, weights=is_trim[r].astype(float), minlength=60)
        frac = np.where(cnt > 0, hit / np.maximum(cnt, 1), np.nan)
        k = 0
        while k < len(frac) and (np.isnan(frac[k]) or frac[k] >= 0.5):
            k += 1
        wd[i] = k * 0.001
    have = wd > 0.003
    gap = float(a_[np.argmax(have)]) if not have[0] and have.any() else 0.0
    g0 = max(gap, float(skip))
    narrow = float(np.median(wd[(a_ >= g0 + 3) & (a_ <= g0 + 30)]))
    wide = float(np.median(wd[a_ >= 150]))
    step = wide > 0.02 and wide >= TRIM_STEP_RATIO * max(narrow, 1e-4)
    at = float(a_[(a_ > g0) & (wd > (narrow + wide) / 2)][0]) if step else None
    return {"angles": a_, "width": wd, "gap": gap, "narrow": narrow, "wide": wide, "step": step, "step_at": at}


def step_width(prof):
    """Ширина кромки «ступенькой» по углу (−180…180, шаг 0,5°): в разрыве — 0, до ступеньки — узкая × TRIM_K, после —
    до шва обода (RING_KNOTS), переходы — TRIM_STEP_SOFT. -> (углы, ширина, м)."""
    full = np.arange(-180, 180, 0.5)
    a = np.abs(full)
    sm = lambda x: np.clip(0.5 + x / (2 * TRIM_STEP_SOFT), 0, 1)
    ring = np.interp(a, *zip(*RING_KNOTS))
    w = prof["narrow"] * TRIM_K + (ring - prof["narrow"] * TRIM_K) * sm(a - prof["step_at"])
    # разрыв спереди не рисуется: кромка — до середины (пользователь, 21.10: «белый доходит не до конца»); замер
    # «разрыва» у сетки NHL 24 ±24° выходит у всех клубов — это вырез adidas у середины, а не разрыв кромки
    return full, w


# ---------------------------------------------------------------- щит NHL по зазору под кромкой (21.10)
# Профиль shield_gap_mm (вместо shield_offset_cm): верх щита — на столько мм ниже низа кромки ворота посередине переда
# (та же мера, что «до кромки» у kitport check). Сдвиг щита по высоте считается до сборки — по геометрии кромки
# (TrimPaint) и посадке нашивки (kit_hybrid.plan_decals), без подбора пересборками (у TBL на подбор ушло 7 сборок по
# ~6 мин). По умолчанию (ворот без шнуровки, нет ни shield_gap_mm, ни shield_offset_cm) — SHIELD_GAP_DEFAULT_MM.
# "source" — зазор как у источника на его сетке: у NHL 27 кромки посередине переда нет (вырез adidas), щит — на 5,4 мм
# ниже края ворота у тёмных форм и на 6,8 мм у белых (замер 21.10: NJD, TBL, BOS; у белых больше — белый край щита на
# белой ткани не виден). Задан shield_offset_cm — как раньше.
# 4 мм — решение пользователя по NJD/TBL (21.10): у одобренных форм «до кромки» 3 мм (NJD) и 4–5 мм (TBL, после его
# «чуть пониже»); у источника больше (5,4–6,8 мм) — его зазор пользователь не взял.
SHIELD_GAP_DEFAULT_MM = 4.0
SHIELD_GAP_MM = None              # профиль shield_gap_mm: число, {форма: число} или "source"; None — shield_offset_cm
SHIELD_GAP_X_CM = 0.41             # x щита при расчёте по зазору — как у всех клубов (середина горловины NHL 24 левее оси)
SHIELD_GAP_COL = 0.003             # м: середина переда — |x| до стольких (как kitport check)
SHIELD_GAP_STEP = 0.0002           # м: шаг точек по высоте на середине переда
SHIELD_GAP_DY = (-0.04, 0.04)      # м: пределы сдвига щита по высоте (в 3D NHL 24) при подборе
SHIELD_H = 0.031                   # м: высота щита при масштабе 1 (0,68 → 2,1 см); щит на кромке — если на ней по высоте
SHIELD_ON_TRIM_PAD = 0.003         # хватает места на щит, зазор источника от края ворота и ещё столько (DET 22.10: у NHL 27
#                                    щит на красном мысе в 5,4 мм от края; «под кромкой» уводило его на 2 см вниз)
SHIELD_SILVER = (110, 40, 14)      # «серебро» щита, как у kitport check: яркость >, |R − G| <, max − min <
_SHIELD_GAP_LOG = {}               # форма → расчёт (в info.json и печать)


def front_column(mesh, y=(1.55, 1.70), col=SHIELD_GAP_COL, n=7, step=SHIELD_GAP_STEP):
    """Точки поверхности на середине переда: сечения плоскостями x = const (|x| ≤ col, n штук) через шаг step по
    длине. -> (P (N×3), UV (N×2), треугольник (N,)). Только перед (z > 0,05) и высоты y."""
    Pm, T, UVm = mesh["pos"], mesh["tri"], mesh["uv"]
    out_p, out_uv, out_t = [], [], []
    for x0 in np.linspace(-col, col, n):
        s = Pm[T][:, :, 0] - x0
        for t in np.nonzero((s.min(1) < 0) & (s.max(1) > 0))[0]:
            a, b, c = T[t]
            pts = []
            for i, j in ((a, b), (b, c), (c, a)):
                si, sj = Pm[i, 0] - x0, Pm[j, 0] - x0
                if (si < 0) != (sj < 0):
                    w = si / (si - sj)
                    pts.append((Pm[i] + w * (Pm[j] - Pm[i]), UVm[i] + w * (UVm[j] - UVm[i])))
            if len(pts) != 2:
                continue
            (p0, u0), (p1, u1) = pts
            k = max(int(np.ceil(np.linalg.norm(p1 - p0) / step)), 1)
            w = (np.arange(k) + 0.5)[:, None] / k
            out_p.append(p0 + w * (p1 - p0))
            out_uv.append(u0 + w * (u1 - u0))
            out_t.append(np.full(k, t))
    P, UV, Tt = np.concatenate(out_p), np.concatenate(out_uv), np.concatenate(out_t)
    keep = (P[:, 2] > 0.05) & (P[:, 1] > y[0]) & (P[:, 1] < y[1])
    return P[keep], UV[keep], Tt[keep]


def band_bottom(yy, in_band, lo=1.59):
    """Низ сплошной полосы сверху (как kitport check: окна 1 мм с шагом 0,25 мм, конец — первое окно, где полосы меньше
    половины). -> y низа (м)."""
    top = yy.max()
    b = top
    while b > lo:
        m = (yy <= b) & (yy > b - 0.001)
        if m.sum() >= 3 and in_band[m].mean() < 0.5:
            break
        b -= 0.00025
    above = in_band & (yy >= b)
    return float(yy[above].min()) if above.any() else float(top)


def trim_front_bottom(trim):
    """Низ кромки (TrimPaint) посередине переда нашей сетки, м — где его найдёт kitport check: по сечениям |x| ≤ 3 мм
    точки, которые кромка красит (D < ширины; на подвороте — D < TRIM_INNER), сплошной полосой от верха."""
    w = Hy.Welded(trim.mesh)
    ring = w.neck()
    zc = float(w.P[ring, 2].mean())
    band, lip = Hy.edge_layers(w, ring, zc)
    fold = Hy.fold_polyline(w, band)
    edge = Hy.smooth_curve(fold if fold is not None else Hy.lip_polyline(lip), zc, win=2.0)
    P, _, Tt = front_column(trim.mesh)
    D = Hy.ring_dist(P, edge)
    th_w, w_w = trim.width
    wid = np.interp(Hy.theta_of(P, zc), th_w, w_w, period=360)
    if getattr(trim, "band_back", False):                # collar_band = "back": спереди — полоса у края
        wid = np.maximum(wid, band_w(Hy.theta_of(P, zc)))
    B = band[w.g[trim.mesh["tri"][Tt]]].all(1)
    in_trim = np.where(B, (D < TRIM_INNER) & (wid > 1e-4), D < wid)
    return band_bottom(P[:, 1], in_trim), float(P[:, 1].max())


def source_shield_gap(M, col, base):
    """Зазор «кромка → щит» у источника посередине переда на его сетке (M — наружная оболочка NHL 24, col / base —
    готовый свитер и основа без нашивок, H×W×3). Кромка — сплошная полоса цвета верха основы; если её нет (у NHL 27
    посередине — вырез adidas, ткань до края) или щит стоит внутри неё (мыс кокетки NJD) — от края ворота.
    -> {edge, trim_bottom, shield_top, ref, gap_mm}."""
    P, UV, _ = front_column(M)
    yy = P[:, 1]
    S = col.shape[0]
    c = kit3d.sample_bilinear(col.astype(np.float64), UV[:, 0], UV[:, 1])[:, :3]
    b = kit3d.sample_bilinear(base.astype(np.float64), UV[:, 0], UV[:, 1])[:, :3]
    top = float(yy.max())
    trim_c = np.median(b[yy > top - 0.002], 0)
    body = np.median(b[(yy > 1.56) & (yy < 1.58)], 0)
    in_trim = np.abs(b - trim_c).max(1) < 45
    tb = band_bottom(yy, in_trim, lo=1.56) if np.abs(trim_c - body).max() >= 45 else top
    patch = (np.abs(c - b).max(1) > 20) & (yy < top - 0.001) & (yy > 1.58)
    sh_top = float(yy[patch].max()) if patch.any() else None
    ref = tb if sh_top is not None and tb > sh_top else top
    return {"edge": round(top, 4), "trim_bottom": round(tb, 4), "shield_top": sh_top and round(sh_top, 4),
            "ref": "кромки" if ref == tb and tb != top else "края ворота",
            "gap_mm": round((ref - sh_top) * 1000, 1) if sh_top is not None else None, "size": S}


def source_gap_for(code, kit):
    """Зазор щита у источника этой формы (выгрузка клуба, source_kits) → мм."""
    n24 = Hy.outer_shell(kit3d.load_nhl24())
    col = kit3d.load_tex(J.n24_tex(Hy.CLUB_NAME[code], kit, "color"))[..., :3]
    base = kit3d.load_tex(J.n24_tex(Hy.CLUB_NAME[code], kit, "base_color"))[..., :3]
    r = source_shield_gap(n24, col, base)
    if r["gap_mm"] is None:
        sys.exit(f"{code} {kit}: щит у источника не найден — задайте shield_gap_mm или shield_offset_cm в профиле")
    return r


def shield_gap_target(code, kit):
    """Зазор (мм) для формы по профилю: число, {форма: число} или "source" (замер источника). -> (мм, откуда)."""
    g = SHIELD_GAP_MM
    if isinstance(g, dict):
        g = g.get(kit, "source")
    if g == "source":
        r = source_gap_for(code, kit)
        return float(r["gap_mm"]), f"замер источника ({r['ref']} {r['edge'] if r['ref'] == 'края ворота' else r['trim_bottom']}"\
                                    f" м, щит {r['shield_top']} м)"
    return float(g), ("SHIELD_GAP_DEFAULT_MM" if g is SHIELD_GAP_DEFAULT_MM else "профиль shield_gap_mm")


def shield_frame(pl, src, dst, tid24, dy):
    """Посадка щита (как kit_hybrid.plan_decals) со сдвигом центра на NHL 24: x — SHIELD_GAP_X_CM, y — dy (м).
    -> (кадр _frame, p NHL 24, cL)."""
    from . import kit_hybrid
    cL0, nL0, pinv0, R, sc, rad, u_c, v_c = pl["_frame"]
    _, p, Jm, n = kit_hybrid.tri_frame(src, tid24, u_c, v_c)
    p = p + np.array([SHIELD_GAP_X_CM / 100.0, dy, 0.0])
    lt, lb, _ = kit3d.project(p[None], n[None], dst, k=32)
    T = dst["tri"][lt[0]]
    cL = lb[0] @ dst["pos"][T]
    nL = kit3d._unit(lb[0] @ dst["nrm"][T])
    JL = Jm - np.outer(nL, nL @ Jm)
    return (cL, nL, np.linalg.pinv(JL), R, sc, rad, u_c, v_c), p, cL


def shield_top_on(P, frame, soft, comp):
    """Верх щита на точках P нашей сетки (середина переда): куда наклейка кладёт «серебро» (как рисует decal_post и
    меряет kitport check). -> y (м) или None."""
    cL, nL, pinv, R, sc, rad, u_c, v_c = frame
    d = P - cL
    duv = ((d @ pinv.T) / sc) @ R.T
    uu, vv = u_c + duv[:, 0], v_c + duv[:, 1]
    a = kit3d.sample_bilinear(soft[..., None], uu, vv)[:, 0]
    col = kit3d.sample_bilinear(comp[..., :3].astype(np.float64), uu, vv)
    lum_min, rg, spread = SHIELD_SILVER
    sil = (a > 0.5) & (col.mean(1) > lum_min) & (np.abs(col[:, 0] - col[:, 1]) < rg) & (col.max(1) - col.min(1) < spread)
    sil &= (np.linalg.norm(d, axis=1) < rad) & (np.abs(d @ nL) < 0.06)
    return float(P[sil, 1].max()) if sil.any() else None


def fit_shield_gap(placed, soft, comp, src, dst, tid24, trim, code, kit):
    """Щит (placed «neck_shield») — по высоте так, чтобы его верх был на зазор ниже низа кромки (trim_front_bottom).
    Подбор — делением отрезка SHIELD_GAP_DY по расчёту, без сборки. Меняет placed на месте."""
    pl = next((p for p in placed if p["name"] == "neck_shield"), None)
    if pl is None or trim is None:
        return None
    if SHIELD_GAP_MM == "panel":                         # шаблон ворота: верх щита — над острием V, как у NHL 27
        target = PANEL_TIP_Y + SHIELD_PANEL_TOP
        gap_mm, why, edge_y = 0.0, f"шаблон ворота: верх на {SHIELD_PANEL_TOP * 100:.1f} см над острием V", target
    else:
        gap_mm, why = shield_gap_target(code, kit)
        edge_y, top_y = trim_front_bottom(trim)
        target = edge_y - gap_mm / 1000.0
    if SHIELD_GAP_MM is SHIELD_GAP_DEFAULT_MM or SHIELD_GAP_MM == "source":
        r = source_gap_for(code, kit)                     # широкая кромка: щит на ней, как у источника
        need = SHIELD_H * SHIELD_SCALE + r["gap_mm"] / 1000.0 + SHIELD_ON_TRIM_PAD
        wid0 = float(np.interp(0.0, trim.width[0], trim.width[1], period=360))   # ширина кромки посередине, м
        if r["ref"] == "края ворота" and wid0 >= need:
            gap_mm = float(r["gap_mm"])
            why = f"на кромке ({wid0 * 100:.1f} см посередине) — зазор источника от края ворота"
            edge_y = top_y
            target = top_y - gap_mm / 1000.0
    P, _, _ = front_column({k: trim.mesh[k] for k in ("pos", "uv", "tri")})
    m = soft[pl["_lid"]]
    lo, hi = SHIELD_GAP_DY
    f = lambda dy: shield_top_on(P, shield_frame(pl, src, dst, tid24, dy)[0], m, comp)
    t_lo, t_hi = f(lo), f(hi)
    if t_lo is None or t_hi is None or not (t_lo <= target <= t_hi):
        print(f"  ! щит по зазору: цель {target:.4f} м вне досягаемого ({t_lo}–{t_hi}) — щит как по shield_offset_cm")
        return None
    for _ in range(30):
        mid = (lo + hi) / 2
        t = f(mid)
        if t is None or t < target:
            lo = mid
        else:
            hi = mid
    dy = (lo + hi) / 2
    frame, p, cL = shield_frame(pl, src, dst, tid24, dy)
    pl["_frame"] = frame
    pl["nhl24_3d"] = np.round(p, 4).tolist()
    pl["legacy_3d"] = np.round(cL, 4).tolist()
    pl["rule"] = dict(pl.get("rule", {}), offset_cm=[SHIELD_GAP_X_CM, round(dy * 100, 3), 0.0])
    top = shield_top_on(P, frame, m, comp)
    rep = {"gap_mm": gap_mm, "from": why, "trim_bottom": round(edge_y, 4), "shield_top": round(top, 4),
           "offset_cm_y": round(dy * 100, 3), "scale": SHIELD_SCALE}
    pl["shield_gap"] = rep
    _SHIELD_GAP_LOG[kit] = rep
    print(f"  щит по зазору {gap_mm:.1f} мм ({why}): низ кромки {edge_y:.4f} м → верх щита {top:.4f} м, "
          f"сдвиг y {dy * 100:+.2f} см (x {SHIELD_GAP_X_CM}), масштаб {SHIELD_SCALE}")
    return rep


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


def wordmark_alpha():
    """Своя надпись (BRAND_TEXT) в рамке src_box EA (+BRAND_PAD строк сверху и снизу) на сетке 1024², повёрнутая на
    180° (как Reebok на развёртке), 0…1."""
    from PIL import Image, ImageDraw, ImageFont
    H, W = brand_alpha().shape
    S, Hh = BRAND_SS, (H + 2 * BRAND_PAD) * BRAND_SS
    f = ImageFont.truetype(BRAND_FONT, 400)
    bx = f.getbbox("x")
    f = ImageFont.truetype(BRAND_FONT, int(round(400 * BRAND_XH * S / (bx[3] - bx[1]))))
    img = Image.new("L", (W * S, Hh), 0)
    d = ImageDraw.Draw(img)
    widths = [f.getlength(ch) for ch in BRAND_TEXT]
    x, base = (W * S - sum(widths)) / 2, int(round(Hh - (BRAND_PAD + BRAND_BASE_ROW) * S))
    for ch, wc in zip(BRAND_TEXT, widths):
        d.text((x, base), ch, font=f, fill=255, anchor="ls")
        x += wc
    hi = (np.asarray(img).astype(np.float64) / 255)[::-1, ::-1]
    return hi.reshape(H + 2 * BRAND_PAD, S, W, S).mean((1, 3))


def brand_relief_model(ea_nm, a, sigma=0.7):
    """Рельеф букв Reebok EA как наклон сглаженной формы: канал R — по v, G — по u (у развёртки спины), + плоское
    дно букв. ea_nm — окно карты EA (как a), a — альфа надписи. -> (k_R, k_G, R0, G0, B0)."""
    from scipy import ndimage as ndi
    h = ndi.gaussian_filter(a, sigma)
    gy, gx = np.gradient(h)
    m = ndi.binary_dilation(a > 0.25, iterations=1)
    A = np.stack([gy[m], gx[m], np.ones(m.sum())], 1)
    kr, _, r0 = np.linalg.lstsq(A, ea_nm[..., 0][m], rcond=None)[0]
    _, kg, g0 = np.linalg.lstsq(A, ea_nm[..., 1][m], rcond=None)[0]
    return kr, kg, r0, g0, float(np.median(ea_nm[..., 2][a > 0.8]))


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
    if INSERT_COLOR == "source":                         # insert_color: вставка любого цвета — внутри контура INSERT_HW
        ys_h, hs_h = (np.array(v) for v in zip(*INSERT_HW))
        hw24 = np.interp(P[:, 1], ys_h, hs_h, left=-1.0, right=-1.0)
        reds = (P[:, 2] > 0.05) & (P[:, 1] > INSERT_SRC_Y[0]) & (P[:, 1] < INSERT_SRC_Y[1]) & \
            (np.abs(P[:, 0] + 0.0035) < hw24 - INSERT_SRC_PAD)
    red = np.median(c[reds], axis=0)
    ours = np.asarray(Image.open(ours_png).convert("RGB")).astype(np.float64)
    lo = ours.mean(-1)
    white = body_color(ours, yoke=(code, kit) in YOKE)   # у формы без кокетки цвет кокетки клуба — не «не ткань» (MTL дом)
    g = yoke_mask(ours, 70)
    no_yoke = bool(INSERT_COLOR) and (code, kit) not in YOKE   # insert_color без кокетки (TOR): ткань — одним цветом
    green = white if no_yoke else np.median(ours[g], axis=0)
    # линия кокетки спереди на нашей сетке: по столбцам |x| 0,05…0,15 — высота перехода «кокетка → ткань»
    t2, b2 = kit3d.raster_uv(mesh, 1024)
    m = t2 >= 0
    Pm = (b2[m][:, :, None] * mesh["pos"][mesh["tri"][t2[m]]]).sum(1)
    cm = ours[m]
    isg = yoke_mask(cm, 70)
    front = (Pm[:, 2] > 0.05) & (Pm[:, 1] > 1.55) & (Pm[:, 1] < 1.70)
    xs_, ys_ = [], []
    for x0 in np.arange(0.04, 0.16, 0.01):
        sl = front & (np.abs(np.abs(Pm[:, 0]) - x0) < 0.005)
        gy = Pm[sl & isg, 1]
        if len(gy):
            xs_.append(x0)
            ys_.append(float(np.percentile(gy, 2)))
    yoke_y = (np.array(xs_), np.array(ys_))
    if no_yoke:                                          # линии кокетки нет: «выше линии» — нигде
        yoke_y = (np.array([0.0, 1.0]), np.array([9.0, 9.0]))
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
    use_club(a.club)
    pilot.extract_club(Hy.CLUB_NAME[a.club])            # текстуры источника — до замеров кокетки (yoke_heights)
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
                r[nm_] = dict(r[nm_], offset_cm=[sx * SHOULDER_IN_CM, 0.0, 0.0],
                              scale=float(r[nm_].get("scale", 1.0)) * SHOULDER_SCALE)
        if "neck_shield" in r:                           # щит — где у NHL 24 (под краем ворота adidas), не у мыска V EA
            sh = {k: v for k, v in r["neck_shield"].items() if k != "legacy_uv"}
            r["neck_shield"] = dict(sh, offset_cm=SHIELD_OFFSET_CM, scale=SHIELD_SCALE)
        return d, r
    orig_fix_rules = kit_fix._rules

    def fix_rules(path=kit_fix.RULES):
        import copy
        t = copy.deepcopy(orig_fix_rules(path))
        if "brand" in t and "back" in t["brand"]:        # Reebok сзади — на высоте логотипа adidas NHL 24
            t["brand"]["back"] = dict(t["brand"]["back"], center=brand_uv())
            if BRAND_WIN is not None:                    # окно замера цвета логотипа источника (профиль brand_win)
                t["brand"]["back"]["nhl24_win"] = BRAND_WIN
        return t
    kit_fix._rules = fix_rules
    orig_brand_relief = kit_fix.BrandSwap.relief
    orig_brand_init = kit_fix.BrandSwap.__init__

    def brand_init(self, rule, comp, tpl_dir, spots=()):
        """Своя надпись (BRAND_TEXT) вместо альфы Reebok EA: рамка выше на 2·BRAND_PAD строк, центр — тот же."""
        orig_brand_init(self, rule, comp, tpl_dir, spots)
        if BRAND_TEXT:
            H = self.src_a.shape[0]
            self.src_a = wordmark_alpha()
            self.src_wh = (self.src_wh[0], self.src_wh[1] * (H + 2 * BRAND_PAD) / H)
    kit_fix.BrandSwap.__init__ = brand_init

    def brand_relief(self, nm_path, sm_path):
        """Рельеф Reebok — туда же, куда цвет (REEBOK_BACK_UV), а не на место EA: иначе под логотипом — второй,
        выдавленный «Reebok»; и метка-прямоугольник в чистом рельефе спины (RELIEF_CLEAR) — заглажена."""
        from PIL import Image
        from scipy import ndimage as ndi
        if BRAND_TEXT:
            return wordmark_relief(self, nm_path, sm_path)
        sb = self.rule["src_box"]
        box = np.zeros((1024, 1024), bool)                 # только буквы (альфа надписи EA), не вся рамка: в рамке
        u0, v0 = int(round(sb[0] * 1024)), int(round(sb[1] * 1024))   # у EA — и край кокетки (давал черту)
        box[v0:v0 + self.src_a.shape[0], u0:u0 + self.src_a.shape[1]] = self.src_a > 0.25
        m = ndi.gaussian_filter(ndi.binary_dilation(box, iterations=2).astype(np.float64), 1.0)
        dy = int(round((brand_uv()[1] - (sb[1] + sb[3]) / 2) * 1024))
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

    def wordmark_relief(self, nm_path, sm_path):
        """Рельеф и блеск своей надписи — по её форме на месте цвета (REEBOK_BACK_UV, как BrandSwap.__call__):
        внутри букв — гладко (без сетки кокетки), по краю — наклон силы Reebok EA (brand_relief_model)."""
        from PIL import Image
        from scipy import ndimage as ndi
        ea_a = brand_alpha()
        sb = self.rule["src_box"]
        u0, v0 = int(round(sb[0] * 1024)), int(round(sb[1] * 1024))
        ea_nm = np.asarray(Image.open(os.path.join(self.tpl_dir, "jersey_nm.png")).convert("RGBA")
                           .resize((1024, 1024), Image.LANCZOS)).astype(np.float64)
        kr, kg, r0, g0, b0 = brand_relief_model(ea_nm[v0:v0 + ea_a.shape[0], u0:u0 + ea_a.shape[1]], ea_a)
        a = wordmark_alpha()
        ph, pw = a.shape
        x0 = int(round(brand_uv()[0] * 1024 - pw / 2))
        y0 = int(round(brand_uv()[1] * 1024 - ph / 2))
        A = np.zeros((1024, 1024))
        A[y0:y0 + ph, x0:x0 + pw] = a
        h = ndi.gaussian_filter(A, 0.7)
        gy, gx = np.gradient(h)
        m = ndi.gaussian_filter(ndi.binary_dilation(A > 0.25, iterations=2).astype(np.float64), 1.0)
        img = Image.open(nm_path)
        mode = img.mode
        cur = np.asarray(img.convert(mode).resize((1024, 1024))).astype(np.float64)
        letter = cur.copy()
        letter[..., 0], letter[..., 1], letter[..., 2] = r0 + kr * gy, g0 + kg * gx, b0
        out = cur * (1 - m[..., None]) + letter * m[..., None]
        Image.fromarray(np.clip(np.round(out), 0, 255).astype(np.uint8), mode).save(nm_path)
        img = Image.open(sm_path)
        mode = img.mode
        cur = np.asarray(img.convert(mode).resize((1024, 1024))).astype(np.float64)
        aa = ndi.gaussian_filter(A, 0.5)[..., None]
        out = cur.copy()
        n = 3 if cur.ndim == 3 and cur.shape[2] == 4 else (cur.shape[2] if cur.ndim == 3 else 1)
        if cur.ndim == 3:
            out[..., :n] = cur[..., :n] * (1 - aa) + (SM_BASE + BRAND_SM_UP) * aa
        else:
            out = cur * (1 - aa[..., 0]) + (SM_BASE + BRAND_SM_UP) * aa[..., 0]
        Image.fromarray(np.clip(np.round(out), 0, 255).astype(np.uint8), mode).save(sm_path)
        print(f"  надпись «{BRAND_TEXT}» сзади: рельеф k_R {kr:.0f}, k_G {kg:.0f}, дно ({r0:.0f}, {g0:.0f}, {b0:.0f})")
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
        pre = [r for r in (yoke_rule.get("cur"), yoke_rule.get("lapel"), yoke_rule.get("trim"), yoke_rule.get("insert"))
               if r is not None] \
            + list(pre)
        return orig_decal_post(comp, placed, soft, n_jersey_tri, collar, pre, crest_fit, protect)
    kit_hybrid.decal_post = decal_post
    orig_plan_decals = kit_hybrid.plan_decals
    cur_kit = {}

    def plan_decals(comp, lab, patches, rules, defaults, src, dst_, tid24):
        """Щит по зазору под кромкой (SHIELD_GAP_MM, профиль shield_gap_mm): высота — расчётом по кромке этой формы
        (yoke_rule["trim"]). Без поля (задан shield_offset_cm) и в первых сборках (кромки ещё нет) — как было."""
        placed, soft = orig_plan_decals(comp, lab, patches, rules, defaults, src, dst_, tid24)
        cur_kit["placed"] = placed                       # для маски герба (relief_flat_under)
        if CREST_SIZE_CM:
            crest_to_size(placed)
        if TORSO_SHIFT:                                  # герб — вместе с полосой (torso_shift)
            torso_shift_crest(placed)
        if CREST_DROP:
            crest_drop(placed, cur_kit.get("kit"))
        if CREST_LEVEL or CREST_ROT:
            crest_level(placed, cur_kit.get("kit"))
        if SHIELD_GAP_MM is not None and yoke_rule.get("trim") is not None:
            fit_shield_gap(placed, soft, comp, src, dst_, tid24, yoke_rule["trim"], a.club, cur_kit["kit"])
        return placed, soft
    kit_hybrid.plan_decals = plan_decals
    orig_sleeve_rule = pilot.sleeve_rule
    sleeve_plan = {}

    def sleeve_rule(od, tpl=None):
        """Полосы к кисти — уже в переносе (SLV_COMPRESS): jersey_cm.png = jersey_cm_raw.png без сдвига; план — для
        info.json."""
        import shutil
        raw = os.path.join(od, "jersey_cm_raw.png")
        if os.path.exists(raw):
            shutil.copyfile(raw, os.path.join(od, "jersey_cm.png"))
        if ARMHOLE_SPLIT_ZONES is ARMHOLE_SPLIT_FULL:     # рукав другого цвета: граница ровно по шву (VGK, DET 22.10)
            print("  пройма: граница рукава по шву, перекрашено текселей:",
                  armhole_clean(os.path.join(od, "jersey_cm.png"), E2))
        globals()["SLEEVE_LINES"] = None
        if SLEEVE_STRIPES == "fit":                       # края полос рукава — гладкие (профиль sleeve_stripes; OTT 22.10)
            for r_ in sleeve_stripes_fit(os.path.join(od, "jersey_cm.png"), E2):
                print("  полосы рукава (sleeve_stripes = fit):", r_)
        elif SLEEVE_STRIPES == "lines":                   # края полос рукава — ломаные («клин», ANA 26.10)
            for r_ in sleeve_stripes_lines(os.path.join(od, "jersey_cm.png"), E2):
                print("  полосы рукава (sleeve_stripes = lines):", r_)
        for box_ in PIPING_FIT or []:                     # кант вдоль руки — гладкий (CBJ, WSH 23.10; окна по очереди)
            for r_ in piping_fit(os.path.join(od, "jersey_cm.png"), E2, box_):
                print(f"  кант (piping_fit {box_}):", r_)
        if CHEST_BANDS:                                   # полосы через грудь у ворота — прямые, по источнику (NYR; 23.10)
            for r_ in chest_bands_fit(os.path.join(od, "jersey_cm.png"), E2, CHEST_BANDS, a.club, cur_kit["kit"]):
                print("  полосы через грудь (chest_bands):", r_)
        if SLEEVE_MIRROR:                                 # правый рукав — зеркалом левого (SEA выезд, 23.10): цвет
            print("  правый рукав — зеркалом левого (sleeve_mirror), цвет, текселей:",
                  sleeve_mirror(od, E2, ("jersey_cm.png",)))
        return dict(sleeve_plan)
    pilot.sleeve_rule = sleeve_rule
    keep = collar_keep_mask({k: E2[k] for k in ("pos", "uv", "nrm", "tri")}, 1024)
    kit3d.transfer = transfer
    kit_hybrid.collar_color = collar_color
    kit_hybrid.legacy_with_shirt = lambda: (dst, n_jt)
    kit_hybrid.load_rules = load_rules
    kit_fix.collar_lace_rule = lambda *args, **kw: None
    orig_crest_fit = kit_fix.crest_fit

    def crest_fit(name_png, path=kit_fix.RULES):
        """Герб не на букву — по тем местам буквы, что будут в слоте: зоны формы NAME_ZONES_FROM и сдвиг LETTER_SHIFT_CM
        (стадия slot делает с картой то же)."""
        import shutil
        if not (NAME_ZONES_FROM or LETTER_SHIFT_CM or LETTER_ZONE_SCALE != 1.0):
            return orig_crest_fit(name_png, path)
        tmp = os.path.join(WORK, "cur_kits", f"_crest_fit_{a.club}.png")
        os.makedirs(os.path.dirname(tmp), exist_ok=True)
        shutil.copyfile(name_png, tmp)
        if NAME_ZONES_FROM:
            ref = os.path.join(WORK, "cur_kits", NAME_ZONES_FROM)
            if not os.path.exists(os.path.join(ref, "kit.json")):
                J.unpack_kit(NAME_ZONES_FROM, ref)
            copy_zones(tmp, os.path.join(ref, "name_cm.png"), LETTER_ZONES)
        if LETTER_SHIFT_CM:
            shift_zones(tmp, *LETTER_SHIFT_CM)
        if LETTER_ZONE_SCALE != 1.0:                    # места буквы мельче (letter_zone_scale) — как в стадии slot
            scale_zones(tmp, LETTER_ZONE_SCALE, solid_zones(tmp, LETTER_ZONES))
        return orig_crest_fit(tmp, path)
    kit_fix.crest_fit = crest_fit
    pilot.set_roots(KITS_OUT, os.path.join(WORK, "pack"))
    try:
        for kit in a.kits.split(","):
            yoke_rule.pop("cur", None)
            use_kit(kit)                                 # yoke_color по форме (EDM, COL, PHI: дома и в гостях разный)
            if COLLAR_LAPEL_KITS is not None:            # collar_lapel по формам (NYI): лацканы — только у этой формы
                globals()["COLLAR_LAPEL"] = COLLAR_LAPEL_KITS.get(kit)
                _RGEO.clear()                            # обод с лацканами и без — разная геометрия (кэш relief_geometry)
            globals()["SLV_COMPRESS"] = None             # первая сборка комплекта — без сжатия (план — по ней)
            globals()["SLV_FILL_S24"] = None
            globals()["SLV_FILL_S24_R"] = None
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
            if heights is not None and heights.get("bands") and getattr(yoke_rule["trim"], "trap", None) is not None:
                heights["trap"] = yoke_rule["trim"].trap   # полосы в кокетке — до боковин вставки шаблона (STL выезд)
            yoke_rule.pop("lapel", None)
            if COLLAR_LAPEL:                             # лацканы другого цвета (MTL, DAL: белые) — от края до шва обода
                cy = yoke_rule.get("cur")
                yoke_rule["lapel"] = lapel_rule(a.club, kit, {k: E2[k] for k in ("pos", "uv", "nrm", "tri", "uv0")},
                                                *((cy.poly["green"], cy.poly["white"]) if cy is not None else ()))
                lapel_trim_band(yoke_rule.get("lapel"), yoke_rule.get("trim"))
            cur_kit["kit"] = kit                       # для щита по зазору (plan_decals)
            if (a.club, kit) in INSERT_KITS:
                if "cur" not in yoke_rule:              # цвета — с первой сборки (как у кокетки)
                    pilot.cmd_build(SimpleNamespace(club=a.club, kits=kit, reuse=False))
                yoke_rule["insert"] = insert_rule(os.path.join(KITS_OUT, f"{a.club}_{kit}", "jersey_cm.png"), E2,
                                                  a.club, kit)
                lp_ = yoke_rule.get("lapel")             # лацкан цвета вставки (NYR выезд): InsertPaint его не трогает
                if lp_ is not None and np.abs(lp_.color - yoke_rule["insert"].red).max() < LAPEL_SAME_COLOR:
                    yoke_rule["insert"].lapel = lp_
                if COLLAR_LAPEL and yoke_rule.get("trim") is not None:   # лацканы (DAL дом, 22.10): кромка у вставки
                    yoke_rule["insert"].trim_w = yoke_rule["trim"].width   # шире INSERT_TRIM — не перекрашивать её
                    #                                                        (сборка 2: зелёные выемки в чёрной кромке)
                if heights is not None:                  # линия кокетки — как у YokePaint (по первой сборке она
                    yoke_rule["insert"].yoke_y = heights["front"]   # 1,625 — у угла вставки был зелёный «прыщ»)
            if SLV_PARAM and (not cmaps or not os.path.exists(os.path.join(KITS_OUT, f"{a.club}_{kit}", "kit.json"))):
                # первая сборка — и для сжатия полос рукава к кисти: без неё нет карты переноса (cmaps) и шаблона
                # (kit.json). У MIN и NJD её всегда делают кокетка или вставка; у клуба без них (TBL, 21.10) полосы рукава
                # шли без сжатия — под номер на рукаве («! полосы рукава: нет kit.json»; у первой формы — молча)
                print("  полосы рукава: первая сборка комплекта — для сжатия к кисти")
                pilot.cmd_build(SimpleNamespace(club=a.club, kits=kit, reuse=False))
            global SLV_COMPRESS, SLV_FILL_S24
            SLV_COMPRESS, SLV_FILL_S24 = None, None
            globals()["SLV_FILL_S24_R"] = None
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
            yoke_rule.pop("lapel", None)
            od = os.path.join(KITS_OUT, f"{a.club}_{kit}")
            if "crest" in RELIEF_FLAT_UNDER:
                print("  маска герба (crest_alpha.png):", save_crest_alpha(cur_kit.get("placed"), od), "текселей")
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
            if SLEEVE_MIRROR:                            # рельеф и блик правого рукава — зеркалом левого (SEA выезд)
                print("  правый рукав — зеркалом левого (sleeve_mirror), рельеф и блик, текселей:",
                      sleeve_mirror(od, E2, ("jersey_nm.png", "jersey_sm.png")))
            pad_island(od, E2)
            print("  прежнее место острова (для lod 0, 3):", fill_old_place(od, E2), "текселей")
            J.fe_preview(od, {k: E2[k] for k in ("pos", "uv", "nrm", "tri")})   # превью меню — по своей сетке
    finally:
        pilot.sleeve_rule = orig_sleeve_rule
        kit_hybrid.decal_post = orig_decal_post
        kit_hybrid.plan_decals = orig_plan_decals
        kit3d.transfer = orig_transfer
        kit_hybrid.load_rules = orig_rules
        kit_fix._rules = orig_fix_rules
        kit_fix.crest_fit = orig_crest_fit
        kit_fix.BrandSwap.relief = orig_brand_relief
        kit_fix.BrandSwap.__init__ = orig_brand_init


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
        b24r = cmap.sleeve.stripes(tex, side=1)[0] if SLEEVE_FILL_SIDE else np.zeros(0)   # правый рукав (SEA выезд)
        if SLEEVE_TOP24 is not None:                     # верх полос — из профиля (SJS): выше конца рукава Edge
            b24 = np.append(b24[b24 < SLEEVE_TOP24], SLEEVE_TOP24)
            bE = np.append(bE[: len(b24) - 1], cmap.sleeve.edge_of(SLEEVE_TOP24))
            print(f"  полосы рукава: верх — sleeve_top24 {SLEEVE_TOP24} (s Edge {bE[-1]:.4f}, конец карты рукава "
                  f"{cmap.sleeve.sides[-1]['e']['s'][-1]:.4f}, наклон {cmap.sleeve.s24_slope(cmap.sleeve.sides[-1]['e'], cmap.sleeve.sides[-1]['s24']):.3f})")
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
    global SLV_FILL_S24, SLV_FILL_EXT_TOP, SLV_FILL_S24_R
    SLV_FILL_S24 = None
    SLV_FILL_S24_R = None
    SLV_FILL_EXT_TOP = None
    margin = sleeve_top_margin(cmap, d_top)
    if margin < SLV_TOP_MARGIN:                          # над полосами у рукава Edge места нет (BOS): выше колена — ткань
        SLV_FILL_S24 = float(b24.max()) + SLV_FILL_TEXELS / 2048.0
        if SLEEVE_FILL == "below":                       # ткань — рукава под полосами (MTL дом, 22.10: над верхней белой
            SLV_FILL_S24 = float(b24.min()) - SLV_FILL_TEXELS / 2048.0   # полосой у конца рукава — 1,5 мм красного,
            #                                              бралась белая: верх рукавов белый)
        if SLEEVE_TOP24 is not None:                     # верх полос далеко за концом рукава (OTT: до 0,30) — ткань и в
            SLV_FILL_EXT_TOP = max(SLV_FILL_EXT, d_top - SLV_U[1] + 0.02)   # реглане до верха полос: иначе там прежние
            #                                              полосы источника ближайшей точкой — второй блок у плеча (сборка 2)
        print(f"  ! полосы рукава: верх полос в {margin * 100:.1f} см от конца рукава (< {SLV_TOP_MARGIN * 100:g}) — "
              f"выше колена {k * d_top:.4f} ткань над полосами (s NHL 24 {SLV_FILL_S24:.4f})")
        if SLEEVE_FILL_SIDE and SLEEVE_TOP24 is None and len(b24r):   # своя рука (23.10, SEA выезд): у NHL 27 верх полос
            SLV_FILL_S24_R = (float(b24r.min()) - SLV_FILL_TEXELS / 2048.0 if SLEEVE_FILL == "below"   # справа выше
                              else float(b24r.max()) + SLV_FILL_TEXELS / 2048.0)   # левого — ткань левого там ещё полоса
            print(f"  полосы рукава (sleeve_fill_side): правый рукав — границы {np.round(b24r, 4).tolist()}, ткань над "
                  f"полосами s NHL 24 {SLV_FILL_S24_R:.4f} (левый {SLV_FILL_S24:.4f})")
    plan_out.clear()
    for z, zone in zones.items():
        left = zone[0] < 0.5
        d_zone = zone[0] if left else 1 - zone[2]
        plan_out[str(z)] = {"left": bool(left), "d_top": round(d_top, 4), "k": round(k, 3),
                            "gap_before": round(float(d_zone - d_top), 3), "gap_after": round(float(d_zone - d_top * k), 3),
                            "mode": "edge_kit: в переносе рукава"}
        if SLV_FILL_S24 is not None:
            fs = SLV_FILL_S24_R if (not left and SLV_FILL_S24_R is not None) else SLV_FILL_S24   # sleeve_fill_side
            plan_out[str(z)].update(top_margin_cm=round(margin * 100, 2), fill_s24=round(fs, 4))
    return (k, d_top)


def sleeve_mirror(od, mesh, files):
    """Профиль sleeve_mirror = "left" (23.10, SEA выезд): правый рукав развёртки Edge от манжеты до верха полос (колено
    SLV_COMPRESS + SLV_MIRROR_PAD, выше — переход SLV_MIRROR_BLEND) — зеркалом левого (тексель u → 1 − u) в файлах files
    папки od; у jersey_nm — R с обратным знаком. Тексель берётся, только если зеркальный — та же точка руки (SLV_MIRROR_TOL);
    поля острова вокруг зоны (SLV_MIRROR_PADPX) — тоже. -> число текселей зоны."""
    from PIL import Image
    from scipy import ndimage as ndi
    S = 1024
    tid, bar = kit3d.raster_uv(mesh, S)
    m = tid >= 0
    P = np.zeros((S, S, 3))
    P[m] = (bar[m][:, :, None] * mesh["pos"][mesh["tri"][tid[m]]]).sum(1)
    top = (SLV_COMPRESS[0] * SLV_COMPRESS[1] if SLV_COMPRESS is not None else SLV_U[1] - SLV_MIRROR_BLEND) + SLV_MIRROR_PAD
    s = 1.0 - (np.arange(S) + 0.5) / S                   # s правого рукава по столбцу
    near = (s < top + SLV_MIRROR_BLEND)[None, :]
    xm = S - 1 - np.arange(S)
    mm = m[:, xm]
    same = np.linalg.norm(P - P[:, xm] * np.array([-1.0, 1.0, 1.0]), axis=-1) < SLV_MIRROR_TOL
    zone = m & mm & near & (P[..., 0] > SLV_X) & same
    zone |= ndi.binary_dilation(zone, iterations=SLV_MIRROR_PADPX) & ~m & ~mm & near
    w = np.clip((top + SLV_MIRROR_BLEND - s) / SLV_MIRROR_BLEND, 0.0, 1.0)
    ys, xs = np.nonzero(zone)
    ww = w[xs][:, None]
    for f in files:
        p = os.path.join(od, f)
        im = Image.open(p)
        a = np.asarray(im).astype(np.float64).copy()
        if a.shape[:2] != (S, S):
            print(f"  ! sleeve_mirror: {f} {a.shape[1]}×{a.shape[0]} — не {S}², не тронут")
            continue
        src = a[ys, S - 1 - xs].copy()
        if f.startswith("jersey_nm"):                    # нормаль в касательных: тангенс по u — у зеркала обратный
            src[:, 0] = 255.0 - src[:, 0]
        a[ys, xs] = src * ww + a[ys, xs] * (1.0 - ww)
        Image.fromarray(np.clip(np.round(a), 0, 255).astype(np.uint8), im.mode).save(p)
    return int(zone.sum())


def sleeve_top_margin(cmap, d_top):
    """Сколько м по средней линии рукава Edge от верха полос d_top до конца рукава SLV_U[1] (≤ 0 — полосы до конца)."""
    e = cmap.sleeve.sides[-1]["e"]
    L = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(e["C"], axis=0), axis=1))])
    return float(np.interp(SLV_U[1], e["s"], L) - np.interp(d_top, e["s"], L))


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
# Буква капитана (зоны 5 и 7 карты номеров): у выездной 1_14_3 они на 0,023 по v ниже, чем у домашней 1_14_4, при
# том же месте герба — на светлой букву почти прижимало к гербу (пользователь, 20.10). Зоны букв — с карты этой формы.
LETTER_ZONES = (5, 7)
LETTER_ZONES_FROM = {"away": "home"}
# Номера на рукавах (зоны 2 и 3 карты номеров) — там же, где у MIN, у всех клубов (пользователь, 21.10: у NJD «чуть
# повыше нужно, как у Миннесоты», общее правило). С карты EA 1_17_0 верх зоны — 1,551 м и зона короче; у MIN дом
# (1_14_4) — 1,566 м, у MIN выезд (1_14_3) — 1,600 м. Образец — домашняя MIN; у самой MIN — свои (профиль "own").
SLEEVE_ZONES = (2, 3)
SLEEVE_ZONES_REF = "1_14_4"
NAME_ZONES = (0, 1, 5, 7)          # фамилия, номер на спине, места буквы капитана
NAME_ZONES_FROM = None             # профиль name_zones_from: форма Legacy, с карты которой зоны NAME_ZONES (VGK 22.10 —
#                                    MIN 1_14_4: у заготовок Custom SEA/VGK фамилия и номер на 15–17 % крупнее, буква
#                                    капитана — 36 × 34 текселей против 15 × 15 у EA)
SLEEVE_ZONES_FROM = SLEEVE_ZONES_REF   # профиль sleeve_zones_from: форма Legacy, с карты которой зоны, или "own"
SOCK_PARTS = ((0.0, (24, 56, 46)), (30, (214, 203, 165)), (30, (159, 14, 10)), (110, (214, 203, 165)))
SOCK_TOP_V = 0.49                  # верх полос своих гетр (v развёртки гетр: 0 — у колена): у EA MIN 0,48–0,50;
#                                    перенесённые с NHL 24 — 0,576 (на ~6,5 см ниже — «повыше», пользователь, 19.10)
# гетры EA (светлая): полоса — в тех же строках, что у домашних (пользователь, 20.10: «линии на гетрах — на одном
# уровне, как на домашней»): place_sock растягивает её (74 → 81 строка из 512) на полосу flat_sock домашних


def sock_parts_auto(src_png, min_rows=2):
    """Полосы гетр источника (перенесённые fb.pilot, строки — поперёк ноги): ткань — самый частый цвет строк, полоса —
    от первой до последней строки не цвета ткани, внутри — отрезки одного цвета (≥ min_rows строк, короче — к
    соседнему). -> ((0, ткань), (строк, цвет), …) — как SOCK_PARTS."""
    from PIL import Image
    a = np.asarray(Image.open(src_png).convert("RGB")).astype(np.float64)
    med = np.median(a[:, a.shape[1] // 4:3 * a.shape[1] // 4], axis=1)
    q = np.round(med / 24)
    _, inv, cnt = np.unique(q, axis=0, return_inverse=True, return_counts=True)
    base = np.median(med[inv.reshape(-1) == cnt.argmax()], axis=0)
    band = np.nonzero(np.linalg.norm(med - base, axis=1) > 40)[0]
    if not len(band):
        return ((0.0, tuple(base)),)
    rows = med[band.min():band.max() + 1]
    segs = []
    for c in rows:
        if segs and np.linalg.norm(c - segs[-1][1] / segs[-1][0]) < 40:
            segs[-1][0] += 1
            segs[-1][1] += c
        else:
            segs.append([1, c.copy()])
    segs = [[n, s_ / n] for n, s_ in segs]
    out = []
    for n, c in segs:
        if n < min_rows and out:
            out[-1][0] += n
        else:
            out.append([n, c])
    if len(out) > 1 and out[0][0] < min_rows:            # строка-переход сверху (сглаживание края) — к следующей полосе
        out[1][0] += out[0][0]
        out = out[1:]
    return ((0.0, tuple(np.round(base))),) + tuple((float(n), tuple(np.round(c))) for n, c in out)


def flat_sock(src_png, parts=None):
    """Гетры: полоса — там же, где у перенесённых (строки, где медиана строки не цвет ткани), разбита в долях parts
    (по умолчанию SOCK_PARTS), края — с долей покрытия строки (без лесенки)."""
    from PIL import Image
    parts = parts or SOCK_PARTS
    a = np.asarray(Image.open(src_png).convert("RGB")).astype(np.float64)
    H, W = a.shape[:2]
    base = np.array(parts[0][1], np.float64)
    med = np.median(a, axis=1)
    band = np.nonzero(np.linalg.norm(med - base, axis=1) > 40)[0]
    y0, y1 = float(band.min()), float(band.max() + 1)
    if SOCK_TOP_V is not None:                           # своя высота полосы (ширина — как у перенесённых)
        y0, y1 = SOCK_TOP_V * H, SOCK_TOP_V * H + (y1 - y0)
    tot = sum(w for w, _ in parts[1:])
    edges, cols = [y0], []
    for w_, c in parts[1:]:
        edges.append(edges[-1] + (y1 - y0) * w_ / tot)
        cols.append(np.array(c, np.float64))
    if band.max() >= H - 3 and SOCK_TOP_V is not None:   # у источника полосы до низа гетры (низ — другого цвета: ANA дом
        edges[-1] = float(H)                             # чёрный, COL синий, NSH тёмно-синий): после подъёма к SOCK_TOP_V
        #                                                  низ — последней полосой, а не тканью (пользователь, 23.10:
        #                                                  «убрать полоску внизу гетр» — ANA, COL, NSH; так же SEA выезд,
        #                                                  VGK, WSH)
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


def scale_name_zone(png, k, zone=0):
    """Зона фамилии карты номеров (R, G > 128, B = зона) ниже в k раз по столбцам: верх фамилии на свитере — край зоны с
    большим v (на спине развёртка перевёрнута: номер — выше по v), он на месте, низ поднимается — до номера свободнее.
    Дуга (DET) — по каждому столбцу. Игра вписывает фамилию в зону: мельче и буквы, и промежутки (пользователь, 22.10,
    LAK и DET: «фамилии меньше, и не забывай про интервалы»). -> (высота было, стало) по середине, в долях."""
    from PIL import Image
    a = np.asarray(Image.open(png).convert("RGBA")).copy()
    m = (a[..., 0] > 128) & (a[..., 1] > 128) & (a[..., 2] == zone)
    if not m.any():
        return None
    color = a[m][0].copy()
    H = a.shape[0]
    xs = np.nonzero(m.any(0))[0]
    mid = xs[len(xs) // 2]
    h0 = h1 = 0
    for x in xs:
        ys = np.nonzero(m[:, x])[0]
        top, bot = ys.max(), ys.min()                 # top — край зоны с большим v (верх фамилии на свитере)
        h = top - bot + 1
        nh = max(1, int(round(h * k)))
        a[ys, x] = (255, 255, 255, 255)
        a[top - nh + 1:top + 1, x] = color
        if x == mid:
            h0, h1 = h / H, nh / H
    Image.fromarray(a, "RGBA").save(png)
    return round(h0, 3), round(h1, 3)


def back_m_per_v():
    """Метров высоты свитера на единицу v развёртки — посередине спины сетки слота (полевой, размер 0, lod 2): на спине
    v растёт снизу вверх (номер — меньше v, фамилия над ним — больше). ~1,57 м: строка карты номеров 256² — ~0,6 см."""
    M = mesh_for(0, 1, 2)
    pos, uv = M["pos"], M["uv"]
    back = (pos[:, 2] < 0) & (np.abs(pos[:, 0]) < 0.04) & (pos[:, 1] > 1.2)
    k = np.polyfit(uv[back, 1], pos[back, 1], 1)
    return float(k[0]), float(k[1])


NAME_FIT_REF = (14, 39)            # образец высоты фамилии — MIN 1_14_4: зона 14 строк карты 256², буквы атласа 39 px
NAME_FIT_GAP = 0.21                # промежуток в клетке к высоте буквы — не больше (22.10: 0,23 → 0,21 — «всё одинаково, плотно»; просил плотнее у SEA,
#                                    LAK, BOS: после правок 0,22–0,23; NJD, DET 0,19 — без просьб; MIN 0,31 — образец не трогаем)
NAME_FIT_GAP_MIN = 0.15            # промежуток не меньше (22.10, DET: шире буквы — слиплись бы)
NAME_ROW_H, NAME_CELL_W = 47, 32   # px атласа: высота строки букв фамилии, шаг клеток


# Стандарт спины — один у всех клубов (пользователь, 22.10: «всё стандартизировать, чтобы было примерно одинаково;
# номера относительно большие — у MIN, возможно, маловаты; учитывать отступ сверху от кокетки — ориентир BUF»).
# Размеры — на свитере, как рисует игра (клетка атласа вписывается в зону по высоте; kitport lettering): зона
# фамилии и номера считается под шрифт формы. Место: верх фамилии — LETTERING_NAME_TOP, а у формы с кокеткой
# сзади — на LETTERING_YOKE_GAP ниже её края (замер 22.10: у BUF выезда 2,7 см; кокетки сзади — 1,60–1,61 м);
# номер — на LETTERING_GAP ниже фамилии. Дуга фамилии (DET) сохраняется: высота по столбцам, верх — со сдвигом.
# Профиль lettering = "own" — как раньше (зоны и размеры образца)
LETTERING = "standard"
LETTERING_NAME_H = 0.072           # м: высота букв фамилии (новые клубы 22.10 — 7,05–7,2 см, MIN 7,1)
LETTERING_NAME_W_MAX = 0.040       # м: буква фамилии не шире — у широкого шрифта фамилия ниже (22.10, DET: «шрифт огромный»
#                                    при 7,5 × 4,4 см; так — 6,8 × 4,0, как одобренный до стандарта)
DIGIT_GAP = 0.052                  # промежуток между цифрами номера (видимый край к краю) к высоте цифры — у клубов без своего
#                                    digit_gap: медиана замеров фото настоящих форм (24.10, 17 клубов: 0–0,086, docs/kitport.md
#                                    §12.1; пользователь: «расстояние между цифрами можно ближе у всех — сравни с фото», у CHI
#                                    98 Бедарда в игре было 0,105, на фото 0,042). Было (22.10–24.10): ≤ 0,08 растяжкой знаков
DIGIT_ASPECT = "keep"              # ширина цифры в игре: "keep" — как была до 24.10 (одобрено пользователем): знак шире по
#                                    правилу 22.10 (fonts.old_digit_widen) в зоне стандарта (клетка шире атласа ×1,13); число —
#                                    к пропорции шрифта источника (фото анфас против атласа NHL 27: медиана ×1,05). Профиль digit_aspect
#                                    24.10 по листам «фото | было | сейчас» пользователь: «мне нравятся номера… стало намного
#                                    лучше» — ширина оставлена "keep" (уже, как у настоящих, — только если попросит)
DIGIT_FIT_ITER = 3                 # растяжек знаков цифр от исходного атласа, пока видимая ширина не выйдет не уже цели
DIGIT_GAPS = {}                    # профиль digit_gap: форма → промежуток к высоте цифры (или одно число на обе)
DIGIT_ASPECTS = {}                 # профиль digit_aspect: форма → "keep" | множитель к пропорции источника
LETTERING_NUM_H = 0.30             # м: высота номера (MIN 25,7–27,5, DET 29,8, SEA 30,5 — «номера относительно большие»)
NUMBER_H = None                    # профиль number_h_cm (23.10, пользователь после игры: «номер на спине поменьше» — ANA BUF
#                                    CGY; «совсем немного / чуть меньше» — EDM NYI SJS): высота номера клуба, см; нет — LETTERING_NUM_H
LETTERING_NAME_TOP = 1.580         # м: верх зоны фамилии (у MIN, TBL, SEA, VGK — 1,577)
LETTERING_YOKE_GAP = 0.027         # м: от края кокетки сзади до верха фамилии (BUF выезд)
LETTERING_GAP = 0.020              # м: от низа зоны фамилии до верха зоны номера
LETTERING_NUM_ASPECT = 69 / 46     # столбцов карты на строку у зоны номера (MIN 1_14_4: 69 × 46)
LETTERING_NUM_X = (94 + 162) / 2   # столбец середины зоны номера (MIN)
LETTERING_NAME_X = (90, 165)       # столбцы зоны фамилии (MIN 1_14_4): ширина одна у всех — длинная фамилия сжимается
#                                    одинаково (было: BOS 61, SEA 128 — у широкой зоны концы фамилии уходят вниз по
#                                    развёртке); у фамилии дугой (профиль name_arch, DET) — ширина и форма своей зоны
NAME_ARCH = False


def back_yoke_bottom(jersey_png, mesh=None):
    """Нижний край кокетки (или иной вставки другого цвета) сзади, м: полосы |x| 4–12 см (мимо надписи у ворота),
    ткань — медиана на 1,45–1,55 м (место фамилии; ниже бывают полосы — MTL дома), вверх от 1,50 до первой
    строки не цвета ткани. Нет до 1,66 м (там уже ворот) — None."""
    from PIL import Image
    M = mesh or mesh_for(0, 1, 2)
    c = np.asarray(Image.open(jersey_png).convert("RGB")).astype(np.float64)
    tid, bar = kit3d.raster_uv(M, c.shape[0])
    ys, xs = np.nonzero(tid >= 0)
    P = (bar[ys, xs][:, :, None] * M["pos"][M["tri"][tid[ys, xs]]]).sum(1)
    sel = (P[:, 2] < -0.03) & (np.abs(np.abs(P[:, 0]) - 0.08) < 0.04)
    y, cc = P[sel, 1], c[ys[sel], xs[sel]]
    body = np.median(cc[(y > 1.45) & (y < 1.55)], 0)
    for y0 in np.arange(1.50, 1.66, 0.0025):
        m = (y >= y0) & (y < y0 + 0.0025)
        if m.sum() > 5 and np.median(np.abs(cc[m] - body).max(1)) >= 40:
            return float(y0)
    return None


def standard_lettering(slot_dir):
    """Зоны фамилии (0) и номера (1) карты номеров — по стандарту спины (LETTERING_*), под шрифт формы.
    -> описание."""
    from PIL import Image
    from .fonts import CAPTAIN_BOX
    png = os.path.join(slot_dir, "name_cm.png")
    a = np.asarray(Image.open(png).convert("RGBA")).copy()
    H = a.shape[0]
    k, b = back_m_per_v()
    row = lambda yy: (yy - b) / k * H                   # строка карты (вниз по картинке — вверх по свитеру)
    f = np.asarray(Image.open(os.path.join(slot_dir, "font_cm.png")).convert("RGBA"))[..., 3] > 40
    if FONT_PLATE:                                      # фамилия на подложке (PHI): буквы — по цвету против плашки
        f = plate_letters(os.path.join(slot_dir, "font_cm.png"))
    hs, ws = [], []
    for r_, (y0, y1) in enumerate(((1, 48), (49, 98))):
        cx = J.FONT_SLOTS[r_]
        bnd = [0] + [(cx[i] + cx[i + 1]) // 2 for i in range(len(cx) - 1)] + [CAPTAIN_BOX[0]]
        for i in range(len(cx)):
            sub = f[y0:y1, bnd[i]:bnd[i + 1]]
            rr, cc = np.nonzero(sub.any(1))[0], np.nonzero(sub.any(0))[0]
            if len(rr):
                hs.append(rr[-1] - rr[0] + 1)
                ws.append(cc[-1] - cc[0] + 1)
    dh = []
    for y0, y1 in ((115, 238), (242, 367)):
        rr = np.nonzero(f[y0:y1, :420].any(1))[0]
        if len(rr):
            dh.append(rr[-1] - rr[0] + 1)
    letter_fill = float(np.median(hs)) / NAME_ROW_H
    digit_fill = float(np.median(dh)) / 123.0
    yb = back_yoke_bottom(os.path.join(slot_dir, "jersey_cm.png"))
    top = LETTERING_NAME_TOP if yb is None else min(LETTERING_NAME_TOP, yb - LETTERING_YOKE_GAP)
    aspect = float(np.median(ws)) / float(np.median(hs))   # ширина буквы к высоте (DET — 0,59, прочие 0,45–0,56)
    name_h = min(LETTERING_NAME_H, LETTERING_NAME_W_MAX / aspect)
    h0 = name_h / letter_fill                           # м: высота зоны фамилии
    num_h = LETTERING_NUM_H if NUMBER_H is None else NUMBER_H
    h1 = num_h / digit_fill
    # фамилия: столбцы прежней зоны, верх каждого — со сдвигом от среднего (дуга DET), высота — h0
    m0 = (a[..., 0] > 128) & (a[..., 1] > 128) & (a[..., 2] == 0)
    xs0 = np.nonzero(m0.any(0))[0]
    if not len(xs0):
        return "зоны фамилии нет — стандарт не применён"
    c0 = m0[:, xs0[len(xs0) // 2]]
    top_c = np.nonzero(c0)[0].max()
    col0 = a[m0][0].copy()
    tops = {x: np.nonzero(m0[:, x])[0].max() - top_c for x in xs0}
    if not NAME_ARCH:                                  # ширина зоны — стандартная, фамилия прямая
        tops = {x: 0 for x in range(LETTERING_NAME_X[0], LETTERING_NAME_X[1] + 1)}
    m1 = (a[..., 0] > 128) & (a[..., 1] > 128) & (a[..., 2] == 1)
    col1 = a[m1][0].copy() if m1.any() else np.array([255, 255, 1, 255], np.uint8)
    a[m0 | m1] = (255, 255, 255, 255)
    t_r, n0 = int(round(row(top))) - 1, max(1, int(round(h0 / k * H)))
    for x, off in tops.items():
        r1 = t_r + off
        a[max(0, r1 - n0 + 1):r1 + 1, x] = col0
    n_top = top - h0 - LETTERING_GAP                     # верх номера, м
    n1 = max(1, int(round(h1 / k * H)))
    r1 = int(round(row(n_top))) - 1
    w1 = int(round(n1 * LETTERING_NUM_ASPECT))
    x0 = int(round(LETTERING_NUM_X - w1 / 2))
    other = (a[..., 0] > 128) & (a[..., 1] > 128) & (a[..., 2] < 16)
    box = np.zeros_like(other)
    box[max(0, r1 - n1 + 1):r1 + 1, max(0, x0):x0 + w1] = True
    if (box & other).any():
        sys.exit(f"{png}: зона номера по стандарту наезжает на другую зону")
    a[box] = col1
    Image.fromarray(a, "RGBA").save(png)
    return (f"фамилия {name_h * 100:.1f} см (зона {h0 * 100:.1f}, ширина буквы {name_h * aspect * 100:.1f}), верх {top:.3f} м"
            + (f" (кокетка сзади до {yb:.3f} м)" if yb is not None else "")
            + f", номер {num_h * 100:.1f} см (зона {h1 * 100:.1f}), верх {n_top:.3f} м, низ {n_top - h1:.3f} м")


_UV_RASTER = {}


def zone_size_cm(png, zone):
    """Ширина и высота зоны карты номеров на свитере слота (полевой, размер 0, lod 2), м: хордами через середину зоны
    вдоль «вправо» и «вверх» касательной плоскости — как jersey_mesh.stamp (kitport backs). Нет зоны — None."""
    from PIL import Image
    a = np.asarray(Image.open(png).convert("RGBA"))
    m = (a[..., 0] > 128) & (a[..., 1] > 128) & (a[..., 2] == zone)
    if not m.any():
        return None
    ys, xs = np.nonzero(m)
    x0, y0, x1, y1 = xs.min(), ys.min(), xs.max(), ys.max()
    S = a.shape[0]
    M = mesh_for(0, 1, 2)
    if S not in _UV_RASTER:
        _UV_RASTER[S] = kit3d.raster_uv(M, S)
    tid, bar = _UV_RASTER[S]
    c = np.array([(x0 + x1 + 1) / 2.0, (y0 + y1 + 1) / 2.0])
    t = tid[int(c[1]), int(c[0])]
    if t < 0:
        return None
    Jm = J.uv_jacobian(M, t, S)
    n = kit3d._unit(np.cross(Jm[:, 0], Jm[:, 1]))
    nv = kit3d._unit((bar[int(c[1]), int(c[0])][:, None] * M["nrm"][M["tri"][t]]).sum(0))
    if (n * nv).sum() < 0:
        n = -n
    up = np.array([0.0, 1.0, 0.0]) - n * n[1]
    up = up / np.linalg.norm(up)
    right = np.cross(up, n)
    pinv = np.linalg.pinv(Jm)
    half = np.array([(x1 + 1 - x0) / 2.0, (y1 + 1 - y0) / 2.0])

    def chord(d3):
        dpx = pinv @ d3
        tt = min(half[i] / abs(dpx[i]) for i in range(2) if abs(dpx[i]) > 1e-12)
        return 2 * tt * np.linalg.norm(Jm @ dpx)
    return float(chord(right)), float(chord(up))


def scale_zones_x(png, zones, k):
    """Зоны карты номеров уже (k < 1) или шире по ширине вокруг середины, высота и строки те же; у всех зон — одна новая
    ширина от одной прежней (зоны 2 и 3 — одинаковые). -> {зона: «ширина было → стало»}."""
    from PIL import Image
    a = np.asarray(Image.open(png).convert("RGBA")).copy()
    res = {}
    for z in zones:
        m = (a[..., 0] > 128) & (a[..., 1] > 128) & (a[..., 2] == z)
        if not m.any():
            continue
        color = a[m][0].copy()
        ys, xs = np.nonzero(m)
        w = int(xs.max() - xs.min() + 1)
        nw = max(1, int(round(w * k)))
        cx = (xs.min() + xs.max() + 1) / 2.0
        x0 = int(round(cx - nw / 2.0))
        rows = np.unique(ys)
        a[m] = (255, 255, 255, 255)
        other = (a[..., 0] > 128) & (a[..., 1] > 128) & (a[..., 2] < 16)
        box = np.zeros(m.shape, bool)
        box[rows[:, None], np.arange(max(0, x0), min(a.shape[1], x0 + nw))[None, :]] = True
        if (box & other).any():
            sys.exit(f"{png}: зона {z} шириной {nw} наезжает на другую зону")
        a[box] = color
        res[z] = f"{w} → {nw}"
    Image.fromarray(a, "RGBA").save(png)
    return res


def digit_spacing(slot_dir, kit):
    """Промежуток между цифрами номера — как у настоящих форм (пользователь, 24.10: «расстояние между цифрами можно
    ближе у всех команд; сравни с фото настоящих — у Бедарда 98 между 9 и 8 в жизни меньше, чем в игре»). Игра рисует
    клетку цифры шириной в половину зоны номера (fb.fonts, «Цифры номера»): промежуток к ширине цифры задаёт атлас,
    ширину цифры к высоте — зона. Знаки цифр шире в клетках, пока промежуток к высоте цифры в игре не станет
    digit_gap формы (профиль; нет — DIGIT_GAP), а зона номера на спине (1) уже в той же мере — ширина цифры в игре
    прежняя (DIGIT_ASPECT "keep") или пропорция шрифта источника × число (digit_aspect). Малые цифры (номер на рукаве) —
    тот же промежуток к ширине цифры, ширина цифры в игре прежняя: множитель ширины зон рукава (2, 3) возвращается —
    их сужает cmd_slot после всех правок зон рукава. Вызывать после standard_lettering. -> (описание, множитель зон рукава)."""
    from . import fonts
    font = os.path.join(slot_dir, "font_cm.png")
    png = os.path.join(slot_dir, "name_cm.png")
    big = fonts.digit_metrics(font)
    zs = zone_size_cm(png, 1)
    if big is None or zs is None:
        return "нет цифр в атласе или зоны номера — без изменений", 1.0
    zw, zh = zs
    row_h = fonts.DIGIT_ROWS[0][1] - fonts.DIGIT_ROWS[0][0]           # 123 px — строка цифр во всю высоту зоны
    s0 = (zw / (2 * fonts.DIGIT_CELL)) / (zh / row_h)                 # клетка в игре шире атласа в столько раз
    gap_h = float(DIGIT_GAPS.get(kit, DIGIT_GAPS.get("*", DIGIT_GAP)))
    asp = DIGIT_ASPECTS.get(kit, DIGIT_ASPECTS.get("*", DIGIT_ASPECT))
    k_old = fonts.old_digit_widen(font)
    if asp == "keep":
        a_game = big["w"] * k_old / big["h"] * s0                   # ширина цифры к высоте в игре — как до 24.10
    else:
        a_game = big["w"] / big["h"] * float(asp)
    g_w = gap_h / a_game                                              # промежуток к ширине цифры

    # знак — целым числом px (промежуток в 5–8 px множителем без округления уходил на ±1 px): габарит (альфа > 40) =
    # видимая ширина под промежуток + кайма сглаживания, не шире клетки − 2 поля; растяжка сглаживает край (кайма
    # 1 → 2 px) — видимую ширину мерить по готовому атласу и, если вышла уже цели, — на 1 px шире (до DIGIT_FIT_ITER раз)
    files = {f: open(os.path.join(slot_dir, f + ".png"), "rb").read() for f in ("font_cm", "font_nm", "font_sm")}
    small = fonts.digit_metrics(font, small=True)
    cell_max = fonts.DIGIT_CELL - 2 * fonts.DIGIT_MARGIN
    want_e = fonts.DIGIT_CELL / (1.0 + g_w)                           # видимая ширина знака под промежуток, px
    w40 = min(round(want_e + big["w"] - big["w_edge"]), cell_max)
    k_s = 1.0
    if small is not None:
        k_s = min(round(fonts.SMALL_CELL / (1.0 + g_w) + small["w"] - small["w_edge"]),
                  fonts.SMALL_CELL - 2 * fonts.DIGIT_MARGIN) / small["w"]
    for it in range(DIGIT_FIT_ITER):
        if it:
            for f, b in files.items():
                open(os.path.join(slot_dir, f + ".png"), "wb").write(b)
        k = w40 / big["w"]
        used = fonts.widen_digits(slot_dir, k, k_s)
        after = fonts.digit_metrics(font)                             # готовый атлас: ширина знака — как вышла
        if after is None or after["w_edge"] >= round(want_e) or w40 >= cell_max:
            break
        w40 += 1
    w1, we1 = (after["w"], after["w_edge"]) if after else (big["w"] * k, want_e)
    s1 = a_game * big["h"] / w1                                       # растяжка клетки, при которой ширина цифры — a_game
    zone = scale_zones_x(png, (1,), s1 / s0)
    zs1 = zone_size_cm(png, 1)                                        # зона — целым числом столбцов: растяжка как вышла
    if zs1:
        s1 = (zs1[0] / (2 * fonts.DIGIT_CELL)) / (zs1[1] / row_h)
    gap0 = (fonts.DIGIT_CELL - big["w_edge"] * k_old) / big["h"] * s0
    gap1 = (fonts.DIGIT_CELL - we1) / big["h"] * s1
    rep = (f"знак {big['w']:.0f} px → {w1:.0f} (×{k:.3f}; было ×{k_old:.3f}), промежуток к высоте цифры "
           f"{gap0:.3f} → {gap1:.3f} (цель {gap_h:g}), ширина цифры {w1 / big['h'] * s1:.3f} высоты "
           f"({'как была' if asp == 'keep' else f'шрифт ×{float(asp):g}'}), зона номера ×{s1 / s0:.3f} "
           f"({zone.get(1, '—')} столбцов); малые ×{k_s:.3f}")
    if "big" in used and used["big"][0] < k - 1e-3:
        rep += f"; широкие знаки («4») — ×{used['big'][0]:.3f}: упор в клетку"
    return rep, 1.0 / k_s


def name_zone_rows(png, zone=0):
    """Высота зоны (строк карты) по среднему столбцу — у дуги (DET) по середине."""
    from PIL import Image
    a = np.asarray(Image.open(png).convert("RGBA"))
    m = (a[..., 0] > 128) & (a[..., 1] > 128) & (a[..., 2] == zone)
    xs = np.nonzero(m.any(0))[0]
    return int(m[:, xs[len(xs) // 2]].sum()) if len(xs) else 0


FONT_PLATE = False                 # профиль font_plate = true (22.10, агент yokes, PHI): фамилия на подложке — в атласе буквы на
#                                    непрозрачной плашке (у NHL 27 и у EA PHI: дома чёрные на белом, в гостях белые на
#                                    чёрном). Растяжка букв в клетках (name_font_fit, scale_glyphs) мерит буквы по альфе — у
#                                    плашки это вся строка: строки букв разрушались (сборка 1 PHI). С полем буквы атласа — как у
#                                    источника, высота букв для стандарта спины — по цвету против плашки (plate_letters)
PLATE_DIFF = 120                   # сумма |ΔR| + |ΔG| + |ΔB| до цвета плашки — больше: буква


def plate_letters(font_png):
    """Маска букв фамилии на плашке (font_plate): в строках букв (1–98, до столбца C и A) — пиксели не цвета плашки
    (медиана строк); вне строк букв — альфа, как раньше. -> маска 512²."""
    from PIL import Image
    from .fonts import CAPTAIN_BOX
    a = np.asarray(Image.open(font_png).convert("RGBA")).astype(np.int32)
    f = a[..., 3] > 40
    rows = a[1:98, :CAPTAIN_BOX[0]]
    op = rows[..., 3] > 200
    if op.mean() > 0.5:
        plate = np.median(rows[op][:, :3], axis=0)
        f[1:98, :CAPTAIN_BOX[0]] = op & (np.abs(rows[..., :3] - plate).sum(-1) > PLATE_DIFF)
    return f


def name_font_fit(slot_dir):
    """Профиль font_name_fit = "auto" (22.10, правило пользователя по SEA и VGK: «расстояние между буквами меньше»,
    «фамилии не крупнее»): буквы фамилии в клетках атласа — во всю высоту строки (sy) и шире, пока промежуток не станет
    ≤ NAME_FIT_GAP высоты буквы (sx), зона фамилии — ниже в k раз, чтобы высота букв в игре была как у MIN (игра
    вписывает клетку в зону: крупнее знак в клетке — крупнее и буква, и в той же мере меньше промежуток).
    -> (sx, sy, k, замер: ширина и высота букв, высота зоны)."""
    from PIL import Image
    from .fonts import NAME_ROWS, CAPTAIN_BOX
    a = np.asarray(Image.open(os.path.join(slot_dir, "font_cm.png")).convert("RGBA"))[..., 3] > 40
    ws, hs = [], []
    for row, (y0, y1) in enumerate(NAME_ROWS):
        cx = J.FONT_SLOTS[row]
        b = [0] + [(cx[i] + cx[i + 1]) // 2 for i in range(len(cx) - 1)] + [CAPTAIN_BOX[0]]
        for i in range(len(cx)):
            sub = a[y0:y1, b[i]:b[i + 1]]
            cols, rows_ = np.nonzero(sub.any(0))[0], np.nonzero(sub.any(1))[0]
            if len(cols):
                ws.append(cols[-1] - cols[0] + 1)
                hs.append(rows_[-1] - rows_[0] + 1)
    w, h, hmax = float(np.median(ws)), float(np.median(hs)), float(np.percentile(hs, 90))
    sy = max(1.0, (NAME_ROW_H - 1) / hmax)
    # широкий шрифт (DET: 25 × 37 px) при растяжке во всю высоту клетки слипался (промежуток 0,11, 22.10): равная
    # растяжка — не дальше NAME_FIT_GAP_MIN, высоту в игре добирает зона (стандарт спины)
    sy = max(1.0, min(sy, NAME_CELL_W / (w + NAME_FIT_GAP_MIN * h)))
    sx = min(max(sy, (NAME_CELL_W - NAME_FIT_GAP * h * sy) / w), (NAME_CELL_W - 2) / w)
    zh = name_zone_rows(os.path.join(slot_dir, "name_cm.png"))
    k = min(1.0, NAME_FIT_REF[0] * NAME_FIT_REF[1] / max(zh * h * sy, 1))
    return round(sx, 2), round(sy, 2), round(k, 2), (w, h, zh)


NAME_FIT_ITER = 2                  # font_name_fit = "measured": замеров готового атласа и пересчётов растяжки — не больше


def name_fit_measured(slot_dir, src_dir, sx, sy, w0):
    """Профиль font_name_fit = "measured" (22.10, агент review-b, SJS): name_font_fit считает растяжку по ширине букв до
    неё, а растяжка (LANCZOS) сглаживает край — по альфе > 40 буква выходит уже на 1–1,5 px (SJS: 18 px × 1,24 → 21 вместо
    22,3; промежуток 0,24 высоты при норме ≤ NAME_FIT_GAP, kitport lettering). Здесь — замер готового атласа тем же
    способом, что у kitport lettering, и растяжка заново от атласа формы (src_dir), пока ширина букв не станет не меньше
    NAME_CELL_W − NAME_FIT_GAP × высоты (с округлением вверх). Высота — как была. -> описание."""
    import math
    import shutil
    from .fonts import scale_glyphs
    rep = []
    for _ in range(NAME_FIT_ITER):
        w1, h1 = name_font_fit(slot_dir)[3][:2]
        tgt = math.ceil(NAME_CELL_W - NAME_FIT_GAP * h1)
        if w1 >= tgt:
            break
        sx = min(sx * tgt / w1, (NAME_CELL_W - 2) / w0)
        for f in ("font_cm", "font_nm", "font_sm"):
            shutil.copy2(os.path.join(src_dir, f + ".png"), os.path.join(slot_dir, f + ".png"))
        if FONT_CAPTAIN_X != 1.0:                        # буквы капитана — как в первом проходе
            scale_glyphs(slot_dir, 1.0, FONT_CAPTAIN_X)
        scale_glyphs(slot_dir, (round(sx, 3), sy))
        rep.append(f"буквы {w1:.0f} px (нужно ≥ {tgt}) → ×{sx:.3f}×{sy}")
    w1, h1 = name_font_fit(slot_dir)[3][:2]
    rep.append(f"итог: буквы {w1:.0f}×{h1:.0f} px, промежуток {(NAME_CELL_W - w1) / h1:.2f} высоты")
    return "; ".join(rep)


def lift_name_zone(png, cm, zone=0):
    """Зона фамилии карты номеров выше на спине на cm (сдвиг строк к большему v; пользователь, 22.10, SEA: фамилия
    вплотную к номеру и ниже, чем у других клубов, — «немного поднять»). Наезд на другую зону — отказ.
    -> (строк, верх зоны было, стало — м над полом)."""
    from PIL import Image
    a = np.asarray(Image.open(png).convert("RGBA")).copy()
    m = (a[..., 0] > 128) & (a[..., 1] > 128) & (a[..., 2] == zone)
    if not m.any():
        return None
    H = a.shape[0]
    k, b = back_m_per_v()
    n = int(round(cm / 100 / k * H))
    ys, xs = np.nonzero(m)
    if ys.max() + n >= H or ys.min() + n < 0:
        sys.exit(f"{png}: зона {zone} на {n} строк выходит за карту")
    other = (a[..., 0] > 128) & (a[..., 1] > 128) & (a[..., 2] < 16) & ~m      # фон — белый (B 255)
    if other[ys + n, xs].any():
        sys.exit(f"{png}: зона {zone} на {n} строк наезжает на другую зону")
    color = a[m][0].copy()
    a[m] = (255, 255, 255, 255)
    a[ys + n, xs] = color
    Image.fromarray(a, "RGBA").save(png)
    top = lambda r: round(k * (r + 1) / H + b, 3)
    return n, top(ys.max()), top(ys.max() + n)


LETTER_SHIFT_CM = None             # профиль letter_zone_shift_cm: [наружу, вверх] — места буквы капитана (5, 7) по груди
#                                    (VGK 22.10: герб упирался в букву — 22 см вместо 27; на свитерах NHL буква выше и
#                                    ближе к плечу); [crest_fit] на стадии kit — по сдвинутым местам
LETTER7_SHIFT_CM = None            # профиль letter_zone7_shift_cm (23.10, агент fix-a, NYR): [наружу, вверх] см — только
#                                    второе место буквы (зона 7), после letter_zone_shift_cm. У NYR оно лежало на «R» надписи
#                                    RANGERS (kitport audit: 16 % синего под зоной у выезда); место C (зона 5) и герб — как
#                                    были ([crest_fit] бережёт только зону 5). None — как было
LETTER_ZONE_SCALE = 1.0            # профиль letter_zone_scale (26.10, DET, пользователь после игры: «литеры поменьше, главное
#                                    лого побольше»): места буквы капитана (зоны 5, 7) — в k раз у их середины (scale_zones;
#                                    игра вписывает букву в зону — буква мельче); [crest_fit] на стадии kit — по уменьшенным
#                                    местам, герб растёт до них (crest_size_cm). 1 — как было
HELMET_LOGO_X = 1.0                # профиль helmet_logo_x (26.10, ANA; пользователь: «возможно, лого на шлеме растянут в
#                                    ширину»): наклейка шлема из источника — ×k по ширине у середины её рамки (helmet_squeeze).
#                                    У ANA helmetlogo NHL 27 шире той же эмблемы на свитере в 1,228 раза (маска 310×238 против
#                                    210×198, вся 532×385 против 360×320), а шлем Legacy наклейку не искажает (у EA лапа ANA на
#                                    шлеме 1,82, на свитере 1,87; круг BOS у NHL 27 — 82×83). 1 — как было


def zone_shift_px(png, zone, out_cm, up_cm):
    """Сдвиг зоны карты номеров в текселях (столбцы, строки) на out_cm наружу (от середины) и up_cm вверх по свитеру:
    якобиан (u, v) по (x, y) — МНК по текселям зоны на сетке слота."""
    from PIL import Image
    a = np.asarray(Image.open(png).convert("RGBA"))
    S = a.shape[0]
    m = (a[..., 0] > 128) & (a[..., 1] > 128) & (a[..., 2] == zone)
    if not m.any():
        return None
    M = mesh_for(0, 1, 2)
    tid, bar = kit3d.raster_uv(M, S)
    ys, xs = np.nonzero(m & (tid >= 0))
    P = (bar[ys, xs][:, :, None] * M["pos"][M["tri"][tid[ys, xs]]]).sum(1)
    X = np.c_[P[:, 0], P[:, 1], np.ones(len(ys))]
    A = np.linalg.lstsq(X, np.c_[xs, ys].astype(np.float64), rcond=None)[0]     # [x, y, 1] → (столбец, строка)
    dx = np.sign(P[:, 0].mean()) * out_cm / 100
    d = np.array([dx, up_cm / 100]) @ A[:2]
    return int(round(d[0])), int(round(d[1]))


def shift_zones(png, out_cm, up_cm, zones=None):
    """Зоны (по умолчанию LETTER_ZONES) карты номеров — сдвиг zone_shift_px; наезд на другую зону — отказ.
    -> {зона: (столбцов, строк)}."""
    from PIL import Image
    zones = LETTER_ZONES if zones is None else zones
    res = {z: zone_shift_px(png, z, out_cm, up_cm) for z in zones}
    a = np.asarray(Image.open(png).convert("RGBA")).copy()
    S = a.shape[0]
    for z, d in res.items():
        if d is None:
            continue
        m = (a[..., 0] > 128) & (a[..., 1] > 128) & (a[..., 2] == z)
        ys, xs = np.nonzero(m)
        ny, nx = ys + d[1], xs + d[0]
        if ny.min() < 0 or nx.min() < 0 or ny.max() >= S or nx.max() >= S:
            sys.exit(f"{png}: зона {z} со сдвигом {d} выходит за карту")
        color = a[m][0].copy()
        a[m] = (255, 255, 255, 255)
        other = (a[..., 0] > 128) & (a[..., 1] > 128) & (a[..., 2] < 16)
        if other[ny, nx].any():
            sys.exit(f"{png}: зона {z} со сдвигом {d} наезжает на другую зону")
        a[ny, nx] = color
    Image.fromarray(a, "RGBA").save(png)
    return res


def solid_zones(png, zones, fill=0.5):
    """Зоны карты номеров, заполненные прямоугольником (доля текселей зоны в её рамке ≥ fill). У EA бывают «зоны» из
    разрозненных текселей (DET 1_10_0: зона 7 — 241 тексель на рамке 80 × 87, мусор шаблона) — scale_zones залил бы
    рамку сплошной зоной (26.10: литера DET на 22 % вне развёртки, kitport audit)."""
    from PIL import Image
    a = np.asarray(Image.open(png).convert("RGBA"))
    out = []
    for z in zones:
        m = (a[..., 0] > 128) & (a[..., 1] > 128) & (a[..., 2] == z)
        if m.any():
            ys, xs = np.nonzero(m)
            if m.sum() >= fill * (ys.max() - ys.min() + 1) * (xs.max() - xs.min() + 1):
                out.append(z)
    return tuple(out)


def scale_zones(png, k, zones, anchor="center"):
    """Зоны карты номеров (прямоугольники на развёртке) — в k раз вокруг середины (игра вписывает знак в зону: мельче и
    номер); anchor = "top" — верх зоны на месте (номер на груди BUF: низ уходит с герба). -> {зона: (ширина × высота
    текселей было, стало)}."""
    from PIL import Image
    a = np.asarray(Image.open(png).convert("RGBA")).copy()
    res = {}
    for z in zones:
        m = (a[..., 0] > 128) & (a[..., 1] > 128) & (a[..., 2] == z)
        if not m.any():
            continue
        color = a[m][0].copy()
        ys, xs = np.nonzero(m)
        cy, cx = (ys.min() + ys.max() + 1) / 2.0, (xs.min() + xs.max() + 1) / 2.0
        nh = max(1, int(round((ys.max() - ys.min() + 1) * k)))   # размер — одним округлением: у зон 2 и 3 одинаковый
        nw = max(1, int(round((xs.max() - xs.min() + 1) * k)))   # (иначе 16 и 14 столбцов — номер на руках разной ширины)
        a[m] = (255, 255, 255, 255)
        y0, x0 = int(round(cy - nh / 2.0)), int(round(cx - nw / 2.0))
        if anchor == "top":
            y0 = int(ys.min())
        y1, x1 = y0 + nh, x0 + nw
        a[y0:y1, x0:x1] = color
        res[z] = (f"{xs.max() - xs.min() + 1}×{ys.max() - ys.min() + 1}", f"{x1 - x0}×{y1 - y0}")
    Image.fromarray(a, "RGBA").save(png)
    return res


def zones_to_point(png, zones, x_to, y_to):
    """Зоны карты номеров (2, 3) — середина на точку свитера своей стороны с |x| = x_to и высотой y_to (м), ближайшую на
    развёртке к прежней середине (сдвиг вокруг руки к верху: shift_zones «вверх» ведёт зону вдоль руки к плечу, высота
    почти не меняется — у ANA +6 см давали +1,3 см). -> {зона: (сдвиг строк, столбцов; точка было → стало)}."""
    from PIL import Image
    a = np.asarray(Image.open(png).convert("RGBA")).copy()
    S = a.shape[0]
    M = mesh_for(0, 1, 2)
    tid, bar = kit3d.raster_uv(M, S)
    yy, xx = np.nonzero(tid >= 0)
    P = (bar[yy, xx][:, :, None] * M["pos"][M["tri"][tid[yy, xx]]]).sum(1)
    res = {}
    for z in zones:
        m = (a[..., 0] > 128) & (a[..., 1] > 128) & (a[..., 2] == z)
        if not m.any():
            continue
        ys, xs = np.nonzero(m)
        cy, cx = int(round(ys.mean())), int(round(xs.mean()))
        dd = (yy - cy) ** 2 + (xx - cx) ** 2
        c3 = P[np.argmin(dd)]
        cand = ((np.sign(P[:, 0]) == np.sign(c3[0])) & (np.abs(np.abs(P[:, 0]) - x_to) < 0.004)
                & (np.abs(P[:, 1] - y_to) < 0.004))
        if not cand.any():
            sys.exit(f"{png}: зона {z} — на свитере нет точки |x| {x_to}, y {y_to} (sleeve_zone_at)")
        t = int(np.argmin(np.where(cand, dd, np.inf)))
        d = (int(yy[t] - cy), int(xx[t] - cx))
        ny, nx = ys + d[0], xs + d[1]
        if ny.min() < 0 or nx.min() < 0 or ny.max() >= S or nx.max() >= S:
            sys.exit(f"{png}: зона {z} со сдвигом {d} выходит за карту")
        color = a[m][0].copy()
        a[m] = (255, 255, 255, 255)
        other = (a[..., 0] > 128) & (a[..., 1] > 128) & (a[..., 2] < 16)
        if other[ny, nx].any():
            sys.exit(f"{png}: зона {z} со сдвигом {d} наезжает на другую зону")
        a[ny, nx] = color
        res[z] = (d, np.round(c3, 3).tolist(), np.round(P[t], 3).tolist())
    Image.fromarray(a, "RGBA").save(png)
    return res


def zones_move_z(png, zones, dz):
    """Зоны карты номеров (2, 3) — к груди (dz > 0, м) или к спине: середина — на точку свитера своей стороны, ближайшую
    в 3D к прежней середине + dz по z (у той же |x| ± 5 см). -> {зона: (сдвиг строк, столбцов; точка было → стало)}."""
    from PIL import Image
    a = np.asarray(Image.open(png).convert("RGBA")).copy()
    S = a.shape[0]
    M = mesh_for(0, 1, 2)
    tid, bar = kit3d.raster_uv(M, S)
    yy, xx = np.nonzero(tid >= 0)
    P = (bar[yy, xx][:, :, None] * M["pos"][M["tri"][tid[yy, xx]]]).sum(1)
    res = {}
    for z in zones:
        m = (a[..., 0] > 128) & (a[..., 1] > 128) & (a[..., 2] == z)
        if not m.any():
            continue
        ys, xs = np.nonzero(m)
        cy, cx = int(round(ys.mean())), int(round(xs.mean()))
        c3 = P[np.argmin((yy - cy) ** 2 + (xx - cx) ** 2)]
        tgt = c3 + np.array([0.0, 0.0, dz])
        side = (np.sign(P[:, 0]) == np.sign(c3[0])) & (np.abs(np.abs(P[:, 0]) - abs(c3[0])) < 0.05)
        t = int(np.argmin(np.where(side, np.linalg.norm(P - tgt, axis=1), np.inf)))
        d = (int(yy[t] - cy), int(xx[t] - cx))
        ny, nx = ys + d[0], xs + d[1]
        if ny.min() < 0 or nx.min() < 0 or ny.max() >= S or nx.max() >= S:
            sys.exit(f"{png}: зона {z} со сдвигом {d} выходит за карту")
        color = a[m][0].copy()
        a[m] = (255, 255, 255, 255)
        other = (a[..., 0] > 128) & (a[..., 1] > 128) & (a[..., 2] < 16)
        if other[ny, nx].any():
            sys.exit(f"{png}: зона {z} со сдвигом {d} наезжает на другую зону")
        a[ny, nx] = color
        res[z] = (d, np.round(c3, 3).tolist(), np.round(P[t], 3).tolist())
    Image.fromarray(a, "RGBA").save(png)
    return res


SLEEVE_ZONE_Z = 0.0                # профиль sleeve_zone_z_cm (23.10, пользователь после игры): номера на рукавах к груди (> 0)
#                                    или к спине, см — ANA «ближе к спине», CBJ «совсем немного ближе к груди», PHI «чуть ближе»
SLEEVE_ZONE_AT = None              # профиль sleeve_zone_at = [|x|, y] (м; 23.10, пользователь, ANA: «подними номера на руках,
#                                    если нужно — сделай поменьше»): середина зон номеров на рукавах — на верх руки у плеча
#                                    (zones_to_point). У ANA «крыло» полос наискосок у зоны MIN (|x| 0,385) — до самого
#                                    верха руки; оранжевое свободно ближе к плечу: |x| 0,33, y 1,55–1,60 (замер по кольцу)
SLEEVE_ZONE_SHIFT = None           # профиль sleeve_zone_shift_cm (23.10, пользователь: «номер на рукаве ложится на полосу —
#                                    поправь»; ANA, OTT, WPG): [наружу, вверх] см или { форма = [...] } — зоны номеров на
#                                    рукавах (2, 3) сдвинуты (shift_zones). У OTT полосы — красно-чёрно-красный блок на всё
#                                    плечо: номер — посередине чёрной полосы; у WPG выезда — целиком на тёмно-синем верхе
#                                    рукава (был у края белого); выше ~5 см зона выходит за развёртку рукава (номер режется)
SLEEVE_ZONE_SHIFT_KITS = None
SLEEVE_ZONE_SCALE = 1.0            # профиль sleeve_zone_scale: зоны номеров на рукавах в k раз (scale_zones) — ANA: «крыло»
#                                    полос наискосок до плеча, номер полного размера над ним не помещается
CHEST_ZONE = 6                     # зона карты номеров «номер на груди» (есть только у EA BUF 1_3_2, 1_3_4: у формы
#                                    2010–13 номер на груди слева; у NHL 27 его нет, игра ставит номер по карте образца)
CHEST_ZONE_SCALE = 1.0             # профиль chest_zone_scale (23.10, агент fix-a, BUF): зона 6 в k раз, верх на месте —
#                                    у герба 27 см низ зоны лежал на его верху (пользователь: «номер на груди поменьше
#                                    или лого пониже»). 1 — как было; 0 — зоны нет, номера на груди нет (BUF 23.10:
#                                    «убери», у NHL 27 номера на груди нет)


def chest_zone_gap(slot_dir):
    """Зазор от низа зоны «номер на груди» (CHEST_ZONE) до верха герба под ней: строки карты 256² (у герба — тексели
    свитера, отличные от ткани над зоной больше чем на 40). -> строк (< 0 — зона на гербе) или None (зоны нет)."""
    from PIL import Image
    n = np.asarray(Image.open(os.path.join(slot_dir, "name_cm.png")).convert("RGBA"))
    m = (n[..., 0] > 128) & (n[..., 1] > 128) & (n[..., 2] == CHEST_ZONE)
    if not m.any():
        return None
    ys, xs = np.nonzero(m)
    j = np.asarray(Image.open(os.path.join(slot_dir, "jersey_cm.png")).convert("RGB")).astype(np.float64)
    k = j.shape[0] // n.shape[0]
    x0, x1, y0, y1 = xs.min() * k, (xs.max() + 1) * k, ys.min() * k, (ys.max() + 1) * k
    fab = np.median(j[max(y0 - 3 * k, 0):y0 - k, x0:x1].reshape(-1, 3), 0)
    win = j[y0:min(y1 + 16 * k, j.shape[0]), x0:x1]
    hit = np.abs(win - fab).max(-1) > 40
    rows = np.nonzero(hit.any(1))[0]
    return round((rows[0] + y0 - y1) / k, 2) if len(rows) else None


# Номера «на рукаве» у ворота (профиль sleeve_zones_at = "shoulder", 22.10, FLA: пользователь — «у Флориды номера на
# ключицах, рядом с шеей, на кокетке, там, где у MIN логотипы на плечах; это особенность формы, сохранить»). Центр зоны —
# у плечевой нашивки MIN NHL 24 (kit_rules shoulder_r / shoulder_l: верх плеча у ворота, |x| 0,14–0,27 м, y 1,69–1,72;
# на развёртке Edge её центр — (0,398; 0,484) / (0,594; 0,484), замер 22.10): зона 2 — x < 0, зона 3 — x > 0. Центр — на
# 4 текселя 256² к плечу и на 3 к переду (верх плеча спереди, |x| ≈ 0,235 м, y ≈ 1,69 м): зона размера рукава у самой
# нашивки задевала вырез горловины на развёртке. Размер — тот же в см, что у зоны рукава (MIN 1_14_4: ~13,6 × 12,8 см),
# тексели — по якобиану развёртки (у ворота она реже)
SHOULDER_ZONE_UV = {2: (0.383, 0.496), 3: (0.611, 0.496)}
SLEEVE_ZONES_AT = None             # профиль sleeve_zones_at: None — рукав (как у MIN), "shoulder" — плечо у ворота (FLA)


def shoulder_zones(name_png):
    """Зоны 2 и 3 карты номеров — на плечи у ворота (SHOULDER_ZONE_UV), размер в см — как у прежней зоны. -> {зона:
    (u, v центра, ширина × высота текселей было → стало)}."""
    from PIL import Image
    a = np.asarray(Image.open(name_png).convert("RGBA")).copy()
    S = a.shape[0]
    M = mesh_for(0, 1, 2)
    tid, _ = kit3d.raster_uv(M, S)
    res = {}
    for z, (uc, vc) in SHOULDER_ZONE_UV.items():
        m = (a[..., 0] > 128) & (a[..., 1] > 128) & (a[..., 2] == z)
        if not m.any():
            continue
        ys, xs = np.nonzero(m)
        w0, h0 = int(xs.max() - xs.min() + 1), int(ys.max() - ys.min() + 1)
        t_old = tid[int(np.median(ys)), int(np.median(xs))]
        t_new = tid[int(vc * S), int(uc * S)]
        if t_old < 0 or t_new < 0:
            sys.exit(f"sleeve_zones_at: зона {z} — центр вне сетки")
        jo, jn = J.uv_jacobian(M, t_old, S), J.uv_jacobian(M, t_new, S)
        w = max(4, int(round(w0 * np.linalg.norm(jo[:, 0]) / np.linalg.norm(jn[:, 0]))))
        h = max(4, int(round(h0 * np.linalg.norm(jo[:, 1]) / np.linalg.norm(jn[:, 1]))))
        x0, y0 = int(round(uc * S - w / 2)), int(round(vc * S - h / 2))
        box = (slice(y0, y0 + h), slice(x0, x0 + w))
        other = (a[box][..., 2] != 255) & (a[box][..., 2] != z)
        if other.any() or (tid[box] < 0).mean() > 0.02:   # (1–2 текселя щели растра у шва развёртки — не край)
            sys.exit(f"sleeve_zones_at: зона {z} на плече задевает другую зону или край развёртки")
        a[m] = (255, 255, 255, 255)
        a[box] = (255, 255, z, 255)
        res[z] = ((uc, vc), f"{w0}×{h0} → {w}×{h}")
    Image.fromarray(a, "RGBA").save(name_png)
    return res


def copy_zones(dst_png, ref_png, zones):
    """Зоны карты номеров (R, G > 128, B = номер зоны) — с карты ref: у dst зона стирается (фон — белый), из ref
    переносится как есть. -> {зона: (v0 было, v0 стало)}."""
    from PIL import Image
    a = np.asarray(Image.open(dst_png).convert("RGBA")).copy()
    r = np.asarray(Image.open(ref_png).convert("RGBA"))
    res = {}
    for z in zones:
        md = (a[..., 0] > 128) & (a[..., 1] > 128) & (a[..., 2] == z)
        mr = (r[..., 0] > 128) & (r[..., 1] > 128) & (r[..., 2] == z)
        if not mr.any():
            continue
        res[z] = (round(float(np.nonzero(md)[0].min()) / a.shape[0], 3) if md.any() else None,
                  round(float(np.nonzero(mr)[0].min()) / a.shape[0], 3))
        a[md] = (255, 255, 255, 255)
        a[mr] = r[mr]
    Image.fromarray(a, "RGBA").save(dst_png)
    return res


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
    if FE_NO_LACES and COLLAR == "lace":                # шнуровка и люверсы — ткань свитера, во вставке — красный
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
    if FE_SHIELD and COLLAR == "lace":                  # щит — спрайтом: крупнее и ниже, на его месте — красный
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
    use_club(a.club)
    reg = json.load(open(os.path.join(REPO, "tools", "legacy_data", "nhl24_kits.json"), encoding="utf-8"))
    regmap = {(k["club"], k["kit"]): k for k in reg["kits"]}
    cur = os.path.join(WORK, "cur_kits")
    flat_kit = next((k for k, sp in SLOT_KITS.items() if sp["sock"] == "flat"), None)
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
        if FONT_NAME_SCALE != 1.0 or FONT_CAPTAIN_X != 1.0:   # знаки атласа крупнее в клетках (профиль; BOS 22.10)
            from .fonts import scale_glyphs
            print(f"  шрифт {kit}:", "; ".join(scale_glyphs(d, FONT_NAME_SCALE, FONT_CAPTAIN_X, name_anchor=FONT_NAME_ANCHOR)))
        for f in ("name_cm", "pant_cm", "pant_nm", "pant_sm"):
            shutil.copy2(os.path.join(leg, f + ".png"), os.path.join(d, f + ".png"))
        if spec.get("pant", "legacy") == "source":       # шорты источника (fb.pilot: 3D-перенос)
            shutil.copy2(os.path.join(src, "pant_cm.png"), os.path.join(d, "pant_cm.png"))
            from . import pant_decals                    # рельеф и блеск — под наши гербы, гербы образца стёрты
            info = pant_decals.relief(leg, d, os.path.join(src, pant_decals.MASKS))   # (23.10, пользователь, DET)
            print(f"  шорты {kit}: рельеф —", pant_decals.relief_note(info))
        elif spec.get("pant_tint") == "source":          # шорты Legacy — основным цветом шорт источника (NYR, 23.10)
            print(f"  шорты {kit}: оттенок источника (pant_tint) —",
                  tint_pant(os.path.join(d, "pant_cm.png"), os.path.join(src, "pant_cm.png")))
        if NAME_ZONES_FROM:                             # фамилия, номер, буква — как у формы Legacy (профиль; VGK)
            ref = os.path.join(cur, NAME_ZONES_FROM)
            if not os.path.exists(os.path.join(ref, "kit.json")):
                J.unpack_kit(NAME_ZONES_FROM, ref)
            print(f"  фамилия, номер, буква {kit}: зоны {NAME_ZONES} — как у {NAME_ZONES_FROM}:",
                  copy_zones(os.path.join(d, "name_cm.png"), os.path.join(ref, "name_cm.png"), NAME_ZONES))
        if kit in LETTER_ZONES_FROM:
            ref = os.path.join(cur, SLOT_KITS[LETTER_ZONES_FROM[kit]]["legacy"])
            if not os.path.exists(os.path.join(ref, "kit.json")):
                J.unpack_kit(SLOT_KITS[LETTER_ZONES_FROM[kit]]["legacy"], ref)
            print(f"  буква капитана {kit}: зоны {LETTER_ZONES} — как у {LETTER_ZONES_FROM[kit]}:",
                  copy_zones(os.path.join(d, "name_cm.png"), os.path.join(ref, "name_cm.png"), LETTER_ZONES))
        if LETTER_SHIFT_CM:                             # места буквы — выше и к плечу (профиль letter_zone_shift_cm; VGK)
            print(f"  буква капитана {kit}: зоны {LETTER_ZONES} сдвинуты на {LETTER_SHIFT_CM} см (наружу, вверх):",
                  shift_zones(os.path.join(d, "name_cm.png"), *LETTER_SHIFT_CM))
        if LETTER7_SHIFT_CM:                            # второе место буквы — с надписи-герба (letter_zone7_shift_cm; NYR)
            print(f"  буква капитана {kit}: зона 7 сдвинута на {LETTER7_SHIFT_CM} см (наружу, вверх):",
                  shift_zones(os.path.join(d, "name_cm.png"), *LETTER7_SHIFT_CM, zones=(7,)))
        if LETTER_ZONE_SCALE != 1.0:                    # буква капитана мельче (профиль letter_zone_scale; DET 26.10)
            zs = solid_zones(os.path.join(d, "name_cm.png"), LETTER_ZONES)   # разрозненные «зоны» EA — как есть
            print(f"  буква капитана {kit}: зоны {zs} ×{LETTER_ZONE_SCALE} (было, стало):",
                  scale_zones(os.path.join(d, "name_cm.png"), LETTER_ZONE_SCALE, zs))
        std = LETTERING == "standard"
        if FONT_PLATE:                                  # фамилия на подложке (PHI): буквы атласа — как у источника
            print(f"  фамилия {kit}: на подложке (font_plate) — атлас букв как у источника, без растяжки")
        elif FONT_NAME_FIT in ("auto", "measured") or (std and FONT_NAME_SCALE == 1.0):   # шрифт фамилии расчётом (VGK
            from .fonts import scale_glyphs             # 22.10); в стандарте спины — у всех, у кого нет своих font_name_scale
            sx, sy, k_, (w_, h_, zh_) = name_font_fit(d)
            print(f"  фамилия {kit}: буквы {w_:.0f}×{h_:.0f} px, зона {zh_} строк → буквы ×{sx}×{sy}, зона ×{k_}")
            print(f"  шрифт {kit}:", "; ".join(scale_glyphs(d, (sx, sy))))   # буквы капитана — выше, своим полем
            if FONT_NAME_FIT == "measured":              # промежуток — по готовому атласу (SJS 22.10: край сглажен)
                print(f"  фамилия {kit} (font_name_fit = measured):", name_fit_measured(d, src, sx, sy, w_))
            if not std:                                 # в стандарте высоту зоны задаёт standard_lettering
                print(f"  фамилия {kit}: зона ×{k_} по высоте (было, стало):",
                      scale_name_zone(os.path.join(d, "name_cm.png"), k_))
        if std:                                         # стандарт спины (22.10): размеры и место фамилии и номера
            print(f"  спина {kit}: стандарт —", standard_lettering(d))
        sleeve_k = 1.0
        if std:                                         # промежуток цифр — как у настоящих форм (24.10; было 22.10 — fit_digits)
            rep_, sleeve_k = digit_spacing(d, kit)
            print(f"  цифры номера {kit}:", rep_)
        if NAME_ZONE_SCALE != 1.0 and not std:          # зона фамилии ниже (профиль name_zone_scale; LAK, DET 22.10)
            print(f"  фамилия {kit}: зона ×{NAME_ZONE_SCALE} по высоте (было, стало):",
                  scale_name_zone(os.path.join(d, "name_cm.png"), NAME_ZONE_SCALE))
        if NAME_ZONE_LIFT and not std:                  # зона фамилии выше (профиль name_zone_lift_cm; SEA 22.10)
            print(f"  фамилия {kit}: зона выше на {NAME_ZONE_LIFT} см (строк карты, верх зоны — м):",
                  lift_name_zone(os.path.join(d, "name_cm.png"), NAME_ZONE_LIFT))
        if SLEEVE_ZONES_FROM not in ("own", spec["legacy"]):
            ref = os.path.join(cur, SLEEVE_ZONES_FROM)
            if not os.path.exists(os.path.join(ref, "kit.json")):
                J.unpack_kit(SLEEVE_ZONES_FROM, ref)
            print(f"  номера на рукавах {kit}: зоны {SLEEVE_ZONES} — как у {SLEEVE_ZONES_FROM}:",
                  copy_zones(os.path.join(d, "name_cm.png"), os.path.join(ref, "name_cm.png"), SLEEVE_ZONES))
        if SLEEVE_ZONES_AT == "shoulder":                # номера не на рукаве, а на плечах у ворота (FLA, 22.10)
            print(f"  номера на плечах {kit} (sleeve_zones_at): зоны {SLEEVE_ZONES} — у ворота, на месте нашивок MIN:",
                  shoulder_zones(os.path.join(d, "name_cm.png")))
        if SLEEVE_ZONE_SCALE != 1.0:                    # номер на рукаве мельче (профиль sleeve_zone_scale; ANA 23.10)
            print(f"  номера на рукавах {kit}: зоны {SLEEVE_ZONES} ×{SLEEVE_ZONE_SCALE}:",
                  scale_zones(os.path.join(d, "name_cm.png"), SLEEVE_ZONE_SCALE, SLEEVE_ZONES))
        if SLEEVE_ZONE_AT:                               # номер на рукаве — на верх руки у плеча (профиль sleeve_zone_at; ANA)
            print(f"  номера на рукавах {kit}: зоны {SLEEVE_ZONES} — середина на |x|, y {SLEEVE_ZONE_AT} м:",
                  zones_to_point(os.path.join(d, "name_cm.png"), SLEEVE_ZONES, *SLEEVE_ZONE_AT))
        if SLEEVE_ZONE_SHIFT:                            # номер на рукаве — мимо полос (профиль sleeve_zone_shift_cm)
            print(f"  номера на рукавах {kit}: зоны {SLEEVE_ZONES} сдвинуты на {SLEEVE_ZONE_SHIFT} см (наружу, вверх):",
                  shift_zones(os.path.join(d, "name_cm.png"), *SLEEVE_ZONE_SHIFT, zones=SLEEVE_ZONES))
        if SLEEVE_ZONE_Z:                                # номер на рукаве к груди / к спине (профиль sleeve_zone_z_cm)
            print(f"  номера на рукавах {kit}: зоны {SLEEVE_ZONES} к груди на {SLEEVE_ZONE_Z * 100:+.1f} см:",
                  zones_move_z(os.path.join(d, "name_cm.png"), SLEEVE_ZONES, SLEEVE_ZONE_Z))
        if abs(sleeve_k - 1.0) > 1e-3:                   # номер на рукаве: малые цифры шире в клетках, зоны уже — ширина
            print(f"  номера на рукавах {kit}: зоны {SLEEVE_ZONES} уже ×{sleeve_k:.3f} (цифры ближе, ширина прежняя):",
                  scale_zones_x(os.path.join(d, "name_cm.png"), SLEEVE_ZONES, sleeve_k))   # цифры прежняя (24.10)
        if CHEST_ZONE_SCALE == 0.0:                    # номера на груди нет (BUF, пользователь 23.10: «убери» — у NHL 27
            from PIL import Image                        # его нет): зона 6 карты номеров — снята
            a_ = np.asarray(Image.open(os.path.join(d, "name_cm.png")).convert("RGBA")).copy()
            m_ = (a_[..., 0] > 128) & (a_[..., 1] > 128) & (a_[..., 2] == CHEST_ZONE)
            a_[m_] = (255, 255, 255, 255)
            Image.fromarray(a_, "RGBA").save(os.path.join(d, "name_cm.png"))
            print(f"  номер на груди {kit}: зона {CHEST_ZONE} снята ({int(m_.sum())} текселей)")
        elif CHEST_ZONE_SCALE != 1.0:                    # номер на груди мельче, верх на месте (профиль chest_zone_scale;
            g0 = chest_zone_gap(d)                       # BUF 23.10: низ зоны лежал на гербе)
            cz = scale_zones(os.path.join(d, "name_cm.png"), CHEST_ZONE_SCALE, (CHEST_ZONE,), anchor="top")
            print(f"  номер на груди {kit}: зона {CHEST_ZONE} ×{CHEST_ZONE_SCALE}, верх на месте: {cz}; до герба строк "
                  f"было {g0}, стало {chest_zone_gap(d)}")
        flat_src = os.path.join(KITS_OUT, f"{a.club}_{flat_kit or kit}", "sock_cm.png")
        if spec["sock"] == "auto":                       # ровные полосы по гетрам источника этой формы
            parts = sock_parts_auto(os.path.join(src, "sock_cm.png"))
            im, info = flat_sock(os.path.join(src, "sock_cm.png"), parts)
            im.save(os.path.join(d, "sock_cm.png"))
            print(f"  гетры {kit}: ткань {parts[0][1]}, полосы {[(int(w), c) for w, c in parts[1:]]}, строки "
                  f"{info[0]:.1f}–{info[1]:.1f}")
        elif spec["sock"] == "flat":
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
        if len(tpl) != len(new):                         # номер другой длины (0_17_10): контейнер — форма стиля 0 из архива
            cont = slot_container(len(new))             # с номером той же длины (имена растров переписываются на месте)
            if cont:
                cmd += ["--container", cont]
        rr = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        print(rr.stdout[-800:], rr.stderr[-800:])
        if rr.returncode:
            sys.exit(f"{kit}: kitpaint pack — ошибка")
        ls = spec["legacy"].split("_")
        if spec.get("helmet_logo", "legacy") == "source":
            h = helmet_from_source(a.club, kit, ls[1], ls[2], r["art"], r["variant"], a.out)
        else:
            h = J.helmet_copy(ls[1], ls[2], r["art"], r["variant"], a.out)
        print(f"{a.club} {spec['kit']} → {new}: шаблон {tpl}, превью (перед ворота на uv0: {n} текселей), "
              f"наклейка на шлем {h}")


def slot_container(n):
    """Форма стиля SLOT_STYLE из архива Legacy с номером длины n («0_108_0» под «0_17_10») — контейнер kitpaint."""
    d = os.path.join(REPO, "game", "other", "legacy", "big", "nocacherender", "rendering", "jersey")
    tags = sorted(f[7:-4] for f in os.listdir(d) if f.startswith(f"texlib_{SLOT_STYLE}_") and f.endswith(".rx2"))
    return next((t for t in tags if len(t) == n), None)


HELMET_CONTAINERS = ("0_1_0", "10_1_0", "127_1_0")   # наклейки EA по длине «A_1_V» (5, 6, 7 знаков, docs/kitport.md §2.3)


def helmet_squeeze(img, k):
    """RGBA наклейки: рамка по альфе — в k раз по ширине у её середины, высота та же (helmet_logo_x). Уменьшение — как у
    helmet_from_source: с премультипликацией, альфа отдельно (кайма без тёмного ореола)."""
    from PIL import Image
    bb = img.getbbox()
    if not bb or k == 1.0:
        return img
    part = img.crop(bb)
    nw = max(1, int(round(part.width * k)))
    a = np.asarray(part).astype(np.float64)
    a[..., :3] *= a[..., 3:4] / 255.0
    pm = np.asarray(Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)).resize((nw, part.height), Image.LANCZOS))
    pm = pm.astype(np.float64)
    al = np.asarray(part.getchannel("A").resize((nw, part.height), Image.LANCZOS)).astype(np.float64)
    pm[..., :3] = np.where(al[..., None] > 0, pm[..., :3] * 255.0 / np.maximum(al[..., None], 1), 0)
    pm[..., 3] = al
    out = Image.new("RGBA", img.size, (0, 0, 0, 0))
    out.paste(Image.fromarray(np.clip(np.round(pm), 0, 255).astype(np.uint8), "RGBA"),
              (int(round((bb[0] + bb[2]) / 2 - nw / 2)), bb[1]))
    return out


def helmet_from_source(code, kit, leg_art, leg_v, art, v, dst_root):
    """Наклейка на шлем формы стиля SLOT_STYLE — helmetlogo источника (у NHL 27 — реклама на шлеме, 1024×512) в
    контейнере наклейки EA той же длины имени (образец формы или HELMET_CONTAINERS), 256×128 DXT5. -> путь или None."""
    from PIL import Image
    from . import kitsrc
    from .jersey_hybrid import CLUB_NAME
    import kitpaint as kp
    import teamart as ta
    club = CLUB_NAME[code]
    src = kitsrc.folder(kit)                             # папка комплекта источника (профиль source_kits)
    png = os.path.join(kitsrc.extract_root(), f"club_{club}", "character", "skater", "league", "nhl", club, "adidas", src,
                       f"helmetlogo_adidas_{club}_{src}_0_color.png")
    if not os.path.exists(png):
        print(f"  наклейка {kit}: нет {png} — как у образца")
        return J.helmet_copy(leg_art, leg_v, art, v, dst_root)
    want = len(f"{art}_{SLOT_STYLE}_{v}")
    rel = None
    for tag in (f"{leg_art}_1_{leg_v}",) + HELMET_CONTAINERS:
        if len(tag) == want:
            ta_, _, tv = tag.split("_")
            rel = J.helmet_copy(ta_, tv, art, v, dst_root)
            if rel:
                break
    if rel is None:
        return None
    path = os.path.join(dst_root, *rel.split("/"))
    rwf = ta.Rw4.load(path)
    t = next(t for t in rwf.textures if t.name.endswith("_0.Raster") or t.name.endswith("_0"))
    w, h, _ = kp.tex_decode(rwf, t)
    img = helmet_squeeze(Image.open(png).convert("RGBA"), HELMET_LOGO_X)   # у́же — профиль helmet_logo_x (ANA, 26.10)
    if HELMET_LOGO_X != 1.0:
        print(f"  наклейка {kit}: по ширине ×{HELMET_LOGO_X} (helmet_logo_x)")
    a = np.asarray(img).astype(np.float64)
    a[..., :3] *= a[..., 3:4] / 255.0                    # уменьшение с премультипликацией (кайма без тёмного ореола)
    small = np.asarray(Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)).resize((w, h), Image.LANCZOS)).astype(np.float64)
    al = np.asarray(img.getchannel("A").resize((w, h), Image.LANCZOS)).astype(np.float64)
    small[..., :3] = np.where(al[..., None] > 0, small[..., :3] * 255.0 / np.maximum(al[..., None], 1), 0)
    small[..., 3] = al
    kp.tex_replace(rwf, t, np.clip(np.round(small), 0, 255).astype(np.uint8).tobytes(), w, h)
    open(path, "wb").write(rwf.bytes())
    return rel


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
    n_ice = pack_ice_centers(man, cache)                 # центры льда NHL 27 у всех клубов (23.10)
    if n_ice:
        print(f"центры льда NHL 27 (fb.ice --source nhl27): {n_ice}")
    from . import sticks                                 # клюшки NHL 27 и белая CCM в слоте D (23.10, stick_slots.toml)
    n_stick = sticks.pack(man, cache)
    if n_stick:
        print(f"клюшки (fb.sticks, stick_slots.toml): {n_stick}, имён {len(man.get('loc', {}))}")
    sys.path.insert(0, os.path.join(REPO, "tools"))
    import stadium                                       # кресла арен (24.10, arena_seats.toml: status = approved)
    n_crowd = stadium.pack(man, cache)
    if n_crowd:
        print(f"кресла арен (stadium.py, arena_seats.toml): {n_crowd}")
    from . import skates                                 # коньки NHL 27 (23.10, skate_slots.toml)
    n_skate = skates.pack(man, cache)
    if n_skate:
        print(f"коньки (fb.skates, skate_slots.toml): {n_skate}, имён всего {len(man.get('loc', {}))}")
    # в пакет (в игру) — только одобренные клубы: все формы слота с default = true (правило 21.10); черновики — нет
    prof = club_profiles()
    built = [c for c in prof if all(os.path.isdir(os.path.join(WORK, "slot", "kits", f"{c}_{k}"))
                                    for k in prof[c].get("slot", {}))]
    clubs = [c for c in built if prof[c].get("slot") and all(s.get("default") for s in prof[c]["slot"].values())]
    print("клубы пакета (профиль, собранный слот, одобрены):", clubs,
          f"; не одобрены (default) — не в пакете: {sorted(set(built) - set(clubs))}" if set(built) - set(clubs) else "")
    for code in clubs:
        use_club(code)
        pack_club(a, code, regmap, man, have, put, phase=2 + list(prof).index(code))
    with open(os.path.join(a.out, "manifest.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(man, f, ensure_ascii=False, indent=1)
    print(f"{a.out}: сеток заменено {n_mesh}, форм {len(man['kits'])}, файлов {len(man['files'])}")


ICE_CENTERS = os.path.join(REPO, "game", "work", "nhl27", "out", "ice")   # центры льда NHL 27 (fb.ice --source nhl27 build)


def pack_ice_centers(man, cache):
    """Центры льда NHL 27 в пакет (23.10, пользователь: «перенести центры льда для всех команд»): PNG из ICE_CENTERS
    (python -m fb.ice --source nhl27 build: картинка NHL 27 на основе Legacy — диск, кольцо, полоса под красную линию)
    → centerlogo_<арт>_cm.rx2 по шаблону (наш файл из legacy-data/out — SEA, VGK, UTA, иначе — архив Legacy), запись
    type center в manifest (прежняя — заменяется: у CHI, MIN, SEA, VGK были центры NHL 24). Нет папки — ничего. -> число."""
    import hashlib
    from PIL import Image
    from . import ice, pack
    if not os.path.isdir(ICE_CENTERS):
        return 0
    n = 0
    for club, art, code, num in ice.clubs("nhl27"):
        png = os.path.join(ICE_CENTERS, f"centerlogo_{code}.png")
        rel = f"rendering/icesurface/centerlogo_{art}_cm.rx2"
        ours = os.path.join(REPO, "game", "work", "legacy-data", "out", *rel.split("/"))
        tpl = ours if os.path.exists(ours) else pack.legacy_has(rel)
        if not os.path.exists(png) or not tpl:
            print(f"  центр льда {code}: нет", "PNG" if not os.path.exists(png) else "шаблона")
            continue
        q = os.path.join(cache, *rel.split("/"))
        pack.write_rx2_rgba(tpl, Image.open(png), q)
        e = {"file": rel, "type": "center", "md5": hashlib.md5(open(q, "rb").read()).hexdigest(),
             "size": os.path.getsize(q), "club": code, "action": "replace",
             "note": f"центр льда NHL 27 (ice_centerlogo_{num}) на основе Legacy (диск, кольцо, полоса), fb.ice"}
        man["files"] = [x for x in man["files"] if x["file"] != rel] + [e]
        n += 1
    return n


def pack_club(a, code, regmap, man, have, put, phase=2):
    """Формы клуба code (SLOT_KITS профиля) в пакет: файлы слота и строки manifest."""
    for kit, spec in SLOT_KITS.items():
        r = regmap[(code, spec["kit"])]
        new = f"{SLOT_STYLE}_{r['art']}_{r['variant']}"
        files = {"jersey": f"rendering/jersey/texlib_{new}.rx2", "name": f"rendering/jersey/name_{new}_cm.rx2",
                 "pant": f"rendering/pant/texlib_{new}.rx2", "sock": f"rendering/sock/sock_{new}_cm.rx2",
                 "fe": f"fe/ion/artassets/jerseys/jersey_{new}.big",
                 "helmet": f"rendering/logo/texlib_{r['art']}_{SLOT_STYLE}_{r['variant']}.rx2"}
        notes = {"jersey": "свитер Edge с передом ворота NHL 24 (fb.edge_kit) и шрифт NHL 24",
                 "name": f"карта номера и фамилии — как у формы {spec['legacy']}",
                 "pant": (f"шорты — источника ({SOURCE_NAME()}, 3D-перенос)" if spec.get("pant") == "source"
                          else f"шорты — как у основной формы {spec['legacy']}"),
                 "sock": ({"flat": "гетры — свои полосы ровными строками", "auto": f"гетры — полосы гетр {SOURCE_NAME()} "
                           "ровными строками"}.get(spec["sock"], f"гетры — как у основной формы {spec['legacy']}")),
                 "fe": "превью меню в позе EA (fb.pilot.fe_preview_ea)",
                 "helmet": (f"наклейка на шлем — {SOURCE_NAME()} (helmetlogo)" if spec.get("helmet_logo") == "source"
                            else f"наклейка на шлем — как у формы {spec['legacy']}")}
        for typ, rel in files.items():
            if rel in have:
                sys.exit(f"{rel}: уже в пакете")
            md, sz = put(rel)
            man["files"].append({"file": rel, "type": typ, "md5": md, "size": sz, "action": "add", "note": notes[typ],
                                 "club": code, "kit": spec["kit"]})
        man["kits"].append({"club": code, "kit": spec["kit"], "variant": r["variant"],
                            "islightcolor": 0 if kit == "home" else 1, "label": spec["label"], "helmet": kit,
                            "phase": phase,  # nhl24.py: строки и шлемы — после adidas, клуб за клубом в порядке
                            #                  профилей (edge_clubs.toml): новый клуб — в конец, строки уже
                            #                  поставленных не сдвигаются (21.10, BOS встал бы раньше MIN)
                            "default": bool(spec.get("default"))})   # одобрена — форма по умолчанию (дом / выезд)
    man["note"] = (man.get("note", "") + f" {code}: формы «{SLOT_KITS['home']['label']}» / «{SLOT_KITS['away']['label']}» "
                   f"({SOURCE_NAME()}) на своей сетке Edge с передом ворота NHL 24 в слоте стиля 0 (сетки adidas сняты, "
                   "пользователь 19.10).")


def SOURCE_NAME():
    from . import kitsrc
    return {"nhl24": "NHL 24", "nhl27": "NHL 27"}[kitsrc.source()]


def cmd_shield(a):
    """Щит NHL без сборки (расчёт, как в kit): где встанет при параметрах профиля, низ кромки посередине переда, зазор
    (как «до кромки» у kitport check), зазор у источника; при щите по зазору (shield_gap_mm или --gap) — и сдвиг под
    него. Ничего не пишет. Для проверки расчёта на готовых клубах и для подбора поля профиля:

        python -m fb.edge_kit shield --club TBL --kits away,home [--gap 4]
    """
    from . import kit_hybrid, pilot
    global SHIELD_GAP_MM
    use_club(a.club)
    if a.gap is not None:
        SHIELD_GAP_MM = a.gap
    pilot.extract_club(Hy.CLUB_NAME[a.club])
    E2, _ = deform(load(0, 1, 2), n24_ring_for(0, 1, 2))
    E2 = island().apply(E2)
    mesh = {k: E2[k] for k in ("pos", "uv", "nrm", "tri")}
    dst = kit_hybrid.merge(mesh, kit3d.load_legacy(kit_hybrid.LEGACY_SHIRT))
    src = kit3d.load_nhl24(pilot.MESH["adidas"])
    tid24, _ = kit3d.raster_uv(src, 1024)
    P, _, _ = front_column(mesh)
    for kit in a.kits.split(","):
        comp = kit3d.load_tex(J.n24_tex(Hy.CLUB_NAME[a.club], kit, "color"))
        base = kit3d.load_tex(J.n24_tex(Hy.CLUB_NAME[a.club], kit, "base_color"))
        defaults, rules = kit_hybrid.load_rules(kit_hybrid.RULES, a.club, kit, [])
        sh = {k: v for k, v in rules["neck_shield"].items() if k != "legacy_uv"}
        rules["neck_shield"] = dict(sh, offset_cm=SHIELD_OFFSET_CM, scale=SHIELD_SCALE)   # как load_rules в cmd_kit
        lab, patches = kit_hybrid.find_patches(comp, base, defaults)
        placed, soft = kit_hybrid.plan_decals(comp, lab, patches, rules, defaults, src, dst, tid24)
        pl = next((p for p in placed if p["name"] == "neck_shield"), None)
        trim = trim_rule(a.club, kit, mesh, with_yoke=(a.club, kit) in YOKE)
        edge_y, top_y = trim_front_bottom(trim)
        sg = source_gap_for(a.club, kit)
        print(f"{a.club} {kit}: край ворота посередине {top_y:.4f} м, низ кромки {edge_y:.4f} м; у источника: "
              f"щит {sg['shield_top']} м, {sg['gap_mm']} мм от {sg['ref']} ({sg['edge']} м)")
        if pl is None:
            print("  щит не найден среди нашивок источника")
            continue
        t0 = shield_top_on(P, pl["_frame"], soft[pl["_lid"]], comp)
        print(f"  по shield_offset_cm {SHIELD_OFFSET_CM}, масштаб {SHIELD_SCALE}: верх щита "
              + (f"{t0:.4f} м, до кромки {(edge_y - t0) * 1000:.1f} мм" if t0 else "не найден"))
        if SHIELD_GAP_MM is not None:
            fit_shield_gap(placed, soft, comp, src, dst, tid24, trim, a.club, kit)


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
    p = sub.add_parser("shield", help="щит NHL без сборки: место, низ кромки, зазор (как kitport check)")
    p.add_argument("--club", default="MIN")
    p.add_argument("--kits", default="away,home")
    p.add_argument("--gap", type=float, default=None, help="мм: и сдвиг щита под этот зазор под кромкой")
    a = ap.parse_args()
    {"preview": cmd_preview, "kit": cmd_kit, "meshes": cmd_meshes, "slot": cmd_slot, "pack": cmd_pack,
     "shield": cmd_shield}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
