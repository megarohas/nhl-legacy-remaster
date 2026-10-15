"""Ставит / снимает моды-данные NHL Legacy (game/work/legacy-data/out — дерево путей как в cache:) в cache:
порта Legacy. Только при закрытой игре (или игре с другой папкой userdata). Вызывается из
tools/legacy_data/install-legacy-data.sh / uninstall-legacy-data.sh (docs/legacy-data.md).

    python tools/legacy_data/install_legacy_data.py install [--ahl32] [--nhl24] [ЧАСТЬ… | @СПИСОК…]
    python tools/legacy_data/install_legacy_data.py uninstall [ЧАСТЬ… | --nhl24]

--ahl32 — поверх out ещё накладка out-ahl32 (база и локализация «АХЛ на 32»: CV/HSK, nhl32 --ahl32;
франшизе нужен порт с врезками АХЛ на 32).
--nhl24 — и накладка out-nhl24 (пакет NHL 24: формы, лёд, шлемы, шайба, клюшки и база с новыми строками формы;
с --ahl32 база — из out-nhl24-ahl32; собирает этап build-all.sh nhl24, docs/legacy-data.md, «Пакет NHL 24»).
uninstall --nhl24 снимает только её: полная установка с прежними флагами без --nhl24 (cache: — как до накладки).
Флаги последней полной установки — в install-flags.txt рядом с installed.txt. Чтобы полной установкой случайно не
снять стоящую накладку, без её флага установка отказывается: --no-ahl32 / --no-nhl24 — снять сознательно.

ЧАСТЬ — начало пути (db, fe/loc, fe/ion/fonts, audio, rendering…), @СПИСОК — файл со списком путей
(files.txt помощников); без частей — всё из out (и тогда файлы прошлой установки, которых в out больше
нет, убираются). Папка cache: — переменная CACHE или строка «CACHE: …» в game/work/status/legacy-port.md.
Чужой файл, лежавший в cache: до первой установки, сохраняется в legacy-data/backup/ и возвращается при
снятии; список поставленного — legacy-data/installed.txt. Своя папка для них (проверка на копии userdata) —
переменная LEGACY_DATA_STATE; вместе с CACHE=копия она не трогает установку пользователя.

Восстановлен 09.10.2026 после потери game/ (docs/incident-2026-10-09.md) по транскрипту агента legacy-data,
сверен с уцелевшим .pyc; с тех пор живёт в git (tools/legacy_data/), выход сборки — в game/work/legacy-data/.
"""
import filecmp
import os
import re
import shutil
import subprocess
import sys



def _repo():
    """Репозиторий: tools/legacy_data/ → корень; из рабочей копии git worktree — основная копия (там game/)."""
    here = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if os.path.isdir(os.path.join(here, 'game')):
        return here
    dotgit = os.path.join(here, '.git')
    if os.path.isfile(dotgit):
        m = re.match(r'gitdir:\s*(.+)', open(dotgit, encoding='utf-8').read().strip())
        if m:
            main = os.path.normpath(os.path.join(m.group(1), os.pardir, os.pardir, os.pardir))
            if os.path.isdir(os.path.join(main, 'game')):
                return main
    return here


GAME = os.path.join(_repo(), 'game')
W = os.path.abspath(os.environ.get('LEGACY_DATA_WORK') or os.path.join(GAME, 'work', 'legacy-data'))   # выход — вне git
SRC = os.path.join(W, 'out')
SRC_AHL32 = os.path.join(W, 'out-ahl32')
SRC_NHL24 = os.path.join(W, 'out-nhl24')                # накладка пакета NHL 24 (nhl24.py build)
SRC_NHL24_AHL32 = os.path.join(W, 'out-nhl24-ahl32')    # её база для варианта --ahl32
NHL24_REPORT = os.path.join(W, 'nhl24', 'report.json')  # из каких баз out собрана накладка
STATE = os.environ.get('LEGACY_DATA_STATE') or W        # installed.txt и backup/ (своя папка — для проверки на копии)
LIST = os.path.join(STATE, 'installed.txt')
BACKUP = os.path.join(STATE, 'backup')
FLAGS = os.path.join(STATE, 'install-flags.txt')        # флаги последней полной установки (--ahl32, --nhl24)


def cache_dir():
    env = os.environ.get('CACHE')
    if env:
        return os.path.normpath(env)
    st = os.path.join(GAME, 'work', 'status', 'legacy-port.md')
    for line in open(st, encoding='utf-8', errors='replace'):
        m = re.match(r'CACHE:\s*(\S+)', line)
        if m:
            return os.path.normpath(m.group(1))
    sys.exit('не знаю папку cache: порта (нет строки CACHE: в work/status/legacy-port.md, задайте CACHE=…)')


def game_running():
    out = subprocess.run(['tasklist'], capture_output=True, text=True, errors='replace').stdout.lower()
    return 'nhllegacy' in out


def _norm(path):
    return os.path.normcase(os.path.normpath(path))


