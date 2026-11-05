"""Настоящий календарь сезона НХЛ → NHL Legacy: первый сезон новых франшиз и ближайший матч любимой команды (этап build-all «schedule»).

Просьба пользователя 02.11.2026: календарь 2026/27 из NHL 27 — для новых франшиз и для ближайшего матча любимой команды (пара
клубов по умолчанию на PLAY NOW / SELECT TEAMS). Описание, разбор игры и что проверено — docs/schedule.md.

    python tools/legacy_data/schedule.py show                     # какой календарь возьмётся: источник, проверка, первые матчи
    python tools/legacy_data/schedule.py fetch                    # скачать календарь сезона из API НХЛ в кэш (пауза 1,1 с)
    python tools/legacy_data/schedule.py check                    # сверить календарь дампа EA с API НХЛ матч в матч
    python tools/legacy_data/schedule.py db                       # проба: что изменится в out*, ничего не пишет
    python tools/legacy_data/schedule.py db --write               # запись в out, out-ahl32, out-nhl24, out-nhl24-ahl32
    python tools/legacy_data/schedule.py db ПУТЬ/nhlng.db --write # запись в одну базу (рядом — копия таблиц в backup)
    python tools/legacy_data/schedule.py save "…/ROSTER 2026…/ROSTER 2026…"          # проба по сейву состава
    python tools/legacy_data/schedule.py save СЕЙВ --out КОПИЯ    # результат — в копию, исходник не трогается
    python tools/legacy_data/schedule.py save СЕЙВ --write        # на месте; копия до правки — legacy-data/backup-saves/
    python tools/legacy_data/schedule.py db ЦЕЛЬ --from-db БАЗА --write   # откат: обе таблицы из другой базы Legacy
    NHL_SEASON=2027 python tools/legacy_data/schedule.py fetch    # следующий сезон (tools/season.py); источник — API

Что меняется: только таблицы `nhlschedule` (её читает создание франшизы, «Стань профи» и сезон) и `favoriteteamschedule`
(её читает выбор ближайшего матча). Поля index, home, away, month, day; round и status = 0, число строк то же. Таблица следующих
сезонов `nhlfutureschedule` не меняется: со второго сезона франшиза живёт как раньше, по ней и переносу дат игры.

Обе таблицы лежат и в сейве ROSTER (группа rosters), а игра при запуске грузит самый новый ROSTER поверх базы: без команды
`save` новая база на виджет и новые франшизы не повлияет. Сейвы франшиз (DYNASTY, BEAPRO) не трогаются и не нужны: календарь
созданной франшизы — её таблица leaguescheduletable.

Источники (--source):
- `nhl27` — база дампа NHL 27 (game/work/nhl27/db/nhl_game.db, NHL27_DB=путь): таблица nhlschedule. Без сети, сверена с API
  НХЛ 02.11.2026: 1344 из 1344 матчей совпали по дате, хозяевам и гостям. Годится только для сезона EA_SEASON;
- `api` — api-web.nhle.com, /v1/club-schedule-season/{клуб}/{сезон}, только регулярка (gameType 2), дата — местная (gameDate).
  Кэш — game/work/schedule/api/<сезон>/ (команда fetch; без неё сети нет);
- `auto` (по умолчанию) — nhl27, если сезон совпал и база есть, иначе кэш api.

Номера клубов: home/away в таблицах — номер внутри лиги (строка exhibitionteams). Сверяются по аббревиатуре в обеих
базах: у NHL 27 номера 30/31 — VGK/SEA, у Legacy — SEA/VGK, остальные совпадают.

Строка Матча звёзд (хозяева ≥ числа клубов, есть только в базах без --ahl32) остаётся и встаёт на воскресенье
перерыва (самый длинный разрыв между игровыми днями в январе–феврале).

Проверки перед записью: у всех клубов поровну игр, домашних — половина, никто не играет дважды в день, нет повторов, даты —
настоящие даты сезона, первая строка — самая ранняя (игра считает старт франшизы от первой строки: минус 17 дней).
После записи: CRC базы и обёртки, размер файла сейва тот же, прочие таблицы байт в байт, повторный план пуст.
"""
import argparse
import collections
import datetime
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
REPO = os.path.dirname(TOOLS)
sys.path.insert(0, TOOLS)
import season as S  # noqa: E402
from gameprofile import game_dir  # noqa: E402
from tdb import SaveFile, Tdb, load_meta  # noqa: E402

