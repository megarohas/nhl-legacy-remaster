"""Маски вратарей NHL 27 → маска NHL Legacy (03.11.2026, docs/goalie-masks.md).

Пользователь: «перенос вратарских шлемов Юты, Вегаса и Сиэтла». В Legacy маска вратаря — модель rendering/goaliehelmet/
helmet_<masktype>_<L>.rx2 (masktype 0 — itech, шейдер helmet_goalie_current_itech_high, та же модель EA, что itech в
NHL 27) и рисунок goaliehelmet_<masktype>_<maskid>_cm.rx2 (512² DXT1, maskid 0…291 заняты EA, поле — 9 бит, до 511).
У NHL 27 рисунок маски — character/skater/goalie/helmet/itech/textures/goalie_helmet_itech_<N>_color (2048²), модель —
goalie_helmet_itech_mesh (mat_helmet). Развёртки похожи (купол, затылок, ремни), но не одинаковы, поэтому перенос по 3D:
модель NHL 27 вписывается в рамку модели Legacy по осям (у NHL 27 голова выше и впереди на ~6–8 см, размеры те же до
2 мм), каждый тексель Legacy берёт цвет с ближайшей точки NHL 27 (kit3d.transfer). Новые маски — свободные номера
(план fb/mask_slots.toml: номер Legacy ← номер NHL 27); вратарю маску ставит этап goaliegear (goalie_gear.json →
nhl27_colors, маска по номеру маски вратаря в NHL 27).

  FB_GAME=nhl27 python -m fb.extract "goalie/helmet/itech/.*goalie_helmet_itech_(420|515)_color$" --out masks27
  python -m fb.masks build     # → game/work/nhl27/out/masks/cache/rendering/goaliehelmet/goaliehelmet_0_<id>_cm.rx2 (+ PNG)
  python -m fb.masks sheet     # → game/work/nhl27/out/masks/sheet.png: Legacy (белая 0/120) | NHL 27 | перенос
Первый запуск — с FB_GAME=nhl27 (сетка NHL 27 кэшируется в game/work/nhl27/out/masks/itech27.pkl).
"""
import argparse
import glob
import json
import os
import pickle
import sys
import tomllib

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .cas import REPO
from . import kit3d

PLAN = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mask_slots.toml")
WORK = os.path.join(REPO, "game", "work", "nhl27", "out", "masks")
SRC27 = os.path.join(REPO, "game", "work", "nhl27", "extract", "masks27", "character", "skater", "goalie", "helmet",
                     "itech", "textures")
MESH27 = "content/character/skater/goalie/helmet/itech/components/goalie_helmet_itech_mesh"
LEGACY_BIG = os.path.join(REPO, "game", "other", "legacy", "big")
LEG_MESH = "rendering/goaliehelmet/helmet_{t}_2.rx2"
LEG_TEX = "rendering/goaliehelmet/goaliehelmet_{t}_{i}_cm.rx2"
TEMPLATE_ID = 120                     # шаблон файла рисунка: белая маска EA 0/120 (формат, мипы — как у неё)
SIZE = 512


def plan():
    """[(номер Legacy, тип маски Legacy, номер NHL 27, подпись)] из mask_slots.toml."""
    with open(PLAN, "rb") as f:
        p = tomllib.load(f)["mask"]
    return [(int(k), int(v.get("masktype", 0)), int(v["nhl27"]), v.get("name", "")) for k, v in p.items()]


def legacy_file(rel):
    for d in sorted(os.listdir(LEGACY_BIG)):
        p = os.path.join(LEGACY_BIG, d, *rel.split("/"))
        if os.path.exists(p):
            return p
    raise SystemExit(f"нет {rel} в {LEGACY_BIG}")


def _normals(pos, tri):
    fn = np.cross(pos[tri[:, 1]] - pos[tri[:, 0]], pos[tri[:, 2]] - pos[tri[:, 0]])
    n = np.zeros_like(pos)
    for k in range(3):
        np.add.at(n, tri[:, k], fn)
    return n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)


