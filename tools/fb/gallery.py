"""Галерея всех комплектов NHL 24 (570 свитеров league/nhl: 32 клуба, All-Star, legends) — для выбора форм.

Рендер на сетке своего кроя NHL 24 (player_jersey_<крой>_notuck_large), спереди и сзади — одна картинка на комплект.
Источник — extract/gallery24 (fb.extract по TOC, со сверкой sha1). Только локально, никуда не публиковать:
ассеты NHL 24 — только для личного использования.

  python -m fb.gallery build     # game/work/nhl24/gallery/<клуб>/<крой>_<комплект>.png, thumbs/, index.html
  python -m fb.gallery index     # только index.html (по уже готовым картинкам)
"""
import argparse
import csv
import html
import json
import os
import re
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from . import kit3d
from .cas import REPO
from .kit_batch import CLUBS

NHL24 = os.path.join(REPO, "game", "work", "nhl24")
SRC = os.path.join(NHL24, "extract", "gallery24")
OUT = os.path.join(NHL24, "gallery")
RX = re.compile(r"^content/character/skater/league/nhl/([a-z0-9]+)/([a-z0-9]+)/([a-z0-9]+)/jersey_\2_\1_\3_color$")
MESH = "content/character/skater/player/jersey/{cut}/components/player_jersey_{cut}_notuck_large_lod0_mesh"
CUTS = {"adidas": "adidas (с 2017)", "rbk": "Reebok Edge (2007–2017)", "nineties": "90-е"}
CUT_ORDER = ("adidas", "rbk", "nineties")
KIT_NAMES = {"home": "домашняя", "away": "выездная", "three": "третья", "two": "альтернативная 2",
             "four": "альтернативная 4", "five": "альтернативная 5", "six": "альтернативная 6",
             "seven": "альтернативная 7", "eight": "альтернативная 8", "nine": "альтернативная 9",
             "twentytwo": "Reverse Retro 2022", "twentythree": "Reverse Retro 2023"}
KIT_ORDER = ("home", "away", "three", "two", "four", "five", "six", "seven", "eight", "nine", "twentytwo", "twentythree")
SPECIAL = {"atlantic": "All-Star: Atlantic", "central": "All-Star: Central", "metropolitan": "All-Star: Metropolitan",
           "pacific": "All-Star: Pacific", "east": "All-Star: East", "west": "All-Star: West", "legends": "Legends"}
NOTE = {"ARI": "ARI → Utah, в пакет не идёт"}
VIEW_W = 420


def kits():
    """[{club, cut, kit, name, status, png}] — по _index.csv выгрузки (все 570 jersey_*_color league/nhl)."""
    out = []
    with open(os.path.join(SRC, "_index.csv"), encoding="utf-8") as f:
        for r in csv.DictReader(f):
            m = RX.match(r["name"])
            if m:
                out.append({"club": m.group(1), "cut": m.group(2), "kit": m.group(3), "name": r["name"],
                            "status": r["status"], "png": os.path.join(SRC, r["png"]) if r.get("png") else None})
    return out


def club_label(folder):
    code = {c: k for c, _a, k in CLUBS}.get(folder)
    return (code or SPECIAL.get(folder, folder)), code


def club_order(folders):
    nhl = sorted([f for f in folders if f not in SPECIAL], key=lambda f: club_label(f)[0])
    return nhl + [f for f in SPECIAL if f in folders]


def kit_key(k):
    return (CUT_ORDER.index(k["cut"]) if k["cut"] in CUT_ORDER else 9,
            KIT_ORDER.index(k["kit"]) if k["kit"] in KIT_ORDER else 99, k["kit"])


def file_of(k):
    return f"{k['cut']}_{k['kit']}.png"


