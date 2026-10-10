"""Слоты клубов АХЛ в базе NHL Legacy (32: 30 клубов EA 2015 года + CV/HSK) → клубы АХЛ 2026/27 из HockeyTech
(кэш game/work/roster-cache/ahl/ht, этап `python -m roster.ahl_ht teams`) → game/work/legacy-data/ahl-2026/slots.json.

Сопоставление (решение координатора 10.10 09:27): тот же клуб остаётся в своём слоте (24), 8 слотов клубов, которых
в 2026/27 нет, получают клуб, который их сменил (переезд/переименование) или занял место аффилиата того же клуба НХЛ.
Аффилиат — клуб НХЛ, у которого клуб АХЛ фарм в 2026/27 (права игроков в prospects; сверено этапом ids).
В файле: слот, artid и artabbr слота (арт не меняется), прежнее и новое название, город, аббревиатура, арена (строка
exhibitionarena, название и город из расписания HockeyTech), логотип 2026/27 (файл кэша и URL), аффилиат.

    python tools/legacy_data/ahl2026_slots.py [DB]          # DB — база с клубами (по умолчанию out-ahl32)
"""
import collections
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from tdb import Tdb  # noqa: E402
from tdb_read import load_meta  # noqa: E402

REPO = os.path.dirname(os.path.dirname(HERE))
W = os.path.join(REPO, 'game', 'work', 'legacy-data')
CACHE = os.path.join(REPO, 'game', 'work', 'roster-cache', 'ahl', 'ht')
OUT = os.path.join(W, 'ahl-2026', 'slots.json')
SEASON_ID = 94
T, A = 'exhibitionteams', 'exhibitionarena'

# слот → (team_id HockeyTech 2026/27, клуб НХЛ — аффилиат 2026/27, почему)
SLOTS = {
    32: (440, 'VAN', 'Albany Devils нет; клуб Ванкувера из Ютики переехал в Абботсфорд (2021)'),
    33: (402, 'EDM', 'тот же клуб'),
    34: (413, 'OTT', 'переезд Binghamton → Belleville (2017)'),
    35: (457, 'NYI', 'переезд Bridgeport → Hamilton (2026)'),
    36: (384, 'FLA', 'тот же клуб; аффилиат CAR → FLA'),
    37: (330, 'CAR', 'тот же клуб; аффилиат STL → CAR'),
    38: (328, 'DET', 'тот же клуб'),
    39: (307, 'NYR', 'тот же клуб'),
    40: (319, 'WSH', 'тот же клуб'),
    41: (389, 'MIN', 'тот же клуб'),
    42: (373, 'CBJ', 'переименование Lake Erie → Cleveland Monsters (2016)'),
    43: (313, 'PHI', 'тот же клуб'),
    44: (321, 'WPG', 'тот же клуб'),
    45: (327, 'NSH', 'тот же клуб'),
    46: (403, 'LAK', 'тот же клуб'),
    47: (411, 'STL', 'переезд Portland → Springfield (2016); аффилиат FLA → STL'),
    48: (309, 'BOS', 'тот же клуб'),
    49: (323, 'BUF', 'тот же клуб'),
    50: (372, 'CHI', 'тот же клуб'),
    51: (415, 'MTL', 'переезд St. John\'s → Laval (2017)'),
    52: (419, 'COL', 'San Antonio Rampage уехали в Хендерсон (у HSK свой слот 225); фарм Колорадо — Colorado Eagles'),
    53: (404, 'ANA', 'тот же клуб'),
    54: (405, 'SJS', 'тот же клуб'),
    55: (412, 'UTA', 'тот же клуб (этап utah: Springfield → Tucson)'),
    56: (444, 'CGY', 'переезд Stockton → Calgary (2022)'),
    57: (324, 'TBL', 'тот же клуб'),
    58: (380, 'DAL', 'тот же клуб'),
    59: (335, 'TOR', 'тот же клуб'),
    60: (390, 'NJD', 'та же марка Utica Comets, другая франшиза; аффилиат VAN → NJD'),
    61: (316, 'PIT', 'тот же клуб'),
    224: (445, 'SEA', 'тот же клуб'),
    225: (437, 'VGK', 'тот же клуб'),
}


