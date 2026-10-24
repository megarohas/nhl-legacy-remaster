"""Арены NHL 27 (PS5, Frostbite) — разбор для сравнения с аренами NHL Legacy: из чего собрана арена, сколько в ней сеток,
треугольников, материалов и текстур, где кресла, какие зрители и какой свет; картинки геометрии в тех же ракурсах, что у
tools/stadium.py (Legacy). Только чтение дампа: в игру и в cache: ничего не пишет. Документация — docs/arenas.md, раздел
«Арены NHL 27: насколько реальны и можно ли перенести».

    python -m fb.arena27 list [--json OUT]               # все арены дампа: папка уровня, сетки, треугольники, кресла, свет
    python -m fb.arena27 stats seattle [--json OUT]      # одна арена: сетки (LOD, треугольники), материалы, текстуры …
    python -m fb.arena27 render seattle [--view all] [--legacy 255] [--size 1600x900]
    python -m fb.arena27 crowd                           # зрители и кресла: сетки «роя», LOD, кости

Запуск — из tools/ с FB_GAME=nhl27 (дамп game/other/nhl27/Data и каталог fb.scan / fb.catalog / fb.toc index). Первый
запуск строит индекс (сетки, ebx уровней и компонентов, GUID разделов — ~20 с) в game/work/nhl27/arenas27/index.pkl;
дальше — из него. Картинки и JSON — в game/work/nhl27/arenas27/{preview,stats}/ (ассеты EA: не коммитить).

Как собрана арена NHL 27 (разбор 24.10.2026, подробно — docs/arenas.md):
- Уровень `content/worlds/stadiums/<город>_<N>/` — ~85 ebx: подуровни (environment_common, 5v5, threes, crowd,
  lighting_*, quality_high_dressing …), N — тот же номер, что `arenaartid` у Legacy (seattle_33, vegas_32, utah_30 — новые).
- Чаша — набор компонентов `content/worlds/components/structures/<город>/` (22–127 сеток MeshSet: трибуны частями,
  крыша, фермы, ложи, перила, борта, стекло, сетка, скамейки) + общие предметы `components/objects/*` (свет, мебель,
  экраны) + табло `content/worlds/scoreboard/<город>/`. У чаши один LOD, у предметов 2–5; метры, Y вверх, лёд вдоль Z.
- Расстановка (placements): группа статических сеток подуровня — у члена импорт сетки и за 0x38 до него относительный
  указатель на массив матриц (уровень хранит префабы уже «расплющенными»); табло — префаб, который подуровень ставит
  объектом: ReferenceObjectData (224/240 Б) с матрицей 4×4 по +32 и импортом по +120. Импорт → раздел по GUID из EFIX
  (у копий компонентов разных арен GUID один — берётся копия своей арены).
- Материалы — секции сеток по имени: пресеты библиотеки `content/worlds/surfacing_presets/<тип>/<основа>/<имя>_mat`
  (общие текстуры `surfacing/<тип>/<основа>/<основа>_{color,normal,coeff}`, плитка 1×1 / 2×2 м) и
  `content/worlds/materials/…`; секции `*_Shadow` — отдельная геометрия для теней.
- Кресла — массив Vec3 (16 Б) в `content/crowd/configs/worlds/stadiums/<город>/crowd_<город>_placement`, дальше
  несколько массивов той же длины (u8/u32, не разобраны). Кресло и зрители — сетки «роя» (swarm) из content/crowd/agent.
- Свет — Enlighten (динамический GI, res 0x70C5CB3E, ~16 МБ на арену) + световые объёмы, а не карты освещения.

Грабли: у части сеток (перила) геометрия в чанке, которого нет в каталоге, — такие пропускаются и печатаются.
"""
import argparse
import collections
import csv
import glob
import json
import os
import pickle
import re
import struct
import sys
import uuid

import numpy as np

from . import cas, source
from .cas import REPO

WORK = os.path.join(source.WORK, "arenas27")
RES_MESH = 0x49B156D4
RES_ENLIGHTEN = 0x70C5CB3E
RES_LIGHTDATA = 0xC6CD3286
EBX_PREFIXES = ("content/worlds/components/", "content/worlds/scoreboard/", "content/worlds/stadiums/",
                "content/crowd/configs/worlds/stadiums/", "content/worlds/surfacing_presets/", "content/worlds/materials/")
