"""Свитер NHL 24 → развёртка NHL Legacy через 3D и офлайн-рендер свитеров (только для сравнения, в игру не ставится).

Обе сетки — в метрах, Y вверх, +Z вперёд, одна поза (руки опущены): свитер NHL 24
(content/character/skater/player/jersey/adidas/components/player_jersey_adidas_notuck_large_lod0_mesh, 3160 вершин)
и свитер Legacy стиля 1 (rendering/jersey/jersey_0_1_2_0_1_2.rx2 — полевой, без заправки, с наплечниками, ближняя
детализация, 2055 вершин; читает tools/rw4mesh.py). Совпадают до 1–3 см, поэтому перенос — «по ближайшей точке»:
тексель Legacy → точка его поверхности (барицентры в UV) → ближайшая точка свитера NHL 24 с той же стороной нормали →
её UV → цвет текстуры NHL 24.

  python -m fb.kit3d transfer NHL24_TEX.png OUT.png [--size 1024] [--ss 2]
  python -m fb.kit3d render (nhl24|legacy) TEX.png OUT_PREFIX     # спереди и сзади: OUT_PREFIX_front/back.png
"""
import argparse
import glob
import json
import os
import sys

import numpy as np
from PIL import Image
from scipy.spatial import cKDTree

from . import cas, meshset
from .cas import REPO

TOOLS = os.path.join(REPO, "tools")
NHL24_JERSEY = "content/character/skater/player/jersey/adidas/components/player_jersey_adidas_notuck_large_lod0_mesh"
LEGACY_JERSEY = "rendering/jersey/jersey_0_1_2_0_1_2.rx2"


def find_res(name):
    key = f'"name": "{name}"'
    from .source import CATALOG
    for p in sorted(glob.glob(os.path.join(CATALOG, "scan", "*.jsonl"))):
        with open(p, encoding="utf-8") as f:
            for line in f:
                if key in line and '"k": "res"' in line and '"ofs"' in line:
                    return json.loads(line)
    raise SystemExit(f"нет res {name}")


def load_nhl24(name=NHL24_JERSEY):
    from .extract import cas_file
    from .extract import chunks
    import struct as _st
    r = find_res(name)
    d, _ = cas.read_entry(cas_file(r["cas"]), r["ofs"], r["size"])
    meta = bytes.fromhex(r["meta"])
    cd = None
    if _st.unpack_from("<I", meta, 4)[0] == 0:  # геометрия — в чанке
        c = chunks().get(meshset.lod_chunk(d))
        if not c or c.get("missing"):
            raise SystemExit(f"{name}: чанк геометрии не найден")
        cd, _ = cas.read_entry(cas_file(c["cas"]), c["ofs"], (c["lo"] or 0) + c["ls"])
    s = meshset.parse(d, meta, cd)[0]
    pos = s["pos"].astype(np.float64)
    if s["nrm"] is not None:
        nrm = s["nrm"][:, :3].astype(np.float64)
    else:  # у части сеток (гетры) нормалей в вершинах нет — по треугольникам
        T = s["tri"]
        fn = np.cross(pos[T[:, 1]] - pos[T[:, 0]], pos[T[:, 2]] - pos[T[:, 0]])
        nrm = np.zeros_like(pos)
        for k in range(3):
            np.add.at(nrm, T[:, k], fn)
        nrm = _unit(nrm)
    out = {"pos": pos, "uv": s["uv"][:, :2].astype(np.float64), "tri": s["tri"], "nrm": nrm}
    if s.get("tan") is not None:  # касательная NHL 24 (для сборки сеток Legacy из NHL 24 — fb.jersey_mesh)
        out["tan24"] = s["tan"][:, :3].astype(np.float64)
    return out


def load_legacy(rel=LEGACY_JERSEY):
    sys.path.insert(0, TOOLS)
    import rw4mesh
    rw4mesh.use_game("legacy")
    m = rw4mesh.Mesh.game(rel)
    return {"pos": np.array([p[:3] for p in m.pos], dtype=np.float64), "uv": np.array(m.uv, dtype=np.float64),
            "tri": np.array(m.tris, dtype=np.int64), "nrm": np.array([n[:3] for n in m.nrm], dtype=np.float64)}


def _unit(v):
    n = np.linalg.norm(v, axis=-1, keepdims=True)
    return v / np.maximum(n, 1e-12)


# ---------------------------------------------------------------- растеризация в UV

def _wh(size):
    return (size, size) if np.isscalar(size) else (int(size[0]), int(size[1]))


