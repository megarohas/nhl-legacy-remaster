# Моды-данные NHL 13 → NHL Legacy (через cache:)

08.10.2026, агент legacy-data и его помощники (fe, music, models, art). Всё, что в NHL 13 ставится
файлами в `cache:` без правки кода игры, собрано для NHL Legacy Edition (Xbox 360, TitleID
`454109EC`) и проверено в своём порту Legacy (`nhl-legacy-port/`, агент legacy-port, D3D12 ROV). Оценка и
план — [legacy-port-feasibility.md](legacy-port-feasibility.md); порт — [legacy-port.md](legacy-port.md).

## Коротко

| Мод | Чем собран | В игре Legacy |
|---|---|---|
| 32 команды в базе: SEA/VGK на 30/31, сборные — 222/223, 8/8/8/8, календари 32 × 84 | `tools/nhl32.py --game legacy` | ✔ Play Now: Kraken и Golden Knights в списке НХЛ, матч SEA–VGK |
| АХЛ на 32 (CV/HSK на 224/225, 8/8/8/8, 32 × 72) — по просьбе nhl-legacy-port | `tools/nhl32.py --game legacy --ahl32` | база собрана; франшиза — с врезками nhl-legacy-port |
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
| Главное меню: без синей подложки на входе; пункты без онлайна, EXIT, панель описаний про офлайн | `tools/menu12_legacy.py` (подложка), `tools/menuitems_legacy.py` (legacy-fe, 09.10) | ✔ синего нет ([fe-menu-legacy.md](fe-menu-legacy.md) §7); меню и EXIT проверены, EXIT — только с exe nhl-legacy-port (§8) |
| Доски драфта на 32: три колонки 15 + 15 + 2 (Be a GM, фэнтези-драфт и его порядок, Live the Life) | `tools/draft32_legacy.py` + `tools/aptc.py` (legacy-fe, 11.10) | ✔ Entry Draft и фэнтези-драфт (exe nhl-legacy-port a1cb8f74), у пользователя с 11.10 16:36; в out — эти 3 ролика, Live the Life — нет ([fe-menu-legacy.md](fe-menu-legacy.md) §11) |
| Год 2015 → 2026 в надписях: стартовый экран, юридический текст, титры, подсказка FA | `tools/year2026_legacy.py` (legacy-fe, 12.10) | в игре не проверялось, не поставлено; в out и out-ahl32 ([fe-menu-legacy.md](fe-menu-legacy.md) §12) |
| Сканы голов NHL 24 игрокам с типовой головой: 178 в out-ahl32 (сканы EA не трогаются), headid = ID EA, строки `stockplayerheads` на местах доноров | `tools/scans24.py` (этап `scans24`, [heads-nhl24.md](heads-nhl24.md)) | пилот Cale Makar ✔ (пользователь, 12.10); массово — ✔ стоит: 358 файлов голов в `cache:` совпадают с out (12.10 10:17–11:39), база — 178 номеров scans24, сейв ROSTER записан 12.10 (`backup-saves/scans24-20261012-101718`); сверка 20.10 |

Набор — `game/work/legacy-data/out/` (дерево путей как в `cache:`); ставится при закрытой игре:

```bash
bash tools/legacy_data/install-legacy-data.sh            # всё из out → cache: порта
bash tools/legacy_data/install-legacy-data.sh --ahl32    # и накладка out-ahl32 («АХЛ на 32»)
bash tools/legacy_data/install-legacy-data.sh db fe/loc  # только части (начало пути)
bash tools/legacy_data/install-legacy-data.sh @game/work/legacy-data/models/files.txt   # по списку
bash tools/legacy_data/uninstall-legacy-data.sh          # снять (чужие файлы вернутся из backup/)
python tools/legacy_data/install_legacy_data.py status   # что стоит, с какими флагами, что изменит установка
python tools/legacy_data/install_legacy_data.py diff     # список файлов, которые установка поменяет или уберёт
python tools/legacy_data/install_legacy_data.py verify   # всё поставленное = нынешней сборке? (иначе код 1)
```

`status`, `diff` и `verify` (с 20.10.2026) только читают, игра им не мешает. Без флагов они берут флаги последней
полной установки (`install-flags.txt`).

Папка `cache:` порта ищется по порядку:
1. переменная `CACHE`;
2. строка «CACHE: …» в `game/work/status/legacy-port.md` (личный файл, сейчас `nhl-legacy-port/userdata/cache/guest`);
3. `user_data_root` из `nhllegacy.toml` рядом с `nhl-legacy-port/out/build/win-amd64-release/nhllegacy.exe` +
   `cache/guest`.

`status` пишет, откуда взята папка. Работает `tools/legacy_data/install_legacy_data.py`
(2500 файлов — секунды). Список поставленного — `game/work/legacy-data/installed.txt`, прежние чужие файлы —
`game/work/legacy-data/backup/`. Своя папка для них — `LEGACY_DATA_STATE`. Проверка на копии userdata ставится
так: `CACHE=копия LEGACY_DATA_STATE=папка bash tools/legacy_data/install-legacy-data.sh`, и установку
пользователя она не трогает. При запущенной игре установщик ставит только тогда, когда у неё другая
`user_data_root`, например тестовая копия legacy-port.

Скрипты и спеки legacy-data лежат в git, в `tools/legacy_data/`. Там установщик, обёртки, `build-all.sh`,
`make_out_ahl32.py`, `models/*.sh`, а также `art/src` и `art/scripts` помощника art. В `game/work/legacy-data/`
остаются только выход сборки и временное: `out/`, `out-ahl32/`, рабочие папки этапов, `installed.txt`.

**`db/draft_roster.db` — старт франшизы «NHL Entry Draft» (09.10.2026, с 10.10 — 10 таблиц).** Этот старт берёт
составы не из `nhlng.db`, а из `db/draft_roster.db`. У EA этот файл лежит в `cacheboot.big` (1,9 МБ): 10 таблиц,
`exhibition*` и `stockteamsalaryextras`, составы на драфт 2015, строка `db/draft_roster.db` есть в образе exe. Пока
файла не было в `cache:`, франшиза со старта драфта шла на составах 2015 (у Анахайма средний возраст 39).
- **09.10 — полная копия нашей базы.** Проверено на копии `nhl-legacy-port/userdata-p2ed`, 15:56–16:00: франшиза
  «NHL Entry Draft» за Анахайм — июнь 2026, средний возраст 24,7, в составе Terry и Vatrano. В логе
  `draft class 2026: real players 66 of 1289`, было `0 of 1492`.
- **10.10 — только 10 таблиц EA-оригинала, с нашими данными** (`tools/legacy_data/draft_roster.py`). С полной копией
  франшиза со старта драфта получала 2 лишние таблицы: `stockintltourneyplayerstats` и `stockintltourneygoaliestats`.
  Сейв при создании выходил больше буфера сохранения — 51 таблица при буфере на 49, порча кучи. Разбор —
  [legacy-port.md](legacy-port.md), «Старт «NHL Entry Draft»: две лишние таблицы…». В файле — те же 10 таблиц, что
  у EA, из нашей базы: блоки в прежнем порядке, каталог и `db_size` заново, CRC пересчитаны.
  - Для `--ahl32` получается 838ca6a0 — байт в байт тот же файл, что nhl-legacy-port проверил в игре
    (`draft_roster_min10.db`). Select Team как с полной копией, класс драфта тот же, сейв при создании — 49 таблиц,
    auto draft 2026 цел. Без `--ahl32` — 2c28ecaa.
- **Где собирается.** `build-all.sh`: этапы `collect` (и `--ahl32`) и `fixdb` пишут `draft_roster.db` рядом с
  `nhlng.db`. Ставит его общая установка из `out/` (и накладка `--ahl32`), снимает `uninstall-legacy-data.sh`.
  Накладка NHL 24 своего `draft_roster.db` не кладёт: её правки этих 10 таблиц не касаются, этап `nhl24` это
  проверяет.
- **Папка для друзей.** `nhl-legacy-port/scripts/make_dist.sh --mods` берёт `draft_roster.db` из `cache:`. Если его там
  нет, скрипт кладёт копию `nhlng.db` — это прежний вариант с двумя лишними таблицами.
- **Откат.** Удалить `cache\guest\db\draft_roster.db` — старт драфта снова возьмёт составы 2015 с диска. Или вернуть
  прежние файлы из бэкапа установки (ниже, «У пользователя»).

**Восстановлено после инцидента 09.10** ([incident-2026-10-09.md](incident-2026-10-09.md)), 16:10–17:20.
- **Что было сломано.** `uninstall-legacy-data.sh` оказался чужим текстом (кусок PIL). `install-legacy-data.sh`
  остался на D: как SUSPECT. От `install_legacy_data.py` уцелел только `.pyc`, `make_out_ahl32.py` не было вовсе.
  `art/scripts` и `art/src` помощника art тоже пропали.
- **Чем восстановлено.** Скрипты собраны по транскриптам агента legacy-data и его помощников: исходная запись плюс
  все правки по порядку. `install_legacy_data.py` сверен с уцелевшим `.pyc` — 0 расхождений по коду, константам,
  именам и таблицам строк. `models/*.sh` целы, они байт в байт совпадают с транскриптом помощника.
- **Состояние CACHE пользователя.** Он стоит в варианте `--ahl32`: 2910 путей из `installed.txt` и 2 своих
  файла порта.
- **Ремонт `out/` и `out-ahl32/`.** Пропавшие 25 файлов скопированы из CACHE: 2 файла музыки, 19 портретов,
  3 шрифта, 1 текстура. Схема основной базы восстановлена (md5 c8009589). Исходники Legacy заново распакованы из
  `game/other/legacy/disc/cacheboot.big` в `game/work/legacy-data/extract/cacheboot/` (db, fe/loc), они совпадают с
  анкерами. `nhl32.patch_meta` по ним даёт ровно c8009589 (основная) и 8ae5e145 (как в CACHE).
- **Проверка на копии** (`game/work/legacy-data/check-ud/`, `tmp/check_install.py`), всё сошлось:
  - uninstall → остаются только 2 файла порта;
  - install `--ahl32` с нуля → копия совпадает с CACHE пользователя байт в байт (2912 файлов), `installed.txt` —
    тот же набор;
  - install без `--ahl32` → совпадает с CACHE, кроме 4 файлов, перекрытых накладкой; там версии `out/`;
  - `--ahl32` поверх → снова совпадает с CACHE;
  - `uninstall db`, затем полный uninstall → снова только файлы порта.
- **Чего нет до сих пор.** Пропали все `*.json`, `*.xml` и `*.html` в `game/`. Это кэш сети
  `game/work/roster-cache`, `write.json`, `players.json`, `photos.json` и `artid-registry.json`. Поэтому этапы
  `roster`, `photos`, `equip` и накладка `--ahl32` (`make_out_ahl32.py`) пересоберутся только после `fetch` из
  сети (ниже). Остальное восстановлено, сухой прогон сходится с `out/` (следующий раздел).

**Пайплайн с нуля (09.10.2026, 17:30–20:00).**
- **Справочное дерево.** `game/other/legacy/big/` сверено с диском `game/other/legacy/disc/*.big`
  (`tools/legacy_data/restore_big.py`: повторная распаковка во временную папку, свой пул процессов). Итог:
  - добавлено 144 файла: схемы `db` и `fe/loc`, шрифты, `crowddata` (64), `attribdb`, речь;
  - заменено 35 испорченных (неверно восстановленных: другие байты того же размера) — прежние лежат в
    `game/work/legacy-data/_stale/other-legacy-big-20261009-170023/`;
  - лишних нет;
  - отчёт — `game/work/legacy-data/extract/restore_big-20261009-170023.tsv`.

  Шрифты NHL 12 для этапа `fonts` (4 `*.ttf`) дораспакованы так же:
  `--disc game/other/nhl12/disc --big game/other/nhl12/big --pattern '^fe/ion/fonts/'`.
- **Справочные клоны `ref/`.** В `nhl-legacy-recomp` и `nhl-modding-studio` удалённые файлы рабочих копий
  возвращены из их собственного git (только удалённые, `git restore --source=HEAD`; `git fsck` чист). Восстановлено
  177 и 339 файлов. Из `nhl-legacy-recomp` инструментам арта нужен `unpack_big.py`.
- **Спеки арта** (`tools/legacy_data/art/src/`) теперь без `"base"` на спеки NHL 13: база встроена, тексты взяты из
  транскриптов агентов logos/uniforms. Пути к SVG ведут в `game/work/logos|uniforms` (вне git). У SEA цвета
  «таблетки» — `#355464`/`#99D9D9`, как в спеке на момент сборки 08.10.
- **Кольца фона главного меню.** `spec.json` menu12 пропал, в транскриптах его нет. Места → клуб восстановлены
  обратным счётом по фону в `out/` — `tools/legacy_data/menu/menu12-rings.json`. `build-all.sh` берёт `spec.json`,
  если он есть, иначе этот файл.
- **Модель позы для превью формы** (`game/work/legacy-data/fepose/pose.bin`) пересчитана командой
  `tools/fepose.py fit --game legacy` по уцелевшему `set-legacy.npz`. Нужен питон с numpy и Pillow: venv
  `game/work/menu12/venv` пропал, взят `game/work/nhl24/venv`. В этап `art` добавлен `czkit.py fe`.
- **Сухой прогон в отдельную папку.** `LEGACY_DATA_WORK=папка bash tools/legacy_data/build-all.sh …` — переменную
  понимают `gameprofile`, `photos.py`, `roster`, установщик и `models/*.sh`. Прогон шёл в
  `game/work/legacy-data/dry/`, этапы base, collect, fonts, music, models, art, menu. Составы с портретами подложены
  из рабочей папки, потому что без сети их не собрать. Результат — из 2910 файлов `out/` байт в байт совпали 2907:
  база, локализация с правками меню, музыка, портреты, меню, 3D и арт. Разница только в 3 шрифтах: у них в TTF
  другое время сборки (`head.modified`). Найдены и исправлены ошибки «с нуля»: `build-all.sh` не создавал
  `nhl32/`, `models/*.sh` — `models/`.
- **Что нужно из сети** (`python tools/roster fetch …`, пауза ≥ 1 с, около 2200 запросов, порядка часа; сам не
  запускал):

  | Источник | Запросы |
  |---|---|
  | api-web.nhle.com | составы 32 клубов; карточки landing ≈ 1300 игроков (НХЛ, АХЛ CV/HSK, свободные агенты) |
  | search.d3.nhle.com | 1 общий + ≈ 50 по именам игроков АХЛ |
  | api.nhle.com/stats/rest | bios полевых и вратарей за 2024/25–2026/27 (≈ 6) |
  | ea.com/games/nhl/ratings | 6 страниц |
  | nhlratings.net | 32 клуба + 13 вратарских списков + ≈ 740 игроков |
  | dailyfaceoff.com | 32 страницы звеньев |
  | liiga.fi | состав и статистика 4 сезонов (≈ 9) |

  Wikipedia (капитаны, клубы АХЛ) и фото (`roster-cache/photos`) — в кэше.
