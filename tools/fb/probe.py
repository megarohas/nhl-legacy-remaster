"""Первое знакомство с дампом Frostbite: читается ли он нашими инструментами (только чтение, без каталога).

    python -m fb.probe [ПАПКА_Data] [--cas N] [--blocks 400]

Проверяет по порядку (docs/frostbite-sources.md, «Первое знакомство»):
  1. дерево: платформенная папка (initfs_<платформа>), *.toc, superbundlelayout/<пакет>NN/cas_NN.cas, Patch рядом;
  2. подписи TOC и initfs (00D1CE01) и DbObject после заголовка 0x22C (layout.toc, initfs — открыт ли);
  3. оглавления: заголовок (hdr[0] = 0x3C у NHL 24), бандлы, чанки, байт patch, ссылки на несуществующие CAS;
  4. первый CAS: манифест бандла в начале, блоки (типы сжатия, флаги 0x7X), пробная распаковка блока каждого типа;
  5. один чанк по месту из TOC: read_stored.
В конце — что выставить (FB_DATA, FB_PLATFORM, FB_PACKAGE) и что делать дальше. Ожидаемое — по NHL 24 PS4.
"""
import argparse
import collections
import glob
import os
import re
import sys

from . import bundle, cas, dbobject, source, toc

OK, WARN, BAD = "ok  ", "!!  ", "НЕТ "


def say(mark, text):
    print(f"  {mark}{text}", flush=True)


def mb(n):
    return f"{n / 2**20:,.1f} МБ".replace(",", " ")


def find_platform(data):
    ini = sorted(glob.glob(os.path.join(data, "initfs_*")))
    if ini:
        return os.path.basename(ini[0])[len("initfs_"):]
    for d in sorted(os.listdir(data)):
        if os.path.isdir(os.path.join(data, d, "superbundlelayout")):
            return d
    return None


def package_prefix(layout):
    names = [d for d in os.listdir(layout) if os.path.isdir(os.path.join(layout, d))] if os.path.isdir(layout) else []
    pre = collections.Counter(re.sub(r"\d+$", "", n) for n in names)
    return (pre.most_common(1)[0][0] if pre else None), sorted(names)


def summarize_dbobject(raw, pos=0x22C, limit=6):
    try:
        v = dbobject.loads(raw, pos)
    except Exception as e:                                         # noqa: BLE001
        return None, f"не DbObject ({type(e).__name__}: {e})"
    if isinstance(v, dict):
        keys = list(v)[:limit]
        return v, "DbObject: ключи " + ", ".join(keys) + (" …" if len(v) > limit else "")
    return v, f"DbObject: {type(v).__name__}"


