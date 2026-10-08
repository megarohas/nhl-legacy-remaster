"""stackpeek.py — чем занят поток запущенного nhl13.exe: пассивный просмотр его стека.

Игру не останавливает и не меняет: только ReadProcessMemory (как «Диспетчер задач» и
Process Explorer). Для потока берётся TEB -> границы стека, стек читается целиком несколько раз
подряд, в нём ищутся адреса возврата в nhl13.exe (за ними должна стоять инструкция call), и каждый
адрес сопоставляется функции: по таблице .pdata exe — начало функции хоста, по таблице
PPCFuncMappings (адрес гостя -> функция хоста) — адрес функции гостя sub_XXXXXXXX. Адреса в
rexruntime.dll / rexgpu-xenos.dll подписываются ближайшим экспортом.

Ограничение: без контекста потока (для него поток пришлось бы приостановить) неизвестна вершина
стека, поэтому ниже живых кадров попадаются «старые» адреса от прошлых вызовов. Кадры, которые
повторяются во всех снимках, — настоящая цепочка вызовов; меняющиеся внизу — работа или мусор.

  python tools/stackpeek.py --thread "XThread84D8" [--snaps 12] [--interval 0.25]
  python tools/stackpeek.py --tid 34008
"""

import argparse
import bisect
import collections
import ctypes
import os
import struct
import sys
import time
from ctypes import wintypes

k32 = ctypes.WinDLL("kernel32", use_last_error=True)
ntdll = ctypes.WinDLL("ntdll")
psapi = ctypes.WinDLL("psapi", use_last_error=True)

PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_VM_READ = 0x0010
THREAD_QUERY_INFORMATION = 0x0040
THREAD_QUERY_LIMITED_INFORMATION = 0x0800
TH32CS_SNAPTHREAD = 0x00000004
TH32CS_SNAPPROCESS = 0x00000002

k32.OpenProcess.restype = wintypes.HANDLE
k32.OpenThread.restype = wintypes.HANDLE
k32.ReadProcessMemory.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t,
                                  ctypes.POINTER(ctypes.c_size_t)]
k32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
k32.GetThreadDescription.argtypes = [wintypes.HANDLE, ctypes.POINTER(ctypes.c_wchar_p)]


class THREADENTRY32(ctypes.Structure):
    _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ThreadID", wintypes.DWORD),
                ("th32OwnerProcessID", wintypes.DWORD), ("tpBasePri", ctypes.c_long),
                ("tpDeltaPri", ctypes.c_long), ("dwFlags", wintypes.DWORD)]


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD),
                ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", wintypes.DWORD),
                ("cntThreads", wintypes.DWORD), ("th32ParentProcessID", wintypes.DWORD),
                ("pcPriClassBase", ctypes.c_long), ("dwFlags", wintypes.DWORD),
                ("szExeFile", ctypes.c_wchar * 260)]


class THREAD_BASIC_INFORMATION(ctypes.Structure):
    _fields_ = [("ExitStatus", ctypes.c_long), ("TebBaseAddress", ctypes.c_void_p),
                ("UniqueProcess", ctypes.c_void_p), ("UniqueThread", ctypes.c_void_p),
                ("AffinityMask", ctypes.c_size_t), ("Priority", ctypes.c_long), ("BasePriority", ctypes.c_long)]


class MODULEINFO(ctypes.Structure):
    _fields_ = [("lpBaseOfDll", ctypes.c_void_p), ("SizeOfImage", wintypes.DWORD), ("EntryPoint", ctypes.c_void_p)]


def find_pid(name):
    snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    e = PROCESSENTRY32W()
    e.dwSize = ctypes.sizeof(e)
    pid = None
    ok = k32.Process32FirstW(snap, ctypes.byref(e))
    while ok:
        if e.szExeFile.lower() == name.lower():
            pid = e.th32ProcessID
            break
        ok = k32.Process32NextW(snap, ctypes.byref(e))
    k32.CloseHandle(snap)
    return pid


