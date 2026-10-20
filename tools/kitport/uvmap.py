"""Схема развёртки свитера NHL Legacy (сетка Reebok Edge, `rendering/jersey/jersey_0_1_2_0_1_2.rx2`, её же UV у
слота формы Edge): каждый тексель — точка тела, по ней — часть тела (перед, спина, рукав, ворот) и высота
в метрах (линии через 10 см); поверх — зоны карты номеров (name_cm) собранной формы и место надписи сзади.
Подложка — текстура собранной формы. Нужна, чтобы понимать, куда на развёртке что ложится (docs/kitport.md)."""
import os

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from . import core

ZONE_NAMES = {0: "фамилия", 1: "номер на спине", 2: "номер на рукаве", 3: "номер на рукаве",
              5: "буква капитана", 7: "2-е место буквы"}
COLORS = {"перед": (60, 140, 255), "спина": (255, 140, 40), "рукав": (80, 200, 90), "у горловины": (230, 60, 200)}


def font(size):
    for f in ("arial.ttf", "C:/Windows/Fonts/arial.ttf"):
        try:
            return ImageFont.truetype(f, size)
        except OSError:
            pass
    return ImageFont.load_default()


def classify(mesh, size=1024):
    """-> (часть тела [h,w] str-код, позиция [h,w,3], маска). Сетка — один кусок развёртки: рукав — за швом проймы
    (fb.edge_kit.ARMHOLE_UV, в строках v 0,27…0,73), ворот — не дальше 3 см от края горловины (граничные рёбра
    выше 1,6 м), остальное — перед / спина по знаку z."""
    from fb import edge_kit, kit3d
    from scipy.spatial import cKDTree
    tid, bar = kit3d.raster_uv(mesh, size)
    m = tid >= 0
    T = mesh["tri"][np.maximum(tid, 0)]
    P = (bar[..., :, None] * mesh["pos"][T]).sum(-2)
    tri = mesh["tri"]
    key = np.round(mesh["pos"], 5)
    _, weld = np.unique(key, axis=0, return_inverse=True)
    weld = weld.ravel()
    e = np.sort(np.concatenate([weld[tri[:, [0, 1]]], weld[tri[:, [1, 2]]], weld[tri[:, [2, 0]]]]), 1)
    ue, cnt = np.unique(e, axis=0, return_counts=True)
    wpos = np.zeros((weld.max() + 1, 3))
    wpos[weld] = mesh["pos"]
    border = ue[cnt == 1]
    neck = border[(wpos[border[:, 0], 1] > 1.6) & (wpos[border[:, 1], 1] > 1.6)]
    pts = np.concatenate([wpos[neck[:, 0]] * (1 - t) + wpos[neck[:, 1]] * t for t in np.linspace(0, 1, 6)])
    dn, _ = cKDTree(pts).query(P[m]) if len(pts) else (np.full(m.sum(), np.inf), None)
    near = np.zeros(m.shape, bool)
    near[m] = dn < 0.03
    H, W = m.shape
    vv, uu = np.meshgrid((np.arange(H) + 0.5) / H, (np.arange(W) + 0.5) / W, indexing="ij")
    au = edge_kit.armhole_u(vv)
    sleeve = (vv >= 0.27) & (vv <= 0.73) & ((uu < au) | (uu > 1 - au))
    part = np.full(m.shape, "", dtype=object)
    z = P[..., 2]
    part[m & (z >= 0)] = "перед"
    part[m & (z < 0)] = "спина"
    part[m & sleeve] = "рукав"
    part[m & near] = "у горловины"
    return part, P, m


def cmd_uvmap(a):
    from fb import kit3d
    mesh = kit3d.load_legacy()
    S = 1024
    part, P, m = classify(mesh, S)
    kit_dir = os.path.join(core.slot_kits_dir(), a.kit)
    base = Image.new("RGB", (S, S), (24, 24, 28))
    cm = os.path.join(kit_dir, "jersey_cm.png")
    if os.path.exists(cm) and not a.plain:                     # --plain: без подложки (можно в git — нет ассетов EA)
        base = Image.blend(base, Image.open(cm).convert("RGB").resize((S, S)), 0.45)
    img = np.asarray(base).astype(np.float64)
    for name, col in COLORS.items():
        k = part == name
        img[k] = img[k] * 0.6 + np.array(col) * 0.4
    y = P[..., 1]
    for h in np.arange(0.9, 1.81, 0.1):                        # линии высоты через 10 см
        band = m & (np.abs(y - h) < 0.0022)
        img[band] = (255, 255, 255)
    out = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8)).resize((2048, 2048), Image.NEAREST)
    d = ImageDraw.Draw(out)
    f, fs = font(26), font(20)
    for h in np.arange(0.9, 1.81, 0.1):                        # подписи высот — у правого края каждой линии
        ys, xs = np.nonzero(m & (np.abs(y - h) < 0.0022))
        if len(xs):
            i = np.argmax(xs)
            d.text((xs[i] * 2 + 6, ys[i] * 2 - 12), f"{h:.1f} м", fill=(255, 255, 255), font=fs)
    for name, col in COLORS.items():                           # подписи частей — в «центре масс»
        ys, xs = np.nonzero(part == name)
        if len(xs):
            d.text((np.median(xs) * 2 - 40, np.median(ys) * 2), name, fill=col, font=f)
    nm = os.path.join(kit_dir, "name_cm.png")
    if os.path.exists(nm):
        z = np.asarray(Image.open(nm).convert("RGBA")).astype(int)
        h, w = z.shape[:2]
        for k, label in ZONE_NAMES.items():
            ys, xs = np.nonzero((z[..., 0] > 128) & (z[..., 1] > 128) & (z[..., 2] == k))
            if len(xs):
                b = [xs.min() / w * 2048, ys.min() / h * 2048, (xs.max() + 1) / w * 2048, (ys.max() + 1) / h * 2048]
                d.rectangle(b, outline=(255, 255, 0), width=3)
                d.text((b[0] + 4, b[1] + 2), f"{k}: {label}", fill=(255, 255, 0), font=fs)
    try:
        from fb import edge_kit
        cx, cy = edge_kit.REEBOK_BACK_UV
        d.rectangle([(cx - 0.035) * 2048, (cy - 0.012) * 2048, (cx + 0.035) * 2048, (cy + 0.012) * 2048],
                    outline=(0, 255, 255), width=3)
        d.text(((cx + 0.04) * 2048, (cy - 0.01) * 2048), "надпись сзади (вверх ногами)", fill=(0, 255, 255), font=fs)
    except Exception:                                          # noqa: BLE001
        pass
    d.text((16, 16), "Развёртка свитера NHL Legacy (Reebok Edge, стиль 1 / слот Edge стиля 0). u → вправо, v → вниз",
           fill=(255, 255, 255), font=f)
    d.text((16, 52), "цвет — часть тела по 3D-точке, белые линии — высота над льдом, жёлтое — зоны карты номеров"
           f" ({a.kit})", fill=(220, 220, 220), font=fs)
    d.text((16, 80), "вверху слева (без заливки) — остров переда ворота: есть только у сеток слота Edge (fb.edge_kit "
           "island, ISLAND_LODS)", fill=(220, 220, 220), font=fs)
    dst = a.out or os.path.join(core.COMPARE, f"uvmap-{a.kit}.png")
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    out.save(dst)
    print("схема:", dst)
    return 0
