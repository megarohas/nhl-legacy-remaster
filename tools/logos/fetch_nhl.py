"""Официальные SVG логотипов клубов НХЛ (assets.nhle.com) → game/work/logos/src/nhl-2026/ (вне git: только для
личного использования). Только эти файлы, пауза между запросами ≥ 1 с; уже скачанное не качается заново.

    python tools/logos/fetch_nhl.py [ABBR…] [--variants light,dark] [--out ПАПКА]

Список клубов — tools/logos/clubs.json (поле "nhle"). Рядом пишется manifest.json: URL, размер, sha256, ETag и
Last-Modified ответа, время скачивания."""
import hashlib, json, os, sys, time, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
URL = 'https://assets.nhle.com/logos/nhl/svg/{abbr}_{variant}.svg'
PAUSE = 1.2


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    args = sys.argv[1:]
    out = os.path.join(ROOT, 'game', 'work', 'logos', 'src', 'nhl-2026')
    variants = ['light', 'dark']
    if '--out' in args:
        i = args.index('--out'); out = args[i + 1]; del args[i:i + 2]
    if '--variants' in args:
        i = args.index('--variants'); variants = args[i + 1].split(','); del args[i:i + 2]
    clubs = json.load(open(os.path.join(HERE, 'clubs.json'), encoding='utf-8'))['nhl']
    abbrs = [c['nhle'] for c in clubs]
    if args:
        abbrs = [a for a in abbrs if a in args]
    os.makedirs(out, exist_ok=True)
    mpath = os.path.join(out, 'manifest.json')
    man = json.load(open(mpath, encoding='utf-8')) if os.path.exists(mpath) else {}
    last = 0.0
    for abbr in abbrs:
        for v in variants:
            name = f'{abbr}_{v}.svg'
            path = os.path.join(out, name)
            if os.path.exists(path) and name in man:
                continue
            wait = PAUSE - (time.time() - last)
            if wait > 0:
                time.sleep(wait)
            url = URL.format(abbr=abbr, variant=v)
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (personal game mod; logos fetch)'})
            last = time.time()
            try:
                with urllib.request.urlopen(req, timeout=60) as r:
                    data = r.read()
                    hdr = {k: r.headers.get(k) for k in ('ETag', 'Last-Modified', 'Content-Type')}
            except Exception as e:
                print(f'{name}: ОШИБКА {e}')
                continue
            if not data.lstrip().startswith((b'<svg', b'<?xml')):
                print(f'{name}: не SVG ({data[:40]!r}) — не сохранён')
                continue
            open(path, 'wb').write(data)
            man[name] = dict(url=url, size=len(data), sha256=hashlib.sha256(data).hexdigest(),
                             fetched=time.strftime('%Y-%m-%d %H:%M:%S'), **hdr)
            json.dump(man, open(mpath, 'w', encoding='utf-8'), ensure_ascii=False, indent=1, sort_keys=True)
            print(f'{name}: {len(data)} байт, {hdr.get("Last-Modified")}')
    print(f'файлов в манифесте: {len(man)} → {out}')


if __name__ == '__main__':
    main()
