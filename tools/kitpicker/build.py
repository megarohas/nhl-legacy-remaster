"""Выбор форм: страница game/work/kit-picker/index.html (только локально, ассеты EA и NHL 24 — лично).

Для каждого из 32 клубов НХЛ в NHL Legacy: формы, которые сейчас в игре (строки stockteamjerseys базы пользователя,
превью меню jersey_<style>_<art>_<fevariant>.big), и формы клуба из NHL 24 (галерея game/work/nhl24/gallery).
Пользователь отмечает, какие оставить или добавить, и какие две — по умолчанию (дом, выезд); выбор выгружается в JSON.

    game/work/nhl24/venv/Scripts/python.exe tools/kitpicker/build.py
"""
import html
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
sys.path.insert(0, os.path.join(ROOT, 'tools', 'legacy_data'))

import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

import nhl24  # noqa: E402
import locdb  # noqa: E402
import teamart as ta  # noqa: E402
import kitpaint as kp  # noqa: E402
import fepose  # noqa: E402
from tdb import Tdb, load_meta  # noqa: E402

CACHE = os.path.join(ROOT, 'nhl-legacy-port', 'userdata', 'cache', 'guest')
GALLERY = os.path.join(ROOT, 'game', 'work', 'nhl24', 'gallery')
OUT = os.path.join(ROOT, 'game', 'work', 'kit-picker')

# подпись в меню по locstring (у 6 — ключ Vintage_<style>_<art>_<variant>)
LOC_LABEL = {0: 'Home', 1: 'Away', 2: 'Alternate', 3: '2006-07 Home', 4: '2006-07 Away', 5: '2006-07 2nd Home'}
# уже перенесённые формы NHL 24 (пилот CHI): (art, variant) → файл галереи
IN_GAME = {(6, 14): 'adidas_home', (6, 15): 'adidas_away', (6, 6): 'adidas_two'}
CODES = nhl24.CODES[:22] + ['UTA'] + nhl24.CODES[23:] + ['SEA', 'VGK']


def preview(style, art, fev):
    rel = f'fe/ion/artassets/jerseys/jersey_{style}_{art}_{fev}.big'
    p = os.path.join(CACHE, *rel.split('/'))
    data = kp._unchunk(open(p, 'rb').read()) if os.path.isfile(p) else fepose.source(rel, 'legacy')
    if data is None:
        return None, None
    w, h, px = ta.UiLogo(data, rel).decode()
    return Image.fromarray(np.frombuffer(bytes(px), np.uint8).reshape(h, w, 4), 'RGBA'), \
        ('cache' if os.path.isfile(p) else 'ea')


def gallery_kits():
    """{код клуба: [(файл без .png, подпись)]} из game/work/nhl24/gallery/index.html."""
    s = open(os.path.join(GALLERY, 'index.html'), encoding='utf-8').read()
    out, cur = {}, None
    for m in re.finditer(r'<h2 id="([a-z]+)">([A-Z]{3})|<a href="([a-z]+)/([a-z]+_[a-z]+)\.png">.*?<figcaption>(.*?)</figcaption>',
                         s, re.S):
        if m.group(1):
            cur = (m.group(1), m.group(2))
            out.setdefault(cur[1], {'folder': cur[0], 'kits': []})
        elif cur and m.group(3) == cur[0]:
            cap = html.unescape(re.sub(r'<[^>]+>', '', m.group(5)))
            out[cur[1]]['kits'].append((m.group(4), cap.split('—', 1)[-1].strip() if '—' in cap else cap))
    return out


def main():
    db = Tdb(open(os.path.join(CACHE, 'db', 'nhlng.db'), 'rb').read(), load_meta(os.path.join(CACHE, 'db', 'nhlng-meta.xml')))
    loc = locdb.LocDb(open(os.path.join(CACHE, *nhl24.LOC.split('/')), 'rb').read(), load_meta(nhl24.LOC_META))
    texts = {sid.lower(): loc.text(off) for _, sid, off in loc.rows()}   # игра ищет ключ без учёта регистра
    rows = nhl24.rows_of(db)
    gal = gallery_kits()
    alias = {'UTA': None, 'LAK': 'LAK', 'SJS': 'SJS', 'TBL': 'TBL', 'NJD': 'NJD'}
    teams = []
    for code in CODES:
        key = 'ARI' if code == 'UTA' else code
        tid = nhl24.CLUBS[key][0]
        name = db.get_string('exhibitionteams', 'fullname', tid).replace('®', '').replace('™', '').strip()
        legacy = []
        for r in sorted((r for r in rows if r['teamid'] == tid), key=lambda r: r['jerseyindex']):
            s, a, v, fev = r['style'], r['teamartid'], r['variant'], r['fevariant']
            label = texts.get(f'vintage_{s}_{a}_{v}', '') if r['locstring'] == 6 else LOC_LABEL.get(r['locstring'], '')
            img, src = preview(s, a, fev)
            rel = None
            if img is not None:
                rel = f'legacy/{code}/{s}_{a}_{v}.png'
                os.makedirs(os.path.join(OUT, 'legacy', code), exist_ok=True)
                img.save(os.path.join(OUT, *rel.split('/')))
            legacy.append({'id': f'L:{s}_{a}_{v}', 'kit': f'{s}_{a}_{v}', 'ji': r['jerseyindex'], 'label': label or '—',
                           'default': r['isdefault'], 'loc': r['locstring'], 'img': rel,
                           'nhl24': IN_GAME.get((a, v)) if code == 'CHI' and s == 1 else None})
        g = gal.get(alias.get(code, code)) if code != 'UTA' else None
        nhl = []
        if g:
            for fn, cap in g['kits']:
                cut = fn.split('_')[0]
                nhl.append({'id': f'N:{fn}', 'kit': fn, 'cut': {'adidas': 'adidas', 'rbk': 'Reebok', 'nineties': '90-е'}.get(cut, cut),
                            'label': cap, 'thumb': f'../nhl24/gallery/{g["folder"]}/thumbs/{fn}.png',
                            'img': f'../nhl24/gallery/{g["folder"]}/{fn}.png'})
        teams.append({'code': code, 'name': name, 'legacy': legacy, 'nhl24': nhl})
        print(code, name, len(legacy), len(nhl), flush=True)
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, 'data.js'), 'w', encoding='utf-8') as f:
        f.write('window.KITDATA = ' + json.dumps({'teams': teams}, ensure_ascii=False) + ';\n')
    print('ok', OUT)


if __name__ == '__main__':
    main()
