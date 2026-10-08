"""Главное меню NHL 12 в NHL 13: сборка файлов для cache: (фон, список меню, игроки).

    python menu12.py build OUTDIR [--tint RRGGBB] [--players-dir DIR] [--no-list] [--no-panel]
        # OUTDIR в раскладке cache: (fe/…):
        #   fe/ion/game/background/nhlmainmenubackground.big — фон главного меню NHL 12 (её cache.big) с правкой
        #       порядка событий фреймворка NHL 13 (иначе игрок гаснет сразу при появлении); --tint — тонировка
        #       серых текстур арены в цвет (вариант «в нашем цвете», напр. 245C99);
        #   fe/ion/game/components/menu.big — список меню NHL 13 с плашкой выделения NHL 12 (selectorBG
        #       пересажен из mainMenuNew NHL 12), невыделенными пунктами ×0,735 и тёмной нейтральной рамкой
        #       подменю (у NHL 13 — тёмно-синяя);
        #   fe/ion/main.big — шрифт пунктов как в NHL 12: 34 (выделенный) / 25 (остальные), тень #DDDDDD;
        #   fe/ion/game/components/nhl_proshopnotification.big — панель «NHL 13 Features» вверху слева, как
        #       панель новостей NHL 12 (--no-panel — оставить внизу справа);
        #   игроки (mainmenuplayers…/nhl<N>.big + цвета колец в фоне) — из сборки tools/menuplayers.py
        #       (--players-dir), фон берётся оттуда и тонируется/правится заново.
    python menu12.py check OUTDIR       # что собрано: разбор, правки байткода, отличия от оригиналов

Подробности — docs/fe-menu.md. Только стандартная библиотека (+ tools/febg.py, feapt.py, playerhead.py).
"""
import os, shutil, struct, sys

TOOLS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TOOLS)
import playerhead as ph   # noqa: E402
import febg               # noqa: E402
import feapt              # noqa: E402

GAME = ph.game_dir()
N12 = os.path.join(GAME, 'other', 'nhl12', 'big')
N13 = os.path.join(GAME, 'extracted', 'big')
BG = 'fe/ion/game/background/nhlmainmenubackground.big'
MENU = 'fe/ion/game/components/menu.big'
MAIN = 'fe/ion/main.big'
MAINMENUNEW12 = 'fe/ion/external/ion_sports07/components/mainmenunew.big'
PROSHOP = 'fe/ion/game/components/nhl_proshopnotification.big'


def p(root, rel):
    return os.path.join(root, *rel.split('/'))


# ---------------------------------------------------------------- правки байткода (той же длины)

def find_seq(code_instrs, names):
    """Найти подряд идущие команды с именами names (список); → список совпадений (списки Instr)."""
    out = []
    flat = []

    def walk(lst):
        for i in lst:
            flat.append(i)
            if i.body:
                walk(i.body)
    walk(code_instrs)
    for k in range(len(flat) - len(names) + 1):
        if all(flat[k + j].name == n for j, n in enumerate(names)):
            out.append(flat[k:k + len(names)])
    return out


