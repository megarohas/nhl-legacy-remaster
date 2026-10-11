"""Компилятор подмножества ActionScript 1/2 в байткод Apt (Flash EA: NHL 13, NHL Legacy) и сборка блока кода.

Нужен, когда правкой «той же длины» (feapt.py patch) не обойтись: новый код дописывается в конец Apt Data
отдельным блоком — Action кадра или InitAction. Имена — строками PushString в Apt Data (без ConstantPool: пул
блока ничей, старый код его не видит), функции — DefineFunction2, как у компилятора EA: _global (у методов
ещё this) — в регистрах, параметры и var — в регистрах, arguments/super подавлены.

Язык:
    function имя(a, b) { … }          на верхнем уровне блока — определить функцию в области кадра (клипа)
    var x = выражение;   x = …;   a.b = …;   a[i] = …;
    if (…) { … } else if (…) { … } else { … }
    while (…) { … }
    return выражение;   return;
    выражение;                         вызов и т. п.;  trace(выражение);
Выражения: 12, -3, 1.5, "строка", true, false, null, undefined, this, _global, имя, a.b, a[b], f(…), a.m(…),
    new X(…), new a.B(…), function (x) { … }, !x, -x, * / %, + -, < > <= >=, == != === !==, &&, ||, c ? a : b, (…)
Замыканий нет: вложенная функция не видит var и параметров внешней (они в регистрах) — компилятор это запрещает.

    python aptc.py demo               пример: исходник → байткод → разбор feapt (дизассемблер и «декомпилятор»)

Только стандартная библиотека. Разбор и проверка — tools/feapt.py; формат — docs/fe-menu.md §7.
"""
import re, struct, sys

ALIGNED = {'SetRegister', 'PushString', 'BranchAlways', 'BranchIfTrue', 'DefineFunction2'}
OPCODE = {
    'End': 0x00, 'Stop': 0x07, 'Subtract': 0x0B, 'Multiply': 0x0C, 'Divide': 0x0D, 'Not': 0x12, 'Pop': 0x17,
    'GetVariable': 0x1C, 'SetVariable': 0x1D, 'Trace': 0x26, 'CallFunction': 0x3D, 'Return': 0x3E, 'Modulo': 0x3F,
    'NewObject': 0x40, 'InitArray': 0x42, 'Add2': 0x47, 'Less2': 0x48, 'Equals2': 0x49, 'PushDuplicate': 0x4C,
    'GetMember': 0x4E, 'SetMember': 0x4F, 'CallMethod': 0x52, 'NewMethod': 0x53, 'PushZero': 0x59, 'PushOne': 0x5A,
    'StrictEquals': 0x66, 'Greater': 0x67, 'PushThis': 0x70, 'PushGlobal': 0x71, 'PushTrue': 0x73, 'PushFalse': 0x74,
    'PushNull': 0x75, 'PushUndefined': 0x76,
    'SetRegister': 0x87, 'DefineFunction2': 0x8E, 'BranchAlways': 0x99, 'BranchIfTrue': 0x9D, 'PushString': 0xA1,
    'PushFloat': 0xB4, 'PushByte': 0xB5, 'PushShort': 0xB6, 'PushLong': 0xB7, 'PushRegister': 0xB9,
}
FN2_MAGIC = bytes.fromhex('9876543212345678')
# флаги DefineFunction2 (как SWF): регистры предзагрузки идут по порядку с 1 — this, arguments, super, _root, _parent, _global
PRELOAD_THIS, SUPPRESS_THIS, SUPPRESS_ARGUMENTS, SUPPRESS_SUPER, PRELOAD_GLOBAL = 0x01, 0x02, 0x08, 0x20, 0x100


class AptcError(Exception):
    pass


# ---------------------------------------------------------------- лексер

TOKEN = re.compile(r'''
 (?P<ws>[ \t\r\n]+|//[^\n]*|/\*.*?\*/)
|(?P<num>0x[0-9A-Fa-f]+|\d+\.\d*|\.\d+|\d+)
|(?P<str>"(?:[^"\\\n]|\\.)*"|'(?:[^'\\\n]|\\.)*')
|(?P<id>[A-Za-z_$][A-Za-z0-9_$]*)
|(?P<op>===|!==|==|!=|<=|>=|&&|\|\||[{}()\[\];,.?:=!<>+\-*/%])
''', re.S | re.X)
ESC = {'n': '\n', 't': '\t', 'r': '\r', '\\': '\\', '"': '"', "'": "'", '0': '\0'}
KEYWORDS = {'function', 'var', 'if', 'else', 'while', 'return', 'new', 'true', 'false', 'null', 'undefined', 'this'}


