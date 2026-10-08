# Главное меню NHL 12 в NHL 13

Разбор и перенос от 08.10.2026. Инструменты — [tools/feapt.py](../tools/feapt.py) (ActionScript и
символы роликов Apt), [tools/menu12.py](../tools/menu12.py) (сборка меню),
[tools/menuplayers.py](../tools/menuplayers.py) (игроки на фоне). Всё собранное — в `game/work/menu12/`
(вне git); фото игроков и картинки из них — только для личного использования, в git их нет.
Смежное: [fe-background.md](fe-background.md) (формат роликов, синий фон), [fe-fonts.md](fe-fonts.md)
(шрифт NHL 12), [player-photos.md](player-photos.md) (портреты).

## Коротко

- Главное меню обеих игр — три независимые части: **фон главного меню** (класс
  `game.background.NHLMainMenuBackground`, `cache:\fe\ion\game\background\nhlmainmenubackground.big`),
  **список меню** (общий компонент фреймворка для всех меню игры) и **полосы интерфейса** (бегущая строка,
  подсказки, панель «NHL 13 Features»). Логика меню (пункты, переходы, режимы) — в
  `boot/fe/ion/game/menus/mainmenuitems.big` и коде игры; её не трогаем.
- **Фон NHL 12 работает в NHL 13 как есть** (тот же базовый класс `NHLBaseBackground`, тот же
  ImageLoader из stdControls, те же картинки игроков в архивах NHL 13), кроме одного: фреймворк NHL 13 шлёт
  событие «переход начался» уже после `Init` фона, и фон NHL 12 принимал собственное появление за уход —
  гасил игрока и снимал анимации. Исправлено двумя правками байткода той же длины.
- **Список меню** NHL 13 оставлен своим (данные меню у NHL 13 другие — `MenuDataManager`), а вид — как у
  NHL 12: пересажена металлическая косая плашка выделения NHL 12 и шрифт пунктов 34/25; панель «NHL 13
  Features» перенесена вверх влево — на место панели новостей NHL 12.
- **Игроки на фоне** — современные звёзды из нашей базы 2026/27 (29 мест + 7 легенд NHL 12) с фамилиями
  «металлом»; кольца света — цвет клуба из установленной базы. Инструмент — `menuplayers.py`.
- Проверено в игре: главное меню, подменю, вход в режим (Play Now → выбор команд) и возврат — без падений.

## 1. Из чего состоит главное меню

| Что | NHL 12 | NHL 13 |
|---|---|---|
| Фон главного меню | `cache: fe/ion/game/background/nhlmainmenubackground.big` (557 КБ, Apt 1:7:4): тёмная арена, лёд, прожекторы, кольца света, **большой игрок** | тот же путь (846 КБ, 1:8:4): «студия» с телевизором, тремя карточками игроков любимой команды, логотипом НХЛ |
| Картинки игроков | `artAssets/backgrounds/mainMenuPlayers/nhl<N>` и `…Blur/nhl<N>`, легенды — `mainMenuLegends(Blur)/nhl<N>` | те же файлы лежат в архивах (байт-в-байт те же картинки NHL 12), но код NHL 13 их не грузит |
| Список меню | `boot: external/ion_sports07/components/mainMenuNew.swf` (его грузит `fw/main.big`) | `boot: game/components/Menu.swf` — новый компонент `game.components.classes.Menu`; копия mainMenuNew лежит в cache, не используется |
| Пункты меню | `boot: game/menus/mainmenuitems.big` | то же (свой вариант: GM Connected, Moments Live, …) |
| Шрифты пунктов | `MenuOptions` в `fw/commonloader.big`: 25 (пункт), 34 (выделенный) | там же те же значения, но `fe/ion/main.big` перекрывает: `GetCustomMenuOptions` — 24 у всех |
| Внизу | бегущая строка (`stdticker`, `nhltickerbackground`) | бегущая строка + панель «NHL 13 Features» (`nhl_proshopnotification.big`) |

Какие фоны у каких режимов — `fe/ion/main.big`, `backgroundIds.as`: `_global.BACKGROUND[путь] = грань`.
Главному меню в обеих играх соответствует грань `MENU` = `game/background/NHLMainMenuBackground`.
У NHL 12 у остальных режимов свои арены (`NHLPlayNowBackground` 517 КБ, `NHLPlayoffBackground`,
Winter Classic…), у NHL 13 они пустые классы — везде синий фон ([fe-background.md](fe-background.md)).

