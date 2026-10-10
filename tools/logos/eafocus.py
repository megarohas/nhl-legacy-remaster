"""Кадр EA по клубам: где у EA в наборах-«крупных планах» (s — «таблетка», c — календарь, w — широкий, tw — значок ленты
новостей, pb — фон карточки игрока) стоит логотип относительно полного логотипа t того же клуба.

У каждого клуба EA выбирала свой фрагмент (у «Рейнджерс» в «таблетке» — надпись RANGERS, у «Бостона» в w — буква B).
Чтобы новый логотип того же рисунка лёг так же, для каждого набора ищется подобие (масштаб и сдвиг, без поворота),
которое переводит t<art> EA в картинку набора: перебор масштаба, сдвиг — взаимная корреляция полей градиента яркости
(FFT). Результат — в долях рамки логотипа t (alpha > 128): точка рамки, которая у EA в центре кадра набора, и размер
рамки в пикселях набора. Сборка (tools/logos/build.py) переносит эти доли на рамку нового логотипа.

    venv/python tools/logos/eafocus.py OUT.json [ART…] [--sets s,c,w,tw,pb] [--sheet DIR] [--game legacy]

ART — номера арта EA (по умолчанию 0…29). Нужны numpy, scipy, Pillow (venv game/work/logos/venv)."""
import json
import os
import sys

import numpy as np
from PIL import Image
from scipy import ndimage as ndi
from scipy.signal import fftconvolve

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import teamart as ta  # noqa: E402

# набор: путь в архиве, центр кадра (x, y) в пикселях картинки, область поиска (x0, y0, x1, y1) — где у EA рисунок
SCALES = {'s': (0.3, 2.6), 'c': (0.3, 2.2), 'w': (0.7, 4.5), 'tw': (0.2, 1.8), 'pb': (0.8, 4.5)}
SETS = {
    's': ('fe/ion/artassets/teamlogossmall/s{}.big', (64.0, 32.0), (10, 12, 118, 52)),
    'c': ('fe/ion/artassets/teamlogoscalendar/c{}.big', (49.0, 43.0), (4, 4, 94, 82)),
    'w': ('fe/ion/artassets/teamlogoswide/w{}.big', (128.0, 128.0), (16, 16, 240, 240)),
    'tw': ('fe/ion/artassets/twittericonsteam/t{}.big', None, None),       # окно значка — по маске (ниже)
    'pb': ('fe/ion/artassets/playerbackgrounds/pb_{}.big', None, None),     # водяной знак — по разнице с медианой
}


def ea(rel):
    u = ta.UiLogo.load(ta.extracted(rel))
    w, h, px = u.decode()
    sw, sh = u.stage
    a = np.frombuffer(bytes(px), np.uint8).reshape(h, w, 4).astype(np.float32)
    return a[:sh, :sw]


def lum_over(img, bg=128.0):
    a = img[..., 3:4] / 255.0
    rgb = img[..., :3] * a + bg * (1 - a)
    return rgb @ np.array([0.299, 0.587, 0.114], np.float32)


def grad(l):
    gx = ndi.sobel(l, 1)
    gy = ndi.sobel(l, 0)
    return gx, gy


def t_frame(t):
    """Рамка логотипа t (alpha > 128): x0, y0, w, h."""
    ys, xs = np.nonzero(t[..., 3] > 128)
    return float(xs.min()), float(ys.min()), float(xs.max() - xs.min() + 1), float(ys.max() - ys.min() + 1)


