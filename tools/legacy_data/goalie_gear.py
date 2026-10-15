"""Командная экипировка вратарей (tools/legacy_data/goalie_gear.json): каждому вратарю клуба — набор вратаря этого
клуба, заготовленный EA (stockgoalieequipment), у клуба без набора — белая экипировка с чёрной графикой и белая
маска. Этап build-all «goaliegear» (после tape).

    python tools/legacy_data/goalie_gear.py db БАЗА.db [БАЗА.db …] [--dry-run]   # nhlng.db, draft_roster.db
    python tools/legacy_data/goalie_gear.py save СЕЙВ [--write]                   # сохранённый состав (ROSTER …)

Как устроено (разбор 12.10.2026, docs/legacy-data.md, «Экипировка вратарей»):
- набор клуба — строка stockgoalieequipment с team = клуб + 1: модели щитков, блина, ловушки и клюшки, маска
  (masktype, maskid → rendering/goaliehelmet/goaliehelmet_<masktype>_<maskid>_cm.rx2), цвета 9 зон щитков, блина и
  ловушки и 3 зон клюшки, showcustomcolors/showcustomstick (0 — цвета клуба из stockteamequipmenttable). У клуба 1–5
  наборов; основной — тот, чья маска равна exhibitionteams.goaliemask<masktype>_starter, запасной — _backup;
- вратари клуба — по составу (exhibitionrostertable): основной (g1) — основной набор, запасной (g2) — запасной, третий
  и дальше — следующие по порядку (наборов меньше — последний). Клуб вратаря — первый клуб лиг club_leagues в его
  записях составов (сборные, Матч звёзд, Top Prospects, Winter Classic, EASHL, заготовки Custom — не клубы; у НХЛ —
  только строки 0…31). Свободные агенты не трогаются;
- в exhibitiongoalieequipment вратаря копируются все поля набора, кроме своих: jerseytuck, sticktapecolor,
  keepcustomiftraded, keepcustomstickiftraded;
- mask_names (по желанию): набор клуба, но маска своя;
- без набора (SEA, VGK, CV, HSK) и клубы из white_names (все спорные — решение пользователя 12.10) (наборы прежних клубов на переименованных
  слотах, у Юты — Аризоны): модели вратаря свои, маска 0/120 (белая), цвета зон — white.zones и white.stick,
  showcustomcolors и showcustomstick = 1.
draft_roster.db (там нет stockgoalieequipment и exhibitionteams) берёт план у nhlng.db рядом, по game_id. Сейв — по своим
же таблицам (составы пользователя). Повторный запуск ничего не меняет; после записи — проверка CRC.
"""
import json
import os
import sys
import time
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from tdb import SaveFile, Tdb, load_meta  # noqa: E402

SPEC = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'goalie_gear.json')
W = os.environ.get('LEGACY_DATA_WORK', os.path.join(ROOT, 'game', 'work', 'legacy-data'))
CACHE_META = os.path.join(ROOT, 'nhl-legacy-port', 'userdata', 'cache', 'guest', 'db', 'nhlng-meta.xml')
EQ, SG, T = 'exhibitiongoalieequipment', 'stockgoalieequipment', 'exhibitionteams'
B, P, R = 'exhibitionplayerbiotable', 'exhibitionplayers', 'exhibitionrostertable'
OWN = {'game_id', 'jerseytuck', 'sticktapecolor', 'keepcustomiftraded', 'keepcustomstickiftraded'}


def spec():
    return json.load(open(SPEC, encoding='utf-8'))


def white_values(db, sp, row):
    """Белый набор: модели вратаря свои, маска и цвета — из spec['white']."""
    w = sp['white']
    v = {'masktype': w['masktype'], 'maskid': w['maskid'], 'showcustomcolors': 1, 'showcustomstick': 1}
    for part in ('pads', 'blocker', 'trapper'):
        for z, rgb in w['zones'].items():
            for c, x in zip('rgb', rgb):
                v[f'{part}zone{z}color_{c}'] = x
    for z, rgb in w['stick'].items():
        for c, x in zip('rgb', rgb):
            v[f'stickzone{z}color_{c}'] = x
    return v


