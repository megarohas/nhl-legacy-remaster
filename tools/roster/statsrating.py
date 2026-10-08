"""Рейтинг по статистике (`--stats-ratings`): OVR шкалы NHL 27 из результативности последних трёх
сезонов в любой лиге — с NHL-эквивалентами лиг (NHLe), амплуа и опытом в НХЛ; калибровка — по
рейтингам NHL 27 (EA и nhlratings.net) игроков тех же составов.

Источник статистики — карточка api-web.nhle.com `/v1/player/{id}/landing` (`seasonTotals`: каждый
сезон каждого клуба в любой лиге — НХЛ, АХЛ, КХЛ, SHL, Liiga, NCAA, OHL…), она уже в кэше у всех
игроков с ID НХЛ. Берётся регулярный чемпионат (`gameTypeId` 2) сезонов 2023/24–2025/26, турниры
сборных и кубки — нет.

Полевые: «производительность» P — очки за игру, переведённые в НХЛ (очки × NHLe лиги), среднее по
играм с весами сезонов 1 / 0,6 / 0,35 (свежий — тяжелее), со «сжатием» к уровню запасного (20
взвешенных игр с P0: нападающий 0,22, защитник 0,12). Опыт E = игры в НХЛ за три сезона / 150 (не
больше 1). OVR = a + b·P + c·P² + d·E + e·E·P — отдельно для нападающих и защитников, коэффициенты —
наименьшие квадраты по игрокам с рейтингом NHL 27 (у новичков EA ставит меньше, чем ветерану с той
же результативностью: это и есть член d·E).
Вратари: процент отражённых минус средний по лиге, с переносимостью лиги (АХЛ 0,6, КХЛ 0,6, …),
сжатие к 0 на 40 игр; OVR = a + b·E + c·sv + d·E·sv (E = игры в НХЛ / 100).

Как сочетается с имеющимися рейтингами (`apply`):
- EA (топ-300, все атрибуты) и nhlratings.net с атрибутами — не трогаются;
- только OVR nhlratings.net/EA: у игрока со 100+ играми в НХЛ за три сезона — как есть, у остальных
  — смесь `nr + w·(оценка − nr)`, w = 0,5·уверенность (у вратарей 0,25·уверенность: модель вратарей
  слабее);
- рейтинга нет — `уверенность·оценка + (1 − уверенность)·прежняя оценка` (прежняя — 25-й
  перцентиль амплуа ± возраст, у АХЛ — уровень АХЛ: ratings.default_ovr).
Уверенность = игры / (игры + 25), игры — взвешенные, только лиги с NHLe ≥ 0,2 (взрослые, NCAA,
CHL, USHL); у вратарей — игры / (игры + 30).
Обоснование коэффициентов лиг — docs/roster-expansion.md.
"""
import statistics
from collections import defaultdict

from .common import SEASON
from .ratings import default_ovr, depth_of

SEASON_W = {SEASON - 10001: 1.0, SEASON - 20002: 0.6, SEASON - 30003: 0.35}

