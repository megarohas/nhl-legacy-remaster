# Моды-данные NHL 13 → NHL Legacy (через cache:)

08.10.2026, агент legacy-data и его помощники (fe, music, models, art). Всё, что в NHL 13 ставится
файлами в `cache:` без правки кода игры, собрано для NHL Legacy Edition (Xbox 360, TitleID
`454109EC`) и проверено в своём порту Legacy (`legacy-port/`, агент legacy-port, D3D12 ROV). Оценка и
план — [legacy-port-feasibility.md](legacy-port-feasibility.md); порт — [legacy-port.md](legacy-port.md).

## Коротко

| Мод | Чем собран | В игре Legacy |
|---|---|---|
| 32 команды в базе: SEA/VGK на 30/31, сборные — 222/223, 8/8/8/8, календари 32 × 84 | `tools/nhl32.py --game legacy` | ✔ Play Now: Kraken и Golden Knights в списке НХЛ, матч SEA–VGK |
| АХЛ на 32 (CV/HSK на 224/225, 8/8/8/8, 32 × 72) — по просьбе legacy-port | `tools/nhl32.py --game legacy --ahl32` | база собрана; франшиза — с врезками legacy-port |
| Составы 2026/27 (рейтинги по статистике, свободные агенты, тон кожи, Liiga) | `tools/roster … --game legacy` | ✔ составы, звенья, номера, буквы, звёзды команд |
| Портреты игроков 2026/27 (НХЛ, Liiga) | `tools/photos.py --game legacy` | ✔ Starting Lineups — наши фото (McCann, Barbashev…) |
| Экипировка по фото (обмотка, гетры, свитер, визор) | `python -m roster.equipment --game legacy apply` | ✔ визор по правилу, обмотка (матч SEA–VGK) |
| Шрифт меню NHL 12 | `tools/fefont.py --game legacy` (помощник fe) | ✔ меню, выбор команд, составы, табло |
| Музыка Best of NHL (16 песен, названия, обложки) | `tools/music.py --game legacy` (помощник music) | ✔ EA SPORTS Trax — все 16 песен, играет наша |
| 3D: гетры, обмотка до носка (и у клюшек на льду), край свитера NHL 10 | `rw4mesh.py`, `sticktape.py`, `jersey10.py --game legacy` (помощник models) | ✔ файлы берутся из cache: (промахов нет); вблизи не разглядывали |
| Логотипы, лёд, шайба, баннер, прожекторы, форма SEA/VGK (арт 100/101) | `teamart.py`, `kitpaint.py`, `czkit.py --game legacy` (помощник art) | ✔ логотипы на выборе команд и заставке, форма в 3D, центр льда VGK |
| Фон меню | варианты на выбор (у Legacy своя тёмная арена) | не ставился — решает пользователь |
| Главное меню NHL 12 | только оценка (ждёт агента menu12) | — |

Набор — `game/work/legacy-data/out/` (дерево путей как в `cache:`); ставится при закрытой игре:

```bash
bash game/work/legacy-data/install-legacy-data.sh            # всё из out → cache: порта
bash game/work/legacy-data/install-legacy-data.sh db fe/loc  # только части (начало пути)
bash game/work/legacy-data/install-legacy-data.sh @game/work/legacy-data/models/files.txt   # по списку
bash game/work/legacy-data/uninstall-legacy-data.sh          # снять (чужие файлы вернутся из backup/)
```

Папка `cache:` порта — строка «CACHE: …» в `game/work/status/legacy-port.md` (сейчас
`legacy-port/userdata/cache/guest`) или переменная `CACHE`. Работает `install_legacy_data.py` рядом
(2500 файлов — секунды); список поставленного — `installed.txt`, прежние чужие файлы — `backup/`.

**Возраст.** Год в коде Legacy — 2015: без врезки года (её делает legacy-port, `season_year = 2026`)
возраст игроков 2026/27 в игре на 11 лет меньше. Даты рождения в базе — настоящие.

## Профиль игры: `tools/gameprofile.py`

