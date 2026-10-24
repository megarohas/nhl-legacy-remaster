"""Арены NHL Legacy (и NHL 13): модель арены, кресла и их цвет — разбор, картинки, перекраска кресел.

    python stadium.py map [--db DB]                     # модель арены (arenaartid) ↔ клуб, название, цвета кресел
    python stadium.py info N|FILE                       # модель stadium_<N>: слои, объекты, материалы, текстуры
    python stadium.py textures N|FILE [--out DIR]       # все текстуры модели → PNG (имя: секция, материалы) + лист
    python stadium.py crowd N|FILE                      # кресла crowd_<N>.cwd: число, ряды, ярусы, цвета по высоте
    python stadium.py render N [--cwd FILE] [--view broadcast|overview|top|end|all] [--out PNG] [--size 1600x900]
    python stadium.py recolor N RULE… [--out DIR] [--preview DIR] [--no-preview]
    python stadium.py recipe [ARENA…|all] [--recipes FILE] [--out DIR] [--preview DIR] [--approved]
    python stadium.py sheet [ARENA…] [--after] [--view overview] [--out PNG]   # лист: арены как у EA / «было | стало»
    python stadium.py nhl27 [--dir DIR] [--json OUT]    # цвет кресел NHL 27 по выгрузке fb.extract (справка)
    python stadium.py check [N…]                        # разбор всех моделей и .cwd, сборка .cwd байт в байт
    python stadium.py clone SRC --to N[,N…] [--out DIR] [--check]   # своя модель: копия модели SRC под номером N

N — номер модели арены (`exhibitionarena.arenaartid`: 0…29 — арены клубов НХЛ, 145/155 — АХЛ, 255 — «EA SPORTS
Arena», полный список — `map`). FILE — свой файл (.rx2 / .cwd). У всех команд — `--game {nhl13,legacy}`
(tools/gameprofile.py); по умолчанию — **legacy** (инструмент делался под NHL Legacy; у NHL 13 те же форматы,
но на её файлах не проверялся).

Как устроена арена (разбор 23.10.2026, подробно — docs/arenas.md):
- `rendering/stadium/stadium_<N>_container_0.rx2` — вся чаша одним контейнером RenderWare 4 (~1 500 секций): ~40
  текстур DXT1/3/5 (0x00020003 + буфер 0x00010031), ~150 сеток (объявление вершин 0x00020004, буферы 0x00020005/7,
  вызов 0x00020009, часть сетки 0x00EF0004), ~65 материалов (0x00EF0005: эффект .FX и техника; 0x00EF0000 —
  объявление параметров эффекта, little-endian; 0x00EF0001 — значения: матрицы, у sampler2D — номер секции растра),
  ~30 объектов (0x00EB0000: матрица — у всех единичная, рамка, ссылка на список 0x00EB0003 «часть сетки + материал»),
  46 слоёв отрисовки (0x00EB0008: LowerBowl, UpperBowl, Boards, Banners, Jumbotron…), таблица имён 0x00EC0010
  (число — u16 по +2: первый байт у арен — 1, поэтому старый разбор teamart.Rw4 тут ломается). Единицы — см, Y вверх,
  лёд вдоль X. Кресел в модели нет: ступени трибун и перила — серые текстуры с запечённым светом.
- `rendering/crowddata/crowd_<N>.cwd` — **кресла** (и места зрителей): «CRWD», версия 9, затем ряды (первое и последнее
  кресло, начало и конец ряда) и кресла по 56 байт: позиция (м), поворот (градусы; к льду — (cos, −sin) по X, Z),
  **цвет кресла RGB (float 0…1)**, ещё серая тройка (0 у нижних рядов, выше убывает к верху — похоже на свет), масштаб, три
  u32 (группа, уровень по высоте шагом 0,5 м, 0); в конце — границы ярусов (номер ряда). Игра грузит только .cwd
  (лог порта), .dat рядом (версия 0x105, те же кресла) — не читает.
- `renderboot rendering/crowd/chair_<v>_<lod>.rx2` — одна общая сетка кресла (v 0 — сиденье опущено, 1 — поднято,
  LOD 0…3) и общая **серая** текстура `chair_cm.rx2`; шейдер crowd_rigid умножает её на цвет кресла из .cwd
  (InstanceData). Значит, цвет кресел арены — это только числа в crowd_<N>.cwd: перекраска = новые float в копии файла,
  всё остальное — байт в байт как у EA.

Правило перекраски (RULE): `[ФИЛЬТР[,ФИЛЬТР…]:]#RRGGBB`. Без фильтра — все кресла. Фильтры (по исходным креслам,
порядок правил важен — следующее перекрывает предыдущее):
    color=#RRGGBB   кресла этого цвета (как в `crowd`, допуск ±2 на канал)
    y=A-B           высота кресла, м (0 — лёд)
    tier=A-B        ярусы файла (номер из `crowd`)
    x=A-B, z=A-B    координаты, м (лёд вдоль X)
Примеры:
    python stadium.py recolor 2 "#484948"                               # TD Garden: все кресла — чёрные
    python stadium.py recolor 27 "color=#f0a05a:#4c4c4c" "y=11-40:#4c4c4c"
    python stadium.py recipe 2 10 --preview ../game/work/legacy-data/arenas/preview
Готовое пишется копией в `game/work/legacy-data/arenas/out/rendering/crowddata/crowd_<N>.cwd` (раскладка cache:),
в игру и в cache: ничего не ставится. Картинки до/после — в `…/arenas/preview/`.

Рецепты (`tools/arena_seats.toml`): цвета кресел каждой арены на сезон 2026/27 — правила, источник, статус
(`proposed` — предложение, `approved` — одобрено пользователем; `recipe --approved` берёт только одобренные).

Своя модель (24.10.2026): у клубов на общей модели (255 — UTA, SEA, VGK, «EA SPORTS Arena») цвет кресел общий. Отдельный
цвет — копия модели под свободным номером: `clone 255 --to 222` пишет stadium_222, crowd_222, jumbotron/texlib_222,
enviro/helmet_222, particle/stadium_222.rvi и fx_222_*.lnb (номер в именах растров и эффектов переписан, остальное — байт
в байт), `--check` — только проверка номера (особые номера игры, файлы игры, записи AttribDB). Рецепт [arena.222] с
`clone_of = 255` и `arenas = [22]` (exhibitionarena.index) — цвет кресел копии и строки базы; все команды по номеру
копии берут файлы исходной. В сборку: tools/legacy_data/arenas.py (этап legacy-data arenas: файлы в out, arenaartid).

Зависимости: numpy, Pillow (venv game/work/nhl24/venv), библиотеки проекта rw4mesh, teamart, playerhead, tdb.
"""
import argparse, collections, glob, json, math, os, re, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gameprofile  # noqa: E402

try:
    import numpy as np
except ImportError:                                   # pragma: no cover
    raise SystemExit('нужен numpy (venv: game/work/nhl24/venv/Scripts/python.exe)')

PROFILE = gameprofile.get('legacy')

STADIUM_REL = 'rendering/stadium/stadium_{n}_container_0.rx2'
CROWD_REL = 'rendering/crowddata/crowd_{n}.cwd'
CHAIR_MESH_REL = 'rendering/crowd/chair_{v}_0.rx2'      # LOD 0 — 2 четырёхугольника (спинка и сиденье)
CHAIR_TEX_REL = 'rendering/crowd/chair_cm.rx2'

# секции контейнера арены
T_DATA, T_RASTER, T_VDECL, T_VB, T_IB, T_DRAW = 0x00010031, 0x00020003, 0x00020004, 0x00020005, 0x00020007, 0x00020009
T_FXDECL, T_FXVALS, T_PART, T_MATERIAL = 0x00EF0000, 0x00EF0001, 0x00EF0004, 0x00EF0005
T_OBJECT, T_BATCHES, T_LAYER, T_NAMES = 0x00EB0000, 0x00EB0003, 0x00EB0008, 0x00EC0010
TYPE_NAMES = {T_DATA: 'буфер', T_RASTER: 'растр', T_VDECL: 'объявление вершин', T_VB: 'буфер вершин',
              T_IB: 'буфер индексов', T_DRAW: 'вызов отрисовки', T_FXDECL: 'параметры эффекта',
              T_FXVALS: 'значения параметров', T_PART: 'часть сетки', T_MATERIAL: 'материал', T_OBJECT: 'объект',
              0x00EB0001: 'объект: ?', 0x00EB0002: 'объект: матрицы', T_BATCHES: 'список «сетка + материал»',
              T_LAYER: 'слой отрисовки', 0x00EB000E: 'cullinfo', T_NAMES: 'имена'}

# кресло в .cwd (56 байт, little-endian; разбор 23.10.2026 по 64 файлам Legacy)
SEAT = np.dtype([('pos', '<f4', 3),      # м; Y вверх, лёд вдоль X (как у модели, только модель в см)
                 ('yaw', '<f4'),         # градусы; направление к льду = (cos, −sin) по (X, Z)
                 ('rgb', '<f4', 3),      # цвет кресла 0…1 (EA округляет до 3 знаков)
                 ('light', '<f4', 3),    # серый 0…1: 0 у нижних рядов, выше — убывает к верху чаши; не проверено
                 ('scale', '<f4'),       # 1.0 у всех
                 ('group', '<u4'),       # 1…~300: блок кресел (назначение не проверено)
                 ('level', '<u4'),       # уровень по высоте (шаг ~0,5 м)
                 ('flags', '<u4')])      # 0 у всех
ROW = np.dtype([('first', '<u4'), ('last', '<u4'), ('p0', '<f4', 4), ('p1', '<f4', 4)])
CWD_VERSION = 9

# Цвет кресла NHL 27 (текстура с цветом) → оттенок кресла Legacy (множитель серой текстуры chair_cm):
# ×1.43 — по двум аренам, где здание и цвет кресел в обеих играх одни и те же: Tampa (#212a4b → у EA Legacy #313f64)
# и Buffalo (#253c62 → #34568c); разброс 1,33…1,50. Решение 23.10.2026 (разбор арен), см. docs/arenas.md.
NHL27_GAIN = 1.43


