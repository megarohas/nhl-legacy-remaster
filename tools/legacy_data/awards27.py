"""История наград и Кубка Стэнли из базы NHL 27 → NHL Legacy (stockawardstable в out и out-ahl32): этап build-all «awards».

Просьба пользователя 23.10.2026: на экранах трофеев (Previous Winners, награды сезона) — настоящая история наград НХЛ
(Кубок Стэнли, Hart, Vezina, Norris, Calder, Art Ross, Rocket Richard, Conn Smythe, Selke, Lady Byng, Ted Lindsay, Jack
Adams…), АХЛ и CHL до сезона 2025/26 (у мода сезон 2026/27). У EA в базе Legacy — только 2010/11…2014/15.

    python tools/legacy_data/awards27.py                       # проба (ничего не пишет): out и out-ahl32, отчёт
    python tools/legacy_data/awards27.py --write               # запись; копия базы и схемы — legacy-data/awards27/backup/
    python tools/legacy_data/awards27.py out-ahl32 --write     # только накладка «АХЛ на 32»
    python tools/legacy_data/awards27.py --show 2025           # победители сезона 2025/26 так, как их увидит игра
    python tools/legacy_data/awards27.py --awards              # номера наград (awardid) и названия
    python tools/legacy_data/awards27.py --from 2005 --leagues nhl --write   # только НХЛ с 2005/06 (прочее в таблице — как было)

Откуда.
- База NHL 27 (PS5, tools/roster/nhl27.py: game/work/nhl27/db/nhl_game.db, NHL27_DB=путь): stockawardstable той же схемы,
  что у Legacy (+ teamartid), 1 707 строк: НХЛ 1996/97…2025/26 (2004/05 — локаут, наград нет), Calder Cup АХЛ с 1999/2000,
  все награды АХЛ и CHL (OHL, QMJHL, WHL) с 2008/09. Номера наград (awardid), лиг (league: 0 НХЛ, 6 АХЛ, 12 WHL, 13 OHL,
  14 QMJHL) и года (year = первый год сезона − 1899: 126 — 2025/26) — как у Legacy: сверено на 2010/11…2014/15, где есть обе.
- Правки — tools/legacy_data/awards_fix.json (только общеизвестные факты): у NHL 27 до 2003/04 перепутаны St. Louis и San
  Jose; Jennings 1996/97 и 1998/99 с одним вратарём дважды; нет King Clancy 2007/08, у King Clancy 2017/18 один Седин;
  Calder Cup 2000/01 — «Anaheim Ducks»; прежние названия клубов-победителей (Mighty Ducks of Anaheim 2002/03, Calder Cup
  Philadelphia Phantoms, Hamilton Bulldogs, Binghamton Senators); клубы, которых больше нет (team_alias, row_teams);
  сезоны 1994/95 и 1995/96 НХЛ, которых нет в NHL 27. --no-fix — без правок.

Как игра это читает (Legacy, разбор кода 23.10.2026). Победитель награды A в сезоне Y — 82BB01C8: Y < 2015 (порт
сдвигает на season_year, хук NhlLegacyYearCmpS2015) — запрос к stockawardstable базы cache:\\db\\nhlng.db «year = Y − 1899,
awardid = A» (82BADD90: поля lastname, firstname, team; первая подходящая строка), иначе — leagueawardstable франшизы
(год сезона франшизы, 0 — первый). Несколько победителей (Jennings, ничьи Rocket Richard) — 82BAE238: те же условия, по
порядку index, ещё playerartid, jerseynumber, playerid. Если firstname и lastname пусты, подпись берётся из клуба team
(829C9280) — у командных наград NHL 27 там город и имя клуба, они и пишутся. Поэтому:
- stockawardstable нет ни в сейве ROSTER, ни в сейве франшизы (savegroups пусто; в сейве франшизы только
  leagueawardstable — награды, разыгранные во франшизе): новая история видна сразу после установки базы, в том числе в
  старых франшизах, сейвы не меняются;
- team — номер строки exhibitionteams Legacy (с нуля): клуб NHL 27 → слот Legacy (НХЛ — roster.nhl27.NHL_SLOT, прочие — по
  аббревиатуре, названию, городу; у базы без CV/HSK их игроки — под клубом НХЛ, чей это фарм-клуб); клубы, которых нет, —
  через team_alias (слот того же клуба после переезда); у НХЛ клуб -1 — Phoenix/Arizona → Utah (22);
- playerid / playerartid — game_id и artid этого человека в нашей базе (имя + дата рождения из биографии NHL 27, иначе
  только имя — если такой один и возраст в том сезоне правдоподобен: AGES), не нашли — -1 (как у EA в 2010/11…2012/13).

Запись. Таблица собирается заново: строки NHL 27 и правок за выбранные сезоны (--from…--to; по умолчанию все, до сезона
перед tools/season.py YEAR), строки базы вне этих сезонов и группы (сезон, лига, награда), которых нет в NHL 27, остаются
(--prune — убрать всё вне --from…--to). Порядок — сезон, лига (НХЛ, АХЛ, OHL, QMJHL, WHL), порядок NHL 27; index — номер
строки. У Legacy index — 9 бит (до 512 строк): если строк больше, поле расширяется до 11 бит, как у NHL 27 (tdb.widen,
запись 60 → 64 байта), и в nhlng-meta.xml рядом (depth 11, rangehigh 2047). Строки длиннее 24 байт UTF-8 обрезаются.
Повтор с теми же параметрами ничего не меняет. draft_roster.db наград не содержит — не пересобирается.
Отчёт — game/work/legacy-data/awards27/<out|out-ahl32>.json. Документация — docs/awards.md.
"""
import argparse
import json
import os
import re
import shutil
import sys
import time
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
REPO = os.path.dirname(TOOLS)
sys.path.insert(0, TOOLS)
os.environ['NHL_GAME'] = 'legacy'
from roster.common import set_game  # noqa: E402
set_game('legacy')
import season  # noqa: E402
from roster import nhl27  # noqa: E402
from roster.common import TEAM_ALIAS, TEAM_SLOT, fit_utf8, norm  # noqa: E402
from tdb import Tdb, load_meta  # noqa: E402

