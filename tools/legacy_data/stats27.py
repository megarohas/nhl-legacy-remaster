"""История статистики игроков из базы NHL 27 → NHL Legacy: недостающие сезоны (этап build-all «stats27»).

Решение пользователя 21.10.2026: всем игрокам, которых точно опознаём в базе Legacy, добавить из NHL 27 сезоны, которых
у нас нет, — чтобы карьерная статистика была на 2025/26 (последний сезон в NHL 27).

Разбор 21.10 показал, что в таблицах статистики базы много чужих карьер: строки «доноров», отданные новым игрокам,
когда-то очищались не все — 7 147 сезонов НХЛ/АХЛ у опознанных игроков приходятся на возраст до 17 лет (у Шестёркина —
сезоны 2009–2015 в НХЛ/АХЛ, когда он играл в России). Поэтому:
- у игрока, у которого в NHL 27 есть история НХЛ/АХЛ (у EA она полная), сезоны этой таблицы — целиком из NHL 27;
- у остальных (пары нет или в NHL 27 у него сезонов нет) — убираются только невозможные сезоны: игроку к концу сезона
  меньше 18 лет (MIN_AGE); прочие сезоны базы EA 2015 года остаются.

    python tools/legacy_data/stats27.py [out|out-ahl32 …] [--dry-run] [--db27 nhl_game.db]

- **Кто.** Игрок Legacy ↔ игрок NHL 27 по имени, фамилии и дате рождения (без диакритики и знаков, roster.common.norm);
  только однозначные пары (одна строка с обеих сторон). game_id у EA между играми тот же, но конвейер отдаёт строки
  «доноров» новым игрокам — поэтому сшивка по человеку, не по номеру.
- **Что.** Таблицы stockcareerseason/playoff + player/goalie stats. В NHL 27 там только НХЛ (league 0) и АХЛ (1), годы
  1980–2026 (поле year — год окончания сезона − 1900, как у Legacy). Сезон — пара (год, лига): если у игрока в Legacy
  её нет, строка NHL 27 добавляется.
- **Обмен по ходу сезона.** У NHL 27 — строка на каждый клуб (Чинахов 2025/26: CBJ 29 игр и PIT 43), у Legacy — одна
  строка на сезон и лигу с клубами через дефис («DAL-NYI» у EA). Строки сезона складываются (merge_rows), клубы — по
  порядку (stint_order): у NHL 27 строки сезона идут по номеру клуба, а не по времени (Панарин 2025/26 — LA, потом NYR),
  поэтому клуб прошлого сезона — первым, клуб следующего (у последнего сезона — клуб игрока сейчас) — последним.
  До 24.10.2026 бралась только первая строка: терялись 902 строки полевых и 63 вратарей (пользователь: «перепроверь
  статистику… изучи Чинахова»).
- **Поля.** Общие — как есть (значения с rangelow каждой схемы); teams — аббревиатура клуба NHL 27 (exhibitionteams по
  index) или «-», как у Legacy (team_name: у EA клуб не записан, team = −1, — у сезонов ушедших из лиги игроков и
  закрытых или переехавших фарм-клубов; −101 — Аризона, переехавшая в Юту: «PHX» до 2013/14, потом «ARZ», как у EA);
  points = goals + assists; shootingpercentage — 0 (у Legacy не заполнено ни в одной
  строке); вратари: minutes = timeinnetseconds // 60, gaa = goalsagainst · 60 / minutes · 100, savepercent = отражённые
  / броски · 1000, losses — как losses NHL 27 (сверено на 148 общих сезонах: OT-поражения у Legacy не прибавлены).
  Новых полей NHL 27 (hits, timeoniceseconds, faceoffs…) у Legacy нет.
- Строки таблиц — по (game_id, year, league), как в базе. Повтор ничего не меняет. Отчёт — game/work/legacy-data/
  stats27/<набор>.json. Документация — docs/legacy-data.md, «Статистика из NHL 27».
"""
import json
import os
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
REPO = os.path.dirname(TOOLS)
sys.path.insert(0, TOOLS)
os.environ['NHL_GAME'] = 'legacy'
from roster.common import set_game  # noqa: E402
set_game('legacy')
from roster import nhl27  # noqa: E402
from roster.common import norm  # noqa: E402
from tdb import Tdb, load_meta  # noqa: E402

