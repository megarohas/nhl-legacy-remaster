"""Клубы АХЛ 2026/27 из HockeyTech (lscluster.hockeytech.com, ключ — публичный, с сайта лиги;
docs/research-data-sources.md §4) и API НХЛ — для актуализации составов АХЛ NHL Legacy (решение пользователя 10.10,
«актуализируй составы АХЛ и свободных агентов»). Все ответы — в кэш game/work/roster-cache/ (повторно сеть не
трогает), только GET, пауза ≥ 1 с на хост (common.Http), разные хосты — параллельно.

    python -m roster.ahl_ht teams          # этап 1: сезоны, клубы 2026/27, составы 32 клубов, логотипы клубов
    python -m roster.ahl_ht ids            # этап 2: prospects 32 клубов НХЛ, все активные (search.d3) → ID НХЛ
    python -m roster.ahl_ht players        # этап 3: landing игроков с ID НХЛ, seasonstats остальных, портреты
    python -m roster.ahl_ht summary        # что в кэше: клубы, игроки, у скольких ID НХЛ (без сети)
    … --offline                            # только кэш

Кэш: ahl/ht/seasons.json, ahl/ht/teams-<season>.json, ahl/ht/roster/<season>-<team>.json,
ahl/ht/logos/<team>.<ext> (+ logos.json: team → URL), ahl/ht/player/<id>-seasonstats.json, nhl/prospects/<TEAM>.json,
nhl/search/active.json, nhl/landing/<id>.json (как у fetch.py), photos/ahl/<id>.jpg (leaguestat 240×240),
photos/20262027/<id>.png (портреты НХЛ, как у photos).
"""
import argparse
import json
import os
import sys
import threading
import urllib.parse

if __package__ in (None, ''):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    __package__ = 'roster'

from .common import Http, Paths, read_json, set_game, write_json  # noqa: E402

HT = 'https://lscluster.hockeytech.com/feed/'
KEY, CLIENT = '50c2cd9b5e18e390', 'ahl'
SEASON_ID = 94                      # регулярный чемпионат 2026/27 (docs/research-data-sources.md §4)
NHL = 'https://api-web.nhle.com/v1'
SEARCH_ALL = 'https://search.d3.nhle.com/api/v1/search/player?culture=en-us&limit=10000&q=*&active=true'
LEAGUESTAT_PHOTO = 'https://assets.leaguestat.com/ahl/240x240/{}.jpg'


def ht_url(view, **kw):
    q = dict(feed='modulekit', view=view, key=KEY, client_code=CLIENT, fmt='json', lang='en', **kw)
    return HT + '?' + urllib.parse.urlencode(q)


def sitekit(d, name):
    """Список из ответа modulekit: {"SiteKit": {"<Name>": [...]}}."""
    kit = (d or {}).get('SiteKit') or {}
    for k, v in kit.items():
        if k.lower() == name.lower():
            return v or []
    return []


def teams(h):
    seasons = sitekit(h.json(ht_url('seasons'), 'ahl/ht/seasons.json'), 'Seasons')
    clubs = sitekit(h.json(ht_url('teamsbyseason', season_id=SEASON_ID), f'ahl/ht/teams-{SEASON_ID}.json'),
                    'Teamsbyseason')
    return seasons, clubs


def rosters(h, clubs):
    out = {}
    for c in clubs:
        tid = c['id']
        out[tid] = sitekit(h.json(ht_url('roster', team_id=tid, season_id=SEASON_ID),
                                  f'ahl/ht/roster/{SEASON_ID}-{tid}.json'), 'Roster')
    return out


def logos(h, clubs):
    urls = {}
    for c in clubs:
        url = c.get('team_logo_url')
        if not url:
            continue
        ext = os.path.splitext(urllib.parse.urlsplit(url).path)[1] or '.png'
        h.get(url, f"ahl/ht/logos/{c['id']}{ext}")
        urls[c['id']] = url
    write_json(os.path.join(h.cache, 'ahl', 'ht', 'logos.json'), urls)
    return urls


def roster_players(roster):
    """Записи игроков состава (без тренеров): у HockeyTech в roster бывают строки-разделители."""
    out = []
    for p in roster:
        if not isinstance(p, dict) or not p.get('player_id') and not p.get('id'):
            continue
        if str(p.get('position', '')).lower() in ('coach', 'head coach', 'assistant coach', 'trainer'):
            continue
        out.append(p)
    return out


