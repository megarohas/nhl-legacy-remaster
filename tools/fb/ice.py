"""Центр льда NHL 24 → формат NHL Legacy (centerlogo_<art>_cm, 1024²) для 32 клубов. Только офлайн.

У NHL 24 (content/worlds/rink/textures/centerlogo/ice_centerlogo_<N>_color, 1024² BC7, N — номер клуба EA) и у EA в
Legacy одна геометрия круга: синее кольцо r ≈ 380 на 1024² (NHL 24 r 377–383, цвет 0,50,160; Legacy 380,5–385,5,
0,56,165). Основа Legacy (как у EA, docs/logos-arenas.md): диск льда (231,233,231) r ≤ 388, кольцо, полоса x 494–529
прозрачная (под ней красная линия ice_cline). Поверх основы — картинка NHL 24 как есть (логотип и надпись арены за
кольцом; ляжет ли надпись за диском r > 388 в игре — проверить в игре).

  python -m fb.ice build         -> game/work/nhl24/out/ice/centerlogo_<КОД>.png (+ _onice.png — превью на льду)
  python -m fb.ice sheet         -> game/work/nhl24/compare/ice_center_32.png (Legacy сейчас | NHL 24 → Legacy)
"""
import argparse
import os
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .cas import REPO
from .kit_batch import CLUBS

NHL24 = os.path.join(REPO, "game", "work", "nhl24")
SRC = os.path.join(NHL24, "extract", "ice", "worlds", "rink", "textures", "centerlogo")
OUT = os.path.join(NHL24, "out", "ice")
LEGACY_BIG = os.path.join(REPO, "game", "other", "legacy", "big")
OURS = os.path.join(REPO, "game", "work", "legacy-data", "out", "rendering", "icesurface")
EA_INDEX = {"vegas": 32, "seattle": 33}  # у остальных номер EA = artid Legacy (0…29)
H = 1024


def legacy_base():
    yy, xx = np.mgrid[0:H, 0:H]
    r = np.hypot(xx - 511.5, yy - 511.5)
    base = np.zeros((H, H, 4))
    base[r <= 388] = [231, 233, 231, 255]
    base[(r >= 380.5) & (r <= 385.5)] = [0, 56, 165, 255]
    return base, r


def convert(n24):
    base, r = legacy_base()
    a = n24[..., 3:4] / 255.0
    out = base.copy()
    out[..., :3] = base[..., :3] * (1 - a) + n24[..., :3] * a
    out[..., 3] = np.maximum(base[..., 3], n24[..., 3])
    stripe = np.zeros((H, H), dtype=bool)
    stripe[:, 494:530] = True
    out[..., 3] = np.where(stripe & (r <= 388), 0, out[..., 3])
    return out


def on_ice(img):
    ice = np.zeros((H, H, 3))
    ice[:] = [226, 230, 232]
    ice[:, 494:530] = [200, 30, 40]
    a = img[..., 3:4] / 255.0
    return Image.fromarray((ice * (1 - a) + img[..., :3] * a).astype(np.uint8))


def legacy_current(art):
    """Нынешний центр льда Legacy: наш (SEA/VGK — game/work/legacy-data/out) или из архивов игры."""
    rel = os.path.join("rendering", "icesurface", f"centerlogo_{art}_cm.rx2")
    for p in [os.path.join(OURS, f"centerlogo_{art}_cm.rx2")] + [os.path.join(LEGACY_BIG, d, rel) for d in
                                                                 sorted(os.listdir(LEGACY_BIG))]:
        if os.path.exists(p):
            png = os.path.join(OUT, "_legacy", f"centerlogo_{art}.png")
            if not os.path.exists(png):
                os.makedirs(os.path.dirname(png), exist_ok=True)
                subprocess.run([sys.executable, os.path.join(REPO, "tools", "teamart.py"), "decode", p, png],
                               check=True, capture_output=True)
            return np.asarray(Image.open(png).convert("RGBA")).astype(np.float64)
    return None


def cmd_build(a):
    os.makedirs(OUT, exist_ok=True)
    for club, art, code in CLUBS:
        n = EA_INDEX.get(club, art)
        p = os.path.join(SRC, f"ice_centerlogo_{n}_color.png")
        if not os.path.exists(p):
            print(code, "нет чанка")
            continue
        img = convert(np.asarray(Image.open(p).convert("RGBA")).astype(np.float64))
        Image.fromarray(img.astype(np.uint8)).save(os.path.join(OUT, f"centerlogo_{code}.png"))
        on_ice(img).save(os.path.join(OUT, f"centerlogo_{code}_onice.png"))
        print(code, f"NHL 24 #{n} -> centerlogo_{art}_cm")


def cmd_sheet(a):
    try:
        font = ImageFont.truetype("C:/Windows/Fonts/segoeuib.ttf", 18)
    except OSError:
        font = ImageFont.load_default()
    S, cols, pad, top = 210, 4, 10, 26
    rows = (len(CLUBS) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * (2 * S + 3 * pad), rows * (S + top + pad) + pad), (30, 30, 34))
    d = ImageDraw.Draw(sheet)
    for i, (club, art, code) in enumerate(CLUBS):
        x = pad + (i % cols) * (2 * S + 3 * pad)
        y = pad + (i // cols) * (S + top + pad)
        d.text((x, y), f"{code}: Legacy сейчас  |  из NHL 24", fill=(235, 235, 235), font=font)
        cur = legacy_current(art)
        if cur is not None:
            sheet.paste(on_ice(cur).resize((S, S), Image.LANCZOS), (x, y + top))
        newp = os.path.join(OUT, f"centerlogo_{code}_onice.png")
        if os.path.exists(newp):
            sheet.paste(Image.open(newp).resize((S, S), Image.LANCZOS), (x + S + pad, y + top))
        else:
            d.text((x + S + pad + 20, y + top + S // 2), "нет чанка", fill=(220, 130, 130), font=font)
    out = os.path.join(NHL24, "compare", "ice_center_32.png")
    sheet.save(out)
    print(out, sheet.size)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("build")
    sub.add_parser("sheet")
    a = ap.parse_args()
    return {"build": cmd_build, "sheet": cmd_sheet}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
