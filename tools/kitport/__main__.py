"""CLI kitport (python -m kitport …, из папки tools/). Команды и порядок — docstring пакета и docs/kitport.md."""
import argparse
import datetime
import os
import re
import shutil
import subprocess
import sys

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    __package__ = "kitport"

from . import core  # noqa: E402


def say(*a):
    print(*a, flush=True)


# ---------------------------------------------------------------- doctor

def cmd_doctor(a):
    ok = True

    def check(cond, what, hint=""):
        nonlocal ok
        say(("  ok   " if cond else "  НЕТ  ") + what + ("" if cond or not hint else f" — {hint}"))
        ok = ok and bool(cond)
    say("python:", sys.executable, sys.version.split()[0])
    check(os.path.normcase(sys.executable) == os.path.normcase(core.VENV_PY) or not os.path.exists(core.VENV_PY),
          "запущен venv-ом game/work/nhl24/venv", f"запускайте {core.VENV_PY} -m kitport …")
    for mod in ("numpy", "scipy", "PIL"):
        try:
            __import__(mod)
            check(True, f"пакет {mod}")
        except ImportError:
            check(False, f"пакет {mod}", "pip install в venv")
    check(shutil.which("bash") is not None, "bash в PATH (стадия overlay — build-all.sh)", "Git Bash")
    for p, what in ((core.NHL24_WORK, "рабочая папка NHL 24"), (core.EDGE_WORK, "рабочая папка fb.edge_kit"),
                    (core.LEGACY_DATA, "сборка модов-данных legacy-data")):
        check(os.path.isdir(p), f"{what}: {p}")
    try:
        from fb import pilot
        check(os.path.isdir(pilot.LEG), f"распакованные формы Legacy (fb.pilot.LEG): {pilot.LEG}",
              "fb.pilot распакует при первой сборке")
    except Exception as e:                                              # noqa: BLE001
        check(False, f"импорт fb.pilot: {e}")
    try:
        from fb import kit3d
        check(kit3d.find_res(kit3d.NHL24_JERSEY) is not None, "сетка свитера NHL 24 в распаковке",
              "fb.extract / fb.scan — docs/nhl24-textures.md")
    except Exception as e:                                              # noqa: BLE001
        check(False, f"сетка свитера NHL 24: {e}")
    try:
        from fb import edge_kit
        if getattr(edge_kit, "BRAND_TEXT", None):
            check(os.path.exists(edge_kit.BRAND_FONT), f"шрифт надписи сзади: {edge_kit.BRAND_FONT}")
    except Exception as e:                                              # noqa: BLE001
        check(False, f"импорт fb.edge_kit: {e}")
    try:
        cache = core.cache_dir()
        check(os.path.isdir(cache), f"cache: игры {cache}")
        check(bool(core.install_flags()), f"флаги последней установки: {' '.join(core.install_flags()) or '—'}")
        say("  игра:", "ЗАПУЩЕНА с этим cache: — ставить нельзя" if core.game_blocks_cache() else "не мешает")
    except SystemExit as e:
        check(False, f"cache: игры — {e}")
    try:
        br = subprocess.run(["git", "branch", "--show-current"], cwd=core.REPO, capture_output=True, text=True).stdout
        dirty = subprocess.run(["git", "status", "--short"], cwd=core.REPO, capture_output=True, text=True).stdout
        say(f"  git: ветка {br.strip()}, изменённых файлов {len([x for x in dirty.splitlines() if x.strip()])}")
    except OSError:
        pass
    say("итог:", "всё на месте" if ok else "есть недостающее (см. «НЕТ»)")
    return 0 if ok else 1


# ---------------------------------------------------------------- status

def journal_tail(n=5):
    if not os.path.exists(core.JOURNAL_DOC):
        return []
    lines = open(core.JOURNAL_DOC, encoding="utf-8").read().splitlines()
    return [ln for ln in lines if re.match(r"- \d\d\.\d\d \d\d:\d\d — ", ln)][-n:]


