"""Свои модели арен в сборку legacy-data: файлы модели в out и exhibitionarena.arenaartid в базах (docs/arenas.md §9).

У клубов на общей модели арены (255 «EA SPORTS Arena» — Юта, Сиэтл, Вегас) цвет кресел один на всех. Своя модель —
копия модели игры под свободным номером (`tools/stadium.py clone`), её цвет кресел — рецепт в tools/arena_seats.toml.
Этот этап по рецептам с `clone_of` (и `arenas` — строки exhibitionarena по полю index):

- status = "approved": файлы копии (stadium, crowd с цветом рецепта, jumbotron, enviro, particle .rvi/.lnb) →
  out/rendering/… (раскладка cache:), в базах out/db и out-ahl32/db строкам `arenas` — arenaartid = номер копии;
- иначе (proposed, keep или рецепт снят): строкам `arenas` — снова arenaartid = clone_of (файлы в out игре не мешают).

Файлы пишутся раньше базы: база в out не ссылается на модель, которой в out нет.

    python tools/legacy_data/arenas.py                    # проба: что поменяется (ничего не пишет)
    python tools/legacy_data/arenas.py --write            # запись (этап build-all.sh arenas); копия баз до правки —
                                                          #   game/work/legacy-data/arenas/backup/<out>-<время>/
    python tools/legacy_data/arenas.py --revert --write   # откат: все строки — на исходные модели
    python tools/legacy_data/arenas.py save СЕЙВ [--write | --out КОПИЯ]
          # сейв ROSTER (таблица exhibitionarena) или франшизы (leaguearena): те же строки по index; --write — на месте,
          # копия до правки — game/work/legacy-data/backup-saves/arenas-<сейв>-<время>/; при запущенной игре не пишет
    --work DIR — папка legacy-data (по умолчанию game/work/legacy-data, как LEGACY_DATA_WORK у build-all.sh)

Повтор ничего не меняет. Строка, у которой arenaartid не исходная и не номер копии (её поменял кто-то другой), не
трогается — в отчёт. draft_roster.db арен не содержит — не меняется.
"""
import argparse
import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
REPO = os.path.dirname(TOOLS)
sys.path.insert(0, TOOLS)
import stadium  # noqa: E402
from tdb import SaveFile, Tdb, load_meta  # noqa: E402

TABLES = ('exhibitionarena', 'leaguearena')        # база и сейв ROSTER — exhibitionarena, франшиза — leaguearena
OUTS = ('out', 'out-ahl32')                         # базы этапа: out/db и накладка «АХЛ на 32»


def say(*a):
    print(*a, flush=True)


def clone_recipes():
    """{номер копии: рецепт} — рецепты arena_seats.toml с clone_of."""
    return {k: r for k, r in stadium.load_recipes().items() if 'clone_of' in r}


def wanted(rec, revert=False):
    """{номер копии: (нужный arenaartid строк, другой допустимый)}: одобренный рецепт — копия, иначе — исходная."""
    out = {}
    for k, r in rec.items():
        on = r.get('status') == 'approved' and not revert
        out[k] = (k, r['clone_of']) if on else (r['clone_of'], k)
    return out


def plan(db, rec, revert=False, tables=TABLES):
    """→ (правки [(таблица, строка, index, название, было, станет)], замечания [текст])."""
    changes, notes = [], []
    want = wanted(rec, revert)
    for t in tables:
        if t not in db.by_name or not db.live_rows(t):
            continue
        by_index = {}
        for row in db.live_rows(t):
            by_index.setdefault(db.value(t, 'index', row, False), []).append(row)
        for k, r in sorted(rec.items()):
            new, other = want[k]
            for idx in r.get('arenas', []):
                rows = by_index.get(idx)
                if not rows:
                    notes.append(f'{t}: нет строки index {idx} ({r.get("club", "")}) — пропуск')
                    continue
                for row in rows:
                    cur = db.get(t, 'arenaartid', row)
                    name = db.value(t, 'arenaname', row, False)
                    if r.get('building') and r['building'].lower() not in name.lower():
                        notes.append(f'{t}[{idx}] «{name}»: в рецепте {k} — «{r["building"]}» (проверьте arenas)')
                    if cur == new:
                        continue
                    if cur != other:
                        notes.append(f'{t}[{idx}] «{name}»: arenaartid {cur}, а не {other}/{new} — не трогаю')
                        continue
                    changes.append((t, row, idx, name, cur, new))
    return changes, notes


