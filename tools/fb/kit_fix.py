"""Правки свитера при переносе NHL 24 → Legacy по правилам kit_rules.toml (поверх основы, до нашивок).

* [crest_fit] — герб на груди не заходит на букву капитана/ассистента: зона 5 карты номеров шаблона (name_*_cm).
  Если зазор «герб — зона буквы» меньше gap_min (у EA-форм Legacy медиана 0,02 — survey), герб опускается и уменьшается
  относительно середины своего нижнего края (верх и бока уходят от буквы, низ на месте), но не меньше min_scale.
  Работает в kit_hybrid.decal_post для нашивки crest.
* [laces.<КЛУБ>.<форма>] — ворот со шнуровкой без 3D-шнурков (hastie 0): раскладка ворота (обод, язычок V, люверсы,
  шнурки) и рельеф ворота — из EA-комплекта Legacy со шнуровкой (from), цвета — из NHL 24: обод — band_uv, язычок
  и V-вставка — insert_uv, шнурки — lace_uv (точки на основе NHL 24). Люверсы и тени шнурков — как у EA.
* [chest_band.<КЛУБ>.<форма>] — горизонтальная полоса на груди уже: верхний край — прямая на trim ниже прежнего
  (по середине груди), выше неё полоса закрашивается цветом свитера (концы у подмышек тоже).
"""
import os
import tomllib

import numpy as np
from PIL import Image
from scipy import ndimage as ndi

from .kit_hybrid import RULES, collar_color

LACE_ROI = (0.40, 0.40, 0.60, 0.68)  # u0, v0, u1, v1: ворот и шнуровка на развёртке Legacy стиля 1


def _rules(path=RULES):
    with open(path, "rb") as f:
        return tomllib.load(f)


def club_rule(table, code, kit, path=RULES):
    """Правило [table.<КЛУБ>.<форма>] или None."""
    return _rules(path).get(table, {}).get(code, {}).get(kit)


def zone_rects(name_png, ids):
    """Прямоугольники зон карты номеров (u0, v0, u1, v1); синий канал — номер зоны (5 — буква капитана)."""
    a = np.asarray(Image.open(name_png).convert("RGBA")).astype(int)
    h, w = a.shape[:2]
    m = (a[..., 0] > 128) & (a[..., 1] > 128)
    out = []
    for z in ids:
        ys, xs = np.nonzero(m & (a[..., 2] == z))
        if len(xs):
            out.append((xs.min() / w, ys.min() / h, (xs.max() + 1) / w, (ys.max() + 1) / h))
    return out


def rect_gap(u, v, rects):
    """Наименьшее расстояние точек (u, v) до прямоугольников; 0 — точка внутри; нет точек — inf."""
    g = np.inf
    if not len(u):
        return g
    for u0, v0, u1, v1 in rects:
        du = np.maximum(np.maximum(u0 - u, u - u1), 0)
        dv = np.maximum(np.maximum(v0 - v, v - v1), 0)
        g = min(g, float(np.sqrt(du * du + dv * dv).min()))
    return g


def crest_fit(name_png, path=RULES):
    """Правило [crest_fit] с зонами букв шаблона → словарь для kit_hybrid.decal_post (None — правила нет)."""
    r = _rules(path).get("crest_fit")
    if not r or not r.get("enabled", True):
        return None
    rects = zone_rects(name_png, r.get("zones", [5]))
    if not rects:
        return None
    return {"rects": rects, "gap_min": float(r.get("gap_min", 0.02)), "min_scale": float(r.get("min_scale", 0.6)),
            "anchor": r.get("anchor", "bottom"), "max_bottom": float(r.get("max_bottom", 0.85))}


