"""Составы АХЛ 2026/27 и свободные агенты на сегодня — на готовой базе NHL Legacy (решение пользователя 10.10:
«актуализируй составы АХЛ и свободных агентов»). Составы НХЛ не меняются (как на 08.10).

Данные — кэш game/work/roster-cache (скачивает `python -m roster.ahl_ht teams|ids|players`), сопоставление слотов —
game/work/legacy-data/ahl-2026/slots.json (tools/legacy_data/ahl2026_slots.py). Сеть этот модуль не трогает.

    python -m roster.ahl2026 build --db DB --work DIR        # players.json и match.json (формат конвейера)
    python -m roster.ahl2026 write --db DB --work DIR --out OUT   # составы АХЛ и пул свободных агентов → OUT

Игроки:
- клуб АХЛ 2026/27 → его слот (slots.json); игрок с ID НХЛ — запись по карточке landing (как у конвейера), номер —
  из HockeyTech; без ID — запись по HockeyTech (рост, вес, хват, место рождения, драфт, игры АХЛ), ID свой:
  95 000 000 + ID HockeyTech;
- свободные агенты — как у `--fa` (fa.py: играли в НХЛ в 2024/25–2025/26, клуба сейчас нет, карточка и Wikipedia);
  кто в составе клуба АХЛ — не свободный агент;
- игрок, который в базе в составе клуба НХЛ (08.10), там и остаётся (НХЛ побеждает) — в отчёт.
Рейтинги — по статистике (statsrating: NHLe, три сезона) с коэффициентами калибровки 09.10 (report-ratings.md:
калибровочных рейтингов NHL 27 в кэше больше нет), у всех, без исключений для атрибутов NHL 27 в базе (11.10):
- игроки клубов АХЛ — квантили по статистике под шкалу АХЛ 2015 года по амплуа, верх — не выше 78 и 25-го
  перцентиля НХЛ (quantile_ratings);
- свободные агенты — по прошлому сезону и NHLe его лиги, с возрастом, шкала NHL 27 (fa_ratings).
Атрибуты — заново под этот OVR (ratings.Model, стиль игрока прежний), сдвиг формы — до OVR, который игра считает из
атрибутов (ovrformula; ahl2026_write включает Model.formula).
Запись — write.Writer с правками (AhlWriter): переписываются только составы клубов АХЛ (32 слота) и пул
свободных агентов; составы НХЛ, Европы, юниоров и особых команд — как были. Игроки АХЛ 2015 года, которых нет в
данных 2026/27, остаются без клуба и контракта (как ветераны этапа retire). Звенья — по рейтингу, буквы — по опыту.
"""
import argparse
import os
import statistics
import sys
from collections import Counter, defaultdict

if __package__ in (None, ''):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    __package__ = 'roster'

os.environ['NHL_GAME'] = 'legacy'
from .common import set_game as _set_game  # noqa: E402
_set_game('legacy')          # до импорта модулей конвейера: dbview, ahl, write читают игру при импорте
from . import ahl as ahl_mod  # noqa: E402
from . import build as build_mod  # noqa: E402
from . import fa as fa_mod  # noqa: E402
from . import match as match_mod  # noqa: E402
from . import sources  # noqa: E402
from . import statsrating as SR  # noqa: E402
from .common import SEASON, SEASON_YEAR, TEAM_NAMES, Paths, norm, read_json, set_game, write_json  # noqa: E402

SYNTH_HT = 95_000_000
# аббревиатуры клубов, у которых код HockeyTech совпал с чужим в базе (CGY, COL — клубы НХЛ; BEL — сборная
# Беларуси; HAM — Hamilton Bulldogs OHL)
ABBR = {'CGY': 'CGW', 'COL': 'COE', 'BEL': 'BLV', 'HAM': 'HMR'}
# коэффициенты statsrating, откалиброванные 09.10.2026 02:50 по рейтингам NHL 27 (game/work/legacy-data/roster-ahl32/
# report-ratings.md): нападающие и защитники — a, b·P, c·P², d·E, e·E·P; вратари — a, b·E, c·sv, d·E·sv
COEF = {'F': [67.939, 21.76, 1.775, 8.949, -8.967], 'D': [69.628, 22.739, -6.666, 7.949, -0.029],
        'G': [78.025, 8.374, -0.019, 3.534]}
