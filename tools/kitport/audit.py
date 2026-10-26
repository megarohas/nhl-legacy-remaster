"""Автопроверка форм слота — то, что пользователь находил в игре (23.10), одной командой по всем формам.

    python -m kitport audit [--clubs ANA,COL] [--helmets]

Проверки (каждая — по обеим формам клуба):
- номера на рукавах (зоны 2, 3) и места литеры (5, 7): фон под зоной карты номеров на развёртке свитера — один цвет;
  второй цвет больше AUDIT_MIX доли — номер на полосе или на границе цветов («номер на руке ложится на полосу», OTT,
  ANA, WPG); зона вне развёртки больше AUDIT_OUT — номер режется (сдвиг зоны слишком далеко);
- номер на спине: высота против профиля (`number_h_cm`, иначе стандарт edge_kit.LETTERING_NUM_H) ± AUDIT_NUM_TOL;
  промежуток цифр (видимый край, к высоте цифры, как рисует игра — kitport lettering) против профиля `digit_gap`
  (иначе edge_kit.DIGIT_GAP) ± lettering.DIGIT_GAP_TOL (24.10: «цифры можно ближе — как у настоящих»);
  фамилия — промежуток букв против edge_kit.NAME_FIT_GAP_MIN … NAME_FIT_GAP;
- гетры: нижние строки своих гетр (flat_sock) против нижних строк перенесённых с источника — у NHL 27 низ бывает
  другого цвета («оранжевая полоска внизу гетр», ANA, COL, NSH);
- шорты pant = "source": рельеф (pant_nm слота) — только под нашими нашивками (fb.pant_decals.relief_check): рельеф
  герба или щита образца Legacy вне наших нашивок не стёрт, наша нашивка без рельефа («лого на трусах выше и сбоку
  относительно рельефного места», DET, 23.10; щит — с 24.10);
- шорты pant = "source": место нашивок на шортах полевых в игре (fb.pant_decals.place_check, сетка GAME_MESH) — центр
  герба и щита NHL против правила LEG_SLOTS (угол вокруг ноги, высота над краем штанины), низ над подворотом, изгиб
  под нашивкой, пропорции против источника («логотипы и щиты на шортах слишком высоко», прежде — «сплюснутый герб у
  края», 24.10: раскладка шла по сетке шорт вратаря);
- полосы рукава (26.10; пользователь после игры: «калгари — светлая форма — кривые предплечья», ANA — «полоски неровные
  в районе чёрного клина»; раньше STL — «полоски на предплечьях с белыми выемками»), если у источника рисунок рукава
  кольцами (в строках кольца развёртки NHL 24 — один порядок цветов): строки кольца нашего рукава (зона колец u < SLV_U,
  без концов у шва снизу) подряд не по самому частому порядку — выемка, клин, пропавшая полоса (sleeve_rows); край полосы
  по строкам (весь рукав до шва проймы) отходит от скользящей медианы на AUDIT_SLV_TOOTH px — зубцы, крючки
  (sleeve_teeth); ложная нашивка на рукаве — patch_N мельче AUDIT_SLV_PATCH (дуга у границы полос, kit_rules.toml
  stripe_edge_*, sleeve_patch). Крупно — `kitport arm`;
- --helmets: строка шлема NHL 27, из которой взята каска (kitport.profile.eq_pick) — общая (−1, −1) или первая era 2
  вместо своей строки формы (COL дом: чёрный вместо синего); нужна база NHL 27 (FB_GAME=nhl27 не обязателен).
Принятое пользователем или проверенное глазами — поле профиля `audit_accept` (список проверок с причиной в комментарии:
sleeve_mix, sleeve_out, letter_mix, letter_out, number, digit_gap, name_gap, sock, pant_relief, pant_place, sleeve_rows,
sleeve_teeth, sleeve_patch, helmet) — не замечание
(печатается «принято»).
Итог — таблица замечаний; код выхода 1, если они есть. Порядок работы с новыми формами — docs/kitport.md §12.11.
"""
import os
import sys

import numpy as np

from . import core

