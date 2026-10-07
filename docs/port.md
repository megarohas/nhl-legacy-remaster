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

## Дальше

1. Сборка: окружение vcvars64 + LLVM в PATH, пресет `win-amd64-*`.
2. По опыту Legacy: найти пару setjmp/longjmp EA CRT (`setjmp_address`/`longjmp_address`),
   иначе загрузка падает; недостающие функции и таблицы переходов.
3. Год: разметить 88 функций с 2011–2013 по сгенерированному коду, найти старт
   франшизы и «текущий год» «Играть сейчас»; правки — через Function Overrides /
   Mid-ASM Hooks SDK, не в сгенерированных файлах.