def raster_uv(mesh, size):
    """size — сторона или (ширина, высота). -> (tri_id[h,w] (-1 — пусто), bary[h,w,3]) по центрам текселей."""
    W, H = _wh(size)
    uv = mesh["uv"] * np.array([W, H]) - 0.5
    tid = np.full((H, W), -1, dtype=np.int64)
    bar = np.zeros((H, W, 3), dtype=np.float64)
    for t, (a, b, c) in enumerate(mesh["tri"]):
        pa, pb, pc = uv[a], uv[b], uv[c]
        x0 = max(int(np.floor(min(pa[0], pb[0], pc[0]))), 0)
        x1 = min(int(np.ceil(max(pa[0], pb[0], pc[0]))), W - 1)
        y0 = max(int(np.floor(min(pa[1], pb[1], pc[1]))), 0)
        y1 = min(int(np.ceil(max(pa[1], pb[1], pc[1]))), H - 1)
        if x1 < x0 or y1 < y0:
            continue
        den = (pb[1] - pc[1]) * (pa[0] - pc[0]) + (pc[0] - pb[0]) * (pa[1] - pc[1])
        if abs(den) < 1e-12:
            continue
        xs, ys = np.meshgrid(np.arange(x0, x1 + 1), np.arange(y0, y1 + 1))
        l0 = ((pb[1] - pc[1]) * (xs - pc[0]) + (pc[0] - pb[0]) * (ys - pc[1])) / den
        l1 = ((pc[1] - pa[1]) * (xs - pc[0]) + (pa[0] - pc[0]) * (ys - pc[1])) / den
        l2 = 1 - l0 - l1
        m = (l0 >= -1e-6) & (l1 >= -1e-6) & (l2 >= -1e-6)
        if not m.any():
            continue
        tid[ys[m], xs[m]] = t
        bar[ys[m], xs[m]] = np.stack([l0[m], l1[m], l2[m]], -1)
    return tid, bar


# ---------------------------------------------------------------- ближайшая точка на сетке

def closest_point_tri(p, a, b, c):
    """Ближайшая точка треугольников (a,b,c) к точкам p (всё (N,3)); -> барицентры (N,3). Эриксон, RTCD 5.1.5."""
    ab, ac, ap = b - a, c - a, p - a
    d1, d2 = (ab * ap).sum(-1), (ac * ap).sum(-1)
    bp = p - b
    d3, d4 = (ab * bp).sum(-1), (ac * bp).sum(-1)
    cp = p - c
    d5, d6 = (ab * cp).sum(-1), (ac * cp).sum(-1)
    va = d3 * d6 - d5 * d4
    vb = d5 * d2 - d1 * d6
    vc = d1 * d4 - d3 * d2
    den = va + vb + vc
    den = np.where(np.abs(den) < 1e-18, 1e-18, den)
    out = np.stack([1 - vb / den - vc / den, vb / den, vc / den], -1)
    with np.errstate(divide="ignore", invalid="ignore"):
        m = (va <= 0) & ((d4 - d3) >= 0) & ((d5 - d6) >= 0)                     # ребро BC
        ww = (d4 - d3) / ((d4 - d3) + (d5 - d6))
        out[m] = np.stack([np.zeros(m.sum()), 1 - ww[m], ww[m]], -1)
        m = (vb <= 0) & (d2 >= 0) & (d6 <= 0)                                    # ребро AC
        ww = d2 / (d2 - d6)
        out[m] = np.stack([1 - ww[m], np.zeros(m.sum()), ww[m]], -1)
        m = (d6 >= 0) & (d5 <= d6)                                               # вершина C
        out[m] = [0, 0, 1]
        m = (vc <= 0) & (d1 >= 0) & (d3 <= 0)                                    # ребро AB
        vv = d1 / (d1 - d3)
        out[m] = np.stack([1 - vv[m], vv[m], np.zeros(m.sum())], -1)
        m = (d3 >= 0) & (d4 <= d3)                                               # вершина B
        out[m] = [0, 1, 0]
        m = (d1 <= 0) & (d2 <= 0)                                                # вершина A
        out[m] = [1, 0, 0]
    return np.nan_to_num(out, nan=1 / 3)


