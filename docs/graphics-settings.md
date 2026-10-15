# Графика порта: что настраивается и как выносить в лаунчер

Ресерч 07.10.2026. Только чтение: исходники и бинарники SDK, данные игры (`game/extracted`),
логи `nhl-13-port/out/*.log`, соседние рекомпилы, интернет. Игра и сборка не запускались — всё
ниже выведено из кода и требует проверки в игре.

**Версии.** Порт собран на nightly `0.10.0.24-dev.gbd833a2` (`ref/rexglue-sdk-0.10.0.24`), а
`ref/rexglue-sdk-src` — тег `v0.10.0` (`f5337cd`), на 24 коммита старше
([сравнение](https://github.com/rexglue/rexglue-sdk/compare/v0.10.0...bd833a2)). Плагин графики
(`src/graphics/**`), презентер, ImGui и оверлеи с тех пор не менялись; изменились окно и
полноэкранный режим, видеорежим гостя, ввод и `ui/rex_app.cpp`. Ссылки `путь:строка` даны от
`ref/rexglue-sdk-src/src/` (v0.10.0); `bd833a2:путь:строка` — nightly на GitHub, от корня
репозитория. Наличие cvar'ов в nightly сверено по экспортам `FLAGS_*_storage_` и строкам
`rexruntime.dll` / `rexgpu-xenos.dll`.

## Главное

1. **Приоритет источников в коде обратный** тому, что написано в вики SDK и в шапке
   `nhl-13-port/nhl13.example.toml`: командная строка > переменные `REX_*` > `nhl13.toml` > умолчания;
   правки из консоли и окна F4 сильнее всего.
2. **Горячей перезагрузки `nhl13.toml` нет**: файл читается только при старте. «На лету» — только
   встроенная консоль (`` ` ``/Ё), окно F4 или код порта. Lifecycle cvar'а — лишь метка.
3. Сразу и бесплатно: **`anisotropic_override = 5`** (16x; по умолчанию в этом SDK 4x).
4. Главный рычаг качества — **`resolution_scale`** (2 = 2560×1440 внутри). Совместим с ROV и
   readback, но ROV «заметно медленнее» (комментарий SDK), а при гостевом vsync кадр, не
   уложившийся в 16,7 мс, сразу падает до 30 FPS. Пробовать 2, следить за запасом GPU.
5. Стоит один раз проверить **`render_target_path_d3d12 = "rtv"`**: в Xenia Canary NHL 13
   играбельна с умолчаниями (на NVIDIA это RTV), а чёрный матч с RTV видели у соседа — NHL Legacy
   (у NHL 14 матч чёрный на D3D12 вообще, они ушли на Vulkan). Если у нас RTV рисует — это самый
   большой выигрыш скорости.
6. **FSR/CAS при выводе в готовом nightly нет**: `present_effect` принимает только `bilinear`
   (FidelityFX выключен при сборке SDK). Нужна своя сборка SDK.
7. FXAA из SDK (`swap_post_effect`) не нужен: у игры своё FXAA каждый кадр поверх 2×MSAA.
8. Не трогать `vsync`, `video_mode_*`, `resolution` и (в полноэкранном режиме)
   `window_width/height`: последние в nightly меняют заодно видеорежим гостя, а сцена игры
   размечена под 720p и 10 МБ EDRAM.
9. **Задержка и плавность:** в каждом запуске живёт невидимый тост-диалог достижений, из-за него
   презентер выводит кадры из UI-потока по тикам vblank монитора — кадр игры ждёт до одного
   обновления экрана, VRR толком не работает. Лечится в порте одной перегрузкой
   (`CreateAchievementNotificationDialog() → nullptr`).
10. Кнопка **«Save to config» в F4 перезаписывает `nhl13.toml`** автосгенерированным файлом —
    комментарии пропадут. Не нажимать (или увести `config_path` в отдельный файл лаунчера).
11. Кадр игры описан текстовым сценарием **`scrape/default.scrape`**, и игра сначала ищет его в
    `cache:` — как `nhlng.db`. Путь к правкам без кода: отражения в полном разрешении, SSAO и
    тени в матче (сейчас выключены в геймплее), отключение FXAA игры.
12. Игра при старте ищет **`d:\startup.ini`** (дев-конфиг EA); в exe есть `sUnlockFramerate`,
    `sShowFramerate`, `gOverrideCameraFOV`, `gDisableCrowdCulling` и др. Формат не выяснен —
    дешёвый эксперимент.
13. Лаунчеру проще всего передавать настройки **аргументами `--имя=значение`** (сильнее toml,
    файл не трогается); для постоянных — отдельный файл лаунчера, подключённый портом.
14. «Вязкость» отчасти — сама игра: в NHL 13 появилось True Performance Skating (инерция,
    радиус поворота растёт со скоростью); в Gameplay Sliders есть Player Acceleration и Game Speed.
15. **Шлемы, перчатки, щитки** игра собирает при загрузке рендером в текстуру и дочитывает
    процессором; с `readback_resolve = "some"` процессор получал старые байты (чужой шлем,
    прозрачность). Порт включает `full` только на время композиции (`nhl_composite_readback`,
    раздел (е)).

## 1. Как устроены настройки

### Источники и приоритет

| Источник | Как задать | Приоритет |
|---|---|---|
| Умолчание | в коде (`REXCVAR_DEFINE_*`) | 0 |
| `nhl13.toml` | только это имя, рядом с exe (`ui/rex_app.cpp:146`); порт читает его сам в `OnConfigurePaths`, SDK — ещё раз (`ui/rex_app.cpp:157-158`) | 1 |
| Окружение | `REX_<ИМЯ_ЗАГЛАВНЫМИ>`, например `REX_RESOLUTION_SCALE=2` (`core/cvar.cpp:70-77`) | 2 |
| Командная строка | `--имя=значение` | 3 |
| Во время работы | консоль, F4, `SetFlagByName` из кода | 4 |

Порядок вызовов: `cvar::Init(argv)` → `ApplyEnvironment()` (`ui/windowed_app_main_sdl.cpp:40-41`) →
`OnConfigurePaths` → `LoadConfig`. Источник пишет значение, только если его приоритет не ниже
текущего (`include/rex/cvar.h:144-150`, `core/cvar.cpp:83-85`). В nightly DLL те же строки:
«Env: {} ignored, already set on the command line», «Config: {} ignored, already set by a
higher-priority source». Вики (`ref/rexglue-sdk.wiki/CVar-System.md:133`) и комментарий
`nhl-13-port/nhl13.example.toml:2-3` («конфиг сильнее аргументов») устарели.

Что важно для лаунчера:
- ключи TOML плоские; вложенная таблица склеивается через `_` (`core/cvar.cpp:97-99`):
  `[d3d12]` + `queue_priority = 1` — то же, что `d3d12_queue_priority = 1`;
- **опечатки молча игнорируются**: неизвестный ключ откладывается «до регистрации»
  (`core/cvar.cpp:117-122`), а предупреждение «unknown cvar» печатает только `FinalizeInit`
  (`core/cvar.cpp:679-687`), который ни SDK, ни порт не вызывают. Недопустимое значение (вне
  `range`/`allowed`) — WARN «Config: invalid value for cvar» в логе (`core/cvar.cpp:133`),
  значение не применяется;
- cvar'ы плагина `rexgpu-xenos` (всё про GPU) регистрируются позже, при загрузке плагина
  (`ui/rex_app.cpp:317`). Для них из командной строки работают только формы `--имя=значение`,
  `--имя`, `--no-имя` (`core/cvar.cpp:610-633`), раздельное `--имя значение` — нет.

### Lifecycle

| Метка | Смысл |
|---|---|
| `kHotReload` (по умолчанию, если не указано) | «можно менять на лету». Это только метка: эффект живой, если код читает значение при каждом использовании. Часть cvar'ов без явной метки читается один раз — в таблицах ниже они помечены «перезапуск» |
| `kRequiresRestart` | значение примется, подействует со следующего запуска; F4 пишет [restart] (`ui/overlay/settings_overlay.cpp:32-55`) |
| `kInitOnly` | задаётся только при старте; в F4 серое |

Механизм «на лету» — `SetFlagByName` плюс колбэки изменений (`core/cvar.cpp:298-345`). В nightly
колбэки есть у `fullscreen`, `fullscreen_exclusive`, `monitor`, `window_width/height`,
`resolution` (`bd833a2:src/ui/rex_app.cpp:364-383`) и `log_level`. Наблюдателя за файлом
конфига нет — правки `nhl13.toml` действуют со следующего запуска.

### Встроенный UI (ImGui) — уже есть в exe

| Клавиша (cvar бинда) | Что |
|---|---|
| F3 (`bind_debug_overlay`) | Отладочный оверлей. График времени кадра и счётчики — только в не-Release сборке SDK (`CMakeLists.txt:25-31` корня SDK), то есть в нашей RelWithDebInfo. Строка «Guest FPS» появится, только если приложение отдаёт статистику (`SetGuestFrameStats`, `ui/rex_app.cpp:609`) — порт пока не отдаёт |
| `` ` ``/Ё (`bind_console`) | Консоль: `имя` — показать, `имя значение` — задать, `find подстрока` (`ui/overlay/console_overlay.cpp:156-225`) |
| F4 (`bind_settings`) | Все cvar'ы по категориям, поиск, метки [live]/[restart]/[init-only]. Кнопка «Save to config» (`ui/overlay/settings_overlay.cpp:505-506`) вызывает `SaveConfig`: **перезаписывает `nhl13.toml`** строкой «# Auto-generated cvar configuration» и всеми неумолчательными значениями (`core/cvar.cpp:693-711`) — комментарии пропадут, значения из командной строки «впечатаются» |
| F7 (`bind_achievements`) | Достижения |

Бинды — тоже cvar'ы (категория Input/Keybinds/System, `ui/keybinds.cpp:171-198`), их можно
переназначить в `nhl13.toml`. Пока открыт F3, F4 или консоль, ввод в игру гасится, когда
ImGui хочет мышь (`ui/rex_app.cpp:253-256`).

## (а) Что можно менять уже сейчас через конфиг

«На лету» — можно поменять из консоли или F4, сработает сразу; «перезапуск» — читается при
старте. Те же ключи годятся для `nhl13.toml`, `--имя=значение` и `REX_ИМЯ`.

### Картинка

| Ключ | Значения (умолч.) | Что делает | Применение | Для NHL 13 | Код |
|---|---|---|---|---|---|
| `resolution_scale` | 1–8, по факту ≤7 (1) | Внутреннее разрешение ×N по обеим осям: все render target'ы, EDRAM, resolve. `draw_resolution_scale_x` / `_y` — то же по осям, сильнее общего | перезапуск | **Главный рычаг.** 2 → 2560×1440 (на 1080p — суперсэмплинг, на 1440p — 1:1), 3 → 3840×2160. Readback форм работает (кадр даунскейлится перед чтением на CPU). С ROV цена ≈ ×4 по пикселям; «не успел в 16,7 мс» = сразу 30 FPS. Проверить формы и шлемы, в логе — нет ли «swap source is unscaled» (игра выводит немасштабированную копию) и «reducing to» | `graphics/pipeline/texture/cache.cpp:66-78, 236-250`; `include/rex/graphics/pipeline/texture/cache.h:63`; `graphics/d3d12/command_processor.cpp:914-925, 1971-1980, 3020-3065` |
| `anisotropic_override` | −1 нет; 0 выкл; 1…5 = 1x/2x/4x/8x/16x (3 = 4x) | Принудительная анизотропия для текстур с мипами и линейной фильтрацией | на лету | **5 (16x)**: лёд, разметка, логотипы, борта под углом камеры; на 3060 бесплатно | `graphics/pipeline/texture/cache.cpp:52-64`; `graphics/d3d12/texture_cache.cpp:973-977` |
| `readback_resolve` | none / fast / some / full (none) | Копия результата resolve (render-to-texture) из памяти GPU в память гостя — для кода игры, который читает его процессором (композиция шлемов, перчаток, щитков). some — копия только при «промахе» (первый resolve с этим адресом и длиной или после 60 кадров простоя), дальше — нет; fast — каждый раз, но данные прошлого resolve с тем же ключом; full — синхронно | на лету | Оставить **some**: full останавливает GPU на каждом resolve (у нас ~25 FPS). Шлемы и экипировка с some читали старые байты — порт сам включает full только на время композиции (`nhl_composite_readback`, раздел (е)); fast их не лечит | `bd833a2:src/graphics/command_processor.cpp:48-56, 172-182`; `bd833a2:src/graphics/d3d12/command_processor.cpp:2873-3103`; `bd833a2:src/graphics/vulkan/command_processor.cpp:4384-4690` |
| `readback_resolve_half_pixel_offset` | bool (false) | При scale > 1 даунскейл для readback берёт центр блока | на лету | Только если при ×2 «поплывут» формы | `graphics/command_processor.cpp:57-60` |
| `render_target_path_d3d12` | "" (на NVIDIA = rtv) / rtv / rov | Эмуляция EDRAM: rtv — хостовые RT (быстро), rov — растровые UAV (точно; «currently much slower generally») | init-only | Сейчас rov (по опыту соседей). Один раз проверить rtv на матче — см. «Главное», п. 5. Если матч чёрный — вернуть rov | `graphics/d3d12/render_target_cache.cpp:44-46, 176-203` |
| `swap_post_effect` | none / fxaa / fxaa_extreme (none) | FXAA SDK по готовому кадру 1280×720 вместе с интерфейсом, до растяжения в окно | перезапуск | **none**: у игры своё FXAA каждый кадр поверх 2×MSAA (`default.scrape`, `RenderScene → Render_FXAA`); второе только мылит текст | `graphics/graphics_system.cpp:34-36, 138` |
| `present_effect` | bilinear (в готовом SDK — только он) | Растяжение кадра игры в окно; cas/fsr/fsr2/fsr3 — только в SDK, собранном с FidelityFX | перезапуск | Недоступно: `REXGLUE_ENABLE_FIDELITYFX` по умолчанию OFF, строк FSR/CAS в DLL nightly нет; `"fsr"` будет отвергнут с WARN | `ui/presenter.cpp:43-78`; `CMakeLists.txt:23` (корень SDK) |
| `present_dither` | bool (false) | Дизеринг в финальном проходе | перезапуск | По вкусу — против полос в тёмных градиентах арены | `ui/presenter.cpp:80-82` |
| `use_fuzzy_alpha_epsilon` | bool (false) | Нестрогое сравнение alpha-test против мерцания на NVIDIA | перезапуск (при трансляции шейдеров) | Только если мерцают сетка, трибуны, волосы | `graphics/flags.cpp:28-30`; `graphics/pipeline/shader/dxbc_translator_om.cpp:2685` |
| `async_shader_compilation`, `store_shaders` | bool (true, true) | Фоновая сборка пайплайнов; кэш шейдеров в `cache_root` | на лету / при старте | Оставить: кэш уже работает (в логе при старте ~430 шейдеров и ~280 пайплайнов из кэша) | `graphics/command_processor.cpp:77-81`; `graphics/graphics_system.cpp:38-40` |
| `texture_cache_memory_limit_soft` / `_hard` | 64–4096 (384) / 128–8192 (768) МБ | Пороги вытеснения текстур; доля под resolve сама растёт с scale² | перезапуск | Не обязательно; при подгрузочных фризах на 12 ГБ VRAM можно 1024 / 2048 | `graphics/pipeline/texture/cache.cpp:29-47, 256-268` |

### Окно и вывод

| Ключ | Значения (умолч.) | Что делает | Применение | Для NHL 13 | Код |
|---|---|---|---|---|---|
| `fullscreen` | bool (**true**) | Полноэкранное окно без рамки на разрешении рабочего стола | на лету (nightly; в консоли `fullscreen false`) | **true** — даёт independent flip, меньше задержка | `bd833a2:src/ui/window.cpp:33-36`; `bd833a2:src/ui/rex_app.cpp:364` |
| `fullscreen_exclusive` | bool (false), только nightly | Сменить режим монитора: размер — из `resolution`, частота — как у рабочего стола | на лету | Пользы нет: частоту не выбрать, а `resolution` заодно меняет видеорежим гостя | `bd833a2:src/ui/window.cpp:38-40`; `bd833a2:src/ui/window_sdl.cpp:311-345` |
| `monitor` | 0–16 (0 — по умолчанию) | Номер дисплея (1 — первый в списке SDL) | на лету (nightly) | по необходимости | `bd833a2:src/ui/window.cpp:42-45` |
| `window_width`, `window_height` | 0–8192 (0) | Размер окна в оконном режиме | на лету (nightly) | **Осторожно:** заданные оба становятся и видеорежимом гостя (`VdQueryVideoMode`), пока `video_mode_*` равны умолчаниям (задать 1280×720 явно нельзя — это и есть умолчание). Окно не 16:9 → презентер растянет картинку под «экран гостя» | `bd833a2:src/ui/window.cpp:25-31`; `bd833a2:include/rex/graphics/video_mode_util.h:111-128`; `bd833a2:src/kernel/xboxkrnl/xboxkrnl_video.cpp:42-51` |
| `resolution` | "" / 480p…1080p, 1440p, 4k / ШxВ | Пресет и для окна, и для видеорежима гостя | окно — на лету; гость — когда игра спросит | **Не задавать**: игра увидит «экран» 1920×1080 или 4K, которого у 360 не было | `bd833a2:src/ui/window.cpp:60-62`; `include/rex/graphics/video_mode_util.h:39-108` |
| `video_mode_width` / `_height` / `_refresh_rate` | 640–4095 (1280) / 480–4095 (720) / 24–240 (60) | Видеорежим гостя; частота = частота гостевого vblank | перезапуск | **Не трогать**: частота — то же, что `vsync` (скорость игры) | `bd833a2:src/ui/window.cpp:52-67`; `graphics/graphics_system.cpp:149-170` |
| `present_letterbox` | bool (true) | Поля, если окно не 16:9 (иначе растяжение) | на лету | true | `ui/presenter.cpp:32-33, 925` |
| `present_allow_overscan_cutoff` + `present_safe_area_x/_y` | false / 0–100 (90) | Разрешить срезать края кадра до N %, чтобы заполнить экран не 16:9 | перезапуск / на лету | Для 16:10 и шире — по вкусу; на 16:9 не влияет | `ui/presenter.cpp:35-41, 84-86, 907-963` |
| `d3d12_allow_variable_refresh_rate_and_tearing` | bool (true) | Swap chain с `ALLOW_TEARING`; кадр выводится `Present(0)` без ожидания vblank | перезапуск (флаг ставится при создании swap chain) | VRR-монитор: true (+ G-SYNC «для оконного и полноэкранного» в панели NVIDIA). Без VRR, если мешают разрывы, — false (цена — до одного обновления монитора задержки) | `ui/d3d12/d3d12_presenter.cpp:33-34, 398-414, 1150-1160` |
| `host_present_from_non_ui_thread` | bool (true) | Разрешает выводить кадр прямо из потока GPU, минуя UI-поток | ≈ перезапуск | true; сейчас фактически не действует из-за тост-диалога — см. (г) | `ui/presenter.cpp:29-30, 1313-1328` |
| `vsync` | bool (true) | Частота гостевого vblank: 60 Гц или «каждую 1 мс» + активное ожидание в WAIT_REG_MEM | на лету | **Не трогать** (игра ускоряется). Для справки: NHL 14 recomp сознательно играет с `vsync=false` — с ним у них кадры квантовались до 22–23 FPS | `graphics/graphics_system.cpp:149-176`; `graphics/command_processor.cpp:1034-1041` |
| `d3d12_queue_priority`, `d3d12_adapter` | 0–2 (1 = high) / −1 | Приоритет очереди D3D12; выбор видеокарты | перезапуск | не трогать | `ui/d3d12/d3d12_provider.cpp:32-38` |

### Ввод и звук

| Ключ | Значения (умолч.) | Что делает | Применение | Для NHL 13 | Код |
|---|---|---|---|---|---|
| `input_backend` | sdl / xinput (sdl) | xinput — прямой `XInputGetState` в момент опроса игрой | перезапуск | xinput (как сейчас) | `bd833a2:src/input/input_system.cpp:29-30` |
| `left_stick_deadzone_percentage`, `right_…` | 0–1 (0), nightly | Доп. радиальная мёртвая зона поверх игровой | на лету | 0 — не добавлять «вязкости» | `bd833a2:src/input/input_system.cpp:36-41` |
| `vibration` | bool (true), nightly | Вибрация | на лету | по вкусу | `bd833a2:src/input/input_system.cpp:34` |
| `audio_maxqframes` | 4–64 (8) | Глубина аудиобуфера | перезапуск | 12–16, если при ×2 появятся щелчки (у Legacy на высоком SSAA голодал звук) | `audio/audio_system.cpp:27-29, 55-57` |

### Не трогать (точность, служебное)

`gpu_plugin`, `protect_zero`, `gpu_allow_invalid_fetch_constants` (без них NHL не играет),
`native_2x_msaa`, `depth_float24_*`, `half_pixel_offset`, `gamma_render_target_as_unorm16`,
`d3d12_bindless`, `d3d12_tiled_shared_memory` (нужен для масштаба), `clear_memory_page_state`,
`occlusion_query_enable`, `readback_memexport*`, `direct_host_resolve`, `mrt_*`, `snorm16_*`,
`execute_unclipped_draw_vs_on_cpu*`, `pre_mask_resolve_l2_block`, `force_convert_*`, `dxbc_*`,
`d3d12_dxbc_*`, `dump_shaders`, `gpu_debug_markers`, `d3d12_debug`, `d3d12_break_on_*`. Полный
список с умолчаниями — `grep -rn REXCVAR_DEFINE ref/rexglue-sdk-src/src`.

## (б) Что требует правок данных, порта или SDK

### Данные через `cache:` (без кода)

Игра сначала ищет файлы в `cache:` (= `game/userdata/cache/guest/`), потом в `.big` — так уже
работают `db/nhlng.db` и локализация ([modding.md](modding.md)). По логам `nhl-13-port/out/game*.log`
так же ищутся `scrape\default.scrape`, `scrape\scenedef.lua`, `AttribDB\renddb.vlt/.bin`,
`shaders\*.fxo` (в т. ч. `fxaa.fxo`, `postfx.fxo`, `ssao.fxo`),
`rendering\colorcube\colorcube_stadium.xml`; отдельно — `d:\startup.ini` (корень игры).

**`scrape/default.scrape` — сценарий кадра** (текст, 29 КБ, из `boot.big` →
`game/extracted/big/boot/scrape/`): поверхности EDRAM с размерами и MSAA, порядок проходов.
Что в нём видно:
- основная сцена — 1280×720 с 2×MSAA, рисуется двумя половинами
  (`MsaaFrameBufferVertSplit $halfwidth0 $height0 … 2x` — предикатный тайлинг, иначе не влезает
  в 10 МБ EDRAM);
- отражения на льду и стёклах бортов и плоские тени на льду — каждый кадр в половинном
  разрешении 640×360 с 2×MSAA (`ReflectionFrameBuffer`, `IceReflectionTexture`,
  `Glass1/2ReflectionTexture`, `RenderToTextures`); SSAO — половинное; блюр bloom/DOF — 320×184;
- в конце кадра — своё FXAA (`RenderScene → Render_FXAA`, кроме hi-res скриншотов);
- динамические тени персонажей и SSAO **в геймплее выключены**: `RenderShadows` и `RenderSSAO`
  под `ifnot renderoptions is_in_gameplay` — работают в повторах и заставках.

Что попробовать: (1) отражения в полном разрешении — `$width0 $height0` без `2x`
(1280×720×(4+4) байт = 7,4 МБ влезает в EDRAM, с 2x — 14,7 МБ уже нет); (2) SSAO и тени в
матче — убрать условие `ifnot … is_in_gameplay`; (3) при `resolution_scale` ≥ 2 отключить FXAA
игры (меньше мыла). Сложность низкая (правка текста), риск — раскладка EDRAM и тайлинг движка;
проверять на матче, откат — удалить файл из `cache:`. При общем `resolution_scale` отражения и
так масштабируются, правка (1) — дешёвая альтернатива.

**`AttribDB/renddb` — атрибуты рендера** (`boot/attribdb/renddb.vlt` 353 КБ + `renddb.bin`
94 КБ). Классы: `rend_postfx`, `rend_shadows_0/2`, `rend_ssao`, `rend_vignette`,
`rend_lighting_0…3`, `rend_crowd`, `rend_ice`, `rend_stadium_*`, `rend_spotlight`,
`rend_skatespray`. Формат EA Attrib (VLT + BIN, имена полей — хеши) — нужен разборщик. Сложность
средняя; польза — тонкая настройка постобработки, виньетки, толпы.

**`d:\startup.ini` — дев-конфиг EA.** Exe при старте пишет «Attempting load of startup.ini.» и
открывает `d:\startup.ini` (в логе — на каждом запуске; на диске файла нет). Рядом менеджер
`cVarMan`, разбор — общий INI-ридер (`Ini:ReadBuffer`); синтаксис не выяснял. В образе есть
твики с подписями: `sUnlockFramerate` / `sShowFramerate` / `sEnableZPrepass` (категория
Render/Profile), `gOverrideCameraFOV`, `gOverrideCameraSettings`, `gDisableCrowdCulling`,
`gRenderCrowdProps`, `gLODShader`, `gbFastLoad` (в exe прямым текстом: «if you set gbFastLoad=1
in startup.ini»). Дешёвый тест: `game/extracted/disc/startup.ini` со строкой
`sShowFramerate = 1`. `sUnlockFramerate` — осторожно, скорость игры.

**Цветокоррекция** — `rendering\colorcube\colorcube_*.xml` (в `cacherender.big`, ещё не
распакован), если захочется другую «картинку».

### Код порта (без пересборки SDK)

| Что | Как | Сложность | Польза |
|---|---|---|---|
| **Убрать постоянный тост-диалог** | `CreateAchievementNotificationDialog()` → `nullptr` (заготовка закомментирована в `nhl-13-port/src/nhl13_app.h:78`); тосты, если нужны, создавать по событию и удалять | ~5 строк | Кадр выводится сразу из потока GPU: −(0…1) обновления монитора задержки, работает VRR, меньше рывков. Подробно — (г) |
| Клавиша полноэкранного режима | `rex::ui::RegisterBind("bind_fullscreen", "F11", …)` → `SetFlagByName("fullscreen", …)` (колбэк в nightly уже есть) | ~10 строк | Удобство; Alt+Enter от DXGI SDK отключил (`ui/d3d12/d3d12_presenter.cpp:427-431`) |
| FPS игры в F3 | `SetGuestFrameStats(…)` + счётчик `VdSwap` (импорт перехватывается, как `XamInput*` в `nhl13_input_lock.cpp`) | малая | Честный FPS игры (внешние счётчики считают Present'ы презентера — см. (г)) |
| Видеорежим гостя всегда 1280×720 | своя `__imp__VdQueryVideoMode` (как заглушки в `nhl13_imports.cpp`) | малая | Свободно задавать размер окна и `resolution` |
| Отдельный файл лаунчера | в `OnConfigurePaths` после чтения `nhl13.toml` поставить `paths.config_path = <exe>/nhl13.launcher.toml` | ~3 строки | SDK загрузит его последним (перекроет `nhl13.toml`), F4 «Save to config» будет писать туда — комментарии `nhl13.toml` целы |
| Своё меню графики | ImGui-диалог в `OnCreateDialogs` с короткой выборкой cvar'ов и сохранением в свой файл (как `renderer/core/nhl_overlay.cpp` + `nhl_settings.h` у Legacy) | средняя | Настройки в игре без опасной кнопки F4 |
| Твики движка | реестр EA: у Legacy 12 098 переменных `gXxx` и перечислитель `src/tunable_registry_dump.h` (`ref/nhl-legacy-recomp/docs/engine-settings-editor-plan.md`); в NHL 13 те же семейства: `gMomentumPhysicsModel`, `gAngularMomentumEnabled`, `gSpeedBoostForTopSpeed`, `gMaxSpeedPerc` | средняя | Геймплей, не графика: «вязкость» катания |
| FOV, ультраширокий экран | `gOverrideCameraFOV` + аспект; интерфейс рассчитан на 16:9 | средняя–высокая | 21:9 без полей |
| Разблокировать FPS | связь симуляции с vblank не выяснена: у нас игра ускоряется, NHL 14 без vsync играют, у Legacy без vsync «тормозит» Flash-меню | высокая, исход неизвестен | 120+ FPS без интерполяции сомнительны |
| Таймер Windows | `SetProcessInformation(ProcessPowerThrottling)` с `PROCESS_POWER_THROTTLING_IGNORE_TIMER_RESOLUTION` в ControlMask и 0 в StateMask: Win11 перестаёт соблюдать `timeBeginPeriod` у перекрытого или свёрнутого **и беззвучного** окна, а `Sleep(1)` — основа гостевого vblank (`graphics/graphics_system.cpp:169`, `core/threading_win.cpp:96-101`) | ~5 строк | Страховка для паузы/фона; к «≈20 FPS, когда поверх окна что-то открыто» относится, только если звук молчит — гипотеза |

### Пересборка SDK из исходников (сейчас — готовый nightly)

- **FSR1/CAS при выводе**: `-DREXGLUE_ENABLE_FIDELITYFX=ON -DREXGLUE_FIDELITYFX_BACKEND=dx12`
  (`CMakeLists.txt:23`, `cmake/rexglue_fidelityfx.cmake`). У Legacy сборка FidelityFX под
  clang/Ninja не пошла — собрали её отдельно генератором Visual Studio и подключили готовой DLL
  (`ref/nhl-legacy-recomp/docs/fidelityfx-enablement-notes.md`); `REX_HAS_FIDELITYFX_SDK` должен
  совпадать у SDK и игры (меняет раскладку `Presenter`). FSR2/3 для игры без векторов движения
  бессмысленны (SDK сам откатывается на пространственный). Сложность средняя–высокая плюс
  поддержка своей сборки SDK. Без сборки — шарпинг драйвера NVIDIA или ReShade поверх готового
  кадра.
- **Задержка и плавность**: `kQueueFrames` 3 → 2
  (`include/rex/graphics/d3d12/command_processor.h:223`), waitable swap chain, гостевой vblank от
  настоящего vblank монитора вместо таймера на `Sleep(1)` (`graphics/graphics_system.cpp:149-176`).
  Средняя.

### Свой рендерер

Как у UnleashedRecomp (свой рендер на Plume для D3D12/Vulkan вместо эмуляции Xenos) или
«high-cut/Plume» у Legacy (`ref/nhl-legacy-recomp/docs/highcut-*`). Месяцы работы — не наша цель.

### Как у соседей

| Проект | Подход | Графика и ввод |
|---|---|---|
| [UnleashedRecomp](https://github.com/hedge-dev/UnleashedRecomp) (Sonic Unleashed) | свой рендер (Plume), не эмуляция GPU | масштаб, MSAA выше оригинальных 2x, alpha-to-coverage, разрешение теней, DOF/motion blur, 60+ FPS, ультраширокий экран; против задержки — waitable swap chain и опрос ввода сразу после ожидания кадра |
| [Zelda 64 Recompiled](https://github.com/Zelda64Recomp/Zelda64Recomp) | рендер RT64 | любое соотношение сторон, высокий FPS интерполяцией («не влияет на геймплей») |
| NHL Legacy recomp (ReXGlue, `ref/nhl-legacy-recomp`) | пропатченный SDK + свой Vulkan-бэкенд | суперсэмплинг 1–2× (3× не дали: буфер > 4 ГБ на Vulkan → экипировка чёрная), FSR/CAS через свою сборку SDK, цветокор, мягкие тени; на D3D12 — 1× и окно 1920×1080 «ради нагрузки»; настройки — свой оверлей + `nhl_enhancements.ini` |
| [NHL 14 recomp](https://github.com/tpalko420-tech/nhl14-recomp) (ReXGlue) | D3D12 для меню, Vulkan для льда | `vsync=false` (иначе квантование до 22–23 FPS), `readback_resolve=some`; настройки — аргументами в `.bat` |

## (в) Как устроить лаунчер

Сделано для NHL Legacy 12.10.2026 — [launcher.md](launcher.md): механизм 1 (аргументы) плюс свой файл
`nhllegacy_launcher.toml`, который читает только лаунчер; порт не правился.

### Каким механизмом

1. **Аргументы командной строки — основной путь.** Сильнее `nhl13.toml`, файл не трогается,
   одна строка — вся конфигурация запуска. Правила: только `--имя=значение`; bool —
   `=true`/`=false`; пути с пробелами — в кавычках. Пример:
   `nhl13.exe --resolution_scale=2 --anisotropic_override=5 --d3d12_allow_variable_refresh_rate_and_tearing=false`.
2. **Файл лаунчера** — для постоянных настроек; нужна правка порта (таблица выше):
   `nhl13.launcher.toml` пишет лаунчер, `nhl13.toml` с комментариями — человек.
3. **`REX_*`** — для ярлыков и `.bat` (`set REX_RESOLUTION_SCALE=2`); по силе между CLI и toml.
4. **Править сам `nhl13.toml`** — только с сохранением комментариев (например, tomlkit) и не во
   время игры.
5. **На лету** канала из лаунчера в запущенную игру нет — только консоль и F4. При желании —
   именованный канал в порте → `SetFlagByName`.

### Что показать

| Раздел | Настройка | cvar | Значения в UI | Когда действует |
|---|---|---|---|---|
| Экран | Полноэкранный режим | `fullscreen` | вкл/выкл | сразу (и из консоли) |
| | Монитор | `monitor` | список | сразу |
| | Разрывы / VRR | `d3d12_allow_variable_refresh_rate_and_tearing` | «VRR или минимум задержки» / «без разрывов» | перезапуск |
| | Сохранять 16:9 | `present_letterbox` | вкл/выкл | сразу |
| Качество | Внутреннее разрешение | `resolution_scale` | ×1 (720p), ×2 (1440p), ×3 (2160p) | перезапуск |
| | Анизотропия | `anisotropic_override` | выкл = 0, 2x = 2, 4x = 3, 8x = 4, 16x = 5 | сразу |
| | Чтение resolve | `readback_resolve` | some (по умолчанию; экипировку порт читает синхронно сам), full — точно, но медленно; fast не показывать (экипировку не лечит) | сразу |
| | Дизеринг | `present_dither` | вкл/выкл | перезапуск |
| Эксперименты | Путь рендера | `render_target_path_d3d12` | ROV / RTV, с предупреждением «если матч чёрный — верните ROV» | перезапуск |
| Ввод | Бэкенд, вибрация, доп. мёртвые зоны | `input_backend`, `vibration`, `*_stick_deadzone_percentage` | | перезапуск / сразу |
| Звук | Буфер | `audio_maxqframes` | 8 / 12 / 16 | перезапуск |
| Игра (порт) | Сезон, НХЛ на 32 | `season_year`, `nhl_teams` | | перезапуск |

Не показывать: `vsync`, `video_mode_*`, `resolution`, `window_*` (в полноэкранном),
`protect_zero`, `gpu_allow_invalid_fetch_constants`, `gpu_plugin`; пути (`game_data_root`,
`user_data_root`) — только в отдельном разделе «Пути».

Пресеты: «Как на Xbox» (×1, AF 4x), «Чётко» (×2, AF 16x), «Максимум» (×3, AF 16x — только если
заработал RTV).

Правила лаунчера: проверять диапазоны сам (SDK молча игнорирует опечатки и отбрасывает
недопустимое с WARN); не трогать файлы при запущенном `nhl13.exe` (их всё равно читают только
при старте); «Сброс» = запуск без аргументов; после запуска показать из лога (`log_file`)
строки «Config: invalid value» и «reducing to». Для отладки — `--log_level=debug`: тогда в логе
видно каждое «Config: имя = значение» и «ignored, already set».

## (г) Задержка ввода

| Звено | Что происходит | Что можно сделать |
|---|---|---|
| Геймпад | DualSense по Bluetooth → DS4Windows (профиль x360: `BTPollRate=4`, мёртвые зоны 0) → виртуальный Xbox 360 → XInput | USB вместо BT; `BTPollRate` 1–2 (менять профиль — только с «да» пользователя); без сглаживаний и кривых |
| Опрос | `XamInputGetState` → `InputSystem::GetState` → сразу `XInputGetState`, без буфера (`input/input_system.cpp:215-245`, `input/xinput/xinput_input_driver.cpp:189-225`) | уже xinput. Нюанс: каждый опрос перечисляет устройства (`RefreshDevices`), пустые слоты опрашиваются раз в 1,1 с, «querying an empty slot costs milliseconds» (`xinput_input_driver.cpp:43-61`) — кандидат на кэш в порте, если будут микрорывки |
| Игра | поток симуляции + рендер (`NhlSimThread`, отложенные контексты) — 2–3 кадра, как на консоли; True Performance Skating — инерция задумана | Gameplay Sliders: Player Acceleration, Game Speed |
| Эмуляция GPU | при упоре в GPU до 3 кадров в очереди D3D12 (`kQueueFrames = 3`); `readback_resolve=full` — остановки и квантование 60 → 30 | держать запас GPU (масштаб), `some` |
| Вывод | всегда живой тост-диалог → вывод из UI-потока по тикам vblank монитора (ниже) | убрать тост (порт); F3/F4/консоль во время матча не держать открытыми |
| Swap chain | 3 буфера FLIP_DISCARD, `Present(0, RESTART \| ALLOW_TEARING)` — своей очереди нет (`ui/d3d12/d3d12_presenter.cpp:398-414, 1150-1160`) | VRR → флаг tearing true; без VRR — true (меньше задержка, разрывы) или false |
| Экран | — | полноэкранный режим без оверлеев поверх (Discord, GOG, Steam) — independent flip; на ТВ — «Игровой режим» |

**Тост-диалог и вывод кадра (по коду).** `ReXApp::LaunchModule` всегда создаёт тост достижений
(`ui/rex_app.cpp:72-78, 436-437`); любой `ImGuiDialog` регистрируется в конструкторе
(`ui/imgui_dialog.cpp:22`), и `ImGuiDrawer` становится UI-отрисовщиком презентера
(`ui/imgui_drawer.cpp:118-135`), а тост висит до выхода, даже пустой. Пока UI-отрисовщик есть,
презентер работает в режиме «рисует UI-поток по запросу» (`ui/presenter.cpp:1321-1328`), а
`ImGuiDrawer` после каждой отрисовки просит следующую (`ui/imgui_drawer.cpp:439-444`). UI-поток
перед каждой отрисовкой ждёт vblank монитора (`ui/presenter.cpp:484, 1579-1606`); новый кадр
игры лишь ставит флаг «срочно» (`ui/presenter.cpp:624-627, 1608-1613`), а уже идущее ожидание
он не будит. Итог: кадр игры показывается на ближайшем vblank монитора — плюс 0…16,7 мс на 60 Гц
(в среднем половина), гостевые 60 Гц «бьются» с частотой монитора (периодический пропуск или
дубль кадра), VRR подстраивается не под игру, а под тики. Без тоста режим становится «рисовать
сразу из потока GPU» (`ui/presenter.cpp:628-636`). Заодно: внешние счётчики FPS (оверлей
NVIDIA, Steam) считают Present'ы, а презентер с тостом перерисовывает и без новых кадров игры —
их цифра может не совпадать с FPS игры.

**Что попробовать без кода:** полноэкранный режим, xinput, `readback_resolve=some`, запас GPU
(масштаб не до упора), режим tearing под свой монитор, USB-кабель, ползунки Player Acceleration /
Game Speed, Game Mode на ТВ. **С кодом:** убрать тост (первым делом), счётчик FPS игры, при
желании — кэш перечисления XInput.

**Как мерить:** съёмка телефоном 240 к/с (палец на кнопке и экран в кадре) — до и после правки
тоста, в меню и в матче; в RelWithDebInfo — график времени кадра в F3 и `perf_log_csv=путь`
(покадровый CSV; в Release счётчики не собраны).

## (д) Рекомендуемый набор для RTX 3060

Шаг 1 — без риска (добавить в `nhl13.toml` или аргументами):

```toml
# Анизотропия 16x (по умолчанию в SDK 4x); меняется и на лету из консоли.
anisotropic_override = 5
# FXAA SDK не нужен: у игры своё FXAA поверх 2×MSAA (scrape/default.scrape).
swap_post_effect = "none"
# Полноэкранный режим без рамки (умолчание SDK, но лучше явно).
fullscreen = true
```

Шаг 2 — проверить на матче:

```toml
# Внутреннее разрешение ×2 (2560×1440). Оставить, если: 60 FPS без провалов до 30, загрузка GPU
# ниже ~85 %, формы и шлемы в порядке, в логе нет «swap source is unscaled».
resolution_scale = 2
# Если при ×2 щёлкает звук:
# audio_maxqframes = 12
```

Шаг 3 — по монитору: с G-SYNC/FreeSync — оставить `d3d12_allow_variable_refresh_rate_and_tearing`
по умолчанию (true) и включить G-SYNC для оконного и полноэкранного режимов; без VRR, если
мешают разрывы, — `false`.

Шаг 4 — эксперимент отдельным запуском: `render_target_path_d3d12 = "rtv"`. Рисует матч —
появляется запас под ×3 (4K-экран 1:1); чёрный экран — вернуть `"rov"`.

Шаг 5 — в коде порта: убрать тост-диалог, затем заново оценить задержку и выбор tearing.

По экрану: 1080p — ×2 даёт суперсэмплинг; 1440p — ×2 ровно 1:1; 4K — ×2 плюс билинейное
растяжение в 1,5 раза, ×3 только с RTV. Перед ×2 полезно посмотреть загрузку GPU на ×1: если
меньше ~25–30 %, ×2 с ROV, скорее всего, потянет.

Не трогать: `vsync`, `video_mode_*`, `resolution`, `window_*` при полноэкранном режиме,
`readback_resolve = "full"`, кнопку «Save to config» в F4.

## (е) Шлемы, перчатки, щитки: чтение resolve композиции (08.10.2026)

**Симптом.** С `readback_resolve = "some"` у части игроков шлем не тех цветов или прозрачный (видна
голова с волосами) — D3D12; на Vulkan — куски чужого шлема, серо-чёрные вставки. Свитера клубов
целы: их текстуры грузятся из `.rx2` готовыми.

**Причина** (по коду игры и SDK; в игре ещё не проверено). Шлем, перчатки и вратарскую амуницию
игра красит не в шейдере, как NHL 12, а собирает текстуры при загрузке — `CompositeOp`, машина
состояний `83328380` (её шагает `83328B78`; описания `composite_jersey`, `composite_font`,
`composite_onetemplate_decal`, `composite_threetemplates_decal`, `composite_centerlogo` —
`83311F80…833138B8`):

| Шаг | Что | Кто |
|---|---|---|
| 2 | шаблон зон (`helmet_0_<модель>_tm`, `glove_<модель>_<n>_tm`…) с цветами из базы рисуется в EDRAM; EndTiling-resolve `832B22A8` в `CompositeOp:TargetTexture` (A8R8G8B8, `0x18280186`) | GPU |
| 3 | ожидание забора (`EndTiling:AsyncOp`, опрос `832B0250`) | — |
| 4 | Linearizer, задание `82A6F368`: LockRect и распаковка тайлов из памяти TargetTexture в буфер | **процессор читает результат resolve** |
| 5–12 | `IMAGE::GAMMAEXPANDER`, `IMAGE::MIPMAPPER`, `IMAGE::GAMMACOMPRESSOR` | процессор |
| 13–14 | `IMAGE::DXTCOMPRESSOR` в итоговую текстуру | процессор |

TargetTexture одна на размер (кэш `83328220` по ширине, высоте и флагу, словарь `83AB8C70`), после
каждой композиции освобождается (`8331CDD8`, счётчик ссылок) и тут же выделяется снова — скорее
всего, по тому же адресу (видно по логу, см. «Проверка»), а длина resolve та же. Стадии 2–4
проходит одна композиция за раз (байт `83AB8C5C` ≤ 1).

SDK (`bd833a2`, D3D12 и Vulkan одинаково) делает resolve в свою копию памяти на GPU:
`MarkRangeAsResolved` (`bd833a2:src/graphics/pipeline/texture/cache.cpp:321`) сбрасывает текстуры
в диапазоне, помечает страницы «записаны GPU» и закрывает их от записи процессора
(`bd833a2:src/graphics/shared_memory.cpp:257-315`); запись процессора потом снова сбрасывает
GPU-копию, и текстура перечитывается из памяти гостя. Поэтому GPU всегда видит свежий resolve, а
память гостя — только то, что скопировал `readback_resolve` (`IssueCopy_ReadbackResolvePath`,
ключ — адрес + длина, два буфера на ключ, вытеснение после 60 кадров простоя,
`kReadbackBufferEvictionAgeFrames`):
- `full` — каждый resolve синхронно (ожидание GPU) — верно, но остановка на каждом resolve кадра;
- `fast` — каждый раз, но из буфера прошлого resolve с тем же ключом: композиция получает прошлую;
- `some` — только при «промахе» (второго буфера ещё нет: первый resolve ключа или после
  вытеснения), иначе ничего. Вторая и следующие композиции того же размера — попадание: Linearizer
  читает то, что лежало по адресу, — прошлую композицию (чужой шлем, другие цвета) или то, что
  процессор писал в этот блок, пока тот был свободен (куски, серо-чёрное, нулевая альфа →
  прозрачный шлем). Какие байты там окажутся, зависит от распределения памяти и времени — отсюда
  разная картина на D3D12 и Vulkan; ROV и FSI ни при чём: на GPU композиция верная в обоих;
- `none` — никогда.

То же у соседей: у NHL Legacy fast и some ломали шлемы и вратарскую амуницию
(`ref/nhl-legacy-recomp/docs/mt-command-recording-handoff.md`), у NHL 14 при some — «белый шлем,
оранжевые перчатки».

**Исправление — в порте, обе сборки** (`src/nhl13_composite.cpp`, подмены `832B22A8` и
`832B0250`). На входе в 832B22A8 (до записи пакетов resolve) `readback_resolve` ставится в `full`;
когда опрос 832B0250 увидел забор, — прежнее значение. Забор игра видит только после того, как
поток команд SDK выполнил resolve, а в режиме full он к этому моменту уже скопировал данные в
память гостя синхронно. Окно — около кадра на композицию, только пока собирается экипировка
(загрузка матча, меню с моделями игроков); остальное время — `some` из `nhl13.toml`, скорость
прежняя. Сторож: забор не увиден за 5 с — значение возвращается само (WARN `no fence seen` в
логе). Если значение за это время сменили из консоли или F4, оно не перетирается. Выключатель —
`nhl_composite_readback` (по умолчанию true, на лету). Кодоген и SDK не нужны.

Отвергнуто: `full` всегда (~25 FPS); `fast` (прошлая композиция); порог по размеру resolve, как у
NHL Legacy (≤ 3 МБ синхронно, нужен патч SDK): у нас каждый кадр идут resolve тех же размеров —
отражения 640×360 (0,9 МБ), блюр 320×184, SSAO — синхронизация каждый кадр; копия по первому
чтению процессора (страницы без доступа) — в SDK нет «data providers» (`xmemory.cpp`,
`EnableAccessCallbacks`: TODO), большая правка.

**Проверка в игре.** Матч или франшиза с разными командами и брендами шлемов; шлемы, перчатки и
щитки вратарей вблизи (повтор, заставка перед вбрасыванием), в D3D12 и в Vulkan. В логе
(`nhl-13-port/out/game-release.log`, `nhl-13-port/out/game-ffx.log`) при загрузке — до 6 строк
`[nhl13] composite readback #N: resolve …, texture … at 0x… WxH fmt 6; readback_resolve 'some' -> full`
и `… fenced after N ms, readback_resolve back to 'some'`; один и тот же адрес у разных N — та самая
переиспользуемая TargetTexture. Для сравнения — в консоли `nhl_composite_readback false` и
загрузить матч других команд (уже собранные текстуры игра может держать): артефакты должны
вернуться.

Тем же путём (`IMAGE::RESOLVER` + Linearizer, но старт `832B2410`) идут снимки экрана и фото
карточек игроков (`HockeyCardScreenshotProcedure`, `InstantReplayScreenshotProcedure`); с some они,
вероятно, тоже читают старые байты. Не тронуто: неизвестно, как часто они вызываются.

## Источники

- SDK: `ref/rexglue-sdk-src` (v0.10.0), бинарники `ref/rexglue-sdk-0.10.0.24/win-amd64/bin`,
  nightly `bd833a2` на GitHub ([релизы](https://github.com/rexglue/rexglue-sdk/releases),
  [сравнение с v0.10.0](https://github.com/rexglue/rexglue-sdk/compare/v0.10.0...bd833a2)).
- Игра: `game/extracted/big/boot/scrape/default.scrape`, `game/extracted/big/boot/attribdb/`,
  строки `game/extracted/xex/default.bin`; логи `nhl-13-port/out/game.log`, `nhl-13-port/out/game-release.log`.
- NHL Legacy recomp: `ref/nhl-legacy-recomp/src/nhllegacy_app.h`,
  `renderer/core/nhl_settings.h`, `docs/fidelityfx-enablement-notes.md`,
  `docs/engine-settings-editor-plan.md`.
- [NHL 14 recomp: getting-to-playable](https://github.com/tpalko420-tech/nhl14-recomp/blob/main/docs/port/getting-to-playable.md),
  `scripts/run-3d.bat`.
- [Xenia Canary: NHL 13 (4541099B), #1188](https://github.com/xenia-canary/game-compatibility/issues/1188) —
  playable, D3D12, `readback_resolve="full"` для форм.
- [UnleashedRecomp](https://github.com/hedge-dev/UnleashedRecomp),
  [Zelda 64 Recompiled](https://github.com/Zelda64Recomp/Zelda64Recomp).
- True Performance Skating: [EA](https://www.ea.com/news/true-performance-skating-deep-dive),
  [обзор GamesRadar](https://www.gamesradar.com/nhl-13-review); ползунки:
  [Operation Sports](https://www.osftw.com/Al_Tito13/blog/21295-altitos-nhl-13-sliders-set-explanation).
- Таймер Windows: [timeBeginPeriod](https://learn.microsoft.com/en-us/windows/win32/api/timeapi/nf-timeapi-timebeginperiod),
  [SetProcessInformation](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-setprocessinformation).
