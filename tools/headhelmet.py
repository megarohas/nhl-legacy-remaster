"""Шапка волос головы Legacy под шлемом: правило, подгонка и проверка (scans24, docs/heads-nhl24.md, «Волосы под шлемом»).

Голова-скан Legacy — одна сетка на все случаи: игра рисует шапку волос (haircap, текстура hair_<id>_cm с альфой) и в
шлеме, и без него; отдельной сетки «под шлем» (как halfmask у NHL 24) или флага нет. Шлем (rendering/helmet/
helmet_<M>_2.rx2, ближняя детализация, кость 10) — одна оболочка без толщины, под ней подкладка padding_<M>_2 (на ~2 см
глубже). Посадку шлема на голову задаёт stockplayerhelmetplacement (сдвиг, поворот, масштаб; 3–4 строки на голову):
строки есть у 365 из 445 сканов EA и у всех типовых; у шаблонов наших голов (10753, 10845, 11145…) и у самих наших
голов их нет — шлем стоит по умолчанию.

Что выяснено 24.10.2026 (пользователь: «у Капризова, Болди и других волосы часто вылазят через шлем»):
  * сканы EA без строк посадки (шлем по умолчанию, как у наших) держат видимую шапку внутри оболочки: у 4 из 8 она
    чуть снаружи отдельных шлемов, до 3,2 мм (чаще CCM Fitlite 23/13); у сканов EA со строками шапка выходит за шлем по
    умолчанию до 35 мм — им игра двигает и масштабирует шлем;
  * у наших голов (сканы NHL 24 и NHL 27, волосы источника запечены на шапку высотой до 12 мм) видимая шапка выходила
    за оболочку на затылке и над ушами: NHL 24 — у 116 из 179 голов (до 15,5 мм), NHL 27 — у 128 из 319 (до 8,4),
    в своём шлеме из базы — у 23 из 173 игроков NHL 24 (до 6,3 мм) и 18 из 305 NHL 27 (до 4,4). Капризов в своём
    Bauer 4500 (1) — 4,1 мм, Болди в своём 21 — 5,0, в 23 — 13,5.

Правило (RULE h2): видимая шапка в зоне шлема — не ближе MARGIN к оболочке самого тесного шлема полевых Legacy (все
модели helmet_models(); по каждому направлению из центра CENTER — меньший радиус оболочки): шлем игрока может смениться
(редактор, обновление составов). Шапка опускается к скальпу вдоль своей нормали ровно на выступ (вершины, середины
рёбер и центры треугольников: между вершинами оболочка бывает вогнута), сдвиг разглаживается по соседям (без
ступеньки на краю шлема), но точки шапки не ниже FLOOR над поверхностью головы (h1 без этого уводил шапку под кожу —
на затылке проступала кожа). Ниже края шлема (на шее, у ушей) шапка не трогается. Считается в позе игры (переносы
суставов общего скелета × InvBind файла головы — как глаза, headeyes.py). Где до шлема тесен сам череп (затылок под
тесными 6, 11, 13/23), шапка ложится на кожу и всё равно выходит наружу — на 1–7 мм; в своём шлеме из базы после
правила снаружи 1 игрок из 478 (Henrique, 1,6 мм в шлеме 25).

  import headhelmet as HH
  env = HH.Envelope.load(cache_dir)          # оболочки шлемов (лучи из CENTER), кэш <cache_dir>/helmet-envelope.npz
  new_pos, rep = HH.fit_cap(pos, capn, off, h, tri, gid, env, head)   # head — не уйти под кожу
  cov, out = env.protrusion(points, model)   # выступ за оболочку, м (> 0 — снаружи шлема)
  rep = HH.head_report(visible_points, head_vertices, env)              # по каждому шлему и по самому тесному, мм
"""
import glob
import os
import time

import numpy as np

