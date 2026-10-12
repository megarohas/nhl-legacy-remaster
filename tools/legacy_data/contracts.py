"""Настоящие контракты клубов НХЛ 2026/27 → exhibitionplayerbiotable (этап build-all «contracts»).

Вход — страницы контрактов 32 клубов, собранные пользователем и разобранные в JSON (только для личного использования,
в git их нет): game/work/contracts/screens/<КЛУБ>.json (другая папка — CONTRACTS_SCREENS). Группы Forwards / Defence /
Goaltenders и Non-roster * — игроки клуба; Retained, Buyout, Buried (удержание, выкуп, «закопанные» в АХЛ — они же есть
в Non-roster) для контракта игрока не берутся. Неподписанные RFA (кэп-хита нет) не трогаются.

    python tools/legacy_data/contracts.py db БАЗА.db [БАЗА.db …] [--dry-run] [--report ОТЧЁТ.json]
    python tools/legacy_data/contracts.py payroll БАЗА.db [--md ФАЙЛ.md]       # ведомости 32 клубов против потолка
    python tools/legacy_data/contracts.py save СЕЙВ [--write]                   # сохранённый состав (ROSTER …)

Сшивка со строкой exhibitionplayerbiotable (живые строки, вратарь ↔ вратарь) — по дате рождения и имени:
- точно: та же дата и то же имя без диакритики (имя может быть формой того же: Matt / Matthew), или то же имя после
  сведения транслитерации (Vasilevskiy / Vasilevsky, Yegor / Egor);
- спорные — не берутся, идут в отчёт: похожее имя при той же дате, то же имя при почти той же дате, две строки базы на
  одного игрока, одна строка базы на двух игроков страниц, нет даты рождения на странице.
Клуб: если в базе у игрока права другого клуба НХЛ (сделка после нашей сборки), игрок переводится в клуб страницы
(решение пользователя 12.10; --no-move — без перевода, только список): proteam и team; запись exhibitionrostertable
прежнего клуба уходит в новый — основной состав страницы → клуб НХЛ, Non-roster → его фарм-клуб АХЛ
(exhibitionteams.ahlaffiliate, rangelow −1), в запас (не одет, без звеньев и буквы). Его места в звеньях,
спецбригадах, буллитах и «одет» прежнего клуба получает запасной того же амплуа (лучший по OVR); своего нет (клубы
АХЛ/Европы/CHL одеты целиком) — запасной того же амплуа клуба той же лиги, где запасных больше всего, с номером
ушедшего (как roster/write.py free_vacancy). Буква — лучшему одетому полевому без буквы. Номер в новом клубе — свой,
занят — ближайший свободный (в отчёте). Затронутые клубы проверяются: места звеньев и одетые — как были, буквы те же,
новых повторов номеров нет, записей ≤ 40, key подряд. Без прав НХЛ в базе (proteam 0) или в пуле свободных агентов —
контракт не ставится, только список.

Поля (docs/legacy-port.md, «Продление контракта»; суммы в базе × 5000 $):
- отрезки контракта — подряд идущие сезоны с одним кэп-хитом, начиная с 2026/27; последний отрезок длится до года
  окончания (expiry.year; страница показывает только 5 сезонов);
- contractdollars = кэп-хит 2026/27, contractlength = длина 1-го отрезка, contractis2way — значок двустороннего
  контракта в 2026/27, contractismultiyear = длина > 1, contractstatus = 1 (сырое: rangelow −1, «на контракте»);
- contractneedsentrylevel = 0: у игры это «не подписан, первый контракт — новичковый» (ставит его драфт, у EA у всех
  подписанных 0); новичковые контракты (флаг Entry Level Contract) только считаются в отчёте;
- extensiondollars / extensionlength / extensionis2way — 2-й отрезок (подписанное продление); отрезков больше двух —
  берётся 2-й, игрок отмечается в отчёте; одного отрезка — продление 0;
- yearufa — у EA год рождения + 27; игра в конце контракта без продления делает игрока UFA, если yearufa ≤ год,
  иначе RFA (82B49E28). Поэтому при окончании UFA* в год Y — min(рожд. + 27, Y), при RFA* — max(рожд. + 27, Y + 1).
Повторный запуск ничего не меняет. После записи — проверка CRC (иначе база не тронута). draft_roster.db — заново
(draft_roster.py), как у других этапов.

payroll: ведомость клуба — как её считает игра (Cap Value на Select Team): сумма contractdollars игроков состава
клуба НХЛ (exhibitionrostertable), потолок 2026/27 — 104 млн. Отдельно — сколько в составе настоящих контрактов и
заглушек конвейера (контракт — заглушка по OVR, ужатая --payroll-max на этапе roster; этот этап идёт после него, и
настоящие суммы не ужимаются).

save: то же, что db, в сейве состава пользователя (ZlibV4, как tape_players.py); без --write — только отчёт. С --write —
копия сейва в game/work/legacy-data/backup-saves, после записи — проверка CRC и обёртки, при ошибке сейв возвращается.
"""
import glob
import json
import os
import sys
import time
from collections import Counter, defaultdict
from difflib import SequenceMatcher

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
os.environ.setdefault('NHL_GAME', 'legacy')
from tdb import SaveFile, Tdb, load_meta  # noqa: E402
from roster.build import same_first  # noqa: E402
from roster.common import SLOT_TEAM, TEAM_SLOT, norm  # noqa: E402
from roster.dbview import FLAGS, fld  # noqa: E402

