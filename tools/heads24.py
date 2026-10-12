"""Типовые головы игроков NHL Legacy по фото — осторожный вариант (решение пользователя 12.10.2026).

Голова игрока — `headid` в `exhibitionplayerbiotable`:
- скан EA — свои `rendering/player/player_<id>.rx2` и `texlib_<id>.rx2`; не трогаются;
- типовая — 60000–60210; волосы и растительность «зашиты» в голову, полей волос в базе Legacy нет.
Цвет головы — только её текстура; `skincolor` выбирает текстуру кистей (`rendering/body/hand_<N>_cm.rx2`) и не меняется.

Кому меняется голова (типовая голова и портрет в игре):
  1) голова EA из NHL 24: в базе NHL 24 у игрока типовая голова (номера и лица голов у NHL 24 и Legacy одни и те же),
     она не противоречит фото по волосам (лысина тоже), растительности (и по ненадёжным признакам), тон — та же
     ступень или соседняя при разнице skincolor не больше 1 → берётся она;
  2) явное несовпадение: на фото надёжно видно цвет волос (рыжий / блонд / тёмный) или растительность (борода / чисто
     выбрит / щетина, усы, лысина), а у нынешней головы — другое → подбор: волосы и растительность — жёстко, тон — та же
     ступень (соседняя при разнице skincolor ≤ 1 — со штрафом), черты лица — мягко (z-признаки фото и текстур головы), против клонов — штраф за
     частоту и одна голова на команду;
  остальным голова остаётся.
Разметка голов (волосы, растительность, азиатская внешность) — tools/legacy_data/heads_legacy.json (по иконкам игры).
Признаки фото — по большому портрету игры p<artid>.big: рамка лица Haar (OpenCV), цвет волос над лбом без каймы вырезки
и кожи, фактура, затемнение подбородка/челюсти/над губой относительно щёк. Признаки голов — по их текстурам.

  python tools/heads24.py plan  [--variant out|out-ahl32]…   # → <work>/heads24/plan-<вариант>.json (ничего не пишет в out)
  python tools/heads24.py apply [--variant …]                 # headid в out/db (nhlng.db, draft_roster.db заново)
  python tools/heads24.py sheet [--variant out-ahl32] [--n 24]  # лист «фото | было | стало | правило»
  python tools/heads24.py save СЕЙВ_ROSTER [--write] [--variant out-ahl32]   # headid и в сохранённом составе

<work> — game/work/legacy-data (или LEGACY_DATA_WORK). Нужен питон с numpy, scipy, Pillow и opencv-python-headless
(PyPI; venv game/work/photos-nhl24/venv) и база NHL 24 из дампа (tools/photos24.py). Повтор plan/apply ничего не меняет:
у поставленных игроков голова уже новая (applied-<вариант>.json).
"""
import argparse
import json
import math
import os
import random
import shutil
import statistics
import subprocess
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor

TOOLS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TOOLS)
os.environ.setdefault('NHL_GAME', 'legacy')
import photos24 as P24  # noqa: E402  (профиль Legacy, игроки базы, база NHL 24)
from tdb import Tdb  # noqa: E402
from tdb_read import load_meta  # noqa: E402

G = P24.G
SPEC = os.path.join(TOOLS, 'legacy_data', 'heads_legacy.json')
HEADS = range(60000, 60211)
VARIANTS = P24.VARIANTS
STEPS = [(1,), (2,), (3, 4), (5, 6), (7, 8, 9), (10,)]          # ступени тона (как roster/skin.py для Legacy)
STEP = {c: k for k, cs in enumerate(STEPS) for c in cs}
# соответствие волос и растительности: что на фото (надёжно) → какие головы подходят
HAIR_OK = {'red': {'red'}, 'blond': {'blond'}, 'dark': {'dark'}, 'brown': {'brown', 'dark', 'blond'}, 'bald': {'bald'}}
HAIR_FALLBACK = {'red': {'blond', 'brown'}, 'blond': {'brown'}, 'dark': {'brown'}}
BEARD_OK = {'beard': {'beard', 'mustache', 'stubble'}, 'none': {'none', 'stubble'},
            'mustache': {'mustache', 'beard', 'stubble'}, 'stubble': {'stubble', 'mustache', 'beard', 'none'}}
