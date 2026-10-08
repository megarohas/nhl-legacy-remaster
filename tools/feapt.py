"""ActionScript роликов интерфейса (Apt, Flash EA) NHL 12/13: дизассемблер, «декомпилятор», поиск.

    python feapt.py dis FILE.big [--raw] [--char N]   # весь код ролика: InitAction, кадры, обработчики клипов;
                                                      # --raw — команды байткода вместо восстановленных выражений
    python feapt.py classes FILE.big                  # классы и методы: Класс.prototype.Метод(параметры)
    python feapt.py calls FILE.big                    # какие имена ролик вызывает/читает у глобальных объектов
    python feapt.py index [--game nhl12|nhl13]        # индекс констант всех роликов fe (game/work/menu12/index)
    python feapt.py grep [--game G] [--exports|--imports] [--exact] PATTERN…   # поиск по индексу
    python feapt.py patch IN.big OUT.big СМЕЩЕНИЕ:СТАРЫЕ=НОВЫЕ…  # правка байткода той же длины (hex, смещения
                                                      # распакованной Apt Data — как в dis --raw)
    python feapt.py graft DST.big SRC.big OUT.big --char N --export ИМЯ   # пересадить символ N из SRC
                                                      # (с графикой) в DST под именем связи ИМЯ

Байткод — как у SWF (AS1/AS2) плюс команды EA (номера — как в OpenSAGE): аргументы
выровнены по 4 байтам, строки — указатели в Apt Data, константы — номера в «Apt constant file»
(через ConstantPool). Порядок байтов — big-endian (Xbox 360). Подробности — docs/fe-menu.md.
Каталог игры — переменная NHL13_GAME или game/ рядом с tools/.
"""
import json, os, re, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import playerhead as ph  # noqa: E402

# ---------------------------------------------------------------- таблица команд

# без аргументов
OPS0 = {
    0x00: 'End', 0x04: 'NextFrame', 0x05: 'PrevFrame', 0x06: 'Play', 0x07: 'Stop', 0x08: 'ToggleQuality',
    0x09: 'StopSounds', 0x0A: 'Add', 0x0B: 'Subtract', 0x0C: 'Multiply', 0x0D: 'Divide', 0x0E: 'Equals',
    0x0F: 'Less', 0x10: 'And', 0x11: 'Or', 0x12: 'Not', 0x13: 'StringEquals', 0x14: 'StringLength',
    0x15: 'StringExtract', 0x17: 'Pop', 0x18: 'ToInteger', 0x1C: 'GetVariable', 0x1D: 'SetVariable',
    0x20: 'SetTarget2', 0x21: 'StringAdd', 0x22: 'GetProperty', 0x23: 'SetProperty', 0x24: 'CloneSprite',
    0x25: 'RemoveSprite', 0x26: 'Trace', 0x27: 'StartDrag', 0x28: 'EndDrag', 0x29: 'StringLess',
    0x2A: 'Throw', 0x2B: 'CastOp', 0x2C: 'ImplementsOp', 0x30: 'RandomNumber', 0x31: 'MBStringLength',
    0x32: 'CharToAscii', 0x33: 'AsciiToChar', 0x34: 'GetTime', 0x35: 'MBStringExtract',
    0x36: 'MBCharToAscii', 0x37: 'MBAsciiToChar', 0x3A: 'Delete', 0x3B: 'Delete2', 0x3C: 'DefineLocal',
    0x3D: 'CallFunction', 0x3E: 'Return', 0x3F: 'Modulo', 0x40: 'NewObject', 0x41: 'DefineLocal2',
    0x42: 'InitArray', 0x43: 'InitObject', 0x44: 'TypeOf', 0x45: 'TargetPath', 0x46: 'Enumerate',
    0x47: 'Add2', 0x48: 'Less2', 0x49: 'Equals2', 0x4A: 'ToNumber', 0x4B: 'ToString', 0x4C: 'PushDuplicate',
    0x4D: 'StackSwap', 0x4E: 'GetMember', 0x4F: 'SetMember', 0x50: 'Increment', 0x51: 'Decrement',
    0x52: 'CallMethod', 0x53: 'NewMethod', 0x54: 'InstanceOf', 0x55: 'Enumerate2',
    0x59: 'PushZero', 0x5A: 'PushOne', 0x5B: 'CallFuncPop', 0x5C: 'CallFunc', 0x5D: 'CallMethodPop',
    0x5E: 'CallMethodEA', 0x60: 'BitAnd', 0x61: 'BitOr', 0x62: 'BitXor', 0x63: 'BitLShift', 0x64: 'BitRShift',
    0x65: 'BitURShift', 0x66: 'StrictEquals', 0x67: 'Greater', 0x68: 'StringGreater', 0x69: 'Extends',
    0x70: 'PushThis', 0x71: 'PushGlobal', 0x72: 'ZeroVar', 0x73: 'PushTrue', 0x74: 'PushFalse',
    0x75: 'PushNull', 0x76: 'PushUndefined', 0x77: 'TraceStart',
}
# с аргументами: имя, выровнены ли аргументы по 4, разбор
OPS1 = {
    0x58: ('Nop58', False, 'u8'),   # всегда «58 4E» между объектом и GetNamedMember — по смыслу ничего не делает
    0x81: ('GotoFrame', True, 'u32'), 0x83: ('GetURL', True, 'str2'), 0x87: ('SetRegister', True, 'u32'),
    0x88: ('ConstantPool', True, 'pool'), 0x8A: ('WaitForFrame', True, 'u32x2'), 0x8B: ('SetTarget', True, 'str'),
    0x8C: ('GotoLabel', True, 'str'), 0x8D: ('WaitForFrame2', True, 'u32'), 0x8E: ('DefineFunction2', True, 'fn2'),
    0x8F: ('Try', True, 'try'), 0x94: ('With', True, 'u32'), 0x96: ('PushData', True, 'data'),
    0x99: ('BranchAlways', True, 's32'), 0x9A: ('GetURL2', False, ''), 0x9B: ('DefineFunction', True, 'fn'),
    0x9D: ('BranchIfTrue', True, 's32'), 0x9E: ('CallFrame', False, ''), 0x9F: ('GotoFrame2', True, 'u32'),
    0xA1: ('PushString', True, 'str'), 0xA2: ('PushConstant', False, 'u8'), 0xA3: ('PushWordConstant', False, 'u16'),
    0xA4: ('GetStringVar', True, 'str'), 0xA5: ('GetStringMember', True, 'str'), 0xA6: ('SetStringVar', True, 'str'),
    0xA7: ('SetStringMember', True, 'str'), 0xAE: ('PushValueOfVar', False, 'u8'), 0xAF: ('GetNamedMember', False, 'u8'),
    0xB0: ('CallNamedFuncPop', False, 'u8'), 0xB1: ('CallNamedFunc', False, 'u8'),
    0xB2: ('CallNamedMethodPop', False, 'u8'), 0xB3: ('CallNamedMethod', False, 'u8'),
    0xB4: ('PushFloat', False, 'f32'), 0xB5: ('PushByte', False, 'u8'), 0xB6: ('PushShort', False, 'u16'),  # со знаком
    0xB7: ('PushLong', False, 'u32'), 0xB8: ('BranchIfFalse', True, 's32'), 0xB9: ('PushRegister', False, 'u8'),
}
BRANCHES = ('BranchAlways', 'BranchIfTrue', 'BranchIfFalse')