def cmd_build(a):
    try:
        f_b = ImageFont.truetype("C:/Windows/Fonts/segoeuib.ttf", 20)
        f_r = ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", 16)
    except OSError:
        f_b = f_r = ImageFont.load_default()
    meshes = {}
    allk = kits()
    done = bad = 0
    for k in sorted(allk, key=lambda k: (k["club"],) + kit_key(k)):
        odir = os.path.join(OUT, k["club"])
        dst = os.path.join(odir, file_of(k))
        if k["status"] != "ok" or not k["png"] or not os.path.exists(k["png"]):
            bad += 1
            continue
        if os.path.exists(dst) and not a.force:
            done += 1
            continue
        cut = k["cut"]
        if cut not in meshes:
            meshes[cut] = kit3d.load_nhl24(MESH.format(cut=cut))
        tex = kit3d.load_tex(k["png"], 1024)
        views = [kit3d.render(meshes[cut], tex, v, VIEW_W, frame=kit3d.FRAME, ss=2) for v in ("front", "back")]
        lbl, code = club_label(k["club"])
        cap = f"{lbl}  ·  {k['club']} / {k['cut']} / {k['kit']}"
        sub = f"{CUTS.get(cut, cut)}, {KIT_NAMES.get(k['kit'], k['kit'])}" + (f"  —  {NOTE[code]}" if code in NOTE else "")
        W = VIEW_W * 2 + 30
        H = views[0].size[1] + 64
        im = Image.new("RGB", (W, H), (30, 30, 34))
        d = ImageDraw.Draw(im)
        d.text((10, 6), cap, fill=(240, 240, 240), font=f_b)
        d.text((10, 32), sub, fill=(200, 200, 200), font=f_r)
        for i, v in enumerate(views):
            im.paste(v, (10 + i * (VIEW_W + 10), 58))
        os.makedirs(os.path.join(odir, "thumbs"), exist_ok=True)
        im.save(dst)
        th = Image.new("RGB", (VIEW_W * 2 + 10, views[0].size[1]), (30, 30, 34))
        for i, v in enumerate(views):
            th.paste(v, (i * (VIEW_W + 10), 0))
        th.resize((th.size[0] * 3 // 8, th.size[1] * 3 // 8), Image.LANCZOS).save(os.path.join(odir, "thumbs", file_of(k)))
        done += 1
        if done % 25 == 0:
            print(done, k["club"], k["cut"], k["kit"], flush=True)
    print(f"картинок {done}, без текстуры {bad}")
    cmd_index(a)


PAGE = """<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Формы NHL 24</title>
<style>
:root {{ --bg:#1c1c20; --card:#26262c; --fg:#ececf0; --dim:#a8a8b4; --acc:#7fb2ff; }}
body {{ margin:0; background:var(--bg); color:var(--fg); font:15px/1.4 "Segoe UI",system-ui,sans-serif; }}
header {{ position:sticky; top:0; background:var(--bg); padding:10px 16px; border-bottom:1px solid #333; z-index:2; }}
h1 {{ font-size:20px; margin:0 0 6px; }}
nav a {{ color:var(--acc); text-decoration:none; margin-right:10px; white-space:nowrap; }}
main {{ padding:0 16px 40px; }}
h2 {{ margin:28px 0 4px; font-size:18px; }}
h3 {{ margin:12px 0 6px; font-size:15px; color:var(--dim); font-weight:600; }}
.grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(330px,1fr)); gap:10px; }}
figure {{ margin:0; background:var(--card); border-radius:6px; padding:6px; }}
figure img {{ width:100%; height:auto; display:block; cursor:zoom-in; border-radius:4px; }}
figcaption {{ font-size:13px; color:var(--dim); margin-top:4px; }}
figcaption b {{ color:var(--fg); font-weight:600; }}
.miss {{ height:120px; display:flex; align-items:center; justify-content:center; color:#d88; font-size:13px; }}
.note {{ color:#e0a060; font-size:13px; }}
#box {{ position:fixed; inset:0; background:rgba(0,0,0,.88); display:none; align-items:center; justify-content:center;
        z-index:9; cursor:zoom-out; }}
#box img {{ max-width:96vw; max-height:94vh; }}
</style></head>
<body>
<header><h1>Формы NHL 24 — {total} комплектов (рендер на сетке NHL 24, спереди и сзади)</h1>
<div class="note">Только для личного использования: картинки из дампа пользователя, никуда не публиковать.</div>
<nav>{nav}</nav></header>
<main>
{body}
</main>
<div id="box" onclick="this.style.display='none'"><img id="big" alt=""></div>
<script>
document.querySelectorAll('figure img').forEach(function (im) {{
  im.addEventListener('click', function (e) {{
    e.preventDefault();
    document.getElementById('big').src = im.dataset.big;
    document.getElementById('box').style.display = 'flex';
  }});
}});
document.addEventListener('keydown', function (e) {{ if (e.key === 'Escape') document.getElementById('box').style.display = 'none'; }});
</script>
</body></html>
"""


def cmd_index(a):
    allk = kits()
    by = {}
    for k in allk:
        by.setdefault(k["club"], []).append(k)
    nav, body = [], []
    for folder in club_order(by):
        lbl, code = club_label(folder)
        ks = sorted(by[folder], key=kit_key)
        nav.append(f'<a href="#{folder}">{html.escape(lbl)}</a>')
        note = f' <span class="note">{html.escape(NOTE[code])}</span>' if code in NOTE else ""
        body.append(f'<h2 id="{folder}">{html.escape(lbl)} <small style="color:#888">({folder}, {len(ks)})</small>{note}</h2>')
        for cut in CUT_ORDER + tuple(sorted({k["cut"] for k in ks} - set(CUT_ORDER))):
            cks = [k for k in ks if k["cut"] == cut]
            if not cks:
                continue
            body.append(f"<h3>{html.escape(CUTS.get(cut, cut))}</h3><div class=\"grid\">")
            for k in cks:
                fn = file_of(k)
                cap = (f"<b>{html.escape(folder)} / {html.escape(cut)} / {html.escape(k['kit'])}</b> — "
                       f"{html.escape(KIT_NAMES.get(k['kit'], k['kit']))}")
                if os.path.exists(os.path.join(OUT, folder, fn)):
                    img = (f'<a href="{folder}/{fn}"><img src="{folder}/thumbs/{fn}" data-big="{folder}/{fn}" '
                           f'loading="lazy" alt="{html.escape(fn)}"></a>')
                else:
                    img = f'<div class="miss">нет текстуры ({html.escape(k["status"])})</div>'
                body.append(f"<figure>{img}<figcaption>{cap}</figcaption></figure>")
            body.append("</div>")
    page = PAGE.format(total=len(allk), nav=" ".join(nav), body="\n".join(body))
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "index.html"), "w", encoding="utf-8", newline="\n") as f:
        f.write(page)
    st = {}
    for k in allk:
        st[k["status"]] = st.get(k["status"], 0) + 1
    with open(os.path.join(OUT, "_summary.json"), "w", encoding="utf-8") as f:
        json.dump({"kits": len(allk), "status": st, "clubs": len(by)}, f, ensure_ascii=False, indent=1)
    print(os.path.join(OUT, "index.html"), len(allk), "комплектов", st)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--force", action="store_true", help="перерисовать и готовые")
    sub.add_parser("index")
    a = ap.parse_args()
    return {"build": cmd_build, "index": cmd_index}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
