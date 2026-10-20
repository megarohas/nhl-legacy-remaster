# Инструменты

Это карта папки `tools/`. Файлы не переносятся: на их пути завязаны импорты (`tools/` в `sys.path`) и
`legacy_data/build-all.sh`. Поэтому здесь они разложены по группам только на бумаге. Документация —
[../docs/README.md](../docs/README.md).

- Запуск — из корня репозитория: `python tools/<имя>.py …`, пакеты — `python tools/roster …` или `cd tools && python -m fb.<модуль> …`. Команды и параметры описаны в начале каждого файла.
- Игра выбирается ключом `--game nhl13|legacy` или переменной `NHL_GAME`. По умолчанию — NHL 13, кроме инструментов `*_legacy.py`. Пути и константы обеих игр — в `gameprofile.py`.
- На входе — своя копия игры в `game/` (вне git), на выходе — `game/work/…`. В `cache:` порта и в сейвы пишут только установщики и команды с явным `--write`, и только при закрытой игре.
- Почти всё написано на стандартной библиотеке Python 3. numpy и Pillow (местами scipy и opencv) нужны `fb/`, `logos/`, `utah/`, `photos24.py`, `heads24.py`, `scans24.py`, `fepose.py`, `menu12_legacy.py`, `menuplayers.py` и `kitpicker/`. Для отрисовки SVG `teamart.py` запускает Chrome или Edge без окна, `music.py` нужен ffmpeg.

## Форматы файлов Xbox 360 и EA

- `svod.py` — контейнеры SVOD (установка с диска, Games on Demand): проверка и распаковка
- `stfs.py` — пакеты STFS: апдейты, сейвы и профили, DLC
- `xex.py` — `default.xex` (XEX2): расшифровка, разжатие в образ памяти, проверка хешей
- `lzx.py`, `aes.py` — LZX (порт lzxd) и AES-128 на чистом Python для `xex.py`
- `big.py` — архивы `.big` (BigEB v3, BIG4/BIGF): список и распаковка, весь диск — пулом процессов
- `unchunk.py` — разжатие файлов `chunkzip` / `chunklzx` из распакованных `.big`
- `tdb_read.py` — минимальная читалка баз EA TDB v6
- `tdb.py` — базы TDB v6 и сейвы RosterFile (NHL 12/13, Legacy — ZlibV4): запись полей, пересчёт CRC
- `locdb.py` — строки локализации `nhl_<язык>.db`: выгрузка, правка, проверка
- `gameprofile.py` — профиль игры для всех инструментов: пути, схема базы, номера строк лиг и арта
- `legacy_settings.py` — блок настроек в сейвах Legacy: разбор, сравнение, перенос слайдеров
- `rw4mesh.py` — сетки RenderWare 4 (`.rx2`) ⇄ OBJ: правка голени, проверки, превью
- `teamart.py` — арт клубов: логотипы интерфейса и 3D (центр льда, шайба, баннер) ⇄ PNG, сборка своих
- `playerhead.py` — портреты `p<artid>.big` ⇄ PNG, сборка новых
- `feapt.py` — ActionScript роликов интерфейса (Apt): дизассемблер, «декомпилятор», поиск, правка без изменения длины
- `aptc.py` — компилятор подмножества ActionScript в байткод Apt, если правкой той же длины не обойтись

## Конвейер модов-данных NHL Legacy: `legacy_data/`

`bash tools/legacy_data/build-all.sh [ЭТАП…] [--ahl32]` собирает весь набор с нуля в `game/work/legacy-data/out`
(дерево файлов как в `cache:`). Без списка этапов идут все по порядку. С `--ahl32` собирается ещё накладка «АХЛ на 32».
Подробно — [docs/legacy-data.md](../docs/legacy-data.md).

