# Варианты сборки порта NHL 13 (архив)

До 15.10.2026 рядом с `port/` жили две локальные копии (не в git): `port-ffx/` — сборка против своего SDK
(Vulkan + FSR/CAS, docs/sdk-build.md) и `port-fr/` — копия для франшизы (docs/franchise-seasons.md). Их сборки и
копии кодогена удалены при уборке: файлов NHL 13 на диске нет с 09.10.2026, сборки не запускаются. Исходники
`src/` у копий были старее или равны `port/src`, поэтому здесь сохранено только то, чего в `port/` нет:

- `nhl13.ffx.toml` — настройки запуска варианта FFX;
- `CMakeLists.txt`, `build.cmd` — сборка против своего SDK (`CMakeLists.fr.txt`, `build.fr.cmd` — то же у `port-fr`);
- `scripts/build_port.cmd`, `scripts/codegen_check.*` — сборка и проверка кодогена NHL 13.

Скрипты сборки самого SDK и патчи 0001–0006 — в `legacy-port/scripts/` (общие с NHL Legacy). Для повторного
портирования NHL 13 нужно снова снять игру с приставки (docs/xbox-transfer.md) и сделать кодоген (docs/port.md).
