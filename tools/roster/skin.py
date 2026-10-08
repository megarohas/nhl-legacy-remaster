"""Тон кожи (`--skin`): типовая голова игрока — под видимый цвет кожи на его официальном фото.

ПРАВИЛО: тон определяется ТОЛЬКО по пикселям кожи лица на официальном портрете игрока
(game/work/roster-cache/photos/<сезон>/<nhl_id>.png — портреты НХЛ 336×336 на прозрачном фоне).
Имя, страна, гражданство, место рождения и т. п. не используются нигде. Нет фото или на фото не
нашлось кожи — значение по умолчанию, как без --skin (голова самого частого тона базы, по хэшу
имени). Ручные поправки — game/work/roster/skin-overrides.json; лист проверки — skin-sheet.html в
папке конвейера (фото, замер, выбранная голова).

Шкала игры (поле `skincolor`, 4 бита; сверено по базе): у каждой типовой головы (`headid` 10000+)
свой постоянный тон — 1, 2, 3, 4, 6, 9, 10; 1–4 — светлые и смуглые (внутри класса головы заметно
разные), 6, 9, 10 — всё темнее; 5, 7, 8 в базе не встречаются. Как голова выглядит в игре, видно по
её иконке (fe/ion/artassets/createplayer/head/head<id>.big, k_8_8_8_8 256×128) — по ней же тем же
способом меряется тон каждой головы, поэтому голова выбирается по тону иконки, а класс берётся у
выбранной головы (как в базе).

Замер (одинаково для фото и иконок): прямоугольник лица (лоб, глаза, нос, щёки до рта: по макушке,
центру и ширине головы из альфа-канала); пиксели, похожие на кожу (CIELAB: светлота 12–92,
насыщенность ≥ 7, тон 12°–85° — без серых волос, бороды, белков и зубов), из них — средняя половина
по светлоте (без теней и бликов); если нижняя половина прямоугольника (щёки) светлее всего на 12°+
ITA после поправки на съёмку и сама светлая (≥ 35°) — лоб закрыт волосами или тенью — берётся она (с
поправкой на обычную разницу) и ставится
«проверить»; тон = ITA° = atan((L* − 50) / b*) (Individual Typology Angle,
Chardon 1991; > 55 очень светлая, 41–55 светлая, 28–41 средняя, 10–28 смуглая, −30…10
коричневая, < −30 тёмная).
Поправка на свет съёмки: у портретов одного клуба одна съёмка, а медианы клубов расходятся на 40°
ITA (свет и баланс белого разные). Поэтому L* и b* игрока сдвигаются на разницу «эталон съёмки −
общий эталон»: эталон — 60-й перцентиль L* и 40-й b* всех фото этой съёмки (папка адреса фото:
сезон/клуб; меньше 8 фото — эталон того же клуба 2026/27 или без поправки).
Тон игры — по ITA фото после поправки (x): x ≥ 42 — класс 1; 30–42 — 2; 21–30 — 3 или 4 (смуглые и
оливковые головы); −10…21 — 6 (светло-коричневые), но при розоватом тоне (угол цвета < 45°: румянец,
загар светлой кожи) — 3/4; −20…−10 — 9; < −20 — 10. ITA иконок (замер теми же правилами) на
границе «оливковая голова в тёмном рендере / коричневая» не различает (у 10178 и 10181 оба около
−3°), поэтому класс решает фото, а иконка — только выбор головы внутри класса: 5 ближайших по ITA к
«цели» (ITA фото, переведённый в шкалу иконок прямой через медианы фото и иконок класса 1, наклон —
по сопоставленным игрокам с тёмными головами EA, ≈ 1,5), из них — по хэшу имени. x в 10–30° (там
рядом смуглые фото светлокожих при тёплом свете и коричневая кожа) или розоватый тон при x < 26° —
«проверить» на листе. Сопоставленным игрокам базы голова EA оставляется, кроме грубого расхождения
(класс по фото дальше чем на 2 ступени шкалы 1 · 2 · 3/4 · 6 · 9 · 10 и замер уверенный).
"""
import html
import math
import os
import statistics
import zlib
from collections import defaultdict

from .common import SEASON, read_json, write_json