| № | Этап | Что делает | Чем |
|---|---|---|---|
| 1 | `base` | база на 32 клуба: SEA/VGK, дивизионы 8/8/8/8, календарь на 84 игры | `nhl32.py --game legacy` |
| 2 | `roster` | составы НХЛ 2026/27 из кэша: рейтинги, свободные агенты, тон кожи, Liiga | `roster all --offline …` |
| 3 | `photos` | портреты: фото не из НХЛ — в кадр НХЛ, сборка файлов, `hasportrait` | `roster photos`, `photos.py` |
| 4 | `equip` | экипировка по фото: обмотка, гетры, свитер, визор | `roster.equipment` |
| 5 | `collect` | в `out/`: база, `draft_roster.db`, схема, локализация, портреты; накладка `out-ahl32` | `draft_roster.py`, `make_out_ahl32.py` |
| 6 | `retire` | ушедшие из НХЛ игроки базы 2015 года остаются без клуба | `retire_veterans.py` |
| 7 | `fixdb` | последний бит записи таблицы освобождается под флаг движка «запись свободна» | `fix_flagbit.py` |
| 8 | `utah` | Юта вместо Аризоны, Тусон вместо Springfield | `utah.py`, арт — `tools/utah/` |
| 9 | `ahl` | составы АХЛ 2026/27 и свободные агенты | `ahl2026_slots.py`, `ahl2026.py` |
| 10 | `nhlattrs` | атрибуты игроков НХЛ под OVR базы (игра считает OVR из атрибутов) | `nhl_attrs.py` |
| 11 | `useredits` | правки экипировки, которые пользователь сделал в игре (из его сейва состава) | `user_equipment.py` |
| 12 | `tape` | обмотка крюка по списку и подписи вариантов в меню | `tape_players.py` |
| 13 | `contracts` | настоящие контракты 2026/27 и продления, переводы игроков в клубы | `contracts.py` |
| 14 | `goaliegear` | командная экипировка вратарей | `goalie_gear.py` |
| 15 | `photos24` | портреты из NHL 24 тем, у кого портрета нет | `photos24.py` |
| 16 | `heads` | типовые головы по фото | `heads24.py` |
| 17 | `scans24` | сканы голов NHL 24 игрокам с типовой головой | `scans24.py` |
| 18 | `fonts` | шрифт меню NHL 12 | `fefont.py --keep` |
| 19 | `music` | музыка Best of NHL | `music.py` |
| 20 | `models` | 3D: гетры, обмотка до носка, нижний край свитера | `models/build.sh` |
| 21 | `art` | арт SEA/VGK и фарм-клубов CV/HSK: логотипы, лёд, формы | `teamart.py`, `czkit.py`, `art/` |
| 22 | `logos` | логотипы клубов 2026/27 по манифесту | `logos/outcopy.py` |
| 23 | `menu` | главное меню NHL 12, пункты меню, доски драфта на 32, год 2026 в надписях | `menu12_legacy.py`, `menuitems_legacy.py`, `draft32_legacy.py`, `year2026_legacy.py` |
| 24 | `nhl24` | накладка `out-nhl24` из пакета NHL 24: формы, лёд, шлемы, клюшки, шайба | `nhl24.py` |

Каким-то этапам нужны внешние входы: кэш HockeyTech, дамп NHL 24, страницы контрактов, спецификация Юты. Если входа
нет, этап пропускается с сообщением.

Рядом со сборкой:
- `install-legacy-data.sh`, `uninstall-legacy-data.sh` (работает `install_legacy_data.py`) — ставят набор в `cache:` порта и снимают его, только при закрытой игре
- `save_sync_ratings.py` — переносит атрибуты из базы в сохранённый состав (сейв ROSTER) после установки
- `draft_roster.py` — собирает `db/draft_roster.db` для старта «NHL Entry Draft» из 10 таблиц нашей базы
- `registry_from_db.py` — восстанавливает таблицу `artid` конвейера по готовой базе
- `restore_big.py` — сверяет распакованные архивы Legacy с диском и дораспаковывает недостающее
- `models/check.sh`, `models/preview.sh`, `art/scripts/` — проверки и листы превью
- данные этапов: `goalie_gear.json`, `heads_legacy.json`, `tape_players.json`, `nhl24_kits.json`, `nhl24_helmets.json`, `menu/menu12-rings.json`, `art/src/*.json`
- `ahl_age_explore.py` — отменённая наработка (10.10.2026), в сборке не участвует

## Составы: `roster/`

`python tools/roster <этап> [--game legacy]`. Этапы идут в порядке fetch → build → lines → match → write → report,
`all` запускает их подряд. Подробно — [docs/roster-pipeline.md](../docs/roster-pipeline.md) и
[docs/roster-expansion.md](../docs/roster-expansion.md).

