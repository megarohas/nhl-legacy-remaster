"""Профиль игры для инструментов: NHL 13 или NHL Legacy — пути, схема базы, номера строк, лиг и арта.

    python tools/gameprofile.py [--game legacy]        # профиль: пути и константы, проверка файлов
    python tools/gameprofile.py --detect FILE …        # какой игры база или сейв

Инструменты, которые умеют обе игры, берут профиль опцией `--game {nhl13,legacy}` (или переменной
окружения `NHL_GAME`); по умолчанию — NHL 13, как было до профиля. Без профиля инструмент,
написанный под NHL 13, молча портит данные Legacy: у неё другие строки особых команд (Custom
222…251, а не 218…247), лиги после строки 61 сдвинуты, номера арта 98/99 заняты, рейтинги — `c_*`
вместо `p_*`/`g_*`. Поэтому `check_db` сверяет базу с профилем и останавливает инструмент, если
база — от другой игры (разбор отличий — docs/legacy-port-feasibility.md, docs/legacy-data.md).

Пути (каталог game/ — не в git, ищется как в tools/roster/common.py, переменная `NHL13_GAME`):

| | NHL 13 | NHL Legacy |
|---|---|---|
| распакованные архивы | game/extracted/big/<архив>/ | game/other/legacy/big/<архив>/ |
| диск (.big) | game/extracted/disc/ | game/other/legacy/disc/ |
| образ default.xex | game/extracted/xex/default.bin | game/other/legacy/xex/default.bin |
| работа инструментов | game/work/<папка>/ | game/work/legacy-data/<папка>/ |
| cache: порта | game/userdata/cache/guest/ | строка «CACHE: …» статуса legacy-port или `NHL_LEGACY_CACHE` |

Константы, нужные одному инструменту, живут в нём по ключу профиля (MUSIC в music.py — вторые версии
песен, слоты EA Trax; LOWER_NAMES в fefont.py — строчные имена файлов в cache: у Legacy; legacy_config
в nhl32.py — берёт отсюда строки, арт и прожекторы). Сводка — docs/legacy-data.md.
"""
import argparse, os, re, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
GAMES = ('nhl13', 'legacy')


def _main_repo():
    """Корень основной рабочей копии (для worktree — по строке gitdir в файле .git)."""
    git = os.path.join(REPO, '.git')
    if os.path.isfile(git):
        line = open(git, encoding='utf-8').read().strip()
        if line.startswith('gitdir:'):
            parts = os.path.normpath(line.split(':', 1)[1].strip()).split(os.sep)
            if 'worktrees' in parts:
                return os.sep.join(parts[:parts.index('worktrees') - 1])
    return REPO


def game_dir():
    env = os.environ.get('NHL13_GAME')
    if env:
        return env
    for root in (REPO, _main_repo()):
        p = os.path.join(root, 'game')
        if os.path.isdir(p):
            return p
    return os.path.join(REPO, 'game')


def ref_dir():
    for root in (REPO, _main_repo()):
        p = os.path.join(root, 'ref')
        if os.path.isdir(p):
            return p
    return os.path.join(REPO, 'ref')


