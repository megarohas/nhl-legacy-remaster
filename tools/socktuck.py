"""Четыре вида заправки гетр из одной гетры (NHL Legacy, эксперимент 05.11.2026).

Пользователю нравится толщина гетры варианта 3 («язык заправлен, задник торчит»), а варианты, где торчит только язык
или не торчит ничего, кажутся ему толще. Идея — все четыре вида собрать из гетры 3, не меняя её толщину, а вид
задавать деталью конька над ботинком (поле игрока exhibitionskaterequipment.skatesocktuck = T выбирает и гетру
rendering/sock/playersock_T_L, и деталь rendering/skate/skatetongue_T_L; при T = 1 детали нет):

    T  вид                                      гетра                 деталь
    3  язык заправлен, задник торчит (как есть)  playersock_3 (своя)   skatetongue_3 — задник (своя)
    1  ничего не торчит                          копия playersock_3    нет (так у игры при 1)
    2  задник заправлен, язык торчит             копия playersock_3    skatetongue_2 EA целиком сдвинут вперёд-вниз
    0  ничего не заправлено                      копия playersock_3    skatetongue_0 = skatetongue_3 как есть + тот же язык

У 1 и 2 (без задника) низ копии гетры подтянут к стенке ботинка у его верха (fill_rim): иначе в щель видна изнанка
стенки. Затенение playersock_T_K_am у 0, 1, 2 — копии от 3.

    python socktuck.py build [--base DIR] [--out DIR] [--no-fill]   # файлы в раскладке cache: (по умолчанию
                                                          # game/work/models-check/tuck4/out), сводка manifest.json
    python socktuck.py check [--out DIR]                  # гетры 1, 2 против ботинка и шнуровки, язык против гетры 3,
                                                          # ботинка и шнуровки — в 7 позах стопы, LOD _2/_0/_3
    python socktuck.py sheet [--out DIR] [--kit 2_23_7] [--skate 41]   # листы в ../pics: views (4 вида и EA 2),
                                                          # holes (стык крупно, изнанка — пурпурным), poses
    python socktuck.py fit                                # подбор сдвига языка (TONGUE_MOVE) заново

--base — откуда брать нынешние файлы (по умолчанию cache: пользователя nhl-legacy-port/userdata/cache/guest, там стоят
правки голени §6/§6а и задника; нет файла — архив Legacy game/other/legacy/big). Подробно — docs/player-models.md §6б.
Только для NHL Legacy (сетки — из её архивов). numpy — для растеризатора картинок (venv game/work/nhl24/venv).
"""
import json, math, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rw4mesh as rm  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(REPO, 'nhl-legacy-port', 'userdata', 'cache', 'guest')
OUT = os.path.join(REPO, 'game', 'work', 'models-check', 'tuck4', 'out')     # эксперимент: не в legacy-data
LODS = (2, 0, 3)
SRC_T = 3                          # гетра-образец: её толщину пользователь хочет у всех четырёх видов
AM = 'rendering/sock/playersock_{t}_{k}_am.rx2'   # затенение гетры (k — 0/1: выбирается не детализацией)
NAMES = {3: 'язык заправлен, задник торчит', 1: 'ничего не торчит', 2: 'задник заправлен, язык торчит',
         0: 'ничего не заправлено'}


def use_legacy():
    rm.use_game('legacy')


def base_file(base, rel):
    """Путь файла rel в base (раскладка cache:) или None."""
    p = os.path.join(base, *rel.split('/'))
    return p if os.path.exists(p) else None


def load(base, rel):
    """Сетка: из base, если там есть, иначе — архив игры."""
    p = base_file(base, rel) if base else None
    return rm.Mesh.load(p) if p else rm.Mesh.game(rel)


def raw_file(base, rel):
    p = base_file(base, rel) if base else None
    return open(p, 'rb').read() if p else rm.source(rel)


# ---------------------------------------------------------------- картинки: растеризатор (numpy)

class Tex:
    """Текстура RGBA → массив float (h, w, 4); выборка билинейная с повтором."""

    def __init__(self, data, name):
        import numpy as np
        import teamart as ta
        import kitpaint as kp
        rw = ta.Rw4(rm.unchunk_any(data), name)
        ts = [t for t in rw.textures if name in t.name] or rw.textures
        w, h, px = kp.tex_decode(rw, ts[0], 0)
        self.a = np.frombuffer(bytes(px), dtype=np.uint8).reshape(h, w, 4).astype(np.float32)
        self.w, self.h = w, h

    def sample(self, u, v):
        import numpy as np
        fx, fy = u * self.w - 0.5, v * self.h - 0.5
        x0, y0 = np.floor(fx).astype(int), np.floor(fy).astype(int)
        tx, ty = (fx - x0)[:, None], (fy - y0)[:, None]
        xa, xb = np.mod(x0, self.w), np.mod(x0 + 1, self.w)
        ya, yb = np.clip(y0, 0, self.h - 1), np.clip(y0 + 1, 0, self.h - 1)
        a = self.a
        return (a[ya, xa] * (1 - tx) + a[ya, xb] * tx) * (1 - ty) + (a[yb, xa] * (1 - tx) + a[yb, xb] * tx) * ty


class Part:
    """Сетка для картинки: Mesh, текстура цвета, карта нормалей, затенение; только нога side (0 — x > 0)."""

    def __init__(self, m, tex=None, nm=None, ao=None, color=(180, 180, 180), side=0, name='', pose=None, skel=None):
        import numpy as np
        self.m, self.tex, self.nm, self.ao, self.color, self.name = m, tex, nm, ao, color, name
        tris = [t for t in m.tris if all(rm.leg_of(m, i) == side for i in t)] if side is not None else list(m.tris)
        self.tris = np.array(tris, dtype=np.int64).reshape(-1, 3)
        pos = m.pos
        if pose and pose[1]:                       # поза стопы (как у rw4mesh check): кости стопы — вокруг голеностопа
            pos = rm.posed(m, skel or rm.Skeleton.game(), pose)
        self.pos = np.array([p[:3] for p in pos], dtype=np.float64)
        self.nrm = np.array(m.nrm, dtype=np.float64)
        self.tan = np.array(m.tan, dtype=np.float64) if m.tan else None
        self.uv = np.array(m.uv, dtype=np.float64)
        # наружная сторона треугольника — по нормалям вершин (у _3 левой ноги обход у EA обратный)
        P = self.pos[self.tris]
        g = np.cross(P[:, 1] - P[:, 0], P[:, 2] - P[:, 0])
        nv = self.nrm[self.tris].sum(axis=1)
        self.flip = (g * nv).sum(axis=1) < 0
        self.gn = np.where(self.flip[:, None], -g, g)


