"""Текстуры файлов игры для редактора: RW4 (.rx2) и картинки интерфейса BIGF/XPR2 (.big) ⇄ картинка Pillow.

Разбор контейнеров — общий с инструментами (teamart: раскладка Xenos и мипы, rw4mesh: секции RW4, playerhead: BIGF и
RefPack, kitpaint: DXT1 с 1-битной альфой). Сжатие и разжатие DXT1/3/5 и DXN (BC5) — Pillow (C, в сотни раз быстрее
кодеков на Python; на чистом Python свитер 1024² с мипами — минуты). Правила мипов — как у kitpaint: вся цепочка, хвост
≤ 16 текселей упакован по Xenos; цвет — уменьшение с премножением альфы; нормали (DXN) — среднее X, Y; DXT5 с
прозрачностью — цвет под прозрачным от соседей (иначе тёмная кайма по краю у шрифтов).

Заголовки, имена растров, форматы и размеры не меняются: меняются только пиксели. Картинка другого размера
подгоняется под размер текстуры (Lanczos) — с предупреждением.
"""
import io
import math
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

from PIL import Image, ImageChops, ImageFilter  # noqa: E402

import teamart as ta  # noqa: E402
import playerhead as ph  # noqa: E402

FMT_8888, FMT_DXT1, FMT_DXT3, FMT_DXT5, FMT_DXN = 6, 18, 19, 20, 0x31
FMT_NAMES = {FMT_8888: '8888', FMT_DXT1: 'DXT1', FMT_DXT3: 'DXT3', FMT_DXT5: 'DXT5', FMT_DXN: 'DXN'}
BCN = {FMT_DXT1: 1, FMT_DXT3: 2, FMT_DXT5: 3, FMT_DXN: 5}
PIXFMT = {FMT_DXT1: 'DXT1', FMT_DXT3: 'DXT3', FMT_DXT5: 'DXT5', FMT_DXN: 'BC5'}
SUPPORTED = set(BCN) | {FMT_8888}

RW4_MAGIC = b'\x89RW4xb2\x00'
T_DATA, T_RASTER, T_NAMES = 0x00010031, 0x00020003, 0x00EC0010


class Raster:
    """Одна текстура файла: имя, размер, формат, уровни; где лежат её байты (буфер и смещение)."""

    def __init__(self, name, fetch, data_off, size, index):
        self.name = name
        self.fetch = fetch
        self.fmt = fetch.fmt
        self.w, self.h = fetch.width, fetch.height
        self.data_off, self.size = data_off, size
        self.index = index
        self.layout = ta.Layout(fetch) if fetch.fmt in ta.BLOCK else None
        self.levels = len(self.layout.levels) if self.layout else 0
        self.ok = self.fmt in SUPPORTED and self.layout is not None and self.layout.size <= size + 4096

    @property
    def fmt_name(self):
        return FMT_NAMES.get(self.fmt, f'0x{self.fmt:02X}')

    def info(self):
        return {'index': self.index, 'name': self.name, 'w': self.w, 'h': self.h, 'fmt': self.fmt_name,
                'levels': self.levels, 'ok': self.ok}


# ---------------------------------------------------------------- контейнеры

class Rw4Textures:
    """Растры контейнера RW4: описание 0x00020003 (константа выборки с +0x1C), буфер — секция номер fetch.base
    (так у форм, голов, арен, экипировки; tools/stadium.py), имена — таблица 0x00EC0010 по номеру секции описания."""

    kind = 'rw4'

    def __init__(self, data, rel=''):
        import rw4mesh as rm
        self.rel = rel
        self.f = f = rm.Rw4File(data, rel)
        self.raw = f.raw
        names = {}
        for s in f.find(T_NAMES):
            o = f.abs_off(s)
            n = struct.unpack_from('>H', self.raw, o + 2)[0]
            for k in range(n):
                ptr, _typ, idx = struct.unpack_from('>3I', self.raw, o + 8 + 12 * k)
                q = self.raw.index(b'\0', ptr)
                names[idx] = bytes(self.raw[ptr:q]).decode('latin1')
        self.rasters = []
        descs = f.find(T_RASTER)
        datas = f.find(T_DATA)
        for i, s in enumerate(descs):
            fe = ta.Fetch(struct.unpack_from('>6I', self.raw, f.abs_off(s) + 0x1C))
            ds = f.sections[fe.base] if fe.base < len(f.sections) else None
            if ds is None or ds.type != T_DATA:
                ds = datas[i] if i < len(datas) and len(datas) == len(descs) else None   # пары «данные → описание»
            if ds is None:
                continue
            self.rasters.append(Raster(names.get(s.index, f'tex{i}'), fe, f.abs_off(ds), ds.size, len(self.rasters)))

    def buffer(self, r):
        return self.raw[r.data_off:r.data_off + r.size]

    def put_buffer(self, r, buf):
        self.raw[r.data_off:r.data_off + r.size] = buf[:r.size]

    def bytes(self):
        return bytes(self.raw)


