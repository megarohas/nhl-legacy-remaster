"""Оглавления (.toc) Frostbite NHL 24 (PS4, Gen4b): бандлы и чанки → места в CAS.

Файл: 0x22C байт заголовка (магия 00D1CE01, подпись, строка-ключ), дальше данные (смещения — от 0x22C), всё BE.
У NHL 27 (PS5) заголовка нет: файл сразу начинается с данных (u32 0x3C).
Заголовок данных (15 × u32): [0] 0x3C, [1] смещение записей бандлов, [2] число бандлов, [3] флаги чанков,
[4] GUID чанков (GUID + u32 индекс×3), [5] число чанков, [6] записи чанков (u8 ?, u8 patch, u8 catalog, u8 cas,
u32 offset, u32 size), … Сразу за заголовком — u32 × число бандлов (ссылки/хеши).
Запись бандла (в [1]): u32 ?, u32 size, u64 offset → в данных TOC структура: u32 ?, u32 ?, u32 смещение флагов,
u32 число записей, u32 смещение записей, …; записи: если флаг 1 — u8 ?, u8 patch, u8 catalog, u8 cas; затем u32 offset,
u32 size. Запись 0 — сам манифест бандла в CAS, дальше — его ebx, res, chunks по порядку манифеста.
catalog — номер пакета установки (nhl_installpackage_NN), cas — номер файла cas_NN.cas.

  python -m fb.toc stats            # бандлы/чанки по всем TOC
  python -m fb.toc index            # game/work/nhl24/catalog/toc_chunks.json (GUID → место) и toc_bundles.jsonl
"""
import argparse
import glob
import json
import os
import struct
import sys
import uuid

from . import bundle, cas
from .cas import REPO

from . import source  # noqa: E402

DATA = source.DATA
CAT = source.CATALOG
BASE = 0x22C


def cas_key(catalog, casn, patch=0):
    """Ключ места: ipNN/cas_MM; из патча — patch/ipNN/cas_MM (у NHL 24 патча нет)."""
    return ("patch/" if patch else "") + f"ip{catalog:02d}/cas_{casn:02d}"


def cas_path(catalog, casn, patch=0):
    return source.cas_path(catalog, casn, patch)


def wide_loc(d, q):
    """Место в записи TOC NHL 27 (8 байт): u32 (старшие 16 бит persistentIndex пакета), u16 (младшие), u16 номер CAS
    → (номер пакета, номер CAS). Неизвестный пакет — 255 (файла не будет, «нет на диске» в fb.probe)."""
    hi, lo, casn = struct.unpack_from(">IHH", d, q)
    pkg = source.package_of(((hi & 0xFFFF) << 16) | lo)
    return (255 if pkg is None else pkg), casn


