"""Варианты обмотки крюка: свободные коды sticktapecolor (2–9) — частичная обмотка белой и чёрной лентой.

    python tapestyles.py table                         # таблица «код → вид обмотки» и границы по UV
    python tapestyles.py build [--out DIR] [--no-preview]
                                                       # texlib_999.rx2 с новыми текстурами sticktape_2…9_cm в
                                                       # раскладке cache: (DIR/rendering/playerstick/), картинки
                                                       # текстур (DIR/png) и лист вариантов на крюке
    python tapestyles.py preview [--out DIR]           # только лист (по готовому texlib_999 из DIR)

У всех команд — опция --game {nhl13,legacy} (или NHL_GAME, tools/gameprofile.py), по умолчанию — как у rw4mesh
(NHL 13); собирается под NHL Legacy: --game legacy. Выход по умолчанию — game/work/models/tapevar/<игра>/out.

Как устроено (разбор — docs/player-models.md §9, §13). Цвет ленты — текстура sticktape_<код>_cm (128×64 DXT1 +
мипы) из rendering/playerstick/texlib_999.rx2; код — поле exhibitionskaterequipment.sticktapecolor (у вратарей —
exhibitiongoalieequipment); в базах NHL 13 и Legacy заняты только 0 (чёрная) и 1 (белая), 2–9 — цвета, которые
никто не носит. Сетка ленты — это сама поверхность средней части крюка (у мода sticktape.py — до кончика носка),
UV-u идёт вдоль крюка: у мода «низ-2» от пятки (кольцо 0, u = 0,018) до кончика (u ≈ 0,684), правее 0,696 —
рисунок набалдашника; UV-v — по кругу сечения. Значит, частичную обмотку можно нарисовать в текстуре: там, где
ленты нет, — голый крюк (тёмный карбон), сетки не меняются. Голый крюк один на все клюшки (текстура ленты не знает
модели клюшки): тёмно-серый карбон. Границы — доли длины крюка от пятки к кончику; переводятся в u по сетке мода
(кольца ленты, sticktape.py «низ-2», для _2 и _4 одинаково, обе руки — зеркало с теми же UV). Край ленты — косой
(лента идёт по спирали) с тонкой тенью. Набалдашник — как у полной ленты того же цвета.

Только стандартная библиотека (+ Chrome/Edge без окна — подписи листа, как в teamart/sticktape).
"""
import hashlib, json, math, os, random, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rw4mesh as rm  # noqa: E402

TEXLIB = 'rendering/playerstick/texlib_999.rx2'
TAPE_TEX = 'sticktape_{}_cm'
W, H = 128, 64

# код → (основа: 0 чёрная / 1 белая, замотанные куски — доли длины крюка от пятки (0) к кончику (1), подпись).
# 0 и 1 — как у EA (полная лента), не перерисовываются.
STYLES = {
    0: (0, [(0.0, 1.0)], 'чёрная, весь крюк (EA)'),
    1: (1, [(0.0, 1.0)], 'белая, весь крюк (EA; так у Кейна)'),
    2: (1, [(0.45, 1.0)], 'белая, от середины до носка, пятка голая (Бенн)'),
    3: (1, [(0.30, 0.87)], 'белая, середина: пятка и носок голые (Селебрини)'),
    4: (1, [(0.0, 0.87)], 'белая, носок голый (~3 см)'),
    5: (1, [(0.55, 0.85)], 'белая, узкая полоса ближе к носку'),
    6: (0, [(0.45, 1.0)], 'чёрная, от середины до носка, пятка голая (Овечкин, Лайне)'),
    7: (0, [(0.30, 0.87)], 'чёрная, середина: пятка и носок голые'),
    8: (0, [(0.0, 0.87)], 'чёрная, носок голый (~3 см)'),
    9: (1, [(0.25, 1.0)], 'белая, голая только пятка (четверть крюка)'),
}
EDGE_SLANT = 0.035          # край ленты косой: сдвиг границы по длине крюка поперёк лицевой стороны (доля длины)
CARBON = (21, 22, 25)       # голый крюк: чёрный карбон (темнее чёрной ленты — она матовая, светлее)
UV_KNOB = 0.69              # правее — набалдашник (не трогается)


def out_root(args=None):
    d = rm.opt(args, '--out') if args is not None else None
    return d or os.path.join(rm.game_dir(), 'work', 'models', 'tapevar', rm.PROFILE.name, 'out')


# ---------------------------------------------------------------- доля длины крюка ↔ UV-u (по сетке мода)

