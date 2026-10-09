"""Атлас шрифта номеров и фамилий (font_*_cm 512², раскладка EA) из своего шрифта — для формы без исходного атласа.

Раскладка EA (замер 118 атласов клубов НХЛ Legacy, медианы рамок глифов — standard_layout()): буквы A–O и P–Z —
две строки в полосе y 0…98 (ячейки по 32 px, M и W — по две), большие цифры — две строки 0–4 и 5–9 (ячейки 80 px,
y 116…237 и 243…365), справа — C и A (x 410…512), внизу — две строки малых цифр (ячейки 48 px: y 372…445 и 451…511).
Игра берёт глифы по местам ячеек, поэтому свои глифы ставятся по центрам рамок EA той же высоты, шириной не больше
ячейки (font_cells в czkit находит их так же, как у EA).

Слои (как у EA): font_cm — DXT5: заливка, обводки, альфа — форма глифа, под прозрачным — цвет края; font_sm —
серый блеск ткани, альфа 0/255; font_nm — нормали: рельеф краёв заливки и обводок + фактура ткани (из font_nm
шаблона EA, по внутренности глифов).

Глифы — векторные контуры: SVG (path на каждый символ, viewBox — высота прописной) или системный шрифт (Chrome
рисует текст). Источник задаётся в SPEC шрифта:
  {"source": "svg", "file": "glyphs.svg"}            # <path id="g-5" d="…"/>…, один viewBox
  {"source": "css", "family": "Bahnschrift", "weight": 700, "stretch": 75}
  {"source": "block", "slant": 10, "weight": 1.0, "round": 1.0}   # свой квадратный шрифт (blockfont.py)
и цвета: {"fill": "#FFFFFF", "outline": ["#6CACE4", 3.0], "outline2": ["#010101", 2.0], "letters_outline": true}
(толщина — px атласа 512 на большие цифры; у букв и малых цифр — пропорционально высоте; letters_outline false — буквы
фамилии без обводки).
"""
import json
import math
import os
import shutil
import sys
import tempfile

import numpy as np
from PIL import Image
from scipy import ndimage as ndi

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
sys.path.insert(0, TOOLS)
import teamart as ta        # noqa: E402
import playerhead as ph     # noqa: E402

LETTERS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
# медианы рамок EA (x0, y0, x1, y1), атлас 512² — tools/utah/src/font_layout_ea.json (tools/utah/font_layout.py)
LAYOUT = None
LAYOUT_JSON = os.path.join(HERE, 'src', 'font_layout_ea.json')


def standard_layout(path=LAYOUT_JSON):
    global LAYOUT
    if LAYOUT is None:
        LAYOUT = {k: tuple(v) for k, v in json.load(open(path, encoding='utf-8'))['boxes'].items()}
    return LAYOUT


def slots():
    """[(ключ, символ, рамка EA, ширина ячейки, часть)] — все места атласа."""
    L = standard_layout()
    out = []
    for ch in LETTERS:
        cw = 64 if ch in 'MW' else 32
        out.append((ch, ch, L[ch], cw, 'letters'))
    for d in '0123456789':
        out.append(('big' + d, d, L['big' + d], 80, 'big'))
    for d in '0123456789':
        out.append(('sm' + d, d, L['sm' + d], 48, 'small'))
        out.append(('sm2_' + d, d, L['sm2_' + d], 48, 'small'))
    out.append(('CA_C', 'C', L['CA_C'], 96, 'big'))
    out.append(('CA_A', 'A', L['CA_A'], 96, 'big'))
    return out


# ---------------------------------------------------------------- глифы → маски (Chrome)

