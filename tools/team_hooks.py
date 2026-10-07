"""Врезки «30 команд НХЛ → N» из списка мест (разбор — docs/teams.md).

    python team_hooks.py SITES.json            # port/nhl13_team_sites.toml + port/src/nhl13_team_sites.cpp
    python team_hooks.py SITES.json --report   # только список: что будет сделано и что отброшено

SITES.json — список {"addr", "old", "new", "class", "func", "what"}: одна инструкция, у которой меняется
только непосредственное значение (cmpwi/cmplwi, li/addi, mulli). Старое слово сверяется с образом
(game/extracted/xex/default.bin, база 0x82000000), места с уже существующими врезками
(port/nhl13_team_hooks.toml) пропускаются. Каждое место — [[midasm_hook]] после инструкции:
сравнение пересчитывается с новым числом, результат li/addi/mulli заменяется. Всё действует только
при nhl_teams = 32 (Nhl13ThirtyTwo() в src/nhl13_teams.cpp).
"""
import argparse, json, os, re, struct, sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
IMAGE = os.path.join(ROOT, 'game', 'extracted', 'xex', 'default.bin')
BASE = 0x82000000
HOOKS = os.path.join(ROOT, 'port', 'nhl13_team_hooks.toml')
OUT_TOML = os.path.join(ROOT, 'port', 'nhl13_team_sites.toml')
OUT_CPP = os.path.join(ROOT, 'port', 'src', 'nhl13_team_sites.cpp')


def s16(v):
    return v - 0x10000 if v & 0x8000 else v


def decode(w):
    """(вид, поля) для поддерживаемых инструкций, иначе None."""
    op = w >> 26
    if op in (10, 11):  # cmplwi / cmpwi
        if (w >> 21) & 1:
            return None  # 64-битное сравнение
        crf, ra, imm = (w >> 23) & 7, (w >> 16) & 31, w & 0xFFFF
        return ('cmpu' if op == 10 else 'cmps', dict(cr=crf, ra=ra, imm=imm if op == 10 else s16(imm)))
    if op == 14:  # addi / li
        rd, ra, imm = (w >> 21) & 31, (w >> 16) & 31, s16(w & 0xFFFF)
        return ('li' if ra == 0 else 'addi', dict(rd=rd, ra=ra, imm=imm))
    if op == 7:  # mulli
        return ('mulli', dict(rd=(w >> 21) & 31, ra=(w >> 16) & 31, imm=s16(w & 0xFFFF)))
    return None


def plan(site, img):
    """(имя функции, регистры, текст) или (None, причина)."""
    a = int(site['addr'], 16)
    old, new = int(site['old'], 16), int(site['new'], 16)
    word = struct.unpack('>I', img[a - BASE:a - BASE + 4])[0]
    if word != old:
        return None, f'в образе {word:08X}, а не {old:08X}'
    d_old, d_new = decode(old), decode(new)
    if not d_old or not d_new or d_old[0] != d_new[0]:
        return None, 'не поддерживаемая инструкция'
    kind, f, g = d_old[0], d_old[1], d_new[1]
    if {k: v for k, v in f.items() if k != 'imm'} != {k: v for k, v in g.items() if k != 'imm'}:
        return None, 'меняются регистры, а не число'
    n = g['imm']
    if kind in ('cmps', 'cmpu'):
        name = f"Nhl13Cmp{'S' if kind == 'cmps' else 'U'}_{n}"
        return (name, [f"r{f['ra']}", f"cr{f['cr']}"], f"{kind} r{f['ra']}, {f['imm']} → {n}"), None
    if kind == 'li':
        return (f'Nhl13Li_{n}', [f"r{f['rd']}"], f"li r{f['rd']}, {f['imm']} → {n}"), None
    if kind == 'addi':
        delta = n - f['imm']
        name = f"Nhl13Add_{'p' if delta >= 0 else 'm'}{abs(delta)}"
        return (name, [f"r{f['rd']}"], f"addi r{f['rd']}, r{f['ra']}, {f['imm']} → {n}"), None
    if kind == 'mulli':
        name = f"Nhl13Mul_{f['imm']}_{n}"
        regs = [f"r{f['rd']}", f"r{f['ra']}"]
        return (name, regs, f"mulli r{f['rd']}, r{f['ra']}, {f['imm']} → {n}"), None
    return None, 'не поддерживаемая инструкция'


