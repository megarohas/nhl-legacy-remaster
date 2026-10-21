"""Портреты из NHL 24 или NHL 27 игрокам NHL Legacy, у которых портрета нет (docs/player-photos-nhl24.md). Только офлайн.

Источник — `--source nhl24` (по умолчанию) или `--source nhl27` (21.10.2026: дамп PS5, портреты те же p<ID EA>
512×340, база — game/work/nhl27/db; рабочая папка — <work>/photos27, кэш — game/work/photos-nhl27). Ниже — про NHL 24,
у NHL 27 всё так же.

Источник — дамп NHL 24 (PS4): портреты `ui/textures/common/playerportraits/p<ID EA>` (BC3 512×340, фото с прозрачным
фоном) и база `gamemodes/database/t3db/nhl_game.db` (legacy-файл, fb.lfs; TDB little-endian): имя, дата рождения, ID EA
(`artid`), голова. ID EA у игроков исходной базы Legacy (2015) — тот же номер (`artid` Legacy): из 1388 сопоставленных по
имени и дате совпал у 1387.

Кому нет портрета: в базе Legacy hasportrait = 0 или нет файла p<artid>.big (ни в архивах игры, ни в out). Сопоставление
с NHL 24 (по порядку, принимается только однозначное):
  1) имя + фамилия + дата рождения (без диакритики и знаков, ø → o, ß → ss…);
  2) фамилия + дата рождения;
  3) имя + дата рождения при похожей фамилии (одна содержит другую или отличие ≤ 2 букв);
  4) ID EA: строка есть в исходной базе Legacy с тем же artid и той же фамилией (artid — ID EA) → p<artid> NHL 24;
     если этот ID есть и в базе NHL 24, фамилия там должна совпасть.
Портрет NHL 24 берётся, если есть текстура, чанк читается и это не силуэт-заглушка (серый, без цвета).
Портрет → кадр портретов НХЛ 336×336 (roster.photos_other.to_nhl_frame: макушка, шея, ширина головы) → оба размера
p<artid Legacy>.big по шаблонам Legacy (как tools/photos.py --game legacy).

  python tools/photos24.py match  [--variant out|out-ahl32]…  # → <work>/photos24/match-<variant>.json
  python tools/photos24.py build  [--jobs 6]                   # портреты → <work>/photos24/<variant>/fe/…
  python tools/photos24.py apply  [--variant …]                # в out: файлы fe и hasportrait = 1 (база, draft_roster)
  python tools/photos24.py sheet  [--variant out-ahl32] [--n 40]   # лист «NHL 24 → портрет Legacy»
  python tools/photos24.py report                              # сводка по лигам
  python tools/photos24.py save СЕЙВ_ROSTER [--write]          # hasportrait = 1 и в сохранённом составе (как в cache:)

<work> — game/work/legacy-data (или LEGACY_DATA_WORK). Кэш NHL 24 (база, выгруженные портреты) —
game/work/photos-nhl24/. Фото и ассеты NHL 24 — только для личного использования: всё лежит в game/ (вне git).
"""
import argparse
import csv
import json
import os
import re
import shutil
import statistics
import subprocess
import sys
import time
import unicodedata
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor

TOOLS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TOOLS)
os.environ.setdefault('NHL_GAME', 'legacy')
from roster import common  # noqa: E402

common.set_game('legacy')
from roster import dbview  # noqa: E402  (номера строк и поля Legacy берёт при импорте)
from tdb import Tdb  # noqa: E402
from tdb_read import load_meta  # noqa: E402