def u32(b, o):
    return struct.unpack_from('>I', b, o)[0]


def cstr(b, o):
    return b[o:b.index(b'\0', o)].decode('latin1') if o else ''


class AptError(Exception):
    pass


class Instr:
    __slots__ = ('off', 'end', 'op', 'name', 'args', 'body', 'target')

    def __init__(self, off, op, name):
        self.off, self.op, self.name = off, op, name
        self.args, self.body, self.target, self.end = (), None, None, off + 1

    def __repr__(self):
        return f'{self.off:#x} {self.name} {self.args}'


class Code:
    """Разбор байткода: блок верхнего уровня кончается командой End (если дальше нет целей переходов),
    тело функции — по длине. Константы: const — таблица «Apt constant file» (строки)."""

    def __init__(self, data, const):
        self.d, self.const = data, const
        self.trace = None                                   # список для отладки: все разобранные команды

    def parse(self, start, end=None, pool=None):
        d = self.d
        out, p, targets = [], start, set()
        pool = pool if pool is not None else [None]
        while True:
            if end is not None and p >= end:
                break
            if p >= len(d):
                raise AptError(f'код вышел за данные @{p:#x}')
            op = d[p]
            ins = None
            if op in OPS0:
                ins = Instr(p, op, OPS0[op])
                p += 1
            elif op in OPS1:
                name, aligned, kind = OPS1[op]
                ins = Instr(p, op, name)
                p += 1
                if aligned:
                    p = (p + 3) & ~3
                if kind == 'u32':
                    ins.args = (u32(d, p),)
                    p += 4
                elif kind == 'u32x2':
                    ins.args = (u32(d, p), u32(d, p + 4))
                    p += 8
                elif kind == 's32':
                    off = struct.unpack_from('>i', d, p)[0]
                    p += 4
                    ins.target = p + off
                    ins.args = (off,)
                    targets.add(ins.target)
                elif kind == 'u8':
                    ins.args = (d[p],)
                    p += 1
                elif kind == 'u16':
                    ins.args = (struct.unpack_from('>H', d, p)[0],)
                    p += 2
                elif kind == 'f32':
                    ins.args = (struct.unpack_from('>f', d, p)[0],)
                    p += 4
                elif kind == 'str':
                    ins.args = (cstr(d, u32(d, p)),)
                    p += 4
                elif kind == 'str2':
                    ins.args = (cstr(d, u32(d, p)), cstr(d, u32(d, p + 4)))
                    p += 8
                elif kind == 'pool':
                    n, ptr = u32(d, p), u32(d, p + 4)
                    p += 8
                    pool[0] = [u32(d, ptr + 4 * k) for k in range(n)]
                    ins.args = (n,)
                elif kind == 'data':
                    n, ptr = u32(d, p), u32(d, p + 4)
                    p += 8
                    ins.args = tuple(u32(d, ptr + 4 * k) for k in range(n))
                elif kind == 'fn2':
                    nameptr, npar, regflags, parptr, size = struct.unpack_from('>IIIII', d, p)
                    p += 20 + 8                                   # + 8 байт 98 76 54 32 12 34 56 78
                    params = [(u32(d, parptr + 8 * k), cstr(d, u32(d, parptr + 8 * k + 4))) for k in range(npar)]
                    ins.args = (cstr(d, nameptr), params, (regflags >> 16) & 0xFF, regflags & 0xFFFF)
                    ins.body = self.parse(p, p + size, pool)
                    p += size
                elif kind == 'fn':
                    nameptr, npar, parptr, size = struct.unpack_from('>IIII', d, p)
                    p += 16 + 8
                    params = [cstr(d, u32(d, parptr + 4 * k)) for k in range(npar)]
                    ins.args = (cstr(d, nameptr), params)
                    ins.body = self.parse(p, p + size, pool)
                    p += size
                elif kind == 'try':
                    raise AptError(f'Try @{ins.off:#x} не поддержан')
                elif kind == '':
                    pass
            else:
                raise AptError(f'неизвестная команда {op:#04x} @{p:#x}')
            ins.end = p
            if ins.name in ('PushConstant', 'PushWordConstant', 'PushValueOfVar', 'GetNamedMember',
                            'CallNamedFuncPop', 'CallNamedFunc', 'CallNamedMethodPop', 'CallNamedMethod'):
                ins.args = (self.pool_str(pool[0], ins.args[0]),)
            elif ins.name == 'PushData':
                ins.args = tuple(self.const_str(k) for k in ins.args)
            out.append(ins)
            if self.trace is not None:
                self.trace.append(ins)
            if ins.name == 'End' and end is None and not any(t > ins.off for t in targets):
                break
        return out

    def const_str(self, k):
        return self.const[k] if 0 <= k < len(self.const) else f'<const {k}?>'

    def pool_str(self, pool, k):
        if pool is None:
            return self.const_str(k)
        return self.const_str(pool[k]) if k < len(pool) else f'<pool {k}?>'


