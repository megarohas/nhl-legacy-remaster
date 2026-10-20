"""Листы «было | стало» по снимку kitport snapshot: спина у ворота (надпись), перед (герб, буква капитана — зоны 5 и 7
карты номеров), плечи, вся развёртка; для каждой формы слота — строка «было | стало»."""
import datetime
import os

import numpy as np
from PIL import Image, ImageDraw

from . import core

# Рамки на развёртке свитера Legacy (u0, v0, u1, v1; 1024²) — docs/kitport.md, «Развёртка»
BACK_NECK = (0.44, 0.395, 0.56, 0.44)     # сзади у ворота: место Reebok / своей надписи (на развёртке — вверх ногами)
FRONT = (0.32, 0.47, 0.70, 0.90)          # грудь: щит NHL, герб, буква капитана
SHOULDERS = (0.29, 0.39, 0.72, 0.53)      # плечи: плечевые нашивки, кокетка, ворот сзади
LETTER_ZONES = (5, 7)


def zones(name_png):
    a = np.asarray(Image.open(name_png).convert("RGBA")).astype(int)
    out = {}
    for z in LETTER_ZONES:
        ys, xs = np.nonzero((a[..., 0] > 128) & (a[..., 1] > 128) & (a[..., 2] == z))
        if len(xs):
            h, w = a.shape[:2]
            out[z] = (xs.min() / w, ys.min() / h, (xs.max() + 1) / w, (ys.max() + 1) / h)
    return out


def _img(d, f):
    p = os.path.join(d, f + ".png")
    return Image.open(p).convert("RGB").resize((1024, 1024)) if os.path.exists(p) else None


def _crop(im, box, k):
    c = im.crop(tuple(int(round(x * 1024)) for x in box))
    return c.resize((int(c.size[0] * k), int(c.size[1] * k)), Image.NEAREST if k >= 4 else Image.LANCZOS)


def tiles(d):
    """Плитки одной формы из папки d (jersey_cm/nm, name_cm)."""
    cm, nm = _img(d, "jersey_cm"), _img(d, "jersey_nm")
    if cm is None:
        return []
    out = [_crop(cm, BACK_NECK, 5).transpose(Image.ROTATE_180)]
    if nm is not None:
        out.append(_crop(nm, BACK_NECK, 5).transpose(Image.ROTATE_180))
    fr = cm.copy()
    if os.path.exists(os.path.join(d, "name_cm.png")):
        dr = ImageDraw.Draw(fr)
        for z, b in zones(os.path.join(d, "name_cm.png")).items():
            dr.rectangle([b[0] * 1024, b[1] * 1024, b[2] * 1024, b[3] * 1024], outline=(255, 0, 255), width=2)
            dr.text((b[0] * 1024 + 3, b[1] * 1024 + 2), str(z), fill=(255, 0, 255))
    out.append(_crop(fr, FRONT, 1.4))
    out.append(_crop(cm, SHOULDERS, 1.6))
    out.append(cm.resize((512, 512), Image.LANCZOS))
    return out


def cmd_sheet(a):
    before = a.before or core.latest_snapshot()
    if not before or not os.path.isdir(before):
        raise SystemExit("нет снимка «было» — python -m kitport snapshot (до сборки)")
    now = core.slot_kits_dir()
    kits = sorted(k for k in os.listdir(before) if os.path.isdir(os.path.join(before, k)))
    rows = []
    for k in kits:
        for label, d in (("было", os.path.join(before, k)), ("стало", os.path.join(now, k))):
            t = tiles(d)
            if t:
                rows.append((f"{k}: {label}", t))
    if not rows:
        raise SystemExit("нечего сравнивать")
    pad, head = 10, 22
    W = max(sum(t.size[0] for t in r) + pad * (len(r) - 1) for _, r in rows)
    H = sum(max(t.size[1] for t in r) + head for _, r in rows) + pad * len(rows)
    sheet = Image.new("RGB", (W, H), (56, 56, 60))
    dr = ImageDraw.Draw(sheet)
    from .uvmap import font
    f = font(16)
    y = 0
    for label, r in rows:
        dr.text((4, y + 2), label, fill=(235, 235, 235), font=f)
        y += head
        x = 0
        for t in r:
            sheet.paste(t, (x, y))
            x += t.size[0] + pad
        y += max(t.size[1] for t in r) + pad
    out = a.out or os.path.join(core.COMPARE, f"sheet-{datetime.datetime.now():%Y%m%d-%H%M}.png")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    sheet.save(out)
    print(f"лист: {out} ({sheet.size[0]}×{sheet.size[1]}), «было» — {before}")
    return 0
