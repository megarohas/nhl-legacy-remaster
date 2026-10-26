"""Рукав крупно со всех сторон вокруг оси руки: полосы у локтя и манжеты, шов снизу рукава, «клинья». Ряды листа —
источник (NHL 27 на сетке NHL 24), снимок «было» (--before) и наша форма слота, виды — одни и те же по сторонам тела.

    python -m kitport arm --clubs STL --kits away            # источник и наш: 6 видов через 60° (0° — сверху, 90° — спереди)
    python -m kitport arm --clubs CGY,ANA --before compare/kitport/20261026-0913-sleeves-before   # «было | стало»
    python -m kitport arm --clubs ANA --kits home --views 300,330,0,30,60,90 --along -0.17,0.06 --h 0.09   # локоть крупно

Зачем (23.10, STL выезд: «полоски на предплечьях с белыми выемками»; 26.10, CGY выезд и ANA: «кривые предплечья»): выемки
бывают только на нижней стороне руки у шва рукава или на верху локтя — ни перед, ни бок, ни спина `kitport present` их не
показывают, а без источника рядом не видно, рисунок это или дефект переноса.

Ось — главная ось вершин руки (|x| от --x0 до --x1, правая рука; левая — зеркальна), «вверх» — вертикаль мира без
составляющей по оси: 0° — камера сверху, 90° — спереди, 180° — снизу, 270° — сзади. Рисуются только треугольники рукава
(по развёртке: u рукава ≤ 0,36, v 0,27–0,75 — без бока туловища и второй руки). Кадр вдоль оси — вся рука (или --along),
поперёк — ±--h м. Лист — compare/kitport/arm-<КЛУБ>_<форма>-<дата>.png (по листу на форму).
"""
import datetime
import os
import sys

import numpy as np

from . import core

VIEWS = (0, 60, 120, 180, 240, 300)      # град вокруг оси руки: 0 — сверху, 90 — спереди, 180 — снизу, 270 — сзади
NAMES = {0: "сверху", 90: "спереди", 180: "снизу", 270: "сзади"}
ARM_UV = (0.36, 0.27, 0.75)              # треугольники рукава: u рукава (как у левого) ≤, v от, до (обе развёртки)


def basis(p, x0, x1):
    """Центр, ось руки (наружу), «вверх» и «вперёд» поперёк оси, пределы кадра вдоль оси — по вершинам x0 < x < x1."""
    sel = (p[:, 0] > x0) & (p[:, 0] < x1)
    c = p[sel].mean(0)
    _, _, vt = np.linalg.svd(p[sel] - c, full_matrices=False)
    ax = vt[0] if vt[0][0] > 0 else -vt[0]
    up = np.array([0.0, 1.0, 0.0]) - ax[1] * ax
    up /= np.linalg.norm(up)
    fr = np.cross(ax, up)
    if fr[2] < 0:
        fr = -fr
    q = (p[sel] - c) @ ax
    return c, ax, up, fr, (q.min() - 0.01, q.max() + 0.01)


def arm_tris(M):
    """Треугольники правого рукава по развёртке (u > 1 − ARM_UV[0], ARM_UV[1] < v < ARM_UV[2]) и x > 0,2 м."""
    uv = M["uv"][M["tri"]]
    p = M["pos"][M["tri"]]
    k = (p[:, :, 0] > 0.2) & (1.0 - uv[:, :, 0] < ARM_UV[0]) & (uv[:, :, 1] > ARM_UV[1]) & (uv[:, :, 1] < ARM_UV[2])
    return M["tri"][k.all(1)]


