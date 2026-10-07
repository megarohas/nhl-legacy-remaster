"""Этап report: players.json + match.json + write.json → game/work/roster/report.md;
lines.json + write.json + выходная база → report-lines.md.

report.md — что сопоставилось и как, кто новый (в чьей строке), кому не хватило места, какие
поля не заполнены или заполнены заглушкой, что стало с ушедшими из НХЛ игроками 2012 года.
report-lines.md — звенья 32 клубов так, как они записаны в базе (имена и OVR из базы), откуда
они (DailyFaceoff или рейтинг), что из источника не сопоставилось и что достроено по рейтингу.
"""
import os
import time
from collections import Counter, defaultdict

from .common import SLOT_TEAM, TEAM_NAMES, read_json
from .dbview import FLAGS, NHL, View
from .lines_real import GROUP_NAME as GROUP

HOW = {'artid': 'artid = ID EA', 'birth': 'фамилия + дата рождения', 'name': 'имя + почти та же дата',
       'birth+similar': 'дата рождения + похожая фамилия'}
SRC = {'ea': 'EA NHL 27 (все атрибуты)', 'nhlratings': 'nhlratings.net (атрибуты)',
       'nhlratings-ovr': 'nhlratings.net (только OVR, атрибуты достроены)', 'ea-ovr': 'EA (только OVR)',
       'none': 'нет — оценка по амплуа и возрасту'}
STYLE = {1: 'оборонец', 2: 'атакующий защитник', 3: 'силовой защитник', 4: 'универсал', 5: 'работяга',
         6: 'плеймейкер', 7: 'снайпер', 8: 'силовой нападающий', 9: 'двусторонний', 10: 'тафгай'}


def _fmt_birth(b):
    return f'{b[0]}-{b[1]:02}-{b[2]:02}' if b else '—'


