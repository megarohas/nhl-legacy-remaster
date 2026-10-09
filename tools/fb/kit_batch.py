"""Пакетный гибрид: свитера и шрифты 32 клубов NHL 24 → развёртки NHL Legacy. Только офлайн.

Комплекты: adidas home / away / three, спецформы adidas twentytwo / twentythree (Reverse Retro 2022/2023 → метки
rr22 / rr23) и все комплекты кроя nineties (ретро 90-х → n90_<комплект>), где в дампе есть чанк.

  python -m fb.kit_batch extract              # свитера (color, base_color) и шрифты (color, normal) в 2048²/1024²
  python -m fb.kit_batch run [--clubs SEA,BOS] [--labels home,away]
  python -m fb.kit_batch sheet LABEL          # лист рендеров спереди: compare/kits_<LABEL>.png (home, away, three,
                                              # rr22, rr23, nineties — все n90_* по клубам)

Решения пользователя (09.10): шнуровки нет ни у одного свитера (щит NHL −4 см у всех), V-вставка ворота Legacy — в
цвет свитера под воротом ([collar.v_insert] в kit_rules.toml), рельеф sm/nm — чистые карты Legacy (T=4).

Выход: комплект, у которого есть строка Legacy (stockteamjerseys стиля 1, locstring 0/1/2 этого клуба) —
game/work/nhl24/out/kits/<КОД>_<метка>/; новый (третья без строки, спецформы, ретро) — out/kits_new/<КОД>_<метка>/:
  jersey_cm.png (1024², гибрид), jersey_sm.png / jersey_nm.png (чистые карты Legacy T=4),
  font_cm.png / font_nm.png / font_sm.png (512², атлас NHL 24 — раскладка EA), info.json; у старых — kit.json шаблона
  для kitpaint pack (fb.pack).
"""
import argparse
import csv
import json
import os
import shutil
import subprocess
import sys
import time
import tomllib

import numpy as np
from PIL import Image

from . import kit3d, kit_hybrid
from .cas import REPO

WORK = os.path.join(REPO, "game", "work")
NHL24 = os.path.join(WORK, "nhl24")
EXTRACT = os.path.join(NHL24, "extract", "kits24")
FONTS = os.path.join(NHL24, "extract", "fonts24")
OUT = os.path.join(NHL24, "out", "kits")
OUT_NEW = os.path.join(NHL24, "out", "kits_new")
LEG = os.path.join(NHL24, "out", "_legacy_kits")
CLEAN = os.path.join(WORK, "uniforms", "czwork", "clean")
CLEAN_T = 4

# клуб NHL 24 → (номер EA = artid Legacy, код)
CLUBS = [("anaheim", 0, "ANA"), ("winnipeg", 1, "WPG"), ("boston", 2, "BOS"), ("buffalo", 3, "BUF"),
         ("calgary", 4, "CGY"), ("carolina", 5, "CAR"), ("chicago", 6, "CHI"), ("colorado", 7, "COL"),
         ("columbus", 8, "CBJ"), ("dallas", 9, "DAL"), ("detroit", 10, "DET"), ("edmonton", 11, "EDM"),
         ("florida", 12, "FLA"), ("losangeles", 13, "LAK"), ("minnesota", 14, "MIN"), ("montreal", 15, "MTL"),
         ("nashville", 16, "NSH"), ("newjersey", 17, "NJD"), ("nyi", 18, "NYI"), ("nyr", 19, "NYR"),
         ("ottawa", 20, "OTT"), ("philadelphia", 21, "PHI"), ("arizona", 22, "ARI"), ("pittsburgh", 23, "PIT"),
         ("stlouis", 24, "STL"), ("sanjose", 25, "SJS"), ("tampabay", 26, "TBL"), ("toronto", 27, "TOR"),
         ("vancouver", 28, "VAN"), ("washington", 29, "WSH"), ("vegas", 101, "VGK"), ("seattle", 100, "SEA")]
KITS = {"home": 0, "away": 1, "three": 2}
ADIDAS = [("home", "home", 0), ("away", "away", 1), ("three", "three", 2), ("twentytwo", "rr22", None),
          ("twentythree", "rr23", None)]
OUR_ROWS = {100: {0: (0, 0), 1: (1, 0), 2: (2, 0)}, 101: {0: (0, 0), 1: (1, 0), 2: (2, 0)}}  # loc → (variant, hastie)
MESH = {"adidas": kit3d.NHL24_JERSEY,
        "nineties": "content/character/skater/player/jersey/nineties/components/player_jersey_nineties_notuck_large_lod0_mesh"}
SEA_VGK_TEMPLATE = "1_131_0"  # контейнер 3-значного арта (docs/uniforms.md, kitpaint.CONTAINERS)