def tokenize(src):
    out, pos, line = [], 0, 1
    while pos < len(src):
        m = TOKEN.match(src, pos)
        if not m:
            raise AptcError(f'строка {line}: непонятный символ {src[pos]!r}')
        text = m.group(m.lastgroup)
        kind = m.lastgroup
        if kind == 'num':
            val = int(text, 16) if text.lower().startswith('0x') else (float(text) if '.' in text else int(text))
            out.append(('num', val, line))
        elif kind == 'str':
            body, s, i = text[1:-1], '', 0
            while i < len(body):
                if body[i] == '\\':
                    s += ESC.get(body[i + 1], body[i + 1])
                    i += 2
                else:
                    s += body[i]
                    i += 1
            out.append(('str', s, line))
        elif kind == 'id':
            out.append(('kw' if text in KEYWORDS else 'id', text, line))
        elif kind == 'op':
            out.append(('op', text, line))
        line += text.count('\n')
        pos = m.end()
    out.append(('eof', None, line))
    return out


# ---------------------------------------------------------------- разбор

class Parser:
    BIN = [('||',), ('&&',), ('==', '!=', '===', '!=='), ('<', '>', '<=', '>='), ('+', '-'), ('*', '/', '%')]

    def __init__(self, src):
        self.t = tokenize(src)
        self.i = 0

    def peek(self, k=0):
        return self.t[self.i + k]

    def at(self, val, kind=None):
        tk = self.peek()
        return tk[1] == val and (kind is None or tk[0] == kind) and tk[0] in ('op', 'kw', kind or 'op')

    def take(self, val=None):
        tk = self.t[self.i]
        if val is not None and (tk[1] != val or tk[0] not in ('op', 'kw')):
            raise AptcError(f'строка {tk[2]}: ждали «{val}», а там {tk[1]!r}')
        self.i += 1
        return tk

    def ident(self):
        tk = self.take()
        if tk[0] != 'id':
            raise AptcError(f'строка {tk[2]}: ждали имя, а там {tk[1]!r}')
        return tk[1]

    def program(self):
        out = []
        while self.peek()[0] != 'eof':
            out.append(self.statement(top=True))
        return out

    def block(self):
        self.take('{')
        out = []
        while not self.at('}'):
            out.append(self.statement())
        self.take('}')
        return out

    def body(self):
        return self.block() if self.at('{') else [self.statement()]

    def params(self):
        self.take('(')
        ps = []
        while not self.at(')'):
            ps.append(self.ident())
            if not self.at(')'):
                self.take(',')
        self.take(')')
        return ps

    def statement(self, top=False):
        tk = self.peek()
        line = tk[2]
        if tk[0] == 'kw' and tk[1] == 'function' and self.peek(1)[0] == 'id':
            if not top:
                raise AptcError(f'строка {line}: function имя(…) — только на верхнем уровне блока')
            self.take()
            name = self.ident()
            return ('fundecl', name, self.params(), self.block(), line)
        if tk[0] == 'kw' and tk[1] == 'var':
            self.take()
            name = self.ident()
            e = None
            if self.at('='):
                self.take('=')
                e = self.expr()
            self.take(';')
            return ('var', name, e, line)
        if tk[0] == 'kw' and tk[1] == 'if':
            self.take()
            self.take('(')
            c = self.expr()
            self.take(')')
            th = self.body()
            el = []
            if self.peek()[0] == 'kw' and self.peek()[1] == 'else':
                self.take()
                el = self.body()
            return ('if', c, th, el, line)
        if tk[0] == 'kw' and tk[1] == 'while':
            self.take()
            self.take('(')
            c = self.expr()
            self.take(')')
            return ('while', c, self.body(), line)
        if tk[0] == 'kw' and tk[1] == 'return':
            self.take()
            e = None if self.at(';') else self.expr()
            self.take(';')
            return ('return', e, line)
        if self.at('{'):
            return ('block', self.block(), line)
        e = self.expr()
        if self.at('='):
            self.take('=')
            if e[0] not in ('name', 'member', 'index'):
                raise AptcError(f'строка {line}: присваивать можно имени, a.b или a[b]')
            v = self.expr()
            self.take(';')
            return ('assign', e, v, line)
        self.take(';')
        return ('expr', e, line)

    def expr(self):
        c = self.binary(0)
        if self.at('?'):
            self.take('?')
            a = self.expr()
            self.take(':')
            b = self.expr()
            return ('cond', c, a, b)
        return c

    def binary(self, level):
        if level == len(self.BIN):
            return self.unary()
        a = self.binary(level + 1)
        while self.peek()[0] == 'op' and self.peek()[1] in self.BIN[level]:
            op = self.take()[1]
            b = self.binary(level + 1)
            a = ('and', a, b) if op == '&&' else ('or', a, b) if op == '||' else ('bin', op, a, b)
        return a

    def unary(self):
        if self.peek()[0] == 'op' and self.peek()[1] in ('!', '-'):
            op = self.take()[1]
            e = self.unary()
            if op == '-' and e[0] == 'num':
                return ('num', -e[1])
            return ('unary', op, e)
        return self.postfix(self.primary())

    def postfix(self, e, allow_call=True):
        while True:
            if self.at('.'):
                self.take('.')
                tk = self.take()
                if tk[0] not in ('id', 'kw'):
                    raise AptcError(f'строка {tk[2]}: после точки ждали имя')
                e = ('member', e, tk[1])
            elif self.at('['):
                self.take('[')
                k = self.expr()
                self.take(']')
                e = ('index', e, k)
            elif self.at('(') and allow_call:
                e = ('call', e, self.args())
            else:
                return e

    def args(self):
        self.take('(')
        out = []
        while not self.at(')'):
            out.append(self.expr())
            if not self.at(')'):
                self.take(',')
        self.take(')')
        return out

    def primary(self):
        tk = self.take()
        kind, val, line = tk
        if kind == 'num':
            return ('num', val)
        if kind == 'str':
            return ('str', val)
        if kind == 'id':
            return ('name', val)
        if kind == 'kw':
            if val in ('true', 'false', 'null', 'undefined'):
                return ('lit', val)
            if val == 'this':
                return ('this',)
            if val == 'function':
                return ('func', self.params(), self.block(), line)
            if val == 'new':
                callee = self.postfix(self.primary(), allow_call=False)
                return ('new', callee, self.args() if self.at('(') else [])
        if kind == 'op' and val == '(':
            e = self.expr()
            self.take(')')
            return e
        raise AptcError(f'строка {line}: непонятно {val!r}')


