# Логотипы, арены и лёд: Seattle Kraken и Vegas Golden Knights

Разбор от 08.10.2026 (файлы игры — диск без TU2, код — `nhl-13-port/generated`, логи — `nhl-13-port/out/*.log`).
Инструменты — [tools/teamart.py](../tools/teamart.py) (форматы, сборка) и
[tools/newteams_art.py](../tools/newteams_art.py) (поля базы, по умолчанию dry-run). Всё собранное лежит
в `game/work/logos/` (вне git), в `game/userdata` ничего не записано, живая `nhlng.db` не тронута.
**В игре результат ещё не проверялся.**

## Коротко

- Логотипы интерфейса — 6 наборов `fe/ion/artassets/teamlogos*/<буква><artid>.big` (t, s, d, c, w, r),
  номер = `exhibitionteams.artid` (во франшизе — `leagueteams.artid`). Контейнер как у фото игроков
  (BIGF → Apt + XPR2, RefPack), текстура **k_8_8_8_8** (не DXT5): байты A, R, G, B, тайлинг Xenos,
  8in32, без мипов.
- В матче по `artid` хозяина берутся **центр льда** `rendering/icesurface/centerlogo_<artid>_cm.rx2`
  и **шайба** `rendering/puck/puck_<artid>_cm.rx2`; по `artid` команды — **все текстуры формы**
  (свитер, номера/фамилии, шорты, гетры, нашивка), а не по `stockteamjerseys.teamartid`.
- 3D-файлы — контейнер RenderWare 4 для Xbox 360 (`.rx2`), DXT1/3/5 с полной цепочкой мипов и
  упакованным хвостом; раскладка разобрана и проверена байт-в-байт на 2 804 файлах.
- Для SEA/VGK собраны **artid 98 и 99** (свободны во всех наборах и в базе; Tappara/TPS 93/94 не
  тронуты): 12 логотипов интерфейса, центр льда, шайба, баннер, логотип прожекторов — 20 файлов,
  `game/work/logos/out/` в раскладке `cache:` (копировать в `game/userdata/cache/guest/`).
- База: обязательно `exhibitionteams[30].artid = 98`, `[31].artid = 99`; по желанию — прожекторы 45/46.
  **С artid 98/99 игре нужны и текстуры формы под 98/99** — без них свитеры будут без текстур (как
  сейчас с 20054). Запасной вариант готов: `game/work/logos/kit-alias/` — копии формы Tappara/TPS
  под 98/99 (48 файлов, 42 МБ).
- Размер льда задаёт `exhibitionarena.arenatype`: 0 — НХЛ (`ice_nhl_Container_0`), 1 — международная
  площадка (`ice_intl_Container_0`). Арена 61 (Hartwall Areena) — международная, поэтому у
  Tappara/TPS в НХЛ был большой лёд. Арены 174/175 (копии 168 «EA SPORTS Arena») — НХЛ, это верно.

## 1. Логотипы интерфейса

| Набор | Папка (`cache.big`) | Файлов | Текстура / сцена | Кадр у EA (замер) | Где видно (логи) |
|---|---|---:|---|---|---|
| t | `teamlogos/t<N>.big` | 306 (+`tblank`, `tcustom`) | 256×256 | логотип ~165–190 × 160–200 по центру, блик сверху, тёмная тень | выбор команд, заставки, шапки |
| s | `teamlogossmall/s<N>.big` | 306 | 128×64 | «таблетка» 114×46 (x 7…120, y 9…54, скругление ~9) цвета команды, крупный план логотипа, блик/тень пополам | списки, таблицы, календарь, табло |
| d | `teamlogosdynasty/d<N>.big` | 306 (+`dblank`) | 128×128 | логотип ~83–110 × 66–100 | франшиза, фарм-клуб на выборе команды |
| c | `teamlogoscalendar/c<N>.big` | 306 | 128×128, сцена 98×86 | крупный план (~×1,5) с растушёвкой краёв | календарь |
| w | `teamlogoswide/w<N>.big` | 306 | 256×256 | крупный план (~×2) с мягкими краями | фон выбора команды |
| r | `teamlogosreflection/r<N>.big` | 30 (только 0…29) | 256×512 | логотип сверху + отражение 10–25 % | один экран-карусель (запросы r9…r17) |

Номера: 0…31 НХЛ и сборные, 34…53 и 108 — сборные стран, 69…97 — Швеция/Финляндия, 131…163 —
АХЛ, 180…196 — DEL, 280…295 — Чехия, 320…331 — Швейцария, 341/342 — проспекты, 360…421 — CHL,
505 — легенды, 20001…20087 — логотипы конструктора команд (`createteam`). TU2 (`patch.big`) заменяет
t/s/d/c/w 76 и 20087.

**Как игра ищет.** ActionScript `GeneralHelpers.getArtAssetPath` (`boot.big`) и код MUD собирают
`artAssets/teamLogos/t%d.swf`, `teamLogosSmall/s%d`, `teamLogosDynasty/d%d`, `teamLogosWide/w%d`
(+ Calendar, Reflection; есть и `teamLogosBroadcast`, но файлов такого набора в NHL 13 нет). Загрузчик
переводит в `cache:\fe\ion\artassets\teamlogos\t<N>.big` (нижний регистр): сначала свободный файл
в `cache:` (= `game/userdata/cache/guest/`), потом архив. Подпапок по диапазону, как у фото, нет.

**Формат файла.** BIGF (6 записей, выравнивание 0x40, метка `L286`, хвост 16 байт) → Apt Data +
геометрия (два треугольника на всю сцену, тексель = точка сцены) + XPR2 `TX2D` (RefPack). Константа
выборки: формат 6 = `k_8_8_8_8`, порядок 2 = 8in32, swizzle 0x60A (D3DFMT_A8R8G8B8), тайлинг, мипов
нет. На диске каждый тексель — 4 байта **A, R, G, B**; адрес — `XGAddress2DTiledOffset` с 4 байтами на
элемент (`log2 = 2`, pitch в текселях). Альфа прямая, под прозрачным — нули. Проверка: все 1 558
логотипов разбираются и собираются заново байт-в-байт (контейнер и тайлинг).

