"""Юта вместо Аризоны и Тусон вместо Springfield в наборе NHL Legacy — этап build-all utah (после collect и fixdb).

Строка 22 базы (Arizona Coyotes) становится клубом Utah Mammoth 2026/27, её фарм-клуб, строка 55 (Springfield Falcons), —
Tucson Roadrunners. Данные и арт подготовил агент utah (docs/utah.md): спецификация game/work/utah/utah_spec.json
(поле за полем: было → стало) и арт game/work/utah/out (дерево cache:, арт 104 Юты, 105 Тусона, прожектор 48).
Здесь спецификация применяется к out/db/nhlng.db и out-ahl32/db/nhlng.db, их локализации fe/loc/NHL_ENG_US.db, а арт
копируется в out/ со сверкой md5. Решения пользователя и координатора (10.10.2026):
- третья форма Юты — не ставится (концепт out-third/ и optional_third спецификации не берутся);
- арена — нейтральная модель «EA SPORTS Arena» с названием Delta Center (как в спецификации), звук команды — 32;
- наклейка на шлем — что есть в арте (логотип клуба Mountain Mammoth; Filevine в арте нет);
- фарм-клуб — Tucson Roadrunners с логотипом «Dusty» на месте строки 55; дивизион не меняется (Pacific — только
  вместе с деревом АХЛ в коде legacy-port, открыто);
- палитра Тусона в stockteamcolorstable (в спецификации её нет): бордовый, песочный, медный, чёрный — по docs/utah.md §6;
- шлем выездной формы Юты — белый (строка шлема варианта 1 после перекраски была тёмной: у Аризоны она от ретро-формы).

Проверки: каждое поле до правки должно быть «было» или уже «стало» (иначе база не та — остановка); строки формы,
экипировки и цветов выбираются по команде и сверяются с номерами строк спецификации. Повторный запуск ничего не меняет.

    python tools/legacy_data/utah.py [СПЕК] [--art ПАПКА]
"""
import hashlib
import json
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from install_legacy_data import GAME, W  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tdb import Tdb  # noqa: E402
from tdb_read import load_meta  # noqa: E402

SPEC = os.path.join(GAME, 'work', 'utah', 'utah_spec.json')
ART = os.path.join(GAME, 'work', 'utah', 'out')
OUT, OUT_AHL32 = os.path.join(W, 'out'), os.path.join(W, 'out-ahl32')
INFO = os.path.join(W, 'utah')
LOC = 'fe/loc/NHL_ENG_US.db'
LOC_META = os.path.join(GAME, 'other', 'legacy', 'big', 'cacheboot', 'fe', 'loc', 'nhl_eng_us-meta.xml')
TUCSON_COLORS = [(0x79, 0x00, 0x23), (0xED, 0xDF, 0xC0), (0xAB, 0x72, 0x4B), (0x18, 0x12, 0x10)]   # docs/utah.md §6


def md5(path):
    return hashlib.md5(open(path, 'rb').read()).hexdigest()


def get(db, c):
    if isinstance(c['old'], str) or isinstance(c['new'], str):
        return db.get_string(c['table'], c['field'], c['row'])
    return db.get(c['table'], c['field'], c['row'])


def apply_fields(db, changes, log):
    n = 0
    for c in changes:
        cur = get(db, c)
        if cur == c['new']:
            continue
        if cur != c['old']:
            sys.exit(f"{c['table']}[{c['row']}].{c['field']}: {cur!r} — ни «было» {c['old']!r}, ни «стало» {c['new']!r}")
        if isinstance(c['new'], str):
            db.set_string(c['table'], c['field'], c['row'], c['new'])
        else:
            db.set(c['table'], c['field'], c['row'], c['new'])
        n += 1
    log.append(f'{changes[0]["table"]}[{changes[0]["row"]}]: полей изменено {n} из {len(changes)}' if changes else '')
    return n


