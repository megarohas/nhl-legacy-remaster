"""Тексты меню и шрифты в редакторе.

Тексты — строки локализации fe/loc/nhl_<язык>.db (tools/locdb.py, docs/fe-menu-legacy.md): ключ → текст, поиск
по ключу и тексту, правка. Правка, которая влезает в прежнее место строки, пишется на место; длиннее — новой строкой
в конец пула (LocDb.put: другие ключи той же строки не меняются). Символ, которого нет в дереве Хаффмана файла,
не записать — редактор так и скажет. Файл — в content\\my\\fe\\loc, CRC пересчитаны (Tdb.fix), перед записью —
LocDb.check.

Шрифты интерфейса — TrueType, их игра растеризует на лету (атласов глифов нет, docs/fe-fonts.md). Поэтому «картинкой»
выгружается образец текста, а замена — своим TTF/OTF через tools/fefont.py build: подгонка под метрики шрифта игры
(высота прописных, вертикальные метрики, набор символов — как у оригинала EA) или «как есть» (--keep, TrueType того
же unitsPerEm). Результат — content\\my\\fe\\ion\\fonts\\<имя как у игры>.
"""
import io
import os
import shutil

import gamefs
import winui
from gamefs import EditorError

LOC_DIR = 'fe/loc'
FONT_KEYS = {'eahelveticaneueconbol-mod.ttf': 'conbold', 'eahelveticaneuemed-mod.ttf': 'med',
             'eahelveticaneuehv-mod.ttf': 'hv', 'indicatorfont.ttf': 'indicator'}


def _meta(ed, lang):
    from tdb_read import load_meta
    rel = f'{LOC_DIR}/{lang}-meta.xml'
    hit = ed.fs.find(rel)
    if hit is None:
        raise EditorError('no_meta', f'Нет схемы {rel}', f'No schema {rel}')
    if hit[2]:
        return load_meta(hit[2])
    p = os.path.join(ed.fs.work, f'{lang}-meta.xml')
    os.makedirs(ed.fs.work, exist_ok=True)
    open(p, 'wb').write(ed.fs.read(rel))
    return load_meta(p)


def languages(ed):
    out = []
    for rel in ed.fs.list_dir(LOC_DIR, r'\.db$'):
        out.append(rel.split('/')[-1][:-3].lower())
    return sorted(set(out), key=lambda x: (x != 'nhl_eng_us', x))


def load(ed, lang):
    from locdb import LocDb
    rel = f'{LOC_DIR}/{lang}.db'
    data = ed.fs.read(rel)
    if data is None:
        raise EditorError('no_loc', f'Нет файла {rel}', f'No file {rel}')
    return LocDb(data, _meta(ed, lang)), rel


def search(ed, lang, q='', offset=0, limit=200):
    loc, rel = load(ed, lang)
    ql = q.strip().lower()
    rows = []
    total = 0
    for _, sid, off in loc.rows():
        text = loc.text(off)
        if ql and ql not in sid.lower() and ql not in text.lower():
            continue
        total += 1
        if offset <= total - 1 < offset + limit:
            rows.append(dict(key=sid, text=text))
    hit = ed.fs.find(rel)
    return dict(rows=rows, total=total, rel=rel, source=hit[1] if hit else None, in_my=ed.fs.in_my(rel))


def save(ed, lang, edits):
    """edits {ключ: текст} → content\\my\\fe\\loc\\<язык>.db. → отчёт."""
    gamefs.check_game_closed()
    loc, rel = load(ed, lang)
    notes, done = [], 0
    for key, text in edits.items():
        r = loc.find(key)
        try:
            if r is None:
                loc.add(key, text)
                notes.append(ed.t(f'{key}: новый ключ', f'{key}: new key'))
            else:
                try:
                    loc.set_text(loc.text_off_at(r), text)
                except ValueError as e:
                    if 'не влезает' not in str(e) and 'MISSING' not in str(e) and '0xFFFFFFFF' not in str(e):
                        raise
                    loc.put(key, text)
        except (ValueError, KeyError) as e:
            raise EditorError('loc', f'{key}: {e}', f'{key}: {e}')
        done += 1
    bad = loc.check()
    if bad:
        raise EditorError('loc_check', 'Проверка строк не прошла, ничего не записано: ' + '; '.join(bad[:3]),
                          'String check failed, nothing written: ' + '; '.join(bad[:3]))
    loc.db.fix()
    with ed.lock:
        ed.fs.write_my(rel.replace(rel.split('/')[-1], _disk_name(ed, rel)), bytes(loc.db.d))
    ed.log(f'тексты {rel}: {done} строк')
    return dict(written=[rel], notes=notes, count=done)