# ---------------------------------------------------------------- ролик: все блоки кода

def load_movie(path):
    """(Apt Data, константы-строки, movie_off, febg.Apt) — разбор через febg."""
    import febg
    mv = febg.FeMovie.load(path)
    c = mv.apt.const
    n = u32(c, 0x18)
    consts = []
    for i in range(n):
        t, v = struct.unpack_from('>II', c, 0x20 + 8 * i)
        consts.append(cstr(c, v) if t == 1 else f'<{t}:{v}>')
    return mv, consts


def clip_actions(d, ptr):
    """Обработчики клипа (PlaceObject +0x3C): u32 число, u32 указатель на массив {u32 флаги событий,
    u32 код клавиши, u32 байткод}."""
    n, arr = u32(d, ptr), u32(d, ptr + 4)
    return [(u32(d, arr + 12 * k), u32(d, arr + 12 * k + 4), u32(d, arr + 12 * k + 8)) for k in range(n)]


CLIP_EVENTS = ['load', 'enterFrame', 'unload', 'mouseMove', 'mouseDown', 'mouseUp', 'keyDown', 'keyUp', 'data',
               'initialize', 'press', 'release', 'releaseOutside', 'rollOver', 'rollOut', 'dragOver', 'dragOut',
               'keyPress', 'construct']


def code_blocks(mv):
    """[(заголовок, смещение байткода)] — InitAction, Action кадров, обработчики клипов."""
    a = mv.apt
    d = a.data
    exports = {i: n for n, i in a.exports}
    out = []
    for ch in a.chars:
        cname = f'{ch.name} {ch.idx}' + (f' «{exports[ch.idx]}»' if ch.idx in exports else '')
        for fi, fr in enumerate(ch.frames):
            for it in fr:
                if it.type == 8:
                    tgt = it.sprite
                    out.append((f'InitAction спрайта {tgt}' + (f' «{exports[tgt]}»' if tgt in exports else '')
                                + f' (в {cname}, кадр {fi})', it.code))
                elif it.type == 1:
                    out.append((f'{cname}, кадр {fi}: Action', it.code))
                elif it.po and it.po.flags & 0x80 and it.po.actions:
                    for flags, key, code in clip_actions(d, it.po.actions):
                        evs = [e for b, e in enumerate(CLIP_EVENTS) if flags & (1 << b)]
                        out.append((f'{cname}, кадр {fi}: клип d={it.po.depth} «{it.po.name}» on({",".join(evs) or hex(flags)})', code))
    return out


# ---------------------------------------------------------------- «декомпиляция»: стек → выражения

PREC_ATOM, PREC_CALL, PREC_UNARY, PREC_MUL, PREC_ADD, PREC_SHIFT, PREC_REL, PREC_EQ = 0, 1, 2, 3, 4, 5, 6, 7
PREC_BAND, PREC_BXOR, PREC_BOR, PREC_AND, PREC_OR, PREC_COND, PREC_ASSIGN = 8, 9, 10, 11, 12, 13, 14

BINOPS = {'Add': ('+', PREC_ADD), 'Add2': ('+', PREC_ADD), 'Subtract': ('-', PREC_ADD), 'Multiply': ('*', PREC_MUL),
          'Divide': ('/', PREC_MUL), 'Modulo': ('%', PREC_MUL), 'Equals': ('==', PREC_EQ), 'Equals2': ('==', PREC_EQ),
          'StrictEquals': ('===', PREC_EQ), 'Less': ('<', PREC_REL), 'Less2': ('<', PREC_REL),
          'Greater': ('>', PREC_REL), 'And': ('&&', PREC_AND), 'Or': ('||', PREC_OR), 'StringEquals': ('eq', PREC_EQ),
          'StringLess': ('lt', PREC_REL), 'StringGreater': ('gt', PREC_REL), 'StringAdd': ('add', PREC_ADD),
          'BitAnd': ('&', PREC_BAND), 'BitOr': ('|', PREC_BOR), 'BitXor': ('^', PREC_BXOR),
          'BitLShift': ('<<', PREC_SHIFT), 'BitRShift': ('>>', PREC_SHIFT), 'BitURShift': ('>>>', PREC_SHIFT),
          'InstanceOf': ('instanceof', PREC_REL)}


class E:
    """Выражение: текст, приоритет, литерал (для имён и счётчиков аргументов)."""
    __slots__ = ('s', 'p', 'lit', 'call')

    def __init__(self, s, p=PREC_ATOM, lit=None, call=False):
        self.s, self.p, self.lit, self.call = s, p, lit, call

    def __str__(self):
        return self.s

    def wrap(self, p):
        return self.s if self.p <= p else f'({self.s})'


def lit_str(v):
    return E(json.dumps(v, ensure_ascii=False), lit=v)


IDENT = re.compile(r'^[A-Za-z_$][\w$]*$')


def member(obj, name):
    if name.lit is not None and isinstance(name.lit, str) and IDENT.match(name.lit):
        return E(f'{obj.wrap(PREC_CALL)}.{name.lit}', PREC_CALL)
    return E(f'{obj.wrap(PREC_CALL)}[{name}]', PREC_CALL)


def varname(name):
    return E(name.lit, lit=None) if isinstance(name.lit, str) and IDENT.match(name.lit) else E(f'eval({name})', PREC_CALL)


