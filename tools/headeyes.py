"""Глаза перенесённой головы Legacy: где поставить яблоко и как это проверить (scans24, docs/heads-nhl24.md, «Глаза v7»).

Шапочка глаза Legacy (eyel / eyer, 66 вершин) — часть сферы радиусом ~14–15 мм (отклонение до 0,3 мм), привязана к
кости 8 (голова, в игре не смещается), зрачок — точка шапочки при UV (0,5; 0,5). Игра вращает яблоко вокруг сустава
23/24 из файла головы.

Правило v7 (21.10.2026, после жалобы пользователя: у Селебрини глаза «выступают из черепа и режут веки», раньше так же у
Matthews и DeBrincat):
  1. Сдвиг — МНК: передняя поверхность глаза источника (NHL 24/27, mat_eyes, в пределах RHO от его оси) ложится на сферу
     шапочки. Веки источника сделаны под его глаз: край век шаблона EA лежит на глазу источника с ошибкой около 0 мм, а
     v6 (глаз — вслед за 24 ближайшими вершинами головы) ставил яблоко на 1–3 мм впереди (p95 2,2 мм, у Селебрини 2,7)
     и у части голов на 2–3 мм ближе к переносице.
  2. Поворот шапочки вокруг центра сферы (поверхность та же) — зрачок анфас в точку разреза век (U_PUPIL, V_PUPIL) —
     медиана 93 сканов EA Legacy (u — от внутреннего угла к наружному, v — снизу вверх). Направление взгляда источника не
     берётся: в позе привязки глаза NHL 24/27 смотрят кто куда (у Zegras в NHL 24 радужка наполовину под веком).
  Нет глаза источника (меньше 20 точек поверхности) или подгонка не сошлась — остаётся сдвиг v6 без поворота.

Проверки (`scans24.py check eyes`; голова — в позе игры: переносы общего скелета × InvBind файла):
  * ahead — насколько поверхность шапочки впереди поверхности глаза источника, p95 по точкам (мм);
  * u, v, asym — зрачок в разрезе век в покое и асимметрия |uL−uR| + |vL−vR| (у сканов EA p95 0,16);
  * hidden — сколько раз зрачок под веком при пяти взглядах (покой, ±12° вбок, ±10° вверх-вниз);
  * edge — сколько точек края шапочки видно впереди головы (те же взгляды, голова анфас и ±30°); у сканов EA p95 272.
"""
import numpy as np

RHO = 0.011                     # м — зона поверхности глаза источника вокруг его оси (разрез век ~24 × 10 мм)
U_PUPIL, V_PUPIL = 0.49, 0.61   # зрачок в разрезе век: медиана сканов EA Legacy (p5–p95: u 0,45–0,52, v 0,50–0,74)
MIN_SRC = 20                    # меньше точек поверхности источника — правило v6
FIT_MAX = 0.006                 # м — подгонка дальше от старта (передние точки совпали) — не сошлась, правило v6
RULE = 'v7.1'                   # версия правила глаз (ключ кэша сборки scans24): 7.1 — старт подгонки от сферы источника
PX = 0.0001                     # м — пиксель растра проверок (0,1 мм)
GAZES = ((0, 0), (12, 0), (-12, 0), (0, 10), (0, -10))


def robust_sphere(p, it=4, tol=0.0004):
    """Сфера по точкам (МНК, затем без точек дальше tol от поверхности) → центр, радиус."""
    m = np.ones(len(p), bool)
    c, r = p.mean(0), 0.0
    for _ in range(it):
        A = np.c_[2 * p[m], np.ones(m.sum())]
        x = np.linalg.lstsq(A, (p[m] ** 2).sum(1), rcond=None)[0]
        c, r = x[:3], float(np.sqrt(x[3] + x[:3] @ x[:3]))
        res = np.abs(np.linalg.norm(p - c, axis=1) - r)
        if (res < tol).sum() > 20:
            m = res < tol
    return c, r


