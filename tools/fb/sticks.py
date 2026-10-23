"""Клюшки NHL 27 → NHL Legacy (playerstick_<N>_cm, 1024×128): перенос текстуры с общей модели клюшки NHL 27 на общую
модель Legacy, листы сравнения и пакет. Что в каком слоте и имена — fb/stick_slots.toml; в игру — edge_kit pack (pack())
и kitport install, как формы. Документация — docs/sticks.md.

Устройство (разбор 23.10.2026, game/work/equipment27/proposal.md):
- Legacy: одна модель на всех — rendering/playerstick/playerstick_H_2 (H — хват; 0 — левый), лента — отдельная сетка
  playersticktape_H_2 (набалдашник и середина крюка — со своей текстурой sticktape_<цвет>_cm); бренд — только текстура
  rendering/playerstick/texlib_<N>.rx2 (playerstick_<N>_cm, 1024×128 DXT1), N = exhibitionskaterequipment.stick;
- NHL 27: тоже одна модель — content/character/skater/player/stick/common/components/player_stick_left_shaft_mesh
  (древко, 266 вершин) и _blade_mesh (крюк, 120), текстура модели — player_stick_<бренд>_<линия>_<модель>_color
  1024×256; обе сетки — в той же системе координат, что у Legacy (древко по x от −0,08 до 1,59 м, крюк по z до 0,21):
  перенос — параметрический (mapping): древко по длине и углу вокруг своей оси, крюк по (x, z) своей стороны, одно
  соответствие на все клюшки.

  python -m fb.sticks build [МОДЕЛЬ…] [--out DIR]        # PNG 1024×128 в развёртке Legacy (без моделей — все слоты плана)
  python -m fb.sticks sheet [--out FILE]                 # лист плана: NHL 27 | в игре (Legacy), лицо и обратная сторона
  python -m fb.sticks sheet --pairs A=105:bauer_vapor_flylite_base,…   # лист: нынешняя Legacy N | NHL 27 на Legacy

Источник: выгрузка FB_GAME=nhl27 python -m fb.extract "/player_stick_(bauer|ccm|…)_[a-z0-9_]+_color$" --out gear27
(game/work/nhl27/extract/gear27), сетки NHL 27 — fb.heads.mesh (PS5), кэш — game/work/equipment27/stick27_meshes.pkl.
"""
import argparse
import glob
import os
import pickle
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .cas import REPO
from . import kit3d

WORK = os.path.join(REPO, "game", "work", "equipment27")
SRC27 = os.path.join(REPO, "game", "work", "nhl27", "extract", "gear27")
LEGACY_BIG = os.path.join(REPO, "game", "other", "legacy", "big")
LEG_MESH = os.path.join(LEGACY_BIG, "renderboot", "rendering", "playerstick", "playerstick_0_2.rx2")
LEG_TEX = os.path.join(LEGACY_BIG, "cacherender", "rendering", "playerstick", "texlib_{}.rx2")
MESH27 = "content/character/skater/player/stick/common/components/player_stick_left_{}_mesh"
SIZE = (1024, 128)
SLOTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stick_slots.toml")
STICK_REL = "rendering/playerstick/texlib_{}.rx2"


def slots():
    """План stick_slots.toml → [(буква редактора, N, from, key, name)] в порядке каталога (A, B, … AA)."""
    import tomllib
    with open(SLOTS, "rb") as f:
        plan = tomllib.load(f)["slot"]
    out = []
    for i, (n, s) in enumerate(plan.items()):
        lab = chr(65 + i) if i < 26 else chr(65 + i - 26) * 2
        kind, _, src = s["from"].partition(":")
        if kind not in ("nhl27", "legacy") or not src:
            raise SystemExit(f"{SLOTS}: слот {n}: from {s['from']!r} — nhl27:<модель> или legacy:<N>")
        out.append((lab, int(n), s["from"], s.get("key"), s.get("name")))
    return out


def slot_image(src):
    """Текстура слота по полю from: nhl27:<модель> — перенос, legacy:<N> — оригинал Legacy. -> RGBA 1024×128."""
    kind, _, v = src.partition(":")
    if kind == "legacy":
        return Image.open(legacy_png(int(v))).convert("RGBA").resize(SIZE, Image.BOX)
    return convert(v)


