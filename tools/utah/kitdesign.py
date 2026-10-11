"""Форма стиля 1 (крой Reebok Edge) NHL Legacy по описанию дизайна — для клуба без исходной текстуры (Utah Mammoth):
свитер (полосы низа и рукавов, ворот, V-вставка), шрифт номеров, шорты, гетры, превью меню; файлы — как у czkit/kitpaint
(контейнер комплекта EA той же длины номера, имена растров → свой номер).

    python tools/utah/kitdesign.py build SPEC.json OUTDIR [--kits home,away] [--work DIR] [--game legacy]
    python tools/utah/kitdesign.py uvmap [--size 1024]          # карта развёртки → 3D (кеш, см. UVMAP_CACHE)

Нужны numpy, scipy, Pillow (venv game/work/utah/venv) и Chrome/Edge без окна (логотипы из SVG — как в kitpaint).

Как рисуется свитер. Развёртка свитера Legacy стиля 1 — «крест»: спина сверху (кромка низа спины — верхний край
текстуры), перёд снизу (кромка низа переда — нижний край), рукава — слева и справа (манжеты — у краёв x = 0 и 1023),
в середине — вырез ворота; в углу 0,08…0,18 × 0,85…0,90 — сетка «рубашки» в V-вырезе (rendering/jersey/shirt_1_1_2).
Сетки Legacy (tools/fb/kit3d.load_legacy, kit_hybrid.legacy_with_shirt) дают по каждому текселю точку на поверхности, и
расстояния считаются по поверхности:
  * hem — от кромки низа (перёд и спина) вдоль столбца развёртки, в сантиметрах: полосы параллельны кромке;
  * sleeve — от манжеты вдоль строки развёртки: прямые полосы поперёк рукава, как рисует EA; сантиметры — средний
    профиль по строкам (у самой манжеты подгиб: первые ~10 текселей — 4…7 см);
  * collar — зоны ворота кроя 4 конструктора (rendering/czjersey/jerseyct_4_0_1_tm: R — кайма ворота, G — ворот
    внутри и V-вставка), vinsert — «рубашка» в вырезе и G-зона. По решению пользователя у всех форм V-вставка — в цвет
    свитера, шнуровки нет (hastie 0).
Поверх — детали кроя 4 (строчка швов, jerseyct_4_0_dm) с силой detail; рельеф и блеск — чистые карты кроя 4
(czkit.clean_jersey_maps: медиана по логотипам конструктора — их же берёт перенос NHL 24, tools/fb/kit_batch.py);
логотипы — kitpaint.apply_logos (цвет, блеск вышивки, рельеф).

SPEC (JSON; примеры — tools/utah/src/UTA-kits.json, TUC-kits.json): colors {имя: "#RRGGBB"}, svg {имя: как в
kitpaint (file, cut, strip_paths, recolor)}, container "1_131_0", name_map "1_23_0" (чья карта мест номера/фамилии/буквы
капитана), font {glyphs {source block|css|svg, …}, texture_kit (чья фактура font_nm), colors {fill, outline [цвет, px],
outline2, letters_outline}} (fontatlas.py), kits {имя: {kit "1_104_0", label,
  jersey {body, hem [[от см, до см, цвет]…], sleeve [[от, до, цвет]…], collar {trim, inner}, vinsert (цвет; по
          умолчанию body), detail 0…1, logos [{svg, center [x, y], size [w, h], rotate} — координаты развёртки 1024² |
          {svg, at3d [x, y, z] м, size_cm [w, h], turn°} — точка на поверхности, верх логотипа — вверх по телу]},
  font {fill, outline, outline2, letters_outline} (поверх общего), pant {design P (czpant), zones [3], detail, logos} |
  {same_as}, sock {base, bands [[от, до, цвет]…] (доли высоты развёртки гетры сверху), shade} }}.
"""
import json
import math
import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
REPO = os.path.dirname(TOOLS)
sys.path.insert(0, TOOLS)
import teamart as ta        # noqa: E402
import kitpaint as kp       # noqa: E402
import czkit                # noqa: E402