W = os.environ.get('LEGACY_DATA_WORK', os.path.join(ROOT, 'game', 'work', 'legacy-data'))
SCREENS = os.environ.get('CONTRACTS_SCREENS', os.path.join(ROOT, 'game', 'work', 'contracts', 'screens'))
CACHE_META = os.path.join(ROOT, 'legacy-port', 'userdata', 'cache', 'guest', 'db', 'nhlng-meta.xml')
B, P, R, F = 'exhibitionplayerbiotable', 'exhibitionplayers', 'exhibitionrostertable', 'exhibitionfreeagents'
T, SAI, GAI = 'exhibitionteams', 'exhibitionskaterai', 'exhibitiongoalieai'
MAX_PER_TEAM = 40                # записей состава у клуба (roster/write.py): key = клуб × 40 + номер
SKIP_GROUPS = ('Retained', 'Buyout', 'Buried')
SEASON = 2026                    # 1-й сезон страниц (2026-27)
CAP = 104_000_000                # потолок 2026/27 (врезка legacy-port nhl_salary_cap)
UNIT = 5000
FIELDS = ('contractstatus', 'contractdollars', 'contractlength', 'contractis2way', 'contractismultiyear',
          'contractneedsentrylevel', 'yearufa', 'extensiondollars', 'extensionlength', 'extensionis2way')
# сведение транслитерации (после norm): длинное — раньше
TRANSLIT = (('iy', 'i'), ('yi', 'i'), ('ii', 'i'), ('kh', 'h'), ('ks', 'x'), ('yu', 'u'), ('ju', 'u'),
            ('ya', 'a'), ('ja', 'a'), ('ye', 'e'), ('yo', 'e'), ('jo', 'e'), ('ts', 'c'), ('tz', 'c'),
            ('ck', 'k'), ('y', 'i'), ('j', 'i'), ('w', 'v'), ('ph', 'f'))


def skeleton(s):
    s = norm(s)
    for a, b in TRANSLIT:
        s = s.replace(a, b)
    out = []
    for ch in s:                 # двойные буквы — одной
        if not out or out[-1] != ch:
            out.append(ch)
    return ''.join(out)


# --- страницы -----------------------------------------------------------------------------------------------------
def segments(p):
    """Отрезки контракта с 2026/27: [{'cap', 'n', 'two_way'}]; последний — до года окончания."""
    cap = p.get('cap') or []
    tw = p.get('two_way') or [False] * len(cap)
    segs = []
    for i, c in enumerate(cap):
        if c is None:
            break
        if segs and segs[-1]['cap'] == c:
            segs[-1]['n'] += 1
        else:
            segs.append({'cap': c, 'n': 1, 'two_way': bool(tw[i]) if i < len(tw) else False})
    seen = sum(s['n'] for s in segs)
    year = (p.get('expiry') or {}).get('year')
    if segs and year and seen == len(cap) and year - SEASON > seen:
        segs[-1]['n'] += year - SEASON - seen
    return segs


def year_ufa(p, birth_year):
    e = p.get('expiry') or {}
    kind, y = (e.get('type') or ''), e.get('year')
    base = birth_year + 27
    if y and kind.startswith('UFA'):
        return min(base, y)
    if y and kind.startswith('RFA'):
        return max(base, y + 1)
    return base


def terms(p):
    """Поля контракта по игроку страницы (None — кэп-хита 2026/27 нет: неподписанный)."""
    segs = segments(p)
    if not segs:
        return None
    s1 = segs[0]
    s2 = segs[1] if len(segs) > 1 else None
    by = int(p['birth'][:4]) if p.get('birth') else SEASON - 25
    return {
        'contractstatus': 1,
        'contractdollars': round(s1['cap'] / UNIT),
        'contractlength': min(15, s1['n']),
        'contractis2way': int(s1['two_way']),
        'contractismultiyear': int(s1['n'] > 1),
        'contractneedsentrylevel': 0,
        'yearufa': year_ufa(p, by) - 1900,
        'extensiondollars': round(s2['cap'] / UNIT) if s2 else 0,
        'extensionlength': min(15, s2['n']) if s2 else 0,
        'extensionis2way': int(s2['two_way']) if s2 else 0,
    }, segs