def blade_mapping():
    """Кольца ленты крюка у мода «низ-2» (_2, левый хват): [(u, доля длины от пятки к кончику)], по возрастанию u.
    Сетка мода собирается в памяти (sticktape.build_pair), без файлов."""
    import sticktape as stt
    pair = stt.make_pair('player', 0, 2)
    tb, _, _ = stt.build_pair(pair, stt.ROUNDS['bottom2'])
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
    """Голый крюк: тёмный карбон, чуть светлее у кромок (по v), лёгкий шум и косое плетение 2×2."""
    weave = 2 if (x + y) % 2 == 0 else -1
    n = rnd.randint(-1, 1)
    return tuple(max(0, min(255, c + weave + n)) for c in CARBON)


def paint_style(base_rgba, intervals, rows):
    """Текстура варианта: основа (полная лента) + голый крюк вне кусков intervals (доли длины крюка). Край ленты —
    косой на лицевых сторонах, сглажен (покрытие пикселя — по 4×4 подточкам) и чуть темнее у самой кромки (толщина
    ленты)."""
    rnd = random.Random(1)
    px = bytearray(base_rgba)
    # сечение по v: верхняя кромка ~0,12–0,15, лицо A, нижняя кромка ~0,41–0,49, лицо B, верхняя кромка ~0,84–0,89;
    # на лицах край ленты косой (лента идёт по спирали), на кромках — прямой
    def slant(v):
        if 0.15 <= v <= 0.41:
            return (v - 0.28) / 0.13
        if 0.49 <= v <= 0.84:
            return -(v - 0.665) / 0.175
        return 0.0

    def edges(v):
        s_ = slant(v) * EDGE_SLANT
        return [(a - s_ if a > 0 else -1.0, b + s_ if b < 1 else 2.0) for a, b in intervals]
    f_px = {}
    for x in range(W):
        for k in range(4):
            u = (x + (k + 0.5) / 4) / W
            f_px[(x, k)] = interp(rows, u)
    df = abs(interp(rows, 1.0 / W) - interp(rows, 0.0))         # доля длины крюка на пиксель
    for y in range(H):
        for x in range(W):
            if (x + 0.5) / W >= UV_KNOB:
                continue
            cov, dist = 0, 9.0
            for j in range(4):
                v = (y + (j + 0.5) / 4) / H
                ee = edges(v)
                for k in range(4):
                    f = f_px[(x, k)]
                    if any(a <= f <= b for a, b in ee):
                        cov += 1
                    for a, b in ee:
                        dist = min(dist, abs(f - a), abs(f - b))
            c = cov / 16
            o = (y * W + x) * 4
            car = carbon_px(x, y, rnd)
            tape = list(px[o:o + 3])
            if c > 0 and dist < 1.2 * df:                       # кромка ленты — темнее
                tape = [int(t * 0.82) for t in tape]
            for i in range(3):
                px[o + i] = int(round(tape[i] * c + car[i] * (1 - c)))
            px[o + 3] = 255
    return bytes(px)


