"""Общее для конвейера составов: пути, вежливые GET-запросы с кэшем, имена, команды.

Каталог game/ (файлы игры, базы, кэш API) — не в git. В отдельной рабочей копии git
(worktree) его нет: тогда берётся game/ основной копии (по файлу .git). Переопределить —
переменной окружения NHL13_GAME.
"""
import http.client, json, os, sys, time, unicodedata, urllib.error, urllib.parse, urllib.request

TOOLS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(TOOLS)
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)          # tdb.py, tdb_read.py

import gameprofile                     # noqa: E402  (tools/gameprofile.py: nhl13 или legacy)

GAME = gameprofile.get()               # профиль игры (NHL_GAME или nhl13); cli: --game legacy → set_game

SEASON = 20262027                      # сезон составов
SEASON_YEAR = 2026                     # «сейчас» игры (season_year порта)
UA = 'Mozilla/5.0 (megarohas_nhl13 roster pipeline; personal, non-commercial)'


def main_repo():
    """Корень основной рабочей копии (для worktree — по строке gitdir в файле .git)."""
    git = os.path.join(REPO, '.git')
    if os.path.isfile(git):
        line = open(git, encoding='utf-8').read().strip()
        if line.startswith('gitdir:'):
            gitdir = os.path.normpath(line.split(':', 1)[1].strip())
            parts = gitdir.split(os.sep)
            if 'worktrees' in parts:
                return os.sep.join(parts[:parts.index('worktrees') - 1])
    return REPO


def game_dir():
    env = os.environ.get('NHL13_GAME')
    if env:
        return env
    for root in (REPO, main_repo()):
        p = os.path.join(root, 'game')
        if os.path.isdir(p):
            return p
    return os.path.join(REPO, 'game')


def set_game(name):
    """Игра конвейера (до импорта этапов: dbview и др. берут номера строк и поля при импорте)."""
    global GAME, AHL_CLUBS
    GAME = gameprofile.get(name)
    # у NHL Legacy (база tools/nhl32.py --game legacy --ahl32) фарм-клубы — на Custom 02/03 = 224/225
    AHL_CLUBS = (dict(zip(GAME.custom[2:4], _AHL_CLUBS_NHL13.values())) if GAME.name == 'legacy'
                 else dict(_AHL_CLUBS_NHL13))
    return GAME


def ref_meta():
    """Схема nhlng-meta.xml из анкеров nhl-modding-studio (ref/ — не в git); у Legacy — схема игры."""
    if GAME.name != 'nhl13':
        return GAME.meta
    for root in (REPO, main_repo()):
        p = os.path.join(root, 'ref', 'nhl-modding-studio', 'anchors', 'xbox360', 'nhl13', 'databases',
                         'nhlng-meta.xml')
        if os.path.exists(p):
            return p
    return None