W_DIR = os.path.abspath(os.environ.get('LEGACY_DATA_WORK') or os.path.join(REPO, 'game', 'work', 'legacy-data'))
WORK = os.path.join(W_DIR, 'awards27')
FIX = os.path.join(HERE, 'awards_fix.json')
EA_DB = os.path.join(REPO, 'game', 'other', 'legacy', 'big', 'cacheboot', 'db', 'nhlng.db')   # база EA: прежние названия
A, B, T = 'stockawardstable', 'exhibitionplayerbiotable', 'exhibitionteams'
YEAR0 = 1899                                     # year в таблице = первый год сезона − 1899 (82BADD90: addi r4,r28,-1899)
LEAGUES = {'nhl': 0, 'ahl': 6, 'whl': 12, 'ohl': 13, 'qmjhl': 14}
LEAGUE_NAME = {v: k for k, v in LEAGUES.items()}
LEAGUE_ORDER = {0: 0, 6: 1, 13: 2, 14: 3, 12: 4}
TEAM_LEAGUE_LEGACY = {0: 0, 6: 1, 13: 9, 14: 10, 12: 11}    # лига награды → exhibitionteams.league у Legacy
TEAM_LEAGUE_27 = {0: 0, 1: 1, 11: 9, 12: 10, 13: 11}        # exhibitionteams.league NHL 27 → Legacy
TEAM_AWARD_MAX = 33                              # awardid 0…33 — командные (НХЛ 0/1/8/9, АХЛ 10–19, CHL 20–33)
COACH_AWARDS = {43}                              # Jack Adams — тренер
INDEX_WIDE = 11                                  # ширина index у NHL 27 (до 2048 строк)
NAME_BYTES = 24                                  # строки 200 бит: 24 байта UTF-8 + 0
# сопоставление только по имени: возраст в том сезоне (год сезона − год рождения) — у юниоров CHL 15…21, иначе тёзка
# (Tyler Johnson 1990 г. р. — не вратарь OHL 2017/18)
AGES = {0: (18, 45), 6: (17, 42), 12: (15, 21), 13: (15, 21), 14: (15, 21)}
AWARDS = {
    0: 'Stanley Cup', 1: "Presidents' Trophy", 8: 'Clarence S. Campbell Bowl (Запад)',
    9: 'Prince of Wales Trophy (Восток)', 34: 'Art Ross Trophy', 35: 'Hart Memorial Trophy',
    36: 'James Norris Memorial Trophy', 37: 'Lady Byng Memorial Trophy', 38: 'Calder Memorial Trophy',
    39: 'Conn Smythe Trophy', 40: 'Vezina Trophy', 41: 'William M. Jennings Trophy', 42: 'Bill Masterton Memorial Trophy',
    43: 'Jack Adams Award', 44: 'Frank J. Selke Trophy', 45: 'Ted Lindsay Award (до 2010 — Lester B. Pearson)',
    46: 'Maurice "Rocket" Richard Trophy', 88: 'King Clancy Memorial Trophy', 10: 'Calder Cup (АХЛ)',
}
for _a, _what in ((range(11, 20), 'АХЛ, командная'), (range(20, 24), 'QMJHL, командная'), (range(24, 32), 'OHL, командная'),
                  (range(32, 34), 'WHL, командная'), (range(47, 57), 'АХЛ, личная'), (range(57, 68), 'QMJHL, личная'),
                  (range(68, 79), 'OHL, личная'), (range(79, 88), 'WHL, личная')):
    for _i in _a:
        AWARDS.setdefault(_i, f'{_what} №{_i}')


