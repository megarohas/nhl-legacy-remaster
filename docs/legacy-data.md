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
| Франшиза на 32: поля команды 6 бит и в заголовках таблиц базы; ведомости состава ≤ 100 млн | `tools/nhl32.py` (`widen_headers`), `tools/roster --payroll-max 100` | ✔ (legacy-port, база e9096f07) франшиза: VGK 22 игрока, ARZ 23 своих, пики 32 × 42 с owner 1…32, сим 19.09 → 11.10 без зависания; ведомости — с базы 84130656 (в CACHE с 23:05) |
| Составы 2026/27 (рейтинги по статистике, свободные агенты, тон кожи, Liiga) | `tools/roster … --game legacy` | ✔ составы, звенья, номера, буквы, звёзды команд |
| Портреты игроков 2026/27 (НХЛ, Liiga) | `tools/photos.py --game legacy` | ✔ Starting Lineups — наши фото (McCann, Barbashev…) |
| Экипировка по фото (обмотка, гетры, свитер, визор) | `python -m roster.equipment --game legacy apply` | ✔ визор по правилу, обмотка (матч SEA–VGK) |
| Шрифт меню NHL 12 | `tools/fefont.py --game legacy` (помощник fe) | ✔ меню, выбор команд, составы, табло |
| Музыка Best of NHL (16 песен, названия, обложки) | `tools/music.py --game legacy` (помощник music) | ✔ EA SPORTS Trax — все 16 песен, играет наша |
| 3D: гетры, обмотка до носка (и у клюшек на льду), край свитера NHL 10 | `rw4mesh.py`, `sticktape.py`, `jersey10.py --game legacy` (помощник models) | ✔ файлы берутся из cache: (промахов нет); вблизи не разглядывали |
| Логотипы, лёд, шайба, баннер, прожекторы, форма SEA/VGK (арт 100/101) | `teamart.py`, `kitpaint.py`, `czkit.py --game legacy` (помощник art); превью формы в позе EA — `fepose.py` + `czkit.py fe` (legacy-fe, 09.10) | ✔ логотипы на выборе команд и заставке, форма в 3D, центр льда VGK; превью на Select Jerseys — манекен EA, все 6 форм ([uniforms.md](uniforms.md) §13) |
| Фон меню | варианты на выбор (у Legacy своя тёмная арена) | не ставился — решает пользователь |
| Главное меню NHL 12: фон с игроками 2026/27, плашка и кегли 34/25 | `tools/menu12_legacy.py` (помощник menu) | ✔ арена NHL 12, игроки сменяются, кольца в цвет клуба, плашка; вход/выход PLAY, Play Now, CUSTOMIZE (полный список — [fe-menu-legacy.md](fe-menu-legacy.md) §5) |
| Главное меню: без синей подложки на входе; пункты без онлайна, EXIT, панель описаний про офлайн | `tools/menu12_legacy.py` (подложка), `tools/menuitems_legacy.py` (legacy-fe, 09.10) | ✔ синего нет ([fe-menu-legacy.md](fe-menu-legacy.md) §7); меню и EXIT проверены, EXIT — только с exe legacy-port (§8) |

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

Вариант «АХЛ на 32» — накладка `game/work/legacy-data/out-ahl32/` (база с CV/HSK, их локализация и
портреты): `install-legacy-data.sh --ahl32` ставит её поверх `out/`. Франшизе с ней нужен порт с врезками
АХЛ на 32 (legacy-port их готовит); «Играть сейчас» и без них. У CV/HSK с 09.10.2026 сила как у соседей по
АХЛ (`tools/roster/ratings.py`, коммит 35cd8fe). У Legacy сохранённый OVR игроков АХЛ на ~9 ниже их
атрибутов, а новые игроки строились по связи NHL 27 и выходили на 12 пунктов атрибутов слабее. Теперь
атрибут полевых 77,0 при 76,7 у соседей, OVR 68,5 при 67,8. Изменены только строки игроков CV/HSK. С 09.10
это в `out-ahl32` (вместе с Liiga, ниже).

Пересборка всего с нуля — `bash game/work/legacy-data/build-all.sh [этап…] [--ahl32]` (этапы base, roster,
photos, equip, collect, fonts, music, models, art; сеть — только докачка недостающих портретов лиг).

