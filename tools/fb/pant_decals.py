"""Нашивки шорт (герб клуба, щит NHL) — наклейками, а не 3D-переносом текстуры.

Перенос по ближайшей точке (fb.kit3d.transfer после kit3d.aligned) растягивает нашивки и поворачивает их на изгибах
(«поехали логотипы», пользователь, 21.10, NJD: герб спереди и щит NHL сзади). Полосам и ткани это не мешает, нашивкам —
да. Поэтому:

1. Ткань — перенос base_color (у EA текстура шорт без нашивок) как раньше (на сетку pilot.PANT_L).
2. Нашивки — разница color − base_color (> DIFF), каждая связная часть — отдельная наклейка на сетке шорт полевых
   в игре (GAME_MESH, 24.10 — до этого на сетке вратаря pilot.PANT_L, ниже):
   - место — правило ноги (LEG_SLOTS, 24.10): герб спереди — на той ноге, где у источника, под углом 22° от середины
     переда наружу, центр на 8,5 см над краем штанины (низ — не ниже 5 см: подворот 3 см); щит NHL сзади — 150° вокруг
     ноги, центр на 7 см над краем (низ — не ниже 4,5 см). Размер герба — как у NHL 27 (шорты полевых Legacy — размера
     шорт NHL 24/27: ширина 0,51 против 0,49 м), щит — 5,1 см высотой (как щит EA в игре). Пропорции нашивки —
     источника (масштаб одинаков по осям);
   - верх наклейки — мировая ось y в касательной плоскости (нога полевого в позе привязки вертикальна), без поворота
     от развёртки: у EA в развёртке гербы повёрнуты по-разному, чтобы на сетке стоять вертикально;
   - история: 21.10 место по точке источника (центр в 3D → выровненная сетка) — щит мельче EA, герб на загибе у края
     штанины «сплюснутый»; потом — центры рамок EA (EA_SLOTS) и +3 см (`lift`, «слишком низко» — по листу на сетке
     вратаря); 24.10 после игры — «логотипы и щиты слишком высоко». Причина: всё раскладывалось на pant_1_0_0_2 —
     это шорты вратаря (pant_G_X_U_L, G — вратарь), на 40 % шире и короче шорт полевых; развёртка общая, но точка
     развёртки на ноге полевого выше в 1,3–1,4 раза: герб в игре стоял на 12,7–14,5 см над краем (у EA — 11,3, у
     NHL 27 — 7,2), щит — на 10,3 (NHL 27 — 6,6), и герб был сжат по ширине в 0,7 (DET 6,8 × 7,5 см вместо 8,1 × 6,2).
   Нашивки не сзади и не спереди (полосы, надписи сбоку) — по точке источника на выровненной сетке игры, размер ×
   высота шорт игры / видимая высота источника. Нашивка с центром выше Y_MAX на сетке источника — под свитером (пояс),
   не нашивка.
3. Наклейка ложится по 3D-точкам текселей сетки (не по UV) — изгиб и швы развёртки её не рвут.

    from fb import pant_decals
    img, rep = pant_decals.apply(img, color, base, src_mesh, size)      # нашивки — на сетку игры (GAME_MESH)

4. Полосы по низу штанин (профиль pant_hem, 23.10, NYR) — hem(): у края штанины тексель Legacy берёт цвет точки источника
   с тем же углом вокруг ноги и той же высотой над краем (полосы вдоль края, толщины NHL 27), выше — переход к переносу.

5. Рельеф и блеск (pant_nm, pant_sm) у шорт pant = "source" — образца Legacy, с его гербом и щитом EA на их местах; наши
   нашивки — в другом месте (пользователь, 23.10, DET: «лого выше и сбоку относительно рельефного места»).
   apply(masks=…) отдаёт альфу нашивок, стадия kit пишет её рядом с pant_cm.png (MASKS), стадия slot (relief) стирает
   гербы образца спереди и щит сзади (24.10: наш щит теперь не в рамке EA) в pant_nm/pant_sm и кладёт рельеф и блеск по
   нашим гербу и щиту. Проверка — relief_check (kitport audit).

Проверка — `python -m fb.pant_decals sheet CLUB KIT` (рендер шорт источника и наш, спереди, сзади, сбоку); место
нашивок в игре — place_check (kitport audit, `pant_place`). Только шорты собранных комплектов (без свитера, ~15 с на
форму; маски нашивок для рельефа) — `python -m fb.pant_decals rebuild --club DET --kits home,away`
(= `kitport build --club DET --stages pant,slot`).
"""
import numpy as np

DIFF = 30                          # из 255: тексель нашивки — отличие color от base_color больше (сжатие — до ~12)
MIN_PX = 200                       # меньше текселей (в 2048²) — не нашивка, а шум
RES = 0.0004                       # м на пиксель наклейки (0,4 мм: у источника 2048² на шорты ~0,3 мм)
SLAB = 0.04                        # м: тексели Legacy дальше от касательной плоскости центра — не на той же поверхности
FACING = 0.3                       # косинус: нормаль текселя к нормали центра — не меньше (не другая нога, не изнанка)
MERGE_PX = 0                       # профиль pant_merge_px (23.10, агент review-d, WSH): части нашивки ближе стольких текселей
#                                    (2048²) — одна наклейка. У WSH на ноге три звезды (по 48 px, промежуток ~30 px): порознь
#                                    каждая шла в место герба EA (11,5 см по диагонали) — одна крупная звезда. 0 — как было
Y_MAX_DEFAULT = 1.05               # м (24.10): у NHL 24/27 низ свитера на 0,93–0,97 м — нашивка с центром выше на сетке
#                                    источника под свитером (пояс): у DAL лого на поясе спереди (1,187 м) шло вторым гербом
#                                    на другую ногу, у WPG — обрывки у шнурка (профиль pant_decal_ymax 1,05 с 23.10)
Y_MAX = Y_MAX_DEFAULT              # профиль pant_decal_ymax, м (23.10, агент review-d, WPG): нашивка с центром выше на сетке
#                                    источника — не нашивка (пояс шорт под свитером: у WPG обрывки разницы у шнурка пояса
#                                    шли в места гербов EA — тёмные пятна на обеих ногах). None — без отсева
HEM_H = None                       # профиль pant_hem, м (23.10, агент fix-a, NYR): полосы низа шорт — от края штанины до
#                                    этой высоты (hem). У NHL 27 NYR по низу штанин две полосы (белая, синяя, белая) и боковые
#                                    полосы переходят в них буквой «Т»; шорты Legacy короче и с подворотом, переносом по
#                                    ближайшей точке полосы низа рвались на клочки (пользователь, 23.10: «артефакты на
#                                    трусах»). None — как было
HEM_BLEND = 0.03                   # м: верх зоны hem — плавный переход к прежнему переносу
HEM_SS = 4                         # сверхвыборка hem (у ss 2 края полос в 512² лесенкой по текселю)
MASK_KIND = {"front_left": "front", "front_right": "front", "back": "back"}   # вид нашивки для масок (apply masks=…)
MASKS = "pant_decals_a.png"        # маски нашивок рядом с pant_cm.png (стадия kit): R — гербы спереди, G — щит сзади,
#                                    B — прочие; по R стадия slot кладёт рельеф и блеск (relief)
# рамки нашивок шорт EA (uv развёртки шорт Legacy; центры рамок): щит — одна рамка у всех 84 форм EA, герб слева —
# среднее рамок 1_14_0, 1_16_2, 1_1_3, 1_23_0, 1_24_3, справа — 1_20_0, 1_131_0, 1_20_3, 1_23_6. С 24.10 — только окна
# поиска гербов образца (template_patches, рельеф); место наших нашивок — LEG_SLOTS (до 24.10: центр рамки + 3 см
# `lift` по сетке вратаря, «слишком низко» 21.10 → «слишком высоко» 24.10 после игры)
EA_SLOTS = {"back": {"uv": (0.1275, 0.3545)},
            "front_left": {"uv": (0.131, 0.613)},
            "front_right": {"uv": (0.881, 0.586)}}
