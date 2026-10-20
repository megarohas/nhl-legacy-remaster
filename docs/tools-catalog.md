# Инструменты по задачам: что запускать, насколько готово, что доделать

20.10.2026. Указатель «по задаче»: что запускать, чтобы обновить составы, добавить клуб, перенести форму и т. п.
Пофайловая карта — [../tools/README.md](../tools/README.md), правило «инструменты, а не разовые скрипты» —
[../CLAUDE.md](../CLAUDE.md).

Зрелость:
- **И** — инструмент (CLI с параметрами и справкой, описан);
- **П** — полуготово (работает, но зашиты сезон, клуб или пути, нет справки или описания);
- **—** — инструмента нет.

Все команды запускаются из корня репозитория: `python tools/…`, пакеты — `cd tools && python -m …`.

## 1. По задачам

| Задача | Чем | Док | Зрелость |
|---|---|---|---|
| **Составы НХЛ** (клубы, звенья, номера, рейтинги, свободные агенты) | `python tools/roster all --game legacy …` (этап `roster`), `registry_from_db.py`, `nhl_attrs.py`, `retire_veterans.py` | [roster-pipeline.md](roster-pipeline.md), [roster-expansion.md](roster-expansion.md), [legacy-data.md](legacy-data.md) | П — сезон константой (`roster/common.py` `SEASON`, `SEASON_YEAR`) |
| **Составы АХЛ** | `python -m roster.ahl_ht`, `roster.ahl2026`, этап `ahl` (`ahl2026_slots.py`) | legacy-data.md | П — `SEASON_ID = 94`, имена под 2026/27 |
| **Составы других лиг** | `roster/league.py` (только Liiga) | roster-expansion.md | — CHL, сборные, SHL, DEL, NL, Extraliga, КХЛ |
| **Фото игроков** | `photos.py` (НХЛ), `python tools/roster photos` (не из НХЛ), `roster.ht_photos` (АХЛ), `photos24.py` (из NHL 24), `playerhead.py` (формат) | [player-photos.md](player-photos.md), [player-photos-nhl24.md](player-photos-nhl24.md) | И; `photos24` — П (привязан к NHL 24) |
| **Логотипы** НХЛ и АХЛ | `logos/fetch_nhl.py`, `logos/build.py`, этап `logos`; `teamart.py` (арт ⇄ PNG) | [logos-2026.md](logos-2026.md), [logos-arenas.md](logos-arenas.md) | И (лиги вне НХЛ/АХЛ — нет) |
| **Новый игрок** | — (рядом: `roster/write.py` доноры, `ratings`, `ovrformula`, `playerhead compose`, `heads24`) | — | — |
| **Новые клубы и лиги** (32 клуба, АХЛ на 32, Юта) | `nhl32.py` (этап `base`), `newteams_art.py`, `tools/utah/*` + этап `utah` | [ahl32.md](ahl32.md), [utah.md](utah.md), legacy-data.md | П — по случаю (SEA/VGK, UTA), общего «клуб по профилю» нет |
| **Формы** | `python -m kitport …` (подход C, MIN), `fb.kit_batch`/`fb.pilot` (подход A, 32 клуба), `fb.jersey_mesh` (B), `legacy_data/nhl24.py alloc/order/build/save`, `kitpaint.py`, `czkit.py`, `fepose.py` | [kitport.md](kitport.md), [nhl24-uniforms.md](nhl24-uniforms.md), [uniforms.md](uniforms.md) | И для MIN; другие клубы подходом C — П (профиль клуба не вынесен) |
| **Головы** | `heads24.py` (типовые по фото), `scans24.py` (сканы NHL 24) | [heads-nhl24.md](heads-nhl24.md) | П — под NHL 24; для NHL 27 — чек-лист |
| **Экипировка** | `python -m roster.equipment …` (по фото), `tape_players.py`, `goalie_gear.py`, `user_equipment.py` (правки из сейва), этап `models` | [player-equipment.md](player-equipment.md), [player-models.md](player-models.md) | И; `useredits` — П (вход делает разовый скрипт вне git) |
| **Арены и лёд** | `teamart.py build --only center,puck,banner,spot`, `fb.ice`, `utah/center_ice.py`, `newteams_art.py` | logos-arenas.md, utah.md | П — 3D-арен нет |
| **Меню и интерфейс** | `fefont.py`, `febg.py`, `feapt.py`/`aptc.py`, `menu12_legacy.py`, `menuitems_legacy.py`, `draft32_legacy.py`, `locdb.py`, `music.py` | [fe-menu-legacy.md](fe-menu-legacy.md), [fe-fonts.md](fe-fonts.md), [music.md](music.md) | И; `menu12_legacy` — П (вход — сборка NHL 13) |
| **Год и даты** | cvar `season_year` (лаунчер), `year_hooks.py`, `year2026_legacy.py`, `tdb.py setstate` | [legacy-port.md](legacy-port.md), fe-menu-legacy.md §12 | П — «2026» зашит, `--year` нет |
| **Контракты, потолок, драфт** | этап `contracts` (`contracts.py`), `roster write --payroll-max`, `payroll_report.py`, cvar `nhl_salary_*`, `draft_roster.py`, `draft32_legacy.py`, cvar `nhl_draftclass_age` | legacy-data.md, [draft-pool.md](draft-pool.md) | П — импорт контрактов держится на разборщике вне git |
| **Настройки лиг** | `legacy_settings.py` (только слайдеры), `nhl32.py` (дивизионы, 84 игры — константами), cvar лаунчера | legacy-port.md | — |
| **Правила** | `legacy_settings.py` читает правила (ID 9…27), записи нет; cvar `nhl_settings_from_profile` | legacy-port.md | — |
| **Сейвы** | `tdb.py verify/live/states/setstate/set`, команда `save` у каждого этапа | [save-editing.md](save-editing.md) | И по отдельности; общего «всё в ROSTER» нет |
| **Установка модов** | `build-all.sh [ЭТАП…] [--ahl32]`, `install-legacy-data.sh`, `uninstall-legacy-data.sh`; для форм — `kitport diff/install/rollback` | legacy-data.md, kitport.md | И, но `status`/`verify` у общего установщика нет |
| **Порт (exe)** | `xmatch.py`, `team_hooks.py`, `year_hooks.py`, `find_indirect_targets.py`, `ppcdis.py`, `stackpeek.py`, `gameshot.ps1` | legacy-port.md, [sdk-build.md](sdk-build.md) | И; `gameshot` и `stackpeek` — П (пути и exe NHL 13) |
| **Новый источник — дамп Frostbite** (NHL 27 PS5) | `python -m fb.source`, `fb.probe`, `fb.scan/catalog/toc/extract` | [frostbite-sources.md](frostbite-sources.md) | И (чтение); перенос форм, голов, фото пишет пути NHL 24 — П |

