"""НХЛ на 32 команды: Seattle Kraken и Vegas Golden Knights — новые клубы на пустых слотах.

    python nhl32.py DB_IN DB_OUT LOC_IN LOC_OUT [--seed N] [--meta META_IN META_OUT]

Почему так (разбор — docs/teams.md):
- Календарь НХЛ (nhlschedule) хранит номер команды в лиге 5 битами (0–31), а команды
  НХЛ — строки 0–29 базы. Строки 30/31 занимали сборные Матча звёзд (Red/Blue). Новые
  клубы встают на 30 и 31 из пустых заготовок «Custom Team 00/01» (строки 218/219 — места
  игры под созданные команды), сборные переезжают на их место. Другие лиги не трогаются
  (до 08.10.2026 клубами 30/31 были Tappara и TPS из финской лиги).
- Строки exhibitionteams и exhibitionteamstrategies меняются местами целиком, во всех
  таблицах ссылки на номера переписываются: где номер хранится с нуля — 30↔218, 31↔219,
  где «номер + 1» (0 = нет) — 31↔219, 32↔220. Поле, в которое новый номер не влезает
  (цвета команд, 7 бит), не переписывается: записи остаются у строк 30/31.
- Заготовки заполняются как клубы НХЛ (fill_new_teams): названия, цвета, активность, лига,
  тактика (как у соседа по дивизиону), своя арена НХЛ-размера (копия нейтральной «EA SPORTS
  Arena»), комплекты формы (пока копии Tappara/TPS — своих текстур ещё нет), цвета шлемов,
  перчаток и прочей экипировки (строки Tappara/TPS, перекрашенные в цвета клуба), свои
  номера арта 98/99 (свободны везде) — у команды и у её комплектов формы, прожекторы 45/46,
  номер звука 32/33 (свободный: 0 — это «Анахайм»). Файлы под 98/99 (логотипы, центр льда,
  шайба, баннер, прожекторы, копии формы Tappara/TPS) — tools/teamart.py, game/work/logos/
  (docs/logos-arenas.md). Вратарская экипировка в базе — по вратарям (game_id + команда),
  командной нет: вратари новых клубов — со стандартной.
- Календарь — формат НХЛ с сезона 2026/27: 84 игры (по 4 с соперниками по дивизиону,
  по 3 с остальной конференцией, по 2 с другой конференцией), 42 дома, по нынешним
  4 дивизионам; раскладывается на игровые дни календаря 2012/13. В самой игре 6
  дивизионов (пустой опасен: плей-офф 2012 года ищет победителя каждого), поэтому
  турнирная таблица делится на «поддивизионы» нынешних — 6 + 5 + 5 в конференции.
- Строки локализации: ключи по номеру (NHLTeamName_30…) — на новые строки, ключи по
  аббревиатуре (NHLTeamName_SEA…) добавляются; сборным — ключи по EAS/WES (по номеру
  218/219 ключей нет, а BLU — это Espoo Blues).
- Поля «команда НХЛ» в exhibitionplayerbiotable (proteam, draftteam: номер + 1, 5 бит)
  расширяются до 6 бит — иначе у Вегаса (31 + 1 = 32) они не влезают.
"""
import argparse, random, re, struct, sys
from collections import Counter, defaultdict
from tdb import Tdb, DEFAULT_META
from tdb_read import load_meta
from locdb import LocDb

