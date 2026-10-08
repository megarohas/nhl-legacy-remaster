# Шрифты интерфейса

Где лежат шрифты NHL 13, как игра их использует и как заменить своим —
`tools/fefont.py`. Разобрано 08.10.2026; в игре замена **ещё не проверялась**.

## Что где

Интерфейс (Apt/ION) рисует текст **обычными TrueType-шрифтами на лету**: растеризатор
Bitstream **FontFusion** внутри RenderWare/RNA (`rw::graphics::font::FusionRasterizer`,
`Render::TextStamping::Font::AutoGlyphCache` в `default.xex`), глифы кэшируются в текстуре.
Готовых атласов глифов для меню нет — заменить шрифт = подложить другой `.ttf`.

| Файл в `cache:` | Архив | Имя в Apt | Что внутри | Где виден |
|---|---|---|---|---|
| `fe\ion\fonts\EAHelveticaNeueConBol-Mod.ttf` | `cache.big` | `EA HelveticaNeue Con Bold` | Helvetica Neue **65 Medium**, уменьшенный до 94,4 % | большинство надписей: заголовки, имена, «Press START», названия команд |
| `fe\ion\fonts\EAHelveticaNeueMed-Mod.ttf` | `cache.big` | `EA HelveticaNeue Med` | тот же 65 Medium (отличается только знак ℠ и классы веса/ширины в OS/2) | то же — второй «главный» шрифт |
| `fe\ion\fonts\EAHelveticaNeueHv-Mod.ttf` | `cache.big` | `EA HelveticaNeue Hv` | Helvetica Neue **85 Heavy**, 94,4 % | пункты меню (`mItemTextFormat` в `boot/fe/ion/main.big`; прописными их делает `menu.big`), цифры в плашках, заголовки таблиц |
| `rendering\indicator\indicatorfont.ttf` | `cacherender.big` (chunklzx) | `EA HelveticaNeue Con Bold` | Helvetica Neue **77 Bold Condensed**, в натуральную величину | подписи над игроками на льду (3D, грузится отдельно) |
| `fe\ion\fonts\fonts.txt` | `cache.big` | | список файлов для загрузки: `arial.ttf`, `EAHelveticaNeueMed-Mod.ttf`, `…Hv-Mod.ttf`, `…ConBol-Mod.ttf` | |
| `fe\ion\fonts\font_extents.txt` | `cache.big` | | высоты строк по кеглям (ниже) | |
| `fe\ion\fonts\rockeb.ttf` | `cache.big` | `Rockwell Extra Bold` | | нет в `fonts.txt`, игра его не открывает |
| `debug\consolasboldreduced.ttf` | `boot.big` (chunklzx) | | Consolas Bold | отладка |

Порядок загрузки (лог порта, строки `NtCreateFile FAILED: path='cache:\…'` — сначала
игра ищет свободный файл в `cache:`, потом берёт из архива): `font_extents.txt`, `fonts.txt`,
по списку `arial.ttf` (его нет ни в `cache:`, ни на диске — пропускается), `…Med-Mod.ttf`,
`…Hv-Mod.ttf`, `…ConBol-Mod.ttf` — всё при запуске; `indicatorfont.ttf` — при первом матче.
Значит, замена работает через `cache:` так же, как база и логотипы, но **нужен перезапуск игры**.

Ролики Apt ссылаются на шрифт **по имени**: шрифтовые символы (`Font`, имя по +0x14) и
строки `TextFormat` в коде роликов. По распакованным архивам (21 159 роликов): `Con Bold` —
421 упоминание в 344 файлах, `Med` — 382 в 337, `Hv` — 374 в 321, `Arial` — 10 (лишь отладочные
экраны), `EA HelveticaNeue Bold`, `… Med Con`, `EA HelveticaNeue` — по 1–2 (таких шрифтов нет).
Имя берётся из таблицы `name` файла шрифта, поэтому замена должна нести те же имена —
сборка переносит `name` оригинала байт-в-байт. Сверка со снимком «Starting Lineups»
(Chrome рисует `…ConBol-Mod.ttf` теми же формами, что игра) подтверждает: основной шрифт
надписей — 65 Medium из `Con Bold`/`Med`, цифры номеров — `Hv`.

Прочее со словом font в архивах — не шрифты меню: `fe/ion/artassets/createteam/font/font0…5.big`
— картинки образцов букв для конструктора команды, `rendering/czfont/*.rx2` — текстуры
номеров и фамилий на форме, `fe/ion/game/overlays/overlayfontcache.big` (`cacheoverlay.big`) —
ролик с текстовым полем `EA HelveticaNeue Con Bold`, где выписан весь набор символов
(прогрев кэша глифов для табло матча).

