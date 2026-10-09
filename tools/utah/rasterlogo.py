"""Логотип из официальной растровой картинки (NHL.com: набор логотипов, фото формы) → чистый RGBA и SVG-обёртка
(<image> внутри SVG: так его берут kitpaint.apply_logos и teamart, которые рисуют SVG в Chrome).

Для знаков, которых нет в открытых векторных файлах (у Utah Mammoth в Википедии и NHL assets — только основной логотип):
«Utah Badge» (плечи домашней формы), «U с бивнем» (шорты), надпись «UTAH» лесенкой (грудь выездной формы).
Пиксели делятся на три цвета клуба (тёмный, голубой, светлый) по близости; фон — светлое, связанное с краем рамки
(заливка от краёв); внутри контура светлое — белый цвет логотипа. Края — сглаживание мягких масок классов при
увеличении. Цвета — палитра клуба (не цвета фото).

    python tools/utah/rasterlogo.py IMAGE x0,y0,x1,y1 OUT.svg [--scale 4] [--png OUT.png]
          [--dark #010101] [--blue #6CACE4] [--light #FFFFFF] [--rotate DEG]
          [--blank x0,y0,x1,y1[;…]]   # закрасить фоном (координаты картинки)
          [--white-min 250]   # белое — пиксели ярче порога (фон картинки светло-серый), без заливки от краёв
"""
import base64
import io
import sys

import numpy as np
from PIL import Image
from scipy import ndimage as ndi


def hexrgb(c):
    c = c.lstrip('#')
    return np.array([int(c[i:i + 2], 16) for i in (0, 2, 4)], np.float32)


def extract(path, box, scale=4, dark='#010101', blue='#6CACE4', light='#FFFFFF', rotate=0.0, white_min=0, blank=None):
    im = Image.open(path).convert('RGBA')
    bg = Image.new('RGBA', im.size, (242, 242, 242, 255))
    bg.alpha_composite(im)
    full = bg.convert('RGB')
    for bx0, by0, bx1, by1 in blank or ():                   # закрасить фоном (чужие знаки в рамке: «C» капитана)
        full.paste(full.getpixel((box[0] + 1, box[1] + 1)), (bx0, by0, bx1, by1))
    a = np.asarray(full.crop(box)).astype(np.float32)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    lum = 0.299 * r + 0.587 * g + 0.114 * b
    is_blue = (b - r > 45) & (b > 140)
    is_dark = (lum < 110) & ~is_blue
    is_light = ~is_blue & ~is_dark
    if white_min:                                            # белое логотипа ярче светло-серого фона картинки;
        cand = is_light & (a.min(-1) < white_min)            # фон — серое, связанное с краем рамки
        lab, n = ndi.label(cand)
        edge = set(np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))) - {0}
        white = is_light & ~np.isin(lab, list(edge))
    else:                                                    # фон — светлое, связанное с краем рамки
        lab, n = ndi.label(is_light)
        edge = set(np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))) - {0}
        white = is_light & ~np.isin(lab, list(edge))
    classes = [(is_dark, hexrgb(dark)), (is_blue, hexrgb(blue)), (white, hexrgb(light))]
    H, W = a.shape[:2]
    out = np.zeros((H * scale, W * scale, 4), np.float32)
    soft = []
    for m, _ in classes:
        mm = Image.fromarray((m * 255).astype(np.uint8)).resize((W * scale, H * scale), Image.BICUBIC)
        soft.append(ndi.gaussian_filter(np.asarray(mm).astype(np.float32) / 255, scale * 0.35))
    tot = np.clip(sum(soft), 1e-6, None)
    alpha = np.clip(sum(soft), 0, 1)
    alpha = np.clip((alpha - 0.5) * 4 + 0.5, 0, 1)            # чёткий край
    col = sum(s[..., None] * c for s, (_, c) in zip(soft, classes)) / tot[..., None]
    out[..., :3] = col
    out[..., 3] = alpha * 255
    img = Image.fromarray(np.clip(out + 0.5, 0, 255).astype(np.uint8), 'RGBA')
    if rotate:
        img = img.rotate(rotate, resample=Image.BICUBIC, expand=True)
    bb = img.getbbox()
    return img.crop(bb)


def svg_wrap(img):
    buf = io.BytesIO()
    img.save(buf, 'PNG')
    data = base64.b64encode(buf.getvalue()).decode('ascii')
    w, h = img.size
    return (f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
            f'viewBox="0 0 {w} {h}" width="{w}" height="{h}">'
            f'<image width="{w}" height="{h}" href="data:image/png;base64,{data}"/></svg>')


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    args = sys.argv[1:]
    if len(args) < 3:
        sys.exit(__doc__)
    path, box, out = args[0], tuple(int(v) for v in args[1].split(',')), args[2]

    def opt(name, default):
        return args[args.index(name) + 1] if name in args else default
    img = extract(path, box, int(opt('--scale', 4)), opt('--dark', '#010101'), opt('--blue', '#6CACE4'),
                  opt('--light', '#FFFFFF'), float(opt('--rotate', 0)), int(opt('--white-min', 0)),
                  [tuple(int(v) for v in b.split(',')) for b in opt('--blank', '').split(';') if b])
    if '--png' in args:
        img.save(opt('--png', None))
    open(out, 'w', encoding='utf-8').write(svg_wrap(img))
    print(f'{out}: {img.size[0]}×{img.size[1]}')


if __name__ == '__main__':
    main()
