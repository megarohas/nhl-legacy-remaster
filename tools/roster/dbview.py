"""Чтение базы для конвейера: игроки, их строки атрибутов, связи и записи составов.

Как устроены ссылки (проверено на исходной базе):
- exhibitionplayerbiotable (био) — строка на игрока, ключ `game_id`, строки по нему отсортированы;
- exhibitionskaterai / exhibitiongoalieai — атрибуты по тому же `game_id` (полевые и вратари
  в разных таблицах: 4875 + 537 = 5412 строк био);
- exhibitionplayers — «связи»: `index` (номер связи, по нему таблица отсортирована) →
  `playerid` = `game_id`; на одного игрока — по связи на каждое его появление в составах
  (у Кросби пять: PIT, Канада, Легенды, Team Wickenheiser, PIT Зимней классики);
  index ≥ 16000 с `table` = 1 — 180 слотов создаваемых игроков (пустые строки био);
- exhibitionrostertable.playerindex — номер связи, у каждой записи своя; `key` = команда × 40 +
  место (места 0…n−1 без пропусков), внутри команды записи идут по возрастанию playerindex;
- exhibitionfreeagents.playerindex — связи свободных агентов (в составах не используются).
"""
from collections import defaultdict

B, S, G = 'exhibitionplayerbiotable', 'exhibitionskaterai', 'exhibitiongoalieai'
P, R, F = 'exhibitionplayers', 'exhibitionrostertable', 'exhibitionfreeagents'
T = 'exhibitionteams'
NHL = range(0, 32)
ALLSTAR = (86, 87)                 # сборные Матча звёзд после tools/nhl32.py
NATIONAL = range(128, 149)
SPECIAL = set(NATIONAL) | set(ALLSTAR) | set(range(209, 218))   # сборные, проспекты, легенды, Зимняя классика
CLUBS = (set(range(32, 128)) | set(range(149, 209))) - set(ALLSTAR)
LINK_LIMIT = 16000                 # с 16000 — связи создаваемых игроков
FLAGS = ([f'l{n}{p}' for n in (1, 2, 3) for p in ('lw', 'c', 'rw', 'ld', 'rd')] + ['l4lw', 'l4c', 'l4rw']
         + [f'pp{n}{p}' for n in (1, 2) for p in ('lw', 'c', 'rw', 'ld', 'rd')]
         + [f'pp4_{n}{p}' for n in (1, 2) for p in ('lw', 'c', 'ld', 'rd')]
         + [f'pk4_{n}{p}' for n in (1, 2) for p in ('lw', 'c', 'ld', 'rd')]
         + [f'pk3_{n}{p}' for n in (1, 2) for p in ('c', 'ld', 'rd')]
         + [f'ot_{n}{p}' for n in (1, 2, 3) for p in ('lw', 'c', 'ld', 'rd')]
         + [f's{n}' for n in range(1, 6)] + ['x1', 'x2', 'g1', 'g2'])
assert len(FLAGS) == 71
POS_CODE = {'C': 0, 'L': 1, 'R': 2, 'D': 3, 'G': 4}
POS_NAME = {v: k for k, v in POS_CODE.items()}


class View:
    def __init__(self, db):
        self.db = db
        self.nbio = db.by_name[B]['rows']
        self.gid = db.column(B, 'game_id')
        self.row_of_gid = {g: r for r, g in enumerate(self.gid)}
        self.ai_row = {}
        for t in (S, G):
            for r, g in enumerate(db.column(t, 'game_id')):
                self.ai_row[g] = (t, r)
        idx, pid, tab = db.column(P, 'index'), db.column(P, 'playerid'), db.column(P, 'table')
        self.link_gid = dict(zip(idx, pid))
        self.link_created = {i for i, t in zip(idx, tab) if t == 1}
        self.links_of = defaultdict(list)
        for i, g in zip(idx, pid):
            self.links_of[g].append(i)
        fields = list(db.by_name[R]['fields'])
        self.entry_fields = fields
        self.entries = [{f: db.get(R, f, r) for f in fields} for r in range(db.by_name[R]['rows'])]
        self.fa = db.column(F, 'playerindex')
        self.teams_of = defaultdict(list)          # строка био → [команды, где он в составе]
        for e in self.entries:
            g = self.link_gid.get(e['playerindex'])
            if g in self.row_of_gid:
                self.teams_of[self.row_of_gid[g]].append(e['team'])
        self.fa_rows = {self.row_of_gid[self.link_gid[l]] for l in self.fa if self.link_gid.get(l) in self.row_of_gid}

    def s(self, field, r):
        return self.db.get_string(B, field, r)

    def g(self, field, r):
        return self.db.get(B, field, r)

    def name(self, r):
        return f"{self.s('firstname', r)} {self.s('lastname', r)}".strip()

    def birth(self, r):
        return (self.g('year', r) + 1900, self.g('month', r) + 1, self.g('day', r) + 1)

    def is_goalie(self, r):
        return self.g('position', r) == 4

    def created_slot(self, r):
        """Пустые строки под создаваемых игроков (связи 16000+, без имени)."""
        return not self.s('lastname', r) or any(l in self.link_created for l in self.links_of[self.gid[r]])

    def ai(self, r):
        return self.ai_row.get(self.gid[r])

    def overall(self, r):
        t, row = self.ai(r)
        return self.db.get(t, 'p_overall' if t == S else 'g_overall', row) + 36

    def team_name(self, t):
        return self.db.get_string(T, 'fullname', t)
