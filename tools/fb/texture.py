"""Текстуры Frostbite NHL 24 (PS4) и NHL 27 (PS5): заголовок res «Texture» (тип 0x6BDE20BA, 132 / 184 Б), детайлинг
PS4 GNM и PS5 (плитки 4 КБ), PNG.

Заголовок: u32 mipOffset0, u32 mipOffset1, u32 type, u32 pixelFormat, u32 unk, u16 flags,
u16 width, u16 height, u16 depth, u16 slices, u8 mipCount, u8 firstMip, guid chunkId,
u32 mipSizes[15], u32 chunkSize, u32 nameHash, 16 Б textureGroup.
"""
import struct
import uuid

RES_TEXTURE = 0x6BDE20BA


def parse_header(d):
    """Заголовок Texture: NHL 24 (PS4) — 132 байта, NHL 27 (PS5) — 184: первые 32 байта те же, дальше 8 новых байт,
    GUID чанка @40 в порядке байт как у GUID оглавлений (не bytes_le), mipSizes @56, размер @116, nameHash @120,
    группа @132 (21.10.2026)."""
    (mo0, mo1, ttype, fmt, unk, flags, w, h, depth, slices, mips, first) = struct.unpack_from("<5I5H2B", d, 0)
    if len(d) >= 184:
        chunk = str(uuid.UUID(bytes=bytes(d[40:56])))
        mip_sizes = list(struct.unpack_from("<15I", d, 56))
        chunk_size, name_hash = struct.unpack_from("<2I", d, 116)
        group = bytes(d[132:184]).split(b"\0")[0].decode("ascii", "replace")
    else:
        chunk = str(uuid.UUID(bytes_le=bytes(d[32:48])))
        mip_sizes = list(struct.unpack_from("<15I", d, 48))
        chunk_size, name_hash = struct.unpack_from("<2I", d, 108)
        group = bytes(d[116:132]).split(b"\0")[0].decode("ascii", "replace")
    return {"mip_offsets": (mo0, mo1), "type": ttype, "format": fmt, "unk": unk, "flags": flags,
            "width": w, "height": h, "depth": depth, "slices": slices, "mips": mips, "first_mip": first,
            "chunk": chunk, "mip_sizes": mip_sizes[:max(mips, 1)],
            "chunk_size": chunk_size, "name_hash": name_hash, "group": group, "ps5": len(d) >= 184}


# --- детайлинг PS4 -------------------------------------------------------------------------
import numpy as np

_MORTON = None


def _morton8():
    global _MORTON
    if _MORTON is None:
        xs, ys = [], []
        for i in range(64):
            x = (i & 1) | ((i >> 1) & 2) | ((i >> 2) & 4)
            y = ((i >> 1) & 1) | ((i >> 2) & 2) | ((i >> 3) & 4)
            xs.append(x)
            ys.append(y)
        _MORTON = (np.array(xs), np.array(ys))
    return _MORTON


