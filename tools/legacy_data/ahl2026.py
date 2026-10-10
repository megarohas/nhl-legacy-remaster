"""Этап build-all ahl: составы АХЛ 2026/27 и свободные агенты на сегодня — в out и out-ahl32 (решение пользователя
10.10, «актуализируй составы АХЛ и свободных агентов»; составы НХЛ остаются на 08.10).

1. Игроки и база — tools/roster/ahl2026.py (build: players.json и match.json по кэшу HockeyTech и API НХЛ;
   write: составы 32 клубов АХЛ, пул свободных агентов, без клуба — игроки АХЛ 2015 года, которых нет в 2026/27).
2. Клубы — по game/work/legacy-data/ahl-2026/slots.json (tools/legacy_data/ahl2026_slots.py): у 8 переименованных
   слотов — полное и короткое название, аббревиатура и строки локализации по их artabbr; у всех 32 — название и
   город арены по расписанию HockeyTech 2026/27 (кроме Tucson — «Tucson Arena», как в спецификации utah); у клубов
   НХЛ — аффилиат АХЛ 2026/27. Арт (artid, artabbr, логотипы, арены) не меняется.
3. draft_roster.db — заново (10 таблиц).

    python tools/legacy_data/ahl2026.py [--only build|photos|write|equip|slots|draft]
Рабочие файлы — game/work/legacy-data/ahl-2026/<out|out-ahl32>/ (players.json, match.json, write.json, report.md).
Полный прогон идёт на копии базы (<рабочая папка>/db): база и локализация в out заменяются только в конце, целиком,
портреты дописываются в <out>/fe. К базе, где этап уже применён (новые названия переименованных слотов), он не
применяется — заново только от сборки базы (build-all.sh collect … ahl) или от баз из бэкапа. --only — один шаг на
месте, для отладки.
"""
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
REPO = os.path.dirname(TOOLS)
sys.path.insert(0, TOOLS)
from tdb import Tdb  # noqa: E402
from tdb_read import load_meta  # noqa: E402

W = os.environ.get('LEGACY_DATA_WORK') or os.path.join(REPO, 'game', 'work', 'legacy-data')
SLOTS = os.path.join(REPO, 'game', 'work', 'legacy-data', 'ahl-2026', 'slots.json')
WORK = os.path.join(REPO, 'game', 'work', 'legacy-data', 'ahl-2026')
LOC = 'fe/loc/NHL_ENG_US.db'
LOC_META = os.path.join(REPO, 'game', 'other', 'legacy', 'big', 'cacheboot', 'fe', 'loc', 'nhl_eng_us-meta.xml')
T, A = 'exhibitionteams', 'exhibitionarena'
KEEP_ARENA = {55: ('Tucson Arena', 'Tucson, AZ')}      # координатор 10.10: как в спецификации utah
# Строка арены, общая с клубом НХЛ (так в базе 2015 года у Manitoba — WPG и San Jose Barracuda — SJ). Если и в
# 2026/27 здание одно (Canada Life Centre у Moose и Jets), строка остаётся общей и новое название — у обоих. Иначе
# (Barracuda с 2022 года — в Tech CU Arena, Sharks — в SAP Center) клуб АХЛ получает свою строку: копию общей (модель,
# звук, центр льда — те же, другие только название и город), строка клуба НХЛ не меняется.
SHARED_BUILDING = {44}
from roster.ahl2026 import ABBR  # noqa: E402  (коды клубов, совпавшие с чужими в базе)
LOC_KEYS = {   # ключ (без _<artabbr>) → что писать
    'NHLTeamName': 'name', 'NHLTEAMNAME': 'name', 'NHLCityName': 'city', 'NHLCITYNAME': 'city', 'Teamline1': 'city',
    'TEAMLINE1': 'city', 'Teamline2': 'nick', 'TEAMLINE2': 'nick', 'NICKLINE2': 'nick', 'TXT_NICKNAME': 'nick',
    'TXT_NICKNAME_ALT': 'nick', 'NHLTeamName_ABBR3': 'abbr', 'X_XLA_TEAM': 'abbr'}


def clean(text):
    return (text or '').replace('’', "'").replace('‘', "'").strip()


def fit(text, limit):
    from roster.common import fit_utf8
    return fit_utf8(text, limit)


