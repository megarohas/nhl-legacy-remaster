"""Коньки NHL 27 → NHL Legacy (skate_<N>_cm, 1024×512): перенос текстуры с модели конька NHL 27 на модель конька Legacy
по 3D, листы сравнения, превью в редакторе и пакет. Что в каком слоте и имена — fb/stick_slots.toml-подобный план
fb/skate_slots.toml; в игру — edge_kit pack (pack()) и kitport install, как формы и клюшки. Документация — docs/skates.md.

Устройство (разбор 23.10.2026):
- Legacy: одна модель на всех — renderboot/rendering/skate/playerskate_2.rx2 (оба конька, 1938 вершин; _0 — дальняя),
  бренд — только текстура cacherender/rendering/skate/texlib_<N>.rx2: skate_<N>_cm 1024×512 (верхняя половина — левый и
  правый конёк зеркально, нижняя пустая), _nm 512×256, _rm 256×128, _sm 512×256; N = exhibitionskaterequipment.skatebrand;
- NHL 27: модель у пяти коньков своя (OWN_MESH), у прочих — общая модель бренда (bauer|ccm|true/common), вариант
  notuck (без заправленной гетры); текстура player_skate_<модель>_color 1024×1024 (верх — один конёк, низ — другой).
  Обе модели — в одной системе (подошва на 0, носок к +z), конёк NHL 27 шире (|x| до 0,237 против 0,177) и выше
  (0,267 против 0,242): перед переносом каждый конёк NHL 27 вписывается в рамку своего конька Legacy по осям.

  python -m fb.skates build [МОДЕЛЬ…] [--out DIR]   # PNG 1024×512 в развёртке Legacy (без моделей — все слоты плана)
  python -m fb.skates sheet [--out FILE]          # лист: было | NHL 27 (своя модель) | в игре (модель Legacy), 4 вида
  python -m fb.skates fe-sheet                     # превью в редакторе: EA → новое
  python -m fb.skates fe-fit                       # ракурсы превью по рамкам силуэта EA (FE_POSES)
Первый запуск — с FB_GAME=nhl27 (сетки NHL 27 кэшируются в WORK/mesh27_*.pkl; edge_kit pack потом работает без неё).
"""
import argparse
import glob
import json
import os
import pickle
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .cas import REPO
from . import kit3d

WORK = os.path.join(REPO, "game", "work", "equipment27", "skates")
SRC27 = os.path.join(REPO, "game", "work", "nhl27", "extract", "gear27")
LEGACY_BIG = os.path.join(REPO, "game", "other", "legacy", "big")
LEG_MESH = os.path.join(LEGACY_BIG, "renderboot", "rendering", "skate", "playerskate_2.rx2")
LEG_TEX = os.path.join(LEGACY_BIG, "cacherender", "rendering", "skate", "texlib_{}.rx2")
SKATE_REL = "rendering/skate/texlib_{}.rx2"
SLOTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "skate_slots.toml")
SIZE = (1024, 512)
MESH27 = "content/character/skater/player/skate/{path}/components/player_skate_{name}_notuck_mesh"
OWN_MESH = {"bauer_supreme_fuse": "bauer/supreme/fuse", "bauer_supreme_shadow": "bauer/supreme/shadow",
            "bauer_vapor_flylite": "bauer/vapor/flylite", "ccm_tacks_xf652": "ccm/tacks/xf652",
            "true_catalyst_9x4": "true/catalyst/9x4"}
_M = {}


def mesh_of(model):
    """Модель NHL 27 для текстуры: своя (OWN_MESH) или общая бренда. -> путь ресурса."""
    for k, path in OWN_MESH.items():
        if model == k or model.startswith(k + "_"):
            return MESH27.format(path=path, name=k)
    brand = model.split("_")[0]
    return MESH27.format(path=f"{brand}/common", name=f"{brand}_common")


def _normals(pos, tri):
    fn = np.cross(pos[tri[:, 1]] - pos[tri[:, 0]], pos[tri[:, 2]] - pos[tri[:, 0]])
    n = np.zeros_like(pos)
    for k in range(3):
        np.add.at(n, tri[:, k], fn)
    return n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)


