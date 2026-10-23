# Экипировка игроков из NHL 27 (`tools/legacy_data/equipment27.py`, 23.10.2026)

Просьба пользователя 23.10.2026: всем игрокам базы взять из NHL 27 всё, что там есть об экипировке, — клюшку, коньки,
шлем, краги, шорты, визор, цвет и вид обмотки, заправку свитера и гетр, — и поставить в NHL Legacy: в базы сборки, в
сохранённый состав (ROSTER) и во франшизу (DYNASTY, Миннесота). Правки самого пользователя в редакторе игры можно
перезаписать.

Инструмент читает базу NHL 27 и таблицы моделей из дампа, сшивает игроков по имени и дате рождения и пишет поля
`exhibitionskaterequipment` / `exhibitiongoalieequipment` (франшиза — `leagueskaterequipment` / `leaguegoalieequipment`).
Модели клюшек и коньков ставятся в слоты каталога Legacy, куда перенесены текстуры NHL 27 ([sticks.md](sticks.md),
[skates.md](skates.md)); шлемы и краги — модели Legacy той же марки и линейки.

## Команды

```bash
python tools/legacy_data/equipment27.py                          # проба по out и out-ahl32: что изменится, отчёт
python tools/legacy_data/equipment27.py out --write              # запись в базу (копия — legacy-data/equipment27/backup/)
python tools/legacy_data/equipment27.py --write                  # обе базы; этап build-all «equip27», eaimport.py equipment
python tools/legacy_data/equipment27.py save СЕЙВ                # проба по сейву (ROSTER или DYNASTY — по таблицам файла)
python tools/legacy_data/equipment27.py save СЕЙВ --out КОПИЯ    # результат — в другой файл, исходник не трогается
python tools/legacy_data/equipment27.py save СЕЙВ --write        # на месте; копия до правки — legacy-data/backup-saves/
python tools/legacy_data/equipment27.py table glove              # модели NHL 27 → номера Legacy (stick, skate, helmet, glove)
python tools/legacy_data/equipment27.py mappings                 # перечитать таблицы моделей из дампа (кэш)
```

Опции: `--fields stick,gloves` (только эти поля), `--generic` (брать и шаблон EA, ниже), `--who Фамилия` (что станет у
этого игрока), `--show N` (N примеров на поле), `--db27`, `--meta` (схема сейва). Python 3.11+, только стандартная
библиотека; нужны база NHL 27 (`game/work/nhl27/db/nhl_game.db`, [import-from-ea.md](import-from-ea.md)) и, для команды
`mappings`, проход `fb.scan` дампа NHL 27. Отчёт — `game/work/legacy-data/equipment27/<набор или сейв>.json` (что
меняется по полям, какие модели куда, перезаписанные правки пользователя, первые 3000 изменений).

## Откуда

**База NHL 27.** `exhibitionskaterequipment` (7432 полевых) и `exhibitiongoalieequipment` (892 вратаря) по `game_id`.
Поля, которые есть и у Legacy, называются так же; модели — номерами.

**Номера моделей.** Ключи таблиц `content/common/configs/mappings/player_{stick,skate,helmet,glove}_mapping` дампа (ebx):
с 0x84 — u32 число записей, записи по 16 байт: u64 смещение C-строки имени от начала поля, u32 номер, u32 0. Так
устроены все 24 таблицы `mappings` (виды обмотки, визоров, заправки, шорт). Кэш — `game/work/equipment27/mappings27.json`
(вне git). Номера у EA сквозные со времён NHL 14: 105 у клюшек обеих игр — `bauer_vapor_1x`, 112 — `ccm_ribcor_40k`, у
краг 82 — `bauer_vapor_1x`, 66 — `warrior_covert_qr1`, у шлемов 23 — CCM Fitlite, 25 — Warrior Krown PX3. Новые модели
NHL 27 — номера выше (клюшки до 240, краги до 139, шлемы 26–42).