Инструменты, которые умеют обе игры, берут профиль опцией `--game {nhl13,legacy}` (у конвейера составов
и экипировки `--game` — ещё и каталог game/, имя игры распознаётся) или переменной `NHL_GAME`; по
умолчанию — NHL 13. Вывод для NHL 13 у всех правленых инструментов побайтно тот же: каждый раз сверялся
старым (HEAD) и новым кодом, итог — в сообщениях коммитов.

| | NHL 13 | NHL Legacy |
|---|---|---|
| распакованные архивы | `game/extracted/big/<архив>/` | `game/other/legacy/big/<архив>/` (база, локализация, шрифты — `cacheboot`) |
| работа инструментов | `game/work/<папка>/` | `game/work/legacy-data/<папка>/` |
| cache: порта | `game/userdata/cache/guest/` | из статуса legacy-port (`NHL_LEGACY_CACHE`) |
| лиги (строки) | НХЛ 0–31, АХЛ 32–61, SHL 62–73, Liiga 74–87, DEL 88–101, Extraliga 102–115, NLA 116–127, сборные 128–148, OHL/QMJHL/WHL 149–208, проспекты 209/210, легенды 211–213, Зимняя классика 214–217, Custom 218–247 | НХЛ 0–31, АХЛ 32–61, SHL 62–75, Liiga 76–90, DEL 91–104, Extraliga 105–118, NLA 119–130, Норвегия 131/132, сборные 133–153, CHL 154–213, проспекты 214/215, Зимняя классика 216–219, EASHL 220/221, Custom 222–251 |
| свободный арт | 98–101 | 100–107 (98 — Vaasan Sport, 99 — KooKoo) |
| рейтинги | `p_*`, `g_*`, `p_style`, `g_style` | `c_*`, `playerstyle` (шкала та же: − 36, 6 бит; стили те же) |
| artid / портреты | 14 бит; ≤ 12000 → `p8001_12000`, больше — `silhouettes` | 16 бит; **≤ 60000** → `p8001_12000` |
| типовые головы | 10000–10181 | 60000–60210 |

`gameprofile.check_db()` останавливает инструмент, если база или сейв — другой игры (по таблицам:
`nhlfutureschedule` есть только у Legacy, `fcc_*` — только у NHL 13; по обёртке сейва). Константы,
нужные одному инструменту, живут в нём по ключу профиля (`MUSIC` в music.py, `LOWER_NAMES` в fefont.py).

## Сейвы Legacy: ZlibV4 (`tools/tdb.py`)

Разобрано на анкерах nhl-modding-studio (ROSTER, DYNASTY, SEASON, BEAPRO Legacy для Xbox 360):

| Смещение | Что |
|---|---|
| 0x10 | checksum_a — CRC-32/IEEE по [0x1C..конец файла], BE |
| 0x14 | версия: 4 — составы, 5 — франшиза, сезон, «Стань профи» |
| 0x24 | размер сжатой области (BE): у составов = длине разжатого, у франшизы — ровно половине |
| 0x28 | checksum_b — CRC-32/BZIP2 по области [0x2C, 0x2C + размер) |
| 0x2C | длина потока zlib (**LE**) |
| 0x30 | поток zlib (78 9C), дальше нули до конца области |
| после области | хвост своих данных (франшиза: 160–1300 КБ; у составов нет) |

Разжатое — база TDB (длина — db_size @0x08) и 4 байта `DB DB DB DB`. `tdb.py verify/set/setstate` и
`SaveFile` читают и пишут такие сейвы: пустая перезапись — байт в байт, правка поля и `resize` — CRC
сходятся. Поток zlib-ng Python другой длины, чем у EA (игра разжимает любой); размер области при
изменённой базе — с тем же отношением к разжатому. `photos.py save` и `roster.equipment roster`
у Legacy берут её схему. Сейва составов у порта пока нет — игра берёт базу из `cache:\db\nhlng.db`.

## База: 32 команды (`tools/nhl32.py --game legacy`)

```bash
L=game/other/legacy/big/cacheboot; W=game/work/legacy-data/nhl32          # (--ahl32 → nhl32-ahl32)
python tools/nhl32.py $L/db/nhlng.db $W/nhlng.db $L/fe/loc/nhl_eng_us.db $W/nhl_eng_us.db \
       --meta $L/db/nhlng-meta.xml $W/nhlng-meta.xml --game legacy [--ahl32]
```