HT_POS = {'C': 'C', 'LW': 'L', 'RW': 'R', 'L': 'L', 'R': 'R', 'W': 'L', 'F': 'C', 'D': 'D', 'LD': 'D', 'RD': 'D',
          'G': 'G'}
TEAM_BY_NAME = {norm(v): k for k, v in TEAM_NAMES.items()}
TEAM_BY_NAME.update({norm('Arizona Coyotes'): 'UTA', norm('Phoenix Coyotes'): 'UTA', norm('Utah Hockey Club'): 'UTA',
                     norm('Atlanta Thrashers'): 'WPG', norm('Mighty Ducks of Anaheim'): 'ANA'})


def legacy_dir(paths):
    return os.path.join(paths.game, 'work', 'legacy-data')


def ht_json(cache, rel):
    return read_json(os.path.join(cache, *rel.split('/')))


def sitekit(d, name):
    kit = (d or {}).get('SiteKit') or {}
    return next((v for k, v in kit.items() if k.lower() == name.lower()), []) or []


def ht_height(s):
    try:
        ft, inch = str(s).split('-')
        return int(ft) * 12 + int(inch)
    except (ValueError, AttributeError):
        return None


def ht_int(s):
    try:
        return int(str(s).strip())
    except (ValueError, TypeError):
        return None


def ht_seasons(cache, htid):
    """Сезоны АХЛ игрока из seasonstats HockeyTech в виде seasonTotals карточки landing (для statsrating)."""
    d = ht_json(cache, f'ahl/ht/player/{htid}-seasonstats.json')
    pl = ((d or {}).get('SiteKit') or {}).get('Player')
    if not isinstance(pl, dict):
        return []
    out = []
    for s in pl.get('regular') or []:
        name = s.get('season_name') or ''
        if 'Regular' not in name or s.get('career') == '0':
            continue
        y = ht_int(name[:4])
        if not y:
            continue
        row = {'season': y * 10000 + y + 1, 'leagueAbbrev': 'AHL', 'gameTypeId': 2,
               'gamesPlayed': ht_int(s.get('games_played')) or 0, 'goals': ht_int(s.get('goals')) or 0,
               'assists': ht_int(s.get('assists')) or 0, 'points': ht_int(s.get('points')) or 0,
               'pim': ht_int(s.get('penalty_minutes')) or 0, 'teamName': {'default': s.get('team_name')}}
        sv = s.get('savepct')
        if sv not in (None, '', '0.000') and s.get('saves') is not None:
            try:
                row['savePctg'] = float(sv)
            except ValueError:
                pass
        out.append(row)
    return out


def ht_draft(p):
    for d in p.get('draftinfo') or []:
        team = TEAM_BY_NAME.get(norm(d.get('draft_team')))
        y = ht_int(d.get('draft_year'))
        if team and y:
            return {'year': y, 'team': team, 'round': ht_int(d.get('draft_round')), 'pick_in_round': None,
                    'overall': ht_int(d.get('draft_rank'))}
    return None


def ht_record(e, slot, code, cache):
    """Запись игрока только по HockeyTech (ID НХЛ нет)."""
    y, m, d = (int(x) for x in (e.get('rawbirthdate') or e.get('birthdate') or f'{SEASON_YEAR - 24}-01-01').split('-'))
    city, region, country = ahl_mod.place(e.get('birthtown') or e.get('birthplace'))
    pos = HT_POS.get(str(e.get('position') or '').upper(), 'C')
    seasons = ht_seasons(cache, e['player_id'])
    pro = sum(s['gamesPlayed'] for s in seasons if s['season'] < SEASON)
    last = [s for s in seasons if s['season'] < SEASON and s['gamesPlayed'] >= 10]
    other = None
    if last:
        s = max(last, key=lambda s: (s['season'], s['gamesPlayed']))
        other = {'league': 'AHL', 'season': s['season'], 'gp': s['gamesPlayed'], 'g': s['goals'], 'a': s['assists'],
                 'pim': s['pim'], 'junior': False}
    hgt, wgt = ht_height(e.get('height')), ht_int(e.get('weight'))
    rec = {
        'nhl_id': SYNTH_HT + int(e['player_id']), 'team': code, 'slot': slot,
        'first': (e.get('first_name') or '').strip(), 'last': (e.get('last_name') or '').strip(), 'pos': pos,
        'shoots': e.get('shoots') if e.get('shoots') in ('L', 'R') else None, 'num': ht_int(e.get('tp_jersey_number')),
        'birth': [y, m, d], 'birth_city': city, 'birth_state': region, 'birth_country': country, 'nationality': country,
        'height_in': hgt or {'D': 74, 'G': 74}.get(pos, 72), 'weight_lb': wgt or {'D': 200, 'G': 190}.get(pos, 190),
        'draft': ht_draft(e), 'nhl_gp': {'career': 0, 'by_season': {}, 'regular_by_season': {}, 'debut': None},
        'pro_gp': pro, 'scoring': {'nhl': {'gp': 0, 'g': 0, 'a': 0, 'pim': 0}, **({'other': other} if other else {})},
        'rookie': build_mod.is_rookie((y, m, d), {}) and e.get('rookie') == '1', 'landing': False, 'omitted': False,
        'photo': None, 'contract': None, 'letter': None, 'ea': None, 'nhlratings': None, 'rating': None,
        'ht_only': True,
    }
    return rec, seasons


