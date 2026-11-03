"""Составы особых команд NHL Legacy: сборные стран и Матч звёзд → база и сейв ROSTER с датой в имени.

    python tools/legacy_data/special_rosters.py run [--dry-run]              # сборные NHL 27, свои сборные, Матч звёзд
    python tools/legacy_data/special_rosters.py run --only nations           # только сборные (allstar — только Матч звёзд)
    python tools/legacy_data/special_rosters.py run --nhl27 CAN,USA --own RUS  # какие сборные откуда
    python tools/legacy_data/special_rosters.py show [--db БАЗА] RUS EAS WES  # состав и звенья команд базы или сейва

Что делает (подробно — docs/special-rosters.md):
- **Сборные из NHL 27** (по умолчанию 19 стран: все, что есть у Legacy, кроме RUS и BEL). Состав, номера, буквы и звенья —
  из сборной базы NHL 27 (лига 10, best-on-best). Игрок, который есть в нашей базе (имя и дата рождения), идёт в сборную
  как есть: клуб, атрибуты и голова — наши. Кого в базе нет, занимает строку игрока, который был только в сборной и
  выбыл (сначала своей страны, потом другой), потом строку игрока без клуба: биография и атрибуты — из NHL 27, без
  прав и контракта НХЛ, голова типовая, портрета нет.
- **Свои сборные** — по спеке tools/legacy_data/special_rosters_nations.txt (сейчас Россия): игроки нашей базы по
  именам, звенья по рейтингу. Кого в базе нет, тот в отчёте и пропускается.
- **Матч звёзд** (Play Now, команды 222 «Green / Red» = Восток и 223 «Black / Blue» = Запад): по 24 игрока (3 G, 8 D,
  13 F, из них не меньше 4 центров) своей конференции; от каждого клуба минимум один (лучший по OVR из тех, кто проходит
  по амплуа), остальные места — лучшим по OVR, равный OVR решают очки (у вратарей — победы) прошлого сезона. Звенья по
  позициям (pos_lines: в центре — центры, крайние по своей стороне, пары лево/право, одноклубники вместе), C и A — у
  трёх лучших полевых.
- Сборные и звёзды, которые не пересобираются (Беларусь и др.), не трогаются. Выбывший из сборной игрок без клуба
  становится игроком без клуба, как ветераны. Игроков, которых игра ищет в коде по имени (вратарь и полевые тренировки по
  умолчанию — NAME_LOOKUP), инструмент строками-донорами не берёт.

Выход — --out (по умолчанию game/work/special-rosters/out): db/nhlng.db, nhlng-meta.xml, draft_roster.db, `ROSTER
ДД.ММ.ГГГГ` — копия новейшего ROSTER пользователя после трёхстороннего слияния (roster_merge.py: правки пользователя
целы), report.md с командами установки. База и сейвы пользователя только читаются. Повторный запуск на готовой базе
ничего не меняет.
"""
import argparse
import datetime
import json
import os
import re
import shutil
import sys
import zlib
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
ROOT = os.path.dirname(TOOLS)
sys.path.insert(0, TOOLS)
sys.path.insert(0, HERE)
import roster_update as RU  # noqa: E402  (ставит профиль legacy до импорта модулей конвейера)
import draft_roster  # noqa: E402
import roster_merge  # noqa: E402
from add_players import NAME_LOOKUP  # noqa: E402
from league27 import ATTR_FIELDS, BIO_SKIP, clamp  # noqa: E402
from roster import lines as LN  # noqa: E402
from roster import match as MM  # noqa: E402
from roster import nhl27, ovrformula  # noqa: E402
from roster.common import SEASON_YEAR, SLOT_TEAM, fit_utf8, norm  # noqa: E402
from roster.dbview import (ALLSTAR, B, F, FLAGS, G, GENERIC_HEAD, NATIONAL, NHL, P, POS_NAME, R, S, SPECIAL, T,  # noqa: E402
                           View, fld)
from roster.ratings import BASE, GK, SK, cls  # noqa: E402
from roster.write import STATS  # noqa: E402
from tdb import SaveFile, Tdb, load_meta  # noqa: E402

WORK = os.path.join(ROOT, 'game', 'work', 'special-rosters')
NATIONS_SPEC = os.path.join(HERE, 'special_rosters_nations.txt')
LEAGUE27_NATIONAL = 10                 # лига NHL 27 со сборными best-on-best (25 — чемпионат мира, 24 — юниоры)
KEEP_DEFAULT = ('BEL',)                # Беларусь не пересобираем: не просили (03.11.2026), в NHL 27 состав 2022 года
OWN_DEFAULT = ('RUS',)                 # Россия — своя спека: у NHL 27 состав не обновлялся с 2022 года
ALLSTAR_SIZE = {'G': 3, 'D': 8, 'F': 13}   # 24 игрока, как у команд Матча звёзд базы (24–25); одеты 20
MIN_CENTRES = 4
INTL_STATS = ('stockintltourneyplayerstats', 'stockintltourneygoaliestats')
CONTRACT = ('proteam', 'contractlength', 'contractdollars', 'contractstatus', 'contractis2way', 'contractismultiyear',
            'contractneedsentrylevel', 'extensionlength', 'extensiondollars', 'extensionis2way', 'yearufa')
LINK_LIMIT = 16000
TAG = re.compile(r'\[([CA])\]')
CLUB = re.compile(r'\(([A-Z]{2,3})\)')


class SpecError(ValueError):
    pass


def group(pos):
    return 'G' if pos == 'G' else 'D' if pos == 'D' else 'F'


# --- спека своих сборных --------------------------------------------------------------------------------------------
LINE_COLS = {'L1': 3, 'L2': 3, 'L3': 3, 'L4': 3, 'D1': 2, 'D2': 2, 'D3': 2}