def plan(db):
    """{game_id: (значения полей, отчёт)} по составам базы db; и сводка по клубам."""
    sp = spec()
    leagues, nhl_rows = set(sp['club_leagues']), sp['nhl_rows']
    white_names = set(sp['white_names'])
    nt = db.by_name[T]['rows']
    tf = db.by_name[T]['fields']

    def is_club(t):
        if t >= nt or ('active' in tf and not db.get(T, 'active', t)):
            return False
        lg = db.get(T, 'league', t)
        return lg in leagues and (lg != 0 or t < nhl_rows)
    fields = [f for f in db.by_name[EQ]['fields'] if f not in OWN]
    sets = defaultdict(list)
    for r in db.live_rows(SG):
        sets[db.get(SG, 'team', r) - 1].append(r)
    link = {db.get(P, 'index', r): db.get(P, 'playerid', r) for r in db.live_rows(P)}
    bio = {db.get(B, 'game_id', r): r for r in db.live_rows(B)}
    eq_gids = {db.get(EQ, 'game_id', r) for r in db.live_rows(EQ)}
    roster = defaultdict(list)                # клуб → [(порядок, game_id)]
    clubs_of = defaultdict(list)
    for r in db.live_rows(R):
        g = link.get(db.get(R, 'playerindex', r))
        if g not in eq_gids or g not in bio or db.get(B, 'position', bio[g]) != 4:
            continue
        t = db.get(R, 'team', r)
        if not is_club(t):
            continue
        order = 0 if db.get(R, 'g1', r) else 1 if db.get(R, 'g2', r) else 2
        clubs_of[g].append((0 if t < nhl_rows else 1, t, order))
    for g, cl in clubs_of.items():
        _, t, order = min(cl)
        roster[t].append((order, g))
    out, summary = {}, {}
    for t, gs in sorted(roster.items()):
        name = db.get_string(T, 'fullname', t)
        gs.sort()
        rows = sets.get(t, [])
        if rows and name not in white_names:
            def rank(r):
                mt, mid = db.get(SG, 'masktype', r), db.get(SG, 'maskid', r)
                st = db.get(T, f'goaliemask{mt}_starter', t) if f'goaliemask{mt}_starter' in tf else None
                bk = db.get(T, f'goaliemask{mt}_backup', t) if f'goaliemask{mt}_backup' in tf else None
                return (0 if mid == st else 1 if mid == bk else 2, db.get(SG, 'key', r))
            rows = sorted(rows, key=rank)
            used = []
            mask = sp.get('mask_names', {}).get(name, {}).get('mask')
            for k, (_, g) in enumerate(gs):
                s = rows[min(k, len(rows) - 1)]
                vals = {f: db.get(SG, f, s) for f in fields}
                if mask:                                   # маска набора с логотипом прежнего клуба — своя
                    vals['masktype'], vals['maskid'] = mask
                out[g] = (vals, f'{name}: набор key {db.get(SG, "key", s)} (маска {vals["masktype"]}_{vals["maskid"]}'
                                + (', вместо маски набора' if mask else '') + ')')
                used.append(db.get(SG, 'key', s))
            summary[t] = (name, 'набор', len(gs), len(rows), used)
        else:
            why = 'нет набора' if not rows else 'спорный набор — white_names'
            for _, g in gs:
                out[g] = (white_values(db, sp, None), f'{name}: белый ({why})')
            summary[t] = (name, 'белый', len(gs), len(rows), why)
    return out, summary


def apply_plan(db, pl):
    """Значения плана → exhibitiongoalieequipment базы db (по game_id). → (вратарей изменено, значений)."""
    rows = {db.get(EQ, 'game_id', r): r for r in db.live_rows(EQ)}
    players = values = 0
    for g, (vals, _) in pl.items():
        r = rows.get(g)
        if r is None:
            continue
        n = 0
        for f, v in vals.items():
            if db.get(EQ, f, r) != v:
                db.set(EQ, f, r, v)
                n += 1
        if n:
            players += 1
            values += n
    return players, values


