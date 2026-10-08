"""Фон меню NHL 13 (Xbox 360): разбор роликов Apt (Flash EA) фона, перекраска и превью.

Синий анимированный фон почти всех меню — ролик game/background/NHLBlueBackground (boot.big,
nhlbluebackground.big: подложка mcColor) + его арт и анимация NHLBlueBackgroundComponents
(cache.big, nhlbluebackgroundcomponents.big). Это не видео: текстуры DXT5, заливки и кадры Apt.

    python febg.py info FILE.big…                    # записи BIGF, импорт/экспорт, все цвета: заливки,
                                                     # множители/добавки PlaceObject, текстуры (средний цвет)
    python febg.py dump FILE.big [--frames N]        # символы, кадры, PlaceObject, заливки геометрии
    python febg.py textures FILE.big OUTDIR          # текстуры → PNG
    python febg.py recolor OUTDIR [--gray [УРОВЕНЬ] | --color RRGGBB] [--sets blue[,mainmenu]]
        # перекраска → OUTDIR в раскладке cache: (fe/ion/game/background/…). Основной синий #0040BA
        # становится серым той же светлоты (--gray, #5D5D5D), серым уровня 0…255 или цветом RRGGBB;
        # остальное — тем же поворотом оттенка, насыщенностью и светлотой (белое/чёрное не меняются)
    python febg.py verify OUTDIR                     # сверка с оригиналами: изменены только цвет и текстуры
    python febg.py preview OUTDIR [--set blue|mainmenu] [--src DIR[,DIR2]] [--label ТЕКСТ]
                       [--also "подпись=DIR;…"] [--times 0,2.5,…] [--width 640] [--name compare] [--no-frames]
        # OUTDIR/<name>.png — сетка кадров (строки — оригинал и варианты, столбцы — секунды анимации),
        # frames/<name>/*.png — те же кадры по отдельности, <name>.html — живая анимация всех вариантов
        # В --src/--also элемент «@игра» (@nhl13, @legacy) — оригиналы другой игры вместо своих:
        # --also "NHL 13=@nhl13;NHL 13 серый=@nhl13,game/work/fe-bg/out"
    … --game nhl13|legacy (или NHL_GAME) — чьи оригиналы: у NHL Legacy фон — свой (тёмная арена, cacheboot.big),
        см. docs/fe-background.md, «NHL Legacy»

Подробности — docs/fe-background.md. Только стандартная библиотека (+ Chrome или Edge для preview).
Каталог игры — переменная NHL13_GAME или game/ рядом с tools/.
"""
import argparse, base64, colorsys, json, os, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import playerhead as ph  # noqa: E402  (BIGF, XPR2, RefPack, PNG)
import teamart as ta     # noqa: E402  (константа выборки, раскладка, DXT1/3/5 и 8888)
import gameprofile       # noqa: E402  (--game: NHL 13 / NHL Legacy)

GAME = gameprofile.get('nhl13')          # игра (--game / NHL_GAME) — задаётся в main()

# ---------------------------------------------------------------- Apt (Flash EA), вариант «Apt Data:1:7:4»

SIG = 0x09876543
CHAR_NAMES = {1: 'Shape', 2: 'EditText', 3: 'Font', 4: 'Button', 5: 'Sprite', 6: 'Sound', 7: 'Image',
              8: 'Morph', 9: 'Movie', 10: 'StaticText', 11: 'None', 12: 'Video'}
ITEM_NAMES = {1: 'Action', 2: 'FrameLabel', 3: 'PlaceObject', 4: 'RemoveObject', 5: 'BackgroundColor',
              6: 'StartSound', 7: 'StartSoundStream', 8: 'InitAction'}
PO_MOVE, PO_CHAR, PO_MATRIX, PO_COLOR, PO_RATIO, PO_NAME, PO_CLIP, PO_ACTIONS = 1, 2, 4, 8, 16, 32, 64, 128


def u32(b, o):
    return struct.unpack_from('>I', b, o)[0]


def f32(b, o):
    return struct.unpack_from('>f', b, o)[0]


def cstr(b, o):
    return b[o:b.index(b'\0', o)].decode('latin1') if o else ''


class PlaceObject:
    """PlaceObject (0x40 байт): флаги, глубина, символ, матрица 2×2 + сдвиг, цвет-множитель и
    цвет-добавка (ARGB), ratio, имя, глубина маски, обработчики."""
    SIZE = 0x40

    def __init__(self, d, off):
        self.off = off
        (_, self.flags, self.depth, self.char) = struct.unpack_from('>IIiI', d, off)
        self.matrix = struct.unpack_from('>6f', d, off + 0x10)
        self.mul, self.add = struct.unpack_from('>II', d, off + 0x28)
        self.ratio = f32(d, off + 0x30)
        self.name = cstr(d, u32(d, off + 0x34)) if self.flags & PO_NAME else ''
        self.clip = struct.unpack_from('>i', d, off + 0x38)[0] if self.flags & PO_CLIP else 0
        self.actions = u32(d, off + 0x3C)

    def describe(self):
        fl = ''.join(c for c, b in zip('MCXTRNKA', (1, 2, 4, 8, 16, 32, 64, 128)) if self.flags & b)
        s = f'place {fl:5s} d={self.depth:<3d}'
        if self.flags & PO_CHAR:
            s += f' char={self.char}'
        if self.flags & PO_MATRIX:
            a, b, c, dd, tx, ty = self.matrix
            s += f' m=({a:.4g},{b:.4g},{c:.4g},{dd:.4g},{tx:.5g},{ty:.5g})'
        if self.flags & PO_COLOR:
            s += f' mul={self.mul:08X} add={self.add:08X}'
        if self.flags & PO_RATIO:
            s += f' ratio={self.ratio:.4g}'
        if self.name:
            s += f' name={self.name}'
        if self.clip:
            s += f' clip≤{self.clip}'
        if self.flags & PO_ACTIONS:
            s += f' actions@{self.actions:#x}'
        return s


class Item:
    def __init__(self, d, off):
        self.off = off
        self.type = u32(d, off)
        self.po = PlaceObject(d, off) if self.type == 3 else None
        if self.type == 4:
            self.depth = u32(d, off + 4)
        elif self.type == 5:
            self.color = u32(d, off + 4)
        elif self.type == 2:
            self.label = cstr(d, u32(d, off + 4))
        elif self.type == 1:
            self.code = u32(d, off + 4)
        elif self.type == 8:
            self.sprite, self.code = u32(d, off + 4), u32(d, off + 8)

    def describe(self):
        if self.po:
            return self.po.describe()
        if self.type == 4:
            return f'remove d={self.depth}'
        if self.type == 5:
            return f'background {self.color:08X}'
        if self.type == 2:
            return f'label "{self.label}"'
        if self.type == 1:
            return f'action @{self.code:#x}'
        if self.type == 8:
            return f'initaction sprite={self.sprite} @{self.code:#x}'
        return f'{ITEM_NAMES.get(self.type, self.type)}'


class Char:
    def __init__(self, d, idx, off):
        self.idx, self.off = idx, off
        self.type = u32(d, off) if off else 0
        self.frames = []
        if not off:
            return
        if u32(d, off + 4) != SIG:
            raise ValueError(f'символ {idx} @{off:#x}: нет подписи')
        if self.type in (5, 9):                       # Sprite, Movie: +0x10 кадров, +0x14 таблица
            n, p = u32(d, off + 0x10), u32(d, off + 0x14)
            for k in range(n):
                cnt, ip = u32(d, p + 8 * k), u32(d, p + 8 * k + 4)
                self.frames.append([Item(d, u32(d, ip + 4 * j)) for j in range(cnt)])
        elif self.type == 7:                          # Image: +0x10 — номер текстуры (= номер символа)
            self.texture = u32(d, off + 0x10)
        elif self.type == 1:                          # Shape: +0x08 — растр, +0x10 рамка, +0x20 геометрия
            self.image = u32(d, off + 8)
            self.bounds = struct.unpack_from('>4f', d, off + 0x10)
            self.geometry = u32(d, off + 0x20)

    @property
    def name(self):
        return CHAR_NAMES.get(self.type, str(self.type)) if self.off else 'import'