class Decompiler:
    def __init__(self, raw=False):
        self.raw = raw

    def func_header(self, ins):
        if ins.name == 'DefineFunction2':
            fname, params, nregs, flags = ins.args
            regs = {}
            r = 1
            for bit, nm in ((0x01, 'this'), (0x04, 'arguments'), (0x10, 'super'), (0x40, '_root'),
                            (0x80, '_parent'), (0x100, '_global')):
                if flags & bit:
                    regs[r] = nm
                    r += 1
            for reg, pn in params:
                if reg:
                    regs[reg] = pn
            return fname, [pn for _, pn in params], regs
        fname, params = ins.args
        return fname, params, {}

    def func_text(self, ins, indent):
        fname, params, regs = self.func_header(ins)
        body = self.block(ins.body, indent + 1, regs)
        pad = '    ' * indent
        return f'function {fname}({", ".join(params)}) {{\n' + '\n'.join(body) + f'\n{pad}}}'

    def block(self, instrs, indent=0, regs=None):
        regs = dict(regs or {})
        pad = '    ' * indent
        if self.raw:
            lines = []
            for ins in instrs:
                a = ''
                if ins.target is not None:
                    a = f'→ {ins.target:#x}'
                elif ins.name in ('DefineFunction2', 'DefineFunction'):
                    fname, params, rg = self.func_header(ins)
                    a = f'{fname}({", ".join(params)}) рег.{rg}'
                elif ins.args:
                    a = ', '.join(json.dumps(x, ensure_ascii=False) if isinstance(x, str) else str(x) for x in ins.args)
                lines.append(f'{pad}{ins.off:06x}  {ins.name} {a}')
                if ins.body is not None:
                    lines += self.block(ins.body, indent + 1, self.func_header(ins)[2])
            return lines

        targets = {i.target for i in instrs if i.target is not None}
        lines = []
        st = []
        merges = {}        # метка → (вид, снимок стека)

        def emit(s):
            lines.append(pad + s)

        def pop():
            return st.pop() if st else E('/*пусто*/')

        def popn():
            n = pop()
            k = n.lit if isinstance(n.lit, int) else 0
            return [pop() for _ in range(k)]

        def reg(n):
            return E(regs.get(n, f'r{n}'))

        for idx, ins in enumerate(instrs):
            if ins.off in targets:
                m = merges.pop(ins.off, None)
                if m and len(st) == len(m[1]) and st:
                    kind, snap, cond = m
                    b = st.pop()
                    if kind in ('&&', '||'):
                        st.append(E(f'{snap[-1].wrap(PREC_OR)} {kind} {b.wrap(PREC_OR)}', PREC_OR if kind == '||' else PREC_AND))
                    else:                                      # ?: — снимок стека «ветки да» + условие
                        st.append(E(f'{cond.wrap(PREC_COND)} ? {snap[-1].wrap(PREC_COND)} : {b.wrap(PREC_COND)}', PREC_COND))
                else:
                    if st:
                        emit(f'// стек на метке: {", ".join(map(str, st))}')
                lines.append(f'{pad[:-2] if pad else ""}L{ins.off:x}:')
            n = ins.name
            a = ins.args
            if n == 'End':
                if idx != len(instrs) - 1:
                    emit('end;')
                continue
            if n in ('PushConstant', 'PushWordConstant', 'PushString'):
                st.append(lit_str(a[0]))
            elif n == 'PushData':
                st.extend(lit_str(x) for x in a)
            elif n in ('PushByte', 'PushShort', 'PushLong'):
                v = a[0]
                if n == 'PushByte' and v >= 0x80:                # байт со знаком: 255 = −1 (проверено в игре)
                    v -= 0x100
                if n == 'PushShort' and v >= 0x8000:
                    v -= 0x10000
                if n == 'PushLong' and v >= 0x80000000:
                    v -= 1 << 32
                st.append(E(str(v), lit=v))
            elif n == 'PushFloat':
                v = a[0]
                st.append(E(repr(round(v, 6)) if v != int(v) else str(int(v)), lit=v))
            elif n == 'PushZero':
                st.append(E('0', lit=0))
            elif n == 'PushOne':
                st.append(E('1', lit=1))
            elif n == 'PushTrue':
                st.append(E('true'))
            elif n == 'PushFalse':
                st.append(E('false'))
            elif n == 'PushNull':
                st.append(E('null'))
            elif n == 'PushUndefined':
                st.append(E('undefined'))
            elif n == 'PushThis':
                st.append(E('this'))
            elif n == 'PushGlobal':
                st.append(E('_global'))
            elif n == 'PushRegister':
                st.append(reg(a[0]))
            elif n == 'PushValueOfVar':
                st.append(E(a[0]) if IDENT.match(a[0]) else E(f'eval({json.dumps(a[0])})'))
            elif n == 'GetStringVar':
                st.append(E(a[0]))
            elif n == 'GetNamedMember' or n == 'GetStringMember':
                o = pop()
                st.append(member(o, lit_str(a[0])))
            elif n == 'GetVariable':
                st.append(varname(pop()))
            elif n == 'GetMember':
                nm, o = pop(), pop()
                st.append(member(o, nm))
            elif n == 'SetVariable':
                v, nm = pop(), pop()
                emit(f'{varname(nm)} = {v};')
            elif n == 'SetStringVar':
                emit(f'{a[0]} = {pop()};')
            elif n == 'SetMember':
                v, nm, o = pop(), pop(), pop()
                emit(f'{member(o, nm)} = {v};')
            elif n == 'SetStringMember':
                v, o = pop(), pop()
                emit(f'{member(o, lit_str(a[0]))} = {v};')
            elif n == 'DefineLocal':
                v, nm = pop(), pop()
                emit(f'var {varname(nm)} = {v};')
            elif n == 'DefineLocal2':
                emit(f'var {varname(pop())};')
            elif n == 'SetRegister':
                if st:
                    top = st[-1]
                    nm = regs.get(a[0], f'r{a[0]}')
                    nxt = instrs[idx + 1].name if idx + 1 < len(instrs) else ''
                    emit(f'{nm} = {top};')
                    st[-1] = E(nm)
                    if nxt == 'Pop':
                        pass
            elif n in ('CallFunction', 'CallFunc', 'CallFuncPop', 'CallNamedFunc', 'CallNamedFuncPop'):
                if n.startswith('CallNamed'):
                    fn = E(a[0])
                else:
                    fn = varname(pop())
                args = popn()
                e = E(f'{fn}({", ".join(map(str, args))})', PREC_CALL, call=True)
                if n.endswith('Pop'):
                    emit(f'{e};')
                else:
                    st.append(e)
            elif n in ('CallMethod', 'CallMethodEA', 'CallMethodPop', 'CallNamedMethod', 'CallNamedMethodPop'):
                if n.startswith('CallNamed'):
                    mname = lit_str(a[0])
                else:
                    mname = pop()
                o = pop()
                args = popn()
                if mname.s in ('undefined', '""'):
                    head = o.wrap(PREC_CALL)
                else:
                    head = member(o, mname).s
                e = E(f'{head}({", ".join(map(str, args))})', PREC_CALL, call=True)
                if n.endswith('Pop'):
                    emit(f'{e};')
                else:
                    st.append(e)
            elif n == 'NewObject':
                fn = varname(pop())
                args = popn()
                st.append(E(f'new {fn}({", ".join(map(str, args))})', PREC_CALL, call=True))
            elif n == 'NewMethod':
                mname, o = pop(), pop()
                args = popn()
                head = o.wrap(PREC_CALL) if mname.s in ('undefined', '""') else member(o, mname).s
                st.append(E(f'new {head}({", ".join(map(str, args))})', PREC_CALL, call=True))
            elif n == 'InitArray':
                args = popn()
                st.append(E(f'[{", ".join(map(str, args))}]'))
            elif n == 'InitObject':
                cnt = pop()
                k = cnt.lit if isinstance(cnt.lit, int) else 0
                items = []
                for _ in range(k):
                    v, nm = pop(), pop()
                    items.append(f'{nm.lit if isinstance(nm.lit, str) else nm}: {v}')
                st.append(E('{' + ', '.join(items) + '}'))
            elif n in BINOPS:
                b, x = pop(), pop()
                sym, p = BINOPS[n]
                st.append(E(f'{x.wrap(p)} {sym} {b.wrap(p - 1)}', p))
            elif n == 'Not':
                x = pop()
                st.append(E(f'!{x.wrap(PREC_UNARY)}', PREC_UNARY))
            elif n == 'Increment':
                st.append(E(f'{pop().wrap(PREC_ADD)} + 1', PREC_ADD))
            elif n == 'Decrement':
                st.append(E(f'{pop().wrap(PREC_ADD)} - 1', PREC_ADD))
            elif n in ('ToNumber', 'ToString', 'ToInteger', 'TypeOf', 'TargetPath', 'StringLength',
                       'MBStringLength', 'CharToAscii', 'AsciiToChar', 'MBCharToAscii', 'MBAsciiToChar', 'RandomNumber'):
                fnm = {'ToNumber': 'Number', 'ToString': 'String', 'ToInteger': 'int', 'TypeOf': 'typeof',
                       'TargetPath': 'targetPath', 'StringLength': 'length', 'MBStringLength': 'mblength',
                       'CharToAscii': 'ord', 'AsciiToChar': 'chr', 'MBCharToAscii': 'mbord', 'MBAsciiToChar': 'mbchr',
                       'RandomNumber': 'random'}[n]
                st.append(E(f'{fnm}({pop()})', PREC_CALL))
            elif n in ('StringExtract', 'MBStringExtract'):
                c, i, s = pop(), pop(), pop()
                st.append(E(f'substring({s}, {i}, {c})', PREC_CALL))
            elif n == 'GetTime':
                st.append(E('getTimer()', PREC_CALL))
            elif n == 'PushDuplicate':
                st.append(st[-1] if st else E('/*пусто*/'))
            elif n == 'StackSwap':
                if len(st) >= 2:
                    st[-1], st[-2] = st[-2], st[-1]
            elif n == 'Pop':
                x = pop()
                if x.call or x.s.startswith('/*'):
                    emit(f'{x};')
                elif x.lit is None and x.s not in ('this', '_global') and not IDENT.match(x.s) and '.' not in x.s:
                    emit(f'{x};')
            elif n == 'Return':
                emit(f'return {pop()};')
            elif n == 'Delete':
                nm, o = pop(), pop()
                st.append(E(f'delete {member(o, nm)}', PREC_UNARY, call=True))
            elif n == 'Delete2':
                st.append(E(f'delete {varname(pop())}', PREC_UNARY, call=True))
            elif n == 'Extends':
                sup, sub = pop(), pop()
                emit(f'{sub} extends {sup};')
            elif n == 'ImplementsOp':
                o = pop()
                ifs = popn()
                emit(f'{o} implements {", ".join(map(str, ifs))};')
            elif n == 'CastOp':
                o, t = pop(), pop()
                st.append(E(f'cast<{t}>({o})', PREC_CALL))
            elif n in ('Enumerate', 'Enumerate2'):
                o = pop()
                emit(f'for (… in {o}) — перебор (имена на стеке до null)')
                st.append(E(f'nextName({o})', PREC_CALL))
            elif n == 'Throw':
                emit(f'throw {pop()};')
            elif n == 'Trace':
                emit(f'trace({pop()});')
            elif n in ('Stop', 'Play', 'NextFrame', 'PrevFrame', 'StopSounds', 'ToggleQuality'):
                emit(f'{n[0].lower() + n[1:]}();')
            elif n == 'GotoFrame':
                emit(f'gotoFrame({a[0]});')
            elif n == 'GotoLabel':
                emit(f'gotoLabel({json.dumps(a[0])});')
            elif n == 'GotoFrame2':
                emit(f'gotoFrame2({pop()}, play={a[0] & 1});')
            elif n == 'SetTarget':
                emit(f'setTarget({json.dumps(a[0])});')
            elif n == 'SetTarget2':
                emit(f'setTarget({pop()});')
            elif n == 'GetURL':
                emit(f'getURL({json.dumps(a[0])}, {json.dumps(a[1])});')
            elif n == 'GetURL2':
                tgt, url = pop(), pop()
                emit(f'getURL2({url}, {tgt});')
            elif n == 'GetProperty':
                i, t = pop(), pop()
                st.append(E(f'getProperty({t}, {i})', PREC_CALL))
            elif n == 'SetProperty':
                v, i, t = pop(), pop(), pop()
                emit(f'setProperty({t}, {i}, {v});')
            elif n == 'CloneSprite':
                dpt, tgt, src = pop(), pop(), pop()
                emit(f'duplicateMovieClip({src}, {tgt}, {dpt});')
            elif n == 'RemoveSprite':
                emit(f'removeMovieClip({pop()});')
            elif n in ('ConstantPool', 'Nop58'):
                pass
            elif n in ('DefineFunction2', 'DefineFunction'):
                txt = self.func_text(ins, indent)
                fname = ins.args[0]
                if fname:
                    emit(txt + ';')
                else:
                    st.append(E(txt))
            elif n in BRANCHES:
                tgt = f'L{ins.target:x}'
                if n == 'BranchAlways':
                    nxt = instrs[idx + 1] if idx + 1 < len(instrs) else None
                    m = merges.get(nxt.off) if nxt else None
                    if m and m[0] == '?' and len(st) == len(m[1]) + 1:
                        snap = st[:]
                        st[:] = m[1]
                        merges.pop(nxt.off)
                        merges[ins.target] = ('?:', snap, m[2])
                        continue
                    emit(f'goto {tgt};')
                    continue
                cond = pop()
                prev = instrs[idx - 1].name if idx else ''
                prev2 = instrs[idx - 2].name if idx > 1 else ''
                if prev == 'PushDuplicate' or (prev == 'Not' and prev2 == 'PushDuplicate'):
                    neg = (prev == 'Not')
                    kind = '||' if (n == 'BranchIfTrue') != neg else '&&'
                    merges[ins.target] = (kind, st[:], None)
                    continue
                if n == 'BranchIfTrue':
                    c = cond
                    # «if (!x) goto» — обычно цикл/условие; ternary: if (!c) goto Lelse; a; goto Lend; Lelse: b; Lend:
                    merges.setdefault(ins.target, ('?', st[:], E(c.s[1:], c.p) if c.s.startswith('!') and c.p == PREC_UNARY else E(f'!{c.wrap(PREC_UNARY)}', PREC_UNARY)))
                    emit(f'if ({c}) goto {tgt};')
                else:
                    merges.setdefault(ins.target, ('?', st[:], cond))
                    emit(f'if (!{cond.wrap(PREC_UNARY)}) goto {tgt};')
            elif n == 'With':
                emit(f'with ({pop()}) {{ … {a[0]} байт }}')
            else:
                emit(f'/* {n} {a} */')
        if st:
            emit(f'// стек в конце: {", ".join(map(str, st))}')
        return lines


