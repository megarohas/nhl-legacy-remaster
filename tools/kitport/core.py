"""Общие части kitport: пути, окружение, сборка → cache: игры (сравнение, установка с копией, откат), снимки."""
import datetime
import importlib.util
import json
import os
import shutil
import subprocess
import sys

TOOLS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(TOOLS)
GAME = os.path.join(REPO, "game")
NHL24_WORK = os.path.join(GAME, "work", "nhl24")
EDGE_WORK = os.path.join(NHL24_WORK, "edgekit")              # fb.edge_kit: out/<КЛУБ>_<форма>, slot/, логи
PACKS = os.path.join(NHL24_WORK, "out")                     # pack-adidas, pack-edge, pack-edge-vN
LEGACY_DATA = os.path.join(GAME, "work", "legacy-data")     # out*, installed.txt, install-flags.txt
# копии заменённого в cache: перед установкой; LEGACY_DATA_STATE — своя папка (проверка на копии userdata)
BACKUP_CACHE = os.path.join(os.environ.get("LEGACY_DATA_STATE") or LEGACY_DATA, "backup-cache")
COMPARE = os.path.join(NHL24_WORK, "compare", "kitport")    # снимки «было» и листы
VENV_PY = os.path.join(NHL24_WORK, "venv", "Scripts", "python.exe")
INSTALLER = os.path.join(TOOLS, "legacy_data", "install_legacy_data.py")
DOC = os.path.join(REPO, "docs", "kitport.md")
JOURNAL_DOC = os.path.join(REPO, "docs", "nhl24-uniforms.md")   # журнал установок форм — §15.1


def installer():
    """Модуль tools/legacy_data/install_legacy_data.py (cache_dir, game_running, running_roots, папки out*)."""
    spec = importlib.util.spec_from_file_location("install_legacy_data", INSTALLER)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def cache_dir():
    return installer().cache_dir()


def cache_file(cache, rel):
    """Файл rel (путь игры через «/») в cache: в любой раскладке (tools/legacy_paths.py)."""
    if TOOLS not in sys.path:
        sys.path.insert(0, TOOLS)
    import legacy_paths
    return legacy_paths.cache_file(cache, rel)


def install_flags():
    """Флаги последней полной установки (install-flags.txt): установка с другими сняла бы накладки."""
    p = installer().FLAGS
    if not os.path.exists(p):
        return []
    return [ln.strip() for ln in open(p, encoding="utf-8") if ln.strip().startswith("--")]


def diff(flags=None, prefix=""):
    """Файлы сборки, которые отличаются от cache: игры: [(«CHANGED»/«NEW»/«GONE», путь, файл сборки)] — расчёт установщика
    (install_legacy_data.plan: out и накладки в порядке наложения, флаги — последней полной установки). GONE — файл
    прошлой установки, которого в сборке больше нет: полная установка его уберёт."""
    m = installer()
    cache = m.cache_dir()
    fl = install_flags() if flags is None else flags
    ahl, n24 = "--ahl32" in fl, "--nhl24" in fl
    parts = [prefix.strip("/")] if prefix else []
    srcs = m.sources(ahl, n24, parts)
    todo, gone = m.plan(cache, ahl, n24, parts)
    return [("CHANGED" if k == "изменён" else "NEW", rel, srcs[rel]) for k, rel in todo] + \
        [("GONE", rel, None) for rel in gone if os.path.exists(cache_file(cache, rel))]


def game_blocks_cache():
    """True — запущена NHL Legacy, которая читает этот cache: (ставить и откатывать нельзя)."""
    m = installer()
    if not m.game_running():
        return False
    target = m._norm(os.path.join(m.cache_dir(), os.pardir, os.pardir))
    roots = m.running_roots()
    return any(r is None or r == target for r in roots)


def today():
    return datetime.datetime.now().strftime("%Y%m%d")


def backup_dir(tag):
    """backup-cache/user-<дата>-<tag> (с номером, если уже есть)."""
    base = os.path.join(BACKUP_CACHE, f"user-{today()}-{tag}")
    d, n = base, 2
    while os.path.exists(d):
        d, n = f"{base}-{n}", n + 1
    return d


