"""Полоски на рукавах ближе к кисти (правило пользователя 11.10, kit_rules.toml [sleeve]) и проверка по карте номеров.

Развёртка свитера Legacy стиля 1: рукава вдоль u, манжета у u = 0 (левый) и у u = 1 (правый), строки rows; плечо
(верх рукава) — там, где игра рисует номер по карте номеров шаблона (name_*_cm, зоны 2 и 3). Правило на каждом рукаве:
  * верх рисунка рукава u_top — самый близкий к плечу пиксель, отличный от цвета под номером (цвет в зоне номера),
    на строках зоны ±margin, в том числе внутри зоны (кроме того, что подходит к ней со стороны плеча);
  * рисунок от манжеты до u_top сжимается к манжете в k раз: k = base_k («не сильно, но ближе», у всех), а если и так
    до зоны номера меньше gap_min — сильнее, но не меньше min_k; манжета на месте, однотонный рукав между рисунком
    и дальним краем зоны номера растягивается, дальше (плечо, пройма, нашивки) — без изменений;
  * проверка — зазор между верхом рисунка и зоной номера по u (у EA CHI 1_6_0 — 0,066).

  python -m fb.sleeve check DIR… [--name name_cm.png]   # зазор «полосы — зона номера» у готовых свитеров (jersey_cm.png)
  python -m fb.sleeve sheet OUT.png "ИМЯ=до.png;после.png;font_cm.png;name_cm.png"…
                                                       # лист «рукав до | после, с номером на плече» («|» в ИМЕНИ — перенос)
"""
import argparse
import os
import sys
import tomllib

import numpy as np
from PIL import Image

RULES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "kit_rules.toml")
DEFAULT = {"rows": [0.28, 0.73], "gap_min": 0.05, "base_k": 0.85, "min_k": 0.7, "thr": 60, "margin": 0.03}
NUMBER_ZONES = (2, 3)  # зоны карты номеров: 2 — левый рукав (u≈0,25), 3 — правый (u≈0,75)


def rule(path=RULES):
    with open(path, "rb") as f:
        r = tomllib.load(f).get("sleeve", {})
    return {**DEFAULT, **r}