LIGHT = (-0.35, 0.45, 0.82)


class View:
    """Ортографическая камера: yaw (0 — спереди, 90 — сбоку снаружи правой ноги, 180 — сзади), pitch (+ — сверху),
    рамка (x0, y0, x1, y1) в метрах после поворота, w × h."""

    def __init__(self, yaw, pitch, frame, w, h):
        self.yaw, self.pitch, self.frame, self.w, self.h = yaw, pitch, frame, w, h
        cy, sy = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
        cp, sp = math.cos(math.radians(pitch)), math.sin(math.radians(pitch))
        import numpy as np
        ry = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
        rp = np.array([[1, 0, 0], [0, cp, -sp], [0, sp, cp]])
        self.R = rp @ ry

    def rot(self, v):
        return v @ self.R.T

    def screen(self, p):
        q = self.rot(p)
        x0, y0, x1, y1 = self.frame
        import numpy as np
        return np.stack([(q[:, 0] - x0) / (x1 - x0) * self.w, (y1 - q[:, 1]) / (y1 - y0) * self.h, q[:, 2]], axis=1)


def raster(parts, view, cull):
    """→ (z, номер части, номер треугольника, барицентрические b0, b1, изнанка) по пикселям."""
    import numpy as np
    W, H = view.w, view.h
    zb = np.full((H, W), -1e9)
    pid = np.full((H, W), -1, dtype=np.int32)
    tid = np.full((H, W), -1, dtype=np.int32)
    b0 = np.zeros((H, W))
    b1 = np.zeros((H, W))
    back = np.zeros((H, W), dtype=bool)
    for k, pt in enumerate(parts):
        S = view.screen(pt.pos)
        facing = view.rot(pt.gn)[:, 2] > 0
        for ti, (a, b, c) in enumerate(pt.tris):
            if cull and not facing[ti]:
                continue
            x0, y0, z0 = S[a]
            x1, y1, z1 = S[b]
            x2, y2, z2 = S[c]
            area = (x1 - x0) * (y2 - y0) - (x2 - x0) * (y1 - y0)
            if abs(area) < 1e-9:
                continue
            mnx, mxx = max(0, int(min(x0, x1, x2))), min(W - 1, int(max(x0, x1, x2)) + 1)
            mny, mxy = max(0, int(min(y0, y1, y2))), min(H - 1, int(max(y0, y1, y2)) + 1)
            if mnx > mxx or mny > mxy:
                continue
            fx = np.arange(mnx, mxx + 1) + 0.5
            fy = (np.arange(mny, mxy + 1) + 0.5)[:, None]
            w0 = ((x1 - fx) * (y2 - fy) - (x2 - fx) * (y1 - fy)) / area
            w1 = ((x2 - fx) * (y0 - fy) - (x0 - fx) * (y2 - fy)) / area
            w2 = 1 - w0 - w1
            ins = (w0 >= 0) & (w1 >= 0) & (w2 >= 0)
            if not ins.any():
                continue
            z = w0 * z0 + w1 * z1 + w2 * z2
            sub = zb[mny:mxy + 1, mnx:mxx + 1]
            upd = ins & (z > sub)
            if not upd.any():
                continue
            sub[upd] = z[upd]
            pid[mny:mxy + 1, mnx:mxx + 1][upd] = k
            tid[mny:mxy + 1, mnx:mxx + 1][upd] = ti
            b0[mny:mxy + 1, mnx:mxx + 1][upd] = w0[upd]
            b1[mny:mxy + 1, mnx:mxx + 1][upd] = w1[upd]
            back[mny:mxy + 1, mnx:mxx + 1][upd] = not facing[ti]
    return zb, pid, tid, b0, b1, back


def shade(parts, view, buf, bg=(58, 60, 68)):
    import numpy as np
    zb, pid, tid, b0, b1, back = buf
    H, W = zb.shape
    img = np.empty((H, W, 3), dtype=np.float32)
    img[:] = bg
    L = np.array(LIGHT) / np.linalg.norm(LIGHT)
    Hv = L + np.array([0, 0, 1.0])
    Hv /= np.linalg.norm(Hv)
    for k, pt in enumerate(parts):
        sel = pid == k
        if not sel.any():
            continue
        t = pt.tris[tid[sel]]
        w0, w1 = b0[sel][:, None], b1[sel][:, None]
        w2 = 1 - w0 - w1
        uv = pt.uv[t[:, 0]] * w0 + pt.uv[t[:, 1]] * w1 + pt.uv[t[:, 2]] * w2
        n = pt.nrm[t[:, 0]] * w0 + pt.nrm[t[:, 1]] * w1 + pt.nrm[t[:, 2]] * w2
        n /= np.linalg.norm(n, axis=1, keepdims=True) + 1e-12
        if pt.nm is not None and pt.tan is not None:
            tg = pt.tan[t[:, 0]] * w0 + pt.tan[t[:, 1]] * w1 + pt.tan[t[:, 2]] * w2
            tg -= (tg * n).sum(axis=1, keepdims=True) * n
            tg /= np.linalg.norm(tg, axis=1, keepdims=True) + 1e-12
            bt = np.cross(n, tg)
            s = pt.nm.sample(uv[:, 0], uv[:, 1])
            sx, sy = s[:, 0:1] / 127.5 - 1, s[:, 1:2] / 127.5 - 1
            sz = np.sqrt(np.clip(1 - sx * sx - sy * sy, 0, 1))
            n = tg * sx - bt * sy + n * sz
            n /= np.linalg.norm(n, axis=1, keepdims=True) + 1e-12
        n = view.rot(n)
        flip = n[:, 2] < 0
        n[flip] *= -1
        dl = np.clip(n @ L, 0, None)[:, None]
        sh = 0.42 + 0.72 * dl
        if pt.ao is not None:
            sh = sh * (0.35 + 0.65 * pt.ao.sample(uv[:, 0], uv[:, 1])[:, 0:1] / 255.0)
        hl = np.clip(n @ Hv, 0, None)[:, None] ** 24 * 0.10 * 255
        col = pt.tex.sample(uv[:, 0], uv[:, 1])[:, :3] if pt.tex is not None else np.array(pt.color, dtype=np.float32)
        img[sel] = np.clip(col * sh + hl, 0, 255)
    return img


