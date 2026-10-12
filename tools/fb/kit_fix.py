"""Правки свитера при переносе NHL 24 → Legacy по правилам kit_rules.toml (поверх основы, до нашивок).

* [crest_fit] — герб на груди не заходит на букву капитана/ассистента: зона 5 карты номеров шаблона (name_*_cm).
  Если зазор «герб — зона буквы» меньше gap_min (у EA-форм Legacy медиана 0,02 — survey), герб опускается и уменьшается
  относительно середины своего нижнего края (верх и бока уходят от буквы, низ на месте), но не меньше min_scale.
  Работает в kit_hybrid.decal_post для нашивки crest.
* [collar_lace.<КЛУБ>.<форма>] — ворот со шнуровкой без 3D-шнурков (hastie 0) от EA-комплекта Legacy (from): слои
  по маскам EA — ткань, ворот и V (перекраска со светотенью EA), шнурки, люверсы, щит NHL по контуру; рельеф — весь
  от from, места нашивок (smooth_boxes) — чистая основа A. Раскладка EA-ворота — общие ключи [collar_lace].
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


def collar_lace_rule(code, kit, path=RULES):
    """[collar_lace] (раскладка EA-ворота со шнуровкой — общая) + [collar_lace.<КЛУБ>.<форма>] или None."""
    t = _rules(path).get("collar_lace", {})
    own = t.get(code, {}).get(kit)
    if own is None:
        return None
    return {**{k: v for k, v in t.items() if not isinstance(v, dict)}, **own}


def _soft(mask, sigma=0.6):
    """Маска → альфа с антиалиасингом ~1 тексель."""
    return np.clip(ndi.gaussian_filter(mask.astype(np.float64), sigma) * 1.6 - 0.3, 0, 1)


class CollarLace:
    """Ворот со шнуровкой без 3D-шнурков ([collar_lace]): из EA-комплекта rule['from'] (папка шаблона tpl_dir).

    Слои по маскам EA (развёртка Legacy), снизу вверх:
      * ткань — цвет свитера под всей областью ворота и шнуровки (остатки ворота NHL 24 закрываются);
      * ворот и нарисованный V — красное EA выше низа щита (v_bottom), перекраска со светотенью EA: выше split_v —
        цвет ворота (collar), ниже — цвет V (v_insert); красное ниже щита (прорезь под шнурками) — не берётся;
      * шнурки — по форме шнурков EA (антиалиасинг 1 тексель), цвет lace со светотенью EA без тёмной обводки;
      * люверсы — по форме, как у EA (металл);
      * щит NHL — по контуру щита EA, без подложки.
    Цвета: <часть>_color = [r, g, b] или <часть>_uv = [u, v] — точка на основе NHL 24 (самый частый цвет окна)."""

    def __init__(self, rule, src_tex, tpl_dir, size=1024):
        self.rule, self.tpl_dir, H = rule, tpl_dir, size
        ea = np.asarray(Image.open(os.path.join(tpl_dir, "jersey_cm.png")).convert("RGB").resize((H, H))) \
            .astype(np.float64)
        R, G, B = ea[..., 0], ea[..., 1], ea[..., 2]
        lum = ea @ np.array([0.299, 0.587, 0.114])
        sat = ea.max(-1) - ea.min(-1)
        yy = (np.arange(H)[:, None] + 0.5) / H + np.zeros((1, H))
        roi = _box(H, rule.get("roi", LACE_ROI))
        sbox = _box(H, rule["shield_box"])
        lbox = _box(H, rule["lace_box"])

        def ref(m):
            return max(float(np.median(lum[m])), 1.0) if m.any() else 1.0

        def color(part):
            if part + "_color" in rule:
                return np.array(rule[part + "_color"], dtype=np.float64)
            return collar_color(src_tex, {"sample_uv": rule[part + "_uv"], "sample_box": rule.get(part + "_win", 0.004),
                                          "method": "mode"})
        full = {k: color(k) for k in ("collar", "v_insert", "lace")}
        self.colors = {k: c[:3] for k, c in full.items()}
        self.insert = full["v_insert"]                                  # V-вставка «рубашки» (все каналы основы)
        # щит NHL EA: чёрный контур → заливка дыр → силуэт (наибольшая область)
        outline = sbox & (lum < 80) & (sat < 50)
        sil = ndi.binary_fill_holes(ndi.binary_closing(outline, iterations=1))
        lab, n = ndi.label(sil)
        if n:
            sil = lab == (np.argmax(ndi.sum(sil, lab, range(1, n + 1))) + 1)
        self.shield_a = _soft(sil)
        # ворот и V: красное EA выше низа щита
        v_bottom = rule.get("v_bottom", rule["shield_box"][3])
        red_strong = roi & (R > G + 40) & (R > B + 40)
        self.red_a = np.clip((R - np.maximum(G, B) - 20) / 60.0, 0, 1) * roi * (yy < v_bottom)
        lum_s = ndi.gaussian_filter(lum, 1.2)
        shade = np.clip(lum_s / ref(red_strong), 0.6, 1.25)[..., None]
        self.red_col = np.where((yy >= rule["split_v"])[..., None], self.colors["v_insert"], self.colors["collar"]) * shade
        # шнурки и люверсы: тёмное в зоне шнуровки (ниже кокетки), не щит, не красное
        white = ref(roi & ~red_strong & (sat < 12) & (lum > 170))
        zone = lbox & (yy >= rule["lace_box"][1]) & ~ndi.binary_dilation(sil, iterations=1)
        red_any = (R - np.maximum(G, B) - 20) / 60.0 > 0.3                         # прорезь под шнурками — не шнурок
        dark = zone & (lum < 0.6 * white) & ~red_any
        lab, n = ndi.label(dark)
        idx = np.arange(1, n + 1)
        size_ = ndi.sum(np.ones_like(lum), lab, idx)
        green = ndi.maximum((G - R) > 10, lab, idx)
        lace = np.isin(lab, idx[(size_ >= 12) & (green > 0)])
        eye = np.isin(lab, idx[(size_ >= 12) & (green == 0)])
        self.lace_a, self.eye_a = _soft(lace), _soft(eye)
        core = lace & ((G - R) > 10)
        self.lace_col = self.colors["lace"] * np.clip(lum_s / ref(core), 0.82, 1.12)[..., None]
        self.ea = ea
        self.area = ndi.binary_dilation(roi & ((self.red_a > 0) | lbox | sbox), iterations=10) & roi  # под тканью
        self.feather = ndi.gaussian_filter(self.area.astype(np.float64), 1.2) * self.area
        self.report = {"from": rule["from"], "colors": {k: [int(x) for x in c] for k, c in self.colors.items()},
                       "lace_texels": int(lace.sum()), "eyelet_texels": int(eye.sum()), "shield_texels": int(sil.sum())}

    def pre(self, out, msk):
        """Основа на сверхвыборке (до нашивок): ткань → ворот и V → шнурки → люверсы → щит NHL."""
        sh = msk.shape
        ring = ndi.binary_dilation(self.area, iterations=10) & ~ndi.binary_dilation(self.area, iterations=3)
        ring = _up(ring, sh) & msk
        body = _mode(out[ring])[:3] if ring.any() else np.array([24.0, 55.0, 46.0])
        new = np.broadcast_to(body, self.ea.shape).copy()
        for a, col in ((self.red_a, self.red_col), (self.lace_a, self.lace_col), (self.eye_a, self.ea),
                       (self.shield_a, self.ea)):
            new = new * (1 - a[..., None]) + col * a[..., None]
        a = (_up(self.feather, sh) * msk)[..., None]
        out[..., :3] = out[..., :3] * (1 - a) + _up(np.clip(new, 0, 255), sh) * a
        return out

    def relief(self, nm_path, sm_path, clean_dir):
        """Весь рельеф (nm, sm) — из шаблона EA; места нашивок (smooth_boxes) — чистая основа A (clean_A_*)."""
        ea_cm = np.asarray(Image.open(os.path.join(self.tpl_dir, "jersey_cm.png")).convert("RGB").resize((1024, 1024))) \
            .astype(np.float64)
        logo = np.zeros((1024, 1024), bool)
        for b in self.rule.get("smooth_boxes", []):
            m = _box(1024, b)
            ys, xs = np.nonzero(m)
            y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
            win = ea_cm[y0:y1, x0:x1]
            border = np.concatenate([win[0], win[-1], win[:, 0], win[:, -1]])
            d = np.abs(win - np.median(border, 0)).sum(-1) > 45
            d = ndi.binary_fill_holes(ndi.binary_closing(d, iterations=2))
            logo[y0:y1, x0:x1] |= d
        logo = ndi.binary_dilation(logo, iterations=5)
        mk = ndi.gaussian_filter(logo.astype(np.float64), 2.5)
        for path, name, clean in ((nm_path, "jersey_nm.png", "clean_A_nm.png"), (sm_path, "jersey_sm.png", "clean_A_sm.png")):
            mode = Image.open(path).mode
            ea = np.asarray(Image.open(os.path.join(self.tpl_dir, name)).convert(mode).resize((1024, 1024), Image.LANCZOS)) \
                .astype(np.float64)
            cl = np.asarray(Image.open(os.path.join(clean_dir, clean)).convert(mode).resize((1024, 1024), Image.LANCZOS)) \
                .astype(np.float64)
            m = mk[..., None] if ea.ndim == 3 else mk
            Image.fromarray(np.clip(np.round(ea * (1 - m) + cl * m), 0, 255).astype(np.uint8), mode).save(path)


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
        top0 = int(np.median(tops))
        top = top0 + int(round(r["trim"] * Hs))
        cut = m.copy()
        cut[top:] = False
        cut[:max(top0 - int(r.get("above", 0.02) * Hs), 0)] = False             # только у полосы (ворот выше — нет)
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
    """Лист «было | стало»: грудь с буквой C в зоне капитана, ворот крупно (с рельефом nm/sm) и щиток NHL с осью
    симметрии. Строка: ИМЯ=заголовок@папка;заголовок@папка[;…];name_cm.png (папка — jersey_cm/nm/sm, font_cm)."""
    from PIL import ImageDraw, ImageFont
    from . import kit3d, kit_hybrid
    mesh, _ = kit_hybrid.legacy_with_shirt()
    f16 = ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", 16)
    f20 = ImageFont.truetype("C:/Windows/Fonts/segoeuib.ttf", 20)
    CHEST, NECK, SHIELD = (-0.36, 0.36, 1.10, 1.62), (-0.17, 0.17, 1.42, 1.70), (-0.07, 0.07, 1.50, 1.66)

    def load(d, n):
        return np.asarray(Image.open(os.path.join(d, n)).convert("RGB").resize((1024, 1024))).astype(np.float64)

    rows = []
    for spec in a.kits:
        name, rest = spec.split("=", 1)
        parts = rest.split(";")
        rect = zone_rects(parts[-1], [5])[0]
        cols = []
        for item in parts[:-1]:
            title, d = item.split("@", 1)
            cm, nm, sm = load(d, "jersey_cm.png"), load(d, "jersey_nm.png"), load(d, "jersey_sm.png")
            _bb, g = crest_box(cm, rect)
            cl = with_letter(cm, os.path.join(d, "font_cm.png"), rect).astype(np.float64)
            v1 = kit3d.render_lit(mesh, cl, "front", 330, frame=CHEST, nmap=nm, smap=sm, ss=2)
            v2 = kit3d.render_lit(mesh, cm, "front", 300, frame=NECK, nmap=nm, smap=sm, ss=2)
            v3 = kit3d.render_lit(mesh, cm, "front", 260, frame=SHIELD, nmap=nm, smap=sm, ss=3)  # щиток и шнуровка ×4
            ImageDraw.Draw(v3).line([(v3.width // 2, 0), (v3.width // 2, v3.height)], fill=(255, 0, 255))
            cols.append((title, g, v1, v2, v3))
        rows.append((name, cols))
        print(name, [round(c[1], 3) for c in cols], flush=True)
    _t, _g, v1, v2, v3 = rows[0][1][0]
    cw = v1.width + v2.width + v3.width + 16
    rh = max(v1.height, v2.height, v3.height) + 30
    ncol = max(len(c) for _n, c in rows)
    S = Image.new("RGB", (200 + ncol * (cw + 30), 70 + len(rows) * rh), (30, 30, 34))
    d = ImageDraw.Draw(S)
    d.multiline_text((10, 8), a.title or ("Было | стало: грудь с буквой «C» в зоне капитана, ворот крупно, щиток NHL "
                     "(лиловая линия — середина)\nзазор «герб — зона буквы»; у EA-форм Legacy медиана 0,02"),
                     fill=(240, 240, 240), font=f20, spacing=4)
    for i, (name, cols) in enumerate(rows):
        y = 64 + i * rh
        d.multiline_text((10, y + rh // 2 - 24), name.replace("|", "\n"), fill=(240, 240, 240), font=f20, spacing=4)
        for j, (title, g, v1, v2, v3) in enumerate(cols):
            x = 200 + j * (cw + 30)
            d.text((x, y), f"{title}: зазор герб—буква {g:.3f}" if g is not None else title, fill=(220, 220, 220),
                   font=f16)
            S.paste(v1, (x, y + 24))
            S.paste(v2, (x + v1.width + 8, y + 24))
            S.paste(v3, (x + v1.width + v2.width + 16, y + 24))
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
    s.add_argument("kits", nargs="+", help="ИМЯ=заголовок@папка;…;name_cm.png («|» в ИМЕНИ — перенос)")
    s.add_argument("--title", default="", help="заголовок листа («\n» — перенос)")
    a = ap.parse_args()
    return {"survey": cmd_survey, "sheet": cmd_sheet}[a.cmd](a)


if __name__ == "__main__":
    import sys
    sys.exit(main())
