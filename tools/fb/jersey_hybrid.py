"""Гибрид свитера: сетка Reebok Edge Legacy (стиль 1) с передом ворота adidas NHL 24 — проба 18.10.2026 (MIN).

Просьба пользователя: взять основную модель Edge и заменить только перед ворота (V-вырез) на перед ворота NHL 24
(узкий ворот у шеи и ровная грудь под ним — место под щит NHL); спину ворота (поднимается вдоль шеи) не трогать;
текстура — основная форма NHL 24.

Сетка:
- Edge (установленная у пользователя, с весами jersey10) без треугольников у переда ворота: зона — до DCUT по
  поверхности от края горловины Edge, по углу вокруг шеи θ (0 — спереди) во всю ширину до TH_A, к TH_B — на нет.
- Кусок adidas (наш стиль 0 того же варианта и детализации — тело там уже по поверхности Edge, ворот NHL 24 поднят
  над «рубашкой» по секторам) — та же зона, на CUT_GAP меньше; подкладка ворота — в секторе переда.
- Бока: край ворота adidas (у шеи, r ≈ 7–8 см) от TH_A к TH_B плавно переходит в край горловины Edge (r ≈ 12–13 см),
  ткань куска — следом (гармоническое продолжение сдвигов).
- Шов: полоса треугольников между краем выреза Edge и краем куска (молния по кратчайшей диагонали).

Развёртка: Edge и полоса шва — UV Edge; кусок adidas — острова его UV NHL 24, сжатые до плотности текселей Edge и
разложенные в свободные углы текстуры Edge (там пусто). Текстура: перенос NHL 24 на Edge (fb.pilot, out/all) с низом
«от края» (fb.hem) + острова куска из текстуры NHL 24 как есть.

  python -m fb.jersey_hybrid build [--out DIR]      # сетки jersey_0_S_2_T_P_L (S — слот) → DIR
  python -m fb.jersey_hybrid preview OUT.png        # рендер: Edge | adidas | гибрид, шашки и швы
"""
import argparse
import os
import sys

import numpy as np

from . import kit3d
from . import jersey_mesh as J
from .cas import REPO

sys.path.insert(0, os.path.join(REPO, "tools"))
import rw4mesh as rw  # noqa: E402

WORK = os.path.join(REPO, "game", "work", "nhl24", "hybrid")
OUT = os.path.join(REPO, "game", "work", "legacy-data", "models", "hybrid")   # сетки в раскладке cache:
SKATERS = [(t, p) for t in range(4) for p in range(2)]
GOALIES = [("g0", 0), ("g1", 0)]
TH_A, TH_B = 60.0, 105.0           # град: перед ворота adidas во всю высоту до TH_A, к TH_B — сходит на нет
TH_RING = 85.0                     # град: к этому углу край ворота adidas уже на сгибе ворота Edge
DCUT = (0.085, 0.045)              # м по прямой от губы ворота Edge: у середины груди (|θ| ≤ 10°: вся шнуровка
#                                    adidas до 1,55 м) и с 25° —
#                                    там буквы C/A (зоны 5, 7 карты номеров EA MIN: θ 27–57°, 5 см от губы) — на Edge
CUT_GAP = 0.003                    # край куска adidas — на столько ближе к шее, между ними — полоса шва
SNAP_KEEP = 0.02                   # м от края ворота adidas: кромка — без прижатия к Edge
CUT_SNAP = 0.03                    # м до линии выреза: край куска adidas — на поверхность Edge
D_STRIP = 0.022                    # м: сзади и с боков кусок adidas — полоса ворота до 2,2 см от края (кромка 0,6–0,9)
LINING_KEEP = 0.03                 # м от края ворота adidas: подкладка глубже — не в куске (не видна)
RIM_K = 1.25                       # растяжение d у края кромки при укладке на Edge
RIM_K_END = 0.018                  # м от края: дальше — без растяжения
CUT_SMOOTH = 5.0                   # град: линия выреза — от сгиба Edge, сглаженного по углу
MERGE_EPS = 0.0003                 # м: вершины куска ближе — одна точка
REFINE_TH = 6.0                    # град: полоса ворота adidas сзади и с боков — разрезы по радиальным линиям через 6°
REFINE_D = (0.004, 0.010)          # м: и по линиям вдоль края (сгиб Edge изогнут сильнее, чем шаг сетки)
D_MAP = (0.024, 0.032)             # м от края adidas: полоса — «от края» на ворот Edge, дальше — на нет (шире —
#                                    в переходе перекашивало границу кокетки: она там в 4,5 см от края)
NRM_BLEND = 0.035                  # м от края куска к вороту: нормали Edge → свои
LIP_BIN = 4.0                      # град: шаг губы ворота Edge по углу


def smooth(s):
    s = np.clip(s, 0.0, 1.0)
    return s * s * (3 - 2 * s)


def dcut(theta):
    """Глубина выреза по углу: середина груди — глубже (V-вставка и щит adidas), у букв C/A — мельче."""
    return DCUT[1] + (DCUT[0] - DCUT[1]) * smooth((25.0 - np.abs(theta)) / 15.0)


def sector_w(theta):
    """1 — перед ворота (|θ| ≤ TH_A), 0 — бока и спина (|θ| ≥ TH_B)."""
    return smooth((TH_B - np.abs(theta)) / (TH_B - TH_A))


# Острова куска (UV NHL 24) → свободные углы развёртки Edge (там нет ни треугольников ни одного варианта сетки
# стиля 1, ни зон карты номеров): (рамка в UV NHL 24 lo, hi; масштаб; левый верхний угол в UV Edge). Плотность
# текселей: Edge 659 px/м (1024²), NHL 24 1216 px/м (2048²) → у острова 1:1 в 1024 — 608 px/м.
REGIONS = {"front": ((0.40, 0.45), (0.60, 0.68), 1.18, (0.004, 0.004)),   # перед: V-вставка, щит, шнуровка, ворот
           "lining": ((0.005, 0.745), (0.245, 0.94), 1.0, (0.752, 0.004))}  # подкладка ворота (тёмная)


def region_of(uv):
    for k, (lo, hi, _, _) in REGIONS.items():
        if (uv >= np.array(lo) - 1e-6).all(-1).all() and (uv <= np.array(hi) + 1e-6).all(-1).all():
            return k
    return None


def to_edge_uv(uv, key):
    lo, _, k, dst = REGIONS[key]
    return (uv - np.array(lo)) * k + np.array(dst)


def pack_piece(H):
    """UV вершин куска (NHL 24) → UV Edge по REGIONS (по островам). Меняет H["uv"] на месте."""
    import scipy.sparse as sp
    from scipy.sparse.csgraph import connected_components
    pc = H["part"] == 1
    T = H["tri"][pc[H["tri"]].all(1)]
    n = len(H["pos"])
    e = np.concatenate([T[:, [0, 1]], T[:, [1, 2]]])
    _, lab = connected_components(sp.coo_matrix((np.ones(len(e)), (e[:, 0], e[:, 1])), shape=(n, n)), directed=False)
    out = []
    for l in np.unique(lab[T[:, 0]]):
        vs = np.unique(T[lab[T[:, 0]] == l])
        key = region_of(H["uv"][vs])
        if key is None:
            raise SystemExit(f"остров куска вне REGIONS: {H['uv'][vs].min(0)}–{H['uv'][vs].max(0)}")
        H["uv"][vs] = to_edge_uv(H["uv"][vs], key)
        out.append((key, len(vs)))
    return out


def compose(edge_img, n24_img):
    """Развёртка Edge (1024², float) + острова куска из картинки NHL 24 (любого размера) по REGIONS."""
    out = edge_img.copy()
    S = out.shape[0]
    for lo, hi, k, dst in REGIONS.values():
        w, h = (np.array(hi) - np.array(lo)) * k
        x0, y0 = int(np.floor(dst[0] * S)), int(np.floor(dst[1] * S))
        x1, y1 = int(np.ceil((dst[0] + w) * S)), int(np.ceil((dst[1] + h) * S))
        ys, xs = np.mgrid[y0:y1, x0:x1]
        u = ((xs + 0.5) / S - dst[0]) / k + lo[0]
        v = ((ys + 0.5) / S - dst[1]) / k + lo[1]
        out[y0:y1, x0:x1] = kit3d.sample_bilinear(n24_img, u.ravel(), v.ravel()).reshape(y1 - y0, x1 - x0, -1)
    return out


def cut_field(E):
    """Поле выреза на сетке Edge: f (м, < 0 — вырезано) и θ в вершинах."""
    we = Welded(E)
    ring = we.neck()
    zc = float(we.P[ring, 2].mean())
    _, lip = edge_layers(we, ring, zc)
    band, _ = edge_layers(we, ring, zc)
    fold = fold_polyline(we, band)
    th = theta_of(we.P, zc)
    f = ring_dist(we.P, smooth_curve(fold if fold is not None else lip_polyline(lip), zc)) - dcut_eff(th)
    return f[we.g], th[we.g], sector_w(th)[we.g]


