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
RULES = os.environ.get("FB_KIT_RULES") or os.path.join(HERE, "kit_rules.toml")  # FB_KIT_RULES — пробы с другими правилами


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
    sp = r.get("sponsor", {})
    if sp.get("drop"):
        for k in sp.get("patches", []):
            if k in rules:
                rules[k]["enabled"] = False
                rules[k]["sponsor"] = True
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


def fill_rows(img, hole):
    """Закраска области hole построчной линейной интерполяцией между краями (горизонтальные полосы сохраняются)."""
    out = img.copy()
    ys = np.unique(np.nonzero(hole)[0])
    for y in ys:
        row = hole[y]
        xs = np.nonzero(row)[0]
        # отрезки подряд
        splits = np.split(xs, np.nonzero(np.diff(xs) > 1)[0] + 1)
        for seg in splits:
            x0, x1 = seg[0] - 1, seg[-1] + 1
            if x0 < 0 or x1 >= img.shape[1]:
                continue
            a, b = img[y, x0], img[y, x1]
            t = (np.arange(len(seg)) + 1)[:, None] / (len(seg) + 1)
            out[y, seg] = a * (1 - t) + b * t
    return out


def fill_mirror(img, hole):
    """Дыра — отражением соседних пикселей той же строки (левая половина — слева, правая — справа): фактура ткани
    и горизонтальные полосы сохраняются; что не нашлось — растеканием цвета соседей."""
    out = img.copy()
    W = img.shape[1]
    left_over = np.zeros_like(hole)
    for y in np.nonzero(hole.any(1))[0]:
        row = hole[y]
        xs = np.nonzero(row)[0]
        cuts = np.nonzero(np.diff(xs) > 1)[0]
        for seg in np.split(xs, cuts + 1):
            a, b = seg[0], seg[-1]
            mid = (a + b) / 2
            src = np.where(seg <= mid, a - 1 - (seg - a), b + 1 + (b - seg))
            ok = (src >= 0) & (src < W)
            ok[ok] = ~row[src[ok]]
            out[y, seg[ok]] = img[y, src[ok]]
            left_over[y, seg[~ok]] = True
    if left_over.any():
        from .kit3d import fill_holes
        out = fill_holes(out, ~left_over, iters=48)
    return out


