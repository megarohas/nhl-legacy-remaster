"""NHL Legacy Remaster — редактор ассетов и составов (docs/editor.md).

Запуск: приложение editor\\NHL Legacy Editor.exe в папке игры (кнопка «Редактор» в лаунчере; окно — Electron,
tools/editor/electron, сервер — этот код с --app-mode) или из репозитория:
    python tools/editor [--install ПАПКА_ИГРЫ] [--port N] [--no-window] [--lang ru|en]

Редактор поднимает HTTP-сервер на 127.0.0.1 (только этот ПК). В приложении окно — Electron, сервер на случайном порту
с ключом сессии, диалоги — через окно (winui.BRIDGE). Из репозитория окно — Microsoft Edge (или Chrome) в режиме
приложения со своим профилем в cache\\editor\\browser. Закрыли окно — редактор завершается. Пишет только в
content\\my (ассеты) и saves\\rosters (новый ростер); при запущенной игре ничего не пишет.
"""
import argparse
import base64
import hashlib
import io
import json
import mimetypes
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
import traceback
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
for p in (HERE, TOOLS):
    if p not in sys.path:
        sys.path.insert(0, p)

import catalog  # noqa: E402
import gamedb  # noqa: E402
import gamefs  # noqa: E402
import tex  # noqa: E402
import winui  # noqa: E402
from gamefs import EditorError  # noqa: E402

FROZEN = getattr(sys, 'frozen', False)
WEB = os.path.join(getattr(sys, '_MEIPASS', HERE), 'web') if FROZEN else os.path.join(HERE, 'web')
REPO = os.path.dirname(TOOLS)


def version():
    for p in (os.path.join(getattr(sys, '_MEIPASS', ''), 'VERSION'), os.path.join(REPO, 'VERSION')):
        try:
            return open(p, encoding='utf-8').read().strip()
        except OSError:
            pass
    return 'dev'


