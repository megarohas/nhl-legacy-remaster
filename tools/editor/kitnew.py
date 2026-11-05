"""Новая форма клуба под новым номером (S_A_V'), копией существующей — потом её текстуры правятся как обычно.

Что нужно игре (docs/kitport.md §2.3, §2.7, docs/uniforms.md §3):
- файлы комплекта под новым номером: rendering/jersey/texlib_S_A_V', name_S_A_V'_cm, rendering/pant/texlib_S_A_V',
  rendering/sock/sock_S_A_V'_cm, fe/ion/artassets/jerseys/jersey_S_A_F' (и наклейка rendering/logo/texlib_A_S_V' при
  helmetlogo). Имена растров внутри (`jersey_S_A_V_cm.Raster`…) игра собирает из тех же чисел — переписываются на
  месте, поэтому новый вариант — той же длины, что исходный (0…9 → 0…9);
- строка stockteamjerseys: копия строки исходной формы, variant = fevariant = V', jerseyindex — следующий в клубе,
  не по умолчанию; подпись — locstring (0 дом, 1 выезд, 2 третья, 6 винтаж — с ключом Vintage_S_A_V' в строках
  игры);
- **в базе и в ростере**: сейв ROSTER хранит формы сам. Мест в таблице форм ростера — max(749, строк + 60), у
  наших баз строк ~665, поэтому строка ложится в запас ростера и в базу, размер сейва не меняется. Шлем новой формы —
  строки stockteamequipmenttable с вариантом −1 (общие у клуба; новых строк там не заводим: их число игра сверяет с
  ростером, старые ростеры стали бы damaged).

Пишется: файлы — content\\my; база — content\\my\\db (nhlng.db + draft_roster.db); ростер — новый ROSTER ДД.ММ.ГГГГ
(копия новейшего с новой строкой). Проверки — как у составов: CRC, места таблиц, лаунчер --check-roster.
"""
import datetime
import os
import re

import gamefs
from gamefs import EditorError

J = 'stockteamjerseys'
LOCS = {0: ('Дом', 'Home'), 1: ('Выезд', 'Away'), 2: ('Третья', 'Third'), 6: ('Винтаж', 'Vintage')}


def kit_files(s, a, v, f, helmet):
    out = [f'rendering/jersey/texlib_{s}_{a}_{v}.rx2', f'rendering/jersey/name_{s}_{a}_{v}_cm.rx2',
           f'rendering/pant/texlib_{s}_{a}_{v}.rx2', f'rendering/sock/sock_{s}_{a}_{v}_cm.rx2',
           f'fe/ion/artassets/jerseys/jersey_{s}_{a}_{f}.big']
    if helmet:
        out.append(f'rendering/logo/texlib_{a}_{s}_{v}.rx2')
    return out


def renamed(data, rel, old, new):
    """Байты файла с номером old → new в именах растров (RW4) — на месте, той же длины."""
    if data[:4] == b'BIGF':
        return data                                      # превью меню: имён с номером внутри нет
    import tex
    c = tex.load(data, rel)
    raw = c.raw
    f = c.f
    for s in f.find(tex.T_NAMES):
        o = f.abs_off(s)
        n = int.from_bytes(raw[o + 2:o + 4], 'big')
        for k in range(n):
            ptr = int.from_bytes(raw[o + 8 + 12 * k:o + 12 + 12 * k], 'big')
            q = raw.index(b'\0', ptr)
            name = bytes(raw[ptr:q]).decode('latin1')
            t = name.replace(old, new, 1)
            if len(t) != len(name):
                raise EditorError('kit_len', f'{name}: номер другой длины', f'{name}: number of another length')
            raw[ptr:q] = t.encode('latin1')
    return bytes(raw)


def free_variant(ed, s, a, v, team_kits):
    used = {k['v'] for k in team_kits} | {k['f'] for k in team_kits}
    for db_kits in ed.db.kits.values():
        used |= {k['v'] for k in db_kits if k['s'] == s and k['a'] == a}
    lo, hi = (0, 9) if v < 10 else (10, 31)
    for cand in range(lo, hi + 1):
        if cand in used:
            continue
        if any(ed.fs.exists(r) for r in kit_files(s, a, cand, cand, True)):
            continue
        return cand
    raise EditorError('no_variant', f'Свободного номера варианта той же длины для {s}_{a}_* нет',
                      f'No free variant number of the same length for {s}_{a}_*')


