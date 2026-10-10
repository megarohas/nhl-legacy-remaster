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


class RateHttp(Http):
    """common.Http с темпом по началам запросов: к одному хосту — не чаще раза в `pause` секунд (≥ 1), при этом
    несколько запросов могут ждать ответа одновременно (потоки run_lanes). Кэш, повторы и 404 — как у Http."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self._locks, self._next, self._guard = {}, {}, threading.Lock()

    def slot(self, host):
        import time
        with self._guard:
            lock = self._locks.setdefault(host, threading.Lock())
        with lock:
            now = time.time()
            at = max(now, self._next.get(host, 0))
            self._next[host] = at + self.pause
        if at > now:
            time.sleep(at - now)

    def get(self, url, rel, refresh=None):
        refresh = self.refresh if refresh is None else refresh
        fn = self.path(rel)
        if not refresh and (os.path.exists(fn) or os.path.exists(fn + '.404')) or self.offline:
            return super().get(url, rel, refresh)
        host = urllib.parse.urlsplit(url).hostname
        self.slot(host)
        self.last[host] = 0                  # темп уже выдержан slot(): своя пауза Http не нужна
        return super().get(url, rel, refresh)

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


SEARCH = 'https://search.d3.nhle.com/api/v1/search/player?culture=en-us&limit=20&q={}'
PNG = b'\x89PNG\r\n\x1a\n'


def _key(p):
    from .common import norm
    return norm(f"{p.get('first_name')}{p.get('last_name')}")


def _is_g(pos):
    return str(pos).upper().startswith('G')


def search_rel(name):
    from .common import norm
    return f'nhl/search/q/{norm(name)}.json'


def landing_rel(pid):
    return f'nhl/landing/{pid}.json'


def landing(h, pid):
    return h.json(f'{NHL}/player/{pid}/landing', landing_rel(pid))


def landing_birth(h, pid):
    if not h.cached(landing_rel(pid)):
        return None
    d = landing(h, pid)
    return (d or {}).get('birthDate')


def headshot(h, pid, url, log=print):
    """Портрет НХЛ в photos/20262027/<id>.png, как tools/photos.py: 302 — фото нет (.default), только PNG."""
    import time
    import urllib.error
    import urllib.request
    fn = os.path.join(h.cache, 'photos', '20262027', f'{pid}.png')
    if os.path.exists(fn) or os.path.exists(fn + '.default') or os.path.exists(fn + '.404'):
        return
    if h.offline:
        return

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None
    opener = urllib.request.build_opener(NoRedirect)
    os.makedirs(os.path.dirname(fn), exist_ok=True)
    host = urllib.parse.urlsplit(url).hostname
    for attempt in range(6):
        if hasattr(h, 'slot'):
            h.slot(host)
        else:
            wait = h.pause - (time.time() - h.last.get(host, 0))
            if wait > 0:
                time.sleep(wait)
            h.last[host] = time.time()
        try:
            from .common import UA
            with opener.open(urllib.request.Request(url, headers={'User-Agent': UA}), timeout=60) as r:
                body = r.read()
            h.requests += 1
            if body[:8] != PNG:
                raise ValueError('не PNG')
            with open(fn + '.part', 'wb') as f:
                f.write(body)
            os.replace(fn + '.part', fn)
            return
        except urllib.error.HTTPError as err:
            h.requests += 1
            if err.code in (301, 302, 303, 307, 308):
                open(fn + '.default', 'w').write(err.headers.get('Location', ''))
                return
            if err.code == 404:
                open(fn + '.404', 'w').close()
                return
            if err.code not in (403, 429, 500, 502, 503, 504) or attempt == 5:
                log(f'  портрет {pid}: HTTP {err.code}')
                return
            time.sleep(min(60, 5 * 2 ** attempt))
        except Exception as err:          # noqa: BLE001
            if attempt == 5:
                log(f'  портрет {pid}: {err}')
                return
            time.sleep(min(30, 3 * 2 ** attempt))


def seasonstats_rel(htid):
    return f'ahl/ht/player/{htid}-seasonstats.json'


def club_season_ids(h, players, ids, club_name):
    """Игроки без ID НХЛ → ID по карточке landing из кэша (кандидаты поиска, свободные агенты и прочие скачанные): та
    же фамилия, то же имя или его форма (build.same_first) либо та же дата рождения (Mike — Michael Sgarbossa),
    вратарь/полевой как в HockeyTech и в сезоне 2026/27 — АХЛ за этот же клуб. Дата рождения при этом может не
    совпасть: в HockeyTech она бывает неверной
    (у Basha «2011-08-05» при 2005-11-08 в НХЛ, у Kerins день, месяц и год переставлены). Берётся только единственный
    кандидат, чей ID ещё ни у кого. → {HT player_id: nhl_id}"""
    import collections
    from .build import same_first
    from .common import SEASON, norm
    d = os.path.join(h.cache, *landing_rel(0).split('/')[:-1])
    by_last = collections.defaultdict(list)
    for f in sorted(os.listdir(d)) if os.path.isdir(d) else []:
        if not f.endswith('.json'):
            continue
        land = read_json(os.path.join(d, f))
        if isinstance(land, dict) and land.get('playerId'):
            by_last[norm(_nm(land, 'lastName') or '')].append(land)
    taken = {v[0] for v in ids.values()}
    out = {}
    for pid, p in players.items():
        if pid in ids:
            continue
        club = norm(club_name.get(p['_team']) or '')
        hits = set()
        for land in by_last.get(norm(p.get('last_name') or ''), []):
            if not same_first(_nm(land, 'firstName') or '', p.get('first_name') or '') and \
                    land.get('birthDate') != p.get('rawbirthdate'):         # Mike / Michael Sgarbossa — та же дата
                continue
            if _is_g(land.get('position')) != _is_g(p.get('position')):
                continue
            if any(s.get('season') == SEASON and s.get('leagueAbbrev') == 'AHL'
                   and norm(_nm(s, 'teamName') or '') == club for s in land.get('seasonTotals') or []):
                hits.add(int(land['playerId']))
        hits -= taken
        if len(hits) == 1:
            out[pid] = hits.pop()
            taken.add(out[pid])
    return out


def players_stage(h, log=print):
    """Этап 3. → сводка {HT player_id: {...}} в game/work/legacy-data/ahl-2026/ids.json."""
    import collections
    from . import fa
    from .common import norm
    seasons, clubs = teams(h)
    rs = rosters(h, clubs)
    pros, active = nhl_ids(h)
    ids0, _ = match_ids(rs, pros, active)
    players = {p['player_id']: dict(p, _team=tid) for tid, r in rs.items() for p in roster_players(r)}
    need_search = [p for pid, p in players.items() if pid not in ids0]
    # волна 1: поиск по имени, landing известных, bios и статьи сезонов для свободных агентов
    lanes = {
        'search.d3': [(lambda p=p: h.json(SEARCH.format(urllib.parse.quote(f"{p['first_name']} {p['last_name']}")),
                                          search_rel(f"{p['first_name']} {p['last_name']}"))) for p in need_search],
        'api-web': [(lambda i=i: landing(h, i)) for i in sorted({v[0] for v in ids0.values()})],
        'stats-rest': [(lambda s=s, k=k: fa._bios(h, k, s)) for s in fa.FA_SEASONS for k in ('skater', 'goalie')],
        'wikipedia': [(lambda t=t: h.text(fa.WIKI.format(urllib.parse.quote(f'{t}_NHL_season')), fa._season_rel(t)))
                      for t in fa.SEASON_ARTICLES],
    }
    log(f'волна 1: поиск {len(need_search)}, landing {len(lanes["api-web"])}, bios 4, статьи сезонов 2')
    errs = run_lanes(lanes, log)
    # сверка известных: дата рождения landing = HockeyTech
    ids = {}
    for pid, (nid, org) in ids0.items():
        if landing_birth(h, nid) == players[pid].get('rawbirthdate'):
            ids[pid] = (nid, org)
    # кандидаты поиска: то же имя, то же амплуа (вратарь/полевой)
    cand = collections.defaultdict(list)
    for p in need_search + [players[pid] for pid in ids0 if pid not in ids]:
        name = f"{p['first_name']} {p['last_name']}"
        rel = search_rel(name)
        if not h.cached(rel):
            continue
        res = h.json(SEARCH.format(urllib.parse.quote(name)), rel) or []
        for r in res:
            if norm(r.get('name', '')) == norm(name) and _is_g(r.get('positionCode')) == _is_g(p.get('position')):
                cand[p['player_id']].append(int(r['playerId']))
    fa_cand = fa.candidates(h, set())
    write_json(h.path('nhl/fa/candidates.json'), {str(k): v for k, v in sorted(fa_cand.items())})
    todo = sorted({i for v in cand.values() for i in v} | set(fa_cand))
    log(f'волна 2: landing кандидатов поиска {len({i for v in cand.values() for i in v})}, '
        f'свободных агентов (кандидаты bios) {len(fa_cand)}')
    errs += run_lanes({'api-web': [(lambda i=i: landing(h, i)) for i in todo]}, log)
    for pid, lst in cand.items():
        ok = [i for i in dict.fromkeys(lst) if landing_birth(h, i) == players[pid].get('rawbirthdate')]
        if len(ok) == 1:
            ids[pid] = (ok[0], None)
    by_club = club_season_ids(h, players, ids, {c['id']: c['name'] for c in clubs})
    for pid, nid in by_club.items():
        ids[pid] = (nid, None)
    if by_club:
        log(f'по клубу 2026/27 (дата рождения в HockeyTech другая): {len(by_club)}')
    no_id = [pid for pid in players if pid not in ids]
    fa_ok = [i for i in sorted(fa_cand) if fa.check_api(landing(h, i) if h.cached(landing_rel(i)) else None,
                                                     fa_cand[i]['gp']) is None]
    shots = [(nid, (landing(h, nid) or {}).get('headshot')) for nid, _ in ids.values()] + \
        [(i, (landing(h, i) or {}).get('headshot')) for i in fa_ok]
    shots = [(i, u) for i, u in dict(shots).items() if u]
    log(f'волна 3: seasonstats и фото leaguestat {len(no_id)}, портреты НХЛ {len(shots)}, '
        f'статьи Wikipedia свободных агентов {len(fa_ok)}')
    lanes = {
        'hockeytech': [(lambda i=i: h.json(ht_url('player', category='seasonstats', player_id=i), seasonstats_rel(i)))
                       for i in no_id],
        'leaguestat': [(lambda i=i: h.get(LEAGUESTAT_PHOTO.format(i), f'photos/ahl/{i}.jpg')) for i in no_id],
        'nhle-assets': [(lambda i=i, u=u: headshot(h, i, u, log)) for i, u in shots],
        'wikipedia': [(lambda i=i: fa.wiki_player(h, f"{landing(h, i)['firstName']['default']} "
                                                     f"{landing(h, i)['lastName']['default']}")) for i in fa_ok],
    }
    errs += run_lanes(lanes, log)
    # волна 4: у кого портрета сезона нет (302 — заглушка), — «последний» портрет НХЛ (photos_other.NHL_LATEST)
    from . import photos_other as po
    latest = [i for i, _ in shots if not os.path.exists(os.path.join(h.cache, 'photos', '20262027', f'{i}.png'))]
    get = po.Getter(pause=h.pause, offline=h.offline)
    log(f'волна 4: портреты НХЛ latest {len(latest)}')
    for i in latest:
        get.get(po.NHL_LATEST.format(i), os.path.join(h.cache, 'photos', 'nhl-latest', f'{i}.png'))
    h.requests += get.requests
    out = {pid: {'ht': pid, 'team': p['_team'], 'name': f"{p['first_name']} {p['last_name']}",
                 'birth': p.get('rawbirthdate'), 'status': p.get('status'), 'nhl_id': ids.get(pid, (None,))[0],
                 'nhl_org': ids.get(pid, (None, None))[1]} for pid, p in players.items()}
    for pid, nid in by_club.items():
        land = landing(h, nid) or {}
        out[pid]['by_club'] = {'nhl_name': f"{_nm(land, 'firstName')} {_nm(land, 'lastName')}",
                               'nhl_birth': land.get('birthDate')}
    dst = os.path.join(os.path.dirname(h.cache), 'legacy-data', 'ahl-2026', 'ids.json')   # game/work/legacy-data/…
    write_json(dst, {'players': out, 'fa_candidates': len(fa_cand), 'fa_api_ok': fa_ok, 'errors': errs})
    log(f'игроков АХЛ {len(players)}: с ID НХЛ {len(ids)}, без {len(no_id)}; свободных агентов после проверки '
        f'карточки {len(fa_ok)} из {len(fa_cand)}; ошибок {len(errs)} → {dst}')
    for e in errs[:10]:
        log('   ' + e)
    return out


def run_lanes(lanes, log=print, workers=8):
    """Задачи по хостам параллельно: lanes = {хост: [функция без аргументов]}; на хост — до `workers` потоков, темп
    (не чаще раза в секунду к хосту) держит RateHttp.slot."""
    import queue
    errors, done = [], {}
    lock = threading.Lock()

    def worker(name, q, total):
        while True:
            try:
                job = q.get_nowait()
            except queue.Empty:
                return
            try:
                job()
            except Exception as err:          # noqa: BLE001 — собрать и показать все
                with lock:
                    errors.append(f'{name}: {err}')
            with lock:
                done[name] = done.get(name, 0) + 1
                if done[name] % 100 == 0:
                    log(f'   {name}: {done[name]}/{total}')
    threads = []
    for name, jobs in lanes.items():
        if not jobs:
            continue
        q = queue.Queue()
        for j in jobs:
            q.put(j)
        for _ in range(min(workers, len(jobs))):
            threads.append(threading.Thread(target=worker, args=(name, q, len(jobs))))
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
    h = RateHttp(paths.cache, pause=a.pause, offline=a.offline or a.stage == 'summary')
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
    if a.stage == 'players':
        players_stage(h)
        print(f'запросов к сети: {h.requests}')


if __name__ == '__main__':
    main()
