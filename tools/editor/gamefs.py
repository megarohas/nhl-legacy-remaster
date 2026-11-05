"""Файлы игры для редактора: что игра возьмёт для пути cache: и откуда — content\\my, части content, архивы EA.

Порядок как в exe (docs/legacy-port.md, «Папка content»): content\\my → части по content\\order.txt (остальные — по
алфавиту) → архивы диска (game_data_root, *.big; только чтение). Пишет редактор только в content\\my: файл там главнее
всего, наш контент и диск не трогаются; «Вернуть как было» убирает файл из my (в копии cache\\editor\\backup).
"""
import os
import re
import shutil
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

import legacy_paths  # noqa: E402
import legacy_saves  # noqa: E402

GAME_EXE = 'nhllegacy.exe'


def norm(rel):
    return rel.replace('\\', '/').strip('/')


class Source:
    MY, PART, EA = 'my', 'part', 'ea'


class EaArchives:
    """Оглавления всех .big диска: {путь в нижнем регистре: (архив, Member)}. Чтение — с разжатием chunk*/RefPack."""

    def __init__(self, root):
        self.root = root
        self.index = {}
        self.names = {}            # нижний регистр → как в архиве
        self.ready = threading.Event()
        self.error = None
        self._cache = {}
        self._lock = threading.Lock()

    def load(self):
        try:
            import big
            if self.root and os.path.isdir(self.root):
                arcs = []
                for d, _, fs in os.walk(self.root):
                    for f in fs:
                        if f.lower().endswith('.big'):
                            arcs.append(os.path.join(d, f))
                # patch/update — последними (поверх), остальные по имени
                arcs.sort(key=lambda p: ('patch' in os.path.basename(p).lower(), p.lower()))
                for a in arcs:
                    try:
                        ms = big.members(a)
                    except Exception:                       # noqa: BLE001  (не BigEB — пропуск)
                        continue
                    for path, m in ms.items():
                        k = norm(path).lower()
                        self.index[k] = (a, m)
                        self.names[k] = norm(path)
        except Exception as e:                              # noqa: BLE001
            self.error = str(e)
        finally:
            self.ready.set()

    def has(self, rel):
        self.ready.wait()
        return norm(rel).lower() in self.index

    def read(self, rel):
        self.ready.wait()
        k = norm(rel).lower()
        hit = self.index.get(k)
        if hit is None:
            return None
        with self._lock:
            if k in self._cache:
                return self._cache[k]
        import big
        arc, m = hit
        with open(arc, 'rb') as f:
            data = big.read_member(f, m)
        if data[:8] in (b'chunklzx', b'chunkzip'):
            import unchunk
            data = unchunk.unchunk(data)
        with self._lock:
            if len(self._cache) > 24:
                self._cache.pop(next(iter(self._cache)))
            self._cache[k] = data
        return data

    def archive_of(self, rel):
        hit = self.index.get(norm(rel).lower())
        return os.path.basename(hit[0]) if hit else None

    def list(self, prefix):
        """Пути (как в архиве) под папкой prefix."""
        self.ready.wait()
        p = norm(prefix).lower().rstrip('/') + '/'
        return [self.names[k] for k in self.index if k.startswith(p)]


