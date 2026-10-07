"""НХЛ на 32 команды: две команды финской лиги (Tappara, TPS) переезжают в НХЛ.

    python nhl32.py DB_IN DB_OUT LOC_IN LOC_OUT [--seed N]

Почему так (разбор — docs/teams.md):
- Календарь НХЛ (nhlschedule) хранит номер команды в лиге 5 битами (0–31), а команды
  НХЛ — строки 0–29 базы. Строки 30/31 занимали сборные Матча звёзд (Red/Blue, в
  календаре — одна игра 31 против 30). Новые команды встают на 30 и 31, сборные — на
  их старые места 86/87 (конец финской лиги, номера остальных финских команд не
  сдвигаются).
- Строки exhibitionteams и exhibitionteamstrategies меняются местами целиком (с
  названием, цветами, artid, ареной), во всех таблицах ссылки на номера переписываются:
  где номер хранится с нуля — 30↔86, 31↔87, где «номер + 1» (0 = нет) — 31↔87, 32↔88.
- Календарь — формат НХЛ с сезона 2026/27: 84 игры (по 4 с соперниками по дивизиону,
  по 3 с остальной конференцией, по 2 с другой конференцией), 42 дома, по нынешним
  4 дивизионам; раскладывается на игровые дни календаря 2012/13. В самой игре 6
  дивизионов (пустой опасен: плей-офф 2012 года ищет победителя каждого), поэтому
  турнирная таблица делится на «поддивизионы» нынешних — 6 + 5 + 5 в конференции.
- Из календаря финской лиги убираются игры ушедших команд.
- Строки локализации по номеру (NHLTeamName_30 и т. п.) указывают на строки
  Tappara/TPS (меняются только указатели, пул строк не трогается).
"""
import argparse, random, struct, sys
from collections import Counter, defaultdict
from tdb import Tdb, DEFAULT_META
from tdb_read import load_meta
from locdb import LocDb

SWAP = {30: 86, 31: 87}            # новая команда НХЛ ← строка финской лиги
LIIGA_REL = {86 - 74, 87 - 74}     # их номера внутри финской лиги (строки 74–87)

# Поля-ссылки на команду: (таблица, поле, кодировка). 'zero' — номер строки,
# 'plus1' — номер + 1 (0 = нет команды). Проверено по известным игрокам и командам.
TEAM_FIELDS = [
    ('exhibitionrostertable', 'team', 'zero'),
    ('stockteamjerseys', 'teamid', 'zero'),
    ('stockteamequipmenttable', 'team', 'zero'),
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

WEST, EAST = 1, 2
# divisiongroup: 3 Northwest, 4 Pacific, 5 Central (Запад); 6 Southeast, 7 Atlantic,
# 8 Northeast (Восток). 6 + 5 + 5 в каждой конференции.
DIVISIONS = {
    5: [6, 7, 9, 14, 16, 24],      # CHI COL DAL MIN NSH STL
    3: [1, 4, 11, 28, 30],         # WPG CGY EDM VAN + Tappara (будущий Сиэтл)
    4: [0, 13, 25, 22, 31],        # ANA LA SJ PHX + TPS (будущий Вегас)
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
LOC_ALIASES = {  # ключ по номеру команды ← ключ по аббревиатуре
    'NHLTeamName_{n}': 'NHLTeamName_{a}', 'NHLCityName_{n}': 'NHLCityName_{a}',
    'NICKLINE2_{n}': 'Teamline2_{a}', 'CITYLINE1_{n}': 'Teamline1_{a}',
    'NHLTeamName_Abbr3_{n}': 'NHLTeamName_ABBR3_{a}',
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
    report = {}
    for table, field, enc in TEAM_FIELDS:
        m = swap_map(enc)
        n = 0
        for r in range(db.by_name[table]['rows']):
            v = db.get(table, field, r)
            if v in m:
                db.set(table, field, r, m[v])
                n += 1
        report[f'{table}.{field}'] = n
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

def prune_liiga(db):
    t = 'finnishschedule'
    keep = []
    for r in range(db.by_name[t]['rows']):
        row = {f: db.get(t, f, r) for f in db.by_name[t]['fields']}
        if row['home'] not in LIIGA_REL and row['away'] not in LIIGA_REL:
            keep.append(row)
    db.resize(t, len(keep))
    for i, row in enumerate(keep):
        row['index'] = i
        for f, v in row.items():
            db.set(t, f, i, v)
    return len(keep)

def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('db_in'); ap.add_argument('db_out'); ap.add_argument('loc_in'); ap.add_argument('loc_out')
    ap.add_argument('--loc-meta', default=None)
    ap.add_argument('--seed', type=int, default=2026)
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding='utf-8')
    rng = random.Random(a.seed)
    db = Tdb(open(a.db_in, 'rb').read(), load_meta(DEFAULT_META))
    names = {r: db.get_string('exhibitionteams', 'fullname', r) for r in list(SWAP) + list(SWAP.values())}
    print('переезд:', {f'{b}→{a_}': names[b] for a_, b in SWAP.items()})
    for k, v in move_teams(db).items():
        print(f'  ссылки {k}: {v}')
    realign(db)
    days, counts = game_days(db)
    plan = schedule(pair_games(rng), days, counts, rng)
    for table in ('nhlschedule', 'favoriteteamschedule'):
        write_schedule(db, table, plan)
    print(f'календарь НХЛ: {len(plan)} игр в {len(days)} игровых днях')
    print(f'финская лига: осталось {prune_liiga(db)} игр')
    db.fix()
    assert not db.verify()
    open(a.db_out, 'wb').write(db.d)
    loc_meta = a.loc_meta or a.loc_in.rsplit('.', 1)[0] + '-meta.xml'
    loc = LocDb(open(a.loc_in, 'rb').read(), load_meta(loc_meta))
    for n, b in SWAP.items():
        abbr = db.get_string('exhibitionteams', 'abbrname', n)
        for dst, src in LOC_ALIASES.items():
            loc.alias(dst.format(n=n), src.format(a=abbr))
    loc.db.fix()
    open(a.loc_out, 'wb').write(loc.db.d)
    print(f'записано: {a.db_out}, {a.loc_out}')

if __name__ == '__main__':
    main()
