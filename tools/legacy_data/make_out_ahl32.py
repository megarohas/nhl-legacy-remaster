"""Накладка «АХЛ на 32» для NHL Legacy: game/work/legacy-data/out-ahl32 — ставится поверх out
(bash tools/legacy_data/install-legacy-data.sh --ahl32). Берёт базу roster-ahl32 (с портретами и экипировкой), схему и
локализацию nhl32-ahl32 и портреты игроков, которых нет в основной базе (CV/HSK). Вызывается из build-all.sh (collect
--ahl32); draft_roster.db накладки build-all.sh кладёт потом сам (10 таблиц nhlng.db — draft_roster.py).

Прежняя накладка не удаляется, а уезжает в game/work/legacy-data/_stale/out-ahl32-<время> (CLAUDE.md: удаление — только в
Корзину или в _stale). Восстановлен 09.10.2026 по транскрипту агента legacy-data (docs/incident-2026-10-09.md).
"""
import json
import os
import shutil
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from install_legacy_data import W  # noqa: E402  (game/work/legacy-data основной копии репозитория)

OUT = os.path.join(W, 'out-ahl32')            # python make_out_ahl32.py [ПАПКА] — собрать в другую (проверка)
STALE = os.path.join(W, '_stale')


def has_links(path):
    """Есть ли внутри symlink/junction (такую папку не трогаем — docs/incident-2026-10-09.md)."""
    for root, dirs, files in os.walk(path):
        for n in dirs + files:
            p = os.path.join(root, n)
            if os.path.islink(p) or (hasattr(os.path, 'isjunction') and os.path.isjunction(p)):
                return True
    return False


def main():
    global OUT
    sys.stdout.reconfigure(encoding='utf-8')
    if len(sys.argv) > 1:
        OUT = os.path.abspath(sys.argv[1])
    if os.path.isdir(OUT):
        if has_links(OUT):
            sys.exit(f'в {OUT} есть ссылки (symlink/junction) — разберитесь вручную')
        os.makedirs(STALE, exist_ok=True)
        old = os.path.join(STALE, 'out-ahl32-' + time.strftime('%Y%m%d-%H%M%S'))
        os.replace(OUT, old)
        print(f'прежняя накладка → {old}')
    os.makedirs(os.path.join(OUT, 'db'))
    os.makedirs(os.path.join(OUT, 'fe', 'loc'))
    shutil.copyfile(os.path.join(W, 'roster-ahl32', 'nhlng-equip.db'), os.path.join(OUT, 'db', 'nhlng.db'))
    shutil.copyfile(os.path.join(W, 'roster-ahl32', 'nhlng-meta.xml'), os.path.join(OUT, 'db', 'nhlng-meta.xml'))
    shutil.copyfile(os.path.join(W, 'nhl32-ahl32', 'nhl_eng_us.db'), os.path.join(OUT, 'fe', 'loc', 'NHL_ENG_US.db'))
    main_ids = {p['nhl_id'] for p in json.load(open(os.path.join(W, 'roster', 'write.json'), encoding='utf-8'))['players']}
    extra = [p for p in json.load(open(os.path.join(W, 'roster-ahl32', 'write.json'), encoding='utf-8'))['players']
             if p['nhl_id'] not in main_ids]
    photos = {p['nhl_id']: p for p in json.load(open(os.path.join(W, 'photos-all', 'photos.json'), encoding='utf-8'))}
    n = 0
    for p in extra:
        ph = photos.get(p['nhl_id'])
        if not ph or ph['status'] != 'ok' or ph['artid'] != p['artid']:
            continue
        for rel in ph['files']:
            src = os.path.join(W, 'photos-all', *rel.split('/'))
            dst = os.path.join(OUT, *rel.split('/'))
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copyfile(src, dst)
            n += 1
    print(f'out-ahl32: база, схема, локализация; игроков сверх основной базы {len(extra)}, файлов портретов {n} → {OUT}')


if __name__ == '__main__':
    main()