def bg_edits(path):
    """Фон NHL 12 под фреймворк NHL 13.

    1. NHL 13 ждёт IsLoaded() (ставится в Init фона) и только потом начинает переход и шлёт
       «ModeTransitionStarted», а фон NHL 12 подписан на это событие с Init и считает его своим уходом:
       animateBackgroundOut гасит игрока и снимает все анимации. Слушатель делается пустым:
       Delegate.Create(this, this.animateBackgroundOut) → Delegate.Create(this, this.mDelay) (число — вызов
       ничего не делает).
    2. Раз уход больше не снимает анимации, их снимает Shutdown (его вызывает Destroy при выгрузке):
       trace(CLASS_NAME + "::Shutdown") → this.ClearAllAnimations() + пустые PushByte/Pop."""
    mv, consts = feapt.load_movie(path)
    code = feapt.Code(mv.apt.data, consts)
    pool = {c: i for i, c in enumerate(consts)}
    edits = []
    for title, off in feapt.code_blocks(mv):
        if '__Packages.game.background.NHLMainMenuBackground' not in title:
            continue
        ins = code.parse(off)
        for m in find_seq(ins, ['PushRegister', 'PushConstant', 'PushRegister', 'GetNamedMember']):
            if m[1].args[0] == 'mMTMListenerObject' and m[3].args[0] == 'animateBackgroundOut':
                edits.append((m[3].off + 1, bytes([pool['animateBackgroundOut']]), bytes([pool['mDelay']])))
        for m in find_seq(ins, ['PushValueOfVar', 'GetNamedMember', 'GetNamedMember', 'GetNamedMember',
                                'PushConstant', 'Add2', 'Trace']):
            if m[3].args[0] == 'CLASS_NAME' and m[4].args[0] == '::Shutdown':
                old = bytes(mv.apt.data[m[0].off:m[6].end])
                new = bytes([0x59, 0xB9, 0x01, 0xB2, pool['ClearAllAnimations']]) + bytes([0xB5, 0, 0x17]) + bytes([0x59, 0x17] * 2)
                assert len(old) == len(new) == 12, (len(old), len(new))
                edits.append((m[0].off, old, new))
    if len(edits) != 2:
        raise SystemExit(f'фон: ожидалось 2 правки, найдено {len(edits)} — другой файл?')
    return edits


def menu_edits(path, unhighlight=0.735):
    """menu.big: MenuItem.UNHIGHLIGHTING_SCALE 0.9 → 25/34 (невыделенные пункты как у NHL 12)."""
    mv, consts = feapt.load_movie(path)
    code = feapt.Code(mv.apt.data, consts)
    for title, off in feapt.code_blocks(mv):
        for m in find_seq(code.parse(off), ['PushConstant', 'PushFloat', 'SetMember']):
            if m[0].args[0] == 'UNHIGHLIGHTING_SCALE':
                return [(m[1].off + 1, struct.pack('>f', m[1].args[0]), struct.pack('>f', unhighlight))]
    raise SystemExit('menu.big: UNHIGHLIGHTING_SCALE не найден')


def main_edits(path):
    """main.big, GetCustomMenuOptions: размеры 24 → 34 у четырёх форматов пунктов, тень выделенного
    #FFFFFF → #DDDDDD, mDisabledAlpha 30 → 50 (как MenuOptions NHL 12)."""
    mv, consts = feapt.load_movie(path)
    code = feapt.Code(mv.apt.data, consts)
    edits = []
    for title, off in feapt.code_blocks(mv):
        flat = []

        def walk(lst):
            for i in lst:
                flat.append(i)
                if i.body:
                    walk(i.body)
        walk(code.parse(off))
        for k, i in enumerate(flat):
            if i.name == 'PushString' and i.args[0] in ('mItemTextFormat', 'mItemDropTextFormat',
                                                        'mHighlightedItemTextFormat', 'mHighlightedItemDropTextFormat'):
                col, size, font = flat[k + 1], flat[k + 2], flat[k + 3]
                if font.name != 'PushString' or font.args[0] != 'EA HelveticaNeue Hv' or size.name != 'PushByte':
                    continue
                if size.args[0] == 24:
                    edits.append((size.off + 1, bytes([24]), bytes([34])))
                if i.args[0] == 'mHighlightedItemDropTextFormat' and col.name == 'PushLong' and col.args[0] == 0xFFFFFF:
                    edits.append((col.off + 1, struct.pack('>I', 0xFFFFFF), struct.pack('>I', 0xDDDDDD)))
            if i.name == 'PushString' and i.args[0] == 'mDisabledAlpha' and flat[k + 1].name == 'PushByte' \
                    and flat[k + 1].args[0] == 30:
                edits.append((flat[k + 1].off + 1, bytes([30]), bytes([50])))
    if len(edits) != 6:
        raise SystemExit(f'main.big: ожидалось 6 правок, найдено {len(edits)}')
    return edits


