"""Врезки «30 команд НХЛ → N» (и «30 клубов АХЛ → 32») из списков мест (разбор — docs/teams.md, docs/ahl32.md).

    python team_hooks.py SITES.json [SITES2.json ...]            # port/nhl13_team_sites.toml + port/src/nhl13_team_sites.cpp
    python team_hooks.py SITES.json [SITES2.json ...] --report   # только список: что будет сделано и что отброшено
    python team_hooks.py ... --out-dir DIR                       # записать оба файла в DIR (для сверки, port/ не трогается)
    python team_hooks.py --game legacy SITES.json ...            # порт NHL Legacy: legacy-port/nhllegacy_team_sites.toml
                                                                 # + legacy-port/src/nhllegacy_team_sites.cpp (имена NhlLegacy…)

SITES.json — список {"addr", "old", "new", "class", "func", "what"[, "when"]}: одна инструкция, у которой
меняется только непосредственное значение (cmpwi/cmplwi, li/addi, mulli). Старое слово сверяется с образом
(game/extracted/xex/default.bin, база 0x82000000), места с уже существующими врезками
(port/nhl13_team_hooks.toml) пропускаются. Каждое место — [[midasm_hook]] после инструкции:
сравнение пересчитывается с новым числом, результат li/addi/mulli заменяется.

Условие места — поле "when" (у места или у всего файла): "team32" (по умолчанию) — при nhl_teams = 32
(Nhl13ThirtyTwo() в src/nhl13_teams.cpp), "ahl32" — при nhl_ahl_teams = 32 (Nhl13Ahl32(); включается только
вместе с nhl_teams = 32). Если один адрес есть в обоих списках, получается одна врезка: при ahl32 — число из
списка ahl32, иначе при 32 — из team32. Пока мест ahl32 нет, вывод тот же, что у прежней версии.

Поле "gate" у места team32 — своё условие вместо Nhl13ThirtyTwo(): "Имя(rN)" — функция из src/nhl13_teams.cpp,
bool Имя(PPCRegister&), получает регистр rN (сама проверяет и nhl_teams). Нужна там, где одна и та же
инструкция служит разным лигам (8292A8B8: отметки таблицы НХЛ и АХЛ). Вместе с местом ahl32 не бывает.
"""
import argparse, json, os, re, struct, sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
IMAGE = os.path.join(ROOT, 'game', 'extracted', 'xex', 'default.bin')
BASE = 0x82000000
HOOKS = os.path.join(ROOT, 'port', 'nhl13_team_hooks.toml')
OUT_TOML = os.path.join(ROOT, 'port', 'nhl13_team_sites.toml')
OUT_CPP = os.path.join(ROOT, 'port', 'src', 'nhl13_team_sites.cpp')

# Игра: образ, свои ручные врезки (места с ними пропускаются), куда писать и префикс имён в C++.
PROFILES = {
    'nhl13': dict(image=IMAGE, hooks=HOOKS, out_toml=OUT_TOML, out_cpp=OUT_CPP, prefix='Nhl13',
                  docs='docs/teams.md', toml_rel='port/nhl13_team_sites.toml'),
    'legacy': dict(image=os.path.join(ROOT, 'game', 'other', 'legacy', 'xex', 'default.bin'),
                   hooks=os.path.join(ROOT, 'legacy-port', 'nhllegacy_team_hooks.toml'),
                   out_toml=os.path.join(ROOT, 'legacy-port', 'nhllegacy_team_sites.toml'),
                   out_cpp=os.path.join(ROOT, 'legacy-port', 'src', 'nhllegacy_team_sites.cpp'),
                   prefix='NhlLegacy', docs='docs/legacy-port.md',
                   toml_rel='legacy-port/nhllegacy_team_sites.toml'),
}
P = PROFILES['nhl13']

WHENS = ('team32', 'ahl32')  # порядок проверки в C++ — обратный: сначала ahl32 (он строже)


def gate_call(when):
    return {'team32': f"{P['prefix']}ThirtyTwo()", 'ahl32': f"{P['prefix']}Ahl32()"}[when]


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


def variant(site, img):
    """(вид, поля старой инструкции, новое число) или (None, причина)."""
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
    return (kind, f, g['imm']), None


def value_tag(kind, f, n):
    """Часть имени функции для одного варианта (как в прежней версии)."""
    if kind in ('cmps', 'cmpu', 'li'):
        return str(n)
    if kind == 'addi':
        delta = n - f['imm']
        return f"{'p' if delta >= 0 else 'm'}{abs(delta)}"
    return f"{f['imm']}_{n}"  # mulli