- **Порядок после fetch:**
  1. `python tools/roster build …` — флаги как в `build-all.sh`.
  2. `python tools/legacy_data/registry_from_db.py game/work/legacy-data/roster/players.json` — artid новых
     игроков по нынешней базе, иначе портреты получат другие имена.
  3. `python tools/roster lines`, `match`, `write`, `report`, затем этапы photos, equip, collect.
  4. С `--ahl32` — то же для `roster-ahl32`, потом `make_out_ahl32.py`.
  5. Сверка с `out/` — `game/work/legacy-data/tmp/cmp_dry.py` (на копии, `LEGACY_DATA_WORK`).

Вариант «АХЛ на 32» — накладка `game/work/legacy-data/out-ahl32/` (база с CV/HSK, их локализация и
портреты): `install-legacy-data.sh --ahl32` ставит её поверх `out/`. Франшизе с ней нужен порт с врезками
АХЛ на 32 (nhl-legacy-port их готовит); «Играть сейчас» и без них. У CV/HSK с 09.10.2026 сила как у соседей по
АХЛ (`tools/roster/ratings.py`, коммит 35cd8fe). У Legacy сохранённый OVR игроков АХЛ на ~9 ниже их
атрибутов, а новые игроки строились по связи NHL 27 и выходили на 12 пунктов атрибутов слабее. Теперь
атрибут полевых 77,0 при 76,7 у соседей, OVR 68,5 при 67,8. Изменены только строки игроков CV/HSK. С 09.10
это в `out-ahl32` (вместе с Liiga, ниже).

Пересборка всего с нуля — `bash tools/legacy_data/build-all.sh [этап…] [--ahl32]` (этапы base, roster, photos,
equip, collect, retire, fixdb, utah, ahl, nhlattrs, useredits, tape, goaliegear, fonts, music, models, art, logos, menu, nhl24; сеть —
только докачка недостающих портретов лиг). Этап `menu` (`menu12_legacy.py`, `menuitems_legacy.py` и
`draft32_legacy.py` — доски драфта на 32, `year2026_legacy.py` — год 2026 в копирайтах) идёт после `collect`: тот кладёт в `out/` локализацию nhl32 без правок меню, а
`menuitems_legacy.py` вносит их снова.

Этап `logos` (с 10.10) идёт после `art`: логотипы клубов 2026/27 агента logos ([logos-2026.md](logos-2026.md)) —
готовые файлы `game/work/logos/out-nhl` и `out-ahl` по их `manifest.json`, со сверкой md5 (`tools/logos/outcopy.py`),
только в `out`. Нет манифеста — папка пропускается. Пересечений с `out`, `out-ahl32`, `out-nhl24`, `utah/out` и
пакетами NHL 24 (`pack`, `pack-all`) нет, кроме одного намеренного у АХЛ: у HSK (арт 103) `art` пишет прежний щит,
`logos` заменяет его нынешним. У накладок `out-ahl32` и `out-nhl24` арта клубов нет, вернуть прежний щит они не могут.
Этап `art` без `logos` вернёт прежний щит HSK. 10.10 (11:41) в `out` добавлено 294 файла НХЛ (манифест 475252db); у
АХЛ манифеста ещё нет.

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
| cache: порта | `game/userdata/cache/guest/` | из статуса nhl-legacy-port (`NHL_LEGACY_CACHE`) |
| лиги (строки) | НХЛ 0–31, АХЛ 32–61, SHL 62–73, Liiga 74–87, DEL 88–101, Extraliga 102–115, NLA 116–127, сборные 128–148, OHL/QMJHL/WHL 149–208, проспекты 209/210, легенды 211–213, Зимняя классика 214–217, Custom 218–247 | НХЛ 0–31, АХЛ 32–61, SHL 62–75, Liiga 76–90, DEL 91–104, Extraliga 105–118, NLA 119–130, Норвегия 131/132, сборные 133–153, CHL 154–213, проспекты 214/215, Зимняя классика 216–219, EASHL 220/221, Custom 222–251 |
| свободный арт | 98–101 | 100–107 (98 — Vaasan Sport, 99 — KooKoo) |
| рейтинги | `p_*`, `g_*`, `p_style`, `g_style` | `c_*`, `playerstyle` (шкала та же: − 36, 6 бит; стили те же) |
| artid / портреты | 14 бит; ≤ 12000 → `p8001_12000`, больше — `silhouettes` | 16 бит; **≤ 60000** → `p8001_12000` |
| типовые головы | 10000–10181 | 60000–60210 |

`gameprofile.check_db()` останавливает инструмент, если база или сейв — другой игры (по таблицам:
`nhlfutureschedule` есть только у Legacy, `fcc_*` — только у NHL 13; по обёртке сейва). Константы,
нужные одному инструменту, живут в нём по ключу профиля (`MUSIC` в music.py, `LOWER_NAMES` в fefont.py).

## Сезон: `tools/season.py` (20.10.2026)

Под какой сезон собираются данные, решает одна настройка — переменная `NHL_SEASON` (первый год сезона,
по умолчанию 2026, то есть 2026/27). Её читают все этапы: составы (`roster/common.py` `SEASON`, `SEASON_YEAR`),
АХЛ (`roster/ahl_ht.py`, `ahl2026_slots.py`), контракты, `nhl32.py`, кэш портретов (`roster-cache/photos/<сезон>/`),
год в копирайтах (`year2026_legacy.py`) и `build-all.sh` (кэш клубов HockeyTech `teams-<id>.json`).

```bash
python tools/season.py                              # что видят инструменты: год, номер сезона, season_id АХЛ
NHL_SEASON=2027 bash tools/legacy_data/build-all.sh # вся сборка под 2027/28
NHL_SEASON=2027 NHL_AHL_SEASON_ID=<номер> bash tools/legacy_data/build-all.sh   # если номера АХЛ нет в таблице
```

- **Номер сезона АХЛ (HockeyTech).** Таблица `HT_SEASON_IDS` в `tools/season.py` (2026 → 94). Нового сезона там нет —
  задайте `NHL_AHL_SEASON_ID` или допишите таблицу. Список сезонов с номерами:
  `cd tools && NHL_SEASON=2027 python -m roster.ahl_ht summary`. Без номера этап АХЛ не скачивает и
  `build-all.sh` его пропускает.
- **Год в игре** задаёт cvar порта `season_year` (лаунчер, [launcher.md](launcher.md)). Он должен совпадать с
  `NHL_SEASON`, иначе возраст игроков и даты разойдутся.
- **Что настройка не меняет — это данные сезона, их правят руками:** таблица слотов АХЛ (`ahl2026_slots.py` `SLOTS`:
  какие клубы HockeyTech занимают 32 слота EA), потолок зарплат (`contracts.py` `CAP`, врезка порта
  `nhl_salary_cap`), сумма минимального контракта в подсказке (`year2026_legacy.py`, `nhl_salary_min` порта),
  страницы контрактов клубов. Имена файлов `ahl2026*`, `year2026*` — исторические.
- Проверено 20.10: с настройкой по умолчанию всё как раньше (номер 20262027, АХЛ 94, папка портретов 20262027,
  локализация `year2026_legacy.py` из того же входа — побайтно та же).

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
  было 83 игры (нашёл nhl-legacy-port). Теперь игры этого дня расходятся по остальным дням, 2 игры WHL того
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
- **`--ahl32`** (по просьбе nhl-legacy-port): Coachella Valley и Henderson — на Custom 02/03 = 224/225, арт
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

`--payroll-max 100`: контракты конвейера — заглушка по OVR, и ведомости клубов выходили 94–135 млн. Потолок 2026/27 — 104 млн, его ставит врезка legacy-port. Игра считает ведомость по составу НХЛ (`exhibitionrostertable`), это nhl-legacy-port сверил на экране Be a GM: у ANA «Cap Value $99.050M» — ровно сумма по 26 строкам состава. Со 2-го сезона игра поднимает потолок до самой дорогой ведомости, а клуб пользователя сверх потолка дальше не пускает. Поэтому у клубов дороже 100 млн контракты (по `proteam`) выше минималки 850 тыс. ужимаются одним коэффициентом до 100 млн: так получилось у 28 клубов, у ANA/VAN/CGY/SEA ведомость 94–99 млн. Настоящие кэп-хиты — CapWages: платный API или разбор страниц, решение за пользователем ([research-data-sources.md](research-data-sources.md) §2).

`--fa-only` (с 09.10.2026): в пуле свободных агентов (`exhibitionfreeagents`) остаются только 39 настоящих
(`--fa`). Раньше там оставались ещё 35 свободных агентов Legacy 2015 года (Ehrhoff, Zidlicky, Visnovsky…),
и к июню 2027 они были в топе хаба свободных агентов франшизы (нашёл nhl-legacy-port). Строки этих игроков
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

## Последний бит записи — флаг движка: поломка `leaguerookiedata.draftteam` (10.10.2026)

Нашёл legacy-port. У каждой таблицы TDB заголовок +0x0C равен reclen·8 − 1, и движок держит в этом последнем бите записи
флаг «запись свободна»: у живых строк 0, у удалённых 1. Это сверено по всем 134 таблицам сейва BE A GM. В базах EA этот
бит свободен у всех таблиц.

- **Поломка.** `tdb.widen()` переносил расширенное поле в конец записи. Если поле доходило до последнего бита, запись не
  удлинялась. У нас так вышло ровно с одной таблицей: `leaguerookiedata.draftteam`. Поле расширено до 6 бит (франшиза
  на 32) и легло в биты 58…63 при reclen 8 (у NHL 13 поля таблицы на бит короче, там бит 63 остался свободным).
- **Что видно в игре.** Младший бит номера клуба стал флагом. Новичок клуба с чётным номером (draftteam = номер + 1,
  нечётный) для игры — удалённая строка.
  - Пул драфта (82A341D0) их пропускает: в BE A GM10 из 357 строк у 107 последний бит 1.
  - Второй драфт франшизы ломается: 159 разных игроков на 224 выбора, выбираются ветераны.
  - AI не подписывает таких новичков.
- **Исправление.**
  - `tools/tdb.py` `widen()`: запись растёт с запасом под флаг (`used + 1`).
  - `tools/legacy_data/fix_flagbit.py` чинит уже собранную базу: у такой таблицы запись становится на 4 байта длиннее,
    поля остаются на местах. У `leaguerookiedata` теперь reclen 12, +0x0C = 95. В базе строк нет, таблицу франшизы
    игра строит по заголовку, поэтому меняется только он. Повторный запуск ничего не меняет.
  - `build-all.sh`, этап `fixdb` после `collect`: чинит `out/db` и `out-ahl32/db`, `draft_roster.db` — копия.
  - Базы теперь: `out` 10a2335d, `out-ahl32` 59b03a68 (были 958f4b6d / 34dfe267). Накладка NHL 24 пересобрана на них.
- **NHL 13 не задета.** Её расширенные таблицы последний бит не занимают: `leaguerookiedata` кончается на бите 63 из 64,
  проверено по `game/work/nhl13-franchise/nhl32-wide3`. Поэтому новый расчёт длины даёт для NHL 13 те же записи.
- **У пользователя** в `cache:` пока база 34dfe267 с этой ошибкой. Исправленная ставится полной установкой
  `install-legacy-data.sh --ahl32`: меняются только `db/nhlng.db` и `db/draft_roster.db`. Ставить её нужно до того, как
  пользователь начнёт свою франшизу; решение — за координатором. Своих франшиз у пользователя нет (nhl-legacy-port), в
  его userdata — тестовые сейвы.
- **Сейвы франшиз, начатых на прежней базе.** В сейве у таблицы своя раскладка, её чинит
  `fix_flagbit.py --save СЕЙВ КОПИЯ --meta META`. Запись становится на 4 байта длиннее, поля остаются на местах.
  Новый последний бит ставится так, как движок держит его во всех 37 таблицах сейва BE A GM10 со строками
  (nhl-legacy-port): 1 у строк из списка удалённых и из запаса `[current, max)`, 0 у живых. Прежний бит 63 — настоящий
  младший бит draftteam, список удалённых в заголовке не трогается. Пишется копия, на месте сейв не чинится.
  - Проверено на копиях двух сейвов. У BE A GM10 (nhl-legacy-port) у 107 из 357 живых строк флаг был 1, после
    ремонта — у 0. Значения полей и остальные таблицы не изменились, суммы сейва сходятся.
  - nhl-legacy-port проверил ту же раскладку в игре своим разовым скриптом на копии `userdata-p3`: сейв грузится, в пуле
    перед драфтом 357 разных, auto draft 2028 — 224 разных выбора из пула.
- **Проверка в игре.** Копия `game/work/legacy-data/ud-rookie` — userdata пользователя без сейвов франшиз, с базой
  59b03a68. nhl-legacy-port проверит на ней франшизу с двумя драфтами.

## Ветераны НХЛ 2015 — без клуба (этап `retire`, 10.10.2026)

Нашёл пользователь: Alex Galchenyuk (1994) стоял в «Милуоки» (АХЛ) с OVR 84 и во франшизе выходил в свободные агенты,
а в жизни он в КХЛ. Таких в базе пользователя (59b03a68) было 94: бывшие игроки НХЛ 2015 года в клубах вне НХЛ, у 67 из
них OVR ≥ 80 — Toews 93, Getzlaf 92, Price 92, Kopitar 91… По лигам: CHL 78, АХЛ 9, Европа 7.

**Причина.** Составы собирались без `--retire-veterans`. Место каждого, кто ушёл в НХЛ из клуба АХЛ, Европы или CHL,
занимал ушедший из НХЛ игрок 2015 года ([roster-pipeline.md](roster-pipeline.md), «--retire-veterans»).

**Исправление.**
- `build-all.sh`: во FLAGS добавлен `--retire-veterans 2010`. База старше на 11 лет, поэтому год накрывает всех
  ушедших из НХЛ. Это для пересборки составов, а она сейчас невозможна: сетевой кэш конвейера после инцидента 09.10
  неполон (`roster build --offline` — «нет состава ANA в кэше»), нужно около 2200 запросов. В сеть не ходим: это
  отдельное решение пользователя.
- Поэтому то же самое делается офлайн по готовой базе: `tools/legacy_data/retire_veterans.py`, этап `retire` после
  `collect`.
  - Ветеран — игрок входной базы конвейера (`nhl32`, составы 2015), который там в клубе НХЛ, а в готовой базе только
    в клубах вне НХЛ (тот же game_id, имя и дата рождения).
  - Его место закрывается по правилам `write.free_vacancy`: незанятое запасное место убирается; иначе звенья, одетость
    и букву получает запасной клуба того же амплуа; иначе — запасной того же амплуа из другого клуба той же лиги.
  - Сам ветеран — без клуба и контракта, как у конвейера: в сборной — сборная + 1, иначе 0. Во франшизу не попадает.
  - Составы, звенья, рейтинги и пул свободных агентов не меняются. Повторный запуск ничего не меняет.
- После этапа `draft_roster.db` собирается заново из исправленной базы: в его 10 таблицах есть составы.

