"""Внешняя экипировка игроков по фото: обмотка клюшки, заправка гетр, свитер, визор.

    cd tools
    python -m roster.equipment fetch   [--team PIT,BOS]            # экшн-фото НХЛ → roster-cache/photos/action/
    python -m roster.equipment todo    --team PIT [--commons]      # кого ещё не смотрели (фото НХЛ / кадры Commons)
    python -m roster.equipment zoom    ID|ФАЙЛ X0,Y0,X1,Y1 [X0,Y0,X1,Y1 …] [--height 420] [--out PNG]
                                                                  # кадры фото крупно (Chrome без окна)
    python -m roster.equipment commons --team PIT [--max 4]        # кадры Wikimedia Commons тем, кому фото НХЛ не хватило
    python -m roster.equipment csheet  ID [--out PNG]              # кадры Commons игрока одной картинкой (выбор)
    python -m roster.equipment record  FILE.json [--by ИМЯ]        # наблюдения → equipment.json (без сети)
    python -m roster.equipment meta                                # автор и лицензия использованных кадров Commons
    python -m roster.equipment status                              # охват по клубам и полям
    python -m roster.equipment sheet   [--team PIT] [--db DB] [--out HTML] [--visor-rule] [--jersey-rule]
                                                                  # лист проверки equipment/sheet.html
    python -m roster.equipment apply   DB_IN DB_OUT [--min-conf high|med] [--fields tape,socks,jersey,visor]
                                       [--visor-rule] [--jersey-rule] [--dry-run] [--report JSON]
    python -m roster.equipment roster  SAVE --report JSON [--meta XML] [--write]
                                                                  # отчёт apply → сохранённый состав игры (ROSTER)

Общие опции (до команды): --work ПАПКА — папка конвейера с write.json (по умолчанию roster-expanded-ahl32;
roster-expanded, roster-custom…), --game — каталог game/.

Источники правды — фото, ничего не угадывается:
1. `heroImage` карточки игрока API НХЛ (кэш roster-cache/nhl/landing/<id>.json) — экшн-кадр 1296×729 с
   assets.nhle.com; кэш game/work/roster-cache/photos/action/<id>.jpg (вне git, для личного
   использования). У игроков без своего кадра CDN отдаёт общую заглушку клуба (фото арены) — один и
   тот же файл у нескольких игроков: «нет фото».
2. Wikimedia Commons (свободные лицензии) — тем, у кого на фото НХЛ не видно обмотки или коньков.
   robots.txt Commons закрывает /w/ (api.php) и /api/, поэтому только страницы: категория игрока
   /wiki/Category:<Имя> (варианты «(ice hockey, born ГГГГ)», «(ice hockey)»; берётся, только если среди
   её категорий есть хоккейная или клуб НХЛ), из неё — до --max самых свежих снимков (год — из имени
   файла), уменьшенная копия 1280 px с upload.wikimedia.org; автор и лицензия — из
   /wiki/File:…?action=raw (шаблоны {{Information}}, {{cc-…}}) — только у использованных снимков.
   Пауза ≥ 1 с на хост, User-Agent конвейера, кэш game/work/roster-cache/photos/commons/.
   Кто на снимке — проверяет смотрящий (номер, клуб, подпись файла).

Наблюдения копятся в game/work/roster-cache/equipment/equipment.json: nhl_id → поля, уверенность
(high/med/low), рамки крюка и коньков (для листа проверки), источник (фото НХЛ или файл Commons с
автором и лицензией). Повторный проход пропускает уже записанных. Вход `record` — список JSON:

    [{"id": 8471675, "tape": "black/high", "tongue": "hidden/high", "heel": "?", "jersey": "none/high",
      "visor": "clear/high", "blade": [207, 318, 335, 400], "skates": [630, 475, 1150, 700], "note": ""},
     {"id": 8478438, "src": "File:Tommy Novak 2026.jpg", "tape": "white/high", "blade": [..]},  # кадр Commons
     {"id": 8478438, "src": "commons", "photo": "none", "note": "на кадрах нет крюка"}]       # Commons смотрели

    tape    black white blue red yellow green orange lightblue pink purple — цвет обмотки на крюке
    tongue  out (язык конька торчит поверх гетры) | hidden (языка не видно, гетра закрывает верх ботинка)
    heel    tucked (сзади гетра заправлена в ботинок) | over (сзади гетра поверх ботинка)
    jersey  none | left | right | full — заправка свитера в шорты (сторона — самого игрока)
    visor   clear | tinted | none
    photo   none — на фото нет этого игрока (заглушка, чужой кадр): все поля «?»
Итог по полю — самое уверенное наблюдение из всех источников (при равной уверенности — более свежее:
кадр НХЛ, затем Commons по году); «расхождение» (low, не применяется, видно на листе) — если другое
значение med+ так же уверено или из более свежего источника.

Коды базы (exhibitionskaterequipment; перечисления nhl-modding-studio defs/enums — те же таблица и
поля, xmja = ajmx, NISO = OSIN…, — сверены с базой NHL 13: у вратарей 84 % белой обмотки, у
полевых 75 % чёрной; Гретцки — заправка справа, у Овечкина 2012 года — тёмный визор):

    sticktapecolor  0 чёрная, 1 белая, 2 синяя, 3 красная, 4 жёлтая, 5 зелёная, 6 оранжевая,
                    7 голубая, 8 розовая, 9 фиолетовая (10–15 не заданы; в базе 2012 только 0 и 1)
    skatesocktuck   0 заправлена полностью (Full), 1 не заправлена — поверх ботинка (None), 2 спереди —
                    язык конька наружу (Front), 3 сзади — язык под гетрой (Back); по данным NHL 13: таблица
                    вариантов в образе игры {2 front, 3 backtuck, 0 full} и геометрия сеток playersock_0…3
                    (0 — самая узкая голень, 1 — самая широкая); подписи каталога NHL Legacy (0 «fully
                    untucked», 1 «fully tucked») для NHL 13 перепутаны в 0/1
    jerseytuck      0 нет, 1 слева, 2 справа, 3 полностью
    visortype       0 обычный, 1 «авиатор», 2 нет визора;  visorcolor 0 прозрачный, 1 тёмный, …

Перевод в коды (apply; берутся только наблюдения не ниже --min-conf, по умолчанию high):
    обмотка — цвет → код;
    гетры   — спереди «язык наружу» = гетра заправлена под язык, «язык не виден» = гетра поверх языка;
              сзади — в ботинке / поверх: (наружу, в ботинке) → 0, (не виден, поверх) → 1, (наружу,
              поверх) → 2, (не виден, в ботинке) → 3; видна одна сторона — значение базы остаётся, если
              с ней согласно, иначе другая сторона берётся «в ботинке» (сзади) / «гетра поверх» (спереди)
              — так на подавляющем большинстве снимков;
    свитер  — что на фото; --jersey-rule: 0 у всех игроков write.json, и у тех, у кого на старом фото
              заправка (НХЛ 2026/27 штрафует за заправку — две минуты после предупреждения);
    визор   — нет: visortype 2; есть: 0, если в базе 2 (обычный/«авиатор» по фото не различаются),
              прозрачный — visorcolor 0, тёмный — 1; --visor-rule (сведения пользователя: в НХЛ
              2026/27 без визора только Jamie Benn, Ryan O'Reilly, Zach Bogosian): у них 2, у всех
              остальных полевых визор (0, если в базе 2; «авиатор» 1 остаётся) — фото не решает; кто
              на фото уверенно без визора, но не из троих, — перечисляется в выводе и отчёте apply.
Пишутся только exhibitionskaterequipment / exhibitiongoalieequipment (у вратарей — обмотка и
свитер); CRC — tools/tdb.py; проверка: CRC, значения на месте, кроме этих полей байты не менялись.

Только стандартная библиотека (+ Chrome или Edge без окна для zoom и csheet). Подробно —
docs/player-equipment.md.
"""
import argparse
import hashlib
import html
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import unicodedata
import urllib.parse
from collections import Counter, defaultdict
from datetime import datetime

if not __package__:                     # python tools/roster/equipment.py …
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    __package__ = 'roster'

from . import common  # noqa: E402
from .common import TEAM_NAMES, Http, Paths, read_json, set_game  # noqa: E402
from .common import write_json as _write_json  # noqa: E402


def write_json(path, obj, tries=40):
    """write_json конвейера, но с повтором: в Windows замена файла не проходит, пока его читает другой
    процесс (несколько проходов сразу читают equipment.json и commons.json)."""
    for i in range(tries):
        try:
            return _write_json(path, obj)
        except PermissionError:
            if i == tries - 1:
                raise
            time.sleep(0.25)


def read_json_retry(path, default=None, tries=40):
    for i in range(tries):
        try:
            return read_json(path, default)
        except (PermissionError, json.JSONDecodeError):
            if i == tries - 1:
                raise
            time.sleep(0.25)

DEFAULT_WORK = 'roster-expanded-ahl32'
DEFAULT_WORK_LEGACY = 'roster'           # --game legacy: game/work/legacy-data/roster
VISOR_EXEMPT_T = 'stockplayervisorexempttable'   # NHL Legacy: game_id игроков, кому можно играть без визора
PHOTO_DIR = ('photos', 'action')        # внутри roster-cache
COMMONS_DIR = ('photos', 'commons')
STORE_DIR = 'equipment'
COMMONS = 'https://commons.wikimedia.org'
UPLOAD = 'https://upload.wikimedia.org/wikipedia/commons'
THUMB_W = 1280

TAPE = {'black': 0, 'white': 1, 'blue': 2, 'red': 3, 'yellow': 4, 'green': 5, 'orange': 6,
        'lightblue': 7, 'pink': 8, 'purple': 9}
TAPE_RU = {'black': 'чёрная', 'white': 'белая', 'blue': 'синяя', 'red': 'красная', 'yellow': 'жёлтая',
           'green': 'зелёная', 'orange': 'оранжевая', 'lightblue': 'голубая', 'pink': 'розовая',
           'purple': 'фиолетовая'}
TAPE_CODE_RU = {v: TAPE_RU[k] for k, v in TAPE.items()}
SOCK_RU = {0: 'полностью', 1: 'не заправлена (поверх)', 2: 'спереди (язык наружу)', 3: 'сзади (язык под гетрой)'}
JERSEY = {'none': 0, 'left': 1, 'right': 2, 'full': 3}
JERSEY_RU = {0: 'нет', 1: 'слева', 2: 'справа', 3: 'полностью'}
VISOR_RU = {0: 'обычный', 1: '«авиатор»', 2: 'нет'}
VOCAB = {
    'tape': set(TAPE),
    'tongue': {'out', 'hidden'},
    'heel': {'tucked', 'over'},
    'jersey': set(JERSEY),
    'visor': {'clear', 'tinted', 'none'},
}
OBS_RU = {'tape': 'обмотка', 'tongue': 'язык конька', 'heel': 'гетра сзади', 'jersey': 'свитер', 'visor': 'визор'}
VAL_RU = {'out': 'наружу', 'hidden': 'не виден', 'tucked': 'заправлена', 'over': 'поверх ботинка',
          'none': 'нет', 'left': 'слева', 'right': 'справа', 'full': 'полностью', 'clear': 'прозрачный',
          'tinted': 'тёмный', **TAPE_RU}
