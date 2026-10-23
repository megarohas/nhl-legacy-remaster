# История наград и Кубка Стэнли из NHL 27 (`tools/legacy_data/awards27.py`, этап `awards`)

23.10.2026. Просьба пользователя: на экранах трофеев NHL Legacy (Previous Winners, награды сезона) — настоящая история
до сезона 2025/26 (у мода сезон 2026/27). У EA в базе Legacy было только пять сезонов, 2010/11…2014/15. **В игре ещё не
проверено** — см. «Проверка в игре».

## Коротко

| | |
|---|---|
| Таблица | `stockawardstable` в `game/work/legacy-data/out/db/nhlng.db` и `out-ahl32/db/nhlng.db` (схема `nhlng-meta.xml` рядом) |
| Источник | `stockawardstable` базы NHL 27 (PS5), та же схема; правки — [`tools/legacy_data/awards_fix.json`](../tools/legacy_data/awards_fix.json) |
| Итог (23.10) | 432 → 1 744 строки: НХЛ 1994/95…2025/26 (31 сезон, 2004/05 — локаут), 578 строк; АХЛ 367 (Calder Cup с 1999/2000, все награды с 2008/09); OHL 339, QMJHL 264, WHL 196 (с 2008/09) |
| Сейвы | не нужны: таблицы нет ни в сейве ROSTER, ни в сейве франшизы — видно сразу после установки базы, и в старых франшизах |

```bash
python tools/legacy_data/awards27.py                     # проба: что будет записано (out и out-ahl32), отчёт
python tools/legacy_data/awards27.py --write             # запись; копия базы и схемы — game/work/legacy-data/awards27/backup/
python tools/legacy_data/awards27.py --show 2025         # победители 2025/26 так, как их увидит игра (клуб, game_id)
python tools/legacy_data/awards27.py --awards            # номера наград (awardid)
python tools/legacy_data/awards27.py --from 2005 --leagues nhl --write   # только НХЛ с 2005/06, прочее в таблице — как было
python tools/legacy_data/awards27.py --no-fix            # строки NHL 27 как есть, без awards_fix.json
bash tools/legacy_data/build-all.sh awards               # то же этапом сборки (после contracts, до nhl24)
python tools/eaimport.py awards                          # то же из точки входа импорта (docs/import-from-ea.md)
```

В игру (при закрытой игре; база накладки `out-nhl24` собирается из `out/db`, поэтому её — заново):

```bash
python tools/legacy_data/awards27.py --write
python tools/eaimport.py overlay                         # = NHL24_PACK=game/work/nhl24/out/pack-edge bash tools/legacy_data/build-all.sh nhl24
bash tools/legacy_data/install-legacy-data.sh --ahl32 --nhl24 db     # или kitport install
```

Повтор с теми же параметрами ничего не меняет («база уже такая»). Отчёт — `game/work/legacy-data/awards27/<набор>.json`:
сезоны по лигам, правки, строки без клуба, как найдены клубы и игроки.

## Как игра читает награды (разбор кода Legacy)

- **82BB01C8** — победитель награды A в сезоне Y (Y — первый год сезона). Если Y < 2015 (порт сдвигает 2015 на
  `season_year`, хуки `NhlLegacyYearCmpS2015` на 82BB0200/82BB0230, у нас 2026) — **82BADD90**: запрос к
  `stockawardstable` «`year` = Y − 1899 и `awardid` = A», из первой строки — `lastname`, `firstname`, `team`. Иначе —
  `leagueawardstable` франшизы (`year` — номер сезона франшизы, 0 — первый). Вычитание 1899 хуками не сдвигается: год
  в таблице — абсолютный (126 — 2025/26).
- **82BAE238** — все победители (Jennings на двоих, ничьи Rocket Richard): те же условия, по порядку `index`, ещё
  `playerartid`, `jerseynumber`, `playerid` (через 82B1D840 — ссылка на игрока). Колонки — по порядку полей схемы
  `nhlng-meta.xml` (index 0 … team 9), биты — по заголовку таблицы в базе.
- **829C9280** (вызов через таблицу методов) — строка для экрана: если `firstname` и `lastname` пусты, подпись берётся
  из клуба `team`; для сезонов до `season_year` клуб ищется среди клубов базы (флаг на 829C92F8, тоже сдвинут хуком).
- В слоте рядом (829C9278) — константа 1994 (порт сдвигает на +11, `year_hooks.py` считает её годом рождения
  18-летних). Если это нижняя граница истории на экране, то без сдвига экран начнётся с 1994/95 — поэтому в правках есть
  1994/95 и 1995/96. Не проверено.