SWAP = {30: 218, 31: 219}          # новый клуб НХЛ ← пустая заготовка «Custom Team 00/01»
ALLSTAR_ROWS = (218, 219)          # сборные Матча звёзд после обмена
TEMPLATE_ARENA = 168               # «EA SPORTS Arena»: нейтральная, площадка НХЛ (arenatype 0)
# Новые клубы. kit — строка, чьи комплекты формы и цвета экипировки копируются (пока своих
# текстур нет), equip — перекраска экипировки kit (цвет → цвет), strategy — чья тактика,
# rival — соперник (номер строки). art — номер арта: логотипы, центр льда, шайба, баннер и
# текстуры формы (рендер берёт artid команды, меню — teamartid комплекта; у EA они равны),
# spotlight — логотип прожекторов, audio — номер звука (свободный: без записей).
NEW_TEAMS = {
    30: dict(short='Seattle', full='Seattle Kraken', abbr='SEA', nick='Kraken', rival=28, strategy=28, kit=86,
             art=98, spotlight=45, audio=32,
             primary=(0, 22, 40), secondary=(153, 217, 217),
             # Tappara: синий, оранжевый, чёрный шлем → глубоководный синий, ледяной голубой
             equip={0x253B73: 0x001628, 0xE35B17: 0x99D9D9, 0xDE5818: 0x99D9D9, 0x202020: 0x001628},
             arena=dict(name='Climate Pledge Arena', city='Seattle, WA', capacity=17151)),
    31: dict(short='Vegas', full='Vegas Golden Knights', abbr='VGK', nick='Golden Knights', rival=13, strategy=13, kit=87,
             art=99, spotlight=46, audio=33,
             primary=(51, 63, 72), secondary=(185, 151, 91),
             # TPS: чёрный шлем, серый → стальной серый, золото
             equip={0x202020: 0x333F48, 0xB3B3B3: 0xB9975B},
             arena=dict(name='T-Mobile Arena', city='Las Vegas, NV', capacity=17500)),
}
# Сборные: имена — по ключам их аббревиатуры (своих ключей по номеру у строк 218/219 нет).
ALLSTAR_NAMES = {218: ('EAS', 'Eastern', 'Eastern All-Stars'), 219: ('WES', 'Western', 'Western All-Stars')}

# Поля-ссылки на команду: (таблица, поле, кодировка). 'zero' — номер строки,
# 'plus1' — номер + 1 (0 = нет команды). Проверено по известным игрокам и командам
# (stockteamequipmenttable до 08.10.2026 ошибочно считалась 'zero' — docs/uniforms.md §7).
TEAM_FIELDS = [
    ('stockteamjerseys', 'teamid', 'zero'),
    ('stockteamequipmenttable', 'team', 'plus1'),     # 255 (−1) — общие строки
    ('stockretirednumbertable', 'team', 'zero'),
    ('stockawardstable', 'team', 'zero'),
    ('stockplayoffteamstats', 'team', 'zero'),
    ('stockseasonteamstats', 'team', 'zero'),
    ('stockteamcolorstable', 'team', 'zero'),
    ('exhibitionplayerbiotable', 'team', 'plus1'),
    ('exhibitionplayerbiotable', 'proteam', 'plus1'),
    ('exhibitionplayerbiotable', 'draftteam', 'plus1'),
    ('exhibitionteams', 'rivalteam', 'plus1'),
    ('exhibitionteams', 'rivalteam2', 'plus1'),
    ('stockgoalieequipment', 'team', 'plus1'),
    ('exhibitiondraftpick', 'origteamid', 'plus1'),
    ('exhibitiondraftpick', 'owner', 'plus1'),
]
PER_TEAM_ROWS = ['exhibitionteams', 'exhibitionteamstrategies']
# Составы: team с нуля, key = team · 40 + место в составе, таблица отсортирована по key
# (нашёл агент конвейера базы; по puckpeak иначе ломается экран «Состав»).
ROSTER, ROSTER_SLOTS = 'exhibitionrostertable', 40