def players_2026(paths, log=print):
    """Игроки клубов АХЛ 2026/27 (по slots.json) в формате players.json и свободные агенты (fa.py)."""
    cache = paths.cache
    slots = read_json(os.path.join(legacy_dir(paths), 'ahl-2026', 'slots.json'))['slots']
    ids = (read_json(os.path.join(legacy_dir(paths), 'ahl-2026', 'ids.json')) or {}).get('players') or {}
    bios = sources.nhl_bios(cache)
    out, ht_seasons_of, moved = [], {}, []
    seen = set()
    for s in slots:
        tid = s['ht_team_id']
        s = dict(s, code=ABBR.get(s['code'], s['code']))
        roster = sitekit(ht_json(cache, f'ahl/ht/roster/94-{tid}.json'), 'Roster')
        for e in roster:
            if not isinstance(e, dict) or not e.get('player_id'):
                continue
            if str(e.get('latest_team_id') or tid) != str(tid):
                moved.append(f"{e.get('first_name')} {e.get('last_name')}: в составе {s['code']}, сейчас клуб "
                             f"{e.get('latest_team_id')}")
                continue
            htid = str(e['player_id'])
            if htid in seen:
                continue
            seen.add(htid)
            nid = (ids.get(htid) or {}).get('nhl_id')
            land = sources.nhl_landing(cache, nid) if nid else None
            if land and land.get('position') in build_mod.POS:
                le = build_mod.entry_from_landing(land)
                num = ht_int(e.get('tp_jersey_number'))
                if num:
                    le['sweaterNumber'] = num                     # номер в АХЛ
                p = build_mod.base_record(s['code'], le, land, bios.get(nid), slot=s['slot'])
                p['team'] = s['code']
            else:
                p, seasons = ht_record(e, s['slot'], s['code'], cache)
                ht_seasons_of[p['nhl_id']] = seasons
            p['ahl'] = {'club': s['code'], 'parent': s['affiliate_of'], 'nhl_contract': e.get('status') == 'NHL',
                        'contract': e.get('status'), 'ht_id': htid}
            if ahl_mod.AHL_SHIFT:
                p['ahl']['shift'] = ahl_mod.AHL_SHIFT
            p['ht_photo'] = f'photos/ahl/{htid}.jpg'
            p['rating'] = build_mod.choose_rating(p)
            out.append(p)
    on_ids = {p['nhl_id'] for p in out}
    over = read_json(os.path.join(paths.game, 'work', 'roster', 'fa-overrides.json'), {}) or {}
    fa_added, fa_dropped = fa_mod.players(cache, bios, build_mod.base_record, build_mod.entry_from_landing,
                                          sources.nhl_landing, on_ids, log, overrides=over)
    for p in fa_added:
        p['rating'] = build_mod.choose_rating(p)
    log(f'АХЛ 2026/27: игроков {len(out)} (без ID НХЛ {sum(1 for p in out if p.get("ht_only"))}); свободных агентов '
        f'{len(fa_added)} (отсеяно {len(fa_dropped)}); ушли из клуба после заявки {len(moved)}')
    return out, fa_added, fa_dropped, ht_seasons_of, moved


class FixedStats(SR.StatsModel):
    """statsrating.StatsModel с готовыми коэффициентами (без калибровки по NHL 27)."""

    def __init__(self, players, landing_of):
        self.feat = {}
        for p in players:
            land = landing_of(p)
            if land:
                self.feat[p['nhl_id']] = SR.goalie_line(land) if p['pos'] == 'G' else SR.skater_line(land)
        self.coef, self.fit_info = dict(COEF), {g: {'coef': COEF[g], 'n': 'report-ratings.md 09.10'} for g in COEF}