SEAM_ZONE = (0.015, 0.05)          # м за линией выреза Edge: ближе — рисунок как на куске adidas, к дальнему краю —
#                                    как у переноса на Edge (out/all); между — плавно само соответствие (UV), рисунок
#                                    изгибается, а не двоится. Тело adidas подогнано под Edge, рисунок на нём съехал на
#                                    1–2 см (MIN выезд: граница зелёной кокетки давала зубцы по краю куска).
SEAM_FADE = 0.015                  # и ещё столько — смешение цвета с out/all (мелкие расхождения переноса)


def clean_color(code, kit):
    """Готовый свитер NHL 24 (2048², float RGB) без спонсорских нашивок (правила [sponsor] fb/kit_rules.toml —
    закраска по строкам, как у fb.pilot): у MIN Tria на груди."""
    from . import kit_hybrid
    comp = kit3d.load_tex(J.n24_tex(CLUB_NAME[code], kit, "color"))
    defaults, rules = kit_hybrid.load_rules(kit_hybrid.RULES, code, kit, [])
    sp = tuple(k for k, r in rules.items() if r.get("sponsor"))
    out, _, _ = kit_hybrid.standard_patches(comp, rules, defaults, names=sp)
    return out[..., :3]


def outer_shell(m):
    """Сетка без подкладки ворота: только самая большая связная часть (низ подкладки NHL 24 лежит прямо под грудью —
    ближайшая точка у шва попадала на неё, тёмную)."""
    from scipy.sparse.csgraph import connected_components
    w = Welded(m)
    _, comp = connected_components(w.A, directed=False)
    keep = comp[w.T[:, 0]] == np.bincount(comp).argmax()
    out = dict(m)
    out["tri"] = m["tri"][keep]
    return out


def seam_bake(edge_img, E, A, n24, src, ss=2):
    """Развёртка Edge у шва (SEAM_ZONE + SEAM_FADE за линией выреза, сектор переда) — заново из src (UV NHL 24).
    Соответствие (UV adidas и UV NHL 24) — в вершинах Edge, внутри треугольников — линейно (как у fb.kit3d.transfer):
    по текселям ближайшая точка прыгает между треугольниками — граница цветов шла лесенкой (пользователь, 18.10)."""
    S = edge_img.shape[0] * ss
    f, th, w = cut_field(E)
    tid, bar = kit3d.raster_uv(E, S)
    m = tid >= 0
    T = E["tri"][tid[m]]
    b = bar[m]
    ft = (b * f[T]).sum(1)
    wt = (b * w[T]).sum(1)
    zone = (ft < SEAM_ZONE[1] + SEAM_FADE) & (wt > 0.02)
    T, b, ft = T[zone], b[zone], ft[zone]
    vz = np.unique(T)
    shells = (outer_shell(A), outer_shell(n24))
    uv_v = []
    for mesh in shells:
        t, bb, _ = kit3d.project(E["pos"][vz], kit3d._unit(E["nrm"][vz]), mesh)
        full = np.zeros((len(E["pos"]), 2))
        full[vz] = (bb[:, :, None] * mesh["uv"][mesh["tri"][t]]).sum(1)
        uv_v.append(full)
    uv = [(b[:, :, None] * u[T]).sum(1) for u in uv_v]
    # треугольник на шве развёртки NHL 24 (вершины в разных островах) — по текселям
    seam = np.zeros(len(T), bool)
    for u in uv_v:
        tu = u[T]
        seam |= np.max(np.linalg.norm(tu[:, :, None, :] - tu[:, None, :, :], axis=-1), axis=(1, 2)) > 0.04
    if seam.any():
        P = (b[seam][:, :, None] * E["pos"][T[seam]]).sum(1)
        N = kit3d._unit((b[seam][:, :, None] * E["nrm"][T[seam]]).sum(1))
        for k, mesh in enumerate(shells):
            t, bb, _ = kit3d.project(P, N, mesh)
            uv[k][seam] = (bb[:, :, None] * mesh["uv"][mesh["tri"][t]]).sum(1)
    s = smooth((ft - SEAM_ZONE[0]) / (SEAM_ZONE[1] - SEAM_ZONE[0]))[:, None]
    far = np.linalg.norm(uv[0] - uv[1], axis=1) > 0.05     # разные острова UV — не смешивать
    uvm = np.where(far[:, None], np.where(s > 0.5, uv[1], uv[0]), uv[0] * (1 - s) + uv[1] * s)
    col = kit3d.sample_bilinear(src, uvm[:, 0], uvm[:, 1])
    a = 1.0 - smooth((ft - SEAM_ZONE[1]) / SEAM_FADE)
    return _blend(edge_img, m, zone, col, a, ss)


def _blend(edge_img, m, zone, col, a, ss):
    """Цвета col с весом a в текселях raster-маски m[zone] (сверхвыборка ss) поверх edge_img."""
    S = m.shape[0]
    img = np.zeros((S, S, 3))
    wgt = np.zeros((S, S))
    ys, xs = np.nonzero(m)
    ys, xs = ys[zone], xs[zone]
    img[ys, xs] = col * a[:, None]
    wgt[ys, xs] = a
    H = edge_img.shape[0]
    img = img.reshape(H, ss, H, ss, 3).mean((1, 3))
    wgt = wgt.reshape(H, ss, H, ss).mean((1, 3))
    return edge_img * (1 - wgt[..., None]) + img


COLLAR_H = (0.025, 0.035)          # м от сгиба ворота Edge: до 2,5 см — как у adidas от края ворота (кромка ≈ 1 см),
#                                    к 3,5 см — переход (у переда это место вырезано — там кусок adidas)
PROFILE_WIN = 6.0                  # град: окно медианы цвета кромки по углу
INNER_TRIM = 0.004                 # подворот Edge у самой губы — кромкой (как край ворота сверху), глубже — подкладкой


def fold_polyline(we, band, k=12):
    """Сгиб ворота Edge — рёбра между треугольниками подворота и наружного слоя (сгущённые в k раз)."""
    tb = band[we.T].all(1)
    owner = {}
    fold = []
    for ti, tri in enumerate(we.T):
        for e in ((tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0])):
            key = (min(e), max(e))
            if key in owner and owner[key] != tb[ti]:
                fold.append(key)
            owner.setdefault(key, tb[ti])
    t = np.linspace(0, 1, k, endpoint=False)[:, None]
    return np.vstack([we.P[a] * (1 - t) + we.P[b] * t for a, b in fold]) if fold else None


def profile_grid(grid, src, win=PROFILE_WIN):
    """Цвета сетки (φ, d) → UV → src, сглаженные по углу медианой в окне ±win°: ширина полос кромки — ровная (у
    adidas край полосы идёт по рёбрам его треугольников и гуляет на ±3 мм — у Edge выходили зубцы)."""
    from . import hem
    uv, ok = grid
    nphi, nd = ok.shape
    col = np.full((nphi, nd, 3), np.nan)
    col[ok] = kit3d.sample_bilinear(src, uv[ok][:, 0], uv[ok][:, 1])
    k = int(round(win / hem.PHI_STEP))
    idx = (np.arange(nphi)[:, None] + np.arange(-k, k + 1)[None]) % nphi
    with np.errstate(all="ignore"):
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            out = np.nanmedian(col[idx], axis=1)
    return out, ~np.isnan(out[..., 0])


def profile_at(prof, phi, d):
    from . import hem
    col, ok = prof
    nphi, nd = ok.shape
    ix = np.round((phi + 180) / hem.PHI_STEP).astype(np.int64) % nphi
    iy = np.clip(np.round(d / hem.D_STEP).astype(np.int64), 0, nd - 1)
    return col[ix, iy], ok[ix, iy] & (d >= -0.005)


