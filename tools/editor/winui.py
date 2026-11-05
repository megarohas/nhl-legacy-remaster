"""Окна Windows для редактора без сторонних библиотек (ctypes): выбор папки и файла (IFileDialog, как у Проводника),
окно сообщения, поиск окна редактора (владелец диалогов — окно браузера с интерфейсом)."""
import ctypes
import threading
import os
import uuid
from ctypes import wintypes

WINDOW_MARK = 'NHL Legacy Remaster Editor'
CLSID_FileOpenDialog = '{DC1C5A9C-E88A-4dde-A5A1-60F82A20AEF7}'
CLSID_FileSaveDialog = '{C0B4E2F3-BA21-4773-8DBA-335EC946EB8B}'
IID_IFileOpenDialog = '{d57c7288-d4ad-4768-be02-9d969532d960}'
IID_IFileSaveDialog = '{84bccd23-5fde-4cdb-aea4-af64b83d78ab}'
IID_IShellItem = '{43826d1e-e718-42ee-bc55-a1e261c37bfe}'
FOS_OVERWRITEPROMPT, FOS_PICKFOLDERS, FOS_FORCEFILESYSTEM, FOS_FILEMUSTEXIST = 0x2, 0x20, 0x40, 0x1000
SIGDN_FILESYSPATH = 0x80058000 - (1 << 32)
ERROR_CANCELLED = 0x800704C7 - (1 << 32)


class GUID(ctypes.Structure):
    _fields_ = [('Data1', ctypes.c_ulong), ('Data2', ctypes.c_ushort), ('Data3', ctypes.c_ushort),
                ('Data4', ctypes.c_ubyte * 8)]


def _guid(s):
    u = uuid.UUID(s)
    g = GUID()
    g.Data1, g.Data2, g.Data3 = u.fields[0], u.fields[1], u.fields[2]
    for i, b in enumerate(u.bytes[8:]):
        g.Data4[i] = b
    return g


class FILTERSPEC(ctypes.Structure):
    _fields_ = [('pszName', wintypes.LPCWSTR), ('pszSpec', wintypes.LPCWSTR)]


def _method(ptr, index, *argtypes):
    vt = ctypes.cast(ctypes.cast(ptr, ctypes.POINTER(ctypes.c_void_p))[0], ctypes.POINTER(ctypes.c_void_p))
    proto = ctypes.WINFUNCTYPE(ctypes.HRESULT, ctypes.c_void_p, *argtypes)
    fn = proto(vt[index])
    return lambda *a: fn(ptr, *a)


def _release(ptr):
    if ptr:
        vt = ctypes.cast(ctypes.cast(ptr, ctypes.POINTER(ctypes.c_void_p))[0], ctypes.POINTER(ctypes.c_void_p))
        ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(vt[2])(ptr)


def find_window():
    """Окно редактора (заголовок со знаком WINDOW_MARK) или None."""
    if os.name != 'nt':
        return None
    user32 = ctypes.windll.user32
    found = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(hwnd, _):
        if user32.IsWindowVisible(hwnd):
            n = user32.GetWindowTextLengthW(hwnd)
            if n:
                buf = ctypes.create_unicode_buffer(n + 1)
                user32.GetWindowTextW(hwnd, buf, n + 1)
                if WINDOW_MARK in buf.value:
                    found.append(hwnd)
                    return False
        return True
    user32.EnumWindows(cb, 0)
    return found[0] if found else None