def season_of(year):
    return year + YEAR0


def nhl_abbr_slot(abbr):
    a = TEAM_ALIAS.get(abbr, abbr)
    return TEAM_SLOT.get(a)


# --- источник: NHL 27 + правки ----------------------------------------------------------------------------------------
def rows_nhl27(N):
    """Строки stockawardstable NHL 27: [{year, league, awardid, firstname, lastname, jerseynumber, pid27, team27, seq}]."""
    out = []
    for r in N.live_rows(A):
        v = {f: N.value(A, f, r) for f in N.by_name[A]['fields']}
        out.append({'year': v['year'], 'league': v['league'], 'awardid': v['awardid'], 'firstname': v['firstname'],
                    'lastname': v['lastname'], 'jerseynumber': v['jerseynumber'], 'pid27': v['playerid'],
                    'team27': v['team'], 'seq': v['index'], 'src': 'nhl27'})
    return out


def clubs27(N):
    """{номер клуба NHL 27: {abbr, city, name, nick, league, affiliate}} — nick: имя без города (Blues)."""
    out = {}
    for r in N.live_rows(T):
        city, name = N.get_string(T, 'cityname', r), N.get_string(T, 'teamname', r)
        out[N.get(T, 'index', r)] = {
            'abbr': N.get_string(T, 'abbrname', r), 'city': city, 'name': name, 'league': N.get(T, 'league', r),
            'nick': name[len(city):].strip() if name.startswith(city) else name,
            'affiliate': N.value(T, 'ahlaffiliate', r) if 'ahlaffiliate' in N.by_name[T]['fields'] else None}
    return out


