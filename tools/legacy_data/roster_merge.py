"""Перенос новой базы в сохранённый состав (сейв ROSTER) — трёхстороннее слияние «старая база / сейв / новая база».

Игра, у которой загружен сейв ROSTER, берёт составы из него, а не из базы: новые составы, головы и флаги портретов
появятся только в сейве. Инструмент переносит изменения новой базы в сейв и сохраняет то, что пользователь сам
поменял в сейве относительно старой базы.

    python tools/legacy_data/roster_merge.py СЕЙВ --old СТАРАЯ.db --new НОВАЯ.db [--write] [--report ОТЧЁТ.json]

СТАРАЯ — база, на которой сделан сейв (та, что стояла в cache: до установки), НОВАЯ — та, что ставится (у
пользователя с --ahl32 --nhl24 — out-nhl24-ahl32/db/nhlng.db). Без --write — только отчёт. С --write — копия сейва в
game/work/legacy-data/backup-saves/roster_merge-<время>/, запись, проверка CRC и обёртки; при ошибке сейв возвращается.

По каждой таблице сейва (O — старая база, U — сейв, N — новая база):
- N = O (мы не меняли) — в сейве остаётся как есть (правки пользователя целы);
- U = O (пользователь не менял) — таблица целиком из N;
- поменяли оба — слияние строк: ключ — game_id (у таблиц с этим полем), иначе номер строки (если число строк
  одинаковое). Строка, которую поменял только пользователь, — его; только мы — наша; обе — по полям: поля, которые
  поменяли мы, — наши, остальные изменённые пользователем — его. Если у game_id в новой базе другой человек (строка
  донора отдана новому игроку: имя или дата рождения другие), правки пользователя к ней не относятся — строка наша.
- число записей — как в N; больше места в таблице сейва (max) — таблица сейва расширяется (Tdb.resize, max = current
  = N, как у nhl24.py save: так проверено в игре на stockteamjerseys и stockteamequipmenttable); у сложных таблиц
  (с индексами) — останов: сейв с записями сверх max игра считает «damaged» (docs/legacy-data.md, «ROSTER 1
  damaged»). Запас [current, max) заполняется 0xDB, как у игры.
Повтор ничего не меняет. Документация — docs/legacy-data.md, «Перенос в сейв ROSTER».
"""
import json
import os
import shutil
import struct
import sys
import time
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
REPO = os.path.dirname(TOOLS)
sys.path.insert(0, TOOLS)
from tdb import SaveFile, Tdb, load_meta  # noqa: E402

B = 'exhibitionplayerbiotable'
WHO = ('firstname', 'lastname', 'year', 'month', 'day')          # кто это (для строк по game_id)


def who_by_gid(db, live=False):
    rows = db.live_rows(B) if live else range(db.by_name[B]['rows'])
    return {db.get(B, 'game_id', r): tuple(db.get(B, f, r) for f in WHO) for r in rows}


def rows_of(db, t, live):
    return db.live_rows(t) if live else list(range(db.by_name[t]['rows']))


def merge_table(t, O, U, N, who_o, who_n):
    """→ (список записей результата или None — оставить сейв как есть, статистика)."""
    ro, ru, rn = rows_of(O, t, False), rows_of(U, t, True), rows_of(N, t, False)
    rec = lambda db, rows: [bytes(db.record(t, r)) for r in rows]
    o, u, n = rec(O, ro), rec(U, ru), rec(N, rn)
    st = {'old': len(o), 'save': len(u), 'new': len(n)}
    if n == o:
        st['how'] = 'новая база не меняла — сейв как есть'
        return None, st
    if u == n:
        st['how'] = 'сейв уже как новая база'
        return None, st
    if u == o:
        st['how'] = 'пользователь не менял — из новой базы'
        return n, st
    fields = U.by_name[t]['fields']
    if 'game_id' in fields:
        key = lambda db, r: db.get(t, 'game_id', r)
    elif len(o) == len(u) == len(n):
        key = None
    else:
        raise SystemExit(f'{t}: поменяли и пользователь, и новая база, ключа game_id нет и число строк разное — '
                         'слить нельзя')
    ko = {(key(O, r) if key else i): i for i, r in enumerate(ro)}
    ku = {(key(U, r) if key else i): i for i, r in enumerate(ru)}
    out = list(n)
    c = Counter()
    for i, r in enumerate(rn):
        k = key(N, r) if key else i
        io, iu = ko.get(k), ku.get(k)
        if io is None or iu is None or u[iu] == o[io]:
            continue                                      # пользователь эту строку не менял
        if key and who_o.get(k) != who_n.get(k):
            c['строка донора отдана новому игроку — наша'] += 1
            continue
        if n[i] == o[io]:
            out[i] = u[iu]
            c['правка пользователя'] += 1
            continue
        # по полям: наши — наши, прочие правки пользователя — его
        res = bytearray(n[i])
        for f in fields:
            vo, vu, vn = (field(N, t, f, x) for x in (o[io], u[iu], n[i]))
            if vu != vo and vn == vo:
                res = set_field(N, t, f, res, vu)
        out[i] = bytes(res)
        c['слияние по полям'] += 1
    st['how'] = 'слияние: ' + ', '.join(f'{k} {v}' for k, v in c.items())
    return out, st