def apply(db, changes):
    for t, row, _, _, _, new in changes:
        db.set(t, 'arenaartid', row, new)


def show(changes, notes, pre='  '):
    for t, _, idx, name, cur, new in changes:
        say(f'{pre}{t}[{idx}] {name}: arenaartid {cur} → {new}')
    for n in notes:
        say(f'{pre}! {n}')


def write_files(rec, out, write):
    """Файлы одобренных копий → out (раскладка cache:): копия модели и crowd с цветом рецепта. → [пути]."""
    done = []
    for k, r in sorted(rec.items()):
        if r.get('status') != 'approved':
            continue
        src = r['clone_of']
        if not write:
            for rel, _, n in stadium.clone_files(src, k):
                say(f'  [{k}] {rel} (номер в именах: {n})')
            continue
        for rel, new, n in stadium.write_clone(src, k, out):
            done.append(rel)
            say(f'  [{k}] {rel}{"" if new else " — уже такой"}')
        cr = stadium.Crowd.load(k)                   # = crowd исходной модели (clone_source)
        stadium.apply_rules(cr, r.get('rules', []))
        p, nb = stadium.write_out(k, cr, out)
        say(f'  [{k}] {stadium.CROWD_REL.format(n=k)}: кресла {", ".join(r.get("rules", [])) or "как у EA"} '
            f'(байт цвета: {nb})')
    return done


def cmd_build(a):
    rec = clone_recipes()
    if not rec:
        say('в arena_seats.toml нет рецептов с clone_of — нечего делать')
        return 0
    W = os.path.abspath(a.work)
    out = os.path.join(W, 'out')
    if not os.path.isdir(out):
        sys.exit(f'нет {out} — сначала этап collect (build-all.sh)')
    on = [k for k, r in rec.items() if r.get('status') == 'approved' and not a.revert]
    say(f'свои модели: {", ".join(f"{k} ({rec[k].get("club", "")}, копия {rec[k]["clone_of"]})" for k in sorted(rec))}; '
        f'включены: {on or "нет"}' + (' (--revert)' if a.revert else ''))
    if not a.revert:
        write_files(rec, out, a.write)              # сначала файлы: база не должна ссылаться на то, чего нет
    for k in on if a.write else ():
        miss = [d for s, d in stadium.model_files(rec[k]['clone_of'], k)
                if stadium.PROFILE.extracted(s) and not os.path.isfile(os.path.join(out, *d.split('/')))]
        if miss:
            sys.exit(f'[{k}] в {out} нет {miss} — базу не трогаю')
    stamp = time.strftime('%Y%m%d-%H%M%S')
    total = 0
    for name in OUTS:
        d = os.path.join(W, name, 'db')
        path, meta = os.path.join(d, 'nhlng.db'), os.path.join(d, 'nhlng-meta.xml')
        if not (os.path.isfile(path) and os.path.isfile(meta)):
            say(f'{name}: нет {path} (или схемы рядом) — пропуск')
            continue
        data = open(path, 'rb').read()
        db = Tdb(data, load_meta(meta))
        changes, notes = plan(db, rec, a.revert, ('exhibitionarena',))
        say(f'{name}/db/nhlng.db: правок {len(changes)}')
        show(changes, notes)
        total += len(changes)
        if not (a.write and changes):
            continue
        apply(db, changes)
        db.fix()
        if db.verify():
            sys.exit(f'{path}: CRC после правки не сходятся — не пишу')
        again, _ = plan(Tdb(bytes(db.d), load_meta(meta)), rec, a.revert, ('exhibitionarena',))
        if again:
            sys.exit(f'{path}: повторный план не пуст ({len(again)}) — не пишу')
        bk = os.path.join(W, 'arenas', 'backup', f'{name}-{stamp}')
        os.makedirs(bk, exist_ok=True)
        shutil.copy2(path, os.path.join(bk, 'nhlng.db'))
        open(path + '.part', 'wb').write(bytes(db.d))
        os.replace(path + '.part', path)
        say(f'  записано; копия до правки — {bk}')
    if not a.write:
        say('проба: ничего не записано (--write)')
    elif not total:
        say('базы уже такие')
    return 0