**Сшивка игроков.** Игрок Legacy ↔ NHL 27, только однозначные пары с обеих сторон, полевой к полевому, вратарь к вратарю:
1. имя, фамилия и дата рождения (без диакритики и знаков, `roster.common.norm`) — 4627 пар в `out`;
2. фамилия и дата рождения при той же первой букве имени: Sammy / Samuel Blais, Gabe / Gabriel Vilardi — 43;
3. имя, фамилия (одни на всю базу с обеих сторон) и год, если в дате NHL 27 день и месяц переставлены или неверно одно
   из них — у EA такие ошибки: Will Cuylle, Olen Zellweger, William Eklund (переставлены), MacKenzie Weegar, Carson
   Soucy, Gabe Perreault, Dalibor Dvorsky — 34.

**Шаблон EA.** У 5050 полевых NHL 27 (почти все юниоры CHL, европейские лиги, часть АХЛ) экипировка — заготовка
генератора: лента крюка цвета `0xDFDDD7` (у настоящих — `0xE7E7E7` белая или `0x202020` чёрная), у ~94 % — Vapor FlyLite
(клюшка, коньки, краги), Re-Akt 3D, обмотка smalltoe, гетры 0. Это не экипировка игрока, поэтому у такого игрока поле,
равное значению шаблона (самое частое значение поля у заготовок), не берётся и в Legacy остаётся прежним; отличное от
шаблона (у части заготовок своя клюшка или коньки) — берётся. `--generic` — брать и шаблон (тогда у всех юниоров одна
экипировка).

## Поля

| Legacy (полевые) | NHL 27 | Правило |
|---|---|---|
| `stick` | `stick` | модель → слот каталога по плану `tools/fb/stick_slots.toml` (`from = "nhl27:<модель>"`); не из плана — слот той же линейки (`STICK_LINES`), иначе марки; спецклюшки (`casual_graphic_*`, `special_*`, `xbox_*`) — не берутся |
| `skatebrand` | `skatebrand` | так же по `tools/fb/skate_slots.toml` и `SKATE_LINES`; командные спецконьки `nhl_<клуб>_original` — не берутся |
| `helmetbrand` | `helmetbrand` | модель Legacy той же марки и вида (`HELMET_LINES`); `generic_default` — не берётся |
| `gloves` | `gloves` | тот же номер, если такие краги есть в Legacy (`LEGACY_GLOVES`), иначе — по линейке (`GLOVE_LINES`) |
| `pantsbrand` | `pantsbrand` | как есть (0–5): сверено на 1077 игроках, бывших и в базе EA 2015, — значения 1, 3, 5 совпали у всех |
| `pantstypecode` | `pantstypecode` | looseshort 0, tightshort 2 → 0 (короткие); looselong 1, tightlong 3 → 1 (длинные) |
| `jerseytuck` | `jerseytuck` | как есть: notuck, lefttuck, righttuck, fulltuck — те же 0–3 |
| `skatesocktuck` | `skatesocktuck` | как есть: fulltuck, notuck, fronttuck, backtuck — те же 0–3 |
| `visortype` | `faceprotectortype` | −1 (нет) → 2; straight 0 → 0; curved 1, aviator 3 → 1 («авиатор»); large, tilted, hightilted, full, решётки 7–10 → 0 |
| `visorcolor` | `visorcolor` | как есть (0 прозрачный, 1 тёмный…, до 14) |
| `sticktapecolor` | `stickbladetapecolor` (RGB), `stickbladetapestyle` | ниже; игроки `tape_players.json` — код оттуда |

Вратари: `jerseytuck` и `sticktapecolor` (у вратарей NHL 27 — код 0/1, как у Legacy: сверено на 128 вратарях базы EA
2015, белая у 96 из 114). Щитки, блин, ловушка, клюшка и маска вратаря — командные (`goalie_gear.py`, решение
пользователя 12.10), не трогаются.

Без визора по NHL 27 из игроков клубов НХЛ — ровно трое: Jamie Benn, Ryan O'Reilly, Zach Bogosian. Это совпадает с
правилом пользователя от 08.10 ([player-equipment.md](player-equipment.md)).

### Модели

Полный список — `equipment27.py table`. Что выходит у игроков `out` (23.10.2026, игроков с моделью не из шаблона):

