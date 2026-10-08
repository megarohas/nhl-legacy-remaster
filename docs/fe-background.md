# Фон меню: синий анимированный фон и его перекраска

Разбор от 08.10.2026 (файлы — диск + TU2, логи — `port/out/game-*.log`). Инструмент —
[tools/febg.py](../tools/febg.py). Всё собранное лежит в `game/work/fe-bg/` (вне git), в
`game/userdata` ничего не записано. **В игре результат ещё не проверялся.**

## Коротко

- Это **не видео**. Ролики VP6 (`cachemovie.big`, `cache.big`, `nocache.big`) — заставка EA, матч-интро,
  шторки повтора, атмосфера арен. Фон меню — ролик интерфейса **Apt** (Flash EA) в контейнере BIGF,
  как фото игроков и логотипы: текстуры DXT5, заливки и кадры анимации.
- Два файла:

  | Файл в `cache:` | Архив | Что |
  |---|---|---|
  | `fe\ion\game\background\nhlbluebackground.big` (3 720 байт) | `boot.big` | класс `NHLBlueBackground`: подложка `mcColor` (синий прямоугольник) + `mcBackground` — импорт второго файла |
  | `fe\ion\game\background\nhlbluebackgroundcomponents.big` (130 116 байт) | `cache.big` | класс `NHLBlueBackgroundComponents`: сам фон, «стёкла»-полосы, блики, виньетка, логотипы команд, затемнение |

- Синее в нём — всего четыре места (всё остальное белое/чёрное): текстура 32×32 сплошного
  **#0040BA**, подложка **#0A09E1** (+ контур #151B20), тёплое свечение по центру (бледно-жёлтое — тоже
  часть «синей» гаммы) и голубоватый блик; плюс синяя **добавка цвета 00003DAE** у логотипов команд
  (302 PlaceObject).
- Собран серый вариант той же светлоты — `game/work/fe-bg/out/` (2 файла), запасные цвета —
  `game/work/fe-bg/variants/`, превью кадров до/после — `game/work/fe-bg/preview/`. Устройство роликов
  не меняется: правятся только слова цвета и пиксели текстур (`febg.py verify` это проверяет).
- Ставить при **закрытой** игре копированием в `game/userdata/cache/guest/`; оба файла игра читает при
  запуске (`boot.big` — сразу после фреймворка), поэтому нужен перезапуск.

## 1. Откуда фон и где он виден

`fe/ion/main.big` (ActionScript `backgroundIds.as`) задаёт фреймворку (`cafe`, ModeTransitionManager в
`fe/ion/external/ion_sports07/fw/commonloader.big`) три фона:

| Строка в `main.big` | Файл | Роль |
|---|---|---|
| `game/background/NHLBlueBackground.swf` | `nhlbluebackground.big` | «цветной фон» (`c_cColorBackground`, `DEPTH_COLOR_BACKGROUND`) — слой под всеми экранами меню |
| `game/background/NHLMainMenuBackground` | `nhlmainmenubackground.big` | своя сцена главного меню (см. §6) |
| `artAssets/backgrounds/vignette` | `vignette.big` | чёрная шторка для затемнения (`SetVignetteAlpha`), не цветная |

В логе порта (`game-release.log`, строки ~183–188) оба файла фона запрашиваются из `cache:` при
запуске, сразу после `podmanager.big`, — рядом с `vignette.big` и `blackbg.big` (рамки безопасной зоны
для отладки). Загрузчик сначала проверяет свободный файл (`NtCreateFile FAILED: path='cache:\fe\ion\game\
background\nhlbluebackground.big'`), потом берёт из архива — тот же механизм, что у базы и логотипов
([modding.md](modding.md)). В TU2 (`patch.big`) этих файлов нет.

Кто обращается к фону (`gMTM.GetBackground()`; поиск по Apt Data и константам всех 14 269 роликов
`fe/ion` из `boot`, `cache` и TU2):

- `screens/playnow/loadingscreen/loadingscreenhub.big` — предматчевый хаб (Starting Lineups и соседние
  экраны): `SetDim`;
- `pods/uicontrolhandlers.big` — `SetDim`, зона создания (`CREATION_ZONE_BACKGROUND_DIM`/`UNDIM`) и,
  судя по именам, полупрозрачный фон в паузе матча (`IN_GAME_BACKGROUND_ALPHA`, `gSetBackgroundAlpha`;
  не проверено);
- `pods/helpers/generalhelpers.big`, `pods/helpers/dynastyhelpers.big`,
  `components/nhldynastyhubsideinfopanel.big`, `components/nhldynastytablespanel.big` — `GetBackground`
  (что именно делают — не разбиралось);
