"""Пилот одного клуба целиком: NHL 24 → NHL Legacy (офлайн, в игру не ставится). Сейчас — Чикаго (CHI).

  python -m fb.pilot build [--club CHI]     # формы: свитер (гибрид), шрифт, шорты и гетры (3D), превью меню
  python -m fb.pilot pack  [--club CHI]     # pack/cache: формы (kitpaint pack), центр льда, наклейки на шлем
  python -m fb.pilot common                 # общие: реклама и логотипы на льду (каталог ice_hotspot), шайба, клюшки
  python -m fb.pilot manifest [--club CHI]  # pack/manifest.json в формате legacy-data (docs/legacy-data.md)
  python -m fb.pilot sheets [--club CHI]    # листы проверки в compare/

Формы клуба: строки Legacy (дом/выезд/третья, если есть) + новые по реестру legacy-data
tools/legacy_data/nhl24_kits.json (номер варианта = fevariant). Решения пользователя: шнуровки нет, щит NHL −4 см,
V-вставка в цвет свитера, рельеф свитера — чистые карты Legacy T=4, шорты/гетры — точно через 3D (сетки по .toc;
сетки разной высоты выравниваются аффинно по рамкам), рельеф шорт — шаблона Legacy.
"""
import argparse
import csv
import json
import os
import shutil
import subprocess
import sys
import time

import numpy as np
from PIL import Image

from . import kit3d, kit_hybrid
from .cas import REPO
from .kit_batch import CLEAN, CLEAN_T, CLUBS, MESH, collar_rule, legacy_target, prefix
from .pack import CACHE, PACK, TMP, TOOLS, md5

NHL24 = os.path.join(REPO, "game", "work", "nhl24")
OUTP = os.path.join(NHL24, "out", "pilot")
LEG = os.path.join(NHL24, "out", "_legacy_kits")
REGISTRY = os.path.join(REPO, "tools", "legacy_data", "nhl24_kits.json")
PANT_N24 = "content/character/skater/player/pant/common/components/player_pant_common_tightlong_lod0_mesh"
SOCK_N24 = "content/character/skater/player/sock/common/components/player_sock_common_notuck_mesh"
PANT_L = "rendering/pant/pant_1_0_0_2.rx2"
SOCK_L = "rendering/sock/playersock_1_2.rx2"
PANT_WAIST = 1.17  # у NHL 24 шорты с высоким поясом до груди; видимая часть — до ремня ~1,17 м


def club_info(code):
    for club, art, c in CLUBS:
        if c == code:
            return club, art
    raise SystemExit(f"нет клуба {code}")


def kits_for(code):
    """[(label, family, kit, variant, new?)] — строки Legacy и реестр новых форм."""
    club, art = club_info(code)
    out = []
    for label, kit, loc in (("home", "home", 0), ("away", "away", 1), ("three", "three", 2)):
        t = legacy_target(art, loc)
        if t:
            out.append((label, "adidas", kit, t["variant"], False))
    with open(REGISTRY, encoding="utf-8") as f:
        reg = json.load(f)["kits"]
    for r in reg:
        if r["club"] != code:
            continue
        lab = r["kit"]
        fam, kit = ("nineties", lab[4:]) if lab.startswith("n90_") else ("adidas", {"three": "three", "rr22": "twentytwo",
                                                                                     "rr23": "twentythree"}[lab])
        out.append((lab, fam, kit, r["variant"], True))
    return out


def unpack(kit):
    d = os.path.join(LEG, kit)
    if not os.path.exists(os.path.join(d, "kit.json")):
        subprocess.run([sys.executable, os.path.join(TOOLS, "kitpaint.py"), "unpack", kit, d, "--game", "legacy"],
                       check=False, capture_output=True, cwd=TOOLS)
    return d