def parse_nations(path):
    """{сборная: [{'name', 'group', 'letter', 'club'}]} из строк «RUS | G: … | D: … | F: … [| L1: … | D1: …]»;
    звенья (если есть) — в parse_nations.lines[сборная] = {'L1': [имена LW, C, RW], 'D1': [LD, RD], …}."""
    out = {}
    parse_nations.lines = {}
    for no, raw in enumerate(open(path, encoding='utf-8-sig'), 1):
        line = raw.strip()
        if not line or line.startswith('#'):
            continue
        cols = [c.strip() for c in line.split('|')]
        where = f'{os.path.basename(path)}, строка {no}'
        abbr, players = cols[0], []
        for col in cols[1:]:
            if ':' not in col:
                raise SpecError(f'{where}: «{col}» — нужно «G: игроки», «D: …» или «F: …»')
            grp, names = col.split(':', 1)
            grp = grp.strip().upper()
            if grp in LINE_COLS:
                who = [CLUB.sub('', TAG.sub('', x)).strip() for x in names.split(' - ')]
                if len(who) != LINE_COLS[grp] or not all(who):
                    raise SpecError(f'{where}: {grp} — {LINE_COLS[grp]} игрока через « - » (левый - центр - правый)')
                parse_nations.lines.setdefault(abbr, {})[grp] = who
                continue
            if grp not in ('G', 'D', 'F'):
                raise SpecError(f'{where}: группа {grp} — только G, D, F, L1–L4, D1–D3')
            for it in names.split(','):
                it = it.strip()
                if not it:
                    continue
                tag = TAG.search(it)
                club = CLUB.search(it)
                name = CLUB.sub('', TAG.sub('', it)).strip()
                if len(name.split()) < 2:
                    raise SpecError(f'{where}: «{it}» — нужно имя и фамилия')
                players.append({'name': name, 'group': grp, 'letter': {'C': 1, 'A': 2}.get(tag.group(1)) if tag else 0,
                                'club': club.group(1) if club else None})
        out[abbr] = players
        got = parse_nations.lines.get(abbr)
        if got and set(got) != set(LINE_COLS):
            raise SpecError(f'{where}: звенья — все семь: L1–L4 и D1–D3, нет {sorted(set(LINE_COLS) - set(got))}')
    return out


# --- звенья по позициям ---------------------------------------------------------------------------------------------
def side_of(p):
    """Сторона крайнего: своя позиция (L/R), у центра на краю — по хвату."""
    return 'lw' if p['pos'] == 'L' or (p['pos'] == 'C' and p['shoots'] == 'L') else 'rw'


def pos_lines(lp, centre_ok, club):
    """Тройки, пары и вратари по позициям (решение пользователя 03.11.2026: «в центре — центры, крайние по своей
    стороне, пары лево/право, по возможности одноклубники вместе»):
    - центры — четыре сильнейших по OVR из тех, кто может играть в центре (centre_ok: своя позиция C или центр
      звена клуба на странице DailyFaceoff); нет четырёх — лучший из прочих;
    - крайние — восемь сильнейших из остальных; сначала одноклубники центров — к своему центру на свою сторону, потом
      остальные от сильнейшего — в самое верхнее звено со свободной своей стороной, иначе на другую сторону;
    - защитники — шесть сильнейших: леворукие слева, праворукие справа (не хватает — лишние другой руки на чужую
      сторону, слабейшие), пары — сначала одноклубники, потом k-й левый с k-м правым, пары по силе;
    - вратари — двое сильнейших.
    → ({место: key} только для l1…l4 и g1/g2, 20 одетых key)."""
    rank = lambda p: (-p['ovr'], p['key'])
    fw = sorted((p for p in lp if p['pos'] in ('C', 'L', 'R')), key=rank)
    dd = sorted((p for p in lp if p['pos'] == 'D'), key=rank)
    gg = sorted((p for p in lp if p['pos'] == 'G'), key=rank)
    if len(gg) < 2 or len(fw) + len(dd) < 18:
        raise LN.NotEnoughPlayers(f'{len(gg)} вратарей, {len(dd)} защитников, {len(fw)} нападающих')
    while len(dd) < 6:
        dd.append(fw.pop())
    while len(fw) < 12:
        fw.append(dd.pop())
    centres = [p for p in fw if p['key'] in centre_ok][:4]
    centres += [p for p in fw if p not in centres][:4 - len(centres)]
    centres.sort(key=rank)
    wings = [p for p in fw if p not in centres][:8]
    slots = {f'l{k + 1}c': c['key'] for k, c in enumerate(centres)}
    has_mate = lambda w: any(club(c['key']) and club(c['key']) == club(w['key']) for c in centres)
    for w in sorted(wings, key=lambda w: (not has_mate(w), rank(w))):    # сначала одноклубники центров
        s = side_of(w)
        o = 'rw' if s == 'lw' else 'lw'
        mates = [k for k, c in enumerate(centres) if club(c['key']) and club(c['key']) == club(w['key'])]
        order = [(k, s) for k in mates] + [(k, s) for k in range(4)] + [(k, o) for k in range(4)]
        k, side = next((k, x) for k, x in order if f'l{k + 1}{x}' not in slots)
        slots[f'l{k + 1}{side}'] = w['key']
    d6 = dd[:6]
    left = [p for p in d6 if p['shoots'] == 'L']
    right = [p for p in d6 if p['shoots'] != 'L']
    while len(left) > 3:
        right.append(left.pop())
    while len(right) > 3:
        left.append(right.pop())
    pairs = []
    for ld in list(left):
        rd = next((r for r in right if club(r['key']) and club(r['key']) == club(ld['key'])), None)
        if rd:
            pairs.append((ld, rd))
            left.remove(ld)
            right.remove(rd)
    pairs += list(zip(sorted(left, key=rank), sorted(right, key=rank)))
    pairs.sort(key=lambda pr: -(pr[0]['ovr'] + pr[1]['ovr']))
    for k, (ld, rd) in enumerate(pairs):
        slots[f'l{k + 1}ld'], slots[f'l{k + 1}rd'] = ld['key'], rd['key']
    slots['g1'], slots['g2'] = gg[0]['key'], gg[1]['key']
    dressed = set(slots.values())
    assert len(dressed) == 20, slots
    return slots, dressed


