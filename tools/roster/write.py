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
   амплуа, номер, команда и права (proteam/draftteam — номер + 1; tools/nhl32.py расширяет их до 6 бит),
   драфт, дебют, игры в НХЛ, новичок. Контракт — заглушка по OVR и возрасту (следующий этап).
3. Рейтинги NHL 27 (ratings.py) и стиль.
4. exhibitionrostertable целиком пересобирается: составы 32 клубов НХЛ со звеньями и буквами —
   звенья по реальным сочетаниям (lines.json этапа lines, DailyFaceoff; lines.build_real: тройки,
   пары, вратари, PP, PK как в источнике, пропуски, овертайм, буллиты и лишние — по рейтингу), у
   клуба без них — по рейтингу (lines.build); место каждого ушедшего из клуба АХЛ/Европы/юниоров занимает ушедший из НХЛ игрок
   того же амплуа — с номером, звеньями, буквой и условиями места (контракт, права, юниорский
   клуб) прежнего, так что размеры и звенья этих команд не меняются; key = команда × 40 +
   место, внутри команды — по возрастанию playerindex (как в исходной базе). Ушедшие из НХЛ,
   кому места нет, остаются без клуба и контракта: `team` = 0 (как у 41 игрока исходной базы)
   или, если он есть в сборной/легендах и т. п., эта команда + 1 (как у 309 игроков сборных без
   клуба в исходной базе).