RULE = 'h2'                     # версия правила (ключ кэша сборки scans24); h2 — шапка не уходит под кожу
ENVELOPE = 1                    # версия оболочек шлемов (ключ кэша helmet-envelope.npz)
HEAD_CENTRE = np.array([0.0, 1.80, 0.0])   # м — для нормалей головы наружу (как у сборки scans24)
CENTER = np.array([0.0, 1.84, 0.0])   # м — центр лучей: середина шлема в позе привязки (кость 10 — 0; 1,775; −0,006)
NDIR = 30000                    # направлений (сфера Фибоначчи, шаг ~1,3° ≈ 2,5 мм на радиусе шлема)
MARGIN = 0.0015                 # м — шапка не ближе к оболочке шлема: шаг half-float позиций на высоте 1–2 м ~1 мм
                                # (округление 0,5), анимация лба и висков, шаг сетки направлений
FLOOR = 0.0005                  # м — шапка не ниже над скальпом там, где до шлема тесно (обычно CAP_MIN сборки 1,5 мм;
                                # глубина 24 бит на 3 м ~0,01 мм — z-конфликта с кожей нет)
SPREAD = 6                      # итераций разглаживания сдвига по рёбрам шапки (переход ~2–3 ребра)
ALPHA_CUT = 100                 # видимая шапка: альфа hair_cm выше (лист рисует с 90–100)
HOLE_DEG = 2.0                  # непокрытые направления — компоненты по соседям в пределах этого угла; все, кроме
                                # самой большой (лицо, шея), — дыры шлема (вентиляция, щели) и считаются покрытыми


def helmet_models():
    """Номера шлемов полевых с сеткой ближней детализации в распакованных архивах Legacy (cacherender, renderboot;
    у вратарей — свои goaliehelmet). На 24.10.2026 — 18: 1, 6, 7, 8, 11–16, 18–21, 23–25, 110."""
    import rw4mesh as R
    R.use_game('legacy')
    out = set()
    for p in glob.glob(os.path.join(R.PROFILE.big, '*', 'rendering', 'helmet', 'helmet_*_2.rx2')):
        k = os.path.basename(p)[7:-6]
        if k.isdigit():
            out.add(int(k))
    if not out:
        raise SystemExit(f'нет сеток шлемов rendering/helmet/helmet_*_2.rx2 в {R.PROFILE.big}')
    return tuple(sorted(out))


def fib(n):
    i = np.arange(n) + 0.5
    phi = np.arccos(1 - 2 * i / n)
    th = np.pi * (1 + 5 ** 0.5) * i
    return np.stack([np.cos(th) * np.sin(phi), np.cos(phi), np.sin(th) * np.sin(phi)], 1)


def raycast_far(o, d, p, t, chunk=192):
    """Лучи из o по направлениям d → дальнее попадание в сетку (p, t) по каждому лучу (−inf — мимо)."""
    v0 = p[t[:, 0]]
    e1, e2 = p[t[:, 1]] - v0, p[t[:, 2]] - v0
    s = o - v0
    q = np.cross(s, e1)
    far = np.full(len(d), -np.inf)
    for a in range(0, len(d), chunk):
        D = d[a:a + chunk]
        pv = np.cross(D[:, None, :], e2[None])
        det = (pv * e1[None]).sum(-1)
        ok = np.abs(det) > 1e-12
        inv = np.where(ok, 1.0 / np.where(ok, det, 1.0), 0.0)
        u = (pv * s[None]).sum(-1) * inv
        v = (D[:, None, :] * q[None]).sum(-1) * inv
        tt = (q[None] * e2[None]).sum(-1) * inv
        hit = ok & (u >= 0) & (v >= 0) & (u + v <= 1) & (tt > 1e-5)
        far[a:a + chunk] = np.where(hit, tt, -np.inf).max(1)
    return far


