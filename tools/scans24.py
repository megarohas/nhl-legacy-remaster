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
  * глаза шаблона — сдвиг по поверхности глаза источника, поворот — зрачок в середину разреза век (v7, headeyes.py);
  * haircap — полем смещений головы, высота над скальпом — по прядям NHL 24, не больше шаблонной + 4 мм и не больше
    12 мм (место под шлемом);
  * поза привязки файла: лицевые суставы шаблона (отличные от общего скелета) — сдвиг по весам кожи;
  * head_<id>_cm — цвет NHL 24 1024 → 512; hair_<id>_cm — пряди NHL 24, запечённые на развёртку haircap.
База: headid игрока → ID EA; stockplayerheads (есть у каждой головы игрока, упорядочена по headid) — строка новой головы
на место строки-донора (голова без файла модели, которой никто не пользуется), число строк не меняется ни в базе, ни в
сейве (иначе старый ROSTER «damaged»). stockplayerhelmetplacement не трогается (шлем по умолчанию, как у шаблона Макара).

  python tools/scans24.py match            # → <work>/scans24/match-<вариант>.json: ok / спорные / конфликты
  python tools/scans24.py build [--jobs 6] [--disputed]   # → <work>/scans24/cache/<id>/, ok → out/rendering/player/
  python tools/scans24.py apply            # headid + stockplayerheads в out/db и out-ahl32/db, draft_roster.db заново
  python tools/scans24.py save СЕЙВ [--write] [--variant out-ahl32]   # то же в сейве ROSTER (копия, проверка CRC)
  python tools/scans24.py sheet [--n 60] [--names "Имя Фамилия,…"]   # лист «типовая сейчас | NHL 24 | наш»
                                           # (+ спорные, + 5 в шлеме)
  python tools/scans24.py styles --source nhl27            # каталог общих причёсок NHL 27 → <work>/scans27/styles*
  python tools/scans24.py hairplan --source nhl27          # hair-plan.json (стиль по фото, цвет из базы) и листы
  python tools/scans24.py check [--ea] [--only папка,…] [--cache ПАПКА]   # глаза: против глаза источника, зрачок,
                                           # край шапочки (headeyes.py); --ea — эталон по сканам EA

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
import headeyes as HE  # noqa: E402
import rw4mesh as R  # noqa: E402
from tdb import Tdb, SaveFile  # noqa: E402
from tdb_read import load_meta  # noqa: E402

G = P24.G
VARIANTS = P24.VARIANTS
VERSION = 7                                   # версия сборки головы (кэш); 2 — карта вершин шаблона, UV; 3 — поза;
                                              # 4 — глаза по глазам NHL 24 (вершина роговицы);
                                              # 5 — суставы век/бровей/скул = общий скелет (EYE_BONES);
                                              # 6 — глаза снова вслед за веками (v3), ось взгляда 23/24 — вместе с глазом
                                              # 7 — яблоко по поверхности глаза источника, зрачок — в середину разреза
                                              #     век (headeyes.py; 21.10, глаза Селебрини «режут веки»)
EA_PLAYER = os.path.join(G.big, 'cacherender', 'rendering', 'player')
COMMON = os.path.join(G.big, 'renderboot', 'rendering', 'player_common', 'texlib_999.rx2')
BIO, HEADS, PLACE = 'exhibitionplayerbiotable', 'stockplayerheads', 'stockplayerhelmetplacement'
TYPICAL = 60000
NECK = (1.60, 1.66)                           # низ шеи — от шаблона (у сканов EA общий), переход
CAP_ADD, CAP_MAX, CAP_MIN = 0.004, 0.012, 0.0015
POSE_DEG, POSE_MM = 2.5, 6.0
# Суставы вокруг глаз — как в общем скелете (skeleton_bindpose_player), а не сдвинутые по смещению вершин: в игре поза
# лица берёт переносы суставов общего скелета, а InvBind — из файла головы, так что сдвинутый сустав даёт в покое
# смещение вершин на (J_общий − J_головы). У век это раздвигало веки (Matthews: белок по кругу, DeBrincat: веко поднято —
# пользователь, 12.10). 23/24, 34/35 — оси век в центре глаза, 36/37 — нижние веки, 38–41 — брови, 25/26 — скулы у
# глаза. Челюсть и губы (16–22, 27–33, 42–47) — как раньше, по смещению вершин (рот в этом экране приоткрыт у всех).
EYE_BONES = (25, 26, 34, 35, 36, 37, 38, 39, 40, 41)
# 23/24 — ось взгляда (игра поворачивает яблоко вокруг сустава из файла головы: у сканов EA он точно у центра яблока,
# J − центр = ±1,3/0/1,6 мм, а от общего скелета у EA глаза на 5–15 мм). С v6 сустав двигается вместе с глазом:
# J = J шаблона + сдвиг глаза (в v5 был общий скелет → у Zegras «косоглазие», пользователь 12.10).
GAZE_BONES = {'eyel': 23, 'eyer': 24}                  # голова NHL 24 в другой позе (наклон/сдвиг черепа) — выровнять
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


def work(src=None):
    """<work>/scans24 (источник NHL 24) или <work>/scans27 (--source nhl27: сетки PS5 читает fb.heads, 21.10.2026)."""
    src = src or P24.SOURCE
    return os.path.join(P24.work(), 'scans24' if src == 'nhl24' else 'scans' + src[3:])


