# Ресерч: откуда брать данные для базы 2026/27

Сводка от 07.10.2026. Сезон НХЛ 2026/27 уже идёт: у Кросби 3 матча. Пометки те же, что в [research-rosters-community.md](research-rosters-community.md):

- **[П]** — вызвал URL сам и видел поля. У CSV и картинок смотрел только заголовки (HEAD), файлы не скачивал;
- **[С]** — знаю из документации или поиска: сам не вызывал, или сайт не пустил;
- **[?]** — вывод или предположение.

**Коротко.**

- **Скелет базы — API НХЛ, бесплатно.** Составы и проспекты 32 клубов, карточка игрока (биография, драфт, статистика по всем лигам с детства), фото, логотипы. С октября 2025 Cloudflare режет частые запросы — нужна пауза 0,5–1 с.
- **Контракты — CapWages.** Тип контракта (новичковый, двусторонний, стандартный), UFA/RFA, суммы по сезонам вместе с зарплатой в АХЛ; у игрока есть `nhlId` и `epId`. Легальный путь — API за $25/мес. PuckPedia и Spotrac автоматике недоступны.
- **Рейтинги NHL 27.**
  - Сайт EA отдаёт только топ-300: 40 атрибутов, OVR от 84.
  - nhlratings.net: OVR для 1 046 игроков НХЛ, атрибуты — у части.
  - Остальное считать самим: MoneyPuck, NHL EDGE, stats REST.
- **Другие лиги без платы.**
  - АХЛ, ECHL, OHL, WHL, QMJHL — HockeyTech, публичные ключи работают.
  - Liiga, SHL, NL — открытый JSON сайтов лиг.
  - DEL и Extraliga — только HTML.
- **EliteProspects API не обязателен.** Бесплатный тариф урезан, каждый регион — $480 в год.

## 0. Какие поля нужны базе и откуда их брать

Поля — из `game/extracted/big/cache/db/nhlng-meta.xml`.

| Поля NHL 13 | Источник |
|---|---|
| `exhibitionplayerbiotable`: `firstname`, `lastname`, `year`/`month`/`day`, `birthplace`, `state`, `intlcountry`, `height`, `weight`, `handedness`, `position`, `jersey`, `team` | НХЛ — `roster`, `prospects`, `landing` (§1); АХЛ и CHL — HockeyTech; Европа — API и сайты лиг (§4) |
| `draftyear`, `draftround`, `draftposition`, `draftteam` | `landing.draftDetails` [П]. Что хранит `draftposition` — общий номер или номер в раунде, — сверить на известном игроке [?] |
| `yearprodebut` | первый сезон НХЛ в `landing.seasonTotals` или поле `firstSeasonForGameType` в `skater/bios` [П] |
| `nhlgamesplayed*` (карьера, прошлый сезон, 2 и 3 сезона назад), `progamesplayedcareer`, `juniorteam`, `juniorleague` | `landing.seasonTotals` [П] |
| `contractdollars`, `contractlength`, `contractis2way`, `contractneedsentrylevel`, `contractismultiyear`, `yearufa`, `extension*` | CapWages (§2) |
| `yearwaivereligible`, `waiversneedreentry` | CapWages `termsWaiversExempt` и records API (`waiverStatus`, `yearsPro`, `ageSignWaiver`); посчитать по правилам CBA [?] |
| `exhibitionskaterai`: 25 атрибутов `p_*`, `p_overall`, `p_potential`, `p_style`; `exhibitiongoalieai`: `g_gsh`, `g_gsl`, `g_ssh`, `g_ssl`, `g_5hole` и др. | EA NHL 27, nhlratings.net (§3); остальное — расчёт |
| `exhibitionteams.primarycolor_*`, `secondarycolor_*` | CapWages `teamMetadata` (hex), Wikipedia `Module:Sports color/ice hockey` |
| `exhibitionarena`: `arenaname`, `cityname`, `maxattendance` | название — `venue` в расписании НХЛ [П]. Вместимость — Wikipedia, EP API (`arenas`), в Liiga — `current_venue_capacity` |
| `exhibitionrostertable`: звенья `l1lw…l4rw`, `pp*`, `pk*`, `ot_*`, буллиты `s1–s5`, `captain` | CapWages `projectedDepth`; DailyFaceoff — со спецбригадами |

## 1. API НХЛ

### 1.1 api-web.nhle.com [П]

Проверено на Кросби (8471675) и составе «Питтсбурга».

