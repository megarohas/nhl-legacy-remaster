"""Рот головы-скана в NHL Legacy: суставы челюсти и губ, зубы не сквозь губы (03.11.2026, docs/heads-nhl24.md, «Рот»).

Пользователь 03.11.2026: у Сергачёва «челюсть залезает через кожу (верхняя)», у Бертуцци — «зубы». Причина общая для голов
NHL 24 и NHL 27 (scans24.py build):

1. Суставы челюсти и губ (16–22, 27–33, 42–47) в позе привязки файла головы сдвигались вслед за вершинами (как до v5 у век).
   Игра берёт переносы суставов общего скелета, а InvBind — из файла (game_pose), поэтому вершина на сдвинутом суставе в
   покое уезжает на J_общий − J_файла: губы теряли среднее смещение скана и возвращались туда, где губы шаблона, а верхние
   зубы (в основном на кости головы 8, она не сдвигается) оставались по скану — зубы подходили к губе и выходили сквозь неё.
   Правило: суставы рта — как в общем скелете (MOUTH_BONES, как веки EYE_BONES с v5): в покое игры рот — ровно рот скана
   (губы сомкнуты, зубы за губами, как в NHL 24/27); челюсть в анимации поворачивается вокруг сустава общего скелета.
   Проба «суставы рта шаблона EA» (m1/m2: рот шаблона + смещение скана, «приоткрыт», как у EA) отвергнута 03.11: у
   Сергачёва между губ виднелись зубы с тёмными щелями, на 60° — красная изнанка губы.
2. У части сканов (NHL 27 чаще) верхние зубы в самом источнике стоят вплотную к губе, и в позе игры край зуба выходит
   сквозь губу (Бертуцци — на 2 мм). Правило: если вершина зубов (острова развёртки рта TEETH) в позе игры снаружи кожи
   (луч +z до кожи head; зуб в щели рта, где впереди кожи нет, не считается) — весь рот
   (mouthbag) сдвигается назад по z на выступ + MARGIN, у края рта (вершины, совпавшие с кожей губ) — без сдвига, переход —
   RIM_FADE. У сканов EA край зуба касается изнанки губы (минимум зазора — медиана 0,15 мм), поэтому MARGIN мал: правило
   убирает только проход сквозь губу, а не «прячет» зубы.

  check_head(P, inv, J) -> {'upper', 'lower': мин. зазор, мм; '<зуб>_out': насколько зуб снаружи кожи, мм; 'outside'}
  fit_teeth(P, inv, J) -> (новые позиции mouthbag в файле, отчёт)
"""
import numpy as np

RULE = 'm3'                       # версия правила (часть ключа кэша сборки головы в scans24.py)
# Суставы рта: челюсть 16, губы и углы рта 17–22, 27–33, 42–47 (scans24.EYE_BONES — веки и брови, их не трогаем).
MOUTH_BONES = tuple(range(16, 23)) + tuple(range(27, 34)) + tuple(range(42, 48))
# Острова развёртки зубов у всех голов Legacy (развёртка одна): верхние — u 0,13–0,40, нижние — u 0,60–0,87, v > 0,95.
TEETH = {'upper': (0.13, 0.40), 'lower': (0.60, 0.87)}
TEETH_V = 0.945
MARGIN = 0.0005                   # м: вершина зуба за кожей губы не ближе (замер 03.11.2026 по 445 сканам EA в покое игры:
#                                   минимум зазора — медиана 0,15 мм; сквозь губу > 0,5 мм — у 29, у NHL 27 до правила — у 44
#                                   из 319); полмиллиметра — запас на half-float позиций (шаг ~1 мм на высоте 1,8 м)
MAX_SHIFT = 0.006                 # м: больше не сдвигать (зуб далеко снаружи — значит, не тот случай, в отчёте)
FRONT = 0.030                     # м: кожа впереди зуба дальше — это не губа (зуб в щели рта, а впереди воздух)
BACK = 0.012                      # м: зуб снаружи кожи, если кожа позади него ближе этого и впереди её нет
RIM = 0.0005                      # м: вершина рта совпадает с кожей — край рта (шов с губой), не двигается
RIM_FADE = 0.006                  # м: от края рта сдвиг растёт до полного


def teeth_mask(uv):
    """{'upper'|'lower': маска вершин mouthbag} по островам развёртки."""
    return {k: (uv[:, 0] >= a) & (uv[:, 0] <= b) & (uv[:, 1] > TEETH_V) for k, (a, b) in TEETH.items()}