class GameFS:
    def __init__(self, install):
        self.install = os.path.abspath(install)
        self.inst = legacy_paths.Install(self.install)
        self.content = self.inst.content if self.inst.new else None
        self.my = os.path.join(self.content, legacy_paths.MY) if self.content else None
        toml = os.path.join(self.install, 'nhllegacy.toml')
        gdr = legacy_paths._toml_value(toml, 'game_data_root')
        if not gdr:
            gdr = os.path.join(self.install, 'game')
        elif not os.path.isabs(gdr):
            gdr = os.path.join(self.install, gdr)
        self.game_root = os.path.normpath(gdr)
        self.ea = EaArchives(self.game_root)
        threading.Thread(target=self.ea.load, daemon=True).start()
        self.saves = legacy_saves.Saves.of_install(self.install)
        self.cache_root = os.path.join(self.install, 'cache')
        self.work = os.path.join(self.cache_root, 'editor')
        self.backup_root = os.path.join(self.work, 'backup')
        self._parts = None
        self._listing = {}

    # ---------------------------------------------------------------- раскладка
    def ok(self):
        return bool(self.content) and os.path.isdir(self.content)

    def parts(self):
        if self._parts is None:
            self._parts = legacy_paths.order(self.content) if self.ok() else []
        return self._parts

    def layers(self):
        """[(имя слоя, папка)] сверху вниз: my, затем части."""
        if not self.ok():
            return []
        return [(legacy_paths.MY, self.my)] + [(p, os.path.join(self.content, p)) for p in self.parts()]

    # ---------------------------------------------------------------- поиск
    def find(self, rel):
        """(источник, имя слоя или архива, путь на диске или None) — что игра возьмёт для rel; None — нигде нет."""
        r = norm(rel)
        for name, root in self.layers():
            p = os.path.join(root, *r.split('/'))
            if os.path.isfile(p):
                return (Source.MY if name == legacy_paths.MY else Source.PART, name, p)
        if self.ea.has(r):
            return (Source.EA, self.ea.archive_of(r), None)
        return None

    def sources(self, rel):
        """Все места, где лежит rel (сверху вниз) — для подсказки «откуда взят»."""
        r = norm(rel)
        out = []
        for name, root in self.layers():
            p = os.path.join(root, *r.split('/'))
            if os.path.isfile(p):
                out.append((name, p))
        if self.ea.has(r):
            out.append(('ea:' + (self.ea.archive_of(r) or ''), None))
        return out

    def read(self, rel, below_my=False):
        """Байты файла, который возьмёт игра (below_my — без content\\my: «как было»). None — нет."""
        r = norm(rel)
        for name, root in self.layers():
            if below_my and name == legacy_paths.MY:
                continue
            p = os.path.join(root, *r.split('/'))
            if os.path.isfile(p):
                data = open(p, 'rb').read()
                if data[:8] in (b'chunklzx', b'chunkzip'):
                    import unchunk
                    data = unchunk.unchunk(data)
                return data
        return self.ea.read(r)

    def exists(self, rel):
        return self.find(rel) is not None

    def in_my(self, rel):
        return bool(self.my) and os.path.isfile(os.path.join(self.my, *norm(rel).split('/')))

    def list_dir(self, folder, pattern=None):
        """Имена путей игры под folder из всех слоёв и архивов (без повторов, регистр — первого найденного)."""
        key = (norm(folder).lower(), pattern)
        rx = re.compile(pattern, re.I) if pattern else None
        seen = {}
        f = norm(folder)
        for _, root in self.layers():
            d = os.path.join(root, *f.split('/'))
            if not os.path.isdir(d):
                continue
            for dp, _, fs in os.walk(d):
                for x in fs:
                    rel = norm(os.path.relpath(os.path.join(dp, x), root))
                    k = rel.lower()
                    if k not in seen and (rx is None or rx.search(rel)):
                        seen[k] = rel
        for rel in self.ea.list(f):
            k = rel.lower()
            if k not in seen and (rx is None or rx.search(rel)):
                seen[k] = rel
        self._listing[key] = seen
        return sorted(seen.values(), key=str.lower)

    # ---------------------------------------------------------------- запись
    def my_path(self, rel):
        return os.path.join(self.my, *norm(rel).split('/'))

    def backup_dir(self):
        d = os.path.join(self.backup_root, time.strftime('%Y%m%d-%H%M%S'))
        os.makedirs(d, exist_ok=True)
        return d

    def write_my(self, rel, data, backup=None):
        """Записать файл в content\\my (прежний файл my — копией в backup). → путь."""
        check_game_closed()
        if not self.ok():
            raise EditorError('content', 'Нет папки content рядом с игрой (нужна раскладка 0.17.0+)',
                              'No content folder next to the game (layout 0.17.0+ required)')
        p = self.my_path(rel)
        if os.path.isfile(p):
            b = backup or self.backup_dir()
            q = os.path.join(b, 'content', 'my', *norm(rel).split('/'))
            os.makedirs(os.path.dirname(q), exist_ok=True)
            shutil.copy2(p, q)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        tmp = p + '.editor-tmp'
        with open(tmp, 'wb') as f:
            f.write(data)
        os.replace(tmp, p)
        return p

    def revert(self, rel, backup=None):
        """Убрать файл из content\\my (переносится в backup). → True, если было что убрать."""
        check_game_closed()
        p = self.my_path(rel)
        if not os.path.isfile(p):
            return False
        b = backup or self.backup_dir()
        q = os.path.join(b, 'content', 'my', *norm(rel).split('/'))
        os.makedirs(os.path.dirname(q), exist_ok=True)
        shutil.move(p, q)
        # пустые папки my, оставшиеся от правки
        d = os.path.dirname(p)
        while os.path.normcase(d) != os.path.normcase(self.my) and os.path.isdir(d) and not os.listdir(d):
            os.rmdir(d)
            d = os.path.dirname(d)
        return True

    def my_files(self):
        out = []
        if self.my and os.path.isdir(self.my):
            for dp, _, fs in os.walk(self.my):
                for x in fs:
                    out.append(norm(os.path.relpath(os.path.join(dp, x), self.my)))
        return sorted(out, key=str.lower)


