"""Этап write: players.json + match.json → game/work/roster/nhlng.db (через tools/tdb.py).

Что меняется (подробно — docs/roster-pipeline.md):
1. Строки игроков. Сопоставленный игрок обновляется на месте (лицо, портрет и имя у
   комментатора — его). Новый занимает строку «донора» того же класса (вратарь — вратаря):
   ушедшего из НХЛ игрока 2012 года, свободного агента или игрока без команды — старшие
   первыми; игроков сборных, Матча звёзд, легенд, проспектов и Зимней классики не трогаем,
   клубы АХЛ/Европы/юниоров — только если не хватит. У донора стираются портрет (hasportrait
   0), голос комментатора (audioid 0), лицо (типовая голова), черты и карьерная статистика;
   artid — свой, из диапазона 9803–16383 (ID EA, если он туда попадает), с таблицей
   соответствия game/work/roster/artid-registry.json.
2. Биография: имя, дата и место рождения, провинция/страна, гражданство, рост, вес, хват,
   амплуа, номер, команда и права (proteam: у команды 31 — Вегаса — 0, не влезает в 5 бит),
   драфт, дебют, игры в НХЛ, новичок. Контракт — заглушка по OVR и возрасту (следующий этап).
3. Рейтинги NHL 27 (ratings.py) и стиль.
4. exhibitionrostertable целиком пересобирается: составы 32 клубов НХЛ со звеньями (lines.py) и
   буквами, место каждого ушедшего из клуба АХЛ/Европы/юниоров занимает ушедший из НХЛ игрок
   того же амплуа (размеры и звенья этих команд не меняются), key = команда × 40 + место,
   внутри команды — по возрастанию playerindex (как в исходной базе). Ушедшие из НХЛ, кому
   места нет, остаются без команды (как 41 такой игрок исходной базы).
5. exhibitionfreeagents — без занятых игроков; exhibitionplayers — новые связи, если нужны.
Потом — проверки (verify ниже) и пересчёт CRC.
"""
import os
import shutil
import unicodedata
import zlib
from collections import Counter, defaultdict

from . import lines as lines_mod
from .codes import NONE, country_code, state_code
from .common import SEASON, SEASON_YEAR, SLOT_TEAM, fit_utf8, norm, read_json, team_slot, write_json
from .dbview import (B, CLUBS, F, FLAGS, G, LINK_LIMIT, NHL, P, POS_CODE, R, S, SPECIAL, View)
from .match import load_db
from .ratings import BASE, SK_BIAS, TRAITS, Model, age, clamp_rating

ART_MIN, ART_MAX = 9803, 16383          # свободные artid: портреты на диске — до p9802, поле — 14 бит
STATS = ['stockcareerseasonplayerstats', 'stockcareerplayoffplayerstats', 'stockcareerseasongoaliestats',
         'stockcareerplayoffgoaliestats']
TIER = {0: 'ушедший из НХЛ', 1: 'свободный агент 2012', 2: 'без команды', 3: 'клуб (АХЛ/Европа/юниоры)'}
MAX_PER_TEAM = 40