GAME_DIR = common.game_dir() if hasattr(common, 'game_dir') else os.path.join(TOOLS, '..', 'game')
G = common.GAME
SOURCES = {   # источник портретов: кэш, база игры, каталог дампа, рабочая подпапка <work>
    'nhl24': {'cache': os.path.join(GAME_DIR, 'work', 'photos-nhl24'), 'label': 'NHL 24', 'sub': 'photos24',
              'db': os.path.join(GAME_DIR, 'work', 'photos-nhl24', 'nhl24db'),
              'catalog': os.path.join(GAME_DIR, 'work', 'nhl24', 'catalog', 'textures.csv')},
    'nhl27': {'cache': os.path.join(GAME_DIR, 'work', 'photos-nhl27'), 'label': 'NHL 27', 'sub': 'photos27',
              'db': os.path.join(GAME_DIR, 'work', 'nhl27', 'db'),
              'catalog': os.path.join(GAME_DIR, 'work', 'nhl27', 'catalog', 'textures.csv')},
}
SOURCE = (sys.argv[sys.argv.index('--source') + 1] if '--source' in sys.argv else
          os.environ.get('PHOTOS_SOURCE', 'nhl24'))
if SOURCE not in SOURCES:
    sys.exit(f'--source: {", ".join(SOURCES)}')
os.environ['FB_GAME'] = SOURCE                              # дамп для модулей fb (импортируются позже)
SRC = SOURCES[SOURCE]
LABEL, SUB = SRC['label'], SRC['sub']
CACHE24 = SRC['cache']
DB24 = SRC['db']
SRC24 = os.path.join(CACHE24, 'portraits')                 # p<ID EA>.png — как в игре-источнике (512×340)
FRAME = os.path.join(CACHE24, 'frame')                     # p<ID EA>.png — в кадре НХЛ 336×336
CATALOG = SRC['catalog']
PORTRAIT_RX = re.compile(r'^ui/textures/common/playerportraits/p(\d+)$')
VARIANTS = ('out', 'out-ahl32')
EA_ART_MAX = 12814                  # artid исходной базы Legacy — до 12814 (новые конвейера — с 12815)
SPECIAL = ('national', 'prospects', 'winterclassic', 'eashl', 'custom')
TRANSLIT = str.maketrans({'ø': 'o', 'Ø': 'o', 'æ': 'ae', 'Æ': 'ae', 'ß': 'ss', 'ł': 'l', 'Ł': 'l', 'đ': 'd',
                          'Đ': 'd', 'ð': 'd', 'þ': 'th', 'œ': 'oe', 'ı': 'i'})


def work():
    return common.legacy_work(GAME_DIR)


def norm(s):
    s = unicodedata.normalize('NFKD', s.translate(TRANSLIT)).encode('ascii', 'ignore').decode().lower()
    return re.sub(r'[^a-z]', '', s)


def near(a, b):
    """Фамилии «похожи»: одна содержит другую (двойные фамилии) или отличие ≤ 2 букв (Левенштейн)."""
    if not a or not b:
        return False
    if a in b or b in a:
        return min(len(a), len(b)) >= 3
    if abs(len(a) - len(b)) > 2:
        return False
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1] <= 2


# --- NHL 24 -------------------------------------------------------------------------------------
class TdbLE(Tdb):
    """База NHL 24 (PS4): битовые поля записи — little-endian (бит k — в байте k // 8, с младшего)."""

    def get(self, table, field, row):
        t = self.by_name[table]
        off, width = t['fields'][field]
        rec = t['records'] + row * t['reclen']
        return (int.from_bytes(self.d[rec:rec + t['reclen']], 'little') >> off) & ((1 << width) - 1)


NHL24_FIELDS = ('artid', 'headid', 'headtexture', 'hasportrait', 'skincolor', 'hairid', 'haircolorcode', 'eyebrowid',
                'eyebrowcolorcode', 'eyecolorcode', 'team', 'position', 'game_id', 'height', 'weight')


def nhl24_db():
    """TdbLE базы NHL 24 (выгружается из дампа один раз — fb.lfs)."""
    db, meta = os.path.join(DB24, 'nhl_game.db'), os.path.join(DB24, 'nhl_game-meta.xml')
    if not (os.path.exists(db) and os.path.exists(meta)):
        from fb import lfs
        os.makedirs(DB24, exist_ok=True)
        for name, out in (('gamemodes/database/t3db/nhl_game.db', db), ('gamemodes/database/t3db/nhl_game-meta.xml', meta)):
            with open(out, 'wb') as f:
                f.write(lfs.get(name))
    return TdbLE(open(db, 'rb').read(), load_meta(meta))