| | NHL 27 → Legacy |
|---|---|
| клюшки | Vapor FlyLite → 105 C (458), Supreme Fuse → 111 B (198), Ribcor Trigger 7 Pro / 8 → 103 H (Trigger 9), Jetspeed FT5 Pro / FT6 → 86 F (FT7), FT8 → 102 E, Tacks AS-V Pro → 87 I (Tacks XF), Alpha LX2 / LX Pro / QX Pro / DX → 98 T (Alpha LX3), Covert QR5 Pro / QRE / QRL → 84 S (QR6), Novium SP Pro → 100 AA (Novium 2), XF Ghost → 72 Y, Catalyst 9X / 9X3 → 85 L (Catalyst PX), Vizion → 106 N |
| коньки | Vapor FlyLite → 47 C (756), Supreme Fuse → 48 B (339), Jetspeed FT4 → 41 A (FT6), Tacks AS-V Pro → 39 F (Tacks XF), TRUE Custom → 74 K (TF Pro), Ribcor 80K → 44 E (100K), TRUE Catalyst → 45 G |
| шлемы | CCM Tacks 910 / 920 / 710 / X → 20 (CCM), Re-Akt 155 / 3D / 70 → 21 (Re-Akt), Bauer 4500 → 1, Fitlite 3DS → 23 (у EA при переносе в Legacy так же: 54 из 54), Warrior Alpha / Covert → 25 (Krown PX3), CCM V10 → 6, Bauer IMS → 18, TRUE → 24, JOFA → 7 (без визора; с визором — 1: у ретро-шлема 7 нет сетки визора) |
| краги | Vapor FlyLite → 82 (Vapor 1X), Jetspeed → 53 (CL500), Supreme → 80 (TotalOne MX3), Tacks → 68 (Tacks Ultra), 4-Roll → 29 (CCM 4R Pro), Nexus 2N → 83 (Nexus 1N), Covert → 66 (QR1), Alpha → 58 (Dynasty AX1), TRUE → 81 (Easton Stealth CX: как у клюшек, TRUE — на месте Easton), Sher-Wood → 62 |

Шлемы и краги Legacy — только с моделями в `cacherender/rendering/helmet` и `glove`; промо-краги EA 70–77, 100, 101 не
берутся (у NHL 27 под этими номерами другие).

### Обмотка крюка

Цвет — по RGB: синяя, зелёная, голубая → 2, 5, 7 (цвета EA); прочее по яркости — чёрная 0 или белая. У чёрной вид не
важен (частичных чёрных у Legacy нет, на чёрном карбоне не видно). У белой — вид NHL 27 → вариант Legacy
([tapestyles.py](../tools/tapestyles.py), [player-models.md](player-models.md) §13). Где у NHL 27 лента — по маскам
`player_sticktape_blade_common_<вид>_alpha` (1024 × 256) на развёртке крюка `uv1` (u от пятки 0 к носку 1):

| Вид NHL 27 | Лента, доля длины от пятки | Legacy |
|---|---|---|
| largetoe 0 | 0–0,70 | 4 «White No Toe» (0–0,87) |
| smalltoe 1 | 0–0,89 | 1 вся |
| notoe 2 | 0–1 | 1 вся |
| half 3 | 0,31–0,89 | 3 «White Middle» (0,30–0,87) |
| halfnotoe 4 | 0,31–1 | 6 «White No Heel» (0,25–1) |
| rezztek 5 | своя сетка | 1 вся |

smalltoe — вид шаблона EA (у 5584 из 7432), голый носок у него ~2,5 см; у Кейна NHL 27 — smalltoe, а пользователь по фото
поставил ему всю ленту (1), поэтому smalltoe → 1. Решения пользователя `tape_players.json` главнее (Benn 9, Celebrini 3,
Kane 1, Ovechkin 8, Laine 0): у Celebrini NHL 27 — half (тот же 3), у Ovechkin — halfnotoe (6, у пользователя 8).

### Не переносится

