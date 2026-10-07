"""Звенья команды: все 71 однобитное место exhibitionrostertable — по рейтингу и амплуа (build)
или по реальным сочетаниям с достройкой по рейтингу (build_real).

build — перенос `legacy_roster/lines.py` из puckpeak-nhl-legacy-rosters (MIT License, Copyright (c) 2026
Matus Riedl, github.com/MatusRiedl/puckpeak-nhl-legacy-rosters) на простые словари. Правила — как у каждой команды НХЛ исходной базы NHL 13 (проверено):
- одеты 20: 12 нападающих в четырёх тройках, 6 защитников в трёх парах, 2 вратаря;
- у каждого места ровно один владелец, места спецбригад — только у одетых;
- никто не стоит дважды в одной группе (пятёрки большинства, четвёрки меньшинства…);
- амплуа по местам (исходная база, 30 клубов): в тройках только нападающие (C/LW/RW — любые),
  в парах и на местах защитников меньшинства — только защитники, на «синей линии» большинства
  бывает и нападающий (Овечкин в pp1ld «Вашингтона»), вратари — только g1/g2.

Игрок — словарь: `key` (любой уникальный), `pos` (C/L/R/D/G), `ovr`, `shoots` (L/R) и
`attrs` (поля p_* в шкале рейтинга) для оценок атаки, обороны и буллитов; для build_real ещё
`out` — травмирован или его нет в /roster/current (в достройку — в последнюю очередь).
"""
OFFENCE = ('p_offawareness', 'p_passing', 'p_puckcontrol', 'p_deking', 'p_wristaccuracy')
DEFENCE = ('p_defawareness', 'p_stickchecking', 'p_shotblocking')
SHOOTOUT = ('p_deking', 'p_wristaccuracy', 'p_puckcontrol')
FACEOFF = ('p_faceoffs',)
FORWARD = ('C', 'L', 'R')
# группы мест, внутри которых игрок не повторяется
GROUPS = ([[f'l{n}{p}' for p in ('lw', 'c', 'rw', 'ld', 'rd')] for n in (1, 2, 3)] + [['l4lw', 'l4c', 'l4rw']]
          + [[f'pp{n}{p}' for p in ('lw', 'c', 'rw', 'ld', 'rd')] for n in (1, 2)]
          + [[f'{g}_{n}{p}' for p in ('lw', 'c', 'ld', 'rd')] for g in ('pp4', 'pk4', 'ot') for n in (1, 2, 3)
             if not (g != 'ot' and n == 3)]
          + [[f'pk3_{n}{p}' for p in ('c', 'ld', 'rd')] for n in (1, 2)]
          + [[f's{n}' for n in range(1, 6)], ['x1', 'x2'], ['g1', 'g2']])


class NotEnoughPlayers(Exception):
    pass


def slot_kind(slot):
    """Кто может стоять на месте: 'G' — вратарь, 'D' — защитник, 'F' — нападающий, None — любой
    полевой («синяя линия» большинства)."""
    if slot in ('g1', 'g2'):
        return 'G'
    if slot.endswith(('ld', 'rd')):
        return None if slot.startswith('pp') else 'D'
    return 'F'


def _score(fields):
    def f(p):
        vals = [p['attrs'][n] for n in fields if p.get('attrs', {}).get(n) is not None]
        return sum(vals) / len(vals) if vals else p['ovr']
    return f


OFF, DFN, SHO, FO = _score(OFFENCE), _score(DEFENCE), _score(SHOOTOUT), _score(FACEOFF)


def by_q(group):
    return sorted(group, key=lambda p: (-p['ovr'], str(p['key'])))


def best(group, key):
    return sorted(group, key=lambda p: (-key(p), -p['ovr'], str(p['key'])))


def sides(x, y):
    """Каждый крайний — на свою сторону, если можно."""
    if (x['pos'] == 'R' and y['pos'] != 'R') or (y['pos'] == 'L' and x['pos'] != 'L'):
        return y, x
    return x, y


