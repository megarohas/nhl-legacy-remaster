"""Свитер NHL 24 (крой adidas, 2017+) → сетки свитера NHL Legacy (.rx2) — пилот 15.10.2026 (docs/nhl24-uniforms.md §14).

Геометрия и развёртка — NHL 24, поэтому текстура комплекта NHL 24 садится как есть (2048 → 1024), без переноса через
3D и без кривизны ворота. Кости и веса — с ближайшей точки свитера Legacy стиля 1 (Edge) того же варианта
(заправка, наплечники; вратарь — своя сетка; установленная у пользователя, с весами края спины NHL 10 — «jersey10»):
барицентры её треугольника, по 4 сильнейших кости. Нормаль — NHL 24,
касательная — вдоль +u развёртки (как у Legacy: бинормаль игра не хранит, cross(n, t) — к −v). Треугольники —
полосами по одному с разрывом 0xFFFF (как у EA — тип 6), порядок обхода — как у Legacy (наружу).

У всех комплектов одного стиля общие сетки, поэтому пилот пишется в слот стиля 0 (ретро-сетки, ими рисуются
комплекты 2006/07 и винтажные): комплекты стиля 1 (Edge — все нынешние) не меняются. Детализации: Legacy _2 (ближняя)
← NHL 24 lod0, _0 ← lod1, _3 ← lod2. Файлы — в раскладке cache: (rendering/jersey/…).

  python -m fb.jersey_mesh map                       # варианты Legacy ↔ NHL 24: профиль низа (заправка), близость
  python -m fb.jersey_mesh build [--out DIR]         # 30 сеток jersey_<вратарь>_0_<h>_<t>_<p>_<lod>.rx2
  python -m fb.jersey_mesh preview TEX.png OUT.png [--out DIR]   # Legacy Edge и пилот: спереди, сзади, ворот, руки вверх
  python -m fb.jersey_mesh kit --club C --kit home --legacy 1_A_V --slot 0_A_V --font-dir DIR   # комплект слота

Ассеты NHL 24 — только для личного использования: сетки и картинки — в game/work/ (не в git).
"""
import argparse
import os
import struct
import sys

import numpy as np
from PIL import Image, ImageDraw

from . import kit3d
from .cas import REPO

sys.path.insert(0, os.path.join(REPO, "tools"))
import rw4mesh as rw  # noqa: E402

rw.use_game("legacy")

OUT = os.path.join(REPO, "game", "work", "legacy-data", "models", "adidas")
N24 = "content/character/skater/player/jersey/adidas/components/player_jersey_adidas_{tuck}_{size}_lod{lod}_mesh"
N24_GOALIE = "content/character/skater/goalie/jersey/adidas/components/goalie_jersey_adidas_notuck_lod{lod}_mesh"
LEG = "rendering/jersey/jersey_{g}_{s}_{h}_{t}_{p}_{lod}.rx2"
TUCKS = ("notuck", "fulltuck", "lefttuck", "righttuck")
SIZES = ("large", "small")
LODS = {2: 0, 0: 1, 3: 2}          # детализация Legacy (файл _L) ← lod NHL 24
STYLE_SRC, STYLE_DST = 1, 0        # кости — со стиля 1, пишем в слот стиля 0
SKATER_T, SKATER_P = range(4), range(2)
GOALIE_H = range(2)                # рука ловушки


def skater_rel(t, p, lod, style):
    return LEG.format(g=0, s=style, h=2, t=t, p=p, lod=lod)


def goalie_rel(h, lod, style):
    return LEG.format(g=1, s=style, h=h, t=0, p=0, lod=lod)


# Установленные сетки пользователя (cache:) главнее архива: у свитеров стоит мод весов края спины NHL 10
# (docs/player-models.md, «jersey10») — кости и веса берём с них, чтобы край висел так же.
CACHE = os.path.join(REPO, "nhl-legacy-port", "userdata", "cache", "guest")


def legacy(rel, installed=True):
    p = os.path.join(CACHE, *rel.split("/"))
    m = rw.Mesh.load(p) if installed and os.path.exists(p) else rw.Mesh.game(rel)
    d = {"pos": np.array([p[:3] for p in m.pos], dtype=np.float64), "uv": np.array(m.uv, dtype=np.float64),
         "tri": np.array(m.tris, dtype=np.int64), "nrm": kit3d._unit(np.array(m.nrm, dtype=np.float64)),
         "bones": np.array(m.bones, dtype=np.int64), "weights": np.array(m.weights, dtype=np.float64)}
    return m, d


