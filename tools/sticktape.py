"""Обмотка клюшки NHL 13: лента до самого носка крюка (без незамотанной «пимпочки») и, по выбору, носок круглее.

    python sticktape.py info                          # разбор: кольца ленты, носок клюшки, стык (полевые и вратарские)
    python sticktape.py build [--round none,strong,bottom1,bottom2] [--kinds player,goalie] [--goalie-round]
                              [--preview DIR] [--no-preview]
                                                      # варианты (ROUNDS) в game/work/models/tape/out (none — без
                                                      # скругления) и out-<вариант>, раскладка cache:; лист превью.
                                                      # --kinds goalie пересобирает только вратарские (записи
                                                      # остальных в manifest.json сохраняются)
    python sticktape.py preview [--round …] [--preview DIR]   # лист превью по готовым файлам
    python sticktape.py check [--round …]             # проверки собранного

У всех команд — опция --game {nhl13,legacy} (или NHL_GAME, tools/gameprofile.py): из архивов какой игры брать сетки и
куда писать по умолчанию (NHL 13 — game/work/models/tape, Legacy — game/work/legacy-data/models/tape). У NHL Legacy
есть ещё реквизит (без костей, rendering/prop/): вратарская клюшка goaliestick_{left,right}_0 и лента
goaliesticktape_{left,right}_0 — та же сетка, что goaliestick_H_2 (вид goalieprop, правится как вратарские), и
клюшка на льду droppedstick_0 — один файл из 6 подсеток: у каждой из двух клюшек (left — зеркало right по y) древко с
крюком stick_<side>_shaft_, лента крюка stick_<side>_heel_tape_ (та же, что у playersticktape_H_2) и набалдашник
stick_<side>_shaft_tape_ (вид dropped, правится как полевые: подсетки — rw4mesh.Mesh(sub=k)). Лист превью у Legacy —
«Legacy, оригинал / Legacy с модом / NHL 13 с модом» (готовые файлы NHL 13 из game/work/models/tape).

Устройство (разбор 08.10.2026, подробно — docs/player-models.md §9). Геометрия клюшки у всех игроков одна:
rendering/playerstick/playerstick_H_V.rx2 (H — 0/1, зеркальные левый и правый хват; V — 2 и 4: _4 — та же сетка,
растянутая вдвое по y и z мира, то есть вдвое толще и длиннее по крюку; путь для отрисовки игра собирает только с _2,
_4 есть лишь в общей таблице предзагрузки), свой скелет из 4 костей вдоль древка (секция 0x00070003). «Модели» клюшек
(Bauer, Easton, Reebok, дерево…) — только текстура texlib_<id>.rx2 (playerstick_<id>_cm, 1024×128). Лента —
отдельная сетка playersticktape_H_V.rx2 из двух кусков: набалдашник на конце древка и средняя часть крюка — **сама
поверхность крюка**, не слой поверх: у клюшки там сетки нет, кольца ленты совпадают с кольцами клюшки на стыках у
пятки и у носка. Носок крюка (≈2,4 см) — отдельный островок сетки клюшки с её текстурой: при белой ленте он чёрный.
Цвет ленты — текстура sticktape_<цвет>_cm (128×64, 10 цветов) из texlib_999.rx2: UV-u — вдоль крюка (0,018…0,661),
правее 0,696 — рисунок набалдашника; UV-v — по кругу сечения. Вратарские (rendering/goaliestick/goaliestick_H_V,
goaliesticktape_H_V) устроены так же: в кольце 15 вершин вместо 9, у островка носка другое устройство (без рельсов).

Правка (build_pair): рамка носка — по кромкам крюка (n — к кончику, c — вверх, w — по толщине); кольца ленты после
«якорного» кольца тела заменяются новыми до самого кончика. До стыка точки ролей — на исходной поверхности (на рёбрах
между кольцами тела), дальше — на «рельсах» носка (ряды контура и края фаски) или, у вратарских, протяжкой сечения
стыка. При скруглении контур — две четверти эллипса, касательные к кромкам (радиусы ROUNDS — доли высоты крюка у
носка; если вместе они больше высоты, высота делится между углами пропорционально), с плавным сопряжением с исходным
контуром; дальше стыка — протяжка сечения стыка, вписанного в новый контур (толщина и середина — гладко по исходному
носку). Нормали — авторские нормали якорного кольца, повёрнутые за поверхностью и сглаженные вдоль крюка. Позиции —
half-float: каждая новая вершина ставится в соседний представимый узел на своём ряду (шаг x у носка ~1 мм; простое
округление дало бы «пилу» по контуру); перевёрнутые после этого треугольники (у самого кончика вратарских) чинятся
выбором другого узла. Торец закрыт; рисунок ленты продолжается (UV-u крюка чуть сжимается, чтобы не залезть в
набалдашник); островок носка клюшки стянут в точку (треугольники вырождаются — не рисуются). Пятка и древко не
меняются, кости и веса — как у кольца на стыке. _4 считается в пространстве _2 (y, z пополам) — скругление то же,
растянутое вместе с клюшкой. Сетка ленты получает новые вершины и индексы — пересборка rw4mesh.Mesh.rebuilt.

Только стандартная библиотека (+ Chrome/Edge без окна — подписи листа превью).
"""
import json, math, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rw4mesh as rm  # noqa: E402

STICK = 'rendering/playerstick/playerstick_{h}_{v}.rx2'
TAPE = 'rendering/playerstick/playersticktape_{h}_{v}.rx2'
GSTICK = 'rendering/goaliestick/goaliestick_{h}_{v}.rx2'
GTAPE = 'rendering/goaliestick/goaliesticktape_{h}_{v}.rx2'
GPSTICK = 'rendering/prop/goaliestick_{side}_0.rx2'        # NHL Legacy: реквизит (без костей), H = 0 left, 1 right
GPTAPE = 'rendering/prop/goaliesticktape_{side}_0.rx2'
KINDS = {'player': (STICK, TAPE), 'goalie': (GSTICK, GTAPE), 'goalieprop': (GPSTICK, GPTAPE)}
KIND_DIR = {'player': 'playerstick', 'goalie': 'goaliestick', 'goalieprop': 'prop'}
SIDES = ('left', 'right')
PAIRS = [(k, h, v) for k in ('player', 'goalie') for v in (2, 4) for h in (0, 1)]
PROP_PAIRS = [('goalieprop', h, 0) for h in (0, 1)]
DROPPED = 'rendering/prop/droppedstick_0.rx2'               # NHL Legacy: две клюшки на льду, по 3 подсетки
KINDS['dropped'] = (DROPPED, DROPPED)
KIND_DIR['dropped'] = 'prop'
UV_GAP = 0.012                              # отступ рисунка крюка от рисунка набалдашника по UV-u


def v_add(a, b):
    return [a[0] + b[0], a[1] + b[1], a[2] + b[2]]


def v_mul(a, k):
    return [a[0] * k, a[1] * k, a[2] * k]


def lerp(a, b, t):
    return [a[k] + (b[k] - a[k]) * t for k in range(3)]


def pairs():
    """Пары клюшка + лента игры: у NHL 13 — PAIRS, у другой игры — ещё реквизит, если он есть в её архивах."""
    if rm.is_nhl13():
        return PAIRS
    return PAIRS + [p for p in PROP_PAIRS if all(rm.game_has(rel) for rel in pair_rels(*p))]


def has_dropped():
    return not rm.is_nhl13() and rm.game_has(DROPPED)


def kinds_default():
    ks = list(dict.fromkeys(k for k, _, _ in pairs()))
    return ','.join(ks + (['dropped'] if has_dropped() else []))


def dropped_subs(data):
    """Подсетки droppedstick_0 по именам шейдеров stick_<side>_<part>_ → {side: {part: k}}; part — shaft (древко с
    крюком и островком носка), heel_tape (лента крюка), shaft_tape (набалдашник)."""
    import re
    f = rm.Rw4File(data, DROPPED)
    out = {}
    for k, sh in enumerate(f.find(rm.TYPE_SHADER)):
        b = f.body(sh)
        mm = re.match(r'stick_(left|right)_(shaft|heel_tape|shaft_tape)_$', b[12:b.index(b'\0', 12)].decode('latin1'))
        if mm:
            out.setdefault(mm.group(1), {})[mm.group(2)] = k
    if any(set(out.get(sd, {})) != {'shaft', 'heel_tape', 'shaft_tape'} for sd in SIDES):
        raise SystemExit(f'{DROPPED}: подсетки {out} — разбор не подходит')
    return out


def dropped_pair(data, side):
    """Пара «древко + лента крюка» одной клюшки droppedstick_0 (side — left/right); UV-u набалдашника — из его
    подсетки (у клюшки в руке он в той же сетке, что лента)."""
    subs = dropped_subs(data)[side]
    st = rm.Mesh(data, DROPPED, sub=subs['shaft'])
    tp = rm.Mesh(data, DROPPED, sub=subs['heel_tape'])
    kn = rm.Mesh(data, DROPPED, sub=subs['shaft_tape'])
    pair = Pair(SIDES.index(side), 0, stick=st, tape=tp, kind='dropped')
    pair.uv_max = min(u for u, _ in kn.uv) - UV_GAP
    pair.subs, pair.side = subs, side
    return pair


def build_dropped(rounding, log=print):
    """droppedstick_0: обе клюшки — как полевые (build_pair); лента — новая подсетка, островок носка древка стянут.
    → (файл, {side: отчёт})."""
    data = rm.source(DROPPED)
    reps = {}
    for side in SIDES:
        pair = dropped_pair(data, side)
        tb, sb, rp = build_pair(pair, rounding)
        squeezed = rm.Mesh(sb, DROPPED, sub=pair.subs['shaft'])
        m = rm.Mesh(tb, DROPPED, sub=pair.subs['shaft'])        # файл с новой лентой — в нём же стянуть носок
        for i in pair.island:
            m.set_pos(i, squeezed.pos[i])
        data = m.bytes()
        reps[side] = rp
        log(f'  {DROPPED} [{side}]: лента {rp["tape_vertices"][0]} → {rp["tape_vertices"][1]} вершин, новых колец '
            f'{len(rp["new_rings_mm"])} (от кольца {rp["anchor_ring"]}), радиусы {rp["radii_mm"]} мм при высоте '
            f'{rp["blade_height_mm"]}; UV-u ×{rp["uv_u_scale"]}; стянуто {rp["stick_island_vertices"]} вершин носка')
    return data, reps


def check_dropped(out, log=print):
    """Проверка собранного droppedstick_0: у каждой клюшки — как у пары (check_pair), набалдашники — байт в байт как
    были и перекодируются байт в байт."""
    src = rm.source(DROPPED)
    new = open(os.path.join(out, *DROPPED.split('/')), 'rb').read()
    man = json.load(open(os.path.join(out, 'manifest.json'), encoding='utf-8'))['files'].get(DROPPED, {})
    ok = True
    for side in SIDES:
        pair = dropped_pair(src, side)
        nt = rm.Mesh(new, DROPPED, sub=pair.subs['heel_tape'])
        ns = rm.Mesh(new, DROPPED, sub=pair.subs['shaft'])
        anchor = man.get(side, {}).get('anchor_ring', len(pair.rings) - 2)
        good, line = check_pair(pair, nt, ns, anchor, f'{DROPPED} [{side}, лента]', f'[{side}, древко]')
        kb = pair.subs['shaft_tape']
        k0, k1 = rm.Mesh(src, DROPPED, sub=kb), rm.Mesh(new, DROPPED, sub=kb)
        if (k0.nv != k1.nv or k0.indices != k1.indices
                or any(k0.vertex_raw(i) != k1.vertex_raw(i) for i in range(k0.nv))):
            good = False
            line += f' — набалдашник [{side}] изменился'
        if rm.reencode_check(k1) or not k1.layout_ok():
            good = False
            line += f' — набалдашник [{side}] не перекодируется байт в байт'
        ok &= good
        log(line)
    return ok