# NHLe полевых: очки в НХЛ на одно очко в лиге. Консенсус опубликованных таблиц и своей проверки по
# переходам «лига → НХЛ в следующем сезоне» у игроков нынешних составов (docs/roster-expansion.md).
NHLE = {
    'NHL': 1.0,
    # Европа, взрослые
    'KHL': 0.65, 'SHL': 0.62, 'NL': 0.52, 'Czechia': 0.45, 'Liiga': 0.45, 'DEL': 0.40,
    'HockeyAllsvenskan': 0.30, 'VHL': 0.30, 'Slovakia': 0.30, 'ICEHL': 0.33, 'Mestis': 0.18, 'SL': 0.20,
    'DEL2': 0.20, 'Czechia2': 0.22, 'Norway': 0.20, 'Denmark': 0.20, 'Ligue Magnus': 0.20, 'Belarus': 0.20,
    'Latvia': 0.15, 'AlpsHL': 0.15,
    # Северная Америка, взрослые
    'AHL': 0.50, 'ECHL': 0.22,
    # студенты и юниоры
    'NCAA': 0.40, 'USports': 0.20,
    'OHL': 0.28, 'WHL': 0.27, 'QMJHL': 0.24, 'USHL': 0.22, 'NTDP': 0.22,
    'MHL': 0.13, 'J20 Nationell': 0.11, 'U20 SM-sarja': 0.11, 'Czechia U20': 0.08, 'BCHL': 0.10, 'NAHL': 0.08,
    'AJHL': 0.08, 'OJHL': 0.07, 'SJHL': 0.07, 'MJHL': 0.07, 'CCHL': 0.07, 'DNL': 0.05,
}
# прежние и другие названия лиг в seasonTotals
ALIAS = {
    'Sweden': 'SHL', 'SEL': 'SHL', 'Finland': 'Liiga', 'SM-liiga': 'Liiga', 'Russia': 'KHL', 'Rus-KHL': 'KHL',
    'Czech': 'Czechia', 'CzRep': 'Czechia', 'Swiss': 'NL', 'NLA': 'NL', 'Germany': 'DEL', 'Austria': 'ICEHL',
    'EBEL': 'ICEHL', 'Sweden-2': 'HockeyAllsvenskan', 'Allsvenskan': 'HockeyAllsvenskan', 'Finland-2': 'Mestis',
    'Russia-2': 'VHL', 'Russia-Jr.': 'MHL', 'Swiss-2': 'SL', 'NLB': 'SL', 'Czech2': 'Czechia2', 'CzRep-2': 'Czechia2',
    'Slovakia2': None, 'Slovak-2': None,
    'H-East': 'NCAA', 'WCHA': 'NCAA', 'CCHA': 'NCAA', 'ECAC': 'NCAA', 'NCHC': 'NCAA', 'Big Ten': 'NCAA',
    'AH': 'NCAA', 'CHA': 'NCAA',
    'USDP': 'NTDP', 'USNTDP': 'NTDP', 'U-18': 'NTDP', 'U-17': 'NTDP',
    'J20 SuperElit': 'J20 Nationell', 'SuperElit': 'J20 Nationell', 'Swe-Jr.': 'J20 Nationell',
    'U20 Nationell': 'J20 Nationell', 'Fin-Jr.': 'U20 SM-sarja', 'Jr. A SM-liiga': 'U20 SM-sarja',
    'U20 SM-liiga': 'U20 SM-sarja', 'CzRep-Jr.': 'Czechia U20', 'Czech U20': 'Czechia U20', 'ON-Jr.A': 'OJHL',
    'OPJHL': 'OJHL',
}
CONF_MIN = 0.2              # лиги с NHLe ниже — в оценку идут, но уверенности не добавляют
# вратари: (средний % отражённых в лиге 2021–2026 — оценка по опубликованной статистике лиг, доля
# разницы, переносимая в НХЛ)
GOALIE = {
    'NHL': (0.903, 1.0), 'AHL': (0.906, 0.6), 'ECHL': (0.900, 0.35), 'KHL': (0.917, 0.6), 'SHL': (0.912, 0.55),
    'Liiga': (0.913, 0.5), 'NL': (0.910, 0.5), 'DEL': (0.908, 0.45), 'Czechia': (0.915, 0.45),
    'NCAA': (0.907, 0.45), 'OHL': (0.892, 0.35), 'WHL': (0.897, 0.35), 'QMJHL': (0.890, 0.35),
    'USHL': (0.900, 0.3), 'NTDP': (0.900, 0.3), 'HockeyAllsvenskan': (0.910, 0.4), 'VHL': (0.915, 0.4),
    'MHL': (0.915, 0.25), 'J20 Nationell': (0.905, 0.25), 'U20 SM-sarja': (0.905, 0.25), 'Mestis': (0.905, 0.3),
    'ICEHL': (0.908, 0.4), 'Slovakia': (0.910, 0.35),
}
K_SHRINK, P0 = 20.0, {'F': 0.22, 'D': 0.12}
K_CONF, K_CONF_G, K_SV = 25.0, 30.0, 40.0
EST_GP, EST_GP_G = 150.0, 100.0          # игры в НХЛ за три сезона, после которых опыт E = 1
ESTABLISHED = 100                        # столько игр в НХЛ за три сезона — рейтинг NHL 27 не смешивается
CALIBRATE = ('ea', 'nhlratings', 'nhlratings-ovr', 'ea-ovr')


def league(abbr):
    return ALIAS.get(abbr, abbr)


def group(p):
    return 'G' if p['pos'] == 'G' else 'D' if p['pos'] == 'D' else 'F'


def _season(s):
    return f"{str(s)[2:4]}/{str(s)[6:8]}"


def _regular(land):
    """Регулярные чемпионаты трёх сезонов; одинаковые строки (клуб, сезон, игры, очки) — один раз:
    в карточках бывает повтор (J20 Nationell 2023/24 у Антона Йоханссона дважды)."""
    seen = set()
    for s in land.get('seasonTotals') or []:
        if s.get('gameTypeId') != 2 or s.get('season') not in SEASON_W:
            continue
        key = (s['season'], s.get('leagueAbbrev'), (s.get('teamName') or {}).get('default'), s.get('gamesPlayed'),
               s.get('goals'), s.get('assists'), s.get('savePctg'))
        if key in seen:
            continue
        seen.add(key)
        yield s