def standard_patches(comp, rules, defaults, names=None, win=0.022):
    """Для комплектов без base-слоёв: нашивки в стандартных местах развёртки (у всех adidas-свитеров NHL 24 щит NHL
    у ворота и логотип сзади лежат в одних и тех же uv). В окне вокруг uv правила фон — медиана рамки окна, нашивка —
    пиксели, отличные от фона; связная область у центра. -> (псевдо-основа с закрашенными нашивками, метки, нашивки)."""
    if names is None:
        names = ("neck_shield", "back_neck") + tuple(k for k, r in rules.items() if r.get("sponsor"))
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
        w = int(r.get("win", win) * H)
        y0, y1, x0, x1 = max(cy - w, 0), min(cy + w, H), max(cx - w, 0), min(cx + w, H)
        if "box" in r:  # нашивка задана прямоугольником uv (u0, v0, u1, v1) — весь он, с фоном нашивки и надписью
            u0, v0, u1, v1 = r["box"]
            bx0, by0, bx1, by1 = int(u0 * H), int(v0 * H), int(np.ceil(u1 * H)), int(np.ceil(v1 * H))
            y0, y1, x0, x1 = max(by0 - 4, 0), min(by1 + 4, H), max(bx0 - 4, 0), min(bx1 + 4, H)
            mk = np.zeros((y1 - y0, x1 - x0), bool)
            mk[by0 - y0:by1 - y0, bx0 - x0:bx1 - x0] = True
            lab[y0:y1, x0:x1][mk] = i
            hole[y0:y1, x0:x1] |= mk
            patches.append((i, (slice(by0, by1), slice(bx0, bx1)), int(mk.sum())))
            a = base[y0:y1, x0:x1, 3].copy()
            base[y0:y1, x0:x1] = fill_rows(base[y0:y1, x0:x1], hole[y0:y1, x0:x1])
            base[y0:y1, x0:x1, 3] = a
            continue
        box = comp[y0:y1, x0:x1, :3]
        if r.get("smooth"):  # фактура ткани (блёстки у VGK) — не нашивка: разница по сглаженному окну
            box = ndi.gaussian_filter(box, (r["smooth"], r["smooth"], 0))
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
        ys, xs = np.nonzero(l == best)
        if r.get("smooth") and (ys.min() == 0 or xs.min() == 0 or ys.max() == l.shape[0] - 1 or xs.max() == l.shape[1] - 1):
            continue  # слилось с окружением (до края окна) — не нашивка, не трогаем
        mk = ndi.binary_dilation(l == best, iterations=2)
        lab[y0:y1, x0:x1][mk] = i
        hole[y0:y1, x0:x1] |= mk
        ys, xs = np.nonzero(mk)
        sl = (slice(y0 + ys.min(), y0 + ys.max() + 1), slice(x0 + xs.min(), x0 + xs.max() + 1))
        patches.append((i, sl, int(mk.sum())))
        # закрасить нашивку: спонсор — построчно (полосы рядом не размываются), герб — отражением соседей той же
        # строки (фактура ткани и полосы сохраняются), прочие — растеканием цвета соседей
        if r.get("fill") == "mirror":
            gh = np.zeros((H, H), dtype=bool)
            gh[y0:y1, x0:x1] = mk
            a = base[..., 3].copy()
            base = fill_mirror(base, gh)
            base[..., 3] = a
            continue
        a = base[y0:y1, x0:x1, 3].copy()
        if r.get("sponsor"):
            base[y0:y1, x0:x1] = fill_rows(base[y0:y1, x0:x1], hole[y0:y1, x0:x1])
        else:
            from .kit3d import fill_holes
            base[y0:y1, x0:x1] = fill_holes(base[y0:y1, x0:x1], ~hole[y0:y1, x0:x1], iters=48)
        base[y0:y1, x0:x1, 3] = a
    return base, lab, patches


def uv_point(mesh, u, v):
    """Точка и нормаль сетки в точке развёртки (u, v) (первый треугольник, в который она попала)."""
    uv = mesh["uv"][mesh["tri"]]                                   # T × 3 × 2
    a, b, c = uv[:, 0], uv[:, 1], uv[:, 2]
    den = (b[:, 1] - c[:, 1]) * (a[:, 0] - c[:, 0]) + (c[:, 0] - b[:, 0]) * (a[:, 1] - c[:, 1])
    with np.errstate(all="ignore"):
        l0 = ((b[:, 1] - c[:, 1]) * (u - c[:, 0]) + (c[:, 0] - b[:, 0]) * (v - c[:, 1])) / den
        l1 = ((c[:, 1] - a[:, 1]) * (u - c[:, 0]) + (a[:, 0] - c[:, 0]) * (v - c[:, 1])) / den
    l2 = 1 - l0 - l1
    ok = np.nonzero((l0 >= -1e-9) & (l1 >= -1e-9) & (l2 >= -1e-9) & np.isfinite(l0))[0]
    if not len(ok):
        raise ValueError(f"({u}, {v}) вне развёртки")
    t = ok[0]
    w = np.array([l0[t], l1[t], l2[t]])
    T = mesh["tri"][t]
    return w @ mesh["pos"][T], _unit(w @ mesh["nrm"][T])


MERGE_PARTS = ()   # имена правил, чьи связные части — одна нашивка (fb.edge_kit.use_club: профиль merge_parts); () — как было


def _match(lab, lid, sl, rules, defaults):
    """Имя правила для участка lid (ближайшее uv центра, не дальше match_radius) или None."""
    H = lab.shape[0]
    ys, xs = np.nonzero(lab[sl] == lid)
    u_c, v_c = (xs.mean() + sl[1].start + 0.5) / H, (ys.mean() + sl[0].start + 0.5) / H
    best, bd = None, 1e9
    for name, r in rules.items():
        if "uv" in r and np.hypot(r["uv"][0] - u_c, r["uv"][1] - v_c) < bd:
            best, bd = name, np.hypot(r["uv"][0] - u_c, r["uv"][1] - v_c)
    return best if bd <= defaults.get("match_radius", 0.05) else None


