"""Источник текстур форм для переноса (fb.pilot, fb.edge_kit): NHL 24 (по умолчанию) или NHL 27.

Выгрузка комплектов клуба — game/work/<источник>/extract/club_<папка клуба> (fb.extract с FB_GAME=<источник>).
Сетки-источники переноса (свитер adidas, шорты, гетры) — всегда NHL 24: развёртка у NHL 27 та же (свитер — до
0,00034 по UV, ≈ 0,7 текселя на 2048; шорты и гетры — совпадают, 21.10.2026), а текстура переносится по UV.

Выбор: переменная окружения KIT_SOURCE или use(<источник>) (fb.edge_kit — по профилю клуба, edge_clubs.toml).
"""
import os

from .cas import REPO

SOURCES = ("nhl24", "nhl27")
_SOURCE = [os.environ.get("KIT_SOURCE", "nhl24")]


def use(source):
    if source not in SOURCES:
        raise SystemExit(f"источник форм {source!r}: {', '.join(SOURCES)}")
    _SOURCE[0] = source


def source():
    return _SOURCE[0]


def extract_root():
    return os.path.join(REPO, "game", "work", source(), "extract")
