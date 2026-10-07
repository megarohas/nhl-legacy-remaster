"""Этап build: кэш источников → нормализованный game/work/roster/players.json.

Скелет — составы 32 клубов НХЛ (`/v1/roster/{TEAM}/current`) и карточки игроков
(`/v1/player/{id}/landing`): имя, амплуа, хват, номер, рост/вес, дата и место рождения,
драфт, игры в НХЛ по сезонам. Гражданство — `nationalityCode` из stats REST (у кого нет —
страна рождения). Рейтинги NHL 27: ea.com (топ-300, все атрибуты и ID EA) → nhlratings.net
(OVR, у части атрибуты и стиль); сшивка EA — по имени и клубу (даты рождения у EA нет),
nhlratings.net — по фамилии и дате рождения. Капитаны — из Wikipedia.
Места под следующие этапы — поля `photo`, `contract` (null), `ea.avatar`.
"""
import time
from collections import defaultdict
from difflib import SequenceMatcher

from . import sources
from .common import SEASON, SEASON_YEAR, TEAM_SLOT, norm, write_json

POS = {'C': 'C', 'L': 'L', 'R': 'R', 'D': 'D', 'G': 'G'}


def _season_gp(land):
    """{сезон: игр} в регулярке НХЛ и сумма НХЛ + АХЛ (профессиональные игры)."""
    nhl, pro = defaultdict(int), 0
    for s in land.get('seasonTotals') or []:
        if s.get('gameTypeId') != 2:
            continue
        gp = s.get('gamesPlayed') or 0
        if s.get('leagueAbbrev') == 'NHL':
            nhl[s['season']] += gp
            pro += gp
        elif s.get('leagueAbbrev') == 'AHL':
            pro += gp
    return dict(nhl), pro


def is_rookie(birth, gp_by_season):
    """Новичок НХЛ: до 26 лет на 15 сентября, ни в одном прошлом сезоне больше 25 игр и не два
    сезона по 6 и больше (правило НХЛ)."""
    y, m, d = birth
    age = SEASON_YEAR - y - ((m, d) > (9, 15))
    prior = [n for s, n in gp_by_season.items() if s < SEASON]
    return age < 26 and max(prior, default=0) <= 25 and sum(n >= 6 for n in prior) < 2


def base_record(abbr, e, land, bio):
    y, m, d = (int(x) for x in e['birthDate'].split('-'))
    gp, pro = _season_gp(land)
    career = ((land.get('careerTotals') or {}).get('regularSeason') or {}).get('gamesPlayed')
    dd = land.get('draftDetails')
    nat = (bio or {}).get('nationalityCode') or e.get('birthCountry')
    return {
        'nhl_id': e['id'], 'team': abbr, 'slot': TEAM_SLOT[abbr],
        'first': e['firstName']['default'].strip(), 'last': e['lastName']['default'].strip(),
        'pos': POS[e['positionCode']], 'shoots': e.get('shootsCatches') or land.get('shootsCatches'),
        'num': e.get('sweaterNumber') or land.get('sweaterNumber'),
        'birth': [y, m, d],
        'birth_city': (e.get('birthCity') or {}).get('default'),
        'birth_state': (e.get('birthStateProvince') or land.get('birthStateProvince') or {}).get('default'),
        'birth_country': e.get('birthCountry'), 'nationality': nat,
        'height_in': e.get('heightInInches'), 'weight_lb': e.get('weightInPounds'),
        'draft': ({'year': dd.get('year'), 'team': dd.get('teamAbbrev'), 'round': dd.get('round'),
                   'pick_in_round': dd.get('pickInRound'), 'overall': dd.get('overallPick')} if dd else None),
        'nhl_gp': {'career': career if career is not None else sum(gp.values()),
                   'by_season': {str(k): v for k, v in sorted(gp.items())},
                   'debut': min((s for s, n in gp.items() if n), default=None)},
        'pro_gp': pro,
        'rookie': is_rookie((y, m, d), gp),
        'landing': bool(land),
        'photo': e.get('headshot'),        # следующий этап: портреты
        'contract': None,                  # следующий этап: контракты (CapWages и т. п.)
        'letter': None, 'ea': None, 'nhlratings': None, 'rating': None,
    }