def _toml_root(exe):
    """user_data_root из nhllegacy.toml рядом с exe: пусто — userdata рядом с exe; нет файла или строки — None."""
    toml = os.path.join(os.path.dirname(exe), 'nhllegacy.toml')
    try:
        text = open(toml, encoding='utf-8', errors='replace').read()
    except OSError:
        return None
    m = re.search(r'^\s*user_data_root\s*=\s*"([^"]*)"', text, re.M)
    if not m:
        return None
    return _norm(m.group(1) or os.path.join(os.path.dirname(exe), 'userdata'))


def running_roots():
    """user_data_root каждой запущенной nhllegacy.exe (--user_data_root= в командной строке, иначе из её
    nhllegacy.toml); None — не удалось узнать."""
    cmd = ("Get-CimInstance Win32_Process -Filter \"name='nhllegacy.exe'\" | "
           "ForEach-Object { $_.ExecutablePath + '|' + $_.CommandLine }")
    try:
        out = subprocess.run(['powershell', '-NoProfile', '-Command', cmd], capture_output=True, text=True,
                             errors='replace', timeout=120).stdout
    except (OSError, subprocess.SubprocessError):
        return [None]
    roots = []
    for line in out.splitlines():
        exe, sep, args = line.strip().partition('|')
        if not sep:
            continue
        m = re.search(r'--user_data_root=("?)([^"\s]+)\1', args)
        roots.append(_norm(m.group(2)) if m else (_toml_root(exe) if exe else None))
    return roots or [None]


def read_list(path):
    return [l.strip() for l in open(path, encoding='utf-8') if l.strip()] if os.path.exists(path) else []


def write_list(path, items):
    with open(path + '.part', 'w', encoding='utf-8', newline='\n') as f:
        f.write(''.join(i + '\n' for i in items))
    os.replace(path + '.part', path)


def parse_parts(args, cwd):
    parts = []
    for a in args:
        if a.startswith('@'):
            p = a[1:] if os.path.isabs(a[1:]) else os.path.join(cwd, a[1:])
            if not os.path.exists(p):
                sys.exit(f'нет списка {p}')
            parts += read_list(p)
        else:
            parts.append(a.strip('/'))
    return parts


def selected(rel, parts):
    return not parts or any(rel == p or rel.startswith(p + '/') for p in parts)


