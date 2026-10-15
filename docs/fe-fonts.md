# Шрифты интерфейса

Где лежат шрифты NHL 13, как игра их использует и как заменить своим — `tools/fefont.py`.
**С 08.10.2026 в игре стоит шрифт меню NHL 12** (вариант «1:1», раздел ниже) — проверен в игре;
откат — `bash game/work/fonts/uninstall-font.sh`.

## Что где

Интерфейс (Apt/ION) рисует текст **обычными TrueType-шрифтами на лету**: растеризатор
Bitstream **FontFusion** внутри RenderWare/RNA (`rw::graphics::font::FusionRasterizer`,
`Render::TextStamping::Font::AutoGlyphCache` в `default.xex`), глифы кэшируются в текстуре.
Готовых атласов глифов для меню нет — заменить шрифт = подложить другой `.ttf`.
**Хинтинг TrueType игра не применяет**: тот же шрифт с инструкциями и без них даёт в игре
попиксельно одинаковую картинку (пункты меню, абзац текста — 0 отличающихся пикселей, 08.10.2026).

| Файл в `cache:` | Архив | Имя в Apt | Что внутри (NHL 13) | Где виден |
|---|---|---|---|---|
| `fe\ion\fonts\EAHelveticaNeueConBol-Mod.ttf` | `cache.big` | `EA HelveticaNeue Con Bold` | Helvetica Neue **65 Medium**, уменьшенный до 94,4 % | большинство надписей: заголовки экранов, имена, составы, «Press START», названия команд, табло матча |
| `fe\ion\fonts\EAHelveticaNeueMed-Mod.ttf` | `cache.big` | `EA HelveticaNeue Med` | тот же 65 Medium (отличается только знак ℠ и классы веса/ширины в OS/2) | то же — второй «главный» шрифт (тексты, подписи) |
| `fe\ion\fonts\EAHelveticaNeueHv-Mod.ttf` | `cache.big` | `EA HelveticaNeue Hv` | Helvetica Neue **85 Heavy**, 94,4 % | пункты меню (`mItemTextFormat` в `boot/fe/ion/main.big`; прописными их делает `menu.big`), цифры в плашках и на карточках игроков, заголовки таблиц |
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
Признак, что подхватилось: в логе порта нет строк `FAILED: path='cache:\fe\ion\fonts\…-Mod.ttf'`.

Ролики Apt ссылаются на шрифт **по имени**: шрифтовые символы (`Font`, имя по +0x14) и
строки `TextFormat` в коде роликов. По распакованным архивам (21 159 роликов): `Con Bold` —
421 упоминание в 344 файлах, `Med` — 382 в 337, `Hv` — 374 в 321, `Arial` — 10 (лишь отладочные
экраны), `EA HelveticaNeue Bold`, `… Med Con`, `EA HelveticaNeue` — по 1–2 (таких шрифтов нет).
Имя берётся из таблицы `name` файла шрифта, поэтому замена должна нести те же имена —
сборка переносит `name` оригинала байт-в-байт.

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
`indicatorfont.ttf`) — 0 расхождений. В NHL 12 `fonts.txt` и `font_extents.txt` **побайтно те же**.

## Шрифт меню NHL 12 — стоит в игре

### Откуда и что это

NHL 12 (диск с приставки, `game/other/nhl12/`, см. `game/work/status/nhl12-*.ready`) хранит
шрифты там же и под теми же именами: `cache.big:fe/ion/fonts/EAHelveticaNeue{Med,Hv,ConBol}-Mod.ttf`
(распаковано в `game/other/nhl12/big/cache/fe/ion/fonts/`). Внутри — **не Helvetica**, хотя имена,
копирайт и OS/2 остались от Helvetica Neue LT Std: EA подменила контуры на квадратный
DIN-подобный гротеск (прямоугольно-скруглённые O C D G Q, R с прямой ногой, квадратные цифры) —
тот самый вид меню NHL 12. В шрифтах есть кириллица, чешские и скандинавские буквы (тот же набор,
что у NHL 13, кроме ℠), хинтинг (fpgm/prep/cvt, hdmx, LTSH, VDMX), кернинга нет.

