"""Атрибуты игроков из базы cache: → сохранённый состав пользователя (сейв ROSTER …).

Игра при запуске загружает последний сохранённый состав целиком, вместе с атрибутами, поэтому после установки базы
с новыми рейтингами в игре видны старые, пока они не перенесены в этот сейв (11.10.2026). Переносятся только
атрибуты c_* в exhibitionskaterai / exhibitiongoalieai по game_id (живые строки сейва); growth* и прочее, что игра
считает сама, и все остальные таблицы сейва (правки пользователя, звенья, экипировка) не трогаются. Рядом —
копия сейва в game/work/legacy-data/backup-saves, после записи — проверка CRC и обёртки, при ошибке сейв возвращается.

    python tools/legacy_data/save_sync_ratings.py СЕЙВ [--write]
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from tdb import SaveFile, Tdb, load_meta  # noqa: E402

CACHE_DB = os.path.join(ROOT, 'legacy-port', 'userdata', 'cache', 'guest', 'db')
TABLES = ('exhibitionskaterai', 'exhibitiongoalieai')


def main(save, write=False):
    meta = load_meta(os.path.join(CACHE_DB, 'nhlng-meta.xml'))
    db = Tdb(open(os.path.join(CACHE_DB, 'nhlng.db'), 'rb').read(), meta)
    raw = open(save, 'rb').read()
    sf = SaveFile(raw, meta)
    sv = sf.db
    total = 0
    for t in TABLES:
        fields = [f for f in db.by_name[t]['fields'] if f.startswith('c_')]
        src = {db.get(t, 'game_id', r): r for r in db.live_rows(t)}
        players = values = 0
        for r in sv.live_rows(t):
            s = src.get(sv.get(t, 'game_id', r))
            if s is None:
                continue
            changed = 0
            for f in fields:
                v = db.get(t, f, s)
                if sv.get(t, f, r) != v:
                    sv.set(t, f, r, v)
                    changed += 1
            if changed:
                players += 1
                values += changed
        print(f'{t}: игроков с новыми атрибутами {players}, значений {values}')
        total += players
    if not write or not total:
        print('без --write ничего не записано' if total else 'сейв уже совпадает с базой')
        return
    out = sf.bytes(fix=True)
    assert len(out) == len(raw), 'размер сейва изменился'
    # копия до правки — не в папку сейва (в профиле игры лишних файлов не оставляем), а в backup-saves проекта
    import time
    bdir = os.path.join(ROOT, 'game', 'work', 'legacy-data', 'backup-saves',
                        f'{os.path.basename(save)}-{time.strftime("%Y%m%d-%H%M%S")}')
    os.makedirs(bdir, exist_ok=True)
    bak = os.path.join(bdir, os.path.basename(save) + '.bak')
    open(bak, 'wb').write(raw)
    open(save, 'wb').write(out)
    bad = SaveFile(open(save, 'rb').read(), meta).verify()
    if bad:
        open(save, 'wb').write(raw)
        sys.exit(f'проверка не прошла, сейв возвращён: {bad}')
    print(f'записано; CRC и обёртка — OK; копия до правки — {bak}')


if __name__ == '__main__':
    main(sys.argv[1], '--write' in sys.argv[2:])
