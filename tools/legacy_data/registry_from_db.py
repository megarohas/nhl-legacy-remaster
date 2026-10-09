"""artid-registry.json конвейера Legacy (nhl_id → artid) заново — по готовой базе: игрок players.json свежей сборки
сопоставляется со строкой базы (out/db/nhlng.db) по имени и дате рождения, его artid берётся из базы. Нужна после
потери game/work/legacy-data/roster/artid-registry.json (09.10.2026): без неё write раздаст новым игрокам другие artid,
портреты получат другие имена, и out/ разойдётся с тем, что стоит у пользователя.

    python tools/legacy_data/registry_from_db.py PLAYERS.json DB [--meta META] [--out REGISTRY.json]

PLAYERS.json — после `roster build` (сеть: этап fetch); DB — база с прежними artid (по умолчанию out/db/nhlng.db, её
схема рядом). Записываются только artid из диапазона новых игроков (write.ART_MIN…ART_MAX) — у сопоставленных со строками
исходной базы artid и так свои. Отчёт: сопоставлено, не найдено, неоднозначно.
"""
import argparse
import json
import os
import sys
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
os.environ.setdefault('NHL_GAME', 'legacy')
from install_legacy_data import W  # noqa: E402
from tdb import Tdb  # noqa: E402
from tdb_read import load_meta  # noqa: E402


def key(first, last):
    s = unicodedata.normalize('NFKD', f'{first} {last}'.lower())
    return ''.join(c for c in s if c.isalnum())


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('players')
    ap.add_argument('db', nargs='?', default=os.path.join(W, 'out', 'db', 'nhlng.db'))
    ap.add_argument('--meta')
    ap.add_argument('--out', default=os.path.join(W, 'roster', 'artid-registry.json'))
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding='utf-8')
    from roster.write import ART_MAX, ART_MIN
    db = Tdb(open(a.db, 'rb').read(), load_meta(a.meta or os.path.join(os.path.dirname(a.db), 'nhlng-meta.xml')))
    B = 'exhibitionplayerbiotable'
    rows = {}
    for r in db.live_rows(B):
        k = (key(db.get_string(B, 'firstname', r), db.get_string(B, 'lastname', r)),
             db.get(B, 'year', r) + 1900, db.get(B, 'month', r) + 1, db.get(B, 'day', r) + 1)
        rows.setdefault(k, []).append(db.get(B, 'artid', r))
    players = json.load(open(a.players, encoding='utf-8'))['players']
    reg, missing, amb = {}, [], []
    for p in players:
        y, m, d = p['birth']
        arts = rows.get((key(p['first'], p['last']), y, m, d), [])
        arts = sorted({x for x in arts if ART_MIN <= x <= ART_MAX})
        if len(arts) == 1:
            reg[str(p['nhl_id'])] = arts[0]
        elif arts:
            amb.append((p['nhl_id'], f"{p['first']} {p['last']}", arts))
        else:
            missing.append((p['nhl_id'], f"{p['first']} {p['last']}"))
    if os.path.exists(a.out):
        sys.exit(f'{a.out} уже есть — не перезаписываю (перенесите в _stale)')
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    json.dump(dict(sorted(reg.items(), key=lambda kv: int(kv[0]))), open(a.out, 'w', encoding='utf-8'), indent=1)
    print(f'artid из базы: {len(reg)}; без новой строки в базе (сопоставленные с исходной или новые) {len(missing)}; '
          f'неоднозначно {len(amb)} {amb[:3]} → {a.out}')


if __name__ == '__main__':
    main()
