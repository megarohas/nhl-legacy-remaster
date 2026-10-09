"""Починка уже собранной базы NHL Legacy: ни одно поле не должно занимать последний бит записи таблицы.

Последний бит записи (reclen·8 − 1) движок TDB держит флагом «запись свободна» (у живых 0, у удалённых 1; legacy-port,
10.10.2026). До исправления tools/tdb.py widen() поле, расширенное до конца записи, занимало его: у Legacy
leaguerookiedata.draftteam (6 бит, биты 58…63 при reclen 8) — новички клубов с чётным номером (draftteam = номер + 1
нечётный) становились для игры удалёнными строками, второй драфт франшизы ломался. Здесь такие таблицы получают запись
на 4 байта длиннее (tdb.widen без полей): поля остаются на местах, флаг переезжает в новый последний бит (0 у всех
строк). Таблицы франшизы игра строит по заголовкам базы, у баз в таких таблицах строк нет — меняется только заголовок.
Повторный запуск ничего не меняет. draft_roster.db — копия nhlng.db, её build-all.sh кладёт заново после починки.

    python tools/legacy_data/fix_flagbit.py БАЗА… [--meta META]     # на месте; схема по умолчанию — рядом с базой
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tdb import Tdb  # noqa: E402
from tdb_read import load_meta  # noqa: E402


def flag_users(db):
    """Таблицы, у которых поле доходит до последнего бита записи: [(таблица, reclen, конец полей)]."""
    out = []
    for name, t in sorted(db.by_name.items()):
        b = t['block']
        reclen = struct.unpack(db.E + 'I', db.d[b + 8:b + 12])[0]
        end = max((o + w for o, w in t['fields'].values()), default=0)
        if end >= reclen * 8:
            out.append((name, reclen, end))
    return out


def fix(path, meta_path):
    db = Tdb(open(path, 'rb').read(), load_meta(meta_path))
    bad = flag_users(db)
    if not bad:
        print(f'{path}: последний бит записи свободен у всех таблиц — без правки')
        return False
    for name, reclen, end in bad:
        maxr, cur, ndel, _ = db.counts(name)
        if ndel:
            sys.exit(f'{path}: у {name} есть удалённые записи — это сейв, а не база; так не чинится')
        db.widen(name, [], 0)
        print(f'{path}: {name} — поля до бита {end} при reclen {reclen} → reclen {db.by_name[name]["reclen"]} '
              f'(строк {cur})')
    if flag_users(db):
        sys.exit(f'{path}: не вышло')
    db.fix()
    if db.verify():
        sys.exit(f'{path}: CRC не сошлись')
    with open(path + '.part', 'wb') as f:
        f.write(db.d)
    os.replace(path + '.part', path)
    return True


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
    args = sys.argv[1:]
    meta = None
    if '--meta' in args:
        i = args.index('--meta')
        meta = args[i + 1]
        del args[i:i + 2]
    if not args:
        sys.exit(__doc__)
    for path in args:
        fix(path, meta or os.path.join(os.path.dirname(path), 'nhlng-meta.xml'))


if __name__ == '__main__':
    main()