def cas_file_of(layout, prefix, catalog, casn):
    return os.path.join(layout, f"{prefix}{catalog:02d}", f"cas_{casn:02d}.cas")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("data", nargs="?", default=source.DATA, help="папка Data дампа (по умолчанию — fb.source.DATA)")
    ap.add_argument("--cas", type=int, default=0, help="какой по счёту CAS смотреть в шаге 4")
    ap.add_argument("--blocks", type=int, default=400, help="сколько блоков пройти в шаге 4")
    a = ap.parse_args()
    data = os.path.abspath(a.data)
    hints = []
    print(f"дамп: {data}")
    if not os.path.isdir(data):
        sys.exit("нет такой папки")

    print("\n1. Дерево")
    plat = find_platform(data)
    say(OK if plat else BAD, f"платформенная папка: {plat or '—'}" + ("  (NHL 24 PS4 — Gen4b)" if plat else
                                                                      "  — ни initfs_*, ни */superbundlelayout"))
    if plat and plat != "Gen4b":
        hints.append(f"FB_PLATFORM={plat}")
    files = sorted(os.listdir(data))
    say(OK, "в Data: " + ", ".join(files[:14]) + (" …" if len(files) > 14 else ""))
    patch = os.path.join(os.path.dirname(data), "Patch")
    say(WARN if os.path.isdir(patch) else OK, "Patch рядом: " + ("есть — записи TOC с patch ≠ 0 читаются оттуда"
                                                                 if os.path.isdir(patch) else "нет"))
    pdir = os.path.join(data, plat) if plat else data
    tocs = [os.path.join(data, "layout.toc")] if os.path.exists(os.path.join(data, "layout.toc")) else []
    tocs += sorted(glob.glob(os.path.join(pdir, "*.toc"))) + sorted(glob.glob(os.path.join(pdir, "levels", "*", "*.toc")))
    sbs = glob.glob(os.path.join(pdir, "**", "*.sb"), recursive=True)
    say(OK if tocs else BAD, f"оглавлений *.toc: {len(tocs)}" + (", отдельных *.sb: %d (у NHL 24 их нет — бандлы в CAS)"
                                                                % len(sbs) if sbs else ""))
    layout = os.path.join(pdir, "superbundlelayout")
    prefix, pkgs = package_prefix(layout)
    cass = sorted(glob.glob(os.path.join(layout, "*", "cas_*.cas")))
    total = sum(os.path.getsize(c) for c in cass)
    say(OK if cass else BAD, f"пакетов {len(pkgs)} (префикс «{prefix}»), CAS {len(cass)}, {mb(total)}")
    if prefix and prefix != "nhl_installpackage_":
        hints.append(f"FB_PACKAGE={prefix}")

    print("\n2. Подписи и DbObject")
    for p in [x for x in tocs if os.path.basename(x) == "layout.toc"] + sorted(glob.glob(os.path.join(data, "initfs_*"))):
        raw = open(p, "rb").read()
        sig = raw[:4].hex()
        signed = sig == "00d1ce01"
        say(OK, f"{os.path.basename(p)}: " + ("подпись 00d1ce01 + заголовок 0x22C (как NHL 24)" if signed else
                                              f"без подписи (как NHL 27 PS5), начало {sig}") + f", {len(raw)} байт")
        v, s = summarize_dbobject(raw, 0x22C if signed else 0)
        enc = isinstance(v, dict) and "encrypted" in v
        say(WARN if enc or v is None else OK, s + ("  — зашифрован (у NHL 24 так же)" if enc else ""))
        if isinstance(v, dict) and "superBundles" in v:
            names = [sb.get("name") for sb in v["superBundles"] if isinstance(sb, dict)]
            say(OK, "суперандлы: " + ", ".join(map(str, names[:10])) + (" …" if len(names) > 10 else ""))

    print("\n3. Оглавления")
    refs = collections.Counter()
    patches = collections.Counter()
    first_chunk = None
    for p in tocs:
        if os.path.basename(p) == "layout.toc":
            continue
        try:
            r = toc.read_toc(p)
        except Exception as e:                                     # noqa: BLE001
            say(BAD, f"{os.path.relpath(p, data)}: {type(e).__name__}: {e}")
            continue
        nent = sum(len(b) for b in r["bundles"])
        for b in r["bundles"]:
            for catalog, casn, pt, eo, es in b:
                refs[(catalog, casn)] += 1
                patches[pt] += 1
        for g, catalog, casn, pt, eo, es in r["chunks"]:
            refs[(catalog, casn)] += 1
            patches[pt] += 1
            if first_chunk is None and es:
                first_chunk = (catalog, casn, pt, eo, es, g)
        h0 = r["hdr"][0]
        say(OK if h0 == 0x3C else WARN, f"{os.path.relpath(p, data):34} hdr[0]=0x{h0:X}  бандлов {len(r['bundles']):6}"
            f" (записей {nent:7}), чанков {len(r['chunks']):6}")
    if patches:
        say(OK if set(patches) == {0} else WARN, "байт patch в записях: " + ", ".join(f"{k}: {v}" for k, v in
                                                                                   sorted(patches.items())))
    if prefix:
        missing = [k for k in refs if not os.path.exists(cas_file_of(layout, prefix, *k))]
        say(OK if not missing else WARN, f"CAS, на которые ссылаются оглавления: {len(refs)}, нет на диске: "
            f"{len(missing)}" + (f" (например ip{missing[0][0]:02d}/cas_{missing[0][1]:02d})" if missing else ""))

    print("\n4. Первый CAS")
    if not cass:
        say(BAD, "CAS нет")
    else:
        cp = cass[min(a.cas, len(cass) - 1)]
        say(OK, os.path.relpath(cp, data) + f", {mb(os.path.getsize(cp))}")
        with open(cp, "rb") as f:
            h = f.read(8)
            man = bundle.is_manifest(h)
            say(OK if man else WARN, "в начале — " + ("манифест бандла (BE-размер + LE-магия 9D798ED5/6)" if man else
                                                     f"не манифест: {h.hex()}"))
            types = collections.Counter()
            tried, errors, n, nman, pos = set(), [], 0, 0, 0
            end = os.path.getsize(cp)
            while n < a.blocks and pos < end:          # манифест → его блоки → следующий манифест …
                f.seek(pos)
                hh = f.read(8)
                if bundle.is_manifest(hh):
                    nman += 1
                    pos += 4 + int.from_bytes(hh[:4], "big")
                    continue
                moved = False
                for bpos, usize, ctype, csize in cas.block_iter(f, pos):
                    moved = True
                    types[ctype] += 1
                    n += 1
                    pos = bpos + 8 + (usize if (ctype & 0x7F) == 0 else csize)
                    if ctype not in tried:
                        tried.add(ctype)
                        f.seek(bpos + 8)
                        payload = f.read(usize if (ctype & 0x7F) == 0 else csize)
                        try:
                            out = cas.decompress_block(ctype, usize, payload)
                            if len(out) != usize:
                                errors.append(f"0x{ctype:02x}: {len(out)} из {usize}")
                        except Exception as e:                     # noqa: BLE001
                            errors.append(f"0x{ctype:02x}: {type(e).__name__}: {e}")
                    if n >= a.blocks:
                        break
                if not moved:                               # ни манифест, ни блок — дальше не идём (у NHL 24 — gap)
                    break
            say(OK, f"манифестов бандлов по пути: {nman}")
            known = {0x00: "без сжатия", 0x02: "zlib", 0x0F: "ZStd", 0x11: "Oodle", 0x15: "Oodle Kraken",
                     0x19: "Oodle"}
            say(OK if n else BAD, f"блоков пройдено {n}: " + ", ".join(f"0x{t:02x} {known.get(t & 0x7F, '?')} ×{c}"
                                                                     for t, c in types.most_common()))
            if not n:
                say(BAD, "после манифеста не блок CAS (флаги не 0x7X или размер > 1 МБ) — формат блока другой")
            for e in errors:
                say(BAD, "распаковка " + e)
            if n and not errors:
                say(OK, "пробная распаковка блока каждого типа — без ошибок")

    print("\n5. Чанк по месту из TOC")
    if first_chunk and prefix:
        catalog, casn, pt, eo, es, g = first_chunk
        cp = cas_file_of(layout, prefix, catalog, casn)
        if os.path.exists(cp):
            try:
                with open(cp, "rb") as f:
                    out = cas.read_stored(f, eo, es)
                say(OK, f"чанк {g}: {es} байт в CAS → {len(out)} распаковано")
            except Exception as e:                                 # noqa: BLE001
                say(BAD, f"чанк {g}: {type(e).__name__}: {e}")
        else:
            say(WARN, f"CAS чанка нет на диске: {cp}")
    else:
        say(WARN, "в оглавлениях нет записей чанков")

    print("\nДальше")
    env = " ".join(hints)
    print(f"  переменные: FB_DATA={data}" + (f" {env}" if env else "") +
          ("  (+ FB_GAME / FB_WORK — своя рабочая папка)" if data != source.DATA else ""))
    print("  1) python -m fb.scan --only <пакет>/<cas> (один CAS) и python -m fb.catalog — в restypes.csv должны быть"
          " 0x6BDE20BA (Texture) и 0x49B156D4 (MeshSet)")
    print("  2) python -m fb.toc index; python -m fb.extract '<узнаваемая текстура>' --list, потом PNG — "
          "детайлинг PS4 на PS5 даст мусор (fb/texture.py)")
    print("  3) сетка-эталон (свитер, голова) — смещения MeshSet; см. docs/frostbite-sources.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