| URL | Что даёт |
|---|---|
| `/v1/roster/PIT/current` (или `/v1/roster/PIT/20262027`) | 16 нападающих, 7 защитников, 2 вратаря. Поля: `id`, `headshot`, `firstName`/`lastName` с переводами cs/fi/sk, `sweaterNumber`, `positionCode` (C/L/R/D/G), `shootsCatches`, рост в дюймах и см, вес в фунтах и кг, `birthDate`, `birthCity`, `birthStateProvince`, `birthCountry` (ISO-3). Провинция записана по-разному: `ON` или `Wisconsin` — нормализовать. Список сезонов — `/v1/roster-season/PIT`: 59, с 1967/68 |
| `/v1/prospects/PIT` | 37 проспектов (16 F, 16 D, 5 G) с теми же полями — игроки АХЛ, юниоры, Европа |
| `/v1/player/8471675/landing` (35 КБ) | поля из состава, а также: <br>• `draftDetails {year, teamAbbrev, round, pickInRound, overallPick}`, `currentTeamAbbrev`, `heroImage`; <br>• `seasonTotals` — 57 строк по всем лигам с детства (NSMHL, QMJHL, NHL, ЧМ, ОИ…): `leagueAbbrev`, `gameTypeId` 2 или 3, `teamName`, игры, голы, передачи, штраф, +/-, броски, TOI, % вбрасываний; <br>• `careerTotals`, `awards`, `last5Games`, `inHHOF`. <br>У проспектов `seasonTotals` захватывает другие лиги: у Шаррона — OHL 2026/27, у Фернстрёма — SHL, у Ильина — КХЛ |
| `/v1/standings/now` (307 на `/v1/standings/2026-10-06`) | 32 клуба, включая UTA, SEA, VGK: аббревиатура, названия, `teamLogo`, `teamLogoDark`, конференция, дивизион |
| `/v1/club-schedule-season/PIT/now` (307 на `.../20262027`) | календарь; у домашних матчей `venue` = «PPG Paints Arena» — отсюда названия арен |
| `/v1/club-stats/PIT/now` | статистика сезона по игрокам клуба |
| `/v1/draft/picks/2026/all` | 224 выбора: раунд, номер, клуб, имя, позиция, страна, рост, вес, любительская лига и клуб. **Без `playerId`.** Годы — с 1979 |
| `/v1/draft/rankings/now` | 253 проспекта Central Scouting: дата и место рождения, хват, итоговое место — пригодится для `p_potential` |
| `/v1/edge/skater-detail/8471675/20252026/2` | NHL EDGE: лучший бросок 144,2 км/ч (перцентиль 0,82), скорость 36,8 км/ч (0,81), пройденная дистанция, время в зонах, броски по точкам. Данные есть с 2021/22. Рядом — `skater-skating-speed-detail`, `skater-shot-speed-detail`, `goalie-detail` |

Ограничения:

