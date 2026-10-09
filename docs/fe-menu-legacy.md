# Главное меню NHL 12 в NHL Legacy

Разбор и сборка от 08.10.2026 (помощник menu агента legacy-data). Инструмент —
[tools/menu12_legacy.py](../tools/menu12_legacy.py). Он берёт функции `menu12.py`, `feapt.py` и
`menuplayers.py` и не меняет их. Как то же сделано для NHL 13 — [fe-menu.md](fe-menu.md). Перенос модов
в Legacy — [legacy-data.md](legacy-data.md). Формат роликов — [fe-background.md](fe-background.md).

Собранное лежит в `game/work/legacy-data/menu/` и `game/work/legacy-data/out/`, вне git.
**Проверено в игре** 08.10.2026, 23:05–23:10 (legacy-data, Release legacy-port, снимки `game/work/legacy-data/ingame/t5-*`): главное меню грузится, игроки сменяются, кольца в цвет клуба, плашка NHL 12 с кнопкой A и ►; вход и выход — PLAY, Play Now → Select Teams → назад, CUSTOMIZE → назад. Мелочь: в подменю на 9 пунктов (CUSTOMIZE) подзаголовок наезжает на потускневшую табличку LEGACY EDITION под кубком (исправлено 09.10, §9). Остальное из §5 (хаб Be a GM, меню паузы, Scenario Mode, легенды) не смотрели.

## Коротко

- Фон главного меню NHL 12 (арена, большой игрок, кольца света) ложится на фреймворк Legacy без правки
  кода игры. Загрузчик фонов, `ModeTransitionManager` и `MovieLoader` у Legacy те же, что у NHL 13;
  у `ModeTransitionManager` добавлен только `SkipEval`. Нужны те же две правки байткода `bg_edits`.
  Фон берётся из сборки menu12 готовым. Кольца перекрашены по базе Legacy: 27 из 29 мест.
- Картинки игроков и легенд (72 файла) — из сборки menu12, байт в байт.
- Список меню — код Legacy со своими заголовками разделов, картинками пунктов и метками «New».
  Менять код не нужно: меняется вид.
  - Плашка выделения — гибрид: полоса и косые края NHL 12 плюс кнопка A, метка «New» и стрелка
    подменю от Legacy.
  - Пункты 34/25, ряды 28/45, без затухания пунктов.
  - Кегль задаётся в `main.big`: 22 → 34.
- Левая панель Legacy с кубком, заголовки «FEATURED» и панель описаний внизу справа остаются Legacy.
  Их место в разметке Legacy своё, поэтому переносить их как в NHL 13 нельзя (§3).

## 1. Что у Legacy вместо главного меню

Снимок оригинала: `legacy-port/out/shots/rel_02.png`.

| Часть | NHL 12 | NHL 13 | NHL Legacy |
|---|---|---|---|
| Фон `cache:\fe\ion\game\background\nhlmainmenubackground.big` | 557 КБ, Apt 1:7:4: арена, большой игрок, кольца | 846 КБ, 1:8:4: студия с телевизором и карточками игроков | 840 КБ, 1:8:4: студия NHL 13 без карточек. На ТВ матч любимой команды, справа щит НХЛ, слева водяной знак клуба. Плюс `_HideComponents`/`_UpdateComponents` |
| Список `boot:\fe\ion\game\components\menu.big` | mainMenuNew из `fw` | 44 КБ, 99 символов | 114 КБ, 132 символа. Левая тёмная панель `mcBGPanel` и картинка пункта `mcFeatureImage` (в корне — кубок с логотипом). Заголовки разделов, «New»/«Locked», значок паков, подзаголовок-хлебные крошки |
| Плашка выделения `selectorBG` | металл, косые края, ширина по тексту | тёмная полоса, ширина по тексту (анимация) | светлая полоса **фиксированной** ширины `HIGHLIGHT_WIDTH` 327. Внутри кнопка A, метка `mcNewIcon`, стрелка `mcMenuArrow`. Правый край код не двигает |
| Кегль пунктов (`main.big`, `GetCustomMenuOptions`) | 34 / 25 (`MenuOptions`) | 24 у всех | 22 у всех |
| Невыделенные (`MenuItem.UNHIGHLIGHTING_SCALE`) | 25/34 | 0,9 | 0,8, ширина ≤ 292 (подменю — 266) |
| Ряды (`Menu.ROW_SIZE_*`) | 28 / 45 | 28 / 45 (`mRowSizeUnhighlighted`/`Highlighted`) | 23 / 40 |
| Затухание пунктов | нет | нет | 80 − 10 на каждый ряд от выделенного, не меньше 30 |
| Внизу | панель новостей (вверху слева) / бегущая строка | панель «NHL 13 Features» + строка | панель описаний пунктов (`nhl_proshopnotification.big`, 19 КБ). Стоит внизу справа: 16:9 — (737, 607), 4:3 — (707, 650). Её подвал «LT RT 1/1 · RS Scroll Text» встроен в полосу помощи: бегущая строка берёт `SetTopRightPadding` от `_x` панели |

