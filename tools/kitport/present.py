"""Лист «ставим или правим» по каждой форме слота (подход C) — для решения пользователя, docs/kitport.md §8.1.

    python -m kitport present [--clubs TBL] [--kits home,away] [--name KUCHEROV --number 86 --letter C] [--out DIR]

По листу на форму — compare/kitport/present-<КЛУБ>_<форма>-<дата>.png. Строки листа:
  1. наша форма на сетке Edge слота (цвет и рельеф): перед, спина, бок, ворот крупно; превью меню (fe.png слота);
  2. оригинал источника (NHL 27 / NHL 24) на сетке NHL 24 — те же виды и кадры, без рельефа (развёртка у источника своя);
  3. «одетый» свитер: фамилия, номер на спине и на рукавах, буква капитана — места по карте номеров слота (name_cm.png:
     зона 0 — фамилия, 1 — номер, 2/3 — рукава, 5 — буква, 6 — номер на груди (BUF), 7 — второе место буквы, обведено),
     глифы — из атласа шрифта
     слота (font_cm.png, раскладка EA — fb.jersey_mesh.FONT_ROWS). Приблизительно: высота надписи — высота зоны, по
     центру, шире зоны — сжатие; разрядка фамилии 0,06 высоты букв, без дуги (как раскладывает игра — не разбиралось);
  4. игрок целиком — свитер, шорты, гетры: наш (сетки Legacy) и оригинал (сетки NHL 24); каска цветом из
     tools/legacy_data/nhl24_helmets.json, наклейка на шлем — собранная в слоте (edgekit/slot/cache/rendering/logo),
     атлас шрифта на цвете свитера под фамилией.

Фамилия и номер по умолчанию — звезда клуба (fb.jersey_mesh.STARS), буква — C. Сборка нужна до листа:
`python -m kitport build --club КЛУБ --stages kit,slot`.
"""
import datetime
import json
import os
import subprocess
import sys

import numpy as np

from . import core

KIT_FRAME = (-0.56, 0.56, 0.90, 1.76)        # м: x0, x1, y0, y1 — свитер целиком спереди и сзади
SIDE_FRAME = (-0.30, 0.30, 0.90, 1.76)       # сбоку (x — глубина)
COLLAR_FRAME = (-0.12, 0.12, 1.56, 1.70)     # ворот крупно (как у kitport check)
FIG_FRAME = (-0.56, 0.56, 0.12, 1.78)        # игрок целиком: свитер, шорты, гетры
VIEWS = (("перед", 0, 330, KIT_FRAME), ("спина", 180, 330, KIT_FRAME), ("бок", 90, 180, SIDE_FRAME),
         ("ворот", 0, 260, COLLAR_FRAME))
DRESS_VIEWS = (("спина: фамилия, номер", 180, 330, KIT_FRAME), ("бок: номер на рукаве", 90, 180, SIDE_FRAME),
               ("бок 3/4", 55, 260, (-0.45, 0.45, 0.90, 1.76)), ("перед: буква", 0, 330, KIT_FRAME))
FIG_VIEWS = (("перед", 0, 240), ("спина", 180, 240))
STAR_ALIAS = {"TBL": "TB", "NJD": "NJ", "LAK": "LA", "SJS": "SJ", "UTA": "UTA"}   # коды клубов → ключи jersey_mesh.STARS
LETTER_ZONE, LETTER_ZONE_2 = 5, 7            # буква капитана и её второе место (docs/kitport.md §2.4)
SLEEVE_ZONES = (2, 3)
SLEEVE_ROW = 6                               # малые цифры атласа (строка 379–438) — номер на рукаве
CHEST_ZONE = 6                               # номер на груди (только EA BUF 1_3_x; цифры — как на рукаве, приблизительно)
BG = (24, 24, 28)


def _font(size=13):
    from PIL import ImageFont
    return ImageFont.truetype(os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", "segoeui.ttf"), size)


def zone_rects(name_png):
    """Прямоугольники зон карты номеров 256² (R, G > 128, B = зона): {зона: (x0, y0, x1, y1)}."""
    from PIL import Image
    a = np.asarray(Image.open(name_png).convert("RGBA"))
    yel = (a[..., 0] > 128) & (a[..., 1] > 128)
    out = {}
    for z in sorted(set(a[..., 2][yel].tolist())):
        ys, xs = np.nonzero(yel & (a[..., 2] == z))
        out[z] = (int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max()))
    return out