# ---------------------------------------------------------------- кодогенерация

class Label:
    n = 0

    def __init__(self):
        Label.n += 1
        self.id = Label.n

    def __repr__(self):
        return f'L{self.id}'


def _scan(stmts, names, flags):
    """var-имена (подъём, как в AS) и пользование this/_global — без вложенных функций."""
    for s in stmts:
        k = s[0]
        if k == 'var':
            names.append(s[1])
            if s[2] is not None:
                _scan_e(s[2], flags)
        elif k == 'assign':
            _scan_e(s[1], flags)
            _scan_e(s[2], flags)
        elif k == 'if':
            _scan_e(s[1], flags)
            _scan(s[2], names, flags)
            _scan(s[3], names, flags)
        elif k == 'while':
            _scan_e(s[1], flags)
            _scan(s[2], names, flags)
        elif k in ('return', 'expr'):
            if s[1] is not None:
                _scan_e(s[1], flags)
        elif k == 'block':
            _scan(s[1], names, flags)


def _scan_e(e, flags):
    k = e[0]
    if k == 'this':
        flags.add('this')
    elif k == 'name' and e[1] == '_global':
        flags.add('_global')
    elif k == 'func':
        return
    for x in e[1:]:
        if isinstance(x, tuple):
            _scan_e(x, flags)
        elif isinstance(x, list):
            for y in x:
                if isinstance(y, tuple):
                    _scan_e(y, flags)


class Func:
    """Контекст функции: регистры this/_global, параметров и var."""

    def __init__(self, params, body, outer=None, line=0):
        names, used = [], set()
        _scan(body, names, used)
        self.outer = outer
        self.flags = SUPPRESS_ARGUMENTS | SUPPRESS_SUPER
        self.regs = {}
        r = 1
        if 'this' in used:
            self.flags |= PRELOAD_THIS
            self.regs['this'] = r
            r += 1
        else:
            self.flags |= SUPPRESS_THIS
        if '_global' in used:
            self.flags |= PRELOAD_GLOBAL
            self.regs['_global'] = r
            r += 1
        self.params = []
        for p in params:
            if p in self.regs:
                raise AptcError(f'строка {line}: параметр {p} повторяется')
            self.regs[p] = r
            self.params.append((r, p))
            r += 1
        for v in names:
            if v not in self.regs:
                self.regs[v] = r
                r += 1
        if r > 255:
            raise AptcError(f'строка {line}: больше 255 регистров')
        self.nregs = r

    def outer_names(self):
        f, out = self.outer, set()
        while f is not None:
            out |= {k for k in f.regs if k not in ('this', '_global')}
            f = f.outer
        return out


class Gen:
    def __init__(self):
        self.out = []

    def op(self, name, arg=None):
        self.out.append((name, arg))

    def label(self, lb):
        self.out.append(('label', lb))

    # -- значения
    def num(self, v):
        if isinstance(v, float) and v.is_integer() and abs(v) < 2 ** 31:
            v = int(v)
        if isinstance(v, int):
            if v == 0:
                self.op('PushZero')
            elif v == 1:
                self.op('PushOne')
            elif -128 <= v <= 127:
                self.op('PushByte', v)
            elif -32768 <= v <= 32767:
                self.op('PushShort', v)
            elif -2 ** 31 <= v < 2 ** 31:
                self.op('PushLong', v)
            else:
                raise AptcError(f'число {v} не влезает в 32 бита')
        else:
            self.op('PushFloat', float(v))


def compile_source(src):
    """Исходник верхнего уровня → список команд (с вложенными телами функций)."""
    prog = Parser(src).program()
    g = Gen()
    for s in prog:
        _stmt(g, s, None)
    g.op('End')
    return g.out