class Paths:
    def __init__(self, game=None, work=None):
        """`work` — папка промежуточных файлов, отчётов и выходной базы: абсолютный путь или
        имя внутри game/work/ («roster-lines», можно и «game/work/roster-lines»); по умолчанию
        game/work/roster."""
        self.game = game or game_dir()
        # Legacy: всё своё — в game/work/legacy-data/ (кэш сети roster-cache — общий: данные не зависят от игры)
        legacy = GAME.name == 'legacy'
        base = os.path.join(self.game, 'work', 'legacy-data') if legacy else os.path.join(self.game, 'work')
        self.cache = os.path.join(self.game, 'work', 'roster-cache')
        if work and not os.path.isabs(work):
            parts = [x for x in os.path.normpath(work).split(os.sep) if x not in ('', '.')]
            if [x.lower() for x in parts[:2]] == ['game', 'work']:
                parts = parts[2:]
            if legacy and [x.lower() for x in parts[:1]] == ['legacy-data']:
                parts = parts[1:]
            work = os.path.join(base, *parts) if parts else None
        self.work = work or os.path.join(base, 'roster')
        self.db_in = os.path.join(base, 'nhl32', 'nhlng.db')
        self.db_orig = (GAME.db if legacy else
                        os.path.join(self.game, 'extracted', 'big', 'cache', 'db', 'nhlng.db'))
        self.db_out = os.path.join(self.work, 'nhlng.db')
        self.players = os.path.join(self.work, 'players.json')
        self.lines = os.path.join(self.work, 'lines.json')
        self.matched = os.path.join(self.work, 'match.json')
        self.written = os.path.join(self.work, 'write.json')
        self.report = os.path.join(self.work, 'report.md')
        self.report_lines = os.path.join(self.work, 'report-lines.md')
        self.registry = os.path.join(self.work, 'artid-registry.json')
        # artid новых игроков общие для всех папок: в новой папке таблица берётся из основной
        self.registry_main = os.path.join(base, 'roster', 'artid-registry.json')
        self.ahl = False                # --ahl32: ещё и клубы АХЛ из AHL_CLUBS (составы из Wikipedia)
        self.stats_ratings = False      # --stats-ratings: OVR по статистике (statsrating.py)
        self.fa = False                 # --fa: свободные агенты (fa.py)
        self.skin = False               # --skin: голова под тон кожи на фото (skin.py)
        self.league = None              # --league liiga: клубы европейской лиги нынешними составами (league.py)
        self.payroll_max = None         # --payroll-max МЛН: ведомость состава клуба НХЛ не выше (write.cap_payroll)
        self.fa_only = False            # --fa-only: в пуле свободных агентов — только настоящие (--fa)
        self.retire_veterans = None     # --retire-veterans ГОД: ушедшие из НХЛ ≤ ГОД г. р. — на пенсию (write)
        self.report_ratings = os.path.join(self.work, 'report-ratings.md')

    def meta_for(self, db_path):
        """Схема рядом с базой (nhl32 кладёт свою, с вместимостью франшизы), иначе анкер."""
        p = os.path.join(os.path.dirname(db_path), 'nhlng-meta.xml')
        return p if os.path.exists(p) else ref_meta()


# --- HTTP -------------------------------------------------------------------------------------
class Offline(Exception):
    """Ответа нет в кэше, а сеть запрещена (--offline)."""


class Http:
    """GET с кэшем на диске: повторный прогон сеть не трогает. Пауза между запросами к
    одному хосту — не меньше `pause` секунд; на 429/5xx — повтор с растущей паузой;
    редиректы 301–308 urllib проходит сам. 404 запоминается (файл .404)."""

    def __init__(self, cache, pause=1.0, offline=False, refresh=False, log=print):
        self.cache, self.pause, self.offline, self.refresh, self.log = cache, pause, offline, refresh, log
        self.last = {}
        self.requests = 0

    def path(self, rel):
        return os.path.join(self.cache, *rel.split('/'))

    def cached(self, rel):
        fn = self.path(rel)
        return os.path.exists(fn) or os.path.exists(fn + '.404')

    def get(self, url, rel, refresh=None):
        """Тело ответа (bytes) или None для 404. `rel` — путь файла в кэше."""
        fn = self.path(rel)
        refresh = self.refresh if refresh is None else refresh
        if not refresh:
            if os.path.exists(fn):
                with open(fn, 'rb') as f:
                    return f.read()
            if os.path.exists(fn + '.404'):
                return None
        if self.offline:
            raise Offline(f'нет в кэше: {rel} ({url})')
        host = urllib.parse.urlsplit(url).hostname
        body = None
        for attempt in range(7):
            wait = self.pause - (time.time() - self.last.get(host, 0))
            if wait > 0:
                time.sleep(wait)
            try:
                req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept-Language': 'en-US,en;q=0.8'})
                with urllib.request.urlopen(req, timeout=60) as r:
                    body = r.read()
                self.last[host] = time.time()
                break
            except urllib.error.HTTPError as err:
                self.last[host] = time.time()
                if err.code == 404:
                    os.makedirs(os.path.dirname(fn), exist_ok=True)
                    open(fn + '.404', 'w').close()
                    self.requests += 1
                    return None
                if err.code not in (403, 429, 500, 502, 503, 504) or attempt == 6:
                    raise
                delay = min(120, 5 * 2 ** attempt)
                self.log(f'  HTTP {err.code} {url} — пауза {delay} с')
                time.sleep(delay)
            except (urllib.error.URLError, http.client.HTTPException, TimeoutError, ConnectionError, OSError) as err:
                self.last[host] = time.time()
                if attempt == 6:
                    raise
                delay = min(60, 3 * 2 ** attempt)
                self.log(f'  сеть: {err} — пауза {delay} с')
                time.sleep(delay)
        self.requests += 1
        os.makedirs(os.path.dirname(fn), exist_ok=True)
        tmp = fn + '.part'
        with open(tmp, 'wb') as f:
            f.write(body)
        os.replace(tmp, fn)
        return body

    def json(self, url, rel, refresh=None):
        body = self.get(url, rel, refresh)
        return None if body is None else json.loads(body)

    def text(self, url, rel, refresh=None):
        body = self.get(url, rel, refresh)
        return None if body is None else body.decode('utf-8', 'replace')


