"""Спины всех форм слота одним листом — фамилия и номер так, как их рисует игра: знак берётся клеткой атласа целиком
(с полями клетки), клетка буквы вписывается в зону карты номеров по высоте; номер (проверено в игре 24.10) — холст из
двух клеток цифр во всю зону 1 (клетка — шириной в половину зоны), однозначный — клетка в средней половине. Видно
размер букв и номера, промежутки и отступы (от кокетки сверху, до полос снизу) у всех клубов сразу.

    python -m kitport backs [--clubs MIN,BUF] [--name ABCDEFGH] [--number 88] [--out FILE]

Отличие от kitport present: там буквы вписаны в зону по своему габариту с условной разрядкой (LETTER_GAP) —
крупнее и плотнее, чем в игре.
"""
import datetime
import os
import sys

import numpy as np

from . import core

NAME_ROWS = ((1, 48), (49, 98))
DIGIT_ROWS = ((115, 238), (242, 367))
DIGIT_PITCH = 80
FRAME = (-0.30, 0.30, 1.05, 1.72)             # x0, x1, y0, y1, м — спина
CELL_W = {"I": 16, "M": 48, "W": 48}           # ширина клетки буквы, px атласа (по раскладке EA; как у игры — не
#                                                разбиралось, docs/kitport.md §2.5)


def _only_main(cell):
    """Клетка атласа без соседних знаков (у EA между буквами — ' . -, у цифр — край соседней): оставить связные
    части, что пересекают средние 40 % ширины клетки."""
    from scipy import ndimage as ndi
    a = cell[..., 3] > 40
    lab, n = ndi.label(a)
    w = cell.shape[1]
    keep = np.zeros_like(a)
    mid = slice(int(w * 0.3), int(w * 0.7) + 1)
    for i in range(1, n + 1):
        m = lab == i
        if m[:, mid].any():
            keep |= m
    out = cell.copy()
    out[~ndi.binary_dilation(keep, iterations=2)] = 0
    return out


def cell_name(font, name):
    """Фамилия из клеток атласа (RGBA): клетка буквы — от середины до середины соседей (fb.jersey_mesh.FONT_SLOTS),
    высота — строка атласа целиком; соседние знаки в клетке убраны."""
    from fb import jersey_mesh as J
    from fb.fonts import CAPTAIN_BOX
    parts = []
    for ch in name:
        row = 0 if ch in J.FONT_ROWS[0][0] else 1
        letters = J.FONT_ROWS[row][0]
        if ch not in letters:
            continue
        cx = J.FONT_SLOTS[row]
        i = letters.index(ch)
        if i >= len(cx):
            continue
        w = CELL_W.get(ch, 32)                         # клетки разной ширины: у EA I смещена (центр 264 между H 240 и
        x0, x1 = cx[i] - w // 2, cx[i] + w // 2        # J 304), M и W — через 48 px: I — 16, M и W — 48, прочие — 32
        right_end = 512 if row == 0 else CAPTAIN_BOX[0]
        x0, x1 = max(0, x0), min(right_end, x1)
        y0, y1 = NAME_ROWS[row]
        parts.append(_only_main(font[y0:y1, x0:x1]))
    h = max(p.shape[0] for p in parts)
    return np.concatenate([np.pad(p, ((0, h - p.shape[0]), (0, 0), (0, 0))) for p in parts], 1)


def _digit_centres(font, y0, y1):
    """Середины цифр строки атласа (по разрывам столбцов), слева направо."""
    cols = (font[y0:y1, :420, 3] > 40).any(0)
    out, x = [], 0
    while x < len(cols):
        if cols[x]:
            s0 = x
            while x < len(cols) and cols[x]:
                x += 1
            if x - s0 > 8:
                out.append((s0 + x) / 2)
        else:
            x += 1
    return out