def cmd_status(a):
    say("cache:", core.cache_dir())
    say("флаги установки:", " ".join(core.install_flags()) or "—")
    say("игра:", "запущена с этим cache:" if core.game_blocks_cache() else "не мешает")
    d = core.diff()
    by = {}
    for kind, rel, _ in d:
        top = "/".join(rel.split("/")[:2])
        by.setdefault(top, [0, 0])[0 if kind == "CHANGED" else 1] += 1
    say(f"сборка против игры: {len(d)} файлов отличаются" + ("" if d else " (стоит то же, что собрано)"))
    for top, (c, n) in sorted(by.items()):
        say(f"  {top}: изменено {c}, новых {n}")
    pe = os.path.join(core.PACKS, "pack-edge")
    if os.path.isdir(pe):
        say("пак формы Edge:", pe, datetime.datetime.fromtimestamp(os.path.getmtime(pe)).strftime("%d.%m %H:%M"))
    vs = sorted((f for f in os.listdir(core.PACKS) if re.match(r"pack-edge-v\d+$", f)),
                key=lambda f: int(f.rsplit("v", 1)[1])) if os.path.isdir(core.PACKS) else []
    if vs:
        say(f"  прежние: {len(vs)} ({vs[0]} … {vs[-1]})")
    if os.path.isdir(core.BACKUP_CACHE):
        bs = sorted(os.listdir(core.BACKUP_CACHE), key=lambda f: os.path.getmtime(os.path.join(core.BACKUP_CACHE, f)))
        say("копии заменённого (последние):", ", ".join(bs[-3:]))
    sk = core.slot_kits_dir()
    if os.path.isdir(sk):
        for k in sorted(os.listdir(sk)):
            t = os.path.getmtime(os.path.join(sk, k))
            say(f"  слот: {k} — собран {datetime.datetime.fromtimestamp(t).strftime('%d.%m %H:%M')}")
    snap = core.latest_snapshot()
    say("последний снимок «было»:", snap or "—")
    j = journal_tail()
    if j:
        say("журнал установок (docs/nhl24-uniforms.md §15.1), последние:")
        for ln in j:
            say("  " + (ln if len(ln) < 160 else ln[:157] + "…"))
    return 0


# ---------------------------------------------------------------- snapshot / diff

def cmd_snapshot(a):
    d, n = core.snapshot(a.tag)
    say(f"снимок: {n} файлов → {d}")
    return 0


def cmd_compare(a):
    d = a.before or core.latest_snapshot()
    if not d or not os.path.isdir(d):
        say("нет снимка «было» — сначала python -m kitport snapshot")
        return 1
    rows, out = core.compare(d, clubs=a.clubs.split(",") if a.clubs else None, th=a.th)
    for kit, f, r in rows:
        say(f"{kit:10} {f:14} {r}")
    say(f"изменено текстур: {sum(1 for *_, r in rows if r.startswith('изменено'))} из {len(rows)}; "
        f"картинки «было | стало | разница ×4» → {out}")
    return 0


def cmd_diff(a):
    d = core.diff(prefix=a.prefix)
    for kind, rel, p in d:
        say(f"{kind:8} {rel}   ← {os.path.relpath(p, core.LEGACY_DATA)}")
    say(f"{len(d)} файлов отличаются от cache: игры" + (f" (с префиксом {a.prefix})" if a.prefix else ""))
    return 0


# ---------------------------------------------------------------- build

STAGES = ("kit", "slot", "pack", "overlay")


def run_stage(name, cmd, cwd, env=None):
    logs = os.path.join(core.EDGE_WORK, "logs")
    os.makedirs(logs, exist_ok=True)
    log = os.path.join(logs, datetime.datetime.now().strftime("%Y%m%d-%H%M%S") + f"-{name}.log")
    say(f"== {datetime.datetime.now():%H:%M:%S} {name}: {' '.join(cmd)}  (лог: {log})")
    with open(log, "w", encoding="utf-8") as f:
        r = subprocess.run(cmd, cwd=cwd, env=dict(os.environ, PYTHONIOENCODING="utf-8", **(env or {})),
                           stdout=f, stderr=subprocess.STDOUT)
    tail = open(log, encoding="utf-8", errors="replace").read().splitlines()[-6:]
    for ln in tail:
        say("   " + ln[:200])
    if r.returncode:
        say(f"   стадия {name}: ошибка {r.returncode} — полный лог {log}")
    return r.returncode


