"""Поза превью формы EA: карта «пиксель превью меню → UV свитера» и затенение — по превью и текстурам EA стиля 1.

Превью формы в меню (fe/ion/artassets/jerseys/jersey_1_A_V.big, 256² 8888) у всех комплектов EA стиля 1
(Reebok Edge) — один и тот же манекен в одной позе (руки опущены), свитер на нём — та же сетка, только текстура
своя (rendering/jersey/texlib_1_A_V.rx2, jersey_1_A_V_cm). Значит, пиксель превью p показывает одну и ту же
точку развёртки uv(p) у всех клубов, с одним и тем же затенением: P_k(p) ≈ gain(p)·T_k(uv(p)) + bias(p).
Сотни клубов с разными рисунками — как сотни «структурированных подсветок»: uv(p) находится по корреляции цвета
пикселя превью по всем клубам с цветом текселя по всем клубам; gain/bias — регрессией по клубам. Манекен, фон и
прозрачность (там, где цвет от клуба не зависит) — медиана по клубам.

С моделью превью любой своей формы — как у EA: та же поза, складки и свет (czkit.py, превью меню вместо своей
отрисовки сетки в позе привязки).

    python fepose.py fit [--game nhl13|legacy] [--out MODEL] [--max N]   # модель → MODEL (по умолчанию
                                       # game/work/<…>/fepose/pose.bin); кеш разжатых картинок — рядом
    python fepose.py check MODEL [--game G] [--sheet PNG] [--kits A_V,…]  # превью EA, предсказанные по их
                                       # текстурам: PSNR по свитеру; лист «EA | модель | разница»
    python fepose.py render MODEL TEXTURE.png OUT.png   # превью по развёртке свитера (PNG 1024² или 512²)
    python fepose.py shade MODEL OUT.png --game G [--kits …]   # перенос затенения: та же карта uv, gain/bias —
                                       # по превью другой игры (у Legacy цвета насыщеннее) → новая MODEL

Формат модели (MODEL, little-endian): b'FEPOSE1\\0', u32 w, h; затем по пикселю (w·h): f32 u, f32 v (−1 —
не свитер), f32 gain[3], f32 bias[3], u8 база RGBA (манекен/фон/прозрачность), u8 альфа свитера. Читается
стандартной библиотекой (czkit.FePose). Модель выводится из арта EA — лежит в game/work, не в git.

Нужны numpy и Pillow (game/work/menu12/venv/Scripts/python.exe). Разбор файлов — teamart, kitpaint.
"""
import os, struct, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import numpy as np            # noqa: E402
import teamart as ta          # noqa: E402
import kitpaint as kp         # noqa: E402
import gameprofile            # noqa: E402

MAGIC = b'FEPOSE1\0'
SIZE = 256
STYLE = 1


def log(*a):
    print(*a, flush=True)


def work_dir(game):
    P = gameprofile.get(game)
    return P.work_dir('fepose') if game != 'nhl13' else os.path.join(P.game, 'work', 'uniforms', 'fepose')


# ---------------------------------------------------------------- файлы

def _nhl13_source(rel):
    """Файл NHL 13 без записи в кеш шаблонов kitpaint (их сотни): распакованное дерево, кеш, диск."""
    g = kp.game_dir()
    arc = kp.archive_of(rel)
    for p in (os.path.join(g, 'extracted', 'big', arc, *rel.split('/')),
              os.path.join(g, 'work', 'uniforms', 'templates', *rel.split('/'))):
        if os.path.exists(p):
            return kp._unchunk(open(p, 'rb').read())
    path, entries, unpack_big = kp._disc_entries(arc)
    e = entries.get(rel)
    if e is None:
        return None
    with open(path, 'rb') as f:
        f.seek(e.offset)
        blob = f.read(e.stored_size)
    if e.is_packed:
        blob = unpack_big.decompress_packed_member(blob, e.unpacked_size)
    return kp._unchunk(blob)


def source(rel, game):
    if game == 'nhl13':
        return _nhl13_source(rel)
    P = gameprofile.get(game)
    p = P.extracted(rel)
    return kp._unchunk(open(p, 'rb').read()) if p else None


