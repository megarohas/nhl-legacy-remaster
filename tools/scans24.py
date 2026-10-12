"""Сканы голов NHL 24 → NHL Legacy игрокам с типовой головой (этап scans24; docs/heads-nhl24.md).

Голова-скан Legacy — rendering/player/player_<headid>.rx2 (сетка) + texlib_<headid>.rx2 (head_<id>_cm 512² DXT1,
hair_<id>_cm 256² DXT3). У сканов EA headid = artid = ID EA. Сетка у NHL 24 и Legacy одна (head 2623 + mouthbag 534 =
mat_head NHL 24 3157), вершины сопоставляются 1:1 по UV. Сканы EA в Legacy (у кого headid < 60000 и файл в архиве) не
трогаются — только игроки с типовой головой (60000+), у которых в NHL 24 есть скан (licensed/<папка>).

Сборка одной головы (как пилот Cale Makar 12.10.2026, проверен пользователем в игре):
  * шаблон — скан EA Legacy с тем же числом цифр в номере (растры переименовываются на месте), ближайший по форме головы
    к NHL 24, без прядей (eyel, eyer, haircap, head, mouthbag);
  * head + mouthbag — позиции NHL 24 (низ шеи y < 1,60 — шаблона, переход до 1,66); нормали и касательные шаблона
    поворачиваются вслед за поверхностью; кости, веса, UV, индексы — шаблона;
  * глаза шаблона — сдвиг вместе с веками; haircap — полем смещений головы, высота над скальпом — по прядям NHL 24, не
    больше шаблонной + 4 мм и не больше 12 мм (место под шлемом);
  * поза привязки файла: лицевые суставы шаблона (отличные от общего скелета) — сдвиг по весам кожи;
  * head_<id>_cm — цвет NHL 24 1024 → 512; hair_<id>_cm — пряди NHL 24, запечённые на развёртку haircap.
База: headid игрока → ID EA; stockplayerheads (есть у каждой головы игрока, упорядочена по headid) — строка новой головы
на место строки-донора (голова без файла модели, которой никто не пользуется), число строк не меняется ни в базе, ни в
сейве (иначе старый ROSTER «damaged»). stockplayerhelmetplacement не трогается (шлем по умолчанию, как у шаблона Макара).

  python tools/scans24.py match            # → <work>/scans24/match-<вариант>.json: ok / спорные / конфликты
  python tools/scans24.py build [--jobs 6] [--disputed]   # → <work>/scans24/cache/<id>/, ok → out/rendering/player/
  python tools/scans24.py apply            # headid + stockplayerheads в out/db и out-ahl32/db, draft_roster.db заново
  python tools/scans24.py save СЕЙВ [--write] [--variant out-ahl32]   # то же в сейве ROSTER (копия, проверка CRC)
  python tools/scans24.py sheet [--n 60]   # лист «типовая сейчас | NHL 24 | наш» (+ спорные, + 5 в шлеме)

<work> — game/work/legacy-data (LEGACY_DATA_WORK). Нужен питон с numpy, scipy, Pillow (PHOTOS24_PYTHON) и дамп NHL 24 с
каталогом (tools/fb). Повтор ничего не меняет (кэш голов по версии сборки, apply/save — по applied-<вариант>.json).
Ассеты NHL 24 и собранные головы — только для личного использования, вне git.
"""
import argparse
import hashlib
import json
import os
import random
import re
import shutil
import struct
import subprocess
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor

import numpy as np

TOOLS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TOOLS)
os.environ.setdefault('NHL_GAME', 'legacy')
import photos24 as P24  # noqa: E402
import rw4mesh as R  # noqa: E402
from tdb import Tdb, SaveFile  # noqa: E402
from tdb_read import load_meta  # noqa: E402

G = P24.G
VARIANTS = P24.VARIANTS
VERSION = 3                                   # версия сборки головы (кэш); 2 — карта вершин шаблона, UV; 3 — поза
EA_PLAYER = os.path.join(G.big, 'cacherender', 'rendering', 'player')
COMMON = os.path.join(G.big, 'renderboot', 'rendering', 'player_common', 'texlib_999.rx2')
BIO, HEADS, PLACE = 'exhibitionplayerbiotable', 'stockplayerheads', 'stockplayerhelmetplacement'
TYPICAL = 60000
NECK = (1.60, 1.66)                           # низ шеи — от шаблона (у сканов EA общий), переход
CAP_ADD, CAP_MAX, CAP_MIN = 0.004, 0.012, 0.0015
POSE_DEG, POSE_MM = 2.5, 6.0                  # голова NHL 24 в другой позе (наклон/сдвиг черепа) — выровнять
ROW_TEMPLATE = 11145                          # строка stockplayerheads образец (haircards_a/b = 0)
# пилот 12.10.2026: в out-ahl32 Макар поставлен makar_db.py до этапа (headid 60112 → 20185) — прежняя голова для сейва
PILOT_OLD = {('cale', 'makar', (1998, 10, 30)): 60112}
NICK = [('alex', 'alexander'), ('alex', 'aleksander'), ('alex', 'alexandre'), ('mitch', 'mitchell'), ('nick', 'nicholas'),
        ('nick', 'nicolas'), ('matt', 'matthew'), ('mike', 'michael'), ('josh', 'joshua'), ('zach', 'zachary'),
        ('zack', 'zachary'), ('jake', 'jacob'), ('chris', 'christopher'), ('tony', 'anthony'), ('dan', 'daniel'),
        ('danny', 'daniel'), ('sam', 'samuel'), ('max', 'maxim'), ('max', 'maxime'), ('tim', 'timothy'),
        ('will', 'william'), ('tom', 'thomas'), ('ben', 'benjamin'), ('joe', 'joseph'), ('jon', 'jonathan'),
        ('fred', 'frederik'), ('freddie', 'frederik'), ('pat', 'patrick'), ('evgeni', 'evgeny'), ('nikita', 'nikita'),
        ('artemi', 'artemiy'), ('yegor', 'egor'), ('ilya', 'ilia'), ('dmitri', 'dmitry'), ('gabe', 'gabriel')]


def lev(a, b):
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def work():
    return os.path.join(P24.work(), 'scans24')


def norm(s):
    return P24.norm(s)


def first_ok(a, b):
    """Имена совместимы: равны, одно начало другого (≥ 3 буквы) или пара из NICK."""
    if a == b:
        return True
    if min(len(a), len(b)) >= 3 and (a.startswith(b) or b.startswith(a)):
        return True
    if min(len(a), len(b)) >= 5 and lev(a, b) <= 2:            # опечатки в именах папок EA (phillipe_myers)
        return True
    return (a, b) in NICK or (b, a) in NICK


# ------------------------------------------------------------------ NHL 24: игроки со сканом и их папки

def nhl24_scans():
    """{индекс игрока NHL 24: папка} для игроков базы NHL 24 со сканом (headid < 60000); спорные папки — отдельно."""
    from fb import heads
    players = P24.nhl24_players()
    folders = heads.licensed_folders()
    flat = {re.sub(r'[^a-z]', '', f): f for f in folders}
    scans = [i for i, p in enumerate(players) if p['headid'] < TYPICAL]
    got, taken, unsure = {}, defaultdict(list), []
    for i in scans:
        p = players[i]
        f = flat.get(norm(p['first']) + norm(p['last']))
        if f:
            got[i] = f
            taken[f].append(i)
    for i in scans:
        if i in got:
            continue
        p = players[i]
        nl, nf = norm(p['last']), norm(p['first'])
        cand = []
        for fl, f in flat.items():
            if f in taken or not fl.endswith(nl) or len(fl) == len(nl):
                continue
            if first_ok(nf, fl[:-len(nl)]):
                cand.append(f)
        if len(cand) == 1:
            got[i] = cand[0]
            taken[cand[0]].append(i)
        elif cand:
            unsure.append((i, cand))
    for f, ii in taken.items():                     # папка у двух игроков — обоим спорно
        if len(ii) > 1:
            for i in ii:
                unsure.append((i, [f]))
                got.pop(i, None)
    return players, got, unsure


def ea_head_files():
    return {int(x[7:-4]) for x in os.listdir(EA_PLAYER) if x.startswith('player_') and x[7:-4].isdigit()}


