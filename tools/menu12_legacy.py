"""Главное меню NHL 12 в NHL Legacy: файлы для cache: Legacy (фон с игроками, вид списка меню).

    python menu12_legacy.py build [--from DIR] [--db DB] [--spec SPEC] [--work DIR] [--no-out]
                                  [--keep-fade] [--no-list] [--no-players] [--no-underlay]
        # DIR — сборка tools/menu12.py для NHL 13 (по умолчанию game/work/menu12/out/nhl12, то, что ставит
        #   install-menu12.sh; вариант арены «в нашем цвете» — game/work/menu12/out/tint-245C99): оттуда фон
        #   NHL 12 с правками menu12 (bg_edits, проезды) и 72 картинки игроков и легенд — без пересборки.
        # Собирается в WORK (game/work/legacy-data/menu/build, раскладка cache:, имена строчные, как в архивах
        # Legacy) и копируется в game/work/legacy-data/out; список своих файлов — game/work/legacy-data/menu/files.txt:
        #   fe/ion/game/background/nhlmainmenubackground.big — фон NHL 12; кольца света — цвет клуба игрока
        #       места по базе Legacy (DB, по умолчанию out/db/nhlng.db; клуб места — из SPEC menu12);
        #   fe/ion/game/components/menu.big — список меню Legacy (его код: заголовки, картинки пунктов, метки
        #       «New», значок паков) с металлической косой плашкой NHL 12 вместо своей (плашка-гибрид: полоса и
        #       косые края NHL 12 + кнопка A, метка «New» и стрелка подменю Legacy), невыделенные пункты ×0,735
        #       (25/34), ряды 28/45 (у NHL 12 и 13; у Legacy 23/40), сдвиг выделенного 10, без затухания пунктов
        #       по удалению от выделенного (--keep-fade — оставить); кубок с табличкой в подменю ×6 % (у Legacy
        #       ×20 %: подзаголовок подменю от 8 пунктов ложится на табличку LEGACY EDITION);
        #   fe/ion/main.big — шрифт пунктов 34 (у Legacy 22), тень выделенного #DDDDDD, mDisabledAlpha 50;
        #   fe/ion/artassets/backgrounds/mainmenu{players,legends}{,blur}/nhl<N>.big — игроки menu12;
        #   fe/ion/game/background/nhlbluebackground.big — «цветной фон» под всеми меню (синяя подложка mcColor и
        #       фото-арена Legacy поверх): на главном меню фото-арена больше не сжимается в «телевизор» студии
        #       Legacy (INACTIVE_* = ACTIVE_*) и не открывает синюю подложку, пока въезжает и проявляется арена
        #       NHL 12; сама подложка — почти чёрная (--no-underlay — не класть).
    python menu12_legacy.py check [DIR]        # разбор собранного (DIR — WORK): правки байткода, сверка с
                                               # оригиналами (вне правок байты те же), плашка
    python menu12_legacy.py mockup [DIR] [--out PNG]   # примерный вид плашки и пунктов (Pillow; не снимок игры)

Почему так и что проверить в игре — docs/fe-menu-legacy.md. Функции правок — из tools/menu12.py,
tools/feapt.py, tools/menuplayers.py (их файлы не меняются). Только стандартная библиотека (mockup — Pillow).
"""
import json, os, shutil, struct, sys

TOOLS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TOOLS)
import playerhead as ph    # noqa: E402  (BIGF, RefPack)
import febg                # noqa: E402  (FeMovie, build_bigf)
import feapt               # noqa: E402  (байткод, graft, patch_bytes)
import menu12              # noqa: E402  (bg_edits, menu_edits, find_seq, пути NHL 12)
import menuplayers         # noqa: E402  (места фона, цвета клубов, ring_color)
import gameprofile         # noqa: E402

P = gameprofile.get('legacy')
GAME = P.game
WORK = P.work_dir('menu', 'build')
FILES = P.work_dir('menu', 'files.txt')
FROM = os.path.join(GAME, 'work', 'menu12', 'out', 'nhl12')
SPEC = os.path.join(GAME, 'work', 'menu12', 'players', 'spec.json')
DB = os.path.join(P.out, 'db', 'nhlng.db')

BG = menu12.BG                                   # fe/ion/game/background/nhlmainmenubackground.big
MENU = menu12.MENU                               # fe/ion/game/components/menu.big
MAIN = menu12.MAIN                               # fe/ion/main.big
PLAYER_DIRS = ('mainmenuplayers', 'mainmenuplayersblur', 'mainmenulegends', 'mainmenulegendsblur')
N12_MMN = menu12.p(menu12.N12, 'boot/' + menu12.MAINMENUNEW12)
N12_SELECTOR = 69                                # mainMenuNew NHL 12: selectorBG (left 0, center 24, right 276)

# вид списка NHL 12 (MenuOptions NHL 12: 34 выделенный / 25 остальные; ряды 45/28)
SIZE = 34
UNHIGHLIGHT = 0.735                              # 25/34
ROWS = {'ROW_SIZE_UNHIGHLIGHTED': (23, 28), 'ROW_SIZE_HIGHLIGHTED': (40, 45)}
HIGHLIGHT_OFFSET = (8, 10)                       # Menu: выделенный пункт выше своего ряда (равные просветы)
FADE = {'TXT_ALPHA_START': (80, 100), 'TXT_ALPHA_DECREMENT': (10, 0)}   # затухание пунктов Legacy → нет

# плашка-гибрид (координаты символа selectorBG; он стоит в пункте на (−29, 1), у NHL 13 — на (−17, 1)).
# Код Legacy делает center._width = HIGHLIGHT_WIDTH (327), mcNewIcon._x = 327, mcMenuArrow._x = 317 и правый
# край не двигает (у NHL 13 — двигает): полоса NHL 12 — там же, где полоса Legacy (0…327), косые края
# снаружи. Видимая часть полосы NHL 12 — строки 0…37 из 39; её середина на уровне середины прописных
# пунктов 34 (поле текста Legacy на 11 выше, чем у NHL 13: (2, −9) против (2, 2)) → −11; элементы Legacy
# (кнопка A, метка «New», стрелка) — на ту же величину, что середина полосы: 0,5 → 7,5.
SEL_DY = -11
SEL_LEGACY_DY = 7
FEATURE_FADED = (20, 6)                          # кубок в подменю: яркость 20 % → 6 % (faded_image_edits)

