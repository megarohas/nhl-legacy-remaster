"""Чистка форм: страница со всеми формами 32 клубов, которые сейчас в игре; галочка — оставить, снял — форма уйдёт.

Только локально: на странице превью из архивов EA и формы NHL 24/27 (личное, наружу не публиковать).
Сервер слушает только 127.0.0.1. Выбор пишется сам при каждом клике — game/work/kit-prune/selection.json.

    python tools/kitpicker/prune.py build          # game/work/kit-prune: страница, data.js, img/<клуб>/<форма>.png
    python tools/kitpicker/prune.py serve [--port 8765]   # http://127.0.0.1:8765
    python tools/kitpicker/prune.py show           # что отмечено на удаление, по клубам

Python — game/work/nhl24/venv (нужны numpy и Pillow на этапе build). Без сервера страница тоже откроется (index.html):
выбор тогда живёт в браузере и выгружается кнопкой «Сохранить файл». Описание — docs/kit-prune.md.
"""
import argparse
import http.server
import json
import os
import re
import shutil
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
sys.path.insert(0, os.path.join(ROOT, 'tools', 'legacy_data'))

PAGE = os.path.join(HERE, 'prune_page')
OUT = os.path.join(ROOT, 'game', 'work', 'kit-prune')
DATA = os.path.join(OUT, 'data.json')
CHOICE = os.path.join(OUT, 'selection.json')
PORT = 8765

# группы на странице, порядок — как в карточках клуба. Формы edge_* стоят по умолчанию: без них клуб останется без
# формы дома или в гостях, поэтому их не снять (locked)
GROUPS = (('edge', 'NHL 27: по умолчанию'), ('adidas', 'Наши: adidas из NHL 24'), ('nhl24', 'Наши: NHL 24'),
          ('old', 'Наши: первые формы'), ('ea_main', 'EA: Home и Away'), ('ea_alt', 'EA: Alternate'),
          ('ea_event', 'EA: Classic и Stadium'), ('ea_past', 'EA: прошлые сезоны'), ('ea_0607', 'EA: 2006-07'),
          ('ea_retro', 'EA: ретро'))
OUR_KITS = {'edge_home': 'edge', 'edge_away': 'edge', 'ad_home': 'adidas', 'ad_away': 'adidas'}   # остальное в реестре — nhl24
OUR_ARTS = (100, 101, 104)      # SEA, VGK, UTA: строки базы, которых нет у EA


def group_of(row, label, kit):
    """row — строка stockteamjerseys, label — подпись в меню, kit — имя формы в реестре nhl24_kits.json или None."""
    if kit:
        return OUR_KITS.get(kit, 'nhl24')
    if row['teamartid'] in OUR_ARTS:
        return 'old'
    if 'Classic' in label or 'Stadium' in label:
        return 'ea_event'
    if label.startswith('2006-07'):
        return 'ea_0607'
    if label == 'Alternate':
        return 'ea_alt'
    if label in ('Home (EA)', 'Away (EA)'):
        return 'ea_main'
    year = re.match(r'(\d{4})-', label)
    if not year:
        sys.exit(f'{row["style"]}_{row["teamartid"]}_{row["variant"]}: не знаю группу для подписи «{label}»')
    return 'ea_past' if int(year.group(1)) > 2006 else 'ea_retro'


def copy_page():
    os.makedirs(OUT, exist_ok=True)
    for name in os.listdir(PAGE):
        shutil.copyfile(os.path.join(PAGE, name), os.path.join(OUT, name))


