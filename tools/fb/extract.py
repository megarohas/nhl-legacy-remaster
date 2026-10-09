"""Выгрузка текстур NHL 24 в PNG по регулярке имени (после fb.scan + fb.catalog).

  python -m fb.extract REGEX [--out ПАПКА] [--mip N] [--limit N] [--list]
PNG кладутся в game/work/nhl24/extract/<ПАПКА>/<путь res без content/>.png,
отчёт — <ПАПКА>/_index.csv (имя, формат, размер, мипы, чанк, статус).
"""
import argparse
import csv
import json
import os
import re
import sys

from . import cas, texture
from .cas import REPO

DATA = os.path.join(REPO, "game", "other", "nhl24", "Data", "Gen4b", "superbundlelayout")
WORK = os.path.join(REPO, "game", "work", "nhl24")
CAT = os.path.join(WORK, "catalog")

_files = {}
_chunks = None
VERIFY = True  # сверять sha1 чанка перед распаковкой


def cas_path(key):
    ip, c = key.split("/")
    return os.path.join(DATA, "nhl_installpackage_" + ip[2:], c + ".cas")


def cas_file(key):
    f = _files.get(key)
    if f is None:
        f = _files[key] = open(cas_path(key), "rb")
    return f


def chunks():
    """GUID чанка -> место в CAS: сразу за манифестом (fb.catalog) или найденное по sha1 (fb.orphans)."""
    global _chunks
    if _chunks is None:
        with open(os.path.join(CAT, "chunks.idx.json"), encoding="utf-8") as f:
            _chunks = json.load(f)
        om = os.path.join(CAT, "orphan_map.json")
        if os.path.exists(om):
            with open(om, encoding="utf-8") as f:
                found = json.load(f)
            by_sha = {}
            for cid, c in _chunks.items():
                if not c.get("missing"):
                    by_sha[c["sha1"]] = c
            for cid, loc in found.items():
                c = _chunks.get(cid)
                if c:
                    c.update(cas=loc["cas"], ofs=loc["ofs"], csize=loc["csize"], missing=0, orphan=1,
                             stored=loc.get("size"))
                    by_sha[c["sha1"]] = c
            for cid, c in _chunks.items():  # те же байты под другим GUID
                if c.get("missing") and c["sha1"] in by_sha:
                    src = by_sha[c["sha1"]]
                    c.update(cas=src["cas"], ofs=src["ofs"], csize=src["csize"], missing=0, orphan=1,
                             stored=src.get("stored"))
        tp = os.path.join(CAT, "toc_chunks.json")
        if os.path.exists(tp):  # оглавления (.toc): точное место каждого чанка — главнее догадок прохода без TOC
            with open(tp, encoding="utf-8") as f:
                toc = json.load(f)
            for cid, t in toc.items():
                c = _chunks.get(cid)
                rec = {"cas": t["cas"], "ofs": t["ofs"], "csize": t["csize"], "missing": 0, "toc": 1,
                       "toc_sha1": t.get("sha1")}  # sha1 есть только у мест из записей бандлов (поток бандла)
                if c is None:
                    rec.update(lo=t.get("lo"), ls=t.get("ls"), sha1=t.get("sha1"))
                    _chunks[cid] = rec
                elif c.get("lo") and c.get("orphan") and c.get("stored") == (c.get("lo") or 0) + c["ls"]:
                    continue  # уже есть целый поток (найден по sha1, с мипом 0) — лучше хвоста из записи бандла
                else:
                    c.update(rec)
                    c.pop("stored", None)
    return _chunks