def dress(d, M, name, number, letter):
    """Текстура свитера слота d с фамилией, номером (спина, рукава) и буквой (зона 5; зона 7 — обведена). -> (RGB
    float, заметки)."""
    from PIL import Image
    from fb import jersey_mesh as J
    t = np.asarray(Image.open(os.path.join(d, "jersey_cm.png")).convert("RGB")).astype(np.float64)
    rects = zone_rects(os.path.join(d, "name_cm.png"))
    gl = J.font_glyphs(os.path.join(d, "font_cm.png"))
    notes = []
    name = "".join(ch for ch in name.upper() if ch.isalpha() and ch.isascii())
    if 0 in rects and name:
        t = J.stamp(t, M, rects[0], J.text_image(gl, None, name))
    big = [gl.get((2 if ch in "01234" else 3, ch)) for ch in number if ch.isdigit()]
    if 1 in rects and big and all(g is not None for g in big):
        hb = max(g.shape[0] for g in big)
        sp = int(0.05 * hb)
        num = np.zeros((hb, sum(g.shape[1] for g in big) + sp * (len(big) - 1), 4), np.uint8)
        x = 0
        for g in big:
            num[hb - g.shape[0]:, x:x + g.shape[1]] = g
            x += g.shape[1] + sp
        t = J.stamp(t, M, rects[1], num)
    for z in SLEEVE_ZONES:
        if z in rects:
            t = J.stamp(t, M, rects[z], J.text_image(gl, SLEEVE_ROW, number, 0.04))
    if CHEST_ZONE in rects:                            # номер на груди (23.10, BUF): у EA BUF 2010–13 — слева на груди
        t = J.stamp(t, M, rects[CHEST_ZONE], J.text_image(gl, SLEEVE_ROW, number, 0.04))
    if letter and LETTER_ZONE in rects:
        t = J.stamp(t, M, rects[LETTER_ZONE], gl[(4 if letter == "C" else 5, letter)])
    if LETTER_ZONE_2 in rects:                         # второе место буквы — контуром (игра ставит туда букву? — не разбиралось)
        x0, y0, x1, y1 = rects[LETTER_ZONE_2]
        k = t.shape[0] // 256
        bx = (slice(y0 * k, (y1 + 1) * k), slice(x0 * k, (x1 + 1) * k))
        edge = np.zeros(t.shape[:2], bool)
        edge[bx] = True
        inner = np.zeros_like(edge)
        inner[y0 * k + 2:(y1 + 1) * k - 2, x0 * k + 2:(x1 + 1) * k - 2] = True
        t[edge & ~inner] = (255, 220, 40)
    notes.append("зоны: " + ", ".join(f"{z}" for z in sorted(rects)))
    return t, notes


def n24_meshes():
    """Сетки NHL 24 (свитер adidas, шорты, гетры) — npz-кэш, читается отдельным процессом (FB_GAME=nhl24)."""
    fn = os.path.join(core.EDGE_WORK, "present_n24_meshes.npz")
    if not os.path.exists(fn):
        code = ("import numpy as np; from fb import kit3d, pilot; j = kit3d.load_nhl24(kit3d.NHL24_JERSEY); "
                "p = kit3d.load_nhl24(pilot.PANT_N24); s = kit3d.load_nhl24(pilot.SOCK_N24); "
                f"np.savez(r'{fn}', jpos=j['pos'], juv=j['uv'], jtri=j['tri'], ppos=p['pos'], puv=p['uv'], "
                "ptri=p['tri'], spos=s['pos'], suv=s['uv'], stri=s['tri'])")
        subprocess.run([sys.executable, "-c", code], cwd=core.TOOLS, check=True,
                       env=dict(os.environ, FB_GAME="nhl24", PYTHONIOENCODING="utf-8"))
    a = np.load(fn)
    return {k: {"pos": a[k + "pos"], "uv": a[k + "uv"][:, :2], "tri": a[k + "tri"]} for k in ("j", "p", "s")}


def helmet_info(code, reg_kit):
    """Цвет каски (зона 1) из nhl24_helmets.json: (RGB или None, откуда)."""
    with open(os.path.join(core.TOOLS, "legacy_data", "nhl24_helmets.json"), encoding="utf-8") as f:
        h = json.load(f)
    e = h.get(code, {}).get(reg_kit)
    if isinstance(e, dict) and e.get("zones"):
        return tuple(e["zones"][0]), "nhl24_helmets.json, зоны"
    if isinstance(e, list):
        return tuple(e), "nhl24_helmets.json"
    return None, "нет записи — шлем прежней формы клуба (база)"


