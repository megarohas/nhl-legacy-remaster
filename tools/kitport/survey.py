"""Обзор форм клубов источника (NHL 27 и др.) на сетке свитера NHL 24: перед, бок (плечо), ворот крупно — для разбора
клубов по типам (ворот со шнуровкой или нет, кокетка: нет / до плеча / на плечо), docs/kitport.md §12.

    python -m kitport survey [--source nhl27] [--clubs chicago,dallas] [--kits default|home,away] [--jobs 8]

--kits default (по умолчанию) — нынешние дом и выезд клуба по базе источника (default_kits), иначе — эти папки.

Текстуры — прямо из дампа по каталогу (без выгрузки клуба), сетка — NHL 24 (развёртка у NHL 27 та же), кэш —
<EDGE_WORK>/survey_mesh.npz. Листы — game/work/<источник>/kit-survey/survey_N.png, по форме — survey/<клуб>_<форма>.png.
"""
import csv
import os
import subprocess
import sys

import numpy as np

from . import core

# формы клуба — по базе источника: дом и выезд по умолчанию (stockteamjerseys стиль 2, isdefault, locstring 0 / 1),
# вариант → папка комплекта. В NHL 27 папки adidas/home и away — прежние формы (времён NHL 24), нынешние — ten/eleven и
# дальше (пользователь, 21.10: «ты рассматриваешь формы NHL 24, а не 27»: ANA, BOS, BUF, CAR, STL, OTT, PHI, SJ, UTA)
WORDS = {0: "home", 1: "away", 2: "three", 10: "ten", 11: "eleven", 12: "twelve", 13: "thirteen", 14: "fourteen",
         15: "fifteen", 16: "sixteen"}
ABBR_FOLDER = {"NYI": "nyi", "NYR": "nyr"}          # остальные — город без пробелов и точек (St. Louis → stlouis)


def default_kits(source):
    """{папка клуба: (дом, выезд)} — комплекты по умолчанию из базы источника (только NHL 27; иначе {})."""
    if source != "nhl27":
        return {}
    sys.path.insert(0, core.TOOLS)
    from roster import nhl27 as N
    db = N.open_db(os.path.join(core.GAME, "work", "nhl27", "db", "nhl_game.db"))
    tm = N.teams(db, {0})
    J = "stockteamjerseys"
    found = {}
    for r in db.live_rows(J):
        t = db.get(J, "teamid", r)
        if t in tm and db.value(J, "style", r) == 2 and db.value(J, "isdefault", r) and db.value(J, "locstring", r) in (0, 1):
            found.setdefault(t, {})[db.value(J, "locstring", r)] = db.value(J, "variant", r)
    out = {}
    for t, v in found.items():
        c = tm[t]
        folder = ABBR_FOLDER.get(c["abbr"]) or c["city"].lower().replace(" ", "").replace(".", "")
        if 0 in v and 1 in v and v[0] in WORDS and v[1] in WORDS:
            out[folder] = (WORDS[v[0]], WORDS[v[1]])
    return out


def mesh_cache():
    """Сетка свитера adidas NHL 24 (позиции, UV, треугольники) — в npz (читается отдельным процессом: FB_GAME=nhl24)."""
    fn = os.path.join(core.EDGE_WORK, "survey_mesh.npz")
    if not os.path.exists(fn):
        code = ("import numpy as np; from fb import kit3d; m = kit3d.load_nhl24(kit3d.NHL24_JERSEY); "
                f"np.savez(r'{fn}', pos=m['pos'], uv=m['uv'], tri=m['tri'])")
        subprocess.run([sys.executable, "-c", code], cwd=core.TOOLS, check=True, env=dict(os.environ, FB_GAME="nhl24"))
    return fn


_ROWS = {}


