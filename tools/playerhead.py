"""Фото игроков NHL 13 (Xbox 360): p<artid>.big ⇄ PNG, сборка новых фото.

    python playerhead.py info FILE.big…                  # контейнер, стадия Apt, текстура
    python playerhead.py decode FILE.big OUT.png [--full] [--dds OUT.dds]
                                                         # стадия (467×253 / 202×128) или вся текстура
    python playerhead.py encode IN.png|IN.dds TEMPLATE.big OUT.big [--trailer keep|md5]
    python playerhead.py roundtrip FILE.big… [--deep]    # разбор → сборка: проверка байт-в-байт
    python playerhead.py compose MUG.png ARTID OUTDIR [--kind big,small] [--preview DIR] [--auto]
        # портрет NHL (336×336) → OUTDIR/fe/ion/artassets/playerheads[small]/<папка>/p<artid>.big
        # (дерево как в cache:); шаблон — оригинал с тем же номером, если есть, иначе p1

Устройство файла (оба размера и силуэты одинаковы, разница — числа):
  * Контейнер — EA BIGF: "BIGF", u32 LE размер без хвоста, u32 BE число записей,
    u32 BE конец заголовка; записи — u32 BE смещение, u32 BE размер, имя ASCIIZ; за ними
    метка "L286"/"L287" + 15 05 00 01. Данные записей — с адресов, кратных 0x40, нули между
    ними (у L287 пустые метки sg1/sg2 занимают своё место 0x40). После данных — 16 байт
    хвоста (не входят в размер; хеш или идентификатор, назначение неизвестно).
  * Записи — ролик Apt (Flash EA): "0" — Apt Data (сцена, кадр, символы), "<N+1>" — геометрия
    (два треугольника на всю сцену с заливкой текстурой 1:1), "sg1" (пустая), "<N>" — текстура,
    "sg2" (пустая), "1" — Apt constant file. Номера символов разные (2/3, 8/9, 1154/1155…),
    любая запись может быть сжата RefPack (10 FB); текстура сжата всегда.
  * Текстура — XPR2 с одним ресурсом TX2D: заголовок 0x60 байт (D3DTexture + константа
    выборки GPU), далее данные: DXT5 (k_DXT4_5), тайлинг Xenos, порядок байт 8in16, без
    мипов. Большие: 512×256 (стадия 467×253) или 512×512 (467×260); малые: 256×128
    (202×128); карты HUT: 256×256 (162×232). Альфа — прямая (не premultiplied), под
    прозрачным — чёрный цвет.

Номер: файл p<artid>.big, поле exhibitionplayerbiotable.artid. Игра показывает его, если
hasportrait = 1, иначе силуэт p6000<artid % 4>. Папка (getArtAssetPath в
pods/helpers/generalhelpers): artid ≤ 4000 → p0_4000, ≤ 8000 → p4001_8000,
≤ 12000 → p8001_12000, больше → silhouettes. Подробности — docs/player-photos.md.

Только стандартная библиотека. Каталог игры — переменная NHL13_GAME или game/ рядом с tools/.
"""
import hashlib, math, os, struct, sys, zlib

# ---------------------------------------------------------------- пути

def game_dir():
    env = os.environ.get('NHL13_GAME')
    if env:
        return env
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    git = os.path.join(here, '.git')
    if os.path.isfile(git):                       # рабочая копия git (.claude/worktrees/…)
        line = open(git, encoding='utf-8').read().strip()
        if line.startswith('gitdir:'):
            main = os.path.abspath(os.path.join(line[7:].strip(), '..', '..', '..'))
            if os.path.isdir(os.path.join(main, 'game')):
                return os.path.join(main, 'game')
    return os.path.join(here, 'game')


KINDS = {   # вид: папка в fe/ion/artassets, архив диска, где лежит распакованное
    'big': ('playerheads', 'nocacherender.big', ('extracted', 'big', 'nocacherender')),
    'small': ('playerheadssmall', 'cache.big', ('extracted', 'big', 'cache')),
}
MAX_ORIGINAL = {'big': 34672, 'small': 10992}   # самые большие файлы игры — больше не делать без проверки


def folder_for(artid):
    """Папка внутри playerheads(small) — как getArtAssetPath в generalhelpers.big."""
    if artid <= 4000:
        return 'p0_4000'
    if artid <= 8000:
        return 'p4001_8000'
    if artid <= 12000:
        return 'p8001_12000'
    return 'silhouettes'


def asset_relpath(kind, artid):
    return '/'.join(('fe', 'ion', 'artassets', KINDS[kind][0], folder_for(artid), f'p{artid}.big'))


def original_path(kind, artid, game=None):
    root = os.path.join(game or game_dir(), *KINDS[kind][2])
    return os.path.join(root, *asset_relpath(kind, artid).split('/'))


def default_template(kind, game=None):
    return original_path(kind, 1, game)          # p1: 512×256 / 256×128, символы 2 и 3


# ---------------------------------------------------------------- RefPack

def refpack_decompress(src):
    if len(src) < 5 or src[1] != 0xFB:
        raise ValueError('не RefPack')
    flags = src[0]
    n = 4 if flags & 0x80 else 3
    p = 2 + (n if flags & 0x01 else 0)
    size = int.from_bytes(src[p:p + n], 'big')
    p += n
    out = bytearray()
    while p < len(src):
        b0 = src[p]
        if b0 < 0x80:
            b1 = src[p + 1]; p += 2
            lit, ln, off = b0 & 3, ((b0 >> 2) & 7) + 3, ((b0 & 0x60) << 3) + b1 + 1
        elif b0 < 0xC0:
            b1, b2 = src[p + 1], src[p + 2]; p += 3
            lit, ln, off = b1 >> 6, (b0 & 0x3F) + 4, ((b1 & 0x3F) << 8) + b2 + 1
        elif b0 < 0xE0:
            b1, b2, b3 = src[p + 1], src[p + 2], src[p + 3]; p += 4
            lit, ln, off = b0 & 3, ((b0 & 0x0C) << 6) + b3 + 5, ((b0 & 0x10) << 12) + (b1 << 8) + b2 + 1
        elif b0 < 0xFC:
            lit = ((b0 & 0x1F) + 1) << 2
            out += src[p + 1:p + 1 + lit]
            p += 1 + lit
            continue
        else:
            lit = b0 & 3
            out += src[p + 1:p + 1 + lit]
            p += 1 + lit
            break
        out += src[p:p + lit]
        p += lit
        start = len(out) - off
        if start < 0:
            raise ValueError('RefPack: ссылка до начала данных')
        if off >= ln:
            out += out[start:start + ln]
        else:
            for i in range(ln):
                out.append(out[start + i])
    if len(out) != size:
        raise ValueError(f'RefPack: {len(out)} байт вместо {size}')
    return bytes(out)


