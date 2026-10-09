"""Листы на проверку пользователю: «Аризона сейчас | Юта» — логотипы интерфейса и 3D, центр льда, свитера на модели
Legacy (спереди и сзади, tools/fb/kit3d.render), превью формы в меню. Только чтение: EA — из распакованных архивов
Legacy, наше — из OUTDIR (раскладка cache:). Картинки — в game/work/utah/compare (не в git).

    python tools/utah/sheets.py logos OUTDIR OUT.png [--old 22] [--new 104] [--spot-old 22] [--spot-new 48]
    python tools/utah/sheets.py center OUTDIR OUT.png [--old 22] [--new 104]
    python tools/utah/sheets.py kits OUTDIR OUT.png NEW_KIT[=подпись]… [--old OLD_KIT=подпись…]
    python tools/utah/sheets.py fe OUTDIR OUT.png NEW_KIT[=подпись]… [--old OLD_KIT=подпись…]
    python tools/utah/sheets.py ui OUTDIR OUT.png [--old 22] [--new 104]
    (NEW_KIT можно как ПАПКА@S_A_V — комплект из другой папки сборки; --sample 9,KELLER,C — пример номера на листе kits)
"""
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
sys.path.insert(0, TOOLS)
import teamart as ta        # noqa: E402
import kitpaint as kp       # noqa: E402

BG = (34, 36, 42)
FG = (232, 234, 238)
DIM = (150, 156, 166)


def font(size, bold=False):
    for f in (('segoeuib.ttf' if bold else 'segoeui.ttf'), 'arial.ttf'):
        try:
            return ImageFont.truetype(os.path.join(r'C:\Windows\Fonts', f), size)
        except OSError:
            pass
    return ImageFont.load_default()


