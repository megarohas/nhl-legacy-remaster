"""Составы в редакторе: карточка игрока, перевод в другой клуб, новый игрок — в копии ростера, запись новым ростером.

Что игра грузит: новейший сейв ROSTER поверх базы (docs/launcher.md, «Как игра выбирает ростер»). Редактор открывает
ростер (по умолчанию новейший), правки держит в памяти и пишет НОВЫМ ростером `ROSTER <время UTC>` в saves\\rosters с
именем в меню `ROSTER ДД.ММ.ГГГГ` — прежние ростеры не трогаются, файл сейва того же размера: места таблиц (max)
не меняются, новые записи занимают запас [current, max) (так пишет и игра, tools/legacy_data/roster_merge.py
write_table). Перед записью: суммы файла и базы, места и поля таблиц как у исходного ростера, лаунчер
`--check-roster` (если он рядом).

Таблицы (docs/roster-pipeline.md): exhibitionplayerbiotable (био по game_id), exhibitionskaterai /
exhibitiongoalieai (атрибуты: шкала 36–99, в файле − 36), exhibitionskaterequipment / exhibitiongoalieequipment,
exhibitionplayers (связь index → game_id), exhibitionrostertable (запись состава: team, playerindex, key = клуб × 40 +
место, номер, буква, одет, 71 место в звеньях), exhibitionfreeagents (связи свободных агентов).

Перевод: как у конвейера (roster/write.py free_vacancy): места в звеньях, «одет» и буква уходящего достаются запасному
того же амплуа в прежнем клубе; запасного нет — звенья клуба заново по рейтингу (roster/lines.py build); в новом
клубе игрок — в запасе, номер прежний или ближайший свободный, контракт едет с ним. Новый игрок — пустой слот
создаваемых игроков игры (связи 16000+ с table = 1, 180 штук; так делает и CREATE PLAYER самой игры).
"""
import datetime
import os
import re
import shutil
import struct
import subprocess
import sys
import time

os.environ.setdefault('NHL_GAME', 'legacy')
_TOOLS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if os.path.join(_TOOLS, 'legacy_data') not in sys.path:
    sys.path.insert(0, os.path.join(_TOOLS, 'legacy_data'))      # roster_merge.write_table

import gamefs  # noqa: E402
import winui  # noqa: E402
from gamefs import EditorError  # noqa: E402

B, S, G = 'exhibitionplayerbiotable', 'exhibitionskaterai', 'exhibitiongoalieai'
SE, GE = 'exhibitionskaterequipment', 'exhibitiongoalieequipment'
P, R, F, T = 'exhibitionplayers', 'exhibitionrostertable', 'exhibitionfreeagents', 'exhibitionteams'
ROSTER_MAX = 40
BASE = 36
POS = {0: 'C', 1: 'LW', 2: 'RW', 3: 'D', 4: 'G'}
POS_LINES = {0: 'C', 1: 'L', 2: 'R', 3: 'D', 4: 'G'}
SPECIAL_LEAGUES = {8, 12, 13, 14, 15}          # сборные, проспекты, Custom, Зимняя классика, EASHL
ALLSTAR = (222, 223)
CREATED_LINK = 16000

FLAGS = ([f'l{n}{p}' for n in (1, 2, 3) for p in ('lw', 'c', 'rw', 'ld', 'rd')] + ['l4lw', 'l4c', 'l4rw']
         + [f'pp{n}{p}' for n in (1, 2) for p in ('lw', 'c', 'rw', 'ld', 'rd')]
         + [f'pp4_{n}{p}' for n in (1, 2) for p in ('lw', 'c', 'ld', 'rd')]
         + [f'pk4_{n}{p}' for n in (1, 2) for p in ('lw', 'c', 'ld', 'rd')]
         + [f'pk3_{n}{p}' for n in (1, 2) for p in ('c', 'ld', 'rd')]
         + [f'ot_{n}{p}' for n in (1, 2, 3) for p in ('lw', 'c', 'ld', 'rd')]
         + [f's{n}' for n in range(1, 6)] + ['x1', 'x2', 'g1', 'g2'])

# атрибуты (шкала 36–99): поле c_* и подписи; порядок — как в меню игры по группам
SK_ATTRS = [
    ('Броски', 'Shooting', ['wristaccuracy', 'wristshotpower', 'slapaccuracy', 'slapshotpower']),
    ('Владение', 'Puck skills', ['deking', 'handeye', 'passing', 'puckcontrol']),
    ('Катание', 'Skating', ['speed', 'acceleration', 'agility', 'balance', 'endurance']),
    ('Чутьё', 'Sense', ['offawareness', 'defawareness', 'discipline', 'poise', 'faceoffs']),
    ('Оборона', 'Defense', ['shotblocking', 'stickchecking']),
    ('Сила', 'Physical', ['bodychecking', 'strength', 'aggression', 'durability', 'fightingskill']),
]
GK_ATTRS = [
    ('Сейвы', 'Saves', ['gsh', 'gsl', 'ssh', 'ssl', '5hole', 'breakaway']),
    ('Позиция и отскоки', 'Positioning', ['positioning', 'reboundcontrol', 'shotrecover', 'vision']),
    ('Атлетизм', 'Athletics', ['speed', 'agility', 'endurance', 'durability', 'aggression']),
    ('Клюшка', 'Stick', ['pokecheck', 'passing', 'puckplayfrequency', 'poise']),
]
ATTR_LABELS = {
    'wristaccuracy': ('Точность кистевого', 'Wrist shot accuracy'), 'wristshotpower': ('Сила кистевого', 'Wrist shot power'),
    'slapaccuracy': ('Точность щелчка', 'Slap shot accuracy'), 'slapshotpower': ('Сила щелчка', 'Slap shot power'),
    'deking': ('Обводка', 'Deking'), 'handeye': ('Координация', 'Hand-eye'), 'passing': ('Пас', 'Passing'),
    'puckcontrol': ('Контроль шайбы', 'Puck control'), 'speed': ('Скорость', 'Speed'),
    'acceleration': ('Ускорение', 'Acceleration'), 'agility': ('Ловкость', 'Agility'), 'balance': ('Баланс', 'Balance'),
    'endurance': ('Выносливость', 'Endurance'), 'offawareness': ('Чутьё в атаке', 'Offensive awareness'),
    'defawareness': ('Чутьё в обороне', 'Defensive awareness'), 'discipline': ('Дисциплина', 'Discipline'),
    'poise': ('Хладнокровие', 'Poise'), 'faceoffs': ('Вбрасывания', 'Faceoffs'),
    'shotblocking': ('Блок бросков', 'Shot blocking'), 'stickchecking': ('Отбор клюшкой', 'Stick checking'),
    'bodychecking': ('Силовые приёмы', 'Body checking'), 'strength': ('Сила', 'Strength'),
    'aggression': ('Агрессия', 'Aggression'), 'durability': ('Крепость', 'Durability'),
    'fightingskill': ('Драка', 'Fighting skill'), 'gsh': ('Перчатка, верх', 'Glove high'),
    'gsl': ('Перчатка, низ', 'Glove low'), 'ssh': ('Блин, верх', 'Stick side high'), 'ssl': ('Блин, низ', 'Stick side low'),
    '5hole': ('Между щитков', 'Five hole'), 'breakaway': ('Выходы один на один', 'Breakaway'),
    'positioning': ('Позиция', 'Positioning'), 'reboundcontrol': ('Контроль отскоков', 'Rebound control'),
    'shotrecover': ('Восстановление', 'Shot recovery'), 'vision': ('Видение', 'Vision'),
    'pokecheck': ('Выбивание', 'Poke check'), 'puckplayfrequency': ('Игра клюшкой', 'Puck playing'),
}
SK_STYLES = {1: ('Оборонец', 'Defensive D'), 2: ('Атакующий защитник', 'Offensive D'), 3: ('Силовой защитник', 'Enforcer D'),
             4: ('Универсал', 'Two-way D'), 5: ('Работяга', 'Grinder'), 6: ('Плеймейкер', 'Playmaker'),
             7: ('Снайпер', 'Sniper'), 8: ('Силовой нападающий', 'Power forward'), 9: ('Двусторонний', 'Two-way F'),
             10: ('Тафгай', 'Enforcer')}
