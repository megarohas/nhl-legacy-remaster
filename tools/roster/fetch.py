"""Этап fetch: сырые ответы источников → кэш game/work/roster-cache/ (повторно сеть не трогает).

Источники (только GET, пауза ≥ 1 с на хост, повтор на 429/5xx):
- api-web.nhle.com: `/v1/roster/{TEAM}/current` (32 клуба), `/v1/player/{id}/landing` по
  каждому игроку составов (биография, драфт, статистика по сезонам);
- search.d3.nhle.com: все активные игроки одним запросом — найти тех, кого состав не
  показывает (травмированные), см. nhl_extras;
- api.nhle.com/stats/rest: `{skater,goalie}/bios` за 2025/26 и 2026/27 — гражданство
  (`nationalityCode`) и дебютный сезон;
- ea.com/games/nhl/ratings?page=1…6 — топ-300 NHL 27 с 40 атрибутами и ID EA;
- nhlratings.net: страницы 32 клубов, игроков с них и 13 списков вратарских атрибутов
  (сборщик — по образцу tools/providers/ea_ratings.py из puckpeak-nhl-legacy-rosters, MIT);
- en.wikipedia.org: «List of current NHL captains and alternate captains» (wikitext).
"""
import re
import time
import urllib.parse

from .common import Http, SEASON, SLOT_TEAM, TEAM_SLOT, write_json

NHL = 'https://api-web.nhle.com/v1'
STATS = 'https://api.nhle.com/stats/rest/en'
SEARCH_ALL = 'https://search.d3.nhle.com/api/v1/search/player?culture=en-us&limit=10000&q=*&active=true'
EXTRA_GP = 40
EA = 'https://www.ea.com/games/nhl/ratings'
NR = 'https://www.nhlratings.net/'
WIKI_CAPTAINS = ('https://en.wikipedia.org/w/index.php?title=List_of_current_NHL_captains_and_alternate_captains'
                 '&action=raw')
NR_TEAMS = {'ANA': 'anaheim-ducks', 'BOS': 'boston-bruins', 'BUF': 'buffalo-sabres', 'CGY': 'calgary-flames',
            'CAR': 'carolina-hurricanes', 'CHI': 'chicago-blackhawks', 'COL': 'colorado-avalanche',
            'CBJ': 'columbus-blue-jackets', 'DAL': 'dallas-stars', 'DET': 'detroit-red-wings',
            'EDM': 'edmonton-oilers', 'FLA': 'florida-panthers', 'LAK': 'los-angeles-kings',
            'MIN': 'minnesota-wild', 'MTL': 'montreal-canadiens', 'NSH': 'nashville-predators',
            'NJD': 'new-jersey-devils', 'NYI': 'new-york-islanders', 'NYR': 'new-york-rangers',
            'OTT': 'ottawa-senators', 'PHI': 'philadelphia-flyers', 'PIT': 'pittsburgh-penguins',
            'SJS': 'san-jose-sharks', 'SEA': 'seattle-kraken', 'STL': 'st-louis-blues',
            'TBL': 'tampa-bay-lightning', 'TOR': 'toronto-maple-leafs', 'UTA': 'utah-mammoth',
            'VAN': 'vancouver-canucks', 'VGK': 'vegas-golden-knights', 'WSH': 'washington-capitals',
            'WPG': 'winnipeg-jets'}
NR_GOALIE_LISTS = ['angles', 'breakaway', 'five-hole', 'glove-side-high', 'glove-side-low', 'stick-side-high',
                   'stick-side-low', 'poke-check', 'rebound-control', 'shot-recover', 'vision',
                   'puck-playing-frequency', 'aggression']
NR_NOT_PLAYERS = ('teams/', 'countries/', 'lists/', 'about', 'contact', 'privacy-policy', 'terms', 'nhl-27-',
                  'wp-content', 'favicon', 'category', 'tag/', 'author', 'feed', 'page/')
NR_LINK = re.compile(r'href="https://www\.nhlratings\.net/([a-z0-9\-]+)/?" title="([^"]+)"')


def teams():
    return [SLOT_TEAM[s] for s in sorted(SLOT_TEAM)]


def nhl_rosters(h, log):
    out = {}
    for abbr in teams():
        out[abbr] = h.json(f'{NHL}/roster/{abbr}/current', f'nhl/roster/{abbr}.json')
    n = sum(len(d.get(g) or []) for d in out.values() for g in ('forwards', 'defensemen', 'goalies'))
    log(f'NHL: составы 32 клубов, {n} игроков')
    return out


def roster_ids(rosters):
    ids = []
    for abbr, d in rosters.items():
        for g in ('forwards', 'defensemen', 'goalies'):
            ids += [p['id'] for p in d.get(g) or []]
    return sorted(set(ids))


