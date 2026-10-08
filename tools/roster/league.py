"""Европейские лиги (`--league liiga`): клубы лиги в базе — нынешними составами с официального сайта.

Проба — финская Liiga (строки exhibitionteams 74–87, SM-liiga 2012 года). Источник — открытый JSON
сайта liiga.fi (тот же, что у страниц сайта; ключа и входа нет, robots.txt пустой):
- `/api/v2/players/info?tournament=runkosarja&fromSeason=2027&toSeason=2027` — состав 2026/27 (сезон
  у Liiga — год окончания): имя, дата и место рождения, страна рождения, гражданство, амплуа
  (H/P/MV), хват, рост (см), вес (кг), номер, C/A, травма, ушёл (`removed`), адрес портрета;
- `/api/v2/players/stats/summed/{S}/{S}/runkosarja/true?dataType=basicStats|basicStatsGk` — сводная
  статистика сезона: игры, голы, передачи, штраф; у вратарей — % отражённых; `role` — VL/OL/KH (левый
  крайний, правый крайний, центр), VP/OP (защитники), MV (вратарь). Сезоны 2024–2027: три прошлых —
  для рейтинга (statsrating, NHLe Liiga 0,45), нынешний — для амплуа.
Кэш — game/work/roster-cache/liiga/ (пробные ответы разведки из roster-cache/research/liiga.fi/
берутся оттуда, повторно не скачиваются).

Клубы: 14 мест базы ← клубы Liiga по городу/названию (Espoo Blues → K-Espoo, остальные — те же клубы);
у Liiga 2026/27 их 17 — KooKoo, Sport и Jukurit мест в базе не имеют (в отчёте). Названия команд
в базе не меняются (это другая работа — редактор команд).
Игрок без ID НХЛ: `nhl_id` = 1 000 000 000 + ID Liiga (у НХЛ таких нет); прав клуба НХЛ, драфта,
игр в НХЛ и контракта нет — как у игроков Европы в исходной базе (317 из 357 у SM-liiga 2012 года
без контракта). Рейтинг — по статистике Liiga трёх сезонов (statsrating); вратари и игроки без
статистики — к уровню лиги исходной базы (медиана OVR клубов Liiga 2012 года: 72 у полевых, 73 у
вратарей) с поправкой на % отражённых.
"""
import os
import shutil
import urllib.parse

from . import common
from .common import SEASON, SEASON_YEAR, norm, read_json, write_json

API = 'https://liiga.fi/api/v2'
SEASON_LIIGA = SEASON % 10000                   # 2027 = 2026/27
STAT_SEASONS = [SEASON_LIIGA - 3, SEASON_LIIGA - 2, SEASON_LIIGA - 1, SEASON_LIIGA]
ID_BASE = 1_000_000_000
# место в базе (строка exhibitionteams) ← клуб Liiga (teamName API) и короткое имя
LIIGA_CLUBS = {
    74: ('Ässät', 'ASS'), 75: ('K-Espoo', 'KES'), 76: ('HIFK', 'HIFK'), 77: ('HPK', 'HPK'), 78: ('Ilves', 'ILV'),
    79: ('Jokerit', 'JOK'), 80: ('JYP', 'JYP'), 81: ('KalPa', 'KAL'), 82: ('Kärpät', 'KAR'), 83: ('Lukko', 'LUK'),
    84: ('Pelicans', 'PEL'), 85: ('SaiPa', 'SAI'), 86: ('Tappara', 'TAP'), 87: ('TPS', 'TPS'),
}
POS = {'KH': 'C', 'VL': 'L', 'OL': 'R', 'VP': 'D', 'OP': 'D', 'P': 'D', 'MV': 'G', 'H': 'C'}
DETAIL = ('KH', 'VL', 'OL', 'VP', 'OP')
LEVEL = {'F': 72, 'D': 72, 'G': 73}             # медиана OVR клубов SM-liiga исходной базы
GOALIE_AVG = 0.913                              # средний % отражённых Liiga (как в statsrating.GOALIE)
RESEARCH = ('research', 'liiga.fi')
CLUB_MAX = 33                                   # как у самого большого клуба исходной базы (HPK 2012)
if common.GAME.name == 'legacy':
    # NHL Legacy: Liiga 2015/16 — строки 76–90 (15 клубов, есть KooKoo и Sport; Jokerit тогда был в КХЛ —
    # места нет, как и у Jukurit); уровень OVR клубов Liiga в базе Legacy ниже: медианы 65/65/64
    LIIGA_CLUBS = {
        76: ('Ässät', 'ASS'), 77: ('K-Espoo', 'KES'), 78: ('HPK', 'HPK'), 79: ('HIFK', 'HIFK'), 80: ('Ilves', 'ILV'),
        81: ('JYP', 'JYP'), 82: ('KalPa', 'KAL'), 83: ('Kärpät', 'KAR'), 84: ('KooKoo', 'KOO'), 85: ('Lukko', 'LUK'),
        86: ('Pelicans', 'PEL'), 87: ('SaiPa', 'SAI'), 88: ('Tappara', 'TAP'), 89: ('TPS', 'TPS'), 90: ('Sport', 'SPO'),
    }
    LEVEL = {'F': 65, 'D': 65, 'G': 64}
    # оценка OVR по статистике (statsrating) — в шкале NHL 13 (Liiga 2026/27 там — медиана 72, как у
    # Liiga 2012 в базе NHL 13); у Legacy лиги вне НХЛ ниже на 7–15 (НХЛ — та же, 82): полевым — сдвиг
    SHIFT = {'F': -7, 'D': -7}