def apply_fixes(rows, fix, c27, rep):
    """Правки awards_fix.json по строкам NHL 27 (на месте) → новый список."""
    if not fix:
        return rows
    slot27 = {nhl27.NHL_SLOT[i]: i for i in range(32)}           # слот Legacy → клуб NHL 27 (НХЛ)
    for sw in fix.get('swap_teams', []):
        lg, until = LEAGUES[sw['league']], sw['until']
        a, b = (slot27[nhl_abbr_slot(x)] for x in sw['teams'])
        n = 0
        for r in rows:
            if r['src'] == 'nhl27' and r['league'] == lg and season_of(r['year']) <= until and r['team27'] in (a, b):
                old, new = (a, b) if r['team27'] == a else (b, a)
                r['team27'] = new
                if r['pid27'] < 0 and (r['firstname'], r['lastname']) == (c27[old]['city'], c27[old]['nick']):
                    r['firstname'], r['lastname'] = c27[new]['city'], c27[new]['nick']      # командная награда
                n += 1
        rep['fixes'].append(f"{'/'.join(sw['teams'])} до {until}/{(until + 1) % 100:02d}: {n} строк")
    nt = fix.get('nhl_no_team')
    if nt:
        for r in rows:
            if r['league'] == 0 and r['team27'] < 0 and not r.get('team_hint'):
                r['team_hint'] = nt['team']
    for rt in fix.get('row_teams', []):
        if 'season' not in rt:
            continue
        key = (rt['season'] - YEAR0, LEAGUES[rt['league']], rt['award'])
        hit = [r for r in rows if (r['year'], r['league'], r['awardid']) == key and norm(r['lastname']) == norm(rt['last'])]
        if len(hit) != 1:
            rep['fix_misses'].append(f"row_teams {rt}: строк {len(hit)}")
        for r in hit:
            r['team_hint'] = rt['team']
    groups = defaultdict(list)
    for r in rows:
        groups[(r['year'], r['league'], r['awardid'])].append(r)
    for g in fix.get('groups', []):
        if 'season' not in g:
            continue
        key = (g['season'] - YEAR0, LEAGUES[g['league']], g['award'])
        old = groups.get(key, [])
        seq = min((r['seq'] for r in old), default=None)
        groups[key] = [{'year': key[0], 'league': key[1], 'awardid': key[2], 'firstname': w['first'], 'lastname': w['last'],
                        'jerseynumber': w.get('number', -1), 'pid27': -1, 'team27': -1, 'team_hint': w['team'],
                        'seq': seq, 'src': 'fix'} for w in g['winners']]
        rep['fixes'].append(f"{g['season']}/{(g['season'] + 1) % 100:02d} {g['league']} {AWARDS.get(g['award'], g['award'])}: "
                            + ('замена' if old else 'добавлено') + (f" ({g['why']})" if g.get('why') else ''))
    return [r for rs in groups.values() for r in rs]


# --- сопоставление с базой Legacy -------------------------------------------------------------------------------------
class Teams:
    """Клуб строки награды → строка exhibitionteams Legacy (номер с нуля)."""

    def __init__(self, L, c27, alias, E=None):
        self.L, self.c27, self.alias = L, c27, alias
        self.rows = {}
        for r in L.live_rows(T):
            self.rows[r] = {'league': L.get(T, 'league', r), 'abbr': L.get_string(T, 'abbrname', r),
                            'full': norm(L.get_string(T, 'fullname', r)), 'city': norm(L.get_string(T, 'shortname', r)),
                            'ea': norm(E.get_string(T, 'fullname', r)) if E and r < E.by_name[T]['rows'] else ''}
        self.parent = {c['affiliate']: i for i, c in c27.items() if c['league'] == 0 and i < 32 and c['affiliate'] is not None}

    def _one(self, rows):
        return rows[0] if len(rows) == 1 else None

    def club27(self, t27):
        """Клуб NHL 27 → слот Legacy его лиги (аббревиатура, название, город), иначе None."""
        c = self.c27.get(t27)
        if c is None:
            return None
        if c['league'] == 0:
            return nhl27.NHL_SLOT.get(t27)
        lg = TEAM_LEAGUE_27.get(c['league'])
        same = [r for r, x in self.rows.items() if x['league'] == lg]
        # сначала название: аббревиатуры у EA между играми разные (CHA у NHL 27 — Chicago Wolves, у Legacy — Charlotte)
        for test in (lambda x: x['full'] == norm(c['name']),
                     lambda x: x['abbr'] == c['abbr'] and x['city'] == norm(c['city']),
                     lambda x: x['city'] == norm(c['city'])):
            hit = self._one([r for r in same if test(self.rows[r])])
            if hit is not None:
                return hit
        return None

    def _named(self, field, k, league):
        hits = [r for r, x in self.rows.items() if x[field] == k]
        pref = [r for r in hits if league is None or self.rows[r]['league'] == league]
        return self._one(pref) if pref else self._one(hits)

    def by_name(self, name, league=None, depth=0):
        """Полное название клуба → слот: нынешнее (сначала своя лига), потом team_alias (слот клуба после переезда),
        в последнюю очередь — строка, где клуб был в базе EA 2015 года (слот мог уйти другому клубу: у San Antonio
        Rampage теперь Colorado Eagles — поэтому после team_alias). 'skip' — клуб в team_alias с null (слота нет)."""
        k = norm(name)
        hit = self._named('full', k, league)
        if hit is not None:
            return hit
        for a, b in self.alias.items():
            if not a.startswith('_') and norm(a) == k:
                if b is None:
                    return 'skip'
                hit = self.by_name(b, league, depth + 1) if depth < 3 else None
                if hit is None:                          # преемника нет в этой базе (HSK/CV без --ahl32) — клуб НХЛ
                    hit = next((nhl27.NHL_SLOT[self.parent[i]] for i, c in self.c27.items()
                                if norm(c['name']) == norm(b) and i in self.parent), None)
                if hit is not None:
                    return hit
        return self._named('ea', k, league)

    def resolve(self, r):
        """(слот или None, как): 'nhl27', 'name', 'hint', 'parent', 'skip'."""
        lg = TEAM_LEAGUE_LEGACY[r['league']]
        hint = r.get('team_hint')
        if hint:
            s = nhl_abbr_slot(hint) if hint.isupper() and len(hint) <= 4 else self.by_name(hint, lg)
            return (None, 'skip') if s == 'skip' else (s, 'hint')
        if r['team27'] >= 0:
            s = self.club27(r['team27'])
            if s is not None:
                return s, 'nhl27'
            c = self.c27.get(r['team27'])
            s = self.by_name(c['name'], lg) if c else None            # переименованный / переехавший — team_alias
            if s == 'skip':
                return None, 'skip'
            if s is not None:
                return s, 'name'
        if r['awardid'] <= TEAM_AWARD_MAX and (r['firstname'] or r['lastname']):
            s = self.by_name(f"{r['firstname']} {r['lastname']}", lg)
            if s == 'skip':
                return None, 'skip'
            if s is not None:
                return s, 'name'
        c = self.c27.get(r['team27'])
        if c is not None and r['team27'] in self.parent:                # фарм-клуб, которого нет в этой базе
            return nhl27.NHL_SLOT[self.parent[r['team27']]], 'parent'
        return None, 'none'


