"""Низ свитера NHL 24 → развёртка Legacy «от края низа» (замечание пользователя 18.10.2026).

При переносе по ближайшей точке (fb.kit3d.transfer) полосы низа садятся по мировой высоте, а края низа у сеток
разные: у Edge середина спереди на 1,5 см ниже, чем у NHL 24 (0,956 и 0,971 м), бока на 1 см выше (0,999 и 0,987),
спина ниже на 1,3 см. Полосы срезаются краем и идут волной (MIN дом: светлая полоса уже и неровная). Здесь тексель
Legacy у низа → (угол вокруг тела φ, высота над краем низа d) → точка NHL 24 с теми же φ и d → её UV: полосы идут
вдоль края Legacy во всю высоту. Выше полосы (d от HEM_H − HEM_BLEND до HEM_H) — плавный переход к прежнему переносу.

  python -m fb.hem apply NHL24_COLOR.png LEGACY_JERSEY_CM.png OUT.png    # низ поверх готовой развёртки Legacy
  python -m fb.hem sheet NHL24_COLOR.png BEFORE.png AFTER.png OUT.png    # лист: NHL 24 | до | после (спереди, сзади)
"""
import argparse
import os
import sys

import numpy as np
from PIL import Image

from . import kit3d

HEM_H = 0.09        # м над краем низа — зона переноса «от края»
HEM_BLEND = 0.03    # верхняя часть зоны — переход к переносу по ближайшей точке
D_STEP = 0.0005     # шаг сетки по высоте, м
PHI_STEP = 0.25     # шаг сетки по углу, градусы


def hem_curve(mesh):
    """Край низа — замкнутая граница сетки с самой низкой средней высотой (не манжеты: они тоже низко, у боков)
    → (φ по возрастанию, y), φ — градусы atan2(x, z)."""
    import scipy.sparse as sp
    from scipy.sparse.csgraph import connected_components
    from collections import Counter
    from .jersey_mesh import weld
    g, first = weld(mesh["pos"])
    P = mesh["pos"][first]
    c = Counter()
    for t in g[mesh["tri"]]:
        for e in ((t[0], t[1]), (t[1], t[2]), (t[2], t[0])):
            c[(min(e), max(e))] += 1
    e = np.array([k for k, v in c.items() if v == 1])
    A = sp.coo_matrix((np.ones(len(e)), (e[:, 0], e[:, 1])), shape=(len(P), len(P)))
    _, lab = connected_components(A, directed=False)
    nodes = np.unique(e)
    best = min({lab[v] for v in nodes}, key=lambda k: P[nodes[lab[nodes] == k], 1].mean())
    low = nodes[lab[nodes] == best]
    phi = np.degrees(np.arctan2(P[low, 0], P[low, 2]))
    o = np.argsort(phi)
    return phi[o], P[low, 1][o]


def hem_y(curve, phi):
    """Высота края низа под углом phi (линейно по кругу)."""
    cp, cy = curve
    xp = np.concatenate([cp - 360, cp, cp + 360])
    return np.interp(phi, xp, np.tile(cy, 3))


def hem_coords(P, curve):
    phi = np.degrees(np.arctan2(P[:, 0], P[:, 2]))
    return phi, P[:, 1] - hem_y(curve, phi)


def polar_grid(tri, phi, d, uv, h):
    """Сетка (φ, d) → UV (или любой признак вершин, например позиция) по треугольникам tri (φ, d, uv — в вершинах; у
    каждого треугольника свои UV, швы развёртки не смешиваются). -> (uv[nφ, nd, k], заполнено[nφ, nd])."""
    nphi, nd = int(round(360 / PHI_STEP)), int(np.ceil(h / D_STEP)) + 1
    out = np.zeros((nphi, nd, uv.shape[1]))
    ok = np.zeros((nphi, nd), bool)
    for t in tri:
        dt = d[t]
        if dt.min() > h or dt.max() < -0.01:
            continue
        pt = phi[t].copy()
        if pt.max() - pt.min() > 180:                  # через φ = ±180
            pt[pt < 0] += 360
        x = (pt + 180) / PHI_STEP
        y = dt / D_STEP
        x0, x1 = int(np.floor(x.min())), int(np.ceil(x.max()))
        y0, y1 = max(int(np.floor(y.min())), 0), min(int(np.ceil(y.max())), nd - 1)
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
        t_uv = uv[t]
        val = l0[m, None] * t_uv[0] + l1[m, None] * t_uv[1] + l2[m, None] * t_uv[2]
        ix = xs[m] % nphi
        out[ix, ys[m]] = val
        ok[ix, ys[m]] = True
    return out, ok


def hem_grid(src, h=HEM_H + 0.01):
    """Сетка (φ, d) → UV src по треугольникам src у низа. -> (uv[nφ, nd, 2], заполнено[nφ, nd])."""
    phi, d = hem_coords(src["pos"], hem_curve(src))
    return polar_grid(src["tri"], phi, d, src["uv"], h)


def lookup(grid, phi, d, reach=8):
    """UV src в точках (φ, d) — ближайший узел сетки (шаг 0,25° × 0,5 мм); пустой узел — ближайший заполненный по d
    в пределах reach шагов (у самого края треугольники покрывают сетку не до 0). -> (uv, найдено)."""
    uv, ok = grid
    nphi, nd = ok.shape
    ix = np.round((phi + 180) / PHI_STEP).astype(np.int64) % nphi
    iy = np.clip(np.round(d / D_STEP).astype(np.int64), 0, nd - 1)
    found = ok[ix, iy].copy()
    jy = iy.copy()
    for k in range(1, reach + 1):
        for sgn in (1, -1):
            miss = ~found
            if not miss.any():
                break
            cand = np.clip(iy + sgn * k, 0, nd - 1)
            hit = miss & ok[ix, cand]
            jy[hit] = cand[hit]
            found |= hit
    return uv[ix, jy], found & (d >= -0.005)