class Writer:
    def __init__(self, paths, log=print):
        self.paths, self.log = paths, log
        self.db, self.meta_path = load_db(paths)
        self.v = View(self.db)
        data = read_json(paths.players)
        mt = read_json(paths.matched)
        if not data or not mt:
            raise SystemExit('нет players.json или match.json — сначала build и match')
        self.players = data['players']
        self.mt = mt['players']
        self.registry = read_json(paths.registry, {}) or {}
        self.model = Model(self.v, self.players)
        self.safe = {ch for r in range(self.v.nbio) for f in ('firstname', 'lastname', 'birthplace')
                     for ch in self.v.s(f, r) if ord(ch) > 127}
        self.notes = defaultdict(list)       # nhl_id -> [что не заполнено / заглушка]
        self.events = []                      # строки отчёта о составах
        self.out = {}                         # nhl_id -> итог по игроку
        self.new_links = []                   # (index, game_id)

    # --- 1. строки игроков -----------------------------------------------------------------
    def donor_candidates(self, taken):
        v = self.v
        out = {'G': [], 'S': []}
        for r in range(v.nbio):
            if r in taken or v.created_slot(r) or not v.ai(r):
                continue
            teams = v.teams_of[r]
            if any(t in SPECIAL for t in teams):
                continue
            if any(t in NHL for t in teams):
                tier = 0
            elif r in v.fa_rows:
                tier = 1
            elif not teams:
                tier = 2
            else:
                tier = 3
            out['G' if v.is_goalie(r) else 'S'].append((tier >= 3, v.birth(r)[0], tier, r))
        for k in out:
            out[k].sort()
        return out

    def plan(self):
        v = self.v
        self.row_of, self.new, self.no_room = {}, set(), []
        for p in self.players:
            m = self.mt.get(str(p['nhl_id']))
            if m and m['row'] is not None:
                self.row_of[p['nhl_id']] = m['row']
        cands = self.donor_candidates(set(self.row_of.values()))
        self.donor_info = {}
        for kind in ('G', 'S'):
            need = [p for p in self.players if p['nhl_id'] not in self.row_of and (p['pos'] == 'G') == (kind == 'G')]
            need.sort(key=lambda p: (p['slot'], p['nhl_id']))
            pool = cands[kind]
            for p in need:
                if not pool:
                    self.no_room.append(p)
                    continue
                _, year, tier, r = pool.pop(0)
                self.row_of[p['nhl_id']] = r
                self.new.add(p['nhl_id'])
                self.donor_info[p['nhl_id']] = {'row': r, 'name': v.name(r), 'birth': list(v.birth(r)),
                                                'teams': list(v.teams_of[r]), 'tier': TIER[tier],
                                                'artid': v.g('artid', r), 'game_id': v.gid[r]}
        self.players = [p for p in self.players if p['nhl_id'] in self.row_of]
        self.p_of_row = {self.row_of[p['nhl_id']]: p for p in self.players}

    # --- 2. биография ----------------------------------------------------------------------
    def clean(self, text):
        out = []
        for ch in text or '':
            if ord(ch) < 128 or ch in self.safe:
                out.append(ch)
            else:     # буквы, которых нет в базе (а значит, может не быть и в шрифте), — без знаков
                out.append(unicodedata.normalize('NFKD', ch).encode('ascii', 'ignore').decode())
        return ''.join(out)

    def set_name(self, r, p, new):
        db, v = self.db, self.v
        same = norm(v.s('firstname', r) + v.s('lastname', r)) == norm(p['first'] + p['last'])
        if new or not same:
            for field, text in (('firstname', p['first']), ('lastname', p['last'])):
                limit = db.by_name[B]['fields'][field][1] // 8 - 1
                db.set_string(B, field, r, fit_utf8(self.clean(text), limit))

    def generic_heads(self):
        v = self.v
        heads = Counter()
        for r in range(v.nbio):
            if not v.created_slot(r) and v.g('headid', r) >= 10000:      # 10000+ — типовые головы
                heads[(v.g('headid', r), v.g('skincolor', r))] += 1
        skin = Counter()
        for (h, c), n in heads.items():
            skin[c] += n
        usual = skin.most_common(1)[0][0]
        self.heads = sorted(k for k in heads if k[1] == usual)

    def assign_artids(self):
        v = self.v
        donors = {self.row_of[i] for i in self.new}
        used = {v.g('artid', r) for r in range(v.nbio) if r not in donors} - {0}
        reserved = {p['ea']['ea_id'] for p in self.players if p.get('ea') and p['ea']['ea_id'] <= ART_MAX}
        regvals = set(self.registry.values())
        self.artid = {}
        for p in sorted((p for p in self.players if p['nhl_id'] in self.new), key=lambda p: p['nhl_id']):
            key = str(p['nhl_id'])
            ea = (p.get('ea') or {}).get('ea_id')
            a = self.registry.get(key)
            if not (a and ART_MIN <= a <= ART_MAX and a not in used):
                a = ea if ea and ART_MIN <= ea <= ART_MAX and ea not in used else None
            if a is None:
                a = next(x for x in range(ART_MIN, ART_MAX + 1) if x not in used and x not in reserved and x not in regvals)
            used.add(a)
            self.artid[p['nhl_id']] = a
            self.registry[key] = a

    def contract(self, p, ovr, r):
        """Заглушка контракта (этап контрактов — потом): сумма по OVR, срок по возрасту."""
        a = age(p['birth'])
        mln = (10.0 if ovr >= 90 else 8.0 if ovr >= 87 else 6.0 if ovr >= 84 else 4.0 if ovr >= 81
               else 2.5 if ovr >= 78 else 1.5 if ovr >= 75 else 0.9)
        if p['rookie'] and a <= 24:
            mln = min(mln, 0.95)
        length = 3 if a <= 23 else 4 if a <= 29 else 2 if a <= 33 else 1
        dr = p.get('draft') or {}
        first = (dr.get('year') + 1) if dr.get('year') else (int(str(p['nhl_gp']['debut'])[:4]) if p['nhl_gp']['debut']
                                                              else SEASON_YEAR)
        first = min(first, SEASON_YEAR)
        signed_age = first - p['birth'][0]
        exempt = 5 if signed_age <= 18 else 4 if signed_age == 19 else 3
        waiver = first + exempt
        if p['nhl_gp']['career'] >= 160:
            waiver = min(waiver, SEASON_YEAR)
        return {'contractdollars': round(mln * 1e6 / 5000), 'contractlength': length, 'contractstatus': 1,
                'contractis2way': int(ovr < 76 and a <= 25), 'contractismultiyear': int(length > 1),
                'contractneedsentrylevel': 0, 'yearufa': SEASON_YEAR + length - 1900, 'extensionlength': 0,
                'extensiondollars': 0, 'extensionis2way': 0, 'yearfirstsigned': first - 1900,
                'yearwaivereligible': waiver - 1900, 'waiversneedreentry': 0}

    def write_bio(self, p, r, new, ovr):
        db, v, notes = self.db, self.v, self.notes[p['nhl_id']]
        put = lambda f, x: db.set(B, f, r, x)
        self.set_name(r, p, new)
        y, m, d = p['birth']
        put('year', y - 1900)
        put('month', m - 1)
        put('day', d - 1)
        if p.get('birth_city'):
            db.set_string(B, 'birthplace', r, fit_utf8(self.clean(p['birth_city']), 39))
        else:
            notes.append('нет места рождения')
        st = state_code(p.get('birth_country'), p.get('birth_state'))
        if st == NONE and p.get('birth_country'):
            notes.append(f"страна рождения {p['birth_country']} — кода нет (127)")
        put('state', st)
        nat = country_code(p.get('nationality'))
        if nat is None:
            nat = country_code(p.get('birth_country'))
        put('intlcountry', NONE if nat is None else nat)
        if p.get('height_in'):
            put('height', max(0, min(31, p['height_in'] - 54)))
        if p.get('weight_lb'):
            put('weight', max(0, min(255, p['weight_lb'] - 120)))
        if p.get('shoots') in ('L', 'R'):
            put('handedness', 0 if p['shoots'] == 'L' else 1)
        else:
            notes.append('нет хвата')
        put('position', POS_CODE[p['pos']])
        put('team', p['slot'] + 1)
        if p['slot'] + 1 <= 31:
            put('proteam', p['slot'] + 1)
        else:
            put('proteam', 0)
            notes.append('proteam = 0 (команда 31 не влезает в 5 бит)')
        dr = p.get('draft')
        if dr and dr.get('year'):
            put('draftyear', dr['year'] - 1900)
            put('draftround', min(15, dr.get('round') or 0))
            put('draftposition', min(511, dr.get('overall') or 0))
            ds = team_slot(dr.get('team'))
            if ds is None:
                put('draftteam', 0)
                notes.append(f"draftteam = 0 (клуб драфта {dr.get('team')} не найден)")
            elif ds + 1 > 31:
                put('draftteam', 0)
                notes.append('draftteam = 0 (Вегас, команда 31, не влезает в 5 бит)')
            else:
                put('draftteam', ds + 1)
        else:
            for f, x in (('draftyear', 255), ('draftround', 0), ('draftposition', 0), ('draftteam', 0)):
                put(f, x)
        gp = p['nhl_gp']
        put('yearprodebut', (int(str(gp['debut'])[4:]) - 1900) if gp['debut'] else 0)
        bys = {int(k): n for k, n in gp['by_season'].items()}
        put('nhlgamesplayedcareer', min(4095, gp['career']))
        put('nhlgamesplayedlastseason', min(127, bys.get(SEASON - 10001, 0)))
        put('nhlgamesplayedtwoseasonsago', min(127, bys.get(SEASON - 20002, 0)))
        put('nhlgamesplayedthreeseasonsago', min(127, bys.get(SEASON - 30003, 0)))
        put('progamesplayedcareer', min(4095, max(p['pro_gp'], gp['career'])))
        put('nhlgamesmissedinjurylastseason', 0)
        put('rookie', int(p['rookie']))
        for f, x in (('active', 1), ('isdraftable', 0), ('juniorteam', 0), ('juniorleague', 1), ('junioryearlost', 0)):
            put(f, x)
        for f, x in self.contract(p, ovr, r).items():
            put(f, x)
        if not p['landing']:
            notes.append('нет карточки landing: драфт и игры по сезонам не заполнены')
        if p.get('omitted'):
            notes.append('нет в /roster/current (вероятно, травмирован)')
        if new:
            put('artid', self.artid[p['nhl_id']])
            put('audioid', 0)
            put('hasportrait', 0)
            head, skin = self.heads[zlib.crc32(f"{p['first']} {p['last']}".encode()) % len(self.heads)]
            put('headid', head)
            put('skincolor', skin)

    # --- 3. рейтинги -----------------------------------------------------------------------
    def write_ratings(self, p, r, new):
        db, v, m = self.db, self.v, self.model
        t, row = v.ai(r)
        style = m.style(p, r, new)
        attrs, ovr = m.attributes(p, r, new, style)
        for f, x in attrs.items():
            db.set(t, f, row, x - BASE)
        pot = m.potential(p)
        if t == S:
            old_style = db.get(S, 'p_style', row)
            db.set(S, 'p_overall', row, clamp_rating(ovr) - BASE)
            db.set(S, 'p_style', row, style)
            if new or style != old_style:
                for f in SK_BIAS:
                    if f in m.bias.get(style, {}):
                        db.set(S, f, row, m.bias[style][f])
            db.set(S, 'p_potential', row, pot)
        else:
            db.set(G, 'g_overall', row, clamp_rating(ovr) - BASE)
            db.set(G, 'g_style', row, style)
            db.set(G, 'g_potential', row, pot)
            # g_consistency не трогаем: в базе это не рейтинг, а 0–2 (у 383 из 537 вратарей — 1)
        if pot == 30:
            db.set(t, 'growthtier', row, 0)
            db.set(t, 'growthletter', row, 0)
        elif db.get(t, 'growthtier', row) == 0:
            db.set(t, 'growthtier', row, 6)          # самое частое у взрослых игроков исходной базы
        if new:
            for f in TRAITS:
                if f in db.by_name[t]['fields']:
                    db.set(t, f, row, 0)
        if p['rating']['source'] == 'none':
            self.notes[p['nhl_id']].append(f'рейтинга нет — оценка OVR {ovr}')
        elif p['rating']['source'] in ('nhlratings-ovr', 'ea-ovr'):
            self.notes[p['nhl_id']].append('атрибуты достроены из OVR')
        return attrs, ovr, style

    # --- 4. составы ------------------------------------------------------------------------
    def numbers(self, team_players):
        """Номера в клубе: из API (при повторе номер у лучшего по OVR); нет номера или повтор —
        прежний номер игрока из базы, если свободен, иначе наименьший свободный."""
        api = {p['num'] for p in team_players if p.get('num')}
        out, used = {}, set()
        for p in sorted(team_players, key=lambda p: (-p['_ovr'], p['nhl_id'])):
            n = p.get('num')
            if n and n not in used:
                out[p['nhl_id']] = n
                used.add(n)
        for p in sorted(team_players, key=lambda p: p['nhl_id']):
            if p['nhl_id'] in out:
                continue
            old = self.v.g('jersey', self.row_of[p['nhl_id']]) if p['nhl_id'] not in self.new else 0
            n = old if 0 < old < 99 and old not in used and old not in api else \
                next(x for x in range(2, 99) if x not in used and x not in api)
            self.notes[p['nhl_id']].append(f"номер {p.get('num') or 'нет'} → {n}")
            out[p['nhl_id']] = n
            used.add(n)
        return out

    def letters(self, team_players):
        """Буквы: ровно три (C + 2 A или 3 A); недостающие — опытнейшим (игры в НХЛ)."""
        caps = [p for p in team_players if p.get('letter') == 'C'][:1]
        alts = sorted((p for p in team_players if p.get('letter') == 'A'), key=lambda p: -p['nhl_gp']['career'])
        need = 3 - len(caps)
        alts = alts[:need]
        if len(caps) + len(alts) < 3:
            rest = sorted((p for p in team_players if p not in caps and p not in alts and p['pos'] != 'G'),
                          key=lambda p: (-p['nhl_gp']['career'], -p['_ovr']))
            for p in rest[:3 - len(caps) - len(alts)]:
                alts.append(p)
                self.notes[p['nhl_id']].append('буква A — по опыту (в Wikipedia не найдена)')
        out = {p['nhl_id']: 1 for p in caps}
        out.update({p['nhl_id']: 2 for p in alts})
        return out

    def rebuild_entries(self):
        v, db = self.v, self.db
        new_rows = set(self.p_of_row)
        donors = {self.row_of[i] for i in self.new}
        link_team = {e['playerindex']: e['team'] for e in v.entries}
        row_of_link = lambda l: v.row_of_gid.get(v.link_gid.get(l))
        kept, vacancies = [], []
        for e in v.entries:
            t, r = e['team'], row_of_link(e['playerindex'])
            if t in NHL:
                continue
            if r in new_rows:
                if t in SPECIAL and r not in donors:
                    kept.append(dict(e))            # сам игрок, например Кросби в сборной Канады
                elif t in SPECIAL:
                    raise RuntimeError(f'донор {v.name(r)} в особой команде {t}')
                else:
                    vacancies.append(dict(e))
            else:
                kept.append(dict(e))
        fa_keep = [l for l in v.fa if row_of_link(l) not in new_rows]
        used = {e['playerindex'] for e in kept} | set(fa_keep)
        free_index = (i for i in range(max(i for i in v.link_gid if i < LINK_LIMIT) + 1, LINK_LIMIT)
                      if i not in v.link_gid)

        def pick_link(r, team):
            gid = v.gid[r]
            cand = [l for l in v.links_of[gid] if l not in used and l not in v.link_created]
            cand.sort(key=lambda l: (link_team.get(l) != team, link_team.get(l) in SPECIAL, l))
            if cand:
                l = cand[0]
            else:
                l = next(free_index)
                self.new_links.append((l, gid))
            used.add(l)
            return l

        # ушедшие из НХЛ: те, чьи записи в НХЛ пропадают, а строка не досталась новому игроку
        displaced = []
        for e in v.entries:
            r = row_of_link(e['playerindex'])
            if e['team'] in NHL and r not in new_rows and r not in displaced:
                displaced.append(r)
        self.displaced = list(displaced)
        # места ушедших в НХЛ из клубов АХЛ/Европы/юниоров — ушедшим из НХЛ того же амплуа
        refill = []
        for e in sorted(vacancies, key=lambda e: (e['team'], e['playerindex'])):
            r_old = row_of_link(e['playerindex'])
            pos = v.g('position', r_old)
            same_kind = [r for r in displaced if v.is_goalie(r) == (pos == 4)
                         and (v.g('position', r) == 3) == (pos == 3)]
            if not same_kind:
                same_kind = [r for r in displaced if v.is_goalie(r) == (pos == 4)]
            if not same_kind:
                self.events.append({'team': e['team'], 'what': 'место осталось пустым', 'player': v.name(r_old)})
                continue
            same_kind.sort(key=lambda r: (v.g('position', r) != pos, -v.birth(r)[0], r))
            r = same_kind[0]
            displaced.remove(r)
            ne = dict(e)
            ne['playerindex'] = pick_link(r, e['team'])
            t_ai, row_ai = v.ai(r)
            ne['playerstyle'] = db.get(t_ai, 'p_style' if t_ai == S else 'g_style', row_ai)
            refill.append(ne)
            db.set(B, 'team', r, e['team'] + 1)
            db.set(B, 'proteam', r, 0)
            db.set(B, 'jersey', r, e['jersey'])
            self.events.append({'team': e['team'], 'what': 'место ушедшего в НХЛ', 'player': v.name(r),
                                'instead': v.name(r_old)})
        # остальные ушедшие из НХЛ — без команды и контракта (как 41 игрок исходной базы)
        for r in displaced:
            for f in ('team', 'proteam', 'contractlength', 'contractdollars', 'contractstatus', 'contractis2way',
                      'contractismultiyear', 'extensionlength', 'extensiondollars', 'extensionis2way'):
                db.set(B, f, r, 0)
        self.teamless = displaced
        # составы НХЛ
        nhl_entries = []
        by_team = defaultdict(list)
        for p in self.players:
            by_team[p['slot']].append(p)
        self.lines_of = {}
        for team in sorted(by_team):
            tp = by_team[team]
            nums = self.numbers(tp)
            letters = self.letters(tp)
            keys, dressed = lines_mod.build([{'key': p['nhl_id'], 'pos': p['pos'], 'ovr': p['_ovr'],
                                              'shoots': p.get('shoots'), 'attrs': p['_attrs']} for p in tp])
            holder = defaultdict(set)
            for slot, k in keys.items():
                holder[k].add(slot)
            self.lines_of[team] = keys
            for p in tp:
                r = self.row_of[p['nhl_id']]
                e = {f: 0 for f in v.entry_fields}
                e.update({'team': team, 'playerindex': pick_link(r, team), 'jersey': nums[p['nhl_id']],
                          'playerstyle': p['_style'], 'rosterstatus': int(p['nhl_id'] in dressed),
                          'captain': letters.get(p['nhl_id'], 0)})
                for slot in holder[p['nhl_id']]:
                    e[slot] = 1
                db.set(B, 'jersey', r, nums[p['nhl_id']])
                nhl_entries.append(e)
                o = self.out[p['nhl_id']]
                o.update({'jersey': nums[p['nhl_id']], 'dressed': int(p['nhl_id'] in dressed),
                          'letter': {1: 'C', 2: 'A'}.get(letters.get(p['nhl_id'], 0)),
                          'slots': sorted(holder[p['nhl_id']])})
        entries = kept + refill + nhl_entries
        per_team = defaultdict(list)
        for e in entries:
            per_team[e['team']].append(e)
        final = []
        for team in sorted(per_team):
            es = sorted(per_team[team], key=lambda e: e['playerindex'])
            if len(es) > MAX_PER_TEAM:
                raise RuntimeError(f'в команде {team} {len(es)} игроков (больше {MAX_PER_TEAM})')
            for k, e in enumerate(es):
                e['key'] = team * MAX_PER_TEAM + k
                final.append(e)
        self.entries, self.fa_keep = final, fa_keep

    # --- 5. запись таблиц ------------------------------------------------------------------
    def write_table_rows(self, table, rows):
        db = self.db
        if db.by_name[table]['rows'] != len(rows):
            db.resize(table, len(rows))
        fields = list(db.by_name[table]['fields'])
        for i, row in enumerate(rows):
            for f in fields:
                db.set(table, f, i, row.get(f, 0))

    def write_links(self):
        if not self.new_links:
            return
        v, db = self.v, self.db
        rows = [{'table': 1 if i in v.link_created else 0, 'index': i, 'playerid': g} for i, g in v.link_gid.items()]
        rows += [{'table': 0, 'index': i, 'playerid': g} for i, g in self.new_links]
        rows.sort(key=lambda x: x['index'])
        self.write_table_rows(P, rows)

    def clean_stats(self):
        """Карьерная статистика прежних владельцев строк-доноров — прочь (строки по game_id)."""
        db = self.db
        gone = {self.v.gid[self.row_of[i]] for i in self.new}
        removed = {}
        for table in STATS:
            t = db.by_name[table]
            raws = [db.record(table, i) for i in range(t['rows'])]
            keep = [raw for i, raw in enumerate(raws) if db.get(table, 'game_id', i) not in gone]
            removed[table] = len(raws) - len(keep)
            if len(keep) != len(raws):
                db.resize(table, len(keep))
                for i, raw in enumerate(keep):
                    db.put_record(table, i, raw)
        return removed

    # --- проверки ----------------------------------------------------------------------------
    def verify(self):
        db = self.db
        v2 = View(db)
        bad = []
        es = v2.entries
        last = None
        cnt = Counter()
        for e in es:
            t = e['team']
            if e['key'] != t * MAX_PER_TEAM + cnt[t]:
                bad.append(f"key {e['key']} у команды {t} не по порядку")
            cnt[t] += 1
            if last is not None and e['key'] <= last:
                bad.append(f"key {e['key']} не по возрастанию")
            last = e['key']
        links = Counter(e['playerindex'] for e in es)
        bad += [f'связь {l} у {n} записей' for l, n in links.items() if n > 1]
        bad += [f"связи {e['playerindex']} нет в exhibitionplayers" for e in es if e['playerindex'] not in v2.link_gid]
        bad += [f'свободный агент {l} в составе' for l in v2.fa if l in links]
        club_of = defaultdict(list)
        for e in es:
            r = v2.row_of_gid.get(v2.link_gid.get(e['playerindex']))
            if r is None:
                bad.append(f"связь {e['playerindex']} → нет игрока")
                continue
            if e['team'] in NHL or e['team'] in CLUBS:
                club_of[r].append(e['team'])
            if v2.is_goalie(r) != (v2.ai(r)[0] == G):
                bad.append(f'{v2.name(r)}: амплуа и таблица атрибутов не совпадают')
        for r, ts in club_of.items():
            if len(ts) > 1:
                bad.append(f'{v2.name(r)} в двух клубах {ts}')
            if v2.g('team', r) != ts[0] + 1:
                bad.append(f"{v2.name(r)}: team {v2.g('team', r)} ≠ клуб {ts[0]} + 1")
        touched = {self.row_of[p['nhl_id']] for p in self.players} | set(self.displaced)
        for r in touched:      # у кого из тронутых команда без записи в клубе (контракт с чужой командой)
            if v2.g('team', r) and r not in club_of:
                bad.append(f"{v2.name(r)}: team {v2.g('team', r)} без записи в клубе")
        for team in NHL:
            te = [e for e in es if e['team'] == team]
            for f in FLAGS:
                n = sum(e[f] for e in te)
                if n != 1:
                    bad.append(f'команда {team}: место {f} у {n} игроков')
            dressed = [e for e in te if any(e[f] for f in FLAGS)]
            if len(dressed) != 20 or any(e['rosterstatus'] != (e in dressed) for e in te):
                bad.append(f'команда {team}: одетых {len(dressed)}, rosterstatus не совпадает')
            caps = Counter(e['captain'] for e in te)
            if not ((caps[1] == 1 and caps[2] == 2) or (caps[1] == 0 and caps[2] == 3)):
                bad.append(f'команда {team}: буквы {dict(caps)}')
            nums = Counter(e['jersey'] for e in te)
            bad += [f'команда {team}: номер {n} у двоих' for n, c in nums.items() if c > 1]
        want = {self.row_of[p['nhl_id']]: p['slot'] for p in self.players}
        for r, team in want.items():
            if club_of.get(r) != [team]:
                bad.append(f'{v2.name(r)}: в составах {club_of.get(r)}, нужен {team}')
        for r, ts in club_of.items():
            if ts[0] in NHL and r not in want:
                bad.append(f'{v2.name(r)} в НХЛ ({ts[0]}), но его нет в составах API')
        crc = db.verify()
        return bad, crc

    # --- всё вместе --------------------------------------------------------------------------
    def run(self):
        v, db = self.v, self.db
        self.plan()
        self.generic_heads()
        self.assign_artids()
        for p in self.players:
            r = self.row_of[p['nhl_id']]
            new = p['nhl_id'] in self.new
            attrs, ovr, style = self.write_ratings(p, r, new)
            p['_attrs'], p['_ovr'], p['_style'] = attrs, ovr, style
            self.write_bio(p, r, new, ovr)
            m = self.mt.get(str(p['nhl_id'])) or {}
            self.out[p['nhl_id']] = {
                'nhl_id': p['nhl_id'], 'name': f"{p['first']} {p['last']}", 'team': p['team'], 'slot': p['slot'],
                'pos': p['pos'], 'row': r, 'game_id': v.gid[r], 'new': new, 'how': m.get('how'),
                'db_name': m.get('db_name'), 'donor': self.donor_info.get(p['nhl_id']),
                'artid': db.get(B, 'artid', r), 'ovr': ovr, 'rating_source': p['rating']['source'],
                'style': style, 'notes': self.notes[p['nhl_id']]}
        self.rebuild_entries()
        self.write_table_rows(R, self.entries)
        self.write_table_rows(F, [{'playerindex': l} for l in self.fa_keep])
        self.write_links()
        removed = self.clean_stats()
        db.fix()
        bad, crc = self.verify()
        return bad, crc, removed