| | NHL 13 Med / Con Bold | NHL 12 Med | NHL 13 Hv | NHL 12 Hv |
|---|---|---|---|---|
| вертикаль hhea / win | 714/−286/200, 952/221 | **та же** | 714/−286/200, 951/234 | **та же** |
| высота прописных | 674 | 644 (−4,5 %) | 674 | 644 (−4,5 %) |
| высота строчных | 487 | 500 | 489 | 506 |
| средняя ширина (A–Z a–z 0–9) | 1 | 0,937 | 1 | 0,912 |
| символов | 326 | 325 (нет ℠) | 325 | 324 (нет ℠) |

`EAHelveticaNeueConBol-Mod.ttf` в NHL 12 — копия `…Med-Mod.ttf` (отличаются два байта `head`),
и имя внутри у него тоже «EA HelveticaNeue **Med**»: шрифта с именем «Con Bold» в NHL 12 нет.

Роли. Пункты меню в NHL 12 — тоже «Hv»: `mItemTextFormat` = `EA HelveticaNeue Hv` в
`boot/fe/ion/external/ion_sports07/fw/commonloader.big` (в NHL 13 — в `boot/fe/ion/main.big`).
Отсюда сопоставление: **`hv` ← NHL 12 Hv** (пункты меню, цифры), **`conbold` и `med` ← NHL 12 Med**
(остальные надписи). Для разбора Apt хватает RefPack из `playerhead.py`: записи BIGF
`main.big`/`commonloader.big` разжимаются и ищутся по строкам `…TextFormat`.

### Сборка: «1:1» (стоит) и «под NHL 13» (запасной)

```bash
D=game/other/nhl12/big/cache/fe/ion/fonts
# 1:1 — шрифт NHL 12 как есть (стоит в игре)
python tools/fefont.py build game/work/fonts/out-nhl12 --keep \
    --face conbold=$D/eahelveticaneueconbol-mod.ttf --face med=$D/eahelveticaneuemed-mod.ttf \
    --face hv=$D/eahelveticaneuehv-mod.ttf
# под высоту прописных NHL 13 (×1,047)
python tools/fefont.py build game/work/fonts/out-nhl12-cap \
    --face conbold=$D/eahelveticaneueconbol-mod.ttf --face med=$D/eahelveticaneuemed-mod.ttf \
    --face hv=$D/eahelveticaneuehv-mod.ttf
python tools/fefont.py compare  game/work/fonts/out-nhl12 game/work/fonts/preview/compare_fonts.png --label "NHL 12"
python tools/fefont.py coverage game/work/fonts/out-nhl12
```

- **«1:1» (`--keep`)** — файлы NHL 12 целиком: контуры, ширины, хинтинг байт в байт (сборка это
  проверяет), вертикальные метрики те же, что у NHL 13, — `font_extents.txt` и базовые линии не
  меняются, текст короче нынешнего на 6–9 % и на 4,5 % ниже — из плашек не вылезает. От NHL 13 —
  только «лицо»: таблица `name` (иначе не найдутся «Con Bold» и пр.), классы веса/ширины,
  `fsSelection`, `macStyle`. Добавлено: **℠** (в NHL 12 нет; нужен в названиях трёх арен базы —
  Xcel Energy Center, Jobing.com Arena, Tampa Bay Times Forum) — собран из букв S и M того же шрифта в рамке его ™; **®** у NHL 12
  крупный, во всю высоту прописных — новым глифом уменьшен в рамку маленького ® NHL 13
  («Capitals®»). Глифов Helvetica в сборке нет ни одного. Файлы 80,6 / 80,6 / 80,8 КБ (у NHL 13 —
  104,6 / 104,5 / 102,0 КБ).