def project(points, normals, mesh, k=24, chunk=40000, min_dot=0.0):
    """Ближайшая точка сетки mesh к points с нормалью той же стороны. -> (tri, bary, dist)."""
    P, T, N = mesh["pos"], mesh["tri"], mesh["nrm"]
    tree = cKDTree(P[T].mean(1))
    out_t = np.empty(len(points), dtype=np.int64)
    out_b = np.empty((len(points), 3))
    out_d = np.empty(len(points))
    for s in range(0, len(points), chunk):
        p = points[s:s + chunk]
        n = normals[s:s + chunk]
        _, cand = tree.query(p, k=k)
        q = np.repeat(p, k, axis=0)
        tc = cand.reshape(-1)
        a, b, c = P[T[tc, 0]], P[T[tc, 1]], P[T[tc, 2]]
        bar = closest_point_tri(q, a, b, c)
        x = bar[:, :1] * a + bar[:, 1:2] * b + bar[:, 2:] * c
        d = np.linalg.norm(x - q, axis=-1)
        nn = _unit(bar[:, :1] * N[T[tc, 0]] + bar[:, 1:2] * N[T[tc, 1]] + bar[:, 2:] * N[T[tc, 2]])
        dot = (nn * np.repeat(n, k, axis=0)).sum(-1)
        pen = (d + np.where(dot >= min_dot, 0.0, 1.0)).reshape(-1, k)  # другая сторона ткани — штраф 1 м
        idx = np.arange(len(p)) * k + pen.argmin(1)
        out_t[s:s + chunk] = tc[idx]
        out_b[s:s + chunk] = bar[idx]
        out_d[s:s + chunk] = d[idx]
    return out_t, out_b, out_d


def sample_bilinear(tex, u, v):
    """tex (H,W,C) float; u,v в [0,1] (v вниз), край — повтор."""
    h, w = tex.shape[:2]
    x = np.clip(u * w - 0.5, 0, w - 1)
    y = np.clip(v * h - 0.5, 0, h - 1)
    x0 = np.floor(x).astype(np.int64)
    y0 = np.floor(y).astype(np.int64)
    x1 = np.minimum(x0 + 1, w - 1)
    y1 = np.minimum(y0 + 1, h - 1)
    fx = (x - x0)[:, None]
    fy = (y - y0)[:, None]
    return (tex[y0, x0] * (1 - fx) * (1 - fy) + tex[y0, x1] * fx * (1 - fy) +
            tex[y1, x0] * (1 - fx) * fy + tex[y1, x1] * fx * fy)


def fill_holes(img, mask, iters=96):
    """Растекание цвета за края островов UV (для мипов и фильтрации). img (H,W,C) float, mask (H,W) bool."""
    m = mask.astype(np.float64)
    acc = img * m[..., None]
    H, W = m.shape
    for _ in range(iters):
        if m.all():
            break
        pa = np.pad(acc, ((1, 1), (1, 1), (0, 0)))
        pm = np.pad(m, 1)
        s = sum(pa[1 + dy:H + 1 + dy, 1 + dx:W + 1 + dx] * pm[1 + dy:H + 1 + dy, 1 + dx:W + 1 + dx, None]
                for dy in (-1, 0, 1) for dx in (-1, 0, 1))
        c = sum(pm[1 + dy:H + 1 + dy, 1 + dx:W + 1 + dx] for dy in (-1, 0, 1) for dx in (-1, 0, 1))
        new = (m == 0) & (c > 0)
        acc[new] = s[new] / c[new][:, None]
        m = np.where(new, 1.0, m)
    return acc


def push_pull(img, mask):
    """Заполнить всё вне mask (пирамида «вниз-вверх») — чтобы мипы не тянули чёрный."""
    if mask.all():
        return img
    h, w = mask.shape
    if h <= 1 or w <= 1:
        val = img[mask].mean(0) if mask.any() else np.zeros(img.shape[-1])
        out = img.copy()
        out[~mask] = val
        return out
    m = mask.astype(np.float64)
    hh, ww = (h + 1) // 2, (w + 1) // 2
    pi = np.zeros((hh * 2, ww * 2, img.shape[-1]))
    pm = np.zeros((hh * 2, ww * 2))
    pi[:h, :w] = img * m[..., None]
    pm[:h, :w] = m
    si = pi.reshape(hh, 2, ww, 2, -1).sum((1, 3))
    sm = pm.reshape(hh, 2, ww, 2).sum((1, 3))
    low = np.where(sm[..., None] > 0, si / np.maximum(sm, 1)[..., None], 0)
    low = push_pull(low, sm > 0)
    up = np.repeat(np.repeat(low, 2, 0), 2, 1)[:h, :w]
    return np.where(mask[..., None], img, up)


_MAPCACHE = {}