HOLE = (255, 0, 220)               # изнанка/дыра на картинке


def render(parts, view, bg=(58, 60, 68), mark=True):
    """Картинка (h, w, 3) uint8: с отсечением изнанки (как, вероятно, в игре); mark — пиксели, где ближняя к камере
    поверхность видна с изнанки (в игре там просвет насквозь или внутренняя сторона), — пурпурным. → (img, дыры)."""
    import numpy as np
    culled = raster(parts, view, True)
    img = shade(parts, view, culled, bg)
    holes = np.zeros(img.shape[:2], dtype=bool)
    if mark:
        full = raster(parts, view, False)
        holes = full[5] & (full[0] > -1e8)
        img[holes] = img[holes] * 0.25 + np.array(HOLE) * 0.75
    return img.astype(np.uint8), holes


# ---------------------------------------------------------------- геометрия: язык EA целиком вперёд, гетра у верха ботинка
#
# 05.11.2026, пользователь (после пробы «язык и кольцо подогнать поверх гетры 3 по лучам» — раздутый язык и перекроенный
# задник): «переиспользуй это» — задник только родной skatetongue_3 как есть и только там, где он торчит (виды 3 и 0), у
# видов 1 и 2 задника нет совсем, щель у ботинка закрывает гетра; язык — родной skatetongue_2 целиком (форма и наклон EA),
# только сдвинут, не деформирован.

# Язык skatetongue_2 — жёстко: поворот вокруг оси X через низ языка (градусы; − — выпрямить) и сдвиг вверх и вперёд, м.
# Подобрано fit_tongue на ближней детализации (05.11.2026): отступ языка от гетры 3 — как у EA от гетры 2 (у корня 0…3 мм,
# кверху язык отходит); гетра 3 у корня языка шире гетры 2 на 5–16 мм. Наклон — как у EA (пользователь: «форма, наклон,
# отступ от гетры как у EA на варианте 2»). Лучшее — вперёд 15 мм и вниз 6: низ языка у шнуровки, как у EA 2 (вперёд 19 без
# опускания — спереди под языком полоса гетры ~1 см; лист game/work/models-check/tuck4/pics/tongue_pos.png).
TONGUE_MOVE = {'rot_x_deg': 0.0, 'up_m': -0.006, 'fwd_m': 0.015}
# дальняя детализация _3: её грубый ботинок спереди выше — при −6 мм язык входит в него до 17 мм; −2 мм — не входит
TONGUE_MOVE_LOD = {3: {'up_m': -0.002}}
FILL_MARGIN = 0.0015              # м: гетра у верха ботинка — внутри стенки ботинка не ближе (во всех позах)
FILL_DEPTH = (0.020, 0.030)       # м под краем ботинка: до первого — полная сила, к второму — с нуля (глубже не видно)
FILL_UP = (0.004, 0.020)          # м над краем ботинка: до первого — полный сдвиг (первое кольцо гетры — на 1–6 мм выше
#                                   края), ко второму — спад к исходной гетре
FILL_POSES = rm.SHIN_POSES
FILL_MAX = 0.009                  # м: сдвиг гетры не больше (щель у верха ботинка сзади — до 8 мм)
FILL_SIN = 0.2                    # только задняя половина и бока (sin угла < FILL_SIN; 90° — вперёд): дыра — сзади,
#                                   спереди гетра 3 и так поверх ботинка


def _push(m, i, axes, d):
    side = rm.leg_of(m, i)
    th, r = axes[side].polar(m.pos[i])
    x, z = axes[side].place(m.pos[i][1], th, r + d)
    m.set_pos(i, [x, m.pos[i][1], z])


def tongue_pivot(k2_near):
    """Опора поворота языка: середина языка ноги x > 0 по x и z, низ по y (ближняя детализация EA) — та же у всех LOD."""
    P = [k2_near.pos[i] for i in range(k2_near.nv) if rm.leg_of(k2_near, i) == 0]
    return [sum(p[0] for p in P) / len(P), min(p[1] for p in P), sum(p[2] for p in P) / len(P)]


def move_rigid(m, piv, mv=None):
    """Деталь целиком: поворот вокруг оси X через опору и сдвиг (вверх, вперёд) — одинаково у обеих ног (поворот вокруг X
    от x не зависит). Нормали и касательные поворачиваются вместе с поверхностью. → отчёт."""
    mv = mv or TONGUE_MOVE
    c, s_ = math.cos(math.radians(mv['rot_x_deg'])), math.sin(math.radians(mv['rot_x_deg']))
    old = [p[:] for p in m.pos]
    for i in range(m.nv):
        p = m.pos[i]
        y, z = p[1] - piv[1], p[2] - piv[2]
        m.set_pos(i, [p[0], piv[1] + y * c - z * s_ + mv['up_m'], piv[2] + y * s_ + z * c + mv['fwd_m']])
    frames = rm.update_frames(m, old, rm.Weld(m))
    return dict(mv, frames_rotated=frames)