def thread_ids(pid):
    snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0)
    e = THREADENTRY32()
    e.dwSize = ctypes.sizeof(e)
    out = []
    ok = k32.Thread32First(snap, ctypes.byref(e))
    while ok:
        if e.th32OwnerProcessID == pid:
            out.append(e.th32ThreadID)
        ok = k32.Thread32Next(snap, ctypes.byref(e))
    k32.CloseHandle(snap)
    return out


def thread_name(tid):
    h = k32.OpenThread(THREAD_QUERY_LIMITED_INFORMATION, False, tid)
    if not h:
        return ""
    try:
        p = ctypes.c_wchar_p()
        if k32.GetThreadDescription(h, ctypes.byref(p)) >= 0 and p.value is not None:
            s = p.value
            k32.LocalFree(p)
            return s
        return ""
    finally:
        k32.CloseHandle(h)


def read(hp, addr, size):
    buf = ctypes.create_string_buffer(size)
    got = ctypes.c_size_t(0)
    if not k32.ReadProcessMemory(hp, ctypes.c_void_p(addr), buf, size, ctypes.byref(got)):
        return None
    return buf.raw[:got.value]


def modules(hp):
    arr = (ctypes.c_void_p * 1024)()
    needed = wintypes.DWORD()
    psapi.EnumProcessModulesEx.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD,
                                           ctypes.POINTER(wintypes.DWORD), wintypes.DWORD]
    psapi.EnumProcessModulesEx(hp, arr, ctypes.sizeof(arr), ctypes.byref(needed), 3)
    out = []
    for i in range(needed.value // ctypes.sizeof(ctypes.c_void_p)):
        hm = arr[i]
        name = ctypes.create_unicode_buffer(520)
        psapi.GetModuleFileNameExW.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.LPWSTR, wintypes.DWORD]
        psapi.GetModuleFileNameExW(hp, ctypes.c_void_p(hm), name, 520)
        mi = MODULEINFO()
        psapi.GetModuleInformation.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.POINTER(MODULEINFO),
                                               wintypes.DWORD]
        psapi.GetModuleInformation(hp, ctypes.c_void_p(hm), ctypes.byref(mi), ctypes.sizeof(mi))
        out.append((mi.lpBaseOfDll, mi.SizeOfImage, name.value))
    return out