def extract_club(club, force=False):
    folder = os.path.join(NHL24, "extract", f"club_{club}")
    if not force and os.path.exists(os.path.join(folder, "_index.csv")):  # уже выгружено — не повторяем
        with open(os.path.join(folder, "_index.csv"), encoding="utf-8") as f:
            return folder, {r["name"] for r in csv.DictReader(f) if r["status"] == "ok"}
    rx = (f"^content/character/skater/league/nhl/{club}/(adidas/(home|away|three|twentytwo|twentythree)|nineties/[a-z]+)/"
          f"(jersey|font|pant|sock|helmetlogo)_(adidas|nineties)_{club}_[a-z]+_(base_)?(color|normal|[0-9]_color)$")
    subprocess.run([sys.executable, "-m", "fb.extract", rx, "--out", f"club_{club}"], check=True, cwd=TOOLS)
    folder = os.path.join(NHL24, "extract", f"club_{club}")
    with open(os.path.join(folder, "_index.csv"), encoding="utf-8") as f:
        ok = {r["name"] for r in csv.DictReader(f) if r["status"] == "ok"}
    return folder, ok


def png(folder, name):
    return os.path.join(folder, *name[len("content/"):].split("/")) + ".png"


def fe_preview(jersey_mesh, tex, size=256):
    """Превью меню 256² (RGBA, прозрачный фон): свитер Legacy спереди, свой рендер (модель позы EA пропала 09.10)."""
    im = kit3d.render(jersey_mesh, tex, "front", 512, bg=(0, 0, 0), frame=(-0.62, 0.62, 0.62, 1.86), ss=2)
    a = np.asarray(im).astype(np.float64)
    alpha = (a.sum(-1) > 6).astype(np.uint8) * 255
    rgba = np.dstack([a.astype(np.uint8), alpha])
    return Image.fromarray(rgba, "RGBA").resize((size, size), Image.LANCZOS)


def lightness(tex):
    a = np.asarray(Image.open(tex).convert("RGB").resize((64, 64))).astype(np.float64) / 255
    return float((0.2126 * a[..., 0] + 0.7152 * a[..., 1] + 0.0722 * a[..., 2]).mean())


