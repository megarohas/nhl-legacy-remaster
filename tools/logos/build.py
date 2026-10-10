"""Логотипы клубов НХЛ 2026/27 для NHL Legacy: официальные SVG НХЛ (assets.nhle.com) → наборы интерфейса
t/s/d/c/w/r, баннер под сводом, прожектор, фон карточки игрока pb и значок ленты новостей — в раскладке cache:.
Описание — docs/logos-2026.md. Ничего не ставит.

    venv/python tools/logos/build.py [КЛУБ…] [--stages svg,reg,spec,ui,extra,verify] [--out DIR] [--work DIR]
                                     [--sets t,s,d,c,w,r,banner,spot,pb,tw]

КЛУБ — abbr из tools/logos/clubs.json (по умолчанию все клубы без "keep"). Этапы:
  svg    — знаки ® и ™ из SVG (svgclean) → WORK/svg/;
  reg    — кадр EA по клубу: где у EA в s/c/w/значке/pb стоит логотип (сопоставление нового логотипа с картинками
           EA того же клуба, eafocus.register) и цвета «таблетки» s по картинке EA → WORK/reg/<КЛУБ>.json, листы
           проверки WORK/reg/<КЛУБ>_<набор>.png;
  spec   — SPEC teamart (SVG, рамка, цвета, кадры) → WORK/spec/<КЛУБ>.json;
  ui     — t, s, d, w, r — teamart.build (размеры и растушёвка по замерам EA, docs/logos-arenas.md §9); c — тот же
           рендер, что у teamart, но кадр — по EA клуба; баннер и прожектор — в контейнере EA того же номера;
  extra  — pb и значок ленты (рисунок — как tools/utah/ui_extra.py);
  verify — каждый файл против шаблона EA (всё, кроме пикселей; разбор → сборка байт в байт).
Выход — OUT (по умолчанию game/work/logos/out-nhl), рабочее — WORK (game/work/logos/work-nhl). Временные файлы
браузера — в game/work/logos/tmp (не в %TEMP%). Нужны venv game/work/logos/venv (numpy, scipy, Pillow) и Chrome/Edge.
Логотипы НХЛ — только для личного использования: SVG и выход в git не идут.
"""
import json
import math
import os
import shutil
import sys
import tempfile

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
ROOT = os.path.dirname(TOOLS)
sys.path.insert(0, TOOLS)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(TOOLS, 'utah'))
import teamart as ta        # noqa: E402
import playerhead as ph     # noqa: E402
import svgclean             # noqa: E402

LOGOS = os.environ.get('LOGOS_WORK', os.path.join(ROOT, 'game', 'work', 'logos'))
SRC = os.path.join(LOGOS, 'src', 'nhl-2026')
CLUBS = os.path.join(HERE, 'clubs.json')
CLUBS_AHL = os.path.join(HERE, 'clubs_ahl.json')          # настройки клубов АХЛ поверх slots.json legacy-data
SLOTS_AHL = os.path.join(ROOT, 'game', 'work', 'legacy-data', 'ahl-2026', 'slots.json')
ALL_SETS = ['t', 's', 'd', 'c', 'w', 'r', 'banner', 'spot', 'pb', 'tw']
# у клубов АХЛ в Legacy нет r и pb (только 0…29), прожектор и туннель общие (34)
LEAGUE_SETS = {'nhl': ALL_SETS, 'ahl': ['t', 's', 'd', 'c', 'w', 'banner', 'tw']}
REG_KINDS = {'nhl': ('s', 'c', 'w', 'tw', 'pb'), 'ahl': ('s', 'c', 'w', 'tw')}
# размеры t/d клубов АХЛ у EA в Legacy не уменьшались (в отличие от НХЛ, teamart.SIZE_TARGET_LEGACY): замер t/d 131…165
# (alpha > 128) — площадь t медиана 17 570 (у НХЛ 14 980), рамка до 209×185; d — 5 131 (у НХЛ 4 400), до 104×100
SIZE_TARGET_AHL = {'t': dict(area=17570, max_w=200, max_h=178), 'd': dict(area=5131, max_w=105, max_h=96)}
UI = {'t': 'teamlogos', 's': 'teamlogossmall', 'd': 'teamlogosdynasty', 'c': 'teamlogoscalendar',
      'w': 'teamlogoswide', 'r': 'teamlogosreflection'}