def field(db, t, f, raw):
    tb = db.by_name[t]
    off, w = tb['fields'][f]
    if db.E == '<':
        return (int.from_bytes(raw, 'little') >> off) & ((1 << w) - 1)
    return (int.from_bytes(raw, 'big') >> (len(raw) * 8 - off - w)) & ((1 << w) - 1)


def set_field(db, t, f, raw, val):
    tb = db.by_name[t]
    off, w = tb['fields'][f]
    if db.E == '<':
        v = int.from_bytes(raw, 'little')
        v = (v & ~(((1 << w) - 1) << off)) | (val << off)
        return bytearray(v.to_bytes(len(raw), 'little'))
    sh = len(raw) * 8 - off - w
    v = int.from_bytes(raw, 'big')
    v = (v & ~(((1 << w) - 1) << sh)) | (val << sh)
    return bytearray(v.to_bytes(len(raw), 'big'))


def write_table(U, t, records):
    """Записи [0, k) — records, current = k, удалённых нет, запас [k, max) — 0xDB."""
    tb = U.by_name[t]
    b = tb['block']
    mx, cur, nd, head = U.counts(t)
    if len(records) > mx:
        try:
            U.resize(t, len(records))                    # max = current = записей новой базы (как nhl24.py save)
        except ValueError as e:
            raise SystemExit(f'{t}: в новой базе {len(records)} записей, в сейве места {mx}, расширить нельзя ({e}) — '
                             'игра сочтёт сейв damaged')
        tb = U.by_name[t]
        b = tb['block']
        mx, cur, nd, head = U.counts(t)
    for i, raw in enumerate(records):
        U.put_record(t, i, raw)
    start = tb['records'] + len(records) * tb['reclen']
    U.d[start:tb['records'] + mx * tb['reclen']] = b'\xdb' * ((mx - len(records)) * tb['reclen'])
    U.d[b + 0x16:b + 0x1C] = struct.pack(U.E + 'HHH', len(records), 0, 0xFFFF)


def run(save, old, new, write, report=None):
    cands = [os.path.join(os.path.dirname(x), 'nhlng-meta.xml') for x in (new, old)]
    cands.append(os.path.join(REPO, 'game', 'work', 'legacy-data', 'out', 'db', 'nhlng-meta.xml'))
    meta = load_meta(next(c for c in cands if os.path.exists(c)))     # схема одна (у накладки своей нет)
    raw = open(save, 'rb').read()
    sf = SaveFile(raw, meta)
    U = sf.db
    O = Tdb(open(old, 'rb').read(), meta)
    N = Tdb(open(new, 'rb').read(), meta)
    who_o, who_n = who_by_gid(O), who_by_gid(N)
    rep = {'save': save, 'old': old, 'new': new, 'tables': {}}
    plan = []
    for tb in U.tables:
        t = tb['name']
        if t not in O.by_name or t not in N.by_name:
            rep['tables'][t] = {'how': 'нет в базе — как есть'}
            continue
        if U.by_name[t]['reclen'] != N.by_name[t]['reclen']:
            raise SystemExit(f'{t}: длина записи в сейве и новой базе разная')
        mx, cur, nd, head = U.counts(t)
        if nd:
            raise SystemExit(f'{t}: в сейве есть удалённые записи ({nd}) — такой сейв не сливаю')
        recs, st = merge_table(t, O, U, N, who_o, who_n)
        st['max'] = mx
        rep['tables'][t] = st
        if recs is not None:
            cur_recs = [bytes(U.record(t, r)) for r in U.live_rows(t)]
            if recs != cur_recs:
                plan.append((t, recs))
                st['changed'] = True
    for t, st in rep['tables'].items():
        if st.get('changed') or 'слияние' in st.get('how', ''):
            print(f"  {t:32} {st.get('save')} → {st.get('new')} (место {st.get('max')}): {st['how']}"
                  + (f" — таблица сейва расширится до {st.get('new')}" if (st.get('new') or 0) > st['max'] else ""))
    print(f'{os.path.basename(save)}: таблиц к записи {len(plan)}' + ('' if write else ' (проба, не записано)'))
    if report:
        json.dump(rep, open(report, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    if not write or not plan:
        return rep
    for t, recs in plan:
        write_table(U, t, recs)
    out = sf.bytes()
    bdir = os.path.join(REPO, 'game', 'work', 'legacy-data', 'backup-saves',
                        f'roster_merge-{time.strftime("%Y%m%d-%H%M%S")}')
    os.makedirs(bdir, exist_ok=True)
    shutil.copy2(save, os.path.join(bdir, os.path.basename(save) + '.bak'))
    open(save, 'wb').write(out)
    bad = SaveFile(open(save, 'rb').read(), meta).verify()
    if bad:
        open(save, 'wb').write(raw)
        raise SystemExit(f'проверка не прошла, сейв возвращён: {bad[:3]}')
    print(f'записано; копия — {bdir}')
    rep['backup'] = bdir
    return rep


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    a = sys.argv[1:]
    if not a or '--old' not in a or '--new' not in a:
        sys.exit(__doc__)
    opt = lambda k: a[a.index(k) + 1] if k in a else None
    run(a[0], opt('--old'), opt('--new'), '--write' in a, opt('--report'))


if __name__ == '__main__':
    main()
