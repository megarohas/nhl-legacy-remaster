"""Новые игроки (и правка уже добавленных) в базе NHL Legacy по спекам JSON — этап build-all «players».

    python tools/legacy_data/add_players.py example                      # образец спеки (add_players.example.json)
    python tools/legacy_data/add_players.py db БАЗА.db [СПЕКА.json | ПАПКА …] [--dry-run] [--report ОТЧЁТ.json]

Без спек — все *.json из game/work/legacy-data/add-players/ (другая папка — ADD_PLAYERS_DIR). Описание полей, порядок
и проверка в игре — docs/add-players.md. Кратко, что делается с каждым игроком спеки:
- **строка**: игрок с тем же именем и датой рождения уже есть — правится он (повторный запуск ничего не меняет); иначе
  берётся строка «донора»: игрок без клуба (не в составах, не в пуле свободных агентов, не в сборных, легендах и т. п.),
  старшие первыми; у вратаря — вратарь. У донора стираются имя, портрет, голос комментатора, черты и карьерная
  статистика; artid — свободный, голова — типовая (или из спеки);
- **биография и контракт** — как у конвейера составов (roster/write.py Writer.write_bio): имя, дата и место рождения,
  гражданство, рост, вес, хват, амплуа, драфт, игры в НХЛ, новичок; контракт — из спеки или заглушка по OVR и возрасту;
- **атрибуты** — под OVR, который покажет игра (roster/ovrformula.py, формула worth2.brk): указанные в спеке атрибуты
  как есть, остальные — форма игроков составов НХЛ его амплуа и стиля, сдвинутая до OVR; без OVR, но со всеми
  атрибутами — OVR из формулы;
- **клуб**: запись exhibitionrostertable в конце состава клуба (номер — из спеки, занят — ближайший свободный), «FA» —
  пул свободных агентов; звенья — `lines`: нет — в запасе (не одет), `{"replace": "Имя Фамилия"}` — места в звеньях,
  спецбригадах и «одет» того игрока (тот — в запас), `"rating"` — звенья клуба заново по рейтингу (lines.build);
- **портрет** — `photo`: PNG с прозрачным фоном (портрет NHL 336×336 — как есть, другой размер — по макушке и центру
  головы) → оба портрета игры в <набор>/fe/…/p<artid>.big, hasportrait = 1.

Проверки после записи: CRC, key подряд, связи без повторов, team = клуб записи, у затронутых клубов места звеньев и
одетые — как были (кроме "rating"), новых повторов номеров нет, записей ≤ 40, OVR игры = цель. Ошибка — база не пишется.
Только NHL Legacy (база tools/nhl32.py --game legacy). Сейвы игры не трогает: новый игрок появится в новой франшизе с
составов базы, а не в уже сохранённом ROSTER (docs/add-players.md).
"""
import json
import os
import sys
import zlib
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
ROOT = os.path.dirname(TOOLS)
sys.path.insert(0, TOOLS)
os.environ['NHL_GAME'] = 'legacy'
from roster.common import set_game  # noqa: E402
set_game('legacy')                     # до импорта модулей конвейера: dbview берёт поля игры при импорте
from roster import lines as lines_mod  # noqa: E402
from roster import ovrformula  # noqa: E402
from roster import write as W  # noqa: E402
from roster.ahl2026_write import AhlWriter  # noqa: E402
from roster.codes import COUNTRY  # noqa: E402
from roster.common import SEASON, SEASON_YEAR, TEAM_SLOT, norm, team_slot  # noqa: E402
from roster.dbview import (B, CLUBS, F, FLAGS, G, GENERIC_HEAD, LINK_LIMIT, NHL, POS_NAME, R, S, SPECIAL, T,  # noqa: E402
                           View, fld)
from roster.ratings import BASE, GK, SK, age, cls  # noqa: E402
from tdb import Tdb, load_meta  # noqa: E402

WORK = os.environ.get('LEGACY_DATA_WORK') or os.path.join(ROOT, 'game', 'work', 'legacy-data')
SPEC_DIR = os.environ.get('ADD_PLAYERS_DIR') or os.path.join(WORK, 'add-players')
EXAMPLE = os.path.join(HERE, 'add_players.example.json')
POS_IN = {'C': 'C', 'L': 'L', 'LW': 'L', 'R': 'R', 'RW': 'R', 'D': 'D', 'LD': 'D', 'RD': 'D', 'G': 'G'}
# стили (шкала сверена по базе, roster/ratings.py Model.style): полевые 1–10, вратари 0–2
STYLES = {'D': {'defensive': 1, 'offensive': 2, 'enforcer': 3, 'two-way': 4},
          'F': {'grinder': 5, 'playmaker': 6, 'sniper': 7, 'power': 8, 'two-way': 9, 'enforcer': 10},
          'G': {'standup': 0, 'butterfly': 1, 'hybrid': 2}}