class _XprTex:
    """Ресурс TX2D внутри XPR2: заголовок D3DTexture 0x34 байта, данные — с адреса базы (в данных XPR2)."""

    def __init__(self, xpr, roff, name):
        self.roff, self.name = roff, name
        d3d = struct.unpack_from('>13I', xpr, 12 + roff)
        self.fetch = ta.Fetch(d3d[7:13])


class BigfTextures:
    """Картинки интерфейса: BIGF → записи (RefPack) → XPR2 (один или несколько TX2D)."""

    kind = 'bigf'

    def __init__(self, data, rel=''):
        self.rel = rel
        self.big = ph.Bigf(bytes(data))
        self.rasters = []
        self._entries = {}          # имя записи → [xpr (bytearray), сжата ли]
        self.stage = None
        for name, blob in self.big.entries:
            if not blob:
                continue
            body, packed = ph.unpack_entry(blob)
            if body[:8] == b'Apt Data' and self.stage is None:
                try:
                    m = struct.unpack_from('>I', body, 0x10)[0]
                    if struct.unpack_from('>II', body, m) == (9, 0x09876543):
                        self.stage = struct.unpack_from('>II', body, m + 0x24)
                except struct.error:
                    pass
            if body[:4] != b'XPR2':
                continue
            xpr = bytearray(body)
            _magic, hsize, dsize, nres = struct.unpack_from('>4sIII', xpr, 0)
            self._entries[name] = [xpr, packed]
            for k in range(nres):
                typ, roff, rsize, noff = struct.unpack_from('>4sIII', xpr, 16 + 16 * k)
                if typ != b'TX2D':
                    continue
                q = xpr.index(b'\0', 12 + noff)
                tname = bytes(xpr[12 + noff:q]).decode('latin1')
                t = _XprTex(xpr, roff, tname)
                base = 12 + hsize + (t.fetch.base << 12)
                size = dsize - (t.fetch.base << 12)
                r = Raster(tname if nres > 1 else name, t.fetch, base, size, len(self.rasters))
                r.entry = name
                self.rasters.append(r)

    def buffer(self, r):
        xpr = self._entries[r.entry][0]
        return xpr[r.data_off:r.data_off + r.size]

    def put_buffer(self, r, buf):
        xpr = self._entries[r.entry][0]
        xpr[r.data_off:r.data_off + r.size] = buf[:r.size]
        self._entries[r.entry].append(True)            # запись изменена

    def bytes(self):
        big = ph.Bigf(self.big.raw)
        for name, e in self._entries.items():
            if len(e) > 2:
                big.put(name, ph.refpack_compress(bytes(e[0])) if e[1] else bytes(e[0]))
        return big.build(None)


def load(data, rel=''):
    if data[:4] == b'BIGF':
        return BigfTextures(data, rel)
    if data[:8] == RW4_MAGIC or data[:8] in (b'chunklzx', b'chunkzip'):
        return Rw4Textures(data, rel)
    raise ValueError(f'{rel}: не RW4 и не BIGF')


# ---------------------------------------------------------------- разжатие

def _blocks(cont, r, lv):
    return r.layout.get_level(cont.buffer(r), lv)


def _pick_level(r, max_side):
    lv = 0
    if max_side:
        while lv + 1 < r.levels and max(r.layout.levels[lv][:2]) > max_side:
            lv += 1
    return lv


def _z_from_xy(im):
    """DXN: R = X, G = Y → B = Z = √(1 − X² − Y²) (таблицами Pillow, без поэлементного Python)."""
    r, g = im.getchannel('R'), im.getchannel('G')
    sq = [min(127, round(((v / 127.5 - 1) ** 2) * 127)) for v in range(256)]
    s = ImageChops.add(r.point(sq), g.point(sq))
    z = s.point([round(math.sqrt(max(0.0, 1 - v / 127)) * 127.5 + 127.5) if v <= 127 else 127 for v in range(256)])
    return Image.merge('RGBA', (r, g, z, Image.new('L', im.size, 255)))


def decode(cont, r, max_side=None):
    """Растр → картинка RGBA (уровень, где большая сторона ≤ max_side; None — базовый)."""
    if not r.ok:
        raise ValueError(f'{r.name}: формат {r.fmt_name} не поддерживается')
    lv = _pick_level(r, max_side)
    w, h = r.layout.levels[lv][:2]
    blocks = _blocks(cont, r, lv)
    if r.fmt == FMT_8888:
        return Image.frombytes('RGBA', (w, h), ta.dxt_decode(FMT_8888, blocks, w, h))
    W, H = max(4, (w + 3) & ~3), max(4, (h + 3) & ~3)
    if r.fmt == FMT_DXN:
        im = Image.frombytes('RGB', (W, H), blocks, 'bcn', 5)
        im = _z_from_xy(im)
    else:
        im = Image.frombytes('RGBA', (W, H), blocks, 'bcn', BCN[r.fmt])
    if (W, H) != (w, h):
        im = im.crop((0, 0, w, h))
    return im


# ---------------------------------------------------------------- сжатие