def transfer(src_tex, src_mesh, dst_mesh, size=1024, ss=2, seam=0.04, post=None):
    """Текстура src (по UV src_mesh) → развёртка dst_mesh, size², суперсэмплинг ss×ss.

    Соответствие считается в вершинах dst (ближайшая точка src той же стороны) и интерполируется по треугольникам dst
    (кусочно-линейно, без «дрожания» краёв полос). Треугольник, вершины которого попали в разные острова UV src
    (разброс UV > seam), считается по текселям.
    """
    W, H = _wh(size)
    S = (W * ss, H * ss)
    T = dst_mesh["tri"]

    def interp(attr, tri, bb):
        return bb[:, :1] * attr[tri[:, 0]] + bb[:, 1:2] * attr[tri[:, 1]] + bb[:, 2:] * attr[tri[:, 2]]

    key = (id(src_mesh), id(dst_mesh), (W, H), ss, seam)
    cached = _MAPCACHE.get(key)
    if cached is None:  # соответствие зависит только от сеток — считаем один раз на все комплекты
        tid, bar = raster_uv(dst_mesh, S)
        mask = tid >= 0
        t, b = tid[mask], bar[mask]
        vt, vb, vd = project(dst_mesh["pos"], _unit(dst_mesh["nrm"]), src_mesh)
        vuv = interp(src_mesh["uv"], src_mesh["tri"][vt], vb)
        tri_uv = vuv[T]
        spread = np.max(np.linalg.norm(tri_uv[:, :, None, :] - tri_uv[:, None, :, :], axis=-1), axis=(1, 2))
        bad_tri = spread > seam
        UV = interp(vuv, T[t], b)
        dist_v = interp(vd[:, None], T[t], b)[:, 0]
        fb = bad_tri[t]
        if fb.any():
            Pf = interp(dst_mesh["pos"], T[t[fb]], b[fb])
            Nf = _unit(interp(dst_mesh["nrm"], T[t[fb]], b[fb]))
            st, sb, sd = project(Pf, Nf, src_mesh)
            UV[fb] = interp(src_mesh["uv"], src_mesh["tri"][st], sb)
            dist_v[fb] = sd
        cached = (mask, t, b, UV, dist_v, bad_tri)
        _MAPCACHE[key] = cached
    mask, t, b, UV, dist_v, bad_tri = cached
    col = sample_bilinear(src_tex, UV[:, 0], UV[:, 1])
    img = np.zeros((S[1], S[0], src_tex.shape[2]))
    img[mask] = col
    dist = np.full((S[1], S[0]), np.nan)
    dist[mask] = dist_v
    if post is not None:  # слои поверх основы, на сверхвыборке: post(img, mask, P, N, tri, uv_src) по текселям mask
        Pm = interp(dst_mesh["pos"], T[t], b)
        Nm = _unit(interp(dst_mesh["nrm"], T[t], b))
        img = post(img, mask, Pm, Nm, t, UV)
    if ss > 1:
        mk = mask.reshape(H, ss, W, ss).astype(np.float64)
        num = (img.reshape(H, ss, W, ss, -1) * mk[..., None]).sum((1, 3))
        cnt = mk.sum((1, 3))
        img = np.where(cnt[..., None] > 0, num / np.maximum(cnt, 1)[..., None], 0)
        mask = cnt > 0
        with np.errstate(all="ignore"):
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                dist = np.nanmax(dist.reshape(H, ss, W, ss), axis=(1, 3))
    info = {"seam_tris": int(bad_tri.sum()), "tris": int(len(T))}
    return push_pull(fill_holes(img, mask, 8), mask), mask, dist, info


# ---------------------------------------------------------------- офлайн-рендер

FRAME = (-0.62, 0.62, 0.86, 1.80)  # x0, x1, y0, y1 (м) — общий кадр для обеих сеток
LIGHT = _unit(np.array([-0.35, 0.45, 1.0]))  # основной свет от камеры: слева сверху
FILL = _unit(np.array([0.8, 0.1, 0.6]))       # заполняющий справа
NECK = (-0.21, 0.21, 1.42, 1.76)              # кадр «горловина крупно»


def render(mesh, tex, view="front", width=520, bg=(46, 46, 52), frame=FRAME, ss=1):
    """Плоский рендер (свет от камеры + заполняющий), растеризация вида кешируется (_view_raster)."""
    if ss > 1:
        big = render(mesh, tex, view, width * ss, bg, frame, 1)
        return big.resize((width, big.size[1] // ss), Image.LANCZOS)
    x0, x1, y0, y1 = frame
    height = int(round(width * (y1 - y0) / (x1 - x0)))
    out = np.zeros((height, width, 3))
    out[:] = bg
    tid, bw = _view_raster(mesh, view, width, height, frame)
    py, px = np.nonzero(tid >= 0)
    if len(py) == 0:
        return Image.fromarray(out.astype(np.uint8))
    N = _rot(mesh["nrm"], view)
    UV = mesh["uv"]
    tr = mesh["tri"][tid[py, px]]
    a, b, c = tr[:, 0], tr[:, 1], tr[:, 2]
    w0, w1, w2 = bw[py, px, 0], bw[py, px, 1], bw[py, px, 2]
    u = w0 * UV[a, 0] + w1 * UV[b, 0] + w2 * UV[c, 0]
    v = w0 * UV[a, 1] + w1 * UV[b, 1] + w2 * UV[c, 1]
    col = sample_bilinear(tex, u, v)[:, :3]
    n = _unit(w0[:, None] * N[a] + w1[:, None] * N[b] + w2[:, None] * N[c])
    lam = np.clip((n * LIGHT).sum(-1), 0, 1)
    fill = np.clip((n * FILL).sum(-1), 0, 1)
    rim = np.clip(1 - np.abs(n[:, 2]), 0, 1) ** 3
    inner = n[:, 2] < -0.05  # изнанка (видна в горловине)
    shade = np.where(inner, 0.32, 0.30 + 0.70 * lam + 0.22 * fill + 0.10 * rim)
    out[py, px] = col * shade[:, None]
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8))