def merge_parts(lab, patches, rules, defaults, names):
    """Участки, которые по месту — одна нашивка из names, — в один (метка, рамка — объединение). Герб TBL (21.10):
    молния и кольцо — разные связные, рамка молнии выходит за кольцо (find_patches их не сливает), и [crest_fit]
    уменьшал их порознь (0,75 и 0,99) — молния съёживалась внутри кольца. lab меняется на месте."""
    out = list(patches)
    for name in names:
        grp = [p for p in out if _match(lab, p[0], p[1], rules, defaults) == name]
        if len(grp) < 2:
            continue
        lid0 = grp[0][0]
        sl = tuple(slice(min(p[1][k].start for p in grp), max(p[1][k].stop for p in grp)) for k in range(2))
        for lid, s, _ in grp[1:]:
            v = lab[s]
            v[v == lid] = lid0
        out = [(lid0, sl, sum(p[2] for p in grp))] + [p for p in out if p not in grp]
        print(f"  нашивка {name}: частей {len(grp)} — одной (merge_parts)")
    return out


def plan_decals(comp, lab, patches, rules, defaults, src, dst, tid24):
    """Рамки декалей: центр и якобиан на свитере NHL 24 → правила → посадка на Legacy. -> (placed, soft)."""
    if MERGE_PARTS:
        patches = merge_parts(lab, patches, rules, defaults, MERGE_PARTS)
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
        if "legacy_uv" in rule:  # место задано на развёртке Legacy (щит NHL — как у всех EA-форм, по центру)
            cL, nL = uv_point(dst, *rule["legacy_uv"])
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
                       "_frame": (cL, nL, pinv, R, sc, rad, u_c, v_c), "_lid": lid,
                       "_box": (sl[1].start / H, sl[0].start / H, sl[1].stop / H, sl[0].stop / H)})
    return placed, soft