def mesh27():
    """Модель маски itech NHL 27 (mat_helmet) {'pos', 'uv', 'tri', 'nrm'}; кэш WORK/itech27.pkl."""
    cache = os.path.join(WORK, "itech27.pkl")
    if os.path.exists(cache):
        m = pickle.load(open(cache, "rb"))
    else:
        os.environ.setdefault("FB_GAME", "nhl27")
        from . import heads
        res = {}
        for p in sorted(glob.glob(os.path.join(heads.CAT, "scan", "*.jsonl"))):
            for line in open(p, encoding="utf-8"):
                if '"k": "res"' in line and "/goalie/helmet/itech/" in line and '"ofs"' in line:
                    r = json.loads(line)
                    res.setdefault(r["name"], r)
        heads._res = res
        s = heads.mesh(MESH27)["sections"]["mat_helmet"]
        m = {"pos": np.asarray(s["pos"], np.float64)[:, :3], "uv": np.asarray(s["uv0"], np.float64)[:, :2],
             "tri": np.asarray(s["tri"], np.int64)}
        os.makedirs(WORK, exist_ok=True)
        pickle.dump(m, open(cache, "wb"))
    return dict(m, nrm=_normals(m["pos"], m["tri"]))


def mesh_legacy(t=0):
    sys.path.insert(0, os.path.join(REPO, "tools"))
    import rw4mesh as rm
    p = legacy_file(LEG_MESH.format(t=t))
    L = rm.Mesh(open(p, "rb").read(), p)
    m = {"pos": np.asarray(L.pos, np.float64)[:, :3], "uv": np.asarray(L.uv, np.float64)[:, :2],
         "tri": np.asarray(L.tris, np.int64)}
    m["nrm"] = np.asarray(L.nrm, np.float64)[:, :3] if len(L.nrm) else _normals(m["pos"], m["tri"])
    return m


CAGE_UV = 0.03                        # у NHL 27 решётка — в той же сетке: прутья — острова развёртки тоньше этого по v
#                                       (полосы v 0,34–0,45); у Legacy решётка — отдельная модель cage_*, без рисунка маски.
#                                       Без исключения серый цвет прутьев ложился полосой на лоб и подбородок (лист 03.11)


