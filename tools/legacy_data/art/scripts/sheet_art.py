"""Лист превью арта команд (интерфейс и 3D) рядом с образцом EA — Chrome/Edge без окна.

    python sheet_art.py OUT_UI.png OUT_3D.png REF_ROOT REF_ART "подпись=ROOT:ART[:SPOT]"…

REF_ROOT — корень дерева cache: с оригиналами EA (распакованные архивы игры: …/big/cache и …/big/cacherender
ищутся сами), REF_ART — номер арта образца (23 — «Питтсбург»); дальше — собранные наборы: ROOT — дерево как в
cache: (out/), ART — номер арта, SPOT — номер прожектора."""
import base64, html as H, os, sys, tempfile, shutil
TOOLS = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..')   # tools/legacy_data/art/scripts → tools
sys.path.insert(0, os.path.normpath(TOOLS))
import playerhead as ph, teamart as ta, kitpaint as kp

UI = [('t', 'teamlogos', 't', 'основной (t)'), ('s', 'teamlogossmall', 's', '«таблетка» (s)'),
      ('d', 'teamlogosdynasty', 'd', 'франшиза (d)'), ('c', 'teamlogoscalendar', 'c', 'календарь (c)'),
      ('w', 'teamlogoswide', 'w', 'крупный план (w)'), ('r', 'teamlogosreflection', 'r', 'с отражением (r)')]
RX = [('center', 'rendering/icesurface/centerlogo_{}_cm.rx2', 'центр льда 1024²'),
      ('puck', 'rendering/puck/puck_{}_cm.rx2', 'шайба 256×512'),
      ('banner', 'rendering/banner/banner_{}_cm.rx2', 'баннер 512²'),
      ('spot', 'rendering/spotlight/texlib_{}.rx2', 'прожекторы 256²')]


def find(root, rel):
    for p in (os.path.join(root, *rel.split('/')), os.path.join(root, 'cache', *rel.split('/')),
              os.path.join(root, 'cacherender', *rel.split('/'))):
        if os.path.exists(p):
            return p
    return None


def uri(w, h, rgba, tmp, name):
    p = os.path.join(tmp, name + '.png')
    ph.png_write(p, w, h, rgba)
    return 'data:image/png;base64,' + base64.b64encode(open(p, 'rb').read()).decode('ascii')


def main():
    out_ui, out_3d, ref_root, ref_art = sys.argv[1:5]
    sets = [('EA (образец)', ref_root, ref_art, ref_art)]
    for a in sys.argv[5:]:
        label, spec = a.rsplit('=', 1)
        bits = spec.rsplit(':', 2)                     # путь может содержать «C:» — разбор с конца
        root, art, spot = bits[0], bits[1], bits[2]
        sets.append((label, root, art, spot))
    tmp = tempfile.mkdtemp(prefix='sheetart_')
    css = ('html,body{margin:0;background:#3a3f46;color:#e8eaed;font:14px "Segoe UI",Arial,sans-serif;overflow:hidden}'
           'h1{margin:0;padding:14px 20px 4px;font-size:22px}table{border-collapse:separate;border-spacing:10px 6px;margin:0 10px}'
           'td{vertical-align:top}th{text-align:left;font-weight:600;color:#cfd3d8;padding-right:8px}'
           'img{display:block;background:repeating-conic-gradient(#8a8f96 0 25%,#6c7178 0 50%) 0 0/16px 16px}'
           '.cap{color:#aab0b7;font-size:12px;margin-top:2px}')
    try:
        # интерфейс
        rows = []
        for label, root, art, spot in sets:
            cells = [f'<th>{H.escape(label)}<div class="cap">art {art}</div></th>']
            for kind, folder, letter, cap in UI:
                p = find(root, f'fe/ion/artassets/{folder}/{letter}{art}.big')
                if not p:
                    cells.append('<td>—</td>')
                    continue
                lg = ta.UiLogo.load(p)
                w, h, rgba = lg.decode()
                sw, sh = lg.stage
                rgba = ph.crop(rgba, w, h, sw, sh)
                cells.append(f'<td><img src="{uri(sw, sh, rgba, tmp, f"u{label}{kind}")}" style="width:{sw}px;height:{sh}px">'
                             f'<div class="cap">{cap} {sw}×{sh}</div></td>')
            rows.append('<tr>' + ''.join(cells) + '</tr>')
        page = (f'<!doctype html><html><head><meta charset="utf-8"><style>{css}</style></head><body>'
                f'<h1>Логотипы интерфейса (NHL Legacy): образец EA и свои</h1><table>{"".join(rows)}</table></body></html>')
        kp.render_page(page, out_ui, 1640, 90 + 560 * len(sets))
        # 3D
        rows = []
        for label, root, art, spot in sets:
            cells = [f'<th>{H.escape(label)}<div class="cap">art {art}, прожектор {spot}</div></th>']
            for kind, pat, cap in RX:
                p = find(root, pat.format(spot if kind == 'spot' else art))
                if not p:
                    cells.append('<td>—</td>')
                    continue
                rw = ta.Rw4.load(p)
                t = rw.textures[0]
                w, h, rgba = rw.decode(t, 0)
                if kind == 'center':
                    for _ in range(2):
                        rgba, w, h = ta.downsample2(rgba, w, h)
                dw, dh = (w, h)
                cells.append(f'<td><img src="{uri(w, h, rgba, tmp, f"x{label}{kind}")}" style="width:{dw}px;height:{dh}px">'
                             f'<div class="cap">{cap}</div></td>')
            rows.append('<tr>' + ''.join(cells) + '</tr>')
        page = (f'<!doctype html><html><head><meta charset="utf-8"><style>{css}</style></head><body>'
                f'<h1>3D: центр льда (¼), шайба, баннер, прожекторы (NHL Legacy)</h1><table>{"".join(rows)}</table></body></html>')
        kp.render_page(page, out_3d, 1640, 90 + 545 * len(sets))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == '__main__':
    main()