# кадр по умолчанию (клуб без EA-образца того же рисунка): медианы кадров EA 0…29 (eafocus, docs/logos-2026.md)
DEFAULT_FRAME = {'s': [0.5, 0.5, 2.1], 'w': [0.45, 0.46, 2.4], 'c': [0.49, 0.48, 1.3], 'tw': [0.39, 0.46, 1.29]}
PB_DEFAULT = [499, 252, 540, 450]               # медиана водяных знаков EA 0…29: центр и рамка логотипа, px
TW_BG = '#13212E'                               # фон окна значка (как у Юты); уточняется замером EA (reg)
PB_TINT, PB_ALPHA = '#A9D3F5', 0.30
REG_MIN_Q = {'s': 0.45, 'c': 0.45, 'w': 0.35, 'tw': 0.45, 'pb': 0.12}                                 # ниже — кадр EA не переносится (другой рисунок), берётся по умолчанию


def log(*a):
    print(*a, flush=True)


def load_clubs(league='nhl'):
    """НХЛ — tools/logos/clubs.json. АХЛ — слоты legacy-data (game/work/legacy-data/ahl-2026/slots.json: слот, artid,
    клуб 2026/27, логотип из кэша HockeyTech game/work/roster-cache/ahl/ht/logos/) + настройки tools/logos/clubs_ahl.json
    по коду клуба (pill, ea_sets, frame, keep…)."""
    if league == 'nhl':
        return [dict(c, league='nhl') for c in json.load(open(CLUBS, encoding='utf-8'))['nhl']]
    slots = json.load(open(SLOTS_AHL, encoding='utf-8'))['slots']
    opts = json.load(open(CLUBS_AHL, encoding='utf-8'))['ahl'] if os.path.exists(CLUBS_AHL) else {}
    out = []
    for sl in slots:
        c = dict(slot=sl['slot'], abbr=sl['code'], artid=sl['artid'], spotlight=None, name=sl['name'], league='ahl',
                 png=os.path.join(ROOT, *sl['logo_file'].split('/')), ht_team_id=sl['ht_team_id'],
                 old=(sl.get('old') or {}).get('fullname'))
        if 131 <= sl['artid'] <= 165:
            c['ea_art'] = sl['artid']
        if sl.get('renamed'):                          # в слоте другой клуб: у EA — чужой рисунок, кадр не переносится
            c['ea_frame'] = False
        c.update(opts.get(sl['code'], {}))
        out.append(c)
    return out


def club_svg_name(c):
    if c.get('png'):
        return c['abbr']
    return f"{c['nhle']}_{c.get('variant', 'light')}"


def png_svg(path, margin=2, blank=(), fill=()):
    """Растровый логотип (PNG с прозрачностью) → SVG-обёртка <image> по рамке непрозрачного (так его рисуют teamart и
    ui_extra в Chrome; как tools/utah/rasterlogo.py svg_wrap). Знаки ® / ™ (tools/logos/pngmarks.py): blank — рамки
    (x0, y0, x1, y1) или круги (cx, cy, r[, r2]) в пикселях PNG, которые делаются прозрачными (знак отдельно от рисунка); fill — рамки, которые
    заливаются самым частым цветом своей каймы в 1 пиксель (знак поверх ровной заливки рисунка)."""
    import base64
    import io
    from collections import Counter
    im = Image.open(path).convert('RGBA')
    for bx in blank:
        if len(bx) in (3, 4):                          # круг (cx, cy, r[, r2]): знак с белой каймой у обводки; в
            cx, cy, r = bx[:3]                         # кольце r…r2 — только полупрозрачное (край каймы)
            r2 = bx[3] if len(bx) == 4 else r
            a = np.asarray(im).copy()
            yy, xx = np.mgrid[0:a.shape[0], 0:a.shape[1]]
            d = np.sqrt((xx + 0.5 - cx) ** 2 + (yy + 0.5 - cy) ** 2)
            kill = (d <= r) | ((d <= r2) & (a[..., 3] < 128))
            a[kill] = 0
            im = Image.fromarray(a, 'RGBA')
        else:
            im.paste((0, 0, 0, 0), tuple(int(v) for v in bx))
    px = im.load()
    for bx in fill:
        x0, y0, x1, y1 = (int(v) for v in bx)
        ring = [px[x, y] for x in range(x0 - 1, x1 + 1) for y in (y0 - 1, y1)] +                [px[x, y] for y in range(y0, y1) for x in (x0 - 1, x1)]
        col = Counter(ring).most_common(1)[0][0]
        im.paste(col, (x0, y0, x1, y1))
    bb = im.getchannel('A').point(lambda a: 255 if a > 4 else 0).getbbox()
    x0, y0, x1, y1 = bb
    x0, y0 = max(0, x0 - margin), max(0, y0 - margin)
    x1, y1 = min(im.width, x1 + margin), min(im.height, y1 + margin)
    im = im.crop((x0, y0, x1, y1))
    buf = io.BytesIO()
    im.save(buf, 'PNG')
    data = base64.b64encode(buf.getvalue()).decode('ascii')
    w, h = im.size
    return (f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
            f'viewBox="0 0 {w} {h}" width="{w}" height="{h}">'
            f'<image width="{w}" height="{h}" href="data:image/png;base64,{data}"/></svg>')