# «цветной фон» (NHLBlueBackground, boot.big; у Legacy и NHL 13 побайтно один): подложка mcColor (Shape 1,
# заливка #0A09E1) и mcBackground — фото-арена Legacy (NHLBlueBackgroundComponents, cacheboot.big). При входе в
# грань MENU код сжимает mcBackground до INACTIVE_* (30 % в точке телевизора студии Legacy), при выходе —
# возвращает ACTIVE_*. У фона NHL 12 телевизора нет: сжатие только открывало синюю подложку, пока арена NHL 12
# въезжает (переход граней) и проявляется (_alpha 0 → 100 за m_speedZoomIn). Теперь INACTIVE = ACTIVE: под
# главным меню — та же тёмная арена Legacy, что под остальными меню; подложка — почти чёрная (если что-то её
# всё же откроет).
UNDERLAY = 'fe/ion/game/background/nhlbluebackground.big'
UNDERLAY_CONSTS = {'INACTIVE_X_POS': (166, 0), 'INACTIVE_Y_POS': (-73, 0),
                   'INACTIVE_X_SCALE': (30, 100), 'INACTIVE_Y_SCALE': (30, 100)}
UNDERLAY_SHAPE = 1                               # mcColor
UNDERLAY_COLOR = (0xFF0A09E1, 0xFF07080A)


def p(root, rel):
    return os.path.join(root, *rel.split('/'))


def u32(b, o):
    return struct.unpack_from('>I', b, o)[0]


def opt(args, name, default=None):
    return args[args.index(name) + 1] if name in args else default


def log(*a):
    print(*a, flush=True)


# ---------------------------------------------------------------- оригиналы Legacy

def legacy_src(rel):
    f = P.extracted(rel)
    if not f:
        raise SystemExit(f'нет {rel} в распакованных архивах Legacy ({P.big})')
    return f


# ---------------------------------------------------------------- правки байткода

def flat_code(code, off):
    out = []

    def walk(lst):
        for i in lst:
            out.append(i)
            if i.body:
                walk(i.body)
    walk(code.parse(off))
    return out


def const_edits(path, block, values):
    """Константы класса: «PushConstant/PushWordConstant ИМЯ, Push… значение, SetMember» в InitAction блока
    block (подстрока заголовка) → [(смещение, старые, новые)]; values — {ИМЯ: (было, стало)}."""
    mv, consts = feapt.load_movie(path)
    code = feapt.Code(mv.apt.data, consts)
    edits, seen = [], set()
    for title, off in feapt.code_blocks(mv):
        if block not in title:
            continue
        fl = flat_code(code, off)
        for k in range(len(fl) - 2):
            a, v, s = fl[k], fl[k + 1], fl[k + 2]
            if a.name not in ('PushConstant', 'PushWordConstant') or a.args[0] not in values or s.name != 'SetMember':
                continue
            old, new = values[a.args[0]]
            if v.name == 'PushFloat' and isinstance(old, float):
                if abs(v.args[0] - old) > 1e-6:
                    raise SystemExit(f'{a.args[0]}: {v.args[0]}, ждали {old}')
                edits.append((v.off + 1, struct.pack('>f', v.args[0]), struct.pack('>f', new)))
            elif v.name == 'PushByte' and not isinstance(old, float):
                got = v.args[0] - 256 if v.args[0] >= 128 else v.args[0]          # PushByte — со знаком
                if got != old or not -128 <= new <= 127:
                    raise SystemExit(f'{a.args[0]}: {got}, ждали {old} (новое {new})')
                edits.append((v.off + 1, bytes([old & 255]), bytes([new & 255])))
            elif v.name == 'PushShort' and not isinstance(old, float):
                got = v.args[0] - 65536 if v.args[0] >= 32768 else v.args[0]      # PushShort — тоже со знаком
                if got != old or not -32768 <= new <= 32767:
                    raise SystemExit(f'{a.args[0]}: {got}, ждали {old} (новое {new})')
                edits.append((v.off + 1, struct.pack('>h', old), struct.pack('>h', new)))
            else:
                raise SystemExit(f'{a.args[0]}: {v.name} {v.args} — не та команда')
            seen.add(a.args[0])
    missing = set(values) - seen
    if missing:
        raise SystemExit(f'{os.path.basename(path)}: не найдены {", ".join(sorted(missing))} в «{block}»')
    if len(edits) != len(values):
        raise SystemExit(f'{os.path.basename(path)}: найдено {len(edits)} мест на {len(values)} констант')
    return edits


def menu_list_edits(path, keep_fade=False):
    """menu.big Legacy: масштаб невыделенных, ряды, сдвиг выделенного, затухание, затемнение кубка в подменю."""
    edits = const_edits(path, '__Packages.game.components.classes.MenuItem»',
                        {'UNHIGHLIGHTING_SCALE': (0.800000011920929, UNHIGHLIGHT)})
    vals = dict(ROWS)
    vals['HIGHLIGHT_OFFSET'] = HIGHLIGHT_OFFSET
    if not keep_fade:
        vals.update(FADE)
    edits += const_edits(path, '__Packages.game.components.classes.Menu»', vals)
    edits += faded_image_edits(path)
    return edits