WEST, EAST = 1, 2
# divisiongroup: 3 Northwest, 4 Pacific, 5 Central (Запад); 6 Southeast, 7 Atlantic,
# 8 Northeast (Восток). 6 + 5 + 5 в каждой конференции.
DIVISIONS = {
    5: [6, 7, 9, 14, 16, 24],      # CHI COL DAL MIN NSH STL
    3: [1, 4, 11, 28, 30],         # WPG CGY EDM VAN SEA
    4: [0, 13, 25, 22, 31],        # ANA LA SJ PHX VGK
    6: [5, 8, 10, 12, 26, 29],     # CAR CBJ DET FLA TB WSH
    7: [17, 18, 19, 21, 23],       # NJ NYI NYR PHI PIT
    8: [2, 3, 15, 20, 27],         # BOS BUF MTL OTT TOR
}
CONFERENCE = {3: WEST, 4: WEST, 5: WEST, 6: EAST, 7: EAST, 8: EAST}
# Нынешние дивизионы НХЛ — по ним календарь (Юта — бывший Phoenix/Arizona, 22).
REAL_DIVISIONS = {
    'Atlantic': [2, 3, 10, 12, 15, 20, 26, 27],      # BOS BUF DET FLA MTL OTT TB TOR
    'Metropolitan': [5, 8, 17, 18, 19, 21, 23, 29],  # CAR CBJ NJ NYI NYR PHI PIT WSH
    'Central': [1, 6, 7, 9, 14, 16, 22, 24],         # WPG CHI COL DAL MIN NSH UTA STL
    'Pacific': [0, 4, 11, 13, 25, 28, 30, 31],       # ANA CGY EDM LA SJ VAN + SEA VGK
}
REAL_CONFERENCE = {'Atlantic': EAST, 'Metropolitan': EAST, 'Central': WEST, 'Pacific': WEST}
GAMES, HOME = 84, 42
# АХЛ-филиал (номер + 1) — общий с соседом по региону, своих клубов в АХЛ нет.
AHL_AFFILIATE = {30: 32 + 1, 31: 58 + 1}   # Abbotsford, Texas
# Вместимость таблиц франшизы = maxinsert в схеме nhlng-meta.xml (игра читает её из
# cache:\db\, сверено с сейвом франшизы): у этих — ровно под 30 команд.
# leaguetempscheduletable — 2 × 1350 игр (НХЛ + АХЛ), как буферы календаря в коде
# (их порт поднимает до 1600 — src/nhl13_teams.cpp).
META_MAXINSERT = {'leaguegmdata': 32, 'leaguestaffdata': 32, 'leaguedraftpick': 32 * 7 * 6,
                  'leaguetempscheduletable': 2 * 1600}
# Поля франшизы «команда НХЛ» шириной 5 бит с диапазоном −1…30 (хранится номер + 1): номер 31
# туда не влезает — расширяем до 6 бит (−1…62). Таблицы франшизы игра создаёт по этой схеме.
META_WIDEN = {
    'exhibitionplayerbiotable': ['proteam', 'draftteam'],
    'leaguedraftpick': ['origteamid', 'owner'],
    'leagueplayerbiotable': ['proteam', 'draftteam'],
    'leaguefreeagentdata': ['originalteamid', 'signedteamid'],
    'leaguerookiedata': ['draftteam'],
    'leaguecontractoffers': ['teamnotification'],
    'leagueretirementtable': ['team'],
    'leaguegamemodesvars': ['team'],
    'leaguescoutvisits': ['team'],
}

def swap_map(encoding):
    m = {}
    for a, b in SWAP.items():
        k = 1 if encoding == 'plus1' else 0
        m[a + k], m[b + k] = b + k, a + k
    return m

def move_teams(db):
    for table in PER_TEAM_ROWS:
        for a, b in SWAP.items():
            ra, rb = db.record(table, a), db.record(table, b)
            db.put_record(table, a, rb)
            db.put_record(table, b, ra)
    for a, b in SWAP.items():
        db.set('exhibitionteams', 'index', a, a)
        db.set('exhibitionteams', 'index', b, b)
    report = {f'{ROSTER}.team': move_roster(db)}
    for table, field, enc in TEAM_FIELDS:
        m = swap_map(enc)
        limit = (1 << db.by_name[table]['fields'][field][1]) - 1
        n = kept = 0
        for r in range(db.by_name[table]['rows']):
            v = db.get(table, field, r)
            if v in m:
                if m[v] > limit:
                    kept += 1  # не влезает (цвета команд, 7 бит) — запись остаётся у строки
                    continue
                db.set(table, field, r, m[v])
                n += 1
        report[f'{table}.{field}'] = n if not kept else f'{n} (оставлено {kept}: номер не влезает)'
    return report

