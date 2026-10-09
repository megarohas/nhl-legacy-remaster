"""Опись карт рельефа (nm) и блеска (sm) свитеров NHL Legacy кроя Reebok (стиль 1) и чистые варианты кроя.

Клубные комплекты: rendering/jersey/texlib_1_<арт>_<вариант>.rx2 (все распакованные архивы game/other/legacy/big/*):
растры jersey_1_A_V_0_nm (DXN 1024²) и jersey_1_A_V_sm (DXT1 1024²). Конструктор: rendering/czlogo/logoct_L_T_nm/sm
(своя карта на каждую пару «логотип × крой T»); чистые карты кроя T — медиана по логотипам (czwork/clean).

Карта рельефа = «запечённые» складки ткани + швы/канты/края нашивных полос + вдавленные логотипы.
  1) Основа складок: низкие частоты (гаусс 3 пикс. на 256²) вне логотипов, RMS разницы X/Y < FAM_THR — одна основа.
  2) Швы внутри основы: доля пикселей, где две карты расходятся больше TOL, от площади их собственных отличий от
     медианы основы (не меньше 300 пикс.); полная связь, порог SEAM_THR — одна раскладка швов.
Логотипы не считаются: места герба, плечевых нашивок, ворота и «рубашки» (mask256) исключены.
Чистые варианты: основа A (медиана карт разных клубов — логотипы и полосы уходят) и «A + швы клуба» — остаток
«клуб − основа» вне мест логотипов поверх чистой основы.

  python -m fb.relief scan          # декод всех карт (256²) -> relief/_nm256.npz, relief/_files.json
  python -m fb.relief inventory     # -> catalog/relief_inventory.json, relief/clean_A_{nm,sm}.png
  python -m fb.relief sheet         # -> compare/relief_all.png (по представителю на каждую раскладку швов)
"""
import argparse
import glob
import hashlib
import json
import os
import re
import sys

import numpy as np
from PIL import Image

from .cas import REPO

TOOLS = os.path.join(REPO, "tools")
BIG = os.path.join(REPO, "game", "other", "legacy", "big")
NHL24 = os.path.join(REPO, "game", "work", "nhl24")
OUT = os.path.join(NHL24, "relief")
CLEAN = os.path.join(REPO, "game", "work", "uniforms", "czwork", "clean")
CZ = os.path.join(BIG, "nocacherender", "rendering")
INV = os.path.join(NHL24, "catalog", "relief_inventory.json")
JERSEY_MESH = "rendering/jersey/jersey_1_0_0_0_0_2.rx2"
TS = (0, 1, 2, 4, 5)
FAM_THR = 3.0
SEAM_THR = 0.3
TOL = 10


def _lib(name):
    if TOOLS not in sys.path:
        sys.path.insert(0, TOOLS)
    return __import__(name)


def raster(rw, suffix):
    for t in rw.textures:
        if t.name.startswith("jersey_") and t.name.endswith(suffix + ".Raster"):
            return t
    return None


def decode(rw, t, size):
    kp = _lib("kitpaint")  # декодер с DXN (у teamart.decode DXN неверный)
    for lv, L in enumerate(t.layout.levels):
        if L[0] == size:
            w, h, rgba = kp.tex_decode(rw, t, lv)
            return np.frombuffer(bytes(rgba), np.uint8).reshape(h, w, 4)
    return None


def club_files():
    """{texlib_1_A_V.rx2: [(архив, путь), …]}"""
    seen = {}
    for p in sorted(glob.glob(os.path.join(BIG, "*", "rendering", "jersey", "texlib_1_*.rx2"))):
        seen.setdefault(os.path.basename(p), []).append((os.path.relpath(p, BIG).split(os.sep)[0], p))
    return seen


def kit_path(kit):
    return club_files()[f"texlib_{kit}.rx2"][0][1]


def zones(size=256):
    """Места логотипов (True): герб, плечевые нашивки, ворот, «рубашка» — в координатах развёртки стиля 1."""
    k = size / 256
    z = np.zeros((size, size), bool)
    z[int(135 * k):int(250 * k), int(70 * k):int(186 * k)] = True
    yy, xx = np.mgrid[0:size, 0:size]
    for cx, cy in ((94, 123), (162, 123)):
        z[(xx - cx * k) ** 2 + (yy - cy * k) ** 2 < (24 * k) ** 2] = True
    z[int(95 * k):int(165 * k), int(108 * k):int(148 * k)] = True
    z[int(190 * k):, :int(64 * k)] = True
    return z