def read_json(path, default=None):
    if not os.path.exists(path):
        return default
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + '.part'
    with open(tmp, 'w', encoding='utf-8', newline='\n') as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


# --- имена ------------------------------------------------------------------------------------
# буквы, которые NFKD не раскладывает на основу и знак (как в puckpeak matching.py, MIT)
SPELLED_OUT = str.maketrans({'ø': 'o', 'Ø': 'O', 'æ': 'ae', 'Æ': 'AE', 'œ': 'oe', 'Œ': 'OE', 'ß': 'ss',
                             'đ': 'd', 'Đ': 'D', 'ð': 'd', 'Ð': 'D', 'þ': 'th', 'Þ': 'Th', 'ł': 'l',
                             'Ł': 'L', 'ı': 'i'})


def norm(s):
    """Имя для сравнения: без диакритики, регистра, пробелов и знаков."""
    s = unicodedata.normalize('NFKD', (s or '').translate(SPELLED_OUT)).encode('ascii', 'ignore').decode().lower()
    return ''.join(ch for ch in s if ch.isalnum())


def fit_utf8(text, limit):
    """Строка, обрезанная до `limit` байт UTF-8 (по целым символам)."""
    text = (text or '').strip()
    while len(text.encode('utf-8')) > limit:
        text = text[:-1]
    return text


# --- команды ----------------------------------------------------------------------------------
# аббревиатура NHL.com → строка exhibitionteams (база после tools/nhl32.py)
TEAM_SLOT = {
    'ANA': 0, 'WPG': 1, 'BOS': 2, 'BUF': 3, 'CGY': 4, 'CAR': 5, 'CHI': 6, 'COL': 7, 'CBJ': 8, 'DAL': 9,
    'DET': 10, 'EDM': 11, 'FLA': 12, 'LAK': 13, 'MIN': 14, 'MTL': 15, 'NSH': 16, 'NJD': 17, 'NYI': 18,
    'NYR': 19, 'OTT': 20, 'PHI': 21, 'UTA': 22, 'PIT': 23, 'STL': 24, 'SJS': 25, 'TBL': 26, 'TOR': 27,
    'VAN': 28, 'WSH': 29, 'SEA': 30, 'VGK': 31,
}
SLOT_TEAM = {v: k for k, v in TEAM_SLOT.items()}
# Клубы АХЛ, которые конвейер заполняет сам (--ahl32; база tools/nhl32.py --ahl32, там те же строки
# в AHL_NEW): строка exhibitionteams → аббревиатура, клуб-хозяин в НХЛ, статья Wikipedia с составом.
AHL_CLUBS = {
    220: dict(abbr='CV', name='Coachella Valley Firebirds', wiki='Coachella_Valley_Firebirds', parent='SEA',
              parent_nick='Kraken'),
    221: dict(abbr='HSK', name='Henderson Silver Knights', wiki='Henderson_Silver_Knights', parent='VGK',
              parent_nick='Golden Knights'),
}
_AHL_CLUBS_NHL13 = dict(AHL_CLUBS)
# прежние и сменившие город клубы → нынешний слот (для команды драфта)
TEAM_ALIAS = {'PHX': 'UTA', 'ARI': 'UTA', 'ATL': 'WPG', 'L.A': 'LAK', 'N.J': 'NJD', 'S.J': 'SJS', 'T.B': 'TBL',
              'LA': 'LAK', 'NJ': 'NJD', 'SJ': 'SJS', 'TB': 'TBL', 'MDA': 'ANA', 'HFD': 'CAR', 'QUE': 'COL',
              'MNS': 'DAL', 'WIN': 'UTA'}