def _z_hits(pts, pos, tri):
    """Для каждой точки — z кожи (треугольники pos/tri) на её вертикали по оси z: список массивов z пересечений."""
    a, b, c = pos[tri[:, 0]], pos[tri[:, 1]], pos[tri[:, 2]]
    lo = np.minimum(np.minimum(a, b), c)[:, :2]
    hi = np.maximum(np.maximum(a, b), c)[:, :2]
    den = (b[:, 1] - c[:, 1]) * (a[:, 0] - c[:, 0]) + (c[:, 0] - b[:, 0]) * (a[:, 1] - c[:, 1])
    ok = np.abs(den) > 1e-14
    out = []
    for p in pts:
        k = ok & (lo[:, 0] <= p[0]) & (hi[:, 0] >= p[0]) & (lo[:, 1] <= p[1]) & (hi[:, 1] >= p[1])
        if not k.any():
            out.append(np.zeros(0))
            continue
        A, B, C, D = a[k], b[k], c[k], den[k]
        l0 = ((B[:, 1] - C[:, 1]) * (p[0] - C[:, 0]) + (C[:, 0] - B[:, 0]) * (p[1] - C[:, 1])) / D
        l1 = ((C[:, 1] - A[:, 1]) * (p[0] - C[:, 0]) + (A[:, 0] - C[:, 0]) * (p[1] - C[:, 1])) / D
        l2 = 1 - l0 - l1
        m = (l0 >= 0) & (l1 >= 0) & (l2 >= 0)
        out.append(l0[m] * A[m, 2] + l1[m] * B[m, 2] + l2[m] * C[m, 2])
    return out


def clearance(teeth, skin_pos, skin_tri):
    """Зазор каждой вершины зуба до кожи впереди (м): > 0 — за губой, < 0 — снаружи кожи, nan — в щели рта (впереди и
    сразу позади кожи нет)."""
    out = np.full(len(teeth), np.nan)
    for i, (p, zs) in enumerate(zip(teeth, _z_hits(teeth, skin_pos, skin_tri))):
        fr = zs[(zs > p[2]) & (zs - p[2] < FRONT)] - p[2]
        if len(fr):
            out[i] = fr.min()
            continue
        bk = p[2] - zs[(zs <= p[2]) & (p[2] - zs < BACK)]
        if len(bk):
            out[i] = -bk.min()
    return out


def game_pos(part, pos, inv, skel_joints):
    """Позиции части в позе игры: вершина + Σ w·(J_общий − J_файла) (scans24.game_pose, без повторного чтения скелета)."""
    jf = np.array([-(m[3, :3] @ np.linalg.inv(m[:3, :3])) for m in inv])
    d = skel_joints - jf
    return pos + (d[part['bones']] * part['w'][..., None]).sum(1)


def check_head(P, inv, skel_joints, mb_pos=None):
    """Зазор зубов до губ в позе игры: {'upper', 'lower'} — минимум по вершинам зуба (мм, None — зуб весь в щели),
    'outside' — вершин зубов снаружи кожи. mb_pos — другие позиции mouthbag (проверка до записи)."""
    mb = P['mouthbag']
    hp = game_pos(P['head'], P['head']['pos'], inv, skel_joints)
    mp = game_pos(mb, mb['pos'] if mb_pos is None else mb_pos, inv, skel_joints)
    rep, out = {}, 0
    for k, m in teeth_mask(mb['uv']).items():
        c = clearance(mp[m], hp, P['head']['tri'])
        good = c[~np.isnan(c)]
        rep[k] = round(float(good.min()) * 1000, 2) if len(good) else None
        rep[k + '_p25'] = round(float(np.percentile(good, 25)) * 1000, 2) if len(good) else None
        rep[k + '_out'] = round(float(max(0.0, -good.min())) * 1000, 2) if len(good) else 0.0
        out += int((good < 0).sum())
    rep['outside'] = out
    return rep


def fit_teeth(P, inv, skel_joints):
    """Сдвиг рта назад, если зубы ближе MARGIN к губе (поза игры). -> (позиции mouthbag в файле, отчёт)."""
    from scipy.spatial import cKDTree
    mb = P['mouthbag']

    def deficit(r):
        # только проход сквозь губу (зазор < 0): край зуба у изнанки губы (0…MARGIN) — как у сканов EA, не трогаем
        gaps = [v for k, v in r.items() if k in TEETH and v is not None]
        worst = min(gaps, default=0.0)
        return (MARGIN * 1000 - worst) / 1000 if worst < 0 else 0.0

    before = check_head(P, inv, skel_joints)
    rep = {'rule': RULE, 'before_mm': before, 'shift_mm': 0.0}
    need = deficit(before)
    if need <= 0:
        rep['after_mm'] = before
        return mb['pos'], rep
    d, _ = cKDTree(P['head']['pos']).query(mb['pos'])
    rim = np.clip((d - RIM) / RIM_FADE, 0, 1)
    w = rim * rim * (3 - 2 * rim)
    new, total, after = mb['pos'].copy(), 0.0, before
    for _ in range(4):                  # у края рта сдвиг неполный — добираем, пока зазор не наберётся
        step = min(need, MAX_SHIFT - total)
        if step <= 1e-5:
            break
        new[:, 2] -= step * w
        total += step
        after = check_head(P, inv, skel_joints, new)
        need = deficit(after)
        if need <= 1e-5:
            break
    rep['shift_mm'] = round(total * 1000, 2)
    rep['after_mm'] = after
    return new, rep
