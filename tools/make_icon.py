"""Иконка NHL Legacy Remaster для nhllegacy.exe и лаунчера: «NHL / LEGACY / REMASTER» в три строки шрифтами
интерфейса самой игры (EA Helvetica Neue Heavy и Condensed Bold из fe/ion/fonts NHL Legacy).

    python tools/make_icon.py [--out DIR] [--jpg 1024]   # -> DIR/nhllegacy.ico (256…16), превью DIR/preview.png
                                                        #    и квадрат без скругления DIR/nhllegacy-1024.jpg

Шрифты берутся из файлов игры пользователя (game/other/legacy/big/cacheboot/fe/ion/fonts), поэтому ни шрифты,
ни готовая иконка в git не попадают: по умолчанию DIR = nhl-legacy-port/launcher/icon (в .gitignore).
Крупные размеры (256…48) — три строки; 32…16 — только «NHL» с полосой (три строки там не читаются).
ICO собирается вручную: каждый размер — PNG внутри ICO (Windows Vista+). Нужен Pillow.
"""
import argparse
import io
import os
import struct

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONTS = os.path.join(ROOT, 'game', 'other', 'legacy', 'big', 'cacheboot', 'fe', 'ion', 'fonts')
HEAVY = os.path.join(FONTS, 'eahelveticaneuehv-mod.ttf')
COND = os.path.join(FONTS, 'eahelveticaneueconbol-mod.ttf')

BG_TOP, BG_BOT = (16, 30, 54), (6, 11, 22)       # тёмно-синий, как шапка лаунчера
ACCENT = (34, 120, 230)                           # синяя полоса лаунчера
SILVER_TOP, SILVER_BOT = (255, 255, 255), (178, 188, 202)
SIZES = [256, 128, 64, 48, 32, 24, 16]


def fit_font(path, text, width, max_h):
    """Наибольший кегль, при котором text укладывается в width и max_h."""
    lo, hi = 4, 600
    while lo < hi:
        mid = (lo + hi + 1) // 2
        f = ImageFont.truetype(path, mid)
        l, t, r, b = f.getbbox(text)
        if r - l <= width and b - t <= max_h:
            lo = mid
        else:
            hi = mid - 1
    return ImageFont.truetype(path, lo)


def gradient(size, top, bot):
    w, h = size
    g = Image.new('RGB', (1, h))
    for y in range(h):
        k = y / max(1, h - 1)
        g.putpixel((0, y), tuple(int(top[i] + (bot[i] - top[i]) * k) for i in range(3)))
    return g.resize((w, h))


def text_layer(W, text, font, x0, y0, italic=0.0, fill_grad=(SILVER_TOP, SILVER_BOT), solid=None):
    """Строка текста маской: серебряный градиент или сплошной цвет, лёгкий наклон (как надписи игры)."""
    l, t, r, b = font.getbbox(text)
    tw, th = r - l, b - t
    pad = int(th * 0.4) + 2
    m = Image.new('L', (tw + 2 * pad, th + 2 * pad), 0)
    ImageDraw.Draw(m).text((pad - l, pad - t), text, font=font, fill=255)
    if italic:
        sh = italic
        m = m.transform(m.size, Image.AFFINE, (1, sh, -sh * m.size[1] / 2, 0, 1, 0), resample=Image.BICUBIC)
    col = Image.new('RGB', m.size, solid) if solid else gradient(m.size, *fill_grad)
    layer = Image.new('RGBA', (W, W), (0, 0, 0, 0))
    layer.paste(col, (x0 - pad, y0 - pad), m)
    return layer, (x0 - pad, y0 - pad, m)


