"""Новый ростер: трейды по спеке, потом свежие звенья всех 32 клубов → база и сейв ROSTER с датой в имени.

    python tools/legacy_data/roster_update.py run [--trades ФАЙЛ] [--fetch-lines] [--date ДД.ММ.ГГГГ] [--dry-run]
    python tools/legacy_data/roster_update.py example            # образец спеки трейдов

Вход:
- спека трейдов — game/work/roster-update/trades.txt, строка на сделку, новые просто дописываются (образец —
  tools/legacy_data/roster_update.example.txt, описание — docs/roster-update.md);
- звенья — кэш DailyFaceoff game/work/roster-cache/dailyfaceoff/ (`--fetch-lines` скачает заново: python tools/roster
  fetch --only dfo --refresh, 33 запроса с паузой);
- база, на которой сделан сейв, — по умолчанию установленная (nhl-legacy-port/userdata/cache/guest/db/nhlng.db), сейв —
  новейший ROSTER пользователя. Оба только читаются.

Выход — папка --out (по умолчанию game/work/roster-update/out):
- `ROSTER ДД.ММ.ГГГГ` — готовый файл на копии новейшего ROSTER (трёхстороннее слияние roster_merge.py, правки
  пользователя в сейве целы). Дата в имени — дата данных: самый свежий трейд и самая свежая страница звеньев, --date
  задаёт её вручную. Лаунчер с этой датой подписывает ростер в меню игры;
- db/nhlng.db, db/nhlng-meta.xml, db/draft_roster.db — база с теми же изменениями: новая франшиза и составы не расходятся;
- report.md и report.json — трейды, переводы, новые игроки, изменения по клубам, кто не сопоставлен;
- new-players.json — спека add_players.py для игроков, которых не было в базе (можно поправить руками: файл читается
  при следующем запуске).

Порядок: новые игроки → трейды → вызовы по звеньям → сверка со списками НХЛ (кто в списке — в клуб; кто в клубе, но нет
ни в списке, ни на странице, — куда скажет карточка игрока) → звенья → буквы → номера → контракты → экипировка вратарей →
проверки → запись. --dry-run считает всё то же, пишет только отчёт. Повторный запуск на готовой базе ничего не меняет.
Подробности и правила — docs/roster-update.md.
"""
import argparse
import datetime
import glob
import json
import os
import re
import shutil
import statistics
import subprocess
import sys
import unicodedata
import urllib.parse
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
ROOT = os.path.dirname(TOOLS)
sys.path.insert(0, TOOLS)
sys.path.insert(0, HERE)
os.environ['NHL_GAME'] = 'legacy'
from roster.common import set_game  # noqa: E402
set_game('legacy')                     # до импорта модулей конвейера: dbview берёт поля игры при импорте
import add_players as AP  # noqa: E402
import contracts as CT  # noqa: E402
import draft_roster  # noqa: E402
import goalie_gear  # noqa: E402
import roster_merge  # noqa: E402
from roster import lines as LN  # noqa: E402
from roster import lines_real, nhl27, ovrformula, sources  # noqa: E402
from roster.build import same_first  # noqa: E402
from roster.common import Http, SEASON, SEASON_YEAR, SLOT_TEAM, TEAM_SLOT, norm, read_json, team_slot  # noqa: E402
from roster.dbview import B, F, FLAGS, G, NHL, POS_NAME, R, SPECIAL, T, View, fld  # noqa: E402
from roster.ratings import BASE, GK, SK, cls  # noqa: E402
from tdb import SaveFile, Tdb, load_meta  # noqa: E402

WORK = os.path.join(ROOT, 'game', 'work', 'roster-update')
CACHE = os.path.join(ROOT, 'game', 'work', 'roster-cache')
USERDATA = os.path.join(ROOT, 'nhl-legacy-port', 'userdata')
SAVES = os.path.join(USERDATA, 'B13EBABEBABEBABE', '454109EC', '00000001')
CACHE_DB = os.path.join(USERDATA, 'cache', 'guest', 'db')
AHL_PLAYERS = os.path.join(ROOT, 'game', 'work', 'legacy-data', 'ahl-2026', 'out-ahl32', 'players.json')
EXAMPLE = os.path.join(HERE, 'roster_update.example.txt')
LAUNCHERS = (os.path.join(ROOT, 'nhl-legacy-port', 'out', 'launcher', 'nhllegacy_launcher.exe'),
             os.path.join(ROOT, 'nhl-legacy-port', 'out', 'build', 'win-amd64-release', 'nhllegacy_launcher.exe'))
MAX_PER_TEAM = 40
NHL_API = 'https://api-web.nhle.com/v1'
SEARCH = 'https://search.d3.nhle.com/api/v1/search/player'
SUFFIXES = {'jr', 'sr', 'ii', 'iii', 'iv'}
AHL_LEAGUE = 1                         # exhibitionteams.league
PICK = re.compile(r'^(?:pick|пик)\s+(\d{4})\s+(?:r|раунд\s*)?(\d)$', re.I)
TAG = re.compile(r'\[(\w+)\]')
NUM = re.compile(r'#(\d{1,2})\b')


class SpecError(ValueError):
    pass


def fmt(d):
    return d.strftime('%d.%m.%Y')


def parse_date(s, what):
    for f in ('%d.%m.%Y', '%Y-%m-%d'):
        try:
            return datetime.datetime.strptime(s.strip(), f).date()
        except ValueError:
            pass
    raise SpecError(f'{what}: дата ДД.ММ.ГГГГ или ГГГГ-ММ-ДД, а не «{s}»')


# --- спека трейдов ----------------------------------------------------------------------------------------------------
def parse_trades(path):
    """Строка файла: `ДАТА | КЛУБ: что получает, что получает | КЛУБ: что получает`. Игрок — имя и фамилия, тёзок
    различает #номер; [farm] — в фарм-клуб нового клуба, [nhl] — в клуб НХЛ, без метки уровень прежний. Пик — `pick 2027
    R2`. Сторон может быть больше двух или одна: так записывается перевод без сделки (`28.10.2026 | CBJ: Carson Soucy
    [farm]`). Столбец `источник: …` попадает в отчёт. # — комментарий."""
    if not os.path.isfile(path):
        raise SpecError(f'нет спеки трейдов {path}: образец — roster_update.py example')
    out = []
    for no, raw in enumerate(open(path, encoding='utf-8-sig'), 1):
        line = raw.split('#', 1)[0] if raw.lstrip().startswith('#') else raw
        line = line.strip()
        if not line:
            continue
        where = f'{os.path.basename(path)}, строка {no}'
        cols = [c.strip() for c in line.split('|')]
        if len(cols) < 2:
            raise SpecError(f'{where}: нужно «дата | клуб: кто | клуб: кто», а не «{line}»')
        tr = {'date': parse_date(cols[0], where), 'line': no, 'sides': [], 'source': None}
        for col in cols[1:]:
            if col.lower().startswith(('источник:', 'source:')):
                tr['source'] = col.split(':', 1)[1].strip()
                continue
            if ':' not in col:
                raise SpecError(f'{where}: сторона без клуба: «{col}»')
            club, items = col.split(':', 1)
            slot = team_slot(club.strip())
            if slot is None:
                raise SpecError(f'{where}: клуб НХЛ — аббревиатура (NSH, SEA…), а не «{club.strip()}»')
            side = {'club': slot, 'items': []}
            for it in items.split(','):
                it = it.strip()
                if not it:
                    continue
                m = PICK.match(it)
                if m:
                    side['items'].append({'pick': (int(m.group(1)), int(m.group(2))), 'text': it})
                    continue
                tags = {t.lower() for t in TAG.findall(it)}
                bad = tags - {'farm', 'nhl'}
                if bad:
                    raise SpecError(f'{where}: метка [{sorted(bad)[0]}] — есть только [farm] и [nhl]')
                num = NUM.search(it)
                name = NUM.sub('', TAG.sub('', it)).strip()
                if len(name.split()) < 2:
                    raise SpecError(f'{where}: «{it}» — нужно имя и фамилия или pick ГГГГ RN')
                side['items'].append({'name': name, 'num': int(num.group(1)) if num else None, 'tags': tags, 'text': it})
            tr['sides'].append(side)
        out.append(tr)
    if not out:
        raise SpecError(f'{path}: нет ни одной сделки')
    return sorted(out, key=lambda t: (t['date'], t['line']))


# --- списки клубов API НХЛ -------------------------------------------------------------------------------------------
def api_rosters(refresh, log):
    """{клуб: [(имя, номер, группа)]} из /v1/roster/{клуб}/current: 32 запроса с паузой, ответы — в кэше
    game/work/roster-cache/nhl/roster-now/ (--fetch-lines берёт заново)."""
    h = Http(CACHE, pause=1.5, refresh=refresh, log=log)
    out = {}
    for abbr in TEAM_SLOT:
        d = h.json(f'{NHL_API}/roster/{abbr}/current', f'nhl/roster-now/{abbr}.json') or {}
        out[abbr] = [(f"{p['firstName']['default']} {p['lastName']['default']}", p.get('sweaterNumber'), g)
                     for k, g in (('forwards', 'f1'), ('defensemen', 'd1'), ('goalies', 'g')) for p in d.get(k) or []]
    return out


