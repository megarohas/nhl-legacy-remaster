"""Форма из элементов конструктора формы NHL 13 («Создать команду», в файлах — cz*) для обычного пути формы
(table = 0, stockteamjerseys): свои файлы комплекта под свой номер арта, логотипы — свои (SVG).

    python czkit.py catalog OUTDIR                    # листы элементов конструктора (свитера, шорты, гетры, шрифты):
                                                      # зоны в условных цветах, на сетке свитера спереди и сзади
    python czkit.py build SPEC.json OUTDIR [--kits home,away] [--preview DIR] [--work DIR]
                                                      # комплекты из элементов конструктора по SPEC (раскладка cache:)
    python czkit.py sheet SPEC.json OUTDIR OUT.png    # лист превью уже собранных комплектов SPEC
    python czkit.py fe SPEC.json OUTDIR [--kits …] [--pose MODEL] [--preview DIR]
                                                      # только превью меню собранных комплектов — в позе EA
                                                      # (модель tools/fepose.py; по умолчанию pose.bin игры)
    python czkit.py verify OUTDIR NEW=CONTAINER…      # собранное против контейнера (kitpaint.verify)
    … --game legacy                                   # у любой команды: элементы и контейнеры NHL Legacy (ниже)

Устройство конструктора (разбор 08.10.2026, подробно — docs/uniforms.md §11). Все файлы — nocacherender.big, RW4
(.rx2), раскладка UV — как у комплектов EA стиля 1 (Reebok Edge):
  * свитер: rendering/czjersey/jerseyct_T_V_0_tm.rx2 и _1_tm (1024² DXT1, без мипов) — маски зон: каналы R, G, B двух
    файлов — 6 зон, в сумме 255 в каждом текселе (сглаженные края); jerseyct_T_V_dm (1024² DXT3) — детали поверх
    (строчка швов, шнуровка ворота, ярлыки) с альфой. T ∈ {0, 1, 2, 4, 5} — крой/рисунок панелей, V ∈ {0, 1} —
    вариант рисунка; в меню конструктора — 10 свитеров fe/ion/artassets/createteam/jersey/jersey0…9.big
    (порядок DESIGNS); в коде игры (таблицы 0x83938C38 / 0x83938C80, индекс — номер рисунка команды) — 9 пар
    (T, V), без 2_1.
  * нормали и блеск свитера: rendering/czlogo/logoct_L_T_nm.rx2 (1024² DXN, мипы) и logoct_L_T_sm (512² DXT1) — свои
    у каждой пары «логотип L × крой T» (рельеф логотипа L уже в карте). Без логотипа карт нет: чистая карта здесь —
    медиана по нескольким логотипам (CLEAN_LOGOS), под логотипом остаётся гладкая ткань.
  * логотип конструктора: logoct_L_0_tm, _1_tm (512², DXT1, альфа — силуэт), logoct_L_dm (детали); L = 0…86 без 54
    (fe/ion/artassets/createteam/logo/logo<20001 + L>.big). Здесь не нужны: логотипы — свои.
  * шрифт: rendering/czfont/czfont_F_tm.rx2 (1024² DXT3: R — заливка, G — обводка, B — вторая обводка, альфа — глиф;
    атлас — как у шрифтов EA, вдвое крупнее), czfont_F_nm (1024² DXN), czfont_F_sm (1024² DXT1); карта мест номера и
    фамилии czname_F_cm (256² 8888, кодировка как у name_*_cm EA: жёлтый, синий канал — зона). F = 0…11, в меню
    конструктора — 0…5 (createteam/font/font0…5.big); у 3 нет czname, у 7, 8, 10 — одна строка малых цифр (у EA —
    две), под обычный путь не годятся (FONT_OK).
  * шорты: rendering/czpant/pantct_P_0_tm.rx2 (512² DXT1, 3 зоны), pantct_P_dm (512² DXT3), czpant_P_nm (512² DXN),
    czpant_P_sm (256² DXT1); P = 0…5 (createteam/pants/pants0…5.big). Раскладка — как у шорт EA стиля 1.
  * гетры: rendering/czsock/texlib_S.rx2: sockct_S_0_tm (512² DXT1, 3 зоны) и sockct_S_dm (512² DXT3); S = 0…11,
    в меню — 0…5 (createteam/socks/socks0…5.big), раскладка — гетры EA стиля 1, сжатые по ширине вдвое (у EA
    1024×512). 6…11 — другая раскладка деталей (в меню их нет; не используются).
  * шейдер shaders/player_jersey_recolor_cz.fxo (boot.big): техника Recolor, сэмплеры recolor_template1…3,
    recolor_detail, recolor_logo_template/2, recolor_logo_detail, recolor_font_template, viraCompositeSampler —
    рисунок собирается на GPU из масок и цветов зон (customteamequipmenttable: 9 зон RGB на вид экипировки и
    variant 0/1), потом идёт как обычная текстура свитера.

Сборка (build): маски зон × свои цвета + детали dm (альфой) → jersey_cm / pant_cm / sock_cm; нормали/блеск — из
конструктора (свитер — медиана по логотипам, шорты — czpant); свои логотипы — на цвет, блеск и рельеф (kitpaint);
шрифт — czfont в своих цветах, уменьшенный до 512² (как у EA); карта номеров — czname; превью меню — в позе EA: манекен
с опущенными руками, складки и свет EA, по модели позы tools/fepose.py (карта «пиксель превью → UV свитера» и затенение,
выведенные из сотен превью и текстур EA стиля 1; файл pose.bin — game/work/…/fepose/, у каждой игры свой). Без модели —
прежняя своя отрисовка сетки свитера (rendering/jersey/jersey_1_0_0_0_0_2.rx2) в позе привязки (руки вперёд и в
стороны — «кривое» превью, как стояло 08.10). Контейнеры файлов (имена, заголовки,
форматы, мипы) — от комплекта EA стиля 1 (container в SPEC), пиксели — все свои; запись — kitpaint.build_kit.

SPEC (JSON, пример — game/work/uniforms/kitsrc-cz/SEA.json):
  team, title, note, colors {имя: "#RRGGBB"}, svg {имя: как в kitpaint}, container "1_28_0" (комплект EA стиля 1),
  sample {number, name, captain "C"|"A"} (пример номера на листе), candidates [{label, jersey}] (образцы без файлов),
  kits {имя: {kit "1_98_0", label, container (необяз.),
      jersey {design 0…9 | "T_V", zones [6 цветов: tm0 R, G, B, tm1 R, G, B], detail 0…1 (сила dm), logos [...],
              relief, relief_sign (необяз.)},
      font {id F, zones [заливка, обводка, вторая обводка], name F (карта, по умолчанию = id)},
      pant {design P, zones [3], detail, logos [...]} | {same_as: имя}, sock {design S, zones [3], detail},
      fe {yaw}}}.
  logos — как в kitpaint: [{"svg", "center": [x, y], "size": [w, h], "rotate"}] в координатах cm.

Только стандартная библиотека (+ Chrome/Edge без окна для SVG и листов — как в kitpaint). kitpaint, teamart,
playerhead — как библиотеки.

Другая игра: --game {nhl13,legacy} (или NHL_GAME, tools/gameprofile.py) у всех команд — элементы конструктора,
сетки и контейнеры из её распакованных архивов (у NHL Legacy cz-файлы почти все байт в байт как в NHL 13); кеш чистых
карт кроя — в папке работы игры (Legacy: game/work/legacy-data/art/czwork/clean). Номер арта другой длины (Legacy:
100/101) — контейнер kitpaint.default_container (3-значный комплект EA той же структуры). SPEC может наследовать
другой ("base", teamart.load_spec): {"base": "…/kitsrc-cz/SEA.json", "kits": {"home": {"kit": "1_100_0"}, …}}.
"""
import json, math, os, shutil, struct, sys, tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import playerhead as ph  # noqa: E402
import teamart as ta     # noqa: E402
import kitpaint as kp    # noqa: E402

Img = kp.Img

DESIGNS = [(0, 0), (0, 1), (1, 0), (1, 1), (2, 0), (2, 1), (4, 0), (4, 1), (5, 0), (5, 1)]   # jerseyN → (T, V)
FONT_OK = (0, 1, 2, 4, 5, 6, 9, 11)          # атлас как у EA (две строки малых цифр) и есть czname
CLEAN_LOGOS = (3, 12, 21, 30, 39, 48, 57, 66, 75)
CHEST_BOX = (300, 560, 724, 990)             # где на развёртке стиля 1 логотип груди (с запасом)
JERSEY_MESH = 'rendering/jersey/jersey_1_0_0_0_0_2.rx2'
JERSEY_AO = ('rendering/jersey/texlib_1_999.rx2', 'jersey_1_0_0_am')
PANT_MESH = 'rendering/pant/pant_1_0_0_2.rx2'
PANT_AO = ('rendering/pant/texlib_1_999.rx2', 'pant_1_0_0_am')
SOCK_MESH = 'rendering/sock/playersock_1_2.rx2'


# ---------------------------------------------------------------- файлы игры

def archive_of(rel):
    if rel.startswith(('rendering/jersey/', 'rendering/cz')):
        return 'nocacherender'
    if rel.startswith('rendering/'):
        return 'cacherender'
    if rel.startswith('shaders/'):
        return 'boot'
    return 'cache'


