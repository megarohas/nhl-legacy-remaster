# Своя сборка ReXGlue SDK: Vulkan + FSR 1 / CAS

07.10.2026. Порт NHL 13 собран против своей сборки SDK — того же коммита, что и ночная
`0.10.0.24-dev.gbd833a2`, но с Vulkan-бэкендом рядом с D3D12 и с FSR 1 / CAS при выводе
кадра. Всё лежит отдельно: SDK — в `ref/rexglue-sdk-custom/`, порт — в копии `port-ffx/`
(в `.gitignore`). `nhl-13-port/` и готовая ночная `ref/rexglue-sdk-0.10.0.24` не тронуты. Игра не
запускалась: сборка проверена по логам, экспортам, флагам компиляции и строкам DLL;
поведение в игре — на проверку.

**Скрипты и патчи в git (с 15.10.2026) — `nhl-legacy-port/scripts/`:** `sdk_build.cmd`, `sdk_fetch.ps1`,
`sdk_env.cmd` (бывший `env.cmd`), `sdk_gpu_build.cmd` и `sdk-patches/0001…0006`. Они собирают тот же SDK в
`ref/rexglue-sdk-custom/`; приоритет — `NHLLEG_NORMALPRIO=1` вместо `NHLFFX_NORMALPRIO=1`. Исходная копия —
`port-ffx/scripts/` (не в git): там патчи 0001…0004 и скрипты порта NHL 13 `build_port.cmd`, `codegen_check.*`.

## Восстановление с нуля (09.10.2026) — ~6 минут

После инцидента 09.10 ([incident-2026-10-09.md](incident-2026-10-09.md)) `ref/rexglue-sdk-custom`
поднялся неполным: в `install` 146 файлов из 1243 (только `include`, `licenses`, `lib/pkgconfig`; нет
`bin/rexglue.exe`, DLL, `*.lib`, `lib/cmake/rexglue`), в `src` 269 МБ из 720 (из `src/src` — 18 файлов).
`build.cmd` порта падал на «SDK not found», собрать SDK из этих остатков нельзя. Папка оставлена как
`ref/rexglue-sdk-custom-damaged` (не удалять без нужды: из неё сверялись уцелевшие файлы).

