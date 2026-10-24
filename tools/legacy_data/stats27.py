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


def pairs(L, N):
    """{game_id Legacy: game_id NHL 27} — однозначные пары по имени и дате рождения."""
    a, b = people(L), people(N)
    return {ga[0]: b[k][0] for k, ga in a.items() if len(ga) == 1 and len(b.get(k, [])) == 1}


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
    v['year'] = N.value(t27, 'year', rs[0])
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
    pr = pairs(L, N)
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
    rep = {'db': path, 'pairs': len(pr), 'tables': {}, 'players': Counter()}
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


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    args = sys.argv[1:]
    dry = '--dry-run' in args
    N = nhl27.open_db(args[args.index('--db27') + 1] if '--db27' in args else None)
    sets = [a for a in args if a in ('out', 'out-ahl32')] or ['out', 'out-ahl32']
    for s in sets:
        path = os.path.join(W_DIR, s, 'db', 'nhlng.db')
        if not os.path.isfile(path):
            continue
        rep = run(path, N, dry)
        os.makedirs(os.path.join(W_DIR, 'stats27'), exist_ok=True)
        json.dump(rep, open(os.path.join(W_DIR, 'stats27', f'{s}.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        print(f"{s}: пар игроков {rep['pairs']}, с историей NHL 27 — {rep['players_with_new']}"
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
