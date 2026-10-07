"""Этап lines: реальные сочетания звеньев 2026/27 (DailyFaceoff) → game/work/roster/lines.json.

Источник — dailyfaceoff.com/teams/{slug}/line-combinations (fetch --only dfo; разбор —
sources.dfo_lines): 4 тройки, 3 пары (у части клубов седьмой защитник — группа d4), 2 вратаря,
PP1/PP2 (по 5 полевых без мест: sk1–sk3 — первый ряд, sk4–sk5 — «синяя линия»), PK1/PK2 (по 4:
sk1–sk2 — нападающие, sk3–sk4 — защитники), травмированные (ir).

Игрок источника ищется только в своём клубе players.json (вратарь — среди вратарей, полевой —
среди полевых; суффиксы Jr./Sr./II/III у имени источника не учитываются):
1. имя и фамилия (common.norm); у тёзок в клубе на каждом шаге решают номер, потом амплуа
   (тройка — нападающий, пара — защитник);
2. та же фамилия и то же имя в другой форме (build.same_first: Alex — Alexander, Zack —
   Zachary) или тот же номер;
3. тот же номер и похожая фамилия (≥ 0,8) — другое написание фамилии;
4. та же фамилия и первая буква имени при амплуа как в звене (Jacob — Jake Middleton).
Кто не нашёлся — в `unmatched` с причиной (в составе другого клуба конвейера или нет в составах
НХЛ); его место — null, write достроит такое место по рейтингу (lines.build_real). Кто нашёлся
не по точному имени — в `fuzzy` (для отчёта).
"""
import datetime
import time
from difflib import SequenceMatcher

from . import sources
from .build import same_first
from .common import TEAM_NAMES, norm, read_json, write_json

F_SLOTS, D_SLOTS, G_SLOTS = ('lw', 'c', 'rw'), ('ld', 'rd'), ('g1', 'g2')
GROUP_NAME = {'f1': '1-я тройка', 'f2': '2-я тройка', 'f3': '3-я тройка', 'f4': '4-я тройка', 'd1': '1-я пара',
              'd2': '2-я пара', 'd3': '3-я пара', 'd4': '7-й защитник', 'g': 'вратари', 'pp1': 'PP1', 'pp2': 'PP2',
              'pk1': 'PK1', 'pk2': 'PK2', 'ir': 'травмированные'}
SUFFIXES = {'jr', 'sr', 'ii', 'iii', 'iv'}
STALE_DAYS = 30        # страница старше — предупреждение (межсезонье: звенья прошлого сезона)
HOW = [None, 'та же фамилия, имя в другой форме или тот же номер', 'тот же номер, похожая фамилия',
       'та же фамилия и первая буква имени']


def full(p):
    return norm(p['first'] + p['last'])


def age_days(iso):
    """Сколько дней назад обновлена страница ('2026-10-06T15:36:43.017Z')."""
    try:
        when = datetime.datetime.fromisoformat(iso.replace('Z', '+00:00'))
    except (AttributeError, ValueError):
        return None
    return (datetime.datetime.now(datetime.timezone.utc) - when).days


def find(team_players, q, group, everyone):
    """(nhl_id, None, как) для записи источника или (None, причина, None)."""
    goalie = group == 'g'
    kind = [p for p in team_players if (p['pos'] == 'G') == goalie]
    words = q['name'].split()
    while len(words) > 2 and norm(words[-1]) in SUFFIXES:
        words = words[:-1]
    name, num = norm(' '.join(words)), q.get('num')
    last = norm(words[-1]) if words else ''
    has_last = lambda p: norm(p['last']) and name.endswith(norm(p['last']))
    first_of = lambda p: name[:len(name) - len(norm(p['last']))]
    steps = [
        lambda p: full(p) == name,
        # имя в другой форме (Alex — Alexander) или тот же номер при той же фамилии
        lambda p: has_last(p) and (same_first(p['first'], first_of(p)) or (num and p.get('num') == num)),
        # фамилия в другом написании: тот же номер и похожая фамилия
        lambda p: num and p.get('num') == num and SequenceMatcher(None, norm(p['last']), last).ratio() >= 0.8,
        # уменьшительное имя (Jacob — Jake): та же фамилия и первая буква имени, амплуа как в звене
        lambda p: (has_last(p) and first_of(p)[:1] == norm(p['first'])[:1]
                   and (group[:1] not in ('f', 'd') or (p['pos'] == 'D') == (group[:1] == 'd'))),
    ]
    for k, step in enumerate(steps):
        cands = [p for p in kind if step(p)]
        if len(cands) > 1 and num:          # тёзки в клубе: номер, потом амплуа (тройка или пара)
            cands = [p for p in cands if p.get('num') == num] or cands
        if len(cands) > 1 and group[:1] in ('f', 'd'):
            cands = [p for p in cands if (p['pos'] == 'D') == (group[:1] == 'd')] or cands
        if len(cands) == 1:
            return cands[0]['nhl_id'], None, HOW[k]
        if cands:
            return None, 'неоднозначно: ' + ', '.join(f"{p['first']} {p['last']} #{p.get('num')}" for p in cands), None
    elsewhere = sorted({p['team'] for p in everyone if full(p) == name and (p['pos'] == 'G') == goalie})
    if elsewhere:
        return None, f"в конвейере — в составе {'/'.join(elsewhere)}", None
    return None, 'нет в составах НХЛ конвейера (API НХЛ его в клубе не числит)', None


