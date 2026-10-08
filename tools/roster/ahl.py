"""Клубы АХЛ, которые конвейер заполняет сам (база tools/nhl32.py --ahl32): составы из Wikipedia.

Источник — статья клуба в английской Wikipedia, раздел «Current roster»: шаблоны
{{Ice hockey team player | first | last | num | pos | nat | s/g | birthyear/month/day | birthplace |
contract | inj | cap}}. Закомментированные (<!-- -->) — не в составе (вызваны в НХЛ, отданы и т. п.).
У части клубов состав — отдельный шаблон «Template:<клуб> roster», он подтягивается сам.
Игроки сшиваются с ID НХЛ поиском search.d3.nhle.com по имени (без фильтра active — находит и
игроков с контрактом только в АХЛ), проверка — дата рождения в карточке landing. Кого не нашли —
запись только из Wikipedia (рост и вес — типовые по амплуа), ID свой: 90 000 000 +.
Контракт: в поле contract — клуб НХЛ (у игрока права клуба-хозяина, proteam) или сам клуб АХЛ.
"""
import os
import re
import urllib.parse
import zlib

from .codes import PROVINCE_NAMES, PROVINCES, STATE_NAMES, STATES
from .common import AHL_CLUBS, SEASON_YEAR, TEAM_NAMES, norm, read_json, write_json

WIKI_RAW = 'https://en.wikipedia.org/wiki/{}?action=raw'      # robots.txt закрывает /w/, /wiki/ — открыт
SEARCH = 'https://search.d3.nhle.com/api/v1/search/player?culture=en-us&limit=20&q={}'
NHL = 'https://api-web.nhle.com/v1'
POS = {'C': 'C', 'LW': 'L', 'RW': 'R', 'W': 'L', 'F': 'C', 'D': 'D', 'G': 'G', 'L': 'L', 'R': 'R'}
NAT = {'canada': 'CAN', 'united states': 'USA', 'usa': 'USA', 'sweden': 'SWE', 'finland': 'FIN',
       'russia': 'RUS', 'czech republic': 'CZE', 'czechia': 'CZE', 'slovakia': 'SVK', 'germany': 'DEU',
       'switzerland': 'CHE', 'latvia': 'LVA', 'denmark': 'DNK', 'norway': 'NOR', 'austria': 'AUT',
       'belarus': 'BLR', 'ukraine': 'UKR', 'slovenia': 'SVN', 'france': 'FRA', 'kazakhstan': 'KAZ',
       'netherlands': 'NLD', 'italy': 'ITA', 'great britain': 'GBR', 'united kingdom': 'GBR', 'england': 'GBR',
       'scotland': 'GBR', 'poland': 'POL', 'hungary': 'HUN', 'lithuania': 'LTU', 'estonia': 'EST',
       'australia': 'AUS', 'japan': 'JPN', 'south korea': 'KOR', 'croatia': 'HRV', 'belgium': 'BEL'}
SYNTH = 90_000_000
# Сила игроков АХЛ без рейтинга (шкала NHL 27): в исходной базе NHL 13 медиана АХЛ — 76 (НХЛ — 83),
# четверти 74 и 78; поправки — возраст и игры в НХЛ.
AHL_OVR = 76


# --- разбор wikitext --------------------------------------------------------------------------
def strip_comments(text):
    return re.sub(r'<!--.*?-->', '', text or '', flags=re.S)


def templates(text, name='Ice hockey team player'):
    """Тела шаблонов {{name | …}} с учётом вложенных {{ }}."""
    pat = re.compile(r'\{\{\s*' + r'\s+'.join(map(re.escape, name.split())) + r'\s*\|', re.I)
    out, i = [], 0
    while True:
        m = pat.search(text, i)
        if not m:
            return out
        depth, j = 0, m.start()
        while j < len(text):
            if text.startswith('{{', j):
                depth += 1
                j += 2
            elif text.startswith('}}', j):
                depth -= 1
                j += 2
                if depth == 0:
                    break
            else:
                j += 1
        out.append(text[m.end():j - 2])
        i = j