def _fn_item(name, params, body, outer, line):
    f = Func(params, body, outer, line)
    g = Gen()
    for s in body:
        _stmt(g, s, f)
    return ('DefineFunction2', {'name': name, 'params': f.params, 'nregs': f.nregs, 'flags': f.flags, 'body': g.out})


def _stmt(g, s, f):
    k = s[0]
    if k == 'fundecl':
        g.out.append(_fn_item(s[1], s[2], s[3], f, s[4]))
    elif k == 'var':
        if f is None:
            raise AptcError(f'строка {s[3]}: var вне функции не поддержан')
        if s[2] is not None:
            _expr(g, s[2], f)
            g.op('SetRegister', f.regs[s[1]])
            g.op('Pop')
    elif k == 'assign':
        t, v = s[1], s[2]
        if t[0] == 'name':
            if f is not None and t[1] in f.regs and t[1] not in ('this', '_global'):
                _expr(g, v, f)
                g.op('SetRegister', f.regs[t[1]])
                g.op('Pop')
            else:
                _check_outer(t[1], f, s[3])
                g.op('PushString', t[1])
                _expr(g, v, f)
                g.op('SetVariable')
        elif t[0] == 'member':
            _expr(g, t[1], f)
            g.op('PushString', t[2])
            _expr(g, v, f)
            g.op('SetMember')
        else:
            _expr(g, t[1], f)
            _expr(g, t[2], f)
            _expr(g, v, f)
            g.op('SetMember')
    elif k == 'expr':
        e = s[1]
        if e[0] == 'call' and e[1] == ('name', 'trace'):
            if len(e[2]) != 1:
                raise AptcError(f'строка {s[2]}: trace — один аргумент')
            _expr(g, e[2][0], f)
            g.op('Trace')
        else:
            _expr(g, e, f)
            g.op('Pop')
    elif k == 'if':
        lelse, lend = Label(), Label()
        _cond_false(g, s[1], f, lelse)
        for x in s[2]:
            _stmt(g, x, f)
        if s[3]:
            g.op('BranchAlways', lend)
            g.label(lelse)
            for x in s[3]:
                _stmt(g, x, f)
            g.label(lend)
        else:
            g.label(lelse)
    elif k == 'while':
        ltop, lend = Label(), Label()
        g.label(ltop)
        _cond_false(g, s[1], f, lend)
        for x in s[2]:
            _stmt(g, x, f)
        g.op('BranchAlways', ltop)
        g.label(lend)
    elif k == 'return':
        if f is None:
            raise AptcError(f'строка {s[2]}: return вне функции')
        if s[1] is None:
            g.op('PushUndefined')
        else:
            _expr(g, s[1], f)
        g.op('Return')
    elif k == 'block':
        for x in s[1]:
            _stmt(g, x, f)
    else:
        raise AptcError(f'оператор {k}?')


def _cond_false(g, c, f, target):
    _expr(g, c, f)
    g.op('Not')
    g.op('BranchIfTrue', target)


def _check_outer(name, f, line):
    if f is not None and name in f.outer_names():
        raise AptcError(f'строка {line}: «{name}» — переменная внешней функции (в регистре), замыканий нет')


BINOP = {'+': ['Add2'], '-': ['Subtract'], '*': ['Multiply'], '/': ['Divide'], '%': ['Modulo'], '<': ['Less2'],
         '>': ['Greater'], '<=': ['Greater', 'Not'], '>=': ['Less2', 'Not'], '==': ['Equals2'],
         '!=': ['Equals2', 'Not'], '===': ['StrictEquals'], '!==': ['StrictEquals', 'Not']}