Восстановление — тем же `sdk_build.cmd` в новую пустую `ref/rexglue-sdk-custom` (свой клон с GitHub +
наши патчи из `sdk-patches/`), полный приоритет, 12 потоков. 09.10 запускалась копия из `port-ffx\scripts\`
(`NHLFFX_NORMALPRIO=1`, патчи 0001…0004); теперь то же делает копия в git, она накладывает 0001…0006:

```sh
# Git Bash; старую папку — переименовать, не удалять
cd /s/Claude/megarohas_nhl13
mv ref/rexglue-sdk-custom ref/rexglue-sdk-custom-damaged     # если она есть
NHLLEG_NORMALPRIO=1 JOBS=12 cmd //c 'S:\Claude\megarohas_nhl13\nhl-legacy-port\scripts\sdk_build.cmd all' > sdk_rebuild.log 2>&1
```

| Шаг (14:12:45 →) | Время | Что в логе |
|---|---|---|
| клон `development` (голова ветки всё ещё `bd833a2`, checkout не понадобился) + 20 сабмодулей `--depth 1` + 16 «материализованных» симлинков | 2 мин 10 с | `[sdk] sources ready: … (v0.10.0-24-gbd833a2)` |
| патчи 0001–0004 | 1 с | `[sdk] applied 000N-….patch` ×4 |
| configure (Ninja Multi-Config) | 1 мин 45 с | |
| сборка Release, 839 шагов, 0 ошибок, 859 предупреждений | 2 мин | `[838/839] Linking … rexglue.exe` |
| установка | 7 с | `EXIT 0` (14:18:45) |

Проверка, что SDK тот же, что был:

- `git -C ref/rexglue-sdk-custom/src status --short` — ровно 8 файлов `M` из патчей (`CMakeLists.txt`,
  `cmake/rexglue_fidelityfx.cmake`, `cmake/rexglue_install.cmake`, `src/system/CMakeLists.txt`,
  `src/ui/CMakeLists.txt`, `src/ui/rex_app.cpp`, `src/graphics/pipeline/shader/spirv_translator_fetch.cpp`,
  `include/rex/graphics/pipeline/shader/spirv_translator.h`) и `m` у `libmspack`/`o1heap` (симлинки).
- Уцелевшие в `-damaged` файлы, которые правят патчи (`CMakeLists.txt`, `src/system/CMakeLists.txt`,
  `src/ui/CMakeLists.txt`), побайтно совпали с новыми.
- Объёмы как 07.10: `src` 720 МБ, `build` 433 МБ, `install` 108 МБ (1243 файла).
- DLL против тех, что стояли в папке игры Legacy (собраны 08.10 прежним SDK): размеры те же;
  `rexgpu-xenos.dll` — секции `.text/.rdata/.data/.pdata` побайтно равны; `rexruntime.dll` —
  `.data/.pdata` равны, разница только в строке сборки `…-Release@20261009_1415` против `@20261007_2039`
  (457 байт `.rdata` — сдвиг строк, 11 байт `.text` — ссылки на них). Сверка:
  `llvm-objcopy --dump-section .text=a.bin X.dll NUL` для обеих и `cmp`.

Чтобы в следующий раз было ещё быстрее: `tools\backup_data.ps1` копирует `ref\rexglue-sdk-custom\install`
на `D:\backup\megarohas_nhl13-data\` — после него восстановление = копия обратно (минута). На 09.10
(14:20) копии SDK на D: ещё не было. Если пропадёт и `port-ffx/`, патчи есть в git —
`nhl-legacy-port/scripts/sdk-patches/` (с 15.10.2026), и целиком в приложении ниже.

Ночная `ref/rexglue-sdk-0.10.0.24` (её берёт `nhl-13-port/` NHL 13 и пресет `win-amd64-relwithdebinfo`) после
инцидента тоже неполная (129 файлов, нет `bin`/`lib`); цел её zip
`ref/rexglue-sdk-0.10.0.24-dev.gbd833a2-win-amd64.zip` (`unzip -t` без ошибок) — распаковать его заново.

## Главное

1. **Готовый exe:** `port-ffx/out/build/win-amd64-release/nhl13.exe` (Release, `-O3`), рядом
   `rexruntime.dll`, `rexgpu-xenos.dll` (D3D12 + Vulkan), `nhl13_snap.exe`, `nhl13.toml`.
   Других DLL не нужно: `vulkan-1.dll` SDK грузит из драйвера сам, `amd_fidelityfx_*.dll` для
   FSR 1 / CAS не нужны (п. 3).
2. **SDK — тот же коммит, что ночная:** `bd833a2` (ветка `development`), версия выходит
   ровно `0.10.0.24-dev.gbd833a2`, заголовки и кодоген совпадают. Свой `rexglue.exe` признал
   `generated/` актуальным («0 written … 1 module(s) up to date»): кодоген не понадобился.
   Контрольный полный прогон своим `rexglue.exe` (`codegen_check.cmd`) даёт тот же код:
   все 679 файлов `generated/default` побайтно совпали с эталоном (при подложенном
   `codegen.partition.json`, см. «Грабли», п. 5).
3. **FSR 1 и CAS — собственные шейдеры презентера SDK**, уже скомпилированные под D3D12 и под
   Vulkan (`src/ui/shaders/bytecode/d3d12_5_1/guest_output_ffx_*`,
   `src/ui/shaders/vulkan_spirv/guest_output_ffx_*`), константы считаются в
   `include/rex/ui/presenter.h`. Им нужен только макрос `REX_HAS_FIDELITYFX_SDK`. FidelityFX
   SDK (DLL `amd_fidelityfx_dx12/vk`) нужен лишь временным FSR 2/3 и только одному бэкенду за
   сборку — для NHL 13 без векторов движения это бесполезно. Поэтому сборка «spatial only»:
   FSR/CAS работают **и на D3D12, и на Vulkan**, рантайм FidelityFX не собирался.
4. **Выбора бэкенда в SDK не было** (`LoadGpuPlugin(name)` с `"any"` всегда берёт D3D12) —
   добавлен cvar **`gpu_backend`** = `any` | `d3d12` | `vulkan` (патч 0003).
5. Включение — закомментированные строки в конце `nhl13.toml` (шаблон
   `port-ffx/nhl13.ffx.toml`):
   ```toml
   gpu_backend = "vulkan"               # + render_target_path_vulkan = "fsi"
   present_effect = "fsr"               # bilinear | cas | fsr | fsr2 | fsr3
   present_fsr_sharpness_reduction = 0.2
   present_cas_additional_sharpness = 0.0
   ```
6. Четыре патча к SDK (`nhl-legacy-port/scripts/sdk-patches/`, исходно — `port-ffx/scripts/sdk-patches/`, полный дифф —
   в приложении):
   FidelityFX без рантайма + общий `REX_HAS_FIDELITYFX_SDK`; установка без записи в реестр
   CMake; `gpu_backend`; исправление чтения `exp_adjust` в SPIR-V (на Vulkan).
7. Сборка с нуля — ~11 минут: клон + сабмодули ~3 мин, configure ~2 мин, SDK (Release)
   ~2,5 мин, порт ~3,7 мин (8 потоков, пониженный приоритет).

## Раскладка

| Путь | Что |
|---|---|
| `ref/rexglue-sdk-custom/src/` | клон `github.com/rexglue/rexglue-sdk` на `bd833a2` + патчи (видны в `git status`), сабмодули — shallow |
| `ref/rexglue-sdk-custom/build/win-amd64/` | дерево сборки (Ninja Multi-Config) |
| `ref/rexglue-sdk-custom/src/out/win-amd64/Release/` | бинарники сборки (SDK пишет их внутрь исходников, `CMAKE_RUNTIME_OUTPUT_DIRECTORY`) |
| `ref/rexglue-sdk-custom/install/win-amd64/` | установка: раскладка как у ночного zip (`bin`, `lib`, `include`, `share/rexglue`, `lib/cmake/rexglue`) — только Release |
| `ref/rexglue-sdk-custom/*.log` | логи: `clone`, `submodules`, `configure`, `build-release`, `codegen-check` (и `codegen-check-unseeded` — прогон без эталонного partition) |
| `ref/rexglue-sdk-custom/cgcheck/` | рабочая папка проверки кодогена (можно удалить) |
| `port-ffx/` | копия `nhl-13-port/` без `out/` (с `generated/`), снята 07.10 в 20:28 — вместе с незакоммиченной правкой `src/nhl13_teams.cpp` |
| `port-ffx/scripts/` | скрипты (ниже) и `sdk-patches/0001…0004.patch` |
| `nhl-legacy-port/scripts/` | в git: `sdk_env.cmd`, `sdk_fetch.ps1`, `sdk_build.cmd`, `sdk_gpu_build.cmd`, `sdk-patches/0001…0006.patch` |
| `port-ffx/nhl13.ffx.toml` | шаблон `nhl13.toml` этой сборки |
| `port-ffx/build.cmd` | заменён обёрткой над `scripts\build_port.cmd` (исходный собирал бы против ночной) |
| `port-ffx/out/build/win-amd64-release/` | готовая сборка |

Объём: `src` 720 МБ, `build` 433 МБ, `install` 108 МБ.

## Версии

| Что | Версия |
|---|---|
| ReXGlue SDK | `bd833a2ab69d305f99ddf57418fc38ffec8af93d` (development, 01.10.2026, «feat(codegen): add sync fences for sync, lwsync, and eieio») = ночная `0.10.0.24-dev.gbd833a2`. `git describe --match v*` даёт `v0.10.0-24-gbd833a2`, нужен тег `v0.10.0` |
| Компилятор | clang 23.1.3 (`C:\Program Files\LLVM`); ночную CI собирает clang из choco |
| CMake / Ninja | 4.4.4 / 1.13.2 (winget) |
| MSVC-окружение | VS 2022 BuildTools 17.14 (`vcvars64`), MSVC 14.44.35207, Windows SDK 10.0.26100.0 |
| Vulkan | заголовки и VMA — сабмодули SDK (стек 1.4.357); установленный Vulkan SDK 1.4.363 сборке не нужен (только `vulkaninfoSDK.exe` для проверки GPU) |
| Python | 3.14.7 — его находит CMake glslang |
| Флаги | как у пресета `win-amd64` SDK: `-march=x86-64-v2`, C++23, Release `-O3 -DNDEBUG`; Tracy и perf-счётчики включены, но в Release вырезаны (как в ночной) |

## Как воспроизвести

Из `cmd` (или из Git Bash: `cmd //c 'S:\...\script.cmd аргументы'`). Скрипты сами
перезапускаются с приоритетом «ниже среднего» (`start /belownormal`; дочерние clang/ninja его
наследуют), параллельность — `JOBS` (по умолчанию 8 из 12 потоков).

Шаг 1 — скрипты из git (`nhl-legacy-port\scripts\`), шаги 2 и 3 — порт NHL 13, только в `port-ffx\scripts\`.
Порт Legacy после шага 1 собирается своим `nhl-legacy-port\build.cmd` ([legacy-port.md](legacy-port.md), «Сборка»).

```bat
:: 1. SDK: клон + сабмодули + патчи, configure, сборка Release, установка
S:\Claude\megarohas_nhl13\nhl-legacy-port\scripts\sdk_build.cmd
::    по шагам: sdk_build.cmd fetch | configure | build   (build = сборка + установка)
::    RelWithDebInfo для пресета win-amd64-relwithdebinfo: set SDK_CONFIGS=Release RelWithDebInfo
:: 2. Порт (пресет по умолчанию win-amd64-release), копирует nhl13.ffx.toml как nhl13.toml,
::    если его ещё нет в папке сборки
S:\Claude\megarohas_nhl13\port-ffx\scripts\build_port.cmd
:: 3. По желанию: свой rexglue.exe генерирует тот же код, что ночной? (~9 мин, приоритет idle;
::    код возврата 0 = все файлы generated\default совпали)
S:\Claude\megarohas_nhl13\port-ffx\scripts\codegen_check.cmd
```

| Скрипт | Что делает |
|---|---|
| `sdk_env.cmd` (в `port-ffx` — `env.cmd`) | пути (`SDKC`, `SDK_SRC`, `SDK_BUILD`, `SDK_PREFIX`, `SDK_PIN`), `vcvars64`, LLVM, CMake, Ninja — как `nhl-13-port/build.cmd` |
| `sdk_fetch.ps1` | клон ветки `development`, `checkout bd833a2`, теги (для версии), shallow-сабмодули без `moltenvk`/`catch2`, «материализация» симлинков git, `git apply` патчей (уже применённые пропускает). Идемпотентен |
| `sdk_build.cmd` | fetch → configure (те же переменные, что пресет `win-amd64` + опции ниже) → `cmake --build --config Release` → `cmake --install` |
| `build_port.cmd` | `cmake --preset … -DCMAKE_PREFIX_PATH=<свой SDK> -DCMAKE_FIND_USE_PACKAGE_REGISTRY=OFF`, сборка, `nhl13.toml` |
| `codegen_check.cmd/.ps1` | полный кодоген копии манифеста своим `rexglue.exe` в `cgcheck/` и сравнение всех файлов с `port-ffx/generated/default` по SHA-256 |

Опции configure сверх пресета: `-DREXGLUE_USE_D3D12=ON -DREXGLUE_USE_VULKAN=ON
-DREXGLUE_ENABLE_FIDELITYFX=ON -DREXGLUE_FIDELITYFX_BACKEND=none -DREXGLUE_REGISTER_PACKAGE=OFF`
(последние два значения добавлены патчами 0001 и 0002).

### Время (Ryzen 5 3600, 8 потоков, «ниже среднего»)

| Шаг | Время |
|---|---|
| клон SDK (ветка development) | 27 с |
| 20 сабмодулей, `--depth 1` | 2 мин 35 с |
| configure (Ninja Multi-Config) | 1 мин 57 с |
| SDK Release: сборка (839 шагов) + установка | 2 мин 21 с |
| port-ffx Release: 355 шагов, кодоген 0,5 с («up to date»), линковка exe 117 МБ | 3 мин 41 с |
| проверка кодогена (`codegen_check.cmd`, idle): полный кодоген + сравнение | 9 мин 10 с (из них кодоген 545 с) |

## Патчи к SDK

Все четыре — в `nhl-legacy-port/scripts/sdk-patches/` (в git; исходная копия — `port-ffx/scripts/sdk-patches/`),
полный дифф — в приложении. `sdk_fetch.ps1` накладывает по порядку все патчи своей папки: в git это 0001…0006,
следующие два — журнал memexport и гонка загрузки текстур ([legacy-port.md](legacy-port.md)), их cvar'ы по
умолчанию выключены.

| Патч | Файлы | Зачем |
|---|---|---|
| `0001-fidelityfx-spatial-only-public-define` | `cmake/rexglue_fidelityfx.cmake`, `CMakeLists.txt`, `src/ui/CMakeLists.txt`, `src/system/CMakeLists.txt` | Новое значение `REXGLUE_FIDELITYFX_BACKEND=none`: FSR 1 / CAS без скачивания и сборки FidelityFX SDK. `REX_HAS_FIDELITYFX_SDK=1` — для всего SDK (`add_compile_definitions`) и **PUBLIC** у `rexruntime`. В оригинале макрос был `PRIVATE` у `rexui`: `rexgpu-xenos` и игра (она сама компилирует `rex_app.cpp` и UI-заголовки) видели бы другую раскладку `Presenter` / `GuestOutputPaintConfig` — то же предупреждение у соседей (`ref/nhl-legacy-recomp/docs/fidelityfx-enablement-notes.md`) |
| `0002-install-optional-package-registry` | `cmake/rexglue_install.cmake` | `cmake --install` SDK пишет префикс в реестр пакетов CMake (`HKCU\Software\Kitware\CMake\Packages\rexglue`) — тогда любой проект без `CMAKE_PREFIX_PATH` мог бы молча найти свой SDK. Опция `REXGLUE_REGISTER_PACKAGE` (по умолчанию ON, как было), здесь OFF. Проверено: записи в реестре нет |
| `0003-gpu-backend-cvar` | `src/ui/rex_app.cpp` | cvar `gpu_backend` (`any` / `d3d12` / `vulkan`, init-only) → `LoadGpuPlugin(gpu_plugin, gpu_backend)`. `rex_app.cpp` компилируется в exe игры (ставится в `share/rexglue`), поэтому cvar регистрируется до чтения `nhl13.toml` |
| `0004-spirv-texture-exp-adjust-word3` | `src/graphics/pipeline/shader/spirv_translator_fetch.cpp`, `include/rex/graphics/pipeline/shader/spirv_translator.h` | Только Vulkan. Показатель `exp_adjust` выборки текстуры брался из слова 4 fetch-константы (там `lod_bias`, биты 12:21), а по `xenos.h` он в слове 3 (`dword_3 +13`) — так читает и DXBC-транслятор D3D12. Любая текстура с ненулевым LOD bias умножалась на мусорную степень двойки; у NHL Legacy на Vulkan из-за этого чернели имена и номера на свитерах (их фикс). Версия транслятора SPIR-V 12 → 13 — кэш шейдеров Vulkan пересоберётся |

Что сознательно **не** перенесено из патча соседей (`ref/nhl-legacy-recomp/sdk/`): их
FidelityFX-рантайм (prebuilt DLL), смягчение теней, `NHL_VK_READBACK_*`, фиксы VP6 и signed
BC5 (DXN) в Vulkan-кэше текстур — титульные или большие и непроверенные на NHL 13. Если
Vulkan покажет их симптомы (см. «Что проверить в игре»), начинать с них.

## FidelityFX: почему без `amd_fidelityfx_*.dll`

- `present_effect` разбирается в `src/ui/presenter.cpp:43-78` (bd833a2). С
  `REX_HAS_FIDELITYFX_SDK` допустимы `bilinear, cas, fsr, fsr2, fsr3` (в ночной — только
  `bilinear`). Цепочку проходов строит `Presenter::GetGuestOutputPaintFlow`
  (`presenter.cpp:1033-1148`): `fsr` — EASU до 2× по оси за проход (до
  `present_fsr_max_upsampling_passes`) + RCAS; если кадр игры не меньше окна — ветка CAS
  (резкость 1:1 или CAS с уменьшением); `cas` — CAS до 2×, дальше билинейно.
- Шейдеры этих проходов — готовые байткоды в дереве SDK, их используют и
  `D3D12Presenter` (`src/ui/d3d12/d3d12_presenter.cpp:42-49, 1272-1335, 1366-1405`), и
  `VulkanPresenter` (`src/ui/vulkan/vulkan_presenter.cpp:112-119, 2337-2421`). Константы
  (`CasSharpenConstants`, `FsrEasuConstants`, `FsrRcasConstants`) — `presenter.h:551-618`.
- `REX_HAS_FIDELITYFX_RUNTIME` (ffx-api: `ffxCreateContext/ffxDispatch`) нужен только
  временным `fsr2`/`fsr3`. Glue SDK собирает **один** рантайм — `amd_fidelityfx_dx12` или
  `_vk` (`REXGLUE_FIDELITYFX_BACKEND`); обе DLL экспортируют одни и те же имена, две в один
  `rexruntime.dll` не слинковать. Сам SDK пишет про этот путь «experimental… synthesized
  depth/motion inputs and may fall back to spatial FSR».
- В этой сборке `fsr2`/`fsr3` допустимы, но без рантайма это один проход EASU на весь масштаб
  + RCAS (хуже `fsr`) и WARN в логе. Пользоваться `fsr`.
- Если FSR 2/3 всё же понадобятся одному бэкенду — рецепт соседей:
  `ref/nhl-legacy-recomp/scripts/_ffx_dll_build.bat` (DLL генератором «Visual Studio 17 2022»,
  в короткой папке из-за MAX_PATH) + их патч `cmake/rexglue_fidelityfx.cmake`
  (`REXGLUE_FIDELITYFX_PREBUILT_DIR`) и `cmake/rexglue_install.cmake`; под clang/Ninja
  FidelityFX не собирается (`toolchain.cmake` ставит `CMAKE_GENERATOR_PLATFORM`, флаги MSVC,
  vswhere, пути PIX).

## Vulkan

- Что внутри: `rexgpu-xenos.dll` 6,4 МБ вместо 2,7 МБ (`VulkanGraphicsSystem`, транслятор
  SPIR-V, `VulkanRenderTargetCache`, `VulkanTextureCache`…), в `rexruntime.dll` — Vulkan-провайдер
  и презентер. Фабрика плагина (`src/graphics/plugin_main.cpp`): `any` → D3D12, если он
  вкомпилирован, иначе Vulkan; `d3d12` / `vulkan` — явно. В логе при неудаче — «requested
  backend '…' is not compiled into this plugin» или «Failed to load GPU plugin 'xenos'
  (backend '…')». Параметр `backend` у `rex::system::LoadGpuPlugin(name, backend = "any")`
  и поле `GpuCreateInfo::backend` в bd833a2 есть, но `ReXApp::SetupPresentation` его не
  передаёт — отсюда патч 0003. Без патча то же делается в порте: в `OnPreSetup(config)`
  `config.graphics = rex::system::LoadGpuPlugin("xenos", "vulkan");` (SDK тогда плагин
  повторно не грузит).
- **Путь EDRAM** — `render_target_path_vulkan` (init-only, `src/graphics/vulkan/render_target_cache.cpp:40, 203-237`):
  `"fsi"` — fragment shader interlock (аналог `rov`), `""` — хостовые render target'ы
  (аналог `rtv`; SDK сам уходит на fsi, если нет 16-битных форматов). У NHL Legacy с не-fsi
  матч на Vulkan был чёрным. RTX 3060 (драйвер 620.02) всё нужное для fsi умеет: по
  `vulkaninfoSDK` `fragmentShaderPixelInterlock` / `SampleInterlock`, `fragmentStoresAndAtomics`,
  `vertexPipelineStoresAndAtomics`, `sampleRateShading`, `standardSampleLocations` — true.
- `readback_resolve` общий: на Vulkan действует тот же `"some"` (`GetReadbackResolveMode`,
  `src/graphics/command_processor.cpp:172-182`; `vulkan_readback_resolve` — устаревший
  псевдоним, работает, только если `readback_resolve` не задан).
- **Масштаб ≤ 2.** Буфер scaled resolve = 512 МБ × масштаб² (`vulkan/texture_cache.cpp:2076`),
  `maxStorageBufferRange` у RTX 3060 = 4 ГБ − 1. При ×3 (4,5 ГБ) чтение resolve дальше 4 ГБ
  молча пропускается (`vulkan/command_processor.cpp:4517-4519`) — у Legacy так чернела
  экипировка. В логе на ×2 будет WARN «Vulkan draw resolution scaling is experimental».
- Вывод: `IMMEDIATE` → `MAILBOX` → `FIFO_RELAXED` → `FIFO` (`vulkan_presenter.cpp:1385-1404`);
  без разрывов — `vulkan_allow_present_mode_immediate = false` (будет mailbox).
  `d3d12_allow_variable_refresh_rate_and_tearing` на Vulkan не действует.
- Кэш: `game/userdata/cache/shaders/shareable/` общий с основной сборкой. `4541099B.xsh`
  (микрокод гостя) общий для бэкендов, пайплайны D3D12 (`*.rov.d3d12.xpso`) — тот же формат,
  что у ночной (тот же коммит); Vulkan заведёт свой файл и в первый запуск будет
  компилировать пайплайны (подвисания). Две сборки одновременно не запускать.

## Строки `nhl13.toml`

`port-ffx/out/build/win-amd64-release/nhl13.toml` — копия
`nhl-13-port/out/build/win-amd64-release/nhl13.toml` (игра, сейвы, кэш, `season_year`, `nhl_teams`,
`readback_resolve = "some"`, ROV — как там), лог — `S:/Claude/megarohas_nhl13/nhl-13-port/out/game-ffx.log`.
В конце — закомментированные блоки:

| Ключ | Значения (умолч.) | Когда | Смысл |
|---|---|---|---|
| `gpu_backend` | `any` / `d3d12` / `vulkan` (`any` = D3D12) | init-only | бэкенд в плагине (патч 0003; в ночной ключа нет — молча игнорируется) |
| `render_target_path_vulkan` | `""` / `fsi` (`""`) | init-only | путь EDRAM на Vulkan; ставить `fsi` |
| `vulkan_allow_present_mode_immediate` | bool (true) | перезапуск | false — без разрывов (mailbox) |
| `present_effect` | `bilinear` / `cas` / `fsr` / `fsr2` / `fsr3` (`bilinear`) | перезапуск | вывод кадра; в ночной допустим только `bilinear` |
| `present_fsr_sharpness_reduction` | 0.0–2.0 стопа (0.2) | перезапуск | RCAS: меньше — резче |
| `present_cas_additional_sharpness` | 0.0–1.0 (0.0) | перезапуск | доп. резкость CAS (`cas`, `fsr` без апскейла) |
| `present_fsr_max_upsampling_passes` | 1–4 (4) | перезапуск | предел проходов EASU |
| `present_fsr_quality_mode` | `auto` / `nativeaa` / `quality` / `balanced` / `performance` / `ultra_performance` (`auto`) | перезапуск | только `fsr2`/`fsr3` |
| `present_dither` | bool (false) | перезапуск | дизеринг последнего прохода (работает и с fsr/cas) |

Что получится на экране: окно 1080p или 1440p при `resolution_scale = 1` — `fsr` даёт один
проход EASU (1280×720 → окно) + RCAS; 4K — два прохода. При `resolution_scale = 2` кадр игры
2560×1440 (если вывод идёт из масштабированного resolve): на 1080p `fsr` = CAS с уменьшением,
на 1440p — CAS 1:1. Эффект ложится на весь кадр вместе с интерфейсом игры (оверлеи ImGui
рисуются поверх, без него).

## Грабли

1. **Симлинки git.** Git for Windows (`core.symlinks=false`) выкладывает 15 файлов
   `thirdparty/libmspack/cabextract/mspack/*` текстом «../../libmspack/mspack/lzxd.c» —
   сборка `mspack` падает. `sdk_fetch.ps1` копирует цели поверх (сабмодуль после этого
   «modified» — так и должно быть).
2. **Реестр пакетов CMake** — см. патч 0002; порт дополнительно собирается с
   `-DCMAKE_FIND_USE_PACKAGE_REGISTRY=OFF`.
3. **`REX_HAS_FIDELITYFX_SDK` PRIVATE** в оригинале — разъезд ABI (патч 0001). Проверено по
   `build/win-amd64/CMakeFiles/impl-Release.ninja` и `port-ffx/out/build/win-amd64-release/build.ninja`:
   `rexgpu-xenos`, `rexui`, `rexglue` и порт компилируются с `REX_HAS_D3D12=1
   REX_HAS_FIDELITYFX_SDK=1 REX_HAS_VULKAN=1`; в `rexglueTargets.cmake` у `rex::runtime` те же
   три макроса.
4. **Кодоген в новой папке сборки** запускается один раз (у Ninja нет записи в логе), но
   отпечаток (`generated/default/codegen.stamp`) считается по содержимому входов, имени файлов,
   «0.10.0-dev» и хешу шаблонов — совпал, ничего не перезаписано. Кодоген при каждом запуске
   переписывает `sdk_version` в `nhl13_manifest.toml` (тот же текст, новое время) — поэтому он
   «запускается» на каждой сборке. `generated/default/codegen.d` с абсолютными путями после
   первого запуска указывает уже на `port-ffx`.
5. **Разбиение функций по файлам «липкое»:** `codegen_writer.cpp` берёт прежний
   `generated/default/codegen.partition.json`. Кодоген в пустую папку раскладывает те же функции
   иначе: первый прогон проверки без эталонного partition дал 673 из 679 различающихся файлов,
   хотя тела всех 117 886 функций, набор объявлений и `nhl13_init/register/pch`, `sources.cmake`
   совпали — отличались только места `extern`-объявлений хуков (`Nhl13YearSub` и др.).
   `codegen_check.ps1` поэтому подкладывает эталонный `codegen.partition.json`. Вывод для порта:
   `generated/` не удалять без нужды — новая раскладка = пересборка всех 336 файлов.
6. **`port-ffx/build.cmd`** из копии собирал бы против ночной (`..\ref\rexglue-sdk-0.10.0.24`) —
   заменён обёрткой. Пресет `win-amd64-relwithdebinfo` требует SDK, собранного и в
   RelWithDebInfo (`SDK_CONFIGS`).
7. **Windows PowerShell 5.1:** `$PSScriptRoot` пуст в значениях параметров по умолчанию;
   stderr git под `ErrorActionPreference=Stop` превращается в ошибку; функция `Git`
   перекрывает `git.exe` (рекурсия). Всё учтено в `sdk_fetch.ps1`.
8. Батники — ASCII с CRLF; `.ps1` — ASCII (5.1 читает файлы без BOM в ANSI).
9. Предупреждения configure от glslang (`cmake_minimum_required`, CMP0148) и ~860
   предупреждений компиляции SDK — безвредны, ошибок 0.
10. MAX_PATH не мешал (`LongPathsEnabled=1`, FidelityFX не собирался — у соседей именно его
   сборка упиралась в 260 символов).

## Что проверить в игре

1. **D3D12 с текущими настройками** (как есть, `present_effect` закомментирован): должно быть
   неотличимо от `nhl-13-port/` Release — тот же коммит SDK, разница в clang 23 вместо CI и
   вкомпилированных FSR/Vulkan. Меню, матч, загрузка франшизы, сохранение. Презентер теперь
   при старте создаёт и корневые сигнатуры/пайплайны FSR/CAS; если они не создадутся, вывода
   не будет вовсе — в логе «D3D12Presenter: Failed to create … AMD FidelityFX …».
2. **FSR на D3D12:** `present_effect = "fsr"` — резкость льда, разметки, логотипов и мелкого
   текста меню; ореолы/пересвет на тонких линиях → `present_fsr_sharpness_reduction` 0.5–1.0
   или `cas`. Лог: нет «Config: invalid value for cvar».
3. **Vulkan:** `gpu_backend = "vulkan"`, `render_target_path_vulkan = "fsi"`, сначала
   `resolution_scale = 1`. Первый запуск — подвисания на компиляции. Смотреть: матч не чёрный;
   имена и номера на свитерах (патч 0004); цвета формы и экипировки, нет ли зелёных точек
   (у Legacy — signed BC5 / DXN); ролики VP6 (`fe/movies`: логотип EA, «new features») — не
   зелёные ли; тени, отражения на льду; скорость против D3D12 ROV (fsi упирается в
   перерисовку); переключение полноэкранного режима и Alt+Tab (пересоздание swap chain); F3/F4
   и консоль.
4. **Vulkan + `resolution_scale = 2`** — формы и шлемы; ×3 на Vulkan не ставить.
5. Лог (`nhl-13-port/out/game-ffx.log`): «Vulkan device properties and enabled features» (в списке
   должен быть `fragmentShaderPixelInterlock`), WARN `VulkanRenderTargetCache` (откат с fsi на
   хостовые RT), «Vulkan draw resolution scaling is experimental», ошибки `VulkanProvider` /
   `VulkanPresenter`.

## Приложение: патчи (дифф к `bd833a2`)

### 0001-fidelityfx-spatial-only-public-define.patch

```diff
diff --git a/CMakeLists.txt b/CMakeLists.txt
index c9dfc17..44becb4 100644
--- a/CMakeLists.txt
+++ b/CMakeLists.txt
@@ -256,6 +256,14 @@ add_compile_options(
 
 include_directories(${REXGLUE_ROOT}/include)
 
+# FSR / CAS presenter effects. REX_HAS_FIDELITYFX_SDK changes the layout of
+# Presenter and GuestOutputPaintConfig (include/rex/ui/presenter.h), so every
+# SDK target (rexruntime, rexgpu-xenos, rexglue) must agree on it; consumers get
+# it through rexruntime's PUBLIC definition (src/system/CMakeLists.txt).
+if(REXGLUE_ENABLE_FIDELITYFX)
+    add_compile_definitions(REX_HAS_FIDELITYFX_SDK=1)
+endif()
+
 add_subdirectory(src/core)
 add_subdirectory(src/filesystem)
 add_subdirectory(src/ui)
diff --git a/cmake/rexglue_fidelityfx.cmake b/cmake/rexglue_fidelityfx.cmake
index af35fa8..8f352ef 100644
--- a/cmake/rexglue_fidelityfx.cmake
+++ b/cmake/rexglue_fidelityfx.cmake
@@ -8,6 +8,25 @@ if(NOT REXGLUE_ENABLE_FIDELITYFX)
     return()
 endif()
 
+set(REXGLUE_FIDELITYFX_BACKEND "auto" CACHE STRING
+    "FidelityFX runtime backend to build (auto, vk, dx12; none = spatial FSR 1 / CAS only)")
+set_property(CACHE REXGLUE_FIDELITYFX_BACKEND PROPERTY STRINGS auto vk dx12 none)
+string(TOLOWER "${REXGLUE_FIDELITYFX_BACKEND}" _rexglue_fidelityfx_backend)
+
+# ── Spatial-only mode ────────────────────────────────────────────────────
+# FSR 1 (EASU + RCAS) and CAS at present time are the SDK's own presenter
+# shaders, prebuilt for both D3D12 and Vulkan (src/ui/shaders/bytecode/
+# d3d12_5_1, src/ui/shaders/vulkan_spirv), with constants computed in
+# include/rex/ui/presenter.h. They only need REX_HAS_FIDELITYFX_SDK. The
+# FidelityFX SDK (amd_fidelityfx_<backend>.dll, one backend per build) is used
+# only by the temporal FSR2/FSR3 path, so "none" skips fetching and building it.
+if(_rexglue_fidelityfx_backend STREQUAL "none")
+    message(STATUS
+        "FidelityFX: spatial only (FSR 1 / CAS presenter effects for every backend, "
+        "no ffx-api runtime, fsr2/fsr3 fall back to spatial)")
+    return()
+endif()
+
 # ── Dependency validation ────────────────────────────────────────────────
 if(NOT WIN32)
     find_package(Vulkan QUIET)
@@ -62,12 +81,6 @@ set(REXGLUE_FIDELITYFX_SOURCE_DIR "${fidelityfx_SOURCE_DIR}" CACHE INTERNAL
     "Root of the fetched FidelityFX SDK source tree")
 
 # ── Backend selection ────────────────────────────────────────────────────
-set(REXGLUE_FIDELITYFX_BACKEND "auto" CACHE STRING
-    "FidelityFX backend to build (auto, vk, dx12)")
-set_property(CACHE REXGLUE_FIDELITYFX_BACKEND PROPERTY STRINGS auto vk dx12)
-set(_rexglue_fidelityfx_backend "${REXGLUE_FIDELITYFX_BACKEND}")
-string(TOLOWER "${_rexglue_fidelityfx_backend}" _rexglue_fidelityfx_backend)
-
 if(_rexglue_fidelityfx_backend STREQUAL "auto")
     if(WIN32 AND REXGLUE_USE_D3D12)
         set(_rexglue_fidelityfx_backend "dx12")
@@ -95,7 +108,7 @@ elseif(_rexglue_fidelityfx_backend STREQUAL "")
 else()
     message(FATAL_ERROR
         "Invalid REXGLUE_FIDELITYFX_BACKEND='${REXGLUE_FIDELITYFX_BACKEND}' "
-        "(expected auto, vk, or dx12)")
+        "(expected auto, vk, dx12, or none)")
 endif()
 
 if(REXGLUE_USE_VULKAN AND REXGLUE_USE_D3D12)
diff --git a/src/system/CMakeLists.txt b/src/system/CMakeLists.txt
index 05979a3..e2e4e7f 100644
--- a/src/system/CMakeLists.txt
+++ b/src/system/CMakeLists.txt
@@ -126,3 +126,11 @@ if(REXGLUE_USE_VULKAN)
     )
     target_compile_definitions(rexruntime PUBLIC REX_HAS_VULKAN=1)
 endif()
+
+# PUBLIC on purpose: presenter.h changes the layout of Presenter and
+# GuestOutputPaintConfig under REX_HAS_FIDELITYFX_SDK, and the game compiles
+# rex_app.cpp and the UI headers itself, so it must see the same define as the
+# SDK binaries (see the root CMakeLists.txt).
+if(REXGLUE_ENABLE_FIDELITYFX)
+    target_compile_definitions(rexruntime PUBLIC REX_HAS_FIDELITYFX_SDK=1)
+endif()
diff --git a/src/ui/CMakeLists.txt b/src/ui/CMakeLists.txt
index 5bd3dc5..360e1df 100644
--- a/src/ui/CMakeLists.txt
+++ b/src/ui/CMakeLists.txt
@@ -116,12 +116,15 @@ target_link_libraries(rexui PUBLIC
 )
 target_link_libraries(rexui PRIVATE utf8cpp)
 
-if(REXGLUE_FIDELITYFX_SOURCE_DIR AND EXISTS "${REXGLUE_FIDELITYFX_SOURCE_DIR}/sdk/include")
+# REX_HAS_FIDELITYFX_SDK itself is defined for the whole SDK in the root
+# CMakeLists.txt (it is ABI-relevant). The FidelityFX SDK headers are only
+# needed by the ffx-api runtime path (temporal FSR2/FSR3).
+if(REXGLUE_ENABLE_FIDELITYFX AND REXGLUE_FIDELITYFX_SOURCE_DIR AND
+   EXISTS "${REXGLUE_FIDELITYFX_SOURCE_DIR}/sdk/include")
     target_include_directories(rexui PRIVATE
         "${REXGLUE_FIDELITYFX_SOURCE_DIR}/sdk/include"
         "${REXGLUE_FIDELITYFX_SOURCE_DIR}/ffx-api/include"
     )
-    target_compile_definitions(rexui PRIVATE REX_HAS_FIDELITYFX_SDK=1)
 endif()
 
 set(REXUI_HAS_FIDELITYFX_RUNTIME OFF)
```

### 0002-install-optional-package-registry.patch

```diff
diff --git a/cmake/rexglue_install.cmake b/cmake/rexglue_install.cmake
index a003313..c303480 100644
--- a/cmake/rexglue_install.cmake
+++ b/cmake/rexglue_install.cmake
@@ -150,6 +150,11 @@ install(EXPORT rexglueTargets
 #
 # Windows: HKCU\Software\Kitware\CMake\Packages\rexglue  (REG_SZ, value name = MD5 hash)
 # Unix:    ~/.cmake/packages/rexglue/<hash>               (file containing prefix path)
+#
+# REXGLUE_REGISTER_PACKAGE=OFF keeps a side-by-side custom SDK out of the
+# registry, so projects that do not pass CMAKE_PREFIX_PATH never pick it up.
+option(REXGLUE_REGISTER_PACKAGE "Register the install prefix in the CMake user package registry" ON)
+if(REXGLUE_REGISTER_PACKAGE)
 install(CODE [[
     # Normalize path casing on Windows before hashing to avoid duplicate entries
     if(CMAKE_HOST_WIN32)
@@ -174,3 +179,4 @@ install(CODE [[
     message(STATUS "Registered rexglue in CMake user package registry")
     message(STATUS "  -> ${CMAKE_INSTALL_PREFIX}")
 ]])
+endif()
```

### 0003-gpu-backend-cvar.patch

```diff
diff --git a/src/ui/rex_app.cpp b/src/ui/rex_app.cpp
index 9ff54e8..74f92a1 100644
--- a/src/ui/rex_app.cpp
+++ b/src/ui/rex_app.cpp
@@ -53,6 +53,14 @@ REXCVAR_DEFINE_STRING(gpu_plugin, "", "GPU",
                       "GPU emulation")
     .lifecycle(rex::cvar::Lifecycle::kInitOnly);
 
+// The plugin's factory (graphics/plugin_main.cpp) takes the backend name; "any"
+// picks D3D12 when it is compiled in, else Vulkan.
+REXCVAR_DEFINE_STRING(gpu_backend, "any", "GPU",
+                      "Graphics API inside the GPU plugin: any (D3D12 if compiled in, else "
+                      "Vulkan), d3d12, vulkan")
+    .allowed({"any", "d3d12", "vulkan"})
+    .lifecycle(rex::cvar::Lifecycle::kInitOnly);
+
 namespace rex {
 
 // --- ReXApp ---
@@ -312,11 +320,12 @@ bool ReXApp::SetupPresentation() {
   OnPreSetup(config_);
 
   if (!config_.graphics && !config_.gpu_plugin.empty()) {
-    config_.graphics = rex::system::LoadGpuPlugin(config_.gpu_plugin);
+    const std::string gpu_backend = REXCVAR_GET(gpu_backend);
+    config_.graphics = rex::system::LoadGpuPlugin(config_.gpu_plugin, gpu_backend);
     if (!config_.graphics) {
       // Fatal by design: no silent headless fallback.
-      auto msg =
-          fmt::format("Failed to load GPU plugin '{}'. See log for details.", config_.gpu_plugin);
+      auto msg = fmt::format("Failed to load GPU plugin '{}' (backend '{}'). See log for details.",
+                             config_.gpu_plugin, gpu_backend);
       REXLOG_ERROR("{}", msg);
       rex::ShowSimpleMessageBox(rex::SimpleMessageBoxType::Error, msg);
       return false;
```

### 0004-spirv-texture-exp-adjust-word3.patch

```diff
diff --git a/include/rex/graphics/pipeline/shader/spirv_translator.h b/include/rex/graphics/pipeline/shader/spirv_translator.h
index dce3dbf..df3cbfc 100644
--- a/include/rex/graphics/pipeline/shader/spirv_translator.h
+++ b/include/rex/graphics/pipeline/shader/spirv_translator.h
@@ -33,7 +33,8 @@ class SpirvShaderTranslator : public ShaderTranslator {
     // TODO(Triang3l): Change to 0xYYYYMMDD once it's out of the rapid
     // prototyping stage (easier to do small granular updates with an
     // incremental counter).
-    static constexpr uint32_t kVersion = 12;
+    // 13: texture fetch exp_adjust is read from fetch constant word 3, not 4.
+    static constexpr uint32_t kVersion = 13;
 
     enum class DepthStencilMode : uint32_t {
       kNoModifiers,
diff --git a/src/graphics/pipeline/shader/spirv_translator_fetch.cpp b/src/graphics/pipeline/shader/spirv_translator_fetch.cpp
index 9ce3bb4..daef849 100644
--- a/src/graphics/pipeline/shader/spirv_translator_fetch.cpp
+++ b/src/graphics/pipeline/shader/spirv_translator_fetch.cpp
@@ -2029,11 +2029,26 @@ void SpirvShaderTranslator::ProcessTextureFetchInstruction(
           }
         }
 
-        // Apply the exponent bias from the bits 13:18 of the fetch constant
-        // word 4.
+        // Apply the exponent bias (exp_adjust) from the bits 13:18 of the fetch
+        // constant word 3 (xenos.h: dword_3 +13; the DXBC translator reads word 3
+        // too). Word 4 bits 12:21 are lod_bias, so reading word 4 here scaled the
+        // result of any texture with a non-zero LOD bias (fix from the NHL Legacy
+        // recomp: black jersey names / numbers on Vulkan).
+        id_vector_temp_.clear();
+        id_vector_temp_.push_back(const_int_0_);
+        id_vector_temp_.push_back(
+            builder_->makeIntConstant(int((fetch_constant_word_0_index + 3) >> 2)));
+        id_vector_temp_.push_back(
+            builder_->makeIntConstant(int((fetch_constant_word_0_index + 3) & 3)));
+        spv::Id fetch_constant_word_3_signed = builder_->createUnaryOp(
+            spv::OpBitcast, type_int_,
+            builder_->createLoad(builder_->createAccessChain(spv::StorageClassUniform,
+                                                             uniform_fetch_constants_,
+                                                             id_vector_temp_),
+                                 spv::NoPrecision));
         spv::Id result_exponent_bias = builder_->createBinBuiltinCall(
             type_float_, ext_inst_glsl_std_450_, GLSLstd450Ldexp, const_float_1_,
-            builder_->createTriOp(spv::OpBitFieldSExtract, type_int_, fetch_constant_word_4_signed,
+            builder_->createTriOp(spv::OpBitFieldSExtract, type_int_, fetch_constant_word_3_signed,
                                   builder_->makeUintConstant(13), builder_->makeUintConstant(6)));
         {
           uint32_t result_remaining_components = used_result_nonzero_components;
```
