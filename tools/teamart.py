"""Арт команд NHL 13 (Xbox 360): логотипы интерфейса и 3D (центр льда, шайба, баннер) ⇄ PNG, сборка своих.

    python teamart.py info FILE…                         # .big (интерфейс) или .rx2 (3D): формат, размеры, мипы
    python teamart.py decode FILE OUT.png [--full] [--mips DIR] [--tex N]
                                                         # сцена (или вся текстура); --mips — все уровни в DIR
    python teamart.py roundtrip FILE_OR_DIR… [--deep]    # разбор → сборка байт-в-байт (контейнер, тайлинг, мипы)
    python teamart.py render SVG OUT.png W H [--strip 4,5]
                                                         # SVG → PNG через Chrome/Edge без окна (прозрачный фон);
                                                         # --strip — номера <path>, которые убрать (знак ®)
    python teamart.py build SPEC.json OUTDIR [--only t,s,d,c,w,r,center,puck,banner,spot] [--preview DIR] [--legacy]
                                                         # исходник (SVG) → все наборы под artid из SPEC; размеры и
                                                         # растушёвка — по замерам EA (--legacy — сборка от 08.10 утра)
    python teamart.py alias SRC_ARTID DST_ARTID OUTDIR   # копия файлов формы команды под другой artid
                                                         # (имена растров внутри переписываются; та же длина номера)

Где что лежит (подробности — docs/logos-arenas.md):
  * Интерфейс — fe/ion/artassets/<набор>/<буква><artid>.big, номер = exhibitionteams.artid:
    teamlogos t (256×256), teamlogossmall s (128×64, «таблетка»), teamlogosdynasty d (128×128),
    teamlogoscalendar c (сцена 98×86 в текстуре 128×128), teamlogoswide w (256×256, крупный план с
    растушёвкой), teamlogosreflection r (256×512, логотип с отражением; в игре только 0…29).
    Контейнер как у фото игроков (playerhead.py): BIGF → Apt + XPR2 (RefPack). Текстура — k_8_8_8_8
    (D3DFMT_A8R8G8B8): на диске байты A, R, G, B на тексель, тайлинг Xenos (4 байта на тексель),
    порядок 8in32, без мипов, альфа прямая.
  * 3D — rendering/…/*.rx2, контейнер RenderWare 4 для Xbox 360 ("\\x89RW4xb2"); в архиве каждый файл
    дополнительно сжат chunklzx (tools/unchunk.py), свободный файл в cache: можно класть без сжатия
    (поток AssetStream распознаёт chunkzip/chunkref/chunlzma/chunklzx по магии, иначе читает как есть).
    Текстура: DXT1/DXT3/DXT5, тайлинг Xenos, порядок 8in16, полная цепочка мипов, хвост мипов ≤ 16
    текселей упакован в один тайл (GetPackedMipOffset, как в Xenia) — проверено байт-в-байт на
    оригиналах (roundtrip --deep).
    centerlogo_<artid хозяина>_cm.rx2 — 1024×1024 DXT3, 11 уровней; puck_<artid>_cm.rx2 — 256×512 DXT1,
    10 уровней; banner_<artid>_cm.rx2 — 512×512 DXT3, 10 уровней; spotlight/texlib_<spotlight>.rx2 —
    256×256 DXT5. Форма (свитер, таблички, шорты, гетры, нашивки) ищется по artid команды — см. alias.

Только стандартная библиотека (+ Chrome или Edge для render/build). Каталог игры — NHL13_GAME или game/.
"""
import json, math, os, shutil, struct, subprocess, sys, tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import playerhead as ph  # noqa: E402  (BIGF, XPR2, RefPack, тайлинг, DXT5, PNG)

# ---------------------------------------------------------------- общие мелочи

FMT_8888, FMT_DXT1, FMT_DXT3, FMT_DXT5 = 6, 18, 19, 20
FMT_NAMES = {FMT_8888: '8888', FMT_DXT1: 'DXT1', FMT_DXT3: 'DXT3', FMT_DXT5: 'DXT5'}
BLOCK = {FMT_8888: (1, 4), FMT_DXT1: (4, 8), FMT_DXT3: (4, 16), FMT_DXT5: (4, 16),   # сторона блока, байт
         0x31: (4, 16), 0x3A: (4, 8), 0x3B: (4, 8), 0x3C: (4, 8)}   # DXN, DXT3A, DXT5A, CTX1 — только раскладка


def log2c(v):
    return max(0, (v - 1).bit_length())


def swap16(b):
    b = bytearray(b)
    b[0::2], b[1::2] = b[1::2], b[0::2]
    return bytes(b)


def swap32(b):
    b = bytearray(b)
    b[0::4], b[1::4], b[2::4], b[3::4] = b[3::4], b[2::4], b[1::4], b[0::4]
    return bytes(b)


def endian_swap(b, mode):
    return swap16(b) if mode == 1 else swap32(b) if mode == 2 else bytes(b)


class Fetch:
    """Константа выборки текстуры Xenos (6 слов)."""

    def __init__(self, words):
        self.words = tuple(words)
        d0, d1, d2, d3, d4, d5 = self.words
        self.tiled = d0 >> 31
        self.pitch = ((d0 >> 22) & 0x1FF) * 32
        self.fmt = d1 & 0x3F
        self.endian = (d1 >> 6) & 3
        self.base = d1 >> 12
        self.width = (d2 & 0x1FFF) + 1
        self.height = ((d2 >> 13) & 0x1FFF) + 1
        self.mip_min, self.mip_max = (d4 >> 2) & 0xF, (d4 >> 6) & 0xF
        self.dimension = (d5 >> 9) & 3
        self.packed = (d5 >> 11) & 1
        self.mip_addr = (d5 >> 12) << 12

    def describe(self):
        return (f'{self.width}×{self.height} {FMT_NAMES.get(self.fmt, self.fmt)} '
                f'{"тайлинг" if self.tiled else "линейно"}, порядок {ph.ENDIAN_NAMES[self.endian]}, '
                f'pitch {self.pitch}, мипы {self.mip_min}..{self.mip_max}'
                f'{" (хвост упакован)" if self.packed else ""}, мипы с +0x{self.mip_addr:X}')


# ---------------------------------------------------------------- раскладка уровней (как в Xenia)

def packed_mip_offset(width, height, mip):
    """Смещение уровня mip в упакованном хвосте, в текселях (x, y), или None, если не упакован."""
    lw, lh = log2c(width), log2c(height)
    ls = min(lw, lh)
    if ls > 4 + mip:
        return None
    base = ls - 4 if ls > 4 else 0
    pm = mip - base
    if pm < 3:
        return (0, 16 >> pm) if lw > lh else (16 >> pm, 0)
    if lw > lh:
        return ((1 << (lw - base)) >> (pm - 2), 0)
    return (0, (1 << (lh - base)) >> (pm - 2))


