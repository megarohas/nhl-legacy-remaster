"""Пакет NHL 24 → NHL Legacy (формы и шрифты номеров, центры и реклама льда, наклейки на шлемах, шорты и гетры,
клюшки, шайба): накладка game/work/legacy-data/out-nhl24 поверх out. Ставится
`install-legacy-data.sh [--ahl32] --nhl24`, снимается `uninstall-legacy-data.sh --nhl24` (docs/legacy-data.md, «NHL 24»).

    python tools/legacy_data/nhl24.py alloc КЛУБ ФОРМА… [--write]   # номера новых форм клуба → nhl24_kits.json
    python tools/legacy_data/nhl24.py build [ПАКЕТ]                  # этап build-all nhl24 → out-nhl24 (+ out-nhl24-ahl32)
    python tools/legacy_data/nhl24.py verify CACHE                   # cache: после установки — как в манифесте и out-nhl24
    python tools/legacy_data/nhl24.py show                           # что в реестре новых форм

Пакет готовит агент nhl24 (tools/fb/pack.py): ПАКЕТ/manifest.json и ПАКЕТ/cache/<путь в cache:>, по умолчанию
game/work/nhl24/out/pack (или переменная NHL24_PACK). Формат манифеста — docs/legacy-data.md, «Пакет NHL 24».

Новые формы (вариант «А», решение 09.10.2026): стиль 1, арт клуба (номер EA 0…29, SEA 100, VGK 101), новый вариант.
Номера выдаёт `alloc` и закрепляет в nhl24_kits.json (рядом, в git); список только дописывается, чтобы формы не
меняли номер между сборками. Вариант — наименьший, у которого у этого арта стиля 1 нет ни строки stockteamjerseys,
ни файла комплекта в архивах Legacy и в out (texlib/name/pant/sock/превью/наклейка на шлем); fevariant = variant;
jerseyindex — следующий за последним у клуба; locstring 2 у третьей (three), 6 у остальных (RR, ретро 90-х).

Этап build (после collect): сверяет каждый файл пакета с манифестом (путь по типу, md5, размер), копирует их в
out-nhl24 и собирает базу накладки из out/db/nhlng.db (и out-ahl32/db/nhlng.db → out-nhl24-ahl32): hastie = 0 у строк
клубов пакета («clubs» манифеста, "all" — у всех), новые строки stockteamjerseys в конец таблицы (номера прежних
строк не сдвигаются) — только для форм, все файлы которых есть в пакете. Та же база — db/draft_roster.db. Подписи
новых форм с locstring 6 (RR, ретро) — ключи Vintage_1_<арт>_<вариант> в fe/loc/NHL_ENG_US.db накладки. Отчёт и копия
манифеста — game/work/legacy-data/nhl24/ (не в out-nhl24: всё, что лежит в накладке, ставится в cache:).
"""
import hashlib
import json
import os
import re
import shutil
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from install_legacy_data import GAME, W  # noqa: E402

TOOLS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, TOOLS)
from tdb import Tdb  # noqa: E402
from tdb_read import load_meta  # noqa: E402

REGISTRY = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'nhl24_kits.json')
PACK = os.environ.get('NHL24_PACK') or os.path.join(GAME, 'work', 'nhl24', 'out', 'pack')
REF = os.path.join(GAME, 'other', 'legacy', 'big')
OUT, OUT_AHL32 = os.path.join(W, 'out'), os.path.join(W, 'out-ahl32')
DST, DST_AHL32 = os.path.join(W, 'out-nhl24'), os.path.join(W, 'out-nhl24-ahl32')
INFO = os.path.join(W, 'nhl24')                  # отчёт этапа и манифест, по которому собрана накладка
STALE = os.path.join(W, '_stale')
T = 'stockteamjerseys'
LOC = 'fe/loc/NHL_ENG_US.db'                   # подписи форм в меню (out и out-ahl32 — у каждого своя)
LOC_META = os.path.join(REF, 'cacheboot', 'fe', 'loc', 'nhl_eng_us-meta.xml')

# код клуба (как у tools/fb) → строка exhibitionteams (teamid) и номер арта
CODES = ['ANA', 'WPG', 'BOS', 'BUF', 'CGY', 'CAR', 'CHI', 'COL', 'CBJ', 'DAL', 'DET', 'EDM', 'FLA', 'LAK', 'MIN',
         'MTL', 'NSH', 'NJD', 'NYI', 'NYR', 'OTT', 'PHI', 'ARI', 'PIT', 'STL', 'SJS', 'TBL', 'TOR', 'VAN', 'WSH']
