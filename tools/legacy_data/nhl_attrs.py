"""Атрибуты игроков составов НХЛ — под OVR базы (координатор 11.10).

Игра считает OVR из атрибутов и поле c_overall не читает (roster.ovrformula: точная формула игры, таблицы worth2.brk,
разбор legacy-port). Конвейер 08.10 достраивал атрибуты из OVR NHL 27 «средним атрибутов + поправкой», и у игроков НХЛ
не из топ-300 EA OVR в игре выходил ниже OVR базы, у многих на 5–12. У топ-300 EA атрибуты настоящие (NHL 27), но и у
них OVR игры по медиане на 1 выше OVR NHL 27: формула NHL 27 другая.

Полевые: у каждого игрока состава НХЛ, у которого OVR игры (ovrformula.game_ovr) не равен полю overall, атрибуты
сдвигаются тем же способом, каким конвейер строит атрибуты (ratings.Model.attributes с Model.formula): форма — его же
атрибуты, сдвиг — пока непрерывный OVR формулы не станет в пределах ±0,25 от overall (тогда OVR игры равен ему точно),
затем по одному атрибуту ±1. Так и у топ-300 EA (там сдвиг мал). Вратари — как с 11.10 06:00: формула вратарей по игре
не сверена (с полем overall вратарей EA она расходится на 2–6), поэтому для них — прежняя регрессия: сдвигаются только
те, у кого |регрессия (не выше 99) − overall| > TOL, если OVR ниже TOP или атрибуты достроены (generated: профиль
отклонений от среднего атрибута ±1,5 как у другого вратаря того же стиля).

Меняются только атрибуты c_* (у полевых 25, у вратарей 19). Поле overall, стиль, тенденции, потенциал, звенья, составы и
всё остальное — как были. Повторный запуск ничего не меняет.

    python tools/legacy_data/nhl_attrs.py БАЗА.db [БАЗА.db …] [--dry-run]

Этап build-all «nhlattrs» (после ahl, до useredits): out и out-ahl32, затем draft_roster.db заново. Отчёт о прогоне,
который менял базу, — game/work/legacy-data/nhl-attrs/<папка базы>.json.
"""
import json
import os
import statistics
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
sys.path.insert(0, TOOLS)
os.environ['NHL_GAME'] = 'legacy'
from roster.common import set_game  # noqa: E402
set_game('legacy')                     # до импорта модулей конвейера: dbview берёт поля игры при импорте
from roster import ovrformula as F  # noqa: E402
from roster.dbview import G, NHL, S, View, fld  # noqa: E402
from roster.ratings import BASE, Model, cls  # noqa: E402
from tdb import Tdb, load_meta  # noqa: E402

W = os.environ.get('LEGACY_DATA_WORK') or os.path.join(os.path.dirname(TOOLS), 'game', 'work', 'legacy-data')
TOL = 1.0              # вратари: |регрессия − overall| не больше — не трогается
TOP = 84               # OVR от TOP — топ-300 EA (ea.com/games/nhl/ratings): у вратарей настоящие атрибуты не трогаются
SAME = 1.5             # профили отклонений, совпавшие до ±SAME по всем атрибутам, — достроенные (форма + сдвиг)
POS = {0: 'C', 1: 'L', 2: 'R', 3: 'D', 4: 'G'}


def nhl_rows(v):
    """Строки био игроков составов НХЛ (по записям exhibitionrostertable клубов 0–31)."""
    rows = set()
    for e in v.entries:
        g = v.link_gid.get(e['playerindex'])
        if e['team'] in NHL and g in v.row_of_gid:
            rows.add(v.row_of_gid[g])
    return sorted(rows)


def deviations(db, v):
    """{строка: (класс, OVR, overall, атрибуты)} у игроков составов НХЛ: у полевых OVR игры (целое), у вратарей —
    регрессия не выше 99."""
    out = {}
    for r in nhl_rows(v):
        if not v.ai(r):
            continue
        t, ai = v.ai(r)
        c = cls(POS[v.g('position', r)])
        if (t == G) != (c == 'G'):
            continue
        attrs = {f: db.get(t, fld(f), ai) + BASE for f in F.fields(c)}
        o = min(99.0, F.regression(c, attrs)) if c == 'G' else F.game_ovr(c, attrs)
        out[r] = (c, o, v.overall(r), attrs)
    return out


def generated(db, v, dev):
    """Строки с достроенными атрибутами: профиль (атрибут − среднее) до ±SAME как у другого игрока того же класса и
    стиля — так выходят игроки одной формы конвейера с общим сдвигом."""
    prof = {}
    for r, (c, _, _, a) in dev.items():
        t, ai = v.ai(r)
        m = statistics.mean(a.values())
        key = (c, db.get(t, fld('p_style' if t == S else 'g_style'), ai))
        prof.setdefault(key, []).append((r, [a[f] - m for f in F.fields(c)]))
    out = set()
    for rows in prof.values():
        for i, (r, p) in enumerate(rows):
            for q, pq in rows[i + 1:]:
                if max(abs(x - y) for x, y in zip(p, pq)) <= SAME:
                    out.update((r, q))
    return out