def preview_rel(a, v):
    return f'fe/ion/artassets/jerseys/jersey_{STYLE}_{a}_{v}.big'


def texture_rel(a, v):
    return f'rendering/jersey/texlib_{STYLE}_{a}_{v}.rx2'


def kit_list(game):
    """Комплекты стиля 1, у которых есть и превью, и свитер: [(A, V)] (variant = fevariant у всех строк EA)."""
    P = gameprofile.get(game)
    fe_dir = None
    for arc in ('cache', 'tu2-patch'):
        d = os.path.join(P.big, arc, 'fe', 'ion', 'artassets', 'jerseys')
        if os.path.isdir(d):
            fe_dir = d
            break
    out = []
    for fn in sorted(os.listdir(fe_dir)):
        if not fn.startswith(f'jersey_{STYLE}_') or not fn.endswith('.big'):
            continue
        a, v = fn[len(f'jersey_{STYLE}_'):-4].split('_')
        out.append((int(a), int(v)))
    return sorted(out)


def load_preview(rel, game):
    data = source(rel, game)
    if data is None:
        return None
    w, h, px = ta.UiLogo(data, rel).decode()
    return np.frombuffer(bytes(px), np.uint8).reshape(h, w, 4)


def cm_texture(rw):
    ts = [t for t in rw.textures if t.name.startswith('jersey') and '_cm' in t.name]
    return ts[0] if ts else None


def load_texture(rel, game, levels=(1, 2)):
    data = source(rel, game)
    if data is None:
        return None
    rw = ta.Rw4(data, rel)
    t = cm_texture(rw)
    if t is None or t.layout.levels[0][:2] != (1024, 1024):
        return None
    out = {}
    for lv in levels:
        w, h, px = kp.tex_decode(rw, t, lv)
        out[lv] = np.frombuffer(bytes(px), np.uint8).reshape(h, w, 4)[:, :, :3]
    return out


def load_set(game, maxn=None, log=log):
    """Превью (N, 256, 256, 4) и свитера: уровни мипов 1 (512²) и 2 (256²), с кешем .npz в папке работы."""
    wd = work_dir(game)
    os.makedirs(wd, exist_ok=True)
    cache = os.path.join(wd, f'set-{game}' + (f'-{maxn}' if maxn else '') + '.npz')
    if os.path.exists(cache):
        z = np.load(cache)
        kits = [tuple(k) for k in z['kits']]
        log(f'набор из кеша {cache}: {len(kits)} комплектов')
        return kits, z['prev'], z['t1'], z['t2']
    kits, prev, t1, t2 = [], [], [], []
    t0 = time.time()
    for i, (a, v) in enumerate(kit_list(game)):
        if maxn and len(kits) >= maxn:
            break
        p = load_preview(preview_rel(a, v), game)
        t = load_texture(texture_rel(a, v), game)
        if p is None or t is None or p.shape != (SIZE, SIZE, 4):
            continue
        kits.append((a, v))
        prev.append(p)
        t1.append(t[1])
        t2.append(t[2])
        if len(kits) % 50 == 0:
            log(f'  {len(kits)} комплектов, {time.time() - t0:.0f} с')
    prev, t1, t2 = np.stack(prev), np.stack(t1), np.stack(t2)
    np.savez(cache, kits=np.array(kits), prev=prev, t1=t1, t2=t2)
    log(f'набор: {len(kits)} комплектов стиля {STYLE} ({game}), {time.time() - t0:.0f} с → {cache}')
    return kits, prev, t1, t2


# ---------------------------------------------------------------- подгонка

def _norm_rows(x):
    """(M, N, 3) → (M, 3N): вычесть среднее по клубам в каждом канале, нормировать строку."""
    x = x - x.mean(axis=1, keepdims=True)
    x = x.reshape(x.shape[0], -1)
    n = np.linalg.norm(x, axis=1, keepdims=True)
    return x / np.maximum(n, 1e-6), n[:, 0]


