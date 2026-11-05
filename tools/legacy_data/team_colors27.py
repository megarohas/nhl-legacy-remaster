"""Базовые цвета клуба из NHL 27: exhibitionteams.primarycolor_r/g/b и secondarycolor_r/g/b (меню, табло, интерфейс).

    python tools/legacy_data/team_colors27.py db БАЗА.db [--clubs "A,B"] [--dry-run]   # nhlng.db (draft_roster.db — тоже)
    python tools/legacy_data/team_colors27.py save СЕЙВ [--write] [--clubs "A,B"]      # сохранённый состав (ROSTER …)
    python tools/legacy_data/team_colors27.py show [--clubs "A,B"] [--sheet ФАЙЛ.png]  # сейчас → NHL 27, без записи;
                                                                                       # --sheet — картинка с логотипами

Откуда: game/work/nhl27/db/nhl_game.db, exhibitionteams.feprimarycolor и fesecondarycolor (0xRRGGBB). Так же устроены
цвета клубов НХЛ у EA: у Чикаго в Legacy primary (208, 18, 42) и secondary (35, 31, 32) = #d0122a и #231f20 — ровно
fe-цвета NHL 27 (сверено 03.11.2026). Клуб ищется по названию (без ®, регистра и знаков): Legacy fullname ↔ NHL 27
teamname. Список клубов по умолчанию — team_colors27.json (решение пользователя и координатора 03.11.2026: клубы АХЛ с
формой целиком из NHL 27; у клубов «новый логотип на старой форме» цвета прежние, чтобы совпадали с формой).

Не трогается stockteamcolorstable (палитра клуба): у EA и NHL 27 порядок цветов в ней разный (у Чикаго в NHL 27 первым
идёт чёрный), а на неё ссылаются цвета экипировки — это форма и шлемы, не базовые цвета. Число строк не меняется, сейв не
«damaged». Повтор ничего не меняет; после записи — проверка CRC (сейв — с копией в legacy-data/backup-saves).
"""
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from tdb import SaveFile, Tdb, load_meta  # noqa: E402

SPEC = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'team_colors27.json')
NHL27_DB = os.path.join(ROOT, 'game', 'work', 'nhl27', 'db', 'nhl_game.db')
import legacy_paths as LP  # noqa: E402 (cache: в обеих раскладках, docs/legacy-port.md «Папка content»)
CACHE_META = LP.legacy_file('db/nhlng-meta.xml')
T = 'exhibitionteams'
FIELDS = {'primarycolor': 'feprimarycolor', 'secondarycolor': 'fesecondarycolor'}


def norm(s):
    return ''.join(ch for ch in s.lower() if ch.isalnum())


def colors27(path=NHL27_DB):
    """{название клуба (norm): {'primarycolor': (r, g, b), 'secondarycolor': (r, g, b)}} из NHL 27."""
    db = Tdb(open(path, 'rb').read(), load_meta(os.path.join(os.path.dirname(path), 'nhl_game-meta.xml')))
    out = {}
    for r in db.live_rows(T):
        v = {k: tuple((db.get(T, f, r) >> s) & 255 for s in (16, 8, 0)) for k, f in FIELDS.items()}
        out.setdefault(norm(db.get_string(T, 'teamname', r)), v)
    return out


def clubs(arg):
    if arg:
        return [c.strip() for c in arg.split(',') if c.strip()]
    return json.load(open(SPEC, encoding='utf-8'))['clubs']


def plan(db, names, log=print):
    """[(строка, название, поле, было, стало)] по клубам names; нет клуба в одной из баз — ошибка."""
    c27 = colors27()
    rows = {norm(db.get_string(T, 'fullname', r)): r for r in db.live_rows(T)}
    out, bad = [], []
    for name in names:
        r, src = rows.get(norm(name)), c27.get(norm(name))
        if r is None or src is None:
            bad.append(f'{name}: нет {"в базе Legacy" if r is None else "в NHL 27"}')
            continue
        for k, rgb in src.items():
            old = tuple(db.get(T, f'{k}_{c}', r) for c in 'rgb')
            out.append((r, name, k, old, rgb))
    if bad:
        raise SystemExit('клубы не найдены: ' + '; '.join(bad))
    return out


def apply(db, pl):
    n = 0
    for r, _name, k, old, new in pl:
        if old != new:
            for c, x in zip('rgb', new):
                db.set(T, f'{k}_{c}', r, x)
            n += 1
    return n


def show(pl, log=print):
    for r, name, k, old, new in pl:
        log(f'  {r:3d} {name:28s} {k:15s} {"#%02x%02x%02x" % old} → {"#%02x%02x%02x" % new}'
            + ('' if old != new else '  (так и есть)'))