def _base_color(px):
    q = (px // 16).astype(int)
    key = q[:, 0] * 256 + q[:, 1] * 16 + q[:, 2]
    vals, cnt = np.unique(key, return_counts=True)
    return np.median(px[key == vals[np.argmax(cnt)]], 0)


RUN = 4  # тексели подряд: просвет короче — ещё тот же рисунок


def band_top(img, zone, left, island=None, r=None):
    """Верх рисунка рукава на строках зоны ±margin — самый близкий к плечу пиксель не цвета «под номером» (цвет зоны)
    от манжеты до дальнего края зоны: полосы, зашедшие в зону, считаются, в том числе через просветы. Не считается
    то, что подходит к зоне со стороны плеча (пройма, кокетка, нашивка): участок, связанный с дальним краем зоны.
    -> (u_top, u_zone) — u_zone: край зоны номера со стороны манжеты; u_top = None — рисунка нет."""
    r = r or rule()
    a = np.asarray(img)[..., :3].astype(int)
    H, W = a.shape[:2]
    u0, v0, u1, v1 = zone
    r0, r1 = int(max(v0 - r["margin"], 0) * H), int(min(v1 + r["margin"], 1) * H)
    z0, z1 = int(u0 * W), int(np.ceil(u1 * W))
    zpx = a[int(v0 * H):int(np.ceil(v1 * H)), z0:z1]
    zok = np.ones(zpx.shape[:2], bool) if island is None else island[int(v0 * H):int(np.ceil(v1 * H)), z0:z1]
    if not zok.any():
        return None, (u0 if left else u1)
    base = _base_color(zpx[zok])
    c0, c1 = (0, z1) if left else (z0, W)       # от манжеты через всю зону
    reg = a[r0:r1, c0:c1]
    ok = np.ones(reg.shape[:2], bool) if island is None else island[r0:r1, c0:c1]
    diff = (np.abs(reg - base).sum(-1) > r["thr"]) & ok
    if not left:
        diff = diff[:, ::-1]                    # манжета — в начале строки
    near = (z0 - c0) if left else (c1 - z1)     # край зоны со стороны манжеты, в текселях от манжеты
    n = diff.shape[1]                           # дальний край зоны
    top = -1
    for row in diff:
        end = n
        while end > near and row[max(near, end - RUN):end].any():
            end -= 1                            # связано с дальним краем зоны — со стороны плеча, не полосы
        cols = np.nonzero(row[:end])[0]
        if len(cols):
            top = max(top, cols.max() + 1)
    if top < 0:
        return None, (u0 if left else u1)
    if left:
        return (c0 + top) / W, u0
    return (c1 - top) / W, u1


def plan(img, zones, island=None, r=None):
    """Сжатие рисунка каждого рукава: {зона: {left, d_top, d_end, k, gap_before, gap_after}} — расстояния по u от манжеты:
    до верха рисунка, до дальнего края зоны номера; зазор рисунок—зона до и после."""
    r = r or rule()
    out = {}
    px = 2.0 / np.asarray(img).shape[1]           # запас 2 текселя: сглаживание на изломе
    for z, zone in zones.items():
        left = bool(zone[0] < 0.5)
        top, uz = band_top(img, zone, left, island, r)
        if top is None:
            continue
        d_top = top if left else 1 - top           # расстояние от манжеты до верха рисунка
        d_zone = uz if left else 1 - uz            # до зоны номера
        d_end = zone[2] if left else 1 - zone[0]   # до дальнего края зоны: дальше развёртка не меняется
        want = min(d_top * r["base_k"], d_zone - r["gap_min"] - px)
        k = max(want / d_top, r["min_k"]) if d_top > 0 else 1.0
        k = min(k, 1.0)
        out[z] = {"left": left, "d_top": round(float(d_top), 4), "d_end": round(float(d_end), 4), "k": round(float(k), 3),
                  "gap_before": round(float(d_zone - d_top), 3), "gap_after": round(float(d_zone - d_top * k), 3)}
    return out


def _remap_side(band, n, W, d_top, k, d_end, left):
    """Строки band (h × W × C): рукав с манжетой у края; источник для расстояния от манжеты t: t/k до верха рисунка,
    дальше — линейно до дальнего края зоны номера d_end (там совпадает с исходным)."""
    t = (np.arange(n) + 0.5) / W                       # расстояние от манжеты (доля u) у текселей рукава
    knee = d_top * k
    src = np.where(t <= knee, t / k, d_top + (t - knee) * (d_end - d_top) / max(d_end - knee, 1e-6))
    xs = np.clip(src * W - 0.5, 0, W - 1)
    if not left:
        xs = W - 1 - xs
    x0 = np.floor(xs).astype(int)
    x1 = np.minimum(x0 + 1, W - 1)
    f = (xs - x0)
    f = f[None, :, None] if band.ndim == 3 else f[None, :]
    return band[:, x0] * (1 - f) + band[:, x1] * f


def remap(img, zones, island=None, r=None):
    """Рисунок рукавов ближе к кисти по плану (plan). -> (новый массив того же вида, план)."""
    r = r or rule()
    a = np.asarray(img)
    H, W = a.shape[:2]
    p = plan(a, zones, island, r)
    out = a.astype(np.float64).copy()
    y0, y1 = int(r["rows"][0] * H), int(np.ceil(r["rows"][1] * H))
    band = a[y0:y1].astype(np.float64)
    for z, q in p.items():
        if q["k"] >= 0.999:
            continue
        n = int(round(q["d_end"] * W))
        side = _remap_side(band, n, W, q["d_top"], q["k"], q["d_end"], q["left"])
        if q["left"]:
            out[y0:y1, :n] = side
        else:
            out[y0:y1, W - n:] = side[:, ::-1]
    if np.issubdtype(a.dtype, np.integer):
        out = np.clip(np.round(out), 0, 255).astype(a.dtype)
    return out, p


def name_zones(name_png, size):
    """Зоны номера на рукавах (u0, v0, u1, v1) по карте номеров (name_cm.png)."""
    a = np.asarray(Image.open(name_png).convert("RGBA")).astype(int)
    h, w = a.shape[:2]
    out = {}
    for z in NUMBER_ZONES:
        ys, xs = np.nonzero((a[..., 0] > 128) & (a[..., 1] > 128) & (a[..., 2] == z))
        if len(xs):
            out[z] = (xs.min() / w, ys.min() / h, (xs.max() + 1) / w, (ys.max() + 1) / h)
    return out


def gap(img, zones, island=None, r=None):
    """Зазор по u между верхом рисунка рукава и зоной номера, по зонам. -> {зона: зазор} (нет рисунка — до манжеты)."""
    r = r or rule()
    res = {}
    for z, zone in zones.items():
        left = bool(zone[0] < 0.5)
        top, uz = band_top(img, zone, left, island, r)
        if top is None:
            res[z] = round(float(uz if left else 1 - uz), 3)
        else:
            res[z] = round(float(uz - top if left else top - uz), 3)
    return res


def island(size=1024):
    from . import kit3d
    tid, _ = kit3d.raster_uv(kit3d.load_legacy(), size)
    return tid >= 0


# ---------------------------------------------------------------- номер на плече для листа

def small_digits(font_png):
    """Глифы малых цифр 0…9 из атласа шрифта (строка малых цифр EA: ~0,70…0,85 высоты). -> {цифра: RGBA}."""
    from scipy import ndimage as ndi
    f = np.asarray(Image.open(font_png).convert("RGBA"))
    H = f.shape[0]
    y0, y1 = int(0.71 * H), int(0.86 * H)
    band = f[y0:y1]
    lab, n = ndi.label(band[..., 3] > 60)
    objs = sorted([s for s in ndi.find_objects(lab) if s is not None and (s[1].stop - s[1].start) > 3],
                  key=lambda s: s[1].start)
    big = [s for s in objs if (s[0].stop - s[0].start) > 0.5 * (y1 - y0) * 0.6]
    return {i: band[s] for i, s in enumerate(big[:10])}


def with_number(cm, font_png, zones, number="19"):
    """Развёртка с номером на рукавах в зонах карты номеров (как приблизительно ставит игра: по высоте зоны)."""
    digits = small_digits(font_png)
    if not digits:
        return cm
    im = Image.fromarray(np.asarray(cm)[..., :3].astype(np.uint8)).convert("RGBA")
    W, H = im.size
    for z, (u0, v0, u1, v1) in zones.items():
        glyphs = [Image.fromarray(digits[int(c)]) for c in number if int(c) in digits]
        if not glyphs:
            continue
        gw = sum(g.size[0] for g in glyphs) + 2 * (len(glyphs) - 1)
        gh = max(g.size[1] for g in glyphs)
        row = Image.new("RGBA", (gw, gh), (0, 0, 0, 0))
        x = 0
        for g in glyphs:
            row.alpha_composite(g, (x, gh - g.size[1]))
            x += g.size[0] + 2
        # на развёртке рукав идёт вдоль u: «верх» номера — к плечу (у левого рукава +u, у правого −u)
        row = row.rotate(-90 if u0 < 0.5 else 90, expand=True)
        zw, zh = int((u1 - u0) * W), int((v1 - v0) * H)
        sc = min(zw / row.size[0], zh / row.size[1])
        row = row.resize((max(1, int(row.size[0] * sc)), max(1, int(row.size[1] * sc))), Image.LANCZOS)
        im.alpha_composite(row, (int(u0 * W + (zw - row.size[0]) / 2), int(v0 * H + (zh - row.size[1]) / 2)))
    return np.asarray(im)


def cmd_check(a):
    r = rule()
    isl = island()
    for d in a.dirs:
        cm = np.asarray(Image.open(os.path.join(d, "jersey_cm.png")).convert("RGB").resize((1024, 1024)))
        zones = name_zones(a.name or os.path.join(d, "name_cm.png"), 1024)
        g = gap(cm, zones, isl)
        m = min(g.values())
        print(os.path.basename(d.rstrip("/\\")), g, "OK" if m >= r["gap_min"] else
              f"не задевает, но меньше {r['gap_min']}" if m > 0 else "ЗАДЕВАЕТ")


def cmd_sheet(a):
    from PIL import ImageDraw, ImageFont
    from . import kit3d, kit_hybrid
    mesh, _ = kit_hybrid.legacy_with_shirt()
    isl = island()
    f16 = ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", 16)
    f20 = ImageFont.truetype("C:/Windows/Fonts/segoeuib.ttf", 20)
    r = rule()
    frame_l = (-0.40, 0.40, 1.10, 1.62)
    rows = []
    for spec in a.kits:
        name, before, after, font, nmap = spec.split("=", 1)[0], *spec.split("=", 1)[1].split(";")
        zones = name_zones(nmap, 1024)
        out = []
        for path in (before, after):
            cm = np.asarray(Image.open(path).convert("RGB").resize((1024, 1024)))
            g = gap(cm, zones, isl)
            t = with_number(cm, font, zones).astype(np.float64)
            views = [kit3d.render(mesh, t, v, 300, frame=frame_l, ss=2) for v in ("right", "left")]
            out.append((g, views))
        rows.append((name, out))
        print(name, [o[0] for o in out], flush=True)
    vw, vh = rows[0][1][0][1][0].size
    LW = 190                                    # колонка подписей; «|» в имени — перенос строки
    S = Image.new("RGB", (LW + 4 * (vw + 8) + 30, 88 + len(rows) * (vh + 34)), (30, 30, 34))
    d = ImageDraw.Draw(S)
    d.multiline_text((10, 10), f"Рукав: до | после — рисунок рукава сжат к манжете (k ≤ {r['base_k']}, не меньше {r['min_k']})"
                     f"\nномер «19» — в зоне карты номеров формы; зазор «рисунок — номер» по u, цель ≥ {r['gap_min']}",
                     fill=(240, 240, 240), font=f20, spacing=6)
    for i, (name, out) in enumerate(rows):
        y = 78 + i * (vh + 34)
        d.multiline_text((10, y + vh // 2 - 20), name.replace("|", "\n"), fill=(240, 240, 240), font=f20, spacing=6)
        for j, (g, views) in enumerate(out):
            x = LW + j * 2 * (vw + 8) + j * 22
            m = min(g.values())
            d.text((x, y), ("до" if j == 0 else "после") + f": зазор {m:.3f}" +
                   ("" if m >= r["gap_min"] else "  (меньше цели)" if m > 0 else "  (номер на полосах)"),
                   fill=(220, 220, 220), font=f16)
            for k, v in enumerate(views):
                S.paste(v, (x + k * (vw + 8), y + 22))
    S.save(a.out)
    print(a.out, S.size)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("dirs", nargs="+")
    c.add_argument("--name", help="карта номеров (name_cm.png), если в папке формы её нет")
    s = sub.add_parser("sheet")
    s.add_argument("out")
    s.add_argument("kits", nargs="+", help="ИМЯ=до.png;после.png;font_cm.png;name_cm.png")
    a = ap.parse_args()
    return {"check": cmd_check, "sheet": cmd_sheet}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
