"""Головы-сканы NHL 24 (PS4): сетки MeshSet и текстуры по имени папки content/character/skater/shared/head/licensed/<папка>.

У всех голов NHL 24 одна сетка `mat_head` (3157 вершин, 6014 треугольников, один порядок вершин и одна развёртка) — та же
базовая голова EA, что у сканов NHL Legacy (head 2623 + mouthbag 534; docs/heads-nhl24.md). Геометрия — в чанке по TOC.

MeshSet головы (тип 0x49B156D4): u64 @0x20 — LOD; LOD+0x08 число секций, +0x0C смещение секций (шаг 0xE0 — у свитера в
meshset.py 0xC0), +0x58/+0x5C — размеры буферов индексов/вершин, +0x60 — GUID чанка, +0x98 — число костей. Секция: +0x08 имя,
+0x20 треугольников, +0x24 первый индекс, +0x28 смещение вершин, +0x2C число вершин, +0x4C — 16 элементов (usage, формат,
смещение, поток), +0x8C — шаги потоков. Usage: 1 позиция, 2/3 индексы костей, 4/5 веса, 6 нормаль, 7 касательная,
8 бинормаль, 0x21/0x22 UV. Форматы: 3 float3, 6 half2, 8 half4, 0x0D ubyte4n, 0x16 ubyte4, 0x17 ushort4.

Только чтение; нужны дамп NHL 24 и каталог (fb.scan, fb.catalog, fb.toc index).
"""
import csv
import os
import re
import struct
import uuid

import numpy as np

from . import cas, texture
from .cas import REPO

CAT = os.path.join(REPO, "game", "work", "nhl24", "catalog")
LICENSED = "content/character/skater/shared/head/licensed"
FMT = {3: ("<f4", 3), 6: ("<f2", 2), 8: ("<f2", 4), 0x0D: ("u1", 4), 0x16: ("u1", 4), 0x17: ("<u2", 4),
       2: ("<f4", 2), 4: ("<f4", 4)}
USAGE = {1: "pos", 2: "bi0", 3: "bi1", 4: "bw0", 5: "bw1", 6: "nrm", 7: "tan", 8: "binrm", 0x21: "uv0", 0x22: "uv1"}
SECTION_STEP = 0xE0

_res = None
_tex = None


def licensed_folders():
    """Папки сканов, у которых в каталоге есть сетка головы head_<папка>_mesh."""
    txt = open(os.path.join(CAT, "meshnames.txt"), encoding="utf-8").read()
    return sorted(set(re.findall(LICENSED + r"/([^/\s]+)/components/head_\1_mesh", txt)))


def _res_index():
    """{имя res: запись прохода fb.scan} — для сеток голов и волос (один проход по каталогу)."""
    global _res
    if _res is None:
        import glob
        import json
        _res = {}
        key = '"k": "res"'
        for p in sorted(glob.glob(os.path.join(CAT, "scan", "*.jsonl"))):
            with open(p, encoding="utf-8") as f:
                for line in f:
                    if key in line and "/head/licensed/" in line and '"ofs"' in line:
                        r = json.loads(line)
                        _res.setdefault(r["name"], r)
    return _res