**Итог (06:09, сборка `collect` → `retire` → `fixdb` → `utah` → `menu` → `nhl24`, база `--ahl32`):**
- Ветеранов 94, без клуба все 94. Места:

  | правило | мест |
  |---|---|
  | запасной клуба | 74 |
  | место запасного убрано | 11 |
  | запасной другого клуба лиги | 9 |
  | ветеран оставлен (нет замены) | 0 |

- В плоском варианте `out` — 72 ветерана: 57, 10 и 5 соответственно, оставленных нет.
- После этапа бывших игроков НХЛ 2015 года в клубах вне НХЛ 0. Звенья, одетые и буквы у всех клубов те же.
  Наименьший состав — 20 (команды 91, 102, 103, 193, 208). Пул свободных агентов тот же — 39.
- Galchenyuk — без клуба (команда 0), Toews, Price, Getzlaf, Bergeron — только в сборных (team 136), Kopitar — в
  сборной Матча звёзд (224). Контракты у всех обнулены.
- В базе изменились только `exhibitionplayerbiotable` (у 94 ветеранов и 9 перешедших запасных) и
  `exhibitionrostertable` (5749 → 5655 записей).
- Новые md5: `out-ahl32` — база 88237e2b, `draft_roster.db` 37aca712 (10 таблиц, совпадают с базой), локализация
  fe380a4b (та же; после канонической пересборки 06:18 — 97fb5826, содержимое то же). `out` — b874973d / 1cc163e1, локализация 93b07369: содержимое то же, другой только порядок строк
  в пуле, потому что Юта теперь применяется до меню.
- Прежние базы — `game/work/legacy-data/backup-cache/out-before-retire-20261010-060759/`.
- Отчёты — `game/work/legacy-data/roster/retire-veterans.json` и `roster-ahl32/retire-veterans.json`.
- Копия для nhl-legacy-port — `game/work/legacy-data/ud-vet` (с Ютой). Пользователю — после теста и слова координатора.
- **ТЕСТ VET пройден** (legacy-port, 10.10). Во франшизе нет ни одного из 94 ветеранов, Galchenyuk нет.
- **Находка теста: в клубах вне НХЛ остались старые игроки составов 2015.** Этап их не трогает: в 2015 году они не
  были в клубах НХЛ.
  - АХЛ (32 клуба): рождены в 1988 году или раньше — 185 из 792, 23 %. У 44 из них OVR не ниже 75, 157 стоят в
    звеньях. 1 июля 37 таких выходят на рынок свободных агентов, например Heatley: 45 лет, OVR 80 (nhl-legacy-port).
  - Лиги Европы со составами 2015 — доля таких игроков: DEL 61 %, NLA 52 %, SHL 46 %, Extraliga 41 %, Норвегия 44 %.
  - Liiga (наша) — 2 %, CHL — 0.
  - Без них в самом малом клубе АХЛ осталось бы 14 игроков, в лигах Европы — 6–9. Составы этих лиг пересобирает
    только сетевой конвейер.
  - Счёт — `tmp/old_in_clubs.py` по `out-ahl32` (88237e2b). Решение — за координатором.

**`collect --ahl32` с нуля — починен (10.10, 06:15).** `make_out_ahl32.py` брал игроков сверх основной базы (для
портретов CV/HSK) из `roster/write.json`, `roster-ahl32/write.json` и `photos-all/photos.json`, а они пропали в
инциденте 09.10. При сборке 06:08 этап остановился, прежняя `out-ahl32` вернулась из `_stale/` байт в байт.
- Теперь список берётся из самой базы `roster-ahl32`: игроки в составах фарм-клубов CV/HSK (224/225) — 51, их портреты —
  файлы `photos-all/…/p<artid>.big` (39 игроков, 78 файлов), как было.
- Проверка: `collect` → `retire` → `fixdb` → `utah` → `menu` с нуля в отдельную папку (`LEGACY_DATA_WORK=dry-collect`)
  дали `out` (2976 файлов) байт в байт как нынешний. В `out-ahl32` (82 файла) совпало всё, кроме
  `fe/loc/NHL_ENG_US.db`: содержимое то же, другой порядок строк в пуле — прежняя `out-ahl32` получила правки меню раньше
  Юты. После пересборки 06:18 на месте `out-ahl32` — каноническая (локализация 97fb5826, база 88237e2b), и сборка с нуля
  с ней совпадает байт в байт.
- Где ещё `build-all` зависит от пропавших файлов — только этапы до `collect`, которые и так требуют сети:
  - `roster` (fetch/build/match/write) — сетевой кэш `roster-cache/nhl`, `ea`, `nhlratings` и свои `players.json`,
    `match.json`, `write.json`;
  - `photos`: `tools/roster photos` (`players.json`, `_other.json`), `photos.py build` (`players.json`, `write.json` →
    `photos.json`), `photos.py db` (`photos.json`, `write.json`);
  - `equip`: `roster.equipment apply` (`write.json`, `roster-cache/nhl/landing/*.json`,
    `roster-cache/equipment/equipment.json`, `commons.json`).

  Без сети их вход не восстановить, поэтому без изменений в выходе их не починить. Остальные этапы (`base`, `collect`,
  `retire`, `fixdb`, `utah`, `fonts`, `music`, `models`, `art`, `menu`, `nhl24`) пропавших `.json` не читают: свои
  `build.json` пишут сами, `menu12/players/spec.json` заменён `tools/legacy_data/menu/menu12-rings.json`.

## Юта вместо Аризоны, Тусон вместо Springfield (этап `utah`, 10.10.2026)

Данные и арт подготовил агент utah ([utah.md](utah.md)): спецификация `game/work/utah/utah_spec.json` (поле за
полем: было → стало) и арт `game/work/utah/out` (66 файлов: Юта — арт 104, Тусон — арт 105, прожектор 48).
`tools/legacy_data/utah.py` (этап `utah` в `build-all.sh`, после `fixdb`) применяет спецификацию к `out/db` и
`out-ahl32/db` и к их локализации и копирует арт в `out/` со сверкой md5. После этапа `draft_roster.db` собирается
заново (Юты в его 10 таблицах нет, файл тот же). Повторный запуск ничего не меняет.

**Проверки.** Каждое поле до правки должно быть «было» или уже «стало», иначе сборка останавливается. Строки формы,
экипировки и цветов выбираются по команде. У формы сверяются число, порядок и поля строк, а не номера: строки
Тусона сдвигаются после Юты.

**Решения (пользователь и координатор, 10.10).**
- Третьей формы Юты нет: концепт `out-third/` и `optional_third` не берутся. У Юты 2 строки формы: дом `1_104_0`,
  выезд `1_104_1`. Прежние 8 строк Аризоны удалены, таблица укоротилась на 6 строк.
- Арена — нейтральная модель «EA SPORTS Arena», как у SEA и VGK, с названием Delta Center, Salt Lake City, UT, на
  14 111 мест. Звук команды — 32.
- Реклама. Нашивок на свитере нет. Наклейки Filevine на шлем в арте нет: на шлеме логотип клуба Mountain Mammoth
  (`helmetlogo 1`) — так и оставлено.
- Фарм-клуб — Tucson Roadrunners с логотипом «Dusty» на строке 55, арена 52 — Tucson Arena (6 521).
- Тусон остаётся в дивизионе Atlantic, как Springfield. Дерево АХЛ задаёт код, у `--ahl32` — врезка legacy-port,
  поэтому перенос в Pacific — открытый вопрос.

**Сверх спецификации.**
- Палитра Тусона в `stockteamcolorstable`: бордовый, песочный, медный, чёрный — по [utah.md](utah.md) §6. В
  спецификации её нет.
- Шлем выездной формы Юты — белый. Строка шлема варианта 1 (era 1, equipment 8) у Аризоны была от её ретро-формы и
  после перекраски стала тёмной. Теперь у Юты шлем чёрный дома и белый в гостях, как на настоящей форме.
  - Уточнение 10.10 (как игра выбирает шлем — раздел пакета NHL 24): сырое era 1 — это ретро-формы стиля 0, поэтому
    правка строки 720 на Юту не влияет.
  - По модели шлем Юты и так верный: дома — строка 716 Аризоны (era −1, variant «любой», чёрный), в гостях — 712
    (era −1, variant 1, белый). Проверка — ТЕСТ UTA.

**Сборка (05:26).**
- Базы: `out` — b7a2a3b0, `out-ahl32` — f446697c (были 10a2335d / 59b03a68).
- Локализация: `out` — 74e573fb, `out-ahl32` — fe380a4b. 22 строки: 5 ключей `*_22`, 9 `*_UTA`, 8 `*_TUC`. Ключи
  `*_PHX`/`*_ARZ` остались для старых франшиз.
- Прежние базы и локализации — в `game/work/legacy-data/backup-cache/out-before-utah-20261010-052619/`.
- Накладка NHL 24 пересобрана на новых базах.
- Проверка на копии `cache:` пользователя (`tmp/check_utah.py`): `install --ahl32` изменил ровно базу и
  локализацию (md5 как в `out-ahl32`) и добавил ровно 66 файлов арта (md5 как в спецификации). `draft_roster.db`
  тот же (838ca6a0), остальное байт в байт как у пользователя.
- Копия для nhl-legacy-port — `game/work/legacy-data/ud-uta` (ТЕСТ UTA).
- **ТЕСТ UTA пройден** (legacy-port, 10.10, на `ud-vet`): меню, Delta Center, формы и шлемы дом/выезд, Тусон
  с логотипом и Tucson Arena; во франшизе Юта в Central, фарм — Tucson, старт Entry Draft — 49 таблиц.

**Пользователю — после теста и слова координатора.** Теперь в `out` уже Юта: любая следующая установка
`install-legacy-data.sh --ahl32` поставит и её. Откат после установки: вернуть из бэкапа `db/nhlng.db` и
`fe/loc/NHL_ENG_US.db` (`draft_roster.db` не меняется). 66 файлов арта с новыми номерами без базы Юты не
используются. Сборка без Юты — этапы `collect`, `fixdb`, `menu` без `utah`.

**Начатые франшизы** хранят свою копию команд: там Аризона останется Аризоной, Юта будет в новых франшизах.

## АХЛ 2026/27 и свободные агенты (этап `ahl`, 10.10.2026)

Решение пользователя (10.10, 09:10): «актуализируй составы АХЛ и свободных агентов». Сеть разрешена только для этих
данных. Составы НХЛ не перекачиваются и остаются на 08.10.

**Скачивание** (`python -m roster.ahl_ht teams | ids | players`, `tools/roster/ahl_ht.py`). Только GET, к одному хосту
— не чаще раза в секунду (по началам запросов, до 8 в ожидании ответа). Все ответы — в `game/work/roster-cache`.
- HockeyTech (`lscluster.hockeytech.com`, сезон 94 = 2026/27):
  - `teamsbyseason` — 32 клуба, логотипы — `ahl/ht/logos/<team_id>.png`;
  - `roster` 32 клубов — 820 игроков;
  - расписание — арены;
  - `seasonstats` игроков без ID НХЛ.
- API НХЛ:
  - `prospects` 32 клубов и `search.d3`: ID НХЛ по имени, сверка даты рождения по `landing`;
  - если дата не сошлась — ID по карточке из кэша (`club_season_ids`): та же фамилия, то же имя (или его форма) либо
    та же дата, в сезоне 2026/27 — АХЛ за этот же клуб. В HockeyTech дата рождения бывает неверной: у Basha
    «2011-08-05» при 2005-11-08, у Kerins, Hurtig, Hovorka, Mešár, Lundell переставлены день, месяц и год, у Becker
    2003 вместо 1997, у Sgarbossa имя Mike при Michael. Так нашлись ID ещё 18 игрокам (в `ids.json` — `by_club`);
  - `landing` — данные и статистика всех лиг;
  - портреты сезона и `latest`.
- Свободные агенты — как у `--fa` (`fa.py`): stats REST `bios` за 2024/25–2025/26, `landing`, Wikipedia.
- Запросов всего — около 2530 (ошибок 0) и 21 при докачке 11:10: портреты НХЛ этих 18 игроков (пропуски).
- ID НХЛ — у 767 игроков из 820, без ID — 53.

**Слоты** (`tools/legacy_data/ahl2026_slots.py` → `game/work/legacy-data/ahl-2026/slots.json`).
- 24 слота — тот же клуб.
- 8 слотов — клуб, который сменил прежний (переезд или переименование) или стал фармом того же клуба НХЛ: Albany →
  Abbotsford, Binghamton → Belleville, Bridgeport → Hamilton, Lake Erie → Cleveland, Portland → Springfield,
  St. John's → Laval, San Antonio → Colorado Eagles, Stockton → Calgary Wranglers.
- Аффилиаты меняются у пяти клубов НХЛ: NJ, VAN, CAR, FLA, STL.
- Поле `exhibitionteams.ahlaffiliate` хранится со сдвигом −1.
- У переименованных меняются:
  - полное и короткое название и аббревиатура; коды, совпавшие с чужими в базе, заменены: CGW, COE, BLV, HMR;
  - строки локализации по `artabbr` слота (`NHLTeamName_*`, `Teamline1/2_*`, `TXT_NICKNAME*`…).
- Арены всех 32 слотов — по расписанию HockeyTech, Tucson оставлен «Tucson Arena» (координатор).
- Строка арены, общая с клубом НХЛ (так в базе 2015 года у двух клубов):
  - Manitoba Moose и Winnipeg Jets — одно здание и в 2026/27, строка общая: Canada Life Centre (было MTS Centre) у
    обоих;
  - San Jose Barracuda с 2022 года играют в Tech CU Arena, Sharks — в SAP Center. Barracuda получили свою строку:
    копию общей (модель, звук, центр льда те же, другие только название и город), в `out` — строка 189, в
    `out-ahl32` — 191. У SJ строка как была. В первом прогоне 10:15 общая строка переименовывалась целиком, и SAP
    Center у Sharks стал бы Tech CU Arena.
- Арт (`artid`, `artabbr`, логотипы, модели арен) не меняется: логотипы АХЛ делает агент logos по `slots.json`.

**Игроки** (`tools/roster/ahl2026.py`, запись — `ahl2026_write.py`).
- Игрок с ID НХЛ — запись по `landing`, как у конвейера, номер — из HockeyTech. Без ID — запись по HockeyTech: рост,
  вес, хват, место рождения, драфт, игры АХЛ; ID свой — 95 000 000 + ID HockeyTech.
- Кто в составе клуба НХЛ на 08.10, там и остаётся (НХЛ побеждает): 22 игроков, список — в отчёте.
- Составы больше 30 урезаны до 30: сначала игроки на просмотре (PTO/ATO), потом по OVR.
- Составы меньше 23 не добираются (координатор 10.10): Bakersfield, Iowa, Colorado Eagles, Texas — по 22, Cleveland —
  21. У этих клубов в HockeyTech самих 22–24 игрока, а других игроков АХЛ и PTO этих клубов в данных нет. Часть
  их игроков — в составах НХЛ на 08.10: у EDM там 29, у MIN и CBJ 25, у COL и DAL 24. Во франшизе их доберут сами
  клубы НХЛ. В базе до этапа тоже были клубы АХЛ по 21 — 4 клуба, франшиза на ней проверена. ECHL не качается: сеть
  только для АХЛ и свободных агентов.
