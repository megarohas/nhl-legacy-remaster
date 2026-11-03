"""Свободные дизайны масок вратаря без логотипов и клубов (03.11.2026, docs/goalie-masks.md, «Стандартные маски»).

Пользователь: «забей на референс, просто поэкспериментируй на шлемах»: геометрия, полосы разной ширины и направления,
шевроны, камуфляж и пиксели, сетка, градиенты, пламя и молнии простыми формами, ретро-двухцвет, матовый и металлик,
номерные зоны — в нескольких базовых схемах цветов, чтобы подходили к разным формам.

Маска — тип 0 (itech, helmet_0_2), рисунок 512². Рисуется только оболочка (fb.mask_gen.geometry: острова купола и
затылка), ремни, пряжки и подкладка — как у маски EA 0/125, вентиляционные отверстия — тёмные по белой маске 0/120.
Рисунок считается от 3D-позиции текселя, а не от развёртки: он непрерывен через швы, своих линий по краю островов нет.
Координаты модели: x — вбок, y — вверх (лоб ~1,74 м, макушка ~1,93), z — вперёд (лицо +0,14, затылок −0,12).
Номера дизайнов (DESIGNS) стабильны: пользователь выбирает по ним.

  python -m fb.mask_designs sheet [--only 1,5,…] [--big 3,7,…]   # листы → game/work/nhl27/out/masks-gen/designs_{1,2}.png
                                                                  # и designs_best.png (--big, крупнее)
  python -m fb.mask_designs build --pick 3,7,… --from 320          # выбранные → masks-gen/cache/…/goaliehelmet_0_<N>_cm.rx2
                                                                  # (N подряд; ставить — kitport put --from …)
"""
import argparse
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from . import mask_gen as G
from . import masks as M

WORK = G.WORK


def _xyz():
    p = G.geometry()["pos"]
    return p[..., 0], p[..., 1], p[..., 2]


def _mix(a, b, t):
    t = np.clip(np.asarray(t, float), 0, 1)[..., None]
    return np.array(a, float) * (1 - t) + np.array(b, float) * t


def _hash3(i, j, k, seed=0):
    h = (i * 73856093) ^ (j * 19349663) ^ (k * 83492791) ^ (seed * 26544357)
    h = (h ^ (h >> 13)) * 1274126177
    return ((h ^ (h >> 16)) & 0xFFFF) / 65535.0


def _noise(scale_mm, seed=0):
    """Плавный шум 0…1 по 3D: решётка с шагом scale_mm, трилинейная интерполяция."""
    x, y, z = _xyz()
    q = np.stack([x, y, z], -1) / (scale_mm / 1000.0)
    i0 = np.floor(q).astype(np.int64)
    f = q - i0
    f = f * f * (3 - 2 * f)
    out = 0.0
    for dx in (0, 1):
        for dy in (0, 1):
            for dz in (0, 1):
                w = (f[..., 0] if dx else 1 - f[..., 0]) * (f[..., 1] if dy else 1 - f[..., 1]) * \
                    (f[..., 2] if dz else 1 - f[..., 2])
                out = out + w * _hash3(i0[..., 0] + dx, i0[..., 1] + dy, i0[..., 2] + dz, seed)
    return out


def _metal(img, amount):
    """Металлик: мягкие блики полосами по высоте (amount 0 — матовый)."""
    if not amount:
        return img
    x, y, z = _xyz()
    band = (0.5 + 0.5 * np.cos((y - 1.70) * 38 + x * 9)) ** 3
    return np.clip(img * (1 - 0.35 * amount) + 255 * 0.35 * amount * band[..., None], 0, 255)


def _fill(c):
    x, y, z = _xyz()
    return np.zeros(x.shape + (3,)) + np.array(c, float)


def d_solid(c, metal=0.0):
    return _metal(_fill(c), metal)


def d_split(c1, c2, metal=0.0):
    """Ретро-двухцвет: верх c1, низ c2, граница чуть ниже лба с наклоном к затылку."""
    x, y, z = _xyz()
    return _metal(_mix(c2, c1, (y - 1.715 + 0.12 * z) > 0), metal)


def d_center_stripe(base, stripe, width_mm=28, edge=None):
    x, y, z = _xyz()
    out = _fill(base)
    w = width_mm / 2000.0
    if edge is not None:
        out[(np.abs(x) < w + 0.004) & (y > 1.70)] = edge
    out[(np.abs(x) < w) & (y > 1.70)] = stripe
    return out


