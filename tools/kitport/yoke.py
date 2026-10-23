"""Кокетка и плечи: наша форма слота (сетка Edge) против источника (NHL 27 / NHL 24 на сетке NHL 24) в одних видах — перед,
бок, спина, 3/4 спереди и сзади — с линиями высот, и замер нижнего края кокетки (docs/kitport.md §12.1, §12.8).

    python -m kitport yoke --clubs MTL                        # формы слота клуба с кокеткой (профиль yoke)
    python -m kitport yoke --clubs BUF,DAL --kits away        # только выезд
    python -m kitport yoke --clubs MTL --source-only          # только источник (слот ещё не собран)
    python -m kitport yoke --clubs MTL --views 90,60,120 --frame -0.30,0.30,1.45,1.76   # бок крупнее

Зачем: кокетка «до плеча» или «на плечо» (тип MTL), её край на руке (yoke_side_blend — прямая наискосок от переда к
спине), край сзади (по EA-форме yoke или источнику — yoke_back), полоса под кокеткой (yoke_stripe), мыс со щитом — всё
это видно только рядом с источником в тех же видах. Линии — 1,50…1,70 м через 5 см (1,60 — малиновая).

Замер края (печать): цвет кокетки — yoke_color профиля ([R, G, B] — ближе edge_kit.YOKE_RGB_DIST; green / dark —
edge_kit.yoke_mask); край — 2-й процентиль высоты текселей этого цвета в полосе: спереди и сзади по |x| (0…0,24 м),
на руке по z (−0,10…+0,10) в трёх полосах |x| (0,18–0,30). У источника x — от середины горловины NHL 24 (+0,0035).
Лист — compare/kitport/yoke-<КЛУБЫ>-<дата>.png.
"""
import datetime
import os
import sys

import numpy as np

from . import core

FRAME = (-0.42, 0.42, 1.38, 1.76)        # м: x0, x1, y0, y1 — перед и спина; боковые виды — уже (×0,75 по x)
VIEWS = (0.0, 90.0, 180.0, 45.0, 135.0)  # град: поворот вокруг вертикали (0 — перед, 180 — спина)
WIDTH = 330                              # px на вид
LINES = (1.50, 1.55, 1.60, 1.65, 1.70)   # м: линии высот (1,60 — малиновая)
ARM_X = ((0.18, 0.22), (0.22, 0.26), (0.26, 0.30))   # м: полосы |x| на руке для замера по z
ARM_Z = np.arange(-0.10, 0.101, 0.02)    # м: z на руке
Y_MIN = 1.55                             # м: спереди и сзади край ищется выше (ниже — герб, номер того же цвета)