class Layout:
    """Где в буфере текстуры лежит каждый уровень. Уровень: (w, h, смещение, pitch в блоках,
    (x0, y0) в блоках внутри хвоста или None)."""

    def __init__(self, f):
        self.fmt = f.fmt
        bs, bpb = BLOCK[f.fmt]
        self.bs, self.bpb, self.log2 = bs, bpb, bpb.bit_length() - 1
        self.tiled = f.tiled
        self.endian = f.endian
        self.levels = []
        w, h = f.width, f.height
        # базовый уровень: pitch из константы, высота — до 32 блоков (тайл)
        pitch0 = max(f.pitch // bs, (w + bs - 1) // bs)
        hb0 = (h + bs - 1) // bs
        if f.tiled:
            pitch0 = (pitch0 + 31) & ~31
            hb0 = (hb0 + 31) & ~31
        self.levels.append((w, h, 0, pitch0, None))
        self.base_size = pitch0 * hb0 * bpb
        off = f.mip_addr if f.mip_max else self.base_size
        pw, phh = 1 << log2c(w), 1 << log2c(h)
        tail = None
        for lv in range(1, f.mip_max + 1):
            lw, lh = max(1, pw >> lv), max(1, phh >> lv)
            po = packed_mip_offset(w, h, lv) if f.packed else None
            if po is not None:
                if tail is None:                         # первый упакованный уровень задаёт область хвоста
                    tw = ((lw + bs - 1) // bs + 31) & ~31
                    th = ((lh + bs - 1) // bs + 31) & ~31
                    if not f.tiled:
                        tw = ((tw * bpb + 255) & ~255) // bpb
                    tail = (off, tw)
                    off += tw * th * bpb
                self.levels.append((lw, lh, tail[0], tail[1], (po[0] // bs, po[1] // bs)))
                continue
            wb, hb = (lw + bs - 1) // bs, (lh + bs - 1) // bs
            if f.tiled:
                wb, hb = (wb + 31) & ~31, (hb + 31) & ~31
            else:                                        # линейные: строка — кратно 256 байт
                wb = ((wb * bpb + 255) & ~255) // bpb
            self.levels.append((lw, lh, off, wb, None))
            off += wb * hb * bpb
        self.size = off

    def block_offsets(self, lv):
        """Смещения блоков уровня lv в порядке строк (для линейной картинки уровня)."""
        lw, lh, off, pitch, xy = self.levels[lv]
        bs, bpb = self.bs, self.bpb
        bw, bh = (lw + bs - 1) // bs, (lh + bs - 1) // bs
        x0, y0 = xy or (0, 0)
        out = []
        for by in range(bh):
            for bx in range(bw):
                x, y = bx + x0, by + y0
                o = ph.tiled_offset_2d(x, y, pitch, self.log2) if self.tiled else (y * pitch + x) * bpb
                out.append(off + o)
        return out

    def get_level(self, buf, lv):
        """Линейные блоки уровня (порядок PC: после перестановки байт)."""
        bpb = self.bpb
        raw = b''.join(buf[o:o + bpb] for o in self.block_offsets(lv))
        return endian_swap(raw, self.endian)

    def put_level(self, buf, lv, blocks):
        bpb = self.bpb
        data = endian_swap(blocks, self.endian)
        for i, o in enumerate(self.block_offsets(lv)):
            buf[o:o + bpb] = data[i * bpb:(i + 1) * bpb]


# ---------------------------------------------------------------- DXT1/3/5 и 8888

def _c565(c):
    return ph._c565(c)


def dxt_decode(fmt, blocks, w, h):
    """Линейные блоки (PC) → RGBA8 w×h (w, h — кратно 4 или меньше 4 для крошечных мипов)."""
    if fmt == FMT_8888:                      # после 8in32: B G R A в байтах (значение ARGB)
        out = bytearray(len(blocks))
        out[0::4], out[1::4], out[2::4], out[3::4] = blocks[2::4], blocks[1::4], blocks[0::4], blocks[3::4]
        return bytes(out)
    if fmt == FMT_DXT5:
        bw4, bh4 = max(4, (w + 3) & ~3), max(4, (h + 3) & ~3)
        full = ph.dxt5_decode(blocks, bw4, bh4)
        return ph.crop(full, bw4, bh4, w, h) if (bw4, bh4) != (w, h) else full
    bw4, bh4 = max(4, (w + 3) & ~3), max(4, (h + 3) & ~3)
    out = bytearray(bw4 * bh4 * 4)
    nbw = bw4 // 4
    step = 8 if fmt == FMT_DXT1 else 16
    for i in range(len(blocks) // step):
        blk = blocks[i * step:(i + 1) * step]
        if fmt == FMT_DXT3:
            abits = int.from_bytes(blk[0:8], 'little')
            al = [((abits >> (4 * k)) & 15) * 17 for k in range(16)]
            cb = blk[8:16]
        else:
            al = None
            cb = blk
        c0, c1, cbits = struct.unpack_from('<HHI', cb, 0)
        p0, p1 = _c565(c0), _c565(c1)
        if fmt == FMT_DXT1 and c0 <= c1:
            pal = [p0 + (255,), p1 + (255,), tuple((a + b) // 2 for a, b in zip(p0, p1)) + (255,), (0, 0, 0, 0)]
        else:
            pal = [p0 + (255,), p1 + (255,), tuple((2 * a + b) // 3 for a, b in zip(p0, p1)) + (255,),
                   tuple((a + 2 * b) // 3 for a, b in zip(p0, p1)) + (255,)]
        bx, by = (i % nbw) * 4, (i // nbw) * 4
        for k in range(16):
            r, g, b, a = pal[(cbits >> (2 * k)) & 3]
            if al is not None:
                a = al[k]
            o = ((by + (k >> 2)) * bw4 + bx + (k & 3)) * 4
            out[o:o + 4] = bytes((r, g, b, a))
    out = bytes(out)
    return ph.crop(out, bw4, bh4, w, h) if (bw4, bh4) != (w, h) else out


def _dxt3_alpha(al):
    v = 0
    for k, a in enumerate(al):
        v |= ((a * 15 + 127) // 255) << (4 * k)
    return v.to_bytes(8, 'little')


def dxt_encode(fmt, rgba, w, h):
    """RGBA8 w×h → линейные блоки (PC). Меньше 4×4 — дополняется повтором края."""
    if fmt == FMT_8888:
        out = bytearray(len(rgba))
        out[0::4], out[1::4], out[2::4], out[3::4] = rgba[2::4], rgba[1::4], rgba[0::4], rgba[3::4]
        return bytes(out)
    W, H = max(4, (w + 3) & ~3), max(4, (h + 3) & ~3)
    if (W, H) != (w, h):
        pad = bytearray(W * H * 4)
        for y in range(H):
            for x in range(W):
                s = (min(y, h - 1) * w + min(x, w - 1)) * 4
                pad[(y * W + x) * 4:(y * W + x) * 4 + 4] = rgba[s:s + 4]
        rgba, w, h = bytes(pad), W, H
    if fmt == FMT_DXT5:
        return ph.dxt5_encode(rgba, w, h)
    out = bytearray()
    cache = {}
    for by in range(0, h, 4):
        for bx in range(0, w, 4):
            raw = b''.join(rgba[((by + y) * w + bx) * 4:((by + y) * w + bx + 4) * 4] for y in range(4))
            blk = cache.get(raw)
            if blk is None:
                px = [(raw[k * 4], raw[k * 4 + 1], raw[k * 4 + 2]) for k in range(16)]
                al = [raw[k * 4 + 3] for k in range(16)]
                if fmt == FMT_DXT1:
                    # непрозрачная текстура (шайба): 4 оттенка, c0 > c1; цвет считается по всем пикселям
                    c0, c1, cbits = ph._encode_color(px, [255] * 16)
                    if c0 == c1:
                        cbits = 0
                        if c0 == 0:
                            c0, c1 = 1, 0     # «c0 > c1» и для чёрного (иначе режим с прозрачным)
                        else:
                            c1 = c0 - 1
                    blk = struct.pack('<HHI', c0, c1, cbits)
                else:
                    c0, c1, cbits = ph._encode_color(px, al)
                    blk = _dxt3_alpha(al) + struct.pack('<HHI', c0, c1, cbits)
                if len(cache) < 8192:
                    cache[raw] = blk
            out += blk
    return bytes(out)


def downsample2(rgba, w, h):
    """Уменьшение вдвое (ящик 2×2) с премножением альфы; нечётное/1 — край повторяется."""
    nw, nh = max(1, w // 2), max(1, h // 2)
    out = bytearray(nw * nh * 4)
    for y in range(nh):
        for x in range(nw):
            acc = [0, 0, 0, 0]
            for dy in (0, 1):
                for dx in (0, 1):
                    sx, sy = min(w - 1, 2 * x + dx), min(h - 1, 2 * y + dy)
                    o = (sy * w + sx) * 4
                    a = rgba[o + 3]
                    acc[0] += rgba[o] * a
                    acc[1] += rgba[o + 1] * a
                    acc[2] += rgba[o + 2] * a
                    acc[3] += a
            o = (y * nw + x) * 4
            if acc[3]:
                out[o:o + 3] = bytes(min(255, (c + acc[3] // 2) // acc[3]) for c in acc[:3])
                out[o + 3] = (acc[3] + 2) // 4
    return bytes(out), nw, nh


# ---------------------------------------------------------------- RW4 (rx2)

RW4_MAGIC = b'\x89RW4xb2\x00'
TAG_DATA, TAG_DESC, TAG_NAMES = 0x00010031, 0x00020003, 0x00EC0010


class Rw4Texture:
    def __init__(self, name, desc_off, data_off, size, fetch):
        self.name, self.desc_off, self.data_off, self.size, self.fetch = name, desc_off, data_off, size, fetch
        self.layout = Layout(fetch) if fetch.fmt in BLOCK else None     # неизвестный формат — только имя/буфер


class Rw4:
    """Контейнер RenderWare 4 (Xbox 360) с текстурами; правка — только пиксели (заголовки не трогаются)."""

    def __init__(self, data, path=''):
        if data[:8] == b'chunklzx' or data[:8] == b'chunkzip':
            import unchunk
            data = unchunk.unchunk(data)
        if data[:8] != RW4_MAGIC:
            raise ValueError(f'{path}: не RW4xb2')
        self.raw = bytearray(data)
        self.path = path
        u32 = lambda o: struct.unpack_from('>I', data, o)[0]
        count, table, self.hdr_size = u32(0x20), u32(0x30), u32(0x44)
        datas, descs, names = [], [], []
        self.name_slots = []                 # (смещение строки, длина) — имена растров
        for i in range(count):
            e = table + 24 * i
            ints = struct.unpack_from('>5I', data, e)
            tag = u32(e + 20)
            if tag == TAG_DATA:
                datas.append(ints)
            elif tag == TAG_DESC:
                descs.append(ints)
            elif tag == TAG_NAMES:
                # число, 0x1505, затем на каждое имя (указатель, 0x00020003, номер записи), строки
                p = ints[0]
                n = u32(p)
                for k in range(n):
                    sp = u32(p + 8 + 12 * k)
                    q = data.index(b'\0', sp)
                    names.append(data[sp:q].decode('latin1'))
                    self.name_slots.append((sp, q - sp))
        if len(datas) != len(descs):
            raise ValueError(f'{path}: {len(datas)} буферов, {len(descs)} описаний')
        self.textures = []
        for i, (dt, ds) in enumerate(zip(datas, descs)):
            words = struct.unpack_from('>6I', data, ds[0] + 0x1C)
            f = Fetch(words)
            name = names[i] if i < len(names) else f'tex{i}'
            self.textures.append(Rw4Texture(name, ds[0], self.hdr_size + dt[0], dt[2], f))

    @classmethod
    def load(cls, path):
        return cls(open(path, 'rb').read(), path)

    def buffer(self, t):
        return self.raw[t.data_off:t.data_off + t.size]

    def decode(self, t, lv=0):
        lw, lh = t.layout.levels[lv][:2]
        blocks = t.layout.get_level(self.buffer(t), lv)
        return lw, lh, dxt_decode(t.fetch.fmt, blocks, lw, lh)

    def replace(self, t, rgba_levels):
        """rgba_levels — [(w, h, rgba)] на все уровни; буфер собирается заново (нули между уровнями)."""
        buf = bytearray(t.size)
        for lv, (w, h, rgba) in enumerate(rgba_levels):
            lw, lh = t.layout.levels[lv][:2]
            if (w, h) != (lw, lh):
                raise ValueError(f'уровень {lv}: {w}×{h} вместо {lw}×{lh}')
            t.layout.put_level(buf, lv, dxt_encode(t.fetch.fmt, rgba, w, h))
        self.raw[t.data_off:t.data_off + t.size] = buf

    def rename(self, old, new):
        """Заменить число old на new в именах растров ("logo_93_0_0_0.Raster" → "logo_55_0_0_0.Raster").
        Длина имени должна сохраниться (номера с тем же числом цифр) — иначе съедет таблица файлов."""
        import re
        old, new = str(old), str(new)
        if len(old) != len(new):
            raise ValueError(f'номера {old} и {new} разной длины — имена растров не переписать на месте')
        pat = re.compile(r'(?<![0-9])' + old + r'(?![0-9])')
        done = []
        for i, (sp, ln) in enumerate(self.name_slots):
            s = self.raw[sp:sp + ln].decode('latin1')
            t = pat.sub(new, s, count=1)
            if t != s:
                self.raw[sp:sp + ln] = t.encode('latin1')
                self.textures[i].name = t if i < len(self.textures) else t
                done.append((s, t))
        return done

    def bytes(self):
        return bytes(self.raw)


def mip_chain(rgba, w, h, levels):
    out = [(w, h, rgba)]
    for _ in range(1, levels):
        rgba, w, h = downsample2(rgba, w, h)
        out.append((w, h, rgba))
    return out


# ---------------------------------------------------------------- интерфейс (BIGF + XPR2 8888)

class UiLogo:
    def __init__(self, data, path=''):
        self.head = ph.PlayerHead(data, path)     # контейнер и Apt — общие с фото игроков
        t = self.head.tex
        f = Fetch(t.fetch)
        self.fetch = f
        self.layout = Layout(f)
        self.stage = self.head.stage

    @classmethod
    def load(cls, path):
        return cls(open(path, 'rb').read(), path)

    def decode(self):
        f = self.fetch
        blocks = self.layout.get_level(self.head.tex.data, 0)
        return f.width, f.height, dxt_decode(f.fmt, blocks, f.width, f.height)

    def build(self, rgba, trailer=None):
        f = self.fetch
        buf = bytearray(self.head.tex.dsize)
        self.layout.put_level(buf, 0, dxt_encode(f.fmt, rgba, f.width, f.height))
        xpr = self.head.tex.build(bytes(buf))
        big = ph.Bigf(self.head.big.raw)
        big.put(self.head.tex_name, ph.refpack_compress(xpr))
        return big.build(trailer)


def load_any(path):
    data = open(path, 'rb').read()
    if data[:4] == b'BIGF':
        return UiLogo(data, path)
    return Rw4(data, path)


# ---------------------------------------------------------------- проверки

def psnr_premul(a, b):
    """PSNR по премноженным RGBA (цвет под прозрачным не считается)."""
    se = n = 0
    for i in range(0, min(len(a), len(b)), 4):
        aa, ab = a[i + 3], b[i + 3]
        for c in range(3):
            se += ((a[i + c] * aa - b[i + c] * ab) / 255.0) ** 2
        se += (aa - ab) ** 2
        n += 4
    return 99.0 if se == 0 else 10 * math.log10(255 * 255 * n / se)


def roundtrip(path, deep=False):
    obj = load_any(path)
    res = {}
    if isinstance(obj, UiLogo):
        h = obj.head
        res['container'] = h.big.build() == h.big.raw
        f = obj.fetch
        blocks = obj.layout.get_level(h.tex.data, 0)
        buf = bytearray(h.tex.dsize)
        obj.layout.put_level(buf, 0, blocks)
        res['tiling'] = bytes(buf) == h.tex.data
        if deep:
            w, hh, rgba = obj.decode()
            res['8888'] = dxt_encode(f.fmt, rgba, w, hh) == blocks
        return obj, res
    raw = obj.bytes()
    for t in obj.textures:
        if t.layout is None:
            continue                                  # формат без раскладки (не текстура цвета)
        buf = obj.buffer(t)
        ok_size = t.layout.size == t.size
        rebuilt = bytearray(t.size)
        for lv in range(len(t.layout.levels)):
            t.layout.put_level(rebuilt, lv, t.layout.get_level(buf, lv))
        res[t.name] = ok_size and bytes(rebuilt) == bytes(buf)
        if deep and t.fetch.fmt in (FMT_DXT1, FMT_DXT3, FMT_DXT5):
            # уровни должны быть уменьшенными копиями друг друга (иначе раскладка хвоста неверна)
            scores = []
            w0, h0, prev = obj.decode(t, 0)
            for lv in range(1, len(t.layout.levels)):
                w, h, cur = obj.decode(t, lv)
                ref, rw, rh = downsample2(prev, w0, h0)
                if (rw, rh) == (w, h):
                    scores.append(round(psnr_premul(ref, cur), 1))
                prev, w0, h0 = cur, w, h
            res[t.name + ':mips_psnr'] = scores
    return obj, res


# ---------------------------------------------------------------- SVG → PNG (Chrome/Edge без окна)

BROWSERS = [r'C:\Program Files\Google\Chrome\Application\chrome.exe',
            r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe',
            r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',
            r'C:\Program Files\Microsoft\Edge\Application\msedge.exe']


def browser():
    env = os.environ.get('NHL13_BROWSER')
    for p in ([env] if env else []) + BROWSERS:
        if p and os.path.exists(p):
            return p
    raise SystemExit('нужен Chrome или Edge (или путь в NHL13_BROWSER)')


def render_html(html, out_png, w, h):
    """Снимок страницы w×h с прозрачным фоном."""
    tmp = tempfile.mkdtemp(prefix='teamart_')
    try:
        page = os.path.join(tmp, 'page.html')
        open(page, 'w', encoding='utf-8').write(html)
        prof = os.path.join(tmp, 'profile')
        out_abs = os.path.abspath(out_png)
        os.makedirs(os.path.dirname(out_abs), exist_ok=True)
        cmd = [browser(), '--headless=new', '--disable-gpu', '--hide-scrollbars', '--no-first-run',
               '--no-default-browser-check', '--force-device-scale-factor=1', f'--user-data-dir={prof}',
               '--default-background-color=00000000', f'--window-size={w},{h}',
               '--virtual-time-budget=2000', f'--screenshot={out_abs}', 'file:///' + page.replace('\\', '/')]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120, check=False)
        if not os.path.exists(out_abs):
            raise SystemExit(f'браузер не сохранил {out_abs}')
        ww, hh, _ = ph.png_read(out_abs)
        if (ww, hh) != (w, h):
            raise SystemExit(f'{out_abs}: {ww}×{hh} вместо {w}×{h}')
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def svg_text(path, strip=()):
    """SVG как текст; strip — номера <path> (с 0), которые убрать (знак ®)."""
    import re
    s = open(path, encoding='utf-8').read()
    if not strip:
        return s
    elems = list(re.finditer(r'<path\b[^>]*?(?:/>|>.*?</path>)', s, re.S))
    out, pos = [], 0
    for i, m in enumerate(elems):
        if i in strip:
            out.append(s[pos:m.start()])
            pos = m.end()
    out.append(s[pos:])
    return ''.join(out)


def data_uri(svg):
    import base64
    return 'data:image/svg+xml;base64,' + base64.b64encode(svg.encode('utf-8')).decode('ascii')


# ---------------------------------------------------------------- сборка своих логотипов

def _svg_viewbox(svg):
    import re
    m = re.search(r'viewBox="([-\d.]+)[ ,]+([-\d.]+)[ ,]+([-\d.]+)[ ,]+([-\d.]+)"', svg)
    return tuple(float(x) for x in m.groups())


def _place(spec, cw, ch, cx, cy, scale_fit=1.0):
    """Позиция и размер <img> всего viewBox так, чтобы рамка рисунка вписалась в cw×ch с центром (cx, cy)."""
    vx, vy, vw, vh = spec['viewbox']
    bx, by, bw, bh = spec['box']
    k = min(cw / bw, ch / bh) * scale_fit
    left = cx - (bx - vx + bw / 2) * k
    top = cy - (by - vy + bh / 2) * k
    return left, top, vw * k, vh * k


def page(w, h, body, extra_css=''):
    return (f'<!doctype html><html><head><meta charset="utf-8"><style>'
            f'html,body{{margin:0;padding:0;background:transparent;overflow:hidden;width:{w}px;height:{h}px}}'
            f'.a{{position:absolute}} {extra_css}</style></head><body>{body}</body></html>')


def logo_layers(uri, left, top, w, h, gloss=0.0, shadow=None, extra=''):
    """Логотип + блик (белый градиент по форме логотипа) + тень."""
    filt = f'filter:drop-shadow({shadow});' if shadow else ''
    s = (f'<img class="a" src="{uri}" style="left:{left:.2f}px;top:{top:.2f}px;width:{w:.2f}px;'
         f'height:{h:.2f}px;{filt}{extra}">')
    if gloss:
        mask = (f'-webkit-mask-image:url({uri});mask-image:url({uri});-webkit-mask-size:100% 100%;'
                f'mask-size:100% 100%;-webkit-mask-repeat:no-repeat;mask-repeat:no-repeat;')
        s += (f'<div class="a" style="left:{left:.2f}px;top:{top:.2f}px;width:{w:.2f}px;height:{h:.2f}px;'
              f'{mask}background:linear-gradient(180deg, rgba(255,255,255,{gloss:.2f}) 0%, '
              f'rgba(255,255,255,{gloss * 0.45:.2f}) 46%, rgba(255,255,255,0) 50%, rgba(0,0,0,{gloss * 0.35:.2f}) 100%);"></div>')
    return s


def html_for(kind, spec, uri):
    """Разметка картинки каждого набора (кадр — по замерам оригиналов EA, docs/logos-arenas.md)."""
    c1, c2 = spec['colors'][0], spec['colors'][1]
    if kind == 't':        # 256×256: логотип в рамке ~190×196, тень и блик
        l, t, w, h = _place(spec, 188, 196, 128, 128)
        return 256, 256, page(256, 256, logo_layers(uri, l, t, w, h, gloss=0.22, shadow='0 2px 3px rgba(0,0,0,0.75)'))
    if kind == 'd':        # 128×128: рамка ~108×100
        l, t, w, h = _place(spec, 108, 100, 64, 64)
        return 128, 128, page(128, 128, logo_layers(uri, l, t, w, h, gloss=0.22, shadow='0 1px 2px rgba(0,0,0,0.75)'))
    if kind == 'r':        # 256×512: логотип как t (центр y=150) + отражение снизу
        l, t, w, h = _place(spec, 182, 176, 128, 150)
        bx, by, bw, bh = spec['box']
        vx, vy, vw, vh = spec['viewbox']
        k = w / vw
        bottom = t + (by - vy + bh) * k                 # низ рисунка
        top2 = 2 * bottom - (t + h) + 6                 # зеркальная копия под ним (отступ 6)
        refl = (f'<div class="a" style="left:0;top:{bottom + 6:.2f}px;width:256px;height:{512 - bottom - 6:.2f}px;'
                f'overflow:hidden;-webkit-mask-image:linear-gradient(180deg,rgba(0,0,0,0.26) 0px,rgba(0,0,0,0) 64px);'
                f'mask-image:linear-gradient(180deg,rgba(0,0,0,0.26) 0px,rgba(0,0,0,0) 64px);">'
                f'<img class="a" src="{uri}" style="left:{l:.2f}px;top:{top2 - bottom - 6:.2f}px;width:{w:.2f}px;'
                f'height:{h:.2f}px;transform:scaleY(-1);"></div>')
        return 256, 512, page(256, 512, refl + logo_layers(uri, l, t, w, h, gloss=0.22, shadow='0 2px 3px rgba(0,0,0,0.75)'))
    if kind == 's':        # 128×64: «таблетка» 114×46 со скруглением, заливка цветом команды, крупный план
        zx, zy, zk = spec.get('small_focus', (0.5, 0.5, 1.9))
        vx, vy, vw, vh = spec['viewbox']
        bx, by, bw, bh = spec['box']
        k = 46 * zk / bh
        w, h = vw * k, vh * k
        l = 64 - (bx - vx + bw * zx) * k
        t = 32 - (by - vy + bh * zy) * k
        pill = ('left:7px;top:9px;width:114px;height:46px;border-radius:9px;overflow:hidden;'
                f'background:linear-gradient(180deg,{c2} 0%,{c1} 100%);'
                'box-shadow:0 0 1px 1px rgba(0,0,0,0.55);')
        inner = (f'<img class="a" src="{uri}" style="left:{l - 7:.2f}px;top:{t - 9:.2f}px;width:{w:.2f}px;height:{h:.2f}px;">'
                 '<div class="a" style="left:0;top:0;width:114px;height:46px;'
                 'background:linear-gradient(180deg,rgba(255,255,255,0.30) 0%,rgba(255,255,255,0.12) 49%,'
                 'rgba(0,0,0,0.10) 51%,rgba(0,0,0,0.28) 100%);box-shadow:inset 0 0 6px rgba(0,0,0,0.55);"></div>')
        return 128, 64, page(128, 64, f'<div class="a" style="{pill}">{inner}</div>')
    if kind == 'c':        # сцена 98×86: крупнее рамки, растушёвка краёв
        l, t, w, h = _place(spec, 96, 84, 49, 43, scale_fit=spec.get('calendar_zoom', 1.45))
        mask = ('-webkit-mask-image:radial-gradient(ellipse 47px 40px at 49px 43px,#000 72%,transparent 100%);'
                'mask-image:radial-gradient(ellipse 47px 40px at 49px 43px,#000 72%,transparent 100%);')
        body = (f'<div class="a" style="left:0;top:0;width:98px;height:86px;overflow:hidden;{mask}">'
                + logo_layers(uri, l, t, w, h, gloss=0.18) + '</div>')
        return 128, 128, page(128, 128, body)
    if kind == 'w':        # 256×256: крупный план (×1.6) с мягкими краями
        zx, zy, zk = spec.get('wide_focus', (0.5, 0.5, 1.6))
        vx, vy, vw, vh = spec['viewbox']
        bx, by, bw, bh = spec['box']
        k = 220 * zk / max(bw, bh)
        w, h = vw * k, vh * k
        l = 128 - (bx - vx + bw * zx) * k
        t = 128 - (by - vy + bh * zy) * k
        mask = ('-webkit-mask-image:radial-gradient(circle 112px at 128px 128px,#000 55%,transparent 100%);'
                'mask-image:radial-gradient(circle 112px at 128px 128px,#000 55%,transparent 100%);')
        body = (f'<div class="a" style="left:0;top:0;width:256px;height:256px;{mask}">'
                + logo_layers(uri, l, t, w, h, gloss=0.15) + '</div>')
        return 256, 256, page(256, 256, body)
    if kind == 'banner':   # 512×512 DXT3: логотип на прозрачном (как banner_93 у EA)
        l, t, w, h = _place(spec, 440, 440, 256, 256)
        return 512, 512, page(512, 512, logo_layers(uri, l, t, w, h))
    if kind == 'spot':     # 256×256 DXT5: логотип для проекции прожекторами на лёд (как spotlight/texlib_0)
        l, t, w, h = _place(spec, 232, 200, 128, 128)
        return 256, 256, page(256, 256, logo_layers(uri, l, t, w, h))
    raise ValueError(kind)


def html_for_ea(kind, spec, uri, scale=1.0):
    """Как html_for, но под замеры EA: t/d/r — с поправкой размера scale (подбирается по SIZE_TARGET в
    build(..., ea_fit=True)), r — тем же кадром, что t; c и w — без CSS-маски (растушёвка — маской EA,
    EA_MASKS, после рендера)."""
    c1, c2 = spec['colors'][0], spec['colors'][1]
    if kind == 't':        # 256×256: логотип по центру, тень и блик
        l, t, w, h = _place(spec, 188, 196, 128, 128, scale_fit=scale)
        return 256, 256, page(256, 256, logo_layers(uri, l, t, w, h, gloss=0.22, shadow='0 2px 3px rgba(0,0,0,0.75)'))
    if kind == 'd':        # 128×128
        l, t, w, h = _place(spec, 108, 100, 64, 64, scale_fit=scale)
        return 128, 128, page(128, 128, logo_layers(uri, l, t, w, h, gloss=0.22, shadow='0 1px 2px rgba(0,0,0,0.75)'))
    if kind == 'r':        # 256×512: логотип как t (тот же размер, центр y=150) + отражение снизу
        l, t, w, h = _place(spec, 188, 196, 128, 150, scale_fit=scale)
        bx, by, bw, bh = spec['box']
        vx, vy, vw, vh = spec['viewbox']
        k = w / vw
        bottom = t + (by - vy + bh) * k                 # низ рисунка
        top2 = 2 * bottom - (t + h) + 6                 # зеркальная копия под ним (отступ 6)
        refl = (f'<div class="a" style="left:0;top:{bottom + 6:.2f}px;width:256px;height:{512 - bottom - 6:.2f}px;'
                f'overflow:hidden;-webkit-mask-image:linear-gradient(180deg,rgba(0,0,0,0.26) 0px,rgba(0,0,0,0) 64px);'
                f'mask-image:linear-gradient(180deg,rgba(0,0,0,0.26) 0px,rgba(0,0,0,0) 64px);">'
                f'<img class="a" src="{uri}" style="left:{l:.2f}px;top:{top2 - bottom - 6:.2f}px;width:{w:.2f}px;'
                f'height:{h:.2f}px;transform:scaleY(-1);"></div>')
        return 256, 512, page(256, 512, refl + logo_layers(uri, l, t, w, h, gloss=0.22, shadow='0 2px 3px rgba(0,0,0,0.75)'))
    if kind == 's':        # 128×64: «таблетка» 114×46 со скруглением, заливка цветом команды, крупный план
        zx, zy, zk = spec.get('small_focus', (0.5, 0.5, 1.9))
        vx, vy, vw, vh = spec['viewbox']
        bx, by, bw, bh = spec['box']
        k = 46 * zk / bh
        w, h = vw * k, vh * k
        l = 64 - (bx - vx + bw * zx) * k
        t = 32 - (by - vy + bh * zy) * k
        pill = ('left:7px;top:9px;width:114px;height:46px;border-radius:9px;overflow:hidden;'
                f'background:linear-gradient(180deg,{c2} 0%,{c1} 100%);'
                'box-shadow:0 0 1px 1px rgba(0,0,0,0.55);')
        inner = (f'<img class="a" src="{uri}" style="left:{l - 7:.2f}px;top:{t - 9:.2f}px;width:{w:.2f}px;height:{h:.2f}px;">'
                 '<div class="a" style="left:0;top:0;width:114px;height:46px;'
                 'background:linear-gradient(180deg,rgba(255,255,255,0.30) 0%,rgba(255,255,255,0.12) 49%,'
                 'rgba(0,0,0,0.10) 51%,rgba(0,0,0,0.28) 100%);box-shadow:inset 0 0 6px rgba(0,0,0,0.55);"></div>')
        return 128, 64, page(128, 64, f'<div class="a" style="{pill}">{inner}</div>')
    if kind == 'c':        # сцена 98×86: крупный план; растушёвка — маской EA (EA_MASKS) после рендера
        l, t, w, h = _place(spec, 96, 84, 49, 43, scale_fit=spec.get('calendar_zoom', 1.45))
        body = (f'<div class="a" style="left:0;top:0;width:98px;height:86px;overflow:hidden;">'
                + logo_layers(uri, l, t, w, h, gloss=0.18) + '</div>')
        return 128, 128, page(128, 128, body)
    if kind == 'w':        # 256×256: крупный план (×1.6) с мягкими краями
        zx, zy, zk = spec.get('wide_focus', (0.5, 0.5, 1.6))
        vx, vy, vw, vh = spec['viewbox']
        bx, by, bw, bh = spec['box']
        k = 220 * zk / max(bw, bh)
        w, h = vw * k, vh * k
        l = 128 - (bx - vx + bw * zx) * k
        t = 128 - (by - vy + bh * zy) * k
        body = (f'<div class="a" style="left:0;top:0;width:256px;height:256px;overflow:hidden;">'
                + logo_layers(uri, l, t, w, h, gloss=0.15) + '</div>')    # маска — EA_MASKS после рендера
        return 256, 256, page(256, 256, body)
    if kind == 'banner':   # 512×512 DXT3: логотип на прозрачном (как banner_93 у EA)
        l, t, w, h = _place(spec, 440, 440, 256, 256)
        return 512, 512, page(512, 512, logo_layers(uri, l, t, w, h))
    if kind == 'spot':     # 256×256 DXT5: логотип для проекции прожекторами на лёд (как spotlight/texlib_0)
        l, t, w, h = _place(spec, 232, 200, 128, 128)
        return 256, 256, page(256, 256, logo_layers(uri, l, t, w, h))
    raise ValueError(kind)


def logo_only(spec, size, box, cx, cy, tmpdir, name):
    """Плоский логотип (без тени и блика) в квадрате size×size → RGBA."""
    l, t, w, h = _place(spec, box, box, cx, cy)
    png = os.path.join(tmpdir, name)
    render_html(page(size, size, logo_layers(spec['_uri'], l, t, w, h)), png, size, size)
    return ph.png_read(png)[2]


def max_radius(rgba, w, h, cx, cy, thr=8):
    r2 = 0
    for y in range(h):
        row = y * w
        for x in range(w):
            if rgba[(row + x) * 4 + 3] > thr:
                d = (x + 0.5 - cx) ** 2 + (y + 0.5 - cy) ** 2
                if d > r2:
                    r2 = d
    return math.sqrt(r2)


def over(dst, src, w, h):
    """src поверх dst (оба RGBA w×h, прямая альфа)."""
    out = bytearray(dst)
    for i in range(0, w * h * 4, 4):
        a = src[i + 3]
        if not a:
            continue
        da = out[i + 3]
        oa = a + da * (255 - a) // 255
        for c in range(3):
            out[i + c] = (src[i + c] * a + out[i + c] * da * (255 - a) // 255) // max(1, oa)
        out[i + 3] = oa
    return bytes(out)


# Центр льда — по замерам centerlogo_*_cm у EA (все одинаковы): диск льда (231, 233, 231) радиуса 388 с
# центром (512, 512), синее кольцо (0, 56, 165) по радиусу ~381–385, по x 494…529 — прозрачная полоса
# под красную линию (её рисует ice_cline_<centerline>). Логотип — плоский, в круге радиуса ~350.
CENTER = {'size': 1024, 'r_disk': 388.0, 'ring': (380.5, 385.5), 'ice': (231, 233, 231), 'blue': (0, 56, 165),
          'stripe': (494, 530), 'r_logo': 350.0}


def center_rgba(spec, tmpdir):
    c = CENTER
    n = c['size']
    cx = cy = n / 2
    box = spec.get('center_box', 640)
    logo = logo_only(spec, n, box, cx, cy, tmpdir, 'center_logo.png')
    r = max_radius(logo, n, n, cx, cy)
    if r > c['r_logo']:                                     # не залезать на кольцо
        box = box * c['r_logo'] / r
        logo = logo_only(spec, n, box, cx, cy, tmpdir, 'center_logo2.png')
    base = bytearray(n * n * 4)
    r0, (r1, r2) = c['r_disk'], c['ring']
    for y in range(n):
        for x in range(n):
            d = math.hypot(x + 0.5 - cx, y + 0.5 - cy)
            if d >= r0 + 0.5:
                continue
            o = (y * n + x) * 4
            # кольцо со сглаживанием по краям
            k = max(0.0, min(1.0, d - r1 + 0.5)) * max(0.0, min(1.0, r2 - d + 0.5))
            col = tuple(int(i * (1 - k) + b * k + 0.5) for i, b in zip(c['ice'], c['blue']))
            base[o:o + 4] = bytes(col + (255,))
    out = bytearray(over(bytes(base), logo, n, n))
    s0, s1 = c['stripe']
    for y in range(n):
        for x in range(s0, s1):
            out[(y * n + x) * 4 + 3] = 0                    # полоса под центральную линию
    return bytes(out)


# Шайба — шаблон puck_255_cm (EA SPORTS): верхняя грань — круг с центром (128, 169), надписи по кругу;
# в середине белый «пятак» радиуса ~31 с логотипом EA. Ставим белый круг радиуса 42 (надписи по кругу
# не задеваются) с серой каймой и
# логотип команды в нём; нижняя грань (НХЛ) и бока — как у шаблона.
PUCK = {'template': 'rendering/puck/puck_255_cm.rx2', 'center': (128.0, 169.0), 'r_white': 42.0,
        'r_rim': 44.5, 'rim': (150, 154, 160), 'box': 70}


def puck_rgba(spec, tmpdir):
    tpl = Rw4.load(extracted(PUCK['template']))
    t = tpl.textures[0]
    w, h, base = tpl.decode(t, 0)
    cx, cy = PUCK['center']
    out = bytearray(base)
    for y in range(int(cy - 60), int(cy + 60)):
        for x in range(int(cx - 60), int(cx + 60)):
            d = math.hypot(x + 0.5 - cx, y + 0.5 - cy)
            o = (y * w + x) * 4
            if d < PUCK['r_white']:
                out[o:o + 3] = b'\xff\xff\xff'
            elif d < PUCK['r_rim']:
                out[o:o + 3] = bytes(PUCK['rim'])
    logo = logo_only(spec, 256, PUCK['box'], 128, 128, tmpdir, 'puck_logo.png')
    # логотип 256×256 → в точку (cx, cy) текстуры
    dy = int(cy - 128)
    lay = bytearray(w * h * 4)
    for y in range(256):
        ty = y + dy
        if 0 <= ty < h:
            lay[ty * w * 4:(ty * w + 256) * 4] = logo[y * 256 * 4:(y + 1) * 256 * 4]
    res = bytearray(over(bytes(out), bytes(lay), w, h))
    for i in range(3, len(res), 4):
        res[i] = 255                                         # DXT1, непрозрачная
    return bytes(res)


# Шайба. Верхняя грань — круг с центром (127.5, 172) (кольцо грани — радиус ~89 у НХЛ, ~115 у АХЛ),
# нижняя грань и бока — как у шаблона.
#  * НХЛ — шаблон puck_255_cm (EA SPORTS): надписи «National Hockey League / Official Game Puck» по кругу,
#    в середине белый «пятак» радиуса ~36 с логотипом EA. Ставим белый круг радиуса 42 (надписи не
#    задеваются) с серой каймой и логотип команды в нём; низ — логотип НХЛ.
#  * АХЛ — шаблон puck_150_cm: тёмная грань (34, 38, 37) с рельефным ободком на радиусе 112–118,
#    логотип команды прямо на грани (до радиуса ~95); низ — логотип АХЛ. Грань до радиуса 107
#    закрашивается её цветом, логотип вписывается в радиус 94.
PUCKS = {
    'nhl': {'template': 'rendering/puck/puck_255_cm.rx2', 'center': (127.5, 172.0), 'r_white': 42.0,
            'r_rim': 44.5, 'rim': (150, 154, 160), 'r_logo': 38.0},
    'ahl': {'template': 'rendering/puck/puck_150_cm.rx2', 'center': (127.5, 172.0), 'r_clear': 107.0,
            'face': (34, 38, 37), 'r_logo': 94.0},
}


def fit_logo(spec, size, r_logo, tmpdir, name):
    """Плоский логотип в квадрате size×size с центром посередине: наибольший радиус рисунка = r_logo."""
    c = size / 2
    box = 2 * r_logo
    logo = logo_only(spec, size, box, c, c, tmpdir, name)
    r = max_radius(logo, size, size, c, c)
    if r > 0:
        logo = logo_only(spec, size, box * r_logo / r, c, c, tmpdir, name)
    return logo


def puck_rgba_league(spec, tmpdir):
    """Шайба по spec["league"] (nhl | ahl, PUCKS): логотип по центру грани (127.5, 172), вписан по
    наибольшему радиусу. Прежняя puck_rgba — НХЛ, центр (128, 169), рамка 70×70."""
    style = spec.get('league', 'nhl')
    P = PUCKS[style]
    tpl = Rw4.load(extracted(P['template']))
    t = tpl.textures[0]
    w, h, base = tpl.decode(t, 0)
    cx, cy = P['center']
    out = bytearray(base)
    reach = int(P.get('r_clear', P.get('r_rim', 60))) + 3
    for y in range(int(cy) - reach, int(cy) + reach + 1):
        for x in range(int(cx) - reach, int(cx) + reach + 1):
            d = math.hypot(x + 0.5 - cx, y + 0.5 - cy)
            o = (y * w + x) * 4
            if style == 'nhl':
                if d < P['r_white']:
                    out[o:o + 3] = bytes((255, 255, 255))
                elif d < P['r_rim']:
                    out[o:o + 3] = bytes(P['rim'])
            else:
                rc = P['r_clear']
                k = 1.0 if d <= rc - 1 else max(0.0, (rc + 1 - d) / 2)   # мягкий край
                if k:
                    for c in range(3):
                        out[o + c] = int(P['face'][c] * k + out[o + c] * (1 - k) + 0.5)
    logo = fit_logo(spec, 256, P['r_logo'], tmpdir, 'puck_logo.png')
    # логотип 256×256 (центр 128, 128) → в точку (cx, cy) текстуры
    dx, dy = int(round(cx - 128)), int(round(cy - 128))
    lay = bytearray(w * h * 4)
    for y in range(256):
        ty = y + dy
        if not 0 <= ty < h:
            continue
        for x in range(256):
            tx = x + dx
            if 0 <= tx < w:
                lay[(ty * w + tx) * 4:(ty * w + tx) * 4 + 4] = logo[(y * 256 + x) * 4:(y * 256 + x) * 4 + 4]
    res = bytearray(over(bytes(out), bytes(lay), w, h))
    for i in range(3, len(res), 4):
        res[i] = 255                                         # DXT1, непрозрачная
    return bytes(res)


def measure_box(svg_uri, viewbox, tmpdir):
    """Рамка рисунка в единицах viewBox: рендер в 2× и границы альфы."""
    vx, vy, vw, vh = viewbox
    k = 2.0
    W, H = int(vw * k), int(vh * k)
    png = os.path.join(tmpdir, 'measure.png')
    render_html(page(W, H, f'<img class="a" src="{svg_uri}" style="left:0;top:0;width:{W}px;height:{H}px">'), png, W, H)
    _, _, px = ph.png_read(png)
    xs0, ys0, xs1, ys1 = W, H, -1, -1
    for y in range(H):
        row = px[y * W * 4:(y + 1) * W * 4]
        alpha = row[3::4]
        if max(alpha) <= 8:
            continue
        first = next(i for i, a in enumerate(alpha) if a > 8)
        last = W - 1 - next(i for i, a in enumerate(reversed(alpha)) if a > 8)
        xs0, xs1 = min(xs0, first), max(xs1, last)
        ys0, ys1 = min(ys0, y), max(ys1, y)
    return [vx + xs0 / k, vy + ys0 / k, (xs1 - xs0 + 1) / k, (ys1 - ys0 + 1) / k]


# Размеры по замеру оригиналов EA 0…29 (непрозрачная часть, альфа > 128): t — рамка w 144…191 (медиана 171),
# h 98…182 (150), площадь 8 493…23 997 (17 111); d — w 66…105 (87), h 50…88 (78,5), площадь 2 404…6 006 (4 267).
# Свой логотип масштабируется к медианной площади, но не выше max_h и не шире max_w.
SIZE_TARGET = {'t': dict(area=17111, max_w=191, max_h=170), 'd': dict(area=4267, max_w=105, max_h=86)}
# Растушёвка c и w — альфа оригиналов EA, где логотип закрывает всю сцену (у всех одинаковая): w — круг с
# центром (125, 128), 50 % на радиусе ~67, ноль к ~124; c — скруглённый прямоугольник 84×73 от (7, 6) с
# мягким краем ~14 px. Маска = поточечный максимум альфы этих файлов.
EA_MASKS = {'w': ('teamlogoswide', 'w', (2, 4, 5)), 'c': ('teamlogoscalendar', 'c', (1, 3, 11))}
_MASK_CACHE = {}


def ea_mask(kind, game=None):
    if kind not in _MASK_CACHE:
        folder, letter, nums = EA_MASKS[kind]
        best = None
        for n in nums:
            lg = UiLogo.load(extracted(f'fe/ion/artassets/{folder}/{letter}{n}.big', game))
            w, h, rgba = lg.decode()
            a = rgba[3::4]
            best = bytearray(a) if best is None else bytearray(max(x, y) for x, y in zip(best, a))
        _MASK_CACHE[kind] = (w, h, bytes(best))
    return _MASK_CACHE[kind]


def apply_mask(rgba, w, h, mask):
    mw, mh, m = mask
    if (mw, mh) != (w, h):
        raise ValueError(f'маска {mw}×{mh}, картинка {w}×{h}')
    out = bytearray(rgba)
    for i in range(w * h):
        a = out[i * 4 + 3] * m[i] // 255
        out[i * 4 + 3] = a
        if not a:
            out[i * 4:i * 4 + 3] = bytes(3)
    return bytes(out)


def alpha_stats(rgba, w, h, thr=128):
    """Рамка (w, h) и площадь непрозрачной части (альфа > thr) — как в замерах оригиналов."""
    xs0, ys0, xs1, ys1, area = w, h, -1, -1, 0
    for y in range(h):
        for x in range(w):
            if rgba[(y * w + x) * 4 + 3] > thr:
                area += 1
                xs0, xs1 = min(xs0, x), max(xs1, x)
                ys0, ys1 = min(ys0, y), max(ys1, y)
    if xs1 < 0:
        return 0, 0, 0
    return xs1 - xs0 + 1, ys1 - ys0 + 1, area


UI_SETS = {   # набор: папка, буква
    't': ('teamlogos', 't'), 's': ('teamlogossmall', 's'), 'd': ('teamlogosdynasty', 'd'),
    'c': ('teamlogoscalendar', 'c'), 'w': ('teamlogoswide', 'w'), 'r': ('teamlogosreflection', 'r'),
}
RX_SETS = {   # набор: путь (формат номера), шаблон из архива (заголовки, раскладка; пиксели — свои),
    #             номер шаблона (имя растра внутри переписывается на свой), поле SPEC с номером
    'center': ('rendering/icesurface/centerlogo_{}_cm.rx2', 'rendering/icesurface/centerlogo_93_cm.rx2', 93, 'artid'),
    'banner': ('rendering/banner/banner_{}_cm.rx2', 'rendering/banner/banner_93_cm.rx2', 93, 'artid'),
    'puck': ('rendering/puck/puck_{}_cm.rx2', 'rendering/puck/puck_93_cm.rx2', 93, 'artid'),
    'spot': ('rendering/spotlight/texlib_{}.rx2', 'rendering/spotlight/texlib_33.rx2', 33, 'spotlight'),
}
# Шаблоны контейнеров по числу цифр своего номера (имя растра внутри переписывается на месте — длина
# номера должна совпасть). 3-значных одиночных прожекторов у EA нет.
RX_TEMPLATES = {'center': {2: 93, 3: 150}, 'banner': {2: 93, 3: 150}, 'puck': {2: 93, 3: 150}, 'spot': {2: 33}}


def rx_template(kind, num):
    """Шаблон контейнера для своего номера: (путь в архиве, номер шаблона) с тем же числом цифр."""
    pattern = RX_SETS[kind][0]
    by_digits = RX_TEMPLATES[kind]
    digits = len(str(num))
    if digits not in by_digits:
        raise SystemExit(f'{kind}: нет шаблона для {digits}-значного номера {num}')
    n = by_digits[digits]
    return pattern.format(n), n


def extracted(rel, game=None):
    g = game or ph.game_dir()
    root = 'cacherender' if rel.startswith('rendering/') else 'cache'
    return os.path.join(g, 'extracted', 'big', root, *rel.split('/'))


def ui_template(kind, game=None):
    folder, letter = UI_SETS[kind]
    return extracted(f'fe/ion/artassets/{folder}/{letter}0.big', game)


def build(spec_path, outdir, only=None, preview=None, ea_fit=False):
    """SPEC.json: artid, svg (путь от SPEC), strip_paths (номера <path> — знак ®), colors [низ, верх
    «таблетки»], small_focus / wide_focus [доля x, доля y, увеличение], center_box (px, по умолчанию 640),
    calendar_zoom (по умолчанию 1.45), spotlight (номер прожектора; нет — набор spot пропускается),
    league: nhl | ahl (наборы по умолчанию: у АХЛ без r и spot; шаблон шайбы — при ea_fit).
    Рамка рисунка (box) считается сама, если её нет.
    ea_fit=True — размеры t/d/r по замерам EA (SIZE_TARGET), растушёвка c/w — маской EA (EA_MASKS), шайба —
    puck_rgba_league (центр грани, лига); по умолчанию — прежняя сборка (html_for, puck_rgba)."""
    spec = json.load(open(spec_path, encoding='utf-8'))
    base = os.path.dirname(os.path.abspath(spec_path))
    svg = svg_text(os.path.join(base, spec['svg']), tuple(spec.get('strip_paths', ())))
    spec['viewbox'] = _svg_viewbox(svg)
    uri = spec['_uri'] = data_uri(svg)
    artid = int(spec['artid'])
    if only:
        kinds = only
    elif spec.get('league', 'nhl') == 'ahl':          # у клубов АХЛ нет r-набора, прожектор и туннель общие (34)
        kinds = ['t', 's', 'd', 'c', 'w', 'center', 'puck', 'banner']
    else:
        kinds = ['t', 's', 'd', 'c', 'w', 'r', 'center', 'puck', 'banner', 'spot']
    tmp = tempfile.mkdtemp(prefix='teamart_b_')
    made = []
    scales = {}
    try:
        if 'box' not in spec:
            spec['box'] = measure_box(uri, spec['viewbox'], tmp)
            print(f'рамка рисунка: {", ".join(f"{v:.1f}" for v in spec["box"])} (viewBox {spec["viewbox"]})')
        for kind in kinds:
            if kind in UI_SETS:
                folder, letter = UI_SETS[kind]
                tpl = UiLogo.load(ui_template(kind))
                base = 't' if kind == 'r' else kind
                scale = 1.0
                if ea_fit and base in SIZE_TARGET:
                    if base not in scales:
                        tg = SIZE_TARGET[base]
                        for _ in range(4):              # рендер → замер → поправка (тень добавляет пару px)
                            W, H, html = html_for_ea(base, spec, uri, scale)
                            png = os.path.join(tmp, f'{base}_fit.png')
                            render_html(html, png, W, H)
                            bw, bh, area = alpha_stats(ph.png_read(png)[2], W, H)
                            f = min(math.sqrt(tg['area'] / area), tg['max_h'] / bh, tg['max_w'] / bw)
                            if 0.998 <= f <= 1.01:          # не крупнее целей, мельче — не больше чем на 1 %
                                break
                            scale *= f
                        scales[base] = scale
                        print(f'{base}: масштаб {scale:.3f} (рамка {bw}×{bh}, площадь {area})')
                    scale = scales[base]
                W, H, html = html_for_ea(kind, spec, uri, scale) if ea_fit else html_for(kind, spec, uri)
                png = os.path.join(tmp, f'{kind}.png')
                render_html(html, png, W, H)
                _, _, rgba = ph.png_read(png)
                tw, th = tpl.fetch.width, tpl.fetch.height
                if ea_fit and kind in EA_MASKS:
                    if (W, H) != (tw, th):
                        rgba, W, H = ph.place(rgba, W, H, tw, th), tw, th
                    rgba = apply_mask(rgba, W, H, ea_mask(kind))
                if (W, H) != (tw, th):
                    rgba = ph.place(rgba, W, H, tw, th)
                data = tpl.build(rgba, 'md5')
                rel = f'fe/ion/artassets/{folder}/{letter}{artid}.big'
            else:
                pattern, _, _, key = RX_SETS[kind]
                if key not in spec:
                    print(f'{kind}: в SPEC нет «{key}» — пропуск')
                    continue
                num = int(spec[key])
                tpl_rel, tpl_num = rx_template(kind, num)
                tpl = Rw4.load(extracted(tpl_rel))
                t = tpl.textures[0]
                if kind == 'puck':
                    rgba = puck_rgba_league(spec, tmp) if ea_fit else puck_rgba(spec, tmp)
                    W, H = t.fetch.width, t.fetch.height
                elif kind == 'center':
                    rgba = center_rgba(spec, tmp)
                    W, H = t.fetch.width, t.fetch.height
                else:
                    W, H, html = html_for_ea(kind, spec, uri) if ea_fit else html_for(kind, spec, uri)
                    png = os.path.join(tmp, f'{kind}.png')
                    render_html(html, png, W, H)
                    _, _, rgba = ph.png_read(png)
                tpl.replace(t, mip_chain(rgba, W, H, len(t.layout.levels)))
                tpl.rename(tpl_num, num)
                data = tpl.bytes()
                rel = pattern.format(num)
            out = os.path.join(outdir, *rel.split('/'))
            os.makedirs(os.path.dirname(out), exist_ok=True)
            open(out, 'wb').write(data)
            made.append((rel, len(data)))
            print(f'{rel}: {len(data)} байт')
            if preview:
                obj = load_any(out)
                if isinstance(obj, UiLogo):
                    w, h, dec = obj.decode()
                    sw, sh = obj.stage
                    ph.png_write(os.path.join(preview, f'{kind}{artid}.png'), sw, sh, ph.crop(dec, w, h, sw, sh))
                else:
                    t = obj.textures[0]
                    w, h, dec = obj.decode(t, 0)
                    ph.png_write(os.path.join(preview, f'{kind}{artid}.png'), w, h, dec)
                    w, h, dec = obj.decode(t, 3)
                    ph.png_write(os.path.join(preview, f'{kind}{artid}_mip3.png'), w, h, dec)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return made


# ---------------------------------------------------------------- копия формы под другой номер

# Файлы, которые игра ищет по exhibitionteams.artid команды (а не по stockteamjerseys.teamartid):
# style и variant — из выбранного комплекта (stockteamjerseys.style / variant). Архив — где лежит у EA.
UNIFORM_SETS = [
    ('nocacherender', 'rendering/jersey/texlib_{s}_{a}_{v}.rx2'),
    ('nocacherender', 'rendering/jersey/name_{s}_{a}_{v}_cm.rx2'),
    ('cacherender', 'rendering/pant/texlib_{s}_{a}_{v}.rx2'),
    ('cacherender', 'rendering/sock/sock_{s}_{a}_{v}_cm.rx2'),
    ('cacherender', 'rendering/logo/texlib_{a}_{s}_{v}.rx2'),
    ('cache', 'fe/ion/artassets/jerseys/jersey_{s}_{a}_{v}.big'),
]


def alias_uniforms(src, dst, outdir, game=None):
    """Копии всех файлов формы команды с artid src под номер dst (имена растров внутри — тоже на dst).
    Номера с одинаковым числом цифр (имена растров переписываются на месте)."""
    import re
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                    'ref', 'nhl-legacy-recomp', 'docs', 'nhl12-decomp-reference', 'tools'))
    from pathlib import Path
    import unpack_big
    import unchunk
    if len(str(src)) != len(str(dst)):
        raise SystemExit('номера должны быть одной длины (имена растров внутри файлов)')
    g = game or ph.game_dir()
    made = []
    for arc in sorted({a for a, _ in UNIFORM_SETS}):
        path = os.path.join(g, 'extracted', 'disc', arc + '.big')
        big = unpack_big.parse_bigeb(Path(path))
        pats = [(re.compile('^' + re.escape(p).replace(r'\{s\}', r'(\d+)').replace(r'\{v\}', r'(\d+)')
                            .replace(r'\{a\}', str(src)) + '$'), p) for a2, p in UNIFORM_SETS if a2 == arc]
        with open(path, 'rb') as f:
            for e in big.entries:
                for rx, p in pats:
                    m = rx.match(e.path)
                    if not m:
                        continue
                    f.seek(e.offset)
                    blob = f.read(e.stored_size)
                    if e.is_packed:
                        blob = unpack_big.decompress_packed_member(blob, e.unpacked_size)
                    if blob[:8] in (b'chunklzx', b'chunkzip'):
                        blob = unchunk.unchunk(blob)
                    renamed = []
                    if blob[:8] == RW4_MAGIC:
                        r = Rw4(blob, e.path)
                        renamed = r.rename(src, dst)
                        blob = r.bytes()
                    rel = re.sub(r'(?<![0-9])' + str(src) + r'(?![0-9])', str(dst), e.path.rsplit('/', 1)[1])
                    rel = e.path.rsplit('/', 1)[0] + '/' + rel
                    out = os.path.join(outdir, *rel.split('/'))
                    os.makedirs(os.path.dirname(out), exist_ok=True)
                    open(out, 'wb').write(blob)
                    made.append((rel, len(blob), len(renamed)))
                    print(f'{e.path} → {rel} ({len(blob)} байт, имён растров: {len(renamed)})')
    return made


# ---------------------------------------------------------------- команды

def cmd_info(paths):
    for p in paths:
        obj = load_any(p)
        if isinstance(obj, UiLogo):
            print(f'{p}: BIGF, сцена {obj.stage[0]}×{obj.stage[1]}, текстура {obj.fetch.describe()}')
        else:
            print(f'{p}: RW4, текстур {len(obj.textures)}')
            for t in obj.textures:
                lv = t.layout
                print(f'   {t.name}: {t.fetch.describe()}; буфер 0x{t.size:X} (раскладка 0x{lv.size:X}), '
                      f'уровней {len(lv.levels)}, база 0x{lv.base_size:X}')


def cmd_decode(args):
    path, out = args[0], args[1]
    obj = load_any(path)
    if isinstance(obj, UiLogo):
        w, h, rgba = obj.decode()
        if '--full' not in args:
            sw, sh = obj.stage
            rgba, w, h = ph.crop(rgba, w, h, sw, sh), sw, sh
        ph.png_write(out, w, h, rgba)
        print(f'{path} → {out} ({w}×{h})')
        return
    t = obj.textures[int(args[args.index('--tex') + 1])] if '--tex' in args else obj.textures[0]
    w, h, rgba = obj.decode(t, 0)
    ph.png_write(out, w, h, rgba)
    print(f'{path} [{t.name}] → {out} ({w}×{h})')
    if '--mips' in args:
        d = args[args.index('--mips') + 1]
        for lv in range(1, len(t.layout.levels)):
            w, h, rgba = obj.decode(t, lv)
            ph.png_write(os.path.join(d, f'mip{lv}_{w}x{h}.png'), w, h, rgba)


def cmd_roundtrip(args):
    deep = '--deep' in args
    files = []
    for p in (a for a in args if not a.startswith('--')):
        if os.path.isdir(p):
            files += sorted(os.path.join(dp, f) for dp, _, fs in os.walk(p) for f in fs
                            if f.endswith(('.big', '.rx2')))
        else:
            files.append(p)
    bad = 0
    for path in files:
        try:
            _, res = roundtrip(path, deep)
        except Exception as e:                     # чужой формат (не текстура) — пропуск
            print(f'пропуск {path}: {e}')
            continue
        ok = all(v for k, v in res.items() if not k.endswith(':mips_psnr'))
        bad += not ok
        if len(files) <= 30 or not ok:
            print(f"{'OK ' if ok else 'ОШИБКА'} {path}: {res}")
    print(f'файлов {len(files)}, с ошибками {bad}')
    return bad


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    cmd, args = sys.argv[1], sys.argv[2:]
    if cmd == 'info':
        cmd_info(args)
    elif cmd == 'decode':
        cmd_decode(args)
    elif cmd == 'roundtrip':
        sys.exit(1 if cmd_roundtrip(args) else 0)
    elif cmd == 'render':
        svg, out, w, h = args[0], args[1], int(args[2]), int(args[3])
        strip = ()
        if '--strip' in args:
            strip = tuple(int(x) for x in args[args.index('--strip') + 1].split(','))
        uri = data_uri(svg_text(svg, strip))
        render_html(page(w, h, f'<img class="a" src="{uri}" style="left:0;top:0;width:{w}px;height:{h}px">'), out, w, h)
        print(f'{svg} → {out} ({w}×{h})')
    elif cmd == 'build':
        only = args[args.index('--only') + 1].split(',') if '--only' in args else None
        preview = args[args.index('--preview') + 1] if '--preview' in args else None
        build(args[0], args[1], only, preview, ea_fit='--legacy' not in args)
    elif cmd == 'alias':
        alias_uniforms(int(args[0]), int(args[1]), args[2])
    else:
        sys.exit(__doc__)


if __name__ == '__main__':
    main()