G_STYLES = {0: ('Стойка', 'Stand-up'), 1: ('Баттерфляй', 'Butterfly'), 2: ('Гибрид', 'Hybrid')}

# поля био и экипировки: (поле, подпись ru, en, вид, параметры). Вид: str, int (как в файле), off (файл + k),
# enum {значение: (ru, en)}, bool, money (× 5000 $), year (+1900).
BIO_MAIN = [
    ('firstname', 'Имя', 'First name', 'str'), ('lastname', 'Фамилия', 'Last name', 'str'),
    ('jersey', 'Номер', 'Number', 'int'),
    ('position', 'Амплуа', 'Position', 'enum', {0: ('Центр', 'C'), 1: ('Левый крайний', 'LW'),
                                                  2: ('Правый крайний', 'RW'), 3: ('Защитник', 'D'), 4: ('Вратарь', 'G')}),
    ('handedness', 'Хват (у вратаря — рука ловушки)', 'Shoots (goalie: catches)', 'enum',
     {0: ('Левый', 'Left'), 1: ('Правый', 'Right')}),
    ('year', 'Год рождения', 'Birth year', 'year'), ('month', 'Месяц рождения', 'Birth month', 'off', 1),
    ('day', 'День рождения', 'Birth day', 'off', 1),
    ('height', 'Рост, дюймов', 'Height, in', 'off', 54), ('weight', 'Вес, фунтов', 'Weight, lb', 'off', 120),
    ('birthplace', 'Место рождения', 'Birthplace', 'str'), ('intlcountry', 'Страна (сборная)', 'Country (national team)', 'int'),
    ('state', 'Место рождения: страна или штат', 'Birth country or state', 'int'),
    ('rookie', 'Новичок', 'Rookie', 'bool'),
]
BIO_LOOK = [
    ('headid', 'Голова (headid)', 'Head (headid)', 'int'), ('skincolor', 'Тон кожи', 'Skin tone', 'int'),
    ('eyecolorcode', 'Цвет глаз', 'Eye color', 'int'), ('hasportrait', 'Есть фото', 'Has portrait', 'bool'),
    ('artid', 'Номер фото (artid)', 'Photo number (artid)', 'int'), ('audioid', 'Голос комментатора', 'Commentary name', 'int'),
]
BIO_CONTRACT = [
    ('contractdollars', 'Зарплата, $ в год', 'Salary, $ per year', 'money'),
    ('contractlength', 'Лет контракта', 'Contract years', 'int'),
    ('contractis2way', 'Двусторонний', 'Two-way', 'bool'), ('contractismultiyear', 'Многолетний', 'Multi-year', 'bool'),
    ('contractstatus', 'Статус контракта', 'Contract status', 'int'),
    ('contractneedsentrylevel', 'Нужен контракт новичка', 'Needs entry level', 'bool'),
    ('yearufa', 'Неограниченно свободный с', 'UFA year', 'year'),
    ('yearfirstsigned', 'Первый контракт, год', 'First signed', 'year'),
    ('yearwaivereligible', 'Драфт отказов с', 'Waiver eligible', 'year'),
    ('extensiondollars', 'Продление: $ в год', 'Extension: $ per year', 'money'),
    ('extensionlength', 'Продление: лет', 'Extension: years', 'int'),
    ('extensionis2way', 'Продление: двустороннее', 'Extension: two-way', 'bool'),
    ('draftyear', 'Драфт: год', 'Draft year', 'year'), ('draftround', 'Драфт: раунд', 'Draft round', 'int'),
    ('draftposition', 'Драфт: номер', 'Draft pick', 'int'),
    ('nhlgamesplayedcareer', 'Игр в НХЛ', 'NHL games', 'int'),
    ('nhlgamesplayedlastseason', 'Игр в НХЛ в прошлом сезоне', 'NHL games last season', 'int'),
    ('progamesplayedcareer', 'Игр среди профи', 'Pro games', 'int'),
]
SK_EQUIP = [
    ('stick', 'Клюшка (модель)', 'Stick (model)'), ('stickcurve', 'Загиб', 'Curve'), ('stickflex', 'Жёсткость', 'Flex'),
    ('sticktapecolor', 'Обмотка', 'Tape'), ('helmetbrand', 'Шлем', 'Helmet'), ('visortype', 'Визор', 'Visor'),
    ('visorcolor', 'Цвет визора', 'Visor color'), ('gloves', 'Краги', 'Gloves'), ('pantsbrand', 'Шорты (бренд)', 'Pants brand'),
    ('pantstypecode', 'Шорты (модель)', 'Pants model'), ('skatebrand', 'Коньки', 'Skates'),
    ('skaterocker', 'Профиль конька', 'Skate rocker'), ('skatesocktuck', 'Заправка гетр', 'Sock tuck'),
    ('jerseytuck', 'Заправка свитера', 'Jersey tuck'), ('shoulderpads', 'Наплечники', 'Shoulder pads'),
]
GK_EQUIP = [('pads', 'Щитки', 'Pads'), ('blocker', 'Блин', 'Blocker'), ('trapper', 'Ловушка', 'Catcher'),
            ('stick', 'Клюшка', 'Stick'), ('helmet', 'Шлем', 'Helmet'), ('masktype', 'Тип маски', 'Mask type'),
            ('maskid', 'Маска', 'Mask')]
LETTERS = {0: ('нет', 'none'), 1: ('Капитан (C)', 'Captain (C)'), 2: ('Ассистент (A)', 'Alternate (A)')}


def _game_ovr(pos, attrs):
    from roster import ovrformula
    c = {'C': 'C', 'LW': 'W', 'RW': 'W', 'D': 'D', 'G': 'G'}[pos]
    pre = 'g_' if c == 'G' else 'p_'
    return ovrformula.game_ovr(c, {pre + k: v for k, v in attrs.items()})


def _rec_get(db, t, f, raw):
    off, w = db.by_name[t]['fields'][f]
    return (int.from_bytes(raw, 'big') >> (len(raw) * 8 - off - w)) & ((1 << w) - 1)


def _rec_set(db, t, f, raw, val):
    off, w = db.by_name[t]['fields'][f]
    if not 0 <= val < (1 << w):
        raise ValueError(f'{t}.{f}: {val} не влезает в {w} бит')
    sh = len(raw) * 8 - off - w
    v = int.from_bytes(raw, 'big')
    v = (v & ~(((1 << w) - 1) << sh)) | (val << sh)
    return bytearray(v.to_bytes(len(raw), 'big'))


class Entry:
    """Запись exhibitionrostertable как байты; поля — e[f], e[f] = v."""

    def __init__(self, db, raw):
        self.db, self.raw = db, bytearray(raw)

    def __getitem__(self, f):
        return _rec_get(self.db, R, f, self.raw)

    def __setitem__(self, f, v):
        self.raw = _rec_set(self.db, R, f, self.raw, v)

    def busy(self):
        return bool(self['rosterstatus'] or self['captain'] or any(self[f] for f in FLAGS))


DB_REF = '@db'      # «ростер» с этим именем — база content\…\db\nhlng.db (основа новых ростеров и франшиз)


class DbRef:
    name = DB_REF
    stamp = ''
    header = ''

    def __init__(self, path):
        self.file = path