def load_pages(folder=SCREENS):
    files = sorted(glob.glob(os.path.join(folder, '*.json')))
    if not files:
        sys.exit(f'нет страниц контрактов: {folder}/*.json')
    out, seen = [], set()
    for f in files:
        d = json.load(open(f, encoding='utf-8'))
        team = d['team']
        for g, v in d['groups'].items():
            if g.startswith(SKIP_GROUPS):
                continue
            for p in v['players']:
                key = (team, p['name'], p.get('birth'), json.dumps(p.get('cap')))
                if key in seen:         # один игрок в двух группах страницы (VAN: Elias Pettersson 2004)
                    continue
                seen.add(key)
                out.append(dict(p, team=team, group=g))
    return out


# --- база ---------------------------------------------------------------------------------------------------------
class Base:
    """Живые строки био, связи, составы и пул свободных агентов базы или сейва."""

    def __init__(self, db):
        self.db = db
        g = lambda t, f, r: db.get(t, f, r)
        self.rows = [r for r in db.live_rows(B) if db.get_string(B, 'lastname', r)]
        created = {g(P, 'index', r) for r in db.live_rows(P) if 'table' in db.by_name[P]['fields'] and g(P, 'table', r) == 1}
        self.link = {g(P, 'index', r): g(P, 'playerid', r) for r in db.live_rows(P)}
        self.row_of_gid = {g(B, 'game_id', r): r for r in self.rows}
        made = {self.link[i] for i in created if i in self.link}
        self.rows = [r for r in self.rows if g(B, 'game_id', r) not in made]
        self.by_birth = defaultdict(list)
        self.by_name = defaultdict(list)
        for r in self.rows:
            self.by_birth[self.birth(r)].append(r)
            self.by_name[norm(self.first(r) + self.last(r))].append(r)
        self.roster = defaultdict(list)          # клуб НХЛ (0…31) → строки био состава
        for e in db.live_rows(R):
            t = g(R, 'team', e)
            r = self.row_of_gid.get(self.link.get(g(R, 'playerindex', e)))
            if t < 32 and r is not None:
                self.roster[t].append(r)
        self.fa = {self.row_of_gid.get(self.link.get(g(F, 'playerindex', e))) for e in db.live_rows(F)} - {None}

    def first(self, r):
        return self.db.get_string(B, 'firstname', r)

    def last(self, r):
        return self.db.get_string(B, 'lastname', r)

    def name(self, r):
        return f'{self.first(r)} {self.last(r)}'

    def birth(self, r):
        db = self.db
        return (db.get(B, 'year', r) + 1900, db.get(B, 'month', r) + 1, db.get(B, 'day', r) + 1)

    def goalie(self, r):
        return self.db.get(B, 'position', r) == 4

    def club(self, r):
        """Клуб НХЛ по правам (proteam − 1) или None."""
        t = self.db.get(B, 'proteam', r) - 1
        return t if 0 <= t < 32 else None


def name_fits(p_full, base, r):
    """Имя страницы и строки базы — одно: 'exact' / 'variant' (форма имени) / 'translit' / None."""
    f, l = norm(base.first(r)), norm(base.last(r))
    if norm(p_full) == f + l:
        return 'exact'
    pf = norm(p_full)
    if l and pf.endswith(l) and same_first(pf[:-len(l)], base.first(r)):
        return 'variant'
    if skeleton(p_full) == skeleton(base.first(r) + base.last(r)):
        return 'translit'
    if l and pf.endswith(l) and pf[:1] == f[:1]:
        return 'initial'                # Jacob / Jake, Zack / Zachary: та же фамилия и первая буква имени
    return None


def kind(group):
    """Амплуа по группе страницы: G, D или F (у вратарей страницы pos пустой)."""
    return 'G' if group.endswith('Goaltenders') else 'D' if group.endswith('Defence') else 'F'


def row_kind(base, r):
    pos = base.db.get(B, 'position', r)
    return 'G' if pos == 4 else 'D' if pos == 3 else 'F'