def kind_prefix(kind):
    """Начало путей файлов вида (записи manifest.json при сборке части видов)."""
    return {'goalieprop': 'rendering/prop/goaliestick', 'dropped': DROPPED}.get(kind, f'rendering/{KIND_DIR[kind]}/')


def pair_rels(kind, h, v):
    """Пути клюшки и ленты пары."""
    return tuple(x.format(h=h, v=v, side=SIDES[h]) for x in KINDS[kind])


def components(m):
    """Связные куски сетки (по сварке точек) → [[вершины RW…]…]."""
    w = rm.Weld(m)
    parent = list(range(w.ngroups))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a
    for a, b, c in m.tris:
        ga, gb, gc = find(w.group[a]), find(w.group[b]), find(w.group[c])
        parent[ga] = gb
        parent[find(gc)] = find(gb)
    out = {}
    for i in range(m.nv):
        out.setdefault(find(w.group[i]), []).append(i)
    return list(out.values())


def pca_axis(pts):
    """Главное направление облака точек (степенной метод по ковариации)."""
    c = [sum(p[k] for p in pts) / len(pts) for k in range(3)]
    C = [[sum((p[i] - c[i]) * (p[j] - c[j]) for p in pts) for j in range(3)] for i in range(3)]
    v = [1.0, 0.7, 0.3]
    for _ in range(60):
        v = [sum(C[i][j] * v[j] for j in range(3)) for i in range(3)]
        v = rm.v_norm(v) or [1.0, 0.0, 0.0]
    return v


class Pair:
    """Клюшка + лента одного хвата/версии: кольца ленты на крюке, роли вершин в кольце, островок носка, рамка носка
    (O — центр кольца на стыке, n — вдоль крюка к кончику, c — по высоте крюка, w = c × n — по толщине)."""

    def __init__(self, h, v, stick=None, tape=None, kind='player'):
        self.h, self.v, self.kind = h, v, kind
        self.rel_stick, self.rel_tape = pair_rels(kind, h, v)
        self.stick = stick or rm.Mesh.game(self.rel_stick)
        self.tape = tape or rm.Mesh.game(self.rel_tape)
        st, tp = self.stick, self.tape
        tcomp = components(tp)
        self.blade = max(tcomp, key=lambda ii: max(tp.pos[i][0] for i in ii))           # крюк (дальше от торца)
        rings = {}
        for i in self.blade:
            rings.setdefault(round(tp.uv[i][0], 4), []).append(i)
        self.ring_u = sorted(rings)
        self.rings = []                    # [{роль: вершина}], роль — номер по порядку UV-v (по кругу сечения)
        for u in self.ring_u:
            ii = sorted(rings[u], key=lambda i: tp.uv[i][1])
            self.rings.append({k: i for k, i in enumerate(ii)})
        self.roles = list(range(len(self.rings[-1])))
        for k, rr in enumerate(self.rings):
            if len(rr) != len(self.roles) or any(abs(tp.uv[rr[r]][1] - tp.uv[self.rings[-1][r]][1]) > 0.002
                                                 for r in self.roles):
                raise SystemExit(f'{self.rel_tape}: кольцо {k} с другим набором вершин — разбор не подходит')
        last = self.rings[-1]
        jpos = [tp.pos[i] for i in last.values()]
        scomp = components(st)
        # островок носка: кусок клюшки, в котором есть каждая точка стыка (с точностью до 0,1 мм — у зеркальной
        # клюшки half-float расходится на единицу младшего разряда)
        isl = [ii for ii in scomp if all(min(math.dist(p, st.pos[i]) for i in ii) < 1e-4 for p in jpos)]
        if len(isl) != 1:
            raise SystemExit(f'{self.rel_stick}: не нашёл островок носка со стыком ленты')
        self.island = isl[0]
        self.joint_gap = max(min(math.dist(p, st.pos[i]) for i in self.island) for p in jpos)
        # рамка носка
        P = [tp.pos[i] for i in last.values()]
        self.O = [sum(p[k] for p in P) / len(P) for k in range(3)]
        prev = [tp.pos[i] for i in self.rings[-2].values()]
        Op = [sum(p[k] for p in prev) / len(prev) for k in range(3)]
        c = pca_axis(P)
        n = rm.v_sub(self.O, Op)
        n = rm.v_norm(rm.v_sub(n, v_mul(c, rm.v_dot(n, c))))
        isl_c = [sum(st.pos[i][k] for i in self.island) / len(self.island) for k in range(3)]
        if rm.v_dot(rm.v_sub(isl_c, self.O), n) < 0:
            n = v_mul(n, -1)
        self.c, self.n = c, n
        self.w = rm.v_cross(c, n)
        self.up = -1 if self.c[0] > 0 else 1          # кромка на льду — дальше от торца древка (больше x)
        knob = [i for comp in tcomp if comp is not self.blade for i in comp]
        self.uv_max = (min(tp.uv[i][0] for i in knob) - UV_GAP) if knob else 0.68
        self.joint_depth = max(self.local(p)[0] for p in jpos)      # стык не плоский: дальняя его точка
        self.tip = max(rm.v_dot(rm.v_sub(st.pos[i], self.O), n) for i in self.island)
        isl_set = set(self.island)
        self.isl_tris = [t for t in st.tris if t[0] in isl_set and t[1] in isl_set and t[2] in isl_set]

    def local(self, p):
        d = rm.v_sub(p, self.O)
        return rm.v_dot(d, self.n), rm.v_dot(d, self.c), rm.v_dot(d, self.w)

    def align_to_edges(self, k=3):
        """Повернуть рамку носка в плоскости крюка так, чтобы u шло вдоль кромок (по наклону верхней и нижней кромки
        на последних k кольцах ленты): у изогнутого крюка и особенно у толстой версии _4 (растянута только по y, z)
        кромки к рамке стыка наклонены. После поворота c — к верхней кромке (up = +1)."""
        tp, st = self.tape, self.stick
        cu = v_mul(self.c, self.up)

        def lv(p):
            d = rm.v_sub(p, self.O)
            return rm.v_dot(d, self.n), rm.v_dot(d, cu)

        def slope(Q):
            mu = sum(q[0] for q in Q) / len(Q)
            mv = sum(q[1] for q in Q) / len(Q)
            den = sum((q[0] - mu) ** 2 for q in Q)
            return sum((q[0] - mu) * (q[1] - mv) for q in Q) / den if den > 0 else 0.0
        tops, bots = [], []
        for rr in self.rings[-k:]:
            P = [lv(tp.pos[i]) for i in rr.values()]
            tops.append(max(P, key=lambda q: q[1]))
            bots.append(min(P, key=lambda q: q[1]))
        th = math.atan((slope(tops) + slope(bots)) / 2)
        n2 = rm.v_norm(v_add(v_mul(self.n, math.cos(th)), v_mul(cu, math.sin(th))))
        c2 = rm.v_norm(v_add(v_mul(cu, math.cos(th)), v_mul(self.n, -math.sin(th))))
        self.n, self.c, self.up = n2, c2, 1
        self.w = rm.v_cross(self.c, self.n)
        self.tip = max(self.local(st.pos[i])[0] for i in self.island)
        self.joint_depth = max(self.local(tp.pos[i])[0] for i in self.rings[-1].values())
        self.edge_tilt_deg = math.degrees(th)
        return th

    # --- сечение носка плоскостью u = const
    def slice(self, u):
        """Сечение островка носка плоскостью на глубине u → отрезки [((p, атрибуты-источник), (p, …))]: каждая точка —
        (позиция, вершины a, b, доля t) — на ребре треугольника островка."""
        st = self.stick
        segs = []
        for tri in self.isl_tris:
            d = [self.local(st.pos[i])[0] - u for i in tri]
            pts = []
            for k in range(3):
                a, b = tri[k], tri[(k + 1) % 3]
                da, db = d[k], d[(k + 1) % 3]
                if (da < 0) != (db < 0):
                    t = da / (da - db)
                    pts.append((lerp(st.pos[a], st.pos[b], t), a, b, t))
            if len(pts) == 2:
                segs.append(pts)
        return segs

    def ring_frame(self, pts):
        """Центр и полуразмеры кольца в плоскости (v, t)."""
        loc = [self.local(p) for p in pts]
        vs, ts = [q[1] for q in loc], [q[2] for q in loc]
        return ((min(vs) + max(vs)) / 2, (min(ts) + max(ts)) / 2,
                max(1e-6, (max(vs) - min(vs)) / 2), max(1e-6, (max(ts) - min(ts)) / 2))

    def role_angles(self):
        """Углы ролей кольца на стыке в нормированных (v, t) — запасной способ поставить роль на новое кольцо."""
        tp = self.tape
        last = self.rings[-1]
        cv, ct, hv, ht = self.ring_frame([tp.pos[i] for i in last.values()])
        out = {}
        for r, i in last.items():
            _, vv, tt = self.local(tp.pos[i])
            out[r] = math.atan2((tt - ct) / ht, (vv - cv) / hv)
        return out

    def rails(self):
        """«Рельсы» носка: островок — только края: ряд контура (силуэт) и ряд края фаски (~5 мм внутрь), у каждого —
        стороны A/B по толщине; рельс — ломаная по ряду и стороне от стыка сверху через кончик к стыку снизу.
        → {(ряд 'out'|'in', сторона +1|−1): [(угол, позиция, нормаль, касательная)…] по убыванию угла},
        роли кольца на стыке → (ряд, сторона, ветвь 'top'|'bot')."""
        st, tp = self.stick, self.tape
        w = rm.Weld(st)
        groups = {}
        for i in self.island:
            groups.setdefault(w.group[i], []).append(i)
        pts = []
        for g, ii in groups.items():
            p = st.pos[ii[0]]
            nrm = rm.v_norm([sum(st.nrm[i][k] for i in ii) for k in range(3)]) or st.nrm[ii[0]]
            tan = rm.v_norm([sum(st.tan[i][k] for i in ii) for k in range(3)]) or st.tan[ii[0]]
            u, v, t = self.local(p)
            pts.append({'p': p, 'n': nrm, 't': tan, 'u': u, 'v': v, 'w': t})
        last = self.rings[-1]
        jl = [self.local(tp.pos[i]) for i in last.values()]
        vc = (min(q[1] for q in jl) + max(q[1] for q in jl)) / 2
        # станции: точки островка группами по углу вокруг (0, vc) — у каждой 4 точки: 2 дальние — контур, 2 ближние —
        # край фаски; в паре сторона — по толщине (больше — +1)
        for q in pts:
            q['ang'] = math.atan2(q['v'] - vc, q['u'])
            q['rad'] = math.hypot(q['u'], q['v'] - vc)
        srt = sorted(pts, key=lambda q: -q['ang'])
        stations, cur = [], [srt[0]]
        for q in srt[1:]:
            if cur[-1]['ang'] - q['ang'] > math.radians(6):
                stations.append(cur)
                cur = []
            cur.append(q)
        stations.append(cur)
        rails = {}
        for stn in stations:
            if len(stn) != 4:
                raise SystemExit(f'носок: станция из {len(stn)} точек (ожидалось 4) — разбор не подходит')
            stn = sorted(stn, key=lambda q: -q['rad'])
            for row, pair_ in (('out', stn[:2]), ('in', stn[2:])):
                a_, b_ = sorted(pair_, key=lambda q: -q['w'])
                for side, x in ((+1, a_), (-1, b_)):
                    x['row'] = row
                    rails.setdefault((row, side), []).append((x['ang'], x['p'], x['n'], x['t'], x['u']))
        for key in rails:
            rails[key].sort(key=lambda e: -e[0])
        # роли стыка: ряд — по ближайшей точке островка, сторона — по толщине в паре, ветвь — по v
        roles = {}
        for r, i in last.items():
            p = tp.pos[i]
            q = min(pts, key=lambda q: math.dist(q['p'], p))
            _, v, _ = self.local(p)
            side = None
            for (row, sd), lst in rails.items():
                if row == q['row'] and any(math.dist(e[1], q['p']) < 1e-9 for e in lst):
                    side = sd
            roles[r] = (q['row'], side, 'top' if v > vc else 'bot')
        return rails, roles

    @staticmethod
    def rail_cross(rail, u, branch):
        """Точка рельса на глубине u на ветви 'top' (от стыка сверху к кончику) или 'bot' (от стыка снизу) →
        (позиция, нормаль, касательная) или None (рельс до этой глубины не доходит)."""
        k_apex = max(range(len(rail)), key=lambda k: rail[k][4])
        seq = rail[:k_apex + 1] if branch == 'top' else rail[k_apex:][::-1]
        for a_, b_ in zip(seq, seq[1:]):
            ua, ub = a_[4], b_[4]
            if (ua - u) * (ub - u) <= 0 and ua != ub:
                t = (u - ua) / (ub - ua)
                return (lerp(a_[1], b_[1], t), rm.v_norm(lerp(a_[2], b_[2], t)) or a_[2],
                        rm.v_norm(lerp(a_[3], b_[3], t)) or a_[3])
        return None

    def new_ring(self, u, angles, rails=None, only=None):
        """Кольцо на глубине u → {роль: (позиция, нормаль, касательная)}: роли контура и фаски — на своих рельсах
        (rails); где рельс до этой глубины не доходит (фаска кончается раньше контура) и без рельсов — точка сечения
        на луче под углом роли (нормированные v, t)."""
        if only is not None:
            angles = {r: a for r, a in angles.items() if r in only}
        if rails is not None:
            rl, roles = rails
            out, rest = {}, {}
            for r, (row, side, branch) in roles.items():
                if r not in angles:
                    continue
                rail = rl.get((row, side))
                hit = self.rail_cross(rail, u, branch) if rail else None
                if hit is None:
                    rest[r] = angles[r]                 # рельс сюда не доходит — точка сечения по углу
                else:
                    out[r] = hit
            if rest:
                out.update(self.new_ring(u, rest))
            return out
        st = self.stick
        segs = self.slice(u)
        if not segs:
            raise SystemExit(f'носок: нет сечения на глубине {u * 1000:.1f} мм')
        pts = [q[0] for s_ in segs for q in s_]
        cv, ct, hv, ht = self.ring_frame(pts)
        out = {}
        for r, ang in angles.items():
            dv, dt = math.cos(ang), math.sin(ang)
            best = None
            for s_ in segs:
                (pa, a0, b0, t0), (pb, a1, b1, t1) = s_
                _, va, ta_ = self.local(pa)
                _, vb, tb = self.local(pb)
                xa, ya = (va - cv) / hv, (ta_ - ct) / ht
                xb, yb = (vb - cv) / hv, (tb - ct) / ht
                ex, ey = xb - xa, yb - ya
                den = -dv * ey + dt * ex
                if abs(den) < 1e-12:
                    continue
                lam = (-xa * ey + ya * ex) / den               # расстояние по лучу
                sg = (dv * ya - dt * xa) / den                 # доля по отрезку
                if lam > 0 and -1e-9 <= sg <= 1 + 1e-9 and (best is None or lam > best[0]):
                    best = (lam, s_, min(1.0, max(0.0, sg)))
            if best is None:
                # у самого кончика сечение крошечное и луч может пройти мимо — ближайшая по направлению точка
                cand = []
                for s_ in segs:
                    for k, q in enumerate(s_):
                        _, vq, tq = self.local(q[0])
                        cand.append((dv * (vq - cv) / hv + dt * (tq - ct) / ht, s_, float(k)))
                if not cand:
                    raise SystemExit(f'носок: роль {r} не нашлась в сечении {u * 1000:.1f} мм')
                best = max(cand, key=lambda e: e[0])
            _, s_, sg = best
            (pa, a0, b0, t0), (pb, a1, b1, t1) = s_
            pos = lerp(pa, pb, sg)

            def attr(arr):
                x = lerp(arr[a0], arr[b0], t0)
                y = lerp(arr[a1], arr[b1], t1)
                return rm.v_norm(lerp(x, y, sg)) or x
            out[r] = (pos, attr(st.nrm), attr(st.tan))
        return out

    def segment_pattern(self, j=None):
        """Треугольники отрезка ленты (кольцо j → j + 1, по умолчанию последний) как ((кольцо 0/1, роль)×3)."""
        tp = self.tape
        j = len(self.rings) - 2 if j is None else j
        a, b = self.rings[j], self.rings[j + 1]
        where = {}
        for r, i in a.items():
            where[i] = (0, r)
        for r, i in b.items():
            where[i] = (1, r)
        pat = []
        for t in tp.tris:
            if all(i in where for i in t) and len({where[i][0] for i in t}) == 2:
                pat.append(tuple(where[i] for i in t))
        return pat