def faded_image_edits(path, values=None):
    """Menu.SetFeatureImageFaded(true) — картинка пункта (кубок с табличкой LEGACY EDITION) в подменю: цвет ×20 %
    → FEATURE_FADED. Подзаголовок подменю стоит на 35 выше списка, а список растёт вверх; с рядами 28/45 у
    списков от 8 пунктов (SETTINGS — 9, лиги Team Rosters — 11, хаб Be a GM — 9) он ложится на табличку и
    надпись NHL кубка. Почти чёрный кубок в подменю (как у NHL 12, где кубка нет) — без наложения при любой длине."""
    old, new = values or FEATURE_FADED
    mv, consts = feapt.load_movie(path)
    code = feapt.Code(mv.apt.data, consts)
    found = []
    for title, off in feapt.code_blocks(mv):
        if '__Packages.game.components.classes.Menu»' not in title:
            continue
        fl = flat_code(code, off)
        for k in range(1, len(fl)):
            f = fl[k]
            if f.name == 'DefineFunction2' and fl[k - 1].name in ('PushConstant', 'PushWordConstant') \
                    and fl[k - 1].args[0] == 'SetFeatureImageFaded' and f.body:
                body = f.body
                for j in range(len(body) - 1):
                    if body[j].name == 'PushByte' and body[j].args[0] == old and body[j + 1].name == 'SetRegister':
                        found.append((body[j].off + 1, bytes([old]), bytes([new])))
    if len(found) != 1:
        raise SystemExit(f'menu.big: SetFeatureImageFaded — найдено {len(found)} мест «PushByte {old}», ждали 1')
    return found


def main_edits(path, old=22, new=SIZE):
    """main.big Legacy, GetCustomMenuOptions: кегль 22 → 34 у четырёх форматов пунктов, тень выделенного
    #FFFFFF → #DDDDDD, mDisabledAlpha 30 → 50 (как menu12.main_edits у NHL 13, где было 24)."""
    mv, consts = feapt.load_movie(path)
    code = feapt.Code(mv.apt.data, consts)
    edits = []
    names = ('mItemTextFormat', 'mItemDropTextFormat', 'mHighlightedItemTextFormat', 'mHighlightedItemDropTextFormat')
    for title, off in feapt.code_blocks(mv):
        fl = flat_code(code, off)
        for k, i in enumerate(fl):
            if i.name == 'PushString' and i.args[0] in names and k + 3 < len(fl):
                col, size, font = fl[k + 1], fl[k + 2], fl[k + 3]
                if font.name != 'PushString' or font.args[0] != 'EA HelveticaNeue Hv' or size.name != 'PushByte':
                    continue
                if size.args[0] == old:
                    edits.append((size.off + 1, bytes([old]), bytes([new])))
                if i.args[0] == 'mHighlightedItemDropTextFormat' and col.name == 'PushLong' and col.args[0] == 0xFFFFFF:
                    edits.append((col.off + 1, struct.pack('>I', 0xFFFFFF), struct.pack('>I', 0xDDDDDD)))
            if i.name == 'PushString' and i.args[0] == 'mDisabledAlpha' and k + 1 < len(fl) \
                    and fl[k + 1].name == 'PushByte' and fl[k + 1].args[0] == 30:
                edits.append((fl[k + 1].off + 1, bytes([30]), bytes([50])))
    if len(edits) != 6:
        raise SystemExit(f'main.big: ожидалось 6 правок, найдено {len(edits)} — другой файл?')
    return edits


def underlay_edits(path):
    """nhlbluebackground.big: INACTIVE_* → значения ACTIVE_* (4 константы класса NHLBlueBackground)."""
    return const_edits(path, '__Packages.game.background.NHLBlueBackground»', UNDERLAY_CONSTS)


def underlay_fill(mv):
    """(запись BIGF, смещение слова цвета в геометрии) заливки-цвета подложки mcColor."""
    fills = [fl for mesh in mv.geometry.get(UNDERLAY_SHAPE, []) for fl in mesh if fl.type == febg.FILL_SOLID]
    if len(fills) != 1:
        raise SystemExit(f'{UNDERLAY}: у Shape {UNDERLAY_SHAPE} заливок-цвета {len(fills)}, ждали 1 — другой файл?')
    return str(UNDERLAY_SHAPE + 1), fills[0]


def build_underlay(src, dst):
    """Правки «цветного фона»: константы INACTIVE_* (байткод той же длины) и цвет подложки (слово заливки)."""
    tmp = dst + '.tmp'
    feapt.patch_bytes(src, tmp, underlay_edits(src), log=lambda *a: None)
    mv = febg.FeMovie.load(tmp)
    key, fl = underlay_fill(mv)
    old, new = UNDERLAY_COLOR
    if fl.color != old:
        raise SystemExit(f'{UNDERLAY}: цвет подложки {fl.color:08X}, ждали {old:08X}')
    g, packed = mv.raw[key]
    g = bytearray(g)
    struct.pack_into('>I', g, fl.off + 0x10, new)
    big = ph.Bigf(mv.big.raw)
    big.put(key, febg.pack_like(bytes(g), packed))
    out = febg.build_bigf(big)
    febg.FeMovie(out)                                            # разбирается обратно
    open(dst, 'wb').write(out)
    os.remove(tmp)


# ---------------------------------------------------------------- плашка-гибрид

def sprite_items(apt, idx):
    """PlaceObject кадра 0 спрайта idx: [(глубина, имя, символ, смещение записи)]."""
    ch = apt.chars[idx]
    if ch.type != 5 or len(ch.frames) != 1:
        raise SystemExit(f'символ {idx}: не спрайт из одного кадра')
    return [(it.po.depth, it.po.name, it.po.char, it.off) for it in ch.frames[0] if it.po]


