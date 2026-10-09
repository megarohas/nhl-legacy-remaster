"""Сетки Frostbite NHL 24 (res MeshSet, тип 0x49B156D4) — только чтение позиций/UV/треугольников для расчётов.

Разобрано на свитере player_jersey_adidas_notuck_large_lod0_mesh: заголовок длиной meta[0] (0xE80), за ним —
буфер вершин (потоки подряд, SoA) и буфер индексов u16. u64 @0x20 — LOD; LOD+0x08 число секций, +0x0C — смещение
секций; LOD+0x58/+0x5C — размеры буферов индексов/вершин. Секция: +0x20 треугольников, +0x24 первый индекс,
+0x28 смещение вершин, +0x2C число вершин, +0x4C — 16 элементов объявления (usage, формат, смещение, поток),
+0x8C — шаги потоков (u16 × число потоков = макс. номер потока + 1; +0xAC — u8 число потоков). Usage: 1 позиция, 2 индексы костей, 4 веса, 6 нормаль, 7 касательная,
8 бинормаль, 0x21 UV0. Форматы: 3 float3, 6 half2, 8 half4, 0x0D ubyte4n, 0x17 ushort4.
"""
import struct

import numpy as np

FMT = {3: ("<f4", 3), 6: ("<f2", 2), 8: ("<f2", 4), 0x0D: ("u1", 4), 0x17: ("<u2", 4), 2: ("<f4", 2), 4: ("<f4", 4)}


def lod_chunk(res):
    """GUID чанка с буферами LOD0 (если геометрия не внутри res): LOD+0x60 (проверено по TOC на шортах)."""
    import uuid
    lod = struct.unpack_from("<Q", res, 0x20)[0]
    return str(uuid.UUID(bytes_le=bytes(res[lod + 0x60:lod + 0x70])))


def parse(res, meta, chunk_data=None):
    """chunk_data — буферы из чанка, если meta[1] (размер встроенных данных) = 0."""
    hdr, inline = struct.unpack_from("<II", meta, 0)
    lod = struct.unpack_from("<Q", res, 0x20)[0]
    nsec, sec_ptr = struct.unpack_from("<II", res, lod + 0x08)
    ib_size, vb_size = struct.unpack_from("<II", res, lod + 0x58)
    data = res[hdr:] if inline or chunk_data is None else chunk_data
    vb = data[:vb_size]
    ib = np.frombuffer(data[vb_size:vb_size + ib_size], dtype="<u2")
    sections = []
    s = sec_ptr
    for k in range(nsec):
        ntri, first, voff, nv = struct.unpack_from("<4I", res, s + 0x20)
        elems = []
        for e in range(16):
            usage, fmt, ofs, stream = struct.unpack_from("4B", res, s + 0x4C + 4 * e)
            if usage == 0:
                continue
            elems.append((usage, fmt, ofs, stream))
        nstreams = max(e[3] for e in elems) + 1 if elems else 0
        strides = struct.unpack_from(f"<{nstreams}H", res, s + 0x8C)
        sections.append({"ntri": ntri, "first": first, "voff": voff, "nv": nv, "elems": elems, "strides": strides})
        s += 0xC0  # следующая секция (не проверено: у свитера одна)
    out = []
    for sec in sections:
        nv = sec["nv"]
        if nv == 0 or sec["ntri"] == 0:
            continue
        # потоки лежат подряд: поток i начинается после всех предыдущих (nv × шаг)
        starts, acc = [], 0
        for st in sec["strides"]:
            starts.append(acc)
            acc += st * nv
        attrs = {}
        for usage, fmt, ofs, stream in sec["elems"]:
            dt, n = FMT.get(fmt, (None, 0))
            if dt is None:
                continue
            st = sec["strides"][stream]
            raw = np.frombuffer(vb, dtype=np.uint8, count=st * nv, offset=starts[stream]).reshape(nv, st)
            a = raw[:, ofs:ofs + np.dtype(dt).itemsize * n].copy().view(dt).reshape(nv, n)
            attrs[usage] = a.astype(np.float32)
        tri = ib[sec["first"]:sec["first"] + 3 * sec["ntri"]].reshape(-1, 3).astype(np.int64)
        out.append({"pos": attrs.get(1)[:, :3], "uv": attrs.get(0x21), "nrm": attrs.get(6), "tri": tri, "info": sec})
    return out