## 2. Как код говорит с фоном

Фреймворк — `ion.manager.ModeTransitionManager` (`gMTM`, `fw/commonloader.big`). Фон — ролик с экземпляром
`Background` в корне; класс наследует `game.background.NHLBaseBackground` → `ion.background.BaseBackground`.

| | NHL 12 | NHL 13 |
|---|---|---|
| Загрузка | `cBackground.loadMovie(путь)` и сразу переход (`Transition`: событие `ModeTransitionStarted`) | `MovieLoader.LoadMovie` → ждёт `IsLoaded()` (ставит `BaseBackground.Init`) → `PostLoadbackground` → `Transition` → `ModeTransitionStarted` |
| Выгрузка | фон сам вызывает `Shutdown` в `OnModeTransitionStarted` | `UnloadMovie` → `Destroy()` → `Shutdown()` → `removeMovieClip` |
| `NHLBaseBackground` | `ClearOnEnterFrameAnimation`, `DestroyInterval` | то же, байт-в-байт по коду |

Что ещё NHL 13 вызывает у текущего фона (`gMTM.GetCurrentBackground()`): `PlayMovieOnTvScreen`,
`StopMovieOnTvScreen`, `GetIsShowingDynamicMessage` (classloader, панель Features), `GetAnimateOutDelayTime`
(commonloader), `Refresh` (экран выбора любимой команды). У фона NHL 12 их нет — в ActionScript вызов
несуществующего метода ничего не делает, и все места написаны с проверками (`… == null`, `undefined → 0`).
Следствие: на главном меню нет роликов «телевизора» (рекламные видео NHL 13) — их и не было в NHL 12.

**Правки фона** (`menu12.py`, функция `bg_edits`; обе той же длины, находятся по шаблону команд):

1. `this.mMTMListenerObject = Delegate.Create(this, this.animateBackgroundOut)` →
   `Delegate.Create(this, this.mDelay)`: слушатель `ModeTransitionStarted` пустой (вызов числа — ничего).
   Без этого в NHL 13 игрок гаснет сразу при появлении, а `ClearAllAnimations` останавливает смену игроков.
2. В `Shutdown`: `trace(CLASS_NAME + "::Shutdown")` → `this.ClearAllAnimations()` + `PushByte 0; Pop` и
   `PushZero; Pop` ×2 (заполнение) — раз уход больше не снимает анимации, их снимает выгрузка.

Как фон NHL 12 выбирает игрока: массив `m_backgroundPlayers` (29 мест: ASSET_ID 0, 2…29; 1 — нет) и, если
`ION_NHLBeAPro.IsLegendsEnabled()`, `m_backgroundLegends` (7); случайный (`ION_Platform.GetRandomNumber`),
каждые ~32 с следующий. У места: `ASSET_ID`, `PRIMARY_COLOUR` (цвет колец света), `ANIM_TYPE_1` (проезд).
Картинки — `ImageLoader.setImage("artAssets/backgrounds/mainMenuPlayers/nhl" + ASSET_ID + ".swf")`.
Не по базе и не по любимой команде — фиксированный список в байткоде.

**Фамилий в главном меню NHL 12 нет.** В архивах NHL 12 лежат `mainMenuPlayerNames/nhl<N>` — большие
фамилии «металлом» (721×150), и в фоне есть пустой символ `mcNameMask`, но код фона их не грузит, и
фамилии не совпадают с картинками (на месте 22 картинка Turris, фамилия BRYZGALOV) — это остатки NHL 11.
Наши фамилии нарисованы в том же стиле прямо в картинке игрока (см. §5).

## 3. Список меню

Оба компонента устроены одинаково по графике: экземпляр пункта создаёт плашку выделения
`attachMovie("SelectorBG")` (символ с дочерними `left`, `center`, `right`; код растягивает `center` и
двигает `right`), `Shine`, `Glint`. Логика разная: у NHL 13 — `MenuDataManager`, `MenuItemData`,
`SetMenuData`, `Refresh`…; подставить mainMenuNew NHL 12 вместо Menu.swf нельзя без переписывания пунктов
меню, поэтому перенесён только вид:

- **Плашка выделения NHL 12** (`mainMenuNew` символ 69 `selectorBG`: металлическая полоса 252×39 и
  косые края 24×39, текстуры 8888) пересажена в `menu.big` (`feapt.py graft` — новые символы 99…108,
  экспорт `selectorBG` → 108, три геометрии и три текстуры новыми записями BIGF).
- **Шрифт пунктов как у NHL 12**: в `fe/ion/main.big` (`GetCustomMenuOptions`) размеры 24 → 34 у
  четырёх форматов, тень выделенного #FFFFFF → #DDDDDD, `mDisabledAlpha` 30 → 50; в `menu.big`
  `MenuItem.UNHIGHLIGHTING_SCALE` 0,9 → 0,735 (невыделенные 34 × 0,735 ≈ 25, как у NHL 12).
  Ряды (`mRowSizeHighlighted` 45 / `Unhighlighted` 28) у игр одинаковые. Сам шрифт (DIN NHL 12) — от
  [fe-fonts.md](fe-fonts.md).
- Компонент общий для всех меню игры — плашка и размеры теперь такие во всех списках (подменю, пауза…).
- Рамка подменю справа от пункта: у NHL 13 — тёмно-синяя, у NHL 12 — чёрная косая `newPreviewPanel`
  другого устройства; пересаживать её нельзя (иная разметка), поэтому три её текстуры сделаны нейтральными
  той же яркости (`menu12.py`, `desaturate_textures`). Место списка на экране — как у NHL 13.

**Панель «NHL 13 Features»** (`cache: fe/ion/game/components/nhl_proshopnotification.big`, грузится в свой
`_level` из `pods/helpers/generalhelpers.big`): у NHL 13 стоит внизу справа (`InitAnimation`:
`THIS_MOVIE._x/_y` = 786/654, на 4:3 — 740/675) и закрывает ноги игрока. У NHL 12 на том же месте по смыслу —
панель новостей вверху слева над списком. Сдвиг ролика целиком (`PushShort` на месте): 16:9 → (192, 184),
4:3 → (150, 205); внутренняя анимация выезда (`ACTIVE_POS_*`) не меняется. Проверено в игре.

## 4. Положение картинки игрока на экране

Ролик картинки — сцена 1280×720, картинка 600×760 стоит в (684, 6); он грузится в
`mcPlayerHolder.ph.cPlayer` (сдвиги < 1 px). Держатель (`playerAnimStage0`) по `ANIM_TYPE_1` за 30 с едет:

| Тип | Начало (x, y, масштаб) | Конец | Кадр на экране, левый край |
|---|---|---|---|
| 0 | (0, 0, 1) | (120, 0, 1) | 684 → 804 |
| 1 | (100, 0, 1) | (0, 0, 1) | 784 → 684 |
| 2 | (100, 50, 0,9) → **у нас (130, 50, 0,9)** | (180, 0, 1) → **у нас 40** | 716 → 864 → **746 → 724** |
| 3 | (100, 50, 0,9) | (−150, 0, 1) → **у нас тип 1** | 716 → 534 |

В конце цикла `ph` проигрывает 120 кадров «наезда» (до ×3,65 с затуханием) и выбирается следующий игрок.
Значит: левый и верхний края кадра всегда видны (обрез там — недопустим), нижний всегда за экраном,
правый — за экраном, кроме типа 3 (кадр уезжает до x = 534, правый край на 1134) — поэтому тип 3 → 1
(`PushByte 3` → `PushByte 1`); у типа 2 к концу на экране оставалась треть кадра — `POS_NEXT` 180 → 40
(`PushShort`), а в начале при масштабе 90 % правый край кадра выходил на экран — старт x 100 → 130
(`PushByte`). Низ экрана (y ≳ 605) закрыт строкой помощи и бегущей строкой.

## 5. Игроки: tools/menuplayers.py

```bash
V=game/work/menu12/venv/Scripts/python.exe          # Pillow, numpy, scipy, rembg[cpu] (onnxruntime)
$V tools/menuplayers.py slots                        # места фона: ASSET_ID, цвет колец, анимация
$V tools/menuplayers.py plan SPEC.json               # 8 обязательных + 21 лучший по рейтингу базы → spec
$V tools/menuplayers.py scout SPEC.json --max 60     # кандидаты фото → лист players/scout/<место>_<id>.jpg
$V tools/menuplayers.py try SPEC.json --slot 8 --cand 0,10,14   # примерка «на экране меню»
$V tools/menuplayers.py pick SPEC.json               # автоматический выбор (правила ниже)
$V tools/menuplayers.py build SPEC.json OUTDIR       # картинки, легенды, фон с цветами
$V tools/menuplayers.py screens OUTDIR               # лист «на экране меню» с подсветкой обрезов
```