def build(args):
    import kitpaint as kp
    out = out_root(args)
    rows = blade_mapping()
    rw = load_texlib()
    pngdir = os.path.join(out, 'png')
    os.makedirs(pngdir, exist_ok=True)
    bases = {c: decode(rw, TAPE_TEX.format(c))[2] for c in (0, 1)}
    man = {'game': rm.PROFILE.name, 'texlib': TEXLIB, 'mapping_u_frac': [[round(u, 4), round(f, 4)] for u, f in rows],
           'styles': {}}
    for code, (base, iv, name) in sorted(STYLES.items()):
        rgba = bases[base] if code in (0, 1) else paint_style(bases[base], iv, rows)
        if code not in (0, 1):
            kp.tex_replace(rw, tex_of(rw, TAPE_TEX.format(code)), rgba, W, H)
        img = kp.Img(W, H, rgba)
        img.save(os.path.join(pngdir, f'sticktape_{code}_cm.png'))
        man['styles'][str(code)] = {'base': base, 'taped': iv, 'name': name,
                                    'u': [[round(interp(rows, a, 1, 0), 4), round(interp(rows, b, 1, 0), 4)]
                                          for a, b in iv]}
    dst = os.path.join(out, *TEXLIB.split('/'))
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    data = rw.bytes()
    open(dst, 'wb').write(data)
    man['sha1'] = hashlib.sha1(data).hexdigest()
    # проверка: файл читается, 0, 1 и остальные текстуры — байт в байт как у игры
    src = load_texlib()
    chk = __import__('teamart').Rw4(data, dst)
    same = [t.name for t in src.textures if not t.name.startswith(('sticktape_2', 'sticktape_3', 'sticktape_4',
                                                                   'sticktape_5', 'sticktape_6', 'sticktape_7',
                                                                   'sticktape_8', 'sticktape_9'))]
    bad = [n for n in same if src.buffer(tex_of(src, n.split('.')[0])) != chk.buffer(tex_of(chk, n.split('.')[0]))]
    if len(data) != len(src.bytes()) or bad:
        raise SystemExit(f'проверка: размер {len(data)} / {len(src.bytes())}, изменились чужие текстуры: {bad}')
    man['unchanged'] = same
    json.dump(man, open(os.path.join(out, 'manifest.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(f'{dst}: sha1 {man["sha1"][:12]}, размер {len(data)} (как у игры), заменены sticktape_2…9_cm; '
          f'остальные {len(same)} текстур — байт в байт')
    if not rm.flag(args, '--no-preview'):
        preview(out)


def table(args):
    rows = blade_mapping()
    print('код | основа | замотано (доли длины крюка от пятки) | UV-u | вид')
    for code, (base, iv, name) in sorted(STYLES.items()):
        us = ', '.join(f'{interp(rows, a, 1, 0):.3f}…{interp(rows, b, 1, 0):.3f}' for a, b in iv)
        print(f'{code} | {"белая" if base else "чёрная"} | {iv} | {us} | {name}')


# ---------------------------------------------------------------- лист вариантов на крюке

PREVIEW_STICKS = (50, 24)            # текстуры клюшки на листе: Reebok 11K (тёмная) и ещё одна


def preview(out):
    import base64
    import czkit as cz
    import kitpaint as kp
    import sticktape as stt
    import teamart as ta
    rw = ta.Rw4(open(os.path.join(out, *TEXLIB.split('/')), 'rb').read(), TEXLIB)
    tex = {c: kp.Img(*kp.tex_decode(rw, tex_of(rw, TAPE_TEX.format(c)), 0)) for c in STYLES}
    mdir = os.path.join(rm.models_dir(), 'tape', 'out-bottom2')
    pair = stt.Pair(0, 2)
    if os.path.exists(os.path.join(mdir, *pair.rel_tape.split('/'))):
        stick, tape = stt.load_pair(mdir, pair)
    else:                                           # нет готового мода — собрать в памяти
        tb, sb, _ = stt.build_pair(stt.make_pair('player', 0, 2), stt.ROUNDS['bottom2'])
        stick, tape = rm.Mesh(sb, pair.rel_stick), rm.Mesh(tb, pair.rel_tape)
    cams = dict(stt.blade_views(pair))
    views = [('сбоку', cams['сбоку']), ('обратная сторона', cams['сбоку, обратная сторона']),
             ('сверху', cams['сверху'])]
    stick_tex = rm.preview_tex(f'rendering/playerstick/texlib_{PREVIEW_STICKS[0]}.rx2',
                               f'playerstick_{PREVIEW_STICKS[0]}_cm')
    pdir = os.path.join(out, 'preview')
    os.makedirs(pdir, exist_ok=True)
    cards = []
    for code, (base, iv, name) in sorted(STYLES.items()):
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
        body.append(f'<div class="card"><div class="code">{code}</div><div class="nm">{name}</div>{figs}</div>')
    html = ('<!doctype html><html><head><meta charset="utf-8"><style>'
            'body{margin:0;background:#26272c;color:#ddd;font:13px Segoe UI,Arial,sans-serif;padding:12px;width:1176px}'
            'h1{font-size:18px;margin:0 0 4px}p{margin:4px 0 10px;color:#bbb}'
            '.card{display:flex;gap:8px;align-items:center;background:#303138;padding:6px 8px;border-radius:6px;'
            'margin-bottom:6px}.code{font-size:26px;font-weight:600;width:34px;text-align:center}'
            '.nm{width:190px;font-size:13px}figure{margin:0}figcaption{font-size:11px;color:#aaa;text-align:center}'
            '</style></head><body><h1>Варианты обмотки крюка: код sticktapecolor → вид — ' + rm.PROFILE.title
            + '</h1><p>Сетка — мод «низ-2» (лента до кончика, носок скруглён), левый хват, клюшка Reebok 11K. 0 и 1 — '
            'как у EA; 2–9 — новые текстуры (вместо синей, красной, жёлтой, зелёной, оранжевой, голубой, розовой, '
            'фиолетовой). Голый крюк — тёмный карбон, один на все клюшки.</p>' + ''.join(body) + '</body></html>')
    sheet = os.path.join(pdir, 'sheet.png')
    ta.render_html(html, sheet, 1200, 90 + len(cards) * 232)
    print(f'лист: {sheet}')


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
        preview(out_root(args))
    else:
        print(__doc__)
        sys.exit(2)


if __name__ == '__main__':
    main()
