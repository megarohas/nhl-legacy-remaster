"""Формы клубов АХЛ: в чём клуб играет сейчас в NHL Legacy и форма NHL 27 — лист для решения «переносить или нет»
(docs/kitport.md §13). Только локально: рендеры из ассетов EA — не публиковать и не класть в git.

    cd tools
    P=../game/work/nhl24/venv/Scripts/python.exe
    $P kitpicker/ahl27.py sheet                    # все 32 клуба АХЛ: game/work/ahl27/ahl27_list.png (+ ahl27_list.json)
    $P kitpicker/ahl27.py sheet --clubs CV,HSK     # только эти
    $P kitpicker/ahl27.py build --clubs CV,HSK     # перенос: формы NHL 27 в те же строки Legacy (дом, выезд) →
                                                   # game/work/ahl27/kits/<КОД>_<форма> и раскладка cache: game/work/ahl27/cache

Перенос (build, 03.11.2026): у АХЛ в NHL 27 крой Reebok Edge (rbk), его развёртка совпадает с развёрткой Edge Legacy (проба
game/work/ahl27/uv_test_cv.png: текстура NHL 27 прямо на сетке Legacy), кроме шва сбоку под рукой (там по UV шла тёмная
черта) — поэтому свитер переносится по 3D (kit3d.transfer, сетка rbk NHL 24 → Edge Legacy, как подход A), вне сетки — по UV.
Рельеф и блеск — чистые Edge T=4 (как подход A, fb.pilot), шрифт — атлас NHL 27 ×½ с премультипликацией (fb.fonts), гетры —
3D-перенос (fb.pilot: сетка гетр NHL 24 → Legacy), шорты — родные Legacy цветами NHL 27 (edge_kit.tint_pant: основной и
второй цвет), превью — поза EA (pilot.fe_preview_ea), карта номеров и наклейка шлема — как у строки Legacy. Номера
строк (S_A_V) не меняются: файлы форм заменяются под теми же именами.

Откуда что:
- клубы и арт Legacy — таблица fb.ice.AHL27 (сопоставление мест Legacy и клубов NHL 27 по названию, агент «Модели»,
  03.11.2026); папка комплекта NHL 27 — FOLDER27 ниже (league/ahl/<папка>/rbk/home|away, крой Reebok Edge);
- формы Legacy — строки stockteamjerseys базы cache: пользователя (только чтение): дом и выезд по умолчанию
  (isdefault, locstring 0 / 1), файлы — fb.jersey_mesh.unpack_kit (cache: пользователя, иначе архив игры);
- рендер: Legacy — свитер на сетке Edge Legacy (стиль 1), NHL 27 — на сетке NHL 24 rbk (кэш каталога
  game/work/kits27-catalog/cache/mesh_rbk.npz, kitpicker/catalog27.py), перед и спина;
- пометка — VERDICT ниже: решение по истории клуба (переезд, смена названия и цветов), «спорно» — решает пользователь.
"""
import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TOOLS = os.path.join(ROOT, "tools")
sys.path.insert(0, TOOLS)
OUT = os.path.join(ROOT, "game", "work", "ahl27")
CACHE_DB = os.path.join(ROOT, "nhl-legacy-port", "userdata", "cache", "guest", "db")
TEX_CSV = os.path.join(ROOT, "game", "work", "nhl27", "catalog", "textures.csv")
MESH_RBK = os.path.join(ROOT, "game", "work", "kits27-catalog", "cache", "mesh_rbk.npz")
VIEW_W = 170
BG = (118, 122, 130)

