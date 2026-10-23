"""Удаление в Корзину и чистка прежних копий сборки: оставлять последние KEEP, остальное — в Корзину.

Правило репозитория (CLAUDE.md): удалять только в Корзину, рекурсивно — только после проверки, что внутри нет ссылок
(symlink/junction). Сборка (legacy_data/nhl24.py build, kitport build --stages pack) откладывает прежний результат
(_stale/out-nhl24-<время>, pack-edge-vN) и теперь сама чистит их через prune().

Корзина на том же диске место не освобождает, пока её не очистят, а при переполнении Windows молча выбрасывает самое
старое из неё (15.10.2026 так пропало старое содержимое Корзины S:). Поэтому prune() не удаляет ничего, если Корзина
вместе с удаляемым заняла бы больше BIN_LIMIT квоты диска, и просит очистить Корзину.

    python tools/recycle.py status S:                     # Корзина диска: занято / квота
    python tools/recycle.py prune DIR REGEX [--keep 3]    # в DIR: группы по REGEX (группа 1 — имя, 2 — порядок)
"""
import argparse
import os
import re
import subprocess
import sys

KEEP = 3          # решение пользователя 23.10.2026: прежних сборок хранить 3 (до этого копились — 102 накладки и
                  # 40 пакетов форм, 45 ГБ)
BIN_LIMIT = 0.8   # доля квоты Корзины: больше — не удалять (иначе Windows выбросит старое содержимое Корзины)


def links_in(path):
    """Первая ссылка (symlink/junction) внутри path или None."""
    isj = getattr(os.path, "isjunction", lambda p: False)
    if os.path.islink(path) or isj(path):
        return path
    for root, dirs, names in os.walk(path):
        for n in dirs + names:
            p = os.path.join(root, n)
            if os.path.islink(p) or isj(p):
                return p
    return None


def size_of(path):
    if os.path.isfile(path):
        return os.path.getsize(path)
    total = 0
    for root, _, names in os.walk(path):
        for n in names:
            try:
                total += os.path.getsize(os.path.join(root, n))
            except OSError:
                pass
    return total


def bin_state(drive):
    """(занято байт, квота байт | None) Корзины диска drive ("S:") для текущего пользователя."""
    import ctypes
    import winreg
    used = size_of(os.path.join(drive + "\\", "$RECYCLE.BIN"))    # обходом: SHQueryRecycleBinW отстаёт (23.10: −4 ГБ)
    buf = ctypes.create_unicode_buffer(64)
    if not ctypes.windll.kernel32.GetVolumeNameForVolumeMountPointW(drive + "\\", buf, 64):
        return used, None
    guid = re.search(r"\{[0-9a-fA-F-]+\}", buf.value).group(0)
    try:
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                           rf"Software\Microsoft\Windows\CurrentVersion\Explorer\BitBucket\Volume\{guid}")
        cap, _ = winreg.QueryValueEx(k, "MaxCapacity")          # МБ
    except OSError:
        return used, None
    try:
        nuke = winreg.QueryValueEx(k, "NukeOnDelete")[0]       # 1 — удаление мимо Корзины
    except OSError:
        nuke = 0
    return used, (0 if nuke else cap * 1024 * 1024)


def to_recycle_bin(path):
    """path (папка или файл) → Корзина. Ссылки внутри или не ушло — SystemExit."""
    link = links_in(path)
    if link:
        raise SystemExit(f"{path}: внутри ссылка {link} — в Корзину не отправляю, разберитесь вручную")
    kind = "Directory" if os.path.isdir(path) else "File"
    ps = ("Add-Type -AssemblyName Microsoft.VisualBasic; [Microsoft.VisualBasic.FileIO.FileSystem]::Delete"
          f"{kind}($env:RECYCLE_PATH, 'OnlyErrorDialogs', 'SendToRecycleBin')")
    subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps], check=True,
                   env={**os.environ, "RECYCLE_PATH": os.path.abspath(path)}, capture_output=True)
    if os.path.exists(path):
        raise SystemExit(f"{path}: не ушло в Корзину")


def prune(folder, pattern, keep=KEEP, say=print):
    """В folder — имена по pattern (группа 1 — имя группы, группа 2 — порядок: число или строка времени); в каждой
    группе оставить keep последних, остальное — в Корзину. Корзина почти полна — ничего не удаляет. -> [удалённое]."""
    if not os.path.isdir(folder):
        return []
    rx = re.compile(pattern)
    groups = {}
    for f in os.listdir(folder):
        m = rx.fullmatch(f)
        if m:
            order = m.group(2)
            groups.setdefault(m.group(1), []).append((int(order) if order.isdigit() else order, f))
    old = [os.path.join(folder, f) for items in groups.values() for _, f in sorted(items)[:-keep] if keep > 0]
    if not old:
        return []
    need = sum(size_of(p) for p in old)
    used, cap = bin_state(os.path.splitdrive(os.path.abspath(folder))[0])
    if cap == 0:
        say(f"на диске удаление мимо Корзины (NukeOnDelete): прежние копии ({len(old)}) не удаляю")
        return []
    if cap is not None and used + need > BIN_LIMIT * cap:
        say(f"Корзина {used / 2**30:.1f} ГБ из {cap / 2**30:.0f}: прежние копии ({len(old)}, {need / 2**30:.1f} ГБ) "
            f"не удаляю — очистите Корзину")
        return []
    for p in old:
        to_recycle_bin(p)
    say(f"прежние копии в Корзину: {len(old)} ({need / 2**30:.1f} ГБ), оставлено по {keep} последних")
    return old


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("status")
    s.add_argument("drive", help="диск: S:")
    s = sub.add_parser("prune")
    s.add_argument("folder")
    s.add_argument("regex", help=r"полное имя; группа 1 — имя группы, 2 — порядок (pack-edge)-v(\d+))")
    s.add_argument("--keep", type=int, default=KEEP)
    a = ap.parse_args()
    if a.cmd == "status":
        used, cap = bin_state(a.drive)
        print(f"Корзина {a.drive}: {used / 2**30:.2f} ГБ" + (f" из {cap / 2**30:.0f} ГБ квоты" if cap else
                                                             " (квота не найдена или удаление без Корзины)"))
        return 0
    prune(a.folder, a.regex, a.keep)
    return 0


if __name__ == "__main__":
    sys.exit(main())