- `stockawardstable` без групп сохранения (`savegroups` пусто): ни в сейв ROSTER, ни в сейв франшизы она не попадает
  (сверено на сейвах `userdata-natcup`: в сейве франшизы 49 таблиц, из наград — только `leagueawardstable`, 36 строк за
  первый сезон). Франшиза её не копирует.

## Откуда и что пишется

- **NHL 27** (`roster.nhl27.open_db`, `NHL27_DB=путь`): `stockawardstable`, 1 707 строк, поля Legacy + `teamartid`.
  Номера наград, лиг (`league`: 0 НХЛ, 6 АХЛ, 12 WHL, 13 OHL, 14 QMJHL — не `exhibitionteams.league`!) и год — как у
  Legacy: на 2010/11…2014/15, где есть обе, победители совпадают (кроме опечаток Legacy: Corey Lock → Locke, Mathew →
  Matt Dumba) — поэтому эти сезоны тоже из NHL 27. Награды НХЛ: 0 Stanley Cup, 1 Presidents' Trophy, 8 Campbell Bowl
  (Запад), 9 Prince of Wales (Восток), 34 Art Ross, 35 Hart, 36 Norris, 37 Lady Byng, 38 Calder, 39 Conn Smythe, 40
  Vezina, 41 Jennings, 42 Masterton, 43 Jack Adams, 44 Selke, 45 Ted Lindsay, 46 Rocket Richard, 88 King Clancy; АХЛ — 10
  Calder Cup, 11–19 командные, 47–56 личные; QMJHL 20–23 / 57–67, OHL 24–31 / 68–78, WHL 32–33 / 79–87.
- **Клуб** (`team` — номер строки `exhibitionteams` Legacy с нуля, 8 бит):
  - НХЛ — `roster.nhl27.NHL_SLOT` (у NHL 27 VGK 30 и SEA 31, у нас наоборот); клуб -1 у NHL 27 — Phoenix/Arizona (для EA
    Utah — новый клуб) → 22, нынешний Utah (`nhl_no_team`);
  - АХЛ и CHL — клуб NHL 27 по полному названию в своей лиге, затем аббревиатура + город, затем город. **Аббревиатуры у
    EA между играми разные**: CHA у NHL 27 — Chicago Wolves, у Legacy — Charlotte, поэтому аббревиатура одна не годится;
  - клуба нет (-1 или переехал) — `team_alias` (слот того же клуба после переезда: Houston Aeros → Iowa Wild, San
    Antonio Rampage → Henderson, Bridgeport → Hamilton Hammers, Acadie-Bathurst → Newfoundland Regiment…), в последнюю
    очередь — строка, где клуб был в базе EA 2015 года (`game/other/legacy/.../nhlng.db`; слот мог уйти другому клубу:
    у San Antonio теперь Colorado Eagles — поэтому только после `team_alias`);
  - в `out` (без «АХЛ на 32») CV и HSK нет: их строки (8) — под клубом НХЛ, чей это фарм-клуб (SEA, VGK), в отчёте;
  - у командных наград подписи — `firstname`/`lastname` из NHL 27 (город и имя клуба); у NHL 27 это нынешнее имя клуба
    (Belleville Senators за Calder Cup 2010/11) — прежние имена победителей Calder Cup и Campbell Bowl 2002/03 — правками.
- **Игрок** (`playerid`, `playerartid` — `game_id` и `artid` нашей базы): по имени и дате рождения из биографии NHL 27
  (у всех 756 строк, где номер есть в биографии, имя совпадает), иначе только по имени, если такой один и возраст в том
  сезоне правдоподобен (`AGES`: НХЛ 18–45, АХЛ 17–42, CHL 15–21 — иначе тёзка: Tyler Johnson 1990 г. р. не вратарь OHL
  2017/18). Не нашли (ушедшие до 2015, их строк в базе нет) — -1, как у EA в 2010/11…2012/13. Итог `out-ahl32`: по дате
  564, по имени 68, нет 541, командные и тренеры 571.
- **Строки.** Таблица собирается заново: строки NHL 27 и правок за сезоны `--from…--to` (по умолчанию все, до сезона
  перед `tools/season.py YEAR` — с 2026/27 игра берёт франшизу), строки базы вне этих сезонов и группы (сезон, лига,
  награда), которых нет в источнике, остаются (`--prune` — убрать всё вне диапазона). Порядок — сезон, лига (НХЛ, АХЛ,
  OHL, QMJHL, WHL), порядок NHL 27; `index` — номер строки. Подписи длиннее 24 байт UTF-8 обрезаются.