## 2. Что мешает собрать набор из публичного репозитория

1. ~~Этап `useredits` требует разовый `equip_from_save.py` вне git~~ — с 20.10 это `user_equipment.py extract`.
2. Этапу `contracts` нужны `game/work/contracts/screens/*.json` от разборщика вне git (решение пользователя).
3. ~~`kitpaint.py`, `teamart.py` (а через них `czkit.py`, `fepose.py`) импортируют `unpack_big` из `ref/`~~ — с 20.10
   чтение архивов через `tools/big.py` (`members`, `read_member`). Схема `tdb.py` без `--meta` — Legacy из
   распакованной игры; `fefont.py`, `roster/common.py` берут `ref/` только для замороженного NHL 13.
4. Установщик берёт `cache:` из личного `game/work/status/legacy-port.md`. У других работает только переменная
   `CACHE`.
5. Сезон зашит: `roster/common.py`, `roster/ahl_ht.py` (`SEASON_ID`), `build-all.sh` (`teams-94.json`),
   `year2026_legacy.py`.

## 3. План: довести до инструментов

Объём: S — до полудня, M — 1–2 дня, L — неделя и больше.

| # | Что | Основа | Объём |
|---|---|---|---|
| 1 | ✔ 20.10: `user_equipment.py extract` вместо разового `equip_from_save.py` (вывод сверен: 191 правка, снимок совпал) | — | S |
| 2 | ✔ 20.10: без `ref/…/unpack_big` в `kitpaint`, `teamart` (→ `czkit`, `fepose`); схема `tdb.py` по умолчанию — Legacy | `tools/big.py` | S–M |
| 3 | Одна настройка сезона (`--season` / профиль) для составов, АХЛ, строк года | `roster/common.py`, `roster/ahl_ht.py`, `year2026_legacy.py`, `build-all.sh` | M |
| 4 | Установщик: `status`, `verify`, `diff`, проверка на копии userdata; `CACHE` явно или из `nhllegacy.toml` | разовые `tmp/check_install.py`, `cmp_cache*.py`, `make_ud.py`, `cmp_dry.py`; `kitport.core` | M |
| 5 | ✔ 20.10: `tdb.py tables`, `dump --where/--fields/--csv`, `diff A B` (по ключу, значения с rangelow); осталось «всё о клубе» | десяток разовых выгрузок (`tmp/dbdiff.py`, `*_dump.py`) | S–M |
| 6 | Импорт контрактов из открытого формата (`contracts.py import`), адаптер сайта — локально | `game/work/contracts/parse_pp.py`, `ingest.py` | M (нужно решение) |
| 7 | Правила: `legacy_settings.py set-rule/copy-rules`, таблица ID 9…27 | `legacy_settings.py`, `nhllegacy_settings.cpp` | S–M |
| 8 | Новый игрок: `python tools/roster add-player SPEC.json` (донор, био, атрибуты под OVR, номер, звено, портрет, голова, сейв) | `roster/write.py`, `ratings`, `ovrformula`, `photos.py`, `playerhead`, `heads24` | M–L |
| 9 | Клуб по профилю: `club.py replace/add PROFILE.json` (база, локализация, арт, арена); общие модули из `tools/utah` | `utah/make_spec.py`, `legacy_data/utah.py`, `nhl32.NEW_TEAMS`, `newteams_art.py` | L |
| 10 | Настройки лиг в файле (дивизионы, число игр для `nhl32`); `tools/brk.py show/set` (rookiegen, worth2, salarydata) | `nhl32.py`, `nhl-legacy-port/analysis/ovr/brk.py` | M–L |
| 11 | kitport: профиль клуба вместо таблиц MIN; `kitport check` (листы слота, вратаря, LOD, гетр, превью); выбор kitpicker → реестр | `fb/edge_kit.py`, `game/work/nhl24/edgekit/*_check.py` | M–L |
| 12 | Источник Frostbite через `fb.source` и у переноса: `photos24`, `heads24`, `scans24`, `kit_batch`, `pilot`, `nhl24.py`, проверки `build-all.sh` | `fb/source.py` | M |
| 13 | Составы CHL через HockeyTech, потом сборные (пул драфта сейчас из игроков 2012 года) | `roster/ahl_ht.py`, `roster/league.py` | L |
| 14 | Пульт и прогон в игре: `gameshot.ps1 -Do pad/burst/boot`, без путей `S:\`; `stackpeek --game legacy` | `game/work/natcup-test/pad.sh`, `loop.sh`, `d32pad.ps1`, `stackpeek_legacy.py` | S–M |
| 15 | `tools/gencode.py` (функция, вызывающие, дерево, строки, хеши полей); «перенести всё в ROSTER»; читалка франшизы (ветка `nations-cup`) | `game/work/natcup-re/*`, `contracts/research/*`, `nhl-legacy-port/analysis/*` | M |

Мелкое (S): убрать `legacy_data/ahl_age_explore.py`, сломанные `game/work/legacy-fe/*.sh`, бэкапы
`edge_kit_v40…v54`.

## 4. Разовые скрипты (game/work)

- **Всего** около 500 скриптов. Около 25 стоит сделать инструментами или командами существующих — это пункты плана
  выше.
- **Остальное — история:**
  - разведка, уже ставшая инструментами (`heads-research` → `scans24`, `photos-nhl24/scripts` → `photos24`/`heads24`,
    `utah/scripts` → `tools/utah`, `nhl24/hybrid`, `adidas3d` → `edge_kit`/`jersey_mesh`);
  - патчеры кода и документов;
  - восстановление после 09.10;
  - установщики NHL 13.
- **Ещё 36 скриптов разведки кода** — в `nhl-legacy-port/analysis/` (вне git): `ovr/brk.py`, `gdis.py`, `callers.py`,
  `refs.py`, `schedule/scripts/*`.

## 5. Документация: что поправить

- **Нет описания:** `fb/hem.py`, `fb/helmet.py`, `genfn.py`, `logos/svgpaths.py`, `logos/svgdiff.py`,
  `payroll_report.py` (только в замороженном franchise-seasons.md), `save_sync_ratings.py`, `kitpicker`; модули
  `tools/utah/*` (по сути общие).
- **Ссылки на отсутствующие скрипты:**
  - `game/work/legacy-fe/install-legacy-fe.sh` — `fe-menu-legacy.md`, `uniforms.md`;
  - `fe/check_font.py` — `fe-fonts.md`;
  - `logos/scripts/verify_out.py` — теперь `tools/legacy_data/art/scripts/verify_out.py`, `logos-arenas.md`;
  - `logos/out.sh` — `logos-arenas.md`;
  - `game/work/draftpool/` — `draft-pool.md`.
- **Процедура держится на разовом скрипте:**
  - `legacy-data.md`: `cmp_dry.py`, `check_ahl2026.py`, `check_ratings_20261011.py`, `user_install_full.py`,
    `parse_pp.py`;
  - `player-equipment.md`: `equip_report_ea_vs_ours.py`;
  - `heads-nhl24.md`: `heads_lib.py`;
  - `fe-menu-legacy.md`: `ddiff.py`.
- **Устарело:**
  - `legacy-data.md`: порядок этапа `contracts` (он идёт до `goaliegear`);
  - шапка `roster-pipeline.md` («этап 1 — только клубы НХЛ»);
  - первые строки docstring «NHL 13» у инструментов, работающих в основном с `--game legacy`: `roster/cli.py`,
    `kitpaint.py`, `teamart.py`, `playerhead.py`, `rw4mesh.py`, `sticktape.py`, `fefont.py`, `febg.py`;
  - `CACHE` по умолчанию из личного файла.
- **Структура.** `legacy-data.md` (≈1350 строк) — хронологический журнал, а не справка. Указателя «по задаче» не было
  — этот документ.