## 2. 3D: что в матче зависит от номеров

| Файл | Номер | Формат | Откуда номер (код) |
|---|---|---|---|
| `rendering/icesurface/centerlogo_<N>_cm.rx2` | artid хозяина | 1024² DXT3, 11 уровней | структура команды +126 (sub_83322658); в логе матча TPS — `centerlogo_94` |
| `rendering/puck/puck_<N>_cm.rx2` | artid хозяина | 256×512 DXT1, 10 уровней | +164 = artid (sub_833266F0); сборные 34…53/108 → 252, созданная команда → 255, арены 510/511 → номер арены, Winter Classic → 700 |
| `rendering/banner/banner_<N>_cm.rx2` | artid | 512² DXT3 | баннеры под сводом (чемпионства); в логах не встречался |
| `rendering/jersey/texlib_<s>_<N>_<v>.rx2`, `name_<s>_<N>_<v>_cm`, `pant/texlib_<s>_<N>_<v>`, `sock/sock_<s>_<N>_<v>_cm` | artid команды | DXT/DXN, 8888 (именные таблички — линейные) | +14 = artid (sub_82816178), стиль/вариант (+26/+52) — из выбранной строки `stockteamjerseys` (поиск по teamid + jerseyindex); путь собирает sub_83310CB0 |
| `rendering/logo/texlib_<N>_<s>_<v>.rx2` | artid | DXT5 256×128 + 128×64 + 128×128 | нашивка на груди и плечах; у формы без нашивки — `texlib_999_0_0` |
| `fe/ion/artassets/jerseys/jersey_<s>_<N>_<v>.big` | artid (= teamartid у EA) | 8888 256×256 | превью формы в меню |
| `rendering/goaliehelmet/goaliehelmet_<s>_<N>_cm.rx2` | маска (`goaliemask*`) | | своя нумерация, не artid |
| `rendering/tunnel/texlib_<N>.rx2` | `exhibitionteams.tunnel` | 3 × DXT1 | таблички и стены туннеля (38 — EA SPORTS) |
| `rendering/spotlight/texlib_<N>.rx2` | `exhibitionteams.spotlight` | 256² DXT5 | логотип, который прожекторы рисуют на льду при выходе (36 — EA SPORTS) |
| `rendering/stadium/stadium_<N>_Container_0.rx2`, `jumbotron/texlib_<N>`, `crowddata/crowd_<N>.cwd`, `particle/stadium_<N>.rvi`, `enviro/helmet_<N>` | `exhibitionarena.arenaartid` | | модель арены, экраны куба, зрители |
| `rendering/icesurface/icesurface_<N>_bm.rx2` | 0…29 (арены НХЛ), иначе 999 | 512² DXT5 | вся площадка с логотипом в центре (дальний план/отражение); у TPS запрошен 999 |
| `rendering/icesurface/ice_cline_<N>_cm.rx2` | `exhibitionarena.centerline` | 32×2048 DXT3 | красная линия: 0 — сплошная, 11 — «шашки», у клубов свои; 8↔9 меняются по типу площадки |
| `rendering/icesurface/ice_lines_<N>_cm.rx2` | +160 структуры хозяина | 1024×2048 DXT1 | разметка: 0 — НХЛ (трапеция), 1 — международная, 4 — швейцарская с рекламой |
| `rendering/icesurface/ice_hotspot_0/1_<N>_cm.rx2` | реклама | | надписи на льду (по 5 на матч) |

Структура команды для матча (sub_82816178) заполняется из строки `exhibitionteams` по номерам
колонок `nhlng-meta.xml` (чтение — sub_829043C0): +12/+14/+164 ← `artid` (колонка 12), +8 ← `audioid`, +92 ← `league`,
+94 ← `table` (1 — «созданная команда»: центр льда собирается из конструктора, шайба 255), +96 —
код страны по artid (sub_8280B830: США → 20, Канада — свой; 98/99 → −1, как у всех неизвестных).

### Контейнер RW4 (`.rx2`)

- В архивах каждый `.rx2` дополнительно сжат `chunklzx` (LZX, кадры XMemCompress). Поток AssetStream
  (sub_8242FC70) узнаёт `chunkzip`, `chunkref`, `chunlzma`, `chunklzx` версии 2, иначе читает файл как
  есть — свободный файл в `cache:` кладётся несжатым. Игра действительно спрашивает свободные
  `cache:\rendering\…\*.rx2` (видно в логах).
- Заголовок: `\x89RW4xb2\0`, +0x20 — число записей, +0x30 — таблица записей, +0x44 — размер заголовка
  (0x1000), +0x54 — размер данных. Записи по 24 байта (5 × u32 + тег): `0x00010031` — буфер (смещение от
  0x1000, размер), `0x00020003` — описание 56 байт (с +0x1C — константа выборки Xenos, 6 слов; поле
  базового адреса = номер записи буфера, адрес мипов — от базы), `0x00EC0010` — имена растров (число,
  0x1505, затем (указатель, 0x00020003, номер записи) на каждое, строки). Имена вида
  `centerlogo_93_cm.Raster`, `logo_93_0_0_0.Raster` — для нашивок, туннеля и экранов игра ищет растр
  по имени (`logo_%i_%i_%i_0.Raster`), поэтому при смене номера имена переписываются (той же длины).
- Раскладка уровней (как в Xenia): база — pitch из константы, высота до 32 блоков; уровни ≥ 1 — с адреса
  мипов, размеры `next_pow2 >> L`, у тайловых каждый уровень до 32×32 блоков, у линейных строка кратна
  256 байтам; с первого уровня, где меньшая сторона ≤ 16 текселей, все уровни лежат в одном «хвосте»
  по смещениям `GetPackedMipOffset`. DXT — порядок 8in16, 8888 — 8in32.
