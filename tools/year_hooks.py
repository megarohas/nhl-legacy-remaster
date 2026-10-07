"""Врезки сдвига года для порта: находит в образе константы-года и пишет [[midasm_hook]].

    python year_hooks.py IMAGE > port/nhl13_year_hooks.toml      # TOML для ReXGlue
    python year_hooks.py IMAGE --report                          # таблица решений по всем местам

Игра считает «сейчас» от зашитого 2012 (сезон 2012/13): дата «Играть сейчас»
(MakeDate(2012, 8, 14)), год новой франшизы, «номер сезона = год − 2012», «год ≥ 2012 —
сезон лиги, иначе история из базы», возраст проспектов 2012 − 18 = 1994 и т. д. Порт
сдвигает всё это на delta = season_year − 2012 (port/src/nhl13_year.cpp):

- li / subfic rD, …, Y и addi rD, rA, +Y — после инструкции rD += delta;
- addi rD, rA, −Y — после инструкции rD −= delta;
- cmpwi / cmplwi crN, rA, Y — после инструкции crN пересчитывается против Y + delta.

Правило: сдвигаются все li/subfic/cmp* с 2011–2013 и addi ±2011…2013 по всему образу,
кроме KEEP — мест, где число не год лиги (адреса, размеры, онлайн, исторические факты).
Плюс EXTRA — года, производные от 2012 (1962 = 2012 − 50, 1994 = 2012 − 18…). Разбор
каждого места — docs/year-and-date.md. Любое расхождение инструкции с ожидаемой — ошибка.
"""
import struct, sys

BASE = 0x82000000
YEARS = (2011, 2012, 2013)

# Совпадения с годом, которые сдвигать нельзя.
KEEP = {
    # li / cmp
    0x826AF878: 'li r5, 2013 — номер строки в assert',
    0x82D72B78: 'li r3, 2013 — «год продукта» для логов и онлайна (203 вызова)',
    0x83353728: 'li r4, 2012 — метка времени 12.12.2012 (онлайн)',
    0x82A04C88: 'cmpwi 2011 — сезон онлайна (82A2BBF8 = 2011 + x)',
    0x82A05AEC: 'cmpwi 2012 — сезон онлайна',
    0x82A12CD8: 'cmpwi 2012 — сезон онлайна',
    0x82A41198: 'cmpwi 2011 — сезон онлайна',
    0x827E0E5C: 'cmpwi 2011 — переезд Атланты в Виннипег (исторический факт)',
    0x82BC3238: 'cmpwi 2011 — внутри перевода Unix-времени',
    # addi: адреса (lis + addi), смещения в структурах, указатели
    0x82515E24: 'адрес', 0x8252C0F0: 'указатель', 0x8252CC40: 'указатель',
    0x8262A1F0: 'указатель', 0x8262A1F8: 'указатель', 0x826D6B6C: 'адрес', 0x826DA32C: 'адрес',
    0x827E642C: 'смещение в структуре', 0x82828AFC: 'адрес', 0x828323D0: 'адрес',
    0x829B15E0: 'адрес', 0x82AE82E8: 'адрес', 0x82AEE434: 'адрес', 0x82B91B8C: 'адрес',
    0x82D5D470: 'адрес', 0x82F54928: 'адрес', 0x82FF7DD4: 'адрес', 0x8366B838: 'адрес',
    0x836A5F20: 'адрес', 0x8379D038: 'адрес', 0x832A7D70: 'указатель', 0x832A91C8: 'указатель',
    0x832AAA34: 'указатель', 0x832F0A90: 'указатель', 0x832F0D20: 'указатель',
    # addi: онлайн-сезон и парная (де)сериализация поля «год − 2012»
    0x82A2BC1C: 'сезон онлайна 2011 + x', 0x82A4118C: 'сезон онлайна', 0x82A46560: 'сезон онлайна',
    0x82D73034: 'пара с 82D84704: +2012 / −2012 одного поля (сериализация)',
    0x82D84704: 'пара с 82D73034',
}

# Года, производные от базового 2012, — сдвигаются вместе с ним.
EXTRA = {
    0x827A9BE0: 'li r3, 1962 — минимальный год рождения в редакторе (2012 − 50)',
    0x827A9BE8: 'li r3, 1997 — максимальный год рождения (2012 − 15)',
    0x827DEBB8: 'li r11, 1962 — индекс в списке годов рождения',
    0x827DEBBC: 'cmpwi 1962 — то же',
    0x828C5F84: 'li r11, 1962 — год рождения не раньше 2012 − 50',
    0x827BF920: 'li r3, 1994 — FeLeague, слот 16: год рождения 18-летних (2012 − 18)',
    0x82788068: 'li r11, 1993 — год рождения игрока «Стань профи» по умолчанию',
    0x8278807C: 'li r11, 1992 — то же',
    0x82823CB8: 'li r7, 1986 — год рождения созданного игрока по умолчанию',
    0x82823D00: 'li r8, 2006 — год драфта созданного игрока по умолчанию',
    0x827D2F70: 'subfic 2030 — год драфта сгенерированного игрока (2012 + 18 − возраст)',
    0x8284EF78: 'cmplwi 2004 — «недавний драфт» (2012 − 8)',
    0x82985D00: 'cmplwi 2004 — то же в интерфейсе',
}