W_DIR = os.path.abspath(os.environ.get('LEGACY_DATA_WORK') or os.path.join(REPO, 'game', 'work', 'legacy-data'))
B = 'exhibitionplayerbiotable'
MIN_AGE = 18                                      # моложе — в НХЛ/АХЛ не играют: такой сезон в базе — чужой
COYOTES = -101                                    # клуб NHL 27 у сезонов Аризоны (с 2024 — Юта): записи клуба нет
TEAMS_MAX = 11                                    # поле teams — 96 бит: 11 знаков и ноль
KEYS27 = ('game_id', 'year', 'league', 'team')    # не складываются при обмене
TABLES = {'stockcareerseasonplayerstats': 'S', 'stockcareerplayoffplayerstats': 'S',
          'stockcareerseasongoaliestats': 'G', 'stockcareerplayoffgoaliestats': 'G'}


def people(db, skip_created=True):
    """{(имя, фамилия, дата): [game_id]} — по живым строкам биографии (у Legacy — кроме пустых созданных слотов)."""
    out = defaultdict(list)
    for r in db.live_rows(B):
        last = db.get_string(B, 'lastname', r)
        if skip_created and not last:
            continue
        key = (norm(db.get_string(B, 'firstname', r)), norm(last), db.value(B, 'year', r), db.value(B, 'month', r),
               db.value(B, 'day', r))
        out[key].append(db.value(B, 'game_id', r))
    return out


def pairs(L, N, how=None):
    """{game_id Legacy: game_id NHL 27} — однозначные пары (одна строка с каждой стороны на ключ), по шагам:
    1) имя, фамилия и дата рождения;
    2) фамилия и дата, имя — та же первая буква или одно внутри другого (Matt/Matthew, Bo/Benoit-Olivier, Viliam/
       Jozef-Viliam);
    3) имя и фамилия одни на всю базу с обеих сторон, тот же год, совпал месяц или день либо они переставлены;
    4) так же, только тот же год.
    3–4 — у EA ошибки в датах NHL 27: месяц на один меньше (Дворский, Леккеримяки), день и месяц переставлены (Куилл,
    Цельвегер), совсем другой день (Марчмент 06.03 вместо 18.06). Шаги 2–4 добавлены 24.10.2026: сверка с NHL 27 нашла
    90 таких игроков без истории. Тёзки с другим годом (Matt Murray 1994 и 1998) и близнецы (Седины: первая буква
    разная) — не сшиваются. how — Counter: сколько пар каким шагом."""
    a, b = people(L), people(N)
    out, used = {}, set()

    def put(ga, gb, step):
        if ga in out or gb in used:
            return
        out[ga] = gb
        used.add(gb)
        if how is not None:
            how[step] += 1

    for k, ga in a.items():
        if len(ga) == 1 and len(b.get(k, [])) == 1:
            put(ga[0], b[k][0], 'имя и дата')
    la, lb = defaultdict(list), defaultdict(list)
    for src, dst in ((a, la), (b, lb)):
        for k, gs in src.items():
            for g in gs:
                dst[(k[1],) + k[2:]].append((g, k[0]))
    for k, xs in la.items():
        ys = lb.get(k, [])
        if len(xs) == 1 and len(ys) == 1:
            fa, fb = xs[0][1], ys[0][1]
            if fa and fb and (fa[0] == fb[0] or fa in fb or fb in fa):
                put(xs[0][0], ys[0][0], 'фамилия и дата')
    na, nb = Counter(), Counter()
    for src, cnt in ((a, na), (b, nb)):
        for k, gs in src.items():
            cnt[k[:2]] += len(gs)
    ua = {k[:2]: (gs[0], k[2:]) for k, gs in a.items() if na[k[:2]] == 1}
    ub = {k[:2]: (gs[0], k[2:]) for k, gs in b.items() if nb[k[:2]] == 1}
    for strict in (True, False):
        for k, (ga, d) in ua.items():
            if k not in ub:
                continue
            gb, e = ub[k]
            if d[0] != e[0]:
                continue
            if strict and not (d[1] == e[1] or d[2] == e[2] or (d[1], d[2]) == (e[2], e[1])):
                continue
            put(ga, gb, 'имя и год, дата похожа' if strict else 'имя и год')
    return out


def team_name(team_abbr, tm, year):
    """Аббревиатура клуба сезона (year — поле year) или None, если у EA клуб не записан (team = −1)."""
    if tm in team_abbr:
        return team_abbr[tm]
    if tm == COYOTES:
        return 'PHX' if year + 1900 <= 2014 else 'ARZ'
    return None