GAME = game_dir()
W_DIR = os.path.abspath(os.environ.get('LEGACY_DATA_WORK') or os.path.join(GAME, 'work', 'legacy-data'))
NHL27_DB = os.environ.get('NHL27_DB') or os.path.join(GAME, 'work', 'nhl27', 'db', 'nhl_game.db')
API_CACHE = os.environ.get('SCHEDULE_CACHE') or os.path.join(GAME, 'work', 'schedule', 'api')
API = 'https://api-web.nhle.com/v1/club-schedule-season/{club}/{season}'
API_PAUSE = 1.1                     # не чаще раза в секунду (то же правило, что у tools/roster/fetch.py)
EA_SEASON = {'nhl27': 2026}         # дамп EA → первый год сезона в его nhlschedule: в таблице года нет, только месяц и день
TABLES = ('nhlschedule', 'favoriteteamschedule')
VARIANTS = ('out', 'out-ahl32', 'out-nhl24', 'out-nhl24-ahl32')
N_TEAMS = 32

# Аббревиатуры клубов как в API НХЛ; в базах EA и Legacy часть пишется иначе
CLUBS = ('ANA BOS BUF CAR CBJ CGY CHI COL DAL DET EDM FLA LAK MIN MTL NJD NSH NYI NYR OTT PHI PIT SEA SJS STL TBL TOR UTA '
         'VAN VGK WPG WSH').split()
ALIASES = {'LA': 'LAK', 'NJ': 'NJD', 'SJ': 'SJS', 'TB': 'TBL', 'UT': 'UTA', 'ARI': 'UTA', 'ARZ': 'UTA', 'PHX': 'UTA'}


def say(*a):
    print(*a, flush=True)


def club(abbr):
    a = abbr.strip().upper()
    a = ALIASES.get(a, a)
    if a not in CLUBS:
        sys.exit(f'неизвестный клуб «{abbr}»: допишите в ALIASES')
    return a


def season_date(year, month, day):
    """Дата матча по месяцу и дню таблицы (с нуля): сентябрь–декабрь — год year, январь–август — year + 1, как у игры."""
    return datetime.date(year if month >= 8 else year + 1, month + 1, day + 1)


def team_numbers(db):
    """Клуб → номер внутри лиги: строки exhibitionteams лиги 0 в порядке номера; заодно проверка, что клубов 32."""
    t = 'exhibitionteams'
    teams = {}
    for r in db.live_rows(t):
        if db.get(t, 'league', r) == 0 and db.get(t, 'index', r) < N_TEAMS:
            teams[club(db.get_string(t, 'abbrname', r))] = db.get(t, 'index', r)
    if sorted(teams) != sorted(CLUBS) or sorted(teams.values()) != list(range(N_TEAMS)):
        sys.exit(f'в базе не 32 клуба с номерами 0…31: {sorted(teams.items(), key=lambda x: x[1])}')
    return teams


# ---------------------------------------------------------------- источники: список (дата, хозяева, гости) по порядку

def from_nhl27(path, year):
    if not os.path.isfile(path):
        sys.exit(f'нет базы NHL 27: {path} (docs/import-from-ea.md, prepare; другой путь — NHL27_DB)')
    meta = load_meta(os.path.splitext(path)[0] + '-meta.xml')
    db = Tdb(open(path, 'rb').read(), meta)
    names = {v: k for k, v in team_numbers(db).items()}
    t = 'nhlschedule'
    out = []
    for r in db.live_rows(t):
        h, a = db.get(t, 'home', r), db.get(t, 'away', r)
        if h >= N_TEAMS or a >= N_TEAMS:            # Матч звёзд дампа не берём: своя строка есть только у баз без --ahl32
            continue
        out.append((season_date(year, db.get(t, 'month', r), db.get(t, 'day', r)), names[h], names[a]))
    return out


def api_dir(year):
    return os.path.join(API_CACHE, str(year))