def mask256():
    return ~zones(256)


def island256():
    p = os.path.join(OUT, "_island256.npy")
    if os.path.exists(p):
        return np.load(p)
    from . import kit3d
    tid, _ = kit3d.raster_uv(kit3d.load_legacy(JERSEY_MESH), 256)
    np.save(p, tid >= 0)
    return tid >= 0


def work_mask():
    from scipy import ndimage as ndi
    return mask256() & ndi.binary_erosion(island256(), iterations=2)


def with_z(xy):
    """X/Y (0..255) -> RGBA с восстановленной Z, как у декодера DXN."""
    x = xy[..., 0].astype(np.float64) / 127.5 - 1
    y = xy[..., 1].astype(np.float64) / 127.5 - 1
    z = np.sqrt(np.clip(1 - x * x - y * y, 0, 1))
    out = np.zeros(xy.shape[:2] + (4,), np.uint8)
    out[..., 0] = np.clip(np.round(xy[..., 0]), 0, 255)
    out[..., 1] = np.clip(np.round(xy[..., 1]), 0, 255)
    out[..., 2] = np.clip(np.round((z + 1) * 127.5), 0, 255)
    out[..., 3] = 255
    return out


def load_kit(kit, size):
    """(nm X/Y float (size², 2), sm серый float (size²) или None)."""
    ta = _lib("teamart")
    rw = ta.Rw4.load(kit_path(kit))
    nm = decode(rw, raster(rw, "_nm"), size)[..., :2].astype(np.float32)
    ts = raster(rw, "_sm")
    sm = decode(rw, ts, size)[..., :3].mean(-1).astype(np.float32) if ts is not None else None
    return nm, sm


# ---------------------------------------------------------------- scan

def cmd_scan(a):
    ta = _lib("teamart")
    files = club_files()
    kits, nms, sms, recs = [], [], [], []
    for i, (name, where) in enumerate(sorted(files.items())):
        mm = re.match(r"texlib_1_(\d+)_(\d+)\.rx2$", name)
        if not mm:
            continue
        arch, p = where[0]
        rw = ta.Rw4.load(p)
        rec = {"kit": f"1_{mm.group(1)}_{mm.group(2)}", "art": int(mm.group(1)), "variant": int(mm.group(2)),
               "archives": [w[0] for w in where], "rasters": {}}
        for t in rw.textures:
            if t.name.startswith("jersey_"):
                L = t.layout
                rec["rasters"][t.name[:-7]] = {"fmt": str(L.fmt), "size": list(L.levels[0][:2]), "mips": len(L.levels)}
        tn, tsm = raster(rw, "_nm"), raster(rw, "_sm")
        rec["nm"] = tn is not None
        rec["sm"] = tsm is not None
        if tn is not None:
            nm = decode(rw, tn, 256)
            sm = decode(rw, tsm, 256) if tsm is not None else None
            kits.append(rec["kit"])
            nms.append(nm[..., :2])
            sms.append(sm[..., 0] if sm is not None else np.zeros((256, 256), np.uint8))
        recs.append(rec)
        if i % 50 == 0:
            print(i, name, flush=True)
    os.makedirs(OUT, exist_ok=True)
    np.savez_compressed(os.path.join(OUT, "_nm256.npz"), kits=np.array(kits), nm=np.stack(nms), sm=np.stack(sms))
    with open(os.path.join(OUT, "_files.json"), "w", encoding="utf-8") as f:
        json.dump(recs, f, ensure_ascii=False, indent=0)
    print(f"файлов texlib_1_*: {len(recs)}, с nm: {len(kits)}")


# ---------------------------------------------------------------- inventory

def load_scan():
    z = np.load(os.path.join(OUT, "_nm256.npz"))
    with open(os.path.join(OUT, "_files.json"), encoding="utf-8") as f:
        recs = json.load(f)
    return [str(k) for k in z["kits"]], z["nm"].astype(np.float32), z["sm"].astype(np.float32), recs


def constructor(size=256):
    refs = {}
    for t in TS:
        im = Image.open(os.path.join(CLEAN, f"{t}_3-12-21-30-39-48-57-66-75_nm.png")).convert("RGBA")
        if im.size != (size, size):
            im = im.resize((size, size), Image.BOX)
        refs[t] = np.asarray(im).astype(np.float32)[..., :2]
    return refs