«FEATURED» в главном меню Legacy — не отдельная панель, а **заголовок раздела** в данных меню. В
`MenuItem` для него есть ветка `IsHeader`: «EA HelveticaNeue Med» 26, #1A9AEF, прозрачность 40.

Главное меню Legacy: PLAY, COMMUNITY, CUSTOMIZE, затем заголовок FEATURED и под ним HOCKEY ULTIMATE
TEAM, LIVE THE LIFE, NHL™ 94 ANNIVERSARY MODE.

## 2. Фон NHL 12 во фреймворке Legacy

Сравнение — `feapt.py dis` по роликам трёх игр. Выкладки — в `game/work/legacy-data/menu/an/`.
Индекс констант всех 27 262 роликов fe Legacy (как `feapt.py index`, собран разово) —
`menu/index/legacy.json`.

- **Фреймворк** (`commonloader.big`). `cafe.core.MovieLoader` — тот же код, что у NHL 13.
  `ModeTransitionManager` — тот же плюс `SkipEval`. `ion.background.BaseBackground` тоже тот же: `Init`
  ставит `IsLoaded`, переход начинается после загрузки, `ModeTransitionStarted` приходит уже
  загруженному фону. Значит, нужны те же `bg_edits`: слушатель → `mDelay`, `ClearAllAnimations` в
  `Shutdown`.
- **Грань `MENU`** и строки `_global.BACKGROUND[…]` в `main.big` — те же, что у NHL 13.
- **Что фон NHL 12 берёт у игры** — то же есть и в Legacy:
  - `ION_Camera.IsWideScreen`, `ION_NHLBeAPro.IsLegendsEnabled`, `ION_Platform.GetRandomNumber` —
    имена есть в образе `default.xex` Legacy, ролики Legacy их вызывают;
  - `gMTM.Add/RemoveEventListener`, `GetTransitionDirection`, `gAnimator`;
  - импорт `stdControls:ImageLoader` (его импортирует и фон Legacy).
- **Что Legacy зовёт у фона** (`GetCurrentBackground()`). Зовут `classloader`, `nhl_proshopnotification`,
  `selectfavouriteteamscreen`, `custom_profile`, `scenariodemovideoscreen`. Методы:
  `PlayMovieOnTvScreen`, `StopMovieOnTvScreen`, `GetIsShowingDynamicMessage`, `OnServerMessageUpdated`
  (с проверкой на null), `Refresh`, `GetAnimateOutDelayTime` (undefined → 0). У фона NHL 12 этих
  методов нет. Вызов несуществующего метода в AS2 ничего не делает, как и в NHL 13.
- **Что пропадает**:
  - телевизор: матч любимой команды, рекламные ролики, сообщения «Press Y to watch» в панели описаний
    (панель добавляет их только при `PlayMovieOnTvScreen != null`);
  - водяной знак клуба.
- **Режим «Scenario Mode»** (`TXT_SCENARIO_MODE` → экран `SCENARIO_DEMO_VIDEO`). Экран невидимый: он
  запускает вступительный ролик на телевизоре фона и ждёт его конца (`EVENT_VIDEO_IS_INACTIVE`) или
  кнопки A. С фоном NHL 12 ролика нет — экран ждёт **A**, затем идёт в `SCENARIO_MODE.LEGACY_INIT`.
- **`osdk.adaptors.SocialNetworksInterface`**. Фон Legacy экспортирует этот класс, но его определяют ещё
  72 ролика, в том числе `classloader` и `globalframework` из `boot.big`. Без фона Legacy класс
  остаётся.
- **Картинки игроков** `artAssets/backgrounds/mainMenuPlayers…/nhl<N>`. В архивах Legacy их нет (в NHL 13
  были). Свободные файлы `cache:` порт берёт раньше архива, и новые пути тоже (так работают портреты
  новых игроков). Ставятся все 72 файла.
- **Кольца света**. Цвет — основной цвет клуба игрока места, `menuplayers.ring_color`. Таблица —
  `exhibitionteams` базы Legacy `out/db/nhlng.db`: строки НХЛ 0…31 те же, SEA 30, VGK 31. Клуб места
  берётся из `game/work/menu12/players/spec.json`.
  - Сверка: цвет в фоне menu12 = цвет того же клуба по базе NHL 13. Иначе — предупреждение «!!».
  - Палитра Legacy другая почти у всех клубов. Примеры: TBL #0D73C9 → #0069D6, COL #CB0B4F → #D60058,
    MIN #B33B47 → #D0122A, DAL #1CBA7D → #00D68D.
  - У VGK цвет тот же, поэтому правок 27 из 29.
  - Легенды (7 мест) — цвета NHL 12, как в NHL 13.

## 3. Список меню: вид NHL 12 на коде Legacy

Файлы menu12 от NHL 13 в Legacy ставить нельзя: код меню Legacy ждёт своих символов и методов.
Правки сделаны на оригиналах Legacy (`boot.big`).

### Плашка-гибрид (`menu.big`, символ 142, экспорт `selectorBG` → 142)

