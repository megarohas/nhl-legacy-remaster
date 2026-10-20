"""Год 2015 → год сезона (2026; NHL_SEASON, tools/season.py) в надписях NHL Legacy: копирайты и юридический текст
(локализация) — файлы для cache: Legacy. Имя файла и папки year2026 — историческое.

    python year2026_legacy.py build [--work DIR] [--no-out]
        # → WORK (game/work/legacy-data/year2026/build/<набор>/fe/loc/NHL_ENG_US.db) и сами наборы legacy-data:
        #   out и накладка out-ahl32 (у каждого своя локализация). Список своих файлов —
        #   game/work/legacy-data/year2026/files.txt
    python year2026_legacy.py check [DIR]     # собранное против входа: отличаются только ключи EDITS, текст — как ждали
    python year2026_legacy.py scan [DB]       # все ключи локализации с «2015» (по умолчанию — out)

Разбор 12.10.2026 (docs/fe-menu-legacy.md §12): «2015» в Legacy есть только в строках локализации
fe/loc/NHL_ENG_US.db. В роликах Apt (всех архивах), exe и текстурах заставок и юридических экранов года нет.
Подпись внизу стартового экрана — не картинка, а текст: 03_pressstart.big ставит в поле txtCopyright строку
ltxt("TitleScreen_Copyright") шрифтом игры. Поэтому правка строки меняет и стартовый экран.

Правка — locdb put: своя строка в конец пула, чужие ключи с тем же текстом не меняются; уже такой текст — без
правки (повторная сборка ничего не добавляет). Меняются только слова с годом; остальной текст ключа — как был.
Не меняются (решение координатора 12.10): Moments Live («2014-2015 Season», даты матчей 2015 года), названия
старых форм («2014-15 Home»), «NHL® 15/16» (названия игр в онлайн-пунктах), чужие © (Naxos, On2), ачивка
«Raise Your Banner '15», задача «2014/2015 NHL® Rookie Entry Draft».

Этап menu в tools/legacy_data/build-all.sh — после menuitems_legacy.py. Накладки out-nhl24 и out-nhl24-ahl32 этап
nhl24 собирает из локализации out и out-ahl32, поэтому идёт после menu и правки переносит сам.

Только стандартная библиотека. Локализация — tools/locdb.py.
"""
import hashlib, json, os, shutil, sys

TOOLS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TOOLS)
import gameprofile         # noqa: E402
import season              # noqa: E402  (tools/season.py: NHL_SEASON, по умолчанию 2026)

P = gameprofile.get('legacy')
WORK = P.work_dir('year2026', 'build')
FILES = P.work_dir('year2026', 'files.txt')
LOC = 'fe/loc/NHL_ENG_US.db'
LOC_META = 'fe/loc/nhl_eng_us-meta.xml'
SETS = {'out': P.out, 'out-ahl32': os.path.join(os.path.dirname(P.out), 'out-ahl32')}

Y = season.YEAR            # год в надписях = первый год сезона (вход всегда сток: «2015» из collect)