def bilinear(tex, u, v):
    """tex (N, H, W, 3) uint8/float; u, v (M,) в [0, 1) → (M, N, 3) float32 (повтор по краям)."""
    n, h, w = tex.shape[:3]
    fx, fy = u * w - 0.5, v * h - 0.5
    x0, y0 = np.floor(fx).astype(np.int64), np.floor(fy).astype(np.int64)
    tx, ty = (fx - x0)[:, None, None], (fy - y0)[:, None, None]
    xa, xb = np.clip(x0, 0, w - 1), np.clip(x0 + 1, 0, w - 1)
    ya, yb = np.clip(y0, 0, h - 1), np.clip(y0 + 1, 0, h - 1)
    g = lambda yy, xx: tex[:, yy, xx, :].transpose(1, 0, 2).astype(np.float32)
    return (g(ya, xa) * (1 - tx) + g(ya, xb) * tx) * (1 - ty) + (g(yb, xa) * (1 - tx) + g(yb, xb) * tx) * ty


def fit(game, maxn=None, var_min=6.0, smooth=3, lam=0.0006, log=log):
    kits, prev, t1, t2 = load_set(game, maxn, log)
    n = len(kits)
    rgb = prev[:, :, :, :3].astype(np.float32)
    alpha = prev[:, :, :, 3]
    # где цвет зависит от клуба — свитер; остальное (манекен, фон, прозрачность) — медиана
    std = rgb.std(axis=0).mean(axis=2)                       # (256, 256)
    base = np.median(prev, axis=0).astype(np.uint8)          # (256, 256, 4)
    jm = (std > var_min) & (np.median(alpha, axis=0) > 0)
    ys, xs = np.nonzero(jm)
    m = len(ys)
    log(f'свитер на превью: {m} пикселей из {SIZE * SIZE} (разброс по клубам > {var_min})')
    X, xn = _norm_rows(rgb[:, ys, xs, :].transpose(1, 0, 2))           # (M, 3N)
    # грубо: тексели 256² (мип 2)
    T2 = t2.astype(np.float32)
    tstd = T2.std(axis=0).mean(axis=2)
    tys, txs = np.nonzero(tstd > 2.0)
    Y, _ = _norm_rows(T2[:, tys, txs, :].transpose(1, 0, 2))           # (U, 3N)
    log(f'тексели-кандидаты (256²): {len(tys)}')
    best = np.zeros(m, np.int64)
    score = np.zeros(m, np.float32)
    t0 = time.time()
    ch = 1024
    Yt = np.ascontiguousarray(Y.T)
    for s in range(0, m, ch):
        c = X[s:s + ch] @ Yt
        best[s:s + ch] = c.argmax(axis=1)
        score[s:s + ch] = c.max(axis=1)
    log(f'грубый поиск: {time.time() - t0:.0f} с, корреляция медиана {np.median(score):.3f}')
    u2 = (txs[best] + 0.5) / 256.0
    v2 = (tys[best] + 0.5) / 256.0
    # точно: окно ±3 текселя на 512² (мип 1), затем парабола по пику
    T1 = t1                                                            # (N, 512, 512, 3) uint8
    cx = np.floor(u2 * 512).astype(np.int64)
    cy = np.floor(v2 * 512).astype(np.int64)
    R = 3
    offs = [(dy, dx) for dy in range(-R, R + 1) for dx in range(-R, R + 1)]
    fu = np.zeros(m, np.float32)
    fv = np.zeros(m, np.float32)
    fs = np.zeros(m, np.float32)
    t0 = time.time()
    ch = 256
    for s in range(0, m, ch):
        e = min(m, s + ch)
        k = e - s
        sc = np.zeros((k, len(offs)), np.float32)
        for j, (dy, dx) in enumerate(offs):
            yy = np.clip(cy[s:e] + dy, 0, 511)
            xx = np.clip(cx[s:e] + dx, 0, 511)
            f, _ = _norm_rows(T1[:, yy, xx, :].transpose(1, 0, 2).astype(np.float32))
            sc[:, j] = (f * X[s:e]).sum(axis=1)
        jb = sc.argmax(axis=1)
        fs[s:e] = sc[np.arange(k), jb]
        g = sc.reshape(k, 2 * R + 1, 2 * R + 1)
        by, bx = jb // (2 * R + 1), jb % (2 * R + 1)
        # парабола по соседям (на краю окна — без поправки)
        def para(a, b, c):
            d = a - 2 * b + c
            with np.errstate(divide='ignore', invalid='ignore'):
                return np.where(np.abs(d) > 1e-6, 0.5 * (a - c) / d, 0.0).clip(-0.5, 0.5)
        ok_x = (bx > 0) & (bx < 2 * R)
        ok_y = (by > 0) & (by < 2 * R)
        ii = np.arange(k)
        gx = np.where(ok_x, para(g[ii, by, np.maximum(bx - 1, 0)], g[ii, by, bx], g[ii, by, np.minimum(bx + 1, 2 * R)]), 0)
        gy = np.where(ok_y, para(g[ii, np.maximum(by - 1, 0), bx], g[ii, by, bx], g[ii, np.minimum(by + 1, 2 * R), bx]), 0)
        fu[s:e] = (cx[s:e] + bx - R + 0.5 + gx) / 512.0
        fv[s:e] = (cy[s:e] + by - R + 0.5 + gy) / 512.0
    log(f'точный поиск (512², ±{R}): {time.time() - t0:.0f} с, корреляция медиана {np.median(fs):.3f}, '
        f'< 0,8: {(fs < 0.8).sum()}, < 0,6: {(fs < 0.6).sum()}')
    if smooth:
        fu, fv, fs = propagate(X, t1, ys, xs, fu * 512, fv * 512, smooth, lam, log)
        fu, fv = fu / 512.0, fv / 512.0
    model = shade_fit(prev, t1, ys, xs, fu, fv, base, log)
    model['score'] = fs
    return kits, model


