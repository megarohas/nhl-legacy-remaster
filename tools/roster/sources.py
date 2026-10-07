"""Разбор сырых ответов из кэша: API НХЛ, EA NHL 27, nhlratings.net, капитаны из Wikipedia.

Каждая функция читает только кэш (game/work/roster-cache/) и возвращает простые словари;
сшивка источников — в build.py.
"""
import html
import json
import os
import re

from .common import SEASON, TEAM_NAMES, norm, read_json

# --- атрибуты: названия источников → поля NHL 13 ----------------------------------------------
# EA (ключи stats на ea.com) → exhibitionskaterai
EA_SKATER = {
    'deking': 'p_deking', 'handeye': 'p_handeye', 'passing': 'p_passing', 'puckControl': 'p_puckcontrol',
    'slapshotAccuracy': 'p_slapaccuracy', 'slapshotPower': 'p_slapshotpower', 'wristshotAccuracy': 'p_wristaccuracy',
    'wristshotPower': 'p_wristshotpower', 'acceleration': 'p_acceleration', 'agility': 'p_agility',
    'balance': 'p_balance', 'endurance': 'p_endurance', 'speed': 'p_speed', 'discipline': 'p_discipline',
    'offensiveAwareness': 'p_offawareness', 'poise': 'p_poise', 'defensiveAwareness': 'p_defawareness',
    'faceoffs': 'p_faceoffs', 'shotBlocking': 'p_shotblocking', 'stickChecking': 'p_stickchecking',
    'aggression': 'p_aggression', 'bodyChecking': 'p_bodychecking', 'durability': 'p_durability',
    'fightingSkill': 'p_fightingskill', 'strength': 'p_strength',
}
# EA → exhibitiongoalieai (Angles = g_positioning; g_consistency в NHL 27 нет)
EA_GOALIE = {
    'glovesideHigh': 'g_gsh', 'glovesideLow': 'g_gsl', 'sticksideHigh': 'g_ssh', 'sticksideLow': 'g_ssl',
    'fiveHole': 'g_5hole', 'pokeCheck': 'g_pokecheck', 'angles': 'g_positioning', 'reboundControl': 'g_reboundcontrol',
    'breakaway': 'g_breakaway', 'puckplayingFrequency': 'g_puckplayfrequency', 'aggressiveness': 'g_aggression',
    'vision': 'g_vision', 'shotRecover': 'g_shotrecover', 'agility': 'g_agility', 'speed': 'g_speed',
    'endurance': 'g_endurance', 'durability': 'g_durability', 'passing': 'g_passing', 'poise': 'g_poise',
}
# nhlratings.net: подписи на странице игрока и в списках
NR_SKATER = {
    'Deking': 'p_deking', 'Hand-Eye': 'p_handeye', 'Passing': 'p_passing', 'Puck Control': 'p_puckcontrol',
    'Slap Shot Accuracy': 'p_slapaccuracy', 'Slap Shot Power': 'p_slapshotpower',
    'Wrist Shot Accuracy': 'p_wristaccuracy', 'Wrist Shot Power': 'p_wristshotpower',
    'Acceleration': 'p_acceleration', 'Agility': 'p_agility', 'Balance': 'p_balance', 'Endurance': 'p_endurance',
    'Speed': 'p_speed', 'Discipline': 'p_discipline', 'Offensive Awareness': 'p_offawareness', 'Poise': 'p_poise',
    'Defensive Awareness': 'p_defawareness', 'Faceoffs': 'p_faceoffs', 'Shot Blocking': 'p_shotblocking',
    'Stick Checking': 'p_stickchecking', 'Aggression': 'p_aggression', 'Aggressiveness': 'p_aggression',
    'Body Checking': 'p_bodychecking', 'Durability': 'p_durability', 'Fighting Skill': 'p_fightingskill',
    'Strength': 'p_strength',
}
NR_GOALIE = {
    'Glove Side High': 'g_gsh', 'Glove Side Low': 'g_gsl', 'Stick Side High': 'g_ssh', 'Stick Side Low': 'g_ssl',
    'Five Hole': 'g_5hole', 'Poke Check': 'g_pokecheck', 'Angles': 'g_positioning',
    'Rebound Control': 'g_reboundcontrol', 'Breakaway': 'g_breakaway', 'Puck Playing Frequency': 'g_puckplayfrequency',
    'Aggression': 'g_aggression', 'Aggressiveness': 'g_aggression', 'Vision': 'g_vision',
    'Shot Recover': 'g_shotrecover', 'Agility': 'g_agility', 'Speed': 'g_speed', 'Endurance': 'g_endurance',
    'Durability': 'g_durability', 'Passing': 'g_passing', 'Poise': 'g_poise',
}
NR_LIST_LABEL = {'angles': 'Angles', 'breakaway': 'Breakaway', 'five-hole': 'Five Hole',
                 'glove-side-high': 'Glove Side High', 'glove-side-low': 'Glove Side Low',
                 'stick-side-high': 'Stick Side High', 'stick-side-low': 'Stick Side Low', 'poke-check': 'Poke Check',
                 'rebound-control': 'Rebound Control', 'shot-recover': 'Shot Recover', 'vision': 'Vision',
                 'puck-playing-frequency': 'Puck Playing Frequency', 'aggression': 'Aggression'}
