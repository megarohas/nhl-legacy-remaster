"""OVR NHL Legacy из атрибутов (c_*) — точная формула игры (разбор кода порта legacy-port, 11.10.2026).

Игра показывает OVR, посчитанный из атрибутов, а поле c_overall не читает вовсе: загрузчики exhibitionskaterai /
exhibitiongoalieai (82A0B388 / 82A0A680) берут колонки по номеру, c_overall среди них нет, хеша имени нет нигде в
коде. После загрузки 82B1FAC8 → 82A6C870 → 82A66948 → 82A66610 → 82A61210 считает OVR, 82B0E070 кладёт его в байт +130
структуры игрока, а списки и звенья читают этот байт (82B8CE08). Веса — таблицы fe/resource_kernel/worth2.brk
(ресурс 22, разбор 82A5A340): нападающие (C, LW, RW одинаково) — таблица 9, защитники — 6, вратари — 13 (номера —
байты 0x839F60E8 / EB / EC). Стиль игрока на OVR не влияет.

Формула (целые числа, как в игре). Атрибут — значение шкалы 36–99. Для каждой категории k:
    S = Σ вес·атрибут, W = Σ вес, S зажимается в [lo·W, hi·W],
    cat_k = (S − lo·W)·1000 // ((hi − lo)·W), не больше 999;
    OVR = (Σ cat_k · доля_k) // 1000 (доли в сумме 100), затем в пределах 36–99.
У полевых 6 категорий, у вратарей 3 (CATS). Сверка: 59 OVR полевых со снимков игры (Be a GM: звенья ANA, состав,
свободные агенты, контракты, статистика; стартовые составы SEA–VGK; 50 нападающих и 9 защитников) и слова пользователя
(Marcus Foligno 85, Nick Foligno 84) — все 61 точно, на базах тех дней. Регрессия (прежняя оценка) угадала 4 из 61,
поле overall расходилось до 12. Вратари в коде считаются так же, но снимков с OVR вратаря нет — сверки по игре у них
нет.

Поле overall у EA с формулой не совпадает (по базе EA Legacy точно у 15 % полевых, формула в среднем на 1–2 выше): игра
его не использует. У топ-300 EA NHL 27 в наших составах (настоящие атрибуты NHL 27, overall — OVR NHL 27) OVR игры по
медиане на 1 выше overall.

Функции:
    game_ovr(c, attrs)   — OVR, который покажет игра (целое, атрибуты округляются);
    ovr(c, attrs)        — непрерывная форма для подбора атрибутов (ratings.Model.formula): значение формулы без
                           отбрасывания дробей минус 0,5, так что round(ovr) — OVR игры (кроме редких случаев у
                           границы, точно — game_ovr), а ovr в пределах ±0,25 от цели даёт ровно цель;
    weights(c)           — прирост ovr от +1 к атрибуту (пока категория не упёрлась в lo/hi или 999);
    regression(c, attrs) — прежняя регрессия overall ~ атрибуты по базе EA (LEGACY_W), только для сверки.

    python -m roster.ovrformula check [БАЗА …]       # формула и регрессия против поля overall по лигам
    python -m roster.ovrformula verify [worth2.brk]  # константы CATS против таблиц игры (game/…/worth2.brk)
    python -m roster.ovrformula compare ДО ПОСЛЕ     # распределения OVR игры по группам и топ АХЛ / свободных агентов
    python -m roster.ovrformula fit                  # регрессия заново по базе EA (печать для LEGACY_W)
"""
import os
import statistics
import struct
import sys

if __name__ == '__main__':
    os.environ['NHL_GAME'] = 'legacy'      # до импорта конвейера: dbview берёт поля игры при импорте
if __package__ in (None, ''):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    __package__ = 'roster'

from .ratings import BASE, GK, SK, cls  # noqa: E402