ROUNDS = {'none': None, 'moderate': (0.45, 0.25), 'strong': (0.62, 0.32),
          'bottom1': (0.62, 0.47), 'bottom2': (0.62, 0.62)}      # (R верхнего угла, R нижнего) / высота крюка у носка
ROUND_NAMES = {'none': 'без скругления', 'moderate': 'умеренно', 'strong': 'сильнее',
               'bottom1': 'низ-1', 'bottom2': 'низ-2'}
ROUND_DEFAULT = 'none,strong,bottom1,bottom2'
SMOOTH = 0.05                                 # ширина плавного сопряжения дуги с исходным контуром / высота крюка


def t_range(edges, a):
    """Края сечения по толщине на высоте a: edges — отрезки ((v, t), (v, t)) → (t мин, t макс) или None."""
    ts = []
    for (va, ta), (vb, tb) in edges:
        if (va - a) * (vb - a) <= 0 and va != vb:
            ts.append(ta + (tb - ta) * (a - va) / (vb - va))
    return (min(ts), max(ts)) if ts else None


def smoothstep(e0, e1, x):
    if x <= e0:
        return 0.0
    if x >= e1:
        return 1.0
    t = (x - e0) / (e1 - e0)
    return t * t * (3 - 2 * t)


def smin(a, b, k):
    """Гладкий минимум (C1): совпадает с min вдали от пересечения, у пересечения — плавное сопряжение шириной k."""
    if k <= 0 or abs(a - b) >= k:
        return min(a, b)
    h = 0.5 + 0.5 * (b - a) / k
    return b * (1 - h) + a * h - k * h * (1 - h)


def smax(a, b, k):
    return -smin(-a, -b, k)


def half_neighbors(x):
    """Представимые в half-float значения у x: ближайшее и соседние по обе стороны."""
    r = rm.half_enc(x)
    out = set()
    for rr in (r - 1, r, r + 1):
        if 0 <= rr <= 0xFFFF:
            v = rm.half_dec(rr)
            if math.isfinite(v):
                out.add(v)
    if r in (0, 0x8000):
        out.update((rm.half_dec(1), rm.half_dec(0x8001)))
    return sorted(out)


def quantize_on_rail(q, T, limit, eps0=0.02):
    """Узел сетки half-float рядом с q (позиция в буфере — FLOAT16), чтобы ряд вершины (её «рельс» вдоль крюка,
    направление T) не ломался: ошибка поперёк ряда — минимальна, сдвиг вдоль ряда — дешёвый, но не дальше limit (иначе
    вершина подошла бы к соседней по ряду). Ошибку грубого x (у x ≈ 1,5 м шаг ~1 мм) гасят мелкие y, z: минимум
    |e⊥|² + eps·e∥²; где сдвиг упирается в limit, eps растёт (ошибка уходит поперёк, но в пределах полушага)."""
    Tx, Ty, Tz = T
    xs = sorted(half_neighbors(q[0]), key=lambda x: abs(x - q[0]))[:2]
    best = None
    for eps in (eps0, 0.1, 0.5, 2.0, 10.0):
        g = 1 - eps
        qyy, qzz, qyz = 1 - g * Ty * Ty, 1 - g * Tz * Tz, -g * Ty * Tz
        det = qyy * qzz - qyz * qyz
        for x in xs:
            d = x - q[0]
            ry, rz = g * Ty * Tx * d, g * Tz * Tx * d
            ay = (ry * qzz - qyz * rz) / det
            az = (qyy * rz - qyz * ry) / det
            for y in half_neighbors(q[1] + ay):
                for z in half_neighbors(q[2] + az):
                    e = (x - q[0], y - q[1], z - q[2])
                    ep = e[0] * Tx + e[1] * Ty + e[2] * Tz
                    if abs(ep) > limit:
                        continue
                    cost = e[0] * e[0] + e[1] * e[1] + e[2] * e[2] - (1 - eps0) * ep * ep
                    if best is None or cost < best[0]:
                        best = (cost, (x, y, z))
    if best is None:
        return [rm.half_dec(rm.half_enc(c)) for c in q]
    return list(best[1])


def rail_candidates(q, T, limit, eps0=0.02):
    """Все узлы-кандидаты quantize_on_rail (и просто ближайший) с их ценой → [(цена, (x, y, z))], по возрастанию."""
    Tx, Ty, Tz = T
    xs = sorted(half_neighbors(q[0]), key=lambda x: abs(x - q[0]))[:2]
    out = {}
    for eps in (eps0, 0.1, 0.5, 2.0, 10.0):
        g = 1 - eps
        qyy, qzz, qyz = 1 - g * Ty * Ty, 1 - g * Tz * Tz, -g * Ty * Tz
        det = qyy * qzz - qyz * qyz
        for x in xs:
            d = x - q[0]
            ry, rz = g * Ty * Tx * d, g * Tz * Tx * d
            ay = (ry * qzz - qyz * rz) / det
            az = (qyy * rz - qyz * ry) / det
            for y in half_neighbors(q[1] + ay):
                for z in half_neighbors(q[2] + az):
                    e = (x - q[0], y - q[1], z - q[2])
                    ep = e[0] * Tx + e[1] * Ty + e[2] * Tz
                    if abs(ep) > limit:
                        continue
                    out[(x, y, z)] = e[0] * e[0] + e[1] * e[1] + e[2] * e[2] - (1 - eps0) * ep * ep
    near = tuple(rm.half_dec(rm.half_enc(c)) for c in q)
    if near not in out:
        e = [near[k] - q[k] for k in range(3)]
        ep = rm.v_dot(e, T)
        out[near] = rm.v_dot(e, e) - (1 - eps0) * ep * ep
    return sorted((c, p) for p, c in out.items())