SKIN_CLASSES = (1, 2, 3, 4, 6, 9, 10)          # тоны типовых голов в базе
# ступени тона: (ITA фото после поправки не меньше, классы голов); последняя — всё темнее
STEPS = [(42.0, (1,)), (30.0, (2,)), (21.0, (3, 4)), (-10.0, (6,)), (-20.0, (9,)), (-999.0, (10,))]
PINK_HUE, PINK_ITA = 45.0, 26.0                # розоватый тон при тёмном замере — не коричневый
ICON_DIR = ('extracted', 'big', 'cache', 'fe', 'ion', 'artassets', 'createplayer', 'head')
ICON_BOX = (42, 36, 98, 82)                    # лицо на иконке 140×108 (анфас по центру)
SESSION_MIN = 8                                # фото в съёмке, чтобы взять её эталон
NEAREST = 5
UNSURE = (10.0, 30.0)
SLOPE_DEFAULT = 1.5
METHOD = 6                                     # версия замера (кэш фото пересчитывается при смене)
# нижняя половина прямоугольника (щёки, нос, губа) у портретов НХЛ в среднем темнее всего прямоугольника на
# 2,74 L* и 0,38 b* (медианы по 837 фото); если она после поправки на съёмку СВЕТЛЕЕ на 12°+ ITA и сама
# светлая (≥ 35°), верх (лоб) закрыт волосами или тенью — берётся она (отметка «проверить»)
LOWER_DL, LOWER_DB, LOWER_JUMP, LOWER_LIGHT = 2.74, 0.38, 12.0, 35.0


# --- цвет ---------------------------------------------------------------------------------------
def _lin(c):
    c /= 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


_LIN = [_lin(i) for i in range(256)]


def lab(r, g, b):
    """sRGB (0–255) → CIELAB (D65)."""
    R, G, B = _LIN[r], _LIN[g], _LIN[b]
    x = (0.4124 * R + 0.3576 * G + 0.1805 * B) / 0.95047
    y = 0.2126 * R + 0.7152 * G + 0.0722 * B
    z = (0.0193 * R + 0.1192 * G + 0.9505 * B) / 1.08883
    f = lambda t: t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116
    fx, fy, fz = f(x), f(y), f(z)
    return 116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)


def ita(L, b):
    return math.degrees(math.atan2(L - 50, b)) if b else (90.0 if L > 50 else -90.0)