- **429 от Cloudflare.** Примерно с 28.10.2025 он отвечает так на частые запросы, лимиты нигде не опубликованы ([issue #73](https://github.com/Zmalski/NHL-API-Reference/issues/73)). Судя по комментариям, хватает паузы 0,5 с.
- **Кэш.** `Cache-Control: max-age` — несколько секунд.
- **Редиректы.** Эндпоинты `…/now` отвечают 307 — клиент должен идти по редиректу.

### 1.2 api.nhle.com/stats/rest [П]

**`/en/skater/bios`.** Пример запроса: `?isAggregate=false&isGame=false&start=0&limit=-1&cayenneExp=gameTypeId=2 and seasonId=20262027`.

- `limit=-1` отдаёт всё. На 07.10 это 625 строк — в отчёт попадают только сыгравшие.
- Поля:
  - рождение: `birthCity`, `birthCountryCode`, `birthStateProvinceCode`, `birthDate`;
  - драфт: `draftYear`, `draftRound`, `draftOverall` — команды нет;
  - **`firstSeasonForGameType`** — дебютный сезон;
  - прочее: `height`, `weight`, `nationalityCode`, `positionCode`, `shootsCatches`, `currentTeamAbbrev`, `isInHallOfFameYn`.

**`/en/config`** — список отчётов:

- у полевых — 18, в том числе `summary`, `realtime` (хиты, блоки, потери, перехваты), `timeonice`, `faceoffwins`, `percentages`, `puckPossessions`, `shottype`;
- у вратарей — 8, у команд — 24.

**Справочники.** `/en/team` — 62 клуба вместе с историческими, `/en/franchise` — 40 франшиз.

### 1.3 records.nhl.com/site/api [П]

**`/player?cayenneExp=id=8471675`** — служебные поля:

- **`epPlayerId` = 6146** — ID в EliteProspects;
- `accruedSeasons`, `group5SeasonsEarned`, `group6SeasonsEarned`, `nhlExperience`, `yearsPro`;
- `waiverStatus`, `ageSignWaiver`, `ageSignelFa`;
- `isJunior`, `isRookie`, `lastAmateurLeagueId`, `lastAmateurTeamId`, `vetCapExcptn`.

По ним можно проверить статус UFA/RFA и драфт отказов [?] и связать игрока с EP. Фильтр `currentTeamId=5 and onRoster='Y'` даёт 23 игрока.

**`/draft?cayenneExp=draftYear=2005 and overallPickNumber=1`** — драфт **с `playerId`**, а также клуб и место рождения.

### 1.4 search.d3.nhle.com [П]

`/api/v1/search/player?culture=en-us&limit=10000&q=*&active=true` — 1 997 активных игроков системы НХЛ одним запросом. Поля: `playerId`, `teamAbbrev`, `lastSeasonId`, номер, рост, вес, город и страна рождения.

### 1.5 Фото и логотипы [П, HEAD]

| Шаблон | Что это |
|---|---|
| `https://assets.nhle.com/mugs/nhl/{сезон}/{TEAM}/{id}.png` | портрет PNG. Для сезона 20262027 уже есть: у Кросби 84 КБ, за 20252026 — 179 КБ |
| `https://assets.nhle.com/mugs/nhl/latest/{id}.png` | текущий портрет, тот же файл; по этому адресу API отдаёт портреты части проспектов |
| `https://assets.nhle.com/mugs/nhl/default-skater.png` | заглушка |
| `https://assets.nhle.com/mugs/actionshots/1296x729/{id}.jpg` | игровое фото (`heroImage`) |
| `https://assets.nhle.com/logos/nhl/svg/{TEAM}_light.svg`, `_dark.svg` | логотип SVG. Старые эмблемы — по шаблону `{TEAM}_{20062007-20152016}_light.svg`, как в `/v1/standings/2013-03-01` (там же `PHX_20032004-20132014`). Есть `NHL_light.svg`; `PIT_secondary_light.svg` отдаёт 404 |

Старые хосты — `nhl.bamcontent.com`, `cms.nhl.bamgrid.com`, `www-league.nhlstatic.com`, `statsapi.web.nhl.com` — у меня не ответили (ошибка TLS). statsapi закрыли в 2023 году [С], так что старая документация (dword4/nhlapi) больше не годится.

### 1.6 Документация и библиотеки

- [Zmalski/NHL-API-Reference](https://github.com/Zmalski/NHL-API-Reference) — 609★, MIT, обновлён 07.11.2025. Основной справочник по обоим API [П].
- [dfleis/nhl-api-docs](https://github.com/dfleis/nhl-api-docs) — автоматический разбор 500+ эндпоинтов, 09.2025 [С].
- [coreyjs/nhl-api-py](https://github.com/coreyjs/nhl-api-py) — пакет `nhl-api-py` 3.3.0 на PyPI (11.05.2026), Apache-2.0, Python ≥ 3.9 [П, по README].
  - Методы: `client.teams.team_roster(team_abbr, season)`, `client.stats.player_career_stats(player_id)`, `client.edge.skater_detail(...)`; есть конструктор запросов к stats REST.
  - Пауз между запросами не делает — проще своя обёртка.
- R-пакеты fastRhockey (sportsdataverse) и `nhlscraper` (CRAN) работают с тем же API [С].

### 1.7 ToS

ToS NHL.com разрешает только «non-commercial, informational, personal use» и запрещает «unauthorized spidering, scraping, or harvesting» [П]. API неофициальный, сообщество пользуется им открыто. Для личного мода это серая зона с низким риском; результат не публиковать.

## 2. Контракты и зарплаты

| Источник | Что есть | Автоматизация, ToS | |
|---|---|---|---|
| **CapWages** (capwages.com) | всё, что нужно игре, — подробности ниже | API — аддон за $25 в месяц или $280 в год, работает без основной подписки. Ключ выдают в настройках после оплаты. Не больше 4 запросов в секунду, полный импорт — раз в сутки | [П] |
| PuckPedia | кэп-хиты, пункты контракта, бонусы | сайт закрыт проверкой Cloudflare: «Just a moment…», 403 и для curl, и для WebFetch. По поисковой выдаче есть план «Hobby / Developer» с некоммерческим API, цену не увидел | [С] |
| Spotrac | контракты | на любой автоматический запрос — 403 или 402; публичного API нет | [С] |
| CapFriendly | — | закрыт в июле 2024 года: сайт выкупили «Вашингтон Кэпиталз»; домен не отвечает | [С] |
| Hockey-Reference | — | контрактов нет: `/contracts/PIT.html` отдаёт 404 | [П] |
| records API НХЛ | выслуга и драфт отказов, сумм нет | — | [П] |
| EP API, аддон Transfer Data (+$228 в год) | «transfers, signings, contract data» — для контрактов в Европе | платно | [С] |

**CapWages** [П]. Сайт на Next.js, данные лежат в JSON `__NEXT_DATA__` страниц.

**Страница клуба** `https://capwages.com/teams/pittsburgh_penguins`:

- `teamMetadata` — цвета (`primary_color` #FFB81C, `secondary_color` #000000), GM, главный тренер, дивизион, город;
- `data.roster` и `non-roster` — игроки:
  - `status`: NHL, Minor, Junior, Loan, IR, SOIR;
  - `terms`: ELC, NMC, M-NTC;
  - `termsWaiversExempt`, `termsSlideCandidate`, номер, хват;
- у каждого игрока `contracts[]`:
  - `type` — Entry-Level, Two-Way, Standard или 35+, с пометкой «(Extension)» у продлений;
  - `expiryStatus` — UFA, RFA, RFA (Arb), RFA (10.2), UFA (Group 6);
  - `details[]` по сезонам — `capHit`, `aav`, `baseSalary`, `signingBonuses`, `performanceBonuses`, **`minorsSalary`** (зарплата в фарме — признак двустороннего контракта; у новичкового контракта Киндела — $85 000), `clause`;
- `reserves` — неподписанные выборы драфта со сроком `mustSignBy`;
- `ahlClub` — фарм-клуб WBS: 17 игроков с контрактами АХЛ и сроками;
- `projectedDepth` — звенья, ключи `lw`, `c`, `rw`, `ld`, `rd`, `g`.

**Страница игрока** `https://capwages.com/players/sidney-crosby` — дополнительно:

- **`nhlId` 8471675 и `epId` 6146**;
- место рождения, рост, вес;
- все контракты. Пример — Кросби: продление по правилу 35+, 2 года, $17,4 млн, кэп-хит $8,7 млн, по окончании UFA, подписан 16.09.2024;
- статистика по сезонам, транзакции.

**API** — `https://capwages.com/api/gateway/v1`, [описание](https://capwages.com/api-docs) [С — без ключа не вызывал]:

- `/players` — список страницами, `limit=100`;
- `/players/:slug` — профиль и контракты;
- `/lineups/:teamSlug` — текущий состав по звеньям.

**ToS CapWages.**

- Данные объявлены собственностью сайта. В разделе про API запрещено «sell, rent, sublicense, bulk-download, repost, or otherwise redistribute».
- Явного запрета парсить сайт я не нашёл; `robots.txt` разрешает всё, кроме `/players/` для Amazonbot.
- Чистый путь — месяц API ($25) на снимок сезона.
- Технически всё есть и на 32 страницах клубов. Парсить ли их — решать вам [?].

## 3. Рейтинги

### 3.1 EA SPORTS NHL 27 — https://www.ea.com/games/nhl/ratings [П]

**Формат.** Сайт уже показывает рейтинги NHL 27 и продаёт игру. Страница сделана на Next.js: в `__NEXT_DATA__` лежит `props.pageProps.ratingDetails = {items[50], totalItems: 300}`, страницы листаются параметром `?page=1…6`.

**Поля игрока:**

- `id` — внутренний ID EA (Макдэвид — 9857, Кросби — 1082), `firstName`, `lastName`, `overallRating`, `jerseyNum`, `rank`;
- `position` — Center, Left Wing, Right Wing, Left Defense, Right Defense, Goalie;
- `team`, `nationality`, `playerAbilities` (X-Factor), `avatarUrl`;
- `stats` — 40 атрибутов вида `{value, diff}`:
  - полевые: acceleration, agility, balance, endurance, speed, strength, durability, aggression, bodyChecking, discipline, fightingSkill, defensiveAwareness, offensiveAwareness, handeye, deking, passing, puckControl, poise, shotBlocking, stickChecking, faceoffs, slapshotAccuracy, slapshotPower, wristshotAccuracy, wristshotPower;
  - вратарские: glovesideHigh, glovesideLow, sticksideHigh, sticksideLow, fiveHole, pokeCheck, angles, reboundControl, breakaway, puckplayingFrequency, aggressiveness, vision, shotRecover.

Атрибуты почти один в один совпадают с полями `p_*` и `g_*` в NHL 13; `angles` соответствует `g_positioning`.

**Охват — только топ-300 (OVR от 84).**

- Страница клуба `/ratings/teams-ratings/pittsburgh-penguins/23` — 8 игроков. Канадцев всего 119, вратарей 28.
- К запуску NHL 26 EA выложила по 10 лучших игроков каждого клуба — 320 человек [С]. Возможно, список NHL 27 тоже расширят — стоит перепроверить.

**JSON-API есть, но пустой.**

- `https://drop-api.ea.com/rating/nhl?locale=en&limit=…&offset=…` вызывает сам код страницы. `/rating/nhl/filters` отвечает, `orderBy` принимает `ovr`, `acl`, `spd`, `dek`, `pas`, `slp`, `wsp`.
- На публичные запросы API отдаёт `{"items":[],"totalItems":0}` — данные есть только в HTML страниц.

**ToS EA.** Лицензия — только личная и некоммерческая, копирование контента ограничено: серая зона [?]. NHL ID в данных EA нет — сшивать по имени, клубу и номеру.

### 3.2 nhlratings.net [П]

Сайт сообщества с рейтингами NHL 27.

- На страницах 32 клубов — 1 046 игроков: от 27 до 41 на клуб, у PIT — 36.
- OVR есть и у тех, кого нет в топ-300 EA: у Бразо — 82. Полный набор атрибутов — только у части игроков: у Кросби цифры есть, у Бразо — «--».
- Вратарские атрибуты собраны в списках топ-100 (`/lists/…`).
- `robots.txt` закрывает только `/wp-admin/`. Сайт живёт на рекламе, ToS не читал.
- Готовый сборщик — `tools/providers/ea_ratings.py` в [puckpeak-nhl-legacy-rosters](https://github.com/MatusRiedl/puckpeak-nhl-legacy-rosters) (MIT): 1 запрос в секунду, около 40 минут.

### 3.3 Другие готовые рейтинги

- **NHL HUT Builder** (nhlhutbuilder.com) — база карточек NHL 27 со всеми атрибутами. `robots.txt` закрывает сайт для curl, wget, python-requests и HTTrack, а также путь `/api/`. Годится только для ручной сверки [П].
- **Rono от CapWages** — их собственный OVR (у Кросби 85, поле `positional`), входит в платный тариф Pro [П, частично].
- **Premier Pivot Rosters 2025/26** — база Eastside Hockey Manager (EHM) в Steam: игроки всего мира, шкала 1–20. Версии 2026/27 не нашёл, формат — собственный файл EHM [С].
- Полных таблиц рейтингов NHL 26/27 на Kaggle и GitHub не нашёл [С].

### 3.4 Сырьё для собственного расчёта

| Источник | Что | Условия | |
|---|---|---|---|
| MoneyPuck | CSV сезона: `https://moneypuck.com/moneypuck/playerData/seasonSummary/{год}/regular/{skaters,goalies,lines,teams}.csv`; год — начало сезона (файл за 2026 обновлён 07.10.2026 в 03:29 GMT, за 2025 — 18.04.2026). Биографии с 2007 — `…/playerBios/allPlayersLookup.csv`. Броски — ZIP на peter-tanner.com, к данным есть словари полей | «free to use for non-commercial purposes»; ссылаться на MoneyPuck. Неодобренный парсинг сайта блокируется | [П, HEAD] |
| NHL EDGE | перцентили скорости и силы броска (§1.1): Speed, Acceleration, Slap/Wrist Power | как у API НХЛ | [П] |
| stats REST | `realtime` (хиты, блоки, потери, перехваты), игровое время, вбрасывания, % реализации | как у API НХЛ | [П] |
| Natural Stat Trick | 5 на 5, xG, сочетания игроков | API нет, автоматике отвечает 403, в `robots.txt` `Crawl-delay: 240`. Только ручная выгрузка CSV из браузера | [П] |
| Evolving-Hockey | GAR, xGAR, RAPM | подписка от $5 в месяц (по их блогу), GAR — в тарифе Pro. API нет | [С] |
| Hockey-Reference | история | не больше 20 запросов в минуту, иначе блок до суток [С]; в `robots.txt` `Crawl-delay: 3`; контрактов нет | [П] |
| NHLe | пересчёт очков в других лигах в эквивалент НХЛ | статьи [Rethinking NHLe](https://thibaudchatel.substack.com/p/rethinking-nhle), Network NHLe (CJ Turtoro) | [С] |

Для игроков без рейтингов EA есть готовая схема — `legacy_roster/estimate.py` в puckpeak [П, код]:

- уровень игрока = медиана НХЛ по позиции + разрыв лиги + поправки на возраст и роль;
- разрывы в баллах рейтинга для нападающих / защитников / вратарей:
  - AHL: −6,1 / −5,6 / −6,9;
  - SHL: −7,4 / −7,1 / −8,0;
  - Liiga: −8,8 / −7,7 / −9,3;
  - DEL: −7,9 / −9,4 / −8,9;
  - Extraliga: −5,9 / −6,0 / −10,7;
  - NL: −4,8 / −5,8 / −6,6;
  - CHL: −13,5 / −13,0 / −15,7.

По словам автора, разрывы измерены на финальном составе EA, где оценены все лиги.

## 4. Европа, АХЛ, юниоры

### HockeyTech: АХЛ, ECHL, OHL, WHL, QMJHL, USHL [П]

На нём же Мемориальный кубок CHL.

**Запрос:** `https://lscluster.hockeytech.com/feed/?feed=modulekit&view=…&key=KEY&client_code=CODE&fmt=json&lang=en`.

**Ключи** — публичные, взяты с сайтов лиг. Все отдали сезоны 2026/27.

| `client_code` | Ключ | `season_id` регулярки 2026/27 |
|---|---|---|
| `ahl` | 50c2cd9b5e18e390 | 94 |
| `ohl` | 2976319eb44abe94 | 88 |
| `whl` | 41b145a848f4bd67 | 295 |
| `lhjmq` (QMJHL) | f322673b6bcae299 | 214 |
| `echl` | 2c2b89ea7345cae8 | 78 |
| `ushl` | e828f89b243dc43f | 91 |
| `chl` | f1aa699db3d81487 | — (только Мемориальный кубок) |

**Режимы (`view`):**

- `seasons` — список сезонов;
- `teamsbyseason&season_id=` — клубы сезона: в АХЛ 32, логотип в `team_logo_url` (например, `…/ahl/logos/316_94.png`);
- `roster&team_id=&season_id=` — состав: в «Уилкс-Барре» 26 записей. Поля: дата и место рождения, рост, вес, хват, позиция, номер, `status`, `draftinfo[]`, фото `https://assets.leaguestat.com/ahl/240x240/{id}.jpg`. В OHL место рождения бывает пустым, а рост записан как «6.00»;
- `player&category=seasonstats&player_id=` — статистика по сезонам: игры, голы, передачи, штраф, +/-, броски, вбрасывания, хиты.

Доступ неофициальный, ключи могут смениться.

### Сайты европейских лиг

| Лига | Как получить | Что даёт | |
|---|---|---|---|
| Liiga | `https://liiga.fi/api/v2/players/info?tournament=runkosarja&fromSeason=2027&toSeason=2027`; сезон 2027 = 2026/27 | 525 игроков одним запросом: дата, место и страна рождения, рост, вес, хват, номер, амплуа, капитаны, фото. Дополнительно — `players/info/{id}` (история по сезонам), `players/stats/summed/2027/2027/runkosarja/true?dataType=basicStats`, `teams/info` (вместимость арен, логотипы) | [П] |
| SHL | JSON сайта (платформа Sportality). Цепочка: `https://www.shl.se/api/sports-v2/season-series-game-types-filter` → `game-schedule?seasonUuid=&seriesUuid=&gameTypeUuid=` → `athletes/by-team-uuid/{team}` → `athlete-details/{uuid}`. Официальный openapi.shl.se мёртв (ошибка 522) | 14 клубов. В составе — 25 игроков с номером, гражданством, портретом. В карточке — дата рождения, рост, вес, хват, `playerExtIds` | [П] |
| NL (Швейцария) | `https://www.nationalleague.ch/api/teams` (14 клубов) → `/api/player/team/{teamId}`. Есть и `https://data.sihf.ch/Statistic/api/cms/cache300?alias=player&…` — таблицы с выгрузкой CSV, но параметр лиги я не подобрал | дата рождения, номер, позиция, статистика; капитан — по коду puckpeak (`isCaptain`). Рост, вес и хват часто пустые | [П] |
| Extraliga | HTML: `https://www.hokej.cz/klub/{клуб}/{id}/soupiska` — составы 2026/27 уже есть | номер, имя, дата рождения, хват, рост, вес, страна; фото — на странице игрока | [П] |
| DEL | HTML: `https://www.penny-del.org/teams` → `/teams/{slug}/kader` (14 клубов) | номер, фото, имя, гражданство, хват, **возраст вместо даты рождения**, рост, вес. Дату рождения брать из Wikidata или EP | [П] |

ToS сайтов лиг не проверял. Готовые парсеры всех пяти лиг и HockeyTech — `tools/providers/` в puckpeak (MIT).

### EliteProspects API [П, тарифы]

Адрес — `https://api.eliteprospects.com/v1/`, ключ — в заголовке `X-Api-Key`; без ключа отвечает 401. [Тарифы](https://developer.eliteprospects.com/pricing) на 07.10.2026:

- **Explorer** — бесплатно: 1 000 вызовов в месяц, 10 в минуту, базовые поля.
- **Personal** (хобби, некоммерческое использование) — база $0 в месяц: 5 000 вызовов в месяц, 60 в минуту. Регионы оплачиваются отдельно.
- **Регионы** — по +$480 в год каждый:
  - North America: NHL, AHL, ECHL, WHL, OHL, QMJHL, USHL, NAHL;
  - Nordics: SHL, Allsvenskan, Liiga и др.;
  - Central Europe: DEL, NL, ICEHL, чешская и словацкая Extraliga и др.;
  - Russia & East: KHL и др.;
  - Global (все регионы) — $1 200 в год.
- **Группы данных** (в год): Draft +$228, Transfer с контрактами +$228, Game +$348, Staff +$108.
- **История**: текущий сезон бесплатно, более ранние — разовой покупкой.
- **Commercial** — $990 в год, **Enterprise** — $5 000 в год.

Что есть в API, по документации:

- игроки: позиция, гражданство, дата рождения, рост, вес, статус; статистика; фото; переходы;
- клубы с цветами; заявки (номер, роль, тип контракта); арены с вместимостью; драфт.

Ключ выдают по заявке на developer.eliteprospects.com, один на организацию. По условиям API лицензия действует только в пределах купленного тарифа. Сайт eliteprospects.com в обход API лучше не парсить [?].

### Связка ID через Wikidata [П]

Бесплатно, лицензия CC0. SPARQL на `https://query.wikidata.org/sparql`:

- P3522 — NHL.com ID (есть у 14 036 человек);
- P2481 — EliteProspects ID (39 951);
- P569 — дата рождения, P19 — место рождения;
- заодно — имена по-русски.

Кросби: Q311280, NHL 8471675 ↔ EP 6146.

### Что не подходит

- **Не для автоматики:** QuantHockey (проверка Cloudflare); пакет `eliteprospect-scraper` с PyPI — он парсит сайт EP.
- **Открываются, но ToS не проверял:** EuroHockey, HockeyDB [П].

## 5. Готовые датасеты

| Датасет | Состав | Обновление | |
|---|---|---|---|
| MoneyPuck CSV (§3.4) | статистика сезона, в том числе продвинутая; биографии с 2007 | ежедневно | [П, HEAD] |
| [sportsdataverse/fastRhockey-nhl-data](https://github.com/sportsdataverse/fastRhockey-nhl-data) | релизы `nhl_rosters`, `nhl_player_boxscores`, `nhl_schedules`, `nhl_pbp_full` и `nhl_pbp_lite` в CSV, Parquet и RDS, сезоны 2010/11–2025/26, MIT. Собрано из API НХЛ | ежедневно в сезон через GitHub Actions; последний коммит 07.10.2026 | [П] репозиторий |
| [sportsdataverse/fastRhockey-data](https://github.com/sportsdataverse/fastRhockey-data) | `nhl_teams_colors_logos.csv` (8 КБ) — цвета и логотипы клубов | — | [П] список файлов |
| Wikipedia, [`Module:Sports color/ice hockey`](https://en.wikipedia.org/wiki/Module:Sports_color/ice_hockey) (`?action=raw`) | 92 записи: по 4 цвета hex на клуб НХЛ (включая Utah Mammoth), бывшие клубы, PWHL, сборные | правят вручную | [П] |
| [patrickendres/nhl_wiki_agg](https://github.com/patrickendres/nhl_wiki_agg) | составы 32 клубов из Wikipedia → CSV | 08.2026 | [С] |
| [danmorse314/hockeyR-data](https://github.com/danmorse314/hockeyR-data) | только протоколы матчей (play-by-play) | 06.2024 | [С] |
| Kaggle | «NHL 2024-25 Stats/contacts» (устарел), «NHL Game Data» (до 2020) | — | [С] |
| Контракты 2026/27 | открытых наборов нет: выгрузки пропали после закрытия CapFriendly | — | [С] |

## Рекомендуемый конвейер

**Общие правила.**

- **Ключ игрока** — NHL `playerId`. Для тех, кто вне системы НХЛ, — имя, фамилия и дата рождения; EP ID — через Wikidata или records API.
- **Кэш.** Все сырые ответы сохранять с датой снимка, например в `game/data/raw/2026-10-07/…` — вне git, как файлы игры.
- **Запросы.** Пауза 0,5–1 с между запросами; при 429 — повтор с растущей паузой; по редиректам 307 идти.

**Порядок сборки.**

1. **Клубы НХЛ.** `standings/now` даёт 32 клуба; как разложить их по слотам игры — см. [teams.md](teams.md).
   - Логотипы — SVG с `assets.nhle.com`, перевести в растр.
   - Цвета — из CapWages `teamMetadata` или Wikipedia, в поля `primarycolor_r/g/b`.
   - Арены — `venue` из календаря; вместимость — Wikipedia (32 числа можно вписать руками).
2. **Список игроков.** `roster/{T}/20262027` и `prospects/{T}` по всем 32 клубам. Альтернатива — поиск `search.d3`: 1 997 активных игроков одним запросом.
3. **Карточки.** `player/{id}/landing` по каждому — около 2 000 запросов, 17–35 минут.
   - Отсюда биография, драфт и `seasonTotals`: матчи по сезонам, юниорский клуб, дебют.
   - Дебютный сезон надёжнее взять из `skater/bios` и `goalie/bios` (`firstSeasonForGameType`, запрос с `limit=-1`).
4. **Служебные поля.** records API `player`: `epPlayerId`, выслуга, драфт отказов → `yearwaivereligible`, проверка статуса UFA/RFA.
5. **Контракты.** CapWages, сшивка по `nhlId`:

   | Поле игры | Откуда в CapWages |
   |---|---|
   | `contractdollars` | `aav` или `capHit` |
   | `contractlength` | последний сезон в `details` |
   | `yearufa` | `expiryStatus` |
   | `contractis2way` | тип Two-Way или `minorsSalary` |
   | `contractneedsentrylevel` | тип Entry-Level (ELC) |

   Плюс контракты АХЛ из `ahlClub`. Юниорам и европейцам — без контракта или значения по умолчанию.
6. **АХЛ и CHL.** HockeyTech `roster` и `seasonstats`: 32 клуба АХЛ и около 60 клубов OHL, WHL и QMJHL.
   - Добрать тех, кого нет в системе НХЛ; фото — с leaguestat.
   - С игроками НХЛ сшивать по имени и дате рождения.
7. **Европа.**

   | Лига | Объём |
   |---|---|
   | Liiga | 1 запрос |
   | SHL | около 370 запросов |
   | NL | 15 запросов |
   | Extraliga | 14 HTML-страниц |
   | DEL | 14 HTML-страниц; дату рождения — из Wikidata или старой базы |

   Проспекты НХЛ, играющие в Европе, уже есть в шаге 3.
8. **Рейтинги.**
   - EA NHL 27: 6 страниц → атрибуты для топ-300 переносятся один в один.
   - nhlratings.net → OVR и стиль игры для ~1 050 игроков НХЛ, атрибуты — где есть.
   - **Остальные игроки НХЛ — модель.** Обучить на 300 размеченных игроках. Признаки: MoneyPuck (показатели на 60 минут, xG), stats REST, перцентили EDGE, рост, вес, возраст. Затем подогнать результат под OVR с nhlratings.net и под шкалу исходной `nhlng.db` по позициям.
   - АХЛ, CHL и Европа — «медиана НХЛ + разрыв лиги + возраст» (коэффициенты в `estimate.py` puckpeak) или NHLe по очкам.
   - `p_potential` — по возрасту, номеру драфта и `draft/rankings`.
9. **Звенья.**
   - Основные: CapWages `projectedDepth` (или API `/lineups`) → `l1…l4`, `g1`/`g2`.
   - Спецбригады и капитаны: DailyFaceoff. На странице `line-combinations` есть JSON Next.js; страница открывается, ToS не проверял [П].
10. **Фото.** Портреты НХЛ, потом leaguestat, Liiga и SHL, в конце — заглушка.
11. **Запись.** `tools/tdb.py` → `cache:\db\nhlng.db`.
    - Контракт не должен ссылаться на игрока не из этого клуба.
    - В NHL Legacy от этого падает «Управление командой» (по коду puckpeak `builder.py`); для NHL 13 не проверено [?].

**Бюджет.** Всё бесплатно, кроме желательного месяца CapWages API ($25). EP API (от $480 в год) нужен, только если хочется точных дат рождения в DEL и контрактов в Европе.

**Использование.** Всё — только для себя: готовую базу не публиковать.