ROSTER_MAX = W.MAX_PER_TEAM            # 40 записей на команду (key = команда × 40 + место)
_CONTRACT = set(W.CONTRACT) | {'contractneedsentrylevel', 'contractismultiyear', 'yearufa', 'yearfirstsigned',
                               'yearwaivereligible'}
# правка игрока, который уже есть в базе: поле спеки → поля exhibitionplayerbiotable, которые оно меняет (прочие — как были)
SPEC_FIELDS = {
    'birth_city': {'birthplace'}, 'birth_country': {'state', 'intlcountry'}, 'birth_state': {'state'},
    'nationality': {'intlcountry'}, 'height': {'height'}, 'height_cm': {'height'}, 'weight_lb': {'weight'},
    'weight_kg': {'weight'}, 'shoots': {'handedness'}, 'pos': {'position'},
    'team': {'team', 'proteam'}, 'rights': {'proteam'},
    'draft': {'draftyear', 'draftround', 'draftposition', 'draftteam'},
    'nhl_gp': {'nhlgamesplayedcareer', 'progamesplayedcareer', 'rookie'}, 'pro_gp': {'progamesplayedcareer'},
    'gp_last_season': {'nhlgamesplayedlastseason'}, 'debut': {'yearprodebut'}, 'rookie': {'rookie'},
    'contract': _CONTRACT, 'head': {'headid', 'skincolor'}, 'photo': {'hasportrait'}, 'number': {'jersey'},
}


class SpecError(ValueError):
    pass


# --- спеки -----------------------------------------------------------------------------------------------------------
def load_specs(args):
    """[(файл, спека)] из файлов и папок (*.json по алфавиту); без аргументов — SPEC_DIR."""
    paths = args or ([SPEC_DIR] if os.path.isdir(SPEC_DIR) else [])
    files = []
    for a in paths:
        if os.path.isdir(a):
            files += [os.path.join(a, f) for f in sorted(os.listdir(a)) if f.endswith('.json') and not f.startswith('_')]
        elif os.path.isfile(a):
            files.append(a)
        else:
            raise SpecError(f'нет файла или папки {a}')
    out = []
    for f in files:
        try:
            data = json.load(open(f, encoding='utf-8'))
        except json.JSONDecodeError as e:
            raise SpecError(f'{f}: не JSON ({e})')
        items = data.get('players', data) if isinstance(data, dict) else data
        for s in items if isinstance(items, list) else [items]:
            out.append((f, s))
    return out


def _num(x, what):
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        raise SpecError(f'{what}: нужно число, а не «{x}»')
    return x


def _date(s, what):
    try:
        y, m, d = (int(x) for x in str(s).split('-'))
        assert 1900 < y < 2100 and 1 <= m <= 12 and 1 <= d <= 31
        return y, m, d
    except (ValueError, AssertionError):
        raise SpecError(f'{what}: дата ГГГГ-ММ-ДД, а не «{s}»')


def _height_in(s):
    if 'height_cm' in s:
        return round(_num(s['height_cm'], 'height_cm') / 2.54)
    h = s.get('height')
    if h is None:
        return None
    if isinstance(h, str) and '-' in h:                        # «6-2», как на NHL.com
        ft, inch = h.split('-')
        return int(ft) * 12 + int(inch)
    return int(_num(h, 'height (дюймы)'))


def _weight_lb(s):
    if 'weight_kg' in s:
        return round(_num(s['weight_kg'], 'weight_kg') * 2.2046)
    return int(_num(s['weight_lb'], 'weight_lb')) if 'weight_lb' in s else None


def _country(code, what):
    if code is None:
        return None
    c = str(code).upper()
    if c not in COUNTRY:
        raise SpecError(f'{what}: страна — код ISO-3, как в API НХЛ (CAN, USA, SWE, RUS…), а не «{code}»')
    return c


def attr_names(pos):
    """{короткое имя: поле конвейера}: speed → p_speed (у вратаря gsh → g_gsh); в базе Legacy — c_*."""
    return {f[2:]: f for f in (GK if pos == 'G' else SK)}