CONF = {'high': 3, 'med': 2, 'low': 1}
FIELDS = ('tape', 'socks', 'jersey', 'visor')            # поля apply (все, что умеем)
DEFAULT_FIELDS = FIELDS            # гетры подтверждены (сетки и таблица вариантов NHL 13), 08.10.2026
SOCK_CODE = {(True, True): 0, (False, False): 1, (True, False): 2, (False, True): 3}  # (спереди, сзади) → код
SOCK_FRONT = {0: True, 1: False, 2: True, 3: False}
SOCK_BACK = {0: True, 1: False, 2: False, 3: True}
GOALIE_SKIP = ('tongue', 'heel', 'visor')                # у вратарей не смотрим (щитки, маска)
VISOR_RULE_SEASON = 20132014
SKATER_T, GOALIE_T = 'exhibitionskaterequipment', 'exhibitiongoalieequipment'
TEAM_ORDER = ['ANA', 'BOS', 'BUF', 'CAR', 'CBJ', 'CGY', 'CHI', 'COL', 'DAL', 'DET', 'EDM', 'FLA', 'LAK', 'MIN',
              'MTL', 'NJD', 'NSH', 'NYI', 'NYR', 'OTT', 'PHI', 'PIT', 'SEA', 'SJS', 'STL', 'TBL', 'TOR', 'UTA',
              'VAN', 'VGK', 'WPG', 'WSH', 'CV', 'HSK', 'FA']
BOX_KEYS = ('blade', 'skates', 'head', 'waist')


# --- пути и данные -------------------------------------------------------------------------------
def store_dir(paths):
    return os.path.join(paths.cache, STORE_DIR)


def store_path(paths):
    return os.path.join(store_dir(paths), 'equipment.json')


def commons_path(paths):
    return os.path.join(store_dir(paths), 'commons.json')


def photo_rel(nid):
    return '/'.join(PHOTO_DIR + (f'{nid}.jpg',))


def photo_file(paths, nid):
    return os.path.join(paths.cache, *PHOTO_DIR, f'{nid}.jpg')


def cache_file(paths, rel):
    return os.path.join(paths.cache, *rel.split('/'))


def load_store(paths):
    st = read_json_retry(store_path(paths), None) or {}
    st.setdefault('version', 2)
    st.setdefault('players', {})
    st.setdefault('placeholders', {})
    return st


class Lock:
    """Блокировка файла между процессами (несколько проходов сразу): файл .lock рядом."""

    def __init__(self, path, timeout=180):
        self.path, self.timeout = path + '.lock', timeout

    def __enter__(self):
        t0 = time.time()
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        while True:
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, str(os.getpid()).encode())
                os.close(fd)
                return self
            except FileExistsError:
                try:
                    stale = time.time() - os.path.getmtime(self.path) > 600       # забытая блокировка
                except OSError:
                    continue
                if stale:
                    try:
                        os.remove(self.path)
                    except OSError:
                        pass
                    continue
                if time.time() - t0 > self.timeout:
                    raise SystemExit(f'занято: {self.path}')
                time.sleep(0.2)

    def __exit__(self, *exc):
        try:
            os.remove(self.path)
        except OSError:
            pass


def roster(paths, teams=None):
    """Игроки write.json конвейера (nhl_id, team, pos, game_id, jersey…) по клубам."""
    w = read_json(paths.written)
    if not w:
        raise SystemExit(f'нет {paths.written} — сначала python tools/roster write --work …')
    players = w['players']
    if teams:
        players = [p for p in players if p['team'] in teams]
    order = {t: i for i, t in enumerate(TEAM_ORDER)}
    return sorted(players, key=lambda p: (order.get(p['team'], 99), p['team'], p['pos'] == 'G', p.get('jersey') or 0))


def landing(paths, nid):
    return read_json(os.path.join(paths.cache, 'nhl', 'landing', f'{nid}.json'), {}) or {}


def players_json(paths):
    pj = read_json(paths.players, {}) or {}
    return {p['nhl_id']: p for p in pj.get('players', [])}


def parse_obs(s):
    """'black/high' → ('black', 'high'); '?' или '' → (None, None)."""
    if s is None:
        return None, None
    s = str(s).strip().lower()
    if s in ('', '?', 'unknown', 'n/a'):
        return None, None
    v, _, c = s.partition('/')
    return v.strip(), (c.strip() or 'med')


def image_size(path):
    """(ширина, высота) JPEG или PNG."""
    with open(path, 'rb') as f:
        d = f.read()
    if d[:8] == b'\x89PNG\r\n\x1a\n':
        return struct.unpack('>II', d[16:24])
    if d[:2] != b'\xff\xd8':
        raise ValueError(f'{path}: не JPEG/PNG')
    p = 2
    while p < len(d):
        while d[p] == 0xFF:
            p += 1
        m = d[p]
        p += 1
        if m in (0xD8, 0x01) or 0xD0 <= m <= 0xD7:
            continue
        ln = struct.unpack('>H', d[p:p + 2])[0]
        if 0xC0 <= m <= 0xCF and m not in (0xC4, 0xC8, 0xCC):
            h, w = struct.unpack('>HH', d[p + 3:p + 7])
            return w, h
        p += ln
    raise ValueError(f'{path}: нет SOF')


jpeg_size = image_size


def now():
    return datetime.now().strftime('%Y-%m-%dT%H:%M')


# --- итог наблюдений по всем источникам ------------------------------------------------------------
def sources(rec):
    """[(источник, obs, год)] — фото НХЛ и использованные кадры Commons."""
    out = []
    if rec.get('obs'):
        out.append(('nhl', rec['obs'], 9999))
    for f in (rec.get('commons') or {}).get('files', []):
        if f.get('obs'):
            out.append((f['title'], f['obs'], f.get('year') or 0))
    return out


def merged(rec):
    """{поле: {'v', 'conf', 'src'[, 'conflict']}} — самое уверенное из источников (при равной уверенности —
    более свежий: фото НХЛ — самое свежее, затем кадры Commons по году). Расхождение (→ low, в базу не
    идёт): другое значение с уверенностью med+ той же уверенности или из более свежего источника —
    т. е. победитель должен быть и не менее уверенным, и не старее всех несогласных."""
    res = {}
    cand = defaultdict(list)
    for src, obs, year in sources(rec or {}):
        for k, o in obs.items():
            cand[k].append((CONF.get(o['conf'], 0), year, src, o['v'], o['conf']))
    for k, lst in cand.items():
        lst.sort(reverse=True)
        c, year, src, v, conf = lst[0]
        rivals = [x for x in lst[1:] if x[0] >= 2 and x[3] != v and (x[0] == c or x[1] > year)]
        if rivals:
            res[k] = {'v': v, 'conf': 'low', 'src': src,
                      'conflict': [{'src': x[2], 'v': x[3], 'conf': x[4]} for x in lst if x[0] >= 2]}
        else:
            res[k] = {'v': v, 'conf': conf, 'src': src}
    return res

def has_photo(rec):
    if not rec:
        return False
    if (rec.get('photo') or {}).get('kind') == 'action':
        return True
    return any(f.get('obs') for f in (rec.get('commons') or {}).get('files', []))


def needs_commons(rec, pos):
    """Фото НХЛ уже смотрели, а уверенной обмотки (и у полевых — языка конька) нет."""
    if not rec or not (rec.get('photo') or {}).get('kind'):
        return False
    m = merged(rec)
    want = ['tape'] + ([] if pos == 'G' else ['tongue'])
    return any((m.get(k) or {}).get('conf') != 'high' for k in want)


# --- fetch (фото НХЛ) -----------------------------------------------------------------------------
def cmd_fetch(paths, a):
    teams = set(a.team.split(',')) if a.team else None
    players = roster(paths, teams)
    http = Http(paths.cache, pause=max(1.0, a.pause))
    st_path = store_path(paths)
    index = {}
    for p in players:
        nid = p['nhl_id']
        url = landing(paths, nid).get('heroImage')
        if not url:
            continue
        body = http.get(url, photo_rel(nid))
        index[nid] = url if body else None
    # заглушки: один и тот же файл у двух и больше игроков (фото арены клуба)
    every = {}
    for p in roster(paths):
        fn = photo_file(paths, p['nhl_id'])
        if os.path.exists(fn):
            every[p['nhl_id']] = hashlib.sha1(open(fn, 'rb').read()).hexdigest()
    counts = Counter(every.values())
    with Lock(st_path):
        st = load_store(paths)
        for h, n in counts.items():
            if n >= 2:
                st['placeholders'][h] = n
        for p in players:
            nid = p['nhl_id']
            if every.get(nid) in st['placeholders']:
                rec = st['players'].get(str(nid))
                if not rec or rec.get('photo', {}).get('kind') != 'placeholder':
                    new = {'name': p['name'], 'team': p['team'], 'pos': p['pos'],
                           'photo': {'kind': 'placeholder', 'sha1': every[nid], 'url': index.get(nid)},
                           'obs': {}, 'reviewed': now(), 'by': 'fetch'}
                    if rec and rec.get('commons'):
                        new['commons'] = rec['commons']
                    st['players'][str(nid)] = new
        write_json(st_path, st)
    ph = sum(1 for p in players if every.get(p['nhl_id']) in st['placeholders'])
    print(f'игроков {len(players)}, с карточкой НХЛ {len(index)}, запросов {http.requests}, '
          f'фото {sum(1 for p in players if p["nhl_id"] in every)}, из них заглушек {ph}')


# --- todo ----------------------------------------------------------------------------------------
def cmd_todo(paths, a):
    teams = set(a.team.split(',')) if a.team else None
    st = load_store(paths)
    cm = read_json_retry(commons_path(paths), {}) or {}
    left = 0
    for p in roster(paths, teams):
        nid = p['nhl_id']
        rec = st['players'].get(str(nid))
        num = landing(paths, nid).get('sweaterNumber', p.get('jersey'))
        if a.commons:
            files = (cm.get(str(nid)) or {}).get('files') or []
            if not rec or not needs_commons(rec, p['pos']) or not files:
                continue
            if (rec.get('commons') or {}).get('reviewed') and not a.all:
                continue
            m = merged(rec)
            have = ', '.join(f'{k} {m[k]["v"]}/{m[k]["conf"]}' for k in ('tape', 'tongue') if k in m) or 'ничего'
            clubs = []
            for sea in landing(paths, nid).get('seasonTotals') or []:
                if sea.get('leagueAbbrev') in ('NHL', 'AHL') and sea.get('season', 0) >= 20200000:
                    t = (sea.get('teamName') or {}).get('default')
                    if t and t not in clubs:
                        clubs.append(t)
            print(f'{nid}\t{p["team"]}\t#{num}\t{p["pos"]}\t{p["name"]}\tкадров Commons {len(files)}\t'
                  f'по фото НХЛ: {have}\tклубы НХЛ/АХЛ с 2020: {", ".join(clubs[-5:]) or "?"}')
            left += 1
            continue
        if rec and not a.all:
            continue
        fn = photo_file(paths, nid)
        state = 'ok' if os.path.exists(fn) else 'нет файла (fetch)'
        print(f'{nid}\t{p["team"]}\t#{num}\t{p["pos"]}\t{p["name"]}\t{state}\t{fn}')
        left += 1
    print(f'— осталось {left}')