GUID_PREFIXES = ("content/worlds/components/", "content/worlds/scoreboard/")
RES_PREFIXES = ("content/worlds/", "content/crowd/", "bakedgi/content/worlds/stadiums/")
MAXLOD = 7
INDEX_VERSION = 2
MEMBER_TRANSFORMS = -0x38    # член группы статических сеток уровня: массив матриц, через 0x38 — импорт сетки, +0x30 — чертёж
PS5_BASE, PS5_LOD_AT, PS5_SECTION = 0x10, 0x30, 0x170
# секции, которые в превью не рисуются: стекло, тени, сетка за воротами, флаг-полотно над трибуной (сцена «флаг»)
SKIP_SECTION = re.compile(r"^glass_|_shadow$|netting|crowdflag", re.I)

_IDX = None
_EBX = {}
_MESH = {}


# ================================================================ индекс

def index(rebuild=False):
    """{'res': {имя: запись fb.scan} (MeshSet и свет), 'ebx': {имя: запись}, 'guid': {GUID раздела: имя ebx}}."""
    global _IDX
    if _IDX is not None and not rebuild:
        return _IDX
    path = os.path.join(WORK, "index.pkl")
    if os.path.exists(path) and not rebuild:
        _IDX = pickle.load(open(path, "rb"))
        if _IDX.get("version") == INDEX_VERSION:
            return _IDX
    scans = sorted(glob.glob(os.path.join(source.CATALOG, "scan", "*.jsonl")))
    if not scans:
        raise SystemExit(f"{source.CATALOG}: нет каталога fb.scan. Запуск — с FB_GAME=nhl27 (из tools/).")
    res, ebx = {}, {}
    for p in scans:
        with open(p, encoding="utf-8") as f:
            for line in f:
                if '"ofs"' not in line:
                    continue
                i = line.find('"name": "') + 9
                if line.startswith('{"k": "ebx"'):
                    if line.startswith(EBX_PREFIXES, i):
                        r = json.loads(line)
                        ebx.setdefault(r["name"], r)
                elif line.startswith('{"k": "res"') and line.startswith(RES_PREFIXES, i):
                    r = json.loads(line)
                    if r["type"] in (RES_MESH, RES_ENLIGHTEN, RES_LIGHTDATA):
                        res.setdefault(r["name"], r)
    guid = collections.defaultdict(list)          # копии компонентов у разных арен — с одним GUID раздела
    for n, r in sorted(ebx.items()):
        if n.startswith(GUID_PREFIXES):
            d = _read(r)
            e = d.find(b"EFIX")
            if e > 0:
                guid[str(uuid.UUID(bytes_le=bytes(d[e + 8:e + 24])))].append(n)
    _IDX = {"res": res, "ebx": ebx, "guid": dict(guid), "version": INDEX_VERSION}
    os.makedirs(WORK, exist_ok=True)
    pickle.dump(_IDX, open(path, "wb"))
    print(f"индекс: сеток и света {len(res)}, ebx {len(ebx)}, GUID {len(guid)} → {path}", file=sys.stderr)
    return _IDX


def _read(r):
    from .extract import cas_file
    d, _ = cas.read_entry(cas_file(r["cas"]), r["ofs"], r["size"])
    return d


def ebx(name):
    if name not in _EBX:
        r = index()["ebx"].get(name)
        if r is None:
            raise KeyError(f"нет ebx {name}")
        _EBX[name] = _read(r)
    return _EBX[name]


# ================================================================ EBX (RIFF): EFIX и ссылки

def efix(d):
    """Раздел EFIX ebx (RIFF EBX, Frostbite 2021+): GUID раздела, смещения объектов, импорты. Смещения — от 0x20."""
    p = d.index(b"EFIX") + 8
    out = {"part": uuid.UUID(bytes_le=bytes(d[p:p + 16]))}
    p += 16

    def arr(fmt, size):
        nonlocal p
        n = struct.unpack_from("<I", d, p)[0]
        p += 4
        v = list(struct.unpack_from(f"<{n}{fmt}", d, p)) if fmt else n
        p += size * n
        return v
    arr("", 16)                                      # GUID типов
    arr("I", 4)                                      # подписи типов
    p += 4                                           # число экспортируемых объектов
    out["dco"] = arr("I", 4)                         # смещения объектов
    arr("I", 4)                                      # указатели
    arr("I", 4)                                      # ссылки на ресурсы
    n = struct.unpack_from("<I", d, p)[0]
    p += 4
    out["imps"] = [(uuid.UUID(bytes_le=bytes(d[p + 32 * k:p + 32 * k + 16])),
                    uuid.UUID(bytes_le=bytes(d[p + 32 * k + 16:p + 32 * k + 32]))) for k in range(n)]
    p += 32 * n
    out["impofs"] = arr("I", 4)
    arr("I", 4)                                      # typeInfo
    out["arr"], out["boxed"], out["strs"] = struct.unpack_from("<3I", d, p)
    return out