def hybrid_selector(path, n12_sel, out_path, legacy_sel_name='selectorBG'):
    """В ролике path (menu.big Legacy после graft NHL 12 selectorBG под номером n12_sel) — новый спрайт:
    полоса и косые края NHL 12 (center/right/left, сдвиги — см. SEL_DY) + кнопка A, mcNewIcon, mcMenuArrow
    из selectorBG Legacy; экспорт selectorBG → он. Старые символы не меняются, новое — в конец Apt Data."""
    mv = febg.FeMovie.load(path)
    a = mv.apt
    d = bytearray(a.data)
    exports = {n.lower(): i for n, i in a.exports}
    # selectorBG Legacy — тот, на кого экспорт указывал в оригинале (graft его уже перенаправил на n12_sel)
    orig = febg.FeMovie.load(legacy_src(MENU)).apt
    leg_idx = {n.lower(): i for n, i in orig.exports}[legacy_sel_name.lower()]
    if exports.get(legacy_sel_name.lower()) != n12_sel:
        raise SystemExit(f'экспорт {legacy_sel_name} → {exports.get(legacy_sel_name.lower())}, ждали {n12_sel}')
    width = None
    mvc, consts = feapt.load_movie(path)
    code = feapt.Code(mvc.apt.data, consts)
    for title, off in feapt.code_blocks(mvc):
        if '__Packages.game.components.classes.MenuItem»' in title:
            fl = flat_code(code, off)
            for k in range(len(fl) - 1):
                if fl[k].name in ('PushConstant', 'PushWordConstant') and fl[k].args[0] == 'HIGHLIGHT_WIDTH':
                    width = fl[k + 1].args[0]
    if not width:
        raise SystemExit('MenuItem.HIGHLIGHT_WIDTH не найден')
    n12 = {name: (depth, char, off) for depth, name, char, off in sprite_items(a, n12_sel)}
    leg = sprite_items(a, leg_idx)
    if set(n12) != {'center', 'right', 'left'}:
        raise SystemExit(f'плашка NHL 12: {sorted(n12)}')
    names = {name for _, name, _, _ in leg}
    if not {'center', 'mcNewIcon', 'mcMenuArrow'} <= names:
        raise SystemExit(f'плашка Legacy: {sorted(names)}')
    # ширина косого левого края NHL 12 — по рамке его фигуры
    lshape = a.chars[a.chars[n12['left'][1]].frames[0][0].po.char]
    left_w = lshape.bounds[2] - lshape.bounds[0]

    def rec(off, depth, tx=None, ty=None, dy=0.0):
        r = bytearray(d[off:off + 0x40])
        struct.pack_into('>I', r, 8, depth)
        if tx is not None:
            struct.pack_into('>f', r, 0x20, tx)
        if ty is not None:
            struct.pack_into('>f', r, 0x24, ty)
        if dy:
            struct.pack_into('>f', r, 0x24, struct.unpack_from('>f', r, 0x24)[0] + dy)
        return bytes(r)

    items = [rec(n12['center'][2], 1, 0.0, SEL_DY),
             rec(n12['right'][2], 2, float(width), SEL_DY),
             rec(n12['left'][2], 4, -float(left_w), SEL_DY)]
    plan = [('center NHL 12', 1, 0, SEL_DY), ('right NHL 12', 2, width, SEL_DY), ('left NHL 12', 4, -left_w, SEL_DY)]
    for depth, name, char, off in leg:
        if name == 'center':
            continue                                   # полоса Legacy → полоса NHL 12
        items.append(rec(off, depth, dy=SEL_LEGACY_DY))
        y = struct.unpack_from('>f', d, off + 0x24)[0] + SEL_LEGACY_DY
        plan.append((f'{name or "символ " + str(char)} Legacy', depth, struct.unpack_from('>f', d, off + 0x20)[0], y))
    items.sort(key=lambda r: u32(r, 8))
    depths = [u32(r, 8) for r in items]
    if len(set(depths)) != len(depths):
        raise SystemExit(f'глубины плашки повторяются: {depths}')

    def align():
        while len(d) % 4:
            d.append(0)
    ptrs = []
    for r in items:
        align()
        ptrs.append(len(d))
        d.extend(r)
    align()
    arr = len(d)
    for q in ptrs:
        d.extend(struct.pack('>I', q))
    align()
    ftab = len(d)
    d.extend(struct.pack('>II', len(ptrs), arr))
    align()
    sp = len(d)
    raw = bytearray(d[a.chars[leg_idx].off:a.chars[leg_idx].off + 0x1C])        # Sprite Legacy как образец
    struct.pack_into('>III', raw, 0x10, 1, ftab, 0)
    d.extend(raw)
    # таблица символов (старые + новый) и экспорт
    m = a.movie_off
    nchar, cp = struct.unpack_from('>II', d, m + 0x1C)
    align()
    tab = len(d)
    for i in range(nchar):
        d.extend(struct.pack('>I', u32(d, cp + 4 * i)))
    d.extend(struct.pack('>I', sp))
    new_idx = nchar
    struct.pack_into('>II', d, m + 0x1C, nchar + 1, tab)
    ne, ep = struct.unpack_from('>II', d, m + 0x38)
    hit = 0
    for k in range(ne):
        if feapt.cstr(d, u32(d, ep + 8 * k)).lower() == legacy_sel_name.lower():
            struct.pack_into('>I', d, ep + 8 * k + 4, new_idx)
            hit += 1
    if hit != 1:
        raise SystemExit(f'экспорт {legacy_sel_name}: {hit} записей')
    big = ph.Bigf(mv.big.raw)
    big.put('0', ph.refpack_compress(bytes(d)) if mv.raw['0'][1] else bytes(d))
    data = febg.build_bigf(big)
    febg.FeMovie(data)
    open(out_path, 'wb').write(data)
    return new_idx, plan


# ---------------------------------------------------------------- фон: цвета колец по базе Legacy

def ring_edits(bg, spec_path, db_path, log=log):
    """Цвета колец мест m_backgroundPlayers: клуб места — из spec menu12, цвет — menuplayers.ring_color по
    exhibitionteams базы Legacy (строки НХЛ 0…31 те же, SEA 30, VGK 31). Сверка: цвет в фоне menu12 должен
    быть цветом того же клуба по базе NHL 13 (иначе spec не от этой сборки — предупреждение)."""
    spec = json.load(open(spec_path, encoding='utf-8'))
    by_slot = {e['slot']: e for e in spec['players']}
    leg = menuplayers.team_colors(db_path)
    try:
        n13 = menuplayers.team_colors()
    except Exception as e:                                   # noqa: BLE001
        n13 = None
        log(f'  (база NHL 13 не прочитана — сверки с menu12 нет: {e})')
    edits, report, warn = [], [], 0
    for s in menuplayers.slots_of(bg):
        if s['list'] != 'm_backgroundPlayers':
            continue
        e = by_slot.get(s['asset'])
        if e is None or s['color_off'] is None:
            raise SystemExit(f'место {s["asset"]}: нет в {spec_path} или цвет не PushLong')
        auto = e.get('color', 'auto') == 'auto'
        if auto:
            if e['team'] not in leg:
                raise SystemExit(f'место {s["asset"]}: клуба {e["team"]} нет среди НХЛ 0…31')
            new = menuplayers.ring_color(*leg[e['team']])
        else:
            new = int(e['color'], 16)
        note = ''
        if auto and n13 is not None:
            want = menuplayers.ring_color(*n13[e['team']])
            if want != s['color']:
                note = f'  !! в фоне menu12 #{s["color"]:06X}, у {e["team"]} по базе NHL 13 #{want:06X}'
                warn += 1
        if new != s['color']:
            edits.append((s['color_off'] + 1, struct.pack('>I', s['color'] & 0xFFFFFFFF), struct.pack('>I', new)))
        report.append(f'  место {s["asset"]:2d}: {e["name"]:24s} {e["team"]}  #{s["color"]:06X} → #{new:06X}{note}')
    report.sort(key=lambda x: int(x.split(':')[0].split()[-1]))
    return edits, report, warn


