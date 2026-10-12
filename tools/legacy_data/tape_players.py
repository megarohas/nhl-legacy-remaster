"""Обмотка крюка игрокам по решению пользователя (tools/legacy_data/tape_players.json) и подписи вариантов обмотки в
меню экипировки. Этап build-all «tape» (после useredits: решение пользователя главнее его прежних правок обмотки).

    python tools/legacy_data/tape_players.py db БАЗА.db [БАЗА.db …] [--dry-run]   # nhlng.db, draft_roster.db
    python tools/legacy_data/tape_players.py loc NHL_ENG_US.db [… ] [--dry-run]    # подписи вариантов (fe/loc)
    python tools/legacy_data/tape_players.py save СЕЙВ [--write]                   # сохранённый состав (ROSTER …)

db: игрок — по фамилии и дате рождения (exhibitionplayerbiotable, живые строки; ровно одна строка, не вратарь),
sticktapecolor ставится во всех таблицах экипировки полевых, где есть поле и строка с его game_id
(exhibitionskaterequipment, leagueskaterequipment); вратарские таблицы не трогаются. Повторный запуск ничего не
меняет. После записи — проверка CRC (иначе база не тронута).

loc: подпись кода — текст ключа его цвета (tools/tapestyles.py LABELS: red → «White Middle» и т. д.), своей строкой
в конец пула (locdb put): чужие ключи с тем же текстом («Red» у TEAMLINE2_PRSA) не меняются.

save: то же, что db, в сейве состава пользователя (обёртка ZlibV4, как tools/legacy_data/save_sync_ratings.py);
без --write — только отчёт. С --write — копия сейва в game/work/legacy-data/backup-saves, после записи — проверка CRC
и обёртки, при ошибке сейв возвращается.
"""
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from tdb import SaveFile, Tdb, load_meta  # noqa: E402

SPEC = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tape_players.json')
W = os.environ.get('LEGACY_DATA_WORK', os.path.join(ROOT, 'game', 'work', 'legacy-data'))
LOC_META = os.path.join(ROOT, 'game', 'other', 'legacy', 'big', 'cacheboot', 'fe', 'loc', 'nhl_eng_us-meta.xml')
CACHE_META = os.path.join(ROOT, 'legacy-port', 'userdata', 'cache', 'guest', 'db', 'nhlng-meta.xml')
BIO = 'exhibitionplayerbiotable'
FIELD = 'sticktapecolor'


def spec():
    return json.load(open(SPEC, encoding='utf-8'))['players']


def skater_tables(db):
    return [t for t, d in db.by_name.items()
            if FIELD in d['fields'] and 'game_id' in d['fields'] and 'goalie' not in t]


def apply(db, label):
    """Обмотка игрокам спецификации в базе db → (изменено значений, строки отчёта, ошибки)."""
    bio = {}
    for r in db.live_rows(BIO):
        key = (db.get_string(BIO, 'lastname', r).lower(),
               (db.get(BIO, 'year', r) + 1900, db.get(BIO, 'month', r) + 1, db.get(BIO, 'day', r) + 1))
        bio.setdefault(key, []).append(r)
    tables = {t: {db.get(t, 'game_id', r): r for r in db.live_rows(t)} for t in skater_tables(db)}
    changed, lines, errors = 0, [], []
    for p in spec():
        rows = bio.get((p['last'].lower(), tuple(p['birth'])), [])
        who = f"{p['first']} {p['last']} {p['birth'][0]}-{p['birth'][1]:02}-{p['birth'][2]:02}"
        if len(rows) != 1:
            errors.append(f'{who}: строк био {len(rows)} (нужна одна)')
            continue
        r = rows[0]
        if db.get(BIO, 'position', r) == 4:
            errors.append(f'{who}: вратарь — не трогаю')
            continue
        gid = db.get(BIO, 'game_id', r)
        first = db.get_string(BIO, 'firstname', r)
        parts = []
        for t, idx in tables.items():
            er = idx.get(gid)
            if er is None:
                continue
            old = db.get(t, FIELD, er)
            if old != p[FIELD]:
                db.set(t, FIELD, er, p[FIELD])
                changed += 1
            parts.append(f'{t} {old} → {p[FIELD]}' if old != p[FIELD] else f'{t} уже {old}')
        if not parts:
            errors.append(f'{who} (game_id {gid}): нет строк экипировки полевого')
            continue
        lines.append(f'  {first} {p["last"]} (game_id {gid}): ' + '; '.join(parts)
                     + ('' if first.lower() == p['first'].lower() else f' (в спецификации имя {p["first"]})'))
    return changed, lines, errors


