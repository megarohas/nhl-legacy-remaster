"""OVR NHL Legacy из атрибутов (c_*): игра показывает полевым OVR, посчитанный из атрибутов, а не поле overall
(координатор 11.10; так же nhl-modding-studio, studio-domain/attributes.rs: «Derived skater Overall — the depth-chart /
list number», вратарям — поле overall).

Формулы игры у нас нет (в образе есть только веса карточек HUT, gCardOverallWeights_*). Здесь — линейная регрессия
overall ~ атрибуты по базе EA Legacy (`gameprofile.LEGACY.db`, cacheboot/db/nhlng.db): отдельно C, W, D, G, все лиги,
без пустышек (OVR ≤ 40). Сверка — `check`: по базе EA медиана остатка по лигам в пределах ±0,6 (у вратарей НХЛ −1,3),
средняя ошибка 0,5–1,8 (НХЛ 1,1–1,4, АХЛ 1,5–1,8, вратари до 2,6). На настоящих атрибутах NHL 27 (топ-300 EA в наших
составах НХЛ) — медиана −0,4. Та же форма, что у nhl-modding-studio (tdb-formula/overall.rs, регрессия по default.db
EA): у нападающих 1,92 × взвешенное среднее − 78,7, у защитников сумма коэффициентов 1,86; здесь — 1,90 / 1,92 / 1,84 /
1,80 (C/W/D/G). То есть OVR растёт почти вдвое быстрее среднего атрибута: у АХЛ EA средний атрибут 77,7 → OVR 69, у
НХЛ 83,7 → 83. Поэтому сдвиг формы «среднее атрибутов + поправка группы = OVR» (ratings.Model, калибровка Liiga и
CV/HSK) верен только в середине шкалы группы: OVR 82 по шкале АХЛ давал средний атрибут 91 и OVR из атрибутов 95, а
OVR 78 по шкале НХЛ — 70. Model.formula = этот модуль — сдвиг формы до OVR формулы.

    python -m roster.ovrformula fit                  # коэффициенты заново по базе EA (печать для LEGACY_W)
    python -m roster.ovrformula check [БАЗА …]       # OVR из атрибутов против поля overall по лигам
    python -m roster.ovrformula compare ДО ПОСЛЕ     # распределения по группам и топ АХЛ / свободных агентов
"""
import os
import statistics
import sys

if __name__ == '__main__':
    os.environ['NHL_GAME'] = 'legacy'      # до импорта конвейера: dbview берёт поля игры при импорте
if __package__ in (None, ''):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    __package__ = 'roster'

from .ratings import BASE, GK, SK, cls  # noqa: E402

JUNK = 40              # OVR 36 (атрибуты 0) — пустышки базы EA, в регрессию не идут
# [свободный член, коэффициенты по SK (полевые) или GK (вратари)] — `fit` по базе EA Legacy 11.10.2026
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


def ovr(c, attrs, w=None):
    """OVR из атрибутов (шкала 36–99, имена p_*/g_*) для класса C/W/D/G — без округления."""
    w = (w or LEGACY_W)[c]
    return w[0] + sum(k * attrs[f] for f, k in zip(fields(c), w[1:]))


def weights(c, w=None):
    """{атрибут: прирост OVR формулы от +1 к нему}."""
    return dict(zip(fields(c), (w or LEGACY_W)[c][1:]))


def gain(c, names, w=None):
    """Насколько вырастет OVR формулы при +1 ко всем атрибутам names."""
    ws = weights(c, w)
    return sum(ws[f] for f in names)


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
    rows, _ = rows_of(path, meta)
    by = {}
    for c, a, o, t, _ in rows:
        if o > JUNK:
            by.setdefault((league(t), c), []).append((ovr(c, a, w), o))
    log(path)
    for (lg, c), xs in sorted(by.items(), key=lambda kv: ([n for n, _, _ in LEAGUES] + ['без клуба', 'прочие']).index(
            kv[0][0]) * 10 + 'CWDG'.index(kv[0][1])):
        if len(xs) < 5:
            continue
        f = sorted(x for x, _ in xs)
        res = [x - o for x, o in xs]
        q = lambda p: f[min(len(f) - 1, int(p * len(f)))]
        log(f'  {lg:9s} {c} n={len(xs):4d}  из атрибутов p10 {q(.1):5.1f} медиана {statistics.median(f):5.1f} p90 '
            f'{q(.9):5.1f} макс {f[-1]:5.1f} | поле overall медиана {statistics.median(o for _, o in xs):5.1f} | '
            f'остаток медиана {statistics.median(res):+5.2f}, средний модуль {statistics.mean(abs(x) for x in res):4.2f}')


def groups(path):
    """{группа: [(класс, OVR из атрибутов, поле overall, имя)]}: НХЛ, АХЛ (с CV/HSK), свободные агенты (пул), Liiga,
    CHL — по составам базы."""
    rows, v = rows_of(path)
    fa = v.fa_rows
    out = {}
    for c, a, o, t, r in rows:
        teams = v.teams_of[r]
        g = 'FA' if r in fa else next((league(x) for x in teams if league(x) in ('NHL', 'AHL', 'CV/HSK', 'Liiga', 'CHL')),
                                      None)
        if g:
            out.setdefault('AHL' if g == 'CV/HSK' else g, []).append((c, ovr(c, a), o, v.name(r)))
    return out


def compare(before, after, top=15, log=print):
    """До/после: распределение OVR из атрибутов по группам и классам, топ АХЛ и свободных агентов."""
    gb, ga = groups(before), groups(after)
    q = lambda xs, p: xs[min(len(xs) - 1, int(p * len(xs)))]
    log(f'OVR из атрибутов (ovrformula): p10 / медиана / p90 / макс; в скобках — поле overall медиана\n'
        f'  до:    {before}\n  после: {after}')
    for g in ('NHL', 'AHL', 'FA', 'Liiga', 'CHL'):
        for c in 'CWDG':
            line = []
            for gg in (gb, ga):
                xs = sorted(f for k, f, _, _ in gg.get(g, []) if k == c)
                st = [o for k, _, o, _ in gg.get(g, []) if k == c]
                line.append(f'{q(xs, .1):5.1f} / {statistics.median(xs):5.1f} / {q(xs, .9):5.1f} / {xs[-1]:5.1f} '
                            f'({statistics.median(st):4.1f})' if xs else '—')
            n = sum(1 for k, *_ in ga.get(g, []) if k == c)
            log(f'  {g:5s} {c} n={n:3d}  {line[0]}  →  {line[1]}')
    for g in ('AHL', 'FA'):
        for name, gg in (('до', gb), ('после', ga)):
            xs = sorted(gg.get(g, []), key=lambda x: -x[1])[:top]
            log(f'  топ-{top} {g} {name}: ' + ', '.join(f'{n} {k} {f:.0f} ({o})' for k, f, o, n in xs))


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    from .common import set_game
    gp = set_game('legacy')
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'check'
    if cmd == 'compare':
        compare(sys.argv[2], sys.argv[3])
        return
    if cmd == 'fit':
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