def cmd_sheet(a):
    from PIL import ImageDraw, ImageFont
    try:
        font = ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", 30)
    except OSError:
        font = ImageFont.load_default()
    meshes = {}
    tiles = []
    H = a.height
    W = int(round(H * (FRAME[1] - FRAME[0]) / (FRAME[3] - FRAME[2])))
    WN = int(round(H * (NECK[1] - NECK[0]) / (NECK[3] - NECK[2])))
    for spec in a.rows:
        kind, tex, label = spec.split(":", 2) if spec.count(":") >= 2 else (spec.split(":")[0], spec.split(":")[1], "")
        if len(kind) == 1:  # буква диска Windows в пути — склеим обратно
            raise SystemExit("формат: nhl24|legacy|legacyv:путь:подпись")
        if kind not in meshes:
            if kind == "legacyv":  # свитер Legacy + «рубашка» V-выреза (видна V-вставка)
                from .kit_hybrid import legacy_with_shirt
                meshes[kind] = legacy_with_shirt()[0]
            else:
                meshes[kind] = load_nhl24() if kind == "nhl24" else load_legacy()
        t = load_tex(tex)
        row = [render(meshes[kind], t, "front", W, frame=FRAME, ss=2),
               render(meshes[kind], t, "back", W, frame=FRAME, ss=2),
               render(meshes[kind], t, "front", WN, frame=NECK, ss=2)]
        tiles.append((label, row))
    pad, top = 16, 52
    sw = W * 2 + WN + pad * 4
    shh = len(tiles) * (H + top) + pad
    sheet = Image.new("RGB", (sw, shh), (30, 30, 34))
    d = ImageDraw.Draw(sheet)
    for i, (label, row) in enumerate(tiles):
        y = pad + i * (H + top)
        d.text((pad, y), label, fill=(235, 235, 235), font=font)
        x = pad
        for im in row:
            sheet.paste(im, (x, y + top - 8))
            x += im.size[0] + pad
    sheet.save(a.out)
    print(a.out, sheet.size)


def load_tex(path, size=None):
    im = Image.open(path).convert("RGBA")
    if size and im.size != (size, size):
        im = im.resize((size, size), Image.LANCZOS)
    return np.asarray(im).astype(np.float64)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("transfer")
    t.add_argument("src")
    t.add_argument("out")
    t.add_argument("--size", type=int, default=1024)
    t.add_argument("--ss", type=int, default=2)
    r = sub.add_parser("render")
    r.add_argument("mesh", choices=["nhl24", "legacy"])
    r.add_argument("tex")
    r.add_argument("out")
    sh = sub.add_parser("sheet", help="лист: строки — варианты (сетка:текстура:подпись), столбцы — спереди/сзади/горловина")
    sh.add_argument("out")
    sh.add_argument("rows", nargs="+", help="nhl24|legacy:TEX.png:Подпись")
    sh.add_argument("--height", type=int, default=860)
    a = ap.parse_args()
    if a.cmd == "sheet":
        return cmd_sheet(a)
    if a.cmd == "transfer":
        src, dst = load_nhl24(), load_legacy()
        img, mask, dist, info = transfer(load_tex(a.src), src, dst, a.size, a.ss)
        Image.fromarray(np.clip(img, 0, 255).astype(np.uint8)).save(a.out)
        d = dist[mask]
        print(f"покрыто {mask.mean():.1%} текселей; расстояние до свитера NHL 24: медиана {np.nanmedian(d) * 100:.1f} см, "
              f"95% {np.nanpercentile(d, 95) * 100:.1f} см, макс {np.nanmax(d) * 100:.1f} см; "
              f"треугольников на швах UV: {info['seam_tris']} из {info['tris']}")
        np.save(os.path.splitext(a.out)[0] + "_dist.npy", dist.astype(np.float32))
    else:
        mesh = load_nhl24() if a.mesh == "nhl24" else load_legacy()
        tex = load_tex(a.tex)
        for v in ("front", "back"):
            render(mesh, tex, v).save(f"{a.out}_{v}.png")