def apply_slots(db, slots, log):
    """Названия 8 переименованных слотов, арены 32 слотов, аффилиаты клубов НХЛ. → число изменённых значений."""
    from collections import defaultdict
    from roster.common import TEAM_SLOT
    TEAM_ABBR = {s: a for a, s in TEAM_SLOT.items()}         # клубы НХЛ: строка → код
    low = {f: lo for f, lo, _ in next(fl for n, fl in db.meta.values() if n == T).values()}
    width = lambda t, f: db.by_name[t]['fields'][f][1] // 8 - 1
    n = 0

    def put(table, field, row, text):
        nonlocal n
        text = clean(text)
        if len(text.encode('utf-8')) > width(table, field):
            log.append(f'  {table}[{row}].{field}: «{text}» длиннее поля ({width(table, field)}) — обрезано')
        text = fit(text, width(table, field))
        if db.get_string(table, field, row) != text:
            db.set_string(table, field, row, text)
            n += 1
    leagues = {t: db.get(T, 'league', t) for t in range(db.by_name[T]['rows'])}
    present = [s for s in slots if leagues.get(s['slot']) == 1]
    users = defaultdict(list)                                # строка арены → команды
    for t in leagues:
        users[db.get(T, 'arenaid', t)].append(t)
    for s in present:
        if s['renamed']:
            put(T, 'fullname', s['slot'], s['name'])
            put(T, 'shortname', s['slot'], s['city'])
            put(T, 'abbrname', s['slot'], ABBR.get(s['code'], s['code']))
        arena = db.get(T, 'arenaid', s['slot'])
        name, city = KEEP_ARENA.get(s['slot'], (s['arenaname'], s['cityname']))
        nhl = [TEAM_ABBR.get(t, t) for t in users[arena] if t in TEAM_ABBR]
        if nhl and s['slot'] not in SHARED_BUILDING and fit(clean(name), width(A, 'arenaname')) != \
                db.get_string(A, 'arenaname', arena):
            row = db.by_name[A]['rows']                      # своя строка — копия общей, в конец таблицы
            raw = db.record(A, arena)
            db.resize(A, row + 1)
            db.put_record(A, row, raw)
            db.set(A, 'index', row, row)
            db.set(T, 'arenaid', s['slot'], row)
            n += 1
            log.append(f"  арена {s['name']}: своя строка {row} (копия {arena} «{db.get_string(A, 'arenaname', arena)}», "
                       f"общей с {', '.join(nhl)}; у клуба НХЛ — как была)")
            arena = row
        put(A, 'arenaname', arena, name)
        put(A, 'cityname', arena, city)
    for s in present:
        t = TEAM_SLOT[s['affiliate_of']]
        raw = s['slot'] - low['ahlaffiliate']                # rangelow −1: в базе — слот + 1
        if db.get(T, 'ahlaffiliate', t) != raw:
            db.set(T, 'ahlaffiliate', t, raw)
            n += 1
            log.append(f"  аффилиат {s['affiliate_of']} → {s['name']} (слот {s['slot']})")
    return n


def apply_loc(path, slots, log):
    import locdb
    loc = locdb.LocDb(open(path, 'rb').read(), load_meta(LOC_META))
    n = 0
    for s in slots:
        if not s['renamed']:
            continue
        val = {'name': s['name'], 'city': s['city'], 'nick': s['nickname'], 'abbr': ABBR.get(s['code'], s['code'])}
        done = set()
        for k, what in LOC_KEYS.items():
            key = f"{k}_{s['artabbr']}"
            f = loc.find_all(key)
            if not f or key.lower() in done:
                continue
            done.add(key.lower())
            cur = loc.text(loc.text_off_at(f[0]))
            if cur != clean(val[what]):
                loc.put(key, clean(val[what]))
                n += 1
    bad = loc.check()
    if bad:
        sys.exit(f'{path}: ' + '; '.join(bad[:3]))
    loc.db.fix()
    log.append(f'  {LOC}: строк изменено {n}')
    return bytes(loc.db.d), n


def write(path, data):
    if os.path.exists(path) and open(path, 'rb').read() == data:
        return False
    with open(path + '.part', 'wb') as f:
        f.write(data)
    os.replace(path + '.part', path)
    return True


def run(cmd, env=None):
    r = subprocess.run(cmd, cwd=TOOLS, capture_output=True, text=True, encoding='utf-8', errors='replace',
                       env=env or dict(os.environ, PYTHONIOENCODING='utf-8'))
    out = (r.stdout + r.stderr).strip()
    print('\n'.join('   ' + x for x in out.splitlines()[-8:]))
    if r.returncode:
        sys.exit(f'{" ".join(cmd[:4])}: код {r.returncode}')


def photos_prep(work):
    """Кадры НХЛ до записи (по ним — тон кожи головы, --skin): leaguestat → кадр НХЛ (roster/ht_photos.py) и
    «последние» портреты НХЛ (photos_other, только кэш)."""
    run([sys.executable, '-m', 'roster.ht_photos', os.path.join(work, 'players.json')])
    code = ("from roster import common; common.set_game('legacy'); from roster import photos_other as po; "
            f"po.run(common.Paths(None, {work!r}), offline=True)")
    run([sys.executable, '-c', code])


