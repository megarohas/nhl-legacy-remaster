"""Игроки на фоне главного меню (фон NHL 12, перенесённый в NHL 13): список → готовые файлы.

Фон главного меню NHL 12 (game.background.NHLMainMenuBackground) по кругу показывает случайного игрока
из списка m_backgroundPlayers (29 мест, ASSET_ID 0, 2…29) и, если включены легенды, — из
m_backgroundLegends (7). Картинка места N — artAssets/backgrounds/mainMenuPlayers/nhl<N> (кадр 600×760 в
текстуре DXT5 1024×1024) и её «размытая» копия mainMenuPlayersBlur/nhl<N>; кольца света красятся в
PRIMARY_COLOUR места. Инструмент собирает эти файлы из фото игроков (вырезка фона — rembg) и правит цвета
колец в байткоде фона (PushLong, на месте). Подробности — docs/fe-menu.md.

    python menuplayers.py slots [--bg FILE]                 # места фона: ASSET_ID, цвет колец, анимация
    python menuplayers.py plan SPEC.json [--top 21] [--must ID,ID…] [--players players.json]
        # список: обязательные (по умолчанию — Кучеров, Макдэвид, Маккиннон, Квинн и Джек Хьюзы, Макар,
        # Шестёркин, Василевский) + лучшие по рейтингу базы; клуб и цвет — из базы. Правится руками.
    python menuplayers.py scout SPEC.json [--slots …] [--max 60] [--skip-done]
        # кандидаты фото: кэш конвейера, players/src/<id>/, категории Commons, картинки статей NHL.com с тегом
        # игрока → быстрая вырезка и оценка → лист players/scout/<место>_<id>.jpg и scout/<id>.json
    python menuplayers.py try SPEC.json --slot N --cand 0,5,7   # примерка кандидатов «на экране меню»
    python menuplayers.py pick SPEC.json [--slots …]        # автоматический выбор (ручной — "photo_locked")
    python menuplayers.py cut SPEC.json                     # вырезка фона (rembg) → кэш players/cut/
    python menuplayers.py build SPEC.json OUTDIR [--only N,…] [--no-names] [--no-legends]
        # раскладка cache: fe/ion/artassets/backgrounds/mainmenuplayers(blur)/nhl<N>.big, легенды с фамилиями,
        # фон NHL 12 с цветами колец и правками проезда; OUTDIR/_preview — кадры и вид «на экране»
    python menuplayers.py screens OUTDIR [--out JPG]        # лист «на экране меню» (видимые обрезы — пурпурным)
    python menuplayers.py sheet OUTDIR [--out PNG]          # контактный лист собранного (как в игре: на арене)

Поля игрока в SPEC.json: slot (ASSET_ID), nhl_id, name, team (аббревиатура НХЛ), photo ("auto" или путь),
focus [x0, y0, x1, y1] (участок фото с нужным игроком — до вырезки), flip (отразить), fit (auto или
{"scale": к, "x": центр, "bottom": низ} в пикселях кадра 600×760), tone (сила обработки 0…1), color
("auto" — по клубу из базы, или RRGGBB). Фото: game/work/menu12/players/src/<nhl_id>/* (свои/скачанные),
иначе экшн-кадр НХЛ из кэша конвейера (roster-cache/photos/action/<nhl_id>.jpg).

Нужны Pillow, numpy, scipy и rembg (onnxruntime) — venv game/work/menu12/venv (pip install "rembg[cpu]").
Фото и собранные картинки — только для личного использования: в git их нет (всё в game/).
"""
import glob, json, os, struct, sys

TOOLS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TOOLS)
import playerhead as ph   # noqa: E402  (BIGF, RefPack, XPR2)
import febg               # noqa: E402  (FeMovie, Texture, build_bigf)
import feapt              # noqa: E402  (байткод фона)

GAME = ph.game_dir()
WORK = os.path.join(GAME, 'work', 'menu12', 'players')
BG_REL = 'fe/ion/game/background/nhlmainmenubackground.big'
PLAYERS_REL = 'fe/ion/artassets/backgrounds/mainmenuplayers/nhl{}.big'
BLUR_REL = 'fe/ion/artassets/backgrounds/mainmenuplayersblur/nhl{}.big'
# шаблоны: файлы места 8 NHL 12 (один кадр 600×760 в текстуре 1024×1024 + частицы льда)
TEMPLATE = os.path.join(GAME, 'other', 'nhl12', 'big', 'cache', *PLAYERS_REL.format(8).split('/'))
TEMPLATE_BLUR = os.path.join(GAME, 'other', 'nhl12', 'big', 'cache', *BLUR_REL.format(8).split('/'))
# фон главного меню NHL 12 (её cache.big): места, цвета колец, типы анимации; правку порядка событий
# фреймворка NHL 13 делает tools/menu12.py build
DEFAULT_BG = os.path.join(GAME, 'other', 'nhl12', 'big', 'cache', *BG_REL.split('/'))
FRAME_W, FRAME_H = 600, 760
MUST = [8476453, 8478402, 8477492, 8480800, 8481559, 8480069, 8478048, 8476883]


# ---------------------------------------------------------------- места фона (байткод)

def slots_of(bg_path):
    """Места m_backgroundPlayers / m_backgroundLegends: [{list, asset, color, color_off, anim1, anim2}].
    Объект места в байткоде: PushConstant имя, значение … (4 пары), PushByte 4, InitObject; список —
    PushConstant "m_backgroundPlayers", объекты, PushByte N, InitArray, SetMember."""
    mv, consts = feapt.load_movie(bg_path)
    code = feapt.Code(mv.apt.data, consts)
    out = []
    for title, off in feapt.code_blocks(mv):
        if 'NHLMainMenuBackground»' not in title or '__Packages' not in title:
            continue
        ins = code.parse(off)
        cur = None
        pending = []
        for k, i in enumerate(ins):
            if i.name in ('PushConstant', 'PushWordConstant') and i.args[0] in ('m_backgroundPlayers', 'm_backgroundLegends'):
                cur, pending = i.args[0], []
                continue
            if cur is None:
                continue
            if i.name == 'InitArray':
                cur, pending = None, []
                continue
            pending.append(i)
            if i.name == 'InitObject':
                obj, j = {}, 0
                seq = pending[:-2]                       # без счётчика пар и InitObject
                while j + 1 < len(seq):
                    key, val = seq[j], seq[j + 1]
                    if key.name in ('PushConstant', 'PushWordConstant'):
                        obj[key.args[0]] = val
                    j += 2
                v = lambda x: (x.args[0] if x.args else {'PushZero': 0, 'PushOne': 1, 'PushTrue': True,
                                                          'PushFalse': False}.get(x.name))
                c = obj.get('PRIMARY_COLOUR')
                an = obj.get('ANIM_TYPE_1')
                out.append(dict(list=cur, asset=v(obj['ASSET_ID']), legend='LEGEND' in obj,
                                anim1_ins=(an.name, an.off) if an is not None else None,
                                color=v(c) if c is not None else None,
                                color_off=c.off if c is not None and c.name == 'PushLong' else None,
                                anim1=v(obj['ANIM_TYPE_1']) if 'ANIM_TYPE_1' in obj else None,
                                anim2=v(obj['ANIM_TYPE_2']) if 'ANIM_TYPE_2' in obj else None))
                pending = []
    return out


def cmd_slots(args):
    bg = opt(args, '--bg', DEFAULT_BG if os.path.exists(DEFAULT_BG) else
             os.path.join(GAME, 'other', 'nhl12', 'big', 'cache', *BG_REL.split('/')))
    for s in slots_of(bg):
        print(f"{s['list']:21s} ASSET_ID {s['asset']:2d}  цвет #{s['color']:06X}  анимация {s['anim1']}/{s['anim2']}"
              f"  (PushLong @{s['color_off']:#x})")


# ---------------------------------------------------------------- игроки и клубы

def load_players(path=None):
    path = path or os.path.join(GAME, 'work', 'roster-expanded-ahl32', 'players.json')
    return {p['nhl_id']: p for p in json.load(open(path, encoding='utf-8'))['players']}


def team_colors(db_path=None):
    """Аббревиатура НХЛ → (основной, второй) цвет клуба из установленной базы (exhibitionteams)."""
    from tdb import SaveFile
    from tdb_read import load_meta
    sys.path.insert(0, os.path.join(TOOLS, 'roster'))
    from roster.common import TEAM_SLOT
    db_path = db_path or os.path.join(GAME, 'userdata', 'cache', 'guest', 'db', 'nhlng.db')
    meta = os.path.join(os.path.dirname(db_path), 'nhlng-meta.xml')
    db = SaveFile(open(db_path, 'rb').read(), load_meta(meta)).db
    t = 'exhibitionteams'
    out = {}
    for abbr, row in TEAM_SLOT.items():
        g = lambda f: db.get(t, f, row)
        out[abbr] = ((g('primarycolor_r') << 16) | (g('primarycolor_g') << 8) | g('primarycolor_b'),
                     (g('secondarycolor_r') << 16) | (g('secondarycolor_g') << 8) | g('secondarycolor_b'))
    return out