def d_side_stripes(base, stripe, n=3, width_mm=7, gap_mm=6):
    x, y, z = _xyz()
    out = _fill(base)
    ax = np.abs(x)
    for k in range(n):
        lo = 0.018 + k * (width_mm + gap_mm) / 1000.0
        out[(ax > lo) & (ax < lo + width_mm / 1000.0) & (y > 1.70)] = stripe
    return out


def d_diagonal(base, stripe, period_mm=34, duty=0.4):
    x, y, z = _xyz()
    t = ((np.abs(x) * 0.8 + y + 0.6 * z) / (period_mm / 1000.0)) % 1.0
    return _mix(base, stripe, t < duty)


def d_chevrons(base, stripe, period_mm=30, duty=0.35):
    x, y, z = _xyz()
    t = ((z + 1.3 * np.abs(x)) / (period_mm / 1000.0)) % 1.0
    return _mix(base, stripe, (t < duty) & (y > 1.69))


def d_pixel_camo(c1, c2, c3, cell_mm=11, seed=3):
    x, y, z = _xyz()
    s = cell_mm / 1000.0
    h = _hash3(np.floor(x / s).astype(np.int64), np.floor(y / s).astype(np.int64), np.floor(z / s).astype(np.int64), seed)
    out = _fill(c1)
    out[h > 0.45] = c2
    out[h > 0.78] = c3
    return out


def d_camo(c1, c2, c3, scale_mm=38, seed=5):
    n = _noise(scale_mm, seed) * 0.65 + _noise(scale_mm / 2.5, seed + 1) * 0.35
    out = _fill(c1)
    out[n > 0.47] = c2
    out[n > 0.60] = c3
    return out


def d_grid(base, line, cell_mm=16, line_mm=2.2):
    x, y, z = _xyz()
    s, w = cell_mm / 1000.0, line_mm / 1000.0
    gx = np.abs(((x + 1.0) % s) - s / 2) > s / 2 - w / 2
    gy = np.abs(((y + 0.6 * z) % s) - s / 2) > s / 2 - w / 2
    return _mix(base, line, gx | gy)


def d_gradient(top, bottom, metal=0.0):
    x, y, z = _xyz()
    return _metal(_mix(bottom, top, (y - 1.64) / 0.27), metal)


def d_side_fade(front, back):
    x, y, z = _xyz()
    return _mix(back, front, (z + 0.10) / 0.24)


def d_flames(base, flame, tip, seed=7):
    """Пламя языками от подбородка вверх: порог шума, вытянутого по высоте."""
    x, y, z = _xyz()
    n = _noise(22, seed)
    h = (1.80 - y) / 0.14 + (n - 0.5) * 0.9 + 0.25 * np.sin(np.abs(x) * 95 + z * 40)
    out = _fill(base)
    out[h > 0.15] = tip
    out[h > 0.45] = flame
    return out


def d_bolts(base, bolt, n=3):
    """Молнии — зигзаги по куполу от лба к затылку."""
    x, y, z = _xyz()
    out = _fill(base)
    zig = 0.010 * (np.abs(((z * 1000 / 26) % 2) - 1) * 2 - 1)
    for k in range(n):
        x0 = (k - (n - 1) / 2) * 0.045
        out[(np.abs(x - x0 - zig) < 0.0045) & (y > 1.76)] = bolt
    return out


def d_number_panels(base, panel, edge):
    """Номерные зоны: круглые плашки по бокам и прямоугольная сзади (под номер вратаря), без цифр."""
    x, y, z = _xyz()
    out = _fill(base)
    d = np.sqrt((np.abs(x) - 0.10) ** 2 + (y - 1.81) ** 2 + (z + 0.02) ** 2)   # по бокам за ухом: проём лица не задевает
    side = (np.abs(x) > 0.05) & (z < 0.05)
    out[side & (d < 0.036)] = edge
    out[side & (d < 0.030)] = panel
    out[(z < -0.07) & (np.abs(x) < 0.04) & (np.abs(y - 1.80) < 0.035)] = panel
    return out


def d_checks(base, c1, c2, cell_mm=12):
    x, y, z = _xyz()
    s = cell_mm / 1000.0
    out = _fill(base)
    band = (np.abs(x) < 0.03) & (y > 1.70)
    chk = ((np.floor(x / s) + np.floor((z + 0.3 * y) / s)) % 2) == 0
    out[band & chk] = c1
    out[band & ~chk] = c2
    return out


