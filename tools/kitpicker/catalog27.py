"""Каталог форм NHL 27: какие уже стоят в NHL Legacy, каких ещё нет — для выбора следующих (docs/kit-catalog27.md).

Пишет ОДИН файл game/work/kits27-catalog/index.html: все комплекты свитеров league/nhl из дампа NHL 27 (32 клуба НХЛ,
крои adidas, Reebok Edge, 90-е, плюс All-Star), у каждого рендер перед + спина на сетке NHL 24 того же кроя, короткий
код, тип формы по базе NHL 27, пометка «в порте» / «похожая в порте» / «нет», галочки и кнопка «Скопировать выбор».
Картинки — внутри файла (JPEG base64), страница открывается без сервера. Только локально: рендеры из ассетов EA —
не публиковать и не класть в git (game/ в .gitignore).

    cd tools
    P=../game/work/nhl24/venv/Scripts/python.exe
    $P kitpicker/catalog27.py build                     # рендеры (кэш — game/work/kits27-catalog/cache) и страница
    $P kitpicker/catalog27.py build --clubs BOS,CHI     # только эти клубы перерисовать (страница — всегда целиком)
    $P kitpicker/catalog27.py build --force             # перерисовать и готовые
    $P kitpicker/catalog27.py page                      # только страница по готовому кэшу
    $P kitpicker/catalog27.py list [--missing]          # таблица в консоль: код, тип, статус

Откуда что:
- комплекты — каталог текстур дампа game/work/nhl27/catalog/textures.csv (fb.catalog), имена
  content/character/skater/league/nhl/<клуб>/<крой>/<комплект>/jersey_<крой>_<клуб>_<комплект>_color;
- тип — строка stockteamjerseys базы NHL 27 game/work/nhl27/db/nhl_game.db: стиль по крою (90-е 0, Reebok 1,
  adidas 2), вариант = номер в имени папки (ten = 10), подпись locstring и isdefault (LOC27); имя особой формы по
  папке (twentytwo / twentythree — Reverse Retro) или по заметке kit_rules.toml [third_source], если форма совпала с
  той формой NHL 24; иначе «название не прочитано» (тип не определён);
- «в порте» — формы NHL 27 на стиле 2: профиль клуба tools/fb/edge_clubs.toml (source = nhl27, source_kits: какая
  папка ушла в Home / Away (NHL 27)); «та же» / «похожая» — текстура совпала (средняя разница миниатюры всей развёртки
  и зоны герба ниже SAME / CREST_SAME или SIMILAR / CREST_SIMILAR) с формой, которая уже стоит: другой папкой NHL 27
  того же клуба в порте или формой NHL 24 из реестра
  tools/legacy_data/nhl24_kits.json, не убранной в tools/legacy_data/kit_removed.json (текстуры NHL 24 —
  game/work/nhl24/extract/gallery24).
"""
import argparse
import base64
import csv
import html
import json
import os
import re
import sys
import time
import tomllib

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TOOLS = os.path.join(ROOT, "tools")
OUT = os.path.join(ROOT, "game", "work", "kits27-catalog")
CACHE = os.path.join(OUT, "cache")
NHL27 = os.path.join(ROOT, "game", "work", "nhl27")
TEX_CSV = os.path.join(NHL27, "catalog", "textures.csv")
DB27 = os.path.join(NHL27, "db", "nhl_game.db")
GALLERY24 = os.path.join(ROOT, "game", "work", "nhl24", "extract", "gallery24")
PROFILES = os.path.join(TOOLS, "fb", "edge_clubs.toml")
KIT_RULES = os.path.join(TOOLS, "fb", "kit_rules.toml")
REGISTRY = os.path.join(TOOLS, "legacy_data", "nhl24_kits.json")
REMOVED = os.path.join(TOOLS, "legacy_data", "kit_removed.json")
MESH24 = "content/character/skater/player/jersey/{cut}/components/player_jersey_{cut}_notuck_large_lod0_mesh"

RX = re.compile(r"^content/character/skater/league/nhl/([a-z0-9]+)/([a-z0-9]+)/([a-z0-9]+)/jersey_\2_\1_\3_color$")

# 32 клуба НХЛ: папка дампа → код (как tools/fb/kit_batch.CLUBS; Аризоны в NHL 27 нет, есть Юта)
CLUBS = [("anaheim", "ANA"), ("boston", "BOS"), ("buffalo", "BUF"), ("calgary", "CGY"), ("carolina", "CAR"),
         ("chicago", "CHI"), ("colorado", "COL"), ("columbus", "CBJ"), ("dallas", "DAL"), ("detroit", "DET"),
         ("edmonton", "EDM"), ("florida", "FLA"), ("losangeles", "LAK"), ("minnesota", "MIN"), ("montreal", "MTL"),
         ("nashville", "NSH"), ("newjersey", "NJD"), ("nyi", "NYI"), ("nyr", "NYR"), ("ottawa", "OTT"),
         ("philadelphia", "PHI"), ("pittsburgh", "PIT"), ("sanjose", "SJS"), ("seattle", "SEA"), ("stlouis", "STL"),
         ("tampabay", "TBL"), ("toronto", "TOR"), ("utah", "UTA"), ("vancouver", "VAN"), ("vegas", "VGK"),
         ("washington", "WSH"), ("winnipeg", "WPG")]
SPECIAL = {"atlantic": "All-Star: Atlantic", "central": "All-Star: Central", "metropolitan": "All-Star: Metropolitan",
           "pacific": "All-Star: Pacific", "east": "All-Star: East", "west": "All-Star: West", "legends": "Legends"}