def parse_gate(site):
    """"Имя(rN)" → (имя, регистр) или None."""
    g = site.get('gate')
    if not g:
        return None
    m = re.fullmatch(r'([A-Za-z_][A-Za-z0-9_]*)\((r\d+)\)', g)
    if not m:
        raise SystemExit(f"{site['addr']}: gate {g!r} — нужно «Имя(rN)»")
    return m.group(1), m.group(2)


def plan(variants, gate=None):
    """variants: {when: (kind, f, n)} одного адреса → (имя функции, регистры, текст)."""
    kind, f, _ = next(iter(variants.values()))
    base = {'cmps': 'CmpS', 'cmpu': 'CmpU', 'li': 'Li', 'addi': 'Add'}.get(kind)
    if kind == 'mulli':
        base = 'MulSame' if f['rd'] == f['ra'] else 'Mul'
    tags = []
    for when in WHENS:
        if when in variants:
            tag = value_tag(kind, f, variants[when][2])
            tags.append(tag if when == 'team32' else 'a' + tag)
    name = f"{P['prefix']}{base}_{'_'.join(tags)}"
    if gate:
        name += '_' + (gate[0][len(P['prefix']):] if gate[0].startswith(P['prefix']) else gate[0])
    if kind in ('cmps', 'cmpu'):
        regs = [f"r{f['ra']}", f"cr{f['cr']}"]
        head = f"{kind} r{f['ra']}, {f['imm']}"
    elif kind == 'li':
        regs = [f"r{f['rd']}"]
        head = f"li r{f['rd']}, {f['imm']}"
    elif kind == 'addi':
        regs = [f"r{f['rd']}"]
        head = f"addi r{f['rd']}, r{f['ra']}, {f['imm']}"
    else:
        regs = [f"r{f['rd']}"] if f['rd'] == f['ra'] else [f"r{f['rd']}", f"r{f['ra']}"]
        head = f"mulli r{f['rd']}, r{f['ra']}, {f['imm']}"
    outs = [f"{variants[w][2]}" + ('' if w == 'team32' else ' (ahl32)') for w in WHENS if w in variants]
    if gate:
        if gate[1] in regs:
            raise SystemExit(f'{name}: регистр условия {gate[1]} совпадает с регистром инструкции')
        regs = regs + [gate[1]]
        outs = [f'{o} при {gate[0]}({gate[1]})' for o in outs]
    return name, regs, f"{head} → {' / '.join(outs)}"


def existing_hooks():
    if not os.path.exists(P['hooks']):
        return set()
    return {int(m, 16) for m in re.findall(r'address\s*=\s*0x([0-9A-Fa-f]+)', open(P['hooks'], encoding='utf-8').read())}


def cpp_gated(name, variants, gate):
    """Место team32 со своим условием gate = (функция, регистр): регистр — последний параметр."""
    kind, f, n = variants['team32']
    cond, g = f'{gate[0]}(g)', 'PPCRegister& g'
    if kind in ('cmps', 'cmpu'):
        t = 'int32_t' if kind == 'cmps' else 'uint32_t'
        field = 's32' if kind == 'cmps' else 'u32'
        return (f'void {name}(PPCRegister& a, PPCCRRegister& cr, {g}) {{\n'
                f'  if ({cond}) {{\n'
                f'    const {t} v = a.{field}, n = {n};\n'
                f'    cr.lt = v < n;\n    cr.gt = v > n;\n    cr.eq = v == n;\n  }}\n}}\n')
    if kind == 'li':
        return f'void {name}(PPCRegister& d, {g}) {{\n  if ({cond}) {{\n    d.s64 = {n};\n  }}\n}}\n'
    if kind == 'addi':
        return f'void {name}(PPCRegister& d, {g}) {{\n  if ({cond}) {{\n    d.s64 += {n - f["imm"]};\n  }}\n}}\n'
    if f['rd'] != f['ra']:
        return (f'void {name}(PPCRegister& d, PPCRegister& a, {g}) {{\n'
                f'  if ({cond}) {{\n    d.s64 = static_cast<int64_t>(a.s32) * {n};\n  }}\n}}\n')
    return (f'void {name}(PPCRegister& d, {g}) {{\n'
            f'  if ({cond}) {{\n    d.s64 = static_cast<int64_t>(d.s32 / {f["imm"]}) * {n};\n  }}\n}}\n')