def _match_len(d, a, b, limit):
    n = 0
    while n + 16 <= limit and d[a + n:a + n + 16] == d[b + n:b + n + 16]:
        n += 16
    while n < limit and d[a + n] == d[b + n]:
        n += 1
    return n


def refpack_compress(data, depth=48):
    """Жадный LZ77 с цепочками по 3 байта; формат как у EA (10 FB + 3 байта размера)."""
    n = len(data)
    if n >= 1 << 24:
        raise ValueError('RefPack: больше 16 МБ')
    out = bytearray(b'\x10\xfb' + n.to_bytes(3, 'big'))
    chains = {}
    lit_start = p = 0

    def flush_literals(upto, keep):
        nonlocal lit_start
        while upto - lit_start > keep:
            k = min(112, (upto - lit_start) & ~3)
            if k < 4:
                break
            out.append(0xE0 + (k >> 2) - 1)
            out.extend(data[lit_start:lit_start + k])
            lit_start += k

    def insert(i):
        if i + 3 <= n:
            chains.setdefault(data[i:i + 3], []).append(i)

    while p < n:
        best_len = best_off = best_gain = 0
        if p + 3 <= n:
            cand = chains.get(data[p:p + 3])
            if cand:
                limit = min(1028, n - p)
                for i in reversed(cand[-depth:]):
                    off = p - i
                    if off > 131072:
                        break
                    full = _match_len(data, i, p, limit)
                    # формы команды: 2 байта (3–10, ≤1 КБ), 3 байта (4–67, ≤16 КБ), 4 байта (5–1028, ≤128 КБ)
                    for ln, cost, ok in ((min(full, 10), 2, off <= 1024 and full >= 3),
                                         (min(full, 67), 3, off <= 16384 and full >= 4),
                                         (full, 4, full >= 5)):
                        if ok and ln - cost > best_gain:
                            best_gain, best_len, best_off = ln - cost, ln, off
                    if full == limit:
                        break
        if best_gain <= 0:
            insert(p)
            p += 1
            continue
        flush_literals(p, 3)
        lit = p - lit_start
        ln, off = best_len, best_off
        if 3 <= ln <= 10 and off <= 1024:
            o = off - 1
            out += bytes((((o >> 3) & 0x60) | ((ln - 3) << 2) | lit, o & 0xFF))
        elif 4 <= ln <= 67 and off <= 16384:
            o = off - 1
            out += bytes((0x80 | (ln - 4), (lit << 6) | (o >> 8), o & 0xFF))
        else:
            o, l = off - 1, ln - 5
            out += bytes((0xC0 | ((o >> 12) & 0x10) | ((l >> 6) & 0x0C) | lit, (o >> 8) & 0xFF, o & 0xFF, l & 0xFF))
        out += data[lit_start:p]
        for i in range(p, p + ln):
            insert(i)
        p += ln
        lit_start = p
    flush_literals(n, 3)
    rest = n - lit_start
    out.append(0xFC | rest)
    out += data[lit_start:n]
    return bytes(out)


def unpack_entry(blob):
    """Запись BIGF → (данные, была ли сжата RefPack)."""
    if len(blob) >= 5 and blob[1] == 0xFB and blob[0] in (0x10, 0x11, 0x90, 0x91):
        return refpack_decompress(blob), True
    return blob, False


# ---------------------------------------------------------------- BIGF

def align(v, a):
    return (v + a - 1) // a * a


class Bigf:
    ALIGN = 0x40

    def __init__(self, data):
        if data[:4] != b'BIGF':
            raise ValueError('не BIGF')
        self.total = struct.unpack_from('<I', data, 4)[0]
        count, self.hsize = struct.unpack_from('>II', data, 8)
        p, self.entries, self.offsets = 16, [], []
        for _ in range(count):
            off, size = struct.unpack_from('>II', data, p)
            e = data.index(b'\0', p + 8)
            name = data[p + 8:e].decode('ascii')
            self.entries.append([name, data[off:off + size]])
            self.offsets.append(off)
            p = e + 1
        self.tag = data[p:self.hsize]               # "L286" + 15 05 00 01
        self.trailer = data[self.total:]
        self.raw = data

    def get(self, name):
        for n, b in self.entries:
            if n == name:
                return b
        raise KeyError(name)

    def put(self, name, blob):
        for e in self.entries:
            if e[0] == name:
                e[1] = blob
                return
        raise KeyError(name)

    def build(self, trailer=None):
        names = b''.join(n.encode('ascii') + b'\0' for n, _ in self.entries)
        hsize = 16 + 8 * len(self.entries) + len(names) + len(self.tag)
        pos, offs = align(hsize, self.ALIGN), []
        # у L287 и L288 (NHL Legacy: 4557 файлов fe/ion/artassets — все собираются так байт в байт; в NHL 13 L288
        # нет) пустая метка занимает своё место 0x40
        l287 = self.tag[:4] in (b'L287', b'L288')
        for _, b in self.entries:
            pos = align(pos, self.ALIGN)
            offs.append(pos)
            pos += len(b) or (self.ALIGN if l287 else 0)
        total = pos
        out = bytearray(total)
        out[0:4] = b'BIGF'
        struct.pack_into('<I', out, 4, total)
        struct.pack_into('>II', out, 8, len(self.entries), hsize)
        p = 16
        for (n, b), off in zip(self.entries, offs):
            struct.pack_into('>II', out, p, off, len(b))
            p += 8
            out[p:p + len(n) + 1] = n.encode('ascii') + b'\0'
            p += len(n) + 1
        out[p:p + len(self.tag)] = self.tag
        for (_, b), off in zip(self.entries, offs):
            out[off:off + len(b)] = b
        if trailer is None:
            trailer = self.trailer
        elif trailer == 'md5':
            trailer = hashlib.md5(out).digest()
        return bytes(out) + trailer