- Проверено: 2 804 файла (`icesurface`, `banner`, `puck`, `logo`, `tunnel`, `spotlight`, `jumbotron`) —
  раскладка покрывает все ненулевые байты буфера, 0 ошибок; соседние уровни мипов — уменьшенные копии
  друг друга (27–40 дБ); занятые блоки хвоста совпадают с расчётом один в один.

### Центр льда (по всем `centerlogo_*`)

Диск цвета льда (231, 233, 231) радиусом 388 вокруг (512, 512), синее кольцо (0, 56, 165) по радиусу
≈ 381–385 (это круг вбрасывания), внутри логотип; полоса x 494…529 — **прозрачная**: под ней видна
красная линия из `ice_cline_<centerline>`. Поле `exhibitionarena.centericelogo` — 0 у всех арен,
игрой для обычного матча не используется. Особые арены (тренировка, EASHL, Winter Classic) ставят
свои центры 500/502/507/508/510/511/512/514.

### Центр льда из NHL 27 (23.10.2026, все 32 клуба)

Пользователь: «перенести центры льда для всех команд». У NHL 27 лёд устроен как у Legacy: центр — отдельная текстура
на клуб `content/worlds/rink/textures/centerlogo/ice_centerlogo_<N>_color` (1024² BC7, кольцо r 378–383 — как у Legacy
380,5–385,5), отдельно разметка `lines/ice_lines_<N>` (2048×4096, у Legacy 1024×2048 — рисунок тот же), красная линия
`centerline/ice_centerline_<N>` (64×4096), надписи `hotspot/ice_hotspot_*` и общие слои материала (`common/`: снег,
грязь, следы заливки — у Legacy другой шейдер, не переносятся). Отличие центра: у NHL 27 вокруг логотипа прозрачно (лёд
даёт сам материал), у Legacy диск льда и прозрачная полоса под красную линию — в текстуре. Номер N = арт EA (0 ANA …
29 WSH = artid Legacy), 30 — Юта (Delta Center, у нас арт 104), 32 — VGK (арт 101), 33 — SEA (арт 100); 22 (прежняя
Аризона) и 31 (Матч всех звёзд) не берутся. Названия арен — нынешние (MIN — Grand Casino Arena).

Порядок (повторить для нового сезона):
1. Выгрузка: `FB_GAME=nhl27 python -m fb.extract "rink/textures/centerlogo/ice_centerlogo_([0-9]|[1-3][0-9])_color$"
   --out ice27` → `game/work/nhl27/extract/ice27/…`.
2. `python -m fb.ice --source nhl27 build` — картинка NHL 27 поверх основы Legacy (`fb.ice.convert`: диск (231, 233, 231)
   r 388, кольцо, полоса x 494–529 прозрачная) → `game/work/nhl27/out/ice/centerlogo_<КОД>.png`; `sheet` — лист «Legacy
   сейчас | из NHL 27» (`game/work/nhl27/compare/ice_center_32.png`).
3. `python -m kitport build --stages pack,overlay` — `edge_kit.pack_ice_centers` кладёт их в пакет (`centerlogo_<арт>_cm.rx2`
   по шаблону: наш файл из `legacy-data/out` у SEA, VGK, UTA, иначе архив Legacy), затем `kitport install`.
   Сейв ROSTER центры льда не хранит.

## 3. Номера арта SEA = 98, VGK = 99: проверка

- **Архивы** (оглавления всех `.big` диска и TU2): ни одного файла с номером 98/99 ни в одном наборе,
  который ищется по artid (логотипы ×6, превью формы, номера, центр льда, баннер, шайба, нашивки,
  свитеры, таблички, шорты, гетры). 98/99 встречаются только как номера вратарских масок —
  другая нумерация.
- **База**: `exhibitionteams.artid`, `stockteamjerseys.teamartid`, `customteamjerseys.teamartid`,
  `exhibitionplayerbiotable.artid` — значений 98/99 нет. `exhibitionarena.puck = 99` у 36 арен
  (европейские, EA) — для текстуры шайбы это поле не используется (в матче TPS на арене с puck 99
  запрошена `puck_94`, файла `puck_99` у EA нет вовсе).
- **Код**: особые диапазоны artid — 34…53 и 108 (шайба сборных), 32/33 (общие свитеры НХЛ), ≥ 20000
  (конструктор), 252/254/255/5xx/7xx/999 (служебные). 98/99 никуда не попадают.
- Номер двузначный, как у шаблонов EA (`*_93`), — имена растров переписываются на месте.

## 4. Что собрано

`game/work/logos/out/` — дерево как в `cache:`; копировать целиком в `game/userdata/cache/guest/`
(откат — удалить эти файлы). Исходники — официальные SVG НХЛ
(`https://assets.nhle.com/logos/nhl/svg/SEA_light.svg`, `VGK_light.svg`, знак ® убран), только для
личного использования; рендер — Chrome без окна, кадр и эффекты — по замерам оригиналов EA.

| Файл | Байт | Что |
|---|---:|---|
| `fe/ion/artassets/teamlogos/t98.big`, `t99.big` | 25 264 / 21 040 | основной логотип |
| `fe/ion/artassets/teamlogossmall/s98.big`, `s99.big` | 10 672 / 10 480 | «таблетка» |
| `fe/ion/artassets/teamlogosdynasty/d98.big`, `d99.big` | 11 696 / 9 776 | франшиза |
| `fe/ion/artassets/teamlogoscalendar/c98.big`, `c99.big` | 10 736 / 10 800 | календарь |
| `fe/ion/artassets/teamlogoswide/w98.big`, `w99.big` | 78 128 / 85 488 | крупный план |
| `fe/ion/artassets/teamlogosreflection/r98.big`, `r99.big` | 31 728 / 28 336 | с отражением |
| `rendering/icesurface/centerlogo_98_cm.rx2`, `_99_` | 1 445 888 | центр льда |
| `rendering/puck/puck_98_cm.rx2`, `_99_` | 110 592 | шайба: логотип на верхней грани, низ — НХЛ |
| `rendering/banner/banner_98_cm.rx2`, `_99_` | 397 312 | логотип для баннеров |
| `rendering/spotlight/texlib_45.rx2` (SEA), `texlib_46.rx2` (VGK) | 135 168 | прожекторы (нужен `spotlight` 45/46) |