def build_pair(pair, rounding=None, uv_max=None, use_rails=True):
    """Лента до носка (и, если rounding = (Rв, Rн) в долях высоты крюка у носка, — носок круглее: дуги радиуса Rв у
    верхнего угла и Rн у нижнего, касательные к кромкам и к концу носка). → (файл ленты, файл клюшки, отчёт).

    Кольца ленты после «якорного» (последнего кольца тела, которое скругление не задевает) заменяются новыми: точки
    ролей — на исходной поверхности (между кольцами тела — на их рёбрах, дальше — на рельсах носка или в сечении
    носка по углу роли), затем при скруглении сечение сжимается по высоте до нового контура; нормали — исходные,
    повёрнутые так же, как повернулась поверхность. Торец закрыт, островок носка клюшки стянут в точку."""
    st, tp = pair.stick, pair.tape
    uv_max = uv_max or pair.uv_max
    pre = tuple(getattr(pair, 'prescale', None) or (1.0, 1.0, 1.0))
    out_p = lambda q: [q[0] / pre[0], q[1] / pre[1], q[2] / pre[2]]              # обратно из пространства разбора
    out_n = lambda q: rm.v_norm([q[0] * pre[0], q[1] * pre[1], q[2] * pre[2]]) or q
    out_t = lambda q: rm.v_norm([q[0] / pre[0], q[1] / pre[1], q[2] / pre[2]]) or q
    pair.align_to_edges()
    angles = pair.role_angles()
    rails = None
    if use_rails:
        try:
            rails = pair.rails()
        except SystemExit:
            rails = None                          # другое устройство носка (у вратарских — 5 точек на станции)
    roles = pair.roles
    loc = [{r: pair.local(tp.pos[i]) for r, i in rr.items()} for rr in pair.rings]
    up = pair.up
    vv = lambda q: q[1] * up                                     # высота «вверх» (от кромки на льду)
    j8 = len(pair.rings) - 1
    H = max(vv(q) for q in loc[j8].values()) - min(vv(q) for q in loc[j8].values())
    tip = pair.tip
    if rounding:
        Rt, Rb = rounding[0] * H, rounding[1] * H
        u_rs = tip - max(Rt, Rb)                                 # где начинается скругление
    else:
        Rt = Rb = 0.0
        u_rs = 0.0
    # якорь — последнее кольцо тела целиком раньше начала скругления (с запасом)
    margin = 0.15 * tip
    anchor = 0
    for j in range(j8):
        if max(q[0] for q in loc[j].values()) < u_rs - margin:
            anchor = j
    if anchor >= j8:
        anchor = j8 - 1
    pattern = pair.segment_pattern(anchor)

    def sample(u):
        """Роли исходной поверхности на глубине u → {роль: (позиция, нормаль, касательная)}."""
        out, rest = {}, {}
        for r in roles:
            done = False
            for j in range(anchor, j8):
                ua, ub = loc[j][r][0], loc[j + 1][r][0]
                if ua <= u <= ub and ub > ua:
                    t = (u - ua) / (ub - ua)
                    ia, ib = pair.rings[j][r], pair.rings[j + 1][r]
                    out[r] = (lerp(tp.pos[ia], tp.pos[ib], t), rm.v_norm(lerp(tp.nrm[ia], tp.nrm[ib], t)) or tp.nrm[ia],
                              rm.v_norm(lerp(tp.tan[ia], tp.tan[ib], t)) or tp.tan[ia])
                    done = True
                    break
            if not done:
                rest[r] = angles[r]
        if rest:
            out.update(pair.new_ring(u, angles, rails, only=rest))
        return out

    def extents(smp):
        vs = [vv(pair.local(q[0])) for q in smp.values()]
        return min(vs), max(vs)

    # контур скругления: верх ≤ T(u), низ ≥ B(u) — четверти эллипсов от касательных к кромкам (наклон кромки — по
    # исходной поверхности перед началом скругления) до конца носка, где касательная вертикальна: вдоль кромки
    # скругление занимает R (Rв у верхнего угла, Rн у нижнего); по высоте — тоже R, а если Rв + Rн больше высоты
    # крюка у кончика, высота делится между углами пропорционально (оба эллипса сходятся в конце носка гладко, без
    # острия)
    if rounding:
        def edge_line(u_s, which):
            d = 0.1 * max(Rt, Rb)
            e0, e1 = extents(sample(u_s - d)), extents(sample(u_s))
            k = 1 if which == 'top' else 0
            return e1[k], (e1[k] - e0[k]) / d
        top0, top_k = edge_line(tip - Rt, 'top')
        bot0, bot_k = edge_line(tip - Rb, 'bot')
        H_tip = (top0 + top_k * Rt) - (bot0 + bot_k * Rb)          # высота между продолженными кромками у кончика
        if Rt + Rb > H_tip:
            bt, bb = H_tip * Rt / (Rt + Rb), H_tip * Rb / (Rt + Rb)
        else:
            bt, bb = Rt, Rb

    def limits(u):
        if not rounding:
            return 1e9, -1e9
        T = 1e9
        if u > tip - Rt:
            d = min(Rt, u - (tip - Rt))
            T = top0 + top_k * d - bt * (1 - math.sqrt(max(0.0, 1 - (d / Rt) ** 2)))
        B = -1e9
        if u > tip - Rb:
            d = min(Rb, u - (tip - Rb))
            B = bot0 + bot_k * d + bb * (1 - math.sqrt(max(0.0, 1 - (d / Rb) ** 2)))
        return T, B

    ks = SMOOTH * H

    def new_extents(lo_, hi_, u):
        """Новые границы сечения: исходные, срезанные дугами; там, где дуга пересекает исходный контур (у кончика),
        сопряжение плавное (ширина растёт от нуля у начала дуги — у касания с кромкой срез точный, без ступеньки)."""
        T, B = limits(u)
        kt = ks * smoothstep(0.0, 0.35 * Rt, u - (tip - Rt)) if rounding else 0.0
        kb = ks * smoothstep(0.0, 0.35 * Rb, u - (tip - Rb)) if rounding else 0.0
        return smax(lo_, B, kb), smin(hi_, T, kt)

    def chord(u):
        lo_, hi_ = extents(sample(u))
        nlo, nhi = new_extents(lo_, hi_, u)
        return nhi - nlo

    # глубины колец: от якоря до начала скругления — крупно; на скруглении — по углу эллипсов (равные доли дуги:
    # гуще у конца, где контур поворачивает круче), кольца — не ближе 0,05 глубины носка друг к другу (неровный шаг
    # колец дал бы полосы на фасках, а half-float у x ≈ 1,5 м с шагом ~1 мм — «пилу»); без скругления — шаг 0,12
    # глубины носка и гуще у кончика; конец — где хорда сечения меньше 5 % высоты крюка (или 0,99 глубины носка) —
    # там торец
    u_first = max(q[0] for q in loc[anchor].values())
    u_mid = max(u_first + 0.02 * tip, min(u_rs, 0.0) if rounding else 0.0)
    depths = []
    n_a = max(1, int(math.ceil((u_mid - u_first) / (0.25 * tip))))
    for k in range(1, n_a + 1):
        depths.append(u_first + (u_mid - u_first) * k / n_a)
    end_u = 0.99 * tip
    min_chord = 0.05 * H
    cand = []
    if rounding:
        for R in (Rt, Rb):
            n_ang = 14
            for k in range(1, n_ang + 1):
                cand.append(tip - R + R * math.sin(0.5 * math.pi * k / n_ang))
    else:
        # исходный носок: от стыка шагом 0,12 глубины, у кончика — гуще (контур носка поворачивает)
        u0_ = max(depths[-1], 0.0)
        k = 1
        while u0_ + 0.12 * tip * k < 0.8 * tip:
            cand.append(u0_ + 0.12 * tip * k)
            k += 1
        for f in (0.8, 0.86, 0.91, 0.95, 0.98):
            cand.append(f * tip)
    cand = sorted(c for c in cand if depths[-1] + 0.05 * tip <= c <= end_u)
    picked = []
    for c in cand:
        if not picked or c - picked[-1] >= 0.05 * tip:
            picked.append(c)
    u = depths[-1]
    for c in picked + [end_u]:
        if c <= u + 1e-9:
            continue
        last = c >= end_u
        if chord(c) < min_chord:
            lo_, hi_ = u, c
            for _ in range(30):
                mid = (lo_ + hi_) / 2
                if chord(mid) < min_chord:
                    hi_ = mid
                else:
                    lo_ = mid
            c, last = lo_, True
        # кольца ближе 0,03 глубины носка друг к другу не ставятся: у кончика ряды сходятся, и тесные кольца дали бы
        # перевёрнутые треугольники — последнее кольцо тогда встаёт на место предыдущего
        if c - u < 0.03 * tip:
            if len(depths) > n_a:
                depths[-1] = c
            elif c - u >= 0.015 * tip:
                depths.append(c)
        else:
            depths.append(c)
        u = depths[-1]
        if last:
            break

    # кольца. До стыка (все роли — на кольцах тела) — исходная поверхность; при скруглении она сжимается по высоте до
    # контура. Дальше стыка при скруглении — «протяжка» сечения тела: сечение у стыка (шаблон: высоты ролей,
    # толщины) вписывается в новый контур, середина и толщина крюка — по исходному носку (сглажены вдоль крюка),
    # фаски — в той же доле высоты, что у шаблона: так носок гладкий, без граней и изломов исходного островка носка
    # клюшки (по нему ряд фаски шёл бы ломаной). Без скругления — исходный носок как есть (сечения островка по
    # рельсам; где рельсов нет — та же протяжка, вписанная в исходный контур).
    u_T = min(loc[j8][r][0] for r in roles)                       # дальше — часть ролей уже на островке
    rows = []
    for u in depths:
        smp = sample(u)
        Ls = {r: pair.local(p) for r, (p, _, _) in smp.items()}
        hi_ = max(vv(q) for q in Ls.values())
        lo_ = min(vv(q) for q in Ls.values())
        nlo, nhi = new_extents(lo_, hi_, u)
        if nhi < nlo:                                            # не должно случаться (конец — раньше)
            nhi = nlo = (nhi + nlo) / 2
        ts = [q[2] for q in Ls.values()]
        rows.append([u, smp, Ls, lo_, hi_, nlo, nhi, (min(ts) + max(ts)) / 2, max(ts) - min(ts)])
    templ = None
    # протяжка сечения — при скруглении и там, где у носка нет рельсов (у вратарских): сечения островка по углу ролей
    # там путают порядок ролей по кругу (перевёрнутые треугольники), а сечение стыка, вписанное в контур островка, —
    # нет; контур при этом — исходный
    if rounding or rails is None:
        smpT = sample(u_T)
        LT = {r: pair.local(p) for r, (p, _, _) in smpT.items()}
        loT, hiT = min(vv(q) for q in LT.values()), max(vv(q) for q in LT.values())
        tsT = [q[2] for q in LT.values()]
        tmT, thT = (min(tsT) + max(tsT)) / 2, max(tsT) - min(tsT)
        templ = {r: ((vv(q) - loT) / (hiT - loT), (q[2] - tmT) / thT if thT > 0 else 0.0) for r, q in LT.items()}
        # без рельсов (вратарские): у кончика толщина ролей берётся из сечения островка носка на высоте роли — доля
        # роли между краями сечения (0 — сторона −w, 1 — сторона +w) — по шаблону; сечение вратарского крюка
        # S-образное (лицо крюка закручено), и протянутое к крутому кончику оно дало бы перекрученные полоски
        if rails is None:
            loop_ = [(vv(LT[r]), LT[r][2]) for r in sorted(roles, key=lambda r: tp.uv[pair.rings[j8][r]][1])]
            edgesT = list(zip(loop_, loop_[1:] + loop_[:1]))
            phi = {}
            for r, q in LT.items():
                rng = t_range(edgesT, min(hiT - 0.02 * (hiT - loT), max(loT + 0.02 * (hiT - loT), vv(q))))
                phi[r] = min(1.0, max(0.0, (q[2] - rng[0]) / (rng[1] - rng[0]))) if rng and rng[1] > rng[0] else 0.5
        # середина и толщина вдоль носка — гладкая парабола по исходному носку, проходящая через шаблон у стыка
        # (у островка грани плоские, сечения по ним дали бы изломы — по ним фаски и грани шли бы полосами)
        idx = [k for k, row in enumerate(rows) if row[0] > u_T]
        if idx:
            def fit(col, y0):
                # y = y0 + a·x + b·x², x = u − u_T, наименьшие квадраты
                X = [rows[k][0] - u_T for k in idx]
                Y = [rows[k][col] - y0 for k in idx]
                s11 = sum(x * x for x in X)
                s12 = sum(x ** 3 for x in X)
                s22 = sum(x ** 4 for x in X)
                r1 = sum(x * y for x, y in zip(X, Y))
                r2 = sum(x * x * y for x, y in zip(X, Y))
                det = s11 * s22 - s12 * s12
                if abs(det) < 1e-30:
                    return lambda x: y0
                a = (r1 * s22 - r2 * s12) / det
                b = (s11 * r2 - s12 * r1) / det
                return lambda x: y0 + a * x + b * x * x
            ftm, fth = fit(7, tmT), fit(8, thT)
            for k in idx:
                x = rows[k][0] - u_T
                rows[k][7] = ftm(x)
                rows[k][8] = max(0.3 * thT, fth(x))
    new_rings = []
    u_J = max(loc[j8][r][0] for r in roles)                       # дальше — все роли на островке
    for u, smp, Ls, lo_, hi_, nlo, nhi, tm, th in rows:
        ring = {}
        isl_edges, blend = None, 0.0
        if templ is not None and rails is None and u > u_J:
            blend = smoothstep(u_J, u_J + 0.25 * tip, u)
            segs = pair.slice(u)
            isl_edges = [tuple((vv(pair.local(q[0])), pair.local(q[0])[2]) for q in sg) for sg in segs] or None
        for r, (p, nrm, tan) in smp.items():
            uu, v, tt = Ls[r]
            if templ is not None and u > u_T:
                fv, ft = templ[r]
                a2 = nlo + fv * (nhi - nlo)
                tt = tm + ft * th
                uu = u
                if isl_edges is not None and blend > 0:
                    lo_i, hi_i = min(min(e[0][0], e[1][0]) for e in isl_edges), max(max(e[0][0], e[1][0]) for e in isl_edges)
                    rng = t_range(isl_edges, min(hi_i - 0.02 * (hi_i - lo_i), max(lo_i + 0.02 * (hi_i - lo_i), a2)))
                    if rng:
                        tt += blend * (rng[0] + phi[r] * (rng[1] - rng[0]) - tt)
                p = v_add(v_add(pair.O, v_mul(pair.n, uu)), v_add(v_mul(pair.c, a2 * up), v_mul(pair.w, tt)))
            elif nhi < hi_ or nlo > lo_:
                a = vv(Ls[r])
                a2 = nlo + (a - lo_) * (nhi - nlo) / (hi_ - lo_) if hi_ > lo_ else a
                p = v_add(v_add(pair.O, v_mul(pair.n, uu)), v_add(v_mul(pair.c, a2 * up), v_mul(pair.w, tt)))
            ring[r] = (p, nrm, tan)
        new_rings.append(ring)
    # нормали и касательные: авторские нормали якорного кольца, перенесённые по новой поверхности — повёрнуты так же,
    # как нормаль граней новой сетки в этой роли отличается от нормали граней в якоре (у носка исходные нормали
    # островка на кромке разрезаны и в среднем шумят — по ним фаска шла бы пятнами)
    def ring_normals(rs):
        acc = [{r: [0.0, 0.0, 0.0] for r in roles} for _ in rs]
        for k in range(len(rs) - 1):
            for t in pattern:
                P = [rs[k + off][r] for off, r in t]
                fn = rm.v_cross(rm.v_sub(P[1], P[0]), rm.v_sub(P[2], P[0]))
                for off, r in t:
                    x = acc[k + off][r]
                    x[0] += fn[0]
                    x[1] += fn[1]
                    x[2] += fn[2]
        return acc
    seq = [{r: tp.pos[i] for r, i in pair.rings[anchor - 1].items()} if anchor > 0 else None,
           {r: tp.pos[i] for r, i in pair.rings[anchor].items()}] + [{r: q[0] for r, q in ring.items()}
                                                                    for ring in new_rings]
    if seq[0] is None:
        seq = seq[1:]
    g = ring_normals(seq)
    ka = 1 if anchor > 0 else 0                                  # якорь в seq
    for k, ring in enumerate(new_rings):
        for r, (p, _, _) in ring.items():
            ia = pair.rings[anchor][r]
            a_, b_ = rm.v_norm(g[ka][r]), rm.v_norm(g[ka + 1 + k][r])
            nrm, tan = tp.nrm[ia], tp.tan[ia]
            rot = rm.rotation_between(a_, b_) if a_ and b_ else None
            if rot:
                nrm = rm.v_norm(rot(nrm)) or nrm
                tan = rot(tan)
            d = rm.v_dot(tan, nrm)
            tan = rm.v_norm([tan[i] - d * nrm[i] for i in range(3)]) or tan
            ring[r] = (p, nrm, tan)
    # сглаживание нормалей вдоль крюка (гаусс по глубине, σ = 0,08 глубины носка): у неравномерных колец нормали
    # граней «пляшут» от кольца к кольцу — на фаске это видно полосами
    sig = 0.08 * tip
    us_ = [pair.local(next(iter(ring.values()))[0])[0] for ring in new_rings]
    sm = []
    for k, ring in enumerate(new_rings):
        out_ = {}
        for r, (p, nrm, tan) in ring.items():
            an, at = [0.0, 0.0, 0.0], [0.0, 0.0, 0.0]
            for j, rj in enumerate(new_rings):
                wgt = math.exp(-((us_[j] - us_[k]) / sig) ** 2)
                if wgt < 1e-3:
                    continue
                nj, tj = rj[r][1], rj[r][2]
                for i in range(3):
                    an[i] += wgt * nj[i]
                    at[i] += wgt * tj[i]
            n2 = rm.v_norm(an) or nrm
            d = rm.v_dot(at, n2)
            t2 = rm.v_norm([at[i] - d * n2[i] for i in range(3)]) or tan
            out_[r] = (p, n2, t2)
        sm.append(out_)
    new_rings = sm

    # half-float: позиции в буфере — FLOAT16; у x ≈ 1,5 м шаг ~1 мм (у y, z — от сотых до 0,24 мм). Простое
    # округление сдвигало бы вершины поперёк их рядов (контур «пилой», края фасок и полосы света зигзагом). Каждая
    # новая вершина ставится в соседний представимый узел, который лежит на её ряду: ошибка x гасится сдвигом по y, z
    # вдоль ряда (не дальше 0,4 расстояния до соседней вершины ряда), поперёк — не больше, чем неизбежно
    anchor_pos = {r: tp.pos[i] for r, i in pair.rings[anchor].items()}
    raw = [{r: out_p(q[0]) for r, q in ring.items()} for ring in new_rings]
    qin = {}                                                      # (кольцо, роль) → (позиция, T, предел сдвига)
    for k, ring in enumerate(new_rings):
        for r, (p, nrm, tan) in list(ring.items()):
            q = raw[k][r]
            qa = raw[k - 1][r] if k > 0 else out_p(anchor_pos[r])
            qb = raw[k + 1][r] if k + 1 < len(new_rings) else None
            T = rm.v_norm(rm.v_sub(qb if qb else q, qa))
            gaps = [math.dist(q, qa)] + ([math.dist(q, qb)] if qb else [])
            if T is None:
                qq = [rm.half_dec(rm.half_enc(c)) for c in q]
            else:
                qq = quantize_on_rail(q, T, 0.4 * min(gaps))
                qin[(k, r)] = (q, T, 0.4 * min(gaps))
            ring[r] = ([qq[0] * pre[0], qq[1] * pre[1], qq[2] * pre[2]], nrm, tan)

    # перевёрнутые треугольники после округления (бывают у самого кончика вратарских, где ряды круто падают и идут
    # тесно): вершины таких треугольников переставляются в другие соседние узлы half-float — с наименьшим числом
    # перевёрнутых вокруг, затем с наименьшей ценой; вершины-близнецы (шов развёртки — одна точка) двигаются вместе.
    # Если перевёрнутых нет (у всех полевых клюшек), ничего не меняется
    seq_p = [{r: out_p(p) for r, p in anchor_pos.items()}] + [{r: out_p(q[0]) for r, q in ring.items()}
                                                             for ring in new_rings]
    seq_n = [{r: out_n(tp.nrm[i]) for r, i in pair.rings[anchor].items()}] + [{r: out_n(q[1]) for r, q in ring.items()}
                                                                          for ring in new_rings]
    tri_k = [[(k + off, r) for off, r in t] for k in range(len(seq_p) - 1) for t in pattern]

    def inverted(tr):
        a_, b_, c_ = (seq_p[k][r] for k, r in tr)
        fn = rm.v_cross(rm.v_sub(b_, a_), rm.v_sub(c_, a_))
        if rm.v_dot(fn, fn) <= 1e-14:
            return False
        return rm.v_dot(fn, [sum(seq_n[k][r][i] for k, r in tr) for i in range(3)]) <= 0
    bad = [tr for tr in tri_k if inverted(tr)]
    if bad:
        groups = {}                                               # (кольцо, позиция) → роли-близнецы
        for (k, r) in qin:
            groups.setdefault((k, tuple(round(c, 9) for c in qin[(k, r)][0])), []).append(r)
        group_of = {(k, r): (k, key) for (k, key), rs in groups.items() for r in rs}
        around = {}
        for tr in tri_k:
            for k, r in tr:
                around.setdefault((k, r), []).append(tr)
        for _ in range(6):
            bad = [tr for tr in tri_k if inverted(tr)]
            if not bad:
                break
            for tr in bad:
                for k, r in tr:
                    if k == 0 or (k - 1, r) not in qin:
                        continue
                    gk = group_of[(k - 1, r)]
                    members = groups[(gk[0], gk[1])]
                    tris_ = {tuple(x) for m_ in members for x in map(tuple, around[(k, m_)])}
                    q, T, lim = qin[(k - 1, r)]
                    best = None
                    for cost, cand in rail_candidates(q, T, 2.5 * lim):
                        for m_ in members:
                            seq_p[k][m_] = list(cand)
                        nb = sum(1 for x in tris_ if inverted(x))
                        if best is None or (nb, cost) < best[:2]:
                            best = (nb, cost, cand)
                    for m_ in members:
                        seq_p[k][m_] = list(best[2])
        for kk, ring in enumerate(new_rings):
            for r, (p, nrm, tan) in list(ring.items()):
                qq = seq_p[kk + 1][r]
                ring[r] = ([qq[0] * pre[0], qq[1] * pre[1], qq[2] * pre[2]], nrm, tan)

    # UV-u: длина по центрам колец от якоря, плотность — как у тела крюка, рисунок не залезает в набалдашник
    def center(P):
        return [sum(p[k] for p in P) / len(P) for k in range(3)]
    centers = [center([tp.pos[i] for i in rr.values()]) for rr in pair.rings]
    s_body = [0.0]
    for k in range(1, len(centers)):
        s_body.append(s_body[-1] + math.dist(centers[k], centers[k - 1]))
    u0 = pair.ring_u[0]
    dens = (pair.ring_u[j8] - u0) / s_body[j8]
    s_new, s, prev = [], s_body[anchor], centers[anchor]
    for ring in new_rings:
        c_ = center([q[0] for q in ring.values()])
        s += math.dist(c_, prev)
        prev = c_
        s_new.append(s)
    uv_anchor = pair.ring_u[anchor]
    end_raw = uv_anchor + dens * (s_new[-1] - s_body[anchor])
    scale = min(1.0, (uv_max - u0) / (end_raw - u0))
    sq = lambda x: u0 + (x - u0) * scale

    # буфер вершин: исходные (у колец крюка до якоря — новый UV-u; кольца после якоря больше не используются)
    vb = []
    ring_of = {i: k for k, rr in enumerate(pair.rings) for i in rr.values()}
    for i in range(tp.nv):
        raw = tp.vertex_raw(i)
        if i in ring_of and ring_of[i] <= anchor:
            raw = tp.pack_vertex(raw, uv=(sq(tp.uv[i][0]), tp.uv[i][1]))
        vb.append(raw)
    base = pair.rings[j8]
    ring_ids = [dict(pair.rings[anchor])]
    apos = {}                                                       # позиции новых вершин в пространстве разбора
    for sv, ring in zip(s_new, new_rings):
        uu = sq(uv_anchor + dens * (sv - s_body[anchor]))
        ids = {}
        for r, (pos, nrm, tan) in ring.items():
            vb.append(tp.pack_vertex(tp.vertex_raw(base[r]), pos=out_p(pos), nrm=out_n(nrm), tan=out_t(tan),
                                     uv=(uu, tp.uv[base[r]][1])))
            ids[r] = len(vb) - 1
            apos[len(vb) - 1] = pos
        ring_ids.append(ids)
    # треугольники: исходные, кроме отрезков после якоря; новые отрезки — по узору отрезка тела; торец
    drop = set()
    for j in range(anchor, j8):
        vs = set(pair.rings[j].values()) | set(pair.rings[j + 1].values())
        for t in tp.tris:
            if all(i in vs for i in t) and any(i in set(pair.rings[j + 1].values()) for i in t):
                drop.add(t)
    tris = [t for t in tp.tris if t not in drop]
    n_old = len(tris)
    for a, b in zip(ring_ids[:-1], ring_ids[1:]):
        for t in pattern:
            tris.append(tuple((a, b)[k][r] for k, r in t))
    order = sorted(roles, key=lambda r: tp.uv[base[r]][1])
    loop, seen = [], set()
    for r in order:
        key = tuple(tp.pos[base[r]])
        if key not in seen:
            seen.add(key)
            loop.append(r)
    half = len(loop) // 2
    end = ring_ids[-1]
    uv_end = sq(uv_anchor + dens * (s_new[-1] - s_body[anchor]))
    cap = {}
    for k, r in enumerate(loop):
        side_role = loop[half - 1] if k < half else loop[half]       # UV нижней кромки своей стороны
        vb.append(tp.pack_vertex(vb[end[r]], nrm=out_n(pair.n), uv=(uv_end, tp.uv[base[side_role]][1])))
        cap[r] = len(vb) - 1
        apos[len(vb) - 1] = apos[end[r]]
    strip, lo, hi = [], 0, len(loop) - 1
    while lo <= hi:
        strip.append(loop[lo])
        if lo != hi:
            strip.append(loop[hi])
        lo, hi = lo + 1, hi - 1
    posv = lambda j: out_p(apos[j])                                # ориентация торца — в пространстве игры
    n_cap = out_n(pair.n)
    for k in range(len(strip) - 2):
        t = [cap[strip[k]], cap[strip[k + 1]], cap[strip[k + 2]]]
        nn = rm.v_cross(rm.v_sub(posv(t[1]), posv(t[0])), rm.v_sub(posv(t[2]), posv(t[0])))
        if rm.v_dot(nn, n_cap) < 0:
            t[0], t[1] = t[1], t[0]
        tris.append(tuple(t))
    # вырожденные (у кончика роли фаски и контура сходятся) оставлены: не рисуются, а сетка остаётся замкнутой
    # индексы: исходные полосы, если ничего не выкинуто, иначе — все треугольники заново (по одному на полосу)
    if drop:
        idx = []
        tri_list = tris
    else:
        idx = list(tp.indices)
        tri_list = tris[n_old:]
    for t in tri_list:
        if idx and idx[-1] != rm.STRIP_RESTART:
            idx.append(rm.STRIP_RESTART)
        idx += list(t)
    tape_bytes = tp.rebuilt(b''.join(vb), idx)
    st2 = rm.Mesh(st.bytes(), st.path, st.sub)
    for i in pair.island:
        st2.set_pos(i, out_p(pair.O))
    rep = {'tape_vertices': [tp.nv, len(vb)], 'tape_indices': [tp.ni, len(idx)], 'new_triangles': len(tris) - n_old,
           'rails': rails is not None, 'anchor_ring': anchor, 'rounding': list(rounding) if rounding else None,
           'radii_mm': [round(Rt * 1000, 1), round(Rb * 1000, 1)], 'blade_height_mm': round(H * 1000, 1),
           'new_rings_mm': [round(u * 1000, 2) for u in depths], 'toe_depth_mm': round(tip * 1000, 2),
           'uv_u_scale': round(scale, 4), 'uv_u_end': round(uv_end, 4), 'stick_island_vertices': len(pair.island)}
    return tape_bytes, st2.bytes(), rep