_N24 = {}


def nhl24(name):
    if name not in _N24:
        _N24[name] = kit3d.load_nhl24(name)
    return _N24[name]


def mean_dist(src, dst):
    """Средняя и 95-я перцентиль расстояния от вершин src до поверхности dst (той же стороны), м."""
    _, _, d = kit3d.project(src["pos"], src["nrm"], dst)
    return float(d.mean()), float(np.percentile(d, 95))


# ---------------------------------------------------------------- соответствие вариантов

# Заправка Legacy t → NHL 24 — по профилю низа (нижняя точка по полосам x, `map`): t0 — навыпуск, t1 — заправлен
# слева (+x), t2 — справа (−x), t3 — весь. Средняя близость поверхностей заправку не различает (заправленный край
# близок к поверхности незаправленного). Наплечники p → размер: плечо p0 1,691 м, p1 1,708; small 1,712, large 1,723.
TUCK_OF = {0: "notuck", 1: "lefttuck", 2: "righttuck", 3: "fulltuck"}
SIZE_OF = {0: "small", 1: "large"}
HEM_BANDS = (-0.3, -0.1, 0.1, 0.25)


def hem_profile(pos):
    """Нижняя точка свитера в полосах x шириной 10 см (м) — отличает заправку."""
    return [round(float(pos[(pos[:, 0] > x0) & (pos[:, 0] < x0 + 0.1)][:, 1].min()), 3) for x0 in HEM_BANDS]


def variant_map():
    """Вариант Legacy (t, p) → (средняя близость, 95 %, tuck, size) NHL 24."""
    out = {}
    for t in SKATER_T:
        for p in SKATER_P:
            _, leg = legacy(skater_rel(t, p, 2, STYLE_SRC))
            md, p95 = mean_dist(leg, nhl24(N24.format(tuck=TUCK_OF[t], size=SIZE_OF[p], lod=0)))
            out[(t, p)] = (md, p95, TUCK_OF[t], SIZE_OF[p])
    return out


# ---------------------------------------------------------------- кости и веса

def skin_from(dst, src):
    """Кости и веса вершин dst (сетка NHL 24) — с ближайшей точки src (сетка Legacy с bones/weights): веса трёх вершин
    треугольника по барицентрам, сложенные по костям; 4 сильнейших, сумма 1."""
    tri, bar, dist = kit3d.project(dst["pos"], dst["nrm"], src)
    T = src["tri"][tri]
    bones, weights = [], []
    for i in range(len(tri)):
        acc = {}
        for k in range(3):
            vi = T[i, k]
            for b, w in zip(src["bones"][vi], src["weights"][vi]):
                if w > 0:
                    acc[int(b)] = acc.get(int(b), 0.0) + bar[i, k] * w
        top = sorted(acc.items(), key=lambda x: -x[1])[:4]
        s = sum(w for _, w in top) or 1.0
        bones.append([b for b, _ in top])
        weights.append([w / s for _, w in top])
    return bones, weights, dist


# ---------------------------------------------------------------- сборка .rx2

def strips(tris):
    """Треугольники → индексы полос: по одному треугольнику, разрыв 0xFFFF (первый в полосе — прямой обход)."""
    idx = []
    for a, b, c in tris:
        if idx:
            idx.append(rw.STRIP_RESTART)
        idx += [int(a), int(b), int(c)]
    return idx


