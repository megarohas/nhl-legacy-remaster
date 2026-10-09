"""Сводка по результатам fb.scan: типы res, текстуры, чанки; группы по путям.

  python -m fb.catalog            -> game/work/nhl24/catalog/{restypes.csv,textures.csv,prefixes.csv,chunks.idx.json}
"""
import collections
import csv
import glob
import json
import os
import sys

from .cas import REPO
from .texture import RES_TEXTURE

CAT = os.path.join(REPO, "game", "work", "nhl24", "catalog")


def records():
    for p in sorted(glob.glob(os.path.join(CAT, "scan", "*.jsonl"))):
        with open(p, encoding="utf-8") as f:
            for line in f:
                yield json.loads(line)


def load():
    tex, chunks, ebx = [], {}, []
    rtypes = collections.Counter()
    rexample = {}
    for r in records():
        k = r["k"]
        if k == "res":
            rtypes[r["type"]] += 1
            rexample.setdefault(r["type"], r["name"])
            if r["type"] == RES_TEXTURE:
                tex.append(r)
        elif k == "chunk":
            c = chunks.setdefault(r["id"], [])
            c.append(r)
        elif k == "ebx":
            ebx.append(r)
    return tex, chunks, ebx, rtypes, rexample


def main():
    tex, chunks, ebx, rtypes, rexample = load()
    os.makedirs(CAT, exist_ok=True)
    with open(os.path.join(CAT, "restypes.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["type", "count", "example"])
        for t, n in rtypes.most_common():
            w.writerow([f"0x{t:08x}", n, rexample[t]])
    with open(os.path.join(CAT, "textures.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["name", "bundle", "cas", "ofs", "csize", "size", "missing"])
        for r in sorted(tex, key=lambda r: r["name"]):
            w.writerow([r["name"], r["b"], r.get("cas", ""), r.get("ofs", ""), r.get("csize", ""), r["size"], r.get("missing", 0)])
    pref = collections.Counter()
    for r in tex:
        parts = r["name"].split("/")
        for d in (2, 3, 4):
            if len(parts) > d:
                pref["/".join(parts[:d])] += 1
    with open(os.path.join(CAT, "prefixes.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["prefix", "textures"])
        for p, n in sorted(pref.items()):
            w.writerow([p, n])
    idx = {}
    for cid, lst in chunks.items():
        have = [c for c in lst if "ofs" in c]
        c = have[0] if have else lst[0]
        idx[cid] = {k: c.get(k) for k in ("cas", "ofs", "csize", "lo", "ls", "sha1", "h32")}
        idx[cid]["missing"] = 0 if have else 1
    with open(os.path.join(CAT, "chunks.idx.json"), "w", encoding="utf-8") as f:
        json.dump(idx, f)
    names = {r["name"] for r in tex}
    print(f"res-типов {len(rtypes)}, текстур {len(tex)} (уникальных имён {len(names)}), "
          f"чанков {len(chunks)} (без места {sum(v['missing'] for v in idx.values())}), ebx {len(ebx)}")


if __name__ == "__main__":
    sys.exit(main())
