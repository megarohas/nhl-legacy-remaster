"""Конвейер составов НХЛ 2026/27 для nhlng.db (NHL 13): fetch → build → lines → match → write → report.

    python tools/roster fetch  [--only nhl,ea,nhlratings,wiki,dfo] [--refresh]  # API → game/work/roster-cache/
    python tools/roster build                       # кэш → game/work/roster/players.json
    python tools/roster lines                       # звенья DailyFaceoff + players.json → lines.json
    python tools/roster match                       # players.json + база → match.json
    python tools/roster write  [--db-in DB] [--db-out DB] [--rating-lines]   # → game/work/roster/nhlng.db
    python tools/roster report                      # → game/work/roster/report.md, report-lines.md
    python tools/roster photos                      # фото не из НХЛ → кадр НХЛ (photos_other.py), лист photos-sheet.html
    python tools/roster all    [--offline]          # всё подряд
    python tools/roster all --offline --work roster-lines   # всё в другую папку: game/work/roster-lines/
    python tools/roster all --ahl32 --db-in game/work/nhl32-ahl32/nhlng.db --work roster-ahl32
                                                    # и фарм-клубы Сиэтла и Вегаса (база nhl32.py --ahl32)

Вход по умолчанию — game/work/nhl32/nhlng.db (НХЛ на 32 команды, tools/nhl32.py), выход —
game/work/roster/nhlng.db (или --work/nhlng.db); в game/userdata/ ничего не пишется.
Подробно — docs/roster-pipeline.md.

NHL Legacy: --game legacy (или NHL_GAME=legacy) — база tools/nhl32.py --game legacy
(game/work/legacy-data/nhl32/nhlng.db), папки — в game/work/legacy-data/ (roster, своя таблица artid);
кэш сети — общий. --ahl32 у Legacy — база nhl32 --game legacy --ahl32 (CV/HSK на 224/225). Подробно — docs/legacy-data.md.
"""
import argparse
import os
import sys

from .common import Paths, set_game
import gameprofile  # noqa: E402  (tools/ в sys.path — common.py)

STAGES = ['fetch', 'build', 'lines', 'match', 'write', 'report']


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    ap = argparse.ArgumentParser(prog='python tools/roster', description=__doc__.splitlines()[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter, epilog='\n'.join(__doc__.splitlines()[2:]))
    ap.add_argument('stage', choices=STAGES + ['all', 'photos'])
    ap.add_argument('--game', help='каталог game/ (по умолчанию — основной копии репозитория) или игра: nhl13, '
                                   'legacy (NHL Legacy, tools/gameprofile.py; иначе NHL_GAME, по умолчанию nhl13)')
    ap.add_argument('--work', help='папка players.json, lines.json, match.json, write.json, отчётов и выходной базы: '
                                   'имя в game/work/ (roster-lines или game/work/roster-lines) или абсолютный путь '
                                   '(по умолчанию game/work/roster)')
    ap.add_argument('--db-in', help='входная база (по умолчанию game/work/nhl32/nhlng.db)')
    ap.add_argument('--db-out', help='выходная база (по умолчанию <work>/nhlng.db)')
    ap.add_argument('--only', help='fetch: части через запятую (nhl, ea, nhlratings, wiki, dfo, ahl, fa, liiga)')
    ap.add_argument('--ahl32', action='store_true',
                    help='и клубы АХЛ из common.AHL_CLUBS (фарм-клубы Сиэтла и Вегаса; база tools/nhl32.py --ahl32)')
    ap.add_argument('--refresh', action='store_true', help='fetch: скачать заново, не глядя в кэш')
    ap.add_argument('--offline', action='store_true', help='только кэш; нет файла — ошибка')
    ap.add_argument('--pause', type=float, default=1.0, help='пауза между запросами к хосту, с (не меньше 1)')
    ap.add_argument('--rating-lines', action='store_true', help='write: звенья всех клубов по рейтингу, без lines.json')
    ap.add_argument('--stats-ratings', action='store_true',
                    help='build: OVR по статистике трёх сезонов с NHL-эквивалентами лиг (statsrating.py) у игроков '
                         'без рейтинга и смесь с «только OVR» у малоопытных; отчёт report-ratings.md')
    ap.add_argument('--fa', action='store_true',
                    help='и свободные агенты: игроки НХЛ 2024/25–2025/26 без клуба (fa.py) → exhibitionfreeagents')
    ap.add_argument('--skin', action='store_true',
                    help='write: типовая голова под тон кожи на официальном фото (skin.py), лист проверки skin-sheet.html')
    ap.add_argument('--league', choices=['liiga'],
                    help='и клубы лиги нынешними составами с сайта лиги (league.py; проба — финская Liiga, строки 74–87)')
    ap.add_argument('--payroll-max', type=float, metavar='МЛН',
                    help='write: ведомость состава клуба НХЛ не больше МЛН $ — контракты-заглушки клуба выше минималки '
                         'ужимаются одним коэффициентом (write.cap_payroll; NHL Legacy: потолок 2026/27 — 104)')
    a = ap.parse_args()
    profile = None
    if a.game and a.game.lower() in gameprofile.GAMES:      # --game legacy — игра, а не каталог
        profile, a.game = a.game.lower(), None
    game = set_game(profile or gameprofile.default_name())
    paths = Paths(a.game, a.work)
    paths.ahl = a.ahl32
    paths.stats_ratings = a.stats_ratings
    paths.fa = a.fa
    paths.skin = a.skin
    paths.league = a.league
    paths.payroll_max = a.payroll_max
    if a.db_in:
        paths.db_in = a.db_in
    if a.db_out:
        paths.db_out = a.db_out
    stages = STAGES if a.stage == 'all' else [a.stage]
    if a.offline and 'fetch' in stages:
        stages = [s for s in stages if s != 'fetch']
    for stage in stages:
        print(f'== {stage}')
        if stage == 'fetch':
            from . import fetch
            fetch.run(paths, a.only.split(',') if a.only else None, pause=max(1.0, a.pause), refresh=a.refresh)
        elif stage == 'build':
            from . import build
            build.run(paths)
        elif stage == 'lines':
            from . import lines_real
            lines_real.run(paths)
        elif stage == 'match':
            from . import match
            match.run(paths)
        elif stage == 'write':
            from . import write
            write.run(paths, real_lines=not a.rating_lines)
        elif stage == 'report':
            from . import report
            report.run(paths)
        elif stage == 'photos':
            # фото не из НХЛ: NHL latest и портреты лиг → кадр НХЛ (photos_other.py); в «all» не входит
            from . import photos_other
            photos_other.run(paths, offline=a.offline)
            if os.path.exists(paths.written):
                photos_other.build(paths)               # → game/work/photos-other/ (не photos-all)
