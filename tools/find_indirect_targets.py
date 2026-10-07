"""Ищет код, на который есть только косвенные ссылки, но ReXGlue его не завёл как функцию.

    python find_indirect_targets.py IMAGE REGISTER_CPP [FUNCTIONS_TOML] > batch.toml

IMAGE — образ памяти из xex.py (база 0x82000000), REGISTER_CPP — сгенерированный
nhl13_register.cpp (строки SetFunction(0xADDR, …) — известные функции). Адреса из
FUNCTIONS_TOML (наши ручные записи) из «известных» вычитаются — так пачка
пересчитывается целиком, а не только новые находки.

Источники адресов:
  - указатели на .text в .rdata и .data (vtable, таблицы обратных вызовов);
  - адреса, собранные в коде парой lis rX,hi + addi/ori rY,rX,lo.
Фильтр (осторожный):
  - адрес не известен и не лежит внутри функции из .pdata (иначе это может быть
    цель switch-таблицы, и объявление функции разрежет чужую функцию);
  - перед адресом граница: blr / bctr / безусловный b / нулевое выравнивание;
  - первая инструкция похожа на начало кода;
  - не база вычисляемого switch: адрес из lis+addi дальше идёт в add → mtctr → bctr
    (0x827E2670 — case сразу после bctr; 0x832B9AA4 — case перед диспетчером, его
    объявление разрезало функцию и оставило default снаружи); плюс старая проверка
    «сразу перед адресом add/lwzx/lhzx/lbzx → mtctr → bctr»;
  - ссылка из данных не часть таблицы переходов switch: таблица — это база, которую
    код собирает lis+addi и читает lwzx (vtable так не читают). Грубое правило «3+
    указателя в окне 0x800» выбрасывало настоящие vtable (0x83963348: 8 методов
    рядом в коде → FATAL «unregistered function at 0x8241A2D0»).
"""
import bisect, re, struct, sys
from collections import defaultdict

BASE = 0x82000000

def main():
    img = open(sys.argv[1], 'rb').read()
    known = {int(m.group(1), 16) for m in re.finditer(rb'SetFunction\(0x([0-9A-Fa-f]{8})', open(sys.argv[2], 'rb').read())}
    if len(sys.argv) > 3:
        known -= {int(m.group(1), 16) for m in re.finditer(rb'(?m)^0x([0-9A-Fa-f]{8})\s*=', open(sys.argv[3], 'rb').read())}
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
    jump_table_bases = set()
    words = struct.unpack(f'>{(text_hi - text_lo) // 4}I', img[text_lo - BASE:text_hi - BASE])
    for i, w in enumerate(words):
        if w >> 26 == 15 and (w >> 16) & 31 == 0:  # lis rX, hi
            rx, hi16 = (w >> 21) & 31, w & 0xFFFF
            for n, x in enumerate(words[i + 1:i + 9]):
                op, rs, ra, imm = x >> 26, (x >> 21) & 31, (x >> 16) & 31, x & 0xFFFF
                if op == 14 and ra == rx:      # addi rY, rX, lo
                    v = ((hi16 << 16) + (imm - 0x10000 if imm & 0x8000 else imm)) & 0xFFFFFFFF
                elif op == 24 and rs == rx:    # ori rY, rX, lo
                    v = (hi16 << 16) | imm
                else:
                    continue
                if text_lo <= v < text_hi and not v & 3:
                    ry = rs if op == 14 else ra
                    tail = words[i + 2 + n:i + 2 + n + 8]
                    is_switch_base = any(
                        y >> 26 == 31 and (y >> 1) & 0x3FF == 266 and ry in ((y >> 16) & 31, (y >> 11) & 31)
                        and any(z == 0x4E800420 for z in tail[k + 1:k + 4])
                        for k, y in enumerate(tail))
                    if not is_switch_base:
                        refs[v].append(f'code {text_lo + 4 * i:08X}')
                else:
                    ry = rs if op == 14 else ra  # регистр с базой; lwzx от неё — switch
                    for y in words[i + 2 + n:i + 2 + n + 8]:
                        if y >> 26 == 31 and (y >> 1) & 0x3FF == 23 and ry in ((y >> 16) & 31, (y >> 11) & 31):
                            jump_table_bases.add(v)
                            break
                break
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
            start = i
            if lo + 4 * i in jump_table_bases:
                # Таблица переходов: её записи смотрят в одну функцию. Вплотную за
                # ней может лежать vtable (0x822E58E0, метод 0x8243A990) — её не трогаем.
                first = vals[i]
                while start < j and abs(vals[start] - first) < 0x4000:
                    start += 1
            for k in range(start, j):
                refs[vals[k]].append(f'data {lo + 4 * k:08X}')
            i = j

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
