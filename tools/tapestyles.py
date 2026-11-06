"""Варианты обмотки крюка: свободные коды sticktapecolor (3, 4, 6, 8, 9) — частичная обмотка белой лентой.

    python tapestyles.py table                         # таблица «код → вид обмотки» и границы по UV
    python tapestyles.py build [--out DIR] [--no-preview]
                                                       # texlib_999.rx2 с новыми текстурами sticktape_N_cm в
                                                       # раскладке cache: (DIR/rendering/playerstick/), картинки
                                                       # текстур (DIR/png) и лист вариантов на крюке
    python tapestyles.py preview [--out DIR] [--stick N]   # только лист (по готовому texlib_999 из DIR); --stick —
                                                       # текстура клюшки N: из cache: порта (поставленная), иначе EA
    python tapestyles.py compare [--out DIR] [--before FILE] [--codes 0,1] [--stick N]
                                                       # было / стало: верх клюшки (лента рукояти) и крюк, текстуры
                                                       # FILE (по умолчанию — texlib_999 в cache: установки) против
                                                       # DIR; полевые _2/_4 обеих рук, вратарские, клюшка на льду
                                                       # → DIR/preview/compare.png и compare-all.png

У всех команд — опция --game {nhl13,legacy} (или NHL_GAME, tools/gameprofile.py), по умолчанию — как у rw4mesh
(NHL 13); собирается под NHL Legacy: --game legacy. Выход по умолчанию — game/work/models/tapevar/<игра>/out.

Как устроено (разбор — docs/player-models.md §9, §13). Цвет ленты — текстура sticktape_<код>_cm (128×64 DXT1 +
мипы) из rendering/playerstick/texlib_999.rx2; код — поле exhibitionskaterequipment.sticktapecolor (у вратарей —
exhibitiongoalieequipment); в базах NHL 13 и Legacy заняты только 0 (чёрная) и 1 (белая), 2–9 — цвета, которые
никто не носит. Сетка ленты — это сама поверхность средней части крюка (у мода sticktape.py — до кончика носка),
UV-u идёт вдоль крюка: у мода «низ-2» от пятки (кольцо 0, u = 0,018) до кончика (u ≈ 0,684), правее 0,696 —
рисунок набалдашника; UV-v — по кругу сечения. Значит, частичную обмотку можно нарисовать в текстуре: там, где
ленты нет, — голый крюк (тёмный карбон), сетки не меняются. Голый крюк один на все клюшки (текстура ленты не знает
модели клюшки): чёрный карбон. Сетки — мод «низ-2» с осевым UV (sticktape.py --axial-uv, папка out-bottom2-axial):
у каждой вершины крюка u — по её глубине вдоль оси крюка, так что столбец текстуры — плоскость поперёк крюка (у
исходных колец EA от пятки до середины u шёл бы наискось, на 9–26 мм). Границы — доли длины крюка от пятки к
кончику, в u — по кольцам этой сетки (_2 и _4 одинаково, обе руки — зеркало с теми же UV). Край ленты ровный,
поперёк оси крюка, жёсткий: пиксель — либо лента, либо карбон, без смешивания (размывают только мипы вдали). Набалдашник — как у полной ленты того же цвета. Чёрных частичных нет: на
чёрном карбоне их не видно; 2, 5, 7 — цвета EA, не меняются (их ключи подписей общие с цветами глаз). У чёрной
ленты EA (код 0) левые столбцы светлее — у ленты до носка они ложатся на пятку белесым разводом, поэтому код 0
тоже перерисовывается: столбцы пятки — полосами ленты рядом (HEEL_COLS, 24.10.2026).

Лента рукояти (верх клюшки, «набалдашник») — второй кусок той же сетки ленты: торец и 17 см древка сверху (у полевых
76 вершин, x −0,080…+0,088 м; клюшка начинается у +0,088), та же текстура, правая часть u ≥ 0,69 (полевые и клюшка
на льду — u 0,696…0,842, v 0,02…0,64; вратарские — u 0,70…0,99, v 0,03…0,96). Своего поля цвета у неё нет, поэтому у
чёрной ленты EA верх тоже чёрный. С 06.11.2026 (KNOB_WHITE) верх у всех кодов — белая лента EA (код 1): столбцы
u ≥ UV_KNOB берутся из sticktape_1_cm, крюк — как был. Граница — столбец 88 (u 0,6875…0,6953): кончик крюка
(u ≤ 0,684) берёт из него 3 % (билинейно), шов набалдашника (u 0,6958) — 44 %, поэтому он белый.

Только стандартная библиотека (+ Chrome/Edge без окна — подписи листа, как в teamart/sticktape).
"""
import hashlib, json, os, random, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rw4mesh as rm  # noqa: E402