def _sim(a, b):
    return SequenceMatcher(None, a, b).ratio()


def same_first(a, b):
    """Одно имя в разных формах (Matt / Matthew, Yegor / Egor)."""
    a, b = norm(a), norm(b)
    return a == b or (min(len(a), len(b)) >= 3 and (a.startswith(b) or b.startswith(a))) or _sim(a, b) >= 0.7


def attach_ea(players, ea):
    by_name = defaultdict(list)
    by_last = defaultdict(list)
    for p in players:
        by_name[norm(p['first'] + p['last'])].append(p)
        by_last[norm(p['last'])].append(p)
    unmatched = []
    for q in ea:
        goalie = q['pos'] == 'G'
        cands = [p for p in by_name.get(norm(q['first'] + q['last']), []) if (p['pos'] == 'G') == goalie]
        if len(cands) > 1:
            cands = [p for p in cands if p['team'] == q['team']] or cands
        if not cands:     # другое написание имени: та же фамилия, клуб и номер или похожее имя
            cands = [p for p in by_last.get(norm(q['last']), []) if (p['pos'] == 'G') == goalie
                     and p['team'] == q['team'] and (p['num'] == q['num'] or same_first(p['first'], q['first']))]
        if len(cands) == 1 and cands[0]['ea'] is None:
            cands[0]['ea'] = {k: q[k] for k in ('ea_id', 'ovr', 'attrs', 'team', 'num', 'avatar')}
            cands[0]['ea']['name'] = f"{q['first']} {q['last']}"
        else:
            unmatched.append({'ea_id': q['ea_id'], 'name': f"{q['first']} {q['last']}", 'team': q['team_label'],
                              'ovr': q['ovr'], 'why': 'нет в составах НХЛ' if not cands else 'неоднозначно'})
    return unmatched


def attach_nr(players, nr):
    by_lb = defaultdict(list)
    by_name = defaultdict(list)
    for p in players:
        by_lb[(norm(p['last']), tuple(p['birth']))].append(p)
        by_name[norm(p['first'] + p['last'])].append(p)
    used = 0
    for q in nr:
        if not q.get('ovr') and not q.get('attrs'):
            continue
        goalie = (q.get('position') or '').startswith('Goalie')
        parts = q['name'].split(' ', 1)
        first, last = (parts + [''])[:2]
        cands = []
        if q.get('birth'):
            b = tuple(q['birth'])
            cands = [p for p in players if tuple(p['birth']) == b and (p['pos'] == 'G') == goalie
                     and (norm(p['first'] + p['last']) == norm(q['name']) or norm(p['last']) in norm(q['name']))]
            if len(cands) > 1:
                cands = [p for p in cands if same_first(p['first'], first)] or cands
        if not cands:
            cands = [p for p in by_name.get(norm(q['name']), []) if (p['pos'] == 'G') == goalie]
            if q.get('birth'):
                cands = [p for p in cands if abs(p['birth'][0] - q['birth'][0]) <= 1]
        if len(cands) != 1:
            continue
        p = cands[0]
        if p['nhlratings'] and len(p['nhlratings']['attrs']) >= len(sources.nr_fields(q)):
            continue
        p['nhlratings'] = {'slug': q['slug'], 'ovr': q.get('ovr'), 'attrs': sources.nr_fields(q),
                           'style': sources.nr_style(q), 'style_label': q.get('style'), 'team': q.get('team_label')}
        used += 1
    return used


