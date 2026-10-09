"""Спецификация изменений базы и CACHE для превращения Arizona Coyotes (строка 22) в Utah Mammoth — для агента
legacy-data (сам ничего не применяет): поле, «было» (по базе, которую читает), «стало», зачем; строки локализации;
файлы арта в cache: (с размерами и md5). Цели (новые значения) — FACTS ниже, источники — в docs/utah.md.

    python tools/utah/make_spec.py DB_DIR LOC.db OUTDIR SPEC.json [--ahl-base DB_DIR]
        DB_DIR  — папка с nhlng.db и nhlng-meta.xml (копия CACHE пользователя: game/work/utah/ref/cache-db)
        LOC.db  — NHL_ENG_US.db той же установки (схема — game/other/legacy/big/cacheboot/fe/loc/nhl_eng_us-meta.xml)
        OUTDIR  — готовые файлы (раскладка cache:) — game/work/utah/out
"""
import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
REPO = os.path.dirname(TOOLS)
sys.path.insert(0, TOOLS)
from tdb import Tdb                 # noqa: E402
from tdb_read import load_meta      # noqa: E402
from locdb import LocDb             # noqa: E402

ROW = 22                            # Arizona Coyotes в базе Legacy (и в нашей, после nhl32): Central, конференция 1
ART_OLD = 22
FACTS = None                        # заполняется из game/work/utah/src/facts.json (main)


def md5(p):
    h = hashlib.md5()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


def val(db, t, f, r):
    off, w = db.by_name[t]['fields'][f]
    return db.get_string(t, f, r) if w > 32 else db.get(t, f, r)


def rgb(h):
    h = h.lstrip('#')
    return [int(h[i:i + 2], 16) for i in (0, 2, 4)]


def change(db, table, row, field, new, why):
    old = val(db, table, field, row)
    return {'table': table, 'row': row, 'field': field, 'old': old, 'new': new, 'why': why,
            'same': old == new}


def team_changes(db, F):
    T = 'exhibitionteams'
    c = []
    add = lambda f, v, why: c.append(change(db, T, ROW, f, v, why))   # noqa: E731
    add('fullname', F['fullname'], 'полное название (экраны выбора, табло, франшиза)')
    add('shortname', F['shortname'], 'город/регион в названии (как placeName в API НХЛ — «Utah»)')
    add('abbrname', F['abbr'], 'сокращение НХЛ (UTA) — и ключи локализации по сокращению')
    add('artabbr', F['abbr'], 'сокращение для арта и ключей NHLTeamName_<abbr> (как у SEA/VGK — то же, что abbrname)')
    add('artid', F['artid'], 'номер арта: логотипы t/s/d/c/w/r, центр льда, шайба, баннер, форма (свободен в Legacy)')
    add('spotlight', F['spotlight'], 'прожекторы на выходе команды — rendering/spotlight/texlib_48 (свободен: у EA 0…45, '
                                     '46/47 — SEA/VGK)')
    add('tunnel', F['tunnel'], 'туннель: 22 — таблички и стены «Койотов»; 38 — нейтральный EA SPORTS (как у SEA/VGK)')
    add('audioid', F['audioid'], 'звук команды: 22 — комментатор называет «Coyotes»/«Arizona»; 32 — номер без записей '
                                 '(как у SEA, проверен в игре: комментатор говорит без названия)')
    for i, (k, h) in enumerate((('primarycolor', F['colors']['primary']), ('secondarycolor', F['colors']['secondary']))):
        for ch, v in zip('rgb', rgb(h)):
            add(f'{k}_{ch}', v, 'основной цвет (подсветка логотипа в меню, табло)' if i == 0 else 'второй цвет')
    add('rivalteam', F['rival'] + 1, f'соперник (номер + 1): {F["rival_name"]}')
    return c


def arena_changes(db, F):
    A = 'exhibitionarena'
    arena = val(db, 'exhibitionteams', 'arenaid', ROW)
    tpl = F['arena']['template']
    c = []
    for f, v, why in ((('arenaname', F['arena']['name'], 'название арены (в базе; строк локализации нет)')),
                      (('cityname', F['arena']['city'], 'город арены')),
                      (('maxattendance', F['arena']['capacity'], 'вместимость на хоккее')),
                      (('avgattendance', F['arena']['avg'], 'заполняемость, %'))):
        c.append(change(db, A, arena, f, v, why))
    # модель и звук арены — как у нейтральной «EA SPORTS Arena» (шаблон SEA/VGK): у модели 22 в 3D — «Койоты»
    for f in ('arenatype', 'arenaartid', 'arenaaudioid', 'cityaudioid', 'chantaudioid', 'goalhorn', 'periodhorn',
              'puck', 'stanchion', 'bouncemap', 'powerring', 'centerline', 'centericelogo'):
        c.append(change(db, A, arena, f, val(db, A, f, tpl), f'как у арены {tpl} «{val(db, A, "arenaname", tpl)}»'))
    return arena, c


