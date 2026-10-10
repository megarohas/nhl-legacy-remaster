"""Знаки ® / ™ на растровых логотипах (PNG АХЛ из кэша HockeyTech): кандидаты — мелкие отдельные пятна непрозрачного
у края рисунка. Лист с рамками и номерами — для проверки глазами; убирать — рамками "blank" в tools/logos/clubs_ahl.json
(координаты PNG, png_svg в build.py закрашивает их прозрачным).

    venv/python tools/logos/pngmarks.py OUT.png PNG… [--json OUT.json]
"""
import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage as ndi


def candidates(path):
    im = np.asarray(Image.open(path).convert('RGBA'))
    a = im[..., 3] > 32
    ys, xs = np.nonzero(a)
    x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
    size = max(x1 - x0, y1 - y0)
    lab, n = ndi.label(ndi.binary_dilation(a, iterations=1), structure=np.ones((3, 3)))
    out = []
    for k, sl in enumerate(ndi.find_objects(lab), 1):
        h, w = sl[0].stop - sl[0].start, sl[1].stop - sl[1].start
        if max(h, w) > 0.09 * size or max(h, w) < 3:
            continue
        cx, cy = (sl[1].start + sl[1].stop) / 2, (sl[0].start + sl[0].stop) / 2
        # у края рамки рисунка (знак ставят снаружи, справа/снизу)
        edge = min(cx - x0, x1 - cx, cy - y0, y1 - cy) / size
        out.append(dict(box=[int(sl[1].start) - 2, int(sl[0].start) - 2, int(sl[1].stop) + 2, int(sl[0].stop) + 2],
                        edge=round(float(edge), 3), size=[int(w), int(h)]))
    return out, im


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    a = sys.argv[1:]
    jout = None
    if '--json' in a:
        i = a.index('--json'); jout = a[i + 1]; del a[i:i + 2]
    out, files = a[0], a[1:]
    font = ImageFont.truetype('C:/Windows/Fonts/segoeui.ttf', 16)
    tiles, res = [], {}
    for p in files:
        cand, im = candidates(p)
        res[os.path.basename(p)] = cand
        img = Image.fromarray(im, 'RGBA')
        bg = Image.new('RGBA', img.size, (190, 190, 190, 255))
        bg.alpha_composite(img)
        d = ImageDraw.Draw(bg)
        for k, c in enumerate(cand):
            col = (255, 0, 0, 255) if c['edge'] < 0.12 else (0, 120, 255, 255)
            d.rectangle(c['box'], outline=col, width=2)
            d.text((c['box'][0], c['box'][3] + 1), str(k), fill=col, font=font)
        d.text((4, 4), os.path.basename(p), fill=(0, 0, 0, 255), font=font)
        tiles.append(bg.resize((360, 360)))
        print(f"{os.path.basename(p)}: " + '; '.join(f"{k} {c['box']} край {c['edge']}" for k, c in enumerate(cand)))
    cols = 6
    rows = (len(tiles) + cols - 1) // cols
    S = Image.new('RGB', (cols * 364, rows * 364), (30, 30, 30))
    for k, t in enumerate(tiles):
        S.paste(t.convert('RGB'), ((k % cols) * 364, (k // cols) * 364))
    S.save(out)
    if jout:
        json.dump(res, open(jout, 'w', encoding='utf-8'), indent=1)
    print(out)


if __name__ == '__main__':
    main()