class Apt:
    """Ролик Apt: запись «0» (Apt Data) + «1» (Apt constant file, по +0x14 — смещение Movie)."""

    def __init__(self, data, const):
        if data[:8] != b'Apt Data' or const[:17] != b'Apt constant file':
            raise ValueError('не Apt')
        self.data, self.const = data, const
        self.version = data[9:data.index(b'\x1a')].decode('latin1')
        self.movie_off = u32(const, 0x14)
        m = self.movie_off
        if struct.unpack_from('>II', data, m) != (9, SIG):
            raise ValueError(f'нет символа Movie по {m:#x}')
        nchar, cp = u32(data, m + 0x1C), u32(data, m + 0x20)
        self.width, self.height, self.ms = u32(data, m + 0x24), u32(data, m + 0x28), u32(data, m + 0x2C)
        self.chars = [Char(data, i, u32(data, cp + 4 * i)) for i in range(nchar)]
        ni, ip, ne, ep = struct.unpack_from('>IIII', data, m + 0x30)
        self.imports = [(cstr(data, u32(data, ip + 16 * k)), cstr(data, u32(data, ip + 16 * k + 4)),
                         u32(data, ip + 16 * k + 8)) for k in range(ni)]
        self.exports = [(cstr(data, u32(data, ep + 8 * k)), u32(data, ep + 8 * k + 4)) for k in range(ne)]

    def place_objects(self):
        """Все PlaceObject: (символ-хозяин, кадр, PlaceObject)."""
        for ch in self.chars:
            for fi, fr in enumerate(ch.frames):
                for it in fr:
                    if it.po:
                        yield ch, fi, it.po


# ---------------------------------------------------------------- геометрия Shape (запись «<номер+1>»)

FILL_TEXTURED, FILL_SOLID, FILL_LINE = 0, 2, 3


class Fill:
    """Заливка: +0 размер, +4 тип (0 — текстура, 2 — цвет, 3 — линии), +0xC толщина линии,
    +0x10 цвет ARGB, +0x14 символ Image, +0x20 матрица текстуры (6 float, точка → тексель),
    +0x38 число треугольников (отрезков), +0x3C смещение вершин (32 байта на вершину треугольника,
    16 — отрезка)."""

    def __init__(self, g, off):
        self.off = off
        self.size, self.type = u32(g, off), u32(g, off + 4)
        self.width = f32(g, off + 0xC)
        self.color, self.image = u32(g, off + 0x10), u32(g, off + 0x14)
        self.texmat = struct.unpack_from('>6f', g, off + 0x20)
        n, vo = u32(g, off + 0x38), u32(g, off + 0x3C)
        if self.type == FILL_LINE:
            self.verts = [struct.unpack_from('>2f', g, off + vo + 16 * k) for k in range(2 * n)]
        else:
            self.verts = [struct.unpack_from('>2f', g, off + vo + 32 * k) for k in range(3 * n)]
        self.count = n


def parse_geometry(g):
    """Геометрия: u32 размер, u32 число сеток, 0, смещения сеток; сетка: размер, число заливок, 0,
    смещения заливок (от начала сетки)."""
    meshes = []
    n = u32(g, 4)
    for k in range(n):
        mo = u32(g, 12 + 4 * k)
        nf = u32(g, mo + 4)
        meshes.append([Fill(g, mo + u32(g, mo + 12 + 4 * j)) for j in range(nf)])
    return meshes


# ---------------------------------------------------------------- файл фона: BIGF + Apt + геометрия + текстуры

def _expand5(v):
    return (v << 3) | (v >> 2)


def _expand6(v):
    return (v << 2) | (v >> 4)


def _single_tables():
    """Для каждого значения 0…255 — пара концов (5/6 бит), у которой точка 2/3·c0 + 1/3·c1
    (индекс 2 в блоке DXT) ближе всего к значению (как OMatch5/OMatch6 в stb_dxt)."""
    tabs = []
    for bits, exp in ((5, _expand5), (6, _expand6)):
        n = 1 << bits
        tab = []
        for v in range(256):
            best = None
            for a in range(n):
                ea = exp(a)
                for b in range(n):
                    err = abs((2 * ea + exp(b)) / 3 - v)
                    if best is None or err < best[0]:
                        best = (err, a, b)
            tab.append(best[1:])
        tabs.append(tab)
    return tabs


_SINGLE = None


def solid_color_block(rgb):
    """Цветовая часть блока DXT (8 байт, порядок PC) для 16 одинаковых текселей: концы подобраны так,
    чтобы точка с индексом 2 (или 3 после обмена концов) была почти ровно этим цветом — у обычного
    кодировщика серый в 565 уходит в зелень на 2–3 единицы."""
    global _SINGLE
    if _SINGLE is None:
        _SINGLE = _single_tables()
    t5, t6 = _SINGLE
    (r0, r1), (g0, g1), (b0, b1) = t5[rgb[0]], t6[rgb[1]], t5[rgb[2]]
    c0, c1 = (r0 << 11) | (g0 << 5) | b0, (r1 << 11) | (g1 << 5) | b1
    if c0 > c1:
        idx = 0xAAAAAAAA                               # все индексы 2: 2/3·c0 + 1/3·c1
    elif c0 < c1:
        c0, c1, idx = c1, c0, 0xFFFFFFFF               # обмен: та же точка — индекс 3
    elif c0 == 0:
        c0, c1, idx = 1, 0, 0x55555555                 # чёрный: «c0 > c1», все индексы 1 → c1 = 0
    else:
        c1, idx = c0 - 1, 0                            # концы совпали — цвет точно c0 (индекс 0)
    return struct.pack('<HHI', c0, c1, idx)


def fix_solid_blocks(fmt, blocks, rgba, w, h):
    """Цвет блоков, где видимые тексели (альфа ≥ 8) одного цвета или серые в пределах 4 уровней, —
    заново, одним цветом через solid_color_block: серый остаётся серым (обычный подбор концов в 565
    даёт зелёный/пурпурный оттенок в 2–4 единицы)."""
    if fmt not in (ta.FMT_DXT1, ta.FMT_DXT3, ta.FMT_DXT5) or w % 4 or h % 4:
        return blocks
    step = 8 if fmt == ta.FMT_DXT1 else 16
    out = bytearray(blocks)
    k = 0
    for by in range(0, h, 4):
        for bx in range(0, w, 4):
            px = [rgba[((by + y) * w + bx + x) * 4:((by + y) * w + bx + x) * 4 + 4] for y in range(4) for x in range(4)]
            vis = [p for p in px if p[3] >= 8]
            if fmt == ta.FMT_DXT1 and len(vis) < 16:
                vis = []                               # прозрачность DXT1 — не трогаем
            color = None
            if vis and all(p[:3] == vis[0][:3] for p in vis):
                color = tuple(vis[0][:3])
            elif vis and all(p[0] == p[1] == p[2] for p in vis) and max(p[0] for p in vis) - min(p[0] for p in vis) <= 4:
                wsum = sum(p[3] for p in vis)
                g = round(sum(p[0] * p[3] for p in vis) / wsum)
                color = (g, g, g)
            if color is not None:
                out[k * step + step - 8:k * step + step] = solid_color_block(color)
            k += 1
    return bytes(out)