KIT_FIELDS = ('teamid', 'teamartid', 'style', 'variant', 'fevariant', 'jerseyindex', 'locstring', 'isdefault',
              'islightcolor', 'hastie', 'helmetlogo', 'helmetnumbers', 'islockable')


def replace_kits(db, spec, log):
    """Строки stockteamjerseys команды — ровно new_rows (лишние удаляются, остальные строки сдвигаются вверх: на номера
    строк этой таблицы ничто не ссылается — спецификация)."""
    T, team = 'stockteamjerseys', spec['teamid']
    rows = [r for r in db.live_rows(T) if db.get(T, 'teamid', r) == team]
    want = [{f: k[f] for f in KIT_FIELDS} for k in spec['new_rows']]
    have = [{f: db.get(T, f, r) for f in KIT_FIELDS} for r in rows]
    if have == want:
        log.append(f'{T} команды {team}: уже как надо ({len(want)} строк)')
        return 0
    # номера строк в спецификации — по базе до правки; строки другой команды выше могли уже сдвинуться (Юта: 8 → 2),
    # поэтому сверяются число, порядок и поля строк, а не номера
    if len(rows) != len(spec['old_rows']) or rows != list(range(rows[0], rows[0] + len(rows))):
        sys.exit(f'{T} команды {team}: строки {rows}, в спецификации {[o["row"] for o in spec["old_rows"]]} — база не та')
    for o, r in zip(spec['old_rows'], rows):
        if any(db.get(T, f, r) != o[f] for f in KIT_FIELDS):
            sys.exit(f'{T}[{r}]: поля не как «было» в спецификации')
    n = db.by_name[T]['rows']
    first, k = rows[0], len(rows)
    tpl = db.record(T, first)
    tail = [db.record(T, r) for r in range(first + k, n)]
    new_n = n - k + len(want)
    if new_n > n:
        db.resize(T, new_n)
    for i, kit in enumerate(want):
        db.put_record(T, first + i, tpl)
        for f, v in kit.items():
            db.set(T, f, first + i, v)
    for i, raw in enumerate(tail):
        db.put_record(T, first + len(want) + i, raw)
    if new_n < n:
        db.resize(T, new_n)
    log.append(f'{T} команды {team}: {k} строк → {len(want)} (строк в таблице {n} → {new_n})')
    return 1


def rgb_groups(db, table):
    f = db.by_name[table]['fields']
    return sorted({x[:-2] for x in f if x.endswith('_r') and x[:-2] + '_g' in f and x[:-2] + '_b' in f})


def recolor(db, table, team_field, team_raw, rows, mapping, log):
    """Цвета строк экипировки команды по карте «#RRGGBB → #RRGGBB» (все тройки _r/_g/_b строки)."""
    have = [r for r in db.live_rows(table) if db.get(table, team_field, r) == team_raw]
    if sorted(rows) != have:
        sys.exit(f'{table}: строк команды {team_raw} {len(have)}, в спецификации {len(rows)} — база не та')
    m = {int(a, 16): int(b, 16) for a, b in mapping.items()}
    groups = rgb_groups(db, table)
    n = 0
    for r in have:
        for g in groups:
            v = db.get(table, g + '_r', r) << 16 | db.get(table, g + '_g', r) << 8 | db.get(table, g + '_b', r)
            if v in m:
                for c, x in zip('rgb', (m[v] >> 16, m[v] >> 8 & 0xFF, m[v] & 0xFF)):
                    db.set(table, f'{g}_{c}', r, x)
                n += 1
    log.append(f'{table} команды {team_raw}: перекрашено зон {n} в {len(have)} строках')
    return n