def run(paths, log=print):
    w = Writer(paths, log)
    bad, crc, removed = w.run()
    if crc:
        raise SystemExit(f'CRC не сходятся: {crc[:3]}')
    os.makedirs(os.path.dirname(paths.db_out), exist_ok=True)
    with open(paths.db_out, 'wb') as f:
        f.write(w.db.d)
    if w.meta_path and os.path.dirname(os.path.abspath(w.meta_path)) != os.path.dirname(os.path.abspath(paths.db_out)):
        shutil.copyfile(w.meta_path, os.path.join(os.path.dirname(paths.db_out), 'nhlng-meta.xml'))
    write_json(paths.registry, dict(sorted(w.registry.items(), key=lambda kv: int(kv[0]))))
    summary = {
        'db_in': paths.db_in, 'db_out': paths.db_out, 'players': list(w.out.values()),
        'no_room': [{'nhl_id': p['nhl_id'], 'name': f"{p['first']} {p['last']}", 'team': p['team'], 'pos': p['pos']}
                    for p in w.no_room],
        'events': w.events, 'teamless': [{'row': r, 'name': w.v.name(r), 'birth': list(w.v.birth(r)),
                                          'special': [t for t in w.v.teams_of[r] if t in SPECIAL]} for r in w.teamless],
        'new_links': w.new_links, 'stats_removed': removed, 'problems': bad,
        'lines': {SLOT_TEAM[t]: k for t, k in w.lines_of.items()},
        'rows': {'roster': w.db.by_name[R]['rows'], 'free_agents': w.db.by_name[F]['rows'],
                 'links': w.db.by_name[P]['rows']},
        'model': {'offset': w.model.offset, 'depth': w.model.depth},
    }
    write_json(paths.written, summary)
    n_new = len(w.new)
    log(f'write: {len(w.out)} игроков ({len(w.out) - n_new} сопоставлено, {n_new} в строках доноров, '
        f'без места {len(w.no_room)}); составов {w.db.by_name[R]["rows"]} записей, свободных агентов '
        f'{w.db.by_name[F]["rows"]}, новых связей {len(w.new_links)} -> {paths.db_out}')
    if bad:
        log(f'  проверки: {len(bad)} проблем, первые: {bad[:5]}')
    else:
        log('  проверки: OK')
    return summary
