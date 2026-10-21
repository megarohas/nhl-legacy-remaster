"""База NHL 27 (PS5) как источник составов для NHL Legacy: игроки лиг, биография, атрибуты, записи составов.

База — gamemodes/database/t3db/nhl_game.db из дампа (TDB little-endian, `tools/tdb.py` читает её сам). Выгрузка один
раз: `cd tools && FB_GAME=nhl27 python -m fb.lfs get gamemodes/database/t3db/nhl_game.db
../game/work/nhl27/db/nhl_game.db` и то же для nhl_game-meta.xml (docs/frostbite-sources.md §5). Другая папка —
NHL27_DB=путь/к/nhl_game.db (схема — рядом).

Что совпадает с Legacy (сверено 21.10.2026 на McDavid, Demidov, Celebrini, Michkov, Kucherov и юниорах CHL):
- все 53 поля exhibitionplayerbiotable Legacy есть в NHL 27 с той же кодировкой (рост − 54, вес − 120, год − 1900,
  суммы × 5000 $, state/intlcountry — та же шкала кодов, team/proteam — номер + 1);
- все 70 полей exhibitionskaterai Legacy и 37 из 63 exhibitiongoalieai; атрибуты c_* у NHL 27 — как есть 0–99, у
  Legacy — значение − 36 в 6 битах (ratings.BASE); рост (growthtier, growthletter, growthspeed, growthage, growthmod),
  черты trait*, тенденции *bias и стиль — та же схема;
- потенциал разный: NHL 27 c_potential 42 у почти всех и 66 у единиц, Legacy 5 и 30 (у юниоров CHL базы EA 2015
  года — 1233 × 5 и 31 × 30; у NHL 27 — 1279 × 42 и 10 × 66) → POTENTIAL;
- места в звеньях: l*, l4*, pk4_1/2*, pk3_1/2*, s1–s5, x1/x2, g1/g2 — те же имена; большинство pp_N* → ppN*,
  овертайм 4 на 4 ev4_N* → ot_N* (FLAG_MAP); у NHL 27 есть ещё pk4_3*, pk3_3*, ev3_* (3 на 3) — в Legacy их нет;
- клубы НХЛ 0–31 в том же порядке, кроме VGK (30 у NHL 27, 31 у Legacy) и SEA (31 / 30) → NHL_SLOT;
- лиги (stockleagues.leagueid → exhibitionteams.league): у NHL 27 OHL 11, QMJHL 12, WHL 13, у Legacy 9, 10, 11.
"""
import os

from tdb import Tdb, load_meta

from .common import REPO
from .dbview import FLAGS

DB_DEFAULT = os.path.join(REPO, 'game', 'work', 'nhl27', 'db', 'nhl_game.db')
B, S, G = 'exhibitionplayerbiotable', 'exhibitionskaterai', 'exhibitiongoalieai'
P, R, T = 'exhibitionplayers', 'exhibitionrostertable', 'exhibitionteams'
LEAGUES = {'nhl': 0, 'ahl': 1, 'shl': 2, 'liiga': 3, 'del': 4, 'extraliga': 5, 'nl': 6, 'icehl': 7, 'allsvenskan': 8,
           'ohl': 11, 'qmjhl': 12, 'whl': 13, 'echl': 15, 'pwhl': 27}
LEGACY_LEAGUE = {11: 9, 12: 10, 13: 11}           # юниоры: лига NHL 27 → лига Legacy (exhibitionteams.league)
NHL_SLOT = {i: i for i in range(30)} | {30: 31, 31: 30}
POTENTIAL = {42: 5, 66: 30}                         # c_potential NHL 27 → Legacy (прочие — ближайшее)


def legacy_flag(name):
    """Место в звеньях NHL 27 → имя места Legacy (None — такого места в Legacy нет)."""
    if name.startswith('pp_'):
        name = 'pp' + name[3:]                       # pp_1c → pp1c
    elif name.startswith('ev4_'):
        name = 'ot_' + name[4:]                      # ev4_1c → ot_1c (овертайм 4 на 4 в Legacy)
    return name if name in FLAGS else None


def open_db(path=None):
    path = path or os.environ.get('NHL27_DB') or DB_DEFAULT
    meta = os.path.join(os.path.dirname(path), 'nhl_game-meta.xml')
    if not (os.path.exists(path) and os.path.exists(meta)):
        raise SystemExit(f'нет базы NHL 27 {path} (и схемы рядом): выгрузка — tools/roster/nhl27.py, docstring')
    return Tdb(open(path, 'rb').read(), load_meta(meta))


def values(db, table, row, fields=None):
    """{поле: значение как его видит игра (с rangelow)} — строки текстом."""
    return {f: db.value(table, f, row) for f in (fields or db.by_name[table]['fields'])}


def teams(db, league_ids):
    """{строка exhibitionteams: {'abbr', 'name', 'city', 'league'}} команд этих лиг."""
    out = {}
    for t in db.live_rows(T):
        lg = db.get(T, 'league', t)
        if lg in league_ids:
            out[t] = {'abbr': db.get_string(T, 'abbrname', t), 'name': db.get_string(T, 'teamname', t),
                      'city': db.get_string(T, 'cityname', t), 'nick': db.get_string(T, 'nickname', t), 'league': lg}
    return out


def players(db, league_ids):
    """Игроки составов команд этих лиг: [{'team', 'bio', 'ai', 'ai_table', 'entry'}] — значения полей как есть
    (bio — все поля биографии, ai — атрибуты своей таблицы, entry — запись exhibitionrostertable)."""
    tm = teams(db, league_ids)
    link = {db.get(P, 'index', r): db.get(P, 'playerid', r) for r in db.live_rows(P)}
    bio_row = {db.get(B, 'game_id', r): r for r in db.live_rows(B)}
    ai_row = {}
    for t in (S, G):
        for r in db.live_rows(t):
            ai_row[db.get(t, 'game_id', r)] = (t, r)
    out = []
    for r in db.live_rows(R):
        team = db.get(R, 'team', r)
        if team not in tm:
            continue
        gid = link.get(db.get(R, 'playerindex', r))
        if gid not in bio_row or gid not in ai_row:
            continue
        t, ar = ai_row[gid]
        out.append({'team': team, 'club': tm[team], 'game_id': gid, 'bio': values(db, B, bio_row[gid]),
                    'ai_table': t, 'ai': values(db, t, ar), 'entry': values(db, R, r)})
    return out