class People:
    """Победитель → (game_id, artid) нашей базы: имя + дата рождения (биография NHL 27), иначе только имя."""

    def __init__(self, L, N):
        self.bio27 = {}
        for r in N.live_rows(B):
            self.bio27[N.value(B, 'game_id', r)] = (N.get_string(B, 'firstname', r), N.get_string(B, 'lastname', r),
                                                    N.value(B, 'year', r), N.value(B, 'month', r), N.value(B, 'day', r))
        self.dob, self.name = defaultdict(list), defaultdict(list)
        for r in L.live_rows(B):
            f, l = norm(L.get_string(B, 'firstname', r)), norm(L.get_string(B, 'lastname', r))
            if not l:
                continue
            x = (L.value(B, 'game_id', r), L.value(B, 'artid', r))
            y = L.value(B, 'year', r)
            self.dob[(f, l, y, L.value(B, 'month', r), L.value(B, 'day', r))].append(x)
            self.name[(f, l)].append(x + ((y, L.value(B, 'month', r), L.value(B, 'day', r)),))

    def resolve(self, r):
        if r['awardid'] <= TEAM_AWARD_MAX or r['awardid'] in COACH_AWARDS:
            return None, 'team'
        b = self.bio27.get(r['pid27']) if r['pid27'] >= 0 else None
        if b and norm(b[1]) != norm(r['lastname']):     # номер у EA занят другим человеком (23.10 таких нет из 756)
            b = None
        if b:
            hit = self.dob.get((norm(b[0]), norm(b[1])) + b[2:], [])
            if len(hit) == 1:
                return hit[0], 'dob'
        season = season_of(r['year'])
        names = {(norm(r['firstname']), norm(r['lastname']))} | ({(norm(b[0]), norm(b[1]))} if b else set())
        lo, hi = AGES.get(r['league'], (17, 45))
        cands = {x[:2]: x for k in names for x in self.name.get(k, [])
                 if lo <= season - (x[2][0] + 1900) <= hi and (not b or x[2] == b[2:])}
        if len(cands) == 1:
            return next(iter(cands)), 'name'
        return None, 'none'