def fetch(year):
    os.makedirs(api_dir(year), exist_ok=True)
    season = year * 10000 + year + 1
    for i, c in enumerate(CLUBS):
        url = API.format(club=c, season=season)
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                data = r.read()
        except urllib.error.URLError as e:
            sys.exit(f'{url}: {e}')
        n = sum(1 for g in json.loads(data)['games'] if g['gameType'] == 2)
        open(os.path.join(api_dir(year), c + '.json'), 'wb').write(data)
        say(f'{c}: {n} матчей регулярки')
        if i + 1 < len(CLUBS):
            time.sleep(API_PAUSE)


def from_api(year):
    games = {}
    for c in CLUBS:
        p = os.path.join(api_dir(year), c + '.json')
        if not os.path.isfile(p):
            sys.exit(f'нет кэша {p}: сначала schedule.py fetch')
        for g in json.load(open(p, encoding='utf-8'))['games']:
            if g['gameType'] == 2:
                games[g['id']] = g
    rows = sorted(games.values(), key=lambda g: (g['gameDate'], g.get('startTimeUTC', ''), g['id']))
    return [(datetime.date.fromisoformat(g['gameDate']), club(g['homeTeam']['abbrev']), club(g['awayTeam']['abbrev']))
            for g in rows]


def from_db(path):
    """Откат: строки обеих таблиц другой базы Legacy как есть, вместе с Матчем звёзд и порядком."""
    meta = load_meta(os.path.join(os.path.dirname(path), 'nhlng-meta.xml') if os.path.isfile(
        os.path.join(os.path.dirname(path), 'nhlng-meta.xml')) else cache_meta())
    db = Tdb(open(path, 'rb').read(), meta)
    return {t: [tuple(db.get(t, f, r) for f in ('month', 'day', 'home', 'away')) for r in db.live_rows(t)] for t in TABLES}


def load_source(a):
    """(имя источника, список матчей) по --source и сезону."""
    year = S.YEAR
    src = a.source
    if src == 'auto':
        src = 'nhl27' if EA_SEASON['nhl27'] == year and os.path.isfile(a.db27) else 'api'
    if src == 'nhl27':
        if EA_SEASON['nhl27'] != year:
            sys.exit(f'в дампе NHL 27 календарь {EA_SEASON["nhl27"]}/{(EA_SEASON["nhl27"] + 1) % 100}, а сезон сборки '
                     f'{S.LABEL}: --source api или другой сезон (NHL_SEASON)')
        return 'база NHL 27', from_nhl27(a.db27, year)
    return 'API НХЛ (кэш)', from_api(year)


# ---------------------------------------------------------------- проверка

def problems(games, year):
    out = []
    played, home, seen, day_teams = collections.Counter(), collections.Counter(), set(), collections.defaultdict(list)
    if not games:
        return ['календарь пуст']
    for d, h, a in games:
        played[h] += 1
        played[a] += 1
        home[h] += 1
        if h == a:
            out.append(f'{d}: {h} сам с собой')
        if (d, h, a) in seen:
            out.append(f'{d}: {a} @ {h} дважды')
        seen.add((d, h, a))
        day_teams[d] += [h, a]
        if not (datetime.date(year, 8, 1) <= d <= datetime.date(year + 1, 7, 31)):
            out.append(f'{d}: вне сезона {year}/{year + 1}')
    if sorted(played) != sorted(CLUBS):
        out.append(f'клубы: не хватает {sorted(set(CLUBS) - set(played))}')
    per = set(played.values())
    if len(per) != 1:
        out.append(f'у клубов разное число игр: {sorted(played.items(), key=lambda x: x[1])[:3]}…')
    else:
        n = per.pop()
        if any(home[c] * 2 != n for c in played):
            out.append(f'домашних не половина: {sorted(home.items(), key=lambda x: x[1])[:3]}…')
    for d, t in sorted(day_teams.items()):
        twice = [c for c, k in collections.Counter(t).items() if k > 1]
        if twice:
            out.append(f'{d}: дважды в день {twice}')
    if [g[0] for g in games] != sorted(g[0] for g in games):
        out.append('строки не по порядку дат (игра считает старт франшизы от первой строки)')
    return out


def breaks(games):
    days = sorted({g[0] for g in games})
    return [(a, b) for a, b in zip(days, days[1:]) if (b - a).days > 1]