def cmd_build(a):
    stages = [s for s in a.stages.split(",") if s]
    bad = [s for s in stages if s not in STAGES]
    if bad:
        sys.exit(f"нет стадий {bad}; есть {STAGES}")
    kits = [k for k in a.kits.split(",") if k]
    if "away" in kits and "home" in kits and kits.index("away") > kits.index("home"):
        kits.remove("away")                                    # кокетку домашней пишет сборка выездной
        kits.insert(kits.index("home"), "away")
        say("порядок форм: выезд раньше дома (форму кокетки дома пишет сборка выезда)")
    py = sys.executable
    if a.meshes and run_stage("meshes", [py, "-m", "fb.edge_kit", "meshes"], core.TOOLS):
        return 1
    if "kit" in stages and run_stage("kit", [py, "-m", "fb.edge_kit", "kit", "--club", a.club,
                                             "--kits", ",".join(kits)], core.TOOLS):
        return 1
    if "slot" in stages and run_stage("slot", [py, "-m", "fb.edge_kit", "slot", "--club", a.club], core.TOOLS):
        return 1
    if "pack" in stages:
        pe = os.path.join(core.PACKS, "pack-edge")
        if os.path.isdir(pe):
            old = core.next_pack_version()
            os.rename(pe, old)
            say(f"прежний пак → {os.path.basename(old)}")
            sys.path.insert(0, core.TOOLS)
            import recycle                    # хранить 3 прежних пака, остальное — в Корзину (23.10: копилось 20 ГБ)
            recycle.prune(core.PACKS, r"(pack-edge)-v(\d+)", say=say)
        if run_stage("pack", [py, "-m", "fb.edge_kit", "pack", "--club", a.club], core.TOOLS):
            return 1
    if "overlay" in stages:
        bash = shutil.which("bash")
        if not bash:
            sys.exit("нет bash (Git Bash) — стадия overlay: NHL24_PACK=… bash tools/legacy_data/build-all.sh nhl24")
        if run_stage("overlay", [bash, "tools/legacy_data/build-all.sh", "nhl24"], core.REPO,
                     env={"NHL24_PACK": "game/work/nhl24/out/pack-edge"}):
            return 1
    d = core.diff()
    say(f"готово: сборка отличается от игры в {len(d)} файлах (python -m kitport diff — список)")
    return 0


# ---------------------------------------------------------------- install / rollback

def confirm(a, text):
    if a.yes:
        return True
    try:
        return input(text + " [y/N] ").strip().lower() in ("y", "yes", "д", "да")
    except EOFError:
        return False


def cmd_install(a):
    d = core.diff()
    if not d:
        say("ставить нечего: cache: игры совпадает со сборкой")
        return 0
    if core.game_blocks_cache():
        sys.exit("NHL Legacy запущена с этим cache: — закройте игру")
    for kind, rel, _ in d:
        say(f"  {kind:8} {rel}")
    flags = core.install_flags()
    if not confirm(a, f"поставить {len(d)} файлов (флаги {' '.join(flags) or '—'})?"):
        say("отменено")
        return 1
    bdir, man = core.backup(d, a.tag)
    say(f"копия заменяемого: {len(man['changed'])} файлов, новых {len(man['new'])} → {bdir}")
    rc = core.run_installer(flags)
    if rc:
        say(f"установщик: ошибка {rc}; откат — python -m kitport rollback {os.path.basename(bdir)}")
        return rc
    left = core.diff()
    say("сверка:", "cache: = сборка" if not left else f"ОТЛИЧАЮТСЯ ещё {len(left)} файлов")
    stamp = datetime.datetime.now().strftime("%d.%m %H:%M")
    say("\nстрока в журнал (docs/nhl24-uniforms.md §15.1), дописать что и почему:")
    say(f"- {stamp} — … Обновились {len(d)} файл(ов): " + ", ".join(f"`{r}`" for _, r, _ in d[:8])
        + (" …" if len(d) > 8 else "") + f". Копия заменённого — `backup-cache/{os.path.basename(bdir)}`.")
    return 0 if not left else 1


def cmd_rollback(a):
    d = a.dir if os.path.isabs(a.dir) else os.path.join(core.BACKUP_CACHE, a.dir)
    if not os.path.isdir(d):
        sys.exit(f"нет папки {d}")
    if core.game_blocks_cache():
        sys.exit("NHL Legacy запущена с этим cache: — закройте игру")
    if not confirm(a, f"вернуть в cache: файлы из {d}?"):
        say("отменено")
        return 1
    back, gone = core.restore(d)
    say(f"возвращено {back} файлов, убрано новых {gone}. Сборка теперь отличается от игры — следующая "
        "установка поставит её снова.")
    return 0