def raster(parts, frame, px=PX):
    """Анфас (вдоль −z), z-буфер: parts — [(pos, tri)], frame — (x0, x1, y0, y1) → (номер части, z) по пикселям."""
    x0, x1, y0, y1 = frame
    W, H = int((x1 - x0) / px), int((y1 - y0) / px)
    zb = np.full((H, W), -np.inf)
    pid = np.full((H, W), -1)
    for k, (pos, tri) in enumerate(parts):
        sx, sy, z = (pos[:, 0] - x0) / px, (y1 - pos[:, 1]) / px, pos[:, 2]
        keep = (sx[tri].max(1) >= 0) & (sx[tri].min(1) < W) & (sy[tri].max(1) >= 0) & (sy[tri].min(1) < H)
        for a, b, c in tri[keep]:
            xa, xb, xc, ya, yb, yc = sx[a], sx[b], sx[c], sy[a], sy[b], sy[c]
            ix0, ix1 = max(int(min(xa, xb, xc)), 0), min(int(max(xa, xb, xc)) + 1, W - 1)
            iy0, iy1 = max(int(min(ya, yb, yc)), 0), min(int(max(ya, yb, yc)) + 1, H - 1)
            if ix1 < ix0 or iy1 < iy0:
                continue
            den = (yb - yc) * (xa - xc) + (xc - xb) * (ya - yc)
            if abs(den) < 1e-14:
                continue
            xs, ys = np.meshgrid(np.arange(ix0, ix1 + 1) + 0.5, np.arange(iy0, iy1 + 1) + 0.5)
            l0 = ((yb - yc) * (xs - xc) + (xc - xb) * (ys - yc)) / den
            l1 = ((yc - ya) * (xs - xc) + (xa - xc) * (ys - yc)) / den
            l2 = 1 - l0 - l1
            m = (l0 >= 0) & (l1 >= 0) & (l2 >= 0)
            if not m.any():
                continue
            zz = (l0 * z[a] + l1 * z[b] + l2 * z[c])[m]
            py, pxx = (ys[m] - 0.5).astype(int), (xs[m] - 0.5).astype(int)
            near = zz > zb[py, pxx]
            zb[py[near], pxx[near]] = zz[near]
            pid[py[near], pxx[near]] = k
    return pid, zb


def pupil(q, uv, tri):
    """Точка шапочки при UV (0,5; 0,5)."""
    t = np.array([0.5, 0.5])
    for a, b, c in tri:
        M = np.array([uv[b] - uv[a], uv[c] - uv[a]]).T
        if abs(np.linalg.det(M)) < 1e-12:
            continue
        l1, l2 = np.linalg.solve(M, t - uv[a])
        if l1 >= -1e-6 and l2 >= -1e-6 and l1 + l2 <= 1 + 1e-6:
            return q[a] + l1 * (q[b] - q[a]) + l2 * (q[c] - q[a])
    return q[np.argmin(np.linalg.norm(uv - t, axis=1))]


def eye_frame(q):
    c = q.mean(0)
    return (c[0] - 0.022, c[0] + 0.022, c[1] - 0.015, c[1] + 0.015)


def aperture(hp, ht, q, tri, side, frame=None):
    """Видимый разрез век анфас → (x внутреннего угла, x наружного, y низа, y верха) или None. side: +1 — eyel."""
    frame = frame or eye_frame(q)
    pid, _ = raster([(hp, ht), (q, tri)], frame)
    ys, xs = np.nonzero(pid == 1)
    if not len(xs):
        return None
    x_lo, x_hi = frame[0] + xs.min() * PX, frame[0] + (xs.max() + 1) * PX
    y_top, y_bot = frame[3] - ys.min() * PX, frame[3] - (ys.max() + 1) * PX
    med, lat = (x_hi, x_lo) if side < 0 else (x_lo, x_hi)
    return med, lat, y_bot, y_top


def rotmat(a, b):
    """Поворот направления a в b (кратчайший) → (матрица, градусы)."""
    a, b = a / np.linalg.norm(a), b / np.linalg.norm(b)
    v, c = np.cross(a, b), float(a @ b)
    if np.linalg.norm(v) < 1e-12:
        return np.eye(3), 0.0
    K = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    return np.eye(3) + K + K @ K / (1 + c), float(np.degrees(np.arccos(np.clip(c, -1, 1))))


def gaze(yaw, pitch):
    cy, sy, cp, sp = np.cos(np.radians(yaw)), np.sin(np.radians(yaw)), np.cos(np.radians(pitch)), np.sin(np.radians(pitch))
    return np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]]) @ np.array([[1, 0, 0], [0, cp, -sp], [0, sp, cp]])


def src_front(e, rho=RHO):
    """Передняя поверхность глаза источника (одна сторона): точки ближе rho к оси, на сфере (±0,8 мм)."""
    if len(e) < MIN_SRC:
        return np.zeros((0, 3))
    cs, rs = robust_sphere(e)
    res = np.abs(np.linalg.norm(e - cs, axis=1) - rs)
    return e[(np.linalg.norm(e[:, :2] - cs[:2], axis=1) < rho) & (e[:, 2] > cs[2]) & (res < 0.0008)]


def fit_to_source(q, pts):
    """Сдвиг шапочки q (радиус — её), при котором точки поверхности источника pts лежат на передней половине её сферы
    (МНК, soft_l1) → сдвиг или None (подгонка не сошлась — тогда правило v6).

    Старт — передняя точка сферы источника = передняя точка шапочки. От нулевого сдвига МНК у 9 глаз из 944 уходил в
    ложный минимум: сфера на 23–28 мм впереди, точки источника — на её задней стороне (21.10, Rantanen, Eichel, Kerfoot…)."""
    from scipy.optimize import least_squares
    c, r = robust_sphere(q)
    cs, rs = robust_sphere(pts)
    t0 = cs + np.array([0.0, 0.0, rs - r]) - c
    t = least_squares(lambda t: np.linalg.norm(pts - (c + t), axis=1) - r, t0, loss='soft_l1', f_scale=0.0003).x
    res = np.abs(np.linalg.norm(pts - (c + t), axis=1) - r)
    if (pts[:, 2] <= c[2] + t[2]).any() or np.median(res) > 0.0005 or np.linalg.norm(t - t0) > FIT_MAX:
        return None
    return t


