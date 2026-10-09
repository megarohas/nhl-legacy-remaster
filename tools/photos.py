"""Портреты игроков НХЛ 2026/27 в игру (разбор и план — docs/player-photos.md).

    python photos.py fetch [--work DIR]                 # портреты NHL → game/work/roster-cache/photos/20262027/
    python photos.py build [--work DIR] [--jobs N]      # → game/work/photos-all/fe/… (оба размера) + photos.json
    python photos.py db DB_IN DB_OUT [--work DIR]       # hasportrait = 1 у игроков с собранным фото
    python photos.py save SAVE_DIR                      # то же в сейве франшизы (leagueplayerbiotable, по artid);
                                                        # копия до правки — game/work/backup-saves/

DIR — папка конвейера составов с players.json (адрес портрета) и write.json (строка базы и
artid каждого игрока); по умолчанию game/work/roster-lines.
--game legacy (tools/gameprofile.py, или NHL_GAME=legacy): портреты под NHL Legacy — папка по artid
как в её generalhelpers.big (≤ 4000, ≤ 8000, ≤ 60000 → p8001_12000, у NHL 13 — ≤ 12000), шаблоны —
из архивов Legacy (большие — nocache, малые — cache), вывод — game/work/legacy-data/photos-all,
папка конвейера по умолчанию — game/work/legacy-data/roster. Портреты НХЛ: 336×336 PNG с
прозрачным фоном; нет фото — CDN отвечает 302 на default-skater.png: редирект не проходим,
игрок остаётся с силуэтом игры (отметка .default). Пауза между запросами — 1 с.
Фото принадлежат НХЛ: только для личного использования, лежат в game/ (вне git).
"""
import http.client, json, os, sys, time, urllib.error, urllib.request
from concurrent.futures import ProcessPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gameprofile  # noqa: E402
import playerhead  # noqa: E402

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
CACHE = os.path.join(ROOT, 'game', 'work', 'roster-cache', 'photos', '20262027')
OUT = os.path.join(ROOT, 'game', 'work', 'photos-all')
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) megarohas-nhl13 (personal use)'
PNG = b'\x89PNG\r\n\x1a\n'


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # 302 → HTTPError: у игрока нет фото, заглушку НХЛ не берём


def arg(name, default=None):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def use_game(name):
    """Портреты другой игры: архивы с оригиналами и папка по artid (playerhead.py написан под NHL 13).
    Вызывается при импорте (и в процессах пула — sys.argv у них тот же)."""
    if name != 'legacy':
        return 16383
    playerhead.KINDS['big'] = ('playerheads', 'nocache.big', ('other', 'legacy', 'big', 'nocache'))
    playerhead.KINDS['small'] = ('playerheadssmall', 'cache.big', ('other', 'legacy', 'big', 'cache'))

    def folder_for(artid):
        # generalhelpers.big Legacy: «push 60000» на месте 12000 у NHL 13 — до 60000 всё в p8001_12000
        if artid <= 4000:
            return 'p0_4000'
        if artid <= 8000:
            return 'p4001_8000'
        if artid <= 60000:
            return 'p8001_12000'
        return 'silhouettes'
    playerhead.folder_for = folder_for
    return 59999                                  # 60000+ — силуэты Legacy


GAME = gameprofile.get(arg('--game') if arg('--game') in gameprofile.GAMES else None)   # --game у roster — и каталог
ART_MAX = use_game(GAME.name)
if GAME.name == 'legacy':
    OUT = GAME.work_dir('photos-all')           # game/work/legacy-data/photos-all (или LEGACY_DATA_WORK)


def work_dir():
    if GAME.name == 'legacy':
        return arg('--work', GAME.work_dir('roster'))
    return arg('--work', os.path.join(ROOT, 'game', 'work', 'roster-lines'))


def load(name):
    return json.load(open(os.path.join(work_dir(), name), encoding='utf-8'))


