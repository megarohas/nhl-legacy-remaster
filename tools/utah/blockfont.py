"""Свой «квадратный» шрифт номеров и фамилий в духе Mammoth Sans (Utah Mammoth, 2025): прямые штрихи, прямоугольные
просветы, косые перекладины у A и H, наклон вперёд 10°. Настоящий Mammoth Sans — фирменный шрифт клуба, в открытом
доступе его нет; здесь — приближение по фото формы (NHL.com, 07.05.2025; снимки игроков из NHL API).

Глифы — многоугольники на сетке высотой 100 (прописная), растр — numpy/Pillow, без Chrome. masks(chars) → {символ:
маска 0..1}, как fontatlas.glyph_masks (источник "block" в SPEC шрифта: {"source": "block", "slant": 10,
"round": 1.5, "weight": 1.0}).
"""
import math

import numpy as np
from PIL import Image, ImageDraw

H = 100.0


def R(x0, y0, x1, y1):
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def P(*pts):
    return list(pts)


def glyphs(s=18.0, t=16.0):
    """{символ: (ширина, [многоугольники])}; s — толщина вертикальных штрихов, t — горизонтальных."""
    g = {}
    # ---- цифры (ширина 58)
    W = 58.0
    m0, m1 = 50 - t / 2, 50 + t / 2                     # средняя перекладина
    g['0'] = (W, [R(0, 0, W, t), R(0, H - t, W, H), R(0, 0, s, H), R(W - s, 0, W, H)])
    g['1'] = (W, [R(W / 2 - s / 2 + 4, 0, W / 2 + s / 2 + 4, H), P((W / 2 - s / 2 + 4, 0), (W / 2 - s / 2 + 4, t + 6),
                                                                  (8, t + 6), (8, t - 4), (18, 0))])
    g['2'] = (W, [R(0, 0, W, t), R(W - s, 0, W, m1), R(0, m0, W, m1), R(0, m0, s, H), R(0, H - t, W, H)])
    g['3'] = (W, [R(0, 0, W, t), R(W - s, 0, W, H), R(10, m0, W, m1), R(0, H - t, W, H)])
    g['4'] = (W, [R(0, 0, s, m1 + 4), R(0, m0 + 4, W, m1 + 4), R(W - s - 4, 0, W - 4, H)])
    g['5'] = (W, [R(0, 0, W, t), R(0, 0, s, m1), R(0, m0, W, m1), R(W - s, m0, W, H), R(0, H - t, W, H)])
    g['6'] = (W, [R(0, 0, W, t), R(0, 0, s, H), R(0, m0, W, m1), R(W - s, m0, W, H), R(0, H - t, W, H)])
    g['7'] = (W, [R(0, 0, W, t), P((W - s, 0), (W, 0), (W, t + 8), (s + 12, H), (12, H), (W - s, t + 4))])
    g['8'] = (W, [R(0, 0, W, t), R(0, m0, W, m1), R(0, H - t, W, H), R(0, 0, s, H), R(W - s, 0, W, H)])
    g['9'] = (W, [R(0, 0, W, t), R(0, 0, s, m1), R(0, m0, W, m1), R(W - s, 0, W, H), R(0, H - t, W, H)])
    # ---- буквы (ширина 50, у широких — своя)
    L = 50.0
    sl, tl = s * 0.9, t * 0.9
    a0, a1 = 54 - tl / 2, 54 + tl / 2
    cb = 9.0                                              # подъём косой перекладины (A, H)
    g['A'] = (L, [P((0, 18), (16, 0), (L, 0), (L, H), (L - sl, H), (L - sl, tl), (sl + 6, tl), (sl, tl + 8), (sl, H),
                    (0, H)),
                  P((sl, a0 + cb), (L - sl, a0 - cb), (L - sl, a1 - cb), (sl, a1 + cb))])
    g['B'] = (L, [R(0, 0, L - 8, tl), R(0, H - tl, L, H), R(0, 0, sl, H), R(L - sl - 6, 0, L - 6, 50), R(0, 50 - tl / 2, L, 50 + tl / 2),
                  R(L - sl, 50 - tl / 2, L, H)])
    g['C'] = (L, [R(0, 0, L, tl), R(0, H - tl, L, H), R(0, 0, sl, H)])
    g['D'] = (L, [R(0, 0, L - 10, tl), R(0, H - tl, L - 10, H), R(0, 0, sl, H), R(L - sl, 10, L, H - 10),
                  P((L - 10, 0), (L, 10), (L, 14), (L - sl, 14), (L - sl, tl), (L - 10, tl)),
                  P((L - sl, H - 14), (L, H - 14), (L, H - 10), (L - 10, H), (L - 10, H - tl), (L - sl, H - tl))])
    g['E'] = (L - 4, [R(0, 0, L - 4, tl), R(0, H - tl, L - 4, H), R(0, 0, sl, H), R(0, 50 - tl / 2, L - 10, 50 + tl / 2)])
    g['F'] = (L - 4, [R(0, 0, L - 4, tl), R(0, 0, sl, H), R(0, 50 - tl / 2, L - 10, 50 + tl / 2)])
    g['G'] = (L, [R(0, 0, L, tl), R(0, H - tl, L, H), R(0, 0, sl, H), R(L - sl, 48, L, H), R(L - 24, 48, L, 48 + tl)])
    g['H'] = (L, [R(0, 0, sl, H), R(L - sl, 0, L, H), P((sl, a0 - 6 + cb), (L - sl, a0 - 6 - cb), (L - sl, a1 - 6 - cb),
                                                          (sl, a1 - 6 + cb))])
    g['I'] = (sl, [R(0, 0, sl, H)])
    g['J'] = (L - 4, [R(L - 4 - sl, 0, L - 4, H), R(0, H - tl, L - 4, H), R(0, 62, sl, H)])
    g['K'] = (L, [R(0, 0, sl, H), P((sl, 44), (L - sl + 2, 0), (L + 2, 0), (sl + 8, 56), (sl, 60)),
                  P((sl + 4, 46), (sl + 14, 40), (L, H), (L - sl, H))])
    g['L'] = (L - 6, [R(0, 0, sl, H), R(0, H - tl, L - 6, H)])
    g['M'] = (64.0, [R(0, 0, sl, H), R(64 - sl, 0, 64, H), R(0, 0, 64, tl), R(32 - sl / 2, 0, 32 + sl / 2, 70)])
    N = L + 6
    g['N'] = (N, [R(0, 0, sl, H), R(N - sl, 0, N, H), P((0, 0), (sl, 0), (N, H - 26), (N, H), (N - sl, H), (0, 26))])
    g['O'] = (L, [R(0, 0, L, tl), R(0, H - tl, L, H), R(0, 0, sl, H), R(L - sl, 0, L, H)])
    g['P'] = (L, [R(0, 0, L, tl), R(0, 0, sl, H), R(L - sl, 0, L, 56), R(0, 56 - tl, L, 56)])
    g['Q'] = (L, [R(0, 0, L, tl), R(0, H - tl, L, H), R(0, 0, sl, H), R(L - sl, 0, L, H),
                  P((L - 22, H - tl - 10), (L - 10, H - tl - 16), (L + 6, H + 2), (L - 8, H + 8))])
    g['R'] = (L, [R(0, 0, L, tl), R(0, 0, sl, H), R(L - sl, 0, L, 54), R(0, 54 - tl, L, 54),
                  P((L - sl - 8, 54 - tl), (L - 8, 54 - tl), (L, H), (L - sl, H))])
    g['S'] = (L, [R(0, 0, L, tl), R(0, 0, sl, 50 + tl / 2), R(0, 50 - tl / 2, L, 50 + tl / 2), R(L - sl, 50 - tl / 2, L, H),
                  R(0, H - tl, L, H)])
    g['T'] = (L, [R(0, 0, L, tl), R(L / 2 - sl / 2, 0, L / 2 + sl / 2, H)])
    g['U'] = (L, [R(0, 0, sl, H), R(L - sl, 0, L, H), R(0, H - tl, L, H)])
    g['V'] = (L + 4, [P((0, 0), (sl, 0), (L / 2 + 2, H - 22), (L + 4 - sl, 0), (L + 4, 0), (L / 2 + 2 + sl / 2, H),
                        (L / 2 + 2 - sl / 2, H))])
    g['W'] = (66.0, [R(0, 0, sl, H), R(66 - sl, 0, 66, H), R(0, H - tl, 66, H), R(33 - sl / 2, 30, 33 + sl / 2, H)])
    g['X'] = (L + 4, [P((0, 0), (sl + 2, 0), (L + 4, H), (L + 4 - sl - 2, H)), P((L + 4 - sl - 2, 0), (L + 4, 0), (sl + 2, H), (0, H))])
    g['Y'] = (L + 4, [P((0, 0), (sl + 2, 0), (L / 2 + 2 + sl / 2, 52), (L / 2 + 2 - sl / 2, 58)),
                      P((L + 4 - sl - 2, 0), (L + 4, 0), (L / 2 + 2 + sl / 2, 58), (L / 2 + 2 - sl / 2, 52)),
                      R(L / 2 + 2 - sl / 2, 50, L / 2 + 2 + sl / 2, H)])
    g['Z'] = (L, [R(0, 0, L, tl), R(0, H - tl, L, H), P((L - sl - 4, tl), (L, tl), (sl + 4, H - tl), (0, H - tl))])
    return g