def propagate(X, T1, ys, xs, U, V, iters=3, lam=0.0006, log=log):
    """Уточнение карты (как PatchMatch): кандидаты пикселя — своя точка и точки 8 соседей, каждая ±1 тексель 512²;
    цель — корреляция минус lam·(расстояние до 3-го ближайшего соседа, не больше 40 текселей): одиночный шум и
    мелкие пятна в однотонных местах свитера (там корреляция почти одна по всей зоне) уходят к соседям, а на шве
    развёртки у пикселя остаются свои соседи по куску. Затем — парабола по пику (доли текселя)."""
    m, n = len(ys), T1.shape[0]
    t0 = time.time()
    tnorm = np.zeros((512, 512), np.float32)
    for y0 in range(0, 512, 32):
        blk = T1[:, y0:y0 + 32].astype(np.float32)
        tnorm[y0:y0 + 32] = np.sqrt(((blk - blk.mean(axis=0)) ** 2).sum(axis=(0, 3)))
    tnorm = np.maximum(tnorm, 1e-3)
    Xr = X.reshape(m, n, 3)
    idx = -np.ones((SIZE, SIZE), np.int64)
    idx[ys, xs] = np.arange(m)
    nbs = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]
    U, V = np.floor(U).astype(np.int64), np.floor(V).astype(np.int64)

    def neighbors():
        nu = np.full((m, 8), np.nan, np.float32)
        nv = np.full((m, 8), np.nan, np.float32)
        for j, (dy, dx) in enumerate(nbs):
            yy, xx = ys + dy, xs + dx
            ok = (yy >= 0) & (yy < SIZE) & (xx >= 0) & (xx < SIZE)
            k = np.full(m, -1)
            k[ok] = idx[yy[ok], xx[ok]]
            v = k >= 0
            nu[v, j], nv[v, j] = U[k[v]] + 0.5, V[k[v]] + 0.5
        return nu, nv

    def corr(pi, cx, cy):
        t = T1[:, cy, cx, :].astype(np.float32)                         # (N, P, K, 3)
        return np.einsum('npkc,pnc->pk', t, Xr[pi]) / tnorm[cy, cx]

    def penalty(px, py, nu, nv):
        d = np.sqrt((px[:, :, None] - nu[:, None, :]) ** 2 + (py[:, :, None] - nv[:, None, :]) ** 2)
        d = np.where(np.isnan(d), np.inf, d)
        d.sort(axis=2)
        cnt = np.isfinite(nu).sum(axis=1)                               # сколько соседей-свитеров
        third = d[:, :, 2]
        few = cnt < 3                                                   # у края: по последнему из имеющихся
        if few.any():
            last = d[few][:, :, :].copy()
            last[np.isinf(last)] = 0
            third[few] = last.max(axis=2)
        return lam * np.minimum(third, 40.0)

    offs = np.array([(dy, dx) for dy in (-1, 0, 1) for dx in (-1, 0, 1)])
    sc_all = np.zeros(m, np.float32)
    for it in range(iters):
        nu, nv = neighbors()
        changed = 0
        for s in range(0, m, 256):
            e = min(m, s + 256)
            pi = np.arange(s, e)
            cu = np.concatenate([U[pi, None] + 0.5, nu[pi]], axis=1)    # (P, 9) центры
            cv = np.concatenate([V[pi, None] + 0.5, nv[pi]], axis=1)
            valid = np.isfinite(cu)
            cu, cv = np.where(valid, cu, U[pi, None] + 0.5), np.where(valid, cv, V[pi, None] + 0.5)
            cx = (np.floor(cu)[:, :, None] + offs[None, None, :, 1]).reshape(len(pi), -1).clip(0, 511).astype(np.int64)
            cy = (np.floor(cv)[:, :, None] + offs[None, None, :, 0]).reshape(len(pi), -1).clip(0, 511).astype(np.int64)
            sc = corr(pi, cx, cy)
            obj = sc - penalty(cx + 0.5, cy + 0.5, nu[pi], nv[pi])
            b = obj.argmax(axis=1)
            ii = np.arange(len(pi))
            nx, ny = cx[ii, b], cy[ii, b]
            changed += int(((nx != U[pi]) | (ny != V[pi])).sum())
            U[pi], V[pi] = nx, ny
            sc_all[pi] = sc[ii, b]
        log(f'  сглаживание, проход {it + 1}: сменили точку {changed} пикселей, корреляция медиана {np.median(sc_all):.4f}')
    # доли текселя: парабола по 3×3 вокруг найденной точки
    fu, fv = np.zeros(m, np.float32), np.zeros(m, np.float32)
    for s in range(0, m, 512):
        e = min(m, s + 512)
        pi = np.arange(s, e)
        cx = (U[pi, None] + offs[None, :, 1]).clip(0, 511)
        cy = (V[pi, None] + offs[None, :, 0]).clip(0, 511)
        g = corr(pi, cx, cy).reshape(len(pi), 3, 3)

        def para(a, b, c):
            d = a - 2 * b + c
            with np.errstate(divide='ignore', invalid='ignore'):
                return np.where(np.abs(d) > 1e-6, 0.5 * (a - c) / d, 0.0).clip(-0.5, 0.5)
        fu[pi] = U[pi] + 0.5 + para(g[:, 1, 0], g[:, 1, 1], g[:, 1, 2])
        fv[pi] = V[pi] + 0.5 + para(g[:, 0, 1], g[:, 1, 1], g[:, 2, 1])
    log(f'сглаживание: {time.time() - t0:.0f} с')
    return fu, fv, sc_all