def _disk_name(ed, rel):
    """Имя файла как у нашего контента (content\\menus\\fe\\loc\\NHL_ENG_US.db), чтобы в my не было второго регистра."""
    hit = ed.fs.find(rel)
    if hit and hit[2]:
        return os.path.basename(hit[2])
    return rel.split('/')[-1]


# ---------------------------------------------------------------- шрифты
def fonts(ed):
    out = []
    for rel in ed.fs.list_dir('fe/ion/fonts', r'\.(ttf|otf)$') + ed.fs.list_dir('rendering/indicator', r'\.ttf$'):
        base = rel.split('/')[-1].lower()
        hit = ed.fs.find(rel)
        out.append(dict(rel=rel, key=FONT_KEYS.get(base), source=hit[1] if hit else None, in_my=ed.fs.in_my(rel)))
    return out


def sample(ed, rel, size=40):
    from PIL import Image, ImageDraw, ImageFont
    data = ed.fs.read(rel)
    if data is None:
        raise EditorError('no_file', f'Нет файла {rel}', f'No file {rel}')
    f = ImageFont.truetype(io.BytesIO(data), size)
    lines = ['NHL LEGACY REMASTER 2026/27', 'Play Now  Be a GM  0123456789', 'Ovechkin · Dahlin · Kaprizov']
    im = Image.new('RGBA', (1100, int(size * 1.35) * len(lines) + 20), (20, 23, 28, 255))
    d = ImageDraw.Draw(im)
    for k, line in enumerate(lines):
        d.text((14, 10 + k * int(size * 1.35)), line, font=f, fill=(235, 238, 242, 255))
    b = io.BytesIO()
    im.save(b, 'PNG')
    return b.getvalue()


def replace_font(ed, rel, keep=False):
    """Свой TTF/OTF вместо шрифта игры через tools/fefont.py build (оригинал для метрик — из архива EA)."""
    key = FONT_KEYS.get(rel.split('/')[-1].lower())
    if not key:
        raise EditorError('font_key', 'Этот шрифт сборкой не заменяется (игра его не открывает) — только файлом',
                          'This font is not rebuilt (the game does not open it) — replace the file instead')
    start = ed.settings.get('import_dir')
    src = winui.pick_file(ed.t('Свой шрифт', 'Your font'), start, [(ed.t('Шрифты', 'Fonts'), '*.ttf;*.otf;*.ttc')])
    if not src:
        return None
    gamefs.check_game_closed()
    import gameprofile
    import fefont
    fefont.GAME = gameprofile.get('legacy')
    orig_game_file = fefont.game_file

    def from_archive(archive, member, game=None):        # метрики — по оригиналу EA с диска игры
        data = ed.fs.ea.read(member)
        if data is None:
            raise EditorError('no_font', f'Нет оригинала {member} в архивах игры', f'No original {member}')
        return fefont.unwrap(data)
    out = os.path.join(ed.fs.work, 'fonts-out')
    if os.path.isdir(out):
        shutil.rmtree(out)                                 # своя временная папка, ссылок в ней нет
    fefont.game_file = from_archive
    try:
        args = [out] + (['--keep'] if keep else []) + ['--face', f'{key}={src}']
        fefont.cmd_build(args)
    except SystemExit as e:
        raise EditorError('fefont', f'Шрифт не подошёл: {e}', f'The font did not fit: {e}')
    finally:
        fefont.game_file = orig_game_file
    built = fefont.built_face(out, key)
    if not built:
        raise EditorError('fefont', 'Сборка шрифта ничего не дала', 'The font build produced nothing')
    with ed.lock:
        ed.fs.write_my(rel, open(built, 'rb').read())
    ed.log(f'шрифт {rel} ← {src} ({"как есть" if keep else "подгонка"})')
    return dict(written=[rel], notes=[ed.t('шрифт собран tools/fefont.py под метрики игры' if not keep else
                                           'шрифт как есть (--keep)', 'built by tools/fefont.py')])


def handle(ed, method, fn, q, a):
    if fn == 'langs':
        return dict(langs=languages(ed))
    if fn == 'search':
        return search(ed, q.get('lang', 'nhl_eng_us'), q.get('q', ''), int(q.get('offset', 0)))
    if fn == 'save':
        return save(ed, a.get('lang', 'nhl_eng_us'), a.get('edits') or {})
    if fn == 'revert':
        rel = f'{LOC_DIR}/{a.get("lang", "nhl_eng_us")}.db'
        hit = ed.fs.find(rel)
        return ed.revert([rel] + ([rel.replace(rel.split('/')[-1], os.path.basename(hit[2]))] if hit and hit[2] else []))
    if fn == 'fonts':
        return dict(fonts=fonts(ed))
    if fn == 'sample':
        return sample(ed, q['rel']), 'image/png'
    if fn == 'font_replace':
        return replace_font(ed, a['rel'], bool(a.get('keep')))
    raise EditorError('bad', f'texts/{fn}?')