# код Legacy → папка league/ahl NHL 27 (03.11.2026, по названию клуба из fb.ice.AHL27)
FOLDER27 = {
    "ABB": "abbotsford", "BAK": "bakersfield", "BLV": "belleville", "HMR": "hamilton_hammers", "CHA": "charlotte_checkers",
    "CHW": "chicagowolves", "GRA": "grand_rapid", "HAR": "hartford", "HER": "hershey", "IOW": "iowa", "CLE": "cleveland",
    "LVP": "lehigh_valley", "MAN": "manitoba", "MIL": "milwaukee", "ONT": "ontario", "SPR": "springfield",
    "PRO": "providence", "RCH": "rochester", "RFD": "rockford", "LAV": "laval", "COE": "colorado_eagles",
    "SD": "sandiego", "SJ": "barracuda", "TUC": "tucson", "CGW": "calgary_wranglers", "SYR": "syracuse",
    "TEX": "texas_stars", "TOA": "torontomarlies", "UTI": "utica", "WBS": "scranton", "CV": "coachella_valley",
    "HSK": "henderson_silverknights",
}
# Пометка (03.11.2026, агент «Формы»; правило пользователя: «реально новые команды обновить, более-менее старые оставить»).
# new — клуба не было в 2015/16 (или на месте другой клуб): форма Legacy чужая; same — тот же клуб, цвета и герб близки;
# ask — спорно (сменились цвета или герб, клуб тот же или преемник)
VERDICT = {
    "CV": ("new", "клуба не было (2022); сейчас — копия формы Springfield Falcons"),
    "HSK": ("new", "клуба не было (2020); сейчас — копия формы Providence Bruins"),
    "ABB": ("new", "клуб с 2021; на месте Albany Devils — форма Devils"),
    "HMR": ("new", "клуб с 2025; на месте Bridgeport — форма Sound Tigers"),
    "LAV": ("new", "клуб с 2017; на месте St. John's IceCaps"),
    "COE": ("new", "клуб с 2018; на месте San Antonio Rampage"),
    "SPR": ("new", "Thunderbirds с 2016; на месте Portland Pirates"),
    "CGW": ("ask", "Wranglers с 2022; на месте Stockton Heat — цвета те же (красный, чёрный, золото), герб другой"),
    "TUC": ("ask", "Roadrunners: у Legacy цвета Аризоны (кирпичный), у NHL 27 — зелёный и белый"),
    "BLV": ("ask", "Senators Бингемтона → Бельвиля (2017): цвета те же, герб другой"),
    "UTI": ("ask", "Comets с 2021 — фарм NJD: цвета сменились (синий/зелёный → красный/чёрный)"),
    "SJ": ("ask", "Barracuda: новый герб, бирюза → серый, чёрный"),
    "RFD": ("ask", "IceHogs: герб обновлён, цвета те же"),
    "CLE": ("ask", "Lake Erie → Cleveland Monsters: цвета сменились (чёрный, красный → синий, золото)"),
    "HAR": ("ask", "тот же клуб, новый герб Wolf Pack, цвета близки"),
    "IOW": ("ask", "тот же клуб, другой дизайн (кремовая IOWA), цвета те же"),
    "ONT": ("ask", "тот же клуб, цвета сменились (чёрный, белый → фиолетовый, золото — как LA)"),
}


# арт Legacy → арт формы EA, копией которой он стоит (tools/legacy_data/build-all.sh, этап art: teamart.py alias)
ALIAS_SRC = {102: 153, 103: 150}


def die(msg):
    sys.exit(msg)


def legacy_kits():
    """{код: (дом, выезд)} — теги S_A_V форм по умолчанию из базы cache: пользователя."""
    from tdb import Tdb
    from tdb_read import load_meta
    from fb.ice import AHL27
    db = Tdb(open(os.path.join(CACHE_DB, "nhlng.db"), "rb").read(), load_meta(os.path.join(CACHE_DB, "nhlng-meta.xml")))
    T = "stockteamjerseys"
    K = ("teamid", "style", "teamartid", "variant", "locstring", "isdefault")
    rows = [{f: db.get(T, f, r) for f in K} for r in db.live_rows(T)]
    out = {}
    for _c, art, code, _n, name in AHL27:
        rr = [r for r in rows if r["teamartid"] == art and r["isdefault"]]
        tag = {r["locstring"]: f"{r['style']}_{r['teamartid']}_{r['variant']}" for r in rr}
        out[code] = (tag.get(0), tag.get(1), name)
    return out