def ring_color(primary, secondary):
    """Цвет колец: основной цвет клуба; если он слишком тёмный или серый (на чёрной арене не виден) —
    второй, если тот ярче; затем светлота не ниже 0,42 (HLS)."""
    import colorsys

    def hls(c):
        return colorsys.rgb_to_hls(((c >> 16) & 255) / 255, ((c >> 8) & 255) / 255, (c & 255) / 255)
    h, l, s = hls(primary)
    h2, l2, s2 = hls(secondary)
    if (l < 0.22 or s < 0.15) and s2 >= 0.3 and l2 > l:
        h, l, s = h2, l2, s2
    l = max(l, 0.42)
    r, g, b = colorsys.hls_to_rgb(h, l, s)
    return (round(r * 255) << 16) | (round(g * 255) << 8) | round(b * 255)


def cmd_plan(args):
    out = args[0]
    players = load_players(opt(args, '--players'))
    top = int(opt(args, '--top', '21'))
    must = [int(x) for x in opt(args, '--must', ','.join(map(str, MUST))).split(',') if x]
    colors = team_colors()
    rated = sorted((p for p in players.values() if p.get('ea') and p['ea'].get('ovr') and not p.get('omitted')
                    and p['nhl_id'] not in must), key=lambda p: (-p['ea']['ovr'], p['last']))
    chosen = [players[i] for i in must] + rated[:top]
    bg = DEFAULT_BG if os.path.exists(DEFAULT_BG) else os.path.join(GAME, 'other', 'nhl12', 'big', 'cache', *BG_REL.split('/'))
    slots = [s['asset'] for s in slots_of(bg) if s['list'] == 'm_backgroundPlayers']
    if len(chosen) > len(slots):
        sys.exit(f'игроков {len(chosen)}, мест {len(slots)}')
    spec = {'background': os.path.relpath(bg, GAME).replace('\\', '/'), 'players': []}
    for slot, p in zip(sorted(slots), chosen):
        pc, sc = colors.get(p['team'], (0xFFFFFF, 0xFFFFFF))
        spec['players'].append({'slot': slot, 'nhl_id': p['nhl_id'], 'name': f"{p['first']} {p['last']}",
                                'team': p['team'], 'pos': p['pos'], 'ovr': p['ea']['ovr'], 'photo': 'auto',
                                'focus': None, 'flip': False, 'fit': 'auto', 'tone': 1.0, 'color': 'auto',
                                'team_colors': [f'{pc:06X}', f'{sc:06X}'], 'ring': f'{ring_color(pc, sc):06X}'})
    json.dump(spec, open(out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    for e in spec['players']:
        print(f"место {e['slot']:2d}: {e['name']:24s} {e['team']} {e['pos']} {e['ovr']}  кольца #{e['ring']}")
    print(f'→ {out}')


# ---------------------------------------------------------------- фото и вырезка

def photo_candidates(nhl_id):
    own = sorted(glob.glob(os.path.join(WORK, 'src', str(nhl_id), '*')))
    action = os.path.join(GAME, 'work', 'roster-cache', 'photos', 'action', f'{nhl_id}.jpg')
    return own + ([action] if os.path.exists(action) else [])


def photo_of(e):
    if e.get('photo') and e['photo'] != 'auto':
        p = e['photo'] if os.path.isabs(e['photo']) else os.path.join(GAME, e['photo'])
        return p
    c = photo_candidates(e['nhl_id'])
    if not c:
        raise SystemExit(f"нет фото для {e['name']} ({e['nhl_id']})")
    return c[0]


_SESSIONS = {}
SCOUT_MODEL = 'isnet-general-use'        # быстрая (~1 с) — для оценки кандидатов по превью
CUT_MODEL = 'birefnet-general'           # точная (~25 с на CPU) — для окончательной вырезки: не берёт сетку
                                         # ворот, буквы рекламы и борта, которые isnet цепляет у вратарей


def session(model=SCOUT_MODEL):
    if model not in _SESSIONS:
        os.environ.setdefault('U2NET_HOME', os.path.join(GAME, 'work', 'menu12', 'models'))
        from rembg import new_session
        _SESSIONS[model] = new_session(model)
    return _SESSIONS[model]


def cut_model(e):
    return e.get('model') or CUT_MODEL


def cut_path(e):
    src = photo_of(e)
    tag = os.path.splitext(os.path.basename(src))[0]
    f = e.get('focus')
    if f:
        tag += '_' + '_'.join(str(int(v)) for v in f)
    m = cut_model(e)
    if m != SCOUT_MODEL:
        tag += '__' + m
    return os.path.join(WORK, 'cut', f"{e['nhl_id']}__{tag}.png")


def cutout(e, force=False):
    """RGBA вырезка (кэш): фото (или его участок focus) → rembg → оставить главный силуэт."""
    from PIL import Image
    import numpy as np
    out = cut_path(e)
    if os.path.exists(out) and not force:
        return Image.open(out).convert('RGBA')
    from rembg import remove
    im = Image.open(photo_of(e)).convert('RGB')
    if e.get('focus'):
        im = im.crop(tuple(int(v) for v in e['focus']))
    if max(im.size) > 2000:                                    # модели работают в 1024 — больше не нужно
        im.thumbnail((2000, 2000), Image.LANCZOS)
    rgba = remove(im, session=session(cut_model(e)))
    a = np.array(rgba)
    a[..., 3] = main_component(a[..., 3])
    res = Image.fromarray(a, 'RGBA')
    os.makedirs(os.path.dirname(out), exist_ok=True)
    res.save(out)
    return res


def main_component(alpha):
    """Оставить самый крупный силуэт (и всё, что касается его в радиусе 12 px: клюшка, перчатка) —
    чужие игроки, судьи и куски борта на фото отдельными пятнами уходят."""
    import numpy as np
    from scipy import ndimage
    m = alpha > 96
    lab, n = ndimage.label(m)
    if n <= 1:
        return alpha
    sizes = ndimage.sum(m, lab, range(1, n + 1))
    main = lab == (1 + int(np.argmax(sizes)))
    near = ndimage.binary_dilation(main, iterations=12)
    keep_labels = set(np.unique(lab[near & m])) - {0}
    keep = np.isin(lab, list(keep_labels))
    keep = ndimage.binary_dilation(keep, iterations=3)          # мягкий край вокруг — из исходной альфы
    return np.where(keep, alpha, 0).astype(alpha.dtype)


def cmd_cut(args):
    spec = json.load(open(args[0], encoding='utf-8'))
    for e in spec['players']:
        p = cut_path(e)
        cutout(e, force='--force' in args)
        print(f"{e['name']:24s} ← {os.path.relpath(photo_of(e), GAME)} → {os.path.relpath(p, GAME)}")


# ---------------------------------------------------------------- поиск фото (Commons + экшн-кадры)

COMMONS = 'https://commons.wikimedia.org/w/api.php'
UA = {'User-Agent': 'megarohas-nhl13-personal/1.0 (local game mod; personal use)'}


def http_json(params):
    import urllib.parse, urllib.request
    url = COMMONS + '?' + urllib.parse.urlencode(dict(params, format='json'))
    return json.load(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60))


def http_get(url, dst):
    import urllib.request
    if not os.path.exists(dst):
        data = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120).read()
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        open(dst, 'wb').write(data)
    return dst


def commons_category_files(name, depth=1):
    """Файлы категорий «Имя Фамилия», «… (ice hockey)» и их подкатегорий (на depth уровней)."""
    seen, files = set(), []
    todo = [(f'Category:{name}', 0), (f'Category:{name} (ice hockey)', 0)]
    while todo:
        cat, lvl = todo.pop()
        if cat in seen:
            continue
        seen.add(cat)
        cont = {}
        while True:
            d = http_json(dict({'action': 'query', 'list': 'categorymembers', 'cmtitle': cat, 'cmlimit': 500,
                                'cmtype': 'file|subcat'}, **cont))
            for m in d.get('query', {}).get('categorymembers', []):
                if m['ns'] == 14 and lvl < depth:
                    todo.append((m['title'], lvl + 1))
                elif m['ns'] == 6 and m['title'].lower().endswith(('.jpg', '.jpeg', '.png')):
                    files.append(m['title'])
            if 'continue' not in d:
                break
            cont = d['continue']
    return list(dict.fromkeys(files))


def commons_info(titles, thumb=640):
    out = {}
    for i in range(0, len(titles), 40):
        d = http_json({'action': 'query', 'titles': '|'.join(titles[i:i + 40]), 'prop': 'imageinfo',
                       'iiprop': 'url|size|extmetadata', 'iiurlwidth': thumb})
        for pg in d['query']['pages'].values():
            if 'imageinfo' not in pg:
                continue
            ii = pg['imageinfo'][0]
            md = ii.get('extmetadata', {})
            out[pg['title']] = {'url': ii['url'], 'thumb': ii.get('thumburl'), 'w': ii['width'], 'h': ii['height'],
                                'license': md.get('LicenseShortName', {}).get('value', ''),
                                'date': (md.get('DateTimeOriginal', {}).get('value') or '')[:10]}
    return out


FORGE = 'https://forge-dapi.d3.nhle.com/v2/content/en-us/stories'
NHL_IMG = 'https://media.d3.nhle.com/image/private/{fmt}/{path}'
BROWSER_UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
                            'Chrome/140.0 Safari/537.36'}


