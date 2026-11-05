"""Раскладка папки NHL Legacy Remaster: где лежит наш контент (cache:) — в обеих раскладках (docs/legacy-port.md,
«Папка content»; раскладку одобрил пользователь 05.11.2026, game/work/status/layout-proposal.md).

Старая раскладка: весь контент — одна папка <user_data_root>\\cache\\guest (игра видит её как cache:\\).
Новая (exe 0.17.0+, если рядом с exe есть папка content): content\\<часть>\\<путь игры>, части — по смыслу:

    database   db\\ (nhlng.db, nhlng-meta.xml, draft_roster.db)
    menus      fe\\ion\\game, fe\\ion\\main.big, fe\\ion\\fonts, fe\\ion\\artassets\\backgrounds, fe\\loc, fe\\resource_kernel …
    photos     fe\\ion\\artassets\\playerheads*, playerbackgrounds, playermenubackgrounds
    logos      fe\\ion\\artassets\\teamlogos*, twittericonsteam, rendering\\logo
    uniforms   rendering\\jersey, pant, sock; fe\\ion\\artassets\\jerseys, teamnumbers*
    heads      rendering\\player
    equipment  rendering\\playerstick, goaliestick, skate, goaliehelmet, puck; fe\\ion\\artassets\\createplayer;
               nhllegacy_masks.txt
    arenas     rendering\\stadium, icesurface, banner, jumbotron, crowddata, enviro, spotlight, prop, particle
    music      audio\\music, fe\\ion\\artassets\\eatrax*
    my         всё, чего нет в таблице, и свои правки поверх всего
Что пишет сама игра (*.ver в корне, admanager_cache_images) — cache\\game; highlights.sav — saves\\highlights.

Инструменты пишут и читают файлы cache: через cache_file(cache, rel): в старой раскладке это cache\\rel, в новой —
content\\<часть rel>\\rel. cache — то, что вернул cache_dir() установщика (tools/legacy_data/install_legacy_data.py):
папка cache\\guest или папка content.

    python tools/legacy_paths.py where [--install DIR]          # раскладка установки, где cache:
    python tools/legacy_paths.py part REL                       # в какую часть content попадёт путь игры REL
    python tools/legacy_paths.py migrate [--install DIR] [--from GUEST] [--write]
        # разложить userdata\\cache\\guest по content\\<часть> КОПИЕЙ (без --write — только план); написанное игрой —
        # в cache\\game, highlights.sav — в saves\\highlights, список шейдеров — в cache\\shaders. Старое не трогается.
        # Перевод установки пользователя — только с его «да» (CLAUDE.md: его данные — только копией).
        # --content-only — только наш контент (так собирает папку релиза scripts/make_dist.sh).
    python tools/legacy_paths.py verify [--install DIR] [--from GUEST]
        # после migrate: каждый файл на новом месте и совпадает по SHA-256 (список — content/migrated.sha256)

--install — папка с nhllegacy.exe и nhllegacy.toml, по умолчанию установка на этом ПК.
"""
import argparse
import filecmp
import os
import re
import shutil
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_INSTALL = os.path.join(REPO, 'nhl-legacy-port', 'out', 'build', 'win-amd64-release')
MARKER = 'order.txt'  # в корне content: порядок частей (my всегда первая)