CLUBS = {c: (i, i) for i, c in enumerate(CODES)}
CLUBS.update(SEA=(30, 100), VGK=(31, 101))

# файлы комплекта стиля 1 (s = 1): обязательные у новой формы и наклейка на шлем (по ней helmetlogo = 1)
KIT_FILES = {'jersey': 'rendering/jersey/texlib_1_{a}_{v}.rx2', 'name': 'rendering/jersey/name_1_{a}_{v}_cm.rx2',
             'pant': 'rendering/pant/texlib_1_{a}_{v}.rx2', 'sock': 'rendering/sock/sock_1_{a}_{v}_cm.rx2',
             'fe': 'fe/ion/artassets/jerseys/jersey_1_{a}_{f}.big'}
HELMET = 'rendering/logo/texlib_{a}_1_{v}.rx2'
ARCHIVE = {'rendering/jersey/': 'nocacherender', 'rendering/': 'cacherender', 'fe/': 'cache'}

# типы файлов пакета: путь в cache: (полное совпадение)
TYPES = {
    'jersey': r'rendering/jersey/texlib_1_\d+_\d+\.rx2',          # свитер и шрифт номеров
    'name': r'rendering/jersey/name_1_\d+_\d+_cm\.rx2',            # карта номера и фамилии
    'pant': r'rendering/pant/texlib_1_\d+_\d+\.rx2',              # шорты
    'sock': r'rendering/sock/sock_1_\d+_\d+_cm\.rx2',              # гетры
    'fe': r'fe/ion/artassets/jerseys/jersey_1_\d+_\d+\.big',       # превью формы в меню
    'helmet': r'rendering/logo/texlib_\d+_1_\d+\.rx2',            # наклейка на шлем (логотип или спонсор)
    'center': r'rendering/icesurface/centerlogo_\d+_cm\.rx2',      # центр льда
    'ice': r'rendering/icesurface/[a-z0-9_]+\.rx2',               # логотипы и реклама на льду
    'puck': r'rendering/puck/[a-z0-9_]+\.rx2',                    # шайба
    'stick': r'rendering/playerstick/[a-z0-9_]+\.rx2',            # клюшки
    'other': r'(rendering|fe)/[a-z0-9_/]+\.(rx2|big)',            # прочее (с полем note)
}


# подпись формы в меню (Select Jerseys): у строки с locstring 6 игра берёт текст ключа Vintage_<style>_<art>_<variant>
# (так у 50 винтажных форм EA: Vintage_0_9_3 «1968-69 Away», Vintage_1_2_3 «2009-10 Classic»); нет ключа — подписи
# нет (тест DAL25). У третьей (locstring 2) — своя «Alternate». «label» в манифесте главнее этих:
LABELS = {'rr22': 'Reverse Retro 2022', 'rr23': 'Reverse Retro 2023', 'n90_home': '1990s Home',
          'n90_away': '1990s Away', 'n90_three': '1990s Alternate'}


def label_of(kit, man_label=None):
    if man_label:
        return man_label
    if kit in LABELS:
        return LABELS[kit]
    return '1990s Retro' if kit.startswith('n90_') else None