def sitekit(d, name):
    kit = (d or {}).get('SiteKit') or {}
    return next((v for k, v in kit.items() if k.lower() == name.lower()), []) or []


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    dbp = sys.argv[1] if len(sys.argv) > 1 else os.path.join(W, 'out-ahl32', 'db', 'nhlng.db')
    db = Tdb(open(dbp, 'rb').read(), load_meta(os.path.join(os.path.dirname(dbp), 'nhlng-meta.xml')))
    clubs = {int(c['id']): c for c in sitekit(json.load(open(os.path.join(CACHE, f'teams-{SEASON_ID}.json'),
                                                            encoding='utf-8')), 'Teamsbyseason')}
    logos = {int(k): v for k, v in json.load(open(os.path.join(CACHE, 'logos.json'), encoding='utf-8')).items()}
    venues = collections.defaultdict(collections.Counter)
    sched = sitekit(json.load(open(os.path.join(CACHE, f'schedule-{SEASON_ID}.json'), encoding='utf-8')), 'Schedule')
    for g in sched:
        venues[int(g['home_team'])][(g.get('venue_name'), g.get('venue_location'))] += 1
    league = {t: db.get(T, 'league', t) for t in range(db.by_name[T]['rows'])}
    ahl_slots = sorted(t for t, lg in league.items() if lg == 1)
    if ahl_slots != sorted(SLOTS) or len(set(v[0] for v in SLOTS.values())) != 32 or set(v[0] for v in SLOTS.values()) \
            != set(clubs):
        sys.exit(f'слоты базы {ahl_slots} или клубы HockeyTech не сходятся с таблицей SLOTS')
    nhl_slot = {}
    from roster.common import TEAM_SLOT          # noqa: E402 (tools/ в sys.path)
    nhl_slot.update(TEAM_SLOT)
    out = []
    for slot in ahl_slots:
        tid, parent, why = SLOTS[slot]
        c = clubs[tid]
        arena = db.get(T, 'arenaid', slot)
        (vname, vloc), _ = venues[tid].most_common(1)[0]
        ext = os.path.splitext(logos[tid])[1] or '.png'
        old_name = db.get_string(T, 'fullname', slot)
        same = why.startswith('тот же клуб') or why.startswith('та же марка')
        out.append({
            'slot': slot, 'artid': db.get(T, 'artid', slot), 'artabbr': db.get_string(T, 'artabbr', slot),
            'old': {'fullname': old_name, 'shortname': db.get_string(T, 'shortname', slot),
                    'abbrname': db.get_string(T, 'abbrname', slot), 'arena_row': arena,
                    'arenaname': db.get_string(A, 'arenaname', arena), 'cityname': db.get_string(A, 'cityname', arena),
                    'affiliate_of': next((a for a, s in nhl_slot.items()
                                          if db.get(T, 'ahlaffiliate', s) - 1 == slot), None)},
            'ht_team_id': tid, 'name': c['name'], 'city': c['city'], 'nickname': c['nickname'], 'code': c['code'],
            'division': c.get('division_long_name'), 'arenaname': vname, 'cityname': vloc,
            'affiliate_of': parent, 'renamed': not same, 'why': why,
            'logo_url': logos[tid], 'logo_file': f'game/work/roster-cache/ahl/ht/logos/{tid}{ext}',
        })
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT + '.part', 'w', encoding='utf-8', newline='\n') as f:
        json.dump({'season': '2026/27', 'ht_season_id': SEASON_ID, 'db': os.path.relpath(dbp, REPO).replace(os.sep, '/'),
                   'slots': out}, f, ensure_ascii=False, indent=1)
    os.replace(OUT + '.part', OUT)
    ren = [s for s in out if s['renamed']]
    aff = [s for s in out if s['old']['affiliate_of'] != s['affiliate_of']]
    print(f'{OUT}: 32 слота, переименований {len(ren)}, смен аффилиата {len(aff)}')
    for s in out:
        flag = ('ПЕРЕИМЕН. ' if s['renamed'] else '') + (f"аффилиат {s['old']['affiliate_of']} → {s['affiliate_of']}"
                                                       if s['old']['affiliate_of'] != s['affiliate_of'] else '')
        print(f"  {s['slot']:3} {s['old']['fullname']:32} → {s['name']:30} ({s['affiliate_of']}) {flag}")


if __name__ == '__main__':
    main()
