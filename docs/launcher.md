# Лаунчер NHL Legacy (legacy-port/launcher)

12.10.2026. Окно настроек перед запуском порта: графика и наши переключатели `nhl_*`, кнопки «Играть» и
«Сбросить». Свой exe на C++/Win32 (`nhllegacy_launcher.exe`, ~250 КБ, статический CRT, без DLL и установки) —
кладётся рядом с `nhllegacy.exe`, запуск двойным щелчком. Порт не менялся: работает с любой сборкой Release
(свой SDK), начиная с exe a1cb8f74.

## Как работает

- Читает `nhllegacy.toml` рядом (только чтение) и поверх — свой `nhllegacy_launcher.toml`.
- «Играть» сохраняет `nhllegacy_launcher.toml` и запускает `nhllegacy.exe --имя=значение …`. Аргументы
  командной строки сильнее `nhllegacy.toml` ([graphics-settings.md](graphics-settings.md), «Источники и
  приоритет», механизм 1 из «(в) Как устроить лаунчер»), сам `nhllegacy.toml` не меняется.
- «Сбросить» — значения как в `nhllegacy.toml` (как без лаунчера). Крестик окна тоже сохраняет выбор.
- Если `nhllegacy.exe` уже запущен, вторую копию не запускает. Без `nhllegacy.exe` рядом «Играть» недоступна.
- Подсказка к настройке — в панели внизу, при наведении мыши или фокусе.
- Запуск `nhllegacy.exe` напрямую (без лаунчера) идёт только по `nhllegacy.toml`.
- Кнопка «Save to config» в окне F4 игры впишет переданные аргументы в `nhllegacy.toml` (так было и до
  лаунчера).

## Настройки → cvar'ы

| Раздел | В окне | cvar'ы |
|---|---|---|
| Графика | Рендер: D3D12 — точный (ROV) / D3D12 — быстрый (RTV) / Vulkan | `gpu_backend`, `render_target_path_d3d12`, `execute_unclipped_draw_vs_on_cpu` (true только для RTV — без него матч чёрный), `render_target_path_vulkan = "fsi"` |
| | Разрешение ×1 (1280×720) / ×2 (2560×1440) | `resolution_scale` |
| | Вывод кадра: обычный / CAS / FSR 1 и ползунок «Резкость» 0–100 % | `present_effect`; FSR — `present_fsr_sharpness_reduction` = (100 − x) / 50, CAS — `present_cas_additional_sharpness` = x / 100 (у каждого режима своё значение) |
| | Анизотропия выкл. / 2x / 4x / 8x / 16x | `anisotropic_override` 0 / 2 / 3 / 4 / 5 |
| Экран | Полный экран (без него — окно 1280×720, растягивается мышью) | `fullscreen` |
| | Без разрывов кадра (V-Sync) | `d3d12_allow_variable_refresh_rate_and_tearing`, `vulkan_allow_present_mode_immediate` = false |
| Управление | Клавиатура как геймпад, вибрация | `mnk_mode`, `vibration` |
| Сезон и лига | Сезон 2015/16…2030/31 | `season_year` |
| | НХЛ на 32 и под ней: Сиэтл и Вегас в выборе команды, АХЛ на 32, ИИ-менеджеры, свободные агенты, фэнтези-драфт (без НХЛ на 32 — серые) | `nhl_teams` 30/32, `nhl_menu32`, `nhl_ahl_teams` 30/32, `nhl_aigm32`, `nhl_fa32`, `nhl_fd32` |
| | Класс драфта без переростков | `nhl_draftclass_age` |
| | Финансы новой франшизы, млн $ (0 — как на диске) | `nhl_salary_cap` / `_floor` / `_min` |
| Исправления | Пункт EXIT, страховка сима матча, страховка сима в «Стань профи» | `nhl_menu_exit`, `nhl_sim_guard`, `nhl_sim_guard_live` |

Чего нет и почему:
- частоты кадров и настоящего `vsync` порта: скорость игры привязана к гостевым 60 Гц, `vsync = false` её
  ускоряет; вместо него — «без разрывов» (флаги вывода кадра);
- размеров окна: `window_width`/`window_height` в этом SDK меняют и видеорежим гостя;
- ×3: в игре не проверено (на Vulkan масштаб ≤ 2);
- служебных `readback_resolve`, `nhl_composite_readback`, `nhl_fence_wait` и диагностики (`nhl_*trace`,
  `nhl_virtual_pad` …).

**В игре ещё не проверены:** FSR 1 / CAS, «без разрывов кадра», вибрация. Остальное — те же cvar'ы, что уже
стоят в `nhllegacy.toml` или проверялись агентами ([legacy-port.md](legacy-port.md)).

## Сборка

```bat
S:\Claude\megarohas_nhl13\legacy-port\launcher\build.cmd
```

MSVC из VS 2022 BuildTools, один файл `nhllegacy_launcher.cpp` → `legacy-port/out/launcher/nhllegacy_launcher.exe`
(не в git). Манифест Common Controls 6 — `#pragma comment(linker, …)` + `/MANIFEST:EMBED`, DPI — Per-Monitor V2
из кода; файлов `.rc`/`.manifest`/иконки нет.

Снимок окна без показа пользователю (окно за пределами экрана, без активации, PrintWindow → PNG):
`nhllegacy_launcher.exe --shot=путь.png [--shot-hint=N]` (N — номер подсказки, 0 = «Рендер»). Стенд —
копия лаунчера в `legacy-port/out/launcher/test/` рядом с копией `nhllegacy.toml`.

## У пользователя

С 12.10 — `legacy-port/out/build/win-amd64-release/nhllegacy_launcher.exe` рядом с его `nhllegacy.exe`. Ярлык
«NHL Legacy» на рабочем столе пока ведёт на `nhllegacy.exe`; перенаправить его на лаунчер — по слову
пользователя.