class Session:
    def __init__(self, ed, ref=None):
        self.ed = ed
        ed.db.load()
        if not ed.db.meta_path:
            raise EditorError('no_db', 'Нет базы content\\database\\db\\nhlng.db', 'No database')
        from tdb import SaveFile, Tdb
        self.meta = ed.db.meta
        self.is_db = ref == DB_REF
        if self.is_db:
            hit = ed.fs.find('db/nhlng.db')
            if not hit or not hit[2]:
                raise EditorError('no_db', 'Нет базы content\\…\\db\\nhlng.db', 'No database content\\…\\db\\nhlng.db')
            self.ref = DbRef(hit[2])
            self.raw = open(hit[2], 'rb').read()
            self.sf = None
            db = self.db = Tdb(self.raw, self.meta)
            bad = db.verify()
            if bad:
                raise EditorError('bad_db', f'База повреждена: CRC @0x{bad[0][0]:X}', f'The database is damaged: CRC '
                                  f'@0x{bad[0][0]:X}')
        else:
            saves = ed.fs.saves
            refs = saves.list('ROSTER')
            if not refs:
                raise EditorError('no_roster', 'Ростеров нет: игра ещё не сохраняла составы (CUSTOMIZE → SAVE) и '
                                  '«Обновить ростеры» в лаунчере не делали. Можно править базу',
                                  'No rosters yet: save rosters in the game or use «Update rosters» in the launcher. '
                                  'You can edit the database')
            self.ref = next((r for r in refs if r.name == ref), None) if ref else refs[-1]
            if self.ref is None:
                raise EditorError('no_roster', f'Нет ростера {ref}', f'No roster {ref}')
            self.raw = open(self.ref.file, 'rb').read()
            self.sf = SaveFile(self.raw, self.meta)
            if self.sf.zlib is None:
                raise EditorError('bad_roster', 'Это не сейв ROSTER NHL Legacy', 'Not an NHL Legacy ROSTER save')
            bad = self.sf.verify()
            if bad:
                raise EditorError('bad_roster', 'Ростер повреждён: ' + '; '.join(bad[:3]), 'The roster is damaged: '
                                  + '; '.join(bad[:3]))
            db = self.db = self.sf.db
        for t in (B, S, G, SE, GE, P, R, F):
            if t in db.by_name and db.counts(t)[2]:
                raise EditorError('deleted', f'В ростере есть удалённые записи ({t}) — такой редактор не правит',
                                  f'The roster has deleted records ({t}) — the editor does not edit such files')
        self.counts0 = {t['name']: db.counts(t['name'])[:2] for t in db.tables}
        self.entries = [Entry(db, db.record(R, r)) for r in db.live_rows(R)]
        self.fa = [db.get(F, 'playerindex', r) for r in db.live_rows(F)]
        self.link_gid, self.link_table = {}, {}
        for r in db.live_rows(P):
            i = db.get(P, 'index', r)
            self.link_gid[i] = db.get(P, 'playerid', r)
            self.link_table[i] = db.get(P, 'table', r)
        self.bio = {db.get(B, 'game_id', r): r for r in db.live_rows(B)}
        self.ai = {}
        for t in (S, G):
            for r in db.live_rows(t):
                self.ai[db.get(t, 'game_id', r)] = (t, r)
        self.eq = {}
        for t in (SE, GE):
            if t in db.by_name:
                for r in db.live_rows(t):
                    self.eq[db.get(t, 'game_id', r)] = (t, r)
        self.teams = {}
        for r in db.live_rows(T):
            i = db.get(T, 'index', r)
            self.teams[i] = dict(index=i, name=re.sub(r'[®™]', '', db.get_string(T, 'fullname', r)).strip(),
                                 abbr=db.get_string(T, 'abbrname', r), league=db.value(T, 'league', r),
                                 table=db.get(T, 'table', r), active=db.get(T, 'active', r))
        self.changes = []
        self.dirty = False

    # ------------------------------------------------------------ чтение
    def g(self, t, f, r):
        return self.db.value(t, f, r, raw=True)

    def club(self, team):
        t = self.teams.get(team)
        if t and t['table'] == 1:                       # свой клуб (слот Custom Team, CREATE TEAM игры) — если включён
            return bool(t['active'])
        return bool(t) and t['league'] not in SPECIAL_LEAGUES and team not in ALLSTAR

    def gid_of(self, e):
        return self.link_gid.get(e['playerindex'])

    def name(self, gid):
        r = self.bio.get(gid)
        if r is None:
            return str(gid)
        return f'{self.db.get_string(B, "firstname", r)} {self.db.get_string(B, "lastname", r)}'.strip()

    def attrs(self, gid):
        t, r = self.ai.get(gid, (None, None))
        if t is None:
            return {}
        names = [a for _, _, fs in (GK_ATTRS if t == G else SK_ATTRS) for a in fs]
        return {a: self.db.get(t, 'c_' + a, r) + BASE for a in names if 'c_' + a in self.db.by_name[t]['fields']}

    def pos(self, gid):
        return POS.get(self.db.get(B, 'position', self.bio[gid]), '?')

    def ovr(self, gid):
        a = self.attrs(gid)
        if not a:
            return None
        try:
            return _game_ovr(self.pos(gid), a)
        except Exception:                            # noqa: BLE001
            return None

    def age(self, gid):
        r = self.bio[gid]
        y = self.db.get(B, 'year', r) + 1900
        m = self.db.get(B, 'month', r) + 1
        d = self.db.get(B, 'day', r) + 1
        today = datetime.date.today()
        return today.year - y - ((today.month, today.day) < (m, d))

    def row(self, gid, e=None, fa=False):
        r = self.bio[gid]
        return dict(gid=gid, name=self.name(gid), first=self.db.get_string(B, 'firstname', r),
                    last=self.db.get_string(B, 'lastname', r), pos=self.pos(gid),
                    jersey=e['jersey'] if e is not None else self.db.get(B, 'jersey', r), ovr=self.ovr(gid),
                    age=self.age(gid), dressed=bool(e['rosterstatus']) if e is not None else False,
                    lines=bool(e is not None and any(e[f] for f in FLAGS)),
                    letter={1: 'C', 2: 'A'}.get(e['captain'], '') if e is not None else '',
                    link=e['playerindex'] if e is not None else None, fa=fa,
                    created=self.link_table.get(e['playerindex']) == 1 if e is not None else False)

    def team_players(self, team):
        if team == 'FA':
            out = []
            for link in self.fa:
                gid = self.link_gid.get(link)
                if gid in self.bio:
                    d = self.row(gid, fa=True)
                    d['link'] = link
                    out.append(d)
            return out
        team = int(team)
        return [self.row(self.gid_of(e), e) for e in self.entries if e['team'] == team and self.gid_of(e) in self.bio]

    def leagues(self, lang):
        import gamedb
        out = {}
        for t in self.teams.values():
            if (t['table'] == 1 and not t['active']) or not t['name']:
                continue
            code = 99 if t['index'] in ALLSTAR else t['league']
            out.setdefault(code, []).append(dict(index=t['index'], name=t['name'], abbr=t['abbr'], club=self.club(t['index']),
                                                 count=sum(1 for e in self.entries if e['team'] == t['index'])))
        res = []
        for code in sorted(out):
            name = ('Матч звёзд' if lang == 'ru' else 'All-Star') if code == 99 else self.ed.db.league_name(code, lang)
            res.append(dict(code=code, name=name, teams=sorted(out[code], key=lambda x: x['name'])))
        return res

    # ------------------------------------------------------------ карточка
    def _field(self, t, f, r, label_ru, label_en, kind, extra=None, lang='ru', readonly=False):
        db = self.db
        if f not in db.by_name[t]['fields']:
            return None
        off, w = db.by_name[t]['fields'][f]
        raw = db.get(t, f, r) if db.by_name[t]['kinds'].get(f) != 0 else None
        d = dict(key=f'{t}.{f}', label=label_ru if lang == 'ru' else label_en, kind=kind, readonly=readonly)
        if db.by_name[t]['kinds'].get(f) == 0:
            d.update(kind='str', value=db.get_string(t, f, r), maxlen=w // 8 - 1)
        elif kind == 'enum':
            d.update(value=raw, options=[[k, v[0] if lang == 'ru' else v[1]] for k, v in extra.items()])
        elif kind == 'bool':
            d.update(value=bool(raw))
        elif kind == 'money':
            d.update(value=raw * 5000, min=0, max=((1 << w) - 1) * 5000, step=5000)
        elif kind == 'year':
            d.update(value=raw + 1900, min=1900, max=1900 + (1 << w) - 1)
        elif kind == 'off':
            d.update(value=raw + extra, min=extra, max=extra + (1 << w) - 1)
        elif kind == 'rating':
            d.update(value=raw + BASE, min=BASE, max=min(99, BASE + (1 << w) - 1))
        else:
            low = db.by_name[t]['lows'].get(f, 0)
            d.update(kind='int', value=raw + low, min=low, max=low + (1 << w) - 1)
        return d

    def card(self, gid, team=None, lang='ru'):
        gid = int(gid)
        if gid not in self.bio:
            raise EditorError('no_player', f'Нет игрока {gid}', f'No player {gid}')
        r = self.bio[gid]
        L = lambda ru, en: ru if lang == 'ru' else en           # noqa: E731
        goalie = self.db.get(B, 'position', r) == 4
        sec = []

        def group(title, items):
            items = [x for x in items if x]
            if items:
                sec.append(dict(title=title, fields=items))

        main = []
        for spec in BIO_MAIN:
            f, ru, en, kind = spec[:4]
            extra = spec[4] if len(spec) > 4 else None
            if f == 'position' and goalie:
                extra = {4: extra[4]}
            elif f == 'position':
                extra = {k: v for k, v in extra.items() if k != 4}
            main.append(self._field(B, f, r, ru, en, kind, extra, lang))
        e = self.club_entry(gid, int(team)) if team not in (None, '', 'FA') else None
        if e is not None:
            main.append(dict(key='entry.captain', label=L('Буква', 'Letter'), kind='enum', value=e['captain'],
                             options=[[k, v[0] if lang == 'ru' else v[1]] for k, v in LETTERS.items()]))
        group(L('Основное', 'Main'), main)
        t, ar = self.ai.get(gid, (None, None))
        if t is not None:
            st = G_STYLES if t == G else SK_STYLES
            if not goalie:
                pos = self.db.get(B, 'position', r)
                st = {k: v for k, v in st.items() if (k <= 4) == (pos == 3)}
            items = [self._field(t, 'playerstyle', ar, 'Стиль', 'Style', 'enum', st, lang)]
            group(L('Стиль', 'Style'), items)
            for gru, gen, names in (GK_ATTRS if t == G else SK_ATTRS):
                group(L(gru, gen), [self._field(t, 'c_' + a, ar, *ATTR_LABELS[a], 'rating', lang=lang) for a in names])
            group(L('Потенциал', 'Potential'), [self._field(t, 'c_potential', ar, 'Потенциал (как в файле)',
                                                             'Potential (raw)', 'int', lang=lang)])
        group(L('Внешность', 'Appearance'), [self._field(B, sp[0], r, *sp[1:], lang=lang) for sp in BIO_LOOK])
        et, er = self.eq.get(gid, (None, None))
        if et is not None:
            group(L('Экипировка', 'Equipment'), [self._field(et, f, er, ru, en, 'int', lang=lang)
                                                  for f, ru, en in (GK_EQUIP if et == GE else SK_EQUIP)])
        group(L('Контракт и карьера', 'Contract and career'),
              [self._field(B, sp[0], r, *sp[1:], lang=lang) for sp in BIO_CONTRACT])
        # все поля — для тех, кто знает базу
        shown = {f['key'] for s in sec for f in s['fields']}
        allf = []
        for tt, rr in ((B, r), (t, ar), (et, er)):
            if tt is None:
                continue
            for f in sorted(self.db.by_name[tt]['fields']):
                if f'{tt}.{f}' in shown or f == 'game_id':
                    continue
                d = self._field(tt, f, rr, f'{tt.replace("exhibition", "")}.{f}', f'{tt.replace("exhibition", "")}.{f}',
                                'int', lang=lang, readonly=f in ('team', 'proteam'))
                if d:
                    allf.append(d)
        sec.append(dict(title=L('Все поля (как в базе)', 'All fields (as in the database)'), fields=allf, advanced=True))
        self._named(sec, lang)
        import pickers
        if getattr(self.ed, 'pickers', None) is None:
            self.ed.pickers = pickers.Pickers(self.ed)
        self.ed.pickers.apply(self, sec, lang, gid)
        info = self.row(gid, e) if e is not None else self.row(gid, fa=team == 'FA')
        info['team'] = team
        info['clubs'] = [dict(index=x['team'], name=self.teams.get(x['team'], {}).get('name', '?'))
                         for x in self.entries if self.gid_of(x) == gid]
        return dict(player=info, sections=sec)

    def _named(self, sec, lang):
        """Коды → названия: страна и регион (roster/codes.py), модели экипировки (каталоги редактора игры)."""
        import gamecat
        cat = getattr(self.ed, 'catalogs', None)
        if cat is None:
            cat = self.ed.catalogs = gamecat.Catalogs(self.ed)
        equip = {f'{SE}.stick': 'stick', f'{SE}.gloves': 'gloves', f'{SE}.helmetbrand': 'helmetbrand',
                 f'{SE}.skatebrand': 'skatebrand', f'{GE}.pads': 'goalie', f'{GE}.blocker': 'goalie',
                 f'{GE}.trapper': 'goalie'}
        pending = False
        for s in sec:
            for f in s['fields']:
                k = f['key']
                if k in (f'{B}.state', f'{B}.intlcountry'):
                    opts = gamecat.country_options(lang, countries_only=k.endswith('intlcountry'))
                    if f['value'] not in [o[0] for o in opts]:
                        opts.insert(0, (f['value'], f'{f["value"]}'))
                    f.update(kind='enum', options=[list(o) for o in opts])
                elif k in equip:
                    opts = cat.options(equip[k], f['value'], lang)
                    if opts is None:
                        pending = True
                        continue
                    f.update(kind='enum', options=[list(o) for o in opts])
        if pending:
            sec.insert(0, dict(title=self.ed.t('Названия экипировки готовятся (разбор каталога игры, ~30 с; '
                                               'откройте карточку ещё раз)', 'Equipment names are being prepared '
                                               '(reading the game catalog, ~30 s; reopen the card)'), fields=[]))

    def club_entry(self, gid, team):
        return next((e for e in self.entries if e['team'] == team and self.gid_of(e) == gid), None)

    # ------------------------------------------------------------ правка
    def _set(self, t, f, r, value, kind=None):
        db = self.db
        if db.by_name[t]['kinds'].get(f) == 0:
            text = str(value).strip()
            try:
                text.encode('latin1')
            except UnicodeEncodeError:
                raise EditorError('chars', f'«{text}»: буквы вне шрифта игры — пишите латиницей без диакритики',
                                  f'«{text}»: letters outside the game font — use plain Latin')
            db.set_string(t, f, r, text)
            return
        off, w = db.by_name[t]['fields'][f]
        v = int(round(float(value))) if not isinstance(value, bool) else int(value)
        if kind == 'money':
            v = int(round(float(value) / 5000))
        elif kind == 'year':
            v -= 1900
        elif kind == 'off':
            v -= self._off.get(f, 0)
        elif kind == 'rating':
            v -= BASE
        elif kind not in ('bool', 'enum'):
            v -= db.by_name[t]['lows'].get(f, 0)
        if not 0 <= v < (1 << w):
            raise EditorError('range', f'{f}: значение {value} вне пределов поля', f'{f}: value {value} is out of range')
        db.set(t, f, r, v)

    _off = {'month': 1, 'day': 1, 'height': 54, 'weight': 120}

    def update(self, gid, team, values, lang='ru'):
        """values {ключ поля карточки: значение} → правка в памяти; → обновлённая карточка."""
        gid = int(gid)
        card = self.card(gid, team, lang)
        kinds = {f['key']: f for s in card['sections'] for f in s['fields']}
        r = self.bio[gid]
        notes = []
        team_i = int(team) if team not in (None, '', 'FA') else None
        e = self.club_entry(gid, team_i) if team_i is not None else None
        for key, val in values.items():
            fd = kinds.get(key)
            if fd is None or fd.get('readonly'):
                continue
            if key == 'entry.captain':
                if e is None:
                    continue
                v = int(val)
                if v == 1:
                    for x in self.entries:
                        if x['team'] == team_i and x is not e and x['captain'] == 1:
                            x['captain'] = 0
                            notes.append(self.ed.t(f'буква C снята с {self.name(self.gid_of(x))}',
                                                   f'C removed from {self.name(self.gid_of(x))}'))
                e['captain'] = v
                continue
            t, f = key.split('.', 1)
            if key == f'{B}.jersey':
                v = int(val)
                if not 0 <= v <= 99:
                    raise EditorError('range', 'Номер — от 0 до 99', 'Number must be 0–99')
                if e is not None:
                    taken = [self.name(self.gid_of(x)) for x in self.entries
                             if x['team'] == team_i and x is not e and x['jersey'] == v]
                    if taken:
                        raise EditorError('number', f'Номер {v} в клубе уже у {taken[0]}',
                                          f'Number {v} is already taken by {taken[0]}')
                    e['jersey'] = v
            if key == f'{B}.position':
                v = int(val)
                if (v == 4) != (self.db.get(B, 'position', r) == 4):
                    raise EditorError('pos', 'Полевого нельзя сделать вратарём и наоборот (другие таблицы атрибутов)',
                                      'A skater cannot become a goalie and vice versa')
            rr = r if t == B else self.ai[gid][1] if t in (S, G) else self.eq[gid][1]
            self._set(t, f, rr, val, fd.get('base_kind', fd['kind']))
            if t in (S, G) and f == 'playerstyle':
                for x in self.entries:
                    if self.gid_of(x) == gid:
                        x['playerstyle'] = int(val)
        if values:
            self.dirty = True
            self.changes.append(self.ed.t(f'{self.name(gid)}: правка карточки (изменено полей: {len(values)})',
                                          f'{self.name(gid)}: card edit ({len(values)} fields)'))
        t, ar = self.ai.get(gid, (None, None))
        if t is not None:                                   # c_overall — как посчитает игра (игра его не читает)
            o = self.ovr(gid)
            if o is not None and 'c_overall' in self.db.by_name[t]['fields']:
                self.db.set(t, 'c_overall', ar, o - BASE)
        out = self.card(gid, team, lang)
        out['notes'] = notes
        return out

    # ------------------------------------------------------------ перевод
    def _kind(self, gid):
        p = self.db.get(B, 'position', self.bio[gid])
        return 'G' if p == 4 else 'D' if p == 3 else 'F'

    def _lines_player(self, e):
        gid = self.gid_of(e)
        r = self.bio[gid]
        a = self.attrs(gid)
        pre = 'g_' if self._kind(gid) == 'G' else 'p_'
        return {'key': e['playerindex'], 'pos': POS_LINES[self.db.get(B, 'position', r)], 'ovr': self.ovr(gid) or 50,
                'attrs': {pre + k: v for k, v in a.items()}, 'shoots': 'L' if self.db.get(B, 'handedness', r) == 0 else 'R',
                'out': False, '_e': e}

    def _vacate(self, e, notes):
        """Места в звеньях, «одет» и буква уходящей записи e — запасному того же амплуа; нет — звенья по рейтингу."""
        if not e.busy():
            return
        team, gid = e['team'], self.gid_of(e)
        kind = self._kind(gid)
        spares = [x for x in self.entries if x['team'] == team and x is not e and not x.busy()
                  and self.gid_of(x) in self.bio and self._kind(self.gid_of(x)) == kind]
        if spares:
            best = max(spares, key=lambda x: self.ovr(self.gid_of(x)) or 0)
            for f in FLAGS + ['rosterstatus', 'captain']:
                best[f], e[f] = e[f], 0
            notes.append(self.ed.t(f'его места в звеньях занял {self.name(self.gid_of(best))}',
                                   f'his line spots went to {self.name(self.gid_of(best))}'))
            return
        from roster import lines as lines_mod
        letter = e['captain']
        team_e = [x for x in self.entries if x['team'] == team and x is not e and self.gid_of(x) in self.bio]
        lp = [self._lines_player(x) for x in team_e]
        try:
            keys, dressed = lines_mod.build(lp)
        except lines_mod.NotEnoughPlayers as err:
            raise EditorError('lines', f'В клубе {self.teams[team]["name"]} без него не собрать звенья ({err})',
                              f'{self.teams[team]["name"]} cannot dress a lineup without him ({err})')
        by = {p['key']: p['_e'] for p in lp}
        for x in team_e + [e]:
            for f in FLAGS:
                x[f] = 0
            x['rosterstatus'] = int(x['playerindex'] in dressed)
        for slot, k in keys.items():
            by[k][slot] = 1
        e['captain'] = 0
        if letter:
            self._give_letter(team, letter, notes)
        notes.append(self.ed.t(f'запасного того же амплуа нет — звенья {self.teams[team]["name"]} собраны по рейтингу',
                               f'no spare of the same position — {self.teams[team]["name"]} lines rebuilt by rating'))

    def _give_letter(self, team, letter, notes):
        cand = [x for x in self.entries if x['team'] == team and x['rosterstatus'] and not x['captain']
                and self.gid_of(x) in self.bio and self._kind(self.gid_of(x)) != 'G']
        if not cand:
            return
        best = max(cand, key=lambda x: self.db.get(B, 'nhlgamesplayedcareer', self.bio[self.gid_of(x)]))
        best['captain'] = letter
        notes.append(self.ed.t(f'буква {"C" if letter == 1 else "A"} — {self.name(self.gid_of(best))}',
                               f'letter {"C" if letter == 1 else "A"} — {self.name(self.gid_of(best))}'))

    def _rekey(self, *teams):
        for t in teams:
            if t is None:
                continue
            for k, e in enumerate(sorted((e for e in self.entries if e['team'] == t), key=lambda e: e['key'])):
                e['key'] = t * ROSTER_MAX + k
        self.entries.sort(key=lambda e: e['key'])

    def _free_number(self, team, want, skip=None):
        taken = {x['jersey'] for x in self.entries if x['team'] == team and x is not skip}
        if 1 <= want <= 98 and want not in taken:
            return want
        return min((n for n in range(2, 99) if n not in taken), key=lambda n: (abs(n - want), n))

    def move(self, gid, src, dst, lang='ru'):
        """Перевод игрока: src/dst — номер клуба или 'FA'. → заметки."""
        gid = int(gid)
        notes = []
        r = self.bio.get(gid)
        if r is None:
            raise EditorError('no_player', f'Нет игрока {gid}', f'No player {gid}')
        if dst != 'FA':
            dst = int(dst)
            if not self.club(dst):
                raise EditorError('special', 'Переводить можно только в клуб (не в сборную, Матч звёзд, проспекты)',
                                  'Players can only move to a club (not national, All-Star or prospect teams)')
        if src != 'FA':
            src = int(src)
            if not self.club(src):
                raise EditorError('special', 'Из сборных и особых команд игрок не переводится — правьте его клуб',
                                  'Players are not moved out of national/special teams — edit his club')
        if src == dst:
            return notes
        if src == 'FA':
            link = next((l for l in self.fa if self.link_gid.get(l) == gid), None)
            if link is None:
                raise EditorError('no_fa', 'Игрока нет в списке свободных агентов', 'The player is not a free agent')
            self.fa.remove(link)
            e = None
        else:
            e = self.club_entry(gid, src)
            if e is None:
                raise EditorError('no_entry', 'Игрока нет в этом клубе', 'The player is not on this team')
            self._vacate(e, notes)
            link = e['playerindex']
        if dst == 'FA':
            if e is not None:
                self.entries.remove(e)
            self.fa.append(link)
            self.fa.sort()
            for f in ('team', 'contractdollars', 'contractlength', 'contractstatus', 'contractis2way',
                      'contractismultiyear', 'contractneedsentrylevel', 'proteam'):
                if f in self.db.by_name[B]['fields']:
                    self.db.set(B, f, r, 0)
            self.db.set(B, 'yearufa', r, datetime.date.today().year - 1900)
            notes.append(self.ed.t('контракт снят: свободный агент', 'contract cleared: free agent'))
        else:
            n = sum(1 for x in self.entries if x['team'] == dst)
            if n >= ROSTER_MAX:
                raise EditorError('full', f'В клубе {self.teams[dst]["name"]} уже {n} игроков (больше 40 нельзя)',
                                  f'{self.teams[dst]["name"]} already has {n} players (40 max)')
            if e is None:
                tpl = next((x for x in self.entries), None)
                e = Entry(self.db, bytes(len(tpl.raw)) if tpl else bytes(self.db.by_name[R]['reclen']))
                e['playerindex'] = link
                self.entries.append(e)
            for f in FLAGS + ['rosterstatus', 'captain']:
                e[f] = 0
            e['team'] = dst
            e['key'] = dst * ROSTER_MAX + n                 # в конец клуба, _rekey — подряд
            t, ar = self.ai.get(gid, (None, None))
            if t is not None:
                e['playerstyle'] = self.db.get(t, 'playerstyle', ar)
            want = self.db.get(B, 'jersey', r) or 0
            num = self._free_number(dst, want, e)
            if num != want:
                notes.append(self.ed.t(f'номер {want} в клубе занят → {num}', f'number {want} is taken → {num}'))
            e['jersey'] = num
            self.db.set(B, 'jersey', r, num)
            self.db.set(B, 'team', r, dst + 1)
            league = self.teams[dst]['league']
            fw = self.db.by_name[B]['fields']['proteam'][1]
            if league == 0 and dst + 1 < (1 << fw):
                self.db.set(B, 'proteam', r, dst + 1)
                if not self.db.get(B, 'contractdollars', r):
                    self.db.set(B, 'contractdollars', r, 170)        # 850 000 $ — минимальный (как roster_update)
                    self.db.set(B, 'contractlength', r, 1)
                    self.db.set(B, 'contractstatus', r, 1)
                    self.db.set(B, 'yearufa', r, datetime.date.today().year + 1 - 1900)
                    notes.append(self.ed.t('контракта не было — минимальный на год (850 000 $), поправьте в карточке',
                                           'no contract — a one-year minimum (850,000 $), edit it in the card'))
        self._rekey(src if src != 'FA' else None, dst if dst != 'FA' else None)
        self.dirty = True
        where = lambda t: (self.ed.t('свободные агенты', 'free agents') if t == 'FA' else self.teams[t]['name'])  # noqa
        self.changes.append(f'{self.name(gid)}: {where(src)} → {where(dst)}')
        return notes

    def swap(self, gid_a, gid_b, team):
        """Поменять местами в звеньях двух игроков одного клуба: 71 место и «одет» (буквы — как были). Так запасной
        встаёт в состав вместо одетого — как «поменять» в EDIT LINES игры."""
        team = int(team)
        a, b = self.club_entry(int(gid_a), team), self.club_entry(int(gid_b), team)
        if a is None or b is None or a is b:
            raise EditorError('swap', 'Оба игрока должны быть в этом клубе', 'Both players must be on this team')
        ka, kb = self._kind(int(gid_a)), self._kind(int(gid_b))
        if (ka == 'G') != (kb == 'G'):
            raise EditorError('swap', 'Вратаря можно поменять только с вратарём', 'A goalie swaps only with a goalie')
        for f in FLAGS + ['rosterstatus']:
            a[f], b[f] = b[f], a[f]
        self.dirty = True
        self.changes.append(self.ed.t(f'{self.teams[team]["abbr"]}: {self.name(int(gid_a))} ⇄ {self.name(int(gid_b))} '
                                      'в звеньях', f'{self.teams[team]["abbr"]}: {self.name(int(gid_a))} ⇄ '
                                      f'{self.name(int(gid_b))} in lines'))
        note = [] if ka == kb else [self.ed.t('амплуа разные: защитник встал на место нападающего или наоборот',
                                              'different positions: a defenceman takes a forward spot or vice versa')]
        return note

    def rebuild_lines(self, team):
        """Звенья клуба заново по рейтингу (roster/lines.py build: 4 тройки, 3 пары, спецбригады, 2 вратаря, 20 одетых).
        Буквы — как были."""
        from roster import lines as lines_mod
        team = int(team)
        team_e = [x for x in self.entries if x['team'] == team and self.gid_of(x) in self.bio]
        lp = [self._lines_player(x) for x in team_e]
        try:
            keys, dressed = lines_mod.build(lp)
        except lines_mod.NotEnoughPlayers as err:
            raise EditorError('lines', f'Мало игроков для звеньев ({err}): нужно 2 вратаря и 18 полевых',
                              f'Not enough players for lines ({err}): 2 goalies and 18 skaters are needed')
        by = {pl['key']: pl['_e'] for pl in lp}
        for x in team_e:
            for f in FLAGS:
                x[f] = 0
            x['rosterstatus'] = int(x['playerindex'] in dressed)
        for slot, k in keys.items():
            by[k][slot] = 1
        self.dirty = True
        self.changes.append(self.ed.t(f'{self.teams[team]["abbr"] or self.teams[team]["name"]}: звенья по рейтингу',
                                      f'{self.teams[team]["abbr"] or self.teams[team]["name"]}: lines by rating'))
        return []

    def new_club(self, name, abbr, short=None, primary='#1e4f9c', secondary='#ffffff'):
        """Свой клуб на свободном слоте Custom Team (exhibitionteams table = 1, лига 13 — как CREATE TEAM игры): имя,
        сокращение, цвета, active = 1. Форма и логотип — конструктора игры (customteamjerseys, czlogo): нарисовать
        их — CUSTOMIZE → Creation Zone → Edit Team в игре. → номер клуба."""
        name, abbr = name.strip(), abbr.strip().upper()
        if not name or not abbr:
            raise EditorError('club', 'Нужны название и сокращение', 'Name and abbreviation are required')
        slot = next((i for i, t in sorted(self.teams.items()) if t['table'] == 1 and not t['active']), None)
        if slot is None:
            raise EditorError('club_full', 'Свободных слотов своих клубов нет', 'No free custom club slots')
        r = next(r for r in self.db.live_rows(T) if self.db.get(T, 'index', r) == slot)
        for f, text in (('fullname', name), ('abbrname', abbr[:4]), ('shortname', short or name), ('artabbr', abbr[:4])):
            self._set(T, f, r, text)
        self.db.set(T, 'active', r, 1)
        for f, c in (('primarycolor', primary), ('secondarycolor', secondary)):
            c = c.lstrip('#')
            for k, ch in enumerate('rgb'):
                self.db.set(T, f'{f}_{ch}', r, int(c[2 * k:2 * k + 2], 16))
        self.teams[slot].update(name=name, abbr=abbr[:4], active=1)
        self.dirty = True
        self.changes.append(self.ed.t(f'новый клуб {name} ({abbr}) на слоте {slot}', f'new club {name} ({abbr}) on slot {slot}'))
        return slot

    # ------------------------------------------------------------ новый игрок
    def create(self, team, pos, first, last, ovr=70, lang='ru'):
        pos = int(pos)
        goalie = pos == 4
        used = {e['playerindex'] for e in self.entries} | set(self.fa)
        slot = None
        for link in sorted(self.link_gid):
            if link < CREATED_LINK or self.link_table.get(link) != 1 or link in used:
                continue
            gid = self.link_gid[link]
            r = self.bio.get(gid)
            if r is None or self.db.get_string(B, 'firstname', r) or self.db.get_string(B, 'lastname', r):
                continue
            t = self.ai.get(gid, (None,))[0]
            if t == (G if goalie else S):
                slot = (link, gid)
                break
        if slot is None:
            raise EditorError('no_slot', 'Свободных слотов создаваемых игроков нет (их 180 в ростере)',
                              'No free created-player slots left (the roster has 180)')
        link, gid = slot
        r = self.bio[gid]
        first, last = first.strip(), last.strip()
        if not last:
            raise EditorError('name', 'Нужна фамилия', 'Last name is required')
        self._set(B, 'firstname', r, first)
        self._set(B, 'lastname', r, last)
        self.db.set(B, 'position', r, pos)
        self.db.set(B, 'active', r, 1)
        self.db.set(B, 'year', r, datetime.date.today().year - 22 - 1900)
        self.db.set(B, 'height', r, 73 - 54)
        self.db.set(B, 'weight', r, 195 - 120)
        t, ar = self.ai[gid]
        target = max(40, min(99, int(ovr)))
        names = [a for _, _, fs in (GK_ATTRS if goalie else SK_ATTRS) for a in fs]
        p = POS[pos]
        val = target
        for v in range(36, 100):                  # ровные атрибуты, при которых игра покажет OVR не ниже цели
            if _game_ovr(p, {a: v for a in names}) >= target:
                val = v
                break
        for a in names:
            if 'c_' + a in self.db.by_name[t]['fields']:
                self.db.set(t, 'c_' + a, ar, val - BASE)
        style = 0 if goalie else (4 if pos == 3 else 9)
        self.db.set(t, 'playerstyle', ar, style)
        if 'c_overall' in self.db.by_name[t]['fields']:
            self.db.set(t, 'c_overall', ar, (self.ovr(gid) or target) - BASE)
        self.fa.append(link)
        self.fa.sort()
        self.db.set(B, 'team', r, 0)
        self.dirty = True
        self.changes.append(self.ed.t(f'новый игрок {first} {last} ({p})', f'new player {first} {last} ({p})'))
        notes = []
        if team not in (None, '', 'FA'):
            notes += self.move(gid, 'FA', team, lang)
        return gid, notes

    # ------------------------------------------------------------ запись
    def build(self):
        """Байты нового ростера и проверки. → bytes."""
        from roster_merge import write_table
        from tdb import SaveFile
        db = self.db
        live = [bytes(db.record(R, r)) for r in db.live_rows(R)]
        new = [bytes(e.raw) for e in self.entries]
        if new != live:
            write_table(db, R, new)
        fa_now = [db.get(F, 'playerindex', r) for r in db.live_rows(F)]
        if fa_now != self.fa:
            tpl = bytearray(db.record(F, db.live_rows(F)[0])) if fa_now else bytearray(db.by_name[F]['reclen'])
            recs = [bytes(_rec_set(db, F, 'playerindex', tpl, link)) for link in self.fa]
            write_table(db, F, recs)
        out = self.sf.bytes()
        chk = SaveFile(out, self.meta)
        bad = chk.verify()
        for t in chk.db.tables:
            n = t['name']
            mx, cur = chk.db.counts(n)[:2]
            if mx != self.counts0[n][0]:
                bad.append(f'{n}: мест {mx} вместо {self.counts0[n][0]}')
            if cur > mx:
                bad.append(f'{n}: записей {cur} больше мест {mx}')
        if len(out) != len(self.raw):
            bad.append(f'размер файла {len(out)} вместо {len(self.raw)}')
        cnt = {}
        for e in self.entries:
            cnt[e['team']] = cnt.get(e['team'], 0) + 1
        bad += [f'клуб {t}: {n} записей' for t, n in cnt.items() if n > ROSTER_MAX]
        if bad:
            raise EditorError('check', 'Проверка ростера не прошла, ничего не записано: ' + '; '.join(bad[:5]),
                              'Roster check failed, nothing written: ' + '; '.join(bad[:5]))
        return out

    def launcher_check(self, path):
        exe = os.path.join(self.ed.fs.install, 'nhllegacy_launcher.exe')
        if not os.path.isfile(exe):
            return None, 'нет лаунчера'
        try:
            p = subprocess.run([exe, '--check-roster', path, '--lang=' + self.ed.lang], capture_output=True, timeout=60,
                               creationflags=0x08000000 if os.name == 'nt' else 0)
        except (OSError, subprocess.TimeoutExpired) as e:
            return None, str(e)
        return p.returncode, (p.stdout or b'').decode('utf-8', 'replace').strip()

    def build_db(self):
        """База с правками: таблицы составов и свободных агентов — ровно по записям (max = current, как у наших баз,
        Tdb.resize), CRC — Tdb.fix(). → bytes."""
        from tdb import Tdb
        db = self.db
        for t, recs in ((R, [bytes(e.raw) for e in self.entries]), (F, None)):
            if recs is None:
                tpl = bytearray(db.record(F, 0)) if db.by_name[F]['rows'] else bytearray(db.by_name[F]['reclen'])
                recs = [bytes(_rec_set(db, F, 'playerindex', tpl, link)) for link in self.fa]
            cur = [bytes(db.record(t, r)) for r in range(db.by_name[t]['rows'])]
            if cur == recs:
                continue
            db.resize(t, len(recs))
            for i, raw in enumerate(recs):
                db.put_record(t, i, raw)
        db.fix()
        out = bytes(db.d)
        chk = Tdb(out, self.meta)
        bad = [f'CRC @0x{o:X}' for o, *_ in chk.verify()]
        cnt = {}
        for e in self.entries:
            cnt[e['team']] = cnt.get(e['team'], 0) + 1
        bad += [f'клуб {t}: {n} записей' for t, n in cnt.items() if n > ROSTER_MAX]
        if bad:
            raise EditorError('check', 'Проверка базы не прошла, ничего не записано: ' + '; '.join(bad[:5]),
                              'Database check failed, nothing written: ' + '; '.join(bad[:5]))
        return out

    def save_db(self):
        """База → content\\my\\db\\nhlng.db (+ draft_roster.db из неё, legacy_data/draft_roster.py). Затем новейший
        ROSTER сверяется с новой базой лаунчером: игра сравнивает места таблиц сейва с базой, и если правка базы
        (новые записи) сломала бы сохранённые ростеры, она откатывается."""
        gamefs.check_game_closed()
        out = self.build_db()
        from draft_roster import KEEP, extract
        from tdb import Tdb
        draft = extract(Tdb(out, self.meta), KEEP)
        fs = self.ed.fs
        rels = ('db/nhlng.db', 'db/draft_roster.db')
        backup = fs.backup_dir()
        had = {r: fs.in_my(r) for r in rels}
        for rel, data in zip(rels, (out, draft)):
            fs.write_my(rel, data, backup)
        refs = fs.saves.list('ROSTER')
        code, msg = (None, '')
        if refs:
            code, msg = self.launcher_check(refs[-1].file)
        if code not in (None, 0):
            for rel in rels:                              # откат: прежняя правка my или её отсутствие
                p = fs.my_path(rel)
                q = os.path.join(backup, 'content', 'my', *rel.split('/'))
                if had[rel] and os.path.isfile(q):
                    shutil.copy2(q, p)
                elif not had[rel] and os.path.isfile(p):
                    fs.revert(rel, backup)
            raise EditorError('db_vs_roster', f'С этими правками база не подходит к ростеру {refs[-1].name} (лаунчер, '
                              f'код {code}: {msg}) — игра назвала бы его damaged. База возвращена как была',
                              f'With these edits the database does not fit roster {refs[-1].name} (launcher code '
                              f'{code}: {msg}) — the game would call it damaged. The database was restored')
        self.ed.log(f'база: {fs.my_path(rels[0])}: {"; ".join(self.changes[-20:])}; ростер {refs[-1].name if refs else "—"}'
                    f' — лаунчер {code}')
        self.dirty = False
        self.ed.db.loaded = False                         # имена — заново
        return dict(folder=os.path.dirname(fs.my_path(rels[0])), name='content\\my\\db\\nhlng.db',
                    display='content\\my\\db\\nhlng.db', launcher=code, changes=self.changes, db=True)

    def save(self):
        if self.is_db:
            return self.save_db()
        gamefs.check_game_closed()
        out = self.build()
        stamp = datetime.date.today().strftime('%d.%m.%Y')
        work = os.path.join(self.ed.fs.work, 'rosters')
        os.makedirs(work, exist_ok=True)
        tmp = os.path.join(work, f'ROSTER {stamp}')
        open(tmp, 'wb').write(out)
        code, msg = self.launcher_check(tmp)
        if code not in (None, 0, 8):            # 8 — лаунчеру не с чем сверять (старый лаунчер без content) — свои проверки
            raise EditorError('launcher', f'Лаунчер не принял ростер (код {code}): {msg}',
                              f'The launcher rejected the roster (code {code}): {msg}')
        folder, header = write_save(self.ed.fs.saves, out, f'ROSTER {stamp}')
        self.ed.log(f'новый ростер {folder} из {self.ref.name}: {"; ".join(self.changes[-20:])}')
        name = os.path.basename(folder)
        self.dirty = False
        return dict(folder=folder, name=name, display=f'ROSTER {stamp}', launcher=code, changes=self.changes)


def header_bytes(folder, display):
    h = bytearray(0x148)
    h[0:8] = struct.pack('>II', 1, 1)
    name = display.encode('utf-16-be')[:0x100 - 2]
    h[8:8 + len(name)] = name
    raw = folder.encode('ascii')
    h[0x108:0x108 + len(raw)] = raw
    h[0x138:0x140] = bytes.fromhex('B13EBABEBABEBABE')
    h[0x140:0x144] = bytes.fromhex('454109EC')
    return bytes(h)


def write_save(saves, data, display):
    """Новая папка ROSTER <время UTC> (не раньше новейшего + 1 с — её игра загрузит) и заголовок с именем в меню."""
    names = [r.name for r in saves.list('ROSTER') if re.fullmatch(r'ROSTER \d{14}A?', r.name)]
    now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None, microsecond=0)
    newest = max((datetime.datetime.strptime(n[7:21], '%Y%m%d%H%M%S') for n in names), default=None)
    if newest and newest >= now:
        now = newest + datetime.timedelta(seconds=1)
    folder = 'ROSTER ' + now.strftime('%Y%m%d%H%M%S')
    save_dir, header_path = saves.place_for(folder)
    os.makedirs(save_dir)
    with open(os.path.join(save_dir, folder), 'wb') as f:
        f.write(data)
    os.makedirs(os.path.dirname(header_path), exist_ok=True)
    with open(header_path, 'wb') as f:
        f.write(header_bytes(folder, display))
    return save_dir, header_path