def fit_tongue(k2, sock_ea, sock_new, axes, rots=(0.0,), ups=None, fwds=None, log=print):
    """Подбор TONGUE_MOVE перебором: у каждой вершины языка (нога x > 0) отступ от новой гетры по лучу из оси голени —
    как у EA от её гетры (вес больше у прилегающих мест); проход сквозь гетру глубже, чем у EA (−1 мм), — штраф.
    → (параметры, худший лишний проход, м)."""
    piv = tongue_pivot(k2)
    ax = axes[0]
    P, ref = [], []
    for i in range(k2.nv):
        if rm.leg_of(k2, i):
            continue
        th, r = ax.polar(k2.pos[i])
        h = sock_ea.hits(ax, k2.pos[i][1] + 1e-5, th)
        if h:
            P.append(k2.pos[i])
            ref.append(r - max(h))
    ups = ups or [x / 1000 for x in range(-8, 19, 2)]
    fwds = fwds or [x / 1000 for x in range(0, 31)]

    def cost(a, up, fwd):
        c, s_ = math.cos(math.radians(a)), math.sin(math.radians(a))
        tot, worst, n = 0.0, 0.0, 0
        for p, c0 in zip(P, ref):
            y, z = p[1] - piv[1], p[2] - piv[2]
            q = [p[0], piv[1] + y * c - z * s_ + up, piv[2] + y * s_ + z * c + fwd]
            th, r = ax.polar(q)
            h = sock_new.hits(ax, q[1] + 1e-5, th)
            if not h:
                continue
            c1 = r - max(h)
            tot += (c1 - c0) ** 2 / (1.0 + max(c0, 0.0) / 0.005)
            lim = min(c0, 0.0) - 0.001
            if c1 < lim:
                tot += 50 * (lim - c1) ** 2
                worst = max(worst, lim - c1)
            n += 1
        return tot / max(n, 1), worst
    best = None
    for a in rots:
        for up in ups:
            for fwd in fwds:
                c, w = cost(a, up, fwd)
                if best is None or c < best[0]:
                    best = (c, w, {'rot_x_deg': a, 'up_m': up, 'fwd_m': fwd})
    log(f'  язык: {best[2]}, лишний проход сквозь гетру — до {best[1] * 1000:.1f} мм')
    return best[2], best[1]


def boot_rim(boot_sl, ax, th, y_top=0.26, y_bot=0.19, step=0.0005):
    """Край ботинка на луче th: (высота, радиус наружной стенки) — первая сверху высота, где луч встречает ботинок."""
    y = y_top
    while y > y_bot:
        h = boot_sl.hits(ax, y, th)
        if h:
            return y, max(h)
        y -= step
    return None


def _posed_limit(m, i, ax, th, d, boots, poses, skel, margin):
    """Сдвиг d вершины i гетры наружу — меньше, если в какой-то позе стопы (низ гетры частью на кости стопы, ботинок —
    тоже) вершина выходит за наружную стенку ботинка − margin; поиск делением пополам."""
    p0 = m.pos[i]

    def ok(dd):
        x, z = ax.place(p0[1], th, ax.polar(p0)[1] + dd)
        q = [x, p0[1], z]
        for sl, pose in zip(boots, poses):
            qq = rm.pose_point(m, i, q, skel, pose)
            t2, r2 = ax.polar(qq)
            h = sl.hits(ax, qq[1] + 1e-5, t2)
            if h and r2 > max(h) - margin:
                return False
        return True
    if ok(d):
        return d
    lo, hi = 0.0, d
    for _ in range(10):
        mid = 0.5 * (lo + hi)
        lo, hi = (mid, hi) if ok(mid) else (lo, mid)
    return lo


def fill_rim(m, boot, axes, skel, poses=FILL_POSES, margin=FILL_MARGIN):
    """Гетра без задника (виды «ничего не торчит» и «язык торчит»): между гетрой 3 и стенкой ботинка у его верха сзади
    щель 5–8 мм, сбоку-сверху в неё видна изнанка стенки (у EA её закрывает задник). Вершины гетры под краем ботинка
    (до FILL_DEPTH) — наружу до стенки − margin (меньшее по позам стопы; верх ботинка — на кости голени, почти не
    ходит), над краем — до стенки у края − margin со спадом за FILL_UP; не больше FILL_MAX, только сзади и с боков
    (FILL_SIN), только наружу. boot — Mesh ботинка той же детализации. → отчёт."""
    boots = [rm.Slicer(boot, rm.posed(boot, skel, p) if p[1] else None) for p in poses]
    old = [p[:] for p in m.pos]
    rims = {}
    moved, dmax = 0, 0.0
    for i in range(m.nv):
        side = rm.leg_of(m, i)
        ax = axes[side]
        th, r = ax.polar(m.pos[i])
        y = m.pos[i][1]
        if math.sin(th) >= FILL_SIN:
            continue
        key = (side, round(th, 2))
        if key not in rims:
            rims[key] = boot_rim(boots[0], ax, key[1])
        rim = rims[key]
        if rim is None:
            continue
        ry, rwall = rim
        if y <= ry:
            depth = ry - y
            if depth >= FILL_DEPTH[1]:
                continue
            lim = None
            for sl in boots:
                h = sl.hits(ax, y + 1e-5, th)
                if h:
                    lim = max(h) if lim is None else min(lim, max(h))
            if lim is None:
                continue
            d = max(0.0, lim - margin - r) * (1.0 - rm.smoothstep(FILL_DEPTH[0], FILL_DEPTH[1], depth))
        else:
            dy = y - ry
            if dy >= FILL_UP[1]:
                continue
            d = max(0.0, rwall - margin - r) * (1.0 - rm.smoothstep(FILL_UP[0], FILL_UP[1], dy))
        d = min(d, FILL_MAX)
        if d > 1e-6:
            d = _posed_limit(m, i, axes[side], th, d, boots, poses, skel, margin)
        if d > 1e-6:
            _push(m, i, axes, d)
            moved += 1
            dmax = max(dmax, d)
    frames = rm.update_frames(m, old, rm.Weld(m))
    return {'moved_vertices': moved, 'max_shift_mm': round(dmax * 1000, 2), 'frames_rotated': frames}


# ---------------------------------------------------------------- сборка

