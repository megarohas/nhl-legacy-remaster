"""Окно наклейки на шлеме Legacy: какая часть текстуры logo_A_S_V_0 (256×128) видна на шлемах полевых, и вписывание
наклейки в это окно (03.11.2026, пользователь после игры: «у Сиэтла не влезает надпись Amazon на шлеме, она обрезается»).

Как шлем берёт наклейку. У сетки rendering/helmet/helmet_<модель>_<LOD>.rx2 две развёртки FLOAT16_2: первая — сама
каска (карты helmet_0_<модель>_*_dm), вторая (uv1) — атлас мест под наклейки. Верхняя половина атласа (v < 0,5) —
трапеция по бокам каски, на неё ложится вся наклейка (v текстуры = 2 v); нижние куски (v 0,7–1) — другие места;
остальная каска — вне атласа (u −1, v 1…2: прозрачный край текстуры). Проверено рендером (`sheet`): на шлеме модели 20
(16 % игроков) Amazon обрезается до «amazo», как увидел пользователь, на модели 21 (56 %) — целиком.

Трапеция у моделей разная: у одной шире справа, у другой — ниже. Правило — «не хуже EA»: окно — пересечение трапеций
тех моделей, на которых родные наклейки EA (стиль 1) видны целиком хотя бы у EA_FIT_MIN из них. Замер 03.11:
21, 20, 23, 19, 18, 24 (89 % полевых) — EA целиком у 50–85 %; на 6, 25 и 1 (11 %) у EA режется большинство (у
модели 6 — треть каждой наклейки), под них не ужимаем. Доли моделей — exhibitionskaterequipment.helmetbrand базы.
Наклейка вписывается в окно целиком: ×k у середины рамки и сдвиг, k — наибольший; влезающая — как есть.

  python -m fb.helmet_window window                 # окно по моделям: доля игроков, сколько текстуры видно
  python -m fb.helmet_window check [--cache DIR]    # наклейки в cache: игры, которые не влезают (доля вне окна)
  python -m fb.helmet_window fit OUT FILE.rx2 [FILE.rx2 …]   # готовые наклейки — в окно (OUT/rendering/logo)
  python -m fb.helmet_window sheet OUT.png FILE.rx2 [FILE.rx2 …] [--fit]   # шлемы частых моделей с наклейкой
  python -m fb.edge_kit helmet --club all           # наклейки форм NHL 27 из исходника — уже в окне (helmet_logo_fit)
"""
import argparse
import glob
import os
import struct
import sys

import numpy as np

from .cas import REPO

sys.path.insert(0, os.path.join(REPO, "tools"))

W, H = 256, 128                    # logo_A_S_V_0
ALPHA_MIN = 64                     # пиксель наклейки — альфа выше (кайма сглаживания — не в счёт)
OUT_TOL = 0.002                    # доля пикселей наклейки вне окна, которая ещё «влезает» (край сглаживания)
SHIFT_MAX = 24                     # тексели: на сколько можно сдвинуть наклейку к середине окна
EA_FIT_MIN = 0.5                   # модель в окне, если на ней целиком видна хотя бы половина наклеек EA (03.11:
#                                    21 — 85 %, 23 — 84, 20 — 75, 24 — 60, 19 — 56, 18 — 50; 25 — 24, 1 — 22, 6 — 1)
FALLBACK_MODELS = (21, 20, 23, 19, 18, 24)   # если базы или наклеек EA нет — по замеру 03.11


def _mesh_uv1(model, lod=0):
    import rw4mesh as R
    R.use_game("legacy")
    m = R.Mesh.game(f"rendering/helmet/helmet_{model}_{lod}.rx2")
    el = [e for e in m.elements if e.tname == "FLOAT16_2"]
    if len(el) < 2:
        return None
    raw = m.f.raw
    u1 = np.array([struct.unpack_from(">2e", raw, m.vo + i * m.stride + el[1].off) for i in range(m.nv)], np.float64)
    return m, u1, np.array([p[:3] for p in m.pos]), np.array(m.tris, np.int64)


def model_window(model, lod=0):
    """Маска H×W: тексели наклейки, видимые на шлеме модели с обеих сторон каски (обе стороны берут одно место атласа,
    но их трапеции у части моделей разные — у 20 справа уже: пересечение)."""
    from PIL import Image, ImageDraw
    got = _mesh_uv1(model, lod)
    if got is None:
        return None
    _, u1, pos, tris = got
    side = np.sign(pos[tris, 0].mean(1))
    out = None
    for s in (1, -1):
        img = Image.new("L", (W, H), 0)
        d = ImageDraw.Draw(img)
        for t in tris[side == s]:
            q = u1[t]
            if q[:, 1].max() > 0.6 or q[:, 0].min() < -0.5:
                continue                                 # не место наклейки (нижние куски атласа, каска вне атласа)
            d.polygon([(x * W, 2 * y * H) for x, y in q], fill=255)
        m = np.asarray(img) > 0
        if m.any():
            out = m if out is None else (out & m)
    return out