def helmets(db, team_raw, want, log):
    """Цвет шлема новых форм: строка шлема — stockteamequipmenttable с team = команда + 1, era 1 (стиль 1), variant =
    вариант формы, equipment 8 (зона 1 — каска; nhl24.add_helmets). Формы Юты получили варианты 0/1, а строки era 1 v0/v1
    у Аризоны были от её ретро-форм (обе тёмные после перекраски), поэтому выезду нужна светлая каска: у Юты шлемы
    чёрные дома и белые в гостях (docs/utah.md §1). Образец светлой/тёмной — строка шлема era 1 этой же команды.
    Уточнение 10.10 (nhl24.add_helmets, docs/legacy-data.md, «Цвет шлема»): значения таблицы — со сдвигом −1, сырое
    era 1 — это ретро-формы стиля 0, поэтому правка шлем Юты не меняет. Он верный и так: дома — строка 716 Аризоны
    (era −1, variant «любой», чёрный), в гостях — 712 (era −1, variant 1, белый). Правка оставлена, чтобы база Юты не
    менялась до ТЕСТ UTA."""
    E = 'stockteamequipmenttable'
    rows = [r for r in db.live_rows(E) if db.get(E, 'team', r) == team_raw and db.get(E, 'era', r) == 1 and
            db.get(E, 'equipment', r) == 8]
    zones = [f'zone{z}_{c}' for z in range(1, 10) for c in 'rgb']

    def light(r):
        rgb = [db.get(E, f'zone1_{c}', r) for c in 'rgb']
        return (rgb[0] * 3 + rgb[1] * 6 + rgb[2]) / 10 > 160
    tpl = {k: next((r for r in rows if light(r) == (k == 'light')), None) for k in ('light', 'dark')}
    n = 0
    for variant, kind in want.items():
        r = next((r for r in rows if db.get(E, 'variant', r) == variant), None)
        if r is None or light(r) == (kind == 'light'):
            continue
        src = tpl[kind]
        if src is None:
            sys.exit(f'{E}: у команды {team_raw} нет образца {kind} каски (era 1, equipment 8)')
        for z in zones:
            db.set(E, z, r, db.get(E, z, src))
        n += 1
        log.append(f'{E}[{r}]: шлем формы варианта {variant} — {"светлый" if kind == "light" else "тёмный"} '
                   f'(как строка {src})')
    if not n:
        log.append(f'{E}: шлемы команды {team_raw} уже как надо')
    return n


def colors(db, team, rgbs, log):
    T = 'stockteamcolorstable'
    rows = sorted((db.get(T, 'colorid', r), r) for r in db.live_rows(T) if db.get(T, 'team', r) == team)
    if [c for c, _ in rows] != list(range(len(rgbs))):
        sys.exit(f'{T}: у команды {team} цвета {[c for c, _ in rows]}, ждал 0…{len(rgbs) - 1}')
    n = 0
    for (cid, r), rgb in zip(rows, rgbs):
        for c, v in zip('rgb', rgb):
            if db.get(T, f'color_{c}', r) != v:
                db.set(T, f'color_{c}', r, v)
                n += 1
    log.append(f'{T} команды {team}: изменено каналов {n}')
    return n


def apply_db(path, spec, log):
    db = Tdb(open(path, 'rb').read(), load_meta(os.path.join(os.path.dirname(path), 'nhlng-meta.xml')))
    d = spec['db']
    apply_fields(db, d['exhibitionteams'], log)
    apply_fields(db, d['exhibitionarena']['changes'], log)
    colors(db, 22, [tuple(c['new']) for c in sorted(d['stockteamcolorstable'], key=lambda c: c['colorid'])], log)
    replace_kits(db, d['stockteamjerseys'], log)
    e = d['equipment']
    recolor(db, e['table'], 'team', e['team_raw'], e['rows'], e['recolor'], log)
    recolor(db, e['goalie_table'], 'team', e['team_raw'], e['goalie_rows'], e['recolor'], log)
    helmets(db, e['team_raw'], {0: 'dark', 1: 'light'}, log)      # дом — чёрный, выезд — белый
    a = spec['ahl']
    apply_fields(db, a['exhibitionteams'], log)
    apply_fields(db, a['exhibitionarena']['changes'], log)
    colors(db, a['row'], TUCSON_COLORS, log)
    replace_kits(db, a['stockteamjerseys'], log)
    e = a['equipment']
    recolor(db, e['table'], 'team', e['team_raw'], e['rows'], e['recolor'], log)
    recolor(db, e['goalie_table'], 'team', e['team_raw'], e['goalie_rows'], e['recolor'], log)
    db.fix()
    if db.verify():
        sys.exit(f'{path}: CRC не сошлись')
    return bytes(db.d)


