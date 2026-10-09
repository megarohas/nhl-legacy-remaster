"""Пункты меню NHL Legacy (mainmenuitems.big): скрыть онлайн-пункты, добавить EXIT — файлы для cache: Legacy.

    python menuitems_legacy.py list [FILE.big]          # пункты по массивам: номер, имя, подпись, смещения
    python menuitems_legacy.py build [--exit last|before-featured|none] [--keep-custom-music] [--keep ИМЯ,…]
                                     [--keep-panel] [--work DIR] [--no-out]
        # → WORK (game/work/legacy-data/menu-items/build, раскладка cache:) и game/work/legacy-data/out; список
        #   своих файлов — game/work/legacy-data/menu-items/files.txt:
        #   fe/ion/game/menus/mainmenuitems.big — без онлайн-пунктов (HIDE) и с EXIT;
        #   fe/loc/NHL_ENG_US.db — локализация из out (база legacy-data): подпись EXIT — ключ XboxLiveMarketPlace
        #       («Xbox Live Marketplace») → «Exit»; панель описаний главного меню — страницы 0–2 (EASHL, HUT Online,
        #       GM Connected) → Be a GM, Play Now, Battle for the Cup (PANEL; --keep-panel — оставить). locdb put:
        #       своя строка, чужие ключи с тем же текстом не меняются
    python menuitems_legacy.py check [DIR]              # разбор собранного: какие пункты в массивах, отличия
                                                        # от оригинала — только правки

Устройство (разбор 09.10.2026, docs/fe-menu-legacy.md §8): все пункты — операторы
`objMainMenu.<массив>.push({name: …, …})` кадра 0 ролика boot:fe/ion/game/menus/mainmenuitems.big (свободный
файл cache: игра берёт раньше архива). `name` — и ключ подписи (ltxt), и ключ switch в objMainMenu.MenuCallback;
подменю — прямая ссылка на массив; номер пункта нужен только курсору и стеку возврата. Скрытие — пункт не
добавляется: имя метода `push` (PushWordConstant #396) → `concat` (#591) — объект строится, Array.concat без
побочных эффектов, клип пункта не создаётся (правка 2 байта той же длины). Флаг isHidden хуже: при загрузке
игра ставит курсор на TXT_HUT по имени (SetHighlightedMenuItem не проверяет видимость).
EXIT — пункт {name: "XboxLiveMarketplace", screenID: null}: его ветка в MenuCallback уже есть и зовёт родную
ION_GameSetup.ShowMarketplaceUI(контроллер) (больше её не зовёт ни один ролик fe). В порте legacy-port
перехватывает её обёртку 0x832EFE28 и закрывает программу (cvar nhl_menu_exit = true). БЕЗ перехвата —
ловушка: заглушка XamShowMarketplaceUI порта отвечает «успех», меню прячет список и ждёт закрытия магазина
навсегда; поэтому файлы ставятся только вместе с exe legacy-port. Корень переписывается участком той же длины: копии байт
операторов (без указателей и переходов), новый пункт, заполнитель PushZero/Pop.

Только стандартная библиотека. Байткод — tools/feapt.py, локализация — tools/locdb.py.
"""
import json, os, shutil, struct, sys

TOOLS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TOOLS)
import feapt               # noqa: E402
import febg                # noqa: E402
import gameprofile         # noqa: E402