# ---------------------------------------------------------------- рендер с рельефом (карта нормалей + блик)

def vertex_tangents(mesh):
    """Касательная (вдоль +u) и бинормаль (вдоль +v) в вершинах — по производным позиций по UV (как у DirectX)."""
    P, UV, T = mesh["pos"], mesh["uv"], mesh["tri"]
    p0, p1, p2 = P[T[:, 0]], P[T[:, 1]], P[T[:, 2]]
    w0, w1, w2 = UV[T[:, 0]], UV[T[:, 1]], UV[T[:, 2]]
    e1, e2 = p1 - p0, p2 - p0
    d1, d2 = w1 - w0, w2 - w0
    den = d1[:, 0] * d2[:, 1] - d2[:, 0] * d1[:, 1]
    r = np.where(np.abs(den) < 1e-12, 0.0, 1.0 / np.where(np.abs(den) < 1e-12, 1.0, den))[:, None]
    t = (e1 * d2[:, 1:2] - e2 * d1[:, 1:2]) * r
    b = (e2 * d1[:, 0:1] - e1 * d2[:, 0:1]) * r
    tv = np.zeros_like(P)
    bv = np.zeros_like(P)
    for k in range(3):
        np.add.at(tv, T[:, k], t)
        np.add.at(bv, T[:, k], b)
    n = _unit(mesh["nrm"])
    tv = _unit(tv - n * (n * tv).sum(-1, keepdims=True))
    bv = _unit(bv - n * (n * bv).sum(-1, keepdims=True))
    return tv, bv


VIEWS = {  # поворот вокруг Y: (cos, sin) — камера смотрит вдоль −Z
    "front": (1.0, 0.0), "back": (-1.0, 0.0), "left": (0.0, 1.0), "right": (0.0, -1.0)}


def _rot(v, view):
    c, s = VIEWS[view]
    out = v.copy()
    out[..., 0] = c * v[..., 0] + s * v[..., 2]
    out[..., 2] = -s * v[..., 0] + c * v[..., 2]
    return out


def render_lit(mesh, tex, view="front", width=600, frame=FRAME, nmap=None, smap=None,
               light=(-1.0, 0.25, 0.35), ambient=0.22, diffuse=0.95, spec=1.0, power=24.0, ss=2, bg=(40, 40, 46),
               flip_green=True):
    """Рендер с картой нормалей (касательное пространство, X = R, Y = G) и бликом (smap — серый, 0..255).
    nmap=None — плоско (нормаль сетки). Свет и камера — в координатах вида (камера вдоль −Z)."""
    if ss > 1:
        big = render_lit(mesh, tex, view, width * ss, frame, nmap, smap, light, ambient, diffuse, spec, power, 1, bg,
                         flip_green)
        return big.resize((width, big.size[1] // ss), Image.LANCZOS)
    x0, x1, y0, y1 = frame
    height = int(round(width * (y1 - y0) / (x1 - x0)))
    N = _rot(_unit(mesh["nrm"]), view)
    if "_tan" not in mesh:
        mesh["_tan"], mesh["_bit"] = vertex_tangents(mesh)
    TG = _rot(mesh["_tan"], view)
    BT = _rot(mesh["_bit"], view)
    L = _unit(np.array(light, dtype=np.float64))
    V = np.array([0.0, 0.0, 1.0])
    Hh = _unit(L + V)
    out = np.zeros((height, width, 3))
    out[:] = bg
    UV = mesh["uv"]
    tid, bw = _view_raster(mesh, view, width, height, frame)
    py, px = np.nonzero(tid >= 0)
    if len(py) == 0:
        return Image.fromarray(out.astype(np.uint8))
    tr = mesh["tri"][tid[py, px]]
    a, b, c = tr[:, 0], tr[:, 1], tr[:, 2]
    w0, w1, w2 = bw[py, px, 0:1], bw[py, px, 1:2], bw[py, px, 2:3]
    u = (w0 * UV[a, 0:1] + w1 * UV[b, 0:1] + w2 * UV[c, 0:1])[:, 0]
    v = (w0 * UV[a, 1:2] + w1 * UV[b, 1:2] + w2 * UV[c, 1:2])[:, 0]
    col = sample_bilinear(tex, u, v)[:, :3]
    n = _unit(w0 * N[a] + w1 * N[b] + w2 * N[c])
    inner = n[:, 2] < -0.05
    if nmap is not None:
        t = _unit(w0 * TG[a] + w1 * TG[b] + w2 * TG[c])
        bb = _unit(w0 * BT[a] + w1 * BT[b] + w2 * BT[c])
        nt = sample_bilinear(nmap, u, v)[:, :3] / 127.5 - 1.0
        gy = -nt[:, 1:2] if flip_green else nt[:, 1:2]  # DirectX: зелёный — «вверх» в текстуре = к −v
        nw = _unit(t * nt[:, 0:1] + bb * gy + n * np.clip(nt[:, 2:3], 0.05, 1))
        n = np.where(inner[:, None], n, nw)
    lam = np.clip((n * L).sum(-1), 0, 1)
    sp = np.clip((n * Hh).sum(-1), 0, 1) ** power
    sk = (sample_bilinear(smap, u, v)[:, 0] / 255.0) if smap is not None else np.full(len(u), 0.12)
    shade = np.where(inner, 0.3, ambient + diffuse * lam)
    out[py, px] = col * shade[:, None] + (spec * sk * sp * 255.0)[:, None] * (~inner)[:, None]
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8))


