"""Музыка в редакторе: песни EA Trax и все звуки банка audio/music — прослушать, выгрузить MP3, заменить своим файлом.

Банк и кодек — tools/music.py (docs/music.md): поток EALayer3 переупаковывается в MP3 без потерь (выгрузка без
ffmpeg), MP3 44,1 кГц стерео от LAME — обратно тоже без перекодирования. Другой файл (WAV, FLAC, MP3 другой частоты)
перекодируется через ffmpeg: ffmpeg.exe рядом с редактором или в PATH; без него — понятный отказ. Новый банк (три
файла: .sbr, .sbs, .bin) пишется в content\\my\\audio\\music; «Вернуть как было» — убрать их оттуда.
"""
import hashlib
import os
import shutil
import sys

import gamefs
import winui
from gamefs import EditorError

FILES = ('music_samples.sbr', 'music_samples.sbs', 'music_musicboxdata.bin', 'music_graffitidata.bin')
REL = 'audio/music/'


def _music():
    import gameprofile
    import music
    music.P = gameprofile.get('legacy')
    return music


def _ffmpeg_path(ed):
    for d in (ed.fs.install, os.path.dirname(os.path.abspath(sys.executable))):
        p = os.path.join(d, 'ffmpeg.exe')
        if os.path.isfile(p):
            os.environ['PATH'] = d + os.pathsep + os.environ.get('PATH', '')
            return p
    return shutil.which('ffmpeg')


def bank(ed):
    """Банк, который возьмёт игра (my → части → архив), — копией в cache\\editor\\music\\src (sbs — 290 МБ, копия
    только если поменялся источник)."""
    m = _music()
    hits = {f: ed.fs.find(REL + f) for f in FILES}
    layers = {h[1] for f, h in hits.items() if h and h[2]}
    if len(layers) == 1 and all(h is None or h[2] for h in hits.values()) and all(hits[f] for f in FILES[:3]):
        root = os.path.dirname(os.path.dirname(os.path.dirname(hits[FILES[0]][2])))   # <слой>udio\music\…
        key = 'disk:' + root + ':' + ':'.join(str(os.path.getmtime(h[2])) for h in hits.values() if h)
        cache = getattr(ed, '_bank', None)
        if cache and cache[0] == key:
            return cache[1]
        b = m.Bank(root)
        ed._bank = (key, b)
        return b
    src = os.path.join(ed.fs.work, 'music', 'src')
    d = os.path.join(src, 'audio', 'music')
    os.makedirs(d, exist_ok=True)
    sig = []
    for f in FILES:
        hit = ed.fs.find(REL + f)
        if hit is None:
            if f == FILES[3]:
                continue
            raise EditorError('no_bank', f'Нет файла банка {REL + f}', f'No bank file {REL + f}')
        stamp = f'{hit[0]}:{hit[1]}:{os.path.getmtime(hit[2]) if hit[2] else 0}'
        sig.append(stamp)
        mark = os.path.join(d, f + '.source')
        if os.path.isfile(os.path.join(d, f)) and os.path.isfile(mark) and open(mark).read() == stamp:
            continue
        if hit[2]:
            shutil.copyfile(hit[2], os.path.join(d, f))
        else:
            open(os.path.join(d, f), 'wb').write(ed.fs.read(REL + f))
        open(mark, 'w').write(stamp)
    key = hashlib.sha1('|'.join(sig).encode()).hexdigest()
    cache = getattr(ed, '_bank', None)
    if cache and cache[0] == key:
        return cache[1]
    b = m.Bank(src)
    ed._bank = (key, b)
    return b


def tracks(ed):
    b = bank(ed)
    out = []
    trax = b.mbx.trax()
    sid_slot = {v: k for k, v in trax.items()}
    for sid in b.ids():
        t = b.mbx.tags(sid)
        out.append(dict(sid=sid, slot=sid_slot.get(sid), cat=t.get('VolumeType', ''), artist=t.get('Artist', ''),
                        title=t.get('Title', ''), sec=round(b.info(sid)['sec'], 1)))
    return out


def mp3(ed, sid):
    m = _music()
    b = bank(ed)
    raw = b.read(int(sid))
    return m.granules_to_mp3(m.stream_decode_parts(raw)[0])


def export(ed, sid):
    b = bank(ed)
    t = b.mbx.tags(int(sid))
    name = f'{t.get("Artist", "")} - {t.get("Title", "")}'.strip(' -') or f'id{sid}'
    name = ''.join(c if c not in '<>:"/\\|?*' else '_' for c in name)
    start = ed.settings.get('export_dir') or os.path.join(os.path.expanduser('~'), 'Desktop')
    p = winui.save_file(ed.t('Выгрузить MP3', 'Export MP3'), start, name + '.mp3', [('MP3', '*.mp3')], 'mp3')
    if not p:
        return None
    ed.settings['export_dir'] = os.path.dirname(p)
    ed.save_settings()
    open(p, 'wb').write(mp3(ed, sid))
    return dict(written=[p], folder=os.path.dirname(p))