# --- новейший ROSTER ---------------------------------------------------------------------------------------------------
def newest_roster(saves=None):
    """Файл новейшего ROSTER. Без saves — установка на этом ПК в любой раскладке (saves\\rosters с 0.17.0 или
    userdata\\<xuid>\\454109EC\\00000001, tools/legacy_saves.py); saves — папка со старыми ROSTER <время>."""
    if saves is None:
        from legacy_saves import Saves
        try:
            return Saves.of_install().latest('ROSTER').file
        except FileNotFoundError as e:
            raise SpecError(f'{e} — укажите --save')
    best = None
    for d in glob.glob(os.path.join(glob.escape(saves), 'ROSTER *')):
        m = re.fullmatch(r'ROSTER (\d{14})', os.path.basename(d))
        f = os.path.join(d, os.path.basename(d))
        if m and os.path.isfile(f) and (best is None or m.group(1) > best[0]):
            best = (m.group(1), f)
    if not best:
        raise SpecError(f'в {saves} нет ROSTER — укажите --save')
    return best[1]


# --- работа с составами --------------------------------------------------------------------------------------------
class Update:
    """Составы базы в памяти: записи exhibitionrostertable и пул свободных агентов; в базу — flush."""

    def __init__(self, db, log=print):
        self.db, self.log = db, log
        self.v = View(db)
        v = self.v
        self.entries = [dict(e) for e in v.entries]
        self.fa = list(v.fa)
        self.by_row = {}
        for e in self.entries:
            if e['team'] not in SPECIAL:
                self.by_row[self.row(e)] = e
        self.by_name, self.by_last = defaultdict(list), defaultdict(list)
        for r in range(v.nbio):
            if not v.created_slot(r):
                self.by_name[norm(v.name(r))].append(r)
                self.by_last[norm(v.s('lastname', r))].append(r)
        self.fa_row = {v.row_of_gid[v.link_gid[l]]: l for l in self.fa if v.link_gid.get(l) in v.row_of_gid}
        self.locked = {}                 # строка → клуб: игрока спеки не тянем обратно по устаревшей странице
        self.touched = set()             # команды, чьи составы менялись
        self.moves, self.signed, self.loans = [], [], []
        self.was = {r: e['team'] for r, e in self.by_row.items()}
        self.notes = []
        self._p = {}
        self._clubs = {}

    # чтение ------------------------------------------------------------------------------------------------------------
    def row(self, e):
        return self.v.row_of_gid.get(self.v.link_gid.get(e['playerindex']))

    def abbr(self, t):
        if t is None:
            return 'FA'
        return SLOT_TEAM.get(t) or self.db.get_string(T, 'abbrname', t) or str(t)

    def team(self, t):
        return [e for e in self.entries if e['team'] == t]

    def name(self, r):
        return self.v.name(r)

    def club_of(self, r):
        e = self.by_row.get(r)
        return e['team'] if e else None

    def rights(self, r):
        x = self.db.get(B, 'proteam', r) - 1
        return x if 0 <= x < 32 else None

    def farm(self, t):
        x = self.db.get(T, 'ahlaffiliate', t) - 1
        return x if x >= 32 else None

    def is_goalie(self, r):
        return self.v.is_goalie(r)

    def player(self, r):
        """Словарь игрока для lines.py: атрибуты и OVR — как их считает игра."""
        if r not in self._p:
            v, db = self.v, self.db
            t, ai = v.ai(r)
            pos = POS_NAME[v.g('position', r)]
            attrs = {f: db.get(t, fld(f), ai) + BASE for f in (GK if t == G else SK)}
            self._p[r] = {'pos': pos, 'ovr': ovrformula.game_ovr(cls(pos), attrs), 'attrs': attrs,
                          'shoots': 'L' if v.g('handedness', r) == 0 else 'R', 'out': False}
        return self._p[r]

    def ovr(self, r):
        return self.player(r)['ovr']

    def find(self, name, goalie=None, club=None, num=None):
        """Строки игрока по имени во всей базе, лучшие первыми: права клуба club, номер, в клубе или в пуле СА."""
        words = name.split()
        while len(words) > 2 and norm(words[-1]) in SUFFIXES:
            words = words[:-1]
        key = norm(' '.join(words))
        hits = list(self.by_name.get(key, []))
        if not hits:
            for last, rows in self.by_last.items():
                if last and key.endswith(last) and len(last) >= 3:
                    first = key[:len(key) - len(last)]
                    hits += [r for r in rows if first and same_first(self.v.s('firstname', r), first)]
        if goalie is not None:
            hits = [r for r in hits if self.is_goalie(r) == goalie]
        rank = lambda r: (self.rights(r) != club, num is not None and self.v.g('jersey', r) != num,
                          r not in self.by_row and r not in self.fa_row, r)
        return sorted(set(hits), key=rank)

    # перевод --------------------------------------------------------------------------------------------------------
    def free_number(self, team, want, me=None):
        taken = {e['jersey'] for e in team if e is not me}
        if 1 <= want <= 98 and want not in taken:
            return want
        return min((n for n in range(1, 99) if n not in taken), key=lambda n: (abs(n - want), n))

    def transfer(self, r, to, rights=None, why='', num=None):
        """Игрок r → команда to (запас, без звеньев и буквы): запись старого клуба переезжает, СА — новая запись на
        связи пула. rights — клуб НХЛ с правами. Звенья прежнего клуба достраиваются потом (lines)."""
        db, v = self.db, self.v
        e = self.by_row.get(r)
        frm = e['team'] if e else None
        rec = {'name': self.name(r), 'row': r, 'from': self.abbr(frm), 'to': self.abbr(to), 'why': why,
               'rights_from': self.abbr(self.rights(r)) if self.rights(r) is not None else '—',
               'rights_to': self.abbr(rights) if rights is not None else None, 'ovr': self.ovr(r)}
        if e is None:
            link = self.fa_row.get(r)
            if link is None:
                cand = [l for l in v.links_of[v.gid[r]] if l not in v.link_created
                        and not any(x['playerindex'] == l for x in self.entries)]
                if not cand:
                    raise SpecError(f'{self.name(r)}: нет свободной связи в exhibitionplayers')
                link = min(cand)
            else:
                self.fa.remove(link)
                del self.fa_row[r]
                self.signed.append(r)
            t, ai = v.ai(r)
            e = {f: 0 for f in v.entry_fields}
            e.update(playerindex=link, playerstyle=db.get(t, 'playerstyle', ai), jersey=v.g('jersey', r))
            self.entries.append(e)
            self.by_row[r] = e
        else:
            self.touched.add(frm)
        team = self.team(to)
        if len(team) + 1 > MAX_PER_TEAM:
            raise SpecError(f'{self.abbr(to)}: уже {MAX_PER_TEAM} записей, {self.name(r)} не влезает')
        n = self.free_number(team, num or e['jersey'] or v.g('jersey', r) or 0, e)
        rec['letter'] = e['captain'] if frm is not None else 0
        if rec['letter']:
            self.notes.append(('letter', frm, rec['letter'], self.name(r)))
        for f in FLAGS:
            e[f] = 0
        e.update(team=to, jersey=n, rosterstatus=0, captain=0, key=to * MAX_PER_TEAM + 10 ** 6)
        db.set(B, 'team', r, to + 1)
        db.set(B, 'jersey', r, n)
        if rights is not None:
            db.set(B, 'proteam', r, rights + 1)
        self.touched.add(to)
        rec['num'] = n
        self.moves.append(rec)
        return rec

    # трейды ---------------------------------------------------------------------------------------------------------
    def trades(self, trades, new_rows):
        out = []
        for tr in trades:
            clubs = [s['club'] for s in tr['sides']]
            for side in tr['sides']:
                to = side['club']
                others = [c for c in clubs if c != to]
                for it in side['items']:
                    st = {'date': fmt(tr['date']), 'to': self.abbr(to), 'item': it['text'], 'source': tr['source']}
                    out.append(st)
                    if 'pick' in it:
                        st['status'] = 'пик: в составах не хранится'
                        continue
                    hits = self.find(it['name'], num=it['num'])
                    if not hits:
                        st['status'] = 'нет в базе'
                        continue
                    live = [r for r in hits if r in self.by_row or r in self.fa_row or self.rights(r) is not None]
                    if len(live) > 1 and it['num'] is None and self.rights(live[0]) == self.rights(live[1]):
                        raise SpecError(f"{it['name']}: в базе тёзки — допишите #номер в спеке трейдов")
                    r = (live or hits)[0]
                    self.locked[r] = to
                    self.trade_one(r, to, others, it, st, new_rows)
        return out

    def trade_one(self, r, to, others, it, st, new_rows):
        rights, club = self.rights(r), self.club_of(r)
        st['player'] = self.name(r)
        st['was'] = f"{self.abbr(club)}, права {self.abbr(rights) if rights is not None else '—'}"
        farm = self.farm(to)
        if r in new_rows:
            st['status'] = 'новый в базе: сразу в новом клубе'
            return
        if rights == to:
            st['status'] = 'уже в новом клубе в базе'
            if 'farm' in it['tags'] and club == to and farm is not None:
                self.transfer(r, farm, why=f"спека {st['date']}: в фарм" + (f" ({st['source']})" if st['source'] else ''))
                st['status'] = f'в фарм-клуб {self.abbr(farm)}'
            elif 'nhl' in it['tags'] and club == farm:
                self.transfer(r, to, why=f"спека {st['date']}: в клуб НХЛ" + (f" ({st['source']})" if st['source'] else ''))
                st['status'] = 'в клуб НХЛ'
            return
        st['status'] = 'проведён' if rights in others or not others else (
            f"проведён, но в базе права {self.abbr(rights) if rights is not None else 'нет'}, а ждали "
            f"{'/'.join(self.abbr(c) for c in others)}")
        pos_club = club in NHL if club is not None else False
        ahl = club is not None and self.db.get(T, 'league', club) == AHL_LEAGUE and club not in NHL
        if 'farm' in it['tags']:
            dest = farm
        elif 'nhl' in it['tags'] or pos_club:
            dest = to
        elif ahl:
            dest = farm
        else:
            dest = None                  # Европа, юниоры: остаётся в клубе, меняются только права
        if dest is None:
            self.db.set(B, 'proteam', r, to + 1)
            st['status'] += f': играет в {self.abbr(club)}, меняются только права'
            return
        self.transfer(r, dest, rights=to, why=f"трейд {st['date']}", num=it['num'])

    # звенья: кто должен быть в клубе -------------------------------------------------------------------------------
    def team_list(self, t):
        """Игроки клуба в формате, который ждёт lines_real.find: вместо nhl_id — game_id."""
        return [{'nhl_id': self.v.gid[self.row(e)], 'first': self.v.s('firstname', self.row(e)),
                 'last': self.v.s('lastname', self.row(e)), 'pos': POS_NAME[self.v.g('position', self.row(e))],
                 'num': e['jersey'], 'team': SLOT_TEAM[t]} for e in self.team(t)]

    def team_players(self):
        return {SLOT_TEAM[t]: self.team_list(t) for t in NHL}

    def actualize(self, src):
        """Игрок страницы, которого нет в клубе: переводится из фарма, пула СА или другого клуба. Новейшая страница
        главнее: чужого игрока тянем, только если его клуб о нём не пишет или его страница старше."""
        listed = defaultdict(list)
        for abbr, s in src.items():
            for g, qs in s['groups'].items():
                for q in qs:
                    listed[norm(q['name'])].append((s.get('updated') or '', abbr))
        tp = self.team_players()
        everyone = [p for x in tp.values() for p in x]
        absent = []
        for abbr in sorted(src, key=lambda a: src[a].get('updated') or '', reverse=True):
            s, slot = src[abbr], TEAM_SLOT[abbr]
            tl = lines_real.team_lines(s, tp[abbr], everyone)
            wanted = [(x['name'], x.get('num'), x['groups'][0]) for x in tl['unmatched']]
            wanted += [(x['name'], next((q.get('num') for q in s['groups'].get('ir', []) if q['name'] == x['name']), None), 'ir')
                       for x in tl['injured'] if x['nhl_id'] is None]
            for name, num, group in wanted:
                goalie = True if group == 'g' else None if group == 'ir' else False
                hits = self.find(name, goalie=goalie, club=slot, num=num)
                if not hits:
                    absent.append({'club': abbr, 'name': name, 'num': num, 'group': group})
                    continue
                r = hits[0]
                cur = self.club_of(r)
                if self.locked.get(r, slot) != slot:
                    self.notes.append(('stale', abbr, name, self.abbr(self.locked[r])))
                    continue
                if cur == slot:
                    continue
                if cur in NHL:
                    mine = max((u for u, a in listed[norm(self.name(r))] if a == abbr), default='')
                    theirs = max((u for u, a in listed[norm(self.name(r))] if a == SLOT_TEAM[cur]), default='')
                    if theirs and theirs > mine:
                        self.notes.append(('stale', abbr, name, SLOT_TEAM[cur]))
                        continue
                why = f'звенья {abbr}: ' + ('свободный агент' if r in self.fa_row else 'вызов из фарма'
                                            if cur is not None and self.farm(slot) == cur else 'из другого клуба')
                self.transfer(r, slot, rights=slot, why=why, num=num)
                self.locked[r] = slot
        return absent

    def need_goalies(self):
        """У клуба АХЛ после вызова меньше двух вратарей: запасной вратарь клуба АХЛ, где вратарей больше всего (права
        у него прежние). Иначе звеньям клуба некого ставить в ворота (g1, g2)."""
        for t in sorted(self.touched):
            if t in NHL or self.db.get(T, 'league', t) != AHL_LEAGUE:
                continue
            while sum(self.is_goalie(self.row(e)) for e in self.team(t)) < 2:
                spare = defaultdict(list)
                for e in self.entries:
                    u = e['team']
                    if u not in NHL and u != t and self.db.get(T, 'league', u) == AHL_LEAGUE and self.is_goalie(self.row(e)):
                        spare[u].append(e)
                spare = {u: g for u, g in spare.items() if len(g) >= 3}
                if not spare:
                    raise SpecError(f'{self.abbr(t)}: остался один вратарь, а запасных в АХЛ нет')
                u = min(spare, key=lambda x: (-len(spare[x]), x))
                e = max((x for x in spare[u] if not (x['g1'] or x['g2'])), key=lambda x: (self.ovr(self.row(x)), -x['key']))
                r = self.row(e)
                self.transfer(r, t, why=f'{self.abbr(t)} остался с одним вратарём после вызова: взят запасной')
                self.loans.append(r)

    # звенья: запись -----------------------------------------------------------------------------------------------
    def lp(self, t):
        out = []
        for e in self.team(t):
            r = self.row(e)
            out.append(dict(self.player(r), key=self.v.gid[r], _e=e))
        return out

    def put_lines(self, team_lp, keys, dressed):
        for p in team_lp:
            e = p['_e']
            for f in FLAGS:
                e[f] = 0
            e['rosterstatus'] = int(p['key'] in dressed)
        by = {p['key']: p['_e'] for p in team_lp}
        for slot, k in keys.items():
            by[k][slot] = 1

    def lines_nhl(self, src):
        tp = self.team_players()
        everyone = [p for x in tp.values() for p in x]
        info = {}
        for abbr, slot in TEAM_SLOT.items():
            team_lp = self.lp(slot)
            s = src.get(abbr)
            res = {'source': 'rating', 'updated': None}
            if s:
                tl = lines_real.team_lines(s, tp[abbr], everyone)
                ovr = {p['key']: p['ovr'] for p in team_lp}
                g = tl['g']
                swapped = None
                if len(g) == 2 and g[0] in ovr and g[1] in ovr and ovr[g[1]] > ovr[g[0]]:
                    g[0], g[1] = g[1], g[0]          # на странице первым стоит сыгравший последним, основной — сильнейший
                    swapped = True
                real = {k: tl.get(k) or [] for k in ('f', 'd', 'g', 'pp', 'pk', 'extra_d')}
                real['injured'] = [i['nhl_id'] for i in tl['injured'] if i.get('nhl_id')]
                n = LN.real_count(team_lp, real)
                res.update(updated=s.get('updated'), by=s.get('source'), url=s.get('source_url'), from_source=n,
                           unmatched=[x['name'] for x in tl['unmatched']], fuzzy=[(x['name'], x['player']) for x in tl['fuzzy']],
                           injured=[i['name'] for i in tl['injured']], goalies_swapped=bool(swapped))
                if n >= LN.MIN_REAL:
                    keys, dressed, how = LN.build_real(team_lp, real)
                    res.update(source='dailyfaceoff', filled=[(sl, self.name(self.v.row_of_gid[k])) for sl, k in how['filled']],
                               dropped=[(self.name(self.v.row_of_gid[k]), w, why) for k, w, why in how['dropped']])
                    self.put_lines(team_lp, keys, dressed)
                    self.touched.add(slot)
                    info[abbr] = res
                    continue
                res['why'] = f'страница дала {n} игроков клуба, нужно {LN.MIN_REAL}'
            keys, dressed = LN.build(team_lp)
            self.put_lines(team_lp, keys, dressed)
            self.touched.add(slot)
            info[abbr] = res
        return info

    def lines_other(self):
        """Клубы вне НХЛ, чей состав изменился: звенья заново по рейтингу, как их собирал конвейер."""
        done = []
        for t in sorted(self.touched):
            if t in NHL:
                continue
            team_lp = self.lp(t)
            try:
                keys, dressed = LN.build(team_lp)
            except LN.NotEnoughPlayers as e:
                raise SpecError(f'{self.abbr(t)}: звенья не собрать, мало игроков ({e})')
            self.put_lines(team_lp, keys, dressed)
            done.append(self.abbr(t))
            n = Counter('D' if p['pos'] == 'D' else 'G' if p['pos'] == 'G' else 'F' for p in team_lp)
            if n['F'] < 12 or n['D'] < 6:
                self.notes.append(('short', t, n['F'], n['D']))
        return done

    def letters(self):
        """Ушла буква: достаётся опытнейшему одетому полевому без буквы того же клуба."""
        out = []
        for kind, frm, letter, name in [n for n in self.notes if n[0] == 'letter']:
            cand = [e for e in self.team(frm) if e['rosterstatus'] and not e['captain'] and not self.is_goalie(self.row(e))]
            if not cand:
                out.append(f'{self.abbr(frm)}: буква {name} снята, отдать некому')
                continue
            c = max(cand, key=lambda e: (self.v.g('nhlgamesplayedcareer', self.row(e)), self.ovr(self.row(e))))
            c['captain'] = letter
            out.append(f"{self.abbr(frm)}: буква {'C' if letter == 1 else 'A'} {name} → {self.name(self.row(c))}")
        return out

    def numbers(self, rosters):
        """Номера клубов НХЛ — из списков API НХЛ: номера страниц звеньев бывают старыми (Dobson № 8 при № 53 в клубе).
        Кого в списке нет, остаётся со своим номером, а занят — ближайший свободный."""
        out = []
        for abbr, api in rosters.items():
            slot = TEAM_SLOT[abbr]
            team = self.team(slot)
            tp = self.team_list(slot)
            want = {}
            for name, num, group in api:
                pid = lines_real.find(tp, {'name': name, 'num': num}, group, tp)[0]
                if pid is not None and num:
                    want[pid] = num
            by_gid = {self.v.gid[self.row(e)]: e for e in team}
            for pid, n in want.items():
                e = by_gid[pid]
                if e['jersey'] != n:
                    out.append(f"{abbr}: {self.name(self.row(e))} № {e['jersey']} → {n}")
                    e['jersey'] = n
                    self.db.set(B, 'jersey', self.row(e), n)
                    self.touched.add(slot)
            for e in team:
                r = self.row(e)
                if self.v.gid[r] in want:
                    continue
                if any(x is not e and x['jersey'] == e['jersey'] for x in team):
                    free = [n for n in range(1, 99) if not any(x['jersey'] == n for x in team)]
                    old, e['jersey'] = e['jersey'], min(free, key=lambda n: (abs(n - e['jersey']), n))
                    self.db.set(B, 'jersey', r, e['jersey'])
                    out.append(f"{abbr}: {self.name(r)} № {old} → {e['jersey']} (номер занят, в списке НХЛ его нет)")
                    self.touched.add(slot)
        return out

    # сверка со списками НХЛ -------------------------------------------------------------------------------------------
    def page_ids(self, abbr, page):
        """game_id игроков клуба на его странице: заявка, спецбригады, седьмой защитник, травмированные."""
        tp = self.team_list(TEAM_SLOT[abbr])
        tl = lines_real.team_lines(page, tp, tp)
        ids = {k for rows in (tl['f'], tl['d'], tl['pp'], tl['pk']) for row in rows for k in row}
        ids |= set(tl['g']) | set(tl['extra_d']) | {i['nhl_id'] for i in tl['injured']}
        return ids - {None}

    def list_ids(self, abbr, api):
        tp = self.team_list(TEAM_SLOT[abbr])
        return {lines_real.find(tp, {'name': n, 'num': x}, g, tp)[0] for n, x, g in api} - {None}

    def sync_lists(self, rosters):
        """Игрок списка НХЛ, которого нет в клубе, — в клуб: страница показывает заявку и травмированных, а запасные (их
        в базе ещё числит фарм) есть только в списке. Игрока спеки список назад не тянет."""
        absent = []
        for abbr, api in rosters.items():
            slot = TEAM_SLOT[abbr]
            tp = self.team_list(slot)
            for name, num, group in api:
                if lines_real.find(tp, {'name': name, 'num': num}, group, tp)[0] is not None:
                    continue
                rows = self.find(name, goalie=group == 'g', club=slot, num=num)
                if not rows:
                    absent.append({'club': abbr, 'name': name, 'num': num, 'group': group})
                    continue
                r = rows[0]
                if self.locked.get(r, slot) != slot:
                    self.notes.append(('stale', abbr, name, self.abbr(self.locked[r])))
                    continue
                if self.club_of(r) != slot:
                    self.transfer(r, slot, rights=slot, why=f'список НХЛ {abbr}', num=num)
                    self.locked[r] = slot
        return absent

    def club_named(self, name):
        """Клуб вне НХЛ по названию (exhibitionteams.fullname) или None."""
        if not self._clubs:
            for t in range(self.db.by_name[T]['rows']):
                if t not in NHL and t not in SPECIAL:
                    self._clubs[norm(self.db.get_string(T, 'fullname', t))] = t
        return self._clubs.get(norm(name))

    def card(self, r, http):
        """Свежая карточка НХЛ игрока: поиск по имени, сверка по дате рождения. → (карточка, ссылка) или (None, None).
        Кэш — nhl/landing-now/: карточки конвейера в nhl/landing/ не трогаем, по ним считаны рейтинги."""
        v = self.v
        first, last = v.s('firstname', r), v.s('lastname', r)
        y, m, d = v.birth(r)
        born = f'{y:04d}-{m:02d}-{d:02d}'
        plain = lambda t: ''.join(c for c in unicodedata.normalize('NFKD', t) if not unicodedata.combining(c))
        for q, rel in ((f'{first} {last}', norm(first + last)), (last, norm(last))):
            found = http.json(f"{SEARCH}?culture=en-us&limit=100&q={urllib.parse.quote(plain(q))}",
                              f'nhl/search/name-{rel}.json') or []
            for x in [x for x in found if norm(x.get('name', '')).endswith(norm(last))][:12]:
                pid = int(x['playerId'])
                land = http.json(f'{NHL_API}/player/{pid}/landing', f'nhl/landing-now/{pid}.json')
                if land and land.get('birthDate') == born:
                    return land, f'NHL API player/{pid}/landing'
        return None, None

    def by_card(self, r, abbr, slot, http):
        """Игрок клуба, которого нет ни в списке, ни на странице. Карточка показывает сезон 2026/27 по лигам:
        - были игры в АХЛ — он в АХЛ: клуб по названию, иначе фарм его клуба НХЛ. Игры в НХЛ при этом ничего не решают:
          sequence у seasonTotals идёт по лигам, а не по времени, а из списка он уже выпал;
        - игры в другой лиге, чей клуб есть в базе (Европа, юниоры), — туда; клуба нет (КХЛ, NCAA) — остаётся, в отчёт;
        - только ECHL — в фарм: лиг ниже АХЛ в базе нет;
        - сменил клуб НХЛ — в новый клуб, запасным;
        - только НХЛ или игр нет — ответа нет: остаётся, в отчёт. Вчера отправленного в АХЛ так не отличить от
          травмированного, поэтому по новости его пишут в спеку строкой `дата | КЛУБ: Имя [farm]`.
        → запись отчёта."""
        rec = {'club': abbr, 'name': self.name(r), 'ovr': self.ovr(r), 'to': None}
        land, url = self.card(r, http)
        if land is None:
            return dict(rec, why='нет карточки НХЛ (поиск по имени и дате рождения)', season='', source='NHL API')
        rows = sorted((x for x in land.get('seasonTotals') or [] if x.get('season') == SEASON and x.get('gameTypeId') == 2),
                      key=lambda x: x.get('sequence') or 0)
        team = lambda x: (x.get('teamName') or {}).get('default') or ''
        season = '; '.join(f"{x.get('leagueAbbrev')} {team(x)} {x.get('gamesPlayed') or 0}" for x in rows) or 'игр нет'
        rec.update(season=season, source=url)
        org = team_slot(land.get('currentTeamAbbrev'))
        home = org if org is not None else slot
        rights = org if org is not None and org != self.rights(r) else None
        lg = lambda *names: [x for x in rows if x.get('leagueAbbrev') in names]
        other = [x for x in rows if x.get('leagueAbbrev') not in ('NHL', 'AHL', 'ECHL')]
        known = [x for x in other if self.club_named(team(x)) is not None]
        dest, why = None, None
        if lg('AHL'):
            x = lg('AHL')[-1]
            dest, why = self.club_named(team(x)) or self.farm(home), f'АХЛ, {team(x)}'
        elif known:
            dest, why = self.club_named(team(known[-1])), f"{known[-1].get('leagueAbbrev')}, {team(known[-1])}"
        elif other:
            return dict(rec, why=f"играет в {other[-1].get('leagueAbbrev')}, {team(other[-1])}: клуба в базе нет")
        elif lg('ECHL'):
            dest, why = self.farm(home), 'ECHL: лиги в базе нет, в фарм'
        elif org is not None and org != slot:
            dest, why = org, f'теперь в {land.get("currentTeamAbbrev")}, не в списке: запасным'
        if dest is None:
            return dict(rec, why=f"{'только НХЛ' if rows else 'игр в сезоне нет'}: ни в списке, ни на странице, ответа нет")
        self.transfer(r, dest, rights=rights, why=f'карточка НХЛ: {why}')
        return dict(rec, to=self.abbr(dest), why=why)

    def sync_extra(self, rosters, src, http):
        """Игроки клубов НХЛ вне списка и страницы: по карточке (by_card). Переведённых в этом запуске не трогает."""
        out = []
        for abbr, slot in TEAM_SLOT.items():
            if not rosters.get(abbr) or abbr not in src:          # нет данных клуба — составы не двигаем
                continue
            known = self.page_ids(abbr, src[abbr]) | self.list_ids(abbr, rosters[abbr])
            for e in self.team(slot):
                r = self.row(e)
                if self.v.gid[r] not in known and r not in self.locked:
                    out.append(self.by_card(r, abbr, slot, http))
        return out

    def check_api(self, rosters, src):
        """Что осталось после сверки: в списке, но не в клубе; в клубе, но нет ни в списке, ни на странице."""
        away, extra = [], []
        for abbr, api in rosters.items():
            slot = TEAM_SLOT[abbr]
            tp = self.team_list(slot)
            for name, num, group in api:
                if lines_real.find(tp, {'name': name, 'num': num}, group, tp)[0] is None:
                    rows = self.find(name, goalie=group == 'g', club=slot, num=num)
                    where = self.abbr(self.club_of(rows[0])) if rows and rows[0] in self.by_row else 'нет в базе'
                    away.append(f'{abbr}: {name} (в базе: {where})')
            if abbr in src:
                known = self.page_ids(abbr, src[abbr]) | self.list_ids(abbr, api)
                extra += [f"{abbr}: {p['first']} {p['last']}" for p in tp if p['nhl_id'] not in known]
        return away, extra

    # запись ---------------------------------------------------------------------------------------------------------
    def rows_write(self, table, rows):
        db = self.db
        if db.by_name[table]['rows'] != len(rows):
            db.resize(table, len(rows))
        fields = list(db.by_name[table]['fields'])
        for i, row in enumerate(rows):
            for f in fields:
                if db.get(table, f, i) != row.get(f, 0):
                    db.set(table, f, i, row.get(f, 0))

    def flush(self):
        """key подряд, внутри команды — по возрастанию playerindex (как у всех команд базы)."""
        for t in sorted(self.touched):
            for k, e in enumerate(sorted(self.team(t), key=lambda e: e['playerindex'])):
                e['key'] = t * MAX_PER_TEAM + k
        self.entries.sort(key=lambda e: e['key'])
        self.rows_write(R, self.entries)
        self.rows_write(F, [{'playerindex': l} for l in sorted(self.fa)])
        self.db.fix()


