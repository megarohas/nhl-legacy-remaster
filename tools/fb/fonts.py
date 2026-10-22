"""Шрифты номеров NHL 24 → NHL Legacy (font_cm/nm/sm 512²) для 32 клубов. Только офлайн.

Атлас NHL 24 (font_adidas_<клуб>_<форма>_color, 1024²) — та же раскладка, что у EA в Legacy (512²): ячейки букв,
больших и малых цифр, C/A — на тех же местах (проверено czkit.font_cells: M/N/O и цифры совпадают; лишние «´» и «.»
у NHL 24 стоят в пустых промежутках раскладки EA). Поэтому перенос — уменьшение 1024 → 512:
  font_cm — цвет с альфой (уменьшение с премультипликацией альфы);
  font_nm — из font_*_normal NHL 24 (BC5: X, Y; Z = √(1 − X² − Y²)), R = X, G = Y, как ждёт kitpaint pack;
  font_sm — как у EA: серый 21 с альфой 0/255 по глифам.
Сравнение с нынешним шрифтом Legacy этой формы (kitpaint unpack 1_<art>_<вариант> --game legacy): IoU масок глифов
цифр и разница цвета заливки; «отличается» — IoU < 0,85 или цвет дальше 30.

  python -m fb.fonts build      -> game/work/nhl24/out/kits/<КОД>_<форма>/font_{cm,nm,sm}.png, out/fonts.json
  python -m fb.fonts sheet      -> game/work/nhl24/compare/fonts_32.png
"""
import argparse
import json
import os
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .cas import REPO
from .kit_batch import CLUBS, KITS, legacy_target

NHL24 = os.path.join(REPO, "game", "work", "nhl24")
SRC = os.path.join(NHL24, "extract", "fonts24", "character", "skater", "league", "nhl")
OUT = os.path.join(NHL24, "out", "kits")
LEG = os.path.join(NHL24, "out", "_legacy_kits")
DIGITS = (0, 98, 405, 368)        # большие цифры (x0, y0, x1, y1) на 512²


def resize_premult(rgba, size):
    a = rgba[..., 3:4] / 255.0
    pre = np.concatenate([rgba[..., :3] * a, rgba[..., 3:4]], -1).astype(np.float32)
    ch = [np.asarray(Image.fromarray(pre[..., k]).resize((size, size), Image.LANCZOS)) for k in range(4)]
    out = np.stack(ch, -1)
    al = np.clip(out[..., 3:4], 0, 255)
    rgb = np.where(al > 0.5, out[..., :3] / np.maximum(al / 255.0, 1e-3), 0)
    return np.clip(np.concatenate([rgb, al], -1), 0, 255).astype(np.uint8)


# Области атласа 512² (docs/kitport.md §2.5): строки букв фамилии (y0, y1) с шагом клеток 32 px и буквы капитана
NAME_ROWS = ((1, 48), (49, 98))
NAME_CELL = 32
CAPTAIN_BOX = (410, 512)          # x: столбец C и A
CAPTAIN_ROWS = ((83, 190), (195, 302))


def _glyph_boxes(alpha, x0, x1, y0, y1, min_h=4):
    """Связные знаки в области атласа (alpha > 40): [(x0, y0, x1, y1)] в координатах атласа."""
    from scipy import ndimage as ndi
    lab, _ = ndi.label(alpha[y0:y1, x0:x1] > 40)
    out = []
    for sl in ndi.find_objects(lab):
        if sl is not None and sl[0].stop - sl[0].start >= min_h:
            out.append((sl[1].start + x0, sl[0].start + y0, sl[1].stop + x0, sl[0].stop + y0))
    return out


