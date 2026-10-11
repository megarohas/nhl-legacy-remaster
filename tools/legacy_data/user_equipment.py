"""Правки экипировки пользователя (сделаны в игре, выгружены из его сейва ROSTER — game/work/legacy-data/tmp/
equip_from_save.py) → базы сборки и cache:. Файлы правок: game/work/legacy-data/equipment-user/*правки.json
(по порядку имён; в каждом edits: table, game_id, field, old, new).

Значение ставится, если в базе сейчас old (база до правки) или уже new; другое значение — конфликт, строка не
трогается и попадает в отчёт. Повторный запуск ничего не меняет. Этап build-all «useredits» (после ahl, до nhl24).

    python tools/legacy_data/user_equipment.py БАЗА.db [БАЗА.db …] [--dry-run]
"""
import glob
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from tdb import Tdb, load_meta  # noqa: E402

W = os.environ.get('LEGACY_DATA_WORK', os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), 'game', 'work', 'legacy-data'))
EDITS = os.path.join(W, 'equipment-user')


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
    main(sys.argv[1:])