# ---------------------------------------------------------------- команды

def disassemble(path, raw=False, char=None, out=sys.stdout):
    mv, consts = load_movie(path)
    code = Code(mv.apt.data, consts)
    dec = Decompiler(raw)
    for title, off in code_blocks(mv):
        if char is not None and f' {char} ' not in title + ' ':
            continue
        print(f'// ===== {title} @{off:#x}', file=out)
        try:
            instrs = code.parse(off)
            for line in dec.block(instrs):
                print(line, file=out)
        except AptError as e:
            print(f'// ОШИБКА: {e}', file=out)
        print(file=out)


def iter_functions(instrs, path=()):
    for ins in instrs:
        if ins.body is not None:
            yield ins, path
            yield from iter_functions(ins.body, path + (ins,))


def cmd_classes(path):
    """Класс.prototype.Метод = function(…) и Класс.Статический = function — по декомпилированному тексту."""
    mv, consts = load_movie(path)
    code = Code(mv.apt.data, consts)
    dec = Decompiler()
    rx = re.compile(r'^\s*([\w.$\[\]"]+) = function \(?([^)]*)\)')
    for title, off in code_blocks(mv):
        try:
            lines = dec.block(code.parse(off))
        except AptError:
            continue
        for ln in lines:
            m = re.match(r'^(\s*)(\S.*?) = function ([\w$]*)\(([^)]*)\) \{', ln)
            if m and len(m.group(1)) <= 4:
                print(f'{m.group(2)}({m.group(4)})')