def textures(regex):
    rx = re.compile(regex)
    seen = {}
    with open(os.path.join(CAT, "textures.csv"), encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if rx.search(r["name"]) and r["ofs"] and r["name"] not in seen:
                seen[r["name"]] = r
    return list(seen.values())


def read_header(r):
    d, _ = cas.read_entry(cas_file(r["cas"]), int(r["ofs"]), int(r["size"]))
    return texture.parse_header(d)


def read_chunk(h):
    """-> (данные, номер мипа, с которого они начинаются) или (None, 0).

    Место — из оглавлений (.toc), если есть: тогда читается весь сохранённый поток [ofs, ofs+csize) и по его длине
    понятно, целый это чанк или только хвост мипов с first_mip. Без TOC — как раньше (sha1-сверка мест прохода)."""
    c = chunks().get(h["chunk"])
    if not c or c.get("missing"):
        return None, 0
    if c.get("toc"):
        d = cas.read_stored(cas_file(c["cas"]), c["ofs"], c["csize"])
        full = sum(h["mip_sizes"])
        tail = sum(h["mip_sizes"][h["first_mip"]:])
        if c.get("toc_sha1") and not c.get("lo") and VERIFY:
            # место из записи бандла — сверка с sha1 манифеста; у частичного чанка (lo > 0) запись TOC указывает на
            # хвост внутри потока, а sha1 манифеста — от всего потока, так что там не сверяем
            import hashlib
            f = cas_file(c["cas"])
            f.seek(c["ofs"])
            if hashlib.sha1(f.read(c["csize"])).hexdigest() != c["toc_sha1"]:
                raise ValueError("sha1 не совпал (место из записи бандла в TOC)")
        if len(d) >= full:
            return d, 0
        if len(d) >= tail:
            return d, h["first_mip"]
        raise ValueError(f"поток {len(d)} Б меньше хвоста мипов {tail} Б")
    lo, ls = c["lo"] or 0, c["ls"]
    stored = c.get("stored") or (ls if (lo and not c.get("orphan")) else lo + ls)
    if VERIFY and c.get("csize"):
        # проход без TOC мог перепутать два чанка одного размера в бандле (свой лежит не здесь, а здесь — соседний):
        # сверка sha1 сжатых байт с манифестом
        import hashlib
        f = cas_file(c["cas"])
        f.seek(c["ofs"])
        if hashlib.sha1(f.read(c["csize"])).hexdigest() != c["sha1"]:
            raise ValueError("sha1 не совпал: на этом месте чужой чанк (перепутан при проходе без TOC)")
    d, _ = cas.read_entry(cas_file(c["cas"]), c["ofs"], stored)
    start = 0
    if lo and stored == ls:
        start = h["first_mip"]
    return d, start


def out_name(name):
    return name[len("content/"):] if name.startswith("content/") else name


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("regex")
    ap.add_argument("--out", default="misc")
    ap.add_argument("--mip", type=int, default=0)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--list", action="store_true", help="только заголовки, без PNG")
    a = ap.parse_args()
    rows = textures(a.regex)
    if a.limit:
        rows = rows[:a.limit]
    base = os.path.join(WORK, "extract", a.out)
    os.makedirs(base, exist_ok=True)
    idx = []
    ok = miss = bad = 0
    for r in rows:
        h = read_header(r)
        rec = {"name": r["name"], "format": texture.format_name(h["format"]), "w": h["width"], "h": h["height"],
               "mips": h["mips"], "slices": h["slices"], "group": h["group"], "chunk": h["chunk"], "status": ""}
        if a.list:
            c = chunks().get(h["chunk"])
            rec["status"] = "missing" if (not c or c.get("missing")) else "ok"
            idx.append(rec)
            continue
        try:
            data, start = read_chunk(h)
        except Exception as e:  # noqa: BLE001
            data, start = None, 0
            rec["status"] = f"error: {e}"
        if data is None and rec["status"]:
            bad += 1
        elif data is None:
            rec["status"] = "missing"
            miss += 1
        else:
            try:
                lvl = min(max(a.mip, start), max(h["mips"] - 1, 0))
                img = texture.decode_mip(h, data, lvl, data_first=start)
                p = os.path.join(base, out_name(r["name"]) + ".png")
                os.makedirs(os.path.dirname(p), exist_ok=True)
                img.save(p)
                rec["status"] = "ok"
                rec["png"] = os.path.relpath(p, base)
                ok += 1
            except Exception as e:  # noqa: BLE001
                rec["status"] = f"error: {e}"
                bad += 1
        idx.append(rec)
    with open(os.path.join(base, "_index.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["name", "format", "w", "h", "mips", "slices", "group", "chunk", "status", "png"])
        w.writeheader()
        for rec in idx:
            w.writerow(rec)
    st = {}
    for rec in idx:
        st[rec["status"].split(":")[0]] = st.get(rec["status"].split(":")[0], 0) + 1
    print(f"{len(idx)} текстур: {st} -> {base}")


if __name__ == "__main__":
    sys.exit(main())