- **Ширина `index`.** У Legacy 9 бит (до 512 строк), у NHL 27 — 11. При 1 744 строках поле расширяется до 11 бит
  (`tdb.widen`: поле — в конец записи, запись 60 → 64 байта, последний бит записи свободен под флаг движка) и в
  `nhlng-meta.xml` рядом (`depth="11" rangehigh="2047"`), как делает `nhl32.py` с полями клубов. База +86 КБ (3,05 →
  3,14 МБ). `draft_roster.db` наград не содержит — не пересобирается.

## Правки (`awards_fix.json`)

Только общеизвестные факты; разбор 23.10 — все личные награды НХЛ 1996/97…2024/25 сверены по сезонам (2025/26 у EA
сверить не с чем).

| Что | Почему |
|---|---|
| `swap_teams` STL ↔ SJS до 2003/04 (12 строк) | у NHL 27 в старых строках St. Louis и San Jose перепутаны (порядок по алфавиту): Pronger, Turek, Quenneville, Demitra 1999/2000 — «San Jose», Nabokov 2000/01 — «St. Louis», Presidents' Trophy 1999/2000 — «San Jose Sharks» вместо St. Louis Blues |
| Jennings 1996/97 — Brodeur и Dunham; 1998/99 — Belfour и Turek | у NHL 27 один вратарь дважды |
| King Clancy 2007/08 — Lecavalier; 2017/18 — Daniel и Henrik Sedin | у NHL 27 нет / один из двух |
| Calder Cup 2000/01 — Saint John Flames | у NHL 27 «Anaheim Ducks» |
| Прежние имена: Campbell Bowl 2002/03 — Mighty Ducks of Anaheim; Calder Cup 2002/03 Houston Aeros, 2004/05 Philadelphia Phantoms, 2006/07 Hamilton Bulldogs (клуб — Laval Rocket, у NHL 27 — OHL Brantford), 2010/11 Binghamton Senators | у NHL 27 нынешнее имя клуба или чужой клуб |
| `row_teams` — 14 строк АХЛ/CHL с клубом -1 | клуб того сезона (Albany River Rats, San Antonio Rampage, Belleville Bulls, Acadie-Bathurst…) → его слот через `team_alias`; у Andreoff 2022/23 и Simmonds 2013/14 — методом исключения |
| 1994/95 и 1995/96 НХЛ (34 строки) | в NHL 27 история с 1996/97; см. «Как игра читает», про 1994 |

Формат: `season` — первый год сезона, `league` — nhl/ahl/ohl/qmjhl/whl, `award` — awardid, `team` — аббревиатура НХЛ
(`roster.common.TEAM_SLOT`, прежние PHX/ATL/HFD/QUE — `TEAM_ALIAS`) или полное название клуба базы; в `team_alias`
`null` — слота нет, строка не пишется (Penticton Vees — 23-й клуб WHL).

## Проверка

- `awards27.py --show <сезон>` — сезон после сопоставления: награда, победитель, аббревиатура клуба Legacy, game_id.
- `python tools/tdb.py dump game/work/legacy-data/out-ahl32/db/nhlng.db stockawardstable --where year=126 --meta …` —
  строки как в базе; `tdb.py verify` — CRC; `legacy_data/fix_flagbit.py` на базе ничего не меняет.

### Проверка в игре (не делалась, 23.10)

1. Be a GM / сезон: экран наград → Previous Winners (ключ локализации `PreviousWinners`) у Кубка Стэнли, Hart, Jennings
   (два вратаря), Rocket Richard 2003/04 (трое). Должны быть сезоны до 2025/26 (Carolina, Kucherov…).
2. Сколько лет назад уходит список: с 2005/06 (если 1994 из 829C9278 — нижняя граница, сдвинутая портом на +11), с
   1994/95 или до первого пустого сезона — 2004/05 (локаут, наград НХЛ нет). Если список обрывается на пустом сезоне,
   нужна заглушка «не вручался» за 2004/05 (строки с пустым клубом нельзя: `team` 0…255).
3. Командные награды АХЛ и CHL — логотип клуба и подпись; CV/HSK — только с «АХЛ на 32».
4. Франшиза, начатая до установки: история та же, награды франшизы (2026/27 и дальше) — свои.

## Грабли

- Писать при закрытой игре не нужно (пишется `out/`), а ставить — только при закрытой (`install-legacy-data.sh`).
- После `--write` накладка `out-nhl24(-ahl32)` устарела: её база — копия `out/db` с формами. Без `eaimport.py overlay`
  установка `--nhl24` поставит прежнюю базу без истории.
- Этап — после `players`/`contracts`: `add_players.py` отдаёт строки игроков без клуба новым игрокам, и `game_id` ушедшего
  победителя мог бы указывать на другого человека. Повторный прогон после них пересчитывает ссылки.
- Названия АХЛ/CHL у NHL 27 не сверялись поштучно (кроме Calder Cup), личные награды АХЛ/CHL — как у EA.
