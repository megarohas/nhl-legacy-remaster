# Музыка: где лежит, формат, замена саундтрека

Вся музыка игры — меню (EA Trax) и арена (выход команд, голы, паузы, конец периода и
матча, гимны) — один звуковой банк `audio/music/music_samples.*`: 195 звуков, EA SPS с
кодеком EALayer3 (переупакованный MP3). Свой саундтрек собирается
[tools/music.py](../tools/music.py): папка с MP3/FLAC/WAV → три файла банка (и обложки
EA Trax) в раскладке `cache:`; архивы не трогаем. Кодирует и читает чужие форматы
ffmpeg — он у пользователя уже стоит (winget `Gyan.FFmpeg` 8.1.1, есть `libmp3lame`),
ставить ничего не нужно.

Разбор от 08.10.2026 (диск без TU2 — в `patch.big` аудио нет). **В игре результат ещё не
проверялся** — см. [§7](#7-что-не-проверено).

## Коротко

- Звук — `nocache.big` → `audio/music/music_samples.sbs` (358 МБ, все потоки подряд);
  оглавление `music_samples.sbr` и теги `music_musicboxdata.bin` — в `audioboot.big`
  (сжаты `chunklzx`). Игра спрашивает все три сначала в `cache:` (лог порта), так что
  свободные файлы в `game/userdata/cache/guest/audio/music/` заменяют архивные.
- Поток: блок `H` (EALayer3 v1b, стерео, 44 100 Гц, тип «поток»), блоки `D` по 16 гранул
  MP3 (9216 сэмплов), блок `E`. Гранулы — MPEG-1 Layer III без резервуара битов, в начале
  47 сэмплов PCM и отброс 1152 сэмплов — ровно задержка LAME. Поэтому MP3 от LAME
  переупаковывается в формат игры без потерь, а исходный банк разбирается и собирается
  заново байт-в-байт (все 195 потоков, оглавление и теги).
- Песни меню — 16 «EA Trax» (слоты `trax0`…`trax15`, тег `Index`); названия, исполнители
  и альбомы — простые строки в тегах `music_musicboxdata.bin`, меню показывает их
  (ключей локализации `eatrax13_*` в игре нет). У 14 песен есть вторая версия (другой
  мастер, отдельные звуки 77–83, 208–222).
- Выбор — дерево `music_graffitidata.bin`: событие `trigger_MusicEvent` с категорией
  (`music_context`) → список звуков, случайный порядок, «пулы повторов»
  (`music_repetitionpools.bin`) не дают повторяться подряд. Песни меню — из 16 EA Trax,
  включённых на экране EA Trax.
- Обложки EA Trax — `fe/ion/artassets/eatrax/e<AssetID>.big` и `eatrax_thumbs/…_thumb.big`
  (тот же BIGF + Apt + DXT5, что у фото игроков, собирает tools/playerhead.py).

## 1. Файлы

| Файл в архиве | Архив | В архиве | Разжатый | Что |
|---|---|---:|---:|---|
| `audio/music/music_samples.sbs` | `nocache.big` | 358 429 052 | — | «SBKS» + 195 потоков SPS |
| `audio/music/music_samples.sbr` | `audioboot.big` | 1 814 | 4 082 | «SBKR»: id звука → смещение в `.sbs` |
| `audio/music/music_musicboxdata.bin` | `audioboot.big` | 3 340 | 18 804 | «MBX0»: теги звуков (категория, названия песен) |
| `audio/music/music_graffitidata.bin` | `audioboot.big` | | 2 068 | «GRF0X360»: дерево выбора звука по параметрам события |
| `audio/music/music_eventsubscr.bin` | `audioboot.big` | | 1 616 | «EVT0X360»: параметры события и их значения |
| `audio/music/music_repetitionpools.bin` | `audioboot.big` | | 516 | «REP0X360»: пулы повторов |
| `audio/music/music_eventdef.csi` | `audioboot.big` | | 72 | «MOIR»: событие `trigger_MusicEvent` |
| `audio/music/music_moduledef.xml` | `audioboot.big` | | 990 | модуль `MusicBoxModule` NHL_musicbox, пул потоков `MUSC` |
| `attribdb/music.vlt` | `boot.big` | | 720 | Attrib: числа с плавающей точкой — видимо, громкости категорий |
| `fe/ion/artassets/eatrax[_thumbs]/e0…e15[_thumb].big` | `cache.big` | | 38 КБ / 3 КБ | обложки EA Trax (сцена 275×271 / 61×60) |

Порт (лог `nhl-13-port/out/game-*.log`) спрашивает в `cache:` при запуске
`audio\music\music_samples.sbr`, `…musicboxdata.bin` и остальные мелкие файлы, а
`music_samples.sbs` — когда начинает играть музыка главного меню.

Рядом, но другим форматом (AEMS-банки `ABKC` + потоки `.ast`, этим инструментом не
меняются): гудки, кричалки и сирены команд `audio/sfx/NNN_goal.abk`, `NNN_chant.abk`,
`NNN_period.abk` (`nocache.big`), звуки меню `audio/sfx/fe.abk`, трибуны `crowds.*`.

Распаковать банк (≈ 1 с): `python tools/music.py unpack` → `game/work/music/orig/audio/music/`
(мелкие файлы сразу разжимаются, как `tools/unchunk.py`).

## 2. Формат

### `music_samples.sbr` — оглавление «SBKR» (big-endian)

| Смещение | Значение | Что |
|---|---|---|
| 0x00 | `SBKR` 01 10 00 00 | магия, версия |
| 0x14 | 0x095E863F | хеш/идентификатор банка |
| 0x1C | 195 | число звуков |
| 0x24 | 0xB6 | таблица звуков: по 10 байт — u32 id, u16 число полей (1), u32 смещение полей |
| 0x28 | 0xB0 | описание полей: `SNS1` 06 04 — одно поле, 4 байта |
| 0x854… | | поля: u16 номер поля (0), u32 адрес значения |
| 0xCE6…0xFF2 | | значения: u32 смещение потока в `.sbs` |

id звуков — 1…263 с пропусками; те же id — в `music_musicboxdata.bin` и в дереве выбора.

### `music_samples.sbs` — потоки

`SBKS` + 12 нулей, дальше потоки, каждый с адреса, кратного 16 (между ними нули,
после последнего — без добивки). Поток EA SPS (все 195: версия 1, кодек 5, стерео,
44 100 Гц, тип 1 «поток», без петли):

- `H` — `48 00 00 0C` + u32 `версия<<28 | кодек<<24 | (каналы−1)<<18 | частота` +
  u32 `тип<<30 | петля<<29 | сэмплов`;
- `D` — `44` + u24 размер блока + u32 сэмплов в блоке + кадры EALayer3. Первый блок —
  18 гранул (9263 сэмпла), дальше в основном по 16 (9216), изредка 18, последний — 8…24;
- `E` — `45 00 00 0N`, N = 4…7: нули до кратного 4 конца потока.

**EALayer3 v1b** (в vgmstream — `MPEG_EAL31b`): каждая гранула MPEG-1 Layer III —
отдельный кадр со своими основными данными (резервуар битов раскрыт):

```
[флаг 8: 0x00 | 0xEE][версия 2 = 3][частота 2][режим 2][расширение режима 2][гранула 1]
[scfsi 4 на канал — только у гранулы 1][на канал: part2_3_length 12 + остальное 47 бит]
[основные данные: part2_3_length бит на канал][добивка до байта]
у 0xEE дальше: [отбросить 16 = 0][PCM-сэмплов 16 = 47][32 нуля][PCM s16be: 47 левого, 47 правого]
```

Флаг 0xEE — только у второго кадра первого блока. Игра выдаёт эти 47 сэмплов PCM, затем
декодирует MP3 и отбрасывает первые 1152 сэмпла: 1152 − 47 = 1105 = задержка кодера LAME
(576) + декодера (529). Проверено сборкой: PCM-начало ложится в декодированный поток точно
на место 1105…1151, а пересборка всех 195 потоков из разобранных гранул совпадает с
оригиналом байт-в-байт. Кодировал EA тоже LAME-подобный кодер: средний поток 150–180 кбит/с
VBR, joint stereo только MS (без intensity), длинные/короткие окна без смешанных — то же,
что даёт `libmp3lame`.

### `music_musicboxdata.bin` — теги «MBX0»

Заголовок до 0x94 (событие `trigger_MusicEvent`, не трогаем), в 0x8C — число записей и
адрес таблицы. Запись 36 байт: u32 id, пять u32 = 1, u32 тип, u32 число пар, u32 адрес
пар; пары — массив указателей (ключ, значение) и сразу строки ASCIIZ с выравниванием на 4.
Тег `VolumeType` — категория звука. У 16 песен EA Trax ещё `Index` (слот), `Artist`,
`Album`, `Title`, `AssetID` (номер обложки), у четырёх `FirstBoot = Yes` (по названию —
песни для первого запуска; читает `sub_829EAC98`), `loc_artist/loc_album/loc_title`
(`eatrax13_<N>_<Имя>_…` — таких ключей нет ни в одной из восьми баз `fe/loc/nhl_*.db`,
там только старые `eatrax12_*` от NHL 12).

Код (`nhl-13-port/generated`): `sub_829EA300` читает теги песни (Index, Title, Artist, Album,
loc_*, AssetID) в структуру; строку меню собирает `sub_8277FDF0` — берёт простой `Artist`,
кроме двух зашитых случаев: при названии «Grace» и «Turn Your Back» исполнитель
подменяется строками `eatraxArtist_Grace` / `eatraxArtist_TurnYourBack` (так своим песням
лучше не называться). Методы экрана EA Trax (`GetSongIDs`, `GetSongInfo`, `PlaySong`,
`StopSong`, `SetPlayableSongIDs`) регистрирует `sub_82F6A188`.

## 3. Что в банке

`python tools/music.py list --all` — полный список с длительностями.

| Категория (`VolumeType`) | Звуков | id | Что |
|---|---:|---|---|
| `MenuTunes` (EA Trax) | 16 | 104–117, 211, 212 | песни меню, слоты trax0…15 |
| `MenuTunes` без названий | 14 | 77–83, 208, 209, 217–222 | вторые версии 14 песен EA Trax |
| `IntroNationalAnthem` | 21 | 1–21 | гимны (16–18 с), по стране хозяев |
| `TeamIntroduction` | 14 | 86–100, 203, 216 | выход команд (~90 с; 203 — Winter Classic, 216 — Winter Classic 2012) |
| `HomeGoal` / `AwayGoal` | 13 / 10 | 66–76, 260–263 / 58–60, 243–249 | после гола хозяев / гостей (25–34 с) |
| `OffPlayGeneric` | 38 | 134–171, 214, 215, 223–226 | паузы в игре (35–59 с) |
| `OffPlayOrgan` | 23 | 172–194 | органчик (5–33 с) |
| `PenaltyHome` / `PenaltyAway` | 2 / 4 | 199, 200 / 195–198 | удаления |
| `EndOfPeriod` | 16 | 22–37 | конец периода (6–10 с) |
| `WinGame` / `LoseGame` | 6 / 6 | 50–56, 202 / 41–46, 201 | после матча (песни 3–4 мин) |
| `PlayoffOrTournamentWin` / `…Lose` | 6 / 6 | 53, 55, 57, 230–232 / 227–229, 233–235 | после серии/турнира (копии Win/Lose) |

EA Trax в оригинале: TFK, Anti-Flag, Arkells, Band Of Skulls, Bassnectar, Battleme,
Classified, My Darkest Days, Foxy Shazam, Gaslight Anthem, The Hives, Zombie Nation,
Monster Truck, The Offspring, Shinedown, The Heavy. Вторые версии сопоставлены по
огибающей громкости (корреляция 0,85–0,97, у ближайшей чужой песни — меньше 0,65) и
длительности; они чуть тише и глуше (другой мастер). Нет их только у Bassnectar и
Zombie Nation. Пары — `ALTERNATES` в инструменте.

## 4. Как игра выбирает трек

Модуль `MusicBoxModule` (`music_moduledef.xml`) по событию `trigger_MusicEvent`
с параметрами `music_context` (категория: AwayGoal, EndOfPeriod, HomeGoal,
IntroNationalAnthem, LoseGame, MenuTunes, OffPlayGeneric, OffPlayOrgan, PenaltyAway,
PenaltyHome, PlayoffOrTournamentLose/Win, ShootoutIntro, TeamIntroduction, WinGame,
UserGoalHorn, WinterClassic, WinterClassic2012), `music_home_team_id`,
`music_home_team_country`, `music_focus_player_type`, `music_match_type` (Normal,
Shootout, Tutorial, Credits), `music_player_id` проходит дерево `music_graffitidata.bin`
(40 узлов; запись — параметр, значение, вид, список) и получает список id:

- по категории — случайный звук из её списка (HomeGoal — из всех 13, без привязки к
  команде); гимн — по стране хозяев: список 1…21 идёт в порядке перечисления стран, то есть
  id = номер страны + 1 (1 Австрия, 2 Беларусь, 3 Канада, 4 Чехия, 5 Дания, 6 Финляндия,
  7 Франция, 8 Германия, 9 Италия, 10 Япония, 11 Казахстан, 12 Латвия, 13 Норвегия,
  14 Польша, 15 Россия, 16 Словакия, 17 Швеция, 18 Швейцария, 19 Великобритания,
  20 Украина, 21 США — по порядку, не на слух);
- `MenuTunes` — случайная из 16 EA Trax, на которые на экране EA Trax стоит «вкл»
  (`SetPlayableSongIDs`); 14 вторых версий — в уточняющих списках (вид 2) по режиму матча
  `music_match_type`: Credits — 77, 83, 208, 218, 220 (титры), Tutorial — остальные 9
  (обучение); устройство дерева — [§9](#9-nhl-legacy);
- повторы режут пулы `music_repetitionpools.bin`: MenuMusicPool 15, GoalTunesPool 10,
  EndOfPeriodPool 10, PenaltyTunesPool 4, OffPlayTunesPool 35, TeamIntroPool 8,
  EndGamePool 8 (по смыслу — сколько последних не повторять). В пул звук попадает по
  «типу» своей записи в `music_musicboxdata.bin` (7-е слово записи = номер пула); размер
  пула — не вместимость: у MenuMusicPool 15 — 30 звуков.

«Своя музыка» Xbox 360 (`Custom Music`: плейлисты с жёсткого диска приставки на любые
категории и команды, `UserMusicArbiter` глушит музыку игры) в порте не работает: XMP в
ReXGlue (`ref/rexglue-sdk-custom/src/src/kernel/xam/apps/xmp_app.cpp`, из Xenia) только
хранит состояние, ничего не играет и не перечисляет плейлисты.

## 5. Инструмент

```bash
python tools/music.py unpack                  # один раз: банк с диска → game/work/music/orig
python tools/music.py list [--all]            # слоты EA Trax, все звуки
python tools/music.py init  ПАПКА             # ПАПКА/tracks.txt по файлам (теги — ffprobe)
python tools/music.py build ПАПКА [OUT]       # → OUT (по умолчанию game/work/music/out)
python tools/music.py check [OUT] [--deep] [--decode trax0 58]
python tools/music.py export trax3 58 HomeGoal ПАПКА [--wav]   # оригиналы в .mp3/.wav
```

Быстрый путь: положить песни в папку (`01 - Artist - Title.mp3` …), запустить `build` —
он сам напишет `tracks.txt` (файлы по алфавиту в trax0, trax1…, названия из тегов или
имени файла), соберёт банк и обложки. Дальше править `tracks.txt` и пересобирать:

```
# слот = файл | исполнитель | название | альбом | обложка
trax0 = 01.mp3 | Megarohas | My Song | My Album | covers/my.jpg
# названия — из тегов файла (нет тегов — из имени «Исполнитель - Название»)
trax1 = Some Band - Hit.flac
# звук прежний, меняется только название
trax5 = | Battleme | Shoot the Noise, Man (Live) |
# все 13 песен после гола хозяев — одним файлом; один звук — по id (list --all)
HomeGoal = goal.mp3
id58 = away1.mp3
```

- Слот — `trax0`…`trax15`, id звука (`105`, `id105`) или категория (`HomeGoal`,
  `TeamIntroduction`, `OffPlayGeneric`…). Комментарий — только целой строкой с `#`
  (в конце строки `#` станет частью поля).
- Песня в слот EA Trax по умолчанию ставится и вместо его второй версии (`--no-alt` — не
  трогать вторые версии).
- Названия — любые длины, UTF-8; кириллица выводится с предупреждением: есть ли буквы в
  шрифте меню — не проверено. Символ `|` в названиях нельзя.
- Обложка (только trax): поле 5, иначе картинка с тем же именем рядом (`.jpg/.png/.webp`),
  иначе картинка внутри MP3/FLAC; ffmpeg растягивает её на 275×271 и 61×60, DXT5 и BIGF —
  через `tools/playerhead.py`. Нет картинки — остаётся старая обложка. `--no-covers` — не
  трогать обложки.
- Кодирование: ffmpeg → PCM 44 100 Гц стерео → LAME `-V2` (≈ 190 кбит/с; `--quality N`,
  `--bitrate K` для CBR, `--volume -3` — усиление в дБ) → переупаковка гранул в EALayer3.
  `--copy` — MP3 (MPEG-1, 44,1 кГц, стерео) переупаковать без перекодирования, длина — по
  тегу LAME; прочие файлы всё равно перекодируются. Блок больше 9600 байт (у EA самый
  большой — 9671) дробится.
- Песня 3,5 мин кодируется ~3 с (178 кбит/с, самый крупный блок 7,6 КБ); `build` всегда
  пишет полный `.sbs` (~350 МБ, остальные потоки копируются как есть) — ещё ~1 с.

**Что пишет build** (OUT устроен как `cache:`):

```
OUT/audio/music/music_samples.sbr          оглавление с новыми смещениями
OUT/audio/music/music_samples.sbs          все 195 потоков, заменённые — свои
OUT/audio/music/music_musicboxdata.bin     теги с новыми названиями
OUT/fe/ion/artassets/eatrax/e<N>.big       обложки (если были картинки)
OUT/fe/ion/artassets/eatrax_thumbs/e<N>_thumb.big
```

**Поставить** (игра закрыта, иначе файлы заняты и банк уже прочитан): скопировать
содержимое OUT в `game/userdata/cache/guest/` (появятся `audio/music/` и
`fe/ion/artassets/eatrax*/`) или сразу собрать туда:
`python tools/music.py build ПАПКА game/userdata/cache/guest`. **Убрать** — удалить
`game/userdata/cache/guest/audio/music/music_*` и `…/fe/ion/artassets/eatrax*/`; игра
вернётся к архивам.

Своя музыка — только в `game/` (вне git), как и файлы игры.

## 6. Пробная замена (собрана, не поставлена)

`game/work/music/test/` — тестовый сигнал `megarohas_test.wav` (сгенерирован: 1 с 440 Гц
только слева, 1 с 880 Гц только справа, дальше 28 с аккордов C–G–Am–F слева и арпеджио со
щелчками справа), обложка `megarohas_test.png` (белая «M» на синем) и `tracks.txt`:
`trax0` (Thousand Foot Krutch — Light Up The Sky, id 211 и вторая версия 217) →
«Megarohas — Test Signal (L/R + chords)», альбом «NHL 13 Port».

Собрано в `game/work/music/out/` (`.sbs` 345 928 940 байт, `.sbr` 4082, `.bin` 18 784,
`e0.big` 10 544, `e0_thumb.big` 2416). `check --deep`: 195 потоков разбираются, пересечений
нет; новый поток декодируется в 1 323 000 сэмплов (30,0 с) ровно, без сдвига
(отношение сигнал/шум к исходнику 48,7 дБ), левый и правый каналы на своих местах.

Проверка в игре: поставить (§5), запустить, открыть экран EA SPORTS Trax (список песен с
переключателями вкл/выкл; экран — `fe/ion/external/ion_sports07/screens/misc/01_trax.big`):
вместо TFK — «Megarohas — Test Signal» с обложкой «M». Включить только её или нажать
«Play» — должны звучать писк слева, писк справа, затем аккорды (30 с). У trax0 тег
`FirstBoot`, как в оригинале.

## 7. Что не проверено

- **Всё — в игре**: что `cache:` подхватывает банк, что меню показывает новые названия и
  обложку. По коду и формату — должно: файлы того же устройства, что у EA.
- Мелкие файлы кладутся **без `chunklzx`** (в архиве сжаты). Загрузчик (`sub_8242FC70`,
  см. [uniforms.md](uniforms.md)) узнаёт сжатие по магии, иначе читает как есть — для
  банков звука не проверено. Запасной вариант — обёртка `chunklzx` с кусками метода 0.
- Обложки: 16 байт хвоста BIGF остаются от оригинала, как у фото игроков
  ([player-photos.md](player-photos.md)) — тоже ещё не проверено в игре.
- Вторые версии песен звучат, судя по дереву выбора, в титрах и в обучении (§4) — на слух
  не проверено (по умолчанию заменяются вместе).
- Больше 16 песен в NHL 13 инструмент не делает. Для Legacy делает (§9): новый id в `.sbr`,
  запись в `.bin`, id в список MenuTunes дерева выбора. По коду NHL 13 устроен так же
  (число песен — из записей с тегом Index, под флаги «вкл» в настройках 25 байт), но не
  проверялось.
- Кириллица в названиях — зависит от шрифта меню.

## 8. Подмена на уровне порта (не делалось)

Не нужна: замена файлами в `cache:` закрывает всё. Варианты, если понадобится:

- **XMP в SDK** — включить «Custom Music» игры: перечислять папки с MP3 на ПК как
  плейлисты, играть их своим декодером в микшер хоста, отдавать игре состояние XMP.
  Работы много (API медиатеки XMP в ReXGlue нет, нужен декодер и свой голос в выводе
  звука), выигрыш — свои песни на любые события и команды из меню игры.
- **Перехват потока** — подменять при `NtCreateFile` путь `music_samples.sbs` или
  декодированные сэмплы в декодере EALayer3 (он — перекомпилированный код игры). Смысла
  мало: формат и так собирается без потерь.

## 9. NHL Legacy

Разбор от 08.10.2026 по диску Legacy (`game/other/legacy`: распакованные архивы `big/`, образ
`xex/default.bin`) и сборка «Best of NHL» для неё. Тот же инструмент с `--game legacy`
(профиль [tools/gameprofile.py](../tools/gameprofile.py)). **В игре не проверялось** — что
смотреть, ниже.

### Отличия от NHL 13

Банк того же устройства и кодека, файлы те же (`audioboot.big` → `audio/music/*`, поток —
`nocache.big`); в архиве, как у NHL 13, `.sbr`, `…musicboxdata.bin`, `…graffitidata.bin` и
`…eventsubscr.bin` сжаты `chunklzx`, остальные — нет; в `cache:` build кладёт их без сжатия
(как и для NHL 13, §7).

| | NHL 13 | NHL Legacy |
|---|---|---|
| звуков | 195, id 1…263 | 239, id 634…1004 |
| поток | EALayer3 v1b, 44,1 кГц, стерео; блок D до 9671 байт | то же у всех 239; блок D до 8455 (у сборки предел — 8455) |
| `music_samples.sbs` | 358 429 052 | 297 564 220 |
| EA Trax | 16 (Index 0…15); Artist, Album, Title, AssetID; FirstBoot у 4 | **10** (Index 0…9, id 694, 700…703, 706, 708, 726, 728, 729); **тега Album нет**; FirstBoot у trax0, trax1, trax9; `loc_*` — `eatrax16_*` (в базах строк нет и их) |
| вторые версии | 14 других мастеров | 10, **байт-в-байт копии** тех же песен: 711, 716–719, 721, 722, 989–991 |
| шапка `MBX0` | число записей в 0x8C | в 0xA4 (у события 4 параметра); адрес пары — в 0x10 у обеих |
| дерево выбора | 40 записей | 73: ещё песни на гол по команде хозяев (`music_home_team_id`, 23 звука) и режим NHL 94 (`music_match_type` = NHL94, 42 звука, в меню — 925…930) |
| пулы повторов | MenuMusicPool 15, GoalTunes 10, EndOfPeriod 10, PenaltyTunes 4, OffPlayTunes 35, TeamIntro 8, EndGame 8 | 22, 10, 16, 6, 59, 12, 9 |
| обложки | `eatrax/e0…e15` | `e0…e21` (от 22 песен NHL 15), в ходу e0…e9 |

Остальное как в NHL 13: `music_eventdef.csi`, `music_moduledef.xml` — те же байты; у
события те же параметры, у `music_match_type` есть ещё значение 16 = NHL94.

### Дерево выбора (`music_graffitidata.bin`, обе игры)

«GRF0X360»: шапка 0x1C байт (в 0x14 — число корзин хеш-таблицы, оно же число записей),
корзины по 8 байт (сколько записей, смещение первой или FFFFFFFF), записи по 16 байт
(параметр, значение, вид, смещение списка), списки (число и id по возрастанию); смещения — от
0x1C, всё подряд. Параметры и значения — из `music_eventsubscr.bin`: 1 `music_context`
(5 = MenuTunes), 2 `music_home_team_id`, 6 `music_home_team_country`, 7
`music_focus_player_type`, 9 `music_match_type` (1 Normal, 2 Shootout, 4 Tutorial, 8 Credits,
у Legacy 16 NHL94), 10 `music_player_id`. Вид 1 — список категории, вид 2 — уточнения; по
устройству игра берёт пересечение: гимн — «IntroNationalAnthem (вид 2) ∩ страна», меню в
титрах — «MenuTunes (вид 2) ∩ Credits». У Legacy в титрах — вторые версии trax3 и trax6
(718, 722), в обучении — остальных восьми. Разбор и пересборка без правок — байт в байт у
обеих игр (класс `Graffiti` в инструменте).

### Сколько песен может быть в EA Trax (по коду Legacy)

- Экран EA Trax — класс `CEATrax` (vtable `0x8203DC24`): GetSongIDs `0x8299DD60`, GetSongInfo
  `0x8299DE18`, SetPlayableSongIDs `0x8299E088` (у NHL 13 — `0x8277FD38`, `0x8277FDF0`,
  `0x82780050`). Число песен — сколько записей в таблице тегов «Index» (`0x82D7ACD0`), песня
  i — запись с `Index` = i (поэтому слоты — подряд с 0), массив флагов «вкл» выделяется под
  это число. GetSongInfo берёт Title, Artist, **Album** и AssetID — `loc_*` не читает.
- Флаги «вкл» копируются в настройки профиля без ограничения числа (`0x829F9D88`, смещение
  +1231; у NHL 13 — +1363); следующее поле настроек — через 25 байт в обеих играх.
- На том же движке NHL 15 держала 22 песни — их обложки e0…e21 остались в архиве.

Поэтому `build` у Legacy дополняет EA Trax слотами `trax10…trax21`: новый id — пропуск в
диапазоне песен (695, 696, 697…: песни NHL 15, которых в банке нет), поток — в конец `.sbs`,
`.sbr` пересобирается как у EA (таблица по id, поля, значения подряд), запись в `.bin` — по
образцу trax0 (тип 1 = MenuMusicPool; VolumeType, Index, Artist, Title, AssetID = номер
слота, Album; без FirstBoot и `loc_*`), id — в список MenuTunes вида 1 дерева выбора (его
build тогда пишет рядом с банком). Пулы повторов не правятся: размер пула — не вместимость
(§4). Если слотов снова 10 — дерево прошлой сборки build удаляет.

### Сборка «Best of NHL» (собрано)

```bash
python tools/music.py --game legacy unpack          # банк из game/other/legacy/big → game/work/legacy-data/music/orig
python tools/music.py --game legacy build best_of_nhl       # → game/work/legacy-data/out (~1,5 мин)
python tools/music.py --game legacy check --deep --compare "trax0=best_of_nhl/Animal Alpha - Bundy.mp3"
```

Те же песни, названия, альбом и обложки, что у NHL 13 (`best_of_nhl/tracks.txt`, тот же
порядок): trax0…trax9 — на места песен Legacy (и вместо их вторых версий), trax10…trax15 —
новые слоты.

| слот | id | песня | длина |
|---|---|---|---:|
| trax0 | 694 (+711) | Animal Alpha — Bundy (FirstBoot) | 3:45 |
| trax1 | 700 (+716) | Priestess — Talk to Her (FirstBoot) | 3:08 |
| trax2 | 701 (+717) | Gatsbys American Dream — Theatre | 2:49 |
| trax3 | 702 (+718, титры) | Living Things — Born Under the Gun | 2:32 |
| trax4 | 703 (+719) | Good Riddance — Darkest Days | 2:40 |
| trax5 | 706 (+721) | Jet — Get What You Need | 4:04 |
| trax6 | 708 (+722, титры) | Modern Day Zero — Down | 3:31 |
| trax7 | 726 (+989) | Millencolin — Done Is Done | 3:50 |
| trax8 | 728 (+990) | Avenged Sevenfold — Afterlife | 4:02 |
| trax9 | 729 (+991) | Fall Out Boy — Our Lawyer Made Us Change the Name of This Song So We Wouldn't Get Sued (FirstBoot) | 3:07 |
| trax10 | 695, новый | American Head Charge — Loyalty | 3:25 |
| trax11 | 696, новый | Mashlin — The Shore | 3:54 |
| trax12 | 697, новый | Avenged Sevenfold — Bat Country | 5:12 |
| trax13 | 698, новый | Cinder — Soul Creation | 3:48 |
| trax14 | 699, новый | Apocalyptica — Grace (feat. Tomoyasu Hotei) | 4:08 |
| trax15 | 704, новый | From First to Last — Two as One | 3:18 |

`game/work/legacy-data/out` (раскладка `cache:`; список — `game/work/legacy-data/music/files.txt`):

| файл | байт | было в игре |
|---|---:|---:|
| `audio/music/music_samples.sbs` | 302 342 764 | 297 564 220 |
| `audio/music/music_samples.sbr` | 5 082 | 4 962 |
| `audio/music/music_musicboxdata.bin` | 20 780 | 19 352 |
| `audio/music/music_graffitidata.bin` | 3 424 | 3 400 |
| `fe/ion/artassets/eatrax/e0…e15.big` | 15 600…18 032 | 39 152…39 472 |
| `fe/ion/artassets/eatrax_thumbs/e0…e15_thumb.big` | 2 608…3 056 | 3 312…3 696 |

`.sbs` больше оригинала на 1,6 %: смещения в `.sbr` — 32 бита, поток читается по смещению
(предела размера в коде и данных не видно; у NHL 13 стоит 322 МБ). Запасной вариант без
новых слотов (только trax0…trax9, `.sbs` меньше оригинала) — `game/work/legacy-data/music/out-10`
(`best10/tracks.txt` там же).

**Проверено** (отчёты — `game/work/legacy-data/music/`):

- `check --deep` (`check.txt`): 245 звуков, битых 0, пересечений 0; id в `.sbr` и `.bin` одни
  и те же; Index 0…15 подряд, все 16 — в списке MenuTunes; все id дерева есть в банке;
  крупнейший блок D во всём банке — 8234 байта (родной поток EA), у наших — до 7665.
- `--compare` шести потоков с исходниками (trax0, вторая версия 711, trax9, trax10, trax12,
  trax15): длина совпадает до сэмпла, сдвиг 0, уровень тот же (73,4…80,8 дБ); стыки блоков D
  и стык «47 сэмплов PCM → MP3»: шум разницы у стыка к соседнему — медиана 0,97, максимум
  2,4…4,3 (щелчок или потерянная гранула дали бы десятки). Сигнал/шум к исходнику 18–22 дБ — это
  сам LAME -V2 по уже сжатым MP3: декод потока банка совпадает с декодом MP3 от LAME бит в
  бит, а 47 сэмплов PCM-начала — с его сэмплами 1105…1151 (`lossless.txt`).
- Сверка с оригиналом (`verify.txt`): 219 из 239 потоков игры — байт в байт прежние, заменены
  20 (10 песен и их копии); в `.bin` изменены только записи песен EA Trax и добавлены 6;
  в дереве изменена одна запись (MenuTunes вида 1: +695…699, 704), шапка и корзины те же.
- Все 16 потоков — байт в байт те же, что в NHL 13 `game/work/music/out-best` (кодер
  детерминирован).

**Не проверено:** всё в игре; что 16 песен (а не 10) примут экран EA Trax и сохранение
настроек (по коду — да); включены ли новые песни по умолчанию в уже существующем профиле;
показывает ли экран Legacy альбом.

### Что проверить в игре

1. Поставить содержимое `game/work/legacy-data/out` (только файлы из `files.txt`) в `cache:`
   порта (`nhl-legacy-port/userdata/cache/guest`) при закрытой игре. В логе порта игра должна
   открыть из `cache:` `audio\music\music_samples.sbr`, `…musicboxdata.bin`,
   `…graffitidata.bin`, а с музыкой меню — `music_samples.sbs`.
2. Главное меню: играет песня из Best of NHL (не Vinyl Theatre/Panic! At The Disco…); если
   есть всплывающее «сейчас играет» — «исполнитель — название», альбом «Best of NHL».
3. Экран EA SPORTS Trax: 16 песен с нашими названиями и синими обложками «BEST OF NHL #N»;
   список прокручивается до 16-й (From First to Last), переключатели вкл/выкл работают,
   «Play» играет выбранную, падений нет.
4. Оставить включённой одну новую песню (например, trax12 Bat Country) → в меню играет она:
   новый слот попал в выбор музыки.
5. Перезапустить игру: переключатели EA Trax сохранились, прочие настройки (звук, управление)
   не сбились — проверка, что 16 флагов помещаются в настройках.
6. По желанию: музыка титров и обучения — тоже наши песни (вторые версии).

Если новые слоты мешают (падение на экране EA Trax, пустые строки, сбитые настройки) — ставить
`game/work/legacy-data/music/out-10` (10 песен на местах игры, без новых слотов).