def match(t, img, region, weight=None, scales=None):
    """Подобие t → img: (масштаб, сдвиг x, сдвиг y, качество). region — где искать в img (x0, y0, x1, y1)."""
    x0, y0, x1, y1 = region
    crop = img[y0:y1, x0:x1]
    cgx, cgy = grad(lum_over(crop))
    if weight is not None:
        wgt = weight[y0:y1, x0:x1]
        cgx, cgy = cgx * wgt, cgy * wgt
    cn = np.sqrt((cgx ** 2 + cgy ** 2).sum()) + 1e-6
    tl = lum_over(t)
    best = None
    scales = scales if scales is not None else np.geomspace(0.25, 4.5, 90)
    for s in scales:
        size = max(8, int(round(t.shape[0] * s)))
        ts = np.asarray(Image.fromarray(np.clip(tl, 0, 255).astype(np.uint8)).resize((size, size), Image.BILINEAR)).astype(np.float32)
        tgx, tgy = grad(ts)
        # корреляция: поле t (большое, с полями нулей) и поле кадра (ядро)
        ph, pw = crop.shape[0], crop.shape[1]
        big_x = np.pad(tgx, ((ph, ph), (pw, pw)))
        big_y = np.pad(tgy, ((ph, ph), (pw, pw)))
        num = fftconvolve(big_x, cgx[::-1, ::-1], 'valid') + fftconvolve(big_y, cgy[::-1, ::-1], 'valid')
        ker = np.ones_like(cgx) if weight is None else (wgt > 0).astype(np.float32)
        en = fftconvolve(big_x ** 2 + big_y ** 2, ker[::-1, ::-1], 'valid')
        sc = num / (np.sqrt(np.maximum(en, 1e-6)) * cn)
        sc[en < 0.05 * en.max()] = -1.0          # там, где под кадром почти пусто (поля) — шум FFT
        k = np.unravel_index(np.argmax(sc), sc.shape)
        q = float(sc[k])
        if best is None or q > best[3]:
            # положение: crop[y, x] ~ ts[y + oy, x + ox], oy = k0 - ph, ox = k1 - pw → t-пиксель (u, v) → img (u*s - ox + x0, …)
            oy, ox = k[0] - ph, k[1] - pw
            best = (float(s), float(x0 - ox), float(y0 - oy), q)
    return best


def refine(t, img, region, weight, s0):
    return match(t, img, region, weight, np.geomspace(s0 / 1.04, s0 * 1.04, 9))


def tw_window(img_ref, img_other):
    """Окно логотипа у значка ленты новостей: там, где значки разных клубов различаются (рамка и «облачко» общие)."""
    same = np.abs(img_ref - img_other).sum(-1) < 6
    diff = ndi.binary_closing(~same & (img_ref[..., 3] > 200), iterations=2)
    win = ndi.binary_fill_holes(diff)
    return ndi.binary_opening(win, iterations=1), same


_PREP = {}


def prep():
    """Общее для всех клубов: окно значка ленты (рамка и вес) и медиана фонов карточки игрока (pb без логотипа)."""
    if not _PREP:
        tw_ref = ea(SETS['tw'][0].format(22))
        tw_other = ea(SETS['tw'][0].format(131))
        win, same = tw_window(tw_ref, tw_other)
        ys, xs = np.nonzero(win)
        _PREP['tw_region'] = (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)
        _PREP['tw_weight'] = (win & ~same).astype(np.float32)
        _PREP['tw_win'] = win
        _PREP['tw_same'] = same
        _PREP['pb_med'] = np.median(np.stack([ea(SETS['pb'][0].format(n)) for n in range(12)]), 0)
    return _PREP


def set_image(kind, art):
    """Картинка набора EA клуба art для сопоставления → (img, область поиска, вес или None, центр кадра)."""
    rel, center, region = SETS[kind]
    img = ea(rel.format(art))
    weight = None
    P = prep()
    if kind == 'tw':
        region, weight = P['tw_region'], P['tw_weight']
        center = ((region[0] + region[2]) / 2, (region[1] + region[3]) / 2)
    if kind == 'pb':
        med = P['pb_med']
        d = np.abs(img[..., :3] - med[..., :3]).sum(-1)
        m = ndi.gaussian_filter((d > 18).astype(np.float32), 2) > 0.2
        ys2, xs2 = np.nonzero(m)
        region = (int(xs2.min()), int(ys2.min()), int(xs2.max()) + 1, int(ys2.max()) + 1)
        diff = np.zeros_like(img)                  # водяной знак без фона: разница с медианой
        diff[..., :3] = np.clip(128 + (img[..., :3] - med[..., :3]) * 2, 0, 255)
        diff[..., 3] = 255
        img = diff
        center = ((region[0] + region[2]) / 2, (region[1] + region[3]) / 2)
    return img, region, weight, center