- **«под NHL 13»** — обычная пересадка (`--fit cap`): ×1,0466, прописные 674 как у NHL 13, ширина
  0,98 (Med) и 0,95 (Hv) от нынешней. Знаки над прописными и выносные, что после увеличения вылезли
  бы за usWinAscent/Descent, ужаты по вертикали в эту рамку: Med — выносные g j p q y ß ý ÿ р на 2 %,
  седиль ¸ на 5 %, кольцо Å на 8 % (часть над прописными); Hv — знаки над À Á Å È Ì Í Ù Ú на 11–14 %,
  над É на 4 %, ¸ на 5 %. На глаз не видно (`preview/compare_fonts-cap.png`).
  В игре не ставился; хинтинга нет, но игра его и не применяет.

Покрытие (`fefont.py coverage`): все 189 символов строк интерфейса `NHL_ENG_US.db` и строк базы
(имена с Č Š Ž Ř Ů Ä Ö Å Ø É ß и пр., команды, арены — то, что стоит в `cache:`) в сборке есть;
нет только 9 иероглифов в строке списка языков `OSDK_CLUBS_LANGUAGES` — их нет и в шрифтах NHL 13.
Прописные к строчным (пункты меню идут через `toUpperCase()`) — тоже все есть.

### Установка и откат

`cache:` порта — `game/userdata/cache/guest/` (см. [modding.md](modding.md)). Только при закрытой игре:

```bash
bash game/work/fonts/install-font.sh            # вариант «1:1» (game/work/fonts/out-nhl12)
bash game/work/fonts/install-font.sh out-nhl12-cap   # вариант «под NHL 13»
bash game/work/fonts/uninstall-font.sh          # откат: шрифты снова из cache.big
```

Ставятся 3 файла `cache:/fe/ion/fonts/EAHelveticaNeue{ConBol,Med,Hv}-Mod.ttf`, список —
`game/work/fonts/installed-font.txt`. Если в `cache:` на их месте уже что-то лежало, это сохраняется
в `game/work/fonts/backup/` и при откате возвращается (08.10.2026 там было пусто). Скрипт проверяет
`tasklist` и при запущенной игре ничего не делает. Подхватывается при следующем запуске игры.

### Проверка в игре (08.10.2026)

Основная сборка `port-ffx/out/build/win-amd64-release/nhl13.exe`, окно 1600×900, ввод — клавиатурой
(`--mnk_mode=true`: Start — Return, A — Space, крестовина — Shift+стрелки, RT — E; конфиг не менялся),
снимки окна — `PrintWindow` с флагами 3 (только клиентская часть, полное содержимое D3D12) из
DPI-aware процесса. Снимки — `game/work/fonts/preview/`: `ingame-before-*.png` (родные шрифты),
`ingame-after-*.png` (шрифт NHL 12 «1:1»), сводка парами — `ingame-pairs.png`, образцы в Chrome —
`compare_fonts.png` (NHL 13 было / NHL 12 оригинал / NHL 13 новый).

- По логу шрифты взяты из `cache:` (нет строк `FAILED … -Mod.ttf`), ошибок нет; без установки
  (`uninstall-font.sh`) строки `FAILED` для трёх файлов возвращаются — откат работает.
- Новым шрифтом: экран выбора языка, юридический экран, титул (окно автосохранения, © 2012),
  главное меню (пункты, «New», окно Features, бегущая строка EA Trax, цифры и фамилии на карточках),
  выбор команд и формы, всплывающее меню перед матчем, Starting Lineups (в т. ч. «M. FEHÉRVÁRY» —
  знаки целы), экраны загрузки, табло матча («WSH 0 MTL 0 1st 19:09»), «Faceoff».
- Ничего не вылезает из плашек, выделение пунктов меню подстраивается под ширину текста.
- Подписи над игроками на льду — прежние (77 Bold Condensed из `indicatorfont.ttf`, не менялись).

