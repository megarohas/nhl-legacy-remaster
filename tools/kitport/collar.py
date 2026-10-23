"""Ворот крупно: наша форма слота (сетка Edge) против источника (NHL 27 / NHL 24 на сетке NHL 24) — решить по источнику,
шнуровка у ворота или нет (профиль collar = lace | plain), и сверить швы и края цветов кромки. docs/kitport.md §12.3.

    python -m kitport collar --clubs TOR                     # формы слота клуба: наш и источник, прямо и сверху
    python -m kitport collar --clubs TOR --source-only       # только источник (до сборки профиля и формы)
    python -m kitport collar --clubs TOR,MIN --kits home --tilt 35 --out ../game/work/nhl24/compare/kitport/c.png
    python -m kitport collar --clubs MTL --kits home --frame 0.06,0.20,1.22,1.32 --width 700   # любое место крупно

Ряд на форму. Наш (если слот собран): цвет прямо, цвет сверху (камера наклонена на --tilt°), рельеф без цвета прямо.
Источник: цвет (готовый свитер), основа (base_color) с рельефом base_normal прямо и сверху, рельеф без цвета прямо.
Шнуровка видна по рельефу источника — люверсы, шнурки, планка и V-вставка под щитом — даже когда шнурки и вставка цвета
ткани (TOR, 22.10: генератор kitport profile по цвету под щитом дал plain, у обеих форм NHL 27 — шнуровка, как у MIN).
Сверху видно и кромку у середины переда, и полосу воротника сзади (TOR дом: белая сзади от ступеньки — collar_band).
Текстуры источника — выгрузка клуба (fb.pilot.extract_club, как у сборки; выгружает, если её ещё нет). Лист —
compare/kitport/collar-<КЛУБЫ>-<дата>.png.
"""
import datetime
import os
import sys

import numpy as np

from . import core

FRAME = (-0.12, 0.12, 1.55, 1.70)        # м: x0, x1, y0, y1 — ворот прямо (как «ворот» у kitport present)
FRAME_TILT = (-0.12, 0.12, 1.50, 1.66)   # сверху: кадр ниже (наклон опускает ворот в кадре)
TILT_AT = 1.62                           # м: высота оси наклона камеры
WIDTH = 420                              # px на вид
GRAY = 170                               # серый «рельефа без цвета»


def tilt(pos, deg):
    """Точки, повёрнутые вокруг оси x на высоте TILT_AT: камера смотрит сверху-спереди (deg > 0)."""
    a = np.radians(deg)
    R = np.array([[1, 0, 0], [0, np.cos(a), -np.sin(a)], [0, np.sin(a), np.cos(a)]])
    c = np.array([0.0, TILT_AT, 0.0])
    return (pos - c) @ R.T + c


def normal_rgb(path, size):
    """base_normal NHL 24/27 (x, y; z — по ним) → RGB-карта для рендера (float, size²)."""
    from PIL import Image
    n = np.asarray(Image.open(path).convert("RGB")).astype(np.float32) / 255.0 * 2 - 1
    z = np.sqrt(np.clip(1 - n[..., 0] ** 2 - n[..., 1] ** 2, 0, 1))
    rgb = (np.stack([n[..., 0], n[..., 1], z], -1) + 1) * 127.5
    im = Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8)).resize((size, size), Image.LANCZOS)
    return np.asarray(im).astype(np.float64)


def views(S, mesh, tex, nmap, deg, what, font):
    """Виды одной поверхности: цвет прямо, (основа + рельеф) сверху, рельеф без цвета — подписанные."""
    from .present import label_img

    def part(pos, t, n):
        return {"pos": pos, "nrm": S.weld_normals(pos, mesh["tri"], S.weld_ids(pos)), "uv": mesh["uv"],
                "tri": mesh["tri"], "tex": t, "nmap": n, "twosided": True}
    gray = np.full(tex.shape, GRAY, np.uint8)
    gray[..., 3] = 255
    base, n_base = what.get("base", (tex, nmap))
    out = [label_img(S.render([part(mesh["pos"], tex, what.get("color_nm", nmap))], 0.0, WIDTH, frame=FRAME),
                     f"{what['name']}: {what['color']}", font),
           label_img(S.render([part(tilt(mesh["pos"], deg), base, n_base)], 0.0, WIDTH, frame=FRAME_TILT),
                     f"{what['name']}: {what['tilted']}, сверху {deg:.0f}°", font)]
    if n_base is not None:
        out.append(label_img(S.render([part(mesh["pos"], gray, n_base)], 0.0, WIDTH, frame=FRAME),
                             f"{what['name']}: рельеф без цвета", font))
    return out