5. exhibitionfreeagents — без занятых игроков; exhibitionplayers — новые связи, если нужны.
Потом — проверки (verify ниже) и пересчёт CRC.
"""
import os
import shutil
import unicodedata
import zlib
from collections import Counter, defaultdict

from tdb import Tdb

from . import lines as lines_mod
from .codes import NONE, country_code, state_code
from .common import SEASON, SEASON_YEAR, SLOT_TEAM, club_abbr, fit_utf8, norm, read_json, team_slot, write_json
from .dbview import (B, CLUBS, F, FLAGS, G, GENERIC_HEAD, LEGACY, LINK_LIMIT, NATIONAL, NHL, P, POS_CODE, POS_NAME, R,
                     S, SPECIAL, View, fld)
from .match import load_db
from .ratings import BASE, SK_BIAS, TRAITS, Model, age, clamp_rating

ART_MIN, ART_MAX = 9803, 16383          # свободные artid: портреты на диске — до p9802, поле — 14 бит
if LEGACY:
    # Legacy: artid 16 бит, у игроков базы — до 12814 (портреты до p12401); портреты ≤ 60000 игра ищет в
    # p8001_12000/ (generalhelpers.big: «push 60000» вместо 12000 у NHL 13), 60000+ — силуэты
    ART_MIN, ART_MAX = 12815, 49999
# «условия» места в клубе: переходят к тому, кто занимает место ушедшего в НХЛ (юниору — без
# контракта, игроку АХЛ — двусторонний контракт с правами клуба НХЛ и т. п.)
SLOT_TERMS = ['proteam', 'contractstatus', 'contractdollars', 'contractlength', 'contractis2way',
              'contractismultiyear', 'contractneedsentrylevel', 'yearufa', 'extensionlength', 'extensiondollars',
              'extensionis2way', 'juniorteam', 'juniorleague', 'junioryearlost']
CONTRACT = ['proteam', 'contractlength', 'contractdollars', 'contractstatus', 'contractis2way', 'contractismultiyear',
            'contractneedsentrylevel', 'extensionlength', 'extensiondollars', 'extensionis2way']
STATS = ['stockcareerseasonplayerstats', 'stockcareerplayoffplayerstats', 'stockcareerseasongoaliestats',
         'stockcareerplayoffgoaliestats']
TIER = {0: 'ушедший из НХЛ', 1: 'свободный агент 2012', 2: 'без команды', 3: 'клуб (АХЛ/Европа/юниоры)',
        4: 'клуб, пересобранный конвейером (--league)'}
MAX_PER_TEAM = 40
# --fa: строки для свободных агентов берутся и у клубов АХЛ/Европы/юниоров 2012 года — только неодетые
# (rosterstatus 0, ни одного места в звеньях) и только сверх CLUB_MIN игроков в клубе, старшие первыми
CLUB_MIN = 22


class Writer:
    def __init__(self, paths, log=print, real_lines=True):
        self.paths, self.log = paths, log
        # реальные сочетания звеньев (этап lines); нет файла или --rating-lines — всё по рейтингу
        self.real = ((read_json(paths.lines) or {}).get('teams') or {}) if real_lines else {}
        self.db, self.meta_path = load_db(paths)
        self.orig = Tdb(bytes(self.db.d), self.db.meta)      # исходные значения (db меняется по ходу)
        self.v = View(self.db)
        data = read_json(paths.players)
        mt = read_json(paths.matched)
        if not data or not mt:
            raise SystemExit('нет players.json или match.json — сначала build и match')
        self.players = data['players']
        self.mt = mt['players']
        self.registry = read_json(paths.registry, {}) or {}
        if not self.registry and os.path.exists(paths.registry_main):
            # своя папка (--work) без таблицы artid: те же номера, что в основной (только чтение)
            self.registry = read_json(paths.registry_main, {}) or {}
            log(f'write: artid новых — по {paths.registry_main}')
        self.model = Model(self.v, self.players)
        self.safe = {ch for r in range(self.v.nbio) for f in ('firstname', 'lastname', 'birthplace')
                     for ch in self.v.s(f, r) if ord(ch) > 127}
        self.notes = defaultdict(list)       # nhl_id -> [что не заполнено / заглушка]
        self.events = []                      # строки отчёта о составах
        self.out = {}                         # nhl_id -> итог по игроку
        self.new_links = []                   # (index, game_id)
        # --fa: свободные агенты (team 'FA', slot None) — связь в exhibitionfreeagents, в составах их нет
        self.fa_players = [p for p in self.players if p.get('fa')]
        self.spare = bool(self.fa_players)    # доноры из клубов — только неодетые сверх CLUB_MIN
        self.skin_on = getattr(paths, 'skin', False)   # --skin: голова под тон кожи на фото (skin.py)
        self.skin_rows, self.skin_info = [], None
        self.payroll_max = getattr(paths, 'payroll_max', None)   # --payroll-max: ведомости под потолок (cap_payroll)
        self.payroll = None

    # --- 1. строки игроков -----------------------------------------------------------------
    def spare_rows(self):
        """Строки игроков клубов АХЛ/Европы/юниоров, которых можно отдать: игрок только в этом клубе, не
        одет и без мест в звеньях, в клубе больше CLUB_MIN игроков; у клуба — старшие первыми."""
        v = self.v
        per = defaultdict(list)
        for e in v.entries:
            per[e['team']].append(e)
        out = set()
        for t, es in per.items():
            if t not in CLUBS or t in self.own_clubs:
                continue
            free = []
            for e in es:
                r = v.row_of_gid.get(v.link_gid.get(e['playerindex']))
                if r is None or v.teams_of[r] != [t] or e['rosterstatus'] or any(e[f] for f in FLAGS):
                    continue
                free.append((v.birth(r), r))
            free.sort()
            out.update(r for _, r in free[:max(0, len(es) - CLUB_MIN)])
        return out

    def donor_candidates(self, taken):
        v = self.v
        out = {'G': [], 'S': []}
        spare = self.spare_rows() if self.spare else None
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
            elif all(t in self.own_clubs for t in teams):
                tier = 4                              # его клуб конвейер пересобирает (--league) — место освобождается
            else:
                tier = 3
                if spare is not None and r not in spare:
                    continue
            out['G' if v.is_goalie(r) else 'S'].append((tier == 3, v.birth(r)[0], tier, r))
        for k in out:
            out[k].sort()
        return out

    def plan(self):
        v = self.v
        self.own_clubs = {p['slot'] for p in self.players if p['slot'] is not None and p['slot'] not in NHL}
        self.row_of, self.new, self.no_room = {}, set(), []
        for p in self.players:
            m = self.mt.get(str(p['nhl_id']))
            if m and m['row'] is not None:
                self.row_of[p['nhl_id']] = m['row']
        cands = self.donor_candidates(set(self.row_of.values()))
        self.donor_info = {}
        for kind in ('G', 'S'):
            need = [p for p in self.players if p['nhl_id'] not in self.row_of and (p['pos'] == 'G') == (kind == 'G')]
            need.sort(key=lambda p: (999 if p['slot'] is None else p['slot'], p['nhl_id']))
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
            if not v.created_slot(r) and v.g('headid', r) >= GENERIC_HEAD:      # 10000+ (Legacy 60000+) — типовые
                heads[(v.g('headid', r), v.g('skincolor', r))] += 1
        skin = Counter()
        for (h, c), n in heads.items():
            skin[c] += n
        usual = skin.most_common(1)[0][0]
        self.heads = sorted(k for k in heads if k[1] == usual)
        self.head_skin = {h: c for h, c in heads}

    # --- тон кожи (--skin) -------------------------------------------------------------------
    MISMATCH_STEPS = 2       # у сопоставленного с типовой головой — замена, если ступень тона по фото дальше

    def prepare_skin(self):
        """Выбор типовой головы по фото: новым — всегда (есть фото), сопоставленным с типовой головой — при
        грубом расхождении (ступень тона по фото дальше MISMATCH_STEPS от головы EA, замер уверенный),
        сканам EA (headid < 10000) — никогда."""
        from . import skin
        v = self.v
        matched_heads = {p['nhl_id']: v.g('headid', self.row_of[p['nhl_id']]) for p in self.players
                         if p['nhl_id'] not in self.new and v.g('headid', self.row_of[p['nhl_id']]) >= GENERIC_HEAD}
        self.skin_model = m = skin.SkinModel(self.paths.game, self.head_skin, self.players, matched_heads, self.log)
        over = skin.load_overrides(self.paths.game)
        self.skin_pick = {}
        counts = Counter()
        for p in self.players:
            pid = p['nhl_id']
            r = self.row_of[pid]
            new = pid in self.new
            ch = m.choose(p)
            cur = v.g('headid', r)
            head, note, kind = None, None, None
            o = over.get(str(pid))
            if o:
                if o.get('head') in self.head_skin:
                    head = o['head']
                elif o.get('skin') in set(self.head_skin.values()):
                    pool = sorted(h for h, c in self.head_skin.items() if c == o['skin'] and h in m.icon and m.icon[h])
                    if ch:
                        pool.sort(key=lambda h: (abs(m.icon[h]['ita'] - ch['target']), h))
                        pool = pool[:5]
                    head = pool[zlib.crc32(f"{p['first']} {p['last']}".encode()) % len(pool)] if pool else None
                if head:
                    note = f"поправка: {o.get('note') or o}"
                    kind = 'override'
                    counts['ручная поправка'] += 1
            if head is None and ch:
                if new:
                    head = ch['head']
                    counts['новый: по фото' + (' (проверить)' if ch['unsure'] else '')] += 1
                elif (cur in self.head_skin and not ch['unsure']
                      and abs(m.step_of_class(self.head_skin[cur]) - ch['step']) > self.MISMATCH_STEPS):
                    head = ch['head']
                    note = f"в базе голова {cur} (тон {self.head_skin[cur]}), по фото тон {ch['skin']} — заменена"
                    kind = 'replaced'
                    counts['в базе: голова заменена'] += 1
                else:
                    counts['в базе: своя голова' if cur < GENERIC_HEAD else 'в базе: голова оставлена'] += 1
            elif head is None:
                counts['новый: нет фото — по умолчанию' if new else 'в базе: нет фото'] += 1
            if head is not None:
                self.skin_pick[pid] = head
            final = head if head is not None else (None if new else cur)
            self.skin_rows.append({'nhl_id': pid, 'name': f"{p['first']} {p['last']}", 'team': p['team'], 'new': new,
                                   'choice': ch, 'final_head': final, 'final_skin': None, 'note': note, 'kind': kind,
                                   'scan': not new and cur < GENERIC_HEAD and head is None})
        self.skin_info = dict(m.summary(), counts=dict(counts))

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
        bio = db.by_name[B]['fields']       # у Legacy нет junioryearlost и waiversneedreentry — пропускаются
        put = lambda f, x: db.set(B, f, r, x) if f in bio else None
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
        put('team', 0 if p.get('fa') else p['slot'] + 1)
        if p.get('fa') or p.get('league'):
            put('proteam', 0)                # свободный агент / клуб лиги: прав клуба НХЛ нет
        elif p.get('ahl'):
            # клуб АХЛ: права — у клуба-хозяина, если контракт с ним (иначе контракт с клубом АХЛ — 0)
            put('proteam', team_slot(p['ahl']['parent']) + 1 if p['ahl']['nhl_contract'] else 0)
        elif p['slot'] + 1 < 1 << db.by_name[B]['fields']['proteam'][1]:
            put('proteam', p['slot'] + 1)
        else:
            put('proteam', 0)
            notes.append('proteam = 0 (номер команды не влезает в поле; tools/nhl32.py расширяет до 6 бит)')
        dr = p.get('draft')
        if dr and dr.get('year'):
            put('draftyear', dr['year'] - 1900)
            put('draftround', min(15, dr.get('round') or 0))
            put('draftposition', min(511, dr.get('overall') or 0))
            ds = team_slot(dr.get('team'))
            if ds is None:
                put('draftteam', 0)
                notes.append(f"draftteam = 0 (клуб драфта {dr.get('team')} не найден)")
            elif ds + 1 >= 1 << db.by_name[B]['fields']['draftteam'][1]:
                put('draftteam', 0)
                notes.append('draftteam = 0 (номер команды не влезает в поле; tools/nhl32.py расширяет до 6 бит)')
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
        if LEGACY:
            # новые поля Legacy: новичок АХЛ/CHL, сделки с удержанием зарплаты — у игроков НХЛ базы 0
            for f in ('rookieahl', 'rookiechl', 'retainedsalarytrades'):
                put(f, 0)
        if p.get('fa'):
            # как у 183 свободных агентов исходной базы: контракта нет, yearufa — нынешний год
            for f in CONTRACT + ['contractneedsentrylevel', 'contractismultiyear']:
                put(f, 0)
            put('yearufa', SEASON_YEAR - 1900)
            put('jersey', min(127, p.get('num') or 0))
        elif p.get('league'):
            # клуб европейской лиги: как у игроков Европы исходной базы — контракта НХЛ нет
            for f in CONTRACT + ['contractneedsentrylevel', 'contractismultiyear']:
                put(f, 0)
        if not p['landing']:
            notes.append('нет карточки landing: драфт и игры по сезонам не заполнены')
        if p.get('omitted'):
            notes.append('нет в /roster/current (вероятно, травмирован)')
        if new:
            put('artid', self.artid[p['nhl_id']])
            put('audioid', 0)
            put('hasportrait', 0)
            head, skin = self.heads[zlib.crc32(f"{p['first']} {p['last']}".encode()) % len(self.heads)]
            if self.skin_on and p['nhl_id'] in self.skin_pick:      # --skin: голова под тон кожи на фото
                head = self.skin_pick[p['nhl_id']]
                skin = self.head_skin[head]
            put('headid', head)
            put('skincolor', skin)
        elif self.skin_on and p['nhl_id'] in self.skin_pick:          # сопоставленный: грубое расхождение тона
            put('headid', self.skin_pick[p['nhl_id']])
            put('skincolor', self.head_skin[self.skin_pick[p['nhl_id']]])

    # --- 3. рейтинги -----------------------------------------------------------------------
    def write_ratings(self, p, r, new):
        db, v, m = self.db, self.v, self.model
        t, row = v.ai(r)
        style = m.style(p, r, new)
        attrs, ovr = m.attributes(p, r, new, style)
        for f, x in attrs.items():
            db.set(t, fld(f), row, x - BASE)
        pot = m.potential(p)
        if t == S:
            old_style = db.get(S, fld('p_style'), row)
            db.set(S, fld('p_overall'), row, clamp_rating(ovr) - BASE)
            db.set(S, fld('p_style'), row, style)
            if new or style != old_style:
                for f in SK_BIAS:
                    if f in m.bias.get(style, {}):
                        db.set(S, fld(f), row, m.bias[style][f])
            db.set(S, fld('p_potential'), row, pot)
        else:
            db.set(G, fld('g_overall'), row, clamp_rating(ovr) - BASE)
            db.set(G, fld('g_style'), row, style)
            db.set(G, fld('g_potential'), row, pot)
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
        src = p['rating']['source']
        if src == 'none':
            self.notes[p['nhl_id']].append(f'рейтинга нет — оценка OVR {ovr}')
        elif src in ('nhlratings-ovr', 'ea-ovr'):
            self.notes[p['nhl_id']].append('атрибуты достроены из OVR')
        elif src == 'stats':             # --stats-ratings
            self.notes[p['nhl_id']].append(f"OVR по статистике — {ovr} (прежняя оценка {p['rating_before']['ovr']})")
        elif src.endswith('+stats'):
            self.notes[p['nhl_id']].append(f"OVR NHL 27 смешан со статистикой — {p['rating_before']['ovr']} → {ovr}; "
                                           'атрибуты достроены из OVR')
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

    def team_lines(self, team, tp):
        """Звенья клуба: по реальным сочетаниям (lines.json), если источник дал хотя бы
        lines.MIN_REAL игроков клуба в тройки, пары и ворота, иначе по рейтингу."""
        abbr = club_abbr(team)
        lp = [{'key': p['nhl_id'], 'pos': p['pos'], 'ovr': p['_ovr'], 'shoots': p.get('shoots'), 'attrs': p['_attrs'],
               'out': bool(p.get('omitted'))} for p in tp]
        src = self.real.get(abbr)
        info = {'source': 'rating'}
        if src:
            real = {k: src.get(k) or [] for k in ('f', 'd', 'g', 'pp', 'pk', 'extra_d')}
            real['injured'] = [i['nhl_id'] for i in src.get('injured') or [] if i.get('nhl_id')]
            n = lines_mod.real_count(lp, real)
            if n >= lines_mod.MIN_REAL:
                keys, dressed, how = lines_mod.build_real(lp, real)
                name = {p['nhl_id']: f"{p['first']} {p['last']}" for p in tp}
                info = {'source': 'dailyfaceoff', 'updated': src.get('updated'), 'by': src.get('source'),
                        'url': src.get('source_url'), 'from_source': n,
                        'filled': [{'slot': s, 'nhl_id': k, 'name': name[k]} for s, k in how['filled']],
                        'dropped': [{'nhl_id': k, 'name': name[k], 'where': w, 'why': why} for k, w, why in how['dropped']]}
                self.lines_info[abbr] = info
                return keys, dressed
            info = {'source': 'rating', 'why': f'источник дал {n} игроков клуба в тройки, пары и ворота '
                                               f'(нужно {lines_mod.MIN_REAL})'}
            self.log(f"  {abbr}: звенья по рейтингу — {info['why']}")
        self.lines_info[abbr] = info
        return lines_mod.build(lp)

    def rebuild_entries(self):
        v, db = self.v, self.db
        new_rows = set(self.p_of_row)
        donors = {self.row_of[i] for i in self.new}
        link_team = {e['playerindex']: e['team'] for e in v.entries}
        row_of_link = lambda l: v.row_of_gid.get(v.link_gid.get(l))
        kept, vacancies = [], []
        for e in v.entries:
            t, r = e['team'], row_of_link(e['playerindex'])
            if t in NHL or t in self.own_clubs:       # составы НХЛ и клубов конвейера — заново ниже
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
            if (e['team'] in NHL or e['team'] in self.own_clubs) and r not in new_rows and r not in displaced:
                displaced.append(r)
        self.displaced = list(displaced)
        # места ушедших в НХЛ из клубов АХЛ/Европы/юниоров — ушедшим из НХЛ того же амплуа
        refill = []
        orig_name = lambda r: f"{self.orig.get_string(B, 'firstname', r)} {self.orig.get_string(B, 'lastname', r)}"
        for e in sorted(vacancies, key=lambda e: (e['team'], e['playerindex'])):
            r_old = row_of_link(e['playerindex'])
            pos = self.orig.get(B, 'position', r_old)      # амплуа того, кто занимал место (до правок)
            same_kind = [r for r in displaced if v.is_goalie(r) == (pos == 4)
                         and (v.g('position', r) == 3) == (pos == 3)]
            if not same_kind:
                same_kind = [r for r in displaced if v.is_goalie(r) == (pos == 4)]
            if not same_kind:
                self.events.append({'team': e['team'], 'what': 'место осталось пустым', 'player': orig_name(r_old)})
                continue
            same_kind.sort(key=lambda r: (v.g('position', r) != pos, -v.birth(r)[0], r))
            r = same_kind[0]
            displaced.remove(r)
            ne = dict(e)
            ne['playerindex'] = pick_link(r, e['team'])
            t_ai, row_ai = v.ai(r)
            ne['playerstyle'] = db.get(t_ai, fld('p_style' if t_ai == S else 'g_style'), row_ai)
            refill.append(ne)
            db.set(B, 'team', r, e['team'] + 1)
            db.set(B, 'jersey', r, e['jersey'])
            for f in (f for f in SLOT_TERMS if f in db.by_name[B]['fields']):   # условия места — как у ушедшего
                db.set(B, f, r, self.orig.get(B, f, r_old))
            self.events.append({'team': e['team'], 'what': 'место ушедшего в НХЛ', 'player': v.name(r),
                                'instead': orig_name(r_old)})
        # остальные ушедшие из НХЛ — без клуба и контракта. Как в исходной базе: у игрока без клуба,
        # но в сборной (легендах и т. п.), `team` = эта команда + 1, у совсем без команды — 0
        for r in displaced:
            special = sorted(t for t in v.teams_of[r] if t in SPECIAL)
            nat = [t for t in special if t in NATIONAL]
            db.set(B, 'team', r, (nat or special)[0] + 1 if special else 0)
            for f in CONTRACT:
                db.set(B, f, r, 0)
        self.teamless = displaced
        # составы НХЛ
        nhl_entries = []
        by_team = defaultdict(list)
        for p in self.players:
            if p['slot'] is not None:
                by_team[p['slot']].append(p)
        self.lines_of, self.lines_info = {}, {}
        for team in sorted(by_team):
            tp = by_team[team]
            nums = self.numbers(tp)
            letters = self.letters(tp)
            keys, dressed = self.team_lines(team, tp)
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
        # свободные агенты (--fa): своя связь — в exhibitionfreeagents
        self.fa_links = {}
        for p in self.fa_players:
            r = self.row_of[p['nhl_id']]
            self.fa_links[p['nhl_id']] = pick_link(r, None)
            self.out[p['nhl_id']].update({'jersey': v.g('jersey', r), 'dressed': 0, 'letter': None, 'slots': [],
                                          'fa_link': self.fa_links[p['nhl_id']]})
        fa_keep = sorted(fa_keep + list(self.fa_links.values()))
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

    def clear_salary_extras(self):
        """Legacy: stockteamsalaryextras — «мёртвые» деньги (выкупы) и удержанные зарплаты клубов 2015/16
        на 25 лет вперёд; к 2026/27 их нет, своих данных у конвейера нет — обнуляются (index остаётся)."""
        t = 'stockteamsalaryextras'
        if t not in self.db.by_name:
            return 0
        n = 0
        for r in range(self.db.by_name[t]['rows']):
            for f in self.db.by_name[t]['fields']:
                if f != 'index' and self.db.get(t, f, r):
                    self.db.set(t, f, r, 0)
                    n += 1
        return n

    def cap_payroll(self, max_mln, min_salary=850_000):
        """--payroll-max: контракт у нас — заглушка по OVR (contract), и ведомости клубов НХЛ выходят 94–135 млн
        при потолке 2026/27 в 104 млн. NHL Legacy с начала 2-го сезона поднимает потолок до самой дорогой ведомости,
        а клуб игрока сверх потолка дальше не пускает. Если ведомость состава клуба (exhibitionrostertable) больше
        max_mln, все контракты клуба (по proteam) выше минималки умножаются на один коэффициент. Минималка
        (min_salary, 2026/27 — 850 тыс.) остаётся минималкой. Коэффициент — наибольший, при котором ведомость
        ≤ max_mln. Настоящие кэп-хиты — этап контрактов (CapWages, docs/research-data-sources.md)."""
        db, unit = self.db, 5000
        low, limit = min_salary // unit, int(max_mln * 1e6 // unit)
        row_of = {g: r for r, g in enumerate(db.column(B, 'game_id'))}
        link = dict(zip(db.column(P, 'index'), db.column(P, 'playerid')))
        roster = defaultdict(list)
        for e in range(db.by_name[R]['rows']):
            t = db.get(R, 'team', e)
            b = row_of.get(link.get(db.get(R, 'playerindex', e)))
            if t in NHL and b is not None:
                roster[t].append(b)
        pay = {r: db.get(B, 'contractdollars', r) for r in range(db.by_name[B]['rows'])}
        org = defaultdict(list)
        for r, x in pay.items():
            t = db.get(B, 'proteam', r) - 1
            if t in roster and x > low:
                org[t].append(r)
        out = {}
        for t in sorted(roster):
            scaled = lambda k: {r: max(low, round(pay[r] * k)) for r in org[t]}
            total = lambda new: sum(new.get(r, pay[r]) for r in roster[t])
            before = total({})
            if before <= limit:
                continue
            lo, hi = 0.0, 1.0
            for _ in range(40):
                mid = (lo + hi) / 2
                lo, hi = (mid, hi) if total(scaled(mid)) <= limit else (lo, mid)
            new = scaled(lo)
            for r, x in new.items():
                db.set(B, 'contractdollars', r, x)
            out[club_abbr(t)] = {'before': round(before * unit / 1e6, 2), 'after': round(total(new) * unit / 1e6, 2),
                                 'k': round(lo, 4), 'contracts': len(new)}
        return out

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
        for r in touched:      # команда в био — клуб игрока, а без клуба — его особая команда или 0
            team = v2.g('team', r)
            if team and r not in club_of and team - 1 not in v2.teams_of[r]:
                bad.append(f"{v2.name(r)}: team {team} — команды нет среди его записей")
        # клубы НХЛ и заполненные конвейером клубы АХЛ (--ahl32): 71 место, 20 одетых, буквы, номера
        own = list(NHL) + sorted(self.own_clubs)
        for team in own:
            te = [e for e in es if e['team'] == team]
            for f in FLAGS:
                n = sum(e[f] for e in te)
                if n != 1:
                    bad.append(f'команда {team}: место {f} у {n} игроков')
            # амплуа по местам: вратари — только g1/g2; у звеньев из источника — как в исходной базе
            strict = (self.lines_info.get(club_abbr(team)) or {}).get('source', 'rating') != 'rating'
            for f in FLAGS:
                for e in (e for e in te if e[f]):
                    r = v2.row_of_gid.get(v2.link_gid.get(e['playerindex']))
                    if r is None:
                        continue
                    pos = POS_NAME[v2.g('position', r)]
                    kind = lines_mod.slot_kind(f)
                    got = 'G' if pos == 'G' else 'D' if pos == 'D' else 'F'
                    if (kind == 'G') != (got == 'G') or (strict and kind not in (None, 'G') and kind != got):
                        bad.append(f'команда {team}: на месте {f} {v2.name(r)} ({pos})')
            dressed = [e for e in te if any(e[f] for f in FLAGS)]
            if len(dressed) != 20 or any(e['rosterstatus'] != (e in dressed) for e in te):
                bad.append(f'команда {team}: одетых {len(dressed)}, rosterstatus не совпадает')
            caps = Counter(e['captain'] for e in te)
            if not ((caps[1] == 1 and caps[2] == 2) or (caps[1] == 0 and caps[2] == 3)):
                bad.append(f'команда {team}: буквы {dict(caps)}')
            nums = Counter(e['jersey'] for e in te)
            bad += [f'команда {team}: номер {n} у двоих' for n, c in nums.items() if c > 1]
        fa_set = set(v2.fa)
        for p in self.fa_players:
            r = self.row_of[p['nhl_id']]
            if club_of.get(r):
                bad.append(f'свободный агент {v2.name(r)} в составе {club_of[r]}')
            if self.fa_links.get(p['nhl_id']) not in fa_set:
                bad.append(f'свободного агента {v2.name(r)} нет в exhibitionfreeagents')
            if v2.g('team', r) != 0 or v2.g('contractstatus', r) != 0:
                bad.append(f"свободный агент {v2.name(r)}: team {v2.g('team', r)}, contractstatus {v2.g('contractstatus', r)}")
        want = {self.row_of[p['nhl_id']]: p['slot'] for p in self.players if p['slot'] is not None}
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
        if self.skin_on:
            self.prepare_skin()
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
        if self.skin_on:
            for row in self.skin_rows:
                r = self.row_of[row['nhl_id']]
                row['final_head'], row['final_skin'] = v.g('headid', r), v.g('skincolor', r)
        self.rebuild_entries()
        self.write_table_rows(R, self.entries)
        self.write_table_rows(F, [{'playerindex': l} for l in self.fa_keep])
        self.write_links()
        if self.payroll_max:
            self.payroll = self.cap_payroll(self.payroll_max)
        removed = self.clean_stats()
        if LEGACY:
            removed['stockteamsalaryextras (обнулено значений)'] = self.clear_salary_extras()
        db.fix()
        bad, crc = self.verify()
        return bad, crc, removed


def run(paths, log=print, real_lines=True):
    w = Writer(paths, log, real_lines)
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
        'lines': {club_abbr(t): k for t, k in w.lines_of.items()},
        'lines_info': w.lines_info,
        'rows': {'roster': w.db.by_name[R]['rows'], 'free_agents': w.db.by_name[F]['rows'],
                 'links': w.db.by_name[P]['rows']},
        'model': {'offset': w.model.offset, 'depth': w.model.depth},
    }
    if w.skin_on:
        from . import skin
        summary['skin'] = w.skin_info
        summary['skin_players'] = [{k: r[k] for k in ('nhl_id', 'name', 'team', 'new', 'final_head', 'final_skin', 'note', 'kind')}
                                   | {'unsure': bool((r['choice'] or {}).get('unsure')),
                                      'photo_ita': (r['choice'] or {}).get('photo_ita'),
                                      'norm': (r['choice'] or {}).get('norm')} for r in w.skin_rows]
        sheet_path = os.path.join(paths.work, 'skin-sheet.html')
        skin.sheet(sheet_path, paths.game, [r for r in w.skin_rows if not r['scan']], w.skin_info)
        log(f"  тон кожи: {w.skin_info['counts']} -> {sheet_path}")
    if w.payroll is not None:
        summary['payroll'] = {'max_mln': w.payroll_max, 'clubs': w.payroll}
        log(f'  ведомости ≤ {w.payroll_max:g} млн: ужато клубов {len(w.payroll)} — '
            + ', '.join(f"{a} {c['before']:.1f}→{c['after']:.1f}" for a, c in w.payroll.items()))
    write_json(paths.written, summary)
    n_new = len(w.new)
    log(f'write: {len(w.out)} игроков ({len(w.out) - n_new} сопоставлено, {n_new} в строках доноров, '
        f'без места {len(w.no_room)}); составов {w.db.by_name[R]["rows"]} записей, свободных агентов '
        f'{w.db.by_name[F]["rows"]}, новых связей {len(w.new_links)} -> {paths.db_out}')
    real = [a for a, i in w.lines_info.items() if i['source'] != 'rating']
    log(f'  звенья: по реальным сочетаниям {len(real)} клубов (достроено мест '
        f"{sum(len(w.lines_info[a]['filled']) for a in real)}), по рейтингу {len(w.lines_info) - len(real)}")
    if bad:
        log(f'  проверки: {len(bad)} проблем, первые: {bad[:5]}')
    else:
        log('  проверки: OK')
    return summary