def checker(w, h, a=(70, 74, 82), b=(86, 90, 98), cell=8):
    y, x = np.mgrid[0:h, 0:w]
    m = ((x // cell + y // cell) % 2).astype(bool)
    out = np.zeros((h, w, 3), np.uint8)
    out[~m] = a
    out[m] = b
    return Image.fromarray(out)


def on_checker(im, bg=None):
    im = im.convert('RGBA')
    base = (bg.copy() if bg is not None else checker(*im.size)).convert('RGBA')
    base.alpha_composite(im)
    return base.convert('RGB')


def load_rel(root, rel):
    """Картинка файла: root=None — EA (архивы Legacy), иначе — файл из дерева root."""
    if root is None:
        data = kp._unchunk(open(ta.GAME.extracted(rel), 'rb').read())
    else:
        data = open(os.path.join(root, *rel.split('/')), 'rb').read()
    if rel.endswith('.big'):
        obj = ta.UiLogo(data, rel)
        w, h, px = obj.decode()
        sw, sh = obj.stage
        return Image.frombytes('RGBA', (w, h), bytes(px)).crop((0, 0, sw, sh))
    obj = ta.Rw4(data, rel)
    t = obj.textures[0]
    w, h, px = obj.decode(t, 0)
    return Image.frombytes('RGBA', (w, h), bytes(px))


def fit(im, w, h):
    k = min(w / im.width, h / im.height)
    return im.resize((max(1, int(im.width * k)), max(1, int(im.height * k))), Image.LANCZOS)


def grid_sheet(title, cols, rows, out, cell=(220, 220), note=''):
    """rows — [(подпись строки, [картинка | None, …])], cols — подписи столбцов."""
    cw, ch = cell
    lw = 250
    W = lw + cw * len(cols) + 20
    H = 70 + (28 if note else 0) + 30 + (ch + 16) * len(rows) + 10
    sheet = Image.new('RGB', (W, H), BG)
    d = ImageDraw.Draw(sheet)
    d.text((16, 14), title, fill=FG, font=font(26, True))
    y = 56
    if note:
        d.text((16, y), note, fill=DIM, font=font(15))
        y += 28
    for i, c in enumerate(cols):
        d.text((lw + i * cw + 6, y), c, fill=DIM, font=font(16))
    y += 30
    for label, ims in rows:
        lines = label.split(' (', 1)
        if len(lines) == 2:
            lines[1] = '(' + lines[1]
        for i, ln in enumerate(lines):
            d.text((16, y + ch // 2 - 12 * len(lines) + 24 * i), ln, fill=FG, font=font(17, True))
        for i, im in enumerate(ims):
            if im is None:
                continue
            t = on_checker(fit(im, cw - 12, ch - 12))
            sheet.paste(t, (lw + i * cw + (cw - t.width) // 2, y + (ch - t.height) // 2))
        y += ch + 16
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    sheet.save(out)
    print(out, sheet.size)


def cmd_logos(outdir, out, old=22, new=104, spot_old=22, spot_new=48, title=None, ahl=False, labels=None):
    sets = [('t', 'teamlogos/t{}.big'), ('s', 'teamlogossmall/s{}.big'), ('d', 'teamlogosdynasty/d{}.big'),
            ('c', 'teamlogoscalendar/c{}.big'), ('w', 'teamlogoswide/w{}.big')]
    if not ahl:
        sets.append(('r', 'teamlogosreflection/r{}.big'))
    rx = [('шайба', 'rendering/puck/puck_{}_cm.rx2'), ('баннер', 'rendering/banner/banner_{}_cm.rx2'),
          ('центр льда', 'rendering/icesurface/centerlogo_{}_cm.rx2')]
    cols = [k for k, _ in sets] + [k for k, _ in rx] + ([] if ahl else ['прожектор'])
    rows = []
    la, lb = labels or (f'сейчас (арт {old})', f'Юта (арт {new})')
    for label, root, n, sp in ((la, None, old, spot_old), (lb, outdir, new, spot_new)):
        ims = []
        for _, pat in sets:
            ims.append(load_rel(root, 'fe/ion/artassets/' + pat.format(n)))
        for _, pat in rx:
            ims.append(load_rel(root, pat.format(n)))
        if not ahl:
            ims.append(load_rel(root, f'rendering/spotlight/texlib_{sp}.rx2'))
        rows.append((label, ims))
    grid_sheet(title or 'Логотипы: Arizona Coyotes (EA, Legacy) → Utah Mammoth', cols, rows, out, cell=(190, 210),
               note='t — основной, s — «таблетка», d — франшиза, c — календарь, w — крупный план' +
                    ('' if ahl else ', r — с отражением') + '; шайба, баннер, центр льда' +
                    ('' if ahl else ', прожектор') + ' — 3D')


def cmd_center(outdir, out, old=22, new=104):
    a = load_rel(None, f'rendering/icesurface/centerlogo_{old}_cm.rx2')
    b = load_rel(outdir, f'rendering/icesurface/centerlogo_{new}_cm.rx2')
    ice = Image.new('RGBA', a.size, (214, 220, 226, 255))
    red = Image.new('RGBA', (36, a.size[1]), (200, 30, 40, 255))
    tiles = []
    for im in (a, b):
        base = ice.copy()
        base.paste(red, (494, 0))
        base.alpha_composite(im)
        tiles.append(base.convert('RGB').resize((640, 640), Image.LANCZOS))
    W, H = 640 * 2 + 60, 640 + 110
    sheet = Image.new('RGB', (W, H), BG)
    d = ImageDraw.Draw(sheet)
    d.text((16, 14), 'Центр льда (1024², формат Legacy): Arizona сейчас | Utah Mammoth', fill=FG, font=font(26, True))
    d.text((16, 52), f'centerlogo_{old}_cm (EA) → centerlogo_{new}_cm; под прозрачной полосой — красная линия, '
                     'вокруг — лёд (для вида)', fill=DIM, font=font(15))
    for i, t in enumerate(tiles):
        sheet.paste(t, (20 + i * 660, 90))
    sheet.save(out)
    print(out, sheet.size)


def kit_cm(root, kit):
    rel = kit.path('jersey')
    data = kp._unchunk(open(ta.GAME.extracted(rel), 'rb').read()) if root is None else \
        open(os.path.join(root, *rel.split('/')), 'rb').read()
    rw = ta.Rw4(data, rel)
    t = next(x for x in rw.textures if kp.layer_name(x.name) == 'jersey_cm')
    w, h, px = kp.tex_decode(rw, t, 0)
    return np.frombuffer(bytes(px), np.uint8).reshape(h, w, 4).astype(np.float64)


def kit_layer(root, kit, kind, layer):
    rel = kit.path(kind)
    data = kp._unchunk(open(ta.GAME.extracted(rel), 'rb').read()) if root is None else         open(os.path.join(root, *rel.split('/')), 'rb').read()
    rw = ta.Rw4(data, rel)
    t = next(x for x in rw.textures if kp.layer_name(x.name) == layer)
    return kp.Img(*kp.tex_decode(rw, t, 0))


def stamped(root, kit, sample):
    """Развёртка свитера с примером номера, фамилии и буквы капитана (czkit.stamp_sample по карте name_*_cm и атласу
    шрифта комплекта) — только для листа: в игре их ставит шейдер."""
    import czkit
    cm = kit_layer(root, kit, 'jersey', 'jersey_cm')
    font = kit_layer(root, kit, 'jersey', 'font_cm')
    nmap = kit_layer(root, kit, 'name', 'name_cm')
    img = czkit.stamp_sample(cm, font, nmap, str(sample.get('number', '9')), sample.get('name', ''),
                             sample.get('captain'))
    return np.frombuffer(bytes(img.px), np.uint8).reshape(img.h, img.w, 4).astype(np.float64)


def cmd_kits(outdir, out, new, old, title=None, sample=None):
    from fb import kit3d, kit_hybrid
    mesh, _ = kit_hybrid.legacy_with_shirt()
    H = 430
    W = int(round(H * (kit3d.FRAME[1] - kit3d.FRAME[0]) / (kit3d.FRAME[3] - kit3d.FRAME[2])))
    items = [(None, k, lab) for k, lab in old] + [(*_root(outdir, k), lab) for k, lab in new]
    rows = []
    for root, k, lab in items:
        kit = kp.Kit.parse(k)
        tex = stamped(root, kit, sample) if sample and root is not None else kit_cm(root, kit)
        rows.append((lab, [kit3d.render(mesh, tex, 'front', W, ss=2), kit3d.render(mesh, tex, 'back', W, ss=2)]))
    pad = 14
    sw = (W + pad) * 4 + pad
    nrow = (len(rows) + 1) // 2
    sh = 70 + nrow * (H + 44) + pad
    sheet = Image.new('RGB', (sw, sh), BG)
    d = ImageDraw.Draw(sheet)
    d.text((16, 14), title or 'Свитера на модели Legacy стиля 1 (спереди и сзади)', fill=FG, font=font(26, True))
    for i, (lab, ims) in enumerate(rows):
        x = pad + (i % 2) * 2 * (W + pad)
        y = 64 + (i // 2) * (H + 44)
        d.text((x, y), lab, fill=FG, font=font(17, True))
        for j, im in enumerate(ims):
            sheet.paste(im, (x + j * (W + pad), y + 30))
    sheet.save(out)
    print(out, sheet.size)


def cmd_fe(outdir, out, new, old, title=None):
    items = [(None, k, lab) for k, lab in old] + [(*_root(outdir, k), lab) for k, lab in new]
    ims = []
    for root, k, lab in items:
        kit = kp.Kit.parse(k)
        ims.append((lab, load_rel(root, kit.path('fe'))))
    cw, ch = 300, 330
    W = 20 + cw * len(ims)
    sheet = Image.new('RGB', (W, ch + 110), BG)
    d = ImageDraw.Draw(sheet)
    d.text((16, 14), title or 'Превью формы в меню (Select Jerseys), поза EA', fill=FG, font=font(26, True))
    for i, (lab, im) in enumerate(ims):
        t = on_checker(im.resize((256, 256), Image.LANCZOS), Image.new('RGB', (256, 256), (58, 62, 70)))
        sheet.paste(t, (20 + i * cw, 70))
        d.text((20 + i * cw, 70 + 262), lab, fill=FG, font=font(15))
    sheet.save(out)
    print(out, sheet.size)


def cmd_ui(outdir, out, old=22, new=104, font_kits=('1_104_0', '1_104_1')):
    """Мелкий арт интерфейса и шлема: фон карточки, значок ленты новостей, цифра меню, наклейка на шлем, атлас шрифта."""
    def ui(root, rel):
        try:
            return load_rel(root, rel)
        except Exception:
            return None
    cols = ['фон карточки (pb)', 'значок ленты (twittericonsteam)', 'цифра меню (tn)', 'наклейка на шлем (logo)',
            'атлас номеров (дом)', 'атлас номеров (выезд)']
    rows = []
    for label, root, n, kits, hl in ((f'Аризона сейчас (EA, арт {old})', None, old, ('1_22_3', '1_22_4'), '1_3'),
                                     (f'Юта (арт {new})', outdir, new, font_kits, '1_0')):
        ims = [ui(root, f'fe/ion/artassets/playerbackgrounds/pb_{n}.big'),
               ui(root, f'fe/ion/artassets/twittericonsteam/t{n}.big'),
               ui(root, f'fe/ion/artassets/teamnumbers/tn{n}_9.big'),
               ui(root, f'rendering/logo/texlib_{n}_{hl}.rx2')]
        for k in kits:
            kit = kp.Kit.parse(k)
            img = kit_layer(root, kit, 'jersey', 'font_cm')
            ims.append(Image.frombytes('RGBA', (img.w, img.h), bytes(img.px)))
        rows.append((label, ims))
    grid_sheet('Интерфейс и шлем: Arizona Coyotes (EA) → Utah Mammoth', cols, rows, out, cell=(300, 300),
               note='pb — фон карточки игрока, значок — лента новостей, tn — цифра шрифтом клуба для меню, наклейка — '
                    'на шлем (helmetlogo 1); атлас номеров — раскладка EA, свой квадратный шрифт с наклоном 10°')


def _pairs(args):
    """«S_A_V=подпись» или «ПАПКА@S_A_V=подпись» (комплект из другой папки сборки)."""
    out = []
    for a in args:
        k, _, lab = a.partition('=')
        out.append((k, lab or k.split('@')[-1]))
    return out


def _root(default, k):
    if '@' in k:
        d, k = k.split('@', 1)
        return d, k
    return default, k


def main():
    game, argv = ta.split_game(sys.argv[1:])
    ta.set_game(game)
    if len(argv) < 3:
        sys.exit(__doc__)
    cmd, outdir, out = argv[0], argv[1], argv[2]
    rest = argv[3:]

    def opt(name, default):
        return int(rest[rest.index(name) + 1]) if name in rest else default
    if cmd == 'logos':
        title = rest[rest.index('--title') + 1] if '--title' in rest else None
        labels = tuple(rest[rest.index('--labels') + 1].split('|')) if '--labels' in rest else None
        cmd_logos(outdir, out, opt('--old', 22), opt('--new', 104), opt('--spot-old', 22), opt('--spot-new', 48),
                  title, '--ahl' in rest, labels)
    elif cmd == 'center':
        cmd_center(outdir, out, opt('--old', 22), opt('--new', 104))
    elif cmd == 'ui':
        cmd_ui(outdir, out, opt('--old', 22), opt('--new', 104))
    elif cmd in ('kits', 'fe'):
        if '--old' in rest:
            i = rest.index('--old')
            new, old = rest[:i], rest[i + 1:]
        else:
            new, old = rest, []
        sample = None
        if '--sample' in rest:                               # номер,фамилия,буква: 9,KELLER,C
            i = rest.index('--sample')
            num, name, cap = (rest[i + 1].split(',') + ['', ''])[:3]
            sample = {'number': num, 'name': name, 'captain': cap or None}
            rest = rest[:i] + rest[i + 2:]
            if '--old' in rest:
                j = rest.index('--old')
                new, old = rest[:j], rest[j + 1:]
            else:
                new, old = rest, []
        if cmd == 'kits':
            cmd_kits(outdir, out, _pairs(new), _pairs(old), sample=sample)
        else:
            cmd_fe(outdir, out, _pairs(new), _pairs(old))
    else:
        sys.exit(__doc__)


if __name__ == '__main__':
    main()