def other_sources(v):
    """Головы, поставленные этим этапом из других источников (applied-<v>.json их папок): {game_id: headid} и номера
    их файлов в out (out-files.json). Это персональные головы нашей версии — источник их не заменяет (решение
    пользователя 21.10: «те, которые уже имеют персонализированную голову, не трогать»)."""
    heads, files = {}, set()
    for src in P24.SOURCES:
        if src == P24.SOURCE:
            continue
        fn = os.path.join(work(src), f'applied-{v}.json')
        if os.path.exists(fn):
            heads.update({r['game_id']: r['new'] for r in json.load(open(fn, encoding='utf-8'))})
        fn = os.path.join(work(src), 'out-files.json')
        if os.path.exists(fn):
            files |= {int(x[7:-4]) for x in json.load(open(fn, encoding='utf-8')) if x.startswith('player_')}
    return heads, files


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
        foreign, foreign_files = other_sources(v)
        ok, disp, conf, nofolder, artid_only = [], [], [], [], []
        ea_scan = ours = 0
        for p in pl:
            h = p['headid']
            if h < TYPICAL and h in ea:
                ea_scan += 1
                continue
            if h < TYPICAL and foreign.get(p['game_id']) == h:
                ours += 1                              # голова из другого источника (NHL 24) — не трогается
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
                if new in foreign_files:
                    why.append(f'файл player_{new} уже собран из другого источника')
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
        out = {'variant': v, 'players': len(pl), 'ea_scans_untouched': ea_scan, 'other_source_untouched': ours,
               'ok': ok, 'disputed': disp,
               'conflict': conf, 'no_folder': nofolder, 'artid_only': artid_only}
        fn = os.path.join(work(), f'match-{v}.json')
        json.dump(out, open(fn, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        print(f'{v}: игроков {len(pl)}, со сканом EA (не трогаются) {ea_scan}, с головой другого источника (не '
              f'трогаются) {ours}; сопоставлено {len(ok)} '
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


_SKEL = None


def skeleton_inv():
    global _SKEL
    if _SKEL is None:
        R.use_game('legacy')
        f = R.Rw4File(R.source(R.SKELETON), R.SKELETON)
        b = f.body(f.find(R.TYPE_BINDPOSE)[0])
        n = R.u32(b, 4)
        _SKEL = np.array(struct.unpack_from('>%df' % (16 * n), b, 16)).reshape(n, 4, 4)
    return _SKEL.copy()


def game_pose(part, pos, inv):
    """Позиции части (head, mouthbag) в позе игры: игра берёт переносы суставов общего скелета, InvBind — из файла
    головы, поэтому вершина смещается на Σ w·(J_общий − J_файла) (docs/heads-nhl24.md, «Веки»)."""
    d = joints(skeleton_inv()) - joints(inv)
    return pos + (d[part['bones']] * part['w'][..., None]).sum(1)


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
    """Вершины Legacy → вершины NHL 24 по UV (дубли по шву — по позиции). У NHL 27 UV совпадают с Legacy до 1e-5, а форма
    у глаз другая: кандидаты — только в пределах «ближайший + 0,0001» (с допуском 0,0008 позиция выбирала соседнюю
    вершину, 31 совпадение у шаблона 10276, 21.10.2026); у NHL 24 — как было."""
    from scipy.spatial import cKDTree
    dd, jj = cKDTree(nuv).query(luv, k=4)
    near = dd < (dd[:, :1] + 0.0001 if P24.SOURCE != 'nhl24' else 0.0008)
    d3 = np.linalg.norm(npos[jj] - lpos[:, None, :], axis=2) + np.where(near, 0.0, 10.0)
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

def source_map(P, N, folder, tpl):
    """Вершины шаблона tpl (head + mouthbag) → вершины mat_head источника и выравнивание черепа источника к шаблону →
    {'j', 'duv', 'uvdev', 'same_order', 'edges_common'?, 'rigid' (Rm, cx, cy) или None, 'pose', 'npos' (выровненные)}."""
    npos, nuv = N['mat_head']['pos'], N['mat_head']['uv0'][:, :2]
    ref = reference_head()
    same_order = bool(N['mat_head']['tri'].shape == ref['tri'].shape and (N['mat_head']['tri'] == ref['tri']).all())
    nh = P['head']['nv']
    lpos = np.concatenate([P['head']['pos'], P['mouthbag']['pos']])
    luv = np.concatenate([P['head']['uv'], P['mouthbag']['uv']])
    out = {'same_order': same_order}
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
        out['edges_common'] = round(common, 3)
        uvdev = duv
        if duv > 0.004 or common < 0.8:
            raise ValueError(f'{folder}: свой порядок вершин NHL 24 не сводится к общей голове (UV {duv:.4f}, '
                             f'общих рёбер {common:.0%})')
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
    out.update(j=j, duv=duv, uvdev=uvdev, rigid=rigid, npos=npos,
               pose={'deg': round(ang, 2), 'mm': round(tr * 1000, 1), 'aligned': rigid is not None})
    return out


def source_eyes(N, rigid):
    """Вершины глаз источника (mat_eyes, оба глаза; x > 0 — левый), с тем же выравниванием, что голова, или None."""
    if 'mat_eyes' not in N:
        return None
    e = N['mat_eyes']['pos']
    return (e - rigid[1]) @ rigid[0].T + rigid[2] if rigid is not None else e


def build_one(job):
    """job: {'new', 'folder', 'tpl'} → <work>/scans24/cache/<new>/ (player/texlib + info.json)."""
    os.environ['KITPAINT_SERIAL'] = '1'
    from scipy.spatial import cKDTree
    from fb import heads, kit3d
    new, folder, tpl = job['new'], job['folder'], job['tpl']
    out = os.path.join(work(), 'cache', str(new))
    info_fn = os.path.join(out, 'info.json')
    key = {'version': VERSION, 'eyes': HE.RULE, 'folder': folder, 'tpl': tpl, 'old_head': job.get('old_head'),
           'style': job.get('style'), 'face_hair': FACE_HAIR if P24.SOURCE in FACE_HAIR_SOURCES else None,
           'hair_color': job.get('hair_color')}
    if os.path.exists(info_fn):
        info = json.load(open(info_fn, encoding='utf-8'))
        if all(info.get(k) == v for k, v in key.items()):
            return info
    t0 = time.time()
    rep = dict(key, new=new)
    raw = bytearray(open(os.path.join(EA_PLAYER, f'player_{tpl}.rx2'), 'rb').read())
    P, bpo, inv = parse_rx2(raw)
    N = heads.head(folder)['sections']
    tx = heads.head_textures(folder)
    sm = source_map(P, N, folder, tpl)
    j, duv, rigid, npos = sm['j'], sm['duv'], sm['rigid'], sm['npos']
    if sm['same_order'] and sm['uvdev'] > 0.001:     # своя правка развёртки у головы NHL 24 — текстура в общую развёртку
        ref = reference_head()
        tx['head'] = warp_uv(tx['head'], N['mat_head']['uv0'][:, :2], ref['uv0'][:, :2], ref['tri'])
    rep['nhl24_same_order'] = sm['same_order']
    if 'edges_common' in sm:
        rep['edges_common'] = sm['edges_common']
    rep['nhl24_uv_dev'] = round(sm['uvdev'], 4)
    rep['pose'] = sm['pose']
    nh = P['head']['nv']
    hair = heads.hair(folder) if tx['hair'] is not None else []
    lpos = np.concatenate([P['head']['pos'], P['mouthbag']['pos']])
    w = smoothstep(NECK[0], NECK[1], lpos[:, 1])[:, None]
    newp = lpos + w * (npos[j] - lpos)
    disp = newp - lpos
    rep.update(uv_match_max=duv, shape_change_mm=round(float(np.linalg.norm(disp, axis=1).mean() * 1000), 2))
    # глаза (v7, headeyes.py): сдвиг шапочки шаблона — по поверхности глаза источника (веки источника сделаны под его
    # глаз), поворот вокруг центра — зрачок в середину разреза век (ниже, после суставов: разрез — в позе игры).
    # До v7 (v3, v6) глаз шёл вслед за 24 ближайшими вершинами головы и вставал на 1–3 мм впереди глаза источника
    # (у Селебрини 2,7, у Matthews ещё и на 3,4 мм ближе к переносице) — «выступает из черепа и режет веки»
    # (пользователь, 21.10; раньше так же у Matthews и DeBrincat). v4/v5 брали вершину роговицы источника — у голов,
    # где глаза источника в позе привязки повёрнуты, яблоки уезжали к переносице (Zegras, «косоглазие»).
    th = cKDTree(lpos[:nh])
    eN = source_eyes(N, rigid)
    eyes, rep['eyes'], eye_shift, eye_rule = {}, {}, {}, {}
    for name, side in (('eyel', 1), ('eyer', -1)):
        q = P[name]['pos']
        d, ii = th.query(q.mean(0), k=24)
        wv = 1.0 / np.maximum(d, 1e-4) ** 2
        t_lids = (disp[:nh][ii] * wv[:, None]).sum(0) / wv.sum()            # v6: вслед за веками
        pts = HE.src_front(eN[np.sign(eN[:, 0]) == side]) if eN is not None else np.zeros((0, 3))
        t = HE.fit_to_source(q, pts) if len(pts) >= HE.MIN_SRC else None
        eye_rule[name] = 'lids' if t is None else 'source'
        t = t_lids if t is None else t
        eyes[name] = q + t
        rep['eyes'][name] = {'rule': eye_rule[name], 'src_points': len(pts), 'shift_mm': np.round(t * 1000, 2).tolist(),
                             'vs_lids_mm': np.round((t - t_lids) * 1000, 2).tolist(),
                             'ahead_v6_mm': HE.ahead(pts, q + t_lids), 'ahead_mm': HE.ahead(pts, q + t)}
        eye_shift[name] = t
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
    rep['hair_from'] = 'source' if hair else 'none'
    if not hair:
        # своих прядей у источника нет: у NHL 27 так у 261 головы из 293 (причёску собирает шейдер по рецепту материала,
        # cranium/materials/recipe/<папка>_material_recipe — не разобран). Волосы нарисованы на скальпе (Селебрини) — как
        # есть; иначе голова вышла бы лысой — волосы с нынешней типовой головы игрока (её подбирали по фото, heads24)
        painted, rep['scalp_ratio'] = scalp_painted(N['mat_head'], tx['head'])
        st = job.get('style')
        if not painted and st is not None:
            # причёска NHL 27 из общих (подбор по фото — hair-plan.json): сетки, обтянутые по голове игрока, и рисунок на
            # скальпе (маска стиля на развёртке головы — она у NHL 27 и Legacy одна)
            hair, hair_tex, tx['head'] = shared_style(st['style'], st['color'], N['mat_head'], tx['head'], rigid)
            rep['hair_from'] = f"style {st['style']} color {st['color']}"
        else:
            lh = None if painted else legacy_hair(job.get('old_head'))
            if lh is not None:
                hair, hair_tex = lh
                rep['hair_from'] = f"legacy {job['old_head']}"
            elif painted:
                rep['hair_from'] = 'painted'
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
    # нормали, касательные; запись вершин (глаза — после суставов: поворот к разрезу век считается в позе игры)
    def put(name, q, nrm, tan):
        p, e = P[name], P[name]['el']
        for i in range(p['nv']):
            o = p['vo'] + i * p['stride']
            struct.pack_into('>3H', raw, o + e[0].off, *[R.half_enc(float(x)) for x in q[i]])
            struct.pack_into('>I', raw, o + e[3].off, R.dec3n_enc(nrm[i], int(p['nrm_w'][i]) >> 30))
            struct.pack_into('>I', raw, o + e[6].off, R.dec3n_enc(tan[i], int(p['tan_w'][i]) >> 30))
    newparts = {'head': newp[:nh], 'mouthbag': newp[nh:], 'haircap': cap_new}
    for name, q in newparts.items():
        p = P[name]
        gid = weld_ids(p['pos'])
        a, b = weld_normals(p['pos'], p['tri'], gid), weld_normals(q, p['tri'], gid)
        put(name, q, rotate_frames(a, b, p['nrm']), rotate_frames(a, b, p['tan']))
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
    inv0 = skeleton_inv()
    for bone in EYE_BONES:
        inv2[bone] = inv0[bone]
    for name, bone in GAZE_BONES.items():      # ось взгляда — вместе с глазом
        jn = Jt[bone] + eye_shift[name]
        inv2[bone] = inv[bone].copy()
        inv2[bone][3, :3] = -(jn @ inv[bone][:3, :3])
    struct.pack_into('>%df' % inv2.size, raw, bpo + 16, *inv2.reshape(-1))
    rep['joints_moved'] = moved
    rep['eye_bones_global'] = len(EYE_BONES)
    # глаза: поворот шапочки вокруг центра — зрачок в середину разреза век головы в позе игры (v7)
    hp_game = game_pose(P['head'], newp[:nh], inv2)
    for name, side in (('eyel', 1), ('eyer', -1)):
        p = P[name]
        nrm, tan = p['nrm'], p['tan']
        turn = HE.turn_to_aperture(eyes[name], p['uv'], p['tri'], hp_game, P['head']['tri'], side) \
            if eye_rule[name] == 'source' else None
        if turn is not None:
            eyes[name], Re, deg = turn
            nrm, tan = nrm @ Re.T, tan @ Re.T
            rep['eyes'][name]['turn_deg'] = round(deg, 1)
        put(name, eyes[name], nrm, tan)
        newparts[name] = eyes[name]
    # проверка разбора
    P2, _, inv3 = parse_rx2(raw)
    rep['check_pos_err_mm'] = round(max(float(np.abs(P2[n]['pos'] - newparts[n]).max()) for n in newparts) * 1000, 3)
    # растительность на лице NHL 27 — по маске specmask (на текстуре лица её нет, игра рисует её сама)
    if P24.SOURCE in FACE_HAIR_SOURCES and job.get('hair_color') is not None:
        try:
            sm_ = heads.tex(f'{heads.LICENSED}/{folder}/textures/head_{folder}_specmask')
        except KeyError:
            sm_ = None
        if sm_ is not None:
            tx['head'], rep['face_hair_cover'] = paint_face_hair(tx['head'], sm_, job['hair_color'])
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


def cornea(p):
    """Вершина роговицы шапочки/сетки глаза: x, y — середина вершин в пределах 1 мм от передней точки, z — передняя точка."""
    z = p[:, 2].max()
    f = p[p[:, 2] > z - 0.001]
    return np.array([f[:, 0].mean(), f[:, 1].mean(), z])


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


# Головы без волос источника (hair_from = legacy <id> / none) в out не идут: решение пользователя 21.10 — сначала
# причёски NHL 27 (рецепты материалов), волосы с типовой головы — только по --legacy-hair
LEGACY_HAIR = False
SCALP_PAINTED = 0.6           # яркость скальпа / медиана яркости кожи головы ниже — волосы нарисованы на текстуре лица


def scalp_painted(mh, tex):
    """Волосы нарисованы на текстуре лица источника? Яркость текстуры у макушки (вершины выше макушки − 3 см) против
    медианы по голове: у Селебрини 0,2, у лысых в NHL 27 скальпов (Сорокин, Марченко, Шестёркин) 0,93–1,03 → (да/нет, отношение)."""
    p, uv = mh['pos'], mh['uv0'][:, :2]
    H, W = tex.shape[:2]
    lum = tex[np.clip((uv[:, 1] * H).astype(int), 0, H - 1), np.clip((uv[:, 0] * W).astype(int), 0, W - 1), :3].mean(1)
    r = float(lum[p[:, 1] > p[:, 1].max() - 0.03].mean() / max(np.median(lum), 1.0))
    return r < SCALP_PAINTED, round(r, 2)


STYLES = 'content/character/skater/shared/head/hair'
# цвет волос NHL 27 (haircolorcode базы) → sRGB: средний цвет иконок creationzone/appearance/haircolor/<код> (21.10.2026)
HAIR_COLORS = {0: (33, 33, 33), 1: (39, 28, 18), 2: (61, 44, 32), 3: (154, 132, 103), 4: (104, 76, 57), 5: (201, 180, 148),
               6: (100, 59, 32), 7: (133, 133, 133), 8: (121, 63, 29), 9: (176, 166, 131), 10: (77, 64, 50),
               11: (170, 128, 87), 12: (111, 112, 111), 13: (108, 87, 61)}
SCALP_GAIN = 1.6                              # рисунок волос на скальпе: альфа head_hair_common_color × маска × 1,6
                                              # (без усиления короткая стрижка Сорокина почти лысая, 21.10)
# Растительность на лице по маске: у NHL 27 (в отличие от NHL 24) бороды и щетины на head_<папка>_color нет — игра рисует
# их по specmask (255 − красный канал: брови, борода). Рисуется ниже линии глаз (FACE_HAIR_ROW доли высоты текстуры:
# выше — брови, они на текстуре есть, и волосы у голов со своими прядями), цвет — haircolorcode, непрозрачность —
# маска × FACE_HAIR_GAIN (не больше FACE_HAIR_MAX), цвет волос × FACE_HAIR_SHADE (борода темнее)
FACE_HAIR = 'v2'                              # v2: маска × 2, цвет × 0,8 (v1 — × 1,25: у Андерссона вместо густой бороды щетина)
FACE_HAIR_SOURCES = ('nhl27',)
FACE_HAIR_ROW, FACE_HAIR_MAX, FACE_HAIR_GAIN, FACE_HAIR_SHADE = 0.32, 0.95, 2.0, 0.8
STYLE_MAX = 72                                # male_0 … male_72 (иконки creationzone/appearance/hairstyle/0…72)
_MEAN = None


def mean_head():
    """Средняя голова NHL 27 (mat_head, порядок общий): под неё сделаны общие причёски — от неё смещение к голове игрока.
    Кэш — <work>/mean_head.npy (по 120 лицензированным головам)."""
    global _MEAN
    if _MEAN is None:
        fn = os.path.join(work(), 'mean_head.npy')
        if not os.path.exists(fn):
            from fb import heads
            ref = reference_head()
            acc, n = np.zeros_like(ref['pos'], dtype=np.float64), 0
            for f in heads.licensed_folders()[::max(1, len(heads.licensed_folders()) // 120)]:
                try:
                    m = heads.head(f)['sections']['mat_head']
                except Exception:  # noqa: BLE001
                    continue
                if m['tri'].shape == ref['tri'].shape and (m['tri'] == ref['tri']).all():
                    acc += m['pos']
                    n += 1
            np.save(fn, acc / n)
        _MEAN = np.load(fn)
    return _MEAN


def shared_style(style, color, mh, face, rigid):
    """Общая причёска NHL 27 male_<style> цвета <color> на голову игрока: сетки base/top (вершины — со смещением средняя
    голова → голова игрока по 8 ближайшим вершинам, затем то же выравнивание, что у головы), их текстура hair_male_<N>_color
    (серая, тонируется цветом) и рисунок на скальпе: head_hair_common_color по маске head_hair_male_<N>_mask на текстуре
    лица → (пряди для bake_hair, текстура прядей RGBA float, текстура лица)."""
    from scipy.spatial import cKDTree
    from fb import heads
    tint = np.array(HAIR_COLORS[color], np.float32)
    base = mean_head()
    tree = cKDTree(base)
    shift = mh['pos'] - base
    secs = []
    for part in ('base', 'top'):
        try:
            m = heads.mesh(f'{STYLES}/male_{style}/default_nomask/components/hair_male_{style}_default_nomask_{part}_mesh')
        except KeyError:
            continue
        for k, v in m['sections'].items():
            dd, ii = tree.query(v['pos'], k=8)
            w = 1.0 / np.maximum(dd, 1e-4) ** 2
            pos = v['pos'] + (shift[ii] * w[..., None]).sum(1) / w.sum(1)[:, None]
            if rigid is not None:
                pos = (pos - rigid[1]) @ rigid[0].T + rigid[2]
            secs.append((f'{part}:{k}', dict(v, pos=pos)))
    if not secs:
        raise ValueError(f'male_{style}: нет сеток default_nomask')
    col = heads.tex(f'{STYLES}/male_{style}/common/textures/hair_male_{style}_color').astype(np.float32)
    col[..., :3] = np.clip(col[..., :3] / 128.0 * tint, 0, 255)
    mask = heads.tex(f'{STYLES}/male_{style}/common/textures/head_hair_male_{style}_mask')[..., 0].astype(np.float32) / 255
    sc = heads.tex(f'{STYLES}/common/textures/head_hair_common_color').astype(np.float32)
    H, W = face.shape[:2]
    if sc.shape[:2] != (H, W):
        from PIL import Image
        sc = np.asarray(Image.fromarray(sc.astype(np.uint8)).resize((W, H), Image.LANCZOS)).astype(np.float32)
        mask = np.asarray(Image.fromarray((mask * 255).astype(np.uint8)).resize((W, H), Image.LANCZOS)).astype(np.float32) / 255
    a = np.clip(sc[..., 3] / 255 * mask * SCALP_GAIN, 0, 1)[..., None]
    out = face.astype(np.float32).copy()
    out[..., :3] = out[..., :3] * (1 - a) + np.clip(sc[..., :3] / 128.0 * tint, 0, 255) * a
    return secs, col, np.clip(out, 0, 255).astype(np.uint8)


def paint_face_hair(face, specmask, color):
    """Борода/щетина NHL 27 на текстуре лица: маска 255 − R specmask ниже FACE_HAIR_ROW, цвет HAIR_COLORS[color]
    → (текстура, доля покрытой площади ниже линии глаз)."""
    from PIL import Image
    H, W = face.shape[:2]
    m = (255 - specmask[..., 0].astype(np.float32)) / 255
    if m.shape != (H, W):
        m = np.asarray(Image.fromarray((m * 255).astype(np.uint8)).resize((W, H), Image.LANCZOS)).astype(np.float32) / 255
    m[:int(H * FACE_HAIR_ROW)] = 0
    a = np.clip(m * FACE_HAIR_GAIN, 0, 1)[..., None] * FACE_HAIR_MAX
    out = face.astype(np.float32).copy()
    out[..., :3] = out[..., :3] * (1 - a) + np.array(HAIR_COLORS[color], np.float32) * FACE_HAIR_SHADE * a
    return np.clip(out, 0, 255).astype(np.uint8), round(float((m[int(H * FACE_HAIR_ROW):] > 0.2).mean()), 3)


_HCOL = None


def source_hair_colors():
    """{ID EA: haircolorcode} базы источника (NHL 27; у NHL 24 — пусто)."""
    global _HCOL
    if _HCOL is None:
        _HCOL = {}
        if P24.SOURCE != 'nhl24':
            from roster import nhl27 as N27
            os.environ.setdefault('NHL27_DB', os.path.join(P24.SRC['db'], 'nhl_game.db'))
            db = N27.open_db()
            B = 'exhibitionplayerbiotable'
            _HCOL = {db.get(B, 'artid', r): db.get(B, 'haircolorcode', r) for r in db.live_rows(B)}
    return _HCOL


def legacy_hair(headid):
    """Шапка волос головы Legacy headid (архив игры) как «пряди» для bake_hair → ([(имя, сетка)], RGBA float) или None."""
    if not headid:
        return None
    mesh_fn, tl_fn = (os.path.join(EA_PLAYER, f'{k}_{headid}.rx2') for k in ('player', 'texlib'))
    if not (os.path.exists(mesh_fn) and os.path.exists(tl_fn)):
        return None
    import kitpaint
    import teamart
    R.use_game('legacy')
    P, _, _ = parse_rx2(open(mesh_fn, 'rb').read())
    rw = teamart.Rw4.load(tl_fn)
    for t in rw.textures:
        if t.name.startswith('hair') and 'haircap' in P:
            w, h, rgba = kitpaint.tex_decode(rw, t)
            c = P['haircap']
            return [('legacy_haircap', {'pos': c['pos'], 'uv0': c['uv'], 'tri': c['tri']})],                 np.frombuffer(bytes(rgba), np.uint8).reshape(h, w, 4).astype(np.float32)
    return None


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


def cmd_build(jobs, disputed, only=None, legacy_hair=LEGACY_HAIR):
    """only — папки источника или имена игроков (через запятую): собрать только их (пилот одной головы)."""
    lib = templates()
    from fb import heads
    want = {}
    for v in VARIANTS:
        fn = os.path.join(work(), f'match-{v}.json')
        if not os.path.exists(fn):
            raise SystemExit(f'нет {fn} — сначала match')
        m = json.load(open(fn, encoding='utf-8'))
        done = {x['game_id']: x for x in json.load(open(applied_fn(v), encoding='utf-8'))}             if os.path.exists(applied_fn(v)) else {}
        for r in m['ok']:
            old = r['old'] if r['old'] >= TYPICAL else (done.get(r['game_id'], {}).get('old') or pilot_old(r))
            want[r['new']] = (r['folder'], 'ok', old)
        if disputed:
            for r in m['disputed']:
                for c in r.get('candidates', []):
                    if c.get('folder') and c['artid'] < TYPICAL and c['artid'] not in want:
                        want[c['artid']] = (c['folder'], 'disputed', r['old'] if r['old'] >= TYPICAL else None)
    if only:
        keys = {norm(x) for x in only}
        want = {k: v for k, v in want.items() if norm(v[0]) in keys}
        if not want:
            raise SystemExit(f'--only {only}: нет среди сопоставленных (папки — как в licensed/<папка>)')
    print(f'голов к сборке: {len(want)} (ok {sum(1 for f, k, _ in want.values() if k == "ok")}); шаблонов {len(lib)}')
    plan = hair_plan()
    joblist = []
    for new, (folder, kind, old) in sorted(want.items()):
        npos = heads.head(folder)['sections']['mat_head']['pos']
        best = pick_template(npos, lib, len(str(new)))
        if best is None:
            print(f'  {new} {folder}: нет шаблона с {len(str(new))} цифрами — пропуск')
            continue
        joblist.append({'new': new, 'folder': folder, 'tpl': best[0], 'tpl_dist_mm': round(best[1] * 1000, 2), 'kind': kind,
                        'old_head': old, 'style': {k: plan[folder][k] for k in ('style', 'color')}
                        if plan.get(folder, {}).get('style') is not None else None,
                        'hair_color': (plan.get(folder) or {}).get('color', source_hair_colors().get(new))})
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
    no_hair = 0
    for new, r in res.items():
        hf = r.get('hair_from', 'source')
        if r['kind'] in ('ok', 'no_hair'):
            r['kind'] = 'ok' if hf in ('source', 'painted') or hf.startswith('style') or (legacy_hair and hf.startswith('legacy'))                 else 'no_hair'
            no_hair += r['kind'] == 'no_hair'
        if r['kind'] != 'ok':
            continue
        for fn in (f'player_{new}.rx2', f'texlib_{new}.rx2'):
            src = os.path.join(work(), 'cache', str(new), fn)
            if not os.path.exists(os.path.join(dst, fn)) or md5(os.path.join(dst, fn)) != md5(src):
                shutil.copyfile(src, os.path.join(dst, fn))
            now.add(fn)
    built_fn = os.path.join(work(), 'built.json')
    if only:                                   # частичная сборка — к собранному раньше, прежние файлы в out остаются
        res = {**({int(k): v for k, v in json.load(open(built_fn, encoding='utf-8')).items()}
                  if os.path.exists(built_fn) else {}), **res}
        now |= prev
    stale = sorted(prev - now)
    for fn in stale:
        p = os.path.join(dst, fn)
        if os.path.exists(p):
            os.makedirs(os.path.join(work(), 'stale'), exist_ok=True)
            shutil.move(p, os.path.join(work(), 'stale', fn))
    json.dump(sorted(now), open(man_fn, 'w', encoding='utf-8'), indent=0)
    json.dump({str(k): v for k, v in sorted(res.items())}, open(built_fn, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(f'собрано {len(res)} (ok в out: {len(now) // 2}; без волос источника, не в out: {no_hair}), ошибок {len(bad)}, '
          f'убрано из out прежних {len(stale)}')
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
        print(f'{v}: headid → скан {P24.LABEL} у {ch}, уже стоял {same}, другая голова (не трогаю) {other}, не собрано {nob}; '
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


# ------------------------------------------------------------------ причёски NHL 27 по фото

def style_cell(st):
    """Стиль male_<st> на средней голове NHL 27 (анфас и 3/4, тёмно-русый) → путь картинки или None (нет сеток)."""
    from fb import heads
    from PIL import Image, ImageDraw, ImageFont
    os.environ['KITPAINT_SERIAL'] = '1'
    ref = heads.head(heads.licensed_folders()[0])['sections']['mat_head']
    mh = dict(ref, pos=mean_head())
    face = np.full((1024, 1024, 4), (205, 160, 130, 255), np.uint8)
    try:
        secs, col, face = shared_style(st, 2, mh, face, None)
    except (KeyError, ValueError):
        return None
    parts = [{'pos': mh['pos'], 'nrm': weld_normals(mh['pos'], mh['tri'], weld_ids(mh['pos'])), 'uv': mh['uv0'][:, :2],
              'tri': mh['tri'], 'tex': face}]
    for _, sec in secs:
        parts.append({'pos': sec['pos'], 'nrm': weld_normals(sec['pos'], sec['tri'], np.arange(len(sec['pos']))),
                      'uv': sec['uv0'][:, :2], 'tri': sec['tri'], 'tex': col.copy(), 'alpha': True, 'cut': 100,
                      'twosided': True})
    fr = (-0.12, 0.12, 1.70, 2.02)
    a = render([dict(x) for x in parts], 0.0, 150, frame=fr)
    b = render([dict(x) for x in parts], np.radians(40), 150, frame=fr)
    im = Image.new('RGB', (a.size[0] + b.size[0] + 4, a.size[1] + 18), (24, 24, 28))
    im.paste(a, (0, 18))
    im.paste(b, (a.size[0] + 4, 18))
    ImageDraw.Draw(im).text((4, 1), str(st), fill=(255, 220, 140), font=ImageFont.truetype('arial.ttf', 14))
    fn = os.path.join(work(), 'styles', f'style_{st}.png')
    os.makedirs(os.path.dirname(fn), exist_ok=True)
    im.save(fn)
    return fn


def cmd_styles(jobs):
    """Каталог общих причёсок источника: <work>/styles/style_<N>.png и styles_sheet.png (у кого есть сетки)."""
    from PIL import Image
    with ProcessPoolExecutor(max_workers=jobs) as ex:
        res = [(st, p) for st, p in zip(range(STYLE_MAX + 1), ex.map(style_cell, range(STYLE_MAX + 1))) if p]
    ims = [Image.open(p) for _, p in res]
    cols, (w, h) = 6, ims[0].size
    sheet = Image.new('RGB', (cols * (w + 4), ((len(ims) + cols - 1) // cols) * (h + 4)), (12, 12, 14))
    for k, im in enumerate(ims):
        sheet.paste(im, ((k % cols) * (w + 4), (k // cols) * (h + 4)))
    fn = os.path.join(work(), 'styles_sheet.png')
    sheet.save(fn)
    print(f'стилей с сетками: {len(res)} из {STYLE_MAX + 1} → {fn}')


def hair_plan():
    """Стили по фото: <work>/scans<NN>/hair-plan.json, нет — копия в репозитории tools/legacy_data/hair_plan_<источник>.json
    (21.10: 259 стилей NHL 27, подобранных по листам hairplan; после правки рабочего файла — скопировать туда)."""
    for fn in (os.path.join(work(), 'hair-plan.json'), os.path.join(TOOLS, 'legacy_data', f'hair_plan_{P24.SOURCE}.json')):
        if os.path.exists(fn):
            return json.load(open(fn, encoding='utf-8'))
    return {}


def hair_players(variant='out-ahl32'):
    """Игроки этапа без своих волос источника: [(папка, имя, artid Legacy, ID EA)] по built.json и match-<variant>.json."""
    built = json.load(open(os.path.join(work(), 'built.json'), encoding='utf-8'))
    m = json.load(open(os.path.join(work(), f'match-{variant}.json'), encoding='utf-8'))
    out = []
    for r in m['ok']:
        v = built.get(str(r['new']))
        if v and v.get('hair_from', 'source') not in ('source', 'painted'):
            out.append((r['folder'], r['name'], r['artid'], r['new']))
    return sorted(out, key=lambda x: x[1].split(' ', 1)[-1])


def cmd_hairplan(variant='out-ahl32', per=30):
    """hair-plan.json: каждому игроку без своих волос — цвет из базы источника (haircolorcode), стиль — вручную по фото
    (null — не назначен: голова не идёт в out). Листы <work>/hairplan/sheet-<k>.png: фото | назначенный стиль."""
    import heads24 as H24
    from PIL import Image, ImageDraw, ImageFont
    color = source_hair_colors()
    fn = os.path.join(work(), 'hair-plan.json')
    plan = hair_plan()
    pl = hair_players(variant)
    for folder, name, art, new in pl:
        e = plan.setdefault(folder, {'style': None, 'color': color.get(new, 2)})
        e.setdefault('color', color.get(new, 2))
        e['name'] = name
    json.dump(dict(sorted(plan.items())), open(fn, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    font = ImageFont.truetype('arial.ttf', 13)
    d = os.path.join(work(), 'hairplan')
    os.makedirs(d, exist_ok=True)
    for k in range(0, len(pl), per):
        cells = []
        for i, (folder, name, art, new) in enumerate(pl[k:k + per], k):
            cell = Image.new('RGB', (300, 176), (24, 24, 28))
            dr = ImageDraw.Draw(cell)
            path = H24.portrait_path(art, variant)
            if path:
                rgba = H24.portrait_rgba(path)
                h, w = rgba.shape[:2]
                ph = Image.fromarray(rgba).crop((int(w * 0.22), 0, int(w * 0.78), int(h * 0.75)))
                ph.thumbnail((140, 150))
                bg = Image.new('RGB', ph.size, (60, 60, 66))
                bg.paste(ph, (0, 0), ph)
                cell.paste(bg, (2, 22))
            e = plan[folder]
            st = e.get('style')
            sp = os.path.join(work(), 'styles', f'style_{st}.png')
            if st is not None and os.path.exists(sp):
                im = Image.open(sp)
                im = im.crop((0, 18, im.size[0] // 2, im.size[1]))
                im.thumbnail((150, 150))
                cell.paste(im, (148, 22))
            dr.rectangle((282, 2, 296, 16), fill=HAIR_COLORS.get(e['color'], (0, 0, 0)))
            dr.text((4, 3), f"{i} {name}  стиль {st} цвет {e['color']}", fill=(255, 220, 140), font=font)
            cells.append(cell)
        cols = 5
        sheet = Image.new('RGB', (cols * 304, ((len(cells) + cols - 1) // cols) * 180), (10, 10, 12))
        for j, c in enumerate(cells):
            sheet.paste(c, ((j % cols) * 304, (j // cols) * 180))
        sheet.save(os.path.join(d, f'sheet-{k // per}.png'))
    done = sum(1 for f, *_ in pl if plan[f].get('style') is not None)
    print(f'без своих волос: {len(pl)}, стиль назначен: {done} → {fn}; листы — {d}')


# ------------------------------------------------------------------ проверка глаз

def check_one(a):
    """(new, folder, tpl, путь к player_<new>.rx2) → метрики глаз (headeyes: ahead, зрачок, под веком, край шапочки)."""
    new, folder, tpl, path = a
    from fb import heads
    B, _, inv = parse_rx2(open(path, 'rb').read())
    T, _, _ = parse_rx2(open(os.path.join(EA_PLAYER, f'player_{tpl}.rx2'), 'rb').read())
    N = heads.head(folder)['sections']
    eN = source_eyes(N, source_map(T, N, folder, tpl)['rigid'])
    hp, ht = game_pose(B['head'], B['head']['pos'], inv), B['head']['tri']
    J = joints(inv)
    piv = {n: J[b] for n, b in GAZE_BONES.items()}
    eyes = {n: (B[n]['pos'], B[n]['uv'], B[n]['tri']) for n in GAZE_BONES}
    out = {'new': new, 'folder': folder}
    for name, side in (('eyel', 1), ('eyer', -1)):
        pts = HE.src_front(eN[np.sign(eN[:, 0]) == side]) if eN is not None else np.zeros((0, 3))
        out[f'ahead_{name}'] = HE.ahead(pts, B[name]['pos'])
    out.update(HE.gaze_check(hp, ht, eyes, piv) or {})
    out['edge'] = HE.edge_seen(hp, ht, eyes, piv)
    return out


def check_ea(path):
    try:
        P, _, inv = parse_rx2(open(path, 'rb').read())
    except Exception:  # noqa: BLE001
        return None
    if 'eyel' not in P or P['head']['nv'] != 2623:
        return None
    J = joints(inv)
    hp, piv = game_pose(P['head'], P['head']['pos'], inv), {n: J[b] for n, b in GAZE_BONES.items()}
    eyes = {n: (P[n]['pos'], P[n]['uv'], P[n]['tri']) for n in GAZE_BONES}
    r = HE.gaze_check(hp, P['head']['tri'], eyes, piv)
    return r and dict(r, edge=HE.edge_seen(hp, P['head']['tri'], eyes, piv))


def cmd_check(jobs, only=None, ea=False, cache=None):
    """Глаза собранных голов (built.json этапа) против глаза источника и разреза век; --ea — те же метрики у сканов EA
    Legacy (эталон). cache — другая папка с player_<id>.rx2 (например, прежняя версия) вместо cache/<id>/."""
    built = json.load(open(os.path.join(work(), 'built.json'), encoding='utf-8'))
    keys = {norm(x) for x in only} if only else None
    todo = []
    for k, v in built.items():
        if v.get('kind') != 'ok' or (keys and norm(v['folder']) not in keys):
            continue
        path = os.path.join(cache, f'player_{k}.rx2') if cache else os.path.join(work(), 'cache', k, f'player_{k}.rx2')
        if os.path.exists(path):
            todo.append((int(k), v['folder'], v['tpl'], path))
    with ProcessPoolExecutor(max_workers=jobs) as ex:
        rows = list(ex.map(check_one, todo, chunksize=2))
        eas = []
        if ea:
            paths = sorted(os.path.join(EA_PLAYER, x) for x in os.listdir(EA_PLAYER)
                           if x.startswith('player_') and x[7:-4].isdigit() and int(x[7:-4]) < 20000)
            eas = [r for r in ex.map(check_ea, paths, chunksize=4) if r]
    pc = lambda a: np.percentile(a, [50, 95, 100]).round(2).tolist() if len(a) else None

    def line(label, rr, src=True):
        ah = [r[f'ahead_{e}'] for r in rr for e in GAZE_BONES if r.get(f'ahead_{e}') is not None] if src else []
        print(f'{label}: голов {len(rr)}; ' + (f'глаз впереди глаза источника, мм p50/p95/max {pc(ah)}; ' if src else '') +
              f'асимметрия зрачков {pc([r["asym"] for r in rr if "asym" in r])}; зрачок под веком при взгляде — у '
              f'{sum(r.get("hidden", 0) > 0 for r in rr)}; край шапочки на виду {pc([r["edge"] for r in rr])}')
    if eas:
        line('сканы EA Legacy', eas, src=False)
    line(os.path.basename(cache) if cache else f'{os.path.basename(work())} v{VERSION}', rows)
    worst = sorted(rows, key=lambda r: -max(r.get('ahead_eyel') or 0, r.get('ahead_eyer') or 0))[:8]
    print('больше всего впереди:', ', '.join(f"{r['folder']} {max(r.get('ahead_eyel') or 0, r.get('ahead_eyer') or 0)}"
                                             for r in worst))
    fn = os.path.join(work(), f'check-eyes{"-" + os.path.basename(cache) if cache else ""}.json')
    json.dump({'rows': rows, 'ea': eas}, open(fn, 'w', encoding='utf-8'), ensure_ascii=False, indent=0, default=float)
    print('→', fn)


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
    # у сеток NHL 27 (PS5) потока нормалей нет — по поверхности
    nrm_of = lambda m: unit(m['nrm'][:, :3]) if 'nrm' in m else weld_normals(m['pos'], m['tri'], np.arange(len(m['pos'])))
    h = N['mat_head']
    out.append({'pos': h['pos'], 'nrm': nrm_of(h), 'uv': h['uv0'][:, :2], 'tri': h['tri'], 'tex': tx['head']})
    e = N.get('mat_eyes')
    if e is not None:
        out.append({'pos': e['pos'], 'nrm': nrm_of(e), 'uv': e['uv1'][:, :2], 'tri': e['tri'],
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
    d.text((6, 18), f"сейчас {job.get('old')} | {P24.LABEL} {job['folder']} | наш {job['new']} (шаблон {job.get('tpl')})",
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
    ap.add_argument('cmd', choices=('match', 'build', 'apply', 'save', 'sheet', 'one', 'check', 'styles', 'hairplan'))
    ap.add_argument('save', nargs='?')
    ap.add_argument('--variant', action='append', choices=VARIANTS)
    ap.add_argument('--write', action='store_true')
    ap.add_argument('--jobs', type=int, default=6)
    ap.add_argument('--n', type=int, default=60)
    ap.add_argument('--disputed', action='store_true', help='build: собрать и головы спорных (в кэш, не в out); sheet: и их')
    ap.add_argument('--stars', action='store_true', help='sheet: 15 звёзд (STARS) вместо случайных')
    ap.add_argument('--names', help='sheet: эти игроки (имя фамилия через запятую) вместо случайных')
    ap.add_argument('--helmets', type=int, default=5)
    ap.add_argument('--source', choices=tuple(P24.SOURCES), default=P24.SOURCE, help='игра-источник сканов (nhl24, nhl27)')
    ap.add_argument('--only', help='build: только эти папки источника через запятую (пилот: --only macklin_celebrini)')
    ap.add_argument('--ea', action='store_true', help='check: и сканы EA Legacy (эталон)')
    ap.add_argument('--legacy-hair', action='store_true',
                    help='build: и головы без волос источника — с волосами нынешней типовой головы (иначе не в out)')
    ap.add_argument('--cache', help='check: папка с player_<id>.rx2 другой версии (например, <work>/scans24/before-v7)')
    a = ap.parse_args()
    variants = a.variant or list(VARIANTS)
    if a.cmd == 'match':
        cmd_match(variants)
    elif a.cmd == 'build':
        cmd_build(a.jobs, a.disputed, a.only.split(',') if a.only else None, a.legacy_hair or LEGACY_HAIR)
    elif a.cmd == 'apply':
        cmd_apply(variants)
    elif a.cmd == 'save':
        if not a.save:
            raise SystemExit('нужен путь к сейву ROSTER')
        cmd_save(a.save, a.write, (a.variant or ['out-ahl32'])[0])
    elif a.cmd == 'sheet':
        names = [x.strip() for x in a.names.split(',')] if a.names else STARS if a.stars else None
        cmd_sheet(a.n, a.jobs, names=names, helmets=a.helmets, disputed=a.disputed)
    elif a.cmd == 'styles':
        cmd_styles(a.jobs)
    elif a.cmd == 'hairplan':
        cmd_hairplan()
    elif a.cmd == 'check':
        cmd_check(a.jobs, a.only.split(',') if a.only else None, a.ea, a.cache)
    elif a.cmd == 'one':                       # отладка: python scans24.py one 20185:cale_makar
        new, folder = a.save.split(':')
        lib = templates()
        from fb import heads
        best = pick_template(heads.head(folder)['sections']['mat_head']['pos'], lib, len(new))
        print(build_one({'new': int(new), 'folder': folder, 'tpl': best[0]}))


if __name__ == '__main__':
    main()