class PE:
    """Минимальный разбор PE64 с диска: секции, .pdata, экспорты."""

    def __init__(self, path):
        self.path = path
        self.data = open(path, "rb").read()
        d = self.data
        pe = struct.unpack_from("<I", d, 0x3C)[0]
        nsec = struct.unpack_from("<H", d, pe + 6)[0]
        opt = pe + 24
        self.image_base = struct.unpack_from("<Q", d, opt + 24)[0]
        self.size_of_image = struct.unpack_from("<I", d, opt + 56)[0]
        ndirs = struct.unpack_from("<I", d, opt + 108)[0]
        self.dirs = [struct.unpack_from("<II", d, opt + 112 + 8 * i) for i in range(ndirs)]
        sec = opt + struct.unpack_from("<H", d, pe + 20)[0]
        self.sections = []
        for i in range(nsec):
            o = sec + 40 * i
            name = d[o:o + 8].rstrip(b"\0").decode("ascii", "replace")
            vsize, va, rawsize, rawptr = struct.unpack_from("<IIII", d, o + 8)
            chars = struct.unpack_from("<I", d, o + 36)[0]
            self.sections.append((name, va, vsize, rawptr, rawsize, chars))

    def rva2off(self, rva):
        for name, va, vsize, rawptr, rawsize, chars in self.sections:
            if va <= rva < va + max(vsize, rawsize):
                return rawptr + (rva - va)
        return None

    def is_code(self, rva):
        for name, va, vsize, rawptr, rawsize, chars in self.sections:
            if va <= rva < va + vsize:
                return bool(chars & 0x20000000)
        return False

    def pdata(self):
        rva, size = self.dirs[3]
        off = self.rva2off(rva)
        n = size // 12
        begins = []
        ends = []
        for i in range(n):
            b, e, u = struct.unpack_from("<III", self.data, off + 12 * i)
            begins.append(b)
            ends.append(e)
        order = sorted(range(n), key=lambda i: begins[i])
        return [begins[i] for i in order], [ends[i] for i in order]

    def exports(self):
        rva, size = self.dirs[0]
        if not rva:
            return [], []
        off = self.rva2off(rva)
        d = self.data
        nfuncs, nnames, afuncs, anames, aords = struct.unpack_from("<IIIII", d, off + 20)
        funcs = [struct.unpack_from("<I", d, self.rva2off(afuncs) + 4 * i)[0] for i in range(nfuncs)]
        out = []
        for i in range(nnames):
            nrva = struct.unpack_from("<I", d, self.rva2off(anames) + 4 * i)[0]
            ordi = struct.unpack_from("<H", d, self.rva2off(aords) + 2 * i)[0]
            no = self.rva2off(nrva)
            name = d[no:d.index(b"\0", no)].decode("ascii", "replace")
            out.append((funcs[ordi], name))
        out.sort()
        return [r for r, n in out], [n for r, n in out]

    def looks_like_call(self, rva):
        """Перед адресом возврата должна стоять инструкция call."""
        off = self.rva2off(rva)
        if off is None or off < 8:
            return False
        b = self.data[off - 8:off]
        if b[3] == 0xE8:  # call rel32
            return True
        if b[2] == 0xFF and b[3] in (0x15, 0x90, 0x91, 0x92, 0x93, 0x95, 0x96, 0x97):  # call [rip+d32]/[r+d32]
            return True
        if b[6] == 0xFF and 0xD0 <= b[7] <= 0xD7:  # call reg
            return True
        if b[5] == 0x41 and b[6] == 0xFF and 0xD0 <= b[7] <= 0xD7:  # call r8-r15
            return True
        if b[5] == 0xFF and 0x50 <= b[6] <= 0x57:  # call [reg+d8]
            return True
        if b[4] == 0x41 and b[5] == 0xFF and 0x50 <= b[6] <= 0x57:
            return True
        if b[1] == 0x41 and b[2] == 0xFF and 0x90 <= b[3] <= 0x97:
            return True
        return False