def collar_layer(edge_img, E, A, src, ss=2, n24=None):
    """Ворот Edge (бока и спина) «от края», как низ (fb.hem): тексель наружного слоя → (угол вокруг шеи θ, расстояние
    от сгиба ворота d) → цвет наружной оболочки adidas с теми же θ и d от края её ворота (медиана по углу ±PROFILE_WIN°);
    подворот — подкладка adidas (у сгиба — кромка). У NHL 24 кромка — полоса ≈ 1 см до самого края по всему кругу; при
    переносе по ближайшей точке она у Edge рвалась и уходила внутрь (пользователь, 18.10)."""
    from scipy.sparse.csgraph import connected_components
    from . import hem
    we = Welded(E)
    ring = we.neck()
    zc = float(we.P[ring, 2].mean())
    band, lip = edge_layers(we, ring, zc)
    fold = fold_polyline(we, band)
    lip_poly = fold if fold is not None else lip_polyline(lip)
    # профиль кромки — с исходной сетки NHL 24 (её ширина там настоящая: 0,6–0,9 см); у подогнанной под Edge сетки
    # adidas сзади край у шеи, а ткань притянута к спине Edge — кромка растянута до 2 см
    A = n24 if n24 is not None else A
    wa = Welded(A)
    _, comp = connected_components(wa.A, directed=False)
    main = np.bincount(comp).argmax()
    bnd = wa.boundary()
    ring_a = wa.neck(bnd[comp[bnd] == main])
    d_a = ring_dist(A["pos"], ring_polyline(wa, ring_a))
    th_a = theta_of(A["pos"], float(wa.P[ring_a, 2].mean()))
    is_main = comp[wa.g[A["tri"][:, 0]]] == main
    p_out = profile_grid(hem.polar_grid(A["tri"][is_main], th_a, d_a, A["uv"], COLLAR_H[1] + 0.01), src)
    p_lin = profile_grid(hem.polar_grid(A["tri"][~is_main], th_a, d_a, A["uv"], 0.08), src)
    lin_uv = A["uv"][np.unique(A["tri"][~is_main])]
    dark = np.median(kit3d.sample_bilinear(src, lin_uv[:, 0], lin_uv[:, 1]), axis=0)
    S = edge_img.shape[0] * ss
    tid, bar = kit3d.raster_uv(E, S)
    m = tid >= 0
    T = E["tri"][tid[m]]
    b = bar[m]
    P = (b[:, :, None] * E["pos"][T]).sum(1)
    d = ring_dist(P, lip_poly)
    inner = band[we.g[T]].all(1)
    zone = inner | (d < COLLAR_H[1])
    P, d, inner = P[zone], d[zone], inner[zone]
    th = theta_of(P, zc)
    col = np.zeros((len(P), 3))
    a = np.zeros(len(P))
    use_out = (~inner) | (d < INNER_TRIM)
    idx = np.nonzero(use_out)[0]
    c, ok = profile_at(p_out, th[idx], d[idx])
    col[idx[ok]] = c[ok]
    a[idx[ok]] = np.where(inner[idx[ok]], 1.0, 1.0 - smooth((d[idx[ok]] - COLLAR_H[0]) / (COLLAR_H[1] - COLLAR_H[0])))
    idx = np.nonzero(inner & ~use_out)[0]
    c, ok = profile_at(p_lin, th[idx], d[idx])
    col[idx] = dark
    col[idx[ok]] = c[ok]
    a[idx] = 1.0
    return _blend(edge_img, m, zone, col, a, ss)


def mesh_d(m):
    d = {"pos": np.array([p[:3] for p in m.pos], dtype=np.float64), "uv": np.array(m.uv, dtype=np.float64),
         "tri": np.array(m.tris, dtype=np.int64), "nrm": kit3d._unit(np.array(m.nrm, dtype=np.float64))}
    if m.bones:
        d["bones"] = np.array(m.bones, dtype=np.int64)
        d["weights"] = np.array(m.weights, dtype=np.float64)
    return d


class Welded:
    """Сварка по позиции: узлы, треугольники в узлах, рёбра с числом треугольников."""

    def __init__(self, m):
        from collections import Counter
        self.g, self.first = J.weld(m["pos"])
        self.P = m["pos"][self.first]
        self.n = len(self.first)
        self.T = self.g[m["tri"]]
        c = Counter()
        for a, b, d in self.T:
            for e in ((a, b), (b, d), (d, a)):
                c[(min(e), max(e))] += 1
        self.edges = c
        self.A = J.adjacency(self.T, self.n)

    def boundary(self):
        return np.array(sorted({v for e, k in self.edges.items() if k == 1 for v in e}), dtype=np.int64)

    def neck(self, nodes=None):
        b = self.boundary() if nodes is None else nodes
        return b[(self.P[b, 1] > 1.45) & (np.abs(self.P[b, 0]) < 0.2)]

    def geodesic(self, src):
        """Расстояние по рёбрам сетки от узлов src (м)."""
        import scipy.sparse as sp
        from scipy.sparse.csgraph import dijkstra
        e = np.array(list(self.edges.keys()))
        L = np.linalg.norm(self.P[e[:, 0]] - self.P[e[:, 1]], axis=1)
        G = sp.coo_matrix((L, (e[:, 0], e[:, 1])), shape=(self.n, self.n)).tocsr()
        return dijkstra(G, directed=False, indices=src, min_only=True)


def theta_of(P, zc):
    return np.degrees(np.arctan2(P[:, 0], P[:, 2] - zc))


def ring_polar(P, ring, zc):
    """Край горловины по углу: (θ по возрастанию, r, y) — для интерполяции по кругу."""
    th = theta_of(P[ring], zc)
    o = np.argsort(th)
    r = np.hypot(P[ring, 0], P[ring, 2] - zc)
    return th[o], r[o], P[ring, 1][o]


def interp_ring(rp, th):
    t, r, y = rp
    xp = np.concatenate([t - 360, t, t + 360])
    return np.interp(th, xp, np.tile(r, 3)), np.interp(th, xp, np.tile(y, 3))


def ring_polyline(w, ring, k=12):
    """Край горловины — замкнутая ломаная по рёбрам границы, сгущённая в k раз (для расстояний)."""
    rs = set(int(v) for v in ring)
    bedges = [e for e, c in w.edges.items() if c == 1 and e[0] in rs and e[1] in rs]
    pts = []
    for a, b in bedges:
        t = np.linspace(0, 1, k, endpoint=False)[:, None]
        pts.append(w.P[a] * (1 - t) + w.P[b] * t)
    return np.vstack(pts)


def ring_dist(P, poly):
    """Расстояние по прямой до края горловины (м). По поверхности не годится: у Edge край подвёрнут внутрь —
    путь шёл бы через подворот (у низа V 15 см вместо 1,3)."""
    from scipy.spatial import cKDTree
    return cKDTree(poly).query(P)[0]


def chain(edges):
    """Рёбра (пары узлов) → упорядоченная цепочка узлов (самая длинная, если их несколько)."""
    from collections import defaultdict
    adj = defaultdict(list)
    for a, b in edges:
        adj[a].append(b)
        adj[b].append(a)
    seen, best = set(), []
    ends = [v for v in adj if len(adj[v]) == 1] + list(adj)
    for s in ends:
        if s in seen:
            continue
        path, cur = [s], s
        seen.add(s)
        while True:
            nx = [v for v in adj[cur] if v not in seen]
            if not nx:
                break
            cur = nx[0]
            seen.add(cur)
            path.append(cur)
        if len(path) > len(best):
            best = path
    return best


def edge_layers(we, ring, zc):
    """У Edge ворот двухслойный: наружный слой тела поднимается к «губе» (видимый край ворота), внутренний (подворот,
    нормали к шее) спускается от губы внутрь до края сетки (скрыт). -> (подворот: узлы, губа: точки по углу)."""
    import scipy.sparse as sp
    from scipy.sparse.csgraph import connected_components
    d_r = ring_dist(we.P, ring_polyline(we, ring))
    N = J.node_normals(we.P, we.T, we.n)
    rad = kit3d._unit(np.stack([we.P[:, 0], np.zeros(we.n), we.P[:, 2] - zc], -1))
    cand = (d_r < 0.07) & ((N * rad).sum(1) < -0.2)
    sub = we.A[cand][:, cand]
    _, lab = connected_components(sub, directed=False)
    idx = np.nonzero(cand)[0]
    ring_labs = set(lab[np.searchsorted(idx, [v for v in ring if cand[v]])])
    band = np.zeros(we.n, bool)
    band[idx[np.isin(lab, list(ring_labs))]] = True
    th = theta_of(we.P, zc)
    r = np.hypot(we.P[:, 0], we.P[:, 2] - zc)
    outer = (~band) & (d_r < 0.07)
    lip = []
    for a in np.arange(-180, 180, LIP_BIN):
        m = outer & (np.abs(((th - a + 180) % 360) - 180) < LIP_BIN)
        if m.any():
            i = np.nonzero(m)[0][np.argmin(r[m])]
            lip.append((a, we.P[i]))
    th_l = np.array([x[0] for x in lip], dtype=np.float64)
    P_l = np.array([x[1] for x in lip])
    for _ in range(2):                                  # сгладить по кругу
        P_l = (np.roll(P_l, 1, 0) + 2 * P_l + np.roll(P_l, -1, 0)) / 4
    return band, (th_l, P_l)


def lip_polyline(lip, k=12):
    _, P = lip
    t = np.linspace(0, 1, k, endpoint=False)[:, None, None]
    return (P[None] * (1 - t) + np.roll(P, -1, 0)[None] * t).reshape(-1, 3)


def lip_at(lip, zc, th):
    """Губа Edge под углом th: (r, y)."""
    t, P = lip
    r = np.hypot(P[:, 0], P[:, 2] - zc)
    o = np.argsort(t)
    xp = np.concatenate([t[o] - 360, t[o], t[o] + 360])
    return np.interp(th, xp, np.tile(r[o], 3)), np.interp(th, xp, np.tile(P[o, 1], 3))


def boundary_edges(T_sel, all_edges):
    """Рёбра на краю выбранных треугольников, внутренние в исходной сетке."""
    from collections import Counter
    c = Counter()
    for tri in T_sel:
        for e in ((tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0])):
            c[(min(e), max(e))] += 1
    return [e for e, k in c.items() if k == 1 and all_edges[e] == 2]