def merged(container, a, b):
    """Две сетки одного формата (задник и язык) — одним файлом в контейнере container (skatetongue_0_L): вершины a, затем
    b; полосы a, разрыв, полосы b (номера вершин b — со сдвигом). → байты файла."""
    decl = lambda m: [(e.word0, e.type, e.word2) for e in m.elements]
    if decl(a) != decl(b) or decl(container) != decl(a) or a.stride != b.stride or container.stride != a.stride:
        raise SystemExit('задник и язык — разный формат вершин')
    vb = bytes(a.f.raw[a.vo:a.vo + a.stride * a.nv]) + bytes(b.f.raw[b.vo:b.vo + b.stride * b.nv])
    idx = list(a.indices) + [rm.STRIP_RESTART] + [i if i == rm.STRIP_RESTART else i + a.nv for i in b.indices]
    data = container.rebuilt(vb, idx)
    m = rm.Mesh(data, container.path)
    if sorted(m.tris) != sorted(list(a.tris) + [tuple(i + a.nv for i in t) for t in b.tris]):
        raise SystemExit(f'{container.path}: треугольники после склейки не сходятся')
    return data


def am_copy(data, t_from, t_to):
    """Затенение гетры playersock_<from>_K_am → под именем варианта to (имя растра той же длины)."""
    import teamart as ta
    rw = ta.Rw4(rm.unchunk_any(data), 'am')
    a, b = f'playersock_{t_from}_', f'playersock_{t_to}_'
    n = 0
    for sp, ln in rw.name_slots:
        s_ = bytes(rw.raw[sp:sp + ln]).decode('latin1')
        if a in s_:
            rw.raw[sp:sp + ln] = s_.replace(a, b, 1).encode('latin1')
            n += 1
    if not n:
        raise SystemExit(f'затенение: нет имени растра {a}…')
    return bytes(rw.raw)


def build(base=CACHE, out=OUT, fill=True, log=print):
    """Все файлы четырёх видов в out (раскладка cache:), сводка manifest.json. fill — у видов без задника (1, 2) низ
    гетры подтянуть к стенке ботинка (fill_rim). → ({путь: байты}, сводка)."""
    import hashlib
    use_legacy()
    skel = rm.Skeleton.game()
    axes = (rm.LegAxis(skel, 0), rm.LegAxis(skel, 1))
    piv = tongue_pivot(load(base, rm.TONGUE.format(t=2, lod=2)))
    summary = {'base': base, 'source_variant': SRC_T, 'tongue_move': TONGUE_MOVE, 'tongue_move_lod': TONGUE_MOVE_LOD,
               'tongue_pivot_m': piv,
               'fill': fill, 'fill_margin_mm': FILL_MARGIN * 1000, 'fill_depth_m': list(FILL_DEPTH),
               'fill_up_m': list(FILL_UP), 'fill_max_mm': FILL_MAX * 1000, 'views': NAMES, 'files': {}}
    files = {}

    def put(rel, data, note):
        p = os.path.join(out, *rel.split('/'))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        open(p, 'wb').write(data)
        summary['files'][rel] = dict(note, sha1=hashlib.sha1(data).hexdigest())
        files[rel] = data
        log(f'  {rel}: {note}')
    for lod in LODS:
        srel = rm.SOCK.format(t=SRC_T, lod=lod)
        s3 = load(base, srel)
        # гетры: у 0 сзади родной задник — копия 3 как есть; у 1 и 2 задника нет — низ у стенки ботинка
        put(rm.SOCK.format(t=0, lod=lod), s3.bytes(), {'what': f'копия {srel}'})
        sf = load(base, srel)
        rep = fill_rim(sf, rm.Mesh.game(rm.BOOT.format(lod=lod)), axes, skel) if fill else {}
        for t in (1, 2):
            put(rm.SOCK.format(t=t, lod=lod), sf.bytes(),
                dict(rep, what=f'копия {srel}' + (', низ у стенки ботинка (fill_rim)' if fill else '')))
        # язык: родной skatetongue_2 целиком вперёд
        k2rel, k3rel, k0rel = (rm.TONGUE.format(t=t, lod=lod) for t in (2, 3, 0))
        k2 = load(base, k2rel)
        mv = move_rigid(k2, piv, dict(TONGUE_MOVE, **TONGUE_MOVE_LOD.get(lod, {})))
        put(k2rel, k2.bytes(), {'what': f'{k2rel} EA целиком сдвинут', 'move': mv})
        # кольцо: родной задник skatetongue_3 как есть + тот же язык
        k3 = load(base, k3rel)
        put(k0rel, merged(load(base, k0rel), k3, k2),
            {'what': f'{k3rel} как есть + {k2rel} (сдвинутый) одной сеткой', 'vertices': k3.nv + k2.nv})
    # затенение гетр: у 0, 1, 2 — от 3 (UV те же)
    for k in (0, 1):
        arel = AM.format(t=SRC_T, k=k)
        data = raw_file(base, arel)
        for t in (0, 1, 2):
            put(AM.format(t=t, k=k), am_copy(data, SRC_T, t),
                {'what': f'копия {arel}' + (' (cache: — Edge)' if base_file(base, arel) else ' (архив)')})
    with open(os.path.join(out, 'manifest.json'), 'w', encoding='utf-8', newline='\n') as f:
        json.dump(summary, f, ensure_ascii=False, indent=1)
    for rel, data in files.items():            # файлы разбираются, пересборка своими буферами — байт в байт
        if not rel.endswith('_am.rx2') and not rm.Mesh(data, rel).layout_ok():
            raise SystemExit(f'{rel}: пересборка своими буферами не сходится')
    log(f'файлы: {out} ({len(files)} шт.), сводка — manifest.json')
    return files, summary


# ---------------------------------------------------------------- картинки

SHEET_KIT = '2_23_7'               # PIT, выезд (NHL 27): светлые гетры — форму видно лучше
SHEET_SKATE = 41                   # CCM Jetspeed FT6 (слот A)
SHEET_VIEWS = (('спереди', 0, 0), ('сбоку', -90, 0), ('сзади', 180, 0))
ZOOM_VIEWS = (('сбоку-сверху', -90, 12), ('сзади 3/4 сверху', -135, 22), ('сзади сверху', 180, 35),
              ('спереди 3/4 сверху', -45, 18))
FONT = r'C:\Windows\Fonts\segoeui.ttf'


