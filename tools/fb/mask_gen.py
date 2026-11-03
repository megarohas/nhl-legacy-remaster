"""Стандартные маски вратаря без логотипов для NHL Legacy (03.11.2026, docs/goalie-masks.md, «Стандартные маски»).

Пользователь: «в игре есть дефолтные шлемы разных цветов. Можно ли расширить этот список … Там есть чёрно-серый,
серебристо-чёрный шлем, который мне всегда нравился и подходил любой команде с чёрным в форме. Можно разных цветов в
схожем стиле, а может, в совершенно другом, нагенерить усреднённых». Образец (подтвердил пользователь) — маска 0/125:
купол серебро, низ чёрный с серебряным узором (каталог редактора, запись 6).

Маска — рисунок 512² на модель itech (rendering/goaliehelmet/helmet_0_2, тип 0). Генерируется только оболочка — острова
развёртки купола и затылка (SHELL_UV — площадь острова в развёртке больше, ремни, пряжки и подкладка остаются как в
образце). Стили:
  swoosh   — рисунок 0/125 перекрашен: серебро → light, чёрное → dark; рельеф и блики образца сохраняются (яркость
             текселя внутри своего класса), вентиляционные отверстия (тёмные точки белой маски 0/120) — чёрные;
  stripes  — однотонная оболочка base и две полосы stripe (с тонкой окантовкой trim) от лба к затылку по куполу;
  carbon   — графитовый карбон (саржа 2×2, шаг CARBON_MM);
  gradient — сверху top к низу bottom по высоте модели.
  (03.11.2026: окантовку trim по линии лба у carbon и gradient убрал — на листе она читалась белой чертой поперёк лица,
  координатор: «шов развёртки/край текстуры».)
Во всех стилях вентиляционные отверстия — тёмные (по белой маске 0/120). Варианты — VARIANTS ниже (имя → стиль и цвета),
цвета — sRGB. Номера масок — свободные после 319 (292–319 заняты масками NHL 27, fb/mask_slots.toml); в выбор редактора
выбранные вписываются в список каталога, который читает exe (формат — docs/goalie-masks.md, раздел агента «Порт»).

  python -m fb.mask_gen sheet [--only имя,…]        # лист вариантов (2 ракурса) → game/work/nhl27/out/masks-gen/sheet.png
  python -m fb.mask_gen build --pick имя,… --from 320   # выбранные → goaliehelmet_0_<N>_cm.rx2 (N подряд с --from) в
                                                     # game/work/nhl27/out/masks-gen/cache (kitport put --from …)
Номер маски вратарю — поле exhibitiongoalieequipment.maskid (masktype 0). В выборе редактора маски — каталог образа игры
(87 записей, см. docs/goalie-masks.md): новый номер там не появится без правки exe.
"""
import argparse
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .cas import REPO
from . import kit3d, masks as M

WORK = os.path.join(REPO, "game", "work", "nhl27", "out", "masks-gen")
SAMPLE, WHITE = 125, 120          # образец стиля swoosh и белая маска (отверстия) — тип 0
SHELL_UV = 0.05                   # острова развёртки с площадью больше — оболочка (купол 0,52, затылок 0,08); ремни меньше
CARBON_MM = 9.0                   # шаг плетения карбона, мм
SIZE = 512

# Варианты (03.11.2026): образец 0/125 как есть + те же формы в базовых цветах (пользователь: «разных цветов в схожем
# стиле»), и 4 простых других стиля. light — вместо серебра, dark — вместо чёрного.
VARIANTS = {
    "silver_black": ("swoosh", {"light": (176, 180, 186), "dark": (16, 16, 18)}),
    "red_black": ("swoosh", {"light": (196, 22, 36), "dark": (16, 16, 18)}),
    "blue_silver": ("swoosh", {"light": (176, 180, 186), "dark": (0, 56, 150)}),
    "navy_silver": ("swoosh", {"light": (176, 180, 186), "dark": (8, 24, 60)}),
    "green_silver": ("swoosh", {"light": (176, 180, 186), "dark": (0, 84, 48)}),
    "gold_black": ("swoosh", {"light": (204, 160, 52), "dark": (16, 16, 18)}),
    "orange_black": ("swoosh", {"light": (236, 110, 20), "dark": (16, 16, 18)}),
    "white_black": ("swoosh", {"light": (236, 236, 236), "dark": (16, 16, 18)}),
    "purple_silver": ("swoosh", {"light": (176, 180, 186), "dark": (70, 30, 120)}),
    "burgundy_silver": ("swoosh", {"light": (176, 180, 186), "dark": (110, 14, 36)}),
    "teal_black": ("swoosh", {"light": (0, 132, 140), "dark": (16, 16, 18)}),
    "black_red": ("swoosh", {"light": (16, 16, 18), "dark": (176, 20, 32)}),
    "stripes_navy": ("stripes", {"base": (10, 28, 66), "stripe": (236, 236, 236), "trim": (196, 22, 36)}),
    "stripes_white": ("stripes", {"base": (236, 236, 236), "stripe": (16, 16, 18), "trim": (150, 154, 160)}),
    "carbon": ("carbon", {}),
    "gradient_red": ("gradient", {"top": (200, 24, 38), "bottom": (16, 16, 18)}),
}


