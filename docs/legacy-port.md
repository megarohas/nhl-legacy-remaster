# Свой порт NHL Legacy (legacy-port/)

Порт NHL Legacy Edition (Xbox 360, TitleID `454109EC`, 2015, база 2015/16) на нашем тулчейне —
ReXGlue SDK 0.10.0.24 (ночной и своя сборка `ref/rexglue-sdk-custom` с Vulkan и FSR/CAS), по
образцу порта NHL 13 (`port/`, `port-ffx/`). Начат 08.10.2026 по плану
[legacy-port-feasibility.md](legacy-port-feasibility.md) (вариант «В»). Цель — чтобы друзья
играли в Legacy с нашими изменениями: год, скорость, данные (составы, формы, шрифты…), а
дальше — франшиза на 32 команды.

## Что работает

| Что | Состояние |
|---|---|
| Запуск, заставка, PRESS START, приветствие (тип игрока, геймплей, управление, любимая команда) | да (08.10, D3D12 ROV) |
| Главное меню, «Играть сейчас», выбор команд и формы | да |
| Матч: арена, заставка выхода, табло, игроки, шлемы и формы, номера, трибуны | да (CPU против CPU, ANA–SJ) |
| Спин потока рендера (`nhl_fence_wait`) и композиты экипировки (`nhl_composite_readback`) | да — функции те же, что в NHL 13 |
| D3D12 RTV (быстрее ROV) | да, но только с `execute_unclipped_draw_vs_on_cpu = true`: матч ARZ–ANA целиком — лёд, игроки, табло, трибуны (08.10, 20:30). У соседей «RTV — чёрный матч» — без этого флага (умолчание SDK — false, в Xenia было true) |

## Устройство

`legacy-port/` — проект ReXGlue. В git: `CMakeLists.txt`, `CMakePresets.json`, `build.cmd`,
`nhllegacy_manifest.toml`, `nhllegacy_*.toml` (ручные функции, врезки), `nhllegacy.example.toml`,
`src/`, `scripts/`, `dist-template/`, `generated/rexglue.cmake`. Только локально: сгенерированный
код `generated/default/` (производное от кода игры), сборка `out/`, сейвы и кэш `userdata/`,
образы и разведка прототипа (`images/`, `xmatch-*`, `sites/`, `codegen/`, `analysis/` …).

| Файл | Что |
|---|---|
| `nhllegacy_manifest.toml` | диск `game/other/legacy/disc`, setjmp `0x830801C0` / longjmp `0x8307E1B0` |
| `nhllegacy_functions.toml` | 327 ручных функций: 306 — наш `tools/find_indirect_targets.py` по образу Legacy, 21 — адреса из списка nhl-legacy-recomp (их порт находил по падениям; нашим фильтром не находятся) |
| `src/nhllegacy_app.h` | хост: пути из `nhllegacy.toml` (без настроек — `game\` и `userdata\` рядом с exe), `cache:` → `userdata/cache/guest`, без окна достижений |
| `src/nhllegacy_crash.cpp`, `_watch.cpp`, `_snap.cpp`, `_debug.h` | отчёт о падении `nhllegacy_crash.txt`, слепки `dumps\`, стеки по флагу, сторож памяти — как в NHL 13 |
| `src/nhllegacy_input_lock.cpp` | обход гонки InputSystem SDK (XamInput* под мьютексом) |
| `src/nhllegacy_imports.cpp` | заглушки XUsbcam |
| `src/nhllegacy_fencewait.cpp` | ожидание забора D3D 827E2BC8 (в NHL 13 — 82663148) без холостого спина |
| `src/nhllegacy_composite.cpp` | resolve композиции экипировки 836214A8 / опрос забора 8361F3E0 (832B22A8 / 832B0250) — на время композиции `readback_resolve = full` |
| `src/nhllegacy_dbtrace.cpp` | трассировка обращений к таблицам базы (флаг `nhllegacy_dbtrace.on` рядом с exe): 827B6FA8 / 827B4818 |

Отличия от NHL 13 по данным диска: `cache:` проверяется для каждого файла раньше архивов
(`cache:\db\nhlng.db`, `cache:\fe\…`) — моды-данные кладутся в `userdata/cache/guest`
без перепаковки. Папка данных — своя (`legacy-port/userdata`), не `game/userdata` NHL 13.

## Сборка

```bat
:: Release — свой SDK (D3D12 + Vulkan, FSR 1 / CAS): out\build\win-amd64-release\nhllegacy.exe
S:\Claude\megarohas_nhl13\legacy-port\build.cmd
:: RelWithDebInfo — ночной SDK (только D3D12), с символами в отчёте о падении
S:\Claude\megarohas_nhl13\legacy-port\build.cmd win-amd64-relwithdebinfo
```

Сборка сама запускает кодоген (`rexglue codegen nhllegacy_manifest.toml`), если менялись
манифест или `*.toml` врезок: ~18 мин при пониженном приоритете (анализ однопоточный), затем
компиляция 368 файлов ~5 мин. Вручную кодоген не запускать: сборка всё равно прогонит его заново
(отпечаток входов в `codegen.stamp` у ручного и встроенного запуска не сходится).

## Запуск

`nhllegacy.toml` рядом с exe (шаблон — `nhllegacy.example.toml`; `build.cmd` кладёт его, если
своего нет). Проверка без геймпада — `tools/gameshot.ps1 -Game legacy` (`--mnk_mode=true`),
замок `game/work/status/game.lock` общий с NHL 13.

## Для друзей

`bash legacy-port/scripts/make_dist.sh [--mods]` собирает папку `legacy-port/dist/NHL Legacy`
(не в git): `nhllegacy.exe`, `rexruntime.dll`, `rexgpu-xenos.dll` (Release, свой SDK — D3D12 и
Vulkan), `nhllegacy_snap.exe`, DLL рантайма MSVC (app-local: `msvcp140`, `msvcp140_atomic_wait`, `vcruntime140`,
`vcruntime140_1` из VC Redist BuildTools — ставить VC++ Redistributable не нужно),
`nhllegacy.toml` и `README.txt` из `legacy-port/dist-template/`, пустые `game\` и
`userdata\cache\guest\`. С `--mods` — моды-данные из `legacy-port/userdata/cache/guest` (без
кэша, который пишет сама игра: `*.ver`, `admanager_cache_images`, `highlights.sav`).

Файлов игры в папке нет: друг кладёт свою копию NHL Legacy (default.xex и `*.big`, диск без TU,
SHA-256 `default.xex` = `d818eb15…c55624`) в `game\` рядом с exe. Пути в `nhllegacy.toml` пустые —
`game\` и `userdata\` рядом с exe; можно указать свои. Публиковать папку — решает пользователь
(в ней производное кода игры — exe порта).