def colors_changes(db, F):
    C = 'stockteamcolorstable'
    out = []
    want = {0: F['colors']['primary'], 1: F['colors']['secondary'], 2: F['colors']['third']}
    for r in db.live_rows(C):
        if db.get(C, 'team', r) == ROW:
            cid = db.get(C, 'colorid', r)
            new = rgb(want[cid])
            old = [db.get(C, f'color_{ch}', r) for ch in 'rgb']
            out.append({'row': r, 'colorid': cid, 'old': old, 'new': new})
    return out


def jersey_rows(db, F):
    J = 'stockteamjerseys'
    rows = [r for r in db.live_rows(J) if db.get(J, 'teamid', r) == ROW]
    fields = sorted(db.by_name[J]['fields'])
    old = [{'row': r, **{f: db.get(J, f, r) for f in fields}} for r in rows]
    new = []
    for k in F['kits']:
        new.append({'teamid': ROW, 'teamartid': F['artid'], 'style': 1, 'variant': k['variant'], 'fevariant': k['variant'],
                    'jerseyindex': k['variant'], 'locstring': k['locstring'], 'isdefault': k['isdefault'],
                    'islightcolor': k['light'], 'hastie': 0, 'helmetlogo': 1, 'helmetnumbers': 1, 'islockable': 0,
                    'label': k['label']})
    return old, new


def equip(db, F, row=ROW):
    E, G = 'stockteamequipmenttable', 'stockgoalieequipment'
    rows = [r for r in db.live_rows(E) if db.get(E, 'team', r) == row + 1]
    cmap = {k.upper(): v.upper() for k, v in F['equip_recolor'].items()}
    seen = {}
    for r in rows:
        for z in range(1, 10):
            h = '%02X%02X%02X' % tuple(db.get(E, f'zone{z}_{ch}', r) for ch in 'rgb')
            seen[h] = seen.get(h, 0) + 1
    grows = [r for r in db.live_rows(G) if db.get(G, 'team', r) == row + 1]
    return {'table': E, 'team_raw': row + 1, 'rows': rows, 'colors_seen': seen,
            'recolor': cmap, 'unmapped': sorted(h for h in seen if h not in cmap),
            'goalie_table': G, 'goalie_rows': grows}


def loc_changes(loc, F):
    ab = F['abbr']
    want = {
        f'NHLTeamName_{ROW}': F['fullname'], f'NHLCityName_{ROW}': F['shortname'], f'NICKLINE2_{ROW}': F['nickname'],
        f'CITYLINE1_{ROW}': F['shortname'], f'NHLTeamName_Abbr3_{ROW}': ab,
        f'NHLTeamName_{ab}': F['fullname'], f'NHLCityName_{ab}': F['shortname'], f'Teamline1_{ab}': F['shortname'],
        f'Teamline2_{ab}': F['nickname'], f'NHLTeamName_ABBR3_{ab}': ab, f'X_XLA_TEAM_{ab}': ab,
        f'NICKLINE2_{ab}': F['nickname'], f'TXT_NICKNAME_{ab}': F['nickname'], f'TXT_NICKNAME_ALT_{ab}': F['nickname'],
    }
    # старые ключи по сокращениям Аризоны: остаются (на них никто не ссылается, если abbrname/artabbr = UTA); для
    # старых франшиз (leagueteams с ARZ/PHX) — по желанию переписать и их
    old_keys = ['NHLTeamName_PHX', 'NHLCityName_PHX', 'NICKLINE2_PHX', 'TEAMLINE1_PHX', 'TEAMLINE2_PHX',
                'TEAMLINE2_ARZ', 'NHLTeamName_Abbr3_PHX', 'X_XLA_TEAM_PHX', 'TXT_NICKNAME_PHX', 'TXT_NICKNAME_ALT_PHX']
    out = []
    for k, v in want.items():
        rows = loc.find_all(k)
        cur = loc.text(loc.text_off_at(rows[0])) if rows else None
        out.append({'key': k, 'old': cur, 'new': v, 'action': 'put' if rows else 'add'})
    olds = []
    for k in old_keys:
        rows = loc.find_all(k)
        olds.append({'key': k, 'text': loc.text(loc.text_off_at(rows[0])) if rows else None})
    return out, olds


