"""Источник текстур форм для переноса (fb.pilot, fb.edge_kit): NHL 24 (по умолчанию) или NHL 27.

Выгрузка комплектов клуба — game/work/<источник>/extract/club_<папка клуба> (fb.extract с FB_GAME=<источник>).
Сетки-источники переноса (свитер adidas, шорты, гетры) — всегда NHL 24: развёртка у NHL 27 та же (свитер — до
0,00034 по UV, ≈ 0,7 текселя на 2048; шорты и гетры — совпадают, 21.10.2026), а текстура переносится по UV.

Выбор: переменная окружения KIT_SOURCE или use(<источник>) (fb.edge_kit — по профилю клуба, edge_clubs.toml).

Комплекты источника (профиль source_kits, 21.10.2026): метка формы (home, away) → папка комплекта adidas/<папка>.
В NHL 27 папки home/away — прежние формы времён NHL 24, нынешние — ten/eleven и дальше (по базе NHL 27,
kitport survey). Без source_kits папка = метка. Через folder() идут все файлы источника по метке: свитер, основа,
рельеф, шрифт, шорты, гетры, наклейка на шлем.
"""
import os

from .cas import REPO

SOURCES = ("nhl24", "nhl27")
_SOURCE = [os.environ.get("KIT_SOURCE", "nhl24")]
_KITS = {}                         # метка формы → папка комплекта источника (профиль source_kits)


def use(source, kits=None):
    if source not in SOURCES:
        raise SystemExit(f"источник форм {source!r}: {', '.join(SOURCES)}")
    _SOURCE[0] = source
    _KITS.clear()
    _KITS.update(kits or {})


def source():
    return _SOURCE[0]


def folder(kit):
    """Папка комплекта источника для метки формы (source_kits профиля; нет — сама метка)."""
    return _KITS.get(kit, kit)


def extract_root():
    return os.path.join(REPO, "game", "work", source(), "extract")
