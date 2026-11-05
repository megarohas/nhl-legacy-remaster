"""Превью формы в меню (fe/ion/artassets/jerseys/jersey_S_A_F.big) после правки свитера — без своей отрисовки.

Модель позы EA (tools/fepose.py: у всех превью один манекен, пиксель превью p показывает точку развёртки uv(p) с тем
же светом: P(p) ≈ gain(p)·T(uv(p)) + bias(p)) — та же, что у fb.pilot.fe_preview_ea. Редактор не рисует превью
заново, а переносит в него разницу свитеров: P'(p) = P(p) + gain(p)·(T'(uv) − T(uv)). Что в свитере не менялось —
в превью остаётся как было у EA или у нашей сборки (воротник, щит, нашивки); перекрашенное — перекрашивается с
тем же светом. Текстуры — уровень 512² (на нём модель подогнана).

Модель выводится из арта EA, в git её нет: tools/fepose.py fit кладёт её в game/work/legacy-data/fepose/pose.bin.
В папке игры редактор ищет её как content\\uniforms\\editor\\fepose.bin (её туда кладёт установка редактора) — нет
модели, превью не пересобирается, только вручную.
"""
import os
import struct

MAGIC = b'FEPOSE1\0'
REL = 'editor/fepose.bin'           # путь cache: (игра его не читает), часть uniforms
DEV = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'game', 'work',
                   'legacy-data', 'fepose', 'pose.bin')
_MODEL = {}


def model_path(fs):
    hit = fs.find(REL)
    if hit and hit[2]:
        return hit[2]
    return DEV if os.path.isfile(DEV) else None


def load(path):
    if path in _MODEL:
        return _MODEL[path]
    data = open(path, 'rb').read()
    if data[:8] != MAGIC:
        raise ValueError(f'{path}: не модель позы')
    w, h = struct.unpack_from('<II', data, 8)
    px = []
    rec = struct.Struct('<ff3f3f4BB')
    off = 16
    for i in range(w * h):
        u, v, g0, g1, g2, b0, b1, b2, *_ = rec.unpack_from(data, off)
        off += rec.size
        if u >= 0:
            px.append((i % w, i // w, u, v, g0, g1, g2))
    m = dict(w=w, h=h, px=px)
    _MODEL[path] = m
    return m


def _sampler(im):
    w, h = im.size
    data = im.load()

    def at(u, v):
        x, y = u * w - 0.5, v * h - 0.5
        x0, y0 = int(x // 1), int(y // 1)
        fx, fy = x - x0, y - y0
        acc = [0.0, 0.0, 0.0]
        for dy, wy in ((0, 1 - fy), (1, fy)):
            for dx, wx in ((0, 1 - fx), (1, fx)):
                c = data[min(w - 1, max(0, x0 + dx)), min(h - 1, max(0, y0 + dy))]
                k = wy * wx
                acc[0] += c[0] * k
                acc[1] += c[1] * k
                acc[2] += c[2] * k
        return acc
    return at


def transfer(preview, old_tex, new_tex, model):
    """preview (RGBA 256²), свитер до и после (RGBA любого размера) → новое превью."""
    from PIL import Image
    if preview.size != (model['w'], model['h']):
        raise ValueError(f'превью {preview.size}, модель {model["w"]}×{model["h"]}')
    a = old_tex.convert('RGB').resize((512, 512), Image.BOX)
    b = new_tex.convert('RGB').resize((512, 512), Image.BOX)
    sa, sb = _sampler(a), _sampler(b)
    out = preview.convert('RGBA').copy()
    pix = out.load()
    changed = 0
    for x, y, u, v, g0, g1, g2 in model['px']:
        ca, cb = sa(u, v), sb(u, v)
        d = (cb[0] - ca[0], cb[1] - ca[1], cb[2] - ca[2])
        if abs(d[0]) + abs(d[1]) + abs(d[2]) < 1.5:
            continue
        r, g, bl, al = pix[x, y]
        pix[x, y] = (max(0, min(255, round(r + g0 * d[0]))), max(0, min(255, round(g + g1 * d[1]))),
                     max(0, min(255, round(bl + g2 * d[2]))), al)
        changed += 1
    return out, changed