# стиль игрока NHL 27 → p_style / g_style NHL 13 (сверено по базе: Кросби 6, Стэмкос 7, Бержерон 9,
# Чара 1, Кит 2, Летанг 4, Броудер 0, Луонго 2)
STYLE = {'defensive d-man': 1, 'offensive d-man': 2, 'enforcer d-man': 3, '2 way d-man': 4, 'two-way d-man': 4,
         'grinder': 5, 'playmaker': 6, 'sniper': 7, 'power forward': 8, '2 way forward': 9, 'two-way forward': 9,
         'enforcer': 10}
GOALIE_STYLE = {'standup': 0, 'stand-up': 0, 'butterfly': 1, 'hybrid': 2}
MONTHS = {m: i + 1 for i, m in enumerate(['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August',
                                          'September', 'October', 'November', 'December'])}


def _p(cache, *parts):
    return os.path.join(cache, *parts)


# --- API НХЛ ----------------------------------------------------------------------------------
def nhl_rosters(cache):
    """{TEAM: [roster entry]} из /v1/roster/{TEAM}/current."""
    out = {}
    for abbr in TEAM_NAMES:
        d = read_json(_p(cache, 'nhl', 'roster', f'{abbr}.json'))
        if d is None:
            raise FileNotFoundError(f'нет состава {abbr} в кэше — сначала fetch')
        out[abbr] = [dict(p, _group=g) for g in ('forwards', 'defensemen', 'goalies') for p in d.get(g) or []]
    return out


def nhl_landing(cache, pid):
    return read_json(_p(cache, 'nhl', 'landing', f'{pid}.json'))


def nhl_bios(cache):
    """playerId → строка stats REST bios (новый сезон поверх прошлого)."""
    out = {}
    for kind in ('skater', 'goalie'):
        for season in (SEASON - 10001, SEASON):
            d = read_json(_p(cache, 'nhl', 'stats', f'{kind}-bios-{season}.json')) or {}
            for r in d.get('data') or []:
                out[r['playerId']] = r
    return out


# --- EA NHL 27 --------------------------------------------------------------------------------
EA_POS = {'Center': 'C', 'Left Wing': 'L', 'Right Wing': 'R', 'Left Defense': 'D', 'Right Defense': 'D',
          'Defense': 'D', 'Goalie': 'G'}


def ea_players(cache):
    """Топ-300 NHL 27 с ea.com: ID EA, имя, клуб, номер, OVR, атрибуты (поля NHL 13)."""
    out, seen = [], set()
    for page in range(1, 7):
        fn = _p(cache, 'ea', f'ratings-page{page}.html')
        if not os.path.exists(fn):
            continue
        t = open(fn, encoding='utf-8').read()
        m = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', t, re.S)
        if not m:
            continue
        items = json.loads(m.group(1))['props']['pageProps']['ratingDetails']['items']
        for it in items:
            if it['id'] in seen:
                continue
            seen.add(it['id'])
            pos = EA_POS.get((it.get('position') or {}).get('label'))
            amap = EA_GOALIE if pos == 'G' else EA_SKATER
            stats = it.get('stats') or {}
            attrs = {f: stats[k]['value'] for k, f in amap.items() if (stats.get(k) or {}).get('value')}
            team = (it.get('team') or {}).get('label') or ''
            out.append({'ea_id': it['id'], 'first': it.get('firstName') or '', 'last': it.get('lastName') or '',
                        'ovr': it.get('overallRating'), 'num': it.get('jerseyNum'), 'pos': pos,
                        'team': next((a for a, n in TEAM_NAMES.items() if norm(n) == norm(team)), None),
                        'team_label': team, 'nationality': (it.get('nationality') or {}).get('label'),
                        'attrs': attrs, 'avatar': it.get('avatarUrl')})
    return out


# --- nhlratings.net ---------------------------------------------------------------------------
def _lines(body):
    body = re.sub(r'<script.*?</script>|<style.*?</style>', '', body, flags=re.S)
    t = html.unescape(re.sub(r'<[^>]+>', '\n', body))
    return [l.strip() for l in t.split('\n') if l.strip()]


def _after(lines, label):
    return lines[lines.index(label) + 1] if label in lines and lines.index(label) + 1 < len(lines) else None