# Категории worth2.brk: (доля в OVR, lo, hi, ((атрибут, вес), …)). Таблица 9 — нападающие, 6 — защитники, 13 — вратари.
_F = (
    (16, 40, 94, (('p_slapaccuracy', 17), ('p_slapshotpower', 17), ('p_wristaccuracy', 40), ('p_wristshotpower', 26))),
    (16, 20, 94, (('p_passing', 55), ('p_puckcontrol', 23), ('p_handeye', 11), ('p_deking', 11))),
    (16, 20, 94, (('p_offawareness', 80), ('p_poise', 19), ('p_discipline', 1))),
    (20, 40, 93, (('p_speed', 25), ('p_acceleration', 25), ('p_agility', 25), ('p_balance', 24), ('p_endurance', 1))),
    (10, 40, 94, (('p_strength', 55), ('p_bodychecking', 35), ('p_aggression', 2), ('p_fightingskill', 2),
                  ('p_durability', 6))),
    (22, 50, 93, (('p_defawareness', 69), ('p_shotblocking', 5), ('p_stickchecking', 25), ('p_faceoffs', 1))),
)
_D = (
    (8, 40, 95, (('p_slapaccuracy', 30), ('p_slapshotpower', 55), ('p_wristaccuracy', 5), ('p_wristshotpower', 10))),
    (11, 40, 94, (('p_passing', 60), ('p_puckcontrol', 25), ('p_handeye', 12), ('p_deking', 3))),
    (10, 45, 95, (('p_offawareness', 97), ('p_discipline', 3))),
    (11, 40, 93, (('p_speed', 26), ('p_acceleration', 21), ('p_agility', 26), ('p_balance', 26), ('p_endurance', 1))),
    (10, 50, 95, (('p_strength', 55), ('p_bodychecking', 35), ('p_aggression', 2), ('p_fightingskill', 2),
                  ('p_durability', 6))),
    (50, 30, 93, (('p_defawareness', 55), ('p_shotblocking', 13), ('p_stickchecking', 20), ('p_poise', 11),
                  ('p_faceoffs', 1))),
)
_G = (
    (60, 27, 95, (('g_positioning', 15), ('g_breakaway', 12), ('g_5hole', 13), ('g_gsh', 15), ('g_gsl', 15),
                  ('g_ssh', 15), ('g_ssl', 15))),
    (20, 40, 95, (('g_passing', 1), ('g_pokecheck', 1), ('g_reboundcontrol', 46), ('g_shotrecover', 46),
                  ('g_puckplayfrequency', 1), ('g_poise', 5))),
    (20, 37, 94, (('g_aggression', 15), ('g_agility', 20), ('g_durability', 15), ('g_endurance', 20), ('g_speed', 15),
                  ('g_vision', 15))),
)
CATS = {'C': _F, 'W': _F, 'D': _D, 'G': _G}
TABLE = {'C': 9, 'W': 9, 'D': 6, 'G': 13}
# номер атрибута в блоке со смещения +130 структуры игрока (колонки attr таблиц worth2.brk; 82A0B388 / 82A0A680)
SLOT = {
    'S': ('p_acceleration', 'p_aggression', 'p_agility', 'p_balance', 'p_bodychecking', 'p_defawareness', 'p_deking',
          'p_discipline', 'p_durability', 'p_endurance', 'p_faceoffs', 'p_fightingskill', 'p_handeye',
          'p_offawareness', 'p_passing', 'p_poise', 'p_puckcontrol', 'p_shotblocking', 'p_slapaccuracy',
          'p_slapshotpower', 'p_speed', 'p_stickchecking', 'p_strength', 'p_wristaccuracy', 'p_wristshotpower'),
    'G': ('g_aggression', 'g_agility', 'g_positioning', 'g_breakaway', 'g_durability', 'g_endurance', 'g_5hole',
          'g_gsh', 'g_gsl', 'g_passing', 'g_poise', 'g_pokecheck', 'g_puckplayfrequency', 'g_reboundcontrol',
          'g_shotrecover', 'g_speed', 'g_ssh', 'g_ssl', 'g_vision'),
}
WORTH2 = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'game', 'other',
                      'legacy', 'big', 'cacheboot', 'fe', 'resource_kernel', 'worth2.brk')