class Profile:
    """Пути и константы одной игры. Номера строк exhibitionteams — исходной базы игры (до nhl32)."""

    def __init__(self, name, **kw):
        self.name = name
        self.__dict__.update(kw)

    # --- пути -------------------------------------------------------------------------------
    @property
    def game(self):
        return game_dir()

    def _g(self, *parts):
        return os.path.join(self.game, *parts)

    @property
    def big(self):
        """Корень распакованных архивов: <big>/<архив>/<путь в архиве>."""
        return self._g(*self.big_parts)

    @property
    def disc(self):
        return self._g(*self.disc_parts)

    @property
    def xex(self):
        return self._g(*self.xex_parts)

    @property
    def work(self):
        """Корень промежуточных файлов инструментов этой игры. У NHL Legacy его можно перенести переменной
        LEGACY_DATA_WORK (сухой прогон tools/legacy_data/build-all.sh в отдельную папку; out — внутри неё)."""
        if self.name == 'legacy' and os.environ.get('LEGACY_DATA_WORK'):
            return os.path.abspath(os.environ['LEGACY_DATA_WORK'])
        return self._g(*self.work_parts)

    def work_dir(self, *parts):
        return os.path.join(self.work, *parts)

    @property
    def out(self):
        """Готовый набор файлов для cache: этой игры (дерево путей как в cache:)."""
        if self.name == 'legacy' and os.environ.get('LEGACY_DATA_WORK'):
            return os.path.join(self.work, 'out')
        return self._g(*self.out_parts)

    @property
    def install(self):
        """Папка cache: порта (куда ставятся моды) или None, если её ещё нет."""
        if self.name == 'nhl13':
            return self._g('userdata', 'cache', 'guest')
        env = os.environ.get('NHL_LEGACY_CACHE')
        if env:
            return env
        status = self._g('work', 'status', 'legacy-port.md')
        if os.path.exists(status):
            for line in open(status, encoding='utf-8', errors='replace'):
                m = re.match(r'\s*CACHE:\s*(\S.*?)\s*$', line)
                if m and not m.group(1).startswith('('):
                    path = m.group(1).split(' (')[0].strip().strip('`')
                    if re.match(r'^[A-Za-z]:[\\/]', path):
                        return os.path.normpath(path)
        return None

    def archive_path(self, archive, rel):
        return os.path.join(self.big, archive, *rel.replace('\\', '/').split('/'))

    def extracted(self, rel, archives=None):
        """Распакованный файл игры по пути в cache: (`db/nhlng.db`, `fe/ion/fonts/…`) — из первого
        архива, где он есть (порядок — `archives` или ARCHIVE_ORDER профиля); None, если нет нигде.
        Регистр имени не важен (в архивах Legacy имена строчные)."""
        for arc in archives or self.archive_order:
            p = self.archive_path(arc, rel)
            if os.path.exists(p):
                return p
            low = self.archive_path(arc, rel.lower())
            if os.path.exists(low):
                return low
        return None

    def archive_of(self, rel):
        p = self.extracted(rel)
        if not p:
            return None
        return os.path.relpath(p, self.big).split(os.sep)[0]

    @property
    def db(self):
        """Исходная nhlng.db игры."""
        return self.archive_path(self.db_archive, 'db/nhlng.db')

    @property
    def meta(self):
        """Схема nhlng-meta.xml игры: распакованная из архива, иначе анкер nhl-modding-studio."""
        p = self.archive_path(self.db_archive, 'db/nhlng-meta.xml')
        if os.path.exists(p):
            return p
        return os.path.join(ref_dir(), 'nhl-modding-studio', 'anchors', 'xbox360', self.anchor, 'databases',
                            'nhlng-meta.xml')

    @property
    def anchor_meta(self):
        return os.path.join(ref_dir(), 'nhl-modding-studio', 'anchors', 'xbox360', self.anchor, 'databases',
                            'nhlng-meta.xml')

    @property
    def loc(self):
        return self.archive_path(self.loc_archive, 'fe/loc/nhl_eng_us.db')

    @property
    def loc_meta(self):
        return self.archive_path(self.loc_archive, 'fe/loc/nhl_eng_us-meta.xml')

    # --- команды ----------------------------------------------------------------------------
    def league_rows(self, league):
        lo, hi = self.leagues[league][1:]
        return list(range(lo, hi + 1))

    def league_of_row(self, row):
        for name, (num, lo, hi) in self.leagues.items():
            if lo <= row <= hi:
                return name
        return None

    def describe(self):
        lines = [f'профиль {self.name}: {self.title} (TitleID {self.title_id})']
        for k in ('game', 'big', 'disc', 'xex', 'work', 'out', 'install', 'db', 'meta', 'loc'):
            v = getattr(self, k)
            ok = '' if v is None else ('' if os.path.exists(v) else '  (нет)')
            lines.append(f'  {k:8} {v}{ok}')
        lines.append('  лиги: ' + ', '.join(f'{n} {lo}–{hi} (league {num})' for n, (num, lo, hi) in self.leagues.items()))
        lines.append(f'  Custom 00/01: {self.custom[0]}/{self.custom[1]}, арена-шаблон {self.arena_template}, '
                     f'свободный арт {list(self.free_art)}, audioid2 «нет» = {self.audioid2_none}')
        lines.append(f'  рейтинги: полевые {self.skater_prefix}*, вратари {self.goalie_prefix}*, стиль '
                     f'{self.skater_style}/{self.goalie_style}; artid {self.artid_bits} бит')
        return '\n'.join(lines)


