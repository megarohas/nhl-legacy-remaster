"""Листы «Legacy сейчас | новый» для пользователя: логотипы клубов, как их показывает игра (разбор готовых .big/.rx2).

    venv/python tools/logos/sheets.py nhl OUT.png [--sets t,s] [--new DIR] [--now DIR] [--title "…"]
    venv/python tools/logos/sheets.py more OUT.png [--new DIR]       # остальные наборы: d, c, w, r, баннер,
                                                                    # прожектор, pb, значок ленты (для проверки)

«Сейчас» — то, что стоит у клуба сейчас: файлы EA из архивов Legacy (у Юты — Аризона, арт 22: Юта пользователю ещё не
ставилась), у SEA/VGK/UTA — наш арт из game/work/legacy-data/out. «Новый» — DIR (по умолчанию game/work/logos/out-nhl),
у клубов с "keep" — тот же наш арт. Рисунок — PIL (шрифт Segoe UI), фон — тёмный, как меню Legacy."""
import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
ROOT = os.path.dirname(TOOLS)
sys.path.insert(0, TOOLS)
import teamart as ta   # noqa: E402

LOGOS = os.environ.get('LOGOS_WORK', os.path.join(ROOT, 'game', 'work', 'logos'))
OURS = os.path.join(ROOT, 'game', 'work', 'legacy-data', 'out')
BG = (34, 38, 44)
PANEL = (48, 54, 62)
TEXT = (232, 234, 237)
DIM = (160, 168, 178)
UIDIR = {'t': 'teamlogos/t', 's': 'teamlogossmall/s', 'd': 'teamlogosdynasty/d', 'c': 'teamlogoscalendar/c',
         'w': 'teamlogoswide/w', 'r': 'teamlogosreflection/r', 'pb': 'playerbackgrounds/pb_', 'tw': 'twittericonsteam/t'}


def font(size, bold=False):
    for f in (('segoeuib.ttf' if bold else 'segoeui.ttf'), 'arial.ttf'):
        try:
            return ImageFont.truetype(os.path.join('C:/Windows/Fonts', f), size)
        except OSError:
            continue
    return ImageFont.load_default()


def ui_path(root, kind, num):
    rel = f'fe/ion/artassets/{UIDIR[kind]}{num}.big'
    if root is None:
        try:
            return ta.extracted(rel)
        except SystemExit:
            return None
    p = os.path.join(root, *rel.split('/'))
    return p if os.path.exists(p) else None


def rx_path(root, kind, num):
    rel = {'banner': f'rendering/banner/banner_{num}_cm.rx2', 'spot': f'rendering/spotlight/texlib_{num}.rx2'}[kind]
    if root is None:
        try:
            return ta.extracted(rel)
        except SystemExit:
            return None
    p = os.path.join(root, *rel.split('/'))
    return p if os.path.exists(p) else None


def decode_ui(path):
    if not path:
        return None
    data = open(path, 'rb').read()
    if data[:8] in (b'chunklzx', b'chunkzip'):
        import unchunk
        data = unchunk.unchunk(data)
    lg = ta.UiLogo(data, path)
    w, h, px = lg.decode()
    sw, sh = lg.stage
    a = np.frombuffer(bytes(px), np.uint8).reshape(h, w, 4)[:sh, :sw]
    return Image.fromarray(a.copy(), 'RGBA')


def decode_rx(path):
    if not path:
        return None
    rw = ta.Rw4.load(path)
    t = rw.textures[0]
    w, h, px = rw.decode(t, 0)
    return Image.fromarray(np.frombuffer(bytes(px), np.uint8).reshape(h, w, 4).copy(), 'RGBA')


