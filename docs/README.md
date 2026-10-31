# Документация

*Documentation is in Russian.* Это рабочие записи по ходу разборов: в каждой есть дата и пометки, что проверено в игре.
Здесь они собраны по темам, по одной строке на документ. Пометка **NHL 13, заморожено** значит, что документ только о
порте NHL 13 (`nhl-13-port/`) и больше не обновляется. Для NHL Legacy верно то, что написано в остальных разделах.

С чего начать:
- игроку — [legacy-port.md](legacy-port.md), раздел «Для друзей», и [launcher.md](launcher.md);
- моддеру — [legacy-data.md](legacy-data.md);
- разработчику порта — [legacy-port.md](legacy-port.md), раздел «Сборка», и [sdk-build.md](sdk-build.md).

Инструменты — по задачам: [tools-catalog.md](tools-catalog.md) (что запускать, насколько готово, план), по файлам — [../tools/README.md](../tools/README.md).

## Порт NHL Legacy

- [legacy-port.md](legacy-port.md) — свой порт NHL Legacy (`nhl-legacy-port/`): что работает, устройство, сборка, запуск, папка для друзей, год, франшиза на 32 клуба и разбор её падений, закрытое (предзаказ, маски, бусты — `nhl_unlock_*`)
- [launcher.md](launcher.md) — лаунчер `nhllegacy_launcher.exe`: перед запуском настраиваются графика и переключатели `nhl_*`
- [graphics-settings.md](graphics-settings.md) — графика порта: cvar'ы SDK, апскейл, ROV/RTV, задержка ввода, источники настроек и их приоритет
- [sdk-build.md](sdk-build.md) — своя сборка ReXGlue SDK (Vulkan, FSR 1 / CAS): скрипты `nhl-legacy-port/scripts/sdk_*`, патчи, восстановление с нуля
- [port.md](port.md) — тулчейн (VS 2022 Build Tools, LLVM, CMake, Ninja, Vulkan SDK, ReXGlue) и первая генерация кода (на NHL 13)
- [performance.md](performance.md) — производительность: замеры GPU/CPU, FSI против хостовых RT, холостой спин потока рендера (замеры на NHL 13, выводы о SDK общие)
- [legacy-port-feasibility.md](legacy-port-feasibility.md) — оценка 08.10.2026, с которой начался порт: что из NHL 13 переносится в Legacy и сколько это стоит

## Моды-данные и конвейер

- [legacy-data.md](legacy-data.md) — набор модов NHL Legacy через `cache:`: состав, этапы `build-all.sh`, установка и снятие, проверка в игре, подробности каждого этапа
- [modding.md](modding.md) — как устроены моды через `cache:`: файл оттуда главнее копии в архиве `.big` (проверено на NHL 13, в Legacy так же)
- [utah.md](utah.md) — Utah Mammoth вместо Arizona Coyotes и Tucson Roadrunners вместо Springfield Falcons: данные и арт
- [awards.md](awards.md) — история наград и Кубка Стэнли из NHL 27 (`tools/legacy_data/awards27.py`, этап `awards`): НХЛ 1994/95…2025/26, АХЛ и CHL, правки ошибок EA, как игра читает награды

## Формы, экипировка, логотипы