else:
    SHIFT = {}


def _rel_info():
    return f'liiga/players-{SEASON_LIIGA}.json'


def _rel_stats(season, gk):
    return f"liiga/stats-{season}-{'goalies' if gk else 'skaters'}.json"


def _seed(h, rel, research_name):
    """Ответ из пробы разведки (roster-cache/research/liiga.fi) — в кэш конвейера, без сети."""
    dst = h.path(rel)
    src = os.path.join(h.cache, *RESEARCH, research_name)
    if not os.path.exists(dst) and os.path.exists(src):
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copyfile(src, dst)


def fetch(h, log):
    """Состав 2026/27 и сводная статистика 4 сезонов (8 запросов, часть — из пробы разведки)."""
    _seed(h, _rel_info(), f'api_v2_players_info_runkosarja_{SEASON_LIIGA}.json')
    roster = h.json(f'{API}/players/info?tournament=runkosarja&fromSeason={SEASON_LIIGA}&toSeason={SEASON_LIIGA}',
                    _rel_info()) or []
    for s in STAT_SEASONS:
        for gk in (False, True):
            dt = 'basicStatsGk' if gk else 'basicStats'
            _seed(h, _rel_stats(s, gk), f'api_v2_players_stats_summed_{s}_runkosarja_{dt}.json')
            h.json(f'{API}/players/stats/summed/{s}/{s}/runkosarja/true?dataType={dt}', _rel_stats(s, gk))
    log(f'Liiga: состав {SEASON_LIIGA - 1}/{SEASON_LIIGA % 100} — {len(roster)} игроков, статистика сезонов '
        f'{STAT_SEASONS[0]}–{STAT_SEASONS[-1]}')


def _cm_in(cm):
    return round(cm / 2.54) if cm else None


def _kg_lb(kg):
    return round(kg * 2.20462) if kg else None


def season_key(s):
    return (s - 1) * 10000 + s


