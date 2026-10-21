"""Линейный проход по CAS NHL 24 без TOC: манифест бандла, за ним его ebx/res/chunks подряд.

  python -m fb.scan [--jobs 3] [--only installpackage_00/cas_01] [--resume]
--resume — пропустить CAS, у которых уже есть готовый jsonl (файл пишется через .part и переименовывается в конце).
Пишет game/work/nhl24/catalog/scan/<пакет>_<cas>.jsonl: записи bundle/ebx/res/chunk/orphan
с координатами (cas, offset, csize, size). Сводка — fb.catalog.
"""
import argparse
import glob
import json
import os
import struct
import sys
import time
from multiprocessing import Pool

from . import bundle, cas

REPO = cas.REPO
from . import source  # noqa: E402

DATA = source.DATA
OUT = os.path.join(source.CATALOG, "scan")


def cas_files():
    return sorted(glob.glob(os.path.join(source.LAYOUT, "*", "cas_*.cas")))


def cas_key(path):
    pkg = os.path.basename(os.path.dirname(path)).replace(source.PACKAGE, "ip")
    return f"{pkg}/{os.path.splitext(os.path.basename(path))[0]}"


def walk_entry(f, pos, size, fsize):
    """Идёт по блокам, пока не наберёт size. -> (end, ok). ok=False — блоки не сошлись."""
    got = 0
    while got < size:
        if pos + 8 > fsize:
            return pos, False
        f.seek(pos)
        h = f.read(8)
        if bundle.is_manifest(h):
            return pos, False
        usize, uflags, ctype, flags, csize = cas.parse_block_header(h)
        if usize == 0 or usize > 0x100000 or (flags & 0xF0) != 0x70:
            return pos, False
        got += usize
        pos += 8 + (usize if (ctype & 0x7F) == 0 else csize)
    return pos, got == size


def scan_file(path):
    key = cas_key(path)
    os.makedirs(OUT, exist_ok=True)
    out_path = os.path.join(OUT, key.replace("/", "_") + ".jsonl")
    fsize = os.path.getsize(path)
    t0 = time.time()
    stats = {"bundles": 0, "ebx": 0, "res": 0, "chunks": 0, "missing": 0, "orphan_bytes": 0}
    with open(path, "rb", buffering=1 << 16) as f, open(out_path + ".part", "w", encoding="utf-8") as out:
        pos = 0
        bid = 0
        while pos + 8 <= fsize:
            f.seek(pos)
            h = f.read(8)
            if bundle.is_manifest(h):
                size = struct.unpack(">I", h[:4])[0] + 4
                f.seek(pos)
                m = bundle.parse(f.read(size))
                bid += 1
                stats["bundles"] += 1
                bkey = f"{key}#{bid}"
                out.write(json.dumps({"k": "bundle", "b": bkey, "cas": key, "ofs": pos, "size": size,
                                      "nebx": len(m["ebx"]), "nres": len(m["res"]),
                                      "nchunk": len(m["chunks"])}) + "\n")
                pos += size
                metas = (m["meta"] or {}) if isinstance(m["meta"], dict) else {}
                cmeta = metas.get("chunkMeta") or []
                items = [("ebx", e) for e in m["ebx"]] + [("res", r) for r in m["res"]] + \
                        [("chunk", c) for c in m["chunks"]]
                ci = 0
                for kind, e in items:
                    need = e["size"] if kind != "chunk" else e["logical_offset"] + e["logical_size"]
                    if kind == "chunk" and e["logical_offset"]:
                        need = e["logical_size"]
                    end, ok = walk_entry(f, pos, need, fsize)
                    rec = {"k": kind, "b": bkey}
                    if kind == "res":
                        rec.update(name=e["name"], type=e["type"], meta=e["meta"].hex(), rid=e["rid"], size=e["size"])
                    elif kind == "ebx":
                        rec.update(name=e["name"], size=e["size"])
                    else:
                        rec.update(id=e["id"], lo=e["logical_offset"], ls=e["logical_size"])
                        if ci < len(cmeta):
                            cm = cmeta[ci]
                            rec["h32"] = cm.get("h32")
                            mm = cm.get("meta")
                            if mm:
                                rec["cmeta"] = {k: (v.hex() if isinstance(v, bytes) else v) for k, v in mm.items()}
                        ci += 1
                    rec["sha1"] = e["sha1"]
                    if ok:
                        rec.update(cas=key, ofs=pos, csize=end - pos)
                        stats[kind if kind != "chunk" else "chunks"] += 1
                        pos = end
                    else:
                        rec["missing"] = 1
                        stats["missing"] += 1
                    out.write(json.dumps(rec) + "\n")
                continue
            # не манифест: поток блоков вне ожидаемого — записываем как orphan до следующего манифеста
            start = pos
            usum = 0
            while pos + 8 <= fsize:
                f.seek(pos)
                h = f.read(8)
                if bundle.is_manifest(h):
                    break
                usize, uflags, ctype, flags, csize = cas.parse_block_header(h)
                if usize == 0 or usize > 0x100000 or (flags & 0xF0) != 0x70:
                    break
                usum += usize
                pos += 8 + (usize if (ctype & 0x7F) == 0 else csize)
            if pos == start:
                # мусор/выравнивание: ищем следующий манифест побайтно в окне
                f.seek(pos)
                win = f.read(1 << 20)
                nxt = -1
                for i in range(1, len(win) - 8):
                    if win[i + 4:i + 8] in (b"\xd6\x8e\x79\x9d", b"\xd5\x8e\x79\x9d") and bundle.is_manifest(win[i:i + 8]):
                        nxt = i
                        break
                out.write(json.dumps({"k": "gap", "cas": key, "ofs": start, "len": nxt if nxt > 0 else len(win)}) + "\n")
                if nxt < 0:
                    pos += len(win)
                    continue
                pos += nxt
                continue
            stats["orphan_bytes"] += pos - start
            out.write(json.dumps({"k": "orphan", "cas": key, "ofs": start, "csize": pos - start, "usize": usum}) + "\n")
    os.replace(out_path + ".part", out_path)
    stats["sec"] = round(time.time() - t0, 1)
    return key, stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jobs", type=int, default=3)
    ap.add_argument("--only", default=None, help="подстрока пути CAS")
    ap.add_argument("--resume", action="store_true", help="пропустить CAS с готовым jsonl")
    a = ap.parse_args()
    files = [p for p in cas_files() if not a.only or a.only in p.replace("\\", "/")]
    if a.resume:
        done = lambda p: os.path.exists(os.path.join(OUT, cas_key(p).replace("/", "_") + ".jsonl"))
        print(f"--resume: готово {sum(map(done, files))} из {len(files)}", flush=True)
        files = [p for p in files if not done(p)]
    with Pool(a.jobs) as pool:
        for key, st in pool.imap_unordered(scan_file, files):
            print(key, st, flush=True)


if __name__ == "__main__":
    sys.exit(main())