def fields(body):
    """Поля шаблона: разделитель | вне [[ ]] и {{ }}."""
    parts, cur, depth, k = [], '', 0, 0
    while k < len(body):
        two = body[k:k + 2]
        if two in ('[[', '{{'):
            depth, cur, k = depth + 1, cur + two, k + 2
        elif two in (']]', '}}'):
            depth, cur, k = depth - 1, cur + two, k + 2
        elif body[k] == '|' and depth == 0:
            parts.append(cur)
            cur, k = '', k + 1
        else:
            cur, k = cur + body[k], k + 1
    parts.append(cur)
    out = {}
    for p in parts:
        if '=' in p:
            key, val = p.split('=', 1)
            out[key.strip().lower()] = val.strip()
    return out


def link_text(v):
    """[[A|B]] → B, [[A]] → A, без разметки."""
    v = re.sub(r'\[\[([^\]|]*)\|([^\]]*)\]\]', r'\2', v or '')
    v = re.sub(r'\[\[([^\]]*)\]\]', r'\1', v)
    v = re.sub(r'\{\{[^}]*\}\}', '', v)
    return re.sub(r'<[^>]+>', '', v).strip()


def roster_entries(text):
    out = []
    for body in templates(strip_comments(text)):
        f = fields(body)
        first, last = link_text(f.get('first')), link_text(f.get('last'))
        if not last:
            continue
        try:
            birth = [int(f['birthyear']), int(f['birthmonth']), int(f['birthday'])]
        except (KeyError, ValueError):
            birth = None
        num = f.get('num', '').strip()
        out.append({'first': first, 'last': last, 'num': int(num) if num.isdigit() else None,
                    'pos': POS.get(f.get('pos', '').strip().upper()), 'nat': link_text(f.get('nat')),
                    'shoots': (f.get('s/g') or '').strip()[:1].upper() or None, 'birth': birth,
                    'birthplace': link_text(f.get('birthplace')), 'contract': link_text(f.get('contract')),
                    'injured': f.get('inj', '').strip().lower() in ('yes', 'y'),
                    'letter': (f.get('cap') or '').strip().upper()[:1] or None})
    return out


# --- fetch ------------------------------------------------------------------------------------
def roster_text(h, club):
    """wikitext состава: статья клуба или подключённый в ней шаблон «<клуб> roster»."""
    text = h.text(WIKI_RAW.format(club['wiki']), f"wiki/ahl/{club['wiki']}.wiki") or ''
    if templates(strip_comments(text)):
        return text
    m = re.search(r'\{\{\s*(' + re.escape(club['name']) + r'\s+roster)\s*\}\}', text, re.I)
    if not m:
        return text
    title = 'Template:' + m.group(1).strip().replace(' ', '_')
    return h.text(WIKI_RAW.format(urllib.parse.quote(title)), f"wiki/ahl/{title.replace(':', '_')}.wiki") or ''


def birth_str(b):
    return '%04d-%02d-%02d' % tuple(b) if b else None


def fetch(h, log):
    """Составы клубов AHL_CLUBS → кэш nhl/ahl/<клуб>.json (с ID НХЛ, где нашёлся) и карточки landing."""
    for slot, club in sorted(AHL_CLUBS.items()):
        entries = roster_entries(roster_text(h, club))
        found = []
        for e in entries:
            q = f"{e['first']} {e['last']}"
            res = h.json(SEARCH.format(urllib.parse.quote(q)), f'nhl/search/ahl/{norm(q)}.json') or []
            cands = [x for x in res if norm(x.get('name')) == norm(q)]
            if not cands:
                cands = [x for x in res if norm(x.get('name')).endswith(norm(e['last']))]
            cands.sort(key=lambda x: (x.get('teamAbbrev') != club['parent'], x.get('lastTeamAbbrev') != club['parent']))
            pid = None
            for x in cands[:4]:
                land = h.json(f"{NHL}/player/{x['playerId']}/landing", f"nhl/landing/{x['playerId']}.json")
                if not land:
                    continue
                same_org = club['parent'] in (x.get('teamAbbrev'), x.get('lastTeamAbbrev'))
                # дата из Wikipedia бывает с ошибкой (John Hayden: 14.09 вместо 14.02.1995): точное имя,
                # тот же клуб-хозяин и год рождения — тоже он
                if (e['birth'] is None or land.get('birthDate') == birth_str(e['birth'])
                        or (norm(x.get('name')) == norm(q) and same_org
                            and str(land.get('birthDate', ''))[:4] == str(e['birth'][0]))):
                    pid = int(x['playerId'])
                    break
            found.append(dict(e, nhl_id=pid))
        write_json(h.path(f"nhl/ahl/{club['abbr']}.json"), {'club': club['abbr'], 'slot': slot, 'players': found})
        log(f"АХЛ {club['abbr']}: в составе {len(entries)}, с ID НХЛ {sum(1 for x in found if x['nhl_id'])}")


