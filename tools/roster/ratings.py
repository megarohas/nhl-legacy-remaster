"""Рейтинги NHL 27 для exhibitionskaterai / exhibitiongoalieai (хранится значение − 36, 6 бит).

- Атрибуты EA (ea.com, топ-300) и nhlratings.net переносятся один в один по названиям
  (Angles → g_positioning). Недостающие поля — по «форме» игрока: у сопоставленного — его
  атрибуты из базы, у нового — медианная форма игроков NHL 27 того же амплуа (C, W, D, G),
  сдвинутая к уровню известных атрибутов.
- Только OVR (nhlratings.net): форма сдвигается, пока «уровень» (среднее атрибутов) плюс
  поправка амплуа не даст OVR; поправка = медиана (OVR − среднее атрибутов) у игроков EA
  (как `ratings.overall_offset` в puckpeak, MIT).
- Ни EA, ни nhlratings.net: OVR = 25-й перцентиль своего амплуа среди игроков НХЛ 2026/27
  с рейтингом ± возраст (молодым −2) — по смыслу формулы estimate.py из puckpeak (медиана
  НХЛ + поправки), без разрывов лиг: все игроки здесь — из составов НХЛ.
- p_overall / g_overall = OVR NHL 27; p_potential — как в исходной базе: 30 до 21 года
  включительно, иначе 5; стиль — с nhlratings.net, иначе прежний (того же класса F/D), по
  результативности или ближайший по форме атрибутов «центроид» стиля из исходной базы.
  g_consistency (в NHL 27 его нет) — не рейтинг: в базе 0–2, не меняется.
"""
import statistics
import zlib
from collections import defaultdict

from .common import SEASON_YEAR
from .dbview import B, G, S

SK = ['p_deking', 'p_handeye', 'p_passing', 'p_puckcontrol', 'p_slapaccuracy', 'p_slapshotpower', 'p_wristaccuracy',
      'p_wristshotpower', 'p_acceleration', 'p_agility', 'p_balance', 'p_endurance', 'p_speed', 'p_discipline',
      'p_offawareness', 'p_poise', 'p_defawareness', 'p_faceoffs', 'p_shotblocking', 'p_stickchecking',
      'p_aggression', 'p_bodychecking', 'p_durability', 'p_fightingskill', 'p_strength']
GK = ['g_gsh', 'g_gsl', 'g_ssh', 'g_ssl', 'g_5hole', 'g_pokecheck', 'g_positioning', 'g_reboundcontrol', 'g_breakaway',
      'g_puckplayfrequency', 'g_aggression', 'g_vision', 'g_shotrecover', 'g_agility', 'g_speed', 'g_endurance',
      'g_durability', 'g_passing', 'g_poise']
BASE = 36
SK_BIAS = ['off_defbias', 'pass_carrybias', 'shoot_passbias', 'p_fighting']
TRAITS = [f'trait{i}' for i in range(32)]
D_STYLES, F_STYLES = (1, 2, 3, 4), (5, 6, 7, 8, 9, 10)


def cls(pos):
    return {'C': 'C', 'L': 'W', 'R': 'W', 'D': 'D', 'G': 'G'}[pos]


def fields_of(pos):
    return GK if pos == 'G' else SK


def clamp_rating(v):
    return max(BASE, min(BASE + 63, int(round(v))))


def age(birth):
    y, m, d = birth
    return SEASON_YEAR - y - ((m, d) > (9, 15))


def _median(xs, default=None):
    xs = [x for x in xs if x is not None]
    return statistics.median(xs) if xs else default


