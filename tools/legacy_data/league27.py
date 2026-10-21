"""Составы лиг из базы NHL 27 → NHL Legacy (out и out-ahl32): этапы build-all «chl» и «europe».

Решения пользователя 21.10.2026: составы CHL обновить целиком по NHL 27 (имена, даты рождения, атрибуты, контракты и
права, номера, звенья); европейские лиги — там, где у нас ещё составы базы EA 2015 года (SHL, DEL, Extraliga, NL; Liiga
конвейер уже собрал с liiga.fi, Норвегии в NHL 27 нет); НХЛ и АХЛ не трогать.

    python tools/legacy_data/league27.py chl|europe [--only build|write|clubs|draft] [--db27 nhl_game.db]

Пресеты (PRESETS): лиги NHL 27, их лиги в Legacy, слоты Legacy, переехавшие клубы.

1. **Игроки** (build) — все игроки составов клубов этих лиг NHL 27 (tools/roster/nhl27.py). Клуб → слот Legacy своей
   лиги: явно (`renamed`), по аббревиатуре, по названию; оставшиеся слоты (клуб выбыл из лиги или исчез) — оставшимся
   клубам NHL 27 по порядку, с новым названием. Клубам NHL 27, кому слота нет (Penticton Vees — 23-й клуб WHL; HC
   Ajoie и Rapperswil-Jona — 13-й и 14-й клубы NL), игроки идут только в добор (ниже). Сопоставление с базой — как у
   конвейера (roster/match.py: имя и дата рождения). Кто в базе в составе клуба вне этих лиг (НХЛ, АХЛ, Liiga, CHL…)
   или в пуле свободных агентов, остаётся там (в отчёт): наши составы уровня НХЛ свежее NHL 27.
2. **Запись** (write) — League27Writer (на основе roster/ahl2026_write.py AhlWriter): переписываются только составы
   клубов этих лиг. Новый игрок занимает строку прежнего игрока этих клубов (старшие первыми), потом — игрока без клуба;
   пул свободных агентов и составы других клубов не трогаются. Прежние игроки, кому места нет, — без клуба и контракта.
   У игрока из NHL 27 копируются как есть:
   - биография (все поля Legacy, кроме арта и головы): имя, дата и место рождения, гражданство, рост, вес, хват,
     амплуа, драфт, права (proteam, клубы НХЛ — NHL_SLOT), контракт, игры, новичок; у юниоров CHL juniorteam и
     juniorleague — свой клуб и его лига (как у юниоров базы EA 2015 года; в NHL 27 у них пусто), у остальных — нет;
   - атрибуты (значение − 36, ratings.BASE), стиль, тенденции, черты, рост (growth*); потенциал — nhl27.POTENTIAL;
   - звенья, большинство, меньшинство, овертайм, буллиты, одетые — из составов NHL 27 (nhl27.legacy_flag); буквы — из
     NHL 27, недостающие — как у конвейера (Writer.letters); номера — по номерам NHL 27 (Writer.numbers).
   Новым игрокам: artid — свободный (таблица legacy-data/league27/artid-registry.json, общая у out и out-ahl32),
   голова — типовая того же тона кожи (skincolor NHL 27), портрета нет (этап портретов NHL 27 — потом).
3. **Клубы** (clubs) — у слотов с другим клубом или названием: название, город, аббревиатура и строки локализации (по
   artabbr слота); арены — название и город из NHL 27, если строка арены не общая с другим клубом. Логотипы не меняются.
4. draft_roster.db — заново.

Повторный запуск на той же базе ничего не меняет (сопоставление находит тех же игроков). Рабочие файлы —
game/work/legacy-data/league27/<пресет>/<out|out-ahl32>/ (players.json, match.json, write.json). Документация —
docs/legacy-data.md, «Лиги из NHL 27».
"""
import json
import os
import shutil
import sys
import zlib
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
REPO = os.path.dirname(TOOLS)
sys.path.insert(0, TOOLS)
os.environ['NHL_GAME'] = 'legacy'
from roster.common import set_game  # noqa: E402
set_game('legacy')
from roster import match as match_mod  # noqa: E402
from roster import nhl27  # noqa: E402
from roster import ovrformula  # noqa: E402
from roster import write as W  # noqa: E402
from roster.ahl2026_write import AhlWriter  # noqa: E402
from roster.common import Paths, fit_utf8, norm, read_json, write_json  # noqa: E402
from roster.dbview import (B, FLAGS, G, POS_NAME, S, SPECIAL, T, View, fld)  # noqa: E402
from roster.ratings import BASE, GK, SK, cls  # noqa: E402
from tdb import Tdb, load_meta  # noqa: E402