def cmd_build(a):
    code = a.club
    club, art = club_info(code)
    folder, ok = extract_club(club)
    dst, n_jersey_tri = kit_hybrid.legacy_with_shirt()
    srcs, tids = {}, {}
    crule = collar_rule()
    pN, sN = kit3d.load_nhl24(PANT_N24), kit3d.load_nhl24(SOCK_N24)
    pL, sL = kit3d.load_legacy(PANT_L), kit3d.load_legacy(SOCK_L)
    bN = kit3d.bbox(pN)
    bN[3] = PANT_WAIST
    pLa = kit3d.aligned(pL, bN, kit3d.bbox(pL))
    sLa = kit3d.aligned(sL, kit3d.bbox(sN), kit3d.bbox(sL))
    report = []
    only = set(a.kits.split(",")) if getattr(a, "kits", "") else None
    for label, family, kit, variant, new in kits_for(code):
        if only and label not in only:
            continue
        t0 = time.time()
        rec = {"club": code, "kit": label, "family": family, "nhl24_kit": kit, "variant": variant, "new": new}
        p = prefix(club, family, kit)
        jc = p + f"jersey_{family}_{club}_{kit}_color"
        if jc not in ok:
            rec["status"] = "нет текстуры свитера"
            report.append(rec)
            print(code, label, rec["status"])
            continue
        od = os.path.join(OUTP, f"{code}_{label}")
        os.makedirs(od, exist_ok=True)
        if family not in srcs:
            srcs[family] = kit3d.load_nhl24(MESH[family])
            tids[family], _ = kit3d.raster_uv(srcs[family], 1024)
        src, tid24 = srcs[family], tids[family]
        defaults, rules = kit_hybrid.load_rules(kit_hybrid.RULES, code, label, [])
        comp = kit3d.load_tex(png(folder, jc))
        bc = p + f"jersey_{family}_{club}_{kit}_base_color"
        if bc in ok and Image.open(png(folder, bc)).size == (comp.shape[1], comp.shape[0]):
            base = kit3d.load_tex(png(folder, bc))
            lab, patches = kit_hybrid.find_patches(comp, base, defaults)
            mode = "base"
        else:
            base, lab, patches = kit_hybrid.standard_patches(comp, rules, defaults)
            mode = "без base: щит NHL и логотип сзади — декалями"
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
        collar = (crule, kit_hybrid.collar_color(base, crule)) if crule.get("mode", "body") == "body" else None
        post = kit_hybrid.decal_post(comp, placed, soft, n_jersey_tri, collar)
        img, mask, dist, info = kit3d.transfer(base, src, dst, 1024, 2, post=post)
        Image.fromarray(np.clip(img, 0, 255).astype(np.uint8)).convert("RGB").save(os.path.join(od, "jersey_cm.png"))
        Image.open(os.path.join(CLEAN, f"{CLEAN_T}_3-12-21-30-39-48-57-66-75_sm.png")).resize((1024, 1024), Image.LANCZOS) \
            .save(os.path.join(od, "jersey_sm.png"))
        shutil.copyfile(os.path.join(CLEAN, f"{CLEAN_T}_3-12-21-30-39-48-57-66-75_nm.png"), os.path.join(od, "jersey_nm.png"))
        # шрифт
        from .fonts import normal_map, resize_premult
        fc, fn = p + f"font_{family}_{club}_{kit}_color", p + f"font_{family}_{club}_{kit}_normal"
        if fc in ok:
            cm = resize_premult(np.asarray(Image.open(png(folder, fc)).convert("RGBA")), 512)
            nm = normal_map(png(folder, fn), 512) if fn in ok else np.dstack(
                [np.full((512, 512), v, np.uint8) for v in (128, 128, 255, 255)])
            sm = np.zeros((512, 512, 4), np.uint8)
            sm[..., :3] = 21
            sm[..., 3] = np.where(cm[..., 3] > 128, 255, 0)
            Image.fromarray(cm).save(os.path.join(od, "font_cm.png"))
            Image.fromarray(nm).save(os.path.join(od, "font_nm.png"))
            Image.fromarray(sm).save(os.path.join(od, "font_sm.png"))
            rec["font"] = "ok"
        else:
            rec["font"] = "нет текстуры шрифта — останется шаблона"
        # шорты и гетры: точно через 3D (сетки по .toc), выравнивание по рамкам
        pc, sc = p + f"pant_{family}_{club}_{kit}_color", p + f"sock_{family}_{club}_{kit}_color"
        if pc in ok:
            pimg, pm, pd, _ = kit3d.transfer(kit3d.load_tex(png(folder, pc)), pN, pLa, 512, 2)
            Image.fromarray(np.clip(pimg, 0, 255).astype(np.uint8)).convert("RGB").save(os.path.join(od, "pant_cm.png"))
            rec["pant"] = "ok (3D)"
        else:
            rec["pant"] = "нет текстуры шорт"
        if sc in ok:
            simg, smk, sd, _ = kit3d.transfer(kit3d.load_tex(png(folder, sc)), sN, sLa, (1024, 512), 2)
            Image.fromarray(np.clip(simg, 0, 255).astype(np.uint8)).convert("RGB").save(os.path.join(od, "sock_cm.png"))
            rec["sock"] = "ok (3D)"
        else:
            rec["sock"] = "нет текстуры гетр"
        fe_preview(dst, kit3d.load_tex(os.path.join(od, "jersey_cm.png"))).save(os.path.join(od, "fe.png"))
        # шаблон для kitpaint: своя строка Legacy (дом/выезд) или домашняя форма клуба (новые)
        tpl_kit = f"1_{art}_{variant}" if not new else f"1_{art}_{legacy_target(art, 0)['variant']}"
        shutil.copyfile(os.path.join(unpack(tpl_kit), "kit.json"), os.path.join(od, "kit.json"))
        rec.update(status="ok", mode=mode, template=tpl_kit, legacy_kit=f"1_{art}_{variant}",
                   islightcolor=int(lightness(os.path.join(od, "jersey_cm.png")) > 0.5),
                   patches=[{k: v for k, v in pl.items() if not k.startswith("_")} for pl in placed],
                   sec=round(time.time() - t0, 1))
        with open(os.path.join(od, "info.json"), "w", encoding="utf-8") as f:
            json.dump(rec, f, ensure_ascii=False, indent=1)
        report.append(rec)
        print(code, label, f"1_{art}_{variant}", mode[:6], "шрифт", rec["font"][:2], "шорты", rec["pant"][:2], "гетры",
              rec["sock"][:2], f"{rec['sec']} с", flush=True)
    rp = os.path.join(OUTP, f"{code}_report.json")
    if only and os.path.exists(rp):  # частичная пересборка — остальные записи отчёта прежние
        with open(rp, encoding="utf-8") as f:
            old = [r for r in json.load(f) if r["kit"] not in only]
        order = [k[0] for k in kits_for(code)]
        report = sorted(old + report, key=lambda r: order.index(r["kit"]) if r["kit"] in order else 99)
    with open(rp, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)