def summary(name, games, year):
    days = sorted({g[0] for g in games})
    say(f'сезон {S.LABEL}, источник: {name}')
    say(f'матчей {len(games)}, игровых дней {len(days)}, {days[0]} … {days[-1]}')
    say('по месяцам:', ', '.join(f'{k}: {v}' for k, v in sorted(collections.Counter(g[0].strftime('%Y-%m') for g in games).items())))
    say('перерывы:', ', '.join(f'{a} → {b}' for a, b in breaks(games)) or 'нет')
    for c in ('TBL', 'MIN', 'SEA'):
        first = [g for g in games if c in g[1:]][:3]
        say(f'{c}:', ', '.join(f'{d:%d.%m} {a} @ {h}' for d, h, a in first))
    bad = problems(games, year)
    say('проверка:', 'всё сходится' if not bad else bad[:8])
    return bad


# ---------------------------------------------------------------- запись

def allstar_day(games, year):
    """Воскресенье самого длинного разрыва в январе–феврале, иначе его последний день; разрыва нет — None."""
    gaps = [(a, b) for a, b in breaks(games) if a.month in (1, 2)]
    if not gaps:
        return None
    a, b = max(gaps, key=lambda g: (g[1] - g[0]).days)
    days = [a + datetime.timedelta(days=i) for i in range(1, (b - a).days)]
    sunday = [d for d in days if d.weekday() == 6]
    return sunday[0] if sunday else days[-1]


def rows_for(db, table, games, numbers, year):
    """Строки таблицы (месяц, день, хозяева, гости) по порядку: матчи календаря + прежние строки Матча звёзд на новый день."""
    live = db.live_rows(table)
    allstar = [(db.get(table, 'home', r), db.get(table, 'away', r), db.get(table, 'month', r), db.get(table, 'day', r))
               for r in live if db.get(table, 'home', r) >= N_TEAMS or db.get(table, 'away', r) >= N_TEAMS]
    rows = [(d, numbers[h], numbers[a]) for d, h, a in games]
    day = allstar_day(games, year)
    for h, a, m, dd in allstar:
        d = day or season_date(year, m, dd)
        if any(g[0] == d for g in games):
            sys.exit(f'{table}: на день Матча звёзд {d} есть игры')
        rows.append((d, h, a))
    rows.sort(key=lambda x: x[0])             # sort устойчивая: порядок матчей внутри дня — как в источнике
    return [(d.month - 1, d.day - 1, h, a) for d, h, a in rows]


def plan(db, table, rows):
    """Правки таблицы: [(строка, поле, было, стало)]; число строк должно совпасть, кроме простых баз (resize — вне плана)."""
    live = db.live_rows(table)
    out = []
    for i, (r, (month, day, home, away)) in enumerate(zip(live, rows)):
        for f, v in (('index', i), ('home', home), ('away', away), ('month', month), ('day', day), ('round', 0), ('status', 0)):
            if db.get(table, f, r) != v:
                out.append((r, f, db.get(table, f, r), v))
    return out


def apply_table(db, table, rows, resize):
    live = db.live_rows(table)
    if len(live) != len(rows):
        if not resize:
            sys.exit(f'{table}: в сейве {len(live)} строк, а нужно {len(rows)}: сейв этой базы не подходит, число строк менять нельзя')
        say(f'  {table}: строк {len(live)} → {len(rows)}')
        db.resize(table, len(rows))
    ch = plan(db, table, rows)
    for r, f, _, v in ch:
        db.set(table, f, r, v)
    return ch


def cache_meta():
    from install_legacy_data import cache_dir, cache_file  # noqa: E402 (рядом, тяжёлый импорт только здесь)
    return cache_file(cache_dir(), 'db/nhlng-meta.xml')


def targets(a):
    if a.targets:
        return [(os.path.basename(os.path.dirname(os.path.dirname(os.path.abspath(p)))) or os.path.basename(p), os.path.abspath(p))
                if p not in VARIANTS else (p, os.path.join(W_DIR, p, 'db', 'nhlng.db')) for p in a.targets]
    out = [(v, os.path.join(W_DIR, v, 'db', 'nhlng.db')) for v in VARIANTS]
    return [(n, p) for n, p in out if os.path.isfile(p)]