def read_toc(path):
    raw = open(path, "rb").read()
    if raw[:4] == b"\x00\xd1\xce\x01":
        d, wide = raw[BASE:], False                      # NHL 24 PS4: заголовок с подписью
    elif raw[:4] == b"\x00\x00\x00\x3c":
        d, wide = raw, True                              # NHL 27 PS5: без заголовка (21.10.2026)
    else:
        raise ValueError(f"{path}: не TOC (нет ни 00D1CE01 + 0x22C, ни данных с 0x3C)")
    hdr = struct.unpack_from(">15I", d, 0)
    (magic, b_ofs, b_cnt, c_flags, c_guids, c_cnt, c_ents) = hdr[:7]
    res = {"hdr": hdr, "bundles": [], "chunks": []}
    # бандлы
    if b_cnt and b_cnt != b_ofs:
        for i in range(b_cnt):
            unk, size, ofs = struct.unpack_from(">IIQ", d, b_ofs + 16 * i)
            p = ofs
            u1, u2, fl_ofs, n, en_ofs = struct.unpack_from(">5I", d, p)
            flags = d[p + fl_ofs:p + fl_ofs + n]
            q = p + en_ofs
            ents = []
            catalog = casn = patch = 0
            for j in range(n):
                if wide and flags[j]:                    # NHL 27: флаг 0x84, место 8 байт (wide_loc)
                    catalog, casn = wide_loc(d, q)
                    patch = 0
                    q += 8
                elif not wide and flags[j] == 1:
                    _u, patch, catalog, casn = struct.unpack_from(">4B", d, q)
                    q += 4
                eo, es = struct.unpack_from(">II", d, q)
                q += 8
                ents.append((catalog, casn, patch, eo, es))
            res["bundles"].append(ents)
    # чанки
    if c_cnt:
        # запись чанка: NHL 24 — 12 байт (u8 ?, u8 patch, u8 catalog, u8 cas, u32 offset, u32 size), индекс у GUID — в
        # u32-словах (÷3); NHL 27 — 16 байт: место 8 байт (wide_loc), offset, size; ÷4
        ent = 16 if wide else 12
        guids = [None] * c_cnt
        for i in range(c_cnt):
            g = d[c_guids + 20 * i:c_guids + 20 * i + 16]
            idx = struct.unpack_from(">I", d, c_guids + 20 * i + 16)[0] & 0xFFFFFF
            guids[idx // (ent // 4)] = str(uuid.UUID(bytes=bytes(g[::-1])))  # GUID в обратном порядке байт
        for i in range(c_cnt):
            q = c_ents + ent * i
            if wide:
                (catalog, casn), patch = wide_loc(d, q), 0
                q += 4
            else:
                _u, patch, catalog, casn = struct.unpack_from(">4B", d, q)
            eo, es = struct.unpack_from(">II", d, q + 4)
            res["chunks"].append((guids[i], catalog, casn, patch, eo, es))
    return res


def all_tocs():
    return [os.path.join(DATA, "layout.toc")] + sorted(glob.glob(os.path.join(source.PLATFORM_DIR, "*.toc"))) + \
        sorted(glob.glob(os.path.join(source.PLATFORM_DIR, "levels", "*", "*.toc")))


def cmd_stats(a):
    for p in all_tocs()[1:]:
        r = read_toc(p)
        nent = sum(len(b) for b in r["bundles"])
        print(f"{os.path.relpath(p, DATA):35s} бандлов {len(r['bundles']):6d} (записей {nent:7d}), чанков {len(r['chunks']):6d}")


def cmd_index(a):
    """Чанки TOC + записи бандлов (с GUID чанков из манифестов) → GUID → место; сверка с каталогом без TOC."""
    chunks = {}
    for p in all_tocs()[1:]:
        r = read_toc(p)
        for g, catalog, casn, patch, eo, es in r["chunks"]:
            chunks.setdefault(g, {"cas": cas_key(catalog, casn, patch), "ofs": eo, "csize": es, "src": "toc"})
        nb = 0
        for ents in r["bundles"]:
            if not ents:
                continue
            catalog, casn, patch, eo, es = ents[0]
            path = cas_path(catalog, casn, patch)
            if not os.path.exists(path):
                continue
            with open(path, "rb") as f:
                f.seek(eo)
                man = f.read(es)
            if not bundle.is_manifest(man[:8]):
                continue
            m = bundle.parse(man)
            items = m["ebx"] + m["res"] + m["chunks"]
            for k, it in enumerate(m["chunks"]):
                j = 1 + len(m["ebx"]) + len(m["res"]) + k
                if j < len(ents):
                    c2, n2, p2, o2, s2 = ents[j]
                    chunks.setdefault(it["id"], {"cas": cas_key(c2, n2, p2), "ofs": o2, "csize": s2, "src": "bundle",
                                                 "lo": it["logical_offset"], "ls": it["logical_size"],
                                                 "sha1": it["sha1"]})
            nb += 1
        print(os.path.relpath(p, DATA), "бандлов прочитано", nb, flush=True)
    os.makedirs(CAT, exist_ok=True)
    with open(os.path.join(CAT, "toc_chunks.json"), "w", encoding="utf-8") as f:
        json.dump(chunks, f)
    # сверка с каталогом без TOC
    with open(os.path.join(CAT, "chunks.idx.json"), encoding="utf-8") as f:
        old = json.load(f)
    om = os.path.join(CAT, "orphan_map.json")
    found_old = {k for k, v in old.items() if not v.get("missing")}
    if os.path.exists(om):
        with open(om, encoding="utf-8") as f:
            found_old |= set(json.load(f))
    new = set(chunks)
    print(f"чанков по TOC: {len(new)}; по каталогу без TOC было найдено: {len(found_old)}; "
          f"из них есть в TOC: {len(found_old & new)}; новых благодаря TOC: {len(new - found_old)}; "
          f"из «без места» в манифестах найдено теперь: {len({k for k, v in old.items() if v.get('missing')} & new)} "
          f"из {sum(1 for v in old.values() if v.get('missing'))}")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("stats")
    sub.add_parser("index")
    a = ap.parse_args()
    return {"stats": cmd_stats, "index": cmd_index}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