# ---------------------------------------------------------------- упаковка (формат 1 legacy-data)

KIT_PATHS = {"jersey": "rendering/jersey/texlib_1_{a}_{v}.rx2", "name": "rendering/jersey/name_1_{a}_{v}_cm.rx2",
             "pant": "rendering/pant/texlib_1_{a}_{v}.rx2", "sock": "rendering/sock/sock_1_{a}_{v}_cm.rx2",
             "fe": "fe/ion/artassets/jerseys/jersey_1_{a}_{v}.big"}
STAGE_LAYERS = ("jersey_cm", "jersey_sm", "jersey_nm", "font_cm", "font_nm", "font_sm", "pant_cm", "sock_cm", "fe")
CONTAINER = {6: "1_10_0"}  # длина «1_A_V» → комплект EA той же длины (имена растров 1_6_10… на символ длиннее 1_6_0)
LABELS = {"n90_two": "1990s Retro Black", "n90_four": "1990s Retro White"}  # прочие подписи — по умолчанию legacy-data
HOTSPOT = os.path.join(NHL24, "extract", "hotspot", "worlds", "rink", "textures", "hotspot")
PUCK = os.path.join(NHL24, "extract", "puck24", "worlds", "puck", "textures", "licensed")
EXCLUDED = [{"club": "ARI", "reason": "ARI → Utah, не ставить"}]
# NHL 24 хранит рекламу на льду осветлённой: по совпадающим рисункам (WHL, EA SPORTS, OHL) c24 ≈ 0,62·c + 76 в каждом
# канале (≈38 % к серому ~200). Legacy «топит» рисунок под лёд сама, её родные картинки насыщенные — поэтому обратное
# преобразование, иначе реклама в Legacy бледнее своей.
UNFADE = (0.62, 76.0)


def part_path(name):
    return os.path.join(PACK, "_parts", f"pilot_{name}.json")


def save_part(name, data):
    os.makedirs(os.path.dirname(part_path(name)), exist_ok=True)
    with open(part_path(name), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)


def entry(rel, typ, **kw):
    p = os.path.join(CACHE, *rel.split("/"))
    return {"file": rel, "type": typ, "md5": md5(p), "size": os.path.getsize(p), **kw}


def stage_kit(od):
    """Слои формы в размерах шаблона kit.json (у чистого sm Legacy 512² → 1024²) — папка для kitpaint pack."""
    meta = json.load(open(os.path.join(od, "kit.json"), encoding="utf-8"))
    sdir = os.path.join(TMP, "stage", os.path.basename(od))
    os.makedirs(sdir, exist_ok=True)
    for ln in STAGE_LAYERS:
        src, dst = os.path.join(od, ln + ".png"), os.path.join(sdir, ln + ".png")
        if not os.path.exists(src):
            if os.path.exists(dst):
                os.remove(dst)
            continue
        L = meta["layers"][ln]
        im = Image.open(src)
        if im.size != (L["w"], L["h"]):
            im = im.resize((L["w"], L["h"]), Image.LANCZOS)
        im.save(dst)
    shutil.copyfile(os.path.join(od, "kit.json"), os.path.join(sdir, "kit.json"))
    return sdir