def md5(path):
    h = hashlib.md5()
    with open(path, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


def load_registry():
    if not os.path.exists(REGISTRY):
        return {'about': 'Новые формы NHL 24 в NHL Legacy (строки stockteamjerseys): номера закреплены, список только '
                         'дописывается (tools/legacy_data/nhl24.py alloc).', 'kits': []}
    return json.load(open(REGISTRY, encoding='utf-8'))


def open_db(base):
    db_path = os.path.join(base, 'db', 'nhlng.db')
    return db_path, Tdb(open(db_path, 'rb').read(), load_meta(os.path.join(base, 'db', 'nhlng-meta.xml')))


def rows_of(db):
    fields = list(db.by_name[T]['fields'])
    return [dict({f: db.get(T, f, r) for f in fields}, row=r) for r in db.live_rows(T)]


def check_club(db, code):
    if code not in CLUBS:
        sys.exit(f'клуб {code}: не знаю (коды: {" ".join(CLUBS)})')
    team, art = CLUBS[code]
    have = db.get('exhibitionteams', 'artid', team)
    if have != art:
        sys.exit(f'{code}: у строки {team} exhibitionteams.artid = {have}, а не {art} — база не та')
    return team, art


def file_taken(rel):
    """Файл комплекта уже есть: в архивах Legacy (распакованное дерево) или в out (наши SEA/VGK)."""
    arc = next(a for p, a in ARCHIVE.items() if rel.startswith(p))
    return os.path.exists(os.path.join(REF, arc, *rel.split('/'))) or os.path.exists(os.path.join(OUT, *rel.split('/')))


def variant_free(art, v, rows, reg):
    if any(r['style'] == 1 and r['teamartid'] == art and v in (r['variant'], r['fevariant']) for r in rows):
        return False
    if any(k['art'] == art and v in (k['variant'], k['fevariant']) for k in reg['kits']):
        return False
    names = [p.format(a=art, v=v, f=v) for p in KIT_FILES.values()] + [HELMET.format(a=art, v=v)]
    return not any(file_taken(n) for n in names)


def cmd_alloc(args):
    write = '--write' in args
    args = [a for a in args if a != '--write']
    if len(args) < 2:
        sys.exit(__doc__)
    code, kits = args[0].upper(), args[1:]
    _, db = open_db(OUT)
    team, art = check_club(db, code)
    rows = rows_of(db)
    reg = load_registry()
    mine = [r for r in rows if r['teamid'] == team]
    ji = max([r['jerseyindex'] for r in mine] + [k['jerseyindex'] for k in reg['kits'] if k['club'] == code]) + 1
    added = []
    for kit in kits:
        if any(k['club'] == code and k['kit'] == kit for k in reg['kits']):
            print(f'{code} {kit}: уже в реестре')
            continue
        v = next((v for v in range(32) if variant_free(art, v, rows, reg)), None)
        if v is None or ji > 31:
            sys.exit(f'{code} {kit}: нет свободного варианта (0…31) или jerseyindex > 31')
        k = dict(club=code, kit=kit, teamid=team, style=1, art=art, variant=v, fevariant=v, jerseyindex=ji,
                 locstring=2 if kit == 'three' else 6)
        reg['kits'].append(k)
        added.append(k)
        ji += 1
        print(f'{code} {kit}: 1_{art}_{v} (fevariant {v}), jerseyindex {k["jerseyindex"]}, locstring {k["locstring"]}')
    if write and added:
        with open(REGISTRY + '.part', 'w', encoding='utf-8', newline='\n') as f:
            json.dump(reg, f, ensure_ascii=False, indent=1)
            f.write('\n')
        os.replace(REGISTRY + '.part', REGISTRY)
        print(f'записано в {REGISTRY}: +{len(added)}')
    elif added:
        print('(проба: --write — записать в реестр)')


def cmd_show(args):
    for k in load_registry()['kits']:
        print(f"{k['club']:4} {k['kit']:12} 1_{k['art']}_{k['variant']} fe{k['fevariant']} ji{k['jerseyindex']} "
              f"loc{k['locstring']}")


# ---------------------------------------------------------------- пакет и манифест

def load_manifest(pack):
    path = os.path.join(pack, 'manifest.json')
    if not os.path.exists(path):
        sys.exit(f'нет манифеста {path} — пакет nhl24 ещё не готов')
    man = json.load(open(path, encoding='utf-8'))
    if man.get('format') != 1:
        sys.exit(f'{path}: format {man.get("format")!r}, понимаю только 1 (docs/legacy-data.md, «Пакет NHL 24»)')
    return man


def check_manifest(pack, man, reg):
    """Ошибки манифеста и пакета (список строк) и {путь: запись} файлов."""
    bad, files = [], {}
    for e in man.get('files', []):
        rel, typ = e.get('file', ''), e.get('type')
        if typ not in TYPES:
            bad.append(f'{rel}: тип {typ!r} не знаю ({", ".join(TYPES)})')
            continue
        if '\\' in rel or '..' in rel.split('/') or rel.startswith('/') or not re.fullmatch(TYPES[typ], rel):
            bad.append(f'{rel}: путь не подходит к типу {typ}')
            continue
        if typ == 'other' and not e.get('note'):
            bad.append(f'{rel}: у типа other нужно поле note')
        if rel in files:
            bad.append(f'{rel}: два раза')
            continue
        p = os.path.join(pack, 'cache', *rel.split('/'))
        if not os.path.isfile(p):
            bad.append(f'{rel}: нет в {pack}/cache')
        elif os.path.getsize(p) != e.get('size') or md5(p) != e.get('md5'):
            bad.append(f'{rel}: md5/размер не как в манифесте')
        files[rel] = e
    clubs = man.get('clubs')
    if clubs != 'all' and (not isinstance(clubs, list) or any(c not in CLUBS for c in clubs)):
        bad.append(f'clubs: {clubs!r} — список кодов клубов или "all"')
    regmap = {(k['club'], k['kit']): k for k in reg['kits']}
    for k in man.get('kits', []):
        key = (k.get('club'), k.get('kit'))
        r = regmap.get(key)
        if not r:
            bad.append(f'новая форма {key}: нет в реестре {os.path.basename(REGISTRY)} (сначала nhl24.py alloc)')
            continue
        if 'variant' in k and k['variant'] != r['variant']:
            bad.append(f'новая форма {key}: variant {k["variant"]}, в реестре {r["variant"]}')
        if k.get('islightcolor') not in (0, 1):
            bad.append(f'новая форма {key}: islightcolor {k.get("islightcolor")!r} — нужен 0 или 1')
        lab = k.get('label')
        if lab is not None and (not isinstance(lab, str) or not 0 < len(lab) <= 32):
            bad.append(f'новая форма {key}: label {lab!r} — строка до 32 символов')
        for kind, pat in KIT_FILES.items():
            rel = pat.format(a=r['art'], v=r['variant'], f=r['fevariant'])
            if rel not in files:
                bad.append(f'новая форма {key}: в пакете нет {kind} {rel}')
    return bad, files


def build_db(base, man, reg, files):
    """База накладки: hastie = 0 у клубов пакета, новые строки в конец stockteamjerseys. → (байты базы, отчёт);
    на диск ничего не пишет (пишет cmd_build, когда обе базы собрались)."""
    db_path, db = open_db(base)
    rows = rows_of(db)
    scope = set(range(256)) if man['clubs'] == 'all' else {CLUBS[c][0] for c in man['clubs']}
    tie = [r['row'] for r in rows if r['teamid'] in scope and r['hastie']]
    for r in tie:
        db.set(T, 'hastie', r, 0)
    regmap = {(k['club'], k['kit']): k for k in reg['kits']}
    new = [regmap[(k['club'], k['kit'])] | {'islightcolor': k['islightcolor'], 'label': k.get('label')}
           for k in man.get('kits', [])]
    new.sort(key=lambda k: reg['kits'].index(regmap[(k['club'], k['kit'])]))
    # jerseyindex у клуба — подряд 0…N−1, как у всех 224 команд EA (с дырой игра не проверялась): форма из реестра
    # может не попасть в пакет, только если за ней в реестре нет форм этого клуба, которые в пакет попали
    for code in sorted({k['club'] for k in new}):
        team = CLUBS[code][0]
        idx = sorted([r['jerseyindex'] for r in rows if r['teamid'] == team] +
                     [k['jerseyindex'] for k in new if k['club'] == code])
        if idx != list(range(len(idx))):
            sys.exit(f'{code}: jerseyindex {idx} — не подряд (в пакете нет формы из середины реестра); '
                     f'добавьте её в пакет или уберите из пакета формы после неё')
    added = []
    if new:
        n = db.by_name[T]['rows']
        db.resize(T, n + len(new))
        for i, k in enumerate(new):
            team, art = check_club(db, k['club'])
            mine = [r for r in rows if r['teamid'] == team]
            if any(r['jerseyindex'] == k['jerseyindex'] for r in mine) or \
                    any(r['style'] == 1 and r['teamartid'] == art and r['variant'] == k['variant'] for r in rows):
                sys.exit(f'{k["club"]} {k["kit"]}: jerseyindex {k["jerseyindex"]} или 1_{art}_{k["variant"]} '
                         f'уже заняты в {db_path}')
            home = next((r for r in mine if r['style'] == 1 and r['locstring'] == 0), mine[0])
            db.put_record(T, n + i, db.record(T, home['row']))
            helmet = HELMET.format(a=art, v=k['variant']) in files
            for f, v in (('teamid', team), ('teamartid', art), ('style', 1), ('variant', k['variant']),
                         ('fevariant', k['fevariant']), ('jerseyindex', k['jerseyindex']),
                         ('locstring', k['locstring']), ('isdefault', 0), ('islockable', 0), ('hastie', 0),
                         ('helmetlogo', int(helmet)), ('helmetnumbers', 1), ('islightcolor', k['islightcolor'])):
                db.set(T, f, n + i, v)
            added.append(f"{k['club']} {k['kit']} 1_{art}_{k['variant']} ji{k['jerseyindex']} "
                         f"loc{k['locstring']} light{k['islightcolor']} helmetlogo{int(helmet)} (строка {n + i})")
    db.fix()
    if db.verify():
        sys.exit(f'{db_path}: CRC не сошлись после правки')
    out = bytes(db.d)
    rep = {'base': db_path, 'base_md5': md5(db_path), 'md5': hashlib.md5(out).hexdigest(),
           'hastie_zeroed': len(tie), 'rows_added': added}
    loc, labels = build_loc(base, new)
    if loc is not None:
        rep.update(loc_base_md5=md5(os.path.join(base, *LOC.split('/'))), loc_md5=hashlib.md5(loc).hexdigest(),
                   labels=labels)
    return (out, loc), rep


def build_loc(base, new):
    """Подписи новых форм с locstring 6 в локализации накладки (ключ Vintage_1_<арт>_<вариант>). → (байты | None,
    {ключ: текст}); подписей нет — None (локализация накладкой не ставится)."""
    want = {f"Vintage_1_{k['art']}_{k['variant']}": label_of(k['kit'], k.get('label'))
            for k in new if k['locstring'] == 6}
    want = {key: text for key, text in want.items() if text}
    if not want:
        return None, {}
    src = os.path.join(base, *LOC.split('/'))
    if not os.path.isfile(src):
        sys.exit(f'нет {src} — подписи новых форм некуда записать (build-all.sh collect, menu)')
    import locdb
    loc = locdb.LocDb(open(src, 'rb').read(), load_meta(LOC_META))
    for key, text in want.items():
        loc.put(key, text)
    bad = loc.check()
    if bad:
        sys.exit(f'{src}: ' + '; '.join(bad[:3]))
    loc.db.fix()
    return bytes(loc.db.d), want


def write_db(dst, data):
    db, loc = data
    os.makedirs(os.path.join(dst, 'db'), exist_ok=True)
    for name in ('nhlng.db', 'draft_roster.db'):           # draft_roster.db — та же база (docs/legacy-data.md)
        with open(os.path.join(dst, 'db', name), 'wb') as f:
            f.write(db)
    if loc is not None:
        p = os.path.join(dst, *LOC.split('/'))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, 'wb') as f:
            f.write(loc)