def players(cache, existing, log=print):
    """Игроки клубов LIIGA_CLUBS в формате players.json (поле league) и сводка (кто не взят)."""
    roster = read_json(os.path.join(cache, *_rel_info().split('/')))
    if roster is None:
        log('  Liiga: нет кэша состава — сначала fetch --only liiga')
        return [], {}
    stats = {}                                  # id → {сезон: строка}
    roles = {}
    for s in STAT_SEASONS:
        for gk in (False, True):
            for r in read_json(os.path.join(cache, *_rel_stats(s, gk).split('/')), []) or []:
                stats.setdefault(r['playerId'], {})[s] = r
                if r.get('role') in DETAIL:          # в нынешнем сезоне у нападающих бывает просто H
                    roles.setdefault(r['playerId'], {})[s] = r['role']
    slot_of = {name: slot for slot, (name, _) in LIIGA_CLUBS.items()}
    have = {(norm(p['first'] + p['last']), tuple(p['birth'])) for p in existing}
    out, skipped = [], {'нет места в базе': [], 'ушёл из клуба': [], 'уже в составе НХЛ/АХЛ': []}
    for q in roster:
        name = f"{q['firstName']} {q['lastName']}"
        if q.get('removed'):
            skipped['ушёл из клуба'].append(name)
            continue
        slot = slot_of.get(q.get('teamName'))
        if slot is None:
            skipped['нет места в базе'].append(f"{name} ({q.get('teamName')})")
            continue
        try:
            birth = [int(x) for x in q['dateOfBirth'].split('-')]
        except (KeyError, ValueError, AttributeError):
            birth = [SEASON_YEAR - 25, 1, 1]
        if (norm(name), tuple(birth)) in have:
            skipped['уже в составе НХЛ/АХЛ'].append(name)
            continue
        rl = roles.get(q['id'], {})
        role = next((rl[s] for s in sorted(rl, reverse=True)), None)      # самый свежий подробный
        pos = 'G' if q.get('roleCode') == 'MV' else 'D' if q.get('roleCode') == 'P' else POS.get(role, 'C')
        if pos == 'D' and q.get('roleCode') == 'H':
            pos = 'C'
        seasons = []
        for s, r in sorted(stats.get(q['id'], {}).items()):
            if s == SEASON_LIIGA:
                continue
            row = {'season': season_key(s), 'gameTypeId': 2, 'leagueAbbrev': 'Liiga', 'gamesPlayed': r.get('games') or 0,
                   'goals': r.get('goals') or 0, 'assists': r.get('assists') or 0, 'points': r.get('points') or 0,
                   'pim': r.get('penaltyMinutes') or 0, 'teamName': {'default': r.get('teamName')}}
            if pos == 'G':
                sv = r.get('savePercentage')
                try:
                    sv = float(str(sv).replace(',', '.'))
                except ValueError:
                    sv = None
                row['savePctg'] = sv / 100 if sv and sv > 1 else sv
            seasons.append(row)
        last = next((x for x in reversed(seasons) if x['gamesPlayed'] >= 10), None)
        sc = {'nhl': {'gp': 0, 'g': 0, 'a': 0, 'pim': 0}}
        if last and pos != 'G':
            sc['other'] = {'league': 'Liiga', 'season': last['season'], 'gp': last['gamesPlayed'], 'g': last['goals'],
                           'a': last['assists'], 'pim': last['pim'], 'junior': False}
        hand = {'LEFT': 'L', 'RIGHT': 'R'}.get(q.get('handedness'))
        nat = (q.get('nationality') or '').strip() or None
        rec = {
            'nhl_id': ID_BASE + q['id'], 'team': LIIGA_CLUBS[slot][1], 'slot': slot, 'first': q['firstName'].strip(),
            'last': q['lastName'].strip(), 'pos': pos, 'shoots': hand, 'num': q.get('jersey') or None, 'birth': birth,
            'birth_city': q.get('placeOfBirth') or None, 'birth_state': None,
            'birth_country': q.get('countryOfBirth') or nat, 'nationality': nat,
            'height_in': _cm_in(q.get('height')), 'weight_lb': _kg_lb(q.get('weight')),
            'draft': None, 'nhl_gp': {'career': 0, 'by_season': {}, 'regular_by_season': {}, 'debut': None},
            'pro_gp': 0, 'scoring': sc, 'rookie': False, 'landing': False, 'omitted': bool(q.get('injured')),
            'photo': q.get('pictureUrl'), 'contract': None,
            'letter': 'C' if q.get('captain') else 'A' if q.get('alternateCaptain') else None,
            'ea': None, 'nhlratings': None, 'rating': None,
            'league': {'code': 'liiga', 'id': q['id'], 'team': q.get('teamName'), 'seasons': seasons,
                       'level': LEVEL['G' if pos == 'G' else 'D' if pos == 'D' else 'F']},
        }
        if SHIFT and pos != 'G':                # Legacy: шкала лиги ниже (statsrating.apply)
            rec['league']['shift'] = SHIFT['D' if pos == 'D' else 'F']
        out.append(rec)
    # не больше CLUB_MAX в клубе (больше, чем у самого большого клуба исходной базы — HPK 2012, 33, — не
    # проверено в игре): лишние — без игр в трёх прошлых сезонах, потом с наименьшим числом игр, не вратари
    skipped['сверх 33 в клубе'] = []
    for slot in LIIGA_CLUBS:
        club = [p for p in out if p['slot'] == slot]
        extra = len(club) - CLUB_MAX
        if extra <= 0:
            continue
        games = lambda p: sum(x['gamesPlayed'] for x in p['league']['seasons'])
        drop = sorted((p for p in club if p['pos'] != 'G'), key=lambda p: (games(p), p['nhl_id']))[:extra]
        for p in drop:
            out.remove(p)
            skipped['сверх 33 в клубе'].append(f"{p['first']} {p['last']} ({p['league']['team']})")
    log(f"Liiga: {len(out)} игроков в {len(LIIGA_CLUBS)} клубах базы; не взяты: "
        + ', '.join(f'{k} {len(v)}' for k, v in skipped.items()))
    return out, skipped


def club_names():
    """{строка exhibitionteams: (сокращение, название)} — для отчётов."""
    return {slot: (abbr, f'{name} (Liiga)') for slot, (name, abbr) in LIIGA_CLUBS.items()}


assert all(common.GAME.leagues['liiga'][1] <= s <= common.GAME.leagues['liiga'][2] for s in LIIGA_CLUBS)
assert urllib.parse