def _dds_blocks(im, pixfmt):
    b = io.BytesIO()
    im.save(b, 'DDS', pixel_format=pixfmt)
    d = b.getvalue()
    if d[:4] != b'DDS ':
        raise ValueError('Pillow: не DDS')
    off = 128
    if d[84:88] == b'DX10':
        off += 20
    return d[off:]


def _pad4(im):
    w, h = im.size
    W, H = max(4, (w + 3) & ~3), max(4, (h + 3) & ~3)
    if (W, H) == (w, h):
        return im
    out = Image.new(im.mode, (W, H))
    out.paste(im, (0, 0))
    if W > w:
        out.paste(im.crop((w - 1, 0, w, h)).resize((W - w, h)), (w, 0))
    if H > h:
        out.paste(out.crop((0, h - 1, W, h)).resize((W, H - h)), (0, h))
    return out


def encode_blocks(fmt, im):
    """Картинка уровня → линейные блоки (порядок PC)."""
    w, h = im.size
    if fmt == FMT_8888:
        return ta.dxt_encode(FMT_8888, im.convert('RGBA').tobytes(), w, h)
    if fmt == FMT_DXN:
        return _dds_blocks(_pad4(im.convert('RGB')), 'BC5')
    im = im.convert('RGBA')
    if fmt == FMT_DXT1 and im.getchannel('A').getextrema()[0] < 128:
        import kitpaint as kp                             # 1-битная альфа (как font_sm у EA) — кодек kitpaint
        return kp.dxt1_encode_a1(im.tobytes(), w, h)
    pim = _pad4(im)
    if fmt == FMT_DXT1:
        pim = pim.convert('RGB').convert('RGBA')
    return _dds_blocks(pim, PIXFMT[fmt])


def bleed(im):
    """Цвет под полностью прозрачными пикселями — от ближайших видимых (размытие с делением на альфу)."""
    a = im.getchannel('A')
    lo, hi = a.getextrema()
    if lo > 0 or hi == 0:
        return im
    out = im
    for rad in (2, 8, 32, 128):
        pre = out.convert('RGBa')
        bl = pre.filter(ImageFilter.BoxBlur(rad)).convert('RGBA')
        hole = out.getchannel('A').point(lambda v: 255 if v == 0 else 0)
        fill = bl.copy()
        fill.putalpha(0)
        base = out.copy()
        base.paste(fill, (0, 0), hole)
        # где размытие тоже пусто — оставить как было, на следующем радиусе заполнится
        solid = bl.getchannel('A').point(lambda v: 255 if v > 0 else 0)
        mask = ImageChops.multiply(hole, solid)
        out_rgb = Image.composite(base, out, mask)
        out_rgb.putalpha(a)
        out = out_rgb
        if ImageChops.multiply(hole, ImageChops.invert(solid)).getbbox() is None:
            break
    return out


def black_under_clear(im):
    """Под полностью прозрачным — чёрный (как у EA в картинках интерфейса: файл меньше, у портретов есть предел)."""
    a = im.getchannel('A')
    if a.getextrema()[0] > 0:
        return im
    out = Image.new('RGBA', im.size, (0, 0, 0, 0))
    out.paste(im, (0, 0), a.point(lambda v: 255 if v else 0))
    out.putalpha(a)
    return out


def mip_chain(fmt, im, levels, sizes, ui=False):
    """[картинки уровней] нужных размеров sizes[(w, h)…]; ui — картинка интерфейса (BIGF, без мипов)."""
    out = []
    cur = im
    for lv in range(levels):
        w, h = sizes[lv]
        if lv == 0:
            m = cur if cur.size == (w, h) else cur.resize((w, h), Image.LANCZOS)
        elif fmt == FMT_DXN:
            m = out[-1].convert('RGB').resize((w, h), Image.BOX).convert('RGBA')
        else:
            m = out[-1].convert('RGBa').resize((w, h), Image.BOX).convert('RGBA')
        out.append(m)
    if ui and fmt != FMT_DXN:
        out = [black_under_clear(m) for m in out]
    elif fmt == FMT_DXT5:
        out = [bleed(m) for m in out]
    return out


def replace(cont, r, im):
    """Новые пиксели растра из картинки (базовый уровень; мипы считаются). → [предупреждения]."""
    if not r.ok:
        raise ValueError(f'{r.name}: формат {r.fmt_name} не поддерживается')
    notes = []
    im = im.convert('RGBA')
    if im.size != (r.w, r.h):
        notes.append(f'{im.size[0]}×{im.size[1]} → {r.w}×{r.h}')
    sizes = [lvl[:2] for lvl in r.layout.levels]
    chain = mip_chain(r.fmt, im, r.levels, sizes, ui=getattr(cont, 'kind', '') == 'bigf')
    buf = bytearray(r.size)
    for lv, m in enumerate(chain):
        r.layout.put_level(buf, lv, encode_blocks(r.fmt, m))
    cont.put_buffer(r, buf)
    return notes


def png_bytes(im):
    b = io.BytesIO()
    im.save(b, 'PNG', compress_level=3)
    return b.getvalue()


def thumb(cont, r, side=256):
    im = decode(cont, r, max_side=side)
    if max(im.size) > side:
        im.thumbnail((side, side), Image.LANCZOS)
    return im