def shade_fit(prev, t1, ys, xs, fu, fv, base, log=log, keep=None):
    """gain/bias по клубам в каждом канале (наименьшие квадраты) по уже найденной карте uv; keep — какие клубы."""
    rgb = prev[:, ys, xs, :3].astype(np.float32).transpose(1, 0, 2)    # (M, N, 3)
    t = bilinear(t1, fu, fv)                                             # (M, N, 3)
    if keep is not None:
        rgb, t = rgb[:, keep], t[:, keep]
    tm, pm = t.mean(axis=1, keepdims=True), rgb.mean(axis=1, keepdims=True)
    cov = ((t - tm) * (rgb - pm)).mean(axis=1)
    var = ((t - tm) ** 2).mean(axis=1)
    gain = np.where(var > 1.0, cov / np.maximum(var, 1e-6), 0.0)
    bias = pm[:, 0, :] - gain * tm[:, 0, :]
    pred = gain[:, None, :] * t + bias[:, None, :]
    res = np.sqrt(((pred - rgb) ** 2).mean(axis=(1, 2)))
    log(f'затенение: gain медиана {np.median(gain):.3f}, остаток (СКО) медиана {np.median(res):.1f}, '
        f'90 % {np.percentile(res, 90):.1f}')
    ja = np.median(prev[:, ys, xs, 3], axis=0).astype(np.uint8)
    return {'ys': ys, 'xs': xs, 'u': fu, 'v': fv, 'gain': gain.astype(np.float32), 'bias': bias.astype(np.float32),
            'base': base, 'alpha': ja, 'res': res}