def nr_player(slug, body):
    """Страница игрока: имя, дата рождения, клуб, амплуа, стиль, OVR, атрибуты (подпись → число)."""
    lines = _lines(body)
    p = {'slug': slug, 'team_label': _after(lines, 'Team:'), 'position': _after(lines, 'Position:'),
         'style': _after(lines, 'Player Style:'), 'nationality': _after(lines, 'Nationality:')}
    title = re.search(r'<title>(.*?)(?: NHL 27| \|)', body)
    p['name'] = html.unescape(title.group(1)).strip() if title else slug
    for l in lines:
        m = re.match(r'Birthdate: (\w+) (\d+), (\d{4})', l)
        if m and m.group(1) in MONTHS:
            p['birth'] = [int(m.group(3)), MONTHS[m.group(1)], int(m.group(2))]
            break
    joined = ' '.join(lines)
    m = (re.search(r'(\d+) current Overall Rating in NHL 27', joined)
         or re.search(r'On NHL 27, .*? has an Overall Rating of (\d+)', joined))
    p['ovr'] = int(m.group(1)) if m else None
    attrs = {}
    if 'NHL 27 Attributes' in lines and 'Total Attributes' in lines:
        seq = lines[lines.index('NHL 27 Attributes') + 1:lines.index('Total Attributes')]
        for val, lab in zip(seq[0::2], seq[1::2]):     # число стоит перед подписью
            if not lab.endswith('Ratings') and val.isdigit():
                attrs[lab] = int(val)
    p['attrs'] = attrs
    return p


def nr_list(body):
    """Список топ-100 по атрибуту: [(имя, команда, значение, OVR)]."""
    lines = _lines(body)
    out = []
    for i, l in enumerate(lines):
        if not re.fullmatch(r'\d+\.', l) or '|' not in lines[i + 1:i + 5]:
            continue
        bar = lines.index('|', i + 1)
        name, team = lines[i + 1], lines[bar + 1]
        nums = lines[bar + 2:bar + 5]
        if len(nums) == 3 and all(x.replace(',', '').isdigit() for x in nums):
            out.append((name, team, int(nums[0]), int(nums[1])))
    return out


def nhlratings_players(cache):
    """Игроки nhlratings.net (страницы клубов) с вратарскими атрибутами из списков топ-100."""
    folder = _p(cache, 'nhlratings', 'players')
    players = []
    if os.path.isdir(folder):
        for fn in sorted(os.listdir(folder)):
            if fn.endswith('.html'):
                with open(os.path.join(folder, fn), encoding='utf-8') as f:
                    players.append(nr_player(fn[:-5], f.read()))
    by_name = {}
    for p in players:
        by_name.setdefault(norm(p['name']), []).append(p)
    for slug, label in NR_LIST_LABEL.items():
        fn = _p(cache, 'nhlratings', f'lists__{slug}.html')
        if not os.path.exists(fn):
            continue
        with open(fn, encoding='utf-8') as f:
            rows = nr_list(f.read())
        for name, team, val, ovr in rows:
            cands = [p for p in by_name.get(norm(name), []) if (p.get('position') or '').startswith('Goalie')]
            if len(cands) > 1:
                cands = [p for p in cands if p.get('ovr') == ovr] or cands
            for p in cands[:1]:
                p['attrs'].setdefault(label, val)
    return players


def nr_fields(p):
    """Атрибуты игрока nhlratings.net в полях NHL 13."""
    goalie = (p.get('position') or '').startswith('Goalie')
    amap = NR_GOALIE if goalie else NR_SKATER
    return {amap[k]: v for k, v in (p.get('attrs') or {}).items() if k in amap}


def nr_style(p):
    s = (p.get('style') or '').strip().lower()
    if (p.get('position') or '').startswith('Goalie'):
        return GOALIE_STYLE.get(s)
    return STYLE.get(s)


# --- капитаны (Wikipedia) ---------------------------------------------------------------------
def captains(cache):
    """{TEAM: {'C': [имя], 'A': [имена]}} из wikitext «List of current NHL captains…»."""
    fn = _p(cache, 'wiki', 'captains.wikitext')
    if not os.path.exists(fn):
        return {}
    text = open(fn, encoding='utf-8').read()
    out = {}

    def names(cell):
        cell = re.sub(r'<ref[^>]*/>|<ref[^>]*>.*?</ref>', '', cell, flags=re.S)
        cell = re.sub(r'\{\{(?:sortname|sname)\|([^|}]+)\|([^|}]+)[^}]*\}\}', r'[[\1 \2]]', cell, flags=re.I)
        found = []
        for m in re.finditer(r'\[\[([^\]|]+)(?:\|([^\]]+))?\]\]', cell):
            name = (m.group(2) or m.group(1)).strip()
            name = re.sub(r'\s*\(.*?\)\s*', '', name)
            if name and not name.lower().startswith(('file:', 'image:')):
                found.append(name)
        return found

    for row in re.split(r'\n\|-', text):
        cells = [c.strip() for c in re.split(r'\n\||\|\|', row) if c.strip()]
        if len(cells) < 2:
            continue
        team = None
        for c in cells:
            for abbr, full in TEAM_NAMES.items():
                if norm(full) in norm(c):
                    team = abbr
                    break
            if team:
                break
        if not team:
            continue
        rest = [c for c in cells if norm(TEAM_NAMES[team]) not in norm(c)]
        people = [names(c) for c in rest]
        people = [p for p in people if p]
        if not people:
            continue
        cap = people[0]
        alts = [n for p in people[1:] for n in p]
        vacant = any('vacant' in c.lower() for c in rest[:1])
        out[team] = {'C': [] if vacant else cap[:1], 'A': (cap[1:] if vacant else []) + alts}
    return out