## Замена своим шрифтом: tools/fefont.py

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
  рамку маленьких надстрочных знаков EA («Wild®»), ℠, которого нет в шрифте, собирается из его S и M;
  знаки над прописными и выносные, вылезающие за usWinAscent/Descent, ужимаются в эту рамку
  (`--no-squeeze` — не трогать);
- `--keep` — шрифт TrueType того же unitsPerEm **как есть** (контуры, ширины, хинтинг), меняется
  только «лицо» и вертикальные метрики; недостающее дописывается (так собран шрифт NHL 12);
- исходник — TTF, OTF (CFF → квадратичные кривые), TTC (`#N`), вариативный шрифт в нужном
  стиле (`@SemiBold`, `@wght=600,wdth=80`; gvar/avar/HVAR и вариации кернинга). WOFF и CFF2 — нет;
- чего нет в исходнике — похожий символ (табуляция и неразрывный пробел → пробел, ‑ → -,
  Ё → Ë, Ω → Ω, ∆ → Δ, ﬁ/ﬂ → f+i/f+l) или глиф оригинала; список — в отчёте сборки;
- хинтинг при пересадке не переносится (игра его не применяет), составные глифы раскрываются;
  файл не больше оригинала (лишнее — за счёт слабых пар кернинга), отчёт — `OUTDIR/fefont-build.json`;
- `coverage` — проверка символов строк интерфейса и базы против сборки, `compare` — PNG
  «было / исходный шрифт / сборка», `preview` — образцы и куски снимков экрана.

```bash
python tools/fefont.py info                                  # шрифты игры: имена, метрики, символы
python tools/fefont.py info C:/Windows/Fonts/bahnschrift.ttf@SemiBold
python tools/fefont.py styles C:/Windows/Fonts/bahnschrift.ttf   # стили вариативного шрифта
python tools/fefont.py build game/work/fe-font/out \
    --face "conbold=C:/Windows/Fonts/bahnschrift.ttf@SemiBold" \
    --face "med=C:/Windows/Fonts/bahnschrift.ttf@SemiBold" \
    --face "hv=C:/Windows/Fonts/bahnschrift.ttf@Bold"
python tools/fefont.py preview game/work/fe-font/out game/work/fe-font/preview/bahnschrift --shot КАДР.webp
python tools/fefont.py coverage game/work/fe-font/out
```

`--shot` — снимок экрана «Starting Lineups» 1651×982 (игра в окне 1600×900): куски кадра
ставятся рядом с тем же текстом оригинальным и новым шрифтом. Оригиналы инструмент берёт из
`game/extracted/big/…`, `game/work/fe-font/src/…` или прямо из `.big` диска (разжимая chunklzx).
Для подписей на льду — `--face indicator=…`, файл ляжет в `OUTDIR/rendering/indicator/indicatorfont.ttf`.
Установка любой сборки — `install-font.sh ПАПКА` (папка внутри `game/work/fonts/`) или копированием
дерева `fe` в `game/userdata/cache/guest/`; `fefont-build.json` копировать не нужно.

Проверки инструмента: пересборка всех четырёх шрифтов игры «из самих себя» даёт те же контуры,
ширины и кернинг всех символов; стили Bahnschrift (Regular, SemiBold, Bold Condensed,
`wght=520,wdth=90`) совпадают с тем, как Chrome рисует вариативный оригинал; шесть OTF (CFF)
из `C:\Windows\Fonts` — тоже; контрольные суммы таблиц и файла верны, Chrome (санитайзер OTS)
файлы принимает, fontTools разбирает и пересобирает все таблицы `--keep`-сборки (в т. ч. hdmx, LTSH);
`font_extents.txt`, собранный по метрикам `indicatorfont.ttf`, байт-в-байт равен игровому.

### Ранние пробные сборки на Bahnschrift (до данных NHL 12, в игру не ставились)