- Рейтинги — по статистике (`statsrating`: NHLe, три сезона) с коэффициентами калибровки 09.10: калибровочных
  рейтингов NHL 27 в кэше больше нет. У игроков АХЛ — сдвиг шкалы АХЛ Legacy (−8) и уровень АХЛ базы.
- У сопоставленного игрока, чьи атрибуты в базе уже 2026 года (писал конвейер 08.10), рейтинги — свои.
- Запись — `write.Writer` с правками. Переписываются только составы 32 клубов АХЛ и пул свободных агентов.
  - Донорами новым игрокам служат только строки без клуба, прежнего пула и игроков АХЛ 2015 года, которых нет в
    данных 2026/27. Строки игроков НХЛ, Европы и юниоров не трогаются.
  - Звенья — по рейтингу, буквы — по опыту, номера — из HockeyTech.
  - Голова — под тон кожи по фото (`--skin`).
- Игроки АХЛ 2015 года без данных 2026/27 остаются без клуба и контракта, как ветераны этапа `retire`.
- Портреты:
  - фото НХЛ — как у конвейера;
  - leaguestat 240×240 — серый фон делается прозрачным (`tools/roster/ht_photos.py`), затем кадр НХЛ
    (`photos_other.to_nhl_frame`);
  - сборка — `tools/photos.py` в свою папку.
- Экипировка — по правилам (`roster.equipment apply --visor-rule --jersey-rule`).
- Проверки этапа:
  - составы НХЛ записей — как до этапа;
  - в клубах АХЛ 21–30 игроков, каждое место звеньев — у одного игрока, одетых 20, буквы и номера без повторов;
  - свободные агенты не в составах;
  - CRC.
- Полный прогон идёт на копии базы (`ahl-2026/<out|out-ahl32>/db`). База и локализация в `out` заменяются целиком в
  конце, портреты дописываются в `<out>/fe`. Если прогон оборвётся, `out` не тронут: так и было 10.10, прогон прерван
  на портретах. К базе, где этап уже применён (у переименованных слотов новые названия), он второй раз не
  применяется, и `slots.json` по ней не переписывается. Заново — от сборки базы (`build-all.sh collect … ahl`) или от
  баз из бэкапа.
- Отдельная проверка — `game/work/legacy-data/tmp/check_ahl2026.py out|out-ahl32` (база до этапа против базы после):
  - у игроков составов НХЛ все строки по `game_id`/`playerid` во всех 17 таких таблицах (био, атрибуты, экипировка,
    исключения визора, карьера, награды…) байт в байт;
  - записи составов НХЛ те же;
  - у строк клубов НХЛ изменился только `ahlaffiliate`, у арен НХЛ — только название WPG;
  - клубы АХЛ, пул свободных агентов, `draft_roster.db` (10 таблиц, байт в байт как в базе), CRC баз и локализации.

**Итог** (пересборка 11:15 с бэкапа `backup-cache/out-before-ahl-20261010-100231`, прежний результат 10:15–10:21 —
`_stale/out-after-ahl-1021-20261010-110532`):
- `out-ahl32`: в составах 32 клубов АХЛ 795 игроков, в клубе 21–30. С ID НХЛ 743, только HockeyTech 52. Сопоставлено с
  базой 158, новые — на строках 675 доноров.
- Charlotte сверх 30 — убраны 3: Lundell, Dorwart, Pinho.
- Свободных агентов 38, в пуле только настоящие (было 39 от 08.10).
- Без клуба осталось 63 игрока АХЛ 2015 года (в `out` — 85).
- `out`: 30 клубов, 745 игроков.
- Обе проверки — OK. Игроки НХЛ (798): записи байт в байт как до этапа.
- Базы: `out` e036f8d5 (draft_roster 4f48845a, локализация 4594e6dd); `out-ahl32` 4bfa0964 (draft_roster 6e0b5b5f,
  локализация 0900978d). Портретов: в `out/fe` +1298 файлов, в `out-ahl32/fe` +1382.
- Накладка NHL 24 (пакет 511e90bd, пилот CHI) пересобрана: `out-nhl24` 5fb940cd / 0240fc4c, `out-nhl24-ahl32`
  77e65fb1 / 13a8ea7f.
- Копия для nhl-legacy-port — `game/work/legacy-data/ud-ahl` (ТЕСТ AHL): userdata пользователя без сейвов франшиз,
  установка `--ahl32 --nhl24` (`tmp/make_ud.py`). Это Юта, ветераны, АХЛ 2026/27 и свободные агенты, накладка NHL 24 —
  пилот CHI, как у пользователя. Новых логотипов в копии нет: её сделали до этапа `logos`. По сравнению с userdata
  пользователя изменились база (77e65fb1), `draft_roster.db` (6e0b5b5f) и локализация (13a8ea7f). Портрет p13587
  (J.R. Avon, CV) — новое фото leaguestat. Добавлено 1368 файлов: портреты и арт Юты; `nhl24.py verify` — 171 файл,
  расхождений 0.
- Пользователю не ставилось. Будущая установка — одна, по слову координатора: база, накладка NHL 24 на все клубы,
  логотипы.

- **Разброс рейтингов узкий.** OVR новых игроков АХЛ по медиане как у АХЛ 2015 года: нападающие 68, защитники 69,
  вратари 64. Но разброс 10–90 % — 65–70, 67–71 и 63–65, а у АХЛ 2015 года 62–75, 61–75 и 55–75. Так работает
  `--stats-ratings` со сдвигом АХЛ: оценка по статистике смешивается с уровнем АХЛ с весом уверенности, медиана
  выравнивается по базе. Вариант на решение — квантили: порядок по статистике, шкала — распределение АХЛ 2015 года
  по амплуа. Сделано 10.10 (квантили), с 11.10 — у всех игроков АХЛ и с атрибутами под OVR игры (раздел ниже).
- **Портрет 8479547 (Matthew Phillips).** Портрет НХЛ `latest` пришёл с неверной контрольной суммой zlib, и
  `playerhead.png_read` его не читал. Он пересохранён без потерь (PIL) в кэше, исходник —
  `game/work/legacy-data/_stale/`.

## CHL из NHL 27 (этап `chl`, 21.10.2026)

До этапа в 60 клубах CHL стояли составы базы EA 2015 года: 1 394 игрока 1994–1998 г. р. Этап ставит туда составы
OHL, QMJHL и WHL из базы NHL 27 (решение пользователя: «составы молодёжных лиг — 100 % из NHL 27»; НХЛ и АХЛ не
трогать). Код — [tools/legacy_data/chl27.py](../tools/legacy_data/chl27.py), чтение базы NHL 27 —
[tools/roster/nhl27.py](../tools/roster/nhl27.py) (как достать базу из дампа — [frostbite-sources.md](frostbite-sources.md) §5).

```bash
python tools/legacy_data/chl27.py                 # out-ahl32 и out; рабочие файлы — game/work/legacy-data/chl27/
bash tools/legacy_data/build-all.sh chl           # то же этапом сборки
```

- **Клубы.** 61 клуб NHL 27 → 60 слотов Legacy по аббревиатуре в своей лиге. Переехавшие франшизы — в прежние слоты
  с новым названием, городом, аббревиатурой и строками локализации: Hamilton → Brantford Bulldogs, Mississauga →
  Brampton Steelheads, Acadie-Bathurst → Newfoundland Regiment, Kootenay → Wenatchee Wild; Cape Breton Screaming Eagles
  → Cape Breton Eagles. Арены всех клубов CHL — название и город из NHL 27. Логотипы — прежние (у четырёх переехавших
  — логотип старого клуба).
- **Penticton Vees** (WHL с 2025 года) — 23-го слота WHL нет, клуб не ставится; двое его игроков пошли в добор.
- **Игроки.** Из NHL 27 как есть: имя, дата и место рождения, гражданство, рост, вес, хват, амплуа, драфт, права НХЛ
  (210 юниоров), контракт, атрибуты (значение − 36), стиль, тенденции, черты, рост (`growth*`). Потенциал — по
  соответствию 42 → 5, 66 → 30 (так распределены юниоры в обеих базах). `juniorteam`/`juniorleague` — свой клуб и его
  лига, как у юниоров базы 2015 года. Новый игрок занимает строку прежнего юниора (старшие первыми), портрета у него
  пока нет, голова — типовая того же тона кожи.
