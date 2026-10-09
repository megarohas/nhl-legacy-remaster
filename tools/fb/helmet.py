"""Наклейки на шлем (спонсор или логотип) NHL 24 → NHL Legacy: rendering/logo/texlib_<art>_1_<вариант>.rx2. Офлайн.

NHL 24: content/character/skater/league/nhl/<клуб>/adidas/<форма>/helmetlogo_adidas_<клуб>_<форма>_0_color
(1024×512, прозрачный фон; у SEA — Amazon). Legacy: растр logo_<A>_1_<V>_0 (256×128 DXT5) — наклейка по центру
(128; 58,5), рамка около 102×81 (docs/uniforms.md); растры _1 (128×64) и _2 (128×128) у EA пустые. Наклейка из NHL 24
вписывается в рамку по альфе с сохранением пропорций. Шлем грузит наклейку только при stockteamjerseys.helmetlogo = 1
(флаг ставит legacy-data).

  python -m fb.helmet build     # -> pack/cache/rendering/logo/…, pack/new/<КОД>_<метка>/helmet_logo_0.png, _parts/helmet.json
  python -m fb.helmet sheet     # -> compare/helmet_logos.png (Legacy сейчас | из NHL 24)
"""
import argparse
import csv
import json
import os
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .cas import REPO
from .kit_batch import ADIDAS, CLUBS, NHL24, legacy_target
from .pack import CACHE, PACK, TOOLS, legacy_has, md5, save_part

SRC = os.path.join(NHL24, "extract", "helmet24")
FRAME = (176, 88)   # по замерам 152 наклеек EA в Legacy: квадратные ~89×86, широкие ~159×44, максимум 192×109
CENTER = (127.5, 58.0)
EXCLUDE = {"ARI": "ARI → Utah, не ставить"}
# шаблон файла под новый номер — по длине «A_1_V» (имена растров logo_A_1_V_k переписываются на месте, длина та же):
# 6_1_0 → texlib_0_1_0, 6_1_10 и 10_1_0 → texlib_10_1_0, 127_1_0 → texlib_127_1_0
TEMPLATES = {5: "rendering/logo/texlib_0_1_0.rx2", 6: "rendering/logo/texlib_10_1_0.rx2",
             7: "rendering/logo/texlib_127_1_0.rx2"}


def template_for(art, variant):
    """-> (свой файл Legacy или None, файл-шаблон)."""
    have = legacy_has(f"rendering/logo/texlib_{art}_1_{variant}.rx2")
    return have, have or legacy_has(TEMPLATES[len(f"{art}_1_{variant}")])


def decal(club, kit):
    n = f"content/character/skater/league/nhl/{club}/adidas/{kit}/helmetlogo_adidas_{club}_{kit}_0_color"
    with open(os.path.join(SRC, "_index.csv"), encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["name"] == n and r["status"] == "ok":
                return Image.open(os.path.join(SRC, r["png"])).convert("RGBA")
    return None


def fit(img):
    """Вписать по альфе в рамку FRAME с центром CENTER на холсте 256×128."""
    a = np.asarray(img)[..., 3]
    ys, xs = np.nonzero(a > 16)
    out = Image.new("RGBA", (256, 128), (0, 0, 0, 0))
    if len(xs) == 0:
        return None
    crop = img.crop((xs.min(), ys.min(), xs.max() + 1, ys.max() + 1))
    s = min(FRAME[0] / crop.size[0], FRAME[1] / crop.size[1])
    nw, nh = max(1, round(crop.size[0] * s)), max(1, round(crop.size[1] * s))
    crop = crop.resize((nw, nh), Image.LANCZOS)
    out.alpha_composite(crop, (int(round(CENTER[0] - nw / 2)), int(round(CENTER[1] - nh / 2))))
    return out


def write_logo(tpl_path, art, variant, logo, out_path):
    sys.path.insert(0, TOOLS)
    import teamart as ta
    rw = ta.Rw4.load(tpl_path)
    import re
    for i, (sp, ln) in enumerate(rw.name_slots):  # logo_<A>_1_<V>_k целиком: арт и вариант могут поменять длину
        s = rw.raw[sp:sp + ln].decode("latin1")     # по отдельности (10_1_0 → 6_1_10), общая длина — та же
        t = re.sub(r"^logo_\d+_1_\d+_", f"logo_{art}_1_{variant}_", s)
        if len(t) != len(s):
            raise ValueError(f"{art}_1_{variant}: длина имени растра меняется ({s}) — нужен шаблон той же длины")
        rw.raw[sp:sp + ln] = t.encode("latin1")
        if i < len(rw.textures):
            rw.textures[i].name = t
    for i, t in enumerate(rw.textures):
        lv = t.layout.levels
        w, h = lv[0][:2]
        src = logo if i == 0 else Image.new("RGBA", (w, h), (0, 0, 0, 0))
        if src.size != (w, h):
            src = src.resize((w, h), Image.LANCZOS)
        levels = []
        for L in lv:
            lw, lh = L[:2]
            im = src if (lw, lh) == src.size else src.resize((lw, lh), Image.BOX)
            levels.append((lw, lh, im.tobytes()))
        rw.replace(t, levels)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "wb") as f:
        f.write(rw.bytes())
    return [t.name for t in rw.textures]