CUTS = {"adidas": "adidas", "rbk": "Reebok Edge 2007–17", "nineties": "90-е"}
CUT_ORDER = ("adidas", "rbk", "nineties")
CUT_SHORT = {"adidas": "", "rbk": "rbk-", "nineties": "90s-"}
CUT_STYLE = {"nineties": 0, "rbk": 1, "adidas": 2}        # стиль строки stockteamjerseys NHL 27 (сверено по числу папок)

_UNITS = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve",
          "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen"]
WORDS = {w: i for i, w in enumerate(_UNITS)}
WORDS.update({"twenty" + (w if i else ""): 20 + i for i, w in enumerate(_UNITS[:10])})
WORDS.update({"home": 0, "away": 1})

# Подпись формы в меню NHL 27 (locstring). Текст подписей из локализации NHL 27 не читали: 0/1/2 — как в Legacy
# (Home / Away / Alternate, kitpicker/build.py LOC_LABEL); 10/11/12 стоят у вариантов 0/1/2 — папок home/away/two, это
# прежние формы времён NHL 24 (kitport/survey.py), поэтому «прошлая»; 6 — своя подпись (ключ Vintage_*), особая форма.
LOC27 = {0: "домашняя", 1: "выездная", 2: "третья", 10: "прошлая домашняя", 11: "прошлая выездная",
         12: "прошлая альтернативная", 3: "ретро: домашняя", 4: "ретро: выездная", 5: "ретро: альтернативная"}
FOLDER_NAMES = {22: "Reverse Retro", 23: "Reverse Retro"}  # папки twentytwo / twentythree (fb/gallery.py KIT_NAMES: «2022» / «2023»; год выпуска не сверяли)

VIEW_W = 270            # ширина одного вида, px (перед и спина рядом)
JPEG_Q = 80
SIG = 48                # миниатюра текстуры для сравнения форм
# Средняя разница миниатюр (0–255), подбор 03.11.2026 на BOS, NJD, CHI (docs/kit-catalog27.md): одна и та же форма в
# двух папках — 0–4; та же форма NHL 24 и NHL 27 с другими нашивками — 12–19 (BOS home 13,7); разные формы — от 17.
SAME = 5.0              # ниже — та же форма
SIMILAR = 15.0          # ниже — похожая (нашивки, отделка): сравнить глазами
# Тело развёртки не различает гербы (VAN two и home NHL 24: 8,9, гербы разные), поэтому отдельно — зона герба
# (jersey_mesh.CREST_ZONE: u 0,37–0,635, v 0,61–0,86) и свои пороги.
CREST_ZONE = (0.37, 0.635, 0.61, 0.86)
CREST_SIG = 32
CREST_SAME = 12.0
CREST_SIMILAR = 15.0
BG = (118, 122, 130)    # средне-серый фон: видны и белые, и чёрные свитера


def die(msg):
    raise SystemExit(f"catalog27: {msg}")


def key_of(club, cut, kit):
    return f"{club}/{cut}/{kit}"


def code_of(abbr, cut, kit):
    return f"{abbr}-{CUT_SHORT[cut]}{kit}"


# ─── входные данные ────────────────────────────────────────────────────────────────────────────────────────────


