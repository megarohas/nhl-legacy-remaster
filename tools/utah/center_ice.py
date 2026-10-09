"""Центр льда в формате NHL Legacy с названием арены по дуге (как у EA в Legacy: «ARIZONA ARENA» вокруг круга
вбрасывания): логотип клуба — teamart.center_rgba (диск 388, синее кольцо, прозрачная полоса под красную линию),
название — две дуги вне диска (радиус 400…455, буквы верхом к центру, читаются против часовой стрелки — как у EA),
цвет и шрифт — из SPEC. Контейнер — centerlogo того же числа цифр (teamart.RX_TEMPLATES), мипы — полные.

    python tools/utah/center_ice.py SPEC.json OUTDIR [--preview DIR] [--game legacy]

SPEC — как у teamart build (artid, svg, center_box) + "arena_text": {"text": "DELTA CENTER", "color": "#262626",
"font": "Segoe UI", "weight": 700, "size": 50, "spacing": 6, "baseline": 452, "span": 88}. Без "arena_text" — как
teamart build --only center.
"""
import os, sys, math, shutil, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import teamart as ta        # noqa: E402
import playerhead as ph     # noqa: E402

DEFAULT_TEXT = {'color': '#262626', 'font': 'Segoe UI', 'weight': 700, 'size': 50, 'spacing': 6,
                'baseline': 452.0, 'span': 88.0}


def arc_text_rgba(t, n=1024):
    """Две дуги текста (слева и справа), RGBA n×n — снимок Chrome (SVG textPath)."""
    t = dict(DEFAULT_TEXT, **t)
    c = n / 2
    R = t['baseline']
    h = math.radians(t['span'] / 2)

    def pt(deg):                                   # угол в «математических» градусах (y вверх) → точка экрана
        a = math.radians(deg)
        return c + R * math.cos(a), c - R * math.sin(a)
    # слева: сверху вниз через 180°, справа: снизу вверх через 0° — обе против часовой (sweep 0), верх букв — к центру
    lx0, ly0 = pt(180 - t['span'] / 2)
    lx1, ly1 = pt(180 + t['span'] / 2)
    rx0, ry0 = pt(-t['span'] / 2)
    rx1, ry1 = pt(t['span'] / 2)
    style = (f"font-family:'{t['font']}';font-weight:{t['weight']};font-size:{t['size']}px;"
             f"letter-spacing:{t['spacing']}px;fill:{t['color']}")
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{n}" height="{n}" viewBox="0 0 {n} {n}">'
           f'<path id="l" d="M{lx0:.2f},{ly0:.2f} A{R},{R} 0 0 0 {lx1:.2f},{ly1:.2f}" fill="none"/>'
           f'<path id="r" d="M{rx0:.2f},{ry0:.2f} A{R},{R} 0 0 0 {rx1:.2f},{ry1:.2f}" fill="none"/>'
           f'<text style="{style}" dominant-baseline="alphabetic"><textPath href="#l" startOffset="50%" '
           f'text-anchor="middle">{t["text"]}</textPath></text>'
           f'<text style="{style}" dominant-baseline="alphabetic"><textPath href="#r" startOffset="50%" '
           f'text-anchor="middle">{t["text"]}</textPath></text></svg>')
    tmp = tempfile.mkdtemp(prefix='center_ice_')
    try:
        png = os.path.join(tmp, 'arc.png')
        ta.render_html(ta.page(n, n, f'<div class="a" style="left:0;top:0">{svg}</div>'), png, n, n)
        return ph.png_read(png)[2]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def build(spec_path, outdir, preview=None):
    spec = ta.load_spec(spec_path)
    base = os.path.dirname(os.path.abspath(spec_path))
    svg = ta.svg_text(os.path.join(base, spec['svg']), tuple(spec.get('strip_paths', ())))
    spec['viewbox'] = ta._svg_viewbox(svg)
    spec['_uri'] = ta.data_uri(svg)
    tmp = tempfile.mkdtemp(prefix='center_ice_b_')
    try:
        if 'box' not in spec:
            spec['box'] = ta.measure_box(spec['_uri'], spec['viewbox'], tmp)
        rgba = bytearray(ta.center_rgba(spec, tmp))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    n = ta.CENTER['size']
    at = spec.get('arena_text')
    if at:
        txt = arc_text_rgba(at, n)
        r_in = ta.CENTER['r_disk'] + 4                 # текст — только вне диска льда
        s0, s1 = ta.CENTER['stripe']
        cx = cy = n / 2
        for y in range(n):
            for x in range(n):
                o = (y * n + x) * 4
                a = txt[o + 3]
                if not a or s0 <= x < s1 or math.hypot(x + 0.5 - cx, y + 0.5 - cy) < r_in:
                    continue
                da = rgba[o + 3]
                oa = a + da * (255 - a) // 255
                for k in range(3):
                    rgba[o + k] = (txt[o + k] * a + rgba[o + k] * da * (255 - a) // 255) // max(1, oa)
                rgba[o + 3] = oa
    num = int(spec['artid'])
    tpl_rel, tpl_num = ta.rx_template('center', num)
    tpl = ta.Rw4.load(ta.extracted(tpl_rel))
    t = tpl.textures[0]
    tpl.replace(t, ta.mip_chain(bytes(rgba), n, n, len(t.layout.levels)))
    tpl.rename(tpl_num, num)
    rel = ta.RX_SETS['center'][0].format(num)
    out = os.path.join(outdir, *rel.split('/'))
    os.makedirs(os.path.dirname(out), exist_ok=True)
    data = tpl.bytes()
    open(out, 'wb').write(data)
    print(f'{rel}: {len(data)} байт' + (f', дуги «{at["text"]}»' if at else ''))
    if preview:
        os.makedirs(preview, exist_ok=True)
        obj = ta.Rw4.load(out)
        w, h, dec = obj.decode(obj.textures[0], 0)
        ph.png_write(os.path.join(preview, f'center{num}.png'), w, h, dec)
    return rel


def main():
    game, argv = ta.split_game(sys.argv[1:])
    ta.set_game(game)
    if len(argv) < 2:
        sys.exit(__doc__)
    preview = argv[argv.index('--preview') + 1] if '--preview' in argv else None
    build(argv[0], argv[1], preview)


if __name__ == '__main__':
    main()