def _md5(path):
    import hashlib
    h = hashlib.md5()
    with open(path, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


def installed_flags(cache):
    """Флаги стоящей установки: из install-flags.txt; до него (установки 08–09.10) --ahl32 узнаётся по базе."""
    if os.path.exists(FLAGS):
        return set(read_list(FLAGS))
    db = os.path.join(cache, 'db', 'nhlng.db')
    ref = os.path.join(SRC_AHL32, 'db', 'nhlng.db')
    if read_list(LIST) and os.path.exists(db) and os.path.exists(ref) and _md5(db) == _md5(ref):
        return {'--ahl32'}
    return set()


def check_nhl24(ahl32):
    """Накладка NHL 24 собрана и база её — из нынешних out (out-ahl32): иначе новая база out затёрлась бы старой."""
    import json
    if not os.path.isdir(SRC_NHL24) or not os.path.exists(NHL24_REPORT):
        sys.exit(f'нет накладки {SRC_NHL24} (bash tools/legacy_data/build-all.sh nhl24)')
    rep = json.load(open(NHL24_REPORT, encoding='utf-8'))
    for key, base, dst in [('out', SRC, SRC_NHL24)] + ([('out-ahl32', SRC_AHL32, SRC_NHL24_AHL32)] if ahl32 else []):
        if key not in rep or not os.path.exists(os.path.join(dst, 'db', 'nhlng.db')):
            sys.exit(f'у накладки NHL 24 нет базы для {key} (build-all.sh nhl24 после collect{" --ahl32" if ahl32 else ""})')
        if rep[key]['base_md5'] != _md5(os.path.join(base, 'db', 'nhlng.db')):
            sys.exit(f'база {key} пересобрана после накладки NHL 24 — сначала bash tools/legacy_data/build-all.sh nhl24')
        loc = os.path.join(base, 'fe', 'loc', 'NHL_ENG_US.db')      # подписи новых форм — в локализации накладки
        if 'loc_base_md5' in rep[key] and (not os.path.exists(loc) or rep[key]['loc_base_md5'] != _md5(loc)):
            sys.exit(f'локализация {key} пересобрана после накладки NHL 24 — сначала bash tools/legacy_data/build-all.sh nhl24')


def install(args, cwd):
    cache = cache_dir()
    if not os.path.isdir(SRC):
        sys.exit(f'нет сборки {SRC}')
    flags = {x for x in args if x in ('--ahl32', '--nhl24', '--no-ahl32', '--no-nhl24')}
    ahl32, nhl24 = '--ahl32' in flags, '--nhl24' in flags
    args = [x for x in args if x not in flags]
    if ahl32 and not os.path.isdir(SRC_AHL32):
        sys.exit(f'нет накладки {SRC_AHL32} (build-all.sh --ahl32)')
    if nhl24:
        check_nhl24(ahl32)
    parts = parse_parts(args, cwd)
    if not parts:
        had = installed_flags(cache)
        for f in ('--ahl32', '--nhl24'):
            if f in had and f not in flags and '--no-' + f[2:] not in flags:
                sys.exit(f'сейчас стоит накладка {f[2:]}: добавьте {f} (оставить) или --no-{f[2:]} (снять); '
                         f'накладку NHL 24 снимает uninstall-legacy-data.sh --nhl24')
    srcs = {}                                        # путь в cache: → файл-источник (накладка — главнее)
    for base in [SRC] + ([SRC_AHL32] if ahl32 else []) + ([SRC_NHL24] if nhl24 else []) + \
            ([SRC_NHL24_AHL32] if nhl24 and ahl32 else []):
        for root, _, names in os.walk(base):
            for n in names:
                if n.endswith('.part'):
                    continue
                full = os.path.join(root, n)
                rel = os.path.relpath(full, base).replace(os.sep, '/')
                if selected(rel, parts):
                    srcs[rel] = full
    files = sorted(srcs)
    if not files:
        sys.exit(f'в {SRC} нет файлов' + (f' для: {" ".join(parts)}' if parts else ''))
    before = set(read_list(LIST))
    changed = 0
    for rel in files:
        dst = os.path.join(cache, *rel.split('/'))
        src = srcs[rel]
        bak = os.path.join(BACKUP, *rel.split('/'))
        if os.path.exists(dst) and rel not in before and not os.path.exists(bak):
            os.makedirs(os.path.dirname(bak), exist_ok=True)
            shutil.copy2(dst, bak)
            print(f'сохранён прежний {rel} → {BACKUP}')
        if not (os.path.exists(dst) and filecmp.cmp(src, dst, shallow=False)):
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copyfile(src, dst)
            changed += 1
    now = set(files)
    if parts:
        installed = sorted(before | now)
    else:
        for rel in sorted(before - now):             # полная установка: прошлое, которого нет в out
            restore(cache, rel)
            print(f'убран {rel}')
        installed = sorted(now)
    write_list(LIST, installed)
    if not parts:
        write_list(FLAGS, [f for f in ('--ahl32', '--nhl24') if f in flags])
    extra = (' (+ АХЛ на 32)' if ahl32 else '') + (' (+ пакет NHL 24)' if nhl24 else '')
    print(f'NHL Legacy, моды-данные{extra}: обновлено {changed} из {len(files)} файлов → {cache}; '
          f'всего поставлено {len(installed)}')


def restore(cache, rel):
    dst = os.path.join(cache, *rel.split('/'))
    bak = os.path.join(BACKUP, *rel.split('/'))
    if os.path.exists(bak):
        shutil.copy2(bak, dst)
        os.remove(bak)
    elif os.path.exists(dst):
        os.remove(dst)


def uninstall(args, cwd):
    cache = cache_dir()
    if '--nhl24' in args:                            # только накладка NHL 24: полная установка без неё
        had = installed_flags(cache)
        if '--nhl24' not in had or len(args) > 1:
            sys.exit('накладка NHL 24 не стоит' if '--nhl24' not in had else 'uninstall --nhl24 — без частей')
        install(sorted(had - {'--nhl24'}) + ['--no-nhl24'], cwd)
        print('накладка NHL 24 снята: cache: — как до неё')
        return
    parts = parse_parts(args, cwd)
    items = read_list(LIST)
    if not items:
        print(f'ничего не поставлено ({LIST} нет)')
        return
    keep, n = [], 0
    for rel in items:
        if selected(rel, parts):
            restore(cache, rel)
            n += 1
        else:
            keep.append(rel)
    if keep:
        write_list(LIST, keep)
    else:
        os.remove(LIST)
        if os.path.exists(FLAGS):
            os.remove(FLAGS)
    print(f'NHL Legacy, моды-данные: снято {n} файлов из {cache}')


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')         # сообщения sys.exit
    if len(sys.argv) < 2 or sys.argv[1] not in ('install', 'uninstall'):
        sys.exit(__doc__)
    if game_running():
        # игра с другой папкой userdata (например, тестовая копия nhl-legacy-port) этот cache: не читает — можно
        target = _norm(os.path.join(cache_dir(), os.pardir, os.pardir))      # CACHE = <user_data_root>/cache/guest
        roots = running_roots()
        if any(r is None or r == target for r in roots):
            print(f'NHL Legacy запущена с этим cache: (или не удалось проверить: {roots}) — закройте игру')
            sys.exit(2)
        print(f'NHL Legacy запущена, но с другой папкой userdata ({roots}) — этот cache: она не читает')
    cwd = os.environ.get('ORIG_PWD') or os.getcwd()
    (install if sys.argv[1] == 'install' else uninstall)(sys.argv[2:], cwd)


if __name__ == '__main__':
    main()

