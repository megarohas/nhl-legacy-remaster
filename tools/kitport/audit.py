"""Автопроверка форм слота — то, что пользователь находил в игре (23.10), одной командой по всем формам.

    python -m kitport audit [--clubs ANA,COL] [--helmets]

Проверки (каждая — по обеим формам клуба):
- номера на рукавах (зоны 2, 3) и места литеры (5, 7): фон под зоной карты номеров на развёртке свитера — один цвет;
  второй цвет больше AUDIT_MIX доли — номер на полосе или на границе цветов («номер на руке ложится на полосу», OTT,
  ANA, WPG); зона вне развёртки больше AUDIT_OUT — номер режется (сдвиг зоны слишком далеко);
- номер на спине: высота против профиля (`number_h_cm`, иначе стандарт edge_kit.LETTERING_NUM_H) ± AUDIT_NUM_TOL;
  фамилия — промежуток букв против edge_kit.NAME_FIT_GAP_MIN … NAME_FIT_GAP;
- гетры: нижние строки своих гетр (flat_sock) против нижних строк перенесённых с источника — у NHL 27 низ бывает
  другого цвета («оранжевая полоска внизу гетр», ANA, COL, NSH);
- шорты pant = "source": рельеф (pant_nm слота) — только под нашими гербами (fb.pant_decals.relief_check): рельеф герба
  образца Legacy вне нашего герба не стёрт, наш герб без рельефа («лого на трусах выше и сбоку относительно рельефного
  места», DET, 23.10);
- --helmets: строка шлема NHL 27, из которой взята каска (kitport.profile.eq_pick) — общая (−1, −1) или первая era 2
  вместо своей строки формы (COL дом: чёрный вместо синего); нужна база NHL 27 (FB_GAME=nhl27 не обязателен).
Принятое пользователем или проверенное глазами — поле профиля `audit_accept` (список проверок с причиной в комментарии:
sleeve_mix, sleeve_out, letter_mix, letter_out, number, name_gap, sock, pant_relief, helmet) — не замечание
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


def check_kit(club, kit, d, src_d, tid, prof, E, lettering):
    from PIL import Image
    flags = []
    acc = set(prof.get("audit_accept", []))
    def flag(kind, text):
        flags.append(text if kind not in acc else f"(принято) {text}")
    jersey = np.asarray(Image.open(os.path.join(d, "jersey_cm.png")).convert("RGB")).astype(np.float64)
    name = np.asarray(Image.open(os.path.join(d, "name_cm.png")).convert("RGBA"))
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
    helm = helmet_flags(sorted({k.split("_")[0] for k in kits if k.split("_")[0] in profs})) if a.helmets else {}
    bad = 0
    for kit in kits:
        club, k = kit.split("_", 1)
        if club not in profs:
            continue
        E.use_club(club)
        flags = check_kit(club, k, os.path.join(src, kit), os.path.join(E.KITS_OUT, kit), tid, profs[club], E,
                          lettering)
        if (club, k) in helm:
            flags.append(helm[(club, k)] if "helmet" not in profs[club].get("audit_accept", []) else
                         "(принято) " + helm[(club, k)])
        bad += any(not f.startswith("(принято)") for f in flags)
        print(f"{kit:9s} " + ("чисто" if not flags else ("\n" + " " * 10).join(flags)))
    print(f"форм с замечаниями: {bad} из {len(kits)}")
    return 1 if bad else 0