def nhl24_players():
    """Игроки базы NHL 24: [{first, last, birth, artid, headid, …}] (кэш nhl24-players.json)."""
    cache = os.path.join(CACHE24, 'nhl24-players.json')
    if os.path.exists(cache):
        return json.load(open(cache, encoding='utf-8'))
    db = nhl24_db()
    t = 'exhibitionplayerbiotable'
    out = []
    for r in db.live_rows(t):
        p = {'row': r, 'first': db.get_string(t, 'firstname', r), 'last': db.get_string(t, 'lastname', r),
             'birth': [db.get(t, 'year', r) + 1900, db.get(t, 'month', r) + 1, db.get(t, 'day', r) + 1]}
        p.update({f: db.get(t, f, r) for f in NHL24_FIELDS})
        out.append(p)
    os.makedirs(CACHE24, exist_ok=True)
    json.dump(out, open(cache, 'w', encoding='utf-8'), ensure_ascii=False, indent=0)
    return out


def portrait_rows():
    """{ID EA: строка textures.csv} — портреты NHL 24, у которых в дампе есть заголовок текстуры."""
    out = {}
    with open(CATALOG, encoding='utf-8') as f:
        for r in csv.DictReader(f):
            m = PORTRAIT_RX.match(r['name'])
            if m and r['ofs']:
                out.setdefault(int(m.group(1)), r)
    return out


def is_silhouette(rgba, w, h):
    """Заглушка NHL 24 «нет фото» (p0) — однотонный серо-голубой силуэт: под альфой яркость не меняется
    (разброс 0; у настоящих портретов — от 40)."""
    import numpy as np
    a = np.frombuffer(rgba, np.uint8).reshape(h, w, 4).astype(np.float32)
    m = a[..., 3] > 128
    if m.sum() < 500:
        return True
    return a[..., :3][m].mean(1).std() < 12


def extract_portrait(ea_id, row=None):
    """p<ID EA> из дампа → SRC24/p<ID>.png (RGBA 512×340); → (путь или None, статус)."""
    png = os.path.join(SRC24, f'p{ea_id}.png')
    if os.path.exists(png):
        return png, 'ok'
    from fb import extract, texture
    if row is None:
        row = portrait_rows().get(ea_id)
        if row is None:
            return None, 'нет текстуры'
    try:
        h = extract.read_header(row)
        data, start = extract.read_chunk(h)
        if data is None:
            return None, 'нет чанка'
        img = texture.decode_mip(h, data, start, data_first=start).convert('RGBA')
    except Exception as err:  # noqa: BLE001
        return None, f'ошибка: {err}'
    os.makedirs(SRC24, exist_ok=True)
    img.save(png)
    return png, 'ok'


# --- Legacy -------------------------------------------------------------------------------------
def portrait_files(variant):
    """artid, у которых есть файл большого портрета: архив игры + out (+ накладка варианта)."""
    have = set()
    base = os.path.join(G.big, 'nocache', 'fe', 'ion', 'artassets', 'playerheads')
    trees = [base, os.path.join(work(), 'out', 'fe', 'ion', 'artassets', 'playerheads')]
    if variant != 'out':
        trees.append(os.path.join(work(), variant, 'fe', 'ion', 'artassets', 'playerheads'))
    for tree in trees:
        for d, _, fs in os.walk(tree):
            for f in fs:
                m = re.match(r'p(\d+)\.big$', f)
                if m:
                    have.add(int(m.group(1)))
    return have


def league_of(teams):
    if not teams:
        return 'free'
    for t in teams:
        if t in common.AHL_CLUBS:
            return 'ahl'
        lg = G.league_of_row(t)
        if lg and lg not in SPECIAL:
            return lg
    return G.league_of_row(teams[0]) or 'other'


