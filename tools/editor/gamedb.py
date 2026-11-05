"""Имена для редактора: клубы, формы, игроки — из того, что игра реально грузит (новейший ROSTER поверх базы).

База — content\\…\\db\\nhlng.db (через gamefs: content\\my главнее), схема — nhlng-meta.xml рядом. Сейв ROSTER хранит
составы, формы клубов и экипировку сам (docs/uniforms.md, docs/launcher.md «Как игра выбирает ростер»), поэтому
списки форм и игроков берутся из новейшего ROSTER, если он есть; без него — из базы. Только чтение.
"""
import os
import re
import sys
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

from tdb import SaveFile, Tdb  # noqa: E402
from tdb_read import load_meta  # noqa: E402

LEAGUES = {0: 'NHL', 1: 'AHL', 2: 'SHL', 3: 'Liiga', 4: 'DEL', 5: 'Extraliga', 6: 'National League', 7: 'Norway',
           8: 'International', 9: 'OHL', 10: 'QMJHL', 11: 'WHL', 12: 'Top Prospects', 13: 'Custom', 14: 'Winter Classic',
           15: 'EASHL'}
LEAGUE_RU = {8: 'Сборные', 12: 'Проспекты', 13: 'Свои команды', 14: 'Зимняя классика'}
ALLSTAR = (222, 223)

# stockteamjerseys.locstring → подпись (docs/kitport.md §2.7)
LOC = {0: ('Дом', 'Home'), 1: ('Выезд', 'Away'), 2: ('Третья', 'Third'), 3: ('2006/07, дом', '2006/07 home'),
       4: ('2006/07, выезд', '2006/07 away'), 5: ('2006/07, третья', '2006/07 third'), 6: ('Винтаж', 'Vintage')}
STYLE = {0: 'ретро / retro', 1: 'Edge', 2: 'NHL 27'}
POS = {0: 'C', 1: 'LW', 2: 'RW', 3: 'D', 4: 'G'}


def clean(name):
    return re.sub(r'[®™]', '', name or '').strip()


class GameDb:
    def __init__(self, fs):
        self.fs = fs
        self.lock = threading.Lock()
        self.loaded = False
        self.error = None
        self.source = None
        self.meta_path = None
        self.db_path = None
        self.roster_path = None

    def load(self, force=False):
        with self.lock:
            if self.loaded and not force:
                return
            self._load()
            self.loaded = True

    def _load(self):
        fs = self.fs
        hit = fs.find('db/nhlng.db')
        meta = fs.find('db/nhlng-meta.xml')
        self.teams, self.kits, self.players, self.members, self.arenas = {}, {}, {}, {}, {}
        if not hit or not meta or not hit[2] or not meta[2]:
            self.error = 'нет базы content\\database\\db\\nhlng.db'
            return
        self.db_path, self.meta_path = hit[2], meta[2]
        self.meta = load_meta(self.meta_path)
        db = Tdb(open(self.db_path, 'rb').read(), self.meta)
        live = None
        try:
            r = fs.saves.latest('ROSTER')
            sf = SaveFile(open(r.file, 'rb').read(), self.meta)
            live, self.roster_path = sf.db, r.file
            self.source = 'roster'
        except Exception:                                   # noqa: BLE001  (нет ростера или чужой — база)
            self.source = 'db'
        self.db = db
        src = live or db
        self.src = src
        rows = lambda d, t: d.live_rows(t) if t in d.by_name else []   # noqa: E731
        v = src.value
        T = 'exhibitionteams'
        for r in rows(src, T):
            i = v(T, 'index', r)
            self.teams[i] = dict(index=i, name=clean(v(T, 'fullname', r)), abbr=v(T, 'abbrname', r),
                                 league=v(T, 'league', r), artid=v(T, 'artid', r), active=v(T, 'active', r),
                                 table=v(T, 'table', r), arena=v(T, 'arenaid', r))
        J = 'stockteamjerseys'
        jsrc = src if J in src.by_name else db
        for r in rows(jsrc, J):
            g = lambda f: jsrc.value(J, f, r)                # noqa: E731
            k = dict(team=g('teamid'), s=g('style'), a=g('teamartid'), v=g('variant'), f=g('fevariant'),
                     loc=g('locstring'), light=g('islightcolor'), default=g('isdefault'), helmetlogo=g('helmetlogo'),
                     index=g('jerseyindex'))
            self.kits.setdefault(k['team'], []).append(k)
        for t in self.kits.values():
            t.sort(key=lambda k: (k['index'], k['s'], k['v']))
        A = 'exhibitionarena'
        asrc = src if A in src.by_name else db
        for r in rows(asrc, A):
            i = asrc.value(A, 'index', r)
            self.arenas[i] = dict(index=i, name=clean(asrc.value(A, 'arenaname', r)),
                                  city=asrc.value(A, 'cityname', r), art=asrc.value(A, 'arenaartid', r))
        B = 'exhibitionplayerbiotable'
        for r in rows(src, B):
            g = lambda f: src.value(B, f, r)                 # noqa: E731
            gid = g('game_id')
            self.players[gid] = dict(gid=gid, first=g('firstname'), last=g('lastname'), artid=g('artid'),
                                     headid=g('headid'), portrait=g('hasportrait'), pos=POS.get(g('position'), '?'),
                                     jersey=g('jersey'), team=g('team') - 1)
        P, R = 'exhibitionplayers', 'exhibitionrostertable'
        link = {src.get(P, 'index', r): src.get(P, 'playerid', r) for r in rows(src, P)}
        for r in rows(src, R):
            gid = link.get(src.get(R, 'playerindex', r))
            if gid in self.players:
                self.members.setdefault(src.get(R, 'team', r), []).append(gid)

    # ------------------------------------------------------------ выборки
    def league_name(self, code, lang='ru'):
        if lang == 'ru' and code in LEAGUE_RU:
            return LEAGUE_RU[code]
        return LEAGUES.get(code, f'#{code}')

    def leagues(self):
        """[(код, [клубы])] — клубы активные, не Custom, по порядку лиги."""
        out = {}
        for t in self.teams.values():
            if t['table'] == 1 or not t['active'] or not t['name']:
                continue
            code = 99 if t['index'] in ALLSTAR else t['league']
            out.setdefault(code, []).append(t)
        res = []
        for code in sorted(out):
            res.append((code, sorted(out[code], key=lambda t: t['name'])))
        return res

    def team(self, i):
        return self.teams.get(i)

    def kit_label(self, k, lang='ru'):
        loc = LOC.get(k['loc'], (f'форма {k["loc"]}', f'kit {k["loc"]}'))[0 if lang == 'ru' else 1]
        st = {0: 'ретро' if lang == 'ru' else 'retro', 1: 'Edge', 2: 'NHL 27'}.get(k['s'], str(k['s']))
        return f'{loc} · {st} · {k["s"]}_{k["a"]}_{k["v"]}'

    def roster(self, team):
        return [self.players[g] for g in self.members.get(team, []) if g in self.players]

    def player_name(self, gid):
        p = self.players.get(gid)
        return f'{p["first"]} {p["last"]}' if p else str(gid)
