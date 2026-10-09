"""DbObject — двоичный формат Frostbite для TOC/initfs/meta бандлов.

Байт типа: младшие 5 бит — тип, бит 0x80 — «без имени» (элемент списка/корень).
Типы: 0x01 list, 0x02 object, 0x06 bool, 0x07 string, 0x08 int32, 0x09 int64,
0x0B float, 0x0C double, 0x0F guid, 0x10 sha1, 0x13 bytes. 0x00 — конец списка/объекта.
"""
import struct
import uuid


def read_varint(buf, pos):
    val = 0
    shift = 0
    while True:
        b = buf[pos]
        pos += 1
        val |= (b & 0x7F) << shift
        if not b & 0x80:
            return val, pos
        shift += 7


def _read_cstr(buf, pos):
    end = buf.index(b"\0", pos)
    return buf[pos:end].decode("utf-8", "replace"), end + 1


def read_value(buf, pos):
    """Читает один элемент: возвращает (name, value, pos). На 0x00 — (None, StopIteration, pos)."""
    t = buf[pos]
    pos += 1
    if t == 0:
        return None, StopIteration, pos
    name = None
    if not t & 0x80:
        name, pos = _read_cstr(buf, pos)
    t &= 0x1F
    if t == 0x01 or t == 0x02:
        size, pos = read_varint(buf, pos)
        end = pos + size
        if t == 0x01:
            out = []
            while pos < end:
                _, v, pos = read_value(buf, pos)
                if v is StopIteration:
                    break
                out.append(v)
        else:
            out = {}
            while pos < end:
                n, v, pos = read_value(buf, pos)
                if v is StopIteration:
                    break
                out[n] = v
        return name, out, end
    if t == 0x06:
        return name, bool(buf[pos]), pos + 1
    if t == 0x07:
        n, pos = read_varint(buf, pos)
        return name, buf[pos:pos + n].rstrip(b"\0").decode("utf-8", "replace"), pos + n
    if t == 0x08:
        return name, struct.unpack_from("<i", buf, pos)[0], pos + 4
    if t == 0x09:
        return name, struct.unpack_from("<q", buf, pos)[0], pos + 8
    if t == 0x0B:
        return name, struct.unpack_from("<f", buf, pos)[0], pos + 4
    if t == 0x0C:
        return name, struct.unpack_from("<d", buf, pos)[0], pos + 8
    if t == 0x0F:
        return name, uuid.UUID(bytes_le=bytes(buf[pos:pos + 16])), pos + 16
    if t == 0x10:
        return name, bytes(buf[pos:pos + 20]).hex(), pos + 20
    if t == 0x13:
        n, pos = read_varint(buf, pos)
        return name, bytes(buf[pos:pos + n]), pos + n
    raise ValueError(f"DbObject: неизвестный тип 0x{t:02x} @0x{pos - 1:x}")


def loads(buf, pos=0):
    _, v, _ = read_value(buf, pos)
    return v


TOC_HEADER = 0x22C  # магия 00D1CE01 + подпись + строка-ключ «x…x»; дальше — открытые данные


def strip_toc_header(data):
    """Снимает заголовок 00D1CE0x (подпись), если есть. В NHL 24 данные после 0x22C не XOR-ены."""
    if data[:3] == b"\x00\xd1\xce" and data[3] in (0, 1, 3):
        return data[TOC_HEADER:]
    return data
