# Маски вратарей из NHL 27 (`tools/fb/masks.py`, 03.11.2026)

Пользователь: «перенос вратарских шлемов Юты, Вегаса и Сиэтла, а также цветов экипы (не покроя щитков, а хотя бы просто
расцветки)». У трёх клубов вратари были в белом наборе с белой маской 0/120 (своего набора EA нет, у Юты — набор Аризоны,
`goalie_gear.json` → `white_names`). Цвета щитков, блина, ловушки и клюшки — [legacy-data.md](legacy-data.md), «Расцветка
вратарей UTA, SEA, VGK из NHL 27»; здесь — рисунок маски.

## Как устроено

- **Legacy.** Модель маски — `rendering/goaliehelmet/helmet_<masktype>_<L>.rx2`; тип 0 — itech (шейдер
  `helmet_goalie_current_itech_high`), решётка — отдельная модель `cage_*`. Рисунок — `goaliehelmet_<masktype>_<maskid>_cm.rx2`
  (512² DXT1). У типа 0 номера 0…291 заняты EA, поле `maskid` — 9 бит (до 511). Маску вратарю задают поля
  `exhibitiongoalieequipment.masktype` и `maskid`.
- **NHL 27.** Рисунок — `character/skater/goalie/helmet/itech/textures/goalie_helmet_itech_<N>_color` (2048²), модель —
  `goalie_helmet_itech_mesh` (секция `mat_helmet`, решётка в той же сетке). N у вратаря — `maskid` в `nhl_game.db`.
- Развёртки двух моделей похожи (купол, затылок, ремни), но не совпадают (`game/work/models-check/probe/mask_uv.png`),
  поэтому перенос по 3D: модель NHL 27 без прутьев решётки (связные куски, у которых развёртка по v уже `CAGE_UV` 0,03)
  вписывается в рамку модели Legacy по осям (у NHL 27 голова на ~6–8 см выше и впереди, размеры — до 2 см), каждый тексель
  Legacy берёт цвет с ближайшей точки NHL 27 (`kit3d.transfer`). Без исключения решётки серый цвет прутьев ложился полосой на
  лоб и подбородок.
- Новые маски — свободные номера, план `tools/fb/mask_slots.toml` (номер Legacy ← номер NHL 27). Файл рисунка — по шаблону
  белой маски 0/120 (растр переименовывается на новый номер).
- Вратарю маску ставит этап `goaliegear` (`tools/legacy_data/goalie_gear.py`): у клубов `nhl27_colors` маска — его маска
  NHL 27 из плана, если она там есть.

| Legacy | NHL 27 itech | вратари |
|---|---|---|
| 0/292 | 420 | Grubauer, Daccord (SEA) |
| 0/293 | 515 | Cossa (UTA) |
| 0/294 | 516 | Vejmelka (UTA) |
| 0/295 | 609 | Hill (VGK) |
| 0/296 | 85 | Hart (VGK) |

## Запуск

```bash
cd tools
FB_GAME=nhl27 python -m fb.extract "goalie/helmet/itech/.*goalie_helmet_itech_(420|515|516|609|85)_color$" --out masks27
FB_GAME=nhl27 python -m fb.masks build    # → game/work/nhl27/out/masks/cache/rendering/goaliehelmet/*.rx2 и PNG
python -m fb.masks sheet                  # → game/work/nhl27/out/masks/sheet.png: Legacy сейчас | NHL 27 | в Legacy
python legacy_data/goalie_gear.py db БАЗА.db --clubs "Utah Mammoth,Seattle Kraken,Vegas Golden Knights"
python legacy_data/goalie_gear.py save СЕЙВ_ROSTER --write --clubs "Utah Mammoth,Seattle Kraken,Vegas Golden Knights"
```

Добавить вратаря: номер его маски в NHL 27 (`nhl_game.db`) → новая строка `[mask.<свободный номер>]` в `mask_slots.toml`,
выгрузка, `build`; клуб — в `goalie_gear.json` → `nhl27_colors.clubs`.

## Проверка и остаток

- Лист `game/work/nhl27/out/masks/sheet.png` (по два ракурса): рисунок на Legacy совпадает с NHL 27 — полосы Кракена,
  надпись UTAH, мамонт, золотой дракон Хилла, золото Харта.
- Остаток: в проёме маски у лба видна часть подкладки NHL 27 (кусок с логотипом изнутри) — в игре её закрывает решётка.
- Модели щитков, блина и ловушки — Legacy (белого набора), покрой не переносится.
