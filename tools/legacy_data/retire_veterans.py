"""Ушедшие из НХЛ игроки базы 2015 года — на пенсию (без клуба), офлайн по готовой базе NHL Legacy: этап build-all
retire (после collect). То же, что `tools/roster write --retire-veterans 2010` (docs/roster-pipeline.md), но без
пересборки составов: сетевой кэш конвейера после инцидента 09.10 неполон (составы НХЛ, рейтинги, звенья — только
через сеть), а составы 2026/27 менять не нужно.

Ветеран — игрок входной базы конвейера (nhl32: составы 2015), который там в составе клуба НХЛ (0–29), а в готовой
базе — только в клубах вне НХЛ (АХЛ, Европа, CHL): тот же game_id, имя и дата рождения. Без флага конвейер ставит
таких на места тех, кто ушёл в НХЛ из клубов АХЛ/Европы/юниоров (у пользователя 94, из них 67 с OVR ≥ 80: Toews,
Price, Kopitar…). Место ветерана — по правилам write.free_vacancy (год 2010 накрывает всех, поэтому правил «ушедший
из НХЛ моложе» нет):
1) запись не одета, без звеньев и буквы — убирается (в клубе на игрока меньше);
2) иначе звенья, rosterstatus и букву получает запасной клуба того же амплуа (не одет, без звеньев), лучший по OVR;
3) нет такого — запасной того же амплуа из другого клуба той же лиги (где запасных этого амплуа больше всего, без
   клубов, пересобранных конвейером), с номером и условиями места ветерана;
4) иначе ветеран остаётся (в отчёте).
Ветеран без клуба — как у конвейера: team — сборная (особая команда) + 1, если он в ней, иначе 0; контракт обнуляется.
Записи составов клуба — по возрастанию связи, key = команда × 40 + место. Повторный запуск ничего не меняет.

    python tools/legacy_data/retire_veterans.py БАЗА_2015 БАЗА [--meta META] [--report ОТЧЁТ.json]
"""
import collections
import json
import os
import sys

TOOLS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, TOOLS)
os.environ['NHL_GAME'] = 'legacy'
from roster import common  # noqa: E402

common.set_game('legacy')
from roster import dbview  # noqa: E402
from roster.dbview import B, FLAGS, JUNIOR, NATIONAL, NHL, R, SPECIAL, T  # noqa: E402
from tdb import Tdb  # noqa: E402
from tdb_read import load_meta  # noqa: E402

SLOT_TERMS = ['proteam', 'contractstatus', 'contractdollars', 'contractlength', 'contractis2way',
              'contractismultiyear', 'contractneedsentrylevel', 'yearufa', 'extensionlength', 'extensiondollars',
              'extensionis2way', 'juniorteam', 'juniorleague', 'junioryearlost']   # как в roster/write.py
CONTRACT = ['proteam', 'contractlength', 'contractdollars', 'contractstatus', 'contractis2way', 'contractismultiyear',
            'contractneedsentrylevel', 'extensionlength', 'extensiondollars', 'extensionis2way']
MAX_PER_TEAM = 40
OWN_CLUBS = set(range(74, 88)) | set(common.AHL_CLUBS)    # пересобраны конвейером: Liiga (--league), CV/HSK (--ahl32)


def kind(pos):
    return 'G' if pos == 4 else 'D' if pos == 3 else 'F'


