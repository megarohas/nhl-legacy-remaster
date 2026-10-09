"""Гибридный перенос свитера NHL 24 → NHL Legacy: основа через 3D + нашивки отдельными «декалями» по правилам.

1. Основа (цвет, полосы, фактура) — jersey_*_base_color NHL 24 (без нашивок) переносится на развёртку Legacy через
   3D, как вариант Б (fb.kit3d.transfer: ближайшая точка поверхности, соответствие в вершинах).
2. Нашивки — связные участки, где готовый jersey_*_color отличается от основы. Для каждой: центр на развёртке NHL 24 →
   точка и касательная рамка (якобиан UV→3D треугольника) на свитере NHL 24 → сдвиг/масштаб/поворот по правилам
   (fb/kit_rules.toml) → ближайшая точка свитера Legacy. Рисунок проецируется на поверхность Legacy по текселям
   (плоская декаль в касательной плоскости) — локальный масштаб и поворот учтены, на швах развёртки разрывов нет.

  python -m fb.kit_hybrid COMPOSITE.png BASE.png OUT.png [--club SEA --kit home] [--rules fb/kit_rules.toml]
         [--profile laces] [--report OUT.json]
"""
import argparse
import json
import os
import sys
import tomllib

import numpy as np
from PIL import Image
from scipy import ndimage as ndi

from . import kit3d
from .kit3d import _unit, load_legacy, load_nhl24, load_tex, project, raster_uv, sample_bilinear

HERE = os.path.dirname(os.path.abspath(__file__))
RULES = os.path.join(HERE, "kit_rules.toml")


def load_rules(path, club=None, kit=None, profiles=()):
    """Правила нашивок: [patch.*] ← [profile.<p>.*] (например laces — комплект со шнуровкой) ← [club.<К>.<форма>.*]."""
    with open(path, "rb") as f:
        r = tomllib.load(f)
    rules = {k: dict(v) for k, v in r.get("patch", {}).items()}
    for prof in profiles or ():
        for k, v in r.get("profile", {}).get(prof, {}).items():
            rules.setdefault(k, {}).update(v)
    if club and kit:
        for k, v in r.get("club", {}).get(club, {}).get(kit, {}).items():
            rules.setdefault(k, {}).update(v)
    return r.get("defaults", {}), rules


def find_patches(comp, base, defaults):
    """-> (метки, список (id, срез, площадь)): |готовый − основа| > threshold, связные; участок, чья рамка лежит
    внутри рамки другого (глаз «S» внутри герба), присоединяется к нему."""
    d = np.abs(comp[..., :3] - base[..., :3]).sum(-1)
    m = ndi.binary_closing(d > defaults.get("threshold", 30), iterations=3)
    m = ndi.binary_fill_holes(m)
    lab, n = ndi.label(m)
    objs = ndi.find_objects(lab)
    keep = []
    for i, sl in enumerate(objs):
        area = int((lab[sl] == i + 1).sum())
        if area >= defaults.get("min_area", 200):
            keep.append([i + 1, sl, area])
    keep.sort(key=lambda k: -k[2])
    merged = []
    for lid, sl, area in keep:
        host = None
        for h in merged:
            hs = h[1]
            if (sl[0].start >= hs[0].start and sl[0].stop <= hs[0].stop and
                    sl[1].start >= hs[1].start and sl[1].stop <= hs[1].stop):
                host = h
                break
        if host is None:
            merged.append([lid, sl, area])
        else:
            lab[lab == lid] = host[0]
            host[2] += area
    return lab, [tuple(h) for h in merged]


def tri_frame(mesh, tid_map, u, v):
    """Треугольник сетки под (u, v) и якобиан d(3D)/d(uv) (3×2) в нём."""
    S = tid_map.shape[0]
    x, y = int(np.clip(u * S, 0, S - 1)), int(np.clip(v * S, 0, S - 1))
    t = tid_map[y, x]
    if t < 0:  # в дырке: ближайший тексель с треугольником
        ys, xs = np.nonzero(tid_map >= 0)
        k = np.argmin((xs - x) ** 2 + (ys - y) ** 2)
        t = tid_map[ys[k], xs[k]]
    a, b, c = mesh["tri"][t]
    P0, P1, P2 = mesh["pos"][a], mesh["pos"][b], mesh["pos"][c]
    U0, U1, U2 = mesh["uv"][a], mesh["uv"][b], mesh["uv"][c]
    Duv = np.stack([U1 - U0, U2 - U0], 1)          # 2×2
    Dp = np.stack([P1 - P0, P2 - P0], 1)           # 3×2
    J = Dp @ np.linalg.inv(Duv)                    # 3×2: d(3D)/d(uv)
    # барицентры точки (u, v) → 3D
    l = np.linalg.solve(Duv, np.array([u, v]) - U0)
    p = P0 + Dp @ l
    nrm = _unit(mesh["nrm"][a] + mesh["nrm"][b] + mesh["nrm"][c])
    n = _unit(np.cross(J[:, 0], J[:, 1]))
    if np.dot(n, nrm) < 0:
        n = -n
    return t, p, J, n