Те же шаги, что в NHL 13 ([teams.md](teams.md)), номера Legacy (`legacy_config()`, из профиля):
- сборные Матча звёзд (у Legacy — «Green / Red», «Black / Blue», строки 30/31) переезжают на Custom
  222/223, SEA/VGK встают на 30/31 (220/221 — команды EASHL, их не трогать);
- дивизионы — нынешние 8/8/8/8: у Legacy их уже 4 (3 Pacific, 4 Central, 5 Atlantic, 6 Metropolitan),
  Аризона (слот Юты) переходит в Central, SEA/VGK — в Pacific;
- арт SEA/VGK — 100/101, прожекторы 46/47 (у Legacy texlib_0…45), звук 32/33, `audioid2` «нет» =
  4095, арена-шаблон — «EA SPORTS ™ Arena» 181, комплекты формы — копии Tappara/TPS (88/89) под свой арт
  (style 1, варианты 0/1/2 — помощник art сверил по файлам формы Legacy), цвета экипировки Tappara в
  Legacy — ещё и тёмно-синие/оранжевый (в перекраске);
- у Legacy у команды 3 цвета (`stockteamcolorstable`, colorid 0–2): SEA — ледяной голубой, глубоководный
  синий, Shadow Blue; VGK — золото, стальной серый, красный;
- фарм-клубы — общие с соседом, как в NHL 13: Stockton Heat (бывший Abbotsford Heat) и Texas Stars;
- календари: `nhlschedule`, `favoriteteamschedule` и `nhlfutureschedule` (у Legacy — календарь
  следующих сезонов франшизы) — 32 × 84 игры по 42 дома, по нынешним дивизионам, на игровые дни своей
  таблицы, плюс строка Матча звёзд 32/33 в тот же день, что у EA (31.01 и 25.01), home/away — 6 бит;
- схема: вместимость франшизы на 32 (`leaguegmdata`/`leaguestaffdata` 32, `leaguedraftpick` 1344,
  `leaguetempscheduletable` 3200), поля «команда НХЛ» −1…30 → 6 бит (у Legacy без
  `leagueretirementtable` — там уже 8 бит, плюс новое `leagueplayerbiotable.tradeblockteam`);
- **`--ahl32`** (по просьбе legacy-port): Coachella Valley и Henderson — на Custom 02/03 = 224/225, арт
  102/103 (формы — копии Springfield/Providence у помощника art, [uniforms.md](uniforms.md) §12), арена —
  копия Cedar Park Center; АХЛ Legacy 2015/16 (30 клубов, 8/7/8/7) → 8/8/8/8: Texas — в Central, Lake Erie
  (Кливленд) — в North, как в нынешней АХЛ; `ahlschedule` — 32 × 72 (8 игр с соперником по дивизиону, 2 —
  с другим дивизионом конференции, 36 дома); `ahlaffiliate` — 8 бит (SEA → CV, VGK → HSK); строки Матча
  звёзд нет (126 команд — предел кода, как в NHL 13 `--ahl32`).

## Составы 2026/27 (`tools/roster --game legacy`)

```bash
python tools/roster all --offline --game legacy --stats-ratings --fa --skin --league liiga
#   → game/work/legacy-data/roster/nhlng.db (+ nhlng-meta.xml, отчёты); вход — база nhl32 выше
#   (--ahl32 --db-in game/work/legacy-data/nhl32-ahl32/nhlng.db --work roster-ahl32 — с CV/HSK)
python tools/roster photos --game legacy             # фото не из НХЛ (Liiga…) → кадр НХЛ (сеть — только недостающие)
python tools/photos.py build --game legacy           # портреты → game/work/legacy-data/photos-all (~13 мин)
python tools/photos.py db game/work/legacy-data/roster/nhlng.db game/work/legacy-data/roster/nhlng-photos.db --game legacy
cd tools && python -m roster.equipment --game legacy apply ../game/work/legacy-data/roster/nhlng-photos.db \
       ../game/work/legacy-data/roster/nhlng-equip.db --visor-rule --jersey-rule --report ../game/work/legacy-data/roster/equipment-apply.json
# в out: nhlng-equip.db → out/db/nhlng.db, nhlng-meta.xml рядом; nhl_eng_us.db из nhl32 → out/fe/loc/NHL_ENG_US.db;
#        photos-all/fe → out/fe
```

