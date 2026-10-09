"""Мелкий арт интерфейса клуба сверх набора teamart (t/s/d/c/w/r): фон карточки игрока (playerbackgrounds/pb_N),
значок ленты новостей (twittericonsteam/tN), цифры шрифтом клуба для меню (teamnumbers/tnN_D, teamnumbersflat/tnfN_D),
картинка левой панели меню (playermenubackgrounds/N_0, N_1 — у EA у всех клубов одна и та же, копия). Контейнеры —
файлы EA того же набора (шаблон — клуб TEMPLATE), пиксели — свои.

    python tools/utah/ui_extra.py SPEC.json OUTDIR [--nums 104,22] [--only pb,tw,tn,menu] [--preview DIR] [--game legacy]

SPEC — как у teamart (svg, strip_paths) + "ui_extra": {"tw_bg": "#0B0B0D", "tw_focus": [x, y, zoom],
"pb_tint": "#A9D3F5", "pb_alpha": 0.32, "pb_box": [cx, cy, w, h], "digits": {glyphs …} (как font.glyphs у kitdesign)}.
--nums — номера, под которыми класть (например, арт клуба и прежний номер слота, если игра берёт эти наборы по номеру
команды, а не по арту: так закрыты оба случая).
"""
import os
import shutil
import sys
import tempfile

import numpy as np
from PIL import Image, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
sys.path.insert(0, TOOLS)
sys.path.insert(0, HERE)
import teamart as ta        # noqa: E402
import kitpaint as kp       # noqa: E402
import playerhead as ph     # noqa: E402

TEMPLATE = 22                                       # контейнеры наборов — файлы EA этого клуба
PB_SOURCES = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]  # фон без логотипа — медиана фонов этих клубов


def ea_ui(rel):
    return ta.UiLogo(kp._unchunk(open(ta.GAME.extracted(rel), 'rb').read()), rel)


def decode(u):
    w, h, px = u.decode()
    return np.frombuffer(bytes(px), np.uint8).reshape(h, w, 4).astype(np.float32)


def render_logo_rgba(spec, w, h, cx, cy, bw, bh, extra=''):
    """Логотип SVG (по рамке рисунка) вписан в bw×bh с центром (cx, cy) на прозрачном w×h."""
    l, t, ww, hh = ta._place(spec, bw, bh, cx, cy)
    tmp = tempfile.mkdtemp(prefix='ui_extra_')
    try:
        png = os.path.join(tmp, 'l.png')
        ta.render_html(ta.page(w, h, ta.logo_layers(spec['_uri'], l, t, ww, hh, extra=extra)), png, w, h)
        _, _, px = ph.png_read(png)
        return np.frombuffer(bytes(px), np.uint8).reshape(h, w, 4).astype(np.float32)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def over(dst, src):
    a = src[..., 3:4] / 255.0
    out = dst.copy()
    out[..., :3] = dst[..., :3] * (1 - a) + src[..., :3] * a
    out[..., 3] = np.maximum(dst[..., 3], src[..., 3])
    return out


def write(u, rgba, outdir, rel):
    data = u.build(np.clip(rgba + 0.5, 0, 255).astype(np.uint8).tobytes(), 'md5')
    p = os.path.join(outdir, *rel.split('/'))
    os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, 'wb').write(data)
    print(f'{rel}: {len(data)} байт')
    return p


def hexf(c):
    c = c.lstrip('#')
    return np.array([int(c[i:i + 2], 16) for i in (0, 2, 4)], np.float32)


# ---------------------------------------------------------------- фон карточки игрока

