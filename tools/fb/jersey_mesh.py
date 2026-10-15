"""Свитер NHL 24 (крой adidas, 2017+) → сетки свитера NHL Legacy (.rx2) — пилот 15.10.2026 (docs/nhl24-uniforms.md §14).

Геометрия и развёртка — NHL 24, поэтому текстура комплекта NHL 24 садится как есть (2048 → 1024), без переноса через
3D и без кривизны ворота. Кости и веса — с ближайшей точки свитера Legacy стиля 1 (Edge) того же варианта
(заправка, наплечники; вратарь — своя сетка; установленная у пользователя, с весами края спины NHL 10 — «jersey10»):
барицентры её треугольника, по 4 сильнейших кости. Нормаль — NHL 24,
касательная — вдоль +u развёртки (как у Legacy: бинормаль игра не хранит, cross(n, t) — к −v). Треугольники —
полосами по одному с разрывом 0xFFFF (как у EA — тип 6), порядок обхода — как у Legacy (наружу).

У всех комплектов одного стиля общие сетки, поэтому пилот пишется в слот стиля 0 (ретро-сетки, ими рисуются
комплекты 2006/07 и винтажные): комплекты стиля 1 (Edge — все нынешние) не меняются. Детализации: Legacy _2 (ближняя)
← NHL 24 lod0, _0 ← lod1, _3 ← lod2. Файлы — в раскладке cache: (rendering/jersey/…).

  python -m fb.jersey_mesh map                       # варианты Legacy ↔ NHL 24: профиль низа (заправка), близость
  python -m fb.jersey_mesh build [--out DIR]         # 30 сеток jersey_<вратарь>_0_<h>_<t>_<p>_<lod>.rx2
  python -m fb.jersey_mesh preview TEX.png OUT.png [--out DIR]   # Legacy Edge и пилот: спереди, сзади, ворот, руки вверх
  python -m fb.jersey_mesh kit --club C --kit home --legacy 1_A_V --slot 0_A_V --font-dir DIR   # комплект слота
  python -m fb.jersey_mesh dress OUT.png [--name CROSBY --number 87 --letter C]   # «одетый» свитер (офлайн)

Ассеты NHL 24 — только для личного использования: сетки и картинки — в game/work/ (не в git).
"""
import argparse
import os
import struct
import sys

import numpy as np
from PIL import Image, ImageDraw

from . import kit3d
from .cas import REPO

sys.path.insert(0, os.path.join(REPO, "tools"))
import rw4mesh as rw  # noqa: E402

rw.use_game("legacy")

OUT = os.path.join(REPO, "game", "work", "legacy-data", "models", "adidas")
N24 = "content/character/skater/player/jersey/adidas/components/player_jersey_adidas_{tuck}_{size}_lod{lod}_mesh"
N24_GOALIE = "content/character/skater/goalie/jersey/adidas/components/goalie_jersey_adidas_notuck_lod{lod}_mesh"
LEG = "rendering/jersey/jersey_{g}_{s}_{h}_{t}_{p}_{lod}.rx2"
TUCKS = ("notuck", "fulltuck", "lefttuck", "righttuck")
SIZES = ("large", "small")
LODS = {2: 0, 0: 1, 3: 2}          # детализация Legacy (файл _L) ← lod NHL 24; ближняя (_2) — первой
STYLE_SRC, STYLE_DST = 1, 0        # кости — со стиля 1, пишем в слот стиля 0
SKATER_T, SKATER_P = range(4), range(2)
GOALIE_H = range(2)                # рука ловушки


def skater_rel(t, p, lod, style):
    return LEG.format(g=0, s=style, h=2, t=t, p=p, lod=lod)


def goalie_rel(h, lod, style):
    return LEG.format(g=1, s=style, h=h, t=0, p=0, lod=lod)


# Установленные сетки пользователя (cache:) главнее архива: у свитеров стоит мод весов края спины NHL 10
# (docs/player-models.md, «jersey10») — кости и веса берём с них, чтобы край висел так же.
CACHE = os.path.join(REPO, "nhl-legacy-port", "userdata", "cache", "guest")


def legacy(rel, installed=True):
    p = os.path.join(CACHE, *rel.split("/"))
    m = rw.Mesh.load(p) if installed and os.path.exists(p) else rw.Mesh.game(rel)
    d = {"pos": np.array([p[:3] for p in m.pos], dtype=np.float64), "uv": np.array(m.uv, dtype=np.float64),
         "tri": np.array(m.tris, dtype=np.int64), "nrm": kit3d._unit(np.array(m.nrm, dtype=np.float64)),
         "bones": np.array(m.bones, dtype=np.int64), "weights": np.array(m.weights, dtype=np.float64)}
    return m, d


_N24 = {}


def nhl24(name):
    if name not in _N24:
        _N24[name] = kit3d.load_nhl24(name)
    return _N24[name]


def mean_dist(src, dst):
    """Средняя и 95-я перцентиль расстояния от вершин src до поверхности dst (той же стороны), м."""
    _, _, d = kit3d.project(src["pos"], src["nrm"], dst)
    return float(d.mean()), float(np.percentile(d, 95))


# ---------------------------------------------------------------- соответствие вариантов

# Заправка Legacy t → NHL 24 — по профилю низа (нижняя точка по полосам x, `map`): t0 — навыпуск, t1 — заправлен
# слева (+x), t2 — справа (−x), t3 — весь. Средняя близость поверхностей заправку не различает (заправленный край
# близок к поверхности незаправленного). Наплечники p → размер: плечо p0 1,691 м, p1 1,708; small 1,712, large 1,723.
TUCK_OF = {0: "notuck", 1: "lefttuck", 2: "righttuck", 3: "fulltuck"}
SIZE_OF = {0: "small", 1: "large"}
HEM_BANDS = (-0.3, -0.1, 0.1, 0.25)


def hem_profile(pos):
    """Нижняя точка свитера в полосах x шириной 10 см (м) — отличает заправку."""
    return [round(float(pos[(pos[:, 0] > x0) & (pos[:, 0] < x0 + 0.1)][:, 1].min()), 3) for x0 in HEM_BANDS]


def variant_map():
    """Вариант Legacy (t, p) → (средняя близость, 95 %, tuck, size) NHL 24."""
    out = {}
    for t in SKATER_T:
        for p in SKATER_P:
            _, leg = legacy(skater_rel(t, p, 2, STYLE_SRC))
            md, p95 = mean_dist(leg, nhl24(N24.format(tuck=TUCK_OF[t], size=SIZE_OF[p], lod=0)))
            out[(t, p)] = (md, p95, TUCK_OF[t], SIZE_OF[p])
    return out


# ---------------------------------------------------------------- форма — по свитеру Edge, ворот — NHL 24