def create(ed, aid, loc=2, label=None):
    """aid — kit:<клуб>:S_A_V_F исходной формы. → отчёт."""
    from tdb import SaveFile, Tdb
    import rosters
    gamefs.check_game_closed()
    ed.db.load()
    kind, _, rest = aid.partition(':')
    team = int(rest.split(':')[0])
    s, a, v, f = (int(x) for x in rest.split(':')[1].split('_'))
    kits = ed.db.kits.get(team, [])
    src = next((k for k in kits if (k['s'], k['a'], k['v'], k['f']) == (s, a, v, f)), None)
    if src is None:
        raise EditorError('no_kit', 'Нет такой формы в ростере', 'No such kit in the roster')
    v2 = free_variant(ed, s, a, v, kits)
    old_tag, new_tag = f'_{s}_{a}_{v}_', f'_{s}_{a}_{v2}_'
    files_src = kit_files(s, a, v, f, src['helmetlogo'])
    files_new = kit_files(s, a, v2, v2, src['helmetlogo'])
    blobs = {}
    for r0, r1 in zip(files_src, files_new):
        data = ed.fs.read(r0)
        if data is None:
            raise EditorError('no_file', f'У исходной формы нет файла {r0}', f'The source kit has no file {r0}')
        if r1.startswith('rendering/logo/'):
            blobs[r1] = renamed(data, r0, f'_{a}_{s}_{v}_', f'_{a}_{s}_{v2}_')
        else:
            blobs[r1] = renamed(data, r0, old_tag, new_tag)
    meta = ed.db.meta

    def add_row(db, rows_live):
        recs = [bytes(db.record(J, r)) for r in rows_live]
        base = next(bytes(db.record(J, r)) for r in rows_live
                    if (db.get(J, 'teamid', r), db.get(J, 'style', r), db.get(J, 'teamartid', r), db.get(J, 'variant', r),
                        db.get(J, 'fevariant', r)) == (team, s, a, v, f))
        idx = max(db.get(J, 'jerseyindex', r) for r in rows_live if db.get(J, 'teamid', r) == team) + 1
        if idx > 31:
            raise EditorError('kit_full', 'У клуба уже 32 формы (больше игра не держит)', 'The club already has 32 kits')
        new = base
        for fld, val in (('variant', v2), ('fevariant', v2), ('jerseyindex', idx), ('isdefault', 0), ('locstring', loc)):
            new = bytes(rosters._rec_set(db, J, fld, bytearray(new), val))
        return recs + [new]

    # ростер: копия новейшего + строка (в запас таблицы)
    refs = ed.fs.saves.list('ROSTER')
    roster_out = None
    if refs:
        from roster_merge import write_table
        sf = SaveFile(open(refs[-1].file, 'rb').read(), meta)
        d = sf.db
        mx, cur = d.counts(J)[:2]
        if cur + 1 > mx:
            raise EditorError('kit_room', f'В ростере нет места для формы ({cur} из {mx})', f'No room in the roster ({cur}/{mx})')
        write_table(d, J, add_row(d, d.live_rows(J)))
        roster_out = sf.bytes()
        if len(roster_out) != os.path.getsize(refs[-1].file) or SaveFile(roster_out, meta).verify():
            raise EditorError('check', 'Ростер с новой формой не прошёл проверку', 'The roster with the new kit failed the check')
    # база
    hit = ed.fs.find('db/nhlng.db')
    db = Tdb(open(hit[2], 'rb').read(), meta)
    recs = add_row(db, list(range(db.by_name[J]['rows'])))
    db.resize(J, len(recs))
    for i, raw in enumerate(recs):
        db.put_record(J, i, raw)
    db.fix()
    from draft_roster import KEEP, extract
    db_out = bytes(db.d)
    draft = extract(Tdb(db_out, meta), KEEP)
    # запись: файлы, база, ростер; лаунчер сверяет новый ростер с новой базой
    with ed.lock:
        backup = ed.fs.backup_dir()
        for rel, data in blobs.items():
            ed.fs.write_my(rel, data, backup)
        ed.fs.write_my('db/nhlng.db', db_out, backup)
        ed.fs.write_my('db/draft_roster.db', draft, backup)
        name = None
        if roster_out is not None:
            stamp = datetime.date.today().strftime('%d.%m.%Y')
            work = os.path.join(ed.fs.work, 'rosters')
            os.makedirs(work, exist_ok=True)
            tmp = os.path.join(work, f'ROSTER {stamp}')
            open(tmp, 'wb').write(roster_out)
            s0 = rosters.Session.__new__(rosters.Session)
            s0.ed = ed
            code, msg = s0.launcher_check(tmp)
            if code not in (None, 0):
                for rel in list(blobs) + ['db/nhlng.db', 'db/draft_roster.db']:
                    ed.fs.revert(rel, backup)
                raise EditorError('launcher', f'Лаунчер не принял ростер с новой формой (код {code}): {msg}; всё '
                                  'возвращено', f'The launcher rejected the roster with the new kit (code {code}): {msg}')
            folder, _ = rosters.write_save(ed.fs.saves, roster_out, f'ROSTER {stamp}')
            name = os.path.basename(folder)
    notes = []
    if loc == 6:
        notes += vintage_label(ed, s, a, v2, label or f'{ed.db.team(team)["abbr"]} {v2}')
    ed._conts.clear()
    ed.db.loaded = False
    ed.rosters = None
    ed.log(f'новая форма {s}_{a}_{v2} клуба {team} из {s}_{a}_{v}: файлы {len(blobs)}, ростер {name}')
    return dict(written=list(blobs) + ['db/nhlng.db'], kit=f'kit:{team}:{s}_{a}_{v2}_{v2}', roster=name,
                notes=notes + [ed.t(f'новая форма {s}_{a}_{v2} — копия {s}_{a}_{v}; ростер {name}',
                                    f'new kit {s}_{a}_{v2} — a copy of {s}_{a}_{v}; roster {name}')])


def vintage_label(ed, s, a, v, text):
    """Подпись винтажной формы — ключ Vintage_S_A_V в строках игры (docs/kitport.md §2.7)."""
    import texts
    try:
        texts.save(ed, 'nhl_eng_us', {f'Vintage_{s}_{a}_{v}': text})
        return [ed.t(f'подпись «{text}» — Vintage_{s}_{a}_{v}', f'label «{text}» — Vintage_{s}_{a}_{v}')]
    except EditorError as e:
        return [ed.t(f'подпись не записана: {e.ru}', f'label not written: {e.en}')]


_ = re
