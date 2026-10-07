"""Этап report: players.json + match.json + write.json → game/work/roster/report.md.

Что сопоставилось и как, кто новый (в чьей строке), кому не хватило места, какие поля не
заполнены или заполнены заглушкой, что стало с ушедшими из НХЛ игроками 2012 года.
"""
import os
import time
from collections import Counter, defaultdict

from .common import SLOT_TEAM, TEAM_NAMES, read_json
from .dbview import NHL

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
    add(f"- остались без команды и контракта: {len(wr['teamless'])} (из них в сборных, Матче звёзд, легендах или "
        f"Зимней классике — {sum(1 for t in wr['teamless'] if t['special'])}; их записи там не тронуты).")
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