def dpair(x, y):
    """Правый хват — направо, если в паре один левый и один правый."""
    if x.get('shoots') == 'R' and y.get('shoots') == 'L':
        return y, x
    return x, y


def _tail(slots, f12, centres, dpairs):
    """Овертайм (центр, лучший в атаке из остальных нападающих и пара), буллиты, лишние — по
    рейтингу из одетых."""
    ot_w = best([p for p in f12 if p not in centres[:3]], OFF)[:3]
    for k in range(3):
        slots[f'ot_{k + 1}lw'], slots[f'ot_{k + 1}c'] = ot_w[k], centres[k]
        slots[f'ot_{k + 1}ld'], slots[f'ot_{k + 1}rd'] = dpairs[k]
    for k, p in enumerate(best(f12, SHO)[:5]):
        slots[f's{k + 1}'] = p
    slots['x1'], slots['x2'] = by_q(f12)[:2]


def check(slots):
    """Все 71 место заняты, в группе мест игрок не повторяется."""
    for g in GROUPS:
        keys = [slots[s]['key'] for s in g]
        if len(set(keys)) != len(keys):
            raise AssertionError(f'повтор в группе {g[0]}…: {keys}')


def build(players):
    """{место: key} для всех 71 мест и множество одетых."""
    goalies = by_q(p for p in players if p['pos'] == 'G')
    defence = by_q(p for p in players if p['pos'] == 'D')
    forwards = by_q(p for p in players if p['pos'] in FORWARD)
    if len(goalies) < 2 or len(defence) + len(forwards) < 18:
        raise NotEnoughPlayers(f'{len(goalies)} вратарей, {len(defence)} защитников, {len(forwards)} нападающих')
    while len(defence) < 6:          # не хватает защитников — играет лишний нападающий, и наоборот
        defence.append(forwards.pop())
    while len(forwards) < 12:
        forwards.append(defence.pop())
    d6, f12 = defence[:6], forwards[:12]
    centres = [p for p in f12 if p['pos'] == 'C'][:4]
    wings = [p for p in f12 if p not in centres]
    while len(centres) < 4:          # мало центров: центром играет лучший из оставшихся
        centres.append(wings.pop(0))
    centres = by_q(centres)
    left = by_q(p for p in wings if p['pos'] == 'L')
    right = by_q(p for p in wings if p['pos'] == 'R')
    rest = by_q(p for p in wings if p['pos'] not in ('L', 'R'))
    pairs = []
    for _ in range(4):               # k-й лучший левый с k-м лучшим правым; не хватает — лучший из прочих
        lw = (left or rest or right).pop(0)
        rw = (right or rest or left).pop(0)
        pairs.append((lw, rw))

    slots = {}
    for k, (lw, rw) in enumerate(pairs):
        slots[f'l{k + 1}lw'], slots[f'l{k + 1}c'], slots[f'l{k + 1}rw'] = lw, centres[k], rw
    dpairs = [dpair(d6[2 * k], d6[2 * k + 1]) for k in range(3)]
    for k, (ld, rd) in enumerate(dpairs):
        slots[f'l{k + 1}ld'], slots[f'l{k + 1}rd'] = ld, rd
    slots['g1'], slots['g2'] = goalies[0], goalies[1]
    # большинство: два самых опасных центра и четыре нападающих, четыре защитника
    pp_c = best(centres, OFF)[:2]
    pp_w = best([p for p in f12 if p not in pp_c], OFF)[:4]
    pp_d = best(d6, OFF)[:4]
    for k in range(2):
        lw, rw = sides(pp_w[2 * k], pp_w[2 * k + 1])
        ld, rd = dpair(pp_d[2 * k], pp_d[2 * k + 1])
        slots[f'pp{k + 1}lw'], slots[f'pp{k + 1}c'], slots[f'pp{k + 1}rw'] = lw, pp_c[k], rw
        slots[f'pp{k + 1}ld'], slots[f'pp{k + 1}rd'] = ld, rd
        slots[f'pp4_{k + 1}lw'], slots[f'pp4_{k + 1}c'] = pp_w[2 * k], pp_c[k]
        slots[f'pp4_{k + 1}ld'], slots[f'pp4_{k + 1}rd'] = ld, rd
    # меньшинство: лучшие в обороне центры, нападающие и пары
    pk_c = best(centres, DFN)[:2]
    pk_w = best([p for p in f12 if p not in pk_c], DFN)[:2]
    pk_d = best(d6, DFN)[:4]
    for k in range(2):
        ld, rd = dpair(pk_d[2 * k], pk_d[2 * k + 1])
        slots[f'pk4_{k + 1}lw'], slots[f'pk4_{k + 1}c'] = pk_w[k], pk_c[k]
        slots[f'pk4_{k + 1}ld'], slots[f'pk4_{k + 1}rd'] = ld, rd
        slots[f'pk3_{k + 1}c'], slots[f'pk3_{k + 1}ld'], slots[f'pk3_{k + 1}rd'] = pk_c[k], ld, rd
    _tail(slots, f12, centres, dpairs)
    keys = {name: p['key'] for name, p in slots.items()}
    dressed = {p['key'] for p in d6 + f12 + goalies[:2]}
    return keys, dressed