def glyph_masks(src, chars, height=256, pad=64, base_dir='.'):
    """{символ: маска float32 (h, w) 0..1} — глиф в своей рамке (обрезан по альфе), высота прописной ≈ height."""
    if src['source'] == 'block':                       # свой «квадратный» шрифт (blockfont.py) — без Chrome
        import blockfont
        return blockfont.masks(chars, height, slant=src.get('slant', 10.0), weight=src.get('weight', 1.0),
                               round_px=src.get('round', 1.5))
    tmp = tempfile.mkdtemp(prefix='fontatlas_')
    try:
        out = {}
        for ch in chars:
            W = H = height + 2 * pad
            if src['source'] == 'svg':
                import re
                text = open(os.path.join(base_dir, src['file']), encoding='utf-8').read()
                vb = [float(v) for v in re.search(r'viewBox="([^"]+)"', text).group(1).replace(',', ' ').split()]
                m = re.search(r'<path[^>]*id="g-%s"[^>]*d="([^"]+)"' % re.escape(ch), text) or \
                    re.search(r'<path[^>]*d="([^"]+)"[^>]*id="g-%s"' % re.escape(ch), text)
                if not m:
                    raise SystemExit(f'{src["file"]}: нет глифа g-{ch}')
                k = height / vb[3]
                body = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}">'
                        f'<g transform="translate({pad},{pad}) scale({k}) translate({-vb[0]},{-vb[1]})">'
                        f'<path d="{m.group(1)}" fill="#fff"/></g></svg>')
                html = ta.page(W, H, f'<div class="a" style="left:0;top:0">{body}</div>')
            else:
                fam, wt = src['family'], src.get('weight', 700)
                st = src.get('stretch', 100)
                size = height / src.get('cap', 0.7)
                html = ta.page(W, H, f'<div class="a" style="left:{pad}px;top:{pad - size * src.get("top", 0.17):.1f}px;'
                                     f"font-family:'{fam}';font-weight:{wt};font-stretch:{st}%;font-size:{size:.1f}px;"
                                     f'line-height:1;color:#fff;white-space:pre">{ch}</div>')
            png = os.path.join(tmp, 'g.png')
            ta.render_html(html, png, W, H)
            w, h, px = ph.png_read(png)
            a = np.frombuffer(bytes(px), np.uint8).reshape(h, w, 4)[..., 3].astype(np.float32) / 255
            ys, xs = np.nonzero(a > 0.02)
            out[ch] = a[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
        return out
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------- атлас

def _hex(c):
    c = c.lstrip('#')
    return np.array([int(c[i:i + 2], 16) for i in (0, 2, 4)], np.float32)


def _resize(mask, w, h):
    im = Image.fromarray(np.clip(mask * 255, 0, 255).astype(np.uint8))
    return np.asarray(im.resize((max(1, w), max(1, h)), Image.LANCZOS)).astype(np.float32) / 255


def build_atlas(masks, colors, nm_template=None, sm_value=38):
    """→ (font_cm RGBA uint8 512², font_nm, font_sm). colors: fill, outline [цвет, px], outline2 [цвет, px] —
    обводки снаружи глифа в пределах рамки EA (глиф уменьшается на их толщину, рамка — как у EA)."""
    S = 512
    cm = np.zeros((S, S, 4), np.float32)
    height_map = np.zeros((S, S), np.float32)        # 0 — фон, 1 — обводка 2, 2 — обводка, 3 — заливка (для рельефа)
    fill = _hex(colors['fill'])
    o1 = colors.get('outline')
    o2 = colors.get('outline2')
    for key, ch, box, cw, part in slots():
        x0, y0, x1, y1 = box
        bh = y1 - y0
        scale_px = bh / 121.0                         # толщины обводок заданы для больших цифр (высота 121)
        t1 = (o1[1] * scale_px) if o1 else 0.0
        t2 = (o2[1] * scale_px) if o2 else 0.0
        if part == 'letters' and not colors.get('letters_outline', True):   # фамилия — без обводки (Utah Mammoth)
            t1 = t2 = 0.0
        inner_h = max(4, int(round(bh - 2 * (t1 + t2))))
        g = masks[ch]
        gh, gw = g.shape
        w = int(round(gw * inner_h / gh))
        maxw = cw - 2 - int(math.ceil(2 * (t1 + t2)))
        if w > maxw:                                  # шире ячейки — ужать по ширине (как узкие шрифты EA)
            w = maxw
        gm = _resize(g, w, inner_h)
        cx = (x0 + x1) / 2.0
        cy = (y0 + y1) / 2.0
        gx0 = int(round(cx - w / 2.0))
        gy0 = int(round(cy - inner_h / 2.0))
        # слой глифа и обводки (дистанция снаружи)
        pad = int(math.ceil(t1 + t2)) + 3
        canvas = np.zeros((inner_h + 2 * pad, w + 2 * pad), np.float32)
        canvas[pad:pad + inner_h, pad:pad + w] = gm
        inside = canvas > 0.5
        dist_out = ndi.distance_transform_edt(~inside)            # px снаружи до глифа
        a_fill = canvas
        a_o1 = np.clip(t1 + 0.5 - dist_out, 0, 1) if t1 else np.zeros_like(canvas)
        a_o2 = np.clip(t1 + t2 + 0.5 - dist_out, 0, 1) if t2 else np.zeros_like(canvas)
        alpha = a_o2 if t2 else a_o1 if t1 else a_fill
        col = np.zeros(canvas.shape + (3,), np.float32)
        col[:] = _hex(o2[0]) if t2 else _hex(o1[0]) if t1 else fill
        if t1 and t2:
            col = col * (1 - a_o1[..., None]) + _hex(o1[0]) * a_o1[..., None]
        col = col * (1 - a_fill[..., None]) + fill * a_fill[..., None]
        hm = np.maximum.reduce([a_o2 * 1.0, a_o1 * 2.0, a_fill * 3.0]) if (t1 or t2) else a_fill * 3.0
        # в атлас
        ax0, ay0 = gx0 - pad, gy0 - pad
        ys, xs = slice(max(0, ay0), min(S, ay0 + canvas.shape[0])), slice(max(0, ax0), min(S, ax0 + canvas.shape[1]))
        cy0, cx0 = ys.start - ay0, xs.start - ax0
        sub = (slice(cy0, cy0 + ys.stop - ys.start), slice(cx0, cx0 + xs.stop - xs.start))
        a = alpha[sub]
        cm[ys, xs, :3] = np.where(a[..., None] > 0, col[sub], cm[ys, xs, :3])
        cm[ys, xs, 3] = np.maximum(cm[ys, xs, 3], a * 255)
        height_map[ys, xs] = np.maximum(height_map[ys, xs], hm[sub])
    # под прозрачным — цвет края (как у EA): растекание цвета глифов наружу
    a = cm[..., 3] > 0
    if a.any():
        idx = ndi.distance_transform_edt(~a, return_distances=False, return_indices=True)
        cm[..., :3] = cm[..., :3][idx[0], idx[1]]
    cm8 = np.clip(cm + 0.5, 0, 255).astype(np.uint8)
    # рельеф: градиент сглаженной карты высот (ступени заливка/обводки) + фактура ткани EA внутри глифов
    hs = ndi.gaussian_filter(height_map, 1.2)
    gy, gx = np.gradient(hs)
    k = 0.9
    nx, ny = -gx * k, -gy * k
    nz = np.ones_like(nx)
    if nm_template is not None:                       # фактура: отклонение нормалей шаблона внутри его глифов
        t = nm_template.astype(np.float32) / 127.5 - 1
        tx, ty = t[..., 0], t[..., 1]
        sm_ = ndi.uniform_filter(tx, 9), ndi.uniform_filter(ty, 9)
        fx, fy = tx - sm_[0], ty - sm_[1]
        tex = (cm[..., 3] > 128)
        nx = nx + np.where(tex, fx * 0.8, 0)
        ny = ny + np.where(tex, fy * 0.8, 0)
    n = np.sqrt(nx * nx + ny * ny + nz * nz)
    nm = np.zeros((S, S, 4), np.uint8)
    nm[..., 0] = np.clip((nx / n + 1) * 127.5, 0, 255)
    nm[..., 1] = np.clip((ny / n + 1) * 127.5, 0, 255)
    nm[..., 2] = np.clip((nz / n + 1) * 127.5, 0, 255)
    nm[..., 3] = 255
    sm = np.zeros((S, S, 4), np.uint8)
    on = cm8[..., 3] >= 128
    sm[on, :3] = sm_value
    sm[on, 3] = 255
    return cm8, nm, sm