def run(paths, log=print):
    data, mt, wr = read_json(paths.players), read_json(paths.matched), read_json(paths.written)
    if not (data and mt and wr):
        raise SystemExit('нет players.json, match.json или write.json — сначала build, match, write')
    meta, players = data['meta'], {p['nhl_id']: p for p in data['players']}
    out = {o['nhl_id']: o for o in wr['players']}
    L = []
    add = L.append
    c = meta['counts']
    n_new = sum(1 for o in out.values() if o['new'])
    n_match = len(out) - n_new
    add('# Составы НХЛ 2026/27 → nhlng.db: отчёт')
    add('')
    add(f"Собрано {time.strftime('%d.%m.%Y %H:%M')} (`python tools/roster all`; данные — снимок {meta['generated']}).")
    add('')
    add(f"- Вход: `{wr['db_in']}`; выход: `{wr['db_out']}` (CRC пересчитаны, `tools/tdb.py verify` — OK).")
    add(f"- Игроков в составах 32 клубов: **{c['players']}** (`/v1/roster/{{TEAM}}/current` — "
        f"{c['players'] - c.get('omitted_added', 0)}, вне его, с клубом НХЛ — {c.get('omitted_added', 0)}).")
    add(f'- Сопоставлено с игроками базы: **{n_match}**; новых (в строках доноров): **{n_new}**; '
        f"без места: **{len(wr['no_room'])}**.")
    add(f"- Записей составов: {wr['rows']['roster']}, свободных агентов: {wr['rows']['free_agents']}, "
        f"связей exhibitionplayers: {wr['rows']['links']} (новых {len(wr['new_links'])}).")
    probs = wr['problems']
    add(f"- Проверки записи: {'OK' if not probs else f'{len(probs)} проблем (ниже)'}.")
    add('')
    add('## Источники')
    add('')
    add('| Источник | Что взято | Сколько |')
    add('|---|---|---|')
    add(f"| api-web.nhle.com | составы, карточки (биография, драфт, игры по сезонам) | {c['players']} игроков, "
        f"без карточки {c['no_landing']} |")
    add('| api.nhle.com/stats/rest (bios) | гражданство | — |')
    add(f"| ea.com/games/nhl/ratings | топ-300 NHL 27: ID EA, OVR, 40 атрибутов | {c['ea_matched']} из {c['ea_top300']} "
        f'найдены в составах |')
    add(f"| nhlratings.net | OVR, у части атрибуты и стиль | {c['nhlratings_matched']} игроков составов "
        f"(страниц {c['nhlratings_pages']}) |")
    add(f"| Wikipedia (List of current NHL captains and alternate captains) | капитаны и ассистенты | "
        f"{c['letters_found']} букв, {c['captains_teams']} клубов |")
    info = wr.get('lines_info') or {}
    real = [a for a, i in info.items() if i['source'] != 'rating']
    ln = read_json(paths.lines) or {}
    n_un = sum(len(ln['teams'][a]['unmatched']) for a in real if a in (ln.get('teams') or {}))
    add(f'| dailyfaceoff.com (line-combinations) | звенья: 4 тройки, 3 пары, вратари, PP1/PP2, PK1/PK2 | '
        f'{len(real)} клубов из 32, не сопоставлено игроков {n_un} (подробно — report-lines.md) |')
    add('')
    add('## Сопоставление')
    add('')
    how = Counter(o['how'] for o in out.values() if not o['new'])
    for k, n in how.most_common():
        add(f'- {HOW.get(k, k)}: {n}')
    add('')
    src = Counter(o['rating_source'] for o in out.values())
    add('Рейтинги:')
    add('')
    for k, n in src.most_common():
        add(f'- {SRC.get(k, k)}: {n}')
    add('')
    tiers = Counter(o['donor']['tier'] for o in out.values() if o['new'])
    add('Строки доноров для новых игроков:')
    add('')
    for k, n in tiers.most_common():
        add(f'- {k}: {n}')
    ea_art = sum(1 for o in out.values() if o['new'] and (players[o['nhl_id']].get('ea') or {}).get('ea_id') == o['artid'])
    add('')
    add(f'artid новых: ID EA — у {ea_art}, свои из 9803–16383 — у {n_new - ea_art} '
        '(таблица `artid-registry.json`: NHL ID → artid, повторный прогон даёт те же номера).')
    add('')
    # --- команды
    add('## Команды')
    add('')
    add('| Слот | Клуб | Игроков (В/З/Н) | Сопост. | Новых | C | A | Лучшие по OVR |')
    add('|---|---|---|---|---|---|---|---|')
    by_team = defaultdict(list)
    for o in out.values():
        by_team[o['slot']].append(o)
    for slot in sorted(by_team):
        os_ = by_team[slot]
        pos = Counter('G' if o['pos'] == 'G' else 'D' if o['pos'] == 'D' else 'F' for o in os_)
        cap = ', '.join(o['name'] for o in os_ if o.get('letter') == 'C') or '—'
        alt = ', '.join(o['name'] for o in os_ if o.get('letter') == 'A')
        top = ', '.join(f"{o['name']} {o['ovr']}" for o in sorted(os_, key=lambda o: -o['ovr'])[:3])
        abbr = SLOT_TEAM[slot]
        add(f"| {slot} | {abbr} {TEAM_NAMES[abbr]} | {len(os_)} ({pos['G']}/{pos['D']}/{pos['F']}) | "
            f"{sum(not o['new'] for o in os_)} | {sum(o['new'] for o in os_)} | {cap} | {alt} | {top} |")
    add('')
    add('Слоты 30 и 31 в базе — бывшие Tappara и TPS (tools/nhl32.py): названия, эмблемы и формы Сиэтла и Вегаса —')
    add('следующий этап. Слот 22 — бывший Phoenix (Юта).')
    add('')
    # --- поля
    add('## Не заполнено или заглушка')
    add('')
    notes = Counter()
    for o in out.values():
        for n in o['notes']:
            if n.startswith('номер'):
                n = 'номера из API нет или он занят в клубе — выдан прежний или свободный'
            elif n.startswith('страна рождения'):
                n = 'страна рождения без кода в базе (127)'
            notes[n.split(' — ')[0] if n.startswith(('рейтинга нет', 'буква A')) else n] += 1
    add('- Контракты у всех игроков НХЛ — **заглушка** по OVR и возрасту (сумма 0,9–10 млн $, срок 1–4 года, '
        'yearufa, yearfirstsigned, yearwaivereligible — по сроку и драфту); настоящие — этап контрактов.')
    add('- Портреты, логотипы, формы — следующий этап: у новых игроков `hasportrait` = 0 (силуэт), типовая голова, '
        '`audioid` = 0 (комментатор не называет фамилию).')
    add('- Карьерная статистика (`stockcareer*`) у сопоставленных — по сезон 2011/12 включительно, сезонов 2012/13–2025/26 '
        f"нет; у строк доноров статистика прежних владельцев удалена: {wr['stats_removed']}.")
    add('- `juniorteam`/`juniorleague` у игроков НХЛ сброшены (0/1, как у ветеранов базы).')
    for k, n in notes.most_common():
        add(f'- {k}: {n}')
    vgk = [o for o in out.values() if o['slot'] == 31]
    add('')
    add(f"**Вегас (слот 31)**: `proteam` = 0 у всех {len(vgk)} игроков — номер команды + 1 = 32 не влезает в 5 бит "
        f"(у остальных клубов proteam = слот + 1). У задрафтованных Вегасом `draftteam` = 0 — "
        f"{sum(1 for o in out.values() if any('draftteam = 0 (Вегас' in n for n in o['notes']))} игроков.")
    add('')
    # --- особые составы и ушедшие
    add('## Что стало с игроками 2012 года')
    add('')
    ev = Counter(e['what'] for e in wr['events'])
    add(f"- Ушедших из НХЛ (их записи в составах НХЛ пересобраны): строки {tiers.get('ушедший из НХЛ', 0)} из них "
        'отданы новым игрокам;')
    add(f"- заняли места игроков, ушедших в НХЛ из клубов АХЛ/Европы/юниоров: {ev.get('место ушедшего в НХЛ', 0)} "
        f"(размеры и звенья этих команд не изменились); пустых мест: {ev.get('место осталось пустым', 0)};")
    add(f"- остались без клуба и контракта: {len(wr['teamless'])} (из них в сборных, Матче звёзд, легендах или "
        f"Зимней классике — {sum(1 for t in wr['teamless'] if t['special'])}: их записи там не тронуты, `team` = "
        'эта команда + 1, как у игроков сборных без клуба в исходной базе; у остальных `team` = 0).')
    add('- Сборные (128–148), Матч звёзд (86/87), проспекты (209/210), легенды и Team Ruggiero/Wickenheiser '
        '(211–213), Зимняя классика (214–217) — составы 2012 года; сопоставленные игроки в них обновлены вместе с '
        'основной записью (например, Кросби в сборной Канады). Обновление этих составов — следующие этапы.')
    add('')
    if wr['no_room']:
        add('## Без места')
        add('')
        for p in wr['no_room']:
            add(f"- {p['name']} ({p['team']}, {p['pos']}) — не хватило строк-доноров")
        add('')
    if probs:
        add('## Проблемы проверки')
        add('')
        for b in probs[:200]:
            add(f'- {b}')
        add('')
    if meta.get('omitted_added'):
        add('## Добавлены вне /roster/current (вероятно, травмированы)')
        add('')
        add('Состав API их не показывает; в поиске search.d3 у них клуб НХЛ, и либо 40+ игр в НХЛ в прошлом '
            'сезоне, либо они в топ-300 EA за этим клубом. Могут оказаться и отправленные в АХЛ.')
        add('')
        add(', '.join(meta['omitted_added']))
        add('')
    if meta.get('ea_unmatched'):
        add('## Топ-300 EA, которых нет в составах НХЛ')
        add('')
        for q in meta['ea_unmatched']:
            add(f"- {q['name']} ({q['team']}, OVR {q['ovr']}, ID EA {q['ea_id']}) — {q['why']}")
        add('')
    if meta.get('letters_unmatched'):
        add('## Буквы из Wikipedia, не найденные в составах')
        add('')
        add(', '.join(meta['letters_unmatched']))
        add('')
    # --- списки игроков
    add('## Игроки')
    add('')
    for slot in sorted(by_team):
        abbr = SLOT_TEAM[slot]
        add(f'### {slot} {abbr} {TEAM_NAMES[abbr]}')
        add('')
        add('| # | Игрок | Поз. | Род. | OVR | Рейтинг | Стиль | Буква | Строка базы | Примечания |')
        add('|---|---|---|---|---|---|---|---|---|---|')
        order = {'C': 0, 'L': 1, 'R': 2, 'D': 3, 'G': 4}
        for o in sorted(by_team[slot], key=lambda o: (order[o['pos']], -o['ovr'])):
            p = players[o['nhl_id']]
            if o['new']:
                d = o['donor']
                where = f"новый, artid {o['artid']}; строка {o['row']} ({d['name']}, {d['birth'][0]}, {d['tier']})"
            else:
                where = f"{HOW.get(o['how'], o['how'])}; строка {o['row']}"
                if o.get('db_name') and o['db_name'] != o['name']:
                    where += f" (в базе: {o['db_name']})"
            style = 'вратарь' if o['pos'] == 'G' else STYLE.get(o['style'], o['style'])
            add(f"| {o.get('jersey', '')} | {o['name']} | {o['pos']} | {_fmt_birth(p['birth'])} | {o['ovr']} | "
                f"{o['rating_source']} | {style} | {o.get('letter') or ''} | {where} | {'; '.join(o['notes'])} |")
        add('')
    os.makedirs(os.path.dirname(paths.report), exist_ok=True)
    with open(paths.report, 'w', encoding='utf-8', newline='\n') as f:
        f.write('\n'.join(L) + '\n')
    log(f'report: {len(L)} строк -> {paths.report}')
    assert all(s in NHL for s in by_team)
    run_lines(paths, log)