def pack(man, cache):
    """Клюшки плана в пакет (edge_kit pack): texlib_<N>.rx2 по шаблону архива Legacy, запись type stick и имена —
    в man["loc"] (nhl24.py build пишет их в локализацию накладки). Слоты плана заменяют прежние записи пакета (клюшки
    NHL 24 из fb.pilot sticks — у тех же N). -> число."""
    import hashlib
    from . import pack as P
    n = 0
    for lab, num, src, key, name in slots():
        rel = STICK_REL.format(num)
        tpl = P.legacy_has(rel)
        if not tpl:
            print(f"  клюшка {lab} ({num}): нет {rel} в архивах Legacy")
            continue
        q = os.path.join(cache, *rel.split("/"))
        P.write_rx2_rgba(tpl, slot_image(src), q)
        e = {"file": rel, "type": "stick", "md5": hashlib.md5(open(q, "rb").read()).hexdigest(),
             "size": os.path.getsize(q), "action": "replace",
             "note": f"клюшка {lab}: {src} (fb.sticks, stick_slots.toml)" + (f" — «{name}»" if name else "")}
        man["files"] = [x for x in man["files"] if x["file"] != rel] + [e]
        if key and name:
            man.setdefault("loc", {})[key] = name
        n += 1
    return n


def meshes27():
    """Древко и крюк NHL 27 одной сеткой {'pos', 'uv', 'tri', 'nrm'} (кэш — stick27_meshes.pkl)."""
    cache = os.path.join(WORK, "stick27_meshes.pkl")
    if os.path.exists(cache):
        m27 = pickle.load(open(cache, "rb"))
    else:
        os.environ.setdefault("FB_GAME", "nhl27")
        from . import heads
        import json
        res = {}
        for p in sorted(glob.glob(os.path.join(heads.CAT, "scan", "*.jsonl"))):
            for line in open(p, encoding="utf-8"):
                if '"k": "res"' in line and "stick/common/components/player_stick_left_" in line and '"ofs"' in line:
                    r = json.loads(line)
                    res.setdefault(r["name"], r)
        heads._res = res
        m27 = {MESH27.format(k).split("/")[-1]: heads.mesh(MESH27.format(k)) for k in ("shaft", "blade")}
        os.makedirs(WORK, exist_ok=True)
        pickle.dump(m27, open(cache, "wb"))
    pos, uv, tri = [], [], []
    for k, sec in (("player_stick_left_shaft_mesh", "mat_shaft"), ("player_stick_left_blade_mesh", "mat_blade")):
        s = m27[k]["sections"][sec]
        off = sum(len(p) for p in pos)
        pos.append(np.asarray(s["pos"], np.float64)[:, :3])
        uv.append(np.asarray(s["uv0"], np.float64)[:, :2])
        tri.append(np.asarray(s["tri"], np.int64) + off)
    m = {"pos": np.concatenate(pos), "uv": np.concatenate(uv), "tri": np.concatenate(tri)}
    m["nrm"] = _normals(m["pos"], m["tri"])
    return m


def mesh_legacy():
    sys.path.insert(0, os.path.join(REPO, "tools"))
    import rw4mesh as rm
    L = rm.Mesh(open(LEG_MESH, "rb").read())
    m = {"pos": np.asarray(L.pos, np.float64)[:, :3], "uv": np.asarray(L.uv, np.float64)[:, :2],
         "tri": np.asarray(L.tris, np.int64)}
    m["nrm"] = np.asarray(L.nrm, np.float64)[:, :3] if len(L.nrm) else _normals(m["pos"], m["tri"])
    return m


def _normals(pos, tri):
    fn = np.cross(pos[tri[:, 1]] - pos[tri[:, 0]], pos[tri[:, 2]] - pos[tri[:, 0]])
    n = np.zeros_like(pos)
    for k in range(3):
        np.add.at(n, tri[:, k], fn)
    return n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)


def src_png(model):
    """PNG текстуры клюшки NHL 27 по имени модели (bauer_vapor_flylite_base)."""
    f = glob.glob(os.path.join(SRC27, "**", f"player_stick_{model}_color.png"), recursive=True)
    if not f:
        raise SystemExit(f"нет выгрузки player_stick_{model}_color в {SRC27}")
    return f[0]