def _expr(g, e, f):
    k = e[0]
    if k == 'num':
        g.num(e[1])
    elif k == 'str':
        g.op('PushString', e[1])
    elif k == 'lit':
        g.op({'true': 'PushTrue', 'false': 'PushFalse', 'null': 'PushNull', 'undefined': 'PushUndefined'}[e[1]])
    elif k == 'this':
        if f is None:
            g.op('PushThis')
        else:
            g.op('PushRegister', f.regs['this'])
    elif k == 'name':
        n = e[1]
        if n == '_global':
            if f is None:
                g.op('PushGlobal')
            else:
                g.op('PushRegister', f.regs['_global'])
        elif f is not None and n in f.regs:
            g.op('PushRegister', f.regs[n])
        else:
            _check_outer(n, f, '?')
            g.op('PushString', n)
            g.op('GetVariable')
    elif k == 'member':
        _expr(g, e[1], f)
        g.op('PushString', e[2])
        g.op('GetMember')
    elif k == 'index':
        _expr(g, e[1], f)
        _expr(g, e[2], f)
        g.op('GetMember')
    elif k == 'call':
        callee, args = e[1], e[2]
        if callee == ('name', 'trace'):
            raise AptcError('trace(…) — только оператором')
        for a in reversed(args):
            _expr(g, a, f)
        g.num(len(args))
        if callee[0] == 'name' and not (f is not None and callee[1] in f.regs):
            _check_outer(callee[1], f, '?')
            g.op('PushString', callee[1])
            g.op('CallFunction')
        elif callee[0] == 'member':
            _expr(g, callee[1], f)
            g.op('PushString', callee[2])
            g.op('CallMethod')
        elif callee[0] == 'index':
            _expr(g, callee[1], f)
            _expr(g, callee[2], f)
            g.op('CallMethod')
        else:
            # значение-функция (регистр, выражение): CallMethod с именем undefined вызывает сам объект
            _expr(g, callee, f)
            g.op('PushUndefined')
            g.op('CallMethod')
    elif k == 'new':
        callee, args = e[1], e[2]
        for a in reversed(args):
            _expr(g, a, f)
        g.num(len(args))
        if callee[0] == 'name':
            g.op('PushString', callee[1])
            g.op('NewObject')
        elif callee[0] == 'member':
            _expr(g, callee[1], f)
            g.op('PushString', callee[2])
            g.op('NewMethod')
        else:
            raise AptcError('new: нужен X или a.B')
    elif k == 'unary':
        if e[1] == '!':
            _expr(g, e[2], f)
            g.op('Not')
        else:
            g.op('PushZero')
            _expr(g, e[2], f)
            g.op('Subtract')
    elif k == 'bin':
        _expr(g, e[2], f)
        _expr(g, e[3], f)
        for o in BINOP[e[1]]:
            g.op(o)
    elif k in ('and', 'or'):
        lend = Label()
        _expr(g, e[1], f)
        g.op('PushDuplicate')
        if k == 'and':
            g.op('Not')
        g.op('BranchIfTrue', lend)
        g.op('Pop')
        _expr(g, e[2], f)
        g.label(lend)
    elif k == 'cond':
        lelse, lend = Label(), Label()
        _cond_false(g, e[1], f, lelse)
        _expr(g, e[2], f)
        g.op('BranchAlways', lend)
        g.label(lelse)
        _expr(g, e[3], f)
        g.label(lend)
    elif k == 'func':
        g.out.append(_fn_item('', e[1], e[2], f, e[3]))
    else:
        raise AptcError(f'выражение {k}?')


def compile_function(src):
    """«function [имя](a, b) { … }» → команда DefineFunction2 (именованная — определение, безымянная — значение)."""
    p = Parser(src)
    tk = p.take('function')
    name = p.ident() if p.peek()[0] == 'id' else ''
    params = p.params()
    body = p.block()
    if p.peek()[0] != 'eof':
        raise AptcError('после тела функции ещё что-то')
    return _fn_item(name, params, body, None, tk[2])


def compile_snippet(src, regs):
    """Операторы для вставки в чужую функцию: regs — её регистры {имя: номер} (this, _global, параметры, rN).
    Своих var нет: только существующие регистры и имена кадра."""
    prog = Parser(src).program()
    f = Func([], [])
    f.regs = dict(regs)
    g = Gen()
    for s in prog:
        if s[0] in ('var', 'fundecl'):
            raise AptcError('во вставке нельзя var и function')
        _stmt(g, s, f)
    return g.out


# ---------------------------------------------------------------- исходный блок EA: разбор с сохранением байт

OPS_NAMES = {}


def _ops():
    """Таблица команд — из feapt (тот же разбор, что у дизассемблера)."""
    if not OPS_NAMES:
        import os
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import feapt
        OPS_NAMES['0'] = feapt.OPS0
        OPS_NAMES['1'] = feapt.OPS1
    return OPS_NAMES['0'], OPS_NAMES['1']


class RawIns:
    """Команда исходного блока: код, выровнены ли аргументы, их байты как есть; у ветвлений — цель, у функций —
    заголовок (без длины тела), тело (элементы) и имя."""
    __slots__ = ('off', 'op', 'name', 'aligned', 'operand', 'target', 'header', 'magic', 'body', 'body_len', 'fname',
                 'arg', 'params', 'regs')

    def __repr__(self):
        return f'{self.off:#x} {self.name} {self.arg!r}'


POOL_OPS = {'PushConstant', 'PushWordConstant', 'PushValueOfVar', 'GetNamedMember', 'CallNamedFuncPop', 'CallNamedFunc',
            'CallNamedMethodPop', 'CallNamedMethod'}
BRANCH_OPS = {'BranchAlways', 'BranchIfTrue', 'BranchIfFalse'}


def _cstr(d, o):
    return d[o:d.index(b'\0', o)].decode('latin1') if o else ''