def attach_captains(players, caps):
    found = 0
    by_team = defaultdict(list)
    for p in players:
        by_team[p['team']].append(p)
    misses = []
    for team, letters in caps.items():
        for letter in ('C', 'A'):
            for name in letters.get(letter, []):
                cands = [p for p in by_team[team] if norm(p['first'] + p['last']) == norm(name)]
                if not cands:
                    last = name.split()[-1]
                    cands = [p for p in by_team[team] if norm(p['last']) == norm(last)]
                if len(cands) == 1:
                    cands[0]['letter'] = letter
                    found += 1
                else:
                    misses.append(f'{team} {letter} {name}')
    return found, misses


def choose_rating(p):
    """Источник рейтинга: EA (все атрибуты) → nhlratings.net (атрибуты) → только OVR → нет."""
    ea, nr = p['ea'], p['nhlratings']
    style = nr.get('style') if nr else None
    if ea and len(ea['attrs']) >= 15:
        return {'source': 'ea', 'ovr': ea['ovr'], 'attrs': dict(ea['attrs']), 'style': style}
    if nr and len(nr['attrs']) >= 10:
        return {'source': 'nhlratings', 'ovr': nr['ovr'], 'attrs': dict(nr['attrs']), 'style': style}
    ovr = (ea or {}).get('ovr') or (nr or {}).get('ovr')
    attrs = dict((nr or {}).get('attrs') or {})
    if ovr:
        return {'source': 'nhlratings-ovr' if not ea else 'ea-ovr', 'ovr': ovr, 'attrs': attrs, 'style': style}
    return {'source': 'none', 'ovr': None, 'attrs': attrs, 'style': style}


def run(paths, log=print):
    cache = paths.cache
    rosters = sources.nhl_rosters(cache)
    bios = sources.nhl_bios(cache)
    players, no_landing = [], []
    for abbr, entries in rosters.items():
        for e in entries:
            land = sources.nhl_landing(cache, e['id']) or {}
            if not land:
                no_landing.append(e['id'])
            players.append(base_record(abbr, e, land, bios.get(e['id'])))
    dup = defaultdict(list)
    for p in players:
        dup[p['nhl_id']].append(p['team'])
    players = list({p['nhl_id']: p for p in players}.values())     # игрок в двух составах — последний
    ea = sources.ea_players(cache)
    ea_unmatched = attach_ea(players, ea)
    nr = sources.nhlratings_players(cache)
    nr_used = attach_nr(players, nr)
    caps = sources.captains(cache)
    cap_found, cap_miss = attach_captains(players, caps)
    for p in players:
        p['rating'] = choose_rating(p)
    by_src = defaultdict(int)
    for p in players:
        by_src[p['rating']['source']] += 1
    meta = {
        'season': SEASON, 'generated': time.strftime('%Y-%m-%d %H:%M:%S'),
        'counts': {'players': len(players), 'no_landing': len(no_landing), 'ea_top300': len(ea),
                   'ea_matched': len(ea) - len(ea_unmatched), 'nhlratings_pages': len(nr),
                   'nhlratings_matched': nr_used, 'captains_teams': len(caps), 'letters_found': cap_found,
                   'rating_sources': dict(by_src)},
        'two_rosters': {str(k): v for k, v in dup.items() if len(v) > 1},
        'ea_unmatched': ea_unmatched, 'letters_unmatched': cap_miss, 'no_landing': no_landing,
    }
    players.sort(key=lambda p: (p['slot'], {'C': 0, 'L': 1, 'R': 2, 'D': 3, 'G': 4}[p['pos']], p['last'], p['first']))
    write_json(paths.players, {'meta': meta, 'players': players})
    c = meta['counts']
    log(f"build: {c['players']} игроков 32 клубов; EA {c['ea_matched']}/{c['ea_top300']}, nhlratings.net "
        f"{c['nhlratings_matched']}; рейтинги {dict(by_src)}; буквы {cap_found} ({len(caps)} клубов) -> {paths.players}")
    if no_landing:
        log(f'  без карточки landing: {len(no_landing)} (fetch не закончен?)')
    return meta