def stats_ratings(players, cache, ht_seasons_of, depth, log=print):
    """OVR по статистике тем, у кого рейтинга нет (как statsrating.apply для source none)."""
    from .ratings import default_ovr

    def landing_of(p):
        if p.get('ht_only'):
            return {'seasonTotals': ht_seasons_of.get(p['nhl_id']) or []}
        return sources.nhl_landing(cache, p['nhl_id'])
    model = FixedStats(players, landing_of)
    counts = Counter()
    for p in players:
        rt = p['rating']
        if rt['source'] != 'none':
            counts[f"{rt['source']}: как есть"] += 1
            continue
        est = model.estimate(p)
        p['stats'] = est
        before = {'source': 'none', 'ovr': default_ovr(p, depth)}
        if est is None:
            counts['нет статистики — оценка по амплуа'] += 1
            continue
        if p.get('ahl') and p['ahl'].get('shift'):
            est['ovr'] = round(est['ovr'] + p['ahl']['shift'], 1)
        new = int(round(est['conf'] * est['ovr'] + (1 - est['conf']) * before['ovr']))
        p['rating_before'] = before
        p['rating'] = dict(rt, ovr=new, source='stats')
        counts['по статистике'] += 1
    log(f'рейтинги: {dict(counts)}')
    return dict(counts)


AHL_BASE_ROWS = range(32, 62)        # клубы АХЛ базы — составы 2015 года (CV/HSK 224/225 — свои, 08.10)
JUNK_OVR = 40                        # OVR 36 (атрибуты 0) — 15 пустышек в клубах АХЛ базы, в шкалу не идут
G_SV = 3.0                           # вратари в квантилях: OVR на пункт переносимой разницы % отражённых с лигой
G_CAP, G_SEASON_K = 3.0, 15.0        # … разница сезона — не больше ±3 пункта, сжата по играм сезона
# верх шкалы АХЛ (координатор 11.10): лучшие — до 78 и не выше 25-го перцентиля НХЛ своего амплуа (db_depth). У АХЛ 2015
# года верх — ветераны НХЛ того времени (до 82): выше 90-го перцентиля шкала сжимается линейно до потолка
AHL_TOP, AHL_KNEE = 78, 0.9
# свободные агенты (координатор 11.10): прошлый сезон, меньше FA_MIN_GP игр в нём — три сезона statsrating; опыт E —
# игры в НХЛ того же окна / FA_EST_GP (полевые; вратари — FA_EST_GP_G); возраст: полевым старше 30, вратарям старше
# 32 — минус FA_AGE_K за год, не больше FA_AGE_MAX
FA_MIN_GP, FA_EST_GP, FA_EST_GP_G = 10, 50.0, 33.0
FA_AGE_F, FA_AGE_G, FA_AGE_K, FA_AGE_MAX = 30, 32, 1.0, 5.0


def base_ahl_ovr(v):
    """OVR игроков клубов АХЛ базы 2015 года по классам C/W/D/G (как ratings.Model.calibrate: по `team` био)."""
    from .ratings import cls
    teams = {t + 1 for t in AHL_BASE_ROWS}
    out = defaultdict(list)
    for r in range(v.nbio):
        if v.g('team', r) in teams and v.ai(r) and not v.created_slot(r):
            o = v.overall(r)
            if o > JUNK_OVR:
                out[cls({0: 'C', 1: 'L', 2: 'R', 3: 'D', 4: 'G'}[v.g('position', r)])].append(o)
    return {c: sorted(x) for c, x in out.items()}


def goalie_sv(seasons):
    """Вратарь: разница % отражённых с лигой в пунктах с переносимостью лиги (statsrating.GOALIE), по сезонам с весами
    statsrating; разница сезона — не больше ±G_CAP и сжата по играм сезона (gp / (gp + G_SEASON_K)): 2 игры в НХЛ с
    .810 не перевешивают 43 игры АХЛ с .915. → (сжатая к 0 на SR.K_SV игр разница, взвешенные игры)."""
    num = den = 0.0
    for s in seasons:
        lg, gp = SR.league(s.get('leagueAbbrev')), s.get('gamesPlayed') or 0
        if lg not in SR.GOALIE or not gp or not s.get('savePctg'):
            continue
        avg, r = SR.GOALIE[lg]
        diff = max(-G_CAP, min(G_CAP, (s['savePctg'] - avg) * 100)) * r * gp / (gp + G_SEASON_K)
        w = SR.SEASON_W[s['season']] * gp
        num += w * diff
        den += w
    return num / (den + SR.K_SV), den