def to_stale(path, tag):
    if os.path.isdir(path):
        for root, dirs, names in os.walk(path):
            if any(os.path.islink(os.path.join(root, n)) for n in dirs + names):
                sys.exit(f'в {path} есть ссылки (symlink/junction) — разберитесь вручную')
        os.makedirs(STALE, exist_ok=True)
        old = base = os.path.join(STALE, f'{tag}-{time.strftime("%Y%m%d-%H%M%S")}')
        n = 1
        while os.path.exists(old):
            n += 1
            old = f'{base}-{n}'
        os.replace(path, old)
        print(f'прежняя {tag} → {old}')


def cmd_build(args):
    pack = os.path.abspath(args[0]) if args else PACK
    man, reg = load_manifest(pack), load_registry()
    bad, files = check_manifest(pack, man, reg)
    if bad:
        print('\n'.join('  ' + b for b in bad))
        sys.exit(f'пакет {pack}: {len(bad)} ошибок — накладку не собираю')
    # сначала обе базы — в памяти (их проверки могут остановить сборку), потом запись в .part и замена накладки
    db_out, rep_out = build_db(OUT, man, reg, files)
    ahl32 = os.path.isfile(os.path.join(OUT_AHL32, 'db', 'nhlng.db'))
    db_ahl32, rep_ahl32 = build_db(OUT_AHL32, man, reg, files) if ahl32 else (None, None)
    part, part_ahl32 = DST + '.part', DST_AHL32 + '.part'
    to_stale(part, 'out-nhl24.part')                   # остатки прерванной сборки
    to_stale(part_ahl32, 'out-nhl24-ahl32.part')
    for rel in sorted(files):
        p = os.path.join(part, *rel.split('/'))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        shutil.copyfile(os.path.join(pack, 'cache', *rel.split('/')), p)
    write_db(part, db_out)
    if ahl32:
        write_db(part_ahl32, db_ahl32)
    to_stale(DST, 'out-nhl24')
    to_stale(DST_AHL32, 'out-nhl24-ahl32')             # и прежняя база --ahl32, если этой сборке её не из чего делать
    os.replace(part, DST)
    if ahl32:
        os.replace(part_ahl32, DST_AHL32)
    report = {'pack': pack, 'manifest_md5': md5(os.path.join(pack, 'manifest.json')),
              'made': time.strftime('%Y-%m-%d %H:%M:%S'), 'files': len(files),
              'types': {t: sum(1 for e in files.values() if e['type'] == t) for t in TYPES}, 'out': rep_out}
    if ahl32:
        report['out-ahl32'] = rep_ahl32
    os.makedirs(INFO, exist_ok=True)
    shutil.copyfile(os.path.join(pack, 'manifest.json'), os.path.join(INFO, 'manifest.json'))
    with open(os.path.join(INFO, 'report.json'), 'w', encoding='utf-8', newline='\n') as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    t = ', '.join(f'{k} {v}' for k, v in report['types'].items() if v)
    print(f'out-nhl24: {len(files)} файлов пакета ({t}); база: hastie 0 у {report["out"]["hastie_zeroed"]} строк, '
          f'новых строк {len(report["out"]["rows_added"])}' + (', и out-nhl24-ahl32' if 'out-ahl32' in report else ''))
    for line in report['out']['rows_added']:
        print('   +', line)
    for key, text in report['out'].get('labels', {}).items():
        print(f'   подпись {key}: {text}')