def masks(chars, height=256, slant=10.0, weight=1.0, round_px=1.5, ss=4):
    """{символ: маска float32 (h, w)} — глиф высотой height (прописная), с наклоном slant° вперёд."""
    g = glyphs(18.0 * weight, 16.0 * weight)
    out = {}
    k = height / H
    sh = math.tan(math.radians(slant))
    for ch in chars:
        if ch not in g:
            raise SystemExit(f'blockfont: нет глифа «{ch}»')
        w, polys = g[ch]
        pad = 8
        Wd = int(math.ceil((w + H * sh + 2 * pad) * k * ss))
        Hd = int(math.ceil((H + 2 * pad + 10) * k * ss))
        im = Image.new('L', (Wd, Hd), 0)
        d = ImageDraw.Draw(im)
        for poly in polys:
            pts = []
            for x, y in poly:
                xx = x + (H - y) * sh + pad             # наклон вперёд: верх вправо
                pts.append((xx * k * ss, (y + pad) * k * ss))
            d.polygon(pts, fill=255)
        if round_px:
            from PIL import ImageFilter
            r = max(1, int(round(round_px * ss)))
            im = im.filter(ImageFilter.GaussianBlur(r)).point(lambda v: 255 if v >= 128 else 0)
        im = im.resize((Wd // ss, Hd // ss), Image.LANCZOS)
        a = np.asarray(im).astype(np.float32) / 255
        ys, xs = np.nonzero(a > 0.02)
        out[ch] = a[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    return out


def sheet(path, chars='ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789', **kw):
    m = masks(chars, 120, **kw)
    W = sum(v.shape[1] + 12 for v in m.values()) + 20
    Hh = max(v.shape[0] for v in m.values()) + 20
    out = np.zeros((Hh, W), np.float32)
    x = 10
    for ch in chars:
        a = m[ch]
        out[10:10 + a.shape[0], x:x + a.shape[1]] = a
        x += a.shape[1] + 12
    Image.fromarray((255 - out * 255).astype(np.uint8)).save(path)


if __name__ == '__main__':
    import sys
    sheet(sys.argv[1])