def match(pages, base):
    """→ (сшитые [(игрок страницы, строка, как)], спорные [(игрок, строки, почему)], не найдено [...])."""
    found, disputed, missing = [], [], []
    for p in pages:
        goalie = kind(p['group']) == 'G'
        club = TEAM_SLOT[p['team']]
        if not p.get('birth'):
            # без даты на странице: та же фамилия, тот же клуб и амплуа — одна строка (J.J. / Janis Jérôme Moser)
            rows = [r for r in base.rows if base.club(r) == club and row_kind(base, r) == kind(p['group'])
                    and norm(base.last(r)) and norm(p['name']).endswith(norm(base.last(r)))]
            if len(rows) == 1:
                found.append((p, rows[0], 'last+club, без даты'))
            else:
                (disputed if rows else missing).append((p, rows, 'нет даты рождения на странице'))
            continue
        b = tuple(int(x) for x in p['birth'].split('-'))
        same = [r for r in base.by_birth.get(b, []) if base.goalie(r) == goalie]
        hits = [(r, name_fits(p['name'], base, r)) for r in same]
        hits = [(r, how) for r, how in hits if how]
        if len(hits) > 1:
            mine = [(r, how) for r, how in hits if base.club(r) == club]
            hits = mine if len(mine) == 1 else hits
        if len(hits) == 1:
            found.append((p, hits[0][0], hits[0][1]))
            continue
        if hits:
            disputed.append((p, [r for r, _ in hits], 'две строки базы на одного игрока'))
            continue
        mine = [r for r in same if norm(p['name']).endswith(norm(base.last(r))) and base.club(r) == club]
        if len(mine) == 1:              # та же дата и фамилия, тот же клуб, имя другое (Robert / Cooper Flinton)
            found.append((p, mine[0], 'last+club'))
            continue
        similar = [r for r in same if SequenceMatcher(None, norm(p['name']), norm(base.name(r))).ratio() >= 0.75]
        if similar:
            disputed.append((p, similar, 'та же дата, похожее имя'))
            continue
        y, m, d = b
        near = [r for r in base.by_name.get(norm(p['name']), []) if base.goalie(r) == goalie and (
            (base.birth(r)[0] == y and (base.birth(r)[1] == m or base.birth(r)[2] == d))
            or (abs(base.birth(r)[0] - y) <= 1 and base.birth(r)[1:] == (m, d)))]
        if near:
            disputed.append((p, near, 'то же имя, почти та же дата'))
            continue
        missing.append((p, [], 'нет в базе'))
    # одна строка базы на двух игроков страниц. Тёзки одного клуба (VAN: Elias Pettersson 1998 и 2004) — разборщик
    # дал обоим одну дату: строка остаётся тому, чьё амплуа совпало, второй ищется по имени, клубу и амплуа
    by_row = defaultdict(list)
    for x in found:
        by_row[x[1]].append(x)
    out = []
    for r, xs in by_row.items():
        if len(xs) == 1:
            out.append(xs[0])
            continue
        fit = [x for x in xs if kind(x[0]['group']) == row_kind(base, r)]
        if len(fit) != 1:
            disputed += [(x[0], [r], 'одна строка базы на двух игроков страниц') for x in xs]
            continue
        out.append(fit[0])
        for p, _, _ in xs:
            if p is fit[0][0]:
                continue
            alt = [q for q in base.by_name.get(norm(p['name']), []) if q != r and base.club(q) == TEAM_SLOT[p['team']]
                   and row_kind(base, q) == kind(p['group'])]
            if len(alt) == 1:
                out.append((p, alt[0], 'тёзка: имя+клуб+амплуа, дата страницы чужая'))
            else:
                disputed.append((p, [r], 'одна строка базы на двух игроков страниц'))
    return out, disputed, missing


# --- применение ---------------------------------------------------------------------------------------------------
def plan(db, pages):
    """Совпадения, изменения и списки отчёта для базы или сейва db."""
    base = Base(db)
    found, disputed, missing = match(pages, base)
    who = lambda p: f"{p['team']} {p['name']} {p.get('birth')}"
    rep = {'found': len(found), 'disputed': [], 'missing': [], 'club_differs': [], 'no_rights': [], 'unsigned': [],
           'more_segments': [], 'translit': [], 'elc': 0, 'extensions': [], 'applied': 0, 'changed_values': 0}
    rep['disputed'] = [{'player': who(p), 'why': why, 'rows': [f'{base.name(r)} {base.birth(r)} proteam '
                                                              f'{SLOT_TEAM.get(base.club(r), "-")}' for r in rows]}
                       for p, rows, why in disputed]
    rep['missing'] = [who(p) for p, _, _ in missing]
    changes, real, moves = [], set(), []
    for p, r, how in found:
        t = terms(p)
        if t is None:
            rep['unsigned'].append(who(p))
            continue
        new, segs = t
        club, mine = base.club(r), TEAM_SLOT[p['team']]
        if how != 'exact' and how != 'variant':
            rep['translit'].append(f'{who(p)} ← {base.name(r)} ({how})')
        if club is None or r in base.fa:
            rep['no_rights'].append(f"{who(p)}: в базе {'свободный агент' if r in base.fa else 'без прав НХЛ'}")
            continue
        if club != mine:
            rep['club_differs'].append(f'{who(p)}: в базе {SLOT_TEAM[club]}')
            moves.append((p, r))
        if len(segs) > 2:
            rep['more_segments'].append(f"{who(p)}: " + ' → '.join(f"{s['cap'] / 1e6:g}×{s['n']}" for s in segs))
        if new['extensionlength']:
            rep['extensions'].append(f"{who(p)}: {segs[0]['cap'] / 1e6:g} млн × {segs[0]['n']} → продление "
                                     f"{segs[1]['cap'] / 1e6:g} млн × {new['extensionlength']}")
        rep['elc'] += 'Entry Level Contract' in (p.get('flags') or [])
        real.add(r)
        rep['applied'] += 1
        for f in FIELDS:
            old = db.get(B, f, r)
            if old != new[f]:
                changes.append((r, f, old, new[f]))
    rep['changed_values'] = len(changes)
    rep['changed_players'] = len({c[0] for c in changes})
    rep['moves'] = moves
    return base, changes, real, rep