# Сетка шорт полевых в игре (24.10). pilot.PANT_L (pant_1_0_0_2) — шорты вратаря: шорты — pant_G_X_U_L, G — вратарь
# (docs/player-models.md §1), у полевых — pant_0_X_U_L, а в cache: pant_0_0_* — копии pant_0_1_* (installed-pantsock
# 15.10): у всех полевых в игре сетка pant_0_1_0 (заправлен свитер — U = 1 — у одного игрока базы). Развёртка у сеток
# общая (текстура одна), шорты полевых — размера шорт NHL 24/27 (x ±0,255 против ±0,246 м; край штанины спереди
# 0,653, сзади 0,701, подворот — нижние 3 см).
GAME_MESH = "rendering/pant/pant_0_1_0_2.rx2"
# Место нашивок на ноге (24.10, пользователь после игры: «логотипы и щиты на шортах стоят слишком высоко … поставь
# реалистично»; прежде — «криво, не того размера, у самого края»). Угол phi — вокруг оси ноги от середины переда
# наружу (fb.pant_decals.leg_frame: 0 — перед, 90 — бок, 180 — зад), d — высота центра над краем штанины под этим углом,
# bottom — низ нашивки не ниже (подворот шорт полевых — 3 см). Замер на сетке игры (qa/pants2/measure.py):
#   герб: NHL 27 — центр 7,2 см (медиана 15 клубов; 25 % видимой высоты шорт), угол 15–27° (COL 53, NJD 40); EA — 11,3
#         (36 %), угол 21°; наш до 24.10 — 12,7 (нога +x, 32°) и 14,5 (нога −x, 19°) — «слишком высоко». Взято
#         8,5 см (27 % видимой высоты 31 см — как NHL 27; ниже EA на 3 см), угол 22° на обеих ногах;
#   щит:  NHL 27 — 6,6 см над краем сзади, 150° (видимая высота сзади 24 см у NHL 24 и 23,5 у Legacy); EA и наш до
#         24.10 — 10,3, 160°. Взято 7 см (низ 4,5 — над подворотом), 150°.
# scale — размер герба к размеру у источника (1 — как у NHL 27: шорты одного размера), max — длинная сторона не больше
# (м); h — высота щита (м): 5,1 см — щит EA в игре (у NHL 27 — 4,7).
LEG_SLOTS = {"front": {"phi": 22.0, "d": 0.085, "bottom": 0.05, "scale": 1.0, "max": 0.14},
             "back": {"phi": 150.0, "d": 0.07, "bottom": 0.045, "h": 0.051}}
PLACE_TOL = {"d": 0.015, "phi": 10.0, "aspect": 0.12, "wrap": 40.0}   # place_check (kitport audit, pant_place): центр от
#                                    правила дальше (м, град), пропорции против источника (доля), изгиб под нашивкой (град)
_GAME = {}


def _surface(mesh, size):
    """Тексели развёртки сетки (size²): маска, 3D-точки, нормали (по треугольникам, интерполяция по вершинам)."""
    from . import kit3d
    tid, bar = kit3d.raster_uv(mesh, size)
    ok = tid >= 0
    tri = mesh["tri"][tid[ok]]
    P = np.zeros(tid.shape + (3,))
    P[ok] = (bar[ok][:, :, None] * mesh["pos"][tri]).sum(1)
    nv = mesh.get("nrm")
    if nv is None or len(nv) != len(mesh["pos"]):
        a, b, c = (mesh["pos"][mesh["tri"][:, i]] for i in range(3))
        fn = np.cross(b - a, c - a)
        nv = np.zeros_like(mesh["pos"])
        for i in range(3):
            np.add.at(nv, mesh["tri"][:, i], fn)
    nv = nv / np.maximum(np.linalg.norm(nv, axis=1, keepdims=True), 1e-12)
    N = np.zeros_like(P)
    N[ok] = (bar[ok][:, :, None] * nv[tri]).sum(1)
    N[ok] /= np.maximum(np.linalg.norm(N[ok], axis=1, keepdims=True), 1e-12)
    return ok, P, N


def _basis(n):
    """Касательный базис: up — мировая y в плоскости, right = up × n (у переда, n ≈ +z, right ≈ +x)."""
    up = np.array([0.0, 1.0, 0.0]) - n[1] * n
    if np.linalg.norm(up) < 1e-6:
        up = np.array([0.0, 0.0, 1.0]) - n[2] * n
    up /= np.linalg.norm(up)
    return np.cross(up, n), up