# --- запись -----------------------------------------------------------------------------------------------------------
def legacy_rows(L):
    out = []
    for r in L.live_rows(A):
        v = {f: L.value(A, f, r) for f in L.by_name[A]['fields']}
        out.append(v)
    return out


def build(L, N, fix, c27, lo, hi, leagues, prune, E=None):
    """Строки новой таблицы (значения полей Legacy) и отчёт."""
    rep = {'fixes': [], 'fix_misses': [], 'skipped': [], 'team': Counter(), 'player': Counter(), 'kept': Counter()}
    src = [r for r in rows_nhl27(N) if r['league'] in leagues]
    src = apply_fixes(src, fix, c27, rep)
    src = [r for r in src if lo <= season_of(r['year']) <= hi and r['league'] in leagues]
    teams, people = Teams(L, c27, (fix or {}).get('team_alias', {}), E), People(L, N)
    new, groups = [], set()
    for r in src:
        slot, how = teams.resolve(r)
        rep['team'][how] += 1
        if slot is None:
            rep['skipped'].append(f"{season_of(r['year'])} {LEAGUE_NAME[r['league']]} {AWARDS.get(r['awardid'])}: "
                                  f"{r['firstname']} {r['lastname']} (клуб NHL 27 {r['team27']}, {r.get('team_hint') or how})")
            continue
        if how == 'parent':
            rep['skipped'].append(f"{season_of(r['year'])} {LEAGUE_NAME[r['league']]} {AWARDS.get(r['awardid'])}: "
                                  f"{r['firstname']} {r['lastname']} — под клубом НХЛ {slot} (фарм-клуба нет в базе)")
        ids, phow = people.resolve(r)
        rep['player'][phow] += 1
        gid, art = ids if ids else (-1, -1)
        groups.add((r['year'], r['league'], r['awardid']))
        new.append({'team': slot, 'awardid': r['awardid'], 'year': r['year'], 'league': r['league'],
                    'firstname': fit_utf8(r['firstname'], NAME_BYTES), 'lastname': fit_utf8(r['lastname'], NAME_BYTES),
                    'jerseynumber': r['jerseynumber'] if -1 <= r['jerseynumber'] <= 126 else -1,
                    'playerid': gid if 0 <= gid <= 16382 else -1, 'playerartid': art if 0 <= art <= 16382 else -1,
                    '_seq': r['seq'], '_src': r['src']})
    # строки базы: вне сезонов (без --prune) и группы, которых в источнике нет
    for v in legacy_rows(L):
        s = season_of(v['year'])
        inside = lo <= s <= hi and v['league'] in leagues
        if (v['year'], v['league'], v['awardid']) in groups or (prune and not inside):
            continue
        v = dict(v, _seq=None, _src='base')
        v.pop('index', None)
        rep['kept'][f"{s}/{(s + 1) % 100:02d}"] += 1
        new.append(v)
    gseq = {}
    for v in new:
        k = (v['year'], v['league'], v['awardid'])
        if v['_seq'] is not None:
            gseq[k] = min(gseq.get(k, v['_seq']), v['_seq'])
    for i, v in enumerate(new):
        k = (v['year'], v['league'], v['awardid'])
        v['_key'] = (v['year'], LEAGUE_ORDER.get(v['league'], 9), gseq.get(k, 10 ** 6 + v['awardid']), k, i)
    new.sort(key=lambda v: v['_key'])
    for i, v in enumerate(new):
        v['index'] = i
    return new, rep


def patch_meta(path, width):
    """nhlng-meta.xml: stockawardstable.index — depth width, rangehigh 2^width − 1. True — файл изменён."""
    text = open(path, encoding='utf-8', newline='').read()
    m = re.search(r'<table name="%s".*?</table>' % A, text, re.S)
    if not m:
        raise SystemExit(f'{path}: нет таблицы {A}')
    block, k = re.subn(r'(<field name="index"[^>]*?)depth="\d+"([^>]*?)rangehigh="\d+"',
                       lambda f: f.group(1) + f'depth="{width}"' + f.group(2) + f'rangehigh="{(1 << width) - 1}"',
                       m.group(0))
    if k != 1:
        raise SystemExit(f'{path}: у {A} не найдено поле index')
    new = text[:m.start()] + block + text[m.end():]
    if new == text:
        return False
    open(path + '.part', 'w', encoding='utf-8', newline='').write(new)
    os.replace(path + '.part', path)
    return True