1. `feapt.graft`: `mainMenuNew` NHL 12, символ 69, пересажен с графикой. Новые символы 132…141, три
   геометрии и три текстуры 8888 — новыми записями BIGF. Текстуры 8888 у Legacy в ходу, например
   `stdhelppopup.big`.
2. Новый спрайт 142 — копии записей PlaceObject:

   | Глубина | Что | x, y |
   |---|---|---|
   | 1 | `center` — полоса NHL 12 252×39 (код растягивает до 327) | 0, −11 |
   | 2 | `right` — косой край NHL 12 | 327, −11 |
   | 3 | кнопка A Legacy (импорт `platform/proxy/art/A`) | 14, 7 |
   | 4 | `left` — косой край NHL 12 | −24, −11 |
   | 5 | `mcNewIcon` Legacy (метка «New»/«Locked»/награда HUT) | 249 (код ставит 327), −8 |
   | 13 | `mcMenuArrow` Legacy (стрелка подменю) | 318 (код ставит 317), 7 |

   - Полоса NHL 12 стоит там же, где полоса Legacy (0…327), косые края — снаружи. Код Legacy двигает
     только `center._width`, `mcNewIcon._x` и `mcMenuArrow._x`, поэтому правый край поставлен на
     327 сразу.
   - На экране полоса идёт от левого края панели Legacy до её правого края (418). Косой правый край
     выходит за панель на 24 px — как у NHL 12, где плашка висит над ареной.
3. Высота подобрана по снимку NHL 13 с меню menu12: тот же шрифт и то же поле текста. Прописные кегля 34
   — с 10 по 30 px от верха поля. Видимая часть полосы NHL 12 — строки 0…37 из 39, текст по её середине.
   - Поле пункта у Legacy на 11 выше, чем у NHL 13: `txtItemHighlight` (2, −9) против (2, 2), рамка
     поля −2. Отсюда y = −11.
   - Элементы Legacy сдвинуты на столько же, на сколько середина полосы: 0,5 → 7,5.
4. Старый `selectorBG` Legacy (символ 39) и пересаженный спрайт NHL 12 (141) остаются в ролике без ссылок.

### Константы (правки той же длины)

| Где | Что | Было → стало |
|---|---|---|
| `menu.big`, `MenuItem` | `UNHIGHLIGHTING_SCALE` | 0,8 → 0,735 (25/34) |
| `menu.big`, `Menu` | `ROW_SIZE_UNHIGHLIGHTED` / `ROW_SIZE_HIGHLIGHTED` | 23 / 40 → 28 / 45 |
| `menu.big`, `Menu` | `HIGHLIGHT_OFFSET` | 8 → 10 |
| `menu.big`, `Menu` | `TXT_ALPHA_START` / `TXT_ALPHA_DECREMENT` | 80 / 10 → 100 / 0 (`--keep-fade` — оставить) |
| `menu.big`, `Menu.SetFeatureImageFaded` | кубок с табличкой в подменю | цвет ×20 % → ×6 % (§9) |
| `main.big`, `GetCustomMenuOptions` | кегль четырёх форматов пунктов | 22 → 34 |
| `main.big`, `GetCustomMenuOptions` | тень выделенного | #FFFFFF → #DDDDDD |
| `main.big`, `GetCustomMenuOptions` | `mDisabledAlpha` | 30 → 50 |

- **`HIGHLIGHT_OFFSET`**. Сдвиг выделенного пункта вверх выровнял просветы вокруг полосы: снизу
  ~10 px, сверху ~11 px, между невыделенными рядами ~13 px. С 8 было бы 8 и 13.
- **Без затухания**. Невыделенные пункты, как в NHL 12, — 80 % (`mUnhighlightedAlpha` у всех трёх
  игр 80).
- **Длинные пункты**. Ширину выделенного код Legacy ограничивает 292 px (в подменю — 266) и сжимает
  текст пропорционально. «HOCKEY ULTIMATE TEAM» в 34 — 357 px, выделенный пункт ×0,82.
  «NHL 94 ANNIVERSARY MODE» — ×0,71, невыделенный — до 284 px.

### Что не тронуто и почему

- **Левая панель, кубок, картинки пунктов, заголовки, хлебные крошки** — от Legacy. Это компонент
  всех меню Legacy (подменю, пауза…). Как и в NHL 13, плашка и кегли меняются во всех списках.
- **Панель описаний** внизу справа. Её подвал — часть полосы помощи: `SetTopRightPadding` бегущей
  строки зависит от `_x` панели. Сдвиг панели, как в NHL 13, оторвал бы подвал. Панель закрывает
  низ картинки игрока: y 540…605 при x ≥ 735 (ниже 605 и так полосы).
- **Бегущая строка и полоса помощи** — Legacy.
- **Предпросмотр подменю** (`MenuPreview`): у Legacy выключен (`SHOW_PREVIEW_MENU = false`), его рамку
  не трогали.

## 4. Сборка, проверка, установка, откат