def _matrix(d, o):
    """LinearTransform (4 × Vec3 по 16 Б) → 4×4 для p' = p @ M или None, если это не матрица."""
    if o < 0 or o + 64 > len(d):
        return None
    with np.errstate(all="ignore"):
        m = np.frombuffer(d[o:o + 64], "<f4").reshape(4, 4).astype(np.float64)
        if not np.all(np.isfinite(m)) or np.abs(m[:, 3]).max() > 1e-6:
            return None
        det = np.linalg.det(m[:3, :3])
    if not (1e-4 < abs(det) < 1e4) or np.abs(m[3, :3]).max() > 1000:
        return None
    M = np.eye(4)
    M[:3, :3], M[3, :3] = m[:3, :3], m[3, :3]
    return M


def guid_name(g, city=None):
    """Раздел по GUID. У копий компонентов (перила florida/nyislanders/pittsburgh…) GUID один — берётся копия своей
    арены, иначе первая по имени."""
    names = index()["guid"].get(str(g)) or []
    own = [n for n in names if city and f"/{city}/" in n]
    return (own or names or [None])[0]


def _imports(d, e, city):
    """[(смещение поля в файле, имя раздела или None)] — поля-импорты ebx (значение (номер << 1) | 1)."""
    out = []
    for o in sorted(e["impofs"]):
        v = struct.unpack_from("<Q", d, 0x20 + o)[0]
        if v & 1 and (v >> 1) < len(e["imps"]):
            out.append((0x20 + o, guid_name(e["imps"][v >> 1][0], city)))
    return out


def refs(name, city=None):
    """Импорты ebx: [(имя раздела или None, матрица объекта или None)]. Матрица — по +32 объекта, в котором ссылка."""
    d = ebx(name)
    e = efix(d)
    starts = sorted(e["dco"])
    out = []
    for q, tgt in _imports(d, e, city):
        a = max((x for x in starts if x <= q - 0x20), default=None)
        out.append((tgt, _matrix(d, 0x20 + a + 32) if a is not None else None))
    return out


def members(name, city=None):
    """Группа статических сеток уровня (массивы после объектов): [(сетка, [матрицы])]. Член: импорт сетки, по
    MEMBER_TRANSFORMS от него — относительный указатель (int32 + 4 нулевых байта) на массив LinearTransform (число — перед ним)."""
    d = ebx(name)
    e = efix(d)
    out = []
    for q, t in _imports(d, e, city):
        if not t or not t.endswith("_mesh") or t not in index()["res"]:
            continue
        f = q + MEMBER_TRANSFORMS
        if f + 8 > len(d):
            continue
        rel, hi = struct.unpack_from("<iI", d, f)
        a = f + rel
        if hi or rel >= 0 or a < 8:
            continue
        c = struct.unpack_from("<I", d, a - 4)[0]
        Ms = [_matrix(d, a + 64 * k) for k in range(c)] if 0 < c < 20000 else []
        if Ms and all(M is not None for M in Ms):
            out.append((t, Ms))
    return out


# ================================================================ арены и расстановка

def arenas():
    """[{'folder': 'seattle_33', 'city': 'seattle', 'n': 33}] — уровни content/worlds/stadiums/<город>_<N>/."""
    out = []
    for n in index()["ebx"]:
        m = re.match(r"content/worlds/stadiums/(([a-z0-9]+?)_(\d+))/\1$", n)
        if m:
            out.append({"folder": m.group(1), "city": m.group(2), "n": int(m.group(3))})
    return sorted(out, key=lambda a: (a["n"], a["city"]))


def arena(key):
    """Арена по городу (seattle), папке (seattle_33) или номеру (33)."""
    al = arenas()
    for a in al:
        if key in (a["city"], a["folder"], str(a["n"])):
            return a
    raise SystemExit(f"{key}: нет такой арены. Есть: {', '.join(a['folder'] for a in al)}")


def component_dirs(city):
    return (f"content/worlds/components/structures/{city}/", f"content/worlds/scoreboard/{city}/")


SKIP_SUBLEVEL = re.compile(r"/(threes|nis|autotest|frontend)[^/]*($|/)")   # 3 на 3, ролики: не матч 5 на 5
_PL = {}