def parse_block(d, start, consts, end=None, pool=None):
    """Блок байткода (с адреса start; end — для тела функции) → элементы для assemble: ('raw', RawIns),
    ('rawbr', RawIns, Label), ('rawfn', RawIns) и ('label', Label). Аргументы пуловых команд расшифрованы в .arg
    (строка), у PushByte/PushShort — число со знаком, у PushString — строка, у PushRegister — номер."""
    ops0, ops1 = _ops()
    pool = pool if pool is not None else [None]
    seq, targets, p = [], set(), start
    while True:
        if end is not None and p >= end:
            break
        op = d[p]
        ins = RawIns()
        ins.off, ins.op, ins.target, ins.body, ins.arg = p, op, None, None, None
        if op in ops0:
            ins.name, ins.aligned, ins.operand = ops0[op], False, b''
            p += 1
        elif op in ops1:
            name, aligned, kind = ops1[op]
            ins.name, ins.aligned = name, aligned
            q = (p + 1 + 3) & ~3 if aligned else p + 1
            if kind in ('u32', 'str', 's32'):
                n = 4
            elif kind in ('u32x2', 'str2', 'pool', 'data'):
                n = 8
            elif kind == 'u8':
                n = 1
            elif kind == 'u16':
                n = 2
            elif kind == 'f32':
                n = 4
            elif kind == '':
                n = 0
            elif kind in ('fn2', 'fn'):
                n = None
            else:
                raise AptcError(f'команда {name} @{p:#x} не поддержана')
            if kind in ('fn2', 'fn'):
                hl = 16 if kind == 'fn2' else 12                   # заголовок без поля длины тела
                ins.header = bytes(d[q:q + hl])
                size = struct.unpack_from('>I', d, q + hl)[0]
                ins.magic = bytes(d[q + hl + 4:q + hl + 12])
                if ins.magic != FN2_MAGIC:
                    raise AptcError(f'функция @{p:#x}: нет 98765432…')
                ins.fname = _cstr(d, struct.unpack_from('>I', d, q)[0])
                if kind == 'fn2':
                    npar, regflags, parptr = struct.unpack_from('>III', d, q + 4)
                    ins.params = [(struct.unpack_from('>I', d, parptr + 8 * k)[0],
                                   _cstr(d, struct.unpack_from('>I', d, parptr + 8 * k + 4)[0])) for k in range(npar)]
                    ins.regs = (regflags >> 16, regflags & 0xFFFF)
                else:
                    npar, parptr = struct.unpack_from('>II', d, q + 4)
                    ins.params = [(0, _cstr(d, struct.unpack_from('>I', d, parptr + 4 * k)[0])) for k in range(npar)]
                    ins.regs = (0, 0)
                bstart = q + hl + 12
                ins.body = parse_block(d, bstart, consts, bstart + size, pool)
                ins.body_len = size
                ins.operand = b''
                p = bstart + size
            else:
                ins.operand = bytes(d[q:q + n])
                p = q + n
                if kind == 's32':
                    ins.target = p + struct.unpack_from('>i', d, q)[0]
                    targets.add(ins.target)
                elif kind == 'pool':
                    cnt, ptr = struct.unpack_from('>II', d, q)
                    pool[0] = [struct.unpack_from('>I', d, ptr + 4 * k)[0] for k in range(cnt)]
                elif name in POOL_OPS:
                    k = d[q] if n == 1 else struct.unpack_from('>H', d, q)[0]
                    pl = pool[0]
                    ins.arg = consts[pl[k]] if pl is not None and k < len(pl) else (consts[k] if pl is None else None)
                elif name == 'PushByte':
                    ins.arg = struct.unpack_from('>b', d, q)[0]
                elif name == 'PushShort':
                    ins.arg = struct.unpack_from('>h', d, q)[0]
                elif name in ('PushRegister',):
                    ins.arg = d[q]
                elif name == 'SetRegister':
                    ins.arg = struct.unpack_from('>I', d, q)[0]
                elif name == 'PushString':
                    ins.arg = _cstr(d, struct.unpack_from('>I', d, q)[0])
        else:
            raise AptcError(f'неизвестная команда {op:#04x} @{p:#x}')
        seq.append(ins)
        if ins.name == 'End' and end is None and not any(t > ins.off for t in targets):
            break
    stop = p
    labels = {}
    for t in targets:
        if t < start or t > stop:
            raise AptcError(f'переход за блок: {t:#x}')
        labels[t] = Label()
    items = []
    for ins in seq:
        if ins.off in labels:
            items.append(('label', labels[ins.off]))
        if ins.target is not None:
            items.append(('rawbr', ins, labels[ins.target]))
        elif ins.body is not None:
            items.append(('rawfn', ins))
        else:
            items.append(('raw', ins))
    if stop in labels:
        items.append(('label', labels[stop]))
    return items


def fn_regs(ins):
    """Регистры функции EA для compile_snippet: this/_global по флагам, параметры по своим номерам."""
    nregs, flags = ins.regs
    regs, r = {}, 1
    for bit, nm in ((0x01, 'this'), (0x04, 'arguments'), (0x10, 'super'), (0x40, '_root'), (0x80, '_parent'),
                    (0x100, '_global')):
        if flags & bit:
            regs[nm] = r
            r += 1
    for reg, pn in ins.params:
        if reg:
            regs[pn] = reg
    for k in range(1, nregs):
        regs.setdefault(f'r{k}', k)
    return regs


