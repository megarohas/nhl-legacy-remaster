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
EQ_HELMET, EQ_GLOVES = 7, 4      # equipment шлема и краг (значения с rangelow, как в nhl24.py)
EQ_NEAR_PAL = 6.0                # ближе к цвету палитры — тот же цвет
EQ_FAR_PAL = 60.0                # дальше — не оттенок этого цвета палитры
EQ_JERSEY_GAIN = 6.0             # цвет палитры ближе к ткани свитера на столько — подменять
NEUTRAL = 25                     # max − min меньше — серый (чёрный, белый): не подменяется
BNM_SIGMA = 2.0                  # px 2048: сглаживание _base_normal перед замером наклона (плетение ткани — мельче)
BNM_RATIO = (4.0, 6.0)           # наклон у края нашивок / у ткани: больше второго — рельеф нашивок «запечён» (TBL ten — 7,8;
#                                  без него 0,9–3,4: NJD, TBL eleven, BOS, 21.10); между — проверить


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
    from fb.kit_batch import CLUBS
    f = next((club for club, _, c in CLUBS if c == code), None)
    if f is None:
        sys.exit(f"{code}: не знаю клуба (fb.kit_batch.CLUBS)")
    return f


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
    return {"xc": xc, "lace_frac": lace_frac, "ref": ref_c, "body": body, "body_uniform": body_uniform,
            "yoke_c": yoke_c, "yoke_uniform": yoke_u, "arm_c": arm_c,
            "yoke": differs(yoke_c, body) and yoke_u > 0.7, "on_arm": not differs(arm_c, yoke_c),
            "trim_c": trim_top, "trim_below": trim_below, "trim_visible": differs(trim_top, trim_below)}


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
                          f"{L_['yoke_uniform']:.0%}), ткань {np.round(L_['body']).astype(int).tolist()}, верх рукава "
                          f"{np.round(L_['arm_c']).astype(int).tolist()}"))
        if L_["yoke"]:
            yk[k] = yoke_kind(L_["yoke_c"])
    prof = {"source": "nhl27", "source_kits": src}
    if any(yoke.values()):
        kinds = {v for v in yk.values() if v}
        kind = kinds.pop() if len(kinds) == 1 else None
        prof["yoke_color"] = kind or "dark"
        D.append(Decision("yoke_color", prof["yoke_color"], kind is not None,
                          f"цвет кокетки {yk}: green — тёмно-зелёная (MIN), dark — чёрная (NJD); другого edge_kit.yoke_mask "
                          "не умеет" if kind is None else f"цвет кокетки — {kind}"))
        prof["yoke"] = {k: "1_14_3" for k in SLOT_KITS if yoke[k]}
        prof["yoke_shape_color"] = "green"
        arm = any(look[k]["on_arm"] for k in SLOT_KITS if yoke[k])
        D.append(Decision("yoke", prof["yoke"], not arm,
                          "бока кокетки «до плеча» — с EA MIN 1_14_3 (как NJD, пользователь 21.10)" if not arm else
                          "кокетка заходит на руку (тип MTL, §12.1): бока 1_14_3 — заготовка, нужен yoke_side_blend"))
    prof["body_color"] = "back"
    bu = min(look[k]["body_uniform"] for k in SLOT_KITS)
    D.append(Decision("body_color", "back", bu > 0.9,
                      f"середина спины ровная на {bu:.0%} (back — как NJD, TBL; light — только MIN)"))
    prof["collar"] = collar
    prof["crest_fit"] = {"gap_min": 0.008}   # герб крупнее, до буквы капитана 0,6 см (пользователь, 22.10: TBL, BOS, DET)
    prof["trim_measure"] = "contiguous"   # ширина кромки — сплошной полосой по основе (с DET 22.10: у широких кромок
    #                                       прежний замер давал 3,7 см по кругу, а мыс спереди — мельче источника)
    vis = {k: look[k]["trim_visible"] for k in SLOT_KITS}
    seen = [k for k in SLOT_KITS if vis[k]]
    if not all(vis.values()) and seen:
        prof["trim_width_from"] = {k: seen[0] for k in SLOT_KITS if not vis[k]}
    D.append(Decision("trim_width_from", prof.get("trim_width_from", "—"), all(vis.values()) or bool(seen),
                      "кромка у ворота сзади против ткани ниже: " + ", ".join(
                          f"{k} {np.round(look[k]['trim_c']).astype(int).tolist()} / "
                          f"{np.round(look[k]['trim_below']).astype(int).tolist()}" for k in SLOT_KITS)
                      + ("" if all(vis.values()) else " — кромка цвета ткани: ширина — по форме, где она видна"
                         + ("" if seen else "; у обеих не видна — ширина по цвету будет неверной, проверить"))))
    # нашивки: герб из частей, рельеф нашивок в основе
    parts, relief = {}, {}
    for k in SLOT_KITS:
        n, s_e, s_f, found, sponsors = crest_parts(code, folder, src[k])
        parts[k], relief[k] = n, (s_e, s_f)
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
    if max(parts.values()) > 1:
        prof["merge_parts"] = ["crest"]
    D.append(Decision("merge_parts", prof.get("merge_parts", "—"), True,
                      f"частей герба у источника: {parts} (больше одной — одной нашивкой, как TBL)"))
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
    for k in ("source", "source_kits", "body_color", "collar", "trim_measure", "trim_width_from", "crest_fit", "yoke_color", "yoke", "yoke_shape_color",
              "shield_offset_cm", "shield_scale", "merge_parts", "base_normal_decals", "hem_h", "insert",
              "letter_zones_from",
              "sock_parts"):
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
                "crest_fit": "герб крупнее: до буквы капитана 0,008 развёртки (~0,6 см), как TBL, BOS, DET"}.get(k)
        if k == "collar":
            note = sure["collar"].why
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


def write_profile(code, lines, prof):
    """Раздел клуба — в конец edge_clubs.toml (окончания строк — как у файла). До замены файла — сверка: все разделы,
    кроме нового, разбираются в то же, что в git HEAD (и что в файле до записи); новый — в предложенное (21.10: без
    заголовка [КОД] ключи BOS легли в [TBL.slot.away]). Не сошлось — запись отменяется."""
    import tomllib
    raw = open(CLUBS_TOML, "rb").read()
    nl = b"\r\n" if b"\r\n" in raw else b"\n"
    txt = raw.rstrip(b"\r\n") + nl + nl + nl.join(l.encode("utf-8") for l in lines) + nl
    before, after = tomllib.loads(raw.decode("utf-8")), tomllib.loads(txt.decode("utf-8"))
    head = head_profiles()
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
            write_profile(code, lines, prof)
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