BEARD_PREF = {'beard': {'beard': 0.0, 'mustache': 0.6, 'stubble': 0.8}, 'none': {'none': 0.0, 'stubble': 1.0},
              'mustache': {'mustache': 0.0, 'beard': 0.3, 'stubble': 0.4},
              'stubble': {'stubble': 0.0, 'mustache': 0.3, 'beard': 0.4, 'none': 1.0}}
W = dict(hairL=1.0, hairb=0.5, haira=0.5, beard=1.2, lip=0.4, bald=2.5, volume=0.3, ita=0.5)
KEYS = ('hairL', 'hairb', 'haira', 'beard', 'lip', 'volume', 'ita')
HAIR = ('hairL', 'hairb', 'haira')
TONE_PEN, FALLBACK_PEN, SOFT, ASIAN_PEN, USE = 2.0, 3.0, 1.0, 4.0, 0.35
SEED = 1012


def work():
    return os.path.join(P24.work(), 'heads24')


# --- цвет и области ---------------------------------------------------------------------------------
def srgb2lab(rgb):
    import numpy as np
    c = rgb / 255.0
    c = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    m = np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]])
    xyz = c @ m.T / np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], -1)


def box_px(lab, mask, face, r):
    """Пиксели (Lab) под маской в прямоугольнике r = (x0, x1, y0, y1) в долях рамки лица."""
    import numpy as np
    fx, fy, fw, fh = face
    x0, x1, y0, y1 = r
    h, w = mask.shape
    xa, xb = max(0, int(round(fx + x0 * fw))), min(w, int(round(fx + x1 * fw)))
    ya, yb = max(0, int(round(fy + y0 * fh))), min(h, int(round(fy + y1 * fh)))
    if xb <= xa or yb <= ya:
        return np.zeros((0, 3))
    return lab[ya:yb, xa:xb][mask[ya:yb, xa:xb]]


# --- головы: признаки по текстурам -----------------------------------------------------------------
HREG = {'cheekL': (165, 205, 195, 235), 'cheekR': (307, 347, 195, 235), 'lip': (228, 284, 236, 250),
        'chin': (215, 297, 295, 330), 'jawL': (150, 190, 270, 315), 'jawR': (322, 362, 270, 315),
        'scalp': (100, 412, 0, 40), 'scalpL': (60, 130, 40, 110), 'scalpR': (382, 452, 40, 110)}


def head_features(hid):
    """Признаки типовой головы по texlib_<id>.rx2: развёртка 512² общая у всех голов (лицо, скальп, уши)."""
    import numpy as np
    import kitpaint
    import teamart
    rw = teamart.Rw4.load(G.extracted(f'rendering/player/texlib_{hid}.rx2'))
    tex = {}
    for t in rw.textures:
        w, h, rgba = kitpaint.tex_decode(rw, t)
        tex['hair' if t.name.startswith('hair') else 'head'] = np.frombuffer(bytes(rgba), np.uint8).reshape(h, w, 4)
    lab = srgb2lab(tex['head'][..., :3].astype(np.float32))
    P = lambda k: lab[HREG[k][2]:HREG[k][3], HREG[k][0]:HREG[k][1]].reshape(-1, 3)
    cheeks = np.concatenate([P('cheekL'), P('cheekR')])
    skin = np.median(cheeks, 0)
    rel = lambda px: float((skin[0] - np.median(px[:, 0])) / max(skin[0], 1))
    scalp = np.concatenate([P('scalp'), P('scalpL'), P('scalpR')])
    sc = np.median(scalp, 0)
    cover, cap = 0.0, None
    if 'hair' in tex:
        m = tex['hair'][..., 3] > 160
        cover = float(m.mean())
        if m.sum() > 50:
            cap = np.median(srgb2lab(tex['hair'][..., :3][m].astype(np.float32)), 0)
    # цвет волос: нарисованные на скальпе 0,6 + шапка волос 0,4 (как на иконке и в матче)
    hair = sc if cap is None or cover < 0.02 else 0.6 * sc + 0.4 * cap
    scalp_d = float(skin[0] - np.median(P('scalp')[:, 0]))
    chin, jaw, lip = rel(P('chin')), rel(np.concatenate([P('jawL'), P('jawR')])), rel(P('lip'))
    return dict(ita=math.degrees(math.atan2(skin[0] - 50, skin[2])), hairL=float(hair[0]), haira=float(hair[1]),
                hairb=float(hair[2]), bald=1.0 if cover < 0.02 and scalp_d < 25 else 0.6 if cover < 0.02 else 0.0,
                volume=cover, chin=chin, jaw=jaw, lip=lip, beard=0.45 * chin + 0.35 * jaw + 0.2 * lip)


