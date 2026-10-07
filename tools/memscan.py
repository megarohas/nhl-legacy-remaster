"""Поиск в гостевой памяти работающего порта (nhl13.exe) — для разведки.

    python memscan.py base                      # где в процессе лежит гостевая память
    python memscan.py find HEX [--max N]        # найти последовательность байт (big-endian, как в госте)
    python memscan.py dump GUEST_ADDR [LEN]     # показать байты по гостевому адресу

Порт держит память Xbox 360 одним большим отображением: гостевой адрес A лежит по
host = base + A. База ищется по образу default.xex: в госте он начинается с 0x82000000
(PE-заголовок «MZ», затем строка из образа). Только чтение (ReadProcessMemory).
"""
import argparse, ctypes, ctypes.wintypes as wt, struct, subprocess, sys

PROCESS_VM_READ, PROCESS_QUERY_INFORMATION = 0x10, 0x400
MEM_COMMIT = 0x1000
k32 = ctypes.WinDLL('kernel32', use_last_error=True)

class MBI(ctypes.Structure):
    _fields_ = [('BaseAddress', ctypes.c_void_p), ('AllocationBase', ctypes.c_void_p),
                ('AllocationProtect', wt.DWORD), ('PartitionId', wt.WORD), ('RegionSize', ctypes.c_size_t),
                ('State', wt.DWORD), ('Protect', wt.DWORD), ('Type', wt.DWORD)]

def pid_of(name='nhl13.exe'):
    out = subprocess.run(['tasklist', '/FI', f'IMAGENAME eq {name}', '/FO', 'CSV', '/NH'], capture_output=True, text=True).stdout
    for line in out.splitlines():
        parts = [p.strip('"') for p in line.split('","')]
        if parts and parts[0].lower() == name:
            return int(parts[1])
    raise SystemExit(f'{name} не запущен')

class Proc:
    def __init__(self, pid):
        self.h = k32.OpenProcess(PROCESS_VM_READ | PROCESS_QUERY_INFORMATION, False, pid)
        if not self.h:
            raise SystemExit(f'OpenProcess: {ctypes.get_last_error()}')

    def read(self, addr, n):
        buf = ctypes.create_string_buffer(n)
        got = ctypes.c_size_t()
        if not k32.ReadProcessMemory(self.h, ctypes.c_void_p(addr), buf, n, ctypes.byref(got)):
            return None
        return buf.raw[:got.value]

    def regions(self):
        addr, mbi = 0, MBI()
        while k32.VirtualQueryEx(self.h, ctypes.c_void_p(addr), ctypes.byref(mbi), ctypes.sizeof(mbi)):
            base, size = mbi.BaseAddress or 0, mbi.RegionSize
            if mbi.State == MEM_COMMIT and not mbi.Protect & 0x100 and mbi.Protect not in (0, 1):
                yield base, size
            addr = base + size
            if addr >= 1 << 47:
                break

def find_base(p):
    probe = open(r'S:\Claude\megarohas_nhl13\game\extracted\xex\default.bin', 'rb').read()[0x1000:0x1040]
    # сначала типичные базы, потом — поиск образа по регионам процесса
    for gb in (0x100000000, 0x200000000, 0x80000000, 0x300000000, 0x400000000, 0x1000000000):
        data = p.read(gb + 0x82001000, len(probe))
        if data == probe:
            return gb
    # медленный путь: найти probe в регионах
    for base, size in p.regions():
        step = 1 << 22
        for off in range(0, size, step):
            data = p.read(base + off, min(step, size - off))
            if data and probe in data:
                host = base + off + data.index(probe)
                return host - 0x82001000
    raise SystemExit('гостевая память не найдена')

def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('cmd', choices=['base', 'find', 'dump'])
    ap.add_argument('arg', nargs='?')
    ap.add_argument('arg2', nargs='?')
    ap.add_argument('--max', type=int, default=20)
    a = ap.parse_args()
    p = Proc(pid_of())
    gb = find_base(p)
    if a.cmd == 'base':
        print(f'гостевая база: 0x{gb:X}')
        return
    if a.cmd == 'dump':
        ga = int(a.arg, 16)
        n = int(a.arg2 or '256', 0)
        data = p.read(gb + ga, n) or b''
        for i in range(0, len(data), 16):
            print(f'{ga + i:08X}  {data[i:i + 16].hex(" ")}')
        return
    pat = bytes.fromhex(a.arg)
    hits = 0
    for gaddr_lo, gaddr_hi in ((0x00000000, 0x40000000), (0x40000000, 0x80000000), (0x80000000, 0xA0000000), (0xA0000000, 0x100000000)):
        step = 1 << 22
        for g in range(gaddr_lo, gaddr_hi, step):
            data = p.read(gb + g, step + len(pat))
            if not data:
                continue
            o = data.find(pat)
            while o != -1 and o < step:
                print(f'0x{g + o:08X}')
                hits += 1
                if hits >= a.max:
                    return
                o = data.find(pat, o + 1)
    print(f'найдено: {hits}')

if __name__ == '__main__':
    main()