def cmd_pack(a):
    from .helmet import fit, template_for, write_logo
    from .pack import centerlogo_template, legacy_has, write_rx2_rgba
    code = a.club
    club, art = club_info(code)
    entries, kits = [], []
    for label, family, kit, variant, new in kits_for(code):
        od = os.path.join(OUTP, f"{code}_{label}")
        info = json.load(open(os.path.join(od, "info.json"), encoding="utf-8"))
        if info.get("status") != "ok":
            print(code, label, "не собрана — пропуск", flush=True)
            continue
        newkit = f"1_{art}_{variant}"
        tpl = json.load(open(os.path.join(od, "kit.json"), encoding="utf-8"))["template"]
        sdir = stage_kit(od)
        odir = os.path.join(TMP, "kitpaint", f"{code}_{label}")
        cmd = [sys.executable, os.path.join(TOOLS, "kitpaint.py"), "pack", sdir, newkit, odir]
        if len(newkit) != len(tpl):
            cmd += ["--container", CONTAINER[len(newkit)]]
        cmd += ["--game", "legacy"]
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=TOOLS)
        if r.returncode != 0:
            raise SystemExit(f"{code} {label}: kitpaint pack — {(r.stdout + r.stderr).strip()[-600:]}")
        for kind, pat in KIT_PATHS.items():
            rel = pat.format(a=art, v=variant)
            built = os.path.join(odir, *rel.split("/"))
            if not new:
                orig = legacy_has(rel)
                if orig and open(orig, "rb").read() == open(built, "rb").read():
                    continue  # слой не менялся (карта номера и фамилии у дом/выезд) — файл EA остаётся
            dst = os.path.join(CACHE, *rel.split("/"))
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copyfile(built, dst)
            note = {"jersey": "свитер (гибрид NHL 24, рельеф Legacy T=4) и шрифт номеров",
                    "name": "карта номера и фамилии — домашней формы клуба", "pant": "шорты (3D из NHL 24)",
                    "sock": "гетры (3D из NHL 24)", "fe": "превью меню (свой рендер)"}[kind]
            entries.append(entry(rel, kind, club=code, kit=label, action="add" if new else "replace",
                                 note=f"{note}; NHL 24 {family}/{kit}"))
        if new:
            k = {"club": code, "kit": label, "variant": variant, "islightcolor": int(info["islightcolor"])}
            if label in LABELS:
                k["label"] = LABELS[label]
            kits.append(k)
        print(code, label, newkit, "— файлов", sum(1 for e in entries if e.get("kit") == label), flush=True)
    # центр льда
    src = os.path.join(NHL24, "out", "ice", f"centerlogo_{code}.png")
    tpl, _ours = centerlogo_template(art)
    rel = f"rendering/icesurface/centerlogo_{art}_cm.rx2"
    write_rx2_rgba(tpl, Image.open(src), os.path.join(CACHE, *rel.split("/")))
    entries.append(entry(rel, "center", club=code, action="replace", note="центр льда NHL 24 на основе EA (диск, кольцо)"))
    # наклейки на шлем
    folder, ok = extract_club(club)
    for label, family, kit, variant, new in kits_for(code):
        name = prefix(club, family, kit) + f"helmetlogo_{family}_{club}_{kit}_0_color"
        if name not in ok:
            continue
        logo = fit(Image.open(png(folder, name)).convert("RGBA"))
        if logo is None:
            continue
        rel = f"rendering/logo/texlib_{art}_1_{variant}.rx2"
        have, tpl = template_for(art, variant)
        write_logo(tpl, art, variant, logo, os.path.join(CACHE, *rel.split("/")))
        entries.append(entry(rel, "helmet", club=code, kit=label, action="replace" if have else "add",
                             note=f"наклейка на шлем NHL 24 {family}/{kit} (шаблон {os.path.basename(tpl)})"))
    save_part(code, {"files": entries, "kits": kits})
    print(f"{code}: файлов {len(entries)}, новых форм {len(kits)}")


