"""Вшить иконку (.ico) в готовый exe Windows как ресурс id 1 — для nhllegacy.exe после сборки и в папке для друзей.

    python tools/set_exe_icon.py EXE [ICO] [--no-backup]   # ICO по умолчанию — nhl-legacy-port/launcher/icon/nhllegacy.ico

Ресурсы пишет сама Windows (BeginUpdateResource / UpdateResource / EndUpdateResource): RT_ICON на каждый размер и
RT_GROUP_ICON 1. Код и отладочная запись exe (связь с pdb) не меняются, меняется только раздел ресурсов. Перед
записью — копия EXE.bak-icon рядом (если её ещё нет); после — проверка, что Windows видит иконку (LoadImage из exe
как из файла данных). Иконку рисует tools/make_icon.py.
"""
import ctypes
import os
import shutil
import struct
import sys
from ctypes import wintypes

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_ICO = os.path.join(ROOT, 'nhl-legacy-port', 'launcher', 'icon', 'nhllegacy.ico')
RT_ICON, RT_GROUP_ICON = 3, 14
LANG = 0  # LANG_NEUTRAL

k32 = ctypes.WinDLL('kernel32', use_last_error=True)
k32.BeginUpdateResourceW.argtypes = [wintypes.LPCWSTR, wintypes.BOOL]
k32.BeginUpdateResourceW.restype = wintypes.HANDLE
k32.UpdateResourceW.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.c_void_p, wintypes.WORD, ctypes.c_void_p,
                                wintypes.DWORD]
k32.UpdateResourceW.restype = wintypes.BOOL
k32.EndUpdateResourceW.argtypes = [wintypes.HANDLE, wintypes.BOOL]
k32.EndUpdateResourceW.restype = wintypes.BOOL


def read_ico(path):
    d = open(path, 'rb').read()
    _, typ, n = struct.unpack_from('<HHH', d, 0)
    if typ != 1:
        raise SystemExit(f'не ICO: {path}')
    out = []
    for i in range(n):
        w, h, cc, res, planes, bpp, size, off = struct.unpack_from('<BBBBHHII', d, 6 + 16 * i)
        out.append((w, h, cc, planes, bpp, d[off:off + size]))
    return out


def set_icon(exe, ico, backup=True):
    imgs = read_ico(ico)
    bak = exe + '.bak-icon'
    if backup and not os.path.exists(bak):
        shutil.copy2(exe, bak)
    h = k32.BeginUpdateResourceW(exe, False)
    if not h:
        raise SystemExit(f'BeginUpdateResource: {ctypes.get_last_error()}')
    ok = True
    grp = struct.pack('<HHH', 0, 1, len(imgs))
    for i, (w, hgt, cc, planes, bpp, data) in enumerate(imgs, start=1):
        buf = ctypes.create_string_buffer(data, len(data))
        ok &= bool(k32.UpdateResourceW(h, ctypes.c_void_p(RT_ICON), ctypes.c_void_p(i), LANG, buf, len(data)))
        grp += struct.pack('<BBBBHHIH', w, hgt, cc, 0, planes or 1, bpp or 32, len(data), i)
    gbuf = ctypes.create_string_buffer(grp, len(grp))
    ok &= bool(k32.UpdateResourceW(h, ctypes.c_void_p(RT_GROUP_ICON), ctypes.c_void_p(1), LANG, gbuf, len(grp)))
    if not ok:
        k32.EndUpdateResourceW(h, True)
        raise SystemExit(f'UpdateResource: {ctypes.get_last_error()}')
    if not k32.EndUpdateResourceW(h, False):
        raise SystemExit(f'EndUpdateResource: {ctypes.get_last_error()}')
    # проверка: иконка грузится из exe как из файла данных
    LOAD_LIBRARY_AS_DATAFILE = 0x2
    k32.LoadLibraryExW.argtypes = [wintypes.LPCWSTR, wintypes.HANDLE, wintypes.DWORD]
    k32.LoadLibraryExW.restype = wintypes.HMODULE
    k32.FreeLibrary.argtypes = [wintypes.HMODULE]
    mod = k32.LoadLibraryExW(exe, None, LOAD_LIBRARY_AS_DATAFILE)
    u32 = ctypes.WinDLL('user32', use_last_error=True)
    u32.LoadImageW.argtypes = [wintypes.HINSTANCE, ctypes.c_void_p, wintypes.UINT, ctypes.c_int, ctypes.c_int,
                               wintypes.UINT]
    u32.LoadImageW.restype = wintypes.HANDLE
    hic = u32.LoadImageW(mod, ctypes.c_void_p(1), 1, 48, 48, 0)
    k32.FreeLibrary(mod)
    print(f'{exe}: иконка ({len(imgs)} размеров) вшита; проверка LoadImage: {"ok" if hic else "НЕТ"}'
          + (f'; копия — {bak}' if backup else ''))
    return bool(hic)


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    args = [a for a in sys.argv[1:] if a != '--no-backup']
    if not args:
        sys.exit(__doc__)
    sys.exit(0 if set_icon(os.path.abspath(args[0]), os.path.abspath(args[1]) if len(args) > 1 else DEFAULT_ICO,
                           backup='--no-backup' not in sys.argv) else 1)