def use_game(name):
    global PROFILE
    PROFILE = gameprofile.get(name)
    import rw4mesh as rm
    rm.use_game(name)
    return PROFILE


def u32(b, o):
    return struct.unpack_from('>I', b, o)[0]


def hex_rgb(c):
    """'#RRGGBB' или 'RRGGBB' → (r, g, b) 0…255."""
    s = c.strip().lstrip('#')
    if not re.fullmatch(r'[0-9a-fA-F]{6}', s):
        raise ValueError(f'цвет {c!r}: нужен #RRGGBB')
    return tuple(int(s[k:k + 2], 16) for k in (0, 2, 4))


def rgb_hex(c):
    return '#%02x%02x%02x' % tuple(int(round(v)) for v in c)


def work(*parts):
    return PROFILE.work_dir('arenas', *parts)


def game_file(rel):
    """Распакованный файл игры (Legacy — game/other/legacy/big/<архив>/…, NHL 13 — через rw4mesh.source)."""
    import rw4mesh as rm
    rm.use_game(PROFILE.name)
    try:
        return rm.source(rel)
    except FileNotFoundError as e:
        raise SystemExit(f'{rel}: нет файлов игры {PROFILE.name} ({e.filename})')


def resolve(arg, rel_tmpl):
    """N или путь к файлу → (байты, подпись)."""
    if isinstance(arg, str) and os.path.isfile(arg):   # число — не путь: os.path.isfile(2) — проверка дескриптора 2 (stderr):
        return open(arg, 'rb').read(), arg             # при выводе в файл он «файл», open(2) читал и закрывал stderr (24.10)
    if not re.fullmatch(r'\d+', str(arg)):
        raise SystemExit(f'{arg}: ни номер арены, ни файл')
    rel = rel_tmpl.format(n=clone_source(int(arg)))     # своя модель (clone_of в рецепте) — файлы её исходной
    return game_file(rel), rel


# ================================================================ модель арены (.rx2)

class Material:
    __slots__ = ('sec', 'name', 'effect', 'technique', 'params', 'textures')


class Part:
    __slots__ = ('sec', 'technique', 'prim', 'vdecl', 'vb', 'ib', 'nv', 'ni', 'stride', 'elements', 'vbase', 'ibase',
                 'idx32')