def load(path):
    img = open(path, 'rb').read()
    e = struct.unpack('<I', img[0x3C:0x40])[0]
    nsec, optsz = struct.unpack('<H', img[e + 6:e + 8])[0], struct.unpack('<H', img[e + 20:e + 22])[0]
    for i in range(nsec):
        sh = e + 24 + optsz + 40 * i
        if img[sh:sh + 8].rstrip(b'\0') == b'.text':
            vsize, va, rsize = struct.unpack('<III', img[sh + 8:sh + 20])
            return img, BASE + va, BASE + va + min(vsize, rsize)
    raise SystemExit('нет секции .text')

def decode(w):
    """(вид, rD, rA, crN, imm) для li/addi/subfic/cmpwi/cmplwi, иначе None."""
    op, d, a = w >> 26, (w >> 21) & 31, (w >> 16) & 31
    simm = (w & 0xFFFF) - 0x10000 if w & 0x8000 else w & 0xFFFF
    if op == 14:
        return ('li', d, 0, None, simm) if a == 0 else ('addi', d, a, None, simm)
    if op == 8:
        return ('subfic', d, a, None, simm)
    if op == 11 and not d & 1:
        return ('cmpwi', None, a, d >> 2, simm)
    if op == 10 and not d & 1:
        return ('cmplwi', None, a, d >> 2, w & 0xFFFF)
    return None

def leap_math_after(img, addr, reg):
    """Результат дальше делится на 4 или берётся по модулю 4 — похоже на счёт високосных."""
    for k in range(1, 7):
        w = struct.unpack('>I', img[addr + 4 * k - BASE:addr + 4 * k - BASE + 4])[0]
        op, s = w >> 26, (w >> 21) & 31
        if op == 31 and ((w >> 1) & 0x3FF) == 824 and s == reg and ((w >> 11) & 31) == 2:
            return True  # srawi rX, reg, 2
        if op == 21 and s == reg and ((w >> 6) & 31, (w >> 1) & 31) == (30, 31):
            return True  # rlwinm rX, reg, 0, 30, 31 (& 3)
    return False

def sites(img, lo, hi):
    out = []
    for i, (w,) in enumerate(struct.iter_unpack('>I', img[lo - BASE:hi - BASE])):
        a = lo + 4 * i
        dec = decode(w)
        if not dec:
            continue
        kind, d, ra, cr, imm = dec
        if a in EXTRA:
            out.append((a, dec, 'extra'))
        elif kind == 'addi' and abs(imm) in YEARS or kind != 'addi' and imm in YEARS:
            out.append((a, dec, 'keep' if a in KEEP else 'shift'))
    found = {a for a, _, _ in out}
    missing = [a for a in list(KEEP) + list(EXTRA) if a not in found]
    if missing:
        raise SystemExit('нет ожидаемых инструкций: ' + ', '.join(f'{a:08X}' for a in missing))
    return out

def hook(a, dec):
    kind, d, ra, cr, imm = dec
    if kind in ('li', 'subfic') or kind == 'addi' and imm > 0:
        return 'Nhl13YearAdd', [f'r{d}']
    if kind == 'addi':
        return 'Nhl13YearSub', [f'r{d}']
    sign = 'S' if kind == 'cmpwi' else 'U'
    return f'Nhl13YearCmp{sign}{imm}', [f'r{ra}', f'cr{cr}']

def main():
    sys.stdout.reconfigure(encoding='utf-8', newline='\n')
    img, lo, hi = load(sys.argv[1])
    found = sites(img, lo, hi)
    if '--report' in sys.argv:
        for a, (kind, d, ra, cr, imm), what in found:
            note = KEEP.get(a) or EXTRA.get(a) or ''
            print(f'{a:08X}  {what:5}  {kind:6} {imm:6}  {note}')
        return
    shifted = [(a, dec) for a, dec, what in found if what != 'keep']
    for a, dec in shifted:
        if dec[0] in ('li', 'subfic', 'addi') and leap_math_after(img, a, dec[1]):
            raise SystemExit(f'{a:08X}: дальше счёт високосных — проверить вручную')
    print('# Сгенерировано tools/year_hooks.py — не править руками.')
    print(f'# Сдвиг года: {len(shifted)} мест (season_year в nhl13.toml, код — src/nhl13_year.cpp).')
    for a, dec in shifted:
        name, regs = hook(a, dec)
        print(f'\n[[midasm_hook]]\naddress = 0x{a:08X}\nname = "{name}"\n'
              f'registers = [{", ".join(chr(34) + r + chr(34) for r in regs)}]\nafter_instruction = true')

if __name__ == '__main__':
    main()
