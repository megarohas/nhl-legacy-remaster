"""Починка уже собранной базы NHL Legacy: ни одно поле не должно занимать последний бит записи таблицы.

Последний бит записи (reclen·8 − 1) движок TDB держит флагом «запись свободна» (у живых 0, у удалённых 1; legacy-port,
10.10.2026). До исправления tools/tdb.py widen() поле, расширенное до конца записи, занимало его: у Legacy
leaguerookiedata.draftteam (6 бит, биты 58…63 при reclen 8) — новички клубов с чётным номером (draftteam = номер + 1
нечётный) становились для игры удалёнными строками, второй драфт франшизы ломался. Здесь такие таблицы получают запись
на 4 байта длиннее (tdb.widen без полей): поля остаются на местах, флаг переезжает в новый последний бит (0 у всех
строк). Таблицы франшизы игра строит по заголовкам базы, у баз в таких таблицах строк нет — меняется только заголовок.
Повторный запуск ничего не меняет. draft_roster.db — копия nhlng.db, её build-all.sh кладёт заново после починки.

    python tools/legacy_data/fix_flagbit.py БАЗА… [--meta META]     # на месте; схема по умолчанию — рядом с базой
    python tools/legacy_data/fix_flagbit.py --save СЕЙВ КОПИЯ --meta META
                                         # сейв франшизы, начатой на старой базе (внутренний файл DYNASTY …) → копия
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


def fix_save(src, dst, meta_path):
    """Сейв франшизы, начатой на базе с полем на последнем бите: у таких таблиц запись +4 байта (поля на местах), новый
    последний бит — флаг: 1 у строк из списка удалённых и из запаса [current, max), 0 у живых (так у всех 37 таблиц сейва
    BE A GM10 со строками — legacy-port, 10.10.2026). Прежний последний бит не трогается: у живых это настоящий младший
    бит draftteam. Список удалённых в заголовке остаётся как был (им движок пользуется при вставке). Пишет в dst."""
    from tdb import SaveFile
    if os.path.abspath(src) == os.path.abspath(dst):
        sys.exit('сейв чинится в другой файл (копию), не на месте')
    sf = SaveFile(open(src, 'rb').read(), load_meta(meta_path))
    db = sf.db
    bad = flag_users(db)
    if not bad:
        print(f'{src}: последний бит записи свободен у всех таблиц — чинить нечего')
        return False
    for name, reclen, end in bad:
        maxr, cur, ndel, _ = db.counts(name)
        free = set(db.deleted(name)) | set(range(cur, maxr))
        db.widen(name, [], 0)
        t = db.by_name[name]
        for r in free:
            p = t['records'] + r * t['reclen'] + t['reclen'] - 1
            db.d[p] |= 1
        live = db.live_rows(name)
        print(f'{src}: {name} — reclen {reclen} → {t["reclen"]}; живых {len(live)} (флаг 0), удалённых {ndel} и запаса '
              f'{maxr - cur} (флаг 1)')
    if flag_users(db):
        sys.exit(f'{src}: не вышло')
    out = sf.bytes()
    if SaveFile(out, load_meta(meta_path)).verify():
        sys.exit(f'{dst}: суммы сейва не сошлись')
    with open(dst + '.part', 'wb') as f:
        f.write(out)
    os.replace(dst + '.part', dst)
    print(f'→ {dst}')
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
    if args[:1] == ['--save']:
        if len(args) != 3 or not meta:
            sys.exit('--save СЕЙВ КОПИЯ --meta META')
        fix_save(args[1], args[2], meta)
        return
    if not args:
        sys.exit(__doc__)
    for path in args:
        fix(path, meta or os.path.join(os.path.dirname(path), 'nhlng-meta.xml'))


if __name__ == '__main__':
    main()