def cmd_calls(path):
    """Что ролик берёт у глобальных объектов: _global.X…, gXxx.Метод(, ION_*.Метод(."""
    mv, consts = load_movie(path)
    code = Code(mv.apt.data, consts)
    dec = Decompiler()
    seen = {}
    rx = re.compile(r'\b((?:_global\.)?(?:g[A-Z]\w*|ION_\w+|_root|_level0|cafe|EA_ZONE)(?:\.\w+)+)(\()?')
    for title, off in code_blocks(mv):
        try:
            lines = dec.block(code.parse(off))
        except AptError:
            continue
        for ln in lines:
            for m in rx.finditer(ln):
                k = m.group(1) + ('()' if m.group(2) else '')
                seen[k] = seen.get(k, 0) + 1
    for k in sorted(seen):
        print(f'{seen[k]:4d}  {k}')


def patch_bytes(src, dst, edits, log=print):
    """Правка байткода на месте (длина записи Apt Data не меняется): edits — [(смещение, старые, новые)],
    смещения — в распакованной Apt Data (как в dis --raw). Старые байты сверяются. Запись «0» сжимается
    обратно RefPack, если была сжата; BIGF собирается как у EA (febg.build_bigf)."""
    import febg
    mv = febg.FeMovie.load(src)
    d, packed = mv.raw['0']
    d = bytearray(d)
    for off, old, new in edits:
        if len(old) != len(new):
            raise ValueError(f'@{off:#x}: длина {len(old)} → {len(new)} — только правка той же длины')
        if bytes(d[off:off + len(old)]) != old:
            raise ValueError(f'@{off:#x}: там {d[off:off + len(old)].hex()}, ждали {old.hex()}')
        d[off:off + len(new)] = new
        log(f'  @{off:#x}: {old.hex()} → {new.hex()}')
    big = ph.Bigf(mv.big.raw)
    big.put('0', ph.refpack_compress(bytes(d)) if packed else bytes(d))
    out = febg.build_bigf(big)
    febg.FeMovie(out)                                            # разбирается обратно
    os.makedirs(os.path.dirname(os.path.abspath(dst)), exist_ok=True)
    open(dst, 'wb').write(out)
    return out


