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
| 0/297–319 | 451, 450, 404, 403, 423, 424, 103, 298, 263, 163, 84, 92, 161, 288, 287, 258, 187, 108, 270, 99, 178, 289, 87 | 16 клубов АХЛ (CV, HSK, ABB, SPR, COE, UTI, CLE, ONT, HMR, LAV, BLV, RFD, SJ, TUC, CGW, HAR), по клубу — `mask_slots.toml` |

**Клубы АХЛ (03.11.2026, второе задание).** Пользователь: «для обновлённых команд обнови … шлема вратарей и цвета экипы
вратарей»; список — `game/work/ahl27/decisions.txt` (решение по формам). Маски — все маски вратарей этих клубов в NHL 27
(23 штуки, у части клубов основной и запасной в разных). Вратарь Legacy, которого нет в этом клубе NHL 27 (другой клуб,
нет в NHL 27, имя пишется иначе: Nikke/Niklas Kokko, Georgii/Georgi Romanov), берёт маску и цвета вратаря клуба NHL 27 с
маской основного (первый в составе) или запасного (остальные), `goaliemask0_starter/backup` клуба в NHL 27. Имена
сравниваются без диакритики (Málek = Malek). Проба на копии базы 2bdc4466 и ROSTER 20261103060852: 34 вратаря 16 клубов;
у клубов с набором EA (HAR, ONT, RFD, SJ, TUC) и из `white_names` набор заменён NHL 27, остальные `white_names` — как были.

## Запуск

```bash
cd tools
FB_GAME=nhl27 python -m fb.extract "goalie/helmet/itech/.*goalie_helmet_itech_(<номера NHL 27 из mask_slots.toml через |>)_color$" --out masks27
FB_GAME=nhl27 python -m fb.masks build    # → game/work/nhl27/out/masks/cache/rendering/goaliehelmet/*.rx2 и PNG
python -m fb.masks sheet                  # → game/work/nhl27/out/masks/sheet.png: Legacy сейчас | NHL 27 | в Legacy
python -m kitport put --from ../game/work/nhl27/out/masks/cache --tag masks-<дата> --yes   # рисунки в cache: с копией
python legacy_data/goalie_gear.py db БАЗА.db --clubs "<клубы через запятую>"
python legacy_data/goalie_gear.py save СЕЙВ_ROSTER --write --clubs "<клубы через запятую>"
```

Добавить вратаря: номер его маски в NHL 27 (`nhl_game.db`) → новая строка `[mask.<свободный номер>]` в `mask_slots.toml`,
выгрузка, `build`; клуб — в `goalie_gear.json` → `nhl27_colors.clubs`.

## Проверка и остаток

- Лист `game/work/nhl27/out/masks/sheet.png` (по два ракурса): рисунок на Legacy совпадает с NHL 27 — полосы Кракена,
  надпись UTAH, мамонт, золотой дракон Хилла, золото Харта.
- Остаток: в проёме маски у лба видна часть подкладки NHL 27 (кусок с логотипом изнутри) — в игре её закрывает решётка.
- Модели щитков, блина и ловушки — Legacy (белого набора), покрой не переносится.
