"""Разбор SVG логотипа по <path>: рамка и площадь каждого (рендер «по цветам»: у каждого пути свой цвет заливки, Chrome
без окна, как teamart), поиск знаков ® / ™ — мелкие пути у края рисунка (кандидаты, проверка — глазами по листу).

    venv/python tools/logos/svgpaths.py SVG… [--json OUT.json] [--sheet OUT.png] [--scale 2]

Для каждого SVG: viewBox, число путей, рамка рисунка, по путям — рамка (в единицах viewBox), площадь (пикс.), цвет
заливки; «tm» — номера кандидатов в знаки ®/™."""
import json, os, re, sys, tempfile, shutil

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage as ndi

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import teamart as ta  # noqa: E402

PATH_RX = re.compile(r'<path\b[^>]*?(?:/>|>.*?</path>)', re.S)


def code_color(i):
    # различимые цвета без сглаживания по границе: шаг 37 по каждому каналу
    i += 1
    return (40 + (i * 37) % 200, 40 + (i * 71) % 200, 40 + (i * 113) % 200)


def coded_svg(svg):
    elems = list(PATH_RX.finditer(svg))
    out, pos = [], 0
    cols = []
    for i, m in enumerate(elems):
        c = code_color(i)
        cols.append(c)
        el = m.group(0)
        el = re.sub(r'\s(fill|stroke|style|class|opacity|fill-opacity)="[^"]*"', '', el)
        el = el.replace('<path', f'<path style="fill:rgb{c};stroke:none;opacity:1"', 1)
        out.append(svg[pos:m.start()]); out.append(el); pos = m.end()
    out.append(svg[pos:])
    return ''.join(out), cols, [m.group(0) for m in elems]


def render(svg, w, h, tmp, name):
    uri = ta.data_uri(svg)
    png = os.path.join(tmp, name)
    ta.render_html(ta.page(w, h, f'<img class="a" src="{uri}" style="left:0;top:0;width:{w}px;height:{h}px">'), png, w, h)
    return np.asarray(Image.open(png).convert('RGBA'))


def analyse(path, scale=2.0, tmp=None):
    svg = open(path, encoding='utf-8').read()
    vx, vy, vw, vh = ta._svg_viewbox(svg)
    W, H = int(vw * scale), int(vh * scale)
    coded, cols, elems = coded_svg(svg)
    img = render(coded, W, H, tmp, 'coded.png')
    full = render(svg, W, H, tmp, 'full.png')
    a = img[..., 3] > 250
    rgb = img[..., :3].astype(int)
    paths = []
    for i, c in enumerate(cols):
        m = a & (np.abs(rgb - np.array(c)).sum(-1) <= 3)
        fill = re.search(r'fill="([^"]*)"', elems[i])
        rec = dict(i=i, fill=fill.group(1) if fill else None, area=int(m.sum()))
        if m.any():
            ys, xs = np.nonzero(m)
            rec['box'] = [round(vx + xs.min() / scale, 1), round(vy + ys.min() / scale, 1),
                          round((xs.max() - xs.min() + 1) / scale, 1), round((ys.max() - ys.min() + 1) / scale, 1)]
        paths.append(rec)
    alpha = full[..., 3] > 8
    ys, xs = np.nonzero(alpha)
    box = [vx + xs.min() / scale, vy + ys.min() / scale, (xs.max() - xs.min() + 1) / scale, (ys.max() - ys.min() + 1) / scale]
    # компоненты связности рисунка: мелкая отдельная компонента у края — кандидат в ®/™
    lab, n = ndi.label(ndi.binary_dilation(alpha, iterations=1))
    sizes = ndi.sum(np.ones_like(lab), lab, range(1, n + 1))
    big = int(np.argmax(sizes)) + 1
    tm = []
    objs = ndi.find_objects(lab)
    main = objs[big - 1]
    mh, mw = main[0].stop - main[0].start, main[1].stop - main[1].start
    for k, sl in enumerate(objs, 1):
        if k == big:
            continue
        h, w = sl[0].stop - sl[0].start, sl[1].stop - sl[1].start
        if max(h, w) > 0.12 * max(mh, mw):
            continue
        comp = lab[sl] == k
        # какие пути внутри компоненты
        sub = img[sl]
        ids = set()
        for i, c in enumerate(cols):
            mm = (np.abs(sub[..., :3].astype(int) - np.array(c)).sum(-1) <= 3) & (sub[..., 3] > 250) & comp
            if mm.any():
                ids.add(i)
        # путь целиком внутри мелкой компоненты?
        for i in sorted(ids):
            pa = paths[i]['area']
            inside = int(((np.abs(sub[..., :3].astype(int) - np.array(cols[i])).sum(-1) <= 3) & comp).sum())
            if pa and inside >= 0.98 * pa:
                tm.append(dict(path=i, comp_box=[round(vx + sl[1].start / scale, 1), round(vy + sl[0].start / scale, 1),
                                                 round(w / scale, 1), round(h / scale, 1)]))
    return dict(file=os.path.basename(path), viewbox=[vx, vy, vw, vh], n_paths=len(elems),
                box=[round(v, 1) for v in box], paths=paths, tm=tm), full, img, scale


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    args = sys.argv[1:]
    jout = sheet = None
    scale = 2.0
    if '--json' in args:
        i = args.index('--json'); jout = args[i + 1]; del args[i:i + 2]
    if '--sheet' in args:
        i = args.index('--sheet'); sheet = args[i + 1]; del args[i:i + 2]
    if '--scale' in args:
        i = args.index('--scale'); scale = float(args[i + 1]); del args[i:i + 2]
    res, thumbs = [], []
    tmp = tempfile.mkdtemp(prefix='svgpaths_', dir=os.environ.get('LOGOS_TMP'))
    try:
        for p in args:
            r, full, img, sc = analyse(p, scale, tmp)
            res.append(r)
            print(f"{r['file']}: путей {r['n_paths']}, рамка {r['box']}, ®/™: {[t['path'] for t in r['tm']]}")
            if sheet:
                im = Image.fromarray(full).convert('RGBA')
                bg = Image.new('RGBA', im.size, (200, 200, 200, 255)); bg.alpha_composite(im)
                d = ImageDraw.Draw(bg)
                vx, vy = r['viewbox'][:2]
                for t in r['tm']:
                    x, y, w, h = t['comp_box']
                    d.rectangle([(x - vx) * sc - 4, (y - vy) * sc - 4, (x - vx + w) * sc + 4, (y - vy + h) * sc + 4], outline=(255, 0, 0, 255), width=4)
                    d.text(((x - vx) * sc, (y - vy + h) * sc + 6), str(t['path']), fill=(255, 0, 0, 255))
                bg = bg.resize((480, 320))
                ImageDraw.Draw(bg).text((6, 4), r['file'], fill=(0, 0, 0, 255))
                thumbs.append(bg)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    if jout:
        json.dump(res, open(jout, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    if sheet and thumbs:
        cols = 4
        rows = (len(thumbs) + cols - 1) // cols
        S = Image.new('RGBA', (480 * cols, 320 * rows), (255, 255, 255, 255))
        for k, t in enumerate(thumbs):
            S.paste(t, ((k % cols) * 480, (k // cols) * 320))
        S.convert('RGB').save(sheet)
        print(f'лист: {sheet}')


if __name__ == '__main__':
    main()