def model_envelope(M, n=NDIR):
    """Оболочка шлема M: радиус оболочки из CENTER по n направлениям; дыры (вентиляция, щели) заполнены по краям."""
    from scipy.spatial import cKDTree
    import rw4mesh as R
    R.use_game('legacy')
    m = R.Mesh.game(f'rendering/helmet/helmet_{M}_2.rx2')
    d = fib(n)
    r = raycast_far(CENTER, d, np.array([q[:3] for q in m.pos]), np.array(m.tris, np.int64))
    hit = np.isfinite(r)
    nb = cKDTree(d).query_ball_point(d, np.radians(HOLE_DEG))
    lab = -np.ones(n, np.int64)
    k = 0
    for i in range(n):
        if hit[i] or lab[i] >= 0:
            continue
        st, lab[i] = [i], k
        while st:
            j = st.pop()
            for x in nb[j]:
                if not hit[x] and lab[x] < 0:
                    lab[x] = k
                    st.append(x)
        k += 1
    hole = np.zeros(n, bool)
    if k:
        big = np.bincount(lab[lab >= 0], minlength=k).argmax()
        hole = (~hit) & (lab != big)
    if hole.any():
        dd, jj = cKDTree(d[hit]).query(d[hole], k=6)
        w = 1.0 / np.maximum(dd, 1e-5)
        r[hole] = (r[hit][jj] * w).sum(1) / w.sum(1)
    return r, hit | hole


class Envelope:
    """Оболочки шлемов: radius[M] — радиус оболочки шлема M по направлениям dirs (inf — не покрыто)."""

    def __init__(self, dirs, radius):
        from scipy.spatial import cKDTree
        self.dirs, self.radius = dirs, radius
        self.models = tuple(sorted(radius))
        self.tree = cKDTree(dirs)

    @classmethod
    def load(cls, cache_dir, jobs=6):
        fn = os.path.join(cache_dir, 'helmet-envelope.npz')
        models = helmet_models()
        if os.path.exists(fn):
            z = np.load(fn)
            if 'version' in z and int(z['version']) == ENVELOPE and int(z['ndir']) == NDIR                     and tuple(z['models'].tolist()) == models:
                return cls(fib(NDIR), {M: z[f'r{M}'] for M in models})
        t0 = time.time()
        from concurrent.futures import ProcessPoolExecutor
        with ProcessPoolExecutor(max_workers=jobs) as ex:
            res = dict(zip(models, ex.map(model_envelope, models)))
        radius = {M: np.where(c, r, np.inf) for M, (r, c) in res.items()}
        os.makedirs(cache_dir, exist_ok=True)
        np.savez_compressed(fn, version=ENVELOPE, ndir=NDIR, models=np.array(models),
                            **{f'r{M}': v for M, v in radius.items()})
        print(f'оболочки шлемов {models}: {time.time() - t0:.0f} с → {fn}', flush=True)
        return cls(fib(NDIR), radius)

    def limit(self, pts, model=None, k=4):
        """Точки (позы игры) → (покрыты шлемом, радиус оболочки из CENTER, расстояние точки от CENTER). Покрыта шлемом —
        если покрыто ближайшее направление; радиус — по покрытым из k ближайших (вес 1/угол). model=None — самый тесный:
        меньший радиус из шлемов, покрывающих точку."""
        v = pts - CENTER
        r = np.linalg.norm(v, axis=1)
        dd, jj = self.tree.query(v / np.maximum(r, 1e-9)[:, None], k=k)
        w0 = 1.0 / np.maximum(dd, 1e-5)
        cov = np.zeros(len(pts), bool)
        lim = np.full(len(pts), np.inf)
        for M in (self.models if model is None else (model,)):
            rr = self.radius[M][jj]
            fin = np.isfinite(rr)
            w = np.where(fin, w0, 0.0)
            lm = (np.where(fin, rr, 0.0) * w).sum(1) / np.maximum(w.sum(1), 1e-12)
            lim = np.where(fin[:, 0], np.minimum(lim, lm), lim)
            cov |= fin[:, 0]
        return cov, lim, r

    def protrusion(self, pts, model=None):
        """→ (покрыты, выступ за оболочку, м: > 0 — точка снаружи шлема)."""
        cov, lim, r = self.limit(pts, model)
        return cov, np.where(cov, r - lim, -np.inf)