def _decode_logo(data):
    sys.path.insert(0, core.TOOLS)
    import kitpaint as kp
    import rw4mesh as rw
    import teamart as ta
    if data[:8] in (b"chunklzx", b"chunkzip"):
        data = rw.unchunk_any(data)
    rwf = ta.Rw4(data)
    w, h, rgba = kp.tex_decode(rwf, rwf.textures[0])
    return np.frombuffer(bytes(rgba), np.uint8).reshape(h, w, 4)


def decal_rgba(art, variant, slot_style=0):
    """Наклейка на шлем из слота (edgekit/slot/cache/rendering/logo/texlib_A_S_V.rx2) → RGBA или None."""
    p = os.path.join(core.EDGE_WORK, "slot", "cache", "rendering", "logo", f"texlib_{art}_{slot_style}_{variant}.rx2")
    return _decode_logo(open(p, "rb").read()) if os.path.exists(p) else None


def ea_decal_rgba(legacy):
    """Наклейка EA-формы-образца (logo/texlib_<арт>_1_<вариант>: cache: игры — только чтение, иначе архив) → RGBA или
    None — для выбора helmet_logo = legacy."""
    from fb import jersey_mesh as J
    _, art, v = legacy.split("_")
    rel = ("rendering", "logo", f"texlib_{art}_1_{v}.rx2")
    for root in (J.CACHE, os.path.join(core.GAME, "other", "legacy", "big", "cacherender")):
        p = os.path.join(root, *rel)
        if os.path.exists(p):
            return _decode_logo(open(p, "rb").read())
    return None


def decal_panel(dec, bgc):
    from PIL import Image
    di = Image.new("RGBA", (dec.shape[1], dec.shape[0]), (*bgc, 255))
    di.alpha_composite(Image.fromarray(dec))
    return di.convert("RGB").resize((dec.shape[1] * 2, dec.shape[0] * 2), Image.LANCZOS)


def label_img(im, text, font, color=(220, 220, 220)):
    from PIL import Image, ImageDraw
    out = Image.new("RGB", (im.size[0], im.size[1] + 18), BG)
    out.paste(im, (0, 18))
    ImageDraw.Draw(out).text((3, 1), text, fill=color, font=font)
    return out


def row(title, ims, font, gap=6):
    from PIL import Image, ImageDraw
    w = max(sum(i.size[0] + gap for i in ims) + gap, int(font.getlength(title)) + 2 * gap)
    h = max(i.size[1] for i in ims) + 26
    r = Image.new("RGB", (w, h), (14, 14, 16))
    ImageDraw.Draw(r).text((gap, 3), title, fill=(255, 220, 140), font=font)
    x = gap
    for i in ims:
        r.paste(i, (x, 24))
        x += i.size[0] + gap
    return r


def fit_h(im, h):
    return im.resize((max(1, round(im.size[0] * h / im.size[1])), h))