def cmd_db(paths, dry, names):
    for path in paths:
        meta_p = os.path.join(os.path.dirname(path), 'nhlng-meta.xml')
        meta = load_meta(meta_p if os.path.isfile(meta_p) else CACHE_META)
        db = Tdb(open(path, 'rb').read(), meta)
        if T not in db.by_name:
            print(f'{path}: нет {T} — пропуск')
            continue
        pl = plan(db, names)
        n = apply(db, pl)
        print(f'{path}: цветов изменено {n} из {len(pl)}')
        show(pl)
        if n and not dry:
            db.fix()
            tmp = path + '.part'
            open(tmp, 'wb').write(bytes(db.d))
            if Tdb(open(tmp, 'rb').read(), meta).verify():
                os.remove(tmp)
                sys.exit(f'{path}: CRC не сходятся после записи — база не тронута')
            os.replace(tmp, path)


def cmd_save(save, write, names):
    meta = load_meta(CACHE_META)
    raw = open(save, 'rb').read()
    sf = SaveFile(raw, meta)
    pl = plan(sf.db, names)
    n = apply(sf.db, pl)
    print(f'{save}: цветов изменено {n} из {len(pl)}')
    show(pl)
    if not write or not n:
        print('без --write ничего не записано' if n else 'сейв уже совпадает')
        return
    out = sf.bytes(fix=True)
    assert len(out) == len(raw), 'размер сейва изменился'
    bdir = os.path.join(ROOT, 'game', 'work', 'legacy-data', 'backup-saves',
                        f'{os.path.basename(save)}-colors-{time.strftime("%Y%m%d-%H%M%S")}')
    os.makedirs(bdir, exist_ok=True)
    bak = os.path.join(bdir, os.path.basename(save) + '.bak')
    open(bak, 'wb').write(raw)
    open(save, 'wb').write(out)
    bad = SaveFile(open(save, 'rb').read(), meta).verify()
    if bad:
        open(save, 'wb').write(raw)
        sys.exit(f'проверка не прошла, сейв возвращён: {bad}')
    print(f'записано; CRC и обёртка — OK; копия до правки — {bak}')


def main(argv):
    sys.stdout.reconfigure(encoding='utf-8')
    if not argv or argv[0] not in ('db', 'save', 'show'):
        print(__doc__)
        sys.exit(2)
    rest = argv[1:]
    arg = rest[rest.index('--clubs') + 1] if '--clubs' in rest else None
    sh = rest[rest.index('--sheet') + 1] if '--sheet' in rest else None
    paths = [a for a in rest if not a.startswith('--') and a not in (arg, sh)]
    names = clubs(arg)
    if argv[0] == 'db':
        cmd_db(paths, '--dry-run' in rest, names)
    elif argv[0] == 'save':
        cmd_save(paths[0], '--write' in rest, names)
    else:
        db = Tdb(open(LP.legacy_file('db/nhlng.db'), 'rb').read(),
                 load_meta(CACHE_META))
        pl = plan(db, names)
        show(pl)
        if '--sheet' in rest:
            sheet(db, pl, rest[rest.index('--sheet') + 1])


def sheet(db, pl, out):
    """Картинка: клуб (логотип t<арт> из cache: пользователя, если есть) | сейчас | NHL 27."""
    from PIL import Image, ImageDraw, ImageFont
    try:
        font = ImageFont.truetype('C:/Windows/Fonts/segoeui.ttf', 15)
    except OSError:
        font = ImageFont.load_default()
    rows = {}
    for r, name, k, old, new in pl:
        rows.setdefault((r, name), {})[k] = (old, new)
    H = 70
    im = Image.new('RGB', (760, 30 + H * len(rows)), (24, 24, 28))
    d = ImageDraw.Draw(im)
    d.text((10, 6), 'клуб                                        сейчас (основной, второй)      NHL 27 → станет', fill=(200, 200, 200),
           font=font)
    for i, ((r, name), v) in enumerate(rows.items()):
        y = 30 + i * H
        d.text((10, y + 22), name, fill=(240, 240, 240), font=font)
        for j, k in enumerate(('primarycolor', 'secondarycolor')):
            old, new = v[k]
            d.rectangle([330 + j * 70, y + 8, 390 + j * 70, y + 60], fill=old, outline=(90, 90, 90))
            d.rectangle([560 + j * 70, y + 8, 620 + j * 70, y + 60], fill=new, outline=(90, 90, 90))
    im.save(out)
    print(out, im.size)


if __name__ == '__main__':
    main(sys.argv[1:])