def split_along(m, fv, eligible_v=None, tol=0.0):
    """Треугольники сетки m, пересекающие уровень 0 поля fv (в вершинах), — разрезать точно по нему: новые вершины на
    рёбрах (позиция, нормаль, UV, кости и веса — по линейной интерполяции). Край выреза — гладкая линия, а не «пила»
    из целых треугольников. Вершина ближе tol к уровню — на нём (разрез идёт через неё, без новой вершины рядом:
    иначе вырожденные треугольники и щели). eligible_v — какие вершины можно резать (ребро — если оба конца).
    -> (сетка, поле в её вершинах; у новых и лежащих на уровне — 0)."""
    f = np.asarray(fv, dtype=np.float64).copy()
    f[np.abs(f) <= tol] = 0.0
    pos, nrm, uv = list(m["pos"]), list(m["nrm"]), list(m["uv"])
    has_skin = "bones" in m
    bones = [list(b) for b in m["bones"]] if has_skin else None
    weights = [list(w) for w in m["weights"]] if has_skin else None
    fl = list(f)
    made = {}

    def cut(i, j):
        key = (min(i, j), max(i, j))
        if key in made:
            return made[key]
        a, b = key
        t = fl[a] / (fl[a] - fl[b])
        pos.append(m["pos"][a] * (1 - t) + m["pos"][b] * t)
        n = m["nrm"][a] * (1 - t) + m["nrm"][b] * t
        nrm.append(n / max(np.linalg.norm(n), 1e-12))
        uv.append(m["uv"][a] * (1 - t) + m["uv"][b] * t)
        if has_skin:
            acc = {}
            for v, k in ((a, 1 - t), (b, t)):
                for bb, ww in zip(m["bones"][v], m["weights"][v]):
                    if ww > 0:
                        acc[int(bb)] = acc.get(int(bb), 0.0) + k * ww
            top = sorted(acc.items(), key=lambda x: -x[1])[:4]
            sw = sum(w for _, w in top) or 1.0
            bones.append([b_ for b_, _ in top] + [top[-1][0]] * (4 - len(top)))
            weights.append([w / sw for _, w in top] + [0.0] * (4 - len(top)))
        fl.append(0.0)
        made[key] = len(pos) - 1
        return made[key]

    def ok_edge(i, j):
        return eligible_v is None or (eligible_v[i] and eligible_v[j])

    def sgn(v):
        return 0 if fl[v] == 0 else (1 if fl[v] > 0 else -1)

    tris = []
    for tri in m["tri"]:
        tri = [int(v) for v in tri]
        sg = [sgn(v) for v in tri]
        if not (1 in sg and -1 in sg):                    # линия не проходит внутри
            tris.append(tri)
            continue
        if 0 in sg:                                       # через вершину на уровне: режется одно ребро (+/−)
            k = sg.index(0)
            a, b, c = tri[k], tri[(k + 1) % 3], tri[(k + 2) % 3]
            if not ok_edge(b, c):
                tris.append(tri)
                continue
            p = cut(b, c)
            tris += [[a, b, p], [a, p, c]]
            continue
        k = next(i for i in range(3) if sg[i] != sg[(i + 1) % 3] and sg[i] != sg[(i + 2) % 3])
        a, b, c = tri[k], tri[(k + 1) % 3], tri[(k + 2) % 3]
        eb, ec = ok_edge(a, b), ok_edge(a, c)
        if eb and ec:
            pab, pac = cut(a, b), cut(a, c)
            tris += [[a, pab, pac], [pab, b, c], [pab, c, pac]]
        elif eb:                                          # одно ребро — на два треугольника через вершину c
            pab = cut(a, b)
            tris += [[a, pab, c], [pab, b, c]]
        elif ec:
            pac = cut(a, c)
            tris += [[a, b, pac], [pac, b, c]]
        else:
            tris.append(tri)
    out = dict(m)
    out["pos"], out["nrm"], out["uv"] = np.array(pos), np.array(nrm), np.array(uv)
    out["tri"] = np.array(tris, dtype=np.int64)
    if has_skin:
        out["bones"], out["weights"] = np.array(bones, dtype=np.int64), np.array(weights)
    return out, np.array(fl)


def dcut_eff(theta):
    """Глубина выреза по углу: спереди — dcut·w (V-вставка и щит adidas), сзади и с боков — полоса ворота D_STRIP."""
    return np.maximum(dcut(theta) * sector_w(theta), D_STRIP)


def chain_loop(edges):
    """Рёбра → (узлы по порядку, замкнута ли цепочка)."""
    from collections import defaultdict
    path = chain(edges)
    adj = defaultdict(set)
    for a, b in edges:
        adj[a].add(b)
        adj[b].add(a)
    closed = len(path) > 2 and path[0] in adj[path[-1]]
    return path, closed


def zipper(ch_e, ch_a, PE, PA, zc, closed):
    """Полоса шва между двумя цепочками (Edge и adidas) — по кратчайшей диагонали; у замкнутых — по кругу от спины."""
    def by_theta(ch, P):
        th = np.unwrap(np.radians(theta_of(P[ch], zc)))
        return ch if th[min(len(ch) - 1, 3)] >= th[0] else ch[::-1]
    if closed:
        ch_e = by_theta(ch_e, PE)
        ch_a = by_theta(ch_a, PA)
        i0 = int(np.argmin(np.abs(np.abs(theta_of(PE[ch_e], zc)) - 180)))
        ch_e = ch_e[i0:] + ch_e[:i0]
        j0 = int(np.argmin(np.linalg.norm(PA[ch_a] - PE[ch_e[0]], axis=1)))
        ch_a = ch_a[j0:] + ch_a[:j0]
        ch_e, ch_a = ch_e + ch_e[:1], ch_a + ch_a[:1]
    else:
        if theta_of(PE[[ch_e[0]]], zc)[0] > theta_of(PE[[ch_e[-1]]], zc)[0]:
            ch_e = ch_e[::-1]
        if theta_of(PA[[ch_a[0]]], zc)[0] > theta_of(PA[[ch_a[-1]]], zc)[0]:
            ch_a = ch_a[::-1]
    bridge = []
    i = j = 0
    while i < len(ch_e) - 1 or j < len(ch_a) - 1:
        if i == len(ch_e) - 1:
            adv_e = False
        elif j == len(ch_a) - 1:
            adv_e = True
        else:
            adv_e = np.linalg.norm(PE[ch_e[i + 1]] - PA[ch_a[j]]) < np.linalg.norm(PE[ch_e[i]] - PA[ch_a[j + 1]])
        if adv_e:
            bridge.append((("e", ch_e[i]), ("e", ch_e[i + 1]), ("a", ch_a[j])))
            i += 1
        else:
            bridge.append((("e", ch_e[i]), ("a", ch_a[j + 1]), ("a", ch_a[j])))
            j += 1
    return bridge


def smooth_curve(pts, zc, win=CUT_SMOOTH, k=6):
    """Кривая около шеи (точки), сглаженная по углу θ (гаусс ±win°) и сгущённая: для линии выреза. Сгиб Edge — ломаная
    из рёбер; расстояние от неё — «фестоны» (линия выреза волной, граница кокетки у шва — тоже)."""
    th = theta_of(pts, zc)
    grid = np.arange(-180.0, 180.0, 1.0)
    out = np.zeros((len(grid), 3))
    for i, a in enumerate(grid):
        dth = ((th - a) + 180) % 360 - 180
        w = np.exp(-0.5 * (dth / win) ** 2)
        out[i] = (w[:, None] * pts).sum(0) / max(w.sum(), 1e-9)
    t = np.linspace(0, 1, k, endpoint=False)[:, None, None]
    return (out[None] * (1 - t) + np.roll(out, -1, 0)[None] * t).reshape(-1, 3)


def fill_to_edge(grid, edge_pts, zc):
    """Сетка (φ, d) → позиция: пустые клетки у самого края (d меньше первой заполненной — треугольники до сгиба не
    доходят) — линейно от точки края с тем же углом до первой заполненной: иначе все вершины ближе к краю
    схлопывались в одну точку (вырожденные треугольники, щели)."""
    from . import hem
    gp, ok = grid
    gp, ok = gp.copy(), ok.copy()
    nphi = ok.shape[0]
    th_e = theta_of(edge_pts, zc)
    o = np.argsort(th_e)
    xp = np.concatenate([th_e[o] - 360, th_e[o], th_e[o] + 360])
    edge_at = lambda a: np.array([np.interp(a, xp, np.tile(edge_pts[o][:, c], 3)) for c in range(3)])  # noqa: E731
    for i in range(nphi):
        if not ok[i].any():
            continue
        i0 = int(np.argmax(ok[i]))
        if i0 == 0:
            continue
        p0 = edge_at(-180 + i * hem.PHI_STEP)
        for k in range(i0):
            gp[i, k] = p0 + (gp[i, i0] - p0) * (k / i0)
            ok[i, k] = True
    return gp, ok