class Editor:
    def __init__(self, install, lang='ru'):
        self.fs = gamefs.GameFS(install)
        gamefs.INSTALL = self.fs.install
        self.db = gamedb.GameDb(self.fs)
        self.cat = catalog.Catalog(self.fs, self.db)
        self.lang = lang
        self.last_ping = time.time()
        self.lock = threading.Lock()          # запись — по одной
        self._conts = {}
        self.settings_path = os.path.join(self.fs.saves.saves_root or self.fs.install, 'settings',
                                          'nhllegacy_editor.json') if self.fs.saves.saves_root else \
            os.path.join(self.fs.work, 'settings.json')
        self.settings = {}
        try:
            self.settings = json.load(open(self.settings_path, encoding='utf-8'))
        except (OSError, ValueError):
            pass
        if 'lang' in self.settings and lang is None:
            self.lang = self.settings['lang']
        self.rosters = None
        threading.Thread(target=self.db.load, daemon=True).start()

    def save_settings(self):
        try:
            os.makedirs(os.path.dirname(self.settings_path), exist_ok=True)
            json.dump(self.settings, open(self.settings_path, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        except OSError:
            pass

    def t(self, ru, en):
        return ru if self.lang == 'ru' else en

    # ------------------------------------------------------------ файлы и текстуры
    def container(self, rel, below_my=False):
        """Разобранный файл (текстуры) с кэшем по (rel, откуда, mtime)."""
        hit = self.fs.find(rel)
        if hit is None:
            return None
        if below_my and hit[0] == gamefs.Source.MY:
            key = (rel.lower(), 'below')
        else:
            key = (rel.lower(), hit[0], hit[1], os.path.getmtime(hit[2]) if hit[2] else 0)
        c = self._conts.get(key)
        if c is None:
            data = self.fs.read(rel, below_my=below_my)
            if data is None:
                return None
            c = tex.load(data, rel)
            if len(self._conts) > 48:
                self._conts.pop(next(iter(self._conts)))
            self._conts[key] = c
        return c

    def file_info(self, rel):
        hit = self.fs.find(rel)
        info = dict(rel=rel, exists=hit is not None, in_my=self.fs.in_my(rel), textures=[], kind=None, error=None)
        if hit is None:
            return info
        src, where, path = hit
        info['source'] = src
        info['where'] = where
        info['sources'] = [s for s, _ in self.fs.sources(rel)]
        try:
            c = self.container(rel)
            info['kind'] = c.kind
            for r in c.rasters:
                d = r.info()
                d['label'] = catalog.raster_label(r.name, self.lang) if c.kind == 'rw4' else (
                    self.t('Картинка', 'Image') if len(c.rasters) == 1 else r.name)
                info['textures'].append(d)
            order = ['jersey_', 'pant_', 'sock_', 'font_', 'name_']
            info['textures'].sort(key=lambda d: next((k for k, p in enumerate(order) if d['name'].startswith(p)),
                                                     len(order)))
            if c.kind == 'bigf' and c.stage:
                info['stage'] = c.stage
        except Exception as e:                       # noqa: BLE001
            info['error'] = str(e)
            info['kind'] = 'raw'
        if rel.lower().endswith('.rx2'):
            info['mesh'] = self.mesh_summary(rel)
        return info

    def mesh_summary(self, rel):
        try:
            import meshes
            return meshes.summary(self.fs.read(rel), rel)
        except Exception:                            # noqa: BLE001
            return None

    def asset(self, aid):
        a = self.cat.asset(aid, self.lang)
        if a is None:
            raise EditorError('no_asset', f'Нет ассета {aid}', f'No asset {aid}')
        files = []
        for f in a['files']:
            info = self.file_info(f['rel'])
            if not info['exists'] and f.get('template') and self.fs.exists(f['template']):
                tpl = self.file_info(f['template'])
                info.update(textures=tpl['textures'], kind=tpl['kind'], from_template=True)
            files.append(dict(f, **info))
        a['files'] = files
        return a

    def tex_png(self, rel, i, side=None, below=False):
        c = self.container(rel, below_my=below)
        if c is None:
            raise EditorError('no_file', f'Нет файла {rel}', f'No file {rel}')
        r = c.rasters[int(i)]
        im = tex.thumb(c, r, side) if side else tex.decode(c, r)
        return tex.png_bytes(im)

    def thumb_png(self, rel, i=0, side=150, stage=True, crop=None):
        """Плитка выбора: картинка (у превью меню — только сцена Apt в углу текстуры; crop — (x, y, w, h) в точках
        текстуры), уменьшенная до side."""
        key = (rel.lower(), i, side, stage, crop)
        cache = self.__dict__.setdefault('_thumbs', {})
        if key in cache:
            return cache[key]
        c = self.container(rel)
        if c is None:
            raise EditorError('no_file', f'Нет файла {rel}', f'No file {rel}')
        r = c.rasters[i]
        im = tex.decode(c, r, max_side=max(side * 2, 256))
        st = getattr(c, 'stage', None)
        if crop:
            k = im.size[0] / r.w
            x, y, w, h = crop
            im = im.crop((round(x * k), round(y * k), round((x + w) * k), round((y + h) * k)))
        elif stage and st and im.size == (r.w, r.h) and st[0] <= r.w and st[1] <= r.h:
            im = im.crop((0, 0, st[0], st[1]))
        im.thumbnail((side, side))
        png = tex.png_bytes(im)
        if len(cache) > 2000:
            cache.clear()
        cache[key] = png
        return png

    # ------------------------------------------------------------ выгрузка
    @staticmethod
    def export_names(asset_files, conts):
        """[(имя PNG, rel, номер растра, растр)] — имена уникальны в ассете."""
        out, used = [], set()
        for f in asset_files:
            c = conts.get(f['rel'])
            if c is None:
                continue
            base = f['rel'].split('/')[-1].rsplit('.', 1)[0]
            for r in c.rasters:
                if not r.ok:
                    continue
                if c.kind == 'rw4':
                    n = r.name.split('.')[0]
                else:
                    folder = f['rel'].split('/')[-2] if '/' in f['rel'] else ''
                    n = f'{folder}_{base}' if folder else base
                    if len(c.rasters) > 1:
                        n += f'_{r.name}'
                k = n
                j = 2
                while k.lower() in used:
                    k = f'{n}_{j}'
                    j += 1
                used.add(k.lower())
                out.append((k + '.png', f['rel'], r.index, r))
        return out

    def pick_folder(self, title):
        start = self.settings.get('export_dir') or os.path.join(os.path.expanduser('~'), 'Desktop')
        d = winui.pick_folder(title, start)
        if d:
            self.settings['export_dir'] = d
            self.save_settings()
        return d

    def export_asset(self, aid, only=None):
        """Все текстуры ассета → <папка>/<имя ассета>/*.png + asset.json; only = (rel, i) — одна текстура в PNG."""
        a = self.cat.asset(aid, self.lang)
        if only:
            rel, i = only
            c = self.container(rel)
            r = c.rasters[int(i)]
            names = self.export_names([dict(rel=rel)], {rel: c})
            fname = next((n for n, rr, ii, _ in names if ii == int(i)), f'{r.name}.png')
            start = self.settings.get('export_dir') or os.path.join(os.path.expanduser('~'), 'Desktop')
            p = winui.save_file(self.t('Выгрузить картинку', 'Export image'), start, fname,
                                [('PNG', '*.png')], 'png')
            if not p:
                return None
            self.settings['export_dir'] = os.path.dirname(p)
            self.save_settings()
            tex.decode(c, r).save(p, 'PNG')
            return dict(written=[p], folder=os.path.dirname(p))
        d = self.pick_folder(self.t('Куда выгрузить', 'Export to folder'))
        if not d:
            return None
        safe = ''.join(ch if ch not in '<>:"/\\|?*' else '_' for ch in a.get('export_name') or aid).strip()
        out = os.path.join(d, safe)
        os.makedirs(out, exist_ok=True)
        conts = {}
        for f in a['files']:
            try:
                c = self.container(f['rel'])
            except Exception:                         # noqa: BLE001
                c = None
            if c is not None:
                conts[f['rel']] = c
        man = dict(asset=aid, title=a['title'], tool='nhllegacy_editor', version=version(), images=[])
        written = []
        for name, rel, i, r in self.export_names(a['files'], conts):
            im = tex.decode(conts[rel], r)
            p = os.path.join(out, name)
            im.save(p, 'PNG')
            written.append(p)
            man['images'].append(dict(png=name, rel=rel, index=i, raster=r.name, w=r.w, h=r.h, fmt=r.fmt_name,
                                      sha1=hashlib.sha1(im.convert('RGBA').tobytes()).hexdigest()))
        json.dump(man, open(os.path.join(out, 'asset.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        return dict(written=written, folder=out)

    # ------------------------------------------------------------ импорт
    def _load_image(self, data):
        from PIL import Image
        im = Image.open(io.BytesIO(data))
        im.load()
        return im.convert('RGBA')

    def apply(self, changes, label, templates=None):
        """changes — [(rel, номер растра, картинка)] → новые файлы в content\\my. → отчёт."""
        gamefs.check_game_closed()
        by_file = {}
        for rel, i, im in changes:
            by_file.setdefault(rel, []).append((int(i), im))
        backup = None
        done, notes = [], []
        jerseys = []                                     # (S, A, V, старый свитер, новый) — для превью в меню
        with self.lock:
            for rel, items in by_file.items():
                data = self.fs.read(rel)
                if data is None and (templates or {}).get(rel):       # нового фото ещё нет — по образцу
                    data = self.fs.read(templates[rel])
                if data is None:
                    raise EditorError('no_file', f'Нет файла {rel}', f'No file {rel}')
                c = tex.load(data, rel)
                m = re.fullmatch(r'rendering/jersey/texlib_(\d+)_(\d+)_(\d+)\.rx2', rel.lower())
                for i, im in items:
                    r = c.rasters[i]
                    if m and re.fullmatch(r'jersey_.*_cm\.raster', r.name.lower()) and not r.name.lower().endswith(
                            '_nm.raster'):
                        jerseys.append((*(int(x) for x in m.groups()), tex.decode(c, r), im))
                    for n in tex.replace(c, r, im):
                        notes.append(f'{r.name}: {n}')
                out = c.bytes()
                if rel.lower().startswith('fe/ion/artassets/playerheads/') and len(out) > 34672:
                    notes.append(self.t(f'{rel}: {len(out)} байт — больше самого большого портрета EA (34 672)',
                                        f'{rel}: {len(out)} bytes — larger than the largest EA portrait (34,672)'))
                if backup is None and any(self.fs.in_my(x) for x in by_file):
                    backup = self.fs.backup_dir()
                self.fs.write_my(rel, out, backup)
                done.append(rel)
            if jerseys and self.settings.get('auto_fe', True) and not any(
                    r.lower().startswith('fe/ion/artassets/jerseys/') for r in by_file):
                for s_, a_, v_, old, new in jerseys:
                    done_fe, note = self._fe_update(s_, a_, v_, old, new, backup)
                    done += done_fe
                    notes += note
        self._conts.clear()
        self.log(f'{label}: {", ".join(done)}' + (f' ({"; ".join(notes)})' if notes else ''))
        return dict(written=done, notes=notes, my=[self.fs.my_path(r) for r in done])

    def fe_rels(self, s_, a_, v_):
        """Превью меню комплекта S_A_V: jersey_S_A_F.big по fevariant строк формы (нет строк — F = V)."""
        self.db.load()
        fs_ = sorted({k['f'] for ks in self.db.kits.values() for k in ks if (k['s'], k['a'], k['v']) == (s_, a_, v_)})
        return [f'fe/ion/artassets/jerseys/jersey_{s_}_{a_}_{f}.big' for f in (fs_ or [v_])]

    def _fe_update(self, s_, a_, v_, old, new, backup=None):
        """Превью меню после правки свитера (fepreview.transfer). → ([записанные], [заметки])."""
        import fepreview
        mp = fepreview.model_path(self.fs)
        if not mp:
            return [], [self.t('превью в меню не пересобрано: нет модели позы (content\\uniforms\\editor\\fepose.bin) — '
                               'замените превью вручную', 'menu preview not rebuilt: no pose model '
                               '(content\\uniforms\\editor\\fepose.bin) — replace the preview by hand')]
        model = fepreview.load(mp)
        out, notes = [], []
        for rel in self.fe_rels(s_, a_, v_):
            data = self.fs.read(rel)
            if data is None:
                continue
            c = tex.load(data, rel)
            r = c.rasters[0]
            prev = tex.decode(c, r)
            newp, n = fepreview.transfer(prev, old, new, model)
            if not n:
                continue
            tex.replace(c, r, newp)
            self.fs.write_my(rel, c.bytes(), backup)
            out.append(rel)
            notes.append(self.t(f'превью в меню {rel.split("/")[-1]} пересобрано ({n} точек)',
                                f'menu preview {rel.split("/")[-1]} rebuilt ({n} pixels)'))
        return out, notes

    def fe_rebuild(self, aid):
        """Кнопка «Пересобрать превью по свитеру»: разница свитера против оригинала (без content\\my) → превью."""
        kind, _, rest = aid.partition(':')
        if kind != 'kit':
            raise EditorError('not_kit', 'Это не форма', 'Not a kit')
        s_, a_, v_, _f = (int(x) for x in rest.split(':')[1].split('_'))
        rel = f'rendering/jersey/texlib_{s_}_{a_}_{v_}.rx2'
        cur, base = self.container(rel), self.container(rel, below_my=True)
        if cur is None or base is None:
            raise EditorError('no_file', f'Нет файла {rel}', f'No file {rel}')
        ri = next(i for i, r in enumerate(cur.rasters) if re.fullmatch(r'jersey_.*_cm\.raster', r.name.lower()))
        new, old = tex.decode(cur, cur.rasters[ri]), tex.decode(base, base.rasters[ri])
        gamefs.check_game_closed()
        fe = self.fe_rels(s_, a_, v_)
        with self.lock:
            backup = self.fs.backup_dir()
            for r in fe:                                    # от превью «как было», а не от прошлой пересборки
                if self.fs.in_my(r):
                    self.fs.revert(r, backup)
            self._conts.clear()
            done, notes = self._fe_update(s_, a_, v_, old, new, backup)
        self._conts.clear()
        self.log(f'превью меню: {", ".join(done) or "без изменений"}')
        return dict(written=done, notes=notes or [self.t('свитер как в оригинале — превью оригинальное',
                                                         'the jersey is as original — the preview is original')])

    def import_one(self, rel, i, data=None, template=None):
        if data is None:
            start = self.settings.get('import_dir') or self.settings.get('export_dir')
            p = winui.pick_file(self.t('Картинка для импорта', 'Image to import'), start,
                                [(self.t('Картинки', 'Images'), '*.png;*.jpg;*.jpeg;*.bmp;*.tga;*.webp;*.dds'),
                                 ('*', '*.*')])
            if not p:
                return None
            self.settings['import_dir'] = os.path.dirname(p)
            self.save_settings()
            data = open(p, 'rb').read()
        return self.apply([(rel, i, self._load_image(data))], 'импорт картинки', {rel: template} if template else None)

    def import_folder(self, aid):
        start = self.settings.get('import_dir') or self.settings.get('export_dir')
        d = winui.pick_folder(self.t('Папка с картинками (выгрузка редактора)', 'Folder with images (editor export)'),
                              start)
        if not d:
            return None
        self.settings['import_dir'] = d
        self.save_settings()
        a = self.cat.asset(aid, self.lang)
        conts = {f['rel']: self.container(f['rel']) for f in a['files'] if self.fs.exists(f['rel'])}
        conts = {k: v for k, v in conts.items() if v is not None}
        man = {}
        mp = os.path.join(d, 'asset.json')
        if os.path.isfile(mp):
            try:
                for e in json.load(open(mp, encoding='utf-8')).get('images', []):
                    man[e['png'].lower()] = e
            except (OSError, ValueError):
                pass
        changes, skipped, unknown = [], [], []
        names = {n.lower(): (n, rel, i) for n, rel, i, _ in self.export_names(a['files'], conts)}
        for fn in sorted(os.listdir(d)):
            if not fn.lower().endswith('.png'):
                continue
            hit = names.get(fn.lower())
            if hit is None:
                unknown.append(fn)
                continue
            im = self._load_image(open(os.path.join(d, fn), 'rb').read())
            e = man.get(fn.lower())
            if e and e.get('sha1') == hashlib.sha1(im.tobytes()).hexdigest():
                skipped.append(fn)
                continue
            changes.append((hit[1], hit[2], im))
        if not changes:
            raise EditorError('nothing', self.t('В папке нет изменённых картинок этого ассета', ''),
                              'No changed images of this asset in the folder')
        rep = self.apply(changes, 'импорт папки')
        rep['skipped'], rep['unknown'] = skipped, unknown
        return rep

    def import_raw(self, rel):
        start = self.settings.get('import_dir')
        p = winui.pick_file(self.t(f'Файл игры для {rel.split("/")[-1]}', f'Game file for {rel.split("/")[-1]}'),
                            start, [('*', '*.*')])
        if not p:
            return None
        data = open(p, 'rb').read()
        gamefs.check_game_closed()
        with self.lock:
            self.fs.write_my(rel, data)
        self._conts.clear()
        self.log(f'импорт файла {p} → {rel}')
        return dict(written=[rel])

    def export_raw(self, rel):
        data = self.fs.read(rel)
        if data is None:
            raise EditorError('no_file', f'Нет файла {rel}', f'No file {rel}')
        start = self.settings.get('export_dir') or os.path.join(os.path.expanduser('~'), 'Desktop')
        p = winui.save_file(self.t('Выгрузить файл игры', 'Export game file'), start, rel.split('/')[-1])
        if not p:
            return None
        open(p, 'wb').write(data)
        return dict(written=[p], folder=os.path.dirname(p))

    def revert(self, rels):
        gamefs.check_game_closed()
        backup, done = None, []
        with self.lock:
            for rel in rels:
                if self.fs.in_my(rel):
                    backup = backup or self.fs.backup_dir()
                    self.fs.revert(rel, backup)
                    done.append(rel)
        self._conts.clear()
        if done:
            self.log(f'вернуть как было: {", ".join(done)} (копия — {backup})')
        return dict(reverted=done, backup=backup)

    def log(self, text):
        try:
            os.makedirs(self.fs.work, exist_ok=True)
            with open(os.path.join(self.fs.work, 'editor.log'), 'a', encoding='utf-8') as f:
                f.write(time.strftime('%Y-%m-%d %H:%M:%S ') + text + '\n')
        except OSError:
            pass

    def info(self):
        self.db.load()
        fs = self.fs
        return dict(version=version(), install=fs.install, content=fs.content, layout_ok=fs.ok(),
                    game_root=fs.game_root, ea_files=len(fs.ea.index) if fs.ea.ready.is_set() else None,
                    ea_error=fs.ea.error, running=gamefs.game_running(fs.install), lang=self.lang,
                    db=self.db.db_path, roster=self.db.roster_path, names_from=self.db.source,
                    my_count=len(fs.my_files()), db_error=self.db.error,
                    auto_fe=self.settings.get('auto_fe', True))


# ---------------------------------------------------------------- HTTP

class Handler(BaseHTTPRequestHandler):
    ed = None
    protocol_version = 'HTTP/1.1'

    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype='application/json; charset=utf-8', cache=False):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode('utf-8')
        elif isinstance(body, str):
            body = body.encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'max-age=60' if cache else 'no-store')
        if self._cookie:
            self.send_header('Set-Cookie', self._cookie)
        self.end_headers()
        self.wfile.write(body)

    def _err(self, e):
        if isinstance(e, EditorError):
            return self._send(400, dict(error=e.code, message=self.ed.t(e.ru, e.en)))
        self.ed.log('ошибка: ' + traceback.format_exc())
        return self._send(500, dict(error='internal', message=f'{type(e).__name__}: {e}'))

    token = None              # режим приложения: ключ сессии (Electron передаёт его в адресе, дальше — cookie)
    _cookie = None

    def _auth(self, q):
        """Режим приложения: запросы — только с ключом этой сессии (адрес со случайным портом и ключом знает только
        окно приложения, другие программы на ПК к серверу не подключатся)."""
        if not self.token:
            return True
        if q.get('token') == self.token:
            self._cookie = f'nhlt={self.token}; Path=/; HttpOnly; SameSite=Strict'
            return True
        for part in (self.headers.get('Cookie') or '').split(';'):
            k, _, v = part.strip().partition('=')
            if k == 'nhlt' and v == self.token:
                return True
        self._send(403, dict(error='forbidden', message='no token'))
        return False

    def do_GET(self):
        ed = self.ed
        u = urllib.parse.urlparse(self.path)
        q = {k: v[-1] for k, v in urllib.parse.parse_qs(u.query).items()}
        if not self._auth(q):
            return
        try:
            if u.path in ('/', '/index.html'):
                return self._static('index.html')
            if u.path.startswith('/static/'):
                return self._static(u.path[len('/static/'):])
            if u.path == '/api/ping':
                ed.last_ping = time.time()
                return self._send(200, dict(ok=True, running=gamefs.game_running(ed.fs.install)))
            if u.path == '/api/info':
                return self._send(200, ed.info())
            if u.path == '/api/tree':
                return self._send(200, ed.cat.children(q.get('node', ''), ed.lang))
            if u.path == '/api/path':
                return self._send(200, ed.cat.path(q['id']))
            if u.path == '/api/asset':
                return self._send(200, ed.asset(q['id']))
            if u.path == '/api/file':
                return self._send(200, ed.file_info(q['rel']))
            if u.path == '/api/tex':
                side = int(q['side']) if q.get('side') else None
                png = ed.tex_png(q['rel'], q.get('i', 0), side, q.get('below') == '1')
                return self._send(200, png, 'image/png')
            if u.path == '/api/thumb':
                crop = tuple(int(x) for x in q['crop'].split(',')) if q.get('crop') else None
                return self._send(200, ed.thumb_png(q['rel'], int(q.get('i', 0)), int(q.get('side', 150)),
                                                     q.get('stage') == '1', crop), 'image/png', cache=True)
            if u.path == '/api/my':
                return self._send(200, dict(files=[dict(rel=r, part=__import__('legacy_paths').part_for(r))
                                                   for r in ed.fs.my_files()]))
            if u.path.startswith('/api/x/'):
                return self._ext('GET', u.path[len('/api/x/'):], q, None)
            return self._send(404, dict(error='not_found'))
        except Exception as e:                       # noqa: BLE001
            return self._err(e)

    def do_POST(self):
        ed = self.ed
        u = urllib.parse.urlparse(self.path)
        if not self._auth({}):
            return
        n = int(self.headers.get('Content-Length') or 0)
        body = self.rfile.read(n) if n else b''
        try:
            a = json.loads(body.decode('utf-8')) if body else {}
        except ValueError:
            a = {}
        try:
            p = u.path
            if p == '/api/lang':
                ed.lang = a.get('lang', 'ru')
                ed.settings['lang'] = ed.lang
                ed.save_settings()
                return self._send(200, dict(ok=True))
            if p == '/api/export':
                only = (a['rel'], a.get('i', 0)) if a.get('rel') is not None else None
                return self._send(200, ed.export_asset(a['id'], only) or dict(cancelled=True))
            if p == '/api/import':
                data = base64.b64decode(a['data']) if a.get('data') else None
                return self._send(200, ed.import_one(a['rel'], a.get('i', 0), data, a.get('template')) or
                                  dict(cancelled=True))
            if p == '/api/import_folder':
                return self._send(200, ed.import_folder(a['id']) or dict(cancelled=True))
            if p == '/api/export_raw':
                return self._send(200, ed.export_raw(a['rel']) or dict(cancelled=True))
            if p == '/api/import_raw':
                return self._send(200, ed.import_raw(a['rel']) or dict(cancelled=True))
            if p == '/api/kit_new':
                import kitnew
                return self._send(200, kitnew.create(ed, a['id'], int(a.get('loc', 2)), a.get('label')))
            if p == '/api/fe_rebuild':
                return self._send(200, ed.fe_rebuild(a['id']))
            if p == '/api/auto_fe':
                ed.settings['auto_fe'] = bool(a.get('on'))
                ed.save_settings()
                return self._send(200, dict(ok=True))
            if p == '/api/revert':
                return self._send(200, ed.revert(a.get('rels') or [a['rel']]))
            if p == '/api/open_folder':
                path = a.get('path')
                if path and os.path.exists(path):
                    os.startfile(path if os.path.isdir(path) else os.path.dirname(path))
                return self._send(200, dict(ok=True))
            if p == '/api/quit':
                self._send(200, dict(ok=True))
                threading.Thread(target=lambda: (time.sleep(0.3), os._exit(0)), daemon=True).start()
                return
            if p.startswith('/api/x/'):
                return self._ext('POST', p[len('/api/x/'):], {}, a)
            return self._send(404, dict(error='not_found'))
        except Exception as e:                       # noqa: BLE001
            return self._err(e)

    def _ext(self, method, name, q, a):
        """Разделы-модули: составы (rosters.py), звук (audio.py), сетки (meshes.py)."""
        mod, _, fn = name.partition('/')
        import importlib
        if mod not in ('rosters', 'audio', 'meshes', 'texts'):
            return self._send(404, dict(error='not_found'))
        m = importlib.import_module(mod)
        res = m.handle(self.ed, method, fn, q, a)
        if isinstance(res, tuple):
            body, ctype = res
            return self._send(200, body, ctype)
        return self._send(200, res if res is not None else dict(cancelled=True))

    def _static(self, name):
        if name == 'icon.png' and not os.path.isfile(os.path.join(WEB, name)):
            return self._send(200, icon_png(), 'image/png', cache=True)
        p = os.path.normpath(os.path.join(WEB, name))
        if not p.startswith(os.path.normpath(WEB)) or not os.path.isfile(p):
            return self._send(404, 'not found', 'text/plain')
        ctype = mimetypes.guess_type(p)[0] or 'application/octet-stream'
        if ctype.startswith('text/') or ctype in ('application/javascript',):
            ctype += '; charset=utf-8'
        return self._send(200, open(p, 'rb').read(), ctype)


_ICON = None


def icon_png():
    """Значок окна: иконка лаунчера (tools/make_icon.py → nhl-legacy-port/launcher/icon, не в git; в exe — своя копия)."""
    global _ICON
    if _ICON is None:
        from PIL import Image
        for p in (os.path.join(getattr(sys, '_MEIPASS', ''), 'nhllegacy.ico'),
                  os.path.join(REPO, 'nhl-legacy-port', 'launcher', 'icon', 'nhllegacy-1024.jpg'),
                  os.path.join(REPO, 'nhl-legacy-port', 'launcher', 'icon', 'nhllegacy.ico')):
            if os.path.isfile(p):
                im = Image.open(p)
                im = im.convert('RGBA')
                im.thumbnail((128, 128))
                _ICON = tex.png_bytes(im)
                break
        else:
            from PIL import Image
            _ICON = tex.png_bytes(Image.new('RGBA', (32, 32), (34, 120, 230, 255)))
    return _ICON


# ---------------------------------------------------------------- окно

def browser_exe():
    cands = []
    for env in ('ProgramFiles(x86)', 'ProgramFiles', 'LOCALAPPDATA'):
        base = os.environ.get(env)
        if base:
            cands += [os.path.join(base, 'Microsoft', 'Edge', 'Application', 'msedge.exe'),
                      os.path.join(base, 'Google', 'Chrome', 'Application', 'chrome.exe')]
    return next((c for c in cands if os.path.isfile(c)), None)


def open_window(url, profile, pos=None):
    """Окно интерфейса: Edge/Chrome в режиме приложения со своим профилем. Фоновый режим браузера выключен (закрыли
    окно — процесс браузера завершается), таймеры свёрнутого окна не замедляются (пинг редактору раз в 3 с)."""
    exe = browser_exe()
    if not exe:
        import webbrowser
        webbrowser.open(url)
        return None
    os.makedirs(profile, exist_ok=True)
    args = [exe, f'--app={url}', f'--user-data-dir={profile}', '--no-first-run', '--no-default-browser-check',
            '--disable-features=Translate,msEdgeSidebarV2,msUndersideButton', '--disable-sync',
            '--disable-background-mode', '--disable-background-timer-throttling', '--disable-renderer-backgrounding',
            '--window-size=1500,920', '--lang=' + ('ru' if 'lang=ru' in url else 'en-US')]
    if pos:
        args.append(f'--window-position={pos}')
    flags = 0x08000000 if os.name == 'nt' else 0      # CREATE_NO_WINDOW
    return subprocess.Popen(args, creationflags=flags)


def watch_parent(pid):
    """Завершить сервер, когда завершится процесс pid (окно приложения закрыто или упало)."""
    if os.name != 'nt':
        return
    import ctypes
    k32 = ctypes.windll.kernel32
    h = k32.OpenProcess(0x00100000, False, pid)          # SYNCHRONIZE
    if not h:
        os._exit(0)
    k32.WaitForSingleObject(h, 0xFFFFFFFF)
    os._exit(0)


def serve_app(ed, a, install):
    """Сервер для окна приложения (tools/editor/electron/main.js): случайный порт, ключ, «READY <порт>» в stdout,
    диалоги — через приложение (winui.BRIDGE)."""
    import secrets
    Handler.ed = ed
    Handler.token = a.token or secrets.token_hex(16)
    srv = ThreadingHTTPServer(('127.0.0.1', a.port), Handler)
    srv.daemon_threads = True
    port = srv.server_address[1]
    for f in (sys.stdin, sys.stdout):        # канал с окном — UTF-8 (у собранного exe по умолчанию — кодировка системы)
        try:
            f.reconfigure(encoding='utf-8')
        except (AttributeError, ValueError):
            pass
    winui.BRIDGE = (sys.stdin, sys.stdout)
    if a.parent_pid:
        threading.Thread(target=watch_parent, args=(a.parent_pid,), daemon=True).start()
    ed.log(f'запуск {version()} (приложение): {install}, порт {port}')
    sys.stdout.write(f'READY {port}\n')
    sys.stdout.flush()
    try:
        srv.serve_forever()
    finally:
        ed.log('выход')
    return 0


def default_install():
    if FROZEN:                    # <игра>\editor\backend\nhllegacy_editor_server.exe → <игра>
        d = os.path.dirname(os.path.abspath(sys.executable))
        for _ in range(3):
            if os.path.isfile(os.path.join(d, 'nhllegacy.exe')):
                return d
            d = os.path.dirname(d)
        return os.path.dirname(os.path.abspath(sys.executable))
    import legacy_paths
    return legacy_paths.DEFAULT_INSTALL


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--install', help='папка игры (nhllegacy.exe); по умолчанию — папка exe редактора')
    p.add_argument('--port', type=int, default=0, help='порт сервера (0 — свободный)')
    p.add_argument('--no-window', action='store_true', help='не открывать окно (адрес — в выводе)')
    p.add_argument('--lang', choices=['ru', 'en'], help='язык окна')
    p.add_argument('--window-pos', help='X,Y окна (для снимков: за краем экрана)')
    p.add_argument('--app-mode', action='store_true',
                   help='сервер для приложения (Electron): без окна и без editor.lock, ключ --token, диалоги — через '
                        'stdin/stdout, выход вместе с процессом --parent-pid; в stdout — «READY <порт>»')
    p.add_argument('--token', help='ключ сессии (режим приложения)')
    p.add_argument('--parent-pid', type=int, help='завершиться, когда завершится этот процесс')
    a = p.parse_args(argv)
    if a.app_mode:
        a.no_window = True
    install = os.path.abspath(a.install or default_install())
    if not os.path.isfile(os.path.join(install, 'nhllegacy.exe')) and not os.path.isfile(
            os.path.join(install, 'nhllegacy.toml')):
        msg = f'Редактор не нашёл игру: в {install} нет nhllegacy.exe. Папка editor должна лежать в папке игры (editor\\NHL Legacy Editor.exe рядом с nhllegacy.exe).'
        if FROZEN:
            winui.message(msg, error=True)
        sys.exit(msg)
    lang = a.lang
    if lang is None:
        import re
        tl = os.path.join(install, 'saves', 'settings', 'nhllegacy_launcher.toml')
        try:
            m = re.search(r'launcher_language\s*=\s*"(\w+)"', open(tl, encoding='utf-8').read())
            lang = m.group(1) if m else None
        except OSError:
            pass
    ed = Editor(install, lang or 'ru')
    if a.lang:
        ed.lang = a.lang
    elif 'lang' in ed.settings:
        ed.lang = ed.settings['lang']
    if a.app_mode:
        return serve_app(ed, a, install)
    # уже открыт — показать его окно
    lockf = os.path.join(ed.fs.work, 'editor.lock')
    try:
        import urllib.request
        port = int(open(lockf).read().strip())
        ok = json.load(urllib.request.urlopen(f'http://127.0.0.1:{port}/api/ping', timeout=1)).get('ok')
        if ok:
            if not a.no_window:
                open_window(f'http://127.0.0.1:{port}/?lang={ed.lang}', os.path.join(ed.fs.work, 'browser'),
                            a.window_pos)
            return 0
    except (OSError, ValueError):
        pass
    Handler.ed = ed
    srv = ThreadingHTTPServer(('127.0.0.1', a.port), Handler)
    srv.daemon_threads = True
    port = srv.server_address[1]
    os.makedirs(ed.fs.work, exist_ok=True)
    open(lockf, 'w').write(str(port))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f'http://127.0.0.1:{port}/?lang={ed.lang}'
    ed.log(f'запуск {version()}: {install}, {url}')
    print(url, flush=True)
    proc = None if a.no_window else open_window(url, os.path.join(ed.fs.work, 'browser'), a.window_pos)
    ed.last_ping = time.time()
    try:
        while True:
            time.sleep(1)
            idle = time.time() - ed.last_ping
            if a.no_window:
                continue
            # окно закрыто: процесс браузера вышел и страница больше не пингует (5 с); браузер остался жить или
            # окно — обычный браузер: страница молчит 3 минуты (пинг раз в 3 с)
            if proc is not None and proc.poll() is not None and idle > 5:
                break
            if idle > 180:
                break
    except KeyboardInterrupt:
        pass
    finally:
        try:
            os.remove(lockf)
        except OSError:
            pass
        if proc is not None and proc.poll() is None:
            proc.terminate()
        ed.log('выход')
    return 0


if __name__ == '__main__':
    sys.exit(main())