JUNK = 40              # OVR 36 (атрибуты 0) — пустышки базы EA, в регрессию и сверку не идут
# Прежняя регрессия overall ~ атрибуты по базе EA Legacy: [свободный член, коэффициенты по SK или GK] — `fit` 11.10.2026
LEGACY_W = {
    'C': [-78.44972, 0.064939, 0.049762, 0.039542, 0.067411, -0.117927, 0.026263, 0.031378, 0.115784, -0.016992,
          0.241539, 0.163611, 0.101828, 0.027905, 0.043452, 0.370698, 0.110138, 0.267067, 0.009329, 0.069195, 0.1996,
          0.000808, 0.004435, -0.023195, 0.052394, 0.004532],
    'W': [-79.51603, 0.046165, -0.013486, 0.076285, 0.060268, 0.017232, 0.0256, 0.067259, 0.079586, 0.131289,
          0.088865, 0.097809, 0.079024, 0.100899, 0.000958, 0.252653, 0.138841, 0.295779, 0.035393, 0.080258,
          0.175721, -0.030409, 0.028274, 0.004023, 0.028692, 0.056923],
    'D': [-72.56794, 0.018482, 0.013747, 0.142605, -0.049992, 0.030377, 0.055769, -0.017248, 0.018358, 0.078495,
          0.025098, 0.058971, 0.093584, 0.018024, 0.012136, 0.128991, 0.20227, 0.387747, 0.010391, 0.072934,
          0.311863, -0.00963, 0.126816, -0.012999, 0.038992, 0.080646],
    'G': [-72.02407, 0.115193, 0.317716, 0.057746, 0.123354, 0.095409, 0.013433, 0.124791, 0.085136, 0.183403,
          -0.010852, 0.028376, 0.021994, 0.157371, 0.066842, 0.032887, 0.154072, 0.033738, 0.120142, 0.079582],
}


def fields(c):
    return GK if c == 'G' else SK