TEXLIB = 'rendering/playerstick/texlib_999.rx2'
TAPE_TEX = 'sticktape_{}_cm'
W, H = 128, 64

# код → (основа: 0 чёрная / 1 белая, замотанные куски — доли длины крюка от пятки (0) к кончику (1), подпись).
# 0 и 1 — как у EA (полная лента), не перерисовываются.
STYLES = {
    0: (0, [(0.0, 1.0)], 'чёрная, весь крюк (EA; пятка — без светлой полосы)'),
    1: (1, [(0.0, 1.0)], 'белая, весь крюк (EA; так у Кейна)'),
    3: (1, [(0.30, 0.87)], 'белая, середина: пятка и носок голые (Селебрини)'),
    # 24.10.2026 пользователь: «4 — нужно сделать больше голого на носке (как у Моргана Райли)» — как маска largetoe
    # NHL 27 (лента 0–0,70 крюка, docs/equipment27.md; у Райли в NHL 27 — largetoe); было 0–0,87 (~3 см)
    4: (1, [(0.0, 0.70)], 'белая, носок голый — треть крюка (Райли)'),
    6: (1, [(0.25, 1.0)], 'белая, голая только пятка (четверть крюка)'),
    8: (1, [(0.45, 1.0)], 'белая, от середины до носка, пятка голая (Овечкин)'),
    9: (1, [(0.55, 0.85)], 'белая, узкая полоса ближе к носку (Бенн)'),
}
# 2, 5, 7 — как у EA (синяя, зелёная, голубая): текстуры не меняются. Подписи цветов в меню — общие ключи
# локализации (blue, green, lightblue — и цвета глаз в редакторе внешности), поэтому варианты — на кодах, чьи ключи
# (red, yellow, orange, pink, purple) больше нигде не нужны (12.10). Чёрных частичных нет: на чёрном карбоне не видно
EA_COLORS = {2: 'синяя (EA)', 5: 'зелёная (EA)', 7: 'голубая (EA)'}
# подписи вариантов в меню экипировки (fe/loc NHL_ENG_US: ключ цвета кода → текст), ставит tape_players.py
LABELS = {3: ('red', 'White Middle'), 4: ('yellow', 'White No Toe'), 6: ('orange', 'White No Heel'),
          8: ('pink', 'White Toe Half'), 9: ('purple', 'White Strip')}
# голый крюк: серый карбон. 24.10.2026 пользователь: «черную часть псевдообмотки сделать посветлее (более серой), чтобы
# меньше выделялась на большинстве клюшек» — медиана цвета крюка у 27 клюшек в игре (cache:, тексели под крюком):
# (49, 52, 51), у тёмных 21–33, у деревянных и белой CCM — светлые. Было (21, 22, 25) — почти чёрный
CARBON = (50, 52, 52)
HEEL_COLS = (4, 6)          # код 0: столбцы 0–3 (светлее: 81–53 против 39 в середине) ← столбцы 6–9 той же ленты
UV_KNOB = 0.69              # правее — набалдашник (лента рукояти): столбцы 88–127
# 06.11.2026 пользователь: «у всех обмоток — чёрная она или белая — верхняя часть клюшки всегда была замотана БЕЛОЙ
# лентой». Набалдашник (u ≥ UV_KNOB) у всех кодов — как у белой ленты EA (код 1): у 0 (чёрная) и 2, 5, 7 (цвета EA)
# он перерисовывается, у 1 и белых частичных он и так белый. False — набалдашник цвета своей ленты (как у EA)
KNOB_WHITE = True
KNOB_FROM = 1               # чей набалдашник берётся (код текстуры)


def out_root(args=None):
    d = rm.opt(args, '--out') if args is not None else None
    return d or os.path.join(rm.game_dir(), 'work', 'models', 'tapevar', rm.PROFILE.name, 'out')