def verify(db, touched):
    """Проверки готовой базы: те же, что у конвейера. → список проблем."""
    v2 = View(db)
    bad = []
    cnt = Counter()
    es = v2.entries
    last = -1
    for e in es:
        t = e['team']
        if e['key'] != t * MAX_PER_TEAM + cnt[t]:
            bad.append(f"key {e['key']} команды {t} не подряд")
        if e['key'] <= last:
            bad.append(f"key {e['key']} не по возрастанию")
        last, cnt[t] = e['key'], cnt[t] + 1
    links = Counter(e['playerindex'] for e in es)
    bad += [f'связь {l} у {n} записей' for l, n in links.items() if n > 1]
    bad += [f'свободный агент {l} в составе' for l in v2.fa if l in links]
    bad += [f"связи {e['playerindex']} нет" for e in es if e['playerindex'] not in v2.link_gid]
    by_team = defaultdict(list)
    for e in es:
        by_team[e['team']].append(e)
    club_of = defaultdict(list)
    for e in es:
        if e['team'] not in SPECIAL:
            club_of[v2.row_of_gid[v2.link_gid[e['playerindex']]]].append(e['team'])
    for r, ts in club_of.items():
        if len(ts) > 1:
            bad.append(f'{v2.name(r)} в двух клубах {ts}')
        if v2.g('team', r) != ts[0] + 1:
            bad.append(f"{v2.name(r)}: team {v2.g('team', r)} ≠ клуб {ts[0]} + 1")
    for t in sorted(set(touched) | set(NHL)):
        te = by_team[t]
        for f in FLAGS:
            n = sum(e[f] for e in te)
            if n != 1:
                bad.append(f'команда {t}: место {f} у {n}')
            for e in te:
                if e[f]:
                    r = v2.row_of_gid[v2.link_gid[e['playerindex']]]
                    kind, pos = LN.slot_kind(f), POS_NAME[v2.g('position', r)]
                    got = 'G' if pos == 'G' else 'D' if pos == 'D' else 'F'
                    if (kind == 'G') != (got == 'G') or (t in NHL and kind not in (None, 'G') and kind != got):
                        bad.append(f'команда {t}: на месте {f} {v2.name(r)} ({pos})')
        dressed = [e for e in te if any(e[f] for f in FLAGS)]
        if len(dressed) != 20 or any(bool(e['rosterstatus']) != (e in dressed) for e in te):
            bad.append(f'команда {t}: одетых {len(dressed)}, rosterstatus не совпадает')
        caps = Counter(e['captain'] for e in te)
        if t in NHL and not ((caps[1] == 1 and caps[2] == 2) or (caps[1] == 0 and caps[2] == 3)):
            bad.append(f'команда {t}: буквы {dict(caps)}')
        nums = Counter(e['jersey'] for e in te)
        bad += [f'команда {t}: номер {n} у двоих' for n, c in nums.items() if c > 1]
        if len(te) > MAX_PER_TEAM:
            bad.append(f'команда {t}: {len(te)} записей')
        for e in te:
            r = v2.row_of_gid[v2.link_gid[e['playerindex']]]
            if v2.g('jersey', r) != e['jersey']:
                bad.append(f"{v2.name(r)}: номер в био {v2.g('jersey', r)}, в составе {e['jersey']}")
            if t in NHL and v2.g('proteam', r) != t + 1:
                bad.append(f"{v2.name(r)}: права {v2.g('proteam', r) - 1}, клуб НХЛ {t}")
            if t in NHL and not v2.g('contractdollars', r):
                bad.append(f'{v2.name(r)}: в клубе НХЛ без контракта')
    return bad + [f'CRC @0x{o:X}' for o, *_ in db.verify()]