def _dialog(save=False, folder=False, title='', start=None, filters=None, name=None, ext=None):
    ole32 = ctypes.windll.ole32
    ole32.CoInitializeEx(None, 2)
    dlg = ctypes.c_void_p()
    try:
        clsid = _guid(CLSID_FileSaveDialog if save else CLSID_FileOpenDialog)
        iid = _guid(IID_IFileSaveDialog if save else IID_IFileOpenDialog)
        hr = ole32.CoCreateInstance(ctypes.byref(clsid), None, 1, ctypes.byref(iid), ctypes.byref(dlg))
        if hr != 0:
            raise OSError(f'CoCreateInstance 0x{hr & 0xFFFFFFFF:08X}')
        p = dlg.value
        opts = ctypes.c_uint()
        _method(p, 10, ctypes.POINTER(ctypes.c_uint))(ctypes.byref(opts))
        o = opts.value | FOS_FORCEFILESYSTEM
        if folder:
            o |= FOS_PICKFOLDERS
        elif save:
            o |= FOS_OVERWRITEPROMPT
        else:
            o |= FOS_FILEMUSTEXIST
        _method(p, 9, ctypes.c_uint)(o)
        if title:
            _method(p, 17, wintypes.LPCWSTR)(title)
        if filters and not folder:
            arr = (FILTERSPEC * len(filters))(*[FILTERSPEC(n, s) for n, s in filters])
            _method(p, 4, ctypes.c_uint, ctypes.c_void_p)(len(filters), ctypes.cast(arr, ctypes.c_void_p))
        if name and save:
            _method(p, 15, wintypes.LPCWSTR)(name)
        if ext and save:
            _method(p, 22, wintypes.LPCWSTR)(ext)
        if start and os.path.isdir(start):
            item = ctypes.c_void_p()
            shell32 = ctypes.windll.shell32
            iid_si = _guid(IID_IShellItem)
            if shell32.SHCreateItemFromParsingName(start, None, ctypes.byref(iid_si), ctypes.byref(item)) == 0:
                _method(p, 12, ctypes.c_void_p)(item)
                _release(item.value)
        try:
            _method(p, 3, wintypes.HWND)(find_window())
        except OSError as e:
            if getattr(e, 'winerror', None) == ERROR_CANCELLED or 'cancel' in str(e).lower() or '0x800704C7' in str(e):
                return None
            if e.args and isinstance(e.args[0], int) and (e.args[0] & 0xFFFFFFFF) == 0x800704C7:
                return None
            return None
        res = ctypes.c_void_p()
        _method(p, 20, ctypes.POINTER(ctypes.c_void_p))(ctypes.byref(res))
        path = ctypes.c_wchar_p()
        _method(res.value, 5, ctypes.c_int, ctypes.POINTER(ctypes.c_wchar_p))(SIGDN_FILESYSPATH, ctypes.byref(path))
        out = path.value
        ole32.CoTaskMemFree(path)
        _release(res.value)
        return out
    finally:
        _release(dlg.value)
        ole32.CoUninitialize()


# Приложение (Electron, tools/editor/electron/main.js): диалоги показывает окно приложения. Сервер пишет в stdout строку
# «@@NHL {"id", "dialog": {…}}», Electron открывает свой dialog.showOpenDialog/showSaveDialog у своего окна и отвечает
# в stdin строкой «{"id", "path"}» (path — null, если отменили). Без приложения — IFileDialog выше.
BRIDGE = None                 # (stdin, stdout) сервера в режиме приложения — ставит app.py
_bridge_lock = threading.Lock()
_bridge_seq = [0]


def _ask_app(req):
    import json
    stdin, stdout = BRIDGE
    with _bridge_lock:
        _bridge_seq[0] += 1
        rid = _bridge_seq[0]
        # строка — чистый ASCII (\uXXXX): у собранного exe кодировка канала — системная, не UTF-8
        stdout.write('@@NHL ' + json.dumps(dict(id=rid, dialog=req)) + '\n')
        stdout.flush()
        while True:
            line = stdin.readline()
            if not line:
                return None
            try:
                ans = json.loads(line)
            except ValueError:
                continue
            if ans.get('id') == rid:
                return ans.get('path')


def _filters(filters):
    """[('PNG', '*.png;*.jpg')] → [{name, extensions: ['png', 'jpg']}] (Electron)."""
    out = []
    for name, spec in filters or []:
        exts = [x.strip().lstrip('*.') or '*' for x in spec.split(';')]
        out.append(dict(name=name, extensions=['*' if e in ('*', '') else e for e in exts]))
    return out


def pick_folder(title='', start=None):
    if BRIDGE:
        return _ask_app(dict(kind='folder', title=title, start=start))
    return _dialog(folder=True, title=title, start=start)


def pick_file(title='', start=None, filters=None):
    if BRIDGE:
        return _ask_app(dict(kind='open', title=title, start=start, filters=_filters(filters)))
    return _dialog(title=title, start=start, filters=filters)


def save_file(title='', start=None, name=None, filters=None, ext=None):
    if BRIDGE:
        return _ask_app(dict(kind='save', title=title, start=start, name=name, filters=_filters(filters)))
    return _dialog(save=True, title=title, start=start, filters=filters, name=name, ext=ext)


def message(text, title='NHL Legacy Remaster', error=False):
    if BRIDGE:
        _ask_app(dict(kind='message', title=title, text=text, error=error))
        return
    if os.name == 'nt':
        ctypes.windll.user32.MessageBoxW(find_window(), text, title, 0x10 if error else 0x40)