def legacy_players(variant):
    meta = load_meta(os.path.join(work(), variant, 'db', 'nhlng-meta.xml'))
    db = Tdb(open(os.path.join(work(), variant, 'db', 'nhlng.db'), 'rb').read(), meta)
    v = dbview.View(db)
    have = portrait_files(variant)
    out = []
    for r in range(v.nbio):
        if v.created_slot(r):
            continue
        art = v.g('artid', r)
        out.append({'row': r, 'game_id': v.gid[r], 'first': v.s('firstname', r), 'last': v.s('lastname', r),
                    'birth': list(v.birth(r)), 'artid': art, 'hasportrait': v.g('hasportrait', r), 'file': art in have,
                    'headid': v.g('headid', r), 'skincolor': v.g('skincolor', r),
                    'league': league_of(v.teams_of.get(r, [])), 'teams': v.teams_of.get(r, [])})
    return out


def original_ea_ids():
    """{artid: нормализованная фамилия} исходной базы Legacy (там artid = ID EA)."""
    db = Tdb(open(G.db, 'rb').read(), load_meta(G.meta))
    t = 'exhibitionplayerbiotable'
    return {db.get(t, 'artid', r): norm(db.get_string(t, 'lastname', r)) for r in range(db.by_name[t]['rows'])
            if db.get(t, 'artid', r)}


# --- сопоставление ------------------------------------------------------------------------------
def match_one(p, by_birth, by_art, orig, prow):
    nl, nf = norm(p['last']), norm(p['first'])
    cands = by_birth.get(tuple(p['birth']), [])
    for how, test in (('имя+дата', lambda x: norm(x['last']) == nl and norm(x['first']) == nf),
                      ('фамилия+дата', lambda x: norm(x['last']) == nl),
                      ('имя+дата, фамилия похожа', lambda x: norm(x['first']) == nf and near(norm(x['last']), nl))):
        hit = [x for x in cands if test(x)]
        if len(hit) == 1:
            return hit[0]['artid'], how, hit[0]
        if len(hit) > 1:
            return None, f'неоднозначно ({how}: {len(hit)})', None
    a = p['artid']
    if a <= EA_ART_MAX and orig.get(a) == nl and a in prow:
        x = by_art.get(a)
        if x is None:
            return a, 'ID EA', None
        if norm(x['last']) == nl:
            return a, f'ID EA + фамилия {LABEL}', x
        return None, f"ID EA у другого в {LABEL} ({x['first']} {x['last']})", None
    return None, f'нет в {LABEL}', None


