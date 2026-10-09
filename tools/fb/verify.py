"""Сверка sha1 всего, из чего собраны выходы пакета (fb.kit_batch, fb.ice, fb.fonts): заголовок текстуры (res) и
её чанк — sha1 сжатых байт в CAS против sha1 манифеста бандла. Без TOC проход по CAS мог перепутать записи одного
размера в бандле — эта проверка их ловит.

  python -m fb.verify            -> game/work/nhl24/out/verify.json + сводка
"""
import csv
import hashlib
import json
import os
import sys

from . import extract
from .cas import REPO
from .kit_batch import CLUBS, KITS

NHL24 = os.path.join(REPO, "game", "work", "nhl24")


def check_texture(name, rows_by_name):
    """-> (статус, подробности). Заголовок: запись res с местом; чанк: по GUID из заголовка."""
    r = rows_by_name.get(name)
    if r is None:
        return "нет в каталоге", {}
    f = extract.cas_file(r["cas"])
    f.seek(int(r["ofs"]))
    raw = f.read(int(r["csize"]))
    rec = {"res_sha1_ok": None, "chunk_sha1_ok": None}
    want = r.get("sha1")
    if want:
        rec["res_sha1_ok"] = hashlib.sha1(raw).hexdigest() == want
        if not rec["res_sha1_ok"]:
            return "заголовок: sha1 не совпал", rec
    h = extract.read_header(r)
    c = extract.chunks().get(h["chunk"])
    if not c or c.get("missing"):
        return "нет чанка", rec
    f = extract.cas_file(c["cas"])
    f.seek(c["ofs"])
    rec["chunk_sha1_ok"] = hashlib.sha1(f.read(c["csize"])).hexdigest() == c["sha1"]
    return ("ok" if rec["chunk_sha1_ok"] else "чанк: sha1 не совпал"), rec


def main():
    # записи res с местом и sha1 манифеста (textures.csv sha1 не хранит — берём из jsonl прохода)
    want = set()
    used = []
    for club, art, code in CLUBS:
        for kit in KITS:
            info = os.path.join(NHL24, "out", "kits", f"{code}_{kit}", "info.json")
            if os.path.exists(info):
                with open(info, encoding="utf-8") as f:
                    rec = json.load(f)
                if rec.get("status") in ("ok", "нет строки Legacy (стиль 1) для этой формы"):
                    base = f"content/character/skater/league/nhl/{club}/adidas/{kit}/jersey_adidas_{club}_{kit}_"
                    used.append(("свитер", code, kit, base + "color"))
                    if rec.get("mode") == "base" or str(rec.get("mode", "")).startswith("base;"):
                        used.append(("свитер base", code, kit, base + "base_color"))
            fb = f"content/character/skater/league/nhl/{club}/adidas/{kit}/font_adidas_{club}_{kit}_"
            if os.path.exists(os.path.join(NHL24, "out", "kits", f"{code}_{kit}", "font_cm.png")):
                used.append(("шрифт", code, kit, fb + "color"))
        n = {"vegas": 32, "seattle": 33}.get(club, art)
        used.append(("центр льда", code, "", f"content/worlds/rink/textures/centerlogo/ice_centerlogo_{n}_color"))
    want = {u[3] for u in used}
    rows = {}
    import glob
    for p in sorted(glob.glob(os.path.join(NHL24, "catalog", "scan", "*.jsonl"))):
        with open(p, encoding="utf-8") as f:
            for line in f:
                if '"k": "res"' not in line or '"ofs"' not in line:
                    continue
                r = json.loads(line)
                if r["name"] in want and r["name"] not in rows:
                    rows[r["name"]] = r
    out = []
    bad = 0
    for kind, code, kit, name in used:
        st, d = check_texture(name, rows)
        out.append({"kind": kind, "code": code, "kit": kit, "name": name, "status": st, **d})
        if st != "ok":
            bad += 1
            print(kind, code, kit, st, flush=True)
    with open(os.path.join(NHL24, "out", "verify.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    by = {}
    for o in out:
        k = (o["kind"], o["status"])
        by[k] = by.get(k, 0) + 1
    for k, v in sorted(by.items()):
        print(f"{k[0]:12s} {k[1]:28s} {v}")
    print(f"проверено {len(out)} текстур (заголовок + чанк), расхождений {bad}")


if __name__ == "__main__":
    sys.exit(main())
