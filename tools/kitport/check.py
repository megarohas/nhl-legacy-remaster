"""Лист проверки форм слота (подход C) на сетке Edge слота: по строке на форму — ворот спереди и в 3/4, рельеф без
цвета спереди и сзади, сбоку — контур зон номеров на рукаве, шрифт на цвете свитера под фамилией, превью меню. Плюс замер щита NHL по середине переда (у ворота без шнуровки: у ворота со
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
    ("zones", 90, 300, (-0.35, 0.35, 1.30, 1.75)),     # сбоку: контур зон номеров на рукаве (карта номеров)
)
SLEEVE_ZONES = (2, 3)              # зоны номеров на рукавах (docs/kitport.md §2.4)


def zone_outline(t, name_png, zones=SLEEVE_ZONES, color=(255, 220, 40)):
    """Текстура свитера с контуром зон карты номеров (R, G > 128, B = зона) — видно, где игра рисует номер."""
    from PIL import Image
    from scipy import ndimage as ndi
    a = np.asarray(Image.open(name_png).convert("RGBA").resize(t.shape[1::-1], Image.NEAREST))
    out = t.copy()
    for z in zones:
        m = (a[..., 0] > 128) & (a[..., 1] > 128) & (a[..., 2] == z)
        out[m & ~ndi.binary_erosion(m, iterations=3), :3] = color
    return out


def font_panel(d, t, h):
    """Атлас шрифта (буквы фамилии и крупные цифры, верх атласа) на цвете свитера под фамилией (зона 0 карты номеров):
    видно обводку и читаемость фамилии."""
    from PIL import Image
    f = Image.open(os.path.join(d, "font_cm.png")).convert("RGBA")
    a = np.asarray(Image.open(os.path.join(d, "name_cm.png")).convert("RGBA").resize(t.shape[1::-1], Image.NEAREST))
    z = (a[..., 0] > 128) & (a[..., 1] > 128) & (a[..., 2] == 0)
    c = tuple(int(x) for x in np.median(t[z][:, :3], 0)) if z.any() else (128, 128, 128)
    crop = f.crop((0, 0, f.size[0], int(f.size[1] * 0.56)))
    bg = Image.new("RGBA", crop.size, c + (255,))
    bg.alpha_composite(crop)
    return bg.convert("RGB").resize((round(crop.size[0] * h / crop.size[1]), h))


def shield_y(M, t):
    """Щит по середине переда: (низ, верх) серебристого и низ красной кромки ворота над ним, м (None — нет)."""
    from fb import kit3d
    tid, bar = kit3d.raster_uv(M, t.shape[0])
    ys, xs = np.nonzero(tid >= 0)
    P = (bar[ys, xs][:, :, None] * M["pos"][M["tri"][tid[ys, xs]]]).sum(1)
    c = t[ys, xs, :3].astype(float)
    sel = (np.abs(P[:, 0]) < 0.003) & (P[:, 2] > 0.05) & (P[:, 1] > 1.59) & (P[:, 1] < 1.66)
    yy, cc = P[sel, 1], c[sel]
    sil = (cc.mean(1) > 110) & (np.abs(cc[:, 0] - cc[:, 1]) < 40) & (cc.max(1) - cc.min(1) < 14)   # серый: не смесь кромки с тканью
    # кромка ворота — сплошная полоса цвета верха (верхние 2 мм середины переда) сверху вниз: окно 1 мм с шагом 0,25 мм
    # (точек мало — по одной-две на полмиллиметра), конец — первое окно, где цвета кромки меньше половины. У NJD кромка
    # красная, у TBL дома — белая (21.10: белую кромку замер принимал за щит — «щит 1,622–1,647», кромки нет)
    top = yy.max() if len(yy) else 0.0
    trim_c = np.median(cc[yy > top - 0.002], 0) if len(yy) else np.zeros(3)
    in_trim = np.abs(cc - trim_c).max(1) < 45
    b = top
    while b > 1.59:
        m = (yy <= b) & (yy > b - 0.001)
        if m.sum() >= 3 and in_trim[m].mean() < 0.5:
            break
        b -= 0.00025
    above = in_trim & (yy >= b)
    edge = float(yy[above].min()) if above.any() else top
    red = in_trim & (yy >= edge) & (yy > 1.63)
    if red.any():                                      # выше низа кромки щита нет (там — кромка и её край)
        sil &= (yy < edge) & ~in_trim                  # и не цвета кромки: у белой кромки её край — тоже «серебро»
    low = (yy > 1.59) & (yy < 1.60)                    # ткань под щитом (у белой — тоже «серебро»: TBL выезд)
    if low.any():
        fab = np.median(cc[low], 0)
        sil &= np.abs(cc - fab).max(1) > 20
        # край кромки — смесь цвета кромки и ткани: у чёрной кромки на белом (BOS выезд, 21.10) он серый, и замер
        # принимал его за верх щита («до кромки 1 мм» при 4 мм). Не щит: до 2 мм под кромкой и цвет на отрезке
        # «кромка — ткань» (у цветной кромки смесь не серая — MIN, NJD, TBL не меняются)
        seg = fab - trim_c
        t = np.clip(((cc - trim_c) @ seg) / max(float(seg @ seg), 1e-6), 0, 1)
        mix = np.linalg.norm(cc - (trim_c + t[:, None] * seg), axis=1) < 12
        sil &= ~(mix & (yy > edge - 0.002))
    if not sil.any():
        return None, None, float(yy[red].min()) if red.any() else None
    s = np.sort(yy[sil])[::-1]                         # сверху вниз до первого разрыва: светлая ткань ниже — не щит
    gap = np.nonzero(-np.diff(s) > 0.004)[0]         # внутри щита — тёмные буквы NHL (до 3 мм)
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
                "relief": {"pos": pos, "nrm": nrm, "uv": uv, "tri": tri, "tex": gray, "nmap": nm, "twosided": True},
                "zones": {"pos": pos, "nrm": nrm, "uv": uv, "tri": tri, "twosided": True,
                          "tex": zone_outline(t, os.path.join(d, "name_cm.png"))}}
        ims = [S.render([dict(part[what])], np.radians(ang), w, frame=fr) for what, ang, w, fr in VIEWS]
        h = max(i.size[1] for i in ims)
        ims.append(font_panel(d, t, h))
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