def apply(db, changes):
    for r, f, old, new in changes:
        db.set(B, f, r, new)


# --- перевод в клуб по контракту ----------------------------------------------------------------------------------
def pos_kind(pos):
    return 'G' if pos == 4 else 'D' if pos == 3 else 'F'


class Rosters:
    """Записи exhibitionrostertable (живые строки подряд с начала — как у баз и сохранённых составов)."""

    def __init__(self, db, base):
        self.db, self.base = db, base
        rows = db.live_rows(R)
        if list(rows) != list(range(len(rows))):
            raise ValueError(f'{R}: живые записи не подряд (удалённые в середине) — перевод не делаю')
        self.fields = list(db.by_name[R]['fields'])
        self.orig = [{f: db.get(R, f, e) for f in self.fields} for e in rows]
        self.entries = [dict(e) for e in self.orig]
        self.touched = set()                    # ещё клубы, чьи составы менялись (донор запасного)
        self.ai = {}
        for t in (SAI, GAI):
            for x in db.live_rows(t):
                self.ai[db.get(t, 'game_id', x)] = (t, x)

    def row(self, e):
        return self.base.row_of_gid.get(self.base.link.get(e['playerindex']))

    def ovr(self, r):
        t, x = self.ai.get(self.db.get(B, 'game_id', r), (None, None))
        return self.db.get(t, fld('p_overall' if t == SAI else 'g_overall'), x) if t else 0

    def kind(self, e):
        r = self.row(e)
        return pos_kind(self.db.get(B, 'position', r)) if r is not None else None

    def team(self, t):
        return [e for e in self.entries if e['team'] == t]

    @staticmethod
    def busy(e):
        return e['rosterstatus'] or e['captain'] or any(e[f] for f in FLAGS)

    def renumber(self, t):
        for k, e in enumerate(sorted(self.team(t), key=lambda e: e['key'])):
            e['key'] = t * MAX_PER_TEAM + k

    def write(self):
        """Записи по возрастанию key на прежние строки; пишутся только изменившиеся поля."""
        self.entries.sort(key=lambda e: e['key'])
        n = 0
        for i, (e, o) in enumerate(zip(self.entries, self.orig)):
            for f in self.fields:
                if e[f] != o[f]:
                    self.db.set(R, f, i, e[f])
                    n += 1
        return n


def team_label(db, t):
    return SLOT_TEAM.get(t) or db.get_string(T, 'fullname', t) or str(t)


def dressed(e):
    return bool(e['rosterstatus'] or any(e[f] for f in FLAGS))