def func_mappings(pe, code_lo=0x82000000, code_hi=0x84000000):
    """PPCFuncMappings: {size_t guest; PPCFunc* host;} — ищем в данных exe."""
    d = pe.data
    first = struct.pack("<Q", 0x823F0000)
    pos = 0
    while True:
        i = d.find(first, pos)
        if i < 0:
            return {}
        if i % 8 == 0 and struct.unpack_from("<Q", d, i + 16)[0] == 0x823F0018:
            break
        pos = i + 1
    out = {}
    o = i
    while o + 16 <= len(d):
        g, h = struct.unpack_from("<QQ", d, o)
        if not (code_lo <= g < code_hi) or not (pe.image_base <= h < pe.image_base + pe.size_of_image):
            break
        out[h - pe.image_base] = g
        o += 16
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--process", default="nhl13.exe")
    ap.add_argument("--tid", type=int)
    ap.add_argument("--thread", help="подстрока имени потока, например XThread84D8")
    ap.add_argument("--snaps", type=int, default=12)
    ap.add_argument("--interval", type=float, default=0.25)
    ap.add_argument("--depth", type=int, default=40, help="сколько кадров от вершины снимка показывать")
    args = ap.parse_args()

    pid = find_pid(args.process)
    if not pid:
        sys.exit(f"{args.process} не запущен")
    tid = args.tid
    if not tid:
        for t in thread_ids(pid):
            if args.thread and args.thread.lower() in thread_name(t).lower():
                tid = t
                break
    if not tid:
        sys.exit("поток не найден")
    print(f"pid {pid}, tid {tid} «{thread_name(tid)}»")

    hp = k32.OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, pid)
    ht = k32.OpenThread(THREAD_QUERY_INFORMATION, False, tid)
    if not hp or not ht:
        sys.exit(f"нет доступа: {ctypes.get_last_error()}")
    tbi = THREAD_BASIC_INFORMATION()
    st = ntdll.NtQueryInformationThread(ht, 0, ctypes.byref(tbi), ctypes.sizeof(tbi), None)
    if st != 0:
        sys.exit(f"NtQueryInformationThread: {st:#x}")
    tib = read(hp, tbi.TebBaseAddress, 0x18)
    stack_base, stack_limit = struct.unpack_from("<QQ", tib, 8)
    print(f"TEB {tbi.TebBaseAddress:#x}, стек {stack_limit:#x}..{stack_base:#x} ({(stack_base - stack_limit) // 1024} КБ)")

    mods = modules(hp)
    pes = {}
    lookups = []
    for base, size, path in mods:
        low = os.path.basename(path).lower()
        if low in ("nhl13.exe", "rexruntime.dll", "rexgpu-xenos.dll"):
            pe = PE(path)
            entry = {"base": base, "size": size, "name": low, "pe": pe}
            if low == "nhl13.exe":
                entry["pdata"] = pe.pdata()
                entry["map"] = func_mappings(pe)
                print(f"nhl13.exe: .pdata {len(entry['pdata'][0])} функций, PPCFuncMappings {len(entry['map'])}")
            else:
                entry["exports"] = pe.exports()
                entry["pdata"] = pe.pdata()
            lookups.append(entry)

    def describe(addr):
        for m in lookups:
            if m["base"] <= addr < m["base"] + m["size"]:
                rva = addr - m["base"]
                pe = m["pe"]
                if not pe.is_code(rva) or not pe.looks_like_call(rva):
                    return None
                begins, ends = m["pdata"]
                i = bisect.bisect_right(begins, rva - 1) - 1
                fbeg = begins[i] if i >= 0 and begins[i] <= rva - 1 < ends[i] else None
                if m["name"] == "nhl13.exe":
                    if fbeg is not None and fbeg in m["map"]:
                        return f"sub_{m['map'][fbeg]:08X}+{rva - fbeg:#x}"
                    return f"nhl13.exe+{rva:#x}" + (f" (функция +{fbeg:#x})" if fbeg is not None else "")
                er, en = m["exports"]
                j = bisect.bisect_right(er, rva) - 1
                if j >= 0 and rva - er[j] < 0x4000:
                    return f"{m['name']}!{en[j]}+{rva - er[j]:#x}"
                return f"{m['name']}+{rva:#x}"
        return None

    snaps = []
    for s in range(args.snaps):
        data = read(hp, stack_limit, stack_base - stack_limit)
        if data is None:
            print("стек не читается")
            break
        frames = []
        for off in range(0, len(data) - 7, 8):
            v = struct.unpack_from("<Q", data, off)[0]
            if v < 0x10000:
                continue
            desc = describe(v)
            if desc:
                frames.append((stack_limit + off, desc))
        snaps.append(frames)
        time.sleep(args.interval)

    # Кадры от дна стека (самые внешние) — по адресу в стеке, сверху вниз
    print()
    print(f"Снимков: {len(snaps)}. Адреса возврата, которые есть во ВСЕХ снимках на том же месте стека (стабильная цепочка):")
    sets = [dict(f) for f in snaps]
    common = set(sets[0].items())
    for st_ in sets[1:]:
        common &= set(st_.items())
    for addr, desc in sorted(common, reverse=True):
        print(f"  {stack_base - addr:7d}  {desc}")
    print()
    print("Изменчивые адреса (место в стеке от дна -> сколько раз из снимков видели):")
    cnt = collections.Counter()
    for st_ in sets:
        for a, d in st_.items():
            if (a, d) not in common:
                cnt[(a, d)] += 1
    for (a, d), c in sorted(cnt.items(), key=lambda x: -x[0][0])[:args.depth]:
        print(f"  {stack_base - a:7d}  {c:2d}/{len(sets)}  {d}")
    print()
    print("Функции гостя, встреченные в изменчивой части (частота):")
    fc = collections.Counter()
    for st_ in sets:
        seen = set()
        for a, d in st_.items():
            if (a, d) in common:
                continue
            f = d.split("+")[0]
            if f not in seen:
                fc[f] += 1
                seen.add(f)
    for f, c in fc.most_common(25):
        print(f"  {c:2d}/{len(sets)}  {f}")


if __name__ == "__main__":
    main()
