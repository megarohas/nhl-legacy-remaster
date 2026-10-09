"""Отчёт «контракты было → стало» между двумя базами — для переноса в сохранённый состав (ROSTER).

Конвейер `tools/roster write --payroll-max МЛН` ужимает контракты-заглушки клубов НХЛ
(exhibitionplayerbiotable.contractdollars, × 5000 $). Игра при каждом запуске сама загружает сохранённый
состав (сейв ROSTER …; проверено 09.10.2026: с ROSTER-сейвом в корне Select Team показывает его контракты,
без него — контракты базы) целиком поверх базы из cache:, поэтому в нём остаются прежние контракты. Этот
отчёт — в формате `roster.equipment apply --report` (changes: table, field, game_id, old, new, name), его
принимает `python -m roster.equipment roster SAVE --report JSON` (без --write — только подсчёт; с --write —
меняются только значения, которые в составе ещё прежние: ручные правки пользователя не трогаются).

`--save SAVE` — не только контракты, а все различия OLD → NEW в таблицах, которые есть в этом сейве
(рейтинги exhibitionskaterai/goalieai, звенья exhibitionrostertable …). Строка таблицы — по game_id, у
exhibitionrostertable (нет game_id) — по key (команда × 50 + номер); в изменении тогда «key_field».

  python tools/payroll_report.py OLD.db NEW.db --meta nhlng-meta.xml --out contracts.json [--save SAVE]
  cd tools && python -m roster.equipment roster "…/ROSTER …/ROSTER …" --report ../contracts.json          # dry-run
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tdb import SaveFile, Tdb  # noqa: E402
from tdb_read import load_meta  # noqa: E402

B = 'exhibitionplayerbiotable'
FIELDS = ['contractdollars', 'contractis2way']
KEYS = ('game_id', 'key')   # поле-ключ строки таблицы: game_id (игроки, рейтинги, экипировка), key (составы)


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('old')
    ap.add_argument('new')
    ap.add_argument('--meta', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--save', help='сейв ROSTER: все различия в его таблицах, а не только контракты')
    a = ap.parse_args()
    meta = load_meta(a.meta)
    old = Tdb(open(a.old, 'rb').read(), meta)
    new = Tdb(open(a.new, 'rb').read(), meta)
    tables = [t['name'] for t in SaveFile(open(a.save, 'rb').read(), meta).db.tables] if a.save else [B]
    names = {old.get(B, 'game_id', r): f"{old.get_string(B, 'firstname', r)} {old.get_string(B, 'lastname', r)}".strip()
             for r in old.live_rows(B)}
    changes, per = [], {}
    for t in tables:
        if t not in old.by_name or t not in new.by_name:
            print(f'  {t}: нет в базах — пропуск')
            continue
        fo, fn = old.by_name[t]['fields'], new.by_name[t]['fields']
        kf = next((k for k in KEYS if k in fo), None)
        fields = FIELDS if t == B and not a.save else [f for f in fo if f in fn and f != kf and fo[f] == fn[f]]
        if any(fo[f] != fn.get(f) for f in fo if f in fn):
            raise SystemExit(f'{t}: поля разной ширины в OLD и NEW — перенос по значениям не годится')
        # только живые записи (tdb.Tdb.live_rows): у баз конвейера это все строки, у базы из сейва — без запаса
        # за current и удалённых
        live = old.live_rows(t)
        if old.by_name[t]['rows'] != new.by_name[t]['rows'] or live != new.live_rows(t):
            raise SystemExit(f'{t}: разное число строк — базы не от одного прогона')
        for r in live:
            diff = [(f, old.get(t, f, r), new.get(t, f, r)) for f in fields]
            diff = [d for d in diff if d[1] != d[2]]
            if not diff:
                continue
            if kf is None:
                raise SystemExit(f'{t}: строка {r} изменилась, а ключа строки (game_id/key) нет')
            k = old.get(t, kf, r)
            if k != new.get(t, kf, r):
                raise SystemExit(f'{t}: строка {r}: разные {kf} — базы не от одного прогона')
            for f, o, n in diff:
                ch = {'table': t, 'field': f, 'game_id': k if kf == 'game_id' else None, 'row': r, 'old': o, 'new': n}
                if kf != 'game_id':
                    ch.update({'key_field': kf, kf: k})
                    gid = None
                else:
                    gid = k
                ch['name'] = names.get(gid, '') if gid is not None else f'{t} {kf} {k}'
                if t == B and f == 'contractdollars':
                    ch.update({'old_usd': o * 5000, 'new_usd': n * 5000})
                changes.append(ch)
                per[t] = per.get(t, 0) + 1
    json.dump({'db_old': a.old, 'db_new': a.new, 'save': a.save, 'fields': FIELDS if not a.save else 'all',
               'changes': changes}, open(a.out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    what = ', '.join(f'{t} {n}' for t, n in per.items()) if a.save else ', '.join(FIELDS)
    print(f'{len(changes)} изменений ({what}) → {a.out}')


if __name__ == '__main__':
    main()