```bash
cd /s/Claude/megarohas_nhl13
python tools/menu12_legacy.py build                 # → game/work/legacy-data/menu/build и out/, список — menu/files.txt
python tools/menu12_legacy.py check                 # сверка (ниже)
game/work/menu12/venv/Scripts/python.exe tools/menu12_legacy.py mockup   # menu/mockup.png — примерный вид
# вариант арены «в нашем цвете» menu12: build --from game/work/menu12/out/tint-245C99
# после пересборки игроков в menu12 (их install-menu12.sh) — просто build ещё раз
bash game/work/legacy-data/install-legacy-data.sh @game/work/legacy-data/menu/files.txt     # при закрытой игре
bash game/work/legacy-data/uninstall-legacy-data.sh @game/work/legacy-data/menu/files.txt   # откат
```

- **Состав.** 76 файлов, 13 086 192 байт:
  - `fe/ion/game/background/nhlmainmenubackground.big` (557 536 байт);
  - `fe/ion/game/components/menu.big` (123 868, у оригинала 113 884);
  - `fe/ion/main.big` (99 380);
  - `fe/ion/artassets/backgrounds/mainmenu{players,playersblur,legends,legendsblur}/nhl<N>.big` — 29 + 29 + 7 + 7;
  - `fe/ion/game/background/nhlbluebackground.big` (3 720) — «цветной фон» без синей подложки на главном меню
    (§7, с 09.10.2026; `--no-underlay` — без него).

  Имена строчные, как в архивах Legacy. Журнал сборки — `menu/build/build.log`.
- **Своих файлов с такими путями в `out/` раньше не было.** В архивах Legacy есть только три ролика
  (фон, `menu.big`, `main.big`). При снятии игра снова возьмёт их из архивов, а картинок игроков у
  Legacy нет вовсе. Полная установка `install-legacy-data.sh` без частей ставит и эти файлы. Если меню
  не нужно — убрать их из `out/` по `menu/files.txt`.
- **`check` без игры.**
  - Каждый ролик разбирается целиком: `FeMovie`, все блоки кода через `feapt.Code`, BIGF собирается
    обратно байт в байт.
  - Фон против фона menu12 отличается только 27 словами `PushLong` цвета колец; `bg_edits` на месте.
  - Игроки байт в байт как у menu12.
  - `menu.big`: в старой части Apt Data отличаются только число и указатель таблицы символов, экспорт
    `selectorBG` и шесть констант. Новое — в конце (+2 330 байт). Старые 55 записей BIGF те же. У новых
    символов есть геометрия и текстуры. `check` печатает разбор плашки 142 и `dis` правленых мест.
  - `main.big` отличается только шестью правками шрифта пунктов.
- **`mockup`.** Плашка из текстур NHL 12 по координатам символа 142 и пункты 34/25 по раскладке
  `Menu.UpdateMenuItemPosition`, поверх левой панели со снимка Legacy. Это сверка геометрии, не снимок
  игры. Шрифт подогнан по замеру NHL 13; заголовок нарисован приблизительно.

## 5. Что проверить в игре

1. **Главное меню.**
   - Арена NHL 12 с игроком: появляется и меняется ~раз в 32 с.
   - Кольца — цвет клуба: Кучеров — синие, Макдэвид — оранжевые.
   - Игрок не гаснет сразу (`bg_edits`).
   - Телевизора и щита НХЛ нет.
   - Слева панель Legacy с кубком.
2. **Плашка.**
   - Металлическая, косые края, текст по середине.
   - Кнопка A на полосе. Стрелка ► у пунктов с подменю (PLAY).
   - Метка «New»/«Locked» у выделенного, если есть.
   - Высота текста и просветы между пунктами; длинные пункты (HOCKEY ULTIMATE TEAM, NHL 94 ANNIVERSARY
     MODE) сжаты, но не вылезают за панель.
   - Заголовок FEATURED.
3. **Подменю PLAY и других.**
   - Подзаголовок, крошки, затухание кубка.
   - Длинные списки не уходят за верх экрана. Меню хаба Be a GM (9 пунктов): выше на ~45 px — не
     наезжает ли на панели хаба.
   - Возврат назад.
4. **Переходы.**
   - Вход в Play Now → выбор команд → назад в главное меню.
   - Матч → выход в меню: фон грузится заново, без падений и чёрного экрана.
   - Пауза в матче (`Menu.Init` упоминает `SCREEN.PAUSE.MENU`): если это тот же компонент — плашка и
     кегли новые.
5. **Панель описаний внизу справа.** Текст пунктов, листание LT/RT и RS, подвал на месте.
6. **Scenario Mode.** Экран вступительного ролика: ролика нет, нужно нажать A — дальше режим.
7. **Легенды** (если `IsLegendsEnabled`). Гретцки и другие с фамилиями.
8. **4:3** (если есть). Плашка и список на своих местах.

**Откат:** `uninstall-legacy-data.sh @game/work/legacy-data/menu/files.txt`. Можно снять по частям:
только список — `fe/ion/game/components/menu.big` и `fe/ion/main.big`, только фон — `fe/ion/game/background`.
Фон и список друг от друга не зависят.