def cmd_patch(args):
    """patch IN.big OUT.big СМЕЩЕНИЕ:СТАРЫЕ=НОВЫЕ… (hex)"""
    src, dst, specs = args[0], args[1], args[2:]
    edits = []
    for s in specs:
        off, rest = s.split(':', 1)
        old, new = rest.split('=', 1)
        edits.append((int(off, 16), bytes.fromhex(old), bytes.fromhex(new)))
    patch_bytes(src, dst, edits)
    print(f'→ {dst}')


# ---------------------------------------------------------------- пересадка символа между роликами

CHAR_SIZE = {1: 0x24, 5: 0x1C, 7: 0x14}                      # Shape, Sprite, Image (Apt 1:7:4 / 1:8:4)


def _deps(apt, root):
    """Символ и всё, что он тянет: Sprite → символы PlaceObject, Shape → Image (растр и заливки)."""
    import febg
    order, seen = [], set()

    def visit(i):
        if i in seen:
            return
        seen.add(i)
        ch = apt.chars[i]
        if ch.type == 5:
            for fr in ch.frames:
                for it in fr:
                    if it.type in (1, 8):
                        raise AptError(f'символ {i}: в кадрах есть код — пересадка не поддержана')
                    if it.po and it.po.flags & febg.PO_CHAR:
                        visit(it.po.char)
        elif ch.type == 1:
            if ch.image:
                visit(ch.image)
        elif ch.type != 7:
            raise AptError(f'символ {i}: тип {ch.name} — пересадка не поддержана')
        order.append(i)
    visit(root)
    return order


def graft(dst_path, src_path, src_char, export, out_path, log=print):
    """Пересадить символ src_char ролика src (со всей зависимой графикой: спрайты, фигуры, текстуры) в ролик
    dst и направить на него экспорт export (имя связи для attachMovie; если такого экспорта нет — добавить).
    Старые символы dst не трогаются: новые дописываются в конец Apt Data, таблица символов и (при
    добавлении) экспорта копируются туда же с новой длиной; геометрия и текстуры — новыми записями BIGF."""
    import febg
    dmv, smv = febg.FeMovie.load(dst_path), febg.FeMovie.load(src_path)
    da, sa = dmv.apt, smv.apt
    sd = sa.data
    d = bytearray(da.data)
    order = _deps(sa, src_char)
    base = len(da.chars)
    remap = {old: base + k for k, old in enumerate(order)}

    def align():
        while len(d) % 4:
            d.append(0)

    def put_str(text):
        align()
        p = len(d)
        d.extend(text.encode('latin1') + b'\0')
        return p

    newptr = {}
    for old in order:
        ch = sa.chars[old]
        size = CHAR_SIZE[ch.type]
        raw = bytearray(sd[ch.off:ch.off + size])
        new = remap[old]
        if ch.type == 7:
            struct.pack_into('>I', raw, 0x10, new)            # номер текстуры = номер символа
        elif ch.type == 1:
            struct.pack_into('>I', raw, 0x08, remap.get(ch.image, 0) if ch.image else 0)
            struct.pack_into('>I', raw, 0x20, new)            # номер геометрии = номер символа
        elif ch.type == 5:
            # кадры: на каждый — массив указателей на элементы; элементы — PlaceObject/RemoveObject
            frames = []
            for fr in ch.frames:
                ptrs = []
                for it in fr:
                    if it.po:
                        po = bytearray(sd[it.off:it.off + 0x40])
                        if it.po.flags & febg.PO_CHAR:
                            struct.pack_into('>I', po, 0x0C, remap[it.po.char])
                        if it.po.flags & febg.PO_NAME and it.po.name:
                            struct.pack_into('>I', po, 0x34, put_str(it.po.name))
                        if it.po.flags & febg.PO_ACTIONS:
                            raise AptError('обработчики клипа не поддержаны')
                        align()
                        ptrs.append(len(d))
                        d.extend(po)
                    elif it.type == 4:                         # RemoveObject (8 байт)
                        align()
                        ptrs.append(len(d))
                        d.extend(sd[it.off:it.off + 8])
                    else:
                        raise AptError(f'элемент кадра типа {it.type} не поддержан')
                align()
                arr = len(d)
                for p in ptrs:
                    d.extend(struct.pack('>I', p))
                frames.append((len(ptrs), arr if ptrs else 0))
            align()
            ftab = len(d)
            for n, p in frames:
                d.extend(struct.pack('>II', n, p))
            struct.pack_into('>I', raw, 0x10, len(frames))
            struct.pack_into('>I', raw, 0x14, ftab)
            struct.pack_into('>I', raw, 0x18, 0)
        align()
        newptr[new] = len(d)
        d.extend(raw)
    # таблица символов: старые + новые
    m = da.movie_off
    nchar, cp = struct.unpack_from('>II', d, m + 0x1C)
    align()
    tab = len(d)
    for i in range(nchar):
        d.extend(struct.pack('>I', struct.unpack_from('>I', d, cp + 4 * i)[0]))
    for i in range(base, base + len(order)):
        d.extend(struct.pack('>I', newptr[i]))
    struct.pack_into('>II', d, m + 0x1C, nchar + len(order), tab)
    # экспорт
    ne, ep = struct.unpack_from('>II', d, m + 0x38)
    target = remap[src_char]
    hit = [k for k in range(ne) if cstr(d, struct.unpack_from('>I', d, ep + 8 * k)[0]).lower() == export.lower()]
    if hit:
        for k in hit:
            struct.pack_into('>I', d, ep + 8 * k + 4, target)
    else:
        name = put_str(export)
        align()
        etab = len(d)
        for k in range(ne):
            d.extend(d[ep + 8 * k:ep + 8 * k + 8])
        d.extend(struct.pack('>II', name, target))
        struct.pack_into('>II', d, m + 0x38, ne + 1, etab)
    # записи BIGF: геометрия (номер Image в заливках — новый) и текстуры
    big = ph.Bigf(dmv.big.raw)
    names = [n for n, _ in big.entries]
    geo, tex = [], []
    for old in order:
        ch = sa.chars[old]
        key = str(old + 1)
        if ch.type == 1 and key in smv.raw:
            g, packed = smv.raw[key]
            g = bytearray(g)
            for mesh in smv.geometry.get(old, []):
                for fl in mesh:
                    if fl.image:
                        struct.pack_into('>I', g, fl.off + 0x14, remap[fl.image])
            geo.append((str(remap[old] + 1), ph.refpack_compress(bytes(g)) if packed else bytes(g)))
        elif ch.type == 7 and key in smv.raw:
            tex.append((str(remap[old] + 1), smv.big.get(key)))
    sg1 = names.index('sg1') if 'sg1' in names else len(names)
    entries = big.entries[:sg1] + [list(x) for x in geo] + big.entries[sg1:]
    names = [n for n, _ in entries]
    sg2 = names.index('sg2') if 'sg2' in names else len(names)
    entries = entries[:sg2] + [list(x) for x in tex] + entries[sg2:]
    big.entries = entries
    _, packed0 = dmv.raw['0']
    big.put('0', ph.refpack_compress(bytes(d)) if packed0 else bytes(d))
    data = febg.build_bigf(big)
    febg.FeMovie(data)
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    open(out_path, 'wb').write(data)
    log(f'  {os.path.basename(src_path)}:{src_char} → {os.path.basename(dst_path)}: символы {base}…{base + len(order) - 1} '
        f'({", ".join(sa.chars[o].name for o in order)}), экспорт «{export}» → {target}; '
        f'геометрия {len(geo)}, текстуры {len(tex)}')
    return remap