Состав `out/` (08.10.2026, 23:00): 2907 файлов, 448 МБ — база и схема (2), локализация (1), шрифты (3), банк музыки
(4) и обложки EA Trax (32), портреты 1264 игроков (2528), арт SEA/VGK и CV/HSK (110), 3D (74); главное меню NHL 12 — 75 файлов, 13 МБ (`menu/files.txt`).

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
  таблицы, плюс строка Матча звёзд 32/33 в тот же день, что у EA (31.01 и 25.01), home/away — 6 бит.
  Игровые дни — только существующие в сезоне 2026/27 (с 09.10.2026). В исходном календаре Legacy
  2015/16 есть 29.02.2016, в 2027 году такого дня нет: 7 игр этого дня игра не играла, у 14 клубов
  было 83 игры (нашёл legacy-port). Теперь игры этого дня расходятся по остальным дням, 2 игры WHL того
  же дня переехали на 28.02;
- схема: вместимость франшизы на 32 (`leaguegmdata`/`leaguestaffdata` 32, `leaguedraftpick` 1344,
  `leaguetempscheduletable` 3200), поля «команда НХЛ» −1…30 → 6 бит (у Legacy без
  `leagueretirementtable` — там уже 8 бит, плюс новое `leagueplayerbiotable.tradeblockteam` и
  `exhibitiondraftpick.owner/origteamid`);
- **те же поля — и в заголовках таблиц базы** (`DB_WIDEN` → `widen_headers`, с 08.10.2026 22:48). В отличие
  от того, что считалось для NHL 13 (агент франшизы NHL 13 09.10 нашёл, что и у NHL 13 так же), Legacy строит
  таблицы франшизы по заголовкам заготовок `league*` в самой базе (из схемы берёт только вместимость
  `maxinsert`). Пока там было 5 бит, в сейве франшизы у игроков Вегаса стоял `proteam` = 32 → 0. Игра
  удаляла все записи состава VGK, и состав оставался пустым. Пики драфта VGK были без владельца, и симуляция
  висла на первой игре VGK: 9→10 октября, `rand() % 0`. Сначала казалось, что 21 игрок VGK «уехал в ARZ»: у
  неё было 45 записей. Но это удалённые записи: `tools/tdb.py` читает и их, а номер следующей свободной записи
  в первых 16 битах перекрывает `team` (`Tdb.deleted`, ниже). Живых записей у ARZ было 23, у VGK — 0. Расширяются
  `leagueplayerbiotable` proteam/draftteam/tradeblockteam, `leaguedraftpick` owner/origteamid,
  `leaguefreeagentdata` originalteamid/signedteamid, `leaguerookiedata.draftteam`,
  `leaguecontractoffers.teamnotification`, `leaguegamemodesvars.team`, `leaguescoutvisits.team`,
  `exhibitiondraftpick` owner/origteamid. При `--ahl32` FA/gamemodesvars/scoutvisits получают 7 бит, `leagueteams.ahlaffiliate` — 8. Значения не
  меняются, у NHL 13 вывод прежний. Поля 0…31 без «+ 1» не трогаются, как в NHL 13: teamid штаба,
  сделок, предложений, RFA и выкупов — 31 туда помещается. Сейвы франшизы, созданные на старой базе,
  хранят свою 5-битную раскладку, их нужно создавать заново. Проверка — заголовок против схемы по всем
  полям: расходятся только home/away календарей (в базе 6 бит, в схеме 5, как в NHL 13);
- **`--ahl32`** (по просьбе legacy-port): Coachella Valley и Henderson — на Custom 02/03 = 224/225, арт
  102/103 (формы — копии Springfield/Providence у помощника art, [uniforms.md](uniforms.md) §12), арена —
  копия Cedar Park Center; АХЛ Legacy 2015/16 (30 клубов, 8/7/8/7) → 8/8/8/8: Texas — в Central, Lake Erie
  (Кливленд) — в North, как в нынешней АХЛ; `ahlschedule` — 32 × 72 (8 игр с соперником по дивизиону, 2 —
  с другим дивизионом конференции, 36 дома); `ahlaffiliate` — 8 бит (SEA → CV, VGK → HSK); строки Матча
  звёзд нет (126 команд — предел кода, как в NHL 13 `--ahl32`).