def move(ros, p, r, log):
    """Перевод игрока r в клуб страницы p: запись состава прежнего клуба → новому (основной состав страницы — клуб
    НХЛ, Non-roster — фарм-клуб АХЛ), его звенья, спецбригады, буллиты и «одет» в прежнем клубе — запасному того же
    амплуа (лучшему по OVR), буква — лучшему одетому полевому без буквы; номер в новом клубе без совпадения
    (занят — ближайший свободный). → строка отчёта или None (перевода нет, причина — в log)."""
    db, base = ros.db, ros.base
    club = TEAM_SLOT[p['team']]
    if p['group'].startswith('Non-roster'):
        new_t = db.get(T, 'ahlaffiliate', club) - 1        # rangelow −1: значение = сырое − 1 (teamid)
        if new_t < 32:
            log.append(f"{base.name(r)}: у {p['team']} нет фарм-клуба АХЛ — не переведён")
            return None
    else:
        new_t = club
    rights = base.club(r)
    cur = db.get(B, 'team', r) - 1
    olds = [e for e in ros.entries if ros.row(e) == r and e['team'] == cur]
    e_old = olds[0] if olds else None
    me = pos_kind(db.get(B, 'position', r))
    note = []
    if e_old is not None and e_old['team'] == new_t:
        return None
    if len(ros.team(new_t)) + 1 > MAX_PER_TEAM:
        log.append(f'{base.name(r)}: в {team_label(db, new_t)} уже {MAX_PER_TEAM} записей — не переведён')
        return None
    if e_old is not None and ros.busy(e_old):
        t_old = e_old['team']
        if dressed(e_old):
            free = [x for x in ros.team(t_old) if x is not e_old and not ros.busy(x) and ros.row(x) is not None]
            same = [x for x in free if ros.kind(x) == me]
            other = [x for x in free if me != 'G' and ros.kind(x) in ('F', 'D')]
            pool = same or other
            src = None
            if not same and t_old >= 32:
                # своего запасного того же амплуа нет (клубы АХЛ/Европы/CHL одеты целиком) — запасной того же амплуа
                # из клуба той же лиги, где запасных больше всего (как roster/write.py free_vacancy)
                league, spares = db.get(T, 'league', t_old), defaultdict(list)
                for x in ros.entries:
                    u = x['team']
                    if (u >= 32 and u != t_old and u != new_t and db.get(T, 'league', u) == league
                            and not ros.busy(x) and ros.kind(x) == me):
                        spares[u].append(x)
                if spares:
                    src = min(spares, key=lambda u: (-len(spares[u]), u))
                    pool = spares[src]
            if not pool:
                log.append(f'{base.name(r)}: в {team_label(db, t_old)} нет запасного на его места — не переведён')
                return None
            sp = max(pool, key=lambda x: (ros.ovr(ros.row(x)), -x['key']))
            for f in FLAGS:
                sp[f] = e_old[f]
            sp['rosterstatus'] = e_old['rosterstatus']
            if src is not None:                 # запасной другого клуба — в прежний клуб игрока, с его номером
                rs = ros.row(sp)
                sp['team'], sp['jersey'], sp['key'] = t_old, e_old['jersey'], t_old * MAX_PER_TEAM + 10 ** 6 - 1
                db.set(B, 'team', rs, t_old + 1)
                db.set(B, 'jersey', rs, e_old['jersey'])
                ros.renumber(src)
                ros.touched.add(src)
            slots = [f for f in FLAGS if e_old[f]]
            note.append(f"места в {team_label(db, t_old)} ({len(slots)} {' '.join(slots[:5])}"
                        f"{'…' if len(slots) > 5 else ''}{', одет' if e_old['rosterstatus'] else ''}) → "
                        f"{base.name(ros.row(sp))}{'' if sp in same else ' (другое амплуа)' if src is None else ''}"
                        f"{'' if src is None else ' из ' + team_label(db, src) + ', № ' + str(e_old['jersey'])}")
        if e_old['captain']:
            cand = [x for x in ros.team(t_old) if x is not e_old and dressed(x) and not x['captain']
                    and ros.kind(x) in ('F', 'D')]
            if cand:
                c = max(cand, key=lambda x: (ros.ovr(ros.row(x)), -x['key']))
                c['captain'] = e_old['captain']
                note.append(f"буква {'C' if e_old['captain'] == 1 else 'A'} в {team_label(db, t_old)} → "
                            f"{base.name(ros.row(c))}")
            else:
                note.append(f"буква {'C' if e_old['captain'] == 1 else 'A'} в {team_label(db, t_old)} снята")
    taken = {x['jersey'] for x in ros.team(new_t)}
    want = db.get(B, 'jersey', r) or (e_old or {}).get('jersey') or 0
    num = want
    if not 1 <= want <= 98 or want in taken:
        num = min((n for n in range(1, 99) if n not in taken), key=lambda n: (abs(n - want), n))
        note.append(f'№ {want} в {team_label(db, new_t)} занят → {num}')
    if e_old is not None:
        ros.entries.remove(e_old)
        ne = dict(e_old)
    else:
        links = [i for i, g in base.link.items() if g == db.get(B, 'game_id', r)]
        if not links:
            log.append(f'{base.name(r)}: нет связи в exhibitionplayers — не переведён')
            return None
        ne = {f: 0 for f in ros.fields}
        ne['playerindex'] = links[0]
    for f in FLAGS:
        ne[f] = 0
    ne.update(team=new_t, jersey=num, rosterstatus=0, captain=0, key=new_t * MAX_PER_TEAM + 10 ** 6)
    ros.entries.append(ne)
    if e_old is not None:
        ros.renumber(e_old['team'])
    ros.renumber(new_t)
    db.set(B, 'proteam', r, club + 1)
    db.set(B, 'team', r, new_t + 1)
    db.set(B, 'jersey', r, num)
    frm = team_label(db, e_old['team']) if e_old is not None else 'без клуба'
    return (f"{base.name(r)}: {frm} (права {SLOT_TEAM.get(rights, '—')}) → {team_label(db, new_t)}"
            f"{'' if new_t == club else ' (фарм ' + p['team'] + ')'}, № {num}, в запасе"
            + (f"; {'; '.join(note)}" if note else ''))


def team_state(ros, entries, t):
    te = [e for e in entries if e['team'] == t]
    dr = [e for e in te if any(e[f] for f in FLAGS)]
    caps = Counter(e['captain'] for e in te)
    return {'flags': {f: sum(e[f] for e in te) for f in FLAGS},
            'dressed': len(dr) if all(bool(e['rosterstatus']) == (e in dr) for e in te) else -1,
            'letters': (caps[1], caps[2]),
            'dup_numbers': sorted(n for n, c in Counter(e['jersey'] for e in te).items() if c > 1),
            'size': len(te)}


def check_teams(ros, teams):
    """Затронутые клубы не хуже, чем были: места звеньев — у стольких же, одетых столько же (rosterstatus = одет),
    те же буквы; новых повторов номеров нет; записей не больше 40; key без повторов."""
    bad = []
    for t in teams:
        a, b = team_state(ros, ros.orig, t), team_state(ros, ros.entries, t)
        name = team_label(ros.db, t)
        bad += [f'{name}: место {f} у {b["flags"][f]} (было {a["flags"][f]})' for f in FLAGS if a['flags'][f] != b['flags'][f]]
        if a['dressed'] != b['dressed']:
            bad.append(f'{name}: одетых {b["dressed"]} (было {a["dressed"]})')
        if a['letters'] != b['letters']:
            bad.append(f'{name}: буквы C/A {b["letters"]} (было {a["letters"]})')
        if set(b['dup_numbers']) - set(a['dup_numbers']):
            bad.append(f'{name}: повтор номеров {b["dup_numbers"]}')
        if b['size'] > MAX_PER_TEAM:
            bad.append(f'{name}: записей {b["size"]}')
    keys = [e['key'] for e in ros.entries]
    if len(set(keys)) != len(keys):
        bad.append('key повторяются')
    return bad