- `components/nhlbackgroundmovieplayer.big` (телевизор) — `SetImageAssets`/`HideImageAssets`: логотипы
  команд на фоне (`mcLogoAway`/`mcLogoHome`, матч любимой команды «хозяева — гости»);
- `nhlmainmenubackground.big` импортирует `NHLBlueBackgroundComponents` — уменьшенное отражение под
  телевизором (`mcBlueBackgroundReflection`, масштаб 0,215).

То есть один и тот же синий фон — у всех меню, кроме главного (у него своя сцена «студии»).
Остальные файлы `fe/ion/game/background/` графики не содержат или не синие: `nhltitlebackground`,
`nhlplaynowbackground`, `nhlloadingbackground`, `nhlgamemode`, `nhlcreationzone` — классы-наследники
`NHLBaseBackground` без единой фигуры; `nhlbootflowbackground` — одна тёмная текстура 2048×1024 для
экранов запуска (выбор языка); `nhlshapes` — частицы, дым и линии для эффекта
`components/nhlgsa_headexplosion.big` (синяя заливка там — только маска, цвет линий задаёт код `setRGB`).

Экраны выбора команд и франшизы (`playnow/01_selectteams08`, `dynasty/dm37_calendar`,
`dm50_dynastyhub`, `selectteamscreen`, `practice/pm03_selectteam`, `scenariosettingsscreen`,
`pro/playerbio`) вызывают `ChangePrimaryBackgroundColor`/`ChangeSecondaryBackgroundColor`; фреймворк
передаёт это «цветному фону» как `ChangeColorPrimary`/`ChangeColorSecondary`, а у `NHLBlueBackground`
таких методов нет (по константам) — цвет фона под команду не меняется, что видно и в игре (на
Starting Lineups фон обычный синий).

## 2. Устройство фона

`nhlbluebackground.big` → Sprite 4 (экземпляр `background`, класс `NHLBlueBackground`):

| Глубина | Имя | Что |
|---|---|---|
| 1 | `mcColor` | Shape 1: заливка **FF0A09E1** 1479×1280 + контур FF151B20 |
| 3 | `mcBackground` | импорт `game/background/NHLBlueBackgroundComponents` |

Код класса только двигает и масштабирует `mcBackground` при смене режимов (`ACTIVE_*`/`INACTIVE_*`,
`speedZoomIn`), пробрасывает `SetDim`, `SetImageAssets`, паузу и запуск «живой» анимации. Цвет кодом
не задаётся: в константах нет `Color`/`setRGB`/`setTransform` (у фреймворка есть `ChangePrimary/
SecondaryBackgroundColor`, но такого метода у `NHLBlueBackground` нет — вызов был бы пустым).

`nhlbluebackgroundcomponents.big` → Sprite 33 (экспорт `game.background.NHLBlueBackgroundComponents`),
всё — вокруг начала координат (в превью ставится в центр экрана 1280×720, так он и выглядит в игре):