def mesh27(path):
    """Модель NHL 27 {'pos', 'uv', 'tri', 'nrm'} (секция mat_skate; кэш — WORK/mesh27_<имя>.pkl)."""
    if path in _M:
        return _M[path]
    cache = os.path.join(WORK, f"mesh27_{path.split('/')[-1]}.pkl")
    if os.path.exists(cache):
        m = pickle.load(open(cache, "rb"))
    else:
        os.environ.setdefault("FB_GAME", "nhl27")
        from . import heads
        res = {}
        for p in sorted(glob.glob(os.path.join(heads.CAT, "scan", "*.jsonl"))):
            for line in open(p, encoding="utf-8"):
                if '"k": "res"' in line and "/player/skate/" in line and '"ofs"' in line:
                    r = json.loads(line)
                    res.setdefault(r["name"], r)
        heads._res = res
        s = heads.mesh(path)["sections"]["mat_skate"]
        m = {"pos": np.asarray(s["pos"], np.float64)[:, :3], "uv": np.asarray(s["uv0"], np.float64)[:, :2],
             "tri": np.asarray(s["tri"], np.int64)}
        os.makedirs(WORK, exist_ok=True)
        pickle.dump(m, open(cache, "wb"))
    m = dict(m, nrm=_normals(m["pos"], m["tri"]))
    _M[path] = m
    return m


def mesh_legacy():
    if "leg" not in _M:
        sys.path.insert(0, os.path.join(REPO, "tools"))
        import rw4mesh as rm
        L = rm.Mesh(open(LEG_MESH, "rb").read())
        m = {"pos": np.asarray(L.pos, np.float64)[:, :3], "uv": np.asarray(L.uv, np.float64)[:, :2],
             "tri": np.asarray(L.tris, np.int64)}
        m["nrm"] = np.asarray(L.nrm, np.float64)[:, :3] if len(L.nrm) else _normals(m["pos"], m["tri"])
        _M["leg"] = m
    return _M["leg"]


def fitted27(path):
    """Модель NHL 27, каждый конёк (знак x) вписан в рамку своего конька Legacy по осям (масштаб и сдвиг)."""
    key = ("fit", path)
    if key in _M:
        return _M[key]
    src, dst = mesh27(path), mesh_legacy()
    p = src["pos"].copy()
    for sgn in (1.0, -1.0):
        ks, kd = src["pos"][:, 0] * sgn > 0, dst["pos"][:, 0] * sgn > 0
        s0, s1 = src["pos"][ks].min(0), src["pos"][ks].max(0)
        d0, d1 = dst["pos"][kd].min(0), dst["pos"][kd].max(0)
        p[ks] = d0 + (src["pos"][ks] - s0) * (d1 - d0) / np.maximum(s1 - s0, 1e-9)
    m = dict(src, pos=p, nrm=_normals(p, src["tri"]))
    _M[key] = m
    return m


def src_png(model):
    f = glob.glob(os.path.join(SRC27, "**", f"player_skate_{model}_color.png"), recursive=True)
    if not f:
        raise SystemExit(f"нет выгрузки player_skate_{model}_color в {SRC27}")
    return f[0]


def legacy_png(n):
    """Нынешняя текстура слота N (skate_<N>_cm) → PNG (кэш WORK/legacy)."""
    out = os.path.join(WORK, "legacy", f"skate_{n}_cm.png")
    if not os.path.exists(out):
        sys.path.insert(0, os.path.join(REPO, "tools"))
        import teamart as ta
        import kitpaint as kp
        rw = ta.Rw4(open(LEG_TEX.format(n), "rb").read(), LEG_TEX.format(n))
        t = [t for t in rw.textures if t.name.startswith(f"skate_{n}_cm")][0]
        w, h, px = kp.tex_decode(rw, t, 0)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        Image.frombytes("RGBA", (w, h), bytes(px)).save(out)
    return out


LACE_ISLAND_Y = (235, 342)          # строки skate_cm 1024×512: остров переда (мысок, язык, шнуровка) — у обоих коньков
LACE_BRIGHT = 150                   # шнурки Legacy — тексели светлее (min по каналам) на этом острове
LACE_PAD = 3                        # текселей запаса вокруг рамки шнуровки