class Stadium:
    """Контейнер арены: имена, растры, материалы, части сеток, объекты, слои. Только чтение."""

    def __init__(self, data, path=''):
        import rw4mesh as rm
        self.f = f = rm.Rw4File(data, path)
        self.path = path
        self.raw = f.raw
        raw = self.raw
        self.names = {}
        for s in f.find(T_NAMES):
            o = f.abs_off(s)
            n = struct.unpack_from('>H', raw, o + 2)[0]       # +0 — флаг (1 у арен), +2 — число имён, +4 — 0x1505
            for k in range(n):
                ptr, typ, idx = struct.unpack_from('>3I', raw, o + 8 + 12 * k)
                self.names[idx] = self._cstr(ptr)
        # растры
        import teamart as ta
        self.rasters = {}
        for s in f.find(T_RASTER):
            fe = ta.Fetch(struct.unpack_from('>6I', raw, f.abs_off(s) + 0x1C))
            self.rasters[s.index] = fe
        # материалы
        self.materials = {}
        for s in f.find(T_MATERIAL):
            self.materials[s.index] = self._material(s)
        # части сеток
        self.parts = {}
        for s in f.find(T_PART):
            self.parts[s.index] = self._part(s)
        # объекты и их списки «часть + материал»
        self.objects = {}
        for s in f.find(T_OBJECT):
            b = f.body(s)
            m = np.array(struct.unpack_from('>16f', b, 0x10), dtype=np.float32).reshape(4, 4)
            bb = struct.unpack_from('>8f', b, 0x50)
            lst = u32(b, 0x70)
            self.objects[s.index] = dict(name=self.names.get(s.index, f'obj{s.index}'), matrix=m,
                                         bbox=(bb[0:3], bb[4:7]), batches=self._batches(lst))
        self.layers = {}
        for s in f.find(T_LAYER):
            b = f.body(s)
            n, off = u32(b, 8), u32(b, 12)
            self.layers[s.index] = dict(name=self.names.get(s.index, f'layer{s.index}'),
                                        objects=[u32(b, off + 4 * k) for k in range(n)])
        self.layer_of = {o: L for L, d in self.layers.items() for o in d['objects']}

    @classmethod
    def load(cls, arg):
        data, label = resolve(arg, STADIUM_REL)
        return cls(data, label)

    def _cstr(self, o):
        q = self.raw.index(b'\0', o)
        return self.raw[o:q].decode('latin1')

    def _material(self, s):
        f, raw = self.f, self.raw
        o = f.abs_off(s)
        m = Material()
        m.sec, m.name = s.index, self.names.get(s.index, f'mat{s.index}')
        m.effect = self._cstr(o + 4)
        m.technique = self._cstr(o + 0x58)
        vals = f.sections[u32(raw, o + 0x50)]               # 0x00EF0001
        vo = f.abs_off(vals)
        decl = f.sections[u32(raw, vo + 4)]                 # 0x00EF0000 (little-endian)
        do = f.abs_off(decl)
        n = struct.unpack_from('<I', raw, do + 8)[0]
        b0 = do + 0x10 + 4 * n                              # n × 4 байта описаний, затем указатели: имя, ?, тип
        m.params, m.textures = {}, {}
        for k in range(n):
            name = self._cstr(struct.unpack_from('<I', raw, b0 + 4 * k)[0])
            typ = self._cstr(struct.unpack_from('<I', raw, b0 + 8 * n + 4 * k)[0])
            po = u32(raw, vo + 0x10 + 4 * k)                # значения: указатели с +0x10 (до них — 2 служебных)
            if typ.startswith('sampler'):
                r = u32(raw, po)
                m.params[name] = r
                if r in self.rasters:
                    m.textures[name] = r
            elif typ == 'int':
                m.params[name] = struct.unpack_from('>i', raw, po)[0]
            elif typ == 'float':
                m.params[name] = struct.unpack_from('>f', raw, po)[0]
            elif re.fullmatch(r'float[234]', typ):
                m.params[name] = struct.unpack_from('>%df' % int(typ[5]), raw, po)
            else:
                m.params[name] = typ
        return m

    def _part(self, s):
        import rw4mesh as rm
        f, raw = self.f, self.raw
        o = f.abs_off(s)
        p = Part()
        p.sec = s.index
        draw, p.vdecl, p.prim = u32(raw, o), u32(raw, o + 4), u32(raw, o + 8)
        p.technique = self._cstr(o + 12)
        dw = struct.unpack_from('>6I', raw, f.abs_off(f.sections[draw]))
        p.ib, p.vb = dw[4], dw[5]
        vbo = f.abs_off(f.sections[p.vb])
        fetch0 = u32(raw, vbo + 0x18)
        p.stride, p.nv = u32(raw, vbo + 0x20) >> 16, u32(raw, vbo + 0x24)
        p.vbase = f.abs_off(f.sections[fetch0 >> 2])
        ibo = f.abs_off(f.sections[p.ib])
        p.idx32 = bool(u32(raw, ibo) & 0x80000000)           # 0xC0000002 — 32-битные индексы (крупные сетки)
        p.ni = u32(raw, ibo + 0x20)
        p.ibase = f.abs_off(f.sections[u32(raw, ibo + 0x18)])
        db = f.body(f.sections[p.vdecl])
        p.elements = [rm.Element(*struct.unpack_from('>3I', db, 16 + 12 * k)) for k in range(db[8])]
        return p

    def _batches(self, sec):
        f, raw = self.f, self.raw
        o = f.abs_off(f.sections[sec])
        n = u32(raw, o + 0x10)
        out = []
        for k in range(n):
            e = o + u32(raw, o + 0x14 + 4 * k)               # рамка (2 × 4 float), часть, материал, −1
            out.append((u32(raw, e + 32), u32(raw, e + 36)))
        return out

    # --- геометрия
    def geometry(self, part):
        """Часть сетки → (позиции N×3 в метрах, uv0 N×2, uv1 N×2 или None, цвет N×4 uint8 или None, треугольники M×3)."""
        import rw4mesh as rm
        p = self.parts[part] if isinstance(part, int) else part
        buf = np.frombuffer(bytes(self.raw[p.vbase:p.vbase + p.stride * p.nv]), dtype=np.uint8).reshape(p.nv, p.stride)
        pos = uv0 = uv1 = col = None
        uvs = []
        for e in p.elements:
            seg = buf[:, e.off:e.off + rm.DECL_INFO.get(e.type, ('', 0))[1]]
            if e.usage == 0 and e.type == rm.DECL_FLOAT3:
                pos = np.frombuffer(seg.tobytes(), dtype='>f4').reshape(p.nv, 3).astype(np.float32) / 100.0
            elif e.usage == 5 and e.tname == 'FLOAT2':
                uvs.append(np.frombuffer(seg.tobytes(), dtype='>f4').reshape(p.nv, 2).astype(np.float32))
            elif e.usage == 10 and e.tname == 'D3DCOLOR':
                col = seg[:, [1, 2, 3, 0]].copy()             # в файле A, R, G, B → R, G, B, A
        if pos is None:
            raise ValueError(f'{self.path}: часть {p.sec} без позиции FLOAT3')
        uv0 = uvs[0] if uvs else np.zeros((p.nv, 2), np.float32)
        uv1 = uvs[1] if len(uvs) > 1 else None
        isz = 4 if p.idx32 else 2
        idx = np.frombuffer(bytes(self.raw[p.ibase:p.ibase + isz * p.ni]), dtype='>u4' if p.idx32 else '>u2')
        idx = idx.astype(np.int64)
        if p.prim == rm.PRIM_TRIANGLELIST:
            tris = idx[:len(idx) // 3 * 3].reshape(-1, 3)
        else:
            tris = np.array(rm.triangles(idx.tolist(), p.prim) or np.zeros((0, 3)), dtype=np.int64).reshape(-1, 3)
        tris = tris[(tris < p.nv).all(1)]
        return pos, uv0, uv1, col, tris

    def texture(self, raster, max_side=None):
        """Растр → (w, h, RGBA uint8 h×w×4); max_side — взять мип не больше этого размера (быстрее)."""
        import teamart as ta
        fe = self.rasters[raster]
        lay = ta.Layout(fe)
        ds = self.f.sections[fe.base]
        buf = self.raw[self.f.abs_off(ds):self.f.abs_off(ds) + ds.size]
        lv = 0
        if max_side:
            while lv + 1 < len(lay.levels) and max(lay.levels[lv][:2]) > max_side:
                lv += 1
        w, h = lay.levels[lv][:2]
        rgba = ta.dxt_decode(fe.fmt, lay.get_level(buf, lv), w, h)
        return w, h, np.frombuffer(rgba, dtype=np.uint8).reshape(h, w, 4)

    def raster_users(self):
        users = collections.defaultdict(list)
        for m in self.materials.values():
            for par, r in m.textures.items():
                users[r].append((m.name, par))
        return users


# ================================================================ кресла (.cwd)

class Crowd:
    """crowd_<N>.cwd: ряды и кресла; правка — только цвет кресел (seats['rgb'] пишет прямо в raw)."""

    def __init__(self, data, path=''):
        if data[:4] != b'CRWD':
            raise ValueError(f'{path}: не CRWD')
        ver, nseat, nrow, ntier, self.loose = struct.unpack_from('<5I', data, 4)   # loose — кресел до первого ряда
        if ver != CWD_VERSION:
            hint = ' (.dat версии 0x105 игра не читает — нужен .cwd)' if ver == 0x105 else ''
            raise ValueError(f'{path}: версия CRWD {ver:#x}, разобрана {CWD_VERSION}{hint}')
        self.raw = bytearray(data)
        self.path = path
        self.row_off = 0x18
        self.seat_off = self.row_off + ROW.itemsize * nrow
        self.tier_off = self.seat_off + SEAT.itemsize * nseat
        if self.tier_off + 4 * ntier != len(data):
            raise ValueError(f'{path}: размер {len(data)} ≠ заголовок + {nrow} рядов + {nseat} кресел + {ntier} ярусов')
        self.rows = np.frombuffer(self.raw, dtype=ROW, count=nrow, offset=self.row_off)
        self.seats = np.frombuffer(self.raw, dtype=SEAT, count=nseat, offset=self.seat_off)
        self.tier_ends = np.frombuffer(self.raw, dtype='<u4', count=ntier, offset=self.tier_off)
        if nrow and (self.rows['first'][0] != self.loose or self.rows['last'][-1] != nseat - 1 or
                     (self.rows['first'][1:] != self.rows['last'][:-1] + 1).any()):
            raise ValueError(f'{path}: ряды не покрывают кресла подряд')

    @classmethod
    def load(cls, arg):
        data, label = resolve(arg, CROWD_REL)
        return cls(data, label)

    @property
    def n(self):
        return len(self.seats)

    def seat_rows(self):
        r = np.full(self.n, -1, np.int64)             # −1 — кресла до первого ряда (loose; у 700–703)
        for k, (a, b) in enumerate(zip(self.rows['first'], self.rows['last'])):
            r[a:b + 1] = k
        return r

    def seat_tiers(self):
        return np.searchsorted(np.asarray(self.tier_ends, np.int64), self.seat_rows(), side='right')

    def bowls(self, gap=1.2):
        """Уровни чаши по разрывам высоты кресел больше gap м: [(y от, y до, число кресел)] снизу вверх."""
        y = np.sort(self.seats['pos'][:, 1])
        if not len(y):
            return []
        cut = np.nonzero(np.diff(y) > gap)[0]
        out, a = [], 0
        for c in list(cut) + [len(y) - 1]:
            out.append((float(y[a]), float(y[c]), int(c - a + 1)))
            a = c + 1
        return out

    def colors255(self):
        return np.rint(self.seats['rgb'] * 255).astype(np.int64)

    def color_groups(self):
        """[(hex, число кресел, маска)] по убыванию; соседние оттенки (±2) EA — один цвет."""
        c = self.colors255()
        out, left = [], np.ones(self.n, bool)
        while left.any():
            keys, cnt = np.unique(c[left], axis=0, return_counts=True)
            k = keys[cnt.argmax()]
            m = left & (np.abs(c - k).max(1) <= 2)
            out.append((rgb_hex(k), int(m.sum()), m))
            left &= ~m
        return out

    def set_rgb(self, mask, rgb):
        v = np.round(np.asarray(rgb, np.float64) / 255.0, 3).astype(np.float32)      # как у EA: 3 знака
        self.seats['rgb'][mask] = v

    def bytes(self):
        return bytes(self.raw)


def parse_rule(text):
    """'[ф=…,ф=…:]#RRGGBB' → (фильтры [(имя, значение)], (r, g, b))."""
    if ':' in text:
        flt, col = text.rsplit(':', 1)
    else:
        flt, col = '', text
    filters = []
    for part in filter(None, (p.strip() for p in flt.split(','))):
        if '=' not in part:
            raise ValueError(f'правило {text!r}: фильтр {part!r} — нужно имя=значение')
        k, v = (s.strip() for s in part.split('=', 1))
        if k == 'color':
            filters.append((k, hex_rgb(v)))
        elif k in ('y', 'x', 'z', 'tier'):
            m = re.fullmatch(r'(-?[\d.]+)\s*-\s*(-?[\d.]+)', v)
            if not m:
                raise ValueError(f'правило {text!r}: {k}={v} — нужен диапазон A-B')
            filters.append((k, (float(m.group(1)), float(m.group(2)))))
        else:
            raise ValueError(f'правило {text!r}: фильтр {k!r} неизвестен (color, y, x, z, tier)')
    return filters, hex_rgb(col)


def rule_mask(crowd, filters, base_rgb=None, tiers=None):
    m = np.ones(crowd.n, bool)
    c = crowd.colors255() if base_rgb is None else base_rgb
    for k, v in filters:
        if k == 'color':
            m &= np.abs(c - np.array(v)).max(1) <= 2
        elif k in ('x', 'y', 'z'):
            col = crowd.seats['pos'][:, 'xyz'.index(k)]
            m &= (col >= v[0]) & (col <= v[1])
        elif k == 'tier':
            t = crowd.seat_tiers() if tiers is None else tiers
            m &= (t >= v[0]) & (t <= v[1])
    return m


def apply_rules(crowd, rules):
    """Правила по исходным креслам; → [(правило, сколько кресел)]."""
    base = crowd.colors255()
    tiers = crowd.seat_tiers()
    report = []
    for r in rules:
        filters, rgb = parse_rule(r)
        m = rule_mask(crowd, filters, base, tiers)
        crowd.set_rgb(m, rgb)
        report.append((r, int(m.sum())))
    return report


# ================================================================ база: арена ↔ клуб

def default_db():
    """База, которую ставит legacy-data (game/work/legacy-data/out/db), иначе исходная база игры."""
    p = os.path.join(PROFILE.out, 'db', 'nhlng.db')
    meta = os.path.join(PROFILE.out, 'db', 'nhlng-meta.xml')
    if os.path.exists(p):
        return p, meta if os.path.exists(meta) else PROFILE.meta
    return PROFILE.db, PROFILE.meta


def arena_map(db_path=None, meta_path=None):
    """{arenaartid: {'arenas': [(строка, название, город, мест)], 'clubs': [(строка, аббр, название)]}}."""
    import tdb
    from tdb_read import load_meta
    if not db_path:
        db_path, meta_path = default_db()
    db = tdb.Tdb(open(db_path, 'rb').read(), load_meta(meta_path or PROFILE.meta))
    out = collections.defaultdict(lambda: {'arenas': [], 'clubs': []})
    arena_art = {}
    for r in db.live_rows('exhibitionarena'):
        v = lambda f: db.value('exhibitionarena', f, r, False)      # noqa: E731
        art = v('arenaartid')
        arena_art[v('index')] = art
        out[art]['arenas'].append((r, v('arenaname'), v('cityname'), v('maxattendance')))
    for r in db.live_rows('exhibitionteams'):
        v = lambda f: db.value('exhibitionteams', f, r, False)      # noqa: E731
        art = arena_art.get(v('arenaid'))
        if art is not None:
            out[art]['clubs'].append((r, v('abbrname'), v('fullname'), v('league')))
    return dict(out), db_path


# ================================================================ картинки

def _look_at(eye, target, up=(0, 1, 0)):
    eye, target, up = (np.asarray(v, np.float64) for v in (eye, target, up))
    f = target - eye
    f /= np.linalg.norm(f)
    r = np.cross(f, up)
    r /= np.linalg.norm(r)
    u = np.cross(r, f)
    return eye, np.stack([r, u, f])


VIEWS = {
    # глаз, цель (м; лёд вдоль X, центр — 0), поле зрения по горизонтали (градусы); top — вид сверху (ортогонально,
    # без крыши и куба: всё выше верхнего ряда кресел + 1 м не рисуется)
    'broadcast': ((0.0, 13.0, -24.0), (0.0, 4.0, 14.0), 72.0),      # камера трансляции: дальние трибуны
    'overview': ((-34.0, 27.0, -27.0), (8.0, 4.0, 8.0), 80.0),      # чаша сверху, из угла
    'end': ((-46.0, 11.0, 0.0), (20.0, 6.0, 0.0), 75.0),            # из-за ворот на противоположную сторону
    'top': None,
}

# слои, которые в превью не рисуются (стекло, отражения, служебное)
SKIP_LAYERS = re.compile(r'^(Reflection_.*|Gameplay_Glass|BoardGlass|AnimatedBoardsGlass_.*|Camera_Position_.*|'
                         r'IceSnow|IceScratch|IceBase|PowerRingGlow|Crowd_2D|Banners)$')   # Banners: полотна с альфой рисуются сплошными
SKIP_EFFECTS = re.compile(r'glass', re.I)


def _sample(tex, uv):
    h, w = tex.shape[:2]
    x = np.mod(np.floor(uv[:, 0] * w).astype(np.int64), w)
    y = np.mod(np.floor(uv[:, 1] * h).astype(np.int64), h)
    return tex[y, x].astype(np.float32) / 255.0


def stadium_triangles(st, layers_skip=SKIP_LAYERS):
    """Треугольники модели для превью: вершины T×3×3 (м) и цвет T×3 (0…1, с запечённым светом)."""
    texcache = {}

    def tex(r):
        if r not in texcache:
            texcache[r] = st.texture(r, max_side=128)[2]
        return texcache[r]

    V, C = [], []
    seen = set()
    for osec, obj in st.objects.items():
        lname = st.layers.get(st.layer_of.get(osec), {}).get('name', '')
        if layers_skip and layers_skip.match(lname):
            continue
        for part, msec in obj['batches']:
            if (part, msec) in seen:
                continue
            seen.add((part, msec))
            mat = st.materials.get(msec)
            if mat is None or SKIP_EFFECTS.search(mat.effect) or part not in st.parts:
                continue
            pos, uv0, uv1, col, tris = st.geometry(part)
            if not len(tris):
                continue
            tv = pos[tris]                                          # T×3×3
            cuv = uv0[tris].mean(1)
            diffuse = next((mat.textures[k] for k in ('diffuseTexture', 'map2', 'map1') if k in mat.textures), None)
            if diffuse is not None:
                s = _sample(tex(diffuse), cuv)
                rgb, alpha = s[:, :3], s[:, 3]
            else:
                rgb, alpha = np.full((len(tris), 3), 0.6, np.float32), np.ones(len(tris), np.float32)
            light = np.ones((len(tris), 1), np.float32)
            amb = mat.textures.get('ambientTexture')
            if amb is not None and uv1 is not None:
                s = _sample(tex(amb), uv1[tris].mean(1))
                light = s[:, :3] * (s[:, 3:4] * 255.0 / 17.0) * 0.5      # альфа 34/51 — множитель 2/3 (как у вершин)
            elif col is not None:
                c = col[tris].astype(np.float32).mean(1)
                light = c[:, :3] / 255.0 * (c[:, 3:4] / 17.0) * 0.9
            light = np.clip(light * 1.6, 0.15, 1.6)
            keep = alpha > 0.35
            V.append(tv[keep])
            C.append(np.clip(rgb[keep] * light[keep], 0, 1))
    if not V:
        return np.zeros((0, 3, 3), np.float32), np.zeros((0, 3), np.float32)
    return np.concatenate(V), np.concatenate(C)


def chair_template():
    """Простое кресло игры (chair_<v>_0: спинка и сиденье, 4 треугольника): {v: (вершины N×3, uv N×2, тр. M×3)}."""
    import rw4mesh as rm
    out = {}
    for v in (0, 1):
        m = rm.Mesh(game_file(CHAIR_MESH_REL.format(v=v)), CHAIR_MESH_REL.format(v=v))
        uv = np.array([[rm.half_dec(h) for h in struct.unpack_from('>2H', m.f.raw, m.vo + i * m.stride + 8)]
                       for i in range(m.nv)], np.float32)
        out[v] = (np.array(m.pos, np.float32), uv, np.array(m.tris, np.int64))
    return out


def chair_texture():
    import teamart as ta
    t = ta.Rw4(game_file(CHAIR_TEX_REL), CHAIR_TEX_REL)
    w, h, rgba = t.decode(t.textures[0])
    return np.frombuffer(rgba, np.uint8).reshape(h, w, 4)


def seat_triangles(crowd, chair=None, chairtex=None, folded=True):
    """Кресла как в игре без зрителей (поднятое сиденье chair_1_0 — пустое место): вершины T×3×3, цвет T×3."""
    chair = chair or chair_template()
    if chairtex is None:
        chairtex = chair_texture()
    verts, uv, tris = chair[1 if folded else 0]
    shade = _sample(chairtex, uv[tris].mean(1))[:, :3].mean(1)          # серый множитель текстуры, по треугольнику
    S = crowd.seats
    yaw = np.radians(S['yaw'].astype(np.float64))
    F = np.stack([np.cos(yaw), np.zeros_like(yaw), -np.sin(yaw)], 1)     # к льду
    U = np.array([0.0, 1.0, 0.0])
    R = np.cross(U, F)
    sc = S['scale'][:, None].astype(np.float64)
    P = S['pos'].astype(np.float64)
    loc = verts.astype(np.float64)
    world = (P[:, None, :] + sc[:, None] * (loc[None, :, 0:1] * R[:, None, :] + loc[None, :, 1:2] * U +
                                             loc[None, :, 2:3] * F[:, None, :]))           # S×N×3
    tv = world[:, tris]                                                   # S×M×3×3
    # серая текстура кресла даёт 0,3…0,9; для наглядности цвета — смесь 55 % цвета и 45 % текстуры (приближение:
    # в игре ещё свет арены gStadiumLightColor и зрители на занятых местах)
    col = S['rgb'][:, None, :].astype(np.float32) * (0.55 + 0.45 * shade[None, :, None]) * 1.1
    return tv.reshape(-1, 3, 3).astype(np.float32), np.clip(col.reshape(-1, 3), 0, 1)


def rink_triangles():
    """Лёд для ориентира: площадка НХЛ 60,96 × 25,9 м (углы r 8,5 м), красная и синие линии."""
    L, W, R = 30.48, 12.95, 8.53
    pts = []
    for cx, cz, a0 in ((L - R, W - R, 0), (-(L - R), W - R, 90), (-(L - R), -(W - R), 180), (L - R, -(W - R), 270)):
        for k in range(9):
            a = math.radians(a0 + 90 * k / 8)
            pts.append((cx + R * math.cos(a), cz + R * math.sin(a)))
    V, C = [], []
    for i in range(len(pts)):
        a, b = pts[i], pts[(i + 1) % len(pts)]
        V.append([(0, 0.01, 0), (a[0], 0.01, a[1]), (b[0], 0.01, b[1])])
        C.append((0.86, 0.88, 0.9))
    for x0, x1, c in ((-0.15, 0.15, (0.75, 0.1, 0.1)), (-7.77, -7.47, (0.1, 0.2, 0.7)), (7.47, 7.77, (0.1, 0.2, 0.7))):
        V += [[(x0, 0.02, -W), (x1, 0.02, -W), (x1, 0.02, W)], [(x0, 0.02, -W), (x1, 0.02, W), (x0, 0.02, W)]]
        C += [c, c]
    return np.array(V, np.float32), np.array(C, np.float32)


def draw(V, C, view, size, bg=(18, 20, 24), ss=2, top_clip=None):
    """Треугольники → картинка PIL (художник: от дальних к ближним, сглаживание ss×). top_clip — у вида сверху не
    рисовать треугольники целиком выше этой высоты (крыша, куб)."""
    from PIL import Image, ImageDraw
    W, H = size
    Wi, Hi = W * ss, H * ss
    if view == 'top':
        if top_clip is not None:
            keep = V[..., 1].min(1) <= top_clip
            V, C = V[keep], C[keep]
        x, z = V[..., 0], V[..., 2]
        span = 80.0
        k = min(Wi / (2 * span * 1.0), Hi / (2 * 60.0))
        sx = Wi / 2 + x * k
        sy = Hi / 2 - z * k
        depth = -V[..., 1].mean(1)
        ok = np.ones(len(V), bool)
    else:
        eye, rot = _look_at(*VIEWS[view][:2])
        fov = math.radians(VIEWS[view][2])
        q = (V.reshape(-1, 3).astype(np.float64) - eye) @ rot.T
        q = q.reshape(-1, 3, 3)
        zc = q[..., 2]
        ok = (zc > 0.3).all(1)
        f = (Wi / 2) / math.tan(fov / 2)
        with np.errstate(divide='ignore', invalid='ignore'):
            sx = Wi / 2 + f * q[..., 0] / zc
            sy = Hi / 2 - f * q[..., 1] / zc
        depth = zc.mean(1)
        ok &= ((sx > -Wi) & (sx < 2 * Wi) & (sy > -Hi) & (sy < 2 * Hi)).all(1)
    order = np.argsort(-depth[ok], kind='stable')
    sx, sy, cc = sx[ok][order], sy[ok][order], (np.clip(C[ok][order], 0, 1) * 255).astype(np.uint8)
    im = Image.new('RGB', (Wi, Hi), bg)
    dr = ImageDraw.Draw(im)
    for k in range(len(order)):
        c = tuple(int(v) for v in cc[k])
        dr.polygon([(sx[k, 0], sy[k, 0]), (sx[k, 1], sy[k, 1]), (sx[k, 2], sy[k, 2])], fill=c, outline=c)
    return im.resize((W, H), Image.LANCZOS) if ss > 1 else im


_SCENE = {}


def scene(st):
    """Треугольники модели арены и льда (кэш на время запуска: «было/стало» рисуют одну модель дважды)."""
    key = id(st)
    if key not in _SCENE:
        V1, C1 = stadium_triangles(st)
        V3, C3 = rink_triangles()
        _SCENE[key] = (st, np.concatenate([V1, V3]), np.concatenate([C1, C3]))
    return _SCENE[key][1:]


def render(n, crowd=None, views=('broadcast',), size=(1600, 900), stadium=None, label=None):
    """Модель N + кресла (crowd — Crowd или None: исходный crowd_<N>) → {вид: картинка}."""
    st = stadium or Stadium.load(n)
    crowd = crowd if crowd is not None else Crowd.load(n)
    V1, C1 = scene(st)
    V2, C2 = seat_triangles(crowd)
    V, C = np.concatenate([V1, V2]), np.concatenate([C1, C2])
    out = {}
    clip = float(crowd.seats['pos'][:, 1].max()) + 1.0 if crowd.n else None
    for v in views:
        im = draw(V, C, v, size, top_clip=clip)
        if label:
            caption(im, label if v == 'broadcast' else f'{label} — {v}')
        out[v] = im
    return out


def caption(im, text, xy=(12, 10)):
    from PIL import ImageDraw, ImageFont
    dr = ImageDraw.Draw(im)
    font = None
    for p in ('C:/Windows/Fonts/segoeui.ttf', 'C:/Windows/Fonts/arial.ttf'):
        if os.path.exists(p):
            font = ImageFont.truetype(p, 26)
            break
    font = font or ImageFont.load_default()
    x, y = xy
    bb = dr.textbbox((x, y), text, font=font)
    dr.rectangle((bb[0] - 6, bb[1] - 4, bb[2] + 6, bb[3] + 4), fill=(0, 0, 0))
    dr.text((x, y), text, fill=(255, 255, 255), font=font)


def swatches(im, colors, xy):
    """Полоска образцов цвета кресел [(hex, подпись)] в углу картинки."""
    from PIL import ImageDraw, ImageFont
    dr = ImageDraw.Draw(im)
    try:
        font = ImageFont.truetype('C:/Windows/Fonts/segoeui.ttf', 20)
    except OSError:
        font = ImageFont.load_default()
    x, y = xy
    for hx, text in colors:
        dr.rectangle((x, y, x + 34, y + 24), fill=hex_rgb(hx), outline=(255, 255, 255))
        dr.text((x + 42, y), f'{hx} {text}', fill=(255, 255, 255), font=font, stroke_width=2, stroke_fill=(0, 0, 0))
        y += 30


def before_after(n, crowd_new, outdir, title='', views=('broadcast', 'overview'), size=(1280, 720)):
    """Картинки «было | стало» по видам → пути PNG."""
    from PIL import Image
    st = Stadium.load(n)
    old = Crowd.load(n)
    a = render(n, old, views, size, stadium=st)
    b = render(n, crowd_new, views, size, stadium=st)
    os.makedirs(outdir, exist_ok=True)
    paths = []
    for v in views:
        im = Image.new('RGB', (size[0] * 2 + 8, size[1]), (255, 255, 255))
        A, B = a[v], b[v]
        caption(A, f'{title} — было (EA)'.strip(' —'))
        caption(B, f'{title} — стало'.strip(' —'))
        swatches(A, [(h, f'{c}') for h, c, _ in old.color_groups()[:4]], (12, size[1] - 34 * min(4, len(old.color_groups())) - 6))
        swatches(B, [(h, f'{c}') for h, c, _ in crowd_new.color_groups()[:4]],
                 (12, size[1] - 34 * min(4, len(crowd_new.color_groups())) - 6))
        im.paste(A, (0, 0))
        im.paste(B, (size[0] + 8, 0))
        p = os.path.join(outdir, f'arena_{n}_{v}.png')
        im.save(p)
        paths.append(p)
    return paths


def color_map(crowd, size=(900, 700), title=''):
    """План кресел сверху: каждое кресло — точка своего цвета (без модели арены)."""
    from PIL import Image, ImageDraw
    W, H = size
    im = Image.new('RGB', size, (24, 26, 30))
    dr = ImageDraw.Draw(im)
    P = crowd.seats['pos']
    k = min(W / 160.0, H / 120.0)
    order = np.argsort(P[:, 1])
    rgb = np.clip(crowd.seats['rgb'] * 255, 0, 255).astype(int)
    for i in order:
        x, z = W / 2 + P[i, 0] * k, H / 2 - P[i, 2] * k
        dr.rectangle((x - 1.2, z - 1.2, x + 1.2, z + 1.2), fill=tuple(rgb[i]))
    if title:
        caption(im, title)
    return im


# ================================================================ NHL 27 (справка)

NHL27_CITY = {   # папка кресел NHL 27 → клуб Legacy (номер модели арены Legacy; None — своей модели у Legacy нет)
    'anaheim': ('ANA', 0), 'winnipeg': ('WPG', 1), 'boston': ('BOS', 2), 'buffalo': ('BUF', 3), 'calgary': ('CGY', 4),
    'carolina': ('CAR', 5), 'chicago': ('CHI', 6), 'colorado': ('COL', 7), 'columbus': ('CBJ', 8), 'dallas': ('DAL', 9),
    'detroit': ('DET', 10), 'edmonton': ('EDM', 11), 'florida': ('FLA', 12), 'losangeles': ('LA', 13),
    'minnesota': ('MIN', 14), 'montreal': ('MTL', 15), 'nashville': ('NSH', 16), 'newjersey': ('NJ', 17),
    'nyislanders': ('NYI', 18), 'nyrangers': ('NYR', 19), 'ottawa': ('OTT', 20), 'philadelphia': ('PHI', 21),
    'utah': ('UTA', None), 'pittsburgh': ('PIT', 23), 'stlouis': ('STL', 24), 'sanjose': ('SJ', 25),
    'tampa': ('TB', 26), 'toronto': ('TOR', 27), 'vancouver': ('VAN', 28), 'washington': ('WSH', 29),
    'seattle': ('SEA', None), 'vegas': ('VGK', None),
}


def nhl27_default_dir():
    return os.path.join(gameprofile.game_dir(), 'work', 'nhl27', 'extract', 'chairs27', 'crowd', 'agent', 'prop',
                        'chair', 'textures')


def nhl27_chairs(root=None):
    """Замер текстур кресел NHL 27 (`crowd_chair_<город>_<0…3>_color`, выгрузка fb.extract): основной цвет каждого
    варианта — самый частый оттенок (шаг 8) и его доля. → {город: [(hex, доля) ×4]}."""
    from PIL import Image
    root = root or nhl27_default_dir()
    if not os.path.isdir(root):
        raise SystemExit(f'{root}: нет выгрузки кресел NHL 27. Сначала (из tools/): FB_GAME=nhl27 python -m fb.extract '
                         '"crowd/agent/prop/chair/textures/[a-z0-9]+/crowd_chair_[a-z0-9]+_[0-3]_color$" --out chairs27')
    out = {}
    for city in sorted(os.listdir(root)):
        vs = []
        for v in range(4):
            p = os.path.join(root, city, f'crowd_chair_{city}_{v}_color.png')
            if not os.path.exists(p):
                vs.append(None)
                continue
            a = np.array(Image.open(p).convert('RGB')).reshape(-1, 3).astype(np.int64)
            key = (a // 8) @ np.array([1024, 32, 1])
            vals, cnt = np.unique(key, return_counts=True)
            k = vals[cnt.argmax()]
            vs.append((rgb_hex(a[key == k].mean(0)), round(float(cnt.max()) / len(a), 2)))
        out[city] = vs
    return out


def to_legacy_tint(hx, gain=NHL27_GAIN):
    return rgb_hex([min(255, c * gain) for c in hex_rgb(hx)])


# ================================================================ рецепты

def recipes_path():
    return os.path.join(HERE, 'arena_seats.toml')


def load_recipes(path=None):
    import tomllib
    path = path or recipes_path()
    with open(path, 'rb') as fh:
        data = tomllib.load(fh)
    out = {}
    for key, r in data.get('arena', {}).items():
        if not re.fullmatch(r'\d+', key):
            raise SystemExit(f'{path}: [arena.{key}] — ключ должен быть номером модели арены')
        for rule in r.get('rules', []):
            try:
                parse_rule(rule)
            except ValueError as e:
                raise SystemExit(f'{path}: [arena.{key}] {e}')
        if 'clone_of' in r and (not isinstance(r['clone_of'], int) or not isinstance(r.get('arenas', []), list)
                                or not all(isinstance(x, int) for x in r.get('arenas', []))):
            raise SystemExit(f'{path}: [arena.{key}] clone_of — номер модели игры, arenas — список exhibitionarena.index')
        out[int(key)] = r
    return out


# ================================================================ своя модель арены: копия под новым номером (24.10.2026)
#
# Как игра берёт модель арены (разбор образа default.bin и кода порта 24.10.2026, docs/arenas.md §9):
# exhibitionarena.arenaartid (10 бит, 0…1023) → структура арены матча +96 (int16) → sub_836110E8 (в режимах 15…17 —
# всегда 254). Списка допустимых номеров нет: пути собираются sprintf-ом из номера — stadium_%d_Container_0.rx2
# (sub_8369CF80), crowddata/crowd_%u.cwd (sub_836A0958), jumbotron/texlib_%d.rx2 (sub_8369B3B8), particle/stadium_%i.rvi
# (sub_8369BE98), enviro/helmet_%i.rx2 (sub_83611460), crowd/walker_%i_cm.rx2 (его нет и у 255 — игра обходится).
# Номер внутри файлов: растры экранов куба игра ищет по имени jumbotron_screen_<0|1>_%d_<0|1>_cm.Raster (sub_836B2940),
# .rvi называет эффекты FX_<N>_… (по имени — файл fx_<N>_….lnb, в нём то же имя), у helmet_<N> растр helmet_<N>.Raster.
# Поэтому копия переписывает номер в этих именах — той же длины (номер с тем же числом цифр), остальное — байт в байт.
ARENA_SPECIAL = {254: 'тренировка: в режимах 15…17 игра берёт 254 всегда (sub_836110E8)',
                 **{n: 'Швейцария: свои проверки номера (sub_836112E8)' for n in (321, 325, 326, 329, 331)},
                 514: 'своя проверка номера (sub_836111F0)',
                 **{n: 'Winter Classic: свои проверки номера (sub_83611130 и др.)' for n in range(700, 704)}}
# Записи AttribDB (boot attribdb/renddb.vlt) по ключам stadium_<N> и crowd_<N> — хеш Jenkins lookup8 (Attrib-ключ EA,
# sub_824A7D58; сверено: «default» → D7EDBD362D7D2152, его игра берёт, когда записи нет). Записи есть: stadium_ — у 28,
# 254, 700…703; crowd_ — у 0…29, 321/325/326/329/331, 514, 700…703. У 255 нет ни одной: копия 255 под номером без
# записей ведёт себя как 255.
ATTRIB_REL = 'attribdb/renddb.vlt'
ATTRIB_KEYS = ('stadium_{n}', 'crowd_{n}')
JUMBO_REL = 'rendering/jumbotron/texlib_{n}.rx2'
ENVIRO_REL = 'rendering/enviro/helmet_{n}.rx2'
RVI_REL = 'rendering/particle/stadium_{n}.rvi'
LNB_REL = 'rendering/particle/{name}.lnb'
MODEL_RELS = (STADIUM_REL, CROWD_REL, JUMBO_REL, ENVIRO_REL, RVI_REL)   # + .lnb эффектов, которые называет .rvi
DB_MAX_ART = 1023                                                       # exhibitionarena.arenaartid — 10 бит

_CLONES = None


def clones():
    """{номер своей модели: номер исходной} — рецепты arena_seats.toml с clone_of (любой status)."""
    global _CLONES
    if _CLONES is None:
        try:
            _CLONES = {k: int(r['clone_of']) for k, r in load_recipes().items() if 'clone_of' in r}
        except (OSError, SystemExit):
            _CLONES = {}
    return _CLONES


def clone_source(n):
    """Номер модели игры, копия которой — модель n (рецепт с clone_of), иначе сам n."""
    return clones().get(n, n)


def _lookup8(k, level=0xABCDEF0011223344):
    """Хеш Боба Дженкинса lookup8 (64 бит) — ключ Attrib EA (sub_824A86B0 → sub_824A7D58)."""
    M = (1 << 64) - 1

    def mix(a, b, c):
        for sa, sb, sc in ((43, 9, 8), (38, 23, 5), (35, 49, 11), (12, 18, 22)):
            a = (a - b - c) & M
            a ^= c >> sa
            b = (b - c - a) & M
            b ^= (a << sb) & M
            c = (c - a - b) & M
            c ^= b >> sc
        return a, b, c
    a = b = level
    c = 0x9E3779B97F4A7C13
    i = 0
    while len(k) - i >= 24:
        a = (a + int.from_bytes(k[i:i + 8], 'little')) & M
        b = (b + int.from_bytes(k[i + 8:i + 16], 'little')) & M
        c = (c + int.from_bytes(k[i + 16:i + 24], 'little')) & M
        a, b, c = mix(a, b, c)
        i += 24
    r = k[i:]
    c = (c + len(k)) & M
    c = (c + (int.from_bytes(r[16:], 'little') << 8)) & M        # байты 16…22 хвоста — в c со сдвигом на байт
    b = (b + int.from_bytes(r[8:16], 'little')) & M
    a = (a + int.from_bytes(r[:8], 'little')) & M
    return mix(a, b, c)[2]


def attrib_keys(n):
    """Ключи AttribDB модели n, у которых в renddb.vlt есть запись (['stadium_28', …]); [] — всё по умолчанию."""
    p = PROFILE.extracted(ATTRIB_REL)
    if not p:
        return []
    vlt = open(p, 'rb').read()
    out = []
    for t in ATTRIB_KEYS:
        h = _lookup8(t.format(n=n).encode())
        if h.to_bytes(8, 'big') in vlt or h.to_bytes(8, 'little') in vlt:
            out.append(t.format(n=n))
    return out


def rvi_effects(data):
    """Имена эффектов частиц в .rvi (XML: <particleEffect name="FX_255_glare_light_medium" …>)."""
    return [x.decode() for x in re.findall(rb'<particleEffect\s+name="([A-Za-z0-9_]+)"', data)]


def model_files(n, to=None):
    """Файлы модели арены n в раскладке cache: — [(путь у n, путь у копии to)]: 5 по номеру и .lnb эффектов FX_<n>_…
    из её .rvi (эффекты с другими именами копия берёт у игры как есть)."""
    to = n if to is None else to
    pairs = [(t.format(n=n), t.format(n=to)) for t in MODEL_RELS]
    p = PROFILE.extracted(RVI_REL.format(n=n))
    if p:
        for name in rvi_effects(open(p, 'rb').read()):
            nm = name.lower()
            if nm.startswith(f'fx_{n}_'):
                pairs.append((LNB_REL.format(name=nm), LNB_REL.format(name=f'fx_{to}_' + nm[len(f'fx_{n}_'):])))
    return pairs


def _name_spans_rw4(data):
    """Строки таблиц имён (0x00EC0010) контейнера RW4: [(начало, конец)]."""
    import rw4mesh as rm
    f = rm.Rw4File(data)
    spans = []
    for s in f.find(T_NAMES):
        o = f.abs_off(s)
        k = struct.unpack_from('>H', f.raw, o + 2)[0]         # +2 — число имён (у арен +0 — флаг 1, у текстур — 0)
        for j in range(k):
            ptr = struct.unpack_from('>I', f.raw, o + 8 + 12 * j)[0]
            spans.append((ptr, f.raw.index(b'\0', ptr)))
    return spans


def renumber(data, src, dst, rel):
    """Номер src → dst в именах внутри файла модели арены (растры, эффекты): → (байты, число замен).
    Только в именах: у .rx2 — строки таблицы имён, у .rvi/.lnb — FX_<N>_; длина номера та же (иначе SystemExit)."""
    if rel.endswith('.rx2'):
        spans, pat = _name_spans_rw4(data), re.compile(rb'(?<=_)%d(?=[_.])' % src)
    else:
        spans, pat = [(0, len(data))], re.compile(rb'(?<=FX_)%d(?=_)' % src)
    out = bytearray(data)
    k = 0
    for a, b in spans:
        for m in pat.finditer(data, a, b):
            if len(str(dst)) != len(str(src)):
                raise SystemExit(f'{rel}: номер {src} есть в именах внутри файла — у копии нужен номер из '
                                 f'{len(str(src))} цифр (имена переписываются той же длины), а не {dst}')
            out[m.start():m.end()] = b'%d' % dst
            k += 1
    return bytes(out), k


def check_clone_number(src, dst):
    """Ошибки номера своей модели (пустой список — номер годится)."""
    bad = []
    if not 0 <= dst <= DB_MAX_ART:
        bad.append(f'{dst}: arenaartid — 10 бит, 0…{DB_MAX_ART}')
    if dst == src:
        bad.append(f'{dst}: совпадает с исходной моделью')
    if dst in ARENA_SPECIAL:
        bad.append(f'{dst}: особый номер — {ARENA_SPECIAL[dst]}')
    if dst < 30:
        bad.append(f'{dst}: 0…29 — арены клубов НХЛ (свои icesurface_<N>_bm, кольца, записи crowd_<N>)')
    taken = [r for r in MODEL_RELS if PROFILE.extracted(r.format(n=dst))]
    if taken:
        bad.append(f'{dst}: у игры уже есть {", ".join(r.format(n=dst) for r in taken)}')
    keys = attrib_keys(dst)
    if keys:
        bad.append(f'{dst}: в AttribDB есть записи {keys} — копия возьмёт чужие настройки')
    return bad


def clone_files(src, dst):
    """Своя модель dst — копия модели игры src: [(путь cache:, байты, число замен номера в именах)]."""
    if clone_source(src) != src:
        raise SystemExit(f'{src}: это своя модель (clone_of {clone_source(src)}) — копировать модель игры')
    bad = check_clone_number(src, dst)
    if bad:
        raise SystemExit('номер не годится:\n  ' + '\n  '.join(bad))
    keys = attrib_keys(src)
    if keys:
        raise SystemExit(f'{src}: у модели есть записи AttribDB {keys} — у копии их не будет (не проверялось)')
    out = []
    for rel, rel_dst in model_files(src, dst):
        if not PROFILE.extracted(rel):
            continue                           # jumbotron/texlib_<N> есть не у всех моделей
        data = game_file(rel)
        new, k = renumber(data, src, dst, rel)
        if len(new) != len(data):
            raise SystemExit(f'{rel}: размер изменился')
        if rel.endswith('.lnb') and k < 1:
            raise SystemExit(f'{rel}: имени FX_{src}_… внутри нет — разбор .lnb не тот')
        out.append((rel_dst, new, k))
    have = {r for r, _, _ in out}
    for rel, data, k in out:
        if rel.endswith('.rvi'):                # эффект копии FX_<dst>_… — свой .lnb, остальные — у игры
            for nm in (x.lower() for x in rvi_effects(data)):
                q = LNB_REL.format(name=nm)
                if q not in have and not PROFILE.extracted(q):
                    raise SystemExit(f'{rel}: эффект {nm} — нет ни копии, ни файла игры {q}')
    return out


def write_clone(src, dst, outdir):
    """Файлы своей модели в outdir (раскладка cache:) → [(путь, записан ли заново)]; crowd — как у src (цвет — рецептом)."""
    res = []
    for rel, data, k in clone_files(src, dst):
        p = os.path.join(outdir, *rel.split('/'))
        same = os.path.isfile(p) and open(p, 'rb').read() == data
        if not same:
            os.makedirs(os.path.dirname(p), exist_ok=True)
            open(p + '.part', 'wb').write(data)
            os.replace(p + '.part', p)
        res.append((rel, not same, k))
    return res


# ================================================================ команды

def cmd_map(a):
    m, dbp = arena_map(a.db)
    print(f'база: {dbp}')
    print('модель\tклубы (строка: аббр.)\tарены (строка: название, мест)\tкресел\tцвета кресел (число)')
    for art in sorted(m):
        d = m[art]
        clubs = ', '.join(f'{r}:{ab}' for r, ab, _, _ in d['clubs'][:6]) + (' …' if len(d['clubs']) > 6 else '')
        arenas = '; '.join(f'{r}: {nm}, {mx}' for r, nm, _, mx in d['arenas'][:3]) + \
                 (f' (+{len(d["arenas"]) - 3})' if len(d['arenas']) > 3 else '')
        try:
            cr = Crowd.load(art)
            cols = ', '.join(f'{h} ({c})' for h, c, _ in cr.color_groups()[:4])
            seats = cr.n
        except SystemExit:
            cols, seats = 'нет crowd_%d.cwd' % art, '-'
        print(f'{art}\t{clubs or "-"}\t{arenas}\t{seats}\t{cols}')


def cmd_info(a):
    st = Stadium.load(a.target)
    f = st.f
    print(f'{st.path}: секций {len(f.sections)}, данные с 0x{f.data_start:X}, {f.data_size} байт')
    cnt = collections.Counter(s.type for s in f.sections)
    for t, n in sorted(cnt.items()):
        print(f'  0x{t:08X} ×{n:<5} {TYPE_NAMES.get(t, "")}')
    users = st.raster_users()
    print(f'\nрастры ({len(st.rasters)}):')
    for r, fe in st.rasters.items():
        u = ', '.join(sorted({f'{m}' for m, _ in users.get(r, [])}))[:110]
        print(f'  {r:5d} {fe.width}×{fe.height} fmt {fe.fmt:#x}  ← {u}')
    print(f'\nматериалы ({len(st.materials)}):')
    for m in st.materials.values():
        tex = ', '.join(f'{k}={v}' for k, v in m.textures.items())
        print(f'  {m.sec:5d} {m.name:58s} {m.effect:28s} {m.technique:22s} {tex}')
    print(f'\nслои и объекты ({len(st.layers)} слоёв, {len(st.objects)} объектов):')
    for L, d in sorted(st.layers.items(), key=lambda kv: kv[1]['name']):
        for o in d['objects']:
            obj = st.objects[o]
            nv = sum(st.parts[p].nv for p, _ in obj['batches'] if p in st.parts)
            mats = sorted({st.materials[m].name for _, m in obj['batches'] if m in st.materials})
            print(f'  {d["name"]:28s} {obj["name"]:40s} частей {len(obj["batches"]):3d}, вершин {nv:6d}: '
                  f'{", ".join(mats)[:120]}')


def cmd_textures(a):
    from PIL import Image, ImageDraw
    st = Stadium.load(a.target)
    tag = re.sub(r'\W+', '_', os.path.basename(st.path).replace('_container_0.rx2', ''))
    out = a.out or work('textures', tag)
    os.makedirs(out, exist_ok=True)
    users = st.raster_users()
    files = []
    for r in st.rasters:
        w, h, rgba = st.texture(r)
        mats = sorted({re.sub(r'_Clone_\d+$', '', m) for m, _ in users.get(r, [])})
        name = f'r{r:04d}_{w}x{h}_' + re.sub(r'[^\w-]+', '_', '+'.join(mats) or 'unused')[:80] + '.png'
        p = os.path.join(out, name)
        Image.fromarray(rgba, 'RGBA').save(p)
        files.append(p)
    T, cols = 192, 8
    rows = (len(files) + cols - 1) // cols
    sheet = Image.new('RGB', (cols * T, rows * (T + 16)), (40, 40, 40))
    dr = ImageDraw.Draw(sheet)
    for i, p in enumerate(files):
        t = Image.open(p).convert('RGBA')
        t.thumbnail((T, T))
        bg = Image.new('RGBA', t.size, (255, 0, 255, 255))
        bg.alpha_composite(t)
        x, y = (i % cols) * T, (i // cols) * (T + 16)
        sheet.paste(bg.convert('RGB'), (x, y))
        dr.text((x + 2, y + T + 1), os.path.basename(p)[:30], fill=(255, 255, 255))
    sp = os.path.join(out, '_sheet.png')
    sheet.save(sp)
    print(f'{len(files)} текстур → {out}\nлист: {sp} (пурпурный — прозрачное)')


def cmd_crowd(a):
    cr = Crowd.load(a.target)
    S = cr.seats
    tiers = cr.seat_tiers()
    print(f'{cr.path}: кресел {cr.n}, рядов {len(cr.rows)}, ярусов {len(cr.tier_ends)}; высота '
          f'{S["pos"][:, 1].min():.1f}…{S["pos"][:, 1].max():.1f} м, X ±{np.abs(S["pos"][:, 0]).max():.1f}, '
          f'Z ±{np.abs(S["pos"][:, 2]).max():.1f}')
    print('уровни чаши (разрыв по высоте > 1,2 м): ' +
          '; '.join(f'{a:.1f}…{b:.1f} м — {k}' for a, b, k in cr.bowls()))
    print('цвета кресел:')
    for hx, c, m in cr.color_groups():
        y = S['pos'][m, 1]
        t = tiers[m]
        print(f'  {hx}  {c:6d} ({100 * c / cr.n:4.1f} %)  высота {y.min():5.1f}…{y.max():5.1f} м, ярусы {t.min()}…{t.max()}')
    if a.tiers:
        print('ярусы: номер, кресел, высота, цвета')
        for k in range(len(cr.tier_ends)):
            m = tiers == k
            if not m.any():
                continue
            cols = collections.Counter(rgb_hex(c) for c in cr.colors255()[m])
            print(f'  {k:3d} {m.sum():5d}  {S["pos"][m, 1].min():5.1f}…{S["pos"][m, 1].max():5.1f} м  '
                  + ', '.join(f'{h} ×{n}' for h, n in cols.most_common(3)))
    if a.map:
        p = a.map if a.map.endswith('.png') else os.path.join(work('preview'), f'seats_{os.path.basename(cr.path)}.png')
        os.makedirs(os.path.dirname(p), exist_ok=True)
        color_map(cr, title=os.path.basename(cr.path)).save(p)
        print(f'план кресел: {p}')


def parse_size(s):
    m = re.fullmatch(r'(\d+)x(\d+)', s)
    if not m:
        raise SystemExit(f'--size {s}: нужно ШxВ')
    return int(m.group(1)), int(m.group(2))


def cmd_render(a):
    n = int(a.target)
    crowd = Crowd(open(a.cwd, 'rb').read(), a.cwd) if a.cwd else None
    views = list(VIEWS) if a.view == 'all' else a.view.split(',')
    for v in views:
        if v not in VIEWS:
            raise SystemExit(f'--view {v}: есть {", ".join(VIEWS)}, all')
    ims = render(n, crowd, views, parse_size(a.size), label=a.label or f'stadium_{n}')
    out = a.out or os.path.join(work('preview'), f'stadium_{n}.png')
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    for v, im in ims.items():
        p = out if len(ims) == 1 else re.sub(r'\.png$', f'_{v}.png', out)
        im.save(p)
        print(p)


def write_out(n, crowd, outdir):
    p = os.path.join(outdir, *CROWD_REL.format(n=n).split('/'))
    os.makedirs(os.path.dirname(p), exist_ok=True)
    data = crowd.bytes()
    orig = game_file(CROWD_REL.format(n=clone_source(n)))      # у своей модели — crowd её исходной модели
    if len(data) != len(orig):
        raise SystemExit('размер .cwd изменился — так быть не должно')
    diff = np.frombuffer(data, np.uint8) != np.frombuffer(orig, np.uint8)
    lo, hi = crowd.seat_off, crowd.tier_off
    idx = np.nonzero(diff)[0]
    rel = (idx - lo) % SEAT.itemsize if len(idx) else idx
    if len(idx) and ((idx < lo).any() or (idx >= hi).any() or (rel < 16).any() or (rel >= 28).any()):
        raise SystemExit('изменилось что-то кроме цвета кресел — файл не записан')
    open(p, 'wb').write(data)
    return p, int(diff.sum())


def do_recolor(n, rules, outdir, preview, title=''):
    try:
        for r in rules:
            parse_rule(r)
    except ValueError as e:
        raise SystemExit(str(e))
    cr = Crowd.load(n)
    report = apply_rules(cr, rules)
    for r, k in report:
        print(f'  {r:40s} кресел: {k}')
        if not k:
            print('    ! ни одного кресла — проверьте фильтр (python stadium.py crowd N)')
    p, nb = write_out(n, cr, outdir)
    print(f'  → {p} (изменено байт: {nb}; всё, кроме цвета кресел, — как у EA)')
    if preview:
        for q in before_after(n, cr, preview, title or f'stadium_{n}'):
            print(f'  картинка: {q}')
    return cr


def cmd_recolor(a):
    n = int(a.target)
    if not a.rules:
        raise SystemExit('нужно хотя бы одно правило, например "#484948" или "y=11-40:#353535"')
    do_recolor(n, a.rules, a.out or work('out'), None if a.no_preview else (a.preview or work('preview')))


def cmd_recipe(a):
    rec = load_recipes(a.recipes)
    if not a.arenas or a.arenas == ['all']:
        keys = sorted(rec)
    else:
        keys = [int(x) for x in a.arenas]
        bad = [k for k in keys if k not in rec]
        if bad:
            raise SystemExit(f'нет рецептов для {bad} в {a.recipes or recipes_path()}')
    done = 0
    for k in keys:
        r = rec[k]
        if a.approved and r.get('status') != 'approved':
            continue
        if not r.get('rules'):
            print(f'[{k}] {r.get("club", "")} — без правил ({r.get("status", "")}): {r.get("note", "")}')
            continue
        print(f'[{k}] {r.get("club", "")} {r.get("building", "")} ({r.get("status", "?")})')
        do_recolor(k, r['rules'], a.out or work('out'), None if a.no_preview else (a.preview or work('preview')),
                   f'{r.get("club", "")} {r.get("building", "")}'.strip())
        done += 1
    print(f'готово арен: {done}')


def cmd_clone(a):
    src = int(a.source)
    try:
        targets = [int(x) for x in re.split(r'[,\s]+', a.to.strip()) if x]
    except ValueError:
        raise SystemExit(f'--to {a.to!r}: номера через запятую, например 222,230,231')
    outdir = a.out or work('out')
    bad = 0
    for dst in targets:
        if a.check:
            b = check_clone_number(src, dst)
            print(f'{dst}: ' + ('годится' if not b else '; '.join(b)))
            bad += bool(b)
            continue
        print(f'[{dst}] копия модели {src} → {outdir}')
        for rel, new, k in write_clone(src, dst, outdir):
            print(f'  {rel}  (номер в именах: {k}){"" if new else " — уже такой"}')
    if not a.check:
        print('кресла копии — как у исходной; цвет — рецептом [arena.N] с clone_of (recipe N), база — '
              'tools/legacy_data/arenas.py (docs/arenas.md §9)')
    return 1 if bad else 0


def pack(man, cache):
    """Кресла одобренных рецептов (status = approved) в пакет (fb.edge_kit pack): crowd_<N>.cwd — копия EA с новым цветом
    кресел, запись type crowd в манифесте; у своей модели (clone_of) — копия crowd исходной. -> число арен.
    Сами файлы своих моделей и arenaartid в базе ставит этап legacy-data arenas (tools/legacy_data/arenas.py)."""
    import hashlib
    rec = load_recipes()
    n = 0
    for k in sorted(rec):
        r = rec[k]
        if r.get('status') != 'approved' or not r.get('rules'):
            continue
        cr = Crowd.load(k)
        apply_rules(cr, r['rules'])
        rel = CROWD_REL.format(n=k)
        p, _ = write_out(k, cr, cache)
        q = os.path.join(cache, *rel.split('/'))
        if os.path.abspath(p) != os.path.abspath(q):
            raise SystemExit(f'{p}: ожидался {q}')
        e = {'file': rel, 'type': 'crowd', 'md5': hashlib.md5(open(q, 'rb').read()).hexdigest(),
             'size': os.path.getsize(q), 'action': 'replace',
             'note': f'кресла {r.get("club", "")} {r.get("building", "")}: {", ".join(r["rules"])} (stadium.py, arena_seats.toml)'}
        man['files'] = [x for x in man['files'] if x['file'] != rel] + [e]
        n += 1
    return n


NHL_MODELS = [n for n in range(30) if n != 22] + [255]     # 22 — арена «Финикса» (у Legacy её никто не берёт)


def cmd_sheet(a):
    """Лист картинок: арены как у EA или «было | стало» по рецептам."""
    from PIL import Image
    rec = load_recipes(a.recipes) if a.after else {}
    if a.arenas:
        nums = [int(x) for x in a.arenas]
    elif a.after:
        nums = [k for k in sorted(rec) if rec[k].get('rules') and (not a.approved or rec[k].get('status') == 'approved')]
    else:
        nums = NHL_MODELS
    try:
        amap, _ = arena_map(a.db)
    except Exception as e:                                  # noqa: BLE001 — без базы подписи короче
        print(f'база не прочитана ({e}) — подписи без клубов')
        amap = {}
    cw, ch = parse_size(a.size)
    cells = []
    for n in nums:
        st = Stadium.load(n)
        old = Crowd.load(n)
        clubs = '/'.join(ab for r, ab, _, lg in amap.get(n, {}).get('clubs', []) if lg == 0) or             '/'.join(ab for r, ab, _, _ in amap.get(n, {}).get('clubs', [])[:2])
        r = rec.get(n, {})
        name = r.get('building') or (amap.get(n, {}).get('arenas') or [(0, f'stadium_{n}')])[0][1]
        title = f'{n} {clubs} — {name}'
        im = render(n, old, (a.view,), (cw, ch), stadium=st)[a.view]
        caption(im, title)
        swatches(im, [(h, str(c)) for h, c, _ in old.color_groups()[:3]], (12, ch - 30 * min(3, len(old.color_groups())) - 6))
        cells.append(im)
        if a.after:
            new = Crowd.load(n)
            apply_rules(new, r.get('rules', []))
            im = render(n, new, (a.view,), (cw, ch), stadium=st)[a.view]
            caption(im, f'{n} {clubs} — стало ({r.get("status", "?")})')
            swatches(im, [(h, str(c)) for h, c, _ in new.color_groups()[:3]],
                     (12, ch - 30 * min(3, len(new.color_groups())) - 6))
            cells.append(im)
        print(f'  {title}')
    cols = a.cols or (4 if a.after else 5)
    rows = (len(cells) + cols - 1) // cols
    sheet = Image.new('RGB', (cols * (cw + 6) - 6, rows * (ch + 6) - 6), (255, 255, 255))
    for i, im in enumerate(cells):
        sheet.paste(im, ((i % cols) * (cw + 6), (i // cols) * (ch + 6)))
    out = a.out or os.path.join(work('preview'), 'sheet_after.png' if a.after else 'sheet_ea.png')
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    sheet.save(out)
    print(out)


def cmd_nhl27(a):
    res = nhl27_chairs(a.dir)
    print('город\tклуб\tмодель Legacy\tвариант 0…3 (цвет NHL 27, доля текстуры)\t→ оттенок Legacy (×%.2f)' % NHL27_GAIN)
    for city, vs in res.items():
        club, art = NHL27_CITY.get(city, ('', None))
        cols = ' | '.join(f'{v[0]} {int(v[1] * 100)}%' if v else '-' for v in vs)
        tint = ', '.join(sorted({to_legacy_tint(v[0]) for v in vs if v}))
        print(f'{city}\t{club}\t{"" if art is None else art}\t{cols}\t{tint}')
    if a.json:
        os.makedirs(os.path.dirname(os.path.abspath(a.json)), exist_ok=True)
        json.dump(res, open(a.json, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        print(a.json)


def cmd_check(a):
    targets = a.targets
    if not targets:
        base = PROFILE.extracted('rendering/stadium/stadium_0_container_0.rx2')
        if not base:
            raise SystemExit('нет распакованных моделей арен (rendering/stadium/)')
        nums = sorted(int(re.search(r'stadium_(\d+)_', p).group(1))
                      for p in glob.glob(os.path.join(os.path.dirname(base), 'stadium_*_container_0.rx2')))
        cdir = os.path.dirname(PROFILE.extracted(CROWD_REL.format(n=0)) or '')
        cnums = sorted(int(re.search(r'crowd_(\d+)\.cwd', p).group(1)) for p in glob.glob(os.path.join(cdir, 'crowd_*.cwd')))
    else:
        nums = cnums = [int(t) for t in targets]
    bad = 0
    for n in nums:
        try:
            st = Stadium.load(n)
            tris = sum(len(st.geometry(p)[4]) for p in st.parts)
            print(f'stadium_{n}: объектов {len(st.objects)}, слоёв {len(st.layers)}, материалов {len(st.materials)}, '
                  f'растров {len(st.rasters)}, частей {len(st.parts)}, треугольников {tris}')
        except (ValueError, KeyError, IndexError, struct.error) as e:
            bad += 1
            print(f'stadium_{n}: ОШИБКА {e}')
    for n in cnums:
        try:
            data = game_file(CROWD_REL.format(n=clone_source(n)))   # своя модель — crowd исходной
            cr = Crowd(data, f'crowd_{n}.cwd')
            same = cr.bytes() == data
            print(f'crowd_{n}: кресел {cr.n}, цветов {len(cr.color_groups())}, сборка байт в байт: {"да" if same else "НЕТ"}')
            bad += not same
        except (ValueError, SystemExit) as e:
            bad += 1
            print(f'crowd_{n}: ОШИБКА {e}')
    print('ошибок нет' if not bad else f'ошибок: {bad}')
    return 1 if bad else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0], formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog='Подробно — docs/arenas.md')
    ap.add_argument('--game', choices=gameprofile.GAMES, default=os.environ.get('NHL_GAME', 'legacy'),
                    help='игра (по умолчанию legacy)')
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('map', help='модель арены ↔ клуб')
    p.add_argument('--db')
    p.set_defaults(fn=cmd_map)
    p = sub.add_parser('info', help='разбор модели арены')
    p.add_argument('target')
    p.set_defaults(fn=cmd_info)
    p = sub.add_parser('textures', help='текстуры модели → PNG')
    p.add_argument('target')
    p.add_argument('--out')
    p.set_defaults(fn=cmd_textures)
    p = sub.add_parser('crowd', help='кресла и их цвета')
    p.add_argument('target')
    p.add_argument('--tiers', action='store_true', help='по ярусам')
    p.add_argument('--map', nargs='?', const='auto', help='план кресел сверху (PNG)')
    p.set_defaults(fn=cmd_crowd)
    p = sub.add_parser('render', help='картинка арены с креслами')
    p.add_argument('target')
    p.add_argument('--cwd', help='свой crowd .cwd (например, перекрашенный)')
    p.add_argument('--view', default='broadcast', help='broadcast, overview, end, top, all или через запятую')
    p.add_argument('--size', default='1600x900')
    p.add_argument('--out')
    p.add_argument('--label')
    p.set_defaults(fn=cmd_render)
    p = sub.add_parser('recolor', help='перекрасить кресла арены (копия .cwd)')
    p.add_argument('target')
    p.add_argument('rules', nargs='*')
    p.add_argument('--out')
    p.add_argument('--preview')
    p.add_argument('--no-preview', action='store_true')
    p.set_defaults(fn=cmd_recolor)
    p = sub.add_parser('recipe', help='перекраска по рецептам arena_seats.toml')
    p.add_argument('arenas', nargs='*')
    p.add_argument('--recipes')
    p.add_argument('--out')
    p.add_argument('--preview')
    p.add_argument('--no-preview', action='store_true')
    p.add_argument('--approved', action='store_true', help='только одобренные пользователем')
    p.set_defaults(fn=cmd_recipe)
    p = sub.add_parser('sheet', help='лист картинок арен (как у EA или «было | стало» по рецептам)')
    p.add_argument('arenas', nargs='*')
    p.add_argument('--after', action='store_true', help='пары «было | стало» по рецептам')
    p.add_argument('--approved', action='store_true')
    p.add_argument('--recipes')
    p.add_argument('--view', default='overview', choices=[v for v in VIEWS])
    p.add_argument('--size', default='560x315')
    p.add_argument('--cols', type=int)
    p.add_argument('--db')
    p.add_argument('--out')
    p.set_defaults(fn=cmd_sheet)
    p = sub.add_parser('nhl27', help='цвет кресел NHL 27 (справка)')
    p.add_argument('--dir')
    p.add_argument('--json')
    p.set_defaults(fn=cmd_nhl27)
    p = sub.add_parser('clone', help='своя модель арены: копия модели игры под новым номером')
    p.add_argument('source', help='номер модели игры (например 255)')
    p.add_argument('--to', required=True, help='номера копий через запятую (например 222,230,231)')
    p.add_argument('--out', help='куда (раскладка cache:), по умолчанию game/work/legacy-data/arenas/out')
    p.add_argument('--check', action='store_true', help='только проверить номера')
    p.set_defaults(fn=cmd_clone)
    p = sub.add_parser('check', help='разбор всех файлов, сборка .cwd байт в байт')
    p.add_argument('targets', nargs='*')
    p.set_defaults(fn=cmd_check)
    a = ap.parse_args()
    use_game(a.game)
    sys.exit(a.fn(a) or 0)


if __name__ == '__main__':
    main()
