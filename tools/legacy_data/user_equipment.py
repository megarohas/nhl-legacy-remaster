"""Правки экипировки, сделанные пользователем в игре (редактор игрока), → базы сборки: выгрузка из сейва ROSTER и
применение. Этап build-all «useredits» (после ahl, до nhl24).

    python tools/legacy_data/user_equipment.py extract НОВЫЙ_СЕЙВ ПРЕДЫДУЩИЙ_СЕЙВ [--out ПАПКА] [--meta СХЕМА.xml]
        снимок всех полей экипировки полевых и вратарей (по game_id) и список отличий от предыдущего сейва —
        «<сейв> — экипировка.json» и «<сейв> — правки.json» в ПАПКЕ (по умолчанию game/work/legacy-data/
        equipment-user); схема — nhlng-meta.xml сборки (out-ahl32/db, иначе out/db)
    python tools/legacy_data/user_equipment.py [apply] БАЗА.db [БАЗА.db …] [--dry-run]
        правки из equipment-user/*правки.json (по порядку имён; в каждом edits: table, game_id, field, old, new) →
        базы. Значение ставится, если в базе сейчас old (база до правки) или уже new; другое значение — конфликт,
        строка не трогается и попадает в отчёт. Повтор ничего не меняет.

Сейв ROSTER — файл внутри папки сейва порта (userdata/<профиль>/454109EC/00000001/ROSTER …/ROSTER …); предыдущий —
сейв до правок в игре (тот, что был установлен со сборкой). Выгрузка раньше жила разовым скриптом
game/work/legacy-data/tmp/equip_from_save.py (до 20.10.2026).
"""
import argparse
import glob
import json
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from tdb import SaveFile, Tdb, load_meta  # noqa: E402

W = os.environ.get('LEGACY_DATA_WORK', os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), 'game', 'work', 'legacy-data'))
EDITS = os.path.join(W, 'equipment-user')
BIO = 'exhibitionplayerbiotable'
TABLES = ('exhibitionskaterequipment', 'exhibitiongoalieequipment')


def default_meta():
    for v in ('out-ahl32', 'out'):
        p = os.path.join(W, v, 'db', 'nhlng-meta.xml')
        if os.path.isfile(p):
            return p
    return None


def snapshot(path, meta):
    """Сейв ROSTER → ({таблица: {game_id: {поле: значение}}}, {game_id: имя})."""
    db = SaveFile(open(path, 'rb').read(), meta).db
    names = {db.get(BIO, 'game_id', r): f"{db.get_string(BIO, 'firstname', r)} {db.get_string(BIO, 'lastname', r)}"
             .strip() for r in db.live_rows(BIO)}
    out = {}
    for t in TABLES:
        fields = [f for f in db.by_name[t]['fields'] if f != 'game_id']
        out[t] = {str(db.get(t, 'game_id', r)): {f: db.get(t, f, r) for f in fields} for r in db.live_rows(t)}
    return out, names