def report(summary, pl, log=print):
    sets = sum(1 for s in summary.values() if s[1] == 'набор')
    whites = [s for s in summary.values() if s[1] == 'белый']
    log(f'  клубов с вратарями: {len(summary)}; по набору клуба: {sets} клубов, '
        f'{sum(s[2] for s in summary.values() if s[1] == "набор")} вратарей; белый: {len(whites)} клубов, '
        f'{sum(s[2] for s in whites)} вратарей')
    for t, s in sorted(summary.items()):
        if s[1] == 'белый':
            log(f'    белый: {t} {s[0]} ({s[4]}, вратарей {s[2]})')


def meta_for(path):
    m = os.path.join(os.path.dirname(path), 'nhlng-meta.xml')
    if not os.path.isfile(m):
        m = os.path.join(W, 'out-ahl32', 'db', 'nhlng-meta.xml')
    return load_meta(m)


def write_db(path, db, meta):
    db.fix()
    tmp = path + '.part'
    open(tmp, 'wb').write(bytes(db.d))
    if Tdb(open(tmp, 'rb').read(), meta).verify():
        os.remove(tmp)
        sys.exit(f'{path}: CRC не сходятся после записи — база не тронута')
    os.replace(tmp, path)


def cmd_db(paths, dry):
    for path in paths:
        meta = meta_for(path)
        db = Tdb(open(path, 'rb').read(), meta)
        src = db
        if SG not in db.by_name or T not in db.by_name:     # draft_roster.db — план у nhlng.db рядом
            nh = os.path.join(os.path.dirname(path), 'nhlng.db')
            src = Tdb(open(nh, 'rb').read(), meta)
        pl, summary = plan(src)
        players, values = apply_plan(db, pl)
        print(f'{path}: вратарей изменено {players}, значений {values}' + (' (план — по nhlng.db рядом)'
                                                                            if src is not db else ''))
        if src is db:
            report(summary, pl)
            os.makedirs(os.path.join(W, 'goaliegear'), exist_ok=True)
            rep = os.path.join(W, 'goaliegear', os.path.basename(os.path.dirname(os.path.dirname(path))) + '.json')
            json.dump({'clubs': {str(t): {'name': s[0], 'kind': s[1], 'goalies': s[2], 'sets': s[3],
                                          'used': s[4]} for t, s in summary.items()},
                       'goalies': {str(g): why for g, (_, why) in pl.items()}},
                      open(rep, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
            print(f'  отчёт: {rep}')
        if players and not dry:
            write_db(path, db, meta)


def cmd_save(save, write):
    meta = load_meta(CACHE_META)
    raw = open(save, 'rb').read()
    sf = SaveFile(raw, meta)
    pl, summary = plan(sf.db)
    players, values = apply_plan(sf.db, pl)
    print(f'{save}: вратарей изменено {players}, значений {values}')
    report(summary, pl)
    if not write or not players:
        print('без --write ничего не записано' if players else 'сейв уже совпадает')
        return
    out = sf.bytes(fix=True)
    assert len(out) == len(raw), 'размер сейва изменился'
    bdir = os.path.join(ROOT, 'game', 'work', 'legacy-data', 'backup-saves',
                        f'{os.path.basename(save)}-{time.strftime("%Y%m%d-%H%M%S")}')
    os.makedirs(bdir, exist_ok=True)
    bak = os.path.join(bdir, os.path.basename(save) + '.bak')
    open(bak, 'wb').write(raw)
    open(save, 'wb').write(out)
    bad = SaveFile(open(save, 'rb').read(), meta).verify()
    if bad:
        open(save, 'wb').write(raw)
        sys.exit(f'проверка не прошла, сейв возвращён: {bad}')
    print(f'записано; CRC и обёртка — OK; копия до правки — {bak}')


def main(argv):
    sys.stdout.reconfigure(encoding='utf-8')
    if not argv or argv[0] not in ('db', 'save'):
        print(__doc__)
        sys.exit(2)
    rest = argv[1:]
    paths = [a for a in rest if not a.startswith('--')]
    if argv[0] == 'db':
        cmd_db(paths, '--dry-run' in rest)
    else:
        cmd_save(paths[0], '--write' in rest)


if __name__ == '__main__':
    main(sys.argv[1:])
