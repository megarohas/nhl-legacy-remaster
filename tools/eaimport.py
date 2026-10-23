"""Импорт из новой EA NHL (дамп Frostbite: NHL 24 PS4, NHL 27 PS5, дальше — новые) в NHL Legacy — одна точка входа.

Каждая команда вызывает готовый инструмент (у каждого свой docstring и документ); здесь — порядок, пути и проверка
готовности. Руководство — docs/import-from-ea.md.

    python tools/eaimport.py status    [--game nhl27]          # что готово: дамп, проход, каталог, индекс TOC, база
    python tools/eaimport.py prepare   [--game nhl27]          # fb.scan --resume, fb.catalog, fb.toc index, база игры
    python tools/eaimport.py leagues   chl|europe [--game …]   # составы лиг (legacy_data/league27.py)
    python tools/eaimport.py stats     [--game …]              # история статистики (legacy_data/stats27.py)
    python tools/eaimport.py awards    [--game …]              # история наград и Кубка Стэнли (legacy_data/awards27.py)
    python tools/eaimport.py portraits [--game …]              # портреты тем, у кого нет (photos24.py --source)
    python tools/eaimport.py heads     [--game …] [--only папка,…]   # сканы голов (scans24.py --source)
    python tools/eaimport.py overlay                           # накладка out-nhl24 заново (пакет форм pack-edge)
    python tools/eaimport.py all       [--game …]              # leagues europe → chl → stats → awards → portraits

Формы — tools/kitport (docs/kitport.md), установка в игру — tools/legacy_data/install_legacy_data.py (status/diff/
install при закрытой игре). Ассеты EA — только для личного использования (game/, вне git).
"""
import argparse
import os
import subprocess
import sys

TOOLS = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TOOLS)
VENV = os.path.join(REPO, 'game', 'work', 'nhl24', 'venv', 'Scripts', 'python.exe')   # numpy, pillow, scipy, ooz
GAMES = ('nhl24', 'nhl27')                         # что сейчас умеют читать fb, photos24, scans24
DB_DIR = {'nhl24': os.path.join(REPO, 'game', 'work', 'photos-nhl24', 'nhl24db'),     # как у photos24.SOURCES
          'nhl27': os.path.join(REPO, 'game', 'work', 'nhl27', 'db')}


def py():
    return VENV if os.path.exists(VENV) else sys.executable


def env_for(game):
    e = dict(os.environ, FB_GAME=game, PYTHONIOENCODING='utf-8')
    e['NHL27_DB'] = os.path.join(DB_DIR[game], 'nhl_game.db')                          # база игры-источника
    return e


def run(cmd, game, cwd=TOOLS):
    print('>', ' '.join(os.path.relpath(c, REPO) if os.path.isabs(c) else c for c in cmd), flush=True)
    r = subprocess.run(cmd, cwd=cwd, env=env_for(game))
    if r.returncode:
        sys.exit(f'ошибка ({r.returncode}): {" ".join(cmd)}')


def paths(game):
    w = os.path.join(REPO, 'game', 'work', game)
    return {'data': os.path.join(REPO, 'game', 'other', game, 'Data'), 'scan': os.path.join(w, 'catalog', 'scan'),
            'catalog': os.path.join(w, 'catalog', 'textures.csv'), 'toc': os.path.join(w, 'catalog', 'toc_chunks.json'),
            'db': os.path.join(DB_DIR[game], 'nhl_game.db'), 'meta': os.path.join(DB_DIR[game], 'nhl_game-meta.xml')}


def cmd_status(game):
    p = paths(game)
    def mark(ok):
        return 'ok ' if ok else '-- '
    n_scan = len(os.listdir(p['scan'])) if os.path.isdir(p['scan']) else 0
    print(f'{game}:')
    print(f"  {mark(os.path.isdir(p['data']))}дамп            {p['data']}")
    print(f"  {mark(n_scan)}проход fb.scan  {n_scan} файлов")
    print(f"  {mark(os.path.exists(p['catalog']))}каталог         {p['catalog']}")
    print(f"  {mark(os.path.exists(p['toc']))}индекс TOC      {p['toc']}")
    print(f"  {mark(os.path.exists(p['db']) and os.path.exists(p['meta']))}база игры       {p['db']}")
    print('  дальше: prepare (если не всё ok), потом leagues/stats/awards/portraits/heads; формы — python -m kitport')


def cmd_prepare(game):
    p = paths(game)
    run([py(), '-m', 'fb.probe'], game)
    run([py(), '-m', 'fb.scan', '--jobs', '8', '--resume'], game)
    run([py(), '-m', 'fb.catalog'], game)
    if not os.path.exists(p['toc']):
        run([py(), '-m', 'fb.toc', 'index'], game)
    os.makedirs(os.path.dirname(p['db']), exist_ok=True)
    for name, out in (('gamemodes/database/t3db/nhl_game.db', p['db']), ('gamemodes/database/t3db/nhl_game-meta.xml', p['meta'])):
        if not os.path.exists(out):
            run([py(), '-m', 'fb.lfs', 'get', name, out], game)
    cmd_status(game)


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('cmd', choices=('status', 'prepare', 'leagues', 'stats', 'awards', 'portraits', 'heads', 'overlay', 'all'))
    ap.add_argument('what', nargs='?', help='leagues: chl | europe')
    ap.add_argument('--game', default='nhl27', choices=GAMES)
    ap.add_argument('--only', help='heads: только эти папки licensed/<папка> через запятую (пилот)')
    a = ap.parse_args()
    g = a.game
    ld = os.path.join(TOOLS, 'legacy_data')
    if a.cmd == 'status':
        cmd_status(g)
    elif a.cmd == 'prepare':
        cmd_prepare(g)
    elif a.cmd == 'leagues':
        if a.what not in ('chl', 'europe'):
            sys.exit('leagues: chl или europe')
        run([sys.executable, os.path.join(ld, 'league27.py'), a.what], g, REPO)
    elif a.cmd == 'stats':
        run([sys.executable, os.path.join(ld, 'stats27.py')], g, REPO)
    elif a.cmd == 'awards':
        run([sys.executable, os.path.join(ld, 'awards27.py'), '--write'], g, REPO)
    elif a.cmd == 'portraits':
        for step in ('match', 'build', 'apply'):
            run([py(), 'photos24.py', step, '--source', g] + (['--jobs', '8'] if step == 'build' else []), g)
    elif a.cmd == 'heads':
        run([py(), 'scans24.py', 'match', '--source', g], g)
        run([py(), 'scans24.py', 'build', '--source', g] + (['--only', a.only] if a.only else []), g)
        run([py(), 'scans24.py', 'apply', '--source', g], g)
    elif a.cmd == 'overlay':
        e = dict(env_for(g), NHL24_PACK='game/work/nhl24/out/pack-edge')
        r = subprocess.run(['bash', 'tools/legacy_data/build-all.sh', 'nhl24'], cwd=REPO, env=e)
        sys.exit(r.returncode)
    elif a.cmd == 'all':
        for sub in (['leagues', 'europe'], ['leagues', 'chl'], ['stats'], ['awards'], ['portraits']):
            subprocess.run([sys.executable, __file__] + sub + ['--game', g], check=True)
        print('головы — отдельно (eaimport.py heads, сначала пилот --only); потом eaimport.py overlay и установка')


if __name__ == '__main__':
    main()