def tex27_rows(all_layers=False):
    import csv
    rows = {}
    with open(TEX_CSV, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            n = r["name"]
            if n.startswith("content/character/skater/league/ahl/") and (all_layers or (
                    n.endswith("_color") and "/jersey_rbk_" in n)):
                rows[n] = r
    return rows


def render_legacy(tag, M):
    import numpy as np
    from PIL import Image
    from fb import jersey_mesh as J, kit3d
    d = os.path.join(OUT, "legacy", tag)
    if not os.path.exists(os.path.join(d, "jersey_cm.png")):
        os.makedirs(d, exist_ok=True)
        J.unpack_kit(tag, d)
    tex = np.asarray(Image.open(os.path.join(d, "jersey_cm.png")).convert("RGBA")).astype(np.float64)
    return [kit3d.render(M, tex, v, VIEW_W, bg=BG, ss=2) for v in ("front", "back")]


def render_27(folder, kit, rows, M):
    import numpy as np
    from PIL import Image
    from fb import kit3d
    sys.path.insert(0, os.path.join(TOOLS, "kitpicker"))
    import catalog27 as C
    name = f"content/character/skater/league/ahl/{folder}/rbk/{kit}/jersey_rbk_{folder}_{kit}_color"
    r = rows.get(name)
    if r is None:
        return None
    jpg = os.path.join(OUT, "nhl27", f"{folder}_{kit}.png")
    if not os.path.exists(jpg):
        os.makedirs(os.path.dirname(jpg), exist_ok=True)
        C._decode(r).save(jpg)
    tex = np.asarray(Image.open(jpg).convert("RGBA")).astype(np.float64)
    return [kit3d.render(M, tex, v, VIEW_W, bg=BG, ss=2) for v in ("front", "back")]


def cmd_sheet(a):
    import numpy as np
    from PIL import Image, ImageDraw
    from fb import edge_kit as E
    sys.path.insert(0, os.path.join(TOOLS, "kitport"))
    from kitport.present import _font
    kits = legacy_kits()
    rows27 = tex27_rows()
    if not os.path.exists(MESH_RBK):
        die(f"нет {MESH_RBK}: сначала kitpicker/catalog27.py build (кэш сеток NHL 24)")
    m = np.load(MESH_RBK)
    Mr = {"pos": m["pos"], "uv": m["uv"], "tri": m["tri"], "nrm": m["nrm"]}
    ML = E.load(0, 1, 2)                                  # Edge Legacy, стиль 1 — сетка форм АХЛ EA
    want = a.clubs.split(",") if a.clubs else list(FOLDER27)
    font, small = _font(16), _font(13)
    col = {"new": (120, 220, 120), "same": (170, 170, 170), "ask": (255, 200, 90)}
    word = {"new": "НОВЫЙ — переносить", "same": "похож — не трогать", "ask": "спорно"}
    tiles, report = [], []
    for code in want:
        home, away, name = kits[code]
        folder = FOLDER27[code]
        lv = [render_legacy(t, ML) if t else None for t in (home, away)]
        nv = [render_27(folder, k, rows27, Mr) for k in ("home", "away")]
        v, why = VERDICT.get(code, ("same", "тот же клуб"))
        W = VIEW_W * 8 + 3 * 4 + 30
        vh = max([im.size[1] * VIEW_W // im.size[0] for p_ in lv + nv if p_ for im in p_] or [VIEW_W])
        H = vh + 36
        t = Image.new("RGB", (W, H + 30), (24, 24, 28))
        d = ImageDraw.Draw(t)
        d.text((6, 4), f"{code} {name}: {word[v]}", fill=col[v], font=font)
        d.text((6, 24), f"{why}.  Legacy: дом {home}, выезд {away}  |  NHL 27: ahl/{folder}/rbk", fill=(210, 210, 210), font=small)
        x = 0
        for lab, pair in (("Legacy сейчас: дом", lv[0]), ("Legacy сейчас: выезд", lv[1]), ("NHL 27: дом", nv[0]),
                          ("NHL 27: выезд", nv[1])):
            d.text((x + 4, 44), lab, fill=(235, 235, 235), font=small)
            if pair:
                for i, im in enumerate(pair):
                    im = im.resize((VIEW_W, int(im.size[1] * VIEW_W / im.size[0])))
                    t.paste(im, (x + i * VIEW_W, 62))
            x += VIEW_W * 2 + 4 + (26 if lab.endswith("выезд") and lab.startswith("Legacy") else 0)
        tiles.append(t)
        report.append({"code": code, "name": name, "verdict": v, "why": why, "legacy": [home, away],
                       "nhl27": f"ahl/{folder}/rbk"})
        print(code, word[v], flush=True)
    cols = 2
    Wt = tiles[0].width
    Ht = max(t.height for t in tiles)
    nrow = (len(tiles) + cols - 1) // cols
    sh = Image.new("RGB", (Wt * cols + 8 * (cols - 1), Ht * nrow + 6 * nrow), (12, 12, 14))
    for i, t in enumerate(tiles):
        sh.paste(t, ((i % cols) * (Wt + 8), (i // cols) * (Ht + 6)))
    os.makedirs(OUT, exist_ok=True)
    out = a.out or os.path.join(OUT, "ahl27_list.png")
    sh.save(out)
    json.dump(report, open(os.path.splitext(out)[0] + ".json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("лист →", out)


def upper_arm_color(d, reach=30):
    """Цвет верха руки у зоны номера левого рукава (2): самый частый в строках зоны от её края к плечу на reach
    текселей 1024² (у Edge плечо — к большему u). -> (R, G, B)."""
    import numpy as np
    from PIL import Image
    n = np.asarray(Image.open(os.path.join(d, "name_cm.png")).convert("RGBA"))
    m = (n[..., 0] > 128) & (n[..., 1] > 128) & (n[..., 2] == 2)
    ys, xs = np.nonzero(m)
    j = np.asarray(Image.open(os.path.join(d, "jersey_cm.png")).convert("RGB")).astype(int)
    k = j.shape[0] // n.shape[0]
    strip = j[ys.min() * k:(ys.max() + 1) * k, (xs.max() + 1) * k:(xs.max() + 1) * k + reach].reshape(-1, 3)
    q = strip // 12
    key = (q[:, 0] * 32 + q[:, 1]) * 32 + q[:, 2]
    ks, cnt = np.unique(key, return_counts=True)
    return tuple(int(v) for v in np.median(strip[key == ks[np.argmax(cnt)]], 0))


FIX3D_CM = None                    # см: тексель Legacy и та же точка развёртки rbk дальше в 3D — цвет по 3D (ближайшая точка rbk).
#                                    Выключено (03.11): сетки расходятся в 3D на 1,5–8 см почти везде (руки в другой позе), при
#                                    1,5 см перекрашено 60 % (нашивки плывут), при 3–8 см — ступеньки полос на границе; тёмная
#                                    черта по шву сбоку под рукой у CV и HSK остаётся — нужен полный 3D-перенос (подход A)
_GEO = {}


def _uv_points(M, S):
    import numpy as np
    from fb import kit3d
    key = (id(M), S)
    if key not in _GEO:
        tid, bar = kit3d.raster_uv(M, S)
        ys, xs = np.nonzero(tid >= 0)
        P = np.full((S, S, 3), np.nan)
        P[ys, xs] = (bar[ys, xs][:, :, None] * M["pos"][M["tri"][tid[ys, xs]]]).sum(1)
        _GEO[key] = P
    return _GEO[key]


def fix_by_3d(img, Mr, ML):
    """Развёртки rbk NHL 24 и Edge Legacy совпадают почти везде, но не на шве сбоку под рукой: там тексель Legacy берёт
    чужое место rbk (тёмная полоса по боку у CV и HSK, 03.11). Где точка Legacy и точка rbk с теми же UV дальше FIX3D_CM, —
    цвет ближайшей в 3D точки поверхности rbk. -> (картинка, перекрашено текселей)."""
    import numpy as np
    from scipy.spatial import cKDTree
    if FIX3D_CM is None:
        return img, 0
    S = img.shape[0]
    PL, PR = _uv_points(ML, S), _uv_points(Mr, S)
    okL = np.isfinite(PL[..., 0])
    far = okL & (~np.isfinite(PR[..., 0]) | (np.linalg.norm(np.nan_to_num(PL - PR, nan=1.0), axis=-1) > FIX3D_CM / 100))
    ry, rx = np.nonzero(np.isfinite(PR[..., 0]))
    tree = cKDTree(PR[ry, rx])
    fy, fx = np.nonzero(far)
    _, k = tree.query(PL[fy, fx])
    out = img.copy()
    out[fy, fx] = img[ry[k], rx[k]]
    return out, int(far.sum())


def pad_outside(img, M, grow=2):
    """Текстура NHL 27 (развёртка rbk) → тексели вне островов сетки-источника (+grow) — цветом ближайшего текселя острова.
    У Legacy на тех же местах бывает ткань (шов сбоку туловища): там шла тёмная полоса фона дампа (CV, HSK 03.11)."""
    import numpy as np
    from scipy import ndimage as ndi
    from fb import kit3d
    S = img.shape[0]
    tid, _ = kit3d.raster_uv(M, S)
    inside = ndi.binary_erosion(tid >= 0, iterations=grow)
    _, (iy, ix) = ndi.distance_transform_edt(~inside, return_indices=True)
    return img[iy, ix]


def cmd_decode(a):
    """Подпроцесс с FB_GAME=nhl27: текстуры дампа NHL 27 по именам → PNG (1024², как catalog27._decode)."""
    sys.path.insert(0, os.path.join(TOOLS, "kitpicker"))
    import catalog27 as C
    rows = tex27_rows(all_layers=True)
    os.makedirs(a.out, exist_ok=True)
    for n in a.names.split(","):
        r = rows.get(n)
        if r is None:
            print("нет", n)
            continue
        C._decode(r).save(os.path.join(a.out, n.rsplit("/", 1)[1] + ".png"))
        print("ok", n)


def decode27(names, out):
    import subprocess
    subprocess.run([sys.executable, os.path.abspath(__file__), "decode", "--names", ",".join(names), "--out", out],
                   check=True, cwd=TOOLS, env=dict(os.environ, FB_GAME="nhl27"))


def cmd_build(a):
    import shutil
    import subprocess
    import numpy as np
    from PIL import Image
    from fb import edge_kit as E, kit3d, pilot
    from fb.fonts import normal_map, resize_premult
    from fb.kit_batch import CLEAN, CLEAN_T
    kits = legacy_kits()
    cache = os.path.join(OUT, "cache")
    E.ZONE_ON_MAX = 0.06                                  # зона EA под другой рисунок рукава — дальше, чем у НХЛ (CV: 4–5 см)
    ML = E.load(0, 1, 2)                                  # Edge Legacy, стиль 1 — сетка форм АХЛ EA
    m_ = np.load(MESH_RBK)
    Mr = {"pos": m_["pos"], "uv": m_["uv"], "tri": m_["tri"], "nrm": m_["nrm"]}
    sN = kit3d.load_nhl24(pilot.SOCK_N24)
    sL = kit3d.load_legacy(pilot.SOCK_L)
    sLa = kit3d.aligned(sL, kit3d.bbox(sN), kit3d.bbox(sL))
    for code in a.clubs.split(","):
        folder = FOLDER27[code]
        for i, kit in enumerate(("home", "away")):
            tag = kits[code][i]
            d = os.path.join(OUT, "kits", f"{code}_{kit}")
            src = os.path.join(OUT, "src", f"{folder}_{kit}")
            base = f"content/character/skater/league/ahl/{folder}/rbk/{kit}/"
            names = [base + f"{l}_rbk_{folder}_{kit}_{s}" for l, s in
                     (("jersey", "color"), ("font", "color"), ("font", "normal"), ("pant", "color"), ("sock", "color"))]
            if not os.path.exists(os.path.join(src, names[0].rsplit("/", 1)[1] + ".png")):
                decode27(names, src)

            def sp(l, s):
                return os.path.join(src, f"{l}_rbk_{folder}_{kit}_{s}.png")
            leg = os.path.join(OUT, "legacy", tag)
            if not os.path.exists(os.path.join(leg, "kit.json")):
                from fb import jersey_mesh as J
                os.makedirs(leg, exist_ok=True)
                J.unpack_kit(tag, leg)
            if os.path.isdir(d):
                shutil.rmtree(d)                           # своя рабочая папка формы (собирается заново)
            shutil.copytree(leg, d)
            jc = np.asarray(Image.open(sp("jersey", "color")).convert("RGB").resize((1024, 1024), Image.LANCZOS))
            tr, msk, _, _ = kit3d.transfer(jc.astype(np.float64), Mr, ML, 1024, 2)   # 3D-перенос (как подход A): у шва
            jc = np.where(msk[..., None], np.clip(np.round(tr[..., :3]), 0, 255), pad_outside(jc, Mr)).astype(np.uint8)
            n_fix = int(msk.sum())                         # сбоку под рукой развёртки rbk и Edge расходятся — по UV там
            Image.fromarray(jc).save(os.path.join(d, "jersey_cm.png"))   # шла тёмная черта; вне сетки (рубашка) — по UV
            Image.open(os.path.join(CLEAN, f"{CLEAN_T}_3-12-21-30-39-48-57-66-75_sm.png")).resize(
                (1024, 1024), Image.LANCZOS).save(os.path.join(d, "jersey_sm.png"))
            shutil.copyfile(os.path.join(CLEAN, f"{CLEAN_T}_3-12-21-30-39-48-57-66-75_nm.png"),
                            os.path.join(d, "jersey_nm.png"))
            rep = [f"{code} {kit} → {tag} (NHL 27 ahl/{folder}/rbk/{kit}), 3D-перенос {n_fix} текселей"]
            if os.path.exists(sp("font", "color")):
                cm = resize_premult(np.asarray(Image.open(sp("font", "color")).convert("RGBA")), 512)
                Image.fromarray(cm).save(os.path.join(d, "font_cm.png"))
                if os.path.exists(sp("font", "normal")):
                    Image.fromarray(normal_map(sp("font", "normal"), 512)).save(os.path.join(d, "font_nm.png"))
                sm = np.zeros((512, 512, 4), np.uint8)
                sm[..., :3] = 21
                sm[..., 3] = np.where(cm[..., 3] > 128, 255, 0)
                Image.fromarray(sm).save(os.path.join(d, "font_sm.png"))
                rep.append("шрифт NHL 27")
            if os.path.exists(sp("sock", "color")):
                simg, _, _, _ = kit3d.transfer(kit3d.load_tex(sp("sock", "color")), sN, sLa, (1024, 512), 2)
                Image.fromarray(np.clip(simg, 0, 255).astype(np.uint8)).convert("RGB").save(os.path.join(d, "sock_cm.png"))
                rep.append("гетры 3D")
            if os.path.exists(sp("pant", "color")):
                rep.append("шорты Legacy цветами NHL 27: " + E.tint_pant(os.path.join(d, "pant_cm.png"), sp("pant", "color"),
                                                                          second=True))
            pilot.fe_preview_ea(os.path.join(d, "jersey_cm.png")).save(os.path.join(d, "fe.png"))
            col = upper_arm_color(d)                       # номер на рукаве — с полос на верх руки (CV: зона EA Falcons
            rep.append(f"номер на рукаве — на цвет {col}: " + str(E.zones_onto_color(   # легла на красную полосу NHL 27)
                os.path.join(d, "name_cm.png"), os.path.join(d, "jersey_cm.png"), (2, 3), col, need=0.95)))
            s_, a_, v_ = tag.split("_")
            if int(a_) in ALIAS_SRC:                       # арт клуба — копия формы EA (build-all.sh, этап art): в архивах
                kj = os.path.join(d, "kit.json")           # игры его нет, шаблон kitpaint — форма-источник копии
                meta = json.load(open(kj, encoding="utf-8"))
                meta["template"] = f"{s_}_{ALIAS_SRC[int(a_)]}_{v_}"
                json.dump(meta, open(kj, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
            rr = subprocess.run([sys.executable, os.path.join(TOOLS, "kitpaint.py"), "--game", "legacy", "pack", d, tag,
                                 cache], capture_output=True, text=True, encoding="utf-8", errors="replace")
            if rr.returncode:
                sys.exit(f"{code} {kit}: kitpaint pack — ошибка\n{rr.stdout[-600:]}\n{rr.stderr[-600:]}")
            print("; ".join(rep), flush=True)
    print("раскладка cache: →", cache)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("sheet", help="лист «Legacy сейчас | NHL 27» по клубам АХЛ с пометкой")
    p.add_argument("--clubs", default=None, help="коды через запятую (по умолчанию — все 32)")
    p.add_argument("--out", default=None)
    p = sub.add_parser("build", help="перенос форм NHL 27 в строки Legacy (дом, выезд) клубов --clubs")
    p.add_argument("--clubs", required=True, help="коды через запятую (CV,HSK)")
    p = sub.add_parser("decode", help="(служебная) текстуры NHL 27 → PNG, FB_GAME=nhl27")
    p.add_argument("--names", required=True)
    p.add_argument("--out", required=True)
    a = ap.parse_args()
    os.environ["FB_GAME"] = "nhl24" if a.cmd == "build" else "nhl27"   # fb.cas берёт корень дампа при импорте
    {"sheet": cmd_sheet, "build": cmd_build, "decode": cmd_decode}[a.cmd](a)


if __name__ == "__main__":
    main()