NHL24_TIE = "content/character/skater/player/jersey/adidas/components/player_jerseytie_adidas_lod0_mesh"
LEGACY_TIE = "rendering/jersey/jerseytie_0_1_2.rx2"


def merge(a, b):
    n = len(a["pos"])
    return {"pos": np.vstack([a["pos"], b["pos"]]), "uv": np.vstack([a["uv"], b["uv"]]),
            "nrm": np.vstack([a["nrm"], b["nrm"]]), "tri": np.vstack([a["tri"], b["tri"] + n])}


def meshes(with_tie=True):
    """Свитер (+ шнуровка ворота: у обеих игр её развёртка — в углу 0,8…1 той же текстуры)."""
    src, dst = load_nhl24(), load_legacy()
    if with_tie:
        src = merge(src, load_nhl24(NHL24_TIE))
        dst = merge(dst, load_legacy(LEGACY_TIE))
    return src, dst


def standard_patches(comp, rules, defaults, names=("neck_shield", "back_neck"), win=0.022):
    """Для комплектов без base-слоёв: нашивки в стандартных местах развёртки (у всех adidas-свитеров NHL 24 щит NHL
    у ворота и логотип сзади лежат в одних и тех же uv). В окне вокруг uv правила фон — медиана рамки окна, нашивка —
    пиксели, отличные от фона; связная область у центра. -> (псевдо-основа с закрашенными нашивками, метки, нашивки)."""
    H = comp.shape[0]
    lab = np.zeros((H, H), dtype=np.int32)
    patches = []
    base = comp.copy()
    hole = np.zeros((H, H), dtype=bool)
    for i, name in enumerate(names, 1):
        r = rules.get(name)
        if not r or "uv" not in r:
            continue
        cx, cy = int(r["uv"][0] * H), int(r["uv"][1] * H)
        w = int(win * H)
        y0, y1, x0, x1 = max(cy - w, 0), min(cy + w, H), max(cx - w, 0), min(cx + w, H)
        box = comp[y0:y1, x0:x1, :3]
        border = np.concatenate([box[0], box[-1], box[:, 0], box[:, -1]])
        bg = np.median(border, axis=0)
        m = np.abs(box - bg).sum(-1) > defaults.get("threshold", 30) * 1.3
        m = ndi.binary_closing(m, iterations=2)
        m = ndi.binary_fill_holes(m)
        l, n = ndi.label(m)
        if n == 0:
            continue
        # компонента ближе всех к центру окна
        best, bd = 0, 1e9
        for k in range(1, n + 1):
            ys, xs = np.nonzero(l == k)
            dd = np.hypot(ys.mean() - (cy - y0), xs.mean() - (cx - x0))
            if dd < bd and len(ys) >= 40:
                best, bd = k, dd
        if not best or bd > w * 0.6:
            continue
        mk = ndi.binary_dilation(l == best, iterations=2)
        lab[y0:y1, x0:x1][mk] = i
        hole[y0:y1, x0:x1] |= mk
        ys, xs = np.nonzero(mk)
        sl = (slice(y0 + ys.min(), y0 + ys.max() + 1), slice(x0 + xs.min(), x0 + xs.max() + 1))
        patches.append((i, sl, int(mk.sum())))
        # закрасить нашивку растеканием цвета соседей — только в окне (быстро)
        from .kit3d import fill_holes
        crop = fill_holes(base[y0:y1, x0:x1], ~hole[y0:y1, x0:x1], iters=48)
        a = base[y0:y1, x0:x1, 3].copy()
        base[y0:y1, x0:x1] = crop
        base[y0:y1, x0:x1, 3] = a
    return base, lab, patches


