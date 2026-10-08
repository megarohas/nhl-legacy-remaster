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

- **У себя:** ярлык «NHL Legacy» на рабочем столе → `legacy-port/out/build/win-amd64-release/nhllegacy.exe`
  (Release, свой SDK). Настройки — `nhllegacy.toml` рядом с exe (шаблон `nhllegacy.example.toml`;
  `build.cmd` кладёт его, если своего нет): игра — `game/other/legacy/disc`, сейвы и `cache:` —
  `legacy-port/userdata` (своя папка, не `game/userdata` NHL 13), лог — `legacy-port/out/game.log`.
- **Vulkan:** `gpu_backend = "vulkan"` + `render_target_path_vulkan = "fsi"` (проверено: меню и матч,
  имена и номера на свитерах на месте).
- **Быстрее на D3D12:** `render_target_path_d3d12 = "rtv"` + `execute_unclipped_draw_vs_on_cpu = true`.
- Проверка без геймпада — `tools/gameshot.ps1 -Game legacy` (`--mnk_mode=true`; `-Do seq` — шаги
  «wait/shot/key»), замок `game/work/status/game.lock` общий с NHL 13. Закрывать игру — из того же
  PowerShell, из которого запущена (`taskkill` из Git Bash не закрывал).

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

## Год (season_year)

Как в NHL 13 ([year-and-date.md](year-and-date.md)): `season_year` в `nhllegacy.toml` — первый год
сезона (2026 = 2026/27), 2015 — как на диске; франшизу грузить с тем же годом, с которым создана.
Врезки — `nhllegacy_year_hooks.toml` (генератор `tools/year_hooks.py --game legacy`), код —
`src/nhllegacy_year.cpp`: результат `li`/`subfic`/`addi +Y` больше на `season_year − 2015`, `addi −Y`
(«номер сезона = год − 2015») — меньше, сравнения пересчитываются против `Y + сдвиг`.

| | мест |
|---|---:|
| `li`/`subfic`/`cmpwi`/`cmplwi` с 2014–2016 и `addi ±2014…2016` | 314 |
| сдвигаются | 259: 212 перенесённых врезок NHL 13 (число ровно +3) и 47 разобранных вручную |
| KEEP (не год лиги) | 55: адреса `lis+addi` 22, стек/кадр `addi rD, r1, 2016` 24, смещение +2016 в структуре 4, онлайн 3 («год продукта» 2016 в путях запросов, пара ±2015 в «SetPlayerStat»), факт «Phoenix до 2014» 1, маска RGB565 0x07E0 1 |
| EXTRA (производные) | 16: года рождения 1965/2000 (редактор), 1996/1995 («Стань профи»), 1986 и год драфта 2006 (созданный игрок), 2033 (год драфта сгенерированного), «недавний драфт» 2004, FeLeague 1994, пики драфта 115/121/2021 (год − 1900) |
| врезок | 275 (сравнения: 1965, 2004, 2014, 2015) |

Года 2011–2013 в коде Legacy (32 места) — не год лиги: те же совпадения, что в KEEP NHL 13, адреса,
константы ГСЧ. Попутно найдено для NHL 13 (не исправлено, порт NHL 13 не трогали): пики драфта
`82807734 li 112`, `8281E87C addi 118`, `8281EA3C addi 2018` не в EXTRA — при `season_year ≠ 2012` пики
при создании лиги получают года 2012…2018.

## НХЛ на 32 команды

База — от агента legacy-data (`tools/nhl32.py --game legacy`): Сиэтл и Вегас — строки 30/31
`exhibitionteams`, сборные Матча звёзд — Custom 222/223, `divisiongroup` 8/8/8/8 (Pacific + SEA/VGK,
Аризона/Юта — Central), `nhlschedule`, `favoriteteamschedule` и `nhlfutureschedule` на 32 × 84
(home/away 6 бит, Матч звёзд 32/33). Код — `nhl_teams = 32` в `nhllegacy.toml`:

- `src/nhllegacy_teams.cpp` — подмены 22 функций и реализации врезок (перенос `port/src/nhl13_teams.cpp`
  со смещениями Legacy);
- `nhllegacy_team_hooks.toml` — 72 ручные врезки;
- `nhllegacy_team_sites.toml` / `src/nhllegacy_team_sites.cpp` — 109 мест «30 → 32» одной инструкцией
  (генератор `tools/team_hooks.py --game legacy` по `nhllegacy_team32_sites.json`,
  `nhllegacy_ahl32_sites.json`).

Что в Legacy иначе, чем в NHL 13 (разбор четырёх помощников, адреса — в файлах выше):