def stamp():
    """Отчёт последней сборки накладки (для проверки установщиком: база out не пересобрана после неё)."""
    p = os.path.join(INFO, 'report.json')
    return json.load(open(p, encoding='utf-8')) if os.path.exists(p) else None


def cmd_verify(args):
    if not args:
        sys.exit(__doc__)
    cache = os.path.abspath(args[0])
    rep = stamp()
    if not rep:
        sys.exit('накладка не собиралась (нет game/work/legacy-data/nhl24/report.json)')
    man = json.load(open(os.path.join(INFO, 'manifest.json'), encoding='utf-8'))
    bad = 0
    for e in man['files']:
        p = os.path.join(cache, *e['file'].split('/'))
        if not os.path.isfile(p) or md5(p) != e['md5']:
            print(f'  не как в манифесте: {e["file"]}')
            bad += 1
    dbmd5 = md5(os.path.join(cache, 'db', 'nhlng.db'))
    want = {rep[k]['md5']: k for k in ('out', 'out-ahl32') if k in rep}
    key = want.get(dbmd5)
    print(f'файлов пакета: {len(man["files"])}, не совпало {bad}; база cache: {dbmd5[:8]} — '
          + ({'out': 'out-nhl24', 'out-ahl32': 'out-nhl24-ahl32'}.get(key) or 'НЕ база накладки'))
    if md5(os.path.join(cache, 'db', 'draft_roster.db')) != dbmd5:
        print('  draft_roster.db не та же, что nhlng.db')
        bad += 1
    if key and 'loc_md5' in rep[key]:                  # подписи новых форм
        loc = os.path.join(cache, *LOC.split('/'))
        ok = os.path.isfile(loc) and md5(loc) == rep[key]['loc_md5']
        print(f'локализация cache: {"с подписями новых форм" if ok else "НЕ локализация накладки"} '
              f'({len(rep[key]["labels"])} подписей)')
        bad += not ok
    sys.exit(1 if bad or not key else 0)


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')         # сообщения sys.exit
    cmds = {'alloc': cmd_alloc, 'build': cmd_build, 'verify': cmd_verify, 'show': cmd_show}
    if len(sys.argv) < 2 or sys.argv[1] not in cmds:
        sys.exit(__doc__)
    cmds[sys.argv[1]](sys.argv[2:])


if __name__ == '__main__':
    main()
