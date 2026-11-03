# Стратегии клубов НХЛ (`tools/legacy_data/team_tactics.py`)

Как играет каждый клуб, когда им управляет ИИ: форчек, средняя зона, давление, оборона, большинство, меньшинство,
стиль и ползунки звеньев. У EA в базе Legacy эти значения остались от 2014–2015 годов и почти одинаковы у всех
(«ловушка/форчек» у всех 32 клубов — 3, «разыгрывать/бросать» у всех звеньев — 5). Инструмент ставит их по спеке
[`team_tactics.json`](../tools/legacy_data/team_tactics.json): тренерские системы клубов 2025/26–2026/27 из открытых
источников, косвенные признаки из API НХЛ, где не нашлось — значения NHL 27. С 03.11.2026.

```bash
python tools/legacy_data/team_tactics.py show --html game/work/tactics/tactics.html --png game/work/tactics/tactics.png
python tools/legacy_data/team_tactics.py db  <nhlng.db> [--dry-run]          # база
python tools/legacy_data/team_tactics.py save "<ROSTER …/ROSTER …>" [--write] # сейв состава: без --write — подсчёт
python tools/legacy_data/team_tactics.py check <база или сейв>                # всё ли как в спеке (код 1 — нет)
… [--clubs FLA,CAR] [--spec ФАЙЛ] [--nhl27 game/work/nhl27/db/nhl_game.db]
```

`show` печатает «сейчас → станет» и рисует таблицу (`--png` — нужен Pillow, есть в `game/work/nhl24/venv`). Повторный
запуск ничего не меняет. Пишется только `exhibitionteamstrategies`, строки 0…31, число строк то же — сейв не
«damaged». Копия сейва до правки — `game/work/legacy-data/backup-saves/<сейв>-tactics-<время>/`.

## Где лежат стратегии и что из них видно в игре

Таблица `exhibitionteamstrategies` (61 поле, строка = клуб `exhibitionteams`), она же в сейве ROSTER (savegroups
`rosters`). Play Now и новая франшиза берут её из сейва состава, поэтому ставить надо и в базу, и в новейший ROSTER.
Начатая франшиза держит свою копию (`leagueteamstrategies` в DYNASTY) — её инструмент не трогает. `buildaistrategies` —
шаблоны «Build Your AI», тоже не трогаются.

Что значат поля, найдено в exe (`game/work/heads-research/xex/default.bin`, 03.11.2026):
- загрузчик стратегий `8318F150` читает все поля по именам (строки `82172100…82172444`);
- названия вариантов меню — таблица `83A2EDE0` (ключи локализации по группам), подсказки к вариантам — `82090590…82090790`;
- ползунки — записи по 32 байта `8208FF40…820904F0`: `{1, −1, параметр ИИ, 0, левая подпись, правая, описание, максимум}`;
  параметр −1 — ползунок не показывается.

Тот же порядок вариантов — в меню NHL 27 (JSON стратегий в дампе, `ChoiceValue` по возрастанию), сверено.

| Настройка (меню «Strategies») | Поле | Значения |
|---|---|---|
| Forecheck | `oz_forecheck` | 0 1-2-2 Passive, 1 2-3, 2 Weak Side Lock, 3 1-2-2 Aggressive |
| Neutral Zone | `nz_forecheck` | 0 1-3-1, 1 1-4, 2 1-2-2 Red, 3 1-2-2 Blue |
| Trap/Forecheck (ползунок 0…6) | `trap_forecheck_bias` | 0 — ждать в средней зоне, 6 — всегда форчек (параметр ИИ 1) |
| Offensive Pressure | `opressure` | 0 Defend Lead, 1 Conservative, 2 Standard, 3 Aggressive, 4 Full Attack |
| Defensive Pressure | `dpressure` | 0 Protect Net, 1 Contain Puck, 2 Normal, 3 Puck Side Attack, 4 High Pressure |
| Defensive Strategy | `defense` | 0 Collapsing, 1 Staggered, 2 Tight Point |
| Powerplay | `pp` | 0 Shooting, 1 Overload, 2 Umbrella |
| Penalty Kill | `pk` | 0 Passive Box, 1 Large Box, 2 Diamond |
| стиль звена 1…4 | `offense1…4` | 0 Overload, 1 Crash the Net, 2 Behind the Net |
| звено: Carry/Dump (0…10) | `forwardN_bias1` | параметр ИИ 0 |
| звено: Cycle/Shoot | `forwardN_bias3` | параметр 2 |
| звено: Efficiency/Energy | `forwardN_bias4` | параметр 3 |
| звено: Don't Block/Block | `forwardN_bias5` | параметр 4 |
| пара защитников: Hold Line/Pinch | `defenseN_bias1` | параметр 5 |
| пара: Cycle/Shoot | `defenseN_bias2` | параметр 2 |
| PP Carry/Dump | `team_bias1` | параметр 0xB |