def to_player(s, idx, src):
    """Спека → игрок в формате players.json конвейера (то, что читают Writer.write_bio и ratings.Model)."""
    who = f"{src}: игрок {idx + 1}"
    for k in ('first', 'last', 'birth', 'pos'):
        if not s.get(k):
            raise SpecError(f'{who}: нет поля {k}')
    who = f"{src}: {s['first']} {s['last']}"
    pos = POS_IN.get(str(s['pos']).upper())
    if not pos:
        raise SpecError(f"{who}: pos — C, LW, RW, D или G, а не «{s['pos']}»")
    birth = _date(s['birth'], f'{who}: birth')
    names = attr_names(pos)
    attrs = {}
    for k, x in (s.get('attributes') or {}).items():
        key = k.lower()
        key = key[2:] if key[:2] in ('p_', 'g_', 'c_') else key
        if key not in names:
            raise SpecError(f'{who}: атрибута «{k}» нет у {"вратаря" if pos == "G" else "полевого"}; есть: '
                            + ', '.join(sorted(names)))
        if not BASE <= _num(x, f'{who}: {k}') <= BASE + 63:
            raise SpecError(f'{who}: {k} = {x}, шкала {BASE}–{BASE + 63}')
        attrs[names[key]] = int(x)
    c = cls(pos)
    ovr = s.get('ovr')
    if ovr is None and len(attrs) == len(names):
        ovr = ovrformula.game_ovr(c, attrs)
    if ovr is not None and not 40 <= _num(ovr, f'{who}: ovr') <= 99:
        raise SpecError(f'{who}: ovr {ovr} вне 40–99')            # нет ovr: новому — ошибка, у правки — OVR игры
    style = s.get('style')
    kind = 'G' if pos == 'G' else 'D' if pos == 'D' else 'F'
    if isinstance(style, str):
        if style.lower() not in STYLES[kind]:
            raise SpecError(f'{who}: style «{style}» — у {kind} есть {", ".join(STYLES[kind])}')
        style = STYLES[kind][style.lower()]
    elif style is not None and style not in STYLES[kind].values():
        raise SpecError(f'{who}: style {style} — у {kind} {sorted(STYLES[kind].values())}')
    team = str(s['team']) if s.get('team') else None            # нет: новый — FA, у правки — клуб как был
    dr = s.get('draft') or {}
    if dr and not dr.get('year'):
        raise SpecError(f'{who}: у draft нужен year')
    gp = int(s.get('nhl_gp') or 0)
    debut = int(_num(s['debut'], f'{who}: debut (год)')) if s.get('debut') else None
    by_season = {}
    if s.get('gp_last_season'):
        by_season[str(SEASON - 10001)] = int(s['gp_last_season'])
    p = {
        'nhl_id': zlib.crc32(f"{norm(s['first'] + s['last'])}|{birth}".encode()),
        'first': s['first'], 'last': s['last'], 'birth': birth, 'pos': pos, 'shoots': (s.get('shoots') or '').upper()[:1],
        'birth_city': s.get('birth_city'), 'birth_country': _country(s.get('birth_country'), f'{who}: birth_country'),
        'birth_state': s.get('birth_state'),
        'nationality': _country(s.get('nationality') or s.get('birth_country'), f'{who}: nationality'),
        'height_in': _height_in(s), 'weight_lb': _weight_lb(s), 'num': s.get('number'),
        'draft': {'year': dr.get('year'), 'round': dr.get('round'), 'overall': dr.get('overall'), 'team': dr.get('team')}
                 if dr else None,
        'nhl_gp': {'career': gp, 'debut': f'{debut}{debut + 1}' if debut else None, 'by_season': by_season},
        'pro_gp': int(s.get('pro_gp') or gp),
        'rookie': bool(s['rookie']) if 'rookie' in s else gp < 25 and age(birth) <= 26,
        'rating': {'source': 'spec', 'ovr': ovr, 'attrs': attrs, 'style': style},
        'landing': True, 'omitted': False, 'ea': None,
        '_spec': s, '_src': src, '_team_in': team, '_lines': s.get('lines'), '_contract': s.get('contract'),
        '_head': s.get('head'), '_photo': s.get('photo'),
    }
    if p['_photo'] and not os.path.isabs(p['_photo']):
        p['_photo'] = os.path.join(os.path.dirname(os.path.abspath(src)), p['_photo'])
    if p['_photo'] and not os.path.isfile(p['_photo']):
        raise SpecError(f"{who}: нет файла фото {p['_photo']}")
    return p


def resolve_team(db, p):
    """Клуб спеки → строка exhibitionteams (None — свободный агент); права НХЛ у клуба не из НХЛ — rights."""
    t = p['_team_in']
    who = f"{p['first']} {p['last']}"
    if t is None or t.upper() == 'FA':
        p.update(fa=True, slot=None, team='FA', _team_default=t is None)
        return None
    slot = team_slot(t)
    if slot is None:
        want = norm(t)
        for row in range(db.by_name[T]['rows']):
            if want in {norm(db.get_string(T, f, row)) for f in ('abbrname', 'shortname', 'fullname')}:
                slot = row
                break
        if slot is None and t.isdigit():
            slot = int(t)
    if slot is None or not 0 <= slot < db.by_name[T]['rows']:
        raise SpecError(f'{who}: клуба «{t}» нет (аббревиатура НХЛ, название из exhibitionteams, номер строки или FA)')
    if slot in SPECIAL:
        raise SpecError(f'{who}: {t} — особая команда (сборная, легенды, Матч звёзд…): туда этот инструмент не ставит')
    if slot not in NHL and slot not in CLUBS:
        raise SpecError(f'{who}: строка {slot} — не клуб')
    p.update(slot=slot, team=t.upper() if slot in NHL else db.get_string(T, 'abbrname', slot) or t)
    rights = p['_spec'].get('rights')
    if slot not in NHL:
        if rights:
            if team_slot(rights) is None:
                raise SpecError(f'{who}: rights — клуб НХЛ (аббревиатура), а не «{rights}»')
            p['ahl'] = {'parent': rights.upper(), 'nhl_contract': True}
        else:
            p['league'] = {'level': p['rating']['ovr']}       # клуб без прав НХЛ: proteam 0, контракта НХЛ нет
    return slot