def legacy_png(n):
    """Нынешняя текстура слота Legacy N → PNG (teamart decode, кэш в WORK/legacy)."""
    out = os.path.join(WORK, "legacy", f"playerstick_texlib_{n}.png")
    if not os.path.exists(out):
        import subprocess
        os.makedirs(os.path.dirname(out), exist_ok=True)
        subprocess.run([sys.executable, os.path.join(REPO, "tools", "teamart.py"), "decode", LEG_TEX.format(n), out],
                       check=True, capture_output=True)
    return out


_M = {}
X_BLADE = 1.37                     # м: дальше по x — крюк (у NHL 27 крюк с 1,384, древко до 1,412; у Legacy — одна сетка)


def _axis(m):
    """Ось древка: середина габарита сечения (y, z) по x (полосы 5 см; медиана вершин восьмигранника попадала в угол).
    -> f(x) -> (y, z)."""
    p = m["pos"]
    sh = p[:, 0] < X_BLADE
    xs = np.arange(p[sh, 0].min(), p[sh, 0].max() + 0.05, 0.05)
    yc, zc, xc = [], [], []
    for x0 in xs:
        k = sh & (np.abs(p[:, 0] - x0) < 0.05)
        if k.sum() >= 4:
            xc.append(x0)
            yc.append((p[k, 1].min() + p[k, 1].max()) / 2)
            zc.append((p[k, 2].min() + p[k, 2].max()) / 2)
    return lambda x: (np.interp(x, xc, yc), np.interp(x, xc, zc))


def _theta(p, ax):
    yc, zc = ax(p[:, 0])
    return np.degrees(np.arctan2(p[:, 2] - zc, p[:, 1] - yc))


def _grids27(src):
    """Сетки поиска UV NHL 27: древко — по (угол вокруг своей оси, x), крюк — по (x, z) для каждой стороны (знак
    нормали по y)."""
    from .edge_kit import _raster
    p, uv, tri = src["pos"], src["uv"], src["tri"]
    ax = _axis(src)
    th = _theta(p, ax)
    cx = p[tri].mean(1)[:, 0]
    tsh = tri[cx < X_BLADE + 0.04]
    g_sh = _raster(tsh, th, p[:, 0], uv, -180, 180, -0.12, 1.45, 1.0, 0.002)
    fn = np.cross(p[tri[:, 1]] - p[tri[:, 0]], p[tri[:, 2]] - p[tri[:, 0]])
    fy = fn[:, 1] / np.maximum(np.linalg.norm(fn, axis=1), 1e-12)
    g_bl = {}
    for sgn in (1, -1):
        tb = tri[(cx > X_BLADE - 0.03) & (fy * sgn > 0.5)]
        g_bl[sgn] = _raster(tb, p[:, 0] * 100, p[:, 2], uv, 130, 165, -0.03, 0.23, 0.1, 0.001)
    return ax, g_sh, g_bl