def mesh(name):
    """MeshSet → {'bbox', 'sections': {имя: {'nv', 'ntri', 'tri', атрибуты по USAGE}}} (LOD0)."""
    from .extract import cas_file, chunks
    r = _res_index().get(name)
    if r is None:
        raise KeyError(f"нет res {name}")
    d, _ = cas.read_entry(cas_file(r["cas"]), r["ofs"], r["size"])
    meta = bytes.fromhex(r["meta"])
    hdr, inline = struct.unpack_from("<II", meta, 0)
    lod = struct.unpack_from("<Q", d, 0x20)[0]
    nsec, sec_ptr = struct.unpack_from("<II", d, lod + 0x08)
    ib_size, vb_size = struct.unpack_from("<II", d, lod + 0x58)
    cid = str(uuid.UUID(bytes_le=bytes(d[lod + 0x60:lod + 0x70])))
    if inline:
        data = d[hdr:]
    else:
        c = chunks().get(cid)
        if not c or c.get("missing"):
            raise KeyError(f"{name}: нет чанка {cid}")
        if c.get("toc"):
            data = cas.read_stored(cas_file(c["cas"]), c["ofs"], c["csize"])
        else:
            data, _ = cas.read_entry(cas_file(c["cas"]), c["ofs"], (c["lo"] or 0) + c["ls"])
    vb = data[:vb_size]
    ib = np.frombuffer(data[vb_size:vb_size + ib_size], dtype="<u2")
    out = {"bbox": struct.unpack_from("<8f", d, 0), "sections": {}}
    for k in range(nsec):
        s = sec_ptr + k * SECTION_STEP
        nmp = struct.unpack_from("<Q", d, s + 0x08)[0]
        sname = d[nmp:d.index(b"\0", nmp)].decode("latin1")
        ntri, first, voff, nv = struct.unpack_from("<4I", d, s + 0x20)
        elems = []
        for e in range(16):
            usage, fmt, ofs, stream = struct.unpack_from("4B", d, s + 0x4C + 4 * e)
            if usage and stream != 0xFF:
                elems.append((usage, fmt, ofs, stream))
        nstreams = max(e[3] for e in elems) + 1
        strides = struct.unpack_from(f"<{nstreams}H", d, s + 0x8C)
        starts, acc = [], voff
        for st in strides:
            starts.append(acc)
            acc += st * nv
        sec = {"nv": nv, "ntri": ntri, "tri": ib[first:first + 3 * ntri].reshape(-1, 3).astype(np.int64)}
        for usage, fmt, ofs, stream in elems:
            if fmt not in FMT:
                continue
            dt, n = FMT[fmt]
            st = strides[stream]
            raw = np.frombuffer(vb, dtype=np.uint8, count=st * nv, offset=starts[stream]).reshape(nv, st)
            sec[USAGE.get(usage, hex(usage))] = raw[:, ofs:ofs + np.dtype(dt).itemsize * n].copy().view(dt).reshape(
                nv, n).astype(np.float64)
        out["sections"][sname] = sec
    return out


def head(folder):
    return mesh(f"{LICENSED}/{folder}/components/head_{folder}_mesh")


def hair(folder, variant="default_nomask"):
    """[(имя, секция)] сеток волос: base (шапка + пряди) и top (пряди); нет сетки — пропускается."""
    out = []
    for part in ("base", "top"):
        try:
            m = mesh(f"{LICENSED}/{folder}/components/hair_{folder}_{variant}_{part}_mesh")
        except KeyError:
            continue
        out += [(f"{part}:{k}", v) for k, v in m["sections"].items()]
    return out


def _tex_index():
    global _tex
    if _tex is None:
        _tex = {}
        with open(os.path.join(CAT, "textures.csv"), encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if "/head/licensed/" in r["name"] and r["ofs"] and r["name"] not in _tex:
                    _tex[r["name"]] = r
    return _tex


def tex(name, mip=0):
    """Текстура по имени res → RGBA uint8 (H, W, 4)."""
    from .extract import read_chunk, read_header
    r = _tex_index().get(name)
    if r is None:
        raise KeyError(f"нет текстуры {name}")
    h = read_header(r)
    data, start = read_chunk(h)
    if data is None:
        raise KeyError(f"{name}: нет чанка")
    img = texture.decode_mip(h, data, max(mip, start), data_first=start)
    return np.array(img.convert("RGBA"))


def head_textures(folder):
    t = f"{LICENSED}/{folder}/textures"
    try:
        hair = tex(f"{t}/hair_{folder}_color")
    except KeyError:                       # без волос (лысый) — текстуры нет
        hair = None
    return {"head": tex(f"{t}/head_{folder}_color"), "hair": hair}