### font_extents.txt

Для каждого из трёх шрифтов — строки `[ size A D ]` для size = 10…250:

```
A = ceil(min(size, 127) · usWinAscent  / unitsPerEm)
D = ceil(min(size, 127) · usWinDescent / unitsPerEm)
```

(выше 127 px значения не растут — видимо, предел кэша глифов). Формула сверена на всех
723 строках: `python tools/fefont.py extents --check`. Для `Med` и `Hv` совпадает с их файлами
(952/221 и 951/234), а блок `Con Bold` посчитан **не по нынешнему `…ConBol-Mod.ttf`**
(952/221 — 201 расхождение), а по настоящему 77 Bold Condensed (961/224, как у
`indicatorfont.ttf`) — 0 расхождений. То есть когда-то «EA HelveticaNeue Con Bold» в меню был
настоящим узким Bold Condensed, а в NHL 13 файл подменили на уменьшенный Medium («-Mod»),
оставив старую таблицу. Меню NHL 12 при этом набрано другим шрифтом — DIN (см. ниже).

## Замена: tools/fefont.py

Инструмент пересаживает контуры своего шрифта в «скелет» шрифта игры:

- **сохраняются** таблица `name` (имена для Apt), классы веса/ширины и `fsSelection` (OS/2),
  `macStyle`, вертикальные метрики (hhea, typo, win — значит, `font_extents.txt` остаётся
  верным и базовая линия не сдвигается) и **ровно тот же набор символов** (326/325 шт.);
- **берутся из своего шрифта** контуры, ширины, кернинг (GPOS или `kern` → таблица `kern`,
  до 10 920 самых сильных пар);
- масштаб — по высоте прописных оригинала (`--fit cap`, у «-Mod» это 674 из 1000), можно
  по строчным (`x`) или кегль в кегль (`em`); `--width auto|K` — сузить/растянуть, `--track N` —
  разрядка в единицах из 1000 (зашивается в ширины; разную для разных шрифтов — отдельными
  запусками в один OUTDIR), `--caps` — строчные рисуются прописными; ®, ™, ℠ вписываются в
  рамку маленьких надстрочных знаков EA («Wild®»);
- исходник — TTF, OTF (CFF → квадратичные кривые), TTC (`#N`), вариативный шрифт в нужном
  стиле (`@SemiBold`, `@wght=600,wdth=80`; gvar/avar/HVAR и вариации кернинга). WOFF и CFF2 — нет;
- чего нет в исходнике — похожий символ (табуляция и неразрывный пробел → пробел, ‑ → -,
  Ё → Ë, Ω → Ω, ∆ → Δ, ﬁ/ﬂ → f+i/f+l) или глиф оригинала; список — в отчёте сборки;
- хинтинг не переносится (FontFusion рисует без инструкций), составные глифы раскрываются;
  файл не больше оригинала (лишнее — за счёт слабых пар кернинга), отчёт —
  `OUTDIR/fefont-build.json`.

```bash
python tools/fefont.py info                                  # шрифты игры: имена, метрики, символы
python tools/fefont.py info C:/Windows/Fonts/bahnschrift.ttf@SemiBold
python tools/fefont.py styles C:/Windows/Fonts/bahnschrift.ttf   # стили вариативного шрифта
python tools/fefont.py build game/work/fe-font/out \
    --face "conbold=C:/Windows/Fonts/bahnschrift.ttf@SemiBold" \
    --face "med=C:/Windows/Fonts/bahnschrift.ttf@SemiBold" \
    --face "hv=C:/Windows/Fonts/bahnschrift.ttf@Bold"
python tools/fefont.py preview game/work/fe-font/out game/work/fe-font/preview/bahnschrift --shot КАДР.webp
```

`--shot` — снимок экрана «Starting Lineups» 1651×982 (игра в окне 1600×900): куски кадра
ставятся рядом с тем же текстом оригинальным и новым шрифтом. Оригиналы инструмент берёт из
`game/extracted/big/…`, `game/work/fe-font/src/…` или прямо из `.big` диска (разжимая chunklzx).

Проверки инструмента: пересборка всех четырёх шрифтов игры «из самих себя» даёт те же контуры,
ширины и кернинг всех символов; стили Bahnschrift (Regular, SemiBold, Bold Condensed,
`wght=520,wdth=90`) совпадают с тем, как Chrome рисует вариативный оригинал; шесть OTF (CFF)
из `C:\Windows\Fonts` — тоже; контрольные суммы таблиц и файла верны, Chrome (санитайзер OTS)
файлы принимает; `font_extents.txt`, собранный по метрикам `indicatorfont.ttf`, байт-в-байт
равен игровому.