def shadow(W, m_pos, blur, alpha):
    x, y, m = m_pos
    s = Image.new('L', (W, W), 0)
    s.paste(m, (x, y + max(1, W // 128)))
    s = s.filter(ImageFilter.GaussianBlur(blur)).point(lambda v: int(v * alpha))
    out = Image.new('RGBA', (W, W), (0, 0, 0, 0))
    out.putalpha(s)
    return out


def base(W, rounded=True):
    S = 4 if W <= 256 else 2  # суперсэмплинг
    big = W * S
    bg = gradient((big, big), BG_TOP, BG_BOT).convert('RGBA')
    if rounded:
        mask = Image.new('L', (big, big), 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, big - 1, big - 1), radius=int(big * 0.18), fill=255)
        bg.putalpha(mask)
    return bg, S


def draw_full(W, rounded=True, margin_k=0.09):
    img, S = base(W, rounded)
    B = W * S
    margin = int(B * margin_k)
    inner = B - 2 * margin
    k = inner / (B * (1 - 2 * 0.09))  # высоты строк — пропорционально полю
    # NHL — крупно, Heavy с наклоном; LEGACY — Condensed Bold; REMASTER — Condensed Bold, синий
    f1 = fit_font(HEAVY, 'NHL', inner, int(B * 0.36 * k))
    f2 = fit_font(COND, 'LEGACY', inner, int(B * 0.21 * k))
    f3 = fit_font(COND, 'REMASTER', inner, int(B * 0.15 * k))
    rows = [(f1, 'NHL', 0.12, None), (f2, 'LEGACY', 0.0, None), (f3, 'REMASTER', 0.0, ACCENT)]
    hs = [f.getbbox(t)[3] - f.getbbox(t)[1] for f, t, _, _ in rows]
    gap = int(B * 0.055 * k)
    total = sum(hs) + 2 * gap
    y = (B - total) // 2
    for i, (f, t, it, solid) in enumerate(rows):
        l, tp, r, bt = f.getbbox(t)
        x = (B - (r - l)) // 2
        layer, mp = text_layer(B, t, f, x, y, italic=it, solid=solid)
        img.alpha_composite(shadow(B, mp, B / 90, 0.6))
        img.alpha_composite(layer)
        y += hs[i] + gap
    return img.resize((W, W), Image.LANCZOS)


def draw_small(W):
    img, S = base(W)
    B = W * S
    inner = int(B * 0.84)
    f1 = fit_font(HEAVY, 'NHL', inner, int(B * 0.52))
    l, t, r, b = f1.getbbox('NHL')
    bar = max(S, int(B * 0.08))
    y = (B - (b - t) - bar - int(B * 0.06)) // 2
    layer, mp = text_layer(B, 'NHL', f1, (B - (r - l)) // 2, y, italic=0.1)
    img.alpha_composite(layer)
    yb = y + (b - t) + int(B * 0.08)
    ImageDraw.Draw(img).rectangle((int(B * 0.18), yb, int(B * 0.82), yb + bar), fill=ACCENT + (255,))
    return img.resize((W, W), Image.LANCZOS)


def write_ico(path, images):
    entries, blobs = [], []
    for im in images:
        buf = io.BytesIO()
        im.save(buf, 'PNG')
        blobs.append(buf.getvalue())
    off = 6 + 16 * len(images)
    hdr = struct.pack('<HHH', 0, 1, len(images))
    for im, data in zip(images, blobs):
        w = im.size[0]
        entries.append(struct.pack('<BBBBHHII', 0 if w >= 256 else w, 0 if w >= 256 else w, 0, 0, 1, 32, len(data), off))
        off += len(data)
    with open(path, 'wb') as f:
        f.write(hdr + b''.join(entries) + b''.join(blobs))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=os.path.join(ROOT, 'nhl-legacy-port', 'launcher', 'icon'))
    ap.add_argument('--jpg', type=int, default=1024, help='квадратная картинка без скругления, сторона (0 — не делать)')
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    imgs = [draw_full(s) if s >= 48 else draw_small(s) for s in SIZES]
    write_ico(os.path.join(a.out, 'nhllegacy.ico'), imgs)
    # превью: все размеры на сером, 256 и 128 крупно
    pv = Image.new('RGBA', (256 + 128 + 64 + 48 + 32 + 24 + 16 + 8 * 8, 272), (60, 64, 70, 255))
    x = 8
    for im in imgs:
        pv.alpha_composite(im, (x, 8))
        x += im.size[0] + 8
    pv.save(os.path.join(a.out, 'preview.png'))
    if a.jpg:
        draw_full(a.jpg, rounded=False, margin_k=0.2).convert('RGB').save(os.path.join(a.out, f'nhllegacy-{a.jpg}.jpg'), quality=95)
    print('->', os.path.join(a.out, 'nhllegacy.ico'))


if __name__ == '__main__':
    main()