def nhl_games(seasons):
    return sum(s.get('gamesPlayed') or 0 for s in seasons if SR.league(s.get('leagueAbbrev')) == 'NHL')


def quantile_ratings(players, v, cache, ht_seasons_of, log=print):
    """OVR игроков клубов АХЛ 2026/27 — квантили по статистике под распределение АХЛ 2015 года в Legacy, по амплуа
    (C/W/D/G), медиана та же (координатор 10.10, 11:45). С 11.10 — у всех игроков клубов АХЛ, без исключений для
    рейтингов 2026 года (NHL 27, CV/HSK 08.10): атрибуты NHL 27 давали игроку АХЛ OVR игры уровня НХЛ. Оценка по
    статистике (statsrating: NHLe трёх сезонов по всем лигам из seasonTotals карточки landing, у кого её нет —
    seasonstats HockeyTech; опыт в НХЛ; у вратарей — % отражённых) тянется к медиане класса по уверенности (малая
    выборка — к медиане); по ней — место в классе, OVR — того же квантиля у игроков клубов АХЛ базы (без пустышек
    OVR 36). Верх шкалы — не выше AHL_TOP и 25-го перцентиля НХЛ амплуа (db_depth): выше AHL_KNEE шкала сжимается
    линейно до потолка. Считается по всем 32 клубам: у игрока одна оценка в out и out-ahl32. → сводка для players.json."""
    import math
    import zlib
    from .ratings import cls

    def landing_of(p):
        if p.get('ht_only'):
            return {'seasonTotals': ht_seasons_of.get(p['nhl_id']) or []}
        return sources.nhl_landing(cache, p['nhl_id'])
    base = base_ahl_ovr(v)
    depth = db_depth(v)
    pop = [p for p in players if p.get('ahl')]
    model = FixedStats(pop, landing_of)
    by = defaultdict(list)
    for p in pop:
        by[cls(p['pos'])].append(p)

    def goalie_est(p):
        """Вратарь: у модели statsrating почти весь вес — на играх в НХЛ (коэффициент % отражённых ≈ 0), и вратари
        без НХЛ шли бы в случайном порядке. Здесь — опыт в НХЛ (тот же коэффициент) и % отражённых (goalie_sv):
        G_SV OVR на пункт разницы с лигой."""
        land = landing_of(p)
        if not land:
            return None
        seasons = list(SR._regular(land))
        sv, den = goalie_sv(seasons)
        e = min(1.0, nhl_games(seasons) / SR.EST_GP_G)
        return {'ovr': COEF['G'][0] + COEF['G'][1] * e + G_SV * sv, 'conf': round(den / (den + SR.K_CONF_G), 2)}
    out = {}
    for c, ps in sorted(by.items()):
        est = {p['nhl_id']: (goalie_est(p) if c == 'G' else model.estimate(p)) for p in ps}
        known = [e['ovr'] for e in est.values() if e]
        med = statistics.median(known) if known else 0.0
        score = {}
        for p in ps:
            e = est[p['nhl_id']]
            score[p['nhl_id']] = med if e is None else e['conf'] * e['ovr'] + (1 - e['conf']) * med
        order = sorted(ps, key=lambda p: (score[p['nhl_id']], zlib.crc32(str(p['nhl_id']).encode())))
        b, n = base[c], len(order)
        knee, top = b[min(len(b) - 1, int(AHL_KNEE * len(b)))], b[-1]
        cap = min(AHL_TOP, depth.get(c, AHL_TOP))
        for i, p in enumerate(order):
            pos = min(len(b) - 1.0, max(0.0, (i + 0.5) / n * len(b) - 0.5))
            lo = int(math.floor(pos))
            hi = min(len(b) - 1, lo + 1)
            x = b[lo] + (b[hi] - b[lo]) * (pos - lo)
            if top > cap > knee and x > knee:
                x = knee + (x - knee) * (cap - knee) / (top - knee)
            ovr = int(round(x))
            e = est[p['nhl_id']]
            p['rating_stats'] = {k: p['rating'].get(k) for k in ('source', 'ovr') if k in p['rating']}
            p.setdefault('rating_before', {'source': p['rating']['source'], 'ovr': p['rating'].get('ovr')})   # write.notes
            p['rating'] = {'source': 'stats', 'ovr': ovr, 'attrs': {}, 'scale': 'ahl-quantile',
                           'score': round(score[p['nhl_id']], 2), 'quantile': round((i + 0.5) / n, 3),
                           'conf': e['conf'] if e else 0.0}
        res = sorted(p['rating']['ovr'] for p in ps)
        out[c] = {'n': n, 'base_n': len(b), 'median_est': round(med, 1),
                  'ovr': [b[0], statistics.median(b), b[-1]], 'knee': knee, 'cap': cap,
                  'result': [res[0], statistics.median(res), res[-1]]}
    log(f"квантили АХЛ 2015: {sum(v_['n'] for v_ in out.values())} игроков; "
        + ', '.join(f"{c}: {v_['n']} → шкала {v_['base_n']} (медиана {v_['ovr'][1]}, верх {v_['ovr'][2]} → "
                    f"{v_['result'][2]})" for c, v_ in out.items()))
    return out