# Замечания пользователя к пилоту (15.10): у adidas «приталенность» (полуширина 0,246 м на 1,10 → 0,223 на 1,30 против
# прямых 0,241 у Edge), спина площе на 1–2 см, у вратаря плечи «странные» (свитер NHL 24 на 6,5 см выше вратарского
# Legacy). Поэтому тело свитера садится на поверхность Edge того же варианта (ближайшая точка той же стороны), а ворот
# (до NECK_KEEP[0] от края горловины, переход к NECK_KEEP[1]) сохраняет форму NHL 24 и сдвигается целиком вместе с
# окружением (гармоническое продолжение сдвигов). Вершины-дубли по швам UV сдвигаются одинаково (сварка).
NECK_KEEP = (0.035, 0.07)        # полоса ворота; шире — у вратаря в неё попадал верх плеча (+3 см к Edge)
SIDE_DOT = 0.3                     # нормаль ближайшей точки — той же стороны ткани
# Под воротом у Legacy — «рубашка» (rendering/jersey/shirt_<g>_<g>_<lod>, тёмная горловина под V-вырезом Edge). Ворот
# не ниже её верха + SHIRT_MARGIN ни в одном секторе вокруг шеи (пользователь, 15.10, v2: «проглядывается чёрное
# вокруг шеи» — ворот опустили на 1,7 см, верх рубашки сзади 1,704 м, край ворота стал 1,695).
SHIRT_MARGIN = 0.005
SHIRT_SECTORS = 12
SHIRT = {0: "rendering/jersey/shirt_0_0_2.rx2", 1: "rendering/jersey/shirt_1_1_2.rx2"}
MAX_D = 0.08                       # дальше — сдвиг не берётся, а продолжается от соседей (внутренние кромки)


def weld(pos, eps=1e-5):
    """Вершины с одной позицией (дубли по швам UV и нормалей) → номер узла; -> (узел вершины, первая вершина узла)."""
    key = np.round(pos / eps).astype(np.int64)
    _, first, inv = np.unique(key, axis=0, return_index=True, return_inverse=True)
    return inv.ravel(), first


def adjacency(tri_g, n):
    import scipy.sparse as sp
    e = np.concatenate([tri_g[:, [0, 1]], tri_g[:, [1, 2]], tri_g[:, [2, 0]]])
    e = np.concatenate([e, e[:, ::-1]])
    A = sp.coo_matrix((np.ones(len(e)), (e[:, 0], e[:, 1])), shape=(n, n)).tocsr()
    A.data[:] = 1.0
    return A


def harmonic(A, val, known):
    """Значения в неизвестных узлах — гармоническое продолжение известных по графу сетки."""
    import scipy.sparse as sp
    import scipy.sparse.linalg as sla
    u = ~known
    if not u.any():
        return val.copy()
    L = sp.diags(np.asarray(A.sum(1)).ravel()) - A
    Luu = (L[u][:, u] + sp.identity(int(u.sum())) * 1e-9).tocsc()
    rhs = -(L[u][:, known] @ val[known])
    out = val.copy()
    out[u] = np.stack([sla.spsolve(Luu, rhs[:, c]) for c in range(val.shape[1])], -1)
    return out


def boundary_nodes(tri_g):
    from collections import Counter
    c = Counter()
    for a, b, d in tri_g:
        for e in ((a, b), (b, d), (d, a)):
            c[(min(e), max(e))] += 1
    return np.array(sorted({v for e, k in c.items() if k == 1 for v in e}), dtype=np.int64)


def node_normals(pos, tri_g, n):
    fn = np.cross(pos[tri_g[:, 1]] - pos[tri_g[:, 0]], pos[tri_g[:, 2]] - pos[tri_g[:, 0]])
    out = np.zeros((n, 3))
    for k in range(3):
        np.add.at(out, tri_g[:, k], fn)
    return kit3d._unit(out)


def rotate_onto(v, a, b):
    """Повернуть векторы v поворотом, переводящим единичные a в b (Родриг, построчно)."""
    axis = np.cross(a, b)
    s = np.linalg.norm(axis, axis=1, keepdims=True)
    c = (a * b).sum(1, keepdims=True)
    k = axis / np.maximum(s, 1e-12)
    return v * c + np.cross(k, v) * s + k * (k * v).sum(1, keepdims=True) * (1 - c)


def neck_ring(pos, tri):
    """Узлы края горловины (граница сетки выше 1,45 м у оси) и их середина. -> (позиции сваренной сетки, кромка, середина)."""
    g, first = weld(pos)
    P = pos[first]
    Tg = g[tri]
    bnd = boundary_nodes(Tg)
    neck = bnd[(P[bnd, 1] > 1.45) & (np.abs(P[bnd, 0]) < 0.2)]
    return P, neck, P[neck].mean(0)


def shirt_lift(ring, shirt_pos, t):
    """Подъём края горловины по секторам вокруг шеи, чтобы он был выше рубашки (+SHIRT_MARGIN) — после сдвига t.
    -> (центр (x, z), подъём по секторам, м): у полевых нужен только с боков шеи (верх рубашки там 1,698 м, край
    ворота NHL 24 — 1,690), сзади и спереди запас 0,3–2 см."""
    c = shirt_pos[:, [0, 2]].mean(0)
    r = ring + t
    lift = np.zeros(SHIRT_SECTORS)
    for k in range(SHIRT_SECTORS):
        rs, ss = r[sector_of(r, c) == k], shirt_pos[sector_of(shirt_pos, c) == k]
        if len(rs) and len(ss):
            lift[k] = max(0.0, ss[:, 1].max() + SHIRT_MARGIN - rs[:, 1].max())
    return c, lift


def sector_of(p, c):
    a = np.arctan2(p[:, 2] - c[1], p[:, 0] - c[0])
    return ((a + np.pi) / (2 * np.pi) * SHIRT_SECTORS).astype(int) % SHIRT_SECTORS


def lift_at(p, c, lift):
    """Подъём в точках p — линейно по углу между серединами секторов (по кругу)."""
    a = (np.arctan2(p[:, 2] - c[1], p[:, 0] - c[0]) + np.pi) / (2 * np.pi) * SHIRT_SECTORS - 0.5
    k0 = np.floor(a).astype(int) % SHIRT_SECTORS
    f = a - np.floor(a)
    return lift[k0] * (1 - f) + lift[(k0 + 1) % SHIRT_SECTORS] * f