def names():
    with open(os.path.join(NHL24, "catalog", "texnames.txt"), encoding="utf-8") as f:
        return set(line.strip() for line in f)


def ok_names(folder):
    """Имена текстур, выгруженных без ошибок (по _index.csv fb.extract; старые PNG с ошибкой не берём)."""
    with open(os.path.join(folder, "_index.csv"), encoding="utf-8") as f:
        return {r["name"] for r in csv.DictReader(f) if r["status"] == "ok"}


def prefix(club, family, kit):
    return f"content/character/skater/league/nhl/{club}/{family}/{kit}/"


def png(folder, name):
    return os.path.join(folder, *name[len("content/"):].split("/")) + ".png"


def legacy_target(art, loc):
    if loc is None:
        return None
    if art in OUR_ROWS:
        v = OUR_ROWS[art].get(loc)
        return None if v is None else {"variant": v[0], "hastie": v[1]}
    with open(os.path.join(NHL24, "catalog", "legacy_kits.json"), encoding="utf-8") as f:
        kits = json.load(f)
    rows = [r for r in kits.get(str(art), []) if r[0] == loc and r[4] == art]  # строка самой команды
    return {"variant": rows[0][1], "hastie": rows[0][2]} if rows else None


def all_kits():
    nm = names()
    for club, art, code in CLUBS:
        for kit, label, loc in ADIDAS:
            p = prefix(club, "adidas", kit)
            yield {"club": club, "art": art, "code": code, "family": "adidas", "kit": kit, "label": label, "loc": loc,
                   "exists": p + f"jersey_adidas_{club}_{kit}_color" in nm}
        kits90 = sorted({n.split("/")[7] for n in nm if n.startswith(f"content/character/skater/league/nhl/{club}/nineties/")
                         and n.endswith("_color") and "/jersey_nineties_" in n})
        for kit in kits90:
            yield {"club": club, "art": art, "code": code, "family": "nineties", "kit": kit, "label": f"n90_{kit}",
                   "loc": None, "exists": True}


def cmd_extract(a):
    clubs = "|".join(c for c, _, _ in CLUBS)
    rx = (f"^content/character/skater/league/nhl/({clubs})/(adidas/(home|away|three|twentytwo|twentythree)|nineties/[a-z]+)/"
          f"jersey_(adidas|nineties)_({clubs})_[a-z]+_(base_)?color$")
    subprocess.run([sys.executable, "-m", "fb.extract", rx, "--out", "kits24"], check=True, cwd=os.path.join(REPO, "tools"))
    rx = (f"^content/character/skater/league/nhl/({clubs})/(adidas/(home|away|three|twentytwo|twentythree)|nineties/[a-z]+)/"
          f"font_(adidas|nineties)_({clubs})_[a-z]+_(color|normal)$")
    subprocess.run([sys.executable, "-m", "fb.extract", rx, "--out", "fonts24"], check=True, cwd=os.path.join(REPO, "tools"))


def collar_rule():
    with open(kit_hybrid.RULES, "rb") as f:
        return tomllib.load(f).get("collar", {}).get("v_insert", {})


def build_font(club, family, kit, ok_fonts, od):
    from .fonts import normal_map, resize_premult
    p = prefix(club, family, kit) + f"font_{family}_{club}_{kit}_"
    if p + "color" not in ok_fonts:
        return "нет чанка"
    cm = resize_premult(np.asarray(Image.open(png(FONTS, p + "color")).convert("RGBA")), 512)
    if p + "normal" in ok_fonts:
        nm = normal_map(png(FONTS, p + "normal"), 512)
        st = "ok"
    else:
        nm = np.zeros((512, 512, 4), np.uint8)
        nm[...] = (128, 128, 255, 255)
        st = "ok (нормаль плоская)"
    sm = np.zeros((512, 512, 4), np.uint8)
    sm[..., :3] = 21
    sm[..., 3] = np.where(cm[..., 3] > 128, 255, 0)
    Image.fromarray(cm).save(os.path.join(od, "font_cm.png"))
    Image.fromarray(nm).save(os.path.join(od, "font_nm.png"))
    Image.fromarray(sm).save(os.path.join(od, "font_sm.png"))
    return st


def template_kit(art, variant):
    """kit.json шаблона для kitpaint pack: нынешний комплект Legacy; у SEA/VGK (100/101) — контейнер 1_131_0."""
    kit = SEA_VGK_TEMPLATE if art in OUR_ROWS else f"1_{art}_{variant}"
    d = os.path.join(LEG, kit)
    if not os.path.exists(os.path.join(d, "kit.json")):
        subprocess.run([sys.executable, os.path.join(REPO, "tools", "kitpaint.py"), "unpack", kit, d, "--game", "legacy"],
                       check=False, capture_output=True, cwd=os.path.join(REPO, "tools"))
    return os.path.join(d, "kit.json") if os.path.exists(os.path.join(d, "kit.json")) else None