def do_moves(db, base, rep):
    """Переводы игроков, у которых в базе права другого клуба НХЛ → (строки отчёта, записано полей, клубы)."""
    if not rep['moves']:
        return [], 0, set()
    ros = Rosters(db, base)
    lines, log, teams = [], [], set()
    for p, r in rep['moves']:
        cur = db.get(B, 'team', r) - 1
        line = move(ros, p, r, log)
        if line:
            lines.append(line)
            teams |= {cur, db.get(B, 'team', r) - 1}
    bad = check_teams(ros, sorted(t for t in teams | ros.touched if t >= 0))
    if bad:
        sys.exit('перевод: проверки не прошли — ' + '; '.join(bad))
    return lines + [f'НЕ ПЕРЕВЕДЁН: {x}' for x in log], ros.write(), teams

def payroll(base, real, pages=None):
    """Ведомости 32 клубов по составу НХЛ: [(клуб, млн, настоящих, заглушек, сверх потолка, по странице млн)]."""
    page_total = Counter()
    for p in pages or []:
        if p['group'] in ('Forwards', 'Defence', 'Goaltenders') and p.get('cap') and p['cap'][0]:
            page_total[p['team']] += p['cap'][0]
    out = []
    for t in range(32):
        rows = base.roster[t]
        total = sum(base.db.get(B, 'contractdollars', r) for r in rows) * UNIT
        n_real = sum(1 for r in rows if r in real)
        out.append((SLOT_TEAM[t], total, n_real, len(rows) - n_real, total > CAP, page_total.get(SLOT_TEAM[t])))
    return out


def payroll_md(table):
    lines = ['| клуб | ведомость игры, млн | до потолка 104 | настоящих | заглушек | по странице (Forwards+Defence+G), млн |',
             '|---|---:|---:|---:|---:|---:|']
    for club, total, n_real, n_stub, over, page in sorted(table, key=lambda x: -x[1]):
        lines.append(f"| {club} | {total / 1e6:.2f} | {(CAP - total) / 1e6:+.2f}{' **сверх**' if over else ''} | "
                     f"{n_real} | {n_stub} | {f'{page / 1e6:.2f}' if page else '—'} |")
    over = [x[0] for x in sorted(table, key=lambda x: -x[1]) if x[4]]
    lines.append(f'\nсверх потолка: {len(over)} — {", ".join(over) or "нет"}; настоящих контрактов в составах '
                 f'{sum(x[2] for x in table)}, заглушек {sum(x[3] for x in table)}')
    return '\n'.join(lines)


def summary(path, rep, log=print):
    log(f"{path}: сшито {rep['found']}, контракт поставлен {rep['applied']} (изменено игроков "
        f"{rep['changed_players']}, значений {rep['changed_values']}); спорных {len(rep['disputed'])}, не найдено "
        f"{len(rep['missing'])}, неподписанных {len(rep['unsigned'])}, без прав НХЛ / в пуле СА {len(rep['no_rights'])}, "
        f"клуб в базе другой {len(rep['club_differs'])}; с продлением {len(rep['extensions'])}, отрезков > 2 "
        f"{len(rep['more_segments'])}, новичковых {rep['elc']}, по транслиту / другой форме имени {len(rep['translit'])}")


def meta_for(path):
    m = os.path.join(os.path.dirname(path), 'nhlng-meta.xml')
    if not os.path.isfile(m):
        m = os.path.join(W, 'out-ahl32', 'db', 'nhlng-meta.xml')
    return load_meta(m)


def moves_and_payroll(db, base, real, rep, pages, no_move):
    """Переводы (если не --no-move) и ведомости до/после у затронутых клубов НХЛ → (таблица, строки, полей, base)."""
    before = {c: t for c, t, *_ in payroll(base, real, pages)}
    lines, n, teams = ([], 0, set()) if no_move else do_moves(db, base, rep)
    if n:                                   # составы изменились — ведомость заново
        rows_real = {db.get(B, 'game_id', r) for r in real}
        base = Base(db)
        real = {r for r in base.rows if db.get(B, 'game_id', r) in rows_real}
    table = payroll(base, real, pages)
    clubs = sorted({SLOT_TEAM[t] for t in teams if t in SLOT_TEAM}
                   | {p['team'] for p, _ in rep['moves']} if lines else set())
    after = {c: t for c, t, *_ in table}
    rep['transfers'] = lines
    rep['payroll_moved'] = {c: [before[c], after[c]] for c in clubs}
    for s in lines:
        print('  перевод:', s)
    if clubs:
        print('  ведомости затронутых клубов: ' + ', '.join(f'{c} {before[c] / 1e6:.2f} → {after[c] / 1e6:.2f}'
                                                          for c in clubs))
    return table, n, base