# --- новые игроки ---------------------------------------------------------------------------------------------------
def nhl27_index():
    try:
        db = nhl27.open_db()
    except SystemExit:
        return None, {}
    out = defaultdict(list)
    for r in db.live_rows(nhl27.B):
        y, m, d = (db.value(nhl27.B, f, r) for f in ('year', 'month', 'day'))
        out[(norm(db.get_string(nhl27.B, 'firstname', r) + db.get_string(nhl27.B, 'lastname', r)),
             (y + 1900, m + 1, d + 1))].append(r)
    return db, out


def rating27(db27, idx, name, birth, pos):
    """Рейтинг игрока из базы NHL 27: {attributes, style, ovr27} или None."""
    if db27 is None:
        return None
    rows = idx.get((norm(name), birth)) or []
    if len(rows) != 1:
        return None
    gid = db27.get(nhl27.B, 'game_id', rows[0])
    t = nhl27.G if pos == 'G' else nhl27.S
    ai = next((x for x in db27.live_rows(t) if db27.get(t, 'game_id', x) == gid), None)
    if ai is None:
        return None
    v = nhl27.values(db27, t, ai)
    attrs = {}
    for short, f in AP.attr_names(pos).items():
        col = fld(f)
        if col in v:
            attrs[short] = max(BASE, min(BASE + 63, int(v[col])))
    return {'attributes': attrs, 'style': v.get('playerstyle'), 'ovr27': v.get('c_overall')}


