"""Отчёт «контракты было → стало» между двумя базами — для переноса в сохранённый состав (ROSTER).

Конвейер `tools/roster write --payroll-max МЛН` ужимает контракты-заглушки клубов НХЛ
(exhibitionplayerbiotable.contractdollars, × 5000 $). Игра загружает сохранённый состав (сейв ROSTER …)
целиком поверх базы из cache:, поэтому в нём остаются прежние контракты. Этот отчёт — в формате
`roster.equipment apply --report` (changes: table, field, game_id, old, new, name), его принимает
`python -m roster.equipment roster SAVE --report JSON` (без --write — только подсчёт; с --write —
меняются только значения, которые в составе ещё прежние: ручные правки пользователя не трогаются).

  python tools/payroll_report.py OLD.db NEW.db --meta nhlng-meta.xml --out contracts.json
  cd tools && python -m roster.equipment roster "…/ROSTER …/ROSTER …" --report ../contracts.json          # dry-run
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tdb import Tdb  # noqa: E402
from tdb_read import load_meta  # noqa: E402

B = 'exhibitionplayerbiotable'
FIELDS = ['contractdollars']


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('old')
    ap.add_argument('new')
    ap.add_argument('--meta', required=True)
    ap.add_argument('--out', required=True)
    a = ap.parse_args()
    meta = load_meta(a.meta)
    old = Tdb(open(a.old, 'rb').read(), meta)
    new = Tdb(open(a.new, 'rb').read(), meta)
    if old.by_name[B]['rows'] != new.by_name[B]['rows']:
        raise SystemExit('разное число игроков — базы не от одного прогона')
    changes = []
    for r in range(old.by_name[B]['rows']):
        if old.get(B, 'game_id', r) != new.get(B, 'game_id', r):
            raise SystemExit(f'строка {r}: разные game_id — базы не от одного прогона')
        for f in FIELDS:
            o, n = old.get(B, f, r), new.get(B, f, r)
            if o != n:
                name = f"{old.get_string(B, 'firstname', r)} {old.get_string(B, 'lastname', r)}".strip()
                changes.append({'table': B, 'field': f, 'game_id': old.get(B, 'game_id', r), 'row': r,
                                'old': o, 'new': n, 'name': name, 'old_usd': o * 5000, 'new_usd': n * 5000})
    json.dump({'db_old': a.old, 'db_new': a.new, 'fields': FIELDS, 'changes': changes},
              open(a.out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(f'{len(changes)} изменений ({", ".join(FIELDS)}) → {a.out}')


if __name__ == '__main__':
    main()