- **НХЛ/АХЛ побеждает.** 61 юниор NHL 27 у нас в составах НХЛ (3: Beaudoin — NYR, Jiricek — STL, O'Brien — SEA) или АХЛ
  (58, из них 48 к 31.12.2026 исполнится 20) — они остаются там.
- **Добор.** Без них у 29 клубов дыры. Клубам, где меньше 2 вратарей или 18 полевых, — 20 запасных (не одетых) того же
  амплуа из клубов той же лиги, у кого запасных больше всего, и 2 игрока Penticton.
- **Звенья.** Из NHL 27 (места переведены: `pp_N*` → `ppN*`, `ev4_N*` → `ot_N*`). У 31 клуба — ровно как в NHL 27, у 29 —
  освободившиеся места в тройках, парах и воротах отданы лучшим неодетым того же амплуа, остальные (большинство,
  меньшинство, овертайм, буллиты) — лучшим одетым. Буквы — из NHL 27, недостающие — по конвейеру.
- **Строк вратарей не хватило на двоих:** вратаря пишут только в строку вратаря, а доноров-вратарей 142 при 144.
  Без места остались два самых слабых третьих вратаря (Reid Thomas, OSH; Owen Lunneborg, VAN).
- **Итог (out, 21.10):** 1 355 игроков в 60 клубах (20–28 в клубе), прежние юниоры без места — без клуба и контракта.
  Проверки конвейера пройдены; составы НХЛ, АХЛ, Европы, особых команд и пул свободных агентов — байт в байт как
  были; повторный запуск ничего не меняет.

## OVR в игре — из атрибутов: АХЛ и свободные агенты со скидкой на лигу, атрибуты НХЛ под OVR базы (11.10.2026)

Жалоба пользователя (11.10, 04:40): составы АХЛ почти такие же сильные, как в НХЛ, есть игроки около 90; то же со
свободными агентами.

**Причина.**
- Игра показывает OVR, посчитанный из атрибутов `c_*`; поле overall она не читает. Точная формула — таблицы
  `fe/resource_kernel/worth2.brk`, разобрал nhl-legacy-port (коммит 1c819e6, `tools/roster/ovrformula.py`: `game_ovr`).
  - У полевых сверено по 61 OVR из игры — все точно.
  - У вратарей формула из кода та же (таблица 13), но по игре не сверена.
  - До разбора (утро 11.10) пользовались регрессией overall ~ атрибуты по базе EA (`regression`, средняя ошибка 0,5–1,8).
- OVR растёт в 1,8–1,9 раза быстрее среднего атрибута; у nhl-modding-studio (регрессия по базе EA) — 1,92.
- Конвейер строил атрибуты так: форма плюс общий сдвиг, пока «среднее + поправка группы» не даст OVR
  (`ratings.Model`). Это верно только в середине шкалы группы.
  - АХЛ: верх квантилей (OVR 77–82, шкала 2015 года) давал средний атрибут 87–91 и OVR из атрибутов 90–95: Vaakanainen,
    Holtz, Reichel, Pelletier, Raddysh. Ещё 87 игроков (`kept_2026`: свободные агенты, CV/HSK и другие) сохраняли
    атрибуты NHL 27.
  - Свободные агенты — атрибуты NHL 27 без поправки на лигу прошлого сезона: Mrazek 84, Tarasenko 83, Drouin 83.
  - НХЛ: у игроков ниже топ-300 (атрибуты достроены из OVR NHL 27) OVR в игре был ниже базы на 3–12. 25-й перцентиль
    НХЛ в игре — 69–75 при 78–81 в базе.

**Что сделано.**
- **`ratings.Model.formula`.** Если задан (модуль `ovrformula`), форма сдвигается до OVR формулы. После округления
  меняется по одному атрибуту на ±1, пока OVR формулы не станет ближе 0,25. Без него всё как было: основной конвейер и
  NHL 13 не меняются.
- **АХЛ** (`ahl2026.quantile_ratings`). Квантили по статистике под шкалу АХЛ 2015 года по амплуа — у всех игроков клубов
  АХЛ 2026/27, без исключений для атрибутов NHL 27.
  - Статистика — NHLe трёх сезонов по всем лигам из карточек landing, у кого их нет — seasonstats HockeyTech.
  - Верх шкалы: выше 90-го перцентиля она сжимается линейно до min(78; 25-й перцентиль НХЛ амплуа в базе). У АХЛ 2015
    года верх давали ветераны НХЛ того времени, до 82.
- **Свободные агенты** (`ahl2026.fa_ratings`). Модель statsrating (коэффициенты 09.10, шкала NHL 27, как у составов НХЛ).
  - Окно — прошлый сезон 2025/26: очки × NHLe лиги, где играл. Опыт E — игры в НХЛ в этом сезоне / 50 (вратари —
    / 33). Если игр в прошлом сезоне меньше 10 — три сезона, как в statsrating (у 8 из 38).
  - Возраст: полевым старше 30 и вратарям старше 32 — минус 1 за год, не больше 5.
  - Вратари — % отражённых против лиги и опыт.
- **Атрибуты АХЛ и свободных агентов** — `ratings.Model` с формулой (`AhlWriter.legacy_model`). Форма нового игрока —
  медиана игроков составов НХЛ базы его амплуа и стиля (NHL 27), у сопоставленного — его атрибуты. Стиль прежний
  (изменился у 0).
- **НХЛ** (слово координатора 11.10; этап `nhlattrs`, `tools/legacy_data/nhl_attrs.py`, после `ahl`).
  - Кого трогает: игрока состава НХЛ, у которого |OVR формулы − overall| > 1, если его OVR ниже 84 или атрибуты
    достроены. Достроенные — профиль отклонений от среднего атрибута такой же (±1,5), как у другого игрока того же
    класса и стиля.
  - Атрибуты сдвигаются тем же `Model` с формулой, форма — свои атрибуты. Меняются только `c_*`.
  - Overall, стиль, тенденции, потенциал, звенья, составы и экипировка — как были. Повтор ничего не меняет.
  - Отчёт — `game/work/legacy-data/nhl-attrs/<out|out-ahl32>.json`.

**Сборка (05:07–05:18).** Базы до этапа — из `backup-cache/out-before-ahl-20261010-100231`, затем `ahl` → `nhlattrs` →
`useredits` → `logos`. Прежние базы — в `backup-cache/out-before-ratings-20261011-0453`.
- Игроки и строки те же: 833 / 783 игрока на тех же `game_id`, составы 21–30, в Charlotte убраны те же 3, свободных
  агентов 38. Портреты не изменились, локализация — та же (0900978d / 4594e6dd).
- Звенья, номера и контракты клубов АХЛ пересобраны по новым OVR.
- `nhlattrs`: в обеих базах атрибуты сдвинуты у 425 игроков НХЛ — 417 ниже 84 и 8 достроенных из 84+ (у Hart и Husso
  вратарские атрибуты были на 22–25 ниже OVR). 353 игрока топ-300 EA не трогались: медиана −0,35, у 130 расхождение
  1–4,7. Это погрешность формулы, а не данных.
- `useredits`: 191 правка в каждой из 4 баз, конфликтов 0.
- Базы: `out` — 4db90a51 (draft_roster dfe0391f), `out-ahl32` — 71fcf2b2 (draft_roster b1317559).
- 05:19: `nhl24` остановился сам — пакет ещё дописывался. 05:31 (слово координатора): `utah` → `logos` → `nhl24` на новых
  базах и новом пакете (манифест 7fd901e2: CHI, SEA, VGK, 205 файлов, новые рукава).
  - `utah`: базы и локализация без изменений, арт Юты — скопировано 5 файлов.
  - `logos` вернул свой значок ленты Юты `t104`: арт utah его перекрывает, поэтому `logos` — после `utah`.
  - `nhl24`: 8 новых форм (CHI 3, SEA 2, VGK 3). Накладки: `out-nhl24` — 54cf7eca, локализация 712e4ca4;
    `out-nhl24-ahl32` — 6df623b2, локализация a8db3617.

**Пересчёт на точной формуле (08:26–08:36).** Сборка заново: базы до этапа `ahl`, затем `ahl` → `nhlattrs` →
`useredits` → `utah` → `logos` → `nhl24` (пакет eeffaf02). Прежние `out*` — в `backup-cache/out-before-exact-20261011-0826`.
- Полевые: подбор атрибутов — пока непрерывная форма формулы (`ovrformula.ovr`) не станет в пределах ±0,25 от цели.
  Тогда OVR игры (`game_ovr`) равен цели точно (`ovrformula.SkatersExact` в `ratings.Model.formula`).
  - АХЛ и свободные агенты: OVR игры = цель у всех — 724 и 35 полевых в `out-ahl32`.
  - НХЛ (`nhlattrs`): атрибуты сдвинуты у всех полевых, у кого OVR игры ≠ overall, — 647 из 725. Из них топ-300 EA —
    240: −2 у 7, −1 у 22, +1 у 101, +2 у 96, +3 у 13, +4 у 1. Остальные 407 были от −17 до +6. После — у всех 725 OVR
    игры = overall.
- Вратари в этой сборке — как были (регрессия): их формула по игре не сверена. С полем overall вратарей EA она
  расходится: у НХЛ +2 (точно у 11 %), у АХЛ +4, в Европе +4…5, у CHL +6. В нашей базе у НХЛ +3 (у Василевского 96 при
  94), у АХЛ +5. Строки вратарей — байт в байт как в прежней сборке.
- **13:11–13:21 — вратари тоже на точной формуле** (пользователь: «исправляй»; таблица 13, доли 60/20/20).
  - Изменены только вратари НХЛ, АХЛ и свободные агенты. Вратари Европы и CHL из базы EA не тронуты: там так считает
    сама игра.
  - `ratings.Model.formula` = `ovrformula` у всех, `nhl_attrs` — точное равенство и у вратарей: сдвинуто 71 из 73, из
    них топ-300 EA — 41 (+2 у 20, +3 у 19).
  - OVR игры = overall у вратарей НХЛ (73), АХЛ (71) и свободных агентов (3).
  - Против установленной 8933e778 изменилась только `exhibitiongoalieai` (147 строк). Полевые и 389 вратарей других
    лиг — байт в байт (`tmp/check_goalies_20261011.py`).
  - Вратари в игре, медиана / максимум: НХЛ 87 / 96 → 84 / 94 (Василевский 96 → 94), АХЛ 68 / 82 → 64 / 78, свободные
    агенты 81 → 78.
  - Базы: `out-nhl24-ahl32` f25bf4a5 (локализация 84b0ec1b), `out-ahl32` 1ea5360f (draft_roster 0d80f9a4), `out`
    a8a99362 (ceaa2556), `out-nhl24` 4f87c696. Прежние — `backup-cache/out-before-goalies-20261011-1311`.
- OVR в игре, `out-ahl32`, до → после (медиана): НХЛ полевые 84 → 82–82,5; АХЛ 70–71 → 67–69, верх 79–81 → 78;
  свободные агенты 76–79 → 75–76,5.
- Против прежней сборки изменились только `exhibitionskaterai` (1403 строки) и звенья АХЛ (`exhibitionrostertable`,
  149 записей).
- Базы: `out-ahl32` 202ac378 (draft_roster 29e4c128), `out` 06652ba1 (28f07a49); накладки `out-nhl24-ahl32` 8933e778
  (локализация 84b0ec1b), `out-nhl24` d3c88881 (d9a16f43). Проверка — `tmp/check_exact_20261011.py`.

**OVR из атрибутов (формула), `out-ahl32`: p10 / медиана / p90 (у АХЛ ещё максимум), до → после**
(`python -m roster.ovrformula compare`):

| | C | W | D | G |
|---|---|---|---|---|
| НХЛ | 66 / 77,6 / 87,5 → 76 / 81,9 / 87,5 | 64 / 77,7 / 88 → 76 / 82 / 88 | 64,5 / 80,7 / 87,7 → 76 / 82,1 / 87,7 | 73 / 84,1 / 88 → 80 / 84,1 / 88 |
| АХЛ | 58 / 69,1 / 83 / 90,6 → 62 / 68,1 / 75 / 78,1 | 60 / 69,9 / 85,3 / 94,8 → 62 / 67,1 / 74,9 / 77,9 | 58 / 72 / 82,4 / 95,3 → 62 / 69 / 75 / 77,9 | 56 / 66 / 85 / 89,9 → 59 / 63,9 / 75,2 / 78,1 |
| свободные агенты | 70 / 72,6 / 77 → 74 / 76,5 / 81 | 63 / 74,8 / 78 → 69 / 76,6 / 80 | 68 / 72,9 / 76 → 69 / 75 / 77 | 79 / 81,1 / 82,5 → 76 / 77,9 / 78,2 |

- 25-й перцентиль НХЛ в игре теперь равен базе: 79,2 / 79 / 78 / 81. Верх АХЛ — 78, игроков АХЛ выше 76 — 25 из 795.
- Liiga и CHL не менялись.
- Топ АХЛ до: Vaakanainen 95, Holtz 95, Reichel 93, Pelletier 93, Raddysh 93. После: Rittich (G), Sundqvist,
  Brodzinski, Vaakanainen, Raddysh, Holtz — по 78.
- Свободные агенты до: Mrazek 82 (в базе 84), Georgiev 81, Tarasenko 79, Reimer 79. После: Kurashev 81, Laine 81,
  Drouin 80, Tarasenko 80, Kunin 79, Hutton 79, Mrazek 78, Georgiev 78 (весь пул — 68–81, медиана 76).

**Проверки** (`game/work/legacy-data/tmp/check_ratings_20261011.py out|out-ahl32`, против прежней сборки; и
`tmp/check_ahl2026.py out-ahl32` после этапа `ahl`) — OK:
- у 798 игроков НХЛ все строки по `game_id`/`playerid` в 17 таблицах байт в байт, кроме атрибутов `c_*` у 425 из отчёта
  `nhlattrs`; записи составов НХЛ, `exhibitionteams` и арены — как были;
- OVR формулы ±1: у игроков НХЛ ниже 84 и достроенных (445) и у всех игроков АХЛ и свободных агентов;
- `draft_roster.db` — 10 таблиц байт в байт как в базе; CRC баз и `draft_roster`; локализация как была.

**У пользователя с 11.10, 05:41** (слово координатора «ставь»; игра закрыта, `nhllegacy.exe` нет).
- Шаги: бэкап → `install-legacy-data.sh --ahl32 --nhl24` (`CACHE=nhl-legacy-port/userdata/cache/guest`, состояние —
  `game/work/legacy-data`) → сверка → `nhl24.py verify`. Скрипт — `tmp/user_install_full.py backup|install|check|rollback`.
- В `cache:` заменено 17 файлов, добавлено 30 (формы SEA и VGK), убрано 0. Остальное, сейвы и userdata не тронуты.

  | файл | md5 | было |
  |---|---|---|
  | `db/nhlng.db` | 6df623b2 (out-nhl24-ahl32) | 4e793c6d |
  | `db/draft_roster.db` | b1317559 | 4d6bb74b |
  | `fe/loc/NHL_ENG_US.db` | a8db3617 | 13a8ea7f |

- Остальные замены — арт Юты (4), CHI с новыми рукавами (5), центры льда и шайбы SEA и VGK (4).
- Сверка: всё поставленное — как в `out*`. `nhl24.py verify` — 205 файлов пакета, расхождений 0, база — out-nhl24-ahl32,
  8 подписей форм.
- Бэкап — `game/work/legacy-data/backup-cache/user-20261011-054127` (заменённые файлы, `state/`, снимок `cache:`,
  списки). Откат при закрытой игре — `python game/work/legacy-data/tmp/user_install_full.py rollback <бэкап>`.
- **06:22 — шлемы SEA/VGK** (слово координатора, игра закрыта).
  - Заменены 2 файла: `db/nhlng.db` 6df623b2 → bbfc2932 (каски новых форм SEA и VGK, клюшка Tsyplakov из ROSTER 1) и
    `db/draft_roster.db` b1317559 → fec4a479.
  - Сверка OK, `nhl24.py verify` — 205 файлов, 0 расхождений.
  - Бэкап — `backup-cache/user-20261011-062216`.
- **06:37 — шлемы VGK Steel Grey и форма MIN дом** (слово координатора, игра закрыта).
  - Заменены 2 файла: `db/nhlng.db` bbfc2932 → 891bb659 и `fe/loc/NHL_ENG_US.db` a8db3617 → 84b0ec1b. Добавлено 8
    файлов MIN. `draft_roster.db` (fec4a479) не изменился.
  - Сверка OK, `nhl24.py verify` — 213 файлов, 0 расхождений, 9 подписей форм.
  - Бэкап — `backup-cache/user-20261011-063705`.
- **12:13 — точная формула OVR** (слово пользователя через координатора, игра закрыта).
  - Заменены 2 файла: `db/nhlng.db` 891bb659 → 8933e778 и `db/draft_roster.db` fec4a479 → 29e4c128. Локализация —
    та же (84b0ec1b).
  - Вратари — как были.
  - Сверка OK, `nhl24.py verify` — 213 файлов, 0 расхождений.
  - Бэкап — `backup-cache/user-20261011-121339`.
- **13:22 — вратари на точной формуле** (слово координатора, игра закрыта).
  - Заменены 2 файла: `db/nhlng.db` 8933e778 → f25bf4a5 и `db/draft_roster.db` 29e4c128 → 0d80f9a4. Локализация —
    та же (84b0ec1b).
  - Сверка OK, `nhl24.py verify` — 213 файлов, 0 расхождений.
  - Бэкап — `backup-cache/user-20261011-132241`.
- **«ROSTER 1 damaged»** — сейв составов ROSTER 20261011010728 сделан на прежней базе 4e793c6d.
  - CRC и раскладка таблиц в порядке, но `stockteamequipmenttable` в новой базе на 5 строк больше, чем вмещает сейв:
    6050 при max 6045, а `maxinsert` у таблицы нет.
  - В сейве — прежние рейтинги и атрибуты. Правки пользователя в нём — только экипировка, они уже в базе.
  - Предложено: сейв не грузить, удалить в игре или сохранить составы поверх.

## У пользователя (10.10.2026, 05:17)

Поставлено по решению координатора: исправленная база (флаговый бит) и `draft_roster.db` из 10 таблиц, без накладки
NHL 24.
- Команда: `CACHE=nhl-legacy-port/userdata/cache/guest bash tools/legacy_data/install-legacy-data.sh --ahl32`. Игра
  пользователя была закрыта: шла одна `nhllegacy.exe` — тест nhl-legacy-port под замком `game.lock` с другой
  `user_data_root` (`ud-ab-plain`). Обновлено 2 файла из 2910.
- Стоит в `cache:` пользователя (`nhl-legacy-port/userdata/cache/guest`):

  | файл | md5 | было |
  |---|---|---|
  | `db/nhlng.db` | 59b03a68 (out-ahl32 после fixdb) | 34dfe267 |
  | `db/draft_roster.db` | 838ca6a0 (10 таблиц) | 34dfe267 (полная копия базы) |
  | `db/nhlng-meta.xml` | 8ae5e145 (без изменений) | — |
  | `fe/loc/NHL_ENG_US.db` | 0973bb47 (без изменений) | — |

- Проверка: тот же шаг заранее на копии `cache:` (`tmp/check_user_install.py` → `check-user-db`) — изменились только
  эти 2 файла. После установки весь `cache:` пользователя байт в байт совпал с этой пробой. В `installed.txt` тот же
  набор путей (2910, пересортирован). Появился `install-flags.txt` (`--ahl32`).
- **Бэкап прежних файлов:** `game/work/legacy-data/backup-cache/user-20261010-051711/db/` (`nhlng.db`,
  `draft_roster.db`, оба 34dfe267; `md5.txt`).
- **Откат** — при закрытой игре скопировать оба файла из бэкапа обратно в `nhl-legacy-port/userdata/cache/guest/db/`.
  Установщик для этого не нужен: оба файла и так в `installed.txt`.
- Сейвы франшиз в userdata пользователя — агентские, их не чинили. Ремонт сейвов, если понадобится, —
  `fix_flagbit.py --save` (раздел выше).

## У пользователя (10.10.2026, 07:00): пилот CHI из пакета NHL 24

Поставлено по слову координатора (06:56): пользователь проверит пилот сам. Ставился только пилот CHI: три формы CHI,
центр льда CHI, лёд и реклама, шайба. Юта, ветераны и другие клубы не ставились.
- **Пакет.** `game/work/nhl24/out/pack`, manifest a2972bab, 171 файл. В нём превью форм в позе EA со сглаживанием
  (CHI3c).
- **Сборка.** Накладка собрана на базе пользователя в `game/work/legacy-data/w-user` (out-ahl32 59b03a68, без Юты;
  `tmp/make_w_user.py`): `LEGACY_DATA_WORK=…/w-user python tools/legacy_data/nhl24.py build`. База и локализация
  накладки — те же, что в копии `ud-chi3b`.
- **Формы CHI.**
  - home `1_6_14` (#11) и away `1_6_15` (#12): по умолчанию, `locstring` 0 и 1, `isdefault` 1;
  - three `1_6_6` (#13): «Third (NHL 24)»;
  - EA `1_6_0` и `1_6_1`: «Home (EA)» и «Away (EA)», `locstring` 6, `isdefault` 0.
- **Установка.** Через `tmp/user_nhl24_install.py` (backup → install → check). Внутри — такая команда:
  `CACHE=nhl-legacy-port/userdata/cache/guest LEGACY_DATA_WORK=…/w-user LEGACY_DATA_STATE=…/game/work/legacy-data
  bash tools/legacy_data/install-legacy-data.sh --ahl32 --nhl24`.
  `LEGACY_DATA_STATE` здесь обязателен: без него состояние установщика (installed.txt, флаги) легло бы в w-user, а не
  к прежней установке пользователя.
- **Игра.** Игра пользователя была закрыта. Шёл только тест nhl-legacy-port с `user_data_root` = `ud-chi3b`.
  `nhllegacy.toml` и exe не трогались.
- **Что изменилось в `cache:` пользователя.** Заменены 2 файла, добавлен 171 файл пакета, остальное не тронуто:

  | файл | md5 | было |
  |---|---|---|
  | `db/nhlng.db` | 9ad0695c (out-nhl24-ahl32) | 59b03a68 |
  | `fe/loc/NHL_ENG_US.db` | c7bcfd41 (подписи CHI) | 0973bb47 |
  | `db/draft_roster.db` | 838ca6a0 (без изменений) | — |
  | `db/nhlng-meta.xml` | 8ae5e145 (без изменений) | — |

  `installed.txt` — 3081 путь (было 2910), `install-flags.txt` — `--ahl32 --nhl24`.
- **Проверка.**
  - До установки — на копии (`tmp/check_nhl24.py` → `check-nhl24`): install → 171 новый файл и 2 замены;
    `nhl24.py verify` — 0 расхождений; uninstall `--nhl24` — `cache:` байт в байт как у пользователя, installed.txt —
    тот же набор.
  - После установки у пользователя: изменились ровно база и локализация, новые файлы — ровно файлы пакета.
    `nhl24.py verify` на его `cache:` — 171 файл, расхождений 0, база 9ad0695c.
- **Бэкап:** `game/work/legacy-data/backup-cache/user-20261010-070028/`. В нём:
  - `db/nhlng.db` (59b03a68) и `fe/loc/NHL_ENG_US.db` (0973bb47);
  - `state/installed.txt` и `state/install-flags.txt`;
  - `md5.txt`, `snapshot.json` (размеры и время всех файлов `cache:` до установки) и `added.txt` (171 добавленный
    файл).
- **Откат** (при закрытой игре) — той же командой, что проверена на копии:
  `CACHE=nhl-legacy-port/userdata/cache/guest LEGACY_DATA_WORK=…/w-user LEGACY_DATA_STATE=…/game/work/legacy-data
  bash tools/legacy_data/uninstall-legacy-data.sh --nhl24`.
  - `LEGACY_DATA_WORK=w-user` обязателен. Снятие накладки — это полная переустановка без неё, и без этой переменной
    она возьмёт `game/work/legacy-data/out`, где уже Юта и ветераны.
  - Ручной путь: вернуть 2 файла и `state/` из бэкапа, а файлы из `added.txt` убрать в Корзину.
- **Третья CHI4 (09:11, слово координатора 09:09; решение пользователя).** Третья `1_6_6` теперь — чёрная
  альтернативная форма Чикаго (adidas/two) вместо Winter Classic 2019.
  - Пакет — manifest 511e90bd. Изменились только 5 файлов третьей: `rendering/jersey/texlib_1_6_6.rx2`,
    `rendering/pant/texlib_1_6_6.rx2`, `rendering/sock/sock_1_6_6_cm.rx2`, `fe/ion/artassets/jerseys/jersey_1_6_6.big`,
    `rendering/logo/texlib_6_1_6.rx2`. База (6274f2ab) и локализация (c7bcfd41) — прежние.
  - Проверка на копии (`tmp/check_nhl24_update.py`): установка изменила ровно эти 5 файлов, `verify` прошёл, после
    снятия — как у пользователя без накладки, байт в байт.
  - У пользователя `verify` — 171 файл, расхождений 0.
  - Бэкап — `game/work/legacy-data/backup-cache/user-20261010-091057/`. Откат — вернуть 5 файлов.
- **Шлемы новых форм.** В 07:00 они стояли без исправления: у #11 и #13 шлем был белым вместо чёрного.
  - Исправление (раздел «Цвет шлема» ниже) проверено в ТЕСТ CHI3C.
  - **Поставлено в 08:59** (слово координатора 08:58). Изменился только `db/nhlng.db`: 9ad0695c → 6274f2ab; новых
    и пропавших файлов нет. installed.txt и install-flags не изменились.
  - Игра пользователя была закрыта. Шёл только тест nhl-legacy-port с `user_data_root` = `userdata-ucheck`.
  - `nhl24.py verify` — 171 файл, расхождений 0, база 6274f2ab.
  - Бэкап: `game/work/legacy-data/backup-cache/user-20261010-085918/` (`db/nhlng.db` 9ad0695c, `state/`).
  - Откат к состоянию 07:00 — вернуть этот файл (при закрытой игре).
  - Скрипт — `tmp/user_helmets_install.py`.

## Пакет NHL 24: формы, лёд, шлемы, шайба, клюшки (накладка `out-nhl24`, 09.10.2026)

Пакет готовит агент nhl24 (`tools/fb/pack.py`, [nhl24-uniforms.md](nhl24-uniforms.md) §8). legacy-data сверяет
пакет, собирает базу и ставит его в `cache:` отдельной накладкой поверх `out`. Первым идёт пилот: Чикаго (CHI) и
общие ресурсы (реклама и логотипы на льду, шайба, клюшки). Остальные клубы — после пилота.

**Правила пользователя (действуют с 10.10, 05:50–05:53).**
- Из NHL 24 ставятся только основные комплекты: дом, выезд и третья (если есть). Reverse Retro, формы 90-х и прочие
  спецформы пока не ставятся.
- Формы NHL 24 — только дополнительными строками с новыми вариантами, оригиналы не перезаписываются. У каждого клуба,
  кроме ARI/UTA, новые дом, выезд и третья идут подряд после форм EA. Файл существующего комплекта (он есть в архивах
  Legacy или в `out`: свитер, номер и фамилия, шорты, гетры, превью, наклейка на шлем) в пакете — ошибка сборки.
  Центр льда, реклама на льду и шайба по-прежнему заменяются.
- По умолчанию в матчах и во франшизе — формы NHL 24. Новые дом (тёмный) и выезд (светлый) получают `isdefault` 1.
  У прежней строки по умолчанию того же цвета (EA; у SEA/VGK — наши `1_100_0`/`1`, `1_101_0`/`1`) `isdefault`
  становится 0. Больше в прежних строках ничего не меняется: `hastie`, `locstring`, `jerseyindex`, файлы — как были,
  формы EA остаются в меню. Если у клуба нет нового дома (или выезда), по умолчанию остаётся прежний.
- Уточнение по ТЕСТ CHI3 (legacy-port, 10.10 06:22): без выбора формы CHI дома надел белую выездную NHL 24. Игра ищет
  форму по умолчанию дома по `isdefault` + `locstring` 0, в гостях — по `isdefault` + `locstring` 1. У всех 222 команд
  EA строки по умолчанию — только с `locstring` 0 и 1, `islightcolor` любой. Поэтому:
  - новые home и away получают `locstring` 0 и 1, подпись у них — стандартная Home/Away;
  - прежние строки по умолчанию — `locstring` 6 с подписями «Home (EA)» и «Away (EA)» (ключи
    `Vintage_<style>_<art>_<variant>`), `isdefault` 0;
  - больше в прежних строках ничего не меняется.
  Проверка механизма — ТЕСТ CHI3B (копия `ud-chi3b`).
- **Окончательное правило (решение пользователя 10.10, для всех клубов):**
  - новые дом и выезд NHL 24 — стандартные Home и Away: `locstring` 0 и 1, `isdefault` 1;
  - прежние формы по умолчанию — «Home (EA)» и «Away (EA)»: `locstring` 6, ключи `Vintage_<style>_<art>_<variant>`,
    `isdefault` 0. У SEA и VGK прежние формы по умолчанию — наши (czkit, `1_100_0`/`1`, `1_101_0`/`1`): у них подписи
    «Home (old)» и «Away (old)» (координатор 10.10). Отличие — по свитеру: есть в архивах EA — «(EA)», нет — «(old)»;
  - третья NHL 24 — «Third (NHL 24)», `locstring` 6, `isdefault` 0.
- **По коду игры** (nhl-legacy-port): форму по умолчанию выбирает `sub_82AEAD20`. Среди форм клуба с `isdefault` ≠ 0 она
  берёт ту, у которой `locstring` 0 (дома) или 1 (в гостях); если такой нет — последнюю с `isdefault`. `islightcolor`
  загрузчик не читает. Поэтому с `locstring` 6 новые формы по умолчанию не находились (ТЕСТ CHI3).
- Юту правила не касаются: это переименование Аризоны, формы у неё не из NHL 24.
- Раньше (09.10): шнуровка снималась у заменённых строк — теперь заменённых строк нет; центры льда — всем 32
  клубам, шрифты номеров — все (шрифт входит в свитер новой формы).

**Номера новых форм — вариант «А».** Стиль 1 (Edge), арт клуба (номер EA 0…29, SEA 100, VGK 101), новый вариант.
- Реестр — `tools/legacy_data/nhl24_kits.json` (в git). Номера выдаёт `nhl24.py alloc КЛУБ ФОРМА… --write`,
  порядок в меню — `nhl24.py order КЛУБ home away three --write` (меняет только `jerseyindex`, варианты остаются).
  После установки пользователю номера и порядок закреплены: реестр только дописывается.
- `variant` — наименьший, у которого у этого арта стиля 1 нет ни строки, ни файла комплекта (в архивах Legacy и в
  `out`: свитер, номер и фамилия, шорты, гетры, превью, наклейка на шлем). `fevariant` = `variant`.
- `jerseyindex` — подряд после форм EA, в порядке дом, выезд, третья. `locstring` — 6 у всех новых: своя подпись
  в меню (ниже).
- Номера на 10.10 (06:10) — у 31 клуба, кроме ARI: дом, выезд, третья. Например, CHI: home `1_6_14`, away `1_6_15`,
  three `1_6_6` (`jerseyindex` 10–12). SEA и VGK: `1_100_3`…`5`, `1_101_3`…`5`. Полный список — `nhl24.py show`.
- Резерв CHI (в базу не идёт): rr22 `1_6_7`, rr23 `1_6_8`, n90_three `1_6_9`, n90_two `1_6_10`, n90_four
  `1_6_11`, n90_home `1_6_12`, n90_away `1_6_13` (`jerseyindex` 13–19).
- `jerseyindex` у клуба должен идти подряд 0…N−1: так у всех 224 команд EA, с пропуском игра не проверялась.
  Поэтому форма из реестра может не попасть в пакет, только если после неё у этого клуба в пакете ничего нет.
  Иначе сборка останавливается.
- Двузначный вариант удлиняет имена растров внутри файлов (`1_6_10` на символ длиннее `1_6_0`). Такой файл
  собирается в контейнере EA с номером той же длины: kitpaint `--container`, например `1_10_0`; у наклейки на
  шлем — `texlib_10_1_0`.
- Предел формата — 32 формы на клуб (`jerseyindex`, `variant`, `fevariant` — по 5 бит). В данных EA больше 13 нет.
  **Тест DAL25** (legacy-port, 09.10, копия `game/work/legacy-data/ud-dal25`): 25 форм у Далласа работают. Новые
  строки дописаны в конец таблицы, варианты 1 и 5–15, текстуры — временно чужие комплекты EA.
  - Меню Select Jerseys: 25 форм в порядке `jerseyindex`, карусель листается до конца и обратно.
  - Матчи в #14 и #25 (двузначный вариант `1_9_15`): форма на всех игроках, номера, фамилии, шорты и гетры на
    месте. Чёрных и розовых текстур нет, промахов `cache:` нет. Смены формы в самом матче в игре нет.
  - Составы: сейв ROSTER сохранил таблицу целиком (726 строк, CRC в порядке), после загрузки у DAL снова 25.
  - Старая франшиза (DYNASTY) грузится, в Select Jerseys у DAL тоже 25. Таблицы форм в этом сейве нет, она
    берётся из базы. Этот сейв создан при АХЛ на 30, грузить его — только с `nhl_ahl_teams = 30`
    ([legacy-port.md](legacy-port.md)), к формам это не относится.

**Формат пакета (format 1).** `ПАКЕТ/manifest.json` и `ПАКЕТ/cache/<путь в cache:>` — готовые файлы (RW4 `.rx2`,
BIGF `.big`), ставятся как есть. Пакет по умолчанию — `game/work/nhl24/out/pack` (или `NHL24_PACK=папка`).

```json
{"format": 1,
 "clubs": ["CHI"],
 "files": [{"file": "rendering/jersey/texlib_1_6_6.rx2", "type": "jersey", "md5": "…", "size": 2797568,
            "club": "CHI", "kit": "three", "action": "add"}],
 "kits": [{"club": "CHI", "kit": "three", "variant": 6, "islightcolor": 0}]}
```

- `clubs` — по желанию, для людей: клубы пакета (список кодов или `"all"`).
- `files` — все файлы пакета. `file` — путь в `cache:` (через `/`, без `..`), `md5` и `size` обязательны; `club`,
  `kit`, `action` (add/replace), `note` — для людей. Тип и путь:

  | type | путь в `cache:` | что |
  |---|---|---|
  | jersey | `rendering/jersey/texlib_1_A_V.rx2` | свитер и шрифт номеров |
  | name | `rendering/jersey/name_1_A_V_cm.rx2` | карта номера и фамилии |
  | pant | `rendering/pant/texlib_1_A_V.rx2` | шорты |
  | sock | `rendering/sock/sock_1_A_V_cm.rx2` | гетры |
  | fe | `fe/ion/artassets/jerseys/jersey_1_A_F.big` | превью формы в меню |
  | helmet | `rendering/logo/texlib_A_1_V.rx2` | наклейка на шлем (логотип или спонсор) |
  | center | `rendering/icesurface/centerlogo_A_cm.rx2` | центр льда |
  | ice | `rendering/icesurface/*.rx2` | логотипы и реклама на льду |
  | puck | `rendering/puck/*.rx2` | шайба |
  | stick | `rendering/playerstick/*.rx2` | клюшки |
  | other | `rendering/…` или `fe/…` (`.rx2`, `.big`) | прочее, с полем `note` |

  Файлы вне `rendering/` и `fe/` (например, `db/`) не принимаются: базу собирает legacy-data.
- `kits` — новые формы, то есть новые строки базы. `club` и `kit` — как в реестре (`variant`, если указан, должен
  совпасть), `islightcolor` — 0 или 1 (у `home` — 0, у `away` — 1: они станут формами по умолчанию), `label` — по
  желанию, подпись в меню (до 32 символов). У каждой новой формы в `files` должны быть jersey, name, pant, sock и fe её
  номера. Наклейка на шлем (helmet) — по желанию: есть файл — `helmetlogo` 1, нет — 0.
- Остальные поля новой строки ставит legacy-data: `teamid` клуба, `teamartid` = арт, `style` 1, `islockable` 0,
  `hastie` 0, `helmetnumbers` 1; `isdefault` — 1 у `home` и `away`, 0 у остальных.
- Цвет шлема (разобрано 10.10 по ТЕСТ CHI3: у всех новых форм шлемы были белые).
  - **Значения в базе — со сдвигом.** У полей `team`, `era`, `variant`, `equipment`, `brand` таблицы
    `stockteamequipmenttable` в meta `rangelow` −1: значение = сырое − 1. Например, `team` 7 — CHI (клуб 6), `era`
    0/1/2 — −1/0/1, `variant` 1 — 0, `equipment` 8 — 7 (шлем), `brand` 0 — −1. Значение −1 значит «любое».
  - **Ключ.** В матче `sub_829F1600` → `sub_829EF868` → `sub_82AEED60` ищет строку по ключу
    (era, variant, equipment, brand): era = `style` формы, variant = `variant` формы, equipment 7, brand — бренд
    шлема игрока. Значения берутся из записи формы (`sub_829756C0`: +16 `style`, +24 `variant`).
  - **Выбор** (`sub_82AEDB98`). Строки клуба грузятся с сортировкой по `equipment` (`sub_82AF7610`), внутри одного
    `equipment` — от последней строки базы к первой. Выигрывает строка, у которой первое различающееся поле
    (era, затем variant, затем brand) равно ключу или равно −1.
  - **Как устроено у EA.** У форм стиля 1 строки шлема — с era −1 (в базе 0) и variant формы. У ретро-форм стиля 0 —
    с era 0 (в базе 1). Форма без своей строки берёт первую подходящую в порядке загрузки. У CHI это строка 241
    (светлая), поэтому `1_6_3` и `1_6_4` в игре в белых шлемах, хотя форма тёмная.
  - **Проверка модели.** Модель сходится со всеми 15 кадрами CHI: 10 форм EA в пилоте и 3 новые формы плюс дом и
    выезд EA в ТЕСТ CHI3. Прямой порядок загрузки дал бы 5 промахов. Скрипты — `tmp/helmet_model.py` и
    `tmp/helmets_dry.py`.
  - **Почему ТЕСТ CHI3 не сработал.** Строки 6040/6041 (коммит 6c1e595) были с сырым era 1 и variant 14/6. На деле
    это era 0 (ретро) и variant 13/5. Ни одна новая форма их не находила и брала строку 241, белую.
  - **Как теперь (`nhl24.py`, `add_helmets`).** Новой форме — строка с era −1 (или 1, если у клуба такие строки
    шлема есть) и variant формы. Цвет — шлема, который игра сейчас даёт домашней форме клуба (тёмной новой) или
    выездной (светлой). Задать явно можно в `kits[].helmet`: `home` или `away`.
  - **Цвет каски явно (11.10, `tools/legacy_data/nhl24_helmets.json`).** У SEA и VGK прежние формы czkit — в белых
    шлемах, и новые тёмные брали белый: пользователь увидел у Вегаса в тёмной форме белый шлем.
    - Теперь цвет задан явно: SEA дом — Deep Sea Blue (0, 22, 40) из палитры клуба в `stockteamcolorstable`; в данных
      NHL 24 цвета каски нет, есть только наклейки.
    - VGK дом и третья — выбор пользователя: официальный Steel Grey клуба #333F48 (51, 63, 72). До этого было: золото
      (185, 151, 91, у пользователя с 06:22), затем цвет текстуры шорт (24, 28, 24) и (49, 44, 49) — он почти чёрный,
      от него отказались (`helmets/pant_color.py`, лист `helmets/vgk-pants-helmet.png`).
    - MIN дом (форма NHL 24 — добавка пользователя) — как у прежней домашней 1_14_0: тёмно-зелёный (24, 55, 47).
    - 06:35, пакет eeffaf02 (CHI, SEA, VGK, MIN; 213 файлов).
      - Новая форма MIN дом 1_14_4: по умолчанию Home, прежняя 1_14_0 — «Home (EA)».
      - По модели изменились только VGK 1_101_3 и 1_101_5 (Steel Grey) и MIN. У остальных форм шлем как был.
      - Номера новых строк SEA и VGK сдвинулись на 1: строки идут по клубам, MIN — раньше.
      - Накладка `out-nhl24-ahl32`: база 891bb659, локализация 84b0ec1b.
    - Строка шлема — как у тёмных шлемов EA, Юты и CHI: зона 1 — каска, зоны 2 и 4–9 — (32, 32, 32), зона 3 — (231,
      231, 231).
    - Выезд — по прежнему правилу, белый. UTA и CHI не менялись.
    - Модель: у прежних форм всех четырёх клубов шлем как был. Лист «форма → шлем» —
      `game/work/legacy-data/helmets/helmets-after.png` (скрипт `helmets/helmet_sheet.py`).
  - **Закреплённые формы.** Новые строки в порядке загрузки встают первыми. Без защиты они перехватили бы формы EA,
    у которых нет своей строки шлема. Таким формам дописывается строка с их нынешним цветом. Перед записью модель
    проверяет: у прежних форм клуба шлем не меняется, у новых — как у образца.
  - **Пример CHI.** home `1_6_14` и three `1_6_6` — чёрный (как строка 216 домашней `1_6_0`), away `1_6_15` —
    белый (как 217 выездной `1_6_1`). `1_6_3` и `1_6_4` закреплены белыми (как 241).
  - **ТЕСТ CHI3C пройден** (legacy-port, 10.10; копия `ud-chi3c`, база 6274f2ab; кадры —
    `nhl-legacy-port/out/agent/chi3c/key/`). Новые формы: #11 и #13 — чёрный, #12 — белый. Формы EA: #6 — чёрный,
    #7 — белый, #9 и #10 — белые, как были. Формы по умолчанию в Play Now — #11 дома, #12 в гостях. Промахов
    `cache:` нет.
  - У пользователя с 08:59 (раздел «У пользователя (10.10.2026, 07:00)»).
- Подпись формы в меню Select Jerseys. У строки с `locstring` 2 игра пишет свою «Alternate», а у строки с `locstring`
  6 берёт текст ключа `Vintage_<style>_<art>_<variant>` из локализации: так подписаны 50 винтажных форм EA,
  например `Vintage_0_9_3` — «1968-69 Away», `Vintage_1_2_3` — «2009-10 Classic». Нет ключа — подписи нет: так
  было в тесте DAL25 у #15–#25. Поэтому накладка добавляет такие ключи в `fe/loc/NHL_ENG_US.db` (своя копия от
  `out` и от `out-ahl32`). Текст — `label` из манифеста, иначе по метке: home «Home (NHL 24)», away «Away (NHL 24)»,
  three «Third (NHL 24)» — так новые формы в меню отличаются от EA. Для резерва: rr22 «Reverse Retro 2022», rr23
  «Reverse Retro 2023», n90_home «1990s Home», n90_away «1990s Away», n90_three «1990s Alternate», прочие n90_*
  «1990s Retro».

**Сборка и установка.**

```bash
python tools/legacy_data/nhl24.py alloc CHI three rr22 rr23 --write  # номера новых форм — до упаковки пакета
bash tools/legacy_data/build-all.sh nhl24                           # сверка пакета → out-nhl24 (+ out-nhl24-ahl32)
bash tools/legacy_data/install-legacy-data.sh --ahl32 --nhl24       # поставить (у пользователя вариант --ahl32)
bash tools/legacy_data/uninstall-legacy-data.sh --nhl24             # снять только накладку: cache: — как до неё
python tools/legacy_data/nhl24.py verify ПАПКА_CACHE                 # cache: — как в манифесте и накладке
```

- Этап `nhl24` идёт после `collect`. Каждый файл пакета сверяется по типу, пути, md5 и размеру. Обе базы сначала
  собираются в памяти, потом всё пишется в `out-nhl24.part` и только тогда подменяет накладку (прежняя уходит в
  `_stale/`). При любой ошибке накладка не трогается. Базы накладки — из `out/db` (и `out-ahl32/db` → `out-nhl24-ahl32`): `hastie` 0 у строк со
  свитером из пакета, новые строки — в конец таблицы. Номера прежних строк не сдвигаются. Та же база — `db/draft_roster.db`.
  Отчёт и манифест, по которому собрана накладка, — `game/work/legacy-data/nhl24/`.
- Установщик с `--nhl24` сначала проверяет, что базы и локализация `out` (`out-ahl32`) не пересобраны после
  накладки. Иначе нужен `build-all.sh nhl24`: накладка затёрла бы их прежними.
- Флаги последней полной установки лежат в `install-flags.txt` рядом с `installed.txt`. Полная установка без
  `--nhl24` при стоящей накладке отказывается: снять её — `uninstall --nhl24` или `--no-nhl24`. Так же с `--ahl32`
  (`--no-ahl32`). До `install-flags.txt` вариант `--ahl32` узнаётся по базе в `cache:`.

**Сейвы.** В сейвах франшизы (DYNASTY, 49 таблиц) таблицы `stockteamjerseys` нет, поэтому новые формы появятся и в
уже начатых франшизах. В сейве составов она есть (`savegroups` allloaded, rosters, rosterupdate).

**Папка для друзей.** `nhl-legacy-port/scripts/make_dist.sh --mods` копирует весь `cache:` пользователя. Со стоящей
накладкой туда попадут и файлы NHL 24 (только для личного использования), и база с новыми строками формы. Убрать одни
текстуры нельзя: строки базы останутся, и новые формы будут без файлов. Решение координатора (09.10): dist пока не
трогаем, пользователь соберёт его сам, когда всё будет отлажено. Тогда накладку NHL 24 надо учесть: список её путей —
`game/work/legacy-data/nhl24/files.txt`, база без неё — `out/db` или `out-ahl32/db`.

**Проверено на пробном пакете** (09.10, 20:15–20:25). Пакет собран из файлов EA, без NHL 24: 37 файлов всех типов
пилота, 6 новых форм CHI. Проверка шла на копии `cache:` и `installed.txt` пользователя (вариант `--ahl32`).
- Сборка: в базах накладки отличается только `stockteamjerseys` — 6 новых строк (709 → 715, у `--ahl32` 714 → 720) и строки шлема новых тёмных форм в `stockteamequipmenttable`
  и `hastie` у строк со свитером из пакета. В пробном пакете это CHI `1_6_0`/`1_6_1`, у них шнуровки и так не было.
  Спецформы `1_6_3`/`4`/`5` остались с `hastie` 1. Если добавить в пакет свитер `1_6_5`, `hastie` 0 становится только
  у него.
- `install --nhl24` без `--ahl32` отказывается. `install --ahl32 --nhl24` обновил 39 файлов (37 файлов пакета и
  2 базы), `nhl24.py verify` — всё совпало.
- Полная установка без `--nhl24` отказывается. `uninstall --nhl24` вернул `cache:` байт в байт, как у пользователя.
  В `installed.txt` тот же набор путей, только пересортированный.
- Ошибки пакета останавливают сборку, и прежняя накладка не трогается. Проверены: чужой md5, тип не по пути, у
  новой формы нет гетр, формы нет в реестре, путь `db/`, `variant` не как в реестре, неизвестный клуб.

**Пилот CHI собран** (09.10, 21:50; пакет nhl24 — манифест 85cc99d3).
- В пакете 210 файлов: 10 форм CHI (дом и выезд `1_6_0`/`1_6_1` заменены, 8 новых `1_6_6`…`1_6_13`, у `1_6_10`…`13`
  контейнер `1_10_0`), 9 наклеек на шлем, центр льда, 151 файл логотипов и рекламы на льду, шайба. Клюшки nhl24
  ещё дописывает.
- База накладки: у CHI 18 форм, новые строки 709–716 (у `--ahl32` 714–721). `hastie` нигде не менялся: у заменённых
  дома и выезда шнуровки и так не было, спецформы `1_6_3`/`4`/`5` её сохранили. 7 подписей новых форм.
- Проверка на копии (`check_nhl24.py`): установка `--ahl32 --nhl24` — 210 файлов, база и локализация как в манифесте и
  накладке, больше ничего не тронуто; `uninstall --nhl24` — `cache:` байт в байт как у пользователя.
- Копия userdata для nhl-legacy-port — `game/work/legacy-data/ud-chi`, лист ожидаемых превью — `game/work/legacy-data/nhl24/chi-expected.png`.
- ТЕСТ CHI (legacy-port, 09.10). В игре всё работает: меню на 18 форм с подписями, матчи во всех формах без
  промахов `cache:`, лёд, шайба, сохранение и загрузка составов (сейв: 722 строки, у CHI 18).
  Найдено и исправлено:
  - белые шлемы у новых форм — теперь тёмные получают шлем домашней (коммит 6c1e595);
  - #14 n90_three: чёрная фамилия на чёрной кокетке — nhl24 перекрасил буквы (манифест 8ca9f505).

  На решение пользователя:
  - логотип Reebok на воротнике у форм 90-х (так в NHL 24);
  - у n90_four нет герба и в NHL 24: оставить, поставить герб декалью или убрать форму;
  - клюшки: замена моделей — только по решению пользователя.

  Отдельно nhl-legacy-port разбирает падения GPU и «голубые лица» за долгую сессию: пакет это или порт (копии
  A/B: `ud-ab-plain` и `ud-ab-nhl24`).

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
  `prop/droppedstick_0`, подсетки) — обмотка и там; пересборка — `bash tools/legacy_data/models/build.sh`.
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

Порт nhl-legacy-port (`nhl-legacy-port/codegen/out/build/win-amd64-relwithdebinfo/nhllegacy.exe`, D3D12 ROV),
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
32 (нужны врезки nhl-legacy-port); возраст (врезка года); фон меню (варианты не ставились).

## Правки экипировки пользователя (этап useredits, 11.10.2026)

Экипировку, которую пользователь меняет в игре (клюшки, обмотка, гетры, коньки, шорты, наплечники…), игра хранит в
его сейве `ROSTER …`. Выгрузка — `python tools/legacy_data/user_equipment.py extract НОВЫЙ_СЕЙВ ПРЕДЫДУЩИЙ_СЕЙВ`
(с 20.10.2026; до этого — разовый `game/work/legacy-data/tmp/equip_from_save.py`, вывод тот же), по умолчанию в
`game/work/legacy-data/equipment-user`: полный снимок экипировки и `… — правки.json` (отличия от предыдущего сейва:
игрок, поле, было → стало). Этап `useredits` (после `ahl` и `nhlattrs`) ставит правки во все базы сборки (`nhlng.db` и
`draft_roster.db` в out и out-ahl32) через `tools/legacy_data/user_equipment.py`: только где в базе прежнее значение,
иное — конфликт в отчёт; повтор ничего не меняет. 11.10 04:07: сейв `ROSTER 20261011010728` — 191 правка у 105
игроков (клюшки 53, обмотка 54, гетры 43, коньки 15…), внесены в out, out-ahl32, out-nhl24, out-nhl24-ahl32 (бэкап
баз — `backup-cache/out-before-useredits-20261011-0431`); копии сейвов — `backup-saves/saves-20261011-0428` (и на D:).

## Обмотка игрокам и варианты обмотки (этапы tape и models, 12.10.2026)

Варианты обмотки — коды `sticktapecolor` 3, 4, 6, 8, 9 (белая частичная лента), текстуры `texlib_999.rx2` и сетки
ленты с осевым UV — [player-models.md](player-models.md) §13.
- **models**: `tools/legacy_data/models/build.sh` собирает ещё клюшки полевых и клюшку на льду с осевым UV
  (`models/tape/out-bottom2-axial`, они главнее `out-bottom2`, вратарские остаются оттуда) и `texlib_999.rx2`
  (`models/tapevar`, `tools/tapestyles.py`). В out — 75 своих файлов (`models/files.txt`): + `rendering/playerstick/
  texlib_999.rx2`, заменены 4 `playersticktape_*` и `prop/droppedstick_0`. Проверки — `models/check.sh`
  (`check-tape-axial.log`).
- **tape** (после `useredits`): `tools/legacy_data/tape_players.py` по `tools/legacy_data/tape_players.json` (фамилия
  + дата рождения → код; вратари не трогаются) ставит обмотку в `nhlng.db` и `draft_roster.db` out и out-ahl32. Он же
  пишет подписи вариантов в меню экипировки, в `fe/loc/NHL_ENG_US.db` out и out-ahl32: ключи цветов red, yellow, orange,
  pink, purple → White Middle, White No Toe, White No Heel, White Toe Half, White Strip. Это своя строка в конец пула,
  поэтому «Red» у TEAMLINE2_PRSA остаётся. Ключи blue, green, lightblue не трогаются: они же — цвета глаз в редакторе
  внешности.
- 12.10 (решение пользователя): Jamie Benn 9, Macklin Celebrini 3, Patrick Kane 1, Alex Ovechkin 8, Patrik Laine 0
  (у Кейна и Лайне так и было). У Овечкина в правках пользователя (`ROSTER 20261011010728 — правки.json`) обмотка
  0 → 1 — решение 12.10 её заменяет.
- Сейв состава: `python tools/legacy_data/tape_players.py save СЕЙВ [--write]` — по фамилии и дате рождения в живых
  строках сейва. С `--write` — копия в `backup-saves`, после записи — проверка CRC и обёртки. Запись на копии проверена.

## Экипировка вратарей по клубам (этап goaliegear, 12.10.2026)

Решение пользователя: каждому вратарю клуба — экипировка, заготовленная EA для этого клуба. У клуба без заготовки —
белая экипировка с чёрной графикой и белая маска. Скрипт `tools/legacy_data/goalie_gear.py`, спецификация
`goalie_gear.json`, этап после `tape`.
- **Заготовки** — `stockgoalieequipment` (552 строки). Строка — набор вратаря клуба (`team` = клуб + 1):
  - модели щитков, блина, ловушки и клюшки;
  - маска (`masktype`, `maskid` → `rendering/goaliehelmet/goaliehelmet_<masktype>_<maskid>_cm.rx2`);
  - цвета 9 зон щитков, блина и ловушки, 3 зон клюшки, `showcustomcolors`/`showcustomstick` (0 — цвета клуба из
    `stockteamequipmenttable`, виды 0–2 — щитки, блин, ловушка).

  У клуба 1–5 наборов. Основной — тот, у кого маска равна `exhibitionteams.goaliemask<masktype>_starter`, запасной —
  `_backup`. Наборы есть у 222 строк. Нет у SEA и VGK, CV и HSK, заготовок Custom.
- **Кому что.** Вратарь по составу (`exhibitionrostertable`): g1 — основной набор, g2 — запасной, третий и дальше —
  следующие. Клуб — первый клуб лиг НХЛ (строки 0–31), АХЛ, Европы и CHL. Сборные, Матч звёзд, Top Prospects, Winter
  Classic и EASHL не считаются. Копируются все поля набора, кроме своих у вратаря: `jerseytuck`, `sticktapecolor`,
  `keepcustom*`. Свободные агенты не трогаются.
- **Белый** (`white`): модели вратаря свои, маска 0_120 — белая. Зоны 1, 4, 6–9 белые (231), 2, 3, 5 чёрные (32) —
  как у заготовки PIT с золотом → чёрным. Клюшка: 1 белая, 2–3 чёрные.
- **Спорные — всегда белый** (решение пользователя 12.10, `white_names`). Сюда входят наборы прежних клубов на
  переименованных слотах: Юта (Аризона, маски с койотом), Abbotsford, Belleville, Hamilton, Cleveland, Springfield,
  Laval, Colorado Eagles, Calgary Wranglers, Utica Comets. Сверка с логотипами 2026/27 — лист
  `game/work/models/goalie/look/contested.png`. Ещё сюда входят клубы, чьи наборы EA берут цвета клуба, которых в
  `stockteamequipmenttable` нет: HC Lausanne, EHC München, HC Olomouc. Вместе с SEA, VGK, CV и HSK (наборов нет) —
  белые 17 клубов (37 вратарей) в out-ahl32 и 15 (33) в out.
- **12.10, 09:50**: менялась только `exhibitiongoalieequipment`, CRC OK, повтор — 0. В out-ahl32 по набору —
  178 клубов (427 вратарей), белые — 17 клубов (37 вратарей). Сначала было 09:47: Belleville, Laval, Calgary и 3
  европейских клуба шли с набором.
  - Базы: out 71286e7d / draft eb7a3a5c, out-ahl32 da4e8845 / draft fb6e04a8.
  - Накладка (пакет `pack-installed-b589fa58`): out-nhl24 ce0b2abe, out-nhl24-ahl32 f820ccf3.
  - Бэкапы — `backup-cache/out-before-goaliegear-20261012-094715` и `out-before-goaliewhite-*`, отчёты —
    `game/work/legacy-data/goaliegear/`.
  - Правок пользователя по вратарям нет: в `equipment-user` ни одной, в сейве ROSTER 20261011041455 вратари совпадают с
    `cache:`. Игра не проверялась.
- Сейв: `python tools/legacy_data/goalie_gear.py save СЕЙВ [--write]` — по составам и наборам самого сейва; с
  `--write` — копия в `backup-saves`, после записи — проверка CRC и обёртки.

## Контракты 2026/27 (этап contracts, 12.10.2026)

Настоящие кэп-хиты и подписанные продления вместо заглушек конвейера. Страницы контрактов 32 клубов собрал
пользователь, разбор — `game/work/contracts/parse_pp.py` → `game/work/contracts/screens/<КЛУБ>.json`. Это данные только
для личного использования, ни страницы, ни JSON, ни разборщик в git не идут. Скрипт этапа — `tools/legacy_data/contracts.py`,
этап после `goaliegear`, до `photos24` и накладки `nhl24`.
- **Заглушки.** `--payroll-max 100` ужимает контракты-заглушки (`roster/write.py`, `cap_payroll`) на этапе `roster`.
  Этап `contracts` идёт после него, настоящие суммы не ужимаются. Заглушки остаются у тех, кого на страницах нет.
- **Кто берётся.** Группы Forwards, Defence, Goaltenders и Non-roster *. Retained, Buyout и Buried не берутся:
  «закопанные» есть и в Non-roster. Неподписанные RFA (кэп-хита нет) не трогаются.
- **Сшивка** — по дате рождения и имени: без диакритики, форма имени (Matt / Matthew), сведение транслитерации
  (Sergeyev / Sergeev, Novosyolov / Novoselov). Ещё два случая: та же фамилия и первая буква имени (Jake / Jacob
  Middleton); та же фамилия и тот же клуб (Cooper / Robert Flinton). Тёзки одного клуба с одной датой на странице
  (VAN: Elias Pettersson 1998 и 2004) разводятся по амплуа. Спорные не берутся, они идут в отчёт. Если в базе у игрока
  права другого клуба, он переводится (ниже, «Перевод»). Без прав НХЛ в базе или в пуле свободных агентов — контракт не
  ставится.
- **Поля.**
  - Отрезок — сезоны подряд с одним кэп-хитом. Страница показывает 5 сезонов, последний отрезок длится до года
    окончания.
  - `contractdollars` — кэп-хит 2026/27 / 5000, `contractlength` — длина 1-го отрезка. `contractis2way` — значок
    двустороннего контракта сезона (разборщик пишет его в `two_way` по сезонам). `contractismultiyear` — длина > 1,
    `contractstatus` 1 (сырое: rangelow −1, «на контракте»).
  - `extension*` — 2-й отрезок, подписанное продление. Игра переносит его в контракт в конце июня, когда истекает
    текущий: [legacy-port.md](legacy-port.md), «Продление контракта».
  - `yearufa` — у EA год рождения + 27. В конце контракта без продления игра делает игрока UFA при `yearufa` ≤ год,
    иначе RFA. Поэтому при окончании UFA* в год Y — min(рожд. + 27, Y), при RFA* — max(рожд. + 27, Y + 1).
  - `contractneedsentrylevel` = 0. У игры это «не подписан, первый контракт — новичковый»: ставит драфт, у EA у всех
    подписанных 0. Новичковые контракты только считаются в отчёте.
- **12.10, 13:32**, out / out-ahl32:
  - сшито 1336 / 1378, контракт поставлен 1311 / 1353 (4522 / 4667 значений); спорный 1 (Kai Schwindt: 17.12 на
    странице, 7.12 в базе);
  - не найдено 173 / 131, почти все — Non-roster: проспекты вне базы. Из основных составов — 17: LTIR (Krug,
    Couture, Ellis), вратари и игроки, которых нет в базе;
  - клуб в базе другой — 6, без прав НХЛ — 17, неподписанных — 8, с продлением — 36, новичковых — 371 / 397;
  - повтор — 0 изменений, CRC OK, `draft_roster.db` заново;
  - базы (после перевода 13:45): out 87d7882f / draft a78f7505, out-ahl32 262b2300 / draft 8d829c93; до этапа — копии в
    `game/work/contracts/research/backup-out/`; отчёты и ведомости — `game/work/legacy-data/contracts/`.
  - Накладки out-nhl24 и out-nhl24-ahl32 пока на прежних контрактах: нужен повтор этапа `nhl24`.
- **Ведомости** (как считает игра: сумма по составу клуба НХЛ, `exhibitionrostertable`). В составах 796 настоящих
  контрактов и 2 заглушки (неподписанные RFA). Сверх потолка 104 млн: TOR 105,61, FLA 104,72, NYR 104,64, ANA 104,45,
  DAL 104,13; VGK — ровно 104,00. Остальные 26 — от 81,3 (SJS) до 103,9 (WSH).
- **Перевод** (решение пользователя 12.10; `--no-move` — без него). Игрок с правами другого клуба НХЛ уходит в клуб
  страницы: основной состав страницы — в клуб НХЛ, Non-roster — в его фарм-клуб АХЛ, в запас. Его места в звеньях,
  спецбригадах, буллитах и «одет» в прежнем клубе получает запасной того же амплуа. Если своего запасного нет (клубы
  CHL/Европы одеты целиком), берётся запасной того же амплуа из клуба той же лиги, с номером ушедшего. Буква — лучшему
  одетому без буквы. Номер в новом клубе — свой, занят — ближайший свободный.
  - 12.10, 13:45, out и out-ahl32, переведены 6:
    - Hallander PIT → EDM, № 11;
    - Struble MTL → NSH, № 47 занят → 45 (его места в MTL — Guhle);
    - MacDermid Erie Otters (права LAK) → OTT, № 23 (места — запасной защитник CHL);
    - Graves Québec Remparts (права NYR) → PIT, № 27 (места — Matt Murphy, буква A — одетому Québec);
    - Stastney EDM → PIT, № 24;
    - Merzlikins HC Lugano (права CBJ) → TOR, № 30 (g2 Lugano — запасной вратарь Ambri-Piotta).
  - Ведомости: EDM 101,81 → 101,14, MTL 96,92 → 95,50, NSH 92,51 → 93,92, OTT 99,74 → 100,89, PIT 91,02 → 96,19,
    TOR 105,61 → 110,03. Сверх потолка — те же 5: TOR, FLA, NYR, ANA, DAL.
  - Проверка всей базы, как roster verify: 0 ошибок. CRC OK, повтор — 0 изменений. Копии до перевода —
    `game/work/contracts/research/backup-out2/`.
- **Сейв состава:** `python tools/legacy_data/contracts.py save СЕЙВ [--write]` — та же сшивка в живых строках сейва.
  Сейв — это и есть сохранённые составы, поэтому
  `save` и переводит по тем же правилам. Атрибуты не трогаются (правки пользователя). `ROSTER 20261012084608` без
  `--write`: 1353 игрока, 4667 значений, те же 6 переводов, сейв не изменился (md5 до и после 22bd493f). Ведомость базы без сшивки —
  `contracts.py payroll БАЗА.db [--md ФАЙЛ]`.

**Свитера adidas отдельными формами (16.10.2026, решение пользователя: «в отдельные слоты с соответствующим названием для
каждой команды»).** Свитер NHL 24 adidas на своей сетке (стиль 0 — слот ретро-сеток, docs/nhl24-uniforms.md §14) — у 31
клуба (кроме Юты) формы `ad_home` и `ad_away` с подписями «Home (adidas)» / «Away (adidas)» (`locstring` 6, ключ
`Vintage_0_<арт>_<вариант>`), не по умолчанию. Пакет — `game/work/nhl24/out/pack-adidas` (`python -m fb.jersey_mesh pack`:
установленный пакет `pack-installed-f86ca9dd` + 62 формы + общие файлы типа other: 30 сеток свитера стиля 0, «рубашка»
полевых, шорты и карты гетр стиля 0 = Edge).
- `nhl24.py alloc КЛУБ ad_home ad_away --style 0` — номера стиля 0 (стиль хранится в записи реестра; старые записи — 1).
  Вариант не берётся, если у клуба уже есть строка шлема с ним (у EA такие есть без формы: BUF 0_3_3, CAR 0_5_2).
- Порядок в меню: у клубов, где формы NHL 24 стоят (CHI, SEA, VGK, MIN), adidas — сразу после них, у остальных — перед
  зарезервированными формами NHL 24 (`order`).
- Строки adidas (и их шлемы) пишутся после строк прежних форм пакета: строки и шлемы уже поставленных форм остаются на
  своих местах (как в сейве). Модель шлема учитывает строки под бренд каски (у CGY — бренд 4).
- **Сейв ROSTER** хранит `stockteamjerseys` и `stockteamequipmenttable` свои: `nhl24.py save СЕЙВ --write` дописывает в
  него новые строки базы `cache:` (прежние записи сейва должны совпадать с базой). У пользователя 16.10: +62 формы,
  +79 строк шлемов; копия — `game/work/legacy-data/backup-saves/ROSTER 20261012105521-20261016-093045/`.
- Установлено 16.10 09:28 (`install-legacy-data.sh --ahl32 --nhl24`): база cache: 82cf29c5 (out-nhl24-ahl32), 629 файлов
  пакета, 71 подпись. Тестовые файлы слотов 0_23_0 / 0_29_0 убраны из cache: (`models/adidas/backup-testslots-*`).