W_DIR = os.path.abspath(os.environ.get("LEGACY_DATA_WORK") or os.path.join(REPO, "game", "work", "legacy-data"))
WORK = os.path.join(W_DIR, 'league27')
LOC = 'fe/loc/NHL_ENG_US.db'
LOC_META = os.path.join(REPO, 'game', 'other', 'legacy', 'big', 'cacheboot', 'fe', 'loc', 'nhl_eng_us-meta.xml')
PRESETS = {
    # юниоры: OHL, QMJHL, WHL (лиги NHL 27 11–13 → Legacy 9–11), слоты 154–213; переехавшие франшизы — в прежние слоты
    'chl': {'leagues': {11: 9, 12: 10, 13: 11}, 'slots': range(154, 214), 'junior': True,
            'renamed': {'BRAN': 158,    # Hamilton Bulldogs → Brantford Bulldogs (2023)
                        'BRAM': 162,    # Mississauga Steelheads → Brampton Steelheads (2024)
                        'NFLD': 174,    # Acadie-Bathurst Titan → Newfoundland Regiment (2025)
                        'WEN': 198}},   # Kootenay Ice → Winnipeg Ice → Wenatchee Wild (2023)
    # Европа с составами 2015 года: SHL, DEL, Extraliga, NL (номера лиг у NHL 27 и Legacy совпадают); Liiga (3) собрал
    # конвейер с liiga.fi, Норвегии (7 у Legacy) в NHL 27 нет — не трогаются
    'europe': {'leagues': {2: 2, 4: 4, 5: 5, 6: 6}, 'slots': range(62, 131), 'junior': False, 'renamed': {}},
}
SYNTH = 97_000_000                                # nhl_id игроков NHL 27 в конвейере: SYNTH + game_id NHL 27
BIO_SKIP = {'game_id', 'jersey', 'artid', 'audioid', 'hasportrait', 'headid', 'skincolor', 'team', 'proteam', 'draftteam',
            'juniorteam', 'juniorleague', 'firstname', 'lastname', 'birthplace'}
ATTR_FIELDS = {fld(f) for f in SK + GK} | {'c_overall'}


def clamp(x, w):
    return max(0, min((1 << w) - 1, int(x)))


# --- 1. игроки -----------------------------------------------------------------------------------------------------
def club_slots(db_l, tm27, pr):
    """{номер команды NHL 27: слот Legacy}: явно (renamed), по аббревиатуре в своей лиге, по названию; оставшиеся слоты
    лиги — оставшимся клубам NHL 27 по порядку. Клубы NHL 27, кому слота не хватило, — нет в словаре."""
    out = {}
    for lg27, lg in pr['leagues'].items():
        free = [t for t in pr['slots'] if db_l.get(T, 'league', t) == lg]
        clubs = sorted(t for t, c in tm27.items() if c['league'] == lg27)
        key = lambda s: norm(s)
        for rule in ('renamed', 'abbr', 'name'):
            for t27 in clubs:
                if t27 in out:
                    continue
                c = tm27[t27]
                if rule == 'renamed':
                    slot = pr['renamed'].get(c['abbr'])
                elif rule == 'abbr':
                    slot = next((t for t in free if db_l.get_string(T, 'abbrname', t) == c['abbr']), None)
                else:
                    slot = next((t for t in free if key(db_l.get_string(T, 'fullname', t)) == key(c['name'])), None)
                if slot is not None and slot in free:
                    out[t27] = slot
                    free.remove(slot)
        for t27 in clubs:                                # выбывшие слоты — пришедшим клубам, по порядку
            if t27 not in out and free:
                out[t27] = free.pop(0)
    return out