def _tex(i):
    import teamart as ta
    import kitpaint as kp
    rw = ta.Rw4(open(M.legacy_file(M.LEG_TEX.format(t=0, i=i)), "rb").read(), "")
    w, h, px = kp.tex_decode(rw, rw.textures[0])
    return np.frombuffer(bytes(px), np.uint8).reshape(h, w, 4).astype(np.float64)


_G = {}


def geometry():
    """Тексели оболочки (маска), 3D-позиция и нормаль каждого текселя развёртки модели itech (SIZE²)."""
    if _G:
        return _G
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    m = M.mesh_legacy(0)
    uv, tri, pos = m["uv"], m["tri"], m["pos"]
    k = np.round(uv * 4096).astype(np.int64)
    _, vid = np.unique(k[:, 0] * 10000 + k[:, 1], return_inverse=True)
    vid = vid.reshape(-1)
    T = vid[tri]
    n = vid.max() + 1
    _, lab = connected_components(coo_matrix((np.ones(len(T) * 3), (T.ravel(), np.roll(T, 1, 1).ravel())), shape=(n, n)),
                                  directed=False)
    tl = lab[T[:, 0]]
    d1, d2 = uv[tri[:, 1]] - uv[tri[:, 0]], uv[tri[:, 2]] - uv[tri[:, 0]]
    area = np.bincount(tl, weights=0.5 * np.abs(d1[:, 0] * d2[:, 1] - d1[:, 1] * d2[:, 0]))
    shell_tri = area[tl] > SHELL_UV
    tid, bar = kit3d.raster_uv(m, SIZE)
    ok = tid >= 0
    t = np.maximum(tid, 0)
    P = (bar[..., :1] * pos[tri[t, 0]] + bar[..., 1:2] * pos[tri[t, 1]] + bar[..., 2:] * pos[tri[t, 2]])
    from scipy import ndimage as ndi
    shell = ok & shell_tri[t]
    shell = ndi.binary_dilation(shell, iterations=2) & ~(ok & ~shell_tri[t])     # запас за край острова (мипы)
    _, (iy, ix) = ndi.distance_transform_edt(~ok, return_indices=True)
    _G.update(shell=shell, pos=P[iy, ix], mesh=m)
    return _G


def _lum(c):
    return c[..., :3] @ np.array([0.299, 0.587, 0.114]) / 255.0


def style_swoosh(light, dark):
    """Рисунок 0/125: серебро → light, чёрное → dark, детали — яркостью внутри класса, отверстия 0/120 — чёрные."""
    s = _tex(SAMPLE)
    L = _lum(s)
    w = np.clip((L - 0.25) / 0.30, 0, 1)
    w = w * w * (3 - 2 * w)                                   # доля «серебра»
    lo = np.clip(0.75 + 2.0 * L, 0.6, 1.4)                    # рельеф чёрного: 0,02…0,2 → 0,79…1,15
    hi = np.clip(L / 0.72, 0.55, 1.35)                        # блик серебра: 0,55…0,95 → 0,76…1,32
    out = (np.array(dark) * lo[..., None]) * (1 - w[..., None]) + (np.array(light) * hi[..., None]) * w[..., None]
    vents = _lum(_tex(WHITE)) < 0.25
    out[vents] = s[vents, :3] * 0.6
    return out


def style_stripes(base, stripe, trim):
    G = geometry()
    p = G["pos"]
    x, y = np.abs(p[..., 0]), p[..., 1]
    out = np.zeros(p.shape[:2] + (3,)) + base
    top = y > 1.74
    band = top & (x > 0.014) & (x < 0.032)
    edge = top & (((x > 0.011) & (x <= 0.014)) | ((x >= 0.032) & (x < 0.035)))
    out[band] = stripe
    out[edge] = trim
    return out