def detile_1d_thin(data, w_el, h_el, el_bytes):
    """PS4 GNM Thin_1dThin: микротайлы 8×8 элементов (элемент — пиксель или блок BCn) в порядке Мортона,
    тайлы — построчно; ширина/высота выровнены до 8 элементов. -> байты линейного изображения w_el×h_el."""
    pw = (w_el + 7) // 8 * 8
    ph = (h_el + 7) // 8 * 8
    need = pw * ph * el_bytes
    buf = np.frombuffer(bytes(data[:need]).ljust(need, b"\0"), dtype=np.uint8)
    t = buf.reshape(ph // 8, pw // 8, 64, el_bytes)
    mx, my = _morton8()
    out = np.zeros((ph // 8, 8, pw // 8, 8, el_bytes), dtype=np.uint8)
    out[:, my, :, mx, :] = t.transpose(2, 0, 1, 3)
    out = out.reshape(ph, pw, el_bytes)[:h_el, :w_el]
    return out.tobytes()


# --- детайлинг PS5 -------------------------------------------------------------------------
# Найдено 21.10.2026 перебором на дампе NHL 27 (логотип Canucks BC1 512×256, BC3 680×548 и 100×100): плитки 4 КБ,
# по строкам слева направо (число плиток по x — ширина в элементах, выровненная вверх), внутри плитки — биты адреса
# элемента: (биты x, биты y) по порядку младших. XOR-перестановок нет. Мипы в потоке — от меньшего к большему: мип 0 —
# последние mip_sizes[0] байт. 4 байта на элемент (RGBA8) пока не встречались — ошибка, а не мусор.
PS5_TILES = {
    8: (32, 16, (0, 3, 4, 6, 8), (1, 2, 5, 7)),          # BC1, BC4: a0=x0 a1=y0 a2=y1 a3=x1 a4=x2 a5=y2 a6=x3 a7=y3 a8=x4
    16: (16, 16, (2, 3, 5, 7), (0, 1, 4, 6)),            # BC2, BC3, BC5, BC7: a0=y0 a1=y1 a2=x0 a3=x1 a4=y2 a5=x2 …
}
_PS5_MAP = {}


def detile_ps5(data, w_el, h_el, el_bytes):
    """PS5: плитки 4 КБ (PS5_TILES) → байты линейного изображения w_el×h_el."""
    if el_bytes not in PS5_TILES:
        raise ValueError(f"детайлинг PS5 для {el_bytes} байт на элемент не известен (fb/texture.py PS5_TILES)")
    tw, th, xs, ys = PS5_TILES[el_bytes]
    n = tw * th
    if el_bytes not in _PS5_MAP:
        a = np.arange(n)
        xb, yb = np.zeros(n, np.int64), np.zeros(n, np.int64)
        for i, k in enumerate(xs):
            xb |= ((a >> k) & 1) << i
        for i, k in enumerate(ys):
            yb |= ((a >> k) & 1) << i
        _PS5_MAP[el_bytes] = (xb, yb)
    xb, yb = _PS5_MAP[el_bytes]
    tx, ty = -(-w_el // tw), -(-h_el // th)
    need = tx * ty * n * el_bytes
    el = np.frombuffer(bytes(data[:need]).ljust(need, b"\0"), dtype=np.uint8).reshape(ty, tx, n, el_bytes)
    out = np.zeros((ty, th, tx, tw, el_bytes), dtype=np.uint8)
    out[:, yb, :, xb, :] = el.transpose(2, 0, 1, 3)
    return out.reshape(ty * th, tx * tw, el_bytes)[:h_el, :w_el].tobytes()


# --- форматы (Frostbite RenderFormat) -----------------------------------------------------
# (имя, режим PIL, декодер, параметр, байт на элемент, элемент = блок 4×4?)
FORMATS = {
    6: ("R8_UNORM", "L", "raw", "L", 1, False),
    11: ("R8G8_UNORM", "LA", "raw", "LA", 2, False),
    18: ("R8G8B8A8_UNORM", "RGBA", "raw", "RGBA", 4, False),
    20: ("R8G8B8A8_SRGB", "RGBA", "raw", "RGBA", 4, False),
    23: ("B8G8R8A8_UNORM", "RGBA", "raw", "BGRA", 4, False),
    24: ("B8G8R8A8_SRGB", "RGBA", "raw", "BGRA", 4, False),
    54: ("BC1_UNORM", "RGBA", "bcn", 1, 8, True),
    55: ("BC1_SRGB", "RGBA", "bcn", 1, 8, True),
    56: ("BC1A_UNORM", "RGBA", "bcn", 1, 8, True),
    57: ("BC1A_SRGB", "RGBA", "bcn", 1, 8, True),
    58: ("BC2_UNORM", "RGBA", "bcn", 2, 16, True),
    59: ("BC2_SRGB", "RGBA", "bcn", 2, 16, True),
    60: ("BC3_UNORM", "RGBA", "bcn", 3, 16, True),
    61: ("BC3_SRGB", "RGBA", "bcn", 3, 16, True),
    62: ("BC4_UNORM", "L", "bcn", 4, 8, True),
    63: ("BC5_UNORM", "RGB", "bcn", 5, 16, True),
    66: ("BC7_UNORM", "RGBA", "bcn", 7, 16, True),
    67: ("BC7_SRGB", "RGBA", "bcn", 7, 16, True),
}


def format_name(fmt):
    return FORMATS.get(fmt, (f"fmt{fmt}",))[0]


def mip_dims(h, level):
    return max(1, h["width"] >> level), max(1, h["height"] >> level)


def decode_mip(h, data, level=0, slice_index=0, tiled=True, data_first=0):
    """data — содержимое чанка с мипа data_first (обычно весь чанк, 0). -> PIL.Image уровня level."""
    from PIL import Image
    fmt = FORMATS.get(h["format"])
    if fmt is None:
        raise ValueError(f"формат {h['format']} не поддержан")
    name, mode, dec, arg, eb, block = fmt
    sizes = h["mip_sizes"]
    first = data_first
    if level < first:
        raise ValueError(f"мип {level} не в данных (с {first})")
    if h.get("ps5"):
        # PS5: мипы от меньшего к большему, у мелких — общий хвост; поток — все мипы
        if first or len(data) < sum(sizes) or not sizes[level]:
            raise ValueError(f"PS5: мип {level} — поток {len(data)} Б при сумме мипов {sum(sizes)} (частичный поток "
                             "или мип в общем хвосте — не разобрано)")
        ofs = sum(sizes[level + 1:]) + slice_index * sum(sizes)
    else:
        ofs = sum(sizes[first:level])
        per_slice = sum(sizes[first:])
        ofs += slice_index * per_slice
    w, hh = mip_dims(h, level)
    if block:
        we, he = (w + 3) // 4, (hh + 3) // 4
    else:
        we, he = w, hh
    raw = data[ofs:ofs + sizes[level]]
    if not tiled:
        lin = bytes(raw[:we * he * eb])
    elif h.get("ps5"):
        lin = detile_ps5(raw, we, he, eb)
    else:
        lin = detile_1d_thin(raw, we, he, eb)
    if block:
        img = Image.frombytes(mode, (we * 4, he * 4), lin, dec, arg)
        if (we * 4, he * 4) != (w, hh):
            img = img.crop((0, 0, w, hh))
    else:
        img = Image.frombytes(mode, (w, hh), lin, dec, arg)
    return img