def cmd_common(a):
    """Общее для всех: реклама и логотипы на льду (каталог ice_hotspot — те же номера в обеих играх), шайба."""
    import glob
    import re
    from .pack import LEGACY_BIG, legacy_has, write_rx2_rgba
    entries, skipped = [], []
    for p in sorted(glob.glob(os.path.join(LEGACY_BIG, "*", "rendering", "icesurface", "ice_hotspot_*_cm.rx2"))):
        m = re.match(r"ice_hotspot_(\d+)_(\d+)_cm\.rx2$", os.path.basename(p))
        src = os.path.join(HOTSPOT, f"ice_hotspot_{m.group(1)}_{m.group(2)}_color.png")
        if not os.path.exists(src):
            skipped.append(f"{os.path.basename(p)}: в NHL 24 нет")
            continue
        img = Image.open(src).convert("RGBA")
        if min(img.size) <= 32:
            skipped.append(f"{os.path.basename(p)}: в NHL 24 заглушка {img.size[0]}×{img.size[1]}")
            continue
        rel = f"rendering/icesurface/{os.path.basename(p)}"
        if a.unfade:
            arr = np.asarray(img).astype(np.float64)
            arr[..., :3] = np.clip((arr[..., :3] - UNFADE[1]) / UNFADE[0], 0, 255)
            img = Image.fromarray(np.round(arr).astype(np.uint8), "RGBA")
        write_rx2_rgba(p, img, os.path.join(CACHE, *rel.split("/")))
        entries.append(entry(rel, "ice", action="replace", note=f"NHL 24 ice_hotspot_{m.group(1)}_{m.group(2)}"
                             + (" (осветление NHL 24 снято)" if a.unfade else "")))
    for code in a.pucks.split(","):
        club, art = club_info(code)
        rel = f"rendering/puck/puck_{art}_cm.rx2"
        src = os.path.join(PUCK, f"puck_{club}_color.png")
        tpl = legacy_has(rel)
        if not os.path.exists(src) or not tpl:
            skipped.append(f"{rel}: нет {'текстуры NHL 24' if not os.path.exists(src) else 'файла Legacy'}")
            continue
        img = np.asarray(Image.open(src).convert("RGBA")).copy()
        img[..., 3] = 255  # у Legacy шайба DXT1 без прозрачности
        write_rx2_rgba(tpl, Image.fromarray(img), os.path.join(CACHE, *rel.split("/")))
        entries.append(entry(rel, "puck", club=code, action="replace",
                             note=f"шайба NHL 24 puck_{club} (та же развёртка 256×512)"))
    save_part("common", {"files": entries, "skipped": skipped})
    print(f"общее: файлов {len(entries)} (лёд {sum(e['type'] == 'ice' for e in entries)}, "
          f"шайба {sum(e['type'] == 'puck' for e in entries)}); пропущено {len(skipped)}")