# --- сбор составов ----------------------------------------------------------------------------------------------------
class Special:
    def __init__(self, db, log=print):
        self.db, self.log = db, log
        self.u = RU.Update(db, log)
        self.v = self.u.v
        self.plans = {}                      # команда → [{'row', 'name', 'pos', 'jersey', 'letter', 'flags', 'p27', 'src'}]
        self.missing = defaultdict(list)     # команда → [кого нет в базе / нет строки]
        self.rules = {}                      # команда → как собрана
        self.new = []                        # новые игроки (строки доноров)
        self.slot_of = {db.get_string(T, 'abbrname', t): t for t in sorted(set(NATIONAL) | set(ALLSTAR))}
        self.spec_lines = {}                 # команда → {место: строка} из спеки (звенья вручную)
        self.centre_ok = self.centres()

    def centres(self):
        """game_id тех, кто может играть в центре: своя позиция C или центр звена своего клуба на странице DailyFaceoff
        (кэш roster_update.py, game/work/roster-cache/dailyfaceoff): там видно, кто сейчас играет в центре."""
        v, u = self.v, self.u
        out = {v.gid[r] for r in range(v.nbio) if not v.created_slot(r) and v.ai(r) and v.g('position', r) == 0}
        try:
            src = RU.sources.dfo_lines(RU.CACHE)
        except Exception as e:                               # кэша нет — только своя позиция
            self.log(f'страниц DailyFaceoff нет ({e}): центры — только по позиции в базе')
            return out
        for abbr, page in src.items():
            for name, grp in page.get('groups', {}).items():
                if not (name.startswith('f') and isinstance(grp, list)):
                    continue
                for p in grp:
                    if isinstance(p, dict) and p.get('slot') == 'c' and p.get('name'):
                        for r in u.find(p['name'], goalie=False):
                            if u.abbr(u.club_of(r)) == abbr:
                                out.add(v.gid[r])
        return out

    def club_key(self, gid):
        r = self.v.row_of_gid[gid]
        cl = [t for t in self.v.teams_of[r] if t not in SPECIAL]
        return cl[0] if cl else None

    def abbr(self, t):
        return self.db.get_string(T, 'abbrname', t)

    def club(self, r):
        cl = [t for t in self.v.teams_of[r] if t not in SPECIAL]
        return self.u.abbr(cl[0]) if cl else ('FA' if r in self.v.fa_rows else '—')

    def protected(self, r):
        return (self.v.s('firstname', r), self.v.s('lastname', r)) in NAME_LOOKUP

    # сборные NHL 27 ------------------------------------------------------------------------------------------------
    def plan_nhl27(self, db27, abbrs):
        tm = nhl27.teams(db27, {LEAGUE27_NATIONAL})
        want = {i: self.slot_of[c['abbr']] for i, c in tm.items() if c['abbr'] in abbrs and c['abbr'] in self.slot_of}
        lost = sorted(set(abbrs) - {self.abbr(s) for s in want.values()})
        if lost:
            raise SpecError(f'в NHL 27 (лига {LEAGUE27_NATIONAL}) нет сборных {lost}')
        v = self.v
        idx = MM.index(v)
        # тот же человек в прежнем составе сборной, но с другой датой рождения (у EA в сборных бывает): по полному имени
        old = defaultdict(list)
        for r in range(v.nbio):
            for t in set(v.teams_of[r]) & set(want.values()):
                old[(t, norm(v.name(r)), v.is_goalie(r))].append(r)
        for p in nhl27.players(db27, {LEAGUE27_NATIONAL}):
            slot = want.get(p['team'])
            if slot is None:
                continue
            b, e = p['bio'], p['entry']
            pos = POS_NAME[b['position']]
            rec = {'first': b['firstname'], 'last': b['lastname'], 'pos': pos,
                   'birth': (b['year'] + 1900, b['month'] + 1, b['day'] + 1)}
            row, how = MM.match_one(v, idx, rec)
            if row is None:
                same = old.get((slot, norm(f"{rec['first']} {rec['last']}"), pos == 'G'), [])
                if len(same) == 1:
                    row, how = same[0], 'name-in-team'
            plan = self.plans.setdefault(slot, [])
            if row is not None and any(x['row'] == row for x in plan):
                row = None
            flags = sorted({nhl27.legacy_flag(f) for f, x in e.items() if x and nhl27.legacy_flag(f)})
            plan.append({'row': row, 'how': how, 'name': f"{rec['first']} {rec['last']}", 'pos': pos,
                         'jersey': e['jersey'], 'letter': e['captain'] if e['captain'] in (1, 2) else 0,
                         'flags': flags, 'p27': p, 'src': 'nhl27'})
        for slot in set(want.values()):
            self.rules[slot] = f'NHL 27, сборная {self.abbr(slot)} (лига {LEAGUE27_NATIONAL})'

    # свои сборные --------------------------------------------------------------------------------------------------
    def find(self, name, goalie, club):
        rows = [r for r in self.u.find(name, goalie=goalie) if self.v.ai(r)]
        if club:
            rows = [r for r in rows if self.club(r) == club]
        rank = lambda r: (not any(t in NHL for t in self.v.teams_of[r]),
                          not any(t not in SPECIAL for t in self.v.teams_of[r]) and r not in self.v.fa_rows, r)
        return sorted(rows, key=rank)

    def plan_spec(self, spec, abbrs):
        for abbr in abbrs:
            if abbr not in spec:
                raise SpecError(f'{abbr}: нет строки в спеке {NATIONS_SPEC}')
            if abbr not in self.slot_of:
                raise SpecError(f'{abbr}: такой сборной в базе нет ({sorted(self.slot_of)})')
            slot = self.slot_of[abbr]
            plan = self.plans.setdefault(slot, [])
            for it in spec[abbr]:
                rows = [r for r in self.find(it['name'], it['group'] == 'G', it['club'])
                        if (it['group'] == 'G') == self.v.is_goalie(r)]
                if not rows:
                    self.missing[slot].append(f"{it['name']} ({it['group']}): нет в базе")
                    continue
                r = rows[0]
                if any(x['row'] == r for x in plan):
                    raise SpecError(f"{abbr}: {it['name']} дважды")
                pos = POS_NAME[self.v.g('position', r)]
                plan.append({'row': r, 'how': 'spec', 'name': self.v.name(r), 'pos': pos, 'jersey': None,
                             'letter': it['letter'], 'flags': None, 'p27': None, 'src': 'spec'})
            lines = getattr(parse_nations, 'lines', {}).get(abbr)
            if lines:
                rows = {norm(x['name']): x['row'] for x in plan}
                fixed = {}
                for grp, who in lines.items():
                    places = ('lw', 'c', 'rw') if grp[0] == 'L' else ('ld', 'rd')
                    for place, name in zip(places, who):
                        hit = [r for n, r in rows.items() if n == norm(name)] or [r for n, r in rows.items() if n.endswith(norm(name))]
                        if len(hit) != 1:
                            raise SpecError(f'{abbr}: {grp} — «{name}» не из состава спеки (или не один)')
                        fixed[f'l{grp[1]}{place}'] = hit[0]
                gk = [x['row'] for x in plan if x['pos'] == 'G'][:2]
                fixed['g1'], fixed['g2'] = gk
                if len(set(fixed.values())) != 20:
                    raise SpecError(f'{abbr}: в звеньях спеки игрок дважды')
                self.spec_lines[slot] = fixed
                self.rules[slot] = f'спека {os.path.basename(NATIONS_SPEC)}, звенья и пары — из спеки'
            else:
                self.rules[slot] = f'спека {os.path.basename(NATIONS_SPEC)}, звенья по позициям'

    # Матч звёзд ----------------------------------------------------------------------------------------------------
    def last_season(self):
        """{game_id: очки регулярки НХЛ прошлого сезона} и {game_id: победы вратаря} — для равного OVR."""
        db, year = self.db, SEASON_YEAR - 1900          # год таблицы — год конца сезона − 1900: 2025/26 → 126
        pts, wins = Counter(), Counter()
        for table, field, out in (('stockcareerseasonplayerstats', 'points', pts),
                                  ('stockcareerseasongoaliestats', 'wins', wins)):
            for i in range(db.by_name[table]['rows']):
                if db.value(table, 'year', i) == year and db.value(table, 'league', i) == 0:
                    out[db.get(table, 'game_id', i)] += db.value(table, field, i)
        return pts, wins

    def plan_allstar(self):
        db, v, u = self.db, self.v, self.u
        pts, wins = self.last_season()
        conf_of = {db.value(T, 'conferencegroup', t): t for t in ALLSTAR}
        cand = defaultdict(list)
        for e in u.entries:
            if e['team'] not in NHL:
                continue
            r = u.row(e)
            conf = db.value(T, 'conferencegroup', e['team'])
            if conf not in conf_of:
                raise SpecError(f'{SLOT_TEAM[e["team"]]}: конференция {conf} — нет команды Матча звёзд')
            pos = POS_NAME[v.g('position', r)]
            stat = wins[v.gid[r]] if pos == 'G' else pts[v.gid[r]]
            cand[conf_of[conf]].append({'row': r, 'club': e['team'], 'pos': pos, 'grp': group(pos), 'ovr': u.ovr(r),
                                        'stat': stat, 'jersey': e['jersey'], 'birth': v.birth(r)})
        for slot, pool in cand.items():
            pool.sort(key=lambda c: (-c['ovr'], -c['stat'], tuple(-x for x in c['birth']), c['row']))
            clubs_all = {c['club'] for c in pool}
            # 1) лучшие по OVR в пределах мест амплуа
            room = dict(ALLSTAR_SIZE)
            chosen = []
            for c in pool:
                if room[c['grp']] > 0:
                    chosen.append(c)
                    room[c['grp']] -= 1
            # 2) клуб без представителя: его игрок встаёт на место самого слабого выбранного того же амплуа из клуба,
            #    где выбраны двое и больше; из игроков клуба — тот, чья замена меньше всего ослабляет команду по OVR, при
            #    равной потере — сильнейший (клубы — по очереди, начиная с того, чей лучший игрок сильнее)
            rank = {id(c): i for i, c in enumerate(pool)}
            while True:
                per = Counter(c['club'] for c in chosen)
                lack = sorted(clubs_all - set(per), key=lambda k: min(rank[id(c)] for c in pool if c['club'] == k))
                if not lack:
                    break
                club = lack[0]
                best = None
                for c in (c for c in pool if c['club'] == club):
                    out = [x for x in chosen if x['grp'] == c['grp'] and per[x['club']] > 1]
                    if not out:
                        continue
                    victim = max(out, key=lambda x: rank[id(x)])
                    gain = (c['ovr'] - victim['ovr'], -rank[id(c)])     # равная потеря — лучший игрок клуба
                    if best is None or gain > best[0]:
                        best = (gain, c, victim)
                if best is None:
                    raise SpecError(f'{self.abbr(slot)}: клубу {SLOT_TEAM[club]} не нашлось места')
                chosen.remove(best[2])
                chosen.append(best[1])
            best_of = {c['club'] for c in pool}
            # 3) центров не меньше MIN_CENTRES: слабейший крайний (клуб которого представлен ещё кем-то) → лучший центр
            while sum(c['pos'] == 'C' for c in chosen) < MIN_CENTRES:
                per = Counter(c['club'] for c in chosen)
                out = [c for c in chosen if c['grp'] == 'F' and c['pos'] != 'C' and per[c['club']] > 1]
                inn = [c for c in pool if c not in chosen and c['pos'] == 'C']
                if not out or not inn:
                    break
                chosen.remove(min(out, key=lambda c: (c['ovr'], c['stat'])))
                chosen.append(inn[0])
            clubs = {c['club'] for c in chosen}
            if len(clubs) != len(best_of):
                raise SpecError(f'{self.abbr(slot)}: клубов {len(clubs)} из {len(best_of)}')
            top = sorted((c for c in chosen if c['grp'] != 'G'), key=lambda c: (-c['ovr'], -c['stat'], c['row']))
            letter = {top[0]['row']: 1, top[1]['row']: 2, top[2]['row']: 2}
            self.plans[slot] = [{'row': c['row'], 'how': 'allstar', 'name': v.name(c['row']), 'pos': c['pos'],
                                 'jersey': c['jersey'], 'letter': letter.get(c['row'], 0), 'flags': None, 'p27': None,
                                 'src': 'allstar', 'club': SLOT_TEAM[c['club']], 'stat': c['stat']}
                                for c in chosen]
            self.rules[slot] = (f"Матч звёзд: конференция {'Восток' if slot == conf_of.get(2) else 'Запад'}, "
                                f"{sum(ALLSTAR_SIZE.values())} игроков, от каждого из {len(clubs)} клубов, дальше по OVR; звенья по позициям")

    # запись --------------------------------------------------------------------------------------------------------
    def apply(self):
        db, v, u = self.db, self.v, self.u
        teams = set(self.plans)
        old = [e for e in u.entries if e['team'] in teams]
        u.entries = [e for e in u.entries if e['team'] not in teams]
        old_links = [e['playerindex'] for e in old]
        selected = {x['row'] for plan in self.plans.values() for x in plan if x['row'] is not None}

        # строки для тех, кого в базе нет: выбывшие «только из сборной», потом игроки без клуба
        leaving, pool = set(), []
        for r in range(v.nbio):
            if r in selected or v.created_slot(r) or not v.ai(r) or r in v.fa_rows or self.protected(r):
                continue
            ts = set(v.teams_of[r])
            if ts and ts <= teams:
                leaving.add(r)
                pool.append((r, ts))
            elif not ts:
                pool.append((r, ts))
        used = set()
        for slot in sorted(teams):
            keep = []
            for x in self.plans[slot]:
                if x['row'] is None:
                    goalie = x['pos'] == 'G'
                    cands = [(0 if slot in ts else 1 if ts else 2, v.birth(r), r) for r, ts in pool
                             if r not in used and v.is_goalie(r) == goalie]
                    if not cands:
                        self.missing[slot].append(f"{x['name']} ({x['pos']}): нет свободной строки-донора")
                        continue
                    r = min(cands)[2]
                    used.add(r)
                    x.update(row=r, donor=f'{v.name(r)} ({v.birth(r)[0]})')
                    self.write_new(x, r, slot)
                    self.new.append({'team': self.abbr(slot), 'name': x['name'], 'pos': x['pos'], 'donor': x['donor'],
                                     'ovr': u.player(r)['ovr']})
                keep.append(x)
            self.plans[slot] = keep
        gone = {v.gid[r] for r in used}
        self.clean_stats(gone)
        # игрок сборной NHL 27, который у нас есть, но без клуба и не в пуле СА: других данных о нём нет — биография и
        # атрибуты из NHL 27 (голова, портрет, статистика — свои)
        self.refreshed = []
        for slot, plan in self.plans.items():
            for x in plan:
                r = x['row']
                if (x['p27'] and not x.get('donor') and r not in v.fa_rows
                        and not any(t not in SPECIAL for t in v.teams_of[r])):
                    self.write_new(x, r, slot, look=False)
                    self.refreshed.append(f"{self.abbr(slot)}: {x['name']}")
        # выбывшие без клуба — без команды (как ветераны), игроки «только из сборной» — в своей сборной
        for r in leaving - used:
            db.set(B, 'team', r, 0)
        for slot, plan in self.plans.items():
            for x in plan:
                r = x['row']
                if not any(t not in SPECIAL for t in v.teams_of[r]) and r not in v.fa_rows and slot in NATIONAL:
                    db.set(B, 'team', r, slot + 1)

        # связи: своя (из прежних записей особых команд или ничья), потом прежняя чужая (playerid — новому), потом новая
        live = {e['playerindex'] for e in u.entries} | set(u.fa)
        own = defaultdict(list)
        for l in old_links:
            own[v.link_gid[l]].append(l)
        for l, g in v.link_gid.items():
            if l not in live and l not in v.link_created and l not in old_links:
                own[g].append(l)
        for g in own:
            own[g].sort()
        same_team = {(v.link_gid[e['playerindex']], e['team']): e['playerindex'] for e in old}
        for slot in sorted(teams):                           # сначала — связь, которая была у него в этой же команде
            for x in self.plans[slot]:
                g = v.gid[x['row']]
                x['link'] = same_team.get((g, slot))
                if x['link'] is not None:
                    own[g].remove(x['link'])
        need = []
        for slot in sorted(teams):
            for x in self.plans[slot]:
                g = v.gid[x['row']]
                if x['link'] is None:
                    x['link'] = own[g].pop(0) if own[g] else None
                if x['link'] is None:
                    need.append(x)
        spare = sorted(l for l in old_links if l in own[v.link_gid[l]])
        p_row = {db.get(P, 'index', i): i for i in range(db.by_name[P]['rows'])}
        top = max(i for i in v.link_gid if i < LINK_LIMIT)
        new_links = []
        for x in need:
            g = v.gid[x['row']]
            if spare:
                x['link'] = spare.pop(0)
                db.set(P, 'playerid', p_row[x['link']], g)
            else:
                top += 1
                if top >= LINK_LIMIT:
                    raise SpecError('связей exhibitionplayers больше нет (до 16000)')
                x['link'] = top
                new_links.append((top, g))
        if new_links:
            rows = [{'index': db.get(P, 'index', i), 'playerid': db.get(P, 'playerid', i), 'table': db.get(P, 'table', i)}
                    for i in range(db.by_name[P]['rows'])] + [{'index': l, 'playerid': g, 'table': 0} for l, g in new_links]
            u.rows_write(P, sorted(rows, key=lambda x: x['index']))
        self.links = {'repointed': len(need) - len(new_links), 'new': len(new_links)}

        # записи составов, звенья, буквы, номера
        for slot in sorted(teams):
            plan = self.plans[slot]
            ents = []
            for x in plan:
                r = x['row']
                t, ai = v.ai(r)
                e = {f: 0 for f in v.entry_fields}
                e.update(playerindex=x['link'], team=slot, playerstyle=db.get(t, 'playerstyle', ai),
                         captain=x['letter'] or 0, key=slot * RU.MAX_PER_TEAM + 10 ** 6)
                want = x['jersey'] if x['jersey'] else v.g('jersey', r)
                e['jersey'] = u.free_number(ents, want or 0)
                ents.append(e)
                x['entry'] = e
            if len(ents) > RU.MAX_PER_TEAM:
                raise SpecError(f'{self.abbr(slot)}: {len(ents)} игроков, больше {RU.MAX_PER_TEAM}')
            u.entries += ents
            self.lines(slot, plan)
            self.letters(slot, plan)
            for x in plan:                                   # у игрока без клуба номер в биографии — как в сборной
                r = x['row']
                if not any(t not in SPECIAL for t in v.teams_of[r]) and r not in v.fa_rows:
                    db.set(B, 'jersey', r, x['entry']['jersey'])
        u.touched = set(teams)
        u.flush()

    def lines(self, slot, plan):
        u, v = self.u, self.v
        lp = [dict(u.player(x['row']), key=v.gid[x['row']], _e=x['entry']) for x in plan]
        keys, dressed = {}, set()
        if all(x['flags'] is not None for x in plan):
            for x in plan:
                for f in x['flags']:
                    keys.setdefault(f, []).append(v.gid[x['row']])
                if x['flags']:
                    dressed.add(v.gid[x['row']])
            if all(len(keys.get(f, [])) == 1 for f in FLAGS) and len(dressed) == 20:
                keys = {f: k[0] for f, k in keys.items() if f in FLAGS}
                ovr = {p['key']: p['ovr'] for p in lp}
                self.rules[slot] += '; звенья как в NHL 27'
                if ovr[keys['g2']] > ovr[keys['g1']]:        # основной — сильнейший (как у roster_update.py)
                    keys['g1'], keys['g2'] = keys['g2'], keys['g1']
                    self.rules[slot] += ', основной вратарь — сильнейший из двух'
                u.put_lines(lp, keys, dressed)
                return
            self.rules[slot] += '; звенья по рейтингу (в NHL 27 не все места)' if any(x['src'] == 'nhl27' for x in plan) else ''
        try:
            if slot in self.spec_lines:
                keys = {f: v.gid[r] for f, r in self.spec_lines[slot].items()}
                dressed = set(keys.values())
            else:
                keys, dressed = pos_lines(lp, self.centre_ok, self.club_key)
            # большинство, меньшинство, овертайм, буллиты, лишние — по рейтингу среди тех же 20 одетых
            rest, d2 = LN.build([p for p in lp if p['key'] in dressed])
        except LN.NotEnoughPlayers as e:
            raise SpecError(f'{self.abbr(slot)}: звенья не собрать ({e})')
        if d2 != dressed:
            raise SpecError(f'{self.abbr(slot)}: одетые спецбригад не совпали с одетыми звеньев')
        rest.update(keys)
        u.put_lines(lp, rest, dressed)

    def letters(self, slot, plan):
        """Ровно один C и два A у одетых полевых: данные источника, недостающие — самым опытным (игры в НХЛ, потом OVR)."""
        v, u = self.v, self.u
        sk = [x for x in plan if x['entry']['rosterstatus'] and x['pos'] != 'G']
        for x in plan:
            if x not in sk:
                x['entry']['captain'] = 0
        rank = lambda x: (-v.g('nhlgamesplayedcareer', x['row']), -u.ovr(x['row']), x['row'])
        cs = sorted((x for x in sk if x['entry']['captain'] == 1), key=rank)
        for x in cs[1:]:
            x['entry']['captain'] = 2
        a = sorted((x for x in sk if x['entry']['captain'] == 2), key=rank)
        for x in a[2:]:
            x['entry']['captain'] = 0
        free = sorted((x for x in sk if not x['entry']['captain']), key=rank)
        if not cs and free:
            free.pop(0)['entry']['captain'] = 1
        for _ in range(2 - min(2, len(a))):
            if free:
                free.pop(0)['entry']['captain'] = 2

    def write_new(self, x, r, slot, look=True):
        """Строка донора → игрок NHL 27 из сборной: биография и атрибуты как у league27.py, без прав и контракта НХЛ.
        look=False — тот же человек уже в строке: голова, портрет и голос комментатора не меняются."""
        db = self.db
        p27 = x['p27']
        b = p27['bio']
        fields, lows = db.by_name[B]['fields'], db.by_name[B]['lows']
        ok = self.safe_chars()
        clean = lambda s: ''.join(ch if ord(ch) < 128 or ch in ok else
                                  __import__('unicodedata').normalize('NFKD', ch).encode('ascii', 'ignore').decode()
                                  for ch in s or '')
        for f in ('firstname', 'lastname', 'birthplace'):
            db.set_string(B, f, r, fit_utf8(clean(b.get(f) or ''), fields[f][1] // 8 - 1))
        for f, (_, w) in fields.items():
            if f in BIO_SKIP or f not in b:
                continue
            db.set(B, f, r, clamp(b[f] - lows.get(f, 0), w))
        put = lambda f, val: db.set(B, f, r, clamp(val - lows.get(f, 0), fields[f][1]))
        put('team', slot)
        nhl = lambda t: nhl27.NHL_SLOT.get(t, -1) if 0 <= t <= 31 else -1
        put('draftteam', nhl(b['draftteam']))
        put('juniorteam', -1)
        put('juniorleague', 0)
        for f in CONTRACT:                                   # только сборная: без прав и контракта НХЛ (как ветераны)
            if f in fields:
                db.set(B, f, r, 0)
        self.write_ratings(p27, r)
        if not look:
            return
        db.set(B, 'audioid', r, 0)
        db.set(B, 'hasportrait', r, 0)
        heads = self.heads()
        pool = [h for h, c in heads.items() if c == b.get('skincolor')] or sorted(heads)
        head = sorted(pool)[zlib.crc32(x['name'].encode()) % len(pool)]
        db.set(B, 'headid', r, head)
        db.set(B, 'skincolor', r, heads[head])

    def write_ratings(self, p27, r):
        """Атрибуты, стиль, тенденции, черты, рост — из NHL 27 (атрибуты − 36, потенциал — nhl27.POTENTIAL)."""
        db = self.db
        t, row = self.v.ai(r)
        src, afields, alows = p27['ai'], db.by_name[t]['fields'], db.by_name[t]['lows']
        for f, (_, w) in afields.items():
            if f == 'game_id':
                continue
            if f not in src:
                db.set(t, f, row, 0)
                continue
            val = src[f]
            if f == 'c_potential':
                raw = nhl27.POTENTIAL.get(val, 30 if val >= 54 else 5)
            elif f in ATTR_FIELDS:
                raw = val - BASE
            else:
                raw = val - alows.get(f, 0)
            db.set(t, f, row, clamp(raw, w))
        self.u._p.pop(r, None)

    def safe_chars(self):
        if not hasattr(self, '_safe'):
            v = self.v
            self._safe = {ch for r in range(v.nbio) for f in ('firstname', 'lastname', 'birthplace')
                          for ch in v.s(f, r) if ord(ch) > 127}
        return self._safe

    def heads(self):
        """Типовые головы базы → тон кожи (как Writer.generic_heads)."""
        if not hasattr(self, '_heads'):
            v = self.v
            self._heads = {}
            for r in range(v.nbio):
                if not v.created_slot(r) and v.g('headid', r) >= GENERIC_HEAD:
                    self._heads.setdefault(v.g('headid', r), v.g('skincolor', r))
        return self._heads

    def clean_stats(self, gone):
        """Статистика прежних владельцев строк-доноров (карьера НХЛ/АХЛ и международные турниры) — прочь."""
        db = self.db
        self.stats_removed = {}
        for table, key in [(t, 'game_id') for t in STATS] + [(t, 'playerid') for t in INTL_STATS]:
            n = db.by_name[table]['rows']
            keep = [db.record(table, i) for i in range(n) if db.get(table, key, i) not in gone]
            if len(keep) != n:
                db.resize(table, len(keep))
                for i, raw in enumerate(keep):
                    db.put_record(table, i, raw)
                self.stats_removed[table] = n - len(keep)


# --- проверки ---------------------------------------------------------------------------------------------------------
def verify_special(db, teams):
    v = View(db)
    bad = []
    by = defaultdict(list)
    for e in v.entries:
        by[e['team']].append(e)
    for t in sorted(teams):
        te = by[t]
        name = db.get_string(T, 'abbrname', t)
        for f in FLAGS:
            n = sum(e[f] for e in te)
            if n != 1:
                bad.append(f'{name}: место {f} у {n}')
            for e in te:
                if e[f]:
                    r = v.row_of_gid[v.link_gid[e['playerindex']]]
                    if (LN.slot_kind(f) == 'G') != v.is_goalie(r):
                        bad.append(f'{name}: на месте {f} {v.name(r)}')
        dressed = [e for e in te if any(e[f] for f in FLAGS)]
        if len(dressed) != 20 or any(bool(e['rosterstatus']) != (e in dressed) for e in te):
            bad.append(f'{name}: одетых {len(dressed)}, rosterstatus не совпадает')
        caps = Counter(e['captain'] for e in te)
        if caps[1] != 1 or caps[2] != 2:
            bad.append(f'{name}: буквы {dict(caps)}')
        nums = Counter(e['jersey'] for e in te)
        bad += [f'{name}: номер {n} у двоих' for n, c in nums.items() if c > 1]
        rows = [v.row_of_gid[v.link_gid[e['playerindex']]] for e in te]
        bad += [f'{name}: {v.name(r)} дважды' for r, c in Counter(rows).items() if c > 1]
        if not 20 <= len(te) <= RU.MAX_PER_TEAM:
            bad.append(f'{name}: {len(te)} игроков')
    return bad


# --- отчёт ------------------------------------------------------------------------------------------------------------
def team_text(db, t):
    """Состав команды: звенья, пары, вратари, запасные — строки для отчёта и show."""
    v = View(db)
    te = [e for e in v.entries if e['team'] == t]
    row = lambda e: v.row_of_gid[v.link_gid[e['playerindex']]]
    letter = {1: ' (C)', 2: ' (A)'}

    def who(f):
        e = next((e for e in te if e[f]), None)
        if e is None:
            return '—'
        r = row(e)
        cl = [x for x in v.teams_of[r] if x not in SPECIAL]
        club = (SLOT_TEAM.get(cl[0]) or db.get_string(T, 'abbrname', cl[0])) if cl else ('FA' if r in v.fa_rows else 'без клуба')
        return f"{v.name(r)}{letter.get(e['captain'], '')} #{e['jersey']} {club} {v.overall(r)}"

    out = [f"{db.get_string(T, 'abbrname', t)} — {db.get_string(T, 'fullname', t)}: {len(te)} игроков"]
    for n in (1, 2, 3, 4):
        out.append(f'  {n}: ' + ' | '.join(who(f'l{n}{p}') for p in ('lw', 'c', 'rw')))
    for n in (1, 2, 3):
        out.append(f'  D{n}: ' + ' | '.join(who(f'l{n}{p}') for p in ('ld', 'rd')))
    out.append(f"  G: {who('g1')} | {who('g2')}")
    rest = [e for e in te if not e['rosterstatus']]
    if rest:
        out.append('  запас: ' + ', '.join(f'{v.name(row(e))} #{e["jersey"]}' for e in rest))
    return out


def write_report(path, sp, db, teams, extra):
    L = ['# Особые команды: сборные и Матч звёзд', '']
    L += [f'- {k}: {x}' for k, x in extra.items()]
    L += [f"- новые игроки (строки доноров): {len(sp.new)}; связи: переназначено {sp.links['repointed']}, новых {sp.links['new']}",
          f"- статистика доноров убрана: {sp.stats_removed or 'нет'}",
          f"- без клуба, данные обновлены из NHL 27: {len(sp.refreshed)}", '']
    for t in sorted(teams):
        L += [f"## {db.get_string(T, 'abbrname', t)} — {sp.rules.get(t, '')}", '', '```'] + team_text(db, t) + ['```']
        if sp.missing.get(t):
            L.append('Нет в составе: ' + '; '.join(sp.missing[t]))
        nw = [n for n in sp.new if n['team'] == db.get_string(T, 'abbrname', t)]
        if nw:
            L.append('Новые (из NHL 27, строка донора): ' + ', '.join(f"{n['name']} {n['pos']} {n['ovr']} ← {n['donor']}" for n in nw))
        L.append('')
    open(path, 'w', encoding='utf-8').write('\n'.join(L) + '\n')


def install_text(roster_file, dbdir):
    db = os.path.join(RU.USERDATA, 'cache', 'guest', 'db')
    exe = RU.LAUNCHERS[1]
    keep = os.path.join(os.path.dirname(dbdir), 'before-install')
    return f'''
## Установка (игра закрыта)

```powershell
New-Item -ItemType Directory -Force "{keep}" | Out-Null
Copy-Item "{db}\\nhlng.db","{db}\\draft_roster.db" "{keep}"
Copy-Item "{dbdir}\\nhlng.db","{dbdir}\\draft_roster.db" "{db}" -Force
Start-Process -Wait -PassThru "{exe}" -ArgumentList '--import-roster','"{roster_file}"'
```

Откат: оба файла из `{keep}` обратно, новый ростер удалить в игре: CUSTOMIZE → SAVE/LOAD/DELETE → DELETE → ROSTERS.
'''.replace('\\\\', '\\')


# --- прогон -----------------------------------------------------------------------------------------------------------
def split(s):
    return [x.strip().upper() for x in s.split(',') if x.strip()] if s else []


def run(a):
    log = print
    db_path = a.db or os.path.join(RU.CACHE_DB, 'nhlng.db')
    meta_path = os.path.join(os.path.dirname(db_path), 'nhlng-meta.xml')
    meta = load_meta(meta_path)
    raw0 = open(db_path, 'rb').read()
    db = Tdb(raw0, meta)
    save = a.save or RU.newest_roster()
    date = a.date or datetime.date.today()
    log(f'база {db_path}\nсейв {save}')
    sp = Special(db, log)
    keep = set(split(a.keep) if a.keep is not None else KEEP_DEFAULT)
    own = [x for x in (split(a.own) if a.own is not None else OWN_DEFAULT) if x not in keep]
    every = sorted(db.get_string(T, 'abbrname', t) for t in NATIONAL)
    nhl = [x for x in (split(a.nhl27) if a.nhl27 is not None else every) if x not in keep and x not in own]
    if a.only in (None, 'nations'):
        if nhl:
            sp.plan_nhl27(nhl27.open_db(a.db27), nhl)
        if own:
            sp.plan_spec(parse_nations(a.spec), own)
    if a.only in (None, 'allstar'):
        sp.plan_allstar()
    teams = set(sp.plans)
    sp.apply()
    db.fix()
    bad = RU.verify(db, set()) + verify_special(db, teams)
    if Tdb(bytes(db.d), meta).verify():
        bad.append('CRC базы')
    os.makedirs(a.out, exist_ok=True)
    extra = {'база': db_path, 'сейв': save, 'дата в имени': RU.fmt(date),
             'пересобраны': ', '.join(db.get_string(T, 'abbrname', t) for t in sorted(teams)),
             'не тронуты': ', '.join(sorted(keep)) or '—', 'проверки': f'{len(bad)} проблем'}
    write_report(os.path.join(a.out, 'report.md'), sp, db, teams, extra)
    json.dump({'extra': extra, 'new': sp.new, 'missing': sp.missing, 'rules': {db.get_string(T, 'abbrname', t): r for t, r in sp.rules.items()},
               'teams': {db.get_string(T, 'abbrname', t): [{'name': x['name'], 'pos': x['pos'], 'src': x['src'], 'how': x.get('how'),
                                                           'donor': x.get('donor')} for x in sp.plans[t]] for t in teams},
               'problems': bad}, open(os.path.join(a.out, 'report.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    log(f"команд {len(teams)}; новых игроков {len(sp.new)}; нет в составах {sum(len(x) for x in sp.missing.values())}; "
        f"проверки: {len(bad)} проблем; база {'как была' if bytes(db.d) == raw0 else 'изменилась'}")
    for b in bad[:30]:
        log('  ' + b)
    if bad:
        raise SystemExit('проверки не прошли: ничего не записано (отчёт — в папке out)')
    if a.dry_run:
        log(f"проба: база и сейв не записаны; отчёт — {os.path.join(a.out, 'report.md')}")
        return 0
    dbdir = os.path.join(a.out, 'db')
    os.makedirs(dbdir, exist_ok=True)
    new_db = os.path.join(dbdir, 'nhlng.db')
    with open(new_db + '.part', 'wb') as f:
        f.write(db.d)
    os.replace(new_db + '.part', new_db)
    shutil.copy2(meta_path, os.path.join(dbdir, 'nhlng-meta.xml'))
    dr = os.path.join(dbdir, 'draft_roster.db')
    with open(dr + '.part', 'wb') as f:
        f.write(draft_roster.extract(db, set(draft_roster.KEEP)))
    os.replace(dr + '.part', dr)
    out_roster = os.path.join(a.out, f'ROSTER {RU.fmt(date)}')
    shutil.copy2(save, out_roster)
    roster_merge.run(out_roster, db_path, new_db, True, os.path.join(a.out, 'merge.json'))
    sf = SaveFile(open(out_roster, 'rb').read(), meta)
    if sf.verify():
        raise SystemExit(f'сейв не прошёл проверку: {sf.verify()[:3]}')
    launcher = next((x for x in ([a.launcher] if a.launcher else RU.LAUNCHERS) if x and os.path.isfile(x)), None)
    if launcher:
        code = RU.launcher_check(launcher, out_roster, dbdir, WORK, log)
        if code:
            raise SystemExit(f'лаунчер не принял ростер, код {code}')
    else:
        log('лаунчер не найден: --check-roster пропущен')
    with open(os.path.join(a.out, 'report.md'), 'a', encoding='utf-8') as f:
        f.write(install_text(out_roster, dbdir))
    log(f'готово: {out_roster}\nбаза: {new_db}\nотчёт: {os.path.join(a.out, "report.md")}')
    return 0


def show(a):
    path = a.db or os.path.join(RU.CACHE_DB, 'nhlng.db')
    meta = load_meta(a.meta or os.path.join(os.path.dirname(path), 'nhlng-meta.xml'))
    raw = open(path, 'rb').read()
    if raw[:2] != b'DB':
        sys.exit(f'{path}: нужна база (.db). Сейв ROSTER читает tools/tdb.py dump … exhibitionrostertable --where team=…')
    db = Tdb(raw, meta)
    by = {db.get_string(T, 'abbrname', t): t for t in sorted(set(NATIONAL) | set(ALLSTAR))}
    for name in a.teams or sorted(by):
        if name.upper() not in by:
            sys.exit(f'нет команды {name}: {sorted(by)}')
        print('\n'.join(team_text(db, by[name.upper()])))
    return 0


def main(argv=None):
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
    ap = argparse.ArgumentParser(prog='special_rosters.py', description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    r = sub.add_parser('run', help='сборные и Матч звёзд → база и ROSTER')
    r.add_argument('--only', choices=('nations', 'allstar'), help='только сборные или только Матч звёзд')
    r.add_argument('--nhl27', help='сборные из NHL 27 через запятую (по умолчанию все, кроме --own и --keep)')
    r.add_argument('--own', help=f'сборные по своей спеке (по умолчанию {",".join(OWN_DEFAULT)})')
    r.add_argument('--keep', help=f'не трогать (по умолчанию {",".join(KEEP_DEFAULT)}); пустая строка — никого')
    r.add_argument('--spec', default=NATIONS_SPEC, help='спека своих сборных (по умолчанию %(default)s)')
    r.add_argument('--db', help='база, на которой сделан сейв (по умолчанию установленная); схема — рядом')
    r.add_argument('--db27', help='база NHL 27 (по умолчанию game/work/nhl27/db/nhl_game.db)')
    r.add_argument('--save', help='файл ROSTER (по умолчанию новейший у пользователя)')
    r.add_argument('--date', type=lambda s: RU.parse_date(s, '--date'), help='дата в имени ROSTER (по умолчанию сегодня)')
    r.add_argument('--out', default=os.path.join(WORK, 'out'), help='куда писать (по умолчанию %(default)s)')
    r.add_argument('--launcher', help='лаунчер для --check-roster (по умолчанию свежая сборка)')
    r.add_argument('--dry-run', action='store_true', help='всё посчитать, записать только отчёт')
    s = sub.add_parser('show', help='состав и звенья сборных и команд Матча звёзд')
    s.add_argument('teams', nargs='*', help='аббревиатуры: RUS, CAN, EAS, WES… (по умолчанию все)')
    s.add_argument('--db', help='база (по умолчанию установленная)')
    s.add_argument('--meta', help='схема (по умолчанию рядом с базой)')
    a = ap.parse_args(argv)
    try:
        return run(a) if a.cmd == 'run' else show(a)
    except (SpecError, RU.SpecError) as e:
        sys.exit(f'ошибка: {e}')


if __name__ == '__main__':
    sys.exit(main())