# Лиги: имя → (номер league, первая строка, последняя строка) в exhibitionteams исходной базы.
NHL13 = Profile(
    'nhl13', title='NHL 13', title_id='4541099B', anchor='nhl13',
    big_parts=('extracted', 'big'), disc_parts=('extracted', 'disc'), xex_parts=('extracted', 'xex', 'default.bin'),
    work_parts=('work',), out_parts=('userdata', 'cache', 'guest'),
    db_archive='cache', loc_archive='cache', fonts_archive='cache',
    archive_order=('cache', 'boot', 'cacherender', 'nocacherender', 'nocache', 'audioboot', 'audioboot2', 'data0',
                   'gamedata', 'tu2-patch'),
    leagues={'nhl': (0, 0, 31), 'ahl': (1, 32, 61), 'shl': (2, 62, 73), 'liiga': (3, 74, 87), 'del': (4, 88, 101),
             'extraliga': (5, 102, 115), 'nla': (6, 116, 127), 'national': (7, 128, 148), 'ohl': (8, 149, 168),
             'qmjhl': (9, 169, 186), 'whl': (10, 187, 208), 'prospects': (11, 209, 210), 'legends': (12, 211, 213),
             'winterclassic': (14, 214, 217), 'custom': (13, 218, 247)},
    allstar=(30, 31), custom=tuple(range(218, 248)), eashl=(),
    arena_template=168,                 # «EA SPORTS Arena» (арена заготовок Custom)
    tappara_tps=(86, 87),               # доноры формы SEA/VGK (Tappara, TPS)
    free_art=(98, 99, 100, 101),        # номера арта без файлов и без команд
    audioid2_none=0,
    # дивизионы НХЛ исходной базы: divisiongroup → конференция (1 Запад, 2 Восток)
    nhl_divisions={3: 1, 4: 1, 5: 1, 6: 2, 7: 2, 8: 2},
    skater_prefix='p_', goalie_prefix='g_', skater_style='p_style', goalie_style='g_style',
    artid_bits=14, generic_heads=(10000, 10999),
    new_team_spotlight=(45, 46),        # прожекторы SEA/VGK (nhl32)
)

LEGACY = Profile(
    'legacy', title='NHL Legacy Edition', title_id='454109EC', anchor='nhllegacy',
    big_parts=('other', 'legacy', 'big'), disc_parts=('other', 'legacy', 'disc'),
    xex_parts=('other', 'legacy', 'xex', 'default.bin'),
    work_parts=('work', 'legacy-data'), out_parts=('work', 'legacy-data', 'out'),
    db_archive='cacheboot', loc_archive='cacheboot', fonts_archive='cacheboot',
    archive_order=('cacheboot', 'cache', 'boot', 'renderboot', 'cacherender', 'nocacherender', 'nocache',
                   'cacheoverlay', 'cachemovie', 'cacheaudio', 'audioboot', 'audioboot2', 'data0', 'gamedata'),
    leagues={'nhl': (0, 0, 31), 'ahl': (1, 32, 61), 'shl': (2, 62, 75), 'liiga': (3, 76, 90), 'del': (4, 91, 104),
             'extraliga': (5, 105, 118), 'nla': (6, 119, 130), 'norway': (7, 131, 132), 'national': (8, 133, 153),
             'ohl': (9, 154, 173), 'qmjhl': (10, 174, 191), 'whl': (11, 192, 213), 'prospects': (12, 214, 215),
             'winterclassic': (14, 216, 219), 'eashl': (15, 220, 221), 'custom': (13, 222, 251)},
    allstar=(30, 31), custom=tuple(range(222, 252)), eashl=(220, 221),
    arena_template=181,
    tappara_tps=(88, 89),
    free_art=(100, 101, 102, 103),      # 98 — Vaasan Sport, 99 — KooKoo
    audioid2_none=4095,
    # 4 дивизиона: 3 Pacific, 4 Central (Запад), 5 Atlantic, 6 Metropolitan (Восток)
    nhl_divisions={3: 1, 4: 1, 5: 2, 6: 2},
    skater_prefix='c_', goalie_prefix='c_', skater_style='playerstyle', goalie_style='playerstyle',
    artid_bits=16, generic_heads=(60000, 60210),
    new_team_spotlight=(46, 47),        # у Legacy есть texlib_0…45
)