Кэш сети (`game/work/roster-cache/`) — общий с NHL 13: данные не зависят от игры. Своё у Legacy: папка
`game/work/legacy-data/roster/`, таблица artid новых (`artid-registry.json` там же; у `--work` другой
папки — та же таблица), замеры иконок голов (`roster-cache/skin/legacy/`).

Что у Legacy иначе (правки в `tools/roster/*`):
- поля рейтингов `c_*` и `playerstyle` вместо `p_*`/`g_*`/`p_style`/`g_style` (`dbview.fld`); шкалы и
  коды стилей те же — сверено по Кросби (6), Стэмкосу (7), Чаре, Кейту, Летангу, вратарям;
- особые команды Legacy не отдают строки донорам: сборные 133–153, Матч звёзд 222/223, проспекты
  214/215, Зимняя классика 216–219, EASHL 220/221; клубы — 32–132, 154–213 (и 224/225 при `--ahl32`);
- artid новых — 12815–49999 (у игроков базы до 12814); портреты Legacy ищет по artid так: ≤ 4000 →
  `p0_4000`, ≤ 8000 → `p4001_8000`, **≤ 60000** → `p8001_12000` (в generalhelpers.big Legacy «push 60000» на
  месте 12000 у NHL 13), больше — `silhouettes`; шаблон портрета — Legacy (512×512 / 256×128, метка BIGF
  L288 — `playerhead.Bigf` собирает её как EA, правка помощника art);
- типовые головы — 60000–60210; у Legacy есть и тоны 5, 7, 8 (по одной голове): по замеру иконок 5 —
  между 4 и 6, 7/8 — между 6 и 9, в выборе по фото — в соседних ступенях;
- в био Legacy нет `junioryearlost` и `waiversneedreentry` (пропускаются), новые `rookieahl`,
  `rookiechl`, `retainedsalarytrades` — 0, как у игроков НХЛ базы;
- `stockteamsalaryextras` (выкупы и удержания 2015/16 на 25 лет вперёд) — обнуляется;
- шкала OVR лиг вне НХЛ у Legacy ниже, чем у NHL 13 (НХЛ та же — медиана 82; АХЛ 68 против 76, Liiga
  65 против 72, SHL 67 против 73, OHL 55 против 67): Liiga 2026/27 (15 клубов Legacy, есть KooKoo и
  Sport; Jokerit и Jukurit мест не имеют) и CV/HSK ставятся в шкале Legacy — оценке по статистике сдвиг
  −7 (Liiga) и −8 (АХЛ), вратари Liiga и игроки без статистики — от уровня Legacy;
- экипировка: у Legacy ещё таблица `stockplayervisorexempttable` (кому можно без визора, 1779 строк —
  пришедшие до правила 2013 года): у полевых конвейера исключение остаётся только у Benn, O'Reilly,
  Bogosian; коды гетр те же (в образе Legacy та же таблица вариантов: 2 front, 3 backtuck, 0 full).
- без изменений осталось: название слота Юты — «Arizona Coyotes» (в NHL 13 — «Phoenix Coyotes»: своего
  арта Юты нет), названия клубов Liiga 2015/16 (Espoo Blues — у K-Espoo), `dynamic_ratings.db` Legacy
  (там заглушка: 800 одинаковых строк с одним game_id).

Итог (08.10.2026): 1274 игрока (НХЛ 798 + 437 Liiga + 39 свободных агентов), 387 сопоставлено (у Legacy
база 2015 года — сопоставленных больше, чем в NHL 13), 887 в строках доноров, проверки конвейера и CRC
— OK; Liiga — медианы 65/65/63 (как у Liiga в Legacy); портреты — у всех, у кого есть фото; экипировка —
обмотка 120, гетры 86, визор по правилу 118, исключения визора −426.

## Что сделали помощники (подробно — в своих документах)

