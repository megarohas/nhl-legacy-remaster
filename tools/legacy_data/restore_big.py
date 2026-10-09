"""Справочное дерево NHL Legacy (game/other/legacy/big/<архив>/…) — сверка с диском и дораспаковка недостающего.

Каждый архив game/other/legacy/disc/<архив>.big распаковывается заново (tools/big.py extract, свой пул процессов на
архивы) во временную папку game/work/legacy-data/extract/fresh/<архив>/ и сравнивается с деревом:
  - файла нет в дереве — копируется из свежей распаковки;
  - файл есть, но отличается — прежний уезжает в game/work/legacy-data/_stale/other-legacy-big-<время>/<архив>/…,
    на место — свежий;
  - лишние файлы дерева (которых нет в архиве) не трогаются — только в отчёт.
Отчёт — TSV (действие, архив, путь, байт, md5 прежнего, md5 нового) в game/work/legacy-data/extract/.

    python tools/legacy_data/restore_big.py [АРХИВ…] [--jobs N] [--dry-run] [--keep-fresh]
    python tools/legacy_data/restore_big.py cache --disc game/other/nhl12/disc --big game/other/nhl12/big            --pattern '^fe/ion/fonts/'      # другая игра / только часть архива (шрифты NHL 12 для этапа fonts)

--dry-run — только сравнить; --keep-fresh — не убирать свежую распаковку (иначе она удаляется: своя временная папка,
перед удалением — проверка, что внутри нет ссылок). Восстановление после инцидента 09.10.2026
(docs/incident-2026-10-09.md, docs/legacy-data.md).
"""
import argparse
import concurrent.futures
import hashlib
import os
import re
import shutil
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from install_legacy_data import GAME, W  # noqa: E402

REPO = os.path.dirname(GAME)
DISC = os.path.join(GAME, 'other', 'legacy', 'disc')
BIG = os.path.join(GAME, 'other', 'legacy', 'big')
FRESH = os.path.join(W, 'extract', 'fresh')


def md5(p):
    h = hashlib.md5()
    with open(p, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def tree(base):
    out = {}
    for root, dirs, names in os.walk(base):
        for n in dirs + names:
            p = os.path.join(root, n)
            if os.path.islink(p) or os.path.isjunction(p):
                raise SystemExit(f'ссылка {p} — не трогаю (docs/incident-2026-10-09.md)')
        for n in names:
            p = os.path.join(root, n)
            out[os.path.relpath(p, base).replace(os.sep, '/')] = p
    return out


def extract(name, jobs, pattern=None):
    dst = os.path.join(FRESH, name)
    if os.path.isdir(dst):
        return name, 'уже распакован', 0
    t = time.time()
    r = subprocess.run([sys.executable, os.path.join(REPO, 'tools', 'big.py'), 'extract',
                        os.path.join(DISC, name + '.big'), dst, '--jobs', str(jobs)]
                       + (['--pattern', pattern] if pattern else []),
                       capture_output=True, text=True, encoding='utf-8', errors='replace',
                       env=dict(os.environ, PYTHONIOENCODING='utf-8'))
    tail = (r.stdout + r.stderr).strip().splitlines()[-1:] or ['']
    if r.returncode:
        raise SystemExit(f'{name}: big.py extract — ошибка:\n{r.stdout}{r.stderr}')
    return name, tail[0], time.time() - t


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('archives', nargs='*')
    ap.add_argument('--jobs', type=int, default=4, help='процессов распаковки на архив (big.py --jobs)')
    ap.add_argument('--parallel', type=int, default=3, help='архивов одновременно')
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--keep-fresh', action='store_true')
    ap.add_argument('--disc', help='папка архивов (по умолчанию game/other/legacy/disc)')
    ap.add_argument('--big', help='справочное дерево (по умолчанию game/other/legacy/big)')
    ap.add_argument('--pattern', help='только пути по регулярному выражению (big.py extract --pattern)')
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding='utf-8')
    global DISC, BIG, FRESH
    if a.disc or a.big:
        DISC = os.path.abspath(a.disc or DISC)
        BIG = os.path.abspath(a.big or BIG)
        FRESH = os.path.join(W, 'extract', 'fresh-' + os.path.basename(os.path.dirname(BIG)))
    names = a.archives or sorted(f[:-4] for f in os.listdir(DISC) if f.lower().endswith('.big'))
    os.makedirs(FRESH, exist_ok=True)
    with concurrent.futures.ThreadPoolExecutor(a.parallel) as pool:
        for name, tail, sec in pool.map(lambda n: extract(n, a.jobs, a.pattern), names):
            print(f'{name}: {tail} ({sec:.0f} с)')
    stamp = time.strftime('%Y%m%d-%H%M%S')
    stale = os.path.join(W, '_stale', f'other-legacy-big-{stamp}')
    report = os.path.join(W, 'extract', f'restore_big-{stamp}.tsv')
    rows, totals = [], {}
    for name in names:
        fresh, cur = tree(os.path.join(FRESH, name)), tree(os.path.join(BIG, name))
        if a.pattern:                     # сверяется только эта часть архива
            cur = {k: v for k, v in cur.items() if re.search(a.pattern, k)}
        for rel in sorted(fresh):
            src = fresh[rel]
            if rel not in cur:
                act, old = 'добавлен', ''
            else:
                old = md5(cur[rel])
                if old == md5(src):
                    totals[(name, 'совпал')] = totals.get((name, 'совпал'), 0) + 1
                    continue
                act = 'заменён'
            new = md5(src)
            rows.append((act, name, rel, os.path.getsize(src), old, new))
            totals[(name, act)] = totals.get((name, act), 0) + 1
            if a.dry_run:
                continue
            dst = os.path.join(BIG, name, *rel.split('/'))
            if act == 'заменён':
                keep = os.path.join(stale, name, *rel.split('/'))
                os.makedirs(os.path.dirname(keep), exist_ok=True)
                os.replace(dst, keep)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)
        for rel in sorted(set(cur) - set(fresh)):
            rows.append(('лишний', name, rel, os.path.getsize(cur[rel]), md5(cur[rel]), ''))
            totals[(name, 'лишний')] = totals.get((name, 'лишний'), 0) + 1
    with open(report, 'w', encoding='utf-8', newline='\n') as f:
        f.write('действие\tархив\tпуть\tбайт\tmd5 прежний\tmd5 новый\n')
        for r in rows:
            f.write('\t'.join(map(str, r)) + '\n')
    for name in names:
        parts = ', '.join(f'{k[1]} {v}' for k, v in sorted(totals.items()) if k[0] == name)
        print(f'  {name}: {parts}')
    print(f'{"сухой прогон — " if a.dry_run else ""}отчёт → {report}' + (f'; прежние → {stale}' if os.path.isdir(stale) else ''))
    if not a.keep_fresh and not a.dry_run:
        tree(FRESH)                       # ссылок нет — своя временная папка
        shutil.rmtree(FRESH)
        print(f'свежая распаковка убрана ({FRESH})')


if __name__ == '__main__':
    main()