# (ключ, было, стало, где видно) — замена подстроки; знак ©, пробелы и порядок слов — как у EA
EDITS = [
    ('TitleScreen_Copyright', '© 2015 ', f'© {Y} ', 'стартовый экран (03_pressstart.big, txtCopyright)'),
    ('LegalText', '© NHL 2015.', f'© NHL {Y}.', 'юридический экран при запуске (01_legal.big)'),
    ('CREDITS_NHL_LEGAL_3', '© NHL 2015 ', f'© NHL {Y} ', 'титры (fe/credits/credits)'),
    ('CREDITS_AHL_LEGAL_2', '©2015 AHL', f'©{Y} AHL', 'титры'),
    ('CREDITS_CHL_LEGAL_2', '©2015 CHL', f'©{Y} CHL', 'титры'),
    ('License_NHL', '© NHL 2015.', f'© NHL {Y}.', 'ролики fe не используют — для порядка'),
    ('TXT_ARCADE_TitleScreen_Copyright', '© 2015 ', f'© {Y} ', 'ролики fe не используют — для порядка'),
    ('TXT_HELP_FREE_AGENT_0_BLURB3', '575K for 2015.', f'850K for {Y}.',
     'подсказка о свободных агентах (exe); 850K — как nhl_salary_min порта (другая сумма — поменять и тут)'),
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


def md5(path):
    return hashlib.md5(open(path, 'rb').read()).hexdigest()


def open_loc(path):
    import locdb
    from tdb_read import load_meta
    return locdb.LocDb(open(path, 'rb').read(), load_meta(legacy_src(LOC_META)))


def text_of(loc, key):
    f = loc.find_all(key)
    return loc.text(loc.text_off_at(f[0])) if f else None


def all_texts(loc):
    """{hashid-ключ (имя записи): текст} — для сравнения двух локализаций."""
    return {sid: loc.text(off) if off != 0xFFFFFFFF else None for _, sid, off in loc.rows()}


def apply(src, dst):
    """Правки EDITS: src → dst. → [(ключ, было, стало | None — уже)]."""
    loc = open_loc(src)
    done = []
    for key, old, new, _ in EDITS:
        t = text_of(loc, key)
        if t is None:
            raise SystemExit(f'{src}: нет ключа {key}')
        if old in t:
            nt = t.replace(old, new)
            loc.put(key, nt)
            done.append((key, t, nt))
        elif new in t:
            done.append((key, t, None))
        else:
            raise SystemExit(f'{src}: {key} — нет ни «{old}», ни «{new}»: «{t}»')
    bad = loc.check()
    if bad:
        raise SystemExit(f'{src}: ' + '; '.join(bad[:3]))
    loc.db.fix()
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    open(dst, 'wb').write(loc.db.d)
    return done


def short(t, key):
    """Кусок текста вокруг правки — для журнала (у LegalText и License_NHL строки длинные)."""
    olds = [o for k, o, n, _ in EDITS if k == key] + [n for k, o, n, _ in EDITS if k == key]
    for s in olds:
        i = t.find(s)
        if i >= 0:
            a, b = max(0, i - 25), min(len(t), i + len(s) + 25)
            return (('…' if a else '') + t[a:b] + ('…' if b < len(t) else '')).replace(chr(10), ' ')
    return t[:60].replace(chr(10), ' ')


def cmd_build(args):
    work = opt(args, '--work', WORK)
    if os.path.isdir(work):
        shutil.rmtree(work)
    os.makedirs(work)
    lines, built = [f'year2026_legacy build: 2015 → {Y} в локализации'], {}
    for name, base in SETS.items():
        src = p(base, LOC)
        if not os.path.exists(src):
            if name == 'out':
                raise SystemExit(f'нет {src} (локализация legacy-data: build-all.sh collect)')
            lines.append(f'{name}: нет {LOC} — пропуск')
            continue
        inp = p(os.path.join(work, name, 'input'), LOC)       # вход — для check
        os.makedirs(os.path.dirname(inp), exist_ok=True)
        shutil.copyfile(src, inp)
        dst = p(os.path.join(work, name), LOC)
        lines.append(f'{name}/{LOC}:')
        for key, t, nt in apply(src, dst):
            lines.append(f'  {key}: «{short(t, key)}» → «{short(nt, key)}»' if nt else f'  {key}: «{short(t, key)}» (уже)')
        built[name] = {'input_md5': md5(inp), 'md5': md5(dst)}
    json.dump({'edits': [list(e) for e in EDITS], 'sets': built, 'files': [LOC]},
              open(os.path.join(work, 'build.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    open(os.path.join(work, 'build.log'), 'w', encoding='utf-8').write('\n'.join(lines) + '\n')
    for x in lines:
        log(x)
    if '--no-out' in args:
        return
    for name in built:
        shutil.copyfile(p(os.path.join(work, name), LOC), p(SETS[name], LOC))
        log(f'→ {p(SETS[name], LOC)}')
    os.makedirs(os.path.dirname(FILES), exist_ok=True)
    with open(FILES, 'w', encoding='utf-8', newline='\n') as f:
        f.write(LOC + '\n')
    log(f'список — {FILES}')


def cmd_check(args):
    work = args[0] if args and not args[0].startswith('--') else WORK
    meta = json.load(open(os.path.join(work, 'build.json'), encoding='utf-8'))
    want = {k: (o, n) for k, o, n, _ in meta['edits']}
    ok = True
    for name, info in meta['sets'].items():
        a = open_loc(p(os.path.join(work, name, 'input'), LOC))
        b = open_loc(p(os.path.join(work, name), LOC))
        ta, tb = all_texts(a), all_texts(b)
        diff = sorted(k for k in set(ta) | set(tb) if ta.get(k) != tb.get(k))
        extra = [k for k in diff if k.lower() not in {w.lower() for w in want}]
        bad = []
        for key, (old, new) in want.items():
            t0, t1 = text_of(a, key), text_of(b, key)
            exp = t0.replace(old, new)
            if t1 != exp or old in t1:
                bad.append(f'{key}: «{short(t1, key)}», ждали «{short(exp, key)}»')
        chk = b.check()
        in_out = os.path.exists(p(SETS[name], LOC)) and md5(p(SETS[name], LOC)) == info['md5']
        log(f'{name}/{LOC}: записей {a.table["rows"]} → {b.table["rows"]}, другой текст у {len(diff)} ключей; '
            f'вне правок: {"нет" if not extra else extra[:5]}; правки как ждали: {"да" if not bad else "НЕТ"}; '
            f'locdb check: {"OK" if not chk else chk[:2]}; в {name}: '
            f'{"этот файл" if in_out else "другой (build --no-out или его пересобрали после)"}')
        for x in bad:
            log('  ОШИБКА', x)
        ok = ok and not extra and not bad and not chk
        left = [k for k, t in tb.items() if t and '2015' in t]
        log(f'  «2015» осталось у {len(left)} ключей: {", ".join(sorted(left))}')
    log('ИТОГ: ' + ('всё сходится' if ok else 'ЕСТЬ ОШИБКИ'))
    if not ok:
        sys.exit(1)


def cmd_scan(args):
    db = args[0] if args else p(P.out, LOC)
    loc = open_loc(db)
    for _, sid, off in loc.rows():
        if off == 0xFFFFFFFF:
            continue
        t = loc.text(off)
        if '2015' in t:
            log(f'{sid}\t{short(t, sid) if any(sid == k for k, *_ in EDITS) else t[:160]}')


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    args = sys.argv[1:]
    if not args:
        sys.exit(__doc__)
    cmd, rest = args[0], args[1:]
    {'build': cmd_build, 'check': cmd_check, 'scan': cmd_scan}.get(cmd, lambda a: sys.exit(__doc__))(rest)


if __name__ == '__main__':
    main()
