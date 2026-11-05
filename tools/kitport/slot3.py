"""kitport slot3 — свой слот форм NHL 27: стиль 2. Слот стиля 0 снова отдаётся оригиналам EA (docs/kitport.md §1.1).

Формы NHL 27 стоят на своей сетке (изогнутая копия Edge с островом развёртки). С 15.10 эта сетка лежала в слоте стиля 0,
и 188 форм EA (сборные, Европа, ретро клубов НХЛ) рисовались на ней с поехавшим рисунком. Вариант A (пользователь, 02.11.2026):
свой номер стиля. Поле style шириной 1 бит только в заголовке таблицы базы, игра читает его как число и подставляет в имена
файлов (разбор — §1.1), поэтому exe не меняется.

Перевод — преобразование того, что стоит сейчас: файлов cache:, базы и новейшего ROSTER. Формы не пересобираются: те же файлы
под новыми именами, в них меняется только цифра стиля в именах растров. Повтор ничего не меняет.

    python -m kitport slot3 status                    # что где стоит: реестр, сборка, cache:, база, ROSTER
    python -m kitport slot3 prepare                   # сборка: слот форм и пак pack-edge-s2 (игру и накладку не трогает)
    python -m kitport slot3 install [--roster ФАЙЛ] [--tag slot3] [--yes] [--no-pipeline]
                                                      # игра закрыта: копия в backup-cache, cache:, база, схема, ROSTER, затем
                                                      # реестр, пак, накладка out-nhl24
    python -m kitport slot3 verify [--before ПАПКА] [--launcher EXE]   # сверка с копией до перевода: файлы, база, экипировка, ROSTER
    python -m kitport slot3 rollback [ПАПКА] [--yes] [--no-pipeline]   # всё обратно

Запуск из tools/ venv-ом game/work/nhl24/venv. Проверка на копии: CACHE=<копия>/cache/guest LEGACY_DATA_STATE=<папка> (там
installed.txt, install-flags.txt, backup-cache, backup-saves) и --no-pipeline; NHL24_REGISTRY=<файл> — другой реестр.
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time

from . import core

STYLE = 2                        # номер слота, как edge_kit.SLOT_STYLE и nhl24.STYLE_EDGE (проверяется в install)
TAG = "slot3"
PACK_NEW = os.path.join(core.PACKS, "pack-edge-s2")
PACK = os.path.join(core.PACKS, "pack-edge")
MESH = re.compile(r"jersey_([01])_0_(\d_\d_\d_\d)\.rx2")
SAVE_DIR = re.compile(r"ROSTER \d{14}A?")


def say(*a):
    print(*a, flush=True)


def nhl24():
    for p in (core.TOOLS, os.path.join(core.TOOLS, "legacy_data")):
        if p not in sys.path:
            sys.path.insert(0, p)
    import nhl24 as L
    return L


def tdb():
    if core.TOOLS not in sys.path:
        sys.path.insert(0, core.TOOLS)
    import tdb as T
    return T


def md5(path):
    return hashlib.md5(open(path, "rb").read()).hexdigest()


def pj(root, rel):
    """root/rel; если root — папка content (exe 0.17.0+), то content/<часть>/rel (tools/legacy_paths.py)."""
    return core.cache_file(root, rel)


# ---------------------------------------------------------------- что куда переезжает

def edge_kits(reg=None):
    L = nhl24()
    return [k for k in (reg or L.load_registry())["kits"] if k["kit"] in L.EDGE_KITS]


def kit_moves(k):
    """Файлы формы: (было, стало, что менять в именах растров, на что, сколько имён). У превью имён нет."""
    a, v, f = k["art"], k["variant"], k["fevariant"]
    o, n = f"0_{a}_{v}", f"{STYLE}_{a}_{v}"
    tag = (f"_{o}_", f"_{n}_")
    return [(f"rendering/jersey/texlib_{o}.rx2", f"rendering/jersey/texlib_{n}.rx2", *tag, 6),
            (f"rendering/jersey/name_{o}_cm.rx2", f"rendering/jersey/name_{n}_cm.rx2", *tag, 1),
            (f"rendering/pant/texlib_{o}.rx2", f"rendering/pant/texlib_{n}.rx2", *tag, 3),
            (f"rendering/sock/sock_{o}_cm.rx2", f"rendering/sock/sock_{n}_cm.rx2", *tag, 1),
            (f"rendering/logo/texlib_{a}_0_{v}.rx2", f"rendering/logo/texlib_{a}_{STYLE}_{v}.rx2",
             f"logo_{a}_0_{v}_", f"logo_{a}_{STYLE}_{v}_", 3),
            (f"fe/ion/artassets/jerseys/jersey_0_{a}_{f}.big", f"fe/ion/artassets/jerseys/jersey_{STYLE}_{a}_{f}.big", None, None, 0)]


def shared_moves(root):
    """Общие файлы, что сейчас под именами стиля 0: сетки свитера, его затенение, карты гетр."""
    jd = pj(root, "rendering/jersey")
    out = [(f"rendering/jersey/{n}", f"rendering/jersey/jersey_{MESH.fullmatch(n).group(1)}_{STYLE}_{MESH.fullmatch(n).group(2)}.rx2",
            None, None, 0) for n in sorted(os.listdir(jd)) if MESH.fullmatch(n)] if os.path.isdir(jd) else []
    out.append(("rendering/jersey/texlib_0_999.rx2", f"rendering/jersey/texlib_{STYLE}_999.rx2", "jersey_0_", f"jersey_{STYLE}_", 5))
    out += [(f"rendering/sock/sock_0_{m}.rx2", f"rendering/sock/sock_{STYLE}_{m}.rx2", f"sock_0_{m}", f"sock_{STYLE}_{m}", 1)
            for m in ("nm", "rm", "sm")]
    return out


def renamed(data, a, b, want, what):
    """Имена растров лежат в заголовке RW4 (до 0x1000), той же длины; тело файла не меняется."""
    if a is None:
        return data
    head = data[:0x1000]
    n = head.count(a.encode())
    if n != want or len(a) != len(b):
        sys.exit(f"{what}: имён «{a}» в заголовке {n}, ждал {want}")
    return head.replace(a.encode(), b.encode()) + data[0x1000:]


def pant_ao():
    """Затенение шорт стиля 2: файл диска EA, имена растров стиля 2. Формы NHL 27 всегда брали затенение стиля 0."""
    import kitpaint as kp
    data = kp.source("rendering/pant/texlib_0_999.rx2", "legacy")
    return f"rendering/pant/texlib_{STYLE}_999.rx2", renamed(data, "pant_0_", f"pant_{STYLE}_", 5, "texlib_0_999 шорт")


def pending(root, moves):
    """Переезды, которых ещё не было. Нет ни старого, ни нового файла — стоп: это не та папка."""
    todo = []
    for m in moves:
        s, d = pj(root, m[0]), pj(root, m[1])
        if os.path.exists(s):
            todo.append(m)
        elif not os.path.exists(d):
            sys.exit(f"нет ни {m[0]}, ни {m[1]} в {root}")
    return todo


def move_files(root, todo):
    for src, dst, a, b, want in todo:
        p = pj(root, dst)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        data = renamed(open(pj(root, src), "rb").read(), a, b, want, src)
        with open(p + ".part", "wb") as f:
            f.write(data)
        os.replace(p + ".part", p)
        os.remove(pj(root, src))


# ---------------------------------------------------------------- сейвы, база

def rosters(cache):
    """Файлы ROSTER: от старых к новым, имя сейва — время записи. cache — userdata/cache/guest; сейвы — в saves рядом
    с userdata (0.17.0+) или в userdata/<xuid>/454109EC/00000001 (tools/legacy_saves.py)."""
    if core.TOOLS not in sys.path:
        sys.path.insert(0, core.TOOLS)
    from legacy_saves import Saves
    s = Saves.of_userdata(os.path.dirname(os.path.dirname(os.path.abspath(cache))))
    refs = [r for r in s.list("ROSTER") if SAVE_DIR.fullmatch(r.name)]
    if not refs:
        sys.exit(f"нет сейвов ROSTER в {s.where()}")
    return [r.file for r in refs]


def open_base(cache=None):
    T = tdb()
    d = os.path.join(cache or core.cache_dir(), "db")
    meta = T.load_meta(os.path.join(d, "nhlng-meta.xml"))
    return T.Tdb(open(os.path.join(d, "nhlng.db"), "rb").read(), meta), meta


def write_atomic(path, data, mode="wb", **kw):
    with open(path + ".part", mode, **kw) as f:
        f.write(data)
    os.replace(path + ".part", path)


def count_styles(db):
    L = nhl24()
    c = {}
    for r in db.live_rows(L.T):
        s = db.get(L.T, "style", r)
        c[s] = c.get(s, 0) + 1
    return dict(sorted(c.items()))


# ---------------------------------------------------------------- status

def cmd_status(a):
    L = nhl24()
    cache = core.cache_dir()
    reg = L.load_registry()
    kits = edge_kits(reg)
    say("реестр:", L.REGISTRY, "формы NHL 27 на стиле:", sorted({k.get("style", 1) for k in kits}), f"({len(kits)} форм)")
    sc = os.path.join(core.EDGE_WORK, "slot", "cache")
    mv = [m for k in kits for m in kit_moves(k)]
    for name, root in (("слот форм (edgekit/slot/cache)", sc), ("cache: игры", cache)):
        have0 = sum(os.path.exists(pj(root, m[0])) for m in mv)
        have2 = sum(os.path.exists(pj(root, m[1])) for m in mv)
        say(f"{name}: файлов форм под стилем 0 — {have0}, под стилем {STYLE} — {have2} из {len(mv)}")
    jd = pj(cache, "rendering/jersey")
    say("cache: сетки стиля 0:", sum(bool(MESH.fullmatch(n)) for n in os.listdir(jd)), f"стиля {STYLE}:",
        sum(bool(re.fullmatch(rf"jersey_[01]_{STYLE}_\d_\d_\d_\d\.rx2", n)) for n in os.listdir(jd)))
    say("пак pack-edge-s2:", "готов" if os.path.exists(os.path.join(PACK_NEW, "manifest.json")) else "нет (slot3 prepare)")
    db, _ = open_base(cache)
    say(f"база: поле style {db.by_name[L.T]['fields']['style']}, строки {count_styles(db)}, экипировка {db.counts(L.EQ)[:2]}")
    T = tdb()
    meta = T.load_meta(pj(cache, "db/nhlng-meta.xml"))
    for p in rosters(cache)[-1:]:
        sv = T.SaveFile(open(p, "rb").read(), meta).db
        say(f"новейший ROSTER {os.path.basename(p)}: поле style {sv.by_name[L.T]['fields']['style']}, строки {count_styles(sv)}, "
            f"места форм {sv.counts(L.T)[:2]}, экипировки {sv.counts(L.EQ)[:2]}")
    return 0


# ---------------------------------------------------------------- prepare: сборка

def build_pack(force=False):
    """Пак стиля 2 рядом с прежним: игра и накладка не меняются. Формы — файлы слота под новыми именами."""
    if os.path.exists(os.path.join(PACK_NEW, "manifest.json")) and not force:
        say("пак уже собран:", PACK_NEW)
        return 0
    if os.path.isdir(PACK_NEW):
        if any(os.path.islink(os.path.join(dp, n)) for dp, ds, fs in os.walk(PACK_NEW) for n in ds + fs):
            sys.exit(f"в {PACK_NEW} есть ссылки — разберитесь вручную")
        shutil.rmtree(PACK_NEW)
    r = subprocess.run([sys.executable, "-m", "fb.edge_kit", "pack", "--out", PACK_NEW], cwd=core.TOOLS,
                       env=dict(os.environ, PYTHONIOENCODING="utf-8"), capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    for ln in r.stdout.splitlines()[-4:]:
        say("  " + ln[:190])
    if r.returncode:
        say(r.stderr[-800:])
        sys.exit("edge_kit pack: ошибка")
    return 0


def check_pack():
    """Пак стиля 2 против прежнего pack-edge: тот же состав, кроме слота; файлы те же, кроме цифры стиля в именах. → ошибки."""
    old = json.load(open(os.path.join(PACK, "manifest.json"), encoding="utf-8"))
    new = json.load(open(os.path.join(PACK_NEW, "manifest.json"), encoding="utf-8"))
    of, nf = {e["file"]: e for e in old["files"]}, {e["file"]: e for e in new["files"]}
    moves = {m[0]: m for k in edge_kits() for m in kit_moves(k)}
    moves.update({m[0]: m for m in shared_moves(pj(PACK, "cache"))})
    bad, same, moved, gone = [], 0, 0, []
    for rel, e in of.items():
        m = moves.get(rel)
        if m is None:
            if rel not in nf or nf[rel]["md5"] != e["md5"]:
                bad.append(f"{rel}: не как в прежнем паке")
            else:
                same += 1
            continue
        if m[1] not in nf:
            bad.append(f"{m[1]}: нет в новом паке")
            continue
        data = renamed(open(pj(pj(PACK, "cache"), rel), "rb").read(), m[2], m[3], m[4], rel)
        if data != open(pj(pj(PACK_NEW, "cache"), m[1]), "rb").read():
            bad.append(f"{m[1]}: не тот файл")
        else:
            moved += 1
    left = set(nf) - set(of) - {m[1] for m in moves.values()}
    extra = sorted(left)
    if rel_bad := [x for x in nf if x in moves]:
        bad.append(f"в новом паке остались файлы стиля 0: {rel_bad[:3]}")
    say(f"пак: без изменений {same}, под новыми именами {moved}, новых {len(extra)}: {extra[:4]}")
    return bad


def cmd_prepare(a):
    """Слот форм edgekit/slot/cache → стиль 2 (файлы те же, файлы сборки игре не видны), пак pack-edge-s2 рядом с прежним."""
    if all(k.get("style") == STYLE for k in edge_kits()):
        say(f"реестр уже на стиле {STYLE}: перевод установлен, готовить нечего")
        return 0
    root = os.path.join(core.EDGE_WORK, "slot", "cache")
    sys.path.insert(0, core.TOOLS)
    todo = pending(root, [m for k in edge_kits() for m in kit_moves(k)]) + \
        [m for m in shared_moves(root) if os.path.exists(pj(root, m[0]))]
    move_files(root, todo)
    say(f"слот форм: переименовано файлов {len(todo)}")
    from fb import edge_kit
    say("карты гетр и затенение шорт:", edge_kit.shared_for_slot(root))
    build_pack(a.force)
    bad = check_pack()
    for b in bad[:12]:
        say("  ", b)
    say("сверка пака:", "ошибок нет" if not bad else f"ошибок {len(bad)}")
    return 1 if bad else 0


# ---------------------------------------------------------------- install

def switch_pipeline(on, old_pack=None):
    """Реестр, пак и накладка: on — стиль 2, иначе — как до перевода (old_pack — прежний пак из манифеста копии). Накладка
    собирается из нынешних out и out-ahl32. → (код сборки, имя прежнего пака)."""
    L = nhl24()
    reg = L.load_registry()
    for k in edge_kits(reg):
        k["style"] = STYLE if on else 0
    L.save_registry(reg)
    say("реестр:", L.REGISTRY, f"формы NHL 27 на стиле {STYLE if on else 0}")
    if on:
        if not os.path.exists(os.path.join(PACK_NEW, "manifest.json")):
            sys.exit("нет пака стиля 2: python -m kitport slot3 prepare")
        old_pack = os.path.basename(core.next_pack_version())
        os.rename(PACK, os.path.join(core.PACKS, old_pack))
        os.rename(PACK_NEW, PACK)
        say(f"пак стиля 2 → pack-edge, прежний → {old_pack}")
    else:
        old = sorted((n for n in os.listdir(core.PACKS) if re.fullmatch(r"pack-edge-v\d+", n)),
                     key=lambda n: int(n.rsplit("v", 1)[1]))
        old_pack = old_pack if old_pack in old else (old[-1] if old else None)
        if not old_pack:
            sys.exit("нет прежнего пака pack-edge-vN: верните его вручную")
        os.rename(PACK, PACK_NEW)
        os.rename(os.path.join(core.PACKS, old_pack), PACK)
        say(f"прежний пак {old_pack} → pack-edge, пак стиля 2 → pack-edge-s2")
    bash = shutil.which("bash")
    r = subprocess.run([bash, "tools/legacy_data/build-all.sh", "nhl24"], cwd=core.REPO,
                       env=dict(os.environ, NHL24_PACK="game/work/nhl24/out/pack-edge", PYTHONIOENCODING="utf-8"),
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    say("накладка:", (r.stdout.splitlines() or [""])[-1][:160])
    return r.returncode, old_pack


def cmd_install(a):
    L = nhl24()
    from fb import edge_kit
    if not STYLE == L.STYLE_EDGE == edge_kit.SLOT_STYLE:
        sys.exit("номера слота разошлись: kitport.slot3.STYLE, nhl24.STYLE_EDGE, edge_kit.SLOT_STYLE")
    cache = core.cache_dir()
    if core.game_blocks_cache():
        sys.exit("NHL Legacy запущена с этим cache: — закройте игру")
    reg = L.load_registry()
    keys = L.edge_keys(reg)
    if a.roster:
        roster = os.path.abspath(a.roster)
    else:
        all_r = rosters(cache)
        if not all_r:
            sys.exit("нет сейва ROSTER: укажите --roster")
        roster = all_r[-1]
    if not os.path.isfile(roster):
        sys.exit(f"нет файла {roster}")
    db, meta = open_base(cache)
    pant_rel, pant_data = pant_ao()
    if L.style_width(db) >= L.STYLE_BITS:         # база пишется последней: переведена — значит, переведён и cache: (в слоте
        #                                           стиля 0 снова лежат сетки ретро, второй раз их трогать нельзя)
        say(f"cache: уже на стиле {STYLE}: {cache}\nROSTER: {roster}")     # повтор и новый ROSTER поверх переведённой игры
        L.sync_save(roster, db, meta, True)
        if not a.no_pipeline and any(k.get("style") != STYLE for k in edge_kits()):
            return switch_pipeline(True)[0]
        return 0
    moves = pending(cache, [m for k in edge_kits(reg) for m in kit_moves(k)]) + \
        [m for m in shared_moves(cache) if os.path.exists(pj(cache, m[0]))]
    m_ins = core.installer()
    fl = core.install_flags()
    base = m_ins.sources("--ahl32" in fl, False)           # что в cache: без накладки: сетки ретро с краем спины — из out
    back_to_base = [m[0] for m in moves if m[0] in base and m[0] not in {x[1] for x in moves}]
    say(f"cache: {cache}")
    say(f"файлов под новыми именами: {len(moves)}; база: поле style {db.by_name[L.T]['fields']['style']}, строки {count_styles(db)}")
    say(f"сетки ретро из legacy-data/out: {len(back_to_base)}; остальное стиля 0 — с диска EA")
    say(f"ROSTER: {roster}")
    if not a.yes:
        try:
            if input("перевести? [y/N] ").strip().lower() not in ("y", "yes", "д", "да"):
                say("отменено")
                return 1
        except EOFError:
            return 1
    changes = [("GONE", m[0], None) for m in moves] + [("NEW", m[1], None) for m in moves]
    if not os.path.exists(pj(cache, pant_rel)):
        changes.append(("NEW", pant_rel, None))
    changes += [("CHANGED", "db/nhlng.db", None), ("CHANGED", "db/nhlng-meta.xml", None)]
    bdir, man = core.backup(changes, a.tag)
    say(f"копия заменяемого: {len(man['changed'])} файлов, новых {len(man['new'])} → {bdir}")
    man_path = os.path.join(bdir, "manifest.json")
    bak = None
    try:
        move_files(cache, moves)
        p = pj(cache, pant_rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        write_atomic(p, pant_data)
        for rel in back_to_base:
            shutil.copy2(base[rel], pj(cache, rel))
        n, eq = L.style2_apply(db, keys)
        db.fix()
        if db.verify():
            sys.exit("база: CRC не сошлись")
        write_atomic(pj(cache, "db/nhlng.db"), bytes(db.d))
        mp = pj(cache, "db/nhlng-meta.xml")
        write_atomic(mp, L.style_meta(open(mp, encoding="utf-8", newline="").read()), "w", encoding="utf-8", newline="")
        say(f"база: форм на стиле {STYLE}: {n}, строк экипировки добавлено: {eq}")
        db2, meta2 = open_base(cache)
        was = open(roster, "rb").read()
        bak = L.sync_save(roster, db2, meta2, True)
        if bak:
            man["roster"] = {"path": roster, "bak": bak, "md5_before": hashlib.md5(was).hexdigest(), "md5_after": md5(roster)}
        items = set(m_ins.read_list(m_ins.LIST))
        items -= {m[0] for m in moves} - set(back_to_base)
        items |= {m[1] for m in moves} | {pant_rel}
        m_ins.write_list(m_ins.LIST, sorted(items))
        with open(man_path, "w", encoding="utf-8", newline="\n") as f:
            json.dump(man, f, ensure_ascii=False, indent=1)
    except BaseException:
        say("ОШИБКА, возвращаю cache: и ROSTER из копии")
        core.restore(bdir)
        if bak:
            shutil.copy2(bak, roster)
        raise
    say(f"cache: переведён; копия {os.path.basename(bdir)}")
    if not a.no_pipeline:
        rc, man["pack_old"] = switch_pipeline(True)
        with open(man_path, "w", encoding="utf-8", newline="\n") as f:
            json.dump(man, f, ensure_ascii=False, indent=1)
        if rc:
            say(f"накладка не собралась (ошибка {rc}): игра переведена, сборка — нет; повторите: bash tools/legacy_data/build-all.sh nhl24 "
                "с NHL24_PACK=game/work/nhl24/out/pack-edge")
            return rc
        left = core.diff()
        say("сборка против игры:", "совпадают" if not left else f"отличаются {len(left)} файлов: "
            + ", ".join(r for _, r, _ in left[:5]))
    say(f"дальше: python -m kitport slot3 verify; откат: python -m kitport slot3 rollback {os.path.basename(bdir)}")
    say(f"журнал (docs/nhl24-uniforms.md §15.1): {time.strftime('%d.%m %H:%M')} — формы NHL 27 на стиль 2, слот стиля 0 — оригиналы "
        f"(docs/kitport.md §1.1): файлов {len(moves)}, база {md5(pj(cache, 'db/nhlng.db'))[:8]}, ROSTER {os.path.basename(roster)}; "
        f"копия — backup-cache/{os.path.basename(bdir)}")
    return 0


# ---------------------------------------------------------------- rollback

def latest_backup():
    if os.path.isdir(core.BACKUP_CACHE):
        ds = [d for d in os.listdir(core.BACKUP_CACHE) if re.fullmatch(rf"user-\d{{8}}-{TAG}(-\d+)?", d)]
        if ds:
            return os.path.join(core.BACKUP_CACHE, max(ds, key=lambda d: os.path.getmtime(os.path.join(core.BACKUP_CACHE, d))))
    return None


def cmd_rollback(a):
    L = nhl24()
    T = tdb()
    d = (a.dir if os.path.isabs(a.dir) else os.path.join(core.BACKUP_CACHE, a.dir)) if a.dir else latest_backup()
    if not d or not os.path.isdir(d):
        sys.exit("нет копии перевода: укажите папку в backup-cache")
    if core.game_blocks_cache():
        sys.exit("NHL Legacy запущена с этим cache: — закройте игру")
    man = json.load(open(os.path.join(d, "manifest.json"), encoding="utf-8"))
    if not a.yes:
        try:
            if input(f"вернуть cache: и ROSTER из {d}? [y/N] ").strip().lower() not in ("y", "yes", "д", "да"):
                say("отменено")
                return 1
        except EOFError:
            return 1
    cache = core.cache_dir()
    back, gone = core.restore(d)
    say(f"cache: возвращено {back} файлов, убрано новых {gone}")
    r = man.get("roster")
    if r and os.path.isfile(r["path"]) and md5(r["path"]) == r["md5_after"]:
        shutil.copy2(r["bak"], r["path"])
        say("ROSTER возвращён из копии:", r["path"])
    meta = T.load_meta(pj(cache, "db/nhlng-meta.xml"))
    for p in rosters(cache):                               # сейвы, записанные уже на стиле 2, — обратно тем же кодом
        sf = T.SaveFile(open(p, "rb").read(), meta)
        if L.style_width(sf.db) >= L.STYLE_BITS:
            n, eq = L.style2_undo(sf.db)
            bdir = os.path.join(L.STATE, "backup-saves", f"{os.path.basename(p)}-{time.strftime('%Y%m%d-%H%M%S')}")
            os.makedirs(bdir, exist_ok=True)
            shutil.copy2(p, os.path.join(bdir, os.path.basename(p) + ".bak"))
            write_atomic(p, sf.bytes(fix=True))
            say(f"{os.path.basename(p)}: на стиль 0 обратно форм {n}, строк экипировки убрано {eq}")
    if not a.no_pipeline:
        return switch_pipeline(False, man.get("pack_old"))[0]
    return 0


# ---------------------------------------------------------------- verify

def field_rows(db, table, skip=()):
    fields = [f for f in sorted(db.by_name[table]["fields"]) if f not in skip]
    return [tuple(db.get(table, f, r) for f in fields) for r in db.live_rows(table)]


def equipment_same(L, old, new, keys):
    """Экипировка по модели игры: у форм keys era 2 в новой базе = era 0 в старой, у остальных форм клубов — как была."""
    low_o, low_n = L.eq_low(old), L.eq_low(new)
    bad, n = [], 0
    rows = L.rows_of(old)
    for team in sorted({k[0] for k in keys}):
        ro, rn = L.club_equipment(old, low_o, team), L.club_equipment(new, low_n, team)
        types = sorted({x[2] for x in ro})
        brands = sorted({x[3] for x in ro if x[3] != -1})
        BR = brands + [next(b for b in range(64) if b not in brands)]
        for r in (x for x in rows if x["teamid"] == team):
            edge = r["style"] == 0 and (team, r["teamartid"], r["variant"]) in keys
            for eq in types:
                for b in BR:
                    n += 1
                    a = L.eq_lookup(ro, (r["style"], r["variant"], eq, b))[5]
                    c = L.eq_lookup(rn, (STYLE if edge else r["style"], r["variant"], eq, b))[5]
                    if a != c:
                        bad.append((team, r["style"], r["variant"], eq, b))
    return n, bad


def cmd_verify(a):
    L = nhl24()
    T = tdb()
    d = (a.before if not a.before or os.path.isabs(a.before) else os.path.join(core.BACKUP_CACHE, a.before)) or latest_backup()
    if not d or not os.path.isdir(d):
        sys.exit("нет копии перевода: укажите --before")
    man = json.load(open(os.path.join(d, "manifest.json"), encoding="utf-8"))
    cache = core.cache_dir()
    fails = []

    def check(ok, text):
        say(("  ok   " if ok else "  НЕТ  ") + text)
        if not ok:
            fails.append(text)
    say(f"копия до перевода: {d}\ncache: {cache}")
    reg = L.load_registry()
    keys = L.edge_keys(reg)
    # файлы форм
    same = diff = 0
    for k in edge_kits(reg):
        for src, dst, x, y, want in kit_moves(k):
            if renamed(open(pj(d, src), "rb").read(), x, y, want, src) == open(pj(cache, dst), "rb").read():
                same += 1
            else:
                diff += 1
            if os.path.exists(pj(cache, src)):
                diff += 1
    check(not diff, f"файлы форм NHL 27: {same} совпали с прежними (разница только в цифре стиля в именах растров), отличий {diff}")
    # общие файлы
    shared_ok = shared_bad = 0
    bk_moves = [(m[0], m[1], m[2], m[3], m[4]) for m in shared_moves(d) if os.path.exists(pj(d, m[0]))]
    for src, dst, x, y, want in bk_moves:
        if renamed(open(pj(d, src), "rb").read(), x, y, want, src) == open(pj(cache, dst), "rb").read():
            shared_ok += 1
        else:
            shared_bad += 1
    check(not shared_bad and shared_ok == 34, f"сетки, AO и карты гетр стиля {STYLE} = прежние файлы слота: {shared_ok} из 34")
    fl = core.install_flags()
    base = core.installer().sources("--ahl32" in fl, False)
    left = [m[0] for m in bk_moves if os.path.exists(pj(cache, m[0])) and
            not (m[0] in base and md5(base[m[0]]) == md5(pj(cache, m[0])))]
    disc = sum(not os.path.exists(pj(cache, m[0])) for m in bk_moves)
    check(not left, f"слот стиля 0: чужих файлов {len(left)}; из legacy-data/out {len(bk_moves) - disc - len(left)}, с диска EA {disc}")
    # база
    db, meta = open_base(cache)
    old_meta = T.load_meta(pj(d, "db/nhlng-meta.xml"))
    old = T.Tdb(open(pj(d, "db/nhlng.db"), "rb").read(), old_meta)
    check(db.by_name[L.T]["fields"]["style"][1] == L.STYLE_BITS and not db.verify(), f"база: поле style {db.by_name[L.T]['fields']['style']}, CRC верны")
    styles = count_styles(db)
    check(styles.get(STYLE, 0) == len(keys), f"база: строки по стилям {styles}")
    other = [t["name"] for t in db.tables if t["name"] not in (L.T, L.EQ) and L.table_bytes(old, t["name"]) != L.table_bytes(db, t["name"])]
    check(not other, f"база: остальные {len(db.tables) - 2} таблиц байт в байт ({other[:3]})")
    check(field_rows(old, L.T, ("style",)) == field_rows(db, L.T, ("style",)), "база: строки форм те же, кроме стиля")
    eq_old, eq_new = [bytes(old.record(L.EQ, r)) for r in old.live_rows(L.EQ)], [bytes(db.record(L.EQ, r)) for r in db.live_rows(L.EQ)]
    check(eq_new[:len(eq_old)] == eq_old, f"база: экипировка {len(eq_old)} строк прежние, добавлено {len(eq_new) - len(eq_old)}")
    n, bad = equipment_same(L, old, db, keys)
    check(not bad, f"экипировка по модели игры: {n} сочетаний форма, тип, бренд, расхождений {len(bad)} {bad[:3]}")
    removed = {f"{L.CLUBS[c][0]}:{i}" for c, ids in L.load_removed().items() for i in ids}
    back = [r for r in L.rows_of(db) if f"{r['teamid']}:{r['style']}_{r['teamartid']}_{r['variant']}" in removed]
    check(not back, f"формы kit_removed.json в базе: {len(back)} из {len(removed)}")
    # ROSTER
    r = man.get("roster")
    p = os.path.abspath(a.roster) if a.roster else (r or {}).get("path") or rosters(cache)[-1]
    sf = T.SaveFile(open(p, "rb").read(), meta)
    sv = sf.db
    say(f"ROSTER: {p}")
    check(not sf.verify(), "сейв: CRC и обёртка верны")
    for t in (L.T, L.EQ):
        check(sv.by_name[t]["fields"] == db.by_name[t]["fields"] and sv.by_name[t]["reclen"] == db.by_name[t]["reclen"]
              and [bytes(sv.record(t, x)) for x in sv.live_rows(t)] == [bytes(db.record(t, x)) for x in db.live_rows(t)],
              f"сейв = база запись в запись: {t}, места {sv.counts(t)[:2]}")
    cur = len(list(db.live_rows(L.T)))
    check(sv.counts(L.T)[0] == (L.KIT_MAX_MIN if cur <= L.KIT_MAX_MIN else cur + L.KIT_INSERT), f"места таблицы форм по правилу: {sv.counts(L.T)[0]}")
    neq = len(list(db.live_rows(L.EQ)))
    check(sv.counts(L.EQ)[0] == max(6000, neq), f"места экипировки по правилу (6000 или строки): {sv.counts(L.EQ)[0]} при {neq} строках")
    if r:
        bak = T.SaveFile(open(r["bak"], "rb").read(), old_meta).db
        o2 = [t["name"] for t in sv.tables if t["name"] not in (L.T, L.EQ) and L.table_bytes(bak, t["name"]) != L.table_bytes(sv, t["name"])]
        check(not o2, f"сейв: остальные {len(sv.tables) - 2} таблиц как до перевода ({o2[:3]})")
    if a.launcher:
        x = subprocess.run([a.launcher, "--check-roster", p], capture_output=True, text=True, errors="replace")
        check(x.returncode == 0, f"лаунчер --check-roster: код {x.returncode} {x.stdout.strip()[:120]}")
    say("итог:", "всё сошлось" if not fails else f"расхождений {len(fails)}")
    return 1 if fails else 0


# ---------------------------------------------------------------- argparse

def add_parser(sub):
    p = sub.add_parser("slot3", help="формы NHL 27 на стиль 2, слот стиля 0 — оригиналы EA: перевод, сверка, откат",
                       description=__doc__, formatter_class=__import__("argparse").RawDescriptionHelpFormatter)
    s3 = p.add_subparsers(dest="slot3_cmd", required=True)
    s = s3.add_parser("status", help="что где стоит")
    s.set_defaults(slot3_func=cmd_status)
    s = s3.add_parser("prepare", help="сборка: слот форм и пак pack-edge-s2; игру и накладку не трогает")
    s.add_argument("--force", action="store_true", help="собрать пак заново")
    s.set_defaults(slot3_func=cmd_prepare)
    s = s3.add_parser("install", help="перевод поставленной игры и новейшего ROSTER, затем реестр, пак и накладка")
    s.add_argument("--roster", default=None, help="файл ROSTER (по умолчанию — новейший)")
    s.add_argument("--tag", default=TAG, help="метка копии в backup-cache")
    s.add_argument("--yes", action="store_true")
    s.add_argument("--no-pipeline", action="store_true", help="только игра: реестр, пак и накладка остаются (проверка на копии)")
    s.set_defaults(slot3_func=cmd_install)
    s = s3.add_parser("verify", help="сверка с копией до перевода: файлы, база, экипировка, ROSTER")
    s.add_argument("--before", default=None, help="папка копии в backup-cache (по умолчанию — последняя с меткой slot3)")
    s.add_argument("--roster", default=None, help="файл ROSTER (по умолчанию — переведённый)")
    s.add_argument("--launcher", default=None, help="nhllegacy_launcher.exe: ещё и --check-roster")
    s.set_defaults(slot3_func=cmd_verify)
    s = s3.add_parser("rollback", help="вернуть cache:, базу и ROSTER; сейвы, записанные на стиле 2, — обратно тем же кодом")
    s.add_argument("dir", nargs="?", default=None, help="папка копии в backup-cache (по умолчанию — последняя с меткой slot3)")
    s.add_argument("--yes", action="store_true")
    s.add_argument("--no-pipeline", action="store_true", help="реестр, пак и накладку не трогать")
    s.set_defaults(slot3_func=cmd_rollback)