def cpp_function(name, regs, variants, gate=None):
    """Тело функции; variants: {when: (kind, f, n)}."""
    kind, f, _ = next(iter(variants.values()))
    if gate:
        return cpp_gated(name, variants, gate)
    whens = [w for w in reversed(WHENS) if w in variants]  # сначала ahl32
    if list(variants) == ['team32']:  # прежний вид — вывод не меняется
        n = variants['team32'][2]
        if kind in ('cmps', 'cmpu'):
            t = 'int32_t' if kind == 'cmps' else 'uint32_t'
            field = 's32' if kind == 'cmps' else 'u32'
            return (f'void {name}(PPCRegister& a, PPCCRRegister& cr) {{\n'
                    f'  if ({gate_call('team32')}) {{\n'
                    f'    const {t} v = a.{field}, n = {n};\n'
                    f'    cr.lt = v < n;\n    cr.gt = v > n;\n    cr.eq = v == n;\n  }}\n}}\n')
        if kind == 'li':
            return f'void {name}(PPCRegister& d) {{\n  if ({gate_call('team32')}) {{\n    d.s64 = {n};\n  }}\n}}\n'
        if kind == 'addi':
            return f'void {name}(PPCRegister& d) {{\n  if ({gate_call('team32')}) {{\n    d.s64 += {n - f["imm"]};\n  }}\n}}\n'
        if f['rd'] != f['ra']:
            return (f'void {name}(PPCRegister& d, PPCRegister& a) {{\n'
                    f'  if ({gate_call('team32')}) {{\n    d.s64 = static_cast<int64_t>(a.s32) * {n};\n  }}\n}}\n')
        return (f'void {name}(PPCRegister& d) {{\n'
                f'  if ({gate_call('team32')}) {{\n    d.s64 = static_cast<int64_t>(d.s32 / {f["imm"]}) * {n};\n  }}\n}}\n')
    # несколько условий: число выбирается по самому строгому включённому
    pick = ''.join(f"  {'if' if i == 0 else '} else if'} ({gate_call(w)}) {{\n    n = {variants[w][2]};\n"
                   for i, w in enumerate(whens)) + '  } else {\n    return;\n  }\n'
    if kind in ('cmps', 'cmpu'):
        t = 'int32_t' if kind == 'cmps' else 'uint32_t'
        field = 's32' if kind == 'cmps' else 'u32'
        return (f'void {name}(PPCRegister& a, PPCCRRegister& cr) {{\n  {t} n;\n{pick}'
                f'  const {t} v = a.{field};\n  cr.lt = v < n;\n  cr.gt = v > n;\n  cr.eq = v == n;\n}}\n')
    if kind == 'li':
        return f'void {name}(PPCRegister& d) {{\n  int64_t n;\n{pick}  d.s64 = n;\n}}\n'
    if kind == 'addi':  # результат = ra + новое число; к уже посчитанному добавляется разница
        return f'void {name}(PPCRegister& d) {{\n  int64_t n;\n{pick}  d.s64 += n - ({f["imm"]});\n}}\n'
    if f['rd'] != f['ra']:
        return f'void {name}(PPCRegister& d, PPCRegister& a) {{\n  int64_t n;\n{pick}  d.s64 = static_cast<int64_t>(a.s32) * n;\n}}\n'
    return (f'void {name}(PPCRegister& d) {{\n  int64_t n;\n{pick}'
            f'  d.s64 = static_cast<int64_t>(d.s32 / {f["imm"]}) * n;\n}}\n')


