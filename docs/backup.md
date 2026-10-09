# Резервные копии

Заведены после инцидента 09.10.2026 ([incident-2026-10-09.md](incident-2026-10-09.md)): всё,
что живёт только на S:, теперь копируется ещё и на D:.

## Код: зеркало git

- `D:\backup\git\megarohas_nhl13.git` — голый репозиторий, в основном он подключён как remote
  `backup`.
- `.git/hooks/post-commit` после каждого коммита отправляет туда все ветки и теги
  (`git push backup --all`, `--tags`). Без `--force` и без удаления веток: переписанная история
  не затрёт старую копию. Если D: недоступен, коммит всё равно проходит.
- Восстановление: `git clone D:/backup/git/megarohas_nhl13.git megarohas_nhl13`.
- Хук лежит в `.git/hooks` и в git не попадает. В новом клоне его ставят заново:

```sh
#!/bin/sh
git push --quiet backup --all >/dev/null 2>&1
git push --quiet backup --tags >/dev/null 2>&1
exit 0
```

## Данные вне git: `tools/backup_data.ps1`

```
powershell -NoProfile -ExecutionPolicy Bypass -File tools\backup_data.ps1
```

- **Что:** `game\work`, `game\userdata` (сейвы и кэш NHL 13), `best_of_nhl`,
  `legacy-port\userdata` (сейвы и CACHE Legacy), `legacy-port\dist`, `legacy-port\codegen`,
  сборки `legacy-port\out\build\win-amd64-release` и `legacy-port-aigm\out\build\win-amd64-release`,
  `port\generated`, `port\out`, `ref\rexglue-sdk-custom\install`.
- **Куда:** `D:\backup\megarohas_nhl13-data\` — те же относительные пути. Журналы лежат в `_logs\`,
  строка на каждый запуск — в `_logs\history.txt`.
- **Как:**
  - robocopy `/E /XJ` без `/MIR` и `/PURGE`: удалённое на S: в копии остаётся;
  - по junction и symlink копия не ходит;
  - не копируются venv, `__pycache__`, `CMakeFiles`, `*.obj`.
- **Сейвы** обеих игр дополнительно получают снимок на каждый день: `_saves\ГГГГММДД\…`. Общая
  копия обновляется, и испорченный сейв затёр бы её, а снимки прошлых дней остаются.
- **Файлы игр не копируются** (`game\other`, `game\raw`, `game\extracted`): их снимают с приставки
  заново ([xbox-transfer.md](xbox-transfer.md)), и на D: под них нет места.
- Старые снимки и журналы скрипт не удаляет: чистить их руками, когда место на D: понадобится.
