# Порт: тулчейн и генерация кода

## Тулчейн (поставлен 07.10.2026, winget)

| Что | Версия | Где |
|---|---|---|
| Visual Studio 2022 Build Tools, нагрузка VCTools | 17.14.41 (MSVC 14.44, Windows SDK 10.0.26100) | `C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools` |
| LLVM / Clang | 23.1.3 | `C:\Program Files\LLVM\bin` |
| CMake | 4.4.4 | `C:\Program Files\CMake\bin` |
| Ninja | 1.13.2 | WinGet Packages, в PATH пользователя |
| Vulkan SDK | 1.4.363.0 | `C:\VulkanSDK\1.4.363.0` (`VULKAN_SDK`) |
| ReXGlue SDK | 0.10.0, готовая сборка win-amd64 | `ref/rexglue-sdk-0.10.0/win-amd64` (из релизов github.com/rexglue/rexglue-sdk) |

Вики SDK — клон в `ref/rexglue-sdk.wiki/`. Параметры CLI v0.10.0 отличаются от вики
(`init --project-name --xex-path --game-root --project-root`). На Windows по умолчанию
рендер D3D12, Vulkan — опция `REXGLUE_USE_VULKAN` (её использует Legacy-порт).

## Проект `port/`

Создан `rexglue init`; в git — `CMakeLists.txt`, пресеты, `nhl13_manifest.toml`, `src/`,
`generated/rexglue.cmake`. Сгенерированный код `port/generated/default/` (производное
от кода игры) и сборка `port/out/` — только локально.

```bash
cd port
../ref/rexglue-sdk-0.10.0/win-amd64/bin/rexglue.exe codegen nhl13_manifest.toml --force
```

## Первая генерация (07.10.2026, диск без TU)

- 10,5 минуты, 679 файлов, 359 МБ C++ (`nhl13_recomp.N.cpp`, функции
  `DEFINE_REX_FUNC(sub_XXXXXXXX)`, у каждой инструкции комментарий с исходным asm).
- 5 нераспознанных переходов (хвостовые `b` в код без записи в `.pdata`):
  `0x82E9F668` ← `0x82E9F724`; `0x82CB7858` ← `0x82CB7934`, `0x82CB7154`;
  `0x82AC44B0` ← `0x82AC45DC`; `0x82B08DC0` ← `0x82B34C84`. Лечатся записями
  `[functions]` в манифесте (как `nhllegacy_functions.toml` у Legacy).
- «Функция» `0x833824D0` размером 2,2 МБ — вероятно, ложная граница, проверить.

## Первый запуск до титульного экрана (07.10.2026)

SDK nightly 0.10.0.24, RelWithDebInfo, D3D12 (RTX 3060). Что понадобилось:

- `[[switch_tables]]` для 9 перечитываемых таблиц (`nhl13_switch_tables.toml`);
- 309 функций с только косвенными ссылками (`tools/find_indirect_targets.py`) и
  граница `0x832B9A70` (default switch за последним case);
- setjmp/longjmp `0x82C9D9B0` / `0x82C9BCB0`;
- заглушки `XUsbcamGetState`/`XUsbcamSetConfig` (нет в готовой rexruntime);
- монтирование `cache:` (`OnPostSetup`), пути из `nhl13.toml` (`OnConfigurePaths` —
  SDK читает конфиг после вычисления путей), плагин `xenos`, флаги `rov`,
  `readback_resolve=full`, `protect_zero=false`, `gpu_allow_invalid_fetch_constants`;
- отчёт о падении `nhl13_crash.txt` (dbghelp) — без него процесс умирал молча.

Итог: звук, геймпад, вступительный ролик VP6 с правильными цветами и титульный экран
«PRESS START». Запуск: `port/out/build/win-amd64-relwithdebinfo/nhl13.exe`
(`--log_file=…` по желанию). Снимок окна: `PrintWindow` с флагом 2 (полное
содержимое D3D12).

## Известные проблемы

- **Ввод**: гонка в `InputSystem::RefreshDevices` SDK (падение
  `std::_Destroy_range<DeviceInfo>` или повреждение кучи 0xC0000374 при нажатии
  кнопки в меню) — обход в `port/src/nhl13_input_lock.cpp`: XamInput* под общим
  мьютексом, оригиналы из DLL рантайма через `GetProcAddress` (модуль — по имени DLL).
  Бэкенд ввода — XInput (`input_backend`): с SDL шторм подключений DualSense/DS4Windows.
- **Видео и вертикальная синхронизация** (наблюдение пользователя 07.10.2026): ролики
  в развёрнутом окне сильно лагают; в превью Alt-Tab / на панели задач идут с нормальной
  скоростью, но с разрывами кадра (tearing). Похоже на синхронизацию кадров с vblank /
  презентацию. Варианты из ресерча: Legacy принудительно включает `vsync`, NHL 14
  выключает ради FPS — проверить, когда дойдём до игры.

## Дальше

1. Сборка: окружение vcvars64 + LLVM в PATH, пресет `win-amd64-*`.
2. По опыту Legacy: найти пару setjmp/longjmp EA CRT (`setjmp_address`/`longjmp_address`),
   иначе загрузка падает; недостающие функции и таблицы переходов.
3. Год: разметить 88 функций с 2011–2013 по сгенерированному коду, найти старт
   франшизы и «текущий год» «Играть сейчас»; правки — через Function Overrides /
   Mid-ASM Hooks SDK, не в сгенерированных файлах.