def load_sites(paths):
    out = []
    for path in paths:
        data = json.load(open(path, encoding='utf-8'))
        default = 'team32'
        if isinstance(data, dict):
            default = data.get('when', 'team32')
            data = data.get('sites', [])
        for s in data:
            s = dict(s)
            s.setdefault('when', default)
            if s['when'] not in WHENS:
                raise SystemExit(f"{path}: {s['addr']}: неизвестное условие {s['when']!r}")
            out.append(s)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('sites', nargs='+')
    ap.add_argument('--report', action='store_true')
    ap.add_argument('--out-dir', help='куда записать .toml и .cpp вместо port/ (для сверки)')
    ap.add_argument('--game', choices=sorted(PROFILES), default='nhl13',
                    help='игра: nhl13 (port/) или legacy (legacy-port/)')
    a = ap.parse_args()
    global P
    P = PROFILES[a.game]
    sys.stdout.reconfigure(encoding='utf-8', newline='\n')
    img = open(P['image'], 'rb').read()
    have = existing_hooks()
    by_addr = {}
    for s in load_sites(a.sites):
        by_addr.setdefault(int(s['addr'], 16), {}).setdefault(s['when'], s)  # первое место на (адрес, условие)
    done, skipped = [], []
    for addr in sorted(by_addr):
        sites = by_addr[addr]
        first = sites.get('team32') or sites['ahl32']
        if addr in have:
            skipped.append((first, 'уже есть врезка'))
            continue
        variants, why = {}, None
        for when, s in sites.items():
            v, why = variant(s, img)
            if not v:
                break
            variants[when] = v
        if why:
            skipped.append((first, why))
            continue
        kinds = {(v[0], tuple(sorted((k, x) for k, x in v[1].items()))) for v in variants.values()}
        if len(kinds) != 1:
            skipped.append((first, 'разные старые слова в списках'))
            continue
        gate = parse_gate(sites['team32']) if 'team32' in sites else None
        if gate and len(variants) > 1:
            raise SystemExit(f"{first['addr']}: gate у места, которое есть и в списке ahl32")
        if 'ahl32' in sites and sites['ahl32'].get('gate'):
            raise SystemExit(f"{first['addr']}: gate бывает только у мест team32")
        done.append((sites, variants, gate, plan(variants, gate)))
    for sites, variants, gate, (name, regs, text) in done:
        s = sites.get('team32') or sites['ahl32']
        cls = '/'.join(sites[w].get('class', '') for w in WHENS if w in sites)
        need = ' [нужно: ' + sites['ahl32']['needs'] + ']' if 'ahl32' in sites and sites['ahl32'].get('needs') else ''
        print(f"{int(s['addr'], 16):08X} {cls:10} {text:38} {name}({', '.join(regs)})  {s.get('what', '')[:60]}{need}")
    for s, why in skipped:
        print(f"skip {s['addr']}: {why}")
    print(f'врезок: {len(done)}, пропущено: {len(skipped)}', file=sys.stderr)
    if a.report:
        return
    out_toml, out_cpp = P['out_toml'], P['out_cpp']
    if a.out_dir:
        os.makedirs(a.out_dir, exist_ok=True)
        out_toml = os.path.join(a.out_dir, os.path.basename(P['out_toml']))
        out_cpp = os.path.join(a.out_dir, os.path.basename(P['out_cpp']))
    ahl = any('ahl32' in v for _, v, _, _ in done)
    with open(out_toml, 'w', encoding='utf-8', newline='\n') as f:
        f.write(f"# Сгенерировано tools/team_hooks.py — не править руками. Разбор — {P['docs']}.\n"
                f"# «30 команд НХЛ → 32»: границы, константы, смещения АХЛ (src/{os.path.basename(P['out_cpp'])}).\n")
        if ahl:
            f.write('# Места ahl32 (docs/ahl32.md): «30 клубов АХЛ → 32», профи-команды 64 — при nhl_ahl_teams = 32.\n')
        for sites, variants, gate, (name, regs, text) in done:
            s = sites.get('team32') or sites['ahl32']
            cls = '/'.join(sites[w].get('class', '') for w in WHENS if w in sites)
            what = ' | '.join(sites[w].get('what', '') for w in WHENS if w in sites)
            f.write(f"\n# {cls} {s.get('func', '')}: {what}\n# {text}\n"
                    f"[[midasm_hook]]\naddress = 0x{int(s['addr'], 16):08X}\nname = \"{name}\"\n"
                    f"registers = [{', '.join(repr(r).replace(chr(39), chr(34)) for r in regs)}]\n"
                    f"after_instruction = true\n")
    funcs = {}
    for sites, variants, gate, (name, regs, text) in done:
        funcs.setdefault(name, (regs, variants, gate))
    gates = sorted({gate[0] for _, _, gate, _ in done if gate})
    with open(out_cpp, 'w', encoding='utf-8', newline='\n') as f:
        f.write('// Сгенерировано tools/team_hooks.py — не править руками.\n'
                f"// Врезки «30 команд НХЛ → 32» ({P['toml_rel']}); действуют при nhl_teams = 32.\n")
        if ahl:
            f.write('// Варианты ahl32 (nhl_ahl_teams = 32, только вместе с nhl_teams = 32) — docs/ahl32.md.\n')
        f.write(f"\n#include <cstdint>\n\n#include <rex/ppc.h>\n\nbool {P['prefix']}ThirtyTwo();\n")
        if ahl:
            f.write(f"bool {P['prefix']}Ahl32();\n")
        for g in gates:
            f.write(f'bool {g}(PPCRegister& r);\n')
        f.write('\n')
        for name in sorted(funcs):
            f.write(cpp_function(name, *funcs[name]) + '\n')
    print(f'записано: {out_toml}, {out_cpp}', file=sys.stderr)


if __name__ == '__main__':
    main()