def plan_decals(comp, lab, patches, rules, defaults, src, dst, tid24):
    """Рамки декалей: центр и якобиан на свитере NHL 24 → правила → посадка на Legacy. -> (placed, soft)."""
    H = comp.shape[0]
    soft = {}
    placed = []
    for lid, sl, area in patches:
        ys, xs = np.nonzero(lab[sl] == lid)
        u_c = (xs.mean() + sl[1].start + 0.5) / H
        v_c = (ys.mean() + sl[0].start + 0.5) / H
        best, bd = None, 1e9
        for name, r in rules.items():
            if "uv" not in r:
                continue
            dd = np.hypot(r["uv"][0] - u_c, r["uv"][1] - v_c)
            if dd < bd:
                best, bd = name, dd
        name = best if bd <= defaults.get("match_radius", 0.05) else f"patch_{lid}"
        rule = rules.get(name, {}) if name in rules else {}
        if not rule.get("enabled", True):
            continue
        Ht = tid24.shape[0]
        if tid24[min(int(v_c * Ht), Ht - 1), min(int(u_c * Ht), Ht - 1)] < 0:
            continue  # центр вне развёртки свитера NHL 24 (запас под другие сетки/варианты) — не нашивка
        t, p, J, n = tri_frame(src, tid24, u_c, v_c)
        p = p + np.array(rule.get("offset_cm", [0, 0, 0]), dtype=np.float64) / 100.0
        lt, lb, ld = project(p[None], n[None], dst, k=32)
        T = dst["tri"][lt[0]]
        cL = lb[0] @ dst["pos"][T]
        nL = _unit(lb[0] @ dst["nrm"][T])
        JL = J - np.outer(nL, nL @ J)
        sc = float(rule.get("scale", 1.0))
        th = np.radians(float(rule.get("rotate_deg", 0.0)))
        R = np.array([[np.cos(th), -np.sin(th)], [np.sin(th), np.cos(th)]])
        pinv = np.linalg.pinv(JL)
        bw = (sl[1].stop - sl[1].start) / H
        bh = (sl[0].stop - sl[0].start) / H
        rad = 0.5 * np.hypot(np.linalg.norm(J[:, 0]) * bw, np.linalg.norm(J[:, 1]) * bh) * sc * 1.25 + 0.01
        mask = np.zeros((H, H), dtype=np.float64)
        mask[sl] = (lab[sl] == lid)
        mask = ndi.gaussian_filter(ndi.binary_dilation(mask > 0, iterations=1).astype(np.float64), 0.8)
        soft[lid] = mask
        placed.append({"name": name, "uv": [round(float(u_c), 4), round(float(v_c), 4)], "area": area,
                       "nhl24_3d": np.round(p, 4).tolist(), "legacy_3d": np.round(cL, 4).tolist(),
                       "snap_cm": round(float(ld[0]) * 100, 2), "rule": {k: v for k, v in rule.items() if k != "note"},
                       "_frame": (cL, nL, pinv, R, sc, rad, u_c, v_c), "_lid": lid})
    return placed, soft


def decal_post(comp, placed, soft, n_jersey_tri):
    def post(img, msk, P, N, tri):
        out = img.copy()
        flat = out[msk]
        on_jersey = tri < n_jersey_tri
        for pl in placed:
            cL, nL, pinv, R, sc, rad, u_c, v_c = pl["_frame"]
            d = P - cL
            sel = (on_jersey & (np.linalg.norm(d, axis=1) < rad) & ((N @ nL) > 0.25) & (np.abs(d @ nL) < 0.06))
            if not sel.any():
                pl["texels"] = 0
                continue
            duv = (d[sel] @ pinv.T) / sc
            duv = duv @ R.T
            uu = u_c + duv[:, 0]
            vv = v_c + duv[:, 1]
            col = sample_bilinear(comp, uu, vv)
            a = sample_bilinear(soft[pl["_lid"]][..., None], uu, vv)[:, 0]
            inside = (uu >= 0) & (uu <= 1) & (vv >= 0) & (vv <= 1)
            a = np.where(inside, np.clip(a, 0, 1), 0)
            flat[sel] = flat[sel] * (1 - a[:, None]) + col * a[:, None]
            pl["texels"] = int((a > 0.5).sum())
        out[msk] = flat
        return out
    return post


def hybrid(comp_path, base_path, out_path, club=None, kit=None, rules_path=RULES, size=1024, ss=2, report=None,
           with_tie=True, profiles=()):
    """base_path = None — комплект без base-слоёв: нашивки ищутся в стандартных местах (standard_patches)."""
    src, dst = meshes(with_tie)
    n_jersey_tri = len(load_legacy()["tri"])  # нашивки — только на свитер, не на шнуровку
    comp = load_tex(comp_path)
    defaults, rules = load_rules(rules_path, club, kit, profiles)
    if base_path:
        base = load_tex(base_path)
        lab, patches = find_patches(comp, base, defaults)
    else:
        base, lab, patches = standard_patches(comp, rules, defaults)
    tid24, _ = raster_uv(src, 1024)
    placed, soft = plan_decals(comp, lab, patches, rules, defaults, src, dst, tid24)
    img, mask, dist, info = kit3d.transfer(base, src, dst, size, ss, post=decal_post(comp, placed, soft, n_jersey_tri))
    Image.fromarray(np.clip(img, 0, 255).astype(np.uint8)).save(out_path)
    rep = [{k: v for k, v in pl.items() if not k.startswith("_")} for pl in placed]
    if report:
        with open(report, "w", encoding="utf-8") as f:
            json.dump(rep, f, ensure_ascii=False, indent=1)
    return rep


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("composite")
    ap.add_argument("base")
    ap.add_argument("out")
    ap.add_argument("--club")
    ap.add_argument("--kit")
    ap.add_argument("--rules", default=RULES)
    ap.add_argument("--report")
    ap.add_argument("--profile", action="append", default=[], help="профиль правил, например laces (шнуровка ворота)")
    a = ap.parse_args()
    rep = hybrid(a.composite, a.base, a.out, a.club, a.kit, a.rules, report=a.report, profiles=a.profile)
    for r in rep:
        print(f"{r['name']:12s} uv={r['uv']} площадь {r['area']:6d}  NHL24 {r['nhl24_3d']} -> Legacy {r['legacy_3d']} "
              f"(посадка {r['snap_cm']} см), текселей {r.get('texels', 0)}")


if __name__ == "__main__":
    sys.exit(main())