## 6. Ограничения и заметки

- Нет телевизора: ролики, сообщения «смотреть» и матч любимой команды на стене не показываются. Нет
  `Refresh` после смены любимой команды. В NHL 13 так же.
- Панель описаний закрывает ноги игрока в правом нижнем углу.
- Ряды 28/45 увеличивают высоту длинных списков (+5 px на ряд). Список растёт вверх от y ≈ 574. При
  ~20 пунктах его верх ушёл бы за экран (у Legacy — при ~25). На снимках самый длинный список — меню
  хаба Be a GM, 9 пунктов: с рядами 28/45 его верх на ~45 px выше, чем у Legacy.
- **`feapt.py dis` показывает `PushByte` без знака, а команда знаковая.** Компилятор пишет 252 через
  `PushShort` (`MINMUM_HIGHLIGHTED_LENGTH`), а `DIRECTION_IN = 255` — это −1. Поэтому в `dis` у Legacy
  `SelectorBG {_x: 227}` — это −29, `Glint {_x: 228, _y: 245}` — (−28, −11),
  `MenuItem.HIGHLIGHT_OFFSET = 228` — −28. `menu12_legacy.py` читает `PushByte` со знаком.

## 7. Синяя подложка при входе в главное меню (09.10.2026, legacy-fe)

Замечание пользователя: при загрузке главного меню сначала видна синяя подложка, на неё наезжает
тёмная арена, и пока арена едет, сверху какое-то время ещё видно синее.

**Причина.** Под всеми меню лежит «цветной фон» `game/background/NHLBlueBackground`
(`boot:fe/ion/game/background/nhlbluebackground.big`, у Legacy и NHL 13 побайтно один,
[fe-background.md](fe-background.md) §2, §10). В нём два слоя: подложка `mcColor` — заливка
**#0A09E1** 1480×1281 — и над ней `mcBackground` — у Legacy фото пустой арены (`NHLBlueBackgroundComponents`,
`cacheboot`). Слушатель `ModeTransitionStarted` (`_AnimateBlueBackground`) при входе в грань `MENU`
сжимает `mcBackground` до `INACTIVE_*`: 30 % в точке (166, −73) от `BASE` (656, 366). Там стоит
телевизор студии Legacy, и фото «уезжает» в него. При выходе из `MENU` фото возвращается в `ACTIVE_*`
(0, 0, 100 %). У фона NHL 12 телевизора нет. Сжатие открывало синюю подложку на весь экран, пока арена
NHL 12 проявлялась (`_alpha` 0 → 100 за `m_speedZoomIn` 90 кадров) и въезжала (переход граней MTM).
Тонкая полоса сверху держится, пока лёд и крыша NHL 12 доезжают на место (600 кадров). По снимкам
`game/work/legacy-fe/shots/before-*`: при входе после Press Start синее занимает до 62 % экрана
(+0,3 с), при возврате из Play Now — до 27 %; полоса сверху видна ещё 5–7 с.

**Правка** (`menu12_legacy.py build`, шаг «подложка», файл
`fe/ion/game/background/nhlbluebackground.big` в `out` и `menu/files.txt`):

| Что | Было → стало |
|---|---|
| `INACTIVE_X_POS` (`PushShort`) | 166 → 0 |
| `INACTIVE_Y_POS` (`PushByte`, со знаком) | −73 → 0 |
| `INACTIVE_X_SCALE`, `INACTIVE_Y_SCALE` | 30 → 100 |
| заливка подложки `mcColor` (Shape 1, запись BIGF 2) | #0A09E1 → #07080A |

`INACTIVE` = `ACTIVE`: на главном меню фото-арена Legacy остаётся на весь экран, и арена NHL 12
проявляется поверх неё, как поверх любого другого меню. Анимации «зум» в `_ActivateBlueBackground`/
`_DeactivateBlueBackground` идут между одинаковыми значениями и ничего не двигают. Подложка почти чёрная —
на случай, если её что-то всё же откроет. Остальное в ролике побайтно то же: `check` сверяет Apt Data,
геометрию и записи BIGF с оригиналом Legacy.

**Проверено в игре** (09.10.2026, своя копия userdata, снимки `game/work/legacy-fe/shots/after-*`, лист
`game/work/legacy-fe/underlay-before-after.png`). Ни на одном кадре нет синего:
- вход в главное меню после Press Start;
- PLAY → Play Now → Select Teams → назад (диалог «Yes») → главное меню;
- CUSTOMIZE и назад; PLAY и назад.

В переходах между подменю синего не было и раньше: там грань та же, `MENU`. Поставлено пользователю
`game/work/legacy-fe/install-legacy-fe.sh underlay`; бэкап — `game/work/legacy-fe/backup-*-underlay`, откат —
`uninstall-legacy-fe.sh underlay`.