def decals(color, base, diff=DIFF, min_px=MIN_PX):
    """Связные части «color − base_color» → [маска (bool, как текстура)] (нашивки по одной)."""
    from scipy import ndimage as ndi
    if base.shape[:2] != color.shape[:2]:                # NHL 24 MIN: color 1024², base_color 2048² (22.10 — MIN с
        from PIL import Image                            # наклейками шорт не собирался: «shapes (1024,1024,3) (2048,…»)
        base = np.stack([np.asarray(Image.fromarray(base[..., k].astype(np.float32)).resize(color.shape[1::-1],
                                                                                          Image.BILINEAR))
                         for k in range(3)], -1)
    d = np.abs(color[..., :3] - base[..., :3]).max(-1) > diff
    lab, n = ndi.label(ndi.binary_dilation(d, iterations=max(3, (MERGE_PX + 1) // 2)))   # MERGE_PX: части рядом — одна
    out = []
    for i in range(1, n + 1):
        m = (lab == i) & d
        if m.sum() >= min_px:
            out.append(ndi.binary_dilation(m, iterations=2) & (lab == i))
    return out


def sticker(color, mask, ok, P, N):
    """Нашивка источника → наклейка в метрах: (RGBA float, центр, нормаль, базис, x0, y0) — пиксель RES."""
    from scipy import ndimage as ndi
    sel = mask & ok
    c = P[sel].mean(0)
    n = N[sel].mean(0)
    n /= np.linalg.norm(n)
    right, up = _basis(n)
    D = P[sel] - c
    lx, ly = D @ right, D @ up
    x0, y0 = lx.min() - 2 * RES, ly.min() - 2 * RES
    w = int(np.ceil((lx.max() - x0) / RES)) + 3
    h = int(np.ceil((ly.max() - y0) / RES)) + 3
    acc = np.zeros((h, w, 4))
    cnt = np.zeros((h, w))
    ix = np.clip(((lx - x0) / RES).astype(int), 0, w - 1)
    iy = np.clip(((ly - y0) / RES).astype(int), 0, h - 1)
    col = color[sel][:, :3]
    np.add.at(acc, (iy, ix), np.concatenate([col, np.ones((len(col), 1))], 1))
    np.add.at(cnt, (iy, ix), 1)
    have = cnt > 0                                  # дырки (тексель источника крупнее пикселя наклейки) — соседями
    if (~have).any():
        idx = ndi.distance_transform_edt(~have, return_distances=False, return_indices=True)
        near = have[idx[0], idx[1]] & (ndi.distance_transform_edt(~have) <= 2.5)
        acc = np.where(near[..., None], acc[idx[0], idx[1]], 0)
        cnt = np.where(near, cnt[idx[0], idx[1]], 0)
    rgba = np.zeros((h, w, 4))
    k = cnt > 0
    rgba[k, :3] = acc[k, :3] / acc[k, 3:4]
    rgba[..., 3] = ndi.gaussian_filter(k.astype(np.float64), 0.6)   # мягкий край
    return rgba, c, n, (right, up), x0, y0


def _sample(img, x, y):
    """Билинейно img[h, w, C] в точках (x, y) пикселей; вне — 0."""
    h, w = img.shape[:2]
    x0, y0 = np.floor(x).astype(int), np.floor(y).astype(int)
    fx, fy = x - x0, y - y0
    out = np.zeros(x.shape + img.shape[2:])
    for dx, dy, wt in ((0, 0, (1 - fx) * (1 - fy)), (1, 0, fx * (1 - fy)), (0, 1, (1 - fx) * fy), (1, 1, fx * fy)):
        xx, yy = x0 + dx, y0 + dy
        inside = (xx >= 0) & (xx < w) & (yy >= 0) & (yy < h)
        v = np.zeros(x.shape + img.shape[2:])
        v[inside] = img[yy[inside], xx[inside]]
        out += v * wt[..., None]
    return out


def slot_of(c, n):
    """Место EA для нашивки с центром c и нормалью n на сетке источника: back, front_left, front_right или None."""
    if n[2] < -0.2:
        return "back"
    if n[2] > 0.2:
        return "front_left" if c[0] < 0 else "front_right"
    return None


def game_mesh(src_mesh=None):
    """Сетка шорт полевых в игре (GAME_MESH) и — если дан src_mesh (шорты NHL 24) — она же, выровненная по рамке
    источника, как ткань в fb.pilot (низ — край штанины, верх — pilot.PANT_WAIST): для нашивок «по точке источника».
    -> (сетка, выровненная или None)."""
    from . import kit3d, pilot
    if "mesh" not in _GAME:
        _GAME["mesh"] = kit3d.load_legacy(GAME_MESH)
    m = _GAME["mesh"]
    if src_mesh is None:
        return m, None
    bN = kit3d.bbox(src_mesh)
    bN[3] = pilot.PANT_WAIST
    return m, kit3d.aligned(m, bN, kit3d.bbox(m))


def leg_spot(kind, leg, h, ok, P, N, frames):
    """Центр нашивки вида kind (front | back) на ноге leg (знак x) по правилу LEG_SLOTS: тексель снаружи ноги с углом phi
    вокруг ноги и высотой центра над краем штанины max(d, bottom + h/2) (h — высота нашивки, м). -> (iy, ix)."""
    sp = LEG_SLOTS[kind]
    dt = max(sp["d"], sp["bottom"] + h / 2)
    fr = frames[leg]
    s = ok & (np.sign(P[..., 0]) == leg)
    ys, xs = np.nonzero(s)
    phi, d, radn = _leg_coords(P[s], N[s], fr, leg)
    r = np.hypot(P[s][:, 0] - fr[0], P[s][:, 2] - fr[1])
    dphi = (phi - sp["phi"] + 180) % 360 - 180
    cost = (np.radians(dphi) * r) ** 2 + (d - dt) ** 2       # м² по поверхности: дуга вокруг ноги и высота
    cost[radn < 0.3] = np.inf                              # снаружи ноги, не изнанка подворота
    j = int(np.argmin(cost))
    return ys[j], xs[j]


def placement(a, ok, P, N, frames, n0=None):
    """Где лежит нашивка с альфой a (S², 0…1) на сетке (ok, P, N — её тексели S², frames — leg_frame по ногам):
    центр (φ, d над краем, м), низ и верх (d), ширина и высота в касательной плоскости (м), изгиб — наибольший угол
    нормали текселей нашивки к нормали центра (град; у края штанины, на загибе — велик). -> dict или None."""
    sel = ok & (a > 0.5)
    if sel.sum() < 8:
        return None
    w = a[sel]
    Q, NN = P[sel], N[sel]
    c = (Q * w[:, None]).sum(0) / w.sum()
    n = (NN * w[:, None]).sum(0) if n0 is None else n0
    n = n / np.linalg.norm(n)
    right, up = _basis(n)
    leg = 1 if c[0] >= 0 else -1
    phi, d, _ = _leg_coords(Q, NN, frames[leg], leg)
    pc, dc, _ = _leg_coords(c[None], n[None], frames[leg], leg)
    D = Q - c
    return {"leg": leg, "phi": round(float(pc[0]), 1), "d": round(float(dc[0]), 4),
            "bottom": round(float(np.percentile(d, 1)), 4), "top": round(float(np.percentile(d, 99)), 4),
            "w": round(float(np.ptp(D @ right)), 4), "h": round(float(np.ptp(D @ up)), 4),
            "wrap": round(float(np.degrees(np.arccos(np.clip(NN @ n, -1, 1))).max()), 1)}


def apply(img, color, base, src_mesh, size=512, ss=2, report=None, slots=True, masks=None, dst=None):
    """Нашивки (color − base) поверх img — переноса base на развёртку шорт Legacy (size², RGB float) → img и [описание].
    Нашивки ложатся на сетку шорт полевых в игре (GAME_MESH; dst — (сетка, выровненная по источнику) вместо неё).
    slots — места по правилу ноги (LEG_SLOTS: герб спереди, щит сзади), иначе — все по точке источника. masks —
    словарь: в него альфа нашивок (size², 0…1) по видам MASK_KIND (front — гербы спереди, back — щит сзади, other — по
    точке источника): по ней рельеф (relief)."""
    from . import kit3d
    S = size * ss
    G, Ga = dst if dst is not None else game_mesh(src_mesh)
    ok_s, P_s, N_s = _surface(src_mesh, color.shape[0])
    ok_a, P_a, N_a = _surface(Ga, S)
    ok_d, P_d, N_d = _surface(G, S)
    frames = {leg: leg_frame(G, leg) for leg in (-1, 1)}
    bd, br = np.array(kit3d.bbox(Ga)), np.array(kit3d.bbox(G))
    scale = (br[3] - br[2]) / max(bd[3] - bd[2], 1e-9)       # высота шорт игры / видимая высота источника
    hi = np.zeros((S, S, 3))
    a_hi = np.zeros((S, S))
    a_kind = {}                                          # альфа по видам нашивок (masks)
    rep = []
    for m in decals(color, base):
        rgba, c, n, (right, up), x0, y0 = sticker(color, m, ok_s, P_s, N_s)
        if Y_MAX is not None and c[1] > Y_MAX:           # пояс под свитером — не нашивка (Y_MAX_DEFAULT; DAL, WPG)
            rep.append({"slot": "skip", "src_center": np.round(c, 3).tolist(), "why": f"y > {Y_MAX}"})
            continue
        slot = slot_of(c, n) if slots else None
        k = scale
        hw = np.array(rgba.shape[:2]) * RES              # высота, ширина наклейки у источника, м
        if slot:                                         # правило ноги: размер, затем центр (низ — по высоте нашивки)
            kind = MASK_KIND[slot]
            sp = LEG_SLOTS[kind]
            k = sp["h"] / hw[0] if "h" in sp else sp.get("scale", 1.0)
            if "max" in sp and hw.max() * k > sp["max"]:
                k = sp["max"] / hw.max()
            iy, ix = leg_spot(kind, 1 if c[0] >= 0 else -1, hw[0] * k, ok_d, P_d, N_d, frames)
        else:                                            # центр → ближайший тексель выровненной сетки игры,
            dd = np.linalg.norm(P_a - c, axis=-1)        # повёрнутый так же (не другая нога и не изнанка)
            dd[~ok_a | ((N_a @ n) < FACING)] = np.inf
            iy, ix = np.unravel_index(np.argmin(dd), dd.shape)
        cL, nL = P_d[iy, ix], N_d[iy, ix]
        rL, uL = _basis(nL)
        D = P_d - cL
        near = ok_d & (np.abs(D @ nL) < SLAB) & ((N_d @ nL) > FACING)
        lx = (D @ rL) / k
        ly = (D @ uL) / k
        px = (lx - x0) / RES
        py = (ly - y0) / RES
        near &= (px > -1) & (py > -1) & (px < rgba.shape[1]) & (py < rgba.shape[0])
        s = _sample(rgba, px[near], py[near])
        a = s[:, 3].clip(0, 1)
        hi[near] = hi[near] * (1 - a[:, None]) + s[:, :3] * a[:, None]
        a_hi[near] = a_hi[near] + a * (1 - a_hi[near])
        ak = a_kind.setdefault(MASK_KIND.get(slot, "other"), np.zeros((S, S)))
        ak[near] = ak[near] + a * (1 - ak[near])
        one = np.zeros((S, S))
        one[near] = a
        pl = placement(one, ok_d, P_d, N_d, frames, nL)
        r = {"slot": slot or "source", "src_center": np.round(c, 3).tolist(),
             "dst_uv": [round(float(ix) / S, 3), round(float(iy) / S, 3)],
             "size_cm": [round(rgba.shape[1] * RES * k * 100, 1), round(rgba.shape[0] * RES * k * 100, 1)],
             "src_cm": [round(rgba.shape[1] * RES * 100, 1), round(rgba.shape[0] * RES * 100, 1)]}
        if pl:                                           # где нашивка на ноге в игре (см): угол, высота центра, низ, верх
            r["leg_cm"] = {"phi": pl["phi"], "d": round(pl["d"] * 100, 1), "bottom": round(pl["bottom"] * 100, 1),
                           "top": round(pl["top"] * 100, 1), "w": round(pl["w"] * 100, 1), "h": round(pl["h"] * 100, 1),
                           "wrap": pl["wrap"]}
        rep.append(r)
    if not [r for r in rep if r["slot"] != "skip"]:
        return img, rep
    box = lambda x: x.reshape(size, ss, size, ss, *x.shape[2:]).mean((1, 3))
    if masks is not None:
        masks.update({kd: box(ak) for kd, ak in a_kind.items()})
    a = box(a_hi)
    col = box(hi * a_hi[..., None]) / np.maximum(a[..., None], 1e-6)
    out = img[..., :3] * (1 - a[..., None]) + col * a[..., None]
    if img.shape[-1] > 3:
        out = np.concatenate([out, img[..., 3:]], -1)
    if report is not None:
        report.extend(rep)
    return out, rep


def leg_frame(m, leg, nh=3):
    """Нога шорт (leg −1 / +1 — знак x) у низа: центр (x, z) и край низа по углу φ вокруг ноги (0 — перед, 90 — наружу,
    ±180 — сзади): минимум y поверхности (тексели 1024²) в секторах 3°, сглажено рядом Фурье до nh гармоник — край без
    зубцов от редких вершин подворота Legacy. -> (cx, cz, φ секторов, y края)."""
    from . import kit3d
    if "_dense" not in m:
        tid, bar = kit3d.raster_uv(m, 1024)
        ok = tid >= 0
        m["_dense"] = (bar[ok][:, :, None] * m["pos"][m["tri"][tid[ok]]]).sum(1)
    P = m["_dense"]
    s = np.sign(P[:, 0]) == leg
    low = s & (P[:, 1] < P[s, 1].min() + 0.15)
    cx, cz = P[low, 0].mean(), P[low, 2].mean()
    phi = np.degrees(np.arctan2((P[low, 0] - cx) * leg, P[low, 2] - cz))
    bins = np.arange(-180, 181, 3.0)
    c = (bins[:-1] + bins[1:]) / 2
    yb = np.full(len(c), np.nan)
    for i in range(len(c)):
        q = (phi >= bins[i]) & (phi < bins[i + 1])
        if q.any():
            yb[i] = P[low][q, 1].min()

    def basis(th):
        return np.column_stack([np.ones(len(th))] + [f(k * th) for k in range(1, nh + 1) for f in (np.cos, np.sin)])
    ok = ~np.isnan(yb)
    coef = np.linalg.lstsq(basis(np.radians(c[ok])), yb[ok], rcond=None)[0]
    return cx, cz, c, basis(np.radians(c)) @ coef


def _leg_coords(P, N, frame, leg):
    """Точки ноги → (φ, высота над краем низа d, радиальная доля нормали: > 0 — снаружи, < 0 — изнанка)."""
    cx, cz, c, yb = frame
    rx, rz = P[:, 0] - cx, P[:, 2] - cz
    phi = np.degrees(np.arctan2(rx * leg, rz))
    d = P[:, 1] - np.interp(phi, c, yb, period=360)
    radn = (rx * N[:, 0] + rz * N[:, 2]) / np.maximum(np.hypot(rx, rz), 1e-9)
    return phi, d, radn


def _column_shift(phL, phS, d, outer, d0, d1, step=1.0):
    """Поправка угла «источник − Legacy» по столбцам (секторы step° угла Legacy): медиана снаружи у верха зоны (d0…d1 —
    там, где hem переходит в перенос), между секторами — линейно по кругу. Угол точки переноса у паха менялся с высотой —
    концы полос у внутренней стороны бедра шли наискось и зубцами (NYR 23.10); с поправкой край полосы — по углу Legacy,
    вертикально, а у верха зоны угол — как у переноса (боковые полосы — одной линией). -> поправка, град."""
    dl = (phS - phL + 180) % 360 - 180
    sel = outer & (d >= d0) & (d <= d1)
    c = np.arange(-180, 180, step) + step / 2
    ib = np.clip(((phL[sel] + 180) / step).astype(int), 0, len(c) - 1)
    med = np.full(len(c), np.nan)
    for i in np.unique(ib):
        med[i] = np.median(dl[sel][ib == i])
    ok = ~np.isnan(med)
    if not ok.any():
        return dl
    return np.interp(phL, c[ok], med[ok], period=360)


def hem(img, base, src_mesh, dst_aligned, dst_mesh, size=512, ss=None, h=None, blend=None):
    """Низ шорт «от края штанины» (как fb.hem у свитера, но по каждой ноге): тексель Legacy у низа (d < h над краем) →
    точка источника той же ноги с тем же φ и той же высотой над своим краем (d в метрах — полосы толщины NHL 27) → цвет
    base. φ — у точки, найденной переносом (ближайшая точка выровненной сетки, kit3d.project): боковые полосы над зоной
    и в ней — одной линией. Снаружи и изнанка — по своим слоям источника (у края они сходятся подворотом). Выше h − blend
    — плавно к прежнему переносу img. img — перенос base (size², RGB float). -> картинка."""
    from . import kit3d
    from . import hem as H
    h = HEM_H if h is None else h
    blend = HEM_BLEND if blend is None else blend
    ss = HEM_SS if ss is None else ss
    if not h:
        return img
    S = size * ss
    tid, bar = kit3d.raster_uv(dst_mesh, S)
    mask = tid >= 0
    b = bar[mask]
    T = dst_mesh["tri"][tid[mask]]
    Pd = (b[:, :, None] * dst_mesh["pos"][T]).sum(1)
    Nd = kit3d._unit((b[:, :, None] * dst_mesh["nrm"][T]).sum(1))
    Pa = (b[:, :, None] * dst_aligned["pos"][T]).sum(1)
    Na = kit3d._unit((b[:, :, None] * dst_aligned["nrm"][T]).sum(1))
    sP, sT = src_mesh["pos"], src_mesh["tri"]
    col = np.zeros((len(Pd), 3))
    w = np.zeros(len(Pd))
    for leg in (-1, 1):
        fs, fd = leg_frame(src_mesh, leg), leg_frame(dst_mesh, leg)
        phs, ds, rs = _leg_coords(sP, src_mesh["nrm"], fs, leg)
        _, dL, rL = _leg_coords(Pd, Nd, fd, leg)
        zone = (np.sign(Pd[:, 0]) == leg) & (dL < h)
        if not zone.any():
            continue
        st, sb, _ = kit3d.project(Pa[zone], Na[zone], src_mesh)
        Ps = (sb[:, :, None] * sP[sT[st]]).sum(1)
        phq = np.degrees(np.arctan2((Ps[:, 0] - fs[0]) * leg, Ps[:, 2] - fs[1]))
        phL = _leg_coords(Pd[zone], Nd[zone], fd, leg)[0]   # одна поправка угла на столбец Legacy (по верху зоны)
        phq = phL + _column_shift(phL, phq, dL[zone], rL[zone] > 0, h - blend, h)
        idx = np.nonzero(zone)[0]
        side = np.sign(sP[:, 0]) == leg
        for outer in (True, False):
            tri = sT[side[sT].all(1) & ((rs[sT].mean(1) > 0) == outer)]
            grid = H.polar_grid(tri, phs, ds, src_mesh["uv"], h + 0.01)
            q = (rL[zone] > 0) == outer
            uv, found = H.lookup(grid, phq[q], dL[zone][q], reach=40)
            j = idx[q][found]
            col[j] = kit3d.sample_bilinear(base[..., :3], uv[found, 0], uv[found, 1])
            t = np.clip((h - dL[j]) / blend, 0, 1)
            w[j] = t * t * (3 - 2 * t)
    L = np.zeros((S, S, 3))
    W = np.zeros((S, S))
    L[mask], W[mask] = col * w[:, None], w
    L = L.reshape(size, ss, size, ss, 3).mean((1, 3))
    W = W.reshape(size, ss, size, ss).mean((1, 3))
    out = np.array(img, dtype=np.float64, copy=True)
    out[..., :3] = out[..., :3] * (1 - W[..., None]) + L
    return out


# ---------------------------------------------------------------- рельеф и блеск нашивок (стадия slot, pant = "source")
# Пользователь, 23.10 (DET): «логотип на трусах стоит выше и сбоку относительно рельефного места». Рельеф (pant_nm) и блеск
# (pant_sm) у шорт pant = "source" — образца Legacy, с его гербом EA на его месте, а цвет (pant_cm) — NHL 27 с нашим гербом
# в другом месте (тогда по рамке EA + 3 см, с 24.10 — LEG_SLOTS) и на той ноге, где у источника. Отсюда: рельеф ниже и
# сбоку от герба (DET, MTL, VAN …), рельеф на другой ноге (BOS, ANA, OTT …), пустой рельеф без герба (LAK, TOR, BUF …).
# Теперь: нашивки образца стираются в pant_nm и pant_sm (kitpaint.erase, гладко), рельеф и блеск — по альфе наших нашивок
# (маска MASKS со стадии kit: R — гербы, G — щит). Щит NHL сзади до 24.10 был у нас в рамке EA (рельеф совпадал); с 24.10
# он ниже (LEG_SLOTS) — щит образца тоже стирается, а наш получает рельеф.
EA_SHIELD_BOX = (0.107, 0.338, 0.148, 0.371)   # рамка щита NHL сзади (uv) — одна у всех 84 форм EA (замер 21.10): у
#                                    SEA 1_100, UTA 1_104, CGY 1_4, VGK 1_101 щит по цвету не выделяется (светлый на светлом,
#                                    рядом панель) — тогда стирается рамка
TPL_WIN = 0.085                    # полуширина окна поиска герба образца вокруг рамки EA (uv; герб EA ~0,08 по диагонали)
TPL_THR = 34.0                     # тексель герба образца — цвет дальше стольких (евклид RGB) от ткани окна (медианы)
TPL_CLOSE = 2                      # замыкание (тексели) до заливки дыр: штрихи надписи — одним пятном (Reebok у VGK 1_101)
TPL_MIN_PX = 150                   # часть меньше (после заливки дыр и размыкания) — потёртость, складка, шов
TPL_EDGE_PX = 3                    # часть у края окна — полоса, пояс, панель (CBJ, NYR, пояс VGK, PIT), не нашивка
TPL_DILATE = 3                     # стирание с запасом: рельеф EA шире цветного герба на 1–2 текселя
RELIEF_SIGN = (-1.0, 1.0)          # знак рельефа (как kitpaint): у образца с гербом — по нему (kitpaint.relief_calibrate)
RELIEF_K = 140.0                   # сила: сдвиг нормали (0–255) на единицу наклона высоты. Подбор по виду рядом с EA (DET,
#                                    BOS, 23.10): 60 (как kitpaint) — еле виден, 140 — как вышивка EA. Подбор по энергии
#                                    рельефа герба образца давал 30 у ANA, STL, UTA, OTT (рельеф — широкая плашка, складки
#                                    ткани сильнее) — у UTA рельефа не видно, отказались
RELIEF_INNER = 0.5                 # доля яркости цвета в высоте: рисунок внутри герба виден в рельефе, как вышивка у EA
RELIEF_BLUR = 0.6                  # σ размытия высоты, тексели 512² (у EA края вышивки — в 1–2 текселя)
RELIEF_SMOOTH = 2.0                # σ сглаживания складок ткани под гербом (нашивка ровнее ткани)
RELIEF_LEFT = 0.35                 # relief_check: остаток рельефа герба образца (доля) — больше: не стёрт
RELIEF_MIN = 1.4                   # relief_check: энергия рельефа по краю нашего герба / фон — меньше: рельефа нет
RELIEF_MEASURABLE = 2.0            # relief_check: рельеф герба образца сильнее фона меньше чем на столько — не мерится
_PANT_SURF = {}


def template_patches(cm, slots=("front_left", "front_right", "back")):
    """Гербы спереди и щит NHL сзади у шорт образца Legacy (cm 512², RGB): у EA нашивка — в цвете (cm), рельефе (nm) и
    блеске (sm) в одном месте, ищется по цвету в окнах рамок EA (EA_SLOTS): отличие от ткани окна > TPL_THR, дыры
    залиты, тонкое (потёртости, швы) снято размыканием, части у края окна (полосы, пояс, панели) и мельче TPL_MIN_PX —
    не нашивка. Щит — часть с центром в рамке EA_SHIELD_BOX, а не нашёлся по цвету — сама рамка ("box": True).
    -> [{"slot", "uv", "px", "mask"[, "box"]}] (mask — bool как cm)."""
    from scipy import ndimage as ndi
    H, W = cm.shape[:2]
    out = []
    for slot in slots:
        u, v = EA_SLOTS[slot]["uv"]
        x0, x1 = max(0, int((u - TPL_WIN) * W)), min(W, int((u + TPL_WIN) * W))
        y0, y1 = max(0, int((v - TPL_WIN) * H)), min(H, int((v + TPL_WIN) * H))
        win = cm[y0:y1, x0:x1, :3].astype(np.float64)
        body = np.median(win.reshape(-1, 3), 0)
        d = np.sqrt(((win - body) ** 2).sum(-1)) > TPL_THR
        d = ndi.binary_opening(ndi.binary_fill_holes(ndi.binary_closing(d, iterations=TPL_CLOSE)))
        lab, n = ndi.label(d)
        for i, sl in enumerate(ndi.find_objects(lab), 1):
            m = lab == i
            if (m.sum() < TPL_MIN_PX or sl[0].start < TPL_EDGE_PX or sl[1].start < TPL_EDGE_PX
                    or sl[0].stop > m.shape[0] - TPL_EDGE_PX or sl[1].stop > m.shape[1] - TPL_EDGE_PX):
                continue
            full = np.zeros((H, W), bool)
            full[y0:y1, x0:x1] = m
            ys, xs = np.nonzero(full)
            uc, vc = float(xs.mean()) / W, float(ys.mean()) / H
            if slot == "back" and not (EA_SHIELD_BOX[0] - 0.01 <= uc <= EA_SHIELD_BOX[2] + 0.01
                                       and EA_SHIELD_BOX[1] - 0.01 <= vc <= EA_SHIELD_BOX[3] + 0.01):
                continue                            # не щит: рядом с рамкой бывают надписи и полосы
            out.append({"slot": slot, "uv": (round(uc, 3), round(vc, 3)), "px": int(m.sum()), "mask": full})
        if slot == "back" and not any(f["slot"] == "back" for f in out):
            full = np.zeros((H, W), bool)
            full[int(EA_SHIELD_BOX[1] * H):int(np.ceil(EA_SHIELD_BOX[3] * H)),
                 int(EA_SHIELD_BOX[0] * W):int(np.ceil(EA_SHIELD_BOX[2] * W))] = True
            out.append({"slot": "back", "uv": (round((EA_SHIELD_BOX[0] + EA_SHIELD_BOX[2]) / 2, 3),
                                               round((EA_SHIELD_BOX[1] + EA_SHIELD_BOX[3]) / 2, 3)),
                        "px": int(full.sum()), "mask": full, "box": True})
    return out


def _pant_points(size=512):
    """Тексели развёртки шорт полевых в игре (GAME_MESH) size²: маска и 3D-точки (для расстояний в см)."""
    if size not in _PANT_SURF:
        ok, P, _ = _surface(game_mesh()[0], size)
        _PANT_SURF[size] = (ok, P)
    return _PANT_SURF[size]


def _center3d(mask, w=None):
    ok, P = _pant_points(mask.shape[0])
    sel = mask & ok
    if not sel.any():
        return None
    wt = np.ones(int(sel.sum())) if w is None else w[sel]
    return (P[sel] * wt[:, None]).sum(0) / max(wt.sum(), 1e-9)


def _hp_energy(N, mask):
    """Средний модуль высоких частот нормалей (R, G; σ 3) в маске — сила рельефа."""
    from scipy import ndimage as ndi
    e = sum(np.abs(N[..., c] - ndi.gaussian_filter(N[..., c], 3.0)) for c in (0, 1))
    return float(e[mask].mean()) if mask.any() else 0.0


def _height(A, cm):
    from scipy import ndimage as ndi
    L = (0.2126 * cm[..., 0] + 0.7152 * cm[..., 1] + 0.0722 * cm[..., 2]) / 255.0
    return ndi.gaussian_filter(A * (1 - RELIEF_INNER) + RELIEF_INNER * L * A, RELIEF_BLUR)


def _renorm(N, m):
    fx, fy = N[..., 0] / 127.5 - 1, N[..., 1] / 127.5 - 1
    z = np.sqrt(np.clip(1 - fx * fx - fy * fy, 0, 1)) * 127.5 + 127.5
    N[..., 2] = np.where(m, z, N[..., 2])


def relief(tpl_dir, out_dir, masks_png):
    """Рельеф и блеск шорт pant = "source" (стадия slot, fb.edge_kit.cmd_slot): pant_nm, pant_sm образца tpl_dir — без его
    гербов спереди (template_patches → kitpaint.erase, гладко) и с рельефом и блеском наших гербов (R маски masks_png,
    цвет — out_dir/pant_cm.png) → out_dir/pant_nm.png, pant_sm.png. Знак рельефа и блеск вышивки — как у герба
    образца (если он есть), сила — RELIEF_K. -> описание (dict; "skip" — маски нет, файлы образца как есть)."""
    import math
    import os
    import sys
    from PIL import Image
    from scipy import ndimage as ndi
    if not os.path.exists(masks_png):
        return {"skip": f"нет {os.path.basename(masks_png)}: рельеф образца как есть (шорты собраны до 23.10 — "
                        "kitport build --club … --stages pant,slot)"}
    tools = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if tools not in sys.path:
        sys.path.insert(0, tools)
    import kitpaint as kp
    tcm = np.asarray(Image.open(os.path.join(tpl_dir, "pant_cm.png")).convert("RGB"))
    nm = kp.Img.load(os.path.join(tpl_dir, "pant_nm.png"))
    sm = kp.Img.load(os.path.join(tpl_dir, "pant_sm.png"))
    N0 = np.frombuffer(bytes(nm.px), np.uint8).reshape(nm.h, nm.w, 4).astype(np.float64)
    S0 = np.frombuffer(bytes(sm.px), np.uint8).reshape(sm.h, sm.w, 4).astype(np.float64)
    found = template_patches(tcm)
    AA = np.asarray(Image.open(masks_png).convert("RGB")).astype(np.float64) / 255.0
    kinds = {"front": AA[..., 0], "back": AA[..., 1]}       # R — гербы спереди, G — щит сзади (24.10)
    A = np.maximum(kinds["front"], kinds["back"])
    ocm = np.asarray(Image.open(os.path.join(out_dir, "pant_cm.png")).convert("RGB")).astype(np.float64)
    if A.shape != N0.shape[:2] or ocm.shape[:2] != N0.shape[:2] or tcm.shape[:2] != N0.shape[:2]:
        sys.exit(f"pant_decals.relief: размеры {masks_png} {A.shape}, pant_cm {ocm.shape[:2]}, образца "
                 f"{tcm.shape[:2]} / {N0.shape[:2]} — нужны одинаковые (512²)")
    Hh = _height(A, ocm)
    gy, gx = np.gradient(Hh)
    sign, k, gloss = RELIEF_SIGN, RELIEF_K, {}
    info = {"template": [], "ours": []}
    real = [f for f in found if not f.get("box")]   # рамка без щита по цвету — не образец знака и блеска
    if real:
        big = max(real, key=lambda f: (f["slot"] != "back", f["px"]))   # знак — по гербу, нет герба — по щиту
        kc = kp.relief_calibrate(nm, bytearray(big["mask"].astype(np.uint8).tobytes()))
        if kc and max(abs(kc[0]), abs(kc[1])) > 6:
            sign = (math.copysign(1.0, kc[0]), math.copysign(1.0, kc[1]))
    for kind in ("front", "back"):                  # блеск вышивки — герба образца для гербов, щита — для щита
        fs = [f for f in real if MASK_KIND[f["slot"]] == kind]
        if fs:
            f2 = max(fs, key=lambda f: f["px"])["mask"].reshape(sm.h, nm.h // sm.h, sm.w, nm.w // sm.w).any((1, 3))
            if f2.any():
                gloss[kind] = float(np.median(S0[f2][:, :3].mean(1)))
    for kind, other in (("front", "back"), ("back", "front")):
        if kind not in gloss and other in gloss:
            gloss[kind] = gloss[other]
    for f in found:                                 # гербы образца — гладкой тканью (рельеф и блеск)
        m = ndi.binary_dilation(f["mask"], iterations=TPL_DILATE)
        mb = bytearray(m.astype(np.uint8).tobytes())
        kp.erase(nm, mb, chans=(0, 1), texture=False)
        kp.renormalize(nm, mb)
        m2 = m.reshape(sm.h, nm.h // sm.h, sm.w, nm.w // sm.w).any((1, 3))
        kp.erase(sm, bytearray(m2.astype(np.uint8).tobytes()), chans=(0, 1, 2), texture=False)
    N = np.frombuffer(bytes(nm.px), np.uint8).reshape(nm.h, nm.w, 4).astype(np.float64)
    S = np.frombuffer(bytes(sm.px), np.uint8).reshape(sm.h, sm.w, 4).astype(np.float64)
    on = ndi.binary_dilation(A > 0.01, iterations=2)
    if on.any():                                    # наши гербы: ткань под ними ровнее + наклон высоты
        for c, g in ((0, sign[0] * gx), (1, sign[1] * gy)):
            sm_c = ndi.gaussian_filter(N[..., c], RELIEF_SMOOTH)
            N[..., c] = np.where(on, np.clip(N[..., c] * (1 - A) + sm_c * A + k * g, 0, 255), N[..., c])
        _renorm(N, on)
        for kind, Ak in kinds.items():              # блеск вышивки — как у нашивки образца
            if kind in gloss:
                A2 = Ak.reshape(sm.h, nm.h // sm.h, sm.w, nm.w // sm.w).mean((1, 3))
                S[..., :3] = S[..., :3] * (1 - A2[..., None]) + gloss[kind] * A2[..., None]
    Image.fromarray(np.rint(N).astype(np.uint8), "RGBA").save(os.path.join(out_dir, "pant_nm.png"))
    Image.fromarray(np.rint(S).astype(np.uint8), "RGBA").save(os.path.join(out_dir, "pant_sm.png"))
    lab, n = ndi.label(A > 0.3)
    ours = [_center3d(lab == i) for i in range(1, n + 1)]
    for f in found:
        c = _center3d(f["mask"])
        d = [float(np.linalg.norm(c - o)) * 100 for o in ours if o is not None and c is not None]
        info["template"].append({"slot": f["slot"], "uv": f["uv"], "cm_to_ours": round(min(d), 1) if d else None})
    for i in range(1, n + 1):
        ys, xs = np.nonzero(lab == i)
        info["ours"].append({"uv": (round(float(xs.mean()) / A.shape[1], 3), round(float(ys.mean()) / A.shape[0], 3))})
    info.update(sign=sign, k=round(k, 1), gloss={kd: round(g, 1) for kd, g in gloss.items()} or None)
    return info


def relief_note(info):
    """Описание relief() одной строкой для журнала стадии slot."""
    if "skip" in info:
        return info["skip"]
    t = "; ".join(f"{f['slot']} uv {f['uv']}" + (f" ({f['cm_to_ours']} см до нашего)" if f["cm_to_ours"] is not None
                                                  else " (нашего рядом нет)") for f in info["template"]) or "нет"
    return (f"нашивки образца стёрты: {t}; наших нашивок с рельефом: {len(info['ours'])} (k {info['k']}, "
            f"блеск {info['gloss']})")


def relief_check(tpl_dir, slot_dir, masks_png):
    """Проверка (kitport audit): рельеф шорт слота — только под нашими нашивками. -> [замечание] и {замеры}.
    - герб или щит образца (template_patches) вне наших нашивок — его рельеф в pant_nm слота должен быть стёрт: остаток
      энергии рельефа сверх фона больше RELIEF_LEFT от исходной — «рельеф без нашивки» (до 23.10: DET, LAK, BOS …; щит —
      с 24.10, когда наш щит ушёл из рамки EA);
    - у нашей нашивки (R и G маски: гербы, щит) рельеф по краю — энергия не меньше RELIEF_MIN × фона рядом, иначе
      «нашивка без рельефа»."""
    import os
    from PIL import Image
    from scipy import ndimage as ndi
    if not os.path.exists(masks_png):
        return [f"шорты: нет маски нашивок {os.path.basename(masks_png)} (шорты до 23.10) — рельеф образца не по гербу; "
                "kitport build --stages pant,slot"], {}
    tcm = np.asarray(Image.open(os.path.join(tpl_dir, "pant_cm.png")).convert("RGB"))
    N0 = np.asarray(Image.open(os.path.join(tpl_dir, "pant_nm.png")).convert("RGB")).astype(np.float64)
    N1 = np.asarray(Image.open(os.path.join(slot_dir, "pant_nm.png")).convert("RGB")).astype(np.float64)
    AA = np.asarray(Image.open(masks_png).convert("RGB")).astype(np.float64) / 255.0
    A = np.maximum(AA[..., 0], AA[..., 1])               # гербы спереди и щит сзади
    ours = ndi.binary_dilation(A > 0.05, iterations=3)
    flags, meas = [], {"template": [], "ours": []}
    for f in template_patches(tcm):
        rest = f["mask"] & ~ours
        if rest.sum() < 0.15 * f["px"]:             # герб образца под нашим (почти совпали) — проверять нечего
            continue
        ring = ndi.binary_dilation(f["mask"], iterations=10) & ~ndi.binary_dilation(f["mask"], iterations=4) & ~ours
        e0, e1, bg = _hp_energy(N0, rest), _hp_energy(N1, rest), _hp_energy(N1, ring)
        if e0 - _hp_energy(N0, ring) < RELIEF_MEASURABLE:   # рельеф образца не сильнее складок (VGK 1_101)
            continue
        left = (e1 - bg) / max(e0 - bg, 1e-6)
        meas["template"].append({"slot": f["slot"], "uv": f["uv"], "left": round(left, 2)})
        if left > RELIEF_LEFT:
            c, o = _center3d(f["mask"]), _center3d(A > 0.3)
            far = f", {np.linalg.norm(c - o) * 100:.1f} см от наших нашивок" if c is not None and o is not None else ""
            what = "щита" if f["slot"] == "back" else "герба"
            flags.append(f"шорты: рельеф {what} образца без нашей нашивки ({f['slot']}, uv {f['uv']}{far}; "
                         f"остаток {left:.0%})")
    lab, n = ndi.label(A > 0.3)
    for i in range(1, n + 1):
        m = lab == i
        edge = ndi.binary_dilation(m, iterations=2) & ~ndi.binary_erosion(m, iterations=2)
        ring = ndi.binary_dilation(m, iterations=10) & ~ndi.binary_dilation(m, iterations=5)
        e, bg = _hp_energy(N1, edge), _hp_energy(N1, ring)
        ys, xs = np.nonzero(m)
        uv = (round(float(xs.mean()) / A.shape[1], 3), round(float(ys.mean()) / A.shape[0], 3))
        meas["ours"].append({"uv": uv, "edge_vs_bg": round(e / max(bg, 1e-6), 2)})
        if e < RELIEF_MIN * bg:
            flags.append(f"шорты: наша нашивка без рельефа (uv {uv}: край {e:.1f}, фон {bg:.1f})")
    return flags, meas


def place_check(masks_png, rep=None):
    """Проверка (kitport audit, `pant_place`): где нашивки шорт (маска MASKS: R — гербы спереди, G — щит сзади) лежат на
    сетке игры (GAME_MESH) против правила LEG_SLOTS: центр (угол, высота над краем — с поправкой на высоту нашивки),
    низ над подворотом, изгиб под нашивкой, пропорции против источника (rep — описание apply из info.json, поле
    src_cm). До 24.10 (раскладка по сетке вратаря): гербы — на 4–6 см выше правила и сжаты по ширине в 0,7, щит — на
    3 см выше. -> ([замечание], [замер])."""
    import os
    from PIL import Image
    from scipy import ndimage as ndi
    if not os.path.exists(masks_png):
        return [f"шорты: нет маски нашивок {os.path.basename(masks_png)} — kitport build --stages pant,slot"], []
    A = np.asarray(Image.open(masks_png).convert("RGB")).astype(np.float64) / 255.0
    G = game_mesh()[0]
    ok, P, N = _surface(G, A.shape[0])
    frames = {leg: leg_frame(G, leg) for leg in (-1, 1)}
    src = {}
    for r in rep or []:
        if r.get("slot") in MASK_KIND and r.get("src_cm"):
            src.setdefault(MASK_KIND[r["slot"]], []).append(r)
    flags, meas = [], []
    for ch, kind in ((0, "front"), (1, "back")):
        sp = LEG_SLOTS[kind]
        lab, n = ndi.label(ndi.binary_dilation(A[..., ch] > 0.3, iterations=6))   # нашивка из частей (звёзды WSH) — одна
        for i in range(1, n + 1):
            a = np.where(lab == i, A[..., ch], 0.0)
            if (a > 0.5).sum() < 30:
                continue
            pl = placement(a, ok, P, N, frames)
            if pl is None:
                continue
            dt = max(sp["d"], sp["bottom"] + pl["h"] / 2)
            m = {"kind": kind, "phi": pl["phi"], "d_cm": round(pl["d"] * 100, 1), "rule_cm": round(dt * 100, 1),
                 "bottom_cm": round(pl["bottom"] * 100, 1), "top_cm": round(pl["top"] * 100, 1),
                 "w_cm": round(pl["w"] * 100, 1), "h_cm": round(pl["h"] * 100, 1), "wrap": pl["wrap"]}
            what = "герб" if kind == "front" else "щит NHL"
            dphi = (pl["phi"] - sp["phi"] + 180) % 360 - 180
            if abs(pl["d"] - dt) > PLACE_TOL["d"] or abs(dphi) > PLACE_TOL["phi"]:
                flags.append(f"шорты: {what} не на месте — центр {m['d_cm']} см над краем штанины, {pl['phi']:.0f}° "
                             f"(правило {m['rule_cm']} см, {sp['phi']:.0f}°)")
            if pl["bottom"] < sp["bottom"] - PLACE_TOL["d"] / 2:
                flags.append(f"шорты: {what} у края штанины — низ {m['bottom_cm']} см (не ниже {sp['bottom'] * 100:.1f})")
            if pl["wrap"] > PLACE_TOL["wrap"]:
                flags.append(f"шорты: {what} на изгибе — нормаль под нашивкой до {pl['wrap']:.0f}°")
            cand = src.get(kind, [])
            if cand and pl["h"] > 0:
                ws = [r["src_cm"][0] / max(r["src_cm"][1], 1e-6) for r in cand]
                asp = pl["w"] / pl["h"]
                best = min(ws, key=lambda q: abs(np.log(asp / q)))
                m["aspect"], m["aspect_src"] = round(asp, 2), round(best, 2)
                if abs(np.log(asp / best)) > np.log(1 + PLACE_TOL["aspect"]):
                    flags.append(f"шорты: {what} сжат — ширина/высота {asp:.2f} против {best:.2f} у источника")
            meas.append(m)
    return flags, meas


def save_masks(path, masks, size=512):
    """Маски нашивок (apply(masks=…)) → PNG (MASKS): R — гербы спереди, G — щит сзади, B — прочие. Пустые — нули."""
    from PIL import Image
    rgb = np.zeros((size, size, 3), np.uint8)
    for k, kd in enumerate(("front", "back", "other")):
        if kd in masks:
            rgb[..., k] = np.clip(np.rint(masks[kd] * 255), 0, 255).astype(np.uint8)
    Image.fromarray(rgb, "RGB").save(path)


def main():
    """sheet: шорты источника на его сетке | прежний перенос | с наклейками — спереди, сзади, сбоку (PNG);
    rebuild: только шорты собранных комплектов клуба."""
    import argparse
    import os
    import sys
    from PIL import Image, ImageDraw, ImageFont
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("rebuild", help="только шорты собранных комплектов клуба (стадия kit без свитера): pant_cm.png, "
                       "маски нашивок, поля info.json")
    p.add_argument("--club", required=True, help="код клуба (DET)")
    p.add_argument("--kits", default="home,away", help="формы через запятую")
    p = sub.add_parser("sheet", help="лист проверки нашивок шорт")
    p.add_argument("--club", required=True, help="папка клуба источника (newjersey)")
    p.add_argument("--kit", required=True, help="папка комплекта (home, ten …)")
    p.add_argument("--source", default=os.environ.get("FB_GAME", "nhl24"), help="nhl24 | nhl27 (откуда текстуры)")
    p.add_argument("--out", default=None)
    p.add_argument("--hem", type=float, default=None, help="м: полосы низа от края штанины до этой высоты "
                   "(профиль pant_hem, NYR 0,15)")
    a = ap.parse_args()
    if a.cmd == "rebuild":                               # профиль клуба (источник, pant_hem, pant_merge_px …) — edge_kit
        from . import edge_kit, pilot
        edge_kit.use_club(a.club)
        pilot.set_roots(edge_kit.KITS_OUT, os.path.join(edge_kit.WORK, "pack"))
        for kit, note in pilot.rebuild_pants(a.club, [k for k in a.kits.split(",") if k]):
            print(f"{a.club} {kit}: шорты — {note}")
        return
    if os.environ.get("FB_GAME", "nhl24") != "nhl24":
        sys.exit("запуск с FB_GAME=nhl24: сетка шорт-источника — из дампа NHL 24 (текстуры — по --source)")
    from . import kit3d, pilot
    from .cas import REPO
    sys.path.insert(0, os.path.join(REPO, "tools"))
    os.environ.setdefault("PHOTOS_SOURCE", "nhl24")
    import scans24 as S
    d = os.path.join(REPO, "game", "work", a.source, "extract", f"club_{a.club}", "character", "skater", "league", "nhl",
                     a.club, "adidas", a.kit)
    color = kit3d.load_tex(os.path.join(d, f"pant_adidas_{a.club}_{a.kit}_color.png"))
    base = kit3d.load_tex(os.path.join(d, f"pant_adidas_{a.club}_{a.kit}_base_color.png"))
    pN, pL = kit3d.load_nhl24(pilot.PANT_N24), kit3d.load_legacy(pilot.PANT_L)
    bN = kit3d.bbox(pN)
    bN[3] = pilot.PANT_WAIST
    pLa = kit3d.aligned(pL, bN, kit3d.bbox(pL))
    old = kit3d.transfer(color, pN, pLa, 512, 2)[0]
    new = kit3d.transfer(base, pN, pLa, 512, 2)[0]
    if a.hem:
        new = hem(new, base, pN, pLa, pL, 512, h=a.hem)
    new, rep = apply(new, color, base, pN, 512)
    pG = game_mesh()[0]                                  # в игре полевые — в шортах GAME_MESH
    for r in rep:
        print("нашивка:", r)

    def part(m, tex):
        t = np.clip(tex, 0, 255).astype(np.uint8)
        if t.shape[-1] == 3:
            t = np.dstack([t, np.full(t.shape[:2], 255, np.uint8)])
        nrm = S.weld_normals(m["pos"], m["tri"], S.weld_ids(m["pos"]))
        return {"pos": m["pos"], "nrm": nrm, "uv": m["uv"], "tri": m["tri"], "tex": t, "twosided": True}

    font = ImageFont.truetype(os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", "segoeui.ttf"), 13)
    rows = []
    for title, m, tex in (("источник на своей сетке", pN, color), ("прежний перенос (растянут), шорты игры", pG, old),
                          ("ткань + наклейки (fb.pant_decals), шорты игры", pG, new)):
        b = kit3d.bbox(m)
        fr = (b[0] - 0.03, b[1] + 0.03, b[2] - 0.02, b[3] + 0.02)
        ims = [S.render([part(m, tex)], np.radians(ang), 240, frame=fr) for ang in (0, 180, 90, -90)]
        r = Image.new("RGB", (sum(i.size[0] + 4 for i in ims), max(i.size[1] for i in ims) + 18), (24, 24, 28))
        ImageDraw.Draw(r).text((4, 2), f"{a.source} {a.club} {a.kit}: {title}", fill=(255, 220, 140), font=font)
        x = 0
        for i in ims:
            r.paste(i, (x, 18))
            x += i.size[0] + 4
        rows.append(r)
    sh = Image.new("RGB", (max(r.size[0] for r in rows), sum(r.size[1] for r in rows)), (10, 10, 12))
    y = 0
    for r in rows:
        sh.paste(r, (0, y))
        y += r.size[1]
    out = a.out or os.path.join(REPO, "game", "work", a.source, "pant-decals", f"{a.club}_{a.kit}.png")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    sh.save(out)
    print("лист →", out)


if __name__ == "__main__":
    main()