Скрыты в меню (параметр −1) и не трогаются: `forwardN_bias2` (NZ Trap/Forecheck звена — в Legacy его заменил общий
ползунок `trap_forecheck_bias`), `forwardN_bias6`, `defenseN_bias3…6`, `team_bias2…6`. Хранятся поля шире (5 бит), меню
показывает 0…10. Во время матча стратегию меняет ещё и сам ИИ по счёту — настройка «CPU Strategy Adjustment»; значения
клуба — это то, с чего он начинает.

Что из этого реально меняет игру ИИ, по коду не прослежено: проверено, что игра их загружает и показывает в меню (см.
«Проверка»). Влияние в матче — замысел EA, на глаз.

## NHL 27

База `game/work/nhl27/db/nhl_game.db`, та же таблица шире (184 поля: отдельно большинство/меньшинство по составам,
выходы из зоны, 3 на 3, `playbookid`). Что видно (03.11.2026):
- клубы различаются: у каждого свой `playbookid` (0…31) и свои значения;
- но ползунки и стиль у всех четырёх звеньев клуба одинаковые (по сути — значение клуба на все звенья), пары защитников тоже;
- форчек в NHL 27 бывает 4 и 5 (у Legacy только 0…3), большинство/меньшинство разложены по составам (`pp_1_strat`,
  `pk4_1_strat`) с другим набором вариантов — эти поля в Legacy не переносятся;
- сверка с ресёрчем там, где он есть: форчек совпал у 3 из 25 клубов, средняя зона 5/20, оборона 9/21, давление в
  обороне 7/21, в атаке 11/32 — на уровне случайного выбора. Значения EA в Legacy совпадают не лучше.

Поэтому NHL 27 — только запасной источник: «nhl27» в спеке берёт из неё средняя зона, оборона, давление в атаке и
обороне, ловушка/форчек (у этих полей смысл и порядок вариантов те же). Нет базы NHL 27 — поле остаётся как есть.

## Ресёрч и правила перевода

Ресёрч 03.11.2026 (только открытые страницы, без обхода платных, PuckPedia не качали): разборы систем тренеров,
предсезонные обзоры, статьи клубов и местной прессы, склонности тренера по прежним клубам (помечены «coach history»).
Выгрузка с цитатами и ссылками — `game/work/tactics/research/{east,west}.json` (не в git), в спеке — вывод, причина и
ссылки. Статистика — API НХЛ (`api.nhle.com/stats/rest/en/team/summary` и `/realtime`, 2025/26 + начало 2026/27,
средневзвешенно по матчам): броски за матч, силовые и блоки за 60 минут.

Как система переводится в настройки игры (сборщик черновика — `game/work/tactics/scripts/make_spec.py`, дальше правка руками):