# --- Chrome/Edge без окна -------------------------------------------------------------------------
BROWSERS = [r'C:\Program Files\Google\Chrome\Application\chrome.exe',
            r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe',
            r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',
            r'C:\Program Files\Microsoft\Edge\Application\msedge.exe']


def browser():
    env = os.environ.get('NHL13_BROWSER')
    for p in ([env] if env else []) + BROWSERS:
        if p and os.path.exists(p):
            return p
    raise SystemExit('нужен Chrome или Edge (или путь в NHL13_BROWSER)')


def screenshot(page_html, out_png, w, h):
    tmp = tempfile.mkdtemp(prefix='equip_')
    try:
        page = os.path.join(tmp, 'page.html')
        with open(page, 'w', encoding='utf-8') as f:
            f.write(page_html)
        out_abs = os.path.abspath(out_png)
        os.makedirs(os.path.dirname(out_abs), exist_ok=True)
        if os.path.exists(out_abs):
            os.remove(out_abs)
        cmd = [browser(), '--headless=new', '--disable-gpu', '--hide-scrollbars', '--no-first-run',
               '--no-default-browser-check', '--force-device-scale-factor=1', '--allow-file-access-from-files',
               f'--user-data-dir={os.path.join(tmp, "profile")}', f'--window-size={w},{h}',
               '--virtual-time-budget=3000', f'--screenshot={out_abs}', 'file:///' + page.replace('\\', '/')]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120, check=False)
        if not os.path.exists(out_abs):
            raise SystemExit(f'браузер не сохранил {out_abs}')
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def file_url(path):
    return 'file:///' + urllib.parse.quote(os.path.abspath(path).replace('\\', '/'), safe='/:')


def parse_box(s):
    v = [int(round(float(x))) for x in s.replace(' ', '').split(',')]
    if len(v) != 4:
        raise SystemExit(f'кадр «{s}»: нужно X0,Y0,X1,Y1')
    x0, y0, x1, y1 = v
    return min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)


def zoom(photo, boxes, out_png, height=420, max_w=1500):
    W, H = image_size(photo)
    tiles = []
    for x0, y0, x1, y1 in boxes:
        x0, y0, x1, y1 = max(0, x0), max(0, y0), min(W, x1), min(H, y1)
        if x1 - x0 < 4 or y1 - y0 < 4:
            continue
        tiles.append((x0, y0, x1, y1))
    if not tiles:
        raise SystemExit(f'пустые кадры (фото {W}×{H})')
    gap = 6
    # общий масштаб по высоте; если не влезает по ширине — уменьшить
    scales = [height / (y1 - y0) for x0, y0, x1, y1 in tiles]
    widths = [(x1 - x0) * s for (x0, y0, x1, y1), s in zip(tiles, scales)]
    k = min(1.0, (max_w - gap * (len(tiles) - 1)) / sum(widths))
    scales = [s * k for s in scales]
    divs, tw, th = [], 0, 0
    for (x0, y0, x1, y1), s in zip(tiles, scales):
        w, h = round((x1 - x0) * s), round((y1 - y0) * s)
        divs.append(f'<div style="width:{w}px;height:{h}px;background:url(\'{file_url(photo)}\') no-repeat;'
                    f'background-size:{W * s:.2f}px {H * s:.2f}px;background-position:{-x0 * s:.2f}px {-y0 * s:.2f}px">'
                    f'</div>')
        tw += w
        th = max(th, h)
    tw += gap * (len(tiles) - 1)
    page = ('<!doctype html><html><head><meta charset="utf-8"><style>html,body{margin:0;background:#808080}'
            f'.r{{display:flex;gap:{gap}px;align-items:flex-start}}</style></head><body><div class="r">'
            + ''.join(divs) + '</div></body></html>')
    screenshot(page, out_png, tw, th)
    return tw, th


def tmp_png(stem):
    return os.path.join(tempfile.gettempdir(), 'nhl13_equip', f'{stem}_{int(time.time() * 1000) % 1000000}.png')


def cmd_zoom(paths, a):
    photo = a.id if os.path.exists(a.id) else photo_file(paths, a.id)
    if not os.path.exists(photo):
        raise SystemExit(f'нет фото {photo}')
    boxes = [parse_box(b) for b in a.boxes]
    out = a.out or tmp_png(os.path.splitext(os.path.basename(photo))[0])
    w, h = zoom(photo, boxes, out, height=a.height)
    print(out, f'{w}x{h}')


# --- Wikimedia Commons ---------------------------------------------------------------------------
# Политика Wikimedia для ботов (https://w.wiki/4wJS, User-Agent policy): своё имя клиента и контакт, не
# «Mozilla/…» — с UA конвейера (common.UA, браузерного вида) upload.wikimedia.org отвечает 429.
WIKI_UA = (f'megarohas_nhl13-equipment/1.0 (https://github.com/megarohas; personal non-commercial use) '
           f'Python-urllib/{sys.version_info[0]}.{sys.version_info[1]}')


class WikiHttp(Http):
    """Http конвейера (кэш, пауза ≥ 1 с на хост, 404 → .404) с User-Agent по политике Wikimedia;
    на 429 — пауза Retry-After и не больше трёх попыток, дальше — ошибка (не долбить)."""

    def get(self, url, rel, refresh=None):
        import urllib.error
        import urllib.request
        fn = self.path(rel)
        if not (self.refresh if refresh is None else refresh):
            if os.path.exists(fn):
                with open(fn, 'rb') as f:
                    return f.read()
            if os.path.exists(fn + '.404'):
                return None
        if self.offline:
            raise SystemExit(f'нет в кэше: {rel} ({url})')
        host = urllib.parse.urlsplit(url).hostname
        for attempt in range(3):
            wait = self.pause - (time.time() - self.last.get(host, 0))
            if wait > 0:
                time.sleep(wait)
            try:
                req = urllib.request.Request(url, headers={'User-Agent': WIKI_UA})
                with urllib.request.urlopen(req, timeout=60) as r:
                    body = r.read()
                self.last[host] = time.time()
                break
            except urllib.error.HTTPError as err:
                self.last[host] = time.time()
                self.requests += 1
                if err.code == 404:
                    os.makedirs(os.path.dirname(fn), exist_ok=True)
                    open(fn + '.404', 'w').close()
                    return None
                if err.code in (429, 503) and attempt < 2:
                    delay = min(60, int(err.headers.get('Retry-After') or 10))
                    self.log(f'  HTTP {err.code} {host} — пауза {delay} с')
                    time.sleep(delay)
                    continue
                raise
        self.requests += 1
        os.makedirs(os.path.dirname(fn), exist_ok=True)
        tmp = fn + '.part'
        with open(tmp, 'wb') as f:
            f.write(body)
        os.replace(tmp, fn)
        return body


def fold(s):
    return ''.join(c for c in unicodedata.normalize('NFKD', s) if not unicodedata.combining(c))


def wiki_url(title, raw=False):
    t = title.replace(' ', '_')
    return f'{COMMONS}/wiki/{urllib.parse.quote(t, safe=":()_,!-.~*")}' + ('?action=raw' if raw else '')


def safe_name(title):
    base = re.sub(r'[^A-Za-z0-9._-]+', '_', fold(title))[:80]
    return f'{base}_{hashlib.md5(title.encode("utf-8")).hexdigest()[:6]}'


def file_md5(title):
    name = title.split(':', 1)[1].replace(' ', '_')
    return name, hashlib.md5(name.encode('utf-8')).hexdigest()


def thumb_urls(title, width=THUMB_W):
    name, h = file_md5(title)
    q = urllib.parse.quote(name, safe='()_,!-.~*')
    ext = name.rsplit('.', 1)[-1].lower()
    tname = q if ext in ('jpg', 'jpeg', 'png') else q + '.jpg'
    return (f'{UPLOAD}/thumb/{h[0]}/{h[:2]}/{q}/{width}px-{tname}', f'{UPLOAD}/{h[0]}/{h[:2]}/{q}')


def _section(page, start_id):
    i = page.find(f'id="{start_id}"')
    if i < 0:
        return ''
    j = page.find('<div id="', i + 10)
    k = page.find('class="printfooter"', i)
    ends = [x for x in (j, k) if x > 0]
    return page[i:min(ends)] if ends else page[i:]


GALLERY_DIMS = {}                       # File:… → (ширина, высота) миниатюры из галереи категории


def parse_category(page):
    """Файлы, подкатегории, родительские категории и перенаправление со страницы категории."""
    unq = lambda s: urllib.parse.unquote(s).replace('_', ' ')
    media = _section(page, 'mw-category-media')
    files = []
    for m in re.finditer(r'href="/wiki/(File:[^"#?]+)"', media):
        t = unq(m.group(1))
        if t not in files:
            files.append(t)
    # размеры миниатюр галереи — по ним видно, портретная вырезка или широкий игровой кадр
    for m in re.finditer(r'href="/wiki/(File:[^"#?]+)"[^>]*>\s*<img[^>]*?width="(\d+)"\s+height="(\d+)"', media):
        GALLERY_DIMS[unq(m.group(1))] = (int(m.group(2)), int(m.group(3)))
    subs = []
    for m in re.finditer(r'href="/wiki/(Category:[^"#?]+)"', _section(page, 'mw-subcategories')):
        t = unq(m.group(1))
        if t not in subs:
            subs.append(t)
    i = page.find('id="catlinks"')
    parents = [unq(x) for x in re.findall(r'href="/wiki/(Category:[^"#?]+)"', page[i:i + 20000])] if i >= 0 else []
    redirect = None
    m = re.search(r'(?:category is located at|Category redirect)[^<]{0,80}(?:<[^>]+>){0,4}\s*<a[^>]+href="/wiki/(Category:[^"#?]+)"',
                  page, re.I)
    if m:
        redirect = unq(m.group(1))
    return files, subs, parents, redirect


HOCKEY_WORDS = ('hockey', 'nhl', 'khl', 'ahl', 'shl', 'iihf', 'eishockey', 'ishockey', 'jääkiekko', 'hokej',
                'hokkej', 'хоккей', 'liiga', 'ncaa', 'ohl', 'whl', 'qmjhl', 'ushl', 'stanley cup', 'world juniors')


def is_hockey(title, parents, files=()):
    """Категория хоккеиста: хоккейное слово или клуб НХЛ в её названии или категориях; если их нет (у
    редких категорий нет и родителей) — хотя бы у трети файлов в именах (у тёзки-конькобежца «Samuel
    Girard» — «Moscow 2015 Relay…», у рестлера, на которого перенаправлена «Ryan O'Reilly», — 2 «Stanley
    Cup parade» из 26 — не берутся)."""
    names = [n.lower() for n in TEAM_NAMES.values()]

    def hit(t):
        lt = fold(t).lower()
        return any(w in lt for w in HOCKEY_WORDS) or any(n in lt for n in names)

    if hit(title) or any(hit(x) for x in parents):
        return True
    files = list(files)
    return bool(files) and sum(1 for f in files if hit(f)) * 3 >= len(files)