def cmd_collar(a):
    global FRAME, WIDTH
    if getattr(a, "frame", None):                       # свой кадр (--frame): стыки полос с гербом, концы кантов
        FRAME = tuple(float(v) for v in a.frame.split(","))
        if len(FRAME) != 4:
            sys.exit("--frame x0,x1,y0,y1 (м)")
    if getattr(a, "width", None):
        WIDTH = a.width
    os.environ.setdefault("PHOTOS_SOURCE", "nhl24")     # scans24 (рендер) читает его при импорте
    sys.path.insert(0, core.TOOLS)
    import scans24 as S
    from PIL import Image
    from fb import edge_kit as E, jersey_mesh as J, kitsrc, pilot
    from fb.jersey_hybrid import CLUB_NAME
    from .present import _font, n24_meshes, row
    clubs = [c for c in a.clubs.split(",") if c]
    kits = [k for k in a.kits.split(",") if k]
    if not clubs:
        print("укажите --clubs (TOR,MIN)")
        return 1
    font = _font(13)
    n24 = n24_meshes()["j"]
    M = None if a.source_only else E.mesh_for(0, 1, 2)            # сетка слота (полевой, размер 0, lod 2)
    rows = []
    for code in clubs:
        E.use_club(code)
        club = CLUB_NAME[code]
        pilot.extract_club(club)                                    # выгрузка источника (есть — не повторяется)
        for kit in kits:
            ims = []
            d = os.path.join(core.slot_kits_dir(), f"{code}_{kit}")
            if M is not None and os.path.exists(os.path.join(d, "jersey_cm.png")):
                t = np.asarray(Image.open(os.path.join(d, "jersey_cm.png")).convert("RGBA"))
                nm = np.asarray(Image.open(os.path.join(d, "jersey_nm.png")).convert("RGB")
                                .resize(t.shape[1::-1])).astype(np.float64)
                ims += views(S, M, t, nm, a.tilt, {"name": "наш", "color": "цвет", "tilted": "цвет"}, font)
            elif M is not None:
                print(f"{code} {kit}: слот не собран ({d}) — только источник")
            src = {layer: J.n24_tex(club, kit, layer) for layer in ("color", "base_color", "base_normal")}
            if not os.path.exists(src["color"]):
                print(f"{code} {kit}: нет текстуры источника {src['color']}")
                continue
            col = np.asarray(Image.open(src["color"]).convert("RGBA").resize((2048, 2048), Image.LANCZOS))
            base = np.asarray(Image.open(src["base_color"]).convert("RGBA").resize((2048, 2048), Image.LANCZOS)) \
                if os.path.exists(src["base_color"]) else col
            bn = normal_rgb(src["base_normal"], 2048) if os.path.exists(src["base_normal"]) else None
            ims += views(S, n24, col, None, a.tilt,
                         {"name": f"{E.SOURCE_NAME()} {kitsrc.folder(kit)}", "color": "цвет", "tilted": "основа + рельеф",
                          "base": (base, bn), "color_nm": None}, font)
            rows.append(row(f"{code} {kit}: ворот — наш (сетка Edge слота) и источник {E.SOURCE_NAME()} adidas/"
                            f"{kitsrc.folder(kit)} (сетка NHL 24)", ims, font))
    if not rows:
        return 1
    W = max(r.size[0] for r in rows)
    sheet = Image.new("RGB", (W, sum(r.size[1] for r in rows)), (10, 10, 12))
    y = 0
    for r in rows:
        sheet.paste(r, (0, y))
        y += r.size[1]
    out = a.out or os.path.join(core.COMPARE, f"collar-{'_'.join(clubs)}-{datetime.datetime.now():%Y%m%d-%H%M}.png")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    sheet.save(out)
    print("лист →", out)
    return 0