def helmet_share(db_dir=None):
    """[(модель, доля полевых)] по убыванию — из exhibitionskaterequipment установленной базы; нет базы — FALLBACK."""
    try:
        from tdb import Tdb
        import scans24 as S
        from . import jersey_mesh as J
        d = db_dir or os.path.join(J.CACHE, "db")
        db = Tdb(open(os.path.join(d, "nhlng.db"), "rb").read(), S.load_meta(os.path.join(d, "nhlng-meta.xml")))
        t = "exhibitionskaterequipment"
        from collections import Counter
        c = Counter(db.get(t, "helmetbrand", r) for r in db.live_rows(t))
        n = sum(c.values())
        return [(m, k / n) for m, k in c.most_common()]
    except Exception as e:                               # noqa: BLE001 — окно и без базы считается
        print(f"  доли шлемов: база не прочитана ({e}) — модели {FALLBACK_MODELS}")
        return [(m, 1 / len(FALLBACK_MODELS)) for m in FALLBACK_MODELS]


_WINDOW = None


def ea_decals():
    """Родные наклейки EA стиля 1 (архив Legacy): [RGBA H×W] с рисунком."""
    out = []
    d = os.path.join(REPO, "game", "other", "legacy", "big", "cacherender", "rendering", "logo")
    for f in sorted(glob.glob(os.path.join(d, "texlib_*_1_*.rx2"))):
        try:
            a = _load_logo(f)
        except Exception:                                # noqa: BLE001
            continue
        if a.shape[:2] == (H, W) and (a[..., 3] > ALPHA_MIN).sum() > 200:
            out.append(a)
    return out


def window(verbose=False):
    """Окно — пересечение окон моделей, на которых видны целиком не меньше EA_FIT_MIN наклеек EA (правило «не хуже
    EA»). Нет наклеек EA — FALLBACK_MODELS."""
    global _WINDOW
    if _WINDOW is not None and not verbose:
        return _WINDOW
    eas = ea_decals()
    win, rows, acc = None, [], 0.0
    for model, share in helmet_share():
        w = model_window(model)
        if w is None:
            rows.append((model, share, None, None, False))
            continue
        ea_ok = float(np.mean([out_frac(a, w) <= OUT_TOL for a in eas])) if eas else None
        use = ea_ok >= EA_FIT_MIN if eas else model in FALLBACK_MODELS
        if use:
            win = w if win is None else (win & w)
            acc += share
        rows.append((model, share, w.mean(), ea_ok, use))
    _WINDOW = win
    if verbose:
        for model, share, f, ea_ok, use in rows:
            print(f"  шлем {model}: {share * 100:.1f} % полевых, " + ("нет uv1" if f is None else
                  f"видно {f * 100:.0f} % текстуры, наклеек EA целиком {ea_ok * 100:.0f} %" if ea_ok is not None else
                  f"видно {f * 100:.0f} % текстуры") + (" — в окне" if use else ""))
        print(f"  в окне — модели {acc * 100:.0f} % полевых")
        ys, xs = np.nonzero(win)
        print(f"  окно: {win.mean() * 100:.0f} % текстуры, рамка x {xs.min()}–{xs.max()}, y {ys.min()}–{ys.max()}")
    return win


def _place(rgba, k, dx, dy):
    """RGBA H×W: рамка по альфе — ×k у её середины (с премультипликацией), сдвиг на (dx, dy) текселей."""
    from PIL import Image
    img = Image.fromarray(rgba, "RGBA")
    bb = img.getbbox()
    part = img.crop(bb)
    nw, nh = max(1, int(round(part.width * k))), max(1, int(round(part.height * k)))
    a = np.asarray(part).astype(np.float64)
    a[..., :3] *= a[..., 3:4] / 255.0
    pm = np.asarray(Image.fromarray(np.clip(np.round(a), 0, 255).astype(np.uint8)).resize((nw, nh), Image.LANCZOS)).astype(np.float64)
    al = np.asarray(part.getchannel("A").resize((nw, nh), Image.LANCZOS)).astype(np.float64)
    pm[..., :3] = np.where(al[..., None] > 0, pm[..., :3] * 255.0 / np.maximum(al[..., None], 1), 0)
    pm[..., 3] = al
    out = Image.new("RGBA", img.size, (0, 0, 0, 0))
    cx, cy = (bb[0] + bb[2]) / 2 + dx, (bb[1] + bb[3]) / 2 + dy
    out.paste(Image.fromarray(np.clip(np.round(pm), 0, 255).astype(np.uint8), "RGBA"),
              (int(round(cx - nw / 2)), int(round(cy - nh / 2))))
    return np.asarray(out)