def desaturate_textures(path, min_share=0.5, max_lum=60):
    """Тёмно-синие текстуры (рамка подменю справа от пункта у NHL 13) → нейтральные той же яркости, как
    чёрная косая панель NHL 12. Берутся только тёмные (средняя яркость ≤ max_lum) и заметно цветные."""
    mv = febg.FeMovie.load(path)
    big = ph.Bigf(mv.big.raw)
    n = 0
    for idx, t in sorted(mv.textures.items()):
        rgba = bytearray(t.decode())
        mean, share, smax = febg.texture_stats(rgba)
        if share < min_share or sum(mean) / 3 > max_lum:
            continue
        for i in range(0, len(rgba), 4):
            y = round(0.299 * rgba[i] + 0.587 * rgba[i + 1] + 0.114 * rgba[i + 2])
            rgba[i:i + 3] = bytes((y, y, y))
        xpr = t.encode(bytes(rgba))
        big.put(t.name, ph.refpack_compress(xpr) if mv.raw[t.name][1] else xpr)
        n += 1
    data = febg.build_bigf(big)
    febg.FeMovie(data)
    open(path, 'wb').write(data)
    return n


# панель «NHL 13 Features» (NHL_ProShopNotification, свой _level): у NHL 13 — внизу справа, поверх ног игрока;
# у NHL 12 такая же панель новостей — вверху слева над списком. Сдвиг ролика целиком (InitAnimation):
# 16:9 (786, 654) → (192, 184), 4:3 (740, 675) → (150, 205) — верх панели ≈ 64 px от верха экрана.
PROSHOP_POS = {(740, 675): (150, 205), (786, 654): (192, 184)}


def proshop_edits(path):
    mv, consts = feapt.load_movie(path)
    code = feapt.Code(mv.apt.data, consts)
    edits = []
    for title, off in feapt.code_blocks(mv):
        for m in find_seq(code.parse(off), ['PushValueOfVar', 'PushConstant', 'PushShort', 'SetMember',
                                            'PushValueOfVar', 'PushConstant', 'PushShort', 'SetMember']):
            if m[0].args[0] == 'THIS_MOVIE' and m[1].args[0] == '_x' and m[5].args[0] == '_y':
                key = (m[2].args[0], m[6].args[0])
                if key in PROSHOP_POS:
                    nx, ny = PROSHOP_POS[key]
                    edits.append((m[2].off + 1, struct.pack('>H', key[0]), struct.pack('>H', nx)))
                    edits.append((m[6].off + 1, struct.pack('>H', key[1]), struct.pack('>H', ny)))
    if len(edits) != 4:
        raise SystemExit(f'панель Features: ожидалось 4 правки, найдено {len(edits)}')
    return edits


# ---------------------------------------------------------------- тонировка фона («в нашем цвете»)

def tint_movie(path_in, path_out, rgb, strength=0.55):
    """Серые текстуры фона → оттенок rgb при той же светлоте (HLS); цветные (кольца, блики) не трогаются."""
    import colorsys
    mv = febg.FeMovie.load(path_in)
    h, _, s = colorsys.rgb_to_hls(*(c / 255 for c in rgb))
    big = ph.Bigf(mv.big.raw)
    n = 0
    for idx, t in sorted(mv.textures.items()):
        rgba = bytearray(t.decode())
        mean, share, smax = febg.texture_stats(rgba)
        if share > 0.3:                                        # заметно цветная — не трогаем
            continue
        memo = {}
        for i in range(0, len(rgba), 4):
            key = bytes(rgba[i:i + 3])
            v = memo.get(key)
            if v is None:
                r, g, b = (c / 255 for c in key)
                _, l, s0 = colorsys.rgb_to_hls(r, g, b)
                ss = s * strength * (1 - abs(2 * l - 1)) + s0 * (1 - strength)
                v = memo[key] = bytes(round(c * 255) for c in colorsys.hls_to_rgb(h, l, min(1, ss)))
            rgba[i:i + 3] = v
        xpr = t.encode(bytes(rgba))
        big.put(t.name, ph.refpack_compress(xpr) if mv.raw[t.name][1] else xpr)
        n += 1
    data = febg.build_bigf(big)
    febg.FeMovie(data)
    open(path_out, 'wb').write(data)
    return n


# ---------------------------------------------------------------- сборка