- **Список** (`plan`): Кучеров, Макдэвид, Маккиннон, Квинн и Джек Хьюзы, Макар, Шестёркин, Василевский + лучшие
  по `ea.ovr` из `players.json` конвейера составов (клуб — по нему же, т. е. по установленной базе).
  Фамилия — последнее слово имени, у братьев Хьюз — «Q. HUGHES»/«J. HUGHES» (`label` в spec).
- **Фото** (`scout`): экшн-кадр НХЛ из кэша конвейера, свои файлы `players/src/<id>/`, категории Commons
  (с подкатегориями) и картинки статей NHL.com с тегом игрока (API `forge-dapi.d3.nhle.com/v2/content/
  en-us/stories?tags.slug=playerid-<id>`; превью `media.d3.nhle.com/image/private/t_ratio16_9-size40/…`,
  оригинал — `t_q-best/…`, до 2568–3000 px). На каждого — быстрая вырезка по превью и оценка: высота
  фигуры (по оригиналу), обрезы краем фото, «чужие» силуэты.
- **Правила отбора** (`pick`, лист `screens`): игрок крупно, в игровой позе, целиком или по пояс; без
  соседей, ворот и рекламы; не сверху; резко; форма нынешнего клуба (берутся свежие статьи NHL.com); без
  обрезов, видимых на экране: силуэт (с клюшкой) не касается левого и верхнего краёв кадра, срез фото
  снизу/справа уводится за край кадра; на листе видимые обрезы — пурпурным.
- **Вырезка** — rembg (модели в `game/work/menu12/models`): для оценки кандидатов — быстрая
  `isnet-general-use` (~1 с), для окончательной — `birefnet-general` (~25 с на CPU): isnet у вратарей цепляет
  сетку ворот, буквы рекламы и борт, BiRefNet — нет. Из найденного остаётся крупнейший силуэт и всё, что его
  касается (клюшка, перчатки); `focus` — участок фото до вырезки.
- **Выбор фото** — автоматический `pick` ошибается на картинках статей NHL.com (тренеры, сборные, пары
  игроков, коллажи), поэтому в итоговом списке все 29 мест выбраны вручную по листам scout и примерке `try`
  и закреплены (`"photo_locked": true`): игрок нынешнего клуба, в игровой позе, один, не сверху.
- **Кадр** 600×760: масштаб по «телу» (без тонкой клюшки), высота ~724 px (по пояс — 700). По горизонтали —
  по «ядру» (туловище и ноги без вытянутых рук и клюшки): его центр — на 42 % ширины кадра, видимой в худший
  момент проезда (тип 0 — 476 px в конце, тип 1 — 496 px в начале, тип 2 — 556 px в конце); до 35 % ядра
  может уходить за край экрана, голова — всегда на экране с запасом 80 px. Левый и верхний края кадра силуэт
  не трогает — кроме строк ниже 604, которые всегда под полосами внизу экрана (туда клюшка и перчатки могут
  уходить за край кадра незаметно). Тон под арену NHL 12 — сверено с её
  картинками (средняя яркость силуэта 0,26–0,55): локальный контраст, экспозиция ×0,86, S-кривая, светлые
  ≤ 0,94, насыщенность ×0,85, «свет сверху» (к низу кадра темнее до −22 %), холодные тени; «размытая» копия
  — светлые горизонтальные шлейфы + чёткий игрок.
- **Фамилия** — шрифт пунктов меню NHL 12 (её `EAHelveticaNeueHv-Mod.ttf`, DIN), наклон, «металл» с
  бликом и царапинами, отражение, 62 %; позади игрока, место в верхней части кадра подбирается, чтобы
  силуэт её меньше закрывал. Легенды — картинки NHL 12 + фамилия в их текстуре.
- **Сборка**: шаблон — файлы места 8 NHL 12 (тот же ролик с частицами льда), меняется только текстура
  DXT5 1024×1024; цвета колец — основной цвет клуба из `exhibitionteams` (слишком тёмный/серый — второй,
  светлота ≥ 0,42), `PushLong` в байткоде фона на месте.

## 6. Сборка, установка, откат