def source(rel):
    """Разжатый файл игры: распакованное дерево game/extracted/big/<архив>/, кеш game/work/uniforms/templates/,
    иначе — образ диска (с записью в кеш). Другая игра (teamart.set_game) — из её распакованных архивов."""
    if ta.game_name() != 'nhl13':
        return kp.profile_source(rel)
    g = kp.game_dir()
    arc = archive_of(rel)
    for p in (os.path.join(g, 'extracted', 'big', arc, *rel.split('/')),
              os.path.join(g, 'work', 'uniforms', 'templates', *rel.split('/'))):
        if os.path.exists(p):
            return kp._unchunk(open(p, 'rb').read())
    path, entries, unpack_big = kp._disc_entries(arc)
    e = entries.get(rel)
    if e is None:
        raise SystemExit(f'{rel}: нет в {arc}.big')
    with open(path, 'rb') as f:
        f.seek(e.offset)
        blob = f.read(e.stored_size)
    if e.is_packed:
        blob = unpack_big.decompress_packed_member(blob, e.unpacked_size)
    blob = kp._unchunk(blob)
    cache = os.path.join(g, 'work', 'uniforms', 'templates', *rel.split('/'))
    os.makedirs(os.path.dirname(cache), exist_ok=True)
    open(cache, 'wb').write(blob)
    return blob


_TEX = {}


def tex(rel, name=None, lv=0):
    """Текстура из .rx2 (первая или с именем, содержащим name) → Img (с кешем; отдаётся копия)."""
    key = (rel, name, lv)
    if key not in _TEX:
        rw = ta.Rw4(source(rel), rel)
        ts = [t for t in rw.textures if name is None or name in t.name]
        if not ts:
            raise SystemExit(f'{rel}: нет текстуры {name}')
        _TEX[key] = Img(*kp.tex_decode(rw, ts[0], lv))
    return _TEX[key].copy()


def fe_image(rel):
    u = ta.UiLogo(source(rel), rel)
    return Img(*u.decode())


# ---------------------------------------------------------------- элементы конструктора

def design_tv(d):
    if isinstance(d, str) and '_' in d:
        t, v = d.split('_')
        return int(t), int(v)
    return DESIGNS[int(d)]


def jersey_layers(design):
    """Маски зон (tm0, tm1) и детали (dm) свитера-шаблона конструктора."""
    t, v = design_tv(design)
    base = f'rendering/czjersey/jerseyct_{t}_{v}'
    return tex(base + '_0_tm.rx2'), tex(base + '_1_tm.rx2'), tex(base + '_dm.rx2')


def pant_layers(p):
    return (tex(f'rendering/czpant/pantct_{p}_0_tm.rx2'), tex(f'rendering/czpant/pantct_{p}_dm.rx2'),
            tex(f'rendering/czpant/czpant_{p}_nm.rx2'), tex(f'rendering/czpant/czpant_{p}_sm.rx2'))


def sock_layers(s):
    rel = f'rendering/czsock/texlib_{s}.rx2'
    return tex(rel, f'sockct_{s}_0_tm'), tex(rel, f'sockct_{s}_dm')


def font_layers(f):
    return (tex(f'rendering/czfont/czfont_{f}_tm.rx2'), tex(f'rendering/czfont/czfont_{f}_nm.rx2'),
            tex(f'rendering/czfont/czfont_{f}_sm.rx2'))


def name_map(f):
    return tex(f'rendering/czfont/czname_{f}_cm.rx2')


def _median_planes(imgs, chans):
    """Попиксельная медиана нескольких картинок одного размера по каналам chans → Img (остальные каналы — первой)."""
    out = imgs[0].copy()
    n = len(imgs)
    mid = n // 2
    pxs = [im.px for im in imgs]
    o = out.px
    for c in chans:
        cols = [p[c::4] for p in pxs]
        res = bytearray(len(cols[0]))
        for i, vals in enumerate(zip(*cols)):
            res[i] = sorted(vals)[mid]
        o[c::4] = res
    return out


_CLEAN = {}


def clean_jersey_maps(t, logos=CLEAN_LOGOS, log=print):
    """Нормали (1024²) и блеск (512²) кроя t без логотипа конструктора: медиана по logos.
    → (nm, sm, калибровка рельефа и блеска вышивки по первому логотипу)."""
    key = (t, tuple(logos))
    if key in _CLEAN:
        nm, sm, cal = _CLEAN[key]
        return nm.copy(), sm.copy(), dict(cal)
    if ta.game_name() == 'nhl13':
        cdir = os.path.join(kp.game_dir(), 'work', 'uniforms', 'czwork', 'clean')
    else:
        cdir = ta.GAME.work_dir('art', 'czwork', 'clean')
    tag = f'{t}_' + '-'.join(map(str, logos))
    paths = [os.path.join(cdir, f'{tag}_{k}') for k in ('nm.png', 'sm.png', 'cal.json')]
    if all(os.path.exists(p) for p in paths):                     # кеш на диске (медиана — ~30 с на крой)
        nm, sm = Img.load(paths[0]), Img.load(paths[1])
        cal = {k: tuple(v) for k, v in json.load(open(paths[2])).items()}
        _CLEAN[key] = (nm.copy(), sm.copy(), dict(cal))
        return nm, sm, cal
    nms = [tex(f'rendering/czlogo/logoct_{l}_{t}_nm.rx2') for l in logos]
    sms = [tex(f'rendering/czlogo/logoct_{l}_{t}_sm.rx2') for l in logos]
    nm = _median_planes(nms, (0, 1))
    sm = _median_planes(sms, (0, 1, 2))
    # следы логотипов конструктора (отличие от медианы на груди): где их больше половины, медиана — сам логотип
    # (гладкая середина вышивки) — там нормали и блеск стираются (гладкий фон + узор трикотажа, kitpaint.erase)
    w, h = nm.w, nm.h
    box = CHEST_BOX
    feet = []
    count = bytearray(w * h)
    for ref in nms:
        f = bytearray(w * h)
        for y in range(box[1], box[3]):
            for x in range(box[0], box[2]):
                i = y * w + x
                if abs(ref.px[i * 4] - nm.px[i * 4]) + abs(ref.px[i * 4 + 1] - nm.px[i * 4 + 1]) > 12:
                    f[i] = 1
        f = kp.fill_holes(kp.dilate(f, w, h, 2), w, h, box)
        feet.append(f)
        for i in range(w * h):
            if f[i]:
                count[i] += 1
    core = bytearray(1 if c * 2 >= len(nms) else 0 for c in count)
    cal = {}
    # знак рельефа по логотипу конструктора не берётся: регрессия по разнице с медианой слабая (|k| ≈ 2…7, знак
    # скачет); рельеф своих логотипов — как у EA (kitpaint: (−1, +1), выпуклая вышивка)
    kp.relief_calibrate(nms[0], feet[0], log)
    g = kp.gloss_calibrate(sms[0], kp.scale_mask(feet[0], w, h, sms[0].w, sms[0].h), log)
    if g:
        cal['gloss'] = g
    bb = kp.mask_bbox(core, w, h)
    if bb:
        m = kp.dilate(core, w, h, 3)
        kp.erase(nm, m, chans=(0, 1), log=log)
        kp.erase(sm, kp.dilate(kp.scale_mask(core, w, h, sm.w, sm.h), sm.w, sm.h, 2), log=log)
    kp.renormalize(nm)
    if log:
        log(f'    чистые карты кроя {t}: медиана по логотипам {list(logos)}; общая середина логотипов — {bb}')
    os.makedirs(cdir, exist_ok=True)
    nm.save(paths[0])
    sm.save(paths[1])
    json.dump(cal, open(paths[2], 'w'))
    _CLEAN[key] = (nm.copy(), sm.copy(), dict(cal))
    return nm, sm, cal


# ---------------------------------------------------------------- сборка картинок