def placements(key):
    """[(имя сетки, матрица 4×4)] — всё статическое в матче 5 на 5 (p' = p @ M, метры, лёд вдоль Z):
    1) группы статических сеток подуровней (environment_common — чаша и предметы, 5v5 — инвентарь у скамеек): уровень
       хранит их уже «расплющенными», с мировыми матрицами;
    2) префабы, которые уровень ставит объектами (табло: scoreboard_<город>_prefab), — обходом с матрицами объектов;
       сетка, уже поставленная группой, второй раз не берётся."""
    a = arena(key)
    if a["folder"] in _PL:
        return _PL[a["folder"]]
    idx = index()
    city = a["city"]
    lv = sorted(n for n in idx["ebx"] if n.startswith(f"content/worlds/stadiums/{a['folder']}/")
                and not SKIP_SUBLEVEL.search(n[len("content/worlds/stadiums/"):]))
    out, seen = [], set()
    for n in lv:
        for t, Ms in members(n, city):
            for M in Ms:
                k = (t, tuple(np.round(M[3, :3], 2)))
                if k not in seen:
                    seen.add(k)
                    out.append((t, M))
    grouped = {t for t, _ in out}

    def walk(n, M, stack):
        for t, Mi in refs(n, city):
            if t is None or t in stack:
                continue
            T = (Mi if Mi is not None else np.eye(4)) @ M
            if t.endswith("_mesh"):
                if t in idx["res"] and t not in grouped:
                    out.append((t, T))
            else:
                walk(t, T, stack + (t,))
    for n in lv:
        for t, Mi in refs(n, city):
            if t and not t.endswith("_mesh") and t.startswith(GUID_PREFIXES) and Mi is not None:
                walk(t, Mi, (t,))
    _PL[a["folder"]] = out
    return out


# ================================================================ сетки

def header(name):
    """Заголовок MeshSet PS5 без геометрии: {'lods': [треугольников на LOD], 'sections': [(имя, треугольников)]}."""
    d = _read(index()["res"][name])
    lods, secs = [], []
    for k in range(MAXLOD):
        p = struct.unpack_from("<Q", d, PS5_LOD_AT + 8 * k)[0]
        if not p:
            continue
        lod = p + PS5_BASE
        nsec, sp = struct.unpack_from("<II", d, lod + 8)
        sp += PS5_BASE
        tot = 0
        for i in range(nsec):
            s = sp + i * PS5_SECTION
            nt = struct.unpack_from("<I", d, s + 0x20)[0]
            tot += nt
            if not lods:
                nmp = struct.unpack_from("<Q", d, s + 0x08)[0] + PS5_BASE
                secs.append((d[nmp:d.index(b"\0", nmp)].decode("latin1"), nt))
        lods.append(tot)
    return {"lods": lods, "sections": secs}


def mesh(name):
    """Геометрия LOD0 через fb.heads.mesh (вершины PS5 склеены): {секция: {'pos', 'tri', 'nv', 'ntri', …}} или None,
    если чанка геометрии нет в каталоге."""
    if name not in _MESH:
        from . import heads
        heads._res = index()["res"]
        try:
            _MESH[name] = heads.mesh(name)["sections"]
        except KeyError as e:
            if "нет чанка" not in str(e):
                raise
            _MESH[name] = None
    return _MESH[name]


# ================================================================ кресла