def move_roster(db):
    """Команда и ключ строк состава по обмену, затем сортировка по ключу."""
    m = swap_map('zero')
    rows, moved = [], 0
    for r in range(db.by_name[ROSTER]['rows']):
        team, key = db.get(ROSTER, 'team', r), db.get(ROSTER, 'key', r)
        slot = key - team * ROSTER_SLOTS
        assert 0 <= slot < ROSTER_SLOTS, (r, team, key)
        if team in m:
            db.set(ROSTER, 'team', r, m[team])
            db.set(ROSTER, 'key', r, m[team] * ROSTER_SLOTS + slot)
            moved += 1
        rows.append((db.get(ROSTER, 'key', r), db.record(ROSTER, r)))
    rows.sort(key=lambda x: x[0])
    for r, (_, raw) in enumerate(rows):
        db.put_record(ROSTER, r, raw)
    return moved

def append_copies(db, table, rows, change):
    """Копии строк rows в конец таблицы; change(новая_строка, исходная) правит поля."""
    n = db.by_name[table]['rows']
    raws = [db.record(table, r) for r in rows]
    db.resize(table, n + len(raws))
    for i, (src, raw) in enumerate(zip(rows, raws)):
        db.put_record(table, n + i, raw)
        if 'index' in db.by_name[table]['fields']:
            db.set(table, 'index', n + i, n + i)
        change(n + i, src)
    return list(range(n, n + len(raws)))

def fill_new_teams(db):
    t = 'exhibitionteams'
    report = {}
    for row, spec in NEW_TEAMS.items():
        for f, v in (('shortname', spec['short']), ('fullname', spec['full']), ('abbrname', spec['abbr']),
                     ('artabbr', spec['abbr'])):
            db.set_string(t, f, row, v)
        for f, v in (('active', 1), ('table', 0), ('state', 0), ('league', 0), ('leaguegroup', 0),
                     ('artid', spec['art']), ('spotlight', spec['spotlight']), ('audioid', spec['audio']),
                     ('audioid2', 0), ('rivalteam', spec['rival'] + 1), ('rivalteam2', 0)):
            db.set(t, f, row, v)
        for prefix, rgb in (('primarycolor', spec['primary']), ('secondarycolor', spec['secondary'])):
            for c, v in zip('rgb', rgb):
                db.set(t, f'{prefix}_{c}', row, v)
        # тактика — как у соседа
        db.put_record('exhibitionteamstrategies', row, db.record('exhibitionteamstrategies', spec['strategy']))
        # арена: копия нейтральной арены НХЛ-размера со своим названием
        a = spec['arena']
        def arena(new, src, a=a):
            db.set_string('exhibitionarena', 'arenaname', new, a['name'])
            db.set_string('exhibitionarena', 'cityname', new, a['city'])
            db.set('exhibitionarena', 'maxattendance', new, a['capacity'])
        new_arena = append_copies(db, 'exhibitionarena', [TEMPLATE_ARENA], arena)[0]
        db.set(t, 'arenaid', row, new_arena)
        # комплекты формы — копии (у заготовки их нет) под свой номер арта
        js = 'stockteamjerseys'
        def kit(new, src, row=row, art=spec['art']):
            db.set(js, 'teamid', new, row)
            db.set(js, 'teamartid', new, art)
        j = [r for r in range(db.by_name[js]['rows']) if db.get(js, 'teamid', r) == spec['kit']]
        append_copies(db, js, j, kit)
        # цвета экипировки (шлемы, перчатки…): строки kit, перекрашенные по equip; team — номер + 1
        e = 'stockteamequipmenttable'
        def recolor(new, src, row=row, m=spec['equip']):
            db.set(e, 'team', new, row + 1)
            for z in range(1, 10):
                rgb = tuple(db.get(e, f'zone{z}_{c}', new) for c in 'rgb')
                v = m.get(rgb[0] << 16 | rgb[1] << 8 | rgb[2])
                if v is not None:
                    for c, x in zip('rgb', (v >> 16, v >> 8 & 0xFF, v & 0xFF)):
                        db.set(e, f'zone{z}_{c}', new, x)
        q = [r for r in range(db.by_name[e]['rows']) if db.get(e, 'team', r) == spec['kit'] + 1]
        append_copies(db, e, q, recolor)
        # цвета команды (запись осталась у строки — 7-битное поле не переписывалось)
        for r in range(db.by_name['stockteamcolorstable']['rows']):
            if db.get('stockteamcolorstable', 'team', r) == row:
                rgb = spec['primary'] if db.get('stockteamcolorstable', 'colorid', r) == 0 else spec['secondary']
                for c, v in zip('rgb', rgb):
                    db.set('stockteamcolorstable', f'color_{c}', r, v)
        report[spec['abbr']] = dict(arena=new_arena, jerseys=len(j), equipment=len(q))
    # сборные: аббревиатура для ключей строк (EAS/WES)
    for row, (abbr, _, _) in ALLSTAR_NAMES.items():
        db.set_string(t, 'abbrname', row, abbr)
    return report