# Правила: путь игры (нижний регистр, «/») → часть. Длиннее — главнее. Хвост «*» — префикс имени последней части
# (teamlogos* = teamlogos, teamlogoscalendar, teamlogossmall …). Решение пользователя 05.11.2026: эти имена и деление.
RULES = [
    ('db', 'database'),
    ('fe/loc', 'menus'), ('fe/ion/game', 'menus'), ('fe/ion/main.big', 'menus'), ('fe/ion/fonts', 'menus'),
    ('fe/ion/artassets/backgrounds', 'menus'), ('fe/resource_kernel', 'menus'), ('fe/salarydata.bin', 'menus'),
    ('fe/ion/artassets/playerheads*', 'photos'), ('fe/ion/artassets/playerbackgrounds', 'photos'),
    ('fe/ion/artassets/playermenubackgrounds', 'photos'),
    ('fe/ion/artassets/teamlogos*', 'logos'), ('fe/ion/artassets/twittericonsteam', 'logos'), ('rendering/logo', 'logos'),
    ('fe/ion/artassets/jerseys', 'uniforms'), ('fe/ion/artassets/teamnumbers*', 'uniforms'),
    ('rendering/jersey', 'uniforms'), ('rendering/pant', 'uniforms'), ('rendering/sock', 'uniforms'),
    ('rendering/player', 'heads'),
    ('rendering/playerstick', 'equipment'), ('rendering/goaliestick', 'equipment'), ('rendering/skate', 'equipment'),
    ('rendering/goaliehelmet', 'equipment'), ('rendering/puck', 'equipment'),
    ('fe/ion/artassets/createplayer', 'equipment'), ('nhllegacy_masks.txt', 'equipment'),
    ('rendering/stadium', 'arenas'), ('rendering/icesurface', 'arenas'), ('rendering/banner', 'arenas'),
    ('rendering/jumbotron', 'arenas'), ('rendering/crowddata', 'arenas'), ('rendering/enviro', 'arenas'),
    ('rendering/spotlight', 'arenas'), ('rendering/prop', 'arenas'), ('rendering/particle', 'arenas'),
    ('audio/music', 'music'), ('fe/ion/artassets/eatrax*', 'music'),
]
PARTS = ['database', 'menus', 'photos', 'logos', 'uniforms', 'heads', 'equipment', 'arenas', 'music']
MY = 'my'
GAME_WRITTEN = [re.compile(r'[^/]+\.ver'), re.compile(r'admanager_cache_images(/.*)?')]  # пишет сама игра
PERSONAL = ['highlights.sav']                                                          # её же, но личное


def norm(rel):
    return rel.replace('\\', '/').strip('/')


def part_for(rel):
    """Часть content для пути игры rel (db/nhlng.db → database); my — если правила нет."""
    r = norm(rel).lower()
    best, best_len = MY, -1
    for pat, part in RULES:
        if pat.endswith('*'):
            head, _, stem = pat[:-1].rpartition('/')
            comps = r.split('/')
            hcomps = head.split('/') if head else []
            ok = (len(comps) > len(hcomps) and comps[:len(hcomps)] == hcomps and comps[len(hcomps)].startswith(stem))
            n = len(pat)
        else:
            ok = r == pat or r.startswith(pat + '/')
            n = len(pat)
        if ok and n > best_len:
            best, best_len = part, n
    return best


def kind_of(rel):
    """content | game (пишет игра, cache\\game) | personal (saves\\highlights)."""
    r = norm(rel).lower()
    if r in PERSONAL:
        return 'personal'
    if any(p.fullmatch(r) for p in GAME_WRITTEN):
        return 'game'
    return 'content'


def is_content_root(cache):
    return os.path.isfile(os.path.join(cache, MARKER)) or (
        os.path.basename(os.path.normpath(cache)).lower() == 'content' and os.path.isdir(cache))


def cache_file(cache, rel):
    """Файл cache: для чтения и записи инструментом. cache — папка cache\\guest (старая раскладка) или content."""
    parts = norm(rel).split('/')
    if is_content_root(cache):
        return os.path.join(cache, part_for(rel), *parts)
    return os.path.join(cache, *parts)


def legacy_cache(install=None):
    """cache: установки для инструментов: папка content (новая раскладка) или cache\\guest (старая)."""
    return Install(install).cache()


def legacy_file(rel, install=None):
    """Файл rel в cache: установки: тот, что возьмёт игра (если есть), иначе — куда его класть."""
    inst = Install(install)
    return inst.find(rel) or cache_file(inst.cache(), rel)


def _toml_value(path, key):
    try:
        text = open(path, encoding='utf-8-sig').read()
    except OSError:
        return None
    m = re.search(rf'(?m)^\s*{re.escape(key)}\s*=\s*"([^"]*)"', text)
    return m.group(1) if m else None