def collar_color(src_tex, rule):
    """Основной цвет свитера под воротом (по правилу [collar.v_insert]) на развёртке NHL 24: method "mode" — самый
    частый цвет окна (цвета квантуются по 16 уровней; шнуровка, щит и кант у ворота — меньшинство и не подмешиваются),
    "median" — медиана окна."""
    H = src_tex.shape[0]
    u, v = rule.get("sample_uv", [0.5, 0.605])
    b = max(int(rule.get("sample_box", 0.008) * H), 2)
    x, y = int(u * H), int(v * H)
    win = src_tex[max(y - b, 0):y + b, max(x - b, 0):x + b, :]
    px = win.reshape(-1, win.shape[-1])
    if rule.get("method", "median") == "mode":
        q = (px[:, :3] // 16).astype(int)
        key = q[:, 0] * 256 + q[:, 1] * 16 + q[:, 2]
        vals, cnt = np.unique(key, return_counts=True)
        return np.median(px[key == vals[np.argmax(cnt)]], axis=0)
    return np.median(px, axis=0)


LEGACY_SHIRT = "rendering/jersey/shirt_1_1_2.rx2"  # «рубашка» в вырезе ворота Edge (V-вставка): её развёртка —
                                                  # угол текстуры свитера u 0,08…0,18, v 0,85…0,90


def legacy_with_shirt():
    """Свитер Legacy + сетка «рубашки» в V-вырезе ворота (в игре она видна в вырезе; цвет — из той же текстуры)."""
    j = load_legacy()
    return merge(j, load_legacy(LEGACY_SHIRT)), len(j["tri"])


def decal_post(comp, placed, soft, n_jersey_tri, collar=None, pre=(), crest_fit=None, protect=None):
    """collar — (правило, цвет): V-вставка ворота Edge — сетка «рубашки» (треугольники после свитера) — заливается
    цветом свитера под воротом: у adidas ворот круглый, выреза нет.
    pre — правки основы до нашивок: fn(img, mask) -> img на сверхвыборке (kit_fix: ворот со шнуровкой, полоса на груди).
    crest_fit — герб не на букву капитана (kit_fix.crest_fit): масштаб герба подбирается по зазору до зон букв.
    protect — маска развёртки (любого размера), куда нашивки не кладутся (ворот со шнуровкой от EA)."""
    def post(img, msk, P, N, tri, UV=None):
        out = img.copy()
        for fn in pre:
            out = fn(out, msk)
        flat = out[msk]
        free = None
        if protect is not None:
            pm = np.asarray(Image.fromarray(protect.astype(np.uint8) * 255).resize(msk.shape[::-1], Image.NEAREST)) > 0
            free = ~pm[msk]
        if crest_fit is not None:
            yy, xx = np.nonzero(msk)
            du, dv = (xx + 0.5) / msk.shape[1], (yy + 0.5) / msk.shape[0]
        on_jersey = tri < n_jersey_tri
        if collar is not None:
            rule, color = collar
            sel = ~on_jersey
            flat[sel] = color[: flat.shape[1]]
            post.v_insert = int(sel.sum())
        for pl in placed:
            cL, nL, pinv, R, sc, rad, u_c, v_c = pl["_frame"]
            d = P - cL
            sel = (on_jersey & (np.linalg.norm(d, axis=1) < rad) & ((N @ nL) > 0.25) & (np.abs(d @ nL) < 0.06))
            if free is not None:
                sel &= free
            if not sel.any():
                pl["texels"] = 0
                continue
            duv = (d[sel] @ pinv.T) / sc
            duv = duv @ R.T
            uu = u_c + duv[:, 0]
            vv = v_c + duv[:, 1]
            if crest_fit is not None and pl["name"] == "crest":
                uu, vv = _fit_crest(pl, uu, vv, soft[pl["_lid"]], du[sel], dv[sel], crest_fit)
            col = sample_bilinear(comp, uu, vv)
            a = sample_bilinear(soft[pl["_lid"]][..., None], uu, vv)[:, 0]
            inside = (uu >= 0) & (uu <= 1) & (vv >= 0) & (vv <= 1)
            a = np.where(inside, np.clip(a, 0, 1), 0)
            flat[sel] = flat[sel] * (1 - a[:, None]) + col * a[:, None]
            pl["texels"] = int((a > 0.5).sum())
        out[msk] = flat
        return out
    return post


def _fit_crest(pl, uu, vv, soft_m, du, dv, fit):
    """Герб не на букву капитана: сначала ниже (низ — не ниже max_bottom, как у EA-форм), потом меньше — масштаб s ≤ 1
    относительно середины нижнего края (или центра), чтобы до зон букв было ≥ gap_min. -> (uu, vv) на развёртке NHL 24."""
    from .kit_fix import fit_crest, rect_gap
    b0, b1, b2, b3 = pl["_box"]
    au, av = (b0 + b2) / 2, (b3 if fit.get("anchor", "bottom") == "bottom" else (b1 + b3) / 2)
    k = np.cov(vv, dv)[0, 1] / max(np.var(dv), 1e-12)        # v NHL 24 на единицу v Legacy у герба

    def moved(s, dlv):
        return au + (uu - au) / s, av + (vv - k * dlv - av) / s

    def foot(s, dlv):
        u2, v2 = moved(s, dlv)
        a = sample_bilinear(soft_m[..., None], u2, v2)[:, 0]
        return (a > 0.5) & (u2 >= 0) & (u2 <= 1) & (v2 >= 0) & (v2 <= 1)

    def gap_of(s, dlv=0.0):
        fp = foot(s, dlv)
        return rect_gap(du[fp], dv[fp], fit["rects"])

    fp0 = foot(1.0, 0.0)
    bottom = float(dv[fp0].max()) if fp0.any() else 1.0
    s, dlv, g0, g1 = fit_crest(fit, gap_of, max(0.0, fit.get("max_bottom", 0.85) - bottom))
    pl["fit_scale"], pl["fit_down_v"] = round(s, 3), round(dlv, 4)
    pl["letter_gap_before"], pl["letter_gap"] = round(g0, 4), round(g1, 4)
    return moved(s, dlv)


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