def morph_to(n24, src, t_neck=None, shirt=None):
    """Сетка NHL 24 с телом по поверхности src (свитер Legacy того же варианта) и воротом NHL 24. -> (сетка, сводка).

    Тело: сдвиг к ближайшей точке src той же стороны; где её нет (внутренние кромки) или где сдвиг выворачивает
    треугольники (подмышки: рядом и рукав, и бок) — продолжение сдвига от соседей. Ворот (до NECK_KEEP[0] от края
    горловины) — целиком на разницу середин горловин src и NHL 24 (у вратаря NHL 24 горловина выше ≈ на 5 см),
    переход к телу — гармонический до NECK_KEEP[1]."""
    from scipy.spatial import cKDTree
    g, first = weld(n24["pos"])
    n = len(first)
    P = n24["pos"][first]
    Tg = g[n24["tri"]]
    N0 = node_normals(P, Tg, n)
    A = adjacency(Tg, n)
    t, b, dist = kit3d.project(P, N0, src)
    T = src["tri"][t]
    q = (b[:, :, None] * src["pos"][T]).sum(1)
    nq = kit3d._unit((b[:, :, None] * src["nrm"][T]).sum(1))
    ok = (dist < MAX_D) & ((nq * N0).sum(1) > SIDE_DOT)
    bnd = boundary_nodes(Tg)
    neck = bnd[(P[bnd, 1] > 1.45) & (np.abs(P[bnd, 0]) < 0.2)]
    dn = cKDTree(P[neck]).query(P)[0]
    s = np.clip((dn - NECK_KEEP[0]) / (NECK_KEEP[1] - NECK_KEEP[0]), 0, 1)
    k = 1.0 - s * s * (3 - 2 * s)
    if t_neck is None:                                 # у дальних детализаций — сдвиг ближней (ворот не «прыгает»)
        _, _, c_src = neck_ring(src["pos"], src["tri"])
        t_neck = c_src - P[neck].mean(0)
        t_neck[0] = 0.0                                # по x не двигаем: обе горловины по оси
        if shirt is not None:                          # но не ниже верха рубашки Legacy: ворот целиком выше, без
            c, lift = shirt_lift(P[neck], shirt, t_neck)   # волны по краю (подъём по секторам гнул бы его на 3 см)
            t_neck[1] += lift.max()
        t_neck = (t_neck, None)
    t_vec, lift = t_neck
    collar_t = np.repeat(t_vec[None], n, 0)
    if lift is not None:
        collar_t[:, 1] += lift_at(P, *lift)
    fn0 = np.cross(P[Tg[:, 1]] - P[Tg[:, 0]], P[Tg[:, 2]] - P[Tg[:, 0]])
    known = ok.copy()
    collar_in, collar_out = k > 0.999, k < 1e-3
    rounds = 0
    for rounds in range(1, 9):
        d_full = harmonic(A, q - P, known)
        vals = d_full.copy()
        vals[collar_in] = collar_t[collar_in]
        D = harmonic(A, vals, collar_in | collar_out)
        deg = np.asarray(A.sum(1)).ravel()[:, None]
        for _ in range(3):  # шум ближайшей точки на складках
            D = 0.5 * D + 0.5 * (A @ D) / np.maximum(deg, 1)
        P2 = P + D
        fn1 = np.cross(P2[Tg[:, 1]] - P2[Tg[:, 0]], P2[Tg[:, 2]] - P2[Tg[:, 0]])
        flipped = (fn0 * fn1).sum(1) <= 0
        if not flipped.any():
            break
        bad = np.zeros(n, bool)
        bad[Tg[flipped].ravel()] = True
        bad |= (A @ bad.astype(float)) > 0             # и соседи
        known &= ~bad
    # что осталось (складка подмышки: рукав и бок тянутся в разные стороны) — разгладить сдвиг вокруг выворотов
    relax = 0
    while flipped.any() and relax < 200:
        relax += 1
        reg = np.zeros(n, bool)
        reg[Tg[flipped].ravel()] = True
        for _ in range(3):
            reg |= (A @ reg.astype(float)) > 0
        reg &= ~collar_in
        avg = (A @ D) / np.maximum(deg, 1)
        D[reg] = 0.3 * D[reg] + 0.7 * avg[reg]
        P2 = P + D
        fn1 = np.cross(P2[Tg[:, 1]] - P2[Tg[:, 0]], P2[Tg[:, 2]] - P2[Tg[:, 0]])
        flipped = (fn0 * fn1).sum(1) <= 0
    N1 = node_normals(P2, Tg, n)
    out = dict(n24)
    out["pos"] = P2[g]
    out["nrm"] = kit3d._unit(rotate_onto(kit3d._unit(n24["nrm"]), N0[g], N1[g]))
    out.pop("_tan", None)
    out.pop("_bit", None)
    shift = np.linalg.norm(D, axis=1)
    out["_t_neck"] = t_neck
    info = {"ok": float(known.mean()), "shift_mean_cm": float(shift.mean() * 100),
            "neck_shift_y_cm": float(t_vec[1] * 100), "neck_shift_z_cm": float(t_vec[2] * 100),
            "neck_lift_max_cm": float(lift[1].max() * 100) if lift is not None else 0.0,
            "flip_rounds": rounds, "relax": relax, "flipped_left": int(flipped.sum())}
    return out, info


# ---------------------------------------------------------------- кости и веса

def skin_from(dst, src):
    """Кости и веса вершин dst (сетка NHL 24) — с ближайшей точки src (сетка Legacy с bones/weights): веса трёх вершин
    треугольника по барицентрам, сложенные по костям; 4 сильнейших, сумма 1."""
    tri, bar, dist = kit3d.project(dst["pos"], dst["nrm"], src)
    T = src["tri"][tri]
    bones, weights = [], []
    for i in range(len(tri)):
        acc = {}
        for k in range(3):
            vi = T[i, k]
            for b, w in zip(src["bones"][vi], src["weights"][vi]):
                if w > 0:
                    acc[int(b)] = acc.get(int(b), 0.0) + bar[i, k] * w
        top = sorted(acc.items(), key=lambda x: -x[1])[:4]
        s = sum(w for _, w in top) or 1.0
        bones.append([b for b, _ in top])
        weights.append([w / s for _, w in top])
    return bones, weights, dist


# ---------------------------------------------------------------- сборка .rx2

def strips(tris):
    """Треугольники → индексы полос: по одному треугольнику, разрыв 0xFFFF (первый в полосе — прямой обход)."""
    idx = []
    for a, b, c in tris:
        if idx:
            idx.append(rw.STRIP_RESTART)
        idx += [int(a), int(b), int(c)]
    return idx


def build_one(n24, skin_src_rel, dst_rel, morph=True, t_neck=None, shirt_rel=None):
    """Сетка dst_rel (файл Legacy слота, его секции и шейдер) с развёрткой и воротом n24, телом по skin_src_rel
    (morph_to); кости — с skin_src_rel, у дублей по швам UV — одинаковые (по сваренным узлам)."""
    _, src = legacy(skin_src_rel)
    base = rw.Mesh.game(dst_rel)
    minfo = {}
    if morph:
        shirt = None
        if shirt_rel:
            sm = rw.Mesh.game(shirt_rel)
            shirt = np.array([p[:3] for p in sm.pos], dtype=np.float64)
        n24, minfo = morph_to(n24, src, t_neck, shirt)
    g, first = weld(n24["pos"])
    Tg = g[n24["tri"]]
    nodes = {"pos": n24["pos"][first], "nrm": node_normals(n24["pos"][first], Tg, len(first))}
    nb, nw, nd = skin_from(nodes, src)
    bones, weights, dist = [nb[i] for i in g], [nw[i] for i in g], nd[g]
    tv, _ = kit3d.vertex_tangents(n24)
    P, N, UV, T = n24["pos"], kit3d._unit(n24["nrm"]), np.clip(n24["uv"], 0.0, 1.0), n24["tri"]
    # обход — как у EA в NHL 24 (у навыпуск 100 % треугольников наружу, как у Legacy); у заправленных 11–16
    # треугольников складки «смотрят» против нормалей вершин — их не трогаем, только считаем
    fn = np.cross(P[T[:, 1]] - P[T[:, 0]], P[T[:, 2]] - P[T[:, 0]])
    flip = (fn * N[T].sum(1)).sum(1) < 0
    tmpl = base.vertex_raw(0)
    vb = bytearray()
    for i in range(len(P)):
        b4 = list(bones[i]) + [bones[i][-1]] * (4 - len(bones[i]))
        w4 = list(weights[i]) + [0.0] * (4 - len(weights[i]))
        v = base.pack_vertex(tmpl, pos=P[i], nrm=N[i], tan=tv[i], uv=UV[i], bones=b4, weights=None)
        vb += v
    tmp = rw.Mesh(base.rebuilt(bytes(vb), strips(T)), dst_rel)
    for i in range(tmp.nv):  # веса — точной квантовкой (сумма ровно 255)
        tmp.set_skin(i, bones[i], weights[i])
    data = tmp.bytes()
    chk = rw.Mesh(data, dst_rel)
    assert chk.nv == len(P) and len(chk.tris) == len(T), (chk.nv, len(chk.tris))
    if morph:
        minfo["_t_neck"] = n24["_t_neck"]
    return data, {"nv": chk.nv, "tris": len(chk.tris), "against_nrm": int(flip.sum()),
                  "skin_d_mean_cm": round(float(dist.mean()) * 100, 2),
                  "skin_d95_cm": round(float(np.percentile(dist, 95)) * 100, 2),
                  **{k: (v if k.startswith("_") else round(v, 3)) for k, v in minfo.items()}}