def to_record(p27, slot):
    b, e = p27['bio'], p27['entry']
    pos = POS_NAME[b['position']]
    flags = sorted({nhl27.legacy_flag(f) for f, x in e.items() if x and nhl27.legacy_flag(f)})
    return {
        'nhl_id': SYNTH + p27['game_id'], 'team': p27['club']['abbr'], 'slot': slot,
        'first': b['firstname'], 'last': b['lastname'], 'pos': pos,
        'shoots': 'L' if b['handedness'] == 0 else 'R', 'num': e['jersey'],
        'birth': [b['year'] + 1900, b['month'] + 1, b['day'] + 1],
        'letter': {1: 'C', 2: 'A'}.get(e['captain']),
        'nhl_gp': {'career': b['nhlgamesplayedcareer'], 'debut': None, 'by_season': {}},
        'rating': {'source': 'nhl27', 'ovr': p27['ai'].get('c_overall'), 'attrs': {}},
        'ea': None, 'landing': True, 'omitted': False,
        '_n27': {'game_id': p27['game_id'], 'team27': p27['team'], 'club': p27['club'], 'bio': b,
                 'ai_table': p27['ai_table'], 'ai': p27['ai'], 'flags': flags,
                 'dressed': bool(flags)},
    }


def cmd_build(db_path, work, db27, pr, log):
    paths = Paths(None, work)
    db, _ = match_mod.load_db(paths, db_path)
    v = View(db)
    tm27 = nhl27.teams(db27, set(pr['leagues']))
    slots = club_slots(db, tm27, pr)
    own = set(slots.values())
    no_slot = sorted({c['abbr'] for t, c in tm27.items() if t not in slots})
    if len(set(slots.values())) != len(slots):
        raise SystemExit(f'два клуба NHL 27 на один слот: {slots}')
    idx = match_mod.index(v)
    recs, skipped, wins = [], [], []
    for p27 in nhl27.players(db27, set(pr['leagues'])):
        slot = slots.get(p27['team'])
        if slot is None:
            skipped.append(f"{p27['bio']['firstname']} {p27['bio']['lastname']} ({p27['club']['abbr']})")
            continue
        recs.append(to_record(p27, slot))
    found = {p['nhl_id']: match_mod.match_one(v, idx, p) for p in recs}
    by_row = defaultdict(list)
    for pid, (row, how) in found.items():
        if row is not None:
            by_row[row].append(pid)
    conflicts = []
    for row, pids in by_row.items():
        if len(pids) > 1:
            pids.sort(key=lambda pid: match_mod.HOW_RANK[found[pid][1]])
            for pid in pids[1:]:
                conflicts.append({'nhl_id': pid, 'row': row, 'kept': pids[0]})
                found[pid] = (None, 'conflict')
    keep = []
    for p in recs:
        row = found[p['nhl_id']][0]
        other = [v.team_name(t) for t in v.teams_of[row] if t not in own and t not in SPECIAL] if row is not None else []
        if row is not None and row in v.fa_rows:
            other.append('пул свободных агентов')
        if other:                                        # в базе — в клубе вне этих лиг или в пуле FA: остаётся там
            wins.append({'name': f"{p['first']} {p['last']}", 'nhl27': p['team'], 'ours': other})
            continue
        keep.append(p)
    fills = fill_rosters(keep, [to_record(p27, None) for p27 in nhl27.players(db27, set(pr['leagues']))
                                if p27['team'] not in slots], db, log)
    for p in keep:                                       # добор из клуба без слота — тоже через сопоставление
        if p['nhl_id'] not in found:
            found[p['nhl_id']] = match_mod.match_one(v, idx, p)
            row = found[p['nhl_id']][0]
            if row is not None and (row in v.fa_rows or any(t not in own and t not in SPECIAL for t in v.teams_of[row])):
                log(f"  {p['first']} {p['last']} (добор) в базе в другом клубе — строка не трогается, добавлен как новый")
                found[p['nhl_id']] = (None, 'none')
    dropped = fit_donors(keep, found, v, log)
    keep.sort(key=lambda p: (p['slot'], {'C': 0, 'L': 1, 'R': 2, 'D': 3, 'G': 4}[p['pos']], p['last'], p['first']))
    os.makedirs(work, exist_ok=True)
    write_json(paths.players, {'meta': {'source': f'NHL 27 nhl_game.db, лиги {sorted(pr["leagues"])}', 'db': db_path,
                                        'slots': {tm27[t]['abbr']: s for t, s in slots.items()}, 'no_slot': no_slot,
                                        'skipped': skipped, 'kept_elsewhere': wins, 'conflicts': conflicts,
                                        'fills': fills, 'dropped_no_row': dropped},
                               'players': keep})
    mt = {}
    for p in keep:
        row, how = found[p['nhl_id']]
        mt[str(p['nhl_id'])] = {'row': row, 'how': how, 'name': f"{p['first']} {p['last']}", 'team': p['team']}
        if row is not None:
            mt[str(p['nhl_id'])].update(db_name=v.name(row), db_teams=v.teams_of[row])
    write_json(paths.matched, {'db': db_path, 'counts': dict(Counter(r['how'] for r in mt.values())), 'players': mt})
    log(f"build: игроков NHL 27 {len(recs) + len(skipped)}, в слотах {len(keep)} ({len(slots)} клубов); "
        f"сопоставлено с базой {sum(1 for r in mt.values() if r['row'] is not None)}; остались в своих клубах вне лиг {len(wins)}; "
        f"без слота {no_slot} — {len(skipped)} игроков")
    return keep


