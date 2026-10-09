"""Привязка «бесхозных» чанков (их нет сразу за манифестом) к GUID без TOC — по sha1.

Манифест знает sha1 каждого чанка = sha1 сжатых байт в CAS (с заголовками блоков). Последовательно
читаем все orphan-участки (fb.scan), режем на потоки по короткому блоку (< 0x40000) и по
совпадению префикса с нужным размером, считаем sha1 и сверяем со всеми чанками «без места».

  python -m fb.orphans [--jobs 2]   -> game/work/nhl24/catalog/orphan_map.json
"""
import argparse
import glob
import hashlib
import json
import os
import struct
import sys
from multiprocessing import Pool

from . import bundle, cas
from .cas import REPO
from .extract import CAT, cas_path

FULL = 0x40000
READ = 32 << 20


def wanted():
    with open(os.path.join(CAT, "chunks.idx.json"), encoding="utf-8") as f:
        idx = json.load(f)
    by_sha = {}
    sizes = set()
    for cid, c in idx.items():
        if c.get("missing"):
            size = c["ls"] if c["lo"] else (c["lo"] or 0) + c["ls"]
            by_sha[c["sha1"]] = (cid, size)
            sizes.add(size)
    return by_sha, sizes


def regions():
    out = {}
    for p in sorted(glob.glob(os.path.join(CAT, "scan", "*.jsonl"))):
        with open(p, encoding="utf-8") as f:
            for line in f:
                if '"k": "orphan"' in line:
                    r = json.loads(line)
                    out.setdefault(r["cas"], []).append((r["ofs"], r["csize"]))
    return out


_W = None


def _init():
    global _W
    _W = wanted()


def scan_cas(item):
    key, regs = item
    by_sha, sizes = _W
    found = {}
    nstreams = 0
    with open(cas_path(key), "rb", buffering=0) as f:
        for ofs, csize in regs:
            f.seek(ofs)
            end = ofs + csize
            buf = b""
            bpos = ofs  # позиция buf[0] в файле
            pos = ofs
            s_start, h, usum = pos, hashlib.sha1(), 0
            while pos < end:
                if pos + 8 > bpos + len(buf):
                    buf = buf[pos - bpos:] + f.read(min(READ, end - (bpos + len(buf))))
                    bpos = pos
                    if pos + 8 > bpos + len(buf):
                        break
                hdr = buf[pos - bpos:pos - bpos + 8]
                usize, uflags, ctype, flags, cs = cas.parse_block_header(hdr)
                n = 8 + (usize if (ctype & 0x7F) == 0 else cs)
                if pos + n > bpos + len(buf):
                    buf = buf[pos - bpos:] + f.read(max(READ, n))
                    bpos = pos
                h.update(buf[pos - bpos:pos - bpos + n])
                usum += usize
                pos += n
                close = usize < FULL
                if not close and usum in sizes:
                    d = h.copy().hexdigest()
                    if d in by_sha:
                        close = True
                if close:
                    d = h.hexdigest()
                    nstreams += 1
                    hit = by_sha.get(d)
                    if hit:
                        found[hit[0]] = {"cas": key, "ofs": s_start, "csize": pos - s_start, "size": usum}
                    s_start, h, usum = pos, hashlib.sha1(), 0
    return key, found, nstreams


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jobs", type=int, default=2)
    a = ap.parse_args()
    regs = regions()
    by_sha, sizes = wanted()
    print(f"чанков без места: {len(by_sha)}, orphan-участков: {sum(len(v) for v in regs.values())} в {len(regs)} CAS", flush=True)
    allfound = {}
    with Pool(a.jobs, initializer=_init) as pool:
        for key, found, ns in pool.imap_unordered(scan_cas, sorted(regs.items())):
            allfound.update(found)
            print(f"{key}: потоков {ns}, найдено {len(found)} (всего {len(allfound)})", flush=True)
    with open(os.path.join(CAT, "orphan_map.json"), "w", encoding="utf-8") as f:
        json.dump(allfound, f)
    print(f"итого найдено {len(allfound)} из {len(by_sha)}")


if __name__ == "__main__":
    sys.exit(main())
