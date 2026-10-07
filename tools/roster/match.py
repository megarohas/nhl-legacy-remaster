"""Этап match: игроки players.json → строки exhibitionplayerbiotable входной базы.

Порядок проверок (вратарь сопоставляется только с вратарём, полевой — с полевым):
1. `artid` = ID EA (сквозной с NHL 13: Кросби 1082), если EA его знает и ID < 16384, —
   с проверкой фамилии и года рождения (±1) или точной даты рождения;
2. фамилия + дата рождения; у однофамильцев с одной датой (близнецы) решает имя;
3. имя и фамилия + почти та же дата (год и месяц или день; или месяц и день при годе ±1);
4. дата рождения + похожая фамилия (≥ 0,8) + первая буква имени.
Логика 2–4 — по образцу matching.py из puckpeak-nhl-legacy-rosters (MIT). Одну строку
не отдают двоим: при споре остаётся лучший способ сопоставления.
"""
from collections import defaultdict
from difflib import SequenceMatcher

from tdb import Tdb
from tdb_read import load_meta

from .build import same_first
from .common import norm, read_json, write_json
from .dbview import View

HOW_RANK = {'artid': 0, 'birth': 1, 'name': 2, 'birth+similar': 3}


def load_db(paths, path=None):
    path = path or paths.db_in
    meta = paths.meta_for(path)
    return Tdb(open(path, 'rb').read(), load_meta(meta)), meta


def index(v):
    by_lb, by_name, by_birth, by_art = defaultdict(list), defaultdict(list), defaultdict(list), defaultdict(list)
    for r in range(v.nbio):
        if v.created_slot(r):
            continue
        b = v.birth(r)
        ln, fn = norm(v.s('lastname', r)), norm(v.s('firstname', r))
        by_lb[(ln, b)].append(r)
        by_name[(fn, ln)].append(r)
        by_birth[b].append((ln, r))
        by_art[v.g('artid', r)].append(r)
    return by_lb, by_name, by_birth, by_art


def best_row(v, rows):
    """Несколько строк одного человека: та, что в составе клуба НХЛ, потом с большим числом записей."""
    return max(rows, key=lambda r: (any(t < 32 for t in v.teams_of[r]), len(v.teams_of[r]), -r))


def match_one(v, idx, p):
    by_lb, by_name, by_birth, by_art = idx
    goalie = p['pos'] == 'G'
    kind = lambda rows: [r for r in rows if v.is_goalie(r) == goalie]
    fn, ln = norm(p['first']), norm(p['last'])
    y, m, d = p['birth']
    ea = p.get('ea') or {}
    if ea.get('ea_id') and ea['ea_id'] < 16384:
        # фамилия похожа и год рождения ±1 — или точная дата рождения при другой фамилии
        # (во входной базе Кросби переименован в «Megarohas» проверкой мода)
        rows = [r for r in kind(by_art.get(ea['ea_id'], []))
                if ((norm(v.s('lastname', r)) == ln or SequenceMatcher(None, norm(v.s('lastname', r)), ln).ratio() >= 0.8)
                    and abs(v.birth(r)[0] - y) <= 1) or v.birth(r) == (y, m, d)]
        if rows:
            return best_row(v, rows), 'artid'
    rows = kind(by_lb.get((ln, (y, m, d)), []))
    if rows:
        if len(rows) > 1:
            rows = [r for r in rows if same_first(v.s('firstname', r), p['first'])] or rows
        return best_row(v, rows), 'birth'
    # полное имя и почти та же дата: тот же год и месяц или день (у Берроуза в базе месяц на один
    # меньше), либо те же месяц и день при годе ±1. Однофамилец-тёзка с другой датой — другой человек
    # (в базе есть юниор Jake Evans 1995 г. р., а у «Монреаля» Jake Evans 1996-го)
    near = lambda b: (b[0] == y and (b[1] == m or b[2] == d)) or (abs(b[0] - y) <= 1 and (b[1], b[2]) == (m, d))
    rows = [r for r in kind(by_name.get((fn, ln), [])) if near(v.birth(r))]
    if rows:
        return best_row(v, rows), 'name'
    rows = kind([r for l2, r in by_birth.get((y, m, d), [])
                 if SequenceMatcher(None, l2, ln).ratio() >= 0.8 and norm(v.s('firstname', r))[:1] == fn[:1]])
    if rows:
        return best_row(v, rows), 'birth+similar'
    return None, 'none'


def run(paths, log=print):
    db, meta = load_db(paths)
    v = View(db)
    data = read_json(paths.players)
    if not data:
        raise SystemExit(f'нет {paths.players} — сначала build')
    idx = index(v)
    found = {}
    for p in data['players']:
        row, how = match_one(v, idx, p)
        found[p['nhl_id']] = (row, how)
    # одна строка — одному игроку
    by_row = defaultdict(list)
    for pid, (row, how) in found.items():
        if row is not None:
            by_row[row].append(pid)
    conflicts = []
    for row, pids in by_row.items():
        if len(pids) > 1:
            pids.sort(key=lambda pid: HOW_RANK[found[pid][1]])
            for pid in pids[1:]:
                conflicts.append({'nhl_id': pid, 'row': row, 'kept': pids[0]})
                found[pid] = (None, 'conflict')
    players = {p['nhl_id']: p for p in data['players']}
    out = {}
    for pid, (row, how) in found.items():
        p = players[pid]
        rec = {'row': row, 'how': how, 'name': f"{p['first']} {p['last']}", 'team': p['team']}
        if row is not None:
            rec.update({'db_name': v.name(row), 'db_birth': list(v.birth(row)), 'db_teams': v.teams_of[row],
                        'db_artid': v.g('artid', row), 'db_overall': v.overall(row)})
        out[str(pid)] = rec
    counts = defaultdict(int)
    for rec in out.values():
        counts[rec['how']] += 1
    write_json(paths.matched, {'db': paths.db_in, 'counts': dict(counts), 'conflicts': conflicts, 'players': out})
    n = sum(1 for r in out.values() if r['row'] is not None)
    log(f'match: сопоставлено {n} из {len(out)} ({dict(counts)}) -> {paths.matched}')
    return out
