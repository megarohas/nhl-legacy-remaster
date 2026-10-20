"""Чтение блочно-сжатых данных CAS (Frostbite 2019+, NHL 24 PS4).

Заголовок блока (8 байт): u32 BE распакованный размер (старший байт — флаги),
u8 тип сжатия, u8 флаги (младшая тетрада — биты 16..19 сжатого размера), u16 BE сжатый размер.
Типы: 0x00 без сжатия, 0x02 zlib, 0x09 LZ4, 0x0F ZStd, 0x11/0x15/0x19 Oodle (у NHL 24 — Kraken).
Oodle распаковывает ooz (powzix/ooz, GPL-3.0), собранный локально: tools/fb/build_ooz.cmd.
"""
import ctypes
import os
import struct
import zlib

from .source import OOZ_DLL, REPO  # noqa: E402,F401  (пути — fb.source: FB_GAME / FB_WORK …)
_ooz = None


def _oodle():
    global _ooz
    if _ooz is None:
        _ooz = ctypes.CDLL(OOZ_DLL)
        _ooz.ooz_kraken_decompress.restype = ctypes.c_int
        _ooz.ooz_kraken_decompress.argtypes = [ctypes.c_char_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t]
    return _ooz


def oodle_decompress(src, out_size):
    buf = ctypes.create_string_buffer(out_size + 64)
    n = _oodle().ooz_kraken_decompress(bytes(src), len(src), buf, out_size)
    if n != out_size:
        raise ValueError(f"Oodle: распаковано {n} из {out_size}")
    return buf.raw[:out_size]


def parse_block_header(h):
    usize, ctype, flags, csize = struct.unpack(">IBBH", h)
    csize |= (flags & 0x0F) << 16
    return usize & 0x00FFFFFF, usize >> 24, ctype, flags, csize


def decompress_block(ctype, usize, payload):
    t = ctype & 0x7F
    if t == 0x00:
        return bytes(payload[:usize])
    if t in (0x11, 0x15, 0x19):
        return oodle_decompress(payload, usize)
    if t == 0x0F:
        import zstandard
        return zstandard.ZstdDecompressor().decompress(bytes(payload), max_output_size=usize)
    if t == 0x02:
        return zlib.decompress(bytes(payload))
    raise ValueError(f"неизвестный тип сжатия 0x{ctype:02x}")


def block_iter(f, offset, end=None):
    """Идёт по блокам с offset: (pos, usize, ctype, csize). Останавливается на мусорном заголовке."""
    pos = offset
    while end is None or pos < end:
        f.seek(pos)
        h = f.read(8)
        if len(h) < 8:
            return
        usize, uflags, ctype, flags, csize = parse_block_header(h)
        if usize == 0 or usize > 0x100000 or (flags & 0xF0) != 0x70:
            return
        yield pos, usize, ctype, csize
        pos += 8 + (usize if (ctype & 0x7F) == 0 else csize)


def read_entry(f, offset, size):
    """Распаковывает поток блоков с offset, пока не наберётся size байт. -> (data, конец потока в CAS)."""
    out = bytearray()
    pos = offset
    while len(out) < size:
        f.seek(pos)
        h = f.read(8)
        usize, uflags, ctype, flags, csize = parse_block_header(h)
        n = usize if (ctype & 0x7F) == 0 else csize
        payload = f.read(n)
        out += decompress_block(ctype, usize, payload)
        pos += 8 + n
    return bytes(out[:size]), pos


def read_stored(f, offset, csize):
    """Распаковать все блоки сохранённого потока [offset, offset+csize) (место из TOC)."""
    out = bytearray()
    pos, end = offset, offset + csize
    while pos + 8 <= end:
        f.seek(pos)
        h = f.read(8)
        usize, uflags, ctype, flags, cs = parse_block_header(h)
        n = usize if (ctype & 0x7F) == 0 else cs
        out += decompress_block(ctype, usize, f.read(n))
        pos += 8 + n
    return bytes(out)