def fa_ratings(players, cache, log=print):
    """OVR свободных агентов (координатор 11.10): по статистике прошлого сезона (2025/26) и NHLe той лиги, где игрок
    играл (НХЛ, АХЛ, КХЛ, SHL…), — модель statsrating с коэффициентами COEF (шкала NHL 27, как у составов НХЛ), с
    возрастом. Меньше FA_MIN_GP игр в прошлом сезоне (травма, без клуба) — три сезона с весами statsrating. Опыт E —
    игры в НХЛ того же окна: в прошлом сезоне / FA_EST_GP (вратари — / FA_EST_GP_G), за три сезона — как в
    statsrating. Вратари — опыт и % отражённых (goalie_sv). Возраст: полевым старше FA_AGE_F, вратарям старше FA_AGE_G
    — минус FA_AGE_K за год, не больше FA_AGE_MAX. Атрибуты потом — под этот OVR формулой игры (ovrformula), без
    поправки на лигу. → сводка."""
    from .ratings import age
    last = SEASON - 10001
    rows = []
    for p in players:
        if not p.get('fa'):
            continue
        seasons = list(SR._regular(sources.nhl_landing(cache, p['nhl_id']) or {}))
        known = SR.GOALIE if p['pos'] == 'G' else SR.NHLE       # игры лиг, по которым есть оценка
        gp_last = sum(s.get('gamesPlayed') or 0 for s in seasons
                      if s['season'] == last and SR.league(s.get('leagueAbbrev')) in known)
        one = gp_last >= FA_MIN_GP
        window = [s for s in seasons if s['season'] == last] if one else seasons
        a = age(p['birth'])
        if p['pos'] == 'G':
            sv, _ = goalie_sv(window)
            e = min(1.0, nhl_games(window) / (FA_EST_GP_G if one else SR.EST_GP_G))
            est = COEF['G'][0] + COEF['G'][1] * e + G_SV * sv
            adj = -min(FA_AGE_MAX, FA_AGE_K * max(0, a - FA_AGE_G))
            info = {'sv': round(sv, 2)}
        else:
            f = SR.skater_line({'seasonTotals': window})
            g = SR.group(p)
            P = (f['num'] + SR.K_SHRINK * SR.P0[g]) / (f['den'] + SR.K_SHRINK)
            e = min(1.0, nhl_games(window) / (FA_EST_GP if one else SR.EST_GP))
            est = sum(k * x for k, x in zip(COEF[g], [1.0, P, P * P, e, e * P]))
            adj = -min(FA_AGE_MAX, FA_AGE_K * max(0, a - FA_AGE_F))
            info = {'P': round(P, 3)}
        ovr = int(round(est + adj))
        p.setdefault('rating_before', {'source': p['rating']['source'], 'ovr': p['rating'].get('ovr')})
        p['rating'] = {'source': 'stats', 'ovr': ovr, 'attrs': {}, 'scale': 'fa-stats', 'est': round(est, 1),
                       'age': a, 'age_adj': adj, 'E': round(e, 2), 'window': '2025/26' if one else '3 сезона',
                       'lines': [f"{s.get('leagueAbbrev')} {SR._season(s['season'])} {s.get('gamesPlayed')}"
                                 for s in window], **info}
        rows.append((ovr, f"{p['first']} {p['last']}"))
    rows.sort(reverse=True)
    one = sum(1 for p in players if p.get('fa') and p['rating'].get('window') == '2025/26')
    log(f'свободные агенты: {len(rows)} по статистике (прошлый сезон — {one}); '
        + (f'OVR {rows[-1][0]}–{rows[0][0]}, медиана {statistics.median(o for o, _ in rows)}; первые: '
           + ', '.join(f'{n} {o}' for o, n in rows[:5]) if rows else '—'))
    return {'n': len(rows), 'last_season': one, 'ovr': [o for o, _ in rows]}