- `cli.py`, `__main__.py` — запуск этапов
- `fetch.py` — ответы источников (API НХЛ, EA NHL 27, nhlratings.net, Wikipedia, DailyFaceoff) в кэш `game/work/roster-cache/`
- `sources.py` — разбор ответов из кэша
- `build.py` — из кэша собирает нормализованный `players.json`
- `lines_real.py`, `lines.py` — звенья: реальные сочетания с DailyFaceoff, остальное достраивается по рейтингу
- `match.py` — сопоставляет игроков со строками базы
- `write.py` — записывает базу через `tdb.py`
- `report.py` — отчёты по составам и звеньям
- `ratings.py` — рейтинги NHL 27 → атрибуты игроков
- `statsrating.py` — рейтинг по статистике с поправкой на лигу (NHLe)
- `ovrformula.py` — точная формула OVR NHL Legacy из атрибутов
- `fa.py` — свободные агенты
- `skin.py` — тон кожи по официальному фото
- `league.py` — европейские лиги (Liiga)
- `ahl.py` — составы фарм-клубов АХЛ из Wikipedia
- `ahl_ht.py`, `ahl2026.py`, `ahl2026_write.py`, `ht_photos.py` — АХЛ 2026/27 из HockeyTech: клубы, составы, свободные агенты, портреты
- `photos_other.py` — фото не из НХЛ в кадр портретов НХЛ
- `equipment.py` — экипировка по фото
- `common.py`, `dbview.py`, `codes.py` — общее: пути и GET-запросы с кэшем, чтение базы, коды мест рождения

Рядом с конвейером:
- `nhl32.py` — НХЛ на 32 команды: Seattle и Vegas на пустых строках, дивизионы, календарь (`--ahl32` — и АХЛ на 32)
- `photos.py` — портреты НХЛ 2026/27: скачивание, сборка файлов, поле `hasportrait` в базе
- `payroll_report.py` — отчёт «контракты были → стали» между двумя базами, для переноса в сейв ROSTER

## Frostbite NHL 24: `fb/` и перенос в Legacy

Разбор своего дампа NHL 24 (PS4) — только для личного использования. Выгрузки лежат в `game/work/nhl24/`,
подробности — в [docs/frostbite-sources.md](../docs/frostbite-sources.md) (чтение дампа, новый источник — NHL 27 PS5)
и [docs/nhl24-uniforms.md](../docs/nhl24-uniforms.md).

- `source.py` — какой дамп читается: NHL 24 по умолчанию, другой — переменными `FB_GAME`, `FB_DATA`, `FB_PLATFORM` …
  (`python -m fb.source` — что видят инструменты)
- `probe.py` — первое знакомство с дампом: дерево, подписи, оглавления, блоки CAS, пробная распаковка, чанк из TOC
- `scan.py`, `toc.py`, `cas.py`, `bundle.py`, `dbobject.py` — чтение CAS, оглавлений и манифестов бандлов
- `catalog.py`, `orphans.py`, `verify.py` — сводка ресурсов, привязка бесхозных чанков, сверка sha1
- `extract.py`, `texture.py`, `meshset.py`, `lfs.py` — текстуры в PNG, сетки, legacy-файлы движка (базы, xml)
- `heads.py` — головы-сканы NHL 24
- `kit3d.py`, `kit_hybrid.py`, `kit_fix.py`, `kit_batch.py`, `kit_models.py`, `sleeve.py`, `relief.py`, `kit_rules.toml` — перенос свитеров на развёртку Legacy и правила нашивок
- `jersey_mesh.py`, `edge_kit.py` — сетка adidas в слоте стиля 0 и свитер Edge с передом ворота NHL 24 (MIN)
- `../kitport/` — **точка входа переноса форм**: `python -m kitport doctor | status | snapshot | build | diff | install | rollback | sheet | uvmap | params` (из `tools/`), руководство — [docs/kitport.md](../docs/kitport.md)
- `fonts.py`, `helmet.py`, `ice.py`, `stick_map.toml` — шрифты номеров, наклейки на шлем, центр льда, клюшки
- `gallery.py` — галерея всех комплектов NHL 24
- `pack.py`, `pilot.py` — упаковка в формат Legacy, пилот одного клуба
- `build_ooz.cmd`, `ooz_export.cpp` — сборка декомпрессора Oodle (ooz, GPL-3.0) для `cas.py`; исходников ooz в git нет
- `../photos24.py`, `../heads24.py`, `../scans24.py` — портреты, типовые головы и сканы голов NHL 24 для Legacy (этапы `build-all.sh`)
- `../kitpicker/build.py` — локальная страница выбора форм