# --- реальные сочетания -------------------------------------------------------------------------
MIN_REAL = 12          # меньше стольких игроков источника в тройках, парах и у ворот — источник не берём


def real_count(players, real):
    """Сколько мест троек, пар и вратарей источник даёт игроками этого клуба."""
    keys = {p['key'] for p in players}
    ev = ([k for line in real.get('f') or [] for k in line] + [k for pair in real.get('d') or [] for k in pair]
          + list(real.get('g') or []))
    return sum(1 for k in ev if k in keys)


def build_real(players, real):
    """Звенья по реальным сочетаниям: {место: key}, одетые и что достроено.

    `real` — из lines.json (lines_real.py): `f` — 4 тройки [lw, c, rw], `d` — 3 пары [ld, rd],
    `g` — [g1, g2], `pp` — 2 пятёрки (sk1–sk3 — первый ряд, sk4–sk5 — «синяя линия»), `pk` — 2
    четвёрки (sk1–sk2 — нападающие, sk3–sk4 — защитники), `injured` — травмированные; вместо
    игрока, которого в клубе нет, — None.

    1. Тройки, пары, вратари — как в источнике. Место без игрока клуба, второе появление того же
       игрока или чужое амплуа (защитник в тройке, нападающий в паре, вратарь не у ворот) —
       достраивается по рейтингу: лучший по OVR из неодетых своего амплуа (в тройке — нападающий,
       на месте центра — сначала центр; в паре — защитник), здоровые раньше травмированных и
       тех, кого нет в /roster/current. Седьмой защитник источника (d4) не одевается: в NHL 13
       одеты 12 нападающих и 6 защитников, его место в 4-й тройке — нападающему по рейтингу.
    2. Большинство и меньшинство — игроки источника из одетых; в первом ряду — только нападающие,
       в заднем ряду меньшинства — только защитники, на «синей линии» большинства — любой полевой
       (как в исходной базе). Пропуск (игрока нет в клубе, не одет, чужое амплуа) — лучший в атаке
       (большинство) или обороне (меньшинство) из одетых, кого в этой пятёрке нет: сначала не из
       другой пятёрки, в первый ряд — нападающий, назад — защитник. Центр — тот, кто центр в
       одной из троек (потом центр по амплуа, потом лучшее вбрасывание), крайние — по своим
       сторонам, задний ряд — по хвату. 4 на 3 (pp4_*) — центр, лучший в атаке крайний и
       «синяя линия» своей пятёрки; 3 на 5 (pk3_*) — центр и пара своей четвёрки меньшинства.
    3. Овертайм, буллиты, лишние — по рейтингу из одетых (как build).
    """
    by_key = {p['key']: p for p in players}
    injured = set(real.get('injured') or [])
    late = lambda p: bool(p.get('out')) or p['key'] in injured
    filled, dropped = [], []
    used = set()
    is_f = lambda p: p['pos'] in FORWARD
    is_d = lambda p: p['pos'] == 'D'
    is_g = lambda p: p['pos'] == 'G'

    def take(k, ok, where):
        p = by_key.get(k)
        if k is None or p is None:
            return None
        if p['key'] in used:
            dropped.append((k, where, 'уже стоит в другом звене источника'))
            return None
        if not ok(p):
            dropped.append((k, where, f"амплуа {p['pos']} не для этого места"))
            return None
        used.add(p['key'])
        return p

    pad = lambda rows, n, m: [((list(rows[i]) if i < len(rows) else []) + [None] * m)[:m] for i in range(n)]
    F = [[take(k, is_f, f'f{n + 1}') for k in line] for n, line in enumerate(pad(real.get('f') or [], 4, 3))]
    D = [[take(k, is_d, f'd{n + 1}') for k in pair] for n, pair in enumerate(pad(real.get('d') or [], 3, 2))]
    Gl = [take(k, is_g, 'g') for k in pad([real.get('g') or []], 1, 2)[0]]
    for k in real.get('extra_d') or []:
        if k in by_key and k not in used:
            dropped.append((k, 'd4', 'седьмой защитник: в NHL 13 одеты 12 нападающих и 6 защитников'))

    def fill(slot):
        """Лучший по OVR неодетый для места: сначала своего амплуа (в тройке — нападающий, на
        месте центра — центр; в паре — защитник), здоровые раньше травмированных."""
        goalie = slot in ('g1', 'g2')
        pool = [p for p in players if p['key'] not in used and is_g(p) == goalie]
        if not pool:
            raise NotEnoughPlayers(f'некого поставить на место {slot}')
        if slot in ('ld', 'rd'):
            rank = lambda p: (not is_d(p), late(p), -p['ovr'], str(p['key']))
        elif goalie:
            rank = lambda p: (late(p), -p['ovr'], str(p['key']))
        else:
            rank = lambda p: (not is_f(p), late(p), slot == 'c' and p['pos'] != 'C', -p['ovr'], str(p['key']))
        p = min(pool, key=rank)
        used.add(p['key'])
        return p

    for n, line in enumerate(F):
        for i, s in enumerate(('lw', 'c', 'rw')):
            if line[i] is None:
                line[i] = fill(s)
                filled.append((f'l{n + 1}{s}', line[i]['key']))
    for n, pair in enumerate(D):
        for i, s in enumerate(('ld', 'rd')):
            if pair[i] is None:
                pair[i] = fill(s)
                filled.append((f'l{n + 1}{s}', pair[i]['key']))
    for i, s in enumerate(('g1', 'g2')):
        if Gl[i] is None:
            Gl[i] = fill(s)
            filled.append((s, Gl[i]['key']))

    slots = {}
    for n, (lw, c, rw) in enumerate(F):
        slots[f'l{n + 1}lw'], slots[f'l{n + 1}c'], slots[f'l{n + 1}rw'] = lw, c, rw
    for n, (ld, rd) in enumerate(D):
        slots[f'l{n + 1}ld'], slots[f'l{n + 1}rd'] = ld, rd
    slots['g1'], slots['g2'] = Gl
    f12 = [p for line in F for p in line]
    d6 = [p for pair in D for p in pair]
    skaters = f12 + d6
    on = {p['key'] for p in skaters}

    def unit(keys, size, front, score, where, other, back_d):
        """Спецбригада источника из одетых; пропуски — по рейтингу. Первый ряд — только
        нападающие, задний (back_d) — только защитники. → (первый ряд, задний ряд)."""
        need = lambda i: is_f if i < front else (is_d if back_d else None)
        members = []
        for i in range(size):
            k = keys[i] if i < len(keys) else None
            p = by_key.get(k) if k is not None else None
            if p is not None:
                why = ('не одет' if p['key'] not in on else 'дважды в пятёрке' if p in members
                       else f"амплуа {p['pos']} не для {'первого' if i < front else 'заднего'} ряда"
                       if need(i) and not need(i)(p) else None)
                if why:
                    dropped.append((k, where, why))
                    p = None
            members.append(p)
        for i, p in enumerate(members):
            if p is None:
                cand = [q for q in skaters if q not in members]
                cand = [q for q in cand if need(i)(q)] if need(i) and any(need(i)(q) for q in cand) else cand
                want_d = i >= front
                q = min(cand, key=lambda q: (q['key'] in other, is_d(q) != want_d, -score(q), -q['ovr'], str(q['key'])))
                members[i] = q
                filled.append((f'{where} sk{i + 1}', q['key']))
        return members[:front], members[front:]

    ev_c = {line[1]['key'] for line in F}

    def centre(group):
        """Центр спецбригады: центр одной из троек, потом центр по амплуа, потом лучшее вбрасывание."""
        c = min(group, key=lambda p: (p['key'] not in ev_c, p['pos'] != 'C', -FO(p), -p['ovr'], str(p['key'])))
        return c, [p for p in group if p is not c]

    def others(kind, n, built):
        """Игроки другой пятёрки (четвёрки): по источнику и уже собранные — замену берём не оттуда."""
        src = [k for i, u in enumerate(real.get(kind) or []) if i != n for k in u if k is not None]
        return set(src) | {q['key'] for u in built for row in u for q in row}

    pp_units = []
    for n in range(2):
        keys = real['pp'][n] if n < len(real.get('pp') or []) else []
        front, back = unit(keys, 5, 3, OFF, f'pp{n + 1}', others('pp', n, pp_units), back_d=False)
        pp_units.append((front, back))
        c, wings = centre(front)
        lw, rw = sides(*wings)
        ld, rd = dpair(*back)
        slots[f'pp{n + 1}lw'], slots[f'pp{n + 1}c'], slots[f'pp{n + 1}rw'] = lw, c, rw
        slots[f'pp{n + 1}ld'], slots[f'pp{n + 1}rd'] = ld, rd
        slots[f'pp4_{n + 1}lw'], slots[f'pp4_{n + 1}c'] = best([lw, rw], OFF)[0], c
        slots[f'pp4_{n + 1}ld'], slots[f'pp4_{n + 1}rd'] = ld, rd
    pk_units = []
    for n in range(2):
        keys = real['pk'][n] if n < len(real.get('pk') or []) else []
        front, back = unit(keys, 4, 2, DFN, f'pk{n + 1}', others('pk', n, pk_units), back_d=True)
        pk_units.append((front, back))
        c, (lw,) = centre(front)
        ld, rd = dpair(*back)
        slots[f'pk4_{n + 1}lw'], slots[f'pk4_{n + 1}c'] = lw, c
        slots[f'pk4_{n + 1}ld'], slots[f'pk4_{n + 1}rd'] = ld, rd
        slots[f'pk3_{n + 1}c'], slots[f'pk3_{n + 1}ld'], slots[f'pk3_{n + 1}rd'] = c, ld, rd
    centres = [line[1] for line in F]
    dpairs = [tuple(pair) for pair in D]
    _tail(slots, f12, centres, dpairs)
    check(slots)
    keys = {name: p['key'] for name, p in slots.items()}
    dressed = {p['key'] for p in skaters + Gl}
    assert len(dressed) == 20 and set(keys.values()) == dressed
    return keys, dressed, {'filled': filled, 'dropped': dropped}
