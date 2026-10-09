"""Обзор моделей свитеров NHL 24 и NHL Legacy: сравнение сеток и лист «спереди + горловина крупно».

  python -m fb.kit_models stats              # вершины/треугольники/рамки, близость поверхностей и развёрток
  python -m fb.kit_models sheet OUT.png [--tex SEA_NHL24.png] [--tex-legacy SEA_LEGACY.png]

Сетки NHL 24 — res MeshSet из дампа (только для расчёта и картинок), сетки Legacy — rw4mesh (распакованные архивы).
"""
import argparse
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from . import kit3d

N24 = "content/character/skater/player/jersey/{f}/components/player_jersey_{f}_{v}_lod0_mesh"
N24_TIE = "content/character/skater/player/jersey/{f}/components/player_jerseytie_{f}_lod0_mesh"
N24_GOALIE = "content/character/skater/goalie/jersey/{f}/components/goalie_jersey_{f}_notuck_lod0_mesh"
LEG = "rendering/jersey/jersey_{g}_{s}_{h}_{t}_{p}_2.rx2"
LEG_TIE = "rendering/jersey/jerseytie_{g}_{s}_2.rx2"

MODELS = [
    ("NHL 24 adidas (2017+)", "nhl24", N24.format(f="adidas", v="notuck_large"), N24_TIE.format(f="adidas")),
    ("NHL 24 rbk (Reebok Edge)", "nhl24", N24.format(f="rbk", v="notuck_large"), None),
    ("NHL 24 nineties (ретро)", "nhl24", N24.format(f="nineties", v="notuck_large"), None),
    ("Legacy стиль 1 (Edge)", "legacy", LEG.format(g=0, s=1, h=2, t=0, p=1), LEG_TIE.format(g=0, s=1)),
    ("Legacy стиль 0 (ретро)", "legacy", LEG.format(g=0, s=0, h=2, t=0, p=1), LEG_TIE.format(g=0, s=0)),
]


def load(kind, name):
    return kit3d.load_nhl24(name) if kind == "nhl24" else kit3d.load_legacy(name)


def merge(a, b):
    if b is None:
        return a
    n = len(a["pos"])
    return {"pos": np.vstack([a["pos"], b["pos"]]), "uv": np.vstack([a["uv"], b["uv"]]),
            "nrm": np.vstack([a["nrm"], b["nrm"]]), "tri": np.vstack([a["tri"], b["tri"] + n])}