def nhl_landing(h, ids, log):
    t0, done = time.time(), 0
    for k, pid in enumerate(ids):
        if not h.cached(f'nhl/landing/{pid}.json'):
            done += 1
        h.json(f'{NHL}/player/{pid}/landing', f'nhl/landing/{pid}.json')
        if (k + 1) % 50 == 0:
            log(f'NHL: карточки {k + 1}/{len(ids)} ({time.time() - t0:.0f} с)')
    log(f'NHL: карточек {len(ids)}, скачано сейчас {done}')


def nhl_extras(h, rosters, log):
    """Игроки, которых `/roster/current` не показывает (травмированные): в поиске
    search.d3 (все активные одним запросом) у них клуб НХЛ, а в составе их нет. Берём тех, кто
    сыграл в прошлом сезоне не меньше 40 игр в НХЛ, или кого EA в топ-300 числит за этим клубом;
    их список — nhl/extras.json, карточки — как у всех."""
    from . import sources
    from .common import norm, read_json
    found = h.json(SEARCH_ALL, 'nhl/search-active.json') or []
    on = set(roster_ids(rosters))
    gp = {}
    for kind in ('skater', 'goalie'):
        d = read_json(h.path(f'nhl/stats/{kind}-bios-{SEASON - 10001}.json')) or {}
        for r in d.get('data') or []:
            gp[r['playerId']] = r.get('gamesPlayed') or 0
    ea = {(norm(q['first'] + q['last']), q['team']) for q in sources.ea_players(h.cache)}
    ids = []
    for x in found:
        pid, team = int(x['playerId']), x.get('teamAbbrev')
        if team in TEAM_SLOT and pid not in on and (gp.get(pid, 0) >= EXTRA_GP or (norm(x.get('name')), team) in ea):
            ids.append(pid)
    write_json(h.path('nhl/extras.json'), sorted(ids))
    for pid in sorted(ids):
        h.json(f'{NHL}/player/{pid}/landing', f'nhl/landing/{pid}.json')
    log(f'NHL: вне /roster/current, но с клубом НХЛ (травмы): {len(ids)}')


def nhl_bios(h, log):
    for kind in ('skater', 'goalie'):
        for season in (SEASON - 10001, SEASON):
            exp = urllib.parse.quote(f'gameTypeId=2 and seasonId={season}')
            url = f'{STATS}/{kind}/bios?isAggregate=false&isGame=false&start=0&limit=-1&cayenneExp={exp}'
            d = h.json(url, f'nhl/stats/{kind}-bios-{season}.json')
            log(f'NHL stats: {kind}/bios {season}: {len((d or {}).get("data") or [])} строк')


def ea_ratings(h, log):
    for page in range(1, 7):
        h.text(f'{EA}?page={page}', f'ea/ratings-page{page}.html')
    log('EA: 6 страниц топ-300 NHL 27')


def nhlratings(h, log):
    slugs = {}
    for abbr in teams():
        body = h.text(f'{NR}teams/{NR_TEAMS[abbr]}', f'nhlratings/teams__{NR_TEAMS[abbr]}.html') or ''
        for slug, name in NR_LINK.findall(body):
            if not slug.startswith(NR_NOT_PLAYERS):
                slugs.setdefault(slug, name)
    for lst in NR_GOALIE_LISTS:
        h.text(f'{NR}lists/{lst}', f'nhlratings/lists__{lst}.html')
    log(f'nhlratings.net: {len(slugs)} игроков на страницах клубов')
    write_json(h.path('nhlratings/_slugs.json'), slugs)
    t0 = time.time()
    for k, slug in enumerate(sorted(slugs)):
        try:
            h.text(f'{NR}{slug}', f'nhlratings/players/{slug}.html')
        except Exception as err:          # страница не открылась — игрок останется без рейтинга
            log(f'  nhlratings: {slug}: {err}')
        if (k + 1) % 100 == 0:
            log(f'nhlratings.net: {k + 1}/{len(slugs)} ({time.time() - t0:.0f} с)')


def wiki(h, log):
    t = h.text(WIKI_CAPTAINS, 'wiki/captains.wikitext')
    log(f'Wikipedia: капитаны, {len(t or "")} символов')


PARTS = ['nhl', 'ea', 'nhlratings', 'wiki']


def run(paths, parts=None, pause=1.0, refresh=False, log=print):
    parts = parts or PARTS
    h = Http(paths.cache, pause=pause, refresh=refresh, log=log)
    if 'nhl' in parts:
        rosters = nhl_rosters(h, log)
        nhl_landing(h, roster_ids(rosters), log)
        nhl_bios(h, log)
    if 'ea' in parts:
        ea_ratings(h, log)
    if 'nhl' in parts:
        nhl_extras(h, rosters, log)
    if 'wiki' in parts:
        wiki(h, log)
    if 'nhlratings' in parts:
        nhlratings(h, log)
    write_json(h.path(f'_fetched-{"-".join(parts)}.json'),
               {'date': time.strftime('%Y-%m-%d %H:%M:%S'), 'parts': parts, 'requests': h.requests})
    log(f'fetch: готово, запросов в сеть {h.requests}')
    assert len(TEAM_SLOT) == 32
