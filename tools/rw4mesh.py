"""3D-модели игроков NHL 13 (Xbox 360): сетки RenderWare 4 (.rx2) ⇄ OBJ и правка толщины голени (гетры).

    python rw4mesh.py info FILE…                       # сетка: вершины, треугольники, формат вершины, кости, рамка
    python rw4mesh.py roundtrip FILE_OR_DIR…           # разбор → сборка байт-в-байт (контейнер, вершины, индексы)
    python rw4mesh.py export FILE.rx2 OUT.obj          # сетка → OBJ для Blender (точки в стабильном порядке)
    python rw4mesh.py import EDITED.obj [--src rendering/sock/playersock_0_2.rx2] [--out DIR] [--no-lods]
                                                       # новые позиции из OBJ → .rx2 в DIR (раскладка cache:, по
                                                       # умолчанию game/work/models/out); нормали и касательные
                                                       # поворачиваются вслед за поверхностью; индексы, UV, кости и
                                                       # веса — байт в байт как были; правка сама переносится на
                                                       # детализации _0 и _3; --src по умолчанию — по имени объекта
    python rw4mesh.py transfer SRC.rx2 SRC_NEW.rx2 DST.rx2 OUT.rx2
                                                       # перенести правку одной детализации (LOD) на другую
    python rw4mesh.py shin [--strength 1] [--taper 0.15] [--variants 0,1,2,3] [--out DIR] [--obj DIR]
                           [--preview DIR] [--no-preview] [--compare 0.5]
                                                       # правка голени гетр: икра у всех вариантов одной формы
                                                       # (среднее четырёх), низ у 1 и 2 поверх ботинка уже
                                                       # (подробно — docs/player-models.md)
    python rw4mesh.py preview [--out DIR] [--preview DIR]
                                                       # картинки до/после (спереди и сбоку) по готовым файлам
    python rw4mesh.py check [--out DIR]                # гетры из DIR против ботинка и языка/задника конька: в позе
                                                       # привязки и при сгибе стопы (не проткнула ли деталь гетру)
    python rw4mesh.py objs [--obj DIR]                 # OBJ исходных гетр и деталей рядом (для Blender)

У всех команд — опция --game {nhl13,legacy} (или NHL_GAME, tools/gameprofile.py): из архивов какой игры брать сетки
(NHL Legacy — распакованные game/other/legacy/big/<архив>/, имена строчные) и куда писать по умолчанию (NHL 13 —
game/work/models/…, Legacy — game/work/legacy-data/models/…). По умолчанию — NHL 13, всё как до профиля. У Legacy
preview рисует ещё колонку «NHL 13 с модом» (готовые гетры NHL 13 из --nhl13-out DIR, по умолчанию
game/work/models/out, — с коньками, шортами и текстурами NHL 13; --no-nhl13 — без неё).

Где что лежит (разбор 08.10.2026, подробно — docs/player-models.md). Тело игрока в матче — набор отдельных сеток
на общем скелете (122 кости, rendering/skeleton_bindpose/skeleton_bindpose_player.rx2 в boot.big): голова
(rendering/player/player_<headid>), шлем, свитер (rendering/jersey/jersey_…), шорты (rendering/pant/pant_…), гетры
(rendering/sock/playersock_T_L), коньки (rendering/skate/playerskate_L, skatelace_L, skatetongue_T_L), перчатки,
кисти, клюшка. Голого тела под формой нет: видимая голень — сетка гетры. T — значение
exhibitionskaterequipment.skatesocktuck (0…3, у игры — байт +690 записи внешности игрока, sub_8328A438); L —
детализация: файл _2 — ближняя (1320 вершин), _0 — средняя (280), _3 — дальняя (40), _4 игра не грузит
(таблица sub_83288A28: LOD 0/1/2 → _3/_0/_2).

Контейнер (.rx2, "\\x89RW4xb2"): заголовок 0x800, таблица секций по 24 байта (смещение, 0, размер, выравнивание,
номер типа, тип). Секции сетки: 0x00020004 — объявление вершин, 0x00010031 — буфер вершин и буфер индексов
(смещения — от начала данных), 0x00020005 — D3DVertexBuffer (+0x18 — номер секции данных << 2 | 3,
+0x20 — шаг << 16, +0x24 — число вершин), 0x00020007 — D3DIndexBuffer (+0x18 — номер секции данных, +0x1C —
размер, +0x20 — число индексов), 0x00020009 — вызов отрисовки (число вершин, первый индекс, число индексов),
0x00EF0004 — имя шейдера экспорта (nhl_export_shader). Рамок/сфер в файле нет — позиции можно менять, ничего
больше не пересчитывая.

Вершина (32 байта, одинакова у всех сеток экипировки): позиция FLOAT16_4 (x, y, z, 1; метры, поза привязки, Y вверх,
+Z — вперёд, к носку конька), нормаль и касательная DEC3N (10 бит на X, Y, Z от младших битов слова, /511; старшие
2 бита — 0), UV USHORT2N, индексы костей USHORT4 (номер кости × 3 — номер регистра матрицы 3×4), веса UBYTE4N
(в файле байты в обратном порядке: вес X — последний байт слова). Индексы — 16 бит, полосы треугольников, 0xFFFF —
разрыв полосы; у нечётных треугольников полосы порядок обхода обратный. Сетки NHL 10 (шаг 40: позиция FLOAT3 —
float32, веса USHORT4N — 4 × u16 в порядке файла) тоже разбираются и кодируются обратно байт в байт (pos_f32,
w_u16); set_skin — кости и веса вершины (сумма весов ровно 255 / 65535).

Только стандартная библиотека (+ Chrome/Edge без окна — подписи листа превью, как в teamart). teamart, kitpaint,
czkit, playerhead — как библиотеки, не меняются.
"""
import json, math, os, struct, sys
from contextlib import contextmanager

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gameprofile  # noqa: E402

RW4_MAGIC = b'\x89RW4xb2\x00'
TYPE_DATA = 0x00010031       # буфер (вершины, индексы, пиксели); смещение — от начала данных
TYPE_RASTER = 0x00020003     # текстура (D3DTexture)
TYPE_VDECL = 0x00020004      # объявление вершин
TYPE_VB = 0x00020005         # D3DVertexBuffer + шаг и число вершин
TYPE_IB = 0x00020007         # D3DIndexBuffer + число индексов
TYPE_DRAW = 0x00020009       # вызов отрисовки
TYPE_BINDPOSE = 0x00070003   # матрицы скелета (skeleton_bindpose_*)
TYPE_SHADER = 0x00EF0004     # имя шейдера экспорта
TYPE_NAMES = 0x00EC0010      # имена растров

# D3DDECLTYPE Xbox 360: биты 0–5 — формат выборки Xenos, 6–9 — знак/целое, 10–21 — перестановка компонент
DECL_FLOAT16_4 = 0x1A2360
DECL_FLOAT3 = 0x2A23B9           # позиция у NHL 10 (шаг вершины 40)
DECL_DEC3N = 0x2A2187
DECL_USHORT2N = 0x2C2059
DECL_USHORT4 = 0x1A225A
DECL_UBYTE4N = 0x1A2086
DECL_USHORT4N = 0x1A205A         # веса у NHL 10: 4 × u16 / 65535, в порядке файла
DECL_INFO = {DECL_FLOAT16_4: ('FLOAT16_4', 8), DECL_DEC3N: ('DEC3N', 4), DECL_USHORT2N: ('USHORT2N', 4),
             DECL_USHORT4: ('USHORT4', 8), DECL_UBYTE4N: ('UBYTE4N', 4), DECL_USHORT4N: ('USHORT4N', 8),
             DECL_FLOAT3: ('FLOAT3', 12), 0x2C23A5: ('FLOAT2', 8), 0x1A23A6: ('FLOAT4', 16), 0x2C83A4: ('FLOAT1', 4),
             0x182886: ('D3DCOLOR', 4), 0x2C2159: ('SHORT2N', 4), 0x1A215A: ('SHORT4N', 8),
             0x2C235F: ('FLOAT16_2', 4), 0x1A2286: ('UBYTE4', 4), 0x2C2359: ('SHORT2', 4)}
USAGE = {0: 'position', 1: 'blendweight', 2: 'blendindices', 3: 'normal', 4: 'psize', 5: 'texcoord', 6: 'tangent',
         7: 'binormal', 10: 'color'}

STRIP_RESTART = 0xFFFF


def u32(b, o):
    return struct.unpack_from('>I', b, o)[0]


def game_dir():
    import playerhead as ph
    return ph.game_dir()


# ---------------------------------------------------------------- игра (профиль)

PROFILE = gameprofile.get()      # из архивов какой игры брать сетки; по умолчанию — NHL_GAME или nhl13


def use_game(name):
    """Игра для всех функций модуля (и для sticktape, jersey10): 'nhl13' или 'legacy'."""
    global PROFILE
    PROFILE = gameprofile.get(name)
    return PROFILE


@contextmanager
def game_profile(name):
    """На время блока — другая игра (картинки «NHL 13 с модом» рядом с Legacy)."""
    old = PROFILE
    use_game(name)
    try:
        yield PROFILE
    finally:
        use_game(old.name)


def is_nhl13():
    return PROFILE.name == 'nhl13'


def take_game(args):
    """Опция --game (gameprofile.add_argument) из списка аргументов команды: включает игру, → остальные аргументы."""
    import argparse
    ap = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    gameprofile.add_argument(ap)
    ns, rest = ap.parse_known_args(args)
    use_game(ns.game)
    return rest


# ---------------------------------------------------------------- файлы игры

def archive_of(rel):
    if rel.startswith(('rendering/jersey/', 'rendering/cz')):
        return 'nocacherender'
    if rel.startswith(('rendering/skeleton_bindpose/', 'rendering/boot/', 'shaders/')):
        return 'boot'
    if rel.startswith('rendering/'):
        return 'cacherender'
    return 'cache'


def src_dir():
    if not is_nhl13():
        return PROFILE.work_dir('models', 'src')
    return os.path.join(game_dir(), 'work', 'models', 'src')


def game_has(rel):
    """Есть ли файл rel в архивах игры (NHL 13 — в оглавлении архива диска, Legacy — среди распакованных)."""
    if not is_nhl13():
        return PROFILE.extracted(rel) is not None
    import kitpaint as kp
    _, entries, _ = kp._disc_entries(archive_of(rel))
    return rel in entries


def source(rel):
    """Разжатый файл игры по пути архива: game/extracted/big/<архив>/…, кеш game/work/models/src/…, иначе — образ
    диска game/extracted/disc/<архив>.big (с записью в кеш). NHL Legacy — распакованные архивы
    game/other/legacy/big/<архив>/… (первый по порядку профиля, где файл есть: renderboot раньше cacherender)."""
    if not is_nhl13():
        p = PROFILE.extracted(rel)
        if p is None:
            raise SystemExit(f'{rel}: нет в распакованных архивах {PROFILE.title} ({PROFILE.big})')
        return unchunk_any(open(p, 'rb').read())
    g = game_dir()
    arc = archive_of(rel)
    for p in (os.path.join(g, 'extracted', 'big', arc, *rel.split('/')), os.path.join(src_dir(), *rel.split('/'))):
        if os.path.exists(p):
            return unchunk_any(open(p, 'rb').read())
    import kitpaint as kp
    path, entries, unpack_big = kp._disc_entries(arc)
    e = entries.get(rel)
    if e is None:
        raise SystemExit(f'{rel}: нет в {arc}.big')
    with open(path, 'rb') as f:
        f.seek(e.offset)
        blob = f.read(e.stored_size)
    if e.is_packed:
        blob = unpack_big.decompress_packed_member(blob, e.unpacked_size)
    blob = unchunk_any(blob)
    dst = os.path.join(src_dir(), *rel.split('/'))
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    open(dst, 'wb').write(blob)
    return blob


def unchunk_any(blob):
    if blob[:8] in (b'chunklzx', b'chunkzip'):
        import unchunk
        return unchunk.unchunk(blob)
    return blob


# ---------------------------------------------------------------- контейнер RW4

class Section:
    __slots__ = ('index', 'off', 'x', 'size', 'align', 'tidx', 'type')

    def __init__(self, index, words):
        self.index = index
        self.off, self.x, self.size, self.align, self.tidx, self.type = words