## Формы, экипировка, арт клубов

- `kitpaint.py` — своя форма из шаблонного комплекта EA: разбор по слоям, сборка `.rx2`/`.big`, перекраска по зонам
- `czkit.py` — форма из элементов конструктора формы (`cz*`) для обычного пути формы
- `fepose.py` — превью формы в меню в позе EA
- `jersey10.py` — нижний край свитера сзади как в NHL 10
- `sticktape.py` — обмотка клюшки до носка крюка
- `tapestyles.py` — варианты частичной обмотки (коды 3, 4, 6, 8, 9)
- `newteams_art.py` — номера арта, прожекторы и арены новых клубов в базе (по умолчанию только показывает план)
- `logos/` — логотипы 2026/27. `fetch_nhl.py` скачивает официальные SVG НХЛ, `build.py` собирает наборы интерфейса. `svgclean.py`, `svgdiff.py`, `svgpaths.py` и `pngmarks.py` убирают знаки ®/™, `eafocus.py` подгоняет кадр под EA, `sheets.py` рисует листы на проверку, `outcopy.py` копирует результат в набор. Список клубов — `clubs.json`, `clubs_ahl.json`
- `utah/` — Utah Mammoth и Tucson Roadrunners. `build.sh` собирает весь арт (логотипы, шрифт номеров, формы, центр льда, наклейку на шлем, мелкий арт меню) и спецификацию для этапа `utah`

## Интерфейс, меню, шрифты, музыка

- `fefont.py` — шрифты интерфейса: свой TTF/OTF по метрикам шрифта игры или шрифт как есть (`--keep`)
- `febg.py` — фон меню: разбор, перекраска, превью
- `menu12_legacy.py` — главное меню NHL 12 в Legacy
- `menuitems_legacy.py` — пункты меню Legacy: без онлайна, с EXIT
- `draft32_legacy.py` — доски драфта на 32 клуба (три колонки)
- `year2026_legacy.py` — 2026 вместо 2015 в надписях
- `menu12.py`, `menuplayers.py` — главное меню NHL 12 и игроки на его фоне в NHL 13; их функции использует `menu12_legacy.py`
- `music.py` — свой саундтрек: MP3/FLAC/WAV → банк музыки игры, названия и обложки EA Trax

## Порт: разведка кода, врезки, проверка в игре

- `xmatch.py` — сопоставление кода двух образов серии (NHL 13 → Legacy, NHL 12): функции и места врезок
- `genfn.py` — asm функции из сгенерированного кода порта
- `ppcdis.py` — мини-дизассемблер PowerPC по образу из `xex.py`
- `find_indirect_targets.py` — находит код, на который есть только косвенные ссылки и который ReXGlue не завёл как функцию (→ `*_functions.toml`)
- `year_hooks.py` — врезки сдвига года (→ `*_year_hooks.toml`)
- `team_hooks.py` — врезки «30 → 32» по спискам мест (→ `*_team_sites.toml` и `.cpp`)
- `stackpeek.py` — стек потока запущенного порта без остановки игры (`--process`)
- `gameshot.ps1` — проверка без геймпада: запуск сборки, снимок окна, нажатия клавиатурой (`-Game legacy`)
- `perfwatch.ps1` — пассивный замер GPU/CPU по потокам во время игры (`-ProcessName`)
- `backup_data.ps1` — резервная копия данных вне git на D: ([docs/backup.md](../docs/backup.md))

## Только NHL 13 (заморожено)

- `capdefs.py` — финансы франшизы NHL 13 (`capdefs.brk`); в Legacy потолок ставят переключатели порта `nhl_salary_*`
- `memscan.py` — поиск в гостевой памяти запущенного `nhl13.exe`
- `perf_ab.ps1` — A/B-запуски сборки NHL 13 (`port-ffx`) с разными вариантами рендера