Каждый файл сверен с шаблоном (`game/work/logos/scripts/verify_out.py`): всё, кроме пикселей и имён
растров, совпадает байт-в-байт. Превью — `game/work/logos/preview/sheet_ui.png` (сверху оригинал
EA «Питтсбург» для сравнения) и `sheet_3d.png`; спецификации — `game/work/logos/src/SEA.json`,
`VGK.json`.

**Запасная форма** — `game/work/logos/kit-alias/`: `teamart.py alias 93 98` и `alias 94 99` — копии
всех файлов формы Tappara/TPS (свитеры, таблички, шорты, гетры, нашивки, превью) под 98/99 с
переписанными именами растров, 48 файлов, 42 МБ. Нужна, только если своих комплектов под 98/99 ещё
нет (их делает агент по формам — его файлы важнее). Внешне — форма Tappara/TPS, как сейчас в базе.

### Размеры — по замерам EA (вторая сборка, 08.10.2026)

Первая сборка (в игре проверена: логотипы видны в меню и на льду) была заметно крупнее логотипов НХЛ.
Замер непрозрачной части (альфа > 128) у оригиналов 0…29 и поправки:

| Набор | EA: рамка (медиана [мин…макс]), площадь | Что сделано | SEA 98 | VGK 99 |
|---|---|---|---|---|
| t | w 171 [144…191], h 150 [98…182], площадь 17 111 [8 493…23 997] | масштаб к медианной площади, h ≤ 170, w ≤ 191 | 135×170, 15 022 | 122×165, 17 072 |
| d | w 87 [66…105], h 78,5 [50…88], площадь 4 267 [2 404…6 006] | то же, h ≤ 86, w ≤ 105 | 68×86, 3 915 | 61×83, 4 272 |
| s | 114×46 у всех | без изменений | 114×46 | 114×46 |
| c | 77×67 (маска), площадь до 4 702 | растушёвка — альфа EA (c1/c3/c11: скруглённый прямоугольник 84×73 от (7, 6), край ~14 px) | 77×67, 4 132 | 77×67, 4 702 |
| w | ≤ 135×135 (круг, 50 % альфы на радиусе 67), площадь до 14 220 | растушёвка — альфа EA (w2/w4/w5: круг с центром (125, 128), ноль к радиусу ~124) | 135×135, 13 970 | 135×135, 14 220 |
| r | (только 0…29) | логотип того же размера, что t | — | — |

Сборка `teamart.py build` (CLI) теперь так и делает (`build(..., ea_fit=True)`; `--legacy` — первая
сборка). Шайба 98/99 пересобрана: логотип по центру грани (127,5; 172) — в первой был на 3 px выше,
вписан по радиусу 38. Центр льда, баннер и прожекторы не менялись. Первая сборка сохранена в
`game/work/logos/tmp/out_v1/`.

## 5. Что применить в базе

`tools/newteams_art.py` (без `--out` ничего не пишет):

```bash
python tools/newteams_art.py                      # план по живой базе
python tools/newteams_art.py --out nhlng.new.db   # копия с правками, CRC пересчитываются и проверяются
    [--spotlight] [--jerseys] [--stadium 601,602] [--centerline 11,11]
```

| Поле | Сейчас | Нужно | Зачем |
|---|---|---|---|
| `exhibitionteams[30].artid` (SEA) | 20054 | **98** | логотипы, центр льда, шайба, баннер, форма |
| `exhibitionteams[31].artid` (VGK) | 20054 | **99** | то же |
| `exhibitionteams[30/31].table` | 0 | 0 (проверяется) | 1 = созданная команда: центр льда из конструктора, шайба 255 |
| `exhibitionteams[30/31].spotlight` | 36 (EA SPORTS) | 45 / 46 — по желанию (`--spotlight`) | логотип клуба от прожекторов |
| `stockteamjerseys[684…687].teamartid` | 93/94 | 98/99 — по желанию (`--jerseys`), когда есть форма под 98/99 | у EA всегда равно artid команды; рендер берёт artid команды |
| `exhibitionarena[174/175].arenatype` | 0 | 0 | площадка НХЛ |

Без смены artid в 98/99 логотипы не появятся; со сменой — обязательно положить файлы формы под
98/99 (свои или `kit-alias`), иначе свитеры, шорты и гетры останутся без текстур. В начатых франшизах
`leagueteams.artid` — старый (копия при создании), новые франшизы возьмут из `nhlng.db`.

Строки локализации для арен не нужны: названия арен игра берёт из `exhibitionarena.arenaname` /
`cityname` (в `NHL_ENG_US.db` есть только `StadiumName_600…605/700…703` — арены HUT и Winter Classic),
а у 174/175 они уже «Climate Pledge Arena, Seattle, WA» и «T-Mobile Arena, Las Vegas, NV».
`NHL_ENG_US.db` не менялась, резервных копий не понадобилось.

## 6. Арены и лёд

`exhibitionarena` (176 строк; во франшизе — копия `leaguearena`), номер арены — `exhibitionteams.arenaid`. Сама чаша
(`stadium_<N>`) и кресла с их цветом (`crowd_<N>.cwd`) у NHL Legacy — в [arenas.md](arenas.md):

| Поле | Что |
|---|---|
| `arenaname`, `cityname` | название и город (строка в базе) |
| `maxattendance`, `avgattendance` | вместимость и заполняемость, % |
| `arenatype` | 0 — площадка НХЛ 200×85 футов, 1 — международная (60×30 м) |
| `arenaartid` | 3D-модель: 0…29 арены НХЛ, 87 Hartwall, 47 Стокгольм, 252 общая европейская, 255 «EA SPORTS Arena», 494 CHL, 145/155 АХЛ, 321…331/498 Швейцария, 507 Чехия, 510/511 EA Hockey League, 600…602 HUT «Small/Medium/Large North American», 603…605 HUT International, 700…703 Winter Classic |
| `centerline` | рисунок красной линии `ice_cline_<N>` |
| `centericelogo` | 0 везде, не используется |
| `arenaaudioid`, `cityaudioid`, `chantaudioid`, `goalhorn`, `periodhorn` | звук: объявление арены и города, кричалки, сирены (255 — общий) |
| `puck` | 0…29 у НХЛ, 99 у прочих; на текстуру шайбы не влияет |
| `stanchion`, `bouncemap`, `powerring` | стойки между стёклами (1 у арен НХЛ), отскоки от бортов и светодиодное кольцо вокруг трибун (у НХЛ — свои 0…29, у прочих 999 — общие) |