def measure(rgba, w, box, alpha_min=200):
    """Тон кожи в прямоугольнике box = (x0, y0, x1, y1): {'L', 'a', 'b', 'ita', 'hue', 'n', 'share'} или None."""
    x0, y0, x1, y1 = box
    px, total = [], 0
    for y in range(y0, y1):
        for x in range(x0, x1):
            o = (y * w + x) * 4
            if rgba[o + 3] < alpha_min:
                continue
            total += 1
            L, a, b = lab(rgba[o], rgba[o + 1], rgba[o + 2])
            chroma = math.hypot(a, b)
            hue = math.degrees(math.atan2(b, a))
            if 12 <= L <= 92 and chroma >= 7 and 12 <= hue <= 85:
                px.append((L, a, b))
    if len(px) < 60 or not total:
        return None
    px.sort()
    mid = px[len(px) // 4: len(px) * 3 // 4]                     # средняя половина по светлоте
    L = statistics.mean(p[0] for p in mid)
    a = statistics.mean(p[1] for p in mid)
    b = statistics.mean(p[2] for p in mid)
    return {'L': round(L, 2), 'a': round(a, 2), 'b': round(b, 2), 'ita': round(ita(L, b), 2),
            'hue': round(math.degrees(math.atan2(b, a)), 1), 'n': len(px), 'share': round(len(px) / total, 3)}


def head_box(rgba, w, h, thr=128):
    """Прямоугольник лица на портрете с прозрачным фоном: по макушке, центру и ширине головы."""
    top = None
    for y in range(h):
        if sum(1 for x in range(w // 3, 2 * w // 3) if rgba[(y * w + x) * 4 + 3] > thr) >= 3:
            top = y
            break
    if top is None:
        return None
    yy = min(h - 1, top + int(0.13 * h))                         # уровень лба: волосы уже не выше макушки
    cx = w // 2
    if rgba[(yy * w + cx) * 4 + 3] <= thr:
        return None
    left = right = cx
    while left - 1 >= 0 and rgba[(yy * w + left - 1) * 4 + 3] > thr:
        left -= 1
    while right + 1 < w and rgba[(yy * w + right + 1) * 4 + 3] > thr:
        right += 1
    hw = right - left + 1
    c = (left + right) // 2
    y0, y1 = top + int(0.30 * hw), top + int(0.95 * hw)          # от лба до рта
    x0, x1 = c - int(0.28 * hw), c + int(0.28 * hw)              # без висков и ушей
    return max(0, x0), max(0, y0), min(w, x1), min(h, y1)


def photo_tone(path):
    """Тон кожи на портрете (PNG с альфой) или None. Если нижняя половина лица заметно светлее всего
    прямоугольника (волосы или тень на лбу), берётся она — с поправкой на обычную разницу — и ставится
    отметка fix (на листе — «проверить»)."""
    import playerhead
    w, h, rgba = playerhead.png_read(path)
    box = head_box(rgba, w, h)
    if not box:
        return None
    m = measure(rgba, w, box)
    if not m:
        return None
    x0, y0, x1, y1 = box
    low = measure(rgba, w, (x0, y0 + (y1 - y0) // 2, x1, y1))
    if low:                                       # нижняя половина в шкале всего прямоугольника
        L, b = low['L'] + LOWER_DL, low['b'] + LOWER_DB
        m['low'] = {'L': round(L, 2), 'a': low['a'], 'b': round(b, 2), 'ita': round(ita(L, b), 2), 'hue': low['hue']}
    m['box'] = list(box)
    return m


# --- иконки голов игры ----------------------------------------------------------------------------
def decode_icon(path):
    """head<id>.big → (w, h, RGBA) области сцены: текстура k_8_8_8_8, тайлинг Xenos, порядок 8in32."""
    import playerhead
    head = playerhead.PlayerHead.load(path)
    t = head.tex
    if t.fmt != 6:
        raise ValueError(f'{path}: формат {t.fmt}, ожидался k_8_8_8_8')
    pitch = max(t.pitch, t.width)
    sw, sh = head.stage
    out = bytearray(sw * sh * 4)
    for y in range(sh):
        for x in range(sw):
            o = playerhead.tiled_offset_2d(x, y, pitch, 2) if t.tiled else (y * pitch + x) * 4
            px = t.data[o:o + 4]
            if t.endian == 2:
                px = px[::-1]
            b, g, r, a = px
            i = (y * sw + x) * 4
            out[i:i + 4] = bytes((r, g, b, a))
    return sw, sh, bytes(out)


def _cache_dir(game):
    return os.path.join(game, 'work', 'roster-cache', 'skin')


def icon_tones(game, heads):
    """{headid: тон иконки} для типовых голов; кэш — roster-cache/skin/heads.json, PNG иконок — skin/icons/."""
    cache = os.path.join(_cache_dir(game), 'heads.json')
    got = {int(k): v for k, v in (read_json(cache, {}) or {}).items()}
    changed = False
    for hid in heads:
        png = os.path.join(_cache_dir(game), 'icons', f'head{hid}.png')
        if hid in got and (got[hid] is None or os.path.exists(png)):
            continue
        path = os.path.join(game, *ICON_DIR, f'head{hid}.big')
        if not os.path.exists(path):
            got[hid] = None
            changed = True
            continue
        import playerhead
        w, h, rgba = decode_icon(path)
        os.makedirs(os.path.dirname(png), exist_ok=True)
        playerhead.png_write(png, w, h, rgba)
        got[hid] = measure(rgba, w, ICON_BOX, alpha_min=128)
        changed = True
    if changed:
        write_json(cache, {str(k): v for k, v in sorted(got.items())})
    return got


def photo_path(game, nhl_id):
    return os.path.join(game, 'work', 'roster-cache', 'photos', str(SEASON), f'{nhl_id}.png')


def photo_tones(game, players):
    """{nhl_id: тон фото или None} с кэшем roster-cache/skin/photos.json (по размеру и времени файла)."""
    cache = os.path.join(_cache_dir(game), 'photos.json')
    got = read_json(cache, {}) or {}
    out, changed = {}, False
    for p in players:
        fn = photo_path(game, p['nhl_id'])
        key = str(p['nhl_id'])
        if not os.path.exists(fn):
            out[p['nhl_id']] = None
            continue
        st = os.stat(fn)
        stamp = [st.st_size, int(st.st_mtime), METHOD]
        if key in got and got[key].get('stamp') == stamp:
            out[p['nhl_id']] = got[key]['tone']
            continue
        tone = photo_tone(fn)
        got[key] = {'stamp': stamp, 'tone': tone}
        out[p['nhl_id']] = tone
        changed = True
    if changed:
        write_json(cache, dict(sorted(got.items(), key=lambda kv: int(kv[0]))))
    return out


def session_of(p):
    """Съёмка портрета — папка адреса фото НХЛ: (сезон, клуб)."""
    parts = (p.get('photo') or '').split('/')
    return (parts[-3], parts[-2]) if len(parts) >= 3 else ('', '')


def _q(xs, f):
    xs = sorted(xs)
    return xs[int(f * (len(xs) - 1))]


# --- выбор головы -------------------------------------------------------------------------------
class SkinModel:
    """Тоны иконок голов, поправка на съёмку, перевод фото → шкала иконок, выбор головы."""

    def __init__(self, game, generic_heads, players, matched_heads, log=print):
        """generic_heads: {headid: skincolor} типовых голов базы; players — записи players.json (с полем
        photo); matched_heads: {nhl_id: headid} сопоставленных игроков с типовой головой (наклон перевода)."""
        self.game = game
        self.head_skin = dict(generic_heads)
        self.icon = icon_tones(game, sorted(generic_heads))
        self.tone = photo_tones(game, players)
        self.session = {p['nhl_id']: session_of(p) for p in players}
        # эталоны съёмок
        by = defaultdict(list)
        for pid, t in self.tone.items():
            if t:
                by[self.session[pid]].append(t)
        self.ref = {s: (_q([t['L'] for t in ts], 0.6), _q([t['b'] for t in ts], 0.4))
                    for s, ts in by.items() if len(ts) >= SESSION_MIN}
        # общий эталон и медиана — по съёмкам НХЛ (сезон из 8 цифр в адресе), чтобы портреты других лиг
        # (--league) не сдвигали замер игроков НХЛ
        nhl = [r for s, r in self.ref.items() if len(s[0]) == 8] or list(self.ref.values())
        self.L0 = statistics.median(r[0] for r in nhl) if nhl else 0.0
        self.b0 = statistics.median(r[1] for r in nhl) if nhl else 0.0
        self.norm = {pid: self.normalized(pid) for pid, t in self.tone.items() if t}
        # перевод: через (медиана фото, медиана иконок класса 1), наклон — по тёмным головам EA
        ones = [self.icon[h]['ita'] for h, s in generic_heads.items() if s == 1 and self.icon.get(h)]
        self.icon_mid = statistics.median(ones) if ones else 39.5
        mid = [x for pid, x in self.norm.items() if len(self.session.get(pid, ('',))[0]) == 8] or list(self.norm.values())
        self.photo_mid = statistics.median(mid) if mid else 48.0
        slopes = []
        for pid, hid in matched_heads.items():
            x = self.norm.get(pid)
            ic = (self.icon.get(hid) or {}).get('ita')
            if x is not None and ic is not None and x < self.photo_mid - 20 and generic_heads.get(hid) in (6, 9, 10):
                slopes.append((ic - self.icon_mid) / (x - self.photo_mid))
        self.slope = statistics.median(slopes) if slopes else SLOPE_DEFAULT
        self.slope_n = len(slopes)
        self.pool = sorted((h for h in generic_heads if self.icon.get(h)), key=lambda h: self.icon[h]['ita'])

    def normalized(self, pid, part=None):
        t = self.tone[pid] if part is None else self.tone[pid].get(part)
        if t is None:
            return None
        s = self.session.get(pid, ('', ''))
        ref = self.ref.get(s) or self.ref.get((str(SEASON), s[1]))
        if not ref:
            return t['ita']
        return ita(t['L'] - ref[0] + self.L0, t['b'] - ref[1] + self.b0)

    def target(self, x):
        return self.icon_mid + self.slope * (x - self.photo_mid)

    @staticmethod
    def step(x, hue):
        """Номер ступени тона (0 — самая светлая) по ITA фото после поправки и углу цвета."""
        for k, (lo, _) in enumerate(STEPS):
            if x >= lo:
                if STEPS[k][1] == (6,) and hue < PINK_HUE:
                    return k - 1                         # розоватый: смуглый, не коричневый
                return k
        return len(STEPS) - 1

    @staticmethod
    def step_of_class(c):
        return next(k for k, (_, cs) in enumerate(STEPS) if c in cs)

    def choose(self, p):
        """{'head', 'skin', 'step', 'photo_ita', 'norm', 'target', 'unsure'} по фото; None — фото нет."""
        pid = p['nhl_id']
        t = self.tone.get(pid)
        if not t:
            return None
        x = self.norm[pid]
        hue = t.get('hue', 50.0)
        fix = False
        xl = self.normalized(pid, 'low')
        if xl is not None and xl - x > LOWER_JUMP and xl >= LOWER_LIGHT:
            x, hue, fix = xl, t['low'].get('hue', hue), True      # лоб закрыт волосами/тенью — по щекам
        pink = x < PINK_ITA and hue < PINK_HUE
        k = self.step(x, hue)
        unsure = UNSURE[0] <= x <= UNSURE[1] or pink or fix
        tgt = self.target(x)
        pool = [h for h in self.pool if self.head_skin[h] in STEPS[k][1]]
        near = sorted(pool, key=lambda h: (abs(self.icon[h]['ita'] - tgt), h))[:NEAREST]
        head = near[zlib.crc32(f"{p['first']} {p['last']}".encode()) % len(near)]
        return {'head': head, 'skin': self.head_skin[head], 'step': k, 'photo_ita': t['ita'], 'norm': round(x, 1),
                'by_cheeks': fix,
                'target': round(tgt, 1), 'icon_ita': self.icon[head]['ita'], 'hue': hue, 'unsure': unsure,
                'session': '/'.join(self.session.get(pid, ('', '')))}

    def summary(self):
        return {'sessions': len(self.ref), 'L0': round(self.L0, 2), 'b0': round(self.b0, 2),
                'photo_mid': round(self.photo_mid, 1), 'icon_mid': round(self.icon_mid, 1),
                'slope': round(self.slope, 3), 'slope_from': self.slope_n, 'heads': len(self.pool)}


def load_overrides(game):
    """game/work/roster/skin-overrides.json: {"<nhl_id>": {"skin": 6} | {"head": 10092}, …}."""
    path = os.path.join(game, 'work', 'roster', 'skin-overrides.json')
    data = read_json(path, None)
    if data is None:
        write_json(path, {'_': 'Ручные поправки тона кожи: "<NHL ID>": {"skin": 1|2|3|4|6|9|10} или {"head": <headid 10000+>}, '
                               'необязательно "note". Замер по фото и выбранная голова — skin-sheet.html в папке конвейера; '
                               'после правки — заново write (python tools/roster write --skin …).'})
        return {}
    return {str(k): v for k, v in data.items() if not str(k).startswith('_')}


# --- лист проверки --------------------------------------------------------------------------------
def sheet(path, game, rows, summary):
    """skin-sheet.html: фото, замер, выбранная голова (иконка игры) — для проверки глазами.
    rows: [{'nhl_id', 'name', 'team', 'new', 'how', 'choice', 'final_head', 'final_skin', 'note'}]."""
    base = os.path.dirname(os.path.abspath(path))
    rel = lambda p: os.path.relpath(p, base).replace(os.sep, '/')
    css = """
:root{--bg:#f4f4f2;--fg:#1d1d1f;--card:#fff;--line:#d8d8d4;--warn:#b35c00;--mute:#6b6b70}
@media (prefers-color-scheme:dark){:root{--bg:#18181a;--fg:#ececee;--card:#232326;--line:#3a3a3e;--warn:#ffb057;--mute:#a0a0a8}}
body{background:var(--bg);color:var(--fg);font:14px/1.4 system-ui,sans-serif;margin:16px}
h1{font-size:20px;margin:0 0 8px} p{max-width:900px;color:var(--mute)}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:10px}
.c{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:8px;display:grid;
   grid-template-columns:96px 96px;gap:6px;align-items:start}
.c.u{border-color:var(--warn);border-width:2px}
.ph{width:96px;height:96px;object-fit:cover;object-position:50% 22%;background:#888;border-radius:4px}
.hd{width:96px;height:74px;object-fit:cover;object-position:50% 0;background:#888;border-radius:4px}
.t{grid-column:1/3;font-size:12px} .t b{font-size:13px} .w{color:var(--warn);font-weight:600}
.m{color:var(--mute)}
"""
    out = ['<!doctype html><html lang="ru"><head><meta charset="utf-8">',
           '<meta name="viewport" content="width=device-width,initial-scale=1">',
           '<title>Тон кожи: проверка</title>', f'<style>{css}</style></head><body>',
           '<h1>Тон кожи по фото: проверка</h1>',
           '<p>Слева — официальный портрет, справа — выбранная типовая голова игры (её иконка). Тон определён '
           'только по коже лица на портрете (с поправкой на свет съёмки клуба). Оранжевая рамка — '
           '«проверить»: замер в зоне, где смуглое фото светлокожего и коричневая кожа близки. Исправить — '
           'в <code>game/work/roster/skin-overrides.json</code>: <code>"&lt;NHL ID&gt;": {"skin": 1|2|3|4|6|9|10}</code> '
           'или <code>{"head": 10092}</code>, затем снова write с --skin. '
           f"Съёмок с эталоном: {summary.get('sessions')}, наклон перевода фото → иконки: {summary.get('slope')}.</p>"]
    plain = lambda r: not r.get('kind')
    groups = [('Проверить', [r for r in rows if r['choice'] and r['choice']['unsure'] and plain(r)]),
              ('Голова EA заменена (по фото тон дальше двух ступеней)', [r for r in rows if r.get('kind') == 'replaced']),
              ('Ручные поправки (skin-overrides.json)', [r for r in rows if r.get('kind') == 'override']),
              ('Остальные (от тёмного к светлому)', [r for r in rows if r['choice'] and not r['choice']['unsure'] and plain(r)]),
              ('Без фото — по умолчанию', [r for r in rows if not r['choice'] and plain(r)])]
    for title, rs in groups:
        if not rs:
            continue
        rs = sorted(rs, key=lambda r: (r['choice'] or {}).get('norm', 99))
        out.append(f'<h2>{html.escape(title)} ({len(rs)})</h2><div class="grid">')
        for r in rs:
            ch = r['choice'] or {}
            photo = photo_path(game, r['nhl_id'])
            icon = os.path.join(_cache_dir(game), 'icons', f"head{r['final_head']}.png")
            img = (f'<img class="ph" loading="lazy" src="{html.escape(rel(photo))}" alt="">' if os.path.exists(photo)
                   else '<div class="ph"></div>')
            hd = (f'<img class="hd" loading="lazy" src="{html.escape(rel(icon))}" alt="">' if os.path.exists(icon)
                  else '<div class="hd"></div>')
            meas = (f"ITA фото {ch['photo_ita']:.0f}° → с поправкой {ch['norm']:.0f}° → цель {ch['target']:.0f}°, "
                    f"иконка {ch['icon_ita']:.0f}°" if ch else 'фото нет')
            flag = ' <span class="w">проверить</span>' if ch.get('unsure') and not r.get('kind') else ''
            note = f"<br><span class=\"w\">{html.escape(r['note'])}</span>" if r.get('note') else ''
            out.append(f'<div class="c{" u" if flag else ""}">{img}{hd}<div class="t"><b>{html.escape(r["name"])}</b> '
                       f'<span class="m">{html.escape(r["team"])} · ID {r["nhl_id"]} · {"новый" if r["new"] else "в базе"}</span>{flag}<br>'
                       f'тон {r["final_skin"]}, голова {r["final_head"]}<br><span class="m">{html.escape(meas)}</span>{note}</div></div>')
        out.append('</div>')
    out.append('</body></html>')
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        f.write('\n'.join(out))
