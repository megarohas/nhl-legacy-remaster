"""Манифест готовых логотипов и копия в общий выход legacy-data (этап build-all, docs/logos-2026.md).

    python tools/logos/outcopy.py manifest OUTDIR            # OUTDIR/manifest.json: путь в cache: → md5, размер
    python tools/logos/outcopy.py copy SRC DST [--dry]       # файлы манифеста SRC → DST (дерево cache:), со сверкой md5
    python tools/logos/outcopy.py check SRC DST              # в DST всё как в манифесте SRC (без записи)

Только стандартная библиотека. copy не трогает в DST ничего, кроме путей манифеста; файл того же пути, но другой —
заменяется (отчёт «заменён»), путь, которого у EA и у нас нет, — добавляется. Повторный запуск ничего не меняет."""
import hashlib
import json
import os
import shutil
import sys


def md5(path):
    h = hashlib.md5()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def files(root):
    out = []
    for dp, _, fs in os.walk(root):
        for f in fs:
            p = os.path.join(dp, f)
            rel = os.path.relpath(p, root).replace('\\', '/')
            if rel == 'manifest.json':
                continue
            out.append(rel)
    return sorted(out)


def make_manifest(root):
    man = {'format': 1, 'files': {}}
    for rel in files(root):
        p = os.path.join(root, *rel.split('/'))
        man['files'][rel] = {'md5': md5(p), 'size': os.path.getsize(p)}
    json.dump(man, open(os.path.join(root, 'manifest.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1,
              sort_keys=True)
    print(f'{root}/manifest.json: файлов {len(man["files"])}, '
          f'{sum(v["size"] for v in man["files"].values()) / 1e6:.1f} МБ')
    return man


def load_manifest(root):
    p = os.path.join(root, 'manifest.json')
    if not os.path.exists(p):
        raise SystemExit(f'{p}: нет манифеста (outcopy.py manifest {root})')
    man = json.load(open(p, encoding='utf-8'))
    bad = [rel for rel, v in man['files'].items()
           if not os.path.exists(os.path.join(root, *rel.split('/'))) or md5(os.path.join(root, *rel.split('/'))) != v['md5']]
    if bad:
        raise SystemExit(f'{root}: файлы не как в манифесте ({len(bad)}): {bad[:5]}')
    return man


def copy(src, dst, dry=False, check_only=False):
    man = load_manifest(src)
    add = rep = same = 0
    for rel, v in sorted(man['files'].items()):
        s = os.path.join(src, *rel.split('/'))
        d = os.path.join(dst, *rel.split('/'))
        if os.path.exists(d):
            if md5(d) == v['md5']:
                same += 1
                continue
            rep += 1
            what = 'заменён'
        else:
            add += 1
            what = 'добавлен'
        if check_only:
            print(f'не как в манифесте: {rel} ({what})')
            continue
        if not dry:
            os.makedirs(os.path.dirname(d), exist_ok=True)
            shutil.copyfile(s, d)
            if md5(d) != v['md5']:
                raise SystemExit(f'{d}: после копии md5 не тот')
        print(f'{what}: {rel}')
    print(f'{dst}: добавлено {add}, заменено {rep}, без изменений {same}' + (' (проба, ничего не записано)' if dry else ''))
    return add + rep


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    a = sys.argv[1:]
    if not a:
        sys.exit(__doc__)
    if a[0] == 'manifest':
        make_manifest(a[1])
    elif a[0] == 'copy':
        copy(a[1], a[2], dry='--dry' in a)
    elif a[0] == 'check':
        sys.exit(1 if copy(a[1], a[2], check_only=True) else 0)
    else:
        sys.exit(__doc__)


if __name__ == '__main__':
    main()