- **Дерево лиги** 82A1E910 по-прежнему строит код (база `divisiongroup` только копируется в
  `leagueteams`): 4 дивизиона (id 3 Pacific 7, 4 Central 7, 5 Atlantic 8, 6 Metropolitan 8), массив
  команд на стеке на 8 — врезки перед четырьмя узлами 82AEBEF0 (82A1E9D4, 82A1EA1C, 82A1EA8C, 82A1EAE4)
  подставляют 8/8/8/8, подмена дописывает 30/31 в список лиги. Меню выбора (829CCA18) — на 30.
- **Календаря-генератора нет.** Первый сезон — `nhlschedule` из базы, со второго — `nhlfutureschedule`
  (82A07C78, селектор 2) с перестановкой команд внутри дивизионов (82AFA838, сдвиг (год − 2015) mod n) и
  переносом дат на дни недели нового года (82B218E0). Предсезонка (82B1E988) — круговой турнир внутри
  дивизиона по таблице 28 пар, не больше 4 дивизионов по 8: при 8/8/8/8 — 112 игр. Буфер календаря лиги —
  1350 игр по 28 байт, как в NHL 13: 1344 + 112 + Матч звёзд не входит — 13 врезок поднимают до 1600.
  Поэтому со второго сезона календарь берётся из текущей базы: франшизу на 32 нельзя продолжать с базой на 30.
- **Кэш сводок команд** (0x83BDC414): записи 332 байта (было 136), флаги +9960, счётчик +9992, всего 9996 —
  записи 30/31 за ним; конструктор 82B63708 строит записи через 82B5F320 (три строки по 100 байт).
- **Настройки и состояния лиги** сдвинуты: «есть сборные» +604 (было +600), сборные — состояния 55/56, Матч
  звёзд — 54; число групп лиг в 82B43DA0 — r18 (было r19).
- **Встроенные функции**: 8289AB80 (номер по teamid) — внутри 82B0A178 (подмена), 8289B040 и 8289AF40 —
  внутри 82B0B798 / 82B0A250 (врезки чтения +520).
- **Драфт**: две статические таблицы порядка 2015 года (0x83A15178 и 0x83A151F0) — обе расширяются до 32;
  лотерея Legacy (один розыгрыш, 14 команд) заменена правилами НХЛ 2022 на 16 команд (два розыгрыша, не выше
  10 мест), список — r1+384.
- **Новое в Legacy**: проверка «номер < 60» в 82AFC398 (→ 62), штаб команд `leaguestaffdata` при создании
  (82B66530), случайная команда НХЛ по маске [30] (82B97860), флаги «пересобрать сводку состава» +15817[30]
  вплотную к подобъекту — флаги 30/31 снаружи (4 врезки RosterFlag*), фильтр «команда НХЛ < 30» в таблицах
  статистики игроков (82B26C40, 82B27050 — без них SEA/VGK выпадали бы из лидеров; в NHL 13 та же ошибка,
  828BDA50/828BDE60, не исправлена).
- **Не нужно** в Legacy: `Nhl13DivisionStart` (EA сама считает начало дивизиона суммой), `TeamCacheWords`.
- **Отложено** (как и в NHL 13): GmModeLogic / Be a Pro (массивы [30] в сохраняемых данных), StatsCache
  (предел 30), «удержание зарплаты» `stockteamsalaryextras` (у 30/31 нули, падений нет), отметки x/y/z/e
  таблицы (рассчитаны на 15 + 15 даже в оригинале с 14 + 16 — косметика).
- **Нужно в базе** (делает legacy-data, `tools/nhl32.py --game legacy`): `leaguegmdata` и `leaguestaffdata` —
  `maxinsert` 30 → 32; поля «команда −1…30» (номер + 1, 5 бит) — 6 бит **в заголовках таблиц самой
  `nhlng.db`**, не только в `nhlng-meta.xml`: Legacy строит таблицы франшизы по заголовкам пустых `league*`
  базы (NHL 13 — по схеме). Без этого у игроков Вегаса `proteam` = 32 обрезалось до 0: при создании лиги
  21 игрок VGK уехал в Аризону (у VGK 0, у ARZ 45, у строк состава VGK `key` = 31·40 + место, а `team` = 22),
  пики VGK остались без владельца, а 9.10 (VGK–PIT) симуляция висла в `rand() % 0` (8298A438 → 82A57670) —
  как зависание NHL 13 «10–11 октября». Поля: `leagueplayerbiotable` proteam/draftteam/tradeblockteam,
  `leaguedraftpick` owner/origteamid, `leaguefreeagentdata` originalteamid/signedteamid,
  `leaguerookiedata.draftteam`, `leaguecontractoffers.teamnotification`, `leaguegamemodesvars.team`,
  `leaguescoutvisits.team`, `exhibitiondraftpick` owner/origteamid. Сейвы франшизы, созданные на 5-битной
  раскладке, не чинятся — франшизу создать заново. Ещё в схеме: у `leaguefreeagentdata` есть только
  `playerinterestinteam0…29` — интерес свободных агентов к 30/31 хранить негде (проверить в межсезонье).