AUDIT_MIX = 0.15        # доля второго цвета под зоной номера на рукаве / литеры — больше: полоса или граница
AUDIT_OUT = 0.05        # доля зоны номера на рукаве вне развёртки — больше: номер режется
AUDIT_OUT_LETTER = 0.15 # у литеры зона EA шире буквы: вне развёртки до 11 % у одобренных (PIT, UTA) — буква цела
AUDIT_NUM_TOL = 0.04    # номер на спине — от заданной высоты не дальше ±4 %
AUDIT_SOCK = 40.0       # низ гетр: разница цвета (max по каналу) с источником — больше: «полоска внизу»
ZONES = {2: "номер на рукаве", 3: "номер на рукаве", 5: "литера", 7: "литера (2-е место)"}
AUDIT_SLV_ROWS = 8      # полосы рукава: строк кольца подряд не по рисунку — выемка / клин (строка ~1 мм по кругу руки)
AUDIT_SLV_SRC_RING = 0.85   # … если у источника рисунок кольцами: доля строк кольца NHL 24 с одним порядком цветов (у ANA —
#                             0,90: шеврон; у CBJ, WSH, COL, PHI, WPG выезд, OTT, CAR выезд — полосы вдоль руки, 0,39–0,82)
AUDIT_SLV_TOOTH = 4.0   # px: край полосы отходит от скользящей медианы 9 строк — зубец (и ≥ 3 строк от 3 px)
AUDIT_SLV_CORE = (0.335, 0.685)   # v: строки колец рукава Edge без концов у шва снизу (там строки неполные)
AUDIT_SLV_SRC = ((0.045, 0.30), (0.37, 0.63))   # u, v рукава NHL 24 (2048²): замер «кольцами» у источника
AUDIT_SLV_PATCH = 4000  # тексели 2048²: patch_N на рукаве (u < 0,30 / > 0,70) мельче — дуга у границы полос (FLA — 18 000)


def zone_background(jersey, name, zone, tid):
    """Фон под зоной карты номеров: (доля главного цвета, второй цвет и его доля, доля вне развёртки)."""
    m = (name[..., 0] > 128) & (name[..., 1] > 128) & (name[..., 2] == zone)
    if not m.any():
        return None
    S = jersey.shape[0]
    ys, xs = np.nonzero(m)
    k = S // name.shape[0]                              # карта номеров 256², свитер 1024²: тексель зоны — k × k
    dy, dx = np.meshgrid(np.arange(k), np.arange(k), indexing="ij")
    yy = (ys[:, None] * k + dy.ravel()[None, :]).ravel()
    xx = (xs[:, None] * k + dx.ravel()[None, :]).ravel()
    on = tid[yy, xx] >= 0
    out = 1.0 - float(on.mean())
    c = jersey[yy[on], xx[on]]
    if not len(c):
        return 0.0, None, 0.0, out
    q = np.round(c / 24.0).astype(np.int64)
    key = (q[:, 0] * 64 + q[:, 1]) * 64 + q[:, 2]
    ks, cnt = np.unique(key, return_counts=True)
    o = np.argsort(-cnt)
    main = cnt[o[0]] / len(c)
    if len(o) < 2:
        return float(main), None, 0.0, out
    second = np.round(np.median(c[key == ks[o[1]]], axis=0)).astype(int).tolist()
    return float(main), second, float(cnt[o[1]] / len(c)), out


def sleeve_geometry(E, kit3d):
    """Растры рукавов для sleeve_flags: развёртка Edge 1024² (сторона тела, зоны колец и рукава до шва проймы) и NHL 24
    2048² (сторона, зона замера «кольцами»)."""
    from .present import n24_meshes
    M = E.mesh_for(0, 1, 2)
    out = {}
    for name, mesh, S in (("e", M, 1024), ("n", n24_meshes()["j"], 2048)):
        tid, bar = kit3d.raster_uv(mesh, S)
        occ = tid >= 0
        ys, xs = np.nonzero(occ)
        X = np.zeros((S, S))
        X[ys, xs] = (bar[ys, xs] * mesh["pos"][mesh["tri"][tid[ys, xs]]][:, :, 0]).sum(1)
        out[name] = (S, occ & (X < 0), (occ & (X > 0))[:, ::-1])      # левая; правая — зеркально (как у левого рукава)
    vv = (np.arange(1024) + 0.5) / 1024
    band = (vv[:, None] >= E.SLV_V[0]) & (vv[:, None] <= E.SLV_V[1])
    out["ring"] = band & (vv[None, :] < E.SLV_U[1])
    out["arm"] = band & (vv[None, :] < E.armhole_u(vv)[:, None])
    v2 = (np.arange(2048) + 0.5) / 2048
    (u0, u1), (v0, v1) = AUDIT_SLV_SRC
    out["src"] = (v2[:, None] >= v0) & (v2[:, None] <= v1) & (v2[None, :] >= u0) & (v2[None, :] <= u1)
    return out