def level_ovr(p, land, club_median, log):
    """OVR без рейтинга EA: оценка по статистике как у игроков АХЛ (ahl2026.quantile_ratings: NHLe трёх сезонов, опыт в
    НХЛ), место среди игроков АХЛ того же класса; OVR — медиана 9 ближайших по оценке. → (OVR, откуда)."""
    from roster import ahl2026
    pop = read_json(AHL_PLAYERS) if os.path.exists(AHL_PLAYERS) else None
    same = [x for x in (pop or {}).get('players', []) if (x.get('rating') or {}).get('scale') == 'ahl-quantile'
            and cls(x['pos']) == cls(p['pos'])]
    if not same or p['pos'] == 'G':
        return club_median, f'медиана амплуа клуба {club_median}: нет оценки по статистике'
    model = ahl2026.FixedStats([p], lambda _: land)
    e = model.estimate(p)
    if not e:
        return club_median, f'медиана амплуа клуба {club_median}: нет статистики'
    med = statistics.median(x['rating']['score'] for x in same)
    score = e['conf'] * e['ovr'] + (1 - e['conf']) * med
    near = sorted(same, key=lambda x: abs(x['rating']['score'] - score))[:9]
    ovr = int(round(statistics.median(x['rating']['ovr'] for x in near)))
    return ovr, f"по статистике как у игроков АХЛ: оценка {score:.1f}, {'; '.join(e['lines'])}"