- [uniforms.md](uniforms.md) — как устроены формы (свитер, номера, гамаши, гетры, наклейка на шлем), как игра выбирает форму, конструктор `cz*`, формы SEA/VGK
- [import-from-ea.md](import-from-ea.md) — **импорт из новой EA NHL** (NHL 24, NHL 27 и дальше): одна точка входа `tools/eaimport.py` — составы лиг, статистика, портреты, головы, формы; порядок и как подключить новую игру
- [kitport.md](kitport.md) — **руководство по переносу форм** из новых EA NHL в Legacy и инструмент `tools/kitport`: подходы, устройство формы Legacy (развёртка, текстуры, номера, база), порядок работ, каталог параметров, проверки, установка и откат, грабли
- [kit-prune.md](kit-prune.md) — чистка форм: локальная страница со всеми формами в игре, галочка — оставить (`tools/kitpicker/prune.py`)
- [nhl24-uniforms.md](nhl24-uniforms.md) — формы NHL 24 → Legacy: модели свитеров, воротники, текстуры, правила переноса; журнал установок (§15.1)
- [nhl24-textures.md](nhl24-textures.md) — перенос текстур NHL 24 в Legacy: план по категориям
- [player-models.md](player-models.md) — 3D-модели игроков: формат RW4, гетры и голень, обмотка до носка крюка, нижний край свитера как в NHL 10
- [sticks.md](sticks.md) — клюшки из NHL 27 в слоты каталога Legacy (`tools/fb/sticks.py`, план `fb/stick_slots.toml`): перенос по модели, имена в редакторе, белая CCM в слоте D
- [skates.md](skates.md) — коньки из NHL 27 в 11 слотов каталога Legacy (`tools/fb/skates.py`, план `fb/skate_slots.toml`): перенос по 3D, рельеф и блик NHL 27, имена и превью в редакторе
- [player-equipment.md](player-equipment.md) — экипировка по фото (обмотка, гетры, свитер, визор): поля базы и охват
- [equipment27.md](equipment27.md) — экипировка игроков из NHL 27 (`tools/legacy_data/equipment27.py`, этап `equip27`): клюшка, коньки, шлем, краги, шорты, визор, обмотка, заправка — в базы, сейв ROSTER и франшизу; соответствия моделей, охват
- [logos-2026.md](logos-2026.md) — логотипы клубов НХЛ и АХЛ 2026/27 в Legacy: наборы интерфейса, этап `logos`
- [logos-arenas.md](logos-arenas.md) — логотипы, арены и лёд Seattle и Vegas: форматы и поля базы (разбор на NHL 13, арт потом перенесён в Legacy)
- [arenas.md](arenas.md) — арены NHL Legacy: модель чаши `stadium_<N>`, кресла `crowd_<N>.cwd` и их цвет, какая арена у какого клуба, перекраска кресел на 2026/27 (`tools/stadium.py`, рецепты `arena_seats.toml`); свои модели арен UTA/SEA/VGK — копии под новым номером (`stadium.py clone`, этап `legacy_data/arenas.py`, §9); арены NHL 27 — как собраны, насколько реальны, можно ли перенести (`tools/fb/arena27.py`, §8)

## Головы, лица, портреты

- [player-photos.md](player-photos.md) — портреты игроков: формат (Apt в BIGF, DXT5), замена на 2026/27, фото не из НХЛ
- [player-photos-nhl24.md](player-photos-nhl24.md) — портреты из NHL 24 игрокам без фото и типовые головы по фото (этапы `photos24` и `heads`)
- [heads-nhl24.md](heads-nhl24.md) — сканы голов NHL 24 и NHL 27 в Legacy: общая базовая сетка, глаза (v7, `headeyes.py`, `scans24.py check`), волосы под шлемом (`headhelmet.py`, `scans24.py helmet`), суставы лица (этап `scans24`)

## Составы, рейтинги, контракты

- [roster-pipeline.md](roster-pipeline.md) — конвейер `tools/roster`: составы НХЛ 2026/27 → `nhlng.db` (игроки, звенья, номера, рейтинги)
- [roster-expansion.md](roster-expansion.md) — что добавлено в конвейер: рейтинги по статистике, свободные агенты, тон кожи, европейские лиги, фото не из НХЛ
- [add-players.md](add-players.md) — **свои игроки** в базе Legacy по спекам JSON (`tools/legacy_data/add_players.py`, этап `players`): новые и правка, клуб, звенья, OVR, портрет
- [draft-pool.md](draft-pool.md) — пул драфта франшизы: откуда берётся класс, почему в нём составы CHL 2012 года, пенсия ветеранов

Контракты 2026/27 и точная формула OVR описаны в разделах больших документов: в [legacy-data.md](legacy-data.md) —
«Контракты 2026/27» и «OVR в игре — из атрибутов», в [legacy-port.md](legacy-port.md) — «OVR из атрибутов» и
«Продление контракта».

