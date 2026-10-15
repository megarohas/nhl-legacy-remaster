# Utah Mammoth вместо Arizona Coyotes (NHL Legacy)

09.10.2026, агент utah. Здесь собраны данные и арт, чтобы строка 22 базы Legacy (Arizona Coyotes) стала клубом
**Utah Mammoth** сезона 2026/27, а его фарм-клуб (строка 55, Springfield Falcons) — **Tucson Roadrunners**.
Ничего не поставлено и не применено:
- арт лежит в `game/work/utah/out/` (дерево как в `cache:`), концепт третьей формы — в `game/work/utah/out-third/`;
- спецификация для legacy-data — `game/work/utah/utah_spec.json`;
- листы на проверку — `game/work/utah/compare/*.png`.

Инструменты лежат в `tools/utah/` (в git). Исходники логотипов (SVG и PNG НХЛ, АХЛ, Википедии) лежат в
`game/work/utah/src/` и в git не идут: они только для личного использования.

## Коротко

| Что | Было (база CACHE) | Стало |
|---|---|---|
| клуб, строка 22 | Arizona Coyotes®, ARZ / PHX, Glendale | **Utah Mammoth**, UTA, Salt Lake City, UT |
| дивизион | Central (nhl32 уже перенёс) | Central, Западная конференция — без изменений |
| арт | 22 (файлы EA) | **104**: логотипы t/s/d/c/w/r, центр льда, шайба, баннер, форма, шлем, меню |
| прожектор, туннель | 22 / 22 (Coyotes) | 48 (свой логотип) / 38 (нейтральный EA SPORTS) |
| арена | 22 «Arizona Arena», модель Аризоны | Delta Center, Salt Lake City, UT, 14 111; модель — «EA SPORTS Arena», как у SEA/VGK |
| форма | 8 комплектов EA 2015/16 | дом 1_104_0 (Rock Black), выезд 1_104_1 (Salt White); третья — концепт, по желанию |
| цвета | кирпичный, песочный, чёрный | Mountain Blue #6CACE4, Rock Black #010101, Salt White #FFFFFF |
| фарм-клуб, строка 55 | Springfield Falcons, art 153 | **Tucson Roadrunners**, TUC, art 105, Tucson Arena (6 521) |

## 1. Клуб: что выяснено (09.10.2026)