class Texture:
    def __init__(self, name, xpr):
        self.name, self.xpr = name, xpr
        self.fetch = ta.Fetch(xpr.fetch)
        self.layout = ta.Layout(self.fetch)

    def decode(self):
        f = self.fetch
        return ta.dxt_decode(f.fmt, self.layout.get_level(self.xpr.data, 0), f.width, f.height)

    def encode(self, rgba):
        f = self.fetch
        blocks = fix_solid_blocks(f.fmt, ta.dxt_encode(f.fmt, rgba, f.width, f.height), rgba, f.width, f.height)
        buf = bytearray(self.xpr.dsize)
        self.layout.put_level(buf, 0, blocks)
        return self.xpr.build(bytes(buf))


class FeMovie:
    """Ролик интерфейса (*.big): записи, Apt, геометрия по номеру символа, текстуры по номеру символа."""

    def __init__(self, data, path=''):
        self.path = path
        self.big = ph.Bigf(data)
        self.raw = {}       # имя записи → (распакованное, было ли сжато)
        for n, blob in self.big.entries:
            if blob:
                self.raw[n] = ph.unpack_entry(blob)
        self.apt = Apt(self.raw['0'][0], self.raw['1'][0])
        self.geometry, self.textures = {}, {}
        for ch in self.apt.chars:
            key = str(ch.idx + 1)                     # запись = номер символа + 1
            if ch.type == 1 and key in self.raw:
                self.geometry[ch.idx] = parse_geometry(self.raw[key][0])
            elif ch.type == 7 and key in self.raw and self.raw[key][0][:4] == b'XPR2':
                self.textures[ch.idx] = Texture(key, ph.Xpr2(self.raw[key][0]))

    @classmethod
    def load(cls, path):
        return cls(open(path, 'rb').read(), path)


def build_bigf(big, trailer=None):
    """BIGF как у EA: Bigf.build + общий размер (u32 LE по +4) добит нулями до кратного 4
    (проверено байт-в-байт на 383 файлах fe/ion); хвост — исходный."""
    out = bytearray(big.build(b''))
    out += b'\0' * (-len(out) % 4)
    struct.pack_into('<I', out, 4, len(out))
    return bytes(out) + (big.trailer if trailer is None else trailer)


def pack_like(data, packed):
    return ph.refpack_compress(data) if packed else data


# ---------------------------------------------------------------- цвет

def hexcolor(s):
    s = s.strip().lstrip('#')
    if len(s) == 3:
        s = ''.join(c * 2 for c in s)
    if len(s) != 6:
        raise ValueError(f'цвет {s!r}: нужно RRGGBB')
    return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))


def hls(rgb):
    return colorsys.rgb_to_hls(*(c / 255.0 for c in rgb))


def chroma(rgb):
    return (max(rgb) - min(rgb)) / 255.0


BASE_BLUE = (0, 64, 186)    # основной синий фона: текстура символа 1 в nhlbluebackgroundcomponents.big


class Recolor:
    """Перекраска «как поворот цветового круга»: главный синий фона (base) переходит в target,
    остальное — так же: оттенок сдвигается на ту же величину, насыщенность умножается на s_t / s_b,
    светлота (HSL) — по ломаной (0 → 0, l_b → l_t, 1 → 1). Чёрное, белое и серое при сохранённой
    светлоте не меняются, альфа — никогда."""

    def __init__(self, target, base=BASE_BLUE):
        self.base, self.target = tuple(base), tuple(target)
        hb, lb, sb = hls(base)
        ht, lt, st = hls(target)
        self.dh = ht - hb
        self.ks = st / sb if sb > 1e-6 else 0.0
        self.lb, self.lt = lb, lt
        self.memo = {}

    def describe(self):
        b, t = self.base, self.target
        return (f'#{b[0]:02X}{b[1]:02X}{b[2]:02X} → #{t[0]:02X}{t[1]:02X}{t[2]:02X} '
                f'(оттенок {self.dh * 360:+.0f}°, насыщенность ×{self.ks:.2f}, '
                f'светлота {self.lb:.3f} → {self.lt:.3f})')

    def curve(self, l):
        lb, lt = self.lb, self.lt
        if l <= lb:
            return l * lt / lb if lb > 0 else lt
        return lt + (l - lb) * (1 - lt) / (1 - lb) if lb < 1 else lt

    def rgb(self, rgb):
        rgb = tuple(rgb)
        out = self.memo.get(rgb)
        if out is None:
            h, l, s = hls(rgb)
            r, g, b = colorsys.hls_to_rgb((h + self.dh) % 1.0, min(1.0, max(0.0, self.curve(l))),
                                          min(1.0, s * self.ks))
            out = self.memo[rgb] = (round(r * 255), round(g * 255), round(b * 255))
        return out

    def argb(self, v):
        """Цвет заливки (ARGB): меняется RGB, альфа остаётся."""
        r, g, b = self.rgb(((v >> 16) & 255, (v >> 8) & 255, v & 255))
        return (v & 0xFF000000) | (r << 16) | (g << 8) | b

    def mul(self, v):
        """Множитель цвета PlaceObject: нейтральный (серый/белый/чёрный) — как есть, цветной — как цвет."""
        return v if chroma(((v >> 16) & 255, (v >> 8) & 255, v & 255)) < 0.02 else self.argb(v)

    def add(self, v):
        """Добавка цвета PlaceObject (ARGB): нулевая и серая — как есть, цветная — как цвет."""
        return v if chroma(((v >> 16) & 255, (v >> 8) & 255, v & 255)) < 0.02 else self.argb(v)

    def rgba(self, data):
        """RGBA8 → RGBA8 (альфа без изменений)."""
        out = bytearray(data)
        for i in range(0, len(out), 4):
            out[i:i + 3] = bytes(self.rgb(out[i:i + 3]))
        return bytes(out)


def texture_stats(rgba):
    """Средний цвет (с весом альфы), доля «цветных» текселей, максимум насыщенности."""
    acc = [0, 0, 0]
    wsum = colored = n = 0
    smax = 0.0
    for i in range(0, len(rgba), 4):
        r, g, b, a = rgba[i:i + 4]
        if a == 0:
            continue
        n += 1
        acc[0] += r * a
        acc[1] += g * a
        acc[2] += b * a
        wsum += a
        c = chroma((r, g, b))
        smax = max(smax, c)
        if c >= 0.08:
            colored += 1
    mean = tuple(round(x / wsum) for x in acc) if wsum else (0, 0, 0)
    return mean, (colored / n if n else 0.0), smax


def visible_delta(a, b):
    """Наибольшее изменение цвета текселя с учётом его альфы (в единицах 0…255 на экране)."""
    m = 0.0
    for i in range(0, min(len(a), len(b)), 4):
        al = a[i + 3]
        if al:
            d = max(abs(a[i] - b[i]), abs(a[i + 1] - b[i + 1]), abs(a[i + 2] - b[i + 2])) * al / 255.0
            if d > m:
                m = d
    return m


# ---------------------------------------------------------------- перекраска файла