def head_tones():
    """Тон (skincolor) каждой типовой головы — как у игроков исходной базы Legacy с этой головой; у голов без игроков
    (10 шт.) — тон головы с ближайшим ITA текстуры."""
    db = Tdb(open(G.db, 'rb').read(), load_meta(G.meta))
    t = 'exhibitionplayerbiotable'
    cnt = defaultdict(Counter)
    for r in range(db.by_name[t]['rows']):
        cnt[db.get(t, 'headid', r)][db.get(t, 'skincolor', r)] += 1
    return {h: c.most_common(1)[0][0] for h, c in cnt.items() if h in HEADS}


# --- фото: признаки по портрету игры -----------------------------------------------------------------
_CASC = {}


def detect_face(rgba):
    """Рамка лица (x, y, w, h) — самая большая из найденных каскадом Haar (frontalface_alt2) на сером фоне."""
    import cv2
    import numpy as np
    if 'face' not in _CASC:
        _CASC['face'] = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_alt2.xml')
    a = rgba[..., 3:4].astype(np.float32) / 255
    rgb = (rgba[..., :3].astype(np.float32) * a + 128 * (1 - a)).astype(np.uint8)
    g = cv2.equalizeHist(cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY))
    faces = _CASC['face'].detectMultiScale(g, 1.05, 3, minSize=(40, 40))
    if not len(faces):
        return None
    return tuple(float(v) for v in max(faces, key=lambda f: f[2] * f[3]))


PREG = {'cheekL': (0.18, 0.34, 0.50, 0.66), 'cheekR': (0.66, 0.82, 0.50, 0.66), 'lip': (0.38, 0.62, 0.69, 0.75),
        'chin': (0.36, 0.64, 0.87, 0.99), 'jawL': (0.14, 0.28, 0.74, 0.92), 'jawR': (0.72, 0.86, 0.74, 0.92),
        'top': (0.25, 0.75, -0.14, -0.02)}


def portrait_rgba(path):
    import numpy as np
    import playerhead
    h = playerhead.PlayerHead.load(path)
    w, hh, rgba = h.decode_rgba()
    sw, sh = h.stage
    return np.ascontiguousarray(np.frombuffer(rgba, np.uint8).reshape(hh, w, 4)[:sh, :sw])


