"""Стандартная раскладка атласа шрифта EA (Legacy, стиль 1): медианы рамок глифов по всем шрифтам клубов НХЛ 0…29
(118 атласов со стандартной раскладкой: J у x 288…300, M у 398…408).
→ JSON {символ: [x0, y0, x1, y1]} (буквы A–Z, big0–9, sm0–9 и sm2_0–9 — две строки малых цифр, CA_C/CA_A — буквы
капитана). Нужен numpy (venv game/work/utah/venv).

    python tools/utah/font_layout.py tools/utah/src/font_layout_ea.json
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding='utf-8')
import numpy as np
import teamart as ta, kitpaint as kp, czkit
ta.set_game('legacy')
out = sys.argv[1]
boxes = {}
n = 0
for a in range(30):
    for v in range(0, 8):
        rel = f'rendering/jersey/texlib_1_{a}_{v}.rx2'
        p = ta.GAME.extracted(rel)
        if not p:
            continue
        rw = ta.Rw4(kp._unchunk(open(p, 'rb').read()), rel)
        t = next(x for x in rw.textures if kp.layer_name(x.name) == 'font_cm')
        f = kp.Img(*kp.tex_decode(rw, t, 0))
        c = czkit.font_cells(f)
        # стандартная раскладка: J около 292…298, M — 400…406
        if not (c.get('J') and 288 <= c['J'][0] <= 300 and c.get('M') and 398 <= c['M'][0] <= 408):
            continue
        ca = czkit.font_cells_ca(f)
        # вторая строка малых цифр
        w, h, A = f.w, f.h, f.px[3::4]
        rows = []
        s = None
        for y in range(368, 512):
            fl = any(A[y * w + x] >= 96 for x in range(w))
            if fl and s is None: s = y
            if not fl and s is not None: rows.append((s, y)); s = None
        if s is not None: rows.append((s, 512))
        if len(rows) >= 2:
            y0, y1 = rows[1]
            cols = []
            s = None
            for x in range(w + 1):
                fl = x < w and any(A[y * w + x] >= 96 for y in range(y0, y1))
                if fl and s is None: s = x
                if not fl and s is not None:
                    if x - s > 2: cols.append((s, x))
                    s = None
            if len(cols) == 10:
                for d, (x0, x1) in zip('0123456789', cols):
                    c['sm2_' + d] = (x0, y0, x1, y1)
        for k, b in list(c.items()) + [('CA_C', ca.get('C')), ('CA_A', ca.get('A'))]:
            if b:
                boxes.setdefault(k, []).append(b)
        n += 1
med = {k: [int(round(x)) for x in np.median(np.array(v), 0)] for k, v in boxes.items() if len(v) >= n // 2}
json.dump({'fonts': n, 'boxes': med}, open(out, 'w'), indent=1)
print('шрифтов', n, 'символов', len(med))
for k in ['A', 'C', 'I', 'M', 'W', 'big0', 'big1', 'big5', 'sm0', 'sm2_0', 'CA_C', 'CA_A']:
    print(k, med.get(k))