IMG_EXT = ('.jpg', '.jpeg', '.png')
SKIP_WORDS = ('signature', 'autograph', 'logo', 'card', 'stamp', 'coin', 'map', 'diagram')


def file_year(title):
    ys = [int(y) for y in re.findall(r'(?<!\d)(19[89]\d|20[0-3]\d)(?!\d)', title)]
    return max(ys) if ys else 0


def commons_candidates(paths, http, p, pj, max_files, log):
    """Категория игрока на Commons и до max_files свежих снимков: запись для commons.json."""
    name = p['name']
    birth = (pj.get(p['nhl_id']) or {}).get('birth') or [None]
    names = [name] + ([fold(name)] if fold(name) != name else [])
    tried, found = [], None
    titles = []
    # сначала просто имя (обычно так и называется); тёзки и неоднозначные — с уточнением
    for n in names:
        titles.append(f'Category:{n}')
    for n in names:
        if birth[0]:
            titles.append(f'Category:{n} (ice hockey, born {birth[0]})')
        titles.append(f'Category:{n} (ice hockey)')
    plain_missing = 0
    for t in titles:
        if found:
            break
        if plain_missing == len(names) and '(ice hockey' in t:
            break                                   # нет даже категории «Имя» — уточнённых обычно тоже нет
        for hop in range(2):                       # и одно перенаправление категории
            tried.append(t)
            body = http.text(wiki_url(t), '/'.join(COMMONS_DIR + ('cat', safe_name(t) + '.html')))
            if body is None:
                if '(ice hockey' not in t:
                    plain_missing += 1
                break
            files, subs, parents, redirect = parse_category(body)
            if redirect and redirect != t and not files:
                t = redirect
                continue
            if birth[0] and '(ice hockey' not in t:   # на странице тёзки — ссылка на «(ice hockey, born ГГГГ)»
                m = re.search(r'href="/wiki/(Category:[^"#?]*%28ice_hockey,_born_' + str(birth[0]) + r'%29)"', body)
                if m:
                    t = urllib.parse.unquote(m.group(1)).replace('_', ' ')
                    continue
            if re.search(r'disambig|Неоднозначн|may refer to', body, re.I) and not files:
                log(f'  {name}: {t} — неоднозначная категория')
                break
            if not is_hockey(t, parents, files):
                log(f'  {name}: {t} — не хоккеист ({", ".join(parents[:4])})')
                break
            # тёзка-хоккеист другого года рождения: в уточнённой категории «born ГГГГ» с другим годом
            m = re.search(r'\(ice hockey, born (\d{4})\)', t)
            if m and birth[0] and int(m.group(1)) != birth[0]:
                break
            found = (t, files, subs)
            break
    rec = {'name': name, 'team': p['team'], 'tried': tried, 'checked': now(), 'category': None, 'files': []}
    if not found:
        return rec
    t, files, subs = found
    rec['category'] = t
    last = fold(name.split()[-1]).lower()

    def pick(lst):
        out = []
        for f in lst:
            lf = f.lower()
            if not lf.endswith(IMG_EXT) or any(w in lf for w in SKIP_WORDS) or 'cropped' in lf:
                continue
            w, h = GALLERY_DIMS.get(f, (0, 0))
            wide = bool(h) and w / h >= 1.15          # широкий кадр — чаще игровой, с клюшкой и коньками
            y = file_year(f)
            out.append(((wide, y >= 2021, y, last in fold(lf)), y, f))
        return out

    cands = pick(files)
    if sum(1 for k, y, _ in cands if k[0] and y >= 2021) < max_files:
        for s in [s for s in subs if last in fold(s).lower()][:3]:
            body = http.text(wiki_url(s), '/'.join(COMMONS_DIR + ('cat', safe_name(s) + '.html')))
            if body:
                cands += pick(parse_category(body)[0])
    seen, chosen = set(), []
    for key, y, f in sorted(cands, key=lambda x: (x[0], x[2]), reverse=True):
        if f in seen:
            continue
        seen.add(f)
        chosen.append((y, f))
        if len(chosen) >= max_files:
            break
    rec['chosen'] = chosen
    return rec


def commons_download(paths, http, p, rec, log):
    """Уменьшенные копии выбранных снимков (upload.wikimedia.org) → rec['files']."""
    for y, f in rec.pop('chosen', []):
        thumb, orig = thumb_urls(f)
        _, h = file_md5(f)
        ext = '.png' if f.lower().endswith('.png') else '.jpg'
        rel = '/'.join(COMMONS_DIR + (str(p['nhl_id']), h[:12] + ext))
        body, url = None, thumb
        try:
            body = http.get(thumb, rel)
        except Exception as err:                    # уменьшенной копии нет (снимок меньше 1280) — исходник
            log(f'  {f}: уменьшенная копия не получена ({err}) — исходник')
            url = orig
            try:
                body = http.get(orig, rel)
            except Exception as err2:
                log(f'  {f}: не скачан ({err2})')
        if body:
            try:
                w, hh = image_size(cache_file(paths, rel))
            except ValueError:
                w = hh = None
            rec['files'].append({'title': f, 'file': rel, 'url': url, 'page': wiki_url(f), 'year': y or None,
                                 'w': w, 'h': hh})
    return rec


def cmd_commons(paths, a):
    """Поиск категорий (commons.wikimedia.org) и загрузка снимков (upload.wikimedia.org) идут параллельно:
    у каждого хоста своя пауза ≥ --pause, запросы к одному хосту — строго по одному."""
    import queue
    import threading
    teams = set(a.team.split(',')) if a.team else None
    st = load_store(paths)
    pj = players_json(paths)
    pause = max(1.0, a.pause)
    http_pages, http_files = WikiHttp(paths.cache, pause=pause), WikiHttp(paths.cache, pause=pause)
    cpath = commons_path(paths)
    done = Counter()
    q = queue.Queue(maxsize=8)
    lock = threading.Lock()

    def out(msg):
        with lock:
            print(msg, flush=True)

    def downloader():
        while True:
            item = q.get()
            if item is None:
                return
            p, r = item
            try:
                commons_download(paths, http_files, p, r, out)
            except Exception as err:               # сеть — запись без снимков, повторить: --retry
                out(f'  {p["name"]}: загрузка прервана ({err})')
                r.pop('chosen', None)
            try:
                with Lock(cpath):
                    cm = read_json_retry(cpath, {}) or {}
                    cm[str(p['nhl_id'])] = r
                    write_json(cpath, cm)
            except Exception as err:               # не ронять поток: игрок останется без записи (--retry)
                out(f'  {p["name"]}: commons.json не записан ({err})')
                continue
            with lock:
                done['категория' if r['category'] else 'нет категории'] += 1
                done['кадров'] += len(r['files'])
            out(f'{p["nhl_id"]}\t{p["team"]}\t{p["name"]}\t{r["category"] or "—"}\tкадров {len(r["files"])}')

    th = threading.Thread(target=downloader, daemon=True)
    th.start()
    cm0 = read_json_retry(cpath, {}) or {}
    try:
        for p in roster(paths, teams):
            rec = st['players'].get(str(p['nhl_id']))
            if not a.all and not needs_commons(rec, p['pos']):
                done['не нужно'] += 1
                continue
            old = cm0.get(str(p['nhl_id']))
            if old and not a.refresh and (old.get('files') or not a.retry):
                done['уже есть'] += 1
                continue
            q.put((p, commons_candidates(paths, http_pages, p, pj, a.max, out)))
    finally:
        q.put(None)
        th.join()
    print(f'— {dict(done)}; запросов: страниц {http_pages.requests}, снимков {http_files.requests}')


def cmd_csheet(paths, a):
    cm = read_json_retry(commons_path(paths), {}) or {}
    r = cm.get(str(a.id))
    if not r or not r.get('files'):
        raise SystemExit(f'{a.id}: кадров Commons нет (python -m roster.equipment commons --team …)')
    files = [f for f in r['files'] if os.path.exists(cache_file(paths, f['file']))]
    cell_w, cell_h, gap = 640, 400, 8
    cols = 2
    rows = (len(files) + cols - 1) // cols
    cells = []
    for i, f in enumerate(files, 1):
        fn = cache_file(paths, f['file'])
        cells.append(f'<div class="c"><img src="{file_url(fn)}"><div class="t">#{i} · {f.get("year") or "год ?"} · '
                     f'{f.get("w")}×{f.get("h")} · {html.escape(f["title"][5:][:70])}</div></div>')
        print(f'#{i}\t{fn}\t{f["title"]}\t{f.get("w")}x{f.get("h")}')
    W = cols * cell_w + (cols + 1) * gap
    H = rows * (cell_h + 22) + (rows + 1) * gap
    page = (f'<!doctype html><html><head><meta charset="utf-8"><style>html,body{{margin:0;background:#333;'
            f'font:13px sans-serif;color:#fff}}.g{{display:grid;grid-template-columns:repeat({cols},{cell_w}px);'
            f'gap:{gap}px;padding:{gap}px}}.c{{width:{cell_w}px}}.c img{{width:{cell_w}px;height:{cell_h}px;'
            f'object-fit:contain;background:#555;display:block}}.t{{height:20px;overflow:hidden;white-space:nowrap}}'
            f'</style></head><body><div class="g">{"".join(cells)}</div></body></html>')
    out = a.out or tmp_png(f'commons_{a.id}')
    screenshot(page, out, W, H)
    print(out, f'{W}x{H}')


def wikitext_license(text):
    """Автор, дата и лицензия из вики-разметки страницы файла."""
    def clean(s):
        s = re.sub(r'\[\[(?:[^|\]]*\|)?([^\]]*)\]\]', r'\1', s)
        s = re.sub(r'\[https?://\S+\s+([^\]]+)\]', r'\1', s)
        s = re.sub(r'\[https?://[^\]\s]+\]', '', s)
        s = re.sub(r'\{\{\s*(?:creator|user)\s*:\s*([^}|]+)[^}]*\}\}', r'\1', s, flags=re.I)
        s = re.sub(r'\{\{[^{}]*\}\}', '', s)
        s = re.sub(r"'''?|<[^>]+>", '', s)
        return ' '.join(s.split()).strip(' ,;')

    author = date = None
    m = re.search(r'^\s*\|\s*author\s*=\s*(.+)$', text, re.I | re.M)
    if m:
        author = clean(m.group(1))[:200] or None
    m = re.search(r'^\s*\|\s*date\s*=\s*(.+)$', text, re.I | re.M)
    if m:
        date = clean(m.group(1))[:40] or None
    lic = []
    for m in re.finditer(r'\{\{\s*([^{}|]+?)\s*((?:\|[^{}]*)?)\}\}', text):
        name, args = m.group(1).strip(), m.group(2)
        names = [name] + ([x.strip() for x in args.split('|') if x.strip()] if name.lower() == 'self' else [])
        for n in names:
            ln = n.lower()
            if re.match(r'(cc-|cc0|pd-|gfdl|fal\b|attribution|copyrighted free use|public domain)', ln) and n not in lic:
                lic.append(n)
    url = None
    short = None
    for n in lic:
        m = re.match(r'cc-(by(?:-sa)?)-(\d\.\d)', n.lower())
        if m:
            short = f'CC {m.group(1).upper()} {m.group(2)}'
            url = f'https://creativecommons.org/licenses/{m.group(1)}/{m.group(2)}/'
            break
        if n.lower() in ('cc-zero', 'cc0'):
            short, url = 'CC0 1.0', 'https://creativecommons.org/publicdomain/zero/1.0/'
            break
    if not short and lic:
        short = lic[0]
    if not short:                      # своя лицензия автора ({{User:…/licence}}) — имя шаблона из раздела лицензии
        i = text.find('license-header')
        m = re.search(r'\{\{\s*([^{}|]+?)\s*(?:\|[^{}]*)?\}\}', text[i:]) if i >= 0 else None
        if m:
            short = m.group(1).strip()
            lic = [short]
            if short.lower().startswith('user:'):
                url = f'{COMMONS}/wiki/{urllib.parse.quote(short.replace(" ", "_"), safe=":/()_,!-.~*")}'
    return {'author': author, 'date': date, 'license': short, 'license_url': url, 'license_templates': lic[:6]}


