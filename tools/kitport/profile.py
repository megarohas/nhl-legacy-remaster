"""Генератор профиля клуба подхода C (формы NHL 27 на крое Edge Legacy), docs/kitport.md §12.3, §12.6.

    python -m kitport profile --club BOS            # предложение и сравнение с тем, что уже есть (ничего не пишет)
    python -m kitport profile --club NJD,TBL        # то же для нескольких клубов (проверка генератора на готовых)
    python -m kitport profile --club BOS --write    # записать: раздел [BOS] в fb/edge_clubs.toml, номера форм в реестре
                                                    # legacy_data/nhl24_kits.json, каска и краги в nhl24_helmets.json
    python -m kitport profile --club BOS --write-palette   # отдельно: палитру клуба NHL 27 → nhl24_team_colors.json

Что решает сам и откуда (у каждого решения в выводе — «уверен» или «проверить» и причина):
- source = "nhl27", source_kits — нынешние дом и выезд по базе NHL 27 (stockteamjerseys стиль 2, isdefault, locstring
  0 / 1 → папка комплекта, как kitport survey);
- образцы legacy — EA-формы клуба в базе Legacy (stockteamjerseys стиль 1, locstring 0 / 1; у одобренных клубов в
  накладке они уже locstring 6 с подписью «(EA)» — база out, до накладки, это не меняет);
- номера форм edge_home / edge_away в реестре — как nhl24.py alloc (--style 0), jerseyindex подряд: формы базы →
  поставленные формы реестра (файл свитера есть в cache: игры) → edge_home, edge_away → прочие не поставленные (так
  правили руками NJD и TBL, §5.3 п. 1, §12.5); поставленные формы номер не меняют никогда;
- collar (lace | plain), кокетка (yoke, yoke_color, yoke_shape_color), body_color — по текстуре основы источника на
  сетке NHL 24 (наружная оболочка): шнуровка — пёстрое под щитом посередине переда, кокетка — цвет верха плеч не цвет
  ткани, «на плечо» — тот же цвет на верхе рукава за суставом;
- trim_width_from — если у формы кромка цвета ткани (верх ворота сзади против ткани ниже; BOS дом: чёрное на чёрном), а
  у другой — видна: ширина кромки — по другой форме (иначе замер по цвету даёт 3,7 см и щит по зазору уезжает вниз);
- merge_parts — если герб источника — несколько связных частей (как молния и кольцо TBL); base_normal_decals — если в
  _base_normal под нашивками есть рельеф (TBL ten);
- щит: у ворота без шнуровки — по зазору под кромкой (edge_kit.SHIELD_GAP_DEFAULT_MM, 4 мм — решение пользователя по
  NJD/TBL), масштаб 0,68 (как NJD и TBL); зазор источника печатается для справки;
- каска (zones) и краги ("gloves") — строки stockteamequipmenttable NHL 27: (era 2, вариант формы) → (era 2, −1) →
  (era −1, −1); зоны 4–9 пустые (0, 0, 0) — цветом зоны 1 (так у полных строк); цветной (не серый) цвет экипировки,
  который расходится с тканью свитера, а цвет палитры клуба NHL 27 рядом с ним есть в свитере, — цветом палитры
  (пользователь, 21.10, TBL: каска (18, 46, 77) при ткани (26, 37, 93));
- палитра клуба (nhl24_team_colors.json) — только предложение (у TBL палитра NHL 27 давала тёмный второй цвет, нужен был
  белый): пишется только с --write-palette;
- шорты, гетры, наклейка на шлем — как у NJD и TBL (одобрены): pant = source, sock = auto, helmet_logo = source
  (реклама NHL 27 на шлеме; эмблема образца — legacy, kitport present показывает обе);
- default не ставит никогда (это одобрение пользователя), label не задаёт (подпись по умолчанию «Home (NHL 27)»).
"""
import json
import os
import sys

import numpy as np

from . import core

LEG_OUT = os.path.join(core.LEGACY_DATA, "out")                    # база Legacy до накладки NHL 24
CLUBS_TOML = os.path.join(core.TOOLS, "fb", "edge_clubs.toml")
HELMETS = os.path.join(core.TOOLS, "legacy_data", "nhl24_helmets.json")
COLORS = os.path.join(core.TOOLS, "legacy_data", "nhl24_team_colors.json")
SLOT_KITS = ("home", "away")
EDGE_KIT = {"home": "edge_home", "away": "edge_away"}
SHIELD_SCALE = 0.68              # щит NHL у форм NHL 27: как у NJD и TBL (одобрены 21.10; MIN — 0,76, «довольно большой»
#                                  при 0,88 — пользователь)
LACE_BOX = (0.022, 1.565, 1.605)  # |x − середины|, y от, y до (м, сетка NHL 24): под щитом посередине переда — шнуровка
#                                   или вставка у lace (MIN, TOR), ткань у plain (NJD, TBL, BOS)
LACE_REF_X = (0.05, 0.09)        # |x| полосы ткани по бокам на той же высоте — с ней сравнивается
LACE_FRAC = 0.15                 # доля «не ткани» под щитом — больше: шнуровка
COLOR_DIFF = 45                  # max |ΔR, ΔG, ΔB| — другой цвет (как у kitport check и edge_kit.trim_profile)
YOKE_TOP_X = (0.12, 0.17)        # |x| верха плеч (у шеи — кромка, дальше — сустав): цвет кокетки
YOKE_ARM_X = (0.25, 0.30)        # |x| верха рукава за плечевым суставом: кокетка «на плечо»
UNDER_Y = (1.50, 1.56)           # м: спина у середины под кокеткой и над полосами груди — с ней сравнивается цвет кокетки и
#                                  рукава (22.10, MTL дом: на 1,30–1,45 м синяя полоса — генератор видел кокетку и «другой» рукав)
YOKE_SIDE_BLEND = 0.10           # м: кокетка «на плечо» — край на руке прямой наискосок (edge_kit.YOKE_SIDE_BLEND; MTL, BUF, DAL)
LAPEL_SRC = ((30.0, 60.0), (120.0, 150.0), (0.020, 0.026))   # |θ| спереди сбоку, сзади; м от края: лацканы у шнуровки
#                                  (edge_kit.LAPEL_SRC) — один цвет и спереди, и сзади, не цвет за ободом (4,5–6 см)
SLEEVE_X = (0.30, 0.34)          # |x| кольца рукава ниже плечевого сустава (до полос у локтя): цвет рукава. Не цвет ткани —
#                                  armhole_split = "full" (VGK 22.10: серые рукава, по полю шва NHL 24 граница зубцами)
EQ_HELMET, EQ_GLOVES = 7, 4      # equipment шлема и краг (значения с rangelow, как в nhl24.py)
EQ_NEAR_PAL = 6.0                # ближе к цвету палитры — тот же цвет
EQ_FAR_PAL = 60.0                # дальше — не оттенок этого цвета палитры
EQ_JERSEY_GAIN = 6.0             # цвет палитры ближе к ткани свитера на столько — подменять
NEUTRAL = 25                     # max − min меньше — серый (чёрный, белый): не подменяется
BNM_SIGMA = 2.0                  # px 2048: сглаживание _base_normal перед замером наклона (плетение ткани — мельче)
BNM_RATIO = (4.0, 6.0)           # наклон у края нашивок / у ткани: больше второго — рельеф нашивок «запечён» (TBL ten — 7,8;
#                                  без него 0,9–3,4: NJD, TBL eleven, BOS, 21.10); между — проверить
LETTER_EA_PX = 24                # px карты номеров 256²: место буквы (зона 5) у EA 15 × 15–17, у заготовок Custom SEA и VGK
#                                  36 × 34 (зоны MIN — name_zones_from); у наших форм Юты 1_104_x — 15 × 16 (карта EA PIT)
MERGE_NEAR = 0.02                # доля развёртки: часть вне правил ближе к гербу — его часть (merge_near; UTA выезд «UTAH»:
#                                  между буквами 0,005–0,010, до прочих нашивок — от 0,05)
MERGE_NEAR_MIN_PX = 2000         # px 2048²: меньше — не буква (обрезки, черта у края развёртки)
CLEAR_FRONT, CLEAR_BACK = (30, 60), (120, 180)   # |θ|: бока спереди и спина — ткань за кромкой (trim_clear)


def say(*a):
    print(*a, flush=True)


# ---------------------------------------------------------------- данные