UVMAP_CACHE = os.path.join(REPO, 'game', 'work', 'utah', 'cache')
CUT = 4                                         # крой конструктора: швы, ворот, чистые карты рельефа/блеска
COLLAR_TM = 'rendering/czjersey/jerseyct_4_0_1_tm.rx2'
DETAIL_DM = 'rendering/czjersey/jerseyct_4_0_dm.rx2'
SHIRT_BOX = (60, 840, 200, 940)                 # где на развёртке 1024² «рубашка» V-выреза (с запасом)
BODY_X = (250, 775)                             # столбцы корпуса (перёд, спина)
SLEEVE_Y = (300, 740)                           # строки рукавов


# ---------------------------------------------------------------- карта развёртки → поверхность

def uvmap(size=1024, cache=UVMAP_CACHE):
    """{'mask', 'shirt', 'pos', 'nrm'} по текселям развёртки свитера Legacy стиля 1 (+ «рубашка» V-выреза)."""
    path = os.path.join(cache, f'uvmap_{size}.npz')
    if os.path.exists(path):
        d = np.load(path)
        return {k: d[k] for k in d.files}
    from fb import kit3d, kit_hybrid
    m, nj = kit_hybrid.legacy_with_shirt()
    tid, bar = kit3d.raster_uv(m, size)
    mask = tid >= 0
    T = m['tri']
    t, b = tid[mask], bar[mask]
    P = b[:, :1] * m['pos'][T[t, 0]] + b[:, 1:2] * m['pos'][T[t, 1]] + b[:, 2:] * m['pos'][T[t, 2]]
    N = kit3d._unit(b[:, :1] * m['nrm'][T[t, 0]] + b[:, 1:2] * m['nrm'][T[t, 1]] + b[:, 2:] * m['nrm'][T[t, 2]])
    pos = np.full((size, size, 3), np.nan)
    nrm = np.zeros((size, size, 3))
    pos[mask], nrm[mask] = P, N
    shirt = np.zeros((size, size), bool)
    shirt[mask] = t >= nj
    out = {'mask': mask & ~shirt, 'shirt': shirt, 'pos': pos, 'nrm': nrm}
    os.makedirs(cache, exist_ok=True)
    np.savez_compressed(path, **out)
    return out


def _cum_along(pos, ok, axis, reverse):
    """Накопленное расстояние по поверхности (см) вдоль оси развёртки от первого текселя участка ok (кромки)."""
    p = np.moveaxis(pos, axis, 0)
    k = np.moveaxis(ok, axis, 0)
    if reverse:
        p, k = p[::-1], k[::-1]
    n = p.shape[0]
    out = np.full(k.shape, np.nan)
    acc = np.zeros(k.shape[1:])
    started = np.zeros(k.shape[1:], bool)
    prev = p[0]
    for i in range(n):
        cur = p[i]
        here = k[i]
        step = np.linalg.norm(np.nan_to_num(cur - prev), axis=-1) * 100
        acc = np.where(started & here, acc + step, 0.0)
        started = np.where(here, True, started)
        acc = np.where(here, acc, 0.0)
        out[i] = np.where(here, acc, np.nan)
        prev = cur
    if reverse:
        out = out[::-1]
    return np.moveaxis(out, 0, axis)