def hexrgb(c):
    c = c.lstrip('#')
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def rgbhex(v):
    return '#' + ''.join(f'{int(max(0, min(255, round(x)))):02X}' for x in v)


# ---------------------------------------------------------------- svg

def stage_svg(c, work):
    name = club_svg_name(c)
    dst = os.path.join(work, 'svg', name + '.svg')
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if c.get('png'):
        open(dst, 'w', encoding='utf-8').write(png_svg(c['png'], blank=c.get('blank', ()), fill=c.get('fill', ())))
        log(f"{c['abbr']}: {os.path.basename(c['png'])} → SVG-обёртка")
        return dst
    src = os.path.join(SRC, name + '.svg')
    svg = open(src, encoding='utf-8').read()
    boxes = [tuple(b) for b in c.get('tm_boxes', [])]
    res, removed = svgclean.clean(svg, boxes)
    open(dst, 'w', encoding='utf-8').write(res)
    n = sum(len(g) for _, g in removed)
    log(f"{c['abbr']}: {name}.svg — убрано подпутей знаков ®/™: {n}")
    return dst


# ---------------------------------------------------------------- рамка и рендер

def base_spec(c, work):
    svg_path = os.path.join(work, 'svg', club_svg_name(c) + '.svg')
    svg = open(svg_path, encoding='utf-8').read()
    spec = {'team': c['name'], 'artid': c['artid'], 'svg': svg_path, 'league': c.get('league', 'nhl')}
    spec['viewbox'] = ta._svg_viewbox(svg)
    spec['_uri'] = ta.data_uri(svg)
    return spec