def kind(pos):
    return 'G' if pos == 'G' else 'S'


def fill_rosters(keep, homeless, db, log):
    """Клубам, которым после «НХЛ/АХЛ побеждает» не хватает 2 вратарей или 18 полевых, — недостающих: незадействованные
    (не одетые, без звеньев) запасные того же амплуа из клуба той же лиги, где таких больше всего (у него остаётся
    не меньше 2 вратарей и 20 полевых), потом игроки клуба без слота (Penticton). → [перевод для отчёта]."""
    league = lambda slot: db.value(T, 'league', slot)
    by = defaultdict(list)
    for p in keep:
        by[p['slot']].append(p)
    count = lambda slot, k: sum(1 for x in by[slot] if kind(x['pos']) == k)
    need_of = lambda slot, k: max(0, (2 if k == 'G' else 18) - count(slot, k))
    keep_min = {'G': 2, 'S': 20}
    pool = sorted(homeless, key=lambda x: -(x['rating']['ovr'] or 0))
    moves = []
    for slot in sorted(by):
        for k in ('G', 'S'):
            for _ in range(need_of(slot, k)):
                donors = [d for d in by if d != slot and league(d) == league(slot) and count(d, k) > keep_min[k]]
                spares = lambda d: [x for x in by[d] if kind(x['pos']) == k and not x['_n27']['flags']]
                donors = [d for d in donors if spares(d)]
                if donors:
                    d = max(donors, key=lambda d: (len(spares(d)), count(d, k), -d))
                    x = max(spares(d), key=lambda x: (x['rating']['ovr'] or 0, -x['nhl_id']))
                    by[d].remove(x)
                    frm = x['team']
                elif any(kind(x['pos']) == k for x in pool):
                    x = next(x for x in pool if kind(x['pos']) == k)
                    pool.remove(x)
                    keep.append(x)
                    frm = x['team']
                else:
                    log(f'  {by[slot][0]["team"]}: не хватает {"вратаря" if k == "G" else "полевого"} — добрать некем')
                    break
                x['_n27']['flags'], x['_n27']['dressed'] = [], False
                x['slot'], x['team'] = slot, by[slot][0]['team']
                by[slot].append(x)
                moves.append({'name': f"{x['first']} {x['last']}", 'pos': x['pos'], 'from': frm, 'to': x['team']})
    if moves:
        log(f'  добор составов: {len(moves)} — ' + ', '.join(f"{m['name']} {m['from']}→{m['to']}" for m in moves))
    return moves


def fit_donors(keep, found, v, log):
    """Строк-доноров (прежние юниоры CHL и игроки без клуба, не в пуле свободных агентов) у вратарей может не хватить:
    вратаря пишут только в строку вратаря (свои таблицы атрибутов и экипировки). Тогда без строки остаются самые
    слабые третьи вратари (не одетые, без звеньев) клубов, где их больше двух. → [кто остался без строки]."""
    own = {p['slot'] for p in keep}
    have = Counter()
    for r in range(v.nbio):
        if v.created_slot(r) or not v.ai(r) or r in v.fa_rows:
            continue
        t = v.teams_of[r]
        if not t or all(x in own for x in t):
            have[v.is_goalie(r)] += 1
    matched = {found[p['nhl_id']][0] for p in keep if found.get(p['nhl_id'], (None,))[0] is not None}
    dropped = []
    for goalie in (True, False):
        need = sum(1 for p in keep if (p['pos'] == 'G') == goalie and found.get(p['nhl_id'], (None,))[0] is None)
        free = have[goalie] - sum(1 for r in matched if v.is_goalie(r) == goalie)
        while need > free:
            by = Counter(p['slot'] for p in keep if (p['pos'] == 'G') == goalie)
            cand = [p for p in keep if (p['pos'] == 'G') == goalie and not p['_n27']['flags'] and
                    by[p['slot']] > (2 if goalie else 20) and found.get(p['nhl_id'], (None,))[0] is None]
            if not cand:
                log(f"  строк-доноров не хватает: {'вратарей' if goalie else 'полевых'} {need} при {free}")
                break
            x = min(cand, key=lambda p: (p['rating']['ovr'] or 0, p['nhl_id']))
            keep.remove(x)
            dropped.append(f"{x['first']} {x['last']} ({x['team']}, {x['pos']}, OVR {x['rating']['ovr']})")
            need -= 1
    if dropped:
        log(f'  без строки (доноров не хватило): {dropped}')
    return dropped


