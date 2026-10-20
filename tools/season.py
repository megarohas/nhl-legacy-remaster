"""Сезон, под который собираются данные NHL Legacy: составы, контракты, календарь, кэш фото, номер сезона HockeyTech.
Один на все инструменты; по умолчанию — 2026/27 (как season_year порта у пользователя).

    NHL_SEASON=2027 bash tools/legacy_data/build-all.sh …   # сезон 2027/28 для всей сборки
    python tools/season.py                                  # что видят инструменты

YEAR — первый год сезона (2026), SEASON — номер в формате API НХЛ (20262027), LABEL — «2026/27». Номер сезона
HockeyTech (АХЛ) — таблица HT_SEASON_IDS, другой — переменной NHL_AHL_SEASON_ID (список сезонов —
`cd tools && python -m roster.ahl_ht summary`, поле season_id). В игре год задаёт cvar порта season_year — он должен
совпадать с YEAR (лаунчер, docs/launcher.md).
"""
import os
import sys

YEAR = int(os.environ.get("NHL_SEASON") or 2026)
SEASON = YEAR * 10000 + YEAR + 1
LABEL = f"{YEAR}/{(YEAR + 1) % 100:02d}"

# регулярный чемпионат АХЛ в HockeyTech: сезон → season_id (docs/research-data-sources.md §4)
HT_SEASON_IDS = {2026: 94}


def ht_season_id(strict=True):
    """season_id HockeyTech; нет — strict: выход с подсказкой, иначе None."""
    v = os.environ.get("NHL_AHL_SEASON_ID")
    if v:
        return int(v)
    if YEAR in HT_SEASON_IDS:
        return HT_SEASON_IDS[YEAR]
    if not strict:
        return None
    sys.exit(f"нет номера сезона HockeyTech для {LABEL}: задайте NHL_AHL_SEASON_ID (список — "
             f"cd tools && python -m roster.ahl_ht summary) или допишите tools/season.py HT_SEASON_IDS")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if "--ht-id" in sys.argv:                  # для build-all.sh: номер или пусто
        print(ht_season_id(strict=False) or "")
        sys.exit(0)
    print(f"сезон {LABEL}: YEAR {YEAR}, SEASON {SEASON}, HockeyTech season_id "
          f"{os.environ.get('NHL_AHL_SEASON_ID') or HT_SEASON_IDS.get(YEAR, '— (NHL_AHL_SEASON_ID)')}")