## Составы 2026/27 (`tools/roster --game legacy`)

```bash
python tools/roster all --offline --game legacy --stats-ratings --fa --fa-only --skin --league liiga --payroll-max 100
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

`--payroll-max 100`: контракты конвейера — заглушка по OVR, и ведомости клубов выходили 94–135 млн. Потолок 2026/27 — 104 млн, его ставит врезка legacy-port. Игра считает ведомость по составу НХЛ (`exhibitionrostertable`), это legacy-port сверил на экране Be a GM: у ANA «Cap Value $99.050M» — ровно сумма по 26 строкам состава. Со 2-го сезона игра поднимает потолок до самой дорогой ведомости, а клуб пользователя сверх потолка дальше не пускает. Поэтому у клубов дороже 100 млн контракты (по `proteam`) выше минималки 850 тыс. ужимаются одним коэффициентом до 100 млн: так получилось у 28 клубов, у ANA/VAN/CGY/SEA ведомость 94–99 млн. Настоящие кэп-хиты — CapWages: платный API или разбор страниц, решение за пользователем ([research-data-sources.md](research-data-sources.md) §2).

`--fa-only` (с 09.10.2026): в пуле свободных агентов (`exhibitionfreeagents`) остаются только 39 настоящих
(`--fa`). Раньше там оставались ещё 35 свободных агентов Legacy 2015 года (Ehrhoff, Zidlicky, Visnovsky…),
и к июню 2027 они были в топе хаба свободных агентов франшизы (нашёл legacy-port). Строки этих игроков
остаются в базе, как у игроков без клуба.

**Сейвы франшизы читать без удалённых записей.** В базах игр (исходные NHL 13 и Legacy, наша) удалённых
записей нет, а в сейвах франшизы есть. Например, во 2-м сезоне `leaguerostertable` — 167 удалённых,
`leaguerookiedata` — 1008. Заголовок таблицы: +0x18 (u16) — число удалённых, +0x1A — голова списка
свободных. У удалённой записи первые 16 бит — номер следующей (0xFFFF — конец). `Tdb.deleted(таблица)`
отдаёт их номера, и в подсчётах по сейву эти строки надо пропускать. Без этого получались «DAL 38 в составе НХЛ»
и «SPR 52 в АХЛ», а живых во 2-м сезоне в НХЛ 21–24, в АХЛ 22–36 (поправка legacy-port, 01:15). Кроме удалённых, не
записи и места `[current, max)`: у таблиц сейва `rows` = max, а там байты 0xDB (у `leaguerostertable` 3318 строк
с `team` 94) или остатки прошлого сезона (календарь, статистика матчей, `leaguestates`). Перебирать сейв — по
`Tdb.live_rows(таблица)`: `[0, current)` без удалённых (docs/save-editing.md, «Живые записи»).

**Сила новых клубов Liiga** (коммит 09.10.2026, `ratings.Model.calibrate`). У Legacy сохранённый OVR вне НХЛ ниже
атрибутов: у Liiga базы на 9,3, у SHL на 8,5, у DEL на 9,4. Клубы Liiga, которые пересобирает конвейер,
строились по связи NHL 27 (атрибуты ≈ OVR) и выходили на 10,5 пункта атрибутов слабее: 63,5 при 74,0 у
исходной Liiga, 75,0 у SHL и 73,1 у DEL. Теперь медиана OVR и связь OVR с атрибутами берутся по игрокам
Liiga базы, атрибут полевых 74,8, вратарей 75,1. Клубы НХЛ (атрибуты EA NHL 27 как есть) не трогались: атрибут
полевых 80,7 при 82,6 у исходной НХЛ Legacy, OVR 82,3 при 81,7. У NHL 13 OVR ≈ атрибуты во всех лигах,
калибровки Liiga там нет. 09.10.2026 03:00 основная база с этой правкой (md5 958f4b6d) поставлена в `out/db/` и
в CACHE порта. Прежняя (fceb2d42) лежит в `game/work/legacy-data/backup-cache/`. Накладка `out-ahl32` (CV/HSK и
Liiga, 34dfe267) обновлена, в CACHE её не ставили. Установщик теперь пускает установку и при запущенной
игре, если её `user_data_root` (из командной строки или `nhllegacy.toml`) — другая папка, например тестовая
копия legacy-port.

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
  (там заглушка: 800 одинаковых строк с одним game_id), вратарская амуниция (щитки, маска) — по вратарю:
  у новых вратарей на строках доноров — щитки донора (у Daccord — со звездой «Далласа»), как и в NHL 13.

Итог (08.10.2026): 1274 игрока (НХЛ 798 + 437 Liiga + 39 свободных агентов), 387 сопоставлено (у Legacy
база 2015 года — сопоставленных больше, чем в NHL 13), 887 в строках доноров, проверки конвейера и CRC
— OK; Liiga — медианы 65/65/63 (как у Liiga в Legacy); портреты — у 1264 (фото не из НХЛ — 433 приведены
к кадру НХЛ, 61 запрос к сети за недостающими: KooKoo, Sport…; без фото 10); экипировка — обмотка 120,
гетры 86, визор по правилу 118, исключения визора −426. Вариант `--ahl32`: 1325 игроков (+51 CV/HSK из
Wikipedia), портреты у 1303, проверки OK.

## Что сделали помощники (подробно — в своих документах)

- **fe** — [fe-fonts.md](fe-fonts.md) «NHL Legacy», [fe-background.md](fe-background.md) §10: шрифт «1:1»
  (глифы и хинтинг NHL 12, таблица `name` и метрики — Legacy, `font_extents.txt` Legacy остаётся верным;
  предела размера в коде нет — буфер по размеру файла из пула `RWFontPP`); фон Legacy — тёмная фотография
  арены, перекраской «как в NHL 13» не сделать — варианты `legacy-gray`, `nhl13-muted`, `nhl13-gray` в
  `game/work/legacy-data/fe/variants/` (не ставились); главное меню NHL 12 ложится на фреймворк Legacy,
  но `menu.big`/`main.big` у Legacy свои — их сделал помощник menu (ниже).
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
- **menu** — [fe-menu-legacy.md](fe-menu-legacy.md): фреймворк фонов Legacy = NHL 13 (+`SkipEval`), фон NHL 12
  из сборки menu12 с `bg_edits` ложится как есть, кольца — по базе Legacy; `menu.big`/`main.big` — свои у Legacy,
  поэтому плашка NHL 12 пересажена в `menu.big` Legacy гибридом (полоса и косые края NHL 12 + кнопка A, «New»,
  стрелка Legacy; ширина 327 фиксирована кодом Legacy), пункты 34/25, ряды 28/45, без затухания; левая панель с
  кубком, заголовки и панель описаний внизу справа — Legacy (её подвал встроен в полосу помощи). 75 файлов
  (3 ролика + 72 картинки игроков menu12, 13 МБ), список `game/work/legacy-data/menu/files.txt`;
  пересборка — `python tools/menu12_legacy.py build`, сверка — `check`. В игре не проверялось.

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

5. 23:05–23:10 — весь out в CACHE (база 84130656, локализация, главное меню NHL 12), Release legacy-port:
   главное меню — арена NHL 12, игроки сменяются (Werenski → Crosby → Barkov → Celebrini → McDavid), фамилия
   металлом над головой, кольца в цвет клуба; плашка NHL 12 (кнопка A, ►), кегль 34; вход/выход: PLAY, Play Now →
   Select Teams → назад, CUSTOMIZE → назад; в описании GM Connected — «32-team NHL». Мелочь: в подменю на 9
   пунктов (CUSTOMIZE) подзаголовок наезжает на потускневшую табличку LEGACY EDITION под кубком.

Не проверено в игре: гетры и клюшки вблизи (повтор), край свитера сзади, клюшка на льду; табличка имени
вратаря SEA на заставке была пустой (снимок посреди анимации? — посмотреть); база `--ahl32` и франшиза на
32 (нужны врезки legacy-port); возраст (врезка года); фон меню (варианты не ставились).