def db_depth(v):
    """25-й перцентиль OVR игроков составов НХЛ базы по амплуа (как ratings.depth_of по игрокам NHL 27)."""
    from .dbview import NHL
    from .ratings import cls
    ovr = defaultdict(list)
    for e in v.entries:
        if e['team'] not in NHL:
            continue
        r = v.row_of_gid.get(v.link_gid.get(e['playerindex']))
        if r is None or not v.ai(r):
            continue
        pos = {0: 'C', 1: 'L', 2: 'R', 3: 'D', 4: 'G'}[v.g('position', r)]
        ovr[cls(pos)].append(v.overall(r))
    return {c: sorted(x)[len(x) // 4] for c, x in ovr.items() if x}


ROSTER_MAX = 30
STATUS_RANK = {'PTO': 0, 'ATO': 0, 'None': 0, None: 0, 'AHL': 1, 'NHL': 2}


def trim_rosters(players, log=print):
    """Клуб АХЛ больше ROSTER_MAX игроков → лишние уходят из состава: сначала на просмотре (PTO/ATO), потом с
    контрактом АХЛ, потом НХЛ — у каждого по возрастанию OVR; минимум остаётся 13 нападающих, 7 защитников, 2 вратаря."""
    by = defaultdict(list)
    for p in players:
        if p.get('ahl'):
            by[p['slot']].append(p)
    out = []
    kind = lambda p: 'G' if p['pos'] == 'G' else 'D' if p['pos'] == 'D' else 'F'
    need = {'F': 13, 'D': 7, 'G': 2}
    for slot, tp in sorted(by.items()):
        if len(tp) <= ROSTER_MAX:
            continue
        have = Counter(kind(p) for p in tp)
        order = sorted(tp, key=lambda p: (STATUS_RANK.get(p['ahl'].get('contract'), 1), p['rating'].get('ovr') or 0,
                                          p['nhl_id']))
        n = len(tp)
        for p in order:
            if n <= ROSTER_MAX:
                break
            if have[kind(p)] <= need[kind(p)]:
                continue
            have[kind(p)] -= 1
            n -= 1
            out.append({'nhl_id': p['nhl_id'], 'name': f"{p['first']} {p['last']}", 'team': p['team'], 'pos': p['pos'],
                        'ovr': p['rating'].get('ovr'), 'contract': p['ahl'].get('contract')})
    if out:
        log(f'составы больше {ROSTER_MAX}: убрано {len(out)} — ' + ', '.join(f"{t['team']} {t['name']} ({t['contract']})"
                                                                         for t in out[:8]))
    return out


def cmd_build(a, paths, log=print):
    from .dbview import NHL, View
    players, fa_added, fa_dropped, ht_seasons_of, moved = players_2026(paths, log)
    db, _ = match_mod.load_db(paths, a.db)
    v = View(db)
    idx = match_mod.index(v)
    allp = players + fa_added
    found = {p['nhl_id']: match_mod.match_one(v, idx, p) for p in allp}
    by_row = defaultdict(list)
    for pid, (row, how) in found.items():
        if row is not None:
            by_row[row].append(pid)
    conflicts = []
    for row, pids in by_row.items():
        if len(pids) > 1:
            pids.sort(key=lambda pid: match_mod.HOW_RANK[found[pid][1]])
            for pid in pids[1:]:
                conflicts.append({'nhl_id': pid, 'row': row, 'kept': pids[0]})
                found[pid] = (None, 'conflict')
    # НХЛ побеждает: игрок в составе клуба НХЛ базы (08.10) остаётся там
    nhl_wins, keep = [], []
    for p in allp:
        row = found[p['nhl_id']][0]
        if row is not None and any(t in NHL for t in v.teams_of[row]):
            nhl_wins.append({'name': f"{p['first']} {p['last']}", 'nhl_id': p['nhl_id'],
                             'where': 'FA' if p.get('fa') else p['team'],
                             'nhl': [t for t in v.teams_of[row] if t in NHL]})
            continue
        keep.append(p)
    # рейтинги — по статистике у всех (11.10: и у тех, чьи атрибуты в базе уже NHL 27): оценка для урезания составов,
    # потом квантили АХЛ и оценка свободных агентов
    stats = stats_ratings(keep, paths.cache, ht_seasons_of, db_depth(v), log)
    trimmed = trim_rosters(keep, log)
    keep = [p for p in keep if p['nhl_id'] not in {t['nhl_id'] for t in trimmed}]
    quant = quantile_ratings(keep, v, paths.cache, ht_seasons_of, log)       # по всем 32 клубам — и для out
    fa = fa_ratings(keep, paths.cache, log)
    if not a.ahl32:
        keep = [p for p in keep if p.get('slot') not in (224, 225)]          # без --ahl32 в базе нет CV/HSK
    keep.sort(key=lambda p: (999 if p['slot'] is None else p['slot'],
                             {'C': 0, 'L': 1, 'R': 2, 'D': 3, 'G': 4}[p['pos']], p['last'], p['first']))
    os.makedirs(paths.work, exist_ok=True)
    write_json(paths.players, {'meta': {'season': SEASON, 'source': 'HockeyTech АХЛ 2026/27 + fa.py', 'db': a.db,
                                        'nhl_wins': nhl_wins, 'fa_dropped': fa_dropped, 'moved': moved, 'trimmed': trimmed,
                                        'stats': stats, 'quantiles': quant, 'fa_ratings': fa},
                               'players': keep})
    out = {}
    for p in keep:
        row, how = found[p['nhl_id']]
        rec = {'row': row, 'how': how, 'name': f"{p['first']} {p['last']}", 'team': p['team']}
        if row is not None:
            rec.update({'db_name': v.name(row), 'db_birth': list(v.birth(row)), 'db_teams': v.teams_of[row],
                        'db_artid': v.g('artid', row), 'db_overall': v.overall(row)})
        out[str(p['nhl_id'])] = rec
    write_json(paths.matched, {'db': a.db, 'counts': dict(Counter(r['how'] for r in out.values())),
                               'conflicts': conflicts, 'players': out})
    log(f"build: в players.json {len(keep)} (АХЛ {sum(1 for p in keep if not p.get('fa'))}, свободных агентов "
        f"{sum(1 for p in keep if p.get('fa'))}); сопоставлено с базой {sum(1 for r in out.values() if r['row'] is not None)}; "
        f"НХЛ побеждает — {len(nhl_wins)}")
    return keep


def register_clubs(paths):
    """Клубы АХЛ слотов — в common.AHL_CLUBS (только в памяти этого процесса): club_abbr и club_name конвейера знают
    лишь клубы НХЛ, CV/HSK и лиг (--league)."""
    from . import common
    for s in read_json(os.path.join(legacy_dir(paths), 'ahl-2026', 'slots.json'))['slots']:
        common.AHL_CLUBS.setdefault(s['slot'], {'abbr': ABBR.get(s['code'], s['code']), 'name': s['name'], 'wiki': None,
                                                'parent': s['affiliate_of'], 'parent_nick': ''})


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('stage', choices=['build', 'write'])
    ap.add_argument('--db', required=True, help='готовая база (out или out-ahl32)')
    ap.add_argument('--work', required=True, help='папка players.json, match.json, write.json')
    ap.add_argument('--out', help='write: выходная база')
    ap.add_argument('--ahl32', action='store_true', help='база --ahl32 (CV/HSK на 224/225)')
    a = ap.parse_args()
    set_game('legacy')
    paths = Paths(None, a.work)
    paths.db_in = os.path.abspath(a.db)
    if a.stage == 'build':
        cmd_build(a, paths)
    else:
        from .ahl2026_write import run_write
        register_clubs(paths)
        paths.db_out = os.path.abspath(a.out or a.db)
        # artid новых игроков — общие у out и out-ahl32 (портреты лежат по artid)
        paths.registry = os.path.join(legacy_dir(paths), 'ahl-2026', 'artid-registry.json')
        paths.fa = True
        paths.fa_only = True
        paths.skin = True                 # голова под тон кожи по фото (кадры НХЛ — до записи, ht_photos)
        paths.retire_veterans = 2010
        run_write(paths)


if __name__ == '__main__':
    main()