def _scale_box(layers, box, sx, sy, bounds, fills, anchor="center"):
    """Знак в рамке box — в sx × sy вокруг его середины, в пределах bounds (x0, y0, x1, y1); layers — массивы одного
    размера (font_cm RGBA — с премультипликацией, font_nm), fills — фон каждого вне знака."""
    bx0, by0, bx1, by1 = box
    w, h = bx1 - bx0, by1 - by0
    cx, cy = (bx0 + bx1) / 2, (by0 + by1) / 2
    nw, nh = max(1, round(w * sx)), max(1, round(h * sy))
    nx0 = int(round(min(max(cx - nw / 2, bounds[0]), bounds[2] - nw)))
    ny0 = int(round(min(max(cy - nh / 2 if anchor == "center" else by0, bounds[1]), bounds[3] - nh)))
    cm = layers[0]
    a = cm[by0:by1, bx0:bx1, 3:4].astype(np.float32) / 255.0
    crops = [np.concatenate([cm[by0:by1, bx0:bx1, :3] * a, cm[by0:by1, bx0:bx1, 3:4]], -1).astype(np.float32)]
    crops += [L[by0:by1, bx0:bx1].astype(np.float32) for L in layers[1:]]
    res = [np.stack([np.asarray(Image.fromarray(c[..., k]).resize((nw, nh), Image.LANCZOS)) for k in range(c.shape[2])],
                    -1) for c in crops]
    for L, fill in zip(layers, fills):                   # прежний знак — фоном
        L[by0:by1, bx0:bx1] = fill
    al = np.clip(res[0][..., 3:4], 0, 255)
    rgb = np.where(al > 0.5, res[0][..., :3] / np.maximum(al / 255.0, 1e-3), 0)
    cm[ny0:ny0 + nh, nx0:nx0 + nw] = np.clip(np.concatenate([rgb, al], -1), 0, 255).astype(np.uint8)
    for L, r, fill in zip(layers[1:], res[1:], fills[1:]):   # рельеф: знак — по альфе нового, вне — фон
        m = (al / 255.0)
        L[ny0:ny0 + nh, nx0:nx0 + nw] = np.clip(r * m + np.array(fill, np.float32) * (1 - m), 0, 255).astype(np.uint8)


def scale_glyphs(slot_dir, name=1.0, captain_x=1.0, log=None, name_anchor="center"):
    """Знаки атласа шрифта слота (font_cm / font_nm / font_sm) крупнее в своих клетках: буквы фамилии — в name раз (в
    пределах клетки: игра берёт знак из клетки атласа — крупнее знак, крупнее и плотнее фамилия), буквы капитана C и
    A — шире в captain_x раз (высота у них и так во всю клетку). Пользователь, 22.10, BOS: у атласа NHL 27 буквы
    фамилии — 32 px высоты из 47 (у EA — 46), промежутки 17 px (у EA — 9), C и A узкие (46–56 px против 67–71).
    font_sm — заново по альфе (как fb.pilot.build_font). -> [описание]."""
    p = lambda f: os.path.join(slot_dir, f + ".png")
    cm = np.asarray(Image.open(p("font_cm")).convert("RGBA")).copy()
    nm = np.asarray(Image.open(p("font_nm")).convert("RGBA")).copy()
    if cm.shape[:2] != (512, 512):
        raise SystemExit(f"{slot_dir}: атлас {cm.shape[1]}×{cm.shape[0]}, ждал 512²")
    fills = ((0, 0, 0, 0), (128, 128, 255, 255))
    rep = []
    nx, ny = (name, name) if np.isscalar(name) else (float(name[0]), float(name[1]))   # [ширина, высота] — раздельно
    if (nx, ny) != (1.0, 1.0):
        n = 0
        from .jersey_mesh import FONT_SLOTS             # центры клеток букв EA (шаг не везде 32 px: L 368, M 416)
        for row, (y0, y1) in enumerate(NAME_ROWS):
            sc = np.array(FONT_SLOTS[row], float)
            mids = np.concatenate([[max(sc[0] - 16, 0)], (sc[1:] + sc[:-1]) / 2, [min(sc[-1] + 16, 512)]])
            # столбец C и A (x ≥ CAPTAIN_BOX[0]) — не буквы фамилии: верх C (y 83) заходит в строку P–Z
            for box in _glyph_boxes(cm[..., 3], 0, CAPTAIN_BOX[0] - 2 if row else 512, y0, y1):
                cx = (box[0] + box[2]) / 2
                i = int(np.argmin(np.abs(sc - cx)))
                if abs(sc[i] - cx) < 8:                  # буква — в своей клетке (до середин к соседям)
                    bx = (mids[i], mids[i + 1])
                else:                                    # ' . - между клетками — в пределах своего места
                    bx = (cx - 8, cx + 8)
                w, h = box[2] - box[0], box[3] - box[1]
                sx_ = min(nx, (bx[1] - bx[0] - 2) / max(w, 1))
                sy_ = min(ny, (y1 - y0 - 1) / max(h, 1))
                if nx == ny:                             # одинаково — как раньше (масштаб — меньший из пределов)
                    sx_ = sy_ = min(sx_, sy_)
                _scale_box([cm, nm], box, sx_, sy_, (bx[0], y0, bx[1], y1), fills, name_anchor)
                n += 1
        rep.append(f"буквы фамилии ×{nx}×{ny} (ширина×высота, в пределах клетки, привязка — {name_anchor}): {n} знаков")
    if captain_x != 1.0:
        for y0, y1 in CAPTAIN_ROWS:
            for box in _glyph_boxes(cm[..., 3], *CAPTAIN_BOX, y0, y1, min_h=40):
                w = box[2] - box[0]
                s = min(captain_x, (CAPTAIN_BOX[1] - CAPTAIN_BOX[0] - 2) / max(w, 1))
                _scale_box([cm, nm], box, s, 1.0, (CAPTAIN_BOX[0], y0, CAPTAIN_BOX[1], y1), fills)
        rep.append(f"буквы капитана шире ×{captain_x}")
    sm = np.zeros((512, 512, 4), np.uint8)
    sm[..., :3] = 21
    sm[..., 3] = np.where(cm[..., 3] > 128, 255, 0)
    Image.fromarray(cm).save(p("font_cm"))
    Image.fromarray(nm).save(p("font_nm"))
    Image.fromarray(sm).save(p("font_sm"))
    if log is not None:
        log.extend(rep)
    return rep