def build_one(n24, skin_src_rel, dst_rel):
    """Сетка dst_rel (файл Legacy слота, его секции и шейдер) с геометрией n24; кости — с skin_src_rel."""
    _, src = legacy(skin_src_rel)
    base = rw.Mesh.game(dst_rel)
    bones, weights, dist = skin_from(n24, src)
    tv, _ = kit3d.vertex_tangents(n24)
    P, N, UV, T = n24["pos"], kit3d._unit(n24["nrm"]), np.clip(n24["uv"], 0.0, 1.0), n24["tri"]
    # обход — как у EA в NHL 24 (у навыпуск 100 % треугольников наружу, как у Legacy); у заправленных 11–16
    # треугольников складки «смотрят» против нормалей вершин — их не трогаем, только считаем
    fn = np.cross(P[T[:, 1]] - P[T[:, 0]], P[T[:, 2]] - P[T[:, 0]])
    flip = (fn * N[T].sum(1)).sum(1) < 0
    tmpl = base.vertex_raw(0)
    vb = bytearray()
    for i in range(len(P)):
        b4 = list(bones[i]) + [bones[i][-1]] * (4 - len(bones[i]))
        w4 = list(weights[i]) + [0.0] * (4 - len(weights[i]))
        v = base.pack_vertex(tmpl, pos=P[i], nrm=N[i], tan=tv[i], uv=UV[i], bones=b4, weights=None)
        vb += v
    tmp = rw.Mesh(base.rebuilt(bytes(vb), strips(T)), dst_rel)
    for i in range(tmp.nv):  # веса — точной квантовкой (сумма ровно 255)
        tmp.set_skin(i, bones[i], weights[i])
    data = tmp.bytes()
    chk = rw.Mesh(data, dst_rel)
    assert chk.nv == len(P) and len(chk.tris) == len(T), (chk.nv, len(chk.tris))
    return data, {"nv": chk.nv, "tris": len(chk.tris), "against_nrm": int(flip.sum()), "skin_d_mean": float(dist.mean()),
                  "skin_d95": float(np.percentile(dist, 95))}


def write(out_dir, rel, data):
    p = os.path.join(out_dir, *rel.split("/"))
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "wb") as f:
        f.write(data)
    return p


def cmd_map(a):
    print("низ по полосам x", HEM_BANDS, "(м)")
    for tuck in TUCKS:
        print(f"  NHL 24 {tuck:9}", hem_profile(nhl24(N24.format(tuck=tuck, size="large", lod=0))["pos"]))
    for t in SKATER_T:
        print(f"  Legacy t{t}      ", hem_profile(legacy(skater_rel(t, 0, 2, STYLE_SRC))[1]["pos"]))
    for (t, p), (md, p95, tuck, size) in sorted(variant_map().items()):
        print(f"Legacy t{t} p{p} → {tuck}_{size}: {md * 100:.1f} см (95 % — {p95 * 100:.1f})")


def cmd_build(a):
    vm = variant_map()
    n = 0
    for (t, p), (_, _, tuck, size) in sorted(vm.items()):
        for lod, l24 in LODS.items():
            n24 = nhl24(N24.format(tuck=tuck, size=size, lod=l24))
            data, info = build_one(n24, skater_rel(t, p, 2, STYLE_SRC), skater_rel(t, p, lod, STYLE_DST))
            write(a.out, skater_rel(t, p, lod, STYLE_DST), data)
            n += 1
            print(f"{skater_rel(t, p, lod, STYLE_DST)} ← {tuck}_{size} lod{l24}: {info}")
    for h in GOALIE_H:
        for lod, l24 in LODS.items():
            n24 = nhl24(N24_GOALIE.format(lod=l24))
            data, info = build_one(n24, goalie_rel(h, 2, STYLE_SRC), goalie_rel(h, lod, STYLE_DST))
            write(a.out, goalie_rel(h, lod, STYLE_DST), data)
            n += 1
            print(f"{goalie_rel(h, lod, STYLE_DST)} ← goalie lod{l24}: {info}")
    print(f"{n} сеток → {a.out}")


# ---------------------------------------------------------------- превью: поза «руки вверх»

ARM_L = (48, 49, 50, 52, 53)       # кости рук свитера (первая — плечевой сустав)
ARM_R = (79, 80, 81, 83, 84)