# ---------------------------------------------------------------- модель: запись, чтение, отрисовка

def save_model(path, model):
    w = h = SIZE
    uv = np.full((h, w, 2), -1.0, np.float32)
    gain = np.zeros((h, w, 3), np.float32)
    bias = np.zeros((h, w, 3), np.float32)
    ja = np.zeros((h, w), np.uint8)
    ys, xs = model['ys'], model['xs']
    uv[ys, xs, 0], uv[ys, xs, 1] = model['u'], model['v']
    gain[ys, xs], bias[ys, xs], ja[ys, xs] = model['gain'], model['bias'], model['alpha']
    rec = np.zeros((h, w), dtype=[('u', '<f4'), ('v', '<f4'), ('g', '<f4', 3), ('b', '<f4', 3), ('base', 'u1', 4),
                                  ('a', 'u1')])
    rec['u'], rec['v'], rec['g'], rec['b'], rec['base'], rec['a'] = uv[..., 0], uv[..., 1], gain, bias, model['base'], ja
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, 'wb') as f:
        f.write(MAGIC + struct.pack('<II', w, h) + rec.tobytes())


def load_model(path):
    data = open(path, 'rb').read()
    if data[:8] != MAGIC:
        raise SystemExit(f'{path}: не модель позы')
    w, h = struct.unpack_from('<II', data, 8)
    rec = np.frombuffer(data, dtype=[('u', '<f4'), ('v', '<f4'), ('g', '<f4', 3), ('b', '<f4', 3), ('base', 'u1', 4),
                                     ('a', 'u1')], count=w * h, offset=16).reshape(h, w)
    ys, xs = np.nonzero(rec['u'] >= 0)
    return {'w': w, 'h': h, 'ys': ys, 'xs': xs, 'u': rec['u'][ys, xs], 'v': rec['v'][ys, xs],
            'gain': rec['g'][ys, xs], 'bias': rec['b'][ys, xs], 'base': rec['base'].copy(), 'alpha': rec['a'][ys, xs]}


def render(model, tex):
    """tex (H, W, 3|4) — развёртка свитера (512² — как мип 1, на котором модель подогнана) → (256, 256, 4)."""
    t = tex[None, :, :, :3]
    if t.shape[1] != 512:
        from PIL import Image
        t = np.asarray(Image.fromarray(tex[:, :, :3]).resize((512, 512), Image.BOX))[None]
    c = bilinear(t, model['u'], model['v'])[:, 0, :]
    col = np.clip(model['gain'] * c + model['bias'], 0, 255)
    out = model['base'].copy()
    ys, xs = model['ys'], model['xs']
    out[ys, xs, :3] = np.round(col).astype(np.uint8)
    out[ys, xs, 3] = model['alpha']
    return out


# ---------------------------------------------------------------- команды

def opt(args, name, default=None):
    return args[args.index(name) + 1] if name in args else default


def psnr(a, b):
    se = ((a.astype(np.float64) - b.astype(np.float64)) ** 2).mean()
    return 99.0 if se == 0 else 10 * np.log10(255 * 255 / se)