def recolor_movie(mv, rc, log=print, min_delta=2.0):
    """Перекрашенный файл (bytes) и число изменённых мест. Устройство ролика не меняется:
    слова цвета правятся на месте, пересобираются только текстуры, которые заметно изменились
    (visible_delta ≥ min_delta; иначе — исходные байты, без потерь пересжатия DXT)."""
    big = ph.Bigf(mv.big.raw)
    changed = 0
    # заливки геометрии
    for idx, meshes in sorted(mv.geometry.items()):
        key = str(idx + 1)
        g, packed = mv.raw[key]
        g = bytearray(g)
        n = 0
        for mesh in meshes:
            for fl in mesh:
                rgb = ((fl.color >> 16) & 255, (fl.color >> 8) & 255, fl.color & 255)
                if fl.type == FILL_TEXTURED and chroma(rgb) < 0.02:
                    continue                          # текстура с белым (серым) множителем
                new = rc.argb(fl.color)
                if new != fl.color:
                    struct.pack_into('>I', g, fl.off + 0x10, new)
                    log(f'    Shape {idx}: цвет {fl.color:08X} → {new:08X}')
                    n += 1
        if n:
            big.put(key, pack_like(bytes(g), packed))
            changed += n
    # множители и добавки цвета в кадрах
    d, packed = mv.raw['0']
    d = bytearray(d)
    seen, n = {}, 0
    for ch, fi, po in mv.apt.place_objects():
        if not po.flags & PO_COLOR:
            continue
        m2, a2 = rc.mul(po.mul), rc.add(po.add)
        if (m2, a2) != (po.mul, po.add):
            struct.pack_into('>II', d, po.off + 0x28, m2, a2)
            k = (ch.idx, po.mul & 0xFFFFFF, po.add, m2 & 0xFFFFFF, a2)
            seen[k] = seen.get(k, 0) + 1
            n += 1
    for (ci, m, a, m2, a2), cnt in seen.items():
        log(f'    Sprite {ci}, PlaceObject ×{cnt}: множитель RGB {m:06X} → {m2:06X}, '
            f'добавка {a:08X} → {a2:08X}')
    if n:
        big.put('0', pack_like(bytes(d), packed))
        changed += n
    # текстуры
    for idx, t in sorted(mv.textures.items()):
        rgba = t.decode()
        new = rc.rgba(rgba)
        if visible_delta(rgba, new) < min_delta:
            continue
        xpr = t.encode(new)
        big.put(t.name, pack_like(xpr, mv.raw[t.name][1]))
        got = Texture(t.name, ph.Xpr2(xpr)).decode()            # что увидит игра после DXT
        log(f'    Image {idx} ({t.fetch.width}×{t.fetch.height} {ta.FMT_NAMES.get(t.fetch.fmt, t.fetch.fmt)}): '
            f'средний цвет {texture_stats(rgba)[0]} → {texture_stats(got)[0]}, '
            f'PSNR пересжатия {ta.psnr_premul(new, got):.1f} дБ')
        changed += 1
    return build_bigf(big), changed


# ---------------------------------------------------------------- превью: сцена → JSON → canvas в Chrome/Edge

def png_bytes(w, h, rgba):
    import zlib
    raw = bytearray()
    for y in range(h):
        raw.append(0)
        raw += rgba[y * w * 4:(y + 1) * w * 4]

    def chunk(t, body):
        return struct.pack('>I', len(body)) + t + body + struct.pack('>I', zlib.crc32(t + body) & 0xFFFFFFFF)
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 6, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(bytes(raw), 6)) + chunk(b'IEND', b''))


def argb_list(v):
    return [(v >> 16) & 255, (v >> 8) & 255, v & 255, (v >> 24) & 255]


def import_key(movie):
    """'game/background/NHLBlueBackgroundComponents' → 'fe/ion/game/background/nhlbluebackgroundcomponents.big'."""
    return 'fe/ion/' + movie.lower() + '.big'


def scene(files):
    """Ролики набора ({путь в cache: → FeMovie}, первый — корень) → данные для рисовалки."""
    keys = list(files)
    movies = []
    for key in keys:
        mv = files[key]
        imports = {}
        for (movie, name, ci) in mv.apt.imports:
            target = files.get(import_key(movie))
            dst = [i for n, i in target.apt.exports if n == name] if target else []
            imports[ci] = {'t': 'import', 'm': keys.index(import_key(movie)) if dst else -1,
                           'c': dst[0] if dst else -1, 'what': f'{movie}:{name}'}
        chars = []
        for ch in mv.apt.chars:
            if ch.idx in imports:
                chars.append(imports[ch.idx])
            elif ch.type == 1:
                fills = []
                for mesh in mv.geometry.get(ch.idx, []):
                    for fl in mesh:
                        fills.append({'k': fl.type, 'c': argb_list(fl.color), 'img': fl.image,
                                      'tm': [round(x, 6) for x in fl.texmat], 'w': fl.width,
                                      'v': [round(c, 3) for p in fl.verts for c in p]})
                chars.append({'t': 'shape', 'fills': fills})
            elif ch.type in (5, 9):
                frames = []
                for fr in ch.frames:
                    items = []
                    for it in fr:
                        if it.po:
                            po = it.po
                            items.append({'f': po.flags, 'd': po.depth, 'c': po.char,
                                          'm': [round(x, 6) for x in po.matrix],
                                          'mul': argb_list(po.mul), 'add': argb_list(po.add),
                                          'clip': po.clip, 'n': po.name})
                        elif it.type == 4:
                            items.append({'r': it.depth})
                    frames.append(items)
                chars.append({'t': 'sprite', 'frames': frames})
            else:
                chars.append(None)
        tex = {}
        for idx, t in mv.textures.items():
            uri = base64.b64encode(png_bytes(t.fetch.width, t.fetch.height, t.decode())).decode('ascii')
            tex[str(idx)] = 'data:image/png;base64,' + uri
        movies.append({'key': key, 'chars': chars, 'tex': tex})
    return {'movies': movies}


# Дрейф полос: в игре их двигает скрипт (_AnimateAmbient, случайные точки), здесь — плавные синусы
# той же амплитуды порядка; маски (mcMask*) и «стёкла» (mcGlass*) двигаются вместе — как в игре
# (_CopyMovieClipProperties), потому что у их частей одинаковые имена.
DRIFT = {'mcPartA': [60, 24, 0.031, 0.043, 0.0], 'mcPartB': [70, 20, 0.027, 0.037, 1.7],
         'mcMaskPartA': [55, 26, 0.029, 0.023, 3.1], 'mcMaskPartB': [65, 18, 0.025, 0.033, 4.4]}

