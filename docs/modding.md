# Моды базы через cache:

Игра сначала ищет файлы в разделе `cache:` (кэш жёсткого диска 360), и только потом —
внутри архивов `.big`. В порте `cache:` — папка `game/userdata/cache/guest/`
(`port/src/nhl13_app.h`, `user_data_root` в `nhl13.toml`). Положенный туда файл
заменяет копию из архива — перепаковывать `.big` не нужно.

Проверено 07.10.2026 в порте:

| Файл в cache: | Что в нём | Проверка |
|---|---|---|
| `db\nhlng.db` | основная база: игроки, команды, составы, рейтинги, календари | фамилия Кросби → «Megarohas» видна в игре |
| `fe\loc\NHL_ENG_US.db` | строки интерфейса на английском | «Pittsburgh Penguins®» → «Megarohas Penguins» видно при выборе команды |

По логу игра ищет и другие файлы: `fe\ion\…\*.big`, `audio\sfx\*.ast`, `shaders\*.fxo`,
`AttribDB\renddb.vlt` и т. д. — тот же механизм.

## Как править

Исходники — из распакованного `cache.big` (`game/extracted/big/cache/`, см.
[game-files.md](game-files.md)).

**Основная база** — `tools/tdb.py` (числа CLI-командой `set`, строки — из Python):

```python
import sys; sys.path.insert(0, 'tools')
from tdb import SaveFile, DEFAULT_META
from tdb_read import load_meta
s = SaveFile(open('game/extracted/big/cache/db/nhlng.db', 'rb').read(), load_meta(DEFAULT_META))
s.db.set_string('exhibitionplayerbiotable', 'lastname', 1189, 'Megarohas')  # Кросби
open('game/userdata/cache/guest/db/nhlng.db', 'wb').write(s.bytes())          # CRC пересчитываются
```

Строки в записях — фиксированной длины, UTF-8 (`firstname`/`lastname` — до 24 байт,
`exhibitionteams.fullname` — до 49).

**Локализация** — `tools/locdb.py`:

```bash
python tools/locdb.py dump game/extracted/big/cache/fe/loc/nhl_eng_us.db game/extracted/big/cache/fe/loc/nhl_eng_us-meta.xml Pittsburgh
python tools/locdb.py set  …/nhl_eng_us.db …/nhl_eng_us-meta.xml game/userdata/cache/guest/fe/loc/NHL_ENG_US.db "NHLTeamName_23=Megarohas Penguins" "NHLCityName_23=Megarohas"
```

Правка на месте: новый текст должен влезть в объём старого (сжатый Хаффманом) и
состоять из символов, которые уже есть в дереве. Пересборка пула для длинных строк —
позже.

## Названия команд

Номер команды в ключах = номер строки в `exhibitionteams` (`nhlng.db`). У
«Питтсбурга» (23, `PIT`): `NHLTeamName_23`, `NHLCityName_23`, `NHLCityName_PIT`,
`TEAMLINE1_PIT`, `TEAMLINE2_PIT`, `NICKLINE2_23`, `NICKLINE2_PIT`, `PITTSBURGH`, `Logo47`.
Поле `exhibitionteams.fullname` в `nhlng.db` интерфейс, судя по проверке, не показывает.

## Оговорки

- Сейвы франшизы несут свою копию базы (48 таблиц) — правки `nhlng.db` попадут в
  новые франшизы и «Играть сейчас», а не в уже начатые.
- Это файлы игры: держать только в `game/` (вне git).