def cmd_meta(paths, a):
    """Автор и лицензия использованных кадров Commons (/wiki/File:…?action=raw) → equipment.json."""
    st = load_store(paths)
    todo = [(nid, f['title']) for nid, rec in st['players'].items()
            for f in (rec.get('commons') or {}).get('files', []) if f.get('obs') and (a.refresh or not f.get('license'))]
    http = WikiHttp(paths.cache, pause=max(1.0, a.pause))
    metas = {t: file_meta(paths, http, t) for _, t in todo}
    with Lock(store_path(paths)):
        st = load_store(paths)
        n = 0
        for nid, rec in st['players'].items():
            for f in (rec.get('commons') or {}).get('files', []):
                if f['title'] in metas:
                    f.update({k: v for k, v in metas[f['title']].items() if v})
                    n += 1
        write_json(store_path(paths), st)
    no_lic = sorted({t for t, m in metas.items() if not m.get('license')})
    print(f'кадров {n}, запросов {http.requests}' + (f'; без лицензии: {no_lic}' if no_lic else ''))


# --- record --------------------------------------------------------------------------------------
def check_entry(e, cm):
    errs = []
    if 'id' not in e:
        return ['нет id']
    for k, voc in VOCAB.items():
        v, c = parse_obs(e.get(k))
        if v is not None and v not in voc:
            errs.append(f'{k}: «{v}» не из {sorted(voc)}')
        if c is not None and c not in CONF:
            errs.append(f'{k}: уверенность «{c}» не из high/med/low')
    for k in BOX_KEYS:
        b = e.get(k)
        if b is not None and (not isinstance(b, list) or len(b) != 4):
            errs.append(f'{k}: нужен [x0, y0, x1, y1]')
    extra = set(e) - set(VOCAB) - set(BOX_KEYS) - {'id', 'note', 'photo', 'name', 'src'}
    if extra:
        errs.append(f'лишние ключи {sorted(extra)}')
    src = e.get('src')
    if src and src != 'commons':
        t = src if src.startswith('File:') else 'File:' + src
        files = [f['title'] for f in (cm.get(str(e['id'])) or {}).get('files', [])]
        if t not in files:
            errs.append(f'src «{src}»: такого кадра нет среди кадров Commons игрока ({len(files)})')
    return errs


def file_meta(paths, http, title):
    rel = '/'.join(COMMONS_DIR + ('raw', safe_name(title) + '.txt'))
    text = http.text(wiki_url(title, raw=True), rel)
    return wikitext_license(text or '')


def cmd_record(paths, a):
    src_text = sys.stdin.read() if a.file == '-' else open(a.file, encoding='utf-8').read()
    entries = json.loads(src_text)
    if isinstance(entries, dict):
        entries = [entries]
    cm = read_json_retry(commons_path(paths), {}) or {}
    bad = {str(e.get('id')): check_entry(e, cm) for e in entries}
    bad = {k: v for k, v in bad.items() if v}
    if bad:
        for k, v in bad.items():
            print(f'{k}: {"; ".join(v)}')
        raise SystemExit('ничего не записано')
    by_id = {p['nhl_id']: p for p in roster(paths)}
    st_path = store_path(paths)
    with Lock(st_path):
        st = load_store(paths)
        for e in entries:
            nid = int(e['id'])
            p = by_id.get(nid, {})
            old = st['players'].get(str(nid)) or {}
            obs = {}
            if e.get('photo') != 'none':
                for k in VOCAB:
                    v, c = parse_obs(e.get(k))
                    if v is not None:
                        obs[k] = {'v': v, 'conf': c}
            boxes = {k: [int(round(x)) for x in e[k]] for k in BOX_KEYS if e.get(k)}
            s = e.get('src')
            if s:                                   # Commons
                rec = old or {'name': p.get('name', e.get('name')), 'team': p.get('team'), 'pos': p.get('pos')}
                c = rec.setdefault('commons', {})
                c['reviewed'] = now()
                c['by'] = a.by
                c.setdefault('files', [])
                if s != 'commons' and e.get('photo') != 'none':
                    t = s if s.startswith('File:') else 'File:' + s
                    info = next(f for f in cm[str(nid)]['files'] if f['title'] == t)
                    prev = next((f for f in c['files'] if f['title'] == t), {})
                    fe = {'title': t, 'file': info['file'], 'url': info['url'], 'page': info['page'],
                          'year': info.get('year'), 'obs': obs, 'reviewed': now(), 'by': a.by}
                    for k in ('author', 'date', 'license', 'license_url', 'license_templates'):
                        if prev.get(k):
                            fe[k] = prev[k]
                    if boxes:
                        fe['boxes'] = boxes
                    if e.get('note'):
                        fe['note'] = e['note']
                    # снимок без наблюдений (всё «не видно») — убрать: отметка «смотрели» и так стоит
                    c['files'] = [f for f in c['files'] if f['title'] != t] + ([fe] if obs else [])
                elif e.get('note'):
                    c['note'] = e['note']
                st['players'][str(nid)] = rec
                continue
            fn = photo_file(paths, nid)
            sha = hashlib.sha1(open(fn, 'rb').read()).hexdigest() if os.path.exists(fn) else None
            rec = {'name': p.get('name', e.get('name')), 'team': p.get('team'), 'pos': p.get('pos'),
                   'photo': {'kind': 'none' if e.get('photo') == 'none' else ('action' if sha else 'missing'),
                             'file': photo_rel(nid), 'sha1': sha,
                             'url': landing(paths, nid).get('heroImage')},
                   'obs': obs, 'reviewed': now(), 'by': a.by}
            if boxes:
                rec['boxes'] = boxes
            if e.get('note'):
                rec['note'] = e['note']
            if old.get('commons'):
                rec['commons'] = old['commons']
            hist = old.get('history') or []
            if old.get('obs') and old.get('obs') != obs:
                hist = hist + [{k: old[k] for k in ('obs', 'reviewed', 'by') if k in old}]
            if hist:
                rec['history'] = hist
            st['players'][str(nid)] = rec
        st['version'] = 2
        st['updated'] = now()
        write_json(st_path, st)
    print(f'записано {len(entries)} → {st_path}')


# --- перевод наблюдений в коды -------------------------------------------------------------------
def good(obs, key, min_conf):
    o = obs.get(key)
    if o and CONF.get(o.get('conf'), 0) >= CONF[min_conf]:
        return o['v']
    return None


def src_ru(obs, key):
    s = (obs.get(key) or {}).get('src')
    return 'фото НХЛ' if s in (None, 'nhl') else 'Commons'


def decide(rec, cur, is_goalie, min_conf='high', fields=FIELDS):
    """Новые значения полей базы по наблюдениям: {поле: (новое, причина)}; cur — текущие значения."""
    out = {}
    obs = merged(rec or {})
    if 'tape' in fields:
        v = good(obs, 'tape', min_conf)
        if v is not None:
            out['sticktapecolor'] = (TAPE[v], f'{src_ru(obs, "tape")}: {TAPE_RU[v]}')
    if 'jersey' in fields:
        v = good(obs, 'jersey', min_conf)
        if v is not None:
            out['jerseytuck'] = (JERSEY[v], f'{src_ru(obs, "jersey")}: {VAL_RU[v]}')
    if is_goalie:
        return out
    if 'socks' in fields:
        t, h = good(obs, 'tongue', min_conf), good(obs, 'heel', min_conf)
        c = cur.get('skatesocktuck')
        why = src_ru(obs, 'tongue')
        # NHL 13: 0 полностью, 1 не заправлена (поверх), 2 спереди (язык поверх гетры), 3 сзади (гетра на языке)
        f = {'out': True, 'hidden': False}.get(t)          # спереди заправлена под язык?
        b = {'tucked': True, 'over': False}.get(h)         # сзади в ботинке?
        c = cur.get('skatesocktuck')
        n = None
        if f is not None and b is not None:
            n = SOCK_CODE[(f, b)]
        elif f is not None:            # сзади не видно: текущее значение, если спереди с ним согласно
            n = c if SOCK_FRONT.get(c) == f else SOCK_CODE[(f, True)]      # иначе — сзади «в ботинке»
        elif b is not None:            # спереди не видно — так же
            n = c if SOCK_BACK.get(c) == b else SOCK_CODE[(False, b)]
        if n is not None:
            seen = ', '.join(x for x in ((f is not None and ('язык наружу' if f else 'язык не виден')),
                                         (b is not None and f'сзади {VAL_RU[h]}')) if x)
            src = src_ru(obs, 'tongue') if t else src_ru(obs, 'heel')
            out['skatesocktuck'] = (n, f'{src}: {seen}')
    if 'visor' in fields:
        v = good(obs, 'visor', min_conf)
        why = src_ru(obs, 'visor')
        if v == 'none':
            out['visortype'] = (2, f'{why}: без визора')
        elif v in ('clear', 'tinted'):
            vt = cur.get('visortype')
            out['visortype'] = (vt if vt in (0, 1) else 0, f'{why}: визор {VAL_RU[v]}')
            vc = cur.get('visorcolor')
            if v == 'clear':
                out['visorcolor'] = (0, f'{why}: визор прозрачный')
            else:
                out['visorcolor'] = (vc if vc not in (0, None) else 1, f'{why}: визор тёмный')
    return out


def season_ru(d):
    return f'{str(d)[:4]}/{str(d)[6:]}' if d else 'нет'


# Без визора в НХЛ 2026/27 играют только трое (сведения пользователя): у остальных полевых визор есть.
NO_VISOR = {8473994: 'Jamie Benn', 8475158: "Ryan O'Reilly", 8474567: 'Zach Bogosian'}