**Выбор площадки** (sub_83322518): модели 702/703 → `ice_nhl_full_lm_Container_0`; иначе
`arenatype == 1` (sub_83288980) → `ice_intl_Container_0`, иначе `ice_nhl_Container_0`. Тот же признак
меняет местами красные линии 8/9; разметка (`ice_lines_0` НХЛ / `_1` международная) приходит из данных
команды-хозяина. Влияет ли `arenatype` и на физику (размер для игроков и шайбы), не проверялось —
вызовы найдены только в рендере.

- **Арена 61** «Hartwall Areena ™», Helsinki: `arenatype 1`, модель 87, звук 87, линия 0, 13 665
  мест — общая для всей финской лиги и сборной Финляндии; отсюда большой лёд у Tappara/TPS в НХЛ.
- **Арена 168** «EA SPORTS ™ Arena», Burnaby: `arenatype 0` (НХЛ), модель 255 (на кубе — «EA SPORTS
  NHL 13»), линия 0, звук 255 (общий), 18 000 мест — у созданных команд, проспектов, тренировок.
- **Арены 174/175** — копии 168 с названиями «Climate Pledge Arena» (17 151) и «T-Mobile Arena»
  (17 500): лёд НХЛ, всё нейтральное. Так и оставить. По желанию: `--stadium 601,602` — модели HUT
  «Medium/Large North American Arena» (НХЛ-размер, все файлы модели на месте, в обычных матчах не
  проверены; на кубе там «EA SPORTS» — экраны `jumbotron/texlib_601/602` можно перерисовать логотипами
  клубов тем же `teamart.py`), `--centerline 11,11` — классическая линия НХЛ.

**Логотипы на льду**: центр — `centerlogo_<artid хозяина>` (поставлен для 98/99); дальний план всей
площадки `icesurface_<N>_bm` есть только у арен 0…29 (у прочих — общий 999 с нейтральным центром,
под свой номер его не подложить без правки кода); реклама — `ice_hotspot_*`; линии — `ice_lines_*` и
`ice_cline_*`. Все — тот же RW4 с DXT, `teamart.py decode/build` их читает и пишет.

## 6а. Фарм-клубы АХЛ: Coachella Valley (artid 100) и Henderson (artid 101)

**Номера.** 100/101 нет ни в одном наборе, который ищется по artid (логотипы, превью формы, центр льда,
баннер, шайба, нашивки, свитеры, таблички, шорты, гетры), и ни у одной команды/комплекта в базе.
Файлы с этими числами есть только в других пространствах номеров: фото игроков `p100/p101`, флаги стран
`f100/f101`, вратарские маски, вещи конструктора игрока, кубки клубов, оверлей `overlay_100`, звук
сирен `100_goal/100_period.abk`. В базе 100/101 — только `exhibitionplayerbiotable.artid` (фото) и
`goaliemask0_starter` (маски).

**Что есть у клубов АХЛ (строки 32–61, все 30):** t, s, d, c, w; центр льда, шайба, баннер; нашивки,
свитеры, таблички, шорты, гетры, превью формы. **Нет:** r (только НХЛ 0…29), teamnumbers (только НХЛ),
`icesurface_<N>_bm` (у арен АХЛ — общий 999). Туннель и прожектор у всех клубов АХЛ общие — `tunnel 34`
(таблички АХЛ) и `spotlight 34` (логотип АХЛ), свой прожектор не нужен. По логам игра запрашивала для
клубов АХЛ только s (344 раза), d (119), c (14), w и t (по 4) — матчей АХЛ в логах нет.

Шайба АХЛ — свой шаблон: верх — логотип клуба прямо на тёмной грани (34, 38, 37) с рельефным ободком
(радиус 112–118), низ — логотип АХЛ. Собрано на шаблоне `puck_150` (грань до радиуса 107 закрашена,
логотип вписан в радиус 94). Центр льда у АХЛ устроен как у НХЛ (диск 388, синее кольцо, полоса под
красную линию); у части клубов EA вокруг — название арены, у наших его нет.

**Собрано** — `game/work/logos/ahl/` (16 файлов, 4,1 МБ, раскладка `cache:`): t/s/d/c/w 100 и 101,
`centerlogo_100/101_cm.rx2`, `puck_100/101_cm.rx2`, `banner_100/101_cm.rx2`. Источник — SVG из
Википедии (`Coachella_Valley_Firebirds_logo.svg`, `Henderson_Silver_Knights_logo.svg`, fair use, только
для личного использования), знака ® в них нет. Размеры — по тем же замерам EA: t 156×164 / 118×169,
d 76×82 / 60×85, c 77×67, w 135×124 / 135×135, s 114×46. Шаблоны контейнеров для 3-значных номеров —
`*_150` (имена растров той же длины). Превью — `game/work/logos/ahl-preview/sheet_ui.png`,
`sheet_3d.png` (слева оригинал EA «Провиденс»).

**Форма** — `game/work/logos/ahl-kit/` (31 файл, 27 МБ): `teamart.py alias 153 100` (Springfield
Falcons, строка 56) и `alias 150 101` (Providence Bruins, строка 51). Стили и варианты в базе совпадают
с архивом: у обоих стиль 1; Springfield — варианты 0, 1, 2 (у нашивки только 0, 1 — как у EA), Providence —
0, 1 (нашивка и превью есть и для 2, в базе его нет). Копировать строки `stockteamjerseys`:

| Новая команда | Строки-образцы | teamid → | teamartid → |
|---|---|---|---|
| 220 CV | 296, 297, 298 (variant 1, 0, 2; jerseyindex 0, 1, 2; у 298 hastie 1, isdefault 0) | 220 | 100 |
| 221 HSK | 285, 286 (variant 1, 0; jerseyindex 0, 1; hastie 1) | 221 | 101 |

**Поля базы для 220/221.** `artid` 100/101; `table` 0 (у заготовок сейчас 1 — с ним центр льда и шайба
берутся у конструктора); `league` 1; `tunnel` 34, `spotlight` 34 (сейчас 38/36 — EA SPORTS); поля
формы и экипировки (`jerseystyle`, `jerseybackhome/away`, `font`, `pantsstyle`, `sockstyle`,
`helmetbrand`, `gloves`, `itechvisorcolor`, `goaliemask*`) и строки `stockteamequipmenttable` — как у
строк 56/51, раз форма их; `audioid` — у клубов АХЛ свои (95, 131…164), 0 — это «Анахайм».
Арены — две новые строки `exhibitionarena` по образцу арены АХЛ (например 54 или 49): «Acrisure Arena»,
«Thousand Palms, CA», 11 000 мест (по Википедии; на хоккей ~10 000) и «Lee's Family Forum»,
«Henderson, NV», 5 567; `arenatype` 0, `arenaartid` 145 (модель АХЛ, на кубе — логотипы АХЛ),
`centerline` 11 (как у 29 из 30 арен АХЛ), `stanchion` 0, `powerring`/`bouncemap` 999, `puck` 0,
сирены 0, `chantaudioid` 0; `arenaaudioid`/`cityaudioid` — 255 (нейтральный, как у «EA SPORTS Arena»;
у арен АХЛ там номер города — 130…163).

**Арены АХЛ в 3D.** Все 30 (строки 30–59): `arenatype` 0 — площадка НХЛ (`ice_nhl_Container_0`);
модели 145 (26 арен США) и 155 (4 канадские: Абботсфорд, Гамильтон, Сент-Джонс, «Рико»); у обеих на
кубе — логотипы АХЛ; `centerline` 11 «шашки» у всех, кроме Рочестера (0); дальний план льда — общий
999; особые: Хартфорд (puck, сирены, кричалки 136), Сидар-Парк (звук и кричалки «Далласа»: 95 и 9).

**Обратите внимание:** `exhibitionteams.ahlaffiliate` — 6 бит (−1…62, номер + 1): номера 220/221 туда
не помещаются (сейчас у SEA 33, у VGK 59). Франшиза к тому же берёт строки 0–127 (`leagueteams.index` —
7 бит). Для логотипов это неважно, для связи «клуб НХЛ ↔ фарм-клуб» — вероятно, понадобится расширение
поля или другие строки.

## 7. Проверить в игре / открыто

1. Положить `out/` в `cache:`, выставить artid 98/99 (+ форма под 98/99) → «Играть сейчас»
   SEA — VGK: логотипы на выборе команд, табло, центр льда и шайба хозяина, прожекторы (если 45/46).
2. В `nhl-13-port/out/game-release.log` строки `NtCreateFile FAILED` для этих путей должны пропасть.
3. Свободные `.rx2` в `cache:` — без chunklzx (так EA файлов в архивах нет); по коду потока это
   допустимо, в игре не проверено. Если не подхватятся — упаковать в `chunkzip` (deflate).
4. `audioid` у SEA/VGK = 0 — это номер «Анахайма»: комментатор может называть клуб Ducks. Свободные
   номера звука (32, 33, 55…65 …) — без записей; что игра скажет с ними, не проверено.
5. Код страны (−1 для 98/99) — вероятно, гимн/флаг; у клубов США EA ставит 20. Не проверено.
6. Хвост 16 байт у новых BIGF — MD5 файла (как у новых фото игроков); назначение хвоста неизвестно.

## 8. Инструменты

```bash
python tools/teamart.py info FILE…                       # формат, размеры, мипы
python tools/teamart.py decode FILE OUT.png [--full] [--mips DIR] [--tex N]
python tools/teamart.py roundtrip [--deep] FILE_OR_DIR…   # проверка разметки байт-в-байт (+ мипы)
python tools/teamart.py build SPEC.json OUTDIR [--only t,s,d,c,w,r,center,puck,banner,spot] [--preview DIR]
python tools/teamart.py alias SRC_ARTID DST_ARTID OUTDIR  # копия формы под другой номер
python tools/newteams_art.py [DB] [--out OUT] [--spotlight] [--jerseys] [--stadium A,B] [--centerline A,B]
```

`build` берёт SVG и SPEC (`artid`, `spotlight`, `strip_paths` — номера `<path>` знака ®, `colors` —
низ/верх «таблетки», `small_focus`/`wide_focus` — точка и увеличение крупного плана, `center_box`,
`calendar_zoom`, `league` — nhl/ahl), рендерит каждый набор в Chrome/Edge без окна (прозрачный фон),
подгоняет размеры под замеры EA, кладёт в шаблон EA того же набора и переписывает имя растра.
Библиотечные функции прежние (`html_for`, `puck_rgba`, `RX_SETS` не менялись); новое — `html_for_ea`,
`puck_rgba_league`, `SIZE_TARGET`, `EA_MASKS`, `ea_mask`, `apply_mask`, `alpha_stats`, `fit_logo`,
`RX_TEMPLATES`, `rx_template` и параметр `build(..., ea_fit=False)`. Только стандартная библиотека Python + браузер. Подсобные
скрипты разбора (дамп базы, поиск ссылок в коде, листы превью) — `game/work/logos/scripts/`.

## 9. NHL Legacy: арт SEA/VGK (08.10.2026)