def replace(ed, sid, artist=None, title=None, path=None):
    """Звук sid ← файл пользователя (диалог), теги Artist/Title — если даны. → отчёт."""
    m = _music()
    sid = int(sid)
    if path is None:
        start = ed.settings.get('import_dir')
        path = winui.pick_file(ed.t('Песня для замены', 'Song to replace with'), start,
                               [(ed.t('Звук', 'Audio'), '*.mp3;*.wav;*.flac;*.ogg;*.m4a'), ('*', '*.*')])
        if not path:
            return None
        ed.settings['import_dir'] = os.path.dirname(path)
        ed.save_settings()
    ff = _ffmpeg_path(ed)
    try:
        stream, how = m.encode_track(path, copy=True, max_block=m.MUSIC['legacy']['max_block'])
    except FileNotFoundError:
        raise EditorError('ffmpeg', 'Этот файл нужно перекодировать, а ffmpeg не найден. Возьмите MP3 44,1 кГц стерео '
                          '(его редактор кладёт без перекодирования) или положите ffmpeg.exe рядом с редактором',
                          'This file needs re-encoding and ffmpeg was not found. Use an MP3 44.1 kHz stereo '
                          '(stored as is) or put ffmpeg.exe next to the editor')
    except (ValueError, SystemExit, OSError) as e:
        hint = '' if ff else ed.t(' (ffmpeg не найден)', ' (ffmpeg not found)')
        raise EditorError('audio', f'Файл не подошёл: {e}{hint}', f'The file did not fit: {e}{hint}')
    gamefs.check_game_closed()
    b = bank(ed)
    if sid < 0:                                          # новый слот EA Trax (music.py Bank.add_trax): trax10…trax21
        trax = b.mbx.trax()
        k = max(trax) + 1 if trax else 0
        top = m.MUSIC['legacy']['max_trax']
        if k >= top:
            raise EditorError('trax_full', f'Слоты EA Trax заняты: trax0…trax{top - 1} (больше игра не знает)',
                              f'EA Trax slots are full: trax0…trax{top - 1}')
        try:
            sid = b.add_trax(k)
        except SystemExit as e:
            raise EditorError('trax', f'Новый слот не добавить: {e}', f'Cannot add a slot: {e}')
        how = f'{how}; ' + ed.t(f'новый слот trax{k} (id {sid})', f'new slot trax{k} (id {sid})')
    if artist is not None and artist != '':
        b.mbx.set_tag(sid, 'Artist', artist)
    if title is not None and title != '':
        b.mbx.set_tag(sid, 'Title', title)
    out_root = os.path.join(ed.fs.work, 'music', 'out')
    if os.path.isdir(os.path.join(out_root, 'audio')):
        shutil.rmtree(os.path.join(out_root, 'audio'))           # своя временная папка, ссылок в ней нет
    d = b.save(out_root, {sid: stream})
    backup = ed.fs.backup_dir() if any(ed.fs.in_my(REL + f) for f in FILES) else None
    written = []
    with ed.lock:
        for f in FILES:
            p = os.path.join(d, f)
            if os.path.isfile(p):
                # .sbs — сотни МБ: write_my читает в память; копия файла — через os.replace во временный
                if f.endswith('.sbs'):
                    gamefs.check_game_closed()
                    dst = ed.fs.my_path(REL + f)
                    if os.path.isfile(dst):
                        q = os.path.join(backup or ed.fs.backup_dir(), 'content', 'my', *(REL + f).split('/'))
                        os.makedirs(os.path.dirname(q), exist_ok=True)
                        shutil.copy2(dst, q)
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    shutil.copyfile(p, dst + '.editor-tmp')
                    os.replace(dst + '.editor-tmp', dst)
                else:
                    ed.fs.write_my(REL + f, open(p, 'rb').read(), backup)
                written.append(REL + f)
    ed._bank = None
    ed.log(f'музыка: id {sid} ← {path} ({how})')
    return dict(written=written, notes=[how])


def handle(ed, method, fn, q, a):
    if fn == 'tracks':
        return dict(tracks=tracks(ed), ffmpeg=bool(_ffmpeg_path(ed)), in_my=any(ed.fs.in_my(REL + f) for f in FILES))
    if fn == 'mp3':
        return mp3(ed, q['sid']), 'audio/mpeg'
    if fn == 'export':
        return export(ed, a['sid'])
    if fn == 'replace':
        return replace(ed, a['sid'], a.get('artist'), a.get('title'))
    if fn == 'revert':
        return ed.revert([REL + f for f in FILES])
    raise EditorError('bad', f'audio/{fn}?')
