"""Размер фамилии и номера на спине и промежутки между буквами у форм слота — в см на свитере, против эталона.

    python -m kitport lettering [--clubs CHI,UTA] [--ref MIN,NJD,TBL,BOS,DET,LAK,SEA,VGK]

Как игра рисует (docs/kitport.md §2.5, §12.1): знак берётся из клетки атласа шрифта фиксированного размера и
вписывается в зону карты номеров по высоте. Значит, на свитере:
- высота буквы фамилии = высота зоны 0 (см) × высота буквы в клетке / высота строки атласа (47 px);
- промежуток между буквами = высота зоны × (шаг клеток 32 px − ширина буквы) / 47 — у плотной фамилии он мал;
- высота номера = высота зоны 1 × высота цифры / высота строки цифр (123 px);
- номер (проверено в игре 24.10): клетка цифры (80 px) — шириной в половину зоны 1, двузначный номер — во всю зону.
  Ширина цифры = ширина зоны × ширина знака / 160; промежуток цифр (видимый край, альфа ≥ 128, без «1») к высоте
  цифры — столбец «пром. №», цель — профиль digit_gap (edge_kit.DIGIT_GAP), замечание — дальше ±0,01.
Зона — по среднему столбцу (у дуги DET — по середине), см — по наклону развёртки спины (edge_kit.back_m_per_v),
ширина зоны номера — хордой через середину (edge_kit.zone_size_cm).
Флаги — против медианы эталона (одобренные клубы): высота фамилии и номера ±10 %, промежуток — до
edge_kit.NAME_FIT_GAP высоты буквы (правило пользователя 22.10: «фамилии не крупнее и не мельче, плотно»).
"""
DIGIT_GAP_TOL = 0.01                      # промежуток цифр — от цели профиля не дальше (доля высоты цифры)
import os
import sys

import numpy as np

from . import core

REF = "MIN,NJD,TBL,BOS,DET,LAK,SEA,VGK"
NAME_ROWS = ((1, 48), (49, 98))           # строки букв фамилии в атласе 512²
NAME_ROW_H, NAME_PITCH = 47, 32
DIGIT_ROWS = ((115, 238), (242, 367))     # крупные цифры номера на спине: 0–4 и 5–9, по 5 в строке до x 420
DIGIT_ROW_H, DIGIT_PITCH = 123, 84
TOL = 0.10                                # ±10 % от медианы эталона


def _boxes(alpha, y0, y1, x1, min_w=3):
    """Знаки в строке атласа: [(ширина, высота)] по разрывам столбцов."""
    sub = alpha[y0:y1, :x1]
    cols = sub.any(0)
    out, x = [], 0
    while x < len(cols):
        if cols[x]:
            s = x
            while x < len(cols) and cols[x]:
                x += 1
            if x - s >= min_w:
                rows = np.nonzero(sub[:, s:x].any(1))[0]
                out.append((x - s, rows[-1] - rows[0] + 1))
        else:
            x += 1
    return out