def present_kit(code, kit, d, M, nrm, n24, a, font):
    """Лист одной формы слота d (КЛУБ_форма). -> PIL.Image."""
    import scans24 as S
    from PIL import Image, ImageDraw
    from fb import edge_kit as E, jersey_mesh as J, kit3d, kitsrc, pilot
    from fb.jersey_hybrid import CLUB_NAME
    from .check import font_panel
    spec = E.SLOT_KITS[kit]
    reg = {(r["club"], r["kit"]): r for r in json.load(open(os.path.join(core.TOOLS, "legacy_data", "nhl24_kits.json"),
                                                            encoding="utf-8"))["kits"]}
    r = reg.get((code, spec["kit"]), {})
    tag = f"{E.SLOT_STYLE}_{r.get('art')}_{r.get('variant')}"
    t = np.asarray(Image.open(os.path.join(d, "jersey_cm.png")).convert("RGBA"))
    nm = np.asarray(Image.open(os.path.join(d, "jersey_nm.png")).convert("RGB").resize(t.shape[1::-1])).astype(np.float64)
    jersey = {"pos": M["pos"], "nrm": nrm, "uv": M["uv"], "tri": M["tri"], "tex": t, "nmap": nm, "twosided": True}

    # 1. наша форма
    # словари частей — одни на все виды: S.render кладёт в них float-текстуры и касательные (кэш)
    ims = [label_img(S.render([jersey], np.radians(ang), w, frame=fr), what, font) for what, ang, w, fr in VIEWS]
    fe = os.path.join(d, "fe.png")
    if os.path.exists(fe):
        ims.append(label_img(fit_h(Image.open(fe).convert("RGB"), ims[0].size[1] - 18), "превью меню (fe.png)", font))
    rows = [row(f"1. Наша форма на сетке Edge слота ({tag}, образец Legacy {spec['legacy']})", ims, font)]

    # 2. оригинал источника на сетке NHL 24
    club = CLUB_NAME[code]
    src_png = J.n24_tex(club, kit, "color")
    src_dir = os.path.dirname(src_png)
    folder = kitsrc.folder(kit)
    if os.path.exists(src_png):
        st = np.asarray(Image.open(src_png).convert("RGBA").resize((1024, 1024), Image.LANCZOS))
        nj = S.weld_normals(n24["j"]["pos"], n24["j"]["tri"], S.weld_ids(n24["j"]["pos"]))
        orig = {"pos": n24["j"]["pos"], "nrm": nj, "uv": n24["j"]["uv"], "tri": n24["j"]["tri"], "tex": st, "twosided": True}
        ims = [label_img(S.render([orig], np.radians(ang), w, frame=fr), what, font) for what, ang, w, fr in VIEWS]
        rows.append(row(f"2. Оригинал {E.SOURCE_NAME()}: adidas/{folder} на сетке NHL 24 (цвет, без рельефа; реклама — "
                        "как в источнике)", ims, font))
    else:
        st = None
        rows.append(row(f"2. Оригинал: нет {src_png}", [Image.new("RGB", (200, 40), BG)], font))

    # 3. «одетый» свитер
    dt, notes = dress(d, dict(M, nrm=nrm), a.name, a.number, a.letter)
    dj = dict(jersey, tex=np.dstack([np.clip(dt, 0, 255), np.full(dt.shape[:2], 255.0)]).astype(np.float32))
    ims = [label_img(S.render([dj], np.radians(ang), w, frame=fr), what, font) for what, ang, w, fr in DRESS_VIEWS]
    rows.append(row(f"3. «Одетый»: {a.name} {a.number}, буква {a.letter} — места по карте номеров слота, глифы — атлас "
                    "шрифта слота; приблизительно (высота — по зоне, по центру, без дуги); жёлтый контур — 2-е место "
                    "буквы (зона 7)", ims, font))

    # 4. игрок целиком, каска, наклейка, шрифт
    pL, sL = kit3d.load_legacy(pilot.PANT_L), kit3d.load_legacy(pilot.SOCK_L)

    def tex4(p):
        return np.asarray(Image.open(p).convert("RGBA"))
    pant = dict(pL, tex=tex4(os.path.join(d, "pant_cm.png")), twosided=True)
    pnm = os.path.join(d, "pant_nm.png")
    if os.path.exists(pnm):
        pant["nmap"] = np.asarray(Image.open(pnm).convert("RGB").resize(pant["tex"].shape[1::-1])).astype(np.float64)
    sock = dict(sL, tex=tex4(os.path.join(d, "sock_cm.png")), twosided=True)
    ours = [jersey, pant, sock]
    ims = [label_img(S.render(ours, np.radians(ang), w, frame=FIG_FRAME), f"наш: {what}", font)
           for what, ang, w in FIG_VIEWS]
    if st is not None:
        orig_parts = [orig]
        for k, f in (("p", "pant"), ("s", "sock")):
            fp = os.path.join(src_dir, f"{f}_adidas_{club}_{folder}_color.png")
            if os.path.exists(fp):
                m = n24[k]
                orig_parts.append({"pos": m["pos"], "uv": m["uv"], "tri": m["tri"], "tex": tex4(fp), "twosided": True,
                                   "nrm": S.weld_normals(m["pos"], m["tri"], S.weld_ids(m["pos"]))})
        ims += [label_img(S.render(orig_parts, np.radians(ang), w, frame=FIG_FRAME),
                          f"оригинал: {what}", font) for what, ang, w in FIG_VIEWS]
    hcol, hsrc = helmet_info(code, spec["kit"])
    hh = ims[0].size[1] - 18
    if hcol is not None:
        hp = S.helmet_parts()
        for p in hp[:1]:
            p["tex"] = np.zeros((4, 4, 4), np.uint8) + np.array((*hcol, 255), np.uint8)
        hb = np.vstack([p["pos"] for p in hp])
        lo, hi = hb.min(0), hb.max(0)
        c, half = (lo + hi) / 2, max(hi[0] - lo[0], hi[2] - lo[2], hi[1] - lo[1]) * 0.6
        him = S.render(hp, np.radians(90), 200, frame=(c[2] - half, c[2] + half, c[1] - half, c[1] + half))
        ims.append(label_img(fit_h(him, min(hh, 200)), f"каска {hcol}", font))
    dec = decal_rgba(r.get("art"), r.get("variant"), E.SLOT_STYLE)
    bgc = hcol or (128, 128, 128)
    src_h = spec.get("helmet_logo", "legacy")
    if dec is not None:
        ims.append(label_img(fit_h(decal_panel(dec, bgc), 150), "наклейка (собрана): " + (
            "helmetlogo источника" if src_h == "source" else f"образца {spec['legacy']}"), font))
    if src_h == "source":                              # вариант на выбор: наклейка EA-формы-образца (helmet_logo = legacy)
        ea = ea_decal_rgba(spec["legacy"])
        if ea is not None:
            ims.append(label_img(fit_h(decal_panel(ea, bgc), 150), f"вариант: образца {spec['legacy']}", font))
    ims.append(label_img(font_panel(d, t, 150), "шрифт на цвете под фамилией", font))
    rows.append(row(f"4. Игрок: свитер, шорты, гетры (наш — сетки Legacy, оригинал — NHL 24); каска — {hsrc}", ims, font))

    head = (f"{code} {kit} → {spec['kit']} {tag} «{spec.get('label', '')}»   источник {E.SOURCE_NAME()} adidas/{folder}   "
            f"шорты {spec.get('pant', 'legacy')}, гетры {spec.get('sock')}, наклейка {spec.get('helmet_logo', 'legacy')}"
            f"{'   по умолчанию' if spec.get('default') else '   не одобрена (default нет)'}")
    hf = _font(15)
    W = max(max(rr.size[0] for rr in rows), int(hf.getlength(head)) + 12)
    sheet = Image.new("RGB", (W, sum(rr.size[1] for rr in rows) + 28), (10, 10, 12))
    ImageDraw.Draw(sheet).text((6, 4), head, fill=(255, 255, 255), font=hf)
    y = 28
    for rr in rows:
        sheet.paste(rr, (0, y))
        y += rr.size[1]
    return sheet