def meta_for(path, a):
    beside = os.path.join(os.path.dirname(path), 'nhlng-meta.xml')
    if a.meta:
        return a.meta
    if os.path.isfile(beside):
        return beside
    # накладки out-nhl24* лежат без схемы: у них та же, что у базы варианта
    variant = os.path.basename(os.path.dirname(os.path.dirname(path)))
    if variant.startswith('out-nhl24'):
        base = os.path.join(W_DIR, 'out-ahl32' if variant.endswith('ahl32') else 'out', 'db', 'nhlng-meta.xml')
        if os.path.isfile(base):
            return base
    return cache_meta()


def tables_only_changed(before, after):
    """Вне двух таблиц всё байт в байт: сравнение записей всех таблиц по именам (размер таблиц календаря мог измениться)."""
    bad = []
    for t in before.tables:
        if t['name'] in TABLES:
            continue
        o = after.by_name.get(t['name'])
        if o is None or o['rows'] != t['rows'] or o['reclen'] != t['reclen']:
            bad.append(t['name'])
            continue
        n = t['rows'] * t['reclen']
        if before.d[t['records']:t['records'] + n] != after.d[o['records']:o['records'] + n]:
            bad.append(t['name'])
    return bad


def wanted(a):
    """Функция таблица, база → нужные строки: из календаря или (--from-db) из другой базы."""
    if a.from_db:
        old = from_db(os.path.abspath(a.from_db))
        say(f'источник: таблицы базы {a.from_db}')
        return lambda db, t: old[t], False
    name, games = load_source(a)
    if summary(name, games, S.YEAR):
        sys.exit('календарь не прошёл проверку, ничего не пишу')
    return lambda db, t: rows_for(db, t, games, team_numbers(db), S.YEAR), True


def game_running():
    tl = subprocess.run(['tasklist'], capture_output=True, text=True, errors='replace').stdout.lower()
    return 'nhllegacy' in tl


def cmd_db(a):
    make, _ = wanted(a)
    paths = targets(a)
    if not paths:
        sys.exit(f'нет баз {VARIANTS} в {W_DIR} (сначала build-all.sh)')
    for name, path in paths:
        if not os.path.isfile(path):
            if name in VARIANTS:                  # сборка без --ahl32 и без накладок: этап build-all идёт дальше
                say(f'{name}: базы нет — пропуск')
                continue
            sys.exit(f'нет базы {path}')
        data = open(path, 'rb').read()
        meta = load_meta(meta_for(path, a))
        db = Tdb(data, meta)
        before = Tdb(data, meta)
        total = 0
        for t in TABLES:
            rows = make(db, t)
            ch = apply_table(db, t, rows, resize=True)
            total += len(ch)
            say(f'{name}: {t}: строк {len(rows)}, правок полей {len(ch)}')
        if not a.write:
            continue
        if not total and bytes(db.d) == data:
            say(f'{name}: уже такая — не пишу')
            continue
        db.fix()
        out = bytes(db.d)
        chk = Tdb(out, meta)
        bad = [f'CRC @{o:X}' for o, _, _ in chk.verify()] + tables_only_changed(before, chk)
        if any(plan(chk, t, make(chk, t)) for t in TABLES):
            bad.append('повторный план не пуст')
        if bad:
            sys.exit(f'{name}: проверка не прошла, ничего не записано: {bad}')
        bk = os.path.join(W_DIR, 'schedule', 'backup', f'{name}-{time.strftime("%Y%m%d-%H%M%S")}')
        os.makedirs(bk, exist_ok=True)
        shutil.copy2(path, os.path.join(bk, 'nhlng.db'))
        open(path, 'wb').write(out)
        say(f'{name}: записано {path}; копия до правки — {bk}')