Перенос в NHL Legacy Edition (Xbox 360, TitleID 454109EC) — те же инструменты с `--game legacy`
(`tools/gameprofile.py`): шаблоны и контейнеры — из распакованных архивов Legacy
(`game/other/legacy/big/<архив>/…`), готовое — дерево `cache:` в `game/work/legacy-data/out/`
(ставит legacy-data своим install-скриптом). **В игре** (порт Legacy, 08.10.2026, проверка legacy-data,
снимки `game/work/legacy-data/ingame/t4-*.png`): логотипы Kraken и Golden Knights на выборе команд, в
стартовых составах и предматчевой заставке, табло SEA/VGK, логотип VGK в центре льда; в логе порта ни
одного промаха `cache:` по нашим файлам. Шайба, прожекторы, r, календарь — отдельно не смотрели.

**Номера.** У Legacy арт 98 и 99 заняты (Vaasan Sport, KooKoo), свободны 100–107: **SEA — 100,
VGK — 101** (файлов с этими номерами в наборах арта Legacy нет — проверено по распакованным архивам).
Прожекторы у Legacy — `spotlight/texlib_0…45` (45 — Verizon), команды берут 0…41: **SEA — 46, VGK — 47**.
База Legacy (`tools/nhl32.py` у legacy-data, `game/work/legacy-data/nhl32/nhlng.db`) так и ставит:
строки 30/31, `artid` 100/101, `spotlight` 46/47, `table` 0, арены 187/188 («Climate Pledge Arena»,
«T-Mobile Arena» — копии «EA SPORTS Arena» 181, площадка НХЛ). Проверка базы — `tools/newteams_art.py` с
`--game legacy` (свои номера Legacy; база другой игры — отказ):

```bash
python tools/newteams_art.py game/work/legacy-data/nhl32/nhlng.db --game legacy --spotlight --jerseys
```

На базе nhl32 08.10.2026 — «изменений: 0», замечаний нет (artid 100/101 только у строк 30/31, `table` 0,
арены и названия на месте, `stockteamjerseys` 703–708 — `teamartid` 100/101).

### Что у Legacy не так, как в NHL 13

| Что | NHL Legacy | Что сделано |
|---|---|---|
| шаблоны интерфейса `t0/s0/d0/c0/w0/r0`, маски растушёвки `c1/c3/c11`, `w2/w4/w5` | байт в байт как в NHL 13 | те же контейнеры и маски; s/c/w SEA/VGK вышли **байт в байт** как в NHL 13 |
| t клубов НХЛ | 24 из 30 перерисованы мельче: площадь (альфа > 128) медиана 14 980 (в NHL 13 — 17 111), w 137…212, h 97…182 (у перерисованных ≤ 169) | `SIZE_TARGET_LEGACY` t: площадь 14 980, h ≤ 166, w ≤ 191 → SEA 132×166, VGK 114×153 |
| d | почти как в NHL 13 (перерисованы 3): медиана 4 400, h ≤ 91 | d: площадь 4 400, h ≤ 88 → SEA 70×88, VGK 62×83 |
| r (только 0…29) | перерисованные — логотип в кадре t (центр 128, 128, размер как у t), отражение слабое: альфа ≤ 0,1…0,35 на ~40 px, в 10–20 px под логотипом | `html_for_r_legacy`, `R_LEGACY` (зазор 10, 0,22 → 0 за 40 px) |
| центр льда | тот же кадр (диск 388, синее кольцо 380–385, прозрачная полоса x 494…529), `centerlogo_150` той же структуры | пиксели как у NHL 13 98/99, контейнер — 3-значный `centerlogo_150` |
| **шайбы клубов НХЛ** | новый рисунок (196 из 218 шайб перерисованы): тёмная грань (21, 22, 21), светлое кольцо радиуса 92, надписи «National Hockey League» / «Official Game Puck», тонкий круг радиуса 74 с центром (127, 172), логотип прямо на грани (наибольший радиус 41…65, медиана 52), почти у всех со светлой каймой; низ — щит НХЛ, «Rondelle de match officielle» и подпись; `puck_255` (EA SPORTS) — тот же, что в NHL 13 | стиль `PUCKS['nhl_legacy']`: шаблон — шайба «Питтсбурга» `puck_23` (вне круга у всех 30 одинаково), круг до радиуса 70 закрашивается цветом грани, логотип вписан в радиус 52, кайма белая 1 px; контейнер — `puck_150` |
| шайбы АХЛ | тоже новый рисунок (овал AHL сверху, круг, клуб посередине, «Official Game Puck») | стиль `PUCKS['ahl_legacy']` — для CV/HSK (102/103), ниже |
| баннер | `banner_93`, `banner_150` — те же | как в NHL 13, контейнер `banner_150` |
| прожекторы | тот же стиль (логотип на прозрачном, 256² DXT5), часть перерисована (Liiga), `texlib_33` той же структуры | как в NHL 13 (пиксели те же), номера 46/47 |

### Сборка

SPEC Legacy — наследники SPEC NHL 13 (`teamart.load_spec`, ключ `"base"`). С 09.10.2026 они лежат в git, в
`tools/legacy_data/art/src/`, и `"base"` указывает на `../../../../game/work/logos/…`; ниже — прежний вид:

```json
{"base": "../../../logos/src/SEA.json", "team": "Seattle Kraken (NHL Legacy)", "artid": 100, "spotlight": 46}
{"base": "../../../logos/src/VGK.json", "team": "Vegas Golden Knights (NHL Legacy)", "artid": 101, "spotlight": 47}
```

```bash
A=game/work/legacy-data/art
python tools/teamart.py build $A/src/SEA.json game/work/legacy-data/out --preview $A/preview/logos --game legacy
python tools/teamart.py build $A/src/VGK.json game/work/legacy-data/out --preview $A/preview/logos --game legacy
python $A/scripts/verify_out.py game/work/legacy-data/out --game legacy          # сверка с шаблонами Legacy
python $A/scripts/sheet_art.py $A/preview/sheet_ui.png $A/preview/sheet_3d.png game/other/legacy/big 23 \
    "SEA (свой)=game/work/legacy-data/out:100:46" "VGK (свой)=game/work/legacy-data/out:101:47"
```

Сборка двух клубов — около двух минут (Chrome без окна). Тот же вывод даёт сборка в другую папку
(повторяемо: NHL 13-сборка SEA новым кодом совпала с `game/work/logos/out.sha1`).