# ---------------------------------------------------------------- доля длины крюка ↔ UV-u (по сетке мода)

def blade_mapping():
    """Кольца ленты крюка у мода «низ-2» с осевым UV (_2, левый хват): [(u, доля длины от пятки к кончику по оси
    крюка)], по возрастанию u. С осевым UV u вершины зависит только от её глубины вдоль оси (рамка носка sticktape, n —
    к кончику), поэтому эта таблица верна для любого пикселя. Сетка собирается в памяти (sticktape.build_pair)."""
    import sticktape as stt
    pair = stt.make_pair('player', 0, 2)
    tb, _, _ = stt.build_pair(pair, stt.ROUNDS['bottom2'], axial_uv=True)
    pair = stt.make_pair('player', 0, 2)              # рамка — по исходной сетке, как у build_pair
    pair.align_to_edges()
    nt = rm.Mesh(tb, pair.rel_tape)
    tp = pair.tape
    blade = set(pair.blade)
    used = set(i for t in nt.tris for i in t)
    rings = {}
    for i in range(nt.nv):
        if (i in blade or i >= tp.nv) and i in used:
            rings.setdefault(round(nt.uv[i][0], 4), []).append(i)
    heel = None
    rows = []
    for u in sorted(rings):
        L = [pair.local(nt.pos[i]) for i in rings[u]]
        d = sum(q[0] for q in L) / len(L)
        heel = d if heel is None else heel
        rows.append((u, d))
    tip = pair.tip
    out = [(u, (d - heel) / (tip - heel)) for u, d in rows]
    out[-1] = (out[-1][0], 1.0)                        # торец — кончик
    return out


def interp(rows, x, a=0, b=1):
    """Кусочно-линейная функция по точкам rows (столбец a → столбец b), за краями — продолжение крайних отрезков."""
    rows = sorted(rows, key=lambda r: r[a])
    for p, q in zip(rows, rows[1:]):
        if x <= q[a] or q is rows[-1]:
            t = (x - p[a]) / (q[a] - p[a]) if q[a] != p[a] else 0.0
            return p[b] + (q[b] - p[b]) * t
    return rows[-1][b]


# ---------------------------------------------------------------- текстуры

def load_texlib():
    import teamart as ta
    return ta.Rw4(rm.source(TEXLIB), TEXLIB)


def tex_of(rw, name):
    ts = [t for t in rw.textures if t.name.startswith(name + '.') or t.name == name]
    if not ts:
        raise SystemExit(f'{TEXLIB}: нет текстуры {name}')
    return ts[0]


def decode(rw, name):
    import kitpaint as kp
    return kp.tex_decode(rw, tex_of(rw, name), 0)         # (w, h, rgba)


def carbon_px(x, y, rnd):
    """Голый крюк: тёмный карбон, лёгкий шум и мелкое плетение."""
    weave = 2 if (x + y) % 2 == 0 else -1
    n = rnd.randint(-1, 1)
    return tuple(max(0, min(255, c + weave + n)) for c in CARBON)


def paint_style(base_rgba, intervals, rows):
    """Текстура варианта: основа (полная лента) + голый крюк вне кусков intervals (доли длины крюка). Граница —
    жёсткая (пиксель либо лента, либо карбон, без смешивания) и поперёк оси крюка (осевой UV: столбец — плоскость)."""
    rnd = random.Random(1)
    px = bytearray(base_rgba)
    for y in range(H):
        for x in range(W):
            if (x + 0.5) / W >= UV_KNOB:
                continue
            f = interp(rows, (x + 0.5) / W)                    # осевой UV: столбец текстуры — плоскость поперёк крюка
            if any(a <= f <= b for a, b in intervals):
                continue
            o = (y * W + x) * 4
            px[o:o + 3] = bytes(carbon_px(x, y, rnd))
            px[o + 3] = 255
    return bytes(px)


def fix_heel(rgba):
    """Код 0: светлые столбцы у края текстуры (пятка ленты до носка) — копией столбцов той же ленты правее."""
    n, src = HEEL_COLS
    px = bytearray(rgba)
    for y in range(H):
        for x in range(n):
            o, s = (y * W + x) * 4, (y * W + src + x) * 4
            px[o:o + 4] = rgba[s:s + 4]
    return bytes(px)