## Интерфейс, меню, шрифты, музыка

- [fe-menu-legacy.md](fe-menu-legacy.md) — главное меню NHL 12 в Legacy, пункты без онлайна и с EXIT, доски драфта на 32, год 2026 в надписях
- [fe-fonts.md](fe-fonts.md) — шрифты интерфейса: какой где используется, замена своим, шрифт меню NHL 12
- [fe-background.md](fe-background.md) — фон меню: формат роликов Apt и перекраска (`tools/febg.py`)
- [music.md](music.md) — музыка: банк `audio/music` (EALayer3), EA Trax, свой саундтрек (`tools/music.py`)

## Исследования и форматы

- [frostbite-sources.md](frostbite-sources.md) — дампы Frostbite: как читается NHL 24 (PS4), допущения форматов, выбор источника (`fb.source`), первое знакомство с новым дампом NHL 27 PS5 (`fb.probe`)
- [game-files.md](game-files.md) — что внутри игр (NHL 13, NHL 12, NHL 10, Legacy): архивы, база, распаковка
- [xbox-transfer.md](xbox-transfer.md) — как снять файлы и сейвы с приставки (FTP Aurora)
- [save-editing.md](save-editing.md) — устройство сейва франшизы и его правка: TDB, CRC, STFS
- [research.md](research.md) — соседние рекомпилы (NHL 14, 3 on 3, Skate 3…) и что из них взято
- [research-rosters-community.md](research-rosters-community.md) — что делает сообщество NHL 13/14/Legacy: составы, лиги, графика
- [research-data-sources.md](research-data-sources.md) — откуда брать данные для составов 2026/27: API НХЛ, контракты, рейтинги, другие лиги

## NHL 13 — история

С порта NHL 13 (`nhl-13-port/`) проект начался. Эти документы больше не обновляются.

- [briefing.md](briefing.md) — вводная 07.10.2026: цель, что известно о базе, план · NHL 13, заморожено
- [year-and-date.md](year-and-date.md) — где хранятся год и даты; для Legacy см. раздел «Год» в legacy-port.md · NHL 13, заморожено
- [teams.md](teams.md) — команды, лиги и календари в базе, НХЛ на 32 · NHL 13, заморожено
- [ahl32.md](ahl32.md) — АХЛ на 32 в коде NHL 13; для Legacy см. раздел «АХЛ на 32» в legacy-port.md · NHL 13, заморожено
- [franchise-seasons.md](franchise-seasons.md) — франшиза на 32 на много сезонов: потолок, контракты, календарь · NHL 13, заморожено
- [team-editor.md](team-editor.md) — встроенный редактор команд: что отсекает обычные команды и что ломает сохранение · NHL 13, заморожено
- [fe-menu.md](fe-menu.md) — главное меню NHL 12 в NHL 13; для Legacy см. fe-menu-legacy.md · NHL 13, заморожено
- [audit-2026-10-07.md](audit-2026-10-07.md) — аудит логов и слепков порта NHL 13 на 32 команды · NHL 13, заморожено
- [team32_sites.json](team32_sites.json), [ahl32_sites.json](ahl32_sites.json) — места врезок «30 → 32» для `tools/team_hooks.py` · NHL 13, заморожено

## Резервные копии и порядок работы

- [backup.md](backup.md) — резервные копии: зеркало git на D:, хуки `post-commit` и `pre-push` (что пускается на GitHub), `tools/backup_data.ps1`
- [incident-2026-10-09.md](incident-2026-10-09.md) — инцидент 09.10.2026: как пропали `game/`, `ref/` и `best_of_nhl/`, что изменили после него
- [../CLAUDE.md](../CLAUDE.md) — правила работы в репозитории для людей и агентов: никаких ссылок на данные, удаление только в Корзину, коммиты
- [../CHANGELOG.md](../CHANGELOG.md) — история версий, номер текущей — в [../VERSION](../VERSION)