def checker(size=1024, cells=16):
    y, x = np.mgrid[0:size, 0:size]
    c = ((x // (size // cells)) + (y // (size // cells))) % 2
    img = np.zeros((size, size, 4))
    img[..., 0] = np.where(c, 205, 150)
    img[..., 1] = np.where(c, 205, 150)
    img[..., 2] = np.where(c, 210, 160)
    img[..., 3] = 255
    # оси развёртки: u — красным, v — зелёным по краям клеток
    img[(x % (size // cells)) < 3, 0] = 220
    img[(y % (size // cells)) < 3, 1] = 200
    return img


def cmd_sheet(a):
    try:
        font = ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", 26)
    except OSError:
        font = ImageFont.load_default()
    tex_chk = checker()
    tex24 = kit3d.load_tex(a.tex) if a.tex else None
    texl = kit3d.load_tex(a.tex_legacy) if a.tex_legacy else None
    W, WN = 560, 560
    rows = []
    for label, kind, name, tie in MODELS:
        try:
            m = load(kind, name)
            t = None
            if tie:
                try:
                    t = load(kind, tie)
                except Exception:  # noqa: BLE001
                    t = None
            mm = merge(m, t)
        except Exception as e:  # noqa: BLE001
            print(label, "нет:", e)
            continue
        tex = tex24 if kind == "nhl24" else texl
        row = [kit3d.render(mm, tex_chk, "front", W, ss=2),
               kit3d.render(mm, tex_chk, "front", WN, frame=kit3d.NECK, ss=2)]
        if tex is not None:
            row += [kit3d.render(mm, tex, "front", WN, frame=kit3d.NECK, ss=2)]
        rows.append((label + (" + шнуровка" if t is not None else ""), row))
    pad, top = 12, 40
    h = max(im.size[1] for _, r in rows for im in r)
    wsum = max(sum(im.size[0] for im in r) + pad * (len(r) + 1) for _, r in rows)
    sheet = Image.new("RGB", (wsum, len(rows) * (h + top) + pad), (30, 30, 34))
    d = ImageDraw.Draw(sheet)
    for i, (label, r) in enumerate(rows):
        y = pad + i * (h + top)
        d.text((pad, y), label, fill=(235, 235, 235), font=font)
        x = pad
        for im in r:
            sheet.paste(im, (x, y + top - 6))
            x += im.size[0] + pad
    sheet.save(a.out)
    print(a.out, sheet.size)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("sheet")
    s.add_argument("out")
    s.add_argument("--tex")
    s.add_argument("--tex-legacy")
    c = sub.add_parser("collars", help="одна текстура свитера Legacy на всех вариантах сетки стиля 1")
    c.add_argument("tex")
    c.add_argument("out")
    a = ap.parse_args()
    if a.cmd == "sheet":
        return cmd_sheet(a)
    if a.cmd == "collars":
        return cmd_collars(a)



# ---------------------------------------------------------------- гибрид на всех вариантах сетки Legacy

COLLAR_ROWS = [
    ("jersey_0_1_2_0_1_2", None, "полевой, без заправки, с наплечниками — основной вариант (заправка 0)"),
    ("jersey_0_1_2_0_0_2", None, "полевой, без наплечников (shoulderpads 0)"),
    ("jersey_0_1_2_1_1_2", None, "заправка 1 (jerseytuck)"),
    ("jersey_0_1_2_2_1_2", None, "заправка 2"),
    ("jersey_0_1_2_3_1_2", None, "заправка 3"),
    ("jersey_0_1_2_0_1_2", "jerseytie_0_1_2", "с шнуровкой ворота (hastie 1)"),
    ("jersey_1_1_0_0_0_2", None, "вратарь, стиль 1"),
    ("jersey_1_1_0_0_0_2", "jerseytie_1_1_2", "вратарь, стиль 1, с шнуровкой"),
]


def cmd_collars(a):
    try:
        font = ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", 24)
    except OSError:
        font = ImageFont.load_default()
    tex = kit3d.load_tex(a.tex)
    W = 520
    rows = []
    for mesh, tie, note in COLLAR_ROWS:
        m = kit3d.load_legacy(f"rendering/jersey/{mesh}.rx2")
        if tie:
            m = merge(m, kit3d.load_legacy(f"rendering/jersey/{tie}.rx2"))
        row = [kit3d.render(m, tex, "front", W, ss=2), kit3d.render(m, tex, "front", W, frame=kit3d.NECK, ss=2),
               kit3d.render(m, tex, "back", W, frame=(-0.21, 0.21, 1.42, 1.76), ss=2)]
        rows.append((f"{mesh}{(' + ' + tie) if tie else ''} — {note}", row))
    pad, top = 12, 38
    h = rows[0][1][0].size[1]
    wsum = sum(im.size[0] for im in rows[0][1]) + pad * 4
    sheet = Image.new("RGB", (wsum, len(rows) * (h + top) + pad), (30, 30, 34))
    d = ImageDraw.Draw(sheet)
    for i, (label, r) in enumerate(rows):
        y = pad + i * (h + top)
        d.text((pad, y), label, fill=(235, 235, 235), font=font)
        x = pad
        for im in r:
            sheet.paste(im, (x, y + top - 6))
            x += im.size[0] + pad
    sheet.save(a.out)
    print(a.out, sheet.size)


if __name__ == "__main__":
    sys.exit(main())