def cmd_manifest(a):
    files, kits, clubs = [], [], []
    for name in a.club.split(",") + ["common"]:
        if not os.path.exists(part_path(name)):
            continue
        with open(part_path(name), encoding="utf-8") as f:
            part = json.load(f)
        files += part["files"]
        kits += part.get("kits", [])
        if name != "common":
            clubs.append(name)
    for e in files:  # сверка: файл в пакете тот же, что записан
        p = os.path.join(CACHE, *e["file"].split("/"))
        if md5(p) != e["md5"] or os.path.getsize(p) != e["size"]:
            raise SystemExit(f"{e['file']}: md5/размер изменились после упаковки — пересоберите часть")
    man = {"format": 1, "clubs": clubs, "files": files, "kits": kits,
           "note": "NHL 24 → NHL Legacy, пилот: " + ", ".join(clubs) + " и общее (реклама на льду, шайба). Ассеты NHL 24 — "
                   "только для личного использования. Решения: шнуровки нет (hastie 0), щит NHL −4 см, V-вставка в цвет "
                   "свитера, спонсорские нашивки на груди сняты, рельеф свитера — чистая карта Legacy T=4.",
           "excluded": EXCLUDED}
    with open(os.path.join(PACK, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(man, f, ensure_ascii=False, indent=1)
    by = {}
    for e in files:
        by[e["type"]] = by.get(e["type"], 0) + 1
    print("manifest.json:", len(files), "файлов", by, "новых форм", len(kits))


# ---------------------------------------------------------------- листы проверки

def _frame_of(mesh, pad=0.06):
    """Кадр (x0, x1, y0, y1) по рамке сетки с запасом."""
    b = kit3d.bbox(mesh)
    cx, cy = (b[0] + b[1]) / 2, (b[2] + b[3]) / 2
    w, h = (b[1] - b[0]) * (1 + pad), (b[3] - b[2]) * (1 + pad)
    return (cx - w / 2, cx + w / 2, cy - h / 2, cy + h / 2)


def cmd_sheets(a):
    from PIL import ImageDraw, ImageFont
    code = a.club
    club, art = club_info(code)
    f22 = ImageFont.truetype("C:/Windows/Fonts/segoeuib.ttf", 22)
    f16 = ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", 16)
    dst, _ = kit_hybrid.legacy_with_shirt()
    pL, sL = kit3d.load_legacy(PANT_L), kit3d.load_legacy(SOCK_L)
    fp, fs = _frame_of(pL), _frame_of(sL)
    rows = []
    for label, family, kit, variant, new in kits_for(code):
        od = os.path.join(OUTP, f"{code}_{label}")
        if not os.path.exists(os.path.join(od, "info.json")):
            continue
        info = json.load(open(os.path.join(od, "info.json"), encoding="utf-8"))
        t = kit3d.load_tex(os.path.join(od, "jersey_cm.png"))
        ims = [kit3d.render(dst, t, "front", 330, frame=kit3d.FRAME, ss=2),
               kit3d.render(dst, t, "back", 330, frame=kit3d.FRAME, ss=2),
               kit3d.render(dst, t, "front", 250, frame=kit3d.NECK, ss=2)]
        if os.path.exists(os.path.join(od, "pant_cm.png")):
            tp = kit3d.load_tex(os.path.join(od, "pant_cm.png"))
            ims += [kit3d.render(pL, tp, "front", 200, frame=fp, ss=2), kit3d.render(pL, tp, "back", 200, frame=fp, ss=2)]
        if os.path.exists(os.path.join(od, "sock_cm.png")):
            ts = kit3d.load_tex(os.path.join(od, "sock_cm.png"))
            ims += [kit3d.render(sL, ts, "front", 130, frame=fs, ss=2), kit3d.render(sL, ts, "left", 130, frame=fs, ss=2)]
        fe = Image.open(os.path.join(od, "fe.png")).convert("RGBA")
        bg = Image.new("RGBA", fe.size, (46, 46, 52, 255))
        ims.append(Image.alpha_composite(bg, fe).convert("RGB"))
        cap = (f"{label}  1_{art}_{variant}  {'новая' if new else 'замена'}  NHL 24 {family}/{kit}  "
               f"светлая {info.get('islightcolor')}  нашивок {len(info.get('patches', []))}")
        rows.append((cap, ims))
        print(label, flush=True)
    H = max(im.size[1] for _, ims in rows for im in ims)
    W = max(sum(im.size[0] + 8 for im in ims) for _, ims in rows) + 24
    S = Image.new("RGB", (W, 60 + len(rows) * (H + 40)), (30, 30, 34))
    d = ImageDraw.Draw(S)
    d.text((12, 12), f"{code}: все формы пилота — свитер спереди / сзади / ворот, шорты, гетры (3D), превью меню",
           fill=(240, 240, 240), font=f22)
    y = 60
    for cap, ims in rows:
        d.text((12, y), cap, fill=(225, 225, 225), font=f16)
        x = 12
        for im in ims:
            S.paste(im, (x, y + 24 + (H - im.size[1]) // 2))
            x += im.size[0] + 8
        y += H + 40
    out = os.path.join(NHL24, "compare", f"{code.lower()}_kits.png")
    S.save(out)
    print(out, S.size)
    sheet_pack(code, art)


def sheet_pack(code, art):
    """Лист «Legacy сейчас | из пакета» для центра льда, наклеек на шлем, шайбы и рекламы на льду."""
    from PIL import ImageDraw, ImageFont
    from .pack import legacy_has
    sys.path.insert(0, TOOLS)
    import teamart as ta
    f16 = ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", 16)
    f22 = ImageFont.truetype("C:/Windows/Fonts/segoeuib.ttf", 22)
    parts = []
    for name in (code, "common"):
        if os.path.exists(part_path(name)):
            with open(part_path(name), encoding="utf-8") as f:
                parts += json.load(f)["files"]

    def tex_of(path, k=0):
        rw = ta.Rw4.load(path)
        w, h, rgba = rw.decode(rw.textures[k])
        im = Image.frombytes("RGBA", (w, h), bytes(rgba))
        bg = Image.new("RGBA", im.size, (120, 124, 130, 255))
        return Image.alpha_composite(bg, im).convert("RGB")

    groups = [("center", 300), ("helmet", 256), ("puck", 160), ("ice", 150)]
    tiles = []
    for typ, size in groups:
        for e in [e for e in parts if e["type"] == typ]:
            new = tex_of(os.path.join(CACHE, *e["file"].split("/")))
            old = legacy_has(e["file"])
            old = tex_of(old) if old else Image.new("RGB", new.size, (60, 20, 20))
            sc = size / max(new.size)
            ns = (max(1, int(new.size[0] * sc)), max(1, int(new.size[1] * sc)))
            tiles.append((f"{typ}: {os.path.basename(e['file'])[:-4]} {e.get('kit', '')}", old.resize(ns), new.resize(ns)))
    cols = 4
    tw = max(o.size[0] * 2 + 30 for _, o, _ in tiles)
    th = max(o.size[1] for _, o, _ in tiles) + 30
    rows = (len(tiles) + cols - 1) // cols
    S = Image.new("RGB", (cols * tw + 20, 60 + rows * th), (30, 30, 34))
    d = ImageDraw.Draw(S)
    d.text((12, 12), f"{code} и общее: Legacy сейчас (слева) | из пакета NHL 24 (справа)", fill=(240, 240, 240), font=f22)
    for i, (lbl, o, n) in enumerate(tiles):
        x, y = 10 + (i % cols) * tw, 60 + (i // cols) * th
        d.text((x, y), lbl, fill=(220, 220, 220), font=f16)
        S.paste(o, (x, y + 24))
        S.paste(n, (x + o.size[0] + 10, y + 24))
    out = os.path.join(NHL24, "compare", f"{code.lower()}_pack_textures.png")
    S.save(out)
    print(out, S.size)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    for c in ("build", "pack", "manifest", "sheets"):
        s = sub.add_parser(c)
        s.add_argument("--club", default="CHI")
        if c == "build":
            s.add_argument("--kits", default="", help="только эти формы (метки через запятую)")
    s = sub.add_parser("common")
    s.add_argument("--pucks", default="CHI", help="шайбы каких клубов (коды через запятую)")
    s.add_argument("--no-unfade", dest="unfade", action="store_false", help="рекламу на льду — как в NHL 24 (бледную)")
    a = ap.parse_args()
    return {"build": cmd_build, "pack": cmd_pack, "common": cmd_common, "manifest": cmd_manifest,
            "sheets": cmd_sheets}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