# ---------------------------------------------------------------- XPR2 / Xenos

FMT_DXT5 = 20
FMT_NAMES = {6: 'k_8_8_8_8', 18: 'k_DXT1', 19: 'k_DXT2_3', 20: 'k_DXT4_5'}
ENDIAN_NAMES = {0: 'none', 1: '8in16', 2: '8in32', 3: '16in32'}


class Xpr2:
    def __init__(self, data):
        magic, self.hsize, self.dsize, nres = struct.unpack_from('>4sIII', data, 0)
        if magic != b'XPR2':
            raise ValueError('не XPR2')
        if nres != 1:
            raise ValueError(f'XPR2: ресурсов {nres}, ожидался 1')
        typ, roff, rsize, noff = struct.unpack_from('>4sIII', data, 16)
        if typ != b'TX2D' or rsize != 0x34:
            raise ValueError(f'XPR2: ресурс {typ!r} размером {rsize}')
        self.name = data[12 + noff:data.index(b'\0', 12 + noff)].decode('latin1')
        self.d3d = struct.unpack_from('>13I', data, 12 + roff)
        self.header = data[:12 + self.hsize]
        self.data = data[12 + self.hsize:12 + self.hsize + self.dsize]
        if len(self.data) != self.dsize or len(data) != 12 + self.hsize + self.dsize:
            raise ValueError('XPR2: размер данных не сходится')
        d0, d1, d2, d3, d4, d5 = self.fetch = self.d3d[7:13]
        self.common = self.d3d[0]
        self.tiled = d0 >> 31
        self.pitch = ((d0 >> 22) & 0x1FF) * 32
        self.fmt = d1 & 0x3F
        self.endian = (d1 >> 6) & 3
        self.base_addr = d1 >> 12
        self.width = (d2 & 0x1FFF) + 1
        self.height = ((d2 >> 13) & 0x1FFF) + 1
        self.swizzle = (d3 >> 1) & 0xFFF
        self.mip_min, self.mip_max = (d4 >> 2) & 0xF, (d4 >> 6) & 0xF
        self.dimension = (d5 >> 9) & 3
        self.packed_mips = (d5 >> 11) & 1
        self.mip_addr = d5 >> 12

    def describe(self):
        sw = ''.join('RGBA01??'[(self.swizzle >> (3 * i)) & 7] for i in range(4))
        return (f'{self.width}×{self.height} {FMT_NAMES.get(self.fmt, self.fmt)} '
                f'{"тайлинг" if self.tiled else "линейно"}, порядок {ENDIAN_NAMES[self.endian]}, '
                f'pitch {self.pitch}, мипы {self.mip_min}..{self.mip_max} (packed {self.packed_mips}), '
                f'swizzle {sw}, 2D={self.dimension == 1}, данные {self.dsize} байт, '
                f'fetch {" ".join(f"{x:08X}" for x in self.fetch)}')

    def build(self, data):
        if len(data) != self.dsize:
            raise ValueError(f'данные текстуры: {len(data)} байт вместо {self.dsize}')
        return self.header + data


def tiled_offset_2d(x, y, pitch, bpb_log2):
    """Смещение блока (x, y) в тайловой текстуре Xenos (как XGAddress2DTiledOffset)."""
    pitch = (pitch + 31) & ~31
    macro = ((x >> 5) + (y >> 5) * (pitch >> 5)) << (bpb_log2 + 7)
    micro = ((x & 7) + ((y & 0xE) << 2)) << bpb_log2
    offset = macro + ((micro & ~0xF) << 1) + (micro & 0xF) + ((y & 1) << 4)
    return (((offset & ~0x1FF) << 3) + ((y & 16) << 7) + ((offset & 0x1C0) << 2)
            + (((((y & 8) >> 2) + (x >> 3)) & 3) << 6) + (offset & 0x3F))


def swap16(b):
    b = bytearray(b)
    b[0::2], b[1::2] = b[1::2], b[0::2]
    return bytes(b)