def write(out_dir, rel, data):
    p = os.path.join(out_dir, *rel.split("/"))
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "wb") as f:
        f.write(data)
    return p


def cmd_map(a):
    print("низ по полосам x", HEM_BANDS, "(м)")
    for tuck in TUCKS:
        print(f"  NHL 24 {tuck:9}", hem_profile(nhl24(N24.format(tuck=tuck, size="large", lod=0))["pos"]))
    for t in SKATER_T:
        print(f"  Legacy t{t}      ", hem_profile(legacy(skater_rel(t, 0, 2, STYLE_SRC))[1]["pos"]))
    for (t, p), (md, p95, tuck, size) in sorted(variant_map().items()):
        print(f"Legacy t{t} p{p} → {tuck}_{size}: {md * 100:.1f} см (95 % — {p95 * 100:.1f})")


def cmd_build(a):
    vm = variant_map()
    n = 0
    for (t, p), (_, _, tuck, size) in sorted(vm.items()):
        tn = None
        for lod, l24 in LODS.items():
            n24 = nhl24(N24.format(tuck=tuck, size=size, lod=l24))
            data, info = build_one(n24, skater_rel(t, p, 2, STYLE_SRC), skater_rel(t, p, lod, STYLE_DST), t_neck=tn,
                                   shirt_rel=SHIRT[0])
            tn = info.pop("_t_neck")
            write(a.out, skater_rel(t, p, lod, STYLE_DST), data)
            n += 1
            print(f"{skater_rel(t, p, lod, STYLE_DST)} ← {tuck}_{size} lod{l24}: {info}")
    for h in GOALIE_H:
        tn = None
        for lod, l24 in LODS.items():
            n24 = nhl24(N24_GOALIE.format(lod=l24))
            data, info = build_one(n24, goalie_rel(h, 2, STYLE_SRC), goalie_rel(h, lod, STYLE_DST), t_neck=tn,
                                   shirt_rel=SHIRT[1])
            tn = info.pop("_t_neck")
            write(a.out, goalie_rel(h, lod, STYLE_DST), data)
            n += 1
            print(f"{goalie_rel(h, lod, STYLE_DST)} ← goalie lod{l24}: {info}")
    print(f"{n} сеток → {a.out}")


# ---------------------------------------------------------------- превью: поза «руки вверх»

ARM_L = (48, 49, 50, 52, 53)       # кости рук свитера (первая — плечевой сустав)
ARM_R = (79, 80, 81, 83, 84)


def posed(mesh_d, bones, weights, joints, deg=55.0):
    """Позиции после подъёма обеих рук на deg° вокруг оси Z плечевых суставов (кости руки — как одно целое)."""
    P = mesh_d["pos"]
    out = np.zeros_like(P)
    mats = {}
    for arm, sgn in ((ARM_L, 1.0), (ARM_R, -1.0)):
        # сторона руки: по x сустава (у Legacy +x — левая сторона игрока)
        j = np.array(joints[arm[0]])
        s = np.sign(j[0]) or sgn
        a = np.radians(deg) * s
        R = np.array([[np.cos(a), -np.sin(a), 0], [np.sin(a), np.cos(a), 0], [0, 0, 1]])
        for b in arm:
            mats[b] = (R, j)
    for i in range(len(P)):
        acc = np.zeros(3)
        for b, w in zip(bones[i], weights[i]):
            if w <= 0:
                continue
            if b in mats:
                R, j = mats[b]
                acc += w * (R @ (P[i] - j) + j)
            else:
                acc += w * P[i]
        out[i] = acc
    m = dict(mesh_d)
    m["pos"] = out
    m.pop("_tan", None)
    m.pop("_bit", None)
    # нормали — по позе
    T = m["tri"]
    fn = np.cross(out[T[:, 1]] - out[T[:, 0]], out[T[:, 2]] - out[T[:, 0]])
    nn = np.zeros_like(out)
    for k in range(3):
        np.add.at(nn, T[:, k], fn)
    m["nrm"] = kit3d._unit(nn)
    return m


def label_font(size=17):
    from PIL import ImageFont
    for f in ("C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/arial.ttf"):
        if os.path.exists(f):
            return ImageFont.truetype(f, size)
    return ImageFont.load_default()


def cmd_preview(a):
    skel = rw.Skeleton.game()
    tex24 = kit3d.load_tex(a.tex)
    _, leg = legacy(skater_rel(0, 1, 2, STYLE_SRC))
    leg_tex = kit3d.load_tex(a.legacy_tex) if a.legacy_tex else None
    pilot_m = rw.Mesh.load(os.path.join(a.out, *skater_rel(0, 1, 2, STYLE_DST).split("/")))
    pil = {"pos": np.array([p[:3] for p in pilot_m.pos]), "uv": np.array(pilot_m.uv), "tri": np.array(pilot_m.tris),
           "nrm": kit3d._unit(np.array(pilot_m.nrm))}
    rows = []
    for title, md, tex, bones, weights in (
            ("Legacy Edge (стиль 1)", leg, leg_tex, leg["bones"], leg["weights"]),
            ("пилот: сетка NHL 24 adidas в Legacy", pil, tex24, np.array(pilot_m.bones), np.array(pilot_m.weights))):
        t = tex if tex is not None else np.full((8, 8, 3), 180.0)
        up = posed(md, bones, weights, skel.joints)
        ims = [kit3d.render_lit(md, t, "front", 420), kit3d.render_lit(md, t, "back", 420),
               kit3d.render_lit(md, t, "front", 420, frame=(-0.2, 0.2, 1.42, 1.74)),
               kit3d.render_lit(up, t, "front", 420, frame=(-0.95, 0.95, 0.85, 2.05))]
        rows.append((title, ims))
    W = sum(im.size[0] for im in rows[0][1]) + 10 * 5
    H = sum(max(im.size[1] for im in ims) + 34 for _, ims in rows)
    sheet = Image.new("RGB", (W, H), (24, 24, 28))
    d = ImageDraw.Draw(sheet)
    font = label_font()
    y = 0
    for title, ims in rows:
        d.text((10, y + 6), title, fill=(235, 235, 235), font=font)
        x = 10
        for im in ims:
            sheet.paste(im, (x, y + 30))
            x += im.size[0] + 10
        y += max(im.size[1] for im in ims) + 34
    sheet.save(a.png)
    print(a.png)


# ---------------------------------------------------------------- комплект в развёртке NHL 24

EXTRACT = os.path.join(REPO, "game", "work", "nhl24", "extract")
KITS_OUT = os.path.join(REPO, "game", "work", "nhl24", "out", "kits")
LEG_SM = 16                        # блик ткани Legacy (медиана jersey_sm комплектов EA ≈ 16 из 255)


def n24_tex(club, kit, layer):
    return os.path.join(EXTRACT, f"club_{club}", "character", "skater", "league", "nhl", club, "adidas", kit,
                        f"jersey_adidas_{club}_{kit}_{layer}.png")


