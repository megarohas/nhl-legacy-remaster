"""Наработка (10.10, отменено в 09:10 — не в сборке): разведка для возрастного спада рейтингов старых игроков АХЛ
составов 2015 года (решение пользователя 09:08, вариант 3; отменено: составы АХЛ 2026/27 из сети его заменят).
Что даёт: поля роста и потенциала по возрасту в базе 2015 (EA) и сопоставленные игроки 2015 → 2026/27 (тот же
game_id, имя и дата рождения): переписаны ли атрибуты конвейером — «свои атрибуты» (EA NHL 27, годятся для калибровки
по атрибутам), «сдвиг формы» (только OVR с nhlratings.net) или как в 2015.
Итог прогона по nhl32-ahl32 → out-ahl32 (88237e2b): в НХЛ 171 со своими атрибутами, 86 со сдвигом формы, 12 как в
2015; в АХЛ 741 как в 2015. У базы 2015 c_potential — только 5 и 30, поля роста (growthtier, growthletter) зависят
от возраста. План модели (не сделан): Δ атрибута = c + Σ r(возраст) за 11 лет, r — рост до 26, плато 26–29, спад с 30
(у катания и физики круче), c — сдвиг шкалы NHL 27 к Legacy; OVR — по линейной формуле базы (подбор по игрокам EA).

    python tools/legacy_data/ahl_age_explore.py OLD_DB NEW_DB
"""
import collections
import os
import statistics
import sys

sys.path.insert(0, 'S:/Claude/megarohas_nhl13/tools')
sys.stdout.reconfigure(encoding='utf-8')
os.environ['NHL_GAME'] = 'legacy'
from roster import common  # noqa: E402

common.set_game('legacy')
from roster import dbview  # noqa: E402
from roster.dbview import G, NHL, S, T  # noqa: E402
from roster.ratings import GK, SK  # noqa: E402
from tdb import Tdb  # noqa: E402
from tdb_read import load_meta  # noqa: E402

GROW = ['growthage', 'growthletter', 'growthmod', 'growthspeed', 'growthtier']


def load(p):
    d = os.path.dirname(p)
    db = Tdb(open(p, 'rb').read(), load_meta(os.path.join(d, 'nhlng-meta.xml')))
    return db, dbview.View(db)


def attrs(db, v, r):
    t, row = v.ai(r)
    names = SK if t == S else GK
    return t, {n: db.get(t, dbview.fld(n), row) + 36 for n in names}, \
        {f: db.get(t, f, row) for f in GROW + ['c_overall', 'c_potential', 'playerstyle']}


old_db, old = load(sys.argv[1])
new_db, new = load(sys.argv[2])
league = {t: new_db.get(T, 'league', t) for t in range(new_db.by_name[T]['rows'])}
print('поля роста по возрасту 2015 (база 2015, полевые, все клубы):')
by_age = collections.defaultdict(lambda: collections.defaultdict(list))
for r in range(old.nbio):
    if old.ai(r) is None or old.created_slot(r):
        continue
    t, a, g = attrs(old_db, old, r)
    if t != S:
        continue
    age = 2015 - old.birth(r)[0]
    band = min(max(age, 18), 40) // 2 * 2
    for f, val in g.items():
        by_age[band][f].append(val)
for band in sorted(by_age):
    row = by_age[band]
    print(f'  {band}-{band + 1}: n={len(row["c_overall"])} ' + ' '.join(
        f'{f}={statistics.median(row[f]):g}' for f in GROW + ['c_potential', 'c_overall']))
print()
same = changed = 0
kinds = collections.Counter()
for r_new in range(new.nbio):
    g = new.gid[r_new]
    r_old = old.row_of_gid.get(g)
    if r_old is None or new.ai(r_new) is None or old.ai(r_old) is None:
        continue
    if new.name(r_new) != old.name(r_old) or new.birth(r_new) != old.birth(r_old):
        continue
    t1, a1, g1 = attrs(new_db, new, r_new)
    t0, a0, g0 = attrs(old_db, old, r_old)
    teams = new.teams_of.get(r_new, [])
    where = ('НХЛ' if any(t in NHL for t in teams) else
             f'лига {league[teams[0]]}' if teams else ('FA' if r_new in new.fa_rows else 'без клуба'))
    if a1 == a0:
        kinds[(where, 'атрибуты как в 2015')] += 1
    else:
        d = [a1[n] - a0[n] for n in a0]
        uniform = statistics.pstdev(d) < 1.5
        kinds[(where, 'сдвиг формы' if uniform else 'свои атрибуты')] += 1
for k, n in sorted(kinds.items(), key=lambda kv: (-kv[1])):
    print(f'  {k[0]:>10} | {k[1]:22} | {n}')