class Rw4File:
    """Контейнер RenderWare 4 (Xbox 360): заголовок, таблица секций; тело секции — срез raw (правка на месте)."""

    def __init__(self, data, path=''):
        data = unchunk_any(data)
        if data[:8] != RW4_MAGIC:
            raise ValueError(f'{path}: не RW4xb2')
        self.raw = bytearray(data)
        self.path = path
        n, table = u32(data, 0x20), u32(data, 0x30)
        self.data_start, self.data_size = u32(data, 0x44), u32(data, 0x54)
        self.sections = [Section(i, struct.unpack_from('>6I', data, table + 24 * i)) for i in range(n)]
        if self.data_start + self.data_size != len(data):
            raise ValueError(f'{path}: размер {len(data)} ≠ 0x{self.data_start:X} + 0x{self.data_size:X}')

    def abs_off(self, s):
        return s.off + (self.data_start if s.type == TYPE_DATA else 0)

    def body(self, s):
        o = self.abs_off(s)
        return bytes(self.raw[o:o + s.size])

    def find(self, typ):
        return [s for s in self.sections if s.type == typ]

    def one(self, typ):
        ss = self.find(typ)
        if len(ss) != 1:
            raise ValueError(f'{self.path}: секций 0x{typ:08X} — {len(ss)}, а не одна')
        return ss[0]

    def bytes(self):
        return bytes(self.raw)


# ---------------------------------------------------------------- кодирование компонент

def half_dec(raw16):
    return struct.unpack('>e', struct.pack('>H', raw16))[0]


def half_enc(v):
    return struct.unpack('>H', struct.pack('>e', v))[0]


def dec3n_dec(w):
    out = []
    for k in range(3):
        v = (w >> (10 * k)) & 1023
        if v & 512:
            v -= 1024
        out.append(max(-1.0, v / 511.0))
    return out


def dec3n_enc(v, top=0):
    w = 0
    for k in range(3):
        q = int(round(max(-1.0, min(1.0, v[k])) * 511.0))
        w |= (q & 0x3FF) << (10 * k)
    return w | ((top & 3) << 30)


# ---------------------------------------------------------------- сетка

class Element:
    __slots__ = ('off', 'stream', 'type', 'usage', 'rwid', 'word0', 'word2')

    def __init__(self, w0, w1, w2):
        self.word0, self.word2 = w0, w2
        self.off, self.stream = w0 & 0xFFFF, w0 >> 16
        self.type = w1
        self.usage, self.rwid = (w2 >> 16) & 0xFF, w2 & 0xFFFF

    @property
    def tname(self):
        return DECL_INFO.get(self.type, (f'0x{self.type:06X}', 0))[0]

    @property
    def uname(self):
        return USAGE.get(self.usage, str(self.usage))


def strip_triangles(idx):
    """Полосы с разрывом 0xFFFF → [(a, b, c)] без вырожденных; у нечётных — обратный обход (как в игре)."""
    tris, strip = [], []
    for i in idx:
        if i == STRIP_RESTART:
            strip = []
            continue
        strip.append(i)
        if len(strip) >= 3:
            a, b, c = strip[-3:]
            if (len(strip) - 3) % 2:
                a, b = b, a
            if a != b and b != c and a != c:
                tris.append((a, b, c))
    return tris