def cell_number(font, number):
    """Номер из клеток цифр (DIGIT_PITCH, от 0), соседние знаки убраны."""
    parts = []
    for ch in number:
        d = int(ch)
        y0, y1 = DIGIT_ROWS[0 if d < 5 else 1]
        x0 = (d % 5) * DIGIT_PITCH                    # клетки цифр — по 80 px (fb.fonts.DIGIT_CELL), как у игры
        cell = np.zeros((y1 - y0, DIGIT_PITCH, 4), np.uint8)
        a0, a1 = max(0, x0), min(font.shape[1], x0 + DIGIT_PITCH)
        cell[:, a0 - x0:a1 - x0] = font[y0:y1, a0:a1]
        parts.append(_only_main(cell))
    h = max(p.shape[0] for p in parts)
    num = np.concatenate([np.pad(p, ((0, h - p.shape[0]), (0, 0), (0, 0))) for p in parts], 1)
    if len(parts) == 1:                               # однозначный — клетка в средней половине холста из двух клеток
        num = np.pad(num, ((0, 0), (DIGIT_PITCH // 2, DIGIT_PITCH // 2), (0, 0)))
    return num


def zone_number(font, number, name_png):
    """Номер под зону 1, как в игре: холст из двух клеток растянут по ширине до пропорции зоны на свитере
    (edge_kit.zone_size_cm) — jersey_mesh.stamp вписывает его по высоте и он ложится во всю зону."""
    from PIL import Image
    from fb import edge_kit as E
    num = cell_number(font, number)
    zs = E.zone_size_cm(name_png, 1)
    if not zs:
        return num
    th = num.shape[0]                                 # холст — всегда две клетки (однозначный — с полями)
    w2 = max(1, int(round(th * zs[0] / zs[1])))
    return np.asarray(Image.fromarray(num).resize((w2, th), Image.LANCZOS))


def cmd_backs(a):
    os.environ.setdefault("PHOTOS_SOURCE", "nhl24")
    sys.path.insert(0, core.TOOLS)
    import scans24 as S
    from PIL import Image, ImageDraw, ImageFont
    from fb import edge_kit as E, jersey_mesh as J
    from .present import zone_rects
    src = core.slot_kits_dir()
    kits = sorted(k for k in os.listdir(src) if os.path.isdir(os.path.join(src, k)) and
                  os.path.exists(os.path.join(src, k, "font_cm.png")))
    if a.clubs:
        kits = [k for k in kits if k.split("_")[0] in a.clubs.split(",")]
    M = E.mesh_for(0, 1, 2)
    nrm = S.weld_normals(M["pos"], M["tri"], S.weld_ids(M["pos"]))
    font_ = ImageFont.truetype(os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", "segoeui.ttf"), 16)
    tiles = []
    for kit in kits:
        d = os.path.join(src, kit)
        t = np.asarray(Image.open(os.path.join(d, "jersey_cm.png")).convert("RGB")).astype(np.float64)
        f = np.asarray(Image.open(os.path.join(d, "font_cm.png")).convert("RGBA"))
        rects = zone_rects(os.path.join(d, "name_cm.png"))
        if 0 in rects:
            t = J.stamp(t, M, rects[0], cell_name(f, a.name.upper()))
        if 1 in rects:
            t = J.stamp(t, M, rects[1], zone_number(f, a.number, os.path.join(d, "name_cm.png")))
        im = S.render([{"pos": M["pos"], "nrm": nrm, "uv": M["uv"], "tri": M["tri"], "tex": t, "twosided": True}],
                      np.radians(180), 300, frame=FRAME)
        tile = Image.new("RGB", (im.size[0], im.size[1] + 22), (24, 24, 28))
        tile.paste(im, (0, 22))
        ImageDraw.Draw(tile).text((4, 2), kit, fill=(255, 220, 140), font=font_)
        tiles.append(tile)
    cols = a.cols
    w, h = tiles[0].size
    rows = (len(tiles) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * (w + 4), rows * (h + 4)), (10, 10, 12))
    for i, tl in enumerate(tiles):
        sheet.paste(tl, ((i % cols) * (w + 4), (i // cols) * (h + 4)))
    out = a.out or os.path.join(core.COMPARE, f"backs-{datetime.datetime.now():%Y%m%d-%H%M}.png")
    sheet.save(out)
    print("лист →", out)
    return 0


def render_number(d, number, M, nrm, frame=(-0.24, 0.24, 1.12, 1.52), px=420):
    """Спина формы из папки d (jersey_cm, font_cm, name_cm) с номером, как в игре, крупно: кадр — область номера."""
    import scans24 as S
    from PIL import Image
    from fb import jersey_mesh as J
    from .present import zone_rects
    t = np.asarray(Image.open(os.path.join(d, "jersey_cm.png")).convert("RGB")).astype(np.float64)
    f = np.asarray(Image.open(os.path.join(d, "font_cm.png")).convert("RGBA"))
    rects = zone_rects(os.path.join(d, "name_cm.png"))
    if 1 in rects:
        t = J.stamp(t, M, rects[1], zone_number(f, number, os.path.join(d, "name_cm.png")))
    return S.render([{"pos": M["pos"], "nrm": nrm, "uv": M["uv"], "tri": M["tri"], "tex": t, "twosided": True}],
                    np.radians(180), px, frame=frame)


def cmd_numbers(a):
    """Номер на спине крупно: фото настоящей формы | снимок «было» (kitport snapshot) | слот сейчас — для сравнения
    промежутка цифр (24.10). Спецификации — «КЛУБ_ФОРМА|НОМЕР|ФОТО|x0,y0,x1,y1» (фото и рамку можно опустить:
    «CHI_away|98»). Фото настоящих — только для личного использования: лист — в compare/ (вне git)."""
    os.environ.setdefault("PHOTOS_SOURCE", "nhl24")
    sys.path.insert(0, core.TOOLS)
    import scans24 as S
    from PIL import Image, ImageDraw, ImageFont
    from fb import edge_kit as E
    before = a.before or core.latest_snapshot()
    M = E.mesh_for(0, 1, 2)
    nrm = S.weld_normals(M["pos"], M["tri"], S.weld_ids(M["pos"]))
    font_ = ImageFont.truetype(os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", "segoeui.ttf"), 15)
    H = a.height
    rows = []
    for spec in a.specs:
        parts = spec.split("|")
        kit, number = parts[0], parts[1]
        tiles = []
        if len(parts) >= 4 and os.path.exists(parts[2]):
            x0, y0, x1, y1 = map(int, parts[3].split(","))
            im = Image.open(parts[2]).convert("RGB").crop((x0, y0, x1, y1))
            tiles.append(("фото", im.resize((max(1, int(im.size[0] * H / im.size[1])), H), Image.LANCZOS)))
        for tag, base in (("было", before), ("сейчас", core.slot_kits_dir())):
            d = os.path.join(base, kit) if base else None
            if d and os.path.exists(os.path.join(d, "font_cm.png")):
                r = render_number(d, number, M, nrm)
                tiles.append((tag, r.resize((int(r.size[0] * H / r.size[1]), H), Image.LANCZOS)))
        row = Image.new("RGB", (130 + sum(t.size[0] + 6 for _, t in tiles), H + 4), (16, 16, 18))
        dr = ImageDraw.Draw(row)
        dr.text((6, H // 2 - 10), f"{kit} {number}", fill=(255, 220, 140), font=font_)
        x = 130
        for tag, t in tiles:
            row.paste(t, (x, 2))
            dr.text((x + 4, 4), tag, fill=(255, 255, 0), font=font_)
            x += t.size[0] + 6
        rows.append(row)
    if not rows:
        sys.exit("нет спецификаций «КЛУБ_ФОРМА|НОМЕР[|ФОТО|x0,y0,x1,y1]»")
    sheet = Image.new("RGB", (max(r.size[0] for r in rows), sum(r.size[1] for r in rows)), (0, 0, 0))
    y = 0
    for r in rows:
        sheet.paste(r, (0, y))
        y += r.size[1]
    out = a.out or os.path.join(core.COMPARE, f"numbers-{datetime.datetime.now():%Y%m%d-%H%M}.png")
    sheet.save(out)
    print("лист →", out, "(было —", before, ")")
    return 0