# --- звенья ------------------------------------------------------------------------------------
def _when(iso):
    """'2026-10-06T15:36:43.017Z' → '06.10.2026 15:36 UTC'."""
    if not iso or len(iso) < 16:
        return iso or '—'
    return f'{iso[8:10]}.{iso[5:7]}.{iso[0:4]} {iso[11:16]} UTC'


def _slot(s):
    """'l1rd' → 'l1rd'; 'pp2 sk4' (4-й игрок пятёрки источника) → 'PP2 №4'."""
    unit, _, k = s.partition(' sk')
    return f'{unit.upper()} №{k}' if k else s


def db_lines(paths):
    """Из выходной базы: {клуб: {место: (строка био, имя, OVR)}} для 32 клубов НХЛ."""
    from .match import load_db
    db, _ = load_db(paths, paths.db_out)
    v = View(db)
    out = defaultdict(dict)
    for e in v.entries:
        if e['team'] not in NHL:
            continue
        r = v.row_of_gid.get(v.link_gid.get(e['playerindex']))
        for f in FLAGS:
            if e[f]:
                out[e['team']][f] = (r, v.name(r), v.overall(r))
    return out


def run_lines(paths, log=print):
    wr, ln = read_json(paths.written), read_json(paths.lines) or {}
    if not wr:
        raise SystemExit('нет write.json — сначала write')
    info = wr.get('lines_info') or {}
    src = ln.get('teams') or {}
    nhl_of_row = {o['row']: o['nhl_id'] for o in wr['players']}
    lines = db_lines(paths)
    L = []
    add = L.append
    real = [a for a in TEAM_NAMES if (info.get(a) or {}).get('source', 'rating') != 'rating']
    rating = [a for a in TEAM_NAMES if a not in real]
    unmatched = [(a, u) for a in real for u in (src.get(a) or {}).get('unmatched', [])]
    fuzzy = [(a, u) for a in real for u in (src.get(a) or {}).get('fuzzy', [])]
    filled = {a: info[a].get('filled', []) for a in real}
    n_ev = sum(1 for a in real for x in filled[a] if ' ' not in x['slot'])
    n_st = sum(1 for a in real for x in filled[a] if ' ' in x['slot'])
    add('# Звенья НХЛ 2026/27 в nhlng.db: реальные сочетания')
    add('')
    add(f"Собрано {time.strftime('%d.%m.%Y %H:%M')}. Источник — DailyFaceoff "
        f"(`dailyfaceoff.com/teams/{{slug}}/line-combinations`, разбор {ln.get('generated', '—')}); база — "
        f"`{wr['db_out']}`. Имена и OVR — как записаны в базе (`firstname`/`lastname`, `p_overall`/`g_overall`); "
        '`*` — место достроено по рейтингу.')
    add('')
    add(f'- Клубов со звеньями из источника: **{len(real)}** из 32' + (f"; по рейтингу: {', '.join(rating)}" if rating
                                                                      else '') + '.')
    add(f'- Игроков источника не сопоставлено: **{len(unmatched)}**'
        + (': ' + '; '.join(f"{u['name']} ({a}) — {u['why']}" for a, u in unmatched) if unmatched else '') + '.')
    add(f'- Достроено по рейтингу: мест в тройках, парах и воротах — {n_ev}, игроков в PP/PK — {n_st} (ниже по клубам).')
    add(f'- Сопоставлены не по точному имени: {len(fuzzy)}'
        + (' — ' + '; '.join(f"{u['name']} → {u['player']} ({a})" for a, u in fuzzy) if fuzzy else '') + '.')
    add('- Тройки, пары, вратари, PP1/PP2, PK1/PK2 — из источника (одеты те же 20). 4 на 3 (`pp4_*`) — центр, лучший '
        'в атаке крайний и «синяя линия» своей пятёрки PP; 3 на 5 (`pk3_*`) — центр и пара своей четвёрки PK; '
        'овертайм, буллиты, лишние (`x1`/`x2`) — по рейтингу из одетых (`lines.build_real`).')
    add('- Седьмой защитник источника (группа d4, когда клуб играет 11 + 7) не одет: в NHL 13 — 12 нападающих и '
        '6 защитников, место в 4-й тройке — нападающему по рейтингу.')
    probs = wr.get('problems') or []
    add(f"- Проверки write (в том числе 71 место по одному владельцу, 20 одетых = rosterstatus, амплуа по местам): "
        f"{'OK' if not probs else f'{len(probs)} проблем (report.md)'}.")
    add('')
    add('## Сводка')
    add('')
    add('| Слот | Клуб | Звенья | Обновлено | Кто составил | Не сопоставлено | Достроено |')
    add('|---|---|---|---|---|---|---|')
    for slot in sorted(SLOT_TEAM):
        abbr = SLOT_TEAM[slot]
        i = info.get(abbr) or {'source': 'rating'}
        s = src.get(abbr) or {}
        if i['source'] == 'rating':
            add(f"| {slot} | {abbr} {TEAM_NAMES[abbr]} | по рейтингу{': ' + i['why'] if i.get('why') else ''} | — | — | — | — |")
            continue
        un = ', '.join(u['name'] for u in s.get('unmatched', [])) or '—'
        fl = ', '.join(f"{_slot(x['slot'])}: {x['name']}" for x in i.get('filled', [])) or '—'
        old = ' (давно — звенья прошлого сезона?)' if s.get('stale') else ''
        add(f"| {slot} | {abbr} {TEAM_NAMES[abbr]} | DailyFaceoff | {_when(i.get('updated'))}{old} | "
            f"{i.get('by') or '—'} | {un} | {fl} |")
    add('')
    mismatch = []
    for slot in sorted(SLOT_TEAM):
        abbr = SLOT_TEAM[slot]
        held = lines.get(slot, {})
        want = (wr.get('lines') or {}).get(abbr) or {}
        for f in FLAGS:
            if f not in held or nhl_of_row.get(held[f][0]) != want.get(f):
                mismatch.append(f'{abbr} {f}')
        i = info.get(abbr) or {'source': 'rating'}
        s = src.get(abbr) or {}
        star = {x['nhl_id'] for x in i.get('filled', []) if ' ' not in x['slot'] and x['slot'] in held
                and nhl_of_row.get(held[x['slot']][0]) == x['nhl_id']}
        unit_star = {(x['slot'].split()[0], x['nhl_id']) for x in i.get('filled', []) if ' ' in x['slot']}

        def who(f, unit=None):
            if f not in held:
                return '—'
            r, name, ovr = held[f]
            pid = nhl_of_row.get(r)
            mark = '*' if (unit is None and pid in star) or (unit and (unit, pid) in unit_star) else ''
            return f'{name} {ovr}{mark}'

        add(f'## {slot} {abbr} {TEAM_NAMES[abbr]}')
        add('')
        if i['source'] == 'rating':
            add('Звенья — **по рейтингу** (lines.build)' + (f": {i['why']}" if i.get('why') else
                                                            ': источника нет') + '.')
        else:
            link = f" ([источник]({i['url']}))" if i.get('url') else ''
            add(f"DailyFaceoff, обновлено {_when(i.get('updated'))}; составил: {i.get('by') or '—'}{link}.")
        add('')
        add('| | LW | C | RW | LD | RD |')
        add('|---|---|---|---|---|---|')
        for k in (1, 2, 3, 4):
            d = [who(f'l{k}ld'), who(f'l{k}rd')] if k < 4 else ['', '']
            add(f"| {k} | {who(f'l{k}lw')} | {who(f'l{k}c')} | {who(f'l{k}rw')} | {d[0]} | {d[1]} |")
        add('')
        add(f"Вратари: {who('g1')}, {who('g2')}.")
        add('')
        add('| | LW | C | RW | LD | RD |')
        add('|---|---|---|---|---|---|')
        for k in (1, 2):
            u = f'pp{k}'
            add(f"| PP{k} | {who(f'{u}lw', u)} | {who(f'{u}c', u)} | {who(f'{u}rw', u)} | {who(f'{u}ld', u)} | "
                f"{who(f'{u}rd', u)} |")
        for k in (1, 2):
            u = f'pk{k}'
            add(f"| PK{k} | {who(f'pk4_{k}lw', u)} | {who(f'pk4_{k}c', u)} | | {who(f'pk4_{k}ld', u)} | "
                f"{who(f'pk4_{k}rd', u)} |")
        add('')
        notes = []
        for u in s.get('unmatched', []) if i['source'] != 'rating' else []:
            where = ', '.join(GROUP.get(g, g) for g in u['groups'])
            notes.append(f"не сопоставлен: {u['name']}{' #' + str(u['num']) if u.get('num') else ''} ({where}) — {u['why']}")
        for x in i.get('dropped', []):
            notes.append(f"не поставлен: {x['name']} ({GROUP.get(x['where'], x['where'])}) — {x['why']}")
        for x in i.get('filled', []):
            notes.append(f"достроено по рейтингу: {_slot(x['slot'])} — {x['name']}")
        for u in s.get('fuzzy', []) if i['source'] != 'rating' else []:
            notes.append(f"не по точному имени: {u['name']} → {u['player']} ({u['how']})")
        dressed = {nhl_of_row.get(r) for r, _, _ in held.values()}
        for q in s.get('injured', []) if i['source'] != 'rating' else []:
            if q.get('nhl_id') in dressed:
                notes.append(f"в звене, но у DailyFaceoff в травмированных: {q['name']} ({q.get('injury')})")
        for n in notes:
            add(f'- {n}')
        if notes:
            add('')
    if mismatch:
        add('## Расхождения базы и write.json')
        add('')
        add(', '.join(mismatch))
        add('')
    with open(paths.report_lines, 'w', encoding='utf-8', newline='\n') as f:
        f.write('\n'.join(L) + '\n')
    log(f'report: звенья — {len(real)} клубов из источника, не сопоставлено {len(unmatched)}'
        + (f', РАСХОЖДЕНИЙ С БАЗОЙ {len(mismatch)}' if mismatch else '') + f' -> {paths.report_lines}')