def posed(mesh_d, bones, weights, joints, deg=55.0):
    """Позиции после подъёма обеих рук на deg° вокруг оси Z плечевых суставов (кости руки — как одно целое)."""
    P = mesh_d["pos"]
    out = np.zeros_like(P)
    mats = {}
    for arm, sgn in ((ARM_L, 1.0), (ARM_R, -1.0)):
        # сторона руки: по x сустава (у Legacy +x — левая сторона игрока)
        j = np.array(joints[arm[0]])
        s = np.sign(j[0]) or sgn
        a = np.radians(deg) * s
        R = np.array([[np.cos(a), -np.sin(a), 0], [np.sin(a), np.cos(a), 0], [0, 0, 1]])
        for b in arm:
            mats[b] = (R, j)
    for i in range(len(P)):
        acc = np.zeros(3)
        for b, w in zip(bones[i], weights[i]):
            if w <= 0:
                continue
            if b in mats:
                R, j = mats[b]
                acc += w * (R @ (P[i] - j) + j)
            else:
                acc += w * P[i]
        out[i] = acc
    m = dict(mesh_d)
    m["pos"] = out
    m.pop("_tan", None)
    m.pop("_bit", None)
    # нормали — по позе
    T = m["tri"]
    fn = np.cross(out[T[:, 1]] - out[T[:, 0]], out[T[:, 2]] - out[T[:, 0]])
    nn = np.zeros_like(out)
    for k in range(3):
        np.add.at(nn, T[:, k], fn)
    m["nrm"] = kit3d._unit(nn)
    return m


def label_font(size=17):
    from PIL import ImageFont
    for f in ("C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/arial.ttf"):
        if os.path.exists(f):
            return ImageFont.truetype(f, size)
    return ImageFont.load_default()


def cmd_preview(a):
    skel = rw.Skeleton.game()
    tex24 = kit3d.load_tex(a.tex)
    _, leg = legacy(skater_rel(0, 1, 2, STYLE_SRC))
    leg_tex = kit3d.load_tex(a.legacy_tex) if a.legacy_tex else None
    pilot_m = rw.Mesh.load(os.path.join(a.out, *skater_rel(0, 1, 2, STYLE_DST).split("/")))
    pil = {"pos": np.array([p[:3] for p in pilot_m.pos]), "uv": np.array(pilot_m.uv), "tri": np.array(pilot_m.tris),
           "nrm": kit3d._unit(np.array(pilot_m.nrm))}
    rows = []
    for title, md, tex, bones, weights in (
            ("Legacy Edge (стиль 1)", leg, leg_tex, leg["bones"], leg["weights"]),
            ("пилот: сетка NHL 24 adidas в Legacy", pil, tex24, np.array(pilot_m.bones), np.array(pilot_m.weights))):
        t = tex if tex is not None else np.full((8, 8, 3), 180.0)
        up = posed(md, bones, weights, skel.joints)
        ims = [kit3d.render_lit(md, t, "front", 420), kit3d.render_lit(md, t, "back", 420),
               kit3d.render_lit(md, t, "front", 420, frame=(-0.2, 0.2, 1.42, 1.74)),
               kit3d.render_lit(up, t, "front", 420, frame=(-0.95, 0.95, 0.85, 2.05))]
        rows.append((title, ims))
    W = sum(im.size[0] for im in rows[0][1]) + 10 * 5
    H = sum(max(im.size[1] for im in ims) + 34 for _, ims in rows)
    sheet = Image.new("RGB", (W, H), (24, 24, 28))
    d = ImageDraw.Draw(sheet)
    font = label_font()
    y = 0
    for title, ims in rows:
        d.text((10, y + 6), title, fill=(235, 235, 235), font=font)
        x = 10
        for im in ims:
            sheet.paste(im, (x, y + 30))
            x += im.size[0] + 10
        y += max(im.size[1] for im in ims) + 34
    sheet.save(a.png)
    print(a.png)


# ---------------------------------------------------------------- комплект в развёртке NHL 24

EXTRACT = os.path.join(REPO, "game", "work", "nhl24", "extract")
KITS_OUT = os.path.join(REPO, "game", "work", "nhl24", "out", "kits")
LEG_SM = 16                        # блик ткани Legacy (медиана jersey_sm комплектов EA ≈ 16 из 255)


def n24_tex(club, kit, layer):
    return os.path.join(EXTRACT, f"club_{club}", "character", "skater", "league", "nhl", club, "adidas", kit,
                        f"jersey_adidas_{club}_{kit}_{layer}.png")