P = gameprofile.get('legacy')
WORK = P.work_dir('menu-items', 'build')
FILES = P.work_dir('menu-items', 'files.txt')
MENUITEMS = 'fe/ion/game/menus/mainmenuitems.big'
LOC = 'fe/loc/NHL_ENG_US.db'
OUT_AHL32 = os.path.join(os.path.dirname(P.out), 'out-ahl32')     # накладка legacy-data «АХЛ на 32»
LOC_META = 'fe/loc/nhl_eng_us-meta.xml'
ROOT = 'objMainMenu.arrRootMenu'
PUSH, CONCAT = bytes.fromhex('a3018c'), bytes.fromhex('a3024f')      # PushWordConstant «push» #396 / «concat» #591
EXIT_NAME, EXIT_KEY, EXIT_TEXT = 'XboxLiveMarketplace', 'XboxLiveMarketPlace', 'Exit'
# панель описаний внизу справа главного меню («Features», 5 страниц TXT_OFFLINE_DYNAMIC_MSG_TITLE/BODY_0…4 из exe):
# страницы 0–2 рекламировали онлайн (EASHL Seasons, HUT Online Seasons, GM Connected) — теперь офлайн-режимы
# меню (3 — Enforcer Engine, 4 — Live the Life остаются); по длине не больше оригиналов
PANEL = {
    'TXT_OFFLINE_DYNAMIC_MSG_TITLE_0': 'Be a GM',
    'TXT_OFFLINE_DYNAMIC_MSG_BODY_0': 'Run your favorite franchise in a 32-team NHL from the 2026/27 season. '
                                      'Sign free agents, make trades and draft your next superstar.',
    'TXT_OFFLINE_DYNAMIC_MSG_TITLE_1': 'Play Now',
    'TXT_OFFLINE_DYNAMIC_MSG_BODY_1': 'Jump straight into a game with any of the 32 NHL teams, including the Seattle '
                                      'Kraken and Vegas Golden Knights, with 2026/27 rosters. Play against the CPU or a friend.',
    'TXT_OFFLINE_DYNAMIC_MSG_TITLE_2': 'Battle for the Cup',
    'TXT_OFFLINE_DYNAMIC_MSG_BODY_2': 'Battle for the Cup is one playoff series for the championship against a friend '
                                      'or the CPU. Pick any two teams and play for the Stanley Cup.',
}

# что не добавлять: (массив, имя пункта или «cb:колбэк» динамического пункта, почему)
HIDE = [
    (ROOT, 'cb:viewInviteFromMainMenuCB', 'приглашение в онлайн-матч (скрыто без приглашения, онлайн)'),
    (ROOT, 'TXT_COMMUNITY', 'Community: Player Hub, Leaderboards, Lobby — онлайн (My Highlights есть в Media Hub)'),
    (ROOT, 'TXT_HUT', 'Hockey Ultimate Team — сервер EA'),
    (ROOT, 'cb:dynamicRivalryModeMenuCB', 'Rivalry / Game of the Week — данные с сервера'),
    ('objMainMenu.arrPlay', 'TXT_HUT', 'Hockey Ultimate Team — сервер EA'),
    ('objMainMenu.arrPlay', 'TXT_ONLINE', 'Online: GM Connected, Versus, EASHL, Arena, Team Play, Shootout'),
    ('objMainMenu.itemSinglePlayer', 'cb:dynamicRivalryModeMenuCB', 'Rivalry / Game of the Week — данные с сервера'),
    ('objMainMenu.arrCustomize', 'TXT_FIRST_PARTY_CODE_REDEMPTION', 'Offer Code Entry — коды Xbox Live'),
    ('objMainMenu.arrTMRosterManagement', 'DownloadRosters', 'Download Rosters — сервер EA'),
    ('objMainMenu.arrSettings', 'OnlineSettings', 'Online Settings — онлайн'),
]
CUSTOM_MUSIC = [
    ('objMainMenu.arrMyMedia', 'TXT_CUSTOM_AUDIO', 'Custom Music — музыка с жёсткого диска Xbox, в порте её нет'),
    ('objMainMenu.arrMyMedia', 'TXT_CUSTOM_AUDIO_TUTORIAL', 'подсказка к Custom Music'),
]


def log(*a):
    print(*a, flush=True)


def opt(args, name, default=None):
    return args[args.index(name) + 1] if name in args else default


def p(root, rel):
    return os.path.join(root, *rel.split('/'))