def cmd_build(args):
    import locdb
    import nhl24
    from tdb import Tdb, load_meta
    from build import CACHE, CODES, LOC_LABEL, preview        # соседний kitpicker/build.py

    db = Tdb(open(os.path.join(CACHE, 'db', 'nhlng.db'), 'rb').read(), load_meta(os.path.join(CACHE, 'db', 'nhlng-meta.xml')))
    loc = locdb.LocDb(open(os.path.join(CACHE, *nhl24.LOC.split('/')), 'rb').read(), load_meta(nhl24.LOC_META))
    texts = {sid.lower(): loc.text(off) for _, sid, off in loc.rows()}   # игра ищет ключ без учёта регистра
    reg = {(k.get('style', 1), k['art'], k['variant']): k['kit'] for k in nhl24.load_registry()['kits']}
    rows = nhl24.rows_of(db)
    order = {g: i for i, (g, _) in enumerate(GROUPS)}
    teams = []
    for code in sorted(CODES):
        tid = nhl24.CLUBS['ARI' if code == 'UTA' else code][0]
        name = db.get_string('exhibitionteams', 'fullname', tid).replace('®', '').replace('™', '').strip()
        kits = []
        for r in sorted((r for r in rows if r['teamid'] == tid), key=lambda r: r['jerseyindex']):
            s, a, v = r['style'], r['teamartid'], r['variant']
            label = texts.get(f'vintage_{s}_{a}_{v}', '') if r['locstring'] == 6 else LOC_LABEL.get(r['locstring'], '')
            if not label:
                sys.exit(f'{code} {s}_{a}_{v}: нет подписи в меню')
            group = group_of(r, label, reg.get((s, a, v)))
            if group == 'edge' and not r['isdefault']:
                sys.exit(f'{code} {s}_{a}_{v}: форма NHL 27 не по умолчанию — пересмотрите группы на странице')
            img = preview(s, a, r['fevariant'])[0]
            if img is None:
                sys.exit(f'{code} {s}_{a}_{v}: нет превью')
            rel = f'img/{code}/{s}_{a}_{v}.png'
            os.makedirs(os.path.join(OUT, 'img', code), exist_ok=True)
            img.save(os.path.join(OUT, *rel.split('/')))
            kits.append({'id': f'{s}_{a}_{v}', 'label': label, 'group': group, 'img': rel,
                         'locked': bool(r['isdefault'])})
        kits.sort(key=lambda k: order[k['group']])          # sorted устойчив: внутри группы — порядок меню игры
        teams.append({'code': code, 'name': name, 'kits': kits})
        print(code, name, len(kits), flush=True)
    data = {'teams': teams, 'groups': [{'id': g, 'title': t} for g, t in GROUPS]}
    copy_page()
    with open(DATA, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False)
    with open(os.path.join(OUT, 'data.js'), 'w', encoding='utf-8') as f:
        f.write('window.KITS = ' + json.dumps(data, ensure_ascii=False) + ';\n')
    print('форм:', sum(len(t['kits']) for t in teams), '→', OUT)


def known_ids():
    if not os.path.isfile(DATA):
        sys.exit(f'нет {DATA}: сначала prune.py build')
    data = json.load(open(DATA, encoding='utf-8'))
    return {k['id'] for t in data['teams'] for k in t['kits'] if not k['locked']}, data


class Handler(http.server.SimpleHTTPRequestHandler):
    known = frozenset()

    def __init__(self, *a, **kw):
        super().__init__(*a, directory=OUT, **kw)

    def end_headers(self):
        if not self.path.endswith('.png'):                  # выбор и страница — всегда свежие, превью не перечитывать
            self.send_header('Cache-Control', 'no-store')
        super().end_headers()

    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path == '/selection.json' and not os.path.isfile(CHOICE):
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(b'{"remove": []}')
            return
        super().do_GET()

    def do_POST(self):
        if self.path != '/selection':
            return self.send_error(404)
        size = int(self.headers.get('Content-Length') or 0)
        try:                                                # текст send_error уходит в строку статуса — только латиница
            remove = json.loads(self.rfile.read(min(size, 1 << 20)))['remove']
            bad = set(remove) - self.known
        except (ValueError, KeyError, TypeError):
            return self.send_error(400, 'expected {"remove": [...]}')
        if bad:
            return self.send_error(400, f'unknown or locked kits: {sorted(bad)[:5]}')
        with open(CHOICE + '.part', 'w', encoding='utf-8') as f:
            json.dump({'saved': time.strftime('%Y-%m-%d %H:%M:%S'), 'remove': sorted(remove)}, f, ensure_ascii=False)
        os.replace(CHOICE + '.part', CHOICE)
        self.send_response(204)
        self.end_headers()


def cmd_serve(args):
    p = argparse.ArgumentParser(prog='prune.py serve')
    p.add_argument('--port', type=int, default=PORT)
    a = p.parse_args(args)
    Handler.known = frozenset(known_ids()[0])
    copy_page()
    srv = http.server.ThreadingHTTPServer(('127.0.0.1', a.port), Handler)
    print(f'http://127.0.0.1:{a.port}  выбор: {CHOICE}', flush=True)
    srv.serve_forever()


def cmd_show(args):
    known, data = known_ids()
    if not os.path.isfile(CHOICE):
        sys.exit('выбора ещё нет: ни одной формы не снято')
    choice = json.load(open(CHOICE, encoding='utf-8'))
    remove = set(choice['remove'])
    print('сохранён', choice['saved'], '· убрать', len(remove), 'из', sum(len(t['kits']) for t in data['teams']))
    titles = dict((g, t) for g, t in GROUPS)
    for t in data['teams']:
        gone = [k for k in t['kits'] if k['id'] in remove]
        if gone:
            print(f"{t['code']}: {len(t['kits']) - len(gone)} остаётся из {len(t['kits'])}")
            for k in gone:
                print(f"   {k['id']:10} {k['label']:20} {titles[k['group']]}")


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
    cmds = {'build': cmd_build, 'serve': cmd_serve, 'show': cmd_show}
    if len(sys.argv) < 2 or sys.argv[1] not in cmds:
        sys.exit(__doc__)
    cmds[sys.argv[1]](sys.argv[2:])


if __name__ == '__main__':
    main()
