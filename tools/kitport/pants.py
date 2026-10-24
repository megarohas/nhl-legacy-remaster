"""Нашивки шорт крупно (наша форма слота, pant = "source"): цвет и рельеф без цвета у нашего герба и щита NHL и у мест
герба и щита образца Legacy — совпадает ли рельеф (pant_nm) с нашивками (pant_cm). С --before — строки «было» из снимка
(kitport snapshot: pant_nm, pant_sm с 23.10) или любой папки <КЛУБ>_<форма>/pant_nm.png. Шорты — на сетке полевых в
игре (fb.pant_decals.GAME_MESH; до 24.10 — на сетке вратаря pilot.PANT_L, где нашивки стояли иначе, чем в игре).

    python -m kitport pants --clubs DET                     # лист на форму: герб — спереди и ±30°, щит — сзади и ±30°
    python -m kitport pants --clubs DET,BOS --kits home --before ../game/work/nhl24/compare/kitport/<снимок>

Зачем (23.10, пользователь, DET: «логотип на трусах стоит выше и сбоку относительно рельефного места»): рельеф шорт
был образца — со своим гербом EA на своём месте; `kitport present` на всю фигуру этого не показывает. Под листом —
замеры fb.pant_decals.relief_check (те же, что в `kitport audit`). Лист — compare/kitport/pants-<КЛУБ>_<форма>-<дата>.png.
"""
import datetime
import math
import os
import sys

import numpy as np

from . import core

VIEWS = (0, 30, -30)       # град: спереди и повёрнуто в обе стороны (герб на любой ноге — к камере)
BACK_VIEWS = (180, 150, 210)   # град: щит NHL сзади (24.10: наш щит ниже рамки EA — рельеф щита образца стирается)
HALF = (0.10, 0.09)        # м: полкадра по x и y вокруг центра герба


def sheet(club, kit, d, before, width):
    os.environ.setdefault("PHOTOS_SOURCE", "nhl24")     # scans24 (рендер) читает его при импорте
    sys.path.insert(0, core.TOOLS)
    import scans24 as S
    from PIL import Image, ImageDraw, ImageFont
    from scipy import ndimage as ndi
    from fb import edge_kit as E, kit3d, pilot, pant_decals as PD
    E.use_club(club)
    spec = E.SLOT_KITS[kit]
    tpl = os.path.join(E.WORK, "cur_kits", spec["legacy"])
    masks = os.path.join(E.KITS_OUT, f"{club}_{kit}", PD.MASKS)
    pL = PD.game_mesh()[0]                              # шорты полевых в игре (24.10: не вратаря pilot.PANT_L)
    cm = np.asarray(Image.open(os.path.join(d, "pant_cm.png")).convert("RGB"))
    AA = (np.asarray(Image.open(masks).convert("RGB")) / 255.0 if os.path.exists(masks)
          else np.zeros(cm.shape[:2] + (3,)))
    centers, ours = [], []
    for ch, what, views in ((0, "наш герб", VIEWS), (1, "наш щит NHL", BACK_VIEWS)):
        lab, n = ndi.label(ndi.binary_dilation(AA[..., ch] > 0.3, iterations=6))   # звёзды WSH — одна нашивка
        for i in range(1, n + 1):
            c = PD._center3d((lab == i) & (AA[..., ch] > 0.3))
            if c is not None:
                ours.append(c)
                centers.append((what, c, views))
    for f in PD.template_patches(np.asarray(Image.open(os.path.join(tpl, "pant_cm.png")).convert("RGB"))):
        c = PD._center3d(f["mask"])
        if c is not None and all(np.linalg.norm(c - o) > 0.05 for o in ours):
            what = "щита" if f["slot"] == "back" else "герба"
            centers.append((f"место {what} образца {spec['legacy']} ({f['slot']}{', рамка EA' if f.get('box') else ''})",
                            c, BACK_VIEWS if f["slot"] == "back" else VIEWS))
    if not centers:
        return None, "нашивок нет ни у нас, ни у образца"
    states = ([("было", before)] if before and os.path.exists(os.path.join(before, "pant_nm.png")) else []) + [("стало", d)]
    font = ImageFont.truetype(os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", "segoeui.ttf"), 13)
    rows = []
    for what, c, views in centers:
        for tag, sd in states:
            nmap = np.asarray(Image.open(os.path.join(sd, "pant_nm.png")).convert("RGB")).astype(np.float64)
            ims = []
            for grey in (False, True):
                tex = (np.full(cm.shape[:2] + (4,), 170, np.float32) if grey else
                       np.dstack([cm, np.full(cm.shape[:2], 255)]).astype(np.float32))
                part = dict(pL, tex=tex, twosided=True, nmap=nmap)
                for ang in views:
                    cr = S.rot(c[None], math.radians(ang))[0]
                    fr = (cr[0] - HALF[0], cr[0] + HALF[0], cr[1] - HALF[1], cr[1] + HALF[1])
                    ims.append(S.render([part], math.radians(ang), width, frame=fr))
            rows.append((f"{club} {kit} — {tag}: {what}; цвет и рельеф без цвета, {', '.join(f'{v}°' for v in views)}",
                         ims))
    w, h = rows[0][1][0].size
    note = PD.relief_check(tpl, d, masks)
    lines = list(note[0]) or ["relief_check: чисто"]
    lines.append(f"замеры: {note[1]}")
    out = Image.new("RGB", (len(rows[0][1]) * (w + 4), len(rows) * (h + 20) + 18 * len(lines) + 6), (10, 10, 12))
    dr = ImageDraw.Draw(out)
    for r, (t, ims) in enumerate(rows):
        dr.text((4, r * (h + 20) + 2), t, fill=(255, 220, 140), font=font)
        for i, im in enumerate(ims):
            out.paste(im, (i * (w + 4), r * (h + 20) + 18))
    for i, t in enumerate(lines):
        dr.text((4, len(rows) * (h + 20) + 4 + 18 * i), t, fill=(220, 220, 220), font=font)
    return out, "; ".join(note[0]) or "чисто"


def cmd_pants(a):
    from fb import edge_kit as E
    clubs = [c for c in a.clubs.split(",") if c]
    kits = [k for k in a.kits.split(",") if k]
    profs = E.club_profiles()
    n = 0
    for code in clubs:
        for kit in kits:
            d = os.path.join(core.slot_kits_dir(), f"{code}_{kit}")
            spec = profs.get(code, {}).get("slot", {}).get(kit)
            if spec is None or not os.path.exists(os.path.join(d, "pant_cm.png")):
                print(f"{code} {kit}: нет в профиле или слот не собран ({d})")
                continue
            if spec.get("pant", "legacy") != "source":
                print(f"{code} {kit}: pant = \"{spec.get('pant', 'legacy')}\" — шорты образца, рельеф свой")
                continue
            im, note = sheet(code, kit, d, os.path.join(a.before, f"{code}_{kit}") if a.before else None, a.width)
            if im is None:
                print(f"{code}_{kit}: {note}")
                continue
            out = os.path.join(core.COMPARE, f"pants-{code}_{kit}-{datetime.datetime.now():%Y%m%d-%H%M}.png")
            os.makedirs(os.path.dirname(out), exist_ok=True)
            im.save(out)
            print(f"{code}_{kit}: {note}; лист →", out)
            n += 1
    return 0 if n else 1
