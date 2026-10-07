"""Ищет код, на который есть только косвенные ссылки, но ReXGlue его не завёл как функцию.

    python find_indirect_targets.py IMAGE REGISTER_CPP > batch.toml

IMAGE — образ памяти из xex.py (база 0x82000000), REGISTER_CPP — сгенерированный
nhl13_register.cpp (строки SetFunction(0xADDR, …) — известные функции).

Источники адресов:
  - указатели на .text в .rdata и .data (vtable, таблицы обратных вызовов);
  - адреса, собранные в коде парой lis rX,hi + addi/ori rY,rX,lo.
Фильтр (осторожный):
  - адрес не известен и не лежит внутри функции из .pdata (иначе это может быть
    цель switch-таблицы, и объявление функции разрежет чужую функцию);
  - перед адресом граница: blr / bctr / безусловный b / нулевое выравнивание;
  - первая инструкция похожа на начало кода;
  - не первый case вычисляемого switch (сразу перед адресом add/lwzx/lhzx/lbzx →
    mtctr → bctr — так 0x827E2670 оказался базой таблицы переходов);
  - ссылка из данных не часть таблицы переходов: 3+ указателя подряд, все в окне
    0x800 байт (у vtable цели разбросаны по коду).
"""
import bisect, re, struct, sys
from collections import defaultdict

BASE = 0x82000000

def main():
    img = open(sys.argv[1], 'rb').read()
    known = {int(m.group(1), 16) for m in re.finditer(rb'SetFunction\(0x([0-9A-Fa-f]{8})', open(sys.argv[2], 'rb').read())}
    word = lambda va: struct.unpack('>I', img[va - BASE:va - BASE + 4])[0]

    # секции из PE-заголовка образа
    e = struct.unpack('<I', img[0x3C:0x40])[0]
    nsec, optsz = struct.unpack('<H', img[e + 6:e + 8])[0], struct.unpack('<H', img[e + 20:e + 22])[0]
    sections = {}
    for i in range(nsec):
        sh = e + 24 + optsz + 40 * i
        name = img[sh:sh + 8].rstrip(b'\0').decode()
        vsize, va, rsize = struct.unpack('<III', img[sh + 8:sh + 20])
        sections[name] = (BASE + va, BASE + va + min(vsize, rsize))
    text_lo, text_hi = sections['.text']
    pd_lo, pd_hi = sections['.pdata']
    pdata = [(a, ((w >> 8) & 0x3FFFFF) * 4) for a, w in struct.iter_unpack('>II', img[pd_lo - BASE:pd_hi - BASE]) if a]
    pdata.sort()
    starts = [a for a, _ in pdata]

    def inside_pdata(a):
        i = bisect.bisect_right(starts, a) - 1
        return i >= 0 and starts[i] < a < starts[i] + pdata[i][1]

    def boundary_before(a):
        w = word(a - 4)
        return w in (0x4E800020, 0x4E800420, 0) or (w >> 26 == 18 and not w & 3)

    def switch_case_start(a):
        if word(a - 4) != 0x4E800420:
            return False
        mt, prev = word(a - 8), word(a - 12)
        is_mtctr = mt >> 26 == 31 and (mt >> 1) & 0x3FF == 467
        return is_mtctr and prev >> 26 == 31 and (prev >> 1) & 0x3FF in (266, 23, 279, 87)

    def plausible(w):
        op = w >> 26
        return w not in (0, 0xFFFFFFFF) and op in {4, 7, 8, 10, 11, 14, 15, 18, 19, 21, 24, 25, 28, 31,
                                                   32, 33, 34, 35, 36, 37, 38, 39, 40, 42, 44, 46, 47,
                                                   48, 50, 52, 54, 58, 59, 62, 63}

    refs = defaultdict(list)
    for name in ('.rdata', '.data'):
        lo, hi = sections[name]
        vals = struct.unpack(f'>{(hi - lo) // 4}I', img[lo - BASE:lo - BASE + (hi - lo) // 4 * 4])
        is_code = [text_lo <= v < text_hi and not v & 3 for v in vals]
        i = 0
        while i < len(vals):
            if not is_code[i]:
                i += 1
                continue
            j = i
            while j < len(vals) and is_code[j]:
                j += 1
            run = vals[i:j]
            jump_table = len(run) >= 3 and max(run) - min(run) < 0x800
            if not jump_table:
                for k, v in enumerate(run):
                    refs[v].append(f'data {lo + 4 * (i + k):08X}')
            i = j
    words = struct.unpack(f'>{(text_hi - text_lo) // 4}I', img[text_lo - BASE:text_hi - BASE])
    for i, w in enumerate(words):
        if w >> 26 == 15 and (w >> 16) & 31 == 0:  # lis rX, hi
            rx, hi16 = (w >> 21) & 31, w & 0xFFFF
            for x in words[i + 1:i + 9]:
                op, rs, ra, imm = x >> 26, (x >> 21) & 31, (x >> 16) & 31, x & 0xFFFF
                if op == 14 and ra == rx:      # addi rY, rX, lo
                    v = ((hi16 << 16) + (imm - 0x10000 if imm & 0x8000 else imm)) & 0xFFFFFFFF
                elif op == 24 and rs == rx:    # ori rY, rX, lo
                    v = (hi16 << 16) | imm
                else:
                    continue
                if text_lo <= v < text_hi and not v & 3:
                    refs[v].append(f'code {text_lo + 4 * i:08X}')
                break

    out = []
    for v in sorted(refs):
        if v in known or inside_pdata(v) or not boundary_before(v) or not plausible(word(v)) \
                or switch_case_start(v):
            continue
        out.append(v)
    print(f'# найдено кандидатов: {len(out)} (адресов с косвенными ссылками: {len(refs)}, известных функций: {len(known)})')
    for v in out:
        r = refs[v]
        print(f'0x{v:08X} = {{ name = "sub_{v:08X}" }}  # {", ".join(r[:3])}{" …" if len(r) > 3 else ""}')

if __name__ == '__main__':
    main()