def existing_hooks():
    if not os.path.exists(HOOKS):
        return set()
    return {int(m, 16) for m in re.findall(r'address\s*=\s*0x([0-9A-Fa-f]+)', open(HOOKS, encoding='utf-8').read())}


def cpp_function(name, regs):
    kind, _, arg = name[len('Nhl13'):].partition('_')
    if kind in ('CmpS', 'CmpU'):
        t = 'int32_t' if kind == 'CmpS' else 'uint32_t'
        field = 's32' if kind == 'CmpS' else 'u32'
        return (f'void {name}(PPCRegister& a, PPCCRRegister& cr) {{\n'
                f'  if (Nhl13ThirtyTwo()) {{\n'
                f'    const {t} v = a.{field}, n = {arg};\n'
                f'    cr.lt = v < n;\n    cr.gt = v > n;\n    cr.eq = v == n;\n  }}\n}}\n')
    if kind == 'Li':
        return f'void {name}(PPCRegister& d) {{\n  if (Nhl13ThirtyTwo()) {{\n    d.s64 = {arg};\n  }}\n}}\n'
    if kind == 'Add':
        delta = int(arg[1:]) * (1 if arg[0] == 'p' else -1)
        return f'void {name}(PPCRegister& d) {{\n  if (Nhl13ThirtyTwo()) {{\n    d.s64 += {delta};\n  }}\n}}\n'
    if kind == 'Mul':
        old, new = arg.split('_')
        return (f'void {name}(PPCRegister& d, PPCRegister& a) {{\n'
                f'  if (Nhl13ThirtyTwo()) {{\n'
                f'    // d = a · {old} уже посчитано; если d и a — один регистр, a испорчено\n'
                f'    const int64_t x = (&d == &a) ? d.s32 / {old} : a.s32;\n'
                f'    d.s64 = x * {new};\n  }}\n}}\n')
    raise ValueError(name)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('sites')
    ap.add_argument('--report', action='store_true')
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding='utf-8', newline='\n')
    img = open(IMAGE, 'rb').read()
    sites = json.load(open(a.sites, encoding='utf-8'))
    if isinstance(sites, dict):
        sites = sites.get('sites', [])
    have = existing_hooks()
    done, skipped, seen = [], [], set()
    for s in sorted(sites, key=lambda s: int(s['addr'], 16)):
        addr = int(s['addr'], 16)
        if addr in seen:
            continue
        seen.add(addr)
        if addr in have:
            skipped.append((s, 'уже есть врезка'))
            continue
        p, why = plan(s, img)
        if p:
            done.append((s, p))
        else:
            skipped.append((s, why))
    for s, (name, regs, text) in done:
        print(f"{int(s['addr'], 16):08X} {s.get('class', ''):10} {text:34} {name}({', '.join(regs)})  {s.get('what', '')[:70]}")
    for s, why in skipped:
        print(f"skip {s['addr']}: {why}")
    print(f'врезок: {len(done)}, пропущено: {len(skipped)}', file=sys.stderr)
    if a.report:
        return
    with open(OUT_TOML, 'w', encoding='utf-8', newline='\n') as f:
        f.write('# Сгенерировано tools/team_hooks.py — не править руками. Разбор — docs/teams.md.\n'
                '# «30 команд НХЛ → 32»: границы, константы, смещения АХЛ (src/nhl13_team_sites.cpp).\n')
        for s, (name, regs, text) in done:
            f.write(f"\n# {s.get('class', '')} {s.get('func', '')}: {s.get('what', '')}\n# {text}\n"
                    f"[[midasm_hook]]\naddress = 0x{int(s['addr'], 16):08X}\nname = \"{name}\"\n"
                    f"registers = [{', '.join(repr(r).replace(chr(39), chr(34)) for r in regs)}]\n"
                    f"after_instruction = true\n")
    names = {}
    for s, (name, regs, text) in done:
        names.setdefault(name, regs)
    with open(OUT_CPP, 'w', encoding='utf-8', newline='\n') as f:
        f.write('// Сгенерировано tools/team_hooks.py — не править руками.\n'
                '// Врезки «30 команд НХЛ → 32» (port/nhl13_team_sites.toml); действуют при nhl_teams = 32.\n\n'
                '#include <cstdint>\n\n#include <rex/ppc.h>\n\nbool Nhl13ThirtyTwo();\n\n')
        for name in sorted(names):
            f.write(cpp_function(name, names[name]) + '\n')
    print(f'записано: {OUT_TOML}, {OUT_CPP}', file=sys.stderr)


if __name__ == '__main__':
    main()
