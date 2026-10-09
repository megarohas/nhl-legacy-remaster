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


def scan_cas2(item):
    """Второй проход: чанк мог начаться не после короткого блока (перед ним — чанк ровно из полных блоков, которого
    нет в манифестах). Для каждого короткого блока размера r и каждого нужного размера S с S mod 0x40000 == r
    начало — за (S − r) / 0x40000 полных блоков до него; sha1 [начало, конец короткого блока] сверяется с нужными."""
    key, regs = item
    by_sha, sizes = _W
    by_rem = {}
    for sz in sizes:
        if sz % FULL:
            by_rem.setdefault(sz % FULL, set()).add(sz // FULL)
    found = {}
    tested = 0
    with open(cas_path(key), "rb", buffering=0) as f:
        for ofs, csize in regs:
            f.seek(ofs)
            data = f.read(csize)
            pos = 0
            run = []  # начала полных блоков текущей серии (смещения в data)
            while pos + 8 <= len(data):
                usize, uflags, ctype, flags, cs = cas.parse_block_header(data[pos:pos + 8])
                n = 8 + (usize if (ctype & 0x7F) == 0 else cs)
                if usize == FULL:
                    run.append(pos)
                    pos += n
                    continue
                end = pos + n
                for k in by_rem.get(usize, ()):
                    if 0 < k <= len(run):
                        start = run[len(run) - k]
                        tested += 1
                        d = hashlib.sha1(data[start:end]).hexdigest()
                        hit = by_sha.get(d)
                        if hit:
                            found[hit[0]] = {"cas": key, "ofs": ofs + start, "csize": end - start,
                                             "size": k * FULL + usize}
                run = []
                pos = end
    return key, found, tested


def list_streams(item):
    """Все потоки orphan-участков (по короткому блоку): cas, ofs, csize, usize, sha1 — для поиска чанков без
    манифеста (например, геометрии сеток — она в TOC) по размеру и содержимому."""
    key, regs = item
    out = []
    with open(cas_path(key), "rb", buffering=0) as f:
        for ofs, csize in regs:
            f.seek(ofs)
            data = f.read(csize)
            pos = start = 0
            us = 0
            while pos + 8 <= len(data):
                usize, uflags, ctype, flags, cs = cas.parse_block_header(data[pos:pos + 8])
                n = 8 + (usize if (ctype & 0x7F) == 0 else cs)
                us += usize
                pos += n
                if usize < FULL:
                    out.append((ofs + start, pos - start, us, hashlib.sha1(data[start:pos]).hexdigest()))
                    start, us = pos, 0
    return key, out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jobs", type=int, default=2)
    ap.add_argument("--pass2", action="store_true", help="второй проход (начало чанка внутри серии полных блоков)")
    ap.add_argument("--streams", action="store_true", help="список всех потоков orphan-участков -> orphan_streams.jsonl")
    a = ap.parse_args()
    if a.streams:
        regs = regions()
        n = 0
        with open(os.path.join(CAT, "orphan_streams.jsonl"), "w", encoding="utf-8") as fo, Pool(a.jobs) as pool:
            for key, out in pool.imap_unordered(list_streams, sorted(regs.items())):
                for o, c, u, h in out:
                    fo.write(json.dumps({"cas": key, "ofs": o, "csize": c, "usize": u, "sha1": h}) + chr(10))
                n += len(out)
                print(f"{key}: потоков {len(out)} (всего {n})", flush=True)
        return
    regs = regions()
    by_sha, sizes = wanted()
    if a.pass2:
        path = os.path.join(CAT, "orphan_map.json")
        with open(path, encoding="utf-8") as f:
            have = json.load(f)
        print(f"второй проход: уже найдено {len(have)}", flush=True)
        with Pool(a.jobs, initializer=_init) as pool:
            for key, found, ns in pool.imap_unordered(scan_cas2, sorted(regs.items())):
                new = {k: v for k, v in found.items() if k not in have}
                have.update(new)
                print(f"{key}: проверок {ns}, новых {len(new)} (всего {len(have)})", flush=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(have, f)
        print(f"итого найдено {len(have)} из {len(by_sha)}")
        return
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