def cmd_save(a):
    if len(a.targets) != 1 or not os.path.isfile(a.targets[0]):
        sys.exit('нужен файл сейва: …/ROSTER <время>/ROSTER <время>')
    save = os.path.abspath(a.targets[0])
    if a.write and a.out:
        sys.exit('или --out (в другой файл), или --write (на месте)')
    if a.out and os.path.abspath(a.out) == save:
        sys.exit('--out совпадает с исходным сейвом — для записи на месте --write')
    make, _ = wanted(a)
    meta = load_meta(a.meta or cache_meta())
    raw = open(save, 'rb').read()
    sf = SaveFile(raw, meta)
    bad0 = sf.verify()
    if bad0:
        sys.exit(f'{save}: сейв не проходит проверку ещё до правки: {bad0}')
    if not all(t in sf.db.by_name for t in TABLES):
        sys.exit(f'{save}: в сейве нет таблиц календаря — это сейв состава? (нужен ROSTER; DYNASTY и BEAPRO не меняются)')
    before = Tdb(bytes(sf.db.d), meta)
    total = 0
    for t in TABLES:
        ch = apply_table(sf.db, t, make(sf.db, t), resize=False)
        total += len(ch)
        say(f'{os.path.basename(save)}: {t}: правок полей {len(ch)}')
    if not (a.out or a.write):
        return
    if not total:
        say('сейв уже такой — не пишу')
        return
    if a.write and game_running():
        sys.exit('запущена игра — сейв на месте не пишу: игра при выходе перезапишет его своим; закройте игру')
    out = sf.bytes(fix=True)
    if len(out) != len(raw):
        sys.exit(f'размер сейва изменился ({len(raw)} → {len(out)}) — не пишу')
    chk = SaveFile(out, meta)
    bad = chk.verify() + tables_only_changed(before, chk.db)
    if any(plan(chk.db, t, make(chk.db, t)) for t in TABLES):
        bad.append('повторный план не пуст')
    if bad:
        sys.exit(f'проверка не прошла, ничего не записано: {bad}')
    dst = os.path.abspath(a.out) if a.out else save
    if a.write:
        name = os.path.basename(save)
        bdir = os.path.join(W_DIR, 'backup-saves', f'{name}-{time.strftime("%Y%m%d-%H%M%S")}')
        os.makedirs(bdir, exist_ok=True)
        shutil.copy2(save, os.path.join(bdir, name + '.bak'))
        say(f'копия до правки — {bdir}')
    open(dst, 'wb').write(out)
    say(f'записано {dst}')


def cmd_show(a):
    name, games = load_source(a)
    sys.exit(1 if summary(name, games, S.YEAR) else 0)


def cmd_check(a):
    year = S.YEAR
    ea, api = from_nhl27(a.db27, year), from_api(year)
    ce, ca = collections.Counter(ea), collections.Counter(api)
    same = sum((ce & ca).values())
    pairs = sum((collections.Counter(g[1:] for g in ea) & collections.Counter(g[1:] for g in api)).values())
    say(f'NHL 27: {len(ea)} матчей, API НХЛ: {len(api)}')
    say(f'совпало дата + хозяева + гости: {same}; без учёта даты: {pairs}')
    for g in list((ce - ca).elements())[:10]:
        say('  только в NHL 27:', g)
    for g in list((ca - ce).elements())[:10]:
        say('  только в API:', g)
    sys.exit(0 if same == len(ea) == len(api) else 1)


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('cmd', choices=('show', 'fetch', 'check', 'db', 'save'))
    p.add_argument('targets', nargs='*', help='db: out, out-ahl32, out-nhl24, out-nhl24-ahl32 или путь к nhlng.db; save: файл ROSTER')
    p.add_argument('--source', choices=('auto', 'nhl27', 'api'), default='auto', help='откуда календарь (auto — см. выше)')
    p.add_argument('--db27', default=NHL27_DB, help='база NHL 27 (nhl_game.db, рядом — nhl_game-meta.xml)')
    p.add_argument('--from-db', help='откат: взять обе таблицы как есть из этой базы Legacy')
    p.add_argument('--meta', help='схема nhlng-meta.xml (по умолчанию рядом с базой, для сейва — установленная)')
    p.add_argument('--write', action='store_true', help='записать (без него — только показать план)')
    p.add_argument('--out', help='save: результат в этот файл, исходный сейв не трогается')
    a = p.parse_args()
    if a.cmd == 'fetch':
        fetch(S.YEAR)
    else:
        {'show': cmd_show, 'check': cmd_check, 'db': cmd_db, 'save': cmd_save}[a.cmd](a)


if __name__ == '__main__':
    main()