def out_frac(rgba, win=None):
    win = window() if win is None else win
    m = rgba[..., 3] > ALPHA_MIN
    return float((m & ~win).sum()) / max(1, int(m.sum()))


def fit_params(rgba, win=None):
    """Наклейка H×W×4 → (k, (dx, dy), доля вне окна): уже влезает — (1, (0, 0)); иначе наибольший k (шаг 0,01) и
    сдвиг до SHIFT_MAX текселей, при которых вне окна (с запасом в тексель) не больше OUT_TOL. Сдвиг — наименьший."""
    from scipy import ndimage
    win = window() if win is None else win
    was = out_frac(rgba, win)
    if was <= OUT_TOL:
        return 1.0, (0, 0), was
    m = rgba[..., 3] > ALPHA_MIN
    ys, xs = np.nonzero(m)
    bb = np.nonzero(rgba[..., 3] > 0)                    # рамка — как у place (getbbox: любая альфа)
    cy, cx = (bb[0].min() + bb[0].max() + 1) / 2, (bb[1].min() + bb[1].max() + 1) / 2
    yy, xx = ys + 0.5 - cy, xs + 0.5 - cx
    inside = ndimage.binary_erosion(win, iterations=1)  # запас в тексель (сглаживание при уменьшении)
    shifts = sorted(((dx, dy) for dx in range(-SHIFT_MAX, SHIFT_MAX + 1, 2) for dy in range(-SHIFT_MAX, SHIFT_MAX + 1, 2)),
                    key=lambda s: s[0] ** 2 + s[1] ** 2)
    for k100 in range(100, 30, -1):
        k = k100 / 100
        for dx, dy in shifts:
            py = np.floor(cy + dy + yy * k).astype(int)
            px = np.floor(cx + dx + xx * k).astype(int)
            ok = (py >= 0) & (py < H) & (px >= 0) & (px < W)
            bad = (~ok).sum() + (~inside[py[ok], px[ok]]).sum()
            if bad <= OUT_TOL * len(ys):
                return k, (dx, dy), was
    return 0.3, (0, 0), was


def place(rgba, k, dx, dy):
    """RGBA любого размера: рамка по альфе — ×k у её середины (с премультипликацией), сдвиг на (dx, dy) пикселей."""
    return _place(rgba, k, dx, dy)


def fit(rgba, win=None):
    """Наклейка H×W×4 → (RGBA в окне, k, (dx, dy), доля вне окна было, стало)."""
    win = window() if win is None else win
    k, sh, was = fit_params(rgba, win)
    if k == 1.0 and sh == (0, 0):
        return rgba, k, sh, was, was
    out = _place(rgba, k, *sh)
    return out, k, sh, was, out_frac(out, win)


def _load_logo(path):
    import kitpaint as kp
    import teamart as ta
    rwf = ta.Rw4.load(path)
    t = rwf.textures[0]
    w, h, px = kp.tex_decode(rwf, t)
    return np.frombuffer(bytes(px), np.uint8).reshape(h, w, 4).copy()


def cmd_window(_a):
    window(verbose=True)


def cmd_check(a):
    from . import jersey_mesh as J
    d = os.path.join(a.cache or J.CACHE, "rendering", "logo")
    win = window(verbose=True)
    bad = 0
    for f in sorted(glob.glob(os.path.join(d, "texlib_*.rx2"))):
        try:
            rgba = _load_logo(f)
        except Exception:                                # noqa: BLE001
            continue
        if rgba.shape[:2] != (H, W) or not (rgba[..., 3] > ALPHA_MIN).any():
            continue
        fr = out_frac(rgba, win)
        if fr > OUT_TOL:
            bad += 1
            print(f"  {os.path.basename(f)}: вне окна {fr * 100:.1f} %")
    print(f"не влезают: {bad}")


