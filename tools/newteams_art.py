"""Арт новых клубов (Seattle, Vegas) в базе: номера логотипов, прожектор, арена. По умолчанию — только
показ плана (dry-run), база не пишется.

    python newteams_art.py [DB] [--meta META]                    # план: «поле: сейчас → будет»
    python newteams_art.py [DB] --out OUT.db                     # записать изменённую копию (CRC пересчитываются)
        [--spotlight]          # прожекторы на выходе команды — логотип клуба (spotlight 45/46 вместо 36)
        [--jerseys]            # stockteamjerseys.teamartid строк клуба = новый artid (как у всех клубов EA)
        [--stadium 601,602]    # 3D-модель арены (exhibitionarena.arenaartid) вместо 255 «EA SPORTS Arena»
        [--centerline N,M]     # рисунок красной линии (ice_cline_N), сейчас 0 — сплошная
        [--in-place]           # разрешить OUT = DB (иначе отказ)
        [--game legacy]        # NHL Legacy (tools/gameprofile.py): SEA/VGK — арт 100/101, прожекторы 46/47, арены 187/188

DB по умолчанию — game/userdata/cache/guest/db/nhlng.db (рядом nhlng-meta.xml); для Legacy — db/nhlng.db в cache:
порта Legacy (gameprofile: строка «CACHE:» статуса legacy-port или NHL_LEGACY_CACHE), лучше указать явно — например
базу nhl32 legacy-data (game/work/legacy-data/nhl32/nhlng.db). База другой игры, чем --game, — отказ (check_db). Файлы арта под эти номера
собирает tools/teamart.py (game/work/logos/out → game/userdata/cache/guest). Почему именно эти поля —
docs/logos-arenas.md:
  * exhibitionteams.artid — номер всех логотипов интерфейса (t/s/d/c/w/r<artid>.big), центра льда хозяина
    (rendering/icesurface/centerlogo_<artid>_cm.rx2), шайбы (puck_<artid>_cm.rx2), баннера, а также
    текстур формы: rendering/jersey/texlib_<style>_<artid>_<variant>.rx2, name_…, pant/texlib_…, sock/sock_…,
    logo/texlib_<artid>_<style>_<variant>.rx2 (номер берётся из поля artid команды, не из stockteamjerseys).
  * exhibitionteams.spotlight — rendering/spotlight/texlib_<N>.rx2 (логотип, который прожекторы рисуют на льду).
  * exhibitionteams.table = 1 — «созданная команда»: центр льда собирается из конструктора, шайба 255 и т. д.
    У новых клубов должно быть 0 (проверяется).
  * exhibitionarena.arenatype — 0: площадка НХЛ (ice_nhl_Container_0), 1: международная (ice_intl_Container_0).
"""
import argparse, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tdb import SaveFile                      # noqa: E402
from tdb_read import load_meta                # noqa: E402
import gameprofile                            # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DB = os.path.join(HERE, '..', 'game', 'userdata', 'cache', 'guest', 'db', 'nhlng.db')