def ahl_section(db, loc, A):
    """Фарм-клуб: строка A['row'] (Springfield Falcons) → Tucson Roadrunners: поля, арена, комплекты, локализация."""
    T, J, AR = 'exhibitionteams', 'stockteamjerseys', 'exhibitionarena'
    r = A['row']
    if val(db, T, 'ahlaffiliate', ROW) != r + 1:
        raise SystemExit(f'фарм-клуб строки {ROW} — не {r}')
    ch = [change(db, T, r, 'fullname', A['fullname'], 'полное название'),
          change(db, T, r, 'shortname', A['shortname'], 'город'),
          change(db, T, r, 'abbrname', A['abbr'], 'сокращение АХЛ'),
          change(db, T, r, 'artabbr', A['abbr'], 'сокращение для арта и ключей локализации'),
          change(db, T, r, 'artid', A['artid'], 'номер арта: логотипы t/s/d/c/w, центр льда, шайба, баннер, форма '
                                                 '(свободен в Legacy)'),
          change(db, T, r, 'audioid', A['audioid'], 'звук команды: свободный номер без записей (как CV/HSK 55/56) — '
                                                     'иначе комментатор назовёт Springfield')]
    for i, (k, h) in enumerate((('primarycolor', A['colors']['primary']), ('secondarycolor', A['colors']['secondary']))):
        for c_, v in zip('rgb', rgb(h)):
            ch.append(change(db, T, r, f'{k}_{c_}', v, 'основной цвет' if i == 0 else 'второй цвет'))
    arena = val(db, T, 'arenaid', r)
    ach = [change(db, AR, arena, 'arenaname', A['arena']['name'], 'арена (модель АХЛ 145 остаётся)'),
           change(db, AR, arena, 'cityname', A['arena']['city'], 'город'),
           change(db, AR, arena, 'maxattendance', A['arena']['capacity'], 'вместимость на хоккее'),
           change(db, AR, arena, 'arenaaudioid', 255, 'объявление арены — нейтральное (как у арен CV/HSK)'),
           change(db, AR, arena, 'cityaudioid', 255, 'объявление города — нейтральное (как у арен CV/HSK)')]
    rows = [x for x in db.live_rows(J) if db.get(J, 'teamid', x) == r]
    fields = sorted(db.by_name[J]['fields'])
    jold = [{'row': x, **{f: db.get(J, f, x) for f in fields}} for x in rows]
    jnew = [{'teamid': r, 'teamartid': A['artid'], 'style': 1, 'variant': k['variant'], 'fevariant': k['variant'],
             'jerseyindex': k['variant'], 'locstring': k['locstring'], 'isdefault': k['isdefault'],
             'islightcolor': k['light'], 'hastie': 0, 'helmetlogo': 1, 'helmetnumbers': 0, 'islockable': 0,
             'label': k['label']} for k in A['kits']]
    ab = A['abbr']
    want = {f'NHLTeamName_{ab}': A['fullname'], f'NHLCityName_{ab}': A['shortname'], f'Teamline1_{ab}': A['shortname'],
            f'Teamline2_{ab}': A['nickname'], f'NHLTeamName_ABBR3_{ab}': ab, f'X_XLA_TEAM_{ab}': ab,
            f'TXT_NICKNAME_{ab}': A['nickname'], f'TXT_NICKNAME_ALT_{ab}': A['nickname']}
    lc = []
    for k, v in want.items():
        rr = loc.find_all(k)
        lc.append({'key': k, 'old': loc.text(loc.text_off_at(rr[0])) if rr else None, 'new': v,
                   'action': 'put' if rr else 'add'})
    return {'row': r, 'now': f'{val(db, T, "fullname", r)} (art {val(db, T, "artid", r)}, арена {arena} '
                              f'«{val(db, AR, "arenaname", arena)}»)',
            'exhibitionteams': ch, 'exhibitionarena': {'row': arena, 'changes': ach},
            'stockteamjerseys': {'teamid': r, 'old_rows': jold, 'new_rows': jnew,
                                 'how': 'строки teamid 55 (Springfield, teamartid 153) заменить этими; форма — '
                                        'game/work/utah/out (1_105_0/1), арт 153 у EA остаётся нетронутым'},
            'equipment': equip(db, {'equip_recolor': A['equip_recolor']}, r),
            'localization': lc, 'division_note': A['division_note']}