def compose(masks, colors, palette=None):
    """Маски зон (Img, каналы R, G, B; сумма по всем маскам — 255) × цвета зон → Img (альфа — первой маски)."""
    cols = [kp.parse_color(c, palette) for c in colors]
    need = 3 * len(masks)
    if len(cols) < need:
        raise SystemExit(f'нужно {need} цветов зон, задано {len(cols)}')
    w, h = masks[0].w, masks[0].h
    out = bytearray(w * h * 4)
    pls = [m.px for m in masks]
    # таблица: значение маски → вклад зоны в каждый канал (×255, целые)
    luts = [[[v * col[c] for v in range(256)] for c in range(3)] for col in cols]
    for i in range(0, w * h * 4, 4):
        r = g = b = 0
        tot = 0
        z = 0
        for p in pls:
            for c in range(3):
                v = p[i + c]
                if v:
                    lt = luts[z]
                    r += lt[0][v]
                    g += lt[1][v]
                    b += lt[2][v]
                    tot += v
                z += 1
        if tot:                                   # сумма зон — 255 (у EA); нормировка — на случай сжатия DXT1
            out[i] = (r + tot // 2) // tot
            out[i + 1] = (g + tot // 2) // tot
            out[i + 2] = (b + tot // 2) // tot
        out[i + 3] = pls[0][i + 3]
    return Img(w, h, out)


def detail_over(img, dm, strength=1.0):
    """Детали конструктора поверх (альфа dm × strength)."""
    if (dm.w, dm.h) != (img.w, img.h):
        dm = resize(dm, img.w, img.h)
    o, d = img.px, dm.px
    for i in range(0, img.w * img.h * 4, 4):
        a = d[i + 3] * strength / 255.0
        if a <= 0:
            continue
        for c in range(3):
            o[i + c] = int(o[i + c] * (1 - a) + d[i + c] * a + 0.5)
    return img


def resize(img, nw, nh):
    """Билинейное масштабирование (для увеличения: гетры 512 → 1024, блеск 512 → 1024)."""
    w, h, s = img.w, img.h, img.px
    out = bytearray(nw * nh * 4)
    for y in range(nh):
        fy = (y + 0.5) * h / nh - 0.5
        y0 = int(math.floor(fy))
        ty = fy - y0
        ya, yb = min(h - 1, max(0, y0)), min(h - 1, max(0, y0 + 1))
        for x in range(nw):
            fx = (x + 0.5) * w / nw - 0.5
            x0 = int(math.floor(fx))
            tx = fx - x0
            xa, xb = min(w - 1, max(0, x0)), min(w - 1, max(0, x0 + 1))
            o = (y * nw + x) * 4
            p00, p01 = (ya * w + xa) * 4, (ya * w + xb) * 4
            p10, p11 = (yb * w + xa) * 4, (yb * w + xb) * 4
            for c in range(4):
                v = (s[p00 + c] * (1 - tx) + s[p01 + c] * tx) * (1 - ty) + (s[p10 + c] * (1 - tx) + s[p11 + c] * tx) * ty
                out[o + c] = int(v + 0.5)
    return Img(nw, nh, out)


def half(img, normals=False):
    """Уменьшение вдвое (атлас шрифта 1024 → 512 как у EA): цвет — с премножением альфы, нормали — нормировкой."""
    if normals:
        rgba, w, h = kp.downsample_normals(img.px, img.w, img.h)
        return Img(w, h, rgba)
    rgba, w, h = ta.downsample2(bytes(img.px), img.w, img.h)
    return Img(w, h, rgba)


def font_image(tm, zones, palette=None):
    """Атлас шрифта конструктора (зоны R/G/B + альфа глифа) в цветах zones [заливка, обводка, вторая обводка]."""
    img = compose([tm], zones, palette)
    img.px[3::4] = tm.px[3::4]
    return img


# ---------------------------------------------------------------- сетка (RW4 Xbox 360) и отрисовка

def _half_float(h):
    s, e, m = (h >> 15) & 1, (h >> 10) & 31, h & 1023
    v = m / 1024.0 * 2 ** -14 if e == 0 else (1 + m / 1024.0) * 2 ** (e - 15)
    return -v if s else v


def _dec3n(w):
    out = []
    for k in range(3):
        v = (w >> (10 * k)) & 1023
        if v & 512:
            v -= 1024
        out.append(max(-1.0, v / 511.0))
    return out


class Mesh:
    """Сетка RW4: декларация вершин (0x20004: смещение, тип D3DDECLTYPE Xbox 360, использование), буфер вершин и
    индексов (0x10031), описания (0x20005: число вершин; 0x20007: число индексов), полосы треугольников с 0xFFFF.
    Вершина свитера (32 байта): позиция FLOAT16_4, нормаль и касательная DEC3N, UV USHORT2N, кости USHORT4, веса
    UBYTE4N — поза привязки (руки вперёд и в стороны)."""

    def __init__(self, data):
        u = lambda o: struct.unpack_from('>I', data, o)[0]
        n, tab, hdr = u(0x20), u(0x30), u(0x44)
        secs = [struct.unpack_from('>6I', data, tab + 24 * i) for i in range(n)]
        datas = [(s[0] + hdr, s[2]) for s in secs if s[5] == 0x10031]
        part = lambda typ: next(data[s[0]:s[0] + s[2]] for s in secs if s[5] == typ)
        decl, vbd, ibd = part(0x20004), part(0x20005), part(0x20007)
        elems = []
        for p in range(16, len(decl) - 11, 12):
            o, t, use = struct.unpack_from('>3I', decl, p)
            elems.append((o & 0xFFFF, t, (use >> 16) & 0xFF))
        nv = struct.unpack_from('>I', vbd, 36)[0]
        ni = struct.unpack_from('>I', ibd, 32)[0]
        (vo, vs), (io, _) = datas[0], datas[1]
        stride = vs // nv
        self.pos, self.nrm, self.tan, self.uv = [], [], [], []
        for i in range(nv):
            b = vo + i * stride
            for o, t, use in elems:
                if t == 0x1a2360 and use == 0:
                    self.pos.append([_half_float(x) for x in struct.unpack_from('>3H', data, b + o)])
                elif t == 0x2a2187 and use == 3:
                    self.nrm.append(_dec3n(u(b + o)))
                elif t == 0x2a2187 and use == 6:
                    self.tan.append(_dec3n(u(b + o)))
                elif t == 0x2c2059 and use == 5:
                    self.uv.append([x / 65535.0 for x in struct.unpack_from('>2H', data, b + o)])
        idx = struct.unpack_from('>%dH' % ni, data, io)
        self.tris = []
        strip = []
        for i in idx:
            if i == 0xFFFF:
                strip = []
                continue
            strip.append(i)
            if len(strip) >= 3:
                a, b, c = strip[-3:]
                if (len(strip) - 3) % 2:
                    a, b = b, a
                if a != b and b != c and a != c:
                    self.tris.append((a, b, c))

    @classmethod
    def load(cls, rel):
        return cls(source(rel))


def _sample(img, u, v):
    """Билинейная выборка (с повтором по краям) → (r, g, b, a) float."""
    w, h, s = img.w, img.h, img.px
    fx, fy = u * w - 0.5, v * h - 0.5
    x0, y0 = int(math.floor(fx)), int(math.floor(fy))
    tx, ty = fx - x0, fy - y0
    xa, xb = min(w - 1, max(0, x0)), min(w - 1, max(0, x0 + 1))
    ya, yb = min(h - 1, max(0, y0)), min(h - 1, max(0, y0 + 1))
    p00, p01, p10, p11 = (ya * w + xa) * 4, (ya * w + xb) * 4, (yb * w + xa) * 4, (yb * w + xb) * 4
    return [(s[p00 + c] * (1 - tx) + s[p01 + c] * tx) * (1 - ty) + (s[p10 + c] * (1 - tx) + s[p11 + c] * tx) * ty
            for c in range(4)]


class Camera:
    """Ортографическая камера: поворот вокруг вертикали (yaw, градусы; 0 — спереди, 180 — сзади), наклон (pitch),
    кадр — рамка (x0, y0, x1, y1) в координатах модели после поворота (метры) → картинка w×h."""

    def __init__(self, yaw, frame, w, h, pitch=0.0):
        self.cy, self.sy = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
        self.cp, self.sp = math.cos(math.radians(pitch)), math.sin(math.radians(pitch))
        self.frame, self.w, self.h = frame, w, h

    def rot(self, p):
        x, y, z = p
        x, z = x * self.cy + z * self.sy, -x * self.sy + z * self.cy
        y, z = y * self.cp - z * self.sp, y * self.sp + z * self.cp
        return x, y, z

    def screen(self, p):
        x, y, z = self.rot(p)
        x0, y0, x1, y1 = self.frame
        return (x - x0) / (x1 - x0) * self.w, (y1 - y) / (y1 - y0) * self.h, z


class Canvas:
    def __init__(self, w, h, bg=(0, 0, 0, 0)):
        self.w, self.h = w, h
        self.px = bytearray(bytes(bg) * (w * h))
        self.z = [-1e9] * (w * h)

    def img(self):
        return Img(self.w, self.h, self.px)


LIGHT = (-0.35, 0.45, 0.82)


def draw_mesh(cv, cam, mesh, tex_img=None, nm=None, ao=None, color=None, light=LIGHT, amb=0.42, diff=0.72,
              spec=0.10, flat=None):
    """Сетка на холст: текстура (или цвет color), нормали из карты nm (касательное пространство), затенение ao,
    Ламберт + немного блика. flat — множитель яркости без света (силуэт манекена)."""
    ln = math.sqrt(sum(c * c for c in light))
    L = [c / ln for c in light]
    H = [L[0], L[1], L[2] + 1.0]
    hn = math.sqrt(sum(c * c for c in H))
    H = [c / hn for c in H]
    S = [cam.screen(p) for p in mesh.pos]
    N = [cam.rot(n) for n in mesh.nrm]
    T = [cam.rot(t) for t in mesh.tan] if mesh.tan else None
    W, Hh = cv.w, cv.h
    zb, px = cv.z, cv.px
    for a, b, c in mesh.tris:
        (x0, y0, z0), (x1, y1, z1), (x2, y2, z2) = S[a], S[b], S[c]
        area = (x1 - x0) * (y2 - y0) - (x2 - x0) * (y1 - y0)
        if abs(area) < 1e-9:
            continue
        minx, maxx = max(0, int(min(x0, x1, x2))), min(W - 1, int(max(x0, x1, x2)) + 1)
        miny, maxy = max(0, int(min(y0, y1, y2))), min(Hh - 1, int(max(y0, y1, y2)) + 1)
        if minx > maxx or miny > maxy:
            continue
        ua, ub, uc = mesh.uv[a], mesh.uv[b], mesh.uv[c]
        na, nb, nc = N[a], N[b], N[c]
        ta_, tb, tc = (T[a], T[b], T[c]) if T else (None, None, None)
        for py in range(miny, maxy + 1):
            fy = py + 0.5
            for qx in range(minx, maxx + 1):
                fx = qx + 0.5
                w0 = ((x1 - fx) * (y2 - fy) - (x2 - fx) * (y1 - fy)) / area
                w1 = ((x2 - fx) * (y0 - fy) - (x0 - fx) * (y2 - fy)) / area
                w2 = 1 - w0 - w1
                if w0 < 0 or w1 < 0 or w2 < 0:
                    continue
                z = w0 * z0 + w1 * z1 + w2 * z2
                i = py * W + qx
                if z <= zb[i]:
                    continue
                zb[i] = z
                u = w0 * ua[0] + w1 * ub[0] + w2 * uc[0]
                v = w0 * ua[1] + w1 * ub[1] + w2 * uc[1]
                n = [w0 * na[k] + w1 * nb[k] + w2 * nc[k] for k in range(3)]
                nl = math.sqrt(n[0] * n[0] + n[1] * n[1] + n[2] * n[2]) or 1.0
                n = [n[0] / nl, n[1] / nl, n[2] / nl]
                if nm is not None and T:
                    t = [w0 * ta_[k] + w1 * tb[k] + w2 * tc[k] for k in range(3)]
                    d = t[0] * n[0] + t[1] * n[1] + t[2] * n[2]
                    t = [t[k] - d * n[k] for k in range(3)]
                    tl = math.sqrt(t[0] * t[0] + t[1] * t[1] + t[2] * t[2]) or 1.0
                    t = [t[k] / tl for k in range(3)]
                    bt = [n[1] * t[2] - n[2] * t[1], n[2] * t[0] - n[0] * t[2], n[0] * t[1] - n[1] * t[0]]
                    s = _sample(nm, u, v)
                    sx, sy_ = s[0] / 127.5 - 1, s[1] / 127.5 - 1
                    sz = math.sqrt(max(0.0, 1 - sx * sx - sy_ * sy_))
                    n = [t[k] * sx - bt[k] * sy_ + n[k] * sz for k in range(3)]
                    nl = math.sqrt(n[0] * n[0] + n[1] * n[1] + n[2] * n[2]) or 1.0
                    n = [n[0] / nl, n[1] / nl, n[2] / nl]
                if n[2] < 0:
                    n = [-n[0], -n[1], -n[2]]
                dl = max(0.0, n[0] * L[0] + n[1] * L[1] + n[2] * L[2])
                sh = amb + diff * dl
                if ao is not None:
                    sh *= 0.35 + 0.65 * _sample(ao, u, v)[0] / 255.0
                hl = max(0.0, n[0] * H[0] + n[1] * H[1] + n[2] * H[2]) ** 24 * spec * 255
                if flat is not None:
                    sh, hl = flat * (0.8 + 0.3 * dl), hl * 0.5
                col = _sample(tex_img, u, v) if tex_img is not None else color
                o = i * 4
                px[o] = min(255, int(col[0] * sh + hl))
                px[o + 1] = min(255, int(col[1] * sh + hl))
                px[o + 2] = min(255, int(col[2] * sh + hl))
                px[o + 3] = 255
    return cv


_MESH = {}


def mesh(rel):
    if rel not in _MESH:
        _MESH[rel] = Mesh.load(rel)
    return _MESH[rel]


def bounds(m, cam_yaw=0.0):
    cam = Camera(cam_yaw, (0, 0, 1, 1), 1, 1)
    pts = [cam.rot(p) for p in m.pos]
    return (min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts))


def fit_frame(b, w, h, pad=0.04):
    x0, y0, x1, y1 = b
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    sw, sh = (x1 - x0) * (1 + pad), (y1 - y0) * (1 + pad)
    if sw / sh < w / h:
        sw = sh * w / h
    else:
        sh = sw * h / w
    return (cx - sw / 2, cy - sh / 2, cx + sw / 2, cy + sh / 2)


def render_jersey(cm, nm=None, yaw=0.0, w=420, h=360, bg=(0, 0, 0, 0), ao=True, frame=None, pants=None):
    """Свитер (и, по желанию, шорты pants = (cm, nm)) на сетке EA стиля 1 → Img."""
    jm = mesh(JERSEY_MESH)
    aoi = tex(*JERSEY_AO) if ao else None
    if frame is None:
        b = bounds(jm, yaw)
        if pants is not None:
            pb = bounds(mesh(PANT_MESH), yaw)
            b = (min(b[0], pb[0]), min(b[1], pb[1]), max(b[2], pb[2]), max(b[3], pb[3]))
        frame = fit_frame(b, w, h)
    cam = Camera(yaw, frame, w, h)
    cv = Canvas(w, h, bg)
    if pants is not None:
        pm = mesh(PANT_MESH)
        draw_mesh(cv, cam, pm, pants[0], pants[1], tex(*PANT_AO) if ao else None)
    draw_mesh(cv, cam, jm, cm, nm, aoi)
    return cv.img()


def render_sock(cm, yaw=0.0, w=200, h=300, bg=(0, 0, 0, 0)):
    sm = mesh(SOCK_MESH)
    frame = fit_frame(bounds(sm, yaw), w, h)
    cam = Camera(yaw, frame, w, h)
    cv = Canvas(w, h, bg)
    draw_mesh(cv, cam, sm, cm, None, None)
    return cv.img()


# ---------------------------------------------------------------- номера и фамилия на развёртке (только для превью)

def font_cells(font_rgba):
    """Клетки глифов атласа 512² (раскладка EA): {символ: (x0, y0, x1, y1)} по альфе."""
    w, h, px = font_rgba.w, font_rgba.h, font_rgba.px
    a = px[3::4]

    def runs(flags):
        out, s = [], None
        for i, f in enumerate(list(flags) + [False]):
            if f and s is None:
                s = i
            if not f and s is not None:
                out.append((s, i))
                s = None
        return out

    def cols_in(y0, y1, x0=0, x1=None):
        x1 = w if x1 is None else x1
        return [(c0 + x0, c1 + x0) for c0, c1 in
                runs([any(a[y * w + x] >= 96 for y in range(y0, y1)) for x in range(x0, x1)])]

    cells = {}
    # буквы: две строки (A–O, P–Z) в полосе 0…98
    lrows = runs([any(a[y * w + x] >= 96 for x in range(w)) for y in range(0, 98)])
    alpha = 'ABCDEFGHIJKLMNO', 'PQRSTUVWXYZ'
    for (y0, y1), chars in zip(lrows[:2], alpha):
        cs = [c for c in cols_in(y0, y1) if c[1] - c[0] > 2]
        for ch, (x0, x1) in zip(chars, cs):
            cells[ch] = (x0, y0, x1, y1)
    # большие цифры: две строки в полосе 98…368, слева от C/A (x < 410)
    brows = runs([any(a[y * w + x] >= 96 for x in range(0, 405)) for y in range(98, 368)])
    brows = [(y0 + 98, y1 + 98) for y0, y1 in brows if y1 - y0 > 40]
    for (y0, y1), chars in zip(brows[:2], ('01234', '56789')):
        cs = [c for c in cols_in(y0, y1, 0, 405) if c[1] - c[0] > 4]
        if len(cs) > 5:                                    # «1» и соседи могут слипнуться — берём 5 самых широких
            cs = sorted(sorted(cs, key=lambda c: c[0] - c[1])[:5])
        for ch, (x0, x1) in zip(chars, cs):
            cells['big' + ch] = (x0, y0, x1, y1)
    # малые цифры: первая строка 368…448
    srows = runs([any(a[y * w + x] >= 96 for x in range(w)) for y in range(368, 512)])
    if srows:
        y0, y1 = srows[0][0] + 368, srows[0][1] + 368
        cs = [c for c in cols_in(y0, y1) if c[1] - c[0] > 2]
        for ch, (x0, x1) in zip('0123456789', cs):
            cells['sm' + ch] = (x0, y0, x1, y1)
    return cells


def glyph_strip(font, cells, keys, height, gap=0.08):
    """Строка глифов (клетки атласа) высотой height → Img RGBA (для превью)."""
    gl = [cells[k] for k in keys if k in cells]
    if not gl:
        return None
    ws = [max(1, int(round((c[2] - c[0]) * height / (c[3] - c[1])))) for c in gl]
    g = int(round(gap * height))
    W = sum(ws) + g * (len(ws) - 1)
    out = Img(max(1, W), max(1, int(height)))
    x = 0
    for c, gw in zip(gl, ws):
        for yy in range(out.h):
            sy = c[1] + (yy + 0.5) * (c[3] - c[1]) / out.h
            for xx in range(gw):
                sx = c[0] + (xx + 0.5) * (c[2] - c[0]) / gw
                s = _sample(font, sx / font.w, sy / font.h)
                o = (yy * out.w + x + xx) * 4
                out.px[o:o + 4] = bytes(min(255, max(0, int(v + 0.5))) for v in s)
        x += gw + g
    return out


def rotate(img, rot):
    """Поворот на 0/90/180/270 градусов по часовой стрелке."""
    rot %= 360
    if rot == 0:
        return img
    w, h, s = img.w, img.h, img.px
    if rot == 180:
        out = Img(w, h)
        for y in range(h):
            for x in range(w):
                o, q = (y * w + x) * 4, ((h - 1 - y) * w + (w - 1 - x)) * 4
                out.px[o:o + 4] = s[q:q + 4]
        return out
    out = Img(h, w)
    for y in range(h):
        for x in range(w):
            q = (y * w + x) * 4
            nx, ny = (h - 1 - y, x) if rot == 90 else (y, w - 1 - x)
            o = (ny * h + nx) * 4
            out.px[o:o + 4] = s[q:q + 4]
    return out


def draw_glyphs(cm, font, cells, keys, box, scale_h=1.0, gap=0.08, rot=0):
    """Глифы keys в рамку box развёртки (x0, y0, x1, y1): по центру, высота — доля scale_h рамки (поперёк
    строки), не шире рамки; rot — поворот строки по часовой стрелке (спина на развёртке EA — вверх ногами)."""
    x0, y0, x1, y1 = box
    bw, bh = (x1 - x0, y1 - y0) if rot % 180 == 0 else (y1 - y0, x1 - x0)
    hgt = bh * scale_h
    strip = glyph_strip(font, cells, keys, max(4, int(hgt * 2)), gap)
    if strip is None:
        return
    k = min(hgt / strip.h, bw / strip.w)
    sw, sh = max(1, int(strip.w * k)), max(1, int(strip.h * k))
    strip = rotate(resize(strip, sw, sh), rot)
    ox = int(round((x0 + x1) / 2 - strip.w / 2))
    oy = int(round((y0 + y1) / 2 - strip.h / 2))
    kp.over_at(cm, strip, ox, oy)


def zone_boxes(nmap, scale):
    """Рамки зон карты номеров (синий канал) в координатах развёртки свитера (×scale)."""
    w, h, px = nmap.w, nmap.h, nmap.px
    boxes = {}
    for i in range(w * h):
        r, g, b = px[i * 4], px[i * 4 + 1], px[i * 4 + 2]
        if r > 200 and g > 200 and b < 16:
            x, y = i % w, i // w
            bb = boxes.setdefault(b, [w, h, -1, -1])
            bb[0], bb[1], bb[2], bb[3] = min(bb[0], x), min(bb[1], y), max(bb[2], x), max(bb[3], y)
    return {k: (v[0] * scale, v[1] * scale, (v[2] + 1) * scale, (v[3] + 1) * scale) for k, v in boxes.items()}


SAMPLE_ROT = {0: 180, 1: 180, 2: 90, 3: 270, 5: 0}     # поворот глифов по зонам карты (развёртка стиля 1)


def stamp_sample(cm, font, nmap, number='19', name='', captain=None, rots=None):
    """Пример номера и фамилии на развёртке (только превью: в игре их ставит шейдер по карте name_*_cm; размеры —
    по рамкам зон карты, поэтому приблизительно)."""
    rots = dict(SAMPLE_ROT, **(rots or {}))
    out = cm.copy()
    cells = font_cells(font)
    boxes = zone_boxes(nmap, cm.w / nmap.w)
    if 1 in boxes:
        draw_glyphs(out, font, cells, ['big' + d for d in number], boxes[1], 0.92, rot=rots[1])
    if name and 0 in boxes:
        draw_glyphs(out, font, cells, list(name.upper()), boxes[0], 0.78, gap=0.12, rot=rots[0])
    for z in (2, 3):
        if z in boxes:
            draw_glyphs(out, font, cells, ['sm' + d for d in number], boxes[z], 0.8, rot=rots[z])
    if captain and 5 in boxes:
        key = 'C' if captain == 'C' else 'A'
        ca = font_cells_ca(font)
        if key in ca:
            draw_glyphs(out, font, ca, [key], boxes[5], 0.85, rot=rots[5])
    return out


def font_cells_ca(font):
    """Клетки C и A (столбец справа от больших цифр, x ≥ 410)."""
    w, h, a = font.w, font.h, font.px[3::4]
    rows = []
    s = None
    for y in range(78, 320):
        f = any(a[y * w + x] >= 96 for x in range(410, w))
        if f and s is None:
            s = y
        if not f and s is not None:
            rows.append((s, y))
            s = None
    rows = [r for r in rows if r[1] - r[0] > 20]
    out = {}
    for (y0, y1), ch in zip(rows[:2], 'CA'):
        xs = [x for x in range(410, w) if any(a[y * w + x] >= 96 for y in range(y0, y1))]
        out[ch] = (xs[0], y0, xs[-1] + 1, y1)
    return out


# ---------------------------------------------------------------- PNG RGB (снимки Chrome) и вырезка

def png_read_any(path):
    """PNG 8 бит RGB/RGBA/серый (снимки Chrome — RGB без альфы; playerhead.png_read их не читает) → (w, h, RGBA)."""
    import zlib
    data = open(path, 'rb').read()
    p = 8
    w = h = ct = 0
    idat = bytearray()
    while p < len(data):
        n = struct.unpack_from('>I', data, p)[0]
        typ = data[p + 4:p + 8]
        body = data[p + 8:p + 8 + n]
        if typ == b'IHDR':
            w, h, bd, ct = struct.unpack_from('>IIBB', body, 0)
            if bd != 8:
                raise SystemExit(f'{path}: глубина {bd}')
        elif typ == b'IDAT':
            idat += body
        p += 12 + n
    bpp = {0: 1, 2: 3, 4: 2, 6: 4}[ct]
    raw = zlib.decompress(bytes(idat))
    stride = w * bpp
    out = bytearray(w * h * 4)
    prev = bytearray(stride)
    pos = 0
    for y in range(h):
        f = raw[pos]
        line = bytearray(raw[pos + 1:pos + 1 + stride])
        pos += 1 + stride
        for i in range(stride):
            a = line[i - bpp] if i >= bpp else 0
            b = prev[i]
            c = prev[i - bpp] if i >= bpp else 0
            if f == 1:
                line[i] = (line[i] + a) & 255
            elif f == 2:
                line[i] = (line[i] + b) & 255
            elif f == 3:
                line[i] = (line[i] + (a + b) // 2) & 255
            elif f == 4:
                pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
                line[i] = (line[i] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        o = y * w * 4
        for x in range(w):
            s = x * bpp
            if bpp == 4:
                out[o + x * 4:o + x * 4 + 4] = line[s:s + 4]
            elif bpp == 3:
                out[o + x * 4:o + x * 4 + 4] = bytes((line[s], line[s + 1], line[s + 2], 255))
            elif bpp == 2:
                out[o + x * 4:o + x * 4 + 4] = bytes((line[s], line[s], line[s], line[s + 1]))
            else:
                out[o + x * 4:o + x * 4 + 4] = bytes((line[s], line[s], line[s], 255))
        prev = line
    return w, h, bytes(out)


def crop_png(src, x0, y0, x1, y1, dst):
    w, h, px = png_read_any(src)
    x1, y1 = min(w, x1), min(h, y1)
    out = bytearray()
    for y in range(y0, y1):
        out += px[(y * w + x0) * 4:(y * w + x1) * 4]
    ph.png_write(dst, x1 - x0, y1 - y0, bytes(out))
    return dst


# ---------------------------------------------------------------- листы (Chrome/Edge без окна)

def _uri(img, tmp, name):
    return kp._png_uri(img, tmp, name)


SHEET_CSS = ('html,body{margin:0;background:#2b2f36;color:#e8eaed;font:14px "Segoe UI",Arial,sans-serif;overflow:hidden}'
             'h1{margin:0;padding:16px 22px 4px;font-size:24px;font-weight:600}'
             'h2{margin:14px 0 6px;font-size:18px;font-weight:600}'
             'h2 span{font-weight:400;color:#9aa0a6;font-size:13px;margin-left:8px}'
             'p.note{margin:2px 22px 8px;color:#b9bec5;font-size:13px;max-width:1700px;line-height:1.4}'
             'section{padding:0 22px 6px}.row{display:flex;gap:12px;align-items:flex-start;flex-wrap:wrap}'
             '.col{display:flex;flex-direction:column;gap:8px}'
             'figure{margin:0}figcaption{color:#b9bec5;font-size:12px;margin-top:3px;max-width:520px}'
             'img{display:block;background:#1f2228}'
             '.chk{background:repeating-conic-gradient(#8a8f96 0 25%,#6c7178 0 50%) 0 0/16px 16px}'
             '.sw{display:inline-block;width:12px;height:12px;border:1px solid #777;vertical-align:-1px;margin:0 3px 0 6px}')


def render_sheet(html_body, title, out_png, w, h):
    import html as H
    page = (f'<!doctype html><html><head><meta charset="utf-8"><style>{SHEET_CSS}'
            f'html,body{{width:{w}px;height:{h}px}}</style></head><body><h1>{H.escape(title)}</h1>{html_body}</body></html>')
    kp.render_page(page, out_png, w, h)
    return out_png


def fig(uri, w, h, cap, cls=''):
    import html as H
    return (f'<figure><img class="{cls}" src="{uri}" style="width:{w}px;height:{h}px">'
            f'<figcaption>{H.escape(cap)}</figcaption></figure>')


TEST_ZONES = ['#D9D9D9', '#C8102E', '#1F4E9C', '#F2B705', '#2E8B57', '#7A3FA0']
TEST_NAMES = ['tm0.R', 'tm0.G', 'tm0.B', 'tm1.R', 'tm1.G', 'tm1.B']


def swatches(colors, names):
    import html as H
    return ''.join(f'<span class="sw" style="background:{c}"></span>{H.escape(n)}' for c, n in zip(colors, names))


def fe_crop(rel):
    """Превью меню конструктора (createteam/…): сцена 140×108 в текстуре 256×128."""
    fe = fe_image(rel)
    return Img(140, 108, ph.crop(bytes(fe.px), fe.w, fe.h, 140, 108))


def catalog(outdir, log=print):
    """Листы элементов конструктора: свитера (10), шорты (6), гетры (12), шрифты (12) — зоны в условных цветах."""
    os.makedirs(outdir, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix='czkit_c_')
    try:
        blocks = []
        for n, (t, v) in enumerate(DESIGNS):
            tm0, tm1, dm = jersey_layers(n)
            cm = detail_over(compose([tm0, tm1], TEST_ZONES), dm)
            nm, _, _ = clean_jersey_maps(t, log=log)
            fr = render_jersey(cm, nm, 0, 330, 270)
            bk = render_jersey(cm, nm, 180, 330, 270)
            fe = fe_crop(f'fe/ion/artassets/createteam/jersey/jersey{n}.big')
            blocks.append(
                f'<div class="col"><h2>jersey{n} <span>jerseyct_{t}_{v} (крой {t}, вариант {v})</span></h2><div class="row">'
                + fig(_uri(cm, tmp, f'j{n}'), 270, 270, 'развёртка: маски зон + детали')
                + fig(_uri(fr, tmp, f'jf{n}'), 330, 270, 'спереди') + fig(_uri(bk, tmp, f'jb{n}'), 330, 270, 'сзади')
                + fig(_uri(fe, tmp, f'jfe{n}'), 140, 108, 'меню конструктора', 'chk') + '</div></div>')
            log(f'  свитер {n}: готово')
        body = (f'<p class="note">Зоны в условных цветах: {swatches(TEST_ZONES, TEST_NAMES)}. Детали (швы, шнуровка, '
                f'ярлыки) — jerseyct_T_V_dm. Нормали — крой T без логотипа конструктора (медиана по логотипам).</p>'
                + ''.join(f'<section>{b}</section>' for b in blocks))
        render_sheet(body, 'Конструктор формы NHL 13: свитера (rendering/czjersey)',
                     os.path.join(outdir, 'cz_jerseys.png'), 1180, 130 + 340 * len(blocks))
        blocks = []
        jtm0, jtm1, jdm = jersey_layers(0)
        jcm = detail_over(compose([jtm0, jtm1], ['#3a3f46'] * 6), jdm)
        for p in range(6):
            tm, dm, nm, sm = pant_layers(p)
            cm = detail_over(compose([tm], TEST_ZONES[:3]), dm)
            fr = render_jersey(jcm, None, 0, 260, 300, pants=(cm, nm))
            bk = render_jersey(jcm, None, 180, 260, 300, pants=(cm, nm))
            fe = fe_crop(f'fe/ion/artassets/createteam/pants/pants{p}.big')
            blocks.append(f'<div class="col"><h2>pants{p} <span>pantct_{p} / czpant_{p}</span></h2><div class="row">'
                          + fig(_uri(cm, tmp, f'p{p}'), 200, 200, 'развёртка')
                          + fig(_uri(fr, tmp, f'pf{p}'), 173, 200, 'спереди')
                          + fig(_uri(bk, tmp, f'pb{p}'), 173, 200, 'сзади')
                          + fig(_uri(fe, tmp, f'pfe{p}'), 140, 108, 'меню', 'chk') + '</div></div>')
            log(f'  шорты {p}: готово')
        sblocks = []
        for s in range(12):
            tm, dm = sock_layers(s)
            cm = detail_over(compose([tm], TEST_ZONES[:3]), dm)
            r = render_sock(resize(cm, 1024, 512), 0, 120, 200)
            extra = ''
            if s < 6:
                extra = fig(_uri(fe_crop(f'fe/ion/artassets/createteam/socks/socks{s}.big'), tmp, f'sfe{s}'),
                            140, 108, 'меню', 'chk')
            sblocks.append(f'<div class="col"><h2>sock{s} <span>sockct_{s}</span></h2><div class="row">'
                           + fig(_uri(cm, tmp, f's{s}'), 160, 160, 'развёртка 512²')
                           + fig(_uri(r, tmp, f'sr{s}'), 96, 160, 'на сетке') + extra + '</div></div>')
        body = (f'<p class="note">Шорты и гетры: 3 зоны {swatches(TEST_ZONES[:3], TEST_NAMES[:3])}; детали — pantct_P_dm, '
                f'sockct_S_dm. Гетры конструктора 512², у EA — 1024×512 (та же раскладка, растянуто по ширине).</p>'
                + '<section><div class="row">' + ''.join(blocks) + '</div></section>'
                + '<section><div class="row">' + ''.join(sblocks) + '</div></section>')
        render_sheet(body, 'Конструктор формы NHL 13: шорты (czpant) и гетры (czsock)',
                     os.path.join(outdir, 'cz_pants_socks.png'), 1780, 1760)
        fblocks = []
        for f in range(12):
            tm, _, _ = font_layers(f)
            img = font_image(tm, ['#F2F2F2', '#C8102E', '#1F4E9C'])
            ok = 'годится' if f in FONT_OK else ('нет czname' if f == 3 else 'одна строка малых цифр')
            extra = ''
            if f < 6:
                extra = fig(_uri(fe_crop(f'fe/ion/artassets/createteam/font/font{f}.big'), tmp, f'ffe{f}'),
                            140, 108, 'меню', 'chk')
            fblocks.append(f'<div class="col"><h2>czfont_{f} <span>{ok}</span></h2><div class="row">'
                           + fig(_uri(half(img), tmp, f'f{f}'), 256, 256, 'атлас (512² — как у EA)', 'chk')
                           + extra + '</div></div>')
        body = (f'<p class="note">Шрифты: заливка (R), обводка (G), вторая обводка (B): '
                f'{swatches(["#F2F2F2", "#C8102E", "#1F4E9C"], ["R", "G", "B"])}. «Годится» — атлас как у EA '
                f'(две строки малых цифр) и есть карта czname.</p>'
                + '<section><div class="row">' + ''.join(fblocks) + '</div></section>')
        render_sheet(body, 'Конструктор формы NHL 13: шрифты номеров (czfont)', os.path.join(outdir, 'cz_fonts.png'),
                     1780, 1180)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------- превью меню (256², как превью EA)

class FePose:
    """Поза превью EA (tools/fepose.py fit): по пикселю превью — точка развёртки свитера (u, v), затенение
    gain/bias по каналам (подогнаны по сотням превью и текстур EA стиля 1, мип 512²), база RGBA (манекен, фон,
    прозрачность) и альфа свитера. Файл — game/work/…/fepose/pose.bin (из арта EA, не в git)."""
    REC = struct.Struct('<ff3f3f4BB')

    def __init__(self, data, path=''):
        if data[:8] != b'FEPOSE1\0':
            raise SystemExit(f'{path}: не модель позы превью (fepose.py)')
        self.path = path
        self.w, self.h = struct.unpack_from('<II', data, 8)
        self.base = bytearray(self.w * self.h * 4)
        self.items = []                                  # (пиксель, u, v, g3, b3, альфа)
        for i, r in enumerate(self.REC.iter_unpack(data[16:16 + self.REC.size * self.w * self.h])):
            self.base[i * 4:i * 4 + 4] = bytes(r[8:12])
            if r[0] >= 0:
                self.items.append((i, r[0], r[1], r[2:5], r[5:8], r[12]))

    @classmethod
    def load(cls, path):
        return cls(open(path, 'rb').read(), path)


def pose_path(game=None):
    """Модель позы для игры: NHL 13 — game/work/uniforms/fepose/pose.bin, NHL Legacy — game/work/legacy-data/fepose/."""
    g = game or ta.game_name()
    import gameprofile
    P = gameprofile.get(g)
    return (os.path.join(P.game, 'work', 'uniforms', 'fepose', 'pose.bin') if g == 'nhl13'
            else P.work_dir('fepose', 'pose.bin'))


def half_img(img):
    """Img вдвое меньше (среднее 2×2) — как мип 1 развёртки, на котором подогнана поза."""
    w, h = img.w // 2, img.h // 2
    s, out = img.px, bytearray(w * h * 4)
    for y in range(h):
        r0, r1 = (2 * y) * img.w * 4, (2 * y + 1) * img.w * 4
        for x in range(w):
            a, b = r0 + 8 * x, r1 + 8 * x
            o = (y * w + x) * 4
            for c in range(4):
                out[o + c] = (s[a + c] + s[a + 4 + c] + s[b + c] + s[b + 4 + c] + 2) // 4
    return Img(w, h, out)


def fe_preview_pose(cm, pose):
    """Превью меню в позе EA: пиксель = gain · свитер(u, v) + bias (развёртка — мип 512²), вне свитера — манекен и фон
    EA (база модели)."""
    tex = cm
    while tex.w > 512:
        tex = half_img(tex)
    out = bytearray(pose.base)
    for i, u, v, g, b, a in pose.items:
        c = _sample(tex, u, v)
        o = i * 4
        for k in range(3):
            x = g[k] * c[k] + b[k]
            out[o + k] = 0 if x < 0 else 255 if x > 255 else int(x + 0.5)
        out[o + 3] = a
    return Img(pose.w, pose.h, out)


def make_fe(cm, nm, ks, log=print):
    """Превью меню комплекта: в позе EA по модели (fepose.py), если она есть; иначе — своя отрисовка сетки."""
    fs = ks.get('fe', {})
    path = fs.get('pose') or pose_path()
    if os.path.exists(path):
        return fe_preview_pose(cm, FePose.load(path))
    log(f'  превью: нет модели позы {path} (tools/fepose.py fit) — своя отрисовка сетки в позе привязки')
    return fe_preview(cm, nm, fs.get('yaw', 14.0))


def _sleeve_ends(m):
    """Середины манжет в позе привязки (рукава вперёд): вершины рук ближе всего к камере (по сторонам)."""
    out = []
    for side in (-1, 1):
        pts = [p for p in m.pos if p[0] * side > 0.3]
        zmax = max(p[2] for p in pts)
        end = [p for p in pts if p[2] > zmax - 0.04]
        out.append([sum(p[k] for p in end) / len(end) for k in range(3)])
    return out


def fe_preview(cm, nm, yaw=14.0, size=256):
    """Превью меню: свитер на сетке EA стиля 1, тёмный манекен (голова, перчатки, шорты с затуханием книзу) — в
    манере превью EA (у них руки опущены; здесь поза привязки сетки — руки согнуты вперёд)."""
    jm, pm = mesh(JERSEY_MESH), mesh(PANT_MESH)
    bx0, by0, bx1, by1 = bounds(jm, yaw)
    k = min(size * 136 / 256 / (by1 - by0), (size - 8) / (bx1 - bx0))   # как у EA: плечи ~64 px, низ ~200 px
    cx = (bx0 + bx1) / 2
    ftop = by1 + size * 64 / 256 / k
    frame = (cx - size / 2 / k, ftop - size / k, cx + size / 2 / k, ftop)
    cam = Camera(yaw, frame, size, size)
    cv = Canvas(size, size)
    dark = (24, 24, 26)
    draw_mesh(cv, cam, pm, None, None, None, color=dark, flat=1.0)
    draw_mesh(cv, cam, jm, cm, nm, tex(*JERSEY_AO))
    # голова и шея — тёмные эллипсы за воротом (z-буфер: рисуются только где свитера нет)
    def blob(c, rx, ry, col, zoff=-0.05):
        sx, sy, sz = cam.screen(c)
        rxp, ryp = rx * cv.w / (frame[2] - frame[0]), ry * cv.h / (frame[3] - frame[1])
        for y in range(max(0, int(sy - ryp)), min(cv.h, int(sy + ryp) + 1)):
            for x in range(max(0, int(sx - rxp)), min(cv.w, int(sx + rxp) + 1)):
                d = ((x + 0.5 - sx) / rxp) ** 2 + ((y + 0.5 - sy) / ryp) ** 2
                if d > 1:
                    continue
                i = y * cv.w + x
                z = sz + zoff
                if z <= cv.z[i]:
                    continue
                cv.z[i] = z
                sh = 0.75 + 0.35 * (1 - d) - 0.25 * ((y - (sy - ryp)) / (2 * ryp))
                o = i * 4
                a = min(1.0, (1 - d) * 6)
                for ch in range(3):
                    cv.px[o + ch] = int(min(255, col[ch] * sh) * a + cv.px[o + ch] * (1 - a))
                cv.px[o + 3] = max(cv.px[o + 3], int(255 * a))
    top = max(p[1] for p in jm.pos)
    blob((0.0, top + 0.045, -0.02), 0.058, 0.06, dark, -0.10)
    blob((0.0, top + 0.135, 0.0), 0.088, 0.105, dark, -0.10)
    for e in _sleeve_ends(jm):
        blob((e[0], e[1] - 0.02, e[2] + 0.03), 0.075, 0.075, dark, 0.5)
    img = cv.img()
    # шорты и низ — затухание книзу, как у EA
    y0 = int(size * 0.80)
    for y in range(y0, size):
        f = max(0.0, 1 - (y - y0) / (size - y0))
        for x in range(size):
            o = (y * size + x) * 4 + 3
            img.px[o] = int(img.px[o] * f)
    return img


# ---------------------------------------------------------------- сборка комплекта по SPEC

def _cal_from(js, cal):
    cal = dict(cal)
    if 'relief' in js:
        cal['strength'] = float(js['relief'])
    if 'relief_sign' in js:
        cal['sign'] = tuple(js['relief_sign'])
    return cal


def make_jersey(js, svgs, palette, log=print):
    t, v = design_tv(js['design'])
    tm0, tm1, dm = jersey_layers(js['design'])
    cm = compose([tm0, tm1], js['zones'], palette)
    detail_over(cm, dm, js.get('detail', 1.0))
    nm, sm512, cal = clean_jersey_maps(t, log=log)
    sm = resize(sm512, 1024, 1024)
    cal = _cal_from(js, cal)
    layers = {'cm': cm, 'sm': sm, 'nm': nm}
    if js.get('logos'):
        kp.apply_logos(layers, js['logos'], svgs, cal, log)
    return layers, cal


def make_pant(ps, svgs, palette, cal, log=print):
    tm, dm, nm, sm = pant_layers(ps['design'])
    cm = compose([tm], ps['zones'], palette)
    detail_over(cm, dm, ps.get('detail', 1.0))
    layers = {'cm': cm, 'sm': sm, 'nm': nm}
    if ps.get('logos'):
        kp.apply_logos(layers, ps['logos'], svgs, _cal_from(ps, cal), log)
    return layers


def make_sock(ss, palette):
    tm, dm = sock_layers(ss['design'])
    cm = compose([tm], ss['zones'], palette)
    detail_over(cm, dm, ss.get('detail', 1.0))
    return resize(cm, 1024, 512)


def make_font(fs, palette):
    tm, nm, sm = font_layers(fs['id'])
    if fs['id'] not in FONT_OK:
        raise SystemExit(f'czfont_{fs["id"]}: атлас не как у EA — для обычного пути не годится')
    img = font_image(tm, fs['zones'], palette)
    cm = half(img)
    fnm = half(nm, normals=True)
    fsm = half(sm)
    return cm, fnm, fsm, name_map(fs.get('name', fs['id']))


def build(spec_path, outdir, only=None, preview=None, work=None, log=print):
    """Комплекты по SPEC → файлы в OUTDIR (раскладка cache:); work — PNG слоёв; preview — лист <team>.png.
    Контейнер другой длины номера, чем у комплекта, заменяется на kitpaint.default_container."""
    spec = ta.load_spec(spec_path)
    base = os.path.dirname(os.path.abspath(spec_path))
    palette = spec.get('colors', {})
    svgs = {k: kp.svg_load(v, base) for k, v in spec.get('svg', {}).items()}
    made, done = [], {}
    for name, ks in spec['kits'].items():
        if only and name not in only:
            continue
        new = kp.Kit.parse(ks['kit'])
        cont = kp.default_container(kp.Kit.parse(ks.get('container', spec.get('container', '1_28_0'))), new)
        log(f'{spec.get("team", "")} {name}: {new} (контейнер {cont})')
        js = ks['jersey']
        jl, cal = make_jersey(js, svgs, palette, log)
        log(f'  свитер: jersey{js["design"]} = jerseyct_{"_".join(map(str, design_tv(js["design"])))}')
        fcm, fnm, fsm, nmap = make_font(ks['font'], palette)
        log(f'  шрифт: czfont_{ks["font"]["id"]}, карта czname_{ks["font"].get("name", ks["font"]["id"])}')
        ps = ks['pant']
        if 'same_as' in ps:
            pl = done[ps['same_as']]['pant']
            log(f'  шорты: как у {ps["same_as"]}')
        else:
            pl = make_pant(ps, svgs, palette, cal, log)
            log(f'  шорты: pants{ps["design"]}')
        scm = make_sock(ks['sock'], palette)
        log(f'  гетры: sock{ks["sock"]["design"]}')
        fe = make_fe(jl['cm'], jl['nm'], ks, log)
        layers = {'jersey_cm': jl['cm'], 'jersey_sm': jl['sm'], 'jersey_nm': jl['nm'],
                  'font_cm': fcm, 'font_nm': fnm, 'font_sm': fsm, 'name_cm': nmap,
                  'pant_cm': pl['cm'], 'pant_nm': pl['nm'], 'pant_sm': pl['sm'], 'sock_cm': scm, 'fe': fe}
        done[name] = {'pant': pl}
        if work:
            d = os.path.join(work, f'{spec.get("team", "kit")}_{name}')
            os.makedirs(d, exist_ok=True)
            for ln, img in layers.items():
                img.save(os.path.join(d, ln + '.png'))
        res = kp.build_kit(cont, new, {k: v.tup() for k, v in layers.items()}, outdir, log=log)
        made += list(res)
    if preview:
        out = os.path.join(preview, f'{spec.get("team", "kits")}.png')
        sheet(spec_path, outdir, out, only, log=log)
    return made


# ---------------------------------------------------------------- лист превью клуба

def rebuild_fe(spec_path, outdir, only=None, pose=None, log=print):
    """Только превью меню уже собранных комплектов SPEC: развёртка свитера — из файла OUTDIR (мип 512², как её
    видит игра), превью — в позе EA (FePose), контейнер превью — сам файл OUTDIR (меняются только пиксели)."""
    spec = ta.load_spec(spec_path)
    pose = FePose.load(pose or pose_path())
    made = []
    for name, ks in spec['kits'].items():
        if only and name not in only:
            continue
        kit = kp.Kit.parse(ks['kit'])
        rel_t, rel_f = kit.path('jersey'), kit.path('fe')
        rw = ta.Rw4(open(os.path.join(outdir, *rel_t.split('/')), 'rb').read(), rel_t)
        t = next(x for x in rw.textures if kp.layer_name(x.name) == 'jersey_cm')
        cm = Img(*kp.tex_decode(rw, t, 1))
        fe = fe_preview_pose(cm, pose)
        fp = os.path.join(outdir, *rel_f.split('/'))
        u = ta.UiLogo(open(fp, 'rb').read(), rel_f)
        data = u.build(bytes(fe.px), 'md5')
        open(fp, 'wb').write(data)
        log(f'{spec.get("team", "")} {name}: {rel_f} — превью в позе EA ({os.path.basename(pose.path)}), {len(data)} байт')
        made.append(rel_f)
    return made


def kit_layers(outdir, kit):
    """Слои собранного комплекта из файлов (как их увидит игра — после сжатия): {слой: Img}."""
    out = {}
    for kind in ('jersey', 'name', 'pant', 'sock'):
        rw = ta.Rw4(open(os.path.join(outdir, *kit.path(kind).split('/')), 'rb').read())
        for t in rw.textures:
            out[kp.layer_name(t.name)] = Img(*kp.tex_decode(rw, t, 0))
    out['fe'] = Img(*ta.UiLogo(open(os.path.join(outdir, *kit.path('fe').split('/')), 'rb').read()).decode())
    return out


def _desc(ks, palette):
    js, fs, ps, ss = ks['jersey'], ks['font'], ks['pant'], ks['sock']
    t, v = design_tv(js['design'])

    def sw(cols):
        return ''.join(f'<span class="sw" style="background:{kp_hex(c, palette)}"></span>{c}' for c in cols)
    parts = [f'свитер <b>jersey{js["design"]}</b> (jerseyct_{t}_{v}): {sw(js["zones"])}',
             f'шрифт <b>czfont_{fs["id"]}</b>: {sw(fs["zones"])}']
    if 'same_as' in ps:
        parts.append(f'шорты — как у «{ps["same_as"]}»')
    else:
        parts.append(f'шорты <b>pants{ps["design"]}</b>: {sw(ps["zones"])}')
    parts.append(f'гетры <b>sock{ss["design"]}</b>: {sw(ss["zones"])}')
    return '<br>'.join(parts)


def kp_hex(c, palette):
    r, g, b = kp.parse_color(c, palette)
    return f'#{r:02X}{g:02X}{b:02X}'


def sheet(spec_path, outdir, out_png, only=None, log=print):
    """Лист клуба: на комплект — вид спереди/сзади (с примером номера), развёртка свитера, превью меню, шрифт, шорты,
    гетры; подписи — элементы конструктора и цвета зон."""
    import html as H
    spec = ta.load_spec(spec_path)
    palette = spec.get('colors', {})
    tmp = tempfile.mkdtemp(prefix='czkit_s_')
    cnt = [0]

    def u(_k, img):
        cnt[0] += 1
        return _uri(img, tmp, f'i{cnt[0]}')
    try:
        blocks = []
        for n, (name, ks) in enumerate(spec['kits'].items()):
            if only and name not in only:
                continue
            kit = kp.Kit.parse(ks['kit'])
            L = kit_layers(outdir, kit)
            smp = ks.get('sample', spec.get('sample', {}))
            cmn = stamp_sample(L['jersey_cm'], L['font_cm'], L['name_cm'], str(smp.get('number', '19')),
                               smp.get('name', ''), smp.get('captain'))
            pants = (L['pant_cm'], L['pant_nm'])
            fr = render_jersey(cmn, L['jersey_nm'], 8, 470, 420, pants=pants)
            bk = render_jersey(cmn, L['jersey_nm'], 180, 470, 420, pants=pants)
            sk = render_sock(L['sock_cm'], 0, 150, 260)
            blocks.append(
                f'<section><h2>{H.escape(ks.get("label", name))} <span>{H.escape(kit.path("jersey").split("/")[-1])} · '
                f'файлы *_{kit.tag()}*</span></h2>'
                f'<p class="note" style="margin:0 0 6px">{_desc(ks, palette)}</p><div class="row">'
                + fig(u('fr', fr), 470, 420, 'спереди (сетка EA стиля 1, поза привязки; шорты — свои)')
                + fig(u('bk', bk), 470, 420, 'сзади (номер и фамилия — пример, ставит шейдер по карте czname)')
                + '<div class="col">' + fig(u('fe', L['fe']), 256, 256, 'превью в меню (256²)', 'chk')
                + fig(u('font', L['font_cm']), 256, 256, 'шрифт номеров (512²)', 'chk') + '</div>'
                + '<div class="col">' + fig(u('cm', L['jersey_cm']), 300, 300, 'развёртка свитера (1024²)')
                + fig(u('pant', L['pant_cm']), 150, 150, 'шорты (512²)') + '</div>'
                + '<div class="col">' + fig(u('sk', sk), 150, 260, 'гетры на сетке')
                + fig(u('sock', L['sock_cm']), 150, 75, 'гетры (1024×512)') + '</div>'
                + '</div></section>')
            log(f'  лист: {name}')
        cand = spec.get('candidates')
        if cand:
            cb = []
            for i, c in enumerate(cand):
                jl, _ = make_jersey(c['jersey'], {}, palette, log=None)
                img = render_jersey(jl['cm'], jl['nm'], 8, 300, 250)
                cb.append(fig(u(f'cand{i}', img), 300, 250, c.get('label', '')))
            blocks.append('<section><h2>Другие варианты (только образцы, файлов нет)</h2><div class="row">'
                          + ''.join(cb) + '</div></section>')
        note = spec.get('note', '')
        body = (f'<p class="note">{H.escape(note)}</p>' if note else '') + ''.join(blocks)
        hh = 100 + 700 * sum(1 for k in spec["kits"] if not only or k in only) + (380 if cand else 0) + (50 if note else 0)
        render_sheet(body, spec.get('title', spec.get('team', '')), out_png, 1780, hh)
        log(f'лист превью: {out_png}')
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return out_png


# ---------------------------------------------------------------- команды

def main():
    game, argv = ta.split_game(sys.argv[1:])
    if len(argv) < 2:
        sys.exit(__doc__)
    ta.set_game(game)
    cmd, args = argv[0], argv[1:]
    if cmd == 'catalog':
        catalog(args[0])
    elif cmd == 'build':
        only = args[args.index('--kits') + 1].split(',') if '--kits' in args else None
        work = args[args.index('--work') + 1] if '--work' in args else None
        preview = args[args.index('--preview') + 1] if '--preview' in args else None
        made = build(args[0], args[1], only, preview, work)
        print(f'файлов: {len(made)}')
    elif cmd == 'sheet':
        only = args[args.index('--kits') + 1].split(',') if '--kits' in args else None
        sheet(args[0], args[1], args[2], only)
    elif cmd == 'fe':
        only = args[args.index('--kits') + 1].split(',') if '--kits' in args else None
        pose = args[args.index('--pose') + 1] if '--pose' in args else None
        made = rebuild_fe(args[0], args[1], only, pose)
        if '--preview' in args:
            spec = ta.load_spec(args[0])
            d = args[args.index('--preview') + 1]
            sheet(args[0], args[1], os.path.join(d, f'{spec.get("team", "kits")}.png'), only)
        print(f'превью: {len(made)}')
    elif cmd == 'verify':
        outdir, bad = args[0], 0
        for pair in args[1:]:
            a, b = pair.split('=')
            new, cont = kp.Kit.parse(a), kp.Kit.parse(b)
            print(f'комплект {new} (контейнер {cont}):')
            bad += kp.verify(outdir, new, cont)
        print('итог:', 'OK' if not bad else f'ошибок {bad}')
        sys.exit(1 if bad else 0)
    else:
        sys.exit(__doc__)


if __name__ == '__main__':
    main()