def name_map(leg_png, leg_d, dst_d, size=256):
    """Карта мест номера/фамилии (name_*_cm, 256²: синий канал — номер зоны, 255 — фон) из развёртки Legacy в
    развёртку dst: тексели каждой зоны → точка свитера Legacy → ближайшая точка dst → её UV; зона в новой карте —
    прямоугольник по этим точкам (игра берёт прямоугольник зоны из самой карты: у комплектов EA они разные).
    -> (RGBA, {зона: (x0, y0, x1, y1)}, {зона: «вверх» на свитере — к −v (True) у dst})."""
    src = np.asarray(Image.open(leg_png).convert("RGBA"))
    tid, bar = kit3d.raster_uv(leg_d, size)
    out = np.full((size, size, 4), 255, np.uint8)
    rects, up_ok = {}, {}
    P, T, N = leg_d["pos"], leg_d["tri"], leg_d["nrm"]
    tv_d, bv_d = kit3d.vertex_tangents(dst_d)
    for z in sorted(set(src[..., 2][src[..., 2] < 255].tolist())):
        ys, xs = np.nonzero((src[..., 2] == z) & (tid >= 0))
        if len(ys) == 0:
            continue
        tr, bb = T[tid[ys, xs]], bar[ys, xs]
        p = (bb[:, :, None] * P[tr]).sum(1)
        n = kit3d._unit((bb[:, :, None] * N[tr]).sum(1))
        t2, b2, _ = kit3d.project(p, n, dst_d)
        T2 = dst_d["tri"][t2]
        uv = (b2[:, :, None] * dst_d["uv"][T2]).sum(1) * size
        x0, y0 = np.floor(uv.min(0)).astype(int)
        x1, y1 = np.ceil(uv.max(0)).astype(int)
        x0, y0, x1, y1 = max(x0, 0), max(y0, 0), min(x1, size - 1), min(y1, size - 1)
        out[y0:y1 + 1, x0:x1 + 1] = (255, 255, z, 255)
        rects[z] = (int(x0), int(y0), int(x1), int(y1))
        # +v развёртки dst в зоне должна смотреть вниз по свитеру (как у Legacy): бинормаль вдоль −Y
        bvz = (b2[:, :, None] * bv_d[T2]).sum(1).mean(0)
        up_ok[z] = bool(bvz[1] < 0)
    return out, rects, up_ok


def zone_overlay(tex, nm_rgba, alpha=0.6):
    """Текстура с зонами карты номеров поверх (красным; размер карты → размер текстуры) — для проверки на 3D."""
    H, W = tex.shape[:2]
    z = np.asarray(Image.fromarray(nm_rgba).resize((W, H), Image.NEAREST))
    m = z[..., 2] < 255
    out = tex[..., :3].astype(np.float64).copy()
    out[m] = out[m] * (1 - alpha) + np.array([255.0, 30.0, 30.0]) * alpha
    return out