def mapping():
    """UV NHL 27 для каждого текселя развёртки Legacy (SIZE × 2): древко — по длине и углу вокруг оси (у Legacy ось на
    2,4 см ниже по z, чем у NHL 27: ближайшая точка путала грани — растяжки по краям), крюк — по (x, z) своей стороны;
    не нашлось — ближайшая точка (kit3d.project). -> (uv (H, W, 2), маска)."""
    if "map" in _M:
        return _M["map"]
    from .edge_kit import _lookup
    src, dst = _M.setdefault("src", meshes27()), _M.setdefault("dst", mesh_legacy())
    W, H = SIZE[0] * 2, SIZE[1] * 2
    tid, bar = kit3d.raster_uv(dst, (W, H))
    mask = tid >= 0
    t, b = tid[mask], bar[mask]
    T = dst["tri"]
    P = (b[:, :, None] * dst["pos"][T[t]]).sum(1)
    Nn = (b[:, :, None] * dst["nrm"][T[t]]).sum(1)
    Nn /= np.maximum(np.linalg.norm(Nn, axis=1, keepdims=True), 1e-12)
    ax27, g_sh, g_bl = _grids27(src)
    axL = _axis(dst)
    uv = np.zeros((len(P), 2))
    ok = np.zeros(len(P), bool)
    sh = P[:, 0] < X_BLADE
    if sh.any():
        u_, o_ = _lookup(g_sh, _theta(P[sh], axL), P[sh, 0], -180, 1.0, -0.12, 0.002)
        uv[sh], ok[sh] = u_, o_
    for sgn in (1, -1):
        k = ~sh & (Nn[:, 1] * sgn > 0.5)
        if k.any():
            u_, o_ = _lookup(g_bl[sgn], P[k, 0] * 100, P[k, 2], 130, 0.1, -0.03, 0.001)
            uv[k], ok[k] = u_, o_
    if (~ok).any():                                    # кромки крюка и прочее — ближайшая точка
        vt, vb, _ = kit3d.project(P[~ok], Nn[~ok], src)
        uv[~ok] = (vb[:, :, None] * src["uv"][src["tri"][vt]]).sum(1)
    out = np.zeros((H, W, 2))
    out[mask] = uv
    _M["map"] = (out, mask)
    print(f"  клюшка: древко по (x, угол) {int((sh & ok).sum())}, крюк по (x, z) {int((~sh & ok).sum())}, "
          f"ближайшей точкой {int((~ok).sum())} текселей")
    return _M["map"]


def convert(model):
    """Текстура клюшки NHL 27 → RGBA 1024×128 в развёртке Legacy (вне развёртки — ближайший тексель, для мипов)."""
    from scipy import ndimage as ndi
    uv, mask = mapping()
    tex = np.asarray(Image.open(src_png(model)).convert("RGBA")).astype(np.float64)
    col = kit3d.sample_bilinear(tex, uv[..., 0][mask], uv[..., 1][mask])
    img = np.zeros(uv.shape[:2] + (4,))
    img[mask] = col
    _, (iy, ix) = ndi.distance_transform_edt(~mask, return_indices=True)
    img = img[iy, ix]
    img[..., 3] = 255
    im = Image.fromarray(np.clip(np.round(img), 0, 255).astype(np.uint8), "RGBA")
    return im.resize(SIZE, Image.BOX)


def render_stick(tex_img, width=900, x0=0.55, angles=(0, 90, 180, 270), nhl27=False):
    """Клюшка с текстурой: древко от x0 до конца крюка, повороты вокруг оси древка (лицо, кромка, обратная сторона,
    кромка); модель Legacy, nhl27 — своя модель NHL 27 (текстура NHL 27 как есть, для сравнения). -> RGB."""
    sys.path.insert(0, os.path.join(REPO, "tools"))
    import scans24 as S
    if "dst" not in _M:
        _M["src"], _M["dst"] = meshes27(), mesh_legacy()
    m = _M["src" if nhl27 else "dst"]
    ax = _axis(m)
    yc, zc = ax(np.array([0.7]))
    tex = np.asarray(tex_img.convert("RGB"))
    rows = []
    for ang in angles:
        r = np.radians(ang)
        Rx = np.array([[1, 0, 0], [0, np.cos(r), -np.sin(r)], [0, np.sin(r), np.cos(r)]])
        q = (m["pos"] - np.array([0, yc[0], zc[0]])) @ Rx.T
        n = m["nrm"] @ Rx.T
        pos = q[:, [0, 2, 1]] * np.array([1.0, 1.0, -1.0])     # длина — x кадра, «вверх» — z, к камере — −y
        nrm = n[:, [0, 2, 1]] * np.array([1.0, 1.0, -1.0])
        part = {"pos": pos, "nrm": nrm, "uv": m["uv"], "tri": m["tri"], "tex": tex, "twosided": True}
        rows.append(S.render([part], 0.0, width, frame=(x0, 1.62, -0.05, 0.23)))
    out = Image.new("RGB", (rows[0].size[0], sum(r.size[1] for r in rows)), (30, 30, 34))
    y = 0
    for r in rows:
        out.paste(r, (0, y))
        y += r.size[1]
    return out