Пока файлов NHL 12 не было, вид меню NHL 12 подбирали по снимку главного меню русской NHL 12
системным **Bahnschrift** (DIN 1451 от Microsoft): `game/work/fe-font/out/` (SemiBold/Bold),
`out-nhl12/` («как меню NHL 12»: Bold с разрядкой 59/1000 для «Hv», SemiBold с разрядкой 10 для
остальных), `out-hncond/` (`Con Bold` ← 77 Bold Condensed из `indicatorfont.ttf`, кегль в кегль).
Превью — `game/work/fe-font/preview/`. Настоящий шрифт NHL 12 (выше) их заменяет: у NHL 12 «чаши»
O C D Q квадратнее, чем у Bahnschrift, и не нужна разрядка.

## NHL Legacy

Шрифт меню NHL 12 для NHL Legacy (агент legacy-data-fe, 08.10.2026). Порт Legacy и общий
профиль игры — [legacy-port-feasibility.md](legacy-port-feasibility.md), `tools/gameprofile.py`.

### Чем шрифты Legacy отличаются от NHL 13

- **Где лежат.** Новый архив `cacheboot.big`, папка `fe/ion/fonts/` (распаковано в
  `game/other/legacy/big/cacheboot/fe/ion/fonts/`, имена строчные). Там те же три файла меню и
  `rockeb.ttf`. `fonts.txt` и `rockeb.ttf` побайтно такие же, как в NHL 12 и NHL 13. Подписи над
  игроками на льду — `cacherender.big:rendering/indicator/indicatorfont.ttf` (77 Bold Condensed),
  этот файл одинаков во всех трёх играх. Рядом лежит `indicatorfont94.ttf` — шрифт «NHL '94» для
  ретро-режима.
- **Рисунок свой.** Внутри не Helvetica (как в NHL 13) и не шрифт NHL 12, а свой квадратный гротеск
  того же семейства, что у NHL 12:
  - «Con Bold» и «Med» — один рисунок, тоньше, чем у NHL 12;
  - «Hv» — жирный, внешне близок к «Hv» NHL 12;
  - прописные 700, строчные 500 (у NHL 12 — 644 и 500, у NHL 13 — 674 и 487).

  Имена в таблице `name` те же, что в NHL 13. Отличие одно: у «Con Bold» подсемейство `Regular`, вес
  500, ширина 5 (в NHL 13 — `Condensed Bold`, 700 и 3). Размеры файлов: 90 864 (Con Bold),
  90 456 (Med), 86 616 (Hv) байт.
- **Набор символов.** Как в NHL 13, плюс Ę ę (U+0118/0119): 328 символов у «Con Bold» и «Med», 326 у
  «Hv». В «Hv» нет ℠ и табуляции.
- **`font_extents.txt` посчитан по самим файлам.** У «Con Bold» — 952/221, а не по 77 Bold Condensed,
  как в NHL 13 (`python tools/fefont.py extents --game legacy` — 0 расхождений по всем трём
  блокам). Вертикальные метрики Legacy (hhea 714/−286/200, win 952/221 и 951/234) те же, что в
  NHL 13. Сборка их сохраняет, поэтому `font_extents.txt` Legacy остаётся верным и в `cache:` не
  нужен.
- **Табло матча.** Ролики `cacheoverlay.big` ссылаются на «EA HelveticaNeue Con Bold» (около 30
  роликов, ещё около 10 — на «Med» и «Hv»). Поэтому табло меняется вместе с меню. В оригинале
  Legacy оно тоже квадратное, так что разница видна в основном по толщине: в моде буквы и цифры
  жирнее.

### Предел размера файла: в коде его нет

Загрузчик шрифтов один и тот же в NHL 13 и Legacy (найден по строкам `Font File Buffer` и
`FontsBuf` в образе, `nhl-legacy-port/analysis/strusers.py`):

- Legacy `82826020` (NHL 13 — `82F605C0`) читает `fonts.txt` целиком в буфер `FontsBuf`
  (размер + 1). По строкам он собирает путь и для каждого файла вызывает `828251C0` (NHL 13 —
  `82F604E0`).