### Пробные сборки (08.10.2026, в игру не ставились)

| Папка | Что | Заметки |
|---|---|---|
| `game/work/fe-font/out/` | `Con Bold` и `Med` ← Bahnschrift SemiBold, `Hv` ← Bahnschrift Bold | ширина при той же высоте прописных — 0,956 / 0,925 от оригинала (надписи не длиннее); из оригинала 14 знаков (DEL, ĕ, ℠, ∂ ∏ ∑ √ ∞ ∫ ≈ ≠ ≤ ≥ ◊); у Bold «Ů» на 10 единиц выше usWinAscent |
| `game/work/fe-font/out-hncond/` | `Con Bold` ← 77 Bold Condensed из `indicatorfont.ttf`, кегль в кегль (`--fit em --vmetrics source`) | вариант «как было до “-Mod”»: прописные 714 вместо 674 (на 6 % крупнее), сам шрифт уже; `font_extents.txt` совпадает с игровым, класть не нужно; `Med` и `Hv` не тронуты |
| `game/work/fe-font/out-nhl12/` | «как меню NHL 12»: `Hv` (пункты меню, цифры) ← Bahnschrift Bold с разрядкой 59/1000, `Con Bold` и `Med` ← Bahnschrift SemiBold с разрядкой 10/1000 | разбор — ниже; строки меню той же ширины, что сейчас (±2 %) |

Превью — `game/work/fe-font/preview/bahnschrift/`, `…/hn-condensed/`, `…/nhl12-look/`:
`*_before_after.png` (строки меню и весь набор символов; красным — знаки, взятые из оригинала),
`shot_compare.png` (куски кадра «Starting Lineups»), `nhl12_menu_compare.png` (меню NHL 12 рядом
с теми же пунктами нынешним и новым «Hv»).

### Как поставить и откатить

`cache:` порта — `game/userdata/cache/guest/` (см. [modding.md](modding.md)). Игру закрыть,
скопировать дерево `fe` нужной сборки (`out`, `out-nhl12`, `out-hncond`) поверх — папки
сливаются, — запустить:

```bash
cp -r game/work/fe-font/out-nhl12/fe game/userdata/cache/guest/
# откат:
rm game/userdata/cache/guest/fe/ion/fonts/EAHelveticaNeue{ConBol,Med,Hv}-Mod.ttf
```

Сборки ставятся целиком или по файлам: например, только `EAHelveticaNeueHv-Mod.ttf` из
`out-nhl12` — поменяются лишь пункты меню и цифры.

Признак, что подхватилось: в логе порта пропадают строки `FAILED: path='cache:\fe\ion\fonts\…-Mod.ttf'`.
Файл `fefont-build.json` (отчёт) копировать не нужно. Для подписей на льду — `--face indicator=…`,
файл ляжет в `OUTDIR/rendering/indicator/indicatorfont.ttf`.

### Не проверено

- Как FontFusion в игре примет шрифт без хинтинга и с таблицей `kern` на ~11 тыс. пар
  (Chrome — без замечаний); применяет ли интерфейс кернинг вообще (в превью — применяется;
  у `TextFormat` в Apt есть флаг `kerning`, как во Flash, — встречается `kerning="1"` в
  `nhlbackgroundcard.big`, по умолчанию, вероятно, выключен).
- Нет ли в игре жёсткого буфера под файлы шрифтов (строки `Font File Buffer`, `FontsBuf`) —
  поэтому сборка не делает файл больше оригинала.
- Обрезка глифов, выходящих за usWinAscent/Descent (у Bahnschrift Bold — «Ů»), и мелкие кегли
  (10–14 px) без хинтинга.
- Тексты с `Arial` (отладочные экраны) по-прежнему без шрифта: `arial.ttf` в `fonts.txt` есть, файла нет.

## Шрифт из NHL 12

### Что видно на снимке главного меню (русская NHL 12)

Меню NHL 12 набрано **не Helvetica**, а гротеском семейства **DIN**: прямоугольно-скруглённые
O, C, D, S, G со шпорой, R с прямой ногой, жирное начертание обычной ширины, разрядка
≈ 9 % высоты прописных; ™ — маленький надстрочный. Тем же DIN набраны шапка HUT (узкий, с
большой разрядкой) и нижняя плашка (средний вес) — и там есть строчные («Standing On The Edge
Of The Noise», «DruchaPucha»): прописные в меню — **от кода меню, а не от шрифта**.