def on_bg(img, size, color=PANEL, nearest=False):
    """Картинка на фоне панели, вписана в size (ширина, высота) с сохранением пропорций."""
    W, H = size
    out = Image.new('RGBA', (W, H), color + (255,))
    if img is None:
        d = ImageDraw.Draw(out)
        d.text((W // 2, H // 2), 'нет файла', fill=DIM + (255,), font=font(16), anchor='mm')
        return out
    k = min(W / img.width, H / img.height)
    im = img.resize((max(1, round(img.width * k)), max(1, round(img.height * k))),
                    Image.NEAREST if nearest and k >= 1 else Image.LANCZOS)
    out.alpha_composite(im, ((W - im.width) // 2, (H - im.height) // 2))
    return out


def club_rows_ahl():
    """Клубы АХЛ 2026/27 по слотам legacy-data (build.load_clubs('ahl')): «сейчас» — арт слота у EA (клуб 2015/16), у
    CV/HSK/TUC — наш арт из out legacy-data."""
    sys.path.insert(0, HERE)
    import build as B
    rows = []
    for c in sorted(B.load_clubs('ahl'), key=lambda c: c['name']):
        if 131 <= c['artid'] <= 165:
            now = (None, c['artid'], None, f"EA, арт {c['artid']}" + (f" — {c['old']}" if c.get('old') and c['old'] != c['name'] else ''))
        else:
            now = (OURS, c['artid'], None, f"наш арт {c['artid']}")
        rows.append((c, now))
    return rows


def club_rows():
    clubs = json.load(open(os.path.join(HERE, 'clubs.json'), encoding='utf-8'))['nhl']
    rows = []
    for c in sorted(clubs, key=lambda c: c['abbr']):
        if c['abbr'] == 'UTA':
            now = (None, 22, 22, 'Arizona Coyotes (EA, арт 22) — Юта ещё не поставлена')
        elif c.get('keep'):
            now = (OURS, c['artid'], c['spotlight'], f"наш арт {c['artid']}")
        else:
            now = (None, c['artid'], c['spotlight'], f"EA, арт {c['artid']}")
        rows.append((c, now))
    return rows


def sheet_nhl(out, new_root, sets=('t', 's'), title=None, rows=None):
    rows = rows or club_rows()
    f_h, f_l, f_s = font(30, True), font(19, True), font(14)
    cell_w, cell_h = 830, 340
    cols = 2
    nrows = (len(rows) + cols - 1) // cols
    head = 92
    S = Image.new('RGBA', (cols * cell_w + 30, head + nrows * cell_h + 20), BG + (255,))
    d = ImageDraw.Draw(S)
    d.text((20, 14), title or 'Логотипы клубов НХЛ 2026/27 в NHL Legacy: сейчас | новый', fill=TEXT + (255,), font=f_h)
    d.text((20, 56), 'В каждой клетке: основной логотип t (256×256) — сейчас и новый; справа «таблетка» s (128×64, ×2) — '
                     'сверху сейчас, снизу новый. Фон — как тёмное меню игры.', fill=DIM + (255,), font=f_s)
    for i, (c, now) in enumerate(rows):
        x0 = 15 + (i % cols) * cell_w
        y0 = head + (i // cols) * cell_h
        d.rounded_rectangle([x0, y0, x0 + cell_w - 15, y0 + cell_h - 14], 10, fill=(28, 31, 36, 255))
        nroot, nart, nspot, nlabel = now
        keep = c.get('keep')
        new_dir = OURS if keep else new_root
        label = f"{c['name']} ({c['abbr']}) · арт {c['artid']}"
        d.text((x0 + 12, y0 + 6), label, fill=TEXT + (255,), font=f_l)
        src = 'логотип АХЛ 2026/27 (HockeyTech)' if c.get('league') == 'ahl' else 'официальный SVG НХЛ 2026/27'
        sub = f"сейчас: {nlabel} · новый: " + ('тот же, уже нынешний' if keep else src)
        d.text((x0 + 12, y0 + 32), sub, fill=DIM + (255,), font=f_s)
        t_now = decode_ui(ui_path(nroot, 't', nart))
        t_new = decode_ui(ui_path(new_dir, 't', c['artid']))
        s_now = decode_ui(ui_path(nroot, 's', nart))
        s_new = decode_ui(ui_path(new_dir, 's', c['artid']))
        S.alpha_composite(on_bg(t_now, (256, 256)), (x0 + 10, y0 + 54))
        S.alpha_composite(on_bg(t_new, (256, 256)), (x0 + 272, y0 + 54))
        S.alpha_composite(on_bg(s_now, (256, 128), nearest=True), (x0 + 540, y0 + 54))
        S.alpha_composite(on_bg(s_new, (256, 128), nearest=True), (x0 + 540, y0 + 182))
        for (xx, yy, txt) in ((x0 + 14, y0 + 292, 'сейчас'), (x0 + 276, y0 + 292, 'новый'),
                              (x0 + 544, y0 + 164, 's сейчас'), (x0 + 544, y0 + 292, 's новый')):
            d.text((xx, yy), txt, fill=DIM + (255,), font=f_s)
    S.convert('RGB').save(out, optimize=True)
    print(f'{out}: {S.width}×{S.height}')


def sheet_more(out, new_root):
    rows = [r for r in club_rows() if not r[0].get('keep') or r[0].get('extra')]
    f_h, f_l, f_s = font(28, True), font(17, True), font(13)
    kinds = [('d', 'd 128²'), ('c', 'c 98×86'), ('w', 'w 256²'), ('r', 'r 256×512'), ('banner', 'баннер'),
             ('spot', 'прожектор'), ('pb', 'фон карточки pb'), ('tw', 'значок ленты')]
    box = 150
    cell_w = 18 + len(kinds) * (box + 8)
    cell_h = 2 * (box + 6) + 40
    head = 70
    S = Image.new('RGBA', (cell_w + 20, head + len(rows) * cell_h), BG + (255,))
    d = ImageDraw.Draw(S)
    d.text((16, 12), 'Остальные наборы по artid: сейчас (верхний ряд) | новый (нижний ряд)', fill=TEXT + (255,), font=f_h)
    for i, (c, now) in enumerate(rows):
        y0 = head + i * cell_h
        nroot, nart, nspot, nlabel = now
        new_dir = new_root
        d.text((16, y0 + 4), f"{c['name']} ({c['abbr']}) · арт {c['artid']} · сейчас: {nlabel}", fill=TEXT + (255,), font=f_l)
        for k, (kind, cap) in enumerate(kinds):
            x = 16 + k * (box + 8)
            if kind in ('banner', 'spot'):
                a = decode_rx(rx_path(nroot, kind, nspot if kind == 'spot' else nart))
                b = decode_rx(rx_path(new_dir, kind, c['spotlight'] if kind == 'spot' else c['artid']))
            else:
                a = decode_ui(ui_path(nroot, kind, nart))
                b = decode_ui(ui_path(new_dir, kind, c['artid']))
            S.alpha_composite(on_bg(a, (box, box)), (x, y0 + 28))
            S.alpha_composite(on_bg(b, (box, box)), (x, y0 + 34 + box))
            d.text((x + 2, y0 + 28 + 2), cap, fill=DIM + (255,), font=f_s)
    S.convert('RGB').save(out, optimize=True)
    print(f'{out}: {S.width}×{S.height}')


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    args = sys.argv[1:]

    def opt(name, default):
        if name in args:
            i = args.index(name)
            v = args[i + 1]
            del args[i:i + 2]
            return v
        return default
    new_root = opt('--new', os.path.join(LOGOS, 'out-ahl' if args and args[0] == 'ahl' else 'out-nhl'))
    title = opt('--title', None)
    ta.set_game('legacy')
    kind, out = args[0], args[1]
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    if kind == 'nhl':
        sheet_nhl(out, new_root, title=title)
    elif kind == 'ahl':
        sheet_nhl(out, new_root, rows=club_rows_ahl(),
                  title=title or 'Логотипы клубов АХЛ 2026/27 в NHL Legacy: сейчас | новый')
    elif kind == 'more':
        sheet_more(out, new_root)
    else:
        sys.exit(__doc__)


if __name__ == '__main__':
    main()