def cmd_fetch():
    os.makedirs(CACHE, exist_ok=True)
    opener = urllib.request.build_opener(NoRedirect)
    players = load('players.json')['players']
    got = default = cached = failed = 0
    last = 0.0
    for i, p in enumerate(players):
        url, nid = p.get('photo'), p.get('nhl_id')
        if not url or not nid:
            continue
        fn = os.path.join(CACHE, f'{nid}.png')
        if os.path.exists(fn) or os.path.exists(fn + '.default') or os.path.exists(fn + '.404'):
            cached += 1
            continue
        for attempt in range(6):
            wait = 1.0 - (time.time() - last)
            if wait > 0:
                time.sleep(wait)
            last = time.time()
            try:
                req = urllib.request.Request(url, headers={'User-Agent': UA})
                with opener.open(req, timeout=60) as r:
                    body = r.read()
                if body[:8] != PNG:
                    raise ValueError('не PNG')
                open(fn, 'wb').write(body)
                got += 1
                break
            except urllib.error.HTTPError as err:
                if err.code in (301, 302, 303, 307, 308):
                    open(fn + '.default', 'w').write(err.headers.get('Location', ''))
                    default += 1
                    break
                if err.code == 404:
                    open(fn + '.404', 'w').close()
                    default += 1
                    break
                if err.code not in (403, 429, 500, 502, 503, 504) or attempt == 5:
                    print(f'  {nid}: HTTP {err.code}')
                    failed += 1
                    break
                time.sleep(min(60, 5 * 2 ** attempt))
            except (urllib.error.URLError, http.client.HTTPException, OSError, ValueError) as err:
                if attempt == 5:
                    print(f'  {nid}: {err}')
                    failed += 1
                    break
                time.sleep(min(30, 3 * 2 ** attempt))
        if (i + 1) % 50 == 0:
            print(f'  {i + 1}/{len(players)}: скачано {got}, без фото {default}, в кэше {cached}, ошибок {failed}', flush=True)
    print(f'итого: скачано {got}, без фото {default}, уже было {cached}, ошибок {failed} → {CACHE}')


def build_one(job):
    nid, artid, name = job
    fn = os.path.join(CACHE, f'{nid}.png')
    if not os.path.exists(fn):
        return nid, artid, name, 'нет фото', []
    try:
        mug = playerhead.png_read(fn)
        files = []
        for kind in ('big', 'small'):
            orig = playerhead.original_path(kind, artid)
            template = orig if os.path.exists(orig) else playerhead.default_template(kind)
            head = playerhead.PlayerHead.load(template)
            t = head.tex
            rgba = playerhead.compose(mug, kind, t.width, t.height, head.stage, False)
            blocks = playerhead.dxt5_encode(rgba, t.width, t.height)
            data = head.with_blocks(blocks, None if template == orig else 'md5')
            rel = playerhead.asset_relpath(kind, artid)
            out = os.path.join(OUT, *rel.split('/'))
            os.makedirs(os.path.dirname(out), exist_ok=True)
            open(out, 'wb').write(data)
            files.append(rel)
        return nid, artid, name, 'ok', files
    except Exception as err:  # noqa: BLE001 — отчёт по игроку, сборка остальных продолжается
        return nid, artid, name, f'ошибка: {err}', []


