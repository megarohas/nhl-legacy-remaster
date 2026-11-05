"""Где лежат сейвы NHL Legacy Remaster — в обеих раскладках (docs/legacy-port.md, «Папка saves»).

С 0.17.0 всё личное — в папке saves рядом с exe (nhl_saves_root в nhllegacy.toml, по умолчанию saves):
    saves\\profiles\\PROFILE 20261105030242\\PROFILE 20261105030242     сейв (папка и файл с одним именем)
    saves\\profiles\\PROFILE 20261105030242.header                       его заголовок (имя в меню)
    saves\\rosters\\…, franchises\\…, be-a-pro\\…  — по префиксу имени (таблица FOLDERS, как в nhllegacy_saves.cpp)
До 0.17.0 (и пока установка не переведена): userdata\\<xuid>\\454109EC\\00000001\\<имя>\\<имя>,
заголовки — userdata\\<xuid>\\454109EC\\Headers\\00000001\\<имя>.header.

Раскладка установки определяется так: если в папке saves есть хоть один сейв — новая, иначе старая.

    python tools/legacy_saves.py where  [--install DIR]               # раскладка и корень сейвов
    python tools/legacy_saves.py list   [--install DIR] [--kind ROSTER]
    python tools/legacy_saves.py latest KIND [--install DIR] [--paths] # файл новейшего сейва вида (ROSTER, PROFILE…);
                                                                      # --paths: три строки — файл, папка, заголовок

--install — папка с nhllegacy.exe и nhllegacy.toml; по умолчанию установка на этом ПК
(nhl-legacy-port/out/build/win-amd64-release). Только чтение.

Из кода:
    from legacy_saves import Saves
    s = Saves.of_install()                 # или Saves.of_install(папка), Saves.of_userdata(userdata)
    s.latest('ROSTER').file                # новейший ROSTER (по времени в имени папки)
    s.place_for('ROSTER 20261105040000')   # (папка сейва, путь заголовка) для нового сейва
"""
import argparse
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_INSTALL = os.path.join(REPO, 'nhl-legacy-port', 'out', 'build', 'win-amd64-release')
TITLE = '454109EC'
SAVED_GAMES = '00000001'

# Префикс имени сейва → папка в saves (решение пользователя 05.11.2026; как kFolders в src/nhllegacy_saves.cpp).
FOLDERS = [
    ('PROFILE', 'profiles'), ('ROSTER', 'rosters'), ('DYNASTY', 'franchises'), ('BEAPRO', 'be-a-pro'),
    ('SEASON', 'seasons'), ('PLAYOFF', 'playoffs'), ('TOURNAMENT', 'tournaments'), ('HOCKEYCARD', 'hockey-cards'),
    ('BUILDYOURAI', 'build-your-ai'), ('SCENARIOFILE', 'scenarios'), ('DYNAMICRATINGS', 'dynamic-ratings'),
    ('RIVALRYGAME', 'rivalry-games'), ('ONLINEROSTER', 'online-rosters'), ('VIDEO', 'videos'),
    ('SCREENSHOT', 'screenshots'),
]
OTHER = 'other'
ALL_FOLDERS = [d for _, d in FOLDERS] + [OTHER]
NAME = re.compile(r'([A-Za-z_]+) (\d{14})(A?)')  # «ROSTER 20261024125927», автосейв — с «A» на конце


def prefix(name):
    m = re.match(r'[A-Za-z_]*', name)
    return m.group(0).upper()


def folder_for(name):
    p = prefix(name)
    return next((d for k, d in FOLDERS if k == p), OTHER)


def _toml_value(path, key):
    """Строковое значение ключа верхнего уровня в nhllegacy.toml (без разбора всего TOML); None — ключа нет."""
    try:
        text = open(path, encoding='utf-8-sig').read()
    except OSError:
        return None
    m = re.search(rf'(?m)^\s*{re.escape(key)}\s*=\s*"([^"]*)"', text)
    return m.group(1) if m else None


class SaveRef:
    def __init__(self, name, folder, header):
        self.name = name            # имя сейва (и папки), например ROSTER 20261024125927
        self.dir = folder           # папка сейва
        self.file = os.path.join(folder, name)  # внутренний файл сейва
        self.header = header        # путь заголовка (может не существовать)

    @property
    def kind(self):
        return prefix(self.name)

    @property
    def stamp(self):
        m = NAME.fullmatch(self.name)
        return m.group(2) if m else ''

    def __repr__(self):
        return f'SaveRef({self.name!r}, {self.dir!r})'


