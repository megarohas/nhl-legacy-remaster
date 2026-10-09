"""Текстуры Frostbite NHL 24 (PS4): заголовок res «Texture» (тип 0x6BDE20BA, 132 Б), детайлинг PS4, PNG.

Заголовок: u32 mipOffset0, u32 mipOffset1, u32 type, u32 pixelFormat, u32 unk, u16 flags,
u16 width, u16 height, u16 depth, u16 slices, u8 mipCount, u8 firstMip, guid chunkId,
u32 mipSizes[15], u32 chunkSize, u32 nameHash, 16 Б textureGroup.
"""
import struct
import uuid

RES_TEXTURE = 0x6BDE20BA


def parse_header(d):
    (mo0, mo1, ttype, fmt, unk, flags, w, h, depth, slices, mips, first) = struct.unpack_from("<5I5H2B", d, 0)
    chunk = bytes(d[32:48])
    mip_sizes = list(struct.unpack_from("<15I", d, 48))
    chunk_size, name_hash = struct.unpack_from("<2I", d, 108)
    group = bytes(d[116:132]).split(b"\0")[0].decode("ascii", "replace")
    return {"mip_offsets": (mo0, mo1), "type": ttype, "format": fmt, "unk": unk, "flags": flags,
            "width": w, "height": h, "depth": depth, "slices": slices, "mips": mips, "first_mip": first,
            "chunk": str(uuid.UUID(bytes_le=chunk)), "mip_sizes": mip_sizes[:max(mips, 1)],
            "chunk_size": chunk_size, "name_hash": name_hash, "group": group}


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


def decode_mip(h, data, level=0, slice_index=0, tiled=True):
    """data — содержимое чанка (весь чанк). -> PIL.Image уровня level (по умолчанию mip0)."""
    from PIL import Image
    fmt = FORMATS.get(h["format"])
    if fmt is None:
        raise ValueError(f"формат {h['format']} не поддержан")
    name, mode, dec, arg, eb, block = fmt
    sizes = h["mip_sizes"]
    first = h["first_mip"]
    ofs = sum(sizes[first:level]) if level >= first else 0
    per_slice = sum(sizes[first:])
    ofs += slice_index * per_slice
    w, hh = mip_dims(h, level)
    if block:
        we, he = (w + 3) // 4, (hh + 3) // 4
    else:
        we, he = w, hh
    raw = data[ofs:ofs + sizes[level]]
    lin = detile_1d_thin(raw, we, he, eb) if tiled else bytes(raw[:we * he * eb])
    if block:
        img = Image.frombytes(mode, (we * 4, he * 4), lin, dec, arg)
        if (we * 4, he * 4) != (w, hh):
            img = img.crop((0, 0, w, hh))
    else:
        img = Image.frombytes(mode, (w, hh), lin, dec, arg)
    return img