def nhl_games(land):
    """(карьера с плей-офф, прошлый сезон с плей-офф, первый сезон в НХЛ, игры НХЛ + АХЛ)."""
    career = last = pro = 0
    first = None
    for s in land.get('seasonTotals') or []:
        lg, gp = s.get('leagueAbbrev'), s.get('gamesPlayed') or 0
        if s.get('gameTypeId') not in (2, 3):
            continue
        if lg == 'NHL':
            career += gp
            pro += gp
            if s.get('season') == SEASON - 10001:
                last += gp
            if s.get('gameTypeId') == 2 and (first is None or s['season'] < first):
                first = s['season']
        elif lg == 'AHL':
            pro += gp
    return career, last, int(str(first)[:4]) if first else None, pro


def spec_for(u, h, want, pages, db27, idx, log):
    """Спека add_players.py по NHL API, база NHL 27 и страницы контрактов. want: name, club, level ('nhl'/'farm'), num."""
    name = want['name']
    last = name.split()[-1]
    found = h.json(f"{SEARCH}?culture=en-us&limit=20&q={last.lower()}&active=true", f'nhl/search/q-{norm(last)}.json') or []
    me = [x for x in found if norm(x.get('name', '')) == norm(name)]
    if not me:
        return None, 'нет в поиске НХЛ'
    pid = int(me[0]['playerId'])
    land = h.json(f'{NHL_API}/player/{pid}/landing', f'nhl/landing/{pid}.json')
    if not land:
        return None, 'нет карточки НХЛ'
    first, lastn = land['firstName']['default'], land['lastName']['default']
    y, m, d = (int(x) for x in land['birthDate'].split('-'))
    pos = {'L': 'L', 'R': 'R', 'C': 'C', 'D': 'D', 'G': 'G'}[land['position']]
    gp, last_gp, debut, pro = nhl_games(land)
    dr = land.get('draftDetails')
    club = TEAM_SLOT[want['club']]
    farm = u.farm(club)
    spec = {'first': first, 'last': lastn, 'birth': land['birthDate'], 'pos': pos, 'shoots': land.get('shootsCatches'),
            'height': f"{land['heightInInches'] // 12}-{land['heightInInches'] % 12}", 'weight_lb': land['weightInPounds'],
            'birth_city': (land.get('birthCity') or {}).get('default'), 'birth_country': land.get('birthCountry'),
            'birth_state': (land.get('birthStateProvince') or {}).get('default'), 'nhl_gp': gp, 'gp_last_season': last_gp,
            'pro_gp': pro,
            'number': want.get('num') or land.get('sweaterNumber'), 'team': want['club'] if want['level'] == 'nhl' else u.abbr(farm),
            '_nhl_id': pid}
    if want['level'] != 'nhl':
        spec['rights'] = want['club']
    if debut:
        spec['debut'] = debut
    if dr:
        spec['draft'] = {'year': dr['year'], 'round': dr['round'], 'overall': dr['overallPick'], 'team': dr['teamAbbrev']}
    page = next((p for p in pages if p.get('nhl_id') == pid), None)
    if page:
        spec['_contract_page'] = page
        spec['_contract_source'] = f"страница контрактов {page['team']}"
    else:
        spec['contract'] = {'cap': 850000, 'years': 1, 'two_way': True}
        spec['_contract_source'] = 'нет на страницах контрактов: минимальный двусторонний на год (заглушка)'
    r27 = rating27(db27, idx, f'{first} {lastn}', (y, m, d), pos)
    p = {'nhl_id': pid, 'pos': pos}
    if r27 and len(r27['attributes']) == len(AP.attr_names(pos)):
        spec['attributes'], spec['style'] = r27['attributes'], r27['style']
        spec['_rating_source'] = f"NHL 27: OVR EA {r27['ovr27']}, все атрибуты"
    elif r27:
        spec['ovr'], spec['attributes'], spec['style'] = r27['ovr27'], r27['attributes'], r27['style']
        spec['_rating_source'] = f"NHL 27: OVR EA {r27['ovr27']}, атрибутов {len(r27['attributes'])}"
    else:
        same = [u.ovr(u.row(e)) for e in u.team(farm if farm is not None else club)
                if cls(POS_NAME[u.v.g('position', u.row(e))]) == cls(pos)]
        ovr, why = level_ovr(p, land, int(statistics.median(same)) if same else 70, log)
        spec['ovr'] = ovr
        spec['_rating_source'] = why
    spec['_sources'] = f'NHL API player/{pid}/landing'
    return spec, None


def add_new(db, specs, log):
    """Игроки спек на строки доноров (add_players.AddWriter); кого уже есть (имя и дата рождения) — пропускаются."""
    v = View(db)
    have = {(norm(v.name(r)), v.birth(r)) for r in range(v.nbio) if not v.created_slot(r)}
    todo = []
    for i, s in enumerate(specs):
        p = AP.to_player(s, i, 'new-players.json')
        if (norm(p['first'] + ' ' + p['last']), p['birth']) in have:
            continue
        AP.resolve_team(db, p)
        p['_page'] = s.get('_contract_page')
        todo.append(p)
    if not todo:
        return {}
    w = AP.AddWriter(db, todo, log=log)
    bad, _ = w.run()
    if bad:
        raise SpecError('новые игроки: ' + '; '.join(bad[:5]))
    out = {}
    for p in todo:
        r = w.row_of[p['nhl_id']]
        if p['_page']:
            t = CT.terms(p['_page'])
            if t:
                for f, x in t[0].items():
                    db.set(B, f, r, x)
        out[r] = w.out[p['nhl_id']]
    db.fix()
    return out


# --- отчёт -----------------------------------------------------------------------------------------------------------
def lineup(db_view, t):
    """{место: имя} клуба."""
    out = {}
    for e in db_view.entries:
        if e['team'] == t:
            r = db_view.row_of_gid[db_view.link_gid[e['playerindex']]]
            for f in FLAGS:
                if e[f]:
                    out[f] = db_view.name(r)
    return out


def club_diff(v0, v1, t):
    a, b = lineup(v0, t), lineup(v1, t)
    aa, bb = set(a.values()), set(b.values())
    moved = sum(1 for f in a if a[f] != b.get(f))
    return {'in': sorted(bb - aa), 'out': sorted(aa - bb), 'slots_changed': moved, 'lines': b}


def lines_text(b):
    row = lambda *fs: ' – '.join(b.get(f, '?') for f in fs)
    out = [f"  {n}: " + row(f'l{n}lw', f'l{n}c', f'l{n}rw') for n in (1, 2, 3, 4)]
    out += [f"  D{n}: " + row(f'l{n}ld', f'l{n}rd') for n in (1, 2, 3)]
    out += ['  G: ' + row('g1', 'g2')]
    out += [f"  PP{n}: " + row(f'pp{n}lw', f'pp{n}c', f'pp{n}rw', f'pp{n}ld', f'pp{n}rd') for n in (1, 2)]
    out += [f"  PK{n}: " + row(f'pk4_{n}lw', f'pk4_{n}c', f'pk4_{n}ld', f'pk4_{n}rd') for n in (1, 2)]
    return out


def payroll(db, v):
    pay = Counter()
    for e in v.entries:
        if e['team'] in NHL:
            pay[e['team']] += db.get(B, 'contractdollars', v.row_of_gid[v.link_gid[e['playerindex']]])
    return {SLOT_TEAM[t]: x * 5000 for t, x in pay.items()}


