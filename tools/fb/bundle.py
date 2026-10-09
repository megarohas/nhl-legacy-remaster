"""Двоичный манифест бандла в CAS (NHL 24 PS4).

u32 BE размер (остатка), затем LE: u32 магия 0x9D798ED6, totalCount, ebxCount, resCount, chunkCount,
stringsOffset, metaOffset, metaSize (смещения — от конца поля размера, т. е. от +4);
sha1[totalCount]; ebx: (nameOfs, size)[ebx]; res: (nameOfs, size)[res]; resType u32[res];
resMeta 16 Б[res]; resRid u64[res]; chunks: (guid 16 Б, logicalOffset, logicalSize)[chunk];
meta — DbObject (chunkMeta: [{h32, meta}]), строки — имена ebx/res (C-строки).
"""
import struct
import uuid

from . import dbobject

MAGICS = (0x9D798ED6, 0x9D798ED5, 0xED1CEDB8)


def is_manifest(head8):
    if len(head8) < 8:
        return False
    size = struct.unpack(">I", head8[:4])[0]
    magic = struct.unpack("<I", head8[4:8])[0]
    return magic in MAGICS and 0x20 <= size < 0x4000000


def parse(data):
    """data — байты начиная с поля размера (u32 BE)."""
    size = struct.unpack_from(">I", data, 0)[0]
    b = memoryview(data)[4:4 + size]
    (magic, total, nebx, nres, nchunk, str_ofs, meta_ofs, meta_size) = struct.unpack_from("<8I", b, 0)
    p = 32
    sha1 = [bytes(b[p + 20 * i:p + 20 * i + 20]).hex() for i in range(total)]
    p += 20 * total

    def cstr(ofs):
        s = bytes(b[str_ofs + ofs:str_ofs + ofs + 512])
        return s[:s.index(b"\0")].decode("utf-8", "replace")

    ebx = []
    for i in range(nebx):
        no, sz = struct.unpack_from("<II", b, p)
        p += 8
        ebx.append({"name": cstr(no), "size": sz, "sha1": sha1[i]})
    res = []
    for i in range(nres):
        no, sz = struct.unpack_from("<II", b, p)
        p += 8
        res.append({"name": cstr(no), "size": sz, "sha1": sha1[nebx + i]})
    for i in range(nres):
        res[i]["type"] = struct.unpack_from("<I", b, p)[0]
        p += 4
    for i in range(nres):
        res[i]["meta"] = bytes(b[p:p + 16])
        p += 16
    for i in range(nres):
        res[i]["rid"] = struct.unpack_from("<Q", b, p)[0]
        p += 8
    chunks = []
    for i in range(nchunk):
        g = uuid.UUID(bytes_le=bytes(b[p:p + 16]))
        lo, ls = struct.unpack_from("<II", b, p + 16)
        p += 24
        chunks.append({"id": str(g), "logical_offset": lo, "logical_size": ls,
                       "sha1": sha1[nebx + nres + i]})
    meta = None
    if meta_size:
        try:
            meta = dbobject.loads(bytes(b[meta_ofs:meta_ofs + meta_size]))
        except Exception:
            meta = None
    return {"magic": magic, "size": size + 4, "ebx": ebx, "res": res, "chunks": chunks, "meta": meta}
