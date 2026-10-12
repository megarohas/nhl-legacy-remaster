"""Пилот одного клуба целиком: NHL 24 → NHL Legacy (офлайн, в игру не ставится). Сейчас — Чикаго (CHI).

  python -m fb.pilot build [--club CHI]     # формы: свитер (гибрид), шрифт, шорты и гетры (3D), превью меню
  python -m fb.pilot pack  [--club CHI]     # pack/cache: формы (kitpaint pack), центр льда, наклейки на шлем
  python -m fb.pilot common                 # общие: реклама и логотипы на льду (каталог ice_hotspot), шайба, клюшки
  python -m fb.pilot manifest [--club CHI]  # pack/manifest.json в формате legacy-data (docs/legacy-data.md)
  python -m fb.pilot sticks                 # клюшки из stick_map.toml [replace] (через 3D)
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

from . import kit3d, kit_fix, kit_hybrid
from .cas import REPO
from .kit_batch import CLEAN, CLEAN_T, CLUBS, MESH, collar_rule, legacy_target, prefix
from .pack import CACHE, PACK, TMP, TOOLS, md5

NHL24 = os.path.join(REPO, "game", "work", "nhl24")
OUTP = os.path.join(NHL24, "out", "pilot")
ALL_OUT = os.path.join(NHL24, "out", "all")          # собранные формы пакета на все клубы
ALL_PACK = os.path.join(NHL24, "out", "pack-all")    # пакет на все клубы (отдельно от pack/ пилота)
EXCLUDE = {"ARI": "ARI → Utah, не ставить"}
LEG = os.path.join(NHL24, "out", "_legacy_kits")
REGISTRY = os.path.join(REPO, "tools", "legacy_data", "nhl24_kits.json")
PANT_N24 = "content/character/skater/player/pant/common/components/player_pant_common_tightlong_lod0_mesh"
SOCK_N24 = "content/character/skater/player/sock/common/components/player_sock_common_notuck_mesh"
PANT_L = "rendering/pant/pant_1_0_0_2.rx2"
SOCK_L = "rendering/sock/playersock_1_2.rx2"
PANT_WAIST = 1.17  # у NHL 24 шорты с высоким поясом до груди; видимая часть — до ремня ~1,17 м


def set_roots(out_root=None, pack_root=None):
    """Куда собирать формы и пакет (по умолчанию — пилот: out/pilot, out/pack)."""
    global OUTP, PACK, CACHE, TMP
    if out_root:
        OUTP = out_root
    if pack_root:
        PACK, CACHE, TMP = pack_root, os.path.join(pack_root, "cache"), os.path.join(pack_root, "_build")


def proposals():
    """Номера новых форм, ещё не записанные в реестр: проба nhl24.py alloc (PACK/alloc_request.json)."""
    p = os.path.join(PACK, "alloc_request.json")
    if not os.path.exists(p):
        return {}
    with open(p, encoding="utf-8") as f:
        return {(r["club"], r["kit"]): r for r in json.load(f)["request"]}


def club_info(code):
    for club, art, c in CLUBS:
        if c == code:
            return club, art
    raise SystemExit(f"нет клуба {code}")


# Правило пользователя (10.10): из NHL 24 ставим только основные комплекты — дом, выезд и третью (если есть).
# RR22/RR23, 90-е и прочие спецформы собраны (out/pilot), но в пакет не идут, пока не решат иначе (--all-kits).
MAIN_KITS = ("home", "away", "three")
ALL_KITS = False


def kits_for(code, main_only=None):
    """[(label, family, kit, variant, new?)] — строки Legacy и реестр новых форм (по умолчанию — только основные)."""
    main_only = (not ALL_KITS) if main_only is None else main_only
    return [k for k in _kits_for(code) if not main_only or k[0] in MAIN_KITS]


def _kits_for(code):
    """Правило пользователя (10.10, 05:50): формы NHL 24 — только новыми строками, прежние (EA и наши SEA/VGK) не
    перезаписываются. Номера всех — из реестра legacy-data (дом, выезд, третья — подряд после форм EA)."""
    club, art = club_info(code)
    with open(REGISTRY, encoding="utf-8") as f:
        reg = [r for r in json.load(f)["kits"] if r["club"] == code]
    out = []
    src = third_source()
    for label in MAIN_KITS:
        r = next((k for k in reg if k["kit"] == label), None)
        kit = src.get(code, "three") if label == "three" else label
        out.append((label, "adidas", kit, r["variant"] if r else None, True))
    for r in reg:
        lab = r["kit"]
        if lab in MAIN_KITS:
            continue
        fam, kit = ("nineties", lab[4:]) if lab.startswith("n90_") else ("adidas", {"rr22": "twentytwo",
                                                                                     "rr23": "twentythree"}[lab])
        out.append((lab, fam, kit, r["variant"], True))
    return out


def third_source():
    """Папка комплекта NHL 24 для третьей (kit_rules.toml [third_source]; по умолчанию adidas/three)."""
    import tomllib
    with open(kit_hybrid.RULES, "rb") as f:
        return tomllib.load(f).get("third_source", {})


def home_template(art):
    """Шаблон kitpaint для новой формы: домашняя форма клуба в Legacy; у наших SEA/VGK (100/101) — контейнер
    3-значного арта 1_131_0 (карта номеров — наша, из legacy-data out)."""
    if art in (100, 101):
        return "1_131_0"
    return f"1_{art}_{legacy_target(art, 0)['variant']}"


OURS_NAME = False  # 11.10: у новых форм SEA/VGK — карта номеров контейнера EA 1_131_0 (зоны рукавов как у EA),
                  # а не наша czkit-карта: её зоны рукавов вдвое больше и номер ложился на полосы рукава


def ours_name(art, od):
    """SEA/VGK: карта номеров и фамилии нашей домашней формы (legacy-data out) → od/name_cm.png. -> путь или None."""
    stale = os.path.join(od, "name_cm.png")
    if not OURS_NAME:
        if os.path.exists(stale):
            os.remove(stale)
        return None
    from .pack import OURS
    p = os.path.join(OURS, "rendering", "jersey", f"name_1_{art}_0_cm.rx2")
    if art not in (100, 101) or not os.path.exists(p):
        return None
    sys.path.insert(0, TOOLS)
    import teamart as ta
    rw = ta.Rw4.load(p)
    w, h, rgba = rw.decode(rw.textures[0])
    out = os.path.join(od, "name_cm.png")
    Image.frombytes("RGBA", (w, h), bytes(rgba)).save(out)
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
    rx = (f"^content/character/skater/league/nhl/{club}/(adidas/[a-z]+|nineties/[a-z]+)/"
          f"(jersey|font|pant|sock|helmetlogo)_(adidas|nineties)_{club}_[a-z]+_(base_)?(color|normal|[0-9]_color)$")
    subprocess.run([sys.executable, "-m", "fb.extract", rx, "--out", f"club_{club}"], check=True, cwd=TOOLS)
    folder = os.path.join(NHL24, "extract", f"club_{club}")
    with open(os.path.join(folder, "_index.csv"), encoding="utf-8") as f:
        ok = {r["name"] for r in csv.DictReader(f) if r["status"] == "ok"}
    return folder, ok


def png(folder, name):
    return os.path.join(folder, *name[len("content/"):].split("/")) + ".png"


POSE = os.path.join(REPO, "game", "work", "legacy-data", "fepose", "pose.bin")  # модель позы EA (tools/fepose.py fit)
_POSE = []


def _pose():
    if not _POSE:
        if TOOLS not in sys.path:
            sys.path.insert(0, TOOLS)
        import fepose
        m = fepose.load_model(POSE)
        U = np.full((m["h"], m["w"]), np.nan)
        V = np.full((m["h"], m["w"]), np.nan)
        U[m["ys"], m["xs"]], V[m["ys"], m["xs"]] = m["u"], m["v"]
        # выбросы карты UV (одиночные пиксели, не похожие ни на одного соседа: подгонка по корреляции там ошиблась —
        # на новых рисунках дают крапины у ворота, плеч и боков) → медиана соседей; 2 прохода
        for _ in range(2):
            nb = [(np.roll(np.roll(U, dy, 0), dx, 1), np.roll(np.roll(V, dy, 0), dx, 1))
                  for dy in (-1, 0, 1) for dx in (-1, 0, 1) if dy or dx]
            su, sv = np.stack([a for a, _b in nb]), np.stack([b for _a, b in nb])
            close = (np.abs(su - U[None]) + np.abs(sv - V[None]) < 0.012) & np.isfinite(su)
            iso = np.isfinite(U) & (close.sum(0) < 2) & (np.isfinite(su).sum(0) >= 3)
            with np.errstate(all="ignore"):
                import warnings
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", RuntimeWarning)
                    mu, mv = np.nanmedian(su, 0), np.nanmedian(sv, 0)
            U, V = np.where(iso, mu, U), np.where(iso, mv, V)
        m["U"], m["V"] = U, V
        m["u"], m["v"] = U[m["ys"], m["xs"]], V[m["ys"], m["xs"]]
        _POSE.append(m)
    return _POSE[0]


def _uv_at(m, y, x, jump=0.04, home=None):
    """UV в дробной точке превью: билинейно по соседним пикселям свитера той же «островной» области развёртки
    (сосед с прыжком UV > jump — другой остров, не смешивается); нет соседей — UV центра пикселя."""
    U, V = m["U"], m["V"]
    H, W = U.shape
    yi, xi = np.round(y).astype(int), np.round(x).astype(int)
    uc, vc = U[np.clip(yi, 0, H - 1), np.clip(xi, 0, W - 1)], V[np.clip(yi, 0, H - 1), np.clip(xi, 0, W - 1)]
    if home is not None:  # ближайший пиксель — не свитер: опора — UV самого пикселя превью
        bad = ~np.isfinite(uc) | (np.abs(uc - home[0]) >= jump) | (np.abs(vc - home[1]) >= jump)
        uc, vc = np.where(bad, home[0], uc), np.where(bad, home[1], vc)
    y0, x0 = np.floor(y).astype(int), np.floor(x).astype(int)
    fy, fx = y - y0, x - x0
    su = np.zeros_like(y)
    sv = np.zeros_like(y)
    sw = np.zeros_like(y)
    for dy, wy in ((0, 1 - fy), (1, fy)):
        for dx, wx in ((0, 1 - fx), (1, fx)):
            yy, xx = np.clip(y0 + dy, 0, H - 1), np.clip(x0 + dx, 0, W - 1)
            u, v = U[yy, xx], V[yy, xx]
            ok = np.isfinite(u) & (np.abs(u - uc) < jump) & (np.abs(v - vc) < jump)
            w = wy * wx * ok
            su += np.where(ok, u, 0) * w
            sv += np.where(ok, v, 0) * w
            sw += w
    good = sw > 1e-6
    return np.where(good, su / np.maximum(sw, 1e-9), uc), np.where(good, sv / np.maximum(sw, 1e-9), vc)


def fe_preview_ea(jersey_png, ss=4, foot=1.25):
    """Превью меню как у EA (манекен, руки опущены, свет и кадр EA): модель позы tools/fepose.py по развёртке свитера.
    Сглаживание: на пиксель превью ss×ss точек (UV между пикселями — билинейно в пределах острова развёртки), цвет —
    среднее по развёртке 1024², затем gain·цвет + bias модели (как у EA: края полос и нашивок мягкие, без лесенки)."""
    m = _pose()
    tex = np.asarray(Image.open(jersey_png).convert("RGB")).astype(np.float64)
    ys, xs = m["ys"].astype(np.float64), m["xs"].astype(np.float64)
    acc = np.zeros((len(ys), 3))
    offs = ((np.arange(ss) + 0.5) / ss - 0.5) * foot  # foot > 1 — шире пикселя (мягче, как у EA)
    for oy in offs:
        for ox in offs:
            u, v = _uv_at(m, ys + oy, xs + ox, home=(m["u"], m["v"]))
            acc += kit3d.sample_bilinear(tex, u, v)[:, :3]
    c = acc / (ss * ss)
    col = np.clip(m["gain"] * c + m["bias"], 0, 255)
    out = m["base"].copy()
    out[m["ys"], m["xs"], :3] = np.round(col).astype(np.uint8)
    out[m["ys"], m["xs"], 3] = m["alpha"]
    return Image.fromarray(out, "RGBA")


def fe_preview(jersey_mesh, tex, size=256):
    """Превью меню 256² (RGBA, прозрачный фон): свитер Legacy спереди, свой рендер (модель позы EA пропала 09.10)."""
    im = kit3d.render(jersey_mesh, tex, "front", 512, bg=(0, 0, 0), frame=(-0.62, 0.62, 0.62, 1.86), ss=2)
    a = np.asarray(im).astype(np.float64)
    alpha = (a.sum(-1) > 6).astype(np.uint8) * 255
    rgba = np.dstack([a.astype(np.uint8), alpha])
    return Image.fromarray(rgba, "RGBA").resize((size, size), Image.LANCZOS)


NAME_CONTRAST = 3.0  # фамилия должна читаться: контраст букв со свитером там, где она стоит (по WCAG), не ниже


def _lum(c):
    c = np.asarray(c, dtype=np.float64) / 255
    c = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def _contrast(a, b):
    la, lb = _lum(a), _lum(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def name_zone(kit, own=None):
    """Место фамилии на развёртке свитера: зона 0 карты номеров (name_*_cm, синий канал) комплекта-шаблона, 256²."""
    a = np.asarray(Image.open(own or os.path.join(unpack(kit), "name_cm.png")).convert("RGBA")).astype(int)
    return (a[..., 0] > 128) & (a[..., 1] > 128) & (a[..., 2] == 0)


def name_contrast(cm, jersey_png, zone, min_ratio=NAME_CONTRAST):
    """Буквы фамилии (верхние строки атласа шрифта) того же цвета, что свитер под ними (у NHL 24 n90_three CHI —
    чёрные на чёрной кокетке: в NHL 24 фамилия, видимо, на светлой полосе, в Legacy место — по карте номеров шаблона):
    тогда буквы — цветом заливки цифр (или белым/чёрным, что контрастнее). -> (атлас, пометка или None)."""
    from scipy import ndimage as ndi
    j = np.asarray(Image.open(jersey_png).convert("RGB").resize(zone.shape[::-1], Image.BOX)).astype(np.float64)
    jc = np.median(j[zone], 0)
    H, W = cm.shape[:2]
    lab, n = ndi.label(cm[..., 3] > 40)
    if n == 0:
        return cm, None
    cy = ndi.center_of_mass(np.ones_like(lab), lab, range(1, n + 1))
    letters = np.isin(lab, [i + 1 for i, (y, _x) in enumerate(cy) if y < 0.19 * H])
    solid = cm[..., 3] > 200
    if not (letters & solid).any():
        return cm, None
    lc = np.median(cm[..., :3][letters & solid], 0)
    r = _contrast(lc, jc)
    if r >= min_ratio:
        return cm, None
    num = np.zeros_like(solid)
    num[int(0.21 * H):int(0.70 * H), :int(0.80 * W)] = True
    nc = np.median(cm[..., :3][num & solid], 0)
    cands = [nc, np.array([235.0, 235, 235]), np.array([20.0, 20, 20])]
    target = max(cands, key=lambda c: _contrast(c, jc) + (0.5 if c is nc else 0))
    out = cm.copy()
    out[letters, :3] = np.round(target).astype(np.uint8)
    return out, (f"фамилия: буквы {lc.astype(int).tolist()} → {target.astype(int).tolist()} (контраст со свитером "
                 f"{r:.1f} → {_contrast(target, jc):.1f})")


def lightness(tex):
    a = np.asarray(Image.open(tex).convert("RGB").resize((64, 64))).astype(np.float64) / 255
    return float((0.2126 * a[..., 0] + 0.7152 * a[..., 1] + 0.0722 * a[..., 2]).mean())


def sleeve_rule(od, tpl=None):
    """Полоски рукавов ближе к кисти (kit_rules.toml [sleeve]): jersey_cm.png = правило(jersey_cm_raw.png).
    Свитер, собранный до правила, — сам себе сырой (копия в jersey_cm_raw.png). -> план {зона: …} (и в info.json)."""
    from . import sleeve
    raw, cm = os.path.join(od, "jersey_cm_raw.png"), os.path.join(od, "jersey_cm.png")
    if not os.path.exists(raw):
        shutil.copyfile(cm, raw)
    a = np.asarray(Image.open(raw).convert("RGB"))
    tpl = tpl or json.load(open(os.path.join(od, "kit.json"), encoding="utf-8"))["template"]  # при сборке kit.json ещё нет
    zones = sleeve.name_zones(os.path.join(unpack(tpl), "name_cm.png"), a.shape[0])
    if not _ISLAND:
        _ISLAND.append(sleeve.island(a.shape[0]))
    new, plan = sleeve.remap(a, zones, _ISLAND[0])
    Image.fromarray(new).save(cm)
    plan = {str(z): q for z, q in plan.items()}
    info = os.path.join(od, "info.json")
    if os.path.exists(info):
        rec = json.load(open(info, encoding="utf-8"))
        rec["sleeve"] = plan
        text = json.dumps(rec, ensure_ascii=False, indent=1)     # сначала в строку: сбой не обрежет info.json
        with open(info + ".tmp", "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(info + ".tmp", info)
    return plan


_ISLAND = []


def cmd_sleeves(a):
    """Только правило рукавов и превью меню у готовых форм (рендер переноса не повторяется)."""
    codes = [c for _cl, _a, c in CLUBS if c not in EXCLUDE] if a.club == "all" else a.club.split(",")
    only = set(a.kits.split(",")) if a.kits else None
    n = 0
    for code in codes:
        for label, *_rest in kits_for(code):
            od = os.path.join(OUTP, f"{code}_{label}")
            if (only and label not in only) or not os.path.exists(os.path.join(od, "info.json")):
                continue
            ours_name(club_info(code)[1], od)   # SEA/VGK: убрать прежнюю czkit-карту номеров
            sleeve_rule(od)
            fe_preview_ea(os.path.join(od, "jersey_cm.png")).save(os.path.join(od, "fe.png"))
            n += 1
            print(code, label, "рукава и превью обновлены", flush=True)
    print(f"форм: {n}")


def build_font(rec, folder, ok, p, family, club, kit, od, tpl_kit, own_name):
    from .fonts import normal_map, resize_premult
    fc, fn = p + f"font_{family}_{club}_{kit}_color", p + f"font_{family}_{club}_{kit}_normal"
    if fc not in ok:
        rec["font"] = "нет текстуры шрифта — останется шаблона"
        return
    cm = resize_premult(np.asarray(Image.open(png(folder, fc)).convert("RGBA")), 512)
    cm, fix = name_contrast(cm, os.path.join(od, "jersey_cm.png"), name_zone(tpl_kit, own_name))
    if fix:
        rec["font_fix"] = fix
    nm = normal_map(png(folder, fn), 512) if fn in ok else np.dstack(
        [np.full((512, 512), v, np.uint8) for v in (128, 128, 255, 255)])
    sm = np.zeros((512, 512, 4), np.uint8)
    sm[..., :3] = 21
    sm[..., 3] = np.where(cm[..., 3] > 128, 255, 0)
    Image.fromarray(cm).save(os.path.join(od, "font_cm.png"))
    Image.fromarray(nm).save(os.path.join(od, "font_nm.png"))
    Image.fromarray(sm).save(os.path.join(od, "font_sm.png"))
    rec["font"] = "ok"


def finish_kit(rec, od, tpl_kit, art, variant, label, mode, patches, t0, pant=None, sock=None):
    """kit.json шаблона и info.json. Светлота: дом — тёмная (0), выезд — светлая (1), как требует сборка legacy-data
    (по умолчанию в матчах — новые дом и выезд); третья — по яркости свитера."""
    shutil.copyfile(os.path.join(unpack(tpl_kit), "kit.json"), os.path.join(od, "kit.json"))
    light = {"home": 0, "away": 1}.get(label, int(lightness(os.path.join(od, "jersey_cm.png")) > 0.5))
    rec.update(status="ok", mode=mode, template=tpl_kit, legacy_kit=f"1_{art}_{variant}", islightcolor=light,
               measured_light=round(lightness(os.path.join(od, "jersey_cm.png")), 3), patches=patches,
               sec=round(time.time() - t0, 1))
    if pant is not None:
        rec.setdefault("pant", pant)
        rec.setdefault("sock", sock)
    with open(os.path.join(od, "info.json"), "w", encoding="utf-8") as f:
        json.dump(rec, f, ensure_ascii=False, indent=1)


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
        tpl_kit = home_template(art)
        own_name = ours_name(art, od)
        done = all(os.path.exists(os.path.join(od, n)) for n in ("jersey_cm.png", "pant_cm.png", "sock_cm.png", "fe.png"))
        if getattr(a, "reuse", False) and done and os.path.exists(os.path.join(od, "info.json")):
            # рендер от номера варианта не зависит — меняются шаблон, номер, светлота; шрифт — заново (дёшево)
            old = json.load(open(os.path.join(od, "info.json"), encoding="utf-8"))
            rec["sleeve"] = sleeve_rule(od, tpl_kit)
            fe_preview_ea(os.path.join(od, "jersey_cm.png")).save(os.path.join(od, "fe.png"))
            build_font(rec, folder, ok, p, family, club, kit, od, tpl_kit, own_name)
            finish_kit(rec, od, tpl_kit, art, variant, label, old.get("mode", ""), old.get("patches", []), t0,
                       pant=old.get("pant", ""), sock=old.get("sock", ""))
            report.append(rec)
            print(code, label, f"1_{art}_{variant}", "рендер прежний, шрифт и данные обновлены", flush=True)
            continue
        if family not in srcs:
            srcs[family] = kit3d.load_nhl24(MESH[family])
            tids[family], _ = kit3d.raster_uv(srcs[family], 1024)
        src, tid24 = srcs[family], tids[family]
        defaults, rules = kit_hybrid.load_rules(kit_hybrid.RULES, code, label, [])
        lace_rule = kit_fix.collar_lace_rule(code, label)
        if lace_rule:  # щит NHL — из ворота EA (по контуру), свой не ставится
            rules.setdefault("neck_shield", {})["enabled"] = False
        fit = kit_fix.crest_fit(os.path.join(unpack(tpl_kit), "name_cm.png"))  # герб не на букву капитана
        comp = kit3d.load_tex(png(folder, jc))
        bc = p + f"jersey_{family}_{club}_{kit}_base_color"
        if bc in ok and Image.open(png(folder, bc)).size == (comp.shape[1], comp.shape[0]):
            base = kit3d.load_tex(png(folder, bc))
            lab, patches = kit_hybrid.find_patches(comp, base, defaults)
            mode = "base"
        else:
            names = ("neck_shield", "back_neck") + tuple(k for k, r in rules.items() if r.get("sponsor"))
            if fit:  # герб — тоже декалью, чтобы его можно было уменьшить
                names += ("crest",)
            base, lab, patches = kit_hybrid.standard_patches(comp, rules, defaults, names=names)
            mode = "без base: щит NHL, логотип сзади" + (" и герб" if fit else "") + " — декалями"
        if mode == "base":  # спонсор зашит в сам base (у MIN — Tria): тоже снимается — закраской по строкам
            sp = tuple(k for k, r in rules.items() if r.get("sponsor"))
            base, _lab_sp, sp_found = kit_hybrid.standard_patches(base, rules, defaults, names=sp)
            if sp_found:
                rec["sponsor_in_base"] = len(sp_found)
        placed, soft = kit_hybrid.plan_decals(comp, lab, patches, rules, defaults, src, dst, tid24)
        missing_std = [nm for nm in ("neck_shield", "back_neck") if nm not in [pl["name"] for pl in placed]
                       and rules.get(nm, {}).get("enabled", True)]  # выключенная правилом — не «потерянная»
        if missing_std and mode == "base":
            base, lab2, patches2 = kit_hybrid.standard_patches(base, rules, defaults, names=tuple(missing_std))
            off = int(lab.max()) + 10
            lab = np.where(lab2 > 0, lab2 + off, lab)
            p2, s2 = kit_hybrid.plan_decals(comp, lab, [(lid + off, sl, ar) for lid, sl, ar in patches2], rules,
                                            defaults, src, dst, tid24)
            placed += p2
            soft.update(s2)
        collar = (crule, kit_hybrid.collar_color(base, crule)) if crule.get("mode", "body") == "body" else None
        pre, band = [], kit_fix.club_rule("chest_band", code, label)
        if lace_rule:  # ворот со шнуровкой без 3D-шнурков по EA-комплекту lace_rule.from, цвета клуба
            laces_fix = kit_fix.CollarLace(lace_rule, base, unpack(lace_rule["from"]))
            pre.append(laces_fix.pre)
            collar = (crule, laces_fix.insert)
            rec["collar_lace"] = laces_fix.report
        if band:
            band_fix = kit_fix.BandTrim(band)
            pre.append(band_fix)
        post = kit_hybrid.decal_post(comp, placed, soft, n_jersey_tri, collar, pre=pre, crest_fit=fit,
                                     protect=laces_fix.area if lace_rule else None)
        img, mask, dist, info = kit3d.transfer(base, src, dst, 1024, 2, post=post)
        if band:
            rec["chest_band"] = getattr(band_fix, "report", None)
        Image.fromarray(np.clip(img, 0, 255).astype(np.uint8)).convert("RGB").save(os.path.join(od, "jersey_cm_raw.png"))
        rec["sleeve"] = sleeve_rule(od, tpl_kit)
        Image.open(os.path.join(CLEAN, f"{CLEAN_T}_3-12-21-30-39-48-57-66-75_sm.png")).resize((1024, 1024), Image.LANCZOS) \
            .save(os.path.join(od, "jersey_sm.png"))
        shutil.copyfile(os.path.join(CLEAN, f"{CLEAN_T}_3-12-21-30-39-48-57-66-75_nm.png"), os.path.join(od, "jersey_nm.png"))
        if lace_rule:
            laces_fix.relief(os.path.join(od, "jersey_nm.png"), os.path.join(od, "jersey_sm.png"), os.path.join(NHL24, "relief"))
        build_font(rec, folder, ok, p, family, club, kit, od, tpl_kit, own_name)
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
        fe_preview_ea(os.path.join(od, "jersey_cm.png")).save(os.path.join(od, "fe.png"))
        finish_kit(rec, od, tpl_kit, art, variant, label, mode,
                   [{k: v for k, v in pl.items() if not k.startswith("_")} for pl in placed], t0)
        report.append(rec)
        print(code, label, f"1_{art}_{variant}", mode[:6], "шрифт", rec["font"][:2], "шорты", rec["pant"][:2], "гетры",
              rec["sock"][:2], f"{rec['sec']} с", flush=True)
    rp = os.path.join(OUTP, f"{code}_report.json")
    if only and os.path.exists(rp):  # частичная пересборка — остальные записи отчёта прежние
        with open(rp, encoding="utf-8") as f:
            old = [r for r in json.load(f) if r["kit"] not in only]
        order = [k[0] for k in kits_for(code, main_only=False)]
        report = sorted(old + report, key=lambda r: order.index(r["kit"]) if r["kit"] in order else 99)
    with open(rp, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)


# ---------------------------------------------------------------- упаковка (формат 1 legacy-data)

KIT_PATHS = {"jersey": "rendering/jersey/texlib_1_{a}_{v}.rx2", "name": "rendering/jersey/name_1_{a}_{v}_cm.rx2",
             "pant": "rendering/pant/texlib_1_{a}_{v}.rx2", "sock": "rendering/sock/sock_1_{a}_{v}_cm.rx2",
             "fe": "fe/ion/artassets/jerseys/jersey_1_{a}_{v}.big"}
STAGE_LAYERS = ("jersey_cm", "jersey_sm", "jersey_nm", "font_cm", "font_nm", "font_sm", "name_cm", "pant_cm", "sock_cm",
                "fe")
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
    from .pack import OURS, centerlogo_template, legacy_has, write_rx2_rgba
    code = a.club
    club, art = club_info(code)
    only = set(a.kits.split(",")) if getattr(a, "kits", "") else None
    entries, kits = [], []
    for label, family, kit, variant, new in kits_for(code):
        if only and label not in only:
            continue
        od = os.path.join(OUTP, f"{code}_{label}")
        if not os.path.exists(os.path.join(od, "info.json")):
            print(code, label, "не собрана (нет в NHL 24) — пропуск", flush=True)
            continue
        info = json.load(open(os.path.join(od, "info.json"), encoding="utf-8"))
        if info.get("status") != "ok":
            print(code, label, "не собрана — пропуск", flush=True)
            continue
        if variant is None:
            print(code, label, "нет номера в реестре — не упакована", flush=True)
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
            if legacy_has(rel) or os.path.exists(os.path.join(OURS, *rel.split("/"))):
                raise SystemExit(f"{code} {label}: {rel} — файл уже существующего комплекта, в пакет нельзя "
                                 f"(формы NHL 24 только новыми номерами)")
            dst = os.path.join(CACHE, *rel.split("/"))
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copyfile(built, dst)
            note = {"jersey": "свитер (гибрид NHL 24, рельеф Legacy T=4) и шрифт номеров",
                    "name": "карта номера и фамилии — домашней формы клуба", "pant": "шорты (3D из NHL 24)",
                    "sock": "гетры (3D из NHL 24)", "fe": "превью меню (свой рендер)"}[kind]
            entries.append(entry(rel, kind, club=code, kit=label, action="add" if new else "replace",
                                 note=f"{note}; NHL 24 {family}/{kit}"))
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
        if only and label not in only:
            continue
        name = prefix(club, family, kit) + f"helmetlogo_{family}_{club}_{kit}_0_color"
        if name not in ok or variant is None or not os.path.exists(os.path.join(OUTP, f"{code}_{label}", "info.json")):
            continue
        logo = fit(Image.open(png(folder, name)).convert("RGBA"))
        if logo is None:
            continue
        rel = f"rendering/logo/texlib_{art}_1_{variant}.rx2"
        have, tpl = template_for(art, variant)
        if have or os.path.exists(os.path.join(OURS, *rel.split("/"))):
            raise SystemExit(f"{code} {label}: {rel} — наклейка уже существующего комплекта, в пакет нельзя")
        write_logo(tpl, art, variant, logo, os.path.join(CACHE, *rel.split("/")))
        entries.append(entry(rel, "helmet", club=code, kit=label, action="add",
                             note=f"наклейка на шлем NHL 24 {family}/{kit} (шаблон {os.path.basename(tpl)})"))
    save_part(code, {"files": entries, "kits": kits})
    print(f"{code}: файлов {len(entries)}, новых форм {len(kits)}")


def cmd_common(a):
    """Общее для всех: реклама и логотипы на льду (каталог ice_hotspot — те же номера в обеих играх), шайба."""
    import glob
    import re
    from .pack import LEGACY_BIG, OURS, legacy_has, write_rx2_rgba
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
    codes = [c for _cl, _a, c in CLUBS if c not in EXCLUDE] if a.pucks == "all" else a.pucks.split(",")
    for code in codes:
        club, art = club_info(code)
        rel = f"rendering/puck/puck_{art}_cm.rx2"
        src = os.path.join(PUCK, f"puck_{club}_color.png")
        ours = os.path.join(OURS, *rel.split("/"))
        tpl = legacy_has(rel) or (ours if os.path.exists(ours) else None)  # SEA/VGK — наши файлы legacy-data
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
    names = [c for _cl, _a, c in CLUBS if c not in EXCLUDE] if a.club == "all" else a.club.split(",")
    for name in names + ["common", "sticks"]:
        if not os.path.exists(part_path(name)):
            continue
        with open(part_path(name), encoding="utf-8") as f:
            part = json.load(f)
        files += part["files"]
        kits += part.get("kits", [])
        if name not in ("common", "sticks"):
            clubs.append(name)
    for e in files:  # сверка: файл в пакете тот же, что записан
        p = os.path.join(CACHE, *e["file"].split("/"))
        if md5(p) != e["md5"] or os.path.getsize(p) != e["size"]:
            raise SystemExit(f"{e['file']}: md5/размер изменились после упаковки — пересоберите часть")
    man = {"format": 1, "clubs": clubs, "files": files, "kits": kits,
           "note": ("NHL 24 → NHL Legacy, все клубы (" + str(len(clubs)) + ")" if a.club == "all" else
                    "NHL 24 → NHL Legacy, пилот: " + ", ".join(clubs)) + " и общее (реклама на льду, шайба). Ассеты NHL 24 — "
                   "только для личного использования. Формы NHL 24 — только новыми строками (дом, выезд, третья; прежние "
                   "формы EA и наши SEA/VGK не меняются). Решения: шнуровки нет (hastie 0), щит NHL −4 см, V-вставка в "
                   "цвет свитера, спонсорские нашивки на груди сняты, рельеф свитера — чистая карта Legacy T=4.",
           "excluded": EXCLUDED}
    with open(os.path.join(PACK, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(man, f, ensure_ascii=False, indent=1)
    by = {}
    for e in files:
        by[e["type"]] = by.get(e["type"], 0) + 1
    print("manifest.json:", len(files), "файлов", by, "новых форм", len(kits))


STICKS = os.path.join(NHL24, "extract", "sticks24", "character", "skater", "player", "stick")
STICK_MAP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stick_map.toml")


def cmd_sticks(a):
    """Клюшки из stick_map.toml [replace] (номер Legacy → текстура NHL 24) — через 3D; [same] не кладутся."""
    import tomllib
    from .pack import legacy_has, write_rx2_rgba
    with open(STICK_MAP, "rb") as f:
        mp = tomllib.load(f)
    rep = {int(k): v for k, v in mp.get("replace", {}).items()}
    entries = []
    if rep:
        c = "content/character/skater/player/stick/common/components/"
        src = kit_hybrid.merge(kit3d.load_nhl24(c + "player_stick_left_shaft_mesh"),
                               kit3d.load_nhl24(c + "player_stick_left_blade_mesh"))
        dst = kit3d.load_legacy("rendering/playerstick/playerstick_0_2.rx2")
        for n, name in sorted(rep.items()):
            rel = f"rendering/playerstick/texlib_{n}.rx2"
            img, _m, _d, _i = kit3d.transfer(kit3d.load_tex(os.path.join(STICKS, *name.split("/")) + "_color.png"),
                                             src, dst, (1024, 128), 2)
            rgba = np.dstack([np.clip(img[..., :3], 0, 255).astype(np.uint8), np.full(img.shape[:2], 255, np.uint8)])
            write_rx2_rgba(legacy_has(rel), Image.fromarray(rgba, "RGBA"), os.path.join(CACHE, *rel.split("/")))
            entries.append(entry(rel, "stick", action="replace", note=f"клюшка NHL 24 {name.split('/')[-1]} (3D)"))
    save_part("sticks", {"files": entries})
    print(f"клюшки: в пакет {len(entries)} (замены из [replace]); та же модель в обеих играх — {len(mp.get('same', {}))}, "
          f"не кладутся")


def cmd_fe(a):
    """Только превью меню (fe.png) по готовым развёрткам — в позе EA; остальное не трогается."""
    codes = [c for _cl, _a, c in CLUBS if c not in EXCLUDE] if a.club == "all" else a.club.split(",")
    n = 0
    for code in codes:
        for label, *_rest in kits_for(code):
            od = os.path.join(OUTP, f"{code}_{label}")
            if os.path.exists(os.path.join(od, "jersey_cm.png")) and os.path.exists(os.path.join(od, "info.json")):
                fe_preview_ea(os.path.join(od, "jersey_cm.png")).save(os.path.join(od, "fe.png"))
                n += 1
    print(f"превью в позе EA: {n}")


def cmd_fe_sheet(a):
    """Лист «EA | новое»: превью меню форм EA клуба и новых форм NHL 24 (как в игре — на тёмном фоне)."""
    from PIL import ImageDraw, ImageFont
    sys.path.insert(0, TOOLS)
    import kitpaint as kp
    import teamart as ta
    import gameprofile
    gameprofile.use("legacy") if hasattr(gameprofile, "use") else None
    f16 = ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", 16)
    f20 = ImageFont.truetype("C:/Windows/Fonts/segoeuib.ttf", 20)
    code = a.club
    club, art = club_info(code)
    with open(os.path.join(NHL24, "catalog", "legacy_kits.json"), encoding="utf-8") as f:
        rows = [r for r in json.load(f).get(str(art), []) if r[4] == art]
    ea = []
    from .pack import legacy_has
    for loc, v, *_ in rows:
        rel = f"fe/ion/artassets/jerseys/jersey_1_{art}_{v}.big"
        path = legacy_has(rel)
        if not path:
            continue
        w, h, rgba = ta.UiLogo(kp._unchunk(open(path, "rb").read()) if hasattr(kp, "_unchunk") else open(path, "rb").read(),
                               rel).decode()
        ea.append((f"EA 1_{art}_{v}", Image.frombytes("RGBA", (w, h), bytes(rgba))))
    new = []
    for label, _f, _k, variant, _n in kits_for(code):
        fe = os.path.join(OUTP, f"{code}_{label}", "fe.png")
        if os.path.exists(fe):
            new.append((f"NHL 24 {label} 1_{art}_{variant}", Image.open(fe).convert("RGBA")))
    z = a.zoom
    cols = max(len(ea), len(new))
    cw, chh = 256 * z + 20, 256 * z + 44
    S = Image.new("RGB", (20 + cols * cw, 60 + 2 * chh), (24, 24, 28))
    d = ImageDraw.Draw(S)
    d.text((12, 12), f"{code}: превью меню ×{z} — сверху формы EA, снизу новые NHL 24 (поза EA, сглаживание 4×4)",
           fill=(240, 240, 240), font=f20)
    for r, items in enumerate((ea, new)):
        for i, (lbl, im) in enumerate(items):
            x, y = 12 + i * cw, 50 + r * chh
            bg = Image.new("RGBA", im.size, (40, 40, 46, 255))
            S.paste(Image.alpha_composite(bg, im).convert("RGB").resize((256 * z, 256 * z), Image.NEAREST), (x, y + 22))
            d.text((x, y), lbl, fill=(220, 220, 220), font=f16)
    out = os.path.join(NHL24, "compare", f"{code.lower()}_fe_ea_vs_new.png")
    S.save(out)
    print(out, S.size)


def cmd_all(a):
    """Пакет на все клубы (кроме ARI): формы (только дом/выезд/третья) — сборка и упаковка; --group i/n — доля клубов
    для параллельного запуска. Общее, манифест и сводный лист — отдельно: common --pucks all, manifest --club all, summary."""
    codes = [c for _cl, _art, c in CLUBS if c not in EXCLUDE]
    if a.group:
        i, n = (int(x) for x in a.group.split("/"))
        codes = codes[i - 1::n]
    for code in codes:
        t0 = time.time()
        a.club = code
        if not a.skip_build:
            cmd_build(a)
        cmd_pack(a)
        print(f"== {code}: {time.time() - t0:.0f} с", flush=True)


def cmd_summary(a):
    """Сводный лист пакета на все клубы: дом / выезд / третья спереди и сзади."""
    from PIL import ImageDraw, ImageFont
    f20 = ImageFont.truetype("C:/Windows/Fonts/segoeuib.ttf", 20)
    f14 = ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", 14)
    dst, _ = kit_hybrid.legacy_with_shirt()
    W = 170
    rows = []
    for _cl, art, code in CLUBS:
        if code in EXCLUDE:
            continue
        cells = []
        for label in MAIN_KITS:
            od = os.path.join(OUTP, f"{code}_{label}")
            info = os.path.join(od, "info.json")
            if not os.path.exists(info):
                cells.append((label, None, None))
                continue
            rec = json.load(open(info, encoding="utf-8"))
            t = kit3d.load_tex(os.path.join(od, "jersey_cm.png"))
            ims = [kit3d.render(dst, t, v, W, frame=kit3d.FRAME, ss=2) for v in ("front", "back")]
            cells.append((label, ims, rec))
        rows.append((code, art, cells))
        print(code, flush=True)
    th = int(round(W * (kit3d.FRAME[3] - kit3d.FRAME[2]) / (kit3d.FRAME[1] - kit3d.FRAME[0])))
    cw = 2 * W + 6
    S = Image.new("RGB", (90 + 3 * (cw + 16), 70 + len(rows) * (th + 26)), (30, 30, 34))
    d = ImageDraw.Draw(S)
    d.text((12, 12), "NHL 24 → Legacy, все клубы (без ARI): дом / выезд / третья — спереди и сзади",
           fill=(240, 240, 240), font=f20)
    for j, lbl in enumerate(("дом", "выезд", "третья")):
        d.text((90 + j * (cw + 16), 44), lbl, fill=(220, 220, 220), font=f14)
    y = 66
    for code, art, cells in rows:
        d.text((12, y + th // 2 - 8), code, fill=(240, 240, 240), font=f20)
        for j, (label, ims, rec) in enumerate(cells):
            x = 90 + j * (cw + 16)
            if ims is None:
                d.text((x + 10, y + th // 2 - 8), "— нет в NHL 24 —" if label == "three" else "нет", fill=(150, 150, 150),
                       font=f14)
                continue
            S.paste(ims[0], (x, y))
            S.paste(ims[1], (x + W + 6, y))
            v = rec.get("variant")
            cap = (f"1_{art}_{v}" + (" новая" if rec.get("new") else "")) if v is not None else "номер ждёт реестр"
            d.text((x, y + th + 2), cap, fill=(190, 190, 190), font=f14)
        y += th + 26
    out = os.path.join(NHL24, "compare", "all_kits_summary.png")
    S.save(out)
    print(out, S.size)


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
        if c in ("build", "pack"):
            s.add_argument("--kits", default="", help="только эти формы (метки через запятую)")
        if c == "build":
            s.add_argument("--reuse", action="store_true", help="готовые рендеры не перерисовывать (номер сменился)")
    s = sub.add_parser("all")
    s.add_argument("--group", default="", help="i/n — каждый n-й клуб, начиная с i (параллельный запуск)")
    s.add_argument("--skip-build", action="store_true", help="только упаковка уже собранного")
    s.add_argument("--kits", default="")
    s.add_argument("--reuse", action="store_true", help="готовые рендеры не перерисовывать (номер сменился)")
    sub.add_parser("summary")
    s = sub.add_parser("sleeves")
    s.add_argument("--club", default="CHI", help="код клуба, коды через запятую или all")
    s.add_argument("--kits", default="", help="только эти формы (метки через запятую)")
    s = sub.add_parser("fe")
    s.add_argument("--club", default="CHI", help="код клуба, коды через запятую или all")
    s = sub.add_parser("fe-sheet")
    s.add_argument("--club", default="CHI")
    s.add_argument("--zoom", type=int, default=2, help="увеличение превью на листе")
    s = sub.add_parser("common")
    s.add_argument("--pucks", default="CHI", help="шайбы каких клубов (коды через запятую или all)")
    s.add_argument("--no-unfade", dest="unfade", action="store_false", help="рекламу на льду — как в NHL 24 (бледную)")
    sub.add_parser("sticks")
    for p in sub.choices.values():
        p.add_argument("--all-kits", action="store_true", help="и спецформы (RR22/RR23, 90-е) — не только дом/выезд/третья")
        p.add_argument("--everything", action="store_true",
                       help="пакет на все клубы: формы в out/all, пакет в out/pack-all (иначе — пилот: out/pilot, out/pack)")
        p.add_argument("--out-root", help="откуда брать собранные формы (вместо out/pilot или out/all)")
        p.add_argument("--pack-root", help="куда класть пакет (вместо out/pack или out/pack-all)")
    a = ap.parse_args()
    global ALL_KITS
    ALL_KITS = a.all_kits
    if a.everything or a.cmd in ("all", "summary"):
        set_roots(ALL_OUT, ALL_PACK)
    set_roots(a.out_root, a.pack_root)
    return {"build": cmd_build, "pack": cmd_pack, "common": cmd_common, "manifest": cmd_manifest,
            "sheets": cmd_sheets, "sticks": cmd_sticks, "all": cmd_all, "summary": cmd_summary, "fe": cmd_fe,
            "sleeves": cmd_sleeves,
            "fe-sheet": cmd_fe_sheet}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