TEAM_NAMES = {
    'ANA': 'Anaheim Ducks', 'BOS': 'Boston Bruins', 'BUF': 'Buffalo Sabres', 'CGY': 'Calgary Flames',
    'CAR': 'Carolina Hurricanes', 'CHI': 'Chicago Blackhawks', 'COL': 'Colorado Avalanche',
    'CBJ': 'Columbus Blue Jackets', 'DAL': 'Dallas Stars', 'DET': 'Detroit Red Wings', 'EDM': 'Edmonton Oilers',
    'FLA': 'Florida Panthers', 'LAK': 'Los Angeles Kings', 'MIN': 'Minnesota Wild', 'MTL': 'Montreal Canadiens',
    'NSH': 'Nashville Predators', 'NJD': 'New Jersey Devils', 'NYI': 'New York Islanders', 'NYR': 'New York Rangers',
    'OTT': 'Ottawa Senators', 'PHI': 'Philadelphia Flyers', 'PIT': 'Pittsburgh Penguins', 'SJS': 'San Jose Sharks',
    'SEA': 'Seattle Kraken', 'STL': 'St. Louis Blues', 'TBL': 'Tampa Bay Lightning', 'TOR': 'Toronto Maple Leafs',
    'UTA': 'Utah Mammoth', 'VAN': 'Vancouver Canucks', 'VGK': 'Vegas Golden Knights', 'WSH': 'Washington Capitals',
    'WPG': 'Winnipeg Jets',
}
# клуб в адресах страниц: одинаково у nhlratings.net (/teams/…) и DailyFaceoff (/teams/…/line-combinations)
TEAM_URL_SLUG = {a: n.lower().replace('.', '').replace(' ', '-') for a, n in TEAM_NAMES.items()}
assert TEAM_URL_SLUG['STL'] == 'st-louis-blues' and TEAM_URL_SLUG['UTA'] == 'utah-mammoth'


def team_slot(abbr):
    abbr = (abbr or '').upper()
    return TEAM_SLOT.get(TEAM_ALIAS.get(abbr, abbr))


def _league_clubs():
    from .league import club_names           # клубы европейских лиг (--league), позднее подключение
    return club_names()


def club_abbr(slot):
    """Аббревиатура клуба по строке: НХЛ, клуб АХЛ из AHL_CLUBS или клуб лиги (--league)."""
    if slot in SLOT_TEAM:
        return SLOT_TEAM[slot]
    if slot in AHL_CLUBS:
        return AHL_CLUBS[slot]['abbr']
    return _league_clubs()[slot][0]


def club_name(abbr):
    return (TEAM_NAMES.get(abbr) or next((c['name'] for c in AHL_CLUBS.values() if c['abbr'] == abbr), None)
            or next(n for a, n in _league_clubs().values() if a == abbr))