def teams_str(names):
    """«CBJ-PIT» — клубы сезона по порядку; неизвестные (None) пропускаются, нет ни одного — «-». Длиннее поля — по 3
    буквы на клуб (фарм-клубы «BELV», «STOC»), ещё длиннее — «4TM», как у hockey-reference."""
    names = [n for n in names if n]
    if not names:
        return '-'
    s = '-'.join(names)
    if len(s) > TEAMS_MAX:
        s = '-'.join(n[:3] for n in names)
    return s if len(s) <= TEAMS_MAX else f'{len(names)}TM'


def stint_order(N, t27, rs, season_teams, year, last_year, now_teams):
    """Строки обмена по времени: клуб прошлого сезона — раньше, клуб следующего (у последнего сезона — клуб сейчас) —
    позже, прочие — между, в порядке NHL 27. season_teams — {год: {клубы}} игрока по обеим лигам таблицы."""
    prev = season_teams.get(year - 1, set())
    nxt = season_teams.get(year + 1, set()) if year < last_year else now_teams
    return sorted(rs, key=lambda r: (N.value(t27, 'team', r) in nxt) - (N.value(t27, 'team', r) in prev))


def convert(N, t27, rs, L, t, gid, team_abbr):
    """Строки NHL 27 одного сезона и лиги (по порядку) → {поле Legacy: значение}; несколько строк (обмен) — сумма."""
    v = {f: sum(N.value(t27, f, r) for r in rs) for f in N.by_name[t27]['fields'] if f not in KEYS27}
    v['year'], v['league'] = N.value(t27, 'year', rs[0]), N.value(t27, 'league', rs[0])
    out = {}
    for f in L.by_name[t]['fields']:
        if f in v:
            out[f] = v[f]
    out['game_id'] = gid
    out['teams'] = teams_str([team_name(team_abbr, N.value(t27, 'team', r), v['year']) for r in rs])
    out['points'] = v.get('goals', 0) + v.get('assists', 0)
    if 'shootingpercentage' in out or 'shootingpercentage' in L.by_name[t]['fields']:
        out['shootingpercentage'] = 0
    if TABLES[t] == 'G':
        minutes = v.get('timeinnetseconds', 0) // 60
        out['minutes'] = minutes
        out['gaa'] = round(v.get('goalsagainst', 0) * 60 / minutes * 100) if minutes else 0
        sa = v.get('shotsagainst', 0)
        out['savepercent'] = round((sa - v.get('goalsagainst', 0)) / sa * 1000) if sa else 0
    return out


