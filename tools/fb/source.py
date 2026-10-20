"""Какой дамп Frostbite читают инструменты fb (scan, catalog, toc, extract, orphans, lfs, heads, kit3d, verify).

По умолчанию — NHL 24 (PS4): дамп game/other/nhl24/Data, платформа Gen4b, рабочая папка game/work/nhl24. Другой
источник — переменными окружения, без правки кода (docs/frostbite-sources.md):

    FB_GAME=nhl27                # имя источника: дамп game/other/<FB_GAME>/Data, работа game/work/<FB_GAME>
    FB_DATA=путь/к/Data          # своя папка Data дампа
    FB_PATCH=путь/к/Patch        # папка патча (по умолчанию — Patch рядом с Data, если есть)
    FB_WORK=путь                 # своя рабочая папка (catalog/, extract/, out/ …)
    FB_PLATFORM=Gen4b            # платформенная папка внутри Data; по умолчанию — по файлу initfs_<платформа>
    FB_PACKAGE=nhl_installpackage_   # префикс папок пакетов в <платформа>/superbundlelayout

Oodle (ooz.dll) — свой в <работа>/bin/, иначе общий game/work/nhl24/bin/ooz.dll.
Проверить, что видят инструменты: python -m fb.source (из tools/).
"""
import glob
import os

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
GAME = os.environ.get("FB_GAME", "nhl24")
DATA = os.path.abspath(os.environ.get("FB_DATA") or os.path.join(REPO, "game", "other", GAME, "Data"))
_patch = os.environ.get("FB_PATCH") or os.path.join(os.path.dirname(DATA), "Patch")
PATCH = os.path.abspath(_patch) if os.path.isdir(_patch) or os.environ.get("FB_PATCH") else None
WORK = os.path.abspath(os.environ.get("FB_WORK") or os.path.join(REPO, "game", "work", GAME))
CATALOG = os.path.join(WORK, "catalog")
PACKAGE = os.environ.get("FB_PACKAGE", "nhl_installpackage_")


def _platform():
    p = os.environ.get("FB_PLATFORM")
    if p:
        return p
    ini = sorted(glob.glob(os.path.join(DATA, "initfs_*")))
    return os.path.basename(ini[0])[len("initfs_"):] if ini else "Gen4b"


PLATFORM = _platform()
PLATFORM_DIR = os.path.join(DATA, PLATFORM)
LAYOUT = os.path.join(PLATFORM_DIR, "superbundlelayout")


def _ooz():
    for p in (os.path.join(WORK, "bin", "ooz.dll"), os.path.join(REPO, "game", "work", "nhl24", "bin", "ooz.dll")):
        if os.path.exists(p):
            return p
    return os.path.join(WORK, "bin", "ooz.dll")


OOZ_DLL = _ooz()


def cas_path(package, casn, patch=0):
    """Файл cas_NN.cas пакета NN (из записей TOC: catalog, cas, patch). patch ≠ 0 — из папки патча, если она есть."""
    root = PATCH if patch and PATCH else DATA
    return os.path.join(root, PLATFORM, "superbundlelayout", f"{PACKAGE}{package:02d}", f"cas_{casn:02d}.cas")


def describe():
    return {"game": GAME, "data": DATA, "patch": PATCH, "platform": PLATFORM, "layout": LAYOUT, "package": PACKAGE,
            "work": WORK, "catalog": CATALOG, "ooz": OOZ_DLL}


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    for k, v in describe().items():
        ok = "" if v is None or k in ("game", "platform", "package") else ("" if os.path.exists(v) else "  (нет)")
        print(f"{k:9} {v}{ok}")