def files_list(outdir, prefixes):
    out = []
    for dp, _, fs in os.walk(outdir):
        for f in sorted(fs):
            p = os.path.join(dp, f)
            rel = os.path.relpath(p, outdir).replace('\\', '/')
            if prefixes and not any(rel.startswith(x) for x in prefixes):
                continue
            out.append({'path': rel, 'bytes': os.path.getsize(p), 'md5': md5(p)})
    return sorted(out, key=lambda x: x['path'])


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    a = sys.argv[1:]
    if len(a) < 4:
        sys.exit(__doc__)
    db_dir, loc_path, outdir, spec_out = a[:4]
    facts = json.load(open(os.path.join(HERE, 'src', 'facts.json'), encoding='utf-8'))
    db_path = os.path.join(db_dir, 'nhlng.db')
    db = Tdb(open(db_path, 'rb').read(), load_meta(os.path.join(db_dir, 'nhlng-meta.xml')))
    loc_meta = os.path.join(REPO, 'game', 'other', 'legacy', 'big', 'cacheboot', 'fe', 'loc', 'nhl_eng_us-meta.xml')
    loc = LocDb(open(loc_path, 'rb').read(), load_meta(loc_meta))
    if val(db, 'exhibitionteams', 'abbrname', ROW) not in ('ARZ', 'UTA'):
        sys.exit(f'строка {ROW}: не ARZ — другая база?')
    F = facts['team']
    arena_row, arena = arena_changes(db, F)
    jold, jnew = jersey_rows(db, F)
    loc_new, loc_old = loc_changes(loc, F)
    spec = {
        'spec': 'utah', 'version': 1, 'date': facts['date'], 'author': 'агент utah (megarohas_nhl13)',
        'what': 'Arizona Coyotes (строка 22 exhibitionteams) → Utah Mammoth 2026/27: поля базы, локализация, файлы арта '
                'в cache:. Ничего не применено — применяет legacy-data (nhl32/build-all) или вручную.',
        'base_db': {'path': os.path.abspath(db_path), 'md5': md5(db_path), 'note': facts.get('db_note', '')},
        'facts': facts['facts'],
        'decisions': facts['decisions'],
        'db': {
            'exhibitionteams': team_changes(db, F),
            'exhibitionarena': {'row': arena_row, 'changes': arena,
                                'alternative': facts['arena_alternative']},
            'stockteamcolorstable': colors_changes(db, F),
            'stockteamjerseys': {'teamid': ROW, 'old_rows': jold, 'new_rows': jnew,
                                 'optional_third': dict(jersey_rows(db, dict(F, kits=[F['kit_third_optional']]))[1][0]),
                                 'how': 'строки teamid 22 (сейчас 8: стиль 1 варианты 3/4/0/1, стиль 0 0/1/3/4) '
                                        'заменить ровно этими; лишние — удалить (на номера строк stockteamjerseys '
                                        'ничто не ссылается)'},
            'equipment': equip(db, F),
        },
        'ahl': ahl_section(db, loc, facts['ahl']),
        'localization': {'file': 'fe/loc/NHL_ENG_US.db', 'set_or_add': loc_new, 'old_arizona_keys': loc_old,
                         'tool': 'tools/locdb.py put (ключ ищется по hashid, регистр не важен)'},
        'cache_files': {
            'add': files_list(outdir, None),
            'optional_third': files_list(os.path.join(os.path.dirname(os.path.abspath(outdir)), 'out-third'), None),
            'note': facts['files_note'],
        },
        'franchise': facts['franchise_note'],
        'other_agents': facts['other_agents'],
        'open_questions': facts['open_questions'],
    }
    json.dump(spec, open(spec_out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    n = sum(1 for x in spec['db']['exhibitionteams'] if not x['same'])
    print(f'{spec_out}: exhibitionteams — {n} полей, арена {arena_row} — {sum(1 for x in arena if not x["same"])}, '
          f'цвета — {len(spec["db"]["stockteamcolorstable"])}, форма — {len(jold)} → {len(jnew)} строк, '
          f'локализация — {len(loc_new)} ключей, файлов — {len(spec["cache_files"]["add"])}')


if __name__ == '__main__':
    main()