PREVIEW_JS = r'''
'use strict';
const D = /*DATA*/;
const FPS = D.fps;
function mmul(A, B) {
  return [A[0]*B[0] + A[2]*B[1], A[1]*B[0] + A[3]*B[1], A[0]*B[2] + A[2]*B[3], A[1]*B[2] + A[3]*B[3],
          A[0]*B[4] + A[2]*B[5] + A[4], A[1]*B[4] + A[3]*B[5] + A[5]];
}
function minv(m) {
  const [a, b, c, d, e, f] = m, det = a*d - b*c || 1e-12;
  return [d/det, -b/det, -c/det, a/det, (c*f - d*e)/det, (b*e - a*f)/det];
}
const CX0 = {mul: [1, 1, 1, 1], add: [0, 0, 0, 0]};
function cxmul(P, mul, add) {          // P ∘ C: сначала свой (C), потом родителя (P)
  const m = mul.map(x => x / 255);
  return {mul: m.map((x, i) => x * P.mul[i]), add: add.map((x, i) => x * P.mul[i] + P.add[i])};
}
const clamp = (x, lo, hi) => Math.min(hi, Math.max(lo, x));
function colorStr(c, cx) {
  const r = clamp(c[0]*cx.mul[0] + cx.add[0], 0, 255), g = clamp(c[1]*cx.mul[1] + cx.add[1], 0, 255),
        b = clamp(c[2]*cx.mul[2] + cx.add[2], 0, 255), a = clamp(c[3]*cx.mul[3] + cx.add[3], 0, 255);
  return `rgba(${r|0},${g|0},${b|0},${(a/255).toFixed(4)})`;
}
// ---- шкала времени спрайта: список (глубина → состояние) на каждый кадр
function timeline(v, mi, ci) {
  const key = mi + ':' + ci;
  if (v.tl[key]) return v.tl[key];
  const ch = v.movies[mi].chars[ci], out = [];
  let cur = new Map();
  ch.frames.forEach((fr, fi) => {
    cur = new Map(cur);
    for (const it of fr) {
      if (it.r !== undefined) { cur.delete(it.r); continue; }
      const prev = cur.get(it.d);
      let st;
      if ((it.f & 1) && prev) { st = Object.assign({}, prev); if (it.f & 2) { st.c = it.c; } }
      else st = {c: it.c, m: [1, 0, 0, 1, 0, 0], mul: [255, 255, 255, 255], add: [0, 0, 0, 0], clip: 0, n: '', born: fi};
      if (it.f & 4) st.m = it.m;
      if (it.f & 8) { st.mul = it.mul; st.add = it.add; }
      if (it.f & 32) st.n = it.n;
      if (it.f & 64) st.clip = it.clip;
      cur.set(it.d, st);
    }
    out.push([...cur.entries()].sort((a, b) => a[0] - b[0]));
  });
  return (v.tl[key] = out);
}
// ---- слои для масок
let W = 0, H = 0;
const pool = [];
let used = 0;
function layer() {
  if (used === pool.length) { const c = document.createElement('canvas'); c.width = W; c.height = H; pool.push(c); }
  const c = pool[used++], x = c.getContext('2d');
  x.setTransform(1, 0, 0, 1, 0, 0); x.globalAlpha = 1; x.globalCompositeOperation = 'source-over';
  x.clearRect(0, 0, W, H);
  return c;
}
// ---- текстура с цветовым преобразованием (множитель/добавка RGB), кэш
function texFor(mv, idx, cx) {
  const img = mv.img[idx];
  if (!img) return null;
  const id = cx.mul[0] === 1 && cx.mul[1] === 1 && cx.mul[2] === 1 && !cx.add[0] && !cx.add[1] && !cx.add[2];
  if (id) return img;
  const key = idx + ':' + cx.mul.slice(0, 3).map(x => x.toFixed(3)).join(',') + ':' + cx.add.slice(0, 3).map(x => x.toFixed(1)).join(',');
  mv.cache = mv.cache || {};
  if (mv.cache[key]) return mv.cache[key];
  const c = document.createElement('canvas'); c.width = img.width; c.height = img.height;
  const x = c.getContext('2d'); x.drawImage(img, 0, 0);
  const d = x.getImageData(0, 0, c.width, c.height), p = d.data;
  for (let i = 0; i < p.length; i += 4)
    for (let k = 0; k < 3; k++) p[i + k] = clamp(p[i + k] * cx.mul[k] + cx.add[k], 0, 255);
  x.putImageData(d, 0, 0);
  return (mv.cache[key] = c);
}
function drawShape(ctx, mv, ch, M, cx, mask) {
  ctx.setTransform(M[0], M[1], M[2], M[3], M[4], M[5]);
  for (const fl of ch.fills) {
    ctx.beginPath();
    const v = fl.v;
    if (fl.k === 3) {
      if (mask) continue;
      for (let i = 0; i + 3 < v.length; i += 4) { ctx.moveTo(v[i], v[i + 1]); ctx.lineTo(v[i + 2], v[i + 3]); }
      ctx.globalAlpha = 1; ctx.strokeStyle = colorStr(fl.c, cx);
      ctx.lineWidth = Math.max(fl.w || 1, 1 / Math.max(1e-6, Math.hypot(M[0], M[1])));
      ctx.stroke();
      continue;
    }
    for (let i = 0; i + 5 < v.length; i += 6) {
      ctx.moveTo(v[i], v[i + 1]); ctx.lineTo(v[i + 2], v[i + 3]); ctx.lineTo(v[i + 4], v[i + 5]); ctx.closePath();
    }
    if (mask) { ctx.globalAlpha = 1; ctx.fillStyle = '#fff'; ctx.fill(); continue; }
    if (fl.k === 0) {
      const fc = cxmul(cx, fl.c, [0, 0, 0, 0]);
      const img = texFor(mv, fl.img, fc);
      if (!img) continue;
      const pat = ctx.createPattern(img, 'repeat');
      pat.setTransform(new DOMMatrix(minv(fl.tm)));
      ctx.fillStyle = pat; ctx.globalAlpha = clamp(fc.mul[3] + fc.add[3] / 255, 0, 1);
      ctx.fill();
    } else {
      ctx.globalAlpha = 1; ctx.fillStyle = colorStr(fl.c, cx); ctx.fill();
    }
  }
}
function drawObj(ctx, v, mi, st, M, cx, age, mask) {
  if (D.hide.includes(st.n)) return;
  let ci = st.c, ch = v.movies[mi].chars[ci];
  while (ch && ch.t === 'import') { if (ch.m < 0) return; mi = ch.m; ci = ch.c; ch = v.movies[mi].chars[ci]; }
  if (!ch) return;
  let m = st.m;
  const dr = D.drift[st.n];
  if (dr && D.animate) {
    const t = age / FPS;
    m = m.slice(); m[4] += dr[0] * Math.sin(2 * Math.PI * dr[2] * t + dr[4]); m[5] += dr[1] * Math.sin(2 * Math.PI * dr[3] * t + 1.3 * dr[4]);
  }
  const M2 = mmul(M, m), cx2 = mask ? cx : cxmul(cx, st.mul, st.add);
  if (ch.t === 'shape') drawShape(ctx, v.movies[mi], ch, M2, cx2, mask);
  else if (ch.t === 'sprite') {
    const tl = timeline(v, mi, ci);
    if (!tl.length) return;
    const f = D.animate ? Math.floor(age) % tl.length : 0;
    drawList(ctx, v, mi, tl[f], f, M2, cx2, age, mask);
  }
}
function drawList(ctx, v, mi, list, f, M, cx, age, mask) {
  for (let i = 0; i < list.length; i++) {
    const [d, st] = list[i];
    const childAge = st.born === 0 ? age : Math.max(0, f - st.born);
    if (st.clip && !mask) {
      let j = i + 1;
      const inner = [];
      while (j < list.length && list[j][0] <= st.clip) inner.push(list[j++]);
      const lc = layer(), mc = layer();
      drawList(lc.getContext('2d'), v, mi, inner, f, M, cx, age, false);
      drawObj(mc.getContext('2d'), v, mi, st, M, cx, childAge, true);
      const lx = lc.getContext('2d');
      lx.setTransform(1, 0, 0, 1, 0, 0); lx.globalAlpha = 1; lx.globalCompositeOperation = 'destination-in';
      lx.drawImage(mc, 0, 0); lx.globalCompositeOperation = 'source-over';
      ctx.save(); ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.globalAlpha = 1; ctx.drawImage(lc, 0, 0); ctx.restore();
      used -= 2;
      i = j - 1;
    } else if (!st.clip) drawObj(ctx, v, mi, st, M, cx, childAge, mask);
  }
}
function render(ctx, v, t) {
  used = 0;
  ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.globalAlpha = 1; ctx.globalCompositeOperation = 'source-over';
  ctx.fillStyle = '#000'; ctx.fillRect(0, 0, W, H);
  const s = W / D.stage[0];
  const root = {c: v.root.c, m: [s, 0, 0, s, D.origin[0] * s, D.origin[1] * s], mul: [255, 255, 255, 255], add: [0, 0, 0, 0], clip: 0, n: '', born: 0};
  drawObj(ctx, v, v.root.m, root, [1, 0, 0, 1, 0, 0], CX0, t * FPS, false);
}
async function load(vs) {
  for (const vi of vs) {
    const v = D.variants[vi];
    v.tl = {};
    for (const mv of v.movies) {
      mv.img = {};
      for (const [k, uri] of Object.entries(mv.tex)) {
        // ждём load, а не decode(): загрузку headless-браузер учитывает в «виртуальном» времени,
        // фоновый разбор картинки — нет (снимок мог уйти раньше рисования)
        const im = new Image();
        await new Promise((ok, fail) => { im.onload = ok; im.onerror = () => fail(new Error('текстура ' + k)); im.src = uri; });
        mv.img[k] = im;
      }
    }
  }
}
async function main() {
  const q = new URLSearchParams(location.hash.slice(1));
  const vs = q.has('v') ? q.get('v').split(',').map(Number) : D.variants.map((_, i) => i);
  await load(vs);
  if (q.has('grid')) {                     // сетка: строки — варианты, столбцы — моменты (для PNG)
    const times = q.get('grid').split(',').map(Number);
    const cw = +(q.get('w') || 640), chh = Math.round(cw * D.stage[1] / D.stage[0]), lab = +(q.get('label') || 22);
    W = cw; H = chh;
    const out = document.getElementById('c');
    out.width = cw * times.length; out.height = (chh + lab) * vs.length;
    out.style.width = out.width + 'px'; out.style.height = out.height + 'px';
    const ox = out.getContext('2d');
    ox.fillStyle = '#111'; ox.fillRect(0, 0, out.width, out.height);
    const cell = document.createElement('canvas'); cell.width = cw; cell.height = chh;
    const cx = cell.getContext('2d');
    vs.forEach((vi, r) => times.forEach((t, k) => {
      render(cx, D.variants[vi], t);
      ox.drawImage(cell, k * cw, r * (chh + lab) + lab);
      if (lab) {
        ox.fillStyle = '#ddd'; ox.font = `${Math.round(lab * 0.7)}px sans-serif`; ox.textBaseline = 'middle';
        ox.fillText(`${D.variants[vi].label} · ${t.toFixed(1)} с`, k * cw + 8, r * (chh + lab) + lab / 2);
      }
    }));
    document.title = 'done';
    return;
  }
  // живой просмотр: все варианты рядом, общий таймер
  const box = document.getElementById('live');
  box.style.display = 'block';
  document.getElementById('c').style.display = 'none';
  W = 640; H = 360;
  const cvs = D.variants.map(v => {
    const fig = document.createElement('figure'), c = document.createElement('canvas'), cap = document.createElement('figcaption');
    c.width = W; c.height = H; cap.textContent = v.label; fig.append(c, cap); box.querySelector('.grid').append(fig);
    return c.getContext('2d');
  });
  const slider = document.getElementById('t'), play = document.getElementById('play'), info = document.getElementById('time');
  let playing = true, t0 = performance.now(), base = 0;
  play.onclick = () => { playing = !playing; play.textContent = playing ? 'Пауза' : 'Пуск'; base = +slider.value; t0 = performance.now(); };
  slider.oninput = () => { base = +slider.value; t0 = performance.now(); };
  function tick(now) {
    const t = playing ? base + (now - t0) / 1000 : +slider.value;
    if (playing) slider.value = (t % +slider.max).toFixed(2);
    info.textContent = t.toFixed(1) + ' с';
    D.variants.forEach((v, i) => render(cvs[i], v, t));
    requestAnimationFrame(tick);
  }
  requestAnimationFrame(tick);
}
function showError(msg) {                 // ошибка — прямо на странице (видно и на снимке)
  document.title = 'ERROR';
  const c = document.getElementById('c');
  c.style.display = 'block'; c.width = 1200; c.height = 240;
  const x = c.getContext('2d');
  x.fillStyle = '#300'; x.fillRect(0, 0, c.width, c.height); x.fillStyle = '#fff'; x.font = '16px monospace';
  String(msg).split('\n').slice(0, 10).forEach((l, i) => x.fillText(l, 10, 24 + 20 * i));
}
window.addEventListener('error', e => showError(e.message));
main().catch(e => showError((e && e.stack) || e));
'''