PRESCALE = {4: (1.0, 0.5, 0.5)}             # _4 = _2, растянутая по y и z вдвое (проверено: те же точки)


def prescale_mesh(m, a):
    """Позиции/нормали/касательные сетки (в памяти, не в байтах) — в пространство A = diag(a)."""
    m.pos = [[q[0] * a[0], q[1] * a[1], q[2] * a[2]] for q in m.pos]
    m.nrm = [rm.v_norm([q[0] / a[0], q[1] / a[1], q[2] / a[2]]) or q for q in m.nrm]
    m.tan = [rm.v_norm([q[0] * a[0], q[1] * a[1], q[2] * a[2]]) or q for q in m.tan]
    m.tris = list(m.tris)
    return m


def make_pair(kind, h, v):
    """Пара клюшка + лента для правки; у толстой _4 разбор и правка — в её «обычном» виде (y, z пополам), так что
    скругление носка у _4 — то же, что у _2, растянутое вместе с клюшкой."""
    rel_s, rel_t = pair_rels(kind, h, v)
    st, tp = rm.Mesh.game(rel_s), rm.Mesh.game(rel_t)
    a = PRESCALE.get(v)
    if a:
        prescale_mesh(st, a)
        prescale_mesh(tp, a)
    pair = Pair(h, v, stick=st, tape=tp, kind=kind)
    pair.prescale = a
    return pair