def categories(c, attrs):
    """Категории игры 0…999 (целые, как в 82A5D530); атрибуты — шкала 36–99, округляются."""
    out = []
    for _, lo, hi, terms in CATS[c]:
        s = sum(w * int(round(attrs[f])) for f, w in terms)
        n = sum(w for _, w in terms)
        s = min(max(s, lo * n), hi * n)
        out.append(min(999, (s - lo * n) * 1000 // ((hi - lo) * n)))
    return out


def game_ovr(c, attrs):
    """OVR, который покажет игра (36–99) для класса C/W/D/G; атрибуты — шкала 36–99 (имена p_*/g_*)."""
    v = sum(k * share for k, (share, *_) in zip(categories(c, attrs), CATS[c])) // 1000
    return min(max(v, 36), 99)


def value(c, attrs):
    """Формула игры без отбрасывания дробей и без пределов 36–99 (непрерывная по атрибутам, можно дробные)."""
    v = 0.0
    for share, lo, hi, terms in CATS[c]:
        avg = sum(w * attrs[f] for f, w in terms) / sum(w for _, w in terms)
        v += share * min(999.0, max(0.0, 1000.0 * (avg - lo) / (hi - lo)))
    return v / 1000


def ovr(c, attrs):
    """Непрерывный OVR для подбора атрибутов: value − 0,5, round(ovr) ≈ game_ovr; ±0,25 от целого N даёт OVR игры N."""
    return value(c, attrs) - 0.5


def weights(c):
    """{атрибут: прирост ovr от +1 к нему} (пока его категория не упёрлась в lo/hi или 999)."""
    out = dict.fromkeys(fields(c), 0.0)
    for share, lo, hi, terms in CATS[c]:
        n = sum(w for _, w in terms)
        for f, w in terms:
            out[f] += share * w / (n * (hi - lo))
    return out


def gain(c, names):
    """Насколько вырастет ovr при +1 ко всем атрибутам names."""
    ws = weights(c)
    return sum(ws[f] for f in names)


def regression(c, attrs, w=None):
    """Прежняя оценка: регрессия overall ~ атрибуты по базе EA Legacy (без округления) — только для сверки."""
    w = (w or LEGACY_W)[c]
    return w[0] + sum(k * attrs[f] for f, k in zip(fields(c), w[1:]))


class SkatersExact:
    """Для ratings.Model.formula (legacy-data, 11.10): у полевых — точная формула игры (ovr, weights), у вратарей —
    прежняя регрессия: формула вратарей по игре не сверена, а с полем overall вратарей EA расходится на 2–6 (медиана),
    поэтому их атрибуты пока строятся как раньше (координатор 11.10)."""

    @staticmethod
    def ovr(c, attrs):
        return regression(c, attrs) if c == 'G' else ovr(c, attrs)

    @staticmethod
    def weights(c):
        return dict(zip(fields(c), LEGACY_W[c][1:])) if c == 'G' else weights(c)


def parse_brk(data):
    """{номер таблицы: [колонка, …]} из fe/resource_kernel/*.brk (формат по 82A5A340 / 82A573A8)."""
    flag, n = data[2], struct.unpack_from('<H', data, 3)[0]
    p, tabs = 5, {}
    for k in range(n):
        idx = k
        if flag == 1:
            idx, p = data[p], p + 1
        w0, w1 = struct.unpack_from('<II', data, p)
        p += 8 + (4 if w1 & 1 else 0)
        last = struct.unpack_from('<I', data, p)[0]
        p += 4
        ncols, nval = last & 0xFF, (last >> 8) & 0xFFF
        hdr = list(struct.unpack_from(f'<{ncols}h', data, p)) + [nval]
        p += 2 * ncols
        if w0 & 1:
            vals = struct.unpack_from(f'<{nval}h', data, p)
            p += 2 * nval
        else:
            vals = struct.unpack_from(f'<{nval}{"b" if w0 & 2 else "B"}', data, p)
            p += nval
        tabs[idx] = [list(vals[hdr[i]:hdr[i + 1]]) for i in range(ncols)]
    return tabs


def verify(path=WORTH2, log=print):
    """CATS против таблиц worth2.brk: колонки весов 0…n−1, lo/hi — колонка n, номера атрибутов — n+1…2n, доли — 2n+1
    (n — число категорий; так читает 82A61210). True, если всё совпало."""
    tabs = parse_brk(open(path, 'rb').read())
    ok = True
    for c in 'CDG':
        t, n = tabs[TABLE[c]], len(CATS[c])
        slots = SLOT['G' if c == 'G' else 'S']
        for k, (share, lo, hi, terms) in enumerate(CATS[c]):
            got = tuple((slots[a - 1], w) for a, w in zip(t[n + 1 + k], t[k]) if a)
            same = got == terms and (t[n][2 * k], t[n][2 * k + 1]) == (lo, hi) and t[2 * n + 1][k] == share
            ok &= same
            if not same:
                log(f'  {c} категория {k}: в файле {t[2 * n + 1][k]}, {t[n][2 * k]}–{t[n][2 * k + 1]}, {got}')
    log(f'{path}: CATS {"совпадают с таблицами 9 / 6 / 13" if ok else "НЕ совпадают"}')
    return ok


def rows_of(db_path, meta_path=None):
    """(класс, атрибуты, overall, номер команды или −1, строка био) по базе — игроки с атрибутами, без слотов
    создаваемых игроков."""
    from tdb import Tdb
    from tdb_read import load_meta
    from .dbview import G, View, fld
    meta = meta_path or os.path.join(os.path.dirname(db_path), 'nhlng-meta.xml')
    db = Tdb(open(db_path, 'rb').read(), load_meta(meta))
    v = View(db)
    out = []
    for r in range(v.nbio):
        if not v.ai(r) or v.created_slot(r):
            continue
        t, ai = v.ai(r)
        pos = {0: 'C', 1: 'L', 2: 'R', 3: 'D', 4: 'G'}[v.g('position', r)]
        c = cls(pos)
        if (t == G) != (c == 'G'):
            continue
        attrs = {f: db.get(t, fld(f), ai) + BASE for f in fields(c)}
        out.append((c, attrs, v.overall(r), v.g('team', r) - 1, r))
    return out, v


def fit(rows):
    from .statsrating import _lstsq
    out = {}
    for c in 'CWDG':
        rs = [(a, o) for k, a, o, _, _ in rows if k == c and o > JUNK]
        X = [[1.0] + [a[f] for f in fields(c)] for a, _ in rs]
        y = [float(o) for _, o in rs]
        out[c] = [round(x, 6) for x in _lstsq(X, y, ridge=1e-6)]
        out[c][0] = round(out[c][0], 5)
    return out


LEAGUES = (('NHL', 0, 31), ('AHL', 32, 61), ('SHL', 62, 75), ('Liiga', 76, 90), ('DEL', 91, 104),
           ('Extraliga', 105, 118), ('NLA', 119, 130), ('CHL', 154, 213), ('CV/HSK', 224, 225))


def league(team):
    if team < 0:
        return 'без клуба'
    return next((n for n, lo, hi in LEAGUES if lo <= team <= hi), 'прочие')


def check(path, meta=None, w=None, log=print):
    """OVR игры (game_ovr) и регрессия против поля overall по лигам и классам."""
    rows, _ = rows_of(path, meta)
    by = {}
    for c, a, o, t, _ in rows:
        if o > JUNK:
            by.setdefault((league(t), c), []).append((game_ovr(c, a), regression(c, a, w), o))
    log(f'{path}\n  OVR игры: p10 / медиана / p90 / макс | поле overall медиана | игра = поле, игра − поле (медиана, '
        f'средний модуль) | регрессия − поле')
    order = [n for n, _, _ in LEAGUES] + ['без клуба', 'прочие']
    for (lg, c), xs in sorted(by.items(), key=lambda kv: order.index(kv[0][0]) * 10 + 'CWDG'.index(kv[0][1])):
        if len(xs) < 5:
            continue
        g = sorted(x for x, _, _ in xs)
        q = lambda p: g[min(len(g) - 1, int(p * len(g)))]
        dg, dr = [x - o for x, _, o in xs], [x - o for _, x, o in xs]
        log(f'  {lg:9s} {c} n={len(xs):4d}  {q(.1):3d} / {statistics.median(g):4.1f} / {q(.9):3d} / {g[-1]:3d} | '
            f'{statistics.median(o for _, _, o in xs):4.1f} | {100 * sum(d == 0 for d in dg) / len(xs):3.0f} %, '
            f'{statistics.median(dg):+4.1f}, {statistics.mean(abs(d) for d in dg):4.2f} | '
            f'{statistics.median(dr):+5.2f}, {statistics.mean(abs(d) for d in dr):4.2f}')


def groups(path):
    """{группа: [(класс, OVR игры, поле overall, имя)]}: НХЛ, АХЛ (с CV/HSK), свободные агенты (пул), Liiga, CHL — по
    составам базы."""
    rows, v = rows_of(path)
    fa = v.fa_rows
    out = {}
    for c, a, o, t, r in rows:
        teams = v.teams_of[r]
        g = 'FA' if r in fa else next((league(x) for x in teams if league(x) in ('NHL', 'AHL', 'CV/HSK', 'Liiga', 'CHL')),
                                      None)
        if g:
            out.setdefault('AHL' if g == 'CV/HSK' else g, []).append((c, game_ovr(c, a), o, v.name(r)))
    return out


def compare(before, after, top=15, log=print):
    """До/после: распределение OVR игры по группам и классам, топ АХЛ и свободных агентов."""
    gb, ga = groups(before), groups(after)
    q = lambda xs, p: xs[min(len(xs) - 1, int(p * len(xs)))]
    log(f'OVR игры из атрибутов (ovrformula.game_ovr): p10 / медиана / p90 / макс; в скобках — поле overall медиана\n'
        f'  до:    {before}\n  после: {after}')
    for g in ('NHL', 'AHL', 'FA', 'Liiga', 'CHL'):
        for c in 'CWDG':
            line = []
            for gg in (gb, ga):
                xs = sorted(f for k, f, _, _ in gg.get(g, []) if k == c)
                st = [o for k, _, o, _ in gg.get(g, []) if k == c]
                line.append(f'{q(xs, .1):3d} / {statistics.median(xs):4.1f} / {q(xs, .9):3d} / {xs[-1]:3d} '
                            f'({statistics.median(st):4.1f})' if xs else '—')
            n = sum(1 for k, *_ in ga.get(g, []) if k == c)
            log(f'  {g:5s} {c} n={n:3d}  {line[0]}  →  {line[1]}')
    for g in ('AHL', 'FA'):
        for name, gg in (('до', gb), ('после', ga)):
            xs = sorted(gg.get(g, []), key=lambda x: -x[1])[:top]
            log(f'  топ-{top} {g} {name}: ' + ', '.join(f'{n} {k} {f} ({o})' for k, f, o, n in xs))


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    from .common import set_game
    gp = set_game('legacy')
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'check'
    if cmd == 'compare':
        compare(sys.argv[2], sys.argv[3])
    elif cmd == 'verify':
        sys.exit(0 if verify(*(sys.argv[2:3] or [WORTH2])) else 1)
    elif cmd == 'fit':
        rows, _ = rows_of(gp.db, gp.meta)
        w = fit(rows)
        print('LEGACY_W = {')
        for c in 'CWDG':
            print(f"    '{c}': {w[c]},")
        print('}')
        same = all(abs(a - b) < 1e-4 for c in 'CWDG' for a, b in zip(w[c], LEGACY_W[c]))
        print('совпадает с LEGACY_W' if same else 'ОТЛИЧАЕТСЯ от LEGACY_W')
        check(gp.db, gp.meta, w)
    else:
        for p in sys.argv[2:] or [gp.db]:
            check(p, gp.meta if p == gp.db else None)


if __name__ == '__main__':
    main()