def outer(M):
    """Сетка без подкладки ворота: только самая большая связная часть (как edge_kit.yoke_heights)."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    pos, tri = M["pos"], M["tri"]
    _, wid = np.unique(np.round(pos / 1e-4).astype(np.int64), axis=0, return_inverse=True)
    wid = wid.ravel()
    T = wid[tri]
    n = int(wid.max()) + 1
    r, c = np.concatenate([T[:, 0], T[:, 1], T[:, 2]]), np.concatenate([T[:, 1], T[:, 2], T[:, 0]])
    _, comp = connected_components(coo_matrix((np.ones(len(r)), (r, c)), shape=(n, n)), directed=False)
    tc = comp[T[:, 0]]
    return dict(M, tri=tri[tc == np.bincount(tc).argmax()])


def points(M, img):
    """Точки сетки M в текселях img (развёртка) и их цвета: (P, цвета)."""
    from fb import kit3d
    tid, bar = kit3d.raster_uv(M, img.shape[0])
    ys, xs = np.nonzero(tid >= 0)
    P = (bar[ys, xs][:, :, None] * M["pos"][M["tri"][tid[ys, xs]]]).sum(1)
    return P, img[ys, xs, :3].astype(np.float64)


def edge_table(P, c, is_yoke, x_fix=0.0):
    """Нижний край кокетки: {строка: «высоты через пробел»}."""
    x, y, z = P[:, 0] + x_fix, P[:, 1], P[:, 2]
    yk = is_yoke(c)

    def low(m):
        return f"{np.percentile(y[m], 2):.3f}" if m.sum() > 15 else "  —  "
    out = {}
    for name, sel in (("перед", z > 0.04), ("спина", z < -0.04)):
        out[f"{name} |x| 0…0,24"] = " ".join(low(yk & sel & (np.abs(np.abs(x) - x0) < 0.005) & (y > Y_MIN))
                                            for x0 in np.arange(0.0, 0.25, 0.02))
    for xa, xb in ARM_X:
        out[f"рука |x| {xa:.2f}–{xb:.2f}, z −0,10…+0,10"] = " ".join(
            low(yk & (np.abs(x) > xa) & (np.abs(x) < xb) & (np.abs(z - z0) < 0.01) & (y > 1.40)) for z0 in ARM_Z)
    return out


def views_row(S, parts, title, font, views, frame):
    """Ряд видов одной поверхности с линиями высот."""
    from PIL import Image, ImageDraw
    from .present import label_img, row
    ims = []
    for ang in views:
        f = frame if ang % 180 == 0 else (frame[0] * 0.75, frame[1] * 0.75, frame[2], frame[3])
        im = S.render([dict(p) for p in parts], np.radians(ang), WIDTH, frame=f).convert("RGB")
        dr = ImageDraw.Draw(im)
        for yy in LINES:
            py = (f[3] - yy) / (f[3] - f[2]) * im.size[1]
            dr.line([(0, py), (im.size[0], py)], fill=(255, 0, 255) if abs(yy - 1.60) < 1e-6 else (0, 200, 255))
        ims.append(label_img(im, f"{ang:.0f}°", font))
    return row(title, ims, font)


def cmd_yoke(a):
    os.environ.setdefault("PHOTOS_SOURCE", "nhl24")     # scans24 (рендер) читает его при импорте
    sys.path.insert(0, core.TOOLS)
    import scans24 as S
    from PIL import Image
    from fb import edge_kit as E, jersey_mesh as J, kitsrc, pilot
    from fb.jersey_hybrid import CLUB_NAME
    from .present import _font, n24_meshes
    clubs = [c for c in a.clubs.split(",") if c]
    if not clubs:
        print("укажите --clubs (MTL,BUF)")
        return 1
    views = tuple(float(v) for v in a.views.split(",")) if a.views else VIEWS
    frame = tuple(float(v) for v in a.frame.split(",")) if a.frame else FRAME
    font = _font(13)
    n24 = n24_meshes()["j"]
    n24o = outer(n24)
    nrm24 = S.weld_normals(n24["pos"], n24["tri"], S.weld_ids(n24["pos"]))
    M = None if a.source_only else E.mesh_for(0, 1, 2)            # сетка слота (полевой, размер 0, lod 2)
    nrmE = S.weld_normals(M["pos"], M["tri"], S.weld_ids(M["pos"])) if M is not None else None
    rows = []
    for code in clubs:
        prof = E.use_club(code)
        club = CLUB_NAME[code]
        pilot.extract_club(club)                                    # выгрузка источника (есть — не повторяется)
        kits = [k for k in a.kits.split(",") if k] or sorted({k for _, k in E.YOKE}) or ["home", "away"]
        for kit in kits:
            kind = prof.get("yoke_color", "green")
            kind = kind.get(kit, next(iter(kind.values()))) if isinstance(kind, dict) else kind   # по форме (EDM)
            is_yoke = (lambda c, k=kind: E.yoke_mask(c, 80, k))
            src = J.n24_tex(club, kit, "color")
            if not os.path.exists(src):
                print(f"{code} {kit}: нет текстуры источника {src}")
                continue
            t24 = np.asarray(Image.open(src).convert("RGBA").resize((2048, 2048), Image.LANCZOS))
            rows.append(views_row(S, [{"pos": n24["pos"], "nrm": nrm24, "uv": n24["uv"], "tri": n24["tri"], "tex": t24,
                                       "twosided": True}],
                                  f"{code} {kit}: источник {E.SOURCE_NAME()} adidas/{kitsrc.folder(kit)} (сетка NHL 24); "
                                  "линии 1,50…1,70 м, 1,60 — малиновая", font, views, frame))
            print(f"== {code} {kit}: нижний край кокетки (цвет {kind}), м")
            Pn, cn = points(n24o, np.asarray(Image.open(src).convert("RGB").resize((1024, 1024))))
            tab_s = edge_table(Pn, cn, is_yoke, 0.0035)
            d = os.path.join(core.slot_kits_dir(), f"{code}_{kit}")
            tab_o = {}
            if M is not None and os.path.exists(os.path.join(d, "jersey_cm.png")):
                t = np.asarray(Image.open(os.path.join(d, "jersey_cm.png")).convert("RGBA"))
                nm = np.asarray(Image.open(os.path.join(d, "jersey_nm.png")).convert("RGB")
                                .resize(t.shape[1::-1])).astype(np.float64)
                rows.append(views_row(S, [{"pos": M["pos"], "nrm": nrmE, "uv": M["uv"], "tri": M["tri"], "tex": t,
                                           "nmap": nm, "twosided": True}],
                                      f"{code} {kit}: наш (сетка Edge слота)", font, views, frame))
                Po, co = points(M, np.asarray(Image.open(os.path.join(d, "jersey_cm.png")).convert("RGB")
                                              .resize((1024, 1024))))
                tab_o = edge_table(Po, co, is_yoke)
            elif M is not None:
                print(f"  слот не собран ({d}) — только источник")
            for k_, v in tab_s.items():
                print(f"  {k_}:\n    источник {v}" + (f"\n    наш      {tab_o[k_]}" if k_ in tab_o else ""))
    if not rows:
        return 1
    W = max(r.size[0] for r in rows)
    sheet = Image.new("RGB", (W, sum(r.size[1] for r in rows)), (10, 10, 12))
    y = 0
    for r in rows:
        sheet.paste(r, (0, y))
        y += r.size[1]
    out = a.out or os.path.join(core.COMPARE, f"yoke-{'_'.join(clubs)}-{datetime.datetime.now():%Y%m%d-%H%M}.png")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    sheet.save(out)
    print("лист →", out)
    return 0
