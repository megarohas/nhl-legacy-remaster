"""Предложения сборных тренеру (пользователю) на Кубок наций — по успехам прошлого сезона.

Сила сборной — средний OVR её лучших 13 нападающих, 7 защитников и вратаря (пулы франшизы, natcup.franchise).
Репутация тренера 0…1: место команды пользователя по очкам в регулярке (0,55), раунд плей-офф (0,25), кубки Стэнли GM
(0,1), прошлые Кубки наций (история, 0,1). Чем выше репутация, тем сильнее сборные в предложениях: цель — место
в рейтинге сборных (1 − репутация)·(N − 1), берутся ближайшие к цели, всего OFFERS (без повторов); сборная,
которую тренер вёл в прошлом году, при медали предлагает продление первой.
"""
import random

from .franchise import NATIONS

OFFERS = 3
ROSTER = {'C': 4, 'W': 8, 'D': 7, 'G': 3}      # для силы и составов CPU: центры, крайние, защитники, вратари


def nation_strength(fr, code):
    pool = fr.pool(code)
    by = {'C': [], 'W': [], 'D': [], 'G': []}
    for p in pool:
        k = 'W' if p['pos'] in 'LR' else p['pos']
        if k in by:
            by[k].append(p['ovr'])
    best = by['C'][:4] + by['W'][:9] + by['D'][:7] + by['G'][:1]
    return sum(best) / max(len(best), 1), len(pool)


def ranking(fr):
    """Сборные по силе: [(код, имя, сила, игроков)], сильные первыми."""
    out = []
    for code, (tid, name) in NATIONS.items():
        s, n = nation_strength(fr, code)
        out.append((code, name, round(s, 1), n))
    return sorted(out, key=lambda x: -x[2])


def season_score(fr):
    """Место команды пользователя в регулярке последнего сезона (доля 0…1, 1 — лучшая) по очкам."""
    t = 'leagueteamseasonstats'
    yrs = fr.col(t, 'year')
    if not yrs:
        return 0.5, None
    y = max(yrs)
    pts = {}
    for i, tid in enumerate(fr.col(t, 'team_id')):
        if yrs[i] != y:
            continue
        w = fr.col(t, 'reg_w')[i] + fr.col(t, 'reg_otw')[i] + fr.col(t, 'reg_sow')[i]
        otl = fr.col(t, 'reg_otl')[i] + fr.col(t, 'reg_sol')[i]
        gp = w + otl + fr.col(t, 'reg_l')[i] + fr.col(t, 'reg_t')[i]
        pts[tid] = (2 * w + otl) / max(gp, 1) if gp else 0.0
    if fr.user_team not in pts or len(pts) < 2:
        return 0.5, y
    order = sorted(pts, key=lambda k: -pts[k])
    return 1 - order.index(fr.user_team) / (len(order) - 1), y


def reputation(fr, history=(), playoff_round=0, cups=0):
    s, _ = season_score(fr)
    po = min(playoff_round, 4) / 4
    medals = sum(1 for h in history[-3:] if h.get('place', 99) <= 3) / 3 if history else 0.0
    return min(1.0, 0.55 * s + 0.25 * po + 0.1 * min(cups, 3) / 3 + 0.1 * medals)


def offers(fr, history=(), playoff_round=0, cups=0, seed=None):
    rank = ranking(fr)
    rep = reputation(fr, history, playoff_round, cups)
    rnd = random.Random(seed)
    target = (1 - rep) * (len(rank) - 1)
    order = sorted(range(len(rank)), key=lambda i: abs(i - target) + rnd.random() * 1.5)
    picks = []
    last = history[-1] if history else None
    if last and last.get('place', 99) <= 3:
        for i, r in enumerate(rank):
            if r[0] == last['country']:
                picks.append(i)
    for i in order:
        if i not in picks:
            picks.append(i)
        if len(picks) == OFFERS:
            break
    return rep, [rank[i] + (i + 1,) for i in picks]