_VRCACHE = {}


def _view_raster(mesh, view, width, height, frame):
    """Растеризация вида (z-буфер): треугольник и барицентры на пиксель; кешируется — от текстур не зависит."""
    # ключ — и по содержимому позиций: id() временного словаря (повороты в скриптах) переиспользуется после сборки
    # мусора, и кеш отдавал растр другого вида
    pos = mesh["pos"]
    key = (id(mesh), len(mesh["tri"]), view, width, height, tuple(frame), len(pos), float(pos[:, 0].sum()),
           float(pos[:, 1].sum()), float(pos[:, 2].sum()), float((pos[:, 0] * pos[:, 2]).sum()))
    if key in _VRCACHE:
        return _VRCACHE[key]
    x0, x1, y0, y1 = frame
    P = _rot(mesh["pos"], view)
    sx = (P[:, 0] - x0) / (x1 - x0) * width
    sy = (y1 - P[:, 1]) / (y1 - y0) * height
    z = P[:, 2]
    zbuf = np.full((height, width), -np.inf)
    tid = np.full((height, width), -1, dtype=np.int64)
    bw = np.zeros((height, width, 3))
    for ti, (a, b, c) in enumerate(mesh["tri"]):
        xa, xb, xc = sx[a], sx[b], sx[c]
        ya, yb, yc = sy[a], sy[b], sy[c]
        ix0 = max(int(np.floor(min(xa, xb, xc))), 0)
        ix1 = min(int(np.ceil(max(xa, xb, xc))), width - 1)
        iy0 = max(int(np.floor(min(ya, yb, yc))), 0)
        iy1 = min(int(np.ceil(max(ya, yb, yc))), height - 1)
        if ix1 < ix0 or iy1 < iy0:
            continue
        den = (yb - yc) * (xa - xc) + (xc - xb) * (ya - yc)
        if abs(den) < 1e-12:
            continue
        xs, ys = np.meshgrid(np.arange(ix0, ix1 + 1) + 0.5, np.arange(iy0, iy1 + 1) + 0.5)
        l0 = ((yb - yc) * (xs - xc) + (xc - xb) * (ys - yc)) / den
        l1 = ((yc - ya) * (xs - xc) + (xa - xc) * (ys - yc)) / den
        l2 = 1 - l0 - l1
        m = (l0 >= 0) & (l1 >= 0) & (l2 >= 0)
        if not m.any():
            continue
        zz = (l0 * z[a] + l1 * z[b] + l2 * z[c])[m]
        py = (ys[m] - 0.5).astype(int)
        px = (xs[m] - 0.5).astype(int)
        closer = zz > zbuf[py, px]
        if not closer.any():
            continue
        py, px = py[closer], px[closer]
        zbuf[py, px] = zz[closer]
        tid[py, px] = ti
        bw[py, px] = np.stack([l0[m][closer], l1[m][closer], l2[m][closer]], -1)
    _VRCACHE[key] = (tid, bw)
    return tid, bw