def photos_build(name, d, dbp, work, log):
    """Портреты в игру: tools/photos.py build в свою папку (photos-all основной сборки не трогается) → <out>/fe,
    hasportrait по write.json."""
    pw = os.path.join(WORK, 'photo-work', name)
    env = dict(os.environ, LEGACY_DATA_WORK=pw, PYTHONIOENCODING='utf-8', NHL_GAME='legacy')
    run([sys.executable, os.path.join(TOOLS, 'photos.py'), 'build', '--game', 'legacy', '--jobs', '6', '--work', work],
        env=env)
    run([sys.executable, os.path.join(TOOLS, 'photos.py'), 'db', dbp, dbp, '--game', 'legacy', '--work', work], env=env)
    src = os.path.join(pw, 'photos-all', 'fe')
    n = 0
    for root, _, files in os.walk(src):
        for f in files:
            a = os.path.join(root, f)
            b = os.path.join(d, 'fe', os.path.relpath(a, src))
            os.makedirs(os.path.dirname(b), exist_ok=True)
            n += write(b, open(a, 'rb').read())
    log.append(f'  портреты: в {name}/fe новых или изменённых файлов {n}')


def applied(dbp, slots):
    """Этап к базе уже применён: у переименованных слотов в ней новые названия (их этап пишет вместе с составами)."""
    db = Tdb(open(dbp, 'rb').read(), load_meta(os.path.join(os.path.dirname(dbp), 'nhlng-meta.xml')))
    width = db.by_name[T]['fields']['fullname'][1] // 8 - 1
    return [s['slot'] for s in slots if s['renamed'] and db.get(T, 'league', s['slot']) == 1
            and db.get_string(T, 'fullname', s['slot']) == fit(clean(s['name']), width)]


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    only = sys.argv[sys.argv.index('--only') + 1] if '--only' in sys.argv else None
    slots = json.load(open(SLOTS, encoding='utf-8'))['slots']
    # сначала out-ahl32 (в ней больше игроков: CV/HSK), потом out — artid новых у обеих общие
    for name, ahl32 in (('out-ahl32', True), ('out', False)):
        d = os.path.join(W, name)
        final = os.path.join(d, 'db', 'nhlng.db')
        if not os.path.isfile(final):
            continue
        work = os.path.join(WORK, name)
        print(f'== {name}')
        if only is None:
            # весь этап — на копии базы в рабочей папке; в out база и локализация попадают только в конце, целиком
            # (обрыв посреди этапа out не трогает), а к базе после этапа он второй раз не применяется
            done = applied(final, slots)
            if done:
                sys.exit(f'{final}: этап ahl к этой базе уже применён (слоты {done} — с новыми названиями); '
                         'заново — от сборки базы (build-all.sh collect … ahl) или от баз из бэкапа')
            stage = os.path.join(work, 'db')
            os.makedirs(stage, exist_ok=True)
            for f in ('nhlng.db', 'nhlng-meta.xml'):
                shutil.copyfile(os.path.join(d, 'db', f), os.path.join(stage, f))
            dbp = os.path.join(stage, 'nhlng.db')
        else:
            dbp = final                                     # --only: отдельный шаг на месте (отладка)
        flags = ['--ahl32'] if ahl32 else []
        log = []
        loc_data = None
        if only in (None, 'build'):
            run([sys.executable, '-m', 'roster.ahl2026', 'build', '--db', dbp, '--work', work] + flags)
        if only in (None, 'photos'):
            photos_prep(work)
        if only in (None, 'write'):
            run([sys.executable, '-m', 'roster.ahl2026', 'write', '--db', dbp, '--work', work, '--out', dbp] + flags)
        if only in (None, 'photos'):
            photos_build(name, d, dbp, work, log)
        if only in (None, 'equip'):
            run([sys.executable, '-m', 'roster.equipment', '--game', 'legacy', '--work', work, 'apply', dbp, dbp,
                 '--visor-rule', '--jersey-rule', '--report', os.path.join(work, 'equipment-apply.json')])
        lp = os.path.join(d, *LOC.split('/'))
        if only in (None, 'slots'):
            db = Tdb(open(dbp, 'rb').read(), load_meta(os.path.join(os.path.dirname(dbp), 'nhlng-meta.xml')))
            n = apply_slots(db, slots, log)
            db.fix()
            if db.verify():
                sys.exit(f'{dbp}: CRC не сошлись')
            write(dbp, bytes(db.d))
            loc_data, m = apply_loc(lp, slots, log)
            if only:
                write(lp, loc_data)
            print(f'   клубы: значений изменено {n}, строк локализации {m}')
        if only is None:                                    # конец этапа: база и локализация — в out
            write(final, open(dbp, 'rb').read())
            write(lp, loc_data)
        if only is None or only == 'draft':
            run([sys.executable, os.path.join(HERE, 'draft_roster.py'), final, os.path.join(d, 'db', 'draft_roster.db')])
        for x in log:
            print('  ' + x)


if __name__ == '__main__':
    main()