def style_carbon(trim=None):
    G = geometry()
    p = G["pos"]
    s = CARBON_MM / 1000.0
    a, b = np.floor((p[..., 0] + p[..., 1]) / s), np.floor((p[..., 1] - p[..., 0] + p[..., 2]) / s)
    weave = ((a + b) % 2).astype(float)
    fine = 0.5 + 0.5 * np.sin((p[..., 0] + p[..., 1] - p[..., 2]) / s * np.pi * 4)
    g = 34 + 22 * weave + 8 * fine
    out = np.repeat(g[..., None], 3, -1) * np.array([1.0, 1.02, 1.06])
    return out


def style_gradient(top, bottom, trim=None):
    G = geometry()
    y = G["pos"][..., 1]
    t = np.clip((y - 1.66) / (1.90 - 1.66), 0, 1)[..., None]
    out = np.array(bottom) * (1 - t) + np.array(top) * t
    return out


STYLES = {"swoosh": style_swoosh, "stripes": style_stripes, "carbon": style_carbon, "gradient": style_gradient}


def make(name):
    """Вариант name → RGBA SIZE²: оболочка — стилем, остальное (ремни, пряжки, подкладка) — как в образце 0/125."""
    style, kw = VARIANTS[name]
    base = _tex(SAMPLE)
    G = geometry()
    img = STYLES[style](**kw)
    out = base.copy()
    sh = G["shell"]
    out[sh, :3] = img[sh]
    vents = sh & (_lum(_tex(WHITE)) < 0.25)                 # вентиляционные отверстия — тёмные, как у масок EA
    out[vents, :3] = _tex(WHITE)[vents, :3] * 0.6
    out[..., 3] = 255
    return Image.fromarray(np.clip(np.round(out), 0, 255).astype(np.uint8), "RGBA")


def cmd_sheet(a):
    os.makedirs(WORK, exist_ok=True)
    try:
        font = ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", 14)
    except OSError:
        font = ImageFont.load_default()
    names = a.only.split(",") if a.only else list(VARIANTS)
    m = geometry()["mesh"]
    frame = (-0.16, 0.16, 1.58, 1.95)
    cells = []
    for n in names:
        img = make(n)
        img.save(os.path.join(WORK, f"{n}.png"))
        ims = [M._render(m, img, ang, frame, 200) for ang in (25, 75)]
        c = Image.new("RGB", (2 * 203, ims[0].size[1] + 22), (16, 16, 20))
        c.paste(ims[0], (0, 22))
        c.paste(ims[1], (203, 22))
        ImageDraw.Draw(c).text((4, 2), f"{n} ({VARIANTS[n][0]})", fill=(255, 220, 140), font=font)
        cells.append(c)
    cols = 4
    W, H = cells[0].size
    o = Image.new("RGB", (cols * (W + 6), ((len(cells) + cols - 1) // cols) * (H + 6)), (0, 0, 0))
    for k, c in enumerate(cells):
        o.paste(c, ((k % cols) * (W + 6), (k // cols) * (H + 6)))
    out = os.path.join(WORK, "sheet.png")
    o.save(out)
    print(out, o.size)


def cmd_build(a):
    names = [x for x in a.pick.split(",") if x]
    bad = [x for x in names if x not in VARIANTS]
    if bad:
        raise SystemExit(f"нет вариантов {bad}; есть: {', '.join(VARIANTS)}")
    cache = os.path.join(WORK, "cache")
    for k, n in enumerate(names):
        mid = a.start + k
        if not 0 <= mid <= 511:
            raise SystemExit(f"номер маски {mid} вне 0…511")
        q, _ = M.write_rx2(make(n), 0, mid, cache)
        print(f"{n} → 0/{mid}: {q}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("sheet", help="лист вариантов")
    s.add_argument("--only", help="только эти варианты (имена через запятую)")
    s = sub.add_parser("build", help="выбранные варианты → .rx2 в раскладке cache:")
    s.add_argument("--pick", required=True, help="имена вариантов через запятую")
    s.add_argument("--from", dest="start", type=int, required=True, help="первый номер маски (тип 0), дальше подряд")
    a = ap.parse_args()
    return {"sheet": cmd_sheet, "build": cmd_build}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