Если для Legacy когда-нибудь поставят вариант фона из `game/work/legacy-data/fe/variants/` (`nhl13-*`,
`legacy-gray`), в нём свой `nhlbluebackground.big` с прежними `INACTIVE_*`. Синее (или серое) тогда
вернётся — те же четыре константы надо поправить и там. В NHL 13 с menu12 то же устройство: подложка
#0A09E1 перекрашена вариантом «b» в приглушённый синий и тоже открывается на входе в главное меню.

## 8. Пункты меню: без онлайна, с EXIT (09.10.2026, legacy-fe)

Решение пользователя: скрыть онлайн-пункты, оставить офлайн-режимы, CUSTOMIZE и настройки, а вместо
«SIGN IN TO EA» поставить **EXIT** — выход из программы. Инструмент — [tools/menuitems_legacy.py](../tools/menuitems_legacy.py).
Разбор всех пунктов и вариантов — `game/work/legacy-fe/menu-items/` (`menu-tree.md` — полное дерево, `mechanism.md` —
устройство).

**Как заданы пункты.**
- Все пункты — операторы `objMainMenu.<массив>.push({name: …, …})` кадра 0 ролика
  `boot:fe/ion/game/menus/mainmenuitems.big`: 161 оператор, 39 массивов. Свободный файл `cache:` игра берёт
  раньше архива.
- `name` — это и ключ подписи (`ltxt`), и ключ `switch` в `objMainMenu.MenuCallback`. Подменю — прямая ссылка
  на массив. Номер пункта нужен только курсору и стеку возврата.
- Список и логика — `MenuDataManager` (`classloader.big`) и `Menu`/`MenuItem` (`menu.big`). Код игры
  добавляет только категории настроек и легенд.
- Панель описаний внизу справа с пунктами не связана: её 5 страниц — строки
  `TXT_OFFLINE_DYNAMIC_MSG_TITLE/BODY_0…4` из exe.