- Тот открывает файл и берёт его размер. Под **ровно этот размер** выделяется буфер
  `Font File Buffer` (`825AB6D8` → менеджер памяти). Затем файл читается и шрифт создаётся из памяти
  (`82824FF0`).

Постоянного буфера под шрифт нет. Пулы памяти заданы текстом конфигурации внутри xex
(`AddAllocator`/`AddCategoryAllocator`, Legacy `0x820DA1A0`/`0x820DB6C0`). Категория `RWFONT` берёт
память по очереди из `GlobalSBA` (блоки до 256 байт), `RWFontPP` (2,5 МБ на Xenon), `GlobalPP` и
`GlobalOverflow`, `allowfail=0` — исчерпание пула шрифтов уходит в общую кучу.

Правило «не больше оригинала» в `fefont.py` остаётся как запас. Сборка NHL 12 его выполняет с
запасом: 80,7 / 80,7 / 80,9 КБ против 90,9 / 90,5 / 86,6 КБ у Legacy, всего 242 КБ вместо 268 КБ.
Хинтинг игра не применяет (см. выше), поэтому вариант без хинтинга не понадобился.

### Сборка

```bash
D=game/other/nhl12/big/cache/fe/ion/fonts
O=game/work/legacy-data/fe/fonts/out-nhl12
python tools/fefont.py build $O --game legacy --keep --add ℠ \
    --face conbold=$D/eahelveticaneueconbol-mod.ttf --face med=$D/eahelveticaneuemed-mod.ttf \
    --face hv=$D/eahelveticaneuehv-mod.ttf
mkdir -p game/work/legacy-data/out/fe/ion/fonts && cp $O/fe/ion/fonts/*.ttf game/work/legacy-data/out/fe/ion/fonts/
python game/work/legacy-data/fe/check_font.py        # проверки сборки (ниже)
python tools/fefont.py coverage --game legacy $O --all-loc --db game/userdata/cache/guest/db/nhlng.db
python tools/fefont.py compare --game legacy game/work/legacy-data/out game/work/legacy-data/fe/preview/compare_fonts.png \
    --col "NHL 12 — оригинал=$D" --col "NHL 13 с модом (стоит в игре)=game/work/fonts/out-nhl12" \
    --col "NHL Legacy — оригинал=game" --col "NHL Legacy с модом=game/work/legacy-data/out"
python tools/fefont.py preview --game legacy $O game/work/legacy-data/fe/preview
```

Результат для `cache:` Legacy — `game/work/legacy-data/out/fe/ion/fonts/eahelveticaneue{conbol,med,hv}-mod.ttf`
(имена строчные, как в архиве; игра просит `EAHelveticaNeue…-Mod.ttf`, папка `cache:` порта на
Windows регистр не различает). Список файлов — `game/work/legacy-data/fe/files.txt`. Ставит
legacy-data своим скриптом, при закрытой игре; подхватывается при следующем запуске.

Что получается — вариант «1:1», как в NHL 13:

- Глифы, ширины и хинтинг NHL 12 — байт в байт. От Legacy взяты таблица `name`, вес, ширина,
  `fsSelection`, `macStyle` и вертикальные метрики.
- **®** остаётся крупным, как в самих NHL 12 и Legacy. В NHL 13 его уменьшали под маленький ® NHL 13.
- **℠** собран из S и M в рамке ™. Через `--add` он есть и в «Hv», хотя в оригинальном «Hv» Legacy
  его не было: в базе ℠ встречается 4 раза (например, «Xcel Energy Center ℠»).
- **Ę ę** — глифы самой Legacy, другого рисунка: прописные выше на 8 %. В строках игры они встречаются
  только в польских сетевых строках OSDK других языков, в английской локализации, базе и составах
  2026/27 их нет.
- Относительно Legacy текст ниже на 8 % (прописные 644 против 700). Средняя ширина та же (×0,99),
  прописные уже (×0,93), цифры шире на 3–4,5 %. Пункты меню и заголовки из плашек не вылезут; длинные
  ряды цифр стоит посмотреть.