DIGIT_ROWS = ((115, 238), (242, 367))   # крупные цифры номера на спине: 0–4 и 5–9
DIGIT_CELL = 80                    # шаг клеток цифр (центры 40, 120, 200, 280, 360 — замер атласов EA и NHL 27)


def fit_digits(slot_dir, gap=0.08, log=None):
    """Цифры номера ближе друг к другу (пользователь, 22.10: «цифры в номере далеко, особенно на светлых формах со
    светлой обводкой»): игра берёт цифру клеткой атласа (DIGIT_CELL) — промежуток между цифрами = поля клетки. Цифры
    шире в своих клетках (высота та же), пока поле не станет ≤ gap высоты цифры (MIN: 64 из 80 px — промежуток 16 px,
    4 см при номере 30 см). -> [описание]."""
    p = lambda f: os.path.join(slot_dir, f + ".png")
    cm = np.asarray(Image.open(p("font_cm")).convert("RGBA")).copy()
    nm = np.asarray(Image.open(p("font_nm")).convert("RGBA")).copy()
    al = cm[..., 3] > 40
    boxes = []
    for y0, y1 in DIGIT_ROWS:
        for i in range(5):
            x0 = i * DIGIT_CELL
            sub = al[y0:y1, x0:x0 + DIGIT_CELL]
            cols, rows = np.nonzero(sub.any(0))[0], np.nonzero(sub.any(1))[0]
            if len(cols):
                boxes.append(((x0 + cols[0], y0 + rows[0], x0 + cols[-1] + 1, y0 + rows[-1] + 1), (x0, y0, x0 + DIGIT_CELL, y1)))
    if not boxes:
        return []
    ws = sorted(b[2] - b[0] for b, _ in boxes)
    w = float(np.median(ws[len(ws) // 5:]))            # без узкой «1»
    h = float(np.median([b[3] - b[1] for b, _ in boxes]))
    sx = min(max(1.0, (DIGIT_CELL - gap * h) / w), (DIGIT_CELL - 2) / w)
    if sx <= 1.0:
        return [f"цифры номера: {w:.0f}×{h:.0f} px, промежуток {DIGIT_CELL - w:.0f} px — уже плотно"]
    fills = ((0, 0, 0, 0), (128, 128, 255, 255))
    for box, cell in boxes:
        _scale_box([cm, nm], box, sx, 1.0, (cell[0] + 1, cell[1], cell[2] - 1, cell[3]), fills)
    sm = np.zeros((512, 512, 4), np.uint8)
    sm[..., :3] = 21
    sm[..., 3] = np.where(cm[..., 3] > 128, 255, 0)
    Image.fromarray(cm).save(p("font_cm"))
    Image.fromarray(nm).save(p("font_nm"))
    Image.fromarray(sm).save(p("font_sm"))
    rep = [f"цифры номера: {w:.0f}×{h:.0f} px, промежуток {DIGIT_CELL - w:.0f} → {DIGIT_CELL - w * sx:.0f} px (шире ×{sx:.2f})"]
    if log is not None:
        log.extend(rep)
    return rep


def normal_map(path, size):
    n = np.asarray(Image.open(path).convert("RGB")).astype(np.float32) / 255.0 * 2 - 1
    x, y = n[..., 0], n[..., 1]
    z = np.sqrt(np.clip(1 - x * x - y * y, 0, 1))
    rgb = (np.stack([x, y, z], -1) + 1) * 127.5
    im = Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8)).resize((size, size), Image.LANCZOS)
    return np.dstack([np.asarray(im), np.full((size, size), 255, np.uint8)])


def legacy_font(art, variant):
    kit = f"1_{art}_{variant}"
    d = os.path.join(LEG, kit)
    p = os.path.join(d, "font_cm.png")
    if not os.path.exists(p):
        subprocess.run([sys.executable, os.path.join(REPO, "tools", "kitpaint.py"), "unpack", kit, d, "--game", "legacy"],
                       check=False, capture_output=True, cwd=os.path.join(REPO, "tools"))
    return np.asarray(Image.open(p).convert("RGBA")) if os.path.exists(p) else None


def compare(new, cur):
    x0, y0, x1, y1 = DIGITS
    a = new[y0:y1, x0:x1, 3] > 128
    b = cur[y0:y1, x0:x1, 3] > 128
    iou = (a & b).sum() / max((a | b).sum(), 1)
    fa = new[y0:y1, x0:x1][new[y0:y1, x0:x1, 3] > 230][:, :3]
    fb = cur[y0:y1, x0:x1][cur[y0:y1, x0:x1, 3] > 230][:, :3]
    dc = float(np.linalg.norm(np.median(fa, 0) - np.median(fb, 0))) if len(fa) and len(fb) else 999.0
    return round(float(iou), 3), round(dc, 1)


def cmd_build(a):
    from .kit_batch import ok_names
    ok = ok_names(os.path.join(NHL24, "extract", "fonts24"))
    res = []
    for club, art, code in CLUBS:
        for kit, loc in KITS.items():
            rec = {"code": code, "kit": kit}
            cp = os.path.join(SRC, club, "adidas", kit, f"font_adidas_{club}_{kit}_color.png")
            npth = os.path.join(SRC, club, "adidas", kit, f"font_adidas_{club}_{kit}_normal.png")
            tgt = legacy_target(art, loc)
            if not os.path.exists(os.path.dirname(cp)):
                rec["status"] = "нет комплекта в NHL 24"
                res.append(rec)
                continue
            base_name = f"content/character/skater/league/nhl/{club}/adidas/{kit}/font_adidas_{club}_{kit}_"
            if base_name + "color" not in ok:
                rec["status"] = "нет чанка" if not os.path.exists(cp) else "нет чанка (на месте чужой, sha1)"
                res.append(rec)
                continue
            if base_name + "normal" not in ok:
                npth = None
            cm = resize_premult(np.asarray(Image.open(cp).convert("RGBA")), 512)
            nm = normal_map(npth, 512) if npth and os.path.exists(npth) else None
            if nm is None:  # нормали NHL 24 нет — плоская (как у шрифтов EA: почти плоская)
                nm = np.zeros((512, 512, 4), np.uint8)
                nm[...] = (128, 128, 255, 255)
                rec["nm"] = "плоская (нормаль NHL 24 не найдена)"
            sm = np.zeros((512, 512, 4), np.uint8)
            sm[..., :3] = 21
            sm[..., 3] = np.where(cm[..., 3] > 128, 255, 0)
            od = os.path.join(OUT, f"{code}_{kit}")
            os.makedirs(od, exist_ok=True)
            Image.fromarray(cm).save(os.path.join(od, "font_cm.png"))
            Image.fromarray(sm).save(os.path.join(od, "font_sm.png"))
            if nm is not None:
                Image.fromarray(nm).save(os.path.join(od, "font_nm.png"))
            rec["status"] = "ok"
            if tgt:
                rec["legacy"] = f"texlib_1_{art}_{tgt['variant']}: font_1_{art}_{tgt['variant']}_cm/nm/sm"
                cur = legacy_font(art, tgt["variant"])
                if cur is not None:
                    iou, dc = compare(cm, cur)
                    rec.update(iou=iou, color_diff=dc, differs=bool(iou < 0.85 or dc > 30))
            else:
                rec["legacy"] = "нет строки Legacy (стиль 1)"
            res.append(rec)
            print(code, kit, rec.get("status"), rec.get("iou"), rec.get("color_diff"),
                  "ОТЛИЧАЕТСЯ" if rec.get("differs") else "", flush=True)
    with open(os.path.join(NHL24, "out", "fonts.json"), "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=1)


def cmd_sheet(a):
    try:
        font = ImageFont.truetype("C:/Windows/Fonts/segoeuib.ttf", 17)
        small = ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", 14)
    except OSError:
        font = small = ImageFont.load_default()
    with open(os.path.join(NHL24, "out", "fonts.json"), encoding="utf-8") as f:
        res = {(r["code"], r["kit"]): r for r in json.load(f)}
    x0, y0, x1, y1 = DIGITS
    cw, chh = 210, int(210 * (y1 - y0) / (x1 - x0))
    cols = 2
    row_h = chh + 40
    lw = 70
    sheet = Image.new("RGB", (cols * (lw + 4 * (cw + 6)) + 10, ((len(CLUBS) + cols - 1) // cols) * row_h + 40),
                      (30, 30, 34))
    d = ImageDraw.Draw(sheet)
    for c in range(cols):
        d.text((10 + c * (lw + 4 * (cw + 6)) + lw, 8), "home: Legacy | NHL 24", fill=(235, 235, 235), font=font)
        d.text((10 + c * (lw + 4 * (cw + 6)) + lw + 2 * (cw + 6), 8), "away: Legacy | NHL 24", fill=(235, 235, 235),
               font=font)

    def tile(img):
        bg = np.zeros_like(img[y0:y1, x0:x1, :3], dtype=np.float64)
        bg[:] = 110
        al = img[y0:y1, x0:x1, 3:4] / 255.0
        t = (bg * (1 - al) + img[y0:y1, x0:x1, :3] * al).astype(np.uint8)
        return Image.fromarray(t).resize((cw, chh), Image.LANCZOS)

    for i, (club, art, code) in enumerate(CLUBS):
        c, r = i % cols, i // cols
        x = 10 + c * (lw + 4 * (cw + 6))
        y = 36 + r * row_h
        d.text((x, y + chh // 2 - 8), code, fill=(235, 235, 235), font=font)
        for j, kit in enumerate(("home", "away")):
            rec = res.get((code, kit), {})
            xx = x + lw + j * 2 * (cw + 6)
            tgt = legacy_target(art, KITS[kit])
            cur = legacy_font(art, tgt["variant"]) if tgt else None
            if cur is not None:
                sheet.paste(tile(cur), (xx, y))
            p = os.path.join(OUT, f"{code}_{kit}", "font_cm.png")
            if rec.get("status") == "ok" and os.path.exists(p):  # только проверенные (sha1) — не старые файлы
                sheet.paste(tile(np.asarray(Image.open(p).convert("RGBA"))), (xx + cw + 6, y))
            else:
                d.text((xx + cw + 20, y + chh // 2 - 8), rec.get("status", "нет"), fill=(220, 130, 130), font=small)
            note = ("отличается" if rec.get("differs") else ("похож" if "iou" in rec else "")) + (
                f"  IoU {rec['iou']}, Δцвет {rec['color_diff']}" if "iou" in rec else "")
            d.text((xx, y + chh + 2), note, fill=(200, 200, 200), font=small)
    out = os.path.join(NHL24, "compare", "fonts_32.png")
    sheet.save(out)
    print(out, sheet.size)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("build")
    sub.add_parser("sheet")
    a = ap.parse_args()
    return {"build": cmd_build, "sheet": cmd_sheet}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
