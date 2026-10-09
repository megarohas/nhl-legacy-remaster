"""Пакетный гибрид: свитера 32 клубов NHL 24 (adidas home/away/three) → развёртки NHL Legacy. Только офлайн.

  python -m fb.kit_batch extract              # нужные jersey_*_color и _base_color в 2048² (fb.extract)
  python -m fb.kit_batch run [--clubs a,b] [--kits home,away,three]
  python -m fb.kit_batch sheet KIT            # лист рендеров спереди по всем клубам: compare/kits_<KIT>.png
  python -m fb.kit_batch finalize             # + kit.json шаблона Legacy → папки готовы для kitpaint pack

Выход: game/work/nhl24/out/kits/<клуб>_<форма>/
  jersey_cm.png     — 1024², развёртка Legacy (гибрид: основа через 3D + нашивки декалями по kit_rules.toml)
  jersey_sm.png, jersey_nm.png — чистые карты Legacy (game/work/uniforms/czwork/clean, рисунок T=4:
                      швы без логотипов EA), пока без рельефа новых нашивок
  info.json         — источник NHL 24, нашивки и правила, цель в Legacy (texlib, растры, hastie, профиль)
Цель в Legacy — строка stockteamjerseys стиля 1 с locstring 0/1/2 (дом/выезд/третья) этого клуба
(game/work/nhl24/catalog/legacy_kits.json; SEA/VGK — наши строки 100/101, варианты 0/1/2, hastie 0).
Если у цели hastie 1 (шнуровка ворота) — профиль laces (щит NHL ниже шнурков).
"""
import argparse
import json
import os
import shutil
import sys
import time

import numpy as np
from PIL import Image

from . import kit3d, kit_hybrid
from .cas import REPO

WORK = os.path.join(REPO, "game", "work")
NHL24 = os.path.join(WORK, "nhl24")
EXTRACT = os.path.join(NHL24, "extract", "kits24")
OUT = os.path.join(NHL24, "out", "kits")
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
OUR_ROWS = {100: {0: (0, 0), 1: (1, 0), 2: (2, 0)}, 101: {0: (0, 0), 1: (1, 0), 2: (2, 0)}}  # loc → (variant, hastie)


_OK = None


def ok_names(folder):
    """Имена текстур, выгруженных без ошибок (по _index.csv fb.extract; старые PNG с ошибкой не берём)."""
    import csv
    with open(os.path.join(folder, "_index.csv"), encoding="utf-8") as f:
        return {r["name"] for r in csv.DictReader(f) if r["status"] == "ok"}


def tex_path(club, kit, base=False):
    """Путь PNG свитера или None, если текстуры нет / чанк не найден / sha1 не совпал."""
    global _OK
    if _OK is None:
        _OK = ok_names(EXTRACT)
    name = f"content/character/skater/league/nhl/{club}/adidas/{kit}/jersey_adidas_{club}_{kit}_{'base_' if base else ''}color"
    p = os.path.join(EXTRACT, "character", "skater", "league", "nhl", club, "adidas", kit, name.split("/")[-1] + ".png")
    return p if name in _OK else None


def legacy_target(art, loc):
    if art in OUR_ROWS:
        v = OUR_ROWS[art].get(loc)
        return None if v is None else {"variant": v[0], "hastie": v[1]}
    with open(os.path.join(NHL24, "catalog", "legacy_kits.json"), encoding="utf-8") as f:
        kits = json.load(f)
    rows = [r for r in kits.get(str(art), []) if r[0] == loc and r[4] == art]  # строка самой команды
    if not rows:
        return None
    r = rows[0]
    return {"variant": r[1], "hastie": r[2]}


def cmd_extract(a):
    import subprocess
    clubs = "|".join(c for c, _, _ in CLUBS)
    rx = (f"^content/character/skater/league/nhl/({clubs})/adidas/(home|away|three)/"
          f"jersey_adidas_({clubs})_(home|away|three)_(base_)?color$")
    subprocess.run([sys.executable, "-m", "fb.extract", rx, "--out", "kits24"], check=True,
                   cwd=os.path.join(REPO, "tools"))