**Скрытие — пункт не добавляется.** Имя метода `push` (PushWordConstant #396) меняется на `concat` (#591).
Объект пункта строится, `Array.concat` ничего не меняет, клип пункта не создаётся. Правка — 2 байта той же
длины. Курсор и возврат назад считаются по готовому массиву, «дыр» нет. Флаг `isHidden` не годится для HUT:
в конце загрузки игра ставит курсор на `TXT_HUT` по имени (`IS_AUTO_SELECT_HUT_ON_BOOT`,
`SetHighlightedMenuItem` видимость не проверяет). Без пункта в массиве поиск его не находит, и курсор
остаётся на PLAY.

| Меню | Скрыто | Осталось |
|---|---|---|
| корень | приглашение в онлайн-матч, COMMUNITY (Player Hub, Leaderboards, Lobby; My Highlights есть в Media Hub), HOCKEY ULTIMATE TEAM, Rivalry / Game of the Week | PLAY, CUSTOMIZE, FEATURED: LIVE THE LIFE, NHL™ 94 ANNIVERSARY MODE, **EXIT** |
| PLAY | HOCKEY ULTIMATE TEAM, ONLINE (GM Connected, Versus, EASHL, Arena, Team Play, Online Shootout) | PLAY NOW, QUICK MODES, CAREER, TOURNAMENTS |
| QUICK MODES | Rivalry | NHL™ 94, MOMENTS LIVE (сценарии с диска), WINTER CLASSIC, TRAINING (практика, буллиты, обучение) |
| CAREER, TOURNAMENTS | — | Live the Life, Be a GM, (Be a Legend), Season; Playoff, Tournament, Battle for the Cup |
| CUSTOMIZE | OFFER CODE ENTRY (коды Xbox Live) | 8 пунктов |
| EA SPORTS™ MEDIA HUB | CUSTOM MUSIC, CUSTOM MUSIC TUTORIAL (музыка с жёсткого диска Xbox — в порте её нет; `--keep-custom-music` — оставить) | MY HIGHLIGHTS, EA SPORTS™ TRAX |
| ROSTER MANAGEMENT | DOWNLOAD ROSTERS | 5 пунктов |
| SETTINGS | ONLINE SETTINGS | Hospitality, Celebrations, Controller, Video Calibration, [категории настроек из кода], Credits |

Меню режимов (хабы Be a GM, сезона, плей-офф, турнира, Live the Life) и паузы — отдельные ролики. Онлайна в
них нет; GM Connected (`mud.big`) и HUT (`cards/futmenuitems.big`) без своих пунктов недостижимы.

**EXIT.** Пункта «Sign in to EA» в меню Legacy нет. Колбэк `OSDK_SIGN_IN_EA` описан в `zoneonlinemain.big`,
но ни в один массив не попадает. EXIT — новый пункт `{name: "XboxLiveMarketplace", screenID: null}` в конце
корня. Для этого имени в `MenuCallback` уже есть ветка: она зовёт родную
`ION_GameSetup.ShowMarketplaceUI(EA_ZONE.gControllerIDCurrentScreen)`. Больше её не зовёт ни один из 27 262
роликов fe.
- Корень переписан участком той же длины 0x44F7…0x4565: копии байт операторов LIVE THE LIFE и NHL 94 (без
  указателей и переходов), новый пункт (22 байта), заполнитель PushZero/Pop.
- Подпись — `ltxt("XboxLiveMarketplace")`. В локализации у ключа `XboxLiveMarketPlace` (регистр игра не
  различает) текст «Xbox Live Marketplace» → «Exit». Правка через `locdb put` — своя строка в конце пула,
  чужие ключи с тем же текстом не трогаются. На экране — прописными.
- Действие — в exe (агент legacy-port): обёртка `ShowMarketplaceUI` 0x832EFE28, регистрация в 0x833019C8
  (natives GameSetup). При cvar `nhl_menu_exit = true` программа закрывается, как от крестика окна, в лог
  пишется «[nhllegacy] menu exit (ShowMarketplaceUI)».
- **Без перехвата EXIT — ловушка** (проверено на сборке без него). Родная функция доходит до заглушки
  `XamShowMarketplaceUI` порта («STUB» в логе), а та возвращает успех. Ветка меню считает, что открылся
  системный UI магазина, прячет список и ждёт его закрытия. Список больше не возвращается, остаётся закрыть
  окно. Попап «нужен вход» бывает только при ответе false. Поэтому файлы этого раздела ставятся **только
  вместе с exe legacy-port**, где есть перехват. При `nhl_menu_exit = false` перехват должен отвечать false
  (попап и возврат в меню) — договорено с legacy-port.

**Проверено в игре** (09.10.2026, 06:22–06:35, своя копия userdata; снимки `game/work/legacy-fe/shots/menus-before/`,
`menus-after/`, лист `game/work/legacy-fe/menu-before-after.png`):
- Все подменю открываются и закрываются, курсор при загрузке — на PLAY, подзаголовки и панель описаний
  работают.
- До правки онлайн-пункт (Community → View Player Hub) давал попап «You must be signed in to Xbox Live and
  the EA servers…».
- Play Now → SEA–VGK → Select Jerseys → назад → главное меню — без сбоев.
- EXIT с exe legacy-port (`--nhl_menu_exit=true`): «[nhllegacy] menu exit (ShowMarketplaceUI): closing like the
  window close button» → «Window closing, shutting down…» → «Title terminated» за 0,2 с.

**Панель описаний** внизу справа листает 5 страниц из exe (`TXT_OFFLINE_DYNAMIC_MSG_TITLE/BODY_0…4`).
Страницы 0–2 рекламировали онлайн (EASHL Seasons, HUT Online Seasons, GM Connected). По решению
пользователя они переписаны на офлайн-режимы меню (`PANEL` в инструменте; `--keep-panel` — оставить).
Длина — не больше оригиналов:

| Стр. | Было | Стало |
|---|---|---|
| 0 | Features — EASHL Seasons | Be a GM — «Run your favorite franchise in a 32-team NHL from the 2026/27 season. Sign free agents, make trades and draft your next superstar.» |
| 1 | Hockey Ultimate Team — HUT Online Seasons | Play Now — «Jump straight into a game with any of the 32 NHL teams, including the Seattle Kraken and Vegas Golden Knights, with 2026/27 rosters. Play against the CPU or a friend.» |
| 2 | GM Connected | Battle for the Cup — «Battle for the Cup is one playoff series for the championship against a friend or the CPU. Pick any two teams and play for the Stanley Cup.» (первая фраза — строка EA `TXT_HEAD_TO_HEAD_MODE_NEW`) |

Страницы 3 (Enforcer Engine) и 4 (Live the Life) — прежние.

**Сборка, установка, откат.**

```bash
python tools/menuitems_legacy.py build      # → game/work/legacy-data/menu-items/build и out; список — menu-items/files.txt
python tools/menuitems_legacy.py check      # разбор: ролик целиком, отличия от оригинала — только правки, что в массивах
python tools/menuitems_legacy.py list [FILE.big]   # все пункты: номер, имя, подпись, смещение push
bash game/work/legacy-fe/install-legacy-fe.sh menu  # при закрытой игре, с бэкапом, ТОЛЬКО вместе с exe legacy-port; откат — uninstall-legacy-fe.sh menu
```

`--exit before-featured` — EXIT перед FEATURED, `--exit none` — без EXIT; `--keep ИМЯ,…` — оставить пункты
(например `TXT_COMMUNITY`); `--keep-panel` — прежние тексты панели описаний. Локализация в сборке — из `out` (база legacy-data); при пересборке локализации
legacy-data подпись вернётся к «Xbox Live Marketplace» — тогда `menuitems_legacy.py build` ещё раз. Те же правки
build вносит и в локализацию накладки «АХЛ на 32» (`game/work/legacy-data/out-ahl32/fe/loc/NHL_ENG_US.db`, CV/HSK):
ставить её — `install-legacy-fe.sh menu --ahl32` (локализация берётся из накладки).

## 9. Подзаголовок подменю и табличка LEGACY EDITION (09.10.2026, legacy-fe)

**Что было.** Подзаголовок подменю (`Menu.UpdateSubtitle`) стоит на `SUBTITLE_Y_OFFSET` = 35 выше списка:
y = mcMenu._y − mcMenu._height − 35. Список растёт вверх. С рядами 28/45 (§3) у списков от 8 пунктов
подзаголовок ложится на табличку LEGACY EDITION и низ надписи NHL: SETTINGS (9), CUSTOMIZE (8), лиги
Team Rosters (11), хаб Be a GM (9). Кубок с табличкой — картинка меню `mcFeatureImage`: `mcImage`
(`artAssets/playerMenuBackgrounds/<любимая команда>_0.swf` из `objMainMenu.GetMenuImageData`) и `mcNHLLogo`.
В подменю `Menu.SetFeatureImageFaded(true)` гасит её цветом ×20 %, и табличка под подзаголовком читается.

**Правка.** В `SetFeatureImageFaded` `PushByte 20` → `PushByte 6`, один байт (`FEATURE_FADED` в
[tools/menu12_legacy.py](../tools/menu12_legacy.py), `faded_image_edits`). В подменю кубок — почти чёрный
силуэт, табличку под подзаголовком видно только вблизи. В корне — ×100 %, как было.

Почему цвет, а не прозрачность. Цветовое преобразование меняет только `SetFeatureImageFaded`. Видимость
и `_alpha` меняют и другие места. Например, когда экран открывается сразу на подменю (новый экземпляр Menu,
путь картинки ещё пуст), `_DelayedMenuImageAssignment` ставит `mcFeatureImage._visible = true` и ведёт
`_alpha` 0 → 100. Ключа `aa` (прозрачность в `setTransform`) в пуле констант ролика нет. Если нужно совсем
без следа таблички — `FEATURE_FADED = (20, 0)`, та же правка: кубок в подменю станет ровным чёрным силуэтом.
Пользователь посмотрел 6 % и оставил их («6 — норм», 09.10.2026); 0 % не собирали.

**Проверено в игре** (09.10.2026, 08:55–09:03, копия `game/work/legacy-fe/userdata-gm`): SETTINGS, лиги
TEAM ROSTERS, CUSTOMIZE, возврат в корень. Лист «до/после» — `game/work/legacy-fe/submenu-before-after.png`,
крупно — `game/work/legacy-fe/shots/plate_zoom.png`.

**Установка, откат.** `menu.big` собирает `menu12_legacy.py build` в `game/work/legacy-data/out` (там уже ×6 %,
переустановка legacy-data старое не вернёт). Поставить в cache: пользователя:

```bash
bash game/work/legacy-fe/install-legacy-fe.sh menufade     # при закрытой игре, с бэкапом
bash game/work/legacy-fe/uninstall-legacy-fe.sh menufade   # откат: прежний menu.big (×20 %)
```

Поставлено 09.10.2026 в 09:04, бэкап `game/work/legacy-fe/backup-20261009-090440-menufade`.

## 10. Экраны франшизы Be a GM: где 30, где 32 (09.10.2026, legacy-fe)

**Ролики.** Разобраны все 36 роликов экранов Be a GM (`cache:fe/ion/game/screens/dynasty/*`, разбор в
`game/work/legacy-fe/franchise/dis/`). Жёстких 30, 29 или 31 нет. Списки команд дают родные функции exe:
`ION_Team.GetIDs(лига, FILTER_…)`, `ION_NHLStats.GetStatTeamIDsByDivisionID`,
`ION_NHLSeries.GetTeamIDsForDivisionId`, `GetActiveLeaguesForScreen`. Если где-то 30, правка в коде
(legacy-port), не в Apt.

**В игре.** Копия userdata пользователя (`game/work/legacy-fe/userdata-gm`, BE A GM1 за Anaheim), рабочий exe.
Сим 26.09 → 12.10.2026 прошёл без падений. Снимки — `game/work/legacy-fe/shots/gm3/`, сводный лист —
`game/work/legacy-fe/franchise-sea-vgk.png`.

| Экран | Список команд | SEA/VGK |
|---|---|---|
| Select Team (создание франшизы) | 30 | нет: Vancouver → Toronto, St. Louis → San Jose (меню 829CCA18 legacy-port) |
| Team Standings | вся лига 32, 4 дивизиона по 8; АХЛ 32 | есть |
| Player Stats — Season (LT/RT) | дивизионы, конференции, 32 команды | есть |
| Team Reports (Coaching) | 32 | есть, данные заполнены |
| Contract Status (LB/RB) | 32 | есть |
| Trade Players, Injury Report (LT) | 32 | есть |
| Roster Moves, Edit Lines | свой клуб и фарм | — |
| Free Agents, Scouting Report, Offer Sheets | без списка команд | — |

**Предсезонка без SEA и VGK** (код, передано legacy-port). К 03.10, концу предсезонки, у остальных клубов
6–7 игр, у Seattle и Vegas 0. В Player Stats у них «No Stats Available». В регулярке их игры идут и
учитываются: на 12.10 Seattle 3-0-0, Vegas 1-1-0, у игроков есть GP, в Team Reports заполнены голы и
спецбригады.