def write_report(path, rep):
    L = [f"# Обновление ростера: данные на {rep['date']}", '',
         f"База: `{rep['db']}`", f"Сейв: `{rep['save']}`", f"Звенья: DailyFaceoff, страницы {rep['lines_from']} … {rep['lines_to']}", '',
         '## Трейды', '', '| Дата | Клуб получает | Игрок | Было | Итог |', '|---|---|---|---|---|']
    for t in rep['trades']:
        L.append(f"| {t['date']} | {t['to']} | {t.get('player') or t['item']} | {t.get('was', '')} | {t['status']}"
                 + (f" ({t['source']})" if t.get('source') else '') + ' |')
    L += ['', '## Новые игроки', '']
    for p in rep['new_players']:
        L.append(f"- **{p['name']}** {p['team']} № {p.get('jersey')}, OVR {p.get('ovr')}: {p['rating']}; контракт: {p['contract']}; {p['sources']}")
    if rep['no_data']:
        L += ['', '## Не найдены нигде', ''] + [f"- {x['name']} ({x['club']}): {x['why']}" for x in rep['no_data']]
    L += ['', '## Переводы', '', '| Игрок | OVR | Откуда | Куда | № | Права | Причина |', '|---|---:|---|---|---:|---|---|']
    for m in rep['moves']:
        L.append(f"| {m['name']} | {m['ovr']} | {m['from']} | {m['to']} | {m['num']} | {m['rights_from']} → {m['rights_to'] or m['rights_from']} | {m['why']} |")
    for k, title in (('letters', 'Буквы'), ('numbers', 'Номера'), ('contracts', 'Контракты'), ('notes', 'Заметки'),
                     ('other_clubs', 'Клубы вне НХЛ со звеньями заново по рейтингу')):
        if rep.get(k):
            L += ['', f'## {title}', ''] + [f'- {x}' for x in rep[k]]
    L += ['', '## Ведомости сверх потолка 104 млн', '']
    L += [f"- {c}: {x / 1e6:.2f} млн (было {rep['payroll_before'].get(c, 0) / 1e6:.2f})"
          for c, x in sorted(rep['payroll'].items(), key=lambda kv: -kv[1]) if x > 104_000_000] or ['- нет']
    L += ['', '## Вне списка НХЛ и страницы звеньев: куда по карточке', '', '| Игрок | OVR | Клуб | Куда | Сезон 2026/27 | Источник |',
          '|---|---:|---|---|---|---|']
    L += [f"| {x['name']} | {x['ovr']} | {x['club']} | {x['to']} | {x['season']} | {x['source']} |" for x in rep['by_card']]
    L += ['', '## Остались в клубе без ответа', '']
    L += [f"- {x['club']}: {x['name']}, {x['why']}; сезон: {x.get('season') or '—'}; {x.get('source')}" for x in rep['stayed']] or ['- нет']
    L += ['', '## После сверки', '',
          f"В списке клуба, но в базе в другом месте, {len(rep['api_away'])}: " + ('; '.join(rep['api_away']) or 'нет'), '',
          f"В клубе в базе, но нет ни в списке, ни на странице звеньев, {len(rep['api_extra'])}: " + ('; '.join(rep['api_extra']) or 'нет')]
    L += ['', '## Клубы', '']
    for abbr, c in rep['clubs'].items():
        i = c['info']
        L.append(f"### {abbr}: {(i.get('updated') or '?')[:10]}, {i.get('by') or i.get('source')}")
        L.append(f"Новые в заявке: {', '.join(c['in']) or '—'}. Вышли из заявки: {', '.join(c['out']) or '—'}. Мест изменилось: {c['slots_changed']} из 71.")
        if i.get('goalies_swapped'):
            L.append('Вратари: основной — сильнейший, на странице первым стоял другой.')
        if i.get('filled'):
            L.append('Достроено: ' + ', '.join(f'{s} {n}' for s, n in i['filled']))
        if i.get('dropped'):
            L.append('Не поставлены: ' + ', '.join(f'{n} ({w}: {y})' for n, w, y in i['dropped']))
        if i.get('unmatched'):
            L.append('Не сопоставлены: ' + ', '.join(i['unmatched']))
        if i.get('fuzzy'):
            L.append('Не по точному имени: ' + ', '.join(f'{a} = {b}' for a, b in i['fuzzy']))
        L += ['```'] + lines_text(c['lines']) + ['```', '']
    open(path, 'w', encoding='utf-8').write('\n'.join(L) + '\n')


def install_text(roster_file, dbdir, launcher):
    """Команды установки для отчёта: сам инструмент у пользователя ничего не ставит."""
    db = os.path.join(USERDATA, 'cache', 'guest', 'db')
    exe = LAUNCHERS[1]
    keep = os.path.join(os.path.dirname(dbdir), 'before-install')
    return f'''
## Установка (игра закрыта)

```powershell
New-Item -ItemType Directory -Force "{keep}" | Out-Null
Copy-Item "{db}\\nhlng.db","{db}\\draft_roster.db","{exe}" "{keep}"
Copy-Item "{dbdir}\\nhlng.db","{dbdir}\\draft_roster.db" "{db}" -Force
Copy-Item "{launcher or LAUNCHERS[0]}" "{exe}" -Force
Start-Process -Wait -PassThru "{exe}" -ArgumentList '--import-roster','"{roster_file}"'
```

Откат: те же три файла из `{keep}` обратно, новый ростер удалить в игре: CUSTOMIZE → SAVE/LOAD/DELETE → DELETE → ROSTERS.
'''.replace('\\\\', '\\')


# --- прогон ----------------------------------------------------------------------------------------------------------
def launcher_check(launcher, roster_file, dbdir, work, log):
    """--check-roster на копии: рядом с лаунчером папка userdata с новой базой. Настоящие сейвы не трогает."""
    stand = os.path.join(work, 'check')
    if os.path.isdir(stand):
        shutil.rmtree(stand)
    db_to = os.path.join(stand, 'userdata', 'cache', 'guest', 'db')
    os.makedirs(db_to)
    for f in ('nhlng.db', 'nhlng-meta.xml'):
        shutil.copy2(os.path.join(dbdir, f), db_to)
    exe = os.path.join(stand, os.path.basename(launcher))
    shutil.copy2(launcher, exe)
    r = subprocess.run([exe, '--check-roster', roster_file, '--lang=ru'], capture_output=True)
    text = (r.stdout or b'').decode('utf-8', 'replace').strip()
    log(f'лаунчер --check-roster: код {r.returncode} {text}')
    shutil.rmtree(stand)
    return r.returncode