def photo_features(rgba):
    import numpy as np
    from scipy.ndimage import binary_erosion, laplace
    face = detect_face(rgba)
    if not face:
        return None
    fx, fy, fw, fh = face
    mask = rgba[..., 3] > 200
    lab = srgb2lab(rgba[..., :3].astype(np.float32))
    P = lambda k: box_px(lab, mask, face, PREG[k])
    cheeks = np.concatenate([P('cheekL'), P('cheekR')])
    if len(cheeks) < 30:
        return None
    skin = cheeks[np.argsort(cheeks[:, 0])][len(cheeks) // 4: len(cheeks) * 3 // 4].mean(0)
    cl = float(np.median(cheeks[:, 0]))
    rows = np.where(mask[:, int(fx + 0.3 * fw): int(fx + 0.7 * fw)].sum(1) >= 3)[0]
    crown = int(rows[0]) if len(rows) else int(fy)
    inner = binary_erosion(mask, iterations=5)              # без каймы вырезки (цветной ореол фона на краях волос)
    hreg = box_px(lab, inner, face, (0.2, 0.8, (crown - fy) / fh, 0.0))
    lap = np.abs(laplace(lab[..., 0]))                       # фактура: волосы — мелкие перепады, лысина — гладко
    tex = box_px(np.repeat(lap[..., None], 3, -1), inner, face, (0.25, 0.75, (crown - fy) / fh, -0.03))
    hp = hreg[np.sqrt(((hreg - skin) ** 2).sum(-1)) >= 12] if len(hreg) else hreg     # без пикселей кожи (лоб)
    if len(hp) >= 15:
        lo, hi = np.percentile(hp[:, 0], [40, 90])
        lit = hp[(hp[:, 0] >= lo) & (hp[:, 0] <= hi)]
        hair = np.median(lit if len(lit) >= 5 else hp, 0)
    else:
        hair = skin
    top = P('top')
    de_top = np.sqrt(((top - skin) ** 2).sum(-1)) if len(top) else np.zeros(1)
    rel = lambda px: float((cl - np.median(px[:, 0])) / max(cl, 1)) if len(px) >= 8 else 0.0
    chin, jaw, lip = rel(P('chin')), rel(np.concatenate([P('jawL'), P('jawR')])), rel(P('lip'))
    return dict(face=[fx, fy, fw, fh], skinL=float(skin[0]), skina=float(skin[1]), skinb=float(skin[2]),
                ita=math.degrees(math.atan2(skin[0] - 50, skin[2])), hairL=float(hair[0]), haira=float(hair[1]),
                hairb=float(hair[2]), bald=float(min(1.0, max(0.0, ((de_top < 12).mean() - 0.5) / 0.4))),
                hair_tex=float(np.median(tex[:, 0])) if len(tex) >= 15 else 0.0, volume=float((fy - crown) / fh),
                chin=chin, jaw=jaw, lip=lip, beard=0.45 * chin + 0.35 * jaw + 0.2 * lip)


def hair_cat(p):
    """(волосы, надёжно): bald / red / blond / dark / brown по фото."""
    L, a, b = p['hairL'], p['haira'], p['hairb']
    hh, hs = math.degrees(math.atan2(b, a)), math.degrees(math.atan2(p['skinb'], p['skina']))
    ch, cs = math.hypot(a, b), math.hypot(p['skina'], p['skinb'])
    tex = p['hair_tex']
    if tex <= 0.05:                                          # над рамкой лица ничего нет (кадр обрезан)
        return 'brown', False
    scalp = abs(hh - hs) < 12 and L >= p['skinL'] - 15 and abs(ch - cs) < 8      # «волосы» цвета кожи — скальп
    if p['volume'] >= 0.15 and scalp and (tex < 2.5 or (p['bald'] >= 0.8 and tex < 3.5)):   # лысина — жёстко: строго
        return 'bald', True
    if (p['bald'] >= 0.8 or scalp) and tex < 4.5 or scalp or p['bald'] >= 0.5:
        return 'bald', False
    if a >= 16 and b >= 18 and hh <= 62 and ch >= cs + 3 and L <= p['skinL'] - 10:
        return 'red', a >= 19 and tex >= 5 and p['bald'] < 0.3
    if L <= 32 and a >= 10 and hh <= 55 and ch >= 0.9 * max(L, 10):       # тёмно-рыжие (медные)
        return 'red', a >= 14 and ch >= 1.25 * max(L, 10) and a >= 0.75 * p['skina'] and tex >= 4 and p['bald'] < 0.3
    if L >= 48 and b >= 12:
        return 'blond', tex >= 4 and p['bald'] < 0.3
    if L >= 40 and hh >= 60:
        return 'blond', False
    if L <= 22:
        return 'dark', True
    if L <= 28:
        return 'dark', False
    return 'brown', True


def beard_cat(p):
    """(растительность, надёжно): beard / mustache / stubble / none по затемнению относительно щёк."""
    c, j, l, s = p['chin'], p['jaw'], p['lip'], p['beard']
    if s >= 0.45 and j >= 0.35:
        return 'beard', True
    if s >= 0.38:
        return 'beard', False
    if (l >= 0.30 or c >= 0.35) and j < 0.30:
        return 'mustache', s >= 0.25
    if s <= 0.12:
        return 'none', True
    if s <= 0.17:
        return 'none', False
    return 'stubble', s >= 0.22


def _photo_job(job):
    artid, path = job
    try:
        return artid, photo_features(portrait_rgba(path))
    except Exception as err:  # noqa: BLE001
        return artid, {'error': str(err)}


_PH = []


def portrait_path(artid, variant):
    import playerhead
    if not _PH:
        import photos
        photos.use_game('legacy')                       # папки портретов Legacy (≤ 60000 → p8001_12000)
        _PH.append(1)
    rel = playerhead.asset_relpath('big', artid).split('/')
    for root in (os.path.join(P24.work(), variant), os.path.join(P24.work(), 'out'), os.path.join(G.big, 'nocache')):
        p = os.path.join(root, *rel)
        if os.path.exists(p):
            return p
    return None


def photo_table(players, variant, jobs=6):
    """{artid: признаки} с кэшем <work>/heads24/photo_feats.json (по пути, размеру и времени файла)."""
    os.makedirs(work(), exist_ok=True)
    fn = os.path.join(work(), 'photo_feats.json')
    cache = json.load(open(fn, encoding='utf-8')) if os.path.exists(fn) else {}
    todo, out = [], {}
    for p in players:
        path = portrait_path(p['artid'], variant)
        if not path:
            continue
        st = os.stat(path)
        stamp = [os.path.relpath(path, P24.GAME_DIR), st.st_size, int(st.st_mtime)]
        c = cache.get(str(p['artid']))
        if c and c.get('stamp') == stamp:
            out[p['artid']] = c['f']
        else:
            todo.append((p['artid'], path, stamp))
    if todo:
        with ProcessPoolExecutor(max_workers=jobs) as pool:
            for (a, f), (_, _, stamp) in zip(pool.map(_photo_job, [(a, pth) for a, pth, _ in todo], chunksize=8), todo):
                cache[str(a)] = {'stamp': stamp, 'f': f}
                out[a] = f
        json.dump(cache, open(fn, 'w', encoding='utf-8'))
    return {a: f for a, f in out.items() if f and 'error' not in f}


# --- подбор ---------------------------------------------------------------------------------------
def zs(vals):
    v = [x for x in vals if x == x]
    m, s = statistics.mean(v), statistics.pstdev(v) or 1.0
    return lambda x: (x - m) / s


class Picker:
    def __init__(self, photos):
        self.lab = {int(k): v for k, v in json.load(open(SPEC, encoding='utf-8')).items() if not k.startswith('_')}
        hf = os.path.join(work(), 'head_feats.json')
        if os.path.exists(hf):
            self.H = {int(k): v for k, v in json.load(open(hf, encoding='utf-8')).items()}
        else:
            self.H = {h: head_features(h) for h in HEADS}
            os.makedirs(work(), exist_ok=True)
            json.dump(self.H, open(hf, 'w', encoding='utf-8'))
        self.tone = head_tones()
        for h in HEADS:
            if h not in self.tone:
                near = min(self.tone, key=lambda x: abs(self.H[x]['ita'] - self.H[h]['ita']))
                self.tone[h] = self.tone[near]
        self.P = photos
        ok = lambda k, x: x['bald'] < 0.5 or k not in HAIR
        self.zh = {k: zs([h[k] for h in self.H.values() if ok(k, h)]) for k in KEYS}
        self.zp = {k: zs([p[k] for p in self.P.values() if ok(k, p)]) for k in KEYS}
        self.ZH = {h: {k: self.zh[k](v[k]) for k in KEYS} for h, v in self.H.items()}
        self.cats = {a: (hair_cat(p), beard_cat(p)) for a, p in self.P.items()}

    def dist(self, p, h):
        hh, zh = self.H[h], self.ZH[h]
        hairw = (1 - p['bald']) * (1 - hh['bald'])
        d = sum(W[k] * (hairw if k in HAIR else 1.0) * (self.zp[k](p[k]) - zh[k]) ** 2 for k in KEYS)
        return d + W['bald'] * (p['bald'] - hh['bald']) ** 2

    def mismatch(self, artid, h):
        """Явное несовпадение головы с фото (надёжные признаки): ['волосы …', 'борода …']."""
        (hc, hs), (bc, bs) = self.cats[artid]
        L = self.lab[h]
        out = []
        # явно: рыжий — у головы не рыжие; блонд/тёмные — у головы не блонд/тёмные и не русые (русые — не явно)
        near = (HAIR_OK.get(hc) or set()) | (set() if hc == 'red' else HAIR_FALLBACK.get(hc, set()))
        if hs and HAIR_OK.get(hc) and L['hair'] not in near:
            out.append(f"волосы: на фото {hc}, у головы {L['hair']}")
        if bs and L['beard'] not in BEARD_OK[bc]:
            out.append(f"лицо: на фото {bc}, у головы {L['beard']}")
        return out

    def agrees(self, artid, h):
        """Не противоречит фото и по ненадёжным признакам (для головы EA из NHL 24)."""
        (hc, _), (bc, _) = self.cats[artid]
        L = self.lab[h]
        return not (HAIR_OK.get(hc) and L['hair'] not in HAIR_OK[hc]) and L['beard'] in BEARD_OK[bc]

    def score(self, artid, skincolor, h):
        """Штраф головы или None (не проходит: тон дальше соседней ступени, волосы/растительность — жёстко)."""
        (hc, hs), (bc, bs) = self.cats[artid]
        L = self.lab[h]
        ps, st = STEP.get(skincolor), STEP.get(self.tone.get(h))
        if ps is None or st is None:
            return None
        if ps != st and (abs(ps - st) > 1 or abs(skincolor - self.tone[h]) > 1):
            return None                            # тон: та же ступень или соседняя при разнице тона не больше 1
        pen = TONE_PEN if ps != st else 0.0
        if L.get('asian'):
            pen += ASIAN_PEN                       # азиатские черты по фото не определить — только по выбору EA
        if HAIR_OK.get(hc) and L['hair'] not in HAIR_OK[hc]:
            if not hs:
                pen += SOFT
            elif L['hair'] in HAIR_FALLBACK.get(hc, ()):
                pen += FALLBACK_PEN
            else:
                return None
        if L['beard'] not in BEARD_OK[bc]:
            if bs:
                return None
            pen += SOFT
        elif bs:
            pen += BEARD_PREF[bc].get(L['beard'], 0.0)
        return pen + self.dist(self.P[artid], h)


def nhl24_heads(players):
    """{строка био: типовая голова игрока в NHL 24} — по имени и дате рождения (однозначно)."""
    by = defaultdict(list)
    for x in P24.nhl24_players():
        by[tuple(x['birth'])].append(x)
    out = {}
    for p in players:
        c = [x for x in by.get(tuple(p['birth']), []) if P24.norm(x['last']) == P24.norm(p['last'])
             and P24.norm(x['first']) == P24.norm(p['first'])]
        if len(c) == 1 and c[0]['headid'] in HEADS:
            out[p['row']] = c[0]['headid']
    return out


def applied(variant):
    fn = os.path.join(work(), f'applied-{variant}.json')
    return {r['game_id']: r for r in json.load(open(fn, encoding='utf-8'))} if os.path.exists(fn) else {}


def cmd_plan(variant, jobs=6):
    players = P24.legacy_players(variant)
    gen = [p for p in players if p['headid'] in HEADS and p['hasportrait'] and p['file']]
    photos = photo_table(gen, variant, jobs)
    pk = Picker(photos)
    prior = nhl24_heads(gen)
    done = applied(variant)
    gen = [p for p in gen if p['artid'] in photos]
    plan, change = [], []
    for p in gen:
        a, cur, pr = p['artid'], p['headid'], prior.get(p['row'])
        if done.get(p['game_id'], {}).get('new') == cur:
            continue                                         # уже поставлено прежним прогоном
        if pr and pr != cur and pk.score(a, p['skincolor'], pr) is not None and pk.agrees(a, pr):
            plan.append((p, pr, 'голова EA из NHL 24'))
            continue
        mm = pk.mismatch(a, cur)
        if mm:
            change.append((p, mm))
    # подбор для явных несовпадений: одна голова на команду (с учётом тех, кто голову не меняет), штраф за частоту
    moving = {p['row'] for p, _ in change} | {p['row'] for p, _, _ in plan}
    team_heads, uses = defaultdict(set), Counter()
    newhead = {p['row']: h for p, h, _ in plan}
    for p in players:
        h = newhead.get(p['row'], p['headid'] if p['row'] not in moving else None)
        if h is not None:
            for t in p['teams']:
                team_heads[t].add(h)
            uses[h] += 1
    avg = max(1.0, len(players) / len(HEADS))
    rnd = random.Random(SEED)
    rnd.shuffle(change)
    left = 0
    for p, mm in change:
        sc = []
        for h in HEADS:
            s = pk.score(p['artid'], p['skincolor'], h)
            if s is None or any(h in team_heads[t] for t in p['teams']):
                continue
            sc.append((s + USE * uses[h] / avg, h))
        sc = [x for x in sc if not pk.mismatch(p['artid'], x[1])]      # новая голова должна снимать несовпадение
        if not sc:
            left += 1
            continue
        h = min(sc)[1]
        for t in p['teams']:
            team_heads[t].add(h)
        uses[h] += 1
        plan.append((p, h, '; '.join(mm)))
    rows = []
    for p, h, why in sorted(plan, key=lambda x: x[0]['row']):
        (hc, hs), (bc, bs) = pk.cats[p['artid']]
        rows.append({'row': p['row'], 'game_id': p['game_id'], 'artid': p['artid'], 'name': f"{p['first']} {p['last']}",
                     'league': p['league'], 'skincolor': p['skincolor'], 'old': p['headid'], 'new': h, 'why': why,
                     'nhl24': prior.get(p['row']), 'photo': {'hair': hc, 'hair_sure': hs, 'face': bc, 'face_sure': bs}})
    out = os.path.join(work(), f'plan-{variant}.json')
    json.dump(rows, open(out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    by = Counter('голова EA из NHL 24' if r['why'] == 'голова EA из NHL 24' else
                 'волосы' if r['why'].startswith('волосы') and 'лицо' not in r['why'] else
                 'растительность' if r['why'].startswith('лицо') else 'волосы и растительность' for r in rows)
    print(f'{variant}: типовых голов с портретом {len(gen)}, сменить {len(rows)} ({dict(by.most_common())}); '
          f'явное несовпадение без подходящей головы — {left}; уже поставлено раньше — {len(done)} → {out}')
    return rows


def cmd_apply(variant):
    fn = os.path.join(work(), f'plan-{variant}.json')
    rows = json.load(open(fn, encoding='utf-8'))
    db_path = os.path.join(P24.work(), variant, 'db', 'nhlng.db')
    db = Tdb(open(db_path, 'rb').read(), load_meta(os.path.join(os.path.dirname(db_path), 'nhlng-meta.xml')))
    t = 'exhibitionplayerbiotable'
    for r in rows:
        if db.get(t, 'game_id', r['row']) != r['game_id'] or db.get(t, 'headid', r['row']) != r['old']:
            raise SystemExit(f"{db_path}: строка {r['row']} ({r['name']}) не та, что в плане — plan заново")
    for r in rows:
        db.set(t, 'headid', r['row'], r['new'])
    db.fix()
    assert not db.verify()
    with open(db_path, 'wb') as f:
        f.write(db.d)
    subprocess.run([sys.executable, os.path.join(TOOLS, 'legacy_data', 'draft_roster.py'), db_path,
                    os.path.join(os.path.dirname(db_path), 'draft_roster.db')], check=True)
    done = applied(variant)
    stamp = time.strftime('%Y-%m-%d %H:%M')
    for r in rows:
        done[r['game_id']] = dict(r, applied=stamp) if r['game_id'] not in done else dict(done[r['game_id']], new=r['new'],
                                                                                         applied=stamp)
    json.dump(sorted(done.values(), key=lambda r: r['row']), open(os.path.join(work(), f'applied-{variant}.json'), 'w',
                                                                   encoding='utf-8'), ensure_ascii=False, indent=1)
    print(f'{variant}: headid сменён у {len(rows)} → {db_path} (draft_roster.db заново)')


def cmd_save(save, write, variant):
    """Сохранённый состав (сейв ROSTER): игра грузит его целиком, вместе с headid. Переносится смена головы из
    applied-<вариант>.json — строкам exhibitionplayerbiotable с тем же game_id, у которых в сейве прежняя голова
    (другая — правка пользователя, не трогается). Копия до правки — <work>/backup-saves/, после записи — проверка CRC."""
    from tdb import SaveFile
    done = applied(variant)
    meta = load_meta(os.path.join(P24.work(), variant, 'db', 'nhlng-meta.xml'))
    sf = SaveFile(open(save, 'rb').read(), meta)
    sv = sf.db
    t = 'exhibitionplayerbiotable'
    n = same = other = 0
    rows = []
    for r in sv.live_rows(t):
        d = done.get(sv.get(t, 'game_id', r))
        if not d:
            continue
        h = sv.get(t, 'headid', r)
        if h == d['new']:
            same += 1
        elif h == d['old']:
            rows.append((r, d['new']))
        else:
            other += 1
    print(f'{os.path.basename(save)}: смен голов в {variant}: {len(done)}; в сейве к замене {len(rows)}, уже новая '
          f'{same}, другая голова (правка в сейве — не трогаю) {other}, нет игрока {len(done) - len(rows) - same - other}')
    if not write or not rows:
        print('без --write: сейв не изменён' if rows else 'менять нечего')
        return
    for r, h in rows:
        sv.set(t, 'headid', r, h)
        n += 1
    out = sf.bytes()
    if SaveFile(out, meta).verify():
        raise SystemExit('проверка CRC после правки не прошла — сейв не записан')
    bk = os.path.join(P24.work(), 'backup-saves', 'heads24-' + time.strftime('%Y%m%d-%H%M%S'))
    os.makedirs(bk, exist_ok=True)
    shutil.copyfile(save, os.path.join(bk, os.path.basename(save)))
    with open(save, 'wb') as f:
        f.write(out)
    print(f'записано: headid у {n}; копия до правки — {bk}')


def cmd_sheet(variant, n, out):
    from PIL import Image, ImageDraw, ImageFont
    rows = json.load(open(os.path.join(work(), f'plan-{variant}.json'), encoding='utf-8'))
    if not rows:
        rows = list(applied(variant).values())
    rnd = random.Random(SEED)
    by = defaultdict(list)
    for r in rows:
        by[r['why'].split(':')[0]].append(r)
    pick = []
    while len(pick) < min(n, len(rows)):
        for k in sorted(by):
            if by[k] and len(pick) < n:
                pick.append(by[k].pop(rnd.randrange(len(by[k]))))
    ff = os.path.join(os.environ.get('WINDIR', r'C:\Windows'), 'Fonts', 'segoeui.ttf')
    font = ImageFont.truetype(ff, 13) if os.path.exists(ff) else ImageFont.load_default()
    import roster.skin as skin
    cw, chh, cols = 470, 176, 2
    sheet = Image.new('RGB', (cols * cw, ((len(pick) + 1) // cols) * chh + 30), (44, 44, 48))
    d = ImageDraw.Draw(sheet)
    d.text((8, 6), 'фото (портрет в игре)  |  было  |  стало        (волосы/лицо по фото; ? — ненадёжно)', fill=(220, 220, 220),
           font=font)
    for i, r in enumerate(pick):
        x0, y0 = (i % cols) * cw, (i // cols) * chh + 30
        rgba = portrait_rgba(portrait_path(r['artid'], variant))
        fx, fy, fw, fh = detect_face(rgba) or (150, 60, 140, 140)
        im = Image.fromarray(rgba, 'RGBA').crop((int(fx - 0.3 * fw), max(0, int(fy - 0.5 * fh)), int(fx + 1.3 * fw),
                                                int(fy + 1.1 * fh))).resize((120, 120))
        sheet.paste(im, (x0 + 4, y0 + 2), im)
        for k, h in enumerate((r['old'], r['new'])):
            w, hh, px = skin.decode_icon(G.extracted(f'fe/ion/artassets/createplayer/head/head{h}.big'))
            ic = Image.frombytes('RGBA', (w, hh), px).crop((18, 0, 122, 104)).resize((120, 120))
            sheet.paste(ic, (x0 + 150 + k * 160, y0 + 2), ic)
            d.text((x0 + 152 + k * 160, y0 + 123), str(h) + (' = NHL 24' if h == r.get('nhl24') else ''),
                   fill=(255, 220, 0) if k else (170, 170, 170), font=font)
        ph = r['photo']
        d.text((x0 + 4, y0 + 123), r['name'], fill=(255, 255, 255), font=font)
        d.text((x0 + 4, y0 + 140), f"{P24.LEAGUE_RU.get(r['league'], r['league'])}, тон {r['skincolor']}; фото: волосы "
               f"{ph['hair']}{'' if ph['hair_sure'] else '?'}, лицо {ph['face']}{'' if ph['face_sure'] else '?'}",
               fill=(150, 200, 255), font=font)
        d.text((x0 + 4, y0 + 157), r['why'][:72], fill=(255, 190, 120), font=font)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    sheet.save(out)
    print(f'лист: {len(pick)} → {out}')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('cmd', choices=('plan', 'apply', 'sheet', 'save'))
    ap.add_argument('save', nargs='?')
    ap.add_argument('--variant', action='append', choices=VARIANTS)
    ap.add_argument('--write', action='store_true')
    ap.add_argument('--jobs', type=int, default=6)
    ap.add_argument('--n', type=int, default=24)
    ap.add_argument('--out')
    a = ap.parse_args()
    variants = a.variant or [v for v in VARIANTS if os.path.exists(os.path.join(P24.work(), v, 'db', 'nhlng.db'))]
    if a.cmd == 'plan':
        for v in variants:
            cmd_plan(v, a.jobs)
    elif a.cmd == 'apply':
        for v in variants:
            cmd_apply(v)
    elif a.cmd == 'sheet':
        v = variants[-1]
        cmd_sheet(v, a.n, a.out or os.path.join(work(), f'sheet-{v}.png'))
    else:
        cmd_save(a.save, a.write, (a.variant or ['out-ahl32'])[0])


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
