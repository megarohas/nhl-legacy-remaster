"""Атрибуты игроков составов НХЛ — под OVR базы (координатор 11.10).

Игра считает полевым OVR из атрибутов (roster.ovrformula: регрессия по базе EA Legacy, OVR растёт в 1,9 раза быстрее
среднего атрибута). Конвейер 08.10 достраивал атрибуты из OVR NHL 27 «средним атрибутов + поправкой», и у игроков НХЛ
не из топ-300 EA OVR из атрибутов выходил ниже OVR базы, у многих на 5–12. У топ-300 EA (OVR от TOP) атрибуты
настоящие, формула с OVR базы сходится: медиана −0,4, у части до ±4,7 — это погрешность самой формулы (по базе EA
Legacy средняя ошибка 1,1–1,4).

Здесь атрибуты сдвигаются у игрока состава НХЛ, у которого OVR формулы (не выше 99) расходится с полем overall больше
чем на TOL, если его OVR ниже TOP или его атрибуты достроены (generated: профиль отклонений от среднего атрибута ±1,5 как
у другого игрока того же класса и стиля — форма конвейера плюс общий сдвиг). Настоящие атрибуты топ-300 EA не трогаются.
Сдвиг — тем же способом, каким конвейер строит атрибуты (ratings.Model.attributes с Model.formula): форма — его же
атрибуты, сдвиг — до OVR формулы, равного overall. Меняются только атрибуты c_* (у полевых 25, у вратарей 19). Поле
overall, стиль, тенденции, потенциал, звенья, составы и всё остальное — как были. Повторный запуск ничего не меняет.

    python tools/legacy_data/nhl_attrs.py БАЗА.db [БАЗА.db …] [--dry-run]

Этап build-all «nhlattrs» (после ahl, до useredits): out и out-ahl32, затем draft_roster.db заново. Отчёт о прогоне,
который менял базу, — game/work/legacy-data/nhl-attrs/<папка базы>.json.
"""
import json
import os
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
sys.path.insert(0, TOOLS)
os.environ['NHL_GAME'] = 'legacy'
from roster.common import set_game  # noqa: E402
set_game('legacy')                     # до импорта модулей конвейера: dbview берёт поля игры при импорте
from roster import ovrformula  # noqa: E402
from roster.dbview import G, NHL, S, View, fld  # noqa: E402
from roster.ratings import BASE, Model, cls  # noqa: E402
from tdb import Tdb, load_meta  # noqa: E402

W = os.environ.get('LEGACY_DATA_WORK') or os.path.join(os.path.dirname(TOOLS), 'game', 'work', 'legacy-data')
TOL = 1.0              # |OVR формулы − overall| не больше — игрок не трогается
TOP = 84               # OVR от TOP — топ-300 EA (ea.com/games/nhl/ratings): настоящие атрибуты не трогаются
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
    """{строка: (класс, OVR формулы не выше 99, overall, атрибуты)} у игроков составов НХЛ."""
    out = {}
    for r in nhl_rows(v):
        if not v.ai(r):
            continue
        t, ai = v.ai(r)
        c = cls(POS[v.g('position', r)])
        if (t == G) != (c == 'G'):
            continue
        attrs = {f: db.get(t, fld(f), ai) + BASE for f in ovrformula.fields(c)}
        out[r] = (c, min(99.0, ovrformula.ovr(c, attrs)), v.overall(r), attrs)
    return out


def generated(db, v, dev):
    """Строки с достроенными атрибутами: профиль (атрибут − среднее) до ±SAME как у другого игрока того же класса и
    стиля — так выходят игроки одной формы конвейера с общим сдвигом."""
    prof = {}
    for r, (c, _, _, a) in dev.items():
        t, ai = v.ai(r)
        m = statistics.mean(a.values())
        key = (c, db.get(t, fld('p_style' if t == S else 'g_style'), ai))
        prof.setdefault(key, []).append((r, [a[f] - m for f in ovrformula.fields(c)]))
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
    m.formula = ovrformula
    dev = deviations(db, v)
    gen = generated(db, v, dev)
    rule = lambda r, o: o < TOP or r in gen
    players = []
    for r, (c, f0, o, old) in sorted(dev.items()):
        if abs(f0 - o) <= TOL or not rule(r, o):
            continue
        t, ai = v.ai(r)
        p = {'pos': POS[v.g('position', r)], 'nhl_id': v.gid[r], 'first': '', 'last': v.name(r),
             'birth': list(v.birth(r)), 'rating': {'source': 'stats', 'ovr': o, 'attrs': {}, 'scale': 'nhl-base'}}
        new, _ = m.attributes(p, r, False)
        for f, x in new.items():
            db.set(t, fld(f), ai, x - BASE)
        players.append({'name': v.name(r), 'game_id': v.gid[r], 'team': [x for x in v.teams_of[r] if x in NHL][0],
                        'pos': p['pos'], 'overall': o, 'generated': r in gen, 'formula_before': round(f0, 1),
                        'formula_after': round(ovrformula.ovr(c, new), 1),
                        'mean_before': round(statistics.mean(old.values()), 1),
                        'mean_after': round(statistics.mean(new.values()), 1)})
    db.fix()
    bad = db.verify()
    if bad:
        sys.exit(f'{path}: CRC не сошлись: {bad[:3]}')
    after = deviations(db, View(db))
    ruled = [(v.name(r), round(f - o, 1)) for r, (_, f, o, _) in after.items() if rule(r, o)]
    off = [x for x in ruled if abs(x[1]) > TOL]
    top = [f - o for r, (_, f, o, _) in after.items() if not rule(r, o)]
    name = os.path.basename(os.path.dirname(os.path.dirname(os.path.abspath(path))))
    summary = {
        'db': path, 'nhl_players': len(dev), 'fixed': len(players), 'tol': TOL, 'top': TOP, 'generated': len(gen),
        'before': {'within_tol': sum(1 for _, f, o, _ in dev.values() if abs(f - o) <= TOL),
                   'median_diff': round(statistics.median(f - o for _, f, o, _ in dev.values()), 2)},
        'after': {'checked': len(ruled), 'max_abs_diff': max((abs(x) for _, x in ruled), default=0), 'outside_tol': off,
                  'median_diff': round(statistics.median(f - o for _, f, o, _ in after.values()), 2)},
        'ea_top_untouched': {'n': len(top), 'median_diff': round(statistics.median(top), 2) if top else None,
                             'outside_tol': sum(1 for x in top if abs(x) > TOL),
                             'max_abs_diff': round(max((abs(x) for x in top), default=0), 1)},
        'players': players}
    print(f'{path}: игроков НХЛ {len(dev)}, атрибуты сдвинуты у {len(players)} (|формула − overall| > {TOL}, OVR ниже '
          f'{TOP} или атрибуты достроены — {len(gen)}); после у них и у всех ниже {TOP}: наибольшее |формула − overall| '
          f'{summary["after"]["max_abs_diff"]:.2f}, вне ±{TOL}: {len(off)}; топ-300 EA (не трогались, {len(top)}): '
          f'медиана {summary["ea_top_untouched"]["median_diff"]:+}, вне ±{TOL} — {summary["ea_top_untouched"]["outside_tol"]}, '
          f'наибольшее {summary["ea_top_untouched"]["max_abs_diff"]}' + (' (проба, не записано)' if dry else ''))
    if off:
        print('  вне допуска:', off[:10])
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
        bad |= bool(run(p, dry)['after']['outside_tol'])
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main(sys.argv[1:])