def cmd_build(args):
    out = args[0]
    tint = args[args.index('--tint') + 1] if '--tint' in args else None
    pdir = args[args.index('--players-dir') + 1] if '--players-dir' in args else None
    os.makedirs(out, exist_ok=True)
    # фон: NHL 12 → (игроки: цвета колец из сборки menuplayers) → правка порядка событий → тонировка
    src_bg = p(N12, 'cache/' + BG)
    if pdir and os.path.exists(p(pdir, BG)):
        src_bg = p(pdir, BG)                                   # уже с цветами колец и правками
        print(f'фон: из сборки игроков {src_bg}')
    dst_bg = p(out, BG)
    os.makedirs(os.path.dirname(dst_bg), exist_ok=True)
    edits = bg_edits(src_bg) if not feapt_already_patched(src_bg) else []
    if edits:
        feapt.patch_bytes(src_bg, dst_bg, edits)
    else:
        shutil.copyfile(src_bg, dst_bg)
    if tint:
        rgb = tuple(int(tint[i:i + 2], 16) for i in (0, 2, 4))
        n = tint_movie(dst_bg, dst_bg, rgb)
        print(f'фон: тонировано текстур {n} в #{tint}')
    # игроки
    if pdir:
        for sub in ('mainmenuplayers', 'mainmenuplayersblur', 'mainmenulegends', 'mainmenulegendsblur'):
            d = p(pdir, f'fe/ion/artassets/backgrounds/{sub}')
            if os.path.isdir(d):
                dd = p(out, f'fe/ion/artassets/backgrounds/{sub}')
                os.makedirs(dd, exist_ok=True)
                for f in os.listdir(d):
                    if f.endswith('.big'):
                        shutil.copyfile(os.path.join(d, f), os.path.join(dd, f))
        print(f'игроки: из {pdir}')
    if '--no-list' not in args:
        # список меню: плашка NHL 12 + масштаб невыделенных
        menu = p(out, MENU)
        feapt.graft(p(N13, 'boot/' + MENU), p(N12, 'boot/' + MAINMENUNEW12), 69, 'selectorBG', menu)
        feapt.patch_bytes(menu, menu, menu_edits(menu))
        n = desaturate_textures(menu)
        print(f'menu.big: рамка подменю — нейтральная ({n} текстуры)')
        main = p(out, MAIN)
        feapt.patch_bytes(p(N13, 'boot/' + MAIN), main, main_edits(p(N13, 'boot/' + MAIN)))
    if '--no-panel' not in args:
        ps = p(out, PROSHOP)
        os.makedirs(os.path.dirname(ps), exist_ok=True)
        feapt.patch_bytes(p(N13, 'cache/' + PROSHOP), ps, proshop_edits(p(N13, 'cache/' + PROSHOP)))
    print(f'→ {out}')


def feapt_already_patched(path):
    """Фон уже с правкой слушателя (из сборки menuplayers, которая берёт исправленный фон)?"""
    mv, consts = feapt.load_movie(path)
    code = feapt.Code(mv.apt.data, consts)
    for title, off in feapt.code_blocks(mv):
        if '__Packages.game.background.NHLMainMenuBackground' not in title:
            continue
        for m in find_seq(code.parse(off), ['PushRegister', 'PushConstant', 'PushRegister', 'GetNamedMember']):
            if m[1].args[0] == 'mMTMListenerObject':
                return m[3].args[0] == 'mDelay'
    return False


def cmd_check(args):
    out = args[0]
    for rel in (BG, MENU, MAIN):
        f = p(out, rel)
        if not os.path.exists(f):
            continue
        mv = febg.FeMovie.load(f)
        print(f'{rel}: {os.path.getsize(f)} байт, символов {len(mv.apt.chars)}, Apt {mv.apt.version}')
    f = p(out, BG)
    if os.path.exists(f):
        print('  слушатель ModeTransitionStarted пустой:', feapt_already_patched(f))


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    {'build': cmd_build, 'check': cmd_check}.get(sys.argv[1], lambda a: sys.exit(__doc__))(sys.argv[2:])


if __name__ == '__main__':
    main()
