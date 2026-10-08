"""Своя форма NHL 13 (Xbox 360) из шаблонного комплекта EA: разбор в PNG по слоям, сборка .rx2/.big
под свой номер, быстрая перекраска по SPEC (зоны цвета шаблона → цвета клуба, свой логотип из SVG).

    python kitpaint.py files S_A_V[_F]…                  # файлы комплекта: текстуры, форматы, мипы
    python kitpaint.py unpack S_A_V[_F] DIR               # все слои комплекта → DIR/<слой>.png + DIR/kit.json
    python kitpaint.py pack DIR S_A_V[_F] OUTDIR [--reencode] [--container S_A_V]
                                                          # PNG из DIR → файлы комплекта под номер S_A_V
                                                          # (раскладка cache:); слой без изменений — байты шаблона
    python kitpaint.py roundtrip S_A_V[_F]…               # шаблон → PNG → сборка: байт-в-байт и с пережатием (PSNR)
    python kitpaint.py paint SPEC.json OUTDIR [--kits home,away] [--preview DIR] [--work DIR] [--mask-game nhl13]
                                                          # перекраска шаблонов по SPEC → готовые комплекты
                                                          # (--mask-game — маски разметки из шаблонов другой игры)
    python kitpaint.py verify OUTDIR NEW=TEMPLATE…        # собранное против шаблона (1_98_0=1_28_0 …; с контейнером —
                                                          # против контейнера: 1_100_0=1_131_0)
    python kitpaint.py sheet OUTDIR "Заголовок" "подпись=S_A_V[_F]"… OUT.png
                                                          # лист превью собранных комплектов (Chrome/Edge)
    … --game legacy                                       # у любой команды: шаблоны и контейнеры NHL Legacy (ниже)

Комплект S_A_V_F: S — style, A — номер арта (у команды EA = teamartid = artid), V — variant, F — fevariant
(по умолчанию = V). Файлы (docs/uniforms.md): rendering/jersey/texlib_S_A_V.rx2 (свитер jersey_cm DXT1,
jersey_sm DXT1, jersey_nm DXN; шрифт номеров font_cm DXT5, font_nm DXN, font_sm DXT1),
rendering/jersey/name_S_A_V_cm.rx2 (карта номера/фамилии, 8888), rendering/pant/texlib_S_A_V.rx2 (шорты),
rendering/sock/sock_S_A_V_cm.rx2 (гетры), fe/ion/artassets/jerseys/jersey_S_A_F.big (превью меню 8888).
Наклейка на шлем (rendering/logo/texlib_A_S_V.rx2) не делается: helmetlogo = 0.

Слои PNG: цвет — RGBA как есть; нормали (DXN) — R = X, G = Y, B = восстановленный Z (при сборке берутся
R и G). Сборка: контейнер шаблона, пиксели — из PNG с полной цепочкой мипов (у Xenos хвост ≤ 16 текселей
упакован — раскладка teamart.Layout), имена растров S_A_V → новый номер (та же длина). DXT1 с прозрачными
пикселями — режим 1-битной альфы (как font_sm у EA), DXT5 — цвет и под прозрачным (как font_cm у EA).

SPEC (JSON; пример — game/work/uniforms/kitsrc/SEA.json, VGK.json):
  colors — палитра {имя: "#RRGGBB"}; svg — {имя: {"file" (от SPEC), "strip_paths": [номера <path>],
  "cut": [[номер path, "начало хвоста d"]], "recolor": {"#старый": "#новый"}}};
  kits — {имя: {"template": "1_28_0", "kit": "1_98_0", "label", "jersey", "font", "pant", "sock", "fe"}}.
  jersey / pant / sock / fe — перекраска слоя cm (у fe — картинка меню):
    zones {зона: [r, g, b]} — цвета шаблона (уточняются по картинке); первая — фон (body);
    map {зона: цвет} — новые цвета ("keep" — как в шаблоне); regions — [{"rect" | "mask", "map", "minw"}]
    (позже в списке — главнее; mask — заливка по слою другого шаблона: {"template", "seed", "thr", "dilate",
    "ring"}); bands — полосы поперёк группы зон [{"rect", "zones", "axis", "edge", "units", "start",
    "smooth", "fill", "bands": [[от, до, цвет]]}]; erase — старые логотипы [{"rect", "thr", "dilate",
    "holes", "all"}] (стираются в cm, sm и nm: гладкий фон + узор трикотажа); logos — [{"svg", "center",
    "size", "rotate"}] (на cm — рисунок, на sm — блеск вышивки, на nm — рельеф); relief — сила рельефа.
    fe дополнительно: snap, blur, keep_alpha (тёмный шаблон → светлая форма без «крапин»).
  font — {"fill", "outline", "outline_px": {"letters", "big", "small"}}: обводка внутрь глифа (форма и
  клетки атласа не меняются). pant — или {"same_as": "home"}.

Шаблоны — из game/extracted/big/<архив>/…, иначе — из образа диска game/extracted/disc/<архив>.big (с
кешем разжатых файлов в game/work/uniforms/templates/). Только стандартная библиотека (+ Chrome/Edge для
SVG и листов превью, как в teamart.py). teamart.py используется как библиотека.

Другая игра: --game {nhl13,legacy} (или NHL_GAME, tools/gameprofile.py) у всех команд — шаблоны и контейнеры из
её распакованных архивов (у NHL Legacy — game/other/legacy/big/<архив>/…); по умолчанию NHL 13, как раньше.
Номер другой длины (Legacy: арт 100/101 вместо 98/99): имена растров на месте не переписать, поэтому файлы
собираются в контейнере (заголовки, имена, форматы, мипы) комплекта EA той же структуры с номером нужной длины
(CONTAINERS, «container» в SPEC или --container S_A_V), а пиксели слоёв, которые не перекрашиваются, — буферы
шаблона как есть. SPEC может наследовать другой: {"base": "…/SEA.json", "kits": {"home": {"kit": "1_100_0"}}}
(teamart.load_spec).
"""
import hashlib, json, math, os, re, shutil, struct, sys, tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import playerhead as ph  # noqa: E402  (PNG, DXT5, BIGF/XPR2)
import teamart as ta     # noqa: E402  (RW4, раскладка Xenos, DXT1/3/5, 8888, рендер SVG)
import gameprofile       # noqa: E402  (профиль игры: NHL 13 или NHL Legacy)

FMT_DXN = 0x31
FMT_NAMES = {ta.FMT_8888: '8888', ta.FMT_DXT1: 'DXT1', ta.FMT_DXT3: 'DXT3', ta.FMT_DXT5: 'DXT5', FMT_DXN: 'DXN'}

# ---------------------------------------------------------------- комплект и шаблоны

KIT_FILES = [   # вид, путь (s — style, a — номер арта, v — variant, f — fevariant)
    ('jersey', 'rendering/jersey/texlib_{s}_{a}_{v}.rx2'),
    ('name', 'rendering/jersey/name_{s}_{a}_{v}_cm.rx2'),
    ('pant', 'rendering/pant/texlib_{s}_{a}_{v}.rx2'),
    ('sock', 'rendering/sock/sock_{s}_{a}_{v}_cm.rx2'),
    ('fe', 'fe/ion/artassets/jerseys/jersey_{s}_{a}_{f}.big'),
]


class Kit:
    """Номер комплекта: style, art, variant, fevariant."""

    def __init__(self, s, a, v, f=None):
        self.s, self.a, self.v = int(s), int(a), int(v)
        self.f = self.v if f is None else int(f)

    @classmethod
    def parse(cls, text):
        p = [int(x) for x in re.split(r'[_,]', str(text).strip())]
        if len(p) not in (3, 4):
            raise SystemExit(f'номер комплекта S_A_V[_F], а не «{text}»')
        return cls(*p)

    def path(self, kind):
        pat = dict(KIT_FILES)[kind]
        return pat.format(s=self.s, a=self.a, v=self.v, f=self.f)

    def tag(self):
        return f'{self.s}_{self.a}_{self.v}'

    def __str__(self):
        return self.tag() + (f'_{self.f}' if self.f != self.v else '')


def game_dir():
    return ph.game_dir()


def archive_of(rel):
    if rel.startswith('rendering/jersey/'):
        return 'nocacherender'
    if rel.startswith('rendering/'):
        return 'cacherender'
    return 'cache'


_DISC = {}


def _disc_entries(arc):
    if arc not in _DISC:
        from pathlib import Path
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                        'ref', 'nhl-legacy-recomp', 'docs', 'nhl12-decomp-reference', 'tools'))
        import unpack_big
        path = os.path.join(game_dir(), 'extracted', 'disc', arc + '.big')
        big = unpack_big.parse_bigeb(Path(path))
        _DISC[arc] = (path, {e.path: e for e in big.entries}, unpack_big)
    return _DISC[arc]


def _unchunk(blob):
    if blob[:8] in (b'chunklzx', b'chunkzip'):
        import unchunk
        return unchunk.unchunk(blob)
    return blob


def profile_source(rel, prof=None):
    """Разжатый файл другой игры (prof или teamart.set_game) из её распакованных архивов (gameprofile)."""
    prof = prof or ta.GAME
    p = prof.extracted(rel)
    if not p:
        raise SystemExit(f'{rel}: нет в распакованных архивах {prof.title} ({prof.big})')
    return _unchunk(open(p, 'rb').read())


def source(rel, game=None):
    """Разжатый файл игры по пути архива (rendering/…, fe/…): распакованное дерево, кеш, образ диска. Другая игра
    (teamart.set_game или game — имя игры) — из её распакованных архивов."""
    g = game or ta.game_name()
    if g != 'nhl13':
        return profile_source(rel, gameprofile.get(g) if game else None)
    g = game_dir()
    arc = archive_of(rel)
    for p in (os.path.join(g, 'extracted', 'big', arc, *rel.split('/')),
              os.path.join(g, 'work', 'uniforms', 'templates', *rel.split('/'))):
        if os.path.exists(p):
            return _unchunk(open(p, 'rb').read())
    path, entries, unpack_big = _disc_entries(arc)
    e = entries.get(rel)
    if e is None:
        raise SystemExit(f'{rel}: нет в {arc}.big')
    with open(path, 'rb') as f:
        f.seek(e.offset)
        blob = f.read(e.stored_size)
    if e.is_packed:
        blob = unpack_big.decompress_packed_member(blob, e.unpacked_size)
    blob = _unchunk(blob)
    cache = os.path.join(g, 'work', 'uniforms', 'templates', *rel.split('/'))
    os.makedirs(os.path.dirname(cache), exist_ok=True)
    open(cache, 'wb').write(blob)
    return blob


def layer_name(raster):
    """'jersey_1_28_0_0_nm.Raster' → 'jersey_nm', 'font_1_28_0_cm.Raster' → 'font_cm'."""
    base = raster.split('.')[0]
    parts = base.split('_')
    return parts[0] + '_' + parts[-1]


# Контейнеры под номер арта другой длины: комплект EA, у которого все 5 файлов устроены как у 1_28_0 (заголовки,
# описания текстур, буферы, форматы и мипы; отличаются только имена растров). Ключ — число цифр номера арта.
# NHL Legacy: 3-значные — клубы АХЛ 131…165 и CHL 360…421 (проверено перебором всех комплектов стиля 1); взят
# 1_131_0. Для NHL 13 не нужен (98/99 — 2-значные, как шаблоны).
CONTAINERS = {'nhl13': {}, 'legacy': {3: '1_131_0'}}


def default_container(template, new):
    """Контейнер для комплекта new: сам template, если номер той же длины, иначе CONTAINERS игры."""
    if len(template.tag()) == len(new.tag()):
        return template
    tag = CONTAINERS.get(ta.game_name(), {}).get(len(str(new.a)))
    if not tag:
        raise SystemExit(f'{template} → {new}: номера разной длины, а контейнера под {len(str(new.a))}-значный номер '
                         f'для {ta.game_name()} нет — укажите container (SPEC) или --container')
    cont = Kit.parse(tag)
    if len(cont.tag()) != len(new.tag()):
        raise SystemExit(f'контейнер {cont} не той длины, что {new}')
    return cont


def rename_rasters(rw, old, new):
    """S_A_V шаблона → S_A_V нового комплекта в именах растров (на месте, той же длины)."""
    a, b = f'_{old.tag()}_', f'_{new.tag()}_'
    if len(a) != len(b):
        raise SystemExit(f'номера {old.tag()} и {new.tag()} разной длины — имена растров не переписать на месте')
    done = 0
    for i, (sp, ln) in enumerate(rw.name_slots):
        s = bytes(rw.raw[sp:sp + ln]).decode('latin1')
        if a not in s:
            raise SystemExit(f'{s}: нет «{a}»')
        t = s.replace(a, b, 1)
        rw.raw[sp:sp + ln] = t.encode('latin1')
        if i < len(rw.textures):
            rw.textures[i].name = t
        done += 1
    return done