- `shoulderpads`, `skaterocker`, `stickcurve`, `stickflex`: в NHL 27 у всех одно значение (0, 1, 2, 1) — об игроке ничего;
- нет полей у Legacy: лента рукояти (`stickshafttape*`), шнурки и рама конька, защита лезвий, капа, защита шеи и ушей,
  цвета краг и шлема по зонам;
- решётки и щитки (`faceprotectortype` 2, 7–10 — женские лиги NHL 27): у полевых Legacy их нет, ставится визор;
- спецмодели (`casual_graphic_*` — у Овечкина клюшка такая, `special_*`, командные и сборные `nhl_*`, `intl_*`):
  остаётся прежнее;
- модели марок, которых в каталоге Legacy нет: клюшки TPS, Torspo, Rebellion, Winnwell, Busch, Graf, краги Verbero и
  Rebellion (`equipment27.py table` — «нет пары»): у сшитых игроков таких нет;
- игроки, которых нет в NHL 27 (или пара неоднозначна): в `out` — 928 из 5632.

## Охват (проба 23.10.2026)

| | `out` | `out-ahl32` | ROSTER 20261023161612 | DYNASTY 20261023154708 |
|---|---|---|---|---|
| игроков (полевых / вратарей) | 5066 / 566 | 5066 / 566 | 5066 / 566 | 4092 / 417 |
| пар с NHL 27 | 4704 | 4740 | 4740 | 2138 |
| из них полевых с шаблоном EA | 2756 | 2761 | 2761 | 680 |
| изменено игроков (полевых / вратарей) | 1675 / 201 | 1701 / 196 | 1702 / 196 | 1335 / 40 |
| `stick` | 1384 | 1405 | 1406 | 1135 |
| `skatebrand` | 1040 | 1053 | 1054 | 862 |
| `helmetbrand` | 1335 | 1354 | 1354 | 1074 |
| `gloves` | 1190 | 1218 | 1218 | 969 |
| `pantsbrand` / `pantstypecode` | 624 / 508 | 640 / 502 | 640 / 502 | 347 / 417 |
| `jerseytuck` / `skatesocktuck` | 5 / 828 | 5 / 832 | 4 / 831 | 4 / 665 |
| `visortype` / `visorcolor` | 174 / 42 | 171 / 42 | 171 / 42 | 91 / 37 |
| `sticktapecolor` (полевые + вратари) | 579 + 201 | 581 + 196 | 580 + 196 | 465 + 40 |

Во франшизе пар меньше: из 4509 её игроков 2770 вне клубов НХЛ и АХЛ (2709 без клуба), и это в основном игроки базы
EA 2015 года (ушедшие, их в NHL 27 нет) — сшито 646; у клубов НХЛ — 708 из 717, у АХЛ — 784 из 1022.

Правок пользователя из редактора (`legacy-data/equipment-user`) NHL 27 перезапишет в `out` 107 (клюшка 52, гетры 16,
коньки 15, обмотка 14, шорты 5, свитер 4, шлем 1), в ROSTER — 105: по решению пользователя.

## Сейвы

- **ROSTER** — таблицы `exhibition*`, ключ `game_id`, как в базе. Загруженный сейв составов игра берёт целиком, вместе с
  экипировкой (проверено на NHL 13: [player-equipment.md](player-equipment.md), «В игре: только через сохранённый
  состав»), поэтому правка нужна и в нём; в Legacy загрузку после такой правки ещё не проверяли. `roster_merge.py` при переносе новой базы правки пользователя в сейве оставляет — экипировку из NHL 27
  поверх них ставит только `equipment27.py save` (запускать после `roster_merge`).
- **DYNASTY** — своих `exhibition*` нет: `leagueplayerbiotable` (имя, дата рождения, `game_id` и `index`),
  `leagueskaterequipment` и `leaguegoalieequipment` (те же 16 полей и поля вратаря), ключ `index` (= `index` биографии;
  полевых 4092 + вратарей 417 = 4509 игроков). `game_id` франшизы не совпадает с базой (другие люди под теми же номерами),
  поэтому сшивка — тоже по имени. Франшиза Миннесоты — в сейвах 23.10 у `leaguegmdata` строки 14 (MIN) имя «GENERAL
  MANAGER»; последний — `DYNASTY 20261023154708` (`…142412A` и `…154456A` — раньше).
