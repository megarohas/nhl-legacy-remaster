"""Наклейка клуба на шлем (rendering/logo/texlib_A_S_V.rx2, растр logo_A_S_V_0 256×128 DXT5; _1 128×64 и _2 128×128 у
клубов НХЛ пустые) — при stockteamjerseys.helmetlogo = 1. У EA (замер клубов НХЛ Legacy) логотип по центру (128; 58,5),
рамка в среднем 102×81. Контейнер — файл EA с номером арта той же длины (3-значный — клуб АХЛ TEMPLATE3), имена
растров переписываются на свой номер и вариант (той же длины).

    python tools/utah/helmet.py SPEC.json OUTDIR --variants 0,1,2 [--box 104,80] [--preview DIR] [--game legacy]

SPEC — как у teamart (artid, svg, strip_paths); "helmet": {"svg": "файл", "box": [w, h]} — другой рисунок для шлема.
"""
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
sys.path.insert(0, TOOLS)
import teamart as ta        # noqa: E402
import kitpaint as kp       # noqa: E402
import playerhead as ph     # noqa: E402

TEMPLATE2 = 'rendering/logo/texlib_22_1_3.rx2'      # 2-значный арт
TEMPLATE3 = 'rendering/logo/texlib_131_1_0.rx2'     # 3-значный арт (Binghamton, АХЛ): та же структура
CENTER = (128.0, 58.5)


def build(spec_path, outdir, variants, box=(104, 80), preview=None):
    spec = ta.load_spec(spec_path)
    base = os.path.dirname(os.path.abspath(spec_path))
    hs = spec.get('helmet', {})
    svg = ta.svg_text(os.path.join(base, hs.get('svg', spec['svg'])), tuple(hs.get('strip_paths', spec.get('strip_paths', ()))))
    sp = {'viewbox': ta._svg_viewbox(svg), '_uri': ta.data_uri(svg)}
    box = tuple(hs.get('box', box))
    art = int(spec['artid'])
    tpl_rel = TEMPLATE3 if len(str(art)) == 3 else TEMPLATE2
    tmp = tempfile.mkdtemp(prefix='helmet_')
    made = []
    try:
        sp['box'] = ta.measure_box(sp['_uri'], sp['viewbox'], tmp)
        l, t, w, h = ta._place(sp, box[0], box[1], CENTER[0], CENTER[1])
        png = os.path.join(tmp, 'h.png')
        ta.render_html(ta.page(256, 128, ta.logo_layers(sp['_uri'], l, t, w, h)), png, 256, 128)
        _, _, rgba = ph.png_read(png)
        src = kp._unchunk(open(ta.GAME.extracted(tpl_rel), 'rb').read())
        old_tag = os.path.basename(tpl_rel)[len('texlib_'):-len('.rx2')]         # «131_1_0»
        for v in variants:
            rw = ta.Rw4(bytes(src), tpl_rel)
            tex0 = rw.textures[0]
            tw, th = tex0.fetch.width, tex0.fetch.height
            if (tw, th) != (256, 128):
                raise SystemExit(f'{tpl_rel}: растр 0 — {tw}×{th}, ждали 256×128')
            kp.tex_replace(rw, tex0, rgba, 256, 128)
            for tx in rw.textures[1:]:                                       # _1, _2 — пустые (как у клубов НХЛ)
                kp.tex_replace(rw, tx, bytes(tx.fetch.width * tx.fetch.height * 4), tx.fetch.width, tx.fetch.height)
            a, s_, v0 = old_tag.split('_')
            new_tag = f'{art}_{s_}_{v}'
            if len(new_tag) != len(old_tag):
                raise SystemExit(f'{old_tag} → {new_tag}: разная длина имени')
            for i, (spos, ln) in enumerate(rw.name_slots):
                s = bytes(rw.raw[spos:spos + ln]).decode('latin1')
                tname = s.replace(f'logo_{old_tag}_', f'logo_{new_tag}_', 1)
                if tname == s:
                    raise SystemExit(f'{s}: нет «logo_{old_tag}_»')
                rw.raw[spos:spos + ln] = tname.encode('latin1')
            rel = f'rendering/logo/texlib_{new_tag}.rx2'
            p = os.path.join(outdir, *rel.split('/'))
            os.makedirs(os.path.dirname(p), exist_ok=True)
            data = rw.bytes()
            open(p, 'wb').write(data)
            made.append(rel)
            print(f'{rel}: {len(data)} байт')
        if preview:
            os.makedirs(preview, exist_ok=True)
            ph.png_write(os.path.join(preview, f'helmet{art}.png'), 256, 128, rgba)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return made


def main():
    game, argv = ta.split_game(sys.argv[1:])
    ta.set_game(game)
    if len(argv) < 2:
        sys.exit(__doc__)
    variants = [int(x) for x in argv[argv.index('--variants') + 1].split(',')] if '--variants' in argv else [0, 1]
    box = tuple(int(x) for x in argv[argv.index('--box') + 1].split(',')) if '--box' in argv else (104, 80)
    preview = argv[argv.index('--preview') + 1] if '--preview' in argv else None
    build(argv[0], argv[1], variants, box, preview)


if __name__ == '__main__':
    main()