def d_waves(base, wave, period_mm=26):
    x, y, z = _xyz()
    t = np.sin((y + 0.018 * np.sin(z * 60 + np.abs(x) * 40)) / (period_mm / 1000.0) * 2 * np.pi)
    return _mix(base, wave, t > 0.45)


def d_tiger(base, stripe, seed=11):
    x, y, z = _xyz()
    t = np.sin((z + 0.5 * y) * 80 + _noise(30, seed) * 6)
    return _mix(base, stripe, (t > 0.55) & (y > 1.66))


def d_halftone(base, dot, cell_mm=7):
    x, y, z = _xyz()
    s = cell_mm / 1000.0
    fx, fy = ((x + 1.0) % s) / s - 0.5, ((y + 0.5 * z + 1.0) % s) / s - 0.5
    r = np.clip((y - 1.66) / 0.25, 0, 1) * 0.48
    return _mix(base, dot, np.hypot(fx, fy) < r)


def d_hex(base, line, size_mm=14):
    x, y, z = _xyz()
    s = size_mm / 1000.0
    u, v = x / s, (y + 0.5 * z) / s

    def dist(u0, v0):
        cu, cv = np.round(u - u0), np.round((v - v0) / 1.732)
        return np.hypot(u - u0 - cu, (v - v0) - cv * 1.732)
    return _mix(base, line, np.minimum(dist(0, 0), dist(0.5, 0.866)) > 0.46)


STYLES = {f.__name__[2:]: f for f in (d_solid, d_split, d_center_stripe, d_side_stripes, d_diagonal, d_chevrons,
                                       d_pixel_camo, d_camo, d_grid, d_gradient, d_side_fade, d_flames, d_bolts,
                                       d_number_panels, d_checks, d_waves, d_tiger, d_halftone, d_hex)}

BK, WH, SV, GR = (18, 18, 20), (232, 232, 232), (172, 176, 182), (70, 74, 80)
RD, NV, BL, GN, GD = (190, 22, 36), (10, 28, 66), (0, 64, 160), (0, 86, 50), (204, 160, 52)
OR, PU, MR, TL, YL = (232, 106, 20), (78, 36, 128), (112, 16, 38), (0, 128, 138), (240, 200, 40)
# Номер → (стиль, параметры). Номера стабильны (лист 03.11.2026), новые — только в конец.
DESIGNS = {
    1: ("split", dict(c1=SV, c2=BK, metal=0.6)), 2: ("split", dict(c1=RD, c2=BK)), 3: ("split", dict(c1=WH, c2=NV)),
    4: ("center_stripe", dict(base=BK, stripe=SV, width_mm=30, edge=RD)),
    5: ("center_stripe", dict(base=WH, stripe=BL, width_mm=22, edge=NV)),
    6: ("side_stripes", dict(base=NV, stripe=WH)), 7: ("side_stripes", dict(base=RD, stripe=BK, n=2, width_mm=10)),
    8: ("diagonal", dict(base=BK, stripe=GR)), 9: ("diagonal", dict(base=WH, stripe=GN, period_mm=44, duty=0.3)),
    10: ("chevrons", dict(base=BK, stripe=OR)), 11: ("chevrons", dict(base=NV, stripe=GD)),
    12: ("pixel_camo", dict(c1=(54, 60, 52), c2=(92, 100, 84), c3=(28, 30, 28))),
    13: ("pixel_camo", dict(c1=NV, c2=BL, c3=WH, cell_mm=9)),
    14: ("camo", dict(c1=(60, 64, 58), c2=(100, 104, 92), c3=(30, 32, 30))), 15: ("camo", dict(c1=BK, c2=GR, c3=SV)),
    16: ("grid", dict(base=BK, line=RD)), 17: ("grid", dict(base=WH, line=GR, cell_mm=12, line_mm=1.6)),
    18: ("gradient", dict(top=RD, bottom=BK)), 19: ("gradient", dict(top=BL, bottom=NV, metal=0.6)),
    20: ("gradient", dict(top=GD, bottom=BK, metal=0.8)), 21: ("side_fade", dict(front=TL, back=BK)),
    22: ("flames", dict(base=BK, flame=RD, tip=OR)), 23: ("flames", dict(base=NV, flame=BL, tip=WH)),
    24: ("bolts", dict(base=BK, bolt=YL)), 25: ("bolts", dict(base=PU, bolt=WH)),
    26: ("number_panels", dict(base=MR, panel=WH, edge=GD)), 27: ("number_panels", dict(base=GN, panel=WH, edge=BK)),
    28: ("checks", dict(base=BK, c1=WH, c2=BK)), 29: ("waves", dict(base=TL, wave=WH)),
    30: ("tiger", dict(base=OR, stripe=BK)), 31: ("halftone", dict(base=BK, dot=RD)),
    32: ("hex", dict(base=GR, line=BK)), 33: ("solid", dict(c=SV, metal=1.0)), 34: ("solid", dict(c=BK)),
}