def cmd_match(variants):
    players, folder_of, unsure_f = nhl24_scans()
    unsure_idx = {i: c for i, c in unsure_f}
    by_art, by_key, by_lb, by_name = defaultdict(list), defaultdict(list), defaultdict(list), defaultdict(list)
    for i, p in enumerate(players):
        if p['headid'] >= TYPICAL:
            continue
        b = tuple(p['birth'])
        by_art[p['artid']].append(i)
        by_key[(norm(p['first']) + norm(p['last']), b)].append(i)
        by_lb[(norm(p['last']), b)].append(i)
        by_name[norm(p['first']) + norm(p['last'])].append(i)
    ea = ea_head_files()
    from fb import heads
    flat = {re.sub(r'[^a-z]', '', f): f for f in heads.licensed_folders()}
    folder_set_taken = set(folder_of.values())
    os.makedirs(work(), exist_ok=True)
    for v in variants:
        pl = P24.legacy_players(v)
        heads_used = defaultdict(set)
        for p in pl:
            heads_used[p['headid']].add(p['game_id'])
        ok, disp, conf, nofolder, artid_only = [], [], [], [], []
        ea_scan = 0
        for p in pl:
            h = p['headid']
            if h < TYPICAL and h in ea:
                ea_scan += 1
                continue
            b = tuple(p['birth'])
            nf, nl = norm(p['first']), norm(p['last'])
            A = [i for i in by_art.get(p['artid'], []) if norm(players[i]['last']) == nl and tuple(players[i]['birth']) == b]
            Aw = [i for i in by_art.get(p['artid'], []) if i not in A]
            B = by_key.get((nf + nl, b), [])
            C = [i for i in by_lb.get((nl, b), []) if i not in B and first_ok(nf, norm(players[i]['first']))]
            Dw = [i for i in by_lb.get((nl, b), []) if i not in B and i not in C]          # та же фамилия и дата
            Ew = [i for i in by_name.get(nf + nl, []) if tuple(players[i]['birth']) != b]  # тёзка с другой датой
            strong = sorted(set(A) | set(B) | set(C))
            rec = {'row': p['row'], 'game_id': p['game_id'], 'name': f"{p['first']} {p['last']}", 'birth': list(b),
                   'artid': p['artid'], 'old': h, 'league': p['league']}
            if len(strong) == 1:
                i = strong[0]
                q = players[i]
                how = '+'.join(k for k, s in (('artid', A), ('имя+дата', B), ('фамилия+дата+имя≈', C)) if i in s)
                rec.update(nhl24={'name': f"{q['first']} {q['last']}", 'birth': q['birth'], 'artid': q['artid'],
                                  'headid': q['headid']}, how=how)
                if i not in folder_of and i not in unsure_idx:
                    f = flat.get(nf + nl)                      # папка по имени из базы Legacy (Gabriel / Gabe)
                    if f and f not in folder_set_taken:
                        folder_of[i] = f
                        folder_set_taken.add(f)
                if i not in folder_of:
                    if i in unsure_idx:
                        rec['why'] = f'папка NHL 24 неоднозначна: {unsure_idx[i]}'
                        disp.append(rec)
                    else:
                        nofolder.append(rec)                   # скан в базе NHL 24 есть, а папки с сеткой не нашлось
                    continue
                rec['folder'] = folder_of[i]
                new = q['artid']
                rec['new'] = new
                why = []
                if new >= TYPICAL:
                    why.append(f'ID EA {new} ≥ 60000')
                if new in ea:
                    why.append(f'файл player_{new} уже есть в архиве (другая голова)')
                other = heads_used.get(new, set()) - {p['game_id']}
                if other and not all(o in matched_same(pl, other, q) for o in other):
                    why.append(f'headid {new} уже у game_id {sorted(other)}')
                if why:
                    rec['why'] = '; '.join(why)
                    conf.append(rec)
                else:
                    ok.append(rec)
            elif Aw and not (len(strong) > 1 or Dw or Ew):
                artid_only.append(dict(rec, other=[f"{players[i]['first']} {players[i]['last']}" for i in Aw]))
            elif len(strong) > 1 or Dw or Ew:
                cand = strong + Dw + Ew
                rec['why'] = ('несколько кандидатов' if len(strong) > 1 else
                              'та же фамилия и дата, другое имя' if Dw else 'тёзка с другой датой рождения')
                rec['candidates'] = [{'name': f"{players[i]['first']} {players[i]['last']}", 'birth': players[i]['birth'],
                                      'artid': players[i]['artid'], 'folder': folder_of.get(i)} for i in cand]
                disp.append(rec)
        out = {'variant': v, 'players': len(pl), 'ea_scans_untouched': ea_scan, 'ok': ok, 'disputed': disp,
               'conflict': conf, 'no_folder': nofolder, 'artid_only': artid_only}
        fn = os.path.join(work(), f'match-{v}.json')
        json.dump(out, open(fn, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        print(f'{v}: игроков {len(pl)}, со сканом EA (не трогаются) {ea_scan}; сопоставлено {len(ok)} '
              f'({dict(Counter(r["how"] for r in ok))}, по лигам {dict(Counter(r["league"] for r in ok).most_common())}); '
              f'спорных {len(disp)}, конфликтов {len(conf)}, скан в базе NHL 24 без папки {len(nofolder)}, совпал только номер '
              f'(другой человек, не берётся) {len(artid_only)} → {fn}')


def matched_same(pl, game_ids, q):
    """game_id строк Legacy, которые — тот же человек, что игрок NHL 24 q (дубли одного игрока в базе)."""
    b = tuple(q['birth'])
    return {p['game_id'] for p in pl if p['game_id'] in game_ids and norm(p['last']) == norm(q['last'])
            and tuple(p['birth']) == b}


# ------------------------------------------------------------------ Legacy: разбор и запись скана

def parse_rx2(raw):
    f = R.Rw4File(bytes(raw), 'rx2')
    S = f.sections
    decls = []
    for s in f.find(R.TYPE_VDECL):
        db = f.body(s)
        decls.append((db[9], [R.Element(*struct.unpack_from('>3I', db, 16 + 12 * k)) for k in range(db[8])]))
    shaders = f.find(R.TYPE_SHADER)
    parts = {}
    for k, (sv, si) in enumerate(zip(f.find(R.TYPE_VB), f.find(R.TYPE_IB))):
        vb = f.body(sv)
        vsec = S[R.u32(vb, 0x18) >> 2]
        stride, nv = R.u32(vb, 0x20) >> 16, R.u32(vb, 0x24)
        els = [d for d in decls if d[0] == stride][0][1]
        ib = f.body(si)
        idx = list(struct.unpack_from('>%dH' % R.u32(ib, 0x20), f.raw, f.abs_off(S[R.u32(ib, 0x18)])))
        b = f.body(shaders[k])
        name = b[12:b.index(b'\0', 12)].decode('latin1').rstrip('_')
        e = {x.usage if x.usage != 5 else ('uv', x.rwid >> 8): x for x in els}
        vo = f.abs_off(vsec)
        rawv = np.frombuffer(bytes(f.raw[vo:vo + stride * nv]), np.uint8).reshape(nv, stride)
        col = lambda el, n, dt: rawv[:, el.off:el.off + n * np.dtype(dt).itemsize].copy().view(dt).reshape(nv, -1)
        nw = col(e[3], 1, '>u4')[:, 0]
        tw = col(e[6], 1, '>u4')[:, 0]
        parts[name] = {'vo': vo, 'stride': stride, 'nv': nv, 'el': e,
                       'tri': np.array(R.triangles(idx, R.shader_prim(b)), np.int64),
                       'pos': col(e[0], 3, '>f2').astype(np.float64),
                       'nrm_w': nw, 'tan_w': tw, 'nrm': dec3n(nw), 'tan': dec3n(tw),
                       'uv': col(e[('uv', 0)], 2, '>u2') / 65535.0,
                       'bones': col(e[2], 4, '>u2') // 3,
                       'w': col(e[1], 4, 'u1')[:, ::-1] / 255.0}
    bp = f.find(R.TYPE_BINDPOSE)[0]
    bpo = f.abs_off(bp)
    n = R.u32(f.raw, bpo + 4)
    inv = np.array(struct.unpack_from('>%df' % (16 * n), f.raw, bpo + 16)).reshape(n, 4, 4)
    return parts, bpo, inv


def dec3n(w):
    w = w.astype(np.int64)
    out = []
    for k in range(3):
        v = (w >> (10 * k)) & 1023
        v = np.where(v & 512, v - 1024, v)
        out.append(np.maximum(-1.0, v / 511.0))
    return np.stack(out, 1)


def joints(inv):
    return np.array([-(m[3, :3] @ np.linalg.inv(m[:3, :3])) for m in inv])


def skeleton_inv():
    R.use_game('legacy')
    f = R.Rw4File(R.source(R.SKELETON), R.SKELETON)
    b = f.body(f.find(R.TYPE_BINDPOSE)[0])
    n = R.u32(b, 4)
    return np.array(struct.unpack_from('>%df' % (16 * n), b, 16)).reshape(n, 4, 4)


def unit(v):
    return v / np.maximum(np.linalg.norm(v, axis=-1, keepdims=True), 1e-12)


def smoothstep(a, b, x):
    t = np.clip((x - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)


def weld_ids(key_pos):
    _, gid = np.unique(np.round(key_pos, 5), axis=0, return_inverse=True)
    return gid.reshape(-1)


def weld_normals(pos, tri, gid):
    fn = np.cross(pos[tri[:, 1]] - pos[tri[:, 0]], pos[tri[:, 2]] - pos[tri[:, 0]])
    acc = np.zeros((gid.max() + 1, 3))
    for k in range(3):
        np.add.at(acc, gid[tri[:, k]], fn)
    return unit(acc[gid])


def rotate_frames(a, b, v):
    """Поворот векторов v вслед за нормалью a → b (Родриг, построчно)."""
    ax = np.cross(a, b)
    s = np.linalg.norm(ax, axis=1)
    c = (a * b).sum(1)
    k = ax / np.maximum(s, 1e-12)[:, None]
    out = v * c[:, None] + np.cross(k, v) * s[:, None] + k * (k * v).sum(1)[:, None] * (1 - c)[:, None]
    return unit(np.where((s < 1e-8)[:, None], v, out))


def uvmap(luv, lpos, nuv, npos):
    """Вершины Legacy → вершины NHL 24 по UV (дубли по шву — по позиции)."""
    from scipy.spatial import cKDTree
    dd, jj = cKDTree(nuv).query(luv, k=4)
    d3 = np.linalg.norm(npos[jj] - lpos[:, None, :], axis=2) + np.where(dd < 0.0008, 0.0, 10.0)
    return jj[np.arange(len(luv)), d3.argmin(1)], float(dd[:, 0].max())


# ------------------------------------------------------------------ шаблоны

_LIB = None


def templates():
    """Сканы EA Legacy для шаблона: 5 сеток без прядей, head 2623 + mouthbag 534. Кэш — <work>/scans24/templates.npz."""
    global _LIB
    if _LIB is not None:
        return _LIB
    fn = os.path.join(work(), 'templates.npz')
    if os.path.exists(fn):
        z = np.load(fn)
        _LIB = {int(k[1:]): z[k] for k in z.files}
        return _LIB
    from fb import heads
    ref = heads.head('cale_makar')['sections']['mat_head']
    nuv, npos = ref['uv0'][:, :2], ref['pos']
    out = {}
    for x in sorted(os.listdir(EA_PLAYER)):
        if not (x.startswith('player_') and x[7:-4].isdigit()):
            continue
        hid = int(x[7:-4])
        if hid >= 20000:                           # 20050+ и 30000+ — женские головы (другая сетка), 60000+ — типовые
            continue
        try:
            P, _, _ = parse_rx2(open(os.path.join(EA_PLAYER, x), 'rb').read())
        except Exception:                          # noqa: BLE001
            continue
        if sorted(P) != ['eyel', 'eyer', 'haircap', 'head', 'mouthbag'] or P['head']['nv'] != 2623 \
                or P['mouthbag']['nv'] != 534:
            continue
        lpos = np.concatenate([P['head']['pos'], P['mouthbag']['pos']])
        luv = np.concatenate([P['head']['uv'], P['mouthbag']['uv']])
        j, dmax = uvmap(luv, lpos, nuv, npos)
        if dmax > 0.001 or len(set(j.tolist())) < 3100:
            continue
        out[hid] = np.concatenate([j[:, None].astype(np.float64), lpos], 1)      # [номер NHL 24, x, y, z]
    os.makedirs(work(), exist_ok=True)
    np.savez_compressed(fn, **{f't{k}': v for k, v in out.items()})
    return out


def pick_template(npos, lib, digits):
    best = None
    for hid, a in lib.items():
        if len(str(hid)) != digits:
            continue
        j = a[:2623, 0].astype(int)
        d = np.linalg.norm(a[:2623, 1:] - npos[j], axis=1).mean()
        if best is None or d < best[1]:
            best = (hid, d)
    return best


# ------------------------------------------------------------------ сборка одной головы

def build_one(job):
    """job: {'new', 'folder', 'tpl'} → <work>/scans24/cache/<new>/ (player/texlib + info.json)."""
    os.environ['KITPAINT_SERIAL'] = '1'
    from scipy.spatial import cKDTree
    from fb import heads, kit3d
    new, folder, tpl = job['new'], job['folder'], job['tpl']
    out = os.path.join(work(), 'cache', str(new))
    info_fn = os.path.join(out, 'info.json')
    key = {'version': VERSION, 'folder': folder, 'tpl': tpl}
    if os.path.exists(info_fn):
        info = json.load(open(info_fn, encoding='utf-8'))
        if all(info.get(k) == v for k, v in key.items()):
            return info
    t0 = time.time()
    rep = dict(key, new=new)
    raw = bytearray(open(os.path.join(EA_PLAYER, f'player_{tpl}.rx2'), 'rb').read())
    P, bpo, inv = parse_rx2(raw)
    N = heads.head(folder)['sections']
    npos, nuv = N['mat_head']['pos'], N['mat_head']['uv0'][:, :2]
    ref = reference_head()
    same_order = N['mat_head']['tri'].shape == ref['tri'].shape and (N['mat_head']['tri'] == ref['tri']).all()
    tx = heads.head_textures(folder)
    if same_order:
        uvdev = float(np.abs(nuv - ref['uv0'][:, :2]).max())
        if uvdev > 0.001:                      # своя правка развёртки у головы NHL 24 — текстура в общую развёртку
            tx['head'] = warp_uv(tx['head'], nuv, ref['uv0'][:, :2], ref['tri'])
    rep['nhl24_same_order'] = bool(same_order)
    nh = P['head']['nv']
    hair = heads.hair(folder) if tx['hair'] is not None else []
    lpos = np.concatenate([P['head']['pos'], P['mouthbag']['pos']])
    luv = np.concatenate([P['head']['uv'], P['mouthbag']['uv']])
    if same_order:                             # Legacy → NHL 24: порядок вершин у почти всех голов NHL 24 один
        j = templates()[tpl][:, 0].astype(int)
        duv = float(np.abs(luv - ref['uv0'][:, :2][j]).max())
        if duv > 0.001:
            raise ValueError(f'{tpl}: карта вершин шаблона не сходится по UV ({duv:.4f})')
        uvdev = float(np.abs(nuv - ref['uv0'][:, :2]).max())
    else:                                      # у головы свой порядок вершин — сопоставление по её UV и проверка рёбер
        j, duv = uvmap(luv, lpos, nuv, npos)
        ltri = np.concatenate([P['head']['tri'], P['mouthbag']['tri'] + nh])
        edges = lambda t: {tuple(e) for e in np.sort(np.concatenate([t[:, [0, 1]], t[:, [1, 2]], t[:, [0, 2]]]), 1).tolist()}
        common = len(edges(j[ltri]) & edges(N['mat_head']['tri'])) / len(edges(N['mat_head']['tri']))
        rep['edges_common'] = round(common, 3)
        uvdev = duv
        if duv > 0.004 or common < 0.8:
            raise ValueError(f'{folder}: свой порядок вершин NHL 24 не сводится к общей голове (UV {duv:.4f}, '
                             f'общих рёбер {common:.0%})')
    rep['nhl24_uv_dev'] = round(uvdev, 4)
    # поза: у части голов NHL 24 череп сдвинут/наклонён относительно шеи (Mark Stone — на 2 см) — тогда жёсткое
    # выравнивание по черепу (y > 1,70) к шаблону; у остальных (и у пилота Макара) — как есть
    m = (lpos[:, 1] > 1.70) & (np.arange(len(lpos)) < nh)
    X, Y = npos[j][m], lpos[m]
    cx, cy = X.mean(0), Y.mean(0)
    U, _, Vt = np.linalg.svd((X - cx).T @ (Y - cy))
    Rm = (U @ Vt).T
    ang = float(np.degrees(np.arccos(np.clip((np.trace(Rm) - 1) / 2, -1, 1))))
    tr = float(np.linalg.norm(cy - cx))
    rigid = None
    if np.linalg.det(Rm) > 0 and (ang > POSE_DEG or tr * 1000 > POSE_MM):
        rigid = (Rm, cx, cy)
        npos = (npos - cx) @ Rm.T + cy
    rep['pose'] = {'deg': round(ang, 2), 'mm': round(tr * 1000, 1), 'aligned': rigid is not None}
    w = smoothstep(NECK[0], NECK[1], lpos[:, 1])[:, None]
    newp = lpos + w * (npos[j] - lpos)
    disp = newp - lpos
    rep.update(uv_match_max=duv, shape_change_mm=round(float(np.linalg.norm(disp, axis=1).mean() * 1000), 2))
    # глаза — вместе с веками
    th = cKDTree(lpos[:nh])
    eyes = {}
    for name in ('eyel', 'eyer'):
        q = P[name]['pos']
        d, ii = th.query(q.mean(0), k=24)
        wv = 1.0 / np.maximum(d, 1e-4) ** 2
        eyes[name] = q + (disp[:nh][ii] * wv[:, None]).sum(0) / wv.sum()
    # haircap: поле смещений + высота по прядям NHL 24
    cap = P['haircap']
    d, ii = th.query(cap['pos'], k=8)
    ww = 1.0 / np.maximum(d, 1e-4) ** 2
    follow = cap['pos'] + (disp[:nh][ii] * ww[..., None]).sum(1) / ww.sum(1)[:, None]
    hgid = weld_ids(lpos[:nh])
    head_new = {'pos': newp[:nh], 'tri': P['head']['tri'], 'nrm': weld_normals(newp[:nh], P['head']['tri'], hgid)}
    cgid = weld_ids(cap['pos'])
    centre = np.array([0.0, 1.80, 0.0])

    def outward(pos, n):
        return np.where(((pos - centre) * n).sum(1, keepdims=True) < 0, -n, n)
    capn = outward(follow, weld_normals(follow, cap['tri'], cgid))
    t_, b_, _ = kit3d.project(follow, np.zeros_like(follow), head_new, k=16, min_dot=-2.0)
    T = head_new['tri'][t_]
    scalp = (b_[:, :1] * head_new['pos'][T[:, 0]] + b_[:, 1:2] * head_new['pos'][T[:, 1]] + b_[:, 2:] * head_new['pos'][T[:, 2]])
    h_follow = ((follow - scalp) * capn).sum(1)
    hair_tex = tx['hair'].astype(np.float32) if tx['hair'] is not None else None
    if rigid is not None:                       # волосы — той же жёсткой поправкой, что голова
        Rm_, cx_, cy_ = rigid
        hair = [(n_, dict(s_, pos=(s_['pos'] - cx_) @ Rm_.T + cy_)) for n_, s_ in hair]
    pts, alp = [], []
    for _, s in hair:
        pos, uv, tri = s['pos'], s['uv0'][:, :2], s['tri']
        for bw in ((1, 0, 0), (0, 1, 0), (0, 0, 1), (1 / 3, 1 / 3, 1 / 3)):
            pts.append(bw[0] * pos[tri[:, 0]] + bw[1] * pos[tri[:, 1]] + bw[2] * pos[tri[:, 2]])
            u = bw[0] * uv[tri[:, 0]] + bw[1] * uv[tri[:, 1]] + bw[2] * uv[tri[:, 2]]
            alp.append(sample(hair_tex[..., 3:4], u[:, 0], u[:, 1])[:, 0])
    outer = np.full(len(follow), np.nan)
    if pts:
        pts, alp = np.concatenate(pts), np.concatenate(alp)
        solid = pts[alp > 128]
        if len(solid):
            st = cKDTree(solid)
            for i, (s0, n0) in enumerate(zip(scalp, capn)):
                c = solid[st.query_ball_point(s0 + n0 * 0.012, 0.016)]
                if len(c) == 0:
                    continue
                rel = c - s0
                t = rel @ n0
                m = (np.linalg.norm(rel - t[:, None] * n0, axis=1) < 0.006) & (t > -0.002) & (t < 0.035)
                if m.sum() >= 3:
                    outer[i] = np.percentile(t[m], 90)
    has = ~np.isnan(outer)
    lim = np.minimum(np.maximum(h_follow, 0.004) + CAP_ADD, CAP_MAX)
    h = np.where(has, np.clip(np.nan_to_num(outer), CAP_MIN, lim), np.minimum(np.maximum(h_follow, CAP_MIN), 0.002))
    ea, eb = np.unique(np.sort(np.concatenate([cap['tri'][:, [0, 1]], cap['tri'][:, [1, 2]], cap['tri'][:, [0, 2]]]), 1),
                       axis=0).T                       # рёбра без повторов — соседи вершины по одному разу
    for _ in range(10):
        acc = np.zeros(len(h)); cnt = np.zeros(len(h))
        np.add.at(acc, ea, h[eb]); np.add.at(acc, eb, h[ea]); np.add.at(cnt, ea, 1); np.add.at(cnt, eb, 1)
        h = 0.5 * h + 0.5 * np.where(cnt > 0, acc / np.maximum(cnt, 1), h)
        g = np.zeros(cgid.max() + 1); c = np.zeros(cgid.max() + 1)
        np.add.at(g, cgid, h); np.add.at(c, cgid, 1)
        h = (g / c)[cgid]
    cap_new = follow + capn * (h - h_follow)[:, None]
    rep.update(cap_with_hair=int(has.sum()), cap_vertices=len(has), cap_height_mm_p50=round(float(np.median(h) * 1000), 2))
    # пряди → hair_cm (UV шапки)
    capmesh = {'pos': cap_new, 'tri': cap['tri'], 'nrm': outward(cap_new, weld_normals(cap_new, cap['tri'], cgid))}
    if hair:
        hair_rgba, ntris = bake_hair(hair, hair_tex, capmesh, cap['uv'], kit3d)
    else:                                       # волос нет (лысый) — шапка прозрачная
        hair_rgba, ntris = np.zeros((256, 256, 4), np.uint8), 0
        hair_rgba[..., :3] = 60
    rep['hair_triangles'] = ntris
    # нормали, касательные; запись вершин
    newparts = {'head': newp[:nh], 'mouthbag': newp[nh:], 'haircap': cap_new, 'eyel': eyes['eyel'], 'eyer': eyes['eyer']}
    for name, q in newparts.items():
        p = P[name]
        if name.startswith('eye'):
            nrm, tan = p['nrm'], p['tan']
        else:
            gid = weld_ids(p['pos'])
            a, b = weld_normals(p['pos'], p['tri'], gid), weld_normals(q, p['tri'], gid)
            nrm, tan = rotate_frames(a, b, p['nrm']), rotate_frames(a, b, p['tan'])
        e = p['el']
        for i in range(p['nv']):
            o = p['vo'] + i * p['stride']
            struct.pack_into('>3H', raw, o + e[0].off, *[R.half_enc(float(x)) for x in q[i]])
            struct.pack_into('>I', raw, o + e[3].off, R.dec3n_enc(nrm[i], int(p['nrm_w'][i]) >> 30))
            struct.pack_into('>I', raw, o + e[6].off, R.dec3n_enc(tan[i], int(p['tan_w'][i]) >> 30))
    # поза привязки: лицевые суставы шаблона
    J0, Jt = joints(skeleton_inv()), joints(inv)
    bones = np.concatenate([P['head']['bones'], P['mouthbag']['bones']])
    wts = np.concatenate([P['head']['w'], P['mouthbag']['w']])
    inv2 = inv.copy()
    moved = 0
    for bone in range(len(inv)):
        if np.linalg.norm(Jt[bone] - J0[bone]) <= 1e-4:
            continue
        ws = ((bones == bone) * wts).sum(1)
        if ws.sum() < 1e-6:
            continue
        jn = Jt[bone] + (disp * ws[:, None]).sum(0) / ws.sum()
        inv2[bone, 3, :3] = -(jn @ inv[bone, :3, :3])
        moved += 1
    struct.pack_into('>%df' % inv2.size, raw, bpo + 16, *inv2.reshape(-1))
    rep['joints_moved'] = moved
    # проверка разбора
    P2, _, inv3 = parse_rx2(raw)
    rep['check_pos_err_mm'] = round(max(float(np.abs(P2[n]['pos'] - newparts[n]).max()) for n in newparts) * 1000, 3)
    # texlib
    import kitpaint
    import teamart
    from PIL import Image
    R.use_game('legacy')
    rw = teamart.Rw4.load(os.path.join(EA_PLAYER, f'texlib_{tpl}.rx2'))
    ren = rw.rename(tpl, new)
    if len(ren) != 2:
        raise RuntimeError(f'{new}: переименовано растров {len(ren)}')
    face = np.array(Image.fromarray(tx['head'][..., :3]).resize((512, 512), Image.LANCZOS))
    face = np.dstack([face, np.full(face.shape[:2], 255, np.uint8)])
    for t in rw.textures:
        if t.name.startswith('head_'):
            kitpaint.tex_replace(rw, t, face.tobytes(), 512, 512)
        elif t.name.startswith('hair_'):
            kitpaint.tex_replace(rw, t, hair_rgba.tobytes(), 256, 256)
    os.makedirs(out, exist_ok=True)
    files = {f'player_{new}.rx2': bytes(raw), f'texlib_{new}.rx2': rw.bytes()}
    for fn, data in files.items():
        with open(os.path.join(out, fn), 'wb') as f:
            f.write(data)
    rep['md5'] = {fn: hashlib.md5(d).hexdigest() for fn, d in files.items()}
    rep['seconds'] = round(time.time() - t0, 1)
    json.dump(rep, open(info_fn, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    return rep


_REF = None


def reference_head():
    """Общая голова NHL 24 (порядок вершин, треугольники, развёртка) — по Макару."""
    global _REF
    if _REF is None:
        from fb import heads
        _REF = heads.head('cale_makar')['sections']['mat_head']
    return _REF


def warp_uv(tex, uv_src, uv_dst, tri):
    """Текстура в развёртке uv_src → в развёртке uv_dst (тот же набор треугольников; по треугольникам, барицентры)."""
    Hh, W = tex.shape[:2]
    out = tex.copy()
    tf = tex.astype(np.float32)
    moved = np.abs(uv_src - uv_dst).max(1) > 1e-4
    for a, b, c in tri[moved[tri].any(1)]:
        sx, sy = uv_dst[[a, b, c], 0] * W, uv_dst[[a, b, c], 1] * Hh
        ix0, ix1 = max(int(np.floor(sx.min())), 0), min(int(np.ceil(sx.max())), W - 1)
        iy0, iy1 = max(int(np.floor(sy.min())), 0), min(int(np.ceil(sy.max())), Hh - 1)
        if ix1 < ix0 or iy1 < iy0:
            continue
        (xa, xb, xc), (ya, yb, yc) = sx, sy
        den = (yb - yc) * (xa - xc) + (xc - xb) * (ya - yc)
        if abs(den) < 1e-9:
            continue
        xs, ys = np.meshgrid(np.arange(ix0, ix1 + 1) + 0.5, np.arange(iy0, iy1 + 1) + 0.5)
        l0 = ((yb - yc) * (xs - xc) + (xc - xb) * (ys - yc)) / den
        l1 = ((yc - ya) * (xs - xc) + (xa - xc) * (ys - yc)) / den
        l2 = 1 - l0 - l1
        m = (l0 >= -1e-3) & (l1 >= -1e-3) & (l2 >= -1e-3)
        if not m.any():
            continue
        su = l0[m] * uv_src[a, 0] + l1[m] * uv_src[b, 0] + l2[m] * uv_src[c, 0]
        sv = l0[m] * uv_src[a, 1] + l1[m] * uv_src[b, 1] + l2[m] * uv_src[c, 1]
        out[(ys[m] - 0.5).astype(int), (xs[m] - 0.5).astype(int)] = np.clip(sample(tf, su, sv), 0, 255).astype(np.uint8)
    return out


def sample(tex, u, v):
    h, w = tex.shape[:2]
    x = np.clip(np.mod(u, 1.0) * w - 0.5, 0, w - 1)
    y = np.clip(np.mod(v, 1.0) * h - 0.5, 0, h - 1)
    x0, y0 = np.floor(x).astype(int), np.floor(y).astype(int)
    x1, y1 = np.minimum(x0 + 1, w - 1), np.minimum(y0 + 1, h - 1)
    fx, fy = (x - x0)[:, None], (y - y0)[:, None]
    t = tex if tex.dtype.kind == 'f' else tex.astype(np.float32)      # большие текстуры — переводить заранее
    return t[y0, x0] * (1 - fx) * (1 - fy) + t[y0, x1] * fx * (1 - fy) + t[y1, x0] * (1 - fx) * fy + t[y1, x1] * fx * fy


def bake_hair(hair, hair_tex, capmesh, cap_uv, kit3d, size=256, ss=2):
    """Пряди NHL 24 → RGBA size² в развёртке haircap: каждая вершина прядей — на ближайшую точку шапки (UV и высота),
    треугольники — растеризация в UV по высоте снизу вверх, «поверх» (альфа текстуры волос NHL 24)."""
    S = size * ss
    acc = np.zeros((S, S, 3))
    A = np.zeros((S, S))
    tris = []
    ct = capmesh['tri']
    for _, s in hair:
        pos, uv, tri = s['pos'], s['uv0'][:, :2], s['tri']
        t_, b_, dd = kit3d.project(pos, np.zeros_like(pos), capmesh, k=16, min_dot=-2.0)
        T = ct[t_]
        cu = b_[:, :1] * cap_uv[T[:, 0]] + b_[:, 1:2] * cap_uv[T[:, 1]] + b_[:, 2:] * cap_uv[T[:, 2]]
        cx = b_[:, :1] * capmesh['pos'][T[:, 0]] + b_[:, 1:2] * capmesh['pos'][T[:, 1]] + b_[:, 2:] * capmesh['pos'][T[:, 2]]
        cn = unit(b_[:, :1] * capmesh['nrm'][T[:, 0]] + b_[:, 1:2] * capmesh['nrm'][T[:, 1]] + b_[:, 2:] * capmesh['nrm'][T[:, 2]])
        ht = ((pos - cx) * cn).sum(1)
        q = cu[tri]
        edge = np.max(np.stack([np.linalg.norm(q[:, 0] - q[:, 1], axis=1), np.linalg.norm(q[:, 1] - q[:, 2], axis=1),
                                np.linalg.norm(q[:, 0] - q[:, 2], axis=1)]), 0)
        keep = (dd[tri].max(1) <= 0.03) & (edge <= 0.08)
        for k in np.nonzero(keep)[0]:
            tris.append((ht[tri[k]].mean(), q[k], uv[tri[k]]))
    tris.sort(key=lambda x: x[0])
    for _, q, su in tris:
        sx, sy = q[:, 0] * S, q[:, 1] * S
        ix0, ix1 = max(int(np.floor(sx.min())), 0), min(int(np.ceil(sx.max())), S - 1)
        iy0, iy1 = max(int(np.floor(sy.min())), 0), min(int(np.ceil(sy.max())), S - 1)
        if ix1 < ix0 or iy1 < iy0:
            continue
        (xa, xb, xc), (ya, yb, yc) = sx, sy
        den = (yb - yc) * (xa - xc) + (xc - xb) * (ya - yc)
        if abs(den) < 1e-9:
            continue
        xs, ys = np.meshgrid(np.arange(ix0, ix1 + 1) + 0.5, np.arange(iy0, iy1 + 1) + 0.5)
        l0 = ((yb - yc) * (xs - xc) + (xc - xb) * (ys - yc)) / den
        l1 = ((yc - ya) * (xs - xc) + (xa - xc) * (ys - yc)) / den
        l2 = 1 - l0 - l1
        m = (l0 >= -1e-6) & (l1 >= -1e-6) & (l2 >= -1e-6)
        if not m.any():
            continue
        c = sample(hair_tex, l0[m] * su[0, 0] + l1[m] * su[1, 0] + l2[m] * su[2, 0],
                   l0[m] * su[0, 1] + l1[m] * su[1, 1] + l2[m] * su[2, 1])
        a = c[:, 3] / 255.0
        py, px = (ys[m] - 0.5).astype(int), (xs[m] - 0.5).astype(int)
        acc[py, px] = c[:, :3] * a[:, None] + acc[py, px] * (1 - a[:, None])
        A[py, px] = a + A[py, px] * (1 - a)
    accd = acc.reshape(size, ss, size, ss, 3).mean((1, 3))
    Ad = A.reshape(size, ss, size, ss).mean((1, 3))
    col = accd / np.maximum(Ad, 1e-4)[..., None]
    col = kit3d.push_pull(col, Ad > 0.05) if (Ad > 0.05).any() else np.full_like(col, 60.0)
    alpha = np.clip(Ad * 1.25, 0, 1)
    return np.dstack([np.clip(col, 0, 255), alpha * 255]).astype(np.uint8), len(tris)


def cmd_build(jobs, disputed):
    lib = templates()
    from fb import heads
    want = {}
    for v in VARIANTS:
        fn = os.path.join(work(), f'match-{v}.json')
        if not os.path.exists(fn):
            raise SystemExit(f'нет {fn} — сначала match')
        m = json.load(open(fn, encoding='utf-8'))
        for r in m['ok']:
            want[r['new']] = (r['folder'], 'ok')
        if disputed:
            for r in m['disputed']:
                for c in r.get('candidates', []):
                    if c.get('folder') and c['artid'] < TYPICAL and c['artid'] not in want:
                        want[c['artid']] = (c['folder'], 'disputed')
    print(f'голов к сборке: {len(want)} (ok {sum(1 for f, k in want.values() if k == "ok")}); шаблонов {len(lib)}')
    joblist = []
    for new, (folder, kind) in sorted(want.items()):
        npos = heads.head(folder)['sections']['mat_head']['pos']
        best = pick_template(npos, lib, len(str(new)))
        if best is None:
            print(f'  {new} {folder}: нет шаблона с {len(str(new))} цифрами — пропуск')
            continue
        joblist.append({'new': new, 'folder': folder, 'tpl': best[0], 'tpl_dist_mm': round(best[1] * 1000, 2), 'kind': kind})
    res, bad = {}, []
    with ProcessPoolExecutor(max_workers=jobs) as ex:
        futs = {ex.submit(build_one, j): j for j in joblist}
        for k, (f, j) in enumerate(futs.items()):
            try:
                res[j['new']] = dict(f.result(), kind=j['kind'], tpl_dist_mm=j['tpl_dist_mm'])
            except Exception as e:  # noqa: BLE001
                bad.append((j['new'], j['folder'], repr(e)))
            if (k + 1) % 20 == 0:
                print(f'  собрано {k + 1}/{len(joblist)}', flush=True)
    # ok → out/rendering/player; прежние файлы этапа, которых больше нет в списке, — в корзину этапа
    dst = os.path.join(P24.work(), 'out', 'rendering', 'player')
    os.makedirs(dst, exist_ok=True)
    man_fn = os.path.join(work(), 'out-files.json')
    prev = set(json.load(open(man_fn, encoding='utf-8'))) if os.path.exists(man_fn) else set()
    now = set()
    for new, r in res.items():
        if r['kind'] != 'ok':
            continue
        for fn in (f'player_{new}.rx2', f'texlib_{new}.rx2'):
            src = os.path.join(work(), 'cache', str(new), fn)
            if not os.path.exists(os.path.join(dst, fn)) or md5(os.path.join(dst, fn)) != md5(src):
                shutil.copyfile(src, os.path.join(dst, fn))
            now.add(fn)
    stale = sorted(prev - now)
    for fn in stale:
        p = os.path.join(dst, fn)
        if os.path.exists(p):
            os.makedirs(os.path.join(work(), 'stale'), exist_ok=True)
            shutil.move(p, os.path.join(work(), 'stale', fn))
    json.dump(sorted(now), open(man_fn, 'w', encoding='utf-8'), indent=0)
    json.dump(res, open(os.path.join(work(), 'built.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(f'собрано {len(res)} (ok в out: {len(now) // 2}), ошибок {len(bad)}, убрано из out прежних {len(stale)}')
    for b in bad:
        print('  ошибка:', b)


def md5(p):
    return hashlib.md5(open(p, 'rb').read()).hexdigest()


# ------------------------------------------------------------------ база и сейв

def head_users(db):
    """Номера голов, которыми кто-то пользуется (все поля *headid вне справочников голов)."""
    used = set()
    for tn in db.by_name:
        if tn in (HEADS, PLACE):
            continue
        for fld in db.by_name[tn]['fields']:
            if fld.endswith('headid'):
                used |= {db.get(tn, fld, r) for r in db.live_rows(tn)}
    return used


def model_files():
    files = ea_head_files()
    d = os.path.join(P24.work(), 'out', 'rendering', 'player')
    if os.path.isdir(d):
        files |= {int(x[7:-4]) for x in os.listdir(d) if x.startswith('player_') and x[7:-4].isdigit()}
    return files


def heads_rows(db, need):
    """Строки stockplayerheads для голов need: на место доноров, число строк то же, порядок по headid. → отчёт."""
    mx, cur, dele, _ = db.counts(HEADS)
    n = len(db.live_rows(HEADS))
    if db.live_rows(HEADS) != list(range(n)) or dele:
        raise SystemExit(f'{HEADS}: живые строки не подряд / есть удалённые — не разбиралось')
    recs = [db.record(HEADS, r) for r in range(n)]
    hs = [db.get(HEADS, 'headid', r) for r in range(n)]
    if hs != sorted(hs):
        raise SystemExit(f'{HEADS}: не упорядочена по headid')
    missing = sorted(set(need) - set(hs))
    if not missing:
        return f'{HEADS}: все {len(need)} строк уже есть'
    tpl = [r for r in range(n) if hs[r] == ROW_TEMPLATE]
    if len(tpl) != 1:
        raise SystemExit(f'{HEADS}: нет строки образца {ROW_TEMPLATE}')
    used, files = head_users(db), model_files()
    donors = [r for r in range(n) if hs[r] < TYPICAL and hs[r] not in used and hs[r] not in files and hs[r] not in need]
    if len(donors) < len(missing):
        raise SystemExit(f'{HEADS}: доноров {len(donors)} < нужно {len(missing)}')
    donors = donors[:len(missing)]
    dset = set(donors)
    rows = [(hs[r], recs[r]) for r in range(n) if r not in dset]
    for hnew in missing:
        rows.append((hnew, None))
    rows.sort(key=lambda x: x[0])
    for r, (hh, rec) in enumerate(rows):
        db.put_record(HEADS, r, rec if rec is not None else recs[tpl[0]])
        if rec is None:
            db.set(HEADS, 'headid', r, hh)
    hs2 = [db.get(HEADS, 'headid', r) for r in range(n)]
    assert hs2 == sorted(hs2) and set(missing) <= set(hs2) and len(hs2) == n
    assert db.counts(HEADS)[:3] == (mx, cur, dele)
    return (f'{HEADS}: + {len(missing)} строк на места доноров (без модели и без пользователей: '
            f'{[hs[r] for r in donors][:6]}{"…" if len(donors) > 6 else ""}), строк по-прежнему {n} (max {mx})')


def applied_fn(v):
    return os.path.join(work(), f'applied-{v}.json')


def cmd_apply(variants):
    for v in variants:
        m = json.load(open(os.path.join(work(), f'match-{v}.json'), encoding='utf-8'))
        built = json.load(open(os.path.join(work(), 'built.json'), encoding='utf-8'))
        d = os.path.join(P24.work(), v, 'db')
        meta = load_meta(os.path.join(d, 'nhlng-meta.xml'))
        db = Tdb(open(os.path.join(d, 'nhlng.db'), 'rb').read(), meta)
        done = {r['game_id']: r for r in json.load(open(applied_fn(v), encoding='utf-8'))} if os.path.exists(applied_fn(v)) else {}
        ch = same = other = nob = 0
        need = set()
        for r in m['ok']:
            if built.get(str(r['new']), {}).get('kind') != 'ok':
                nob += 1
                continue
            rows = [x for x in db.live_rows(BIO) if db.get(BIO, 'game_id', x) == r['game_id']]
            if len(rows) != 1:
                raise SystemExit(f'{v}: game_id {r["game_id"]} — {len(rows)} строк')
            x = rows[0]
            h = db.get(BIO, 'headid', x)
            old = r['old'] if r['old'] != r['new'] else done.get(r['game_id'], {}).get('old') or pilot_old(r)
            if h == r['new']:
                same += 1
            elif h == r['old']:
                db.set(BIO, 'headid', x, r['new'])
                ch += 1
            else:
                other += 1
                continue
            need.add(r['new'])
            done[r['game_id']] = {'game_id': r['game_id'], 'row': x, 'name': r['name'], 'old': old, 'new': r['new'],
                                  'folder': r['folder'], 'applied': done.get(r['game_id'], {}).get('applied')
                                  or time.strftime('%Y-%m-%d %H:%M')}
        line = heads_rows(db, need)
        db.fix()
        if db.verify():
            raise SystemExit(f'{v}: CRC после правки не сходится')
        bk = os.path.join(work(), 'backup', time.strftime('%Y%m%d-%H%M%S'), v)
        os.makedirs(bk, exist_ok=True)
        for fn in ('nhlng.db', 'draft_roster.db'):
            if os.path.exists(os.path.join(d, fn)):
                shutil.copyfile(os.path.join(d, fn), os.path.join(bk, fn))
        with open(os.path.join(d, 'nhlng.db'), 'wb') as f:
            f.write(db.d)
        subprocess.run([sys.executable, os.path.join(TOOLS, 'legacy_data', 'draft_roster.py'), os.path.join(d, 'nhlng.db'),
                        os.path.join(d, 'draft_roster.db')], check=True)
        json.dump(sorted(done.values(), key=lambda r: r['row']), open(applied_fn(v), 'w', encoding='utf-8'),
                  ensure_ascii=False, indent=1)
        print(f'{v}: headid → скан NHL 24 у {ch}, уже стоял {same}, другая голова (не трогаю) {other}, не собрано {nob}; '
              f'{line}; копия до правки — {bk}')


def pilot_old(r):
    n = r['name'].split(' ', 1)
    return PILOT_OLD.get((norm(n[0]), norm(n[1]), tuple(r['birth'])))


def heads24_old(v):
    fn = os.path.join(P24.work(), 'heads24', f'applied-{v}.json')
    if not os.path.exists(fn):
        return {}
    return {r['game_id']: {r.get('old'), r.get('new')} for r in json.load(open(fn, encoding='utf-8'))}


def cmd_save(save, write, v):
    done = {r['game_id']: r for r in json.load(open(applied_fn(v), encoding='utf-8'))}
    h24 = heads24_old(v)
    meta = load_meta(os.path.join(P24.work(), v, 'db', 'nhlng-meta.xml'))
    sf = SaveFile(open(save, 'rb').read(), meta)
    db = sf.db
    ch = same = other = 0
    need = set()
    for x in db.live_rows(BIO):
        r = done.get(db.get(BIO, 'game_id', x))
        if not r:
            continue
        h = db.get(BIO, 'headid', x)
        if h == r['new']:
            same += 1
            need.add(r['new'])
        elif h == r['old'] or h in h24.get(r['game_id'], set()):
            db.set(BIO, 'headid', x, r['new'])
            ch += 1
            need.add(r['new'])
        else:
            other += 1
    line = heads_rows(db, need) if need else f'{HEADS}: не нужно'
    out = sf.bytes()
    chk = SaveFile(out, meta)
    bad = chk.verify()
    print(f'{os.path.basename(save)}: голов этапа в {v}: {len(done)}; в сейве к замене {ch}, уже стоит {same}, другая '
          f'голова (правка пользователя — не трогаю) {other}, нет игрока {len(done) - ch - same - other}; {line}; '
          f'CRC после правки: {"ок" if not bad else bad}; {HEADS} в сейве {chk.db.counts(HEADS)[:2]}')
    if not write:
        print('без --write: сейв не изменён')
        return
    if bad:
        raise SystemExit('проверка не прошла — сейв не записан')
    bk = os.path.join(P24.work(), 'backup-saves', 'scans24-' + time.strftime('%Y%m%d-%H%M%S'))
    os.makedirs(bk, exist_ok=True)
    shutil.copyfile(save, os.path.join(bk, os.path.basename(save)))
    with open(save, 'wb') as f:
        f.write(out)
    print(f'записано; копия до правки — {bk}')


# ------------------------------------------------------------------ лист проверки (офлайн-рендер)

FRAME = (-0.17, 0.17, 1.52, 2.00)
FRAME_HELMET = (-0.19, 0.19, 1.50, 2.06)
KEY = unit(np.array([-0.45, 0.55, 0.85]))
FILL = unit(np.array([0.7, 0.0, 0.6]))


def rot(v, a):
    c, s = np.cos(a), np.sin(a)
    out = v.copy()
    out[..., 0] = c * v[..., 0] + s * v[..., 2]
    out[..., 2] = -s * v[..., 0] + c * v[..., 2]
    return out


def vtangents(pos, uv, tri, nrm):
    t, b = np.zeros_like(pos), np.zeros_like(pos)
    e1, e2 = pos[tri[:, 1]] - pos[tri[:, 0]], pos[tri[:, 2]] - pos[tri[:, 0]]
    d1, d2 = uv[tri[:, 1]] - uv[tri[:, 0]], uv[tri[:, 2]] - uv[tri[:, 0]]
    r = d1[:, 0] * d2[:, 1] - d2[:, 0] * d1[:, 1]
    r = np.where(np.abs(r) < 1e-12, 1e-12, r)
    sd = (e1 * d2[:, 1:2] - e2 * d1[:, 1:2]) / r[:, None]
    td = (e2 * d1[:, 0:1] - e1 * d2[:, 0:1]) / r[:, None]
    for k in range(3):
        np.add.at(t, tri[:, k], sd)
        np.add.at(b, tri[:, k], td)
    return unit(t - nrm * (t * nrm).sum(-1, keepdims=True)), unit(b - nrm * (b * nrm).sum(-1, keepdims=True))


def render(parts, angle=0.0, width=220, ss=2, frame=FRAME, bg=(38, 38, 44)):
    from PIL import Image
    W = width * ss
    x0, x1, y0, y1 = frame
    Hh = int(round(W * (y1 - y0) / (x1 - x0)))
    zb = np.full((Hh, W), -np.inf)
    pid = np.full((Hh, W), -1, np.int64)
    tid = np.full((Hh, W), -1, np.int64)
    bw = np.zeros((Hh, W, 3))
    for k, p in enumerate(parts):
        Pp = rot(p['pos'], angle)
        sx = (Pp[:, 0] - x0) / (x1 - x0) * W
        sy = (y1 - Pp[:, 1]) / (y1 - y0) * Hh
        z = Pp[:, 2]
        if p['tex'].dtype.kind != 'f':
            p['tex'] = p['tex'].astype(np.float32)
        al = p['tex'][..., 3:4] if p.get('alpha') else None
        uv = p['uv']
        for ti, (a, b, c) in enumerate(p['tri']):
            xa, xb, xc, ya, yb, yc = sx[a], sx[b], sx[c], sy[a], sy[b], sy[c]
            ix0, ix1 = max(int(min(xa, xb, xc)), 0), min(int(max(xa, xb, xc)) + 1, W - 1)
            iy0, iy1 = max(int(min(ya, yb, yc)), 0), min(int(max(ya, yb, yc)) + 1, Hh - 1)
            if ix1 < ix0 or iy1 < iy0:
                continue
            den = (yb - yc) * (xa - xc) + (xc - xb) * (ya - yc)
            if abs(den) < 1e-12:
                continue
            xs, ys = np.meshgrid(np.arange(ix0, ix1 + 1) + 0.5, np.arange(iy0, iy1 + 1) + 0.5)
            l0 = ((yb - yc) * (xs - xc) + (xc - xb) * (ys - yc)) / den
            l1 = ((yc - ya) * (xs - xc) + (xa - xc) * (ys - yc)) / den
            l2 = 1 - l0 - l1
            m = (l0 >= 0) & (l1 >= 0) & (l2 >= 0)
            if not m.any():
                continue
            L0, L1, L2 = l0[m], l1[m], l2[m]
            zz = L0 * z[a] + L1 * z[b] + L2 * z[c]
            py, px = (ys[m] - 0.5).astype(int), (xs[m] - 0.5).astype(int)
            keep = zz > zb[py, px]
            if al is not None and keep.any():
                keep &= sample(al, L0 * uv[a, 0] + L1 * uv[b, 0] + L2 * uv[c, 0],
                               L0 * uv[a, 1] + L1 * uv[b, 1] + L2 * uv[c, 1])[:, 0] > p.get('cut', 100)
            if not keep.any():
                continue
            py, px = py[keep], px[keep]
            zb[py, px] = zz[keep]
            pid[py, px] = k
            tid[py, px] = ti
            bw[py, px] = np.stack([L0[keep], L1[keep], L2[keep]], -1)
    out = np.zeros((Hh, W, 3))
    out[:] = bg
    Hk = unit(KEY + np.array([0.0, 0.0, 1.0]))
    for k, p in enumerate(parts):
        py, px = np.nonzero(pid == k)
        if not len(py):
            continue
        tr = p['tri'][tid[py, px]]
        a, b, c = tr[:, 0], tr[:, 1], tr[:, 2]
        w0, w1, w2 = bw[py, px, 0:1], bw[py, px, 1:2], bw[py, px, 2:3]
        uv = p['uv']
        u = (w0 * uv[a, 0:1] + w1 * uv[b, 0:1] + w2 * uv[c, 0:1])[:, 0]
        v = (w0 * uv[a, 1:2] + w1 * uv[b, 1:2] + w2 * uv[c, 1:2])[:, 0]
        col = sample(p['tex'][..., :3], u, v)
        N = rot(p['nrm'], angle)
        if p.get('nmap') is not None and p['nmap'].dtype != np.float32:
            p['nmap'] = p['nmap'].astype(np.float32)
        n = unit(w0 * N[a] + w1 * N[b] + w2 * N[c])
        if p.get('nmap') is not None:
            if '_tb' not in p:
                p['_tb'] = vtangents(p['pos'], p['uv'], p['tri'], p['nrm'])
            Tg, Bt = rot(p['_tb'][0], angle), rot(p['_tb'][1], angle)
            t = unit(w0 * Tg[a] + w1 * Tg[b] + w2 * Tg[c])
            bb = unit(w0 * Bt[a] + w1 * Bt[b] + w2 * Bt[c])
            nt = sample(p['nmap'][..., :3], u, v) / 127.5 - 1.0
            n = unit(t * nt[:, 0:1] - bb * nt[:, 1:2] + n * np.clip(nt[:, 2:3], 0.2, 1))
        if p.get('twosided'):
            n = np.where(n[:, 2:3] < 0, -n, n)
        lam = np.clip((n * KEY).sum(-1), 0, 1)
        fil = np.clip((n * FILL).sum(-1), 0, 1)
        sp = np.clip((n * Hk).sum(-1), 0, 1) ** 30 * p.get('spec', 0.10)
        out[py, px] = col * (0.28 + 0.78 * lam + 0.18 * fil)[:, None] + 255 * sp[:, None]
    img = Image.fromarray(np.clip(out, 0, 255).astype(np.uint8))
    return img.resize((width, Hh // ss), Image.LANCZOS)


_COMMON = None


def common_tex():
    global _COMMON
    if _COMMON is None:
        import kitpaint
        import teamart
        R.use_game('legacy')
        rw = teamart.Rw4.load(COMMON)
        c = {}
        for t in rw.textures:
            w, h, rgba = kitpaint.tex_decode(rw, t)
            c[t.name.split('.')[0]] = np.frombuffer(bytes(rgba), np.uint8).reshape(h, w, 4)
        _COMMON = c
    return _COMMON


def legacy_parts(mesh_path, texlib_path):
    import kitpaint
    import teamart
    c = common_tex()
    P, _, _ = parse_rx2(open(mesh_path, 'rb').read())
    rw = teamart.Rw4.load(texlib_path)
    tex = {}
    for t in rw.textures:
        w, h, rgba = kitpaint.tex_decode(rw, t)
        tex['hair' if t.name.startswith('hair') else 'head'] = np.frombuffer(bytes(rgba), np.uint8).reshape(h, w, 4)
    out = []
    for name, p in P.items():
        d = {'pos': p['pos'], 'nrm': unit(p['nrm']), 'uv': p['uv'], 'tri': p['tri']}
        if name in ('head', 'mouthbag'):
            d.update(tex=tex['head'], nmap=c['head_cnm'].astype(np.float64))
        elif name == 'haircap':
            d.update(tex=tex['hair'], alpha=True, cut=90, twosided=True)
        elif name.startswith('eye'):
            d.update(tex=c['eyes_2_cm'], spec=0.5)
        else:
            continue
        out.append(d)
    return out


def nhl24_parts(folder):
    from fb import heads
    N = heads.head(folder)['sections']
    tx = heads.head_textures(folder)
    out = []
    h = N['mat_head']
    out.append({'pos': h['pos'], 'nrm': unit(h['nrm'][:, :3]), 'uv': h['uv0'][:, :2], 'tri': h['tri'], 'tex': tx['head']})
    e = N.get('mat_eyes')
    if e is not None:
        out.append({'pos': e['pos'], 'nrm': unit(e['nrm'][:, :3]), 'uv': e['uv1'][:, :2], 'tri': e['tri'],
                    'tex': common_tex()['eyes_2_cm'], 'spec': 0.5})
    for _, s in (heads.hair(folder) if tx['hair'] is not None else []):
        nrm = unit(s['nrm'][:, :3]) if 'nrm' in s else weld_normals(s['pos'], s['tri'], np.arange(len(s['pos'])))
        out.append({'pos': s['pos'], 'nrm': nrm, 'uv': s['uv0'][:, :2], 'tri': s['tri'],
                    'tex': tx['hair'], 'alpha': True, 'cut': 100, 'twosided': True})
    return out


def helmet_parts():
    R.use_game('legacy')
    out = []
    for rel, col in (('rendering/helmet/helmet_11_2.rx2', (111, 38, 61)), ('rendering/helmet/chinstrap_11_2.rx2', (25, 25, 28))):
        m = R.Mesh.game(rel)
        tex = np.zeros((4, 4, 4), np.uint8)
        tex[...] = (*col, 255)
        out.append({'pos': np.array([p[:3] for p in m.pos]), 'tri': np.array(m.tris, np.int64),
                    'nrm': unit(np.array([n[:3] for n in m.nrm])), 'uv': np.zeros((len(m.pos), 2)), 'tex': tex,
                    'spec': 0.25, 'twosided': True})
    return out


def sheet_cell(job):
    from PIL import Image, ImageDraw, ImageFont
    os.environ['KITPAINT_SERIAL'] = '1'
    font = ImageFont.truetype(os.path.join(os.environ.get('WINDIR', r'C:\Windows'), 'Fonts', 'segoeui.ttf'), 13)
    W = 200
    cache = os.path.join(work(), 'cache', str(job['new']))
    imgs = []
    if job.get('helmet'):
        pass
    elif job.get('old') and job['old'] >= TYPICAL and os.path.exists(os.path.join(EA_PLAYER, f'player_{job["old"]}.rx2')):
        imgs.append(render(legacy_parts(os.path.join(EA_PLAYER, f'player_{job["old"]}.rx2'),
                                        os.path.join(EA_PLAYER, f'texlib_{job["old"]}.rx2')), width=W))
    else:
        imgs.append(Image.new('RGB', (W, 282), (38, 38, 44)))
    if not job.get('helmet'):
        imgs.append(render(nhl24_parts(job['folder']), width=W))
    ours = legacy_parts(os.path.join(cache, f'player_{job["new"]}.rx2'), os.path.join(cache, f'texlib_{job["new"]}.rx2'))
    imgs.append(render(ours, width=W))
    if job.get('helmet'):
        hp = helmet_parts()
        imgs.append(render(ours + hp, np.radians(35), width=W, frame=FRAME_HELMET))
        imgs.append(render(ours + hp, np.radians(90), width=W, frame=FRAME_HELMET))
    h = max(i.size[1] for i in imgs)
    cell = Image.new('RGB', (len(imgs) * (W + 4) + 4, h + 40), (28, 28, 32))
    for k, i in enumerate(imgs):
        cell.paste(i, (4 + k * (W + 4), 36))
    d = ImageDraw.Draw(cell)
    d.text((6, 2), f"{job['name']} ({job.get('league', '')}) — {job.get('tag', '')}", fill=(255, 220, 140), font=font)
    d.text((6, 18), f"сейчас {job.get('old')} | NHL 24 {job['folder']} | наш {job['new']} (шаблон {job.get('tpl')})",
           fill=(200, 200, 200), font=font)
    p = os.path.join(work(), 'sheet', f"{job['new']}{'_h' if job.get('helmet') else ''}.png")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    cell.save(p)
    return p


STARS = ('Auston Matthews', 'Nikita Kucherov', 'Connor Bedard', 'David Pastrnak', 'Aleksander Barkov', 'Mikko Rantanen',
         'Kirill Kaprizov', 'Jack Eichel', 'Jack Hughes', 'Quinn Hughes', 'Rasmus Dahlin', 'Matthew Tkachuk',
         'Andrei Vasilevskiy', 'Connor Hellebuyck', 'Cale Makar')


def cmd_sheet(n, jobs, variant='out-ahl32', names=None, helmets=5, disputed=True):
    from PIL import Image
    m = json.load(open(os.path.join(work(), f'match-{variant}.json'), encoding='utf-8'))
    built = json.load(open(os.path.join(work(), 'built.json'), encoding='utf-8'))
    rnd = random.Random(12)
    ok = [r for r in m['ok'] if str(r['new']) in built]
    if names:
        by = {norm(r['name']): r for r in ok}
        pick = [by[norm(x)] for x in names if norm(x) in by]
        miss = [x for x in names if norm(x) not in by]
        if miss:
            print('нет среди сопоставленных:', miss)
    else:
        pick = rnd.sample(ok, min(n, len(ok)))
        if not any(r['name'] == 'Cale Makar' for r in pick):
            pick = [r for r in ok if r['name'] == 'Cale Makar'] + pick[:n - 1]
    jobs_l = [dict(r, tag='ok', tpl=built[str(r['new'])]['tpl'], old=r['old'] if r['old'] >= TYPICAL else
                   pilot_old(r)) for r in pick]
    for r in (m['disputed'] if disputed else []):
        for c in r.get('candidates', []):
            if str(c['artid']) in built:
                jobs_l.append({'name': f"{r['name']} ≟ {c['name']} {c['birth']}", 'league': r['league'], 'tag': r['why'],
                               'old': r['old'], 'folder': c['folder'], 'new': c['artid'],
                               'tpl': built[str(c['artid'])]['tpl']})
    for r in pick[:helmets]:
        jobs_l.append(dict(r, tag='в шлеме (3/4, сбоку)', helmet=True, tpl=built[str(r['new'])]['tpl'],
                           old=None))
    with ProcessPoolExecutor(max_workers=jobs) as ex:
        cells = list(ex.map(sheet_cell, jobs_l))
    ims = [Image.open(c) for c in cells]
    cols = 2
    cw = max(i.size[0] for i in ims)
    ch = max(i.size[1] for i in ims)
    rows = (len(ims) + cols - 1) // cols
    sheet = Image.new('RGB', (cols * (cw + 6), rows * (ch + 6)), (20, 20, 24))
    for k, im in enumerate(ims):
        sheet.paste(im, ((k % cols) * (cw + 6), (k // cols) * (ch + 6)))
    out = os.path.join(work(), f'sheet-{variant}.png')
    sheet.save(out)
    print(f'лист: {len(ims)} клеток → {out}')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('cmd', choices=('match', 'build', 'apply', 'save', 'sheet', 'one'))
    ap.add_argument('save', nargs='?')
    ap.add_argument('--variant', action='append', choices=VARIANTS)
    ap.add_argument('--write', action='store_true')
    ap.add_argument('--jobs', type=int, default=6)
    ap.add_argument('--n', type=int, default=60)
    ap.add_argument('--disputed', action='store_true', help='build: собрать и головы спорных (в кэш, не в out); sheet: и их')
    ap.add_argument('--stars', action='store_true', help='sheet: 15 звёзд (STARS) вместо случайных')
    ap.add_argument('--helmets', type=int, default=5)
    a = ap.parse_args()
    variants = a.variant or list(VARIANTS)
    if a.cmd == 'match':
        cmd_match(variants)
    elif a.cmd == 'build':
        cmd_build(a.jobs, a.disputed)
    elif a.cmd == 'apply':
        cmd_apply(variants)
    elif a.cmd == 'save':
        if not a.save:
            raise SystemExit('нужен путь к сейву ROSTER')
        cmd_save(a.save, a.write, (a.variant or ['out-ahl32'])[0])
    elif a.cmd == 'sheet':
        cmd_sheet(a.n, a.jobs, names=STARS if a.stars else None, helmets=a.helmets, disputed=a.disputed)
    elif a.cmd == 'one':                       # отладка: python scans24.py one 20185:cale_makar
        new, folder = a.save.split(':')
        lib = templates()
        from fb import heads
        best = pick_template(heads.head(folder)['sections']['mat_head']['pos'], lib, len(new))
        print(build_one({'new': int(new), 'folder': folder, 'tpl': best[0]}))


if __name__ == '__main__':
    main()