| Глубина | Имя | Символ | Что |
|---|---|---|---|
| 1 | `mcBlueBg` | Sprite 10 | основа: Image 1 (32×32, сплошной **#0040BA**) ×370/×230 → 1480×920; свечение Image 4 (256×256, бледно-жёлтое (247, 243, 173), альфа ≤ 110) с прозрачностью 25 %; виньетка Image 7 (512×256, чёрная) 55 % |
| 7, 9 | `mcLogoAway`, `mcLogoHome` | Sprite 13 (421 кадр) | логотип команды (ImageLoader) — появляется, медленно растёт, гаснет; **добавка 00003DAE**; 20 % |
| 11 → 25 | `mcMask2` | Sprite 17 | маска (clip depth): две полосы Sprite 16 под −24° открывают копию `mcBlueBg` и логотипы на 50 % |
| 29 → 43 | `mcMask1` | Sprite 18 | то же под −60°, логотипы на 30 % |
| 47, 56 | `mcGlass2`, `mcGlass1` | Sprite 29, 30 → Sprite 28 (322 кадра) | «стёкла»: светлая полоса (Image 14, белая с альфой), тёмная полоса (та же, множитель FF000000), бегущий блик (Image 22) и вспышка вдоль кромки (Image 25) |
| 65 | `mcVingette` | Sprite 9 | виньетка ещё раз |
| 67 | `mcDimmer` | Sprite 32 | чёрный прямоугольник 1502×1000, 66 % — затемнение (`SetDim`), обычно скрыт |

Анимация: шкалы кадров 60 к/с (блик и вспышка — Sprite 28, логотипы — Sprite 13) плюс скрипт
`_AnimateAmbient`: части масок и «стёкол» (`mcPartA/B`, `mcMaskPartA/B`) медленно ходят к случайным
точкам (`MASK1_MIN_Y`…, `GLASS_DELTA_RANGE`, `ANGLE_DELTA`), стёкла повторяют маски
(`_CopyMovieClipProperties`). Перекраска ничего из этого не трогает.

## 3. Формат (дополнение к [player-photos.md](player-photos.md))

Проверено на фоновых роликах (`Apt Data:1:7:4`, у главного меню `1:8:4` — разбирается так же).

- **BIGF**: как у фото, но общий размер (u32 LE по +4) **добит нулями до кратного 4** —
  `playerhead.Bigf.build` этого не делает; `febg.build_bigf` с добивкой собирает 383 файла
  `fe/ion/game/background`, `components`, `artassets/backgrounds` и весь `boot.big/fe` байт-в-байт.
  Записи: `0` — Apt Data, `1` — константы, `<N+1>` — геометрия Shape N или текстура Image N.
- **Начало Movie** надёжно брать из константного файла: `Apt constant file` + `1A 00 00`, по +0x14 —
  смещение Movie в Apt Data, +0x18 — число констант, +0x20 — пары (тип, значение), тип 1 — строка.
  В Apt Data сразу за заголовком лежат таблицы импорта (путь ролика, имя, символ, 0) и экспорта (имя,
  символ).
- **Символ**: u32 тип, u32 `0x09876543`, два слова (у Shape первое — номер Image), дальше своё.
  Movie: +0x10 число кадров, +0x14 кадры, +0x1C число символов, +0x20 таблица символов (0 — импорт),
  +0x24/+0x28 сцена, +0x2C мс на кадр, +0x30/+0x34 импорт, +0x38/+0x3C экспорт. Sprite: +0x10/+0x14
  кадры. Image: +0x10 номер текстуры. Shape: +0x10 рамка (4 float), +0x20 номер геометрии.
- **Кадр** — (число элементов, указатель на массив указателей). Элементы: 1 Action, 2 FrameLabel,
  3 PlaceObject, 4 RemoveObject (+4 глубина), 5 BackgroundColor (+4 ARGB), 8 InitAction (+4 спрайт,
  +8 байткод).
- **PlaceObject** (0x40 байт): +4 флаги (1 move, 2 символ, 4 матрица, 8 цвет, 0x10 ratio, 0x20 имя,
  0x40 маска, 0x80 обработчики), +8 глубина, +0xC символ, +0x10 матрица a b c d (x′ = a·x + c·y + tx,
  как во Flash и canvas), +0x20 tx ty, **+0x28 множитель цвета ARGB, +0x2C добавка ARGB**, +0x30 ratio,
  +0x34 имя, +0x38 глубина маски, +0x3C обработчики.
- **Геометрия**: u32 размер, u32 число сеток, 0, смещения сеток; сетка — размер, число заливок, 0,
  смещения заливок от начала сетки; заливка — +0 размер, +4 тип (0 текстура, 2 цвет, 3 линии),
  +0xC толщина линии, **+0x10 цвет ARGB**, +0x14 Image, +0x20 матрица текстуры (точка → тексель того
  же растра, порядок Flash), +0x38 число треугольников (отрезков), +0x3C смещение вершин (32 байта на
  вершину треугольника, 16 — отрезка; x, y — float). Растр лежит в левом верхнем углу текстуры
  (например, 4×4 в 32×32).
- **Текстуры** — XPR2, DXT5 (у компонентов главного меню DXT1), тайлинг Xenos, 8in16, без мипов;
  разбор и сборка — `teamart.Fetch/Layout/dxt_*`.

## 4. Перекраска

```bash
python tools/febg.py info game/extracted/big/cache/fe/ion/game/background/nhlbluebackgroundcomponents.big
python tools/febg.py recolor game/work/fe-bg/out --gray            # серый той же светлоты, #5D5D5D
python tools/febg.py recolor DIR --gray 120                        # серый заданного уровня (0…255)
python tools/febg.py recolor DIR --color 8E1B1B                    # любой цвет вместо основного синего
python tools/febg.py verify game/work/fe-bg/out                    # изменены только цвет и пиксели текстур
python tools/febg.py preview game/work/fe-bg/preview --src game/work/fe-bg/out --label серый
```

- `--color RRGGBB` — во что превращается основной синий #0040BA; остальные цвета ролика идут за ним:
  оттенок (HSL) сдвигается на ту же величину, насыщенность умножается на s(цель)/s(#0040BA),
  светлота — по ломаной 0 → 0, l(#0040BA) → l(цель), 1 → 1. Белое и чёрное не меняются, альфа — никогда.
  `--gray` — насыщенность 0 при той же светлоте (0,365 → #5D5D5D); `--gray N` — серый уровня N.
- Где меняется: слова цвета заливок (+0x10), множители/добавки PlaceObject (+0x28/+0x2C; нейтральные
  множители вроде FFFFFFFF/FF000000 не трогаются), пиксели текстур. Текстура пересжимается, только если
  изменение заметно (≥ 2/255 с учётом альфы), иначе остаются исходные байты. Ролики пересжимаются
  RefPack, как были.
- DXT: блоки одного цвета и «почти одного серого» (±4) кодируются одним цветом с подобранными концами
  (точка 2/3·c0 + 1/3·c1, как OMatch в stb_dxt) — иначе 565 уводит серый в зелень/пурпур на 2–4 единицы,
  а чёрный — в (0, 0, 8). Итог по `build.log`: основа 32×32 — ровно (93, 93, 93), PSNR пересжатия
  свечения 62 дБ, блика 53 дБ.

Серый #5D5D5D заменяет основу; подложка #0A09E1 → #757575, контур → #1A1A1A, свечение → (209, 209, 209),
блик → (221, 221, 221), добавка логотипов 00003DAE → 00575757 (логотипы светлеют нейтрально вместо
синего отлива).

## 5. Превью

`febg.py preview` рисует ролики в Chrome/Edge без окна (canvas): шкалы кадров, маски (clip depth),
множители/добавки цвета, текстуры с их матрицами — по разобранным данным, а не по снимкам игры.
Оригинал совпадает с экраном игры (полосы под −24° и −60°, виньетка, блик). Отличия от игры:
дрейф полос (в игре — скрипт со случайными точками) заменён плавными синусами, логотипы команд (их
подгружает ImageLoader из кода) и затемнение `mcDimmer` не рисуются; телевизор и карточки главного меню
— другие файлы, на превью главного меню там пусто.

## 6. Главное меню (по желанию)

`nhlmainmenubackground.big` (+ лёд и фермы `nhlbackgroundcompressedcomponents.big`) — отдельная тёмная
«студия» с синими неоновыми огнями, бликами и логотипом НХЛ, не тот фон, что в остальных меню. Серая
версия собрана отдельно (`febg.py recolor DIR --gray --sets mainmenu`, 27 + 3 текстуры, ≈ 30 с):
`game/work/fe-bg/out-mainmenu/`, сравнение — `preview/mainmenu.png`. Телевизор
(`components/nhlbackgroundmovieplayer.big`) и карточки (`components/nhlbackgroundcard.big`) не
перекрашивались.

## 7. Что собрано (`game/work/fe-bg/`, вне git)

| Путь | Что |
|---|---|
| `out/fe/ion/game/background/nhlbluebackground.big`, `…/nhlbluebackgroundcomponents.big` | серый фон #5D5D5D (3 720 и 115 780 байт) |
| `variants/graphite`, `light-gray`, `red`, `green`, `purple` | те же 2 файла: #3A3A3A, #808080, #8E1B1B, #1D6B3A, #4B2A8A |
| `out-mainmenu/fe/ion/game/background/…` | серое главное меню (2 файла), по желанию |
| `preview/compare.png`, `frames/compare/*.png` | оригинал и серый, 0 / 2,5 / 5 / 7,5 с, 640×360 |
| `preview/palette.png` | все варианты, 1,5 и 4 с |
| `preview/mainmenu.png` | главное меню до/после |
| `preview/*.html` | живая анимация вариантов рядом (открыть в браузере) |
| `build.log`, `build-mainmenu.log` | что поменялось в каждом файле |

## 8. Установка и откат

При закрытой игре:

```bash
cd /s/Claude/megarohas_nhl13/game
cp -r work/fe-bg/out/fe userdata/cache/guest/                 # серый (или work/fe-bg/variants/<имя>/fe)
cp -r work/fe-bg/out-mainmenu/fe userdata/cache/guest/        # по желанию: серое главное меню
```

Откат — удалить из `userdata/cache/guest/fe/ion/game/background/` положенные файлы
(`nhlbluebackground.big`, `nhlbluebackgroundcomponents.big`, для главного меню —
`nhlmainmenubackground.big`, `nhlbackgroundcompressedcomponents.big`): игра снова возьмёт их из архивов.
Своих файлов в этой папке раньше не было.

## 9. Не проверено

- В игре не запускалось (игра была занята): ни вид, ни то, что загрузчик примет пересжатую нашим
  RefPack запись Apt Data (`0`; у фото так пересжимались только текстуры).
- Логотипы команд с новой добавкой цвета на превью не видны.
- Дрейф полос в превью приблизительный (см. §5).
- Полупрозрачный фон в паузе матча и зона создания — по именам констант.
