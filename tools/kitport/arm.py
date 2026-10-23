"""Рукав крупно со всех сторон вокруг оси предплечья (наша форма слота): полосы у манжеты, шов снизу рукава, номер на
рукаве. Ось — главная ось вершин сетки с x > --x0 (правая рука; левая — зеркальна).

    python -m kitport arm --clubs STL --kits away            # 6 видов через 60° (0° — сверху-спереди), лист на форму
    python -m kitport arm --clubs STL --kits away,home --x0 0.30 --x1 0.52 --width 420

Зачем (23.10, STL выезд: «полоски на предплечьях с белыми выемками»): выемки были только на нижней стороне руки у шва
рукава — ни перед, ни бок, ни спина `kitport present` её не показывают. Лист — compare/kitport/arm-<КЛУБ>_<форма>-<дата>.png.
"""
import datetime
import os
import sys

import numpy as np

from . import core


def views(kit_dir, x0, x1, width):
    os.environ.setdefault("PHOTOS_SOURCE", "nhl24")     # scans24 (рендер) читает его при импорте
    sys.path.insert(0, core.TOOLS)
    import scans24 as S
    from PIL import Image, ImageDraw
    from fb import edge_kit as E
    M = E.mesh_for(0, 1, 2)
    p = M["pos"]
    sel = p[:, 0] > x0
    c = p[sel].mean(0)
    _, _, vt = np.linalg.svd(p[sel] - c, full_matrices=False)
    ax = vt[0] if vt[0][0] > 0 else -vt[0]
    t = np.asarray(Image.open(os.path.join(kit_dir, "jersey_cm.png")).convert("RGBA"))
    nm = np.asarray(Image.open(os.path.join(kit_dir, "jersey_nm.png")).convert("RGB").resize(t.shape[1::-1])) \
        .astype(np.float64)
    e1 = np.cross(ax, [0, 0, 1.0])
    e1 /= np.linalg.norm(e1)
    e2 = np.cross(ax, e1)
    outs = []
    for ang in range(0, 360, 60):
        a = np.radians(ang)
        v = np.cos(a) * e2 + np.sin(a) * e1              # к камере
        up = np.cross(v, ax)
        q = p - c
        pos = np.stack([q @ ax, q @ up, q @ v], 1)
        part = {"pos": pos, "nrm": S.weld_normals(pos, M["tri"], S.weld_ids(pos)), "uv": M["uv"], "tri": M["tri"],
                "tex": t, "nmap": nm, "twosided": False}
        im = S.render([part], 0.0, width, frame=(x0 - c[0] - 0.02, x1 - c[0] + 0.05, -0.09, 0.09))
        ImageDraw.Draw(im).text((4, 4), f"{ang}°", fill=(255, 220, 140))
        outs.append(im)
    W, H = outs[0].size
    o = Image.new("RGB", (3 * W + 12, 2 * H + 6), (10, 10, 12))
    for i, im in enumerate(outs):
        o.paste(im, ((i % 3) * (W + 6), (i // 3) * (H + 6)))
    return o


def cmd_arm(a):
    clubs = [c for c in a.clubs.split(",") if c]
    kits = [k for k in a.kits.split(",") if k]
    n = 0
    for code in clubs:
        for kit in kits:
            d = os.path.join(core.slot_kits_dir(), f"{code}_{kit}")
            if not os.path.exists(os.path.join(d, "jersey_cm.png")):
                print(f"{code} {kit}: слот не собран ({d})")
                continue
            out = os.path.join(core.COMPARE, f"arm-{code}_{kit}-{datetime.datetime.now():%Y%m%d-%H%M}.png")
            os.makedirs(os.path.dirname(out), exist_ok=True)
            views(d, a.x0, a.x1, a.width).save(out)
            print(f"{code}_{kit}: лист →", out)
            n += 1
    return 0 if n else 1