def run(a):
    log = print
    os.makedirs(a.out, exist_ok=True)
    trades = parse_trades(a.trades)
    if a.fetch_lines:
        subprocess.run([sys.executable, os.path.join(TOOLS, 'roster'), 'fetch', '--only', 'dfo', '--refresh', '--pause', '1.5'],
                       check=True, cwd=ROOT)
    src = sources.dfo_lines(CACHE)
    miss = [x for x in TEAM_SLOT if x not in src]
    if miss:
        log(f"нет страниц звеньев: {', '.join(miss)} — эти клубы по рейтингу")
    wrong = [x for x, s in src.items() if s.get('abbr') and s['abbr'] != x]
    for x in wrong:
        del src[x]
    updated = sorted((s['updated'] for s in src.values() if s.get('updated')))
    date = a.date or max([t['date'] for t in trades] + [datetime.date.fromisoformat(updated[-1][:10])])
    save = a.save or newest_roster()
    db_path = a.db or os.path.join(CACHE_DB, 'nhlng.db')
    meta_path = os.path.join(os.path.dirname(db_path), 'nhlng-meta.xml')
    meta = load_meta(meta_path)
    raw0 = open(db_path, 'rb').read()
    db = Tdb(raw0, meta)
    log(f'база {db_path}\nсейв {save}\nданные на {fmt(date)}; сделок {len(trades)}; страниц звеньев {len(src)}, '
        f'{updated[0][:10]} … {updated[-1][:10]}')

    rosters = api_rosters(a.fetch_lines, log)

    # 1. кого нет в базе: игроки сделок, звеньев и списков НХЛ
    u0 = Update(db)
    pages = CT.load_pages() if glob.glob(os.path.join(glob.escape(CT.SCREENS), '*.json')) else []
    wanted = []
    for tr in trades:
        for side in tr['sides']:
            for it in side['items']:
                if 'name' in it and not u0.find(it['name']):
                    wanted.append({'name': it['name'], 'club': SLOT_TEAM[side['club']], 'num': it['num'],
                                   'level': 'nhl' if 'nhl' in it['tags'] else 'farm', 'why': f"трейд {fmt(tr['date'])}"})
    known = {norm(w['name']) for w in wanted}
    tp = u0.team_players()
    everyone = [p for x in tp.values() for p in x]
    for abbr, s in src.items():
        tl = lines_real.team_lines(s, tp[abbr], everyone)
        lst = [(x['name'], x.get('num')) for x in tl['unmatched']] + [(x['name'], None) for x in tl['injured'] if x['nhl_id'] is None]
        for name, num in lst:
            if not u0.find(name) and norm(name) not in known:
                known.add(norm(name))
                wanted.append({'name': name, 'club': abbr, 'num': num, 'level': 'nhl', 'why': f'звенья {abbr}'})
    for abbr, api in rosters.items():
        for name, num, group in api:
            if (lines_real.find(tp[abbr], {'name': name, 'num': num}, group, tp[abbr])[0] is None
                    and not u0.find(name, goalie=group == 'g') and norm(name) not in known):
                known.add(norm(name))
                wanted.append({'name': name, 'club': abbr, 'num': num, 'level': 'nhl', 'why': f'список НХЛ {abbr}'})
    spec_file = os.path.join(a.work, 'new-players.json')
    specs = read_json(spec_file) if os.path.exists(spec_file) else []
    have = {norm(s['first'] + ' ' + s['last']) for s in specs}
    no_data = []
    h = Http(CACHE, pause=1.5, refresh=a.fetch_lines, log=log)
    if wanted and not a.no_new:
        db27, idx = nhl27_index()
        for w in wanted:
            if norm(w['name']) in have:
                continue
            spec, why = spec_for(u0, h, w, pages, db27, idx, log)
            if spec is None:
                no_data.append(dict(w, why=why))
                continue
            spec['_why'] = w['why']
            specs.append(spec)
        os.makedirs(a.work, exist_ok=True)
        if not a.dry_run:
            with open(spec_file, 'w', encoding='utf-8') as f:
                json.dump(specs, f, ensure_ascii=False, indent=1)
    new_out = add_new(db, specs, log) if not a.no_new else {}

    # 2–7. трейды, звенья, буквы, номера
    u = Update(db)
    st = u.trades(trades, set(new_out))
    absent = u.actualize(src) + u.sync_lists(rosters)
    extra = u.sync_extra(rosters, src, h)
    for x in absent:
        if norm(x['name']) not in {norm(y['name']) for y in no_data}:
            no_data.append(dict(x, why='нет в базе, спеки нет'))
    u.need_goalies()
    info = u.lines_nhl(src)
    other = u.lines_other()
    letters = u.letters()
    numbers = u.numbers(rosters)

    # контракты тех, кто подписан из пула СА или пришёл без контракта
    contracts_rep = []
    for e in u.entries:
        if e['team'] in NHL:
            r = u.row(e)
            if db.get(B, 'contractdollars', r):
                continue
            name = norm(u.name(r))
            page = next((p for p in pages if norm(p['name']) == name), None)
            t = CT.terms(page) if page else None
            if t:
                for f, x in t[0].items():
                    db.set(B, f, r, x)
                contracts_rep.append(f"{u.name(r)}: со страницы контрактов {page['team']}")
            else:
                vals = {'contractstatus': 1, 'contractdollars': 850000 // 5000, 'contractlength': 1, 'contractis2way': 0,
                        'contractismultiyear': 0, 'contractneedsentrylevel': 0, 'yearufa': SEASON_YEAR + 1 - 1900}
                for f, x in vals.items():
                    db.set(B, f, r, x)
                contracts_rep.append(f'{u.name(r)}: на страницах контрактов нет, минимальный на год — заглушка')
    u.flush()

    # экипировка вратарей: набор нового клуба и роли g1/g2 (только у тех, кого это коснулось)
    pl, _ = goalie_gear.plan(db)
    moved = [m['row'] for m in u.moves if u.is_goalie(m['row'])] + [r for r in new_out if u.is_goalie(r)]
    clubs = {u.club_of(r) for r in moved} | {u.was.get(r) for r in moved}
    gear = {u.v.gid[u.row(e)] for e in u.entries if e['team'] in clubs and u.is_goalie(u.row(e))}
    gear_rep = goalie_gear.apply_plan(db, {g: x for g, x in pl.items() if g in gear})
    db.fix()

    bad = verify(db, u.touched)
    if Tdb(bytes(db.d), meta).verify():
        bad.append('CRC базы')
    v0, v1 = View(Tdb(raw0, meta)), View(db)
    rep = {'date': fmt(date), 'db': db_path, 'save': save, 'lines_from': updated[0][:10], 'lines_to': updated[-1][:10],
           'trades': st, 'moves': u.moves, 'no_data': no_data, 'letters': letters, 'numbers': numbers,
           'contracts': contracts_rep, 'other_clubs': other,
           'notes': [f'{n[1]}: страница числит {n[2]}, но он в {n[3]} (страница старше)' for n in u.notes if n[0] == 'stale']
           + [f'{u.abbr(n[1])}: нападающих {n[2]}, защитников {n[3]}: в звеньях недостающего играет другое амплуа'
              for n in u.notes if n[0] == 'short']
           + [f"Экипировка вратарей: изменено у {gear_rep[0]}"] + [f'Взят запасной вратарь: {u.name(r)}' for r in u.loans],
           'payroll': payroll(db, v1), 'payroll_before': payroll(v0.db, v0), 'clubs': {}, 'new_players': []}
    rep['api_away'], rep['api_extra'] = u.check_api(rosters, src)
    rep['by_card'] = [x for x in extra if x['to']]
    rep['stayed'] = [x for x in extra if not x['to']]
    spec_by = {(norm(s['first'] + ' ' + s['last'])): s for s in specs}
    for r, o in new_out.items():
        s = spec_by.get(norm(o['name']), {})
        rep['new_players'].append({'name': o['name'], 'team': o.get('team'), 'jersey': o.get('jersey'), 'ovr': o.get('ovr_game'),
                                   'rating': s.get('_rating_source'), 'contract': s.get('_contract_source'),
                                   'sources': s.get('_sources'), 'why': s.get('_why')})
    for abbr, t in TEAM_SLOT.items():
        c = club_diff(v0, v1, t)
        c['info'] = info.get(abbr, {})
        rep['clubs'][abbr] = c
    write_report(os.path.join(a.out, 'report.md'), rep)
    json.dump(rep, open(os.path.join(a.out, 'report.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1, default=str)
    log(f"переводов {len(u.moves)}; новых {len(new_out)}; не найдено {len(no_data)}; проверки: {len(bad)} проблем; "
        f"база {'как была: все сделки и звенья уже в ней' if bytes(db.d) == raw0 else 'изменилась'}")
    for b in bad[:30]:
        log('  ' + b)
    if bad:
        raise SystemExit('проверки не прошли: ничего не записано (отчёт — в папке out)')
    if a.dry_run:
        log(f"проба: база и сейв не записаны; отчёт — {os.path.join(a.out, 'report.md')}")
        return 0

    dbdir = os.path.join(a.out, 'db')
    os.makedirs(dbdir, exist_ok=True)
    new_db = os.path.join(dbdir, 'nhlng.db')
    with open(new_db + '.part', 'wb') as f:
        f.write(db.d)
    os.replace(new_db + '.part', new_db)
    shutil.copy2(meta_path, os.path.join(dbdir, 'nhlng-meta.xml'))
    dr = os.path.join(dbdir, 'draft_roster.db')
    with open(dr + '.part', 'wb') as f:
        f.write(draft_roster.extract(db, set(draft_roster.KEEP)))
    os.replace(dr + '.part', dr)
    out_roster = os.path.join(a.out, f'ROSTER {fmt(date)}')
    shutil.copy2(save, out_roster)
    roster_merge.run(out_roster, db_path, new_db, True, os.path.join(a.out, 'merge.json'))
    sf = SaveFile(open(out_roster, 'rb').read(), meta)
    if sf.verify():
        raise SystemExit(f'сейв не прошёл проверку: {sf.verify()[:3]}')
    launcher = next((x for x in ([a.launcher] if a.launcher else LAUNCHERS) if x and os.path.isfile(x)), None)
    if launcher:
        code = launcher_check(launcher, out_roster, dbdir, a.work, log)
        if code:
            raise SystemExit(f'лаунчер не принял ростер, код {code}')
    else:
        log('лаунчер не найден: --check-roster пропущен')
    log(f'готово: {out_roster}\nбаза: {new_db}\nотчёт: {os.path.join(a.out, "report.md")}')
    with open(os.path.join(a.out, 'report.md'), 'a', encoding='utf-8') as f:
        f.write(install_text(out_roster, dbdir, launcher))
    return 0


def main(argv=None):
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
    ap = argparse.ArgumentParser(prog='roster_update.py', description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    sub.add_parser('example', help='напечатать образец спеки трейдов')
    r = sub.add_parser('run', help='трейды, звенья, база и ROSTER')
    r.add_argument('--trades', default=os.path.join(WORK, 'trades.txt'), help='спека трейдов (по умолчанию %(default)s)')
    r.add_argument('--work', default=WORK, help='рабочая папка: new-players.json (по умолчанию %(default)s)')
    r.add_argument('--out', default=os.path.join(WORK, 'out'), help='куда писать (по умолчанию %(default)s)')
    r.add_argument('--db', help='база, на которой сделан сейв (по умолчанию установленная); схема — рядом')
    r.add_argument('--save', help='файл ROSTER (по умолчанию новейший у пользователя)')
    r.add_argument('--date', type=lambda s: parse_date(s, '--date'), help='дата данных ДД.ММ.ГГГГ (по умолчанию сама)')
    r.add_argument('--fetch-lines', action='store_true',
                   help='скачать заново страницы звеньев (33 запроса), списки клубов (32) и карточки спорных игроков')
    r.add_argument('--no-new', action='store_true', help='не добавлять игроков, которых нет в базе')
    r.add_argument('--launcher', help='лаунчер для --check-roster (по умолчанию свежая сборка)')
    r.add_argument('--dry-run', action='store_true', help='всё посчитать, записать только отчёт')
    a = ap.parse_args(argv)
    if a.cmd == 'example':
        print(open(EXAMPLE, encoding='utf-8').read())
        return 0
    try:
        return run(a)
    except (SpecError, AP.SpecError) as e:
        sys.exit(f'ошибка: {e}')


if __name__ == '__main__':
    sys.exit(main())