def write_table(L, rows):
    t = L.by_name[A]
    need = max(9, (len(rows) - 1).bit_length())
    width = t['fields']['index'][1]
    if need > width:
        if need > INDEX_WIDE:
            raise SystemExit(f'{len(rows)} строк: index шире {INDEX_WIDE} бит не делаю (у NHL 27 — {INDEX_WIDE})')
        L.widen(A, ['index'], INDEX_WIDE)
    L.resize(A, len(rows))
    t = L.by_name[A]
    zero = bytes(t['reclen'])
    for i, v in enumerate(rows):
        L.put_record(A, i, zero)
        for f, (_, w) in t['fields'].items():
            if t['kinds'].get(f) == 0:
                L.set_string(A, f, i, v.get(f, '') or '')
            else:
                L.set(A, f, i, int(v[f]) - t['lows'].get(f, 0))
    L.fix()
    if L.verify():
        raise SystemExit('CRC не сошлись')
    return L.by_name[A]['fields']['index'][1]


def run(name, N, fix, c27, args, E):
    d = os.path.join(W_DIR, name, 'db')
    path, meta = os.path.join(d, 'nhlng.db'), os.path.join(d, 'nhlng-meta.xml')
    if not (os.path.isfile(path) and os.path.isfile(meta)):
        print(f'{name}: нет {path} (или схемы рядом) — пропуск')
        return None
    data = open(path, 'rb').read()
    L = Tdb(data, load_meta(meta))
    before = len(L.live_rows(A))
    rows, rep = build(L, N, fix, c27, args.lo, args.hi, args.league_ids, args.prune, E)
    width = write_table(L, rows)
    changed = bytes(L.d) != data
    meta_need = width > 9
    by = defaultdict(Counter)
    for v in rows:
        by[season_of(v['year'])][LEAGUE_NAME.get(v['league'], v['league'])] += 1
    out = {'db': path, 'rows_before': before, 'rows': len(rows), 'index_bits': width,
           'seasons': {f"{s}/{(s + 1) % 100:02d}": dict(c) for s, c in sorted(by.items())},
           'fixes': rep['fixes'], 'fix_misses': rep['fix_misses'], 'skipped': rep['skipped'],
           'team_how': dict(rep['team']), 'player_how': dict(rep['player']), 'kept_from_base': dict(rep['kept'])}
    if args.write and changed:
        stamp = time.strftime('%Y%m%d-%H%M%S')
        bk = os.path.join(WORK, 'backup', f'{name}-{stamp}')
        os.makedirs(bk, exist_ok=True)
        shutil.copy2(path, os.path.join(bk, 'nhlng.db'))
        shutil.copy2(meta, os.path.join(bk, 'nhlng-meta.xml'))
        open(path + '.part', 'wb').write(L.d)
        os.replace(path + '.part', path)
        out['written'], out['backup'] = True, bk
    if args.write and meta_need:
        out['meta_patched'] = patch_meta(meta, width)
    os.makedirs(WORK, exist_ok=True)
    json.dump(out, open(os.path.join(WORK, f'{name}.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    state = ('записано' if out.get('written') else 'база уже такая') if args.write else \
        ('проба, не записано' if changed else 'проба: база уже такая')
    yrs = sorted(by)
    print(f"{name}: строк {before} → {len(rows)} (index {width} бит), сезоны {yrs[0]}/{(yrs[0] + 1) % 100:02d}…"
          f"{yrs[-1]}/{(yrs[-1] + 1) % 100:02d} — {state}")
    lg = Counter()
    for c in by.values():
        lg.update(c)
    print(f"  по лигам: {dict(lg)}; клубы: {dict(rep['team'])}; игроки: {dict(rep['player'])}")
    print(f"  правок {len(rep['fixes'])}" + (f", не применились {len(rep['fix_misses'])}" if rep['fix_misses'] else '')
          + (f"; из прежней таблицы оставлено {sum(rep['kept'].values())}" if rep['kept'] else ''))
    for s in rep['fix_misses'] + rep['skipped']:
        print('   ', s)
    if out.get('backup'):
        print(f"  копия до записи: {out['backup']}")
    if out.get('meta_patched'):
        print(f"  схема: {meta} — index {width} бит")
    if args.show is not None:
        show(L, rows, args.show)
    return out


def show(L, rows, s):
    abbr = {r: L.get_string(T, 'abbrname', r) for r in L.live_rows(T)}
    print(f'  сезон {s}/{(s + 1) % 100:02d} (year {s - YEAR0}):')
    for v in rows:
        if season_of(v['year']) == s:
            pid = f" id {v['playerid']}" if v['playerid'] >= 0 else ''
            print(f"    {LEAGUE_NAME.get(v['league'], v['league']):5} {AWARDS.get(v['awardid'], v['awardid'])[:34]:34} "
                  f"{(v['firstname'] + ' ' + v['lastname']).strip():30} {abbr.get(v['team'], v['team'])}{pid}")


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0], formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog=__doc__.split('\n\n', 1)[1])
    ap.add_argument('sets', nargs='*', metavar='out|out-ahl32',
                    help='базы game/work/legacy-data/<набор>/db (по умолчанию обе)')
    ap.add_argument('--write', action='store_true', help='записать (без него — проба)')
    ap.add_argument('--db27', help='база NHL 27 (по умолчанию NHL27_DB или game/work/nhl27/db/nhl_game.db)')
    ap.add_argument('--from', dest='lo', type=int, default=1900, help='первый сезон (год начала: 1996 = 1996/97)')
    ap.add_argument('--to', dest='hi', type=int, default=season.YEAR - 1,
                    help=f'последний сезон (по умолчанию {season.YEAR - 1} — сезон перед tools/season.py YEAR)')
    ap.add_argument('--leagues', default='nhl,ahl,chl', help='nhl, ahl, chl (= ohl, qmjhl, whl) через запятую')
    ap.add_argument('--prune', action='store_true', help='убрать из таблицы всё вне --from…--to и --leagues')
    ap.add_argument('--fix', default=FIX, help='файл правок (по умолчанию tools/legacy_data/awards_fix.json)')
    ap.add_argument('--no-fix', action='store_true', help='без правок — строки NHL 27 как есть')
    ap.add_argument('--show', type=int, help='показать сезон (год начала) после сопоставления')
    ap.add_argument('--awards', action='store_true', help='номера наград и названия')
    args = ap.parse_args()
    bad = [s for s in args.sets if s not in ('out', 'out-ahl32')]
    if bad:
        ap.error(f'наборы — out и out-ahl32, не {bad}')
    if args.awards:
        for a in sorted(AWARDS):
            print(f'{a:3} {AWARDS[a]}')
        return
    if args.hi >= season.YEAR:
        print(f'внимание: сезоны с {season.YEAR}/{(season.YEAR + 1) % 100:02d} игра берёт из франшизы, не из этой таблицы')
    ids = set()
    for x in args.leagues.split(','):
        x = x.strip().lower()
        if x == 'chl':
            ids |= {12, 13, 14}
        elif x in LEAGUES:
            ids.add(LEAGUES[x])
        else:
            raise SystemExit(f'--leagues: нет лиги «{x}» (nhl, ahl, chl, ohl, qmjhl, whl)')
    args.league_ids = ids
    fix = None if args.no_fix else json.load(open(args.fix, encoding='utf-8'))
    N = nhl27.open_db(args.db27)
    c27 = clubs27(N)
    E = None
    if os.path.isfile(EA_DB) and os.path.isfile(EA_DB[:-3] + '-meta.xml'):
        E = Tdb(open(EA_DB, 'rb').read(), load_meta(EA_DB[:-3] + '-meta.xml'))
    for s in args.sets or ['out', 'out-ahl32']:
        run(s, N, fix, c27, args, E)
    if not args.write:
        print('проба: ничего не записано (--write — записать)')


if __name__ == '__main__':
    main()