def cmd_run(a):
    clubs = [c for c in CLUBS if not a.clubs or c[0] in a.clubs.split(",") or c[2] in a.clubs.split(",")]
    kits = a.kits.split(",")
    src, dst = kit_hybrid.meshes(True)
    n_jersey_tri = len(kit3d.load_legacy()["tri"])
    tid24, _ = kit3d.raster_uv(src, 1024)
    summary = []
    for club, art, code in clubs:
        for kit in kits:
            t0 = time.time()
            rec = {"club": club, "code": code, "kit": kit, "art": art, "status": ""}
            loc = KITS[kit]
            tgt = legacy_target(art, loc)
            comp_p = tex_path(club, kit)
            base_p = tex_path(club, kit, True)
            if not comp_p:
                rec["status"] = "нет чанка"
                summary.append(rec)
                print(code, kit, rec["status"], flush=True)
                continue
            if tgt is None:
                rec["status"] = "нет строки Legacy (стиль 1) для этой формы"
            profiles = ["laces"] if tgt and tgt["hastie"] else []
            defaults, rules = kit_hybrid.load_rules(kit_hybrid.RULES, code, kit, profiles)
            comp = kit3d.load_tex(comp_p)
            if base_p:
                base = kit3d.load_tex(base_p)
                if base.shape[:2] != comp.shape[:2]:  # у base в CAS только хвост мипов (с 1024²): разница по краям
                    base, lab, patches = kit_hybrid.standard_patches(comp, rules, defaults)  # — как без base
                    mode = "base только 1024² (хвост мипов): щит NHL и логотип сзади — декалями, остальное через 3D"
                else:
                    lab, patches = kit_hybrid.find_patches(comp, base, defaults)
                    mode = "base"
                if not patches and mode == "base":  # base совпадает с готовым свитером — нашивки уже в нём
                    base, lab, patches = kit_hybrid.standard_patches(comp, rules, defaults)
                    mode = "без нашивок в base: щит NHL и логотип сзади — декалями, остальное через 3D"
            else:
                base, lab, patches = kit_hybrid.standard_patches(comp, rules, defaults)
                mode = "без base: щит NHL и логотип сзади — декалями, остальное через 3D"
            placed, soft = kit_hybrid.plan_decals(comp, lab, patches, rules, defaults, src, dst, tid24)
            missing_std = [nm for nm in ("neck_shield", "back_neck") if nm not in [pl["name"] for pl in placed]]
            if missing_std and mode == "base":  # стандартная нашивка осталась в base — вырезать её и оттуда
                base, lab2, patches2 = kit_hybrid.standard_patches(base, rules, defaults, names=tuple(missing_std))
                off = int(lab.max()) + 10
                lab = np.where(lab2 > 0, lab2 + off, lab)
                patches2 = [(lid + off, sl, area) for lid, sl, area in patches2]
                p2, s2 = kit_hybrid.plan_decals(comp, lab, patches2, rules, defaults, src, dst, tid24)
                placed += p2
                soft.update(s2)
                if p2:
                    mode += f"; из base вырезаны: {', '.join(pl['name'] for pl in p2)}"
            img, mask, dist, info = kit3d.transfer(base, src, dst, 1024, 2,
                                                   post=kit_hybrid.decal_post(comp, placed, soft, n_jersey_tri))
            od = os.path.join(OUT, f"{code}_{kit}")
            os.makedirs(od, exist_ok=True)
            Image.fromarray(np.clip(img, 0, 255).astype(np.uint8)).convert("RGB").save(os.path.join(od, "jersey_cm.png"))
            for src_name, dst_name in ((f"{CLEAN_T}_3-12-21-30-39-48-57-66-75_sm.png", "jersey_sm.png"),
                                       (f"{CLEAN_T}_3-12-21-30-39-48-57-66-75_nm.png", "jersey_nm.png")):
                shutil.copyfile(os.path.join(CLEAN, src_name), os.path.join(od, dst_name))
            names = [pl["name"] for pl in placed]
            warn = []
            if "neck_shield" not in names:
                warn.append("щит NHL у ворота не найден")
            for pl in placed:
                if pl.get("snap_cm", 0) > 6:
                    warn.append(f"{pl['name']}: посадка {pl['snap_cm']} см")
                if pl.get("texels", 1) == 0:
                    warn.append(f"{pl['name']}: не легла на Legacy")
            rec.update(mode=mode, patches=[{k: v for k, v in pl.items() if not k.startswith("_")} for pl in placed],
                       warnings=warn, sec=round(time.time() - t0, 1))
            if tgt:
                v = tgt["variant"]
                rec["legacy"] = {"texlib": f"rendering/jersey/texlib_1_{art}_{v}.rx2",
                                 "rasters": {"jersey_cm": f"jersey_1_{art}_{v}_cm", "jersey_sm": f"jersey_1_{art}_{v}_sm",
                                             "jersey_nm": f"jersey_1_{art}_{v}_0_nm"},
                                 "variant": v, "hastie": tgt["hastie"], "profile": profiles}
            rec["collar"] = "NHL 24 adidas (круглый ворот) → Legacy стиль 1 (V Edge)" + (
                ", шнуровка (hastie 1): щит NHL −9 см" if profiles else ", без шнуровки: щит NHL −4 см")
            rec["status"] = rec["status"] or "ok"
            with open(os.path.join(od, "info.json"), "w", encoding="utf-8") as f:
                json.dump(rec, f, ensure_ascii=False, indent=1)
            summary.append(rec)
            print(code, kit, rec["status"], mode[:4], f"нашивок {len(placed)}", "; ".join(warn), f"{rec['sec']} с",
                  flush=True)
    write_summary(summary)