class Model:
    def __init__(self, v, players):
        self.v = v
        db = v.db
        # форма NHL 27 по амплуа: медианы атрибутов игроков с полным набором
        samples = defaultdict(list)
        for p in players:
            rt = p['rating']
            fs = fields_of(p['pos'])
            if rt['source'] in ('ea', 'nhlratings') and sum(f in rt['attrs'] for f in fs) >= len(fs) - 3:
                samples[cls(p['pos'])].append(rt['attrs'])
        # запасная форма — медианы игроков НХЛ исходной базы (у кого из NHL 27 мало данных)
        base = defaultdict(list)
        for r in range(v.nbio):
            if 1 <= v.g('team', r) <= 30 and v.ai(r) and not v.created_slot(r):
                t, row = v.ai(r)
                fs = GK if t == G else SK
                base[cls({0: 'C', 1: 'L', 2: 'R', 3: 'D', 4: 'G'}[v.g('position', r)])].append(
                    {f: db.get(t, f, row) + BASE for f in fs})
        self.shape = {}
        for c in 'CWDG':
            fs = GK if c == 'G' else SK
            self.shape[c] = {f: _median([a.get(f) for a in samples[c]]) or _median([a[f] for a in base[c]], 60)
                             for f in fs}
        # форма по стилю (у кого nhlratings.net называет стиль): снайперу — бросок и т. п.
        by_style = defaultdict(list)
        for p in players:
            rt = p['rating']
            if rt['source'] in ('ea', 'nhlratings') and rt.get('style') is not None and p['pos'] != 'G':
                if sum(f in rt['attrs'] for f in SK) >= len(SK) - 3:
                    by_style[(cls(p['pos']), rt['style'])].append(rt['attrs'])
        self.shape_style = {}
        for key, rows in by_style.items():
            if len(rows) >= 5:
                self.shape_style[key] = {f: _median([a.get(f) for a in rows]) or self.shape[key[0]][f] for f in SK}
        # поправка OVR − среднее атрибутов (по игрокам EA)
        diffs = defaultdict(list)
        for p in players:
            rt = p['rating']
            if rt['source'] == 'ea' and rt['ovr']:
                fs = fields_of(p['pos'])
                vals = [rt['attrs'][f] for f in fs if f in rt['attrs']]
                if len(vals) >= len(fs) - 3:
                    diffs[cls(p['pos'])].append(rt['ovr'] - sum(vals) / len(vals))
        self.offset = {c: _median(diffs[c], 0.0) for c in 'CWDG'}
        # перцентили OVR НХЛ 2026/27 по амплуа — для тех, у кого рейтинга нет совсем
        ovrs = defaultdict(list)
        for p in players:
            if p['rating']['ovr']:
                ovrs[cls(p['pos'])].append(p['rating']['ovr'])
        self.depth = {c: (sorted(x)[len(x) // 4] if x else 75) for c, x in ovrs.items()}
        # стили исходной базы: «центроид» формы атрибутов и медианы тенденций ИИ
        cent, bias = defaultdict(lambda: defaultdict(list)), defaultdict(lambda: defaultdict(list))
        for r in range(db.by_name[S]['rows']):
            st = db.get(S, 'p_style', r)
            vals = {f: db.get(S, f, r) for f in SK}
            mean = sum(vals.values()) / len(vals)
            for f in SK:
                cent[st][f].append(vals[f] - mean)
            for f in SK_BIAS:
                bias[st][f].append(db.get(S, f, r))
        self.centroid = {st: {f: statistics.mean(x) for f, x in d.items()} for st, d in cent.items()
                         if st in D_STYLES + F_STYLES and len(d['p_speed']) >= 3}
        self.bias = {st: {f: int(statistics.median(x)) for f, x in d.items()} for st, d in bias.items()}
        self.estimated = {}

    # --- атрибуты ------------------------------------------------------------------------------
    def db_attrs(self, r):
        t, row = self.v.ai(r)
        return {f: self.v.db.get(t, f, row) + BASE for f in (GK if t == G else SK)}

    def target_ovr(self, p):
        rt = p['rating']
        if rt['ovr']:
            return rt['ovr']
        c = cls(p['pos'])
        a = age(p['birth'])
        adj = -2 if a <= 21 else -1 if a <= 23 else 0
        name = f"{p['first']} {p['last']}"
        spread = zlib.crc32(name.encode()) % 3 - 1          # −1…+1, постоянный для игрока
        ovr = self.depth.get(c, 75) + adj + spread
        self.estimated[p['nhl_id']] = ovr
        return ovr

    def attributes(self, p, row, new, style=None):
        """(атрибуты в шкале 36–99, OVR) для игрока; row — его строка био (новый: строка донора).
        Форма нового игрока — по стилю, если для стиля набралось игроков NHL 27, иначе по амплуа."""
        fs = fields_of(p['pos'])
        c = cls(p['pos'])
        if new or self.v.is_goalie(row) != (p['pos'] == 'G'):
            shape = self.shape_style.get((c, style)) or self.shape[c]
        else:
            shape = self.db_attrs(row)
        shape = {f: shape.get(f, self.shape[c][f]) for f in fs}
        rt = p['rating']
        ovr = self.target_ovr(p)
        known = {f: v for f, v in rt['attrs'].items() if f in fs}
        if rt['source'] in ('ea', 'nhlratings') and len(known) >= 3:
            # полный набор: известные — как есть, недостающие — форма на уровне известных
            delta = sum(known.values()) / len(known) - sum(shape[f] for f in known) / len(known)
            out = {f: known.get(f, shape[f] + delta) for f in fs}
            return {f: clamp_rating(x) for f, x in out.items()}, ovr
        # только OVR (и, может быть, несколько атрибутов): известные — как есть, остальные —
        # форма, сдвинутая так, чтобы среднее всех плюс поправка амплуа дало OVR
        unknown = [f for f in fs if f not in known]
        out = {f: known.get(f, shape[f]) for f in fs}
        for _ in range(10):   # упирающиеся в 36/99 значения съедают часть сдвига
            level = sum(clamp_rating(out[f]) for f in fs) / len(fs) + self.offset[c]
            delta = (ovr - level) * len(fs) / max(1, len(unknown))
            if abs(ovr - level) < 0.3 or not unknown:
                break
            for f in unknown:
                out[f] += delta
        return {f: clamp_rating(x) for f, x in out.items()}, ovr

    def style(self, p, row, new):
        """p_style (полевые: 1 защитник-оборонец, 2 атакующий, 3 силовой, 4 универсал; 5 «работяга»,
        6 плеймейкер, 7 снайпер, 8 силовой нападающий, 9 двусторонний, 10 тафгай) / g_style
        (0 стойка, 1 баттерфляй, 2 гибрид) — шкала сверена по базе. Порядок: nhlratings.net →
        прежний стиль того же класса (F/D) → по результативности (карьера в НХЛ или последний
        сезон в другой лиге) → центроид формы атрибутов исходной базы."""
        rt = p['rating']
        if p['pos'] == 'G':
            if rt.get('style') in (0, 1, 2):
                return rt['style']
            if not new and self.v.ai(row)[0] == G:
                return self.v.db.get(G, 'g_style', self.v.ai(row)[1])
            return 1                                          # butterfly — самый частый
        allowed = D_STYLES if p['pos'] == 'D' else F_STYLES
        if rt.get('style') in allowed:
            return rt['style']
        if not new and self.v.ai(row)[0] == S:
            old = self.v.db.get(S, 'p_style', self.v.ai(row)[1])
            if old in allowed:
                return old
        by_stats = self.style_from_scoring(p)
        if by_stats:
            return by_stats
        attrs = rt['attrs']
        if sum(f in attrs for f in SK) < len(SK) - 3:
            return 4 if p['pos'] == 'D' else 9
        mean = sum(attrs[f] for f in SK if f in attrs) / sum(f in attrs for f in SK)
        dev = {f: attrs.get(f, mean) - mean for f in SK}
        cand = [st for st in allowed if st in self.centroid and st not in (3, 10)]   # силовиков не назначаем
        return min(cand, key=lambda st: sum((dev[f] - self.centroid[st][f]) ** 2 for f in SK))

    @staticmethod
    def style_from_scoring(p):
        """Стиль по очкам за игру, доле голов, штрафу и весу. В юниорских и студенческих лигах
        очков больше — делим на 1,8, в прочих взрослых (АХЛ, Европа) — на 1,2."""
        sc = p.get('scoring') or {}
        s = sc.get('nhl') or {}
        k = 1.0
        if (s.get('gp') or 0) < 20:
            s = sc.get('other') or {}
            k = 1.8 if s.get('junior') else 1.2
        gp = s.get('gp') or 0
        if gp < 10:
            return None
        ppg = (s['g'] + s['a']) / gp / k
        share = s['g'] / max(1, s['g'] + s['a'])
        pim = s['pim'] / gp
        weight = p.get('weight_lb') or 195
        if p['pos'] == 'D':
            if ppg >= 0.45:
                return 2
            if ppg < 0.22 and (weight >= 210 or pim >= 0.8):
                return 1
            return 4
        if ppg >= 0.65:
            return 7 if share >= 0.45 else 6
        if ppg >= 0.4:
            return 8 if weight >= 210 else 7 if share >= 0.5 else 9
        return 5 if pim >= 0.8 or weight >= 205 else 9

    @staticmethod
    def potential(p):
        return 30 if age(p['birth']) <= 21 else 5
