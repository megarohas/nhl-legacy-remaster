"""Legacy-файлы NHL 24 (не-ebx файлы движка EA: базы, xml, json, csv) — список и выгрузка по имени. Только офлайн.

Где лежат (разобрано 12.10.2026 на дампе PS4): ebx `globals/chunkfilecollector` (ChunkFileCollector, 332 байта) —
по +0x60 GUID чанка-манифеста (16 байт как есть). Манифест (распакованный чанк):
  +0x0C u32 — число записей; записи с +0x68, по 0x38 байт:
    GUID чанка с данными (16 байт как есть), u64 смещение имени (C-строка в том же манифесте),
    u64, u64 (у файлов внутри общего чанка — место в сжатом потоке, не нужно), u64 смещение в распакованном
    чанке, u64 размер.
  Свой чанк у файла — смещение 0, размер = весь чанк.
Есть ещё сборщики globals/chunkfilecollectorui* (меню); их манифесты устроены так же (--collector).

Пример: gamemodes/database/t3db/nhl_game.db (база NHL 24, TDB little-endian, 13,7 МБ) и nhl_game-meta.xml (схема)
лежат в одном чанке ba0ebf21-…, смещения 1 112 613 и 523 714.

  python -m fb.lfs list [REGEX] [--collector globals/chunkfilecollector]
  python -m fb.lfs get NAME OUT_FILE [--collector …]
"""
import argparse
import json
import os
import re
import struct
import sys
import uuid

from . import cas
from .extract import CAT, cas_file, chunks

COLLECTOR = "globals/chunkfilecollector"
ENTRY0, ENTRY = 0x68, 0x38


def find_ebx(name):
    """Место ebx по имени из прохода fb.scan (catalog/scan/*.jsonl)."""
    key = f'"name": "{name}"'
    sd = os.path.join(CAT, "scan")
    for fn in sorted(os.listdir(sd)):
        with open(os.path.join(sd, fn), encoding="utf-8") as f:
            for line in f:
                if key in line and '"k": "ebx"' in line:
                    return json.loads(line)
    raise KeyError(f"ebx {name} нет в catalog/scan")


def read_chunk(guid):
    c = chunks().get(guid)
    if not c or c.get("missing"):
        raise KeyError(f"чанк {guid} не найден в дампе")
    if c.get("toc"):
        return cas.read_stored(cas_file(c["cas"]), c["ofs"], c["csize"])
    d, _ = cas.read_entry(cas_file(c["cas"]), c["ofs"], (c.get("lo") or 0) + c["ls"])
    return d


def manifest(collector=COLLECTOR):
    """[(имя, GUID чанка, смещение, размер)] из манифеста сборщика."""
    r = find_ebx(collector)
    ebx, _ = cas.read_entry(cas_file(r["cas"]), r["ofs"], r["size"])
    m = read_chunk(str(uuid.UUID(bytes=bytes(ebx[0x60:0x70]))))
    n = struct.unpack_from("<I", m, 0x0C)[0]
    out = []
    for i in range(n):
        o = ENTRY0 + i * ENTRY
        if o + ENTRY > len(m):
            break
        no, _, _, off, size = struct.unpack_from("<5Q", m, o + 16)
        if no >= len(m):
            continue
        name = m[no:m.index(b"\0", no)].decode("utf-8", "replace")
        out.append((name, str(uuid.UUID(bytes=bytes(m[o:o + 16]))), off, size))
    return out


def get(name, collector=COLLECTOR):
    for nm, guid, off, size in manifest(collector):
        if nm == name:
            d = read_chunk(guid)
            if off + size > len(d):
                raise ValueError(f"{name}: {off}+{size} за концом чанка ({len(d)})")
            return d[off:off + size]
    raise KeyError(f"{name} нет в манифесте {collector}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("list", "get"))
    ap.add_argument("args", nargs="*")
    ap.add_argument("--collector", default=COLLECTOR)
    a = ap.parse_args()
    if a.cmd == "list":
        rx = re.compile(a.args[0]) if a.args else None
        for nm, guid, off, size in manifest(a.collector):
            if rx is None or rx.search(nm):
                print(f"{size:>10} {guid} +{off:<9} {nm}")
    else:
        name, out = a.args
        data = get(name, a.collector)
        os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
        with open(out, "wb") as f:
            f.write(data)
        print(f"{name}: {len(data)} Б -> {out}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