def hem_layer(src_tex, src_mesh, dst_mesh, size=1024, ss=2):
    """Низ src_tex по краю низа dst_mesh: -> (цвет × вес size², вес 0..1 — 1 у края, 0 выше HEM_H)."""
    S = size * ss
    tid, bar = kit3d.raster_uv(dst_mesh, S)
    mask = tid >= 0
    t, b = tid[mask], bar[mask]
    T = dst_mesh["tri"][t]
    P = (b[:, :, None] * dst_mesh["pos"][T]).sum(1)
    phi, d = hem_coords(P, hem_curve(dst_mesh))
    near = d < HEM_H
    uv, found = lookup(hem_grid(src_mesh), phi[near], d[near])
    col = np.zeros((len(P), src_tex.shape[2]))
    w = np.zeros(len(P))
    col[np.nonzero(near)[0][found]] = kit3d.sample_bilinear(src_tex, uv[found, 0], uv[found, 1])
    s = np.clip((HEM_H - d) / HEM_BLEND, 0, 1)
    w[np.nonzero(near)[0][found]] = (s * s * (3 - 2 * s))[near][found]
    img = np.zeros((S, S, src_tex.shape[2]))      # цвет × вес (предумноженный)
    wt = np.zeros((S, S))
    img[mask], wt[mask] = col * w[:, None], w
    if ss > 1:
        img = img.reshape(size, ss, size, ss, -1).mean((1, 3))
        wt = wt.reshape(size, ss, size, ss).mean((1, 3))
    return img, wt


def apply(src_tex, src_mesh, dst_mesh, dst_tex):
    """Развёртка Legacy dst_tex (size², RGB/RGBA) с низом «от края». -> новая картинка (uint8)."""
    size = dst_tex.shape[0]
    rgb = dst_tex[..., :3].astype(np.float64)
    layer, w = hem_layer(src_tex[..., :3].astype(np.float64), src_mesh, dst_mesh, size)
    out = rgb * (1 - w[..., None]) + layer           # layer — предумноженный на вес
    res = dst_tex.copy()
    res[..., :3] = np.clip(out, 0, 255).astype(np.uint8)
    return res


def main():
    from .jersey_mesh import N24, legacy, skater_rel
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("apply")
    p.add_argument("src")
    p.add_argument("dst")
    p.add_argument("out")
    p = sub.add_parser("sheet")
    p.add_argument("src")
    p.add_argument("before")
    p.add_argument("after")
    p.add_argument("out")
    a = ap.parse_args()
    n24 = kit3d.load_nhl24(N24.format(tuck="notuck", size="large", lod=0))
    _, edge = legacy(skater_rel(0, 1, 2, 1))
    src = np.asarray(Image.open(a.src).convert("RGB"))
    if a.cmd == "apply":
        dst = np.asarray(Image.open(a.dst).convert("RGBA"))
        Image.fromarray(apply(src, n24, edge, dst)).save(a.out)
        print(a.out)
        return
    fr = (-0.36, 0.36, 0.90, 1.22)
    t24 = src.astype(np.float64)
    tb = np.asarray(Image.open(a.before).convert("RGB")).astype(np.float64)
    ta = np.asarray(Image.open(a.after).convert("RGB")).astype(np.float64)
    rows = [[kit3d.render_lit(m, t, v, 360, frame=fr) for m, t in ((n24, t24), (edge, tb), (edge, ta))]
            for v in ("front", "back")]
    w, h = rows[0][0].size
    sh = Image.new("RGB", (3 * (w + 4), 2 * (h + 4)), (20, 20, 24))
    for j, row in enumerate(rows):
        for i, im in enumerate(row):
            sh.paste(im, (i * (w + 4), j * (h + 4)))
    sh.save(a.out)
    print(a.out)


if __name__ == "__main__":
    sys.exit(main())


def lookup_lin(grid, phi, d):
    """Как lookup, но двулинейно между соседними клетками (если все четыре заполнены, иначе — ближайшая): у сетки
    позиций ближайшая клетка склеивала вершины ближе шага (0,25° × 0,5 мм) в одну точку."""
    val, ok = grid
    nphi, nd = ok.shape
    x = (phi + 180) / PHI_STEP
    y = np.clip(d / D_STEP, 0, nd - 1.001)
    x0 = np.floor(x).astype(np.int64)
    y0 = np.floor(y).astype(np.int64)
    fx, fy = (x - x0)[:, None], (y - y0)[:, None]
    i0, i1 = x0 % nphi, (x0 + 1) % nphi
    j0, j1 = y0, np.minimum(y0 + 1, nd - 1)
    all4 = ok[i0, j0] & ok[i1, j0] & ok[i0, j1] & ok[i1, j1]
    out = (val[i0, j0] * (1 - fx) * (1 - fy) + val[i1, j0] * fx * (1 - fy) + val[i0, j1] * (1 - fx) * fy
           + val[i1, j1] * fx * fy)
    near, okn = lookup(grid, phi, d)
    out = np.where(all4[:, None], out, near)
    return out, (all4 | okn) & (d >= -0.005)