def xenos_to_linear(tex):
    """Данные XPR2 (DXT5) → линейные блоки DXT5 в порядке PC (little-endian)."""
    if tex.fmt != FMT_DXT5 or tex.dimension != 1 or tex.mip_max:
        raise ValueError('поддержан только DXT5 2D без мипов: ' + tex.describe())
    bw, bh = tex.width // 4, tex.height // 4
    pitch = max(tex.pitch // 4, bw)
    src, out = tex.data, bytearray(bw * bh * 16)
    for by in range(bh):
        for bx in range(bw):
            o = tiled_offset_2d(bx, by, pitch, 4) if tex.tiled else (by * pitch + bx) * 16
            out[(by * bw + bx) * 16:(by * bw + bx + 1) * 16] = src[o:o + 16]
    return swap16(out) if tex.endian == 1 else bytes(out)


def linear_to_xenos(tex, blocks):
    if tex.endian == 1:
        blocks = swap16(blocks)
    bw, bh = tex.width // 4, tex.height // 4
    pitch = max(tex.pitch // 4, bw)
    out = bytearray(tex.dsize)
    for by in range(bh):
        for bx in range(bw):
            o = tiled_offset_2d(bx, by, pitch, 4) if tex.tiled else (by * pitch + bx) * 16
            out[o:o + 16] = blocks[(by * bw + bx) * 16:(by * bw + bx + 1) * 16]
    return bytes(out)


# ---------------------------------------------------------------- DXT5

def _c565(c):
    r, g, b = (c >> 11) & 31, (c >> 5) & 63, c & 31
    return ((r << 3) | (r >> 2), (g << 2) | (g >> 4), (b << 3) | (b >> 2))


def _alpha_palette(a0, a1):
    if a0 > a1:
        return [a0, a1] + [((7 - i) * a0 + i * a1) // 7 for i in range(1, 7)]
    return [a0, a1] + [((5 - i) * a0 + i * a1) // 5 for i in range(1, 5)] + [0, 255]


def _color_palette(c0, c1):
    p0, p1 = _c565(c0), _c565(c1)
    return [p0, p1, tuple((2 * a + b) // 3 for a, b in zip(p0, p1)), tuple((a + 2 * b) // 3 for a, b in zip(p0, p1))]


def dxt5_decode(blocks, w, h):
    """Линейные блоки DXT5 (PC) → RGBA8 w×h. Цвет — всегда 4 оттенка (BC3)."""
    out = bytearray(w * h * 4)
    bw = w // 4
    cache = {}
    for i in range(len(blocks) // 16):
        blk = blocks[i * 16:i * 16 + 16]
        px = cache.get(blk)
        if px is None:
            al = _alpha_palette(blk[0], blk[1])
            abits = int.from_bytes(blk[2:8], 'little')
            c0, c1, cbits = struct.unpack_from('<HHI', blk, 8)
            cols = _color_palette(c0, c1)
            px = []
            for k in range(16):
                c = cols[(cbits >> (2 * k)) & 3]
                px.append(bytes((c[0], c[1], c[2], al[(abits >> (3 * k)) & 7])))
            if len(cache) < 4096:
                cache[blk] = px
        bx, by = (i % bw) * 4, (i // bw) * 4
        for k in range(16):
            o = ((by + (k >> 2)) * w + bx + (k & 3)) * 4
            out[o:o + 4] = px[k]
    return bytes(out)


def _q565(r, g, b):
    r = min(31, max(0, int(r * 31 / 255 + 0.5)))
    g = min(63, max(0, int(g * 63 / 255 + 0.5)))
    b = min(31, max(0, int(b * 31 / 255 + 0.5)))
    return (r << 11) | (g << 5) | b


def _color_indices(px, c0, c1, vis):
    """Индексы для всех 16 пикселей; ошибка — только по видимым (vis)."""
    pal = _color_palette(c0, c1)
    bits = err = 0
    for k, (r, g, b) in enumerate(px):
        best, bi = 1 << 30, 0
        for j, (pr, pg, pb) in enumerate(pal):
            e = (r - pr) ** 2 + (g - pg) ** 2 + (b - pb) ** 2
            if e < best:
                best, bi = e, j
        bits |= bi << (2 * k)
        if vis[k]:
            err += best
    return bits, err


def _encode_color(px, al):
    """Цвет блока DXT5. Концы подбираются по видимым пикселям (альфа ≥ 8): под прозрачным
    цвет не важен и не должен тянуть край к чёрному. Совсем прозрачный блок — чёрный, как у EA."""
    vis = [a >= 8 for a in al]
    pts = [p for p, v in zip(px, vis) if v]
    if not pts:
        return 0, 0, 0
    first = pts[0]
    if all(p == first for p in pts):
        c = _q565(*first)
        return c, c, 0
    # главная ось цветов блока (степенной метод по ковариации), концы — крайние проекции
    n = float(len(pts))
    mr = sum(p[0] for p in pts) / n
    mg = sum(p[1] for p in pts) / n
    mb = sum(p[2] for p in pts) / n
    crr = cgg = cbb = crg = crb = cgb = 0.0
    for r, g, b in pts:
        r -= mr; g -= mg; b -= mb
        crr += r * r; cgg += g * g; cbb += b * b; crg += r * g; crb += r * b; cgb += g * b
    if crr >= cgg and crr >= cbb:
        vr, vg, vb = crr, crg, crb
    elif cgg >= cbb:
        vr, vg, vb = crg, cgg, cgb
    else:
        vr, vg, vb = crb, cgb, cbb
    for _ in range(6):
        vr, vg, vb = (crr * vr + crg * vg + crb * vb, crg * vr + cgg * vg + cgb * vb, crb * vr + cgb * vg + cbb * vb)
        m = max(abs(vr), abs(vg), abs(vb)) or 1.0
        vr, vg, vb = vr / m, vg / m, vb / m
    proj = [p[0] * vr + p[1] * vg + p[2] * vb for p in pts]
    c0, c1 = _q565(*pts[proj.index(max(proj))]), _q565(*pts[proj.index(min(proj))])
    bits, err = _color_indices(px, c0, c1, vis)
    best = (err, c0, c1, bits)
    # уточнение концов наименьшими квадратами по выбранным индексам (как RefineBlock в stb_dxt)
    weights = ((1.0, 0.0), (0.0, 1.0), (2 / 3, 1 / 3), (1 / 3, 2 / 3))
    for _ in range(2):
        saa = sbb = sab = 0.0
        ar = ag = abl = br = bg = bbl = 0.0
        for k, (r, g, b) in enumerate(px):
            if not vis[k]:
                continue
            wa, wb = weights[(best[3] >> (2 * k)) & 3]
            saa += wa * wa; sbb += wb * wb; sab += wa * wb
            ar += wa * r; ag += wa * g; abl += wa * b
            br += wb * r; bg += wb * g; bbl += wb * b
        det = saa * sbb - sab * sab
        if abs(det) < 1e-6:
            break
        f = 1.0 / det
        c0 = _q565((ar * sbb - br * sab) * f, (ag * sbb - bg * sab) * f, (abl * sbb - bbl * sab) * f)
        c1 = _q565((br * saa - ar * sab) * f, (bg * saa - ag * sab) * f, (bbl * saa - abl * sab) * f)
        bits, err = _color_indices(px, c0, c1, vis)
        if err >= best[0]:
            break
        best = (err, c0, c1, bits)
    _, c0, c1, bits = best
    if c0 == c1:
        return c0, c1, 0
    if c0 < c1:                     # 4 оттенка и при «режиме DXT1» (c0 > c1): переставить концы
        c0, c1 = c1, c0
        bits = bits ^ 0x55555555    # 0↔1, 2↔3
    return c0, c1, bits


def _alpha_indices(al, pal):
    bits = err = 0
    for k, a in enumerate(al):
        best, bi = 1 << 30, 0
        for j, v in enumerate(pal):
            e = (a - v) * (a - v)
            if e < best:
                best, bi = e, j
        bits |= bi << (3 * k)
        err += best
    return bits, err


def _encode_alpha(al):
    lo, hi = min(al), max(al)
    if lo == hi:
        return lo, lo, 0
    a0, a1 = hi, lo                                     # 8 значений
    bits, err = _alpha_indices(al, _alpha_palette(a0, a1))
    best = (err, a0, a1, bits)
    mid = [a for a in al if 0 < a < 255]
    if mid and len(mid) < 16:                           # 6 значений + точные 0 и 255
        m0, m1 = min(mid), max(mid)
        b6, e6 = _alpha_indices(al, _alpha_palette(m0, m1))
        if e6 < best[0]:
            best = (e6, m0, m1, b6)
    _, a0, a1, bits = best
    return a0, a1, bits


def dxt5_encode(rgba, w, h):
    """RGBA8 w×h (кратные 4) → линейные блоки DXT5 (PC)."""
    if w % 4 or h % 4:
        raise ValueError('размеры должны делиться на 4')
    out = bytearray()
    cache = {}
    for by in range(0, h, 4):
        for bx in range(0, w, 4):
            raw = b''.join(rgba[((by + y) * w + bx) * 4:((by + y) * w + bx + 4) * 4] for y in range(4))
            blk = cache.get(raw)
            if blk is None:
                px = [(raw[k * 4], raw[k * 4 + 1], raw[k * 4 + 2]) for k in range(16)]
                al = [raw[k * 4 + 3] for k in range(16)]
                a0, a1, abits = _encode_alpha(al)
                c0, c1, cbits = _encode_color(px, al)
                blk = bytes((a0, a1)) + abits.to_bytes(6, 'little') + struct.pack('<HHI', c0, c1, cbits)
                if len(cache) < 8192:
                    cache[raw] = blk
            out += blk
    return bytes(out)


# ---------------------------------------------------------------- PNG / DDS

def png_read(path):
    """PNG → (w, h, RGBA8). Все типы цвета, 1–16 бит, Adam7."""
    d = open(path, 'rb').read()
    if d[:8] != b'\x89PNG\r\n\x1a\n':
        raise ValueError(f'{path}: не PNG')
    p, idat, plte, trns = 8, bytearray(), None, None
    while p < len(d):
        ln = struct.unpack_from('>I', d, p)[0]
        t, body = d[p + 4:p + 8], d[p + 8:p + 8 + ln]
        p += 12 + ln
        if t == b'IHDR':
            w, h, bd, ct, _, _, il = struct.unpack('>IIBBBBB', body)
        elif t == b'PLTE':
            plte = body
        elif t == b'tRNS':
            trns = body
        elif t == b'IDAT':
            idat += body
        elif t == b'IEND':
            break
    raw = zlib.decompress(bytes(idat))
    chans = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[ct]
    bpp_bits = chans * bd
    bpp = max(1, bpp_bits // 8)
    out = bytearray(w * h * 4)
    passes = ([(0, 0, 8, 8), (4, 0, 8, 8), (0, 4, 4, 8), (2, 0, 4, 4), (0, 2, 2, 4), (1, 0, 2, 2), (0, 1, 1, 2)]
              if il else [(0, 0, 1, 1)])
    q = 0
    for x0, y0, dx, dy in passes:
        pw, phh = (w - x0 + dx - 1) // dx, (h - y0 + dy - 1) // dy
        if pw == 0 or phh == 0:
            continue
        stride = (pw * bpp_bits + 7) // 8
        prev = bytearray(stride)
        for yy in range(phh):
            f = raw[q]
            line = bytearray(raw[q + 1:q + 1 + stride])
            q += 1 + stride
            if f == 1:
                for i in range(bpp, stride):
                    line[i] = (line[i] + line[i - bpp]) & 255
            elif f == 2:
                for i in range(stride):
                    line[i] = (line[i] + prev[i]) & 255
            elif f == 3:
                for i in range(stride):
                    a = line[i - bpp] if i >= bpp else 0
                    line[i] = (line[i] + ((a + prev[i]) >> 1)) & 255
            elif f == 4:
                for i in range(stride):
                    a = line[i - bpp] if i >= bpp else 0
                    b = prev[i]
                    c = prev[i - bpp] if i >= bpp else 0
                    pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
                    line[i] = (line[i] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
            prev = line
            y = y0 + yy * dy
            if ct == 6 and bd == 8 and dx == 1:          # частый случай (портреты NHL): RGBA8
                out[y * w * 4:(y + 1) * w * 4] = line
                continue
            for xx in range(pw):
                if bd == 16:                             # исходные значения (orig) — для tRNS, выход — старший байт
                    orig = [int.from_bytes(line[(xx * chans + c) * 2:(xx * chans + c) * 2 + 2], 'big') for c in range(chans)]
                    s = [v >> 8 for v in orig]
                elif bd == 8:
                    orig = s = list(line[xx * chans:xx * chans + chans])
                else:
                    bit = xx * bd
                    v = (line[bit >> 3] >> (8 - bd - (bit & 7))) & ((1 << bd) - 1)
                    orig = [v]
                    s = [v if ct == 3 else v * 255 // ((1 << bd) - 1)]
                if ct == 0:
                    a = 0 if trns and orig[0] == int.from_bytes(trns[:2], 'big') else 255
                    px = (s[0], s[0], s[0], a)
                elif ct == 2:
                    key = [int.from_bytes(trns[i:i + 2], 'big') for i in (0, 2, 4)] if trns else None
                    px = (s[0], s[1], s[2], 0 if key == orig else 255)
                elif ct == 3:
                    i = s[0]
                    px = (plte[i * 3], plte[i * 3 + 1], plte[i * 3 + 2], trns[i] if trns and i < len(trns) else 255)
                elif ct == 4:
                    px = (s[0], s[0], s[0], s[1])
                else:
                    px = tuple(s)
                o = (y * w + x0 + xx * dx) * 4
                out[o:o + 4] = bytes(px)
    return w, h, bytes(out)


def png_write(path, w, h, rgba):
    raw = bytearray()
    for y in range(h):
        raw.append(0)
        raw += rgba[y * w * 4:(y + 1) * w * 4]

    def chunk(t, body):
        return struct.pack('>I', len(body)) + t + body + struct.pack('>I', zlib.crc32(t + body) & 0xFFFFFFFF)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, 'wb') as f:
        f.write(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 6, 0, 0, 0))
                + chunk(b'IDAT', zlib.compress(bytes(raw), 9)) + chunk(b'IEND', b''))


def dds_write(path, w, h, blocks):
    hdr = struct.pack('<4sIIIIIII44xII4sIIIIIIIII4x', b'DDS ', 124, 0x81007, h, w, len(blocks), 0, 1,
                      32, 4, b'DXT5', 0, 0, 0, 0, 0, 0x1000, 0, 0, 0)
    assert len(hdr) == 128
    with open(path, 'wb') as f:
        f.write(hdr + blocks)


def dds_read(path):
    d = open(path, 'rb').read()
    if d[:4] != b'DDS ' or d[84:88] != b'DXT5':
        raise ValueError(f'{path}: нужен DDS DXT5')
    h, w = struct.unpack_from('<II', d, 12)
    size = (w // 4) * (h // 4) * 16
    return w, h, d[128:128 + size]


# ---------------------------------------------------------------- фото игрока

class PlayerHead:
    """p<artid>.big: контейнер, ролик Apt и текстура."""

    def __init__(self, data, path=''):
        self.path = path
        self.big = Bigf(data)
        self.tex_name = None
        for name, blob in self.big.entries:
            if not blob:
                continue
            body, packed = unpack_entry(blob)
            if body[:4] == b'XPR2':
                self.tex_name, self.tex_packed, self.tex = name, packed, Xpr2(body)
            elif body[:8] == b'Apt Data':
                self.apt_name, self.apt_packed, self.apt = name, packed, body
        if self.tex_name is None:
            raise ValueError(f'{path}: нет текстуры XPR2')
        m = struct.unpack_from('>I', self.apt, 0x10)[0]          # символ Movie (тип 9)
        if struct.unpack_from('>II', self.apt, m) != (9, 0x09876543):
            raise ValueError(f'{path}: не найден символ Movie')
        self.stage = struct.unpack_from('>II', self.apt, m + 0x24)

    @classmethod
    def load(cls, path):
        return cls(open(path, 'rb').read(), path)

    def blocks(self):
        return xenos_to_linear(self.tex)

    def decode_rgba(self):
        t = self.tex
        return t.width, t.height, dxt5_decode(self.blocks(), t.width, t.height)

    def with_blocks(self, blocks, trailer=None):
        """Новый .big того же устройства с другими блоками DXT5."""
        xpr = self.tex.build(linear_to_xenos(self.tex, blocks))
        big = Bigf(self.big.raw)
        big.put(self.tex_name, refpack_compress(xpr))
        return big.build(trailer)


def crop(rgba, w, h, cw, ch):
    return b''.join(rgba[y * w * 4:(y * w + cw) * 4] for y in range(ch))


def place(rgba, w, h, tw, th):
    """RGBA w×h в левый верхний угол прозрачной текстуры tw×th."""
    out = bytearray(tw * th * 4)
    for y in range(min(h, th)):
        out[y * tw * 4:(y * tw + min(w, tw)) * 4] = rgba[y * w * 4:(y * w + min(w, tw)) * 4]
    return bytes(out)


# ---------------------------------------------------------------- масштаб и компоновка

def _lanczos(x, a=3.0):
    if x == 0.0:
        return 1.0
    if -a < x < a:
        px = math.pi * x
        return a * math.sin(px) * math.sin(px / a) / (px * px)
    return 0.0


def _taps(dst_len, src_len, scale, src0, dst0):
    """Для каждого выходного пикселя — [(индекс источника, вес)]: dst = (src - src0)·scale + dst0."""
    support = 3.0 / min(1.0, scale)
    k = min(1.0, scale)
    res = []
    for x in range(dst_len):
        c = (x + 0.5 - dst0) / scale + src0             # центр в координатах источника
        lo, hi = int(math.floor(c - support)), int(math.ceil(c + support))
        taps, tot = [], 0.0
        for i in range(max(lo, 0), min(hi, src_len - 1) + 1):
            wgt = _lanczos((i + 0.5 - c) * k)
            if wgt:
                taps.append((i, wgt))
                tot += wgt
        if c < 0 or c >= src_len or not taps or tot <= 1e-9:
            res.append(())
        else:
            res.append(tuple((i, wgt / tot) for i, wgt in taps))
    return res


def resample(rgba, sw, sh, dw, dh, scale, src0=(0.0, 0.0), dst0=(0.0, 0.0)):
    """Lanczos-3 c премножением альфы: точка src0 источника встаёт в dst0, масштаб scale."""
    n = sw * sh
    pa = [rgba[i * 4 + 3] / 255.0 for i in range(n)]
    planes = [[rgba[i * 4 + c] * pa[i] for i in range(n)] for c in range(3)] + [[a * 255.0 for a in pa]]
    tx = _taps(dw, sw, scale, src0[0], dst0[0])
    ty = _taps(dh, sh, scale, src0[1], dst0[1])
    cols = [x for x in range(dw) if tx[x]]
    out = bytearray(dw * dh * 4)
    if not cols:
        return bytes(out)
    x_lo, x_hi = cols[0], cols[-1] + 1
    tx = tx[x_lo:x_hi]
    nx = x_hi - x_lo
    rows_needed = sorted({i for t in ty for i, _ in t})
    horiz = {}
    for y in rows_needed:
        base = y * sw
        hr = []
        for plane in planes:
            row = plane[base:base + sw]
            hr.append([sum(row[i] * wgt for i, wgt in t) if t else 0.0 for t in tx])
        horiz[y] = hr
    for y in range(dh):
        t = ty[y]
        if not t:
            continue
        acc = [[0.0] * nx for _ in range(4)]
        for i, wgt in t:
            hr = horiz[i]
            for c in range(4):
                a, src = acc[c], hr[c]
                for x in range(nx):
                    a[x] += src[x] * wgt
        for xi in range(nx):
            al = acc[3][xi]
            x = x_lo + xi
            o = (y * dw + x) * 4
            if al <= 0.5:
                continue                                # прозрачное — чёрное, как у EA
            a8 = min(255, int(al + 0.5))
            inv = 255.0 / al
            out[o] = min(255, max(0, int(acc[0][xi] * inv + 0.5)))
            out[o + 1] = min(255, max(0, int(acc[1][xi] * inv + 0.5)))
            out[o + 2] = min(255, max(0, int(acc[2][xi] * inv + 0.5)))
            out[o + 3] = a8
    return bytes(out)


def mug_geometry(rgba, w, h, thr=128):
    """Верх головы (первая строка с заметной альфой в средней трети) и центр головы по x."""
    top = None
    for y in range(h):
        n = sum(1 for x in range(w // 3, 2 * w // 3) if rgba[(y * w + x) * 4 + 3] > thr)
        if n >= 3:
            top = y
            break
    if top is None:
        raise ValueError('портрет пустой')
    xs = [x for y in range(top, min(h, top + h // 6)) for x in range(w) if rgba[(y * w + x) * 4 + 3] > thr]
    return top, sum(xs) / len(xs)


# Компоновка под оригиналы EA (замер по 40 случайным фото каждого вида против 8 портретов NHL,
# docs/player-photos.md): scale — масштаб портрета NHL 336×336 (по ширине головы, шеи и
# расстоянию «макушка — плечи»), top и cx — куда на сцене встаёт макушка и центр головы,
# fade — строки сцены, где плечи плавно уходят в прозрачность (у малых — обрез по краю).
MUG_TOP, MUG_CX = 71.5, 167.5        # макушка и центр головы у портретов NHL 336×336 (медиана)
LAYOUT = {
    'big': {'scale': 1.36, 'top': 15, 'cx': 234.0, 'fade': (230, 250)},
    'small': {'scale': 0.67, 'top': 11, 'cx': 101.0, 'fade': None},
}


def compose(mug, kind, tex_w, tex_h, stage, auto=False):
    """Портрет NHL (w, h, rgba) → RGBA текстуры tex_w×tex_h с картинкой на сцене stage.

    По умолчанию кадр NHL берётся как есть (у них постоянная постановка), auto — по найденной
    макушке и центру головы."""
    w, h, rgba = mug
    lay = LAYOUT[kind]
    k = w / 336.0
    top, cx = mug_geometry(rgba, w, h) if auto else (MUG_TOP * k, MUG_CX * k)
    s = lay['scale'] / k                                # другой размер исходника — тот же кадр
    sw, sh = stage
    img = resample(rgba, w, h, sw, sh, s, src0=(cx, float(top)), dst0=(lay['cx'], float(lay['top'])))
    if lay['fade']:
        y0, y1 = lay['fade']
        img = bytearray(img)
        for y in range(y0, sh):
            t = 0.0 if y >= y1 else (y1 - y) / float(y1 - y0)
            k = t * t * (3 - 2 * t)                     # smoothstep, как у оригиналов
            for x in range(sw):
                o = (y * sw + x) * 4 + 3
                a = int(img[o] * k + 0.5)
                img[o] = a
                if a == 0:
                    img[o - 3:o] = b'\0\0\0'
        img = bytes(img)
    return place(img, sw, sh, tex_w, tex_h)


# ---------------------------------------------------------------- проверки

def roundtrip(path, deep=False):
    """Разбор и сборка: контейнер байт-в-байт, тайлинг туда-обратно; с deep — ещё RefPack
    туда-обратно и полная пересборка из линейных блоков DXT5 (как из DDS)."""
    data = open(path, 'rb').read()
    head = PlayerHead(data, path)
    res = {'container': head.big.build() == data}
    t = head.tex
    blocks = xenos_to_linear(t)
    res['tiling'] = linear_to_xenos(t, blocks) == t.data
    if deep:
        xpr = t.build(t.data)
        z = refpack_compress(xpr)
        res['refpack'] = refpack_decompress(z) == xpr
        res['refpack_size'] = (len(z), len(head.big.get(head.tex_name)))
        new = PlayerHead(head.with_blocks(blocks))         # блоки → тайлинг → XPR2 → свой RefPack → BIGF
        others = all(a == b for (n, a), (m, b) in zip(head.big.entries, new.big.entries) if n != head.tex_name)
        new.big.put(new.tex_name, head.big.get(head.tex_name))   # со сжатием EA — весь файл как был
        res['rebuild'] = others and new.tex.data == t.data and new.big.build() == data
    return head, res


def psnr(a, b, chans=(0, 1, 2, 3)):
    se = n = 0
    for i in range(0, len(a), 4):
        for c in chans:
            se += (a[i + c] - b[i + c]) ** 2
            n += 1
    return 99.0 if se == 0 else 10 * math.log10(255 * 255 * n / se)


# ---------------------------------------------------------------- команды

def cmd_info(paths):
    for path in paths:
        head = PlayerHead.load(path)
        b = head.big
        print(f'{path}: {len(b.raw)} байт, BIGF размер {b.total}, хвост {b.trailer.hex()}, '
              f'заголовок 0x{b.hsize:X}, метка {b.tag[:4].decode()} {b.tag[4:].hex()}')
        for (name, blob), off in zip(b.entries, b.offsets):
            body, packed = unpack_entry(blob) if blob else (b'', False)
            kind = ('Apt Data' if body[:8] == b'Apt Data' else 'Apt constant' if body[:12] == b'Apt constant'
                    else 'XPR2' if body[:4] == b'XPR2' else 'метка' if not blob else 'геометрия')
            z = f', RefPack → {len(body)}' if packed else ''
            print(f'   {name:>5}  @0x{off:05X}  {len(blob):6} байт{z}  {kind}')
        print(f'   сцена Apt {head.stage[0]}×{head.stage[1]}; текстура {head.tex.describe()}')


def cmd_decode(args):
    path, out = args[0], args[1]
    head = PlayerHead.load(path)
    w, h, rgba = head.decode_rgba()
    if '--dds' in args:
        dds_write(args[args.index('--dds') + 1], w, h, head.blocks())
    if '--full' not in args:
        sw, sh = head.stage
        rgba, w, h = crop(rgba, w, h, sw, sh), sw, sh
    png_write(out, w, h, rgba)
    print(f'{path} → {out} ({w}×{h})')


def cmd_encode(args):
    src, template, out = args[0], args[1], args[2]
    trailer = None
    if '--trailer' in args and args[args.index('--trailer') + 1] == 'md5':
        trailer = 'md5'
    head = PlayerHead.load(template)
    t = head.tex
    if src.lower().endswith('.dds'):
        w, h, blocks = dds_read(src)
        if (w, h) != (t.width, t.height):
            raise SystemExit(f'DDS {w}×{h}, а текстура шаблона {t.width}×{t.height}')
    else:
        w, h, rgba = png_read(src)
        if (w, h) == tuple(head.stage):
            rgba = place(rgba, w, h, t.width, t.height)
        elif (w, h) != (t.width, t.height):
            raise SystemExit(f'PNG {w}×{h}: нужен размер сцены {head.stage[0]}×{head.stage[1]} '
                             f'или текстуры {t.width}×{t.height}')
        blocks = dxt5_encode(rgba, t.width, t.height)
    data = head.with_blocks(blocks, trailer)
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    open(out, 'wb').write(data)
    print(f'{src} → {out} ({len(data)} байт, шаблон {template})')


def cmd_roundtrip(args):
    deep = '--deep' in args
    paths = [a for a in args if not a.startswith('--')]
    files = []
    for p in paths:
        if os.path.isdir(p):
            files += sorted(os.path.join(dp, f) for dp, _, fs in os.walk(p) for f in fs if f.endswith('.big'))
        else:
            files.append(p)
    bad = 0
    for path in files:
        head, res = roundtrip(path, deep)
        ok = all(v for k, v in res.items() if k != 'refpack_size')
        bad += not ok
        if len(files) <= 20 or not ok:
            extra = f", свой RefPack {res['refpack_size'][0]} байт, в файле {res['refpack_size'][1]}" if deep else ''
            print(f"{'OK ' if ok else 'ОШИБКА'} {path}: " + ', '.join(f'{k}={v}' for k, v in res.items() if k != 'refpack_size') + extra)
    print(f'файлов {len(files)}, с ошибками {bad}')
    return bad


def cmd_compose(args):
    mug_path, artid, outdir = args[0], int(args[1]), args[2]
    kinds = ['big', 'small']
    if '--kind' in args:
        kinds = args[args.index('--kind') + 1].split(',')
    preview = args[args.index('--preview') + 1] if '--preview' in args else None
    auto = '--auto' in args
    if not 0 < artid <= 16383:
        raise SystemExit('artid — от 1 до 16383 (поле 14 бит)')
    mug = png_read(mug_path)
    for kind in kinds:
        orig = original_path(kind, artid)
        template = orig if os.path.exists(orig) else default_template(kind)
        head = PlayerHead.load(template)
        t = head.tex
        rgba = compose(mug, kind, t.width, t.height, head.stage, auto)
        blocks = dxt5_encode(rgba, t.width, t.height)
        data = head.with_blocks(blocks, None if template == orig else 'md5')
        rel = asset_relpath(kind, artid)
        out = os.path.join(outdir, *rel.split('/'))
        os.makedirs(os.path.dirname(out), exist_ok=True)
        open(out, 'wb').write(data)
        print(f'{mug_path} → {out} ({len(data)} байт, шаблон {os.path.basename(os.path.dirname(template))}/'
              f'{os.path.basename(template)}, сцена {head.stage[0]}×{head.stage[1]})')
        if len(data) > MAX_ORIGINAL[kind]:
            print(f'   внимание: больше самого большого файла игры ({MAX_ORIGINAL[kind]} байт)')
        if preview:
            back = PlayerHead(data)
            w, h, dec = back.decode_rgba()
            sw, sh = back.stage
            png_write(os.path.join(preview, f'{kind}_p{artid}.png'), sw, sh, crop(dec, w, h, sw, sh))


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    cmd, args = sys.argv[1], sys.argv[2:]
    if cmd == 'info':
        cmd_info(args)
    elif cmd == 'decode':
        cmd_decode(args)
    elif cmd == 'encode':
        cmd_encode(args)
    elif cmd == 'roundtrip':
        sys.exit(1 if cmd_roundtrip(args) else 0)
    elif cmd == 'compose':
        cmd_compose(args)
    else:
        sys.exit(__doc__)


if __name__ == '__main__':
    main()
