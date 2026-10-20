"""Сейв франшизы NHL Legacy (DYNASTY, ZlibV4) для Кубка наций: только чтение.

    from natcup.franchise import Franchise
    f = Franchise.load(путь)          # или Franchise.latest(папка_сейвов)
    f.user_team, f.players, f.teams

Игрок: index (= index в leagueplayerbiotable и в leagueskaterai / leaguegoalieai), имя, позиция, страна
(intlcountry), команда (teamid лиги), OVR — точная формула игры (roster.ovrformula.game_ovr) по текущим атрибутам c_*.
Команда пользователя — leaguestates type 4 key 24 (НХЛ) / 25 (АХЛ), docs/legacy-port.md.
"""
import glob
import os
import sys
import tempfile

TOOLS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)
os.environ.setdefault('NHL_GAME', 'legacy')

import tdb as TD                      # noqa: E402
import tdb_read as T                  # noqa: E402
from roster.ovrformula import game_ovr  # noqa: E402
from roster.ratings import BASE, GK, SK, cls  # noqa: E402

REPO = os.path.dirname(TOOLS)
META = os.path.join(REPO, 'nhl-legacy-port', 'userdata', 'cache', 'guest', 'db', 'nhlng-meta.xml')
SAVES = os.path.join(REPO, 'nhl-legacy-port', 'userdata', 'B13EBABEBABEBABE', '454109EC', '00000001')
POS = {0: 'C', 1: 'L', 2: 'R', 3: 'D', 4: 'G'}

# intlcountry → сборная (exhibitionteams, лига 8): код страны игрока, teamid сборной, имя
NATIONS = {
    0: (135, 'Canada'), 14: (153, 'USA'), 67: (138, 'Finland'), 69: (150, 'Sweden'), 82: (136, 'Czech Republic'),
    97: (151, 'Switzerland'), 85: (140, 'Germany'), 76: (148, 'Russia'), 95: (149, 'Slovakia'), 68: (146, 'Norway'),
    70: (134, 'Belarus'), 74: (145, 'Latvia'), 66: (137, 'Denmark'), 87: (142, 'Italy'), 91: (147, 'Poland'),
    77: (152, 'Ukraine'), 83: (141, 'Great Britain'), 109: (143, 'Japan'), 84: (139, 'France'), 72: (144, 'Kazakstan'),
    78: (133, 'Austria'),
}


def _text(d, tinfo, fname, r):
    rows, reclen, rb, fds, fmeta = tinfo
    for kind, bitoff, fid, w in fds:
        if fmeta.get(fid, (fid,))[0] == fname:
            rec = d[rb + r * reclen: rb + (r + 1) * reclen]
            return rec[bitoff // 8:(bitoff + w) // 8].split(b'\0')[0].decode('utf-8', 'replace')
    raise KeyError(fname)


class Franchise:
    def __init__(self, path, d, tb):
        self.path, self.d, self.tb = path, d, tb
        self.states = self._states()
        self.user_team = self.states.get((4, 24))
        self.user_farm = self.states.get((4, 25))
        self.teams = self._teams()
        self.players = self._players()

    @classmethod
    def load(cls_, path, meta=META):
        z = TD.ZlibV4(open(path, 'rb').read())
        fd, tmp = tempfile.mkstemp(suffix='.db', dir=os.path.join(REPO, 'game', 'work'))
        try:
            with os.fdopen(fd, 'wb') as f:
                f.write(z.inflated[:z.db_size])
            d, tb = T.read_db(tmp, T.load_meta(meta))
        finally:
            os.remove(tmp)
        return cls_(path, d, tb)

    @classmethod
    def latest(cls_, folder=SAVES):
        saves = sorted(glob.glob(os.path.join(folder, 'DYNASTY *', 'DYNASTY *')), key=os.path.getmtime)
        if not saves:
            raise FileNotFoundError(f'нет сейвов франшизы в {folder}')
        return cls_.load(saves[-1])

    # --- таблицы
    def col(self, table, field):
        return T.column(self.d, self.tb[table], field, live_only=True)

    def rows(self, table):
        return T.live_rows(self.d, self.tb[table])

    def _states(self):
        return {(a, b): c for a, b, c in zip(self.col('leaguestates', 'type'), self.col('leaguestates', 'key'),
                                              self.col('leaguestates', 'value'))}

    def _teams(self):
        t = 'leagueteams'
        out = {}
        for r, tid, lg in zip(self.rows(t), self.col(t, 'teamid'), self.col(t, 'league')):
            out[tid] = {'teamid': tid, 'league': lg, 'name': _text(self.d, self.tb[t], 'fullname', r),
                        'abbr': _text(self.d, self.tb[t], 'abbrname', r)}
        return out

    def _ai(self, table, names):
        idx = self.col(table, 'index')
        cols = {n: self.col(table, 'c_' + n.split('_', 1)[1]) for n in names}
        return {p: {n: cols[n][i] + BASE for n in names} for i, p in enumerate(idx)}

    def _players(self):
        t = 'leagueplayerbiotable'
        sk, gk = self._ai('leagueskaterai', SK), self._ai('leaguegoalieai', GK)
        cols = {f: self.col(t, f) for f in ('index', 'position', 'intlcountry', 'team', 'year', 'month', 'day',
                                            'birthplace', 'injurydaysleft')}
        out = []
        for i, r in enumerate(self.rows(t)):
            p = cols['index'][i]
            pos = POS.get(cols['position'][i], '?')
            c = cls(pos) if pos in 'CLRDG' else None
            attrs = (gk if c == 'G' else sk).get(p)
            out.append({
                'index': p, 'first': _text(self.d, self.tb[t], 'firstname', r),
                'last': _text(self.d, self.tb[t], 'lastname', r), 'pos': pos, 'country': cols['intlcountry'][i],
                'team': cols['team'][i] - 1,           # teamid (−1 — без клуба); в базе поле = teamid + 1
                'born': (1900 + cols['year'][i], cols['month'][i] + 1, cols['day'][i]),
                'injury_days': cols['injurydaysleft'][i],
                'ovr': game_ovr(c, attrs) if (c and attrs) else None,
            })
        return out

    def season_year(self, base=2026):
        """Год начала текущего сезона: season_year порта + номер сезона франшизы (leagueteamseasonstats.year)."""
        yrs = self.col('leagueteamseasonstats', 'year')
        return base + (max(yrs) if yrs else 0)

    def team_abbr(self, tid):
        return self.teams.get(tid, {}).get('abbr', '') if tid >= 0 else 'FA'

    # --- для Кубка наций
    def pool(self, country):
        """Игроки страны (по intlcountry) с OVR, лучшие первыми."""
        return sorted((p for p in self.players if p['country'] == country and p['ovr']), key=lambda p: -p['ovr'])


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    f = Franchise.load(sys.argv[1]) if len(sys.argv) > 1 else Franchise.latest()
    print(os.path.basename(f.path), 'команда пользователя', f.user_team, f.teams.get(f.user_team, {}).get('name'),
          'игроков', len(f.players))
    for code in (0, 14, 76, 69, 67, 82):
        top = f.pool(code)[:6]
        print(NATIONS[code][1], len(f.pool(code)), ', '.join(f"{p['first']} {p['last']} {p['pos']} {p['ovr']}" for p in top))