def fit_crest(fit, gap_of, max_down):
    """Сначала ниже (не больше max_down по v), потом меньше: наибольший масштаб s ∈ [min_scale, 1] и наименьший сдвиг,
    при которых gap_of(s, сдвиг) ≥ gap_min. -> (s, сдвиг, зазор было, зазор стало)."""
    need = fit["gap_min"]
    g0 = gap_of(1.0, 0.0)
    if g0 >= need:
        return 1.0, 0.0, g0, g0
    d = max_down
    if gap_of(1.0, d) >= need:                    # хватает сдвига вниз — наименьший такой сдвиг
        lo, hi = 0.0, d
        for _ in range(12):
            mid = (lo + hi) / 2
            lo, hi = (lo, mid) if gap_of(1.0, mid) >= need else (mid, hi)
        return 1.0, hi, g0, gap_of(1.0, hi)
    lo, hi = fit["min_scale"], 1.0
    if gap_of(lo, d) < need:
        return lo, d, g0, gap_of(lo, d)
    for _ in range(14):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if gap_of(mid, d) >= need else (lo, mid)
    return lo, d, g0, gap_of(lo, d)


def _box(H, b):
    m = np.zeros((H, H), bool)
    u0, v0, u1, v1 = b
    m[int(v0 * H):int(np.ceil(v1 * H)), int(u0 * H):int(np.ceil(u1 * H))] = True
    return m


def _up(a, shape):
    """Маска/поле 1024² → размер сверхвыборки (повтор пикселей)."""
    fy, fx = shape[0] // a.shape[0], shape[1] // a.shape[1]
    return np.repeat(np.repeat(a, fy, axis=0), fx, axis=1)