def realign(db):
    seen = sorted(t for teams in DIVISIONS.values() for t in teams)
    assert seen == list(range(32)), seen
    for div, teams in DIVISIONS.items():
        for t in teams:
            db.set('exhibitionteams', 'league', t, 0)
            db.set('exhibitionteams', 'leaguegroup', t, 0)
            db.set('exhibitionteams', 'conferencegroup', t, CONFERENCE[div])
            db.set('exhibitionteams', 'divisiongroup', t, div)
    for t, aff in AHL_AFFILIATE.items():
        db.set('exhibitionteams', 'ahlaffiliate', t, aff)

def pair_games(rng):
    """Пары и хозяева: 4 игры в дивизионе, 3 в конференции, 2 с другой конференцией."""
    div_of = {t: d for d, teams in REAL_DIVISIONS.items() for t in teams}
    conf_of = {t: REAL_CONFERENCE[d] for t, d in div_of.items()}
    games, odd = [], defaultdict(list)
    teams = sorted(div_of)
    assert teams == list(range(32))
    for i, x in enumerate(teams):
        for y in teams[i + 1:]:
            if div_of[x] == div_of[y]:
                games += [(x, y), (y, x)] * 2
            elif conf_of[x] == conf_of[y]:
                games += [(x, y), (y, x)]
                odd[x].append(y)
                odd[y].append(x)
            else:
                games += [(x, y), (y, x)]
    # третья игра внутри конференции: ориентация по эйлерову циклу — 4 «лишних»
    # домашних из 8 у каждой команды
    adj = {t: v[:] for t, v in odd.items()}
    for t in adj:
        rng.shuffle(adj[t])
    used = set()
    for start in sorted(adj):
        stack, path = [start], []
        while stack:
            v = stack[-1]
            while adj[v] and frozenset((v, adj[v][-1])) in used:
                adj[v].pop()
            if adj[v]:
                w = adj[v].pop()
                used.add(frozenset((v, w)))
                stack.append(w)
            else:
                path.append(stack.pop())
        games += list(zip(path, path[1:]))
    per = Counter(t for g in games for t in g)
    home = Counter(h for h, a in games)
    assert all(per[t] == GAMES and home[t] == HOME for t in teams), (per, home)
    return games

def game_days(db):
    """Игровые дни регулярки 2012/13 по порядку и сколько в них было игр (без Матча звёзд)."""
    days, counts = [], Counter()
    for r in range(db.by_name['nhlschedule']['rows']):
        h, a = db.get('nhlschedule', 'home', r), db.get('nhlschedule', 'away', r)
        if h >= 30 or a >= 30:
            continue
        d = (db.get('nhlschedule', 'month', r), db.get('nhlschedule', 'day', r))
        if d not in counts:
            days.append(d)
        counts[d] += 1
    return days, counts