def lace_mask(n):
    """Рамка нарисованной шнуровки Legacy слота N (по коньку: светлые тексели острова переда, их рамка + LACE_PAD) —
    у NHL 27 шнурки — отдельная сетка прядей, переносом на нарисованную шнуровку Legacy выходила каша (23.10). -> маска."""
    a = np.asarray(Image.open(legacy_png(n)).convert("RGB")).astype(np.int32)
    H, W = a.shape[:2]
    m = np.zeros((H, W), bool)
    y0, y1 = (int(v * H / 512) for v in LACE_ISLAND_Y)
    for x0, x1 in ((0, W // 2), (W // 2, W)):
        br = a[y0:y1, x0:x1].min(-1) > LACE_BRIGHT
        ys, xs = np.nonzero(br)
        if len(ys) < 50:
            continue
        m[max(y0 + ys.min() - LACE_PAD, 0):y0 + ys.max() + LACE_PAD + 1,
          max(x0 + xs.min() - LACE_PAD, 0):x0 + xs.max() + LACE_PAD + 1] = True
    return m


def convert(model, n=None):
    """Текстура конька NHL 27 → RGBA 1024×512 в развёртке Legacy (вне развёртки — ближайший тексель, для мипов);
    с n — шнуровка (lace_mask) — нарисованная Legacy (слота LACE_REF)."""
    from scipy import ndimage as ndi
    src, dst = fitted27(mesh_of(model)), mesh_legacy()
    tex = kit3d.load_tex(src_png(model))
    img, mask, _d, _i = kit3d.transfer(tex, src, dst, SIZE, 2)
    img = np.asarray(img, np.float64)[..., :3]
    m = np.asarray(mask, bool)
    if m.shape != img.shape[:2]:
        m = np.asarray(Image.fromarray(m.astype(np.uint8) * 255).resize(img.shape[1::-1], Image.NEAREST)) > 0
    _, (iy, ix) = ndi.distance_transform_edt(~m, return_indices=True)
    img = img[iy, ix]
    rgba = np.dstack([np.clip(np.round(img), 0, 255).astype(np.uint8), np.full(img.shape[:2], 255, np.uint8)])
    im = Image.fromarray(rgba, "RGBA")
    im = im if im.size == SIZE else im.resize(SIZE, Image.BOX)
    if n is not None:
        lm = lace_mask(LACE_REF)
        out = np.asarray(im).copy()
        out[lm] = np.asarray(Image.open(legacy_png(LACE_REF)).convert("RGBA").resize(SIZE))[lm]
        im = Image.fromarray(out, "RGBA")
    return im


HOLDER_V = 0.72                     # остров с серединой ниже (v) — стакан с лезвием (строки 373–508 из 512): рельеф гладкий
LACE_REF = 48                       # шнуровка — с этого слота Legacy (Supreme 1S: белые шнурки на чёрном языке); у слота
#                                    со светлым ботинком (70, белый APX) рамка «светлого» захватывала ботинок — оранжевые куски


def src27(model, kind):
    """PNG карты NHL 27 (color | normal | coeff) модели."""
    f = glob.glob(os.path.join(SRC27, "**", f"player_skate_{model}_{kind}.png"), recursive=True)
    if not f:
        raise SystemExit(f"нет выгрузки player_skate_{model}_{kind} в {SRC27} (FB_GAME=nhl27 python -m fb.extract …)")
    return f[0]


def legacy_map(n, kind):
    """Карта слота Legacy (cm | nm | sm | rm) → numpy (H, W, 4)."""
    sys.path.insert(0, os.path.join(REPO, "tools"))
    import teamart as ta
    import kitpaint as kp
    rw = ta.Rw4(open(LEG_TEX.format(n), "rb").read(), LEG_TEX.format(n))
    t = [t for t in rw.textures if t.name.startswith(f"skate_{n}_{kind}")][0]
    w, h, px = kp.tex_decode(rw, t, 0)
    return np.frombuffer(bytes(px), np.uint8).reshape(h, w, 4).astype(np.float64)


def islands(size):
    """Острова развёртки Legacy на растре size: номер острова у текселя (−1 — пусто)."""
    key = ("isl", size)
    if key in _M:
        return _M[key]
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    m = mesh_legacy()
    k = np.round(m["uv"] * 4096).astype(np.int64)
    _, vid = np.unique(k[:, 0] * 10000 + k[:, 1], return_inverse=True)
    T = vid[m["tri"]]
    n = vid.max() + 1
    A = coo_matrix((np.ones(len(T) * 3), (T.ravel(), np.roll(T, 1, 1).ravel())), shape=(n, n))
    _, lab = connected_components(A, directed=False)
    tid, _ = kit3d.raster_uv(m, size)
    isl = np.where(tid >= 0, lab[T[np.maximum(tid, 0), 0]], -1)
    _M[key] = isl
    return isl


def maps(model, n):
    """Рельеф и блик слота n по модели NHL 27: nm — перенос normal NHL 27 (kit3d.transfer_normals), sm — канал G
    coeff NHL 27 (гладкость деталей), подогнанный по каждому острову к среднему и разбросу блика Legacy слота n (уровни
    материалов игры — как были, рисунок — новый). -> (nm RGBA 512×256, sm RGBA 512×256). Карты Legacy нарисованы под
    прежний дизайн (окна стакана Tuuk, «X» Supreme 1S) — под новым рисунком они проступали бы."""
    src, dst = fitted27(mesh_of(model)), mesh_legacy()
    nsz = (SIZE[0] // 2, SIZE[1] // 2)
    nt = kit3d.load_tex(src27(model, "normal"))
    nm = kit3d.transfer_normals(nt, src, dst, nsz, 2)
    co = kit3d.load_tex(src27(model, "coeff"))
    g, _m, _d, _i = kit3d.transfer(np.repeat(np.asarray(co)[..., 1:2], 3, -1), src, dst, nsz, 2)
    g = np.asarray(g, np.float64)[..., 0]
    old = legacy_map(n, "sm")
    if old.shape[:2] != g.shape:
        old = np.asarray(Image.fromarray(old.astype(np.uint8)).resize(g.shape[::-1], Image.BILINEAR)).astype(np.float64)
    isl = islands(nsz)
    sm = old[..., 0].copy()
    for i in np.unique(isl[isl >= 0]):
        k = isl == i
        sg, so = g[k].std(), old[..., 0][k].std()
        sm[k] = old[..., 0][k].mean() + (g[k] - g[k].mean()) * (so / sg if sg > 1e-6 else 0.0)
    sm = np.clip(sm, 0, 255)
    # шнуровка — рельеф и блик Legacy (как и её цвет, LACE_REF); стакан — гладкий: у NHL 27 там пряди шнурков и прорези
    # стакана другой формы — переносом рельеф шёл цветной кашей (лист _maps43, 23.10)
    lm = np.asarray(Image.fromarray(lace_mask(LACE_REF).astype(np.uint8) * 255).resize(nsz, Image.NEAREST)) > 0
    ref_nm, ref_sm = legacy_map(LACE_REF, "nm"), legacy_map(LACE_REF, "sm")
    if ref_nm.shape[:2] != lm.shape:
        ref_nm = np.asarray(Image.fromarray(ref_nm.astype(np.uint8)).resize(nsz, Image.BILINEAR)).astype(np.float64)
        ref_sm = np.asarray(Image.fromarray(ref_sm.astype(np.uint8)).resize(nsz, Image.BILINEAR)).astype(np.float64)
    nm = np.asarray(nm, np.float64).copy()
    nm[lm] = ref_nm[lm][:, :3]
    sm[lm] = ref_sm[lm][:, 0]
    vv = (np.arange(nsz[1]) + 0.5) / nsz[1]
    for i in np.unique(isl[isl >= 0]):
        k = isl == i
        if vv[np.nonzero(k)[0]].mean() > HOLDER_V:
            nm[k] = (127.5, 127.5, 255.0)
    nm_img = np.dstack([np.clip(np.round(nm), 0, 255).astype(np.uint8), np.full(nm.shape[:2], 255, np.uint8)])
    sm_img = np.dstack([np.repeat(np.round(sm).astype(np.uint8)[..., None], 3, -1), np.full(sm.shape, 255, np.uint8)])
    return Image.fromarray(nm_img, "RGBA"), Image.fromarray(sm_img, "RGBA")


def slots():
    """План skate_slots.toml → [(буква, N, from, key, name | None)] в порядке каталога."""
    import tomllib
    with open(SLOTS, "rb") as f:
        plan = tomllib.load(f)["slot"]
    out = []
    for i, (n, s) in enumerate(plan.items()):
        kind, _, src = s["from"].partition(":")
        if kind != "nhl27" or not src:
            raise SystemExit(f"{SLOTS}: слот {n}: from {s['from']!r} — nhl27:<модель>")
        out.append((chr(65 + i), int(n), s["from"], s.get("key"), s.get("name")))
    return out


def slot_image(src, n=None):
    return convert(src.partition(":")[2], n)


# Превью в редакторе: fe/ion/artassets/createplayer/skates/skate<N>.big (BIGF/Apt, 8888 256×128, картинка 140×108) — у EA
# два вида одного конька: сбоку (носок влево) и сзади (пятка к камере, у 72 на ней логотип EA SPORTS). Ракурсы — подбор по силуэту превью EA (fe_fit), свет — как у
# клюшек (fb.sticks.FE_LIGHT), модель — конёк Legacy (x > 0).
FE_REL = "fe/ion/artassets/createplayer/skates/skate{}.big"
FE_SIZE = (140, 108)
FE_REF = 48                         # превью EA для подбора ракурса (у 72 кадр другой — крупнее)
FE_POSES = [(-1.571, -0.105, 0.0, -18.0, 19.0, 266.292, 0.0),   # сбоку (fe_fit_box по skate48, 23.10)
            (3.142, -0.105, 0.0, 39.5, 18.0, 257.143, 0.0)]     # сзади
FE_LIGHT = (-0.986, 0.174, 0.665, -0.398, 0.45, 0.7)             # свет (fe_fit по skate48): ошибка цвета 46


def _fe_parts():
    if "fe" not in _M:
        m = mesh_legacy()
        k = m["pos"][:, 0] > 0
        keep = k[m["tri"]].all(1)
        part = {"pos": m["pos"], "uv": m["uv"], "tri": m["tri"][keep], "nrm": m["nrm"]}
        _M["fe"] = (part, m["pos"][k].mean(0))
    return _M["fe"]


def fe_ea(n):
    from .sticks import LEGACY_BIG as LB
    sys.path.insert(0, os.path.join(REPO, "tools"))
    import teamart as ta
    o = ta.UiLogo.load(os.path.join(LB, "cache", *FE_REL.format(n).split("/")))
    w, h, px = o.decode()
    return Image.frombytes("RGBA", (w, h), bytes(px)).crop((0, 0) + FE_SIZE)


FE_VIEWS = ((-90.0, -6.0), (180.0, -6.0))   # (рыскание, тангаж), °: сбоку снаружи носком влево; сзади; чуть сверху


def fe_fit_box(ref=FE_REF, log=print):
    """Ракурсы превью — фиксированные (FE_VIEWS), масштаб и место — по рамке силуэта превью EA в своей половине кадра
    (подбор по силуэту целиком сваливался: у EA для превью — конёк с ботинком выше, IoU тянул вид сзади в три четверти).
    -> позы."""
    from .sticks import _fe_raster
    part, c = _fe_parts()
    bare = [dict(part, tex=None)]
    from scipy import ndimage as ndi
    A = np.asarray(fe_ea(ref))[..., 3] > 127
    lab, n = ndi.label(A)
    big = sorted(range(1, n + 1), key=lambda i: -(lab == i).sum())[:2]
    figs = sorted(big, key=lambda i: np.nonzero(lab == i)[1].mean())   # слева — сбоку, справа — сзади
    poses = []
    for half, (yaw, pitch) in enumerate(FE_VIEWS):
        ay, ax = np.nonzero(lab == figs[half])
        q = np.array([np.radians(yaw), np.radians(pitch), 0.0, 0.0, 0.0, 300.0, 0.0])
        for _ in range(4):
            yy, xx = np.nonzero(_fe_raster(bare, q, c, 1, FE_SIZE, base=np.eye(3))[0])
            q[5] *= min((ay.max() - ay.min() + 1) / max(yy.max() - yy.min() + 1, 1),    # вписать в рамку EA:
                        (ax.max() - ax.min() + 1) / max(xx.max() - xx.min() + 1, 1))    # у Legacy ботинок ниже
            yy, xx = np.nonzero(_fe_raster(bare, q, c, 1, FE_SIZE, base=np.eye(3))[0])
            q[3] += (ax.min() + ax.max()) / 2 - (xx.min() + xx.max()) / 2
            q[4] += ay.max() - yy.max()                  # лезвие — на той же высоте, что у EA
        log(f"  вид {half}: {np.round(q, 3).tolist()}")
        poses.append(q)
    return poses


def fe_fit(ref=FE_REF, log=print):
    """Ракурсы двух видов превью по силуэту превью EA слота ref (левая половина кадра — вид сбоку, правая — сзади) и
    свет по нему. -> (позы, свет)."""
    from scipy.optimize import least_squares, minimize
    from .sticks import _fe_raster, _fe_shade
    part, c = _fe_parts()
    bare = [dict(part, tex=None)]
    A = np.asarray(fe_ea(ref))[..., 3] > 127
    W = FE_SIZE[0]
    poses = []
    for half in (0, 1):
        Am = A.copy()
        Am[:, (W // 2 if half == 0 else 0):(W if half == 0 else W // 2)] = False
        ay, ax = np.nonzero(Am)
        region = np.zeros_like(A)
        region[:, (0 if half == 0 else W // 2):(W // 2 if half == 0 else W)] = True

        def full(q):                                     # вид сзади: масштаб и перспектива — как сбоку, разворот ±12°
            if half == 0:
                return q
            yaw = np.radians(180) + np.radians(12) * np.tanh(q[0])
            return np.array([yaw, q[1], 0.0, q[3], q[4], poses[0][5], poses[0][6]])

        def loss(q):
            cov = _fe_raster(bare, full(q), c, 1, FE_SIZE, base=np.eye(3))[0]
            return float(((Am ^ cov) & region).mean() + (cov & ~region).mean())

        def centred(q):
            cov = _fe_raster(bare, full(q), c, 1, FE_SIZE, base=np.eye(3))[0]
            yy, xx = np.nonzero(cov)
            if len(xx):
                q = q.copy()
                q[3] += ax.mean() - xx.mean()
                q[4] += ay.mean() - yy.mean()
            return q
        y0 = -90 if half == 0 else 180                   # сбоку снаружи (носок влево) | сзади (пятка к камере)
        grid = ([np.array([np.radians(y0 + y), np.radians(p), 0.0, 0, 0, sc, 0.0]) for y in range(-40, 41, 10)
                 for p in (-20, -10, 0, 10, 20) for sc in (250, 350, 450)] if half == 0 else
                [np.array([t, np.radians(p), 0.0, 0, 0, 0, 0]) for t in (-1.0, 0.0, 1.0) for p in (-20, -10, 0, 10, 20)])
        cands = sorted(((loss(q), q) for q in (centred(g) for g in grid)), key=lambda t: t[0])
        step = np.array([0.3, 0.3, 0.3, 8, 8, 40, 0.4])
        best = None
        for _, q in cands[:6]:
            r = minimize(loss, q, method="Nelder-Mead", options={"maxiter": 1500, "xatol": 1e-3, "fatol": 1e-6,
                                                                 "initial_simplex": np.vstack([q] + [q + np.eye(7)[i] * step[i] for i in range(7)])})
            if best is None or r.fun < best[0]:
                best = (r.fun, r.x)
        log(f"  вид {half}: силуэт {best[0]:.4f} {np.round(full(best[1]), 3).tolist()}")
        poses.append(full(best[1]))
    tex = np.asarray(Image.open(legacy_png(ref)).convert("RGBA")).astype(np.float64)
    ea = np.asarray(fe_ea(ref)).astype(np.float64)
    data = []
    for q in poses:
        cov, alb, nrm, pt = _fe_raster([dict(part, tex=tex)], q, c, 1, FE_SIZE, base=np.eye(3))
        ok = cov & (ea[..., 3] > 250)
        data.append((alb[ok], nrm[ok], pt[ok], ea[..., :3][ok]))
    al, nr, pa, E = (np.concatenate([d[i] for d in data]) for i in range(4))
    r = least_squares(lambda q: (_fe_shade(al, nr, pa, q) - E).ravel(), [0.0, 0.5, 0.45, 0.7, 0.45, 0.7])
    log(f"  свет {np.round(r.x, 3).tolist()}, ошибка цвета {np.abs(_fe_shade(al, nr, pa, r.x) - E).mean():.1f}")
    return poses, r.x


def render_fe(tex_img, ss=4):
    """Превью конька для редактора (два вида, как у EA). -> RGBA FE_SIZE."""
    from .sticks import _fe_raster, _fe_shade
    if FE_POSES is None:
        raise SystemExit("нет FE_POSES — python -m fb.skates fe-fit")
    part, c = _fe_parts()
    tex = np.asarray(tex_img.convert("RGBA")).astype(np.float64)
    W, H = FE_SIZE
    acc = np.zeros((H, W, 4))
    for q in FE_POSES:
        cov, alb, nrm, pt = _fe_raster([dict(part, tex=tex)], q, c, ss, FE_SIZE, base=np.eye(3))
        col = _fe_shade(alb, nrm, pt, FE_LIGHT) * cov[..., None]
        a = cov.reshape(H, ss, W, ss).mean((1, 3))
        rgb = col.reshape(H, ss, W, ss, 3).sum((1, 3)) / np.maximum(cov.reshape(H, ss, W, ss).sum((1, 3)), 1)[..., None]
        acc[..., :3] = acc[..., :3] * (1 - a[..., None]) + rgb * a[..., None]
        acc[..., 3] = np.maximum(acc[..., 3], a)
    img = np.concatenate([acc[..., :3], acc[..., 3:] * 255], -1)
    return Image.fromarray(np.clip(np.round(img), 0, 255).astype(np.uint8), "RGBA")


def write_fe(img, n, out):
    from .sticks import LEGACY_BIG as LB
    sys.path.insert(0, os.path.join(REPO, "tools"))
    import teamart as ta
    import playerhead as ph
    tpl = ta.UiLogo.load(os.path.join(LB, "cache", *FE_REL.format(n).split("/")))
    tw, th = tpl.fetch.width, tpl.fetch.height
    rgba = ph.place(img.convert("RGBA").tobytes(), img.size[0], img.size[1], tw, th)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "wb") as f:
        f.write(tpl.build(rgba, "md5"))


def pack(man, cache):
    """Коньки плана в пакет (edge_kit pack): texlib_<N>.rx2 по шаблону архива Legacy — skate_N_cm (перенос), _nm и _sm
    (maps), _rm — как был; записи type skate и имена — в man["loc"]. -> число."""
    import hashlib
    sys.path.insert(0, os.path.join(REPO, "tools"))
    import teamart as ta
    import kitpaint as kp
    k = 0
    for lab, num, src, key, name in slots():
        model = src.partition(":")[2]
        rel = SKATE_REL.format(num)
        rw = ta.Rw4(open(LEG_TEX.format(num), "rb").read(), LEG_TEX.format(num))
        cm = slot_image(src, num)
        nm, sm = maps(model, num)
        for t in rw.textures:
            kind = t.name.split(".")[0].rsplit("_", 1)[-1]
            img = {"cm": cm, "nm": nm, "sm": sm}.get(kind)
            if img is None:
                continue
            w, h = t.layout.levels[0][:2]
            kp.tex_replace(rw, t, img.convert("RGBA").resize((w, h), Image.LANCZOS).tobytes(), w, h)
        q = os.path.join(cache, *rel.split("/"))
        os.makedirs(os.path.dirname(q), exist_ok=True)
        with open(q, "wb") as f:
            f.write(rw.bytes())
        fe = FE_REL.format(num)
        qf = os.path.join(cache, *fe.split("/"))
        write_fe(render_fe(cm), num, qf)
        for f, path, what in ((rel, q, "конёк"), (fe, qf, "превью в редакторе")):
            e = {"file": f, "type": "skate", "md5": hashlib.md5(open(path, "rb").read()).hexdigest(),
                 "size": os.path.getsize(path), "action": "replace",
                 "note": f"{what} {lab}: {src} (fb.skates, skate_slots.toml)" + (f" — «{name}»" if name else "")}
            man["files"] = [x for x in man["files"] if x["file"] != f] + [e]
        if key and name:
            man.setdefault("loc", {})[key] = name
        k += 1
    return k


def render_skate(tex_img, mesh, width=420, angles=(90, 0, -90, 180), side=1.0):
    """Конёк (сторона side по знаку x) с текстурой: виды вокруг вертикали (90 — снаружи сбоку, 0 — спереди,
    180 — сзади). -> RGB."""
    sys.path.insert(0, os.path.join(REPO, "tools"))
    import scans24 as S
    k = mesh["pos"][:, 0] * side > 0
    keep = k[mesh["tri"]].all(1)
    c = mesh["pos"][k].mean(0)
    tex = np.asarray(tex_img.convert("RGB"))
    rows = []
    for ang in angles:
        a = np.radians(ang)
        R = np.array([[np.cos(a), 0, np.sin(a)], [0, 1, 0], [-np.sin(a), 0, np.cos(a)]])
        pos = (mesh["pos"] - c) @ R.T
        part = {"pos": pos, "nrm": mesh["nrm"] @ R.T, "uv": mesh["uv"], "tri": mesh["tri"][keep], "tex": tex,
                "twosided": True}
        rows.append(S.render([part], 0.0, width, frame=(-0.17, 0.17, -0.13, 0.15)))
    out = Image.new("RGB", (sum(r.size[0] + 4 for r in rows), rows[0].size[1]), (30, 30, 34))
    x = 0
    for r in rows:
        out.paste(r, (x, 0))
        x += r.size[0] + 4
    return out


def _font(size):
    try:
        return ImageFont.truetype("C:/Windows/Fonts/segoeuib.ttf", size)
    except OSError:
        return ImageFont.load_default()


def cmd_build(a):
    out = a.out or os.path.join(WORK, "out")
    os.makedirs(out, exist_ok=True)
    items = [(None, None, "nhl27:" + m, None, None) for m in a.ids] if a.ids else slots()
    for lab, n, src, key, name in items:
        model = src.partition(":")[2]
        p = os.path.join(out, f"skate_{model}.png" if n is None else f"texlib_{n}.png")
        slot_image(src, n).save(p)
        print(f"{lab or '-'} {n or ''} {model} ({mesh_of(model).split('/')[-1]}) -> {p}")


def cmd_fe_sheet(a):
    """Лист превью редактора: EA (нынешнее) → новое, по слотам плана, ×3."""
    font = _font(15)
    z = 3
    W, H = FE_SIZE
    items = slots()
    cols = 3
    cw, ch = W * z * 2 + 30, H * z + 30
    rows = (len(items) + cols - 1) // cols
    sh = Image.new("RGB", (cols * cw + 10, rows * ch + 10), (20, 20, 24))
    d = ImageDraw.Draw(sh)
    for i, (lab, n, src, key, name) in enumerate(items):
        x, y = 10 + (i % cols) * cw, 10 + (i // cols) * ch
        d.text((x, y), f"{lab} · {n} · {name or key}", fill=(255, 220, 140), font=font)
        for j, im in enumerate((fe_ea(n), render_fe(slot_image(src, n)))):
            bg = Image.new("RGBA", im.size, (58, 60, 68, 255))
            bg.alpha_composite(im)
            sh.paste(bg.convert("RGB").resize((W * z, H * z), Image.NEAREST), (x + j * (W * z + 10), y + 22))
    out = a.out or os.path.join(WORK, "sheet-fe.png")
    sh.save(out)
    print(out, sh.size)


def cmd_sheet(a):
    font = _font(15)
    tiles = []
    for lab, n, src, key, name in slots():
        model = src.partition(":")[2]
        left = render_skate(Image.open(src_png(model)), mesh27(mesh_of(model)), 260)
        right = render_skate(slot_image(src, n), mesh_legacy(), 260)
        old = render_skate(Image.open(legacy_png(n)), mesh_legacy(), 260)
        t = Image.new("RGB", (left.size[0], left.size[1] * 3 + 60), (18, 18, 22))
        d = ImageDraw.Draw(t)
        d.text((6, 2), f"{lab} · {n} · {name or key}: было (Legacy) | NHL 27 {model} | в игре", fill=(255, 220, 140),
               font=font)
        for i, im in enumerate((old, left, right)):
            t.paste(im, (0, 20 + i * (im.size[1] + 20)))
        tiles.append(t)
    cols = 2
    tw, th = tiles[0].size
    rows = (len(tiles) + cols - 1) // cols
    sh = Image.new("RGB", (cols * (tw + 10), rows * (th + 10)), (8, 8, 10))
    for i, t in enumerate(tiles):
        sh.paste(t, ((i % cols) * (tw + 10), (i // cols) * (th + 10)))
    out = a.out or os.path.join(WORK, "sheet-skates.png")
    sh.save(out)
    print(out, sh.size)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("build")
    s.add_argument("ids", nargs="*", help="модели NHL 27 (ccm_jetspeed_ft6); без них — все слоты плана")
    s.add_argument("--out")
    s = sub.add_parser("sheet")
    s.add_argument("--out")
    sub.add_parser("fe-fit", help="подбор FE_POSES по рамкам силуэта превью EA")
    s = sub.add_parser("fe-sheet", help="превью редактора: EA → новое по плану")
    s.add_argument("--out")
    a = ap.parse_args()
    if a.cmd == "fe-fit":
        poses = fe_fit_box()
        light = FE_LIGHT
        print("FE_POSES =", [tuple(round(float(v), 3) for v in q) for q in poses])
        print("FE_LIGHT =", tuple(round(float(v), 3) for v in light))
        return 0
    return {"build": cmd_build, "sheet": cmd_sheet, "fe-sheet": cmd_fe_sheet}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