def apply_loc(path, spec, log):
    import locdb
    loc = locdb.LocDb(open(path, 'rb').read(), load_meta(LOC_META))
    n = 0
    for e in spec['localization']['set_or_add'] + spec['ahl']['localization']:
        f = loc.find_all(e['key'])
        cur = loc.text(loc.text_off_at(f[0])) if f else None
        if cur == e['new']:
            continue
        if cur != e['old']:
            sys.exit(f"{path}: {e['key']} = {cur!r}, в спецификации «было» {e['old']!r}")
        loc.put(e['key'], e['new'])
        n += 1
    bad = loc.check()
    if bad:
        sys.exit(f'{path}: ' + '; '.join(bad[:3]))
    loc.db.fix()
    log.append(f'{LOC}: строк изменено/добавлено {n}')
    return bytes(loc.db.d)


def write(path, data):
    if os.path.exists(path) and open(path, 'rb').read() == data:
        return False
    with open(path + '.part', 'wb') as f:
        f.write(data)
    os.replace(path + '.part', path)
    return True


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
    args = sys.argv[1:]
    art = ART
    if '--art' in args:
        i = args.index('--art')
        art = os.path.abspath(args[i + 1])
        del args[i:i + 2]
    spec_path = os.path.abspath(args[0]) if args else SPEC
    spec = json.load(open(spec_path, encoding='utf-8'))
    if spec.get('spec') != 'utah' or spec.get('version') != 1:
        sys.exit(f'{spec_path}: не спецификация utah версии 1')
    # арт: только cache_files.add (out-third/ и optional_third — нет), со сверкой md5
    files = spec['cache_files']['add']
    for e in files:
        p = os.path.join(art, *e['path'].split('/'))
        if not os.path.isfile(p) or os.path.getsize(p) != e['bytes'] or md5(p) != e['md5']:
            sys.exit(f"{e['path']}: в {art} нет или не тот (md5/размер не как в спецификации)")
    report = {'spec': spec_path, 'spec_md5': md5(spec_path), 'art': art, 'files': len(files), 'bases': {}}
    for base in (OUT, OUT_AHL32):
        dbp = os.path.join(base, 'db', 'nhlng.db')
        if not os.path.isfile(dbp):
            continue
        log = []
        before = md5(dbp)
        data = apply_db(dbp, spec, log)
        changed = write(dbp, data)
        locp = os.path.join(base, *LOC.split('/'))
        loc_changed = write(locp, apply_loc(locp, spec, log)) if os.path.isfile(locp) else False
        report['bases'][os.path.basename(base)] = {'db_before': before, 'db': md5(dbp), 'db_changed': changed,
                                                   'loc': md5(locp) if os.path.isfile(locp) else None,
                                                   'loc_changed': loc_changed, 'log': [x for x in log if x]}
        print(f'{os.path.basename(base)}: база {before[:8]} → {md5(dbp)[:8]}' + ('' if changed else ' (без изменений)')
              + f'; локализация{" обновлена" if loc_changed else " без изменений"}')
        for line in log:
            if line:
                print('   ', line)
    copied = 0
    for e in files:
        src = os.path.join(art, *e['path'].split('/'))
        dst = os.path.join(OUT, *e['path'].split('/'))
        if os.path.exists(dst) and md5(dst) == e['md5']:
            continue
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copyfile(src, dst)
        copied += 1
    report['art_copied'] = copied
    os.makedirs(INFO, exist_ok=True)
    with open(os.path.join(INFO, 'report.json'), 'w', encoding='utf-8', newline='\n') as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    print(f'арт: {len(files)} файлов в out/ (скопировано {copied}); отчёт — {os.path.join(INFO, "report.json")}')


if __name__ == '__main__':
    main()