def schedule(games, days, counts, rng):
    total = len(games)
    scale = total / sum(counts.values())
    raw = [counts[d] * scale for d in days]
    target = [int(x) for x in raw]
    for i in sorted(range(len(days)), key=lambda i: raw[i] - target[i], reverse=True)[:total - sum(target)]:
        target[i] += 1
    pool = games[:]
    rng.shuffle(pool)
    left = Counter(t for g in pool for t in g)
    last = {}
    met = {}
    plan = []
    for di, d in enumerate(days):
        busy = set()
        cand = []
        for g in pool:
            h, a = g
            score = left[h] + left[a] + rng.random()
            for t in g:
                if last.get(t) == di - 1:
                    score -= 30
                if last.get(t) == di - 1 and last.get((t, 'prev')) == di - 2:
                    score -= 200
            if met.get(frozenset(g), -99) > di - 10:
                score -= 15
            cand.append((score, g))
        cand.sort(reverse=True)
        chosen = []
        for score, g in cand:
            if len(chosen) >= target[di]:
                break
            if g[0] in busy or g[1] in busy:
                continue
            chosen.append(g)
            busy.update(g)
        for g in chosen:
            pool.remove(g)
            plan.append((d, g))
            met[frozenset(g)] = di
            for t in g:
                left[t] -= 1
                last[(t, 'prev')] = last.get(t)
                last[t] = di
    # хвост — в любые дни, где обе команды свободны
    for g in pool[:]:
        for di, d in enumerate(days):
            if not any(dd == d and (g[0] in gg or g[1] in gg) for dd, gg in plan):
                plan.append((d, g))
                pool.remove(g)
                break
    if pool:
        raise SystemExit(f'не разложилось {len(pool)} игр')
    order = {d: i for i, d in enumerate(days)}
    plan.sort(key=lambda x: order[x[0]])
    per_day = defaultdict(list)
    for d, g in plan:
        per_day[d].extend(g)
    assert all(len(v) == len(set(v)) for v in per_day.values())
    return plan

def write_schedule(db, table, plan):
    db.resize(table, len(plan))
    for i, ((month, day), (h, a)) in enumerate(plan):
        for f, v in (('index', i), ('home', h), ('away', a), ('month', month), ('day', day), ('round', 0), ('status', 0)):
            db.set(table, f, i, v)
    return db

# Матч звёзд — отдельная строка календаря НХЛ, как в исходной базе (там «31 против 30» 27 января):
# загрузчик календаря франшизы (827B2300) считает игру с хозяевами ≥ числа команд Матчем звёзд и
# подставляет сборные (состояния 53/54). Без неё игра ставит матч с датой 0/0 и после перерыва
# теряет дату франшизы. При 32 командах номер ≥ 32 не влезает в 5 бит — home/away → 6 бит.
ALLSTAR = ((0, 26), (33, 32))
SEASON_MONTHS = [8, 9, 10, 11, 0, 1, 2, 3, 4, 5, 6, 7]

def add_allstar(db, table):
    rows = [((db.get(table, 'month', r), db.get(table, 'day', r)), (db.get(table, 'home', r), db.get(table, 'away', r)))
            for r in range(db.by_name[table]['rows'])]
    assert not any(d == ALLSTAR[0] for d, _ in rows), 'в день Матча звёзд есть игры'
    rows.append(ALLSTAR)
    rows.sort(key=lambda x: (SEASON_MONTHS.index(x[0][0]), x[0][1]))
    db.widen(table, ['home', 'away'], 6)
    db.resize(table, len(rows))
    for i, ((month, day), (h, a)) in enumerate(rows):
        for f, v in (('index', i), ('home', h), ('away', a), ('month', month), ('day', day), ('round', 0), ('status', 0)):
            db.set(table, f, i, v)