Такого шрифта в NHL 13 нет (в её архивах только Helvetica Neue четырёх видов, Rockwell и
Consolas). Ближайший из имеющихся — системный **Bahnschrift** (DIN 1451 от Microsoft,
вариативный). Подбор по замерам девяти строк меню (ширина при той же высоте прописных 10,5 px
снимка, разрядка — МНК): Bahnschrift Bold/SemiBold обычной ширины — расхождение 2,4 px,
разрядка 0,087 высоты прописных; SemiCondensed — 2,5 px, но нужна разрядка 0,23 (буквы уже,
чем в NHL 12); Helvetica Neue 85 Heavy (нынешний «Hv») — 3,7 px, 77 Bold Condensed — 4,2 px,
Segoe UI Bold — 3,7, Franklin Gothic — 4,3; на глаз Helvetica и Segoe — явно не то. Отличие
Bahnschrift от NHL 12: у NHL 12 «чаши» (O, C, D, Q) квадратнее, штрих на снимке чуть тяжелее
(может быть и свечение/JPEG).

Пункты главного меню NHL 13 рисует компонент `boot/fe/ion/game/components/menu.big`
шрифтом `mItemTextFormat` = «EA HelveticaNeue Hv» (задаётся в `boot/fe/ion/main.big`) и сам
переводит их в прописные (`GetName().toUpperCase()`; так же имена игроков в
`03_startinglineups.big`). Поэтому для «меню как в NHL 12» достаточно заменить `Hv`;
регистр трогать не нужно. Если понадобятся прописные где-то ещё: правка строк
(`tools/locdb.py put`), либо `fefont.py build … --caps` — строчные рисуются глифами прописных,
но тогда во **всех** текстах этого шрифта. Apt поддерживает и `letterSpacing`/`kerning` в
`TextFormat` (встречается в `nhlbackgroundcard.big`), но менять разметку роликов — сложнее,
поэтому разрядка зашита в сам шрифт (`--track`).

Вариант «как меню NHL 12» (`game/work/fe-font/out-nhl12/`, превью
`preview/nhl12-look/nhl12_menu_compare.png`):

```bash
python tools/fefont.py build game/work/fe-font/out-nhl12 --track 10 \
    --face "conbold=C:/Windows/Fonts/bahnschrift.ttf@SemiBold" --face "med=C:/Windows/Fonts/bahnschrift.ttf@SemiBold"
python tools/fefont.py build game/work/fe-font/out-nhl12 --track 59 --face "hv=C:/Windows/Fonts/bahnschrift.ttf@Bold"
python tools/fefont.py preview game/work/fe-font/out-nhl12 game/work/fe-font/preview/nhl12-look --nhl12 СНИМОК_NHL12.jpg
```

59 = 0,087 × 674 (высота прописных «-Mod» в единицах из 1000). Строки меню при этом той же
ширины, что с нынешним «Hv» (±2 %) — в разметку NHL 13 влезут. Цифры (номера в «Starting
Lineups») тоже станут DIN с разрядкой — они набраны тем же «Hv».

### Если доставать настоящий шрифт из NHL 12

Архивы NHL 12 того же формата BigEB v3 (`unpack_big.py` из `ref/nhl-legacy-recomp` писался
именно под NHL 12), интерфейс — тот же ION с FontFusion, так что шрифт будет TTF и подойдёт к
`fefont.py` без конвертации. Установка с диска → `svod.py extract` (см. [game-files.md](game-files.md)),
затем:

```bash
python ref/nhl-legacy-recomp/docs/nhl12-decomp-reference/tools/unpack_big.py \
    НАШ_ДИСК_NHL12/*.big --list --pattern 'font|\.ttf|\.otf'
```

- `fe/ion/fonts/fonts.txt` — какие файлы грузятся; `fe/ion/fonts/*.ttf`, `font_extents.txt`;
- имя шрифта пунктов меню — строка после `mItemTextFormat` в `fe/ion/main.big` NHL 12 (у NHL 13
  там «EA HelveticaNeue Hv»); искать файл, у которого это имя в таблице `name`
  (`fefont.py info ФАЙЛ.ttf`);
- записи, начинающиеся с `chunklzx`/`chunkzip`, разжать `tools/unchunk.py`.

Сборка (свой межбуквенный интервал шрифта — без `--track`; `--fit cap` — под высоту прописных NHL 13,
`--fit em --vmetrics source` — как есть, с его вертикальными метриками и новым `font_extents.txt`):

```bash
python tools/fefont.py build game/work/fe-font/out-nhl12-real --face "hv=game/work/fe-font/nhl12/<шрифт меню>.ttf"
```

Внутренние имена шрифта NHL 12 значения не имеют — сборка ставит имена NHL 13. Если в NHL 12
несколько DIN-начертаний, сопоставить по роли: пункты меню и цифры — `hv`, остальные надписи —
`conbold` и `med`.
