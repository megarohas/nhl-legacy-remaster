"""Лист проверки форм слота (подход C) на сетке Edge слота: по строке на форму — ворот спереди и в 3/4, рельеф без
цвета спереди и сзади, превью меню. Плюс замер щита NHL по середине переда (у ворота без шнуровки: у ворота со
шнуровкой щит на вставке того же цвета, что кромка). docs/kitport.md §12.3, п. 6.

    python -m kitport check [--clubs MIN,NJD] [--out FILE]

Что смотреть: щит (поля сверху до кромки и снизу), края кокетки на плече и сбоку, швы у ворота («отросточки» у ворота
без шнуровки), черта поперёк груди на рельефе (стык на 1,44–1,52 м).
"""
import datetime
import os
import sys

import numpy as np

from . import core

VIEWS = (                          # (что, угол вокруг оси тела, ширина px, рамка x0, x1, y0, y1 в м)
    ("color", 0, 360, (-0.12, 0.12, 1.56, 1.70)),
    ("color", 35, 300, (-0.14, 0.14, 1.56, 1.70)),
    ("relief", 0, 420, (-0.32, 0.32, 1.38, 1.74)),
    ("relief", 180, 420, (-0.32, 0.32, 1.38, 1.74)),
)


def shield_y(M, t):
    """Щит по середине переда: (низ, верх) серебристого и низ красной кромки ворота над ним, м (None — нет)."""
    from fb import kit3d
    tid, bar = kit3d.raster_uv(M, t.shape[0])
    ys, xs = np.nonzero(tid >= 0)
    P = (bar[ys, xs][:, :, None] * M["pos"][M["tri"][tid[ys, xs]]]).sum(1)
    c = t[ys, xs, :3].astype(float)
    sel = (np.abs(P[:, 0]) < 0.003) & (P[:, 2] > 0.05) & (P[:, 1] > 1.59) & (P[:, 1] < 1.66)
    yy, cc = P[sel, 1], c[sel]
    sil = (cc.mean(1) > 110) & (np.abs(cc[:, 0] - cc[:, 1]) < 40)
    red = (cc[:, 0] > cc[:, 1] + 60) & (cc[:, 0] > 100) & (yy > 1.63)
    if not sil.any():
        return None, None, float(yy[red].min()) if red.any() else None
    s = np.sort(yy[sil])[::-1]                         # сверху вниз до первого разрыва: светлая ткань ниже — не щит
    gap = np.nonzero(-np.diff(s) > 0.0015)[0]
    lo = float(s[gap[0]] if len(gap) else s[-1])
    return lo, float(s[0]), float(yy[red].min()) if red.any() else None


def cmd_check(a):
    os.environ.setdefault("PHOTOS_SOURCE", "nhl24")     # scans24 (рендер) читает его при импорте
    sys.path.insert(0, core.TOOLS)
    import scans24 as S
    from PIL import Image, ImageDraw, ImageFont
    from fb import edge_kit as E
    font = ImageFont.truetype(os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", "segoeui.ttf"), 13)
    collar = {c: p.get("collar", "lace") for c, p in E.club_profiles().items()}
    src = core.slot_kits_dir()
    kits = sorted(k for k in os.listdir(src) if os.path.isdir(os.path.join(src, k)))
    if a.clubs:
        kits = [k for k in kits if k.split("_")[0] in a.clubs.split(",")]
    if not kits:
        print(f"нет собранных форм в {src}" + (f" для {a.clubs}" if a.clubs else "") + " — сначала build --stages kit,slot")
        return 1
    M = E.mesh_for(0, 1, 2)            # полевой, размер 0, lod 2 — сетка слота
    pos, uv, tri = M["pos"], M["uv"], M["tri"]
    nrm = S.weld_normals(pos, tri, S.weld_ids(pos))
    gray = np.full((1024, 1024, 4), (170, 170, 170, 255), np.uint8)
    rows = []
    for kit in kits:
        d = os.path.join(src, kit)
        t = np.asarray(Image.open(os.path.join(d, "jersey_cm.png")).convert("RGBA"))
        nm = np.asarray(Image.open(os.path.join(d, "jersey_nm.png")).convert("RGB").resize(t.shape[1::-1])).astype(np.float64)
        part = {"color": {"pos": pos, "nrm": nrm, "uv": uv, "tri": tri, "tex": t, "twosided": True},
                "relief": {"pos": pos, "nrm": nrm, "uv": uv, "tri": tri, "tex": gray, "nmap": nm, "twosided": True}}
        ims = [S.render([dict(part[what])], np.radians(ang), w, frame=fr) for what, ang, w, fr in VIEWS]
        fe = os.path.join(d, "fe.png")
        if os.path.exists(fe):
            im = Image.open(fe).convert("RGB")
            h = max(i.size[1] for i in ims)
            ims.append(im.resize((round(im.size[0] * h / im.size[1]), h)))
        if collar.get(kit.split("_")[0], "lace") == "lace":
            note = "ворот со шнуровкой: щит на вставке, замер — на глаз"
        else:
            lo, hi, edge = shield_y(M, t)
            note = (f"щит {lo:.3f}–{hi:.3f} м" if lo else "щит не найден") + \
                   (f", до кромки {(edge - hi) * 1000:.0f} мм" if lo and edge else "")
        r = Image.new("RGB", (sum(i.size[0] + 4 for i in ims), max(i.size[1] for i in ims) + 20), (24, 24, 28))
        ImageDraw.Draw(r).text((4, 1), f"{kit}   {note}", fill=(255, 220, 140), font=font)
        x = 0
        for i in ims:
            r.paste(i, (x, 20))
            x += i.size[0] + 4
        rows.append(r)
        print(f"{kit}: {note}")
    sheet = Image.new("RGB", (max(r.size[0] for r in rows), sum(r.size[1] for r in rows)), (10, 10, 12))
    y = 0
    for r in rows:
        sheet.paste(r, (0, y))
        y += r.size[1]
    out = a.out or os.path.join(core.COMPARE, f"check-{datetime.datetime.now():%Y%m%d-%H%M}.png")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    sheet.save(out)
    print("лист →", out)
    return 0