def skater_line(land):
    """Признаки полевого за три сезона: P (NHLe очков за игру, без сжатия: num/den), взвешенные игры
    (все и только «весомых» лиг), игры в НХЛ, строки по лигам для отчёта."""
    num = den = den_conf = 0.0
    nhl_gp, lines = 0, []
    for s in _regular(land):
        lg, gp = league(s.get('leagueAbbrev')), s.get('gamesPlayed') or 0
        if lg == 'NHL':
            nhl_gp += gp
        f = NHLE.get(lg)
        if f is None or not gp or s.get('points') is None:
            continue
        w = SEASON_W[s['season']] * gp
        num += w * f * s['points'] / gp
        den += w
        if f >= CONF_MIN:
            den_conf += w
        lines.append(f"{lg} {_season(s['season'])} {gp}-{s.get('goals') or 0}-{s.get('assists') or 0}")
    return {'num': num, 'den': den, 'den_conf': den_conf, 'nhl_gp': nhl_gp, 'lines': lines}


def goalie_line(land):
    """Признаки вратаря: взвешенная разница % отражённых с лигой (с переносимостью лиги), игры."""
    num = den = 0.0
    nhl_gp, lines = 0, []
    for s in _regular(land):
        lg, gp = league(s.get('leagueAbbrev')), s.get('gamesPlayed') or 0
        if lg == 'NHL':
            nhl_gp += gp
        if lg not in GOALIE or not gp or not s.get('savePctg'):
            continue
        avg, r = GOALIE[lg]
        w = SEASON_W[s['season']] * gp
        num += w * r * (s['savePctg'] - avg) * 100       # в процентных пунктах
        den += w
        lines.append(f"{lg} {_season(s['season'])} {gp} игр, {s['savePctg']:.3f}")
    return {'num': num, 'den': den, 'den_conf': den, 'nhl_gp': nhl_gp, 'lines': lines}


def _lstsq(X, y, w=None, ridge=1e-3):
    """Взвешенные наименьшие квадраты (нормальные уравнения, Гаусс); ridge — кроме свободного члена."""
    n = len(X[0])
    A = [[0.0] * n for _ in range(n)]
    b = [0.0] * n
    for row, t, wt in zip(X, y, w or [1.0] * len(X)):
        for i in range(n):
            ri = row[i] * wt
            b[i] += ri * t
            for j in range(n):
                A[i][j] += ri * row[j]
    for i in range(1, n):
        A[i][i] += ridge
    M = [A[i][:] + [b[i]] for i in range(n)]
    for c in range(n):
        piv = max(range(c, n), key=lambda r: abs(M[r][c]))
        M[c], M[piv] = M[piv], M[c]
        pv = M[c][c]
        M[c] = [x / pv for x in M[c]]
        for r in range(n):
            if r != c and M[r][c]:
                f = M[r][c]
                M[r] = [x - f * y_ for x, y_ in zip(M[r], M[c])]
    return [M[i][n] for i in range(n)]


class StatsModel:
    """Признаки всех игроков с карточкой landing и модель OVR по ним (fit — на игроках с рейтингом)."""

    def __init__(self, players, landing):
        self.feat = {}
        for p in players:
            if p.get('league'):                      # клуб лиги (--league): сезоны с сайта лиги
                land = {'seasonTotals': p['league'].get('seasons') or []}
            else:
                land = landing(p['nhl_id']) if p.get('landing', True) and not p.get('wiki_only') else None
            if not land:
                continue
            self.feat[p['nhl_id']] = goalie_line(land) if p['pos'] == 'G' else skater_line(land)
        self.coef, self.fit_info = {}, {}
        for g in 'FDG':
            rows = [p for p in players if group(p) == g and p['nhl_id'] in self.feat
                    and p['rating']['source'] in CALIBRATE and p['rating']['ovr']]
            X = [self.x(p) for p in rows]
            y = [p['rating']['ovr'] for p in rows]
            # nhlratings.net у вратарей расходится с EA чаще (сверка: |разница| ≥ 3 у 12 из 26) — вес меньше
            wts = [1.0 if p['rating']['source'].startswith('ea') or g != 'G' else 0.7 for p in rows]
            self.coef[g] = _lstsq(X, y, wts)
            pred = [self.raw(p) for p in rows]
            err = [a - b for a, b in zip(pred, y)]
            low = [e for e, p in zip(err, rows) if self.feat[p['nhl_id']]['nhl_gp'] < 40]
            self.fit_info[g] = {'n': len(rows), 'mae': round(statistics.mean(abs(e) for e in err), 2) if err else None,
                                'n_rookies': len(low),
                                'mae_rookies': round(statistics.mean(abs(e) for e in low), 2) if low else None,
                                'coef': [round(c, 3) for c in self.coef[g]]}

    def P(self, p):
        f = self.feat[p['nhl_id']]
        g = group(p)
        return (f['num'] + K_SHRINK * P0[g]) / (f['den'] + K_SHRINK)

    def x(self, p):
        f = self.feat[p['nhl_id']]
        if p['pos'] == 'G':
            sv = f['num'] / (f['den'] + K_SV)
            e = min(1.0, f['nhl_gp'] / EST_GP_G)
            return [1.0, e, sv, e * sv]
        P = self.P(p)
        e = min(1.0, f['nhl_gp'] / EST_GP)
        return [1.0, P, P * P, e, e * P]

    def raw(self, p):
        return sum(a * b for a, b in zip(self.x(p), self.coef[group(p)]))

    def estimate(self, p):
        """{'ovr': оценка, 'conf': 0…1, 'P'/'sv', 'nhl_gp', 'lines'} или None (нет карточки)."""
        if p['nhl_id'] not in self.feat:
            return None
        f = self.feat[p['nhl_id']]
        k = K_CONF_G if p['pos'] == 'G' else K_CONF
        out = {'ovr': round(self.raw(p), 1), 'conf': round(f['den_conf'] / (f['den_conf'] + k), 2),
               'nhl_gp': f['nhl_gp'], 'lines': f['lines']}
        if p['pos'] == 'G':
            out['sv'] = round(f['num'] / (f['den'] + K_SV), 2)
        else:
            out['P'] = round(self.P(p), 3)
        return out


