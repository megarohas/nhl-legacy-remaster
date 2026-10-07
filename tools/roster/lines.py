"""Звенья команды по рейтингу и амплуа: все 71 однобитных места exhibitionrostertable.

Перенос `legacy_roster/lines.py` из puckpeak-nhl-legacy-rosters (MIT License, Copyright (c) 2026
Matus Riedl, github.com/MatusRiedl/puckpeak-nhl-legacy-rosters) на простые словари. Правила — как у каждой команды НХЛ исходной базы NHL 13 (проверено):
- одеты 20: 12 нападающих в четырёх тройках, 6 защитников в трёх парах, 2 вратаря;
- у каждого места ровно один владелец, места спецбригад — только у одетых;
- никто не стоит дважды в одной группе (пятёрки большинства, четвёрки меньшинства…).

Игрок — словарь: `key` (любой уникальный), `pos` (C/L/R/D/G), `ovr`, `shoots` (L/R) и
`attrs` (поля p_* в шкале рейтинга) для оценок атаки, обороны и буллитов.
"""
OFFENCE = ('p_offawareness', 'p_passing', 'p_puckcontrol', 'p_deking', 'p_wristaccuracy')
DEFENCE = ('p_defawareness', 'p_stickchecking', 'p_shotblocking')
SHOOTOUT = ('p_deking', 'p_wristaccuracy', 'p_puckcontrol')


class NotEnoughPlayers(Exception):
    pass


def _score(fields):
    def f(p):
        vals = [p['attrs'][n] for n in fields if p.get('attrs', {}).get(n) is not None]
        return sum(vals) / len(vals) if vals else p['ovr']
    return f


def build(players):
    """{место: key} для всех 71 мест и множество одетых."""
    by_q = lambda group: sorted(group, key=lambda p: (-p['ovr'], str(p['key'])))
    goalies = by_q(p for p in players if p['pos'] == 'G')
    defence = by_q(p for p in players if p['pos'] == 'D')
    forwards = by_q(p for p in players if p['pos'] in ('C', 'L', 'R'))
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

    def sides(x, y):                 # каждый крайний — на свою сторону, если можно
        if (x['pos'] == 'R' and y['pos'] != 'R') or (y['pos'] == 'L' and x['pos'] != 'L'):
            return y, x
        return x, y

    def dpair(x, y):                 # правый хват — направо, если в паре один левый и один правый
        if x.get('shoots') == 'R' and y.get('shoots') == 'L':
            return y, x
        return x, y

    off, dfn, sho = _score(OFFENCE), _score(DEFENCE), _score(SHOOTOUT)
    best = lambda group, key: sorted(group, key=lambda p: (-key(p), -p['ovr'], str(p['key'])))
    slots = {}
    for k, (lw, rw) in enumerate(pairs):
        slots[f'l{k + 1}lw'], slots[f'l{k + 1}c'], slots[f'l{k + 1}rw'] = lw, centres[k], rw
    dpairs = [dpair(d6[2 * k], d6[2 * k + 1]) for k in range(3)]
    for k, (ld, rd) in enumerate(dpairs):
        slots[f'l{k + 1}ld'], slots[f'l{k + 1}rd'] = ld, rd
    slots['g1'], slots['g2'] = goalies[0], goalies[1]
    # большинство: два самых опасных центра и четыре нападающих, четыре защитника
    pp_c = best(centres, off)[:2]
    pp_w = best([p for p in f12 if p not in pp_c], off)[:4]
    pp_d = best(d6, off)[:4]
    for k in range(2):
        lw, rw = sides(pp_w[2 * k], pp_w[2 * k + 1])
        ld, rd = dpair(pp_d[2 * k], pp_d[2 * k + 1])
        slots[f'pp{k + 1}lw'], slots[f'pp{k + 1}c'], slots[f'pp{k + 1}rw'] = lw, pp_c[k], rw
        slots[f'pp{k + 1}ld'], slots[f'pp{k + 1}rd'] = ld, rd
        slots[f'pp4_{k + 1}lw'], slots[f'pp4_{k + 1}c'] = pp_w[2 * k], pp_c[k]
        slots[f'pp4_{k + 1}ld'], slots[f'pp4_{k + 1}rd'] = ld, rd
    # меньшинство: лучшие в обороне центры, нападающие и пары
    pk_c = best(centres, dfn)[:2]
    pk_w = best([p for p in f12 if p not in pk_c], dfn)[:2]
    pk_d = best(d6, dfn)[:4]
    for k in range(2):
        ld, rd = dpair(pk_d[2 * k], pk_d[2 * k + 1])
        slots[f'pk4_{k + 1}lw'], slots[f'pk4_{k + 1}c'] = pk_w[k], pk_c[k]
        slots[f'pk4_{k + 1}ld'], slots[f'pk4_{k + 1}rd'] = ld, rd
        slots[f'pk3_{k + 1}c'], slots[f'pk3_{k + 1}ld'], slots[f'pk3_{k + 1}rd'] = pk_c[k], ld, rd
    # овертайм: три четвёрки — центр, лучший из остальных нападающих и пара
    ot_w = best([p for p in f12 if p not in centres[:3]], off)[:3]
    for k in range(3):
        slots[f'ot_{k + 1}lw'], slots[f'ot_{k + 1}c'] = ot_w[k], centres[k]
        slots[f'ot_{k + 1}ld'], slots[f'ot_{k + 1}rd'] = dpairs[k]
    for k, p in enumerate(best(f12, sho)[:5]):
        slots[f's{k + 1}'] = p
    slots['x1'], slots['x2'] = by_q(f12)[:2]
    keys = {name: p['key'] for name, p in slots.items()}
    dressed = {p['key'] for p in d6 + f12 + goalies[:2]}
    return keys, dressed