def cmd_graft(args):
    """graft DST.big SRC.big OUT.big --char N --export ИМЯ"""
    graft(args[0], args[1], int(args[args.index('--char') + 1]), args[args.index('--export') + 1], args[2])


def index_dir(game=None):
    return os.path.join(game or ph.game_dir(), 'work', 'menu12', 'index')


ROOTS = {'nhl13': [('boot', ('extracted', 'big', 'boot')), ('cache', ('extracted', 'big', 'cache'))],
         'nhl12': [('boot', ('other', 'nhl12', 'big', 'boot')), ('cache', ('other', 'nhl12', 'big', 'cache'))]}


def _index_one(job):
    arch, root, p = job
    rel = os.path.relpath(p, root).replace('\\', '/')
    try:
        big = ph.Bigf(open(p, 'rb').read())
        names = [n for n, _ in big.entries]
        if '0' not in names or '1' not in names:
            return rel, None
        data, const = ph.unpack_entry(big.get('0'))[0], ph.unpack_entry(big.get('1'))[0]
        if data[:8] != b'Apt Data' or const[:17] != b'Apt constant file':
            return rel, None
        strs = [cstr(const, struct.unpack_from('>II', const, 0x20 + 8 * i)[1]) for i in range(u32(const, 0x18))]
        m = u32(const, 0x14)
        ni, ip, ne, ep = struct.unpack_from('>IIII', data, m + 0x30)
        return rel, {'arch': arch, 'ver': data[9:data.index(b'\x1a')].decode('latin1'),
                     'imports': [(cstr(data, u32(data, ip + 16 * k)), cstr(data, u32(data, ip + 16 * k + 4))) for k in range(ni)],
                     'exports': [cstr(data, u32(data, ep + 8 * k)) for k in range(ne)], 'const': strs}
    except Exception as e:                                  # noqa: BLE001
        return rel, {'arch': arch, 'error': str(e)}


def cmd_index(games):
    import multiprocessing as mp
    out = index_dir()
    os.makedirs(out, exist_ok=True)
    for game in games:
        jobs = []
        for arch, parts in ROOTS[game]:
            root = os.path.join(ph.game_dir(), *parts)
            for dp, _, fn in os.walk(os.path.join(root, 'fe')):
                jobs += [(arch, root, os.path.join(dp, f)) for f in fn if f.endswith('.big')]
        idx = {}
        with mp.Pool(max(1, (os.cpu_count() or 2) - 2)) as pool:
            for rel, r in pool.imap_unordered(_index_one, jobs, chunksize=16):
                if r is not None:
                    idx[rel] = r
        json.dump(idx, open(os.path.join(out, game + '.json'), 'w', encoding='utf-8'), ensure_ascii=False)
        print(f'{game}: {len(idx)} роликов → {out}')


def cmd_grep(args):
    games = ['nhl12', 'nhl13']
    if '--game' in args:
        g = args.pop(args.index('--game') + 1)
        args.remove('--game')
        games = [g]
    mode = 'const'
    for flag, m in (('--exports', 'exports'), ('--imports', 'imports')):
        if flag in args:
            args.remove(flag)
            mode = m
    exact = '--exact' in args
    if exact:
        args.remove('--exact')
    for game in games:
        p = os.path.join(index_dir(), game + '.json')
        if not os.path.exists(p):
            sys.exit(f'нет индекса {p}: python feapt.py index')
        idx = json.load(open(p, encoding='utf-8'))
        for pat in args:
            rx = re.compile(('^' + re.escape(pat) + '$') if exact else pat, re.I)
            hits = []
            for rel, r in sorted(idx.items()):
                vals = r.get(mode, [])
                if mode == 'imports':
                    vals = [f'{a}:{b}' for a, b in vals]
                m = sorted({v for v in vals if rx.search(v)})
                if m:
                    hits.append((rel, r.get('arch'), m))
            print(f'== {game} {mode} /{pat}/: {len(hits)}')
            for rel, arch, m in hits:
                print(f'  [{arch}] {rel}: {m[:8]}{" …" if len(m) > 8 else ""}')


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    cmd, args = sys.argv[1], sys.argv[2:]
    if cmd == 'dis':
        char = int(args[args.index('--char') + 1]) if '--char' in args else None
        disassemble(args[0], raw='--raw' in args, char=char)
    elif cmd == 'classes':
        cmd_classes(args[0])
    elif cmd == 'calls':
        cmd_calls(args[0])
    elif cmd == 'index':
        games = [args[args.index('--game') + 1]] if '--game' in args else ['nhl12', 'nhl13']
        cmd_index(games)
    elif cmd == 'grep':
        cmd_grep(args)
    elif cmd == 'patch':
        cmd_patch(args)
    elif cmd == 'graft':
        cmd_graft(args)
    else:
        sys.exit(__doc__)


if __name__ == '__main__':
    main()