def nhl24_mod():
    """tools/legacy_data/nhl24.py (реестр, база Legacy, модель шлемов)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("nhl24", os.path.join(core.TOOLS, "legacy_data", "nhl24.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def club_folder(code):
    from fb.kit_batch import club                   # CLUBS и NEW_CLUBS (UTA → utah: клуба нет в NHL 24)
    f = club(code)
    if f is None:
        sys.exit(f"{code}: не знаю клуба (fb.kit_batch.CLUBS, NEW_CLUBS)")
    return f[0]


def letter_zone_px(kit):
    """Место буквы капитана (зона 5 карты номеров 256²) формы Legacy kit (S_A_V: из cache: игры, иначе из архивов —
    fb.jersey_mesh.unpack_kit, в edgekit/cur_kits, как у стадии slot) -> (ширина, высота) px или None."""
    from PIL import Image
    from fb import jersey_mesh as J
    d = os.path.join(core.EDGE_WORK, "cur_kits", kit)
    if not os.path.exists(os.path.join(d, "kit.json")):
        J.unpack_kit(kit, d)
    a = np.asarray(Image.open(os.path.join(d, "name_cm.png")).convert("RGBA"))
    ys, xs = np.nonzero((a[..., 0] > 128) & (a[..., 1] > 128) & (a[..., 2] == 5))
    return (int(xs.max() - xs.min() + 1), int(ys.max() - ys.min() + 1)) if len(xs) else None


def nhl27_db():
    from roster import nhl27 as N
    return N, N.open_db(os.path.join(core.GAME, "work", "nhl27", "db", "nhl_game.db"))


def nhl27_team(N, legacy_team):
    return {v: k for k, v in N.NHL_SLOT.items()}[legacy_team]


def nhl27_kits(db, team):
    """{0: вариант дома, 1: вариант выезда} — формы по умолчанию NHL 27 (стиль 2, isdefault, locstring 0 / 1)."""
    J = "stockteamjerseys"
    out = {}
    for r in db.live_rows(J):
        if db.get(J, "teamid", r) == team and db.value(J, "style", r) == 2 and db.value(J, "isdefault", r) \
                and db.value(J, "locstring", r) in (0, 1):
            out[db.value(J, "locstring", r)] = db.value(J, "variant", r)
    return out


def rgb(v):
    return [int(v) >> 16 & 255, int(v) >> 8 & 255, int(v) & 255]


def nhl27_equipment(db, team, equipment):
    """[(era, variant, brand, [9 зон RGB])] строк stockteamequipmenttable клуба. Поля зон в таблице NHL 27 идут не по
    порядку — по имени zone1…zone9, цвет — упакованный 0xRRGGBB."""
    E = "stockteamequipmenttable"
    out = []
    for r in db.live_rows(E):
        if db.value(E, "team", r) == team and db.value(E, "equipment", r) == equipment:
            out.append((db.value(E, "era", r), db.value(E, "variant", r), db.value(E, "brand", r),
                        [rgb(db.value(E, f"zone{i}", r)) for i in range(1, 10)]))
    return out


def eq_pick(rows, variant):
    """Строка экипировки формы: (era 2, вариант формы) → (era 2, −1) → (era −1, −1); бренд −1. -> (зоны, откуда)."""
    for era, v in ((2, variant), (2, -1), (-1, -1)):
        r = next((x for x in rows if x[0] == era and x[1] == v and x[2] == -1), None)
        if r is not None:
            return [list(z) for z in r[3]], f"era {era}, variant {v}"
    return None, "нет строки"


def palette27(db, team):
    C = "stockteamcolorstable"
    rows = sorted((db.value(C, "colorid", r), rgb(db.value(C, "color", r))) for r in db.live_rows(C)
                  if db.value(C, "team", r) == team)
    return [c for _, c in rows]


_TEX = {}


def tex(folder, kit, layer, size=None):
    """Текстура свитера источника NHL 27 из дампа (по каталогу, kitport.survey.tex) → float RGBA (size² — уменьшено)."""
    from . import survey
    key = (folder, kit, layer, size)
    if key not in _TEX:
        im = survey.tex("nhl27", f"content/character/skater/league/nhl/{folder}/adidas/{kit}/"
                                 f"jersey_adidas_{folder}_{kit}_{layer}")
        if size:
            from PIL import Image
            im = im.resize((size, size), Image.BOX)
        _TEX[key] = np.asarray(im).astype(np.float64)
    return _TEX[key]


_N24 = {}


def n24_outer():
    """Наружная оболочка свитера NHL 24 (без подкладки ворота; развёртка у NHL 27 та же) и её P на развёртке 1024²."""
    if not _N24:
        from scipy.sparse import coo_matrix
        from scipy.sparse.csgraph import connected_components
        from fb import kit3d
        from . import survey
        a = np.load(survey.mesh_cache())
        pos, uv, tri = a["pos"], a["uv"], a["tri"]
        _, wid = np.unique(np.round(pos / 1e-4).astype(np.int64), axis=0, return_inverse=True)
        wid = wid.ravel()
        T = wid[tri]
        n = int(wid.max()) + 1
        r, c = np.concatenate([T[:, 0], T[:, 1], T[:, 2]]), np.concatenate([T[:, 1], T[:, 2], T[:, 0]])
        _, comp = connected_components(coo_matrix((np.ones(len(r)), (r, c)), shape=(n, n)), directed=False)
        tc = comp[T[:, 0]]
        M = {"pos": pos, "uv": uv, "tri": tri[tc == np.bincount(tc).argmax()]}
        tid, bar = kit3d.raster_uv(M, 1024)
        ys, xs = np.nonzero(tid >= 0)
        P = (bar[ys, xs][:, :, None] * M["pos"][M["tri"][tid[ys, xs]]]).sum(1)
        _N24.update(M=M, ys=ys, xs=xs, P=P)
    return _N24


# ---------------------------------------------------------------- решения

class Decision:
    def __init__(self, field, value, sure, why):
        self.field, self.value, self.sure, self.why = field, value, sure, why


def median_c(a):
    return np.median(a, 0) if len(a) else np.full(3, np.nan)


def differs(a, b):
    return bool(np.abs(np.asarray(a) - np.asarray(b)).max() >= COLOR_DIFF)


HEM_WIN = 0.40                     # м над краем низа — окно замера полос
HEM_BODY = (0.30, 0.40)            # м: здесь — ткань (её цвет); ниже — полосы низа (LAK — до 22 см: серебро, белое, серебро)
HEM_RING = 0.5                     # доля круга туловища другого цвета — полоса низа
HEM_TORSO_X = 0.20                 # м: |x| — туловище (рукава в замер полос низа не берутся)
HEM_MARGIN = 0.04                  # м: зона низа «от края» — выше верха полос (переход fb.hem.HEM_BLEND 3 см + 1 см)


def hem_band_top(folder, kit):
    """Верх полос низа источника над краем низа (м, сетка NHL 24): самое высокое место не цвета ткани у низа."""
    from fb import hem
    a = np.load(survey_mesh())
    m = {"pos": a["pos"], "uv": a["uv"], "tri": a["tri"]}
    g = n24_outer()
    P, ys, xs = g["P"], g["ys"], g["xs"]
    _, dh = hem.hem_coords(P, hem.hem_curve(m))
    b = tex(folder, kit, "base_color", 1024)[ys, xs, :3]
    sel = (dh > 0) & (dh < HEM_WIN) & (np.abs(P[:, 0]) < HEM_TORSO_X)   # только туловище: рукава висят у низа (LAK: 25 см)
    body = median_c(b[sel & (dh > HEM_BODY[0]) & (dh < HEM_BODY[1])])   # ткань — выше полос (у LAK полосы до 22 см)
    diff = sel & (np.abs(b - body).max(1) >= COLOR_DIFF)
    # полоса — то, что опоясывает туловище (не меньше HEM_RING по кругу): герб или нашивка спереди — не полоса (LAK:
    # без этого «верх полос» — 25 см)
    k = (dh[sel] / 0.005).astype(int)
    tot = np.bincount(k, minlength=int(HEM_WIN / 0.005) + 1)
    hit = np.bincount(k, weights=diff[sel].astype(float), minlength=int(HEM_WIN / 0.005) + 1)
    tot[int(HEM_BODY[0] / 0.005):] = 0                   # выше начала зоны ткани полос не ищем
    ring = np.nonzero((tot > 20) & (hit >= HEM_RING * np.maximum(tot, 1)))[0]
    return float((ring.max() + 1) * 0.005) if len(ring) else 0.0


def survey_mesh():
    from . import survey
    return survey.mesh_cache()


def look_kit(folder, kit):
    """Ворот, кокетка, ткань одной формы источника по основе на сетке NHL 24 -> dict."""
    g = n24_outer()
    P, ys, xs = g["P"], g["ys"], g["xs"]
    b = tex(folder, kit, "base_color", 1024)[ys, xs, :3]
    x, y, z = P[:, 0], P[:, 1], P[:, 2]
    xc = float(np.median(x[(y > 1.60) & (y < 1.64) & (z > 0.05) & (np.abs(x) < 0.03)]))
    front = z > 0.05
    lace = front & (np.abs(x - xc) < LACE_BOX[0]) & (y > LACE_BOX[1]) & (y < LACE_BOX[2])
    ref = front & (np.abs(x) > LACE_REF_X[0]) & (np.abs(x) < LACE_REF_X[1]) & (y > LACE_BOX[1]) & (y < LACE_BOX[2])
    ref_c = median_c(b[ref])
    lace_frac = float((np.abs(b[lace] - ref_c).max(1) >= COLOR_DIFF).mean())
    back = (z < -0.05) & (np.abs(x) < 0.08) & (y > 1.30) & (y < 1.45)
    body = median_c(b[back])
    body_uniform = float((np.abs(b[back] - body).max(1) < 20).mean())
    # кромка видна? верх ворота сзади посередине (3 мм) против ткани на 4,5–6,5 см ниже (BOS дом: чёрное на чёрном)
    bk = (z < -0.03) & (np.abs(x) < 0.04)
    ytop = float(y[bk].max())
    trim_top = median_c(b[bk & (y > ytop - 0.003)])
    trim_below = median_c(b[bk & (y < ytop - 0.045) & (y > ytop - 0.065)])

    def top_of(xr):                                  # верх плеч / рукава: самые высокие точки по полосам |x|
        sel = (np.abs(x) > xr[0]) & (np.abs(x) < xr[1]) & (np.abs(z) < 0.06)
        if not sel.any():
            return np.full(3, np.nan), 0.0
        bins = np.round(np.abs(x[sel]) / 0.005).astype(int)
        yy = y[sel]
        top = np.zeros(sel.sum(), bool)
        for k in np.unique(bins):
            m = bins == k
            top[m] = yy[m] > yy[m].max() - 0.012
        cc = b[sel][top]
        c = median_c(cc)
        return c, float((np.abs(cc - c).max(1) < COLOR_DIFF).mean())
    yoke_c, yoke_u = top_of(YOKE_TOP_X)
    arm_c, _ = top_of(YOKE_ARM_X)
    sleeve_c = median_c(b[(np.abs(x) > SLEEVE_X[0]) & (np.abs(x) < SLEEVE_X[1])])
    # ткань под кокеткой (UNDER_Y): с ней сравниваются кокетка и рукав — середина спины ниже бывает полосой груди (MTL дом)
    under = median_c(b[(z < -0.05) & (np.abs(x) < 0.08) & (y > UNDER_Y[0]) & (y < UNDER_Y[1])])
    yoke_on = differs(yoke_c, under) and yoke_u > 0.7
    # полоса под кокеткой (BUF выезд, 22.10: золотая) — 2–8 мм под нижним краем цвета кокетки у середины спины
    stripe_c = np.full(3, np.nan)
    if yoke_on:
        bk_ = (z < -0.05) & (np.abs(x) < 0.10) & (y > 1.50)
        yl = y[bk_ & (np.abs(b - yoke_c).max(1) < COLOR_DIFF)]
        if len(yl):
            y0_ = float(np.percentile(yl, 2))
            stripe_c = median_c(b[bk_ & (y < y0_ - 0.002) & (y > y0_ - 0.008)])
    stripe = yoke_on and bool(np.isfinite(stripe_c).all()) and differs(stripe_c, yoke_c) and differs(stripe_c, under)
    return {"xc": xc, "lace_frac": lace_frac, "ref": ref_c, "body": body, "body_uniform": body_uniform,
            "sleeve_c": sleeve_c, "sleeve_other": differs(sleeve_c, under), "under": under,
            "yoke_c": yoke_c, "yoke_uniform": yoke_u, "arm_c": arm_c,
            "yoke": yoke_on, "on_arm": not differs(arm_c, yoke_c), "stripe": stripe, "stripe_c": stripe_c,
            "trim_c": trim_top, "trim_below": trim_below, "trim_visible": differs(trim_top, trim_below)}


def lapel_look(folder, kit):
    """Лацканы ворота со шнуровкой (edge_kit.collar_lapel): цвет между кромкой и ободом спереди сбоку и сзади (LAPEL_SRC)
    и за ободом. -> (цвет спереди, сзади, за ободом)."""
    from fb import jersey_hybrid as Hy
    g = n24_outer()
    if "ring" not in g:
        w = Hy.Welded(g["M"])
        ring = w.neck()
        zc = float(w.P[ring, 2].mean())
        g["ring"] = (Hy.ring_dist(g["P"], Hy.ring_polyline(w, ring)), Hy.theta_of(g["P"], zc))
    d, th = g["ring"]
    ath = np.abs(th)
    b = tex(folder, kit, "base_color", 1024)[g["ys"], g["xs"], :3]
    (f0, f1), (b0, b1), (d0, d1) = LAPEL_SRC
    lap = (d > d0) & (d < d1)
    return (median_c(b[lap & (ath > f0) & (ath < f1)]), median_c(b[lap & (ath > b0) & (ath < b1)]),
            median_c(b[(d > 0.045) & (d < 0.06) & (ath > f0) & (ath < b1)]))


def font_plate(kit, folder):
    """Фамилия на подложке (22.10, PHI): строки букв атласа шрифта источника (верхние 19 % высоты, до столбца C и A —
    80 %) в основном непрозрачны (у прочих клубов там прозрачно между буквами)."""
    from . import survey
    try:
        im = survey.tex("nhl27", f"content/character/skater/league/nhl/{folder}/adidas/{kit}/font_adidas_{folder}_{kit}_color")
    except (KeyError, ValueError, OSError):
        return False
    a = np.asarray(im)
    if a.ndim < 3 or a.shape[2] < 4:
        return False
    H, W = a.shape[:2]
    return bool(np.median(a[:int(0.19 * H), :int(0.8 * W), 3]) > 200)


def ea_yoke_rgb(kit):
    """Цвет кокетки EA-формы Legacy у её семени (edge_kit.yoke_polygon: строка 0,53, столбец 0,37 развёртки 1024), если он
    не цвет середины спины (edge_kit.BODY_BOX); у формы нет кокетки — None."""
    from PIL import Image
    from fb import edge_kit as E, pilot
    if not kit:
        return None
    im = np.asarray(Image.open(os.path.join(pilot.unpack(kit), "jersey_cm.png")).convert("RGB")
                    .resize((1024, 1024))).astype(np.float64)
    seed = im[int(0.53 * 1024), int(0.37 * 1024)]
    u0, v0, u1, v1 = E.BODY_BOX
    body = np.median(im[int(v0 * 1024):int(v1 * 1024), int(u0 * 1024):int(u1 * 1024)].reshape(-1, 3), axis=0)
    return [int(round(v)) for v in seed] if differs(seed, body) else None


def beyond_trim(folder, kit):
    """Ткань сразу за кромкой источника (сетка NHL 24, основа) — спереди сбоку (|θ| CLEAR_FRONT) и сзади (CLEAR_BACK):
    медианы от edge_kit.TRIM_CLEAR_GAP за кромкой (сплошная полоса цвета кромки или полоса шаблона ворота
    edge_kit.BAND_KNOTS — что шире) и на TRIM_CLEAR дальше, как замер edge_kit.trim_body_by_angle. -> {front, back}."""
    from fb import edge_kit as E, jersey_hybrid as Hy
    g = n24_outer()
    if "ring" not in g:
        w = Hy.Welded(g["M"])
        ring = w.neck()
        zc = float(w.P[ring, 2].mean())
        g["ring"] = (Hy.ring_dist(g["P"], Hy.ring_polyline(w, ring)), Hy.theta_of(g["P"], zc))
    d, th = g["ring"]
    b = tex(folder, kit, "base_color", 1024)[g["ys"], g["xs"], :3]
    col = median_c(b[d < 0.003])
    pr = E.trim_profile(d, th, np.linalg.norm(b - col, axis=1) < 60)
    ath = np.abs(th)
    w0 = np.maximum(np.interp(ath, pr["angles"], pr["width"]), np.interp(ath, *zip(*E.BAND_KNOTS))) + E.TRIM_CLEAR_GAP
    ring_ok = (d > w0) & (d < w0 + E.TRIM_CLEAR)
    return {what: median_c(b[ring_ok & (ath >= a0) & (ath <= a1)])
            for what, (a0, a1) in (("front", CLEAR_FRONT), ("back", CLEAR_BACK))}


def yoke_kind(c):
    lum = float(np.mean(c))
    if lum < 70 and c[1] > c[0] + 15:
        return "green"
    if lum < 70 and np.max(c) - np.min(c) < 45:
        return "dark"
    return None


def crest_parts(code, folder, kit):
    """(частей герба, рельеф в _base_normal: средний наклон у края нашивок ±6 px и у ткани в 40–60 px от них — после
    сглаживания BNM_SIGMA, чтобы плетение не мешало)."""
    from scipy import ndimage as ndi
    from fb import kit_hybrid
    comp, base = tex(folder, kit, "color"), tex(folder, kit, "base_color")
    defaults, rules = kit_hybrid.load_rules(kit_hybrid.RULES, code, kit, [])
    lab, patches = kit_hybrid.find_patches(comp, base, defaults)
    H = lab.shape[0]
    found = []
    for lid, sl, area in patches:
        yy, xx = np.nonzero(lab[sl] == lid)
        found.append((kit_hybrid._match(lab, lid, sl, rules, defaults), (xx.mean() + sl[1].start) / H,
                      (yy.mean() + sl[0].start) / H, int(area)))
    n = sum(1 for f in found if f[0] == "crest")
    # части вне правил рядом с гербом (UTA выезд, 22.10: «UTAH» — четыре буквы, U и H дальше match_radius) — «crest~»
    grp = [p for p, f in zip(patches, found) if f[0] == "crest"]
    free = [p for p, f in zip(patches, found) if f[0] is None and p[2] >= MERGE_NEAR_MIN_PX]
    if grp and free:
        near_ids = {p[0] for p in kit_hybrid.near_parts(lab, grp, free, MERGE_NEAR)} - {p[0] for p in grp}
        found = [("crest~",) + f[1:] if p[0] in near_ids else f for p, f in zip(patches, found)]
    sponsors = {k for k, r in rules.items() if r.get("sponsor")}
    try:
        nm = tex(folder, kit, "base_normal")[..., :2] / 127.5 - 1.0
    except (KeyError, ValueError, OSError):
        return n, None, None, found, sponsors
    m = ndi.binary_fill_holes(ndi.binary_closing(np.abs(comp[..., :3] - base[..., :3]).sum(-1) > 30, iterations=3))
    g = sum(np.hypot(*np.gradient(ndi.gaussian_filter(nm[..., i], BNM_SIGMA))) for i in range(2))
    edge = ndi.binary_dilation(m, iterations=6) & ~ndi.binary_erosion(m, iterations=6)
    far = ndi.binary_dilation(m, iterations=60) & ~ndi.binary_dilation(m, iterations=40)
    s_edge = float(g[edge].mean()) if edge.any() else 0.0
    s_far = float(g[far].mean()) if far.any() else 0.0
    return n, s_edge, s_far, found, sponsors


def jersey_dist(cols, c):
    """Насколько цвет c есть в свитере: 0,5-й процентиль расстояния текселей до c."""
    return float(np.percentile(np.linalg.norm(cols - np.asarray(c, float), axis=1), 0.5))


def palette_fix(zones, palette, cols, what):
    """Зоны экипировки: цветной цвет, который расходится с тканью, → ближайший цвет палитры клуба (если он в свитере
    есть). -> (зоны, [замены])."""
    out, notes = [list(z) for z in zones], []
    cache = {}
    for i, z in enumerate(zones):
        key = tuple(z)
        if key not in cache:
            cache[key] = None
            if max(z) - min(z) >= NEUTRAL and palette:
                p = min(palette, key=lambda q: np.linalg.norm(np.subtract(q, z)))
                d = float(np.linalg.norm(np.subtract(p, z)))
                dz, dp = jersey_dist(cols, z), jersey_dist(cols, p)
                if EQ_NEAR_PAL < d < EQ_FAR_PAL and dp + EQ_JERSEY_GAIN < dz:
                    cache[key] = list(p)
                    notes.append(f"{what} {tuple(z)} → {tuple(p)} (палитра NHL 27): до ткани {dz:.0f} против {dp:.0f}")
                elif d >= EQ_NEAR_PAL:
                    notes.append(f"{what} {tuple(z)}: оставлен (ближайший цвет палитры {tuple(p)} — Δ {d:.0f}, "
                                 f"до ткани {dz:.0f} / {dp:.0f})")
        if cache[key] is not None:
            out[i] = cache[key]
    return out, notes


def fill_zones(zones):
    """Зоны 4–9 строки NHL 27 пустые (0, 0, 0) — цветом зоны 1: так у всех полных строк шлема (NJD, TBL, BOS era −1),
    а чёрные детали на белой каске Legacy рисовал бы иначе. -> (зоны, заполнено ли)."""
    if all(z == [0, 0, 0] for z in zones[3:9]):
        return zones[:3] + [list(zones[0])] * 6, True
    return zones, False


# ---------------------------------------------------------------- реестр

def registry_plan(L, code):
    """Номера edge_home / edge_away и jerseyindex форм клуба в реестре. -> (новый реестр, строки отчёта, есть ли
    изменения)."""
    import copy
    _, db = L.open_db(L.OUT)
    team, art = L.check_club(db, code)
    rows = L.rows_of(db)
    reg = copy.deepcopy(L.load_registry())
    base_ji = max(r["jerseyindex"] for r in rows if r["teamid"] == team)
    notes, changed = [], False
    try:
        cache = core.cache_dir()
    except SystemExit:
        cache = None
    man = os.path.join(core.LEGACY_DATA, "nhl24", "manifest.json")
    in_man = {(k["club"], k["kit"]) for k in json.load(open(man, encoding="utf-8"))["kits"]} if os.path.exists(man) else set()

    def installed(k):
        rel = L.KIT_FILES["jersey"].format(s=k.get("style", 1), a=k["art"], v=k["variant"])
        if cache:
            return os.path.exists(os.path.join(cache, *rel.split("/")))
        return (k["club"], k["kit"]) in in_man
    helm = {(x[0], x[1]) for x in L.club_equipment(db, L.eq_low(db), team) if x[2] == L.EQ_HELMET}
    for kit in EDGE_KIT.values():
        if any(k["club"] == code and k["kit"] == kit for k in reg["kits"]):
            continue
        v = next((v for v in range(32) if L.variant_free(art, v, rows, reg, 0, helm)), None)
        if v is None:
            sys.exit(f"{code} {kit}: нет свободного варианта стиля 0")
        reg["kits"].append(dict(club=code, kit=kit, teamid=team, style=0, art=art, variant=v, fevariant=v,
                                jerseyindex=99, locstring=6))
        notes.append(f"{kit}: новый номер 0_{art}_{v} (как nhl24.py alloc --style 0)")
        changed = True
    mine = sorted((k for k in reg["kits"] if k["club"] == code), key=lambda k: k["jerseyindex"])
    inst = [k for k in mine if installed(k)]
    edge = [k for k in mine if k["kit"] in EDGE_KIT.values() and k not in inst]
    rest = [k for k in mine if k not in inst and k not in edge]
    edge.sort(key=lambda k: list(EDGE_KIT.values()).index(k["kit"]))
    for i, k in enumerate(inst + edge + rest):
        want = base_ji + 1 + i
        st = "стоит в игре" if k in inst else "не стоит"
        if k["jerseyindex"] != want:
            if k in inst:
                sys.exit(f"{code} {k['kit']}: поставленная форма сменила бы jerseyindex {k['jerseyindex']} → {want} — "
                         "так нельзя (сдвинет формы в сейвах); разберитесь руками")
            notes.append(f"{k['kit']:9} {k.get('style', 1)}_{k['art']}_{k['variant']}: jerseyindex "
                         f"{k['jerseyindex'] if k['jerseyindex'] != 99 else '—'} → {want} ({st})")
            k["jerseyindex"] = want
            changed = True
        else:
            notes.append(f"{k['kit']:9} {k.get('style', 1)}_{k['art']}_{k['variant']}: jerseyindex {want} ({st})")
    notes.insert(0, f"формы базы Legacy — jerseyindex 0…{base_ji}; дальше — поставленные, edge, не поставленные"
                    + ("" if cache else " (cache: игры не найден — «стоит» по манифесту накладки)"))
    return reg, notes, changed


# ---------------------------------------------------------------- профиль

def propose(code):
    """-> (решения [Decision], данные для записи)."""
    N, db27 = nhl27_db()
    L = nhl24_mod()
    folder = club_folder(code)
    team_leg, art = L.CLUBS[code]
    team27 = nhl27_team(N, team_leg)
    from . import survey
    v27 = nhl27_kits(db27, team27)
    if 0 not in v27 or 1 not in v27:
        sys.exit(f"{code}: в базе NHL 27 нет формы по умолчанию дома или выезда")
    src = {"home": survey.WORDS.get(v27[0]), "away": survey.WORDS.get(v27[1])}
    if None in src.values():
        sys.exit(f"{code}: вариант {v27} — нет слова папки в kitport.survey.WORDS")
    D = []
    D.append(Decision("source", "nhl27", True, "текстуры — NHL 27 (дамп PS5)"))
    D.append(Decision("source_kits", dict(src), True,
                      f"формы по умолчанию NHL 27: дом — вариант {v27[0]}, выезд — {v27[1]} (stockteamjerseys стиль 2)"))
    # образцы Legacy
    _, dbl = L.open_db(L.OUT)
    rows = [r for r in L.rows_of(dbl) if r["teamid"] == team_leg and r["style"] == 1]
    legacy = {}
    for kit, loc in (("home", 0), ("away", 1)):
        r = next((r for r in rows if r["locstring"] == loc), None)
        if r is None:                                    # уже ушла в 6 «(EA)»: тогда — по умолчанию этого цвета
            r = next((r for r in rows if r["isdefault"] and r["islightcolor"] == loc), None)
        legacy[kit] = f"1_{art}_{r['variant']}" if r else None
    D.append(Decision("legacy", legacy, all(legacy.values()),
                      "EA-формы клуба в базе Legacy (out): стиль 1, locstring 0 / 1"))
    # ворот, кокетка, ткань
    look = {k: look_kit(folder, src[k]) for k in SLOT_KITS}
    lace = {k: look[k]["lace_frac"] > LACE_FRAC for k in SLOT_KITS}
    collar = "lace" if all(lace.values()) else "plain"
    fr = ", ".join(f"{k} {look[k]['lace_frac']:.2f}" for k in SLOT_KITS)
    D.append(Decision("collar", collar, len(set(lace.values())) == 1 and
                      all(abs(look[k]["lace_frac"] - LACE_FRAC) > 0.08 for k in SLOT_KITS),
                      f"под щитом посередине переда не цвет ткани: {fr} (порог {LACE_FRAC}; шнуровка — больше)"
                      + ("" if len(set(lace.values())) == 1 else " — у форм по-разному, профиль один: проверить")))
    yoke = {k: look[k]["yoke"] for k in SLOT_KITS}
    yk = {}
    for k in SLOT_KITS:
        L_ = look[k]
        D.append(Decision(f"кокетка {k}", ("на плечо" if L_["on_arm"] else "до плеча") if L_["yoke"] else "нет",
                          not L_["yoke"] or L_["yoke_uniform"] > 0.85,
                          f"верх плеч {np.round(L_['yoke_c']).astype(int).tolist()} (однороден на "
                          f"{L_['yoke_uniform']:.0%}), ткань под кокеткой {np.round(L_['under']).astype(int).tolist()}, "
                          f"верх рукава {np.round(L_['arm_c']).astype(int).tolist()}"))
        if L_["yoke"]:
            yk[k] = yoke_kind(L_["yoke_c"])
    prof = {"source": "nhl27", "source_kits": src}
    arm = any(look[k]["on_arm"] for k in SLOT_KITS if yoke[k])
    if any(yoke.values()) and arm:
        # кокетка «на плечо» (22.10, MTL, BUF, DAL; агент yoke, docs/kitport.md §12): цвет — RGB источника (green / dark
        # узнают не все), край спины — по своей EA-форме клуба (у неё кокетка тоже на плече; как MIN и NJD — спина по EA),
        # боков EA нет — шапка на руке кончается краем, прямой наискосок от переда к спине (yoke_side_blend)
        yc = np.median([look[k]["yoke_c"] for k in SLOT_KITS if yoke[k]], axis=0)
        prof["yoke_color"] = [int(round(v)) for v in yc]
        ycs = {k: [int(round(v)) for v in look[k]["yoke_c"]] for k in SLOT_KITS if yoke[k]}
        if len(ycs) > 1 and differs(*ycs.values()):      # у форм кокетки разного цвета (22.10, EDM: дома оранжевая, в гостях
            prof["yoke_color"] = ycs                     # синяя; среднее не узнавало ни ту, ни другую) — таблицей по форме
        ea = {k: ea_yoke_rgb(legacy[k]) for k in SLOT_KITS if yoke[k]}
        prof["yoke"] = {k: (legacy[k] if v is not None else "1_14_3") for k, v in ea.items()}
        got = [v for v in ea.values() if v is not None]
        prof["yoke_shape_color"] = got[0] if got else "green"
        shp = {k: (v if v is not None else "green") for k, v in ea.items()}
        if len(shp) > 1 and len({json.dumps(v) for v in shp.values()}) > 1 and                 not (all(isinstance(v, list) for v in shp.values()) and not differs(*shp.values())):
            prof["yoke_shape_color"] = shp               # и у EA-форм (край спины) — своей формы
        prof["yoke_side_blend"] = YOKE_SIDE_BLEND
        # «проверить» всегда: у NHL 27 кокетка adidas одна и та же (NJD, BUF, MTL, DAL — шапка до одного места на руке), а у
        # NJD пользователь выбрал «до плеча» (бока MIN 1_14_3, 21.10) — решение по листу, не по текстуре
        D.append(Decision("yoke", prof["yoke"], False,
                          f"кокетка «на плечо» (тип MTL, §12.1): цвет {prof['yoke_color']}, край спины — EA-форма "
                          f"{prof['yoke']} (её кокетка {prof['yoke_shape_color']}), край на руке — прямая "
                          f"(yoke_side_blend {YOKE_SIDE_BLEND})" + ("" if len(got) == len(ea) else
                                                                   " — у EA-формы кокетки нет: спина по MIN 1_14_3")
                          + "; «до плеча», как NJD, — yoke = 1_14_3, yoke_shape_color = green, без yoke_side_blend"))
        st = [k for k in SLOT_KITS if yoke[k] and look[k]["stripe"]]
        if st:
            prof["yoke_stripe"] = "source"
        D.append(Decision("yoke_stripe", prof.get("yoke_stripe", "—"), True, ", ".join(
            f"{k}: под кокеткой сзади {np.round(look[k]['stripe_c']).astype(int).tolist()}" for k in SLOT_KITS if yoke[k])
            + (" — полоса другого цвета (BUF выезд): цвет и ширина по источнику" if st else "")))
    elif any(yoke.values()):
        kinds = {v for v in yk.values() if v}
        kind = kinds.pop() if len(kinds) == 1 else None
        prof["yoke_color"] = kind or [int(round(v)) for v in np.median([look[k]["yoke_c"] for k in SLOT_KITS if yoke[k]],
                                                                       axis=0)]
        D.append(Decision("yoke_color", prof["yoke_color"], kind is not None,
                          f"цвет кокетки {yk}: green — тёмно-зелёная (MIN), dark — чёрная (NJD); другой — [R, G, B] "
                          "источника (edge_kit.yoke_mask, 22.10)" if kind is None else f"цвет кокетки — {kind}"))
        prof["yoke"] = {k: "1_14_3" for k in SLOT_KITS if yoke[k]}
        prof["yoke_shape_color"] = "green"
        arm = any(look[k]["on_arm"] for k in SLOT_KITS if yoke[k])
        D.append(Decision("yoke", prof["yoke"], not arm,
                          "бока кокетки «до плеча» — с EA MIN 1_14_3 (как NJD, пользователь 21.10)" if not arm else
                          "кокетка заходит на руку (тип MTL, §12.1): бока 1_14_3 — заготовка, нужен yoke_side_blend"))
    if any(yoke.values()):                               # у NHL 27 в кокетке сетки ямок нет (MTL, DAL, BUF, 22.10)
        prof["yoke_mesh"] = False
    # рукав другого цвета, чем ткань (VGK: серые рукава; DET выезд: красные) — граница по шву проймы Edge целиком
    other = [k for k in SLOT_KITS if look[k]["sleeve_other"]]
    if other:
        prof["armhole_split"] = "full"
    D.append(Decision("armhole_split", prof.get("armhole_split", "—"), True,
                      "рукав ниже плеча / ткань: " + ", ".join(
                          f"{k} {np.round(look[k]['sleeve_c']).astype(int).tolist()} / "
                          f"{np.round(look[k]['body']).astype(int).tolist()}" for k in SLOT_KITS)
                      + (" — рукав другого цвета: граница по шву проймы целиком (VGK, DET 22.10: по полю шва — зубцы)"
                         if other else "")))
    # фамилия, номер, буква: у заготовок Custom (SEA, VGK — art ≥ 100) зоны крупнее EA — как у MIN; шрифт — расчётом.
    # Наш арт ≥ 100 — не всегда Custom: у Юты (UTA 1_104_x, docs/utah.md) карта номеров — EA PIT 1_23_0, свои зоны
    # (22.10). Замер — место буквы на карте образца: больше LETTER_EA_PX — Custom
    lz = letter_zone_px(legacy["home"]) if art >= 100 and legacy["home"] else None
    custom = art >= 100 and (lz is None or max(lz) > LETTER_EA_PX)
    if custom:
        prof["name_zones_from"] = "1_14_4"
    elif lz:                             # наш арт ≥ 100 с картой EA (UTA): зоны — свои, но явно: шаблон стадии kit у 3-значного
        prof["name_zones_from"] = legacy["home"]   # арта — 1_131_0 (fb.pilot.home_template), места буквы у него ниже, без
        #                                            зоны 7 — герб [crest_fit] мерил бы не по тем местам, что в слоте
    prof["font_name_fit"] = "auto"
    plate = {k: font_plate(src[k], folder) for k in SLOT_KITS}   # фамилия на подложке (PHI, 22.10): атлас — как у источника
    if any(plate.values()):
        prof["font_plate"] = True
    D.append(Decision("font_plate", prof.get("font_plate", "—"), True,
                      "строки букв фамилии в атласе источника непрозрачны (плашка): " + ", ".join(
                          f"{k} {'да' if v else 'нет'}" for k, v in plate.items())))
    lz_s = f"буква {lz[0]} × {lz[1]}" if lz else "буква —"
    D.append(Decision("name_zones_from", prof.get("name_zones_from", "—"), True,
                      f"заготовка Custom: фамилия и номер на 15–17 % крупнее EA, {lz_s} против 15 × 15 — зоны MIN"
                      if custom else f"зоны образца {legacy['home']} ({lz_s}) — как у EA; явно, чтобы [crest_fit] на "
                      "стадии kit мерил по ним, а не по шаблону 1_131_0" if lz else "зоны EA-формы клуба"))
    prof["body_color"] = "back"
    bu = min(look[k]["body_uniform"] for k in SLOT_KITS)
    D.append(Decision("body_color", "back", bu > 0.9,
                      f"середина спины ровная на {bu:.0%} (back — как NJD, TBL; light — только MIN)"))
    prof["collar"] = collar
    if collar == "plain":                                # шов вставки под воротом (U вокруг щита) — как у NHL 27 (VGK 22.10);
        prof["collar_panel"] = True                      # с 22.10 и у формы с кокеткой: мыс со щитом — V шаблона (BUF)
    prof["crest_fit"] = {"gap_min": 0.008}   # герб крупнее, до буквы капитана 0,6 см (пользователь, 22.10: TBL, BOS, DET)
    prof["crest_size_cm"] = 27               # герб не меньше 27 см (22.10, VGK: «лого побольше»; EA NHL 13 — медиана 27)
    prof["trim_measure"] = "contiguous"   # ширина кромки — сплошной полосой по основе (с DET 22.10: у широких кромок
    #                                       прежний замер давал 3,7 см по кругу, а мыс спереди — мельче источника)
    vis = {k: look[k]["trim_visible"] for k in SLOT_KITS}
    bt = {k: beyond_trim(folder, src[k]) for k in SLOT_KITS}
    # двухцветный ворот (UTA выезд, 22.10): у края полоса цвета ткани, за ней — кромка другого цвета по всему кругу (и
    # спереди — V со щитом): collar_band, а не ширина по другой форме
    band2 = [k for k in SLOT_KITS if not vis[k] and differs(bt[k]["front"], look[k]["body"])
             and not differs(bt[k]["front"], bt[k]["back"])]
    if band2:
        prof["collar_band"] = {k: "full" for k in band2}
    D.append(Decision("collar_band", prof.get("collar_band", "—"), True,
                      "у края — цвет ткани, за полосой спереди сбоку / сзади: " + ", ".join(
                          f"{k} {np.round(bt[k]['front']).astype(int).tolist()} / "
                          f"{np.round(bt[k]['back']).astype(int).tolist()}" for k in SLOT_KITS if not vis[k])
                      + (" — двухцветный ворот: полоса у края цвета ткани, кромка во весь V" if band2 else "")
                      if not all(vis.values()) else "кромка у края видна (не цвета ткани)"))
    seen = [k for k in SLOT_KITS if vis[k]]
    if not all(vis.values()) and seen and [k for k in SLOT_KITS if not vis[k] and k not in band2]:
        prof["trim_width_from"] = {k: seen[0] for k in SLOT_KITS if not vis[k] and k not in band2}
    D.append(Decision("trim_width_from", prof.get("trim_width_from", "—"), all(vis.values()) or bool(seen),
                      "кромка у ворота сзади против ткани ниже: " + ", ".join(
                          f"{k} {np.round(look[k]['trim_c']).astype(int).tolist()} / "
                          f"{np.round(look[k]['trim_below']).astype(int).tolist()}" for k in SLOT_KITS)
                      + ("" if all(vis.values()) else " — кромка цвета ткани: ширина — по форме, где она видна"
                         + ("" if seen else "; у обеих не видна — ширина по цвету будет неверной, проверить"))))
    # за кромкой сбоку и сзади — вторая полоса, спереди — ткань (CHI 22.10): зачистка за кромкой — по углу
    two = [k for k in SLOT_KITS if differs(bt[k]["front"], bt[k]["back"])]
    if two:
        prof["trim_clear"] = "angle"
    D.append(Decision("trim_clear", prof.get("trim_clear", "—"), True,
                      "ткань за кромкой спереди сбоку / сзади: " + ", ".join(
                          f"{k} {np.round(bt[k]['front']).astype(int).tolist()} / "
                          f"{np.round(bt[k]['back']).astype(int).tolist()}" for k in SLOT_KITS)
                      + (" — сбоку и сзади вторая полоса: зачистка цветом источника по углу" if two else "")))
    # нашивки: герб из частей, рельеф нашивок в основе
    parts, relief, near = {}, {}, {}
    for k in SLOT_KITS:
        n, s_e, s_f, found, sponsors = crest_parts(code, folder, src[k])
        parts[k], relief[k] = n, (s_e, s_f)
        near[k] = sum(1 for f in found if f[0] == "crest~")
        sp = [f for f in found if f[0] in sponsors]
        # нашивка на груди не из правил (не герб, не щит, не плечевые): перенесётся как есть — реклама останется
        odd = [f for f in found if f[0] is None and f[3] > 2000 and 0.30 < f[1] < 0.70 and 0.55 < f[2] < 0.80]
        D.append(Decision(f"реклама {k}", "снимается [sponsor]" if sp else ("нет" if not odd else "ОСТАНЕТСЯ"),
                          not odd, (", ".join(f"{f[0]} uv ({f[1]:.3f}, {f[2]:.3f}), {f[3]} px" for f in sp) or
                                    "на груди рекламы нет") + ("" if not odd else "; не из правил kit_rules.toml: "
                                    + ", ".join(f"uv ({f[1]:.3f}, {f[2]:.3f}), {f[3]} px" for f in odd))))
    # низ: зона «от края» — выше полос (иначе верхние полосы — в переходе и раздуваются посередине, BOS 21.10)
    from fb import hem
    tops = {k: hem_band_top(folder, src[k]) for k in SLOT_KITS}
    if max(tops.values()) > hem.HEM_H - hem.HEM_BLEND - 0.01:
        prof["hem_h"] = round(max(tops.values()) + HEM_MARGIN, 3)
    D.append(Decision("hem_h", prof.get("hem_h", "—"), True,
                      "верх полос низа над краем, см: " + ", ".join(f"{k} {v * 100:.1f}" for k, v in tops.items())
                      + f" (зона «от края» без поля — {hem.HEM_H * 100:.0f} см, переход — верхние "
                      f"{hem.HEM_BLEND * 100:.0f} см)"))
    if max(parts.values()) > 1 or any(near.values()):
        prof["merge_parts"] = ["crest"]
    D.append(Decision("merge_parts", prof.get("merge_parts", "—"), True,
                      f"частей герба у источника: {parts} (больше одной — одной нашивкой, как TBL)"))
    if any(near.values()):
        prof["merge_near"] = MERGE_NEAR
    D.append(Decision("merge_near", prof.get("merge_near", "—"), True,
                      f"частей вне правил ближе {MERGE_NEAR} развёртки к гербу: {near}"
                      + (" — буквы надписи-герба одной нашивкой (как «UTAH» UTA)" if any(near.values()) else "")))
    ratio = {k: (s / max(f, 1e-6) if s is not None else None) for k, (s, f) in relief.items()}
    flat = any(r is not None and r > BNM_RATIO[1] for r in ratio.values())
    if flat:
        prof["base_normal_decals"] = "flat"
    D.append(Decision("base_normal_decals", prof.get("base_normal_decals", "—"),
                      all(r is None or not (BNM_RATIO[0] <= r <= BNM_RATIO[1]) for r in ratio.values()),
                      "наклон рельефа _base_normal у края нашивок / у ткани: "
                      + ", ".join(f"{k} {r:.1f}" if r is not None else f"{k} нет карты" for k, r in ratio.items())
                      + f" (больше {BNM_RATIO[1]:g} — запечён, как у TBL ten 7,8)"))
    # щит
    from fb import edge_kit as E
    g = n24_outer()
    gaps = {}
    for k in SLOT_KITS:
        r = E.source_shield_gap(g["M"], tex(folder, src[k], "color")[..., :3], tex(folder, src[k], "base_color")[..., :3])
        gaps[k] = r
    if collar == "plain":
        prof["shield_scale"] = SHIELD_SCALE
        D.append(Decision("щит", f"зазор {E.SHIELD_GAP_DEFAULT_MM:g} мм под кромкой, масштаб {SHIELD_SCALE}", True,
                          "edge_kit.SHIELD_GAP_DEFAULT_MM (решение пользователя по NJD 3 мм / TBL 4–5 мм); у источника — "
                          + ", ".join(f"{k} {r['gap_mm']} мм от {r['ref']}" for k, r in gaps.items()) + " (справка)"))
    else:
        prof["shield_offset_cm"] = [0.41, 0.45, 0.0]
        prof["shield_scale"] = 0.76
        D.append(Decision("щит", "как MIN: shield_offset_cm [0,41; 0,45; 0], 0,76", False,
                          "ворот со шнуровкой: щит на вставке, замера нет (kitport check — на глаз)"))
    prof["insert"] = ["home", "away"] if collar == "lace" else []
    if collar == "lace":
        D.append(Decision("insert", prof["insert"], False, "ворот со шнуровкой — вставка, как у MIN: проверить по листу"))
        prof["insert_color"] = "source"                  # у NHL 27 вставка бывает не красной (TOR, MTL, DAL, 22.10)
        # лацканы другого цвета (MTL, DAL: белые) — один цвет спереди сбоку и сзади, не цвет за ободом (у TOR дома белое
        # только сзади — там collar_band = "back")
        lp = {k: lapel_look(folder, src[k]) for k in SLOT_KITS}
        lap = [k for k in SLOT_KITS if not differs(lp[k][0], lp[k][1]) and differs(lp[k][0], lp[k][2])]
        if lap and len(lap) == len(SLOT_KITS):
            prof["collar_lapel"] = "source"
        D.append(Decision("collar_lapel", prof.get("collar_lapel", "—"), len(lap) in (0, len(SLOT_KITS)), ", ".join(
            f"{k}: лацкан спереди / сзади {np.round(lp[k][0]).astype(int).tolist()} / "
            f"{np.round(lp[k][1]).astype(int).tolist()}, за ободом {np.round(lp[k][2]).astype(int).tolist()}"
            for k in SLOT_KITS) + (" — лацканы другого цвета, от кромки до шва обода (edge_kit.LapelPaint)" if
                                   "collar_lapel" in prof else "")))
    prof["letter_zones_from"] = {}
    prof["sock_parts"] = [[0.0, [0, 0, 0]]]
    prof["slot"] = {k: {"kit": EDGE_KIT[k], "legacy": legacy[k], "sock": "auto", "pant": "source",
                        "helmet_logo": "source"} for k in SLOT_KITS}
    from . import survey as SV
    have_logo = {}
    for k in SLOT_KITS:
        try:
            SV.tex("nhl27", f"content/character/skater/league/nhl/{folder}/adidas/{src[k]}/"
                            f"helmetlogo_adidas_{folder}_{src[k]}_0_color")
            have_logo[k] = True
        except (KeyError, ValueError, OSError):
            have_logo[k] = False
    D.append(Decision("slot: sock / pant / helmet_logo", "auto / source / source", False,
                      "как у одобренных NJD и TBL; наклейка на шлем: " + ", ".join(
                          f"{k} — {'helmetlogo NHL 27 (реклама?)' if have_logo[k] else 'у источника нет — эмблема образца'}"
                          for k in SLOT_KITS) + " (эмблема образца всегда — helmet_logo = legacy, решение пользователя)"))
    # каска и краги
    cols = np.concatenate([tex(folder, src[k], "base_color", 512)[..., :3].reshape(-1, 3) for k in SLOT_KITS])
    pal = palette27(db27, team27)
    hrows, grows = nhl27_equipment(db27, team27, EQ_HELMET), nhl27_equipment(db27, team27, EQ_GLOVES)
    helmets = {}
    for k, loc in (("home", 0), ("away", 1)):
        hz, hw = eq_pick(hrows, v27[loc])
        gz, gw = eq_pick(grows, v27[loc])
        notes = []
        if hz is None:
            sys.exit(f"{code} {k}: в NHL 27 нет строки шлема (era 2 / −1)")
        hz, filled = fill_zones(hz)
        if filled:
            notes.append("зоны 4–9 шлема пустые — цветом зоны 1")
        hz, n1 = palette_fix(hz, pal, cols, "каска")
        ent = {"zones": hz}
        if gz is not None:
            gz, n2 = palette_fix(gz, pal, cols, "краги")
            ent["gloves"] = gz
            notes += n2
        helmets[EDGE_KIT[k]] = ent
        D.append(Decision(f"каска {k}", f"{hz[0]} … (строка {hw}); краги {gz[0] if gz else '—'} (строка {gw})",
                          not (n1 or [n for n in notes if "→" in n]), "; ".join(n1 + notes) or "как в NHL 27"))
    leg_pal = [[dbl.get("stockteamcolorstable", f"color_{c}", r) for c in "rgb"]
               for r in sorted(dbl.live_rows("stockteamcolorstable"), key=lambda r: dbl.get("stockteamcolorstable", "colorid", r))
               if dbl.get("stockteamcolorstable", "team", r) == team_leg]
    D.append(Decision("палитра (nhl24_team_colors.json)", pal, False,
                      f"предложение — палитра NHL 27 (stockteamcolorstable); в Legacy {leg_pal}. Пишется только с "
                      "--write-palette: у TBL второй цвет NHL 27 был тёмным, пользователь выбрал белый"))
    return D, {"profile": prof, "helmets": helmets, "palette": pal, "gaps": gaps, "look": look, "folder": folder}


# ---------------------------------------------------------------- вывод и запись

def toml_value(v):
    if isinstance(v, str):
        return json.dumps(v, ensure_ascii=False)
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    if isinstance(v, dict):
        return "{ " + ", ".join(f"{k} = {toml_value(x)}" for k, x in v.items()) + " }" if v else "{}"
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(toml_value(x) for x in v) + "]"
    raise TypeError(v)


def toml_section(code, prof, D, data):
    """Раздел профиля клуба (строки без окончаний)."""
    sure = {d.field: d for d in D}
    src = prof["source_kits"]
    out = [f"# {code} — из NHL 27, профиль собран генератором (python -m kitport profile --club {code}, "
           f"{__import__('datetime').date.today():%d.%m.%Y}).",
           f"# Нынешние формы — {src['home']} / {src['away']} (база NHL 27). Решения «проверить» — в выводе генератора и",
           "# docs/kitport.md §12.6; одобрения нет (default) — его ставит пользователь.",
           f"[{code}]"]
    for k in ("source", "source_kits", "body_color", "collar", "trim_measure", "trim_width_from", "collar_band", "crest_fit", "crest_size_cm", "yoke_color", "yoke", "yoke_shape_color",
              "yoke_side_blend", "yoke_stripe", "shield_offset_cm", "shield_scale", "merge_parts", "merge_near",
              "base_normal_decals", "hem_h", "insert", "insert_color", "collar_lapel",
              "letter_zones_from", "yoke_mesh", "collar_panel", "trim_clear", "armhole_split", "name_zones_from", "font_name_fit",
              "font_plate", "sock_parts"):
        if k not in prof:
            continue
        line = f"{k} = {toml_value(prof[k])}"
        note = {"shield_scale": f"щит по зазору под кромкой — edge_kit.SHIELD_GAP_DEFAULT_MM; у источника "
                                + " / ".join(f"{g['gap_mm']} мм" for g in data['gaps'].values()) + " (справка)",
                "sock_parts": "не используется (sock = auto)",
                "body_color": sure["body_color"].why,
                "trim_width_from": "кромка цвета ткани — ширина кромки по другой форме (edge_kit.TRIM_WIDTH_FROM)",
                "hem_h": "м: зона низа «от края» выше полос (fb.hem.HEM_H; без поля — 0,09)",
                "trim_measure": "ширина кромки — сплошной полосой от края по основе (edge_kit.TRIM_MEASURE)",
                "crest_fit": "герб крупнее: до буквы капитана 0,008 развёртки (~0,6 см), как TBL, BOS, DET",
                "yoke_mesh": "у NHL 27 в кокетке сетки ямок нет (edge_kit.YOKE_MESH)",
                "collar_panel": "шаблон ворота NHL 27: полоса, вставка со щитом, V, обод — одинаково у всех (edge_kit.panel_v)",
                "crest_size_cm": "герб не меньше 27 см (√ ширина × высота), как EA-гербы NHL 13 (edge_kit.crest_to_size)",
                "armhole_split": "рукав другого цвета: граница с тканью по шву проймы Edge целиком (VGK, DET)",
                "name_zones_from": "заготовка Custom: зоны фамилии, номера и буквы — как у MIN",
                "font_name_fit": "фамилия: высота как у MIN, промежуток ≤ 0,23 высоты буквы (edge_kit.name_font_fit)",
                "font_plate": "фамилия на подложке: буквы атласа — как у источника, без растяжки (edge_kit.FONT_PLATE)",
                "collar_band": "двухцветный ворот: у края полоса цвета ткани, за ней кромка во весь V (щит на ней) "
                               "(edge_kit.COLLAR_BAND)",
                "trim_clear": "за кромкой сбоку и сзади — вторая полоса: зачистка цветом источника по углу "
                              "(edge_kit.trim_body_by_angle)",
                "merge_near": "буквы надписи-герба рядом с гербом — одной нашивкой (kit_hybrid.near_parts)",
                "yoke_side_blend": "кокетка «на плечо»: край на руке — прямая наискосок от переда к спине (рисунок "
                                   "пользователя 21.10), боков EA нет",
                "yoke_stripe": "полоса под кокеткой — цвет и ширина по источнику (edge_kit.yoke_stripe_source)",
                "insert_color": "вставка цвета источника (edge_kit.INSERT_COLOR)",
                "collar_lapel": "лацканы другого цвета — от кромки до шва обода (edge_kit.LapelPaint)"}.get(k)
        if k == "collar":
            note = sure["collar"].why
        if k == "name_zones_from" and prof[k] != "1_14_4":
            note = ("зоны образца (карта EA): шаблон стадии kit у 3-значного арта — 1_131_0, [crest_fit] — по местам "
                    "буквы слота")
        out.append(line + (f"   # {note}" if note else ""))
    for kit in SLOT_KITS:
        s = prof["slot"][kit]
        out += ["", f"[{code}.slot.{kit}]"] + [f"{k} = {toml_value(v)}" for k, v in s.items()]
    return out


def compare(code, prof, helmets):
    """Сравнение с тем, что уже есть: профиль, реестр, каска. -> строки."""
    import tomllib
    have = tomllib.load(open(CLUBS_TOML, "rb")).get(code)
    out = []
    if have is None:
        out.append(f"профиля [{code}] в edge_clubs.toml нет")
    else:
        keys = sorted(set(have) | set(prof))
        for k in keys:
            a, b = have.get(k, "—"), prof.get(k, "—")
            if k == "slot":
                for kit in SLOT_KITS:
                    ha, hb = a.get(kit, {}) if isinstance(a, dict) else {}, b.get(kit, {}) if isinstance(b, dict) else {}
                    for kk in sorted(set(ha) | set(hb)):
                        if ha.get(kk, "—") != hb.get(kk, "—"):
                            out.append(f"  slot.{kit}.{kk}: есть {ha.get(kk, '—')!r} — генератор {hb.get(kk, '—')!r}")
                continue
            norm = lambda x: sorted(x) if isinstance(x, list) and all(isinstance(i, str) for i in x) else x
            mark = "  " if norm(a) == norm(b) else "≠ "
            out.append(f"{mark}{k}: есть {a!r} — генератор {b!r}")
    hj = json.load(open(HELMETS, encoding="utf-8")).get(code, {})
    for kit, ent in helmets.items():
        e = hj.get(kit)
        if e is None:
            out.append(f"≠ каска {kit}: в nhl24_helmets.json нет — генератор {ent['zones'][0]}…, краги "
                       f"{ent.get('gloves', [['—']])[0]}…")
            continue
        for f in ("zones", "gloves"):
            a, b = e.get(f) if isinstance(e, dict) else None, ent.get(f)
            if a != b:
                diff = [i + 1 for i in range(9) if (a or [None] * 9)[i] != (b or [None] * 9)[i]]
                out.append(f"≠ {f} {kit}: есть {a} — генератор {b} (зоны {diff})")
            else:
                out.append(f"  {f} {kit}: совпадает")
    return out


def head_profiles():
    """Разделы edge_clubs.toml в git HEAD (None — не в git или нет git)."""
    import subprocess
    import tomllib
    try:
        r = subprocess.run(["git", "show", "HEAD:tools/fb/edge_clubs.toml"], cwd=core.REPO, capture_output=True)
    except OSError:
        return None
    return tomllib.loads(r.stdout.decode("utf-8")) if r.returncode == 0 else None


def write_profile(code, lines, prof, head_check=True):
    """Раздел клуба — в конец edge_clubs.toml (окончания строк — как у файла). До замены файла — сверка: все разделы,
    кроме нового, разбираются в то же, что в git HEAD (и что в файле до записи); новый — в предложенное (21.10: без
    заголовка [КОД] ключи BOS легли в [TBL.slot.away]). Не сошлось — запись отменяется."""
    import tomllib
    raw = open(CLUBS_TOML, "rb").read()
    nl = b"\r\n" if b"\r\n" in raw else b"\n"
    txt = raw.rstrip(b"\r\n") + nl + nl + nl.join(l.encode("utf-8") for l in lines) + nl
    before, after = tomllib.loads(raw.decode("utf-8")), tomllib.loads(txt.decode("utf-8"))
    head = head_profiles() if head_check else None   # --no-head-check: агенты параллельно правят свои разделы
    for ref, what in ((before, "файле до записи"), (head, "git HEAD")):
        if ref is None:
            continue
        bad = sorted(c for c in set(ref) | set(after) if c != code and ref.get(c) != after.get(c))
        if bad:
            sys.exit(f"запись профиля {code}: разделы {bad} не как в {what} — запись отменена")
    if after.get(code) != json.loads(json.dumps(prof)):
        sys.exit(f"раздел [{code}] разбирается не в предложенное — запись отменена")
    open(CLUBS_TOML + ".part", "wb").write(txt)
    os.replace(CLUBS_TOML + ".part", CLUBS_TOML)


def write_helmets(code, helmets, about_note):
    """Каска и краги edge-форм клуба — в nhl24_helmets.json. У клуба уже есть запись других форм (SEA 22.10: «home»
    прежней формы NHL 24) — edge-формы дописываются в неё, прежние ключи — как были; те же формы — отказ."""
    raw = open(HELMETS, "rb").read().decode("utf-8")
    data = json.loads(raw)
    old = data.get(code, {})
    if set(old) & set(helmets):
        sys.exit(f"{HELMETS}: у {code} формы {sorted(set(old) & set(helmets))} уже есть — не трогаю")
    body = ",\n         ".join(f'"{kit}": ' + json.dumps(ent, ensure_ascii=False)
                               for kit, ent in list(old.items()) + list(helmets.items()))
    if old:                                            # объект клуба — от '"КОД": {' до парной скобки
        i = raw.index(f'\n "{code}": {{') + 1
        depth = 0
        for j in range(raw.index("{", i), len(raw)):
            depth += {"{": 1, "}": -1}.get(raw[j], 0)
            if depth == 0:
                break
        new = raw[:i] + f' "{code}": {{{body}}}' + raw[j + 1:]
    else:
        i = raw.rstrip().rindex("}")
        new = raw[:i].rstrip() + f',\n "{code}": {{{body}}}\n' + raw[i:]
    old_about = ' "about": ' + json.dumps(data["about"], ensure_ascii=False) + ","
    if old_about in new:
        new = new.replace(old_about, ' "about": ' + json.dumps(data["about"] + " " + about_note, ensure_ascii=False) + ",")
    else:
        say(f"  ! {HELMETS}: строку about не нашёл дословно — пояснение не дописано")
    json.loads(new)
    open(HELMETS + ".part", "wb").write(new.encode("utf-8"))
    os.replace(HELMETS + ".part", HELMETS)


def write_palette(code, pal):
    raw = open(COLORS, "rb").read().decode("utf-8")
    data = json.loads(raw)
    if json.dumps(data, ensure_ascii=False, indent=1) + "\n" != raw:
        sys.exit(f"{COLORS}: формат файла не тот, что у json.dump(indent=1) — правьте руками")
    data[code] = pal
    data["about"] += f" {code} ({__import__('datetime').date.today():%d.%m}): палитра NHL 27 (kitport profile --write-palette)."
    open(COLORS + ".part", "w", encoding="utf-8", newline="\n").write(json.dumps(data, ensure_ascii=False, indent=1) + "\n")
    os.replace(COLORS + ".part", COLORS)


def cmd_profile(a):
    os.environ["FB_GAME"] = "nhl27"                     # каталог дампа NHL 27 (fb.source читает его при импорте)
    sys.path.insert(0, core.TOOLS)
    clubs = [c.strip().upper() for c in a.club.split(",") if c.strip()]
    if (a.write or a.write_palette) and len(clubs) != 1:
        sys.exit("--write — по одному клубу")
    L = nhl24_mod()
    for code in clubs:
        say(f"\n==== {code}")
        D, data = propose(code)
        prof = data["profile"]
        say("решения (+ — уверен, ? — проверить):")
        for d in D:
            v = d.value if isinstance(d.value, str) else json.dumps(d.value, ensure_ascii=False)
            say(f"  {'+' if d.sure else '?'} {d.field}: {v}\n      {d.why}")
        reg, rnotes, rchanged = registry_plan(L, code)
        say("номера форм в реестре (nhl24_kits.json):")
        for n in rnotes:
            say("  " + n)
        for kit in SLOT_KITS:
            k = next(k for k in reg["kits"] if k["club"] == code and k["kit"] == EDGE_KIT[kit])
            say(f"  {EDGE_KIT[kit]} → 0_{k['art']}_{k['variant']}")
        lines = toml_section(code, prof, D, data)
        say("профиль (edge_clubs.toml):")
        for ln in lines:
            say("  | " + ln)
        say("каска и краги (nhl24_helmets.json):")
        for kit, ent in data["helmets"].items():
            say(f"  {kit}: {json.dumps(ent, ensure_ascii=False)}")
        say("сравнение с тем, что есть:")
        for ln in compare(code, prof, data["helmets"]):
            say("  " + ln)
        if a.write:
            import tomllib
            if code in tomllib.load(open(CLUBS_TOML, "rb")):
                sys.exit(f"[{code}] в edge_clubs.toml уже есть — генератор не переписывает готовый профиль")
            had = set(json.load(open(HELMETS, encoding="utf-8")).get(code, {})) & set(data["helmets"])
            if had:
                sys.exit(f"{code}: формы {sorted(had)} в nhl24_helmets.json уже есть — не трогаю")
            if rchanged:
                L.save_registry(reg)
                say(f"записано: реестр {L.REGISTRY}")
            write_profile(code, lines, prof, head_check=not getattr(a, "no_head_check", False))
            say(f"записано: профиль [{code}] → {CLUBS_TOML}")
            fixes = [d.why for d in D if d.field.startswith("каска") and "→" in d.why]
            note = (f"{code} edge_home/edge_away ({__import__('datetime').date.today():%d.%m}, kitport profile) — зоны 1–9 из "
                    "stockteamequipmenttable NHL 27 (era 2 и вариант формы, иначе era 2 / −1, иначе −1 / −1), пустые зоны "
                    "4–9 — цветом зоны 1" + (f"; подмена цветом палитры: {'; '.join(fixes)}" if fixes else "") + ".")
            write_helmets(code, data["helmets"], note)
            say(f"записано: каска и краги → {HELMETS}")
        if a.write_palette:
            write_palette(code, data["palette"])
            say(f"записано: палитра {data['palette']} → {COLORS}")
        if not (a.write or a.write_palette):
            say("(проба: --write — записать профиль, реестр, каску; палитра — только --write-palette)")
    return 0