class Install:
    """Пути установки: exe, content, cache, saves, userdata (как в nhllegacy_app.h / nhllegacy_content.cpp)."""

    def __init__(self, install=None):
        self.dir = os.path.abspath(install or DEFAULT_INSTALL)
        toml = os.path.join(self.dir, 'nhllegacy.toml')
        rel = lambda p: os.path.normpath(p if os.path.isabs(p) else os.path.join(self.dir, p))
        cr = _toml_value(toml, 'nhl_content_root')
        self.content = rel('content' if cr is None else cr) if cr != '' else None
        self.userdata = rel(_toml_value(toml, 'user_data_root') or 'userdata')
        sr = _toml_value(toml, 'nhl_saves_root')
        self.saves = rel('saves' if sr is None else sr) if sr != '' else None
        cache = _toml_value(toml, 'cache_root')
        self.new = bool(self.content) and os.path.isdir(self.content)
        self.cache_root = rel(cache) if cache else (os.path.join(self.dir, 'cache') if self.new else
                                                    os.path.join(self.userdata, 'cache'))
        self.guest = os.path.join(self.userdata, 'cache', 'guest')

    def cache(self):
        """То, что инструменты передают в cache_file(): content (новая раскладка) или cache\\guest (старая)."""
        return self.content if self.new else self.guest

    def find(self, rel):
        """Файл, который игра возьмёт для rel (порядок как в exe: highlights, cache\\game, my, части)."""
        r = norm(rel)
        if not self.new:
            p = os.path.join(self.guest, *r.split('/'))
            return p if os.path.exists(p) else None
        cands = []
        if r.lower() in PERSONAL and self.saves:
            cands.append(os.path.join(self.saves, 'highlights', r))
        cands.append(os.path.join(self.cache_root, 'game', *r.split('/')))
        cands.append(os.path.join(self.content, MY, *r.split('/')))
        for part in order(self.content):
            cands.append(os.path.join(self.content, part, *r.split('/')))
        return next((c for c in cands if os.path.exists(c)), None)


def order(content):
    """Части content по порядку поиска после my: order.txt, затем остальные по алфавиту (как PackOrder в exe)."""
    listed = []
    p = os.path.join(content, MARKER)
    if os.path.isfile(p):
        for line in open(p, encoding='utf-8-sig'):
            s = line.strip()
            if s and not s.startswith('#') and s.lower() != MY and os.path.isdir(os.path.join(content, s)):
                listed.append(s)
    rest = sorted((d for d in os.listdir(content) if os.path.isdir(os.path.join(content, d)) and d.lower() != MY
                   and not d.startswith('.') and d.lower() not in (x.lower() for x in listed)), key=str.lower)
    return listed + rest


ORDER_TEXT = '''# Порядок частей content (NHL Legacy Remaster): файл, который есть в двух частях, берётся из верхней.
# content\\my всегда первая, её здесь не пишут. Части, которых нет в списке, идут после — по алфавиту.
# docs/legacy-port.md, «Папка content».
''' + '\n'.join(PARTS) + '\n'


def plan_migrate(guest):
    """[(rel, куда: ('content', часть) | ('game', None) | ('personal', None))] для всех файлов guest."""
    out = []
    for d, _, fs in os.walk(guest):
        for f in fs:
            full = os.path.join(d, f)
            rel = norm(os.path.relpath(full, guest))
            k = kind_of(rel)
            out.append((rel, (k, part_for(rel) if k == 'content' else None)))
    return sorted(out)


def migrate(inst, guest, write, content_only=False):
    plan = plan_migrate(guest)
    count = {}
    for rel, (k, part) in plan:
        key = part if k == 'content' else ('cache\\game' if k == 'game' else 'saves\\highlights')
        count[key] = count.get(key, 0) + 1
    print(f'{guest}: {len(plan)} файлов')
    for k in sorted(count):
        print(f'  {k}: {count[k]}')
    if not write:
        print('план, ничего не записано (--write — копировать)')
        return 0
    content = inst.content or os.path.join(inst.dir, 'content')
    if content_only:  # папка релиза (make_dist.sh): только наш контент, без кэша игры и личного
        plan = [x for x in plan if x[1][0] == 'content']
    elif not inst.saves:
        sys.exit('nhl_saves_root пуст: highlights.sav некуда класть — включите saves (по умолчанию saves рядом с exe)')
    copied = same = clash = 0
    for rel, (k, part) in plan:
        src = os.path.join(guest, *rel.split('/'))
        if k == 'content':
            dst = os.path.join(content, part, *rel.split('/'))
        elif k == 'game':
            dst = os.path.join(inst.dir, 'cache', 'game', *rel.split('/'))
        else:
            dst = os.path.join(inst.saves, 'highlights', *rel.split('/'))
        if os.path.exists(dst):
            if filecmp.cmp(src, dst, shallow=False):
                same += 1
            else:
                clash += 1
                print(f'  уже есть другой: {dst} — не тронут')
            continue
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)
        copied += 1
    for part in PARTS + [MY]:
        os.makedirs(os.path.join(content, part), exist_ok=True)
    mp = os.path.join(content, MARKER)
    if not os.path.exists(mp):
        open(mp, 'w', encoding='utf-8', newline='\n').write(ORDER_TEXT)
    sh = os.path.join(inst.userdata, 'cache', 'shaders', 'shareable')
    if os.path.isdir(sh) and not content_only:
        to = os.path.join(inst.dir, 'cache', 'shaders', 'shareable')
        os.makedirs(to, exist_ok=True)
        for f in os.listdir(sh):
            if not os.path.exists(os.path.join(to, f)):
                shutil.copy2(os.path.join(sh, f), os.path.join(to, f))
    print(f'скопировано {copied}, уже было таких же {same}, конфликтов {clash}; {guest} не тронут')
    return 1 if clash else 0


