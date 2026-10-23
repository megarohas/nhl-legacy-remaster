"""Нашивки шорт (герб клуба, щит NHL) — наклейками, а не 3D-переносом текстуры.

Шорты NHL 24/27 и Legacy разной формы: у Legacy шире (по x ≈ 1,45 от NHL 24) и короче, перенос по ближайшей точке
(fb.kit3d.transfer после kit3d.aligned) растягивает нашивки по ширине и поворачивает на изгибах («поехали логотипы»,
пользователь, 21.10, NJD: герб спереди и щит NHL сзади). Полосам и ткани это не мешает, нашивкам — да. Поэтому:

1. Ткань — перенос base_color (у EA текстура шорт без нашивок) как раньше.
2. Нашивки — разница color − base_color (> DIFF), каждая связная часть — отдельная наклейка:
   - место и размер — как у EA на шортах Legacy (EA_SLOTS, замер 21.10 по 84 формам EA): щит NHL сзади — рамка
     развёртки (0,107; 0,338)–(0,148; 0,371) у всех EA, высота 5,5 см; герб спереди — на той ноге, где у источника,
     в середине рамок EA этой стороны, по диагонали ~11,5 см. Пропорции нашивки — источника (масштаб одинаков по осям).
     Сначала место бралось по точке источника (центр в 3D → выровненная сетка Legacy): щит выходил мельче EA, герб —
     ниже и сбоку, на загибе у края штанины, «сплюснутым» (пользователь, 21.10, NJD). Нашивки не сзади и не спереди
     (полосы, надписи сбоку) — по-прежнему по точке источника, размер × высота шорт Legacy / источника;
   - верх наклейки — мировая ось y в касательной плоскости (вертикально), без поворота от развёртки: у EA в развёртке
     гербы повёрнуты по-разному, чтобы на сетке стоять вертикально.
3. Наклейка ложится по 3D-точкам текселей сетки Legacy (не по UV) — изгиб и швы развёртки её не рвут.

    from fb import pant_decals
    img = pant_decals.apply(img, color, base, src_mesh, dst_aligned, dst_mesh, size)

4. Полосы по низу штанин (профиль pant_hem, 23.10, NYR) — hem(): у края штанины тексель Legacy берёт цвет точки источника
   с тем же углом вокруг ноги и той же высотой над краем (полосы вдоль края, толщины NHL 27), выше — переход к переносу.

5. Рельеф и блеск (pant_nm, pant_sm) у шорт pant = "source" — образца Legacy, с его гербом EA на его месте; наш герб —
   по EA_SLOTS выше и на ноге источника (пользователь, 23.10, DET: «лого выше и сбоку относительно рельефного места»).
   apply(masks=…) отдаёт альфу нашивок, стадия kit пишет её рядом с pant_cm.png (MASKS), стадия slot (relief) стирает
   гербы образца спереди в pant_nm/pant_sm и кладёт рельеф и блеск по нашим гербам. Проверка — relief_check (kitport audit).

Проверка — `python -m fb.pant_decals sheet CLUB KIT` (рендер шорт источника и наш, спереди, сзади, сбоку).
Только шорты собранных комплектов (без свитера, ~15 с на форму; маски нашивок для рельефа) —
`python -m fb.pant_decals rebuild --club DET --kits home,away` (= `kitport build --club DET --stages pant,slot`).
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
Y_MAX = None                       # профиль pant_decal_ymax, м (23.10, агент review-d, WPG): нашивка с центром выше на сетке
#                                    источника — не нашивка (пояс шорт под свитером: у WPG обрывки разницы у шнурка пояса
#                                    шли в места гербов EA — тёмные пятна на обеих ногах). None — как было
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
# места нашивок шорт EA (uv развёртки шорт Legacy pant_1_0_0_2; центры рамок): щит — одна рамка у всех 84 форм EA,
# герб слева — среднее рамок 1_14_0, 1_16_2, 1_1_3, 1_23_0, 1_24_3, справа — 1_20_0, 1_131_0, 1_20_3, 1_23_6
EA_SLOTS = {"back": {"uv": (0.1275, 0.3545), "h": 0.055},
            "front_left": {"uv": (0.131, 0.613), "diag": 0.115, "lift": 0.03},
            "front_right": {"uv": (0.881, 0.586), "diag": 0.115, "lift": 0.03}}
# lift — м вверх по шортам от центра рамки EA (пользователь, 21.10: герб на шортах «слишком низко, чуть поднять»)


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


def apply(img, color, base, src_mesh, dst_aligned, dst_mesh, size=512, ss=2, report=None, ea=True, masks=None):
    """Нашивки (color − base) поверх img — переноса base на развёртку dst (size², RGB float) → img и [описание].
    ea — места и размеры EA (EA_SLOTS), иначе — по точке источника. masks — словарь: в него альфа нашивок (size², 0…1)
    по видам MASK_KIND (front — гербы спереди, back — щит сзади, other — по точке источника): по ней рельеф (relief)."""
    from . import kit3d
    S = size * ss
    ok_s, P_s, N_s = _surface(src_mesh, color.shape[0])
    ok_a, P_a, N_a = _surface(dst_aligned, S)
    ok_d, P_d, N_d = _surface(dst_mesh, S)
    bs, bd = np.array(kit3d.bbox(src_mesh)), np.array(kit3d.bbox(dst_aligned))
    br = np.array(kit3d.bbox(dst_mesh))
    scale = (br[3] - br[2]) / max(bd[3] - bd[2], 1e-9)       # высота шорт Legacy / видимая высота источника
    hi = np.zeros((S, S, 3))
    a_hi = np.zeros((S, S))
    a_kind = {}                                          # альфа по видам нашивок (masks)
    rep = []
    for m in decals(color, base):
        rgba, c, n, (right, up), x0, y0 = sticker(color, m, ok_s, P_s, N_s)
        if Y_MAX is not None and c[1] > Y_MAX:           # пояс под свитером — не нашивка (профиль pant_decal_ymax, WPG)
            rep.append({"slot": "skip", "src_center": np.round(c, 3).tolist(), "why": f"y > {Y_MAX}"})
            continue
        slot = slot_of(c, n) if ea else None
        k = scale
        if slot:                                         # место EA: тексель с центром рамки (ближайший на развёртке)
            u, v = EA_SLOTS[slot]["uv"]
            yy, xx = np.nonzero(ok_d)
            j = np.argmin((xx - u * S) ** 2 + (yy - v * S) ** 2)
            iy, ix = yy[j], xx[j]
            lift = EA_SLOTS[slot].get("lift", 0.0)
            if lift:                                     # выше по той же поверхности: тексель у точки центр + lift·верх
                c0, n0 = P_d[iy, ix], N_d[iy, ix]
                q = c0 + lift * _basis(n0)[1]
                dq = np.linalg.norm(P_d - q, axis=-1)
                dq[~ok_d | ((N_d @ n0) < FACING)] = np.inf
                iy, ix = np.unravel_index(np.argmin(dq), dq.shape)
            hw = np.array(rgba.shape[:2]) * RES                  # высота, ширина наклейки, м
            k = EA_SLOTS[slot]["h"] / hw[0] if "h" in EA_SLOTS[slot] else EA_SLOTS[slot]["diag"] / np.hypot(*hw)
        else:                                            # центр → ближайший тексель выровненной сетки Legacy,
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
        rep.append({"slot": slot or "source", "src_center": np.round(c, 3).tolist(),
                    "dst_uv": [round(float(ix) / S, 3), round(float(iy) / S, 3)],
                    "size_cm": [round(rgba.shape[1] * RES * k * 100, 1), round(rgba.shape[0] * RES * k * 100, 1)]})
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
# по EA_SLOTS (+ lift 3 см, пользователь 21.10) и на той ноге, где у источника. Отсюда: рельеф ниже и сбоку от герба
# (DET, MTL, VAN …), рельеф на другой ноге (BOS, ANA, OTT …), пустой рельеф без герба (LAK, TOR, BUF …). Теперь: нашивки
# образца спереди стираются в pant_nm и pant_sm (kitpaint.erase, гладко), рельеф и блеск — по альфе наших гербов (маска
# MASKS со стадии kit). Место герба (решение 21.10) не меняется. Щит NHL сзади у EA и у нас — в одной рамке: не трогается.
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


def template_patches(cm):
    """Гербы спереди у шорт образца Legacy (cm 512², RGB): у EA герб — в цвете (cm), рельефе (nm) и блеске (sm) в одном
    месте, ищется по цвету в окнах рамок EA (EA_SLOTS front_*): отличие от ткани окна > TPL_THR, дыры залиты, тонкое
    (потёртости, швы) снято размыканием, части у края окна (полосы, пояс, панели) и мельче TPL_MIN_PX — не герб.
    -> [{"slot", "uv", "px", "mask"}] (mask — bool как cm)."""
    from scipy import ndimage as ndi
    H, W = cm.shape[:2]
    out = []
    for slot in ("front_left", "front_right"):
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
            out.append({"slot": slot, "uv": (round(float(xs.mean()) / W, 3), round(float(ys.mean()) / H, 3)),
                        "px": int(m.sum()), "mask": full})
    return out


def _pant_points(size=512):
    """Тексели развёртки шорт Legacy (pilot.PANT_L) size²: маска и 3D-точки (для расстояний в см)."""
    if size not in _PANT_SURF:
        from . import kit3d, pilot
        ok, P, _ = _surface(kit3d.load_legacy(pilot.PANT_L), size)
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
    A = np.asarray(Image.open(masks_png).convert("RGB"))[..., 0].astype(np.float64) / 255.0
    ocm = np.asarray(Image.open(os.path.join(out_dir, "pant_cm.png")).convert("RGB")).astype(np.float64)
    if A.shape != N0.shape[:2] or ocm.shape[:2] != N0.shape[:2] or tcm.shape[:2] != N0.shape[:2]:
        sys.exit(f"pant_decals.relief: размеры {masks_png} {A.shape}, pant_cm {ocm.shape[:2]}, образца "
                 f"{tcm.shape[:2]} / {N0.shape[:2]} — нужны одинаковые (512²)")
    Hh = _height(A, ocm)
    gy, gx = np.gradient(Hh)
    sign, k, gloss = RELIEF_SIGN, RELIEF_K, None
    info = {"template": [], "ours": []}
    if found:
        big = max(found, key=lambda f: f["px"])
        kc = kp.relief_calibrate(nm, bytearray(big["mask"].astype(np.uint8).tobytes()))
        if kc and max(abs(kc[0]), abs(kc[1])) > 6:
            sign = (math.copysign(1.0, kc[0]), math.copysign(1.0, kc[1]))
        f2 = big["mask"].reshape(sm.h, nm.h // sm.h, sm.w, nm.w // sm.w).any((1, 3))
        gloss = float(np.median(S0[f2][:, :3].mean(1))) if f2.any() else None
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
        if gloss is not None:                       # блеск вышивки — как у герба образца
            A2 = A.reshape(sm.h, nm.h // sm.h, sm.w, nm.w // sm.w).mean((1, 3))
            S[..., :3] = S[..., :3] * (1 - A2[..., None]) + gloss * A2[..., None]
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
    info.update(sign=sign, k=round(k, 1), gloss=None if gloss is None else round(gloss, 1))
    return info


def relief_note(info):
    """Описание relief() одной строкой для журнала стадии slot."""
    if "skip" in info:
        return info["skip"]
    t = "; ".join(f"{f['slot']} uv {f['uv']}" + (f" ({f['cm_to_ours']} см до нашего)" if f["cm_to_ours"] is not None
                                                  else " (нашего рядом нет)") for f in info["template"]) or "нет"
    return (f"гербы образца стёрты: {t}; наших гербов с рельефом: {len(info['ours'])} (k {info['k']}, "
            f"блеск {info['gloss']})")


def relief_check(tpl_dir, slot_dir, masks_png):
    """Проверка (kitport audit): рельеф шорт слота — только под нашими гербами. -> [замечание] и {замеры}.
    - герб образца (template_patches) вне наших гербов — его рельеф в pant_nm слота должен быть стёрт: остаток энергии
      рельефа сверх фона больше RELIEF_LEFT от исходной — «рельеф без герба» (до 23.10: DET, LAK, BOS …);
    - у нашего герба (R маски) рельеф по краю — энергия не меньше RELIEF_MIN × фона рядом, иначе «герб без рельефа»."""
    import os
    from PIL import Image
    from scipy import ndimage as ndi
    if not os.path.exists(masks_png):
        return [f"шорты: нет маски нашивок {os.path.basename(masks_png)} (шорты до 23.10) — рельеф образца не по гербу; "
                "kitport build --stages pant,slot"], {}
    tcm = np.asarray(Image.open(os.path.join(tpl_dir, "pant_cm.png")).convert("RGB"))
    N0 = np.asarray(Image.open(os.path.join(tpl_dir, "pant_nm.png")).convert("RGB")).astype(np.float64)
    N1 = np.asarray(Image.open(os.path.join(slot_dir, "pant_nm.png")).convert("RGB")).astype(np.float64)
    A = np.asarray(Image.open(masks_png).convert("RGB"))[..., 0].astype(np.float64) / 255.0
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
            far = f", {np.linalg.norm(c - o) * 100:.1f} см от нашего герба" if c is not None and o is not None else ""
            flags.append(f"шорты: рельеф герба образца без нашего герба ({f['slot']}, uv {f['uv']}{far}; "
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
            flags.append(f"шорты: наш герб без рельефа (uv {uv}: край {e:.1f}, фон {bg:.1f})")
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
    new, rep = apply(new, color, base, pN, pLa, pL, 512)
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
    for title, m, tex in (("источник на своей сетке", pN, color), ("прежний перенос (растянут)", pL, old),
                          ("ткань + наклейки (fb.pant_decals)", pL, new)):
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