def game_running():
    try:
        out = subprocess.run(['tasklist'], capture_output=True, text=True, errors='replace').stdout
    except OSError:
        return False
    return any('nhl' in line.lower().split(' ')[0] for line in out.splitlines() if line.strip())


def cmd_save(a):
    save = os.path.abspath(a.save)
    if os.path.isdir(save):                         # папка сейва …/ROSTER <время>/ — файл внутри с тем же именем
        save = os.path.join(save, os.path.basename(save))
    if not os.path.isfile(save):
        sys.exit(f'нет файла сейва {save} (нужен файл внутри папки сейва: …/ROSTER <время>/ROSTER <время>)')
    if a.write and a.out:
        sys.exit('или --out (в другой файл), или --write (на месте)')
    meta_p = a.meta or os.path.join(os.path.abspath(a.work), 'out', 'db', 'nhlng-meta.xml')
    meta = load_meta(meta_p)
    raw = open(save, 'rb').read()
    sf = SaveFile(raw, meta)
    bad = sf.verify()
    if bad:
        sys.exit(f'{save}: сейв не проходит проверку ещё до правки: {bad}')
    rec = clone_recipes()
    changes, notes = plan(sf.db, rec, a.revert)
    name = os.path.basename(save)
    say(f'{name}: правок {len(changes)} (таблицы: {", ".join(t for t in TABLES if t in sf.db.by_name) or "нет арен"})')
    show(changes, notes)
    if not (a.write or a.out):
        say('проба: ничего не записано (--out КОПИЯ или --write)')
        return 0
    if not changes:
        say('сейв уже такой — не пишу')
        return 0
    if a.write and game_running():
        sys.exit('запущена игра (tasklist: nhl…) — сейв на месте не пишу; закройте игру')
    apply(sf.db, changes)
    out = sf.bytes(fix=True)
    if len(out) != len(raw):
        sys.exit(f'размер сейва изменился ({len(raw)} → {len(out)}) — не пишу')
    chk = SaveFile(out, meta)
    bad = chk.verify()
    again, _ = plan(chk.db, rec, a.revert)
    if bad or again:
        sys.exit(f'проверка не прошла, ничего не записано: CRC {bad}, повторный план {len(again)}')
    dst = os.path.abspath(a.out) if a.out else save
    if a.write:
        bdir = os.path.join(os.path.abspath(a.work), 'backup-saves', f'arenas-{name}-{time.strftime("%Y%m%d-%H%M%S")}')
        os.makedirs(bdir, exist_ok=True)
        shutil.copy2(save, os.path.join(bdir, name))
        say(f'  копия до правки — {bdir}')
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    open(dst, 'wb').write(out)
    if SaveFile(open(dst, 'rb').read(), meta).verify():
        if a.write:
            open(save, 'wb').write(raw)
        sys.exit('после записи проверка не прошла' + (', сейв возвращён' if a.write else ''))
    say(f'  записано: {dst}; CRC базы и обёртки — OK, размер тот же')
    return 0


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0], formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog=__doc__.split('\n', 2)[2])
    ap.add_argument('cmd', nargs='?', choices=('build', 'save'), default='build')
    ap.add_argument('save', nargs='?', help='сейв (для save)')
    ap.add_argument('--write', action='store_true')
    ap.add_argument('--revert', action='store_true', help='все строки — на исходные модели')
    ap.add_argument('--out', help='save: записать копию сюда')
    ap.add_argument('--meta', help='save: схема базы (по умолчанию out/db/nhlng-meta.xml)')
    ap.add_argument('--work', default=os.environ.get('LEGACY_DATA_WORK') or os.path.join(REPO, 'game', 'work',
                                                                                        'legacy-data'))
    a = ap.parse_args()
    if a.cmd == 'save':
        if not a.save:
            ap.error('save СЕЙВ')
        return cmd_save(a)
    return cmd_build(a)


if __name__ == '__main__':
    sys.exit(main() or 0)