def cmd_build():
    jobs = int(arg('--jobs', '6'))
    players = load('write.json')['players']
    work = [(p['nhl_id'], p['artid'], p.get('name', '')) for p in players if p.get('artid')]
    bad = [w for w in work if not 0 < w[1] <= ART_MAX]
    if bad:
        sys.exit(f'artid вне 1…{ART_MAX}: {bad[:5]}')
    t0 = time.time()
    result = []
    with ProcessPoolExecutor(max_workers=jobs) as pool:
        for i, r in enumerate(pool.map(build_one, work, chunksize=4)):
            result.append(r)
            if (i + 1) % 100 == 0:
                print(f'  {i + 1}/{len(work)} за {time.time() - t0:.0f} с', flush=True)
    by = {}
    for r in result:
        by.setdefault(r[3] if not r[3].startswith('ошибка') else 'ошибка', []).append(r)
    rows = {p['nhl_id']: p['row'] for p in players}
    json.dump([{'nhl_id': n, 'row': rows.get(n), 'artid': a, 'name': nm, 'status': st, 'files': fs}
               for n, a, nm, st, fs in result],
              open(os.path.join(OUT, 'photos.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('итого:', {k: len(v) for k, v in by.items()}, f'за {time.time() - t0:.0f} с →', OUT)
    for r in by.get('ошибка', [])[:10]:
        print('  ', r)


def cmd_db():
    from tdb import Tdb
    from tdb_read import load_meta
    db_in, db_out = sys.argv[2], sys.argv[3]
    meta = os.path.join(os.path.dirname(db_in), 'nhlng-meta.xml')
    db = Tdb(open(db_in, 'rb').read(), load_meta(meta))
    photos = json.load(open(os.path.join(OUT, 'photos.json'), encoding='utf-8'))
    # строки игроков — из write.json текущей папки конвейера (--work): после пересборки базы
    # строки могут быть другими, artid стабилен (artid-registry.json)
    rows = {p['nhl_id']: p['row'] for p in load('write.json')['players']}
    t = 'exhibitionplayerbiotable'
    on = skip = mism = 0
    for p in photos:
        row = rows.get(p['nhl_id'])
        if p['status'] != 'ok' or row is None:
            skip += 1
            continue
        if db.get(t, 'artid', row) != p['artid']:
            print(f"  строка {row} ({p['name']}): artid в базе {db.get(t, 'artid', row)}, у фото {p['artid']} — пропуск")
            mism += 1
            continue
        if db.get(t, 'hasportrait', row) != 1:
            db.set(t, 'hasportrait', row, 1)
        on += 1
    db.fix()
    assert not db.verify()
    open(db_out, 'wb').write(db.d)
    print(f'hasportrait = 1: {on}, без фото: {skip}, artid не совпал: {mism} → {db_out}')


def cmd_save():
    import shutil
    from tdb import SaveFile
    from tdb_read import load_meta
    d = os.path.normpath(sys.argv[2])
    fn = os.path.join(d, os.path.basename(d))
    if GAME.name == 'nhl13':
        meta = load_meta(os.path.join(ROOT, 'game', 'userdata', 'cache', 'guest', 'db', 'nhlng-meta.xml'))
        backups = os.path.join(ROOT, 'game', 'work', 'backup-saves')
    else:          # Legacy: схема — та, что ставится в cache: (game/work/legacy-data/out/db), сейв — ZlibV4
        out_meta = os.path.join(GAME.out, 'db', 'nhlng-meta.xml')
        meta = load_meta(out_meta if os.path.exists(out_meta) else GAME.meta)
        backups = os.path.join(GAME.work, 'backup-saves')
    backup_fn = os.path.join(backups, os.path.basename(d), os.path.basename(d))
    raw = open(backup_fn if os.path.exists(backup_fn) else fn, 'rb').read()
    sf = SaveFile(raw, meta)
    db = sf.db
    t = 'leagueplayerbiotable'
    # Ключ — artid и game_id игрока (write.json): франшиза сама выдаёт сгенерированным
    # игрокам (призывники, свободные агенты) номера фото из того же диапазона, что и новые
    # игроки конвейера, — им чужое лицо не ставим. Строки — только живые записи сейва
    # (tdb.Tdb.live_rows: [0, current) без удалённых; у удалённой прежние artid и game_id остаются).
    rows = {}
    for r in db.live_rows(t):
        rows.setdefault((db.get(t, 'artid', r), db.get(t, 'game_id', r)), []).append(r)
    # game_id в сейве — со сдвигом +1 (кодировка ссылок франшизы), в базе — как есть
    game_ids = {p['nhl_id']: p['game_id'] + 1 for p in load('write.json')['players'] if p.get('game_id') is not None}
    photos = json.load(open(os.path.join(OUT, 'photos.json'), encoding='utf-8'))
    on = missing = dup = 0
    for p in photos:
        if p['status'] != 'ok':
            continue
        hit = rows.get((p['artid'], game_ids.get(p['nhl_id'])), [])
        if not hit:
            missing += 1
            continue
        if len(hit) > 1:
            dup += 1
        for r in hit:
            if db.get(t, 'hasportrait', r) != 1:
                db.set(t, 'hasportrait', r, 1)
        on += 1
    out = sf.bytes()
    check = SaveFile(out, meta)
    assert not check.verify(), check.verify()
    backup = os.path.join(backups, os.path.basename(d))
    if not os.path.exists(backup):
        shutil.copytree(d, backup)
    open(fn, 'wb').write(out)
    print(f'{os.path.basename(d)}: hasportrait = 1 у {on} игроков (нет в сейве: {missing}, '
          f'повтор artid: {dup}); копия до правки — {backup}')


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else ''
    if cmd == 'fetch':
        cmd_fetch()
    elif cmd == 'build':
        cmd_build()
    elif cmd == 'db':
        cmd_db()
    elif cmd == 'save':
        cmd_save()
    else:
        sys.exit(__doc__)


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