def legacy_src(rel):
    f = P.extracted(rel)
    if not f:
        raise SystemExit(f'нет {rel} в распакованных архивах Legacy ({P.big})')
    return f


# ---------------------------------------------------------------- разбор: операторы push кадра 0

PUSH1 = {'PushConstant', 'PushWordConstant', 'PushString', 'PushValueOfVar', 'PushGlobal', 'PushThis',
         'PushByte', 'PushShort', 'PushLong', 'PushFloat', 'PushTrue', 'PushFalse', 'PushNull',
         'PushUndefined', 'PushZero', 'PushOne', 'PushRegister', 'GetStringVar'}
UNARY = {'Not', 'ToNumber', 'ToString', 'ToInteger', 'TypeOf', 'TargetPath', 'StringLength', 'GetVariable',
         'Increment', 'Decrement', 'Delete2'}
BIN = set(feapt.BINOPS) | {'Delete'}


class Span:
    __slots__ = ('start', 'end', 'lit', 'pairs', 'ins')

    def __init__(self, start, end, lit=None, pairs=None, ins=None):
        self.start, self.end, self.lit, self.pairs, self.ins = start, end, lit, pairs, ins


def _lit(ins):
    n, a = ins.name, ins.args
    if n in ('PushConstant', 'PushWordConstant', 'PushString'):
        return a[0]
    if n in ('PushByte', 'PushShort', 'PushLong'):
        bits = {'PushByte': 8, 'PushShort': 16, 'PushLong': 32}[n]
        return a[0] - (1 << bits) if a[0] >= 1 << (bits - 1) else a[0]
    return {'PushZero': 0, 'PushOne': 1}.get(n)