def cmd_db(paths, dry, report, no_move=False):
    pages = load_pages()
    for path in paths:
        meta = meta_for(path)
        db = Tdb(open(path, 'rb').read(), meta)
        base, changes, real, rep = plan(db, pages)
        apply(db, changes)
        summary(path, rep)
        table, moved, base = moves_and_payroll(db, base, real, rep, pages, no_move)
        changes = changes or moved
        md = payroll_md(table)
        print(md)
        if report:
            dst = report if len(paths) == 1 else os.path.splitext(report)[0] + f'-{len(paths) and paths.index(path)}.json'
            os.makedirs(os.path.dirname(os.path.abspath(dst)), exist_ok=True)
            rep['payroll'] = [{'club': c, 'payroll': t, 'real': a, 'stub': s, 'over_cap': o, 'page_roster': pg}
                              for c, t, a, s, o, pg in table]
            rep['moves'] = [f"{p['team']} {p['name']} {p.get('birth')}" for p, _ in rep['moves']]
            json.dump(rep, open(dst, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
            open(os.path.splitext(dst)[0] + '-payroll.md', 'w', encoding='utf-8').write(md + '\n')
            print(f'отчёт → {dst}')
        if changes and not dry:
            db.fix()
            tmp = path + '.part'
            open(tmp, 'wb').write(bytes(db.d))
            if Tdb(open(tmp, 'rb').read(), meta).verify():
                os.remove(tmp)
                sys.exit(f'{path}: CRC не сходятся после записи — база не тронута')
            os.replace(tmp, path)
            print(f'{path}: записано, CRC — OK')
        elif changes:
            print('--dry-run: ничего не записано')


def cmd_payroll(path, md_out):
    pages = load_pages()
    db = Tdb(open(path, 'rb').read(), meta_for(path))
    base, changes, real, rep = plan(db, pages)
    if changes:
        print(f'внимание: в базе ещё не все настоящие контракты (изменений {len(changes)}) — ведомость как есть')
    md = payroll_md(payroll(base, real, pages))
    print(md)
    if md_out:
        open(md_out, 'w', encoding='utf-8').write(md + '\n')


def cmd_save(save, write, no_move=False):
    meta = load_meta(CACHE_META)
    raw = open(save, 'rb').read()
    sf = SaveFile(raw, meta)
    pages = load_pages()
    base, changes, real, rep = plan(sf.db, pages)
    apply(sf.db, changes)
    summary(save, rep)
    for r, f, old, new in changes[:6]:
        print(f'  {base.name(r)}: {f} {old} → {new}')
    if len(changes) > 6:
        print(f'  … ещё {len(changes) - 6}')
    table, moved, base = moves_and_payroll(sf.db, base, real, rep, pages, no_move)
    over = [c for c, t, *_ in table if t > CAP]
    print(f'  сверх потолка {CAP / 1e6:g} млн: {len(over)} — {", ".join(over) or "нет"}')
    if not write or not (changes or moved):
        print('без --write ничего не записано' if changes or moved else 'сейв уже совпадает')
        return
    out = sf.bytes(fix=True)
    bdir = os.path.join(ROOT, 'game', 'work', 'legacy-data', 'backup-saves',
                        f'{os.path.basename(save)}-{time.strftime("%Y%m%d-%H%M%S")}')
    os.makedirs(bdir, exist_ok=True)
    bak = os.path.join(bdir, os.path.basename(save) + '.bak')
    open(bak, 'wb').write(raw)
    open(save, 'wb').write(out)
    bad = SaveFile(open(save, 'rb').read(), meta).verify()
    if bad:
        open(save, 'wb').write(raw)
        sys.exit(f'проверка не прошла, сейв возвращён: {bad}')
    print(f'записано; CRC и обёртка — OK; копия до правки — {bak}')


def main(argv):
    sys.stdout.reconfigure(encoding='utf-8')
    if not argv or argv[0] not in ('db', 'payroll', 'save'):
        print(__doc__)
        sys.exit(2)
    cmd, rest = argv[0], argv[1:]
    opt = lambda name: rest[rest.index(name) + 1] if name in rest and rest.index(name) + 1 < len(rest) else None
    vals = {opt('--report'), opt('--md')}
    paths = [a for a in rest if not a.startswith('--') and a not in vals]
    if cmd == 'db':
        cmd_db(paths, '--dry-run' in rest, opt('--report'), '--no-move' in rest)
    elif cmd == 'payroll':
        cmd_payroll(paths[0], opt('--md'))
    else:
        cmd_save(paths[0], '--write' in rest, '--no-move' in rest)


if __name__ == '__main__':
    main(sys.argv[1:])