def team_lines(src, tp, everyone):
    groups = src['groups']
    out = {'updated': src.get('updated'), 'source': src.get('source'), 'source_url': src.get('source_url'),
           'f': [], 'd': [], 'extra_d': [], 'g': [], 'pp': [], 'pk': [], 'injured': [], 'unmatched': [], 'fuzzy': [],
           'empty': []}
    missed, fuzzy = {}, {}
    names = {p['nhl_id']: f"{p['first']} {p['last']}" for p in tp}

    def one(group, q):
        pid, why, how = find(tp, q, group, everyone)
        if pid is None:
            m = missed.setdefault(norm(q['name']), {'name': q['name'], 'num': q.get('num'), 'groups': [], 'why': why})
            m['groups'].append(group)
        elif how:
            fuzzy.setdefault(pid, {'name': q['name'], 'nhl_id': pid, 'player': names[pid], 'how': how})
        return pid

    def by_slot(group, slots):
        qs = {q['slot']: q for q in groups.get(group, [])}
        row = []
        for s in slots:
            if s in qs:
                row.append(one(group, qs[s]))
            else:
                row.append(None)
                out['empty'].append(f'{group} {s}')
        return row

    out['f'] = [by_slot(f'f{k}', F_SLOTS) for k in (1, 2, 3, 4)]
    out['d'] = [by_slot(f'd{k}', D_SLOTS) for k in (1, 2, 3)]
    out['extra_d'] = [x for x in (one('d4', q) for q in groups.get('d4', [])) if x is not None]
    out['g'] = by_slot('g', G_SLOTS)
    order = lambda qs: sorted(qs, key=lambda q: q.get('slot') or '')
    out['pp'] = [[one(f'pp{k}', q) for q in order(groups.get(f'pp{k}', []))] for k in (1, 2)]
    out['pk'] = [[one(f'pk{k}', q) for q in order(groups.get(f'pk{k}', []))] for k in (1, 2)]
    for q in groups.get('ir', []):
        pid = find(tp, q, 'ir', everyone)[0]
        if pid is None:     # травмированный может быть и вратарём
            pid = find(tp, q, 'g', everyone)[0]
        out['injured'].append({'name': q['name'], 'injury': q.get('injury'), 'nhl_id': pid})
    out['unmatched'], out['fuzzy'] = list(missed.values()), list(fuzzy.values())
    return out


def run(paths, log=print):
    data = read_json(paths.players)
    if not data:
        raise SystemExit(f'нет {paths.players} — сначала build')
    everyone = data['players']
    src = sources.dfo_lines(paths.cache)
    teams, missing = {}, []
    for abbr in TEAM_NAMES:
        if abbr not in src:
            missing.append(abbr)
            continue
        if src[abbr].get('abbr') and src[abbr]['abbr'] != abbr:
            log(f"  lines: на странице {abbr} клуб {src[abbr]['abbr']} — пропущен")
            missing.append(abbr)
            continue
        tp = [p for p in everyone if p['team'] == abbr]
        teams[abbr] = team_lines(src[abbr], tp, everyone)
        days = age_days(src[abbr].get('updated'))
        if days is not None and days > STALE_DAYS:
            teams[abbr]['stale'] = True
            log(f"  lines: {abbr} — страница обновлена {days} дн. назад ({src[abbr]['updated'][:10]}): звенья могут быть "
                'прошлого сезона')
    out = {'source': 'dailyfaceoff.com/teams/{slug}/line-combinations', 'generated': time.strftime('%Y-%m-%d %H:%M:%S'),
           'teams': teams, 'missing': missing}
    write_json(paths.lines, out)
    n_un = sum(len(t['unmatched']) for t in teams.values())
    log(f'lines: звенья DailyFaceoff — {len(teams)} клубов из 32 (нет: {", ".join(missing) or "—"}); '
        f'не сопоставлено игроков {n_un} -> {paths.lines}')
    return out