class Mesh:
    """Одна сетка .rx2 (один буфер вершин и один буфер индексов — так у всех сеток экипировки игроков). Атрибуты
    раскладываются в списки; правка — set_pos/set_nrm/set_tan пишет в raw только изменённые вершины, остальное в
    файле — байт в байт как было. sub=k — k-я подсетка файла из нескольких (буферы вершин и индексов, вызовы
    отрисовки и шейдеры — по порядку; объявление вершин — общее или своё у каждой; так устроен реквизит
    rendering/prop/droppedstick_0 у NHL Legacy); bytes() — весь файл."""

    def __init__(self, data, path='', sub=None):
        self.f = f = Rw4File(data, path)
        self.path = path
        self.sub = sub
        raw = f.raw
        # объявление вершин
        sd = f.one(TYPE_VDECL) if sub is None else f.find(TYPE_VDECL)[min(sub, len(f.find(TYPE_VDECL)) - 1)]
        db = f.body(sd)
        self.decl_head = struct.unpack_from('>4I', db, 0)
        ne, stride = db[8], db[9]
        self.elements = [Element(*struct.unpack_from('>3I', db, 16 + 12 * k)) for k in range(ne)]
        if 16 + 12 * ne != len(db):
            raise ValueError(f'{path}: объявление вершин {len(db)} байт на {ne} элементов')
        # буфер вершин
        sv = f.one(TYPE_VB) if sub is None else f.find(TYPE_VB)[sub]
        self.vbh = sv
        vb = f.body(sv)
        fetch0 = u32(vb, 0x18)
        if fetch0 & 3 != 3:
            raise ValueError(f'{path}: выборка вершин 0x{fetch0:08X}')
        self.vsec = f.sections[fetch0 >> 2]
        self.stride, self.nv = u32(vb, 0x20) >> 16, u32(vb, 0x24)
        if self.stride != stride or self.vsec.type != TYPE_DATA or self.stride * self.nv > self.vsec.size:
            raise ValueError(f'{path}: буфер вершин (шаг {self.stride}/{stride}, {self.nv} вершин, '
                             f'секция {self.vsec.index} 0x{self.vsec.size:X})')
        self.vo = f.abs_off(self.vsec)
        # буфер индексов
        si = f.one(TYPE_IB) if sub is None else f.find(TYPE_IB)[sub]
        self.ibh = si
        ib = f.body(si)
        self.ib_common = u32(ib, 0)
        if self.ib_common & 0x80000000:
            raise ValueError(f'{path}: 32-битные индексы не разбирались')
        self.isec = f.sections[u32(ib, 0x18)]
        self.ni = u32(ib, 0x20)
        if self.isec.type != TYPE_DATA or 2 * self.ni > self.isec.size or u32(ib, 0x1C) != self.isec.size:
            raise ValueError(f'{path}: буфер индексов ({self.ni} индексов, секция {self.isec.index})')
        self.io = f.abs_off(self.isec)
        self.indices = list(struct.unpack_from('>%dH' % self.ni, raw, self.io))
        if max(i for i in self.indices if i != STRIP_RESTART) >= self.nv:
            raise ValueError(f'{path}: индекс за пределами буфера вершин')
        draws = f.find(TYPE_DRAW)
        if sub is not None:                       # вызов этой подсетки: слова 5 и 6 — номера секций индексов и вершин
            draws = [d for d in draws if struct.unpack_from('>6I', f.body(d), 0)[5] == sv.index] or draws[sub:sub + 1]
        self.draw = struct.unpack_from('>6I', f.body(draws[0]), 0) if draws else None
        shaders = f.find(TYPE_SHADER)
        if sub is not None:
            shaders = shaders[sub:sub + 1]
        self.shader = ''
        if shaders:
            b = f.body(shaders[0])
            self.shader = b[12:b.index(b'\0', 12)].decode('latin1')
        self.tris = strip_triangles(self.indices)
        self._decode()

    @classmethod
    def load(cls, path, sub=None):
        return cls(open(path, 'rb').read(), path, sub)

    @classmethod
    def game(cls, rel, sub=None):
        return cls(source(rel), rel, sub)

    def elem(self, usage, typ=None):
        for e in self.elements:
            if e.usage == usage and (typ is None or e.type == typ):
                return e
        return None

    def _decode(self):
        raw, vo, st, nv = self.f.raw, self.vo, self.stride, self.nv
        ep = self.elem(0, DECL_FLOAT16_4) or self.elem(0, DECL_FLOAT3)
        en, et = self.elem(3, DECL_DEC3N), self.elem(6, DECL_DEC3N)
        eu, ei = self.elem(5, DECL_USHORT2N), self.elem(2, DECL_USHORT4)
        ew = self.elem(1, DECL_UBYTE4N) or self.elem(1, DECL_USHORT4N)
        if ep is None:
            raise ValueError(f'{self.path}: нет позиции FLOAT16_4 / FLOAT3')
        self.e_pos, self.e_nrm, self.e_tan, self.e_uv, self.e_bi, self.e_bw = ep, en, et, eu, ei, ew
        self.pos_f32 = ep.type == DECL_FLOAT3            # NHL 10: позиция float32, веса u16
        self.w_u16 = ew is not None and ew.type == DECL_USHORT4N
        self.pos, self.nrm, self.tan, self.uv, self.bones, self.weights = [], [], [], [], [], []
        for i in range(nv):
            b = vo + i * st
            if self.pos_f32:
                self.pos.append(list(struct.unpack_from('>3f', raw, b + ep.off)))
            else:
                self.pos.append([half_dec(h) for h in struct.unpack_from('>3H', raw, b + ep.off)])
            if en:
                self.nrm.append(dec3n_dec(u32(raw, b + en.off)))
            if et:
                self.tan.append(dec3n_dec(u32(raw, b + et.off)))
            if eu:
                self.uv.append([x / 65535.0 for x in struct.unpack_from('>2H', raw, b + eu.off)])
            if ei:
                self.bones.append(tuple(x // 3 for x in struct.unpack_from('>4H', raw, b + ei.off)))
            if ew and self.w_u16:
                self.weights.append(tuple(x / 65535.0 for x in struct.unpack_from('>4H', raw, b + ew.off)))
            elif ew:
                self.weights.append(tuple(x / 255.0 for x in raw[b + ew.off:b + ew.off + 4][::-1]))

    # --- запись (только изменённые вершины)
    def _vb(self, i, e):
        return self.vo + i * self.stride + e.off

    def _pos_bytes(self, p):
        if self.pos_f32:
            return struct.pack('>3f', *(float(c) for c in p))
        return struct.pack('>3H', *(half_enc(float(c)) for c in p))

    def _pos_read(self, buf, o):
        if self.pos_f32:
            return list(struct.unpack_from('>3f', buf, o))
        return [half_dec(h) for h in struct.unpack_from('>3H', buf, o)]

    def set_pos(self, i, p):
        o = self._vb(i, self.e_pos)
        b = self._pos_bytes(p)
        self.f.raw[o:o + len(b)] = b
        self.pos[i] = self._pos_read(self.f.raw, o)

    def _set_dec3n(self, e, i, v):
        o = self._vb(i, e)
        top = u32(self.f.raw, o) >> 30
        w = dec3n_enc(v, top)
        struct.pack_into('>I', self.f.raw, o, w)
        return dec3n_dec(w)

    def set_nrm(self, i, n):
        self.nrm[i] = self._set_dec3n(self.e_nrm, i, n)

    def set_tan(self, i, t):
        self.tan[i] = self._set_dec3n(self.e_tan, i, t)

    def set_skin(self, i, bones, weights):
        """Кости (номера скелета, до 4) и веса вершины i: веса квантуются в формат файла так, чтобы сумма была
        ровно 255 (u16 — 65535); пустые места — последняя кость с весом 0 (как у EA)."""
        bones, weights = list(bones)[:4], list(weights)[:4]
        while len(bones) < 4:
            bones.append(bones[-1] if bones else 0)
            weights.append(0.0)
        full = 65535 if self.w_u16 else 255
        s = sum(weights) or 1.0
        raw_q = [w / s * full for w in weights]
        q = [int(x) for x in raw_q]
        for k in sorted(range(4), key=lambda k: raw_q[k] - q[k], reverse=True)[:full - sum(q)]:
            q[k] += 1
        o = self._vb(i, self.e_bi)
        struct.pack_into('>4H', self.f.raw, o, *(b * 3 for b in bones))
        o = self._vb(i, self.e_bw)
        if self.w_u16:
            struct.pack_into('>4H', self.f.raw, o, *q)
        else:
            self.f.raw[o:o + 4] = bytes(q[::-1])
        self.bones[i] = tuple(bones)
        self.weights[i] = tuple(x / full for x in q)

    def bytes(self):
        return self.f.bytes()

    # --- другая топология: новый буфер вершин и/или индексов
    def vertex_raw(self, i):
        b = self.vo + i * self.stride
        return bytes(self.f.raw[b:b + self.stride])

    def pack_vertex(self, base, pos=None, nrm=None, tan=None, uv=None, bones=None, weights=None):
        """Новая вершина (байты шага) по образцу base (байты вершины этой сетки): заменяются заданные атрибуты."""
        v = bytearray(base)
        if pos is not None:
            b = self._pos_bytes(pos)
            v[self.e_pos.off:self.e_pos.off + len(b)] = b
        for e, val in ((self.e_nrm, nrm), (self.e_tan, tan)):
            if val is not None and e is not None:
                top = u32(v, e.off) >> 30
                struct.pack_into('>I', v, e.off, dec3n_enc(val, top))
        if uv is not None and self.e_uv:
            struct.pack_into('>2H', v, self.e_uv.off, *(max(0, min(65535, int(round(c * 65535)))) for c in uv))
        if bones is not None and self.e_bi:
            struct.pack_into('>4H', v, self.e_bi.off, *(b * 3 for b in bones))
        if weights is not None and self.e_bw and self.w_u16:
            struct.pack_into('>4H', v, self.e_bw.off, *(max(0, min(65535, int(round(w * 65535)))) for w in weights))
        elif weights is not None and self.e_bw:
            q = [max(0, min(255, int(round(w * 255)))) for w in weights]
            v[self.e_bw.off:self.e_bw.off + 4] = bytes(q[::-1])
        return bytes(v)

    def rebuilt(self, vb, indices):
        """Файл с другим буфером вершин vb (байты, кратно шагу) и индексами indices — те же секции в том же порядке;
        меняются: размеры и смещения двух секций данных (вершины с добивкой нулями до 32 байт, индексы — до 16),
        размер данных в заголовке (+0x54), в D3DVertexBuffer — размер в словах и число вершин, в D3DIndexBuffer —
        размер и число индексов, в записи вызова — числа вершин и индексов. rebuilt(свои буферы) == исходный файл
        (проверка layout_ok). У подсетки (sub) — rebuilt_sub: остальные подсетки не меняются."""
        if self.sub is not None:
            return self.rebuilt_sub(vb, indices)
        f = self.f
        st = self.stride
        if len(vb) % st:
            raise ValueError('буфер вершин не кратен шагу')
        datas = [x for x in f.sections if x.type == TYPE_DATA]
        if (len(datas) != 2 or self.vsec.off != 0 or self.isec.off != self.vsec.size
                or f.data_size != self.vsec.size + self.isec.size):
            raise ValueError(f'{self.path}: раскладка данных не «вершины, затем индексы» — пересборка не поддержана')
        nv = len(vb) // st
        if indices and max(i for i in indices if i != STRIP_RESTART) >= nv:
            raise ValueError('индекс за пределами нового буфера вершин')
        vb = bytes(vb) + bytes((-len(vb)) % 32)               # секция вершин — с добивкой до 32 байт
        ib = struct.pack('>%dH' % len(indices), *indices)
        ib += bytes((-len(ib)) % 16)
        raw = bytearray(f.raw[:f.data_start])
        table = u32(raw, 0x30)
        for sec, off, size in ((self.vsec, 0, len(vb)), (self.isec, len(vb), len(ib))):
            struct.pack_into('>I', raw, table + 24 * sec.index, off)
            struct.pack_into('>I', raw, table + 24 * sec.index + 8, size)
        struct.pack_into('>I', raw, 0x54, len(vb) + len(ib))
        o = f.one(TYPE_VB).off
        w1 = u32(raw, o + 0x1C)
        struct.pack_into('>I', raw, o + 0x1C, (w1 & ~(0xFFFFFF << 2)) | ((len(vb) // 4) << 2))
        struct.pack_into('>I', raw, o + 0x24, nv)
        o = f.one(TYPE_IB).off
        struct.pack_into('>I', raw, o + 0x1C, len(ib))
        struct.pack_into('>I', raw, o + 0x20, len(indices))
        for sd in f.find(TYPE_DRAW):
            struct.pack_into('>I', raw, sd.off + 0x04, nv)
            struct.pack_into('>I', raw, sd.off + 0x0C, len(indices))
        return bytes(raw) + vb + ib

    def rebuilt_sub(self, vb, indices):
        """Файл из нескольких подсеток с другим буфером вершин и индексами этой подсетки: секции данных (у таких
        файлов — подряд, без промежутков: сначала все буферы вершин, затем все индексы) раскладываются заново в
        прежнем порядке, их смещения и размеры — в таблице секций; размер данных в заголовке (+0x54); в
        D3DVertexBuffer, D3DIndexBuffer и вызове отрисовки этой подсетки — размеры и числа (как в rebuilt)."""
        f = self.f
        st = self.stride
        if len(vb) % st:
            raise ValueError('буфер вершин не кратен шагу')
        nv = len(vb) // st
        if indices and max(i for i in indices if i != STRIP_RESTART) >= nv:
            raise ValueError('индекс за пределами нового буфера вершин')
        vb = bytes(vb) + bytes((-len(vb)) % 32)
        ib = struct.pack('>%dH' % len(indices), *indices)
        ib += bytes((-len(ib)) % 16)
        raw = bytearray(f.raw[:f.data_start])
        table = u32(raw, 0x30)
        bodies, pos = [], 0
        for sec in sorted((x for x in f.sections if x.type == TYPE_DATA), key=lambda x: x.off):
            if sec.off != pos:
                raise ValueError(f'{self.path}: секции данных не подряд — пересборка не поддержана')
            pos += sec.size
            body = vb if sec is self.vsec else ib if sec is self.isec else f.body(sec)
            struct.pack_into('>I', raw, table + 24 * sec.index, sum(len(b) for b in bodies))
            struct.pack_into('>I', raw, table + 24 * sec.index + 8, len(body))
            bodies.append(body)
        if pos != f.data_size:
            raise ValueError(f'{self.path}: секции данных не занимают всю область данных')
        struct.pack_into('>I', raw, 0x54, sum(len(b) for b in bodies))
        o = self.vbh.off
        w1 = u32(raw, o + 0x1C)
        struct.pack_into('>I', raw, o + 0x1C, (w1 & ~(0xFFFFFF << 2)) | ((len(vb) // 4) << 2))
        struct.pack_into('>I', raw, o + 0x24, nv)
        o = self.ibh.off
        struct.pack_into('>I', raw, o + 0x1C, len(ib))
        struct.pack_into('>I', raw, o + 0x20, len(indices))
        for sd in f.find(TYPE_DRAW):
            if u32(raw, sd.off + 0x14) == self.vbh.index:
                struct.pack_into('>I', raw, sd.off + 0x04, nv)
                struct.pack_into('>I', raw, sd.off + 0x0C, len(indices))
        return bytes(raw) + b''.join(bodies)

    def layout_ok(self):
        """Пересборка своими же буферами даёт исходный файл байт в байт."""
        vb = bytes(self.f.raw[self.vo:self.vo + self.stride * self.nv])
        try:
            return self.rebuilt(vb, self.indices) == self.bytes()
        except ValueError:
            return False

    # --- служебное
    def raw_key(self, i):
        """Ключ сварки: позиция (с w) и кости/веса байт в байт — дубликаты вершины по швам UV/нормалей."""
        b = self.vo + i * self.stride
        k = bytes(self.f.raw[b + self.e_pos.off:b + self.e_pos.off + (12 if self.pos_f32 else 8)])
        if self.e_bi:
            k += bytes(self.f.raw[b + self.e_bi.off:b + self.e_bi.off + 8])
        if self.e_bw:
            k += bytes(self.f.raw[b + self.e_bw.off:b + self.e_bw.off + (8 if self.w_u16 else 4)])
        return k

    def main_bone(self, i):
        if not self.bones:
            return -1
        w = self.weights[i]
        return self.bones[i][max(range(4), key=lambda k: w[k])]

    def used(self):
        u = bytearray(self.nv)
        for t in self.tris:
            for i in t:
                u[i] = 1
        return u

    def bounds(self):
        return ([min(p[k] for p in self.pos) for k in range(3)], [max(p[k] for p in self.pos) for k in range(3)])

    def bone_usage(self):
        use = {}
        for i in range(self.nv):
            for b, w in zip(self.bones[i], self.weights[i]):
                if w > 0:
                    use[b] = use.get(b, 0) + 1
        return dict(sorted(use.items()))


def reencode_check(m):
    """Перекодировать все атрибуты из разобранных значений в копию буфера → совпадение байт в байт."""
    raw = bytearray(m.f.raw)
    bad = {}
    for i in range(m.nv):
        b = m.vo + i * m.stride
        o = b + m.e_pos.off
        pb = m._pos_bytes(m.pos[i])
        if pb != raw[o:o + len(pb)]:
            bad['position'] = bad.get('position', 0) + 1
        for name, e, vals in (('normal', m.e_nrm, m.nrm), ('tangent', m.e_tan, m.tan)):
            if e is None:
                continue
            o = b + e.off
            w = u32(raw, o)
            if dec3n_enc(vals[i], w >> 30) != w:
                bad[name] = bad.get(name, 0) + 1
        if m.e_uv:
            o = b + m.e_uv.off
            if struct.pack('>2H', *(int(round(c * 65535)) for c in m.uv[i])) != raw[o:o + 4]:
                bad['texcoord'] = bad.get('texcoord', 0) + 1
        if m.e_bi:
            o = b + m.e_bi.off
            if struct.pack('>4H', *(x * 3 for x in m.bones[i])) != raw[o:o + 8]:
                bad['blendindices'] = bad.get('blendindices', 0) + 1
        if m.e_bw and m.w_u16:
            o = b + m.e_bw.off
            if struct.pack('>4H', *(int(round(x * 65535)) for x in m.weights[i])) != raw[o:o + 8]:
                bad['blendweight'] = bad.get('blendweight', 0) + 1
        elif m.e_bw:
            o = b + m.e_bw.off
            if bytes(int(round(x * 255)) for x in m.weights[i])[::-1] != raw[o:o + 4]:
                bad['blendweight'] = bad.get('blendweight', 0) + 1
    if struct.pack('>%dH' % m.ni, *m.indices) != raw[m.io:m.io + 2 * m.ni]:
        bad['indices'] = 1
    return bad


# ---------------------------------------------------------------- векторы

def v_sub(a, b):
    return [a[0] - b[0], a[1] - b[1], a[2] - b[2]]


def v_cross(a, b):
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]


def v_dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def v_norm(a):
    ln = math.sqrt(v_dot(a, a))
    return [a[0] / ln, a[1] / ln, a[2] / ln] if ln > 1e-20 else None


def rotation_between(a, b):
    """Поворот (функция) единичного a в единичный b (Родриг); None — почти тождество или вырожденно."""
    c = v_dot(a, b)
    if c > 1 - 1e-9 or c < -0.999:
        return None
    v = v_cross(a, b)
    k = 1.0 / (1.0 + c)

    def rot(x):
        vx = v_cross(v, x)
        d = v_dot(v, x) * k
        return [x[j] * c + vx[j] + v[j] * d for j in range(3)]
    return rot


# ---------------------------------------------------------------- сварка (точки OBJ) и нормали

class Weld:
    """Вершины RW с одинаковыми позицией, костями и весами (дубликаты по швам UV и нормалей) → одна точка.
    faces — треугольники на точках (без вырожденных после сварки и без повторов) с вершинами RW углов;
    point[i] — номер точки OBJ вершины RW i (−1, если вершина не входит ни в один треугольник). Точки нумеруются по
    первой вершине RW — порядок стабилен (тот же файл → тот же порядок)."""

    def __init__(self, m):
        keys = {}
        self.group = [keys.setdefault(m.raw_key(i), len(keys)) for i in range(m.nv)]
        self.ngroups = len(keys)
        g = self.group
        seen = set()
        faces = []
        for a, b, c in m.tris:
            ga, gb, gc = g[a], g[b], g[c]
            if ga == gb or gb == gc or ga == gc:
                continue
            r = min((ga, gb, gc), (gb, gc, ga), (gc, ga, gb))      # тот же треугольник с тем же обходом
            if r in seen:
                continue
            seen.add(r)
            faces.append((a, b, c))
        self.faces = faces
        used = set(g[i] for f in faces for i in f)
        pog = {}
        for i in range(m.nv):
            if g[i] in used and g[i] not in pog:
                pog[g[i]] = len(pog)
        self.point_of_group = pog
        self.point = [pog.get(g[i], -1) for i in range(m.nv)]
        self.np = len(pog)
        self.rep = [0] * self.np                                    # вершина RW — представитель точки
        for i in range(m.nv - 1, -1, -1):
            if self.point[i] >= 0:
                self.rep[self.point[i]] = i


def group_normals(m, w, pos=None):
    """Нормали групп сварки (сумма нормалей граней с весом площади) по позициям pos (по умолчанию m.pos)."""
    pos = pos or m.pos
    acc = [[0.0, 0.0, 0.0] for _ in range(w.ngroups)]
    g = w.group
    for a, b, c in w.faces:
        fn = v_cross(v_sub(pos[b], pos[a]), v_sub(pos[c], pos[a]))
        for i in (a, b, c):
            s = acc[g[i]]
            s[0] += fn[0]
            s[1] += fn[1]
            s[2] += fn[2]
    return acc


def update_frames(m, old_pos, w=None, min_angle=1e-4):
    """После сдвига вершин: нормаль и касательная каждой вершины поворачиваются так же, как повернулась нормаль
    поверхности в её точке (сумма граней до/после) — сохраняется авторское сглаживание и швы. Вершины, где поверхность
    не повернулась, остаются байт в байт. → число изменённых вершин."""
    w = w or Weld(m)
    n0, n1 = group_normals(m, w, old_pos), group_normals(m, w)
    rots = {}
    cmin = math.cos(min_angle)
    for gi in range(w.ngroups):
        a, b = v_norm(n0[gi]), v_norm(n1[gi])
        if a is None or b is None or v_dot(a, b) > cmin:
            continue
        r = rotation_between(a, b)
        if r:
            rots[gi] = r
    done = 0
    for i in range(m.nv):
        r = rots.get(w.group[i])
        if r is None:
            continue
        n = None
        if m.e_nrm:
            n = v_norm(r(m.nrm[i])) or m.nrm[i]
            m.set_nrm(i, n)
        if m.e_tan:
            t = r(m.tan[i])
            if n is not None:
                d = v_dot(t, n)
                t = [t[j] - d * n[j] for j in range(3)]
            m.set_tan(i, v_norm(t) or m.tan[i])
        done += 1
    return done


# ---------------------------------------------------------------- OBJ

def obj_name(path):
    return os.path.splitext(os.path.basename(path))[0]


def export_obj(m, path, name=None, note=None):
    """Сетка → OBJ: v — точки сварки (порядок стабилен), vt/vn — по вершинам RW, f — треугольники. Координаты —
    метры, Y вверх (как в игре); Blender по умолчанию ставит Y файла вверх (Z сцены) и так же пишет обратно."""
    w = Weld(m)
    name = name or obj_name(m.path or path)
    out = [f'# rw4mesh.py: {m.path or name} — {m.nv} вершин RW, {w.np} точек, {len(w.faces)} треугольников',
           '# Не добавлять/удалять точки и грани, не менять их порядок: import сопоставляет точки по номеру.',
           '# Метры, поза привязки; Y вверх, +Z вперёд (к носку конька).']
    if note:
        out += ['# ' + s for s in note.splitlines()]
    out.append(f'o {name}')
    for p in range(w.np):
        x, y, z = m.pos[w.rep[p]]
        out.append(f'v {x:.7g} {y:.7g} {z:.7g}')
    for i in range(m.nv):
        u, v = m.uv[i] if m.uv else (0.0, 0.0)
        out.append(f'vt {u:.6f} {1.0 - v:.6f}')
    if m.nrm:
        for i in range(m.nv):
            out.append('vn %.4f %.4f %.4f' % tuple(m.nrm[i]))
    out.append('s off')
    pt = w.point
    for a, b, c in w.faces:
        if m.nrm:
            out.append(f'f {pt[a] + 1}/{a + 1}/{a + 1} {pt[b] + 1}/{b + 1}/{b + 1} {pt[c] + 1}/{c + 1}/{c + 1}')
        else:
            out.append(f'f {pt[a] + 1}/{a + 1} {pt[b] + 1}/{b + 1} {pt[c] + 1}/{c + 1}')
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        f.write('\n'.join(out) + '\n')
    return w


def read_obj(path):
    """→ (точки [[x, y, z]], грани [[номер точки с 0, …]], имя первого объекта)."""
    vs, faces, name = [], [], None
    with open(path, encoding='utf-8', errors='replace') as f:
        for line in f:
            if line.startswith('v '):
                vs.append([float(t) for t in line.split()[1:4]])
            elif line.startswith('f '):
                idx = []
                for tok in line.split()[1:]:
                    k = int(tok.split('/')[0])
                    idx.append(k - 1 if k > 0 else len(vs) + k)
                faces.append(idx)
            elif line.startswith('o ') and name is None:
                name = line[2:].strip()
    return vs, faces, name


def apply_obj(m, path, eps=2e-6):
    """Позиции из OBJ (сделанного export_obj и поправленного) → m (на месте), нормали/касательные — update_frames.
    Проверки: то же число точек; грани — те же тройки точек (порядок граней и углов не важен; пропавшие повторы
    допускаются, новые — нет). → отчёт."""
    w = Weld(m)
    vs, faces, _ = read_obj(path)
    if len(vs) != w.np:
        raise SystemExit(f'{path}: точек {len(vs)}, ожидалось {w.np} — сетку перестроили (добавили/удалили/слили '
                         f'вершины, применили модификатор?) — импорт по номеру невозможен')
    want = {}
    for a, b, c in w.faces:
        k = frozenset((w.point[a], w.point[b], w.point[c]))
        want[k] = want.get(k, 0) + 1
    extra = 0
    for f in faces:
        if len(f) != 3:
            raise SystemExit(f'{path}: грань из {len(f)} точек — нужны треугольники (грани не объединять)')
        k = frozenset(f)
        if want.get(k, 0) <= 0:
            extra += 1
        else:
            want[k] -= 1
    missing = sum(v for v in want.values() if v > 0)
    if extra:
        raise SystemExit(f'{path}: {extra} граней не совпадают с исходной сеткой — порядок точек изменился или '
                         f'топология перестроена; импорт по номеру невозможен')
    old = [p[:] for p in m.pos]
    moved = 0
    dmax = 0.0
    for i in range(m.nv):
        p = w.point[i]
        if p < 0:
            continue
        q = vs[p]
        if max(abs(q[k] - old[i][k]) for k in range(3)) > eps:
            m.set_pos(i, q)
            moved += 1
            dmax = max(dmax, math.sqrt(sum((m.pos[i][k] - old[i][k]) ** 2 for k in range(3))))
    frames = update_frames(m, old, w)
    return {'points': w.np, 'moved_vertices': moved, 'max_shift_mm': round(dmax * 1000, 2),
            'frames_rotated': frames, 'faces_missing_in_obj': missing}


# ---------------------------------------------------------------- перенос правки на другую детализацию

def displacement_field(src0, src1, k=6, bone_penalty=3.0):
    """Поле сдвигов по паре «исходная → поправленная» (одна и та же сетка): f(p, кость) → сдвиг (среднее k
    ближайших точек с весом 1/d²; точки на другой основной кости — «дальше» в bone_penalty раз)."""
    w = Weld(src0)
    pts, disp, bone = [], [], []
    for p in range(w.np):
        i = w.rep[p]
        pts.append(src0.pos[i])
        disp.append(v_sub(src1.pos[i], src0.pos[i]))
        bone.append(src0.main_bone(i))

    def field(q, qb):
        best = []
        for j, p in enumerate(pts):
            d2 = (p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2 + (p[2] - q[2]) ** 2
            if bone[j] != qb:
                d2 *= bone_penalty * bone_penalty
            best.append((d2, j))
        best.sort()
        sw = 0.0
        acc = [0.0, 0.0, 0.0]
        for d2, j in best[:k]:
            wt = 1.0 / (d2 + 1e-8)
            sw += wt
            for t in range(3):
                acc[t] += wt * disp[j][t]
        return [a / sw for a in acc]
    return field


def transfer(src0, src1, dst, eps=1e-6):
    """Правку src0 → src1 перенести на dst (другая детализация той же детали) — на месте; → отчёт."""
    field = displacement_field(src0, src1)
    w = Weld(dst)
    old = [p[:] for p in dst.pos]
    moved, dmax = 0, 0.0
    cache = {}
    for i in range(dst.nv):
        g = w.group[i]
        if g not in cache:
            cache[g] = field(old[i], dst.main_bone(i))
        d = cache[g]
        if max(abs(c) for c in d) > eps:
            dst.set_pos(i, [old[i][t] + d[t] for t in range(3)])
            moved += 1
            dmax = max(dmax, math.sqrt(sum(c * c for c in d)))
    frames = update_frames(dst, old, w)
    return {'moved_vertices': moved, 'max_shift_mm': round(dmax * 1000, 2), 'frames_rotated': frames}


# ---------------------------------------------------------------- скелет

SKELETON = 'rendering/skeleton_bindpose/skeleton_bindpose_player.rx2'
# ноги (номера костей скелета игрока): бедро, голень (от колена), стопа (от голеностопа), носок, конец носка,
# скрутка бедра; первая — x > 0, вторая — x < 0
LEGS = ({'thigh': 110, 'knee': 111, 'ankle': 112, 'toe': 113, 'toe_end': 114, 'twist': 115},
        {'thigh': 116, 'knee': 117, 'ankle': 118, 'toe': 119, 'toe_end': 120, 'twist': 121})
LEG_BONES = tuple(frozenset(leg.values()) for leg in LEGS)


class Skeleton:
    """skeleton_bindpose_player.rx2: две секции 0x00070003 по 122 матрицы 4×4 (строка — перенос, w = 0); первая —
    обратные матрицы позы привязки (модель → кость): сустав кости = −t·R⁻¹."""

    def __init__(self, data, path=''):
        f = Rw4File(data, path)
        b = f.body(f.find(TYPE_BINDPOSE)[0])
        n = u32(b, 4)
        self.inv = [struct.unpack_from('>16f', b, 16 + 64 * i) for i in range(n)]
        self.joints = []
        for m in self.inv:
            R = (m[0:3], m[4:7], m[8:11])
            t = m[12:15]
            self.joints.append([-(t[0] * R[j][0] + t[1] * R[j][1] + t[2] * R[j][2]) for j in range(3)])

    @classmethod
    def game(cls):
        return cls(source(SKELETON), SKELETON)


# ---------------------------------------------------------------- голень: сечения, оси, позы

SOCK = 'rendering/sock/playersock_{t}_{lod}.rx2'
TONGUE = 'rendering/skate/skatetongue_{t}_{lod}.rx2'
BOOT = 'rendering/skate/playerskate_{lod}.rx2'
LACE = 'rendering/skate/skatelace_{lod}.rx2'
SOCK_LODS = (2, 0, 3)             # 2 — ближняя (по ней — общая форма икры), 0 — средняя, 3 — дальняя; _4 игра не грузит
SHIN_YS = [round(0.18 + 0.01 * k, 2) for k in range(49)]      # 0,18…0,66 м — сетка профилей (графики)
SHIN_NA = 48                                                  # углов по кругу (7,5°)
BOOT_TOP = 0.243                  # верх ботинка playerskate_2 (м от низа лезвия)
# икра: с CALF[0] у всех вариантов одна и та же форма (среднее четырёх), до CALF[1]; переход к колену/низу шорт —
# CALF[1]…CALF[2] (низ шорт 0,585, сустав колена 0,629)
CALF = (0.36, 0.54, 0.60)
# снизу: где выравнивание икры начинается и где выходит на полную силу. 0 и 3 (в ботинке) — только над языком/
# задником (верх 0,305); 1 и 2 (поверх ботинка) — от верха ботинка
RAMP = {0: (0.30, 0.36), 1: (BOOT_TOP, 0.36), 2: (BOOT_TOP, 0.36), 3: (0.30, 0.36)}
# сужение низа (доля радиуса) у вариантов поверх ботинка: у верха ботинка и ниже — полное, к началу икры — 0
TAPER = {1: 0.15, 2: 0.15}
SHIN_MARGIN = 0.003               # гетра поверх детали конька — не ближе к её поверхности, м (и под деталью — тоже)
SHIN_GAP = 0.003                  # гетра под деталью (язык у 2): щель между ними не шире (если была уже), м
# позы для зазоров: сгиб стопы вокруг оси X сустава голеностопа (− носок вверх, + вниз) и наклон вбок (ось Z)
SHIN_POSES = (('x', 0.0), ('x', -25.0), ('x', -12.0), ('x', 10.0), ('x', 20.0), ('z', -10.0), ('z', 10.0))


def smoothstep(e0, e1, x):
    if x <= e0:
        return 0.0
    if x >= e1:
        return 1.0
    t = (x - e0) / (e1 - e0)
    return t * t * (3 - 2 * t)


def leg_of(m, i):
    b = m.main_bone(i)
    if b in LEG_BONES[0]:
        return 0
    if b in LEG_BONES[1]:
        return 1
    return 0 if m.pos[i][0] >= 0 else 1


class LegAxis:
    """Ось голени ноги side (0 — x > 0, 1 — x < 0): прямая через суставы колена и голеностопа позы привязки; at(y) —
    точка оси (x, z) на высоте y (горизонтальные сечения, ось наклонена на ~9°)."""

    def __init__(self, skel, side):
        self.side = side
        self.knee = skel.joints[LEGS[side]['knee']]
        self.ankle = skel.joints[LEGS[side]['ankle']]

    def at(self, y):
        k, a = self.knee, self.ankle
        t = (y - a[1]) / (k[1] - a[1])
        return a[0] + t * (k[0] - a[0]), a[2] + t * (k[2] - a[2])

    def polar(self, p):
        """Точка → (угол, радиус) вокруг оси на её высоте; угол 0 — наружу (от середины тела), π/2 — вперёд."""
        cx, cz = self.at(p[1])
        dx, dz = p[0] - cx, p[2] - cz
        if self.side == 1:
            dx = -dx
        return math.atan2(dz, dx), math.hypot(dx, dz)

    def place(self, y, th, r):
        cx, cz = self.at(y)
        dx, dz = r * math.cos(th), r * math.sin(th)
        if self.side == 1:
            dx = -dx
        return cx + dx, cz + dz


class Slicer:
    """Горизонтальные сечения сетки по ногам: треугольники, все вершины которых на одной ноге (leg_of); pos —
    другие позиции тех же вершин (поза). Треугольники разложены по слоям высоты (5 мм) — сечение быстрое."""
    CELL = 0.005

    def __init__(self, m, pos=None):
        pos = pos or m.pos
        self.m = m
        self.tris = ([], [])
        for t in m.tris:
            s = {leg_of(m, i) for i in t}
            if len(s) == 1:
                P = tuple(pos[i] for i in t)
                ys = (P[0][1], P[1][1], P[2][1])
                self.tris[s.pop()].append((min(ys), max(ys), P))
        self.yrange = [(min((t[0] for t in ts), default=0.0), max((t[1] for t in ts), default=0.0))
                       for ts in self.tris]
        self.cells = ({}, {})
        for side in (0, 1):
            for k, (y0, y1, _) in enumerate(self.tris[side]):
                for c in range(int(math.floor(y0 / self.CELL)), int(math.floor(y1 / self.CELL)) + 1):
                    self.cells[side].setdefault(c, []).append(k)
        self._cache = {}

    def segments(self, side, y):
        lo, hi = self.yrange[side]
        if y <= lo or y >= hi:
            return []
        key = (side, round(y, 6))
        if key in self._cache:
            return self._cache[key]
        segs = []
        tris = self.tris[side]
        for k in self.cells[side].get(int(math.floor(y / self.CELL)), ()):
            ymin, ymax, P = tris[k]
            if y <= ymin or y >= ymax:
                continue
            pts = []
            for j in range(3):
                p, q = P[j], P[(j + 1) % 3]
                if (p[1] - y) * (q[1] - y) < 0:
                    t = (y - p[1]) / (q[1] - p[1])
                    pts.append((p[0] + t * (q[0] - p[0]), p[2] + t * (q[2] - p[2])))
            if len(pts) == 2:
                segs.append(pts)
        if len(self._cache) > 20000:
            self._cache.clear()
        self._cache[key] = segs
        return segs

    def hits(self, axis, y, th):
        """Пересечения луча из оси (угол th, как LegAxis.polar) с сечением на высоте y → [r…]."""
        segs = self.segments(axis.side, y)
        if not segs:
            return []
        cx, cz = axis.at(y)
        dx, dz = math.cos(th), math.sin(th)
        if axis.side == 1:
            dx = -dx
        out = []
        for (x0, z0), (x1, z1) in segs:
            ex, ez = x1 - x0, z1 - z0
            den = -dx * ez + dz * ex
            if abs(den) < 1e-12:
                continue
            rx, rz = x0 - cx, z0 - cz
            r = (-rx * ez + rz * ex) / den
            s = (dx * rz - dz * rx) / den
            if 0.0 <= s <= 1.0 and r > 0:
                out.append(r)
        return out

    def outer(self, axis, y, th):
        h = self.hits(axis, y, th)
        return max(h) if h else 0.0


def profile(slicer, axes, ys=SHIN_YS, na=SHIN_NA):
    """Внешний радиус сетки R[нога][высота][угол] (0 — нет сечения)."""
    return [[[slicer.outer(axes[s], y, 2 * math.pi * a / na) for a in range(na)] for y in ys] for s in (0, 1)]


def mean_radius(prof_row):
    vals = [r for r in prof_row if r > 0]
    return sum(vals) / len(vals) if len(vals) == len(prof_row) else 0.0


def _rot(axis, deg):
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    if axis == 'x':
        return lambda v: [v[0], v[1] * c - v[2] * s, v[1] * s + v[2] * c]
    return lambda v: [v[0] * c - v[1] * s, v[0] * s + v[1] * c, v[2]]


def pose_point(m, i, p, skel, pose):
    """Точка p вершины i сетки m в позе pose = (ось 'x'|'z', градусы): кости стопы и носка поворачиваются вокруг
    сустава голеностопа, голень и бедро на месте (система голени); смешивание по весам вершины — как в игре."""
    axis, deg = pose
    if not deg:
        return p
    rot = _rot(axis, deg)
    acc = [0.0, 0.0, 0.0]
    sw = 0.0
    for b, w in zip(m.bones[i], m.weights[i]):
        if w <= 0:
            continue
        side = 0 if b in LEG_BONES[0] else 1 if b in LEG_BONES[1] else None
        if side is not None and b in (LEGS[side]['ankle'], LEGS[side]['toe'], LEGS[side]['toe_end']):
            a = skel.joints[LEGS[side]['ankle']]
            r = rot(v_sub(p, a))
            q = [a[0] + r[0], a[1] + r[1], a[2] + r[2]]
        else:
            q = p
        for k in range(3):
            acc[k] += w * q[k]
        sw += w
    return [c / (sw or 1.0) for c in acc]


def posed(m, skel, pose, pos=None):
    pos = pos or m.pos
    return [pose_point(m, i, pos[i], skel, pose) for i in range(m.nv)]


def pose_name(pose):
    axis, deg = pose
    if not deg:
        return 'поза привязки'
    if axis == 'x':
        return f'стопа {deg:+.0f}° ({"носок вверх" if deg < 0 else "носок вниз"})'
    return f'стопа вбок {deg:+.0f}°'


def clamp_radius(lo, hi, r0, r1, margin=SHIN_MARGIN, gap=SHIN_GAP):
    """Луч из оси голени через деталь конька (стенки lo…hi) и точку гетры (было r0, хочет r1) → допустимое r1.
    Гетра под деталью (r0 ≤ lo): наружу — не ближе margin к детали; внутрь — щель не шире gap (или прежней).
    Поверх детали (r0 ≥ hi): внутрь — не ближе margin; наружу — можно. В толще детали: наружу — не дальше её внешней
    стенки − margin; внутрь — можно (под деталью, не видно)."""
    if r0 <= lo:
        r1 = min(r1, max(r0, lo - margin))
        return max(r1, min(r0, lo - gap))
    if r0 >= hi:
        return max(r1, min(r0, hi + margin))
    if r1 > r0:
        return min(r1, max(r0, hi - margin))
    return r1


class ShinField:
    """Правка голени одного варианта гетры t: множитель радиуса вокруг оси голени
        f = (1 + strength · w(y) · (R_общая / R_свой − 1)) · (1 − taper · (1 − smoothstep(BOOT_TOP, CALF[0], y))),
    где R_свой — внешний радиус ближней (_2) сетки этого варианта, R_общая — среднее внешних радиусов ближних сеток
    всех четырёх вариантов (лучом из оси на высоте и под углом вершины — точно в вершине, без сетки профилей: при
    полной силе вершины ближней детализации всех вариантов ложатся на одну и ту же поверхность; у средней и дальней —
    с тем же отношением, они остаются «полнее» ближней настолько же, насколько были), w — 0 внизу, рост на RAMP[t],
    1 на икре, спад к колену на
    CALF[1]…CALF[2]. Сдвиг только горизонтальный (высота, UV, кости, веса — без изменений). Ограничения по деталям
    конька (ботинок, шнуровка, язык/задник своего варианта) — clamp_radius в вершинах и в точках рёбер, во всех позах
    poses (у средней детализации у низа голени есть вес стопы — деталь и гетра в позе расходятся)."""

    def __init__(self, t, axes, refs, strength=1.0, ramp=None, calf=CALF, taper=0.0, skel=None, poses=SHIN_POSES,
                 margin=SHIN_MARGIN, gap=SHIN_GAP):
        self.t, self.axes, self.refs, self.strength = t, axes, refs, strength
        self.ramp = ramp or RAMP[t]
        self.calf, self.taper, self.skel, self.margin, self.gap = calf, taper, skel, margin, gap
        self.poses = poses if skel is not None else (('x', 0.0),)
        self.obst = []
        self.clamped = self.edge_reduced = 0

    def set_obstacles(self, obstacles):
        """obstacles — [(поза, [Slicer детали в этой позе])] для правимой детализации."""
        self.obst = obstacles

    def weight(self, y):
        return smoothstep(self.ramp[0], self.ramp[1], y) * (1.0 - smoothstep(self.calf[1], self.calf[2], y))

    def taper_f(self, y):
        return 1.0 - self.taper * (1.0 - smoothstep(BOOT_TOP, self.calf[0], y)) if self.taper else 1.0

    def target_ratio(self, side, y, th):
        ax, yy = self.axes[side], y + 1e-5
        rv = self.refs[self.t].outer(ax, yy, th)
        rts = [r.outer(ax, yy, th) for r in self.refs]
        if rv <= 0 or min(rts) <= 0:
            return 1.0
        return sum(rts) / len(rts) / rv

    def _clamp_all(self, m, i, p, side, r0, r1):
        ax = self.axes[side]
        for pose, sls in self.obst:
            pk = pose_point(m, i, p, self.skel, pose)
            thk, r0k = ax.polar(pk)
            r1k = r0k + (r1 - r0)
            for ob in sls:
                for dy in (0.0, -0.004, 0.004):   # и чуть ниже/выше — грань между вершинами тоже не должна войти
                    h = ob.hits(ax, pk[1] + dy, thk)
                    if h:
                        r1k = clamp_radius(min(h), max(h), r0k, r1k, self.margin, self.gap)
            r1 = r0 + (r1k - r0k)
        return r1

    def move(self, m, i, p):
        y = p[1]
        w, tf = self.weight(y), self.taper_f(y)
        if w <= 0.0 and tf >= 1.0:
            return None
        side = leg_of(m, i)
        ax = self.axes[side]
        th, r0 = ax.polar(p)
        f = 1.0 + self.strength * w * (self.target_ratio(side, y, th) - 1.0) if w > 0 else 1.0
        r1 = r0 * f * tf
        free = r1
        if self.obst:
            r1 = self._clamp_all(m, i, p, side, r0, r1)
        if abs(r1 - free) > 1e-7:
            self.clamped += 1
        if abs(r1 - r0) < 1e-7:
            return None
        x, z = ax.place(y, th, r1)
        return [x, y, z]

    def _edge_pass(self, m, w, rep, old, new, step=0.005, passes=3):
        """Те же ограничения — в точках треугольников между вершинами (рёбра и середина; поверхность между вершинами
        плоская, и в позе тоже: GPU смешивает вершины, потом интерполирует): у крупных треугольников середина может
        войти в деталь, хотя вершины — нет. Нарушение → сдвиг всех вершин треугольника уменьшается в σ раз."""
        ymax = max(sl.yrange[sd][1] for _, sls in self.obst for sl in sls for sd in (0, 1)) + 0.03
        faces = []
        for f in w.faces:
            gs = tuple(w.group[i] for i in f)
            if all(new[g] is None for g in gs) or min(old[i][1] for i in f) > ymax:
                continue
            if len({leg_of(m, i) for i in f}) != 1:
                continue
            faces.append(gs)
        reduced = set()
        for _ in range(passes):
            sigma = {}
            for pose, sls in self.obst:
                cache = {}

                def P(g, which):
                    k = (g, which)
                    if k not in cache:
                        i = rep[g]
                        q = old[i] if which == 0 or new[g] is None else new[g]
                        cache[k] = pose_point(m, i, q, self.skel, pose)
                    return cache[k]
                for gs in faces:
                    ax = self.axes[leg_of(m, rep[gs[0]])]
                    A0, B0, C0 = (P(g, 0) for g in gs)
                    A1, B1, C1 = (P(g, 1) for g in gs)
                    n = max(3, int(max(math.dist(A0, B0), math.dist(B0, C0), math.dist(C0, A0)) / step) + 1)
                    for i in range(n + 1):
                        for j in range(n + 1 - i):
                            u, v = i / n, j / n
                            ww = 1.0 - u - v
                            if (i == n) or (j == n) or (i == 0 and j == 0):
                                continue                  # вершины — в move()
                            s0 = [u * A0[k] + v * B0[k] + ww * C0[k] for k in range(3)]
                            s1 = [u * A1[k] + v * B1[k] + ww * C1[k] for k in range(3)]
                            th0, r0 = ax.polar(s0)
                            _, r1 = ax.polar(s1)
                            if abs(r1 - r0) < 1e-6:
                                continue
                            r1c = r1
                            for ob in sls:
                                h = ob.hits(ax, s0[1], th0)
                                if h:
                                    r1c = clamp_radius(min(h), max(h), r0, r1c, self.margin, self.gap)
                            if abs(r1c - r1) > 1e-7:
                                sg = max(0.0, min(1.0, (r1c - r0) / (r1 - r0)))
                                for g in gs:
                                    sigma[g] = min(sigma.get(g, 1.0), sg)
            if not sigma:
                break
            for g, sg in sigma.items():
                if new[g] is None or sg >= 1.0:
                    continue
                i = rep[g]
                new[g] = [old[i][k] + sg * (new[g][k] - old[i][k]) for k in range(3)]
                reduced.add(g)
        return len(reduced)

    def apply(self, m, eps=1e-7):
        """Применить к сетке m (на месте): сдвиг вершин, ограничения в вершинах и на рёбрах, затем поворот
        нормалей/касательных. → отчёт."""
        w = Weld(m)
        old = [p[:] for p in m.pos]
        rep = {}
        for i in range(m.nv):
            rep.setdefault(w.group[i], i)
        done = {g: self.move(m, i, old[i]) for g, i in rep.items()}
        self.edge_reduced = self._edge_pass(m, w, rep, old, done) if self.obst else 0
        moved, dmax = 0, 0.0
        for i in range(m.nv):
            q = done[w.group[i]]
            if q is None:
                continue
            if max(abs(q[k] - old[i][k]) for k in range(3)) > eps:
                m.set_pos(i, q)
                moved += 1
                dmax = max(dmax, math.dist(m.pos[i], old[i]))
        frames = update_frames(m, old, w)
        return {'moved_vertices': moved, 'max_shift_mm': round(dmax * 1000, 2), 'frames_rotated': frames}


class Obstacles:
    """Детали конька около гетры (ботинок, шнуровка, язык/задник варианта) по детализациям и позам — кеш сечений."""

    def __init__(self, skel, poses=SHIN_POSES):
        self.skel, self.poses = skel, poses
        self._mesh, self._sl = {}, {}

    def mesh(self, rel):
        if rel not in self._mesh:
            self._mesh[rel] = Mesh.game(rel)
        return self._mesh[rel]

    def rels(self, t, lod):
        ol = lod if lod in (0, 2, 3) else 3          # у конька детализации 0, 2, 3; к _4 гетры — дальняя _3
        out = [BOOT.format(lod=ol), LACE.format(lod=ol)]
        if t != 1:
            out.append(TONGUE.format(t=t, lod=ol))
        return out

    def slicer(self, rel, pose):
        k = (rel, pose)
        if k not in self._sl:
            m = self.mesh(rel)
            self._sl[k] = Slicer(m, posed(m, self.skel, pose) if pose[1] else None)
        return self._sl[k]

    def for_variant(self, t, lod):
        return [(pose, [self.slicer(r, pose) for r in self.rels(t, lod)]) for pose in self.poses]


def shin_build(strength=1.0, variants=(0, 1, 2, 3), lods=SOCK_LODS, log=print, poses=SHIN_POSES, ramp=None,
               calf=CALF, taper=None):
    """Правка голени (см. ShinField) вариантов variants по всем детализациям lods. → ({путь: Mesh}, сводка)."""
    ramp = dict(RAMP, **(ramp or {}))
    taper = dict(TAPER if taper is None else taper)
    skel = Skeleton.game()
    axes = (LegAxis(skel, 0), LegAxis(skel, 1))
    base = {t: Mesh.game(SOCK.format(t=t, lod=2)) for t in range(4)}
    refs = [Slicer(base[t]) for t in range(4)]
    obst = Obstacles(skel, poses)
    out = {}
    summary = {'strength': strength, 'calf_m': list(calf), 'ramp_m': {str(t): list(ramp[t]) for t in range(4)},
               'taper': {str(t): taper.get(t, 0.0) for t in range(4)}, 'boot_top_m': BOOT_TOP,
               'margin_mm': SHIN_MARGIN * 1000, 'gap_mm': SHIN_GAP * 1000,
               'poses': [pose_name(p) for p in poses], 'files': {}, 'mean_radius_mm': {}}
    for t in variants:
        field = ShinField(t, axes, refs, strength, ramp[t], calf, taper.get(t, 0.0), skel, poses)
        for lod in lods:
            rel = SOCK.format(t=t, lod=lod)
            m = Mesh.game(rel)
            field.set_obstacles(obst.for_variant(t, lod))
            field.clamped = 0
            rep = field.apply(m)
            rep['clamped'] = field.clamped
            rep['clamped_edges'] = field.edge_reduced
            out[rel] = m
            summary['files'][rel] = rep
            log(f'  {rel}: сдвинуто {rep["moved_vertices"]} вершин, до {rep["max_shift_mm"]} мм; ограничено деталями '
                f'конька: {rep["clamped"]} вершин, ещё {rep["clamped_edges"]} — по треугольникам')
    profs = {t: profile(refs[t], axes) for t in range(4)}
    tgt = [mean_radius([sum(profs[t][0][i][a] for t in range(4)) / 4 for a in range(SHIN_NA)])
           if all(mean_radius(profs[t][0][i]) > 0 for t in range(4)) else 0.0 for i in range(len(SHIN_YS))]
    for t in range(4):
        after = profile(Slicer(out[SOCK.format(t=t, lod=2)]), axes) if SOCK.format(t=t, lod=2) in out else profs[t]
        summary['mean_radius_mm'][str(t)] = {
            f'{y:.2f}': [round(mean_radius(profs[t][0][i]) * 1000, 1), round(mean_radius(after[0][i]) * 1000, 1),
                         round(tgt[i] * 1000, 1)]
            for i, y in enumerate(SHIN_YS) if 0.16 <= y <= 0.62 and round(y * 100) % 2 == 0}
    return out, summary


# ---------------------------------------------------------------- проверка: гетра против деталей конька в позах

def relation_changes(sock0, sock1, obstacle, axes, ys, na=96, gap=SHIN_GAP):
    """Лучи из оси голени: как гетра (внешняя поверхность) стоит к детали до и после.
    → {событие: (число лучей, наибольшая величина, м)}: «внутри → снаружи» — гетра вылезла сквозь деталь,
    «снаружи → внутри» — деталь проткнула гетру, «… → в стенке» — в толще детали (снаружи не видно),
    «щель под деталью шире» — гетра под деталью отошла от неё больше чем на gap (и больше прежнего)."""
    out = {}

    def add(k, d):
        n, dm = out.get(k, (0, 0.0))
        out[k] = (n + 1, max(dm, d))
    for side in (0, 1):
        for y in ys:
            for i in range(na):
                th = 2 * math.pi * i / na
                oh = obstacle.hits(axes[side], y, th)
                if not oh:
                    continue
                sb, sa = sock0.hits(axes[side], y, th), sock1.hits(axes[side], y, th)
                if not sb or not sa:
                    continue
                lo, hi = min(oh), max(oh)
                b, a = max(sb), max(sa)

                def cls(r):
                    return 'внутри' if r <= lo else ('снаружи' if r >= hi else 'в стенке')
                cb, ca = cls(b), cls(a)
                if cb != ca:
                    add(f'{cb} → {ca}', (a - lo) if cb == 'внутри' else (hi - a) if cb == 'снаружи' else 0.0)
                if cb == ca == 'внутри' and lo - a > max(lo - b, gap) + 0.0005:
                    add('щель под деталью шире', (lo - a) - max(lo - b, gap))
    return out


def clearance_report(outdir, lods=(2, 0, 3), poses=SHIN_POSES, log=print):
    """Гетры из outdir против ботинка, шнуровки и языка/задника своего варианта — в позе привязки и в позах poses.
    Проблема (← ПРОВЕРИТЬ) — «внутри → снаружи», «снаружи → внутри», «щель под деталью шире» глубже 1 мм.
    → [(вариант, LOD, поза, деталь, события)]."""
    skel = Skeleton.game()
    axes = (LegAxis(skel, 0), LegAxis(skel, 1))
    obst = Obstacles(skel, poses)
    names = {BOOT[:BOOT.index('{')]: 'ботинок', LACE[:LACE.index('{')]: 'шнуровка', TONGUE[:TONGUE.index('{')]: 'язык/задник'}
    rows, bad = [], 0
    for lod in lods:
        for t in range(4):
            p = os.path.join(outdir, *SOCK.format(t=t, lod=lod).split('/'))
            if not os.path.exists(p):
                continue
            s0, s1 = Mesh.game(SOCK.format(t=t, lod=lod)), Mesh.load(p)
            for pose in poses:
                a0 = Slicer(s0, posed(s0, skel, pose) if pose[1] else None)
                a1 = Slicer(s1, posed(s1, skel, pose) if pose[1] else None)
                for rel in obst.rels(t, lod):
                    name = next(v for k, v in names.items() if rel.startswith(k))
                    ys = [0.15 + 0.0025 * k for k in range(70)]
                    ch = relation_changes(a0, a1, obst.slicer(rel, pose), axes, ys)
                    rows.append((t, lod, pose, name, ch))
                    flag = any(d > 0.001 for k, (n, d) in ch.items() if 'в стенке' not in k)
                    bad += flag
                    if ch:
                        txt = ', '.join(f'{k}: {n} (до {d * 1000:.1f} мм)' for k, (n, d) in ch.items())
                        log(f'  вариант {t}, LOD _{lod}, {pose_name(pose)}, {name}: {txt}' + ('  ← ПРОВЕРИТЬ' if flag else ''))
    log(f'  итог: {"замечаний нет" if not bad else f"{bad} мест проверить"} (прочие сочетания — как было)')
    return rows


# ---------------------------------------------------------------- превью (свой растеризатор czkit.draw_mesh)

PREVIEW_KIT = '1_23_1'                     # текстуры для картинок: «Питтсбург», выезд (светлые гетры)
PREVIEW_VIEWS = (('спереди', 0.0, (-0.30, 0.10, 0.30, 0.72)),
                 ('сбоку', 90.0, (-0.26, 0.10, 0.26, 0.72)))     # yaw, кадр (x0, y0, x1, y1) после поворота, м


class _MeshView:
    """Обёртка Mesh для czkit.draw_mesh (pos/nrm/tan/uv/tris)."""

    def __init__(self, m):
        self.pos, self.nrm, self.tan, self.uv, self.tris = m.pos, m.nrm, m.tan, m.uv, m.tris


_TEXC = {}


def preview_tex(rel, name):
    key = (rel, name) if is_nhl13() else (PROFILE.name, rel, name)
    if key not in _TEXC:
        import teamart as ta
        import kitpaint as kp
        rw = ta.Rw4(source(rel), rel)
        ts = [t for t in rw.textures if name in t.name]
        if not ts:
            raise SystemExit(f'{rel}: нет текстуры {name}')
        _TEXC[key] = kp.Img(*kp.tex_decode(rw, ts[0], 0))
    return _TEXC[key]


def render_leg(sock, t, yaw, frame, w, h, kit=PREVIEW_KIT, bg=(58, 60, 68, 255), parts=None, want_mask=False):
    """Нижняя часть игрока: шорты, гетра (sock — Mesh варианта t), ботинок, шнуровка, деталь конька t → Img
    (с want_mask — (Img, видимая гетра, фон) — маски bytearray по второму проходу плоскими цветами)."""
    import czkit as cz
    s, a, v = kit.split('_')
    parts = parts or {}
    pant = parts.get('pant') or Mesh.game(f'rendering/pant/pant_{s}_0_0_2.rx2')
    boot = parts.get('boot') or Mesh.game(BOOT.format(lod=2))
    lace = parts.get('lace') or Mesh.game('rendering/skate/skatelace_2.rx2')
    tongue = parts.get('tongue') if 'tongue' in parts else (
        Mesh.game(TONGUE.format(t=t, lod=2)) if t != 1 else None)
    cam = cz.Camera(yaw, frame, w, h)
    cv = cz.Canvas(w, h, bg)
    skate_cm = preview_tex('rendering/skate/texlib_23.rx2', 'skate_23_cm')
    others = [(pant, preview_tex(f'rendering/pant/texlib_{s}_{a}_{v}.rx2', 'pant_'),
               preview_tex(f'rendering/pant/texlib_{s}_{a}_{v}.rx2', '_nm')),
              (boot, skate_cm, None),
              (lace, preview_tex('rendering/skate/texlib_999.rx2', 'skatelace_ccm'), None)]
    if tongue is not None:
        others.append((tongue, skate_cm, None))
    sock_tex = (preview_tex(f'rendering/sock/sock_{s}_{a}_{v}_cm.rx2', 'sock_'),
                preview_tex(f'rendering/sock/sock_{s}_nm.rx2', 'sock_'))
    cz.draw_mesh(cv, cam, _MeshView(others[0][0]), others[0][1], others[0][2])
    cz.draw_mesh(cv, cam, _MeshView(sock), *sock_tex)
    for m, tx, nm in others[1:]:
        cz.draw_mesh(cv, cam, _MeshView(m), tx, nm)
    if not want_mask:
        return cv.img()
    cv2 = cz.Canvas(w, h, (0, 0, 0, 255))
    for m, _, _ in others:
        cz.draw_mesh(cv2, cam, _MeshView(m), color=(0, 0, 255), flat=1.0)
    cz.draw_mesh(cv2, cam, _MeshView(sock), color=(255, 0, 0), flat=1.0)
    px = cv2.px
    sock_vis = bytearray(1 if px[4 * i] > px[4 * i + 2] else 0 for i in range(w * h))
    bgm = bytearray(1 if cv2.z[i] <= -1e9 else 0 for i in range(w * h))
    return cv.img(), sock_vis, bgm


def outline_against(mask, bgm, w, h):
    """Пиксели mask, соседние (4-связность) с фоном bgm, — контур гетры на фоне → [(x, y)]."""
    out = []
    for y in range(1, h - 1):
        for x in range(1, w - 1):
            i = y * w + x
            if mask[i] and (bgm[i - 1] or bgm[i + 1] or bgm[i - w] or bgm[i + w]):
                out.append((x, y))
    return out


def section_paths(m, axes, heights, side=0, scale=900.0, cx=0.0, cy=0.0):
    """Сечения сетки на высотах heights (нога side) → SVG-пути в координатах «наружу / вперёд» от оси, мм·scale."""
    sl = Slicer(m)
    out = []
    for y in heights:
        ax = axes[side]
        ox, oz = ax.at(y)
        d = []
        for (x0, z0), (x1, z1) in sl.segments(side, y):
            sx0, sx1 = (x0 - ox, x1 - ox) if side == 0 else (ox - x0, ox - x1)
            d.append(f'M{cx + sx0 * scale:.1f},{cy - (z0 - oz) * scale:.1f}'
                     f'L{cx + sx1 * scale:.1f},{cy - (z1 - oz) * scale:.1f}')
        out.append(''.join(d))
    return out


def draw_points(img, pts, col):
    for x, y in pts:
        o = (y * img.w + x) * 4
        img.px[o:o + 4] = bytes(col)


def _svg_chart(series, ys, w=330, h=210, y_lo=40, y_hi=110):
    """Средний радиус голени по высоте: series [(подпись, цвет, пунктир, [r по ys или 0])] → SVG."""
    x0, x1, yb, yt = 38, w - 8, h - 24, 8
    X = lambda y: x0 + (y - ys[0]) / (ys[-1] - ys[0]) * (x1 - x0)
    Y = lambda r: yb - (r - y_lo) / (y_hi - y_lo) * (yb - yt)
    out = [f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}">',
           f'<rect x="{x0}" y="{yt}" width="{x1 - x0}" height="{yb - yt}" fill="none" stroke="#666"/>']
    for r in range(y_lo, y_hi + 1, 10):
        out.append(f'<line x1="{x0}" x2="{x1}" y1="{Y(r):.1f}" y2="{Y(r):.1f}" stroke="#444"/>'
                   f'<text x="{x0 - 4}" y="{Y(r) + 4:.1f}" text-anchor="end">{r}</text>')
    for yy in (0.25, 0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60):
        if ys[0] <= yy <= ys[-1]:
            out.append(f'<line x1="{X(yy):.1f}" x2="{X(yy):.1f}" y1="{yt}" y2="{yb}" stroke="#444"/>'
                       f'<text x="{X(yy):.1f}" y="{yb + 14}" text-anchor="middle">{yy:.2f}</text>')
    for label, col, dash, vals in series:
        pts = ' '.join(f'{X(y):.1f},{Y(r):.1f}' for y, r in zip(ys, vals) if r > 0)
        out.append(f'<polyline points="{pts}" fill="none" stroke="{col}" stroke-width="2"'
                   + (f' stroke-dasharray="{dash}"' if dash else '') + '/>')
    out.append('</svg>')
    return ''.join(out)


VAR_COLORS = ('#ff6b6b', '#4dabf7', '#69db7c', '#ffd43b')
VAR_NAMES = ('0 Full — заправлена', '1 None — поверх ботинка', '2 Front — язык наружу', '3 Back — сзади в ботинке')


def leg_parts(t):
    """Шорты, ботинок, шнуровка и деталь конька варианта t (ближняя детализация) — для render_leg."""
    return {'pant': Mesh.game('rendering/pant/pant_1_0_0_2.rx2'), 'boot': Mesh.game(BOOT.format(lod=2)),
            'lace': Mesh.game('rendering/skate/skatelace_2.rx2'),
            'tongue': Mesh.game(TONGUE.format(t=t, lod=2)) if t != 1 else None}


def preview(afters, outdir, variants=(0, 1, 2, 3), log=print, w=260, h=300, before_label='до', title=None):
    """Картинки до/после: по варианту — спереди и сбоку; на «после» — контур гетры «до» (красный, по фону);
    лист outdir/sheet.png с графиками среднего радиуса и сечениями. afters — [(подпись, {вариант: Mesh LOD _2})] или
    [(подпись, {…}, игра)]: колонка другой игры рисуется с её шортами, коньками и текстурами (game_profile)."""
    import teamart as ta
    import base64
    os.makedirs(outdir, exist_ok=True)
    skel = Skeleton.game()
    axes = (LegAxis(skel, 0), LegAxis(skel, 1))
    parts = {'pant': Mesh.game('rendering/pant/pant_1_0_0_2.rx2'), 'boot': Mesh.game(BOOT.format(lod=2)),
             'lace': Mesh.game('rendering/skate/skatelace_2.rx2')}
    before = {t: Mesh.game(SOCK.format(t=t, lod=2)) for t in range(4)}
    files = {}
    tags = [('before', before_label)] + [(f'after{k}', af[0]) for k, af in enumerate(afters)]
    fw = PREVIEW_VIEWS[0][2][2] - PREVIEW_VIEWS[0][2][0]
    for t in variants:
        pp = dict(parts, tongue=Mesh.game(TONGUE.format(t=t, lod=2)) if t != 1 else None)
        for vname, yaw, frame in PREVIEW_VIEWS:
            vw = int(round(w * (frame[2] - frame[0]) / fw))
            vtag = 'front' if yaw == 0 else 'side'
            b, vis, bgm = render_leg(before[t], t, yaw, frame, vw, h, parts=pp, want_mask=True)
            edge = outline_against(vis, bgm, vw, h)
            imgs = [b]
            for af in afters:
                res = af[1]
                other = af[2] if len(af) > 2 and af[2] != PROFILE.name else None
                if t not in res:
                    a = b.copy()
                elif other:
                    with game_profile(other):
                        a = render_leg(res[t], t, yaw, frame, vw, h, parts=leg_parts(t))
                else:
                    a = render_leg(res[t], t, yaw, frame, vw, h, parts=pp)
                draw_points(a, edge, (255, 70, 70, 255))
                imgs.append(a)
            for (st, _), img in zip(tags, imgs):
                p = os.path.join(outdir, f'sock_{t}_{vtag}_{st}.png')
                img.save(p)
                files[(t, vtag, st)] = p
            log(f'  превью: вариант {t}, {vname}')
    ys = [y for y in SHIN_YS if 0.22 <= y <= 0.62]

    def mean_prof(m):
        sl = Slicer(m)
        return [mean_radius([sl.outer(axes[0], y, 2 * math.pi * a / SHIN_NA) for a in range(SHIN_NA)]) * 1000
                for y in ys]
    pb = {t: mean_prof(before[t]) for t in range(4)}
    pas = [{t: (mean_prof(af[1][t]) if t in af[1] else pb[t]) for t in range(4)} for af in afters]
    tgt = [sum(pb[t][i] for t in range(4)) / 4 if all(pb[t][i] > 0 for t in range(4)) else 0 for i in range(len(ys))]
    charts = [(before_label, _svg_chart([(VAR_NAMES[t], VAR_COLORS[t], None, pb[t]) for t in range(4)]
                                + [('цель', '#ffffff', '3,3', tgt)], ys))]
    for af, pa in zip(afters, pas):
        charts.append((af[0], _svg_chart([(VAR_NAMES[t], VAR_COLORS[t], None, pa[t]) for t in range(4)]
                                       + [('цель', '#ffffff', '3,3', tgt)], ys)))
    hs = (0.28, 0.34, 0.40, 0.46, 0.52)
    sec = []
    first = afters[0][1] if afters else {}
    for k, y in enumerate(hs):
        cx, cy = 66 + 132 * k, 84
        sec.append(f'<text x="{cx}" y="14" text-anchor="middle">{y:.2f} м</text>'
                   f'<line x1="{cx - 60}" x2="{cx + 60}" y1="{cy}" y2="{cy}" stroke="#444"/>'
                   f'<line x1="{cx}" x2="{cx}" y1="{cy - 62}" y2="{cy + 62}" stroke="#444"/>')
        for t in range(4):
            d0 = section_paths(before[t], axes, [y], 0, 520.0, cx, cy)[0]
            sec.append(f'<path d="{d0}" stroke="{VAR_COLORS[t]}" stroke-width="1" stroke-dasharray="2,2" '
                       f'fill="none" opacity="0.85"/>')
            if t in first:
                d1 = section_paths(first[t], axes, [y], 0, 520.0, cx, cy)[0]
                sec.append(f'<path d="{d1}" stroke="{VAR_COLORS[t]}" stroke-width="1.6" fill="none"/>')
    sec_svg = f'<svg width="660" height="170" viewBox="0 0 660 170">{"".join(sec)}</svg>'

    def uri(p):
        return 'data:image/png;base64,' + base64.b64encode(open(p, 'rb').read()).decode()
    cards = []
    for t in variants:
        figs = []
        for vn, vtag in (('спереди', 'front'), ('сбоку', 'side')):
            for st, lab in tags:
                figs.append(f'<figure><img src="{uri(files[(t, vtag, st)])}"><figcaption>{vn}, {lab}</figcaption>'
                            '</figure>')
        nums = []
        for i, y in enumerate(ys):
            if y in (0.30, 0.36, 0.42, 0.48):
                nums.append(f'{y:.2f} м: {pb[t][i]:.0f} → ' + ' / '.join(f'{pa[t][i]:.0f}' for pa in pas))
        labs = ' / '.join(af[0] for af in afters)
        cards.append(f'<div class="card"><h2 style="color:{VAR_COLORS[t]}">{VAR_NAMES[t]}</h2>'
                     f'<div class="row">{"".join(figs)}</div>'
                     f'<p>средний радиус голени, мм ({before_label} → {labs}): {"; ".join(nums)}</p></div>')
    legend = ' '.join(f'<span style="color:{VAR_COLORS[t]}">■ {VAR_NAMES[t]}</span>' for t in range(4))
    chart_html = ''.join(f'<div><b>средний радиус, мм — {lab}</b><br>{svg}</div>' for lab, svg in charts)
    sec_lab = afters[0][0] if afters else ''
    html = ('<!doctype html><html><head><meta charset="utf-8"><style>'
            'body{margin:0;background:#26272c;color:#ddd;font:13px Segoe UI,Arial,sans-serif;padding:12px}'
            'h1{font-size:18px;margin:0 0 4px}h2{font-size:15px;margin:2px 0 6px}'
            '.card{background:#303138;padding:8px;border-radius:6px;margin-bottom:10px}'
            '.row{display:flex;gap:6px}figure{margin:0}'
            'figcaption{font-size:11px;color:#aaa;text-align:center}'
            'p{margin:4px 0 0;font-size:12px;color:#bbb}svg text{fill:#bbb;font-size:10px}'
            '.charts{display:flex;gap:14px;flex-wrap:wrap;background:#303138;padding:8px;border-radius:6px}'
            '</style></head><body>'
            f'<h1>{title or "Голень (гетра): до и после автоправки"}</h1>'
            f'<p>Красный контур на «после» — силуэт гетры «{before_label}». Ботинок, шнуровка, язык/задник конька '
            'и шорты не менялись. Высоты — от низа лезвия, м; радиус — от оси голени (колено → голеностоп).</p>'
            f'{"".join(cards)}'
            f'<div class="charts">{chart_html}<div><b>сечения: пунктир — {before_label}, линия — {sec_lab}'
            ' (вверх — вперёд, вправо — наружу)</b><br>' + sec_svg + '</div></div>'
            f'<p>{legend}</p></body></html>')
    side_w = int(round(w * (PREVIEW_VIEWS[1][2][2] - PREVIEW_VIEWS[1][2][0]) / fw))
    width = max(1440, 24 + 16 + (w + side_w) * (1 + len(afters)) + 6 * (2 * (1 + len(afters)) - 1))
    per_row = max(1, (width - 40) // 350)                       # графики 330 px, сечения — 660 (два места)
    rows = (len(charts) + 2 + per_row - 1) // per_row
    height = 70 + len(variants) * (h + 86) + rows * 250 + 60
    sheet = os.path.join(outdir, 'sheet.png')
    ta.render_html(html, sheet, width, height)
    log(f'  лист: {sheet}')
    return files


# ---------------------------------------------------------------- команды

def models_dir():
    """Папка работы с моделями: NHL 13 — game/work/models, Legacy — game/work/legacy-data/models."""
    if not is_nhl13():
        return PROFILE.work_dir('models')
    return os.path.join(game_dir(), 'work', 'models')


def nhl13_models_dir():
    """Готовые сборки NHL 13 (для колонки «NHL 13 с модом» на листах Legacy)."""
    return os.path.join(game_dir(), 'work', 'models')


def as_mesh(arg):
    """Путь к файлу или путь игры (rendering/…) → Mesh."""
    if os.path.exists(arg):
        return Mesh.load(arg)
    return Mesh.game(arg.replace('\\', '/'))


def game_rel(arg):
    a = arg.replace('\\', '/')
    k = a.find('rendering/')
    return a[k:] if k >= 0 else None


def lod_siblings(rel):
    """rendering/…/name_2.rx2 → те же пути с _0 и _3 (средняя и дальняя детализации), что есть в архиве игры
    (_4 игра не грузит — не трогаем)."""
    import re
    mm = re.match(r'(.*_)2\.rx2$', rel)
    if not mm:
        return []
    if not is_nhl13():
        return [mm.group(1) + f'{k}.rx2' for k in (0, 3) if game_has(mm.group(1) + f'{k}.rx2')]
    import kitpaint as kp
    _, entries, _ = kp._disc_entries(archive_of(rel))
    return [mm.group(1) + f'{k}.rx2' for k in (0, 3) if mm.group(1) + f'{k}.rx2' in entries]


def write_out(outdir, rel, m):
    p = os.path.join(outdir, *rel.split('/'))
    os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, 'wb').write(m.bytes())
    return p


def find_src_for_obj(obj_path, name):
    """Исходный путь игры по имени объекта/файла OBJ (playersock_0_2 → rendering/sock/playersock_0_2.rx2)."""
    import kitpaint as kp
    cands = [n for n in (name, obj_name(obj_path)) if n]
    for n in cands:
        n = n.split('.')[0]
        if not is_nhl13():
            hits = set()
            for arc in PROFILE.archive_order:
                root = os.path.join(PROFILE.big, arc)
                for dp, _, fs in os.walk(os.path.join(root, 'rendering')):
                    hits.update(os.path.relpath(os.path.join(dp, f), root).replace(os.sep, '/')
                                for f in fs if f.lower() == n.lower() + '.rx2')
            if len(hits) == 1:
                return hits.pop()
            continue
        for arc in ('cacherender', 'nocacherender', 'boot'):
            _, entries, _ = kp._disc_entries(arc)
            hits = [r for r in entries if r.endswith('/' + n + '.rx2')]
            if len(hits) == 1:
                return hits[0]
    raise SystemExit(f'{obj_path}: не понял, от какой сетки этот OBJ — укажите --src rendering/…/имя.rx2')


def cmd_info(paths):
    for p in paths:
        try:
            m = as_mesh(p)
        except ValueError as e:
            print(f'{p}: {e}')
            continue
        lo, hi = m.bounds()
        w = Weld(m)
        print(f'{p}: {m.nv} вершин (шаг {m.stride}), {len(m.tris)} треугольников из {m.ni} индексов полос, '
              f'{w.np} точек после сварки; шейдер {m.shader}')
        print('   вершина: ' + ', '.join(f'{e.uname} {e.tname} +{e.off}' for e in m.elements))
        print('   рамка, м: ' + ' '.join(f'{a:.3f}…{b:.3f}' for a, b in zip(lo, hi)))
        if m.bones:                                 # у сеток-реквизита (rendering/prop/…) костей нет
            print('   кости (номер: вершин с весом): ' + ', '.join(f'{b}: {n}' for b, n in m.bone_usage().items()))


def cmd_roundtrip(args):
    files = []
    for a in args:
        if os.path.isdir(a):
            files += [os.path.join(dp, f) for dp, _, fs in os.walk(a) for f in fs if f.endswith('.rx2')]
        else:
            files.append(a)
    ok = bad = skip = 0
    for p in sorted(files):
        data = open(p, 'rb').read() if os.path.exists(p) else source(p)
        try:
            m = Mesh(data, p)
        except ValueError:
            skip += 1
            continue
        res = reencode_check(m)
        same = m.bytes() == unchunk_any(data)
        lay = m.layout_ok()
        if res or not same or not lay:
            bad += 1
            print(f'НЕ СОШЛОСЬ {p}: {res or ("контейнер" if not same else "пересборка буферов")}')
        else:
            ok += 1
    print(f'сеток: {ok} байт в байт (атрибуты, контейнер, пересборка буферов), {bad} с расхождением; не сетки: {skip}')
    return bad == 0


def opt(args, name, default=None):
    if name in args:
        i = args.index(name)
        v = args[i + 1]
        del args[i:i + 2]
        return v
    return default


def flag(args, name):
    if name in args:
        args.remove(name)
        return True
    return False


def cmd_shin(args):
    strength = float(opt(args, '--strength', '1.0'))
    variants = tuple(int(x) for x in opt(args, '--variants', '0,1,2,3').split(','))
    tp = opt(args, '--taper')
    taper = None if tp is None else {1: float(tp), 2: float(tp)}
    out = opt(args, '--out', os.path.join(models_dir(), 'out'))
    objdir = opt(args, '--obj', os.path.join(models_dir(), 'obj'))
    prev = opt(args, '--preview', os.path.join(models_dir(), 'preview'))
    no_prev = flag(args, '--no-preview')
    compare = [float(x) for x in opt(args, '--compare', '').split(',') if x]
    print(f'голень: сила {strength}, варианты {variants}, икра {CALF}, сужение низа {taper or TAPER}')
    res, summary = shin_build(strength, variants, taper=taper)
    written = []
    for rel, m in res.items():
        p = os.path.join(out, *rel.split('/'))
        if m.bytes() == source(rel):                    # без изменений (дальняя детализация, где всё ограничено)
            if os.path.exists(p):
                os.remove(p)
            summary['files'][rel]['unchanged'] = True
            continue
        written.append(write_out(out, rel, m))
    import hashlib
    summary['written'] = {os.path.relpath(p, out).replace('\\', '/'): hashlib.sha1(open(p, 'rb').read()).hexdigest()
                          for p in written}
    json.dump(summary, open(os.path.join(out, 'manifest.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(f'файлы: {out} ({len(written)} шт., раскладка cache:), сводка — manifest.json')
    if objdir:
        export_objs(objdir, res, log=print)
    if not no_prev:
        lab = f'после (сила {strength:g})' if is_nhl13() else f'{PROFILE.title} с модом (сила {strength:g})'
        afters = [(lab, {t: res[SOCK.format(t=t, lod=2)] for t in variants})]
        for cs in compare:
            r2, _ = shin_build(cs, variants, lods=(2,), log=lambda *a: None, taper=taper)
            afters.append((f'сила {cs:g}', {t: r2[SOCK.format(t=t, lod=2)] for t in variants}))
        preview(afters, prev, variants, **preview_labels())


def export_objs(objdir, res=None, log=print):
    """OBJ исходных гетр (ближняя детализация) и деталей рядом (для примерки), и — если res — автоправки."""
    for t in range(4):
        m = Mesh.game(SOCK.format(t=t, lod=2))
        export_obj(m, os.path.join(objdir, f'playersock_{t}_2.obj'))
    ref = os.path.join(objdir, 'reference')
    for rel in [BOOT.format(lod=2), 'rendering/skate/skatelace_2.rx2', 'rendering/pant/pant_1_0_0_2.rx2'] + \
               [TONGUE.format(t=t, lod=2) for t in (0, 2, 3)]:
        export_obj(Mesh.game(rel), os.path.join(ref, obj_name(rel) + '.obj'))
    if res:
        for rel, m in res.items():
            if rel.endswith('_2.rx2'):
                export_obj(m, os.path.join(objdir, 'auto', obj_name(rel) + '.obj'), name=obj_name(rel),
                           note='автоправка rw4mesh.py shin — можно начать с неё; import --src — исходная сетка')
    log(f'OBJ: {objdir}')


def preview_labels():
    """Подписи листа: у NHL 13 — «до»/«после» как раньше, у другой игры — с её названием."""
    if is_nhl13():
        return {}
    return {'before_label': f'{PROFILE.title}, оригинал',
            'title': f'Голень (гетра), {PROFILE.title}: оригинал, с модом и NHL 13 с модом'}


def load_socks(out, variants):
    after = {}
    for t in variants:
        p = os.path.join(out, *SOCK.format(t=t, lod=2).split('/'))
        if os.path.exists(p):
            after[t] = Mesh.load(p)
    return after


def cmd_preview(args):
    out = opt(args, '--out', os.path.join(models_dir(), 'out'))
    prev = opt(args, '--preview', os.path.join(models_dir(), 'preview'))
    variants = tuple(int(x) for x in opt(args, '--variants', '0,1,2,3').split(','))
    nhl13_out = opt(args, '--nhl13-out', os.path.join(nhl13_models_dir(), 'out'))
    with13 = not flag(args, '--no-nhl13') and os.path.isdir(nhl13_out)
    after = load_socks(out, variants)
    lab = 'после'
    mp = os.path.join(out, 'manifest.json')
    if os.path.exists(mp):
        st = json.load(open(mp, encoding='utf-8')).get('strength')
        lab = f'сила {st:g}' if st is not None else lab
    afters = [(lab, after)]
    if not is_nhl13():
        afters = [(f'{PROFILE.title} с модом' + (f' ({lab})' if lab != 'после' else ''), after)]
        if with13:                                    # готовые гетры NHL 13 — с текстурами и коньками NHL 13
            with game_profile('nhl13'):
                afters.append(('NHL 13 с модом', load_socks(nhl13_out, variants), 'nhl13'))
    preview(afters, prev, variants, **preview_labels())


def cmd_import(args):
    src = opt(args, '--src')
    out = opt(args, '--out', os.path.join(models_dir(), 'out'))
    no_lods = flag(args, '--no-lods')
    if len(args) != 1:
        raise SystemExit('import EDITED.obj [--src rendering/…/имя.rx2] [--out DIR] [--no-lods]')
    obj = args[0]
    _, _, name = read_obj(obj)
    rel = game_rel(src) if src else find_src_for_obj(obj, name)
    if not rel:
        raise SystemExit('--src: нужен путь вида rendering/…/имя.rx2 (по нему же кладётся результат)')
    orig, m = Mesh.game(rel), Mesh.game(rel)
    rep = apply_obj(m, obj)
    print(f'{rel}: {rep}')
    write_out(out, rel, m)
    if not no_lods:
        for sib in lod_siblings(rel):
            d = Mesh.game(sib)
            r2 = transfer(orig, m, d)
            write_out(out, sib, d)
            print(f'  → {sib}: {r2}')
    print(f'готово: {out}')


def main():
    args = take_game(sys.argv[1:])
    if not args:
        print(__doc__)
        return
    cmd = args.pop(0)
    if cmd == 'info':
        cmd_info(args)
    elif cmd == 'roundtrip':
        sys.exit(0 if cmd_roundtrip(args) else 1)
    elif cmd == 'export':
        m = as_mesh(args[0])
        w = export_obj(m, args[1])
        print(f'{args[1]}: {w.np} точек, {len(w.faces)} треугольников')
    elif cmd == 'import':
        cmd_import(args)
    elif cmd == 'transfer':
        s0, s1, d = as_mesh(args[0]), as_mesh(args[1]), as_mesh(args[2])
        print(transfer(s0, s1, d))
        open(args[3], 'wb').write(d.bytes())
    elif cmd == 'shin':
        cmd_shin(args)
    elif cmd == 'preview':
        cmd_preview(args)
    elif cmd == 'check':
        clearance_report(opt(args, '--out', os.path.join(models_dir(), 'out')))
    elif cmd == 'objs':
        export_objs(opt(args, '--obj', os.path.join(models_dir(), 'obj')))
    else:
        print(__doc__)
        sys.exit(2)


if __name__ == '__main__':
    main()