def register(t, art, kinds=('s', 'c', 'w', 'tw', 'pb')):
    """Подобие картинки t (256×256 RGBA: логотип целиком) → наборы EA клуба art: {набор: dict(scale, tx, ty, q,
    center)}; пиксель t (u, v) → (u * scale + tx, v * scale + ty) в картинке набора."""
    res = {}
    for kind in kinds:
        img, region, weight, center = set_image(kind, art)
        lo, hi = SCALES[kind]
        s, tx, ty, q = match(t, img, region, weight, np.geomspace(lo, hi, 64))
        s, tx, ty, q = refine(t, img, region, weight, s)
        res[kind] = dict(scale=s, tx=tx, ty=ty, q=q, center=center, region=region)
    return res


def overlay(t, img, r, path):
    """Лист проверки: картинка набора и контур t по найденному подобию (пурпурный)."""
    H, W = img.shape[:2]
    size = int(round(t.shape[0] * r['scale']))
    tt = Image.fromarray(np.clip(t, 0, 255).astype(np.uint8), 'RGBA').resize((size, size), Image.BILINEAR)
    lay = Image.new('RGBA', (W, H))
    lay.paste(tt, (int(round(r['tx'])), int(round(r['ty']))), tt)
    al = np.asarray(lay)[..., 3] > 128
    ed = ndi.binary_dilation(al) ^ al
    base = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8), 'RGBA')
    bg = Image.new('RGBA', base.size, (90, 90, 90, 255))
    bg.alpha_composite(base)
    arr = np.asarray(bg).copy()
    arr[ed] = (255, 0, 255, 255)
    Image.fromarray(arr).save(path)


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    game, argv = ta.split_game(sys.argv[1:])
    ta.set_game(game if game != 'nhl13' else 'legacy')
    sets = ['s', 'c', 'w', 'tw', 'pb']
    sheet = None
    if '--sets' in argv:
        i = argv.index('--sets'); sets = argv[i + 1].split(','); del argv[i:i + 2]
    if '--sheet' in argv:
        i = argv.index('--sheet'); sheet = argv[i + 1]; del argv[i:i + 2]
    out = argv[0]
    arts = [int(a) for a in argv[1:]] or list(range(30))
    res = json.load(open(out, encoding='utf-8')) if os.path.exists(out) else {}
    for art in arts:
        t = ea(f'fe/ion/artassets/teamlogos/t{art}.big')
        fx, fy, fw, fh = t_frame(t)
        rec = res.get(str(art), {})
        rec['t_frame'] = [fx, fy, fw, fh]
        for kind, r in register(t, art, sets).items():
            s, tx, ty, q = r['scale'], r['tx'], r['ty'], r['q']
            cx, cy = r['center']
            u, v = (cx - tx) / s, (cy - ty) / s
            rec[kind] = dict(scale=round(s, 4), tx=round(tx, 2), ty=round(ty, 2), q=round(q, 3),
                             center=[round(cx, 2), round(cy, 2)],
                             focus=[round((u - fx) / fw, 4), round((v - fy) / fh, 4)],
                             frame_px=[round(fw * s, 2), round(fh * s, 2)], region=list(r['region']))
            print(f'art {art:3d} {kind:2s}: масштаб {s:.3f}, фокус {rec[kind]["focus"]}, рамка {rec[kind]["frame_px"]}, '
                  f'качество {q:.3f}', flush=True)
            if sheet:
                os.makedirs(sheet, exist_ok=True)
                overlay(t, set_image(kind, art)[0], r, os.path.join(sheet, f'{kind}_{art:03d}.png'))
        res[str(art)] = rec
        json.dump(res, open(out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)


if __name__ == '__main__':
    main()