def cmd_build(a):
    entries = []
    for club, art, code in CLUBS:
        for kit, label, loc in ADIDAS:
            img = decal(club, kit)
            if img is None:
                continue
            logo = fit(img)
            if logo is None:  # пустая наклейка (у twentythree часто) — пропуск
                continue
            tgt = legacy_target(art, loc)
            if code in EXCLUDE:
                entries.append({"type": "наклейка на шлем", "club": code, "kit": label, "action": "excluded",
                                "reason": EXCLUDE[code]})
                continue
            if not tgt:
                odir = os.path.join(PACK, "new", f"{code}_{label}")
                os.makedirs(odir, exist_ok=True)
                p = os.path.join(odir, "helmet_logo_0.png")
                logo.save(p)
                entries.append({"type": "наклейка на шлем", "club": code, "kit": label, "file": f"new/{code}_{label}/helmet_logo_0.png",
                                "action": "add_new (растр logo_<арт>_1_<вариант>_0, 256×128; номер назначит legacy-data)",
                                "md5": md5(p), "size": os.path.getsize(p), "db": "helmetlogo = 1"})
                continue
            v = tgt["variant"]
            rel = f"rendering/logo/texlib_{art}_1_{v}.rx2"
            have, tpl = template_for(art, v)
            names = write_logo(tpl, art, v, logo, os.path.join(CACHE, rel))
            entries.append({"type": "наклейка на шлем", "club": code, "kit": label, "file": rel,
                            "action": "replace" if have else "add",
                            "md5": md5(os.path.join(CACHE, rel)), "size": os.path.getsize(os.path.join(CACHE, rel)),
                            "rasters": names, "db": "stockteamjerseys.helmetlogo = 1",
                            "template": os.path.relpath(tpl, REPO).replace("\\", "/")})
            print(code, label, "->", rel, "replace" if have else "add (новый файл)", flush=True)
    save_part("helmet", entries)


def cmd_sheet(a):
    sys.path.insert(0, TOOLS)
    import teamart as ta
    try:
        font = ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", 15)
    except OSError:
        font = ImageFont.load_default()
    with open(os.path.join(PACK, "_parts", "helmet.json"), encoding="utf-8") as f:
        ent = json.load(f)
    W, H = 256, 128
    cols = 3
    rows = (len(ent) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * (2 * W + 30), rows * (H + 30) + 10), (60, 64, 70))
    d = ImageDraw.Draw(sheet)
    for i, e in enumerate(ent):
        x = (i % cols) * (2 * W + 30) + 10
        y = (i // cols) * (H + 30) + 10
        d.text((x, y), f"{e['club']} {e['kit']}: Legacy сейчас | из NHL 24 ({e['action'][:9]})", fill=(240, 240, 240),
               font=font)
        if e.get("action") == "excluded":
            d.text((x + 10, y + 50), e["reason"], fill=(240, 150, 150), font=font)
            continue
        cur = legacy_has(e["file"]) if e["file"].startswith("rendering/") else None
        if cur:
            rw = ta.Rw4.load(cur)
            w, h, rgba = rw.decode(rw.textures[0])
            sheet.paste(Image.alpha_composite(Image.new("RGBA", (w, h), (110, 110, 110, 255)),
                                              Image.frombytes("RGBA", (w, h), bytes(rgba))).convert("RGB"), (x, y + 20))
        newp = os.path.join(CACHE, e["file"]) if e["file"].startswith("rendering/") else os.path.join(PACK, e["file"])
        if newp.endswith(".rx2"):
            rw = ta.Rw4.load(newp)
            w, h, rgba = rw.decode(rw.textures[0])
            im = Image.frombytes("RGBA", (w, h), bytes(rgba))
        else:
            im = Image.open(newp).convert("RGBA")
        sheet.paste(Image.alpha_composite(Image.new("RGBA", im.size, (110, 110, 110, 255)), im).convert("RGB"),
                    (x + W + 10, y + 20))
    out = os.path.join(NHL24, "compare", "helmet_logos.png")
    sheet.save(out)
    print(out, sheet.size)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("build")
    sub.add_parser("sheet")
    a = ap.parse_args()
    return {"build": cmd_build, "sheet": cmd_sheet}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