def _slv_rows(E, A, reg):
    """Строки зоны reg: {строка: (первый столбец, ширина, отрезки цветов)} — палитра и отрезки как у edge_kit
    (_slv_palette, _slv_runs)."""
    pal = E._slv_palette(A, reg)
    if len(pal) < 2:
        return {}
    lab = np.stack([np.abs(A - p).max(-1) for p in pal], -1).argmin(-1)
    rows = {}
    for r in np.nonzero(reg.any(1))[0]:
        cols = np.nonzero(reg[r])[0]
        rows[r] = (cols.min(), len(cols), E._slv_runs(lab[r, cols.min():cols.max() + 1]))
    return rows


def _slv_keys(rows, rmin=None, rmax=None):
    """Порядки цветов строк полной ширины (≥ 0,9 наибольшей) в rmin…rmax: {строка: порядок}."""
    if not rows:
        return {}
    wmax = max(w for _, w, _ in rows.values())
    return {r: tuple(q[0] for q in rr) for r, (x0, w, rr) in rows.items()
            if w >= 0.9 * wmax and (rmin is None or rmin <= r <= rmax)}


def sleeve_flags(E, J, club, kit, jersey, geo, src_d):
    """Полосы рукава: [(проверка, замечание)] — выемки (строки кольца не по рисунку), зубцы краёв, ложные нашивки."""
    import json
    from PIL import Image
    from scipy.ndimage import median_filter
    from fb.jersey_hybrid import CLUB_NAME
    out = []
    info = os.path.join(src_d, "info.json")
    if os.path.exists(info):
        with open(info, encoding="utf-8") as f:
            for p in json.load(f).get("patches", []):
                if p.get("name", "").startswith("patch_") and (p["uv"][0] < 0.30 or p["uv"][0] > 0.70) and \
                        p.get("area", 0) < AUDIT_SLV_PATCH:
                    out.append(("sleeve_patch", f"рукав: {p['name']} у uv {p['uv']} ({p['area']} тексл.) — ложная нашивка "
                                                "у границы полос (kit_rules.toml stripe_edge_*)"))
    src = J.n24_tex(CLUB_NAME[club], kit, "base_color")
    if not os.path.exists(src):
        return out
    S2 = geo["n"][0]
    a2 = np.asarray(Image.open(src).convert("RGB").resize((S2, S2))).astype(np.float64)
    S = geo["e"][0]
    for side, name in ((0, "левый"), (1, "правый")):
        A2 = a2 if side == 0 else a2[:, ::-1]
        k2 = _slv_keys(_slv_rows(E, A2, geo["src"] & geo["n"][1 + side]))
        if not k2:
            continue
        cnt = {}
        for k in k2.values():
            cnt[k] = cnt.get(k, 0) + 1
        if max(cnt.values()) / len(k2) < AUDIT_SLV_SRC_RING:
            continue                                     # у источника полосы не кольцами (вдоль руки, наискосок)
        A = jersey if side == 0 else jersey[:, ::-1]
        sm = geo["e"][1 + side]
        rows = _slv_rows(E, A, geo["ring"] & sm)
        keys = _slv_keys(rows, int(AUDIT_SLV_CORE[0] * S), int(AUDIT_SLV_CORE[1] * S))
        if keys:
            cnt = {}
            for k in keys.values():
                cnt[k] = cnt.get(k, 0) + 1
            pat = max(cnt, key=cnt.get)
            if cnt[pat] >= 0.5 * len(keys):              # у нас кольца (иначе — шеврон ANA: только зубцы)
                bad = sorted(r for r, k in keys.items() if k != pat)
                g = []
                for r in bad:
                    if g and r - g[-1][1] <= 2:
                        g[-1][1] = r
                    else:
                        g.append([r, r])
                for r0, r1 in g:
                    if r1 - r0 + 1 >= AUDIT_SLV_ROWS:
                        out.append(("sleeve_rows", f"рукав {name}: строки кольца v {r0 / S:.3f}–{r1 / S:.3f} ({r1 - r0 + 1}) "
                                                   "не по рисунку полос — выемка / клин (kitport arm)"))
        rows = _slv_rows(E, A, geo["arm"] & sm)
        if not rows:
            continue
        cnt = {}
        for r, (x0, w, rr) in rows.items():
            k = tuple(q[0] for q in rr)
            cnt[k] = cnt.get(k, 0) + 1
        pat = max(cnt, key=lambda k: (len(k), cnt[k]) if cnt[k] > 0.15 * len(rows) else (0, 0))
        for e in range(len(pat) - 1):                    # край e — по строкам с этим порядком (или его началом)
            rs, bs = [], []
            for r, (x0, w, rr) in sorted(rows.items()):
                k = tuple(q[0] for q in rr)
                if k == pat[:len(k)] and len(k) > e + 1:
                    rs.append(r)
                    bs.append(rr[e][2] + x0)
            if len(rs) < 20:
                continue
            bs = np.asarray(bs, np.float64)
            dev = np.abs(bs - median_filter(bs, 9, mode="nearest"))
            if dev.max() >= AUDIT_SLV_TOOTH and (dev >= 3).sum() >= 3:
                out.append(("sleeve_teeth", f"рукав {name}: край полосы {e} — зубец {dev.max():.0f} px у v "
                                            f"{rs[int(dev.argmax())] / S:.3f} (kitport arm)"))
    return out