class Look:
    """Текстуры для картинок: гетра и шорты формы kit (из base, иначе архив), конёк texlib_<skate>, шнуровка."""

    def __init__(self, base=CACHE, kit=SHEET_KIT, skate=SHEET_SKATE):
        use_legacy()
        self.base = base
        tx = lambda rel, name: Tex(raw_file(base, rel), name)
        self.skate = tx(f'rendering/skate/texlib_{skate}.rx2', f'skate_{skate}_cm')
        self.skate_nm = tx(f'rendering/skate/texlib_{skate}.rx2', f'skate_{skate}_nm')
        t999 = raw_file(base, 'rendering/skate/texlib_999.rx2')
        self.lace, self.boot_ao = Tex(t999, 'skatelace_ccm'), Tex(t999, 'playerskate_am')
        self.sock = tx(f'rendering/sock/sock_{kit}_cm.rx2', 'sock_')
        self.sock_nm = tx(f'rendering/sock/sock_{kit.split("_")[0]}_nm.rx2', 'sock_')
        self.pant = tx(f'rendering/pant/texlib_{kit}.rx2', f'pant_{kit}_cm')
        self.ao = {}

    def sock_ao(self, src, t):
        rel = AM.format(t=t, k=0)
        if (src, t) not in self.ao:
            p = os.path.join(src, *rel.split('/')) if src else None
            self.ao[(src, t)] = Tex(open(p, 'rb').read() if p and os.path.exists(p) else raw_file(self.base, rel),
                                    'playersock')
        return self.ao[(src, t)]

    def parts(self, t, src=None, lod=2, pose=None, skel=None):
        """Нога x > 0 варианта t: гетра и деталь — из src (раскладка cache:; None — нынешние из base)."""
        kw = dict(pose=pose, skel=skel)
        get = lambda rel: rm.Mesh.load(os.path.join(src, *rel.split('/'))) if src and os.path.exists(
            os.path.join(src, *rel.split('/'))) else load(self.base, rel)
        ps = [Part(load(self.base, f'rendering/pant/pant_0_0_0_{lod}.rx2'), self.pant, name='pant', **kw),
              Part(get(rm.SOCK.format(t=t, lod=lod)), self.sock, self.sock_nm, self.sock_ao(src, t), name='sock', **kw),
              Part(rm.Mesh.game(rm.BOOT.format(lod=lod)), self.skate, self.skate_nm, self.boot_ao, name='boot', **kw),
              Part(rm.Mesh.game(rm.LACE.format(lod=lod)), self.lace, name='lace', **kw)]
        if t != 1:
            ps.append(Part(get(rm.TONGUE.format(t=t, lod=lod)), self.skate, self.skate_nm, name='tongue', **kw))
        return ps


def shot(parts, yaw, pitch, ylo, yhi, scale, mark=True):
    """Снимок ноги: рамка — по точкам на высотах ylo…yhi (сбоку — по ним же, сверху — по их проекции). → (img, дыры)."""
    import numpy as np
    v = View(yaw, pitch, (0, 0, 1, 1), 10, 10)
    pts = np.concatenate([p.pos[p.tris.reshape(-1)] for p in parts])
    q = v.rot(pts)
    sel = (pts[:, 1] > ylo) & (pts[:, 1] < yhi)
    if pitch:
        fr = (q[sel, 0].min() - 0.01, q[sel, 1].min() - 0.005, q[sel, 0].max() + 0.01, q[sel, 1].max() + 0.005)
    else:
        fr = (q[sel, 0].min() - 0.02, ylo, q[sel, 0].max() + 0.02, yhi)
    v = View(yaw, pitch, fr, int((fr[2] - fr[0]) * scale), int((fr[3] - fr[1]) * scale))
    return render(parts, v, mark=mark)