def constructor_sm(t, size):
    im = Image.open(os.path.join(CLEAN, f"{t}_3-12-21-30-39-48-57-66-75_sm.png")).convert("RGB")
    if im.size != (size, size):
        im = im.resize((size, size), Image.LANCZOS)
    return np.asarray(im).astype(np.float32).mean(-1)


def rms_matrix(V, npix):
    g = V @ V.T
    n2 = np.diag(g)
    D = np.sqrt(np.maximum(n2[:, None] + n2[None, :] - 2 * g, 0) / npix)
    np.fill_diagonal(D, 0)
    return D


def bake_groups(X, M):
    from scipy import ndimage as ndi
    from scipy.cluster import hierarchy as hc
    from scipy.spatial.distance import squareform
    L = np.stack([ndi.gaussian_filter(x - 128, (3, 3, 0))[M].reshape(-1) for x in X]).astype(np.float64)
    D = rms_matrix(L, M.sum() * 2)
    return hc.fcluster(hc.linkage(squareform(D, checks=False), "average"), FAM_THR, "distance"), D


def seam_matrix(X, M, names):
    """Попарная доля расхождений швов внутри одной основы (кеш по составу)."""
    key = hashlib.sha1(("|".join(names) + f"|{TOL}").encode()).hexdigest()[:12]
    p = os.path.join(OUT, f"_seam_{key}.npy")
    if os.path.exists(p):
        return np.load(p)
    base = np.median(X, 0) if len(X) >= 3 else X[0]
    XA = X[:, M].astype(np.int16)
    R = np.abs(XA - base[M].astype(np.int16)).max(-1) > TOL
    n = len(X)
    D = np.zeros((n, n), np.float32)
    for i in range(n - 1):
        dif = np.abs(XA[i + 1:] - XA[i]).max(-1) > TOL
        sup = R[i + 1:] | R[i]
        D[i, i + 1:] = dif.sum(1) / np.maximum(sup.sum(1), 300)
    D = D + D.T
    np.save(p, D)
    return D


def art_teams():
    p = os.path.join(OUT, "_art_teams.json")
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            return {int(k): v for k, v in json.load(f).items()}
    tdb = _lib("tdb")
    from tdb_read import load_meta
    db = tdb.Tdb(open(os.path.join(BIG, "cacheboot", "db", "nhlng.db"), "rb").read(),
                 load_meta(os.path.join(REPO, "legacy-port", "big", "cacheboot", "db", "nhlng-meta.xml")))
    a2 = {}
    for r in db.live_rows("exhibitionteams"):
        a2.setdefault(db.get("exhibitionteams", "artid", r), []).append(
            (db.get_string("exhibitionteams", "abbrname", r), db.get_string("exhibitionteams", "fullname", r)))
    with open(p, "w", encoding="utf-8") as f:
        json.dump({str(k): v for k, v in a2.items()}, f, ensure_ascii=False)
    return a2


def team_of(kit, teams):
    if kit.startswith("T="):
        return "конструктор"
    v = teams.get(int(kit.split("_")[1]))
    return v[0][0] if v else "арт " + kit.split("_")[1]