| В источнике | В игре |
|---|---|
| 1-2-2 aggressive / passive | Forecheck 1-2-2 Aggressive / Passive; «умеренный 1-2-2» — Passive |
| 2-1-2 (два нападающих глубоко) | 2-3 («два ближних давят, третий страхует») |
| агрессивный форчек без названной схемы | вариант EA, если он агрессивный (2-3 или 1-2-2 Aggressive), иначе 1-2-2 Aggressive |
| 1-3-1 / 1-1-3 (1-4) / 1-2-2 у красной / у синей | Neutral Zone так же; 1-1-3 — «1-4» |
| персональная опека, давление везде | Defensive Strategy Tight Point + давление High Pressure (темп высокий) или Puck Side Attack |
| смешанная опека | Staggered + Normal |
| зонная, «защищать пятак» | Collapsing + Contain Puck (низкий темп — Protect Net; агрессивный box+1 — Puck Side Attack) |
| большинство 1-3-1 | Umbrella (один у синей, двое под бросок с ходу) |
| две точки у синей и броски с экранами | Shooting |
| меньшинство: пассивный бокс / давящий бокс / ромб, wedge+1 | Passive Box / Large Box / Diamond |
| темп высокий / средний / низкий | Offensive Pressure Aggressive / Standard / Conservative; Trap/Forecheck 4 / 3 / 1, ±1 за агрессивный или пассивный форчек |
| стиль атаки: из-за ворот, цикл / на пятак, броски / скорость, перегруз | стиль 1-го и 2-го звена: Behind the Net / Crash the Net / Overload (3-е и 4-е — как у EA) |
| занос / вброс | Carry/Dump звеньев: цель 3 (занос) … 7 (вброс) |
| защитники подключаются / держат синюю | Pinch пар: цель 7 (агрессивно), 6, 5 (умеренно), 3 (осторожно) |
| броски за матч | Cycle/Shoot звеньев: 5 + 1,5·z, +1 за стиль «бросать с пятака» |
| блоки за 60 мин | Block: сдвиг от EA на round(z), не больше ±2 |
| силовые за 60 мин и темп | Efficiency/Energy: сдвиг от EA на round(0,7·z) ±1 за темп, не больше ±2 |

Ползунок считается как цель для клуба (или сдвиг): все звенья сдвигаются на одну величину от значений EA в базе
773ef7e9, разница между звеньями, которую поставила EA (4-е звено чаще вбрасывает и блокирует), сохраняется. В спеку
пишется готовый итог по звеньям (`"lines": [1-е, 2-е, 3-е, 4-е]`, у пар — 3 числа), инструмент ставит его как есть,
поэтому повторный запуск ничего не меняет. Если ресёрч ничего не нашёл, поля в спеке нет или стоит «nhl27». В `why`
у каждого значения — откуда оно и насколько надёжно («точно», «вероятно», «слабый источник»).

Формат спеки (клуб — `abbrname` клуба в базе):

```json
"FLA": {"coach": "Paul Maurice",
        "team":    {"forecheck": {"value": "1-2-2 aggressive", "why": "…"}, "neutral_zone": {"value": "nhl27", "why": "…"}},
        "lines":   {"style": ["behind the net", "behind the net", null, null], "why": "…"},
        "sliders": {"carry_dump": {"lines": [5, 6, 7, 8], "why": "…"}},
        "sources": ["https://…"], "stats": {"shotsForPerGame": 30.1, "…": 0}}
```

Ключи `team`: forecheck, neutral_zone, trap_forecheck (0…6), opressure, dpressure, defense, pp, pk — значения
по-английски, как в меню (таблица выше, строчными). `sliders`: carry_dump, cycle_shoot, energy, block, pinch, d_shoot,
pp_carry_dump. `null` в `style` и отсутствующий ключ — не менять. Ошибки в спеке (нет варианта, число вне диапазона,
«nhl27» у поля с другим смыслом в NHL 27) инструмент называет до записи.

## Установка (при закрытой игре)

```bash
cp nhl-legacy-port/userdata/cache/guest/db/nhlng.db game/work/tactics/backup/nhlng-$(date +%Y%m%d-%H%M).db
python tools/legacy_data/team_tactics.py db nhl-legacy-port/userdata/cache/guest/db/nhlng.db
python tools/legacy_data/team_tactics.py save "<новейший ROSTER …/ROSTER …>" --write
python tools/legacy_data/team_tactics.py check "<тот же ROSTER>"
```

Откат: вернуть копию базы и `…/backup-saves/<сейв>-tactics-<время>/<сейв>.bak` на место файла сейва. После полной
пересборки базы (`build-all.sh`) — снова `db` и `save`: в этапы build-all инструмент не входит.

## Проверка

- `check` по базе и сейву — код 0;
- в игре (копия userdata, Play Now): пауза → Strategies у 2–3 клубов показывает значения спеки (названия вариантов
  совпадают с таблицей выше — это и проверка порядка вариантов).

## Грабли

- Игра пересохраняет ROSTER под новым именем (время UTC): ставить в самый свежий.
- Правки стратегий, сделанные пользователем в меню, лежат в том же сейве: `save` перепишет поля из спеки у клубов
  спеки. До записи `save` без `--write` покажет, что поменяется.
- Сборные, Матч звёзд, АХЛ и прочие лиги — не в спеке и не трогаются.