def make(num):
    """Дизайн num → RGBA 512²: оболочка — рисунком, ремни, пряжки, подкладка — как у 0/125, отверстия тёмные."""
    style, kw = DESIGNS[num]
    base = G._tex(G.SAMPLE)
    sh = G.geometry()["shell"]
    img = STYLES[style](**kw)
    x, y, z = _xyz()
    rel = 0.9 + 0.1 * np.clip((y - 1.62) / 0.3, 0, 1)        # лёгкое затенение книзу — объём без своей карты нормалей
    out = base.copy()
    out[sh, :3] = (img * rel[..., None])[sh]
    w = G._tex(G.WHITE)
    vents = sh & (G._lum(w) < 0.25)
    out[vents, :3] = w[vents, :3] * 0.6
    out[..., 3] = 255
    return Image.fromarray(np.clip(np.round(out), 0, 255).astype(np.uint8), "RGBA")


def _font(size):
    try:
        return ImageFont.truetype("C:/Windows/Fonts/segoeuib.ttf", size)
    except OSError:
        return ImageFont.load_default()


def cmd_sheet(a):
    os.makedirs(WORK, exist_ok=True)
    nums = [int(x) for x in a.only.split(",")] if a.only else list(DESIGNS)
    big = [int(x) for x in a.big.split(",")] if a.big else []
    m = G.geometry()["mesh"]
    frame = (-0.16, 0.16, 1.58, 1.95)

    def cell(n, width):
        img = make(n)
        img.save(os.path.join(WORK, f"design_{n:02d}.png"))
        ims = [M._render(m, img, ang, frame, width) for ang in (25, 80)]
        c = Image.new("RGB", (2 * (width + 3), ims[0].size[1] + 28), (16, 16, 20))
        c.paste(ims[0], (0, 28))
        c.paste(ims[1], (width + 3, 28))
        ImageDraw.Draw(c).text((6, 2), f"№{n}  {DESIGNS[n][0]}", fill=(255, 220, 140), font=_font(18))
        return c

    def sheet(cells, cols, out):
        W, H = cells[0].size
        o = Image.new("RGB", (cols * (W + 6), ((len(cells) + cols - 1) // cols) * (H + 6)), (0, 0, 0))
        for k, c in enumerate(cells):
            o.paste(c, ((k % cols) * (W + 6), (k // cols) * (H + 6)))
        o.save(out)
        print(out, o.size)
    half = (len(nums) + 1) // 2
    for part, chunk in enumerate((nums[:half], nums[half:]), 1):
        if chunk:
            sheet([cell(n, 170) for n in chunk], 4, os.path.join(WORK, f"designs_{part}.png"))
    if big:
        sheet([cell(n, 300) for n in big], 3, os.path.join(WORK, "designs_best.png"))


def cmd_build(a):
    nums = [int(x) for x in a.pick.split(",") if x]
    bad = [n for n in nums if n not in DESIGNS]
    if bad:
        raise SystemExit(f"нет дизайнов {bad}; есть 1…{max(DESIGNS)}")
    for k, n in enumerate(nums):
        mid = a.start + k
        if not 0 <= mid <= 511:
            raise SystemExit(f"номер маски {mid} вне 0…511")
        q, _ = M.write_rx2(make(n), 0, mid, os.path.join(WORK, "cache"))
        print(f"№{n} ({DESIGNS[n][0]}) → 0/{mid}: {q}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("sheet", help="листы дизайнов с номерами")
    s.add_argument("--only", help="номера через запятую")
    s.add_argument("--big", help="номера через запятую — крупнее, отдельным листом")
    s = sub.add_parser("build", help="выбранные дизайны → .rx2 в раскладке cache:")
    s.add_argument("--pick", required=True, help="номера дизайнов через запятую")
    s.add_argument("--from", dest="start", type=int, required=True, help="первый номер маски (тип 0), дальше подряд")
    a = ap.parse_args()
    return {"sheet": cmd_sheet, "build": cmd_build}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