| Файл (`game/work/legacy-data/out/…`) | Байт SEA / VGK | Что |
|---|---:|---|
| `fe/ion/artassets/teamlogos/t100.big`, `t101.big` | 24 624 / 19 568 | основной логотип (размер Legacy) |
| `fe/ion/artassets/teamlogossmall/s100.big`, `s101.big` | 10 672 / 10 480 | «таблетка» (как NHL 13 s98/s99) |
| `fe/ion/artassets/teamlogosdynasty/d100.big`, `d101.big` | 11 760 / 9 776 | франшиза |
| `fe/ion/artassets/teamlogoscalendar/c100.big`, `c101.big` | 10 736 / 10 800 | календарь (как c98/c99) |
| `fe/ion/artassets/teamlogoswide/w100.big`, `w101.big` | 78 128 / 85 488 | крупный план (как w98/w99) |
| `fe/ion/artassets/teamlogosreflection/r100.big`, `r101.big` | 28 656 / 23 920 | с отражением, стиль Legacy |
| `rendering/icesurface/centerlogo_100_cm.rx2`, `_101_` | 1 445 888 | центр льда |
| `rendering/puck/puck_100_cm.rx2`, `_101_` | 110 592 | шайба в стиле Legacy |
| `rendering/banner/banner_100_cm.rx2`, `_101_` | 397 312 | баннер |
| `rendering/spotlight/texlib_46.rx2` (SEA), `texlib_47.rx2` (VGK) | 135 168 | прожекторы |

### Проверено

- `verify_out.py --game legacy`: все 20 файлов — как шаблон Legacy вне пикселей и имён растров (BIGF:
  записи, Apt, заголовок XPR2, константа выборки, сцена; RW4: заголовки, описания, размеры), имена растров
  с 100/101/46/47, разбор → сборка байт в байт (контейнер, тайлинг; у RW4 — все уровни мипов, соседние уровни
  28…57 дБ).
- Листы `game/work/legacy-data/art/preview/sheet_ui.png`, `sheet_3d.png` (сверху — оригиналы Legacy
  «Питтсбурга»): размеры t/d/r как у логотипов Legacy, шайба — как шайбы клубов Legacy (кайма видна,
  кольца и надписи целы).
- NHL 13 не изменился: без `--game` новые `teamart.py`, `kitpaint.py`, `czkit.py`, `newteams_art.py` дают
  те же файлы и логи, что код до правки (итоговая сверка — 210 файлов и 19 логов: build SEA, CVF, VGK
  `--legacy`, info, roundtrip, decode, alias; paint, verify, roundtrip, unpack/pack; czkit build, verify;
  план и `--out` newteams_art); сборки совпали с `game/work/logos/out`, `uniforms/kits`, `uniforms/kits-cz`.

### Фарм-клубы CV и HSK (арт 102/103, на будущее)

База Legacy АХЛ на 32 ещё не сделана (номера решены группой: CV — 102, HSK — 103), арт готов заранее и лежит
в `out/` (номера свободны — ни один файл и ни одна строка базы на них не ссылаются, пока их не поставит база):

- t, s, d, c, w (у клубов АХЛ нет r и своего прожектора — `spotlight`/`tunnel` 34), центр льда, баннер — как у
  SEA/VGK; SPEC — `art/src/CVF.json`, `HSK.json` (наследники `game/work/logos/ahl-src/*.json`, `artid` 102/103);
- шайба — свой стиль `PUCKS['ahl_legacy']`: у Legacy шайбы клубов АХЛ тоже перерисованы (грань (21, 22, 21),
  тонкий круг радиуса ~59 с центром (127,5; 172), сверху на нём овал AHL — низ овала в 48 px над центром, по
  бокам линии, ниже «Official Game Puck»; логотип клуба в круге, рамка ±41 по вертикали, наибольший радиус
  45…54). Шаблон — шайба «Провиденса» `puck_150`: круг радиуса 48 закрашивается цветом грани, кроме полосы выше
  46 px над центром (овал цел), логотип — в радиус 44 с белой каймой 1 px; низ (логотип AHL, подпись,
  Sher-Wood) — как у EA.

```bash
python tools/teamart.py build $A/src/CVF.json game/work/legacy-data/out --preview $A/preview/ahl-logos --game legacy
python tools/teamart.py build $A/src/HSK.json game/work/legacy-data/out --preview $A/preview/ahl-logos --game legacy
```

16 файлов (t/s/d/c/w 102/103 — 11…91 КБ, `centerlogo_102/103_cm` 1 445 888, `puck_102/103_cm` 110 592,
`banner_102/103_cm` 397 312), `verify_out.py --game legacy` — 0 ошибок; листы —
`$A/preview/ahl_sheet_ui.png`, `ahl_sheet_3d.png` (сверху — «Провиденс» Legacy). Форма — временная, копии
формы клубов АХЛ Legacy (`teamart.py alias … --game legacy`, uniforms.md §12).

### Проверить в игре (Legacy)

1. «Играть сейчас» SEA — VGK: t на выборе команд, табло, центр льда хозяина — **видны** (см. выше); ещё не
   смотрели: s/d/c/w на других экранах, r — если экран-карусель есть в Legacy; шайба хозяина вблизи;
   прожекторы при выходе (46/47).
2. В логе порта (аналог `NtCreateFile FAILED` в NHL 13) — не должно быть запросов `cache:\…\t100.big`,
   `centerlogo_100_cm.rx2` и т. п. без ответа.
3. Шайба: кайма и размер логотипа рядом с шайбами других клубов; низ — щит НХЛ.
4. Свободные `.rx2` в `cache:` — без chunklzx (как в NHL 13; у порта puckhead73 `cache_root/guest` — слой
   поверх `_compiled`, должно читаться так же).
5. CV/HSK — только когда база Legacy получит АХЛ на 32 (`artid` 102/103): логотипы в меню франшизы, шайба
   АХЛ (овал и линии целы), центр льда хозяина.