```bash
cd /s/Claude/megarohas_nhl13
V=game/work/menu12/venv/Scripts/python.exe
$V tools/menuplayers.py build game/work/menu12/players/spec.json game/work/menu12/build/players
python tools/menu12.py build game/work/menu12/out/nhl12 --players-dir game/work/menu12/build/players
python tools/menu12.py build game/work/menu12/out/tint-245C99 --players-dir game/work/menu12/build/players --tint 245C99
bash game/work/menu12/install-menu12.sh            # или: install-menu12.sh tint-245C99
bash game/work/menu12/uninstall-menu12.sh          # откат: прежние файлы из game/work/menu12/backup
```

- Ставится в `cache:` (`game/userdata/cache/guest/`): фон главного меню, `menu.big`, `main.big`,
  58 картинок игроков, 14 картинок легенд. Прежнее (фон «b» главного меню из
  [fe-background.md](fe-background.md)) сохраняется в `game/work/menu12/backup/` и возвращается откатом.
- `install-ahl32.sh` и `install-art.sh` ставят вариант фона «b» в те же папки — теперь они пропускают
  файлы из `game/work/menu12/installed-menu12.txt`, то есть меню NHL 12 не затирают.
- Варианты: `out/nhl12` — арена как в NHL 12 (тёмно-серая, холодный лёд), **ставится по умолчанию**;
  `out/tint-245C99` — серые текстуры арены тонированы в приглушённый синий #245C99 (как фон «b» остальных
  меню), держится готовым.

## 7. Формат Apt — дополнения к fe-background.md

- **Байткод** — как SWF (AS1/AS2) + команды EA (номера — как в OpenSAGE): `0x70` PushThis, `0x71`
  PushGlobal, `0x59/0x5A` PushZero/PushOne, `0x5B…0x5E` CallFunc/Method(Pop), `0xA1` PushString,
  `0xA2/0xA3` PushConstant (байт/слово, через ConstantPool), `0xAE` PushValueOfVar, `0xAF`
  GetNamedMember, `0xB0…0xB3` CallNamedFunc/Method(Pop), `0xB4` PushFloat, `0xB5` PushByte, `0xB6`
  PushShort (знаковый), `0xB7` PushLong, `0xB8` BranchIfFalse, `0xB9` PushRegister; `0x58 xx` — встречается
  только как «58 4E» перед GetNamedMember и ничего не делает. Аргументы выровнены по 4 только у
  ConstantPool, PushData, ветвлений, SetRegister, DefineFunction(2), GotoFrame(2), Get/SetString*,
  PushString; у байтовых, PushShort, PushFloat, PushLong и GetURL2 — без выравнивания.
- **DefineFunction2**: имя, число параметров, `(регистров << 16) | флаги` (флаги как SWF: 0x01 this,
  0x04 arguments, 0x10 super, 0x40 _root, 0x80 _parent, 0x100 _global — регистры по порядку с 1),
  указатель на пары (регистр, имя), длина тела, 8 байт `98 76 54 32 12 34 56 78`, тело.
- **Символы**: Image 0x14 байт (+0x10 номер текстуры = номер символа, запись BIGF номер+1), Shape 0x24
  (+0x08 Image, +0x10 рамка, +0x20 номер геометрии = номер символа), Sprite 0x1C (+0x10 кадров,
  +0x14 таблица кадров); EditText: +0x10 рамка, +0x20 Font, +0x28 цвет, +0x2C кегль, +0x3C текст; Font:
  +0x10 имя. Пересадка (`feapt.py graft`) дописывает символы в конец Apt Data, копирует таблицу символов
  (и при новом имени — экспорта) туда же, геометрию и текстуры — новыми записями.
- Проверка дизассемблера: все 27 153 ролика fe обеих игр, 12 056 блоков кода, без ошибок.

## 8. Не сделано / ограничения

- Ролики «телевизора» и динамические сообщения EA на стене студии NHL 13 на главном меню не показываются
  (их показывал фон NHL 13); `Refresh` фона после выбора любимой команды ничего не делает.
- Панель «NHL 13 Features» и полосы внизу — от NHL 13 (закрывают ноги игроков); место списка — NHL 13.
- Арены других режимов NHL 12 (Play Now, плей-офф, Winter Classic) не переносились — у NHL 13 там синий фон.
- Картинки игроков — пресс-фото и Commons для личного использования; в git — только код.