def cmd_present(a):
    os.environ.setdefault("PHOTOS_SOURCE", "nhl24")     # scans24 (рендер) читает его при импорте
    sys.path.insert(0, core.TOOLS)
    import scans24 as S
    from fb import edge_kit as E, jersey_mesh as J
    src = core.slot_kits_dir()
    kits = sorted(k for k in os.listdir(src) if os.path.isdir(os.path.join(src, k)))
    if a.clubs:
        kits = [k for k in kits if k.split("_")[0] in a.clubs.split(",")]
    if a.kits:
        kits = [k for k in kits if k.split("_", 1)[1] in a.kits.split(",")]
    if not kits:
        print(f"нет собранных форм в {src}" + (f" для {a.clubs}" if a.clubs else "") +
              " — сначала python -m kitport build --club КЛУБ --stages kit,slot")
        return 1
    font = _font(13)
    M = E.mesh_for(0, 1, 2)                             # полевой, размер 0, lod 2 — сетка слота
    nrm = S.weld_normals(M["pos"], M["tri"], S.weld_ids(M["pos"]))
    n24 = n24_meshes()
    out_dir = a.out or core.COMPARE
    os.makedirs(out_dir, exist_ok=True)
    stamp_ = datetime.datetime.now().strftime("%Y%m%d-%H%M")
    for k in kits:
        code, kit = k.split("_", 1)
        E.use_club(code)
        if kit not in E.SLOT_KITS:
            print(f"{k}: нет в профиле {code} — пропуск")
            continue
        star = J.STARS.get(STAR_ALIAS.get(code, code), ("PLAYER", "19"))
        aa = type(a)(**vars(a))
        aa.name = a.name or star[0]
        aa.number = a.number or star[1]
        sheet = present_kit(code, kit, os.path.join(src, k), M, nrm, n24, aa, font)
        fn = os.path.join(out_dir, f"present-{k}-{stamp_}.png")
        sheet.save(fn)
        print(f"{k}: лист → {fn}")
    return 0