def transfer_normals(src_nmap, src_mesh, dst_mesh, size=1024, ss=2, flip_green=True):
    """Карта нормалей src (касательное пространство src) → касательное пространство dst через то же соответствие:
    n_мир = T·x + B·y + N·z на src, затем проекция на T, B, N dst. -> RGB (R = X, G = Y, B = Z), size²."""
    S = size * ss
    transfer(np.zeros((4, 4, 3)), src_mesh, dst_mesh, size, ss)  # заполнить кеш соответствия
    mask, t, b, UV, dist_v, bad_tri = _MAPCACHE[(id(src_mesh), id(dst_mesh), _wh(size), ss, 0.04)]
    T = dst_mesh["tri"]

    def interp(attr, tri, bb):
        return bb[:, :1] * attr[tri[:, 0]] + bb[:, 1:2] * attr[tri[:, 1]] + bb[:, 2:] * attr[tri[:, 2]]

    if "_tan" not in dst_mesh:
        dst_mesh["_tan"], dst_mesh["_bit"] = vertex_tangents(dst_mesh)
    if "_tan" not in src_mesh:
        src_mesh["_tan"], src_mesh["_bit"] = vertex_tangents(src_mesh)
    Nd = _unit(interp(dst_mesh["nrm"], T[t], b))
    Td = _unit(interp(dst_mesh["_tan"], T[t], b))
    Bd = _unit(interp(dst_mesh["_bit"], T[t], b))
    # треугольник src под uv: растр развёртки src
    key = ("tid", id(src_mesh), 2048)
    if key not in _MAPCACHE:
        _MAPCACHE[key] = raster_uv(src_mesh, 2048)[0]
    tid_s = _MAPCACHE[key]
    xs = np.clip((UV[:, 0] * 2048).astype(int), 0, 2047)
    ys = np.clip((UV[:, 1] * 2048).astype(int), 0, 2047)
    ts = tid_s[ys, xs]
    ok = ts >= 0
    ts = np.where(ok, ts, 0)
    Ts = src_mesh["tri"][ts]
    # барицентры uv внутри треугольника src — гладкая интерполяция T, B, N (без граней)
    u0, u1, u2 = src_mesh["uv"][Ts[:, 0]], src_mesh["uv"][Ts[:, 1]], src_mesh["uv"][Ts[:, 2]]
    den = (u1[:, 1] - u2[:, 1]) * (u0[:, 0] - u2[:, 0]) + (u2[:, 0] - u1[:, 0]) * (u0[:, 1] - u2[:, 1])
    den = np.where(np.abs(den) < 1e-12, 1e-12, den)
    l0 = ((u1[:, 1] - u2[:, 1]) * (UV[:, 0] - u2[:, 0]) + (u2[:, 0] - u1[:, 0]) * (UV[:, 1] - u2[:, 1])) / den
    l1 = ((u2[:, 1] - u0[:, 1]) * (UV[:, 0] - u2[:, 0]) + (u0[:, 0] - u2[:, 0]) * (UV[:, 1] - u2[:, 1])) / den
    bb = np.clip(np.stack([l0, l1, 1 - l0 - l1], -1), 0, 1)
    bb /= np.maximum(bb.sum(-1, keepdims=True), 1e-9)
    Ns = _unit(interp(src_mesh["nrm"], Ts, bb))
    Tsv = _unit(interp(src_mesh["_tan"], Ts, bb))
    Bsv = _unit(interp(src_mesh["_bit"], Ts, bb))
    nt = sample_bilinear(src_nmap, UV[:, 0], UV[:, 1])[:, :3] / 127.5 - 1.0
    gy = -nt[:, 1:2] if flip_green else nt[:, 1:2]
    nz = np.sqrt(np.clip(1 - nt[:, 0:1] ** 2 - nt[:, 1:2] ** 2, 0, 1))
    nw = _unit(Tsv * nt[:, 0:1] + Bsv * gy + Ns * nz)
    x = (nw * Td).sum(-1)
    y = (nw * Bd).sum(-1)
    z = (nw * Nd).sum(-1)
    if flip_green:
        y = -y
    out = np.zeros((S, S, 3))
    out[...] = (127.5, 127.5, 255.0)
    out[mask] = np.stack([x, y, z], -1) * 127.5 + 127.5
    out[mask][~ok] = (127.5, 127.5, 255.0)
    if ss > 1:
        out = out.reshape(size, ss, size, ss, 3).mean((1, 3))
    return np.clip(out, 0, 255)


def aligned(mesh, src_box, dst_box):
    """Копия сетки, переведённая аффинно по осям: рамка dst_box (x0,x1,y0,y1,z0,z1) → src_box. Нужна, когда сетки одной
    вещи разной высоты/ширины (шорты, гетры Legacy и NHL 24): соответствие по ближайшей точке ищется после выравнивания."""
    a = np.array(dst_box, dtype=np.float64).reshape(3, 2)
    b = np.array(src_box, dtype=np.float64).reshape(3, 2)
    sc = (b[:, 1] - b[:, 0]) / np.maximum(a[:, 1] - a[:, 0], 1e-9)
    off = b[:, 0] - a[:, 0] * sc
    m = dict(mesh)
    m["pos"] = mesh["pos"] * sc + off
    n = mesh["nrm"] / np.where(sc == 0, 1, sc)  # нормали — обратным масштабом
    m["nrm"] = _unit(n)
    for k in ("_tan", "_bit"):
        m.pop(k, None)
    return m


def bbox(mesh):
    P = mesh["pos"]
    return [P[:, 0].min(), P[:, 0].max(), P[:, 1].min(), P[:, 1].max(), P[:, 2].min(), P[:, 2].max()]


if __name__ == "__main__":
    sys.exit(main())