def name_map(leg_png, leg_d, dst_d, size=256):
    """Карта мест номера/фамилии (name_*_cm, 256²: синий канал — номер зоны, 255 — фон) из развёртки Legacy в
    развёртку dst: тексели каждой зоны → точка свитера Legacy → ближайшая точка dst → её UV; зона в новой карте —
    прямоугольник по этим точкам (игра берёт прямоугольник зоны из самой карты: у комплектов EA они разные).
    -> (RGBA, {зона: (x0, y0, x1, y1)}, {зона: «вверх» на свитере — к −v (True) у dst})."""
    src = np.asarray(Image.open(leg_png).convert("RGBA"))
    tid, bar = kit3d.raster_uv(leg_d, size)
    out = np.full((size, size, 4), 255, np.uint8)
    rects, up_ok = {}, {}
    P, T, N = leg_d["pos"], leg_d["tri"], leg_d["nrm"]
    tv_d, bv_d = kit3d.vertex_tangents(dst_d)
    for z in sorted(set(src[..., 2][src[..., 2] < 255].tolist())):
        ys, xs = np.nonzero((src[..., 2] == z) & (tid >= 0))
        if len(ys) == 0:
            continue
        tr, bb = T[tid[ys, xs]], bar[ys, xs]
        p = (bb[:, :, None] * P[tr]).sum(1)
        n = kit3d._unit((bb[:, :, None] * N[tr]).sum(1))
        t2, b2, _ = kit3d.project(p, n, dst_d)
        T2 = dst_d["tri"][t2]
        uv = (b2[:, :, None] * dst_d["uv"][T2]).sum(1) * size
        x0, y0 = np.floor(uv.min(0)).astype(int)
        x1, y1 = np.ceil(uv.max(0)).astype(int)
        x0, y0, x1, y1 = max(x0, 0), max(y0, 0), min(x1, size - 1), min(y1, size - 1)
        out[y0:y1 + 1, x0:x1 + 1] = (255, 255, z, 255)
        rects[z] = (int(x0), int(y0), int(x1), int(y1))
        # +v развёртки dst в зоне должна смотреть вниз по свитеру (как у Legacy): бинормаль вдоль −Y
        bvz = (b2[:, :, None] * bv_d[T2]).sum(1).mean(0)
        up_ok[z] = bool(bvz[1] < 0)
    return out, rects, up_ok


SLEEVE_ZONES = (2, 3)              # номера на рукавах (у EA — у локтя: центр на |x| 0,40 м при плече 0,21 и локте 0,43)
SLEEVE_UP_CM = 8.0                 # пользователь (15.10): у adidas номер — ближе к плечевому суставу
# Фамилия (зона 0) — пользователь (15.10, после теста пилота): «слишком близко к номерам, слишком большие буквы,
# слишком большое расстояние между буквами» → зона меньше (ширина, высота — доли размера EA) и выше на NAME_UP_CM.
# По фото Кросби с матчей 2022–2025 (Getty, 15.10): номер ≈ 0,43 высоты спинки (≈ 32 см, правило НХЛ 12″) против 26,8 см
# у EA, буквы фамилии ≈ 6 см (у EA 8,9), зазор до номера ≈ 4,5 см.
# Тест v3 в игре (пользователь, 15.10): «номер поменьше, верхняя точка там же; фамилию чуть побольше и немного ниже».
NAME_ZONE, NAME_SCALE, NAME_UP_CM = 0, (0.79, 0.76), 1.0
NUMBER_ZONE, NUMBER_SCALE = 1, (0.9, 1.0)         # от верхнего края зоны: верх остаётся, меньше — к низу спины


def uv_jacobian(m, tri, size):
    """dP/d(пиксель развёртки size²) треугольника tri: 3×2 (столбцы — по u и по v)."""
    T = m["tri"][tri]
    P, U = m["pos"][T], m["uv"][T] * size
    E = np.stack([P[1] - P[0], P[2] - P[0]], 1)
    D = np.array([[U[1, 0] - U[0, 0], U[2, 0] - U[0, 0]], [U[1, 1] - U[0, 1], U[2, 1] - U[0, 1]]])
    return E @ np.linalg.inv(D)