def seats(city):
    """Позиции кресел (S×3, м; лёд вдоль Z) из crowd_<город>_placement: массив Vec3 по 16 Б с числом перед ним."""
    name = f"content/crowd/configs/worlds/stadiums/{city}/crowd_{city}_placement"
    if name not in index()["ebx"]:
        return np.zeros((0, 3))
    d = ebx(name)
    a = np.frombuffer(d[:len(d) // 16 * 16], "<f4").reshape(-1, 4)
    with np.errstate(all="ignore"):
        ok = (np.isfinite(a).all(1) & (a[:, 3] == 0) & (np.abs(a[:, 0]) < 150) & (a[:, 1] > -5) & (a[:, 1] < 80)
              & (np.abs(a[:, 2]) < 150) & (np.abs(a[:, 0]) + np.abs(a[:, 2]) > 3))
    best = (0, 0)
    i, n = 0, len(ok)
    while i < n:
        if ok[i]:
            j = i
            while j < n and ok[j]:
                j += 1
            cnt = struct.unpack_from("<I", d, i * 16 - 4)[0] if i else 0
            run = min(j - i, cnt) if 0 < cnt <= j - i else 0
            if run > best[1]:
                best = (i, run)
            i = j
        else:
            i += 1
    return a[best[0]:best[0] + best[1], :3].astype(np.float64)


# ================================================================ текстуры

_TEX = None


def _textures():
    """{имя текстуры: строка textures.csv} — только content/worlds, content/crowd, bakedgi."""
    global _TEX
    if _TEX is None:
        _TEX = {}
        with open(os.path.join(source.CATALOG, "textures.csv"), encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if r["ofs"] and r["name"].startswith(("content/worlds/", "content/crowd/", "bakedgi/")):
                    _TEX.setdefault(r["name"], r)
    return _TEX


def tex_header(name):
    from .extract import read_header
    return read_header(_textures()[name])


def tex_mean(name):
    """Средний цвет текстуры (0…1) по мелкому мипу или None."""
    from . import texture
    from .extract import read_chunk
    try:
        h = tex_header(name)
        data, start = read_chunk(h)
    except Exception:  # noqa: BLE001
        return None
    if data is None:
        return None
    for lvl in range(min(h["mips"] - 1, 5), -1, -1):
        if lvl < start:
            break
        try:
            im = texture.decode_mip(h, data, lvl, data_first=start).convert("RGB")
            return np.asarray(im, np.float64).reshape(-1, 3).mean(0) / 255.0
        except Exception:  # noqa: BLE001
            continue
    return None


def material_info(mat):
    """Материал секции → {'kind': preset|material|other, 'ebx', 'textures': [имена]} (по пресету — color/normal/coeff)."""
    idx = index()
    if not hasattr(material_info, "_by"):
        by = {}
        for n in idx["ebx"]:
            if n.startswith(("content/worlds/surfacing_presets/", "content/worlds/materials/")):
                by.setdefault(n.rsplit("/", 1)[1].lower(), n)
        material_info._by = by
    n = material_info._by.get(mat.lower())
    if n is None:
        return {"kind": "other", "ebx": None, "textures": []}
    if n.startswith("content/worlds/surfacing_presets/"):
        _, _, _, typ, base, _ = n.split("/", 5)
        pre = f"content/worlds/surfacing/{typ}/{base}/"
        texs = sorted(t for t in _textures() if t.startswith(pre) and t.count("/") == pre.count("/"))
        return {"kind": "preset", "ebx": n, "textures": texs}
    return {"kind": "material", "ebx": n, "textures": []}


# ================================================================ сводки

def arena_textures(city):
    """Текстуры с именем города (content/worlds, content/crowd, bakedgi)."""
    rx = re.compile(rf"(^|[/_]){re.escape(city)}([/_]|\d|$)")
    return sorted(t for t in _textures() if rx.search(t))


def lighting(a):
    pre = f"content/worlds/stadiums/{a['folder']}/lighting/"
    return {n.rsplit("/", 1)[1]: r["size"] for n, r in index()["res"].items() if n.startswith(pre)}


def stats(key, textures=True):
    a = arena(key)
    city = a["city"]
    idx = index()
    pl = placements(a["folder"])
    inst = collections.Counter(m for m, _ in pl)
    pre = component_dirs(city)
    own = sorted(n for n in idx["res"] if n.startswith(pre) and n.endswith("_mesh"))
    rows, missing = [], []
    mats = collections.Counter()
    for m in sorted(set(own) | set(inst)):
        h = header(m)
        draw = sum(t for s, t in h["sections"] if not s.lower().endswith("_shadow"))
        shadow = sum(t for s, t in h["sections"] if s.lower().endswith("_shadow"))
        for s, t in h["sections"]:
            mats[s] += t * max(1, inst.get(m, 0))
        secs = mesh(m)
        if secs is None:
            missing.append(m)
        nv = sum(s["nv"] for s in secs.values()) if secs else None
        rows.append({"mesh": m, "own": m in own, "instances": inst.get(m, 0), "lods": len(h["lods"]),
                     "tris": draw, "shadow_tris": shadow, "verts": nv, "sections": len(h["sections"])})
    placed = sum(r["tris"] * r["instances"] for r in rows)
    unique_own = sum(r["tris"] for r in rows if r["own"])
    minfo = {s: material_info(s) for s in mats if not s.lower().endswith("_shadow")}
    out = {"arena": a, "meshes_own": len(own), "meshes_shared": sum(1 for r in rows if not r["own"]),
           "placements": len(pl), "tris_own_unique": unique_own, "tris_placed": placed,
           "shadow_tris": sum(r["shadow_tris"] * max(1, r["instances"]) for r in rows),
           "missing_geometry": missing, "materials": len(minfo),
           "materials_by_kind": dict(collections.Counter(v["kind"] for v in minfo.values())),
           "seats": int(len(seats(city))), "lighting": lighting(a),
           "level_ebx": sum(1 for n in idx["ebx"] if n.startswith(f"content/worlds/stadiums/{a['folder']}/")),
           "meshes": rows}
    if textures:
        surf = sorted({t for v in minfo.values() for t in v["textures"]})
        own_tex = arena_textures(city)
        tex = {}
        for t in surf + own_tex:
            try:
                h = tex_header(t)
                tex[t] = (h["width"], h["height"], h["mips"], h["format"])
            except Exception:  # noqa: BLE001
                tex[t] = None
        out["textures_surfacing"] = len(surf)
        out["textures_own"] = len(own_tex)
        out["texture_sizes"] = dict(collections.Counter(f"{v[0]}x{v[1]}" for v in tex.values() if v))
        out["texture_mb_mip0"] = round(sum(_bytes(v) for v in tex.values() if v) / 2 ** 20, 1)
        out["textures"] = {t: v for t, v in tex.items()}
    return out


def _bytes(v):
    from . import texture
    w, h, _, fmt = v
    name = texture.format_name(fmt)
    bpp = 4 if name.startswith(("BC1", "BC4")) else 8 if name.startswith(("BC", )) else 32
    return w * h * bpp / 8 * 4 / 3


# ================================================================ картинки

def _to_legacy(p):
    """Метры NHL 27 (лёд вдоль Z, скамейки при +X) → кадр tools/stadium.py (лёд вдоль X, штрафная при +Z)."""
    return np.stack([p[..., 2], p[..., 1], -p[..., 0]], -1)


TINT = [  # цвет по слову в имени материала (пресет красит общую текстуру; сам оттенок — в параметрах ebx, не разобран)
    ("blackmesh", (0.05, 0.05, 0.05)), ("black", (0.06, 0.06, 0.07)), ("graydark", (0.22, 0.22, 0.23)),
    ("greydark", (0.22, 0.22, 0.23)), ("graylight", (0.68, 0.68, 0.68)), ("lightgrey", (0.68, 0.68, 0.68)),
    ("gray", (0.45, 0.45, 0.46)), ("grey", (0.45, 0.45, 0.46)), ("white", (0.88, 0.88, 0.88)),
    ("beigedarker", (0.52, 0.47, 0.38)), ("beige", (0.76, 0.70, 0.58)), ("bluedarker", (0.08, 0.11, 0.24)),
    ("bluedark", (0.10, 0.15, 0.33)), ("blue", (0.18, 0.30, 0.60)), ("navy", (0.08, 0.10, 0.25)),
    ("red", (0.62, 0.10, 0.10)), ("yellowlighter", (0.92, 0.82, 0.30)), ("yellow", (0.85, 0.70, 0.12)),
    ("green", (0.15, 0.40, 0.20)), ("teal", (0.10, 0.45, 0.50)), ("orange", (0.85, 0.45, 0.10)),
]
FALLBACK = [("concrete", (0.55, 0.55, 0.54)), ("metal", (0.42, 0.43, 0.45)), ("wood", (0.55, 0.40, 0.25)),
            ("carpet", (0.25, 0.25, 0.28)), ("fabric", (0.25, 0.25, 0.28)), ("boards", (0.85, 0.85, 0.85)),
            ("plastic", (0.30, 0.30, 0.32)), ("banner", (0.35, 0.40, 0.55)), ("scoreboard", (0.12, 0.12, 0.14)),
            ("powerring", (0.10, 0.10, 0.12)), ("crowdflag", (0.30, 0.45, 0.60))]
_MATCOL = {}


def material_color(mat):
    if mat not in _MATCOL:
        low = mat.lower()
        col = next((np.array(c) for k, c in TINT if k in low), None)
        if col is None:
            info = material_info(mat)
            t = next((t for t in info["textures"] if t.endswith("_color")), None)
            col = tex_mean(t) if t else None
        if col is None:
            col = np.array(next((c for k, c in FALLBACK if k in low), (0.5, 0.5, 0.5)))
        _MATCOL[mat] = np.clip(col, 0, 1)
    return _MATCOL[mat]


def scene(key, with_seats=True):
    """Треугольники для tools/stadium.draw: (V T×3×3 в кадре Legacy, C T×3), число пропущенных сеток."""
    import stadium as st
    a = arena(key)
    city = a["city"]
    L = np.array([0.30, 1.0, -0.35])
    L /= np.linalg.norm(L)
    V, C = [], []
    skipped = 0
    for m, M in placements(a["folder"]):
        secs = mesh(m)
        if secs is None:
            skipped += 1
            continue
        for sname, s in secs.items():
            if SKIP_SECTION.search(sname) or not len(s["tri"]):
                continue
            p = s["pos"][:, :3] @ M[:3, :3] + M[3, :3]
            tv = _to_legacy(p[s["tri"]])
            tv = tv[tv[..., 1].max(1) > 0.05]               # пол на уровне льда (под площадкой) — не рисуется
            n = np.cross(tv[:, 1] - tv[:, 0], tv[:, 2] - tv[:, 0])
            n /= np.linalg.norm(n, axis=1, keepdims=True) + 1e-12
            shade = 0.38 + 0.62 * np.abs(n @ L)
            V.append(tv)
            C.append(material_color(sname)[None, :] * shade[:, None])
    if with_seats:
        sv, sc = seat_triangles(city)
        V.append(sv)
        C.append(sc)
    rv, rc = st.rink_triangles()
    V.append(rv)
    C.append(rc)
    return np.concatenate(V).astype(np.float32), np.clip(np.concatenate(C), 0, 1).astype(np.float32), skipped


def chair_color(city):
    """Основной цвет кресла арены по текстуре crowd_chair_<город>_0_color (выгрузка stadium.py nhl27) или серый."""
    import stadium as st
    try:
        v = st.nhl27_chairs().get(city) or []
    except SystemExit:
        v = []
    hx = next((x[0] for x in v if x), None)
    return np.array(st.hex_rgb(hx)) / 255.0 if hx else np.array([0.25, 0.25, 0.27])


def seat_triangles(city):
    """Кресла — сиденье и спинка (4 треугольника) на каждое место, лицом к оси льда; цвет — chair_color."""
    P = seats(city)
    if not len(P):
        return np.zeros((0, 3, 3)), np.zeros((0, 3))
    Q = _to_legacy(P)                                                       # лёд вдоль X
    tgt = np.stack([np.clip(Q[:, 0], -22.0, 22.0), Q[:, 1], np.zeros(len(Q))], 1)
    F = tgt - Q
    F[:, 1] = 0
    F /= np.linalg.norm(F, axis=1, keepdims=True) + 1e-9
    U = np.array([0.0, 1.0, 0.0])
    R = np.cross(U, F)
    w, d0, d1, hs, hb = 0.23, -0.05, 0.38, 0.42, 0.85      # полуширина, перёд/зад сиденья, высота сиденья и спинки
    quads = [((-w, hs, d1), (w, hs, d1), (w, hs, d0), (-w, hs, d0)),          # сиденье (вперёд — к льду, d0 < d1)
             ((-w, hs, d0), (w, hs, d0), (w, hb, d0 - 0.06), (-w, hb, d0 - 0.06))]
    tris = []
    for q in quads:
        tris += [(q[0], q[1], q[2]), (q[0], q[2], q[3])]
    loc = np.array(tris)                                                    # 4×3×3: (поперёк, вверх, к льду со знаком −)
    world = (Q[:, None, None, :] + loc[None, ..., 0:1] * R[:, None, None, :] + loc[None, ..., 1:2] * U
             - loc[None, ..., 2:3] * F[:, None, None, :])
    base = chair_color(city)
    col = np.concatenate([np.repeat([base * 1.05], 2, 0), np.repeat([base * 0.8], 2, 0)])
    return world.reshape(-1, 3, 3), np.tile(col, (len(Q), 1))


def render(key, views=("broadcast",), size=(1600, 900), legacy=None, out=None, with_seats=True):
    """Картинки арены NHL 27 в видах tools/stadium.py; legacy=N — рядом модель Legacy N тем же видом. → [пути]."""
    from PIL import Image
    import stadium as st
    a = arena(key)
    V, C, skipped = scene(a["folder"], with_seats)
    P = seats(a["city"])
    clip = float(P[:, 1].max()) + 1.0 if len(P) else 30.0
    out = out or os.path.join(WORK, "preview")
    os.makedirs(out, exist_ok=True)
    paths = []
    for v in views:
        im = st.draw(V, C, v, size, top_clip=clip)
        st.caption(im, f"NHL 27 — {a['folder']} ({len(V):,} тр.)".replace(",", " "))
        if legacy is not None:
            L = st.render(legacy, None, (v,), size)[v]
            st.caption(L, f"NHL Legacy — stadium_{legacy}")
            both = Image.new("RGB", (size[0] * 2 + 8, size[1]), (255, 255, 255))
            both.paste(L, (0, 0))
            both.paste(im, (size[0] + 8, 0))
            im = both
            p = os.path.join(out, f"compare_{a['folder']}_vs_{legacy}_{v}.png")
        else:
            p = os.path.join(out, f"arena27_{a['folder']}_{v}.png")
        im.save(p)
        paths.append(p)
    if skipped:
        print(f"без геометрии (нет чанка): {skipped} размещений", file=sys.stderr)
    return paths


# ================================================================ команды

def cmd_list(a):
    rows = []
    for ar in arenas():
        city = ar["city"]
        pre = component_dirs(city)
        own = [n for n in index()["res"] if n.startswith(pre) and n.endswith("_mesh")]
        tris = shadow = 0
        for m in own:
            for s, t in header(m)["sections"]:
                if s.lower().endswith("_shadow"):
                    shadow += t
                else:
                    tris += t
        lt = lighting(ar)
        enl = sum(v for k, v in lt.items() if k.startswith("en_"))
        rows.append(dict(ar, meshes=len(own), tris=tris, shadow_tris=shadow, seats=int(len(seats(city))),
                         enlighten_mb=round(enl / 2 ** 20, 1)))
        r = rows[-1]
        print(f"{r['folder']:24s} N={r['n']:<4d} сеток {r['meshes']:4d}  треугольников {r['tris']:8,d} (+тени "
              f"{r['shadow_tris']:7,d})  кресел {r['seats']:6,d}  Enlighten {r['enlighten_mb']:5.1f} МБ".replace(",", " "))
    if a.json:
        json.dump(rows, open(a.json, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(a.json)


def cmd_stats(a):
    s = stats(a.arena)
    ar = s["arena"]
    print(f"{ar['folder']} (N={ar['n']}): ebx уровня {s['level_ebx']}")
    print(f"  сетки: свои {s['meshes_own']}, общие (из префабов) {s['meshes_shared']}, размещений {s['placements']}")
    print(f"  треугольники LOD0: свои уникальные {s['tris_own_unique']:,}, по размещениям {s['tris_placed']:,}, "
          f"геометрия теней {s['shadow_tris']:,}".replace(",", " "))
    lods = collections.Counter(r["lods"] for r in s["meshes"])
    print(f"  LOD у сеток: {dict(lods)}; без геометрии в каталоге: {len(s['missing_geometry'])}")
    print(f"  материалы: {s['materials']} {s['materials_by_kind']}")
    print(f"  текстуры: библиотеки (по пресетам) {s['textures_surfacing']}, с именем города {s['textures_own']}, "
          f"размеры {s['texture_sizes']}, ≈{s['texture_mb_mip0']} МБ с мипами")
    print(f"  кресел: {s['seats']:,}".replace(",", " "))
    print("  свет: " + ", ".join(f"{k} {v / 2 ** 20:.1f} МБ" for k, v in sorted(s["lighting"].items())))
    top = sorted(s["meshes"], key=lambda r: -r["tris"] * max(1, r["instances"]))[:15]
    print("  крупные сетки (треугольники × размещения):")
    for r in top:
        print(f"    {r['tris']:7,d} × {r['instances']:<3d} {r['mesh'].split('/', 3)[-1]}".replace(",", " "))
    path = a.json or os.path.join(WORK, "stats", f"{ar['folder']}.json")
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    json.dump(s, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
    print(path)


def cmd_render(a):
    import stadium as st
    views = list(st.VIEWS) if a.view == "all" else a.view.split(",")
    for v in views:
        if v not in st.VIEWS:
            raise SystemExit(f"--view {v}: есть {', '.join(st.VIEWS)}, all")
    w, h = (int(x) for x in a.size.lower().split("x"))
    for p in render(a.arena, views, (w, h), a.legacy, a.out, not a.no_seats):
        print(p)


def cmd_crowd(a):
    groups = collections.defaultdict(list)
    for n in index()["res"]:
        if n.startswith("content/crowd/agent/") and n.endswith("_mesh"):
            groups["/".join(n.split("/")[3:5])].append(n)
    print("группа                      сеток  LOD0 треугольников (мин…макс)  LOD  кости")
    for g, names in sorted(groups.items()):
        hs = [header(n) for n in names]
        t0 = [h["lods"][0] for h in hs if h["lods"]]
        secs = mesh(names[0]) or {}
        bones = any("bi0" in s for s in secs.values())
        print(f"{g:28s} {len(names):5d}  {min(t0):7,d} … {max(t0):7,d}            "
              f"{max(len(h['lods']) for h in hs):3d}  {'да' if bones else 'нет'}".replace(",", " "))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rebuild", action="store_true", help="пересобрать индекс")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("list", help="все арены дампа")
    p.add_argument("--json")
    p = sub.add_parser("stats", help="одна арена подробно")
    p.add_argument("arena", help="город (seattle), папка (seattle_33) или номер (33)")
    p.add_argument("--json")
    p = sub.add_parser("render", help="картинки геометрии (виды tools/stadium.py)")
    p.add_argument("arena")
    p.add_argument("--view", default="broadcast", help="broadcast, overview, end, top или all")
    p.add_argument("--legacy", type=int, help="номер модели Legacy рядом (тем же видом)")
    p.add_argument("--size", default="1600x900")
    p.add_argument("--out", help="папка (по умолчанию game/work/nhl27/arenas27/preview)")
    p.add_argument("--no-seats", action="store_true")
    sub.add_parser("crowd", help="сетки зрителей и кресел")
    a = ap.parse_args()
    sys.path.insert(0, os.path.join(REPO, "tools"))          # tools/stadium.py (виды, отрисовка, Legacy)
    if source.GAME != "nhl27":
        print(f"FB_GAME={source.GAME}: инструмент разбирает дамп NHL 27 (FB_GAME=nhl27)", file=sys.stderr)
    index(a.rebuild)
    {"list": cmd_list, "stats": cmd_stats, "render": cmd_render, "crowd": cmd_crowd}[a.cmd](a)


if __name__ == "__main__":
    main()