def rule_values(p, cur, is_goalie, debut, visor_rule, jersey_rule, new):
    """Правила поверх фото: свитер не заправлен у всех (НХЛ 2026/27); визор у всех полевых, кроме
    NO_VISOR (у них «нет визора») — фото тут не решает (кто на фото без визора — в отчёт apply)."""
    out = {}
    if jersey_rule and 'jerseytuck' in cur:
        if cur['jerseytuck'] != 0 or 'jerseytuck' in new:
            out['jerseytuck'] = (0, 'правило НХЛ 2026/27: свитер не заправлять')
    if visor_rule and not is_goalie and 'visortype' in cur:
        if p['nhl_id'] in NO_VISOR:
            out['visortype'] = (2, 'правило: играет без визора (один из трёх в НХЛ)')
        else:
            out['visortype'] = (cur['visortype'] if cur['visortype'] in (0, 1) else 0,
                                'правило: визор у всех, кроме Benn, O\'Reilly, Bogosian')
    return out


def visor_doubts(st, rows):
    """Кто уверенно без визора на фото, но не из NO_VISOR (правило ставит ему визор) — для отчёта."""
    out = []
    for p, table, r, cur, new in rows:
        o = merged(st['players'].get(str(p['nhl_id'])) or {}).get('visor')
        if p['pos'] != 'G' and o and o['v'] == 'none' and o['conf'] in ('high', 'med') and p['nhl_id'] not in NO_VISOR:
            out.append({'nhl_id': p['nhl_id'], 'name': p['name'], 'team': p['team'], 'conf': o['conf'],
                        'src': o.get('src')})
    return out


# --- база ----------------------------------------------------------------------------------------
def open_db(path, meta=None):
    from tdb import Tdb                       # tools/ в sys.path через common
    from tdb_read import load_meta
    from .common import ref_meta
    meta_path = meta
    if not meta_path:
        side = os.path.join(os.path.dirname(os.path.abspath(path)), 'nhlng-meta.xml')
        meta_path = side if os.path.exists(side) else ref_meta()
    with open(path, 'rb') as f:
        return Tdb(f.read(), load_meta(meta_path))


def row_index(db, table, field='game_id'):
    """game_id (или другое поле-ключ) → строка, только живые записи (tdb.Tdb.live_rows). В сейве игры (ROSTER,
    франшиза) за current — запас из байтов 0xDB с одним game_id на все строки, у франшизы ещё и удалённые
    записи; в базах игр и наших все строки живые — индекс тот же, что по range(rows)."""
    return {db.get(table, field, r): r for r in db.live_rows(table)}


SK_FIELDS = ('sticktapecolor', 'skatesocktuck', 'jerseytuck', 'visortype', 'visorcolor')
GK_FIELDS = ('sticktapecolor', 'jerseytuck')


def current(db, idx_sk, idx_gk, p):
    g = p['game_id']
    if p['pos'] == 'G':
        r = idx_gk.get(g)
        return (GOALIE_T, r, {f: db.get(GOALIE_T, f, r) for f in GK_FIELDS}) if r is not None else (GOALIE_T, None, {})
    r = idx_sk.get(g)
    return (SKATER_T, r, {f: db.get(SKATER_T, f, r) for f in SK_FIELDS}) if r is not None else (SKATER_T, None, {})


def plan(paths, db, st, min_conf, fields, visor_rule, jersey_rule, teams=None):
    """[(игрок, таблица, строка, текущие, {поле: (новое, причина)})] для всех игроков write.json."""
    idx_sk, idx_gk = row_index(db, SKATER_T), row_index(db, GOALIE_T)
    debut = {k: (v.get('nhl_gp') or {}).get('debut') for k, v in players_json(paths).items()} if visor_rule else {}
    rows = []
    for p in roster(paths, teams):
        table, r, cur = current(db, idx_sk, idx_gk, p)
        rec = st['players'].get(str(p['nhl_id']))
        new = decide(rec, cur, p['pos'] == 'G', min_conf, fields) if r is not None else {}
        if r is not None:
            new.update(rule_values(p, cur, p['pos'] == 'G', debut, visor_rule and 'visor' in fields,
                                   jersey_rule and 'jersey' in fields, new))
        rows.append((p, table, r, cur, new))
    return rows


def cmd_apply(paths, a):
    st = load_store(paths)
    fields = tuple(f for f in a.fields.split(',') if f)
    bad = set(fields) - set(FIELDS)
    if bad:
        raise SystemExit(f'--fields: нет полей {sorted(bad)} (есть {",".join(FIELDS)})')
    db = open_db(a.db_in, a.meta)
    src = bytes(db.d)
    rows = plan(paths, db, st, a.min_conf, fields, a.visor_rule, a.jersey_rule)
    changed, same, missing = Counter(), Counter(), []
    by_why = Counter()
    log = []
    for p, table, r, cur, new in rows:
        if r is None:
            missing.append(p)
            continue
        for f, (v, why) in new.items():
            if cur.get(f) == v:
                same[f] += 1
                continue
            db.set(table, f, r, v)
            changed[f] += 1
            by_why[(f, why.split(':')[0])] += 1
            log.append({'nhl_id': p['nhl_id'], 'name': p['name'], 'team': p['team'], 'game_id': p['game_id'],
                        'table': table, 'field': f, 'old': cur.get(f), 'new': v, 'why': why})
    db.fix()
    problems = verify_out(src, db, log)
    problems += same_tables(src, db)
    exempt = None
    if not problems and a.visor_rule and 'visor' in fields and VISOR_EXEMPT_T in db.by_name:
        exempt = visor_exempt(db, rows)       # NHL Legacy: таблица «можно без визора» — по тому же правилу
    doubts = visor_doubts(st, rows) if a.visor_rule else []
    print(f'игроков {len(rows)}; без строки экипировки {len(missing)}')
    if exempt is not None:
        print(f"  {VISOR_EXEMPT_T}: убрано {exempt['removed']}, добавлено {exempt['added']}, строк {exempt['rows']}")
    if doubts:
        print('  на фото без визора, но не из троих (визор оставлен по правилу): '
              + ', '.join(f'{x["name"]} ({x["team"]}, {x["conf"]})' for x in doubts))
    for f in sorted(set(changed) | set(same), key=lambda x: (SK_FIELDS + GK_FIELDS).index(x)):
        src_counts = ', '.join(f'{w} {n}' for (ff, w), n in sorted(by_why.items()) if ff == f)
        print(f'  {f}: изменено {changed[f]}' + (f' ({src_counts})' if src_counts else '') + f', уже так {same[f]}')
    if problems:
        for x in problems[:20]:
            print('  ПРОБЛЕМА:', x)
        raise SystemExit(f'проверка не прошла ({len(problems)}), {a.db_out} не записан')
    if a.dry_run:
        print('--dry-run: база не записана')
    else:
        tmp = a.db_out + '.part'
        os.makedirs(os.path.dirname(os.path.abspath(a.db_out)), exist_ok=True)
        with open(tmp, 'wb') as f:
            f.write(db.d)
        os.replace(tmp, a.db_out)
        again = open_db(a.db_out, a.meta)
        if again.verify():
            raise SystemExit(f'{a.db_out}: CRC не сходятся после записи')
        print(f'записано → {a.db_out} (CRC в порядке)')
    if a.report:
        write_json(a.report, {'db_in': a.db_in, 'db_out': None if a.dry_run else a.db_out, 'work': paths.work,
                              'min_conf': a.min_conf, 'fields': fields, 'visor_rule': a.visor_rule,
                              'jersey_rule': a.jersey_rule, 'changed': dict(changed), 'same': dict(same),
                              'no_visor': NO_VISOR if a.visor_rule else None, 'visor_doubts': doubts,
                              **({'visor_exempt': exempt} if exempt is not None else {}),
                              'changes': log})
        print(f'отчёт → {a.report}')


def visor_exempt(db, rows):
    """NHL Legacy: stockplayervisorexempttable — game_id тех, кому можно без визора (у Legacy 1779 строк:
    пришедшие в НХЛ до правила 2013 года). Строки игроков конвейера — новые люди на строках доноров и
    игроки 2015 года через 11 лет: исключение остаётся только у тех, кто по правилу без визора (NO_VISOR),
    у остальных полевых конвейера снимается; прочие строки таблицы не трогаются. Таблица — по game_id."""
    t = VISOR_EXEMPT_T
    cur = db.column(t, 'game_id')
    skaters = {p['game_id'] for p, table, r, c, n in rows if table == SKATER_T and r is not None}
    keep = {p['game_id'] for p, table, r, c, n in rows if table == SKATER_T and r is not None and p['nhl_id'] in NO_VISOR}
    new = sorted((set(cur) - skaters) | keep)
    out = {'removed': len((set(cur) & skaters) - keep), 'added': len(keep - set(cur)), 'rows': len(new)}
    if new != cur:
        db.resize(t, len(new))
        for i, g in enumerate(new):
            db.set(t, 'game_id', i, g)
        db.fix()
    return out


def same_tables(src, db):
    """Все таблицы, кроме двух таблиц экипировки, байт в байт как во входной базе (записи); отдельно —
    био игроков: hasportrait, artid, headid, skincolor (фото и тон кожи предыдущих этапов)."""
    from tdb import Tdb
    before = Tdb(src, db.meta)
    problems, same = [], 0
    for t in db.tables:
        if t['name'] in (SKATER_T, GOALIE_T):
            continue
        b = before.by_name[t['name']]
        n = t['reclen'] * t['rows']
        if before.d[b['records']:b['records'] + n] != db.d[t['records']:t['records'] + n]:
            problems.append(f'таблица {t["name"]} изменилась')
        else:
            same += 1
    bio = 'exhibitionplayerbiotable'
    cols = [f for f in ('hasportrait', 'artid', 'headid', 'skincolor') if f in db.by_name[bio]['fields']]
    diff = sum(1 for f in cols for r in range(db.by_name[bio]['rows']) if db.get(bio, f, r) != before.get(bio, f, r))
    print(f'  прочие таблицы без изменений: {same} из {len(db.tables) - 2}; {bio}: '
          f'{", ".join(cols)} — расхождений {diff} ({db.by_name[bio]["rows"]} строк)')
    if diff:
        problems.append(f'{bio}: {diff} расхождений в {cols}')
    return problems