def grid(rows, cols, cells, path, title='', note=''):
    """Лист: rows — подписи строк, cols — подписи столбцов, cells[r][c] — картинки (h, w, 3) → PNG."""
    from PIL import Image, ImageDraw, ImageFont
    f1, f2, f3 = (ImageFont.truetype(FONT, s) for s in (22, 17, 15))
    cw = [max(cells[r][c].shape[1] for r in range(len(rows))) for c in range(len(cols))]
    rh = [max(cells[r][c].shape[0] for c in range(len(cols))) for r in range(len(rows))]
    lw, top, gap = 210, 64 + (22 if note else 0), 8
    W = lw + sum(cw) + gap * (len(cols) + 1)
    H = top + sum(rh) + gap * (len(rows) + 1)
    im = Image.new('RGB', (W, H), (38, 39, 44))
    d = ImageDraw.Draw(im)
    d.text((12, 8), title, font=f1, fill=(235, 235, 235))
    if note:
        d.text((12, 38), note, font=f3, fill=(180, 180, 180))
    x = lw + gap
    for c, name in enumerate(cols):
        d.text((x + cw[c] // 2, top - 6), name, font=f2, fill=(200, 200, 200), anchor='ms')
        x += cw[c] + gap
    y = top + gap
    for r, name in enumerate(rows):
        lines = name.split('\n')
        for k, ln in enumerate(lines):
            d.text((12, y + rh[r] // 2 - 12 * len(lines) + 24 * k), ln, font=f2 if k == 0 else f3,
                   fill=(235, 235, 235) if k == 0 else (170, 170, 170))
        x = lw + gap
        for c in range(len(cols)):
            img = cells[r][c]
            im.paste(Image.fromarray(img), (x + (cw[c] - img.shape[1]) // 2, y + (rh[r] - img.shape[0]) // 2))
            x += cw[c] + gap
        y += rh[r] + gap
    os.makedirs(os.path.dirname(path), exist_ok=True)
    im.save(path)
    return path


ROWS = [  # (подпись, вариант T, откуда файлы: 'new' — сборка, 'base' — нынешние)
    ('Вид 1 = T 3 (как есть)\n= родной EA 3: гетра 3 + задник 3', 3, 'base'),
    ('Вид 2 = T 1\nгетра 3, ничего не торчит', 1, 'new'),
    ('Вид 3 = T 2\nгетра 3 + язык 2 (сдвинут)', 2, 'new'),
    ('Вид 4 = T 0\nгетра 3 + задник 3 + язык 2', 0, 'new'),
    ('Родной EA 2 (сейчас)\nдля сравнения', 2, 'base'),
]


def sheet(out=OUT, base=CACHE, kit=SHEET_KIT, skate=SHEET_SKATE, pics=None, log=print):
    """Листы: views.png — 4 вида и родной EA 2 спереди/сбоку/сзади (вид 1 — это и есть EA 3); holes.png — места
    возможных дыр крупно (пурпурное — изнанка: в игре там просвет или внутренняя сторона) у видов и EA 0–3;
    poses.png — вид 2 и 4 в позах стопы. → {имя: путь}."""
    pics = pics or os.path.join(os.path.dirname(out), 'pics')
    lk = Look(base, kit, skate)
    skel = rm.Skeleton.game()
    src = lambda w: out if w == 'new' else None
    res = {}
    cells = [[shot(lk.parts(t, src(w)), yaw, pitch, 0.12, 0.42, 1300)[0] for _, yaw, pitch in SHEET_VIEWS]
             for _, t, w in ROWS]
    res['views'] = grid([r[0] for r in ROWS], [v[0] for v in SHEET_VIEWS], cells, os.path.join(pics, 'views.png'),
                        'Четыре вида заправки из гетры 3 (NHL Legacy, ближняя детализация, PIT выезд, CCM FT6)',
                        'Задник — родной skatetongue_3 как есть; язык — родной skatetongue_2 целиком, сдвинут вперёд '
                        f'на {TONGUE_MOVE["fwd_m"] * 1000:.0f} мм и вниз на {-TONGUE_MOVE["up_m"] * 1000:.0f} мм '
                        '(наклон и форма EA). Пурпурное — изнанка.')
    log(f'  лист: {res["views"]}')
    zrows = ROWS[1:4] + [('Родной EA 3', 3, 'base'), ('Родной EA 2', 2, 'base'), ('Родной EA 1', 1, 'base'),
                         ('Родной EA 0', 0, 'base')]
    holes = {}
    zc = []
    for name, t, w in zrows:
        row = []
        for vn, yaw, pitch in ZOOM_VIEWS:
            img, hm = shot(lk.parts(t, src(w)), yaw, pitch, 0.20, 0.31, 3000)
            row.append(img)
            holes[(name.split('\n')[0], vn)] = int(hm.sum())
        zc.append(row)
    res['holes'] = grid([r[0] + '\nизнанка: ' + str(sum(v for (n, _), v in holes.items() if n == r[0].split('\n')[0]))
                         + ' пикс.' for r in zrows], [v[0] for v in ZOOM_VIEWS], zc, os.path.join(pics, 'holes.png'),
                        'Стык гетры, ботинка, языка и задника крупно (0,20–0,31 м)',
                        'Пурпурное — видна изнанка поверхности (в игре там просвет насквозь или внутренняя сторона).')
    log(f'  лист: {res["holes"]}')
    pc, prow = [], []
    for name, t, w in [ROWS[1], ROWS[2], ROWS[3]]:
        row = []
        for pose in rm.SHIN_POSES:
            img, _ = shot(lk.parts(t, src(w), pose=pose, skel=skel), -135, 20, 0.17, 0.33, 1700)
            row.append(img)
        pc.append(row)
        prow.append(name)
    res['poses'] = grid(prow, [rm.pose_name(p).replace(' (', '\n(') .split('\n')[0] for p in rm.SHIN_POSES], pc,
                        os.path.join(pics, 'poses.png'), 'Позы стопы (сзади 3/4 сверху)', '')
    log(f'  лист: {res["poses"]}')
    with open(os.path.join(pics, 'holes.json'), 'w', encoding='utf-8') as f:
        json.dump({f'{a} | {b}': v for (a, b), v in holes.items()}, f, ensure_ascii=False, indent=1)
    return res


# ---------------------------------------------------------------- проверка

CHECK_YS = [0.15 + 0.0025 * k for k in range(70)]       # 0,15…0,32 м
CHECK_NA = 96


def wall_relation(det, sock, axes, ys=CHECK_YS, na=CHECK_NA, y_min=None):
    """Деталь (Slicer) против гетры (Slicer) лучами из оси голени, обе ноги: гетра под деталью (щель — наименьшая), в
    толще детали (снаружи не видно) или снаружи её наружной стенки (видна сквозь деталь). → сводка, мм."""
    n_in = n_wall = n_out = 0
    gap_min, wall_max, out_max = None, 0.0, 0.0
    for side in (0, 1):
        for y in ys:
            if y_min is not None and y < y_min:
                continue
            for k in range(na):
                th = 2 * math.pi * k / na
                dh = det.hits(axes[side], y, th)
                sh = sock.hits(axes[side], y, th)
                if not dh or not sh:
                    continue
                lo, hi, r = min(dh), max(dh), max(sh)
                if r <= lo:
                    n_in += 1
                    gap_min = lo - r if gap_min is None else min(gap_min, lo - r)
                elif r <= hi:
                    n_wall += 1
                    wall_max = max(wall_max, r - lo)
                else:
                    n_out += 1
                    out_max = max(out_max, r - hi)
    return {'rays_under': n_in, 'gap_min_mm': round((gap_min or 0.0) * 1000, 1), 'rays_in_wall': n_wall,
            'in_wall_max_mm': round(wall_max * 1000, 1), 'rays_through': n_out, 'through_max_mm': round(out_max * 1000, 1)}


def obstacle_into(det, obst, axes, ys=CHECK_YS, na=CHECK_NA):
    """Ботинок/шнуровка (Slicer, в позе) против языка (Slicer): лучи, где наружная поверхность препятствия дальше
    внутренней стенки языка (входит в язык или выходит сквозь него). → (лучей, наибольшая глубина, мм)."""
    n, dm = 0, 0.0
    for side in (0, 1):
        for y in ys:
            for k in range(na):
                th = 2 * math.pi * k / na
                dh = det.hits(axes[side], y, th)
                oh = obst.hits(axes[side], y, th)
                if dh and oh and max(oh) > min(dh):
                    n += 1
                    dm = max(dm, max(oh) - min(dh))
    return n, round(dm * 1000, 1)


def check(out=OUT, base=CACHE, poses=rm.SHIN_POSES, log=print):
    """Проверка сборки out: (1) гетры 1 и 2 против ботинка и шнуровки в позах стопы — что изменилось против гетры 3
    (rw4mesh.relation_changes: проход сквозь деталь глубже 1 мм — ПРОВЕРИТЬ); (2) язык (виды 2 и 0) против гетры 3 —
    рядом то же у родного языка EA на гетре 2; (3) ботинок и шнуровка в языке в позах — рядом EA 2. LOD _2, _0, _3.
    → сводка (и check.json в out)."""
    use_legacy()
    skel = rm.Skeleton.game()
    axes = (rm.LegAxis(skel, 0), rm.LegAxis(skel, 1))
    get = lambda rel: rm.Mesh.load(os.path.join(out, *rel.split('/')))
    res, bad = {'socks': [], 'tongue_vs_sock': {}, 'obstacles_in_tongue': {}}, 0
    for lod in LODS:
        s3 = load(base, rm.SOCK.format(t=SRC_T, lod=lod))
        obs = {n: rm.Mesh.game(r.format(lod=lod)) for n, r in (('ботинок', rm.BOOT), ('шнуровка', rm.LACE))}
        for t in (1, 2):
            s1 = get(rm.SOCK.format(t=t, lod=lod))
            if s1.bytes() == s3.bytes():
                continue
            for pose in poses:
                a0 = rm.Slicer(s3, rm.posed(s3, skel, pose) if pose[1] else None)
                a1 = rm.Slicer(s1, rm.posed(s1, skel, pose) if pose[1] else None)
                for name, om in obs.items():
                    osl = rm.Slicer(om, rm.posed(om, skel, pose) if pose[1] else None)
                    ch = rm.relation_changes(a0, a1, osl, axes, CHECK_YS)
                    flag = any(d > 0.001 for k, (n, d) in ch.items() if 'в стенке' not in k)
                    bad += flag
                    if ch:
                        txt = ', '.join(f'{k}: {n} (до {d * 1000:.1f} мм)' for k, (n, d) in ch.items())
                        log(f'  гетра {t} _{lod}, {rm.pose_name(pose)}, {name}: {txt}' + ('  ← ПРОВЕРИТЬ' if flag else ''))
                        res['socks'].append([t, lod, rm.pose_name(pose), name, {k: [n, round(d * 1000, 1)]
                                                                               for k, (n, d) in ch.items()}])
        k_new = rm.Slicer(get(rm.TONGUE.format(t=2, lod=lod)))
        k_ea = rm.Slicer(load(base, rm.TONGUE.format(t=2, lod=lod)))
        s2ea = rm.Slicer(load(base, rm.SOCK.format(t=2, lod=lod)))
        new, ea = wall_relation(k_new, rm.Slicer(s3), axes), wall_relation(k_ea, s2ea, axes)
        res['tongue_vs_sock'][f'_{lod}'] = {'new_on_sock3': new, 'ea_on_sock2': ea}
        log(f'  язык _{lod} на гетре 3: {new}\n         EA 2 на гетре 2: {ea}')
        if new['through_max_mm'] > max(1.0, ea['through_max_mm'] + 0.5):
            bad += 1
            log('    ← ПРОВЕРИТЬ: гетра выходит сквозь язык глубже, чем у EA')
        km, ke = get(rm.TONGUE.format(t=2, lod=lod)), load(base, rm.TONGUE.format(t=2, lod=lod))
        for pose in poses:
            row = {}
            for name, om in obs.items():
                osl = rm.Slicer(om, rm.posed(om, skel, pose) if pose[1] else None)
                a = obstacle_into(rm.Slicer(km, rm.posed(km, skel, pose) if pose[1] else None), osl, axes)
                b = obstacle_into(rm.Slicer(ke, rm.posed(ke, skel, pose) if pose[1] else None), osl, axes)
                row[name] = {'new': a, 'ea2': b}
                if a[1] > max(1.0, b[1] + 0.5):
                    bad += 1
                    log(f'  язык _{lod}, {rm.pose_name(pose)}: {name} входит в язык {a} (у EA 2 {b})  ← ПРОВЕРИТЬ')
            res['obstacles_in_tongue'][f'_{lod} {rm.pose_name(pose)}'] = row
    res['problems'] = bad
    log(f'  итог: {"замечаний нет" if not bad else f"{bad} мест проверить"}')
    with open(os.path.join(out, 'check.json'), 'w', encoding='utf-8', newline='\n') as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    return res


# ---------------------------------------------------------------- команды

def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(prog='socktuck.py', description=__doc__.split('\n\n')[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    ap.add_argument('cmd', choices=('build', 'check', 'sheet', 'fit'))
    ap.add_argument('--base', default=CACHE, help='нынешние файлы (раскладка cache:), по умолчанию cache: пользователя')
    ap.add_argument('--out', default=OUT, help='куда собирать / что проверять')
    ap.add_argument('--no-fill', action='store_true', help='у видов без задника гетру у ботинка не подтягивать')
    ap.add_argument('--kit', default=SHEET_KIT, help='форма для картинок (S_A_V), по умолчанию ' + SHEET_KIT)
    ap.add_argument('--skate', type=int, default=SHEET_SKATE, help='конёк для картинок (texlib_N)')
    a = ap.parse_args(argv)
    if a.cmd == 'build':
        build(a.base, a.out, fill=not a.no_fill)
    elif a.cmd == 'check':
        check(a.out, a.base)
    elif a.cmd == 'sheet':
        sheet(a.out, a.base, a.kit, a.skate)
    else:
        use_legacy()
        skel = rm.Skeleton.game()
        axes = (rm.LegAxis(skel, 0), rm.LegAxis(skel, 1))
        fit_tongue(load(a.base, rm.TONGUE.format(t=2, lod=2)), rm.Slicer(load(a.base, rm.SOCK.format(t=2, lod=2))),
                   rm.Slicer(load(a.base, rm.SOCK.format(t=SRC_T, lod=2))), axes)


if __name__ == '__main__':
    main()