def distances(um):
    """Поля расстояний (см) на развёртке: hem (от кромки низа, перёд и спина), sleeve (от манжеты, прямые полосы)."""
    mask, pos = um['mask'], um['pos']
    S = mask.shape[0]
    hem = np.full((S, S), np.nan)
    body = np.zeros_like(mask)
    body[:, BODY_X[0]:BODY_X[1] + 1] = True
    front = mask & body
    front[:S // 2] = False
    back = mask & body
    back[S // 2:] = False
    ys = np.arange(S)[:, None]
    # столбцы, где край участка — кромка низа (а не подмышка): перёд — нижний край ниже 960, спина — верхний выше 60
    bot = np.where(front, ys, -1).max(0)
    top = np.where(back, ys, S).min(0)
    front &= (bot > 960)[None, :]
    back &= (top < 60)[None, :]
    hem_f = _cum_along(pos, front, 0, reverse=True)       # от нижнего края вверх
    hem_b = _cum_along(pos, back, 0, reverse=False)       # от верхнего края вниз
    hem = np.where(front, hem_f, np.where(back, hem_b, np.nan))
    # рукава: прямые полосы (столбец = расстояние от манжеты), сантиметры — средний профиль строк
    sleeve = np.full((S, S), np.nan)
    rows = slice(SLEEVE_Y[0], SLEEVE_Y[1])
    for side in ('left', 'right'):
        if side == 'left':
            region = np.zeros_like(mask)
            region[rows, :BODY_X[0]] = True
        else:
            region = np.zeros_like(mask)
            region[rows, BODY_X[1] + 1:] = True
        ok = mask & region
        cum = _cum_along(pos, ok, 1, reverse=(side == 'right'))
        xs = np.arange(S)
        off = np.full((S, S), -1)
        for y in range(*SLEEVE_Y):
            cols = xs[ok[y]]
            if not len(cols):
                continue
            edge = cols.min() if side == 'left' else cols.max()
            if (side == 'left' and edge > 20) or (side == 'right' and edge < S - 21):
                continue                                  # край строки — подмышка, а не манжета
            off[y, cols] = (cols - edge) if side == 'left' else (edge - cols)
        # средний профиль: см на смещение (по строкам, где рукав полностью до этого смещения)
        maxo = int(off.max()) + 1
        prof = np.full(maxo, np.nan)
        for o in range(maxo):
            sel = off == o
            if sel.sum() >= 20:
                prof[o] = np.nanmedian(cum[sel])
        valid = ~np.isnan(prof)
        prof = np.interp(np.arange(maxo), np.nonzero(valid)[0], prof[valid])
        prof = np.maximum.accumulate(prof)
        sel = off >= 0
        sleeve[sel] = prof[off[sel]]
    return {'hem': hem, 'sleeve': sleeve}


# ---------------------------------------------------------------- картинки

def to_img(a):
    a = np.ascontiguousarray(np.clip(a + 0.5, 0, 255).astype(np.uint8))
    return kp.Img(a.shape[1], a.shape[0], a.tobytes())


def from_img(img):
    return np.frombuffer(bytes(img.px), np.uint8).reshape(img.h, img.w, 4).astype(np.float32)


def col(c, palette):
    return np.array(kp.parse_color(c, palette), np.float32)


def band(d, d0, d1, aa):
    """Доля покрытия полосы [d0, d1) по полю расстояний d (см), сглаживание — aa см."""
    with np.errstate(invalid='ignore'):
        c = np.clip((d - d0) / aa + 0.5, 0, 1) * np.clip((d1 - d) / aa + 0.5, 0, 1)
    return np.nan_to_num(c)


def mix(img, color, cov):
    img[..., :3] = img[..., :3] * (1 - cov[..., None]) + color * cov[..., None]


def rx2_layer(rel, name=None):
    rw = ta.Rw4(kp.source(rel), rel)
    t = next(x for x in rw.textures if name is None or name in x.name)
    w, h, px = kp.tex_decode(rw, t, 0)
    return np.frombuffer(bytes(px), np.uint8).reshape(h, w, 4).astype(np.float32)


_CLEAN = None


def clean_maps():
    """Чистые нормали (1024²) и блеск (512²) кроя CUT без логотипа + калибровка рельефа (czkit.clean_jersey_maps;
    копия кеша — в UVMAP_CACHE/clean, чужой кеш только читается)."""
    global _CLEAN
    if _CLEAN is None:
        tag = f'{CUT}_' + '-'.join(map(str, czkit.CLEAN_LOGOS))
        mine = os.path.join(UVMAP_CACHE, 'clean')
        names = [f'{tag}_{k}' for k in ('nm.png', 'sm.png', 'cal.json')]
        if not all(os.path.exists(os.path.join(mine, n)) for n in names):
            os.makedirs(mine, exist_ok=True)
            theirs = ta.GAME.work_dir('art', 'czwork', 'clean')
            if all(os.path.exists(os.path.join(theirs, n)) for n in names):
                import shutil
                for n in names:
                    shutil.copy2(os.path.join(theirs, n), os.path.join(mine, n))
            else:                                       # посчитать в свой кеш (czkit пишет в work_dir игры — подменяем)
                orig = ta.GAME.work_dir
                ta.GAME.work_dir = lambda *parts: mine if parts == ('art', 'czwork', 'clean') else orig(*parts)
                try:
                    czkit.clean_jersey_maps(CUT)
                finally:
                    del ta.GAME.work_dir
        nm = kp.Img.load(os.path.join(mine, names[0]))
        sm = kp.Img.load(os.path.join(mine, names[1]))
        cal = {k: tuple(v) for k, v in json.load(open(os.path.join(mine, names[2]))).items()}
        _CLEAN = (nm, sm, cal)
    nm, sm, cal = _CLEAN
    return nm.copy(), sm.copy(), dict(cal)


# ---------------------------------------------------------------- свитер

def paint_jersey(js, palette, um, dist, log=print):
    S = um['mask'].shape[0]
    body = col(js['body'], palette)
    cm = np.zeros((S, S, 4), np.float32)
    cm[..., :3] = body
    cm[..., 3] = 255
    for d0, d1, c in js.get('hem', ()):
        mix(cm, col(c, palette), band(dist['hem'], d0, d1, 0.18))
    for d0, d1, c in js.get('sleeve', ()):
        mix(cm, col(c, palette), band(dist['sleeve'], d0, d1, 0.15))
    for region in js.get('regions', ()):                     # произвольные зоны: {"mask": "yoke"|…, "color"}
        raise SystemExit(f'зона {region} не поддерживается')
    # ворот: зоны кроя 4 конструктора (R — кайма ворота, G — ворот внутри и V-вставка)
    collar = js.get('collar', {})
    tm1 = rx2_layer(COLLAR_TM) / 255.0
    dm = rx2_layer(DETAIL_DM)
    vee = vee_mask(dm)                                       # клин V-вставки под вырезом (тёмный треугольник dm)
    vcol = col(js.get('vinsert', js['body']), palette)
    if collar.get('trim'):
        mix(cm, col(collar['trim'], palette), tm1[..., 0] * (1 - vee))
    mix(cm, col(collar.get('inner', js.get('vinsert', js['body'])), palette), tm1[..., 1])
    mix(cm, vcol, vee)
    img = to_img(cm)
    if js.get('detail', 0.6) > 0:                           # строчка швов кроя 4 (без «рубашки» в углу и клина V)
        x0, y0, x1, y1 = SHIRT_BOX
        dm[y0:y1, x0:x1, 3] = 0
        dm[..., 3] *= (1 - vee)
        czkit.detail_over(img, to_img(dm), js.get('detail', 0.6))
    cmf = from_img(img)
    # V-вставка: «рубашка» в вырезе ворота — цвет свитера (решение пользователя), с запасом вокруг
    sh = ndi_dilate(um['shirt'], 6)
    x0, y0, x1, y1 = SHIRT_BOX
    box = np.zeros_like(sh)
    box[y0:y1, x0:x1] = True
    mix(cmf, col(js.get('vinsert', js['body']), palette), (sh & box).astype(np.float32))
    return to_img(cmf)


VEE_BOX = (470, 560, 560, 660)                   # где под вырезом ворота клин V-вставки кроя 4


def vee_mask(dm):
    """Клин V-вставки под вырезом ворота: тёмный непрозрачный треугольник деталей кроя 4 (+1 px)."""
    x0, y0, x1, y1 = VEE_BOX
    m = np.zeros(dm.shape[:2], bool)
    sub = dm[y0:y1, x0:x1]
    m[y0:y1, x0:x1] = (sub[..., 3] > 96) & (sub[..., :3].mean(-1) < 90)
    m = ndi_dilate(m, 1)
    return m.astype(np.float32)


def ndi_dilate(m, r):
    from scipy import ndimage as ndi
    return ndi.binary_dilation(m, iterations=r)


def place3d(um, item):
    """Логотип по точке на поверхности: {"at3d": [x, y, z] (м, сетка Legacy: y вверх, +z — грудь), "size_cm": [w, h],
    "turn": доворот°} → центр на развёртке, размер в текселях и поворот, при котором верх логотипа смотрит вверх по
    3D (по градиенту высоты на развёртке)."""
    pos, mask = um['pos'], um['mask']
    t = np.array(item['at3d'], np.float64)
    dd = np.where(mask, np.nansum((pos - t) ** 2, -1), np.inf)
    y, x = np.unravel_index(np.argmin(dd), dd.shape)
    k = 3
    du = np.linalg.norm(pos[y, x + k] - pos[y, x - k]) / (2 * k) * 100      # см на тексель по u
    dv = np.linalg.norm(pos[y + k, x] - pos[y - k, x]) / (2 * k) * 100      # и по v
    gx = (pos[y, x + k, 1] - pos[y, x - k, 1]) / du
    gy = (pos[y + k, x, 1] - pos[y - k, x, 1]) / dv
    ang = math.degrees(math.atan2(gx, -gy)) + item.get('turn', 0.0)
    w, h = item['size_cm']
    # размер рамки в текселях: развёртка не изотропна — берём среднюю плотность (поворот путает оси)
    dens = (du + dv) / 2
    out = {k2: v for k2, v in item.items() if k2 not in ('at3d', 'size_cm', 'turn')}
    out.update(center=[int(x), int(y)], size=[w / dens, h / dens], rotate=round(ang, 1))
    return out


def sleeve_rule(cm, nmap, um, log=print):
    """Полоски рукавов ближе к кисти — то же правило, что у переноса форм NHL 24 (tools/fb/kit_rules.toml [sleeve],
    решение пользователя 11.10): номер на плече (карта номеров формы, зоны 2 и 3) не ложится на полосы. До логотипов:
    они правилом не сдвигаются."""
    from fb import sleeve
    a = from_img(cm)
    zones = {}
    nm = np.frombuffer(bytes(nmap.px), np.uint8).reshape(nmap.h, nmap.w, 4).astype(int)
    for z in sleeve.NUMBER_ZONES:
        ys, xs = np.nonzero((nm[..., 0] > 128) & (nm[..., 1] > 128) & (nm[..., 2] == z))
        if len(xs):
            zones[z] = (xs.min() / nmap.w, ys.min() / nmap.h, (xs.max() + 1) / nmap.w, (ys.max() + 1) / nmap.h)
    new, plan = sleeve.remap(a, zones, um['mask'])
    for z, q in plan.items():
        log(f'  рукав (зона {z}): рисунок ×{q["k"]} к манжете, зазор до номера {q["gap_before"]} → {q["gap_after"]}')
    return to_img(new)


def make_jersey(js, svgs, palette, um, dist, log=print, nmap=None):
    cm = paint_jersey(js, palette, um, dist, log)
    if nmap is not None:
        cm = sleeve_rule(cm, nmap, um, log)
    nm, sm512, cal = clean_maps()
    sm = czkit.resize(sm512, 1024, 1024)
    if 'relief' in js:
        cal['strength'] = float(js['relief'])
    layers = {'cm': cm, 'sm': sm, 'nm': nm}
    if js.get('logos'):
        items = [place3d(um, it) if 'at3d' in it else it for it in js['logos']]
        kp.apply_logos(layers, items, svgs, cal, log)
    return layers, cal


# ---------------------------------------------------------------- гетры

def make_sock(ss, palette, shade=None):
    """Гетры 1024×512: основа и полосы [от, до, цвет] — доли высоты развёртки сверху (у EA полосы — поперёк всей
    ширины); shade — затенение ткани (яркость белой гетры EA / среднее)."""
    W, H = 1024, 512
    a = np.zeros((H, W, 4), np.float32)
    a[..., :3] = col(ss['base'], palette)
    a[..., 3] = 255
    y = (np.arange(H)[:, None] + 0.5) / H * np.ones((1, W))
    for f0, f1, c in ss.get('bands', ()):
        mix(a, col(c, palette), band(y * H, f0 * H, f1 * H, 1.0))
    if shade is not None:
        a[..., :3] = np.clip(a[..., :3] * shade[..., None], 0, 255)
    return to_img(a)


def sock_shade(rel='rendering/sock/sock_1_2_1_cm.rx2', rows=(0, 250)):
    """Затенение ткани гетры: яркость белой части гетры EA (по умолчанию — выездные «Бостона», верх до полос),
    продолжена на всю высоту отражением; среднее — 1."""
    s = rx2_layer(rel)
    L = s[..., :3].mean(-1)
    part = L[rows[0]:rows[1]]
    reps = int(math.ceil(512 / part.shape[0])) + 1
    tile = np.concatenate([part if i % 2 == 0 else part[::-1] for i in range(reps)], 0)[:512]
    return tile / tile.mean()


# ---------------------------------------------------------------- сборка комплектов

def make_font(spec_font, kit_font, base_dir, masks_cache, palette):
    import fontatlas as fa
    src = spec_font['glyphs']
    key = json.dumps(src, sort_keys=True)
    if key not in masks_cache:
        chars = sorted(set(fa.LETTERS + '0123456789'))
        masks_cache[key] = fa.glyph_masks(src, chars, base_dir=base_dir)
    colors = dict(spec_font.get('colors', {}), **kit_font)

    def hx(c):
        r, g, b = kp.parse_color(c, palette)
        return f'#{r:02X}{g:02X}{b:02X}'
    for k in ('fill',):
        colors[k] = hx(colors[k])
    colors['letters_outline'] = bool(colors.get('letters_outline', True))
    for k in ('outline', 'outline2'):
        if colors.get(k):
            colors[k] = [hx(colors[k][0]), float(colors[k][1])]
    tpl = spec_font.get('texture_kit')
    nm_t = None
    if tpl:
        rel = kp.Kit.parse(tpl).path('jersey')
        rw = ta.Rw4(kp.source(rel), rel)
        t = next(x for x in rw.textures if kp.layer_name(x.name) == 'font_nm')
        w, h, px = kp.tex_decode(rw, t, 0)
        nm_t = np.frombuffer(bytes(px), np.uint8).reshape(h, w, 4)
    cm, nm, sm = fa.build_atlas(masks_cache[key], colors, nm_template=nm_t)
    return to_img(cm.astype(np.float32)), to_img(nm.astype(np.float32)), to_img(sm.astype(np.float32))


def name_map(kit_tag):
    rel = kp.Kit.parse(kit_tag).path('name')
    rw = ta.Rw4(kp.source(rel), rel)
    return kp.Img(*kp.tex_decode(rw, rw.textures[0], 0))


def build(spec_path, outdir, only=None, work=None, log=print):
    spec = ta.load_spec(spec_path)
    base = os.path.dirname(os.path.abspath(spec_path))
    palette = spec.get('colors', {})
    svgs = {k: kp.svg_load(v, base) for k, v in spec.get('svg', {}).items()}
    um = uvmap()
    dist = distances(um)
    shade = sock_shade()
    masks_cache = {}
    made, done = [], {}
    for name, ks in spec['kits'].items():
        if only and name not in only:
            continue
        new = kp.Kit.parse(ks['kit'])
        cont = kp.default_container(kp.Kit.parse(ks.get('container', spec.get('container', '1_131_0'))), new)
        log(f'{spec.get("team", "")} {name}: {new} (контейнер {cont})')
        nmap = name_map(ks.get('name_map', spec.get('name_map', '1_22_3')))
        jl, cal = make_jersey(ks['jersey'], svgs, palette, um, dist, log, nmap=nmap)
        fcm, fnm, fsm = make_font(spec['font'], ks.get('font', {}), base, masks_cache, palette)
        ps = ks['pant']
        if 'same_as' in ps:
            pl = done[ps['same_as']]['pant']
        else:
            pl = czkit.make_pant(ps, svgs, palette, cal, log)
        scm = make_sock(ks['sock'], palette, shade if ks['sock'].get('shade', True) else None)
        fe = czkit.make_fe(jl['cm'], jl['nm'], ks, log)
        layers = {'jersey_cm': jl['cm'], 'jersey_sm': jl['sm'], 'jersey_nm': jl['nm'],
                  'font_cm': fcm, 'font_nm': fnm, 'font_sm': fsm, 'name_cm': nmap,
                  'pant_cm': pl['cm'], 'pant_nm': pl['nm'], 'pant_sm': pl['sm'], 'sock_cm': scm, 'fe': fe}
        done[name] = {'pant': pl}
        if work:
            d = os.path.join(work, f'{spec.get("team", "kit")}_{name}')
            os.makedirs(d, exist_ok=True)
            for ln, img in layers.items():
                img.save(os.path.join(d, ln + '.png'))
        res = kp.build_kit(cont, new, {k: v.tup() for k, v in layers.items()}, outdir, log=log)
        made += list(res)
    return made


def main():
    game, argv = ta.split_game(sys.argv[1:])
    ta.set_game(game)
    if not argv:
        sys.exit(__doc__)
    cmd, args = argv[0], argv[1:]
    if cmd == 'uvmap':
        size = int(args[args.index('--size') + 1]) if '--size' in args else 1024
        um = uvmap(size)
        print(f'развёртка {size}²: текселей свитера {int(um["mask"].sum())}, «рубашки» {int(um["shirt"].sum())}')
    elif cmd == 'build':
        only = args[args.index('--kits') + 1].split(',') if '--kits' in args else None
        work = args[args.index('--work') + 1] if '--work' in args else None
        made = build(args[0], args[1], only, work)
        print(f'файлов: {len(made)}')
    else:
        sys.exit(__doc__)


if __name__ == '__main__':
    main()
