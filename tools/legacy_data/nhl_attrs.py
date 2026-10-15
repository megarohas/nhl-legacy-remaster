"""Атрибуты игроков составов НХЛ — под OVR базы (координатор 11.10).

Игра считает OVR из атрибутов и поле c_overall не читает (roster.ovrformula: точная формула игры, таблицы worth2.brk,
разбор nhl-legacy-port). Конвейер 08.10 достраивал атрибуты из OVR NHL 27 «средним атрибутов + поправкой», и у игроков НХЛ
не из топ-300 EA OVR в игре выходил ниже OVR базы, у многих на 5–12. У топ-300 EA атрибуты настоящие (NHL 27), но и у
них OVR игры по медиане на 1 выше OVR NHL 27: формула NHL 27 другая.

У каждого игрока состава НХЛ (полевые и вратари), у которого OVR игры (ovrformula.game_ovr) не равен полю overall,
атрибуты сдвигаются тем же способом, каким конвейер строит атрибуты (ratings.Model.attributes с Model.formula): форма —
его же атрибуты, сдвиг — пока непрерывный OVR формулы не станет в пределах ±0,25 от overall (тогда OVR игры равен ему
точно), затем по одному атрибуту ±1. Так и у топ-300 EA (там сдвиг мал). Вратари — с 11.10 12:20 тоже по точной формуле
(таблица 13; до того — регрессия, в игре у них выходило на 3–5 больше базы; «исправляй» — пользователь).

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
TOP = 84               # OVR от TOP и атрибуты не достроены — топ-300 EA (ea.com/games/nhl/ratings), для отчёта
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
    """{строка: (класс, OVR игры, overall, атрибуты)} у игроков составов НХЛ."""
    out = {}
    for r in nhl_rows(v):
        if not v.ai(r):
            continue
        t, ai = v.ai(r)
        c = cls(POS[v.g('position', r)])
        if (t == G) != (c == 'G'):
            continue
        attrs = {f: db.get(t, fld(f), ai) + BASE for f in F.fields(c)}
        out[r] = (c, F.game_ovr(c, attrs), v.overall(r), attrs)
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
    m.formula = F
    dev = deviations(db, v)
    gen = generated(db, v, dev)
    top = lambda r, o: o >= TOP and r not in gen
    players, before = [], Counter()
    for r, (c, f0, o, old) in sorted(dev.items()):
        if f0 == o:
            continue
        before[('вратари' if c == 'G' else 'полевые', 'топ-300 EA' if top(r, o) else 'остальные', f0 - o)] += 1
        t, ai = v.ai(r)
        p = {'pos': POS[v.g('position', r)], 'nhl_id': v.gid[r], 'first': '', 'last': v.name(r),
             'birth': list(v.birth(r)), 'rating': {'source': 'stats', 'ovr': o, 'attrs': {}, 'scale': 'nhl-base'}}
        new, _ = m.attributes(p, r, False)
        for f, x in new.items():
            db.set(t, fld(f), ai, x - BASE)
        players.append({'name': v.name(r), 'game_id': v.gid[r], 'team': [x for x in v.teams_of[r] if x in NHL][0],
                        'pos': p['pos'], 'overall': o, 'generated': r in gen, 'top300': top(r, o),
                        'before': f0, 'after': F.game_ovr(c, new),
                        'mean_before': round(statistics.mean(old.values()), 1),
                        'mean_after': round(statistics.mean(new.values()), 1),
                        'changed_attrs': sum(1 for f in new if new[f] != old[f]),
                        'max_step': max(abs(new[f] - old[f]) for f in new)})
    db.fix()
    bad = db.verify()
    if bad:
        sys.exit(f'{path}: CRC не сошлись: {bad[:3]}')
    after = deviations(db, View(db))
    off = [(v.name(r), o, f) for r, (c, f, o, _) in after.items() if f != o]
    sk = [x for x in players if x['pos'] != 'G']
    gk = [x for x in players if x['pos'] == 'G']
    name = os.path.basename(os.path.dirname(os.path.dirname(os.path.abspath(path))))
    summary = {
        'db': path, 'nhl_players': len(dev), 'fixed': len(players), 'generated': len(gen), 'top': TOP,
        'skaters_fixed': len(sk), 'skaters_top300_fixed': sum(1 for x in sk if x['top300']),
        'goalies_fixed': len(gk), 'goalies_top300_fixed': sum(1 for x in gk if x['top300']),
        'before': {f'{a}, {k} {d:+d}': n for (a, k, d), n in sorted(before.items())},
        'after': {'not_equal': off},
        'players': players}
    print(f'{path}: игроков НХЛ {len(dev)}; OVR игры ≠ overall — полевых {len(sk)} (топ-300 EA '
          f'{summary["skaters_top300_fixed"]}), вратарей {len(gk)} (топ-300 EA {summary["goalies_top300_fixed"]}); '
          f'после — у {len(off)}' + (' (проба, не записано)' if dry else ''))
    print('  было (OVR игры − overall): ' + ', '.join(f'{k}: {n}' for k, n in summary['before'].items()))
    if off:
        print('  не сошлись:', off[:10])
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
        bad |= bool(s['after']['not_equal'])
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main(sys.argv[1:])