def cap_samples(tri):
    """Точки проверки шапки: вершины, середины рёбер, центры треугольников → (номера вершин [n, 3], веса [n, 3]).
    Между вершинами оболочка шлема бывает вогнута (рёбра жёсткости, затылок), и хорда треугольника выходит наружу."""
    nv = int(tri.max()) + 1
    ea, eb = np.unique(np.sort(np.concatenate([tri[:, [0, 1]], tri[:, [1, 2]], tri[:, [0, 2]]]), 1), axis=0).T
    v = np.arange(nv)
    idx = np.concatenate([np.stack([v, v, v], 1), np.stack([ea, eb, eb], 1), tri])
    w = np.concatenate([np.tile([1.0, 0.0, 0.0], (nv, 1)), np.tile([0.5, 0.5, 0.0], (len(ea), 1)),
                        np.full((len(tri), 3), 1 / 3)])
    return idx, w


def head_height(q, head):
    """Знаковая высота точек q над поверхностью головы head {'pos', 'tri', 'nrm'} (ближайшая точка, нормаль наружу)
    → (высота, м; нормаль головы в ближайшей точке)."""
    from fb import kit3d
    t_, b_, d_ = kit3d.project(q, np.zeros_like(q), head, k=16, min_dot=-2.0)
    T = head['tri'][t_]
    x = sum(b_[:, k:k + 1] * head['pos'][T[:, k]] for k in range(3))
    n = sum(b_[:, k:k + 1] * head['nrm'][T[:, k]] for k in range(3))
    n = n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
    n = np.where(((x - HEAD_CENTRE) * n).sum(1, keepdims=True) < 0, -n, n)
    return np.where(((q - x) * n).sum(1) < 0, -d_, d_), n


def fit_cap(pos, capn, off, h, tri, gid, env, head=None, margin=MARGIN, floor=FLOOR, spread=SPREAD):
    """Шапка внутрь шлема. pos — вершины шапки (поза привязки), capn — нормали наружу, off — сдвиг вершин в позу игры
    (game_pose − pos), h — высота над скальпом вдоль capn, tri — треугольники, gid — номер вершины после склейки шва,
    head — голова {'pos', 'tri', 'nrm'} в той же позе: опущенная шапка не уходит под кожу (точки шапки — не ниже FLOOR
    над поверхностью головы; без этого на затылке проступала кожа — Капризов, Болди, 24.10).
    → (новые pos, отчёт: сдвинуто вершин, сдвиг max мм, выступ до/после max мм (вершины, середины рёбер, центры),
    вершин, которым не хватило места до кожи)."""
    idx, wt = cap_samples(tri)
    at = lambda q: (q[idx] * wt[..., None]).sum(1)
    ng = gid.max() + 1

    def weld_max(x):                            # вершины шва — один сдвиг (больший)
        g = np.zeros(ng)
        np.maximum.at(g, gid, x)
        return g[gid]

    def weld_mean(x):
        a, c = np.zeros(ng), np.zeros(ng)
        np.add.at(a, gid, x)
        np.add.at(c, gid, 1)
        return (a / c)[gid]
    q0 = pos + off
    _, out0 = env.protrusion(at(q0))
    room = np.maximum(h - floor, 0.0)
    need = np.zeros(len(pos))
    for _ in range(10):                         # опускание вдоль нормали: выступ точки / cos(нормаль, луч из центра)
        q = at(q0 - capn * need[:, None])
        cov, lim, r = env.limit(q)
        exc = np.where(cov, r - (lim - margin), -np.inf)
        if not (exc > 1e-5).any():
            break
        cosa = np.clip((((q - CENTER) / np.maximum(r, 1e-9)[:, None]) * at(capn)).sum(1), 0.35, 1.0)
        inc = np.zeros(len(pos))
        for k in range(3):                      # точка на ребре/в треугольнике — сдвиг всем её вершинам
            m = wt[:, k] > 0
            np.maximum.at(inc, idx[m, k], np.maximum(exc[m], 0.0) / cosa[m])
        need = weld_max(np.minimum(need + inc, room))
    ea, eb = np.unique(np.sort(np.concatenate([tri[:, [0, 1]], tri[:, [1, 2]], tri[:, [0, 2]]]), 1), axis=0).T
    s = need.copy()
    for _ in range(spread):                     # разгладить: сдвиг расходится к соседям, но не меньше нужного
        acc, cnt = np.zeros(len(s)), np.zeros(len(s))
        np.add.at(acc, ea, s[eb])
        np.add.at(acc, eb, s[ea])
        np.add.at(cnt, ea, 1)
        np.add.at(cnt, eb, 1)
        s = np.minimum(np.maximum(need, weld_mean(0.5 * s + 0.5 * np.where(cnt > 0, acc / np.maximum(cnt, 1), s))), room)
    if head is not None and (s > 1e-5).any():  # не под кожу: точка шапки (и середины рёбер) не ниже FLOOR над головой
        d0, _ = head_height(at(pos), head)
        moved_s = (s[idx] * (wt > 0)).max(1) > 1e-5
        for _ in range(4):
            d, hn = head_height(at(pos - capn * s[:, None]), head)
            low = moved_s & (d < np.minimum(floor, d0) - 1e-5)
            if not low.any():
                break
            cosb = np.clip((at(capn) * hn).sum(1), 0.35, 1.0)
            dec = np.zeros(len(pos))
            for k in range(3):
                m = low & (wt[:, k] > 0)
                np.maximum.at(dec, idx[m, k], (np.minimum(floor, d0[m]) - d[m]) / cosb[m])
            s = np.maximum(s - weld_max(dec), 0.0)
    new = pos - capn * s[:, None]
    _, out1 = env.protrusion(at(new + off))
    fin = lambda a: round(float(a[np.isfinite(a)].max()) * 1000, 2) if np.isfinite(a).any() else None
    rep = {'rule': RULE, 'moved': int((s > 1e-5).sum()), 'shift_max_mm': round(float(s.max()) * 1000, 2),
           'out_before_mm': fin(out0), 'out_after_mm': fin(out1),
           'no_room': int(((s < need - 1e-4) | ((need >= room - 1e-6) & (need > 1e-5))).sum())}
    return new, rep