def cmd_kit(a):
    """Комплект клуба NHL 24 (adidas) в развёртке NHL 24 → папка PNG для kitpaint pack под номер слота a.slot
    (стиль 0) + сборка в a.dst (раскладка cache:). Шорты, гетры — из комплекта Legacy a.legacy, шрифт — атлас NHL 24
    из fb.kit_batch (out/kits/<КОД>_<комплект>), меню и шаблон — от слота."""
    import shutil
    import subprocess
    work = os.path.join(REPO, "game", "work", "nhl24", "adidas3d")
    d = os.path.join(work, f"pack_{a.slot}")
    os.makedirs(d, exist_ok=True)
    unpack = lambda kit: os.path.join(work, f"kit_{kit}")  # noqa: E731
    for kit in (a.slot, a.legacy):
        if not os.path.exists(os.path.join(unpack(kit), "kit.json")):
            subprocess.run([sys.executable, os.path.join(REPO, "tools", "kitpaint.py"), "--game", "legacy", "unpack",
                            kit, unpack(kit)], check=True, capture_output=True)
    # свитер: цвет и рельеф NHL 24 как есть (2048 → 1024), блик — ровный, как ткань Legacy
    cm = Image.open(n24_tex(a.club, a.kit, "color")).convert("RGB").resize((1024, 1024), Image.LANCZOS)
    cm.convert("RGBA").save(os.path.join(d, "jersey_cm.png"))
    from .fonts import normal_map
    Image.fromarray(normal_map(n24_tex(a.club, a.kit, "normal"), 1024)).save(os.path.join(d, "jersey_nm.png"))
    sm = np.zeros((1024, 1024, 4), np.uint8)
    sm[..., :3], sm[..., 3] = LEG_SM, 255
    Image.fromarray(sm).save(os.path.join(d, "jersey_sm.png"))
    # карта номеров — из комплекта Legacy (развёртка Edge) в развёртку NHL 24
    _, leg = legacy(skater_rel(0, 1, 2, STYLE_SRC))
    dst = nhl24(N24.format(tuck="notuck", size="large", lod=0))
    nmap, rects, up_ok = name_map(os.path.join(unpack(a.legacy), "name_cm.png"), leg, dst)
    Image.fromarray(nmap).save(os.path.join(d, "name_cm.png"))
    print("зоны номеров (x0, y0, x1, y1 из 256):", rects, "вверх ок:", up_ok)
    # шрифт NHL 24 (fb.kit_batch), шорты и гетры Legacy, меню и kit.json слота
    for f in ("font_cm", "font_nm", "font_sm"):
        shutil.copy2(os.path.join(a.font_dir, f + ".png"), os.path.join(d, f + ".png"))
    for f in ("pant_cm", "pant_nm", "pant_sm", "sock_cm"):
        shutil.copy2(os.path.join(unpack(a.legacy), f + ".png"), os.path.join(d, f + ".png"))
    for f in ("fe.png", "kit.json"):
        shutil.copy2(os.path.join(unpack(a.slot), f), os.path.join(d, f))
    r = subprocess.run([sys.executable, os.path.join(REPO, "tools", "kitpaint.py"), "--game", "legacy", "pack", d,
                        a.slot, a.dst], capture_output=True, text=True, encoding="utf-8", errors="replace")
    print(r.stdout[-1500:], r.stderr[-1500:])
    # проверка: зоны номеров на 3D (пилотная сетка и Legacy Edge со своей картой)
    tex = np.asarray(Image.open(os.path.join(d, "jersey_cm.png")).convert("RGB")).astype(np.float64)
    ltex = np.asarray(Image.open(os.path.join(unpack(a.legacy), "jersey_cm.png")).convert("RGB")).astype(np.float64)
    lmap = np.asarray(Image.open(os.path.join(unpack(a.legacy), "name_cm.png")).convert("RGBA"))
    ims = []
    for md, t, z in ((leg, ltex, lmap), (dst, tex, nmap)):
        ov = zone_overlay(t, z)
        ims.append([kit3d.render_lit(md, ov, v, 360) for v in ("front", "back", "left", "right")])
    W = sum(im.size[0] + 8 for im in ims[0])
    H = sum(row[0].size[1] + 8 for row in ims)
    sheet = Image.new("RGB", (W, H), (24, 24, 28))
    y = 0
    for row in ims:
        x = 0
        for im in row:
            sheet.paste(im, (x, y))
            x += im.size[0] + 8
        y += row[0].size[1] + 8
    p = os.path.join(work, f"zones_{a.slot}.png")
    sheet.save(p)
    print(p)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("map")
    b = sub.add_parser("build")
    b.add_argument("--out", default=OUT)
    p = sub.add_parser("preview")
    p.add_argument("tex")
    p.add_argument("png")
    p.add_argument("--legacy-tex", default=None, help="текстура комплекта Legacy (развёртка Edge) для первой строки")
    p.add_argument("--out", default=OUT)
    k = sub.add_parser("kit")
    k.add_argument("--club", required=True, help="папка клуба NHL 24 (pittsburgh)")
    k.add_argument("--kit", default="home", help="комплект adidas NHL 24 (home, away…)")
    k.add_argument("--legacy", required=True, help="комплект Legacy для шорт, гетр и карты номеров (1_23_0)")
    k.add_argument("--slot", required=True, help="номер слота стиля 0, куда собирать (0_23_0)")
    k.add_argument("--font-dir", required=True, help="папка шрифта NHL 24 из fb.kit_batch (out/kits/PIT_home)")
    k.add_argument("--dst", default=OUT)
    a = ap.parse_args()
    {"map": cmd_map, "build": cmd_build, "preview": cmd_preview, "kit": cmd_kit}[a.cmd](a)


if __name__ == "__main__":
    main()