class EditorError(Exception):
    """Ошибка для пользователя: код и текст на двух языках."""

    def __init__(self, code, ru, en=None):
        super().__init__(ru)
        self.code, self.ru, self.en = code, ru, en or ru


def _process_path(k32, pid):
    from ctypes import wintypes
    import ctypes
    h = k32.OpenProcess(0x1000, False, pid)                 # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return None
    try:
        buf = ctypes.create_unicode_buffer(1024)
        n = wintypes.DWORD(len(buf))
        if k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(n)):
            return buf.value
        return None
    finally:
        k32.CloseHandle(h)


def game_running(install=None):
    """Запущен ли nhllegacy.exe (Toolhelp32 — без окна консоли). install — только игра из этой папки (копия игры в
    другой папке сейвы и content этой установки не трогает); путь процесса не узнать — считается, что это она."""
    if os.name != 'nt':
        return False
    import ctypes
    from ctypes import wintypes

    class PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [('dwSize', wintypes.DWORD), ('cntUsage', wintypes.DWORD), ('th32ProcessID', wintypes.DWORD),
                    ('th32DefaultHeapID', ctypes.c_void_p), ('th32ModuleID', wintypes.DWORD),
                    ('cntThreads', wintypes.DWORD), ('th32ParentProcessID', wintypes.DWORD),
                    ('pcPriClassBase', ctypes.c_long), ('dwFlags', wintypes.DWORD),
                    ('szExeFile', ctypes.c_wchar * 260)]
    k32 = ctypes.windll.kernel32
    k32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    k32.OpenProcess.restype = wintypes.HANDLE
    snap = k32.CreateToolhelp32Snapshot(2, 0)
    if snap in (None, wintypes.HANDLE(-1).value):
        return False
    try:
        e = PROCESSENTRY32W()
        e.dwSize = ctypes.sizeof(e)
        ok = k32.Process32FirstW(snap, ctypes.byref(e))
        while ok:
            if e.szExeFile.lower() == GAME_EXE:
                if install is None:
                    return True
                p = _process_path(k32, e.th32ProcessID)
                if p is None or os.path.normcase(os.path.dirname(os.path.abspath(p))) ==                         os.path.normcase(os.path.abspath(install)):
                    return True
            ok = k32.Process32NextW(snap, ctypes.byref(e))
    finally:
        k32.CloseHandle(snap)
    return False


INSTALL = None      # папка игры редактора (app.py): игра из другой папки запись не останавливает


def check_game_closed():
    if game_running(INSTALL):
        raise EditorError('game_running', 'Игра запущена: закройте NHL Legacy и повторите (пока она открыта, '
                          'редактор ничего не записывает)',
                          'The game is running: close NHL Legacy and try again (nothing is written while it is open)')