def merge_close(m, eps=MERGE_EPS):
    """Вершины ближе eps — в одну точку (их среднее), выродившиеся треугольники — прочь: измельчение (refine_strip)
    рождает почти-дубли (0,01–0,1 мм) — при сварке по позиции они давали щели и рёбра на 3–4 треугольника."""
    from scipy.spatial import cKDTree
    P = m["pos"].copy()
    parent = np.arange(len(P))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    for i, j in cKDTree(P).query_pairs(eps):
        if np.abs(m["uv"][i] - m["uv"][j]).max() > 0.01:   # разные острова (подкладка и ворот) — не сводить
            continue
        a, b = find(i), find(j)
        if a != b:
            parent[max(a, b)] = min(a, b)
    root = np.array([find(i) for i in range(len(P))])
    acc = np.zeros_like(P)
    cnt = np.zeros(len(P))
    np.add.at(acc, root, P)
    np.add.at(cnt, root, 1)
    out = dict(m)
    out["pos"] = (acc[root] / cnt[root][:, None])
    T = m["tri"]
    r = root[T]
    keep = (r[:, 0] != r[:, 1]) & (r[:, 1] != r[:, 2]) & (r[:, 0] != r[:, 2])
    out["tri"] = T[keep]
    return out


def submesh(m, keep):
    """Сетка из треугольников keep (bool по треугольникам), вершины — перенумерованы."""
    T = m["tri"][keep]
    used = np.unique(T)
    remap = -np.ones(len(m["pos"]), np.int64)
    remap[used] = np.arange(len(used))
    out = {k: (v[used] if isinstance(v, np.ndarray) and len(v) == len(m["pos"]) else v) for k, v in m.items()}
    out["tri"] = remap[T]
    return out, used


def refine_strip(m, zc, d_of, d_lines=REFINE_D, th_from=TH_A - 4.0, th_step=REFINE_TH):
    """Измельчить сетку у края ворота: разрезы по радиальным линиям θ = const (через th_step°, в секторе |θ| ≥
    th_from) и по линиям d = const вдоль края. У края adidas 24 вершины (через 2–3 см) — уложенный на изогнутый сгиб
    Edge, он шёл хордами: по «рожкам» Edge сзади по бокам — углы."""
    for tk in np.arange(-180.0, 180.0, th_step):
        if abs(tk) < th_from:
            continue
        th = theta_of(m["pos"], zc)
        f = ((th - tk + 180) % 360) - 180
        m, _ = split_along(m, f, np.abs(f) < 45, tol=0.4)   # только у своей линии (на обороте θ = tk + 180 — нет)
    for dl in d_lines:
        m, _ = split_along(m, d_of(m["pos"]) - dl, tol=0.0006)
    return m


def loops_of(T, P):
    """Граница сетки (узлы сварены по позиции) → список замкнутых или открытых цепочек узлов (индексы вершин)."""
    from collections import Counter
    w = Welded({"pos": P, "tri": T, "uv": np.zeros((len(P), 2)), "nrm": np.zeros((len(P), 3))})
    edges = [e for e, k in w.edges.items() if k == 1]
    from collections import defaultdict
    adj = defaultdict(list)
    for a, b in edges:
        adj[a].append(b)
        adj[b].append(a)
    seen, out = set(), []
    for s0 in adj:
        if s0 in seen:
            continue
        path, cur = [s0], s0
        seen.add(s0)
        while True:
            nx = [v for v in adj[cur] if v not in seen]
            if not nx:
                break
            cur = nx[0]
            seen.add(cur)
            path.append(cur)
        out.append([int(w.first[v]) for v in path])
    return out, w


REFINE_LOD = {2: (6.0, (0.004, 0.010)), 0: (12.0, (0.007,)), 3: (30.0, ())}   # ближняя, средняя, дальняя