def meta_for(path):
    m = os.path.join(os.path.dirname(path), 'nhlng-meta.xml')
    if not os.path.isfile(m):           # у накладок (out-nhl24*) схемы рядом нет — она та же, что у out-ahl32
        m = os.path.join(W, 'out-ahl32', 'db', 'nhlng-meta.xml')
    return load_meta(m)


def cmd_db(paths, dry):
    bad = 0
    for path in paths:
        meta = meta_for(path)
        db = Tdb(open(path, 'rb').read(), meta)
        changed, lines, errors = apply(db, path)
        print(f'{path}: изменено значений {changed}, ошибок {len(errors)}')
        for s in lines + [f'  ОШИБКА: {e}' for e in errors]:
            print(s)
        bad += len(errors)
        if changed and not dry:
            db.fix()
            tmp = path + '.part'
            open(tmp, 'wb').write(bytes(db.d))
            if Tdb(open(tmp, 'rb').read(), meta).verify():
                os.remove(tmp)
                sys.exit(f'{path}: CRC не сходятся после записи — база не тронута')
            os.replace(tmp, path)
    if bad:
        sys.exit(f'ошибок: {bad}')


def cmd_loc(paths, dry):
    import locdb
    import tapestyles
    for path in paths:
        loc = locdb.LocDb(open(path, 'rb').read(), load_meta(LOC_META))
        done = 0
        for code, (key, text) in sorted(tapestyles.LABELS.items()):
            found = loc.find_all(key)
            cur = loc.text(loc.text_off_at(found[0])) if found else None
            if cur == text:
                print(f'  {code}: {key} уже «{text}»')
                continue
            loc.put(key, text)
            done += 1
            print(f'  {code}: {key} «{cur}» → «{text}»')
        bad = loc.check()
        if bad:
            sys.exit(f'{path}: не записано — ошибки локализации: ' + '; '.join(bad))
        print(f'{path}: подписей изменено {done}')
        if done and not dry:
            loc.db.fix()
            open(path, 'wb').write(loc.db.d)


def cmd_save(save, write):
    meta = load_meta(CACHE_META)
    raw = open(save, 'rb').read()
    sf = SaveFile(raw, meta)
    changed, lines, errors = apply(sf.db, save)
    print(f'{save}: изменено значений {changed}, ошибок {len(errors)}')
    for s in lines + [f'  ОШИБКА: {e}' for e in errors]:
        print(s)
    if errors:
        sys.exit('есть ошибки — сейв не трогаю')
    if not write or not changed:
        print('без --write ничего не записано' if changed else 'сейв уже совпадает')
        return
    out = sf.bytes(fix=True)
    assert len(out) == len(raw), 'размер сейва изменился'
    bdir = os.path.join(ROOT, 'game', 'work', 'legacy-data', 'backup-saves',
                        f'{os.path.basename(save)}-{time.strftime("%Y%m%d-%H%M%S")}')
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
    if not argv or argv[0] not in ('db', 'loc', 'save'):
        print(__doc__)
        sys.exit(2)
    cmd, rest = argv[0], argv[1:]
    flags = {a for a in rest if a.startswith('--')}
    paths = [a for a in rest if not a.startswith('--')]
    if cmd == 'db':
        cmd_db(paths, '--dry-run' in flags)
    elif cmd == 'loc':
        cmd_loc(paths, '--dry-run' in flags)
    else:
        cmd_save(paths[0], '--write' in flags)


if __name__ == '__main__':
    main(sys.argv[1:])