class Saves:
    """Сейвы одной установки: new — раскладка saves\\<вид>, иначе старая userdata\\<xuid>\\454109EC\\00000001."""

    def __init__(self, saves_root, userdata):
        self.saves_root = saves_root    # None — nhl_saves_root пуст (старая раскладка навсегда)
        self.userdata = userdata
        self.new = bool(saves_root) and any(self._new_refs())

    @classmethod
    def of_install(cls, install=None):
        install = os.path.abspath(install or DEFAULT_INSTALL)
        toml = os.path.join(install, 'nhllegacy.toml')
        sr = _toml_value(toml, 'nhl_saves_root')
        sr = 'saves' if sr is None else sr
        ud = _toml_value(toml, 'user_data_root') or 'userdata'
        rel = lambda p: os.path.normpath(p if os.path.isabs(p) else os.path.join(install, p))
        return cls(rel(sr) if sr else None, rel(ud))

    @classmethod
    def of_userdata(cls, userdata, saves_root=None):
        """Старая привязка инструментов к папке userdata; saves рядом с ней ищется как <userdata>\\..\\saves."""
        userdata = os.path.abspath(userdata)
        if saves_root is None:
            # установка на этом ПК: user_data_root в её nhllegacy.toml указывает сюда, saves — рядом с её exe
            inst = cls.of_install()
            if os.path.normcase(inst.userdata) == os.path.normcase(userdata) and inst.saves_root:
                saves_root = inst.saves_root
            else:  # папка релиза: userdata и saves рядом с exe
                guess = os.path.join(os.path.dirname(userdata), 'saves')
                saves_root = guess if os.path.isdir(guess) else None
        return cls(saves_root, userdata)

    # -- перечисление
    def _new_refs(self):
        if not self.saves_root:
            return
        for d in ALL_FOLDERS:
            base = os.path.join(self.saves_root, d)
            if not os.path.isdir(base):
                continue
            for n in sorted(os.listdir(base)):
                p = os.path.join(base, n)
                if os.path.isdir(p) and os.path.isfile(os.path.join(p, n)):
                    yield SaveRef(n, p, os.path.join(base, n + '.header'))

    def _old_refs(self):
        if not os.path.isdir(self.userdata):
            return
        for x in sorted(os.listdir(self.userdata)):
            base = os.path.join(self.userdata, x, TITLE, SAVED_GAMES)
            if not (re.fullmatch(r'[0-9A-Fa-f]{16}', x) and os.path.isdir(base)):
                continue
            headers = os.path.join(self.userdata, x, TITLE, 'Headers', SAVED_GAMES)
            for n in sorted(os.listdir(base)):
                p = os.path.join(base, n)
                if os.path.isdir(p) and os.path.isfile(os.path.join(p, n)):
                    yield SaveRef(n, p, os.path.join(headers, n + '.header'))

    def list(self, kind=None):
        refs = list(self._new_refs() if self.new else self._old_refs())
        if kind:
            refs = [r for r in refs if r.kind == kind.upper()]
        return sorted(refs, key=lambda r: (r.stamp, r.name))

    def latest(self, kind):
        refs = self.list(kind)
        if not refs:
            raise FileNotFoundError(f'нет сейвов {kind.upper()} в {self.where()}')
        return refs[-1]

    def where(self):
        if self.new:
            return self.saves_root
        return os.path.join(self.userdata, '<xuid>', TITLE, SAVED_GAMES)

    def place_for(self, name):
        """Куда класть новый сейв name: (папка сейва, путь заголовка) в действующей раскладке."""
        if self.new or (self.saves_root and not any(self._old_refs())):
            base = os.path.join(self.saves_root, folder_for(name))
            return os.path.join(base, name), os.path.join(base, name + '.header')
        xuid = next((x for x in sorted(os.listdir(self.userdata)) if re.fullmatch(r'[0-9A-Fa-f]{16}', x)),
                    'B13EBABEBABEBABE') if os.path.isdir(self.userdata) else 'B13EBABEBABEBABE'
        root = os.path.join(self.userdata, xuid, TITLE)
        return os.path.join(root, SAVED_GAMES, name), os.path.join(root, 'Headers', SAVED_GAMES, name + '.header')


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('cmd', choices=['where', 'list', 'latest'])
    p.add_argument('kind', nargs='?', help='вид сейва для latest: ROSTER, PROFILE, DYNASTY…')
    p.add_argument('--install', help='папка установки (nhllegacy.exe, nhllegacy.toml)')
    p.add_argument('--kind', dest='kind_opt', help='только этот вид (для list)')
    p.add_argument('--paths', action='store_true', help='latest: файл, папка сейва и заголовок — тремя строками')
    a = p.parse_args()
    s = Saves.of_install(a.install)
    if a.cmd == 'where':
        print(('saves (0.17.0+): ' if s.new else 'старая раскладка: ') + s.where())
    elif a.cmd == 'list':
        for r in s.list(a.kind_opt):
            print(r.file)
    else:
        if not a.kind:
            p.error('latest: укажите вид, например ROSTER')
        try:
            r = s.latest(a.kind)
        except FileNotFoundError as e:
            sys.exit(str(e))
        print('\n'.join([r.file, r.dir, r.header]) if a.paths else r.file)


if __name__ == '__main__':
    main()