# --- build ------------------------------------------------------------------------------------
def nhl_contract(club, contract):
    c = norm(contract)
    parent = TEAM_NAMES[club['parent']]
    return bool(c) and (c in norm(parent) or norm(parent).endswith(c) or norm(club['parent_nick']) in c)


def place(text):
    """«Город, провинция/штат/страна» → (город, регион, ISO-3 страны или None)."""
    parts = [x.strip() for x in (text or '').split(',') if x.strip()]
    city = parts[0] if parts else None
    region = parts[1] if len(parts) > 1 else None
    r = (region or '').lower()
    if r in PROVINCE_NAMES or region in PROVINCES:
        return city, region, 'CAN'
    if r in STATE_NAMES or region in STATES:
        return city, region, 'USA'
    return city, None, NAT.get(r) or NAT.get((parts[-1] if parts else '').lower())


def wiki_record(club, slot, e):
    """Запись игрока только по Wikipedia (у кого нет ID НХЛ)."""
    y, m, d = e['birth'] or (SEASON_YEAR - 24, 1, 1)
    city, region, country = place(e['birthplace'])
    nat = NAT.get((e['nat'] or '').lower()) or country
    pos = e['pos'] or 'C'
    sid = SYNTH + zlib.crc32(f"{norm(e['first'] + e['last'])}{y:04d}{m:02d}{d:02d}".encode()) % 9_000_000
    return {
        'nhl_id': sid, 'team': club['abbr'], 'slot': slot, 'first': e['first'], 'last': e['last'], 'pos': pos,
        'shoots': e['shoots'], 'num': e['num'], 'birth': [y, m, d], 'birth_city': city, 'birth_state': region,
        'birth_country': country or nat, 'nationality': nat,
        'height_in': {'D': 74, 'G': 74}.get(pos, 72), 'weight_lb': {'D': 200, 'G': 190}.get(pos, 190),
        'draft': None, 'nhl_gp': {'career': 0, 'by_season': {}, 'regular_by_season': {}, 'debut': None},
        'pro_gp': 0, 'scoring': {'nhl': {'gp': 0, 'g': 0, 'a': 0, 'pim': 0}},
        'rookie': SEASON_YEAR - y < 26, 'landing': False, 'omitted': False, 'photo': None, 'contract': None,
        'letter': None, 'ea': None, 'nhlratings': None, 'rating': None, 'wiki_only': True,
    }


def players(cache, bios, base_record, entry_from_landing, landing, log=print):
    """Игроки клубов AHL_CLUBS в формате players.json (поле ahl: клуб, хозяин, контракт НХЛ)."""
    out, missing = [], []
    for slot, club in sorted(AHL_CLUBS.items()):
        d = read_json(os.path.join(cache, 'nhl', 'ahl', f"{club['abbr']}.json"))
        if not d:
            missing.append(club['abbr'])
            continue
        for e in d['players']:
            land = landing(cache, e['nhl_id']) if e['nhl_id'] else None
            if land and land.get('position') in POS.values():
                le = entry_from_landing(land)
                if e['num']:
                    le['sweaterNumber'] = e['num']          # номер в АХЛ
                p = base_record(club['abbr'], le, land, bios.get(e['nhl_id']), slot=slot)
            else:
                p = wiki_record(club, slot, e)
            p['ahl'] = {'club': club['abbr'], 'parent': club['parent'], 'nhl_contract': nhl_contract(club, e['contract']),
                        'contract': e['contract']}
            p['letter'] = e['letter'] if e['letter'] in ('C', 'A') else None
            p['omitted'] = e['injured']
            out.append(p)
    if missing:
        log(f"  АХЛ: нет кэша составов {missing} — сначала fetch --only ahl")
    return out


def target_ovr(p, spread):
    """OVR игрока АХЛ без рейтинга: медиана АХЛ, моложе 21 — на 1 ниже, с опытом НХЛ — выше."""
    gp = p['nhl_gp']['career']
    a = SEASON_YEAR - p['birth'][0]
    adj = (-1 if a <= 21 else 0) + (2 if gp >= 200 else 1 if gp >= 40 else 0)
    if p['pos'] == 'G':
        adj -= 1
    return AHL_OVR + adj + spread