# --- 2. запись -----------------------------------------------------------------------------------------------------
class League27Writer(AhlWriter):
    ROSTER_MIN, ROSTER_MAX = 20, 36                  # в NHL 27 у клубов CHL 20–30 игроков, у Европы до 32 (одеты 20)
    junior = True                                    # юниоры CHL: juniorteam/juniorleague — свой клуб

    def donor_candidates(self, taken):
        """Строки прежних игроков клубов пресета (старшие первыми), потом игроков без клуба; пул свободных агентов, НХЛ,
        АХЛ, Европа и особые команды — никогда."""
        v = self.v
        out = {'G': [], 'S': []}
        for r in range(v.nbio):
            if r in taken or v.created_slot(r) or not v.ai(r) or r in v.fa_rows:
                continue
            teams = v.teams_of[r]
            if teams and all(t in self.own_clubs for t in teams):
                tier = 4                                 # W.TIER: клуб, пересобранный конвейером
            elif not teams:
                tier = 2                                 # без команды
            else:
                continue
            out['G' if v.is_goalie(r) else 'S'].append((tier != 4, v.birth(r)[0], r, tier))
        for k in out:                                    # Writer.plan берёт по порядку: (_, год, tier, строка)
            out[k] = [(False, y, tier, r) for _, y, r, tier in sorted(out[k])]
        return out

    def write_ratings(self, p, r, new):
        """Атрибуты, стиль, тенденции, черты и рост — из NHL 27 (атрибуты − 36; потенциал — nhl27.POTENTIAL)."""
        db, v = self.db, self.v
        t, row = v.ai(r)
        src = p['_n27']['ai']
        fields = db.by_name[t]['fields']
        lows = db.by_name[t]['lows']
        for f, (_, w) in fields.items():
            if f == 'game_id':
                continue
            if f not in src:
                if new:
                    db.set(t, f, row, 0)
                continue
            x = src[f]
            if f == 'c_potential':
                raw = nhl27.POTENTIAL.get(x, 30 if x >= 54 else 5)
            elif f in ATTR_FIELDS:
                raw = x - BASE
            else:
                raw = x - lows.get(f, 0)
            db.set(t, f, row, clamp(raw, w))
        attrs = {f: db.get(t, fld(f), row) + BASE for f in (GK if t == G else SK)}
        ovr = ovrformula.game_ovr(cls(p['pos']), attrs)
        style = db.get(t, fld('p_style' if t == S else 'g_style'), row)
        return attrs, ovr, style

    def write_bio(self, p, r, new, ovr):
        """Биография из NHL 27 (все общие поля, кроме арта и головы); клубы — в нумерации Legacy."""
        db = self.db
        b = p['_n27']['bio']
        fields, lows = db.by_name[B]['fields'], db.by_name[B]['lows']
        self.set_name(r, p, True)
        db.set_string(B, 'birthplace', r, fit_utf8(self.clean(b.get('birthplace') or ''), fields['birthplace'][1] // 8 - 1))
        for f, (_, w) in fields.items():
            if f in BIO_SKIP or f not in b:
                continue
            db.set(B, f, r, clamp(b[f] - lows.get(f, 0), w))
        put = lambda f, val: db.set(B, f, r, clamp(val - lows.get(f, 0), fields[f][1]))
        put('team', p['slot'])
        nhl = lambda x: nhl27.NHL_SLOT.get(x, -1) if 0 <= x <= 31 else -1
        put('proteam', nhl(b['proteam']))
        put('draftteam', nhl(b['draftteam']))
        # юниорский клуб — свой слот и его лига (так у юниоров CHL базы EA 2015 года; в NHL 27 у них пусто)
        put('juniorteam', p['slot'] if self.junior else -1)
        put('juniorleague', db.value(T, 'league', p['slot']) if self.junior else 0)
        if new:
            db.set(B, 'artid', r, self.artid[p['nhl_id']])
            db.set(B, 'audioid', r, 0)
            db.set(B, 'hasportrait', r, 0)
            skin = b.get('skincolor')
            pool = [h for h in self.heads_all if self.head_skin[h] == skin] or [h for h, _ in self.heads]
            head = pool[zlib.crc32(f"{p['first']} {p['last']}".encode()) % len(pool)]
            db.set(B, 'headid', r, head)
            db.set(B, 'skincolor', r, self.head_skin[head])

    def repair_lines(self, tp, keys):
        """Звенья NHL 27, у которых ушли игроки (в НХЛ/АХЛ базы): места в тройках, парах и воротах — лучшим по OVR
        неодетым того же амплуа (нет — полевому другого амплуа), остальные места (большинство, меньшинство, овертайм,
        буллиты, лишние) — лучшим одетым подходящего амплуа, не повторяясь в группе. → (места, одетые, [заполнено])
        или None — не вышло."""
        by = {p['nhl_id']: p for p in tp}
        slots = {f: ks[0] for f, ks in keys.items() if len(ks) == 1}
        core = [f for f in FLAGS if f[0] == 'l' or f in ('g1', 'g2')]
        dressed = {slots[f] for f in core if f in slots}
        kind_of = lambda p: 'G' if p['pos'] == 'G' else 'D' if p['pos'] == 'D' else 'F'
        group_of = {f: g for g in W.lines_mod.GROUPS for f in g}
        filled = []
        for f in core:
            if f in slots:
                continue
            need = W.lines_mod.slot_kind(f)
            free = [p for p in tp if p['nhl_id'] not in dressed and (kind_of(p) == need or
                                                                      (need != 'G' and kind_of(p) != 'G'))]
            if not free:
                return None
            x = max(free, key=lambda p: (kind_of(p) == need, p['_ovr'], -p['nhl_id']))
            slots[f] = x['nhl_id']
            dressed.add(x['nhl_id'])
            filled.append({'slot': f, 'name': f"{x['first']} {x['last']}"})
        if len(dressed) != 20:
            return None
        for f in FLAGS:
            if f in slots:
                continue
            need = W.lines_mod.slot_kind(f)
            taken = {slots.get(g) for g in group_of.get(f, [f])}
            cand = [by[k] for k in dressed if k not in taken and
                    ((need is None and kind_of(by[k]) != 'G') or kind_of(by[k]) == need or
                     (need in ('F', 'D') and kind_of(by[k]) not in ('G', need)))]
            if not cand:
                return None
            x = max(cand, key=lambda p: (kind_of(p) == need, p['_ovr'], -p['nhl_id']))
            slots[f] = x['nhl_id']
            filled.append({'slot': f, 'name': f"{x['first']} {x['last']}"})
        return slots, dressed, filled

    def generic_heads(self):
        super().generic_heads()
        self.heads_all = sorted(self.head_skin)

    def team_lines(self, team, tp):
        """Звенья и одетые — из NHL 27 (каждое место Legacy у одного игрока; проверено на всех 61 клубе CHL);
        если в данных дыра — по рейтингу, как у конвейера."""
        keys, dressed = {}, set()
        for p in tp:
            for f in p['_n27']['flags']:
                keys.setdefault(f, []).append(p['nhl_id'])
            if p['_n27']['flags']:
                dressed.add(p['nhl_id'])
        if all(len(keys.get(f, [])) == 1 for f in FLAGS) and len(dressed) == 20:
            self.lines_info[tp[0]['slot']] = {'source': 'nhl27'}
            return {f: keys[f][0] for f in FLAGS}, dressed
        fixed = self.repair_lines(tp, keys)
        if fixed:
            self.lines_info[tp[0]['slot']] = {'source': 'nhl27+', 'filled': fixed[2]}
            return fixed[0], fixed[1]
        lp = [{'key': p['nhl_id'], 'pos': p['pos'], 'ovr': p['_ovr'], 'shoots': p.get('shoots'), 'attrs': p['_attrs'],
               'out': False} for p in tp]
        self.lines_info[tp[0]['slot']] = {'source': 'rating', 'why': 'в NHL 27 не все места звеньев'}
        return W.lines_mod.build(lp)


def cmd_write(db_path, work, out, pr, log):
    paths = Paths(None, work)
    paths.db_in = os.path.abspath(db_path)
    paths.db_out = os.path.abspath(out)
    paths.registry = os.path.join(WORK, 'artid-registry.json')       # общая у пресетов, out и out-ahl32
    paths.retire_veterans = 2010                    # free_vacancy: моложе 2010 г. р. ушедших из НХЛ нет — без них
    w = League27Writer(paths, log, real_lines=False)
    w.junior = pr['junior']
    bad, crc, removed = w.run()
    if crc:
        raise SystemExit(f'CRC не сходятся: {crc[:3]}')
    if bad:
        for x in bad[:20]:
            log('  ПРОВЕРКА: ' + x)
        raise SystemExit(f'{len(bad)} проблем — база не записана')
    tmp = paths.db_out + '.part'
    with open(tmp, 'wb') as f:
        f.write(w.db.d)
    os.replace(tmp, paths.db_out)
    write_json(paths.registry, dict(sorted(w.registry.items(), key=lambda kv: int(kv[0]))))
    sizes = Counter(e['team'] for e in w.entries if e['team'] in w.own_clubs)
    lines = Counter(i['source'] for i in w.lines_info.values())
    write_json(paths.written, {'db_in': paths.db_in, 'db_out': paths.db_out, 'players': list(w.out.values()),
                               'teamless': [{'row': r, 'name': w.v.name(r), 'birth': list(w.v.birth(r))} for r in w.teamless],
                               'new_links': w.new_links, 'stats_removed': removed, 'lines': dict(lines),
                               'sizes': {str(t): n for t, n in sorted(sizes.items())}})
    log(f'write: игроков {len(w.out)} (сопоставлено {len(w.out) - len(w.new)}, в строках доноров {len(w.new)}); '
        f'клубов {len(sizes)} ({min(sizes.values())}–{max(sizes.values())} игроков); звенья {dict(lines)}; '
        f'без клуба (прежние игроки) {len(w.teamless)}; новых связей {len(w.new_links)} → {paths.db_out}')


# --- 3. клубы ------------------------------------------------------------------------------------------------------
LOC_KEYS = {'NHLTeamName': 'name', 'NHLTEAMNAME': 'name', 'NHLCityName': 'city', 'NHLCITYNAME': 'city',
            'Teamline1': 'city', 'TEAMLINE1': 'city', 'Teamline2': 'nick', 'TEAMLINE2': 'nick', 'NICKLINE2': 'nick',
            'TXT_NICKNAME': 'nick', 'TXT_NICKNAME_ALT': 'nick', 'NHLTeamName_ABBR3': 'abbr', 'X_XLA_TEAM': 'abbr'}


def cmd_clubs(db_path, db27, pr, loc_path, log):
    """Названия слотов с другим клубом или названием (база и локализация), арены клубов из NHL 27.
    → (байты базы, байты локализации)."""
    db = Tdb(open(db_path, 'rb').read(), load_meta(os.path.join(os.path.dirname(db_path), 'nhlng-meta.xml')))
    tm27 = nhl27.teams(db27, set(pr['leagues']))
    slots = club_slots(db, tm27, pr)
    width = lambda t, f: db.by_name[t]['fields'][f][1] // 8 - 1
    n = 0
    # буквы, которые уже есть в названиях команд и арен базы (значит, есть в шрифте игры)
    seen = {ch for t in (T, 'exhibitionarena') for r in range(db.by_name[t]['rows'])
            for f in (('fullname', 'shortname', 'abbrname') if t == T else ('arenaname', 'cityname'))
            for ch in db.get_string(t, f, r)}
    in_font = lambda ch: ord(ch) < 128 or ch in seen

    def put(table, field, row, text):
        nonlocal n
        text = fit_utf8(safe_text((text or '').replace('’', "'").strip(), in_font), width(table, field))
        if db.get_string(table, field, row) != text:
            db.set_string(table, field, row, text)
            n += 1
    users = defaultdict(list)
    for t in range(db.by_name[T]['rows']):
        users[db.get(T, 'arenaid', t)].append(t)
    renamed = []
    for t27, slot in sorted(slots.items(), key=lambda x: x[1]):
        c = tm27[t27]
        if c['abbr'] in pr['renamed'] or db.get_string(T, 'fullname', slot) != fit_utf8(c['name'], width(T, 'fullname')):
            renamed.append((slot, c))
            put(T, 'fullname', slot, c['name'])
            put(T, 'shortname', slot, c['city'])
            put(T, 'abbrname', slot, c['abbr'])
        a27 = db27.get(nhl27.T, 'arenaid', c['row'])
        a = db.get(T, 'arenaid', slot)
        if users[a] == [slot] and a27 in db27.live_rows('exhibitionarena'):
            put('exhibitionarena', 'arenaname', a, db27.get_string('exhibitionarena', 'arenaname', a27))
            put('exhibitionarena', 'cityname', a, db27.get_string('exhibitionarena', 'cityname', a27))
    db.fix()
    if db.verify():
        raise SystemExit(f'{db_path}: CRC не сошлись')
    import locdb
    loc = locdb.LocDb(open(loc_path, 'rb').read(), load_meta(LOC_META))
    m = 0
    for slot, c in renamed:
        art = db.get_string(T, 'artabbr', slot)
        nick = c['name'][len(c['city']):].strip() if c['name'].startswith(c['city']) else c['name']
        val = {'name': c['name'], 'city': c['city'], 'nick': nick, 'abbr': c['abbr']}
        done = set()
        for k, what in LOC_KEYS.items():
            key = f'{k}_{art}'
            if key.lower() in done or not loc.find_all(key):
                continue
            done.add(key.lower())
            text = safe_text(val[what], lambda ch: all(b in loc.codes for b in ch.encode('utf-8')))
            if loc.text(loc.text_off_at(loc.find_all(key)[0])) != text:
                loc.put(key, text)
                m += 1
    bad = loc.check()
    if bad:
        raise SystemExit(f'{loc_path}: ' + '; '.join(bad[:3]))
    loc.db.fix()
    log(f"clubs: переименовано {len(renamed)} ({', '.join(c['name'] for _, c in renamed)}); значений в базе {n}, "
        f'строк локализации {m}')
    return bytes(db.d), bytes(loc.db.d)


def ascii_of(ch):
    import unicodedata
    return unicodedata.normalize('NFKD', ch).encode('ascii', 'ignore').decode()


def safe_text(text, ok):
    """Буквы, которых нет в ok (функция «символ можно»), — без диакритики (Ó → O; у EA бывает и кириллица: Malmӧ)."""
    return ''.join(ch if ok(ch) else ascii_of(ch) for ch in text)


def write_if_changed(path, data):
    if os.path.exists(path) and open(path, 'rb').read() == data:
        return False
    with open(path + '.part', 'wb') as f:
        f.write(data)
    os.replace(path + '.part', path)
    return True


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    args = sys.argv[1:]
    if not args or args[0] not in PRESETS:
        sys.exit(__doc__)
    name_pr, pr = args[0], PRESETS[args[0]]
    only = args[args.index('--only') + 1] if '--only' in args else None
    db27 = nhl27.open_db(args[args.index('--db27') + 1] if '--db27' in args else None)
    for name in ('out-ahl32', 'out'):
        d = os.path.join(W_DIR, name)
        final = os.path.join(d, 'db', 'nhlng.db')
        if not os.path.isfile(final):
            continue
        work = os.path.join(WORK, name_pr, name)
        print(f'== {name}')
        # на копии базы в рабочей папке: в out база и локализация попадают только в конце, целиком
        stage = os.path.join(work, 'db')
        os.makedirs(stage, exist_ok=True)
        for f in ('nhlng.db', 'nhlng-meta.xml'):
            shutil.copyfile(os.path.join(d, 'db', f), os.path.join(stage, f))
        dbp = os.path.join(stage, 'nhlng.db')
        log = print
        if only in (None, 'build'):
            cmd_build(dbp, work, db27, pr, log)
        if only in (None, 'write'):
            cmd_write(dbp, work, dbp, pr, log)
        lp = os.path.join(d, *LOC.split('/'))
        loc_data = None
        if only in (None, 'clubs'):
            data, loc_data = cmd_clubs(dbp, db27, pr, lp, log)
            write_if_changed(dbp, data)
        if only is None or only in ('write', 'clubs'):
            changed = write_if_changed(final, open(dbp, 'rb').read())
            if loc_data is not None:
                changed |= write_if_changed(lp, loc_data)
            print(f"   → {final}{'' if changed else ' (без изменений)'}")
        if only in (None, 'draft', 'write', 'clubs'):
            import subprocess
            subprocess.run([sys.executable, os.path.join(HERE, 'draft_roster.py'), final,
                            os.path.join(d, 'db', 'draft_roster.db')], check=True)


if __name__ == '__main__':
    main()