def cmd_extract(new, prev, out_dir, meta_path):
    meta_path = meta_path or default_meta()
    if not meta_path or not os.path.isfile(meta_path):
        sys.exit('нет схемы nhlng-meta.xml (соберите out или укажите --meta)')
    for p in (new, prev):
        if not os.path.isfile(p):
            sys.exit(f'нет файла сейва: {p} (нужен файл ROSTER внутри папки сейва)')
    meta = load_meta(meta_path)
    snap, names = snapshot(new, meta)
    old, _ = snapshot(prev, meta)
    edits, per = [], Counter()
    for t in TABLES:
        for g, vals in snap[t].items():
            was = old[t].get(g)
            if was is None:
                continue
            for f, v in vals.items():
                if was.get(f) != v:
                    edits.append({'table': t, 'game_id': int(g), 'name': names.get(int(g), ''), 'field': f,
                                  'old': was.get(f), 'new': v})
                    per[f] += 1
    os.makedirs(out_dir, exist_ok=True)
    stem = os.path.basename(new)
    with open(os.path.join(out_dir, f'{stem} — экипировка.json'), 'w', encoding='utf-8') as f:
        json.dump({'save': new, 'names': {str(k): v for k, v in names.items()}, 'equipment': snap}, f,
                  ensure_ascii=False)
    with open(os.path.join(out_dir, f'{stem} — правки.json'), 'w', encoding='utf-8') as f:
        json.dump({'save': new, 'prev': prev, 'edits': edits}, f, ensure_ascii=False, indent=1)
    players = Counter(e['name'] for e in edits)
    print('полей экипировки:', {t: len(next(iter(snap[t].values()))) for t in TABLES if snap[t]})
    print('правок против предыдущего сейва:', len(edits), 'у игроков:', len(players))
    print('по полям:', dict(per.most_common()))
    print('игроки:', ', '.join(f'{n} ({c})' for n, c in players.most_common(40)))
    print('→', out_dir)


def load_edits():
    out = []
    for p in sorted(glob.glob(os.path.join(EDITS, '*правки.json'))):
        out += json.load(open(p, encoding='utf-8'))['edits']
    return out


def apply(path, edits, dry):
    meta = os.path.join(os.path.dirname(path), 'nhlng-meta.xml')
    if not os.path.isfile(meta):        # у накладок (out-nhl24*) схемы рядом нет — она та же, что у out-ahl32
        meta = os.path.join(W, 'out-ahl32', 'db', 'nhlng-meta.xml')
    db = Tdb(open(path, 'rb').read(), load_meta(meta))
    index, done, same, conflict, missing = {}, 0, 0, [], 0
    for e in edits:
        t = e['table']
        if t not in db.by_name:
            missing += 1
            continue
        if t not in index:
            index[t] = {db.get(t, 'game_id', r): r for r in db.live_rows(t)}
        r = index[t].get(e['game_id'])
        if r is None:
            missing += 1
            continue
        cur = db.get(t, e['field'], r)
        if cur == e['new']:
            same += 1
        elif cur == e['old']:
            db.set(t, e['field'], r, e['new'])
            done += 1
        else:
            conflict.append(f"{e['name']} {e['field']}: в базе {cur}, было {e['old']}, у пользователя {e['new']}")
    print(f'{path}: записано {done}, уже так {same}, конфликтов {len(conflict)}, нет в базе {missing}')
    for c in conflict[:20]:
        print('  конфликт:', c)
    if done and not dry:
        db.fix()
        tmp = path + '.part'
        open(tmp, 'wb').write(bytes(db.d))
        if Tdb(open(tmp, 'rb').read(), load_meta(meta)).verify():
            os.remove(tmp)
            sys.exit(f'{path}: CRC не сходятся после записи — база не тронута')
        os.replace(tmp, path)
    return done, conflict


def main(argv):
    if argv and argv[0] == 'extract':
        ap = argparse.ArgumentParser(prog='user_equipment.py extract', description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
        ap.add_argument('new', help='сейв ROSTER с правками пользователя')
        ap.add_argument('prev', help='сейв ROSTER до правок')
        ap.add_argument('--out', default=EDITS)
        ap.add_argument('--meta', default=None)
        a = ap.parse_args(argv[1:])
        return cmd_extract(a.new, a.prev, a.out, a.meta)
    if argv and argv[0] == 'apply':
        argv = argv[1:]
    if not argv or argv[0] in ('-h', '--help'):
        sys.exit(__doc__)
    dry = '--dry-run' in argv
    paths = [a for a in argv if a != '--dry-run']
    edits = load_edits()
    if not edits:
        print(f'правок экипировки нет ({EDITS})')
        return
    print(f'правок экипировки: {len(edits)} ({EDITS})')
    for p in paths:
        apply(p, edits, dry)


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main(sys.argv[1:])