def measure(spec):
    tmp = tempfile.mkdtemp(prefix='logos_m_')
    try:
        return ta.measure_box(spec['_uri'], spec['viewbox'], tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def render_rgba(html, w, h):
    tmp = tempfile.mkdtemp(prefix='logos_r_')
    try:
        png = os.path.join(tmp, 'r.png')
        ta.render_html(html, png, w, h)
        _, _, px = ph.png_read(png)
        return np.frombuffer(bytes(px), np.uint8).reshape(h, w, 4).astype(np.float32)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def plain_t(spec):
    """Логотип целиком без блика и тени в кадре t (рамка вписана в 188×196 с центром 128, 128) и px на единицу."""
    bx, by, bw, bh = spec['box']
    kt = min(188 / bw, 196 / bh)
    l, t, w, h = ta._place(spec, 188, 196, 128, 128)
    img = render_rgba(ta.page(256, 256, ta.logo_layers(spec['_uri'], l, t, w, h)), 256, 256)
    return img, kt


# ---------------------------------------------------------------- reg: кадр EA и цвета «таблетки»

def pill_colors(ea_s, alpha_warp):
    """Цвета «таблетки» s EA (низ, верх) по пикселям фона (вне логотипа): обратный ход блика teamart (белый 0,30 →
    0,12 сверху, чёрный 0,10 → 0,28 снизу), линейный градиент по высоте. None — фона почти не видно."""
    from scipy import ndimage as ndi
    bg = ~ndi.binary_dilation(alpha_warp > 24, iterations=2)
    ys, xs = np.mgrid[0:64, 0:128]
    inner = (xs >= 15) & (xs <= 112) & (ys >= 16) & (ys <= 48)
    m = bg & inner & (ea_s[..., 3] > 250)
    if m.sum() < 40:
        return None
    py = (ys[m] - 9 + 0.5) / 46.0
    P = ea_s[..., :3][m]
    G = np.zeros_like(P)
    keep = np.ones(len(py), bool)
    for i, f in enumerate(py):
        if f < 0.49:
            a = 0.30 + (0.12 - 0.30) * f / 0.49
            G[i] = (P[i] - 255 * a) / (1 - a)
        elif f > 0.51:
            b = 0.10 + 0.18 * (f - 0.51) / 0.49
            G[i] = P[i] / (1 - b)
        else:
            keep[i] = False
    py, G = py[keep], G[keep]
    if len(py) < 30:
        return None
    if py.min() < 0.4 and py.max() > 0.6:
        A = np.stack([1 - py, py], 1)                      # G = top * (1 - f) + bottom * f
        sol, *_ = np.linalg.lstsq(A, G, rcond=None)
        top, bottom = sol[0], sol[1]
    else:
        top = bottom = np.median(G, 0)
    return rgbhex(np.clip(bottom, 0, 255)), rgbhex(np.clip(top, 0, 255)), int(m.sum())


def warp_alpha(t_img, r, shape):
    s = r['scale']
    size = int(round(t_img.shape[0] * s))
    a = Image.fromarray(np.clip(t_img[..., 3], 0, 255).astype(np.uint8)).resize((size, size), Image.BILINEAR)
    lay = Image.new('L', (shape[1], shape[0]))
    lay.paste(a, (int(round(r['tx'])), int(round(r['ty']))))
    return np.asarray(lay).astype(np.float32)


def stage_reg(c, work):
    import eafocus
    spec = base_spec(c, work)
    spec['box'] = measure(spec)
    out = dict(club=c['abbr'], artid=c['artid'], box=spec['box'], viewbox=list(spec['viewbox']))
    bx, by, bw, bh = spec['box']
    ea_art = c.get('ea_art', c['artid'] if c['artid'] < 30 else None)
    if ea_art is None or c.get('ea_frame') is False:
        out['reg'] = None
        log(f"{c['abbr']}: кадр EA не переносится ({'нет образца EA' if ea_art is None else 'другой рисунок'})")
    else:
        os.makedirs(os.path.join(work, 'reg'), exist_ok=True)
        t_img, kt = plain_t(spec)
        res = eafocus.register(t_img, ea_art, REG_KINDS[c.get('league', 'nhl')])
        P = eafocus.prep()
        win = P['tw_region']
        frames = {}
        for kind, r in res.items():
            s, (cx, cy) = r['scale'], r['center']
            u, v = (cx - r['tx']) / s, (cy - r['ty']) / s
            zx, zy = (u - 128) / (bw * kt) + 0.5, (v - 128) / (bh * kt) + 0.5
            kpx = s * kt
            if kind == 's':
                zk = kpx * bh / 46
            elif kind == 'w':
                zk = kpx * max(bw, bh) / 220
            elif kind == 'c':
                zk = kpx * bh / 86
            elif kind == 'tw':
                zk = kpx * max(bw, bh) / (win[2] - win[0])
            if kind == 'pb':
                frames[kind] = dict(q=round(r['q'], 3), box=[round(128 * s + r['tx'], 1), round(128 * s + r['ty'], 1),
                                                             round(bw * kpx, 1), round(bh * kpx, 1)])
            else:
                frames[kind] = dict(q=round(r['q'], 3), focus=[round(zx, 4), round(zy, 4), round(zk, 4)])
            img = eafocus.set_image(kind, ea_art)[0]
            eafocus.overlay(t_img, img, r, os.path.join(work, 'reg', f"{c['abbr']}_{kind}.png"))
            if kind == 's':
                pc = pill_colors(img, warp_alpha(t_img, r, img.shape))
                if pc:
                    frames['pill_ea'] = dict(bottom=pc[0], top=pc[1], pixels=pc[2])
            if kind == 'tw':
                aw = warp_alpha(t_img, r, img.shape)
                from scipy import ndimage as ndi
                m = P['tw_win'] & ~P['tw_same'] & ~ndi.binary_dilation(aw > 24, iterations=2) & (img[..., 3] > 250)
                if m.sum() > 30:
                    frames['tw_bg_ea'] = rgbhex(np.median(img[..., :3][m], 0))
        out['reg'] = frames
        log(f"{c['abbr']}: кадр EA (арт {ea_art}): " + ', '.join(f"{k} q={v['q']}" for k, v in frames.items()
                                                               if isinstance(v, dict) and 'q' in v))
    p = os.path.join(work, 'reg', f"{c['abbr']}.json")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    json.dump(out, open(p, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    return out


# ---------------------------------------------------------------- spec

def frame_for(c, reg, kind):
    """Кадр набора: вручную (clubs.json "frame") → EA (reg: наборы из "ea_sets" клуба, без него — с качеством не ниже
    REG_MIN_Q) → по умолчанию (медианы EA)."""
    man = c.get('frame', {}).get(kind)
    if man is not None:
        return man, 'вручную'
    r = (reg.get('reg') or {}).get(kind) if reg else None
    ok = r and (kind in c['ea_sets'] if 'ea_sets' in c else r['q'] >= REG_MIN_Q[kind])
    if ok:                                         # "ea_sets" — наборы, где кадр EA принят по листу проверки
        return (r['box'] if kind == 'pb' else r['focus']), f"EA q={r['q']}"
    return (PB_DEFAULT if kind == 'pb' else DEFAULT_FRAME[kind]), 'по умолчанию'


def stage_spec(c, work):
    rp = os.path.join(work, 'reg', f"{c['abbr']}.json")
    reg = json.load(open(rp, encoding='utf-8'))
    spec_dir = os.path.join(work, 'spec')
    os.makedirs(spec_dir, exist_ok=True)
    svg_rel = os.path.relpath(os.path.join(work, 'svg', club_svg_name(c) + '.svg'), spec_dir).replace('\\', '/')
    notes = {}
    pill = c.get('pill')
    if pill:
        notes['colors'] = 'вручную'
    else:
        pe = (reg.get('reg') or {}).get('pill_ea')
        if pe:
            pill = [pe['bottom'], pe['top']]
            notes['colors'] = f"EA ({pe['pixels']} пикс.)"
        else:
            raise SystemExit(f"{c['abbr']}: нет цветов «таблетки» — задать \"pill\" в clubs.json")
    fr = {k: frame_for(c, reg, k) for k in ('s', 'w', 'c', 'tw', 'pb')}
    if c.get('league') == 'ahl':
        fr.pop('pb')
    notes.update({k: v[1] for k, v in fr.items()})
    tw_bg = c.get('tw_bg', TW_BG)
    spec = {
        'team': c['name'] + ' (NHL Legacy, 2026/27)', 'artid': c['artid'],
        'svg': svg_rel, 'strip_paths': [], 'league': c.get('league', 'nhl'), 'box': reg['box'],
        'colors': pill, 'small_focus': fr['s'][0], 'wide_focus': fr['w'][0], 'calendar_focus': fr['c'][0],
        'ui_extra': {'tw_bg': tw_bg, 'tw_focus': fr['tw'][0]},
        '_notes': notes,
    }
    if c.get('spotlight') is not None:
        spec['spotlight'] = c['spotlight']
    if 'pb' in fr:
        spec['ui_extra'].update(pb_tint=PB_TINT, pb_alpha=PB_ALPHA, pb_box=fr['pb'][0])
    p = os.path.join(spec_dir, f"{c['abbr']}.json")
    json.dump(spec, open(p, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    log(f"{c['abbr']}: SPEC — " + ', '.join(f'{k}: {v}' for k, v in notes.items()))
    return p


def load_built_spec(c, work):
    p = os.path.join(work, 'spec', f"{c['abbr']}.json")
    spec = ta.load_spec(p)
    base = os.path.dirname(os.path.abspath(p))
    svg = ta.svg_text(os.path.join(base, spec['svg']), ())
    spec['viewbox'] = ta._svg_viewbox(svg)
    spec['_uri'] = ta.data_uri(svg)
    spec['_base'] = base
    return p, spec


# ---------------------------------------------------------------- ui

def write(out, rel, data):
    p = os.path.join(out, *rel.split('/'))
    os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, 'wb').write(data)
    log(f'   {rel}: {len(data)} байт')
    return p


def calendar_big(spec):
    """c: кадр 98×86 (как html_for_ea('c') у teamart: блик 0,18, без тени), точка рамки (zx, zy) — в центре кадра
    (49, 43), рамка высотой 86·zk px; растушёвка — маской EA (ea_mask), контейнер — c0."""
    zx, zy, zk = spec['calendar_focus']
    vx, vy, vw, vh = spec['viewbox']
    bx, by, bw, bh = spec['box']
    k = 86 * zk / bh
    w, h = vw * k, vh * k
    l = 49 - (bx - vx + bw * zx) * k
    t = 43 - (by - vy + bh * zy) * k
    body = ('<div class="a" style="left:0;top:0;width:98px;height:86px;overflow:hidden;">'
            + ta.logo_layers(spec['_uri'], l, t, w, h, gloss=0.18) + '</div>')
    rgba = render_rgba(ta.page(128, 128, body), 128, 128)
    tpl = ta.UiLogo.load(ta.ui_template('c'))
    raw = np.clip(rgba + 0.5, 0, 255).astype(np.uint8).tobytes()
    raw = ta.apply_mask(raw, 128, 128, ta.ea_mask('c'))
    return tpl.build(raw, 'md5')


def rx_template_own(kind, num):
    """Контейнер 3D-набора: файл EA того же номера (у клубов 0…29 он есть: имена растров уже свои), иначе — шаблон
    teamart с номером той же длины."""
    pattern = ta.RX_SETS[kind][0]
    rel = pattern.format(num)
    try:
        return ta.extracted(rel), num
    except SystemExit:
        tpl_rel, tpl_num = ta.rx_template(kind, num)
        return ta.extracted(tpl_rel), tpl_num


def rx_build(spec, kind, num):
    tpl_path, tpl_num = rx_template_own(kind, num)
    tpl = ta.Rw4.load(tpl_path)
    t = tpl.textures[0]
    W, H, html = ta.html_for_ea(kind, spec, spec['_uri'])
    rgba = np.clip(render_rgba(html, W, H) + 0.5, 0, 255).astype(np.uint8).tobytes()
    tpl.replace(t, ta.mip_chain(rgba, W, H, len(t.layout.levels)))
    if tpl_num != num:
        tpl.rename(tpl_num, num)
    return tpl.bytes()


def stage_ui(c, work, out, sets):
    p, spec = load_built_spec(c, work)
    art = c['artid']
    prev = os.path.join(work, 'preview', c['abbr'])
    os.makedirs(prev, exist_ok=True)
    tsets = [k for k in ('t', 's', 'd', 'w', 'r') if k in sets]
    if tsets:
        log(f"{c['abbr']}: teamart build {','.join(tsets)}")
        ta.build(p, out, only=tsets, preview=prev, ea_fit=True)
    if 'c' in sets:
        data = calendar_big(spec)
        fn = write(out, f'fe/ion/artassets/teamlogoscalendar/c{art}.big', data)
        lg = ta.UiLogo.load(fn)
        w, h, dec = lg.decode()
        sw, sh = lg.stage
        ph.png_write(os.path.join(prev, f'c{art}.png'), sw, sh, ph.crop(dec, w, h, sw, sh))
    if 'banner' in sets:
        write(out, f'rendering/banner/banner_{art}_cm.rx2', rx_build(spec, 'banner', art))
    if 'spot' in sets and c.get('spotlight') is not None:
        write(out, f"rendering/spotlight/texlib_{c['spotlight']}.rx2", rx_build(spec, 'spot', c['spotlight']))


_TW_SAME = {}


def tw_icon(spec, ex):
    """Значок ленты новостей — как tools/utah/ui_extra.make_tw (окно, крупный план, блик), но «общие» пиксели рамки и
    «облачка» — те, что совпадают у всех 30 значков клубов EA, а не у двух (t22 и t131): у двух совпадали и случайные
    пиксели внутри окна, и в новом значке оставались точки старого рисунка."""
    import ui_extra as ux
    from scipy import ndimage as ndi
    u = ux.ea_ui('fe/ion/artassets/twittericonsteam/t22.big')
    a = ux.decode(u)
    if 'same' not in _TW_SAME:
        stack = np.stack([ux.decode(ux.ea_ui(f'fe/ion/artassets/twittericonsteam/t{n}.big')) for n in range(30)])
        _TW_SAME['same'] = (stack.max(0) - stack.min(0)).sum(-1) < 12
    same_all = _TW_SAME['same']
    b = ux.decode(ux.ea_ui('fe/ion/artassets/twittericonsteam/t131.big'))
    same2 = (np.abs(a - b).sum(-1) < 6)                       # окно — как у ui_extra и eafocus (t22 и t131)
    H, W = a.shape[:2]
    diff = ndi.binary_closing(~same2 & (a[..., 3] > 200), iterations=2)
    win = ndi.binary_opening(ndi.binary_fill_holes(diff), iterations=1)
    bg = ux.hexf(ex.get('tw_bg', TW_BG))
    zx, zy, zk = ex.get('tw_focus', DEFAULT_FRAME['tw'])
    ys, xs = np.nonzero(win)
    x0, x1, y0, y1 = xs.min(), xs.max() + 1, ys.min(), ys.max() + 1
    bx, by, bw, bh = spec['box']
    k = (x1 - x0) * zk / max(bw, bh)
    cx = (x0 + x1) / 2 + (0.5 - zx) * bw * k
    cy = (y0 + y1) / 2 + (0.5 - zy) * bh * k
    logo = ux.render_logo_rgba(spec, W, H, cx, cy, bw * k, bh * k)
    inner = np.zeros_like(a)
    inner[..., :3] = bg
    inner[..., 3] = 255
    inner = ux.over(inner, logo)
    yy = (np.arange(H)[:, None] - y0) / max(1, (y1 - y0))
    inner[..., :3] = np.clip(inner[..., :3] * (1.0 + 0.10 * (0.5 - yy)), 0, 255)
    out = a.copy()
    m = win & ~same_all
    soft = ndi.gaussian_filter(m.astype(np.float32), 0.6)
    soft = np.where(same_all, 0, np.clip(soft * 1.4, 0, 1))
    out[..., :3] = out[..., :3] * (1 - soft[..., None]) + inner[..., :3] * soft[..., None]
    return u, out


def stage_extra(c, work, out, sets):
    import ui_extra as ux
    p, spec = load_built_spec(c, work)
    ex = spec.get('ui_extra', {})
    art = c['artid']
    prev = os.path.join(work, 'preview', c['abbr'])
    os.makedirs(prev, exist_ok=True)
    jobs = []
    if 'pb' in sets:
        jobs.append(('pb', f'fe/ion/artassets/playerbackgrounds/pb_{art}.big', ux.make_pb))
    if 'tw' in sets:
        jobs.append(('tw', f'fe/ion/artassets/twittericonsteam/t{art}.big', tw_icon))
    for kind, rel, fn in jobs:
        u, img = fn(spec, ex)
        data = u.build(np.clip(img + 0.5, 0, 255).astype(np.uint8).tobytes(), 'md5')
        write(out, rel, data)
        sw, sh = u.stage
        Image.fromarray(np.clip(img[:sh, :sw] + 0.5, 0, 255).astype(np.uint8)).save(os.path.join(prev, f'{kind}{art}.png'))


# ---------------------------------------------------------------- verify

def verify(out):
    """Каждый файл OUT против шаблона: .big — контейнер t0/s0/… (записи BIGF, Apt, заголовок XPR2, константа выборки,
    сцена), .rx2 — файл EA того же номера (или шаблон teamart): всё, кроме пикселей и имён растров; разбор → сборка
    байт в байт (у .rx2 — все уровни мипов)."""
    import re
    bad = n = 0
    for dp, _, fs in os.walk(out):
        for f in sorted(fs):
            path = os.path.join(dp, f)
            rel = os.path.relpath(path, out).replace('\\', '/')
            if not rel.endswith(('.big', '.rx2')):
                continue                               # manifest.json и прочее
            data = open(path, 'rb').read()
            n += 1
            try:
                if rel.endswith('.big'):
                    folder = rel.split('/')[-2]
                    if folder in UI.values():
                        kind = next(k for k, v in UI.items() if v == folder)
                        tpl = ta.UiLogo.load(ta.ui_template(kind))
                    else:
                        tdir = {'playerbackgrounds': 'playerbackgrounds/pb_22', 'twittericonsteam': 'twittericonsteam/t22'}[folder]
                        import kitpaint as kp
                        tpl = ta.UiLogo(kp._unchunk(open(ta.GAME.extracted(f'fe/ion/artassets/{tdir}.big'), 'rb').read()), tdir)
                    obj = ta.UiLogo(data, path)
                    same = [nm for (nm, b), (m, cc) in zip(obj.head.big.entries, tpl.head.big.entries)
                            if nm == m and nm != obj.head.tex_name and b == cc]
                    others = [nm for nm, _ in tpl.head.big.entries if nm != tpl.head.tex_name]
                    ok = (len(same) == len(others) and obj.head.tex.header == tpl.head.tex.header
                          and obj.head.big.tag == tpl.head.big.tag and obj.stage == tpl.stage
                          and obj.fetch.words == tpl.fetch.words)
                    _, rt = ta.roundtrip(path, deep=True)
                    ok = ok and all(v for k, v in rt.items() if not k.endswith(':mips_psnr'))
                    w, h, rgba = obj.decode()
                    cover = sum(1 for a in rgba[3::4] if a) / (w * h)
                    log(f"{'OK ' if ok else 'ОШИБКА'} {rel}: {len(data)} байт, сцена {obj.stage}, "
                        f"{obj.fetch.width}×{obj.fetch.height} {ta.FMT_NAMES.get(obj.fetch.fmt)}, непрозрачно {cover:.0%}")
                else:
                    key = next(k for k, v in ta.RX_SETS.items() if v[0].split('{}')[0] in rel)
                    num = int(re.search(r'_(\d+)(?:_cm)?\.rx2$', rel).group(1))
                    tpl_path, tpl_num = rx_template_own(key, num)
                    tpl = ta.Rw4.load(tpl_path)
                    obj = ta.Rw4(data, path)
                    t0 = tpl.textures[0]
                    a, b = bytearray(tpl.raw), bytearray(obj.raw)
                    for x in (a, b):
                        x[t0.data_off:t0.data_off + t0.size] = bytes(t0.size)
                    for (sp, ln) in tpl.name_slots:
                        a[sp:sp + ln] = bytes(ln)
                        b[sp:sp + ln] = bytes(ln)
                    names_ok = all(re.search(r'(?<!\d)' + str(num) + r'(?!\d)', t.name) for t in obj.textures)
                    _, rt = ta.roundtrip(path, deep=True)
                    lay = all(v for k, v in rt.items() if not k.endswith(':mips_psnr'))
                    psnr = [v for k, v in rt.items() if k.endswith(':mips_psnr')]
                    ok = a == b and len(data) == len(tpl.raw) and names_ok and lay
                    p0 = psnr[0] if psnr and psnr[0] else []
                    log(f"{'OK ' if ok else 'ОШИБКА'} {rel}: {len(data)} байт, шаблон {os.path.basename(tpl_path)}, "
                        f"{obj.textures[0].fetch.describe()}, мипы {min(p0) if p0 else '—'}…{max(p0) if p0 else '—'} дБ")
                bad += not ok
            except Exception as e:
                bad += 1
                log(f'ОШИБКА {rel}: {e}')
    log(f'файлов {n}, ошибок {bad}')
    return bad


# ---------------------------------------------------------------- main

def main():
    sys.stdout.reconfigure(encoding='utf-8')
    args = sys.argv[1:]

    def opt(name, default):
        if name in args:
            i = args.index(name)
            v = args[i + 1]
            del args[i:i + 2]
            return v
        return default
    league = opt('--league', 'nhl')
    stages = opt('--stages', 'svg,reg,spec,ui,extra,verify').split(',')
    out = opt('--out', os.path.join(LOGOS, f'out-{league}'))
    work = opt('--work', os.path.join(LOGOS, f'work-{league}'))
    sets = opt('--sets', ','.join(LEAGUE_SETS[league])).split(',')
    tmp = os.path.join(LOGOS, 'tmp')
    os.makedirs(tmp, exist_ok=True)
    tempfile.tempdir = tmp                         # рендеры Chrome — в папке проекта, не в %TEMP%
    ta.set_game('legacy')
    if league == 'ahl':                            # только в этом процессе: цели размеров t/d — по логотипам АХЛ EA
        ta.SIZE_TARGET_LEGACY = SIZE_TARGET_AHL
    clubs = load_clubs(league)
    if args:
        want = set(args)
        clubs = [c for c in clubs if c['abbr'] in want or c.get('nhle') in want]
    else:
        clubs = [c for c in clubs if not c.get('keep')]
    for c in clubs:
        csets = sets
        if c.get('keep'):                          # логотипы уже нынешние — только то, чего у клуба нет
            csets = [s for s in sets if s in c.get('extra', [])]
        if 'svg' in stages:
            stage_svg(c, work)
        if 'reg' in stages:
            stage_reg(c, work)
        if 'spec' in stages:
            stage_spec(c, work)
        if 'ui' in stages:
            stage_ui(c, work, out, csets)
        if 'extra' in stages:
            stage_extra(c, work, out, csets)
    if 'verify' in stages:
        bad = verify(out)
        sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