def analyse(path):
    """Операторы `<массив>.push(арг)` кадра 0 по порядку: [{array, index, stmt (нач, кон), push (смещение
    команды «push»), name, cb, text}]. Разбор стека — по командам (feapt.Code), без исполнения."""
    mv, consts = feapt.load_movie(path)
    d = mv.apt.data
    code = feapt.Code(d, consts)
    off = [o for t, o in feapt.code_blocks(mv) if t.startswith('Movie 0, кадр 0: Action')][0]
    instrs = code.parse(off)
    dec = feapt.Decompiler()

    def text(start, end):
        lines = dec.block([i for i in instrs if start <= i.off < end])
        for ln in lines:
            if ln.strip().startswith('// стек в конце:'):
                return ln.split(':', 1)[1].strip()
        return ' '.join(x.strip() for x in lines)

    st, found, warn = [], [], []
    stmt_start, carry, prev = None, None, None
    for ins in instrs:
        nm = ins.name
        if stmt_start is None:
            stmt_start = ins.off

        def push(sp):
            nonlocal carry
            if carry is not None:
                sp.start = min(sp.start, carry)
                carry = None
            st.append(sp)

        def pop():
            return st.pop() if st else Span(ins.off, ins.off)

        def popargs():
            k = pop()
            cnt = k.lit if isinstance(k.lit, int) else 0
            return k, [pop() for _ in range(cnt)]

        end = False
        if nm in PUSH1:
            push(Span(ins.off, ins.end, _lit(ins), ins=ins))
        elif nm == 'PushData':
            for a in ins.args:
                push(Span(ins.off, ins.end, a, ins=ins))
        elif nm == 'PushDuplicate':
            t = st[-1] if st else Span(ins.off, ins.off)
            push(Span(t.start, ins.end, t.lit))
        elif nm in ('GetNamedMember', 'GetStringMember'):
            o = pop()
            push(Span(o.start, ins.end))
        elif nm == 'GetMember':
            k, o = pop(), pop()
            push(Span(min(o.start, k.start), ins.end))
        elif nm in UNARY:
            a = pop()
            push(Span(a.start, ins.end))
        elif nm in BIN:
            b, a = pop(), pop()
            push(Span(min(a.start, b.start), ins.end))
        elif nm in ('CallMethod', 'CallMethodEA', 'CallMethodPop'):
            name, obj = pop(), pop()
            k, args = popargs()
            if nm == 'CallMethodPop':
                if name.lit == 'push' and args:
                    found.append((stmt_start, ins.end, name.ins, obj, args[0]))
                end = True
            else:
                push(Span(min([name.start, obj.start, k.start] + [x.start for x in args]), ins.end))
        elif nm in ('CallNamedMethod', 'CallNamedMethodPop'):
            obj = pop()
            k, args = popargs()
            if nm.endswith('Pop'):
                if ins.args[0] == 'push' and args:
                    found.append((stmt_start, ins.end, ins, obj, args[0]))
                end = True
            else:
                push(Span(min([obj.start, k.start] + [x.start for x in args]), ins.end))
        elif nm in ('CallFunction', 'CallFunc', 'CallFuncPop', 'NewObject'):
            name = pop()
            k, args = popargs()
            if nm == 'CallFuncPop':
                end = True
            else:
                push(Span(min([name.start, k.start] + [x.start for x in args]), ins.end))
        elif nm in ('CallNamedFunc', 'CallNamedFuncPop'):
            k, args = popargs()
            if nm.endswith('Pop'):
                end = True
            else:
                push(Span(min([k.start] + [x.start for x in args]), ins.end))
        elif nm == 'NewMethod':
            name, obj = pop(), pop()
            k, args = popargs()
            push(Span(min([name.start, obj.start, k.start] + [x.start for x in args]), ins.end))
        elif nm == 'InitObject':
            k = pop()
            cnt = k.lit if isinstance(k.lit, int) else 0
            pairs = []
            for _ in range(cnt):
                v, key = pop(), pop()
                pairs.append((key, v))
            pairs.reverse()
            push(Span(min([k.start] + [x.start for pr in pairs for x in pr]), ins.end, pairs=pairs, ins=ins))
        elif nm == 'InitArray':
            k, args = popargs()
            push(Span(min([k.start] + [x.start for x in args]), ins.end))
        elif nm == 'SetMember':
            pop(); pop(); pop()
            end = True
        elif nm in ('SetVariable', 'DefineLocal', 'SetStringMember', 'Extends'):
            pop(); pop()
            end = True
        elif nm in ('DefineLocal2', 'Trace', 'Return', 'Throw', 'SetStringVar'):
            pop()
            end = True
        elif nm == 'Pop':
            x = pop()
            if prev is not None and prev.name in feapt.BRANCHES:
                carry = x.start                              # a && b / a || b
            else:
                end = True
        elif nm in ('BranchIfTrue', 'BranchIfFalse'):
            pop()
            if not (prev is not None and prev.name in ('PushDuplicate', 'Not')):
                end = True
        elif nm == 'BranchAlways':
            end = not st
        elif nm in ('DefineFunction2', 'DefineFunction'):
            if not ins.args[0]:
                push(Span(ins.off, ins.end))
            else:
                end = True
        elif nm in ('SetRegister', 'Nop58'):
            pass
        elif nm == 'ConstantPool':
            end = True
        elif nm == 'End':
            break
        elif nm == 'ImplementsOp':
            pop(); popargs()
            end = True
        elif nm in ('Enumerate', 'Enumerate2'):
            pop()
            push(Span(ins.off, ins.end))
        else:
            warn.append(f'{ins.off:#x} {nm}: не учтено')
        if end:
            if st:
                warn.append(f'{ins.off:#x} {nm}: стек не пуст в конце оператора ({len(st)})')
                st.clear()
            stmt_start, carry = None, None
        prev = ins
    items, count = [], {}
    for s, e, pins, obj, arg in found:
        names = [i.args[0] for i in instrs if obj.start <= i.off < obj.end
                 and i.name in ('PushConstant', 'PushWordConstant', 'PushValueOfVar', 'GetNamedMember')]
        arr = '.'.join(names)
        k = count.get(arr, 0)
        count[arr] = k + 1
        name = cb = None
        for key, val in (arg.pairs or []):
            if key.lit == 'name' and isinstance(val.lit, str):
                name = val.lit
            if key.lit == 'cbDynamic':
                cb = text(val.start, val.end)
        if arg.pairs is None:
            cb = text(arg.start, arg.end)
        items.append({'array': arr, 'index': k, 'stmt': (s, e), 'push': pins.off,
                      'push_bytes': d[pins.off:pins.end].hex(), 'name': name, 'cb': cb,
                      'text': text(arg.start, arg.end)})
    return mv, items, warn