def tex(source, name):
    """Текстура источника по имени res (каталог textures.csv) → RGBA (PIL)."""
    from fb import extract, source as src, texture
    if not _ROWS:
        with open(os.path.join(src.WORK, "catalog", "textures.csv"), encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if r["ofs"] and r["name"] not in _ROWS:
                    _ROWS[r["name"]] = r
    h = extract.read_header(_ROWS[name])
    data, start = extract.read_chunk(h)
    return texture.decode_mip(h, data, start, data_first=start).convert("RGBA")


def cell(job):
    source, club, kit, mesh_fn, out_dir = job
    os.environ["FB_GAME"] = source
    os.environ["PHOTOS_SOURCE"] = source                 # photos24 (через scans24) сам выставляет FB_GAME по нему
    sys.path.insert(0, core.TOOLS)
    import scans24 as S
    from PIL import Image, ImageDraw
    a = np.load(mesh_fn)
    pos, uv, tri = a["pos"], a["uv"], a["tri"]
    try:
        t = np.asarray(tex(source, f"content/character/skater/league/nhl/{club}/adidas/{kit}/jersey_adidas_{club}_{kit}_color")
                       .resize((1024, 1024)))
    except (KeyError, ValueError, OSError):
        return club, kit, None
    nrm = S.weld_normals(pos, tri, S.weld_ids(pos))
    parts = [{"pos": pos, "nrm": nrm, "uv": uv, "tri": tri, "tex": t, "twosided": True}]
    ims = [S.render([dict(p) for p in parts], np.radians(ang), w, frame=fr) for ang, fr, w in
           ((0, (-0.6, 0.6, 0.9, 1.8), 200), (80, (-0.45, 0.45, 1.3, 1.78), 160), (0, (-0.14, 0.14, 1.52, 1.72), 160))]
    im = Image.new("RGB", (sum(i.size[0] + 2 for i in ims), max(i.size[1] for i in ims) + 14), (24, 24, 28))
    x = 0
    for i in ims:
        im.paste(i, (x, 14))
        x += i.size[0] + 2
    ImageDraw.Draw(im).text((3, 1), f"{club} {kit}", fill=(255, 220, 140))
    fn = os.path.join(out_dir, "survey", f"{club}_{kit}.png")
    os.makedirs(os.path.dirname(fn), exist_ok=True)
    im.save(fn)
    return club, kit, fn


def cmd_survey(a):
    from concurrent.futures import ProcessPoolExecutor
    from PIL import Image
    sys.path.insert(0, core.TOOLS)
    os.environ["FB_GAME"] = a.source                     # до импорта fb в процессах (fb.source читает его при импорте)
    from fb.kit_batch import CLUBS
    dk = default_kits(a.source)
    clubs = a.clubs.split(",") if a.clubs else sorted({c for c, _, _ in CLUBS if c != "arizona"} | {"utah"})
    out_dir = os.path.join(core.GAME, "work", a.source, "kit-survey")
    mesh_fn = mesh_cache()
    pick = lambda c: a.kits.split(",") if a.kits != "default" else dk.get(c, ("home", "away"))
    jobs = [(a.source, c, k, mesh_fn, out_dir) for c in clubs for k in pick(c)]
    print("комплекты:", {c: pick(c) for c in clubs})
    with ProcessPoolExecutor(max_workers=a.jobs) as ex:
        res = list(ex.map(cell, jobs))
    miss = [f"{c} {k}" for c, k, f in res if not f]
    ims = [Image.open(f) for _, _, f in res if f]
    if not ims:
        sys.exit("ни одной формы — проверьте --source и каталог дампа (python tools/eaimport.py status)")
    w, h = ims[0].size
    # обзор части клубов (--clubs) — в свой лист, не поверх общих survey_N.png (21.10: обзор TBL затёр survey_0)
    stem = "survey" + (f"_{'-'.join(clubs)}" if a.clubs else "")
    for part in range(0, len(ims), 16):
        chunk = ims[part:part + 16]
        sheet = Image.new("RGB", (2 * (w + 4), ((len(chunk) + 1) // 2) * (h + 4)), (10, 10, 12))
        for k, im in enumerate(chunk):
            sheet.paste(im, ((k % 2) * (w + 4), (k // 2) * (h + 4)))
        many = not a.clubs or len(ims) > 16
        sheet.save(os.path.join(out_dir, f"{stem}_{part // 16}.png" if many else f"{stem}.png"))
    print(f"форм {len(ims)}, листов {(len(ims) + 15) // 16} → {out_dir}" + (f"; нет: {miss}" if miss else ""))
    return 0