def visible_points(pos, uv, tri, alpha):
    """Точки шапки (вершины, центры и середины рёбер треугольников) → те, где альфа hair_cm видима (> ALPHA_CUT)."""
    pts, uvs = [pos], [uv]
    for bw in ((1 / 3, 1 / 3, 1 / 3), (0.5, 0.5, 0), (0, 0.5, 0.5), (0.5, 0, 0.5)):
        pts.append(sum(bw[k] * pos[tri[:, k]] for k in range(3)))
        uvs.append(sum(bw[k] * uv[tri[:, k]] for k in range(3)))
    pts, uvs = np.concatenate(pts), np.concatenate(uvs)
    h, w = alpha.shape[:2]                      # билинейно, как scans24.sample (повтор по краю)
    x = np.clip(np.mod(uvs[:, 0], 1.0) * w - 0.5, 0, w - 1)
    y = np.clip(np.mod(uvs[:, 1], 1.0) * h - 0.5, 0, h - 1)
    x0, y0 = np.floor(x).astype(int), np.floor(y).astype(int)
    x1, y1 = np.minimum(x0 + 1, w - 1), np.minimum(y0 + 1, h - 1)
    fx, fy = x - x0, y - y0
    t = alpha[..., 0].astype(np.float32)
    a = t[y0, x0] * (1 - fx) * (1 - fy) + t[y0, x1] * fx * (1 - fy) + t[y1, x0] * (1 - fx) * fy + t[y1, x1] * fx * fy
    return pts[a > ALPHA_CUT]


def head_report(pts, scalp, env):
    """Видимые точки шапки и вершины головы (поза игры) → выступ за оболочку по каждому шлему и по самому тесному, мм."""
    out = {}
    for M in (None,) + env.models:
        _, o = env.protrusion(pts, M) if len(pts) else (None, np.array([-np.inf]))
        _, sc = env.protrusion(scalp, M)
        o = o[np.isfinite(o)]
        sc = sc[np.isfinite(sc)]
        out['tight' if M is None else str(M)] = {
            'out_mm': round(float(o.max()) * 1000, 2) if len(o) else None, 'n_out': int((o > 0).sum()),
            'scalp_mm': round(float(sc.max()) * 1000, 2) if len(sc) else None}
    return out
