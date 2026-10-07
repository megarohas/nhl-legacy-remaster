"""Мини-дизассемблер PowerPC (Xbox 360) для разведки по образу из xex.py.

    python ppcdis.py IMAGE ADDR [COUNT]          # COUNT инструкций с адреса (hex)
    python ppcdis.py IMAGE --around ADDR [N]      # N инструкций до и после адреса

Знает частые целочисленные инструкции; остальное печатает как .long. Образ —
память с базы 0x82000000.
"""
import struct, sys

BASE = 0x82000000

def s16(v):
    return v - 0x10000 if v & 0x8000 else v

def dis(w, addr):
    op, d, a, b = w >> 26, (w >> 21) & 31, (w >> 16) & 31, (w >> 11) & 31
    imm, simm = w & 0xFFFF, s16(w & 0xFFFF)
    mem = {32: 'lwz', 33: 'lwzu', 34: 'lbz', 35: 'lbzu', 36: 'stw', 37: 'stwu', 38: 'stb', 39: 'stbu',
           40: 'lhz', 41: 'lhzu', 42: 'lha', 44: 'sth', 45: 'sthu', 46: 'lmw', 47: 'stmw',
           48: 'lfs', 50: 'lfd', 52: 'stfs', 54: 'stfd'}
    if w == 0x60000000:
        return 'nop'
    if op == 14:
        return f'li r{d}, {simm}' if a == 0 else f'addi r{d}, r{a}, {simm}'
    if op == 15:
        return f'lis r{d}, 0x{imm:X}' if a == 0 else f'addis r{d}, r{a}, 0x{imm:X}'
    if op == 24:
        return f'ori r{a}, r{d}, 0x{imm:X}'
    if op == 25:
        return f'oris r{a}, r{d}, 0x{imm:X}'
    if op == 28:
        return f'andi. r{a}, r{d}, 0x{imm:X}'
    if op == 11:
        return f'cmpwi cr{d >> 2}, r{a}, {simm}' if not d & 1 else f'cmpdi cr{d >> 2}, r{a}, {simm}'
    if op == 10:
        return f'cmplwi cr{d >> 2}, r{a}, {imm}' if not d & 1 else f'cmpldi cr{d >> 2}, r{a}, {imm}'
    if op == 8:
        return f'subfic r{d}, r{a}, {simm}'
    if op == 7:
        return f'mulli r{d}, r{a}, {simm}'
    if op in mem:
        return f'{mem[op]} {"f" if op >= 48 else "r"}{d}, {simm}(r{a})'
    if op == 58:
        return f'{["ld", "ldu", "lwa", "?"][w & 3]} r{d}, {s16(w & 0xFFFC)}(r{a})'
    if op == 62:
        return f'{["std", "stdu", "?", "?"][w & 3]} r{d}, {s16(w & 0xFFFC)}(r{a})'
    if op == 18:
        li = w & 0x03FFFFFC
        if li & 0x02000000:
            li -= 0x04000000
        tgt = li if w & 2 else addr + li
        return f'{"bl" if w & 1 else "b"} 0x{tgt & 0xFFFFFFFF:08X}'
    if op == 16:
        bd = s16(w & 0xFFFC)
        tgt = bd if w & 2 else addr + bd
        return f'bc{"l" if w & 1 else ""} {d}, cr{a >> 2}.{["lt", "gt", "eq", "so"][a & 3]}, 0x{tgt & 0xFFFFFFFF:08X}'
    if op == 19:
        xo = (w >> 1) & 0x3FF
        if xo == 16:
            return 'blr' if d == 20 else f'bclr {d}, {a}'
        if xo == 528:
            return 'bctr' if d == 20 else f'bcctr {d}, {a}'
    if op == 21:
        sh, mb, me = b, (w >> 6) & 31, (w >> 1) & 31
        return f'rlwinm r{a}, r{d}, {sh}, {mb}, {me}'
    if op == 31:
        xo = (w >> 1) & 0x3FF
        spr = ((w >> 16) & 31) | (((w >> 11) & 31) << 5)
        names = {266: 'add', 40: 'subf', 235: 'mullw', 491: 'divw', 459: 'divwu', 28: 'and', 316: 'xor',
                 24: 'slw', 536: 'srw', 792: 'sraw', 23: 'lwzx', 151: 'stwx', 87: 'lbzx', 215: 'stbx',
                 279: 'lhzx', 407: 'sthx', 75: 'mulhw', 11: 'mulhwu'}
        if xo == 444:
            return f'mr r{a}, r{d}' if d == b else f'or r{a}, r{d}, r{b}'
        if xo == 339:
            return 'mflr r%d' % d if spr == 8 else f'mfspr r{d}, {spr}'
        if xo == 467:
            return 'mtlr r%d' % d if spr == 8 else ('mtctr r%d' % d if spr == 9 else f'mtspr {spr}, r{d}')
        if xo in (0, 32):
            return f'{"cmpw" if xo == 0 else "cmplw"} cr{d >> 2}, r{a}, r{b}'
        if xo == 824:
            return f'srawi r{a}, r{d}, {b}'
        if xo == 954:
            return f'extsb r{a}, r{d}'
        if xo == 922:
            return f'extsh r{a}, r{d}'
        if xo == 104:
            return f'neg r{d}, r{a}'
        if xo in names:
            if xo in (24, 536, 792, 28, 316):
                return f'{names[xo]} r{a}, r{d}, r{b}'
            return f'{names[xo]} r{d}, r{a}, r{b}'
    return f'.long 0x{w:08X}'

def listing(img, addr, count):
    out = []
    for i in range(count):
        a = addr + 4 * i
        w = struct.unpack('>I', img[a - BASE:a - BASE + 4])[0]
        out.append(f'{a:08X}  {w:08X}  {dis(w, a)}')
    return out

def main():
    img = open(sys.argv[1], 'rb').read()
    if sys.argv[2] == '--around':
        addr = int(sys.argv[3], 16)
        n = int(sys.argv[4]) if len(sys.argv) > 4 else 12
        lines = listing(img, addr - 4 * n, 2 * n + 1)
        lines[n] = lines[n] + '   <==='
    else:
        lines = listing(img, int(sys.argv[2], 16), int(sys.argv[3]) if len(sys.argv) > 3 else 32)
    print('\n'.join(lines))

if __name__ == '__main__':
    main()