def item_key(it):
    """(имя команды, аргумент) для поиска по образцу."""
    if it[0] in ('raw', 'rawbr', 'rawfn'):
        return (it[1].name, it[1].arg if it[0] != 'rawfn' else it[1].fname)
    if it[0] == 'label':
        return ('label', None)
    return (it[0], it[1] if not isinstance(it[1], dict) else it[1].get('name'))


def find_seq(items, pattern, start=0):
    """Индекс первой команды последовательности pattern ([(имя, арг|None)…], метки пропускаются) или -1."""
    real = [i for i in range(start, len(items)) if items[i][0] != 'label']
    for a in range(len(real) - len(pattern) + 1):
        ok = True
        for k, (nm, arg) in enumerate(pattern):
            key = item_key(items[real[a + k]])
            if key[0] != nm or (arg is not None and key[1] != arg):
                ok = False
                break
        if ok:
            return real[a], real[a + len(pattern) - 1]
    return -1, -1


# ---------------------------------------------------------------- сборка в Apt Data

def _align(n):
    return (n + 3) & ~3


def _walk_strings(items, acc):
    for it in items:
        if it[0] == 'PushString':
            acc.add(it[1])
        elif it[0] == 'DefineFunction2':
            fn = it[1]
            acc.add(fn['name'])
            for _, p in fn['params']:
                acc.add(p)
            _walk_strings(fn['body'], acc)
        elif it[0] == 'rawfn':
            _walk_strings(it[1].body, acc)


def _size(it, addr):
    name, arg = it[0], it[1]
    if name == 'label':
        return 0
    if name == 'raw':
        return (_align(addr + 1) if arg.aligned else addr + 1) + len(arg.operand) - addr
    if name == 'rawbr':
        return _align(addr + 1) + 4 - addr
    if name in ALIGNED:
        start = _align(addr + 1)
        return start + 4 - addr
    if name in ('PushByte', 'PushRegister'):
        return 2
    if name == 'PushShort':
        return 3
    if name in ('PushLong', 'PushFloat'):
        return 5
    return 1


def _layout(items, addr, labels):
    """Адреса меток; возвращает длину."""
    start = addr
    for it in items:
        if it[0] == 'label':
            labels[it[1]] = addr
        elif it[0] == 'DefineFunction2':
            s = _align(addr + 1)
            body_len = _layout(it[1]['body'], s + 28, labels)
            it[1]['_len'] = body_len
            addr = s + 28 + body_len
        elif it[0] == 'rawfn':
            fn = it[1]
            s = _align(addr + 1) + len(fn.header) + 4 + 8
            fn.body_len = _layout(fn.body, s, labels)
            addr = s + fn.body_len
        else:
            addr += _size(it, addr)
    return addr - start


def _encode(items, addr, labels, strs, parrays, out):
    for it in items:
        name, arg = it[0], it[1]
        if name == 'label':
            continue
        if name in ('raw', 'rawbr', 'rawfn'):
            out.append(arg.op)
            addr += 1
            if arg.aligned:
                pad = _align(addr) - addr
                out.extend(b'\0' * pad)
                addr += pad
            if name == 'raw':
                out.extend(arg.operand)
                addr += len(arg.operand)
            elif name == 'rawbr':
                out.extend(struct.pack('>i', labels[it[2]] - (addr + 4)))
                addr += 4
            else:
                fn = arg
                out.extend(fn.header + struct.pack('>I', fn.body_len) + fn.magic)
                addr += len(fn.header) + 12
                body = bytearray()
                _encode(fn.body, addr, labels, strs, parrays, body)
                if len(body) != fn.body_len:
                    raise AptcError('длина тела функции EA не сошлась')
                out.extend(body)
                addr += len(body)
            continue
        out.append(OPCODE[name])
        addr += 1
        if name in ALIGNED:
            pad = _align(addr) - addr
            out.extend(b'\0' * pad)
            addr += pad
        if name == 'PushString':
            out.extend(struct.pack('>I', strs[arg]))
            addr += 4
        elif name == 'SetRegister':
            out.extend(struct.pack('>I', arg))
            addr += 4
        elif name in ('BranchAlways', 'BranchIfTrue'):
            out.extend(struct.pack('>i', labels[arg] - (addr + 4)))
            addr += 4
        elif name == 'DefineFunction2':
            fn = arg
            out.extend(struct.pack('>IIIII', strs[fn['name']], len(fn['params']), (fn['nregs'] << 16) | fn['flags'],
                                   parrays[id(fn)], fn['_len']))
            out.extend(FN2_MAGIC)
            addr += 28
            body = bytearray()
            _encode(fn['body'], addr, labels, strs, parrays, body)
            if len(body) != fn['_len']:
                raise AptcError('длина тела функции не сошлась')
            out.extend(body)
            addr += len(body)
        elif name in ('PushByte',):
            out.extend(struct.pack('>b', arg))
            addr += 1
        elif name == 'PushRegister':
            out.append(arg)
            addr += 1
        elif name == 'PushShort':
            out.extend(struct.pack('>h', arg))
            addr += 2
        elif name == 'PushLong':
            out.extend(struct.pack('>i', arg))
            addr += 4
        elif name == 'PushFloat':
            out.extend(struct.pack('>f', arg))
            addr += 4


