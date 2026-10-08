"""Фото игроков не из НХЛ (`python tools/roster photos`): портреты лиг → кадр портретов НХЛ → тот же
путь в игру, что у фото НХЛ (tools/photos.py build / db, docs/player-photos.md).

Источники (только GET, пауза ≥ 1 с на хост, кэш — game/work/roster-cache/photos/…):
- НХЛ: `assets.nhle.com/mugs/nhl/latest/<id>.png` — у игроков с ID НХЛ, у кого по адресу из
  карточки (сезон/клуб) фото нет (АХЛ, проспекты); PNG 336×336 на прозрачном фоне;
- Liiga (`--league liiga`): `pictureUrl` из состава liiga.fi — PNG 600×600 на прозрачном фоне
  (у 500 из 525 игроков); исходники — photos/liiga/<сезон>/<id Liiga>.png.
АХЛ, OHL/QMJHL/WHL (HockeyTech: картинки assets.leaguestat.com/<лига>/240x240/<id>.jpg, но ID игрока
— только через фид с ключом) и NL (данные сайта — за `Disallow: /api`) — не используются (описание —
docs/roster-expansion.md).

Кадр: у портретов разных лиг масштаб и поля разные. По альфа-каналу находятся макушка, «шея» (самая
узкая строка между головой и плечами) и центр головы; картинка масштабируется так, чтобы расстояние
«макушка — шея» и ширина головы были как у портретов НХЛ (среднее геометрическое двух масштабов; медианы —
по кэшу фото НХЛ), и кладётся в холст 336×336 с
макушкой и центром головы там же, где у НХЛ (playerhead.MUG_TOP, MUG_CX). Результат —
photos/20262027/<nhl_id>.png (там же, где фото НХЛ: tools/photos.py build берёт его как обычное), список
приведённых — photos/20262027/_other.json; лист «до/после» — photos-sheet.html в папке конвейера
(исходник, кадр НХЛ и сцена большого портрета игры, как её соберёт playerhead.compose).
Фото принадлежат лигам и клубам: только для личного использования, лежат в game/ (вне git).
"""
import html
import json
import os
import statistics
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

from .common import SEASON, TOOLS, UA, read_json, write_json

NHL_LATEST = 'https://assets.nhle.com/mugs/nhl/latest/{}.png'
PNG = b'\x89PNG\r\n\x1a\n'


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None                               # 302 на заглушку «нет фото» — не идём


def _ph():
    if TOOLS not in sys.path:
        sys.path.insert(0, TOOLS)
    import playerhead
    return playerhead


def photo_dir(game):
    return os.path.join(game, 'work', 'roster-cache', 'photos', str(SEASON))


class Getter:
    """GET картинок с кэшем: пауза ≥ 1 с на хост, редиректы не проходим (заглушка), 404 запоминается."""

    def __init__(self, pause=1.0, offline=False):
        self.pause, self.offline, self.last, self.requests = pause, offline, {}, 0
        self.opener = urllib.request.build_opener(_NoRedirect)

    def get(self, url, fn):
        if os.path.exists(fn):
            return True
        if os.path.exists(fn + '.none'):
            return False
        if self.offline:
            return False
        host = urllib.parse.urlsplit(url).hostname
        for attempt in range(5):
            wait = self.pause - (time.time() - self.last.get(host, 0))
            if wait > 0:
                time.sleep(wait)
            self.last[host] = time.time()
            try:
                with self.opener.open(urllib.request.Request(url, headers={'User-Agent': UA}), timeout=60) as r:
                    body = r.read()
                self.requests += 1
                if body[:8] != PNG:
                    raise ValueError('не PNG')
                os.makedirs(os.path.dirname(fn), exist_ok=True)
                with open(fn + '.part', 'wb') as f:
                    f.write(body)
                os.replace(fn + '.part', fn)
                return True
            except urllib.error.HTTPError as err:
                self.requests += 1
                if err.code in (301, 302, 303, 307, 308, 403, 404):
                    os.makedirs(os.path.dirname(fn), exist_ok=True)
                    open(fn + '.none', 'w').write(f'{err.code} {url}')
                    return False
                time.sleep(min(60, 5 * 2 ** attempt))
            except (urllib.error.URLError, OSError, ValueError):
                time.sleep(min(30, 3 * 2 ** attempt))
        return False