def veterans(old, new):
    """[(строка био в готовой базе, game_id)] — бывшие игроки НХЛ 2015 года только в клубах вне НХЛ."""
    out = []
    for r_old, g in enumerate(old.gid):
        if not any(t in range(0, 30) for t in old.teams_of.get(r_old, [])):
            continue
        r = new.row_of_gid.get(g)
        if r is None or new.name(r) != old.name(r_old) or new.birth(r) != old.birth(r_old):
            continue
        teams = new.teams_of.get(r, [])
        if any(t in dbview.CLUBS for t in teams) and not any(t in NHL for t in teams):
            out.append(r)
    return out


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
    args = sys.argv[1:]
    opt = {}
    for k in ('--meta', '--report'):
        if k in args:
            i = args.index(k)
            opt[k] = args[i + 1]
            del args[i:i + 2]
    if len(args) != 2:
        sys.exit(__doc__)
    base_path, db_path = args
    meta = load_meta(opt.get('--meta') or os.path.join(os.path.dirname(db_path), 'nhlng-meta.xml'))
    old = dbview.View(Tdb(open(base_path, 'rb').read(), meta))
    db = Tdb(open(db_path, 'rb').read(), meta)
    v = dbview.View(db)
    vets = veterans(old, v)
    vet_set = set(vets)
    row_of_link = lambda l: v.row_of_gid.get(v.link_gid.get(l))   # noqa: E731
    entries = [dict(e) for e in v.entries]
    vac = [e for e in entries if e['team'] in dbview.CLUBS and row_of_link(e['playerindex']) in vet_set]
    vac.sort(key=lambda e: (e['team'], e['playerindex']))
    kept = [e for e in entries if not (e['team'] in dbview.CLUBS and row_of_link(e['playerindex']) in vet_set)]
    actions, events = collections.Counter(), []
    refill = []

    def is_spare(x, team, want):
        r = row_of_link(x['playerindex'])
        return (x['team'] == team and r is not None and r not in vet_set and v.ai(r) is not None
                and not x['rosterstatus'] and not x['captain'] and not any(x[f] for f in FLAGS)
                and kind(v.g('position', r)) == want), r

    for e in vac:
        t = e['team']
        r_vet = row_of_link(e['playerindex'])
        pos = v.g('position', r_vet)
        want = kind(pos)
        busy = e['rosterstatus'] or e['captain'] or any(e[f] for f in FLAGS)
        name = v.name(r_vet)
        if not busy:
            actions['место запасного убрано'] += 1
            events.append({'team': t, 'veteran': name, 'what': 'место запасного убрано'})
            continue
        mine = [(x, r) for x in kept for ok, r in [is_spare(x, t, want)] if ok]
        if mine:
            x, r = min(mine, key=lambda xr: (v.g('position', xr[1]) != pos, -v.overall(xr[1]), xr[0]['playerindex']))
            for f in FLAGS:
                x[f] = e[f]
            x['rosterstatus'], x['captain'] = e['rosterstatus'], e['captain']
            actions['запасной клуба'] += 1
            events.append({'team': t, 'veteran': name, 'what': 'запасной клуба', 'player': v.name(r)})
            continue
        league = db.get(T, 'league', t)
        pool = collections.defaultdict(list)
        for x in kept:
            u = x['team']
            if u == t or u not in dbview.CLUBS or u in OWN_CLUBS or db.get(T, 'league', u) != league:
                continue
            ok, r = is_spare(x, u, want)
            if ok:
                pool[u].append((x, r))
        if pool:
            u = min(pool, key=lambda u: (-len(pool[u]), u))
            x, r = min(pool[u], key=lambda xr: (v.g('position', xr[1]) != pos, -v.overall(xr[1]), xr[0]['playerindex']))
            kept.remove(x)
            ne = dict(e)
            ne['playerindex'], ne['playerstyle'] = x['playerindex'], x['playerstyle']
            db.set(B, 'team', r, t + 1)
            db.set(B, 'jersey', r, e['jersey'])
            for f in (f for f in SLOT_TERMS if f in db.by_name[B]['fields']):
                db.set(B, f, r, db.get(B, f, r_vet))
            refill.append(ne)
            actions['запасной другого клуба лиги'] += 1
            events.append({'team': t, 'veteran': name, 'what': 'запасной другого клуба лиги', 'player': v.name(r),
                           'from_team': u})
            continue
        refill.append(e)                                        # некем заменить — ветеран остаётся
        vet_set.discard(r_vet)
        actions['ветеран оставлен (нет замены)'] += 1
        events.append({'team': t, 'veteran': name, 'what': 'ветеран оставлен (нет замены)'})
    # ветераны без клуба и контракта (как у конвейера: в сборной — эта команда + 1)
    retired = []
    final_entries = kept + refill
    teams_now = collections.defaultdict(list)
    for e in final_entries:
        r = row_of_link(e['playerindex'])
        if r is not None:
            teams_now[r].append(e['team'])
    for r in vets:
        if r not in vet_set:
            continue
        if any(t in dbview.CLUBS or t in NHL for t in teams_now.get(r, [])):
            continue
        special = sorted(t for t in teams_now.get(r, []) if t in SPECIAL)
        nat = [t for t in special if t in NATIONAL]
        db.set(B, 'team', r, (nat or special)[0] + 1 if special else 0)
        for f in CONTRACT:
            if f in db.by_name[B]['fields']:
                db.set(B, f, r, 0)
        retired.append({'row': r, 'name': v.name(r), 'birth': v.birth(r)[0], 'ovr': v.overall(r)})
    # записи составов: по командам, внутри — по связи, key = команда × 40 + место
    per_team = collections.defaultdict(list)
    for e in final_entries:
        per_team[e['team']].append(e)
    rows = []
    for team in sorted(per_team):
        es = sorted(per_team[team], key=lambda e: e['playerindex'])
        if len(es) > MAX_PER_TEAM:
            sys.exit(f'в команде {team} {len(es)} игроков (больше {MAX_PER_TEAM})')
        for k, e in enumerate(es):
            e['key'] = team * MAX_PER_TEAM + k
            rows.append(e)
    if not vets:
        print(f'{db_path}: ветеранов 2015 года в клубах вне НХЛ нет — без правки')
        return
    if db.by_name[R]['rows'] != len(rows):
        db.resize(R, len(rows))
    fields = list(db.by_name[R]['fields'])
    for i, e in enumerate(rows):
        for f in fields:
            db.set(R, f, i, e.get(f, 0))
    db.fix()
    if db.verify():
        sys.exit(f'{db_path}: CRC не сошлись')
    with open(db_path + '.part', 'wb') as f:
        f.write(db.d)
    os.replace(db_path + '.part', db_path)
    sizes = collections.Counter(e['team'] for e in rows if e['team'] in dbview.CLUBS or e['team'] in NHL)
    small = min(sizes.items(), key=lambda kv: kv[1])
    print(f'{db_path}: ветеранов {len(vets)}, без клуба {len(retired)}; места: {dict(actions)}; записей составов '
          f'{len(entries)} → {len(rows)}; наименьший состав — команда {small[0]}: {small[1]}')
    if opt.get('--report'):
        with open(opt['--report'], 'w', encoding='utf-8', newline='\n') as f:
            json.dump({'base': base_path, 'db': db_path, 'veterans': len(vets), 'actions': dict(actions),
                       'retired': retired, 'events': events, 'smallest': small}, f, ensure_ascii=False, indent=1)


if __name__ == '__main__':
    main()