def name_map_cm(leg_png, leg_d, dst_d, size=256, sleeve_up_cm=SLEEVE_UP_CM, grid=5):
    """Карта мест номера/фамилии в развёртке dst с размерами зон в сантиметрах — как у Legacy.

    Сетка grid×grid точек внутри зоны Legacy (у рукавов — сдвинутая вдоль руки к плечу на sleeve_up_cm) → точки
    свитера Legacy → ближайшие точки dst → их UV; по парам — аффинное соответствие пикселей Legacy → пикселей dst
    (наименьшие квадраты), зона dst — образ прямоугольника Legacy (рамка параллелограмма). Без раздувания рамки, как у
    переноса тексель-в-тексель (фамилия была на 32 % выше), и без шума якобиана одного треугольника.
    -> (RGBA, {зона: прямоугольник}, {зона: сводка})."""
    src = np.asarray(Image.open(leg_png).convert("RGBA"))
    tid, bar = kit3d.raster_uv(leg_d, size)
    tid_d, _ = kit3d.raster_uv(dst_d, size)
    out = np.full((size, size, 4), 255, np.uint8)
    rects, info = {}, {}
    LP, LT, LN = leg_d["pos"], leg_d["tri"], leg_d["nrm"]

    def on_leg(xs, ys):
        ix = np.clip(xs.astype(int), 0, size - 1)
        iy = np.clip(ys.astype(int), 0, size - 1)
        t = tid[iy, ix]
        ok = t >= 0
        bb = bar[iy[ok], ix[ok]]
        T = LT[t[ok]]
        return ok, (bb[:, :, None] * LP[T]).sum(1), kit3d._unit((bb[:, :, None] * LN[T]).sum(1)), t[ok]

    for z in sorted(set(src[..., 2][src[..., 2] < 255].tolist())):
        ys, xs = np.nonzero(src[..., 2] == z)
        x0, x1, y0, y1 = xs.min(), xs.max() + 1, ys.min(), ys.max() + 1
        w, h = x1 - x0, y1 - y0
        off = np.zeros(2)
        if z in SLEEVE_ZONES and sleeve_up_cm:
            # вдоль руки — ось u зоны (у EA так у обоих рукавов); к плечу — туда, где |x| меньше
            cx, cy = np.array([(x0 + x1) / 2.0]), np.array([(y0 + y1) / 2.0])
            _, pc, _, tc = on_leg(cx, cy)
            Jl = uv_jacobian(leg_d, tc[0], size)
            du = 1.0 if abs((pc[0] + Jl[:, 0])[0]) < abs(pc[0][0]) else -1.0
            off = np.array([du * sleeve_up_cm / 100.0 / np.linalg.norm(Jl[:, 0]), 0.0])
        if z == NAME_ZONE and NAME_UP_CM:
            # вверх по свитеру — вдоль v зоны, туда, где y точки свитера больше
            cx, cy = np.array([(x0 + x1) / 2.0]), np.array([(y0 + y1) / 2.0])
            _, pc, _, tc = on_leg(cx, cy)
            Jl = uv_jacobian(leg_d, tc[0], size)
            dv = 1.0 if (pc[0] + Jl[:, 1])[1] > pc[0][1] else -1.0
            off = np.array([0.0, dv * NAME_UP_CM / 100.0 / np.linalg.norm(Jl[:, 1])])
        gx, gy = np.meshgrid(np.linspace(x0 + 0.5, x1 - 0.5, grid), np.linspace(y0 + 0.5, y1 - 0.5, grid))
        gx, gy = gx.ravel() + off[0], gy.ravel() + off[1]
        ok, p, nrm, tl = on_leg(gx, gy)
        t2, b2, d2 = kit3d.project(p, nrm, dst_d)
        uvd = (b2[:, :, None] * dst_d["uv"][dst_d["tri"][t2]]).sum(1) * size
        X = np.stack([gx[ok], gy[ok], np.ones(ok.sum())], 1)
        keep = d2 < 0.03                                  # дальше 3 см — точка ушла на чужую поверхность (ворот)
        for _ in range(4):                                # 3×2: [x, y, 1] Legacy → (u, v) dst, пиксели; выбросы — прочь
            M, *_ = np.linalg.lstsq(X[keep], uvd[keep], rcond=None)
            res = np.linalg.norm(X @ M - uvd, axis=1)
            new_keep = keep & (res < max(3.0, 3 * np.median(res[keep])))
            if new_keep.sum() < 6 or (new_keep == keep).all():
                break
            keep = new_keep
        corners = np.array([[x0, y0, 1], [x1, y0, 1], [x0, y1, 1], [x1, y1, 1]], float)
        if z == NAME_ZONE:                              # меньше — от центра зоны
            cc = np.array([(x0 + x1) / 2.0, (y0 + y1) / 2.0])
            corners[:, :2] = cc + (corners[:, :2] - cc) * np.array(NAME_SCALE)
        if z == NUMBER_ZONE:                            # выше: верх (к фамилии) на месте — у EA верх зоны — бо́льшие v
            top = corners[:, 1].max()
            cc = np.array([(x0 + x1) / 2.0, top])
            corners[:, :2] = cc + (corners[:, :2] - cc) * np.array(NUMBER_SCALE)
        corners[:, :2] += off
        cd = corners @ M
        rx0, ry0 = int(round(cd[:, 0].min())), int(round(cd[:, 1].min()))
        rx1, ry1 = int(round(cd[:, 0].max())) - 1, int(round(cd[:, 1].max())) - 1
        rx0, ry0, rx1, ry1 = max(rx0, 0), max(ry0, 0), min(rx1, size - 1), min(ry1, size - 1)
        out[ry0:ry1 + 1, rx0:rx1 + 1] = (255, 255, z, 255)
        rects[z] = (rx0, ry0, rx1, ry1)
        cover = float((tid_d[ry0:ry1 + 1, rx0:rx1 + 1] >= 0).mean())
        Jl = uv_jacobian(leg_d, tl[len(tl) // 2], size)
        res = np.abs(X[keep] @ M - uvd[keep]).max()
        info[z] = {"legacy_px": (int(w), int(h)),
                   "cm": (round(float(w * np.linalg.norm(Jl[:, 0]) * 100), 1), round(float(h * np.linalg.norm(Jl[:, 1]) * 100), 1)),
                   "dst_px": (rx1 - rx0 + 1, ry1 - ry0 + 1), "scale": (round(float(M[0, 0]), 3), round(float(M[1, 1]), 3)),
                   "shear": (round(float(M[1, 0]), 3), round(float(M[0, 1]), 3)), "fit_err_px": round(float(res), 2),
                   "points": f"{int(keep.sum())}/{len(keep)}",
                   "on_mesh": round(cover, 3), "dist_cm": round(float(d2.mean()) * 100, 2)}
    return out, rects, info


def zone_overlay(tex, nm_rgba, alpha=0.6):
    """Текстура с зонами карты номеров поверх (красным; размер карты → размер текстуры) — для проверки на 3D."""
    H, W = tex.shape[:2]
    z = np.asarray(Image.fromarray(nm_rgba).resize((W, H), Image.NEAREST))
    m = z[..., 2] < 255
    out = tex[..., :3].astype(np.float64).copy()
    out[m] = out[m] * (1 - alpha) + np.array([255.0, 30.0, 30.0]) * alpha
    return out


# Нашивки шире, чем надо (пользователь, 15.10: «логотип в ширину растянут», у вратаря — сильнее): герб PIT
# спереди, ширина/высота по хорде (вид спереди) — у EA на Edge 1,06; NHL 24 на своей сетке — 1,18; на сетке с телом
# Edge — 1,26 (грудь площе), у вратаря — 1,25. Поэтому нашивки (готовый свитер минус основа без нашивок) кладутся на
# основу сжатыми по u вокруг своей середины: DECAL_SQUEEZE = 1,06 / 1,26.
DECAL_SQUEEZE = 0.84
DECAL_DIFF = 60                    # порог «нашивка ≠ основа» (сумма |ΔRGB|)
DECAL_MIN_PX = 40                  # меньше — шум сжатия, не нашивка (2048²)


def squeeze_decals(color, base, layers, f=DECAL_SQUEEZE):
    """Нашивки (связные участки color ≠ base, с заливкой дыр) — на основу, сжатые по u в f раз от своей середины.
    layers — [(готовый слой, слой основы)] той же раскладки (цвет, рельеф): правка одна на все. -> (слои, сводка)."""
    from scipy import ndimage
    diff = np.abs(color.astype(np.int32) - base.astype(np.int32)).sum(-1) > DECAL_DIFF
    diff = ndimage.binary_closing(diff, iterations=2)
    # близкие куски (детали герба, логотип и надпись спонсора) — одна нашивка, сжатие от общей середины
    lab, n = ndimage.label(ndimage.binary_dilation(diff, iterations=8))
    outs = [b.astype(np.float64).copy() for _, b in layers]
    info = []
    for i, sl in enumerate(ndimage.find_objects(lab), start=1):
        m = ndimage.binary_fill_holes((lab[sl] == i) & diff[sl])
        if m.sum() < DECAL_MIN_PX:
            continue
        ys, xs = sl
        y0, y1, x0, x1 = ys.start, ys.stop, xs.start, xs.stop
        w = x1 - x0
        if y1 - y0 < 4 or w > 12 * (y1 - y0):        # полосы и линии шва — не нашивки
            continue
        nw = max(1, int(round(w * f)))
        nx0 = x0 + (w - nw) // 2
        mm = np.asarray(Image.fromarray((ndimage.binary_dilation(m, iterations=1) * 255).astype(np.uint8))
                        .resize((nw, y1 - y0), Image.BILINEAR)).astype(np.float64)[..., None] / 255.0
        for (full, _), out in zip(layers, outs):
            crop = full[y0:y1, x0:x1].astype(np.float32)
            sq = np.stack([np.asarray(Image.fromarray(crop[..., c]).resize((nw, y1 - y0), Image.LANCZOS))
                           for c in range(crop.shape[-1])], -1).astype(np.float64)
            region = out[y0:y1, nx0:nx0 + nw]
            out[y0:y1, nx0:nx0 + nw] = region * (1 - mm) + sq * mm
        info.append((int(x0), int(y0), int(w), int(y1 - y0)))
    return [np.clip(o, 0, 255).astype(np.uint8) for o in outs], info


def cmd_kit(a):
    """Комплект клуба NHL 24 (adidas) в развёртке NHL 24 → папка PNG для kitpaint pack под номер слота a.slot
    (стиль 0) + сборка в a.dst (раскладка cache:). Шорты, гетры — из комплекта Legacy a.legacy, шрифт — атлас NHL 24
    из fb.kit_batch (out/kits/<КОД>_<комплект>), меню и шаблон — от слота."""
    import shutil
    import subprocess
    work = os.path.join(REPO, "game", "work", "nhl24", "adidas3d")
    d = os.path.join(work, f"pack_{a.slot}")
    os.makedirs(d, exist_ok=True)
    unpack = lambda kit: os.path.join(work, f"kit_{kit}")  # noqa: E731
    for kit in (a.slot, a.legacy):
        if not os.path.exists(os.path.join(unpack(kit), "kit.json")):
            subprocess.run([sys.executable, os.path.join(REPO, "tools", "kitpaint.py"), "--game", "legacy", "unpack",
                            kit, unpack(kit)], check=True, capture_output=True)
    # свитер: цвет и рельеф NHL 24 (2048 → 1024), нашивки — сжатые по ширине (squeeze_decals; если у комплекта нет
    # основы без нашивок — как есть); блик — ровный, как ткань Legacy
    from .fonts import normal_map
    rgb = lambda p: np.asarray(Image.open(p).convert("RGB"))  # noqa: E731
    color, normal = rgb(n24_tex(a.club, a.kit, "color")), rgb(n24_tex(a.club, a.kit, "normal"))
    if os.path.exists(n24_tex(a.club, a.kit, "base_color")) and a.squeeze < 1.0:
        base, base_n = rgb(n24_tex(a.club, a.kit, "base_color")), rgb(n24_tex(a.club, a.kit, "base_normal"))
        (color, normal), dinfo = squeeze_decals(color, base, [(color, base), (normal, base_n)], a.squeeze)
        print(f"нашивок сжато по ширине ×{a.squeeze}: {len(dinfo)} — {dinfo}")
    Image.fromarray(color).resize((1024, 1024), Image.LANCZOS).convert("RGBA").save(os.path.join(d, "jersey_cm.png"))
    tmp_n = os.path.join(d, "_normal_2048.png")
    Image.fromarray(normal).save(tmp_n)
    Image.fromarray(normal_map(tmp_n, 1024)).save(os.path.join(d, "jersey_nm.png"))
    os.remove(tmp_n)
    sm = np.zeros((1024, 1024, 4), np.uint8)
    sm[..., :3], sm[..., 3] = LEG_SM, 255
    Image.fromarray(sm).save(os.path.join(d, "jersey_sm.png"))
    # карта номеров — из комплекта Legacy (развёртка Edge) в развёртку NHL 24
    _, leg = legacy(skater_rel(0, 1, 2, STYLE_SRC))
    built = os.path.join(a.dst, *skater_rel(0, 1, 2, STYLE_DST).split("/"))   # собранная сетка (build) — с телом Edge
    bm = rw.Mesh.load(built)
    dst = {"pos": np.array([p[:3] for p in bm.pos]), "uv": np.array(bm.uv), "tri": np.array(bm.tris),
           "nrm": kit3d._unit(np.array(bm.nrm))}
    nmap, rects, zinfo = name_map_cm(os.path.join(unpack(a.legacy), "name_cm.png"), leg, dst)
    Image.fromarray(nmap).save(os.path.join(d, "name_cm.png"))
    print("зоны номеров (x0, y0, x1, y1 из 256):", rects)
    for z, v in zinfo.items():
        print(f"  зона {z}: {v}")
    # шрифт NHL 24 (fb.kit_batch), шорты и гетры Legacy, меню и kit.json слота
    for f in ("font_cm", "font_nm", "font_sm"):
        shutil.copy2(os.path.join(a.font_dir, f + ".png"), os.path.join(d, f + ".png"))
    for f in ("pant_cm", "pant_nm", "pant_sm", "sock_cm"):
        shutil.copy2(os.path.join(unpack(a.legacy), f + ".png"), os.path.join(d, f + ".png"))
    for f in ("fe.png", "kit.json"):
        shutil.copy2(os.path.join(unpack(a.slot), f), os.path.join(d, f))
    r = subprocess.run([sys.executable, os.path.join(REPO, "tools", "kitpaint.py"), "--game", "legacy", "pack", d,
                        a.slot, a.dst], capture_output=True, text=True, encoding="utf-8", errors="replace")
    print(r.stdout[-1500:], r.stderr[-1500:])
    # проверка: зоны номеров на 3D (пилотная сетка и Legacy Edge со своей картой)
    tex = np.asarray(Image.open(os.path.join(d, "jersey_cm.png")).convert("RGB")).astype(np.float64)
    ltex = np.asarray(Image.open(os.path.join(unpack(a.legacy), "jersey_cm.png")).convert("RGB")).astype(np.float64)
    lmap = np.asarray(Image.open(os.path.join(unpack(a.legacy), "name_cm.png")).convert("RGBA"))
    ims = []
    for md, t, z in ((leg, ltex, lmap), (dst, tex, nmap)):
        ov = zone_overlay(t, z)
        ims.append([kit3d.render_lit(md, ov, v, 360) for v in ("front", "back", "left", "right")])
    W = sum(im.size[0] + 8 for im in ims[0])
    H = sum(row[0].size[1] + 8 for row in ims)
    sheet = Image.new("RGB", (W, H), (24, 24, 28))
    y = 0
    for row in ims:
        x = 0
        for im in row:
            sheet.paste(im, (x, y))
            x += im.size[0] + 8
        y += row[0].size[1] + 8
    p = os.path.join(work, f"zones_{a.slot}.png")
    sheet.save(p)
    print(p)


# ---------------------------------------------------------------- «одетый» свитер: фамилия, номер, буква (офлайн)

# Атлас шрифта комплекта (512², раскладка EA — у NHL 24 та же ×2): строки (y0, y1, x-диапазон) и порядок знаков.
FONT_ROWS = (("ABCDEFGHIJKLMNO", 1, 48, (0, 512)), ("PQRSTUVWXYZ", 49, 98, (0, 420)),
             ("01234", 115, 238, (0, 420)), ("56789", 242, 367, (0, 420)), ("C", 83, 190, (420, 512)),
             ("A", 195, 302, (420, 512)), ("0123456789", 379, 438, (0, 512)), ("0123456789", 450, 512, (0, 512)))
LETTER_GAP = 0.06                  # разрядка фамилии — доля высоты букв (для картинки; как у игры — не разбиралось)


def font_glyphs(font_png):
    """Знаки атласа: {(строка, знак): RGBA} — нарезка по пустым столбцам внутри строки."""
    a = np.asarray(Image.open(font_png).convert("RGBA"))
    out = {}
    for row, (chars, y0, y1, (xa, xb)) in enumerate(FONT_ROWS):
        al = a[y0:y1, xa:xb, 3] > 40
        cols = al.any(0)
        segs, x = [], 0
        while x < len(cols):
            if cols[x]:
                s0 = x
                while x < len(cols) and cols[x]:
                    x += 1
                segs.append((s0, x))
            else:
                x += 1
        segs = [s for s in segs if s[1] - s[0] > 3][:len(chars)]
        for ch, (s0, s1) in zip(chars, segs):
            g = a[y0:y1, xa + s0:xa + s1]
            ys = np.nonzero(g[..., 3].any(1))[0]
            out[(row, ch)] = g[ys.min():ys.max() + 1]
    return out


def text_image(glyphs, row, text, gap=LETTER_GAP):
    """Строка знаков (строка атласа row; для букв — row=None: A–O из первой строки, P–Z из второй): высота — общая
    (по самому высокому), разрядка — gap × высоты."""
    gs = [glyphs[(row if row is not None else (0 if ch in FONT_ROWS[0][0] else 1), ch)] for ch in text]
    h = max(g.shape[0] for g in gs)
    sp = int(round(gap * h))
    w = sum(g.shape[1] for g in gs) + sp * (len(gs) - 1)
    img = np.zeros((h, w, 4), np.uint8)
    x = 0
    for g in gs:
        y = h - g.shape[0]
        img[y:y + g.shape[0], x:x + g.shape[1]] = g
        x += g.shape[1] + sp
    return img


def stamp(tex, mesh, rect256, text_rgba, fill="height"):
    """Нанести надпись в зону rect256 (из карты номеров 256²) текстуры tex (H×W×3, развёртка mesh): «вверх» — мировой
    +y в касательной плоскости, «вправо» — для смотрящего на ткань; высота надписи — высота зоны (сантиметры по
    якобиану развёртки), шире зоны — сжатие по ширине; надпись — по центру зоны."""
    H, W = tex.shape[:2]
    k = W / 256.0
    x0, y0, x1, y1 = rect256
    c = np.array([(x0 + x1 + 1) / 2.0, (y0 + y1 + 1) / 2.0])
    tid, bar = kit3d.raster_uv(mesh, 256)
    t = tid[int(c[1]), int(c[0])]
    if t < 0:
        return tex
    Jm = uv_jacobian(mesh, t, 256)
    n = kit3d._unit(np.cross(Jm[:, 0], Jm[:, 1]))
    nv = kit3d._unit((bar[int(c[1]), int(c[0])][:, None] * mesh["nrm"][mesh["tri"][t]]).sum(0))
    if (n * nv).sum() < 0:
        n = -n
    up = np.array([0.0, 1.0, 0.0]) - n * n[1]
    up = up / np.linalg.norm(up)
    right = np.cross(up, n)
    corners = np.array([[x0, y0], [x1 + 1, y0], [x0, y1 + 1], [x1 + 1, y1 + 1]], float) - c
    world = corners @ Jm.T
    zw, zh = np.ptp(world @ right), np.ptp(world @ up)
    th, tw = text_rgba.shape[:2]
    sh = zh / th                                       # метров на пиксель надписи по высоте
    sw = min(sh, zw / tw)                              # по ширине — не шире зоны
    out = tex.astype(np.float64).copy()
    ys, xs = np.mgrid[int(y0 * k):int((y1 + 1) * k), int(x0 * k):int((x1 + 1) * k)]
    d = np.stack([(xs + 0.5) / k - c[0], (ys + 0.5) / k - c[1]], -1) @ Jm.T
    X = (d @ right) / sw + tw / 2.0
    Y = th / 2.0 - (d @ up) / sh
    ok = (X >= 0) & (X < tw) & (Y >= 0) & (Y < th)
    g = text_rgba[np.clip(Y.astype(int), 0, th - 1), np.clip(X.astype(int), 0, tw - 1)].astype(np.float64)
    al = (g[..., 3:4] / 255.0) * ok[..., None]
    out[ys, xs] = out[ys, xs] * (1 - al) + g[..., :3] * al
    return out


def cmd_dress(a):
    """Свитер слота с фамилией, номером, буквой и номерами на рукавах — рендер с разных сторон (офлайн)."""
    work = os.path.join(REPO, "game", "work", "nhl24", "adidas3d")
    d = os.path.join(work, f"pack_{a.slot}")
    bm = rw.Mesh.load(os.path.join(a.dst, *skater_rel(0, 1, 2, STYLE_DST).split("/")))
    mesh = {"pos": np.array([p[:3] for p in bm.pos]), "uv": np.array(bm.uv), "tri": np.array(bm.tris),
            "nrm": kit3d._unit(np.array(bm.nrm))}
    tex = np.asarray(Image.open(os.path.join(d, "jersey_cm.png")).convert("RGB")).astype(np.float64)
    nm = np.asarray(Image.open(os.path.join(d, "jersey_nm.png")).convert("RGB")).astype(np.float64)
    zm = np.asarray(Image.open(os.path.join(d, "name_cm.png")).convert("RGBA"))
    rects = {}
    for z in sorted(set(zm[..., 2][zm[..., 2] < 255].tolist())):
        ys, xs = np.nonzero(zm[..., 2] == z)
        rects[z] = (xs.min(), ys.min(), xs.max(), ys.max())
    gl = font_glyphs(os.path.join(d, "font_cm.png"))
    tex = stamp(tex, mesh, rects[0], text_image(gl, None, a.name.upper()))
    big = [gl[(2 if ch in "01234" else 3, ch)] for ch in a.number]
    hb = max(g.shape[0] for g in big)
    num = np.zeros((hb, sum(g.shape[1] for g in big) + int(0.05 * hb) * (len(big) - 1), 4), np.uint8)
    x = 0
    for g in big:
        num[hb - g.shape[0]:, x:x + g.shape[1]] = g
        x += g.shape[1] + int(0.05 * hb)
    tex = stamp(tex, mesh, rects[1], num)
    for z in SLEEVE_ZONES:
        tex = stamp(tex, mesh, rects[z], text_image(gl, a.sleeve_row, a.number, 0.04))
    if a.letter:
        tex = stamp(tex, mesh, rects[5], gl[(4 if a.letter == "C" else 5, a.letter)])
    ims = [kit3d.render_lit(mesh, tex, v, 360, nmap=nm) for v in ("back", "front", "left", "right")]
    W = sum(im.size[0] + 8 for im in ims)
    sheet = Image.new("RGB", (W, ims[0].size[1]), (24, 24, 28))
    x = 0
    for im in ims:
        sheet.paste(im, (x, 0))
        x += im.size[0] + 8
    sheet.save(a.png)
    Image.fromarray(np.clip(tex, 0, 255).astype(np.uint8)).save(os.path.splitext(a.png)[0] + "_tex.png")
    print(a.png)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("map")
    b = sub.add_parser("build")
    b.add_argument("--out", default=OUT)
    p = sub.add_parser("preview")
    p.add_argument("tex")
    p.add_argument("png")
    p.add_argument("--legacy-tex", default=None, help="текстура комплекта Legacy (развёртка Edge) для первой строки")
    p.add_argument("--out", default=OUT)
    k = sub.add_parser("kit")
    k.add_argument("--club", required=True, help="папка клуба NHL 24 (pittsburgh)")
    k.add_argument("--kit", default="home", help="комплект adidas NHL 24 (home, away…)")
    k.add_argument("--legacy", required=True, help="комплект Legacy для шорт, гетр и карты номеров (1_23_0)")
    k.add_argument("--slot", required=True, help="номер слота стиля 0, куда собирать (0_23_0)")
    k.add_argument("--font-dir", required=True, help="папка шрифта NHL 24 из fb.kit_batch (out/kits/PIT_home)")
    k.add_argument("--dst", default=OUT)
    k.add_argument("--squeeze", type=float, default=DECAL_SQUEEZE, help="сжатие нашивок по ширине (1 — как есть)")
    r = sub.add_parser("dress")
    r.add_argument("png")
    r.add_argument("--slot", default="0_23_0")
    r.add_argument("--name", default="CROSBY")
    r.add_argument("--number", default="87")
    r.add_argument("--letter", default="C")
    r.add_argument("--sleeve-row", type=int, default=7, help="строка малых цифр атласа (6 или 7)")
    r.add_argument("--dst", default=OUT)
    a = ap.parse_args()
    {"map": cmd_map, "build": cmd_build, "preview": cmd_preview, "kit": cmd_kit, "dress": cmd_dress}[a.cmd](a)


if __name__ == "__main__":
    main()