# --- запись --------------------------------------------------------------------------------------------------------
class AddWriter(AhlWriter):
    """Writer конвейера на готовой базе: только строки игроков спек, их записи составов и связи."""

    def __init__(self, db, players, log=print):
        self.log, self.db = log, db
        self.orig = Tdb(bytes(db.d), db.meta)
        self.v = View(db)
        self.players = players
        self.mt, self.registry, self.own_clubs = {}, {}, set()
        from roster.ratings import Model
        self.model = Model(self.v, [])
        self.safe = {ch for r in range(self.v.nbio) for f in ('firstname', 'lastname', 'birthplace')
                     for ch in self.v.s(f, r) if ord(ch) > 127}
        self.notes = {p['nhl_id']: [] for p in players}
        self.out, self.new_links, self.events = {}, [], []
        self.skin_on, self.skin_pick, self.spare, self.fa_only = False, {}, False, False

    def find_existing(self):
        v = self.v
        key = {}
        for r in range(v.nbio):
            if not v.created_slot(r):
                key.setdefault((norm(v.s('firstname', r) + v.s('lastname', r)), v.birth(r)), []).append(r)
        self.row_of, self.new, self.donor_info = {}, set(), {}
        for p in self.players:
            rows = key.get((norm(p['first'] + p['last']), p['birth']), [])
            if len(rows) > 1:
                raise SpecError(f"{p['first']} {p['last']} {p['birth']}: в базе {len(rows)} строки с таким именем и "
                                'датой — правьте вручную')
            if rows:
                r = rows[0]
                if v.is_goalie(r) != (p['pos'] == 'G'):
                    raise SpecError(f"{p['first']} {p['last']}: в базе он {'вратарь' if v.is_goalie(r) else 'полевой'} "
                                    '— амплуа между вратарём и полевым не меняю')
                self.row_of[p['nhl_id']] = r
                if p.get('_team_default'):           # правка без team — клуб и записи составов как были
                    p['_keep_team'] = True

    def pick_donors(self):
        """Доноры — игроки без клуба (нет записей составов и связи в пуле свободных агентов), не созданные слоты,
        старшие первыми; пул свободных агентов не трогаем (там игроки «на сегодня» этапа ahl)."""
        v = self.v
        taken = set(self.row_of.values())
        pool = {'G': [], 'S': []}
        for r in range(v.nbio):
            if r in taken or v.created_slot(r) or not v.ai(r) or v.teams_of[r] or r in v.fa_rows:
                continue
            pool['G' if v.is_goalie(r) else 'S'].append((v.birth(r), r))
        for k in pool:
            pool[k].sort()
        for p in self.players:
            if p['nhl_id'] in self.row_of:
                continue
            k = 'G' if p['pos'] == 'G' else 'S'
            if not pool[k]:
                raise SpecError(f"{p['first']} {p['last']}: нет свободной строки-донора ({'вратарь' if k == 'G' else 'полевой'})")
            _, r = pool[k].pop(0)
            self.row_of[p['nhl_id']] = r
            self.new.add(p['nhl_id'])
            self.donor_info[p['nhl_id']] = {'row': r, 'name': v.name(r), 'birth': list(v.birth(r)),
                                            'artid': v.g('artid', r), 'game_id': v.gid[r]}

    def apply_contract(self, p, r):
        c = p['_contract']
        if not c or p.get('fa'):
            return
        who = f"{p['first']} {p['last']}"
        cap, years = _num(c.get('cap'), f'{who}: contract.cap'), int(_num(c.get('years'), f'{who}: contract.years'))
        if not 1 <= years <= 8:
            raise SpecError(f'{who}: contract.years {years} — 1…8')
        for f, x in (('contractdollars', round(cap / 5000)), ('contractlength', years), ('contractstatus', 1),
                     ('contractis2way', int(bool(c.get('two_way')))), ('contractismultiyear', int(years > 1)),
                     ('yearufa', SEASON_YEAR + years - 1900)):
            self.db.set(B, f, r, x)

    def apply_head(self, p, r):
        h = p['_head']
        if h is None:
            return
        if h not in self.head_skin:
            raise SpecError(f"{p['first']} {p['last']}: head {h} — не типовая голова базы "
                            f'({min(self.head_skin)}…{max(self.head_skin)})')
        self.db.set(B, 'headid', r, h)
        self.db.set(B, 'skincolor', r, self.head_skin[h])

    def keep_unlisted(self, p, r, bio0, ai0, t, ai):
        """Правка игрока, который уже есть: меняются только поля из спеки (SPEC_FIELDS), остальное — как было
        (драфт, игры, контракт этапа contracts, голова, портрет…). В атрибутах — сами атрибуты и OVR (ovr,
        attributes), стиль и тенденции стиля (style); потенциал и рост — как были."""
        db, spec = self.db, p['_spec']
        mine = set().union(*(SPEC_FIELDS.get(k, ()) for k in spec))
        if 'team' in spec and p.get('league'):      # в клуб без прав НХЛ — контракта НХЛ нет (write_bio обнулил)
            mine |= _CONTRACT
        for f, x in bio0.items():
            if f not in mine and db.get(B, f, r) != x:
                db.set(B, f, r, x)
        ok = {fld(f) for f in (GK if t == G else SK)} | {fld('p_overall' if t == S else 'g_overall')}
        if 'style' in spec:
            ok |= {fld('p_style')} | {fld(f) for f in W.SK_BIAS}
        for f, x in ai0.items():
            if f not in ok and db.get(t, f, ai) != x:
                db.set(t, f, ai, x)

    # --- составы -------------------------------------------------------------------------------------------------
    def row(self, e):
        return self.v.row_of_gid.get(self.v.link_gid.get(e['playerindex']))

    def place(self):
        """Записи составов: игрок спеки — в свой клуб (в конец состава) или в пул свободных агентов."""
        v, db = self.v, self.db
        self.entries = [dict(e) for e in v.entries]
        self.fa_list = list(v.fa)
        used = {e['playerindex'] for e in self.entries} | set(self.fa_list)
        free_index = (i for i in range(max(i for i in v.link_gid if i < LINK_LIMIT) + 1, LINK_LIMIT)
                      if i not in v.link_gid)
        self.touched = set()

        def link(r):
            cand = [l for l in v.links_of[v.gid[r]] if l not in used and l not in v.link_created]
            l = min(cand) if cand else next(free_index)
            if not cand:
                self.new_links.append((l, v.gid[r]))
            used.add(l)
            return l

        for p in self.players:
            r, who = self.row_of[p['nhl_id']], f"{p['first']} {p['last']}"
            if p.get('_keep_team'):
                for e in self.entries:                       # стиль в записях клубов — как в атрибутах (Writer)
                    if self.row(e) == r and e['team'] not in SPECIAL and e['playerstyle'] != p['_style']:
                        e['playerstyle'] = p['_style']
                        self.touched.add(e['team'])
                self.out[p['nhl_id']].update(team='как был', jersey=v.g('jersey', r), dressed=None, slots=None)
                continue
            mine = [e for e in self.entries if self.row(e) == r and e['team'] not in SPECIAL]
            fa_links = [l for l in self.fa_list if v.row_of_gid.get(v.link_gid.get(l)) == r]
            target = p['slot']
            keep = [e for e in mine if e['team'] == target]
            for e in mine:
                if e in keep:
                    continue
                if e['rosterstatus'] or e['captain'] or any(e[f] for f in FLAGS):
                    raise SpecError(f'{who}: в клубе {e["team"]} он одет / в звеньях / с буквой — переводить такого '
                                    'не берусь: уберите из звеньев в игре или в базе')
                self.entries.remove(e)
                self.touched.add(e['team'])
            if target is None:
                if not fa_links:
                    self.fa_list.append(link(r))
                db.set(B, 'team', r, 0)
                for f in W.CONTRACT + ['contractneedsentrylevel', 'contractismultiyear']:
                    db.set(B, f, r, 0)
                db.set(B, 'yearufa', r, SEASON_YEAR - 1900)
                if p.get('num'):
                    db.set(B, 'jersey', r, int(p['num']))
                self.out[p['nhl_id']].update(team='FA', jersey=v.g('jersey', r), dressed=0, slots=[])
                continue
            for l in fa_links:
                self.fa_list.remove(l)
            team = [e for e in self.entries if e['team'] == target]
            if keep:
                e = keep[0]
            else:
                if len(team) + 1 > ROSTER_MAX:
                    raise SpecError(f'{who}: в клубе {p["team"]} уже {len(team)} записей (больше {ROSTER_MAX} нельзя)')
                e = {f: 0 for f in v.entry_fields}
                e.update(team=target, playerindex=link(r), key=target * ROSTER_MAX + len(team))
                self.entries.append(e)
            e['playerstyle'] = p['_style']
            taken = {x['jersey'] for x in self.entries if x['team'] == target and x is not e}
            want = int(p.get('num') or e['jersey'] or 0)
            num = want if 1 <= want <= 98 and want not in taken else \
                min((n for n in range(2, 99) if n not in taken), key=lambda n: (abs(n - want), n))
            if want and num != want:
                self.notes[p['nhl_id']].append(f'номер {want} в клубе занят → {num}')
            e['jersey'] = num
            db.set(B, 'jersey', r, num)
            db.set(B, 'team', r, target + 1)
            self.touched.add(target)
            self.lines(p, e, target)
            self.out[p['nhl_id']].update(team=p['team'], jersey=num, dressed=e['rosterstatus'],
                                         slots=[f for f in FLAGS if e[f]])
        for t in self.touched:                                   # key подряд в прежнем порядке
            for k, e in enumerate(sorted((e for e in self.entries if e['team'] == t), key=lambda e: e['key'])):
                e['key'] = t * ROSTER_MAX + k
        self.entries.sort(key=lambda e: e['key'])

    def lines(self, p, e, target):
        mode, who = p['_lines'], f"{p['first']} {p['last']}"
        if mode is None:
            return
        team = [x for x in self.entries if x['team'] == target]
        if isinstance(mode, dict) and mode.get('replace'):
            if e['rosterstatus'] or any(e[f] for f in FLAGS):
                return                                           # уже на его местах (повторный запуск)
            want = norm(mode['replace'])
            hit = [x for x in team if x is not e and self.row(x) is not None and norm(self.v.name(self.row(x))) == want]
            if not hit:
                raise SpecError(f'{who}: lines.replace — «{mode["replace"]}» нет в клубе {p["team"]}')
            old = hit[0]
            if not (old['rosterstatus'] or any(old[f] for f in FLAGS)):
                raise SpecError(f'{who}: lines.replace — {mode["replace"]} и так в запасе')
            rk = POS_NAME[self.v.g('position', self.row(old))]
            if (rk == 'G') != (p['pos'] == 'G'):
                raise SpecError(f'{who}: lines.replace — {mode["replace"]} {"вратарь" if rk == "G" else "полевой"}')
            if (rk == 'D') != (p['pos'] == 'D'):
                self.notes[p['nhl_id']].append(f'места {mode["replace"]} ({rk}) — другое амплуа')
            for f in FLAGS + ['rosterstatus']:
                e[f], old[f] = old[f], 0
            self.notes[p['nhl_id']].append(f'звенья — места {mode["replace"]} (он в запасе)')
            return
        if mode != 'rating':
            raise SpecError(f'{who}: lines — нет, {{"replace": "Имя Фамилия"}} или "rating", а не «{mode}»')
        db, v = self.db, self.v
        lp = []
        for x in team:
            r = self.row(x)
            t, ai = v.ai(r)
            pos = POS_NAME[v.g('position', r)]
            attrs = {f: db.get(t, fld(f), ai) + BASE for f in (GK if t == G else SK)}
            lp.append({'key': x['playerindex'], 'pos': pos, 'ovr': ovrformula.game_ovr(cls(pos), attrs), 'attrs': attrs,
                       'shoots': 'L' if v.g('handedness', r) == 0 else 'R', 'out': False, '_e': x})
        try:
            keys, dressed = lines_mod.build(lp)
        except lines_mod.NotEnoughPlayers as err:
            raise SpecError(f'{who}: lines "rating" — в клубе мало игроков ({err})')
        by = {x['key']: x['_e'] for x in lp}
        for x in team:
            for f in FLAGS:
                x[f] = 0
            x['rosterstatus'] = int(x['playerindex'] in dressed)
        for slot, k in keys.items():
            by[k][slot] = 1
        self.rebuilt = getattr(self, 'rebuilt', set()) | {target}
        self.notes[p['nhl_id']].append(f'звенья клуба {p["team"]} — заново по рейтингу')

    # --- проверки ------------------------------------------------------------------------------------------------
    def check(self):
        db, bad = self.db, []
        v2 = View(db)
        cnt = Counter()
        for e in v2.entries:
            if e['key'] != e['team'] * ROSTER_MAX + cnt[e['team']]:
                bad.append(f"key {e['key']} у команды {e['team']} не подряд")
            cnt[e['team']] += 1
        links = Counter(e['playerindex'] for e in v2.entries)
        bad += [f'связь {l} у {n} записей' for l, n in links.items() if n > 1]
        bad += [f'свободный агент {l} в составе' for l in v2.fa if l in links]
        bad += [f"связи {e['playerindex']} нет в exhibitionplayers" for e in v2.entries if e['playerindex'] not in v2.link_gid]
        ov = View(self.orig)

        def state(vv, t):
            te = [e for e in vv.entries if e['team'] == t]
            return ({f: sum(e[f] for e in te) for f in FLAGS}, sum(1 for e in te if e['rosterstatus']),
                    (sum(e['captain'] == 1 for e in te), sum(e['captain'] == 2 for e in te)), {n for n, c in Counter(e['jersey'] for e in te).items() if c > 1},
                    len(te))
        for t in sorted(self.touched):
            a, b = state(ov, t), state(v2, t)
            if t not in getattr(self, 'rebuilt', ()) and (a[0] != b[0] or a[1] != b[1]):
                bad.append(f'клуб {t}: места звеньев или одетые изменились')
            if t in getattr(self, 'rebuilt', ()) and (any(n != 1 for n in b[0].values()) or b[1] != 20):
                bad.append(f'клуб {t}: звенья по рейтингу — не все места по одному или одетых {b[1]}')
            if a[2] != b[2]:
                bad.append(f'клуб {t}: буквы C/A {b[2]} (было {a[2]})')
            if b[3] - a[3]:
                bad.append(f'клуб {t}: повтор номеров {sorted(b[3] - a[3])}')
            if b[4] > ROSTER_MAX:
                bad.append(f'клуб {t}: {b[4]} записей')
        for p in self.players:
            r = self.row_of[p['nhl_id']]
            t, ai = v2.ai(r)
            attrs = {f: db.get(t, fld(f), ai) + BASE for f in (GK if t == G else SK)}
            self.out[p['nhl_id']]['ovr_game'] = got = ovrformula.game_ovr(cls(p['pos']), attrs)
            if got != round(p['_ovr']):
                bad.append(f"{p['first']} {p['last']}: OVR игры {got}, цель {p['_ovr']}")
            if p.get('_keep_team'):
                continue
            clubs = [e['team'] for e in v2.entries if v2.row_of_gid.get(v2.link_gid.get(e['playerindex'])) == r
                     and e['team'] not in SPECIAL]
            want = [] if p['slot'] is None else [p['slot']]
            if clubs != want:
                bad.append(f"{p['first']} {p['last']}: в составах {clubs}, нужен {want or 'пул FA'}")
            if v2.g('team', r) != (0 if p['slot'] is None else p['slot'] + 1):
                bad.append(f"{p['first']} {p['last']}: team {v2.g('team', r)}")
        return bad + [f'CRC @0x{o:X}' for o, *_ in db.verify()]

    def run(self):
        db, v = self.db, self.v
        self.find_existing()
        self.pick_donors()
        self.generic_heads()
        self.legacy_model()
        self.assign_artids()
        for p in self.players:
            r = self.row_of[p['nhl_id']]
            new = p['nhl_id'] in self.new
            self.out[p['nhl_id']] = {'name': f"{p['first']} {p['last']}", 'spec': p['_src'], 'row': r,
                                     'game_id': v.gid[r], 'new': new, 'donor': self.donor_info.get(p['nhl_id'])}
            spec, (t, ai) = p['_spec'], v.ai(r)
            bio0 = None if new else {f: db.get(B, f, r) for f in db.by_name[B]['fields']}
            ai0 = None if new else {f: db.get(t, f, ai) for f in db.by_name[t]['fields']}
            cur = {f: db.get(t, fld(f), ai) + BASE for f in (GK if t == G else SK)}
            if p['rating']['ovr'] is None:
                if new:
                    raise SpecError(f"{p['first']} {p['last']}: новому игроку нужен ovr (или все атрибуты)")
                p['rating']['ovr'] = ovrformula.game_ovr(cls(p['pos']), {**cur, **p['rating']['attrs']})
            if new or any(k in spec for k in ('ovr', 'attributes', 'style')):
                attrs, ovr, style = self.write_ratings(p, r, new)
            else:
                attrs, ovr, style = cur, ovrformula.game_ovr(cls(p['pos']), cur), db.get(t, fld('p_style'), ai)
            p['_attrs'], p['_ovr'], p['_style'] = attrs, ovr, style
            self.write_bio(p, r, new, ovr)
            self.apply_contract(p, r)
            self.apply_head(p, r)
            if not new:
                self.keep_unlisted(p, r, bio0, ai0, t, ai)
                self.notes[p['nhl_id']][:] = [n for n in self.notes[p['nhl_id']] if not n.startswith('нет ')]
            self.out[p['nhl_id']].update(artid=db.get(B, 'artid', r), ovr=ovr, style=style,
                                         potential=self.model.potential(p), notes=self.notes[p['nhl_id']])
        self.place()
        self.write_table_rows(R, self.entries)
        self.write_table_rows(F, [{'playerindex': l} for l in sorted(self.fa_list)])
        self.write_links()
        removed = self.clean_stats()
        db.fix()
        return self.check(), removed