# ---------------------------------------------------------------- кодеки (DXN = BC5 и обёртки над teamart)

def _bc4_decode(b8):
    pal = ph._alpha_palette(b8[0], b8[1])
    bits = int.from_bytes(b8[2:8], 'little')
    return [pal[(bits >> (3 * k)) & 7] for k in range(16)]


def dxn_decode(blocks, w, h):
    """Линейные блоки DXN (после 8in16) → RGBA: R = X, G = Y (первый и второй блок BC4), B = Z, A = 255."""
    bw4, bh4 = max(4, (w + 3) & ~3), max(4, (h + 3) & ~3)
    out = bytearray(bw4 * bh4 * 4)
    nbw = bw4 // 4
    zcache = {}
    for i in range(len(blocks) // 16):
        blk = blocks[i * 16:i * 16 + 16]
        xs, ys = _bc4_decode(blk[0:8]), _bc4_decode(blk[8:16])
        bx, by = (i % nbw) * 4, (i // nbw) * 4
        for k in range(16):
            r, g = xs[k], ys[k]
            z = zcache.get((r, g))
            if z is None:
                fx, fy = r / 127.5 - 1, g / 127.5 - 1
                z = zcache[(r, g)] = int(max(0.0, 1 - fx * fx - fy * fy) ** 0.5 * 127.5 + 127.5)
            o = ((by + (k >> 2)) * bw4 + bx + (k & 3)) * 4
            out[o:o + 4] = bytes((r, g, z, 255))
    out = bytes(out)
    return ph.crop(out, bw4, bh4, w, h) if (bw4, bh4) != (w, h) else out


def _bc4_encode(vals):
    a0, a1, bits = ph._encode_alpha(vals)
    return bytes((a0, a1)) + bits.to_bytes(6, 'little')


def dxn_encode(rgba, w, h):
    """RGBA (R = X, G = Y) → линейные блоки DXN. Меньше 4×4 — повтор края."""
    W, H = max(4, (w + 3) & ~3), max(4, (h + 3) & ~3)
    if (W, H) != (w, h):
        pad = bytearray(W * H * 4)
        for y in range(H):
            for x in range(W):
                s = (min(y, h - 1) * w + min(x, w - 1)) * 4
                pad[(y * W + x) * 4:(y * W + x) * 4 + 4] = rgba[s:s + 4]
        rgba, w, h = bytes(pad), W, H
    out = bytearray()
    cache = {}
    for by in range(0, h, 4):
        for bx in range(0, w, 4):
            raw = b''.join(rgba[((by + y) * w + bx) * 4:((by + y) * w + bx + 4) * 4] for y in range(4))
            xy = raw[0::4] + raw[1::4]
            blk = cache.get(xy)
            if blk is None:
                blk = _bc4_encode(list(raw[0::4])) + _bc4_encode(list(raw[1::4]))
                if len(cache) < 16384:
                    cache[xy] = blk
            out += blk
    return bytes(out)


def decode_blocks(fmt, blocks, w, h):
    if fmt == FMT_DXN:
        return dxn_decode(blocks, w, h)
    return ta.dxt_decode(fmt, blocks, w, h)


def _pad4(rgba, w, h):
    W, H = max(4, (w + 3) & ~3), max(4, (h + 3) & ~3)
    if (W, H) == (w, h):
        return rgba, w, h
    pad = bytearray(W * H * 4)
    for y in range(H):
        for x in range(W):
            s = (min(y, h - 1) * w + min(x, w - 1)) * 4
            pad[(y * W + x) * 4:(y * W + x) * 4 + 4] = rgba[s:s + 4]
    return bytes(pad), W, H


def _blocks_of(rgba, w, h):
    for by in range(0, h, 4):
        for bx in range(0, w, 4):
            yield b''.join(rgba[((by + y) * w + bx) * 4:((by + y) * w + bx + 4) * 4] for y in range(4))


def dxt5_encode_full(rgba, w, h):
    """DXT5, цвет — по всем 16 пикселям (как у EA в шрифтах: под прозрачным — цвет заливки, иначе при
    фильтрации по краям глифов проступает чёрная кайма)."""
    rgba, w, h = _pad4(rgba, w, h)
    out, cache = bytearray(), {}
    for raw in _blocks_of(rgba, w, h):
        blk = cache.get(raw)
        if blk is None:
            px = [(raw[k * 4], raw[k * 4 + 1], raw[k * 4 + 2]) for k in range(16)]
            a0, a1, abits = ph._encode_alpha(list(raw[3::4]))
            c0, c1, cbits = ph._encode_color(px, [255] * 16)
            blk = bytes((a0, a1)) + abits.to_bytes(6, 'little') + struct.pack('<HHI', c0, c1, cbits)
            if len(cache) < 8192:
                cache[raw] = blk
        out += blk
    return bytes(out)


def dxt1_encode_a1(rgba, w, h):
    """DXT1 с 1-битной альфой (как font_sm у EA): блок с прозрачными пикселями — режим 3 цвета + прозрачный."""
    rgba, w, h = _pad4(rgba, w, h)
    out, cache = bytearray(), {}
    for raw in _blocks_of(rgba, w, h):
        blk = cache.get(raw)
        if blk is None:
            px = [(raw[k * 4], raw[k * 4 + 1], raw[k * 4 + 2]) for k in range(16)]
            vis = [raw[k * 4 + 3] >= 128 for k in range(16)]
            if all(vis):
                c0, c1, bits = ph._encode_color(px, [255] * 16)
                if c0 == c1:
                    bits = 0
                    c0, c1 = (1, 0) if c0 == 0 else (c0, c0 - 1)
            elif not any(vis):
                c0, c1, bits = 0, 0, 0xFFFFFFFF
            else:
                c0, c1, _ = ph._encode_color(px, [255 if v else 0 for v in vis])
                c0, c1 = min(c0, c1), max(c0, c1)               # c0 ≤ c1 — режим с прозрачным
                p0, p1 = ph._c565(c0), ph._c565(c1)
                pal = [p0, p1, tuple((a + b) // 2 for a, b in zip(p0, p1))]
                bits = 0
                for k in range(16):
                    if not vis[k]:
                        bits |= 3 << (2 * k)
                        continue
                    r, g, b = px[k]
                    j = min(range(3), key=lambda i: (r - pal[i][0]) ** 2 + (g - pal[i][1]) ** 2 + (b - pal[i][2]) ** 2)
                    bits |= j << (2 * k)
            blk = struct.pack('<HHI', c0, c1, bits)
            if len(cache) < 8192:
                cache[raw] = blk
        out += blk
    return bytes(out)


def encode_blocks(fmt, rgba, w, h):
    if fmt == FMT_DXN:
        return dxn_encode(rgba, w, h)
    if fmt == ta.FMT_DXT5:
        return dxt5_encode_full(rgba, w, h)
    if fmt == ta.FMT_DXT1 and min(rgba[3::4]) < 128:
        return dxt1_encode_a1(rgba, w, h)
    return ta.dxt_encode(fmt, rgba, w, h)


def _encode_band(args):
    return encode_blocks(*args)


_POOL = None


def _pool():
    global _POOL
    if _POOL is None:
        from concurrent.futures import ProcessPoolExecutor
        _POOL = ProcessPoolExecutor(max_workers=max(1, (os.cpu_count() or 2) - 1))
    return _POOL


def encode_level(fmt, rgba, w, h):
    """RGBA → линейные блоки формата fmt; большие уровни — полосами по 16 строк блоков параллельно."""
    if fmt == ta.FMT_8888 or w * h < 128 * 128 or h < 128 or os.environ.get('KITPAINT_SERIAL'):
        return _encode_band((fmt, rgba, w, h))
    band = 64
    jobs = [(fmt, rgba[y * w * 4:(y + band) * w * 4], w, band) for y in range(0, h, band)]
    return b''.join(_pool().map(_encode_band, jobs))


def downsample_normals(rgba, w, h):
    """Уменьшение вдвое карты нормалей (R = X, G = Y): среднее единичных векторов, нормировка."""
    nw, nh = max(1, w // 2), max(1, h // 2)
    out = bytearray(nw * nh * 4)
    for y in range(nh):
        for x in range(nw):
            sx = sy = sz = 0.0
            for dy in (0, 1):
                for dx in (0, 1):
                    o = (min(h - 1, 2 * y + dy) * w + min(w - 1, 2 * x + dx)) * 4
                    fx, fy = rgba[o] / 127.5 - 1, rgba[o + 1] / 127.5 - 1
                    sx += fx
                    sy += fy
                    sz += max(0.0, 1 - fx * fx - fy * fy) ** 0.5
            n = math.sqrt(sx * sx + sy * sy + sz * sz) or 1.0
            r = min(255, max(0, int((sx / n + 1) * 127.5 + 0.5)))
            g = min(255, max(0, int((sy / n + 1) * 127.5 + 0.5)))
            z = min(255, max(0, int((sz / n + 1) * 127.5 + 0.5)))
            o = (y * nw + x) * 4
            out[o:o + 4] = bytes((r, g, z, 255))
    return bytes(out), nw, nh


def bleed(rgba, w, h):
    """Цвет под полностью прозрачными пикселями — от ближайшего видимого (у EA в шрифте под прозрачным —
    цвет заливки; иначе при фильтрации у краёв глифов — тёмная кайма)."""
    from collections import deque
    out = bytearray(rgba)
    n = w * h
    done = bytearray(1 if out[i * 4 + 3] else 0 for i in range(n))
    if all(done) or not any(done):
        return bytes(out)
    q = deque(i for i in range(n) if done[i])
    while q:
        i = q.popleft()
        x, y = i % w, i // w
        for j in ((i - 1) if x else -1, (i + 1) if x + 1 < w else -1, (i - w) if y else -1, (i + w) if y + 1 < h else -1):
            if j >= 0 and not done[j]:
                done[j] = 1
                out[j * 4:j * 4 + 3] = out[i * 4:i * 4 + 3]
                q.append(j)
    return bytes(out)


def mip_chain(fmt, rgba, w, h, levels):
    alpha = fmt == ta.FMT_DXT5 and min(rgba[3::4]) < 255
    out = [(w, h, bleed(rgba, w, h) if alpha else rgba)]
    for _ in range(1, levels):
        if fmt == FMT_DXN:
            rgba, w, h = downsample_normals(rgba, w, h)
        else:
            rgba, w, h = ta.downsample2(rgba, w, h)
        out.append((w, h, bleed(rgba, w, h) if alpha else rgba))
    return out


def tex_fmt(t):
    return t.fetch.fmt


def tex_decode(rw, t, lv=0):
    lw, lh = t.layout.levels[lv][:2]
    return lw, lh, decode_blocks(tex_fmt(t), t.layout.get_level(rw.buffer(t), lv), lw, lh)


def tex_replace(rw, t, rgba, w, h):
    """Новый буфер текстуры из картинки базового уровня (мипы считаются)."""
    lw, lh = t.layout.levels[0][:2]
    if (w, h) != (lw, lh):
        raise SystemExit(f'{t.name}: картинка {w}×{h}, нужна {lw}×{lh}')
    buf = bytearray(t.size)
    fmt = tex_fmt(t)
    for lv, (mw, mh, m) in enumerate(mip_chain(fmt, rgba, w, h, len(t.layout.levels))):
        t.layout.put_level(buf, lv, encode_level(fmt, m, mw, mh))
    rw.raw[t.data_off:t.data_off + t.size] = buf


def rgba_sha1(rgba):
    return hashlib.sha1(rgba).hexdigest()


def is_normal(layer):
    return layer.endswith('_nm')


# ---------------------------------------------------------------- разбор и сборка комплекта

def kit_textures(kit, game=None):
    """[(вид, путь, объект)] — Rw4 для .rx2, UiLogo для превью. game — из архивов другой игры (source)."""
    out = []
    for kind, _ in KIT_FILES:
        rel = kit.path(kind)
        data = source(rel, game)
        obj = ta.UiLogo(data, rel) if kind == 'fe' else ta.Rw4(data, rel)
        out.append((kind, rel, obj))
    return out


def cmd_files(args):
    for a in args:
        kit = Kit.parse(a)
        print(f'комплект {kit}:')
        for kind, rel, obj in kit_textures(kit):
            if kind == 'fe':
                print(f'  {rel}: BIGF, сцена {obj.stage[0]}×{obj.stage[1]}, {obj.fetch.describe()}')
                continue
            print(f'  {rel}: {len(obj.raw)} байт')
            for t in obj.textures:
                f = t.fetch
                print(f'     {t.name:28s} {f.width}×{f.height} {FMT_NAMES.get(f.fmt, f.fmt):4s} '
                      f'{"тайлинг" if f.tiled else "линейно"} уровней {len(t.layout.levels)} → слой {layer_name(t.name)}')


def unpack(kit, outdir):
    os.makedirs(outdir, exist_ok=True)
    meta = {'template': str(kit), 'layers': {}}
    for kind, rel, obj in kit_textures(kit):
        if kind == 'fe':
            w, h, rgba = obj.decode()
            ph.png_write(os.path.join(outdir, 'fe.png'), w, h, rgba)
            meta['layers']['fe'] = dict(file='fe', path=rel, fmt='8888', w=w, h=h, levels=1, sha1=rgba_sha1(rgba))
            continue
        for t in obj.textures:
            ln = layer_name(t.name)
            w, h, rgba = tex_decode(obj, t)
            ph.png_write(os.path.join(outdir, ln + '.png'), w, h, rgba)
            meta['layers'][ln] = dict(file=kind, path=rel, raster=t.name, fmt=FMT_NAMES.get(t.fetch.fmt, t.fetch.fmt),
                                      w=w, h=h, levels=len(t.layout.levels), sha1=rgba_sha1(rgba))
        print(f'{rel}: {", ".join(layer_name(t.name) for t in obj.textures)}')
    json.dump(meta, open(os.path.join(outdir, 'kit.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    return meta


def _same_texture(a, b):
    """Те же размер буфера, раскладка и константа выборки (кроме поля базового адреса)."""
    wa, wb = list(a.fetch.words), list(b.fetch.words)
    wa[1] &= 0xFFF
    wb[1] &= 0xFFF
    return a.size == b.size and wa == wb


def build_kit(template, new, layers, outdir=None, reencode=False, keep=None, trailer='md5', log=print, container=None):
    """Файлы комплекта new из шаблона template. layers — {слой: (w, h, rgba)} (нет слоя — пиксели шаблона);
    keep — {слой: sha1 исходной картинки}: совпала — буфер шаблона без пережатия. → {путь: байты}.
    container — комплект EA, чьи файлы берутся за основу (заголовки, имена растров → new), если он не template
    (номер другой длины, default_container): нетронутые слои — буферы шаблона как есть (структура та же)."""
    keep = keep or {}
    made = {}
    if container is not None and container.tag() == template.tag() and container.f == template.f:
        container = None
    tpl_objs = {kind: obj for kind, _, obj in kit_textures(template)} if container is not None else None
    base = container if container is not None else template
    for kind, rel, obj in kit_textures(base):
        out_rel = new.path(kind)
        if kind == 'fe':
            img = layers.get('fe')
            if container is not None and (img is None or (not reencode and rgba_sha1(img[2]) == keep.get('fe'))):
                tf = tpl_objs['fe']                      # 8888 без сжатия: превью шаблона в контейнер без потерь
                if tf.fetch.words != obj.fetch.words:
                    raise SystemExit(f'{rel}: превью контейнера и шаблона устроены по-разному')
                data = obj.build(tf.decode()[2], trailer)
            elif img is None or (not reencode and rgba_sha1(img[2]) == keep.get('fe')):
                big = ph.Bigf(obj.head.big.raw)
                data = big.build(None if template.tag() == new.tag() and template.f == new.f else trailer)
            else:
                w, h, rgba = img
                if (w, h) != (obj.fetch.width, obj.fetch.height):
                    raise SystemExit(f'fe: {w}×{h}, нужна {obj.fetch.width}×{obj.fetch.height}')
                data = obj.build(rgba, None if template.tag() == new.tag() and template.f == new.f else trailer)
            if log:
                log(f'{out_rel}: {len(data)} байт' + (', превью шаблона' if img is None else ''))
        else:
            changed = []
            tobj = tpl_objs[kind] if container is not None else None
            for t in obj.textures:
                ln = layer_name(t.name)
                img = layers.get(ln)
                if img is None or (not reencode and rgba_sha1(img[2]) == keep.get(ln)):
                    if tobj is not None:                 # контейнер: пиксели шаблона — его буфер как есть
                        tt = next((x for x in tobj.textures if layer_name(x.name) == ln), None)
                        if tt is None or not _same_texture(t, tt):
                            raise SystemExit(f'{rel}: слой {ln} у контейнера {container} и шаблона {template} разный')
                        obj.raw[t.data_off:t.data_off + t.size] = tobj.raw[tt.data_off:tt.data_off + tt.size]
                    continue
                tex_replace(obj, t, img[2], img[0], img[1])
                changed.append(ln)
            if base.tag() != new.tag():
                rename_rasters(obj, base, new)
            data = obj.bytes()
            if log:
                log(f'{out_rel}: {len(data)} байт' + (f', новые слои: {", ".join(changed)}' if changed else ', пиксели шаблона'))
        made[out_rel] = data
        if outdir:
            p = os.path.join(outdir, *out_rel.split('/'))
            os.makedirs(os.path.dirname(p), exist_ok=True)
            open(p, 'wb').write(data)
    return made


def read_layers(d):
    meta = json.load(open(os.path.join(d, 'kit.json'), encoding='utf-8'))
    layers, keep = {}, {}
    for ln, info in meta['layers'].items():
        p = os.path.join(d, ln + '.png')
        if os.path.exists(p):
            layers[ln] = ph.png_read(p)
            keep[ln] = info['sha1']
    return meta, layers, keep


def cmd_pack(args):
    d, new, outdir = args[0], Kit.parse(args[1]), args[2]
    meta, layers, keep = read_layers(d)
    tpl = Kit.parse(meta['template'])
    cont = Kit.parse(args[args.index('--container') + 1]) if '--container' in args else default_container(tpl, new)
    build_kit(tpl, new, layers, outdir, reencode='--reencode' in args, keep=keep, container=cont)


def psnr(a, b, chans=(0, 1, 2, 3)):
    se = n = 0
    for c in chans:
        for x, y in zip(a[c::4], b[c::4]):
            se += (x - y) * (x - y)
        n += len(a) // 4
    return 99.0 if se == 0 else 10 * math.log10(255 * 255 * n / se)


def roundtrip(kit, log=print):
    """1) разбор → сборка без изменений: файлы байт-в-байт как шаблон; 2) с пережатием всех слоёв: всё, кроме
    буферов текстур, байт-в-байт, раскладка (teamart.roundtrip) сходится, PSNR уровней 0 и 3 к оригиналу."""
    tmp = tempfile.mkdtemp(prefix='kitpaint_rt_')
    ok = True
    try:
        unpack(kit, tmp)
        meta, layers, keep = read_layers(tmp)
        same = build_kit(kit, kit, layers, None, reencode=False, keep=keep, log=None)
        for kind, rel, _ in kit_textures(kit):
            eq = same[rel] == source(rel)
            ok &= eq
            log(f'  {rel}: без изменений — {"байт-в-байт" if eq else "ОТЛИЧАЕТСЯ"}')
        re_ = build_kit(kit, kit, layers, None, reencode=True, keep=keep, log=None)
        for kind, rel, obj in kit_textures(kit):
            data = re_[rel]
            if kind == 'fe':
                new = ta.UiLogo(data, rel)
                w, h, a = obj.decode()
                _, _, b = new.decode()
                same_hdr = new.head.big.entries[0] == obj.head.big.entries[0]
                log(f'  {rel}: пережато — PSNR {psnr(a, b):.1f} дБ, Apt тот же: {same_hdr}')
                ok &= same_hdr
                continue
            new = ta.Rw4(data, rel)
            mask = bytearray(len(data))
            for t in new.textures:
                mask[t.data_off:t.data_off + t.size] = b'\1' * t.size
            outside = all(m or x == y for m, x, y in zip(mask, data, obj.raw))
            ok &= outside and len(data) == len(obj.raw)
            parts = []
            for t0, t1 in zip(obj.textures, new.textures):
                lay = t1.layout.size == t1.size
                q = []
                for lv in (0, 3):
                    if lv < len(t0.layout.levels):
                        _, _, a = tex_decode(obj, t0, lv)
                        _, _, b = tex_decode(new, t1, lv)
                        if is_normal(layer_name(t0.name)):
                            q.append(f'{psnr(a, b, (0, 1)):.1f}')
                        elif min(a[3::4]) < 255:          # с альфой: цвет под прозрачным не считается
                            q.append(f'{ta.psnr_premul(a, b):.1f}')
                        else:
                            q.append(f'{psnr(a, b, (0, 1, 2)):.1f}')
                parts.append(f'{layer_name(t0.name)} {"/".join(q)} дБ' + ('' if lay else ' (раскладка!)'))
            log(f'  {rel}: пережато — вне буферов {"байт-в-байт" if outside else "ОТЛИЧАЕТСЯ"}; '
                f'PSNR ур. 0/3: {"; ".join(parts)}')
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return ok


def cmd_roundtrip(args):
    bad = 0
    for a in args:
        kit = Kit.parse(a)
        print(f'комплект {kit}:')
        ok = roundtrip(kit)
        bad += not ok
        print('  итог:', 'OK' if ok else 'ОШИБКА')
    return bad


# ---------------------------------------------------------------- картинки и маски (чистый Python)

class Img:
    """RGBA w×h (bytearray)."""
    __slots__ = ('w', 'h', 'px')

    def __init__(self, w, h, px=None):
        self.w, self.h = w, h
        self.px = bytearray(px) if px is not None else bytearray(w * h * 4)

    @classmethod
    def load(cls, path):
        return cls(*ph.png_read(path))

    def save(self, path):
        ph.png_write(path, self.w, self.h, bytes(self.px))

    def copy(self):
        return Img(self.w, self.h, self.px)

    def tup(self):
        return self.w, self.h, bytes(self.px)


def parse_color(v, palette=None):
    palette = palette or {}
    if isinstance(v, str):
        if v in palette:
            return parse_color(palette[v], palette)
        s = v.lstrip('#')
        if len(s) == 3:
            s = ''.join(c * 2 for c in s)
        return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))
    return tuple(int(c) for c in v[:3])


def lum(r, g, b):
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def rect_clip(rect, w, h):
    x0, y0, x1, y1 = (int(round(v)) for v in rect)
    return max(0, x0), max(0, y0), min(w, x1), min(h, y1)


def dilate(mask, w, h, r):
    """Квадратное расширение двоичной маски (bytearray 0/1) на r пикселей (префиксные суммы, O(n))."""
    if r <= 0:
        return bytearray(mask)
    tmp = bytearray(w * h)
    for y in range(h):
        row = mask[y * w:(y + 1) * w]
        acc = [0] * (w + 1)
        for x in range(w):
            acc[x + 1] = acc[x] + (1 if row[x] else 0)
        o = y * w
        for x in range(w):
            if acc[min(w, x + r + 1)] - acc[max(0, x - r)]:
                tmp[o + x] = 1
    out = bytearray(w * h)
    for x in range(w):
        col = tmp[x::w]
        acc = [0] * (h + 1)
        for y in range(h):
            acc[y + 1] = acc[y] + col[y]
        for y in range(h):
            if acc[min(h, y + r + 1)] - acc[max(0, y - r)]:
                out[y * w + x] = 1
    return out


def fill_holes(mask, w, h, rect):
    """Дырки маски внутри rect (нули, не связанные с краем rect) → единицы (внутренность логотипа)."""
    from collections import deque
    x0, y0, x1, y1 = rect
    seen = bytearray(w * h)
    q = deque()
    for x in range(x0, x1):
        for y in (y0, y1 - 1):
            i = y * w + x
            if not mask[i] and not seen[i]:
                seen[i] = 1
                q.append(i)
    for y in range(y0, y1):
        for x in (x0, x1 - 1):
            i = y * w + x
            if not mask[i] and not seen[i]:
                seen[i] = 1
                q.append(i)
    while q:
        i = q.popleft()
        x, y = i % w, i // w
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if x0 <= nx < x1 and y0 <= ny < y1:
                j = ny * w + nx
                if not mask[j] and not seen[j]:
                    seen[j] = 1
                    q.append(j)
    out = bytearray(mask)
    for y in range(y0, y1):
        for x in range(x0, x1):
            i = y * w + x
            if not out[i] and not seen[i]:
                out[i] = 1
    return out


def mask_bbox(mask, w, h):
    xs0, ys0, xs1, ys1 = w, h, -1, -1
    for y in range(h):
        row = mask[y * w:(y + 1) * w]
        if not any(row):
            continue
        ys0, ys1 = min(ys0, y), y
        xs0 = min(xs0, next(i for i, v in enumerate(row) if v))
        xs1 = max(xs1, w - 1 - next(i for i, v in enumerate(reversed(row)) if v))
    return None if xs1 < 0 else (xs0, ys0, xs1 + 1, ys1 + 1)


def scale_mask(mask, w, h, nw, nh):
    """Маска в другом разрешении (та же раскладка UV): пиксель новой — «есть хоть один» в исходной области."""
    out = bytearray(nw * nh)
    for y in range(nh):
        sy0, sy1 = y * h // nh, max(y * h // nh + 1, (y + 1) * h // nh)
        for x in range(nw):
            sx0, sx1 = x * w // nw, max(x * w // nw + 1, (x + 1) * w // nw)
            if any(mask[yy * w + xx] for yy in range(sy0, sy1) for xx in range(sx0, sx1)):
                out[y * nw + x] = 1
    return out


def box_blur(plane, w, h, r):
    """Ящичное размытие плоскости (список float) радиуса r, края — повтор."""
    if r <= 0:
        return list(plane)
    tmp = [0.0] * (w * h)
    k = 2 * r + 1
    for y in range(h):
        o = y * w
        row = plane[o:o + w]
        s = sum(row[min(w - 1, max(0, i))] for i in range(-r, r + 1))
        for x in range(w):
            tmp[o + x] = s / k
            s += row[min(w - 1, x + r + 1)] - row[max(0, x - r)]
    out = [0.0] * (w * h)
    for x in range(w):
        col = tmp[x::w]
        s = sum(col[min(h - 1, max(0, i))] for i in range(-r, r + 1))
        for y in range(h):
            out[y * w + x] = s / k
            s += col[min(h - 1, y + r + 1)] - col[max(0, y - r)]
    return out


def norm_blur(plane, wt, w, h, r):
    """Размытие только по известным пикселям (wt = 1): Σ(v·wt) / Σwt."""
    a = box_blur([v * m for v, m in zip(plane, wt)], w, h, r)
    b = box_blur(wt, w, h, r)
    return [x / y if y > 1e-6 else 0.0 for x, y in zip(a, b)]


def pushpull(planes, wt, w, h):
    """Заполнение неизвестных (wt < 1) пикселей плавной интерполяцией от краёв (пирамида push-pull)."""
    pyr = [(planes, wt, w, h)]
    while w > 1 or h > 1:
        nw, nh = (w + 1) // 2, (h + 1) // 2
        nwt = [0.0] * (nw * nh)
        npl = [[0.0] * (nw * nh) for _ in planes]
        for y in range(nh):
            for x in range(nw):
                sw = 0.0
                acc = [0.0] * len(planes)
                for yy in (2 * y, 2 * y + 1):
                    if yy >= h:
                        continue
                    for xx in (2 * x, 2 * x + 1):
                        if xx >= w:
                            continue
                        i = yy * w + xx
                        m = wt[i]
                        if m:
                            sw += m
                            for c, pl in enumerate(planes):
                                acc[c] += pl[i] * m
                j = y * nw + x
                if sw:
                    for c in range(len(planes)):
                        npl[c][j] = acc[c] / sw
                nwt[j] = min(1.0, sw)
        planes, wt, w, h = npl, nwt, nw, nh
        pyr.append((planes, wt, w, h))
    for lv in range(len(pyr) - 2, -1, -1):
        planes, wt, w, h = pyr[lv]
        cpl, _, cw, ch = pyr[lv + 1]
        for y in range(h):
            fy = min(ch - 1.0, max(0.0, y * 0.5 - 0.25))
            ya = int(fy)
            yb = min(ch - 1, ya + 1)
            ty = fy - ya
            for x in range(w):
                i = y * w + x
                m = wt[i]
                if m >= 1:
                    continue
                fx = min(cw - 1.0, max(0.0, x * 0.5 - 0.25))
                xa = int(fx)
                xb = min(cw - 1, xa + 1)
                tx = fx - xa
                for c in range(len(planes)):
                    q = cpl[c]
                    up = ((q[ya * cw + xa] * (1 - tx) + q[ya * cw + xb] * tx) * (1 - ty)
                          + (q[yb * cw + xa] * (1 - tx) + q[yb * cw + xb] * tx) * ty)
                    planes[c][i] = planes[c][i] * m + up * (1 - m)
    return pyr[0][0]


def erase(img, mask, chans=(0, 1, 2), margin=40, ring=14, seed=1, log=None, texture=True, known=None):
    """Стереть область mask (логотип шаблона) на img: гладкий фон (push-pull от краёв, по размытому фону
    вокруг) + фактура трикотажа — средний узор по фазам периода, найденного по кольцу вокруг области
    (у свитеров EA узор периодичен: 3×3 на груди, 6×8 на спине). Меняются только пиксели маски.
    texture=False — только гладкий фон (превью меню: там трикотажа нет); known — маска пикселей, по которым
    можно считать фон (у превью — только ткань, без манекена и прозрачного)."""
    import random
    w, h = img.w, img.h
    bb = mask_bbox(mask, w, h)
    if not bb:
        return None
    x0, y0 = max(0, bb[0] - margin), max(0, bb[1] - margin)
    x1, y1 = min(w, bb[2] + margin), min(h, bb[3] + margin)
    cw, ch = x1 - x0, y1 - y0
    m = bytearray(cw * ch)
    for y in range(ch):
        m[y * cw:(y + 1) * cw] = mask[(y0 + y) * w + x0:(y0 + y) * w + x1]
    if known is None:
        wt = [0.0 if v else 1.0 for v in m]
    else:
        wt = [0.0 if v or not known[(y0 + i // cw) * w + x0 + i % cw] else 1.0 for i, v in enumerate(m)]
    px = img.px
    planes = [[float(px[((y0 + y) * w + x0 + x) * 4 + c]) for y in range(ch) for x in range(cw)] for c in chans]
    lows = [norm_blur(pl, wt, cw, ch, 3) for pl in planes]
    near = dilate(m, cw, ch, ring)
    ring_idx = [i for i in range(cw * ch) if near[i] and wt[i] > 0]
    hf = [[planes[c][i] - lows[c][i] for i in ring_idx] for c in range(len(chans))]
    # период узора: (px, py) с наибольшей долей объяснённой дисперсии (из почти равных — меньший)
    gx = [(i % cw + x0) for i in ring_idx]
    gy = [(i // cw + y0) for i in ring_idx]
    tot = [sum(v * v for v in hc) for hc in hf]
    sst = sum(tot) or 1.0
    scores = []
    for pyy in range(1, 9):
        for pxx in range(1, 9):
            n = pxx * pyy
            sse = 0.0
            for hc in hf:
                s = [0.0] * n
                c = [0] * n
                for v, xx, yy in zip(hc, gx, gy):
                    k = (xx % pxx) + (yy % pyy) * pxx
                    s[k] += v
                    c[k] += 1
                sse += sum(v * v for v in hc) - sum(s[k] * s[k] / c[k] for k in range(n) if c[k])
            scores.append((1 - sse / sst, pxx, pyy))
    best = max(r for r, _, _ in scores)
    r2, pxx, pyy = min((s for s in scores if s[0] >= best - 0.03), key=lambda s: (s[1] * s[2], -s[0]))
    tiles = []
    for hc in hf:
        n = pxx * pyy
        s, c = [0.0] * n, [0] * n
        for v, xx, yy in zip(hc, gx, gy):
            k = (xx % pxx) + (yy % pyy) * pxx
            s[k] += v
            c[k] += 1
        tiles.append([s[k] / c[k] if c[k] else 0.0 for k in range(n)])
    # остаток (неперио­дическая часть узора) — шумом той же силы
    rnd = random.Random(seed)
    noise = []
    for ci, hc in enumerate(hf):
        res = [v - tiles[ci][(xx % pxx) + (yy % pyy) * pxx] for v, xx, yy in zip(hc, gx, gy)]
        noise.append((sum(v * v for v in res) / max(1, len(res))) ** 0.5 * 0.6)
    filled = pushpull(lows, wt, cw, ch)
    for i in range(cw * ch):
        if not m[i]:
            continue
        xx, yy = i % cw + x0, i // cw + y0
        k = (xx % pxx) + (yy % pyy) * pxx
        o = (yy * w + xx) * 4
        g = rnd.gauss(0.0, 1.0) if texture else 0.0
        for ci, c in enumerate(chans):
            v = filled[ci][i] + (tiles[ci][k] + g * noise[ci] if texture else 0.0)
            px[o + c] = 0 if v < 0 else 255 if v > 255 else int(v + 0.5)
    info = dict(bbox=bb, period=(pxx, pyy), r2=round(r2, 2))
    if log:
        log(f'    стирание {bb}: период узора {pxx}×{pyy} (R² {r2:.2f})')
    return info


def renormalize(img, mask=None):
    """B карты нормалей = восстановленный Z (для просмотра; при сборке берутся R и G)."""
    px = img.px
    for i in range(img.w * img.h):
        if mask is not None and not mask[i]:
            continue
        fx, fy = px[i * 4] / 127.5 - 1, px[i * 4 + 1] / 127.5 - 1
        px[i * 4 + 2] = int(max(0.0, 1 - fx * fx - fy * fy) ** 0.5 * 127.5 + 127.5)


# ---------------------------------------------------------------- перекраска по зонам цвета шаблона

class Recolor:
    """Каждый пиксель шаблона раскладывается на смесь двух зон (цветов шаблона) t·A + (1−t)·B + остаток
    (швы, затенение, фактура). Новая картинка — та же смесь новых цветов зон + тот же остаток: сглаженные края
    полос и затенение сохраняются. Цвет зоны можно задать по областям (rect/маска) и полосами (bands).
    Пиксели, которые смесью не объясняются (ошибка > keep), остаются как в шаблоне."""

    def __init__(self, img, zones, keep=60, palette=None, snap=0.0):
        """snap — доля смеси у краёв (t < snap → чистая зона A, t > 1 − snap → B, между — растяжение): шум
        тёмного шаблона не превращается в «крапины» другой зоны при перекраске в светлое (превью)."""
        from array import array
        self.img = img
        self.names = [n for n, _ in zones]
        self.cols = [parse_color(c, palette) for _, c in zones]
        self.zi = {n: i for i, n in enumerate(self.names)}
        self.keep2 = keep * keep
        self.snap = snap
        w, h, px = img.w, img.h, img.px
        n = w * h
        idx = array('I', bytes(4 * n))
        uniq = {}
        for i in range(n):
            o = i * 4
            key = (px[o] << 16) | (px[o + 1] << 8) | px[o + 2]
            k = uniq.get(key)
            if k is None:
                k = uniq[key] = len(uniq)
            idx[i] = k
        self.idx = idx
        self.dec = [None] * len(uniq)
        for key, k in uniq.items():
            self.dec[k] = self._decomp(key >> 16, (key >> 8) & 255, key & 255)
        self.map = {i: c for i, c in enumerate(self.cols)}
        self.regions = []

    def _decomp(self, r, g, b):
        cols = self.cols
        K = len(cols)
        d2 = [(r - c[0]) ** 2 + (g - c[1]) ** 2 + (b - c[2]) ** 2 for c in cols]
        order = sorted(range(K), key=d2.__getitem__)
        best = (d2[order[0]], order[0], order[0], 0.0)
        for a in order[:2]:
            ca = cols[a]
            for z in range(K):
                if z == a:
                    continue
                cb = cols[z]
                dx, dy, dz = cb[0] - ca[0], cb[1] - ca[1], cb[2] - ca[2]
                L = dx * dx + dy * dy + dz * dz
                if not L:
                    continue
                t = ((r - ca[0]) * dx + (g - ca[1]) * dy + (b - ca[2]) * dz) / L
                t = 0.0 if t < 0 else 1.0 if t > 1 else t
                e = (r - ca[0] - t * dx) ** 2 + (g - ca[1] - t * dy) ** 2 + (b - ca[2] - t * dz) ** 2
                if e < best[0] - 1e-9:
                    best = (e, a, z, t)
        e, za, zb, t = best
        s = self.snap
        if s and za != zb:
            t = min(1.0, max(0.0, (t - s) / (1 - 2 * s)))
        ca, cb = cols[za], cols[zb]
        q = [ca[c] + t * (cb[c] - ca[c]) for c in range(3)]
        return (za, zb, t, r - q[0], g - q[1], b - q[2], e > self.keep2)

    # --- что во что
    def z(self, name):
        if name not in self.zi:
            raise SystemExit(f'нет зоны «{name}» (есть: {", ".join(self.names)})')
        return self.zi[name]

    def color(self, zone, c, palette=None):
        """Цвет для зоны: "keep" — цвет зоны в шаблоне (без изменений), иначе имя палитры / #RRGGBB / [r, g, b]."""
        return self.cols[zone] if c == 'keep' else parse_color(c, palette)

    def set(self, mapping, palette=None):
        for zn, c in mapping.items():
            self.map[self.z(zn)] = self.color(self.z(zn), c, palette)

    def region(self, rect, mapping, palette=None, mask=None, minw=0.0):
        """mapping {зона: цвет} внутри rect (и маски mask — bytearray w×h, если задана); minw — только там,
        где доля зоны в пикселе не меньше minw (превью: не красить тени, похожие на смесь с этой зоной)."""
        r = rect_clip(rect, self.img.w, self.img.h)
        if mapping == 'keep':
            mapping = {n: 'keep' for n in self.names}
        self.regions.append(dict(rect=r, mask=mask, minw=minw, map={self.z(zn): self.color(self.z(zn), c, palette)
                                                                    for zn, c in mapping.items()}))

    def membership(self, i, group):
        za, zb, t = self.dec[self.idx[i]][:3]
        return (1 - t if za in group else 0.0) + (t if zb in group else 0.0)

    def bands(self, rect, zones, bands, axis='y', edge='lo', palette=None, start=None, units='frac', smooth=0,
              fill=False):
        """Полосы внутри группы зон zones в rect: по каждой линии поперёк (столбец для axis='y') — границы
        группы, координата s от края edge ('lo' — меньшая координата, 'hi' — большая): доля 0…1 (units='frac')
        или пиксели (units='px'); bands — [[s0, s1, цвет]], пиксель окрашивается по покрытию (сглаженно).
        start — зона, с которой группа начинается со стороны edge (раньше неё — не полоса: например, белый бок
        над серой линией низа). smooth — сглаживание начала полосы по соседним линиям; fill — внутри границ
        группы красить и пиксели других зон (крапины фактуры шаблона внутри полосы)."""
        w, h = self.img.w, self.img.h
        x0, y0, x1, y1 = rect_clip(rect, w, h)
        group = {self.z(zn) for zn in zones}
        sz = {self.z(start)} if start else None
        cols = [(float(a), float(b), parse_color(c, palette)) for a, b, c in bands]
        rw, rh = x1 - x0, y1 - y0
        colors = [None] * (rw * rh)
        inside = bytearray(rw * rh) if fill else None
        lines = range(x0, x1) if axis == 'y' else range(y0, y1)
        span = range(y0, y1) if axis == 'y' else range(x0, x1)
        ext = {}
        for ln in lines:
            def idx(p):
                return (p * w + ln) if axis == 'y' else (ln * w + p)

            def mg(p):
                return self.membership(idx(p), group) if span.start <= p < span.stop else 0.0

            def ms(p):
                return self.membership(idx(p), sz) if span.start <= p < span.stop else 0.0
            if sz is None:
                pos = [p for p in span if mg(p) >= 0.5]
                if not pos:
                    continue
                lo, hi = pos[0], pos[-1] + 1
                flo, fhi = lo - mg(lo - 1), hi + mg(hi)
            elif edge == 'lo':
                first = next((p for p in span if ms(p) >= 0.5), None)
                if first is None:
                    continue
                lo, hi = first, first
                while hi < span.stop and mg(hi) >= 0.5:
                    hi += 1
                flo, fhi = lo - ms(lo - 1), hi + mg(hi)
            else:
                first = next((p for p in reversed(span) if ms(p) >= 0.5), None)
                if first is None:
                    continue
                lo, hi = first, first + 1
                while lo - 1 >= span.start and mg(lo - 1) >= 0.5:
                    lo -= 1
                flo, fhi = lo - mg(lo - 1), hi + ms(hi)
            ext[ln] = [lo, hi, flo, fhi]
        if smooth > 1:
            # граница со стороны edge — медиана, затем среднее по соседним линиям (у EA линии с фактурой:
            # начало «прыгает» на пиксель-другой, без сглаживания край полосы — ступеньками)
            r = smooth // 2
            for k in (2, 3):                                 # обе границы группы
                raw = {ln: e[k] for ln, e in ext.items()}
                med = {}
                for ln in ext:
                    near = sorted(raw[j] for j in range(ln - r, ln + r + 1) if j in raw)
                    med[ln] = near[len(near) // 2]
                for ln, e in ext.items():
                    near = [med[j] for j in range(ln - r, ln + r + 1) if j in med]
                    e[k] = sum(near) / len(near)
            for e in ext.values():
                e[0] = min(e[0], int(math.floor(e[2])))
                e[1] = max(e[1], int(math.ceil(e[3])))
        for ln, (lo, hi, flo, fhi) in ext.items():
            size = max(1e-6, fhi - flo) if units == 'frac' else 1.0
            for p in range(max(span.start, lo - 1), min(span.stop, hi + 1)):
                if edge == 'hi':
                    a, b = (fhi - p - 1) / size, (fhi - p) / size
                else:
                    a, b = (p - flo) / size, (p + 1 - flo) / size
                acc = [0.0, 0.0, 0.0]
                cov = 0.0
                for s0, s1, c in cols:
                    o = min(b, s1) - max(a, s0)
                    if o > 0:
                        cov += o
                        for k in range(3):
                            acc[k] += o * c[k]
                if cov <= 0:
                    continue
                x, y = (ln, p) if axis == 'y' else (p, ln)
                colors[(y - y0) * rw + (x - x0)] = tuple(int(v / cov + 0.5) for v in acc)
                if inside is not None and lo <= p < hi:
                    inside[(y - y0) * rw + (x - x0)] = 1
        self.regions.append(dict(rect=(x0, y0, x1, y1), mask=None, band=(group, colors, rw, inside)))

    def _zone_color(self, zone, x, y, i):
        for reg in reversed(self.regions):
            x0, y0, x1, y1 = reg['rect']
            if not (x0 <= x < x1 and y0 <= y < y1):
                continue
            if reg['mask'] is not None and not reg['mask'][i]:
                continue
            if 'band' in reg:
                group, colors, rw, inside = reg['band']
                j = (y - y0) * rw + (x - x0)
                if zone in group or (inside is not None and inside[j]):
                    c = colors[j]
                    if c is not None:
                        return c
                continue
            c = reg['map'].get(zone)
            if c is not None:
                if reg.get('minw'):
                    za, zb, t = self.dec[self.idx[i]][:3]
                    wz = (1 - t if za == zone else 0.0) + (t if zb == zone else 0.0)
                    if wz < reg['minw']:
                        continue
                return c
        return self.map[zone]

    def render(self):
        w, h = self.img.w, self.img.h
        src = self.img.px
        out = bytearray(src)
        lut = []
        for za, zb, t, rr, rg, rb, keep in self.dec:
            if keep:
                lut.append(None)
                continue
            a, b = self.map[za], self.map[zb]
            lut.append(bytes(max(0, min(255, int(a[c] + t * (b[c] - a[c]) + d + 0.5)))
                             for c, d in ((0, rr), (1, rg), (2, rb))))
        idx = self.idx
        for i in range(w * h):
            v = lut[idx[i]]
            if v is not None:
                out[i * 4:i * 4 + 3] = v
        done = bytearray(w * h)
        for reg in self.regions:
            x0, y0, x1, y1 = reg['rect']
            for y in range(y0, y1):
                for x in range(x0, x1):
                    i = y * w + x
                    if done[i]:
                        continue
                    done[i] = 1
                    za, zb, t, rr, rg, rb, keep = self.dec[idx[i]]
                    if keep:
                        continue
                    a = self._zone_color(za, x, y, i)
                    b = a if zb == za else self._zone_color(zb, x, y, i)
                    out[i * 4:i * 4 + 3] = bytes(max(0, min(255, int(a[c] + t * (b[c] - a[c]) + d + 0.5)))
                                                 for c, d in ((0, rr), (1, rg), (2, rb)))
        return Img(w, h, out)


def refine_zones(img, zones, radius=28, palette=None):
    """Уточнение цветов зон: среднее пикселей ближе radius к затравке (и ближе к ней, чем к другим)."""
    cols = [parse_color(c, palette) for _, c in zones]
    acc = [[0, 0, 0, 0] for _ in cols]
    px = img.px
    from collections import Counter
    cnt = Counter((px[i] << 16) | (px[i + 1] << 8) | px[i + 2] for i in range(0, len(px), 4))
    r2 = radius * radius
    for key, n in cnt.items():
        r, g, b = key >> 16, (key >> 8) & 255, key & 255
        d = [(r - c[0]) ** 2 + (g - c[1]) ** 2 + (b - c[2]) ** 2 for c in cols]
        k = min(range(len(cols)), key=d.__getitem__)
        if d[k] <= r2:
            a = acc[k]
            a[0] += r * n
            a[1] += g * n
            a[2] += b * n
            a[3] += n
    out = []
    for (name, _), c, a in zip(zones, cols, acc):
        out.append((name, tuple(int(a[k] / a[3] + 0.5) for k in range(3)) if a[3] else c))
    return out


# ---------------------------------------------------------------- логотипы: SVG → RGBA (Chrome/Edge без окна)

_SVG_BOX = {}
_RENDER = {}


def svg_load(spec, base):
    """{"file": путь (от SPEC), "strip_paths": [номера <path>], "cut": [[номер path, "подстрока d", …]]}"""
    path = os.path.normpath(os.path.join(base, spec['file']))
    svg = ta.svg_text(path, ())
    for item in spec.get('cut', ()):              # отрезать хвост d у path (знак ® внутри контура)
        n, start = item[0], item[1]
        elems = list(re.finditer(r'<path\b[^>]*?(?:/>|>.*?</path>)', svg, re.S))
        e = elems[n]
        frag = e.group(0)
        md = re.search(r'd="([^"]*)"', frag)
        d = md.group(1)
        p = d.find(start)
        if p < 0:
            raise SystemExit(f'{path}: в path {n} нет «{start}»')
        frag2 = frag[:md.start(1)] + d[:p] + frag[md.end(1):]
        svg = svg[:e.start()] + frag2 + svg[e.end():]
    strip = tuple(spec.get('strip_paths', ()))
    if strip:
        elems = list(re.finditer(r'<path\b[^>]*?(?:/>|>.*?</path>)', svg, re.S))
        out, pos = [], 0
        for i, mm in enumerate(elems):
            if i in strip:
                out.append(svg[pos:mm.start()])
                pos = mm.end()
        out.append(svg[pos:])
        svg = ''.join(out)
    rec = list(spec.get('recolor', {}).items())          # замена цветов заливки и контура (одновременно:
    for k, (old, _) in enumerate(rec):                      # {"#99D9D9": "#001628", "#001628": "#99D9D9"} — обмен)
        for attr in ('fill', 'stroke'):
            svg = re.sub(re.escape(f'{attr}="{old}"'), f'{attr}="@@{k}@@"', svg, flags=re.I)
    for k, (_, new) in enumerate(rec):
        svg = svg.replace(f'"@@{k}@@"', f'"{new}"')
    return svg


def svg_box(svg):
    key = hashlib.sha1(svg.encode('utf-8')).hexdigest()
    if key not in _SVG_BOX:
        tmp = tempfile.mkdtemp(prefix='kitpaint_m_')
        try:
            _SVG_BOX[key] = ta.measure_box(ta.data_uri(svg), ta._svg_viewbox(svg), tmp)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    return _SVG_BOX[key]


def render_logo(svg, w, h, fit_w, fit_h, rotate=0, extra_css=''):
    """Картинка w×h: рисунок SVG (по его рамке) вписан в fit_w×fit_h по центру и повёрнут на rotate
    градусов по часовой стрелке (90 — верх логотипа смотрит вправо)."""
    key = (hashlib.sha1(svg.encode('utf-8')).hexdigest(), w, h, fit_w, fit_h, rotate, extra_css)
    if key in _RENDER:
        return _RENDER[key]
    vx, vy, vw, vh = ta._svg_viewbox(svg)
    bx, by, bw, bh = svg_box(svg)
    if rotate % 180:
        k = min(fit_w / bh, fit_h / bw)
    else:
        k = min(fit_w / bw, fit_h / bh)
    cx, cy = (bx - vx + bw / 2) * k, (by - vy + bh / 2) * k
    left, top = w / 2 - cx, h / 2 - cy
    body = (f'<img class="a" src="{ta.data_uri(svg)}" style="left:{left:.3f}px;top:{top:.3f}px;'
            f'width:{vw * k:.3f}px;height:{vh * k:.3f}px;transform-origin:{cx:.3f}px {cy:.3f}px;'
            f'transform:rotate({rotate}deg);{extra_css}">')
    tmp = tempfile.mkdtemp(prefix='kitpaint_r_')
    try:
        png = os.path.join(tmp, 'logo.png')
        ta.render_html(ta.page(w, h, body), png, w, h)
        img = Img(*ph.png_read(png))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    _RENDER[key] = img
    return img


def over_at(dst, src, x0, y0, shade=None):
    """src поверх dst со сдвигом (x0, y0); shade(x, y) → множитель яркости src (затенение превью)."""
    w, h = dst.w, dst.h
    d, s = dst.px, src.px
    for y in range(src.h):
        ty = y + y0
        if not 0 <= ty < h:
            continue
        for x in range(src.w):
            tx = x + x0
            if not 0 <= tx < w:
                continue
            so = (y * src.w + x) * 4
            a = s[so + 3]
            if not a:
                continue
            do = (ty * w + tx) * 4
            k = shade(tx, ty) if shade else 1.0
            da = d[do + 3]
            oa = a + da * (255 - a) // 255
            for c in range(3):
                sv = min(255, s[so + c] * k)
                d[do + c] = int((sv * a + d[do + c] * da * (255 - a) / 255) / max(1, oa) + 0.5)
            d[do + 3] = oa


def place_alpha(w, h, logo, x0, y0, out=None):
    """Альфа логотипа в маске размера w×h (float 0..1) и яркость его цвета (0..1)."""
    a = out[0] if out else [0.0] * (w * h)
    L = out[1] if out else [0.0] * (w * h)
    s = logo.px
    for y in range(logo.h):
        ty = y + y0
        if not 0 <= ty < h:
            continue
        for x in range(logo.w):
            tx = x + x0
            if not 0 <= tx < w:
                continue
            o = (y * logo.w + x) * 4
            al = s[o + 3] / 255.0
            if al <= 0:
                continue
            i = ty * w + tx
            a[i] = al + a[i] * (1 - al)
            L[i] = lum(s[o], s[o + 1], s[o + 2]) / 255.0 * al + L[i] * (1 - al)
    return a, L


# ---------------------------------------------------------------- рельеф и блеск логотипа (нормали, sm)

def _grad(hmap, w, h):
    gx = [0.0] * (w * h)
    gy = [0.0] * (w * h)
    for y in range(h):
        for x in range(w):
            i = y * w + x
            gx[i] = (hmap[y * w + min(w - 1, x + 1)] - hmap[y * w + max(0, x - 1)]) * 0.5
            gy[i] = (hmap[min(h - 1, y + 1) * w + x] - hmap[max(0, y - 1) * w + x]) * 0.5
    return gx, gy


def relief_calibrate(nm, footprint, log=None):
    """Знак и сила рельефа нашивки в нормалях шаблона: регрессия (X − фон) на ∂h/∂x и (Y − фон) на ∂h/∂y,
    h — размытая маска старого логотипа. → (kx, ky) или None."""
    w, h = nm.w, nm.h
    bb = mask_bbox(footprint, w, h)
    if not bb:
        return None
    x0, y0 = max(0, bb[0] - 8), max(0, bb[1] - 8)
    x1, y1 = min(w, bb[2] + 8), min(h, bb[3] + 8)
    cw, ch = x1 - x0, y1 - y0
    f = [float(footprint[(y0 + y) * w + x0 + x]) for y in range(ch) for x in range(cw)]
    hm = box_blur(box_blur(f, cw, ch, 1), cw, ch, 1)
    gx, gy = _grad(hm, cw, ch)
    res = []
    for c, g in ((0, gx), (1, gy)):
        pl = [float(nm.px[((y0 + y) * w + x0 + x) * 4 + c]) for y in range(ch) for x in range(cw)]
        lowp = box_blur(pl, cw, ch, 6)
        sxy = sxx = 0.0
        for i in range(cw * ch):
            gi = g[i]
            if abs(gi) > 0.02:
                sxy += gi * (pl[i] - lowp[i])
                sxx += gi * gi
        res.append(sxy / sxx if sxx else 0.0)
    if log:
        log(f'    рельеф шаблона: kx {res[0]:+.1f}, ky {res[1]:+.1f} (на единицу наклона)')
    return tuple(res)


def _logo_height(alpha, L, w, h, inner, pad=5):
    """Высота нашивки в рамке логотипа: альфа · (1 − inner + inner·яркость цвета), размытие 3×3.
    → (x0, y0, cw, ch, высота, ∂x, ∂y) или None."""
    bbm = bytearray(1 if v > 0.01 else 0 for v in alpha)
    bb = mask_bbox(bbm, w, h)
    if not bb:
        return None
    x0, y0, x1, y1 = max(0, bb[0] - pad), max(0, bb[1] - pad), min(w, bb[2] + pad), min(h, bb[3] + pad)
    cw, ch = x1 - x0, y1 - y0
    hm = []
    for y in range(ch):
        for x in range(cw):
            i = (y0 + y) * w + x0 + x
            a = alpha[i]
            hm.append(a * (1 - inner + inner * L[i] / a) if a > 1e-6 else 0.0)
    hm = box_blur(hm, cw, ch, 1)
    gx, gy = _grad(hm, cw, ch)
    return x0, y0, cw, ch, hm, gx, gy


def add_relief(nm, alpha, L, k, inner=0.3):
    """Рельеф нашивки на карте нормалей: под логотипом трикотаж сглаживается (вышивка гладкая), наклон
    высоты → сдвиг X/Y на k·∂h (знак — как у рельефа логотипа шаблона)."""
    w, h = nm.w, nm.h
    r = _logo_height(alpha, L, w, h, inner)
    if not r:
        return
    x0, y0, cw, ch, hm, gx, gy = r
    px = nm.px
    planes = [[float(px[((y0 + y) * w + x0 + x) * 4 + c]) for y in range(ch) for x in range(cw)] for c in (0, 1)]
    smooth = [box_blur(pl, cw, ch, 4) for pl in planes]
    kx, ky = k
    for y in range(ch):
        for x in range(cw):
            i = y * cw + x
            a = alpha[(y0 + y) * w + x0 + x]
            if a <= 0.01 and not (gx[i] or gy[i]):
                continue
            o = ((y0 + y) * w + x0 + x) * 4
            for c, d in ((0, kx * gx[i]), (1, ky * gy[i])):
                v = planes[c][i] * (1 - a) + smooth[c][i] * a + d
                px[o + c] = 0 if v < 0 else 255 if v > 255 else int(v + 0.5)
            fx, fy = px[o] / 127.5 - 1, px[o + 1] / 127.5 - 1
            px[o + 2] = int(max(0.0, 1 - fx * fx - fy * fy) ** 0.5 * 127.5 + 127.5)


def gloss_calibrate(sm, footprint, log=None):
    """Блеск вышивки шаблона (sm под старым логотипом): среднее и разброс. → (среднее, 0, разброс) или None."""
    vals = [lum(sm.px[i * 4], sm.px[i * 4 + 1], sm.px[i * 4 + 2]) for i in range(sm.w * sm.h) if footprint[i]]
    if len(vals) < 50:
        return None
    mean = sum(vals) / len(vals)
    sd = (sum((s - mean) ** 2 for s in vals) / len(vals)) ** 0.5
    if log:
        log(f'    блеск вышивки шаблона: среднее {mean:.0f}, разброс {sd:.0f}')
    return mean, 0.0, sd


def add_gloss(sm, alpha, L, cal, seed=7, inner=0.3, edge=520.0):
    """Блеск вышивки: внутри — средний уровень шаблона с мелким шумом (гладь), по краям цветов — светлые
    линии (у EA швы вышивки блестят)."""
    import random
    a0, _, sd = cal
    rnd = random.Random(seed)
    w, h = sm.w, sm.h
    r = _logo_height(alpha, L, w, h, inner, pad=3)
    if not r:
        return
    x0, y0, cw, ch, hm, gx, gy = r
    px = sm.px
    for y in range(ch):
        for x in range(cw):
            i = y * cw + x
            j = (y0 + y) * w + x0 + x
            al = alpha[j]
            g = math.hypot(gx[i], gy[i])
            if al <= 0.01 and g < 0.01:
                continue
            v = a0 + rnd.gauss(0.0, sd * 0.35) + edge * g
            o = j * 4
            k = max(al, min(1.0, g * 6))
            for c in range(3):
                q = px[o + c] * (1 - k) + v * k
                px[o + c] = 0 if q < 0 else 255 if q > 255 else int(q + 0.5)


# ---------------------------------------------------------------- шрифт номеров: заливка и обводка

FONT_PARTS = {   # области атласа 512² (одинаковы у всех шрифтов EA): буквы фамилии, большие цифры + C/A, малые цифры
    'letters': (0, 0, 512, 98), 'big': (0, 98, 512, 368), 'small': (0, 368, 512, 512), 'ca': (420, 78, 512, 306),
}


def font_part(x, y):
    x0, y0, x1, y1 = FONT_PARTS['ca']
    if x0 <= x < x1 and y0 <= y < y1:
        return 'big'
    for name in ('letters', 'big', 'small'):
        x0, y0, x1, y1 = FONT_PARTS[name]
        if x0 <= x < x1 and y0 <= y < y1:
            return name
    return 'small'


def paint_font(img, fill, outline=None, outline_px=None, palette=None):
    """Глифы шрифта (альфа — форма, у EA — один цвет): заливка fill, внутренняя обводка outline шириной
    outline_px[часть] пикселей (форма и внешняя граница глифа не меняются — за клетку атласа не выходит).
    Цвет под прозрачным — цвет края (обводки), как у EA."""
    w, h, px = img.w, img.h, img.px
    fill = parse_color(fill, palette)
    outline = parse_color(outline, palette) if outline else None
    widths = outline_px or {}
    # цвет шаблона (средний по непрозрачным) — для переноса оттенков
    n = sr = sg = sb = 0
    for i in range(0, len(px), 4):
        if px[i + 3] == 255:
            n += 1
            sr += px[i]
            sg += px[i + 1]
            sb += px[i + 2]
    base = (sr / n, sg / n, sb / n) if n else (255, 255, 255)
    inside = bytearray(1 if px[i * 4 + 3] >= 128 else 0 for i in range(w * h))
    maxr = max([int(math.ceil(v)) for v in widths.values()] + [0]) + 2
    offs = sorted(((dx, dy, math.hypot(dx, dy)) for dy in range(-maxr, maxr + 1) for dx in range(-maxr, maxr + 1)),
                  key=lambda t: t[2])
    out = bytearray(px)
    for y in range(h):
        for x in range(w):
            i = y * w + x
            o = i * 4
            a = px[o + 3]
            r = widths.get(font_part(x, y), 0) if outline else 0
            if a == 0 and not r:
                out[o:o + 3] = bytes(fill)
                continue
            if r and inside[i]:
                d = maxr + 1.0
                for dx, dy, dd in offs:
                    if dd >= d:
                        break
                    nx, ny = x + dx, y + dy
                    if not (0 <= nx < w and 0 <= ny < h) or not inside[ny * w + nx]:
                        d = dd
                        break
                d -= 0.5                                  # до края глифа (граница между пикселями)
                k = max(0.0, min(1.0, d - r + 0.5))       # 1 — заливка, 0 — обводка
            elif r:
                k = 0.0
            else:
                k = 1.0
            col = [fill[c] * k + outline[c] * (1 - k) if outline else fill[c] for c in range(3)]
            if a:
                col = [col[c] + (px[o + c] - base[c]) * 0.5 for c in range(3)]   # мягкий перенос оттенков шаблона
            out[o:o + 3] = bytes(max(0, min(255, int(v + 0.5))) for v in col)
    img.px[:] = out


# ---------------------------------------------------------------- превью меню (BIGF 8888 256×256)

def shade_map(img, base_rgb, mask=None):
    """Множитель затенения превью: яркость пикселя / яркость цвета зоны (0.35…1.25)."""
    bl = max(1.0, lum(*base_rgb))
    px = img.px

    def f(x, y):
        o = (y * img.w + x) * 4
        return max(0.35, min(1.25, lum(px[o], px[o + 1], px[o + 2]) / bl))
    return f


# ---------------------------------------------------------------- сборка своей формы по SPEC

def template_layers(kit):
    """Все слои шаблона: {слой: Img}."""
    out = {}
    for kind, rel, obj in kit_textures(kit):
        if kind == 'fe':
            out['fe'] = Img(*obj.decode())
            continue
        for t in obj.textures:
            out[layer_name(t.name)] = Img(*tex_decode(obj, t))
    return out


_LAYER_CACHE = {}


def template_layer(kit, layer, game=None):
    """Один слой шаблона (с кешем): Img. game — шаблон другой игры (маски разметки, MASK_GAME)."""
    key = (str(kit), layer) if game is None else (game, str(kit), layer)
    if key not in _LAYER_CACHE:
        for kind, rel, obj in kit_textures(kit, game):
            if kind == 'fe':
                if layer == 'fe':
                    _LAYER_CACHE[key] = Img(*obj.decode())
                continue
            for t in obj.textures:
                if layer_name(t.name) == layer:
                    _LAYER_CACHE[key] = Img(*tex_decode(obj, t))
        if key not in _LAYER_CACHE:
            raise SystemExit(f'{kit}: нет слоя {layer}')
    return _LAYER_CACHE[key]


# Игра, из шаблонов которой берутся маски разметки (template_mask), если в маске нет "game": None — та же, что у
# шаблонов (teamart.set_game). Разметка SPEC NHL 13 рисовалась по шаблонам NHL 13; UV у Legacy те же, а шаблоны
# перерисованы (у «Ванкувера» Legacy нет швов панелей — заливка от seed растекается по всему свитеру), поэтому для
# SPEC NHL 13 под Legacy маски — из NHL 13 (paint --mask-game nhl13).
MASK_GAME = None


def template_mask(spec, w, h):
    """Маска по слою шаблона (раскладка UV у всех комплектов стиля одна): заливка от seed по пикселям, близким
    к цвету seed (thr), затем расширение dilate; ring — только кольцо (расширение минус заливка).
    {"template": "1_28_0", "layer": "jersey_cm", "seed": [x, y], "thr": 40, "dilate": 8, "ring": false,
     "game": "nhl13" (необяз.: шаблон другой игры; по умолчанию MASK_GAME)}"""
    from collections import deque
    img = template_layer(Kit.parse(spec['template']), spec.get('layer', 'jersey_cm'), spec.get('game') or MASK_GAME)
    if (img.w, img.h) != (w, h):
        raise SystemExit(f'маска {spec}: слой {img.w}×{img.h}, нужен {w}×{h}')
    sx, sy = spec['seed']
    px = img.px
    o = (sy * w + sx) * 4
    c0 = (px[o], px[o + 1], px[o + 2])
    thr2 = spec.get('thr', 40) ** 2
    m = bytearray(w * h)
    q = deque([sy * w + sx])
    m[sy * w + sx] = 1
    while q:
        i = q.popleft()
        x, y = i % w, i // w
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if 0 <= nx < w and 0 <= ny < h:
                j = ny * w + nx
                if not m[j]:
                    o = j * 4
                    if (px[o] - c0[0]) ** 2 + (px[o + 1] - c0[1]) ** 2 + (px[o + 2] - c0[2]) ** 2 <= thr2:
                        m[j] = 1
                        q.append(j)
    if spec.get('dilate'):
        d = dilate(m, w, h, spec['dilate'])
        m = bytearray(1 if d[i] and not m[i] else 0 for i in range(w * h)) if spec.get('ring') else d
    return m


def add_regions(rc, regions, palette):
    for reg in regions:
        mask = None
        rect = reg.get('rect')
        if 'mask' in reg:
            mask = template_mask(reg['mask'], rc.img.w, rc.img.h)
            bb = mask_bbox(mask, rc.img.w, rc.img.h)
            if not bb:
                continue
            rect = bb if rect is None else (max(rect[0], bb[0]), max(rect[1], bb[1]), min(rect[2], bb[2]), min(rect[3], bb[3]))
        rc.region(rect, reg['map'], palette, mask=mask, minw=reg.get('minw', 0.0))


def erase_masks(cm, specs, body, log=None):
    """Маски стирания по описаниям [{"rect": […], "thr": 34, "dilate": 3, "holes": true}]: пиксели rect,
    отличающиеся от цвета фона body больше thr, с заполнением дырок и расширением.
    → (маска для стирания, «след» старого логотипа без расширения)."""
    w, h = cm.w, cm.h
    total = bytearray(w * h)
    foot = bytearray(w * h)
    for sp in specs:
        x0, y0, x1, y1 = rect_clip(sp['rect'], w, h)
        thr2 = sp.get('thr', 34) ** 2
        bodyc = parse_color(sp.get('body', body))
        m = bytearray(w * h)
        if sp.get('all'):
            for y in range(y0, y1):
                for x in range(x0, x1):
                    m[y * w + x] = 1
        else:
            for y in range(y0, y1):
                for x in range(x0, x1):
                    o = (y * w + x) * 4
                    d = sum((cm.px[o + c] - bodyc[c]) ** 2 for c in range(3))
                    if d > thr2:
                        m[y * w + x] = 1
            if sp.get('holes', True):
                m = fill_holes(m, w, h, (x0, y0, x1, y1))
        for i in range(w * h):
            if m[i]:
                foot[i] = 1
        d = dilate(m, w, h, sp.get('dilate', 3))
        for i in range(w * h):
            if d[i]:
                total[i] = 1
    return total, foot


def apply_logos(layers, items, svgs, cal, log=None, scale=None):
    """Логотипы на свитер/шорты: цвет (cm), блеск (sm), рельеф (nm). items — [{"svg", "center": [x, y],
    "size": [w, h], "rotate": 0}] в координатах cm; sm/nm другого размера — масштаб координат."""
    cm = layers['cm']
    for it in items:
        svg = svgs[it['svg']]
        cx, cy = it['center']
        fw, fh = it['size']
        rot = it.get('rotate', 0)
        for key in ('cm', 'sm', 'nm'):
            img = layers.get(key)
            if img is None:
                continue
            k = img.w / cm.w
            W = int(math.ceil(max(fw, fh) * k * 1.5)) + 8
            logo = render_logo(svg, W, W, fw * k, fh * k, rot)
            x0, y0 = int(round(cx * k - W / 2)), int(round(cy * k - W / 2))
            if key == 'cm':
                over_at(img, logo, x0, y0)
                continue
            a, L = place_alpha(img.w, img.h, logo, x0, y0)
            if key == 'nm':
                sx, sy = cal.get('sign', (-1.0, 1.0))
                st = it.get('relief', cal.get('strength', 60.0))
                add_relief(img, a, L, (sx * st, sy * st), inner=it.get('inner', 0.3))
            if key == 'sm' and cal.get('gloss'):
                add_gloss(img, a, L, cal['gloss'], inner=it.get('inner', 0.3))
        if log:
            log(f'    логотип {it["svg"]}: центр {cx},{cy}, рамка {fw}×{fh}, поворот {rot}°')


def paint_surface(name, layers, spec, svgs, palette, cal_src=None, log=print):
    """Свитер / шорты / гетры: стирание старых логотипов (cm, sm, nm), перекраска cm по зонам, свои логотипы.
    layers — {'cm': Img, 'sm': Img|None, 'nm': Img|None}. cal_src — калибровка рельефа/блеска (если в
    шаблоне слоя нет своего логотипа). → калибровка."""
    cm = layers['cm']
    zones = [(k, v) for k, v in spec['zones'].items()]
    if spec.get('refine', True):
        zones = refine_zones(cm, zones, palette=palette)
    log(f'  {name}: зоны ' + ', '.join(f'{n}={"#%02x%02x%02x" % c}' for n, c in zones))
    cal = dict(cal_src or {})
    body = dict(zones)[spec.get('body', zones[0][0])]
    if spec.get('erase'):
        mask, foot = erase_masks(cm, spec['erase'], body)
        if layers.get('nm') is not None and not spec.get('no_calibrate'):
            nm = layers['nm']
            f2 = foot if nm.w == cm.w else scale_mask(foot, cm.w, cm.h, nm.w, nm.h)
            k = relief_calibrate(nm, f2, log)
            if k and max(abs(k[0]), abs(k[1])) > 6:          # знак рельефа (сила — своя: регрессия занижает,
                cal['sign'] = (math.copysign(1.0, k[0]), math.copysign(1.0, k[1]))   # у EA края — узкие валики)
        if layers.get('sm') is not None and not spec.get('no_calibrate'):
            sm = layers['sm']
            g = gloss_calibrate(sm, foot if sm.w == cm.w else scale_mask(foot, cm.w, cm.h, sm.w, sm.h), log)
            if g:
                cal['gloss'] = g
        for key in ('cm', 'sm', 'nm'):
            img = layers.get(key)
            if img is None:
                continue
            m = mask if img.w == cm.w else scale_mask(mask, cm.w, cm.h, img.w, img.h)
            erase(img, m, chans=(0, 1) if key == 'nm' else (0, 1, 2), log=log if key == 'cm' else None)
            if key == 'nm':
                renormalize(img, m)
    if 'relief' in spec:
        cal['strength'] = float(spec['relief'])
    rc = Recolor(cm, zones, keep=spec.get('keep', 60), palette=palette, snap=spec.get('snap', 0.0))
    rc.set(spec.get('map', {}), palette)
    add_regions(rc, spec.get('regions', ()), palette)
    for b in spec.get('bands', ()):
        rc.bands(b['rect'], b['zones'], b['bands'], b.get('axis', 'y'), b.get('edge', 'lo'), palette,
                 start=b.get('start'), units=b.get('units', 'frac'), smooth=b.get('smooth', 0),
                 fill=b.get('fill', False))
    layers['cm'] = rc.render()
    if spec.get('logos'):
        apply_logos(layers, spec['logos'], svgs, cal, log)
    return cal


def paint_fe(img, spec, svgs, palette, log=print):
    """Превью меню: перекраска по зонам (с зоной чёрного для затенения), стирание старого логотипа
    (гладкая заливка), свой логотип с затенением по месту."""
    zones = [(k, v) for k, v in spec['zones'].items()]
    if spec.get('refine', True):
        zones = refine_zones(img, zones, palette=palette)
    body = dict(zones)[spec.get('body', zones[0][0])]
    alpha = bytes(img.px[3::4])
    orig = bytes(img.px)
    shade = None
    if spec.get('erase'):
        mask, _ = erase_masks(img, spec['erase'], body)
        lb = lum(*body) * 0.25
        px = img.px
        known = bytearray(1 if px[i * 4 + 3] >= 250 and lum(px[i * 4], px[i * 4 + 1], px[i * 4 + 2]) >= lb else 0
                          for i in range(img.w * img.h))
        erase(img, mask, margin=12, ring=4, texture=False, known=known)
        shade = shade_map(img, body)
    if spec.get('blur'):
        # шум фактуры тёмного шаблона при перекраске в светлое становится «крапинами» — раскладка по зонам
        # по слегка размытой картинке (с весом альфы: края силуэта не темнеют)
        r = int(spec['blur'])
        w, h, px = img.w, img.h, img.px
        al = [px[i * 4 + 3] / 255.0 for i in range(w * h)]
        bal = box_blur(al, w, h, r)
        for c in range(3):
            pl = box_blur([px[i * 4 + c] * al[i] for i in range(w * h)], w, h, r)
            for i in range(w * h):
                if bal[i] > 1e-3:
                    px[i * 4 + c] = max(0, min(255, int(pl[i] / bal[i] + 0.5)))
    rc = Recolor(img, zones, keep=spec.get('keep', 70), palette=palette, snap=spec.get('snap', 0.0))
    rc.set(spec.get('map', {}), palette)
    add_regions(rc, spec.get('regions', ()), palette)
    out = rc.render()
    out.px[3::4] = alpha
    ka = spec.get('keep_alpha', 0)
    if ka:                     # полупрозрачное (манекен, тень внизу) — как в шаблоне: «чёрную» зону можно
        for i in range(out.w * out.h):          # тогда красить в тень цвета формы, не трогая манекен
            if alpha[i] < ka:
                out.px[i * 4:i * 4 + 3] = orig[i * 4:i * 4 + 3]
    for it in spec.get('logos', ()):
        cx, cy = it['center']
        fw, fh = it['size']
        W = int(max(fw, fh) * 1.5) + 8
        logo = render_logo(svgs[it['svg']], W, W, fw, fh, it.get('rotate', 0))
        over_at(out, logo, int(round(cx - W / 2)), int(round(cy - W / 2)), shade)
    return out


def paint(spec_path, outdir, only=None, preview=None, work=None, log=print):
    """Комплекты по SPEC (формат — в начале модуля) → файлы в OUTDIR (раскладка cache:); work — PNG изменённых
    слоёв; preview — лист превью <team>.png. → (список путей, слои). У комплекта может быть "container" (S_A_V) —
    основа файлов под номер другой длины; нет — default_container."""
    spec = ta.load_spec(spec_path)
    base = os.path.dirname(os.path.abspath(spec_path))
    palette = spec.get('colors', {})
    svgs = {k: svg_load(v, base) for k, v in spec.get('svg', {}).items()}
    painted = {}
    made = []
    for kit_name, ks in spec['kits'].items():
        if only and kit_name not in only:
            continue
        tpl, new = Kit.parse(ks['template']), Kit.parse(ks['kit'])
        log(f'{spec.get("team", "")} {kit_name}: шаблон {tpl} → {new}')
        src = template_layers(tpl)
        keep = {ln: rgba_sha1(bytes(img.px)) for ln, img in src.items()}
        L = {ln: img.copy() for ln, img in src.items()}
        # свитер
        jl = {'cm': L['jersey_cm'], 'sm': L['jersey_sm'], 'nm': L['jersey_nm']}
        cal = paint_surface('свитер', jl, ks['jersey'], svgs, palette, log=log)
        L['jersey_cm'], L['jersey_sm'], L['jersey_nm'] = jl['cm'], jl['sm'], jl['nm']
        # шрифт
        if 'font' in ks:
            f = ks['font']
            paint_font(L['font_cm'], f['fill'], f.get('outline'), f.get('outline_px'), palette)
            log(f'  шрифт: заливка {f["fill"]}, обводка {f.get("outline")} {f.get("outline_px")}')
        # шорты
        if 'pant' in ks:
            ps = ks['pant']
            if 'same_as' in ps:
                ref = ps['same_as']
                if ref not in painted:                     # тот комплект в этом запуске не собирается — шорты отдельно
                    rs = spec['kits'][ref]
                    rk = Kit.parse(rs['template'])
                    pl = {'cm': template_layer(rk, 'pant_cm').copy(), 'sm': template_layer(rk, 'pant_sm').copy(),
                          'nm': template_layer(rk, 'pant_nm').copy()}
                    paint_surface(f'шорты ({ref})', pl, rs['pant'], svgs, palette, cal_src=cal, log=log)
                    painted[ref] = {'pant_cm': pl['cm'], 'pant_sm': pl['sm'], 'pant_nm': pl['nm']}
                for ln in ('pant_cm', 'pant_sm', 'pant_nm'):
                    L[ln] = painted[ref][ln].copy()
                log(f'  шорты: как у {ref}')
            else:
                pl = {'cm': L['pant_cm'], 'sm': L['pant_sm'], 'nm': L['pant_nm']}
                paint_surface('шорты', pl, ps, svgs, palette, cal_src=cal, log=log)
                L['pant_cm'], L['pant_sm'], L['pant_nm'] = pl['cm'], pl['sm'], pl['nm']
        # гетры
        if 'sock' in ks:
            sl = {'cm': L['sock_cm']}
            paint_surface('гетры', sl, ks['sock'], svgs, palette, log=log)
            L['sock_cm'] = sl['cm']
        # превью
        if 'fe' in ks:
            L['fe'] = paint_fe(L['fe'], ks['fe'], svgs, palette, log)
            log('  превью: готово')
        painted[kit_name] = L
        if work:
            d = os.path.join(work, f'{spec.get("team", "kit")}_{kit_name}')
            os.makedirs(d, exist_ok=True)
            for ln, img in L.items():
                if keep.get(ln) != rgba_sha1(bytes(img.px)):
                    img.save(os.path.join(d, ln + '.png'))
        layers = {ln: img.tup() for ln, img in L.items()}
        cont = Kit.parse(ks['container']) if ks.get('container') else default_container(tpl, new)
        if cont is not tpl:
            log(f'  контейнер файлов: {cont}')
        res = build_kit(tpl, new, layers, outdir, keep=keep, log=log, container=cont)
        made += list(res)
    if preview:
        kits = [(ks.get('label', name), Kit.parse(ks['kit'])) for name, ks in spec['kits'].items()
                if not only or name in only]
        out = os.path.join(preview, f'{spec.get("team", "kits")}.png')
        sheet(outdir, spec.get('title', spec.get('team', '')), kits, out)
        log(f'лист превью: {out}')
    return made, painted


def cmd_paint(args):
    global MASK_GAME
    spec, outdir = args[0], args[1]
    if '--mask-game' in args:
        MASK_GAME = args[args.index('--mask-game') + 1]
    only = args[args.index('--kits') + 1].split(',') if '--kits' in args else None
    work = args[args.index('--work') + 1] if '--work' in args else None
    preview = args[args.index('--preview') + 1] if '--preview' in args else None
    made, painted = paint(spec, outdir, only, preview, work)
    print(f'файлов: {len(made)}')


# ---------------------------------------------------------------- проверка собранного

def verify(outdir, new, template, log=print):
    """Собранный комплект против шаблона: имена растров — под новый номер; всё, кроме буферов текстур и
    имён, — байт-в-байт как у шаблона; раскладка и мипы сходятся (teamart.roundtrip --deep); все уровни
    разбираются. → число ошибок."""
    bad = 0
    tex = {kind: (rel, obj) for kind, rel, obj in kit_textures(template)}
    for kind, _ in KIT_FILES:
        rel = new.path(kind)
        path = os.path.join(outdir, *rel.split('/'))
        if not os.path.exists(path):
            log(f'  НЕТ ФАЙЛА {rel}')
            bad += 1
            continue
        data = open(path, 'rb').read()
        trel, tobj = tex[kind]
        if kind == 'fe':
            obj = ta.UiLogo(data, rel)
            same = [e[0] for e in obj.head.big.entries] == [e[0] for e in tobj.head.big.entries]
            apt = obj.head.big.get('0') == tobj.head.big.get('0')
            ok = same and apt and obj.fetch.words == tobj.fetch.words and obj.stage == tobj.stage
            log(f'  {rel}: BIGF {"как у шаблона" if ok else "ОТЛИЧАЕТСЯ"} (записи, Apt, константа выборки, сцена)')
            bad += not ok
            continue
        obj = ta.Rw4(data, rel)
        names = [t.name for t in obj.textures]
        want = [t.name.replace(f'_{template.tag()}_', f'_{new.tag()}_') for t in tobj.textures]
        mask = bytearray(len(data))
        for t in obj.textures:
            mask[t.data_off:t.data_off + t.size] = b'\1' * t.size
        for sp, ln in obj.name_slots:
            mask[sp:sp + ln] = b'\1' * ln
        same = len(data) == len(tobj.raw) and all(m or a == b for m, a, b in zip(mask, data, tobj.raw))
        _, res = ta.roundtrip(path, deep=True)
        lay = all(v for k, v in res.items() if not k.endswith(':mips_psnr'))
        own = {t.name for t, t0 in zip(obj.textures, tobj.textures) if obj.buffer(t) != tobj.buffer(t0)}
        mips = {k.split(':')[0]: v for k, v in res.items() if k.endswith(':mips_psnr') and k.split(':')[0] in own}
        dec = True
        for t in obj.textures:
            if t.layout is None:
                dec = False
                continue
            for lv in range(len(t.layout.levels)):
                tex_decode(obj, t, lv)
        ok = names == want and same and lay and dec
        bad += not ok
        worst = min((min(v) for v in mips.values() if v), default=None)
        log(f'  {rel}: имена {"OK" if names == want else names}; вне буферов {"как у шаблона" if same else "ОТЛИЧАЕТСЯ"}; '
            f'раскладка {"OK" if lay else "ОШИБКА"}; уровней разобрано: все{"" if dec else " — НЕТ"}'
            + (f'; мипы новых слоёв — соседние уровни ≥ {worst:.1f} дБ' if worst is not None else ''))
    return bad


def cmd_verify(args):
    outdir, bad = args[0], 0
    for pair in args[1:]:
        a, b = pair.split('=')
        new, tpl = Kit.parse(a), Kit.parse(b)
        print(f'комплект {new} (шаблон {tpl}):')
        bad += verify(outdir, new, tpl)
    print('итог:', 'OK' if not bad else f'ошибок {bad}')
    return bad


# ---------------------------------------------------------------- лист превью

def kit_images(outdir, kit):
    """Слои собранного комплекта (из файлов OUTDIR, как их увидит игра — после сжатия): {слой: Img}."""
    out = {}
    for kind in ('jersey', 'pant', 'sock'):
        rw = ta.Rw4(open(os.path.join(outdir, *kit.path(kind).split('/')), 'rb').read())
        for t in rw.textures:
            ln = layer_name(t.name)
            if ln in ('jersey_cm', 'pant_cm', 'sock_cm', 'font_cm'):
                out[ln] = Img(*tex_decode(rw, t, 0))
    fe = ta.UiLogo(open(os.path.join(outdir, *kit.path('fe').split('/')), 'rb').read())
    out['fe'] = Img(*fe.decode())
    return out


def render_page(html, out_png, w, h):
    """Снимок страницы w×h (непрозрачной) — как teamart.render_html, но без чтения PNG обратно
    (playerhead.png_read не читает RGB без альфы, а такой снимок Chrome сохраняет без неё)."""
    import subprocess
    tmp = tempfile.mkdtemp(prefix='kitpaint_p_')
    try:
        pg = os.path.join(tmp, 'page.html')
        open(pg, 'w', encoding='utf-8').write(html)
        out_abs = os.path.abspath(out_png)
        os.makedirs(os.path.dirname(out_abs), exist_ok=True)
        if os.path.exists(out_abs):
            os.remove(out_abs)
        cmd = [ta.browser(), '--headless=new', '--disable-gpu', '--hide-scrollbars', '--no-first-run',
               '--no-default-browser-check', '--force-device-scale-factor=1', f'--user-data-dir={os.path.join(tmp, "p")}',
               f'--window-size={w},{h}', '--virtual-time-budget=4000', f'--screenshot={out_abs}',
               'file:///' + pg.replace('\\', '/')]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=180, check=False)
        if not os.path.exists(out_abs):
            raise SystemExit(f'браузер не сохранил {out_abs}')
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _png_uri(img, tmp, name):
    import base64
    p = os.path.join(tmp, name + '.png')
    img.save(p)
    return 'data:image/png;base64,' + base64.b64encode(open(p, 'rb').read()).decode('ascii')


def sheet(outdir, title, kits, out_png):
    """Лист превью (Chrome/Edge без окна): kits — [(подпись, Kit)]; на комплект — развёртка свитера, превью меню,
    шрифт номеров, шорты, гетры."""
    import html as H
    tmp = tempfile.mkdtemp(prefix='kitpaint_s_')
    try:
        blocks = []
        for n, (label, kit) in enumerate(kits):
            im = kit_images(outdir, kit)
            u = {k: _png_uri(v, tmp, f'{n}_{k}') for k, v in im.items()}
            fig = lambda k, w, h, cap, cls='': (f'<figure><img class="{cls}" src="{u[k]}" style="width:{w}px;height:{h}px">'
                                                f'<figcaption>{H.escape(cap)}</figcaption></figure>')
            blocks.append(
                f'<section><h2>{H.escape(label)} <span>{H.escape(kit.path("jersey").split("/")[-1])}</span></h2>'
                f'<div class="row">{fig("jersey_cm", 512, 512, "свитер — развёртка UV 1024² (уменьшено)")}'
                f'{fig("fe", 384, 384, "превью в меню (256² ×1,5)")}'
                f'<div class="col">{fig("font_cm", 256, 256, "шрифт номеров и фамилии", "chk")}'
                f'{fig("pant_cm", 256, 256, "шорты")}</div>'
                f'<div class="col">{fig("sock_cm", 512, 256, "гетры")}</div></div></section>')
        W, Hh = 1780, 90 + 650 * len(kits)
        css = ('html,body{margin:0;background:#2b2f36;color:#e8eaed;font:15px "Segoe UI",Arial,sans-serif;'
               f'width:{W}px;height:{Hh}px;overflow:hidden}}'
               'h1{margin:0;padding:18px 24px 6px;font-size:26px;font-weight:600}'
               'section{padding:6px 24px 0}h2{margin:10px 0 8px;font-size:19px;font-weight:600}'
               'h2 span{font-weight:400;color:#9aa0a6;font-size:14px;margin-left:10px}'
               '.row{display:flex;gap:18px;align-items:flex-start}.col{display:flex;flex-direction:column;gap:10px}'
               'figure{margin:0}figcaption{color:#b9bec5;font-size:13px;margin-top:4px}'
               'img{display:block;background:#1f2228;image-rendering:auto}'
               '.chk{background:repeating-conic-gradient(#8a8f96 0 25%,#6c7178 0 50%) 0 0/16px 16px}')
        page = (f'<!doctype html><html><head><meta charset="utf-8"><style>{css}</style></head><body>'
                f'<h1>{H.escape(title)}</h1>{"".join(blocks)}</body></html>')
        render_page(page, out_png, W, Hh)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return out_png


def cmd_sheet(args):
    """sheet OUTDIR "Заголовок" "подпись=S_A_V[_F]" … OUT.png"""
    outdir, title, out = args[0], args[1], args[-1]
    kits = []
    for a in args[2:-1]:
        label, k = a.rsplit('=', 1)
        kits.append((label, Kit.parse(k)))
    sheet(outdir, title, kits, out)
    print(f'{out}: готово')


# ---------------------------------------------------------------- команды

def main():
    game, argv = ta.split_game(sys.argv[1:])
    if len(argv) < 2:
        sys.exit(__doc__)
    ta.set_game(game)
    cmd, args = argv[0], argv[1:]
    if cmd == 'files':
        cmd_files(args)
    elif cmd == 'unpack':
        unpack(Kit.parse(args[0]), args[1])
    elif cmd == 'pack':
        cmd_pack(args)
    elif cmd == 'roundtrip':
        sys.exit(1 if cmd_roundtrip(args) else 0)
    elif cmd == 'paint':
        cmd_paint(args)
    elif cmd == 'sheet':
        cmd_sheet(args)
    elif cmd == 'verify':
        sys.exit(1 if cmd_verify(args) else 0)
    else:
        sys.exit(__doc__)


if __name__ == '__main__':
    main()