def put_row(L, t, row, vals):
    fields, lows = L.by_name[t]['fields'], L.by_name[t]['lows']
    for f, (_, w) in fields.items():
        x = vals.get(f, 0)
        if L.by_name[t]['kinds'].get(f) == 0:
            L.set_string(t, f, row, str(x)[:w // 8 - 1])
        else:
            L.set(t, f, row, max(0, min((1 << w) - 1, int(x) - lows.get(f, 0))))


def run(path, N, dry=False):
    meta = os.path.join(os.path.dirname(path), 'nhlng-meta.xml')
    L = Tdb(open(path, 'rb').read(), load_meta(meta))
    how = Counter()
    pr = pairs(L, N, how)
    team_abbr = {N.get('exhibitionteams', 'index', x): N.get_string('exhibitionteams', 'abbrname', x)
                 for x in N.live_rows('exhibitionteams')}
    by27 = {v: k for k, v in pr.items()}                       # game_id NHL 27 → game_id Legacy
    by27_inv = pr                                              # game_id Legacy → game_id NHL 27
    link = defaultdict(set)                                    # exhibitionplayers: связь состава → game_id NHL 27
    for r in N.live_rows('exhibitionplayers'):
        link[N.value('exhibitionplayers', 'index', r)].add(N.value('exhibitionplayers', 'playerid', r))
    now = defaultdict(set)                                     # game_id NHL 27 → клубы в составах NHL 27 сейчас
    for r in N.live_rows('exhibitionrostertable'):
        for g in link.get(N.value('exhibitionrostertable', 'playerindex', r), ()):
            now[g].add(N.value('exhibitionrostertable', 'team', r))
    born = {L.value(B, 'game_id', r): L.value(B, 'year', r) + 1900 for r in L.live_rows(B)}
    rep = {'db': path, 'pairs': len(pr), 'pairs_by': dict(how), 'tables': {}, 'players': Counter()}
    for t in TABLES:
        n27 = defaultdict(list)
        for r in N.live_rows(t):
            gid = by27.get(N.value(t, 'game_id', r))
            if gid is not None:
                n27[gid].append(r)
        keep, drop = [], Counter()
        for r in L.live_rows(t):
            gid, year, lg = L.value(t, 'game_id', r), L.value(t, 'year', r), L.value(t, 'league', r)
            if gid in n27:
                drop['заменён историей NHL 27'] += 1
                continue
            if gid in born and year + 1900 - born[gid] < MIN_AGE:
                drop[f'игроку меньше {MIN_AGE} (чужой сезон)'] += 1
                continue
            keep.append(((gid, year, lg), L.record(t, r)))
        if len(L.live_rows(t)) != L.by_name[t]['rows']:
            raise SystemExit(f'{t}: есть удалённые записи — такую базу не правлю')
        add, merged = [], 0
        for gid, rs in n27.items():
            seasons, teams = defaultdict(list), defaultdict(set)
            for r in rs:
                seasons[(N.value(t, 'year', r), N.value(t, 'league', r))].append(r)
                teams[N.value(t, 'year', r)].add(N.value(t, 'team', r))
            last = max(teams)
            for (year, lg), srs in seasons.items():
                if len(srs) > 1:
                    srs = stint_order(N, t, srs, teams, year, last, now.get(by27_inv[gid], set()))
                    merged += 1
                add.append(((gid, year, lg), convert(N, t, srs, L, t, gid, team_abbr)))
                rep['players'][gid] += 1
        allr = sorted([(k, raw, None) for k, raw in keep] + [(k, None, v) for k, v in add], key=lambda x: x[0])
        years = Counter(k[1] + 1900 for k, _ in add)
        rep['tables'][t] = {'before': len(L.live_rows(t)), 'after': len(allr), 'from_nhl27': len(add), 'merged': merged,
                            'dropped': dict(drop), 'by_year': dict(sorted(years.items()))}
        if dry:
            continue
        L.resize(t, len(allr))
        zero = bytes(L.by_name[t]['reclen'])
        for i, (k, raw, vals) in enumerate(allr):
            if raw is not None:
                L.put_record(t, i, raw)
            else:
                L.put_record(t, i, zero)
                put_row(L, t, i, vals)
    rep['players_with_new'] = len(rep['players'])
    rep['players'] = {str(k): n for k, n in rep['players'].items()}
    if not dry:
        L.fix()
        bad = L.verify()
        if bad:
            raise SystemExit(f'{path}: CRC не сошлись')
        if open(path, 'rb').read() != bytes(L.d):
            tmp = path + '.part'
            open(tmp, 'wb').write(L.d)
            os.replace(tmp, path)
            rep['written'] = True
    return rep


CHECK = {'S': ('gamesplayed', 'goals', 'assists', 'penaltyminutes', 'plusminus', 'shots', 'powerplaygoals',
               'shorthandedgoals', 'gamewinninggoals'),
         'G': ('gamesplayed', 'wins', 'losses', 'shutouts', 'goalsagainst', 'shotsagainst')}


def check(path, N):
    """Сверка базы с NHL 27 (эталон — пользователь 24.10.2026: «в NHL 27 уже норм… просто сверься по ней»): у каждой пары
    игроков каждый сезон (год, лига) каждой таблицы — суммы NHL 27 по клубам против строки базы (CHECK, у вратарей ещё
    минуты), набор клубов. Считается заново из строк NHL 27, без convert, — ловит и ошибки самого переноса. Плюс игроки
    NHL 27 с историей, которых сшивка не нашла, но в базе есть тот же человек по имени или по фамилии и дате."""
    L = Tdb(open(path, 'rb').read(), load_meta(os.path.join(os.path.dirname(path), 'nhlng-meta.xml')))
    pr = pairs(L, N)
    team_abbr = {N.get('exhibitionteams', 'index', x): N.get_string('exhibitionteams', 'abbrname', x)
                 for x in N.live_rows('exhibitionteams')}
    by27 = {v: k for k, v in pr.items()}
    rep, ex = Counter(), defaultdict(list)
    hist27 = set()
    for t, kind in TABLES.items():
        fields = CHECK[kind]
        n = defaultdict(lambda: defaultdict(list))
        for r in N.live_rows(t):
            g27 = N.value(t, 'game_id', r)
            hist27.add(g27)
            if g27 in by27:
                n[by27[g27]][(N.value(t, 'year', r), N.value(t, 'league', r))].append(r)
        lrows = defaultdict(dict)
        for r in L.live_rows(t):
            gid = L.value(t, 'game_id', r)
            if gid in n:
                lrows[gid][(L.value(t, 'year', r), L.value(t, 'league', r))] = r
        for gid, seasons in n.items():
            for key, rs in seasons.items():
                lr = lrows[gid].pop(key, None)
                if lr is None:
                    rep[f'{t}: сезона нет в базе'] += 1
                    if len(ex[f'{t}: нет']) < 10:
                        ex[f'{t}: нет'].append([gid, key[0] + 1900, key[1]])
                    continue
                want = {f: sum(N.value(t, f, r) for r in rs) for f in fields}
                if kind == 'G':
                    want['minutes'] = sum(N.value(t, 'timeinnetseconds', r) for r in rs) // 60
                got = {f: L.value(t, f, lr) for f in want}
                tw = {team_name(team_abbr, N.value(t, 'team', r), key[0]) for r in rs} - {None}
                tg = set(L.get_string(t, 'teams', lr).split('-')) - {''}
                bad = [f for f in want if want[f] != got[f]] + (['teams'] if (tw or tg) and {x[:3] for x in tw} != {x[:3] for x in tg} else [])
                rep[f'{t}: {"совпало" if not bad else "не совпало"}'] += 1
                if bad and len(ex[t]) < 15:
                    ex[t].append([gid, key[0] + 1900, key[1], bad, {f: [want[f], got[f]] for f in bad if f != 'teams'},
                                  sorted(tw), L.get_string(t, 'teams', lr)])
            for key in lrows[gid]:
                rep[f'{t}: лишний сезон в базе'] += 1
    # пары, которые сшивка пропустила: тот же человек по имени (другая дата) или по фамилии и дате (другое имя)
    lf, nf = people(L), people(N)
    by_name, by_last = defaultdict(list), defaultdict(list)
    for k, gs in lf.items():
        by_name[k[:2]] += gs
        by_last[(k[1],) + k[2:]] += gs
    miss = []
    for k, gs in nf.items():
        if len(gs) != 1 or gs[0] not in hist27 or gs[0] in by27:
            continue
        near = sorted(set(by_name.get(k[:2], [])) | set(by_last.get((k[1],) + k[2:], [])))
        if near:
            miss.append([gs[0], f'{k[0]} {k[1]}', [k[2] + 1900, k[3] + 1, k[4] + 1], near])
    rep['история NHL 27 без пары, но похожий игрок в базе'] = len(miss)
    return {'db': path, 'pairs': len(pr), 'counts': dict(sorted(rep.items())), 'examples': ex, 'near_misses': miss}


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    args = sys.argv[1:]
    dry = '--dry-run' in args
    N = nhl27.open_db(args[args.index('--db27') + 1] if '--db27' in args else None)
    sets = [a for a in args if a in ('out', 'out-ahl32')] or ['out', 'out-ahl32']
    if args and args[0] == 'check':
        for s in sets:
            path = os.path.join(W_DIR, s, 'db', 'nhlng.db')
            if os.path.isfile(path):
                rep = check(path, N)
                fn = os.path.join(W_DIR, 'stats27', f'{s}-check.json')
                json.dump(rep, open(fn, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
                print(f"{s}: пар игроков {rep['pairs']}; отчёт — {fn}")
                for k, v in rep['counts'].items():
                    print(f'  {k}: {v}')
        return
    for s in sets:
        path = os.path.join(W_DIR, s, 'db', 'nhlng.db')
        if not os.path.isfile(path):
            continue
        rep = run(path, N, dry)
        os.makedirs(os.path.join(W_DIR, 'stats27'), exist_ok=True)
        json.dump(rep, open(os.path.join(W_DIR, 'stats27', f'{s}.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        print(f"{s}: пар игроков {rep['pairs']} ({', '.join(f'{k} {v}' for k, v in rep['pairs_by'].items())}), "
              f"с историей NHL 27 — {rep['players_with_new']}"
              + (' (проба, не записано)' if dry else '' if rep.get('written') else ' (база уже такая)'))
        for t, x in rep['tables'].items():
            yrs = x['by_year']
            print(f"  {t}: было {x['before']}, стало {x['after']}; из NHL 27 {x['from_nhl27']}"
                  + (f" ({min(yrs)}–{max(yrs)})" if yrs else '') + f", из них обменов {x['merged']}; убрано {x['dropped']}")
        if rep.get('written'):
            import subprocess
            subprocess.run([sys.executable, os.path.join(HERE, 'draft_roster.py'), path,
                            os.path.join(os.path.dirname(path), 'draft_roster.db')], check=True)


if __name__ == '__main__':
    main()