def write_summary(extra=()):
    """_summary.json — по info.json всех папок + записи без папки (нет чанка / нет комплекта)."""
    path = os.path.join(OUT, "_summary.json")
    old = []
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            old = json.load(f)
    recs = {}
    for r in old + list(extra):
        recs[(r["code"], r["kit"])] = r
    for d in os.listdir(OUT):
        info = os.path.join(OUT, d, "info.json")
        if os.path.exists(info):
            with open(info, encoding="utf-8") as f:
                r = json.load(f)
            recs[(r["code"], r["kit"])] = r
    with open(os.path.join(NHL24, "catalog", "texnames.txt"), encoding="utf-8") as f:
        names = set(line.strip() for line in f)
    for club, art, code in CLUBS:  # чего нет вовсе: комплекта нет в каталоге NHL 24 или его чанк не найден (нет TOC)
        for kit in KITS:
            r = recs.get((code, kit))
            if r is None or r.get("status", "").startswith("нет комплекта") or r.get("status") == "нет чанка":
                n = f"content/character/skater/league/nhl/{club}/adidas/{kit}/jersey_adidas_{club}_{kit}_color"
                st = "нет чанка (нет TOC)" if n in names else "нет комплекта в NHL 24"
                recs[(code, kit)] = {"club": club, "code": code, "kit": kit, "art": art, "status": st}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(sorted(recs.values(), key=lambda r: (r["code"], r["kit"])), f, ensure_ascii=False, indent=1)


