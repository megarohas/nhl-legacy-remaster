"""Командная экипировка вратарей (tools/legacy_data/goalie_gear.json): каждому вратарю клуба — набор вратаря этого
клуба, заготовленный EA (stockgoalieequipment), у клуба без набора — белая экипировка с чёрной графикой и белая
маска. Этап build-all «goaliegear» (после tape).

    python tools/legacy_data/goalie_gear.py db БАЗА.db [БАЗА.db …] [--dry-run]   # nhlng.db, draft_roster.db
    python tools/legacy_data/goalie_gear.py save СЕЙВ [--write]                   # сохранённый состав (ROSTER …)
    … [--clubs "Utah Mammoth,Seattle Kraken"]   # только вратари этих клубов (остальные — как есть в базе/сейве)

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
- nhl27_colors (03.11.2026): у клубов списка (UTA, SEA, VGK) белый набор красится цветами зон вратаря из NHL 27 (палитра:
  самый частый цвет → base, следующие → accent1/accent2 по roles; модели — белого набора), маска — его маска NHL 27,
  перенесённая fb.masks в свободный номер (tools/fb/mask_slots.toml), если она там есть;
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


NHL27_DB = os.path.join(ROOT, 'game', 'work', 'nhl27', 'db', 'nhl_game.db')
_P27 = None


def palettes27(path=NHL27_DB):
    """Вратари NHL 27: {(имя, фамилия) в нижнем регистре: {'team': название клуба, 'pads'|'blocker'|'trapper': [rgb ×15],
    'stick': [rgb ×6]}} из exhibitiongoalieequipment (цвет зоны — 0xRRGGBB). Нет базы — {}."""
    global _P27
    if _P27 is not None:
        return _P27
    _P27 = {}
    if not os.path.isfile(path):
        return _P27
    db = Tdb(open(path, 'rb').read(), load_meta(os.path.join(os.path.dirname(path), 'nhl_game-meta.xml')))
    eq = {db.get(EQ, 'game_id', r): r for r in db.live_rows(EQ)}
    rgb = lambda v: [(v >> 16) & 255, (v >> 8) & 255, v & 255]
    for r in db.live_rows(B):
        e = eq.get(db.get(B, 'game_id', r))
        if e is None or db.get(B, 'position', r) != 4:
            continue
        t = db.get(B, 'team', r) - 1
        v = {'team': db.get_string(T, 'teamname', t) if 0 <= t < db.by_name[T]['rows'] else ''}
        for part in ('pads', 'blocker', 'trapper'):
            v[part] = [rgb(db.get(EQ, f'{part}zone{z}color', e)) for z in range(1, 16)]
        v['stick'] = [rgb(db.get(EQ, f'stickzone{z}color', e)) for z in range(1, 7)]
        v['mask'] = db.get(EQ, 'maskid', e) if db.get(EQ, 'masktype', e) == 0 else None
        _P27[fold(db.get_string(B, 'firstname', r), db.get_string(B, 'lastname', r))] = v
    _T27.clear()
    for t in db.live_rows(T):                  # маски основного и запасного вратаря клуба (тип 0)
        _T27[db.get_string(T, 'teamname', t)] = (db.get(T, 'goaliemask0_starter', t), db.get(T, 'goaliemask0_backup', t))
    return _P27


_T27 = {}


def fold(first, last):
    """(имя, фамилия) без диакритики, в нижнем регистре: Málek = Malek, Östman = Ostman."""
    import unicodedata
    f = lambda x: unicodedata.normalize('NFKD', x).encode('ascii', 'ignore').decode().lower().strip()
    return f(first), f(last)


def palette(colors):
    """Цвета зон → [base, accent1, accent2]: по частоте (при равенстве — кто раньше); не хватает — чёрный или белый."""
    order = []
    for c in colors:
        if c not in order:
            order.append(c)
    order.sort(key=lambda c: -colors.count(c))
    while len(order) < 3:
        order.append([32, 32, 32] if sum(order[0]) > 3 * 128 else [231, 231, 231])
    return order[:3]


def nhl27_values(sp, vals, first, last, club, order=0):
    """Белый набор vals + цвета зон и маска вратаря из NHL 27 (nhl27_colors в goalie_gear.json). Источник — сам вратарь в
    NHL 27, если он там в этом же клубе; иначе (другой клуб, нет в NHL 27, имя пишется иначе) — вратарь клуба NHL 27 с маской
    основного (order 0) или запасного (order ≥ 1) вратаря клуба (exhibitionteams.goaliemask0_starter/backup), нет такого —
    первый вратарь клуба по имени. -> (vals, откуда) или (vals, None)."""
    p27 = palettes27()
    src = p27.get(fold(first, last))
    how = 'свои'
    if src is None or src['team'] != club:
        same = sorted(k for k, v in p27.items() if v['team'] == club)
        if not same:
            return vals, None
        want = _T27.get(club, (None, None))[0 if order == 0 else 1]
        pick = [k for k in same if p27[k]['mask'] == want] or same
        src, how = p27[pick[0]], f'клуба ({" ".join(pick[0]).title()})'
    cfg = sp['nhl27_colors']
    vals = dict(vals)
    for part in ('pads', 'blocker', 'trapper'):
        pal = dict(zip(('base', 'accent1', 'accent2'), palette(src[part])))
        for role, zones in cfg['roles'].items():
            for z in zones:
                for c, x in zip('rgb', pal[role]):
                    vals[f'{part}zone{z}color_{c}'] = x
    pal = dict(zip(('base', 'accent1', 'accent2'), palette(src['stick'])))
    for role, zones in cfg['stick_roles'].items():
        for z in zones:
            for c, x in zip('rgb', pal[role]):
                vals[f'stickzone{z}color_{c}'] = x
    mk = masks27().get(src.get('mask'))         # маска NHL 27, перенесённая в свободный номер Legacy (fb.masks)
    if mk is not None:
        vals['masktype'], vals['maskid'] = mk
        how += f', маска {mk[0]}/{mk[1]} ← NHL 27 itech {src["mask"]}'
    return vals, how


def masks27():
    """Номер маски itech NHL 27 → (masktype, maskid) Legacy из tools/fb/mask_slots.toml (маски, перенесённые fb.masks)."""
    import tomllib
    p = os.path.join(ROOT, 'tools', 'fb', 'mask_slots.toml')
    if not os.path.isfile(p):
        return {}
    with open(p, 'rb') as f:
        plan = tomllib.load(f).get('mask', {})
    return {int(v['nhl27']): (int(v.get('masktype', 0)), int(k)) for k, v in plan.items()}


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
        nhl27_clubs = set(sp.get('nhl27_colors', {}).get('clubs', ()))
        if rows and name not in white_names and name not in nhl27_clubs:
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
            why = 'нет набора' if not rows else 'спорный набор — white_names' if name in white_names else                 'набор EA заменён NHL 27 (nhl27_colors)'
            for k, (_, g) in enumerate(gs):
                vals, src = white_values(db, sp, None), None
                if name in nhl27_clubs:        # 03.11.2026: расцветка и маска вратаря из NHL 27
                    vals, src = nhl27_values(sp, vals, db.get_string(B, 'firstname', bio[g]),
                                             db.get_string(B, 'lastname', bio[g]), name, k)
                out[g] = (vals, f'{name}: белый ({why})' + (f', цвета зон NHL 27 — {src}' if src else ''))
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


def only_clubs(pl, clubs):
    """План только для вратарей клубов clubs (названия через запятую; None — все)."""
    if not clubs:
        return pl
    names = [c.strip() for c in clubs.split(',') if c.strip()]
    return {g: v for g, v in pl.items() if any(v[1].startswith(n + ':') for n in names)}


def cmd_db(paths, dry, clubs=None):
    for path in paths:
        meta = meta_for(path)
        db = Tdb(open(path, 'rb').read(), meta)
        src = db
        if SG not in db.by_name or T not in db.by_name:     # draft_roster.db — план у nhlng.db рядом
            nh = os.path.join(os.path.dirname(path), 'nhlng.db')
            src = Tdb(open(nh, 'rb').read(), meta)
        pl, summary = plan(src)
        pl = only_clubs(pl, clubs)
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


def cmd_save(save, write, clubs=None):
    meta = load_meta(CACHE_META)
    raw = open(save, 'rb').read()
    sf = SaveFile(raw, meta)
    pl, summary = plan(sf.db)
    pl = only_clubs(pl, clubs)
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
    clubs = rest[rest.index('--clubs') + 1] if '--clubs' in rest else None
    paths = [a for a in rest if not a.startswith('--') and a != clubs]
    if argv[0] == 'db':
        cmd_db(paths, '--dry-run' in rest, clubs)
    else:
        cmd_save(paths[0], '--write' in rest, clubs)


if __name__ == '__main__':
    main(sys.argv[1:])
