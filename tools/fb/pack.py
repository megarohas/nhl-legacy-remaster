"""Упаковка готового из NHL 24 в формат NHL Legacy (только файлы, в игру не ставится): game/work/nhl24/out/pack/.

  python -m fb.pack jerseys     # свитер + шрифт: kitpaint pack по kit.json шаблона → cache/rendering/jersey/texlib_*
  python -m fb.pack new         # новые формы (нет строки Legacy): только PNG в размерах Legacy → pack/new/<КОД>_<метка>/
  python -m fb.pack centers     # центр льда: teamart.Rw4 по шаблону → cache/rendering/icesurface/centerlogo_<art>_cm.rx2
  python -m fb.pack manifest    # pack/manifest.json: тип, файл Legacy, заменяется/добавляется, md5, клуб/форма

pack/cache/ — дерево «как в cache:» Legacy: свободные несжатые RW4, перекрывают архивы (ставит legacy-data).
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys

import numpy as np
from PIL import Image

from .cas import REPO
from .kit_batch import CLUBS, LEG, NHL24, OUT, OUT_NEW

PACK = os.path.join(NHL24, "out", "pack")
CACHE = os.path.join(PACK, "cache")
TMP = os.path.join(PACK, "_build")
LEGACY_BIG = os.path.join(REPO, "game", "other", "legacy", "big")
OURS = os.path.join(REPO, "game", "work", "legacy-data", "out")   # наши SEA/VGK (100/101), уже собранные czkit/teamart
TOOLS = os.path.join(REPO, "tools")
CHANGED = ("jersey_cm", "jersey_sm", "jersey_nm", "font_cm", "font_nm", "font_sm")
SIZES = {"jersey_cm": 1024, "jersey_sm": 1024, "jersey_nm": 1024, "font_cm": 512, "font_nm": 512, "font_sm": 512}


def md5(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def legacy_has(rel):
    """Есть ли файл в архивах Legacy (распакованные game/other/legacy/big/<архив>/)."""
    for d in sorted(os.listdir(LEGACY_BIG)):
        if os.path.exists(os.path.join(LEGACY_BIG, d, rel)):
            return os.path.join(LEGACY_BIG, d, rel)
    return None


def log_entry(entries, **kw):
    p = os.path.join(CACHE, kw["file"]) if kw.get("where", "cache") == "cache" else kw.pop("abs")
    kw.setdefault("md5", md5(p))
    kw.setdefault("size", os.path.getsize(p))
    entries.append(kw)


def stage(kdir, sizes=None):
    """Слои PNG в размерах шаблона (kit.json): кому не хватает — пересэмплирование (у чистого sm Legacy 512² → 1024²)."""
    sdir = os.path.join(TMP, "stage", os.path.basename(kdir))
    os.makedirs(sdir, exist_ok=True)
    meta = json.load(open(os.path.join(kdir, "kit.json"), encoding="utf-8"))
    for ln in CHANGED:
        src = os.path.join(kdir, ln + ".png")
        if not os.path.exists(src):
            continue
        L = meta["layers"].get(ln)
        im = Image.open(src)
        if L and im.size != (L["w"], L["h"]):
            im = im.resize((L["w"], L["h"]), Image.LANCZOS)
        im.save(os.path.join(sdir, ln + ".png"))
    shutil.copyfile(os.path.join(kdir, "kit.json"), os.path.join(sdir, "kit.json"))
    return sdir


def cmd_jerseys(a):
    entries = []
    for d in sorted(os.listdir(OUT)):
        kdir = os.path.join(OUT, d)
        info = os.path.join(kdir, "info.json")
        if not os.path.exists(info) or not os.path.exists(os.path.join(kdir, "kit.json")):
            continue
        rec = json.load(open(info, encoding="utf-8"))
        if rec.get("status") != "ok" or not rec.get("legacy"):
            continue
        newkit = rec["legacy"]["kit"]
        sdir = stage(kdir)
        odir = os.path.join(TMP, "kitpaint", d)
        r = subprocess.run([sys.executable, os.path.join(TOOLS, "kitpaint.py"), "pack", sdir, newkit, odir, "--game",
                            "legacy"], capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=TOOLS)
        rel = rec["legacy"]["file"]
        built = os.path.join(odir, rel)
        if r.returncode != 0 or not os.path.exists(built):
            print(d, "ОШИБКА pack:", (r.stdout + r.stderr).strip().splitlines()[-1:] if (r.stdout + r.stderr) else "")
            continue
        dst = os.path.join(CACHE, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copyfile(built, dst)
        ours = rec["art"] in (100, 101)
        log_entry(entries, type="свитер+шрифт", club=rec["code"], kit=rec["label"], file=rel.replace("\\", "/"),
                  action="replace_ours" if ours else "replace", legacy_kit=newkit,
                  layers=[ln for ln in CHANGED if os.path.exists(os.path.join(kdir, ln + ".png"))],
                  source=f"NHL 24 {rec['family']}/{rec['kit']}", hastie_want=0,
                  note=("наш комплект czkit заменяется; контейнер " + rec["legacy"].get("template", "")) if ours else "")
        print(d, "->", rel, flush=True)
    save_part("jerseys", entries)


def cmd_new(a):
    entries = []
    for d in sorted(os.listdir(OUT_NEW)) if os.path.exists(OUT_NEW) else []:
        kdir = os.path.join(OUT_NEW, d)
        info = os.path.join(kdir, "info.json")
        if not os.path.exists(info):
            continue
        rec = json.load(open(info, encoding="utf-8"))
        if rec.get("status") != "ok":
            continue
        odir = os.path.join(PACK, "new", d)
        os.makedirs(odir, exist_ok=True)
        files = []
        for ln, size in SIZES.items():
            src = os.path.join(kdir, ln + ".png")
            if not os.path.exists(src):
                continue
            im = Image.open(src)
            if im.size != (size, size):
                im = im.resize((size, size), Image.LANCZOS)
            im.save(os.path.join(odir, ln + ".png"))
            files.append(ln + ".png")
        shutil.copyfile(info, os.path.join(odir, "info.json"))
        for fn in files:
            p = os.path.join(odir, fn)
            entries.append({"type": "новая форма: текстуры", "club": rec["code"], "kit": rec["label"],
                            "file": f"new/{d}/{fn}", "action": "add_new (номер арта и строку базы назначает legacy-data)",
                            "md5": md5(p), "size": os.path.getsize(p), "source": f"NHL 24 {rec['family']}/{rec['kit']}",
                            "legacy_layer": fn[:-4], "hastie_want": 0})
        print(d, len(files), "PNG", flush=True)
    save_part("new", entries)


def centerlogo_template(art):
    rel = f"rendering/icesurface/centerlogo_{art}_cm.rx2"
    ours = os.path.join(OURS, rel)
    if art in (100, 101) and os.path.exists(ours):
        return ours, True
    p = legacy_has(rel)
    return p, False


def write_rx2_rgba(tpl_path, rgba_img, out_path):
    """Шаблон RW4 (одна текстура) → те же заголовки, пиксели — из картинки (все мипы)."""
    sys.path.insert(0, TOOLS)
    import teamart as ta
    rw = ta.Rw4.load(tpl_path)
    t = rw.textures[0]
    lv = t.layout.levels
    w, h = lv[0][:2]
    im = rgba_img.convert("RGBA")
    if im.size != (w, h):
        im = im.resize((w, h), Image.LANCZOS)
    levels = []
    cur = im
    for i, L in enumerate(lv):
        lw, lh = L[:2]
        if cur.size != (lw, lh):
            # уменьшение с премультипликацией альфы (как ta.downsample2), быстро — numpy
            arr = np.asarray(im).astype(np.float32)
            a = arr[..., 3:4] / 255.0
            pre = np.concatenate([arr[..., :3] * a, arr[..., 3:4]], -1)
            ch = [np.asarray(Image.fromarray(pre[..., k]).resize((lw, lh), Image.BOX)) for k in range(4)]
            o = np.stack(ch, -1)
            al = np.clip(o[..., 3:4], 0, 255)
            rgb = np.where(al > 0.5, o[..., :3] / np.maximum(al / 255.0, 1e-3), 0)
            cur = Image.fromarray(np.clip(np.concatenate([rgb, al], -1), 0, 255).astype(np.uint8), "RGBA")
        levels.append((lw, lh, cur.tobytes()))
    rw.replace(t, levels)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "wb") as f:
        f.write(rw.bytes())


def cmd_centers(a):
    entries = []
    src_dir = os.path.join(NHL24, "out", "ice")
    for club, art, code in CLUBS:
        png = os.path.join(src_dir, f"centerlogo_{code}.png")
        tpl, ours = centerlogo_template(art)
        if not os.path.exists(png) or not tpl:
            print(code, "нет", "PNG" if not os.path.exists(png) else "шаблона")
            continue
        rel = f"rendering/icesurface/centerlogo_{art}_cm.rx2"
        write_rx2_rgba(tpl, Image.open(png), os.path.join(CACHE, rel))
        log_entry(entries, type="центр льда", club=code, kit="", file=rel, action="replace_ours" if ours else "replace",
                  source=f"NHL 24 ice_centerlogo ({code})", template=os.path.relpath(tpl, REPO).replace("\\", "/"))
        print(code, "->", rel, flush=True)
    save_part("centers", entries)


def save_part(name, entries):
    os.makedirs(os.path.join(PACK, "_parts"), exist_ok=True)
    with open(os.path.join(PACK, "_parts", name + ".json"), "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=1)
    print(f"{name}: {len(entries)} записей")


def cmd_manifest(a):
    parts = {}
    pdir = os.path.join(PACK, "_parts")
    for fn in sorted(os.listdir(pdir)):
        with open(os.path.join(pdir, fn), encoding="utf-8") as f:
            parts[fn[:-5]] = json.load(f)
    allx = [e for v in parts.values() for e in v]
    man = {"what": "NHL 24 → NHL Legacy: файлы для установки в cache: (pack/cache/...) и текстуры новых форм (pack/new/...)",
           "install_root": "cache: Legacy — nhl-legacy-port/userdata/cache/guest/ (свободные несжатые RW4 перекрывают архивы)",
           "decisions": {"hastie": 0, "neck_shield": "-4 см", "v_insert": "цвет свитера под воротом",
                         "relief": "sm/nm — чистые карты Legacy (T=4)"},
           "counts": {k: len(v) for k, v in parts.items()}, "files": allx}
    with open(os.path.join(PACK, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(man, f, ensure_ascii=False, indent=1)
    print("manifest.json:", man["counts"], "всего", len(allx))


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    for c in ("jerseys", "new", "centers", "manifest"):
        sub.add_parser(c)
    a = ap.parse_args()
    return {"jerseys": cmd_jerseys, "new": cmd_new, "centers": cmd_centers, "manifest": cmd_manifest}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