def cmd_finalize(a):
    """Папки комплектов — в раскладку kitpaint unpack: kit.json шаблона (нынешний комплект Legacy) + изменённые
    слои (jersey_cm/nm/sm, font_cm/nm/sm). Остальные слои (name, pant, sock, fe) pack возьмёт из шаблона."""
    import subprocess
    leg = os.path.join(NHL24, "out", "_legacy_kits")
    n = 0
    for d in sorted(os.listdir(OUT)):
        info = os.path.join(OUT, d, "info.json")
        if not os.path.exists(info):
            continue
        with open(info, encoding="utf-8") as f:
            rec = json.load(f)
        lg = rec.get("legacy")
        if not lg:
            continue
        kit = f"1_{rec['art']}_{lg['variant']}"
        src = os.path.join(leg, kit)
        if not os.path.exists(os.path.join(src, "kit.json")):
            subprocess.run([sys.executable, os.path.join(REPO, "tools", "kitpaint.py"), "unpack", kit, src, "--game",
                            "legacy"], check=False, capture_output=True, cwd=os.path.join(REPO, "tools"))
        if not os.path.exists(os.path.join(src, "kit.json")):
            print(d, "нет шаблона", kit)
            continue
        old = os.path.join(OUT, d, "jersey_0_nm.png")
        if os.path.exists(old):
            os.replace(old, os.path.join(OUT, d, "jersey_nm.png"))
        shutil.copyfile(os.path.join(src, "kit.json"), os.path.join(OUT, d, "kit.json"))
        n += 1
    print("готово папок:", n)


def cmd_sheet(a):
    from PIL import ImageDraw, ImageFont
    try:
        font = ImageFont.truetype("C:/Windows/Fonts/segoeuib.ttf", 20)
        small = ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", 15)
    except OSError:
        font = small = ImageFont.load_default()
    with open(os.path.join(OUT, "_summary.json"), encoding="utf-8") as f:
        summ = {(r["code"], r["kit"]): r for r in json.load(f)}
    jersey = kit3d.load_legacy()
    tie = kit_hybrid.merge(jersey, kit3d.load_legacy(kit_hybrid.LEGACY_TIE))
    W, cols = 300, 8
    H = int(round(W * (kit3d.FRAME[3] - kit3d.FRAME[2]) / (kit3d.FRAME[1] - kit3d.FRAME[0])))
    rows = (len(CLUBS) + cols - 1) // cols
    top = 28
    sheet = Image.new("RGB", (cols * (W + 8) + 8, rows * (H + top + 22) + 8), (30, 30, 34))
    d = ImageDraw.Draw(sheet)
    for i, (club, art, code) in enumerate(CLUBS):
        x = 8 + (i % cols) * (W + 8)
        y = 8 + (i // cols) * (H + top + 22)
        r = summ.get((code, a.kit))
        d.text((x, y), f"{code} {a.kit}", fill=(235, 235, 235), font=font)
        if not r or r["status"] != "ok":
            d.text((x + 10, y + top + H // 2), (r or {}).get("status", "нет"), fill=(220, 130, 130), font=font)
            continue
        tex = kit3d.load_tex(os.path.join(OUT, f"{code}_{a.kit}", "jersey_cm.png"))
        m = tie if r.get("legacy", {}).get("hastie") else jersey
        sheet.paste(kit3d.render(m, tex, "front", W, ss=2), (x, y + top))
        note = ("шнуровка, щит −9" if r.get("legacy", {}).get("hastie") else "щит −4") + (
            "; без base" if r.get("mode", "").startswith("без") else "")
        if r.get("warnings"):
            note += "; " + "; ".join(r["warnings"])[:40]
        d.text((x, y + top + H + 2), note, fill=(200, 200, 200), font=small)
    out = os.path.join(NHL24, "compare", f"kits_{a.kit}.png")
    sheet.save(out)
    print(out, sheet.size)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("extract")
    r = sub.add_parser("run")
    r.add_argument("--clubs", default="")
    r.add_argument("--kits", default="home,away,three")
    s = sub.add_parser("sheet")
    s.add_argument("kit")
    sub.add_parser("finalize")
    sub.add_parser("summarize")
    a = ap.parse_args()
    return {"extract": cmd_extract, "run": cmd_run, "sheet": cmd_sheet, "finalize": cmd_finalize,
            "summarize": lambda a: write_summary()}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