def _walk_fns(items, acc):
    for it in items:
        if it[0] == 'DefineFunction2':
            acc.append(it[1])
            _walk_fns(it[1]['body'], acc)
        elif it[0] == 'rawfn':
            _walk_fns(it[1].body, acc)


def put_string(d, text, table=None):
    """Строка в конец Apt Data (с выравниванием по 4, как у feapt.graft); table — кэш уже положенных."""
    if table is not None and text in table:
        return table[text]
    while len(d) % 4:
        d.append(0)
    p = len(d)
    d.extend(text.encode('latin1') + b'\0')
    if table is not None:
        table[text] = p
    return p


def assemble(items, d, strings=None):
    """Дописать в Apt Data d (bytearray) строки, массивы параметров и код; вернуть смещение начала кода."""
    strings = {} if strings is None else strings
    acc = set()
    _walk_strings(items, acc)
    for s in sorted(acc):
        put_string(d, s, strings)
    fns = []
    _walk_fns(items, fns)
    parrays = {}
    for fn in fns:
        while len(d) % 4:
            d.append(0)
        parrays[id(fn)] = len(d)
        for reg, p in fn['params']:
            d.extend(struct.pack('>II', reg, strings[p]))
    while len(d) % 4:
        d.append(0)
    base = len(d)
    labels = {}
    total = _layout(items, base, labels)
    out = bytearray()
    _encode(items, base, labels, strings, parrays, out)
    if len(out) != total:
        raise AptError_('длина блока не сошлась')
    d.extend(out)
    return base


class AptError_(AptcError):
    pass


def encode_at(items, base):
    """Байты элементов, как если бы они стояли по адресу base (только исходные команды и код без строк)."""
    labels = {}
    total = _layout(items, base, labels)
    out = bytearray()
    _encode(items, base, labels, {}, {}, out)
    if len(out) != total:
        raise AptcError('длина не сошлась')
    return bytes(out)


def roundtrip(path):
    """Проверка разбора: каждый блок кода ролика → элементы → байты по тому же адресу (должны совпасть) и по
    сдвинутому на 1…3 (разбор feapt должен дать те же команды и цели)."""
    import os
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import feapt
    mv, consts = feapt.load_movie(path)
    d = mv.apt.data
    nb = 0
    for title, off in feapt.code_blocks(mv):
        items = parse_block(d, off, consts)
        b = encode_at(items, off)
        if b != d[off:off + len(b)]:
            raise AptcError(f'{title}: байты не совпали')
        for shift in (1, 2, 3):
            buf = bytearray(d) + b'\0' * 8
            base = len(d) + shift
            buf = bytearray(d) + b'\0' * shift
            buf.extend(encode_at(items, base))
            a = [(i.name, i.args) for i in _flat(feapt.Code(d, consts).parse(off))]
            c = [(i.name, i.args) for i in _flat(feapt.Code(bytes(buf), consts).parse(base))]
            if a != c:
                raise AptcError(f'{title}: при сдвиге {shift} разбор другой')
        nb += 1
    return nb


def _flat(instrs):
    for i in instrs:
        yield i
        if i.body is not None:
            yield from _flat(i.body)


def compile_into(src, d, strings=None):
    """Исходник → блок кода в конце Apt Data; вернуть смещение начала (для Action/InitAction)."""
    return assemble(compile_source(src), d, strings)


# ---------------------------------------------------------------- пример

DEMO = r'''
function panelOffset(mc) {
    if (mc == mcThirdPanel) { return 2 * MAX_TEAMS_PER_PANEL; }
    return mc == mcRightPanel ? MAX_TEAMS_PER_PANEL : 0;
}
function initPanels() {
    var n = m_arrDraftTeamIDs.length;
    var a = n > MAX_TEAMS_PER_PANEL ? MAX_TEAMS_PER_PANEL : n;
    var b = n - a > MAX_TEAMS_PER_PANEL ? MAX_TEAMS_PER_PANEL : n - a;
    trace("initPanels: " + n);
    initPanel(mcLeftPanel, 0, a);
    initPanel(mcRightPanel, MAX_TEAMS_PER_PANEL, b);
    initPanel(mcThirdPanel, 2 * MAX_TEAMS_PER_PANEL, n - a - b);
    _global.EA_ZONE.gSTM.addItem(mcThirdPanel);
    updateHighlight();
}
'''


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    if sys.argv[1:2] != ['demo']:
        sys.exit(__doc__)
    import os
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import feapt
    d = bytearray(b'Apt Data:1:7:4\x1a\0')
    off = compile_into(DEMO, d)
    code = feapt.Code(bytes(d), [])
    instrs = code.parse(off)
    print('\n'.join(feapt.Decompiler(raw=True).block(instrs)))
    print()
    print('\n'.join(feapt.Decompiler().block(instrs)))


if __name__ == '__main__':
    main()
