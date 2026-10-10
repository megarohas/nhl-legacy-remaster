"""Проверка вырезки знаков ®/™ (svgclean): исходный и чистый SVG рисуются в Chrome без окна, разница пикселей должна
быть только в маленькой области у края рисунка. Пишет лист: исходник, чистый, разница (красным) и увеличенный
фрагмент.

    venv/python tools/logos/svgdiff.py SRC_DIR CLEAN_DIR OUT.png [ИМЯ…] [--scale 1]
"""
import os, sys, tempfile, shutil

import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import teamart as ta  # noqa: E402


def render(svg_path, w, h, tmp, name):
    uri = ta.data_uri(open(svg_path, encoding='utf-8').read())
    png = os.path.join(tmp, name)
    ta.render_html(ta.page(w, h, f'<img class="a" src="{uri}" style="left:0;top:0;width:{w}px;height:{h}px">'), png, w, h)
    return np.asarray(Image.open(png).convert('RGBA')).astype(int)


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    a = sys.argv[1:]
    scale = 1.0
    if '--scale' in a:
        i = a.index('--scale'); scale = float(a[i + 1]); del a[i:i + 2]
    src, cln, out = a[0], a[1], a[2]
    names = a[3:] or sorted(f[:-4] for f in os.listdir(cln) if f.endswith('.svg'))
    tiles, bad = [], 0
    tmp = tempfile.mkdtemp(prefix='svgdiff_', dir=os.environ.get('LOGOS_TMP'))
    try:
        for n in names:
            vx, vy, vw, vh = ta._svg_viewbox(open(os.path.join(src, n + '.svg'), encoding='utf-8').read())
            W, H = int(vw * scale), int(vh * scale)
            A = render(os.path.join(src, n + '.svg'), W, H, tmp, 'a.png')
            B = render(os.path.join(cln, n + '.svg'), W, H, tmp, 'b.png')
            diff = (np.abs(A - B).max(-1) > 24)
            ys, xs = np.nonzero(diff)
            if len(xs):
                box = (xs.min(), ys.min(), xs.max() + 1, ys.max() + 1)
                bw, bh = box[2] - box[0], box[3] - box[1]
            else:
                box, bw, bh = None, 0, 0
            ok = box is not None and bw <= 40 * scale and bh <= 40 * scale
            bad += not ok
            print(f"{'OK ' if ok else 'ПРОВЕРИТЬ'} {n}: разница {bw}×{bh} px" + (f' в {box}' if box else ' — нет'))
            # плитка: исходник | чистый | фрагмент ×4 (исходник/чистый)
            t = Image.new('RGBA', (960, 260), (60, 64, 70, 255))
            for k, im in enumerate((A, B)):
                img = Image.fromarray(im.astype(np.uint8), 'RGBA').resize((360, 240))
                bg = Image.new('RGBA', img.size, (200, 200, 200, 255)); bg.alpha_composite(img)
                t.paste(bg, (k * 370, 18))
            if box:
                cx, cy = (box[0] + box[2]) // 2, (box[1] + box[3]) // 2
                r = int(30 * scale)
                for k, im in enumerate((A, B)):
                    crop = Image.fromarray(im.astype(np.uint8), 'RGBA').crop((cx - r, cy - r, cx + r, cy + r)).resize((110, 110), Image.NEAREST)
                    bg = Image.new('RGBA', crop.size, (200, 200, 200, 255)); bg.alpha_composite(crop)
                    t.paste(bg, (740 + k * 112, 18 + 60))
            ImageDraw.Draw(t).text((4, 2), f'{n}: разница {bw}x{bh}', fill=(255, 255, 255, 255))
            tiles.append(t)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    cols = 2
    rows = (len(tiles) + cols - 1) // cols
    S = Image.new('RGB', (960 * cols, 260 * rows), (40, 40, 40))
    for k, t in enumerate(tiles):
        S.paste(t.convert('RGB'), ((k % cols) * 960, (k // cols) * 260))
    S.save(out)
    print(f'лист {out}; проверить: {bad}')


if __name__ == '__main__':
    main()