def check_kit(club, kit, d, src_d, tid, prof, E, lettering, geo=None):
    from PIL import Image
    flags = []
    acc = set(prof.get("audit_accept", []))
    def flag(kind, text):
        flags.append(text if kind not in acc else f"(принято) {text}")
    jersey = np.asarray(Image.open(os.path.join(d, "jersey_cm.png")).convert("RGB")).astype(np.float64)
    name = np.asarray(Image.open(os.path.join(d, "name_cm.png")).convert("RGBA"))
    if geo is not None:                                  # полосы рукава (26.10: CGY, ANA)
        from fb import jersey_mesh as J
        for kind, text in sleeve_flags(E, J, club, kit, jersey, geo, src_d):
            flag(kind, text)
    for z, what in ZONES.items():
        r = zone_background(jersey, name, z, tid)
        if r is None:
            continue
        main, second, share, out = r
        kind = "sleeve" if z in (2, 3) else "letter"
        if share > AUDIT_MIX:
            flag(kind + "_mix", f"{what} (зона {z}): под ним второй цвет {second} — {share:.0%} (полоса / граница цветов)")
        if out > (AUDIT_OUT if z in (2, 3) else AUDIT_OUT_LETTER):
            flag(kind + "_out", f"{what} (зона {z}): {out:.0%} зоны вне развёртки — режется")
    k, _ = E.back_m_per_v()
    r = lettering.measure(d, k / 256.0)
    want = float(prof.get("number_h_cm", E.LETTERING_NUM_H * 100))
    if abs(r["num_h"] / want - 1) > AUDIT_NUM_TOL:
        flag("number", f"номер на спине {r['num_h']:.1f} см при заданных {want:g} ({r['num_h'] / want - 1:+.0%})")
    gap_want = float(E.DIGIT_GAPS.get(kit, E.DIGIT_GAPS.get("*", E.DIGIT_GAP)))   # промежуток цифр (24.10, по фото)
    if E.LETTERING == "standard" and r.get("digit_gap") is not None and abs(r["digit_gap"] - gap_want) > lettering.DIGIT_GAP_TOL:
        flag("digit_gap", f"промежуток цифр номера {r['digit_gap']:.3f} высоты цифры при цели {gap_want:g} (digit_gap)")
    if prof.get("font_plate"):                        # фамилия на подложке (PHI): промежуток по альфе не мерится
        pass
    elif r["gap_ratio"] > E.NAME_FIT_GAP + 0.02:      # допуск — как у kitport lettering (одобренные DAL, SEA — 0,22–0,23)
        flag("name_gap", f"фамилия разрежена: промежуток {r['gap_ratio']:.2f} высоты буквы (≤ {E.NAME_FIT_GAP})")
    elif r["gap_ratio"] < E.NAME_FIT_GAP_MIN - 0.02:  # широкий шрифт (DET, STL, CAR выезд) — 0,14
        flag("name_gap", f"фамилия слиплась: промежуток {r['gap_ratio']:.2f} высоты буквы (≥ {E.NAME_FIT_GAP_MIN})")
    ours, src = os.path.join(d, "sock_cm.png"), os.path.join(src_d, "sock_cm.png")
    if os.path.exists(ours) and os.path.exists(src):
        a = np.asarray(Image.open(ours).convert("RGB")).astype(np.float64)
        b = np.asarray(Image.open(src).convert("RGB")).astype(np.float64)
        ca = np.median(a[-6:].reshape(-1, 3), axis=0)
        cb = np.median(b[-6:, b.shape[1] // 4:3 * b.shape[1] // 4].reshape(-1, 3), axis=0)
        if np.abs(ca - cb).max() > AUDIT_SOCK:
            flag("sock", f"низ гетр {np.round(ca).astype(int).tolist()}, у источника {np.round(cb).astype(int).tolist()}"
                         " — полоска внизу")
    spec = prof.get("slot", {}).get(kit, {})
    if spec.get("pant", "legacy") == "source":       # рельеф шорт — под нашими гербами (23.10, DET)
        from fb import pant_decals
        tpl = os.path.join(E.WORK, "cur_kits", spec["legacy"])
        if os.path.exists(os.path.join(tpl, "pant_nm.png")):
            for t in pant_decals.relief_check(tpl, d, os.path.join(src_d, pant_decals.MASKS))[0]:
                flag("pant_relief", t)
        info = os.path.join(src_d, "info.json")     # место нашивок на шортах полевых в игре (24.10, «слишком высоко»)
        rep = None
        if os.path.exists(info):
            import json
            with open(info, encoding="utf-8") as f:
                rep = json.load(f).get("pant_decals")
        for t in pant_decals.place_check(os.path.join(src_d, pant_decals.MASKS), rep)[0]:
            flag("pant_place", t)
    return flags


def helmet_flags(clubs):
    """Каска: из какой строки NHL 27 (eq_pick) — {(клуб, форма): замечание}."""
    sys.path.insert(0, os.path.join(core.TOOLS, "legacy_data"))
    import nhl24 as N24
    from . import profile as PR
    N, db27 = PR.nhl27_db()
    out = {}
    for code in clubs:
        team27 = PR.nhl27_team(N, N24.CLUBS[code][0])
        v27 = PR.nhl27_kits(db27, team27)
        rows = PR.nhl27_equipment(db27, team27, PR.EQ_HELMET)
        for kit, loc in (("home", 0), ("away", 1)):
            if loc not in v27:
                continue
            z, w = PR.eq_pick(rows, v27[loc])
            if w == "era -1, variant -1":                # общая строка — не так, как выбирает NHL 27 (COL дом, 23.10)
                out[(code, kit)] = f"каска — из строки NHL 27 «{w}» (своей строки формы {v27[loc]} нет): {z[0] if z else None}"
    return out


def cmd_audit(a):
    sys.path.insert(0, core.TOOLS)
    os.environ.setdefault("PHOTOS_SOURCE", "nhl24")
    from fb import edge_kit as E, kit3d
    from . import lettering
    src = core.slot_kits_dir()
    want = set(a.clubs.split(",")) if a.clubs else None
    kits = sorted(d for d in os.listdir(src) if os.path.isdir(os.path.join(src, d)) and "_" in d
                  and (want is None or d.split("_")[0] in want))
    profs = E.club_profiles()
    M = E.mesh_for(0, 1, 2)
    tid, _ = kit3d.raster_uv(M, 1024)
    geo = sleeve_geometry(E, kit3d)
    helm = helmet_flags(sorted({k.split("_")[0] for k in kits if k.split("_")[0] in profs})) if a.helmets else {}
    bad = 0
    for kit in kits:
        club, k = kit.split("_", 1)
        if club not in profs:
            continue
        E.use_club(club)
        flags = check_kit(club, k, os.path.join(src, kit), os.path.join(E.KITS_OUT, kit), tid, profs[club], E,
                          lettering, geo)
        if (club, k) in helm:
            flags.append(helm[(club, k)] if "helmet" not in profs[club].get("audit_accept", []) else
                         "(принято) " + helm[(club, k)])
        bad += any(not f.startswith("(принято)") for f in flags)
        print(f"{kit:9s} " + ("чисто" if not flags else ("\n" + " " * 10).join(flags)))
    print(f"форм с замечаниями: {bad} из {len(kits)}")
    return 1 if bad else 0
