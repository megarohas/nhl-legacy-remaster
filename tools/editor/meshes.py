"""Сетки .rx2 в редакторе: сводка, геометрия для 3D-просмотра, выгрузка OBJ и импорт поправленного OBJ.

Разбор и запись — tools/rw4mesh.py (Mesh, export_obj, apply_obj): импорт меняет только позиции точек (нормали и
касательные поворачиваются следом), индексы, UV, кости и веса — байт в байт как были. Точек и граней в OBJ должно
быть столько же и в том же порядке, что при выгрузке (docs/player-models.md, docs/editor.md «Модели»). Файл из
нескольких подсеток (реквизит, некоторые клюшки) — по OBJ на подсетку: <имя>_sub<N>.obj.
"""
import os
import struct

import gamefs
import winui
from gamefs import EditorError

T_VDECL = 0x00020004
MAX_VERTS = 200_000


def _count_subs(data):
    import rw4mesh as rm
    f = rm.Rw4File(data)
    return len(f.find(rm.TYPE_VB)), f


def load_meshes(data, rel=''):
    """[Mesh] всех подсеток файла (пусто — сеток нет или устройство не как у сеток экипировки)."""
    import rw4mesh as rm
    n, _ = _count_subs(data)
    if n == 0:
        return []
    out = []
    if n == 1:
        out.append(rm.Mesh(data, rel))
    else:
        for k in range(n):
            out.append(rm.Mesh(data, rel, sub=k))
    return out


def summary(data, rel):
    try:
        ms = load_meshes(data, rel)
    except Exception as e:                       # noqa: BLE001
        n = 0
        try:
            n, _ = _count_subs(data)
        except Exception:                        # noqa: BLE001
            pass
        return {'subs': n, 'error': str(e)} if n else None
    if not ms:
        return None
    return {'subs': len(ms), 'vertices': sum(m.nv for m in ms), 'triangles': sum(len(m.tris) for m in ms),
            'uv': all(bool(m.uv) for m in ms)}


def geometry(ed, rel):
    data = ed.fs.read(rel)
    if data is None:
        raise EditorError('no_file', f'Нет файла {rel}', f'No file {rel}')
    ms = load_meshes(data, rel)
    out = []
    for m in ms:
        if m.nv > MAX_VERTS:
            continue
        pos = [round(c, 5) for p in m.pos for c in p]
        uv = [round(c, 5) for t in m.uv for c in t] if m.uv else []
        idx = [i for t in m.tris for i in t]
        out.append({'pos': pos, 'uv': uv, 'idx': idx, 'nv': m.nv})
    return {'subs': out}


def export_obj(ed, rel):
    data = ed.fs.read(rel)
    ms = load_meshes(data, rel) if data else []
    if not ms:
        raise EditorError('no_mesh', 'В файле нет сетки', 'The file has no mesh')
    import rw4mesh as rm
    base = rel.split('/')[-1].rsplit('.', 1)[0]
    start = ed.settings.get('export_dir') or os.path.join(os.path.expanduser('~'), 'Desktop')
    p = winui.save_file(ed.t('Выгрузить OBJ', 'Export OBJ'), start, base + '.obj', [('OBJ', '*.obj')], 'obj')
    if not p:
        return None
    ed.settings['export_dir'] = os.path.dirname(p)
    ed.save_settings()
    written = []
    note = (f'NHL Legacy Remaster editor: {rel}. Import back: the same points and faces in the same order '
            '(no new or merged vertices, triangles only).')
    for k, m in enumerate(ms):
        q = p if len(ms) == 1 else p[:-4] + f'_sub{k}.obj'
        rm.export_obj(m, q, name=base if len(ms) == 1 else f'{base}_sub{k}', note=note)
        written.append(q)
    return {'written': written, 'folder': os.path.dirname(p)}


def import_obj(ed, rel):
    data = ed.fs.read(rel)
    ms = load_meshes(data, rel) if data else []
    if not ms:
        raise EditorError('no_mesh', 'В файле нет сетки', 'The file has no mesh')
    start = ed.settings.get('import_dir') or ed.settings.get('export_dir')
    p = winui.pick_file(ed.t('OBJ для импорта', 'OBJ to import'), start, [('OBJ', '*.obj')])
    if not p:
        return None
    ed.settings['import_dir'] = os.path.dirname(p)
    ed.save_settings()
    import rw4mesh as rm
    files = [p]
    if len(ms) > 1:
        stem = p[:-4]
        if stem.rsplit('_sub', 1)[-1].isdigit():
            stem = stem.rsplit('_sub', 1)[0]
        files = [f'{stem}_sub{k}.obj' for k in range(len(ms))]
        missing = [f for f in files if not os.path.isfile(f)]
        if missing:
            raise EditorError('obj_parts', f'Нужны все части: нет {", ".join(os.path.basename(x) for x in missing)}',
                              f'All parts are needed: missing {", ".join(os.path.basename(x) for x in missing)}')
    reports = []
    cur = data
    try:
        for k, f in enumerate(files):
            m = rm.Mesh(cur, rel, sub=None if len(ms) == 1 else k)
            reports.append(rm.apply_obj(m, f))
            cur = m.bytes()
    except SystemExit as e:
        raise EditorError('obj', f'OBJ не подходит: {e}', f'OBJ does not fit: {e}')
    gamefs.check_game_closed()
    with ed.lock:
        ed.fs.write_my(rel, cur)
    ed._conts.clear()
    moved = sum(r['moved_vertices'] for r in reports)
    ed.log(f'импорт OBJ {p} → {rel}: сдвинуто вершин {moved}')
    return {'written': [rel], 'notes': [ed.t(f'сдвинуто вершин: {moved}, наибольший сдвиг '
                                             f'{max(r["max_shift_mm"] for r in reports)} мм',
                                             f'moved vertices: {moved}, max shift '
                                             f'{max(r["max_shift_mm"] for r in reports)} mm')]}


def handle(ed, method, fn, q, a):
    if fn == 'geom':
        import json
        return json.dumps(geometry(ed, q['rel'])).encode(), 'application/json'
    if fn == 'export':
        return export_obj(ed, a['rel'])
    if fn == 'import':
        return import_obj(ed, a['rel'])
    raise EditorError('bad', f'meshes/{fn}?')


_ = struct