def ident(it):
    """Имя пункта для списков: name, а у динамического (cbDynamic) — «cb:колбэк»."""
    if it['cb']:
        return 'cb:' + it['cb'].split('.')[-1].rstrip('()')
    return it['name'] or ''


def visible(items):
    """{массив: [имена]} — какие пункты добавляются (push, не concat)."""
    out = {}
    for it in items:
        if it['push_bytes'] == PUSH.hex():
            out.setdefault(it['array'], []).append(ident(it))
    return out


# ---------------------------------------------------------------- правки

def filler(n):
    """n байт без действия: PushZero/Pop (59 17) парами, при нечётном n — PushZero/Not/Pop (59 12 17)."""
    if n < 0 or n == 1:
        raise SystemExit(f'заполнитель {n} байт не собрать')
    out = b''
    if n % 2:
        out, n = bytes.fromhex('591217'), n - 3
    return out + bytes.fromhex('5917') * (n // 2)


def plan(src, exit_mode='last', hide=None):
    """[(смещение, старые, новые)] для feapt.patch_bytes и список скрытого [(массив, имя, почему)]."""
    hide = HIDE if hide is None else hide
    mv, items, warn = analyse(src)
    if warn:
        raise SystemExit('разбор mainmenuitems.big: ' + '; '.join(warn[:5]))
    d = mv.apt.data
    by = {}
    for it in items:
        by.setdefault((it['array'], ident(it)), []).append(it)
    root = [it for it in items if it['array'] == ROOT]
    rid = [ident(it) for it in root]
    want = ['cb:viewInviteFromMainMenuCB', 'TXT_PLAY_ROOT', 'TXT_COMMUNITY', 'TXT_CUSTOMIZATION', 'FUT_LiveTournaments',
            'TXT_HUT', 'cb:dynamicRivalryModeMenuCB', 'TXT_BE_A_PRO_MODE', 'TXT_CLASSIC_MODE']
    if rid != want:
        raise SystemExit(f'корень меню не тот, что ждали: {rid}')
    raw = lambda it: bytes(d[it['stmt'][0]:it['stmt'][1]])
    edits, rewritten, hidden = [], set(), []
    if exit_mode != 'none':
        play = raw(root[1])
        tail = play[play.rindex(bytes.fromhex('435a')) + 1:]         # PushOne, приёмник, «push», CallMethodPop
        if not tail.endswith(PUSH + b'\x5d'):
            raise SystemExit(f'хвост оператора PLAY не тот: {tail.hex()}')
        # {name: "XboxLiveMarketplace", screenID: null}: «name» #0, строка #757, «screenID» #14 пула кадра 0
        # (сам ролик после правки разбирается целиком — check)
        exit_item = bytes.fromhex('a200' 'a302f5' 'a20e' '75' 'b502' '43') + tail
        if exit_mode == 'last':           # корень [5…8] → LIVE THE LIFE, NHL 94, EXIT
            a, b = root[5]['stmt'][0], root[8]['stmt'][1]
            new = raw(root[7]) + raw(root[8]) + exit_item
            rewritten = {5, 6, 7, 8}
            hidden += [(ROOT, rid[5], 'Hockey Ultimate Team — сервер EA'),
                       (ROOT, rid[6], 'Rivalry / Game of the Week — данные с сервера')]
        elif exit_mode == 'before-featured':   # корень [2…8] → CUSTOMIZE, EXIT, FEATURED, LIVE THE LIFE, NHL 94
            a, b = root[2]['stmt'][0], root[8]['stmt'][1]
            new = raw(root[3]) + exit_item + raw(root[4]) + raw(root[7]) + raw(root[8])
            rewritten = {2, 3, 4, 5, 6, 7, 8}
            hidden += [(ROOT, rid[2], 'Community — онлайн'), (ROOT, rid[5], 'Hockey Ultimate Team — сервер EA'),
                       (ROOT, rid[6], 'Rivalry / Game of the Week — данные с сервера')]
        else:
            raise SystemExit(f'--exit {exit_mode}: last | before-featured | none')
        new += filler((b - a) - len(new))
        edits.append((a, bytes(d[a:b]), new))
    for arr, name, why in hide:
        its = by.get((arr, name))
        if not its:
            raise SystemExit(f'нет пункта {name} в {arr} — другой файл?')
        for it in its:
            if arr == ROOT and it['index'] in rewritten:
                continue
            o = it['push']
            if bytes(d[o:o + 3]) != PUSH:
                raise SystemExit(f'{arr} {name}: @{o:#x} не «push» ({d[o:o + 3].hex()})')
            edits.append((o, PUSH, CONCAT))
            hidden.append((arr, name, why))
    edits.sort()
    return edits, hidden


def loc_edits(src_db, dst_db, meta, edits):
    """Локализация: {ключ: текст} — своя строка в конец пула (locdb put: чужие ключи с тем же текстом не
    меняются); уже такой текст — без правки. → [(ключ, было, стало)]."""
    import locdb
    from tdb_read import load_meta
    loc = locdb.LocDb(open(src_db, 'rb').read(), load_meta(meta))
    done = []
    for key, text in edits.items():
        found = loc.find_all(key)
        if not found:
            raise SystemExit(f'{src_db}: нет ключа {key}')
        old = loc.text(loc.text_off_at(found[0]))
        if old != text:
            loc.put(key, text)
        done.append((key, old, text))
    bad = loc.check()
    if bad:
        raise SystemExit('локализация: ' + '; '.join(bad[:3]))
    loc.db.fix()
    open(dst_db, 'wb').write(loc.db.d)
    return done


def loc_text(db, meta, key):
    import locdb
    from tdb_read import load_meta
    loc = locdb.LocDb(open(db, 'rb').read(), load_meta(meta))
    f = loc.find_all(key)
    return loc.text(loc.text_off_at(f[0])) if f else None


# ---------------------------------------------------------------- команды

def cmd_list(args):
    path = args[0] if args else legacy_src(MENUITEMS)
    _, items, warn = analyse(path)
    for w in warn:
        log('  !!', w)
    meta = legacy_src(LOC_META)
    db = p(P.out, LOC) if os.path.exists(p(P.out, LOC)) else legacy_src('fe/loc/nhl_eng_us.db')
    import locdb
    from tdb_read import load_meta
    loc = locdb.LocDb(open(db, 'rb').read(), load_meta(meta))

    def label(n):
        f = loc.find_all(n) if n and not n.startswith('cb:') else []
        return loc.text(loc.text_off_at(f[0])) if f else ''
    cur = None
    for it in items:
        if it['array'] != cur:
            cur = it['array']
            log(f'\n== {cur}')
        shown = it['push_bytes'] == PUSH.hex()
        log(f"  [{it['index']}] {'   ' if shown else '(-)'} {ident(it):34s} {label(it['name'])!s:32s} push @{it['push']:#06x}")


def cmd_build(args):
    work = opt(args, '--work', WORK)
    exit_mode = opt(args, '--exit', 'last')
    keep = set((opt(args, '--keep', '') or '').split(',')) - {''}
    hide = [h for h in HIDE + ([] if '--keep-custom-music' in args else CUSTOM_MUSIC) if h[1] not in keep]
    if os.path.isdir(work):
        shutil.rmtree(work)
    os.makedirs(work)
    src = legacy_src(MENUITEMS)
    dst = p(work, MENUITEMS)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    edits, hidden = plan(src, exit_mode, hide)
    feapt.patch_bytes(src, dst, edits, log=lambda *a: None)
    lines = [f'menuitems_legacy build: --exit {exit_mode}' + (f', оставлены: {", ".join(sorted(keep))}' if keep else ''),
             f'{MENUITEMS}: {len(edits)} правок той же длины']
    lines += [f'  скрыт {arr.split(".")[-1]}: {name} — {why}' for arr, name, why in hidden]
    _, items, _ = analyse(dst)
    for arr, names in visible(items).items():
        if arr.startswith('objMainMenu.') and any(arr == h[0] for h in hidden) or arr == ROOT:
            lines.append(f'  {arr.split(".")[-1]}: {", ".join(names)}')
    built = [MENUITEMS]
    loc = ({EXIT_KEY: EXIT_TEXT} if exit_mode != 'none' else {}) | ({} if '--keep-panel' in args else PANEL)
    if loc:
        sdb = p(P.out, LOC)
        if not os.path.exists(sdb):
            raise SystemExit(f'нет {sdb} (локализация legacy-data)')
        ddb = p(work, LOC)
        os.makedirs(os.path.dirname(ddb), exist_ok=True)
        lines.append(f'{LOC} (из {sdb}):')
        for key, old, new in loc_edits(sdb, ddb, legacy_src(LOC_META), loc):
            lines.append(f'  {key}: «{old}» → «{new}»' if old != new else f'  {key}: «{new}» (уже)')
        built.append(LOC)
        # накладка «АХЛ на 32» (out-ahl32, install-legacy-data.sh --ahl32) несёт свою локализацию (CV/HSK):
        # те же правки и в ней, иначе установка с --ahl32 вернула бы «Xbox Live Marketplace» и прежнюю панель
        a32 = p(OUT_AHL32, LOC)
        if os.path.exists(a32):
            d32 = p(os.path.join(work, 'ahl32'), LOC)
            os.makedirs(os.path.dirname(d32), exist_ok=True)
            lines.append(f'{LOC} накладки АХЛ на 32 (из {a32}):')
            for key, old, new in loc_edits(a32, d32, legacy_src(LOC_META), loc):
                lines.append(f'  {key}: «{old[:40]}…» → «{new[:40]}…»' if old != new else f'  {key}: (уже)')
    open(os.path.join(work, 'build.log'), 'w', encoding='utf-8').write('\n'.join(lines) + '\n')
    json.dump({'exit': exit_mode, 'hide_spec': [list(h) for h in hide], 'hide': [list(h) for h in hidden],
               'loc': loc, 'files': built},
              open(os.path.join(work, 'build.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    for x in lines:
        log(x)
    if '--no-out' not in args:
        old = [x.strip() for x in open(FILES, encoding='utf-8')] if os.path.exists(FILES) else []
        for rel in sorted(set(old) - set(built)):
            if rel == LOC:
                log(f'  {LOC} в out остаётся (это файл legacy-data); подпись EXIT в нём — снять пересборкой legacy-data')
            elif rel and os.path.exists(p(P.out, rel)):
                os.remove(p(P.out, rel))
                log(f'  убран из out: {rel}')
        for rel in built:
            d = p(P.out, rel)
            os.makedirs(os.path.dirname(d), exist_ok=True)
            shutil.copyfile(p(work, rel), d)
        d32 = p(os.path.join(work, 'ahl32'), LOC)
        if os.path.exists(d32):
            shutil.copyfile(d32, p(OUT_AHL32, LOC))
            log(f'→ {p(OUT_AHL32, LOC)} (накладка АХЛ на 32)')
        os.makedirs(os.path.dirname(FILES), exist_ok=True)
        with open(FILES, 'w', encoding='utf-8', newline='\n') as f:
            f.write(''.join(r + '\n' for r in built))
        log(f'→ {P.out}: {len(built)} файлов; список — {FILES}')


def cmd_check(args):
    work = args[0] if args and not args[0].startswith('--') else WORK
    meta = json.load(open(os.path.join(work, 'build.json'), encoding='utf-8'))
    ok = True
    f = p(work, MENUITEMS)
    src = legacy_src(MENUITEMS)
    data = open(f, 'rb').read()
    mv = febg.FeMovie(data)
    rt = febg.build_bigf(feapt.ph.Bigf(data)) == data
    mvc, consts = feapt.load_movie(f)
    code = feapt.Code(mvc.apt.data, consts)
    nb = 0
    for t, off in feapt.code_blocks(mvc):
        code.parse(off)
        nb += 1
    orig = febg.FeMovie.load(src)
    edits, _ = plan(src, meta['exit'], [tuple(h) for h in meta['hide_spec']])
    a0, a1 = orig.apt.data, mv.apt.data
    diffs, k = [], 0
    while k < min(len(a0), len(a1)):
        if a0[k] != a1[k]:
            s = k
            while k < len(a0) and a0[k] != a1[k]:
                k += 1
            diffs.append((s, k))
        k += 1
    allowed = [(o, o + len(x)) for o, x, _ in edits]
    bad = [dd for dd in diffs if not any(dd[0] >= lo and dd[1] <= hi for lo, hi in allowed)]
    other = {n: x for n, x in orig.raw.items() if n != '0'} == {n: x for n, x in mv.raw.items() if n != '0'}
    log(f'{MENUITEMS}: {len(data)} байт, блоков кода {nb} (разбираются), BIGF туда-обратно: {"да" if rt else "НЕТ"}; '
        f'Apt Data той же длины: {"да" if len(a0) == len(a1) else "НЕТ"}, отличий {len(diffs)}, все — в правках: '
        f'{"да" if not bad else "НЕТ " + str(bad[:4])}; прочие записи BIGF те же: {"да" if other else "НЕТ"}')
    if bad or not rt or len(a0) != len(a1) or not other:
        ok = False
    _, items, warn = analyse(f)
    if warn:
        ok = False
        log('  !! разбор:', warn[:3])
    vis = visible(items)
    for arr in (ROOT, 'objMainMenu.arrPlay', 'objMainMenu.itemSinglePlayer', 'objMainMenu.arrCustomize',
                'objMainMenu.arrMyMedia', 'objMainMenu.arrTMRosterManagement', 'objMainMenu.arrSettings'):
        log(f'  {arr.split(".")[-1]}: {", ".join(vis.get(arr, []))}')
    for arr, name, why in meta['hide']:
        if name in vis.get(arr, []):
            ok = False
            log(f'  ОШИБКА: {name} в {arr} всё ещё добавляется')
    if meta['exit'] != 'none' and EXIT_NAME not in vis.get(ROOT, []):
        ok = False
        log('  ОШИБКА: EXIT нет в корне')
    for key, text in meta.get('loc', {}).items():
        t = loc_text(p(work, LOC), legacy_src(LOC_META), key)
        log(f'  {LOC}: {key} = «{t}»')
        if t != text:
            ok = False
            log(f'  ОШИБКА: ждали «{text}»')
    log('ИТОГ: ' + ('всё сходится' if ok else 'ЕСТЬ ОШИБКИ'))
    if not ok:
        sys.exit(1)


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    args = sys.argv[1:]
    if not args:
        sys.exit(__doc__)
    cmd, rest = args[0], args[1:]
    {'list': cmd_list, 'build': cmd_build, 'check': cmd_check}.get(cmd, lambda a: sys.exit(__doc__))(rest)


if __name__ == '__main__':
    main()