- **fe** — [fe-fonts.md](fe-fonts.md) «NHL Legacy», [fe-background.md](fe-background.md) §10: шрифт «1:1»
  (глифы и хинтинг NHL 12, таблица `name` и метрики — Legacy, `font_extents.txt` Legacy остаётся верным;
  предела размера в коде нет — буфер по размеру файла из пула `RWFontPP`); фон Legacy — тёмная фотография
  арены, перекраской «как в NHL 13» не сделать — варианты `legacy-gray`, `nhl13-muted`, `nhl13-gray` в
  `game/work/legacy-data/fe/variants/` (не ставились); главное меню NHL 12 ложится на фреймворк Legacy,
  но `menu.big`/`main.big` у Legacy свои — нужна `--game legacy` у menu12 (агент menu12 ещё работает).
- **music** — [music.md](music.md) §9: кодек тот же (EALayer3 v1b), EA Trax у Legacy — 10 песен, вторые
  версии — свои; `build` добавляет слоты trax10…21 (новые id в `.sbr`, записи в MBX, список MenuTunes
  дерева выбора); 16 песен Best of NHL, `.sbs` на 1,6 % больше оригинала; запасной вариант на 10 песен —
  `game/work/legacy-data/music/out-10`.
- **models** — [player-models.md](player-models.md) §11: у Legacy байт в байт как в NHL 13 все 60
  свитеров, клюшки, скелеты и детализации `_0`/`_2`; отличаются `_3` гетр, коньков и шорт (полосы
  треугольников вместо списка) — пересобраны; новое у Legacy — клюшки на льду (`prop/goaliestick*`,
  `prop/droppedstick_0`, подсетки) — обмотка и там; пересборка — `bash game/work/legacy-data/models/build.sh`.
  Попутно найдено: у NHL 13 сетки `_3` — список треугольников, `rw4mesh` читал их как полосы (правки `_3`
  в NHL 13 считались по неверной поверхности; игра рисует верно) — решение за пользователем.
- **art** — [logos-arenas.md](logos-arenas.md) §9, [uniforms.md](uniforms.md) §12: логотипы t/s/d/c/w/r
  (размеры — по перерисованным логотипам Legacy), центр льда, шайба в новом стиле Legacy, баннер,
  прожекторы 46/47, форма czkit дом/выезд/третья; CV/HSK (102/103) — копии формы Springfield/Providence.

## Проверка в игре

Порт legacy-port (`legacy-port/codegen/out/build/win-amd64-relwithdebinfo/nhllegacy.exe`, D3D12 ROV),
по замку `game/work/status/game.lock`; снимки — `game/work/legacy-data/ingame/`:

1. 20:13 — база nhl32: игра берёт `cache:\db\nhlng.db`, в Play Now в списке НХЛ — GOLDEN KNIGHTS и
   KRAKEN (без логотипов и составов), матч ARZ–ANA идёт.
2. 20:18 — шрифт NHL 12: подхватился (меню, Select Teams, Starting Lineups, табло — «Con Bold» NHL 12).
3. 20:52 — составы + музыка + шрифт: главное меню шрифтом NHL 12; EA SPORTS Trax — все 16 песен Best of
   NHL с нашими названиями и обложками, играет наша; у SEA/VGK свои составы (звёзды 4/4/4,5), Starting
   Lineups «Arizona VS Seattle», матч. Пользователь сам доиграл период: у Вегаса состав, вратарь и головы
   есть, форма была синяя (арт ещё не стоял).
4. 21:35–21:57 — всё вместе (база с портретами и экипировкой, портреты, 3D, арт): Play Now SEA–VGK —
   логотипы Kraken и Golden Knights, превью формы (SEA белая выездная, VGK золотая), Starting Lineups с
   нашими портретами (McCann, Barbashev), предматчевая заставка с логотипами, в матче — форма SEA/VGK в
   3D (номера, нашивки, капитанская C), логотип VGK в центре льда, табло SEA/VGK; визор у Stone, обмотка.
   По логу порта: ни один файл 3D, арта, музыки и шрифта из out/ не дал промаха `cache:` (свободные файлы
   берутся раньше архивов).

Не проверено в игре: гетры и клюшки вблизи (повтор), край свитера сзади, клюшка на льду; табличка имени
вратаря SEA на заставке была пустой (снимок посреди анимации? — посмотреть); база `--ahl32` и франшиза на
32 (нужны врезки legacy-port); возраст (врезка года); фон меню (варианты не ставились).
