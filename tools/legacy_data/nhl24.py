"""Пакет NHL 24 → NHL Legacy (формы и шрифты номеров, центры и реклама льда, наклейки на шлемах, шорты и гетры,
клюшки, шайба): накладка game/work/legacy-data/out-nhl24 поверх out. Ставится
`install-legacy-data.sh [--ahl32] --nhl24`, снимается `uninstall-legacy-data.sh --nhl24` (docs/legacy-data.md, «NHL 24»).

    python tools/legacy_data/nhl24.py alloc КЛУБ ФОРМА… [--write]   # номера новых форм клуба → nhl24_kits.json
    python tools/legacy_data/nhl24.py order КЛУБ ФОРМА… [--write]   # порядок новых форм клуба в меню (jerseyindex)
    python tools/legacy_data/nhl24.py build [ПАКЕТ]                  # этап build-all nhl24 → out-nhl24 (+ out-nhl24-ahl32)
    python tools/legacy_data/nhl24.py verify CACHE                   # cache: после установки — как в манифесте и out-nhl24
    python tools/legacy_data/nhl24.py show                           # что в реестре новых форм
    python tools/legacy_data/nhl24.py save СЕЙВ [--write]            # новые строки форм и шлемов — в сейв ROSTER

Пакет готовит агент nhl24 (tools/fb/pack.py): ПАКЕТ/manifest.json и ПАКЕТ/cache/<путь в cache:>, по умолчанию
game/work/nhl24/out/pack (или переменная NHL24_PACK). Формат манифеста — docs/legacy-data.md, «Пакет NHL 24».

Новые формы (вариант «А», решение 09.10.2026): стиль 1, арт клуба (номер EA 0…29, SEA 100, VGK 101), новый вариант.
Номера выдаёт `alloc` и закрепляет в nhl24_kits.json (рядом, в git); список только дописывается, чтобы формы не
меняли номер между сборками. Вариант — наименьший, у которого у этого арта стиля 1 нет ни строки stockteamjerseys,
ни файла комплекта в архивах Legacy и в out (texlib/name/pant/sock/превью/наклейка на шлем); fevariant = variant;
jerseyindex — следующий за последним у клуба; locstring 6 у всех новых (своя подпись в меню, ниже).
Правила пользователя 10.10.2026:
- 05:50 — формы NHL 24 только дополнительными строками, оригиналы не перезаписываются. У каждого клуба (кроме ARI/UTA) —
  новые дом, выезд и третья подряд после форм EA (`order КЛУБ home away three`). Файл существующего комплекта (есть в
  архивах Legacy или в out) в пакете — ошибка сборки.
- 05:53 — по умолчанию (в матчах и во франшизе) — формы NHL 24: новые дом (тёмная) и выезд (светлая) получают
  isdefault 1, прежние строки по умолчанию того же цвета (EA; у SEA/VGK — наши 1_100_0/1, 1_101_0/1) — isdefault 0.
  Больше в прежних строках ничего не меняется (файлы, hastie, locstring, jerseyindex). Нет нового дома (выезда) — у
  клуба по умолчанию остаётся прежний дом (выезд).

Этап build (после collect): сверяет каждый файл пакета с манифестом (путь по типу, md5, размер), копирует их в
out-nhl24 и собирает базу накладки из out/db/nhlng.db (и out-ahl32/db/nhlng.db → out-nhl24-ahl32): новые строки
stockteamjerseys (hastie 0) в конец таблицы (номера прежних строк не сдвигаются) — только для форм, все файлы которых
есть в пакете; у прежних строк меняется только isdefault (правило 05:53). db/draft_roster.db накладка не кладёт: в нём только 10 таблиц exhibition* и
stockteamsalaryextras, их накладка не меняет — остаётся draft_roster.db из out (out-ahl32). Подписи
новых форм (locstring 6) — ключи Vintage_1_<арт>_<вариант> в fe/loc/NHL_ENG_US.db накладки. Отчёт и копия
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

# файлы комплекта стиля s (у формы NHL 24 «А» — 1; свитера adidas на сетке NHL 24 — 0, слот ретро-сеток,
# docs/nhl24-uniforms.md §14): обязательные у новой формы и наклейка на шлем (по ней helmetlogo = 1)
KIT_FILES = {'jersey': 'rendering/jersey/texlib_{s}_{a}_{v}.rx2', 'name': 'rendering/jersey/name_{s}_{a}_{v}_cm.rx2',
             'pant': 'rendering/pant/texlib_{s}_{a}_{v}.rx2', 'sock': 'rendering/sock/sock_{s}_{a}_{v}_cm.rx2',
             'fe': 'fe/ion/artassets/jerseys/jersey_{s}_{a}_{f}.big'}
HELMET = 'rendering/logo/texlib_{a}_{s}_{v}.rx2'
ARCHIVE = {'rendering/jersey/': 'nocacherender', 'rendering/': 'cacherender', 'fe/': 'cache'}

# типы файлов пакета: путь в cache: (полное совпадение)
TYPES = {
    'jersey': r'rendering/jersey/texlib_[01]_\d+_\d+\.rx2',       # свитер и шрифт номеров
    'name': r'rendering/jersey/name_[01]_\d+_\d+_cm\.rx2',         # карта номера и фамилии
    'pant': r'rendering/pant/texlib_[01]_\d+_\d+\.rx2',           # шорты
    'sock': r'rendering/sock/sock_[01]_\d+_\d+_cm\.rx2',           # гетры
    'fe': r'fe/ion/artassets/jerseys/jersey_[01]_\d+_\d+\.big',    # превью формы в меню
    'helmet': r'rendering/logo/texlib_\d+_[01]_\d+\.rx2',         # наклейка на шлем (логотип или спонсор)
    'center': r'rendering/icesurface/centerlogo_\d+_cm\.rx2',      # центр льда
    'ice': r'rendering/icesurface/[a-z0-9_]+\.rx2',               # логотипы и реклама на льду
    'puck': r'rendering/puck/[a-z0-9_]+\.rx2',                    # шайба
    'stick': r'rendering/playerstick/[a-z0-9_]+\.rx2',            # клюшки
    'other': r'(rendering|fe)/[a-z0-9_/]+\.(rx2|big)',            # прочее (с полем note)
}


# подпись формы в меню (Select Jerseys): у строки с locstring 6 игра берёт текст ключа Vintage_<style>_<art>_<variant>
# (так у 50 винтажных форм EA: Vintage_0_9_3 «1968-69 Away», Vintage_1_2_3 «2009-10 Classic»); нет ключа — подписи
# нет (тест DAL25). Новые формы NHL 24 — все с locstring 6 и своей подписью, чтобы в меню отличались от EA (правило
# 10.10). «label» в манифесте главнее этих:
LABELS = {'home': 'Home (NHL 24)', 'away': 'Away (NHL 24)', 'three': 'Third (NHL 24)',
          'ad_home': 'Home (adidas)', 'ad_away': 'Away (adidas)',     # свитер adidas NHL 24 на своей сетке (стиль 0)
          'rr22': 'Reverse Retro 2022', 'rr23': 'Reverse Retro 2023', 'n90_home': '1990s Home',
          'n90_away': '1990s Away', 'n90_three': '1990s Alternate'}
KIT_TYPES = ('jersey', 'name', 'pant', 'sock', 'fe', 'helmet')   # файлы комплекта: только новых номеров (правило 05:50)
DEFAULT_KITS = {'home': 0, 'away': 1}          # новые формы по умолчанию (правило 05:53): форма → islightcolor
# ТЕСТ CHI3 (legacy-port, 10.10 06:22): игра ищет форму по умолчанию дома по isdefault + locstring 0, в гостях — по
# isdefault + locstring 1 (у всех 222 команд EA строки по умолчанию — только loc 0 и 1, islightcolor любой); с locstring 6
# новые формы по умолчанию не находились. По коду (nhl-legacy-port): sub_82AEAD20 среди форм с isdefault ≠ 0 берёт ту, у
# которой locstring 0 (дома) или 1 (в гостях), иначе — последнюю с isdefault; islightcolor загрузчик не читает. Поэтому
# новые home/away — locstring 0/1 (подпись стандартная Home/Away), прежние строки по умолчанию — locstring 6 с подписью
# «Home (EA)» / «Away (EA)» (окончательное правило пользователя 10.10; ТЕСТ CHI3B)
DEFAULT_LOC = {'home': 0, 'away': 1}
OLD_DEFAULT_LABELS = {0: 'Home (EA)', 1: 'Away (EA)'}   # прежняя форма по умолчанию: islightcolor → подпись
# прежняя форма по умолчанию не из архивов EA (наши SEA/VGK czkit: 1_100_0/1, 1_101_0/1) — «(old)» (координатор 10.10)
OLD_OURS_LABELS = {0: 'Home (old)', 1: 'Away (old)'}


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


def variant_free(art, v, rows, reg, style=1, helm=()):
    """helm — (era, variant) строк шлема клуба: у EA бывают строки шлема вариантов без формы (BUF 0_3_3, CAR 0_5_2) —
    такой номер новой форме не годится (add_helmets: «у варианта уже есть строка шлема»)."""
    if (style - 1 if style == 1 else 0, v) in helm or (style == 1 and (1, v) in helm):
        return False
    if any(r['style'] == style and r['teamartid'] == art and v in (r['variant'], r['fevariant']) for r in rows):
        return False
    if any(k.get('style', 1) == style and k['art'] == art and v in (k['variant'], k['fevariant']) for k in reg['kits']):
        return False
    names = [p.format(s=style, a=art, v=v, f=v) for p in KIT_FILES.values()] + [HELMET.format(s=style, a=art, v=v)]
    return not any(file_taken(n) for n in names)


def cmd_alloc(args):
    write = '--write' in args
    style = 1
    if '--style' in args:                            # --style 0 — свитера adidas на сетке NHL 24 (слот стиля 0)
        i = args.index('--style')
        style = int(args[i + 1])
        args = args[:i] + args[i + 2:]
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
        helm = {(x[0], x[1]) for x in club_equipment(db, eq_low(db), team) if x[2] == EQ_HELMET}
        v = next((v for v in range(32) if variant_free(art, v, rows, reg, style, helm)), None)
        if v is None or ji > 31:
            sys.exit(f'{code} {kit}: нет свободного варианта (0…31) или jerseyindex > 31')
        k = dict(club=code, kit=kit, teamid=team, style=style, art=art, variant=v, fevariant=v, jerseyindex=ji,
                 locstring=6)
        reg['kits'].append(k)
        added.append(k)
        ji += 1
        print(f'{code} {kit}: {style}_{art}_{v} (fevariant {v}), jerseyindex {k["jerseyindex"]}, '
              f'locstring {k["locstring"]}')
    if write and added:
        save_registry(reg)
        print(f'записано в {REGISTRY}: +{len(added)}')
    elif added:
        print('(проба: --write — записать в реестр)')


def save_registry(reg):
    with open(REGISTRY + '.part', 'w', encoding='utf-8', newline='\n') as f:
        json.dump(reg, f, ensure_ascii=False, indent=1)
        f.write('\n')
    os.replace(REGISTRY + '.part', REGISTRY)


def cmd_order(args):
    """order КЛУБ ФОРМА… — jerseyindex форм клуба в реестре: подряд после форм базы, сначала перечисленные (дом, выезд,
    третья — правило 10.10), за ними остальные формы клуба в прежнем порядке; locstring у всех — 6. Номера вариантов не
    меняются. Пока накладка у пользователя не стоит, так можно (потом порядок закреплён)."""
    write = '--write' in args
    args = [a for a in args if a != '--write']
    if len(args) < 2:
        sys.exit(__doc__)
    code, first = args[0].upper(), args[1:]
    _, db = open_db(OUT)
    team, _ = check_club(db, code)
    reg = load_registry()
    mine = [k for k in reg['kits'] if k['club'] == code]
    missing = [x for x in first if x not in {k['kit'] for k in mine}]
    if missing:
        sys.exit(f'{code}: в реестре нет {missing} (сначала alloc)')
    order = [next(k for k in mine if k['kit'] == x) for x in first] + [k for k in mine if k['kit'] not in first]
    ji = max(r['jerseyindex'] for r in rows_of(db) if r['teamid'] == team) + 1
    changed = 0
    for i, k in enumerate(order):
        if (k['jerseyindex'], k['locstring']) != (ji + i, 6):
            changed += 1
        k['jerseyindex'], k['locstring'] = ji + i, 6
        print(f"{code} {k['kit']}: {k.get('style', 1)}_{k['art']}_{k['variant']}, jerseyindex {k['jerseyindex']}, "
              f"locstring 6")
    if write and changed:
        save_registry(reg)
        print(f'записано в {REGISTRY}: изменено {changed}')
    elif changed:
        print('(проба: --write — записать в реестр)')


def cmd_show(args):
    for k in load_registry()['kits']:
        print(f"{k['club']:4} {k['kit']:12} {k.get('style', 1)}_{k['art']}_{k['variant']} fe{k['fevariant']} "
              f"ji{k['jerseyindex']} "
              f"loc{k['locstring']}")


# ---------------------------------------------------------------- пакет и манифест

def load_manifest(pack):
    path = os.path.join(pack, 'manifest.json')
    if not os.path.exists(path):
        sys.exit(f'нет манифеста {path} — пакет nhl24 ещё не готов')
    raw = open(path, 'rb').read()                # читается один раз: nhl24 может дописывать пакет во время сборки
    man = json.loads(raw.decode('utf-8'))
    if man.get('format') != 1:
        sys.exit(f'{path}: format {man.get("format")!r}, понимаю только 1 (docs/legacy-data.md, «Пакет NHL 24»)')
    man['_raw'] = raw
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
        if typ in KIT_TYPES and file_taken(rel):
            bad.append(f'{rel}: это файл существующего комплекта (есть в архивах Legacy или в out) — формы NHL 24 '
                       f'только новыми строками с новыми номерами (правило 10.10)')
        if rel in files:
            bad.append(f'{rel}: два раза')
            continue
        p = os.path.join(pack, 'cache', *rel.split('/'))
        if not os.path.isfile(p):
            bad.append(f'{rel}: нет в {pack}/cache')
        elif os.path.getsize(p) != e.get('size') or md5(p) != e.get('md5'):
            bad.append(f'{rel}: md5/размер не как в манифесте')
        files[rel] = e
    clubs = man.get('clubs')                         # для людей: клубы пакета (шнуровку определяют файлы свитеров)
    if clubs is not None and clubs != 'all' and (not isinstance(clubs, list) or any(c not in CLUBS for c in clubs)):
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
        if k.get('helmet') not in (None, 'home', 'away'):
            bad.append(f'новая форма {key}: helmet {k.get("helmet")!r} — home, away или без поля')
        if k.get('kit') in DEFAULT_KITS and k.get('islightcolor') != DEFAULT_KITS[k['kit']]:
            bad.append(f'новая форма {key}: islightcolor {k.get("islightcolor")!r} — дом должен быть тёмным (0), '
                       f'выезд светлым (1): они становятся формами по умолчанию (правило 10.10)')
        for kind, pat in KIT_FILES.items():
            rel = pat.format(s=r.get('style', 1), a=r['art'], v=r['variant'], f=r['fevariant'])
            if rel not in files:
                bad.append(f'новая форма {key}: в пакете нет {kind} {rel}')
    return bad, files


def build_db(base, man, reg, files):
    """База накладки: hastie = 0 у строк со свитером из пакета, новые строки в конец stockteamjerseys. → (байты базы, отчёт);
    на диск ничего не пишет (пишет cmd_build, когда обе базы собрались)."""
    db_path, db = open_db(base)
    rows = rows_of(db)
    # правило 10.10 (05:50): прежние строки не меняются (hastie, locstring, jerseyindex — как были), пакет с файлами
    # существующих комплектов не проходит check_manifest; исключение — isdefault (правило 05:53, ниже)
    tie = []
    regmap = {(k['club'], k['kit']): k for k in reg['kits']}
    new = [regmap[(k['club'], k['kit'])] | {'islightcolor': k['islightcolor'], 'label': k.get('label'),
                                             'helmet': k.get('helmet')} for k in man.get('kits', [])]
    # строки — по клубу и порядку в меню; свитера adidas (ad_*, 16.10) — после всех прежних форм пакета: строки уже
    # поставленных форм (и их шлемов) остаются на своих местах — так их хранит и сейв ROSTER (nhl24.py save)
    new.sort(key=lambda k: (k['kit'].startswith('ad_'), CLUBS[k['club']][0], k['jerseyindex']))
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
    n_before = db.by_name[T]['rows']
    if new:
        n = db.by_name[T]['rows']
        db.resize(T, n + len(new))
        for i, k in enumerate(new):
            team, art = check_club(db, k['club'])
            mine = [r for r in rows if r['teamid'] == team]
            st = k.get('style', 1)
            if any(r['jerseyindex'] == k['jerseyindex'] for r in mine) or \
                    any(r['style'] == st and r['teamartid'] == art and r['variant'] == k['variant'] for r in rows):
                sys.exit(f'{k["club"]} {k["kit"]}: jerseyindex {k["jerseyindex"]} или {st}_{art}_{k["variant"]} '
                         f'уже заняты в {db_path}')
            home = next((r for r in mine if r['style'] == 1 and r['locstring'] == 0), mine[0])
            db.put_record(T, n + i, db.record(T, home['row']))
            helmet = HELMET.format(s=st, a=art, v=k['variant']) in files
            for f, v in (('teamid', team), ('teamartid', art), ('style', st), ('variant', k['variant']),
                         ('fevariant', k['fevariant']), ('jerseyindex', k['jerseyindex']),
                         ('locstring', final_loc(k)), ('isdefault', 0), ('islockable', 0), ('hastie', 0),
                         ('helmetlogo', int(helmet)), ('helmetnumbers', 1), ('islightcolor', k['islightcolor'])):
                db.set(T, f, n + i, v)
            added.append(f"{k['club']} {k['kit']} {st}_{art}_{k['variant']} ji{k['jerseyindex']} "
                         f"loc{final_loc(k)} light{k['islightcolor']} helmetlogo{int(helmet)} (строка {n + i})")
    first = [k for k in new if not k['kit'].startswith('ad_')]
    later = [k for k in new if k['kit'].startswith('ad_')]
    helmets = add_helmets(db, rows, first)
    if later:                                         # шлемы adidas — вторым проходом, после строк прежних форм
        ad_keys = {(CLUBS[k['club']][0], k.get('style', 1), k['variant']) for k in later}
        rows_mid = [r for r in rows_of(db) if (r['teamid'], r['style'], r['variant']) not in ad_keys]
        helmets += add_helmets(db, rows_mid, later)
    defaults, old_labels = set_defaults(db, rows, new, n_before)
    import draft_roster                               # накладка не должна менять таблицы draft_roster.db (он — из out)
    base_db = open_db(base)[1]
    for name in draft_roster.KEEP:
        if table_bytes(base_db, name) != table_bytes(db, name):
            sys.exit(f'накладка меняет {name} — тогда ей нужен свой draft_roster.db')
    db.fix()
    if db.verify():
        sys.exit(f'{db_path}: CRC не сошлись после правки')
    out = bytes(db.d)
    rep = {'base': db_path, 'base_md5': md5(db_path), 'md5': hashlib.md5(out).hexdigest(),
           'hastie_zeroed': len(tie), 'rows_added': added, 'helmets': helmets, 'defaults': defaults}
    loc, labels = build_loc(base, new, old_labels)
    if loc is not None:
        rep.update(loc_base_md5=md5(os.path.join(base, *LOC.split('/'))), loc_md5=hashlib.md5(loc).hexdigest(),
                   labels=labels)
    return (out, loc), rep


def final_loc(k):
    """locstring новой строки: у новых home/away (они — по умолчанию) — 0/1, у остальных — из реестра (6)."""
    return DEFAULT_LOC.get(k['kit'], k['locstring'])


def set_defaults(db, rows, new, n_before):
    """Правило 10.10 (05:53): по умолчанию — формы NHL 24. Новый дом (тёмный) и выезд (светлый) — isdefault 1 (их
    locstring 0/1 — final_loc), прежняя строка по умолчанию того же цвета у клуба (EA; у SEA/VGK — наши 1_100_0/1,
    1_101_0/1) — isdefault 0 и locstring 6 с подписью «Home (EA)» / «Away (EA)» (ТЕСТ CHI3). Нового дома (выезда) нет — у
    клуба остаётся прежний. Новые строки — в [n_before, конец). → ([описание], {ключ Vintage_…: подпись})."""
    out, labels = [], {}
    added = {(k['club'], k['kit']): n_before + i for i, k in enumerate(new)}
    for (code, kit), r_new in sorted(added.items(), key=lambda kv: kv[1]):
        if kit not in DEFAULT_KITS:
            continue
        team = CLUBS[code][0]
        light = DEFAULT_KITS[kit]
        old = [r for r in rows if r['teamid'] == team and r['isdefault'] and r['islightcolor'] == light]
        if len(old) != 1:
            sys.exit(f'{code}: прежних форм по умолчанию с islightcolor {light} — {len(old)}, ждал одну')
        o = old[0]
        db.set(T, 'isdefault', o['row'], 0)
        db.set(T, 'locstring', o['row'], 6)
        db.set(T, 'isdefault', r_new, 1)
        key = f"Vintage_{o['style']}_{o['teamartid']}_{o['variant']}"
        jersey = f"rendering/jersey/texlib_{o['style']}_{o['teamartid']}_{o['variant']}.rx2"
        ea = os.path.exists(os.path.join(REF, 'nocacherender', *jersey.split('/')))   # свитер в архивах EA — форма EA
        labels[key] = (OLD_DEFAULT_LABELS if ea else OLD_OURS_LABELS)[light]
        out.append(f"{code} {kit}: по умолчанию 1_{db.get(T, 'teamartid', r_new)}_{db.get(T, 'variant', r_new)} "
                   f"(строка {r_new}, locstring {db.get(T, 'locstring', r_new)}) вместо {o['style']}_{o['teamartid']}_"
                   f"{o['variant']} (строка {o['row']}: isdefault 0, locstring {o['locstring']} → 6, «{labels[key]}»)")
    return out, labels


EQ = 'stockteamequipmenttable'
EQ_HELMET = 7                                   # equipment шлема (в базе — 8, см. eq_low)
EQ_KEY = ('era', 'variant', 'equipment', 'brand')
EQ_ZONES = tuple(f'zone{i}_{c}' for i in range(1, 10) for c in 'rgb')
# цвет каски новой формы явно (координатор 11.10): клуб → форма → RGB; зоны строки — как у тёмных шлемов EA, Юты и CHI
HELMETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'nhl24_helmets.json')
DARK_TRIM = ((32, 32, 32), (231, 231, 231)) + ((32, 32, 32),) * 6     # зоны 2–9


def helmet_colors():
    """{(клуб, форма): зоны строки шлема (27 чисел)} из nhl24_helmets.json; файла нет — {}."""
    if not os.path.exists(HELMETS):
        return {}
    out = {}
    for club, kits in json.load(open(HELMETS, encoding='utf-8')).items():
        if club == 'about':
            continue
        for kit, rgb in kits.items():
            if len(rgb) != 3 or not all(isinstance(c, int) and 0 <= c <= 255 for c in rgb):
                sys.exit(f'{HELMETS}: {club} {kit} — нужен [R, G, B] 0…255, а не {rgb!r}')
            out[(club, kit)] = tuple(c for z in (tuple(rgb),) + DARK_TRIM for c in z)
    return out


def eq_low(db):
    """rangelow полей ключа экипировки из meta. У EA у team, era, variant, equipment и brand он −1: значение = сырое − 1
    (team 7 — CHI, era 0/1/2 — −1/0/1, variant 1 — 0, equipment 8 — шлем 7, brand 0 — −1, «любой»)."""
    for name, fields in db.meta.values():
        if name == EQ:
            low = {f: lo for f, lo, _ in fields.values()}
            return {f: low[f] for f in ('team',) + EQ_KEY}
    sys.exit(f'нет {EQ} в meta')


def _eq_dec(c, b, k):
    return c == k or (c == -1 and b != k)


def eq_better(key, c, b):
    """Компаратор sub_82AEDB98: запись c лучше лучшей b для ключа (era, variant, equipment, brand)? Сначала equipment,
    затем у типов 0–3 brand, era, variant, у остальных era, variant, brand: первое различающееся поле решает — лучше то,
    что равно ключу, или −1 («любое»), если у b оно не равно ключу."""
    if c[2] != b[2]:
        return _eq_dec(c[2], b[2], key[2])
    for i in ((3, 0, 1) if key[2] in (0, 1, 2, 3) else (0, 1, 3)):
        if c[i] != b[i]:
            return _eq_dec(c[i], b[i], key[i])
    return False


def eq_lookup(recs, key):
    """sub_82AEED60: от первой записи — к лучшей по компаратору, точное совпадение всех четырёх полей — сразу."""
    best = recs[0]
    for c in recs[1:]:
        if best[:4] == key:
            break
        if eq_better(key, c, best):
            best = c
    return best


def club_equipment(db, low, team, extra=()):
    """Записи экипировки клуба в том порядке, в каком их грузит игра (sub_82AF7610: team = клуб, ORDER BY equipment;
    внутри одного equipment — от последней строки базы к первой: только так сходятся все 15 кадров CHI — 10 форм EA в
    пилоте и 3 новые формы ТЕСТ CHI3; прямой порядок даёт 5 промахов). extra — записи, которые будут дописаны в конец
    базы. Запись: (era, variant, equipment, brand, строка базы, цвета зон)."""
    recs = [tuple(db.get(EQ, f, r) + low[f] for f in EQ_KEY) + (r, tuple(db.get(EQ, z, r) for z in EQ_ZONES))
            for r in db.live_rows(EQ) if db.get(EQ, 'team', r) + low['team'] == team]
    recs = (recs + list(extra))[::-1]
    recs.sort(key=lambda x: x[2])                   # сортировка устойчивая: внутри equipment — с конца базы
    return recs


def _shade(colors):
    r, g, b = colors[:3]                            # зона 1 — каска (красный канал маски helmet_*_tm)
    return 'тёмный' if (r * 3 + g * 6 + b) / 10 < 128 else 'светлый'


def add_helmets(db, rows, new):
    """Цвет шлема новых форм — строками stockteamequipmenttable (только новыми). Как выбирает игра (sub_829F1600 →
    sub_829EF868 → sub_82AEED60, ключ — из записи формы sub_829756C0): era = style формы, variant = variant формы,
    equipment 7 (шлем), brand — бренд шлема игрока. Значения в базе — со сдвигом (eq_low). У EA строки шлема форм стиля
    1 — era −1 («любая», в базе 0) с variant формы, у форм стиля 0 — era 0 (в базе 1). Формы без своей строки берут
    первую подходящую в порядке загрузки (club_equipment) — у CHI это 241 (светлая): поэтому в ТЕСТ CHI3 все новые формы
    были в белых шлемах (строки 6040/6041 были с era 0 — для ретро-форм — и variant на 1 меньше).
    Новой форме — строка (era как у шлемов форм стиля 1 этого клуба, variant формы) с цветами шлема, который игра сейчас
    даёт домашней (тёмной новой) или выездной (светлой) форме клуба; manifest kits[].helmet = home | away — явно.
    Цвет каски можно задать явно — nhl24_helmets.json (клуб → форма → RGB; координатор 11.10: у SEA и VGK прежние формы
    czkit в белых шлемах, и новые тёмные брали белый): тогда у строки зона 1 — этот цвет, остальные — как у тёмных
    шлемов EA, Юты и CHI (DARK_TRIM). Новые строки встают в порядке загрузки первыми и могут перехватить формы клуба без
    своей строки шлема — таким формам дописывается строка с их нынешним цветом («закреплён»). Сверка на модели: у
    прежних форм клуба шлем не меняется, у новых — как у образца или заданный. → [описание добавленного]."""
    low = eq_low(db)
    done, adds = [], []
    explicit = helmet_colors()
    for code in sorted({k['club'] for k in new}, key=lambda c: CLUBS[c][0]):
        team, art = CLUBS[code]
        recs = club_equipment(db, low, team)
        helm = [x for x in recs if x[2] == EQ_HELMET]
        if not helm:
            sys.exit(f'{code}: у клуба нет строк шлема ({EQ}, equipment {EQ_HELMET}) — цвет новых форм не задать')
        # строки шлема под бренд каски игрока (у CGY — бренд 4): модель сверяется по каждому такому бренду и по «любому
        # другому» (gen; у клубов без них — 0, как раньше); новые строки — бренд −1 («любой»)
        brands = sorted({x[3] for x in helm if x[3] != -1})
        gen = next(b for b in range(64) if b not in brands)
        BR = brands + [gen]
        mine = [r for r in rows if r['teamid'] == team]
        kits = sorted({(r['style'], r['variant']) for r in mine})

        def key(style, variant, brand=gen):
            return style, variant, EQ_HELMET, brand

        pre = {kv: eq_lookup(recs, key(*kv)) for kv in kits}
        pre_b = {(kv, b): eq_lookup(recs, key(*kv, b)) for kv in kits for b in BR}
        era1 = 1 if any(x[0] == 1 for x in helm) else -1          # какие строки шлема берут формы стиля 1
        club = []                                          # (запись-образец, era, variant, описание, зоны шлема)
        for k in [k for k in new if k['club'] == code]:
            like = k.get('helmet') or ('away' if k['islightcolor'] else 'home')
            sk = next((r for r in mine if r['style'] == 1 and r['locstring'] == (0 if like == 'home' else 1)), None)
            if sk is None:
                sys.exit(f"{code} {k['kit']}: у клуба нет {'домашней' if like == 'home' else 'выездной'} формы стиля 1 "
                         f'(locstring {0 if like == "home" else 1}) — не с чего взять цвет шлема')
            st = k.get('style', 1)
            era_k = era1 if st == 1 else 0                 # у EA шлемы форм стиля 0 — era 0 (в базе 1)
            if any(x[0] == era_k and x[1] == k['variant'] for x in helm):
                sys.exit(f"{code} {k['kit']}: у варианта {k['variant']} уже есть строка шлема — не тот номер?")
            src = pre[(1, sk['variant'])]
            zones = explicit.get((code, k['kit']))
            if zones is None:
                club.append((src, era_k, k['variant'],
                             f"{code} {k['kit']} {st}_{art}_{k['variant']}: шлем как у "
                             f"{'домашней' if like == 'home' else 'выездной'} 1_{art}_{sk['variant']} — {_shade(src[5])} "
                             f"(строка {src[4]})", src[5]))
            else:
                club.append((src, era_k, k['variant'],
                             f"{code} {k['kit']} {st}_{art}_{k['variant']}: каска {zones[:3]} — "
                             f"{os.path.basename(HELMETS)}", zones))
        for _ in range(len(kits) + 1):
            extra = [(era, v, EQ_HELMET, -1, None, zones) for src, era, v, _, zones in club]
            post_recs = club_equipment(db, low, team, extra)
            moved = [kv for kv in kits if any(eq_lookup(post_recs, key(*kv, b))[5] != pre_b[(kv, b)][5] for b in BR)]
            if not moved:
                break
            for s, v in moved:
                club.append((pre[(s, v)], era1 if s == 1 else 0, v,
                             f'{code} {s}_{art}_{v}: шлем как был — {_shade(pre[(s, v)][5])} (строка {pre[(s, v)][4]}), '
                             f'закреплён', pre[(s, v)][5]))
        else:
            sys.exit(f'{code}: шлемы прежних форм не удаётся сохранить — модель не сошлась')
        mine_new = [k for k in new if k['club'] == code]
        for (src, era, v, _, zones), k in zip(club[:len(mine_new)], mine_new):
            for b in BR:
                got = eq_lookup(post_recs, key(k.get('style', 1), v, b))
                if got[5] != zones:
                    sys.exit(f'{code} {k.get("style", 1)}_{art}_{v}: по модели шлем не тот (строка {got[4]}, бренд {b})')
        new_keys = {(k.get('style', 1), k['variant']) for k in mine_new}
        for kv in kits:                                     # прежние формы клуба — шлем как был
            if kv not in new_keys and any(eq_lookup(post_recs, key(*kv, b))[5] != pre_b[(kv, b)][5] for b in BR):
                sys.exit(f'{code} {kv[0]}_{art}_{kv[1]}: по модели у прежней формы сменился шлем')
        adds += club
        done += [d for _, _, _, d, _ in club]
    if adds:
        n = db.by_name[EQ]['rows']
        db.resize(EQ, n + len(adds))
        for i, (src, era, v, _, zones) in enumerate(adds):
            db.put_record(EQ, n + i, db.record(EQ, src[4]))     # team, equipment, brand (−1), цвета — как у образца
            db.set(EQ, 'era', n + i, era - low['era'])
            db.set(EQ, 'variant', n + i, v - low['variant'])
            db.set(EQ, 'index', n + i, n + i)
            if zones != src[5]:                                 # каска задана явно (nhl24_helmets.json)
                for f, c in zip(EQ_ZONES, zones):
                    db.set(EQ, f, n + i, c)
    return done


def build_loc(base, new, extra=None):
    """Подписи новых форм с locstring 6 (ключ Vintage_1_<арт>_<вариант>) и прежних форм по умолчанию, ставших
    locstring 6 (extra), в локализации накладки. → (байты | None, {ключ: текст}); подписей нет — None (локализация
    накладкой не ставится)."""
    want = {f"Vintage_{k.get('style', 1)}_{k['art']}_{k['variant']}": label_of(k['kit'], k.get('label'))
            for k in new if final_loc(k) == 6}
    want = {key: text for key, text in want.items() if text}
    want.update(extra or {})
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


def table_bytes(db, name):
    """Раскладка и записи таблицы (для сравнения двух баз; CRC заголовка не входит)."""
    t = db.by_name[name]
    return t['reclen'], t['rows'], sorted(t['fields'].items()), \
        bytes(db.d[t['records']:t['records'] + t['reclen'] * t['rows']])


def write_db(dst, data):
    db, loc = data
    os.makedirs(os.path.join(dst, 'db'), exist_ok=True)
    with open(os.path.join(dst, 'db', 'nhlng.db'), 'wb') as f:   # draft_roster.db — из out: его 10 таблиц не меняются
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
        if md5(p) != files[rel]['md5']:              # файл пакета сменился после сверки (пакет дописывают)
            sys.exit(f'{rel}: изменился во время сборки — пакет ещё дописывается, повторите позже '
                     f'(недособранная накладка — {part}, прежняя не тронута)')
    write_db(part, db_out)
    if ahl32:
        write_db(part_ahl32, db_ahl32)
    to_stale(DST, 'out-nhl24')
    to_stale(DST_AHL32, 'out-nhl24-ahl32')             # и прежняя база --ahl32, если этой сборке её не из чего делать
    os.replace(part, DST)
    if ahl32:
        os.replace(part_ahl32, DST_AHL32)
    report = {'pack': pack, 'manifest_md5': hashlib.md5(man['_raw']).hexdigest(),
              'made': time.strftime('%Y-%m-%d %H:%M:%S'), 'files': len(files),
              'types': {t: sum(1 for e in files.values() if e['type'] == t) for t in TYPES}, 'out': rep_out}
    if ahl32:
        report['out-ahl32'] = rep_ahl32
    os.makedirs(INFO, exist_ok=True)
    with open(os.path.join(INFO, 'manifest.json'), 'wb') as f:   # тот манифест, по которому собрано
        f.write(man['_raw'])
    # список путей накладки (cache:) — для тех, кому нужно знать, что в cache: от NHL 24 (папка для друзей и т. п.)
    paths = set()
    for d in (DST, DST_AHL32):
        for root, _, names in os.walk(d):
            paths |= {os.path.relpath(os.path.join(root, n), d).replace(os.sep, '/') for n in names}
    with open(os.path.join(INFO, 'files.txt'), 'w', encoding='utf-8', newline='\n') as f:
        f.write(''.join(x + '\n' for x in sorted(paths)))
    with open(os.path.join(INFO, 'report.json'), 'w', encoding='utf-8', newline='\n') as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    t = ', '.join(f'{k} {v}' for k, v in report['types'].items() if v)
    print(f'out-nhl24: {len(files)} файлов пакета ({t}); база: hastie 0 у {report["out"]["hastie_zeroed"]} строк, '
          f'новых строк {len(report["out"]["rows_added"])}' + (', и out-nhl24-ahl32' if 'out-ahl32' in report else ''))
    for line in report['out']['rows_added']:
        print('   +', line)
    for key, text in report['out'].get('labels', {}).items():
        print(f'   подпись {key}: {text}')
    for line in report['out'].get('helmets', []):
        print('   шлем', line)
    for line in report['out'].get('defaults', []):
        print('   по умолчанию', line)


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
    if key:                                            # draft_roster.db — тот, что ставит out (накладка его не меняет)
        ref = os.path.join(OUT if key == 'out' else OUT_AHL32, 'db', 'draft_roster.db')
        if not os.path.isfile(ref) or md5(os.path.join(cache, 'db', 'draft_roster.db')) != md5(ref):
            print(f'  draft_roster.db не тот, что в {key}')
            bad += 1
    if key and 'loc_md5' in rep[key]:                  # подписи новых форм
        loc = os.path.join(cache, *LOC.split('/'))
        ok = os.path.isfile(loc) and md5(loc) == rep[key]['loc_md5']
        print(f'локализация cache: {"с подписями новых форм" if ok else "НЕ локализация накладки"} '
              f'({len(rep[key]["labels"])} подписей)')
        bad += not ok
    sys.exit(1 if bad or not key else 0)


def cmd_save(args):
    """save СЕЙВ [--write] — новые строки форм и шлемов поставленной накладки (stockteamjerseys и stockteamequipmenttable
    базы cache: db/nhlng.db) в сейв ROSTER: у сейва эти таблицы свои, игра берёт формы из него (ТЕСТ DAL25). Прежние
    живые записи сейва должны совпадать с базой запись в запись (иначе — стоп: сейв правили иначе); новые дописываются
    в конец (таблица расширяется). Копия до правки — game/work/legacy-data/backup-saves/<сейв>-<время>/."""
    write = '--write' in args
    args = [a for a in args if a != '--write']
    if not args:
        sys.exit(__doc__)
    from install_legacy_data import cache_dir
    from tdb import SaveFile
    save = os.path.abspath(args[0])
    cache = cache_dir()
    meta = load_meta(os.path.join(cache, 'db', 'nhlng-meta.xml'))
    db = Tdb(open(os.path.join(cache, 'db', 'nhlng.db'), 'rb').read(), meta)
    raw = open(save, 'rb').read()
    sf = SaveFile(raw, meta)
    sv = sf.db
    total = 0
    for t in (T, EQ):
        if t not in sv.by_name:
            print(f'{t}: в сейве нет — пропуск')
            continue
        src = [bytes(db.record(t, r)) for r in db.live_rows(t)]
        live = sv.live_rows(t)
        dst = [bytes(sv.record(t, r)) for r in live]
        if live != list(range(len(live))):
            sys.exit(f'{t}: в сейве удалённые записи — дописывать в такой сейв не берусь')
        if dst != src[:len(dst)]:
            bad = next(i for i, (a, b) in enumerate(zip(dst, src)) if a != b) if len(dst) <= len(src) else len(src)
            sys.exit(f'{t}: запись {bad} сейва не как в базе cache: — сейв правили иначе (или база не та)')
        extra = src[len(dst):]
        print(f'{t}: в сейве {len(dst)}, в базе {len(src)} — дописать {len(extra)}')
        if extra:
            sv.resize(t, len(src))
            for i, rec in enumerate(extra):
                sv.put_record(t, len(dst) + i, rec)
            total += len(extra)
    if not write or not total:
        print('без --write ничего не записано' if total else 'сейв уже совпадает с базой')
        return
    out = sf.bytes(fix=True)
    bdir = os.path.join(W, 'backup-saves', f'{os.path.basename(save)}-{time.strftime("%Y%m%d-%H%M%S")}')
    os.makedirs(bdir, exist_ok=True)
    bak = os.path.join(bdir, os.path.basename(save) + '.bak')
    open(bak, 'wb').write(raw)
    open(save, 'wb').write(out)
    bad = SaveFile(open(save, 'rb').read(), meta).verify()
    if bad:
        open(save, 'wb').write(raw)
        sys.exit(f'проверка не прошла, сейв возвращён: {bad}')
    chk = SaveFile(open(save, 'rb').read(), meta).db
    for t in (T, EQ):
        if t in chk.by_name and [bytes(chk.record(t, r)) for r in chk.live_rows(t)] != \
                [bytes(db.record(t, r)) for r in db.live_rows(t)]:
            open(save, 'wb').write(raw)
            sys.exit(f'{t}: после записи сейв не как база — сейв возвращён')
    print(f'записано: +{total} строк; CRC и обёртка — OK; копия до правки — {bak}')


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')         # сообщения sys.exit
    cmds = {'alloc': cmd_alloc, 'order': cmd_order, 'build': cmd_build, 'verify': cmd_verify, 'show': cmd_show,
            'save': cmd_save}
    if len(sys.argv) < 2 or sys.argv[1] not in cmds:
        sys.exit(__doc__)
    cmds[sys.argv[1]](sys.argv[2:])


if __name__ == '__main__':
    main()