| Что | Значение | Источник |
|---|---|---|
| название | Utah Hockey Club (2024/25, временное) → **Utah Mammoth** с 07.05.2025. Новый клуб (франшиза 40), хоккейные активы Arizona Coyotes (франшиза 28) переданы 18.04.2024 | [NHL.com](https://www.nhl.com/news/mammoth-unveiled-as-utah-nickname), [релиз клуба](https://www.nhl.com/utah/news/utah-s-nhl-franchise-officially-named-the-utah-mammoth-release-5-7-25), [stats API](https://api.nhle.com/stats/rest/en/franchise) |
| город, сокращение | Salt Lake City, Utah; **UTA**. В API на 2026/27: teamName «Utah Mammoth», placeName «Utah», teamCommonName «Mammoth» | [standings/now](https://api-web.nhle.com/v1/standings/now), [roster/UTA](https://api-web.nhle.com/v1/roster/UTA/current) |
| арена | **Delta Center**, без переименований; перестройка идёт до 2027. Официальной вместимости на хоккее после перестройки нет. На матчах 2026/27 — **14 111** (протоколы 26.09 и 01.10.2026); в Википедии устаревшие 16 020. 31.12.2026 Юта принимает «Колорадо» в Зимней классике на Rice-Eccles Stadium | [протокол матча](https://www.nhl.com/scores/htmlreports/20262027/GS020013.HTM), [Википедия](https://en.wikipedia.org/wiki/Delta_Center), [календарь](https://api-web.nhle.com/v1/club-schedule-season/UTA/20262027) |
| дивизион 2026/27 | Западная конференция, Центральный: CHI, COL, DAL, MIN, NSH, STL, UTA, WPG | [standings/now](https://api-web.nhle.com/v1/standings/now) |
| цвета | Rock Black **#010101**, Mountain Blue **#6CACE4**, Salt White **#FFFFFF** — по векторному логотипу НХЛ. Сайт клуба и Википедия дают голубой #7AB2E0; по NHL.com Mountain Blue — это Pantone 292 (≈ #69B3E7). Взят #6CACE4, как в логотипе | [UTA_light.svg](https://assets.nhle.com/logos/nhl/svg/UTA_light.svg), [NHL.com 2024](https://www.nhl.com/news/utah-hockey-club-proud-of-inaugural-jersey-design) |
| логотипы | основной — **Mountain Mammoth** (вектор НХЛ, `UTA_light`/`UTA_dark` одинаковы, ™ убран). Второстепенные: «UTAH» с бивнем, «U» с бивнем (на шортах), **Utah Badge** — штат с надписью UTAH (плечи домашней), надписи UTAH MAMMOTH | [набор логотипов NHL.com](https://media.d3.nhle.com/image/private/t_q-best/prd/lvoknrhnxhtpwzes7wlb), [Utah Badge, фр. Википедия](https://fr.wikipedia.org/wiki/Fichier:Logo_secondaire_du_Mammoth_de_l%27Utah.png) |
| форма 2026/27 | дом и выезд 2025/26 без изменений (фото с матчей 01.10 и 03.10.2026). **Третьей нет.** Hometown Remix (Fanatics, у всех 32 клубов) покажут в ноябре; у Юты, по утечке, — голубая основа с «U»/бивнем | [фото формы](https://media.d3.nhle.com/image/private/t_q-best/prd/qgijqeqcmd2ouolnrxf2), [матч 01.10](https://www.nhl.com/utah/news/utah-opens-season-with-6-0-win-over-chicago-game-story-10-1-26), [Hometown Remix](https://www.nhl.com/news/hometown-remix-uniforms-coming-to-nhl-2026-27-season), [Deseret, утечка](https://www.deseret.com/sports/2026/08/19/nhl-hometown-remix-jerseys/) |
| шрифт | **Mammoth Sans** (Doubleday & Cartwright): наклон вперёд 10°, косые перекладины у A и H; номера и фамилии. В открытом доступе шрифта нет | [релиз клуба](https://www.nhl.com/utah/news/utah-s-nhl-franchise-officially-named-the-utah-mammoth-release-5-7-25) |
| реклама | шлем — Filevine, нашивки — SME Steel (дом), 1Password (выезд) | [Filevine](https://www.nhl.com/utah/news/utah-mammoth-announce-filevine-as-official-helmet-partner-release-9-9-25), [SME](https://www.nhl.com/utah/news/utah-announces-sme-industries-inc-as-home-jersey-patch-partner-release-10-14-25), [1Password](https://www.nhl.com/utah/news/utah-mammoth-unveil-1password-as-first-ever-away-jersey-patch-partner-release-10-9-25) |
| фарм-клуб | **Tucson Roadrunners** (TUC), Тусон; Tucson Arena (Tucson Convention Center, 6 521 на хоккее); Тихоокеанский дивизион. Аренда продлена до 2027/28, переезда и переименования нет. Логотип 2026/27 у АХЛ — «Dusty»; «Качина» был основным в 2025/26 (10-летие) | [NHL.com, 25.09.2026](https://www.nhl.com/utah/news/utah-holds-practice-at-delta-center-on-friday-notebook-9-25-26), [АХЛ](https://theahl.com/news/roadrunners-extend-lease-at-tucson-arena), [Википедия](https://en.wikipedia.org/wiki/Tucson_Roadrunners), [логотип АХЛ](https://assets.leaguestat.com/ahl/logos/412_94.png) |

Как выглядит форма. Описание — по официальному фото NHL.com, пропорции полос замерены по его пикселям.

**Дом (Rock Black):**
- на груди — Mountain Mammoth, на плечах — Utah Badge;
- рукава: голубой, просвет, белый (чуть шире), просвет, голубой — на уровне локтя;
- низ: белый, просвет, голубой, ниже — чёрная кайма;
- ворот: тонкая голубая кайма, щит НХЛ в мыске;
- номера белые с голубой обводкой, фамилия без обводки;
- шорты чёрные с «U» на бедре.

**Выезд (Salt White):**
- на груди — «UTAH» лесенкой (чёрный с голубой обводкой), на плечах — Mountain Mammoth;
- рукава: голубой, широкий чёрный, голубой;
- низ: широкий чёрный, голубой, ниже — белая кайма;
- ворот: широкая голубая полоса;
- номера чёрные с голубой обводкой.

Гетры повторяют полосы рукавов. Шлемы — чёрные дома и белые в гостях.

## 2. Что сейчас на месте ARI в базе (CACHE пользователя, только чтение)

Базу брал из копии `nhl-legacy-port/userdata/cache/guest/db` → `game/work/utah/ref/cache-db`. Это вариант `--ahl32`, md5
34dfe267. В `out/` legacy-data (958f4b6d) строки 22 и 55 те же.

| Таблица | Что там |
|---|---|
| `exhibitionteams[22]` | fullname «Arizona Coyotes®», shortname «Arizona», abbrname **ARZ**, artabbr **PHX**, artid 22, audioid 22, spotlight 22, tunnel 22, arenaid 22, Central (divisiongroup 4, конференция 1), ahlaffiliate 56 (строка 55), rivalteam 14 («Лос-Анджелес»), цвета #97002E / #EEE1C5 |
| `exhibitionarena[22]` | «Arizona Arena», «Glendale, AZ», 18 000; модель 22, звук арены и города 22, кричалки, сирены и кольцо — свои 22 |
| `stockteamjerseys` 183–190 | 8 комплектов teamartid 22: стиль 1 — варианты 3 (дом), 4 (выезд), 0/1 (винтаж, шнуровка); стиль 0 — 0, 1, 3, 4 |
| `stockteamcolorstable` 76–78 | colorid 0/1/2 = #97002E, #EEE1C5, #231F20 |
| `stockteamequipmenttable` | 26 строк с team 23 (номер + 1): шлемы, перчатки и др. в цветах Coyotes |
| `stockgoalieequipment` | 3 строки team 23 (вратари 2015/16) |
| локализация | `NHLTeamName_22`, `NHLCityName_22`, `NICKLINE2_22`, `CITYLINE1_22`, `NHLTeamName_Abbr3_22`; по сокращениям — `*_PHX` (TEAMLINE1/2, NICKLINE2, TXT_NICKNAME «Coyotes»/ALT «Yotes»…), `TEAMLINE2_ARZ` |
| фарм-клуб, строка 55 | Springfield Falcons (SPR, art 153, audioid 154), арена 52 «MassMutual Center», Springfield, MA (6 679, модель АХЛ 145); комплекты 327/328 (teamartid 153); Atlantic (10, Восток) |

Арт Аризоны в архивах Legacy устроен так.
- По `artid` 22: логотипы, центр льда (с надписью ARIZONA ARENA по дуге), шайба, баннер, наклейка на шлем, форма,
  `teamnumbers` и `pb_22`.
- По арене (`arenaartid` 22): модель, табло `jumbotron/texlib_22` с логотипом, кольцо `powerring_22_*` и отражения на
  шлемах `enviro/helmet_22` («PHOENIX COYOTES»). Сюда же, судя по логам порта, толпа: `crowd/team_22_*` (форма Coyotes)
  и `prop_team_*_22` (плакаты «GO COYOTES»). У арены «EA SPORTS Arena» вместо них общие `team_998`.
- По полям команды: туннель `tunnel/texlib_22` и прожектор `spotlight/texlib_22`.

## 3. Решения

- **Новый номер арта — 104.** Так же сделаны SEA 100, VGK 101, CV 102 и HSK 103. Перерисовывать арт 22 не стал:
  - файлы EA Аризоны не затираются;
  - откат — вернуть `artid 22`;
  - не пересекается с пакетом NHL 24 агента nhl24: по решению координатора новые формы идут «на прежние номера арта
    клуба», а у NHL 24 есть только Arizona.

  Номера 104–107 свободны во всех наборах арта Legacy, у прожекторов есть 0…45, 46 и 47 занимают SEA/VGK. У Тусона —
  105.
- **Арена — нейтральная модель «EA SPORTS Arena»**, как у SEA и VGK. В 3D-модели Аризоны везде Coyotes (§2):
  табло, толпа, плакаты, кольцо, отражения, дальний план льда. Названия и вместимость — Delta Center. Другой
  вариант описан в спецификации (`arena_alternative`): оставить модель 22 и только переименовать, но тогда «койоты»
  останутся в 3D, а диктор объявит Аризону.
- **Звук — номер 32 (без записей)**, как у SEA: так проверено в игре. С 22 комментатор говорил бы «Coyotes».
  У Тусона — 57 (свободный, как 55/56 у CV/HSK).
- **Форма — свой рисунок по официальному фото**, крой Reebok Edge (стиль 1). NHL 24 Юты не знает. Решения
  пользователя по всем формам выполнены:
  - шнуровки нет, `hastie 0`;
  - V-вставка ворота — в цвет свитера: и «рубашка» в вырезе, и клин под ним;
  - щит НХЛ — у мыска ворота.
- **Шрифт** — свой квадратный, с наклоном 10° и косыми перекладинами у A и H (`tools/utah/blockfont.py`). Это
  приближение Mammoth Sans по фото: настоящий шрифт фирменный и в открытом доступе его нет.
- **Наклейка на шлем** — Mountain Mammoth (`helmetlogo 1`), как у всех клубов НХЛ у EA. Рекламу не ставил: ни
  Filevine на шлем, ни нашивки SME Steel и 1Password. У EA в Legacy рекламы на форме нет — вопрос к пользователю.
- **Третья форма** официально не показана. Собран концепт по утечке Hometown Remix: Mountain Blue, «U» с бивнем на
  груди. Он лежит отдельно, в `out-third/`.

## 4. Что собрано (`game/work/utah/out/`, 66 файлов, 26 МБ)

| Файлы | Что |
|---|---|
| `fe/ion/artassets/teamlogos*/{t,s,d,c,w,r}104.big` | логотипы интерфейса (`teamart.py build`, размеры по замерам EA Legacy) |
| `rendering/icesurface/centerlogo_104_cm.rx2` | центр льда 1024² в формате Legacy: диск, кольцо, полоса под красную линию, логотип и «DELTA CENTER» по дуге, как «ARIZONA ARENA» у EA (`tools/utah/center_ice.py`) |
| `rendering/puck/puck_104_cm.rx2`, `banner/banner_104_cm.rx2`, `spotlight/texlib_48.rx2` | шайба (стиль шайб НХЛ Legacy), баннер, прожекторы |
| `rendering/jersey/texlib_1_104_{0,1}.rx2`, `name_1_104_{0,1}_cm.rx2`, `pant/texlib_1_104_*`, `sock/sock_1_104_*_cm`, `fe/ion/artassets/jerseys/jersey_1_104_{0,1}.big` | форма дом и выезд: свитер (цвет, блеск, рельеф), атлас номеров, карта мест номера (как у «Питтсбурга»: буква капитана — на левой груди игрока), шорты, гетры, превью меню в позе EA (модель `game/work/legacy-data/fepose/pose.bin`) |
| `rendering/logo/texlib_104_1_{0,1}.rx2` | наклейка на шлем |
| `fe/ion/artassets/playerbackgrounds/pb_104.big`, `twittericonsteam/t104.big`, `teamnumbers/tn104_*.big`, `teamnumbersflat/tnf104_*.big`, `playermenubackgrounds/104_{0,1}.big` | фон карточки игрока, значок ленты новостей, цифры шрифтом клуба для меню, картинка левой панели (у EA у всех клубов одна, копия) — `tools/utah/ui_extra.py` |
| `…105…` | Тусон: логотипы t/s/d/c/w, центр льда с «TUCSON ARENA», шайба АХЛ, баннер, форма 1_105_{0,1}, наклейка на шлем |

В `out-third/` лежат 6 файлов концепта третьей формы: `1_104_2` и наклейка `texlib_104_1_2`.

Контейнеры — файлы EA той же структуры с трёхзначным номером: комплекты `1_131_0`, логотипы 3D `*_150`, наклейка на
шлем `texlib_131_1_0`. Меняются только пиксели и имена растров.

Проверки (все — 0 ошибок):
- `kitpaint verify` всех комплектов против контейнера;
- `verify_out.py` логотипов против шаблонов EA;
- `teamart roundtrip` всех 72 файлов.

Листы `game/work/utah/compare/`:

| Лист | Что |
|---|---|
| `logos.png` | все логотипы: Аризона сейчас \| Юта |
| `center_ice.png` | центр льда: Аризона сейчас \| Юта |
| `kits_front_back.png` | свитера на модели Legacy спереди и сзади, с примером номера и фамилии (KELLER 9, C) |
| `menu_preview.png` | превью в меню, рядом Аризона EA |
| `ui_helmet_font.png` | фон карточки, значок, цифра меню, наклейка на шлем, атласы номеров |
| `third_concept.png` | концепт третьей формы |
| `tucson_logos.png`, `tucson_kits.png` | Тусон |

## 5. Как рисуется форма (`tools/utah/kitdesign.py`)

Развёртка свитера Legacy стиля 1 — это крест:
- спина сверху, её кромка низа — верхний край текстуры;
- перёд снизу;
- рукава слева и справа, манжеты — у краёв;
- в середине вырез ворота;
- в углу 0,08…0,18 × 0,85…0,90 — сетка «рубашки» в V-вырезе.

По сеткам Legacy (`tools/fb/kit3d`, `kit_hybrid.legacy_with_shirt`) каждый тексель получает точку на поверхности.
Полосы строятся по расстоянию на поверхности:
- **низ** — от кромки низа вдоль столбцов. На передней и задней частях, которые сходятся в боковом шве, полосы
  совпадают и идут параллельно кромке;
- **рукава** — прямые полосы поперёк рукава, как рисует EA. Сантиметры считаются по среднему профилю строк: у
  манжеты подгиб, первые ~10 текселей дают 4–7 см.
- **правило полосок (11.10)** — то же, что у форм NHL 24 (`[sleeve]` в `tools/fb/kit_rules.toml`,
  [nhl24-uniforms.md](nhl24-uniforms.md) §11). Полосы рукава сжимаются к манжете, чтобы номер на плече (зоны 2 и 3
  карты номеров формы) на них не ложился. Делается до логотипов, они не сдвигаются. У Юты полосы заходили в зону
  номера на 0,04; при нижнем пределе k = 0,7 зазор 0,026–0,028 по u.

Поверх полос:
- зоны ворота кроя 4 конструктора: кайма, ворот внутри, клин V-вставки;
- строчка швов кроя 4;
- рельеф и блеск — чистые карты кроя 4. Их же берёт перенос NHL 24, поэтому ткань у всех одинаковая.

Логотипы ставятся в 3D-точку (`at3d`) с размером в сантиметрах. Поворот подбирается так, чтобы верх логотипа смотрел
вверх по телу: плечевые нашивки — на передней части плеча. Затем `kitpaint.apply_logos` наносит цвет, блеск вышивки и
рельеф.

Атлас номеров (`tools/utah/fontatlas.py`) повторяет раскладку EA. По 118 атласам клубов НХЛ Legacy она фиксирована:
- буквы — в ячейках по 32 px (у M и W по две ячейки);
- большие цифры — по 80 px;
- малые — по 48 px, две строки;
- C и A — в столбце справа.

Глифы ставятся по центрам рамок EA той же высоты. Слои атласа:
- обводка — снаружи глифа; у фамилии её нет, как на настоящей форме;
- под прозрачным — цвет края;
- `font_nm` — рельеф ступеней «заливка/обводка» плюс фактура ткани из атласа EA;
- `font_sm` — серый, альфа 0/255.

## 6. Фарм-клуб: Tucson Roadrunners (строка 55, арт 105)

Логотип взят у АХЛ на 2026/27 — «Dusty», PNG 500×500 (`assets.leaguestat.com/ahl/logos/412_94.png`). Цвета сняты с
него:
- бордовый #790023;
- песочный #EDDFC0;
- медный #AB724B;
- чёрный #181210.

Логотипы t/s/d/c/w, шайба АХЛ, баннер и центр льда с «TUCSON ARENA» собраны тем же пайплайном, что CV/HSK. Формы АХЛ
у Тусона на 2026/27 не опубликованы (2025/26 — «Качина», зелёная и белая), поэтому сделана **форма по мотивам
классической 2016–2025**:
- дом — бордовый;
- выезд — белый;
- полосы чёрный/песочный/чёрный;
- на груди Dusty, на плечах — логотип Юты;
- номера — Bahnschrift.

Вопрос о «Качине» открыт (§9). Комплекты Springfield (арт 153) у EA не тронуты.

Дивизион по умолчанию не меняется: строка 55 остаётся в Atlantic, как Springfield в 2015/16. Дерево АХЛ задаёт код, а
в варианте `--ahl32` — врезка legacy-port. Как перенести в Pacific без поломки 8/8/8/8 — в спецификации
(`ahl.division_note`): 55 → Pacific, 52 San Antonio → Central, 36 Charlotte → Atlantic.

## 7. Спецификация для legacy-data (`game/work/utah/utah_spec.json`)

Её делает `tools/utah/make_spec.py` по копии базы и локализации CACHE. По каждому полю там есть «было» (из базы),
«стало» и «зачем».

**`db.exhibitionteams`** — 15 полей строки 22:
- названия;
- UTA/UTA;
- artid 104, spotlight 48, tunnel 38, audioid 32;
- цвета;
- соперник «Колорадо» (rivalteam 8).

**`db.exhibitionarena`** — строка 22: название, город, 14 111, 99 %, остальное — как у 181 «EA SPORTS Arena». Здесь
же другой вариант.

**`db.stockteamcolorstable`** — строки 76–78: #6CACE4, #010101, #FFFFFF.

**`db.stockteamjerseys`**:
- 8 строк teamid 22 заменить двумя (1_104_0 дом, 1_104_1 выезд);
- `helmetlogo 1`, `helmetnumbers 1`, `hastie 0`;
- `optional_third` — строка концепта, вариант 2.

**`db.equipment`** — 26 строк экипировки (team 23) перекрасить по карте:
- красные Coyotes → чёрный / #0F0F0F;
- акценты и ретро-синий → Mountain Blue;
- белые шлемы и белое не трогать;
- 3 строки вратарей — по той же карте, по желанию.

**`ahl`** — строка 55 → Tucson Roadrunners:
- поля, audioid 57;
- арена 52: Tucson Arena, Tucson, AZ, 6 521, нейтральный звук 255;
- комплекты 1_105_0/1;
- перекраска экипировки;
- локализация `*_TUC`;
- заметка о дивизионе.

**`localization`**:
- `put` — 5 ключей `*_22`;
- `add` — 9 ключей `*_UTA` (NHLTeamName, NHLCityName, Teamline1/2, ABBR3, X_XLA_TEAM, NICKLINE2, TXT_NICKNAME, ALT);
- ключи `*_PHX`/`*_ARZ` — список «как есть». Они нужны только старым франшизам.

**`cache_files`** — 66 файлов `out/` и 6 `out-third/` с размерами и md5. EA-файлы не заменяются: все номера новые.

**`franchise`, `other_agents`, `open_questions`** — для координатора.

Применять при закрытой игре:
1. Базу собрать через nhl32 или build-all (это зона legacy-data).
2. Локализацию — через `tools/locdb.py put`.
3. Арт — установщиком legacy-data из `game/work/utah/out`.
4. После новой базы — `draft_roster.db` = копия `nhlng.db`.

Начатые франшизы хранят свою копию команд, там Аризона так и останется Аризоной. Юта будет в новых франшизах.

## 8. Сборка

```bash
bash tools/utah/build.sh                  # всё: logos ui kits tucson verify sheets spec (~12 мин)
bash tools/utah/build.sh kits verify      # только части
UTAH_WORK=game/work/utah/dry bash tools/utah/build.sh logos kits   # сухой прогон в другую папку
```

| Инструмент | Назначение |
|---|---|
| `center_ice.py` | центр льда с названием арены по дуге |
| `kitdesign.py` | форма по описанию |
| `fontatlas.py` + `blockfont.py` | атлас номеров и свой шрифт |
| `font_layout.py` | раскладка атласа EA → `src/font_layout_ea.json` |
| `helmet.py` | наклейка на шлем |
| `ui_extra.py` | pb, значок, цифры меню, картинка панели |
| `rasterlogo.py` | знак из растра NHL.com → SVG-обёртка |
| `sheets.py` | листы |
| `make_spec.py` | спецификация |

Спеки лежат в `tools/utah/src/*.json`. В git идут только тексты — пути ведут в `game/work/utah/src`, где SVG и PNG.

Окружение:
- Python со стандартной библиотекой — для teamart, kitpaint, czkit, helmet, make_spec;
- venv `game/work/utah/venv` (numpy, scipy, Pillow) — для kitdesign, ui_extra, sheets, fontatlas;
- Chrome или Edge без окна.

Кеш развёртки и чистых карт кроя лежит в `game/work/utah/cache`.

Попутно 20:32 `czkit.clean_jersey_maps(4)` (через `kitdesign.clean_maps`) записал в кеш legacy-data
`game/work/legacy-data/art/czwork/clean/` два файла и добавил один:
- перезаписаны `4_…_nm.png` и `4_…_sm.png`: те же входы, тот же размер, детерминированный расчёт;
- добавлен недостававший `4_…_cal.json`.

Теперь `kitdesign` кеширует только в своей папке.

## 9. Открытые вопросы к пользователю

1. Третья форма: Hometown Remix Юты покажут в ноябре. Ставить ли концепт из `out-third/` до показа?
2. Реклама: добавлять ли нашивки SME Steel и 1Password и наклейку Filevine на шлем?
3. Арена: нейтральная «EA SPORTS Arena» (по умолчанию) или модель Аризоны с её 3D-«койотами»?
4. Звук: 32 (без названия, как у SEA) или оставить 22 («Coyotes»)?
5. Тусон: переносить ли его в Pacific в варианте `--ahl32` (нужна правка дерева АХЛ у nhl-legacy-port)?
6. Логотип Тусона: «Dusty» (как у АХЛ на 2026/27) или «Качина» (2025/26)?
7. Шрифт: квадратный «как Mammoth Sans» устраивает? Цифры — на листе `ui_helmet_font.png`.

В игре ничего не проверялось: игру тестирует nhl-legacy-port под `game.lock`, и ставить нужно вместе с базой.