def forge_images(nhl_id, limit=120):
    """Картинки статей NHL.com с тегом игрока (API Forge): [(путь картинки, заголовок, дата)]. Путь —
    «v…/prd/<id>» в CDN media.d3.nhle.com: превью — t_ratio16_9-size40 (832×468), оригинал — t_q-best."""
    import urllib.request
    out, seen, skip = [], set(), 0
    while skip < limit:
        url = f'{FORGE}?tags.slug=playerid-{nhl_id}&$limit=40&$skip={skip}'
        d = json.load(urllib.request.urlopen(urllib.request.Request(url, headers=BROWSER_UA), timeout=60))
        items = d.get('items', [])
        for it in items:
            th = it.get('thumbnail') or {}
            tu = th.get('templateUrl') or ''
            if '{formatInstructions}/' not in tu:
                continue
            path = tu.split('{formatInstructions}/', 1)[1]
            if path in seen:
                continue
            seen.add(path)
            out.append((path, it.get('title', ''), (it.get('contentDate') or it.get('date') or '')[:10]))
        if len(items) < 40:
            break
        skip += 40
    return out


def evaluate(img):
    """Быстрая оценка кандидата по превью: вырезка, главный силуэт, его рамка, обрезы краем фото,
    доля «чужих» пятен. → dict."""
    import numpy as np
    from rembg import remove
    from scipy import ndimage
    rgba = np.array(remove(img.convert('RGB'), session=session()))
    al = rgba[..., 3]
    m = al > 128
    lab, n = ndimage.label(m)
    if n == 0:
        return {'ok': False}
    sizes = ndimage.sum(m, lab, range(1, n + 1))
    k = int(np.argmax(sizes))
    others = float(sizes.sum() - sizes[k]) / float(sizes[k])
    keep = main_component(al)
    _, sides = source_cuts(keep)
    ys, xs = np.nonzero(keep > 128)
    H, W = m.shape
    rgba[..., 3] = keep
    return {'ok': True, 'bbox': [int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1],
            'fig_h': (int(ys.max()) - int(ys.min())) / H, 'fig_w': (int(xs.max()) - int(xs.min())) / W,
            'others': round(others, 3), 'cuts': [k2 for k2, v in sides.items() if v], 'rgba': rgba}