def new_place(inst, rel, kind, part):
    if kind == 'content':
        return os.path.join(inst.content or os.path.join(inst.dir, 'content'), part, *rel.split('/'))
    if kind == 'game':
        return os.path.join(inst.dir, 'cache', 'game', *rel.split('/'))
    return os.path.join(inst.saves, 'highlights', *rel.split('/'))


def verify(inst, guest, content_only=False):
    """Каждый файл guest на своём новом месте и совпадает по SHA-256; список — <content>/migrated.sha256."""
    import hashlib

    def sha(p):
        h = hashlib.sha256()
        with open(p, 'rb') as f:
            for b in iter(lambda: f.read(1 << 20), b''):
                h.update(b)
        return h.hexdigest()

    plan = [x for x in plan_migrate(guest) if not content_only or x[1][0] == 'content']
    missing, differ, lines = [], [], []
    for rel, (k, part) in plan:
        src, dst = os.path.join(guest, *rel.split('/')), new_place(inst, rel, k, part)
        if not os.path.exists(dst):
            missing.append(rel)
            continue
        a, b = sha(src), sha(dst)
        if a != b:
            differ.append(rel)
        lines.append(f'{b}  {os.path.relpath(dst, inst.dir).replace(os.sep, "/")}')
    out = os.path.join(inst.content or os.path.join(inst.dir, 'content'), 'migrated.sha256')
    open(out, 'w', encoding='utf-8', newline='\n').write('\n'.join(lines) + '\n')
    print(f'{len(plan)} файлов: нет на новом месте {len(missing)}, отличаются {len(differ)}; список — {out}')
    for r in (missing + differ)[:20]:
        print('  ', r)
    return 1 if missing or differ else 0


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('cmd', choices=['where', 'part', 'migrate', 'verify'])
    p.add_argument('rel', nargs='?', help='part: путь игры, например rendering/jersey/x.rx2')
    p.add_argument('--install', help='папка установки (nhllegacy.exe, nhllegacy.toml)')
    p.add_argument('--from', dest='src', help='migrate: откуда (по умолчанию <user_data_root>/cache/guest)')
    p.add_argument('--write', action='store_true', help='migrate: копировать (без него — план)')
    p.add_argument('--content-only', action='store_true',
                   help='migrate: только наш контент (для папки релиза): без написанного игрой и highlights.sav')
    a = p.parse_args()
    inst = Install(a.install)
    if a.cmd == 'where':
        if inst.new:
            print(f'content (0.17.0+): {inst.content}; кэш игры {os.path.join(inst.cache_root, "game")}; '
                  f'части после my: {", ".join(order(inst.content))}')
        else:
            print(f'старая раскладка: cache: = {inst.guest}')
    elif a.cmd == 'part':
        if not a.rel:
            p.error('part: укажите путь игры')
        k = kind_of(a.rel)
        print(part_for(a.rel) if k == 'content' else ('cache\\game' if k == 'game' else 'saves\\highlights'))
    else:
        guest = os.path.abspath(a.src) if a.src else inst.guest
        if not os.path.isdir(guest):
            sys.exit(f'нет папки {guest}')
        if a.cmd == 'verify':
            sys.exit(verify(inst, guest, a.content_only))
        sys.exit(migrate(inst, guest, a.write, a.content_only))


if __name__ == '__main__':
    main()