def run(path, dry=False):
    meta = os.path.join(os.path.dirname(path), 'nhlng-meta.xml')
    db = Tdb(open(path, 'rb').read(), load_meta(meta))
    v = View(db)
    m = Model(v, [])
    m.formula = F.SkatersExact
    dev = deviations(db, v)
    gen = generated(db, v, dev)
    top = lambda r, c, o: o >= TOP and r not in gen
    goalie_rule = lambda r, o: o < TOP or r in gen
    players, before = [], Counter()
    for r, (c, f0, o, old) in sorted(dev.items()):
        if c == 'G':
            if abs(f0 - o) <= TOL or not goalie_rule(r, o):
                continue
        elif f0 == o:
            continue
        else:
            before[('топ-300 EA' if top(r, c, o) else 'остальные', f0 - o)] += 1
        t, ai = v.ai(r)
        p = {'pos': POS[v.g('position', r)], 'nhl_id': v.gid[r], 'first': '', 'last': v.name(r),
             'birth': list(v.birth(r)), 'rating': {'source': 'stats', 'ovr': o, 'attrs': {}, 'scale': 'nhl-base'}}
        new, _ = m.attributes(p, r, False)
        for f, x in new.items():
            db.set(t, fld(f), ai, x - BASE)
        players.append({'name': v.name(r), 'game_id': v.gid[r], 'team': [x for x in v.teams_of[r] if x in NHL][0],
                        'pos': p['pos'], 'overall': o, 'generated': r in gen, 'top300': c != 'G' and top(r, c, o),
                        'before': round(f0, 1),
                        'after': round(F.regression(c, new), 1) if c == 'G' else F.game_ovr(c, new),
                        'mean_before': round(statistics.mean(old.values()), 1),
                        'mean_after': round(statistics.mean(new.values()), 1),
                        'changed_attrs': sum(1 for f in new if new[f] != old[f]),
                        'max_step': max(abs(new[f] - old[f]) for f in new)})
    db.fix()
    bad = db.verify()
    if bad:
        sys.exit(f'{path}: CRC не сошлись: {bad[:3]}')
    after = deviations(db, View(db))
    off = [(v.name(r), o, f) for r, (c, f, o, _) in after.items() if c != 'G' and f != o]
    goff = [(v.name(r), round(f - o, 1)) for r, (c, f, o, _) in after.items()
            if c == 'G' and goalie_rule(r, o) and abs(f - o) > TOL]
    sk = [x for x in players if x['pos'] != 'G']
    name = os.path.basename(os.path.dirname(os.path.dirname(os.path.abspath(path))))
    summary = {
        'db': path, 'nhl_players': len(dev), 'fixed': len(players), 'generated': len(gen), 'top': TOP, 'tol_goalies': TOL,
        'skaters_fixed': len(sk), 'skaters_top300_fixed': sum(1 for x in sk if x['top300']),
        'goalies_fixed': len(players) - len(sk),
        'before': {f'{k} {d:+d}': n for (k, d), n in sorted(before.items())},
        'after': {'skaters_not_equal': off, 'goalies_outside_tol': goff},
        'players': players}
    print(f'{path}: игроков НХЛ {len(dev)}; полевые — OVR игры ≠ overall у {len(sk)} (топ-300 EA '
          f'{summary["skaters_top300_fixed"]}), после — у {len(off)}; вратари (регрессия, ±{TOL}) — сдвинуты у '
          f'{summary["goalies_fixed"]}, вне допуска {len(goff)}' + (' (проба, не записано)' if dry else ''))
    print('  было (OVR игры − overall): ' + ', '.join(f'{k}: {n}' for k, n in summary['before'].items()))
    if off or goff:
        print('  не сошлись:', (off + goff)[:10])
    if players and not dry:                # отчёт — о прогоне, который менял базу (повтор его не затирает)
        rep = os.path.join(W, 'nhl-attrs', f'{name}.json')
        os.makedirs(os.path.dirname(rep), exist_ok=True)
        json.dump(summary, open(rep, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        tmp = path + '.part'
        with open(tmp, 'wb') as fh:
            fh.write(db.d)
        os.replace(tmp, path)
    return summary


def main(argv):
    sys.stdout.reconfigure(encoding='utf-8')
    dry = '--dry-run' in argv
    bad = False
    for p in [a for a in argv if a != '--dry-run']:
        s = run(p, dry)
        bad |= bool(s['after']['skaters_not_equal'] or s['after']['goalies_outside_tol'])
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main(sys.argv[1:])