def apply(players, landing, log=print, only=None):
    """Рейтинг по статистике в players.json: p['stats'] — оценка и признаки, p['rating_before'] —
    рейтинг до правки; p['rating'] меняется по правилам из шапки модуля. Возвращает сводку."""
    depth = depth_of(players)                 # прежняя оценка «нет рейтинга» — как в ratings.Model
    model = StatsModel(players, landing)
    counts = defaultdict(int)
    for p in players:
        if only and not only(p):
            continue
        rt = p['rating']
        est = model.estimate(p)
        p['stats'] = est
        if est is None:
            counts['нет карточки — как было'] += 1
            continue
        src = rt['source']
        before = {'source': src, 'ovr': rt['ovr'] if rt['ovr'] else default_ovr(p, depth)}
        conf = est['conf']
        if src in ('ea', 'nhlratings'):
            counts[f'{src}: как есть'] += 1
            continue
        if src in ('nhlratings-ovr', 'ea-ovr'):
            if est['nhl_gp'] >= ESTABLISHED:
                counts[f'{src}: 100+ игр в НХЛ — как есть'] += 1
                continue
            w = (0.25 if p['pos'] == 'G' else 0.5) * conf
            new = int(round(rt['ovr'] + w * (est['ovr'] - rt['ovr'])))
            if new == rt['ovr']:
                counts[f'{src}: смесь — без изменений'] += 1
                continue
            p['rating_before'] = before
            p['rating'] = dict(rt, ovr=new, source=f'{src}+stats')
            counts[f'{src}: смесь с оценкой'] += 1
            continue
        # рейтинга нет: оценка по статистике, при малой уверенности — ближе к прежней
        if p.get('league') and p['pos'] == 'G':
            # вратари лиги: модель вратарей НХЛ держится на опыте в НХЛ — здесь уровень лиги + % отражённых
            # (sv — разница с лигой × переносимость 0,5; 3 OVR на пункт переносимой разницы, не больше ±5)
            est['ovr'] = round(p['league']['level'] + max(-5.0, min(5.0, 3.0 * est.get('sv', 0.0))), 1)
        elif p.get('league') and p['league'].get('shift'):
            # NHL Legacy: лиги вне НХЛ в её шкале ниже, чем в NHL 13 (league.SHIFT) — оценка сдвигается
            est['ovr'] = round(est['ovr'] + p['league']['shift'], 1)
        new = int(round(conf * est['ovr'] + (1 - conf) * before['ovr']))
        p['rating_before'] = before
        p['rating'] = dict(rt, ovr=new, source='stats')
        counts['нет рейтинга: по статистике'] += 1
    changed = [p for p in players if p.get('rating_before')]
    log(f"stats-ratings: {len(model.feat)} игроков с карточкой; модель — "
        + ', '.join(f"{g}: n={i['n']} MAE {i['mae']} (новички {i['n_rookies']}: {i['mae_rookies']})"
                    for g, i in model.fit_info.items())
        + f"; изменено {len(changed)}")
    return {'fit': model.fit_info, 'counts': dict(counts), 'changed': len(changed),
            'nhle': NHLE, 'season_weights': {str(k): v for k, v in SEASON_W.items()}}