# --- портрет -------------------------------------------------------------------------------------------------------
def portrait(img, artid, set_root):
    """PNG с прозрачным фоном → оба портрета игры (большой, малый) в set_root/fe/…; → [пути]."""
    argv, sys.argv = sys.argv, [sys.argv[0], '--game', 'legacy']     # photos.py читает --game при импорте
    try:
        import photos                                       # noqa: F401  (настраивает playerhead под Legacy)
    finally:
        sys.argv = argv
    import playerhead
    mug = playerhead.png_read(img)
    w, h, rgba = mug
    if not any(rgba[i] < 250 for i in range(3, len(rgba), 4 * 97)):
        raise SpecError(f'{img}: у картинки нет прозрачного фона — нужен вырезанный портрет (PNG с альфой)')
    auto = (w, h) != (336, 336)                              # не кадр НХЛ — по макушке и центру головы
    files = []
    for kind in ('big', 'small'):
        orig = playerhead.original_path(kind, artid)
        template = orig if os.path.exists(orig) else playerhead.default_template(kind)
        head = playerhead.PlayerHead.load(template)
        t = head.tex
        out_rgba = playerhead.compose(mug, kind, t.width, t.height, head.stage, auto)
        data = head.with_blocks(playerhead.dxt5_encode(out_rgba, t.width, t.height), None if template == orig else 'md5')
        rel = playerhead.asset_relpath(kind, artid)
        dst = os.path.join(set_root, *rel.split('/'))
        if not os.path.exists(dst) or open(dst, 'rb').read() != data:
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            tmp = dst + '.part'
            open(tmp, 'wb').write(data)
            os.replace(tmp, dst)
        files.append(rel)
    return files