def fit_file(src, dst=None, win=None):
    """Готовая наклейка (rx2) — в окно: растр 256×128 ×k и сдвиг (повторное уменьшение — немного мягче исходника).
    dst — куда писать (по умолчанию на место). -> строка отчёта; влезающую не пишет."""
    import kitpaint as kp
    import teamart as ta
    rwf = ta.Rw4.load(src)
    t = rwf.textures[0]
    w, h, px = kp.tex_decode(rwf, t)
    if (w, h) != (W, H):
        return f"{w}×{h} — не наклейка шлема, пропуск"
    rgba = np.frombuffer(bytes(px), np.uint8).reshape(h, w, 4).copy()
    out, k, sh, was, now = fit(rgba, win)
    if k == 1.0 and sh == (0, 0):
        return f"влезает (вне окна {was * 100:.1f} %)"
    kp.tex_replace(rwf, t, np.ascontiguousarray(out).tobytes(), w, h)
    open(dst or src, "wb").write(rwf.bytes())
    return f"вне окна {was * 100:.1f} % → ×{k:.2f}, сдвиг {sh} → {now * 100:.1f} %"


def cmd_fit(a):
    """Готовые наклейки — в окно, запись в a.out/rendering/logo (раскладка cache: для kitport put). Для наклеек без
    исходника под рукой (АХЛ 03.11: ahl27 put_helmet вписывал рисунок во всю текстуру; копии наклеек EA у форм с
    helmet_logo = legacy); из исходника лучше — edge_kit helmet (без повторного уменьшения)."""
    win = window(verbose=True)
    dst = os.path.join(a.out, "rendering", "logo")
    os.makedirs(dst, exist_ok=True)
    for f in a.files:
        print(f"  {os.path.basename(f)}:", fit_file(f, os.path.join(dst, os.path.basename(f)), win))


def cmd_sheet(a):
    """Шлемы частых моделей с наклейкой (рендер по uv1, как в игре): 3/4 спереди и бока."""
    import scans24 as S
    from PIL import Image, ImageDraw
    from PIL import ImageFont
    font = ImageFont.truetype(os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", "segoeui.ttf"), 13)
    win = window()
    models = [m for m, _ in helmet_share()][:a.models]
    rows = []
    for f in a.files:
        rgba = _load_logo(f)
        variants = [("как есть", rgba)]
        if a.fit:
            out, k, sh, was, now = fit(rgba, win)
            variants.append((f"в окне: ×{k:.2f}, сдвиг {sh}", out))
        for label, img in variants:
            cells = []
            for model in models:
                got = _mesh_uv1(model)
                if got is None:
                    continue
                m, u1, pos, tris = got
                base = np.array([40, 90, 110], np.float64)
                big = np.zeros((H * 3, W * 3, 4), np.float32)
                big[..., :3] = base
                big[..., 3] = 255
                al = img[..., 3:4] / 255.0
                big[H:2 * H, W:2 * W, :3] = base * (1 - al) + img[..., :3] * al
                uv = np.stack([(u1[:, 0] + 1) / 3, (2 * u1[:, 1] + 1) / 3], -1)
                nrm = S.unit(np.array([n[:3] for n in m.nrm]))
                part = {"pos": pos, "nrm": nrm, "uv": uv, "tri": tris, "tex": big, "spec": 0.2, "twosided": True}
                fr = (-0.16, 0.16, 1.72, 2.02)
                for ang in (90, -90):
                    cells.append(S.render([part], np.radians(ang), width=220, frame=fr))
            row = Image.new("RGB", (sum(c.size[0] for c in cells), cells[0].size[1] + 18), (20, 20, 24))
            x = 0
            for c in cells:
                row.paste(c, (x, 18))
                x += c.size[0]
            ImageDraw.Draw(row).text((4, 1), f"{os.path.basename(f)} — {label}; шлемы {models} (у каждого — правый и левый бок)",
                                     fill=(230, 230, 230), font=font)
            rows.append(row)
    out = Image.new("RGB", (max(r.size[0] for r in rows), sum(r.size[1] for r in rows)), (20, 20, 24))
    y = 0
    for r in rows:
        out.paste(r, (0, y))
        y += r.size[1]
    out.save(a.out)
    print("→", a.out)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    sp.add_parser("window", help="окно по моделям шлема").set_defaults(fn=cmd_window)
    p = sp.add_parser("check", help="наклейки cache:, которые не влезают")
    p.add_argument("--cache")
    p.set_defaults(fn=cmd_check)
    p = sp.add_parser("fit", help="готовые наклейки — в окно на месте (→ OUT/rendering/logo)")
    p.add_argument("out")
    p.add_argument("files", nargs="+")
    p.set_defaults(fn=cmd_fit)
    p = sp.add_parser("sheet", help="рендер шлемов с наклейкой")
    p.add_argument("out")
    p.add_argument("files", nargs="+")
    p.add_argument("--fit", action="store_true", help="и вписанная в окно")
    p.add_argument("--models", type=int, default=3, help="сколько частых моделей шлема (по умолчанию 3)")
    p.set_defaults(fn=cmd_sheet)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