PROFILES = {'nhl13': NHL13, 'legacy': LEGACY}


def default_name():
    name = (os.environ.get('NHL_GAME') or 'nhl13').strip().lower()
    if name not in PROFILES:
        raise SystemExit(f'NHL_GAME={name!r}: такой игры нет (есть {", ".join(GAMES)})')
    return name


def get(name=None):
    return PROFILES[(name or default_name()).lower()]


def add_argument(ap, dest='game'):
    """Опция --game у argparse; по умолчанию — NHL_GAME или nhl13."""
    ap.add_argument('--' + dest.replace('_', '-'), dest=dest, choices=GAMES, default=default_name(),
                    help='игра: nhl13 (по умолчанию) или legacy (NHL Legacy Edition); можно NHL_GAME=legacy')
    return ap


# --- какой игры файл --------------------------------------------------------------------------
LEGACY_ONLY_TABLES = {b'byED'}          # nhlfutureschedule — только у Legacy
NHL13_ONLY_TABLES = {b'eEiE'}           # fcc_playercards — только у NHL 13 (и NHL 12)


def _table_ids(db):
    if db[:2] != b'DB':
        return set()
    E = '>' if db[4] == 1 else '<'
    n = struct.unpack(E + 'I', db[0x10:0x14])[0]
    return {bytes(db[0x18 + 8 * i:0x1C + 8 * i]) for i in range(n)}


def detect(data):
    """'legacy', 'nhl13' или None — по таблицам базы (nhlng.db) или обёртке сейва (ZlibV4 — Legacy).
    Сейв без особых таблиц — по обёртке: база, сжатая zlib с 0x30, — Legacy; открытая с 0x2C — по
    версии @0x14 (NHL 13: составы 0, франшиза 3; Legacy: 4 и 5, открыто у Legacy лежит только PROFILE)."""
    data = bytes(data[:0x400000]) if len(data) > 0x400000 else bytes(data)
    if data[:2] != b'DB':
        if len(data) > 0x32 and data[0x30] == 0x78 and data[0x2C:0x2E] != b'DB':
            return 'legacy'
        if len(data) > 0x30 and data[0x2C:0x2E] == b'DB':
            version = struct.unpack('>I', data[0x14:0x18])[0]
            ids = _table_ids(data[0x2C:])
            if ids & LEGACY_ONLY_TABLES:
                return 'legacy'
            if ids & NHL13_ONLY_TABLES:
                return 'nhl13'
            if version in (4, 5):
                return 'legacy'
            if version in (0, 1, 2, 3):
                return 'nhl13'
        return None
    ids = _table_ids(data)
    if ids & LEGACY_ONLY_TABLES:
        return 'legacy'
    if ids & NHL13_ONLY_TABLES:
        return 'nhl13'
    return None


def check_db(profile, data, what='база'):
    """Остановка, если база или сейв — заведомо другой игры, чем профиль."""
    got = detect(data)
    if got and got != profile.name:
        raise SystemExit(f'{what}: это {PROFILES[got].title}, а профиль — {profile.title} '
                         f'(--game {got} или NHL_GAME={got})')
    return got


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    add_argument(ap)
    ap.add_argument('--detect', nargs='+', metavar='FILE', help='какой игры база или сейв')
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding='utf-8')
    if a.detect:
        for f in a.detect:
            with open(f, 'rb') as fh:
                print(f'{detect(fh.read(0x400000)) or "?"}\t{f}')
        return
    print(get(a.game).describe())


if __name__ == '__main__':
    main()