# --- команды -------------------------------------------------------------------------------------------------------
def cmd_db(path, specs, dry, report):
    meta = os.path.join(os.path.dirname(path), 'nhlng-meta.xml')
    db = Tdb(open(path, 'rb').read(), load_meta(meta))
    if 'nhlfutureschedule' not in db.by_name:
        raise SpecError(f'{path}: не база NHL Legacy')
    players = []
    for i, (src, s) in enumerate(specs):
        p = to_player(s, i, src)
        resolve_team(db, p)
        players.append(p)
    seen = Counter(p['nhl_id'] for p in players)
    dup = [f"{p['first']} {p['last']}" for p in players if seen[p['nhl_id']] > 1]
    if dup:
        raise SpecError(f'один игрок в спеках дважды: {sorted(set(dup))}')
    w = AddWriter(db, players)
    bad, removed = w.run()
    set_root = os.path.dirname(os.path.dirname(os.path.abspath(path)))
    for p in players:
        o = w.out[p['nhl_id']]
        if p['_photo'] and not bad:
            r = w.row_of[p['nhl_id']]
            o['portrait'] = portrait(p['_photo'], db.get(B, 'artid', r), set_root) if not dry else 'проба'
            db.set(B, 'hasportrait', r, 1)
        print(f"  {o['name']}: {'новый, строка донора ' + o['donor']['name'] if o['new'] else 'уже в базе — правка'}; "
              f"{o.get('team')} № {o.get('jersey')}"
              f"{'' if o.get('dressed') is None or o.get('team') == 'FA' else ', одет' if o['dressed'] else ', в запасе'}; "
              f"OVR {o.get('ovr_game')}; artid {o['artid']}" + (f"; {'; '.join(o['notes'])}" if o['notes'] else ''))
    if bad:
        print('  ПРОВЕРКИ:', *bad[:10], sep='\n    ')
        raise SystemExit(f'{path}: не записано ({len(bad)} проблем)')
    db.fix()
    changed = bytes(db.d) != bytes(w.orig.d)
    summary = {'db': path, 'players': list(w.out.values()), 'new_links': w.new_links, 'stats_removed': removed,
               'changed': changed}
    if report:
        os.makedirs(os.path.dirname(os.path.abspath(report)), exist_ok=True)
        json.dump(summary, open(report, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    if dry or not changed:
        print(f"{path}: игроков {len(players)}; {'проба, не записано' if dry else 'база уже такая — без записи'}")
        return summary
    tmp = path + '.part'
    with open(tmp, 'wb') as fh:
        fh.write(db.d)
    os.replace(tmp, path)
    print(f'{path}: игроков {len(players)} (новых {len(w.new)}), новых связей {len(w.new_links)} — записано')
    return summary


def main(argv):
    sys.stdout.reconfigure(encoding='utf-8')
    if not argv or argv[0] not in ('db', 'example'):
        sys.exit(__doc__)
    if argv[0] == 'example':
        print(open(EXAMPLE, encoding='utf-8').read())
        return
    dry = '--dry-run' in argv
    report = argv[argv.index('--report') + 1] if '--report' in argv else None
    rest = [a for i, a in enumerate(argv[1:], 1) if a != '--dry-run' and a != '--report' and argv[i - 1] != '--report']
    if not rest:
        sys.exit('нужна база: add_players.py db БАЗА.db [СПЕКА.json | ПАПКА …]')
    try:
        specs = load_specs(rest[1:])
        if not specs:
            print(f'спек нет ({SPEC_DIR}) — ничего не делаю')
            return
        cmd_db(rest[0], specs, dry, report)
    except SpecError as e:
        sys.exit(f'ошибка: {e}')


if __name__ == '__main__':
    main(sys.argv[1:])