def hybrid(E, A, info=None, refine=REFINE_LOD[2]):
    """Сетка Edge E (dict с bones/weights) + ворот сетки adidas A (dict). -> (dict сетки, сводка).

    Ворот adidas — целиком, по всему кругу (кромка — одним куском, без стыка): спереди — как у NHL 24 (V-вставка,
    щит, шнуровка, до dcut от сгиба Edge), сзади и с боков — полоса до D_STRIP от края, уложенная на наружный слой
    ворота Edge «от края» (точка adidas на расстоянии d от своего края → точка Edge на том же угле θ и расстоянии d от
    сгиба): форма ворота сзади — Edge (поднимается вдоль шеи), кромка adidas — своей ширины. Перед укладкой полоса
    измельчена (refine_strip). Шов — по ткани ниже кромки (пользователь, 18.10: на стыке кромки двух частей была видна
    разная толщина). Подворот Edge снят по кругу, вместо него — подкладка adidas (уложена на его место так же).
    В выходе: pos, nrm, uv (у куска — UV NHL 24 как есть, part = 1), tri, bones, weights, part (0 — Edge и шов,
    1 — кусок adidas)."""
    info = {} if info is None else info
    from scipy.sparse.csgraph import connected_components
    from . import hem
    we0 = Welded(E)
    ring0 = we0.neck()
    zc = float(we0.P[ring0, 2].mean())
    band0, lip = edge_layers(we0, ring0, zc)
    fold0 = fold_polyline(we0, band0)
    edge_poly = fold0 if fold0 is not None else lip_polyline(lip)
    cut_poly = smooth_curve(edge_poly, zc)

    def field(P):
        return ring_dist(P, cut_poly) - dcut_eff(theta_of(P, zc))
    # --- adidas: край ворота, расстояние от него (до укладки)
    wa0 = Welded(A)
    _, comp0 = connected_components(wa0.A, directed=False)
    main0 = np.bincount(comp0).argmax()
    bnd0 = wa0.boundary()
    ring_a0 = wa0.neck(bnd0[comp0[bnd0] == main0])
    ring_poly_a = ring_polyline(wa0, ring_a0)

    def d_a(P):
        return ring_dist(P, ring_poly_a)

    def s_of(P):
        return smooth((np.abs(theta_of(P, zc)) - TH_A) / (TH_RING - TH_A))
    # --- кусок adidas: спереди — по полю выреза Edge, сзади и с боков — по расстоянию от своего края
    is_main_v = (comp0 == main0)[wa0.g]

    def f_piece(P):
        sv = s_of(P)
        return (1 - sv) * field(P) + sv * (d_a(P) - D_STRIP) + CUT_GAP
    A, fv_a = split_along(A, f_piece(A["pos"]))
    wa1 = Welded(A)
    _, comp1 = connected_components(wa1.A, directed=False)
    main1 = np.bincount(comp1).argmax()
    tri_main = comp1[wa1.T[:, 0]] == main1
    fa_t = fv_a[A["tri"]].mean(1)
    keep_a = (tri_main & (fa_t < 0)) | (~tri_main & (d_a(A["pos"])[A["tri"]].min(1) < LINING_KEEP))
    A, _ = submesh(A, keep_a)
    lining_v = np.zeros(len(A["pos"]), bool)
    wsub = Welded(A)
    _, csub = connected_components(wsub.A, directed=False)
    big = np.bincount(csub).argmax()
    # подкладка — отдельные компоненты (не та, где край ворота); главная — самая большая
    lining_v = (csub != big)[wsub.g]
    # --- измельчить у края и уложить на ворот Edge «от края»
    A = merge_close(refine_strip(A, zc, d_a, d_lines=refine[1], th_step=refine[0]))
    wsub = Welded(A)
    _, csub = connected_components(wsub.A, directed=False)
    lining_v = (csub != np.bincount(csub).argmax())[wsub.g]
    P0 = A["pos"].copy()
    th_v = theta_of(P0, zc)
    dv = d_a(P0)
    sv = s_of(P0)
    # ширина кромки: уложенная на скруглённый сгиб Edge, она выходила на 15–25 % уже, чем у NHL 24 — у края d
    # растягивается в RIM_K раз (к RIM_K_END — снова 1:1, чтобы шов на D_STRIP совпал с вырезом Edge)
    kk = 1.0 + (RIM_K - 1.0) * (1.0 - smooth(dv / RIM_K_END))
    dv_map = dv * kk
    outer_tri = E["tri"][~band0[we0.g[E["tri"]]].any(1)]
    g_pos = fill_to_edge(hem.polar_grid(outer_tri, theta_of(E["pos"], zc), ring_dist(E["pos"], edge_poly), E["pos"],
                                        D_MAP[1] + 0.01), edge_poly, zc)
    tgt, ok = hem.lookup_lin(g_pos, th_v, dv_map)
    fall = 1.0 - smooth((dv - D_MAP[0]) / (D_MAP[1] - D_MAP[0]))
    wmap = sv * fall * ok * (~lining_v)
    P1 = P0 + wmap[:, None] * (tgt - P0)
    band_tri = E["tri"][band0[we0.g[E["tri"]]].all(1)]
    if lining_v.any():
        # подкладка: со сдвигом края по углу; где есть подворот Edge — на него «от края»
        ring_v = (dv < 1e-6) & ~lining_v
        if ring_v.any():
            Dr = P1[ring_v] - P0[ring_v]
            tr = th_v[ring_v]
            o = np.argsort(tr)
            xp = np.concatenate([tr[o] - 360, tr[o], tr[o] + 360])
            li = np.nonzero(lining_v)[0]
            for k in range(3):
                P1[li, k] = P0[li, k] + np.interp(th_v[li], xp, np.tile(Dr[o][:, k], 3)) * sv[li]
        if len(band_tri):
            g_band = fill_to_edge(hem.polar_grid(band_tri, theta_of(E["pos"], zc), ring_dist(E["pos"], edge_poly),
                                                 E["pos"], 0.08), edge_poly, zc)
            li = np.nonzero(lining_v)[0]
            tl, okl = hem.lookup_lin(g_band, th_v[li], dv[li])
            wl = sv[li] * okl
            P1[li] = P1[li] * (1 - wl[:, None]) + tl * wl[:, None]
    wP0 = Welded({"pos": P0, "tri": A["tri"], "uv": A["uv"], "nrm": A["nrm"]})
    N0 = J.node_normals(wP0.P, wP0.T, wP0.n)
    N1 = J.node_normals(P1[wP0.first], wP0.T, wP0.n)
    A["pos"] = P1
    A["nrm"] = kit3d._unit(J.rotate_onto(kit3d._unit(A["nrm"]), N0[wP0.g], N1[wP0.g]))
    A = merge_close(A)                                   # после укладки — тоже (сходящиеся у сгиба точки)
    info.update(strip_mapped=int((wmap > 0.5).sum()), piece_verts=len(P1))
    # --- Edge: разрезать по линии выреза; снять наружный слой до неё и подворот по кругу
    E, fv_e = split_along(E, field(E["pos"]))
    we = Welded(E)
    band, _ = edge_layers(we, we.neck(), zc)
    f_e = fv_e[we.first]
    keep_e = ~(band[we.T].all(1) | (f_e[we.T].mean(1) < 0))
    # --- кусок: узлы, края
    wa = Welded(A)
    _, comp = connected_components(wa.A, directed=False)
    main = np.bincount(comp).argmax()
    piece = np.ones(len(wa.T), bool)
    used = np.ones(wa.n, bool)
    Pa = wa.P.copy()
    f_a = f_piece(P0[wa.first])                         # поле — по позициям до укладки
    d_ring = d_a(P0[wa.first])
    D = np.zeros((wa.n, 3))
    # у края куска (последние CUT_SNAP до линии выреза) — плавно точно на наружный слой Edge (перед: у ворота кусок
    # adidas держит форму NHL 24 и на 3–5 мм не совпадает с Edge — граница кокетки у шва шла ступенькой); кромку у края
    # (до SNAP_KEEP) не трогать
    wsnap = smooth((f_a + CUT_SNAP) / CUT_SNAP) * (comp == main) * smooth(d_ring / SNAP_KEEP)
    sel = np.nonzero(wsnap > 0)[0]
    if len(sel):
        outer_t = ~band[we.T].any(1)
        tgt = {"pos": we.P, "nrm": J.node_normals(we.P, we.T, we.n), "tri": we.T[outer_t]}
        t, bb, _ = kit3d.project(Pa[sel], J.node_normals(Pa, wa.T, wa.n)[sel], tgt)
        q = (bb[:, :, None] * we.P[tgt["tri"][t]]).sum(1)
        # только по нормали: со сдвигом вдоль поверхности рисунок сползал (граница кокетки у шва провисала на ~1 см),
        # а пересчёт развёртки по вершинам давал на ней ступени
        nrm_sel = J.node_normals(Pa, wa.T, wa.n)[sel]
        dn = ((q - Pa[sel]) * nrm_sel).sum(1, keepdims=True) * nrm_sel
        Pa[sel] += wsnap[sel, None] * dn
        D = Pa - wa.P
    info.update(zc=round(zc, 4), band_nodes=int(band.sum()), edge_removed=int((~keep_e).sum()),
                piece_tris=int(len(wa.T)))
    # --- шов: край выреза Edge (наружный слой) ↔ внешний край куска (не край ворота); обе линии замкнуты
    cut_e = [e for e in boundary_edges(we.T[keep_e], we.edges) if not (band[e[0]] or band[e[1]])]
    bnd = wa.boundary()
    bnd = bnd[comp[bnd] == main]
    from collections import defaultdict
    bset = set(int(v) for v in bnd)
    bedges = [e for e, k in wa.edges.items() if k == 1 and e[0] in bset and e[1] in bset]
    # компоненты границы: внутренняя (край ворота) и внешняя (линия выреза) — внешняя дальше от края ворота
    import scipy.sparse as sp
    if bedges:
        ee = np.array(bedges)
        G = sp.coo_matrix((np.ones(len(ee)), (ee[:, 0], ee[:, 1])), shape=(wa.n, wa.n))
        _, lab = connected_components(G, directed=False)
        labs = {int(lab[v]) for v in bnd}
        outer_lab = max(labs, key=lambda l: d_ring[bnd[lab[bnd] == l]].mean())
        cut_a = [e for e in bedges if lab[e[0]] == outer_lab]
    else:
        cut_a = []
    (ch_e, cl_e), (ch_a, cl_a) = chain_loop(cut_e), chain_loop(cut_a)
    info.update(cut_e=len(ch_e), cut_e_edges=len(cut_e), cut_a=len(ch_a), cut_a_edges=len(cut_a),
                closed=bool(cl_e and cl_a))
    bridge = zipper(ch_e, ch_a, we.P, Pa, zc, cl_e and cl_a)
    info["bridge_tris"] = len(bridge)
    info["_f_a"], info["_main_a"] = f_a, comp == main
    H, info = assemble(E, A, we, wa, keep_e, piece, Pa, D, bridge, info)
    # сетка adidas с итоговыми позициями куска — для переноса текстуры у шва (cmd_kit)
    H["_A_final"] = {"pos": Pa[wa.g], "uv": A["uv"], "tri": A["tri"],
                     "nrm": kit3d._unit(J.node_normals(Pa, wa.T, wa.n)[wa.g])}
    return H, info


def assemble(E, A, we, wa, keep_e, piece, Pa, D, bridge, info):
    """Вершины: Edge (как есть) | шов (узлы adidas с UV Edge) | кусок adidas (UV NHL 24, part 1)."""
    # Edge — вершины кept-треугольников как есть
    te = E["tri"][keep_e]
    used_e = np.unique(te)
    map_e = -np.ones(len(E["pos"]), np.int64)
    map_e[used_e] = np.arange(len(used_e))
    pos = [E["pos"][used_e]]
    nrm = [E["nrm"][used_e]]
    uv = [E["uv"][used_e]]
    part = [np.zeros(len(used_e), np.int64)]
    tris = [map_e[te]]
    base = len(used_e)
    # вершина Edge узла (для шва): вершина любого оставленного треугольника с этим узлом
    node_vert = {}
    for tri in te:
        for v in tri:
            node_vert.setdefault(we.g[v], v)
    # узлы adidas шва — с UV Edge по проекции
    a_nodes = sorted({x[1] for tri in bridge for x in tri if x[0] == "a"})
    Pb = Pa[a_nodes]
    nb_ = kit3d._unit(J.node_normals(Pa, wa.T, wa.n)[a_nodes])
    t, b, dist = kit3d.project(Pb, nb_, E)
    TE = E["tri"][t]
    uvb = (b[:, :, None] * E["uv"][TE]).sum(1)
    nrb = kit3d._unit((b[:, :, None] * E["nrm"][TE]).sum(1))
    info["seam_proj_mm"] = round(float(dist.max() * 1000), 1)
    seam_idx = {a: base + k for k, a in enumerate(a_nodes)}
    pos.append(Pb)
    nrm.append(nrb)
    uv.append(uvb)
    part.append(np.zeros(len(a_nodes), np.int64))
    base += len(a_nodes)
    bt = []
    for tri in bridge:
        bt.append([map_e[node_vert[x[1]]] if x[0] == "e" else seam_idx[x[1]] for x in tri])
    bt = np.array(bt, np.int64)
    # обход шва — наружу (по нормали Edge)
    P_all = np.vstack(pos)
    N_all = np.vstack(nrm)
    fn = np.cross(P_all[bt[:, 1]] - P_all[bt[:, 0]], P_all[bt[:, 2]] - P_all[bt[:, 0]])
    flip = (fn * N_all[bt].sum(1)).sum(1) < 0
    bt[flip] = bt[flip][:, [0, 2, 1]]
    tris.append(bt)
    # кусок adidas — вершины его треугольников, позиции со сдвигом боков
    ta = A["tri"][piece]
    used_a = np.unique(ta)
    map_a = -np.ones(len(A["pos"]), np.int64)
    map_a[used_a] = base + np.arange(len(used_a))
    pa = Pa[wa.g[used_a]]
    # нормали: повернуть вслед за сдвигом; у края куска — как у Edge (шов без излома света)
    N0 = J.node_normals(wa.P, wa.T, wa.n)
    N1 = J.node_normals(Pa, wa.T, wa.n)
    na = kit3d._unit(J.rotate_onto(kit3d._unit(A["nrm"][used_a]), N0[wa.g[used_a]], N1[wa.g[used_a]]))
    # тело куска у шва — нормали Edge (ближайшая точка), к вороту — свои: иначе светотень куска другая (у MIN выезд
    # на белом — серое пятно в форме куска)
    f_a, main_a = info.pop("_f_a"), info.pop("_main_a")
    nd_ = wa.g[used_a]
    t, b, _ = kit3d.project(pa, na, E)
    ne = kit3d._unit((b[:, :, None] * E["nrm"][E["tri"][t]]).sum(1))
    bl = (smooth((f_a[nd_] + NRM_BLEND) / NRM_BLEND) * main_a[nd_])[:, None]
    na = kit3d._unit(na * (1 - bl) + ne * bl)
    seam_n = {a: nrb[k] for k, a in enumerate(a_nodes)}
    for k, v in enumerate(used_a):
        if wa.g[v] in seam_n:
            na[k] = seam_n[wa.g[v]]
    pos.append(pa)
    nrm.append(na)
    uv.append(A["uv"][used_a])
    part.append(np.ones(len(used_a), np.int64))
    tris.append(map_a[ta])
    out = {"pos": np.vstack(pos), "nrm": np.vstack(nrm), "uv": np.vstack(uv), "tri": np.vstack(tris),
           "part": np.concatenate(part)}
    # кости и веса — с Edge (ближайшая точка; у Edge — свои)
    bones = np.zeros((len(out["pos"]), 4), np.int64)
    weights = np.zeros((len(out["pos"]), 4))
    bones[:len(used_e)] = E["bones"][used_e]
    weights[:len(used_e)] = E["weights"][used_e]
    rest = np.arange(len(used_e), len(out["pos"]))
    nb, nw, nd = J.skin_from({"pos": out["pos"][rest], "nrm": out["nrm"][rest]}, E)
    for k, i in enumerate(rest):
        bb = list(nb[k]) + [nb[k][-1]] * (4 - len(nb[k]))
        ww = list(nw[k]) + [0.0] * (4 - len(nw[k]))
        bones[i], weights[i] = bb, ww
    out["bones"], out["weights"] = bones, weights
    info.update(nv=len(out["pos"]), tris=len(out["tri"]), skin_d95_cm=round(float(np.percentile(nd, 95) * 100), 2))
    return out, info