def _zone_rows(a, zone):
    m = (a[..., 0] > 128) & (a[..., 1] > 128) & (a[..., 2] == zone)
    xs = np.nonzero(m.any(0))[0]
    return int(m[:, xs[len(xs) // 2]].sum()) if len(xs) else 0


def measure(kit_dir, m_per_row):
    """-> dict: зоны (см), буквы (px и см), промежуток, номер."""
    from PIL import Image
    from fb import jersey_mesh as J
    from fb.fonts import CAPTAIN_BOX
    name = np.asarray(Image.open(os.path.join(kit_dir, "name_cm.png")).convert("RGBA"))
    font = np.asarray(Image.open(os.path.join(kit_dir, "font_cm.png")).convert("RGBA"))[..., 3] > 40
    z0, z1 = _zone_rows(name, 0) * m_per_row * 100, _zone_rows(name, 1) * m_per_row * 100
    ws, hs = [], []
    for row, (y0, y1) in enumerate(NAME_ROWS):     # буквы — по клеткам FONT_SLOTS (между ними бывают ' . -)
        cx = J.FONT_SLOTS[row]
        b = [0] + [(cx[i] + cx[i + 1]) // 2 for i in range(len(cx) - 1)] + [CAPTAIN_BOX[0]]
        for i in range(len(cx)):
            sub = font[y0:y1, b[i]:b[i + 1]]
            cols, rows_ = np.nonzero(sub.any(0))[0], np.nonzero(sub.any(1))[0]
            if len(cols):
                ws.append(cols[-1] - cols[0] + 1)
                hs.append(rows_[-1] - rows_[0] + 1)
    lw, lh = float(np.median(ws)), float(np.median(hs))
    dg = [bx for y0, y1 in DIGIT_ROWS for bx in _boxes(font, y0, y1, 420)]
    dw, dh = (float(np.median([w for w, _ in dg])), float(np.median([h for _, h in dg]))) if dg else (0.0, 0.0)
    letter_h = z0 * lh / NAME_ROW_H
    gap = z0 * (NAME_PITCH - lw) / NAME_ROW_H
    # цифры: клетка (80 px) — шириной в половину зоны номера, во всю её высоту (проверено в игре 24.10, §2.5)
    from fb import edge_kit as E, fonts as Fo
    zs = E.zone_size_cm(os.path.join(kit_dir, "name_cm.png"), 1)
    dm = Fo.digit_metrics(os.path.join(kit_dir, "font_cm.png"))
    num_w = d_gap = None
    if zs and dm:
        per_px = zs[0] * 100 / (2 * Fo.DIGIT_CELL)                   # см свитера на px атласа по ширине
        num_w = dm["w"] * per_px
        h_chord = zs[1] * 100 * dm["h"] / DIGIT_ROW_H                 # высота цифры — той же хордой, что ширина
        d_gap = (Fo.DIGIT_CELL - dm["w_edge"]) * per_px / max(h_chord, 1e-6)
    return {"name_zone": z0, "num_zone": z1, "letter_px": (lw, lh), "letter_h": letter_h,
            "letter_w": z0 * lw / NAME_ROW_H, "gap": gap, "gap_ratio": gap / max(letter_h, 1e-6),
            "digit_px": (dw, dh), "num_h": z1 * dh / DIGIT_ROW_H, "num_w": num_w if num_w is not None else 0.0,
            "digit_gap": d_gap}


def cmd_lettering(a):
    sys.path.insert(0, core.TOOLS)
    from fb import edge_kit as E
    k, _ = E.back_m_per_v()
    m_per_row = k / 256.0                          # карта номеров — 256²
    src = core.slot_kits_dir()
    kits = sorted(d for d in os.listdir(src) if os.path.isdir(os.path.join(src, d)))
    want = set(a.clubs.split(",")) if a.clubs else None
    ref = set(a.ref.split(","))
    res = {}
    for kit in kits:
        club = kit.split("_")[0]
        if (want is None or club in want or club in ref) and os.path.exists(os.path.join(src, kit, "font_cm.png")):
            res[kit] = measure(os.path.join(src, kit), m_per_row)
    rk = [r for kk, r in res.items() if kk.split("_")[0] in ref]
    if not rk:
        sys.exit("нет эталонных форм в слоте")
    med = {f: float(np.median([r[f] for r in rk])) for f in ("letter_h", "num_h", "gap_ratio")}
    print(f"эталон ({a.ref}): буква {med['letter_h']:.2f} см, номер {med['num_h']:.1f} см, промежуток "
          f"{med['gap_ratio']:.2f} высоты буквы; допуск ±{TOL:.0%}, промежуток ≤ {E.NAME_FIT_GAP}")
    print(f"{'форма':10s} {'зона ф.':>7s} {'буква в×ш':>11s} {'пром.':>11s} {'зона №':>7s} {'номер в×ш':>11s} "
          f"{'пром. №':>13s}  замечания")
    bad = 0
    for kit, r in res.items():
        flags = []
        club, kname = kit.split("_")[0], kit.split("_", 1)[1]
        E.use_club(club)                           # цель промежутка цифр — профиль клуба (digit_gap)
        want_gap = float(E.DIGIT_GAPS.get(kname, E.DIGIT_GAPS.get("*", E.DIGIT_GAP)))
        if r["digit_gap"] is not None and abs(r["digit_gap"] - want_gap) > DIGIT_GAP_TOL:
            flags.append(f"промежуток цифр {r['digit_gap']:.3f} высоты при цели {want_gap:g}")
        if abs(r["letter_h"] / med["letter_h"] - 1) > TOL:
            flags.append(f"фамилия {'крупнее' if r['letter_h'] > med['letter_h'] else 'мельче'} эталона "
                         f"{r['letter_h'] / med['letter_h'] - 1:+.0%}")
        if r["gap_ratio"] > E.NAME_FIT_GAP + 0.02:
            flags.append(f"буквы разрежены ({r['gap_ratio']:.2f} высоты)")
        if abs(r["num_h"] / med["num_h"] - 1) > TOL:
            flags.append(f"номер {'крупнее' if r['num_h'] > med['num_h'] else 'мельче'} эталона "
                         f"{r['num_h'] / med['num_h'] - 1:+.0%}")
        mark = "" if kit.split("_")[0] in ref else "*"
        bad += bool(flags) and not mark == ""
        dg_ = f"{r['digit_gap']:.3f} ({want_gap:g})" if r["digit_gap"] is not None else "—"
        print(f"{kit + mark:10s} {r['name_zone']:6.1f}см {r['letter_h']:5.2f}×{r['letter_w']:4.2f}  "
              f"{r['gap']:4.2f} ({r['gap_ratio']:.2f}) {r['num_zone']:6.1f}см {r['num_h']:5.1f}×{r['num_w']:4.1f} "
              f"{dg_:>13s}  {'; '.join(flags)}")
    print("* — проверяемые формы (не эталон)")
    return 1 if bad else 0