def vertex_pos(m, raw):
    import struct
    return [rm.half_dec(h) for h in struct.unpack_from('>3H', raw, m.e_pos.off)]


# ---------------------------------------------------------------- команды

def tape_dir():
    return os.path.join(rm.models_dir(), 'tape')


def opt(args, name, default=None):
    return rm.opt(args, name, default)


def cmd_info(args):
    for kind, h, v in pairs():
        p = Pair(h, v, kind=kind)
        print(f'{p.rel_stick} + {p.rel_tape}: колец ленты на крюке {len(p.rings)} '
              f'(UV-u {p.ring_u[0]:.3f}…{p.ring_u[-1]:.3f}), вершин в кольце {len(p.roles)}; островок носка '
              f'{len(p.island)} вершин, {len(p.isl_tris)} треугольников, глубина {p.tip * 1000:.1f} мм; '
              f'отрезок ленты — {len(p.segment_pattern())} треугольников; стык сходится до '
              f'{p.joint_gap * 1e6:.0f} мкм')


def out_dir(variant):
    return os.path.join(tape_dir(), 'out' if variant == 'none' else f'out-{variant}')


def cmd_build(args):
    variants = opt(args, '--round', ROUND_DEFAULT).split(',')
    kinds = opt(args, '--kinds', kinds_default()).split(',')
    goalie_round = rm.flag(args, '--goalie-round')
    prev = opt(args, '--preview', os.path.join(rm.models_dir(), 'preview', 'tape'))
    no_prev = rm.flag(args, '--no-preview')
    import hashlib
    for var in variants:
        out = out_dir(var)
        summary = {'variant': var, 'rounding': ROUNDS[var], 'files': {}}
        mf = os.path.join(out, 'manifest.json')
        if os.path.exists(mf):                      # сборка части видов (--kinds) — записи остальных файлов сохраняются
            try:
                old = json.load(open(mf, encoding='utf-8'))
                if old.get('variant') == var:
                    summary['files'] = {k: v_ for k, v_ in old.get('files', {}).items()
                                        if not any(k.startswith(kind_prefix(kd)) for kd in kinds)}
            except ValueError:
                pass
        for kind, h, v in pairs():
            if kind not in kinds:
                continue
            pair = make_pair(kind, h, v)
            rnd = ROUNDS[var] if (kind == 'player' or goalie_round) else None
            tb, sb, rp = build_pair(pair, rnd)
            for rel, data in ((pair.rel_tape, tb), (pair.rel_stick, sb)):
                pth = os.path.join(out, *rel.split('/'))
                os.makedirs(os.path.dirname(pth), exist_ok=True)
                open(pth, 'wb').write(data)
                summary['files'][rel] = {'sha1': hashlib.sha1(data).hexdigest(), 'size': len(data)}
            summary['files'][pair.rel_tape].update(rp)
            print(f'  [{ROUND_NAMES[var]}] {pair.rel_tape}: вершин {rp["tape_vertices"][0]} → {rp["tape_vertices"][1]}, '
                  f'новых колец {len(rp["new_rings_mm"])} (от кольца {rp["anchor_ring"]}), радиусы '
                  f'{rp["radii_mm"]} мм при высоте {rp["blade_height_mm"]}; UV-u ×{rp["uv_u_scale"]}')
        if 'dropped' in kinds and has_dropped():               # клюшка на льду — как полевые
            data, reps = build_dropped(ROUNDS[var], log=lambda s, n=ROUND_NAMES[var]: print(f'  [{n}]' + s[1:]))
            pth = os.path.join(out, *DROPPED.split('/'))
            os.makedirs(os.path.dirname(pth), exist_ok=True)
            open(pth, 'wb').write(data)
            summary['files'][DROPPED] = dict({'sha1': hashlib.sha1(data).hexdigest(), 'size': len(data)}, **reps)
        json.dump(summary, open(os.path.join(out, 'manifest.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        print(f'файлы [{ROUND_NAMES[var]}]: {out}')
    if not no_prev:
        preview([v for v in variants], prev, nhl13=not rm.flag(args, '--no-nhl13'))


def main():
    args = rm.take_game(sys.argv[1:])
    if not args:
        print(__doc__)
        return
    cmd = args.pop(0)
    if cmd == 'info':
        cmd_info(args)
    elif cmd == 'build':
        cmd_build(args)
    elif cmd == 'preview':
        preview(opt(args, '--round', ROUND_DEFAULT).split(','),
                opt(args, '--preview', os.path.join(rm.models_dir(), 'preview', 'tape')),
                nhl13=not rm.flag(args, '--no-nhl13'))
    elif cmd == 'check':
        good = True
        for var in opt(args, '--round', ROUND_DEFAULT).split(','):
            print(f'[{ROUND_NAMES[var]}] {out_dir(var)}')
            good &= check(out_dir(var), rounded=var != 'none')
        sys.exit(0 if good else 1)
    else:
        print(__doc__)
        sys.exit(2)


# ---------------------------------------------------------------- превью

class Cam:
    """Ортографическая камера по базису: right, up (единичные), центр кадра, полуширина кадра (м), размер картинки.
    Для czkit.draw_mesh: rot() — координаты в базисе камеры (z — к зрителю), screen() — пиксели и глубина."""

    def __init__(self, right, up, center, half_w, w, h):
        self.R = rm.v_norm(right)
        u = rm.v_sub(up, v_mul(self.R, rm.v_dot(up, self.R)))
        self.U = rm.v_norm(u)
        self.F = rm.v_cross(self.R, self.U)
        self.c, self.hw, self.w, self.h = center, half_w, w, h
        self.hh = half_w * h / w

    def rot(self, p):
        return rm.v_dot(p, self.R), rm.v_dot(p, self.U), rm.v_dot(p, self.F)

    def screen(self, p):
        x, y, z = self.rot(rm.v_sub(p, self.c))
        return (x + self.hw) / (2 * self.hw) * self.w, (self.hh - y) / (2 * self.hh) * self.h, z


class _MV:
    def __init__(self, m):
        self.pos, self.nrm, self.tan, self.uv, self.tris = m.pos, m.nrm, m.tan, m.uv, m.tris


PREVIEW_STICK = 50                   # текстура клюшки для картинок: Reebok 11K (тёмная, как у большинства)


def render_blade(stick, tape, cam, tape_color, stick_id=PREVIEW_STICK, bg=(64, 66, 74, 255)):
    import czkit as cz
    cv = cz.Canvas(cam.w, cam.h, bg)
    cz.draw_mesh(cv, cam, _MV(stick), rm.preview_tex(f'rendering/playerstick/texlib_{stick_id}.rx2',
                                                     f'playerstick_{stick_id}_cm'))
    cz.draw_mesh(cv, cam, _MV(tape), rm.preview_tex('rendering/playerstick/texlib_999.rx2',
                                                    f'sticktape_{tape_color}_cm'))
    return cv.img()


def blade_views(pair):
    """Виды крюка: сбоку (на лицевую и обратную стороны), сверху (на верхнюю кромку, ближе к носку), носок крупно
    сбоку и в три четверти сверху — по рамке носка пары (n — к кончику, c — вверх по высоте крюка, w — по толщине).
    Cam(right, up): к зрителю — right × up: (n, c) — на сторону −w, (−n, c) — на сторону +w, (n, w) — сверху (+c);
    c здесь — к верхней кромке (кромка на льду — внизу картинки), w = c × n."""
    if pair.up != 1:
        pair.align_to_edges()                                        # рамка вдоль кромок, c — к верхней кромке
    n = pair.n
    c = v_mul(pair.c, pair.up)                                       # вверх — к верхней кромке (не к льду)
    w = rm.v_cross(c, n)
    tp = pair.tape
    P = [tp.pos[i] for i in pair.blade]
    cen = [sum(p[k] for p in P) / len(P) for k in range(3)]
    span = max(math.dist(p, cen) for p in P)
    toe = v_add(pair.O, v_mul(n, pair.tip * 0.4))
    top_c = lerp(cen, toe, 0.55)
    obl = rm.v_norm(v_add(v_mul(c, 0.55), v_mul(w, -0.85)))          # сверху и спереди (сторона −w)
    return [('сбоку', Cam(n, c, cen, span * 1.12, 300, 200)),
            ('сбоку, обратная сторона', Cam(v_mul(n, -1), c, cen, span * 1.12, 300, 200)),
            ('сверху', Cam(n, w, top_c, span * 0.8, 300, 110)),
            ('носок крупно', Cam(n, c, toe, pair.tip * 2.6, 200, 200)),
            ('носок, три четверти сверху', Cam(n, rm.v_cross(obl, n), toe, pair.tip * 2.6, 200, 200))]


def _silhouette(stick, tape, cam):
    import czkit as cz
    cv = cz.Canvas(cam.w, cam.h, (0, 0, 0, 255))
    cz.draw_mesh(cv, cam, _MV(stick), color=(255, 0, 0), flat=1.0)
    cz.draw_mesh(cv, cam, _MV(tape), color=(255, 0, 0), flat=1.0)
    m = bytearray(1 if cv.z[i] > -1e9 else 0 for i in range(cam.w * cam.h))
    w, h = cam.w, cam.h
    return [(x, y) for y in range(1, h - 1) for x in range(1, w - 1)
            if m[y * w + x] and not (m[y * w + x - 1] and m[y * w + x + 1] and m[(y - 1) * w + x] and m[(y + 1) * w + x])]


PREVIEW_VIEWS = ('сбоку', 'сверху', 'носок крупно')


def load_pair(outdir, pair):
    return (rm.Mesh.load(os.path.join(outdir, *pair.rel_stick.split('/'))),
            rm.Mesh.load(os.path.join(outdir, *pair.rel_tape.split('/'))))


def preview(variants, prevdir, log=print, nhl13=True):
    """Лист prevdir/sheet.png: для обычной (_2) и толстой (_4) клюшки левого хвата, белой и чёрной ленты — виды
    «сбоку», «сверху», «носок крупно»: исходная, затем варианты variants (ключи ROUNDS: none, strong, bottom1, …);
    красный контур — силуэт исходной. Картинки — prevdir/tape_<V>_<цвет>_<вид>_<вариант>.png. У другой игры (Legacy)
    с nhl13 — ещё колонки «NHL 13 с модом»: готовые файлы NHL 13 (game/work/models/tape/out-<вариант>) с текстурами
    NHL 13 (tape_<V>_<цвет>_<вид>_nhl13_<вариант>.png)."""
    import base64
    import teamart as ta
    os.makedirs(prevdir, exist_ok=True)
    other = not rm.is_nhl13()
    gname = rm.PROFILE.title
    cards = []
    for v in (2, 4):
        pair = Pair(0, v)
        cams = dict(blade_views(pair))
        built = {var: load_pair(out_dir(var), pair) for var in variants}
        b13 = {}
        if other and nhl13:
            for var in variants:
                d13 = os.path.join(rm.nhl13_models_dir(), 'tape', 'out' if var == 'none' else f'out-{var}')
                if os.path.exists(os.path.join(d13, *pair.rel_tape.split('/'))):
                    b13[var] = load_pair(d13, pair)
        edges = {vn: _silhouette(pair.stick, pair.tape, cams[vn]) for vn in PREVIEW_VIEWS}
        for color, cname in ((1, 'белая'), (0, 'чёрная')):
            rows = []
            for k, vn in enumerate(PREVIEW_VIEWS):
                cam = cams[vn]
                cells = []
                for var in ['orig'] + list(variants) + [('nhl13', x) for x in b13]:
                    if isinstance(var, tuple):                # NHL 13 с модом — сетки и текстуры NHL 13
                        with rm.game_profile('nhl13'):
                            img = render_blade(*b13[var[1]], cam, color)
                    else:
                        s_, t_ = (pair.stick, pair.tape) if var == 'orig' else built[var]
                        img = render_blade(s_, t_, cam, color)
                    if var != 'orig':
                        for x, y in edges[vn]:
                            o = (y * img.w + x) * 4
                            img.px[o:o + 4] = bytes((255, 60, 60, 255))
                    tag = f'nhl13_{var[1]}' if isinstance(var, tuple) else var
                    fn = f'tape_{v}_{color}_{k}_{tag}.png'
                    img.save(os.path.join(prevdir, fn))
                    if not other:
                        lab = 'до' if var == 'orig' else ROUND_NAMES[var]
                    elif isinstance(var, tuple):
                        lab = f'NHL 13 с модом ({ROUND_NAMES[var[1]]})'
                    else:
                        lab = f'{gname}, оригинал' if var == 'orig' else f'{gname} с модом ({ROUND_NAMES[var]})'
                    cells.append((fn, lab, cam.w, cam.h))
                rows.append((vn, cells))
            cards.append((f'клюшка _{v} ({"обычная" if v == 2 else "толстая: вдвое толще и длиннее по крюку"}), '
                          f'лента {cname}', rows))
            log(f'  превью: _{v}, лента {cname}')
    if other and has_dropped():                       # клюшка на льду (реквизит, у NHL 13 его нет) — правая
        pair = dropped_pair(rm.source(DROPPED), 'right')
        cams = dict(blade_views(pair))
        built = {}
        for var in variants:
            p = os.path.join(out_dir(var), *DROPPED.split('/'))
            if os.path.exists(p):
                data = open(p, 'rb').read()
                built[var] = (rm.Mesh(data, DROPPED, sub=pair.subs['shaft']),
                              rm.Mesh(data, DROPPED, sub=pair.subs['heel_tape']))
        edges = {vn: _silhouette(pair.stick, pair.tape, cams[vn]) for vn in PREVIEW_VIEWS}
        for color, cname in ((1, 'белая'), (0, 'чёрная')):
            rows = []
            for k, vn in enumerate(PREVIEW_VIEWS):
                cam = cams[vn]
                cells = []
                for var in ['orig'] + [x for x in variants if x in built]:
                    s_, t_ = (pair.stick, pair.tape) if var == 'orig' else built[var]
                    img = render_blade(s_, t_, cam, color)
                    if var != 'orig':
                        for x, y in edges[vn]:
                            o = (y * img.w + x) * 4
                            img.px[o:o + 4] = bytes((255, 60, 60, 255))
                    fn = f'tape_dropped_{color}_{k}_{var}.png'
                    img.save(os.path.join(prevdir, fn))
                    cells.append((fn, f'{gname}, оригинал' if var == 'orig' else f'{gname} с модом ({ROUND_NAMES[var]})',
                                  cam.w, cam.h))
                rows.append((vn, cells))
            cards.append((f'клюшка на льду {DROPPED} (реквизит, у NHL 13 его нет; правая), лента {cname}', rows))
            log(f'  превью: клюшка на льду, лента {cname}')

    def uri(fn):
        return 'data:image/png;base64,' + base64.b64encode(open(os.path.join(prevdir, fn), 'rb').read()).decode()
    body = []
    for title, rows in cards:
        rr = []
        for vn, cells in rows:
            figs = ''.join(f'<figure><img src="{uri(fn)}" width="{w}" height="{h}"><figcaption>{lab}</figcaption>'
                           f'</figure>' for fn, lab, w, h in cells)
            rr.append(f'<div class="vrow"><div class="vn">{vn}</div>{figs}</div>')
        body.append(f'<div class="card"><h2>{title}</h2>{"".join(rr)}</div>')
    def radii(v):
        r = ROUNDS.get(v)
        if not r:
            return ''
        h2 = 74.7                                                    # высота крюка _2 у носка, мм (см. manifest)
        return f' (верх {r[0] * h2:.0f} мм, низ {r[1] * h2:.0f} мм у _2)'
    names = ', '.join(f'«{ROUND_NAMES[v]}»{radii(v)}' for v in variants)
    html = ('<!doctype html><html><head><meta charset="utf-8"><style>'
            'body{margin:0;background:#26272c;color:#ddd;font:13px Segoe UI,Arial,sans-serif;padding:12px;width:1456px}'
            'h1{font-size:18px;margin:0 0 4px}h2{font-size:14px;margin:0 0 6px}'
            '.card{background:#303138;padding:8px;border-radius:6px;margin-bottom:10px}'
            '.vrow{display:flex;gap:6px;align-items:flex-end;margin-bottom:4px}'
            '.vn{width:86px;font-size:12px;color:#ccc;align-self:center}figure{margin:0}'
            'figcaption{font-size:11px;color:#aaa;text-align:center}p{margin:4px 0 8px;color:#bbb}'
            '</style></head><body><h1>Обмотка крюка: лента до носка и скругление носка'
            + (f' — {gname}' if other else '') + '</h1>'
            f'<p>Варианты: {names}. Красный контур — силуэт исходного крюка. Клюшка с текстурой '
            + ('Reebok 11K (texlib_50)' if not other else f'texlib_{PREVIEW_STICK} своей игры')
            + '; геометрия у всех клюшек одна, «модели» — только текстуры; правый хват — зеркало левого. '
            'Пятка, высота и длина крюка до скругления не менялись.</p>' + ''.join(body) + '</body></html>')
    sheet = os.path.join(prevdir, 'sheet.png')
    ta.render_html(html, sheet, 1480, 80 + len(cards) * 625)
    log(f'  лист: {sheet}')


# ---------------------------------------------------------------- проверка собранного

def boundary_loops(m, verts):
    """Число граничных рёбер (по сварке) у куска сетки из вершин verts."""
    w = rm.Weld(m)
    vs = set(verts)
    cnt = {}
    for t in m.tris:
        if not all(i in vs for i in t):
            continue
        g = [w.group[i] for i in t]
        if len(set(g)) < 3:
            continue
        for a, b in ((g[0], g[1]), (g[1], g[2]), (g[2], g[0])):
            k = (min(a, b), max(a, b))
            cnt[k] = cnt.get(k, 0) + 1
    return sum(1 for c in cnt.values() if c == 1)


def _tri_key(t):
    a, b, c = t
    return min((a, b, c), (b, c, a), (c, a, b))


def _outline_overshoot(pair, nt, first_new, anchor):
    """Насколько новые вершины ленты выходят за исходный контур крюка у носка в плоскости крюка (u, v), мм: контур —
    выпуклая оболочка исходных точек от якорного кольца до кончика (тело ленты и островок носка клюшки)."""
    tp, st = pair.tape, pair.stick
    pts = [pair.local(tp.pos[i])[:2] for j in range(anchor, len(pair.rings)) for i in pair.rings[j].values()]
    pts += [pair.local(st.pos[i])[:2] for i in pair.island]
    P = sorted(set((round(u, 6), round(v, 6)) for u, v in pts))

    def crs(o, a_, b_):
        return (a_[0] - o[0]) * (b_[1] - o[1]) - (a_[1] - o[1]) * (b_[0] - o[0])
    lo, hi = [], []
    for q in P:
        while len(lo) >= 2 and crs(lo[-2], lo[-1], q) <= 0:
            lo.pop()
        lo.append(q)
    for q in reversed(P):
        while len(hi) >= 2 and crs(hi[-2], hi[-1], q) <= 0:
            hi.pop()
        hi.append(q)
    hull = lo[:-1] + hi[:-1]
    u_min = min(u for u, _ in hull)
    worst = 0.0
    for i in range(first_new, nt.nv):
        u, v, _ = pair.local(nt.pos[i])
        if u < u_min:
            continue
        out = max(crs(a_, b_, (u, v)) / math.hypot(b_[0] - a_[0], b_[1] - a_[1]) * -1
                  for a_, b_ in zip(hull, hull[1:] + hull[:1]) if (a_ != b_))
        worst = max(worst, out)
    return max(0.0, worst) * 1000


def check(out, rounded=False, log=print):
    """Собранные файлы: разбор и перекодирование байт в байт; у ленты исходные вершины — как были (у колец крюка до
    якоря — кроме UV-u; кольца после якоря больше не используются), исходные треугольники — все, кроме отрезков после
    якоря, новые — не перевёрнуты, у крюка не осталось открытого края у носка (только стык у пятки); новые вершины не
    выходят за исходный контур носка; у клюшки изменены только позиции вершин островка носка (стянуты в точку)."""
    ok = True
    for kind, h, v in pairs():
        pair = Pair(h, v, kind=kind)
        rel_t, rel_s = pair.rel_tape, pair.rel_stick
        if not os.path.exists(os.path.join(out, *rel_t.split('/'))):
            continue
        nt = rm.Mesh.load(os.path.join(out, *rel_t.split('/')))
        ns = rm.Mesh.load(os.path.join(out, *rel_s.split('/')))
        man = json.load(open(os.path.join(out, 'manifest.json'), encoding='utf-8'))['files'].get(rel_t, {})
        anchor = man.get('anchor_ring', len(pair.rings) - 2)
        good, line = check_pair(pair, nt, ns, anchor, rel_t, rel_s)
        ok &= good
        log(line)
    if not rm.is_nhl13() and os.path.exists(os.path.join(out, *DROPPED.split('/'))):
        ok &= check_dropped(out, log)
    log('  итог: ' + ('всё в порядке' if ok else 'есть замечания'))
    return ok


def check_pair(pair, nt, ns, anchor, rel_t, rel_s):
    """Проверки одной пары (см. check): nt, ns — собранные лента и клюшка. → (всё ли в порядке, строка отчёта)."""
    msgs = []
    for m in (nt, ns):
        if rm.reencode_check(m) or not m.layout_ok():
            msgs.append(f'{m.path}: не перекодируется байт в байт')
    tp, st = pair.tape, pair.stick
    ring_of = {i: k for k, rr in enumerate(pair.rings) for i in rr.values()}
    for i in range(tp.nv):
        same = (nt.pos[i] == tp.pos[i] and nt.nrm[i] == tp.nrm[i] and nt.bones[i:i + 1] == tp.bones[i:i + 1]
                and nt.weights[i:i + 1] == tp.weights[i:i + 1] and abs(nt.uv[i][1] - tp.uv[i][1]) < 1e-9)
        if not same or (i not in ring_of and nt.uv[i] != tp.uv[i]):
            msgs.append(f'лента: вершина {i} изменилась')
            break
    used = set(i for t in nt.tris for i in t)
    orphan = [i for i, k in ring_of.items() if k > anchor]
    if any(i in used for i in orphan):
        msgs.append('лента: кольца после якоря всё ещё в треугольниках')
    dropped = [t for t in tp.tris if all(i in ring_of and ring_of[i] >= anchor for i in t)
               and any(ring_of[i] > anchor for i in t)]
    keep = {_tri_key(t) for t in tp.tris} - {_tri_key(t) for t in dropped}
    have = {_tri_key(t) for t in nt.tris}
    if not keep <= have:
        msgs.append(f'лента: пропало {len(keep - have)} исходных треугольников')
    new_tris = [t for t in nt.tris if _tri_key(t) not in keep]
    flipped = 0                                   # перевёрнутые: грань смотрит против нормалей своих вершин
    for t in new_tris:
        a_, b_, c_ = (nt.pos[i] for i in t)
        fn = rm.v_cross(rm.v_sub(b_, a_), rm.v_sub(c_, a_))
        if rm.v_dot(fn, fn) > 1e-14 and rm.v_dot(fn, [sum(nt.nrm[i][k] for i in t) for k in range(3)]) <= 0:
            flipped += 1
    if flipped:
        msgs.append(f'лента: перевёрнутых треугольников {flipped}')
    blade_new = [i for i in pair.blade if i not in orphan] + list(range(tp.nv, nt.nv))
    b1 = boundary_loops(nt, blade_new)
    heel = len(pair.segment_pattern()) // 2
    if b1 != heel:
        msgs.append(f'лента: открытых рёбер у крюка {b1} (ожидалось {heel} — только стык у пятки)')
    over = _outline_overshoot(pair, nt, tp.nv, anchor)
    if over > 0.6:
        msgs.append(f'лента: выходит за исходный контур носка на {over:.2f} мм')
    isl = set(pair.island)
    for i in range(st.nv):
        if i in isl:
            if math.dist(ns.pos[i], pair.O) > 1e-3:
                msgs.append(f'клюшка: вершина носка {i} не стянута')
                break
        elif ns.vertex_raw(i) != st.vertex_raw(i):
            msgs.append(f'клюшка: вершина {i} вне носка изменилась')
            break
    if ns.indices != st.indices:
        msgs.append('клюшка: индексы изменились')
    return not msgs, (f'  {rel_t}: вершин {tp.nv} → {nt.nv}, треугольников {len(tp.tris)} → {len(nt.tris)} '
                      f'(новых {len(new_tris)}, перевёрнутых {flipped}); у крюка открыт только стык у пятки: '
                      f'{"да" if b1 == heel else "нет"}; '
                      f'за исходный контур — {over:.2f} мм; {rel_s}: стянуто {len(isl)} вершин носка'
                      + ('' if not msgs else ' — ' + '; '.join(msgs)))


if __name__ == '__main__':
    main()