def rels(t, p, lod):
    """Вариант (t, p, lod) → (файл Edge стиля 1, файл adidas стиля 0); t = 'g0'/'g1' — вратарь (рука ловушки)."""
    if isinstance(t, str):
        h = int(t[1:])
        return J.goalie_rel(h, lod, 1), J.goalie_rel(h, lod, 0)
    return J.skater_rel(t, p, lod, 1), J.skater_rel(t, p, lod, 0)


_PAIR = {}


def load_pair(t, p, lod):
    """(Edge, adidas) варианта. Полевые: adidas — заново из NHL 24 (fb.jersey_mesh.morph_to: тело по Edge), ворот —
    на своей высоте NHL 24, без подъёма над «рубашкой» (у сетки adidas перед ворота поднят на 1 см, и граница кокетки
    на куске шла на 1,4 см выше переноса на Edge — у шва была «лесенка», пользователь 18.10; спереди рубашку и так
    закрывает грудь). Вратари — собранная сетка adidas (NHL 24 у них на 6,5 см выше, ворот сдвинут к Edge)."""
    key = (t, p, lod)
    if key not in _PAIR:
        e_rel, a_rel = rels(t, p, lod)
        _, E = J.legacy(e_rel)
        if isinstance(t, str):
            A = mesh_d(rw.Mesh.load(os.path.join(J.OUT, *a_rel.split("/"))))
        else:
            n24 = J.nhl24(J.N24.format(tuck=J.TUCK_OF[t], size=J.SIZE_OF[p], lod=J.LODS[lod]))
            A, _ = J.morph_to(n24, E, t_neck=(np.zeros(3), None), shirt=None, lift_shirt=False)
            A = {k: A[k] for k in ("pos", "nrm", "uv", "tri")}
        _PAIR[key] = (E, A)
    E, A = _PAIR[key]
    return dict(E), dict(A)


def dst_rel(t, p, lod, style):
    if isinstance(t, str):
        return J.goalie_rel(int(t[1:]), lod, style)
    return J.skater_rel(t, p, lod, style)


def write_mesh(H, rel):
    """Гибрид → байты .rx2 по образцу файла игры rel (его секции и шейдер): вершины, полосы по одному треугольнику."""
    base = rw.Mesh.game(rel)
    tv, _ = kit3d.vertex_tangents(H)
    P, N, UV, T = H["pos"], kit3d._unit(H["nrm"]), np.clip(H["uv"], 0.0, 1.0), H["tri"]
    tmpl = base.vertex_raw(0)
    vb = bytearray()
    for i in range(len(P)):
        vb += base.pack_vertex(tmpl, pos=P[i], nrm=N[i], tan=tv[i], uv=UV[i], bones=[int(x) for x in H["bones"][i]])
    tmp = rw.Mesh(base.rebuilt(bytes(vb), J.strips(T)), rel)
    for i in range(tmp.nv):
        tmp.set_skin(i, [int(x) for x in H["bones"][i]], [float(x) for x in H["weights"][i]])
    data = tmp.bytes()
    chk = rw.Mesh(data, rel)
    assert chk.nv == len(P) and len(chk.tris) == len(T), (chk.nv, len(chk.tris))
    return data


def cmd_build(a):
    """Все сетки гибрида: полевые (заправка 0–3 × наплечники 0/1) и вратари (рука 0/1), детализации 2, 0, 3 →
    OUT/rendering/jersey/ под именами стиля a.style (по образцу его файлов игры)."""
    import json
    rep = {}
    for t, p in SKATERS + GOALIES:
        for lod in (2, 0, 3):
            E, A = load_pair(t, p, lod)
            H, info = hybrid(E, A, refine=REFINE_LOD[lod])
            H.pop("_A_final", None)
            info["islands"] = pack_piece(H)
            rel = dst_rel(t, p, lod, a.style)
            path = J.write(a.out, rel, write_mesh(H, rel))
            rep[rel] = info
            print(rel, {k: info[k] for k in ("nv", "tris", "piece_tris", "bridge_tris", "seam_proj_mm")}, flush=True)
    with open(os.path.join(a.out, f"hybrid_build_style{a.style}.json"), "w", encoding="utf-8") as f:
        json.dump(rep, f, ensure_ascii=False, indent=1, default=str)


def cmd_preview(a):
    from PIL import Image, ImageDraw
    E, A = load_pair(0, 1, 2)
    H, info = hybrid(E, A)
    print(info)
    sys.path.insert(0, WORK)
    from views import sheet, join, checker  # noqa: E402 — рабочие скрипты (game/work/nhl24/hybrid)
    sh = mesh_d(rw.Mesh.load(os.path.join(J.OUT, *J.SHIRT[0].split("/"))))
    ch = checker()
    # куску — свой цвет (красноватые шашки): UV куска сдвинуть в правую половину палитры
    tex = np.concatenate([ch, ch * np.array([1.0, 0.75, 0.75])], 1)
    tex[-4:, -4:] = (40, 200, 60)
    Hm = dict(H)
    Hm["uv"] = H["uv"].copy()
    Hm["uv"][:, 0] = np.where(H["part"] == 1, 0.5 + H["uv"][:, 0] * 0.5, H["uv"][:, 0] * 0.5)
    Hm["uv"] = np.clip(Hm["uv"], 0, 0.995)
    Em, Am = dict(E), dict(A)
    Em["uv"] = E["uv"] * [0.5, 1]
    Am["uv"] = A["uv"] * [0.5, 1] + [0.5, 0]
    sheet([("Edge", join(Em, sh)), ("adidas (наш)", join(Am, sh)), ("гибрид (красное — adidas)", join(Hm, sh))],
          a.out, tex=tex)


CLUB_NAME = {"MIN": "minnesota"}


def _club_names():
    """Код клуба → папка комплектов в дампе (fb.kit_batch.CLUBS: MIN → minnesota, NJD → newjersey)."""
    from .kit_batch import CLUBS
    return {code: club for club, _, code in CLUBS}


CLUB_NAME.update(_club_names())


def kit_dir(code, kit):
    return os.path.join(WORK, f"kit_{code}_{kit}")