def cmd_scout(args):
    """Кандидаты фото по местам spec: экшн-кадр НХЛ, свои src/<id>/*, категории Commons → вырезка по превью,
    оценка и лист сравнения players/scout/<место>_<id>.jpg (+ scout/<id>.json с адресами)."""
    from PIL import Image, ImageDraw, ImageFont
    spec = json.load(open(args[0], encoding='utf-8'))
    only = opt(args, '--slots')
    only = {int(x) for x in only.split(',')} if only else None
    ids = opt(args, '--ids')
    ids = {int(x) for x in ids.split(',')} if ids else None
    mx = int(opt(args, '--max', '40'))
    font = ImageFont.truetype('C:/Windows/Fonts/segoeui.ttf', 13)
    for e in spec['players']:
        if (only and e['slot'] not in only) or (ids and e['nhl_id'] not in ids):
            continue
        sd = os.path.join(WORK, 'scout', str(e['nhl_id']))
        if '--skip-done' in args and os.path.exists(os.path.join(WORK, 'scout', f"{e['nhl_id']}.json")):
            continue
        os.makedirs(sd, exist_ok=True)
        cands = [{'src': p, 'title': os.path.basename(p), 'w': None, 'h': None, 'date': '', 'license': 'local'}
                 for p in photo_candidates(e['nhl_id'])]
        names = [e['name']] + list(e.get('commons_names', []))
        files = []
        for nm in names:
            try:
                files += commons_category_files(nm)
            except Exception as ex:                                     # noqa: BLE001
                print('  commons:', ex)
        info = commons_info(files) if files else {}
        import hashlib
        jobs = []
        if '--no-forge' not in args:
            try:
                for path, title, date in forge_images(e['nhl_id']):
                    fn = os.path.join(sd, 'nhl', hashlib.md5(path.encode()).hexdigest()[:12] + '.jpg')
                    jobs.append((NHL_IMG.format(fmt='t_ratio16_9-size40', path=path), fn, BROWSER_UA,
                                 {'src': fn, 'title': 'NHL: ' + title, 'url': NHL_IMG.format(fmt='t_q-best', path=path),
                                  'w': None, 'h': None, 'date': date, 'license': 'nhl.com (личное)', 'nhl_path': path}))
            except Exception as ex:                                     # noqa: BLE001
                print('  forge:', ex)
        for t, v in info.items():
            if max(v['w'], v['h']) < 900 or not v.get('thumb'):
                continue
            fn = os.path.join(sd, 'thumbs', hashlib.md5(t.encode('utf-8')).hexdigest()[:12] + '.jpg')
            jobs.append((v['thumb'], fn, UA, {'src': fn, 'title': t, 'url': v['url'], 'w': v['w'], 'h': v['h'],
                                              'date': v['date'], 'license': v['license']}))
        # NHL.com (свежие статьи — нынешняя форма) — вперёд, Commons — после; всего не больше --max
        jobs.sort(key=lambda j: 0 if j[3].get('nhl_path') else 1)
        jobs = jobs[:mx]

        def fetch(job):
            import urllib.request
            url, fn, hdr, c = job
            try:
                if not os.path.exists(fn):
                    data = urllib.request.urlopen(urllib.request.Request(url, headers=hdr), timeout=60).read()
                    os.makedirs(os.path.dirname(fn), exist_ok=True)
                    open(fn, 'wb').write(data)
                return c
            except Exception as ex:                                     # noqa: BLE001
                print('  превью:', url[:90], ex)
                return None
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(8) as pool:
            cands += [c for c in pool.map(fetch, jobs) if c]
        rows = []
        for c in cands:
            try:
                im = Image.open(c['src']).convert('RGB')
            except Exception:                                           # noqa: BLE001
                continue
            orig_h = c['h'] or (im.size[1] * 3.0 if c.get('nhl_path') else im.size[1])
            if max(im.size) > 900:
                im.thumbnail((900, 900))
            ev = evaluate(im)
            if not ev.get('ok'):
                continue
            full_h = orig_h * ev['fig_h']
            bad_cut = [k for k in ev['cuts'] if k in ('left', 'top')]
            score = min(full_h, 1000) / 10 - 40 * len(bad_cut) - 8 * ('right' in ev['cuts']) - 60 * min(ev['others'], 1)
            c.update({'fig_px': round(full_h), 'cuts': ev['cuts'], 'others': ev['others'], 'score': round(score, 1),
                      'bbox': ev['bbox'], 'thumb_size': list(im.size)})
            rows.append((c, im, ev['rgba']))
        rows.sort(key=lambda r: -r[0]['score'])
        json.dump([r[0] for r in rows], open(os.path.join(WORK, 'scout', f"{e['nhl_id']}.json"), 'w', encoding='utf-8'),
                  ensure_ascii=False, indent=1)
        # лист: пары «фото | вырезка», по 4 пары в ряд
        TW, TH = 240, 170
        cols = 4
        nrow = (len(rows) + cols - 1) // cols
        sheet = Image.new('RGB', (cols * TW * 2, max(1, nrow) * (TH + 36) + 28), (16, 16, 20))
        d = ImageDraw.Draw(sheet)
        d.text((6, 6), f"место {e['slot']}: {e['name']} {e['team']} — кандидатов {len(rows)}", fill=(255, 220, 120), font=font)
        for k, (c, im, rgba) in enumerate(rows):
            x, y = (k % cols) * TW * 2, 28 + (k // cols) * (TH + 36)
            a = im.copy()
            a.thumbnail((TW - 4, TH - 4))
            sheet.paste(a, (x + 2, y + 2))
            cut = Image.fromarray(rgba, 'RGBA')
            cut.thumbnail((TW - 4, TH - 4))
            bgc = Image.new('RGBA', cut.size, (32, 36, 46, 255))
            bgc.alpha_composite(cut)
            sheet.paste(bgc.convert('RGB'), (x + TW + 2, y + 2))
            col = (255, 120, 120) if any(q in ('left', 'top') for q in c['cuts']) else (200, 200, 200)
            d.text((x + 2, y + TH + 1), f"#{k} {c['score']} фиг.{c['fig_px']}px обрез:{','.join(c['cuts']) or '-'} чуж:{c['others']}",
                   fill=col, font=font)
            ttl = c['title'][5:60] if c['title'].startswith('File:') else c['title'][:60]
            d.text((x + 2, y + TH + 17), f"{c['date']} {ttl}", fill=(150, 150, 150), font=font)
        out = os.path.join(WORK, 'scout', f"{e['slot']:02d}_{e['nhl_id']}.jpg")
        sheet.save(out, quality=85)
        print(f"место {e['slot']:2d} {e['name']:24s} кандидатов {len(rows):3d} → {os.path.relpath(out, GAME)}", flush=True)


_NUMS = None


def number_label(nhl_id):
    """«№30 G» — номер и амплуа из players.json конвейера (для сверки: на фото из статей NHL.com бывает
    другой игрок той же команды)."""
    global _NUMS
    if _NUMS is None:
        try:
            _NUMS = {i: (p.get('num'), p.get('pos')) for i, p in load_players().items()}
        except Exception:                                           # noqa: BLE001
            _NUMS = {}
    num, pos = _NUMS.get(int(nhl_id), (None, None))
    return f'№{num} {pos}' if num is not None else ''


def fetch_original(c, nhl_id):
    """Оригинал кандидата scout в players/src/<id>/ (кэш): NHL.com — t_q-best, Commons — url."""
    import hashlib
    if c.get('license') == 'local' or not c.get('url'):
        return c['src']
    ext = '.jpg' if not c['url'].lower().split('?')[0].endswith('.png') else '.png'
    key = c.get('nhl_path') or c['url']
    dst = os.path.join(WORK, 'src', str(nhl_id), ('nhl_' if c.get('nhl_path') else 'commons_')
                       + hashlib.md5(key.encode()).hexdigest()[:12] + ext)
    if not os.path.exists(dst):
        import urllib.request
        hdr = BROWSER_UA if c.get('nhl_path') else UA
        data = urllib.request.urlopen(urllib.request.Request(c['url'], headers=hdr), timeout=180).read()
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        open(dst, 'wb').write(data)
    return dst


def thumb_body_aspect(c):
    """Ширина/высота «тела» силуэта на превью кандидата (вырезка кэшируется рядом с превью): у одного игрока
    ≈ 0,4…1,1, у пары/группы — больше."""
    import numpy as np
    from PIL import Image
    cp = os.path.splitext(c['src'])[0] + '.cut.png'
    if os.path.exists(cp):
        al = np.asarray(Image.open(cp))[..., 3]
    else:
        im = Image.open(c['src']).convert('RGB')
        im.thumbnail((900, 900))
        ev = evaluate(im)
        if not ev.get('ok'):
            return 99.0
        Image.fromarray(ev['rgba'], 'RGBA').save(cp)
        al = ev['rgba'][..., 3]
    x0, y0, x1, y1 = body_box(al)
    return (x1 - x0) / max(1, y1 - y0)


def auto_pick(cands, year_from=None, max_aspect=1.15):
    """Лучший кандидат scout по правилам отбора: один игрок (чужих силуэтов < 3 %, «тело» не шире 1,15 своей
    высоты — не пара и не группа), без обрезов краем фото слева и сверху, фигура не мелкая (оценка по
    оригиналу ≥ 800 px), предпочтение — NHL.com (свежие статьи — нынешняя форма) и крупная фигура.
    → (индекс, кандидат) или None."""
    ranked = []
    for k, c in enumerate(cands):
        if c.get('others', 1) > 0.03 or any(x in ('left', 'top') for x in c.get('cuts', [])):
            continue
        if c.get('fig_px', 0) < 800:
            continue
        bx0, by0, bx1, by1 = c['bbox']
        hw = (by1 - by0) / max(1, bx1 - bx0)
        if not 0.6 <= hw <= 3.0:
            continue
        if year_from and c.get('date') and c['date'][:4].isdigit() and int(c['date'][:4]) < year_from:
            continue
        score = min(c['fig_px'], 1400) / 14 + (25 if c.get('nhl_path') else 0) - (10 if 'right' in c.get('cuts', []) else 0)
        score += 0.5 * (int(c['date'][:4]) - 2020) if c.get('date', '')[:4].isdigit() else 0
        ranked.append((score, k, c))
    ranked.sort(key=lambda r: -r[0])
    for score, k, c in ranked[:12]:
        if thumb_body_aspect(c) <= max_aspect:
            return k, c
    return None


def cmd_pick(args):
    """pick SPEC.json [--slots …] [--year-from 2024]: фото по местам — лучший кандидат scout (auto_pick),
    скачивается оригинал; spec обновляется (photo, focus = null). Места с ручным выбором ("photo_locked": true)
    не трогаются."""
    spec = json.load(open(args[0], encoding='utf-8'))
    only = opt(args, '--slots')
    only = {int(x) for x in only.split(',')} if only else None
    yf = opt(args, '--year-from')
    for e in spec['players']:
        if (only and e['slot'] not in only) or e.get('photo_locked'):
            continue
        jp = os.path.join(WORK, 'scout', f"{e['nhl_id']}.json")
        if not os.path.exists(jp):
            print(f"место {e['slot']:2d} {e['name']}: нет scout")
            continue
        cands = json.load(open(jp, encoding='utf-8'))
        r = auto_pick(cands, int(yf) if yf else e.get('year_from'))
        if not r:
            print(f"место {e['slot']:2d} {e['name']}: подходящего кандидата нет — фото прежнее")
            continue
        k, c = r
        src = fetch_original(c, e['nhl_id'])
        e['photo'] = os.path.relpath(src, GAME).replace('\\', '/')
        e['focus'] = None
        e['pick'] = {'cand': k, 'title': c.get('title', ''), 'date': c.get('date', ''), 'fig_px': c.get('fig_px')}
        print(f"место {e['slot']:2d} {e['name']:24s} ← #{k} {c.get('date', '')} {c.get('title', '')[:60]}")
    json.dump(spec, open(args[0], 'w', encoding='utf-8'), ensure_ascii=False, indent=1)


def cmd_try(args):
    """Примерка кандидатов scout на место: оригинал → вырезка → кадр → фамилия → лист «на экране меню».
    try SPEC.json --slot N --cand 0,5,7 [--focus i:x0,y0,x1,y1] — индексы — из листа scout."""
    from PIL import Image, ImageDraw, ImageFont
    spec = json.load(open(args[0], encoding='utf-8'))
    slot = int(opt(args, '--slot'))
    e = next(x for x in spec['players'] if x['slot'] == slot)
    cands = json.load(open(os.path.join(WORK, 'scout', f"{e['nhl_id']}.json"), encoding='utf-8'))
    idx = [int(x) for x in opt(args, '--cand').split(',')]
    focus = {}
    for f in [a for a in args if a.startswith('--focus=')]:
        k, box = f[8:].split(':')
        focus[int(k)] = [int(v) for v in box.split(',')]
    anim = slot_anims(DEFAULT_BG).get(slot, 2)
    font = ImageFont.truetype('C:/Windows/Fonts/segoeui.ttf', 18)
    tiles = []
    for i in idx:
        c = cands[i]
        src = fetch_original(c, e['nhl_id'])
        e2 = dict(e, photo=src, focus=focus.get(i))
        cut = cutout(e2)
        player, sc, bad = compose(cut, e2, anim)
        player = tone(player, e.get('tone', 1.0))
        frame = with_name(player, e2)
        scr = screen_preview(frame, bad, anim, 1.0).convert('RGB')
        scr0 = screen_preview(frame, bad, anim, 0.0).convert('RGB')
        both = Image.new('RGB', (1280, 720 * 2 + 30), (10, 10, 12))
        both.paste(scr0, (0, 0))
        both.paste(scr, (0, 750))
        d = ImageDraw.Draw(both)
        d.text((8, 723), f"#{i} [{e['name']} {number_label(e['nhl_id'])}] {os.path.basename(src)}  {Image.open(src).size}  масштаб ×{sc:.2f}  "
                         f"обрезы на экране: {int(bad.sum())} px  ({c.get('date', '')} {c.get('title', '')[:70]})",
                fill=(255, 220, 120) if not bad.any() else (255, 120, 255), font=font)
        tiles.append(both.resize((640, 375)))
        print(f"#{i}: {os.path.relpath(src, GAME)} → обрезы {int(bad.sum())} px, масштаб ×{sc:.2f}", flush=True)
    cols = 3
    sheet = Image.new('RGB', (640 * cols, 375 * ((len(tiles) + cols - 1) // cols)), (0, 0, 0))
    for k, t in enumerate(tiles):
        sheet.paste(t, ((k % cols) * 640, (k // cols) * 375))
    out = os.path.join(WORK, 'scout', f"try_{slot:02d}_{e['nhl_id']}.jpg")
    sheet.save(out, quality=88)
    print(out)


# ---------------------------------------------------------------- компоновка и тон

def body_box(alpha):
    """Рамка «тела» без тонкой клюшки: строки и столбцы, где силуэт шире/выше 6 % его размера."""
    import numpy as np
    m = alpha > 128
    ys, xs = np.nonzero(m)
    if not len(xs):
        return 0, 0, alpha.shape[1], alpha.shape[0]
    full = (xs.min(), ys.min(), xs.max() + 1, ys.max() + 1)
    rows, cols = m.sum(1), m.sum(0)
    ry = np.nonzero(rows > 0.06 * (full[2] - full[0]))[0]
    cx = np.nonzero(cols > 0.06 * (full[3] - full[1]))[0]
    return int(cx.min()), int(ry.min()), int(cx.max()) + 1, int(ry.max()) + 1


def full_box(alpha, thr=40):
    import numpy as np
    ys, xs = np.nonzero(alpha > thr)
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def source_cuts(alpha, edge=2, thr=128):
    """Где силуэт упирается в край фото (или участка focus): маска «обрезанных» пикселей и стороны."""
    import numpy as np
    m = alpha > thr
    cut = np.zeros_like(m)
    cut[:edge, :] = m[:edge, :]
    cut[-edge:, :] |= m[-edge:, :]
    cut[:, :edge] |= m[:, :edge]
    cut[:, -edge:] |= m[:, -edge:]
    sides = {'left': bool(m[:, :edge].any()), 'top': bool(m[:edge, :].any()),
             'right': bool(m[:, -edge:].any()), 'bottom': bool(m[-edge:, :].any())}
    # мелочь (пара пикселей шума у края) не считается
    for k, sl in (('left', m[:, :edge]), ('top', m[:edge, :]), ('right', m[:, -edge:]), ('bottom', m[-edge:, :])):
        if sl.sum() < 6:
            sides[k] = False
    return cut, sides


# Положение кадра на экране 1280×720 (по Apt фона NHL 12): картинка игрока стоит в (684, 6) ролика,
# ролик — в mcPlayerHolder.ph.cPlayer (сдвиги < 1 px); держатель по типу анимации ANIM_TYPE_1 едет за
# 30 с из начального положения в конечное: (x, y, масштаб).
ANIM_PATH = {0: ((0, 0, 1.0), (120, 0, 1.0)), 1: ((100, 0, 1.0), (0, 0, 1.0)), 2: ((130, 50, 0.9), (40, 0, 1.0)),
             3: ((100, 50, 0.9), (-150, 0, 1.0))}
FRAME_POS = (684.0, 6.0)
# к концу проезда типа 2 на экране остаётся левая часть кадра шириной ~416 px — тело ставится левее
BODY_CX = 215
POS2_END = 40
POS2_START = 130
# что закрывает картинку в главном меню (по снимку 1600×900 → 1280×720): строка помощи и бегущая строка
# внизу (панель Features tools/menu12.py переносит вверх влево, левее кадра)
OCCLUDERS = [(0, 605, 1280, 720)]


def screen_rect(anim, t):
    """Кадр на экране в момент t (0 — начало проезда, 1 — конец): (x0, y0, масштаб)."""
    (x0, y0, s0), (x1, y1, s1) = ANIM_PATH.get(anim, ((0, 50, 0.9), (0, 0, 1.0)))
    hx, hy, hs = x0 + (x1 - x0) * t, y0 + (y1 - y0) * t, s0 + (s1 - s0) * t
    return hx + hs * FRAME_POS[0], hy + hs * FRAME_POS[1], hs


def visible_mask(anim, times=(0.0, 0.5, 1.0)):
    """Пиксели кадра 600×760, которые хоть в какой-то момент проезда видны на экране и не закрыты
    интерфейсом."""
    import numpy as np
    vis = np.zeros((FRAME_H, FRAME_W), bool)
    fy, fx = np.mgrid[0:FRAME_H, 0:FRAME_W]
    for t in times:
        X0, Y0, sc = screen_rect(anim, t)
        X, Y = X0 + fx * sc, Y0 + fy * sc
        v = (X >= 0) & (X < 1280) & (Y >= 0) & (Y < 720)
        for (a, b, c, d) in OCCLUDERS:
            v &= ~((X >= a) & (X < c) & (Y >= b) & (Y < d))
        vis |= v
    return vis


# видимая ширина кадра (px кадра) в худший момент проезда: тип 0 — в конце (x 804), тип 1 — в начале
# (x 784), тип 2 — в конце (x 724)
VIS_END = {0: 476, 1: 496, 2: 556}
VISIBLE_ROWS = 604                         # ниже этой строки кадра — полосы внизу экрана (при любом проезде)


def core_box(alpha):
    """«Ядро» силуэта — туловище и ноги без вытянутых рук и клюшки: столбцы, где силуэт выше 30 % своей
    высоты."""
    import numpy as np
    m = alpha > 128
    ys, xs = np.nonzero(m)
    if not len(xs):
        return 0, 0, alpha.shape[1], alpha.shape[0]
    h = ys.max() - ys.min() + 1
    cols = np.nonzero(m.sum(0) > 0.30 * h)[0]
    if not len(cols):
        return body_box(alpha)
    rows = np.nonzero(m[:, cols.min():cols.max() + 1].any(1))[0]
    return int(cols.min()), int(rows.min()), int(cols.max()) + 1, int(rows.max()) + 1


def compose(cut, e, anim=2):
    """Вырезка → кадр 600×760 и маска «плохих» обрезов (видимых на экране).

    Как у NHL 12: игрок во весь рост кадра. Левый и верхний края кадра на экране видны всегда — силуэт
    (с клюшкой) их не касается; правый и нижний — за краем экрана (у анимаций 0–2), туда можно уводить
    срезанное: если игрок срезан на фото снизу или справа, этот край фото ставится на край кадра."""
    import numpy as np
    from PIL import Image
    if e.get('flip'):
        cut = cut.transpose(Image.FLIP_LEFT_RIGHT)
    a = np.array(cut)
    alpha = a[..., 3]
    x0, y0, x1, y1 = body_box(alpha)
    fx0, fy0, fx1, fy1 = full_box(alpha)
    bw, bh = x1 - x0, y1 - y0
    cutmask, sides = source_cuts(alpha)
    SW, SH = cut.size
    fit = e.get('fit') or 'auto'
    M = 10                                                     # поле у видимых краёв кадра
    c0, _, c1, _ = core_box(alpha)
    cw, ccx = c1 - c0, (c0 + c1) / 2
    # голова: середина верхних 10 % силуэта (у наклонившегося игрока — сбоку от «ядра»)
    m128 = alpha > 128
    ys_, xs_ = np.nonzero(m128)
    top = ys_.min()
    sel = ys_ < top + 0.10 * (ys_.max() - top + 1)
    hx = float(xs_[sel].mean()) if sel.any() else ccx
    vis = VIS_END.get(anim, 556)
    rows_any = alpha > 40

    def left_visible(s, oy):
        """Левый край силуэта среди строк, видимых на экране (ниже y ≈ 600 кадра — полосы помощи и
        бегущей строки): клюшка или перчатка внизу может уходить за левый край кадра незаметно."""
        cutoff = int(max(0, min(SH, (VISIBLE_ROWS - oy) / s)))
        if cutoff <= 0:
            return SW
        cols = np.nonzero(rows_any[:cutoff].any(0))[0]
        return int(cols.min()) if len(cols) else SW

    if fit == 'auto':
        # по высоте тела (~724 px; по пояс — 700); «ядро» (туловище и ноги, без рук и клюшки) — не шире
        # видимой в худший момент проезда части кадра и с центром на 42 % её ширины; за край экрана может
        # уходить до 35 % ядра (обрез краем экрана допустим), голова — видна с запасом
        s = min((700 if sides['bottom'] else 724) / bh, 0.95 * vis / max(1, cw))
        for _ in range(60):
            oy = (FRAME_H - SH * s) if sides['bottom'] else (748 - y1 * s)
            ox = 0.42 * vis - ccx * s
            ox = max(ox, M - left_visible(s, oy) * s)
            if sides['right']:                                 # срез справа — уводим за правый край кадра
                ox = max(ox, FRAME_W - SW * s)
            top_ok = fy0 * s + oy >= M
            core_right = c1 * s + ox                           # правый край ядра — в видимой части
            head_ok = hx * s + ox <= vis - 80                  # голова — в видимой части с запасом
            if top_ok and head_ok and core_right <= vis + 0.35 * cw * s:
                break
            s *= 0.97
    else:
        s = fit['scale']
        ox = fit.get('x', BODY_CX) - (x0 + bw / 2) * s
        oy = (FRAME_H - SH * s) if fit.get('bottom') == 'cut' else fit.get('bottom', 748) - y1 * s
    ox, oy = round(ox), round(oy)
    W, H = max(1, round(SW * s)), max(1, round(SH * s))
    big = cut.resize((W, H), Image.LANCZOS)
    frame = Image.new('RGBA', (FRAME_W, FRAME_H), (0, 0, 0, 0))
    frame.paste(big, (ox, oy), big)                            # кадр пустой — вставка с маской = наложение
    # обрезы: края фото, попавшие внутрь кадра, + касание краёв кадра
    cm = Image.fromarray((cutmask * 255).astype(np.uint8)).resize((W, H), Image.NEAREST)
    cmf = Image.new('L', (FRAME_W, FRAME_H), 0)
    cmf.paste(cm, (ox, oy))
    bad = np.asarray(cmf) > 0
    fa = np.asarray(frame)[..., 3] > 128
    border = np.zeros_like(fa)
    border[:2, :] = fa[:2, :]
    border[-2:, :] |= fa[-2:, :]
    border[:, :2] |= fa[:, :2]
    border[:, -2:] |= fa[:, -2:]
    bad = (bad | border) & visible_mask(anim)
    return frame, s, bad


def tone(frame, k=1.0):
    """Под тёмную арену NHL 12 (сверено с её картинками: средняя яркость силуэта 0,26–0,55, свет сверху,
    низ темнее): локальный контраст, экспозиция ×0,86, S-кривая (тени глубже, светлые ≤ 0,94),
    насыщенность ×0,85, к низу кадра темнее до −22 %, холодные тени. k — сила (0 — без обработки)."""
    import numpy as np
    from PIL import Image, ImageFilter
    if k <= 0:
        return frame
    a = np.asarray(frame).astype(np.float32) / 255
    rgb, al = a[..., :3], a[..., 3:4]
    blur = np.asarray(frame.convert('RGB').filter(ImageFilter.GaussianBlur(18))).astype(np.float32) / 255
    x = np.clip(rgb + 0.35 * (rgb - blur), 0, 1)
    x = x * (1 - 0.14 * k)
    sc = np.where(x < 0.42, 0.42 * (x / 0.42) ** 1.35, 1 - 0.58 * ((1 - x) / 0.58) ** 1.1)
    x = np.clip(x + k * (sc - x), 0, 0.94)
    lum = (0.299 * x[..., 0] + 0.587 * x[..., 1] + 0.114 * x[..., 2])[..., None]
    x = lum + (1 - 0.15 * k) * (x - lum)
    yy = np.linspace(0, 1, x.shape[0], dtype=np.float32)[:, None, None]
    x = x * (1 + k * (0.04 - 0.26 * yy ** 1.3))
    shadow = np.clip(1 - lum / 0.5, 0, 1)
    x = x + k * shadow * np.array([-0.012, 0.0, 0.03], np.float32)
    out = np.concatenate([np.clip(x, 0, 1), al], axis=2)
    return Image.fromarray((out * 255 + 0.5).astype(np.uint8), 'RGBA')


def streaks(frame):
    """«Размытая» копия как у NHL 12: светлые горизонтальные шлейфы от силуэта + чёткий игрок поверх."""
    import numpy as np
    from PIL import Image
    a = np.asarray(frame).astype(np.float32) / 255
    rgb, al = a[..., :3], a[..., 3]
    pm = rgb * al[..., None]
    light = (0.45 * pm + 0.55 * al[..., None])                 # к белому, предумноженное
    acc_c = np.zeros_like(light)
    acc_a = np.zeros_like(al)
    wsum = 0.0
    L = 90
    for d in range(-L, L + 1, 3):
        w = (1 - abs(d) / (L + 1)) ** 2
        acc_c += w * np.roll(light, d, axis=1)
        acc_a += w * np.roll(al, d, axis=1)
        wsum += w
    acc_c /= wsum
    acc_a = np.clip(acc_a / wsum * 0.85, 0, 1)
    # чёткий игрок поверх шлейфа (предумноженное «над»)
    out_a = al + acc_a * (1 - al)
    out_c = pm + acc_c * 0.85 * (1 - al)[..., None]
    rgb2 = np.where(out_a[..., None] > 1e-4, out_c / np.maximum(out_a[..., None], 1e-4), 0)
    res = np.concatenate([np.clip(rgb2, 0, 1), out_a[..., None]], axis=2)
    return Image.fromarray((res * 255 + 0.5).astype(np.uint8), 'RGBA')


# ---------------------------------------------------------------- фамилия в кадре

NAME_FONT = os.path.join(GAME, 'other', 'nhl12', 'big', 'cache', 'fe', 'ion', 'fonts', 'eahelveticaneuehv-mod.ttf')


def surname(e):
    if e.get('label'):
        return e['label']
    parts = e['name'].split()
    last = ' '.join(parts[1:]) if len(parts) > 1 else parts[0]
    return last.upper()


def render_name(text, max_w=360, max_cap=84, shear=0.21):
    """Фамилия «металлом», как mainMenuPlayerNames (остатки NHL 11 в архивах NHL 12): шрифт пунктов меню
    NHL 12 («EA HelveticaNeue Hv» из её cache.big — DIN), наклон, градиент, царапины, отражение. → RGBA."""
    import numpy as np
    from PIL import Image, ImageDraw, ImageFont, ImageFilter
    size = 200
    for _ in range(30):
        f = ImageFont.truetype(NAME_FONT, size)
        x0, y0, x1, y1 = f.getbbox(text)
        cap = f.getbbox('H')[3] - f.getbbox('H')[1]
        track = round(size * 0.04)
        w = (x1 - x0) + track * (len(text) - 1) + cap * shear
        if w <= max_w and cap <= max_cap:
            break
        size = int(size * min(max_w / w, max_cap / cap, 0.97))
    W, H = int(w) + 8, int((y1 - y0) * 1.7) + 8
    mask = Image.new('L', (W, H), 0)
    d = ImageDraw.Draw(mask)
    x = 4 + cap * shear
    for ch in text:                                            # разрядка вручную
        d.text((x - x0, 4 - y0), ch, font=f, fill=255)
        x += f.getlength(ch) + track
    # наклон: x' = x + shear·(базовая − y)
    base = 4 + (f.getbbox('H')[3] - y0)
    mask = mask.transform(mask.size, Image.AFFINE, (1, shear, -shear * base, 0, 1, 0), Image.BICUBIC)
    m = np.asarray(mask).astype(np.float32) / 255
    hgt = base - 4
    yy = np.arange(H, dtype=np.float32)[:, None]
    t = np.clip((yy - 4) / max(1, hgt), 0, 1)
    metal = 0.95 - 0.38 * t + 0.08 * np.exp(-((t - 0.18) / 0.08) ** 2)          # блик под верхом
    rng = np.random.default_rng(len(text) * 7919)
    scratches = np.zeros((H, W), np.float32)
    for _ in range(int(W * H / 900)):
        cx, cy, ln = rng.integers(0, W), rng.integers(0, H), rng.integers(6, 40)
        ang = rng.normal(-0.15, 0.25)
        for k in range(ln):
            px, py = int(cx + k * np.cos(ang)), int(cy + k * np.sin(ang))
            if 0 <= px < W and 0 <= py < H:
                scratches[py, px] = rng.uniform(0.15, 0.45)
    lum = np.clip(metal + scratches - 0.06 * rng.random((H, W)), 0, 1)
    rgb = np.stack([lum * 0.97, lum * 0.99, lum * 1.03], 2)
    # отражение: перевёрнутая нижняя часть с затуханием
    refl = np.zeros_like(m)
    span = H - int(base) - 2
    if span > 4:
        flip = m[int(base) - span:int(base)][::-1]
        fade = np.linspace(0.32, 0.0, span, dtype=np.float32)[:, None]
        refl[int(base) + 2:int(base) + 2 + span] = flip * fade
    alpha = np.clip(m + refl * (1 - m), 0, 1)
    out = np.concatenate([np.clip(rgb, 0, 1), alpha[..., None]], 2)
    img = Image.fromarray((out * 255 + 0.5).astype(np.uint8), 'RGBA')
    return img.filter(ImageFilter.SMOOTH_MORE) if False else img


# фамилия — правее панели «NHL 13 Features» (она вверху слева, до x ≈ 742 экрана; кадр — с 684)
NAME_X_MIN = 74


def best_name_pos(fig_alpha, name_alpha, xs=(NAME_X_MIN, NAME_X_MIN + 30, NAME_X_MIN + 60), ys=range(36, 268, 8),
                  origin=(0, 0)):
    """Где фамилия меньше всего закрыта силуэтом: перебор положений (x, y) в координатах кадра/сцены;
    fig_alpha — альфа силуэта (H×W, 0…1) с началом в origin. Предпочтение — выше и левее."""
    import numpy as np
    nh, nw = name_alpha.shape
    tot = float(name_alpha.sum()) or 1.0
    best = None
    for y in ys:
        for x in xs:
            fx, fy = x - origin[0], y - origin[1]
            region = np.zeros_like(name_alpha)
            y0, x0 = max(0, fy), max(0, fx)
            y1, x1 = min(fig_alpha.shape[0], fy + nh), min(fig_alpha.shape[1], fx + nw)
            if y1 > y0 and x1 > x0:
                region[y0 - fy:y1 - fy, x0 - fx:x1 - fx] = fig_alpha[y0:y1, x0:x1]
            cover = float((region * name_alpha).sum()) / tot
            score = cover + 0.0012 * (y - ys[0]) + 0.0005 * (x - xs[0])
            if best is None or score < best[0]:
                best = (score, x, y, cover)
    return best[1], best[2], best[3]


def with_name(frame, e, opacity=0.62, pos=None, player=None):
    """Фамилия позади игрока: слой имени (полупрозрачный), сверху — игрок. Место — где её меньше всего
    закрывает силуэт (best_name_pos по силуэту player или самого кадра), если не задано pos/e['name_pos']."""
    from PIL import Image
    import numpy as np
    name = render_name(surname(e))
    a = np.asarray(name).astype(np.float32)
    if pos is None:
        pos = e.get('name_pos')
    if pos is None:
        fig = np.asarray(player or frame)[..., 3].astype(np.float32) / 255
        x, y, cover = best_name_pos(fig, a[..., 3] / 255)
        pos = (x, y)
    a[..., 3] *= opacity
    name = Image.fromarray(a.astype(np.uint8), 'RGBA')
    base = Image.new('RGBA', (FRAME_W, FRAME_H), (0, 0, 0, 0))
    base.alpha_composite(name, (int(pos[0]), int(pos[1])))
    base.alpha_composite(frame)
    return base


# ---------------------------------------------------------------- лист «на экране меню»

# снимок главного меню с фоном NHL 12 без игрока (сборка с пустыми картинками игроков), панель Features наверху
BACKDROP = os.path.join(GAME, 'work', 'menu12', 'test', 'backdrop-nhl12-menu.png')


def screen_preview(frame, bad, anim, t=1.0, backdrop=None):
    """Кадр на снимке главного меню (1280×720) в положении проезда t; плохие обрезы — пурпурным."""
    import numpy as np
    from PIL import Image
    bd = Image.open(backdrop or BACKDROP).convert('RGBA').resize((1280, 720), Image.LANCZOS)
    X0, Y0, sc = screen_rect(anim, t)
    f = frame.resize((round(FRAME_W * sc), round(FRAME_H * sc)), Image.LANCZOS)
    layer = Image.new('RGBA', (1280, 720), (0, 0, 0, 0))
    layer.paste(f, (round(X0), round(Y0)), f)
    # интерфейс поверх (панель Features и нижние полосы — с исходного снимка)
    out = bd.copy()
    out.alpha_composite(layer)
    bdn = np.asarray(bd)
    o = np.array(out)
    for (a, b, c, d) in OCCLUDERS:
        o[b:d, a:c] = bdn[b:d, a:c]
    if bad is not None and bad.any():
        bm = Image.fromarray((bad * 255).astype(np.uint8)).resize(f.size, Image.NEAREST)
        bml = Image.new('L', (1280, 720), 0)
        bml.paste(bm, (round(X0), round(Y0)))
        m = np.asarray(bml) > 0
        from scipy import ndimage
        m = ndimage.binary_dilation(m, iterations=3)
        o[m] = (255, 0, 255, 255)
    return Image.fromarray(o, 'RGBA')


# ---------------------------------------------------------------- сборка .big

def texture_entry(mv):
    """Запись BIGF с самой большой текстурой (картинка игрока) и её Texture."""
    best = max(mv.textures.values(), key=lambda t: t.fetch.width * t.fetch.height)
    return best


def pack(template, frame, dst):
    """Шаблон .big (NHL 12) + новый кадр 600×760 → .big: только текстура, всё остальное — как в шаблоне."""
    import numpy as np
    mv = febg.FeMovie.load(template)
    t = texture_entry(mv)
    w, h = t.fetch.width, t.fetch.height
    canvas = np.zeros((h, w, 4), np.uint8)
    f = np.asarray(frame)
    canvas[:FRAME_H, :FRAME_W] = f
    canvas[..., :3] = np.where(canvas[..., 3:4] > 0, canvas[..., :3], 0)    # под прозрачным — чёрный
    xpr = t.encode(canvas.tobytes())
    big = ph.Bigf(mv.big.raw)
    big.put(t.name, ph.refpack_compress(xpr) if mv.raw[t.name][1] else xpr)
    data = febg.build_bigf(big)
    febg.FeMovie(data)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    open(dst, 'wb').write(data)
    return len(data)


LEGENDS_REL = 'fe/ion/artassets/backgrounds/mainmenulegends/nhl{}.big'
LEGENDS_BLUR_REL = 'fe/ion/artassets/backgrounds/mainmenulegendsblur/nhl{}.big'
# легенды NHL 12 (m_backgroundLegends, ASSET_ID 0…6): картинки остаются её, добавляется фамилия
LEGENDS = {0: 'GRETZKY', 1: 'YZERMAN', 2: 'ROY', 3: 'BOURQUE', 4: 'HOWE', 5: 'LEMIEUX', 6: 'ROENICK'}
NAME_STAGE = (FRAME_POS[0] + 14, FRAME_POS[1] + 58)          # где фамилия игрока на сцене ролика картинки


def image_placement(mv):
    """Ролик картинки (mainMenuPlayers/Legends…): (Texture, Shape, сдвиг tx, ty спрайта на сцене) — самая
    большая текстура, её фигура и положение спрайта с ней в корне ролика (масштаб 1)."""
    t = texture_entry(mv)
    img_idx = next(i for i, x in mv.textures.items() if x is t)
    shape = next(ch for ch in mv.apt.chars if ch.type == 1 and ch.image == img_idx)
    holder = next(ch for ch in mv.apt.chars if ch.type == 5 and any(
        it.po and it.po.char == shape.idx for fr in ch.frames for it in fr))
    root = mv.apt.chars[0]
    for it in root.frames[0]:
        if it.po and it.po.char == holder.idx:
            a, b, c, d, tx, ty = it.po.matrix
            return t, shape, (tx, ty)
    raise ValueError('спрайт картинки не найден в корне ролика')


def name_into_movie(src, dst, label, behind=True, opacity=0.62, pos=None):
    """Фамилия в текстуру готового ролика картинки (легенды NHL 12): на сцене — там же, где у наших игроков
    (NAME_STAGE), позади силуэта. Текстура в фигуре — 1:1 от её левого верхнего угла (матрица единичная)."""
    import numpy as np
    from PIL import Image
    mv = febg.FeMovie.load(src)
    t, shape, (tx, ty) = image_placement(mv)
    w, h = t.fetch.width, t.fetch.height
    img = Image.frombytes('RGBA', (w, h), t.decode())
    name = render_name(label)
    a = np.asarray(name).astype(np.float32)
    if pos is None:
        fig = np.asarray(img)[..., 3].astype(np.float32) / 255
        sx, sy, _ = best_name_pos(fig, a[..., 3] / 255, xs=tuple(range(int(FRAME_POS[0]) - 120, int(FRAME_POS[0]) + 90, 30)),
                                  ys=range(40, 268, 8), origin=(round(tx), round(ty)))
        pos = (sx, sy)
    a[..., 3] *= opacity
    name = Image.fromarray(a.astype(np.uint8), 'RGBA')
    x, y = round(pos[0] - tx), round(pos[1] - ty)
    layer = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    layer.alpha_composite(name, (max(0, x), max(0, y)))
    if behind:
        layer.alpha_composite(img)
        out = layer
    else:
        out = img.copy()
        out.alpha_composite(layer)
    arr = np.array(out)
    bw, bh = int(round(shape.bounds[2])), int(round(shape.bounds[3]))
    arr[bh:, :, :] = 0                                           # за пределами фигуры — пусто
    arr[:, bw:, :] = 0
    arr[..., :3] = np.where(arr[..., 3:4] > 0, arr[..., :3], 0)
    xpr = t.encode(arr.tobytes())
    big = ph.Bigf(mv.big.raw)
    big.put(t.name, ph.refpack_compress(xpr) if mv.raw[t.name][1] else xpr)
    data = febg.build_bigf(big)
    febg.FeMovie(data)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    open(dst, 'wb').write(data)
    return len(data)


def legend_name_pos(src, label):
    import numpy as np
    from PIL import Image
    mv = febg.FeMovie.load(src)
    t, shape, (tx, ty) = image_placement(mv)
    img = Image.frombytes('RGBA', (t.fetch.width, t.fetch.height), t.decode())
    a = np.asarray(render_name(label))[..., 3].astype(np.float32) / 255
    fig = np.asarray(img)[..., 3].astype(np.float32) / 255
    lo = max(int(FRAME_POS[0]) + NAME_X_MIN, round(tx) + 4)                # правее панели Features, в картинке
    hi = min(int(FRAME_POS[0]) + 90, round(tx) + int(shape.bounds[2]) - a.shape[1] - 4)
    xs = tuple(range(lo, max(lo, hi) + 1, 30))
    ys = range(max(40, round(ty) + 4), 268, 8)
    x, y, _ = best_name_pos(fig, a, xs=xs, ys=ys, origin=(round(tx), round(ty)))
    return x, y


def build_legends(outdir, labels=None, log=print):
    labels = labels or LEGENDS
    base = os.path.join(GAME, 'other', 'nhl12', 'big', 'cache')
    for k, label in sorted(labels.items()):
        src = os.path.join(base, *LEGENDS_REL.format(k).split('/'))
        pos = legend_name_pos(src, label)
        n1 = name_into_movie(src, os.path.join(outdir, *LEGENDS_REL.format(k).split('/')), label, pos=pos)
        n2 = name_into_movie(os.path.join(base, *LEGENDS_BLUR_REL.format(k).split('/')),
                             os.path.join(outdir, *LEGENDS_BLUR_REL.format(k).split('/')), label, pos=pos)
        log(f'легенда {k}: {label} ({n1} + {n2} байт)')


def patch_background(bg_src, bg_dst, colors, anim3_to=1):
    """Фон: цвета колец мест (PushLong на месте) и тип анимации 3 → anim3_to (PushByte 3 → PushByte 1):
    при типе 3 держатель уезжает влево до x = −150, и правый край кадра выходит на экран; тип 1 — въезд
    влево из x = 100 в 0, правый край кадра всё время за экраном."""
    edits = []
    for s in slots_of(bg_src):
        if s['list'] != 'm_backgroundPlayers':
            continue
        if s['asset'] in colors and s['color_off'] is not None:
            old = struct.pack('>I', s['color'] & 0xFFFFFFFF)
            new = struct.pack('>I', colors[s['asset']])
            if old != new:
                edits.append((s['color_off'] + 1, old, new))
        if anim3_to is not None and s['anim1'] == 3 and s['anim1_ins'] and s['anim1_ins'][0] == 'PushByte':
            edits.append((s['anim1_ins'][1], bytes([0xB5, 3]), bytes([0xB5, anim3_to])))
    # тип 2: держатель едет из x = 100 в POS_NEXT = 180 — к концу на экране остаётся левая треть кадра;
    # 180 → POS2_END (почти на месте, только приближение 90 → 100 %)
    mv, consts = feapt.load_movie(bg_src)
    code = feapt.Code(mv.apt.data, consts)
    for title, off in feapt.code_blocks(mv):
        if '__Packages' not in title:
            continue
        flat = []

        def walk(lst):
            for i in lst:
                flat.append(i)
                if i.body:
                    walk(i.body)
        walk(code.parse(off))
        for k, i in enumerate(flat[:-1]):
            if i.name == 'PushConstant' and i.args[0] == 'POS_NEXT' and flat[k + 1].name == 'PushShort'                     and flat[k + 1].args[0] == 180:
                edits.append((flat[k + 1].off + 1, struct.pack('>H', 180), struct.pack('>H', POS2_END)))
                # начало типа 2: x = 100 при масштабе 90 % — правый край кадра на 1256, виден; → POS2_START
                for j in range(k - 1, max(0, k - 30), -1):
                    if flat[j].name == 'PushConstant' and flat[j].args[0] == '_x' and flat[j + 1].name == 'PushByte'                             and flat[j + 1].args[0] == 100:
                        edits.append((flat[j + 1].off + 1, bytes([100]), bytes([POS2_START])))
                        break
    feapt.patch_bytes(bg_src, bg_dst, edits, log=lambda *a: None)
    return len(edits)


def slot_anims(bg, anim3_to=1):
    return {s['asset']: (anim3_to if (s['anim1'] == 3 and anim3_to is not None) else s['anim1'])
            for s in slots_of(bg) if s['list'] == 'm_backgroundPlayers'}


def cmd_build(args):
    spec_path, outdir = args[0], args[1]
    spec = json.load(open(spec_path, encoding='utf-8'))
    bg = spec.get('background') or DEFAULT_BG
    bg = bg if os.path.isabs(bg) else os.path.join(GAME, bg)
    colors = team_colors()
    anims = slot_anims(bg)
    prev = os.path.join(outdir, '_preview')
    os.makedirs(prev, exist_ok=True)
    ring = {}
    report = []
    only = opt(args, '--only')
    only = {int(x) for x in only.split(',')} if only else None
    names = '--no-names' not in args
    import numpy as np
    for e in spec['players']:
        if only and e['slot'] not in only:
            continue
        anim = anims.get(e['slot'], 2)
        cut = cutout(e)
        player, s, bad = compose(cut, e, anim)
        player = tone(player, e.get('tone', 1.0))
        if names:
            import numpy as np
            nm = np.asarray(render_name(surname(e)))[..., 3].astype(np.float32) / 255
            nx, ny, _ = best_name_pos(np.asarray(player)[..., 3].astype(np.float32) / 255, nm)
            e = dict(e, name_pos=e.get('name_pos') or (nx, ny))
        frame = with_name(player, e) if names else player
        blur = streaks(player)
        blur = with_name(blur, e) if names else blur
        tag = f"{e['slot']:02d}_{e['nhl_id']}"
        frame.save(os.path.join(prev, tag + '.png'))
        np.save(os.path.join(prev, tag + '_bad.npy'), bad)
        screen_preview(frame, bad, anim, 1.0).convert('RGB').save(os.path.join(prev, tag + '_screen.jpg'), quality=88)
        n1 = pack(TEMPLATE, frame, os.path.join(outdir, *PLAYERS_REL.format(e['slot']).split('/')))
        n2 = pack(TEMPLATE_BLUR, blur, os.path.join(outdir, *BLUR_REL.format(e['slot']).split('/')))
        if e.get('color', 'auto') == 'auto':
            pc, sc = colors.get(e['team'], (0xFFFFFF, 0xFFFFFF))
            c = ring_color(pc, sc)
        else:
            c = int(e['color'], 16)
        ring[e['slot']] = c
        flag = f'  ОБРЕЗЫ НА ЭКРАНЕ: {int(bad.sum())} px' if bad.any() else ''
        report.append(f"место {e['slot']:2d}: {e['name']:24s} {e['team']}  анимация {anim}  масштаб ×{s:.2f}  "
                      f"кольца #{c:06X}  ({n1} + {n2} байт){flag}")
        print(report[-1], flush=True)
    if not only and names and '--no-legends' not in args:
        build_legends(outdir, {int(k): v for k, v in spec.get('legends', {}).items()} or None)
    if not only:
        n = patch_background(bg, os.path.join(outdir, *BG_REL.split('/')), ring)
        print(f'фон: {n} правок (цвета колец, анимация 3 → 1) → {os.path.join(outdir, *BG_REL.split("/"))}')
        open(os.path.join(outdir, 'menuplayers-build.txt'), 'w', encoding='utf-8').write('\n'.join(report) + '\n')


# ---------------------------------------------------------------- контактный лист

def arena_backdrop(w, h):
    """Тёмная «арена» для листа: градиент, как фон NHL 12 за игроком."""
    import numpy as np
    from PIL import Image
    y = np.linspace(0, 1, h)[:, None]
    x = np.linspace(-1, 1, w)[None, :]
    v = 0.05 + 0.10 * np.exp(-((x - 0.2) ** 2) / 0.5) * (1 - 0.6 * y) + 0.10 * y ** 2
    rgb = np.stack([v * 0.85, v * 0.95, v * 1.15], 2)
    return Image.fromarray((np.clip(rgb, 0, 1) * 255).astype(np.uint8), 'RGB').convert('RGBA')


def cmd_screens(args):
    """Лист «на экране меню»: все _preview/*_screen.jpg сборки, по 4 в ряд."""
    from PIL import Image, ImageDraw, ImageFont
    outdir = args[0]
    out = opt(args, '--out', os.path.join(outdir, 'menuplayers-screens.jpg'))
    fs = sorted(glob.glob(os.path.join(outdir, '_preview', '*_screen.jpg')))
    font = ImageFont.truetype('C:/Windows/Fonts/segoeui.ttf', 18)
    TW, TH, cols = 480, 270, 4
    sheet = Image.new('RGB', (TW * cols, (TH + 24) * ((len(fs) + cols - 1) // cols)), (14, 14, 18))
    d = ImageDraw.Draw(sheet)
    for k, f in enumerate(fs):
        im = Image.open(f).resize((TW, TH), Image.LANCZOS)
        x, y = (k % cols) * TW, (k // cols) * (TH + 24)
        sheet.paste(im, (x, y))
        tag = os.path.basename(f)[:-11]
        nid = tag.split('_')[1] if '_' in tag else ''
        d.text((x + 6, y + TH + 2), f"{tag}  {number_label(nid) if nid.isdigit() else ''}", fill=(220, 220, 220), font=font)
    sheet.save(out, quality=88)
    print(out)


def cmd_sheet(args):
    from PIL import Image, ImageDraw, ImageFont
    outdir = args[0]
    out = opt(args, '--out', os.path.join(outdir, 'menuplayers-sheet.png'))
    spec = json.load(open(opt(args, '--spec'), encoding='utf-8')) if opt(args, '--spec') else None
    names = {e['slot']: e['name'] for e in spec['players']} if spec else {}
    files = sorted(glob.glob(os.path.join(outdir, *PLAYERS_REL.format('*').split('/'))),
                   key=lambda p: int(os.path.basename(p)[3:-4]))
    font = ImageFont.truetype('C:/Windows/Fonts/segoeui.ttf', 15)
    TW, TH, cols = 200, 253, 8
    sheet = Image.new('RGB', (TW * cols, (TH + 20) * ((len(files) + cols - 1) // cols)), (18, 18, 22))
    d = ImageDraw.Draw(sheet)
    for k, p in enumerate(files):
        mv = febg.FeMovie.load(p)
        t = texture_entry(mv)
        rgba = t.decode()
        img = Image.frombytes('RGBA', (t.fetch.width, t.fetch.height), rgba).crop((0, 0, FRAME_W, FRAME_H))
        bg = arena_backdrop(FRAME_W, FRAME_H)
        bg.alpha_composite(img)
        x, y = (k % cols) * TW, (k // cols) * (TH + 20)
        sheet.paste(bg.convert('RGB').resize((TW, TH), Image.LANCZOS), (x, y))
        slot = int(os.path.basename(p)[3:-4])
        d.text((x + 4, y + TH + 1), f'{slot}: {names.get(slot, "")}', fill=(220, 220, 220), font=font)
    sheet.save(out)
    print(out)


def opt(args, name, default=None):
    return args[args.index(name) + 1] if name in args else default


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    cmd, args = sys.argv[1], sys.argv[2:]
    {'slots': cmd_slots, 'plan': cmd_plan, 'cut': cmd_cut, 'build': cmd_build, 'sheet': cmd_sheet,
     'screens': cmd_screens, 'scout': cmd_scout, 'try': cmd_try, 'pick': cmd_pick}.get(
        cmd, lambda a: sys.exit(__doc__))(args)


if __name__ == '__main__':
    main()