def cmd_run(a):
    want_clubs = set(a.clubs.split(",")) if a.clubs else None
    want_labels = set(a.labels.split(",")) if a.labels else None
    ok_j, ok_f = ok_names(EXTRACT), ok_names(FONTS)
    dst, n_jersey_tri = kit_hybrid.legacy_with_shirt()  # без шнуровки (jerseytie нет ни у кого) + «рубашка» V-выреза
    srcs, tids = {}, {}
    crule = collar_rule()
    summary = []
    for k in all_kits():
        club, art, code, family, kit, label = k["club"], k["art"], k["code"], k["family"], k["kit"], k["label"]
        if want_clubs and club not in want_clubs and code not in want_clubs:
            continue
        if want_labels and label not in want_labels and not (label.startswith("n90_") and "nineties" in want_labels):
            continue
        t0 = time.time()
        rec = {"club": club, "code": code, "art": art, "family": family, "kit": kit, "label": label}
        if not k["exists"]:
            rec["status"] = "нет комплекта в NHL 24"
            summary.append(rec)
            continue
        p = prefix(club, family, kit) + f"jersey_{family}_{club}_{kit}_"
        if p + "color" not in ok_j:
            rec["status"] = "нет чанка (нет TOC)"
            summary.append(rec)
            print(code, label, rec["status"], flush=True)
            continue
        tgt = legacy_target(art, k["loc"])
        od = os.path.join(OUT if tgt else OUT_NEW, f"{code}_{label}")
        os.makedirs(od, exist_ok=True)
        if family not in srcs:
            srcs[family] = kit3d.load_nhl24(MESH[family])
            tids[family], _ = kit3d.raster_uv(srcs[family], 1024)
        src, tid24 = srcs[family], tids[family]
        defaults, rules = kit_hybrid.load_rules(kit_hybrid.RULES, code, label, [])
        comp = kit3d.load_tex(png(EXTRACT, p + "color"))
        mode = "base"
        if p + "base_color" in ok_j:
            base = kit3d.load_tex(png(EXTRACT, p + "base_color"))
            if base.shape[:2] != comp.shape[:2]:
                base, lab, patches = kit_hybrid.standard_patches(comp, rules, defaults)
                mode = "base только 1024²: щит NHL и логотип сзади — декалями, остальное через 3D"
            else:
                lab, patches = kit_hybrid.find_patches(comp, base, defaults)
                if not patches:
                    base, lab, patches = kit_hybrid.standard_patches(comp, rules, defaults)
                    mode = "нашивки уже в base: щит NHL и логотип сзади — декалями, остальное через 3D"
        else:
            base, lab, patches = kit_hybrid.standard_patches(comp, rules, defaults)
            mode = "без base: щит NHL и логотип сзади — декалями, остальное через 3D"
        placed, soft = kit_hybrid.plan_decals(comp, lab, patches, rules, defaults, src, dst, tid24)
        missing_std = [nm for nm in ("neck_shield", "back_neck") if nm not in [pl["name"] for pl in placed]]
        if missing_std and mode == "base":
            base, lab2, patches2 = kit_hybrid.standard_patches(base, rules, defaults, names=tuple(missing_std))
            off = int(lab.max()) + 10
            lab = np.where(lab2 > 0, lab2 + off, lab)
            p2, s2 = kit_hybrid.plan_decals(comp, lab, [(lid + off, sl, ar) for lid, sl, ar in patches2], rules,
                                            defaults, src, dst, tid24)
            placed += p2
            soft.update(s2)
            if p2:
                mode += f"; из base вырезаны: {', '.join(pl['name'] for pl in p2)}"
        collar = None
        if crule.get("mode", "body") == "body":
            collar = (crule, kit_hybrid.collar_color(base, crule))
        post = kit_hybrid.decal_post(comp, placed, soft, n_jersey_tri, collar)
        img, mask, dist, info = kit3d.transfer(base, src, dst, 1024, 2, post=post)
        Image.fromarray(np.clip(img, 0, 255).astype(np.uint8)).convert("RGB").save(os.path.join(od, "jersey_cm.png"))
        for sname, dname in ((f"{CLEAN_T}_3-12-21-30-39-48-57-66-75_sm.png", "jersey_sm.png"),
                             (f"{CLEAN_T}_3-12-21-30-39-48-57-66-75_nm.png", "jersey_nm.png")):
            shutil.copyfile(os.path.join(CLEAN, sname), os.path.join(od, dname))
        stale = os.path.join(od, "jersey_0_nm.png")
        if os.path.exists(stale):
            os.replace(stale, os.path.join(od, "jersey_nm.png"))
        rec["font"] = build_font(club, family, kit, ok_f, od)
        warn = []
        if "neck_shield" not in [pl["name"] for pl in placed]:
            warn.append("щит NHL у ворота не найден")
        for pl in placed:
            if pl.get("snap_cm", 0) > 6:
                warn.append(f"{pl['name']}: посадка {pl['snap_cm']} см")
        rec.update(status="ok", mode=mode, out=os.path.relpath(od, NHL24), warnings=warn,
                   v_insert_texels=getattr(post, "v_insert", 0),
                   patches=[{kk: vv for kk, vv in pl.items() if not kk.startswith("_")} for pl in placed],
                   collar="NHL 24 круглый ворот → Legacy стиль 1 (V Edge), V-вставка в цвет свитера; шнуровки нет; щит NHL −4 см",
                   sec=round(time.time() - t0, 1))
        if tgt:
            v = tgt["variant"]
            rec["legacy"] = {"kit": f"1_{art}_{v}", "variant": v, "hastie_now": tgt["hastie"], "hastie_want": 0,
                             "file": f"rendering/jersey/texlib_1_{art}_{v}.rx2"}
            tpl = template_kit(art, v)
            if tpl:
                shutil.copyfile(tpl, os.path.join(od, "kit.json"))
                rec["legacy"]["template"] = json.load(open(tpl, encoding="utf-8"))["template"]
            else:
                warn.append("нет шаблона kitpaint")
        with open(os.path.join(od, "info.json"), "w", encoding="utf-8") as f:
            json.dump(rec, f, ensure_ascii=False, indent=1)
        summary.append(rec)
        print(code, label, rec["status"], mode[:12], f"нашивок {len(placed)}", f"V {rec['v_insert_texels']}",
              f"шрифт: {rec['font']}", "; ".join(warn), f"{rec['sec']} с", flush=True)
    path = os.path.join(NHL24, "out", "kits_summary.json")
    old = []
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            old = json.load(f)
    keys = {(r["code"], r["label"]) for r in summary}
    with open(path, "w", encoding="utf-8") as f:
        json.dump([r for r in old if (r["code"], r["label"]) not in keys] + summary, f, ensure_ascii=False, indent=1)


