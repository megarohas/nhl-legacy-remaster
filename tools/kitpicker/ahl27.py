"""Формы клубов АХЛ: в чём клуб играет сейчас в NHL Legacy и форма NHL 27 — лист для решения «переносить или нет»
(docs/kitport.md §13). Только локально: рендеры из ассетов EA — не публиковать и не класть в git.

    cd tools
    P=../game/work/nhl24/venv/Scripts/python.exe
    $P kitpicker/ahl27.py sheet                    # все 32 клуба АХЛ: game/work/ahl27/ahl27_list.png (+ ahl27_list.json)
    $P kitpicker/ahl27.py sheet --clubs CV,HSK     # только эти
    $P kitpicker/ahl27.py build --clubs CV,HSK     # перенос: формы NHL 27 в те же строки Legacy (дом, выезд) →
                                                   # game/work/ahl27/kits/<КОД>_<форма> и раскладка cache: game/work/ahl27/cache
    $P kitpicker/ahl27.py crest --clubs HMR,LAV    # только герб: форма Legacy, на груди и плечах — гербы NHL 27, шлем,
                                                   # превью (та же раскладка cache:); --dry — только картинки «было | стало»
    $P kitpicker/ahl27.py out ../game/work/legacy-data/out   # (этап сборки) раскладка — в дерево накладки

Установка — python -m kitport put --from ../game/work/ahl27/cache --tag ahl-…; в полной сборке накладки формы АХЛ кладёт
fb.edge_kit pack (пакет pack-edge, тип other) — полная переустановка их не откатывает.

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
import legacy_paths as LP  # noqa: E402 (cache: в обеих раскладках, docs/legacy-port.md «Папка content»)
CACHE_DB = os.path.dirname(LP.legacy_file("db/nhlng.db"))
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


LETTERING_FROM = "1_14_4"                  # форма EA, с карты номеров которой места фамилии и номера на спине (MIN дом)
SLEEVE_SMALL = 0.8                         # номер на рукаве мельче, если на цвете верха руки ему нет места (ABB, 03.11)
FULL_EQUIP = ["ABB", "SPR", "COE", "CLE", "ONT", "CV", "HSK"]   # полный перенос: шлем и краги — NHL 27 (03.11)
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


SLEEVE_UV_FEATHER = 3.0                   # текселей: переход «рукав по развёртке» → «туловище 3D» у шва проймы


def sleeve_soft(S):
    """Доля «рукав» у текселей развёртки Edge S²: за швом проймы (edge_kit.armhole_u по строкам рукава SLV_V), сглажено.
    -> (S, S) 0…1."""
    import numpy as np
    from scipy import ndimage as ndi
    from fb import edge_kit as E
    vv = (np.arange(S) + 0.5) / S
    au = E.armhole_u(np.clip(vv, E.ARMHOLE_UV[0][0], E.ARMHOLE_UV[-1][0]))
    rows = (vv >= E.SLV_V[0] - 0.02) & (vv <= E.SLV_V[1] + 0.02)
    m = ((vv[None, :] < au[:, None]) | (vv[None, :] > 1 - au[:, None])) & rows[:, None]
    return np.clip(ndi.gaussian_filter(m.astype(float), SLEEVE_UV_FEATHER), 0, 1)


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


# ---------------------------------------------------------------- гербы, наклейка шлема (03.11.2026)
# Пользователь, 03.11: «только логотип — форма Legacy остаётся (цвета, полосы, номера), на груди старый герб закрасить цветом
# свитера (с тканью и тенями, без пятна) и поставить герб клуба из NHL 27 того же размера и места; то же на превью; проверить
# шлем и плечевые нашивки — если там старый логотип, тоже заменить». Развёртки Edge Legacy и rbk NHL 27 у груди и плеч
# совпадают (проба uv_test_cv.png), поэтому места — прямоугольники развёртки 1024², одни на обе.
CREST_BOX = (0.30, 0.60, 0.70, 0.92)       # u0, v0, u1, v1: герб на груди (у EA АХЛ — u 0,40–0,60, v 0,63–0,85)
SHOULDER_BOXES = ((0.25, 0.37, 0.45, 0.59), (0.55, 0.37, 0.75, 0.59))   # нашивки на плечах (EA: u 0,34 и 0,64, v 0,47;
#                                    у NHL 27 LAV надпись LAVAL — до u 0,58: при рамке 0,58–0,72 резалась до «AVAL»)
CREST_BOX_WIDE = (0.25, 0.56, 0.75, 0.95)  # герб крупнее рамки CREST_BOX (BLV дом) — вторая попытка
PATCH_DIFF = 18                            # max |ΔRGB| до цвета ткани — часть нашивки (при 40 у Sound Tigers оставалась серая тень герба)
PATCH_MIN_PX = 80                          # меньше текселей — не нашивка (пятно, надпись CCM)
CREST_FIT_MAX = 1.15                       # новый герб: площадь как у прежнего, но не шире / не выше его рамки в столько раз
A27_LO, A27_HI = 10.0, 40.0
CREST_CONTRAST_MIN = 80                    # медиана max|ΔRGB| герба NHL 27 к ткани Legacy — меньше: взять другую форму NHL 27
DECAL_NEAR = 20                            # текселей: части нашивки NHL 27 не дальше от главной — её же                # NHL 27: |color − base_color| → альфа нашивки (сглаженный край — между)


def _body_color(img, box):
    """Цвет ткани вокруг рамки box (кольцо 3–6 % развёртки за ней, самый частый). -> np.array(3)."""
    import numpy as np
    S = img.shape[0]
    u0, v0, u1, v1 = (int(round(x * S)) for x in box)
    m = np.zeros(img.shape[:2], bool)
    g = int(0.05 * S)
    m[max(0, v0 - g):v1 + g, max(0, u0 - g):u1 + g] = True
    m[v0:v1, u0:u1] = False
    px = img[m].reshape(-1, 3).astype(int)
    q = px // 10
    key = (q[:, 0] * 32 + q[:, 1]) * 32 + q[:, 2]
    ks, cnt = np.unique(key, return_counts=True)
    return np.median(px[key == ks[np.argmax(cnt)]], 0)


def _row_bg(img, box):
    """Фон по строкам рамки: самый частый цвет строки внутри рамки (герб уже рамки; полосы поперёк груди — LAV выезд,
    синяя полоса через герб — фон, не нашивка). Тексели за рамкой не годятся: у BLV там красные «крылья» плеч. -> (H, 3)."""
    import numpy as np
    S = img.shape[0]
    u0, v0, u1, v1 = (int(round(x * S)) for x in box)
    out = np.zeros((S, 3))
    for r in range(v0, v1):
        px = img[r, u0:u1, :3].astype(int)
        q = px // 10
        key = (q[:, 0] * 32 + q[:, 1]) * 32 + q[:, 2]
        ks, cnt = np.unique(key, return_counts=True)
        out[r] = np.median(px[key == ks[np.argmax(cnt)]], 0)
    return out


def _patch_mask(img, box, body=None, bg="row"):
    """Нашивка в рамке box: тексели не цвета фона, связные части целиком внутри рамки, с дырами. Фон: "row" — свой у
    строки (_row_bg: ткань и полосы поперёк груди), "mode" — самый частый цвет рамки (плечо: нашивка на кокетке LAV дом —
    вокруг рамки ткань другого цвета). -> (маска 1024², цвет ткани) или (None, цвет)."""
    import numpy as np
    from scipy import ndimage as ndi
    S = img.shape[0]
    body = _body_color(img, box) if body is None else body
    u0, v0, u1, v1 = (int(round(x * S)) for x in box)
    if bg == "mode":
        px = img[v0:v1, u0:u1, :3].reshape(-1, 3).astype(int)
        q = px // 10
        key = (q[:, 0] * 32 + q[:, 1]) * 32 + q[:, 2]
        ks, cnt = np.unique(key, return_counts=True)
        mc = np.median(px[key == ks[np.argmax(cnt)]], 0)
        diff = np.abs(img[..., :3].astype(np.float64) - mc).max(-1) > PATCH_DIFF
    else:
        bgr = _row_bg(img, box)
        diff = np.abs(img[..., :3].astype(np.float64) - bgr[:, None, :]).max(-1) > PATCH_DIFF
    zone = np.zeros(diff.shape, bool)
    zone[v0:v1, u0:u1] = True
    lab, n = ndi.label(diff & zone, np.ones((3, 3), bool))
    out = np.zeros(diff.shape, bool)
    for i in range(1, n + 1):
        c = lab == i
        ys, xs = np.nonzero(c)
        if len(ys) < PATCH_MIN_PX or ys.min() <= v0 or xs.min() <= u0 or ys.max() >= v1 - 1 or xs.max() >= u1 - 1:
            continue
        out |= c
    if not out.any():
        return None, body
    return ndi.binary_fill_holes(ndi.binary_closing(out, iterations=3)), body


def _erase(img, mask, grow=3):
    """Стереть нашивку: по строкам — линейно между краями маски слева и справа (цвет ткани, полосы поперёк и плавные тени
    сохраняются), затем лёгкое сглаживание по вертикали внутри маски и мелкая фактура ткани из соседнего места той же
    ширины без нашивки. -> (картинка, маска стёртого)."""
    import numpy as np
    from scipy import ndimage as ndi
    m = ndi.binary_dilation(mask, iterations=grow)
    out = img[..., :3].astype(np.float64).copy()
    ys, xs = np.nonzero(m)
    y0, y1, x0, x1 = ys.min() - 2, ys.max() + 3, xs.min() - 2, xs.max() + 3
    sub = out[y0:y1, x0:x1].copy()
    mm = m[y0:y1, x0:x1]
    f = sub.copy()
    xx = np.arange(sub.shape[1])
    for r in range(sub.shape[0]):                        # строка: между ближайшими целыми текселями слева и справа
        row = mm[r]
        if not row.any():
            continue
        good = np.nonzero(~row)[0]
        for c_ in range(3):
            f[r, row, c_] = np.interp(xx[row], good, sub[r, good, c_])
    sm = ndi.gaussian_filter(f, (1.0, 0, 0))             # строки между собой — без ряби
    f[mm] = sm[mm]
    w = x1 - x0                                          # фактура: высокие частоты из соседнего места без нашивки
    for dx in (w, -w, 2 * w, -2 * w):
        a0, a1 = x0 + dx, x1 + dx
        if a0 < 0 or a1 > img.shape[1] or m[y0:y1, a0:a1].any():
            continue
        don = out[y0:y1, a0:a1]
        hf = don - ndi.gaussian_filter(don, (3, 3, 0))
        if np.abs(hf).max() < 40:                        # без резких краёв (полоса, надпись) — только фактура
            f[mm] += hf[mm]
        break
    sub[mm] = f[mm]
    out[y0:y1, x0:x1] = sub
    return np.clip(np.round(out), 0, 255).astype(np.uint8), m


def _decal27(color, base, box, pos=False):
    """Нашивка NHL 27 в рамке box: альфа по |color − base_color|, цвет без фона (премультипликация). -> RGBA (обрезано по
    рамке нашивки) или None."""
    import numpy as np
    from scipy import ndimage as ndi
    S = color.shape[0]
    u0, v0, u1, v1 = (int(round(x * S)) for x in box)
    c, b = color[..., :3].astype(np.float64), base[..., :3].astype(np.float64)
    d = np.abs(c - b).max(-1)
    a = np.clip((d - A27_LO) / (A27_HI - A27_LO), 0, 1)
    zone = np.zeros(d.shape, bool)
    zone[v0:v1, u0:u1] = True
    lab, n = ndi.label((a > 0.05) & zone, np.ones((3, 3), bool))
    keep = np.zeros(d.shape, bool)
    for i in range(1, n + 1):
        cc = lab == i
        ys, xs = np.nonzero(cc)
        if len(ys) >= PATCH_MIN_PX and ys.min() > v0 and xs.min() > u0 and ys.max() < v1 - 1 and xs.max() < u1 - 1:
            keep |= cc
    if not keep.any():
        return None
    lab2, n2 = ndi.label(keep, np.ones((3, 3), bool))     # главная часть и всё, что рядом (части герба); дальние крапины
    if n2 > 1:                                            # ткани — не герб (RFD выезд: рамка шире, свинья выходила мелкой)
        sz = np.bincount(lab2.ravel())
        sz[0] = 0
        big = lab2 == sz.argmax()
        near = ndi.binary_dilation(big, iterations=DECAL_NEAR)
        keep = np.isin(lab2, np.unique(lab2[near & (lab2 > 0)]))
    keep = ndi.binary_dilation(keep, iterations=2)
    a = np.where(keep, a, 0.0)
    solid = a > 0.5                                      # внутри контура герба — цвет NHL 27 под ним (LAV выезд: «R» с
    a = np.where(ndi.binary_fill_holes(solid) & ~solid, 1.0, a)   # белой каймой, внутри — красная ткань; без этого — прозрачно)
    # цвет нашивки: там, где она непрозрачна, — сам цвет; на краю — (color − (1 − a)·base) / a
    rgb = np.where(a[..., None] > 0.02, (c - (1 - a[..., None]) * b) / np.maximum(a[..., None], 0.02), 0)
    ys, xs = np.nonzero(a > 0.02)
    sl = (slice(ys.min(), ys.max() + 1), slice(xs.min(), xs.max() + 1))
    dec = np.dstack([np.clip(rgb[sl], 0, 255), a[sl] * 255]).astype(np.float64)
    return (dec, (int(xs.min()), int(ys.min()))) if pos else dec


def crest_contrast(dec, body):
    """Контраст герба к цвету ткани body: медиана max|ΔRGB| по непрозрачным текселям герба (SJ выезд: тёмно-бирюзовый герб
    с чёрной формы NHL 27 на бирюзе Legacy — кайма чёрная, но сам герб сливается). -> число."""
    import numpy as np
    if dec is None:
        return -1.0
    solid = dec[..., 3] > 230
    if not solid.any():
        return -1.0
    return float(np.median(np.abs(dec[..., :3][solid] - np.asarray(body, float)).max(-1)))


def crest_under_stripes(color, base):
    """Доля рамки герба NHL 27, где под ним (base_color) не ткань: полосы поперёк груди. -> 0…1."""
    import numpy as np
    dec_a = np.abs(color[..., :3].astype(int) - base[..., :3].astype(int)).max(-1) > A27_HI
    S = color.shape[0]
    u0, v0, u1, v1 = (int(round(x * S)) for x in CREST_BOX)
    ys, xs = np.nonzero(dec_a[v0:v1, u0:u1])
    if not len(ys):
        return 1.0
    b = base[v0 + ys.min():v0 + ys.max() + 1, u0 + xs.min():u0 + xs.max() + 1, :3].astype(int)
    med = np.median(b.reshape(-1, 3), 0)
    return float((np.abs(b - med).max(-1) > 30).mean())


def _paste(img, dec, mask_old, fit=CREST_FIT_MAX):
    """Нашивка dec (RGBA float) — на место прежней (рамка mask_old): площадь рамки как у прежней, не больше fit её ширины и
    высоты, середина — та же; уменьшение с премультипликацией. -> (картинка, (x0, y0, w, h))."""
    import numpy as np
    from PIL import Image
    ys, xs = np.nonzero(mask_old)
    wo, ho = xs.max() - xs.min() + 1, ys.max() - ys.min() + 1
    hn, wn = dec.shape[:2]
    s = np.sqrt(wo * ho / float(wn * hn))
    s = min(s, fit * wo / wn, fit * ho / hn)
    W, H = max(1, int(round(wn * s))), max(1, int(round(hn * s)))
    pre = dec.copy()
    pre[..., :3] *= pre[..., 3:4] / 255.0
    ch = [np.asarray(Image.fromarray(pre[..., k].astype(np.float32)).resize((W, H), Image.LANCZOS)) for k in range(4)]
    pre = np.clip(np.stack(ch, -1), 0, 255)
    cx, cy = (xs.min() + xs.max() + 1) / 2.0, (ys.min() + ys.max() + 1) / 2.0
    x0, y0 = int(round(cx - W / 2)), int(round(cy - H / 2))
    out = img[..., :3].astype(np.float64).copy()
    reg = out[y0:y0 + H, x0:x0 + W]
    al = pre[..., 3:4] / 255.0
    out[y0:y0 + H, x0:x0 + W] = pre[..., :3] + (1 - al) * reg
    return np.clip(np.round(out), 0, 255).astype(np.uint8), (x0, y0, W, H)


def put_helmet(tag, rgba, out_root):
    """Наклейка на шлем формы tag (S_A_V, стиль 1): контейнер — её же наклейка EA (cache: пользователя или архив), растр —
    rgba (helmetlogo NHL 27 или герб), вписан в 256×128 с полем, уменьшение с премультипликацией. -> путь или None."""
    import numpy as np
    from PIL import Image
    from fb import jersey_mesh as J
    import kitpaint as kp
    import teamart as ta
    s_, a_, v_ = tag.split("_")
    rel = J.helmet_copy(a_, v_, a_, v_, out_root, style=int(s_))
    if rel is None:
        return None
    path = os.path.join(out_root, *rel.split("/"))
    rwf = ta.Rw4.load(path)
    tx = next(x for x in rwf.textures if x.name.endswith("_0.Raster") or x.name.endswith("_0"))
    w, h, _ = kp.tex_decode(rwf, tx)
    im = Image.fromarray(np.clip(rgba, 0, 255).astype(np.uint8), "RGBA")
    bb = im.getbbox()
    im = im.crop(bb) if bb else im
    k = min((w - 8) / im.width, (h - 8) / im.height)
    nw, nh = max(1, int(im.width * k)), max(1, int(im.height * k))
    a = np.asarray(im).astype(np.float64)
    a[..., :3] *= a[..., 3:4] / 255.0
    small = np.asarray(Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)).resize((nw, nh), Image.LANCZOS)).astype(np.float64)
    al = np.asarray(im.getchannel("A").resize((nw, nh), Image.LANCZOS)).astype(np.float64)
    small[..., :3] = np.where(al[..., None] > 0, small[..., :3] * 255.0 / np.maximum(al[..., None], 1), 0)
    small[..., 3] = al
    canvas = np.zeros((h, w, 4))
    y0, x0 = (h - nh) // 2, (w - nw) // 2
    canvas[y0:y0 + nh, x0:x0 + nw] = small
    canvas = np.clip(np.round(canvas), 0, 255).astype(np.uint8)
    from fb import helmet_window as HW                   # в окно шлема (03.11, SEA Amazon: на шлеме модели 20 край
    if (w, h) == (HW.W, HW.H):                           # наклейки во всю текстуру обрезается)
        k_, (dx, dy), was = HW.fit_params(canvas)
        if k_ != 1.0 or dx or dy:
            canvas = HW.place(canvas, k_, dx, dy)
            print(f"  наклейка {tag}: окно шлема — вне окна было {was * 100:.1f} %, ×{k_:.2f}, сдвиг ({dx}, {dy})")
    kp.tex_replace(rwf, tx, np.ascontiguousarray(canvas).tobytes(), w, h)
    open(path, "wb").write(rwf.bytes())
    return rel


def helmet_rgba(folder, kit27, src_dir, crest):
    """Наклейка шлема: helmetlogo NHL 27 этой формы (есть у 9 из 16 нужных клубов), иначе — герб с груди. -> RGBA."""
    import numpy as np
    from PIL import Image
    p = os.path.join(src_dir, f"helmetlogo_rbk_{folder}_{kit27}_0_color.png")
    if os.path.exists(p):
        return np.asarray(Image.open(p).convert("RGBA")).astype(np.float64), "helmetlogo NHL 27"
    return crest, "герб с груди"


def pack_kit(d, tag, cache):
    """kitpaint pack папки формы d в раскладку cache. Шаблон — сама форма EA; нет её в архивах (CV, HSK — копии EA, TUC —
    свой арт агента utah) — ALIAS_SRC или контейнер 3-значного арта 1_131_0 (все слои — свои PNG)."""
    import subprocess
    s_, a_, v_ = tag.split("_")
    arc = os.path.join(ROOT, "game", "other", "legacy", "big", "nocacherender", "rendering", "jersey", f"texlib_{tag}.rx2")
    if not os.path.exists(arc):
        kj = os.path.join(d, "kit.json")
        meta = json.load(open(kj, encoding="utf-8"))
        meta["template"] = f"{s_}_{ALIAS_SRC[int(a_)]}_{v_}" if int(a_) in ALIAS_SRC else "1_131_0"
        for lay in meta.get("layers", {}).values():          # слои — все свои: не брать буферы контейнера
            lay["sha1"] = "0" * 40
        json.dump(meta, open(kj, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    rr = subprocess.run([sys.executable, os.path.join(TOOLS, "kitpaint.py"), "--game", "legacy", "pack", d, tag, cache],
                        capture_output=True, text=True, encoding="utf-8", errors="replace")
    if rr.returncode:
        sys.exit(f"{tag}: kitpaint pack — ошибка\n{rr.stdout[-600:]}\n{rr.stderr[-600:]}")


def cmd_crest(a):
    """Только герб (03.11.2026): форма Legacy (дом и выезд по умолчанию) остаётся, герб на груди и нашивки на плечах —
    NHL 27 (из формы NHL 27, чья ткань ближе по цвету), на месте и площадью прежних; нет нашивки на плече у NHL 27 —
    прежняя стирается. Рельеф и блеск под прежними нашивками — чистые Edge T=4 (без старого контура), превью — заново,
    наклейка на шлем — helmetlogo NHL 27 или новый герб."""
    import shutil
    import numpy as np
    from PIL import Image
    from scipy import ndimage as ndi
    from fb import jersey_mesh as J, pilot
    from fb.kit_batch import CLEAN, CLEAN_T
    kits = legacy_kits()
    cache = os.path.join(OUT, "cache")
    clean_nm = np.asarray(Image.open(os.path.join(CLEAN, f"{CLEAN_T}_3-12-21-30-39-48-57-66-75_nm.png")).convert("RGB"))
    clean_sm = np.asarray(Image.open(os.path.join(CLEAN, f"{CLEAN_T}_3-12-21-30-39-48-57-66-75_sm.png")).convert("RGB")
                          .resize((1024, 1024), Image.LANCZOS))
    for code in a.clubs.split(","):
        folder = FOLDER27[code]
        src = os.path.join(OUT, "src", f"{folder}_crest")
        base = f"content/character/skater/league/ahl/{folder}/rbk/"
        names = [base + f"{k}/{l}_rbk_{folder}_{k}_{s}" for k in ("home", "away")
                 for l, s in (("jersey", "color"), ("jersey", "base_color"), ("helmetlogo", "0_color"))]
        if not os.path.exists(os.path.join(src, f"jersey_rbk_{folder}_home_color.png")):
            decode27(names, src)
        k27 = {}
        for k in ("home", "away"):
            c = os.path.join(src, f"jersey_rbk_{folder}_{k}_color.png")
            if os.path.exists(c):
                k27[k] = (np.asarray(Image.open(c).convert("RGB").resize((1024, 1024), Image.LANCZOS)),
                          np.asarray(Image.open(os.path.join(src, f"jersey_rbk_{folder}_{k}_base_color.png")).convert("RGB")
                                     .resize((1024, 1024), Image.LANCZOS)))
        for i, kit in enumerate(("home", "away")):
            tag = kits[code][i]
            leg = os.path.join(OUT, "legacy", tag)
            if not os.path.exists(os.path.join(leg, "kit.json")):
                os.makedirs(leg, exist_ok=True)
                J.unpack_kit(tag, leg)
            d = os.path.join(OUT, "kits", f"{code}_{kit}")
            if os.path.isdir(d):
                shutil.rmtree(d)                           # своя рабочая папка формы (собирается заново)
            shutil.copytree(leg, d)
            jc = np.asarray(Image.open(os.path.join(d, "jersey_cm.png")).convert("RGB"))
            nm = np.asarray(Image.open(os.path.join(d, "jersey_nm.png")).convert("RGB")).copy()
            sm = np.asarray(Image.open(os.path.join(d, "jersey_sm.png")).convert("RGB").resize((1024, 1024))).copy()
            m_old, body = _patch_mask(jc, CREST_BOX)
            if m_old is None:
                m_old, body = _patch_mask(jc, CREST_BOX_WIDE)
            if m_old is None:
                print(f"{code} {kit} ({tag}): на груди не нашёл герб — форма не тронута", flush=True)
                continue
            # форма NHL 27 — та же (дом ↔ дом: середина «R» LAV — как у NHL 27 на этой форме), если под её гербом ровная ткань и
            # кайма контрастна к ткани Legacy (CREST_CONTRAST_MIN); иначе — лучшая. Под гербом ровная ткань (полоса за гербом — часть герба цвета полосы пропадает: LAV выезд, синяя
            # «R» на синей полосе), из таких — с каймой герба контрастнее к ткани Legacy (SJ выезд: тёмный герб с чёрной формы
            # NHL 27 на бирюзе Legacy терялся — светлый, с серой домашней, виден)
            score = {k: (crest_under_stripes(*k27[k]) > 0.05, -crest_contrast(_decal27(*k27[k], CREST_BOX), body))
                     for k in k27}
            kk = kit if kit in score and -score[kit][1] >= CREST_CONTRAST_MIN else min(score, key=score.get)
            color, basec = k27[kk]
            crest = _decal27(color, basec, CREST_BOX)
            if crest is None:
                crest = _decal27(color, basec, CREST_BOX_WIDE)
            if crest is None:
                print(f"{code} {kit}: у NHL 27 {kk} на груди не нашёл герб — форма не тронута", flush=True)
                continue
            jc, er = _erase(jc, m_old)
            jc, place = _paste(jc, crest, m_old)
            rep = [f"{code} {kit} {tag}: герб — NHL 27 {kk}, место {place}"]
            erased = [er]
            for box in SHOULDER_BOXES:
                m_s, b_s = _patch_mask(jc, box, bg="mode")
                if m_s is None:
                    continue
                jc, er_s = _erase(jc, m_s)
                erased.append(er_s)
                dp = _decal27(color, basec, box, pos=True)
                if dp is not None:                         # нашивка плеча — на месте и размера NHL 27 (развёртки у плеч
                    dec, (px0, py0) = dp                   # совпадают; по площади прежней надпись LAVAL у LAV выходила за
                    m_n = np.zeros(m_s.shape, bool)        # остров развёртки плеча — «AVAL», 03.11)
                    m_n[py0:py0 + dec.shape[0], px0:px0 + dec.shape[1]] = True
                    jc, pl = _paste(jc, dec, m_n, fit=1.0)
                    rep.append(f"плечо {box[0]:.2f}: нашивка NHL 27 {pl}")
                else:
                    rep.append(f"плечо {box[0]:.2f}: прежняя нашивка стёрта (у NHL 27 нет)")
            allm = ndi.binary_dilation(np.any(erased, 0), iterations=4)
            soft = ndi.gaussian_filter(allm.astype(float), 2.0)[..., None]
            nm = np.round(nm * (1 - soft) + clean_nm * soft).astype(np.uint8)   # без рельефа прежних нашивок
            sm = np.round(sm * (1 - soft) + clean_sm * soft).astype(np.uint8)
            Image.fromarray(jc).save(os.path.join(d, "jersey_cm.png"))
            Image.fromarray(nm).save(os.path.join(d, "jersey_nm.png"))
            Image.fromarray(sm).save(os.path.join(d, "jersey_sm.png"))
            pilot.fe_preview_ea(os.path.join(d, "jersey_cm.png")).save(os.path.join(d, "fe.png"))
            if a.dry:
                print("; ".join(rep), flush=True)
                continue
            pack_kit(d, tag, cache)
            hr, how = helmet_rgba(folder, kk, src, crest)
            rel = put_helmet(tag, hr, cache)
            rep.append(f"шлем — {how}" + (f" ({rel})" if rel else " (наклейки у формы нет)"))
            print("; ".join(rep), flush=True)
    print("раскладка cache: →", cache)


def cmd_out(a):
    """Раскладка game/work/ahl27/cache — в дерево a.dir (накладка / пакет), файлы поверх. -> число файлов."""
    import shutil
    src = os.path.join(OUT, "cache")
    n = 0
    for dp, _, fn in os.walk(src):
        for f in fn:
            rel = os.path.relpath(os.path.join(dp, f), src)
            q = os.path.join(a.dir, rel)
            os.makedirs(os.path.dirname(q), exist_ok=True)
            shutil.copy2(os.path.join(dp, f), q)
            n += 1
    print(f"формы АХЛ: {n} файлов → {a.dir}")
    return n


DIGIT_CELL_WIDE = 1.135                    # клетка цифры в игре шире атласа — как у стандарта спины клубов НХЛ (одобрено 24.10)
DIGIT_ASPECT_BIG = 2 * 80 / 123 * DIGIT_CELL_WIDE   # ширина зоны номера к высоте (на свитере): клетка цифры 80 × 123 px
#                                    рисуется в половину зоны (03.11, пользователь: «номер на спине очень узкий и вытянутый»:
#                                    зона EA прежнего клуба — под его шрифт; у ABB шрифт NHL 27 и сам узкий — 0,45 ширины к
#                                    высоте против 0,64 у EA, в игре теперь 0,51)
DIGIT_ASPECT_SMALL = 1.057                 # зона номера на рукаве, ширина к высоте — как у одобренной MIN (слот, zone_size_cm):
#                                    при клетке 48 × 59 вышло ×1,65 — цифры на руке HSK растянуты (03.11)


def fit_digit_aspect(d, which=("back", "sleeve")):
    """Зоны номера на спине (1) и рукавах (2, 3) — шириной под пропорции цифр атласа (DIGIT_ASPECT_*): у зоны EA прежнего
    клуба другая пропорция, цифры NHL 27 выходили сжатыми или растянутыми. Ширина у середины, высота та же; наезд на
    другую зону — сколько можно. -> описание."""
    from fb import edge_kit as E
    png = os.path.join(d, "name_cm.png")
    rep = []
    for zones, asp in [z for w, z in (("back", ((1,), DIGIT_ASPECT_BIG)), ("sleeve", ((2, 3), DIGIT_ASPECT_SMALL)))
                       if w in which]:
        zs = E.zone_size_cm(png, zones[0])
        if zs is None:
            continue
        k = asp * zs[1] / zs[0]
        if abs(k - 1) < 0.03:
            continue
        for kk in (k, 1 + (k - 1) * 0.75, 1 + (k - 1) * 0.5):
            keep = open(png, "rb").read()
            try:
                r = E.scale_zones_x(png, zones, kk)
                rep.append(f"зоны {zones} шире ×{kk:.2f} {r}")
                break
            except SystemExit:                         # наезд на другую зону — меньше
                open(png, "wb").write(keep)
    return "пропорции цифр: " + ("; ".join(rep) if rep else "как есть")


NAME_YOKE_GAP = 0.027                     # м: от края кокетки сзади до верха фамилии (как у клубов НХЛ, LETTERING_YOKE_GAP)


def fit_name_yoke(d):
    """Фамилия не на кокетке сзади (03.11, HSK: «фамилия обрезана сверху, наезжает на кокетку»): от середины зоны фамилии
    вверх по середине спины — первая строка не цвета ткани (край кокетки); верх фамилии выше края − NAME_YOKE_GAP —
    фамилия и номер ниже на столько же (номер потом — fit_back_number: не на полосах подола). -> описание."""
    import math
    import numpy as np
    from PIL import Image
    from fb import edge_kit as E
    k, _b = E.back_m_per_v()
    png = os.path.join(d, "name_cm.png")
    a = np.asarray(Image.open(png).convert("RGBA"))
    H = a.shape[0]
    m0 = (a[..., 0] > 128) & (a[..., 1] > 128) & (a[..., 2] == 0)
    if not m0.any():
        return "зоны фамилии нет — как есть"
    ys, xs = np.nonzero(m0)
    j = np.asarray(Image.open(os.path.join(d, "jersey_cm.png")).convert("RGB")).astype(int)
    S = j.shape[0]
    f = S // H
    cx = (xs.min() + xs.max() + 1) * f // 2
    col = j[:, cx - S // 40:cx + S // 40]
    mid = (ys.min() + ys.max() + 1) * f // 2
    body = np.median(col[mid - 4 * f:mid + 4 * f].reshape(-1, 3), 0)
    yb = None
    for r in range(mid, S):                               # вверх по спине — к большим строкам
        if np.median(np.abs(col[r] - body).max(-1)) > 40:
            yb = r
            break
    if yb is None:
        return "кокетки сзади нет — фамилия как есть"
    per_row = k / H
    top_max = math.floor(yb / f - NAME_YOKE_GAP / per_row)    # верхняя строка фамилии — не выше
    over = ys.max() + 1 - top_max
    if over <= 0:
        return f"фамилия: до кокетки {(top_max - ys.max() - 1) * per_row * 100 + NAME_YOKE_GAP * 100:.1f} см — как есть"
    r0 = E.lift_name_zone(png, -over * per_row * 100, zone=0)
    r1 = E.lift_name_zone(png, -over * per_row * 100, zone=1)
    return f"фамилия и номер ниже на {over * per_row * 100:.1f} см (кокетка сзади) {r0} {r1}"


BACK_HEM_GAP = 0.015                      # м: от верха полос подола до низа зоны номера на спине — не меньше
BACK_NAME_GAP = 0.010                     # м: от низа зоны фамилии до верха зоны номера — не меньше (при подъёме)


def fit_back_number(d):
    """Номер на спине не на полосах подола (пользователь, 03.11, ABB: «номера на спине тоже заходят на нижние полосы»):
    зона номера (1) EA прежнего клуба стоит под его рисунок, у NHL 27 полосы подола выше. Всё — в строках развёртки (на
    спине +v — вверх): от середины зоны номера вниз по середине спины — первая строка не цвета ткани (верх полос подола);
    низ зоны ниже его + BACK_HEM_GAP — зона выше (до BACK_NAME_GAP под фамилией), не хватает — ещё и мельче, верх на
    месте. -> описание."""
    import math
    import numpy as np
    from PIL import Image
    from fb import edge_kit as E
    k, _b = E.back_m_per_v()
    png = os.path.join(d, "name_cm.png")
    a = np.asarray(Image.open(png).convert("RGBA"))
    H = a.shape[0]
    zone = lambda z: (a[..., 0] > 128) & (a[..., 1] > 128) & (a[..., 2] == z)
    m1, m0 = zone(1), zone(0)
    if not m1.any():
        return "зоны номера нет — как есть"
    ys, xs = np.nonzero(m1)
    j = np.asarray(Image.open(os.path.join(d, "jersey_cm.png")).convert("RGB")).astype(int)
    S = j.shape[0]
    f = S // H
    cx = (xs.min() + xs.max() + 1) * f // 2
    col = j[:, cx - S // 40:cx + S // 40]
    mid = (ys.min() + ys.max() + 1) * f // 2
    body = np.median(col[mid - 4 * f:mid + 4 * f].reshape(-1, 3), 0)
    hem = None
    for r in range(mid, 0, -1):                           # вниз по спине — к меньшим строкам
        if np.median(np.abs(col[r] - body).max(-1)) > 40:
            hem = r + 1                                   # первая строка ткани над полосами (развёртка S²)
            break
    if hem is None:
        return "полос подола у середины спины нет — номер как есть"
    per_row = k / H                                       # м на строку карты номеров
    target = math.ceil(hem / f + BACK_HEM_GAP / per_row)
    need = target - ys.min()
    if need <= 0:
        return f"номер на спине: над полосами подола {(ys.min() - hem / f) * per_row * 100:.1f} см — как есть"
    r0 = np.nonzero(m0.any(1))[0]
    room = (r0.min() - int(math.ceil(BACK_NAME_GAP / per_row)) - ys.max() - 1) if len(r0) else need
    lift = max(0, min(need, room))
    rep = []
    if lift:
        rep.append(f"выше на {lift} строк ({lift * per_row * 100:.1f} см) {E.lift_name_zone(png, lift * per_row * 100, zone=1)}")
    rest = need - lift
    if rest > 0:
        h = ys.max() - ys.min() + 1
        kk = max(0.6, (h - rest) / h)
        sz = E.scale_zones(png, kk, (1,), anchor="top")    # «top» у scale_zones — меньшая строка, на спине это низ
        nh = int(round(h * kk))                            # номера: верх на место — подъём на разницу высот
        E.lift_name_zone(png, (h - nh) * per_row * 100, zone=1)
        rep.append(f"мельче ×{kk:.2f} {sz}, верх на месте")
    return f"номер на спине: был {(ys.min() - hem / f) * per_row * 100:+.1f} см над полосами подола — " + "; ".join(rep)

# ---------------------------------------------------------------- шорты, экипировка, копия формы НХЛ (03.11.2026)
# Пользователь, 03.11: «трусы, шлемы, перчатки для команд АХЛ, у которых ты серьёзно менял форму, ты не поменял — это
# косяк». Шорты — текстура формы (pant/texlib_S_A_V); шлем и краги — строки stockteamequipmenttable клуба (equipment 7 и
# 4, ключ — era, вариант формы, бренд; nhl24.py eq_lookup — как выбирает игра).

def pants27(d, leg, color_png, base_png):
    """Шорты NHL 27 формы → d/pant_cm.png: ткань — 3D-перенос base_color (сетки шорт NHL 24 → Legacy, как fb.pilot), нашивки
    — наклейками на шорты полевых в игре (fb.pant_decals.apply), рельеф и блеск — образца Legacy leg без его гербов и с
    рельефом наших (pant_decals.relief). У АХЛ NHL 27 шорты однотонные — полос низа нет (у CBJ переносом рвались они).
    Прежде (до 03.11) — родные шорты Legacy с тонировкой: оставались полосы и герб прежнего клуба. -> описание."""
    import numpy as np
    from PIL import Image
    from fb import kit3d, pilot, pant_decals
    pN, pL = kit3d.load_nhl24(pilot.PANT_N24), kit3d.load_legacy(pilot.PANT_L)
    bN = kit3d.bbox(pN)
    bN[3] = pilot.PANT_WAIST
    pLa = kit3d.aligned(pL, bN, kit3d.bbox(pL))
    pcol, pbase = kit3d.load_tex(color_png), kit3d.load_tex(base_png)
    pimg = kit3d.transfer(pbase, pN, pLa, 512, 2)[0]
    masks = {}
    pimg, prep = pant_decals.apply(pimg, pcol, pbase, pN, 512, masks=masks)
    Image.fromarray(np.clip(pimg, 0, 255).astype(np.uint8)).convert("RGB").save(os.path.join(d, "pant_cm.png"))
    mp = os.path.join(d, pant_decals.MASKS)
    pant_decals.save_masks(mp, masks)
    info = pant_decals.relief(leg, d, mp)
    return f"NHL 27 (3D, нашивок {len(prep)}; рельеф — {pant_decals.relief_note(info)})"


EQ_HELMET, EQ_GLOVES = 7, 4
COPY_FROM = {"UTI": "NJD"}                 # клуб АХЛ → клуб НХЛ, чья форма слота — за основу (03.11, пользователь по Utica:
#                                    «возьмём за основу форму НХЛ (Нью-Джерси), уберём шильдик НХЛ и поменяем логотип»)
COPY_KITS = {"home": "away", "away": "home"}   # дом АХЛ — белая (выезд NJD), выезд — красная (дом NJD), как принято в АХЛ
SHIELD_BOX_UV0 = (0.470, 0.575, 0.530, 0.607)   # щит НХЛ у ворота в развёртке Edge (uv0; у NJD — u 0,488–0,511, v 0,584–0,598):
#                                    рамка внутри чёрного мыса V — фон рамки (самый частый цвет) — мыс, щит в нём


def team27_index():
    """{код АХЛ: index клуба в exhibitionteams NHL 27} — по названию (fb.ice.AHL27)."""
    from tdb import Tdb
    from tdb_read import load_meta
    from fb.ice import AHL27, _norm
    D = os.path.join(ROOT, "game", "work", "nhl27", "db")
    db = Tdb(open(os.path.join(D, "nhl_game.db"), "rb").read(), load_meta(os.path.join(D, "nhl_game-meta.xml")))
    t = "exhibitionteams"
    by = {}
    for r in db.live_rows(t):
        for nm in (db.get_string(t, "cityname", r) + db.get_string(t, "nickname", r), db.get_string(t, "teamname", r)):
            by[_norm(nm)] = db.get(t, "index", r)
    return db, {code: by.get(_norm(name)) for _c, _a, code, _n, name in AHL27}


FOLDER_VARIANT = {"home": 0, "away": 1}    # папка комплекта АХЛ NHL 27 → вариант (номер папки, как ten = 10 у НХЛ): у NHL 27
#                                    белая home — variant 0 с locstring 1; наша форма дома собрана из папки home


def zones27(db27, team, eq, var):
    """Зоны 1–9 строки экипировки NHL 27 для формы клуба с этим вариантом: (−1, вариант) → (−1, −1) → первая.
    -> [27 чисел] или None."""
    from kitport.profile import nhl27_equipment
    rows = nhl27_equipment(db27, team, eq)
    for v in (var, -1):
        r = next((x for x in rows if x[1] == v and x[2] == -1), None)
        if r is not None:
            return [c for z in r[3] for c in z]
    return [c for z in rows[0][3] for c in z] if rows else None


def equip_plan(db, kits):
    """План экипировки: [(клуб, форма, equipment, строка базы, зоны было, стало)] — у строк, которые игра берёт для формы
    (nhl24.eq_lookup: era = стиль формы, вариант, бренд −1 и бренды строк клуба). Клубы — полный перенос (FULL_EQUIP) и
    копии форм НХЛ (COPY_FROM: экипировка клуба НХЛ той же формы)."""
    sys.path.insert(0, os.path.join(TOOLS, "legacy_data"))
    import nhl24 as N
    low = N.eq_low(db)
    db27, t27 = team27_index()
    J = "stockteamjerseys"
    teamid = {code: next((db.get(J, "teamid", r) for r in db.live_rows(J) if db.get(J, "teamartid", r) == art), None)
              for _c, art, code, _n, _nm in __import__("fb.ice", fromlist=["AHL27"]).AHL27}
    ref = _ref_db()                                      # экипировка формы-основы — из базы cache: (с накладкой NHL 27):
    rlow = N.eq_low(ref)                                 # в базе out строк стиля 2 у NJD ещё нет
    reg = json.load(open(os.path.join(TOOLS, "legacy_data", "nhl24_kits.json"), encoding="utf-8"))["kits"]
    plan, seen = [], {}
    for code in FULL_EQUIP + list(COPY_FROM):
        if teamid.get(code) is None:
            print(f"  {code}: клуба нет в этой базе (CV, HSK — только --ahl32) — пропуск")
            continue
        tag_h, tag_a, _ = kits[code]
        recs = N.club_equipment(db, low, teamid[code])
        for loc, (kit, tag) in enumerate((("home", tag_h), ("away", tag_a))):
            s_, a_, v_ = (int(x) for x in tag.split("_"))
            for eq in (EQ_HELMET, EQ_GLOVES):
                if code in COPY_FROM:                     # экипировка формы клуба НХЛ (слот стиля 2)
                    src = COPY_FROM[code]
                    r = next(x for x in reg if x["club"] == src and x["kit"] == f"edge_{COPY_KITS[kit]}")
                    srecs = N.club_equipment(ref, rlow, r["teamid"])
                    want = list(N.eq_lookup(srecs, (r["style"], r["variant"], eq, -1))[5])
                else:
                    want = zones27(db27, t27[code], eq, FOLDER_VARIANT[kit])
                if want is None:
                    continue
                brands = sorted({x[3] for x in recs if x[2] == eq} | {-1})
                for b in brands:
                    best = N.eq_lookup(recs, (s_, v_, eq, b))
                    if best[2] != eq:
                        continue
                    row = best[4]
                    key = (code, eq, row)
                    if key in seen and seen[key] != want:
                        print(f"  {code} {kit}: строка {row} (equipment {eq}) общая с другой формой — оставлена по "
                              f"{seen[key + ('kit',)]}")
                        continue
                    seen[key], seen[key + ("kit",)] = want, kit
                    if list(best[5]) != want and not any(p_[3] == row for p_ in plan):
                        plan.append((code, kit, eq, row, list(best[5]), want))
    return plan


_REF = []


def _ref_db():
    from tdb import Tdb
    from tdb_read import load_meta
    if not _REF:
        _REF.append(Tdb(open(os.path.join(CACHE_DB, "nhlng.db"), "rb").read(), load_meta(os.path.join(CACHE_DB, "nhlng-meta.xml"))))
    return _REF[0]


def equip_apply(db, plan):
    sys.path.insert(0, os.path.join(TOOLS, "legacy_data"))
    import nhl24 as N
    lows = db.by_name[N.EQ]["lows"]
    for _c, _k, _e, row, _old, new in plan:
        for f, v in zip(N.EQ_ZONES, new):
            db.set(N.EQ, f, row, v - lows.get(f, 0))


def cmd_equip(a):
    """Шлем и краги полностью перенесённых клубов АХЛ (FULL_EQUIP) — цвета NHL 27 их новой формы, копий форм НХЛ (UTI) — как
    у формы-основы; база (--db, по умолчанию cache: пользователя) или сейв (--save, ROSTER / DYNASTY). Строки не добавляются
    — меняются зоны тех, что игра уже берёт для этих форм. Проба — без --write; запись — копия рядом, CRC, повторный план
    пуст. -> 0."""
    import shutil
    import time
    from tdb import SaveFile, Tdb, load_meta
    meta_p = a.meta or os.path.join(CACHE_DB, "nhlng-meta.xml")
    meta = load_meta(meta_p)
    kits = legacy_kits()
    targets = [("db", p) for p in (a.db or [])] + [("save", p) for p in (a.save or [])]
    if not targets:
        targets = [("db", os.path.join(CACHE_DB, "nhlng.db"))]
    for kind, path in targets:
        raw = open(path, "rb").read()
        if kind == "save":
            sf = SaveFile(raw, meta)
            bad0 = sf.verify()
            if bad0:
                sys.exit(f"{path}: сейв не проходит проверку до правки: {bad0}")
            db = sf.db
        else:
            db = Tdb(raw, meta)
        plan = equip_plan(db, kits)
        print(f"{path}: строк к правке {len(plan)}")
        for code, kit, eq, row, old, new in plan:
            print(f"  {code} {kit} {'шлем' if eq == EQ_HELMET else 'краги'} (строка {row}): {old[:3]} → {new[:3]}")
        if not a.write or not plan:
            print("  проба: не записано" if not a.write else "  уже так")
            continue
        equip_apply(db, plan)
        bdir = os.path.join(OUT, "backup", f"{os.path.basename(path)}-{time.strftime('%Y%m%d-%H%M%S')}")
        os.makedirs(bdir, exist_ok=True)
        shutil.copy2(path, os.path.join(bdir, os.path.basename(path)))
        if kind == "save":
            out = sf.bytes(fix=True)
            if len(out) != len(raw):
                sys.exit("размер сейва изменился — не пишу")
            chk = SaveFile(out, meta)
            bad = chk.verify()
            if not bad and equip_plan(chk.db, kits):
                bad = ["повторный план не пуст"]
        else:
            db.fix()
            out = bytes(db.d)
            chk = Tdb(out, meta)
            bad = [f"CRC {x}" for x in chk.verify()]
            if not bad and equip_plan(chk, kits):
                bad = ["повторный план не пуст"]
        if bad:
            sys.exit(f"{path}: проверка не прошла, не записано: {bad}")
        open(path + ".part", "wb").write(out)
        os.replace(path + ".part", path)
        print(f"  записано; CRC — OK; копия до записи — {bdir}")
    return 0


def copy_pants_clean(d, leg, src_out):
    """Шорты формы-основы без её гербов (NJD: «N» Devils на ноге): по маскам нашивок стадии kit (src_out/pant_decals_a.png,
    R — гербы спереди) — заливка тканью вокруг; рельеф и блеск — образца Legacy leg без его гербов и без наших
    (pant_decals.relief с пустой маской). -> описание."""
    import numpy as np
    from PIL import Image
    from scipy import ndimage as ndi
    from fb import pant_decals
    mp = os.path.join(src_out, pant_decals.MASKS)
    if not os.path.exists(mp):
        return "шорты основы как есть (нет масок нашивок)"
    pc = np.asarray(Image.open(os.path.join(d, "pant_cm.png")).convert("RGB"))
    mk = np.asarray(Image.open(mp).convert("RGB").resize(pc.shape[1::-1], Image.NEAREST))
    m = mk[..., 0] > 20                                  # гербы спереди; щит сзади (G) — шорты НХЛ-клуба, у АХЛ его нет тоже
    m |= mk[..., 1] > 20
    n = int(m.sum())
    if n:
        out = pc.astype(np.float64).copy()
        lab, k = ndi.label(ndi.binary_dilation(m, iterations=3))
        for i in range(1, k + 1):
            part = lab == i
            ys, xs = np.nonzero(part)
            sub_m = part[ys.min() - 2:ys.max() + 3, xs.min() - 2:xs.max() + 3]
            img = out[ys.min() - 2:ys.max() + 3, xs.min() - 2:xs.max() + 3]
            ring = ndi.binary_dilation(sub_m, iterations=2) & ~sub_m
            img[sub_m] = np.median(img[ring], 0)
        Image.fromarray(np.clip(np.round(out), 0, 255).astype(np.uint8)).save(os.path.join(d, "pant_cm.png"))
    empty = os.path.join(d, "_no_decals.png")
    pant_decals.save_masks(empty, {})
    info = pant_decals.relief(leg, d, empty)
    os.remove(empty)
    return f"шорты основы: гербы стёрты ({n} текс.), рельеф — {pant_decals.relief_note(info)}"


def cmd_copy(a):
    """Форма клуба АХЛ — копия формы слота клуба НХЛ (COPY_FROM; 03.11, Utica ← NJD): свитер (развёртка Edge, uv0 —
    edge_kit.deislanded: у строк АХЛ сетка стиля 1), рельеф, блеск, шрифт, карта номеров, шорты, гетры — формы НХЛ; щит НХЛ
    у ворота стёрт, герб на груди — герб клуба из NHL 27; превью — заново, наклейка шлема — герб. Дом АХЛ — белая
    (COPY_KITS). Раскладка — game/work/ahl27/cache."""
    import shutil
    import numpy as np
    from PIL import Image
    from fb import edge_kit as E, jersey_mesh as J, pilot
    kits = legacy_kits()
    cache = os.path.join(OUT, "cache")
    slot = os.path.join(ROOT, "game", "work", "nhl24", "edgekit", "slot", "kits")
    for code in a.clubs.split(","):
        src_club = COPY_FROM[code]
        folder = FOLDER27[code]
        s27 = os.path.join(OUT, "src", f"{folder}_crest")
        base = f"content/character/skater/league/ahl/{folder}/rbk/"
        if not os.path.exists(os.path.join(s27, f"jersey_rbk_{folder}_home_color.png")):
            decode27([base + f"{k}/jersey_rbk_{folder}_{k}_{s}" for k in ("home", "away") for s in ("color", "base_color")], s27)
        k27 = {k: (np.asarray(Image.open(os.path.join(s27, f"jersey_rbk_{folder}_{k}_color.png")).convert("RGB")
                              .resize((1024, 1024), Image.LANCZOS)),
                   np.asarray(Image.open(os.path.join(s27, f"jersey_rbk_{folder}_{k}_base_color.png")).convert("RGB")
                              .resize((1024, 1024), Image.LANCZOS))) for k in ("home", "away")}
        for i, kit in enumerate(("home", "away")):
            tag = kits[code][i]
            leg = os.path.join(OUT, "legacy", tag)
            if not os.path.exists(os.path.join(leg, "kit.json")):
                os.makedirs(leg, exist_ok=True)
                J.unpack_kit(tag, leg)
            sd = os.path.join(slot, f"{src_club}_{COPY_KITS[kit]}")
            d = os.path.join(OUT, "kits", f"{code}_{kit}")
            if os.path.isdir(d):
                shutil.rmtree(d)
            shutil.copytree(leg, d)
            for f in ("jersey_nm", "jersey_sm", "font_cm", "font_nm", "font_sm", "name_cm", "pant_cm", "pant_nm",
                      "pant_sm", "sock_cm"):
                shutil.copy2(os.path.join(sd, f + ".png"), os.path.join(d, f + ".png"))
            E.deislanded(os.path.join(sd, "jersey_cm.png"), os.path.join(d, "jersey_cm.png"))
            rep_p = copy_pants_clean(d, leg, os.path.join(ROOT, "game", "work", "nhl24", "edgekit", "out",
                                                          f"{src_club}_{COPY_KITS[kit]}"))
            jc = np.asarray(Image.open(os.path.join(d, "jersey_cm.png")).convert("RGB"))
            rep = [f"{code} {kit} {tag} ← {src_club} {COPY_KITS[kit]}", rep_p]
            m_sh, _ = _patch_mask(jc, SHIELD_BOX_UV0, bg="mode")
            if m_sh is not None:
                jc, _ = _erase(jc, m_sh, grow=1)
                rep.append(f"щит НХЛ стёрт ({int(m_sh.sum())} текс.)")
            m_old, body = _patch_mask(jc, CREST_BOX)
            if m_old is None:
                m_old, body = _patch_mask(jc, CREST_BOX_WIDE)
            score = {k: -crest_contrast(_decal27(*k27[k], CREST_BOX), body) for k in k27}
            kk = min(score, key=score.get)
            crest = _decal27(*k27[kk], CREST_BOX)
            jc, _ = _erase(jc, m_old)
            jc, place = _paste(jc, crest, m_old)
            rep.append(f"герб — NHL 27 {kk}, место {place}")
            Image.fromarray(jc).save(os.path.join(d, "jersey_cm.png"))
            pilot.fe_preview_ea(os.path.join(d, "jersey_cm.png")).save(os.path.join(d, "fe.png"))
            pack_kit(d, tag, cache)
            rel = put_helmet(tag, crest, cache)
            rep.append(f"шлем — герб ({rel})")
            print("; ".join(rep), flush=True)
    print("раскладка cache: →", cache)


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
    from fb import jersey_mesh as J
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
                     (("jersey", "color"), ("font", "color"), ("font", "normal"), ("pant", "color"), ("sock", "color"),
                      ("jersey", "base_color"), ("helmetlogo", "0_color"), ("pant", "base_color"))]
            if not os.path.exists(os.path.join(src, names[-1].rsplit("/", 1)[1] + ".png")):
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
            uvd = pad_outside(jc, Mr)                      # сбоку под рукой развёртки rbk и Edge расходятся — по UV там
            jc = np.where(msk[..., None], np.clip(np.round(tr[..., :3]), 0, 255), uvd)   # шла тёмная черта
            sl = sleeve_soft(jc.shape[0])                  # рукава — по развёртке (03.11, пользователь: «у Абботсфорда
            jc = np.round(jc * (1 - sl[..., None]) + uvd * sl[..., None]).astype(np.uint8)   # косяки на рукавах»: руки
            n_fix = int(msk.sum())                         # сеток в разной позе, 3D сдвигал полосы и клин рукава)
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
            if os.path.exists(sp("pant", "color")) and os.path.exists(sp("pant", "base_color")):
                rep.append("шорты — " + pants27(d, leg, sp("pant", "color"), sp("pant", "base_color")))
            pilot.fe_preview_ea(os.path.join(d, "jersey_cm.png")).save(os.path.join(d, "fe.png"))
            ref = os.path.join(OUT, "legacy", LETTERING_FROM)    # фамилия и номер на спине — места MIN (как у клубов НХЛ,
            if not os.path.exists(os.path.join(ref, "kit.json")):   # стандарт спины): у карты EA прежнего клуба свои (CLE —
                os.makedirs(ref, exist_ok=True)             # Lake Erie: фамилия дугой на кокетке, номер огромный)
                J.unpack_kit(LETTERING_FROM, ref)
            rep.append(f"фамилия и номер — места {LETTERING_FROM}: "
                       f"{E.copy_zones(os.path.join(d, 'name_cm.png'), os.path.join(ref, 'name_cm.png'), (0, 1))}")
            rep.append(fit_name_yoke(d))
            rep.append(fit_digit_aspect(d, ("back",)))
            rep.append(fit_back_number(d))
            col = upper_arm_color(d)                       # номер на рукаве — с полос на верх руки (CV: зона EA Falcons
            nm_png = os.path.join(d, "name_cm.png")       # легла на красную полосу NHL 27)
            keep_nm = open(nm_png, "rb").read()
            zr = E.zones_onto_color(nm_png, os.path.join(d, "jersey_cm.png"), (2, 3), col, need=0.95)
            if any("!" in str(v[1]) for v in zr.values()):  # места цвета под номер не хватает (ABB: 0,83–0,89) — мельче
                open(nm_png, "wb").write(keep_nm)
                E.scale_zones(nm_png, SLEEVE_SMALL, (2, 3))
                zr = E.zones_onto_color(nm_png, os.path.join(d, "jersey_cm.png"), (2, 3), col, need=0.95)
                rep.append(f"номер на рукаве ×{SLEEVE_SMALL}")
            rep.append(f"номер на рукаве — на цвет {col}: " + str(zr))
            rep.append(fit_digit_aspect(d, ("sleeve",)))
            pack_kit(d, tag, cache)
            # наклейка на шлем (03.11: у всех стояла наклейка прежнего клуба) — helmetlogo NHL 27 или герб с груди
            crest = _decal27(np.asarray(Image.open(sp("jersey", "color")).convert("RGB").resize((1024, 1024))),
                             np.asarray(Image.open(sp("jersey", "base_color")).convert("RGB").resize((1024, 1024))),
                             CREST_BOX) if os.path.exists(sp("jersey", "base_color")) else None
            hp = sp("helmetlogo", "0_color")
            hr = np.asarray(Image.open(hp).convert("RGBA")).astype(np.float64) if os.path.exists(hp) else crest
            if hr is not None:
                rel = put_helmet(tag, hr, cache)
                rep.append(f"шлем — {'helmetlogo NHL 27' if os.path.exists(hp) else 'герб с груди'} ({rel})")
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
    p = sub.add_parser("crest", help="только герб: форма Legacy, гербы и наклейка шлема — NHL 27 (--clubs HMR,LAV)")
    p.add_argument("--clubs", required=True, help="коды через запятую")
    p.add_argument("--dry", action="store_true", help="без раскладки cache: — только папки форм (картинки)")
    p = sub.add_parser("copy", help="форма — копия формы слота клуба НХЛ (UTI ← NJD): щит стёрт, герб NHL 27 клуба")
    p.add_argument("--clubs", default="UTI")
    p = sub.add_parser("equip", help="шлем и краги клубов с новой формой — цвета NHL 27 (база --db, сейв --save)")
    p.add_argument("--db", action="append", help="база nhlng.db (по умолчанию — cache: пользователя); можно несколько")
    p.add_argument("--save", action="append", help="сейв ROSTER/DYNASTY (файл внутри папки сейва)")
    p.add_argument("--meta", default=None, help="nhlng-meta.xml (по умолчанию — из cache: пользователя)")
    p.add_argument("--write", action="store_true")
    p = sub.add_parser("out", help="раскладку game/work/ahl27/cache — в дерево (накладка, пакет)")
    p.add_argument("dir", help="корень дерева cache:")
    p = sub.add_parser("decode", help="(служебная) текстуры NHL 27 → PNG, FB_GAME=nhl27")
    p.add_argument("--names", required=True)
    p.add_argument("--out", required=True)
    a = ap.parse_args()
    os.environ["FB_GAME"] = "nhl24" if a.cmd in ("build", "crest", "copy", "equip") else "nhl27"   # fb.cas: корень дампа
    {"sheet": cmd_sheet, "build": cmd_build, "crest": cmd_crest, "out": cmd_out, "decode": cmd_decode, "copy": cmd_copy,
     "equip": cmd_equip}[a.cmd](a)


if __name__ == "__main__":
    main()
