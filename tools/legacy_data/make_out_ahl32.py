"""Накладка «АХЛ на 32» для NHL Legacy: game/work/legacy-data/out-ahl32 — ставится поверх out
(bash tools/legacy_data/install-legacy-data.sh --ahl32). Берёт базу roster-ahl32 (с портретами и экипировкой), схему и
локализацию nhl32-ahl32 и портреты игроков, которых нет в основной базе (CV/HSK). Вызывается из build-all.sh (collect
--ahl32); draft_roster.db накладки build-all.sh кладёт потом сам (10 таблиц nhlng.db — draft_roster.py).

Игроки CV/HSK — по самой базе roster-ahl32: все, кто в составах фарм-клубов (roster.common.AHL_CLUBS, 224/225); их
портреты — файлы photos-all/fe/ion/artassets/playerheads(small)/<диапазон>/p<artid>.big, если они есть. До 10.10.2026
список брался из roster/write.json, roster-ahl32/write.json и photos-all/photos.json, а они пропали в инциденте 09.10;
результат тот же (сверено: 51 игрок, 39 с портретами, 78 файлов — как в out-ahl32 до правки).

Прежняя накладка не удаляется, а уезжает в game/work/legacy-data/_stale/out-ahl32-<время> (CLAUDE.md: удаление — только в
Корзину или в _stale). Восстановлен 09.10.2026 по транскрипту агента legacy-data (docs/incident-2026-10-09.md).
"""
import os
import shutil
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from install_legacy_data import W  # noqa: E402  (game/work/legacy-data основной копии репозитория)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ['NHL_GAME'] = 'legacy'
from roster import common  # noqa: E402

common.set_game('legacy')
from roster import dbview  # noqa: E402  (после set_game: номера команд Legacy)
from tdb import Tdb  # noqa: E402
from tdb_read import load_meta  # noqa: E402

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


def head_dir(artid):
    """Папка портрета Legacy по artid (docs/legacy-data.md: ≤ 4000, ≤ 8000, ≤ 60000)."""
    return 'p0_4000' if artid <= 4000 else 'p4001_8000' if artid <= 8000 else 'p8001_12000'


def farm_artids(db_path):
    """artid игроков в составах фарм-клубов --ahl32 (CV/HSK) — по базе."""
    db = Tdb(open(db_path, 'rb').read(), load_meta(os.path.join(os.path.dirname(db_path), 'nhlng-meta.xml')))
    v = dbview.View(db)
    rows = {v.row_of_gid[v.link_gid[e['playerindex']]] for e in v.entries
            if e['team'] in common.AHL_CLUBS and v.link_gid.get(e['playerindex']) in v.row_of_gid}
    return sorted({v.g('artid', r) for r in rows})


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
    extra = farm_artids(os.path.join(W, 'roster-ahl32', 'nhlng-equip.db'))
    n = 0
    for a in extra:
        for kind in ('playerheads', 'playerheadssmall'):
            rel = f'fe/ion/artassets/{kind}/{head_dir(a)}/p{a}.big'
            src = os.path.join(W, 'photos-all', *rel.split('/'))
            if not os.path.isfile(src):
                continue
            dst = os.path.join(OUT, *rel.split('/'))
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copyfile(src, dst)
            n += 1
    print(f'out-ahl32: база, схема, локализация; игроков сверх основной базы {len(extra)}, файлов портретов {n} → {OUT}')


if __name__ == '__main__':
    main()