# ---------------------------------------------------------------- main

def main():
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(prog="python -m kitport", description=sys.modules["kitport"].__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("doctor", help="проверка окружения")
    sub.add_parser("status", help="что стоит в игре против сборки")
    s = sub.add_parser("snapshot", help="снимок «было» файлов слота форм")
    s.add_argument("--tag", default="before")
    s = sub.add_parser("compare", help="слот форм против снимка «было»: сколько и где изменилось")
    s.add_argument("--before", default=None, help="папка снимка (по умолчанию — последний)")
    s.add_argument("--clubs", default="", help="клубы через запятую (MIN,NJD), по умолчанию — все в снимке")
    s.add_argument("--th", type=int, default=core.COMPARE_TH, help="порог отличия тексела, из 255")
    s = sub.add_parser("diff", help="сборка против cache: игры")
    s.add_argument("--prefix", default="", help="только пути с этим началом (rendering/jersey …)")
    s = sub.add_parser("build", help="стадии сборки формы")
    s.add_argument("--club", default="MIN")
    s.add_argument("--kits", default="away,home")
    s.add_argument("--stages", default=",".join(STAGES), help=f"через запятую из {STAGES}")
    s.add_argument("--meshes", action="store_true", help="и сетки слота (fb.edge_kit meshes) — после правки сеток")
    s = sub.add_parser("install", help="установка в игру с копией заменённого")
    s.add_argument("--tag", required=True, help="метка копии: edge12, mgrhs …")
    s.add_argument("--yes", action="store_true")
    s = sub.add_parser("rollback", help="вернуть файлы из backup-cache")
    s.add_argument("dir", help="папка в backup-cache (user-20261021-edge11) или полный путь")
    s.add_argument("--yes", action="store_true")
    s = sub.add_parser("sheet", help="листы «было | стало»")
    s.add_argument("--before", default=None, help="папка снимка (по умолчанию — последний)")
    s.add_argument("--out", default=None)
    s = sub.add_parser("uvmap", help="схема развёртки свитера Legacy")
    s.add_argument("--kit", default="MIN_away", help="текстура какой собранной формы подложить")
    s.add_argument("--plain", action="store_true", help="без текстуры (только части тела, высоты, зоны)")
    s.add_argument("--out", default=None)
    s = sub.add_parser("check", help="лист проверки форм слота: ворот, рельеф, превью меню, замер щита")
    s.add_argument("--clubs", default="", help="клубы через запятую (по умолчанию — все в слоте)")
    s.add_argument("--out", default=None)
    sub.add_parser("params", help="каталог параметров формы")
    s = sub.add_parser("present", help="лист «ставим или правим» на форму слота: наша и оригинал, «одетый» свитер, "
                                       "игрок целиком, каска, наклейка, шрифт")
    s.add_argument("--clubs", default="", help="клубы через запятую (по умолчанию — все в слоте)")
    s.add_argument("--kits", default="", help="формы через запятую: home,away (по умолчанию — все)")
    s.add_argument("--name", default="", help="фамилия на спине (по умолчанию — звезда клуба, fb.jersey_mesh.STARS)")
    s.add_argument("--number", default="", help="номер (по умолчанию — звезды клуба)")
    s.add_argument("--letter", default="C", choices=("C", "A", ""), help="буква капитана (C, A; пусто — без буквы)")
    s.add_argument("--out", default=None, help="папка листов (по умолчанию — compare/kitport/)")
    s = sub.add_parser("collar", help="ворот крупно: наш и источник (цвет, основа + рельеф, сверху) — шнуровка или нет")
    s.add_argument("--clubs", required=True, help="коды клубов через запятую (TOR,MIN)")
    s.add_argument("--kits", default="home,away", help="формы через запятую")
    s.add_argument("--source-only", action="store_true", help="только источник (слот ещё не собран)")
    s.add_argument("--tilt", type=float, default=35.0, help="наклон камеры сверху, град")
    s.add_argument("--out", default=None, help="файл листа (по умолчанию — compare/kitport/collar-…png)")
    s = sub.add_parser("yoke", help="кокетка и плечи: наш и источник в одних видах с линиями высот, замер края кокетки")
    s.add_argument("--clubs", required=True, help="коды клубов через запятую (MTL,BUF)")
    s.add_argument("--kits", default="", help="формы через запятую (по умолчанию — с кокеткой в профиле)")
    s.add_argument("--source-only", action="store_true", help="только источник (слот ещё не собран)")
    s.add_argument("--views", default="", help="углы видов, град (по умолчанию 0,90,180,45,135)")
    s.add_argument("--frame", default="", help="кадр x0,x1,y0,y1, м (по умолчанию -0.42,0.42,1.38,1.76)")
    s.add_argument("--out", default=None, help="файл листа (по умолчанию — compare/kitport/yoke-…png)")
    s = sub.add_parser("backs", help="спины всех форм слота одним листом: фамилия и номер клетками атласа, как в игре")
    s.add_argument("--clubs", default="", help="клубы через запятую (по умолчанию — все в слоте)")
    s.add_argument("--name", default="MACKINNON", help="фамилия")
    s.add_argument("--number", default="88", help="номер")
    s.add_argument("--cols", type=int, default=8, help="форм в ряду")
    s.add_argument("--out", default=None, help="файл листа (по умолчанию — compare/kitport/backs-….png)")
    s = sub.add_parser("lettering", help="фамилия, номер и промежутки букв на спине (см) против эталона")
    s.add_argument("--clubs", default="", help="клубы через запятую (по умолчанию — все в слоте)")
    s.add_argument("--ref", default="MIN,NJD,TBL,BOS,DET,LAK,SEA,VGK", help="эталон — одобренные клубы")
    s = sub.add_parser("audit", help="автопроверка форм слота: номера на рукавах и литера на полосах, размеры спины, "
                                     "низ гетр, каска (--helmets) — что пользователь находил в игре")
    s.add_argument("--clubs", default="", help="клубы через запятую (по умолчанию — все в слоте)")
    s.add_argument("--helmets", action="store_true", help="и строки шлема NHL 27 (нужна база NHL 27)")
    s = sub.add_parser("survey", help="обзор форм клубов источника: перед, плечо, ворот (разбор по типам)")
    s.add_argument("--source", default="nhl27")
    s.add_argument("--clubs", default="", help="папки клубов через запятую (по умолчанию — все)")
    s.add_argument("--kits", default="default", help="default — дом и выезд по базе источника; или папки через запятую")
    s.add_argument("--jobs", type=int, default=8)
    s = sub.add_parser("profile", help="генератор профиля клуба из NHL 27: предложение и сравнение (--write — записать)")
    s.add_argument("--club", required=True, help="код клуба (BOS); без --write — можно через запятую (NJD,TBL)")
    s.add_argument("--write", action="store_true", help="записать профиль, номера в реестре, каску и краги")
    s.add_argument("--write-palette", action="store_true", help="и палитру клуба NHL 27 в nhl24_team_colors.json")
    s.add_argument("--no-head-check", action="store_true",
                   help="не сверять прочие разделы с git HEAD (параллельная работа: у других клубов правки не закоммичены);"
                        "сверка с файлом до записи остаётся")
    a = p.parse_args()
    if a.cmd == "audit":
        from . import audit
        return audit.cmd_audit(a)
    if a.cmd == "profile":
        from . import profile
        return profile.cmd_profile(a)
    if a.cmd in ("sheet",):
        from . import sheets
        return sheets.cmd_sheet(a)
    if a.cmd == "uvmap":
        from . import uvmap
        return uvmap.cmd_uvmap(a)
    if a.cmd == "check":
        from . import check
        return check.cmd_check(a)
    if a.cmd == "collar":
        from . import collar
        return collar.cmd_collar(a)
    if a.cmd == "yoke":
        from . import yoke
        return yoke.cmd_yoke(a)
    if a.cmd == "backs":
        from . import backs
        return backs.cmd_backs(a)
    if a.cmd == "lettering":
        from . import lettering
        return lettering.cmd_lettering(a)
    if a.cmd == "survey":
        from . import survey
        return survey.cmd_survey(a)
    if a.cmd == "present":
        from . import present
        return present.cmd_present(a)
    if a.cmd == "params":
        from . import params
        return params.cmd_params(a)
    return {"doctor": cmd_doctor, "status": cmd_status, "snapshot": cmd_snapshot, "compare": cmd_compare, "diff": cmd_diff,
            "build": cmd_build, "install": cmd_install, "rollback": cmd_rollback}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