def cmd_inventory(a):
    from scipy.cluster import hierarchy as hc
    from scipy.spatial.distance import squareform
    kits, nm, sm, recs = load_scan()
    teams = art_teams()
    M = work_mask()
    refs = constructor(256)
    names = kits + [f"T={t}" for t in TS]
    X = np.concatenate([nm, np.stack([refs[t] for t in TS])], 0)
    lab, _ = bake_groups(X, M)
    groups = {}
    for i, l in enumerate(lab):
        groups.setdefault(l, []).append(i)
    glist = sorted(groups.values(), key=lambda g: -len(g))
    fams, nb = [], 0
    for g in glist:
        gn = [names[i] for i in g]
        if any(n.startswith("T=") for n in gn):
            fid = "K"
        elif not fams or all(f["id"] != "A" for f in fams):
            fid = "A"
        else:
            nb += 1
            fid = f"B{nb}"
        D = seam_matrix(X[g], M, gn) if len(g) > 1 else np.zeros((1, 1), np.float32)
        lab2 = hc.fcluster(hc.linkage(squareform(D, checks=False), "complete"), SEAM_THR, "distance") \
            if len(g) > 1 else np.array([1])
        lay = {}
        for j, l in enumerate(lab2):
            lay.setdefault(l, []).append(j)
        layouts = []
        for k, idx in enumerate(sorted(lay.values(), key=lambda c: (-len(c), gn[c[0]]))):
            sub = D[np.ix_(idx, idx)]
            rep = gn[idx[int(np.argmin(sub.sum(1)))]]
            if fid == "K":   # у конструктора представитель — сама чистая карта T
                rep = next((gn[j] for j in idx if gn[j].startswith("T=")), rep)
            mem = sorted(gn[j] for j in idx)
            layouts.append({"id": f"{fid}-{k}", "rep": rep, "team": team_of(rep, teams), "count": len(idx),
                            "arts": len({m.split("_")[1] for m in mem if not m.startswith("T=")}), "kits": mem})
        arts = sorted({int(n.split("_")[1]) for n in gn if not n.startswith("T=")})
        fams.append({"id": fid, "count": len(g), "club_maps": sum(1 for n in gn if not n.startswith("T=")),
                     "arts": len(arts), "teams": sorted({teams.get(x, [("?",)])[0][0] for x in arts}),
                     "layouts": layouts})
        print(f"основа {fid}: карт {len(g)}, артов {len(arts)}, раскладок швов {len(layouts)}", flush=True)
    # чистая основа A: медиана карт разных клубов с наименьшими отличиями от основы (1024²)
    fa = next(f for f in fams if f["id"] == "A")
    ia = [kits.index(k) for lay in fa["layouts"] for k in lay["kits"]]
    base = np.median(nm[ia], 0)
    own = {kits[i]: float((np.abs(nm[i] - base).max(-1)[M] > TOL).sum()) for i in ia}
    pick, seen = [], set()
    for k in sorted(own, key=own.get):
        art = k.split("_")[1]
        if art not in seen:
            seen.add(art)
            pick.append(k)
        if len(pick) == a.n_clean:
            break
    nms, sms = [], []
    for k in pick:
        x, s = load_kit(k, 1024)
        nms.append(x)
        if s is not None:
            sms.append(s)
    Image.fromarray(with_z(np.median(np.stack(nms), 0))).save(os.path.join(OUT, "clean_A_nm.png"))
    Image.fromarray(np.clip(np.median(np.stack(sms), 0), 0, 255).astype(np.uint8)).save(os.path.join(OUT, "clean_A_sm.png"))
    nm_r = sum(1 for r in recs for n in r["rasters"] if n.endswith("_nm"))
    sm_r = sum(1 for r in recs for n in r["rasters"] if n.endswith("_sm"))
    cz = os.listdir(os.path.join(CZ, "czlogo"))
    inv = {
        "club": {"texlib_1": len(recs), "arts": len({r["art"] for r in recs}), "nm": nm_r, "sm": sm_r,
                 "archives": sorted({x for r in recs for x in r["archives"]}),
                 "second_nm": [r["kit"] for r in recs if sum(1 for n in r["rasters"] if n.endswith("_nm")) > 1],
                 "nm_only": [r["kit"] for r in recs if not r["sm"]]},
        "constructor": {"logoct_nm": sum(1 for n in cz if n.endswith("_nm.rx2")),
                        "logoct_sm": sum(1 for n in cz if n.endswith("_sm.rx2")),
                        "T": sorted({int(n.split("_")[2]) for n in cz if n.endswith("_nm.rx2")}),
                        "jerseyct": sorted(os.listdir(os.path.join(CZ, "czjersey")))},
        "params": {"FAM_THR": FAM_THR, "SEAM_THR": SEAM_THR, "TOL": TOL},
        "clean_A_from": pick, "families": fams}
    with open(INV, "w", encoding="utf-8") as f:
        json.dump(inv, f, ensure_ascii=False, indent=1)
    nl = sum(len(f["layouts"]) for f in fams)
    print(f"клубных nm {nm_r}, sm {sm_r}; основ складок {len(fams)}; раскладок швов всего {nl} "
          f"(в основе A: {len(fa['layouts'])}); чистая основа A — из {len(pick)} клубов")


# ---------------------------------------------------------------- sheet