def patch_meta(text):
    for table, n in META_MAXINSERT.items():
        pat = re.compile(r'(<table name="%s"[^>]*maxinsert=")(\d+)(")' % table)
        text, k = pat.subn(lambda m: m.group(1) + str(n) + m.group(3), text)
        assert k == 1, table
    for table, fields in META_WIDEN.items():
        m = re.search(r'<table name="%s".*?</table>' % table, text, re.S)
        block = m.group(0)
        for field in fields:
            pat = re.compile(r'(<field name="%s"[^>]*?)depth="5"([^>]*?)rangehigh="30"([^>]*?rangelow="-1")' % field)
            block, k = pat.subn(lambda f: f.group(1) + 'depth="6"' + f.group(2) + 'rangehigh="62"' + f.group(3), block)
            assert k == 1, (table, field)
        text = text[:m.start()] + block + text[m.end():]
    return text

def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('db_in'); ap.add_argument('db_out'); ap.add_argument('loc_in'); ap.add_argument('loc_out')
    ap.add_argument('--loc-meta', default=None)
    ap.add_argument('--meta', nargs=2, metavar=('META_IN', 'META_OUT'), help='схема nhlng-meta.xml: вместимость таблиц франшизы')
    ap.add_argument('--seed', type=int, default=2026)
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding='utf-8')
    rng = random.Random(a.seed)
    db = Tdb(open(a.db_in, 'rb').read(), load_meta(DEFAULT_META))
    names = {r: db.get_string('exhibitionteams', 'fullname', r) for r in list(SWAP) + list(SWAP.values())}
    print('переезд:', {f'{b}→{a_}': names[b] for a_, b in SWAP.items()})
    for k, v in move_teams(db).items():
        print(f'  ссылки {k}: {v}')
    print('новые клубы:', fill_new_teams(db))
    realign(db)
    db.widen('exhibitionplayerbiotable', ['proteam', 'draftteam'], 6)
    days, counts = game_days(db)
    plan = schedule(pair_games(rng), days, counts, rng)
    for table in ('nhlschedule', 'favoriteteamschedule'):
        write_schedule(db, table, plan)
        add_allstar(db, table)
    print(f'календарь НХЛ: {len(plan)} игр в {len(days)} игровых днях')
    db.fix()
    assert not db.verify()
    open(a.db_out, 'wb').write(db.d)
    loc_meta = a.loc_meta or a.loc_in.rsplit('.', 1)[0] + '-meta.xml'
    loc = LocDb(open(a.loc_in, 'rb').read(), load_meta(loc_meta))
    strings = {}
    for n, spec in NEW_TEAMS.items():
        ab = spec['abbr']
        strings.update({f'NHLTeamName_{n}': spec['full'], f'NHLCityName_{n}': spec['short'],
                        f'NICKLINE2_{n}': spec['nick'], f'CITYLINE1_{n}': spec['short'],
                        f'NHLTeamName_Abbr3_{n}': ab,
                        f'NHLTeamName_{ab}': spec['full'], f'NHLCityName_{ab}': spec['short'],
                        f'Teamline1_{ab}': spec['short'], f'Teamline2_{ab}': spec['nick'],
                        f'NHLTeamName_ABBR3_{ab}': ab, f'X_XLA_TEAM_{ab}': ab})
    for row, (ab, city, full) in ALLSTAR_NAMES.items():
        strings.update({f'NHLTeamName_{ab}': full, f'NHLCityName_{ab}': city, f'Teamline1_{ab}': city,
                        f'Teamline2_{ab}': 'All-Stars', f'NHLTeamName_ABBR3_{ab}': ab, f'X_XLA_TEAM_{ab}': ab})
    added = 0
    for key, text in strings.items():
        if loc.put(key, text) is None:
            added += 1
    print(f'строки: {len(strings)} ключей, из них новых {added}')
    loc.db.fix()
    assert not loc.db.verify()
    open(a.loc_out, 'wb').write(loc.db.d)
    if a.meta:
        meta = patch_meta(open(a.meta[0], encoding='utf-8', newline='').read())
        open(a.meta[1], 'w', encoding='utf-8', newline='').write(meta)
        print(f'схема: {META_MAXINSERT}, поля 6 бит: {sum(map(len, META_WIDEN.values()))} -> {a.meta[1]}')
    print(f'записано: {a.db_out}, {a.loc_out}')

if __name__ == '__main__':
    main()