def cmd_fit(args):
    game = opt(args, '--game', gameprofile.default_name())
    out = opt(args, '--out', os.path.join(work_dir(game), 'pose.bin'))
    maxn = int(opt(args, '--max', '0')) or None
    kits, model = fit(game, maxn)
    # клубы, чьё превью не сходится с их свитером (другая сетка, превью от другой версии), — без них ещё раз
    _, prev, t1, _ = load_set(game, maxn, lambda *a: None)
    ys, xs = model['ys'], model['xs']
    rgb = prev[:, ys, xs, :3].astype(np.float32)
    t = bilinear(t1, model['u'], model['v']).transpose(1, 0, 2)
    pred = model['gain'][None] * t + model['bias'][None]
    kres = np.sqrt(((pred - rgb) ** 2).mean(axis=(1, 2)))
    thr = max(12.0, float(np.percentile(kres, 90)) * 1.5)
    keep = np.nonzero(kres <= thr)[0]
    bad = [f'{kits[i][0]}_{kits[i][1]} ({kres[i]:.0f})' for i in np.argsort(-kres)[:8] if kres[i] > thr]
    log(f'остаток по клубам: медиана {np.median(kres):.1f}; не сошлись (> {thr:.0f}): {len(kits) - len(keep)} '
        + (', '.join(bad) if bad else ''))
    if len(keep) < len(kits):
        base = model['base']
        m2 = shade_fit(prev, t1, ys, xs, model['u'], model['v'], base, keep=keep)
        m2['score'] = model['score']
        model = m2
    save_model(out, model)
    log(f'→ {out}')


def cmd_check(args):
    path = args[0]
    game = opt(args, '--game', gameprofile.default_name())
    model = load_model(path)
    want = opt(args, '--kits')
    kits = [tuple(int(x) for x in k.split('_')) for k in want.split(',')] if want else None
    allk = kit_list(game)
    if kits is None:
        kits = allk[::max(1, len(allk) // 12)][:12]
    rows, ps = [], []
    for a, v in kits:
        p = load_preview(preview_rel(a, v), game)
        t = load_texture(texture_rel(a, v), game, levels=(1,))
        if p is None or t is None:
            log(f'{a}_{v}: нет файлов')
            continue
        r = render(model, t[1])
        ys, xs = model['ys'], model['xs']
        q = psnr(p[ys, xs, :3], r[ys, xs, :3])
        ps.append(q)
        log(f'{a}_{v}: PSNR по свитеру {q:.1f} дБ')
        rows.append((f'{a}_{v}', p, r))
    log(f'итого: {len(ps)} комплектов, PSNR медиана {np.median(ps):.1f} дБ')
    sheet = opt(args, '--sheet')
    if sheet:
        from PIL import Image, ImageDraw
        W = SIZE
        im = Image.new('RGB', (W * 3, (W + 16) * len(rows)), (40, 42, 48))
        d = ImageDraw.Draw(im)
        for i, (name, p, r) in enumerate(rows):
            y = i * (W + 16)
            bg = np.zeros((W, W, 3), np.float32) + 90
            for j, img in enumerate((p, r)):
                a = img[:, :, 3:4] / 255.0
                comp = img[:, :, :3] * a + bg * (1 - a)
                im.paste(Image.fromarray(comp.astype(np.uint8)), (j * W, y))
            diff = np.clip(np.abs(p[:, :, :3].astype(int) - r[:, :, :3].astype(int)) * 4, 0, 255).astype(np.uint8)
            im.paste(Image.fromarray(diff), (2 * W, y))
            d.text((4, y + W + 2), f'{name}: EA | модель | разница ×4', fill=(230, 230, 230))
        im.save(sheet)
        log(f'лист: {sheet}')


def cmd_render(args):
    from PIL import Image
    model = load_model(args[0])
    tex = np.asarray(Image.open(args[1]).convert('RGB'))
    out = render(model, tex)
    Image.fromarray(out, 'RGBA').save(args[2])
    log(f'→ {args[2]}')


def cmd_shade(args):
    """Та же карта uv, затенение — по превью другой игры."""
    src, out = args[0], args[1]
    game = opt(args, '--game', gameprofile.default_name())
    model = load_model(src)
    kits, prev, t1, _ = load_set(game, None)
    base = np.median(prev, axis=0).astype(np.uint8)
    m2 = shade_fit(prev, t1, model['ys'], model['xs'], model['u'], model['v'], base)
    save_model(out, m2)
    log(f'→ {out} (карта uv из {src}, затенение — {game}, {len(kits)} комплектов)')


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return
    cmd, rest = args[0], args[1:]
    {'fit': cmd_fit, 'check': cmd_check, 'render': cmd_render, 'shade': cmd_shade}.get(
        cmd, lambda a: sys.exit(__doc__))(rest)


if __name__ == '__main__':
    main()