def nhl_ids(h):
    """Этап 2: prospects 32 клубов НХЛ и все активные игроки (search.d3, один запрос) → кэш."""
    from .common import SLOT_TEAM
    pros = {}
    for slot in sorted(SLOT_TEAM):
        abbr = SLOT_TEAM[slot]
        d = h.json(f'{NHL}/prospects/{abbr}', f'nhl/prospects/{abbr}.json') or {}
        pros[abbr] = [p for g in ('forwards', 'defensemen', 'goalies') for p in d.get(g) or []]
    active = h.json(SEARCH_ALL, 'nhl/search/active.json') or []
    return pros, active


def _nm(p, key):
    v = p.get(key)
    return v.get('default') if isinstance(v, dict) else v


def match_ids(rosters_by_team, pros, active):
    """Игрок АХЛ → ID НХЛ: по имени и дате рождения сначала в prospects (там и клуб НХЛ — права), затем среди
    активных (search.d3). → ({HT player_id: (nhl_id, клуб НХЛ | None)}, {клуб АХЛ: Counter клубов НХЛ})."""
    import collections
    from .common import norm
    idx = collections.defaultdict(list)
    for abbr, lst in pros.items():
        for p in lst:
            key = (norm(f"{_nm(p, 'firstName')}{_nm(p, 'lastName')}"), p.get('birthDate'))
            idx[key].append((p.get('id'), abbr))
    act = collections.defaultdict(list)
    for p in active:
        key = (norm(p.get('name', '')), p.get('birthDate'))
        act[key].append((int(p.get('playerId')), p.get('teamAbbrev') or None))
    out, orgs = {}, collections.defaultdict(collections.Counter)
    for tid, roster in rosters_by_team.items():
        for p in roster_players(roster):
            key = (norm(f"{p.get('first_name')}{p.get('last_name')}"), p.get('rawbirthdate') or p.get('birthdate'))
            hit = idx.get(key) or act.get(key)
            if hit and len({x[0] for x in hit}) == 1:
                out[p['player_id']] = hit[0]
                if hit[0][1] and idx.get(key):
                    orgs[tid][hit[0][1]] += 1
    return out, orgs


def run_lanes(lanes, log=print):
    """Задачи по хостам параллельно: lanes = {хост: [функция без аргументов]}; внутри хоста — по очереди (пауза
    ≥ 1 с — у common.Http на каждый хост)."""
    errors = []

    def lane(name, jobs):
        for i, job in enumerate(jobs, 1):
            try:
                job()
            except Exception as err:          # noqa: BLE001 — собрать и показать все
                errors.append(f'{name}: {err}')
            if i % 100 == 0:
                log(f'   {name}: {i}/{len(jobs)}')
    threads = [threading.Thread(target=lane, args=(n, j)) for n, j in lanes.items() if j]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return errors


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('stage', choices=['teams', 'ids', 'players', 'summary'])
    ap.add_argument('--offline', action='store_true')
    ap.add_argument('--pause', type=float, default=1.0)
    a = ap.parse_args()
    if a.pause < 1:
        sys.exit('пауза — не меньше 1 с')
    set_game('legacy')
    paths = Paths(None, None)
    h = Http(paths.cache, pause=a.pause, offline=a.offline or a.stage == 'summary')
    if a.stage in ('teams', 'summary'):
        seasons, clubs = teams(h)
        cur = next((s for s in seasons if str(s.get('season_id')) == str(SEASON_ID)), None)
        print(f'сезон {SEASON_ID}: {cur.get("season_name") if cur else "?"}; клубов {len(clubs)}')
        rs = rosters(h, clubs)
        n = {tid: len(roster_players(r)) for tid, r in rs.items()}
        print(f'составы: игроков {sum(n.values())}, по клубам {min(n.values())}–{max(n.values())}')
        if a.stage == 'teams':
            urls = logos(h, clubs)
            print(f'логотипы: {len(urls)}')
        print(f'запросов к сети: {h.requests}')
    if a.stage in ('ids', 'summary'):
        seasons, clubs = teams(h)
        rs = rosters(h, clubs)
        pros, active = nhl_ids(h)
        ids, orgs = match_ids(rs, pros, active)
        n = sum(len(roster_players(r)) for r in rs.values())
        print(f'prospects: {sum(len(v) for v in pros.values())} у 32 клубов; активных (search.d3): {len(active)}')
        print(f'игроков АХЛ {n}, с ID НХЛ {len(ids)} ({100 * len(ids) // max(n, 1)} %), без — {n - len(ids)}')
        name = {c['id']: c['name'] for c in clubs}
        for tid, c in sorted(orgs.items(), key=lambda kv: name[kv[0]]):
            top = c.most_common(2)
            print(f'   {name[tid]}: права у ' + ', '.join(f'{k} {v}' for k, v in top))
        print(f'запросов к сети: {h.requests}')


if __name__ == '__main__':
    main()
