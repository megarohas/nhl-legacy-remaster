"""Конвейер составов НХЛ 2026/27 для nhlng.db (NHL 13): fetch → build → lines → match → write → report.

    python tools/roster fetch  [--only nhl,ea,nhlratings,wiki,dfo] [--refresh]  # API → game/work/roster-cache/
    python tools/roster build                       # кэш → game/work/roster/players.json
    python tools/roster lines                       # звенья DailyFaceoff + players.json → lines.json
    python tools/roster match                       # players.json + база → match.json
    python tools/roster write  [--db-in DB] [--db-out DB] [--rating-lines]   # → game/work/roster/nhlng.db
    python tools/roster report                      # → game/work/roster/report.md
    python tools/roster all    [--offline]          # всё подряд
    python tools/roster all --offline --work roster-lines   # всё в другую папку: game/work/roster-lines/

Вход по умолчанию — game/work/nhl32/nhlng.db (НХЛ на 32 команды, tools/nhl32.py), выход —
game/work/roster/nhlng.db (или --work/nhlng.db); в game/userdata/ ничего не пишется.
Подробно — docs/roster-pipeline.md.
"""
import argparse
import sys

from .common import Paths

STAGES = ['fetch', 'build', 'lines', 'match', 'write', 'report']


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    ap = argparse.ArgumentParser(prog='python tools/roster', description=__doc__.splitlines()[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter, epilog='\n'.join(__doc__.splitlines()[2:]))
    ap.add_argument('stage', choices=STAGES + ['all'])
    ap.add_argument('--game', help='каталог game/ (по умолчанию — основной копии репозитория)')
    ap.add_argument('--work', help='папка players.json, lines.json, match.json, write.json, отчётов и выходной базы: '
                                   'имя в game/work/ (roster-lines или game/work/roster-lines) или абсолютный путь '
                                   '(по умолчанию game/work/roster)')
    ap.add_argument('--db-in', help='входная база (по умолчанию game/work/nhl32/nhlng.db)')
    ap.add_argument('--db-out', help='выходная база (по умолчанию <work>/nhlng.db)')
    ap.add_argument('--only', help='fetch: части через запятую (nhl, ea, nhlratings, wiki, dfo)')
    ap.add_argument('--refresh', action='store_true', help='fetch: скачать заново, не глядя в кэш')
    ap.add_argument('--offline', action='store_true', help='только кэш; нет файла — ошибка')
    ap.add_argument('--pause', type=float, default=1.0, help='пауза между запросами к хосту, с (не меньше 1)')
    ap.add_argument('--rating-lines', action='store_true', help='write: звенья всех клубов по рейтингу, без lines.json')
    a = ap.parse_args()
    paths = Paths(a.game, a.work)
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