def views(M, tex, nm, a, font, title):
    """Ряд видов одной сетки с текстурой tex (и рельефом nm) — картинка с подписью."""
    os.environ.setdefault("PHOTOS_SOURCE", "nhl24")     # scans24 (рендер) читает его при импорте
    sys.path.insert(0, core.TOOLS)
    import scans24 as S
    from PIL import Image, ImageDraw
    p = M["pos"]
    c, ax, up, fr, (a0, a1) = basis(p, a.x0, a.x1)
    if a.along:
        a0, a1 = (float(v) for v in a.along.split(","))
    tri = arm_tris(M)
    angs = [float(v) for v in a.views.split(",")] if a.views else VIEWS
    ims = []
    for ang in angs:
        t = np.radians(ang)
        cam = np.cos(t) * up + np.sin(t) * fr               # к камере
        vup = np.cross(cam, ax)
        q = p - c
        pos = np.stack([q @ ax, q @ vup, q @ cam], 1)
        part = {"pos": pos, "nrm": S.weld_normals(pos, M["tri"], S.weld_ids(pos)), "uv": M["uv"], "tri": tri,
                "tex": tex, "twosided": False}
        if nm is not None:
            part["nmap"] = nm
        im = S.render([part], 0.0, a.width, frame=(a0, a1, -a.h, a.h)).convert("RGB")
        ImageDraw.Draw(im).text((4, 3), f"{ang:.0f}° {NAMES.get(int(ang) % 360, '')}", fill=(255, 220, 140), font=font)
        ims.append(im)
    w, h = ims[0].size
    cols = 3 if len(ims) > 4 else len(ims)
    rows = (len(ims) + cols - 1) // cols
    o = Image.new("RGB", (cols * (w + 4), rows * (h + 4) + 20), (14, 14, 18))
    ImageDraw.Draw(o).text((4, 3), title, fill=(230, 230, 230), font=font)
    for i, im in enumerate(ims):
        o.paste(im, ((i % cols) * (w + 4), 20 + (i // cols) * (h + 4)))
    return o


def load_maps(d):
    from PIL import Image
    t = np.asarray(Image.open(os.path.join(d, "jersey_cm.png")).convert("RGBA"))
    nmp = os.path.join(d, "jersey_nm.png")
    nm = np.asarray(Image.open(nmp).convert("RGB").resize(t.shape[1::-1])).astype(np.float64) \
        if os.path.exists(nmp) else None
    return t, nm


def cmd_arm(a):
    sys.path.insert(0, core.TOOLS)
    from PIL import Image
    from fb import edge_kit as E, jersey_mesh as J
    from fb.jersey_hybrid import CLUB_NAME
    from .present import _font, n24_meshes
    clubs = [c for c in a.clubs.split(",") if c]
    kits = [k for k in a.kits.split(",") if k]
    font = _font(13)
    ME = E.mesh_for(0, 1, 2)
    n24 = None if a.no_source else n24_meshes()["j"]
    before = None
    if a.before:                                         # снимок kitport snapshot: путь, имя папки в compare/kitport или
        for c in (a.before, os.path.join(core.COMPARE, a.before), os.path.join(core.NHL24_WORK, a.before)):   # от nhl24
            if os.path.isdir(c):
                before = c
                break
        else:
            print(f"нет снимка {a.before}")
            return 1
    n = 0
    for code in clubs:
        E.use_club(code)
        for kit in kits:
            d = os.path.join(core.slot_kits_dir(), f"{code}_{kit}")
            if not os.path.exists(os.path.join(d, "jersey_cm.png")):
                print(f"{code} {kit}: слот не собран ({d})")
                continue
            rows = []
            if n24 is not None:
                src = J.n24_tex(CLUB_NAME[code], kit, "color")
                if os.path.exists(src):
                    t24 = np.asarray(Image.open(src).convert("RGBA").resize((2048, 2048), Image.LANCZOS))
                    rows.append(views(n24, t24, None, a, font, f"{code} {kit}: источник {os.path.basename(src)} "
                                                              "(сетка NHL 24, цвет)"))
            if before:
                bd = os.path.join(before, f"{code}_{kit}")
                if os.path.exists(os.path.join(bd, "jersey_cm.png")):
                    rows.append(views(ME, *load_maps(bd), a, font, f"{code} {kit}: было — {os.path.basename(before)}"))
                else:
                    print(f"{code} {kit}: в снимке {before} формы нет")
            rows.append(views(ME, *load_maps(d), a, font, f"{code} {kit}: " + ("стало" if before else "наш")
                              + " (слот, сетка Edge)"))
            W = max(r.size[0] for r in rows)
            sheet = Image.new("RGB", (W, sum(r.size[1] + 4 for r in rows)), (6, 6, 8))
            y = 0
            for r in rows:
                sheet.paste(r, (0, y))
                y += r.size[1] + 4
            out = os.path.join(a.out or core.COMPARE, f"arm-{code}_{kit}-{datetime.datetime.now():%Y%m%d-%H%M}.png")
            os.makedirs(os.path.dirname(out), exist_ok=True)
            sheet.save(out)
            print(f"{code}_{kit}: лист →", out)
            n += 1
    return 0 if n else 1