- Обёртка ZlibV4 (`tools/tdb.py SaveFile`): база разжимается, правятся поля живых строк, CRC таблиц, поток zlib, размер
  области (с прежним отношением к разжатому), checksum_b и checksum_a — заново; хвост франшизы (368 796 байт) — как был.
  Проверки перед записью: CRC базы и обёртки, размер файла тот же, повторный план пуст, все прочие таблицы и поля — байт
  в байт. На месте (`--write`) — только при закрытой игре (`tasklist`), копия до правки — `backup-saves/`; при ошибке
  после записи исходник возвращается.

## Порядок (базы и сейвы пользователя)

```bash
tasklist | grep -i nhl                                    # игра закрыта
python tools/legacy_data/equipment27.py --write           # out и out-ahl32 (+ draft_roster.db), копии — equipment27/backup
python tools/eaimport.py overlay                          # накладки out-nhl24* из новых баз
python tools/legacy_data/install_legacy_data.py status    # дальше — установка как обычно (import-from-ea.md)
U="nhl-legacy-port/userdata/B13EBABEBABEBABE/454109EC/00000001"
python tools/legacy_data/equipment27.py save "$U/ROSTER 20261023161612/ROSTER 20261023161612"            # проба
python tools/legacy_data/equipment27.py save "$U/ROSTER 20261023161612/ROSTER 20261023161612" --write    # после roster_merge
python tools/legacy_data/equipment27.py save "$U/DYNASTY 20261023154708/DYNASTY 20261023154708" --write
```

Сейв — последний по времени (`ls -t "$U"`). Повтор ничего не меняет, поэтому после нового сохранения в игре команду
можно повторить.

## Проверка

- `python tools/tdb.py diff ДО ПОСЛЕ --tables exhibitionskaterequipment` (франшиза — `leagueskaterequipment`, `--meta
  nhl-legacy-port/userdata/cache/guest/db/nhlng-meta.xml`) — что поменялось;
- `equipment27.py … --who Crosby` — что ставится игроку и почему;
- в игре (редактор игрока, экипировка): Crosby — клюшка «CCM Ribcor Trigger 9» (H), коньки «CCM Tacks XF» (F), шлем
  Fitlite, краги CCM; Kaprizov — шлем Bauer 4500, клюшка и коньки Supreme Fuse (B); McDavid — Jetspeed FT8 (E), белая лента.

## Грабли

- Даты рождения в NHL 27 местами с ошибкой (день и месяц переставлены и т. п.) — поэтому третий шаг сшивки; совсем
  другие даты (≥ 1 года) — не сшиваются: это другой человек с тем же именем.
- Слоты, закрытые в редакторе (клюшки X, Y, Z, AA; коньки I, J, K — предзаказ), игроки базы носят: XF Ghost — 21 игрок
  (Y), Novium 2 — 16 (AA), TRUE TF Pro / Custom — 87 (K). Выбрать их в редакторе нельзя; имя у K — общее с клюшкой Z
  (`eastonpreorder`, [skates.md](skates.md)). Текстуры этих слотов — из пакета клюшек и коньков (`kitport install`); пока он
  не стоит, у них прежние рисунки EA.
- Краги 29 (CCM 4R Pro), 58 (Dynasty AX1), 81 (Stealth CX) и коньки 74 у игроков базы до этого не стояли — модели в игре
  есть, но вид на льду пока не проверен.
- Номер NHL 27 у шлема 20 — `ccm_tacks_710`, у Legacy (каталог сообщества) — «CCM Resistance»: та же марка, модель может
  выглядеть иначе.
- Игрок, которого пользователь поменял в редакторе после записи, при повторе снова получит значение NHL 27.
- Франшизу с этой правкой в игре ещё не загружали. Игра отвергает сейвы франшизы с нарушенными связями таблиц
  ([save-editing.md](save-editing.md)); здесь меняются только значения полей экипировки, строки и номера — те же.