def make_pb(spec, ex):
    u = ea_ui(f'fe/ion/artassets/playerbackgrounds/pb_{TEMPLATE}.big')
    imgs = [decode(ea_ui(f'fe/ion/artassets/playerbackgrounds/pb_{n}.big')) for n in PB_SOURCES]
    base = np.median(np.stack(imgs), 0)                       # сцена без логотипа клуба
    H, W = base.shape[:2]
    cx, cy, bw, bh = ex.get('pb_box', [560, 230, 470, 330])
    logo = render_logo_rgba(spec, W, H, cx, cy, bw, bh)
    a = logo[..., 3] / 255.0
    lum = logo[..., :3].mean(-1) / 255.0
    tint = hexf(ex.get('pb_tint', '#A9D3F5'))
    k = ex.get('pb_alpha', 0.30) * a * (0.55 + 0.45 * lum)      # светлые части логотипа ярче (как водяной знак EA)
    glow = np.asarray(Image.fromarray((a * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(10))) / 255.0
    out = base.copy()
    out[..., :3] = out[..., :3] + (tint - out[..., :3]) * k[..., None] + 18 * glow[..., None]
    out[..., :3] = np.clip(out[..., :3], 0, 255)
    return u, out


# ---------------------------------------------------------------- значок ленты новостей

def make_tw(spec, ex):
    u = ea_ui(f'fe/ion/artassets/twittericonsteam/t{TEMPLATE}.big')
    a = decode(u)
    b = decode(ea_ui('fe/ion/artassets/twittericonsteam/t131.big'))
    same = (np.abs(a - b).sum(-1) < 6)                          # рамка, «облачко», фон — общие у всех значков
    H, W = a.shape[:2]
    # окно логотипа — внутренний скруглённый квадрат: там, где у значков различие, + дырки внутри
    from scipy import ndimage as ndi
    diff = ndi.binary_closing(~same & (a[..., 3] > 200), iterations=2)
    win = ndi.binary_fill_holes(diff)
    win = ndi.binary_opening(win, iterations=1)
    bg = hexf(ex.get('tw_bg', '#0B0B0D'))
    zx, zy, zk = ex.get('tw_focus', [0.55, 0.45, 1.25])
    ys, xs = np.nonzero(win)
    x0, x1, y0, y1 = xs.min(), xs.max() + 1, ys.min(), ys.max() + 1
    vx, vy, vw, vh = spec['viewbox']
    bx, by, bw, bh = spec['box']
    k = (x1 - x0) * zk / max(bw, bh)
    cx = (x0 + x1) / 2 + (0.5 - zx) * bw * k
    cy = (y0 + y1) / 2 + (0.5 - zy) * bh * k
    logo = render_logo_rgba(spec, W, H, cx, cy, bw * k, bh * k)
    inner = np.zeros_like(a)
    inner[..., :3] = bg
    inner[..., 3] = 255
    inner = over(inner, logo)
    # блик сверху, как у EA (светлее к верху окна)
    yy = (np.arange(H)[:, None] - y0) / max(1, (y1 - y0))
    inner[..., :3] = np.clip(inner[..., :3] * (1.0 + 0.10 * (0.5 - yy)), 0, 255)
    out = a.copy()
    m = win & ~same
    soft = ndi.gaussian_filter(m.astype(np.float32), 0.6)
    soft = np.where(same, 0, np.clip(soft * 1.4, 0, 1))
    out[..., :3] = out[..., :3] * (1 - soft[..., None]) + inner[..., :3] * soft[..., None]
    return u, out


# ---------------------------------------------------------------- цифры клуба для меню

def make_digits(spec, ex, flat):
    import fontatlas as fa
    g = ex['digits']
    masks = fa.glyph_masks(g, list('0123456789'), height=256, base_dir=spec['_base'])
    res = {}
    for d in '0123456789':
        u = ea_ui(f'fe/ion/artassets/{"teamnumbersflat/tnf" if flat else "teamnumbers/tn"}{TEMPLATE}_{d}.big')
        ref = decode(u)
        H, W = ref.shape[:2]
        sw, sh = u.stage
        ys, xs = np.nonzero(ref[:sh, :sw, 3] > 128)               # рамка цифры EA в сцене
        x0, x1, y0, y1 = xs.min(), xs.max() + 1, ys.min(), ys.max() + 1
        m = masks[d]
        hh = y1 - y0
        ww = int(round(m.shape[1] * hh / m.shape[0]))
        ww = min(ww, sw - 4)
        mm = np.asarray(Image.fromarray((m * 255).astype(np.uint8)).resize((ww, hh), Image.LANCZOS)) / 255.0
        out = np.zeros_like(ref)
        out[..., :3] = 236
        cx = (x0 + x1) / 2
        ox = int(round(cx - ww / 2))
        out[y0:y1, ox:ox + ww, 3] = mm * 255
        if not flat:                                             # объёмные: лёгкая тень к низу, как у EA
            yy = (np.arange(H)[:, None] - y0) / max(1, hh)
            out[..., :3] = np.clip(240 - 26 * yy, 180, 255)[..., None] * np.ones((1, 1, 3))
        res[d] = (u, out)
    return res


# ---------------------------------------------------------------- сборка

def main():
    game, argv = ta.split_game(sys.argv[1:])
    ta.set_game(game)
    if len(argv) < 2:
        sys.exit(__doc__)
    spec_path, outdir = argv[0], argv[1]
    nums = [int(x) for x in argv[argv.index('--nums') + 1].split(',')] if '--nums' in argv else None
    only = argv[argv.index('--only') + 1].split(',') if '--only' in argv else ['pb', 'tw', 'tn', 'menu']
    preview = argv[argv.index('--preview') + 1] if '--preview' in argv else None
    spec = ta.load_spec(spec_path)
    base = os.path.dirname(os.path.abspath(spec_path))
    spec['_base'] = base
    svg = ta.svg_text(os.path.join(base, spec['svg']), tuple(spec.get('strip_paths', ())))
    spec['viewbox'] = ta._svg_viewbox(svg)
    spec['_uri'] = ta.data_uri(svg)
    tmp = tempfile.mkdtemp(prefix='ui_extra_m_')
    try:
        spec['box'] = spec.get('box') or ta.measure_box(spec['_uri'], spec['viewbox'], tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    ex = spec.get('ui_extra', {})
    nums = nums or [int(spec['artid'])]
    made = []

    def put(u, rgba, rel):
        p = write(u, rgba, outdir, rel)
        made.append(p)
        if preview:
            os.makedirs(preview, exist_ok=True)
            sw, sh = u.stage
            Image.fromarray(np.clip(rgba[:sh, :sw] + 0.5, 0, 255).astype(np.uint8)).save(
                os.path.join(preview, rel.rsplit('/', 1)[1].replace('.big', '.png')))
    if 'pb' in only:
        u, img = make_pb(spec, ex)
        for n in nums:
            put(u, img, f'fe/ion/artassets/playerbackgrounds/pb_{n}.big')
    if 'tw' in only:
        u, img = make_tw(spec, ex)
        for n in nums:
            put(u, img, f'fe/ion/artassets/twittericonsteam/t{n}.big')
    if 'tn' in only and ex.get('digits'):
        for flat in (False, True):
            for d, (u, img) in make_digits(spec, ex, flat).items():
                for n in nums:
                    put(u, img, f'fe/ion/artassets/{"teamnumbersflat/tnf" if flat else "teamnumbers/tn"}{n}_{d}.big')
    if 'menu' in only:                               # у EA у всех клубов одна картинка (кубок) — копия под свой номер
        for k in (0, 1):
            src = ta.GAME.extracted(f'fe/ion/artassets/playermenubackgrounds/{TEMPLATE}_{k}.big')
            for n in nums:
                rel = f'fe/ion/artassets/playermenubackgrounds/{n}_{k}.big'
                if n == TEMPLATE:
                    continue
                p = os.path.join(outdir, *rel.split('/'))
                os.makedirs(os.path.dirname(p), exist_ok=True)
                shutil.copyfile(src, p)
                made.append(p)
                print(f'{rel}: копия {TEMPLATE}_{k}')
    print(f'файлов: {len(made)}')


if __name__ == '__main__':
    main()