PREVIEW_HTML = '''<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><title>Фон меню NHL 13</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
:root{--bg:#141619;--fg:#d6d9de;--muted:#8b9099}
html,body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.4 system-ui,sans-serif}
#c{display:block}
#live{display:none;padding:12px 16px}
#live .grid{display:flex;flex-wrap:wrap;gap:12px}
figure{margin:0} figcaption{color:var(--muted);margin-top:4px}
canvas{max-width:100%;height:auto}
.bar{display:flex;gap:12px;align-items:center;margin:0 0 12px} input[type=range]{width:min(480px,60vw)}
button{background:#2a2e35;color:var(--fg);border:1px solid #3a3f47;border-radius:4px;padding:4px 12px;cursor:pointer}
p.note{color:var(--muted);max-width:900px}
</style></head><body>
<canvas id="c"></canvas>
<div id="live">
<div class="bar"><button id="play">Пауза</button><input id="t" type="range" min="0" max="30" step="0.01" value="0"><span id="time"></span></div>
<div class="grid"></div>
<p class="note">/*NOTE*/</p>
</div>
<script>/*JS*/</script>
</body></html>
'''


def preview_page(variants, origin, stage=(1280, 720), animate=True, hide=('mcDimmer',), note=''):
    """variants: [(подпись, {путь → FeMovie} — первый ролик корневой)] → HTML с рисовалкой."""
    data = {'fps': 60, 'stage': list(stage), 'origin': list(origin), 'animate': animate,
            'hide': list(hide), 'drift': DRIFT, 'variants': []}
    for label, files in variants:
        sc = scene(files)
        data['variants'].append({'label': label, 'movies': sc['movies'], 'root': {'m': 0, 'c': 0}})
    js = PREVIEW_JS.replace('/*DATA*/', json.dumps(data, ensure_ascii=False, separators=(',', ':')))
    return PREVIEW_HTML.replace('/*NOTE*/', note).replace('/*JS*/', js)


def screenshot(html_path, out_png, w, h, hash_=''):
    """Снимок страницы Chrome/Edge без окна (как teamart.render_html, но со своим адресом и #параметрами)."""
    import shutil, subprocess, tempfile
    prof = tempfile.mkdtemp(prefix='febg_')
    try:
        out_abs = os.path.abspath(out_png)
        os.makedirs(os.path.dirname(out_abs), exist_ok=True)
        url = 'file:///' + os.path.abspath(html_path).replace('\\', '/') + ('#' + hash_ if hash_ else '')
        cmd = [ta.browser(), '--headless=new', '--disable-gpu', '--hide-scrollbars', '--no-first-run',
               '--no-default-browser-check', '--force-device-scale-factor=1', f'--user-data-dir={prof}',
               f'--window-size={w},{h}', '--virtual-time-budget=20000', f'--screenshot={out_abs}', url]
        if os.path.exists(out_abs):
            os.remove(out_abs)
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=300, check=False)
        if not os.path.exists(out_abs):
            raise SystemExit(f'браузер не сохранил {out_abs}')
    finally:
        shutil.rmtree(prof, ignore_errors=True)