def verify_out(src, db, log):
    """Изменились только поля из log (и CRC); значения на месте; CRC сходятся."""
    problems = []
    if db.verify():
        problems.append('CRC не сходятся')
    out = bytes(db.d)
    if len(out) != len(src):
        return problems + [f'размер {len(src)} → {len(out)}']
    allowed = set()
    for t in db.tables:
        for o in (t['block'], t['block'] + 0x24):
            allowed.update(range(o, o + 4))
    allowed.update(range(len(out) - 4, len(out)))
    allowed.update(range(0x14, 0x18))
    recs = {}
    for t in (SKATER_T, GOALIE_T):
        tb = db.by_name[t]
        recs[t] = (tb['records'], tb['reclen'], tb['rows'])
    expect = defaultdict(dict)                         # (таблица, строка) → {поле: значение}
    index = {t: row_index(db, t) for t in (SKATER_T, GOALIE_T)}
    for x in log:
        expect[(x['table'], index[x['table']][x['game_id']])][x['field']] = x['new']
    diff = [i for i in range(len(out)) if out[i] != src[i]]
    for i in diff:
        if i in allowed:
            continue
        hit = None
        for t, (start, reclen, nrows) in recs.items():
            if start <= i < start + reclen * nrows:
                hit = (t, (i - start) // reclen)
                break
        if hit is None or hit not in expect:
            problems.append(f'байт 0x{i:x} изменился вне полей экипировки')
            if len(problems) > 20:
                break
    from tdb import Tdb
    before = Tdb(src, db.meta)
    for (t, r), fv in expect.items():
        for f in db.by_name[t]['fields']:
            want = fv.get(f, before.get(t, f, r))
            if db.get(t, f, r) != want:
                problems.append(f'{t}[{r}].{f}: {db.get(t, f, r)} вместо {want}')
    return problems


# --- status --------------------------------------------------------------------------------------
def coverage(paths, st, teams=None):
    by_team = defaultdict(Counter)
    for p in roster(paths, teams):
        c = by_team[p['team']]
        c['всего'] += 1
        rec = st['players'].get(str(p['nhl_id']))
        if not rec or not (rec.get('photo') or {}).get('kind'):
            continue
        c['просмотрено'] += 1
        if (rec.get('commons') or {}).get('reviewed'):
            c['commons'] += 1
        if not has_photo(rec):
            c['без фото'] += 1
            continue
        m = merged(rec)
        for k in VOCAB:
            if k in GOALIE_SKIP and p['pos'] == 'G':
                continue
            o = m.get(k)
            if o and o['conf'] == 'high':
                c[k + ':high'] += 1
                if o.get('src') not in (None, 'nhl'):
                    c[k + ':commons'] += 1
            elif o:
                c[k + ':other'] += 1
    return by_team


def cmd_roster(paths, a):
    """Отчёт apply → сохранённый состав игры (сейв ROSTER …): экипировку игра берёт только оттуда.

    Из cache:/db/nhlng.db экипировку игроков игра не подхватывает (08.10.2026: после установки базы
    с экипировкой у всех полевых в памяти значения EA 2012 года), а сохранённый состав загружает
    целиком. Новое значение ставится, только если в составе сейчас старое из отчёта: ручные правки
    пользователя в игре (там уже другое) не трогаются. Без --write — только подсчёт.
    Строки по game_id — только живые записи сейва (row_index): запас за current (0xDB) и удалённые
    записи не в счёт.
    """
    from tdb import SaveFile
    from tdb_read import load_meta
    from .common import ref_meta
    if common.GAME.name == 'nhl13':
        meta_path = a.meta or os.path.join(paths.game, 'userdata', 'cache', 'guest', 'db', 'nhlng-meta.xml')
    else:       # Legacy: схема, поставленная в cache: порта (или собранная в out/), сейв — ZlibV4 (tdb.SaveFile)
        inst = common.GAME.install
        meta_path = a.meta or next((p for p in (os.path.join(inst, 'db', 'nhlng-meta.xml') if inst else '',
                                                os.path.join(common.GAME.out, 'db', 'nhlng-meta.xml')) if p and os.path.exists(p)), '')
    if not os.path.exists(meta_path):
        meta_path = ref_meta()
    raw = open(a.save, 'rb').read()
    sf = SaveFile(raw, load_meta(meta_path))
    db = sf.db
    changes = json.load(open(a.report, encoding='utf-8'))['changes']
    index = {}
    done = same = kept = missing = 0
    for c in changes:
        # ключ строки: game_id, у таблиц без него (exhibitionrostertable) — поле из key_field (payroll_report --save)
        t, f, kf = c['table'], c['field'], c.get('key_field', 'game_id')
        if (t, kf) not in index:
            index[(t, kf)] = row_index(db, t, kf)
            dead = len(db.dead_rows(t))
            if dead:
                print(f'  {t}: строк {db.by_name[t]["rows"]}, из них не записи {dead} (запас за current, '
                      f'удалённые) — не в счёт')
        r = index[(t, kf)].get(c[kf])
        if r is None:
            missing += 1
            continue
        cur = db.get(t, f, r)
        if cur == c['new']:
            same += 1
        elif cur == c['old']:
            db.set(t, f, r, c['new'])
            done += 1
        else:
            kept += 1
            print(f'  оставлено (ручная правка): {c["name"]} {f}: в составе {cur}, у нас {c["new"]}')
    print(f'{"записано" if a.write else "будет записано"} {done}, уже было {same}, '
          f'ручные правки оставлены {kept}, нет в составе {missing}')
    if not a.write:
        return
    out = sf.bytes(fix=True)
    assert len(out) == len(raw), 'размер сейва изменился'
    bak = a.save + '.bak'
    if not os.path.exists(bak):
        open(bak, 'wb').write(raw)
    open(a.save, 'wb').write(out)
    bad = SaveFile(open(a.save, 'rb').read(), load_meta(meta_path)).verify()
    if bad:
        open(a.save, 'wb').write(raw)
        raise SystemExit(f'проверка не прошла, сейв возвращён: {bad}')
    print(f'сейв записан, проверка CRC/обёртки — OK; копия до правки — {bak}')


def cmd_status(paths, a):
    st = load_store(paths)
    cov = coverage(paths, st)
    tot = Counter()
    keys = ['tape', 'tongue', 'heel', 'jersey', 'visor']
    print('клуб  всего смотр. б/фото Commons  ' + '  '.join(f'{k}(в/пр)' for k in keys))
    for t, c in cov.items():
        if t not in TEAM_ORDER and not c['просмотрено']:
            continue
        tot.update(c)
        print(f'{t:5} {c["всего"]:5} {c["просмотрено"]:6} {c["без фото"]:6} {c["commons"]:7}  '
              + '  '.join(f'{c[k + ":high"]:3}/{c[k + ":other"]:<3}' for k in keys))
    print(f'итого {tot["всего"]:5} {tot["просмотрено"]:6} {tot["без фото"]:6} {tot["commons"]:7}  '
          + '  '.join(f'{tot[k + ":high"]:3}/{tot[k + ":other"]:<3}' for k in keys))
    print('из них уверенно по кадрам Commons: ' + ', '.join(f'{k} {tot[k + ":commons"]}' for k in keys))
    nhl = [t for t in TEAM_ORDER[:32] if t in cov]
    done = sum(1 for t in nhl if cov[t]['просмотрено'] == cov[t]['всего'])
    print(f'клубов НХЛ пройдено (фото НХЛ) {done} из {len(nhl)}')
    if a.values:                                   # распределение значений (уверенно, high)
        vals = defaultdict(Counter)
        pos = {p['nhl_id']: p['pos'] for p in roster(paths)}
        for nid, rec in st['players'].items():
            if int(nid) not in pos:
                continue
            for k, o in merged(rec).items():
                if o['conf'] == 'high':
                    vals[(k, 'G' if pos[int(nid)] == 'G' else 'F')][o['v']] += 1
        for (k, g), c in sorted(vals.items()):
            print(f'  {k:6} {"вратари" if g == "G" else "полевые"}: ' + ', '.join(f'{v} {n}' for v, n in c.most_common()))


# --- лист проверки -------------------------------------------------------------------------------
def crop_div(photo_href, box, W, H, h_px=120, max_w=230):
    x0, y0, x1, y1 = box
    x0, y0, x1, y1 = max(0, x0), max(0, y0), min(W, x1), min(H, y1)
    if x1 - x0 < 4 or y1 - y0 < 4:
        return ''
    s = min(h_px / (y1 - y0), max_w / (x1 - x0))
    w, h = round((x1 - x0) * s), round((y1 - y0) * s)
    return (f'<div class="crop" style="width:{w}px;height:{h}px;background-image:url(\'{photo_href}\');'
            f'background-size:{W * s:.1f}px {H * s:.1f}px;background-position:{-x0 * s:.1f}px {-y0 * s:.1f}px"></div>')


def fmt_code(field, v):
    if v is None:
        return '—'
    if field == 'sticktapecolor':
        return f'{v} {TAPE_CODE_RU.get(v, "?")}'
    if field == 'skatesocktuck':
        return f'{v} {SOCK_RU.get(v, "?")}'
    if field == 'jerseytuck':
        return f'{v} {JERSEY_RU.get(v, "?")}'
    if field == 'visortype':
        return f'{v} {VISOR_RU.get(v, "?")}'
    if field == 'visorcolor':
        return f'{v} {"прозрачный" if v == 0 else "тёмный" if v == 1 else "цветной"}'
    return str(v)


def images_html(paths, out_dir, fn, boxes, label=None, attrib=None):
    href = os.path.relpath(fn, out_dir).replace('\\', '/')
    href = urllib.parse.quote(href, safe='/.:-_')
    W, H = image_size(fn)
    s = (f'<a href="{href}" target="_blank"><img class="full" loading="lazy" src="{href}"></a>')
    for k in ('blade', 'skates'):
        b = (boxes or {}).get(k)
        if b:
            s += (f'<div class="cw"><div class="lbl">{"крюк" if k == "blade" else "коньки"}</div>'
                  f'{crop_div(href, b, W, H)}</div>')
    head = f'<div class="src">{label}</div>' if label else ''
    tail = f'<div class="attr">{attrib}</div>' if attrib else ''
    return f'<div class="srcbox">{head}<div class="imgs">{s}</div>{tail}</div>'


ASPECTS = [('обмотка', ['tape'], ['sticktapecolor']),
           ('гетры', ['tongue', 'heel'], ['skatesocktuck']),
           ('свитер', ['jersey'], ['jerseytuck']),
           ('визор', ['visor'], ['visortype', 'visorcolor'])]


def cmd_sheet(paths, a):
    st = load_store(paths)
    db_path = a.db or paths.db_out
    db = open_db(db_path, a.meta)
    teams = set(a.team.split(',')) if a.team else None
    rows = plan(paths, db, st, a.min_conf, tuple(a.fields.split(',')), a.visor_rule, a.jersey_rule, teams)
    out = a.out or os.path.join(store_dir(paths), 'sheet.html')
    out_dir = os.path.dirname(os.path.abspath(out))
    by_team = defaultdict(list)
    for row in rows:
        by_team[row[0]['team']].append(row)
    cov = coverage(paths, st, teams)
    parts = []
    toc = []
    for team in sorted(by_team, key=lambda t: (TEAM_ORDER.index(t) if t in TEAM_ORDER else 99, t)):
        c = cov[team]
        if team not in TEAM_ORDER and not c['просмотрено']:
            continue
        toc.append(f'<a href="#{team}">{team}</a> <span class="mut">{c["просмотрено"]}/{c["всего"]}</span>')
        cards = []
        for p, table, r, cur, new in by_team[team]:
            nid = p['nhl_id']
            rec = st['players'].get(str(nid))
            fn = photo_file(paths, nid)
            kind = ((rec or {}).get('photo') or {}).get('kind')
            imgs = ''
            if rec and kind == 'action' and os.path.exists(fn):
                imgs += images_html(paths, out_dir, fn, rec.get('boxes'), 'фото НХЛ')
            elif rec and kind in ('placeholder', 'none'):
                imgs += '<div class="nophoto">фото НХЛ: нет снимка игрока</div>'
            elif not rec:
                imgs += '<div class="nophoto">не просмотрен</div>'
            for f in ((rec or {}).get('commons') or {}).get('files', []):
                cf = cache_file(paths, f['file'])
                if os.path.exists(cf):
                    attrib = (f'<a href="{html.escape(f["page"])}" target="_blank">{html.escape(f["title"][5:][:60])}</a> · '
                              f'{html.escape(f.get("author") or "автор ?")} · '
                              + (f'<a href="{f["license_url"]}" target="_blank">{html.escape(f.get("license") or "")}</a>'
                                 if f.get('license_url') else html.escape(f.get('license') or 'лицензия ?'))
                              + ' · Wikimedia Commons')
                    imgs += images_html(paths, out_dir, cf, f.get('boxes'), f'Commons {f.get("year") or ""}', attrib)
            cnote = ((rec or {}).get('commons') or {}).get('note')
            m = merged(rec or {})
            trs = []
            for label, keys, dbf in ASPECTS:
                if p['pos'] == 'G' and label not in ('обмотка', 'свитер'):
                    continue
                seen = []
                for k in keys:
                    o = m.get(k)
                    if not o:
                        continue
                    txt = (f'{OBS_RU[k] + " " if len(keys) > 1 else ""}{VAL_RU.get(o["v"], o["v"])} · {o["conf"]}'
                           + (' · Commons' if o.get('src') not in (None, 'nhl') else ''))
                    if o.get('conflict'):
                        txt += ' · расхождение: ' + ', '.join(
                            f'{"НХЛ" if x["src"] == "nhl" else "Commons"} {VAL_RU.get(x["v"], x["v"])}' for x in o['conflict'])
                    seen.append(f'<span class="c-{o["conf"]}">{html.escape(txt)}</span>')
                obs_html = '<br>'.join(seen) or '<span class="c-no">не видно</span>'
                vals, whys, chg = [], [], False
                for f in dbf:
                    if f not in cur:
                        continue
                    if f in new and new[f][0] != cur[f]:
                        chg = True
                        vals.append(f'{fmt_code(f, cur[f])} → <b>{fmt_code(f, new[f][0])}</b>')
                        whys.append(new[f][1])
                    else:
                        vals.append(fmt_code(f, cur[f]))
                why = f'<div class="why">{html.escape("; ".join(whys))}</div>' if whys else ''
                trs.append(f'<tr class="{"chg" if chg else ""}" title="{html.escape(", ".join(dbf))}"><td>{label}</td>'
                           f'<td>{obs_html}</td><td>{"<br>".join(vals)}{why}</td></tr>')
            notes = [x for x in ((rec or {}).get('note'), cnote and f'Commons: {cnote}') if x]
            notes += [f'Commons: {f["note"]}' for f in ((rec or {}).get('commons') or {}).get('files', []) if f.get('note')]
            cards.append(
                f'<div class="card"><div class="hd"><b>#{p.get("jersey") or "?"} {html.escape(p["name"])}</b> '
                f'<span class="mut">{p["pos"]} · {nid} · {"новый" if p["new"] else "из базы 2012"}</span></div>'
                f'{imgs}<table class="fl"><tr><th></th><th>на фото</th><th>в базе → станет</th></tr>{"".join(trs)}</table>'
                + ''.join(f'<div class="note">{html.escape(x)}</div>' for x in notes) + '</div>')
        parts.append(f'<h2 id="{team}">{team} <span class="mut">просмотрено {c["просмотрено"]} из {c["всего"]}, '
                     f'без фото {c["без фото"]}, Commons {c["commons"]}</span></h2><div class="grid">{"".join(cards)}</div>')
    page = f'''<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Экипировка по фото</title>
<style>
:root{{--bg:#f6f6f4;--fg:#1d1d1b;--mut:#6b6b66;--card:#fff;--line:#ddd;--chg:#fff2c2;--hi:#1b7f3b;--med:#9a6b00;--lo:#b33}}
@media (prefers-color-scheme: dark){{:root{{--bg:#1b1b1a;--fg:#ececea;--mut:#9a9a94;--card:#262624;--line:#3a3a37;--chg:#4a3f12;--hi:#5fd38a;--med:#e0b14a;--lo:#ff7b7b}}}}
body{{margin:0;padding:16px;background:var(--bg);color:var(--fg);font:14px/1.4 system-ui,Segoe UI,sans-serif}}
h1{{font-size:20px;margin:0 0 8px}} h2{{font-size:17px;margin:24px 0 8px;border-bottom:1px solid var(--line)}}
.mut{{color:var(--mut);font-weight:normal;font-size:12px}} .toc a{{margin-right:4px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(330px,1fr));gap:10px}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:6px;padding:8px}}
.srcbox{{margin:6px 0}} .src{{font-size:11px;color:var(--mut)}} .attr{{font-size:11px;color:var(--mut)}}
.imgs{{display:flex;flex-wrap:wrap;gap:6px;align-items:flex-end}}
img.full{{width:150px;height:auto;display:block;border-radius:3px}}
.crop{{background-repeat:no-repeat;border-radius:3px;outline:1px solid var(--line)}}
.cw .lbl{{font-size:11px;color:var(--mut)}}
.nophoto{{color:var(--mut);font-style:italic;padding:6px 0}}
table{{border-collapse:collapse;width:100%;font-size:12px;margin-top:4px}} td,th{{padding:1px 4px;text-align:left;vertical-align:top}}
tr.chg td{{background:var(--chg)}} .c-high{{color:var(--hi)}} .c-med{{color:var(--med)}} .c-low,.c-no{{color:var(--lo)}}
.note{{font-size:12px;color:var(--mut);margin-top:4px}} a{{color:inherit}} .why{{font-size:11px;color:var(--mut)}}
table.fl td:first-child{{white-space:nowrap;color:var(--mut)}}
</style></head><body>
<h1>Экипировка по фото</h1>
<p class="mut">Папка конвейера: {html.escape(paths.work)} · база: {html.escape(db_path)} · порог уверенности: {a.min_conf} ·
правила: визор {"да" if a.visor_rule else "нет"}, свитер {"да" if a.jersey_rule else "нет"} · сгенерировано {now()}.
Жёлтым — что изменит <code>python -m roster.equipment apply</code> с теми же флагами. Кадры «крюк» и «коньки» вырезаны
из того же снимка; щелчок по снимку — исходник. Снимки Commons — со свободными лицензиями, автор и лицензия под снимком.</p>
<div class="toc">{" · ".join(toc)}</div>
{"".join(parts)}
</body></html>'''
    os.makedirs(out_dir, exist_ok=True)
    with open(out, 'w', encoding='utf-8', newline='\n') as f:
        f.write(page)
    print(f'лист → {out}')


# --- main ----------------------------------------------------------------------------------------
def main(argv=None):
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
    ap = argparse.ArgumentParser(prog='python -m roster.equipment', description=__doc__.splitlines()[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog='\n'.join(__doc__.splitlines()[2:]))
    ap.add_argument('--game', help='каталог game/ (по умолчанию — основной копии репозитория) или игра: nhl13, legacy '
                                   '(NHL Legacy, tools/gameprofile.py; иначе NHL_GAME, по умолчанию nhl13)')
    ap.add_argument('--work', help=f'папка конвейера с write.json (по умолчанию {DEFAULT_WORK}, у Legacy — '
                                   f'game/work/legacy-data/{DEFAULT_WORK_LEGACY})')
    sub = ap.add_subparsers(dest='cmd', required=True)
    s = sub.add_parser('fetch')
    s.add_argument('--team')
    s.add_argument('--pause', type=float, default=1.2)
    s = sub.add_parser('todo')
    s.add_argument('--team')
    s.add_argument('--all', action='store_true', help='и уже просмотренных')
    s.add_argument('--commons', action='store_true', help='кому смотреть кадры Commons')
    s = sub.add_parser('zoom')
    s.add_argument('id', help='nhl_id или путь к снимку')
    s.add_argument('boxes', nargs='+', help='кадры X0,Y0,X1,Y1 в пикселях снимка')
    s.add_argument('--height', type=int, default=420)
    s.add_argument('--out')
    s = sub.add_parser('commons')
    s.add_argument('--team')
    s.add_argument('--max', type=int, default=4, help='снимков на игрока (самые свежие)')
    s.add_argument('--pause', type=float, default=1.2)
    s.add_argument('--all', action='store_true', help='и тем, кому фото НХЛ хватило')
    s.add_argument('--retry', action='store_true', help='заново искать тех, у кого кадров не нашлось')
    s.add_argument('--refresh', action='store_true', help='заново для всех')
    s = sub.add_parser('csheet')
    s.add_argument('id')
    s.add_argument('--out')
    s = sub.add_parser('meta')
    s.add_argument('--pause', type=float, default=1.2)
    s.add_argument('--refresh', action='store_true')
    s = sub.add_parser('record')
    s.add_argument('file', help='JSON со списком наблюдений или - (stdin)')
    s.add_argument('--by', default='claude')
    s = sub.add_parser('status')
    s.add_argument('--values', action='store_true', help='и распределение уверенных значений')
    s = sub.add_parser('roster')
    s.add_argument('save', help='файл сейва ROSTER … (userdata/<профиль>/4541099B/00000001/ROSTER …/ROSTER …)')
    s.add_argument('--report', required=True, help='отчёт apply (equipment-apply.json)')
    s.add_argument('--meta', help='nhlng-meta.xml (по умолчанию из cache: игры)')
    s.add_argument('--write', action='store_true', help='записать (без него — только подсчёт)')
    for name in ('sheet', 'apply'):
        s = sub.add_parser(name)
        if name == 'apply':
            s.add_argument('db_in')
            s.add_argument('db_out')
            s.add_argument('--dry-run', action='store_true')
            s.add_argument('--report', help='JSON со списком изменений')
        else:
            s.add_argument('--db', help='база для колонки «в базе» (по умолчанию <work>/nhlng.db)')
            s.add_argument('--team')
            s.add_argument('--out')
        s.add_argument('--fields', default=','.join(DEFAULT_FIELDS),
                       help=f'поля через запятую из {",".join(FIELDS)} (по умолчанию все)')
        s.add_argument('--min-conf', choices=['high', 'med'], default='high')
        s.add_argument('--visor-rule', action='store_true',
                       help="визор у всех полевых, кроме Benn, O'Reilly, Bogosian (без визора), — и без фото")
        s.add_argument('--jersey-rule', action='store_true', help='свитер не заправлен у всех (НХЛ 2026/27)')
        s.add_argument('--meta', help='nhlng-meta.xml (по умолчанию рядом с базой или анкер)')
    a = ap.parse_args(argv)
    import gameprofile
    profile = None
    if a.game and a.game.lower() in gameprofile.GAMES:      # --game legacy — игра, а не каталог
        profile, a.game = a.game.lower(), None
    game = set_game(profile or gameprofile.default_name())
    a.work = a.work or (DEFAULT_WORK if game.name == 'nhl13' else DEFAULT_WORK_LEGACY)
    paths = Paths(a.game, a.work)
    {'fetch': cmd_fetch, 'todo': cmd_todo, 'zoom': cmd_zoom, 'commons': cmd_commons, 'csheet': cmd_csheet,
     'meta': cmd_meta, 'record': cmd_record, 'status': cmd_status, 'sheet': cmd_sheet, 'apply': cmd_apply,
     'roster': cmd_roster}[a.cmd](paths, a)


if __name__ == '__main__':
    main()
