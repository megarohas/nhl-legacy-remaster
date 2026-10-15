# Ресерч: соседние рекомпилы (07.10.2026)

Сводка отчёта агента-исследователя. Отмечено, что проверено (код, issue, байты образа),
а что — предположение.

## Проекты

| Проект | Что полезного |
|---|---|
| [tpalko420-tech/nhl14-recomp](https://github.com/tpalko420-tech/nhl14-recomp) (ReXGlue 0.9.0, играбелен, включая Be a GM) | скрипты `tools/find_setjmp_longjmp.py`, `find_truncated_functions.py`, `find_unclaimed_gaps.py`; `docs/port/*` — загрузка, сбор незарегистрированных целей, разборы падений; `docs/formats/{big-archives, chunklzx, eb-name-table, big-archive-patching, t3db}.md`; `docs/research/dating-a-save.md` |
| [puckhead73/nhl-legacy-recomp](https://github.com/puckhead73/nhl-legacy-recomp) | `docs/nhl12-decomp-reference/` — заметки NHL 12: `quirks/gotchas.md`, `jump_tables.md`, `tools/ea_jumptables.py` |
| [Wndwsqrrl/3on3NHL-recomp](https://github.com/Wndwsqrrl/3on3NHL-recomp) (EA Canada 2009) | патчи SDK: гонка в InputSystem (зависание после Start), `vpk` unsigned alias |
| [furqanagwan/nhl](https://github.com/furqanagwan/nhl), форк SDK [furqanagwan/rexglue-sdk](https://github.com/furqanagwan/rexglue-sdk) | NHL Legacy на D3D12/GDK; issue #160 (XUsbcam), #182 (RTV — матч чёрный) |
| [mchughalex/skate3recomp](https://github.com/mchughalex/skate3recomp), форк SDK [rexglue-skate3](https://github.com/mchughalex/rexglue-skate3) (ветка `skate3-sdk-clean`, `73259922`) | `classifyTarget` по выводимой функции — общее решение «undeclared label»; ~1740 `{ end = … }`; `patched_file_path` для .xexp — только в их форке |
| [florinp93/hells-gate-recomp](https://github.com/florinp93/hells-gate-recomp) (Dante's Inferno, EA) | `docs/vp6_fmv_corruption_fix.md` — зелёное VP6, тот же `vpkuwus128` |
| [StevensND/nfsmw-nx](https://github.com/StevensND/nfsmw-nx) | `*_as_local` + `share_registers` для скорости; ключи верхнего уровня TOML — выше `[functions]` |
| [xdzleo/rexglue-sdk](https://github.com/xdzleo/rexglue-sdk) | однокоммитные ветки поверх v0.10.0: `codegen-jumptable-landing-in-emitting-fn`, `codegen-bdz-tail-call`, … (PR #434/#435 закрыты без слияния) |

Публичного рекомпила NHL 13 (4541099B) не найдено.

## Выводы, применённые в порте

- **Таблицы переходов** (проверено): автодетектор v0.10.0 и nightly перечитывает таблицы,
  у которых граница проверяется на копии индексного регистра. 9 таблиц —
  `nhl-13-port/nhl13_switch_tables.toml`; совет мейнтейнеров в #170/#129/#177 — ручные
  `[[switch_tables]]`. `max_jump_extension` в v0.10.0 только логируется; `parent` по сути
  не работает.
- **setjmp/longjmp** `0x82C9D9B0` / `0x82C9BCB0` подтверждены (18 stfd/std, 64 lvx128);
  у NHL 12 та же раскладка CRT.
- **XUsbcam***: `xboxkrnl_usbcam.cpp` закомментирован в сборке рантайма — заглушки в
  `nhl-13-port/src/nhl13_imports.cpp`.
- **cache:** — монтировать самим (`nhl-13-port/src/nhl13_app.h`).
- **Флаги**: `render_target_path_d3d12=rov`, `readback_resolve=full`, `protect_zero=false`,
  `gpu_allow_invalid_fetch_constants=true`, `vsync=true` (`nhl-13-port/nhl13.example.toml`).
- **SDK nightly 0.10.0.24**: PR #449 (VP6), `01ac2a3b` (перезапись файлов — сейвы),
  `ee20900e` (коды XAM content), `bd833a2a` (барьеры sync/lwsync/eieio).

## На будущее

- **База**: в NHL 14 незапакованный `cache:\db\nhlng.db` перекрывает копию из `.big`
  (проверено ими в игре) — самый дешёвый путь подмены базы.
- `.big` EB: оглавление по 16 байт, f4 = djb2(путь); целостность не проверяется; сжатие
  определяется по сигнатуре (`chunkunc`/`chunkzip`/`chunkref`/`chunklzx`) — несжатый файл
  можно класть вместо сжатого.
- После каждой генерации: `grep "outside function"` по сгенерированному коду и
  `find_truncated_functions.py` (у NHL 14 запись `[functions]` посреди живого кода дала
  голый `return` без эпилога — сдвиг стека).
- Импорты, на которых EA-игры молча выходят (NHL 12): `ExGetXConfigSetting`,
  `XexCheckExecutablePrivilege`, `XeCrypt*`.
- Возможное зависание после Start — патч 0001 из 3on3 (предположение).
- Функция `0x833824D0` (2,2 МБ) настоящая: длина в .pdata 0xEEB8.
- Xenia Canary: NHL 13 играбельна с `readback_resolve="full"`
  ([game-compatibility#1188](https://github.com/xenia-canary/game-compatibility/issues/1188)).