def knob_cols():
    """Столбцы текстуры набалдашника (u центра ≥ UV_KNOB)."""
    return [x for x in range(W) if (x + 0.5) / W >= UV_KNOB]


def white_knob(rgba, src):
    """Набалдашник (столбцы knob_cols, все строки) — из текстуры src (белая лента EA), остальное — как в rgba."""
    px = bytearray(rgba)
    for y in range(H):
        for x in knob_cols():
            o = (y * W + x) * 4
            px[o:o + 4] = src[o:o + 4]
    return bytes(px)


def knob_codes():
    """Коды, у которых набалдашник перерисовывается (не совпадает с KNOB_FROM): при KNOB_WHITE — 0 и цвета EA."""
    if not KNOB_WHITE:
        return ()
    return tuple(c for c in sorted(set(STYLES) | set(EA_COLORS)) if c != KNOB_FROM and STYLES.get(c, (0,))[0] != 1)


# перерисовываются: варианты STYLES (1 — белая EA — как есть) и, при KNOB_WHITE, цвета EA (набалдашник)
REDRAWN = tuple(sorted(set(c for c in STYLES if c != 1) | set(knob_codes())))


def build(args):
    import kitpaint as kp
    out = out_root(args)
    rows = blade_mapping()
    rw = load_texlib()
    pngdir = os.path.join(out, 'png')
    os.makedirs(pngdir, exist_ok=True)
    bases = {c: decode(rw, TAPE_TEX.format(c))[2] for c in (0, 1)}
    knob_src = decode(rw, TAPE_TEX.format(KNOB_FROM))[2]
    man = {'game': rm.PROFILE.name, 'texlib': TEXLIB, 'mapping_u_frac': [[round(u, 4), round(f, 4)] for u, f in rows],
           'styles': {}, 'knob': {'white': KNOB_WHITE, 'from': KNOB_FROM, 'uv_u_from': UV_KNOB,
                                  'cols': [knob_cols()[0], knob_cols()[-1]], 'codes': list(knob_codes())}}
    for code, (base, iv, name) in sorted(STYLES.items()):
        rgba = bases[1] if code == 1 else fix_heel(bases[0]) if code == 0 else paint_style(bases[base], iv, rows)
        if code in knob_codes():
            rgba = white_knob(rgba, knob_src)
        if code in REDRAWN:
            kp.tex_replace(rw, tex_of(rw, TAPE_TEX.format(code)), rgba, W, H)
        img = kp.Img(W, H, rgba)
        img.save(os.path.join(pngdir, f'sticktape_{code}_cm.png'))
        man['styles'][str(code)] = {'base': base, 'taped': iv, 'name': name,
                                    'u': [[round(interp(rows, a, 1, 0), 4), round(interp(rows, b, 1, 0), 4)]
                                          for a, b in iv]}
    for code, name in sorted(EA_COLORS.items()):         # цвета EA: крюк как есть, набалдашник — белый
        if code not in knob_codes():
            continue
        rgba = white_knob(decode(rw, TAPE_TEX.format(code))[2], knob_src)
        kp.tex_replace(rw, tex_of(rw, TAPE_TEX.format(code)), rgba, W, H)
        kp.Img(W, H, rgba).save(os.path.join(pngdir, f'sticktape_{code}_cm.png'))
        man['styles'][str(code)] = {'base': None, 'taped': [[0.0, 1.0]], 'name': name + ', верх — белый'}
    dst = os.path.join(out, *TEXLIB.split('/'))
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    data = rw.bytes()
    open(dst, 'wb').write(data)
    man['sha1'] = hashlib.sha1(data).hexdigest()
    # проверка: файл читается, 0, 1 и остальные текстуры — байт в байт как у игры
    src = load_texlib()
    chk = __import__('teamart').Rw4(data, dst)
    changed = tuple(f'sticktape_{c}_cm' for c in REDRAWN)
    same = [t.name for t in src.textures if not t.name.startswith(changed)]
    bad = [n for n in same if src.buffer(tex_of(src, n.split('.')[0])) != chk.buffer(tex_of(chk, n.split('.')[0]))]
    if len(data) != len(src.bytes()) or bad:
        raise SystemExit(f'проверка: размер {len(data)} / {len(src.bytes())}, изменились чужие текстуры: {bad}')
    man['unchanged'] = same
    json.dump(man, open(os.path.join(out, 'manifest.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(f'{dst}: sha1 {man["sha1"][:12]}, размер {len(data)} (как у игры), заменены sticktape_{",".join(str(c) for c in REDRAWN)}_cm; '
          f'остальные {len(same)} текстур — байт в байт')
    if not rm.flag(args, '--no-preview'):
        preview(out)


def table(args):
    rows = blade_mapping()
    print('код | основа | замотано (доли длины крюка от пятки) | UV-u | вид')
    for code, (base, iv, name) in sorted(STYLES.items()):
        us = ', '.join(f'{interp(rows, a, 1, 0):.3f}…{interp(rows, b, 1, 0):.3f}' for a, b in iv)
        print(f'{code} | {"белая" if base else "чёрная"} | {iv} | {us} | {name}')
    for code, name in sorted(EA_COLORS.items()):
        print(f'{code} | — | — | — | {name}' + (', крюк не меняется' if code in knob_codes() else ', не меняется'))
    if KNOB_WHITE:
        c = knob_cols()
        print(f'верх клюшки (лента рукояти, u ≥ {UV_KNOB}, столбцы {c[0]}–{c[-1]}): у всех кодов — как у кода {KNOB_FROM} '
              f'(белая EA); перерисовывается у {", ".join(map(str, knob_codes()))}')
    else:
        print('верх клюшки (лента рукояти): цвета своей ленты, как у EA')


# ---------------------------------------------------------------- лист вариантов на крюке

PREVIEW_STICKS = (50, 24)            # текстуры клюшки на листе: Reebok 11K (тёмная) и ещё одна


def preview(out, stick_n=None):
    import base64
    import czkit as cz
    import kitpaint as kp
    import sticktape as stt
    import teamart as ta
    rw = ta.Rw4(open(os.path.join(out, *TEXLIB.split('/')), 'rb').read(), TEXLIB)
    shown = sorted(set(STYLES) | set(knob_codes()))
    tex = {c: kp.Img(*kp.tex_decode(rw, tex_of(rw, TAPE_TEX.format(c)), 0)) for c in shown}
    mdir = os.path.join(rm.models_dir(), 'tape', 'out-bottom2-axial')
    pair = stt.Pair(0, 2)
    if os.path.exists(os.path.join(mdir, *pair.rel_tape.split('/'))):
        stick, tape = stt.load_pair(mdir, pair)
    else:                                           # нет готового мода — собрать в памяти
        tb, sb, _ = stt.build_pair(stt.make_pair('player', 0, 2), stt.ROUNDS['bottom2'], axial_uv=True)
        stick, tape = rm.Mesh(sb, pair.rel_stick), rm.Mesh(tb, pair.rel_tape)
    cams = dict(stt.blade_views(pair))
    views = [('сбоку', cams['сбоку']), ('обратная сторона', cams['сбоку, обратная сторона']),
             ('сверху', cams['сверху'])]
    kv = dict(stt.knob_views(tape, w=300))
    views.append(('верх клюшки (торец)', kv['торец, три четверти']))
    n = stick_n or PREVIEW_STICKS[0]
    import legacy_paths as LP
    cached = LP.legacy_file(f'rendering/playerstick/texlib_{n}.rx2')
    if stick_n and os.path.exists(cached):                # поставленная клюшка (клюшки NHL 27 — в cache: порта)
        srw = ta.Rw4(open(cached, 'rb').read(), cached)
        stick_tex = kp.Img(*kp.tex_decode(srw, [t for t in srw.textures if f'playerstick_{n}_cm' in t.name][0], 0))
    else:
        stick_tex = rm.preview_tex(f'rendering/playerstick/texlib_{n}.rx2', f'playerstick_{n}_cm')
    pdir = os.path.join(out, 'preview')
    os.makedirs(pdir, exist_ok=True)
    cards = []
    for code in shown:
        name = STYLES[code][2] if code in STYLES else EA_COLORS[code] + ', верх — белый'
        cells = []
        for k, (vn, cam) in enumerate(views):
            cv = cz.Canvas(cam.w, cam.h, (64, 66, 74, 255))
            cz.draw_mesh(cv, cam, stt._MV(stick), stick_tex)
            cz.draw_mesh(cv, cam, stt._MV(tape), tex[code])
            fn = f'style_{code}_{k}.png'
            cv.img().save(os.path.join(pdir, fn))
            cells.append((fn, vn, cam.w, cam.h))
        cards.append((code, name, cells))

    def uri(fn):
        return 'data:image/png;base64,' + base64.b64encode(open(os.path.join(pdir, fn), 'rb').read()).decode()
    body = []
    for code, name, cells in cards:
        figs = ''.join(f'<figure><img src="{uri(fn)}" width="{w}" height="{h}"><figcaption>{lab}</figcaption>'
                       f'</figure>' for fn, lab, w, h in cells)
        lab = f'<br><i>«{LABELS[code][1]}»</i>' if code in LABELS else ''
        body.append(f'<div class="card"><div class="code">{code}</div><div class="nm">{name}{lab}</div>{figs}</div>')
    html = ('<!doctype html><html><head><meta charset="utf-8"><style>'
            'body{margin:0;background:#26272c;color:#ddd;font:13px Segoe UI,Arial,sans-serif;padding:12px;width:1336px}'
            'h1{font-size:18px;margin:0 0 4px}p{margin:4px 0 10px;color:#bbb}'
            '.card{display:flex;gap:8px;align-items:center;background:#303138;padding:6px 8px;border-radius:6px;'
            'margin-bottom:6px}.code{font-size:26px;font-weight:600;width:34px;text-align:center}'
            '.nm{width:190px;font-size:13px}figure{margin:0}figcaption{font-size:11px;color:#aaa;text-align:center}'
            '</style></head><body><h1>Варианты обмотки крюка: код sticktapecolor → вид — ' + rm.PROFILE.title
            + '</h1><p>Сетка — мод «низ-2» с осевым UV (лента до кончика, носок скруглён), левый хват, клюшка Reebok 11K. '
            '0 и 1 — как у EA; 3, 4, 6, 8, 9 — новые текстуры (вместо красной, жёлтой, оранжевой, розовой, фиолетовой; '
            'подпись в меню — справа от номера); 2, 5, 7 — цвета EA (синяя, зелёная, голубая), крюк как у EA. Голый крюк — '
            'серый карбон, один на все клюшки. Край ленты — поперёк крюка, жёсткий. У 0 пятка — без светлой полосы EA.'
            + (f' Верх клюшки (лента рукояти) у всех кодов — белый (как у {KNOB_FROM}).' if KNOB_WHITE else '')
            + '</p>' + ''.join(body) + '</body></html>')
    sheet = os.path.join(pdir, 'sheet.png')
    ta.render_html(html, sheet, 1360, 110 + len(cards) * 240)
    print(f'лист: {sheet}')


# ---------------------------------------------------------------- было / стало: верх клюшки и крюк

COMPARE_STICK = 105                  # клюшка на листе сравнения: Vapor FlyLite (слот 105 C — самая частая в базе)
GOALIE_STICK_RGB = (52, 54, 58)      # вратарская клюшка — ровным цветом (её текстура — маска командных цветов)


def _installed_bytes(rel):
    """Файл, который возьмёт игра: из cache: установки (наш мод), иначе — из архивов игры."""
    import legacy_paths as LP
    f = LP.legacy_file(rel) if not rm.is_nhl13() else None
    return open(f, 'rb').read() if f and os.path.exists(f) else rm.source(rel)


def _mesh_installed(rel):
    return rm.Mesh(_installed_bytes(rel), rel)


def compare_sets():
    """[(подпись, Pair для видов крюка, клюшка, [ленты], лента с набалдашником, вид)] — все клюшки с лентой игры."""
    import sticktape as stt
    out = []
    for kind, h, v in stt.pairs():
        rel_s, rel_t = stt.pair_rels(kind, h, v)
        st = _mesh_installed(rel_s)
        tp = _mesh_installed(rel_t)
        pair = stt.Pair(h, v, kind=kind)
        lab = {'player': 'полевая', 'goalie': 'вратарская', 'goalieprop': 'вратарская (реквизит)'}[kind]
        hand = ('левый', 'правый')[h]
        out.append((f'{lab} {os.path.basename(rel_t)[:-4]} — хват {hand}', pair, st, [tp], tp, kind))
    if stt.has_dropped():
        data = _installed_bytes(stt.DROPPED)
        subs = stt.dropped_subs(data)
        for side in stt.SIDES:
            pair = stt.dropped_pair(rm.source(stt.DROPPED), side)
            st = rm.Mesh(data, stt.DROPPED, sub=subs[side]['shaft'])
            tps = [rm.Mesh(data, stt.DROPPED, sub=subs[side][k]) for k in ('heel_tape', 'shaft_tape')]
            out.append((f'клюшка на льду droppedstick_0 — {side}', pair, st, tps, tps[1], 'dropped'))
    return out


def compare(args):
    """Лист «было / стало»: текстуры ленты из --before (по умолчанию — поставленный texlib_999 в cache:) и из DIR."""
    import base64
    import czkit as cz
    import kitpaint as kp
    import sticktape as stt
    import teamart as ta
    import legacy_paths as LP
    out = out_root(args)
    after_f = os.path.join(out, *TEXLIB.split('/'))
    before_f = rm.opt(args, '--before') or (LP.legacy_file(TEXLIB) if not rm.is_nhl13() else None)
    if not before_f or not os.path.exists(before_f):
        raise SystemExit(f'нет файла «было»: {before_f} (--before FILE)')
    if not os.path.exists(after_f):
        raise SystemExit(f'нет файла «стало»: {after_f} (сначала build)')
    codes = [int(c) for c in (rm.opt(args, '--codes') or '0,1').split(',')]
    sn = int(rm.opt(args, '--stick') or COMPARE_STICK)
    texs = {}
    for tag, f in (('было', before_f), ('стало', after_f)):
        rw = ta.Rw4(open(f, 'rb').read(), TEXLIB)
        texs[tag] = {c: kp.Img(*kp.tex_decode(rw, tex_of(rw, TAPE_TEX.format(c)), 0)) for c in codes}
    cached = LP.legacy_file(f'rendering/playerstick/texlib_{sn}.rx2') if not rm.is_nhl13() else ''
    if cached and os.path.exists(cached):
        srw = ta.Rw4(open(cached, 'rb').read(), cached)
        stick_tex = kp.Img(*kp.tex_decode(srw, [t for t in srw.textures if f'playerstick_{sn}_cm' in t.name][0], 0))
    else:
        sn = PREVIEW_STICKS[0]
        stick_tex = rm.preview_tex(f'rendering/playerstick/texlib_{sn}.rx2', f'playerstick_{sn}_cm')
    pdir = os.path.join(out, 'preview', 'compare')
    os.makedirs(pdir, exist_ok=True)
    bg = (64, 66, 74, 255)

    def draw(cam, st, tps, kind, tx, fn):
        cv = cz.Canvas(cam.w, cam.h, bg)
        if kind in ('goalie', 'goalieprop'):
            cz.draw_mesh(cv, cam, stt._MV(st), color=GOALIE_STICK_RGB)
        else:
            cz.draw_mesh(cv, cam, stt._MV(st), stick_tex)
        for tp in tps:
            cz.draw_mesh(cv, cam, stt._MV(tp), tx)
        cv.img().save(os.path.join(pdir, fn))
        return fn

    def uri(fn):
        return 'data:image/png;base64,' + base64.b64encode(open(os.path.join(pdir, fn), 'rb').read()).decode()

    def fig(fn, cam, cap):
        return f'<figure><img src="{uri(fn)}" width="{cam.w}" height="{cam.h}"><figcaption>{cap}</figcaption></figure>'
    sets = compare_sets()
    css = ('body{margin:0;background:#26272c;color:#ddd;font:13px Segoe UI,Arial,sans-serif;padding:12px;width:%dpx}'
           'h1{font-size:18px;margin:0 0 4px}p{margin:4px 0 10px;color:#bbb}h2{font-size:15px;margin:12px 0 4px}'
           '.row{display:flex;gap:8px;align-items:center;background:#303138;padding:6px 8px;border-radius:6px;'
           'margin-bottom:6px}.tag{width:70px;font-size:16px;font-weight:600}.tag.after{color:#9fe09f}'
           'figure{margin:0}figcaption{font-size:11px;color:#aaa;text-align:center}.lab{width:250px;font-size:12px}'
           '</style>')
    names = {0: 'чёрная лента (0)', 1: 'белая лента (1)'}
    # 1) крупно: полевая _2, левый хват — верх и крюк, было / стало
    lab0, pair0, st0, tps0, knob0, kind0 = sets[0]
    kv = stt.knob_views(knob0, w=420)
    bv = dict(stt.blade_views(pair0))
    big = [(kv[0][1], 'верх клюшки, широкая сторона'), (kv[2][1], 'торец, три четверти'),
           (bv['сбоку'], 'крюк сбоку'), (bv['носок крупно'], 'носок крупно')]
    body = []
    for c in codes:
        body.append(f'<h2>{names.get(c, f"код {c}")}</h2>')
        for tag in ('было', 'стало'):
            figs = ''.join(fig(draw(cam, st0, tps0, kind0, texs[tag][c], f'big_{c}_{tag}_{k}.png'), cam, cap)
                           for k, (cam, cap) in enumerate(big))
            body.append(f'<div class="row"><div class="tag{" after" if tag == "стало" else ""}">{tag}</div>{figs}</div>')
    html = ('<!doctype html><html><head><meta charset="utf-8"><style>' + css % 1376
            + f'<body><h1>Верх клюшки (лента рукояти): было / стало — {rm.PROFILE.title}</h1><p>Полевая клюшка _2, '
            f'левый хват, сетки — как стоят в игре (лента до кончика, «низ-2»), клюшка — texlib_{sn}. «Было» — '
            f'{os.path.relpath(before_f, os.path.dirname(rm.game_dir()))}, «стало» — новая texlib_999.</p>' + ''.join(body)
            + '</body></html>')
    sheet = os.path.join(out, 'preview', 'compare.png')
    hh = sum(max(cam.h for cam, _ in big) + 34 for _ in range(2 * len(codes))) + 60 * len(codes) + 70
    ta.render_html(html, sheet, 1400, hh)
    print(f'лист: {sheet}')
    # 2) все клюшки: верх и крюк, чёрная лента (первый код) — было / стало
    c = codes[0]
    rows, hh = [], 70
    for k, (lab, pair, st, tps, knob, kind) in enumerate(sets):
        kv = stt.knob_views(knob, w=300)
        bvs = dict(stt.blade_views(pair))
        cells = []
        for tag in ('было', 'стало'):
            cells.append(fig(draw(kv[0][1], st, tps, kind, texs[tag][c], f'all_{k}_{tag}_side.png'), kv[0][1],
                             f'{tag}: верх'))
            cells.append(fig(draw(kv[2][1], st, tps, kind, texs[tag][c], f'all_{k}_{tag}_butt.png'), kv[2][1],
                             f'{tag}: торец'))
        cam = bvs['сбоку']
        cam = stt.Cam(cam.R, cam.U, cam.c, cam.hw, 220, 147)
        cells.append(fig(draw(cam, st, tps, kind, texs['стало'][c], f'all_{k}_blade.png'), cam, 'стало: крюк'))
        rows.append(f'<div class="row"><div class="lab">{lab}</div>{"".join(cells)}</div>')
        hh += max(kv[0][1].h, kv[2][1].h, cam.h) + 34
    html = ('<!doctype html><html><head><meta charset="utf-8"><style>' + css % 1636
            + f'<body><h1>Верх клюшки у всех сеток с лентой — {names.get(c, f"код {c}")}, было / стало — '
            f'{rm.PROFILE.title}</h1><p>Сетки — как стоят в игре (cache:), иначе EA. Вратарская клюшка — ровным '
            'цветом (её цвет — командный).</p>' + ''.join(rows) + '</body></html>')
    sheet2 = os.path.join(out, 'preview', 'compare-all.png')
    ta.render_html(html, sheet2, 1660, hh)
    print(f'лист: {sheet2}')


def main():
    args = rm.take_game(sys.argv[1:])
    if not args:
        print(__doc__)
        return
    cmd = args.pop(0)
    if cmd == 'table':
        table(args)
    elif cmd == 'build':
        build(args)
    elif cmd == 'preview':
        s = rm.opt(args, '--stick')
        preview(out_root(args), int(s) if s else None)
    elif cmd == 'compare':
        compare(args)
    else:
        print(__doc__)
        sys.exit(2)


if __name__ == '__main__':
    main()