def cmd_build(a):
    out = a.out or os.path.join(WORK, "out")
    os.makedirs(out, exist_ok=True)
    if a.ids:
        for model in a.ids:
            convert(model).save(os.path.join(out, f"stick_{model}.png"))
            print(model, "->", os.path.join(out, f"stick_{model}.png"))
        return
    for lab, n, src, key, name in slots():
        p = os.path.join(out, f"texlib_{n}.png")
        slot_image(src).save(p)
        print(f"{lab:2s} {n:3d} {src:40s} «{name}» -> {p}")


def _font(size):
    try:
        return ImageFont.truetype("C:/Windows/Fonts/segoeuib.ttf", size)
    except OSError:
        return ImageFont.load_default()


def sheet_plan(out):
    """Лист плана: слот (буква, N, имя), слева — исходник (NHL 27 на своей модели; legacy — оригинал), справа — что
    будет в игре (на модели Legacy); лицо и обратная сторона. Две колонки слотов."""
    font = _font(17)
    tiles = []
    for lab, n, src, key, name in slots():
        kind, _, v = src.partition(":")
        if kind == "nhl27":
            left = render_stick(Image.open(src_png(v)), 700, -0.1, (0, 180), nhl27=True)
        else:
            left = render_stick(Image.open(legacy_png(int(v))), 700, -0.1, (0, 180))
        right = render_stick(slot_image(src), 700, -0.1, (0, 180))
        t = Image.new("RGB", (left.size[0] * 2 + 10, left.size[1] + 26), (18, 18, 22))
        d = ImageDraw.Draw(t)
        d.text((6, 3), f"{lab} · {n} · {name}", fill=(255, 220, 140), font=font)
        d.text((left.size[0] + 16, 3), ("NHL 27 → " if kind == "nhl27" else "Legacy → ") + "в игре",
               fill=(140, 220, 255), font=font)
        t.paste(left, (0, 26))
        t.paste(right, (left.size[0] + 10, 26))
        tiles.append(t)
    tw, th = tiles[0].size
    rows = (len(tiles) + 1) // 2
    sh = Image.new("RGB", (tw * 2 + 14, rows * (th + 8)), (8, 8, 10))
    for i, t in enumerate(tiles):
        sh.paste(t, ((i // rows) * (tw + 14), (i % rows) * (th + 8)))
    sh.save(out)
    print(out, sh.size)


def cmd_sheet(a):
    if not a.pairs:
        return sheet_plan(a.out or os.path.join(WORK, "sheet-plan.png"))
    font = _font(18)
    pairs = []
    for p in a.pairs.split(","):
        lab, _, rest = p.partition("=")
        n, _, model = rest.partition(":")
        pairs.append((lab, int(n), model))
    tiles = []
    for lab, n, model in pairs:
        old = render_stick(Image.open(legacy_png(n)), 700)
        new = render_stick(convert(model), 700)
        t = Image.new("RGB", (old.size[0] * 2 + 12, old.size[1] + 28), (18, 18, 22))
        d = ImageDraw.Draw(t)
        d.text((6, 4), f"{lab}: Legacy {n}", fill=(255, 220, 140), font=font)
        d.text((old.size[0] + 18, 4), f"→ NHL 27 {model}", fill=(140, 220, 255), font=font)
        t.paste(old, (0, 28))
        t.paste(new, (old.size[0] + 12, 28))
        tiles.append(t)
    W = tiles[0].size[0]
    H = sum(t.size[1] + 6 for t in tiles)
    sh = Image.new("RGB", (W, H), (10, 10, 12))
    y = 0
    for t in tiles:
        sh.paste(t, (0, y))
        y += t.size[1] + 6
    out = a.out or os.path.join(WORK, "sheet-sticks.png")
    sh.save(out)
    print(out, sh.size)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("build")
    s.add_argument("ids", nargs="*", help="модели NHL 27 (bauer_vapor_flylite_base); без них — все слоты плана")
    s.add_argument("--out")
    s = sub.add_parser("sheet")
    s.add_argument("--pairs", help="метка=N:модель через запятую (A=108:bauer_nexus_tracer_base); без — лист плана")
    s.add_argument("--out")
    a = ap.parse_args()
    return {"build": cmd_build, "sheet": cmd_sheet}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