def cmd_kit(a):
    """Слои комплекта гибрида: свитер — перенос NHL 24 на Edge (fb.pilot, out/all/<КОД>_<форма>) с низом «от края»
    и островами куска из NHL 24 в углах; шрифт, шорты, гетры — оттуда же; карта номеров и рельеф/блик шорт — от
    шаблона EA (info.json → template), как у fb.pilot pack."""
    import shutil
    from PIL import Image
    from . import hem
    from .fonts import normal_map
    code, kit = a.club, a.kit
    club = CLUB_NAME[code]
    d = kit_dir(code, kit)
    os.makedirs(d, exist_ok=True)
    src = os.path.join(REPO, "game", "work", "nhl24", "out", "all", f"{code}_{kit}")
    import json
    tmpl = json.load(open(os.path.join(src, "info.json"), encoding="utf-8"))["template"]
    leg = os.path.join(REPO, "game", "work", "nhl24", "adidas3d", f"kit_{tmpl}")
    if not os.path.exists(os.path.join(leg, "kit.json")):
        J.unpack_kit(tmpl, leg)
    n24c = clean_color(code, kit)
    E, A = load_pair(0, 1, 2)
    A = hybrid(dict(E), dict(A))[0]["_A_final"]       # кусок — где он в гибриде (прижат к Edge у шва)
    n24m = kit3d.load_nhl24(J.N24.format(tuck="notuck", size="large", lod=0))
    cm = np.asarray(Image.open(os.path.join(src, "jersey_cm.png")).convert("RGBA"))
    cm = hem.apply(n24c, n24m, E, cm)
    rgb = seam_bake(cm[..., :3].astype(np.float64), E, A, n24m, n24c)
    rgb = compose(collar_layer(rgb, E, A, n24c, n24=n24m), n24c)
    out = np.dstack([np.clip(rgb, 0, 255).astype(np.uint8), np.full(rgb.shape[:2], 255, np.uint8)])
    Image.fromarray(out).save(os.path.join(d, "jersey_cm.png"))
    nm = np.asarray(Image.open(os.path.join(src, "jersey_nm.png")).convert("RGBA")).astype(np.float64)
    n24n = normal_map(J.n24_tex(club, kit, "normal"), 2048).astype(np.float64)
    nm = compose(nm, n24n)
    Image.fromarray(np.clip(nm, 0, 255).astype(np.uint8)).save(os.path.join(d, "jersey_nm.png"))
    sm = np.asarray(Image.open(os.path.join(src, "jersey_sm.png")).convert("RGBA")).astype(np.float64)
    flat = np.zeros((8, 8, 4))
    flat[..., :3], flat[..., 3] = J.LEG_SM, 255
    sm = compose(sm, flat)
    Image.fromarray(np.clip(sm, 0, 255).astype(np.uint8)).save(os.path.join(d, "jersey_sm.png"))
    for f in ("font_cm", "font_nm", "font_sm", "pant_cm", "sock_cm"):
        shutil.copy2(os.path.join(src, f + ".png"), os.path.join(d, f + ".png"))
    for f in ("name_cm", "pant_nm", "pant_sm"):
        shutil.copy2(os.path.join(leg, f + ".png"), os.path.join(d, f + ".png"))
    print(d)


SLOTS = {("MIN", "home"): "0_14_3", ("MIN", "away"): "0_14_4"}   # формы «Home/Away (adidas)» (реестр nhl24_kits)


def cmd_pack(a):
    """Комплект гибрида → файлы слота (kitpaint pack) в OUT/pack_<слот>/ (раскладка cache:): свитер и шрифт, карта
    номеров, шорты, гетры, превью меню (рендер гибрида)."""
    import shutil
    import subprocess
    code, kit = a.club, a.kit
    slot = SLOTS[(code, kit)]
    d = kit_dir(code, kit)
    u = os.path.join(REPO, "game", "work", "nhl24", "adidas3d", f"kit_{slot}")
    if not os.path.exists(os.path.join(u, "kit.json")):
        J.unpack_kit(slot, u)
    shutil.copy2(os.path.join(u, "kit.json"), os.path.join(d, "kit.json"))
    E, A = load_pair(0, 1, 2)
    H, _ = hybrid(E, A)
    pack_piece(H)
    J.fe_preview(d, H)
    stage = os.path.join(OUT, f"pack_{slot}")
    if os.path.isdir(stage):
        shutil.rmtree(stage)
    r = subprocess.run([sys.executable, os.path.join(REPO, "tools", "kitpaint.py"), "--game", "legacy", "pack", d, slot,
                        stage], capture_output=True, text=True, encoding="utf-8", errors="replace")
    print(r.stdout[-1500:], r.stderr[-1500:])
    for root, _, files in os.walk(stage):
        for f in files:
            print(os.path.relpath(os.path.join(root, f), stage).replace(os.sep, "/"))


def cmd_render(a):
    """Свитер гибрида с текстурой комплекта: спереди, 3/4, сзади, крупно ворот; рядом — NHL 24 и Edge (форма NHL 24)."""
    from PIL import Image, ImageDraw
    code, kit = a.club, a.kit
    d = kit_dir(code, kit)
    t, pp, lod = a.variant
    E, A = load_pair(t if t.startswith("g") else int(t), int(pp), int(lod))
    H, info = hybrid(E, A)
    pack_piece(H)
    shirt_rel = J.SHIRT[1 if t.startswith("g") else 0]
    shp = os.path.join(J.OUT, *shirt_rel.split("/"))
    sh = mesh_d(rw.Mesh.load(shp) if os.path.exists(shp) else rw.Mesh.game(shirt_rel))
    tex = np.asarray(Image.open(os.path.join(d, "jersey_cm.png")).convert("RGB")).astype(np.float64)
    nmap = np.asarray(Image.open(os.path.join(d, "jersey_nm.png")).convert("RGB")).astype(np.float64)
    src = os.path.join(REPO, "game", "work", "nhl24", "out", "all", f"{code}_{kit}")
    old = np.asarray(Image.open(os.path.join(src, "jersey_cm.png")).convert("RGB")).astype(np.float64)
    n24m = kit3d.load_nhl24(J.N24.format(tuck="notuck", size="large", lod=0))
    n24t = np.asarray(Image.open(J.n24_tex(CLUB_NAME[code], kit, "color")).convert("RGB")).astype(np.float64)

    def with_shirt(m, t):
        n = len(m["pos"])
        mm = {"pos": np.vstack([m["pos"], sh["pos"]]), "nrm": np.vstack([m["nrm"], sh["nrm"]]),
              "uv": np.vstack([m["uv"], np.full((len(sh["pos"]), 2), 0.9995)]), "tri": np.vstack([m["tri"], sh["tri"] + n])}
        t = t.copy()
        t[-2:, -2:] = (22, 22, 24)                       # рубашка — тёмная
        return mm, t
    sys.path.insert(0, WORK)
    from views import rot  # noqa: E402
    rows = []
    for title, m, t in (("NHL 24 (своя сетка)", n24m, n24t), ("сейчас: форма NHL 24 на Edge", E, old),
                        ("гибрид: Edge + перед ворота adidas", H, tex)):
        mm, tt = with_shirt(m, t)
        ims = [kit3d.render_lit(mm, tt, "front", 300, frame=(-0.42, 0.42, 0.98, 1.80)),
               kit3d.render_lit(rot(mm, "x", 0), tt, "front", 300, frame=(-0.16, 0.16, 1.46, 1.75)),
               kit3d.render_lit(rot(rot(mm, "y", -40), "x", 15), tt, "front", 300, frame=(-0.16, 0.16, 1.46, 1.75)),
               kit3d.render_lit(rot(mm, "x", 45, c=(0, 1.62, 0)), tt, "front", 300, frame=(-0.16, 0.16, 1.46, 1.75)),
               kit3d.render_lit(rot(rot(mm, "y", 180), "x", 30, c=(0, 1.62, 0)), tt, "front", 300,
                                frame=(-0.16, 0.16, 1.46, 1.75))]
        rows.append((title, ims))
    font = J.label_font(15)
    w = max(i.size[0] for i in rows[0][1])
    hs = [max(i.size[1] for i in r[1]) for r in rows]
    W = sum(i.size[0] + 4 for i in rows[0][1]) + 4
    sheet = Image.new("RGB", (W, sum(h + 24 for h in hs)), (24, 24, 28))
    dr = ImageDraw.Draw(sheet)
    y = 0
    for (title, ims), h in zip(rows, hs):
        dr.text((8, y + 3), title, fill=(235, 235, 235), font=font)
        x = 4
        for im in ims:
            sheet.paste(im, (x, y + 22))
            x += im.size[0] + 4
        y += h + 24
    sheet.save(a.out)
    print(info)
    print(a.out)


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("preview")
    p.add_argument("out")
    p = sub.add_parser("build")
    p.add_argument("--out", default=OUT)
    p.add_argument("--style", type=int, default=0, help="в какой слот стиля писать имена файлов (0 — слот adidas)")
    for name in ("kit", "render", "pack"):
        p = sub.add_parser(name)
        p.add_argument("--club", default="MIN")
        p.add_argument("--kit", default="home")
        if name == "render":
            p.add_argument("out")
            p.add_argument("--variant", nargs=3, default=("0", "1", "2"), metavar=("T", "P", "LOD"),
                           help="заправка (или g0/g1 — вратарь), наплечники, детализация")
    a = ap.parse_args()
    {"preview": cmd_preview, "build": cmd_build, "kit": cmd_kit, "render": cmd_render, "pack": cmd_pack}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