def png_read_rgb(path):
    """PNG 8 бит RGB/RGBA без чересстрочности (снимки Chrome) → (w, h, RGBA8)."""
    import zlib
    d = open(path, 'rb').read()
    p, idat = 8, bytearray()
    while p < len(d):
        ln = struct.unpack_from('>I', d, p)[0]
        t, body = d[p + 4:p + 8], d[p + 8:p + 8 + ln]
        p += 12 + ln
        if t == b'IHDR':
            w, h, bd, ct, _, _, il = struct.unpack('>IIBBBBB', body)
        elif t == b'IDAT':
            idat += body
    if bd != 8 or ct not in (2, 6) or il:
        return ph.png_read(path)
    bpp = 3 if ct == 2 else 4
    raw, stride = zlib.decompress(bytes(idat)), w * bpp
    out, prev, q = bytearray(w * h * 4), bytearray(stride), 0
    for y in range(h):
        f, line = raw[q], bytearray(raw[q + 1:q + 1 + stride])
        q += 1 + stride
        if f == 1:
            for i in range(bpp, stride):
                line[i] = (line[i] + line[i - bpp]) & 255
        elif f == 2:
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 255
        elif f == 3:
            for i in range(stride):
                line[i] = (line[i] + (((line[i - bpp] if i >= bpp else 0) + prev[i]) >> 1)) & 255
        elif f == 4:
            for i in range(stride):
                a = line[i - bpp] if i >= bpp else 0
                b, c = prev[i], (prev[i - bpp] if i >= bpp else 0)
                pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
                line[i] = (line[i] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        prev = line
        row = out[y * w * 4:(y + 1) * w * 4]
        if ct == 6:
            row[:] = line
        else:
            row[0::4], row[1::4], row[2::4], row[3::4] = line[0::3], line[1::3], line[2::3], b'\xff' * w
        out[y * w * 4:(y + 1) * w * 4] = row
    return w, h, bytes(out)


def crop_png(src, dst, x, y, w, h):
    sw, sh, rgba = png_read_rgb(src)
    out = bytearray()
    for yy in range(y, y + h):
        out += rgba[(yy * sw + x) * 4:(yy * sw + x + w) * 4]
    ph.png_write(dst, w, h, bytes(out))


# ---------------------------------------------------------------- наборы файлов

# путь в cache: → архив, из которого распакован оригинал (game/extracted/big/<архив>/…)
SETS = {
    # синий фон почти всех меню: класс NHLBlueBackground (подложка mcColor) + его арт и анимация
    'blue': {'files': [('fe/ion/game/background/nhlbluebackground.big', 'boot'),
                       ('fe/ion/game/background/nhlbluebackgroundcomponents.big', 'cache')],
             'origin': (640, 360)},
    # главное меню: своя сцена (стена арены, синие огни, лёд); отражение синего фона — импорт из «blue»
    'mainmenu': {'files': [('fe/ion/game/background/nhlmainmenubackground.big', 'cache'),
                           ('fe/ion/game/background/nhlbackgroundcompressedcomponents.big', 'cache'),
                           ('fe/ion/game/background/nhlbluebackgroundcomponents.big', 'cache')],
                 'origin': (0, 0), 'recolor': 2},   # перекрашиваются первые два (третий — из «blue»)
}


def source_path(rel, archive, game=None, profile=None):
    """Оригинал файла: NHL 13 — game/extracted/big/<архив>/…; другая игра (профиль) — её распакованные архивы,
    первый, где файл есть (у Legacy фон NHLBlueBackgroundComponents — в cacheboot.big, а не в cache.big)."""
    P = profile or GAME
    if P.name == 'nhl13':
        return os.path.join(game or ph.game_dir(), 'extracted', 'big', archive, *rel.split('/'))
    return P.extracted(rel) or P.archive_path(archive, rel)


def load_set(name, src=None, game=None):
    """{путь → FeMovie}: файлы из src (папка или папки через запятую в раскладке cache:, по порядку),
    чего там нет — оригиналы из game/extracted/big (у --game legacy — из архивов Legacy); элемент «@игра»
    в src — оригиналы этой игры (@nhl13, @legacy)."""
    dirs = [d for d in (src or '').split(',') if d]
    base = next((gameprofile.get(d[1:]) for d in dirs if d.startswith('@')), None)
    dirs = [d for d in dirs if not d.startswith('@')]
    files = {}
    for rel, archive in SETS[name]['files']:
        p = next((q for q in (os.path.join(d, *rel.split('/')) for d in dirs) if os.path.exists(q)), None)
        files[rel] = FeMovie.load(p or source_path(rel, archive, game, base))
    return files


def make_recolor(args):
    """--gray [уровень] | --color RRGGBB (во что превращается основной синий #0040BA)."""
    if '--color' in args:
        return Recolor(hexcolor(args[args.index('--color') + 1]))
    lvl = None
    if '--gray' in args:
        i = args.index('--gray')
        if i + 1 < len(args) and args[i + 1].isdigit():
            lvl = min(255, int(args[i + 1]))
    if lvl is None:
        lvl = round(hls(BASE_BLUE)[1] * 255)          # серый той же светлоты (HSL), #5D5D5D
    return Recolor((lvl, lvl, lvl))


def recolor_set(name, rc, outdir, log=print, game=None):
    files = load_set(name, game=game)
    keys = list(files)[:SETS[name].get('recolor', len(files))]
    written = []
    for rel in keys:
        log(f'  {rel}')
        data, n = recolor_movie(files[rel], rc, log)
        if not n:
            log('    без изменений — не пишется')
            continue
        dst = os.path.join(outdir, *rel.split('/'))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        open(dst, 'wb').write(data)
        FeMovie(data)                                  # самопроверка: файл разбирается обратно
        written.append((rel, len(data)))
        log(f'    → {dst} ({len(data)} байт, было {len(files[rel].big.raw)})')
    return written


# ---------------------------------------------------------------- команды

def cmd_info(paths):
    for p in paths:
        mv = FeMovie.load(p)
        a = mv.apt
        print(f'{p}: Apt {a.version}, сцена {a.width}×{a.height}, {a.ms} мс на кадр, символов {len(a.chars)}')
        for n, blob in mv.big.entries:
            body, packed = mv.raw.get(n, (b'', False))
            kind = ('Apt Data' if body[:8] == b'Apt Data' else 'константы' if body[:12] == b'Apt constant'
                    else 'XPR2' if body[:4] == b'XPR2' else 'метка' if not blob else 'геометрия')
            print(f'   запись {n:5s} {kind:10s} {len(blob):7d} байт' + (f' (RefPack → {len(body)})' if packed else ''))
        if a.imports:
            print('   импорт: ' + '; '.join(f'{c} ← {m}:{n}' for m, n, c in a.imports))
        if a.exports:
            print('   экспорт: ' + '; '.join(f'{n} = {c}' for n, c in a.exports))
        print('   цвета:')
        for idx, meshes in sorted(mv.geometry.items()):
            for mesh in meshes:
                for fl in mesh:
                    if fl.type != FILL_TEXTURED or fl.color != 0xFFFFFFFF:
                        kind = {FILL_TEXTURED: 'текстура ×', FILL_SOLID: 'заливка', FILL_LINE: 'линия'}.get(fl.type, fl.type)
                        print(f'     Shape {idx}: {kind} {fl.color:08X}')
        tints = {}
        for ch, fi, po in a.place_objects():
            if po.flags & PO_COLOR and (po.mul & 0xFFFFFF != 0xFFFFFF or po.add & 0xFFFFFF):
                k = (ch.idx, po.mul & 0xFFFFFF, po.add)
                tints[k] = tints.get(k, 0) + 1
        for (ci, m, ad), cnt in sorted(tints.items()):
            print(f'     Sprite {ci}: множитель RGB {m:06X}, добавка {ad:08X} (PlaceObject ×{cnt})')
        for idx, t in sorted(mv.textures.items()):
            mean, share, smax = texture_stats(t.decode())
            print(f'     Image {idx}: {t.fetch.width}×{t.fetch.height} {ta.FMT_NAMES.get(t.fetch.fmt, t.fetch.fmt)}, '
                  f'средний цвет {mean}, цветных текселей {share:.0%}, макс. насыщенность {smax:.2f}')


def cmd_dump(path, maxframes=3):
    mv = FeMovie.load(path)
    a = mv.apt
    print(f'{path}: Apt {a.version}, Movie @{a.movie_off:#x}, сцена {a.width}×{a.height}, {a.ms} мс/кадр')
    for ch in a.chars:
        extra = ''
        if ch.type == 1:
            extra = f' растр={ch.image} рамка={tuple(round(x, 2) for x in ch.bounds)} геометрия={ch.geometry}'
        elif ch.type == 7:
            t = mv.textures.get(ch.idx)
            extra = ' ' + (t.fetch.describe() if t else 'нет текстуры')
        elif ch.type in (5, 9):
            extra = f' кадров={len(ch.frames)}'
        print(f'{ch.idx:4d} {ch.name}{extra}')
        for mesh in mv.geometry.get(ch.idx, []):
            for fl in mesh:
                print(f'       заливка тип {fl.type} цвет {fl.color:08X} растр {fl.image} n={fl.count} '
                      f'матрица {tuple(round(x, 5) for x in fl.texmat)}')
        for fi, fr in enumerate(ch.frames[:maxframes]):
            for it in fr:
                print(f'       к{fi}: {it.describe()}')
        if len(ch.frames) > maxframes:
            print(f'       … ещё {len(ch.frames) - maxframes} кадров')


def cmd_textures(path, outdir):
    mv = FeMovie.load(path)
    os.makedirs(outdir, exist_ok=True)
    for idx, t in sorted(mv.textures.items()):
        p = os.path.join(outdir, f'{idx}.png')
        ph.png_write(p, t.fetch.width, t.fetch.height, t.decode())
        print(p, t.fetch.describe())


def diff_ranges(a, b):
    """Отличающиеся байты: список смещений (a и b одной длины)."""
    return [i for i in range(len(a)) if a[i] != b[i]]


def verify_file(orig, new):
    """Что изменилось в собранном файле относительно оригинала. Разрешено: слова цвета
    PlaceObject (+0x28…+0x2F) в Apt Data, слова цвета заливок (+0x10…+0x13) в геометрии,
    данные текстур (заголовок XPR2 — тот же). Возвращает (ok, строки отчёта)."""
    rep, ok = [], True
    if [n for n, _ in orig.big.entries] != [n for n, _ in new.big.entries] or orig.big.tag != new.big.tag:
        return False, ['записи BIGF или метка не совпадают']
    if orig.big.trailer != new.big.trailer:
        rep.append('хвост BIGF другой')
    allowed_apt = set()
    for ch, fi, po in orig.apt.place_objects():
        allowed_apt.update(range(po.off + 0x28, po.off + 0x30))
    for n, _ in orig.big.entries:
        a, b = orig.raw.get(n, (b'', False))[0], new.raw.get(n, (b'', False))[0]
        if a == b:
            continue
        if len(a) != len(b):
            ok = False
            rep.append(f'запись {n}: длина {len(a)} → {len(b)}')
            continue
        offs = diff_ranges(a, b)
        if n == '0':
            bad = [o for o in offs if o not in allowed_apt]
            rep.append(f'Apt Data: {len(offs)} байт в словах цвета PlaceObject' + (f', ЧУЖИХ {len(bad)}' if bad else ''))
            ok &= not bad
        elif a[:4] == b'XPR2':
            hdr = [o for o in offs if o < 12 + ph.Xpr2(a).hsize]
            rep.append(f'текстура {n}: данные {len(offs)} байт' + (', ЗАГОЛОВОК ИЗМЕНЁН' if hdr else ''))
            ok &= not hdr
        else:
            idx = int(n) - 1
            allowed = set()
            for mesh in orig.geometry.get(idx, []):
                for fl in mesh:
                    allowed.update(range(fl.off + 0x10, fl.off + 0x14))
            bad = [o for o in offs if o not in allowed]
            rep.append(f'геометрия {n}: {len(offs)} байт в цвете заливок' + (f', ЧУЖИХ {len(bad)}' if bad else ''))
            ok &= not bad
    return ok, rep


def cmd_verify(args):
    outdir, bad, seen = args[0], 0, set()
    for name, s in SETS.items():
        for rel, archive in s['files']:
            p = os.path.join(outdir, *rel.split('/'))
            if rel in seen or not os.path.exists(p):
                continue
            seen.add(rel)
            ok, rep = verify_file(FeMovie.load(source_path(rel, archive)), FeMovie.load(p))
            print(f'{"OK " if ok else "BAD"} {rel}: ' + '; '.join(rep))
            bad += not ok
    sys.exit(1 if bad else 0)


def opt(args, name, default=None):
    return args[args.index(name) + 1] if name in args else default


def cmd_recolor(args):
    outdir = args[0]
    rc = make_recolor(args)
    sets = opt(args, '--sets', 'blue').split(',')
    print(f'перекраска {rc.describe()}')
    for s in sets:
        print(f'набор {s}:')
        recolor_set(s, rc, outdir)


def cmd_preview(args):
    """Кадры до/после: OUTDIR/<name>.png (сетка: строки — варианты, столбцы — моменты),
    frames/<name>/*.png (каждый кадр отдельно), <name>.html (живая анимация всех вариантов)."""
    outdir = args[0]
    sets = opt(args, '--set', 'blue')
    name = opt(args, '--name', 'compare')
    times = [float(x) for x in opt(args, '--times', '0,2.5,5,7.5').split(',')]
    cw = int(opt(args, '--width', '640'))
    variants = [('оригинал' if GAME.name == 'nhl13' else f'оригинал ({GAME.title})', load_set(sets))]
    if '--src' in args:
        variants.append((opt(args, '--label', 'перекраска'), load_set(sets, opt(args, '--src'))))
    for extra in (opt(args, '--also', '') or '').split(';'):
        if extra:
            label, path = extra.split('=', 1)
            variants.append((label, load_set(sets, path)))
    os.makedirs(outdir, exist_ok=True)
    note = ('Варианты фона рядом, общий таймер. Дрейф полос в игре задаёт скрипт (случайные точки) — '
            'здесь он заменён плавными синусами; логотипы команд (их подгружает код) и затемнение '
            '(mcDimmer) не показаны.')
    page = os.path.join(outdir, name + '.html')
    open(page, 'w', encoding='utf-8').write(preview_page(variants, SETS[sets]['origin'], note=note))
    ch, lab = round(cw * 720 / 1280), 22
    grid = os.path.join(outdir, name + '.png')
    # по снимку на вариант (строку): с десятками текстур на странице headless-браузер не всегда
    # успевает разобрать все картинки за отведённое «виртуальное» время, по одному варианту — успевает
    rows = []
    for r in range(len(variants)):
        part = os.path.join(outdir, f'.{name}_{r}.png')
        for attempt in range(4):                       # пустой снимок (не успел нарисовать) — ещё раз
            screenshot(page, part, cw * len(times), ch + lab,
                       f'grid={",".join(str(t) for t in times)}&w={cw}&label={lab}&v={r}')
            shot = png_read_rgb(part)
            body = shot[2][(lab + 1) * shot[0] * 4:]
            if len({body[i:i + 3] for i in range(0, len(body), 4 * 101)}) > 4:
                break
            print(f'  снимок «{variants[r][0]}» пустой, повтор {attempt + 1}')
        rows.append(shot)
        os.remove(part)
    ph.png_write(grid, cw * len(times), (ch + lab) * len(variants), b''.join(rgba for _, _, rgba in rows))
    print(f'{grid}: {len(variants)}×{len(times)} кадров по {cw}×{ch}')
    if '--no-frames' in args:
        return
    fdir = os.path.join(outdir, 'frames', name)
    os.makedirs(fdir, exist_ok=True)
    import re
    for r, (label, _) in enumerate(variants):
        safe = re.sub(r'[^\w-]+', '_', label).strip('_')
        for k, t in enumerate(times):
            crop_png(grid, os.path.join(fdir, f'{r}_{safe}_{t:04.1f}s.png'), k * cw, r * (ch + lab) + lab, cw, ch)
    print(f'{fdir}: {len(variants) * len(times)} PNG; живой просмотр — {page}')


def main():
    global GAME
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    ap = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    gameprofile.add_argument(ap)                          # --game nhl13|legacy (или NHL_GAME) — где угодно в строке
    g, rest = ap.parse_known_args(sys.argv[1:])
    GAME = gameprofile.get(g.game)
    if len(rest) < 2:
        sys.exit(__doc__)
    cmd, args = rest[0], rest[1:]
    if cmd == 'info':
        cmd_info(args)
    elif cmd == 'dump':
        cmd_dump(args[0], int(opt(args, '--frames', '3')))
    elif cmd == 'textures':
        cmd_textures(args[0], args[1])
    elif cmd == 'recolor':
        cmd_recolor(args)
    elif cmd == 'preview':
        cmd_preview(args)
    elif cmd == 'verify':
        cmd_verify(args)
    else:
        sys.exit(__doc__)


if __name__ == '__main__':
    main()