def cmd_match(variants):
    n24 = nhl24_players()
    prow = portrait_rows()
    orig = original_ea_ids()
    by_birth, by_art = defaultdict(list), {}
    for x in n24:
        by_birth[tuple(x['birth'])].append(x)
        by_art.setdefault(x['artid'], x)
    os.makedirs(os.path.join(work(), SUB), exist_ok=True)
    for variant in variants:
        players = legacy_players(variant)
        art_users = defaultdict(list)
        for p in players:
            art_users[p['artid']].append(p)
        res = []
        for p in players:
            if p['hasportrait'] and p['file']:
                continue
            ea, how, x = match_one(p, by_birth, by_art, orig, prow)
            rec = {k: p[k] for k in ('row', 'game_id', 'first', 'last', 'birth', 'artid', 'hasportrait', 'file',
                                     'headid', 'skincolor', 'league')}
            rec.update(ea=ea, how=how, n24=({k: x[k] for k in ('first', 'last', 'birth', 'artid', 'headid', 'hairid',
                                                               'haircolorcode', 'skincolor')} if x else None))
            others = [o for o in art_users[p['artid']] if o['row'] != p['row']]
            if not p['artid']:
                rec['status'] = 'нет artid'
            elif others:
                rec['status'] = f"artid {p['artid']} ещё у {others[0]['first']} {others[0]['last']}"
            elif ea is None:
                rec['status'] = how
            elif ea not in prow:
                rec['status'] = f'в {LABEL} нет портрета'
            else:
                png, st = extract_portrait(ea, prow[ea])
                if png is None:
                    rec['status'] = f'портрет {LABEL}: {st}'
                else:
                    from playerhead import png_read
                    w, h, rgba = png_read(png)
                    rec['status'] = f'силуэт {LABEL}' if is_silhouette(rgba, w, h) else 'ok'
            res.append(rec)
        path = os.path.join(work(), SUB, f'match-{variant}.json')
        json.dump(res, open(path, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        st = Counter(r['status'] if not r['status'].startswith('artid ') else 'artid занят' for r in res)
        print(f'{variant}: игроков {len(players)}, без портрета {len(res)}; найдено {st.get("ok", 0)}; '
              f'{dict(st.most_common())} → {path}')


# --- сборка -------------------------------------------------------------------------------------
_REF = None


def _build_one(job):
    """(ID EA, artid) → (artid, ID EA, статус): оба размера p<artid>.big в кэш <work>/photos24/cache/a<artid>-e<ID EA>/
    (результат зависит только от этой пары: шаблон — оригинал Legacy с тем же artid или p1)."""
    global _REF
    ea, artid = job
    from roster import photos_other
    ph = photos_other._ph('legacy')
    cdir = os.path.join(work(), SUB, 'cache', f'a{artid}-e{ea}')
    if all(os.path.exists(os.path.join(cdir, f'{k}.big')) for k in ('big', 'small')):
        return artid, ea, 'ok'
    try:
        if _REF is None:
            _REF = photos_other.nhl_reference(GAME_DIR)
        frame = os.path.join(FRAME, f'p{ea}.png')
        if not os.path.exists(frame):
            w, h, rgba = ph.png_read(os.path.join(SRC24, f'p{ea}.png'))
            img, geo = photos_other.to_nhl_frame(rgba, w, h, _REF)
            if img is None:
                return artid, ea, 'кадр не найден'
            os.makedirs(FRAME, exist_ok=True)
            ph.png_write(frame, 336, 336, img)
        mug = ph.png_read(frame)
        os.makedirs(cdir, exist_ok=True)
        for kind in ('big', 'small'):
            orig = ph.original_path(kind, artid)
            template = orig if os.path.exists(orig) else ph.default_template(kind)
            head = ph.PlayerHead.load(template)
            t = head.tex
            rgba = ph.compose(mug, kind, t.width, t.height, head.stage, False)
            data = head.with_blocks(ph.dxt5_encode(rgba, t.width, t.height), None if template == orig else 'md5')
            with open(os.path.join(cdir, f'{kind}.big.tmp'), 'wb') as f:
                f.write(data)
            os.replace(os.path.join(cdir, f'{kind}.big.tmp'), os.path.join(cdir, f'{kind}.big'))
        return artid, ea, 'ok'
    except Exception as err:  # noqa: BLE001 — отчёт по игроку, остальные собираются
        return artid, ea, f'ошибка: {err}'


def cmd_build(variants, jobs):
    """Сборка в кэш по парам (artid, ID EA); дерево варианта <work>/photos24/<вариант>/fe/… — копии из кэша."""
    from roster import photos_other
    ph = photos_other._ph('legacy')
    todo, res_of = set(), {}
    for variant in variants:
        mp = os.path.join(work(), SUB, f'match-{variant}.json')
        res_of[variant] = (mp, json.load(open(mp, encoding='utf-8')))
        todo |= {(r['ea'], r['artid']) for r in res_of[variant][1] if r['status'] == 'ok'}
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=jobs) as pool:
        done = {(ea, a): st for a, ea, st in pool.map(_build_one, sorted(todo), chunksize=2)}
    print(f'собрано {sum(1 for st in done.values() if st == "ok")} из {len(todo)} пар за {time.time() - t0:.0f} с')
    for k, st in done.items():
        if st != 'ok':
            print('  ', k, st)
    for variant, (mp, res) in res_of.items():
        root = os.path.join(work(), SUB, variant)
        n = 0
        for r in res:
            r.pop('built', None)
            r.pop('files', None)
            if r['status'] != 'ok':
                continue
            st = done.get((r['ea'], r['artid']))
            r['built'] = st
            if st != 'ok':
                continue
            r['files'] = []
            for kind in ('big', 'small'):
                rel = ph.asset_relpath(kind, r['artid'])
                dst = os.path.join(root, *rel.split('/'))
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copyfile(os.path.join(work(), SUB, 'cache', f"a{r['artid']}-e{r['ea']}", f'{kind}.big'), dst)
                r['files'].append(rel)
            n += 1
        json.dump(res, open(mp, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        print(f'{variant}: портретов {n} → {root}')


def built(variant):
    res = json.load(open(os.path.join(work(), SUB, f'match-{variant}.json'), encoding='utf-8'))
    return [r for r in res if r.get('built') == 'ok']


def set_portraits(db_path, rows, check=True):
    """hasportrait = 1 по строкам [(row, artid, game_id)]; artid и game_id строки должны совпасть."""
    meta = load_meta(os.path.join(os.path.dirname(db_path), 'nhlng-meta.xml'))
    db = Tdb(open(db_path, 'rb').read(), meta)
    t = 'exhibitionplayerbiotable'
    on = 0
    for row, artid, gid in rows:
        if db.get(t, 'artid', row) != artid or db.get(t, 'game_id', row) != gid:
            raise SystemExit(f'{db_path}: строка {row} — artid/game_id не те ({artid}, {gid}); match заново')
        if db.get(t, 'hasportrait', row) != 1:
            db.set(t, 'hasportrait', row, 1)
            on += 1
    db.fix()
    assert not db.verify()
    with open(db_path, 'wb') as f:
        f.write(db.d)
    return on


def owners(variant):
    """{artid: (game_id, hasportrait)} базы варианта в out."""
    meta = load_meta(os.path.join(work(), variant, 'db', 'nhlng-meta.xml'))
    db = Tdb(open(os.path.join(work(), variant, 'db', 'nhlng.db'), 'rb').read(), meta)
    t = 'exhibitionplayerbiotable'
    return {db.get(t, 'artid', r): (db.get(t, 'game_id', r), db.get(t, 'hasportrait', r)) for r in range(db.by_name[t]['rows'])}


def cmd_apply(variants):
    """Портреты в out: файлы fe (свой вариант — в свою папку) и hasportrait = 1; draft_roster.db — заново.
    Файлы out/fe видны и накладке out-ahl32: если там тот же artid у другого игрока с портретом, а своего файла у
    накладки нет — такой портрет в out не кладётся (конфликт в отчёте)."""
    others = {v: owners(v) for v in VARIANTS if os.path.exists(os.path.join(work(), v, 'db', 'nhlng.db'))}
    for variant in variants:
        rs = built(variant)
        src = os.path.join(work(), SUB, variant)
        dst = os.path.join(work(), variant)
        ok, conflict = [], []
        for r in rs:
            bad = None
            if variant == 'out':
                for ov, own in others.items():
                    if ov == 'out':
                        continue
                    o = own.get(r['artid'])
                    own_file = os.path.exists(os.path.join(work(), ov, *r['files'][0].split('/')))
                    if o and o[0] != r['game_id'] and o[1] == 1 and not own_file:
                        bad = f"{ov}: artid {r['artid']} у game_id {o[0]} с портретом"
            (conflict if bad else ok).append((r, bad))
        n = 0
        for r, _ in ok:
            for rel in r['files']:
                s, d = os.path.join(src, *rel.split('/')), os.path.join(dst, *rel.split('/'))
                os.makedirs(os.path.dirname(d), exist_ok=True)
                shutil.copyfile(s, d)
                n += 1
        db = os.path.join(dst, 'db', 'nhlng.db')
        on = set_portraits(db, [(r['row'], r['artid'], r['game_id']) for r, _ in ok])
        subprocess.run([sys.executable, os.path.join(TOOLS, 'legacy_data', 'draft_roster.py'), db,
                        os.path.join(dst, 'db', 'draft_roster.db')], check=True)
        log = os.path.join(work(), SUB, f'applied-{variant}.json')
        prev = {r['game_id']: r for r in json.load(open(log, encoding='utf-8'))} if os.path.exists(log) else {}
        prev.update({r['game_id']: dict(r, applied=time.strftime('%Y-%m-%d %H:%M')) for r, _ in ok})
        json.dump(sorted(prev.values(), key=lambda r: r['row']), open(log, 'w', encoding='utf-8'), ensure_ascii=False,
                  indent=1)
        print(f'{variant}: файлов {n}, hasportrait = 1 у {on} (портретов {LABEL}: {len(ok)}, конфликтов: {len(conflict)}) → {dst}')
        for r, why in conflict:
            print(f"   конфликт: {r['first']} {r['last']} — {why}")


def cmd_save(save, write, db_path=None):
    """Сохранённый состав пользователя (сейв ROSTER …): игра грузит его целиком, вместе с hasportrait, поэтому
    после установки базы флаг портрета переносится и туда — строкам exhibitionplayerbiotable с тем же game_id и
    artid, у которых в базе cache: hasportrait = 1. Остальное в сейве не трогается; копия до правки —
    <work>/backup-saves/, после записи — проверка CRC."""
    from tdb import SaveFile
    db_path = db_path or os.path.join(common.REPO, 'nhl-legacy-port', 'userdata', 'cache', 'guest', 'db', 'nhlng.db')
    meta = load_meta(os.path.join(os.path.dirname(db_path), 'nhlng-meta.xml'))
    db = Tdb(open(db_path, 'rb').read(), meta)
    t = 'exhibitionplayerbiotable'
    want = {(db.get(t, 'game_id', r), db.get(t, 'artid', r)) for r in range(db.by_name[t]['rows'])
            if db.get(t, 'hasportrait', r) == 1}
    raw = open(save, 'rb').read()
    sf = SaveFile(raw, meta)
    sv = sf.db
    rows = [r for r in sv.live_rows(t) if (sv.get(t, 'game_id', r), sv.get(t, 'artid', r)) in want
            and sv.get(t, 'hasportrait', r) != 1]
    print(f'{save}: hasportrait 0 → 1 у {len(rows)} игроков')
    if not write or not rows:
        return
    for r in rows:
        sv.set(t, 'hasportrait', r, 1)
    out = sf.bytes()
    assert not SaveFile(out, meta).verify()
    bk = os.path.join(work(), 'backup-saves', 'photos24-' + time.strftime('%Y%m%d-%H%M%S'))
    os.makedirs(bk, exist_ok=True)
    shutil.copyfile(save, os.path.join(bk, os.path.basename(save)))
    with open(save, 'wb') as f:
        f.write(out)
    print(f'записано; копия до правки — {bk}')


# --- отчёт и лист -------------------------------------------------------------------------------
LEAGUE_RU = {'nhl': 'НХЛ', 'ahl': 'АХЛ', 'shl': 'SHL', 'liiga': 'Liiga', 'del': 'DEL', 'extraliga': 'Экстралига',
             'nla': 'NLA', 'norway': 'Норвегия', 'national': 'сборные', 'ohl': 'OHL', 'qmjhl': 'QMJHL', 'whl': 'WHL',
             'eashl': 'EASHL', 'free': 'без клуба', 'winterclassic': 'Зимняя классика', 'prospects': 'проспекты'}


def cmd_report(variants):
    for variant in variants:
        res = json.load(open(os.path.join(work(), SUB, f'match-{variant}.json'), encoding='utf-8'))
        tot, ok = Counter(r['league'] for r in res), Counter(r['league'] for r in res if r.get('built', r['status']) == 'ok')
        print(f'{variant}: без портрета {len(res)}, найдено {sum(ok.values())}')
        for lg, n in tot.most_common():
            print(f'  {LEAGUE_RU.get(lg, lg):16} {ok.get(lg, 0):4} из {n}')
        print('  как найдены:', dict(Counter(r['how'] for r in res if r['status'] == 'ok')))


def cmd_sheet(variant, n, out):
    from PIL import Image, ImageDraw
    import playerhead as ph
    from roster import photos_other
    photos_other._ph('legacy')
    from PIL import ImageFont
    try:
        font = ImageFont.truetype(os.path.join(os.environ.get('WINDIR', r'C:\Windows'), 'Fonts', 'segoeui.ttf'), 13)
    except OSError:
        font = ImageFont.load_default()
    rs = built(variant)
    by = defaultdict(list)
    for r in rs:
        by[r['league']].append(r)
    pick, k = [], 0
    while len(pick) < min(n, len(rs)):                # поровну из лиг
        for lg in sorted(by, key=lambda x: -len(by[x])):
            if k < len(by[lg]) and len(pick) < n:
                pick.append(by[lg][k])
        k += 1
    cw, chh = 400, 196
    cols = 4
    sheet = Image.new('RGB', (cols * cw, ((len(pick) + cols - 1) // cols) * chh), (52, 52, 56))
    dr = ImageDraw.Draw(sheet)
    root = os.path.join(work(), SUB, variant)
    for i, r in enumerate(pick):
        x0, y0 = (i % cols) * cw, (i // cols) * chh
        src = Image.open(os.path.join(SRC24, f"p{r['ea']}.png")).convert('RGBA')
        src.thumbnail((180, 120))
        sheet.paste(src, (x0 + 4, y0 + 4), src)
        head = ph.PlayerHead.load(os.path.join(root, *r['files'][0].split('/')))
        w, h, rgba = head.decode_rgba()
        sw, sh = head.stage
        img = Image.frombytes('RGBA', (w, h), rgba).crop((0, 0, sw, sh))
        img.thumbnail((200, 120))
        sheet.paste(img, (x0 + 192, y0 + 4), img)
        dr.text((x0 + 6, y0 + 128), f"{r['first']} {r['last']}", fill=(255, 255, 255), font=font)
        dr.text((x0 + 6, y0 + 144), f"{LEAGUE_RU.get(r['league'], r['league'])} · {r['birth'][0]}-{r['birth'][1]:02}-"
                                    f"{r['birth'][2]:02} · {r['how']}", fill=(190, 190, 200), font=font)
        dr.text((x0 + 6, y0 + 160), f"{LABEL} p{r['ea']} → Legacy p{r['artid']}", fill=(150, 150, 160), font=font)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    sheet.save(out)
    print(f'лист: {len(pick)} игроков → {out}')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('cmd', choices=('match', 'build', 'apply', 'report', 'sheet', 'save'))
    ap.add_argument('save', nargs='?')
    ap.add_argument('--write', action='store_true')
    ap.add_argument('--db', help='save: база с флагами (по умолчанию cache: порта)')
    ap.add_argument('--variant', action='append', choices=VARIANTS)
    ap.add_argument('--jobs', type=int, default=6)
    ap.add_argument('--n', type=int, default=40)
    ap.add_argument('--out')
    ap.add_argument('--source', choices=tuple(SOURCES), default=SOURCE, help='игра-источник портретов (по умолчанию nhl24)')
    a = ap.parse_args()
    variants = a.variant or [v for v in VARIANTS if os.path.exists(os.path.join(work(), v, 'db', 'nhlng.db'))]
    if a.cmd == 'match':
        cmd_match(variants)
    elif a.cmd == 'build':
        cmd_build(variants, a.jobs)
    elif a.cmd == 'apply':
        cmd_apply(variants)
    elif a.cmd == 'report':
        cmd_report(variants)
    elif a.cmd == 'save':
        cmd_save(a.save, a.write, a.db)
    else:
        v = variants[-1]
        cmd_sheet(v, a.n, a.out or os.path.join(work(), SUB, f'sheet-{v}.png'))


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