def cmd_sheet(a):
    from PIL import ImageDraw, ImageFont
    try:
        font = ImageFont.truetype("C:/Windows/Fonts/segoeuib.ttf", 20)
        small = ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", 15)
    except OSError:
        font = small = ImageFont.load_default()
    with open(os.path.join(NHL24, "out", "kits_summary.json"), encoding="utf-8") as f:
        summ = json.load(f)
    jersey, _ = kit_hybrid.legacy_with_shirt()
    if a.label == "nineties":
        cells = [(r["code"], r["label"], r) for r in summ if r["label"].startswith("n90_")]
    else:
        by = {(r["code"], r["label"]): r for r in summ}
        cells = [(code, a.label, by.get((code, a.label))) for _, _, code in CLUBS]
    W, cols = 300, 8
    H = int(round(W * (kit3d.FRAME[3] - kit3d.FRAME[2]) / (kit3d.FRAME[1] - kit3d.FRAME[0])))
    rows = (len(cells) + cols - 1) // cols
    top = 28
    sheet = Image.new("RGB", (cols * (W + 8) + 8, rows * (H + top + 22) + 8), (30, 30, 34))
    d = ImageDraw.Draw(sheet)
    for i, (code, label, r) in enumerate(cells):
        x = 8 + (i % cols) * (W + 8)
        y = 8 + (i // cols) * (H + top + 22)
        d.text((x, y), f"{code} {label}", fill=(235, 235, 235), font=font)
        if not r or r.get("status") != "ok":
            d.text((x + 10, y + top + H // 2), (r or {}).get("status", "нет комплекта в NHL 24"), fill=(220, 130, 130),
                   font=font)
            continue
        tex = kit3d.load_tex(os.path.join(NHL24, r["out"], "jersey_cm.png"))
        sheet.paste(kit3d.render(jersey, tex, "front", W, ss=2), (x, y + top))
        note = ("в Legacy: " + r["legacy"]["kit"]) if r.get("legacy") else "новая форма"
        if r.get("warnings"):
            note += "; " + "; ".join(r["warnings"])[:38]
        d.text((x, y + top + H + 2), note, fill=(200, 200, 200), font=small)
    out = os.path.join(NHL24, "compare", f"kits_{a.label}.png")
    sheet.save(out)
    print(out, sheet.size, len(cells))


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("extract")
    r = sub.add_parser("run")
    r.add_argument("--clubs", default="")
    r.add_argument("--labels", default="", help="home,away,three,rr22,rr23,nineties")
    s = sub.add_parser("sheet")
    s.add_argument("label")
    a = ap.parse_args()
    return {"extract": cmd_extract, "run": cmd_run, "sheet": cmd_sheet}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