def backup(changes, tag):
    """Копия заменяемых и убираемых файлов cache: (CHANGED, GONE), список новых (NEW) и списки установщика (installed.txt,
    install-flags.txt) — в backup-cache; манифест для отката."""
    cache = cache_dir()
    d = backup_dir(tag)
    os.makedirs(d)
    man = {"date": datetime.datetime.now().isoformat(timespec="seconds"), "tag": tag, "flags": install_flags(),
           "cache": cache, "changed": [], "new": [], "state": {}}
    m = installer()
    for p in (m.LIST, m.FLAGS):
        if os.path.exists(p):
            os.makedirs(os.path.join(d, "_state"), exist_ok=True)
            shutil.copy2(p, os.path.join(d, "_state", os.path.basename(p)))
            man["state"][os.path.basename(p)] = p
    for kind, rel, _ in changes:
        if kind in ("CHANGED", "GONE"):
            dst = os.path.join(d, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(cache_file(cache, rel), dst)
            man["changed"].append(rel)
        else:
            man["new"].append(rel)
    with open(os.path.join(d, "manifest.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(man, f, ensure_ascii=False, indent=1)
    return d, man


def run_installer(flags):
    env = dict(os.environ, ORIG_PWD=REPO)
    return subprocess.run([sys.executable, INSTALLER, "install"] + list(flags), cwd=REPO, env=env).returncode


def restore(d):
    """Откат из backup-cache/<d>: файлы и списки установщика — обратно; новые (по манифесту) — убрать. -> (вернул, убрал)."""
    cache = cache_dir()
    man_p = os.path.join(d, "manifest.json")
    man = json.load(open(man_p, encoding="utf-8")) if os.path.exists(man_p) else None
    files = man["changed"] if man else [os.path.relpath(os.path.join(dp, f), d).replace(os.sep, "/")
                                        for dp, _, fn in os.walk(d) for f in fn if "_state" not in dp]
    back = 0
    for rel in files:
        src = os.path.join(d, rel)
        if os.path.isfile(src):
            dst = cache_file(cache, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)
            back += 1
    gone = 0
    for rel in (man or {}).get("new", []):
        p = cache_file(cache, rel)
        if os.path.exists(p):
            os.remove(p)
            gone += 1
    for name, path in (man or {}).get("state", {}).items():
        shutil.copy2(os.path.join(d, "_state", name), path)
    return back, gone


def next_pack_version(name="pack-edge"):
    """Свободное имя для прежнего пака: pack-edge-vN (N — следующее)."""
    n = 1
    for f in os.listdir(PACKS):
        if f.startswith(name + "-v") and f[len(name) + 2:].isdigit():
            n = max(n, int(f[len(name) + 2:]) + 1)
    return os.path.join(PACKS, f"{name}-v{n}")


def slot_kits_dir():
    return os.path.join(EDGE_WORK, "slot", "kits")


SNAP_FILES = ("jersey_cm", "jersey_nm", "jersey_sm", "name_cm", "sock_cm", "font_cm", "pant_cm", "pant_nm", "pant_sm")
#            pant_nm, pant_sm — с 23.10: рельеф нашивок шорт (fb.pant_decals.relief, kitport pants --before)


def snapshot(tag="before"):
    """Файлы слота форм (edgekit/slot/kits/<КЛУБ>_<форма>) → compare/kitport/<дата-время>-<tag>/<КЛУБ>_<форма>/."""
    src = slot_kits_dir()
    d = os.path.join(COMPARE, datetime.datetime.now().strftime("%Y%m%d-%H%M") + f"-{tag}")
    n = 0
    for kit in sorted(os.listdir(src)) if os.path.isdir(src) else []:
        for f in SNAP_FILES:
            p = os.path.join(src, kit, f + ".png")
            if os.path.exists(p):
                os.makedirs(os.path.join(d, kit), exist_ok=True)
                shutil.copy2(p, os.path.join(d, kit, f + ".png"))
                n += 1
    return d, n


COMPARE_TH = 8          # из 255: меньше — шум сжатия и сглаживания, не изменение рисунка


def compare(before, clubs=None, th=COMPARE_TH):
    """Слот форм против снимка: [(клуб_форма, файл, итог)], папка картинок «было | стало | разница ×4».

    Итог — «без изменений», «изменено N % … рамка u …, v …» (доли развёртки) или почему не сравнить. Нужен после
    правки общего кода (fb.edge_kit), чтобы уже готовые клубы собирались как раньше (docs/kitport.md §5.3).
    """
    import numpy as np
    from PIL import Image
    src = slot_kits_dir()
    out = os.path.join(before, "diff")
    rows = []
    for kit in sorted(os.listdir(before)):
        if kit == "diff" or not os.path.isdir(os.path.join(before, kit)) or (clubs and kit.split("_")[0] not in clubs):
            continue
        for f in sorted(os.listdir(os.path.join(before, kit))):
            if not f.endswith(".png"):
                continue
            cur = os.path.join(src, kit, f)
            if not os.path.exists(cur):
                rows.append((kit, f, "нет в слоте"))
                continue
            r = Image.open(os.path.join(before, kit, f)).convert("RGBA")
            c = Image.open(cur).convert("RGBA")
            if r.size != c.size:
                rows.append((kit, f, f"изменено: размер {r.size} → {c.size}"))
                continue
            d = np.abs(np.asarray(r, np.int16) - np.asarray(c, np.int16)).max(axis=2)
            m = d > th
            if not m.any():
                rows.append((kit, f, f"без изменений (макс {int(d.max())})"))
                continue
            ys, xs = np.nonzero(m)
            h, w = m.shape
            rows.append((kit, f, f"изменено {m.mean() * 100:.3f} % (макс {int(d.max())}), рамка "
                                 f"u {xs.min() / w:.3f}–{xs.max() / w:.3f}, v {ys.min() / h:.3f}–{ys.max() / h:.3f}"))
            heat = Image.fromarray(np.clip(d * 4, 0, 255).astype(np.uint8)).convert("RGB")
            sheet = Image.new("RGB", (3 * w, h))
            for k, im in enumerate((r.convert("RGB"), c.convert("RGB"), heat)):
                sheet.paste(im, (k * w, 0))
            os.makedirs(os.path.join(out, kit), exist_ok=True)
            s = min(1.0, 1024 / h)
            sheet.resize((int(3 * w * s), int(h * s))).save(os.path.join(out, kit, f))
    return rows, out


def latest_snapshot():
    if not os.path.isdir(COMPARE):
        return None
    ds = sorted(d for d in os.listdir(COMPARE) if os.path.isdir(os.path.join(COMPARE, d)) and not d.startswith("sheet"))
    return os.path.join(COMPARE, ds[-1]) if ds else None