def roster_display(ref):
    """Имя ростера в меню игры — из заголовка (смещение 8, UTF-16 BE)."""
    if ref.name == DB_REF:
        return 'nhlng.db'
    try:
        h = open(ref.header, 'rb').read()
        return h[8:0x108].decode('utf-16-be').split('\0')[0]
    except (OSError, UnicodeDecodeError):
        return ''


# ---------------------------------------------------------------- HTTP
def handle(ed, method, fn, q, a):
    lang = ed.lang
    if fn == 'list':
        refs = ed.fs.saves.list('ROSTER')
        cur = ed.rosters.ref.name if ed.rosters else None
        return dict(rosters=[dict(name=r.name, display=roster_display(r), stamp=r.stamp) for r in reversed(refs)]
                    + [dict(name=DB_REF, display=ed.t('БАЗА игры (основа новых профилей и франшиз)',
                                                      'Game DATABASE (base for new profiles and franchises)'),
                            stamp='')],
                    current=cur, dirty=bool(ed.rosters and ed.rosters.dirty),
                    changes=ed.rosters.changes if ed.rosters else [])
    if fn == 'open':
        if ed.rosters and ed.rosters.dirty and not a.get('discard'):
            raise EditorError('dirty', 'Есть несохранённые правки', 'There are unsaved edits')
        ed.rosters = Session(ed, a.get('name'))
        return dict(ok=True, name=ed.rosters.ref.name)
    s = ed.rosters
    if s is None:
        s = ed.rosters = Session(ed)
    if fn == 'teams':
        return dict(leagues=s.leagues(lang), roster=s.ref.name, display=roster_display(s.ref), dirty=s.dirty,
                    changes=s.changes, is_db=s.is_db, file=s.ref.file)
    if fn == 'players':
        return dict(players=s.team_players(q['team']))
    if fn == 'card':
        return s.card(q['gid'], q.get('team'), lang)
    if fn == 'update':
        return s.update(a['gid'], a.get('team'), a.get('values') or {}, lang)
    if fn == 'move':
        notes = s.move(a['gid'], a['src'], a['dst'], lang)
        return dict(ok=True, notes=notes, changes=s.changes)
    if fn == 'lines':
        s.rebuild_lines(a['team'])
        return dict(ok=True, changes=s.changes)
    if fn == 'new_club':
        slot = s.new_club(a.get('name', ''), a.get('abbr', ''), a.get('short'), a.get('primary') or '#1e4f9c',
                          a.get('secondary') or '#ffffff')
        return dict(ok=True, team=slot, changes=s.changes)
    if fn == 'swap':
        notes = s.swap(a['a'], a['b'], a['team'])
        return dict(ok=True, notes=notes, changes=s.changes)
    if fn == 'create':
        gid, notes = s.create(a.get('team'), a.get('pos', 0), a.get('first', ''), a.get('last', ''), a.get('ovr', 70), lang)
        return dict(ok=True, gid=gid, notes=notes, changes=s.changes)
    if fn == 'discard':
        ed.rosters = Session(ed, s.ref.name)
        return dict(ok=True)
    if fn == 'save':
        res = s.save()
        ed.rosters = Session(ed, DB_REF if s.is_db else None)   # база — снова базу, ростер — записанный (новейший)
        return res
    if fn == 'export':
        ref = s.ref
        start = ed.settings.get('export_dir') or os.path.join(os.path.expanduser('~'), 'Desktop')
        disp = roster_display(ref) or 'ROSTER'
        if s.is_db:
            disp = 'nhlng.db'
        elif not re.search(r'\d{2}\.\d{2}\.\d{4}', disp):
            disp = 'ROSTER ' + datetime.datetime.strptime(ref.stamp, '%Y%m%d%H%M%S').strftime('%d.%m.%Y') \
                if ref.stamp else 'ROSTER'
        p = winui.save_file(ed.t('Выгрузить ростер', 'Export roster'), start, disp)
        if not p:
            return None
        shutil.copyfile(ref.file, p)
        return dict(written=[p], folder=os.path.dirname(p))
    if fn == 'import':
        start = ed.settings.get('import_dir')
        p = winui.pick_file(ed.t('Файл ростера', 'Roster file'), start, [('ROSTER', 'ROSTER*'), ('*', '*.*')])
        if not p:
            return None
        gamefs.check_game_closed()
        exe = os.path.join(ed.fs.install, 'nhllegacy_launcher.exe')
        if not os.path.isfile(exe):
            raise EditorError('no_launcher', 'Рядом нет nhllegacy_launcher.exe — им проверяется и ставится ростер',
                              'nhllegacy_launcher.exe is missing — it checks and adds rosters')
        r = subprocess.run([exe, '--import-roster', p, '--lang=' + ed.lang], capture_output=True, timeout=120,
                           creationflags=0x08000000 if os.name == 'nt' else 0)
        msg = (r.stdout or b'').decode('utf-8', 'replace').strip()
        if r.returncode != 0:
            raise EditorError('launcher', f'Лаунчер не принял файл (код {r.returncode}): {msg}',
                              f'The launcher rejected the file (code {r.returncode}): {msg}')
        if not s.dirty:
            ed.rosters = Session(ed)
        return dict(ok=True, message=msg)
    raise EditorError('bad', f'rosters/{fn}?')


_ = (sys, time)