def clean_from_club(kit, size, base_nm, base_sm):
    """Чистая основа A + швы клуба: остаток «клуб − основа» вне мест логотипов (края мягкие)."""
    from scipy import ndimage as ndi
    x, s = load_kit(kit, size)
    w = 1 - ndi.gaussian_filter(zones(size).astype(np.float32), size / 256 * 1.5)
    nmx = base_nm + (x - base_nm) * w[..., None]
    smx = base_sm + ((s - base_sm) * w if s is not None else 0)
    return nmx, smx


def rgba(nm_xy):
    return with_z(nm_xy).astype(np.float64)


def gray3(sm):
    return np.repeat(np.clip(sm, 0, 255)[..., None], 4, -1).astype(np.float64)


VIEWS = [("спереди", "front", None), ("сбоку", "left", (-0.55, 0.55, 0.86, 1.80)),
         ("плечо крупно", "front", (-0.50, -0.06, 1.38, 1.74)), ("бок крупно", "left", (-0.24, 0.24, 1.06, 1.46))]
LIGHT = (-1.0, 0.22, 0.30)


def cmd_sheet(a):
    from PIL import ImageDraw, ImageFont
    from . import kit3d, kit_hybrid
    with open(INV, encoding="utf-8") as f:
        inv = json.load(f)
    f19 = ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", 19)
    fb = ImageFont.truetype("C:/Windows/Fonts/segoeuib.ttf", 21)
    f13 = ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", 13)
    fb30 = ImageFont.truetype("C:/Windows/Fonts/segoeuib.ttf", 30)
    mesh, _ = kit_hybrid.legacy_with_shirt()
    tex = kit3d.load_tex(os.path.join(NHL24, "out", "kits", "SEA_home", "jersey_cm.png"))
    frames = [fr or kit3d.FRAME for _, _, fr in VIEWS]

    def views(nmap, smap, w):
        return [kit3d.render_lit(mesh, tex, v, w, frame=fr, nmap=nmap, smap=smap, light=LIGHT, ss=2)
                for (_, v, _), fr in zip(VIEWS, frames)]

    bnm = np.asarray(Image.open(os.path.join(OUT, "clean_A_nm.png")).convert("RGBA")).astype(np.float32)[..., :2]
    bsm = np.asarray(Image.open(os.path.join(OUT, "clean_A_sm.png")).convert("L")).astype(np.float32)
    b512 = np.asarray(Image.fromarray(with_z(bnm)).resize((512, 512), Image.BOX)).astype(np.float32)[..., :2]
    s512 = np.asarray(Image.fromarray(bsm.astype(np.uint8)).resize((512, 512), Image.BOX)).astype(np.float32)
    fams = {f["id"]: f for f in inv["families"]}
    fa = fams["A"]
    # ---- часть 1: чистые варианты крупно (как relief_variants)
    big = [("A: основа клубов", f"чисто; так {fa['club_maps']} из {inv['club']['texlib_1']} клубных карт",
            rgba(bnm), gray3(bsm))]
    c1024, c512 = constructor(1024), constructor(512)
    for t in TS:
        big.append((f"T={t}", "конструктор, чисто", rgba(c1024[t]), gray3(constructor_sm(t, 1024))))
    for kit in a.examples.split(","):
        lay = next(l for l in fa["layouts"] if kit in l["kits"])
        nmx, smx = clean_from_club(kit, 1024, bnm, bsm)
        team = next((v[0][0] for k, v in art_teams().items() if k == int(kit.split("_")[1])), "?")
        big.append((f"A + швы {team}", f"{kit} ({lay['id']}), логотипы сняты", rgba(nmx), gray3(smx)))
    W1 = 300
    col1 = [views(n, s, W1) for _, _, n, s in big]
    hs1 = [im.size[1] for im in col1[0]]
    # ---- часть 2: все раскладки швов (по представителю), мелко
    items = []
    for fid in ["A", "K"] + sorted((k for k in fams if k.startswith("B")), key=lambda k: int(k[1:])):
        for lay in fams[fid]["layouts"]:
            rep = lay["rep"]
            if rep.startswith("T="):
                t = int(rep[2:])
                n = rgba(c512[t])
                s = gray3(constructor_sm(t, 512))
                note = "чисто"
            elif fid == "A":
                nmx, smx = clean_from_club(rep, 512, b512, s512)
                n, s = rgba(nmx), gray3(smx)
                note = "лого снято"
            else:
                x, sx = load_kit(rep, 512)
                n, s = rgba(x), gray3(sx if sx is not None else np.full((512, 512), 24, np.float32))
                note = "как есть"
            items.append((f"{lay['id']} ×{lay['count']}  {lay['team']} {rep}", note, n, s))
        print(fid, "раскладок", len(fams[fid]["layouts"]), flush=True)
    W2 = 150
    tex = np.full((8, 8, 4), 190.0)   # каталог — на светло-сером свитере: швы видно лучше, чем на тёмно-синем
    tex[..., 3] = 255
    blocks = [views(n, s, W2) for _, _, n, s in items]
    bh = max(im.size[1] for im in blocks[0]) + 22
    bw = 4 * W2 + 3 * 4
    per = 6
    rows2 = (len(items) + per - 1) // per
    width = max(130 + len(big) * (W1 + 10), per * (bw + 18) + 20)
    h1 = 72 + sum(h + 16 for h in hs1)
    head = 150
    H = head + h1 + 60 + rows2 * bh + 40
    S = Image.new("RGB", (width, H), (28, 28, 32))
    d = ImageDraw.Draw(S)
    c = inv["club"]
    nl = sum(len(f["layouts"]) for f in inv["families"])
    d.text((16, 10), "Рельеф свитеров NHL Legacy, крой Reebok (стиль 1): все карты", fill=(245, 245, 245), font=fb30)
    d.text((16, 52), f"Клубных карт nm {c['nm']}, sm {c['sm']} ({c['texlib_1']} texlib_1_*, {c['arts']} артов) + конструктор "
           f"{inv['constructor']['logoct_nm']} nm / {inv['constructor']['logoct_sm']} sm (86 логотипов × T 0,1,2,4,5; T=3 нет "
           f"ни в файлах, ни в таблице игры).", fill=(220, 220, 220), font=f19)
    d.text((16, 80), f"Основ складок: {len(inv['families'])} (A — {fa['club_maps']} клубных карт; K — конструктор T; "
           f"B1…B{len(inv['families']) - 2} — старые/особые). Раскладок швов (канты, полосы, панели; логотипы не "
           f"в счёт): {nl}, из них в A — {len(fa['layouts'])}.", fill=(220, 220, 220), font=f19)
    d.text((16, 108), "Свет и виды — как relief_variants.png. Вверху — чистые варианты крупно (цвет SEA home); ниже — по "
           "представителю каждой раскладки на светло-сером (A — логотипы сняты, K/B — как есть).", fill=(200, 200, 200),
           font=f19)
    y0 = head
    for j, (l1, l2, _, _) in enumerate(big):
        x = 130 + j * (W1 + 10)
        d.text((x, y0 + 4), l1, fill=(240, 240, 240), font=fb)
        d.text((x, y0 + 32), l2, fill=(205, 205, 205), font=f13)
    y = y0 + 72
    for r, (vn, _, _) in enumerate(VIEWS):
        d.text((8, y + hs1[r] // 2 - 10), vn, fill=(235, 235, 235), font=f19)
        for j, col in enumerate(col1):
            S.paste(col[r], (130 + j * (W1 + 10), y))
        y += hs1[r] + 16
    y += 20
    d.text((16, y), "Все раскладки швов: код ×число карт  клуб представитель — виды: спереди | сбоку | плечо | бок",
           fill=(240, 240, 240), font=fb)
    y += 40
    for i, ((lbl, note, _, _), bl) in enumerate(zip(items, blocks)):
        X = 20 + (i % per) * (bw + 18)
        Y = y + (i // per) * bh
        d.text((X, Y + 2), f"{lbl} · {note}", fill=(225, 225, 225), font=f13)
        for k, im in enumerate(bl):
            S.paste(im, (X + k * (W2 + 4), Y + 20))
    out = os.path.join(NHL24, "compare", "relief_all.png")
    S.save(out, optimize=True)
    print(out, S.size, os.path.getsize(out) // 1024, "КБ")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("scan")
    i = sub.add_parser("inventory")
    i.add_argument("--n-clean", type=int, default=25)
    s = sub.add_parser("sheet")
    s.add_argument("--examples", default="1_6_0,1_0_0,1_23_0,1_161_1")
    a = ap.parse_args()
    return {"scan": cmd_scan, "inventory": cmd_inventory, "sheet": cmd_sheet}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