# ---------------------------------------------------------------- сборка

def cmd_build(args):
    src = opt(args, '--from', FROM)
    work = opt(args, '--work', WORK)
    db = opt(args, '--db', DB)
    spec = opt(args, '--spec', SPEC)
    keep_fade = '--keep-fade' in args
    if os.path.isdir(work):
        shutil.rmtree(work)
    os.makedirs(work)
    built = []
    lines = [f'menu12_legacy build: из {src}', f'база колец: {db}', f'spec: {spec}']
    # фон
    sbg = p(src, BG)
    if not os.path.exists(sbg):
        raise SystemExit(f'нет фона {sbg} (сборка menu12)')
    dbg = p(work, BG)
    os.makedirs(os.path.dirname(dbg), exist_ok=True)
    tmp = dbg + '.tmp'
    if menu12.feapt_already_patched(sbg):
        shutil.copyfile(sbg, tmp)
        lines.append('фон: правки порядка событий (bg_edits) уже есть')
    else:
        feapt.patch_bytes(sbg, tmp, menu12.bg_edits(sbg), log=lambda *a: None)
        lines.append('фон: bg_edits применены здесь')
    edits, report, warn = ring_edits(tmp, spec, db)
    feapt.patch_bytes(tmp, dbg, edits, log=lambda *a: None)
    os.remove(tmp)
    lines.append(f'фон: кольца по базе Legacy — {len(edits)} правок PushLong' + (f', ПРЕДУПРЕЖДЕНИЙ {warn}' if warn else ''))
    lines += report
    built.append(BG)
    # игроки
    if '--no-players' not in args:
        n = 0
        for sub in PLAYER_DIRS:
            sd = p(src, f'fe/ion/artassets/backgrounds/{sub}')
            if not os.path.isdir(sd):
                raise SystemExit(f'нет {sd}')
            dd = p(work, f'fe/ion/artassets/backgrounds/{sub}')
            os.makedirs(dd, exist_ok=True)
            for f in sorted(os.listdir(sd)):
                if f.endswith('.big'):
                    febg.FeMovie.load(os.path.join(sd, f))          # целый ли ролик
                    shutil.copyfile(os.path.join(sd, f), os.path.join(dd, f.lower()))
                    built.append(f'fe/ion/artassets/backgrounds/{sub}/{f.lower()}')
                    n += 1
        lines.append(f'игроки: {n} файлов из {src}')
    # список меню
    if '--no-list' not in args:
        smenu = legacy_src(MENU)
        dmenu = p(work, MENU)
        os.makedirs(os.path.dirname(dmenu), exist_ok=True)
        g1 = dmenu + '.graft'
        glog = []
        remap = feapt.graft(smenu, N12_MMN, N12_SELECTOR, 'selectorBG', g1, log=glog.append)
        lines += [x.strip() for x in glog]
        g2 = dmenu + '.hybrid'
        idx, plan = hybrid_selector(g1, remap[N12_SELECTOR], g2)
        lines.append(f'menu.big: плашка-гибрид — символ {idx}, экспорт selectorBG → {idx}:')
        lines += [f'    d={dp:<2d} {nm:22s} x={x:g} y={y:g}' for nm, dp, x, y in plan]
        me = menu_list_edits(g2, keep_fade)
        feapt.patch_bytes(g2, dmenu, me, log=lambda *a: None)
        os.remove(g1)
        os.remove(g2)
        lines.append(f'menu.big: {len(me)} правок констант (масштаб невыделенных {UNHIGHLIGHT}, ряды 28/45, '
                     f'сдвиг выделенного 10' + ('' if keep_fade else ', без затухания пунктов') +
                     f', кубок в подменю {FEATURE_FADED[0]} % → {FEATURE_FADED[1]} %)')
        built.append(MENU)
        smain = legacy_src(MAIN)
        dmain = p(work, MAIN)
        feapt.patch_bytes(smain, dmain, main_edits(smain), log=lambda *a: None)
        lines.append('main.big: кегль пунктов 22 → 34 (4 формата), тень выделенного #DDDDDD, mDisabledAlpha 50')
        built.append(MAIN)
    # «цветной фон» под меню: без сжатия фото-арены на главном меню, подложка почти чёрная
    if '--no-underlay' not in args:
        dund = p(work, UNDERLAY)
        os.makedirs(os.path.dirname(dund), exist_ok=True)
        build_underlay(legacy_src(UNDERLAY), dund)
        lines.append('nhlbluebackground.big: INACTIVE_* = ACTIVE_* (' + ', '.join(
            f'{k} {a} → {b}' for k, (a, b) in UNDERLAY_CONSTS.items()) +
            f'), подложка mcColor #{UNDERLAY_COLOR[0] & 0xFFFFFF:06X} → #{UNDERLAY_COLOR[1] & 0xFFFFFF:06X}')
        built.append(UNDERLAY)
    built = sorted(set(built))
    open(os.path.join(work, 'build.log'), 'w', encoding='utf-8').write('\n'.join(lines) + '\n')
    json.dump({'from': src, 'db': db, 'spec': spec, 'keep_fade': keep_fade, 'files': built},
              open(os.path.join(work, 'build.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    for x in lines:
        log(x)
    if '--no-out' not in args:
        out = P.out
        old = [x.strip() for x in open(FILES, encoding='utf-8')] if os.path.exists(FILES) else []
        for rel in sorted(set(old) - set(built)):          # свои файлы прошлой сборки, которых больше нет
            if rel and os.path.exists(p(out, rel)):
                os.remove(p(out, rel))
                log(f'  убран из out: {rel}')
        for rel in built:
            dst = p(out, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copyfile(p(work, rel), dst)
        with open(FILES, 'w', encoding='utf-8', newline='\n') as f:
            f.write(''.join(r + '\n' for r in built))
        log(f'→ {out}: {len(built)} файлов; список — {FILES}')
    else:
        log(f'→ {work}: {len(built)} файлов (в out не копировалось)')


# ---------------------------------------------------------------- проверка

def apt_diff(a, b):
    """Отличающиеся байты двух Apt Data на общей длине: [(начало, конец)]."""
    out, n, k = [], min(len(a), len(b)), 0
    while k < n:
        if a[k] != b[k]:
            s = k
            while k < n and a[k] != b[k]:
                k += 1
            out.append((s, k))
        else:
            k += 1
    return out


def covered(diffs, allowed):
    """Все ли отличия внутри разрешённых диапазонов [(начало, конец)]."""
    bad = []
    for s, e in diffs:
        if not any(s >= a and e <= b for a, b in allowed):
            bad.append((s, e))
    return bad


def check_movie(path):
    """Разбор ролика целиком: FeMovie, все блоки кода, BIGF собирается обратно байт в байт."""
    data = open(path, 'rb').read()
    mv = febg.FeMovie(data)
    big = ph.Bigf(data)
    rt = febg.build_bigf(big) == data
    mvc, consts = feapt.load_movie(path)
    code = feapt.Code(mvc.apt.data, consts)
    nb = 0
    for title, off in feapt.code_blocks(mvc):
        code.parse(off)
        nb += 1
    return mv, rt, nb


def show_edits(path, edits_spec, title):
    """dis правленых мест: строки команд с этими смещениями."""
    mvc, consts = feapt.load_movie(path)
    code = feapt.Code(mvc.apt.data, consts)
    offs = {o for o, _, _ in edits_spec}
    out = []
    for t, off in feapt.code_blocks(mvc):
        if title not in t:
            continue
        fl = flat_code(code, off)
        for k, i in enumerate(fl):
            if i.body is None and any(i.off <= o < i.end for o in offs):
                prev = fl[k - 1]
                a = i.args[0] if i.args else ''
                if i.name == 'PushByte' and isinstance(a, int) and a >= 128:
                    a -= 256
                if i.name == 'PushLong':
                    a = f'0x{a:06X}'
                pa = prev.args[0] if prev.args else ''
                out.append(f'    @{i.off:#07x} {prev.name} {pa!s} → {i.name} {a}')
    return out


def cmd_check(args):
    work = args[0] if args and not args[0].startswith('--') else WORK
    meta = os.path.join(work, 'build.json')
    params = json.load(open(meta, encoding='utf-8')) if os.path.exists(meta) else {}
    src_dir = params.get('from', FROM)                      # с чем сборка сверяется: её же источник
    keep_fade = params.get('keep_fade', '--keep-fade' in args)
    ok = True

    def fail(msg):
        nonlocal ok
        ok = False
        log('  ОШИБКА: ' + msg)
    # фон
    f = p(work, BG)
    if os.path.exists(f):
        mv, rt, nb = check_movie(f)
        log(f'{BG}: {os.path.getsize(f)} байт, Apt {mv.apt.version}, символов {len(mv.apt.chars)}, блоков кода {nb}, '
            f'BIGF туда-обратно: {"да" if rt else "НЕТ"}')
        if not rt:
            fail('BIGF фона не собирается обратно')
        if not menu12.feapt_already_patched(f):
            fail('слушатель ModeTransitionStarted не пустой (нет bg_edits)')
        else:
            log('  слушатель ModeTransitionStarted пустой (bg_edits): да')
        src = p(src_dir, BG)
        if os.path.exists(src):
            a0, a1 = febg.FeMovie.load(src).apt.data, mv.apt.data
            diffs = apt_diff(a0, a1)
            slots = [s for s in menuplayers.slots_of(f) if s['list'] == 'm_backgroundPlayers']
            allowed = [(s['color_off'] + 1, s['color_off'] + 5) for s in slots]
            bad = covered(diffs, allowed) + ([('длина', len(a0), len(a1))] if len(a0) != len(a1) else [])
            log(f'  против фона menu12 ({src}): отличий {len(diffs)}, все — слова цвета колец: {"да" if not bad else "НЕТ " + str(bad[:5])}')
            if bad:
                fail('фон отличается от menu12 не только цветами колец')
            log('  кольца: ' + ' '.join(f'{s["asset"]}:#{s["color"]:06X}' for s in slots))
    # игроки
    n, bad = 0, []
    for sub in PLAYER_DIRS:
        d = p(work, f'fe/ion/artassets/backgrounds/{sub}')
        if os.path.isdir(d):
            for fn in os.listdir(d):
                n += 1
                s = p(src_dir, f'fe/ion/artassets/backgrounds/{sub}/{fn}')
                if os.path.exists(s) and open(s, 'rb').read() != open(os.path.join(d, fn), 'rb').read():
                    bad.append(fn)
    if n:
        log(f'игроки: {n} файлов, отличных от {src_dir}: {len(bad)}')
        if bad:
            fail('картинки игроков отличаются от источника — menu12 пересобрал? (build ещё раз)')
        if n != 72:
            fail(f'игроков {n}, ждали 72 (29 + 29 + 7 + 7)')
    # menu.big
    f = p(work, MENU)
    if os.path.exists(f):
        mv, rt, nb = check_movie(f)
        orig = febg.FeMovie.load(legacy_src(MENU))
        log(f'{MENU}: {os.path.getsize(f)} байт (оригинал {os.path.getsize(legacy_src(MENU))}), символов '
            f'{len(mv.apt.chars)} (было {len(orig.apt.chars)}), блоков кода {nb}, BIGF туда-обратно: {"да" if rt else "НЕТ"}')
        if not rt:
            fail('BIGF menu.big не собирается обратно')
        a0, a1 = orig.apt.data, mv.apt.data
        m = orig.apt.movie_off
        ne, ep = struct.unpack_from('>II', a0, m + 0x38)
        k = [i for i in range(ne) if feapt.cstr(a0, u32(a0, ep + 8 * i)).lower() == 'selectorbg'][0]
        me = menu_list_edits(legacy_src(MENU), keep_fade)
        allowed = [(m + 0x1C, m + 0x24), (ep + 8 * k + 4, ep + 8 * k + 8)] + [(o, o + len(x)) for o, x, _ in me]
        diffs = apt_diff(a0, a1)
        badd = covered(diffs, allowed)
        log(f'  Apt Data: было {len(a0)}, стало {len(a1)} (+{len(a1) - len(a0)} в конце); отличий в старой части '
            f'{len(diffs)}, все — число/таблица символов, экспорт selectorBG и константы: {"да" if not badd else "НЕТ " + str(badd[:5])}')
        if badd:
            fail('menu.big: лишние отличия в старой части Apt Data')
        # записи BIGF: старые — те же, новые — геометрия и текстуры пересаженной плашки
        r0 = {n: x for n, x in orig.raw.items() if n != '0'}
        r1 = {n: x for n, x in mv.raw.items() if n != '0'}
        same = all(n in r1 and r1[n][0] == r0[n][0] for n in r0)
        log(f'  записи BIGF: старые {len(r0)} те же: {"да" if same else "НЕТ"}, новые: {sorted(set(r1) - set(r0), key=lambda s: int(s) if s.isdigit() else 0)}')
        if not same:
            fail('menu.big: изменены старые записи BIGF')
        exp = {n.lower(): i for n, i in mv.apt.exports}
        sel = exp['selectorbg']
        log(f'  экспорт selectorBG → символ {sel}:')
        for depth, name, char, off in sprite_items(mv.apt, sel):
            po = febg.PlaceObject(mv.apt.data, off)
            log(f'    d={depth:<2d} {name or "-":12s} символ {char:3d} ({mv.apt.chars[char].name}) x={po.matrix[4]:g} y={po.matrix[5]:g}')
        for t in ('__Packages.game.components.classes.MenuItem»', '__Packages.game.components.classes.Menu»'):
            for line in show_edits(f, me, t):
                log(line)
        # selectorBG Legacy и пересаженный NHL 12 разбираются
        for i in range(len(orig.apt.chars), len(mv.apt.chars)):
            ch = mv.apt.chars[i]
            if ch.type == 1 and i not in mv.geometry:
                fail(f'символ {i}: нет геометрии')
            if ch.type == 7 and i not in mv.textures:
                fail(f'символ {i}: нет текстуры')
    # main.big
    f = p(work, MAIN)
    if os.path.exists(f):
        mv, rt, nb = check_movie(f)
        src = legacy_src(MAIN)
        a0, a1 = febg.FeMovie.load(src).apt.data, mv.apt.data
        ed = main_edits(src)
        diffs = apt_diff(a0, a1)
        badd = covered(diffs, [(o, o + len(x)) for o, x, _ in ed]) + ([('длина',)] if len(a0) != len(a1) else [])
        log(f'{MAIN}: {os.path.getsize(f)} байт, блоков кода {nb}, BIGF туда-обратно: {"да" if rt else "НЕТ"}; '
            f'отличий {len(diffs)}, все — правки шрифта пунктов: {"да" if not badd else "НЕТ"}')
        if badd or not rt:
            fail('main.big: лишние отличия или BIGF')
        for line in show_edits(f, ed, ''):
            log(line)
    # «цветной фон»
    f = p(work, UNDERLAY)
    if os.path.exists(f):
        mv, rt, nb = check_movie(f)
        src = legacy_src(UNDERLAY)
        orig = febg.FeMovie.load(src)
        ed = underlay_edits(src)
        diffs = apt_diff(orig.apt.data, mv.apt.data)
        badd = covered(diffs, [(o, o + len(x)) for o, x, _ in ed]) + \
            ([('длина',)] if len(orig.apt.data) != len(mv.apt.data) else [])
        key, fl = underlay_fill(mv)
        r0 = {n: x for n, x in orig.raw.items() if n not in ('0', key)}
        r1 = {n: x for n, x in mv.raw.items() if n not in ('0', key)}
        g0, g1 = orig.raw[key][0], mv.raw[key][0]
        gd = apt_diff(g0, g1)
        gbad = covered(gd, [(fl.off + 0x10, fl.off + 0x14)]) + ([('длина',)] if len(g0) != len(g1) else [])
        log(f'{UNDERLAY}: {os.path.getsize(f)} байт, блоков кода {nb}, BIGF туда-обратно: {"да" if rt else "НЕТ"}; '
            f'Apt Data: отличий {len(diffs)}, все — константы INACTIVE_*: {"да" if not badd else "НЕТ"}; '
            f'геометрия подложки: цвет #{fl.color & 0xFFFFFF:06X}, прочее то же: {"да" if not gbad else "НЕТ"}; '
            f'остальные записи те же: {"да" if r0 == r1 else "НЕТ"}')
        if badd or gbad or not rt or r0 != r1 or fl.color != UNDERLAY_COLOR[1]:
            fail('nhlbluebackground.big: лишние отличия, другой цвет подложки или BIGF')
        for line in show_edits(f, ed, '__Packages.game.background.NHLBlueBackground»'):
            log(line)
    log('ИТОГ: ' + ('всё сходится' if ok else 'ЕСТЬ ОШИБКИ'))
    if not ok:
        sys.exit(1)


# ---------------------------------------------------------------- примерный вид (Pillow)

def cmd_mockup(args):
    """Плашка-гибрид и пункты списка по разобранным данным (текстуры NHL 12, раскладка menu.big Legacy, шрифт
    пунктов из out/fe/ion/fonts) поверх левой панели Legacy со снимка игры — для сверки геометрии, не снимок."""
    from PIL import Image, ImageDraw, ImageFont
    work = args[0] if args and not args[0].startswith('--') else WORK
    out = opt(args, '--out', P.work_dir('menu', 'mockup.png'))
    mv = febg.FeMovie.load(p(work, MENU))
    a = mv.apt
    sel = {n.lower(): i for n, i in a.exports}['selectorbg']

    def sprite_img(idx):
        """Спрайт из одной фигуры с текстурой → (RGBA, x0, y0)."""
        po = a.chars[idx].frames[0][0].po
        shp = a.chars[po.char]
        t = mv.textures[shp.image]
        w, h = t.fetch.width, t.fetch.height
        im = Image.frombytes('RGBA', (w, h), bytes(t.decode()))
        b = shp.bounds
        return im.crop((0, 0, int(b[2] - b[0]), int(b[3] - b[1]))), b[0], b[1]
    font_path = p(P.out, 'fe/ion/fonts/eahelveticaneuehv-mod.ttf')
    shot = os.path.join(os.path.dirname(GAME), 'legacy-port', 'out', 'shots', 'rel_02.png')
    W, H = 1280, 720
    canvas = Image.new('RGBA', (W, H), (12, 14, 18, 255))
    if os.path.exists(shot):
        canvas.paste(Image.open(shot).convert('RGBA').crop((0, 0, 418, 720)), (0, 0))
        ImageDraw.Draw(canvas).rectangle((0, 320, 417, 600), fill=(26, 31, 40, 255))
    items = ['PLAY', 'COMMUNITY', 'CUSTOMIZE', None, 'HOCKEY ULTIMATE TEAM', 'LIVE THE LIFE', 'NHL 94 ANNIVERSARY MODE']
    hl = 0
    item_x, base_y = 120, 574                       # левый край пункта и низ списка на экране (снимок Legacy)
    ru, rh, ho = ROWS['ROW_SIZE_UNHIGHLIGHTED'][1], ROWS['ROW_SIZE_HIGHLIGHTED'][1], HIGHLIGHT_OFFSET[1]
    above_h, below_h = 20, 5
    ys = {}
    for k in range(len(items) - 1, -1, -1):          # как Menu.UpdateMenuItemPosition: снизу вверх
        below = items[k + 1:]
        rows, heads = sum(1 for x in below if x), sum(1 for x in below if x is None)
        y = -(ru * rows + (above_h + below_h + ru) * heads)
        if k == hl:
            y -= ho
        elif items[k] is None:
            y += above_h + ((ru - rh) if k < hl else 0)
        elif k < hl:
            y += ru - rh
        ys[k] = base_y + y
    d = ImageDraw.Draw(canvas)
    # заголовок раздела: «EA HelveticaNeue Med» 26 в поле, сжатом кодом так же, как невыделенные (×0,735 → ~19)
    fh = ImageFont.truetype(p(P.out, 'fe/ion/fonts/eahelveticaneuemed-mod.ttf'), 19)
    # плашка выделенного
    sy = ys[hl] + 1
    sx = item_x - 29
    for depth, name, char, off in sprite_items(a, sel):
        po = febg.PlaceObject(a.data, off)
        tx, ty = po.matrix[4], po.matrix[5]
        if name in ('center', 'left', 'right'):
            im, x0, y0 = sprite_img(char)
            if name == 'center':
                im = im.resize((327, im.height), Image.BILINEAR)
            canvas.alpha_composite(im, (int(round(sx + tx + x0)), int(round(sy + ty + y0))))
        elif name == 'mcMenuArrow':
            ax, ay = sx + 317, sy + ty
            d.polygon([(ax - 12, ay - 7), (ax, ay + 0.5), (ax - 12, ay + 8)], fill=(40, 40, 40, 255))
        elif not name:
            d.ellipse((sx + tx - 10, sy + ty - 10, sx + tx + 10, sy + ty + 10), fill=(90, 160, 40, 255))
            d.text((sx + tx, sy + ty), 'A', font=ImageFont.truetype(font_path, 14), fill=(255, 255, 255, 255), anchor='mm')
    # текст: поле на (2, −9) в пункте, рамка поля −2 → верх поля на 11 выше пункта; прописные кегля 34 в игре —
    # с 10 по 30 px от верха поля (замер снимка NHL 13 с меню menu12: тот же шрифт и то же поле, верх поля там
    # на уровне пункта, полоса NHL 12 — с 1); у Pillow тот же рисунок даёт такие прописные при кегле ~31.
    # Невыделенные — тот же текст ×0,735 от (0, 0) пункта (код масштабирует textHolder_mc целиком).
    f34 = ImageFont.truetype(font_path, 31)
    for k, t in enumerate(items):
        y = ys[k]
        if t is None:
            d.text((item_x + 2, y + 15), 'FEATURED', font=fh, fill=(26, 154, 239, 160), anchor='ls')
            continue
        if k == hl:
            img = Image.new('RGBA', (900, 80), (0, 0, 0, 0))
            ImageDraw.Draw(img).text((2, 30), t, font=f34, fill=(0x25, 0x2A, 0x2F, 255), anchor='ls')
            canvas.alpha_composite(img, (item_x, y - 11))
        else:
            img = Image.new('RGBA', (900, 80), (0, 0, 0, 0))
            ImageDraw.Draw(img).text((2, 30), t, font=f34, fill=(255, 255, 255, 204), anchor='ls')
            w = img.getbbox()[2] if img.getbbox() else 1
            sc = UNHIGHLIGHT if w * UNHIGHLIGHT <= 292 else 284 / w
            img = img.resize((int(900 * sc), int(80 * sc)), Image.LANCZOS)
            canvas.alpha_composite(img, (item_x, int(round(y - 11 * sc))))
    d.text((440, 20), 'Примерный вид (Pillow, не снимок игры): плашка NHL 12 + пункты 34/25 в меню Legacy',
           font=ImageFont.truetype(font_path, 18), fill=(255, 220, 120, 255))
    canvas.convert('RGB').save(out)
    log(f'→ {out}')


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    if len(sys.argv) < 2 or sys.argv[1] not in ('build', 'check', 'mockup'):
        sys.exit(__doc__)
    {'build': cmd_build, 'check': cmd_check, 'mockup': cmd_mockup}[sys.argv[1]](sys.argv[2:])


if __name__ == '__main__':
    main()