def shell27():
    """Модель NHL 27 без прутьев решётки (связные куски, у которых развёртка по v уже CAGE_UV)."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    m = mesh27()
    pos, tri, uv = m["pos"], m["tri"], m["uv"]
    _, gid = np.unique(np.round(pos, 5), axis=0, return_inverse=True)
    gid = gid.reshape(-1)
    n = gid.max() + 1
    e = np.concatenate([tri[:, [0, 1]], tri[:, [1, 2]], tri[:, [0, 2]]])
    _, lab = connected_components(coo_matrix((np.ones(len(e)), (gid[e[:, 0]], gid[e[:, 1]])), shape=(n, n)),
                                  directed=False)
    tl = lab[gid[tri[:, 0]]]
    keep = np.ones(len(tri), bool)
    for c in np.unique(tl):
        v = np.unique(tri[tl == c])
        if np.ptp(uv[v, 1]) < CAGE_UV:
            keep[tl == c] = False
    return dict(m, tri=tri[keep])


def fitted27(t=0):
    """Модель NHL 27 без решётки, вписанная в рамку модели Legacy по осям (сдвиг и масштаб по каждой оси)."""
    a, b = shell27(), mesh_legacy(t)
    used = np.unique(a["tri"])
    lo, hi = a["pos"][used].min(0), a["pos"][used].max(0)
    LO, HI = b["pos"].min(0), b["pos"].max(0)
    pos = LO + (a["pos"] - lo) / (hi - lo) * (HI - LO)
    return dict(a, pos=pos, nrm=_normals(pos, a["tri"]))


def convert(n27, t=0):
    """Рисунок маски NHL 27 № n27 → RGBA SIZE² в развёртке маски Legacy типа t (вне развёртки — ближайший тексель)."""
    from scipy import ndimage as ndi
    p = os.path.join(SRC27, f"goalie_helmet_itech_{n27}_color.png")
    if not os.path.exists(p):
        raise SystemExit(f"нет {p}: FB_GAME=nhl27 python -m fb.extract \"goalie/helmet/itech/.*goalie_helmet_itech_"
                         f"({n27})_color$\" --out masks27")
    tex = kit3d.load_tex(p)
    img, mk, _d, _i = kit3d.transfer(tex, fitted27(t), mesh_legacy(t), SIZE, 2)
    img = np.asarray(img, np.float64)[..., :3]
    mk = np.asarray(mk, bool)
    if mk.shape != img.shape[:2]:
        mk = np.asarray(Image.fromarray(mk.astype(np.uint8) * 255).resize(img.shape[1::-1], Image.NEAREST)) > 0
    _, (iy, ix) = ndi.distance_transform_edt(~mk, return_indices=True)
    img = img[iy, ix]
    return Image.fromarray(np.dstack([np.clip(np.round(img), 0, 255).astype(np.uint8),
                                      np.full(img.shape[:2], 255, np.uint8)]), "RGBA")


def write_rx2(img, t, mid, cache):
    """RGBA → goaliehelmet_<t>_<mid>_cm.rx2 по шаблону белой маски EA (растр переименовывается на номер mid)."""
    sys.path.insert(0, os.path.join(REPO, "tools"))
    import teamart as ta
    import kitpaint as kp
    tpl = legacy_file(LEG_TEX.format(t=t, i=TEMPLATE_ID))
    rw = ta.Rw4(open(tpl, "rb").read(), tpl)
    ren = rw.rename(f"{t}_{TEMPLATE_ID}", f"{t}_{mid}")
    tx = rw.textures[0]
    w, h = tx.layout.levels[0][:2]
    kp.tex_replace(rw, tx, img.convert("RGBA").resize((w, h), Image.LANCZOS).tobytes(), w, h)
    q = os.path.join(cache, *LEG_TEX.format(t=t, i=mid).split("/"))
    os.makedirs(os.path.dirname(q), exist_ok=True)
    open(q, "wb").write(rw.bytes())
    return q, ren


def cmd_build(a):
    os.makedirs(WORK, exist_ok=True)
    cache = os.path.join(WORK, "cache")
    for mid, t, n27, name in plan():
        img = convert(n27, t)
        img.save(os.path.join(WORK, f"goaliehelmet_{t}_{mid}.png"))
        q, ren = write_rx2(img, t, mid, cache)
        print(f"{t}/{mid} ← NHL 27 itech {n27} ({name}) → {q}" + (f"; растры: {ren}" if ren else ""))


def _render(m, tex, ang, frame, width=240):
    sys.path.insert(0, os.path.join(REPO, "tools"))
    os.environ.setdefault("PHOTOS_SOURCE", "nhl24")
    import scans24 as S
    part = {"pos": m["pos"], "nrm": m["nrm"], "uv": m["uv"], "tri": m["tri"],
            "tex": np.asarray(tex.convert("RGB")), "twosided": True, "spec": 0.25}
    return S.render([part], np.radians(ang), width=width, frame=frame)


def cmd_sheet(a):
    sys.path.insert(0, os.path.join(REPO, "tools"))
    import teamart as ta
    import kitpaint as kp
    try:
        font = ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", 14)
    except OSError:
        font = ImageFont.load_default()
    L = mesh_legacy()
    F = fitted27()
    rw = ta.Rw4(open(legacy_file(LEG_TEX.format(t=0, i=TEMPLATE_ID)), "rb").read(), "")
    w, h, px = kp.tex_decode(rw, rw.textures[0])
    white = Image.fromarray(np.frombuffer(bytes(px), np.uint8).reshape(h, w, 4))
    frame = (-0.16, 0.16, 1.58, 1.95)
    rows = []
    for mid, t, n27, name in plan():
        new = Image.open(os.path.join(WORK, f"goaliehelmet_{t}_{mid}.png"))
        src = Image.open(os.path.join(SRC27, f"goalie_helmet_itech_{n27}_color.png"))
        ims = [_render(L, white, ang, frame) for ang in (20, 70)] + \
              [_render(F, src, ang, frame) for ang in (20, 70)] + [_render(L, new, ang, frame) for ang in (20, 70)]
        W = sum(i.size[0] + 3 for i in ims)
        r = Image.new("RGB", (W + 12, ims[0].size[1] + 22), (16, 16, 20))
        x = 0
        for k, i in enumerate(ims):
            r.paste(i, (x + (12 if k >= 2 else 0) + (12 if k >= 4 else 0) // 2, 22))
            x += i.size[0] + 3
        ImageDraw.Draw(r).text((4, 2), f"{name}: Legacy сейчас (белая 0/{TEMPLATE_ID}) | NHL 27 itech {n27} | "
                                       f"в Legacy 0/{mid}", fill=(255, 220, 140), font=font)
        rows.append(r)
    W = max(r.size[0] for r in rows)
    o = Image.new("RGB", (W, sum(r.size[1] + 4 for r in rows)), (0, 0, 0))
    y = 0
    for r in rows:
        o.paste(r, (0, y))
        y += r.size[1] + 4
    out = os.path.join(WORK, "sheet.png")
    o.save(out)
    print(out, o.size)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("build", help="рисунки масок плана → WORK/cache (дерево cache:) и PNG")
    sub.add_parser("sheet", help="лист: Legacy сейчас | NHL 27 | перенос")
    a = ap.parse_args()
    return {"build": cmd_build, "sheet": cmd_sheet}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