def turn_to_aperture(q, uv, tri, hp, ht, side):
    """Поворот шапочки q вокруг центра её сферы: зрачок анфас — в точку (U_PUPIL, V_PUPIL) разреза век головы hp
    (поза игры) → (новые позиции, матрица, градусы) или None, если глаза не видно."""
    ap = aperture(hp, ht, q, tri, side)
    if ap is None:
        return None
    med, lat, yb, yt = ap
    c, r = robust_sphere(q)
    x, y = med + U_PUPIL * (lat - med) - c[0], yb + V_PUPIL * (yt - yb) - c[1]
    d = np.array([x, y, np.sqrt(max(r * r - x * x - y * y, 1e-8))])
    R, ang = rotmat(pupil(q, uv, tri) - c, d)
    return (q - c) @ R.T + c, R, ang


def ahead(pts, q):
    """Поверхность шапочки q впереди поверхности источника pts: p95, мм (> 0 — выступает)."""
    if not len(pts):
        return None
    c, r = robust_sphere(q)
    return round(float(np.percentile((r - np.linalg.norm(pts - c, axis=1)) * 1000, 95)), 2)


def gaze_check(hp, ht, eyes, pivots):
    """eyes {'eyel'|'eyer': (pos, uv, tri)}, pivots — суставы 23/24 → зрачок в разрезе век в покое, асимметрия, сколько
    раз зрачок под веком при взглядах GAZES (как gazesim из research, 12.10)."""
    res = {}
    for name, side in (('eyel', 1), ('eyer', -1)):
        q, uv, tri = eyes[name]
        fr = eye_frame(q)
        ap = aperture(hp, ht, q, tri, side, fr)
        if ap is None:
            return None
        med, lat, yb, yt = ap
        p0 = pupil(q, uv, tri)
        out = []
        for yaw, pitch in GAZES:
            R = gaze(yaw, pitch)
            qq = (q - pivots[name]) @ R.T + pivots[name]
            pp = (p0 - pivots[name]) @ R.T + pivots[name]
            pid, _ = raster([(hp, ht), (qq, tri)], fr)
            ix, iy = int((pp[0] - fr[0]) / PX), int((fr[3] - pp[1]) / PX)
            hidden = not (0 <= iy < pid.shape[0] and 0 <= ix < pid.shape[1] and pid[iy, ix] == 1)
            out.append(((pp[0] - med) / (lat - med), (pp[1] - yb) / (yt - yb), hidden))
        res[name] = out
    L, Rr = res['eyel'], res['eyer']
    return {'uv': [[round(L[0][0], 3), round(L[0][1], 3)], [round(Rr[0][0], 3), round(Rr[0][1], 3)]],
            'asym': round(abs(L[0][0] - Rr[0][0]) + abs(L[0][1] - Rr[0][1]), 3),
            'hidden': sum(int(x[2]) for x in L + Rr)}


def boundary_points(q, tri, k=8):
    e = np.sort(np.concatenate([tri[:, [0, 1]], tri[:, [1, 2]], tri[:, [0, 2]]]), 1)
    u, cnt = np.unique(e, axis=0, return_counts=True)
    b = u[cnt == 1]
    s = np.linspace(0, 1, k, endpoint=False)
    return (q[b[:, 0], None] * (1 - s)[None, :, None] + q[b[:, 1], None] * s[None, :, None]).reshape(-1, 3)


def turn_y(v, deg):
    a = np.radians(deg)
    out = v.copy()
    out[..., 0] = np.cos(a) * v[..., 0] + np.sin(a) * v[..., 2]
    out[..., 2] = -np.sin(a) * v[..., 0] + np.cos(a) * v[..., 2]
    return out


def edge_seen(hp, ht, eyes, pivots):
    """Точки края шапочек впереди головы (на 0,05 мм): взгляды GAZES × голова анфас и ±30°."""
    n = 0
    for name, (q, _, tri) in eyes.items():
        for yaw, pitch in GAZES:
            R = gaze(yaw, pitch)
            qq = (q - pivots[name]) @ R.T + pivots[name]
            for turn in (0.0, 30.0, -30.0):
                hq, qt = turn_y(hp, turn), turn_y(qq, turn)
                bp = boundary_points(qt, tri)
                c = qt.mean(0)
                fr = (c[0] - 0.024, c[0] + 0.024, c[1] - 0.016, c[1] + 0.016)
                _, zb = raster([(hq, ht)], fr)
                ix, iy = ((bp[:, 0] - fr[0]) / PX).astype(int), ((fr[3] - bp[:, 1]) / PX).astype(int)
                ok = (ix >= 0) & (ix < zb.shape[1]) & (iy >= 0) & (iy < zb.shape[0])
                zh = np.full(len(bp), -np.inf)
                zh[ok] = zb[iy[ok], ix[ok]]
                n += int((bp[:, 2] > zh + 0.00005).sum())
    return n