def _mode(px):
    q = (px[:, :3] // 16).astype(int)
    key = q[:, 0] * 256 + q[:, 1] * 16 + q[:, 2]
    vals, cnt = np.unique(key, return_counts=True)
    return np.median(px[key == vals[np.argmax(cnt)]], 0)


class Laces:
    """Ворот со шнуровкой по раскладке EA-комплекта rule['from'] (папка распакованного шаблона tpl_dir)."""

    def __init__(self, rule, src_tex, tpl_dir, size=1024):
        self.rule, self.tpl_dir, H = rule, tpl_dir, size
        ea = np.asarray(Image.open(os.path.join(tpl_dir, "jersey_cm.png")).convert("RGB").resize((H, H))) \
            .astype(np.float64)
        R, G, B = ea[..., 0], ea[..., 1], ea[..., 2]
        lum = ea @ np.array([0.299, 0.587, 0.114])
        roi = _box(H, rule.get("roi", LACE_ROI))
        shield = _box(H, rule["shield_box"])
        red = roi & (R > G + 40) & (R > B + 40)
        red_full = ndi.binary_closing(red | shield, iterations=3) & roi       # язычок V под щитом EA — тоже
        yy = (np.arange(H)[:, None] + 0.5) / H + np.zeros((1, H))
        self.band = red_full & (yy < rule["split_v"])                         # обод ворота
        self.tongue = red_full & (yy >= rule["split_v"])                      # язычок V
        ref = np.median(lum[red]) if red.any() else 1.0
        self.shade = np.clip(lum / max(ref, 1.0), 0.7, 1.2)
        self.clean = _box(H, rule["clean_box"]) & ~red_full                   # здесь — цвет свитера, затем шнурки
        lace = _box(H, rule["lace_box"]) & ~red_full & ~shield                # шнурки и люверсы EA (ниже кокетки)
        light = lace & (lum > 170)
        white = np.median(lum[light]) if light.any() else 230.0
        alpha = np.clip((white - lum) / max(white - 50.0, 1.0), 0, 1) * lace
        alpha[alpha < 0.3] = 0                                                # строчка по краю — не переносим
        green = (G - R) > 6
        self.lace_a = alpha * green                                           # шнурки
        self.keep_a = alpha * ~green                                          # люверсы, обводка — как у EA
        self.ea = ea
        full = {k: collar_color(src_tex, {"sample_uv": rule[k + "_uv"], "sample_box": rule.get(k + "_win", 0.004),
                                          "method": "mode"}) for k in ("band", "insert", "lace")}
        self.colors = {k: c[:3] for k, c in full.items()}
        self.insert = full["insert"]                                          # V-вставка (все каналы основы)
        rm = red_full | self.clean | shield
        self.relief_mask = ndi.gaussian_filter(ndi.binary_dilation(rm, iterations=4).astype(np.float64), 2.0)

    def pre(self, out, msk):
        """Основа на сверхвыборке (до нашивок): ворот по раскладке EA в цветах NHL 24."""
        sh = msk.shape
        o = out
        red = self.band | self.tongue
        ring = ndi.binary_dilation(self.clean, iterations=12) & ~ndi.binary_dilation(self.clean | red, iterations=4)
        ring = _up(ring, sh) & msk
        clean = _up(self.clean, sh) & msk
        if ring.any():
            o[clean] = _mode(o[ring])[: o.shape[-1]]                       # остатки ворота NHL 24 — цвет свитера
        shade = _up(self.shade, sh)
        for m, c in ((self.band, self.colors["band"]), (self.tongue, self.colors["insert"])):
            mm = _up(m, sh) & msk
            o[mm, :3] = c[None, :] * shade[mm][:, None]
        la = (_up(self.lace_a, sh) * msk)[..., None]
        o[..., :3] = o[..., :3] * (1 - la) + self.colors["lace"][None, None, :] * la
        ka = (_up(self.keep_a, sh) * msk)[..., None]
        o[..., :3] = o[..., :3] * (1 - ka) + _up(self.ea, sh) * ka
        return o

    def relief(self, nm_path, sm_path):
        """Рельеф ворота (обод, люверсы, шнуровка) из шаблона EA поверх чистых карт формы (файлы переписываются)."""
        for path, name in ((nm_path, "jersey_nm.png"), (sm_path, "jersey_sm.png")):
            im = Image.open(path)
            cur = np.asarray(im).astype(np.float64)
            H, W = cur.shape[:2]
            ea = np.asarray(Image.open(os.path.join(self.tpl_dir, name)).convert(im.mode).resize((W, H), Image.LANCZOS))                 .astype(np.float64)
            m = np.asarray(Image.fromarray((self.relief_mask * 255).astype(np.uint8)).resize((W, H), Image.LANCZOS))                 .astype(np.float64) / 255.0
            if cur.ndim == 3:
                m = m[..., None]
            Image.fromarray(np.clip(np.round(cur * (1 - m) + ea * m), 0, 255).astype(np.uint8), im.mode).save(path)


class BandTrim:
    """Полоса на груди уже: верхний край — прямая на trim ниже прежнего (по середине груди)."""

    def __init__(self, rule):
        self.r = rule

    def __call__(self, out, msk):
        r = self.r
        Hs, Ws = msk.shape
        u0, u1 = r.get("u", [0.22, 0.78])
        v0, v1 = r.get("v", [0.60, 0.82])
        x0, x1, y0, y1 = int(u0 * Ws), int(u1 * Ws), int(v0 * Hs), int(v1 * Hs)

        def sample(uv, box=0.006):
            x, y, b = int(uv[0] * Ws), int(uv[1] * Hs), max(int(box * Hs), 2)
            win = out[y - b:y + b, x - b:x + b].reshape(-1, out.shape[-1])
            ok = msk[y - b:y + b, x - b:x + b].reshape(-1)
            return _mode(win[ok]) if ok.any() else win.mean(0)

        band, body = sample(r["band_uv"]), sample(r["body_uv"])
        reg = out[y0:y1, x0:x1]
        m = (np.abs(reg[..., :3] - band[:3]).sum(-1) < r.get("thr", 60)) & msk[y0:y1, x0:x1]
        tops = []
        for a, b in r.get("ref_u", [[0.30, 0.38], [0.62, 0.70]]):
            for x in range(int(a * Ws) - x0, int(b * Ws) - x0):
                ys = np.nonzero(m[:, x])[0]
                if len(ys):
                    tops.append(ys.min())
        if not tops:
            return out
        top = int(np.median(tops)) + int(round(r["trim"] * Hs))
        cut = m.copy()
        cut[top:] = False
        cut = ndi.binary_dilation(cut, iterations=3) & msk[y0:y1, x0:x1]   # и сглаженный край прежней полосы
        cut[top:] = False
        reg[cut] = body[: reg.shape[-1]]
        self.report = {"band_top_v": round((y0 + np.median(tops)) / Hs, 4), "new_top_v": round((y0 + top) / Hs, 4),
                       "texels": int(cut.sum())}
        return out


# ---------------------------------------------------------------- опись EA и лист «было | стало»

def letter_glyphs(font_png):
    """Буквы капитана и ассистента из атласа шрифта (столбец справа: C, под ней A). -> {"C": RGBA, "A": RGBA}."""
    f = np.asarray(Image.open(font_png).convert("RGBA"))
    H, W = f.shape[:2]
    x0, y0, y1 = int(0.80 * W), int(0.12 * H), int(0.66 * H)
    col = f[y0:y1, x0:]
    lab, n = ndi.label(col[..., 3] > 60)
    objs = [s for s in ndi.find_objects(lab) if s is not None and (s[0].stop - s[0].start) > 0.08 * H]
    objs.sort(key=lambda s: s[0].start)
    return {k: col[s] for k, s in zip("CA", objs[:2])}


def with_letter(cm, font_png, rect, letter="C"):
    """Развёртка с буквой капитана в зоне карты номеров (по высоте зоны, по центру) — как ставит игра."""
    g = letter_glyphs(font_png).get(letter)
    im = Image.fromarray(np.asarray(cm)[..., :3].astype(np.uint8)).convert("RGBA")
    if g is None:
        return np.asarray(im.convert("RGB"))
    W, H = im.size
    u0, v0, u1, v1 = rect
    zw, zh = (u1 - u0) * W, (v1 - v0) * H
    sc = min(zw / g.shape[1], zh / g.shape[0])
    gi = Image.fromarray(g).resize((max(1, int(g.shape[1] * sc)), max(1, int(g.shape[0] * sc))), Image.LANCZOS)
    im.alpha_composite(gi, (int(u0 * W + (zw - gi.size[0]) / 2), int(v0 * H + (zh - gi.size[1]) / 2)))
    return np.asarray(im.convert("RGB"))


def crest_box(cm, rect, size=512):
    """Рамка герба на груди (связная область «не цвет зоны буквы» у (0,5; 0,745)) и зазор до зоны. -> (рамка, зазор)."""
    a = np.asarray(Image.fromarray(np.asarray(cm)[..., :3].astype(np.uint8)).resize((size, size))).astype(int)
    u0, v0, u1, v1 = rect
    body = _mode(a[int(v0 * size):int(v1 * size), int(u0 * size):int(u1 * size)].reshape(-1, 3).astype(np.float64))
    diff = np.abs(a - body).sum(-1) > 60
    roi = _box(size, (0.33, 0.60, 0.67, 0.90))
    lab, n = ndi.label(ndi.binary_closing(diff & roi, iterations=2))
    ys, xs = np.nonzero(lab)
    if not len(xs):
        return None, None
    i = np.argmin((ys - 0.745 * size) ** 2 + (xs - 0.5 * size) ** 2)
    m = lab == lab[ys[i], xs[i]]
    ys, xs = np.nonzero(m)
    return ((xs.min() / size, ys.min() / size, (xs.max() + 1) / size, (ys.max() + 1) / size),
            rect_gap((xs + 0.5) / size, (ys + 0.5) / size, [rect]))


def cmd_survey(a):
    """EA-комплекты Legacy (распакованные шаблоны): герб и зона буквы капитана — зазор, низ, ширина."""
    import glob
    rows = []
    for d in sorted(glob.glob(os.path.join(a.kits, "1_*"))):
        if not (os.path.exists(os.path.join(d, "jersey_cm.png")) and os.path.exists(os.path.join(d, "name_cm.png"))):
            continue
        z = zone_rects(os.path.join(d, "name_cm.png"), [5])
        if not z:
            continue
        bb, g = crest_box(Image.open(os.path.join(d, "jersey_cm.png")).convert("RGB"), z[0])
        if bb and bb[2] - bb[0] > 0.1:          # мелкое — не герб (не нашлось)
            rows.append((os.path.basename(d), bb, g))
    p = lambda xs: np.percentile(xs, [10, 25, 50, 75, 90]).round(3).tolist()
    print(f"EA-форм {len(rows)}: зазор герб—буква p10/25/50/75/90 {p([r[2] for r in rows])}; "
          f"низ герба {p([r[1][3] for r in rows])}; ширина {p([r[1][2] - r[1][0] for r in rows])}")


def cmd_sheet(a):
    """Лист «было | стало»: грудь с буквой C в зоне карты номеров и ворот крупно, с рельефом (nm, sm)."""
    from PIL import ImageDraw, ImageFont
    from . import kit3d, kit_hybrid
    mesh, _ = kit_hybrid.legacy_with_shirt()
    f16 = ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", 16)
    f20 = ImageFont.truetype("C:/Windows/Fonts/segoeuib.ttf", 20)
    CHEST, NECK = (-0.36, 0.36, 1.10, 1.62), (-0.17, 0.17, 1.42, 1.70)

    def load(d, n, mode="RGB"):
        return np.asarray(Image.open(os.path.join(d, n)).convert(mode).resize((1024, 1024))).astype(np.float64)

    rows = []
    for spec in a.kits:
        name, rest = spec.split("=", 1)
        was, now, nmap = rest.split(";")
        rect = zone_rects(nmap, [5])[0]
        cols = []
        for d in (was, now):
            cm, nm, sm = load(d, "jersey_cm.png"), load(d, "jersey_nm.png"), load(d, "jersey_sm.png")
            _bb, g = crest_box(cm, rect)
            cl = with_letter(cm, os.path.join(d, "font_cm.png"), rect).astype(np.float64)
            v1 = kit3d.render_lit(mesh, cl, "front", 330, frame=CHEST, nmap=nm, smap=sm, ss=2)
            v2 = kit3d.render_lit(mesh, cm, "front", 300, frame=NECK, nmap=nm, smap=sm, ss=2)
            cols.append((g, v1, v2))
        rows.append((name, cols))
        print(name, [round(c[0], 3) for c in cols], flush=True)
    v1w, v1h = rows[0][1][0][1].size
    v2w, v2h = rows[0][1][0][2].size
    rh = max(v1h, v2h) + 30
    cw = v1w + v2w + 8
    S = Image.new("RGB", (200 + 2 * cw + 40, 70 + len(rows) * rh), (30, 30, 34))
    d = ImageDraw.Draw(S)
    d.multiline_text((10, 8), "Было | стало: грудь с буквой «C» в зоне капитана (карта номеров формы) и ворот крупно\n"
                     "зазор «герб — зона буквы» по u/v; у EA-форм Legacy медиана 0,02", fill=(240, 240, 240),
                     font=f20, spacing=4)
    for i, (name, cols) in enumerate(rows):
        y = 64 + i * rh
        d.multiline_text((10, y + rh // 2 - 24), name.replace("|", "\n"), fill=(240, 240, 240), font=f20, spacing=4)
        for j, (g, v1, v2) in enumerate(cols):
            x = 200 + j * (cw + 30)
            d.text((x, y), ("было" if j == 0 else "стало") + f": зазор герб—буква {g:.3f}", fill=(220, 220, 220), font=f16)
            S.paste(v1, (x, y + 24))
            S.paste(v2, (x + v1w + 8, y + 24))
    S.save(a.out)
    print(a.out, S.size)


def main():
    import argparse
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("survey")
    s.add_argument("--kits", default=os.path.join(os.path.dirname(RULES), "..", "..", "game", "work", "nhl24", "out",
                                                  "_legacy_kits"))
    s = sub.add_parser("sheet")
    s.add_argument("out")
    s.add_argument("kits", nargs="+", help="ИМЯ=папка_было;папка_стало;name_cm.png («|» в ИМЕНИ — перенос)")
    a = ap.parse_args()
    return {"survey": cmd_survey, "sheet": cmd_sheet}[a.cmd](a)


if __name__ == "__main__":
    import sys
    sys.exit(main())