Запасной вариант «под высоту Legacy» — `game/work/legacy-data/fe/variants/fonts-cap/`, в `out/` не
кладётся и в игре не проверялся. Это обычная пересадка: та же команда без `--keep` и `--add`, ×1,087,
хинтинга нет. Прописные как у Legacy (700), но текст на 7–8 % шире оригинала Legacy, и длинные строки
могут не влезть. Сравнение — `game/work/legacy-data/fe/preview/compare_fonts-cap.png`.

### Проверено

- `check_font.py` по всем трём файлам:
  - не больше оригиналов Legacy, контрольные суммы таблиц и `checkSumAdjustment` верны;
  - `name` — Legacy байт в байт; вес, ширина, `fsSelection`, `macStyle` и вертикальные метрики — Legacy;
  - строки `font_extents.txt` по формуле — как у оригиналов;
  - все символы Legacy есть;
  - глифы (332/332, 332/332, 325/325), ширины и `fpgm`/`prep`/`cvt` — NHL 12 байт в байт;
  - рисунок общих символов совпадает со сборкой, что стоит в NHL 13 (`game/work/fonts/out-nhl12`),
    кроме ®.
- `coverage --game legacy`: проверены английская локализация и база, которые стоят в `cache:` порта
  Legacy, и составы 2026/27 (`--db` с базой NHL 13). Все символы, которые есть в шрифтах Legacy, есть
  и в сборке. С `--all-loc` (все 8 файлов локализации Legacy) нет только символов, которых нет и в
  оригинале (Ą Ć Ł Ń Ő Ś Ű Ż и иероглифы списка языков).
- Превью — `game/work/legacy-data/fe/preview/`: `compare_fonts.png` в четыре колонки (NHL 12 /
  NHL 13 с модом / Legacy / Legacy с модом) и `*_before_after.png` со всеми символами (красным —
  Ę ę из оригинала).
- **В игре** (legacy-data, 08.10.2026 20:18–20:21, порт `nhl-legacy-port`, D3D12 ROV): три файла
  подхватились — в логе нет `FAILED` для `cache:\fe\ion\fonts\EAHelveticaNeue…-Mod.ttf`, падений нет.
  Снимки — `game/work/legacy-data/ingame/` (`t1-orig-*` — оригинал, `t2-font-*` — с модом):
  - Play Now → Select Teams: заголовок, «COYOTES®», «DUCKS™», «VS», нижняя панель подсказок;
  - Starting Lineups;
  - табло: жирнее оригинала.
- NHL 13 (без `--game`): `fefont.py` до и после правок даёт побайтно одно и то же. Проверены сборки,
  отчёты, `coverage`, `compare`, `preview` и прочие команды — см. сообщение коммита.

### Что проверить в игре

- Главное меню: пункты («Hv»), выделение, бегущая строка EA Trax.
- Live the Life и Be a GM — длинные тексты «Med» в окнах.
- Таблицы статистики — ряды цифр (цифры NHL 12 на 3–4,5 % шире, чем у Legacy).
- Арена «Xcel Energy Center ℠».

## Не проверено

- Кернинг: у шрифтов NHL 12 и NHL 13 его нет, применяет ли интерфейс таблицу `kern` своих шрифтов
  (у `TextFormat` в Apt есть флаг `kerning`, встречается `kerning="1"` в `nhlbackgroundcard.big`).
- Жёсткий буфер под файлы шрифтов: в коде его нет, буфер выделяется по размеру файла (раздел
  «NHL Legacy», загрузчик тот же, что в NHL 13). Сборки всё равно не больше оригиналов.
- Тексты с `Arial` (отладочные экраны) по-прежнему без шрифта: `arial.ttf` в `fonts.txt` есть, файла нет.
- Вариант «под NHL 13» (`out-nhl12-cap`) в игре не запускался (тот же шрифт крупнее на 4,7 %).
