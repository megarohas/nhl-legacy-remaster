"""Портреты игроков АХЛ без ID НХЛ: фото leaguestat (assets.leaguestat.com/ahl/240x240/<id>.jpg, однотонный серый
фон, кэш photos/ahl/<id>.jpg — скачивает `python -m roster.ahl_ht players`) → прозрачный фон → кадр портретов НХЛ
(photos_other.to_nhl_frame) → photos/20262027/<nhl_id>.png, как у прочих портретов; дальше — tools/photos.py build.

JPG → PNG — средствами Windows (PowerShell, System.Drawing), фон — заливка от верхнего края и боков (верхние 2/3
кадра) по близости к цвету фона, край — полупрозрачный. Сеть не нужна. Фото принадлежат лиге: только для личного
использования, лежат в game/ (вне git).

    python -m roster.ht_photos PLAYERS_JSON [--sheet HTML]
"""
import json
import os
import statistics
import subprocess
import sys
from collections import deque

if __package__ in (None, ''):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    __package__ = 'roster'
os.environ.setdefault('NHL_GAME', 'legacy')

from . import common  # noqa: E402
from .common import read_json, write_json  # noqa: E402

THR = 34          # близость к цвету фона (евклидово расстояние RGB)


def to_png(pairs):
    """[(jpg, png)] → PNG через System.Drawing (одним запуском PowerShell)."""
    todo = [(j, p) for j, p in pairs if os.path.exists(j) and not os.path.exists(p)]
    if not todo:
        return 0
    lst = os.path.join(os.path.dirname(todo[0][1]), '_convert.txt')
    os.makedirs(os.path.dirname(lst), exist_ok=True)
    with open(lst, 'w', encoding='utf-8') as f:
        for j, p in todo:
            f.write(f'{os.path.abspath(j)}|{os.path.abspath(p)}\n')
    ps = ("Add-Type -AssemblyName System.Drawing; "
          f"Get-Content -Encoding UTF8 '{lst}' | ForEach-Object {{ $a = $_ -split '\\|'; "
          "$im = [System.Drawing.Image]::FromFile($a[0]); $im.Save($a[1], [System.Drawing.Imaging.ImageFormat]::Png); "
          "$im.Dispose() }")
    subprocess.run(['powershell', '-NoProfile', '-NonInteractive', '-Command', ps], check=True, capture_output=True)
    os.remove(lst)
    return len(todo)


def key_background(rgba, w, h):
    """Однотонный фон → прозрачный (заливка от верха и боков в верхних 2/3)."""
    px = lambda x, y: rgba[(y * w + x) * 4:(y * w + x) * 4 + 3]
    border = [px(x, 0) for x in range(w)] + [px(0, y) for y in range(h * 2 // 3)] + \
        [px(w - 1, y) for y in range(h * 2 // 3)]
    bg = [statistics.median(c[i] for c in border) for i in range(3)]
    near = lambda c: sum((c[i] - bg[i]) ** 2 for i in range(3)) <= THR * THR
    out = bytearray(rgba)
    seen = bytearray(w * h)
    q = deque()
    for x in range(w):
        q.append((x, 0))
    for y in range(h * 2 // 3):
        q.append((0, y))
        q.append((w - 1, y))
    while q:
        x, y = q.popleft()
        i = y * w + x
        if seen[i] or not near(px(x, y)):
            continue
        seen[i] = 1
        out[i * 4 + 3] = 0
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if 0 <= nx < w and 0 <= ny < h and not seen[ny * w + nx]:
                q.append((nx, ny))
    for y in range(h):                          # край: соседи фона — полупрозрачные
        for x in range(w):
            i = y * w + x
            if seen[i]:
                continue
            if any(0 <= x + dx < w and 0 <= y + dy < h and seen[(y + dy) * w + x + dx]
                   for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))):
                out[i * 4 + 3] = 160
    return bytes(out), sum(seen) / (w * h)


def run(players_json, log=print):
    from . import photos_other as po
    data = read_json(players_json)
    game = common.game_dir()
    ph = po._ph('legacy')
    d = po.photo_dir(game)
    manifest_fn = os.path.join(d, '_other.json')
    manifest = read_json(manifest_fn, {}) or {}
    ref = po.nhl_reference(game)
    cache = os.path.join(game, 'work', 'roster-cache')
    todo = [p for p in data['players'] if p.get('ht_only') and p.get('ht_photo')]
    pairs = [(os.path.join(cache, *p['ht_photo'].split('/')),
              os.path.join(cache, 'photos', 'ahl-png', os.path.basename(p['ht_photo'])[:-4] + '.png')) for p in todo]
    conv = to_png(pairs)
    counts = {}
    for p, (jpg, png) in zip(todo, pairs):
        dst = os.path.join(d, f"{p['nhl_id']}.png")
        if os.path.exists(dst) and str(p['nhl_id']) in manifest:
            counts['уже в кадре НХЛ'] = counts.get('уже в кадре НХЛ', 0) + 1
            continue
        if not os.path.exists(png):
            counts['нет фото'] = counts.get('нет фото', 0) + 1
            continue
        w, h, rgba = ph.png_read(png)
        keyed, share = key_background(rgba, w, h)
        if share < 0.15:
            counts['фон не нашёлся'] = counts.get('фон не нашёлся', 0) + 1
            continue
        img, geo = po.to_nhl_frame(keyed, w, h, ref)
        if img is None:
            counts['кадр не найден'] = counts.get('кадр не найден', 0) + 1
            continue
        ph.png_write(dst, 336, 336, img)
        manifest[str(p['nhl_id'])] = {'source': f"leaguestat {p['ahl'].get('ht_id')}",
                                      'raw': os.path.relpath(jpg, game).replace(os.sep, '/'), 'geometry': geo,
                                      'background': round(share, 2), 'name': f"{p['first']} {p['last']}",
                                      'team': p['team']}
        counts['приведено к кадру НХЛ'] = counts.get('приведено к кадру НХЛ', 0) + 1
    write_json(manifest_fn, dict(sorted(manifest.items(), key=lambda kv: int(kv[0]))))
    log(f'ht_photos: JPG → PNG {conv}; {counts} → {d}')
    return counts


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    common.set_game('legacy')
    run(sys.argv[1])