# строка exhibitionteams: аббревиатура (для проверки), artid, spotlight, арена (строка exhibitionarena)
TEAMS_BY_GAME = {
    'nhl13': {
        30: dict(abbr='SEA', artid=98, spotlight=45, arena=174, arena_name='Climate Pledge Arena'),
        31: dict(abbr='VGK', artid=99, spotlight=46, arena=175, arena_name='T-Mobile Arena'),
    },
    # NHL Legacy (база — tools/nhl32.py у legacy-data): арт 98/99 заняты (Vaasan Sport, KooKoo) → 100/101; файлы
    # прожекторов у Legacy texlib_0…45 → 46/47; арены — копии «EA SPORTS Arena» (181) в конце таблицы
    'legacy': {
        30: dict(abbr='SEA', artid=100, spotlight=46, arena=187, arena_name='Climate Pledge Arena'),
        31: dict(abbr='VGK', artid=101, spotlight=47, arena=188, arena_name='T-Mobile Arena'),
    },
}
TEAMS = TEAMS_BY_GAME['nhl13']
OLD_ART = {93, 94}                            # Tappara, TPS — их арт не трогаем (у Legacy те же номера)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('db', nargs='?')
    ap.add_argument('--meta')
    ap.add_argument('--out')
    ap.add_argument('--in-place', action='store_true')
    ap.add_argument('--spotlight', action='store_true')
    ap.add_argument('--jerseys', action='store_true')
    ap.add_argument('--stadium')
    ap.add_argument('--centerline')
    gameprofile.add_argument(ap)
    a = ap.parse_args()
    P = gameprofile.get(a.game)
    TEAMS = TEAMS_BY_GAME[P.name]
    if a.db is None:
        if P.name == 'nhl13':
            a.db = DEFAULT_DB
        elif P.install:
            a.db = os.path.join(P.install, 'db', 'nhlng.db')
        else:
            sys.exit(f'{P.title}: папка cache: порта не известна — укажите DB')
    meta_path = a.meta or os.path.join(os.path.dirname(os.path.abspath(a.db)), 'nhlng-meta.xml')
    raw = open(a.db, 'rb').read()
    gameprofile.check_db(P, raw)
    s = SaveFile(raw, load_meta(meta_path))
    db = s.db
    T, A, J = 'exhibitionteams', 'exhibitionarena', 'stockteamjerseys'
    stadiums = [int(x) for x in a.stadium.split(',')] if a.stadium else None
    clines = [int(x) for x in a.centerline.split(',')] if a.centerline else None
    plan, problems = [], []

    def want(table, field, row, value, why):
        cur = db.get(table, field, row)
        plan.append((table, field, row, cur, value, why))

    art_rows = {}                             # только живые записи (tdb.Tdb.live_rows; у базы — все строки)
    for r in db.live_rows(T):
        art_rows.setdefault(db.get(T, 'artid', r), []).append(r)
    for i, (row, t) in enumerate(TEAMS.items()):
        abbr = db.get_string(T, 'abbrname', row)
        if abbr != t['abbr']:
            problems.append(f'строка {row}: аббревиатура «{abbr}», ожидалась {t["abbr"]}')
        others = [r for r in art_rows.get(t['artid'], []) if r != row]
        if others:
            problems.append(f'artid {t["artid"]} уже у строк {others}')
        if db.get(T, 'table', row):
            problems.append(f'строка {row}: table = 1 (созданная команда) — центр льда и шайба будут от конструктора')
        want(T, 'artid', row, t['artid'], 'логотипы, центр льда, шайба, баннер, текстуры формы')
        if a.spotlight:
            want(T, 'spotlight', row, t['spotlight'], 'логотип прожекторов на выходе команды')
        arena = db.get(T, 'arenaid', row)
        if arena != t['arena']:
            problems.append(f'строка {row}: arenaid {arena}, ожидалась {t["arena"]}')
        elif db.is_live(A, arena):
            name = db.get_string(A, 'arenaname', arena)
            if name != t['arena_name']:
                problems.append(f'арена {arena}: «{name}», ожидалась «{t["arena_name"]}»')
            if db.get(A, 'arenatype', arena) != 0:
                want(A, 'arenatype', arena, 0, 'площадка НХЛ 200×85 футов')
            if stadiums:
                want(A, 'arenaartid', arena, stadiums[i], '3D-модель арены')
            if clines:
                want(A, 'centerline', arena, clines[i], 'рисунок красной линии')
        if a.jerseys:
            for jr in db.live_rows(J):
                if db.get(J, 'teamid', jr) == row:
                    want(J, 'teamartid', jr, t['artid'], 'номер арта комплекта (UI)')
    for n in OLD_ART:
        rows = art_rows.get(n, [])
        if rows and any(r in TEAMS for r in rows):
            problems.append(f'artid {n} (Tappara/TPS) у новых клубов — не должно быть')

    print(f'база: {os.path.abspath(a.db)}')
    for table, field, row, cur, value, why in plan:
        mark = '  ' if cur == value else '→ '
        print(f'{mark}{table}[{row}].{field}: {cur} → {value}   ({why})')
    for p in problems:
        print('ВНИМАНИЕ:', p)
    changes = [p for p in plan if p[3] != p[4]]
    print(f'изменений: {len(changes)}')
    if not a.out:
        print('dry-run: база не записана (нужен --out)')
        return
    if os.path.abspath(a.out) == os.path.abspath(a.db) and not a.in_place:
        sys.exit('OUT совпадает с DB — нужен --in-place')
    if problems:
        sys.exit('есть замечания — запись отменена')
    for table, field, row, cur, value, why in changes:
        db.set(table, field, row, value)
    data = s.bytes()
    check = SaveFile(data, load_meta(meta_path))
    if check.verify():
        sys.exit('CRC не сходятся после записи — файл не сохранён')
    open(a.out, 'wb').write(data)
    print(f'записано: {a.out} ({len(data)} байт), CRC сходятся')


if __name__ == '__main__':
    main()
