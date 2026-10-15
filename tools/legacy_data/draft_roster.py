"""db/draft_roster.db для NHL Legacy: из нашей базы — только 10 таблиц, которые есть в EA-оригинале (cacheboot.big:
exhibition* и stockteamsalaryextras), с нашими данными.

Старт франшизы «NHL Entry Draft» берёт составы из db/draft_roster.db, а не из nhlng.db (docs/legacy-data.md,
«draft_roster.db»). До 10.10.2026 туда клалась полная копия nhlng.db, и тогда франшиза с этого старта получала ещё
2 таблицы (stockintltourneyplayerstats, stockintltourneygoaliestats). Сейв при создании выходил больше буфера
сохранения: 51 таблица при буфере на 49, порча кучи (legacy-port, docs/legacy-port.md, «Старт «NHL Entry Draft»: две
лишние таблицы…»). nhl-legacy-port проверил вариант из 10 таблиц (draft_roster_min10.db, md5 838ca6a0). Здесь — та же
сборка: блоки таблиц в прежнем порядке, каталог (порядок как в базе) и db_size заново, CRC — Tdb.fix().

    python tools/legacy_data/draft_roster.py nhlng.db draft_roster.db [--meta META]   # схема — рядом с nhlng.db
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tdb import Tdb  # noqa: E402
from tdb_read import load_meta  # noqa: E402

# таблицы EA-оригинала game/other/legacy/big/cacheboot/db/draft_roster.db (сверяются с ним, если он есть)
KEEP = ('exhibitionskaterai', 'exhibitionrostertable', 'exhibitionplayers', 'exhibitionplayerbiotable',
        'exhibitiongoalieai', 'exhibitionfreeagents', 'stockteamsalaryextras', 'exhibitiondraftpick',
        'exhibitionskaterequipment', 'exhibitiongoalieequipment')
EA = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                  'game', 'other', 'legacy', 'big', 'cacheboot', 'db', 'draft_roster.db')


def tables_of(db):
    return {name for name in db.by_name}


def extract(db, keep):
    """Копия базы только с таблицами keep → байты (CRC пересчитаны)."""
    d, E = db.d, db.E
    order = sorted(db.tables, key=lambda t: t['block'])
    ends = [t['block'] for t in order[1:]] + [len(d) - 4]
    span = {id(t): (t['block'], e) for t, e in zip(order, ends)}
    names = {id(t): n for n, t in db.by_name.items()}
    missing = set(keep) - set(db.by_name)
    if missing:
        sys.exit(f'в базе нет таблиц {sorted(missing)}')
    body, new_off = bytearray(), {}
    for t in order:                                  # блоки — в прежнем порядке
        if names[id(t)] in keep:
            b, e = span[id(t)]
            new_off[id(t)] = len(body)
            body += d[b:e]
    out = bytearray(d[:0x18])
    for t in db.tables:                              # каталог — в прежнем порядке
        if names[id(t)] in keep:
            out += t['id'].encode('latin1') + struct.pack(E + 'I', new_off[id(t)])
    out += body + bytes(4)                           # последний CRC — fix()
    struct.pack_into(E + 'I', out, 0x10, len(new_off))
    struct.pack_into(E + 'I', out, 0x08, len(out))
    res = Tdb(bytes(out), db.meta)
    res.fix()
    if res.verify():
        sys.exit('draft_roster: CRC не сошлись')
    return bytes(res.d)


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
    args = sys.argv[1:]
    meta_path = None
    if '--meta' in args:
        i = args.index('--meta')
        meta_path = args[i + 1]
        del args[i:i + 2]
    if len(args) != 2:
        sys.exit(__doc__)
    src, dst = args
    meta = load_meta(meta_path or os.path.join(os.path.dirname(src), 'nhlng-meta.xml'))
    if os.path.exists(EA):
        ea = tables_of(Tdb(open(EA, 'rb').read(), meta))
        if ea != set(KEEP):
            sys.exit(f'таблицы EA-оригинала другие: {sorted(ea ^ set(KEEP))}')
    db = Tdb(open(src, 'rb').read(), meta)
    data = extract(db, set(KEEP))
    with open(dst + '.part', 'wb') as f:
        f.write(data)
    os.replace(dst + '.part', dst)
    print(f'{dst}: {len(KEEP)} таблиц из {len(db.tables)} ({len(data)} байт)')


if __name__ == '__main__':
    main()
