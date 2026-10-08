# megarohas_nhl13

Личный нативный порт NHL 13 (Xbox 360, TitleID `4541099B`) на Windows по образцу
[nhl-legacy-recomp](https://github.com/puckhead73/nhl-legacy-recomp) (ReXGlue).
Главное — глубокая правка базы `nhlng.db`: составы, устройство лиг и текущий год,
чтобы возраст игроков был правильным. Геймплей вторичен.

Только для себя, без распространения. Файлы игры, сейвы и базы EA в репозиторий
не попадают: они лежат в `game/`, которая целиком в `.gitignore`. В git — только
скрипты и документация.

## Структура

| Путь | Что |
|---|---|
| [docs/briefing.md](docs/briefing.md) | Вводная: цель, что известно о базе, план |
| [docs/xbox-transfer.md](docs/xbox-transfer.md) | Как достать файлы с приставки |
| [docs/game-files.md](docs/game-files.md) | Что внутри игры, где база, как распаковать |
| [docs/year-and-date.md](docs/year-and-date.md) | Где живут текущий год и даты: сейвы, календари, код |
| [docs/save-editing.md](docs/save-editing.md) | Устройство сейва франшизы и как его править |
| [docs/port.md](docs/port.md) | Тулчейн порта, генерация кода ReXGlue, что дальше |
| [docs/research.md](docs/research.md) | Соседние рекомпилы (NHL 14, 3 on 3, Skate 3…) и что из них взято |
| [docs/modding.md](docs/modding.md) | Моды базы через cache: — игроки (nhlng.db) и названия (локализация) |
| [docs/music.md](docs/music.md) | Музыка: банк audio/music (EALayer3), EA Trax, как игра выбирает трек, замена саундтрека |
| [docs/team-editor.md](docs/team-editor.md) | Встроенный редактор команд: кто отсекает обычные команды, что ломает сохранение, вариант «форма-донор» |
| [docs/fe-fonts.md](docs/fe-fonts.md) | Шрифты интерфейса (TrueType в fe/ion/fonts): какой для чего, замена своим, шрифт меню NHL 12 |
| [docs/fe-background.md](docs/fe-background.md) | Фон меню (анимация Apt): синий → любой цвет, tools/febg.py |
| [docs/player-models.md](docs/player-models.md) | 3D-модели игроков: из чего собран игрок, детализации, формат сетки RW4, гетры (skatesocktuck) и правка голени, клюшка и обмотка до носка |
| [docs/player-equipment.md](docs/player-equipment.md) | Экипировка игроков по фото (НХЛ + Wikimedia Commons): обмотка клюшки, гетры, свитер, визор — поля базы и охват |
| [docs/teams.md](docs/teams.md) | Команды, лиги, ссылки на команду и календари в базе; НХЛ на 32 команды |
| [docs/graphics-settings.md](docs/graphics-settings.md) | Настройки графики порта: cvar'ы рантайма, апскейл, RTV/ROV, задержка ввода, лаунчер |
| `port/` | Проект порта ReXGlue (сгенерированный код — не в git) |
| [tools/svod.py](tools/svod.py) | Проверка и распаковка контейнеров SVOD (установка с диска, GoD) |
| [tools/stfs.py](tools/stfs.py) | Проверка и распаковка пакетов STFS (апдейты, сейвы) |
| [tools/xex.py](tools/xex.py) | Расшифровка и разжатие `default.xex` в образ памяти |
| [tools/lzx.py](tools/lzx.py), [tools/aes.py](tools/aes.py) | LZX (порт lzxd) и AES-128 на чистом Python |
| [tools/unchunk.py](tools/unchunk.py) | Разжатие EA `chunklzx` / `chunkzip` внутри `.big` |
| [tools/ppcdis.py](tools/ppcdis.py) | Мини-дизассемблер PowerPC для разведки по образу |
| [tools/tdb_read.py](tools/tdb_read.py) | Читалка баз EA TDB v6 (только чтение) |
| [tools/tdb.py](tools/tdb.py) | Запись полей TDB, пересчёт CRC базы и обёртки сейва |
| [tools/locdb.py](tools/locdb.py) | Строки локализации (Хаффман): выгрузка и правка |
| [tools/year_hooks.py](tools/year_hooks.py) | Поиск годов-констант в коде и врезки сдвига года для порта |
| [tools/nhl32.py](tools/nhl32.py) | НХЛ на 32 команды: перенос двух команд, дивизионы, календарь на 84 игры |
| [tools/febg.py](tools/febg.py) | Фон меню: разбор анимации интерфейса, перекраска, превью |
| [tools/fefont.py](tools/fefont.py) | Замена шрифтов интерфейса: свой TTF/OTF в «скелет» шрифта игры с теми же именами и метриками |
| [tools/music.py](tools/music.py) | Свой саундтрек: MP3/FLAC/WAV → банк музыки игры, названия и обложки EA Trax (через ffmpeg) |
| [tools/rw4mesh.py](tools/rw4mesh.py) | Сетки игроков RW4 ⇄ OBJ для Blender, правка голени гетр, проверка зазоров, превью |
| [tools/sticktape.py](tools/sticktape.py) | Обмотка клюшки до самого носка крюка и скругление носка: полевые и вратарские, обе руки, `_2`/`_4`, проверки, лист превью |
| `game/` | Локальные файлы игры, не в git |
| `ref/` | Клоны репозиториев puckhead73 для справки, не в git |

## Статус

- [x] Xbox 360 найден в сети, FTP Aurora отвечает
- [x] На приставке: установка с диска, апдейт TU2, сейвы (в т. ч. 4 франшизы)
- [x] На ПК: заголовок установки, TU2, сейвы
- [x] На ПК: данные установки `Data0000`–`Data0037` (5,92 ГБ, размеры сверены)
- [x] Распаковка SVOD с проверкой хешей: 20 файлов в `game/extracted/disc/` (`default.xex`, `.big`)
- [x] `nhlng.db` найдена (`cache.big` → `db/`), побайтово равна анкерной из nhl-modding-studio
- [x] Апдейт TU2 разобран: `default.xexp` + `patch.big` (интерфейс, сценарии; базы нет)
- [x] Стартовый год: в конфигах нет; год лиги — в сейве (`leaguestates`), но 2012 зашит в код ~88 функций
- [x] Возраст во франшизе считается от года лиги (подтвердил пользователь по своей франшизе 2017 года)
- [x] Правка сейвов: запись TDB с CRC, перехеширование STFS ([docs/save-editing.md](docs/save-editing.md))
- [x] Тулчейн порта: VS 2022 Build Tools, LLVM 23, CMake, Ninja, Vulkan SDK, ReXGlue SDK 0.10.0
- [x] Порт: первая генерация кода ReXGlue (679 файлов, 5 нераспознанных переходов) — [docs/port.md](docs/port.md)
- [x] Порт: сборка и запуск до титульного экрана (ролик VP6, звук, геймпад) — [docs/port.md](docs/port.md)
- [x] Порт: первый матч — меню, 3D, звук, геймпад; 2,5 периода и гол (07.10.2026)
- [x] Моды через cache: — `db/nhlng.db` (игроки) и `fe/loc/NHL_ENG_US.db` (названия команд) работают в порте — [docs/modding.md](docs/modding.md)
- [ ] Порт: производительность (Release/PGO, vsync и лаги роликов)
- [ ] НХЛ на 32 команды (Tappara и TPS вместо сборных Матча звёзд, календарь на 84 игры) — проверка в игре
- [x] Год: `season_year` сдвигает «сейчас» игры — возраст в «Играть сейчас» и новая франшиза
  2026/27 проверены в игре (07.10.2026) — [docs/year-and-date.md](docs/year-and-date.md)