# --- кадр -----------------------------------------------------------------------------------------
def geometry(rgba, w, h, thr=128):
    """(макушка, шея, центр головы по x, ширина головы) по альфа-каналу портрета или None."""
    widths = []
    for y in range(h):
        row = [x for x in range(w) if rgba[(y * w + x) * 4 + 3] > thr]
        widths.append((row[0], row[-1]) if row else None)
    top = next((y for y, r in enumerate(widths) if r and r[1] - r[0] >= max(3, w // 60)), None)
    if top is None:
        return None
    wd = [(r[1] - r[0] + 1) if r else 0 for r in widths]
    # голова — до самой широкой строки в верхней трети ниже макушки; шея — самая узкая строка после неё,
    # пока ширина не вырастет вдвое против шеи (плечи)
    span = h - top
    head_rows = range(top, min(h, top + span // 3))
    head_w = max(wd[y] for y in head_rows)
    y_head = max(head_rows, key=lambda y: wd[y])
    neck, neck_w = None, None
    for y in range(y_head, h):
        if wd[y] == 0:
            continue
        if neck_w is None or wd[y] < neck_w:
            neck, neck_w = y, wd[y]
        elif wd[y] > 1.8 * neck_w and y > neck:
            break
    if neck is None or neck - top < span * 0.15:
        return None
    band = range(top, top + (neck - top) * 2 // 3)
    xs = [(widths[y][0] + widths[y][1]) / 2 for y in band if widths[y]]
    return top, neck, statistics.median(xs), head_w


def nhl_reference(game, sample=60):
    """Медианы геометрии портретов НХЛ из кэша: (макушка, «макушка — шея», центр x, ширина головы)."""
    cache = os.path.join(game, 'work', 'roster-cache', 'photos', 'nhl-geometry.json')
    ref = read_json(cache)
    if ref:
        return ref
    ph = _ph()
    d = photo_dir(game)
    files = sorted(f for f in os.listdir(d) if f.endswith('.png') and f[:-4].isdigit() and int(f[:-4]) < 10 ** 9)
    step = max(1, len(files) // sample)
    g = []
    for f in files[::step][:sample]:
        w, h, rgba = ph.png_read(os.path.join(d, f))
        r = geometry(rgba, w, h)
        if r and w == 336:
            g.append(r)
    ref = {'top': statistics.median(x[0] for x in g), 'height': statistics.median(x[1] - x[0] for x in g),
           'cx': statistics.median(x[2] for x in g), 'head_w': statistics.median(x[3] for x in g), 'n': len(g)}
    write_json(cache, ref)
    return ref


def to_nhl_frame(rgba, w, h, ref):
    """Портрет с прозрачным фоном → RGBA 336×336 в кадре НХЛ (или None, если геометрия не нашлась)."""
    ph = _ph()
    g = geometry(rgba, w, h)
    if not g:
        return None, None
    top, neck, cx, head_w = g
    # масштаб — среднее геометрическое двух мер: «макушка — шея» (у высокого воротника шея ниже) и ширина
    # головы (с волосами и ушами); у портретов НХЛ обе меры — медианы по кэшу
    scale = ((ref['height'] / float(neck - top)) * (ref['head_w'] / float(head_w))) ** 0.5
    img = ph.resample(rgba, w, h, 336, 336, scale, src0=(cx, float(top)), dst0=(ref['cx'], float(ref['top'])))
    return img, {'top': top, 'neck': neck, 'cx': round(cx, 1), 'head_w': head_w, 'scale': round(scale, 3)}


# --- этап -----------------------------------------------------------------------------------------
def run(paths, log=print, offline=False):
    """Фото для игроков players.json, у кого нет портрета НХЛ: NHL latest и портреты лиги → кадр НХЛ."""
    ph = _ph()
    data = read_json(paths.players)
    if not data:
        raise SystemExit('нет players.json — сначала build')
    game = paths.game
    d = photo_dir(game)
    os.makedirs(d, exist_ok=True)
    manifest_fn = os.path.join(d, '_other.json')
    manifest = read_json(manifest_fn, {}) or {}
    ref = nhl_reference(game)
    get = Getter(offline=offline)
    rows, counts = [], {}
    for k, p in enumerate(data['players']):
        pid = p['nhl_id']
        dst = os.path.join(d, f'{pid}.png')
        if os.path.exists(dst) and str(pid) not in manifest and pid < 10 ** 9:
            continue                                       # своё фото НХЛ уже есть (у ID 10⁹+ — только наши)
        known = manifest.get(str(pid))
        if known and os.path.exists(dst) and os.path.exists(os.path.join(game, *known['raw'].split('/'))):
            rows.append((p, os.path.join(game, *known['raw'].split('/')), dst))     # уже приведено раньше
            counts['приведено к кадру НХЛ'] = counts.get('приведено к кадру НХЛ', 0) + 1
            continue
        if k % 25 == 0:
            write_json(manifest_fn, dict(sorted(manifest.items(), key=lambda kv: int(kv[0]))))   # на случай обрыва
        src, raw = None, None
        if p.get('league') and p.get('photo'):
            raw = os.path.join(game, 'work', 'roster-cache', 'photos', p['league']['code'], str(SEASON % 10000),
                               f"{p['league']['id']}.png")
            src = p['photo'] if get.get(p['photo'], raw) else None
        elif pid < 10 ** 9 and not p.get('wiki_only'):
            raw = os.path.join(game, 'work', 'roster-cache', 'photos', 'nhl-latest', f'{pid}.png')
            src = NHL_LATEST.format(pid) if get.get(NHL_LATEST.format(pid), raw) else None
            if not src:
                old = os.path.join(game, 'work', 'roster-cache', 'photos', 'nhl-other', f'{pid}.png')
                if os.path.exists(old):                     # найдено раньше вручную по прошлым сезонам
                    raw, src = old, 'nhl-other'
        if not src:
            counts['нет фото'] = counts.get('нет фото', 0) + 1
            continue
        w, h, rgba = ph.png_read(raw)
        if src.startswith('https://assets.nhle.com') and w == 336:
            img, geo = rgba, {'scale': 1.0}                # уже кадр НХЛ
        else:
            img, geo = to_nhl_frame(rgba, w, h, ref)
        if img is None:
            counts['кадр не найден'] = counts.get('кадр не найден', 0) + 1
            continue
        ph.png_write(dst, 336, 336, img)
        manifest[str(pid)] = {'source': src, 'raw': os.path.relpath(raw, game).replace(os.sep, '/'), 'geometry': geo,
                              'name': f"{p['first']} {p['last']}", 'team': p['team']}
        rows.append((p, raw, dst))
        counts['приведено к кадру НХЛ'] = counts.get('приведено к кадру НХЛ', 0) + 1
    write_json(manifest_fn, dict(sorted(manifest.items(), key=lambda kv: int(kv[0]))))
    sheet_fn = os.path.join(paths.work, 'photos-sheet.html')
    sheet(sheet_fn, game, [(p, raw, dst) for p, raw, dst in rows], ref)
    log(f'photos: {counts}, запросов в сеть {get.requests} -> {d}; лист {sheet_fn}')
    return counts


def sheet(path, game, rows, ref, limit=80):
    """photos-sheet.html: исходник → кадр НХЛ → сцена большого портрета игры (как в игре); сцена
    собирается у первых `limit` (сборка — секунды на портрет), у остальных — исходник и кадр НХЛ."""
    ph = _ph()
    prev = os.path.join(game, 'work', 'roster-cache', 'photos', 'preview')
    os.makedirs(prev, exist_ok=True)
    base = os.path.dirname(os.path.abspath(path))
    rel = lambda p: os.path.relpath(p, base).replace(os.sep, '/')
    tmpl = ph.default_template('big')
    head = ph.PlayerHead.load(tmpl)
    cards = []
    for i, (p, raw, dst) in enumerate(rows):
        stage_fn = os.path.join(prev, f"{p['nhl_id']}_big.png")
        if i >= limit and not os.path.exists(stage_fn):
            cards.append(f'<div class="c"><img src="{html.escape(rel(raw))}" class="a" alt=""><img src="{html.escape(rel(dst))}" '
                         f'class="b" alt=""><div class="t"><b>{html.escape(p["first"] + " " + p["last"])}</b> '
                         f'<span>{html.escape(p["team"])}</span></div></div>')
            continue
        if not os.path.exists(stage_fn) or os.path.getmtime(stage_fn) < os.path.getmtime(dst):
            mug = ph.png_read(dst)
            t = head.tex
            img = ph.compose(mug, 'big', t.width, t.height, head.stage, False)
            sw, sh = head.stage
            ph.png_write(stage_fn, sw, sh, ph.crop(img, t.width, t.height, sw, sh))
        cards.append(f'<div class="c"><img src="{html.escape(rel(raw))}" class="a" alt=""><img src="{html.escape(rel(dst))}" '
                     f'class="b" alt=""><img src="{html.escape(rel(stage_fn))}" class="s" alt=""><div class="t"><b>'
                     f'{html.escape(p["first"] + " " + p["last"])}</b> <span>{html.escape(p["team"])}</span></div></div>')
    css = """:root{--bg:#f4f4f2;--fg:#1d1d1f;--card:#fff;--line:#d8d8d4;--mute:#6b6b70}
@media (prefers-color-scheme:dark){:root{--bg:#18181a;--fg:#ececee;--card:#232326;--line:#3a3a3e;--mute:#a0a0a8}}
body{background:var(--bg);color:var(--fg);font:14px/1.4 system-ui,sans-serif;margin:16px}
p{max-width:900px;color:var(--mute)} .g{display:grid;grid-template-columns:repeat(auto-fill,minmax(420px,1fr));gap:10px}
.c{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:8px;display:flex;gap:6px;flex-wrap:wrap}
.c img{background:repeating-conic-gradient(#bbb 0 25%,#ddd 0 50%) 0 0/16px 16px;border-radius:4px}
.a,.b{width:96px;height:96px;object-fit:contain} .s{width:200px;height:108px;object-fit:contain}
.t{width:100%;font-size:12px} .t span{color:var(--mute)}"""
    out = ['<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">',
           '<title>Фото не из НХЛ</title>', f'<style>{css}</style></head><body><h1>Фото не из НХЛ: до и после</h1>',
           f'<p>Слева — исходный портрет (лига), в середине — он же в кадре портретов НХЛ (336×336, макушка и центр '
           f'головы как у НХЛ: медианы по {ref.get("n")} фото), справа — сцена большого портрета игры (467×253), как её '
           f'соберёт tools/photos.py build. Клетка — прозрачный фон.</p><div class="g">', *cards, '</div></body></html>']
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        f.write('\n'.join(out))


# --- сборка в формат игры (в отдельную папку, не в photos-all) --------------------------------------
def _build_one(job):
    """(nhl_id, artid, png, out_root) → (nhl_id, artid, статус, файлы): оба размера p<artid>.big, как
    tools/photos.py build_one, но в свою папку."""
    nid, artid, png, root = job
    ph = _ph()
    try:
        mug = ph.png_read(png)
        files = []
        for kind in ('big', 'small'):
            orig = ph.original_path(kind, artid)
            template = orig if os.path.exists(orig) else ph.default_template(kind)
            head = ph.PlayerHead.load(template)
            t = head.tex
            rgba = ph.compose(mug, kind, t.width, t.height, head.stage, False)
            data = head.with_blocks(ph.dxt5_encode(rgba, t.width, t.height), None if template == orig else 'md5')
            rel = ph.asset_relpath(kind, artid)
            out = os.path.join(root, *rel.split('/'))
            os.makedirs(os.path.dirname(out), exist_ok=True)
            with open(out, 'wb') as f:
                f.write(data)
            files.append(rel)
        return nid, artid, 'ok', files
    except Exception as err:  # noqa: BLE001 — отчёт по игроку, остальные собираются
        return nid, artid, f'ошибка: {err}', []


def build(paths, log=print, jobs=6):
    """Приведённые фото игроков этой папки (write.json: artid) → game/work/photos-other/<папка>/fe/… (оба
    размера) и photos-other.json. В photos-all (её ставят install-*.sh) не пишет: artid новых игроков
    записаны в artid-registry.json этой папки, у другой папки они могут быть другими."""
    from concurrent.futures import ProcessPoolExecutor
    wr = read_json(paths.written)
    if not wr:
        raise SystemExit('нет write.json — сначала write')
    d = photo_dir(paths.game)
    manifest = read_json(os.path.join(d, '_other.json'), {}) or {}
    root = os.path.join(paths.game, 'work', 'photos-other', os.path.basename(os.path.normpath(paths.work)))
    work = [(o['nhl_id'], o['artid'], os.path.join(d, f"{o['nhl_id']}.png"), root) for o in wr['players']
            if str(o['nhl_id']) in manifest and o.get('artid') and os.path.exists(os.path.join(d, f"{o['nhl_id']}.png"))]
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=jobs) as pool:
        res = list(pool.map(_build_one, work, chunksize=4))
    write_json(os.path.join(root, 'photos-other.json'),
               [{'nhl_id': n, 'artid': a, 'status': st, 'files': fs} for n, a, st, fs in res])
    ok = sum(1 for r in res if r[2] == 'ok')
    log(f'photos: собрано {ok} из {len(work)} (оба размера) за {time.time() - t0:.0f} с -> {root}')
    return ok