def scan_kits():
    """[{club, cut, kit, row}] — все jersey_*_color league/nhl в каталоге текстур NHL 27 (первая строка с данными)."""
    if not os.path.exists(TEX_CSV):
        die(f"нет каталога текстур NHL 27 {TEX_CSV}: сначала FB_GAME=nhl27 python -m fb.catalog (docs/frostbite-sources.md)")
    seen = {}
    with open(TEX_CSV, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            name = r["name"]
            if "/league/nhl/" not in name or not name.endswith("_color"):
                continue
            m = RX.match(name)
            if not m or not r["ofs"]:
                continue
            k = key_of(*m.groups())
            if k not in seen:
                seen[k] = {"club": m.group(1), "cut": m.group(2), "kit": m.group(3), "row": r}
    if not seen:
        die(f"в {TEX_CSV} нет свитеров league/nhl — это каталог NHL 27?")
    return list(seen.values())


def db_rows():
    """{(папка клуба, стиль, вариант): {locstring, isdefault, jerseyindex}} — stockteamjerseys NHL 27, клубы НХЛ."""
    sys.path.insert(0, TOOLS)
    from roster import nhl27 as N
    if not os.path.exists(DB27):
        die(f"нет базы NHL 27 {DB27} (выгрузка — tools/roster/nhl27.py)")
    db = N.open_db(DB27)
    tm = N.teams(db, {0})
    folder_of = {}
    for t, c in tm.items():
        folder_of[t] = {"NYI": "nyi", "NYR": "nyr"}.get(c["abbr"]) or c["city"].lower().replace(" ", "").replace(".", "")
    J = "stockteamjerseys"
    out = {}
    for r in db.live_rows(J):
        t = db.get(J, "teamid", r)
        if t not in folder_of:
            continue
        out[(folder_of[t], db.value(J, "style", r), db.value(J, "variant", r))] = {
            "locstring": db.value(J, "locstring", r), "isdefault": db.value(J, "isdefault", r),
            "jerseyindex": db.value(J, "jerseyindex", r)}
    names = {folder_of[t]: c["name"] for t, c in tm.items()}
    return out, names


def port_kits():
    """Что стоит в порте.

    nhl27: {(папка, крой, комплект): подпись} — источники форм NHL 27 на стиле 2 по профилям edge_clubs.toml;
    nhl24: {код клуба: [(папка NHL 24 'крой/комплект', подпись)]} — формы NHL 24 из реестра, не убранные чисткой."""
    with open(PROFILES, "rb") as f:
        prof = tomllib.load(f)
    with open(KIT_RULES, "rb") as f:
        third = tomllib.load(f).get("third_source", {})
    reg = json.load(open(REGISTRY, encoding="utf-8"))["kits"]
    removed = json.load(open(REMOVED, encoding="utf-8"))["clubs"]
    folder = {code: fold for fold, code in CLUBS}
    nhl27, nhl24 = {}, {}
    for code, p in prof.items():
        if not isinstance(p, dict) or code not in folder:
            continue
        src = p.get("source", "nhl24")
        kits = p.get("source_kits", {})
        for lab in ("home", "away"):
            where = kits.get(lab, lab)
            text = f"{'Home' if lab == 'home' else 'Away'} (NHL 27) — форма Edge по умолчанию"
            if src == "nhl27":
                nhl27[(folder[code], "adidas", where)] = text
            else:                                   # MIN: Edge-формы из текстур NHL 24 тех же папок
                nhl24.setdefault(code, []).append((f"adidas/{where}", text + ", текстура NHL 24"))
    names24 = {"home": "home", "away": "away", "ad_home": "home", "ad_away": "away", "rr22": "twentytwo",
               "rr23": "twentythree"}
    for k in reg:
        code, kit = k["club"], k["kit"]
        if kit.startswith("edge_") or f"{k['style']}_{k['art']}_{k['variant']}" in set(removed.get(code, [])):
            continue
        if kit == "three":
            src = f"adidas/{third.get(code, 'three')}"
        elif kit.startswith("n90_"):
            src = f"nineties/{kit[4:]}"
        elif kit in names24:
            src = f"adidas/{names24[kit]}"
        else:
            continue
        nhl24.setdefault(code, []).append((src, f"форма из NHL 24 «{kit}» ({k['style']}_{k['art']}_{k['variant']})"))
    return nhl27, nhl24


def third_notes():
    """{код клуба: название} — что за форма у клуба в NHL 24 adidas/three, по заметкам kit_rules.toml [third_source]
    («three — Winter Classic 2019»). Ставится форме NHL 27, совпавшей с этой формой NHL 24."""
    out = {}
    for line in open(KIT_RULES, encoding="utf-8"):
        m = re.match(r"^([A-Z]{3})\s*=.*three\s+—\s+((?:Winter|Stadium|Heritage|Reverse|Global)[^);]*)", line)
        if m:
            out[m.group(1)] = m.group(2).strip()
    return out


# ─── рендер (процессы пула) ───────────────────────────────────────────────────────────────────────────────────

_MESH = {}


def _mesh(cut):
    import numpy as np
    if cut not in _MESH:
        fn = os.path.join(CACHE, f"mesh_{cut}.npz")
        a = np.load(fn)
        _MESH[cut] = {"pos": a["pos"], "uv": a["uv"], "tri": a["tri"], "nrm": a["nrm"]}
    return _MESH[cut]


def _decode(row):
    from fb import extract, texture
    h = extract.read_header(row)
    data, start = extract.read_chunk(h)
    if data is None:
        raise ValueError("нет данных текстуры")
    for level in (max(1, start), start):
        try:
            im = texture.decode_mip(h, data, level=level, data_first=start)
            break
        except (ValueError, IndexError):
            im = None
    if im is None:
        raise ValueError("мип не декодируется")
    return im.convert("RGBA").resize((1024, 1024)) if im.size != (1024, 1024) else im.convert("RGBA")


def render_job(job):
    """(ключ, строка каталога, крой, jpg, sig) → (ключ, ошибка или None). Пишет jpg и подпись sig (.npz: тело и герб)."""
    key, row, cut, jpg, sig = job
    os.environ["FB_GAME"] = "nhl27"
    sys.path.insert(0, TOOLS)
    import numpy as np
    from PIL import Image
    from fb import kit3d
    try:
        im = _decode(row)
    except Exception as e:  # noqa: BLE001 — одна битая текстура не должна ронять сборку
        return key, f"{type(e).__name__}: {e}"
    tex = np.asarray(im).astype(np.float64)
    views = [kit3d.render(_mesh(cut), tex, v, VIEW_W, bg=BG, ss=2) for v in ("front", "back")]
    W = VIEW_W * 2 + 4
    card = Image.new("RGB", (W, views[0].size[1]), BG)
    card.paste(views[0], (0, 0))
    card.paste(views[1], (VIEW_W + 4, 0))
    os.makedirs(os.path.dirname(jpg), exist_ok=True)
    card.save(jpg, quality=JPEG_Q, optimize=True)
    body, crest = signature(im)
    np.savez(sig, body=body, crest=crest)
    return key, None


def signature(im):
    """(тело, герб): миниатюра всей развёртки SIG² и зоны герба CREST_SIG² (uint8 RGB)."""
    import numpy as np
    from PIL import Image
    rgb = im.convert("RGB")
    w, h = rgb.size
    u0, u1, v0, v1 = CREST_ZONE
    body = rgb.resize((SIG, SIG), Image.BOX)
    crest = rgb.crop((int(u0 * w), int(v0 * h), int(u1 * w), int(v1 * h))).resize((CREST_SIG, CREST_SIG), Image.BOX)
    return np.asarray(body, dtype=np.uint8), np.asarray(crest, dtype=np.uint8)


def dist(a, b):
    """(разница тела, разница герба) — средняя по каналам, 0–255."""
    import numpy as np
    return (float(np.abs(a[0].astype(np.int16) - b[0]).mean()), float(np.abs(a[1].astype(np.int16) - b[1]).mean()))


def verdict(d):
    """same / similar / None по паре разниц и порогам SAME / SIMILAR, CREST_SAME / CREST_SIMILAR."""
    if d is None:
        return None
    if d[0] < SAME and d[1] < CREST_SAME:
        return "same"
    if d[0] < SIMILAR and d[1] < CREST_SIMILAR:
        return "similar"
    return None


def score(d):
    return max(d[0] / SIMILAR, d[1] / CREST_SIMILAR)


def load_sig(fn):
    import numpy as np
    if not os.path.exists(fn):
        return None
    with np.load(fn) as z:
        return z["body"], z["crest"]


def sig24(src_folder, club_folder):
    """Подпись (signature) текстуры NHL 24 из game/work/nhl24/extract/gallery24 или None."""
    import numpy as np
    from PIL import Image
    cut, kit = src_folder.split("/")
    fn = os.path.join(CACHE, "sig24", f"{club_folder}_{cut}_{kit}.npz")
    if os.path.exists(fn):
        return load_sig(fn)
    png = os.path.join(GALLERY24, "character", "skater", "league", "nhl", club_folder, cut, kit,
                       f"jersey_{cut}_{club_folder}_{kit}_color.png")
    if not os.path.exists(png):
        return None
    body, crest = signature(Image.open(png))
    os.makedirs(os.path.dirname(fn), exist_ok=True)
    np.savez(fn, body=body, crest=crest)
    return body, crest


def paths(k):
    base = os.path.join(CACHE, "img", k["club"], f"{k['cut']}_{k['kit']}")
    return base + ".jpg", base + ".sig.npz"


# ─── сборка данных страницы ───────────────────────────────────────────────────────────────────────────────────


def classify(kits, rows, nhl27, nhl24, notes):
    """Дописывает каждому комплекту: code, abbr, group, type, undetermined, status, status_text, db."""
    folder_code = dict(CLUBS)
    sigs = {key_of(k["club"], k["cut"], k["kit"]): load_sig(paths(k)[1]) for k in kits}
    for k in kits:
        club, cut, kit = k["club"], k["cut"], k["kit"]
        abbr = folder_code.get(club) or SPECIAL.get(club, club)
        k["abbr"] = abbr
        k["code"] = code_of(folder_code.get(club, club.upper()), cut, kit)
        num = WORDS.get(kit)
        k["variant"] = num
        r = rows.get((club, CUT_STYLE.get(cut), num)) if club in folder_code and num is not None else None
        k["db"] = r
        und = False
        if club in SPECIAL:
            group, typ = "allstar", SPECIAL[club]
        elif cut != "adidas":
            group = "retro"
            base = {0: "домашняя", 1: "выездная"}.get(num, f"альтернативная ({kit})")
            typ = f"ретро {CUTS[cut]}: {base}"
        elif r is None:
            group, typ, und = "nodb", f"нет строки в базе NHL 27 ({kit})", True
        elif r["locstring"] == 6 and num in (0, 1):
            # папки home / away со своей подписью: прежние формы клуба (подпись, видимо, с годом — не прочитана)
            group, typ = "previous", ("прошлая домашняя" if num == 0 else "прошлая выездная") + " (своя подпись)"
        elif r["locstring"] == 6:
            group = "special"
            typ = FOLDER_NAMES.get(num)
            if not typ:
                typ, und = f"особая ({kit}): название не прочитано", True
        elif r["locstring"] in LOC27:
            group = "main" if r["locstring"] in (0, 1, 2) else "previous"
            typ = LOC27[r["locstring"]]
            if r["isdefault"]:
                typ += ", по умолчанию в NHL 27"
        else:
            group, typ, und = "special", f"подпись {r['locstring']} ({kit})", True
        k.update(group=group, type=typ, undetermined=und)
        # статус
        here = nhl27.get((club, cut, kit))
        k["match"] = None
        if here:
            k.update(status="port", status_text=here)
            continue
        best, best_d, note = None, None, None
        me = sigs.get(key_of(club, cut, kit))
        if me is not None:
            cands = [(f"{code_of(folder_code.get(club, ''), cut2, kit2)}, {text}", sigs.get(key_of(c2, cut2, kit2)))
                     for (c2, cut2, kit2), text in nhl27.items() if c2 == club and cut2 == cut]
            cands += [(text, sig24(src, club)) for src, text in nhl24.get(folder_code.get(club, ""), [])
                      if src.split("/")[0] == cut]
            for text, o in cands:
                if o is not None:
                    d = dist(me, o)
                    if best_d is None or score(d) < score(best_d):
                        best, best_d = text, d
            # название особой формы: заметка kit_rules.toml [third_source] о форме NHL 24 adidas/three этого клуба
            n = notes.get(folder_code.get(club, ""))
            o = sig24("adidas/three", club) if n and cut == "adidas" else None
            if o is not None and verdict(dist(me, o)):
                note = n
        if note and k["undetermined"] and group == "special":
            k.update(type=f"{note} (по заметке kit_rules.toml к той же форме NHL 24)", undetermined=False)
        k["match"] = [round(best_d[0], 1), round(best_d[1], 1)] if best_d else None
        v = verdict(best_d)
        if v == "same":
            k.update(status="same", status_text=f"та же форма уже в порте: {best}")
        elif v == "similar":
            k.update(status="similar", status_text=f"похожая в порте (нашивки, отделка — сравните): {best}")
        else:
            k.update(status="missing", status_text="нет в порте")
    # одна и та же форма в двух папках NHL 27 (BOS four = twelve): подсказка, чтобы не выбрать обе
    for k in kits:
        me = sigs.get(key_of(k["club"], k["cut"], k["kit"]))
        if me is None or k["status"] in ("port", "same"):   # у «та же» двойник уже назван в статусе
            continue
        twins = [o["code"] for o in kits if o is not k and o["club"] == k["club"] and o["cut"] == k["cut"]
                 and o["status"] != "port"
                 and sigs.get(key_of(o["club"], o["cut"], o["kit"])) is not None
                 and verdict(dist(me, sigs[key_of(o["club"], o["cut"], o["kit"])])) == "same"]
        if twins:
            k["twins"] = twins
    return kits


def club_sections(kits):
    order = [c for c, _ in CLUBS] + list(SPECIAL)
    by = {}
    for k in kits:
        by.setdefault(k["club"], []).append(k)
    gorder = {"main": 0, "previous": 1, "special": 2, "nodb": 3, "retro": 4, "allstar": 5}
    for v in by.values():
        v.sort(key=lambda k: (CUT_ORDER.index(k["cut"]) if k["cut"] in CUT_ORDER else 9,
                              0 if k["status"] == "port" else 1,
                              gorder.get(k["group"], 9), k["variant"] if k["variant"] is not None else 99))
    return [(c, by[c]) for c in order if c in by]


def summary(kits):
    nhl = [k for k in kits if k["group"] != "allstar"]
    ad = [k for k in nhl if k["cut"] == "adidas"]
    s = {
        "all": len(kits), "nhl": len(nhl), "adidas": len(ad), "retro": sum(k["group"] == "retro" for k in kits),
        "allstar": sum(k["group"] == "allstar" for k in kits),
        "port": sum(k["status"] == "port" for k in kits), "same": sum(k["status"] == "same" for k in kits),
        "similar": sum(k["status"] == "similar" for k in kits),
        "missing": sum(k["status"] == "missing" for k in kits),
        "missing_adidas": sum(k["status"] == "missing" for k in ad),
        "special": sum(k["group"] == "special" for k in kits),
        "special_missing": sum(k["group"] == "special" and k["status"] == "missing" for k in kits),
        "undetermined": sum(k["undetermined"] for k in kits),
    }
    return s


# ─── страница ─────────────────────────────────────────────────────────────────────────────────────────────────

CSS = """
:root { --bg:#15171b; --panel:#1f2228; --line:#363a43; --text:#eceef1; --dim:#a4a9b3; --port:#3ecf8e; --sim:#e0b04a;
  --miss:#8d93a0; --sel:#6db3ff; --same:#7fd0c8; }
* { box-sizing:border-box; }
html { scroll-padding-top:120px; }
body { margin:0; background:var(--bg); color:var(--text); font:14px/1.4 "Segoe UI",system-ui,sans-serif; }
header { position:sticky; top:0; z-index:5; background:#101215; border-bottom:1px solid var(--line); padding:8px 16px; }
.top { display:flex; flex-wrap:wrap; align-items:center; gap:6px 14px; }
h1 { font-size:17px; margin:0; }
.sum { color:var(--dim); font-variant-numeric:tabular-nums; }
.sum b { color:var(--text); font-weight:600; }
.sum .p { color:var(--port); } .sum .q { color:var(--same); } .sum .s { color:var(--sim); }
.ctl { display:flex; flex-wrap:wrap; align-items:center; gap:6px 14px; margin-top:6px; }
.ctl label { color:var(--dim); cursor:pointer; display:inline-flex; gap:5px; align-items:center; }
button { font:inherit; color:var(--text); background:#2b2f37; border:1px solid var(--line); border-radius:6px;
  padding:5px 10px; cursor:pointer; }
button:hover { background:#363b45; }
button.main { background:#1d4f86; border-color:#2e6db3; }
button.main:hover { background:#255f9e; }
#msg { color:var(--port); font-size:13px; }
nav { display:flex; gap:2px; margin-top:6px; overflow-x:auto; scrollbar-width:thin; }
nav a { flex:none; color:var(--dim); text-decoration:none; padding:2px 6px; border-radius:4px; font-size:12px; }
nav a:hover { color:var(--text); background:#262a31; }
nav a.has { color:var(--sel); }
main { padding:12px 16px 80px; max-width:1700px; margin:0 auto; }
.help { color:var(--dim); margin:0 0 10px; max-width:110ch; }
.legend { display:flex; flex-wrap:wrap; gap:14px; color:var(--dim); font-size:13px; margin-bottom:6px; }
.dot { display:inline-block; width:10px; height:10px; border-radius:50%; margin-right:5px; vertical-align:middle; }
section { padding:14px 0 6px; border-bottom:1px solid var(--line); }
section h2 { display:flex; flex-wrap:wrap; align-items:baseline; gap:2px 10px; font-size:18px; font-weight:600; margin:0 0 8px; }
section h2 span { color:var(--dim); font-size:13px; font-weight:400; }
h3 { font-size:13px; color:var(--dim); font-weight:600; margin:10px 0 6px; }
.grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(300px,1fr)); gap:8px; }
.card { position:relative; display:flex; flex-direction:column; background:var(--panel); border:2px solid transparent;
  border-radius:8px; overflow:hidden; }
.card.pick { cursor:pointer; }
.card.pick:hover { border-color:#5a6070; }
.card.on { border-color:var(--sel); }
.card input { position:absolute; left:6px; top:6px; width:20px; height:20px; margin:0; accent-color:var(--sel);
  cursor:pointer; z-index:1; }
.card img { display:block; width:100%; height:auto; cursor:zoom-in; }
.txt { padding:5px 8px 7px; }
.code { font-weight:600; font-family:Consolas,monospace; font-size:13px; }
.type { margin-top:1px; }
.st { font-size:12px; margin-top:3px; }
.st.port { color:var(--port); } .st.same { color:var(--same); } .st.similar { color:var(--sim); }
.st.missing { color:var(--miss); }
.twin { color:#c9a0ff; font-size:12px; }
.und { color:#ff9b6b; font-size:12px; }
.meta { color:#7d838e; font-size:11px; margin-top:2px; }
.card.port { opacity:.92; }
.card.port .badge, .card.similar .badge { position:absolute; left:6px; top:6px; font-size:11px; font-weight:600;
  padding:1px 6px; border-radius:4px; background:rgba(16,18,21,.78); }
.card.port .badge { color:var(--port); } .card.similar .badge { color:var(--sim); }
.hide { display:none !important; }
#box { position:fixed; inset:0; background:rgba(0,0,0,.88); display:none; align-items:center; justify-content:center;
  z-index:9; cursor:zoom-out; }
#box img { width:min(96vw,1400px); height:auto; image-rendering:auto; }
#copybox { position:fixed; inset:10% 10% auto 10%; z-index:10; background:#1f2228; border:1px solid var(--line);
  border-radius:8px; padding:12px; display:none; }
#copybox textarea { width:100%; height:50vh; background:#101215; color:var(--text); border:1px solid var(--line);
  font:13px/1.4 Consolas,monospace; }
@media (max-width:640px) { .grid { grid-template-columns:1fr; } }
"""

JS = r"""
(function () {
  var KEY = 'kits27-catalog-v1';
  var cards = Array.prototype.slice.call(document.querySelectorAll('.card'));
  var sel = {};
  try { sel = JSON.parse(localStorage.getItem(KEY) || '{}') || {}; } catch (e) { sel = {}; }
  function save() { try { localStorage.setItem(KEY, JSON.stringify(sel)); } catch (e) {} }
  function count() { return Object.keys(sel).filter(function (k) { return sel[k]; }).length; }
  function refresh() {
    cards.forEach(function (c) {
      var cb = c.querySelector('input');
      if (!cb) return;
      cb.checked = !!sel[c.dataset.key];
      c.classList.toggle('on', cb.checked);
    });
    document.getElementById('n').textContent = count();
    document.querySelectorAll('nav a').forEach(function (a) {
      var club = a.getAttribute('href').slice(1);
      a.classList.toggle('has', cards.some(function (c) { return c.dataset.club === club && sel[c.dataset.key]; }));
    });
    filter();
  }
  function filter() {
    var mode = document.querySelector('input[name=f]:checked').value;
    var retro = document.getElementById('retro').checked;
    cards.forEach(function (c) {
      var d = c.dataset, show = true;
      if (mode === 'missing') show = d.status === 'missing' || d.status === 'similar';
      if (mode === 'special') show = d.group === 'special' || d.group === 'nodb';
      if (mode === 'picked') show = !!sel[d.key];
      if (!retro && d.group === 'retro' && mode !== 'picked') show = false;
      c.classList.toggle('hide', !show);
    });
    document.querySelectorAll('.cutblock').forEach(function (b) {
      b.classList.toggle('hide', !b.querySelector('.card:not(.hide)'));
    });
    document.querySelectorAll('section').forEach(function (s) {
      s.classList.toggle('hide', !s.querySelector('.card:not(.hide)'));
    });
  }
  cards.forEach(function (c) {
    var cb = c.querySelector('input');
    if (!cb) return;
    c.addEventListener('click', function (e) {
      if (e.target.tagName === 'IMG') return;
      if (e.target !== cb) cb.checked = !cb.checked;
      if (cb.checked) sel[c.dataset.key] = 1; else delete sel[c.dataset.key];
      save(); refresh();
    });
  });
  document.querySelectorAll('.card img').forEach(function (im) {
    im.addEventListener('click', function (e) {
      e.stopPropagation();
      document.getElementById('big').src = im.src;
      document.getElementById('box').style.display = 'flex';
    });
  });
  document.getElementById('box').addEventListener('click', function () { this.style.display = 'none'; });
  document.querySelectorAll('input[name=f], #retro').forEach(function (i) { i.addEventListener('change', filter); });
  function text() {
    var lines = [];
    cards.forEach(function (c) {
      if (sel[c.dataset.key]) lines.push(c.dataset.code + '\t' + c.dataset.name + '\t' + c.dataset.type + '\t' + c.dataset.key);
    });
    return 'Формы NHL 27 к переносу (' + lines.length + '):\n' + lines.join('\n') + '\n';
  }
  function fallback(t) {
    var box = document.getElementById('copybox'), ta = box.querySelector('textarea');
    ta.value = t; box.style.display = 'block'; ta.focus(); ta.select();
    var ok = false;
    try { ok = document.execCommand('copy'); } catch (e) {}
    document.getElementById('msg').textContent = ok ? 'Скопировано (' + count() + ')' : 'Выделено — нажмите Ctrl+C';
  }
  document.getElementById('copy').addEventListener('click', function () {
    var t = text();
    if (!count()) { document.getElementById('msg').textContent = 'Ничего не отмечено'; return; }
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(t).then(function () {
        document.getElementById('msg').textContent = 'Скопировано: ' + count() + ' форм — вставьте в чат';
      }, function () { fallback(t); });
    } else { fallback(t); }
  });
  document.getElementById('clear').addEventListener('click', function () {
    if (count() && !confirm('Снять все отметки?')) return;
    sel = {}; save(); refresh();
  });
  document.getElementById('closebox').addEventListener('click', function () {
    document.getElementById('copybox').style.display = 'none';
  });
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') { document.getElementById('box').style.display = 'none';
      document.getElementById('copybox').style.display = 'none'; }
  });
  refresh();
})();
"""


def card_html(k, club_name):
    e = html.escape
    jpg = paths(k)[0]
    if os.path.exists(jpg):
        b64 = base64.b64encode(open(jpg, "rb").read()).decode("ascii")
        img = f'<img loading="lazy" decoding="async" alt="{e(k["code"])}" src="data:image/jpeg;base64,{b64}">'
    else:
        img = '<div style="height:120px;display:flex;align-items:center;justify-content:center;color:#d88">нет картинки</div>'
    pickable = k["status"] != "port"
    cb = '<input type="checkbox" aria-label="выбрать">' if pickable else ""
    badge = {"port": "в порте"}.get(k["status"])
    db = k["db"]
    meta = f"{CUTS.get(k['cut'], k['cut'])} · папка {k['kit']}"
    if db:
        meta += f" · стиль {CUT_STYLE[k['cut']]}, вариант {k['variant']}, подпись {db['locstring']}"
    if k.get("match") is not None and k["status"] != "port":
        meta += f" · разница: тело {k['match'][0]}, герб {k['match'][1]}"
    und = '<div class="und">тип не определён</div>' if k["undetermined"] else ""
    if k.get("twins"):
        und += f'<div class="twin">та же форма, что {e(", ".join(k["twins"]))}</div>'
    cls = f"card {k['status']}" + (" pick" if pickable else "")
    data = (f'data-key="{e(key_of(k["club"], k["cut"], k["kit"]))}" data-club="{e(k["club"])}" data-code="{e(k["code"])}" '
            f'data-name="{e(club_name)}" data-type="{e(k["type"])}" data-group="{k["group"]}" data-status="{k["status"]}"')
    return (f'<div class="{cls}" {data}>{cb}' + (f'<span class="badge">{badge}</span>' if badge and not cb else "")
            + f'{img}<div class="txt"><div class="code">{e(k["code"])}</div><div class="type">{e(k["type"])}</div>'
            f'{und}<div class="st {k["status"]}">{e(k["status_text"])}</div><div class="meta">{e(meta)}</div></div></div>')


def write_page(kits, names):
    s = summary(kits)
    nav, body = [], []
    for club, ks in club_sections(kits):
        code = dict(CLUBS).get(club)
        title = f"{code} — {names.get(club, club)}" if code else SPECIAL.get(club, club)
        name = names.get(club, SPECIAL.get(club, club))
        nav.append(f'<a href="#{club}">{html.escape(code or SPECIAL.get(club, club))}</a>')
        n_port = sum(k["status"] == "port" for k in ks)
        n_miss = sum(k["status"] != "port" for k in ks)
        body.append(f'<section id="{club}"><h2>{html.escape(title)} <span>форм {len(ks)} · в порте {n_port} · '
                    f'нет {n_miss}</span></h2>')
        for cut in CUT_ORDER:
            cks = [k for k in ks if k["cut"] == cut]
            if not cks:
                continue
            body.append(f'<div class="cutblock"><h3>{html.escape(CUTS[cut])}</h3><div class="grid">')
            body.extend(card_html(k, name) for k in cks)
            body.append("</div></div>")
        body.append("</section>")
    stamp = time.strftime("%d.%m.%Y %H:%M")
    page = f"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Формы NHL 27: каталог</title><style>{CSS}</style></head>
<body>
<header>
<div class="top"><h1>Формы NHL 27 → NHL Legacy</h1>
<div class="sum">всего <b>{s['all']}</b> (adidas {s['adidas']}, ретро {s['retro']}, All-Star {s['allstar']}) ·
<span class="p">в порте <b>{s['port']}</b></span> · <span class="q">та же уже в порте <b>{s['same']}</b></span> ·
<span class="s">похожая <b>{s['similar']}</b></span> ·
нет <b>{s['missing']}</b> (из них adidas {s['missing_adidas']}) · особых {s['special']}</div></div>
<div class="ctl">
<label><input type="radio" name="f" value="all" checked> все</label>
<label><input type="radio" name="f" value="missing"> только не в порте</label>
<label><input type="radio" name="f" value="special"> только особые</label>
<label><input type="radio" name="f" value="picked"> только отмеченные</label>
<label><input type="checkbox" id="retro" checked> ретро (Reebok, 90-е)</label>
<button class="main" id="copy">Скопировать выбор (<span id="n">0</span>)</button>
<button id="clear">Снять отметки</button><span id="msg"></span>
</div>
<nav>{''.join(nav)}</nav>
</header>
<main>
<p class="help">Отметьте формы, которые хотите в игре, и нажмите «Скопировать выбор» — список попадёт в буфер, его
можно прислать в чат. Отметки запоминаются в этом браузере. Клик по картинке — крупнее. Рендер: перед и спина на сетке
NHL 24 того же кроя (в игре форма ляжет на крой Edge). Только для личного использования: картинки из дампа
пользователя, не публиковать. Собрано {stamp}.</p>
<div class="legend"><span><i class="dot" style="background:var(--port)"></i>в порте — эта форма NHL 27 уже стоит
(Home / Away (NHL 27))</span><span><i class="dot" style="background:var(--same)"></i>та же уже в порте — такая же текстура
уже в игре: форма из NHL 24 или другая папка NHL 27</span><span><i class="dot" style="background:var(--sim)"></i>похожая —
в игре есть почти такая (другие нашивки или отделка), сравните</span><span><i class="dot" style="background:var(--miss)"></i>нет — в
игре такой нет</span><span style="color:#ff9b6b">тип не определён — название в базе NHL 27 не прочитано</span></div>
{''.join(body)}
</main>
<div id="box"><img id="big" alt=""></div>
<div id="copybox"><div style="display:flex;justify-content:space-between;margin-bottom:6px"><b>Выбор (скопируйте Ctrl+C)</b>
<button id="closebox">Закрыть</button></div><textarea readonly></textarea></div>
<script>{JS}</script>
</body></html>
"""
    os.makedirs(OUT, exist_ok=True)
    fn = os.path.join(OUT, "index.html")
    tmp = fn + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(page)
    os.replace(tmp, fn)
    data = [{x: k[x] for x in ("code", "club", "cut", "kit", "variant", "group", "type", "undetermined", "status",
                               "status_text", "match")} | {"db": k["db"]} for k in kits]
    with open(os.path.join(OUT, "data.json"), "w", encoding="utf-8") as f:
        json.dump({"summary": s, "kits": data}, f, ensure_ascii=False, indent=1)
    return fn, s


# ─── команды ──────────────────────────────────────────────────────────────────────────────────────────────────


def ensure_meshes():
    need = [c for c in CUT_ORDER if not os.path.exists(os.path.join(CACHE, f"mesh_{c}.npz"))]
    if not need:
        return
    import subprocess
    code = ("import numpy as np, os; from fb import kit3d\n"
            f"for cut in {need!r}:\n"
            f"    m = kit3d.load_nhl24({MESH24!r}.format(cut=cut))\n"
            f"    np.savez(os.path.join({CACHE!r}, f'mesh_{{cut}}.npz'), pos=m['pos'], uv=m['uv'], tri=m['tri'], nrm=m['nrm'])\n")
    os.makedirs(CACHE, exist_ok=True)
    print("сетки NHL 24:", ", ".join(need), flush=True)
    subprocess.run([sys.executable, "-c", code], cwd=TOOLS, check=True, env=dict(os.environ, FB_GAME="nhl24"))


def load_all(clubs=None):
    kits = scan_kits()
    rows, names = db_rows()
    if clubs:
        want = {c.upper() for c in clubs}
        code = dict(CLUBS)
        bad = want - set(code.values())
        if bad:
            die(f"неизвестные клубы {sorted(bad)}; есть {', '.join(sorted(code.values()))}")
    return kits, rows, names


def cmd_build(a):
    from concurrent.futures import ProcessPoolExecutor
    ensure_meshes()
    kits, rows, names = load_all(a.clubs)
    code = dict(CLUBS)
    want = {c.upper() for c in a.clubs} if a.clubs else None
    jobs = []
    for k in kits:
        if want and code.get(k["club"]) not in want:
            continue
        jpg, sig = paths(k)
        if a.force or not (os.path.exists(jpg) and os.path.exists(sig)):
            jobs.append((key_of(k["club"], k["cut"], k["kit"]), k["row"], k["cut"], jpg, sig))
    print(f"комплектов {len(kits)}, рисовать {len(jobs)}", flush=True)
    errors = {}
    if jobs:
        os.environ["FB_GAME"] = "nhl27"
        t0 = time.time()
        with ProcessPoolExecutor(max_workers=a.jobs) as ex:
            for i, (key, err) in enumerate(ex.map(render_job, jobs, chunksize=4), 1):
                if err:
                    errors[key] = err
                if i % 50 == 0 or i == len(jobs):
                    print(f"  {i}/{len(jobs)}  {time.time() - t0:.0f} с", flush=True)
    for key, err in sorted(errors.items()):
        print(f"  ОШИБКА {key}: {err}")
    return cmd_page(a, kits, rows, names)


def cmd_page(a, kits=None, rows=None, names=None):
    if kits is None:
        kits, rows, names = load_all()
    nhl27, nhl24 = port_kits()
    classify(kits, rows, nhl27, nhl24, third_notes())
    fn, s = write_page(kits, names)
    size = os.path.getsize(fn) / 1e6
    print(f"{fn}  {size:.1f} МБ")
    print(json.dumps(s, ensure_ascii=False))
    missing_port = [x for x in nhl27 if not any((k["club"], k["cut"], k["kit"]) == x for k in kits)]
    if missing_port:
        print("в профилях есть папки, которых нет в дампе:", missing_port)
    return 0


def cmd_list(a):
    kits, rows, names = load_all()
    nhl27, nhl24 = port_kits()
    classify(kits, rows, nhl27, nhl24, third_notes())
    for club, ks in club_sections(kits):
        for k in ks:
            if a.missing and k["status"] == "port":
                continue
            print(f"{k['code']:<24} {k['status']:<8} {k['type']:<52} {k['status_text']}")
    return 0


def main():
    for stream in (sys.stdout, sys.stderr):          # консоль cp1251: русский текст и «×» в справке
        if stream.encoding and stream.encoding.lower() != "utf-8":
            try:
                stream.reconfigure(encoding="utf-8")
            except (AttributeError, ValueError):
                pass
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="рендеры + страница")
    b.add_argument("--clubs", type=lambda s: [x for x in s.split(",") if x], help="коды клубов через запятую")
    b.add_argument("--force", action="store_true", help="перерисовать и готовые")
    b.add_argument("--jobs", type=int, default=max(2, min(8, (os.cpu_count() or 4) - 2)), help="процессов (умолч. ≤ 8)")
    sub.add_parser("page", help="только страница из кэша")
    l = sub.add_parser("list", help="таблица в консоль")
    l.add_argument("--missing", action="store_true", help="без форм, которые уже в порте")
    a = ap.parse_args()
    return {"build": cmd_build, "page": cmd_page, "list": cmd_list}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
