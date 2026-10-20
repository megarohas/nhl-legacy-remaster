# Дампы Frostbite (NHL 24 PS4 → NHL 27 PS5): чтение, допущения, первое знакомство с новым дампом

20.10.2026. Как устроено чтение дампа NHL 24 нашими инструментами `tools/fb/`, что в нём жёстко завязано на PS4 и
NHL 24 и как проверить новый дамп (NHL 27, PS5) до массовой выгрузки. Перенос форм — [kitport.md](kitport.md),
голов — [heads-nhl24.md](heads-nhl24.md), портретов — [player-photos-nhl24.md](player-photos-nhl24.md), план по
текстурам — [nhl24-textures.md](nhl24-textures.md). Дамп и всё выгруженное — только для личного использования
(в `game/`, вне git).

## 1. Какой дамп читается: `fb.source`

Все модули чтения (`scan`, `catalog`, `toc`, `extract`, `orphans`, `lfs`, `heads`, `kit3d`, `verify`, `gallery`)
берут пути из `tools/fb/source.py`. По умолчанию — NHL 24, другой источник выбирается переменными окружения, без
правки кода:

| Переменная | По умолчанию | Что |
|---|---|---|
| `FB_GAME` | `nhl24` | имя источника: дамп `game/other/<FB_GAME>/Data`, работа `game/work/<FB_GAME>` |
| `FB_DATA` | `game/other/<FB_GAME>/Data` | своя папка Data |
| `FB_PATCH` | `Patch` рядом с Data, если есть | папка патча: записи TOC с `patch` ≠ 0 читаются оттуда (ключ места `patch/ipNN/cas_MM`) |
| `FB_WORK` | `game/work/<FB_GAME>` | рабочая папка: `catalog/`, `extract/`, `out/` |
| `FB_PLATFORM` | по файлу `initfs_<платформа>` | платформенная папка внутри Data (NHL 24 PS4 — `Gen4b`) |
| `FB_PACKAGE` | `nhl_installpackage_` | префикс папок пакетов в `<платформа>/superbundlelayout` |

- **Oodle** (`ooz.dll`) — свой в `<работа>/bin/`, иначе общий `game/work/nhl24/bin/ooz.dll`.
- **Что видят инструменты** — `python -m fb.source` (из `tools/`).
- **Модули переноса** (`pilot`, `jersey_mesh`, `edge_kit`, `photos24`, `scans24` …) пишут выход по путям NHL 24.
  Для второго источника их надо будет параметризовать отдельно.

## 2. Как читается дамп NHL 24

**Дамп** — `game/other/nhl24/Data`, NHL 24 v1.00, PS4:

| Файл | Формат | Кто читает |
|---|---|---|
| `layout.toc` | подпись `00 D1 CE 01`, заголовок 0x22C, дальше DbObject `{superBundles, fs, head, installManifest}` | `fb.probe` |
| `initfs_Gen4b` | то же, DbObject с полем `encrypted` — **зашифрован** | никто |
| `chunkmanifest` | DbObject: `Version` 3.0, `chunks[{id, empty, installPackageId}]` | никто |
| `Gen4b/*.toc`, `Gen4b/levels/game/game.toc` | `00D1CE01` + 0x22C, дальше двоичный TOC (BE, 15 × u32, `hdr[0]` = 0x3C) | `fb.toc` |
| `Gen4b/superbundlelayout/nhl_installpackage_NN/cas_MM.cas` | блоки CAS и двоичные манифесты бандлов внутри (отдельных `.sb` нет) | `fb.scan`, `fb.extract` и все остальные |

Сейчас в дампе 26 CAS на 24 ГБ. Изначально их было 36: 15.10 удалили видео, звук и 4 CAS
(`game/work/cleanup-audit/report.md`). Типы EBX лежат в исполняемом файле, в дампе их нет.

**Порядок** (из `tools/`, venv `game/work/nhl24/venv`: Python 3.14, numpy, pillow, scipy, zstandard):

| # | Команда | Выход |
|---|---|---|
| 0 | `tools\fb\build_ooz.cmd` (ooz из GitHub, VS 2022 Build Tools + clang-cl) | `game/work/nhl24/bin/ooz.dll` |
| 1 | `python -m fb.probe` | первое знакомство (§4), ничего не пишет |
| 2 | `python -m fb.scan [--jobs 3] [--only …]` | `catalog/scan/ipNN_cas_MM.jsonl`: bundle/ebx/res/chunk/orphan/gap; 20–45 с на CAS |
| 3 | `python -m fb.catalog` | `restypes.csv`, `textures.csv`, `prefixes.csv`, `chunks.idx.json` |
| 4 | `python -m fb.toc stats`, `python -m fb.toc index` | `toc_chunks.json` (GUID → место); `index` — после `catalog` |
| 5 | без TOC: `python -m fb.orphans`, `--pass2`, `--streams` | `orphan_map.json` — чанки, найденные по sha1 манифестов |
| 6 | `python -m fb.extract REGEX --out ИМЯ [--list] [--no-detile]` | `extract/ИМЯ/<путь>.png` + `_index.csv` |
| 7 | `python -m fb.verify`, `python -m fb.gallery build`, `python -m fb.lfs list/get` | сверка sha1, галерея свитеров, legacy-файлы (база `nhl_game.db`) |

**Путь одной текстуры:**
1. запись `res` в scan jsonl;
2. заголовок `Texture` (132 байта) из CAS;
3. GUID чанка;
4. место чанка: сначала `toc_chunks.json`, потом `orphan_map.json`, потом `chunks.idx.json`;
5. распаковка (Oodle, ZStd или zlib);
6. детайлинг PS4 и BCn → PNG.

## 3. Допущения о формате — что сломается на новом дампе

| Модуль | Допущение (NHL 24) | Если не так |
|---|---|---|
| `fb.source` | платформа по `initfs_*`, пакеты `nhl_installpackage_` | `fb.probe` подскажет `FB_PLATFORM`, `FB_PACKAGE` |
| `fb.toc` | подпись `00D1CE01`, заголовок 0x22C, данные BE `>15I`; бандл `>IIQ` + `>5I`; чанк — 20 байт GUID (обратный порядок) + u32, запись `>4B` (?, patch, catalog, cas) + `>II` | ошибка «не TOC 00D1CE01». **`hdr[0]` (0x3C) не проверяется** — другая длина заголовка пройдёт молча; `fb.probe` её показывает |
| `fb.cas` | блок — 8 байт BE `>IBBH`: распакованный размер (24 бита), тип сжатия, флаги (`& 0xF0 == 0x70`), сжатый размер (+4 бита); блок ≤ 0x40000; сжатие 0x00 / 0x02 zlib / 0x0F ZStd без словаря / 0x11, 0x15, 0x19 Oodle | `fb.probe` шаг 4: «не блок CAS», «неизвестный тип сжатия», «Oodle: распаковано n из m». LZ4 (0x09) не реализован |
| `fb.bundle` | манифест: u32 BE (размер), дальше LE; магии `9D798ED6`, `9D798ED5`, `ED1CEDB8`; sha1 — сжатых байт с заголовками блоков | другая магия → 0 бандлов, всё уйдёт в orphan/gap. Ошибки meta глотаются молча |
| `fb.dbobject` | байт типа: 5 бит тип, 0x80 — без имени; varint; числа LE | ошибка «неизвестный тип 0x..» |
| `fb.scan` | за манифестом подряд его ebx, res, chunks; поиск следующего манифеста по магии в окне 1 МБ | записи `missing`, большие `gap` |
| `fb.texture` | заголовок `Texture` 132 байта LE (GUID чанка @32, `mipSizes` @48, nameHash @112); **детайлинг PS4 GNM Thin_1dThin** (микротайлы 8×8 в порядке Мортона, выравнивание до 8 элементов, без макротайлов и упаковки хвоста мипов); форматы 6, 11, 18/20, 23/24, 54–63, 66/67 (BC1–BC5, BC7) | **на PS5 тайлинг другой** (AGC: блоки 4/64 КБ с XOR, хвост мипов упакован) — ошибки не будет, будет мусорная картинка. Неизвестный формат — ошибка «формат N не поддержан». BC6H, float, 16-бит не поддержаны |
| `fb.meshset`, `fb.heads` | MeshSet `0x49B156D4`: LOD @0x20; +0x08 число и смещение секций; +0x58/+0x5C размеры буферов; +0x60 GUID чанка; секция: +0x20 ntri, +0x24 first, +0x28 voff, +0x2C nv, +0x4C 16 элементов, +0x8C шаги потоков; **шаг секции 0xC0 у свитера, 0xE0 у головы**; индексы u16; потоки подряд (SoA) | ошибки нет, числа вершин и рамка — бред. **`heads.py` молча пропускает неизвестный формат вершин** |
| `fb.lfs` | `globals/chunkfilecollector`: GUID @+0x60, записи с +0x68 по 0x38 байт | база игры не найдётся |
| `fb.extract` | место из TOC — весь поток; частичный чанк (хвост с `first_mip`) | ошибка длины или sha1 |

ID типов res (Texture `0x6BDE20BA`, MeshSet `0x49B156D4`) — хеши имён типов, обычно стабильны. Меняется содержимое.

## 4. Первое знакомство с новым дампом (NHL 27 PS5)

### 4.1. Что получить с консоли

- **Папку `Data` целиком** (TOC, `initfs_*`, `layout.toc`, `chunkmanifest`, `superbundlelayout/**`) и **`Patch`**, если
  есть. Без `*.toc` теряется ≈ 8 000 чанков и вся геометрия экипировки — у NHL 24 так и было (`need_from_ps4.txt`).
- **Исполняемый файл** (расшифрованный): в нём типы EBX и, возможно, ключ initfs.
- **Если есть NHL 24 для PS5** — одна и та же текстура в двух дампах (тот же GUID и sha1 исходника) сразу даст
  алгоритм детайлинга PS5.

Положить в `game/other/nhl27/` — вне git.

### 4.2. Порядок

```bash
cd tools
P=../game/work/nhl24/venv/Scripts/python.exe
FB_GAME=nhl27 $P -m fb.source                          # пути, которые увидят инструменты
FB_GAME=nhl27 $P -m fb.probe                           # шаги 1–5 ниже, только чтение
FB_GAME=nhl27 $P -m fb.scan --only nhl_installpackage_00/cas_01   # один CAS
FB_GAME=nhl27 $P -m fb.catalog                         # restypes.csv: есть ли 0x6BDE20BA и 0x49B156D4
FB_GAME=nhl27 $P -m fb.toc index
FB_GAME=nhl27 $P -m fb.extract 'playerportraits/p.*' --out probe --limit 3          # с детайлингом PS4
FB_GAME=nhl27 $P -m fb.extract 'playerportraits/p.*' --out probe_lin --limit 3 --no-detile   # без
```

`fb.probe` проверяет:
1. **Дерево:**
   - платформенную папку (NHL 24 — `Gen4b`; у PS5 будет другая);
   - `*.toc`, отдельные `*.sb`;
   - пакеты и CAS, `Patch`.
2. **Подписи и DbObject:**
   - `layout.toc` — список суперандлов;
   - `initfs` — открыт ли.
3. **Оглавления:**
   - `hdr[0]` (0x3C у NHL 24), число бандлов и чанков;
   - распределение байта `patch`;
   - есть ли на диске все CAS, на которые ссылаются оглавления.
4. **Первый CAS:**
   - манифест в начале;
   - блоки через манифесты (типы сжатия);
   - пробная распаковка блока каждого типа.
5. **Один чанк** по месту из TOC.

Эталон NHL 24 (20.10):
- `Gen4b`;
- суперандлы `contentlaunchsb`, `contentsb`, `globals`, `globalsfull`, `game`, `movies`, `ui`, `worldssb`;
- initfs зашифрован;
- `hdr[0]` = 0x3C у всех 8 TOC; `patch` = 0 у всех 1,9 млн записей;
- блоки: Oodle 0x11 и без сжатия;
- чанк 37 270 → 177 152 байт.

### 4.3. Дальше — эталоны

- **Каталог:**
  - в `restypes.csv` должны быть `0x6BDE20BA` и `0x49B156D4` (у NHL 24 — 306 519 и 16 813, всего 21 тип);
  - `size` у Texture — 132.
- **Текстура-эталон** — портрет `ui/textures/common/playerportraits/p<ID>` или `systems/render/lighting/bluenoise16x16_rgb`:
  - `--list` — правдоподобны ли формат и размеры (`fmtNN` — неизвестный номер формата);
  - PNG с детайлингом и без (`--no-detile`). Если оба — мусор, нужен детайлер PS5 в `fb/texture.py`.
- **Сетка-эталон:**
  - свитер `player_jersey_adidas_notuck_large_lod0_mesh` — у NHL 24 3160 вершин, 5962 треугольника, рамка x ±0,51 м;
  - голова `mat_head` — 3157 вершин, та же развёртка, что у Legacy (главное допущение переноса голов —
    [heads-nhl24.md](heads-nhl24.md), «Новый источник»).

  Если числа бредовые — сдвинулись смещения MeshSet.
- **База игры** — `fb.lfs list nhl_game` (TDB little-endian): имена полей, диапазон ID EA. Ограничение Legacy:
  `headid`/`artid` — 16 бит, 60000+ заняты типовыми головами.

## 5. Что известно про PS5 (общие знания, на нашем дампе не проверено)

- **Платформенная папка** — скорее всего не `Gen4b`: по аналогии `Gen4a` — Xbox One, `Gen4b` — PS4.
- **Тайлинг текстур PS5** (RDNA2, AGC) не похож на GNM 1dThin PS4: блоки 4/64 КБ с XOR-перестановкой, мелкие мипы в
  хвосте.
- **Заголовок Texture** может получить новые поля или другую длину; нумерация форматов может сдвинуться, BC7 станет
  частым.
- **Oodle Kraken** на PS5 аппаратный, формат потока, вероятно, тот же. Возможны ZStd со словарём, зашифрованные
  бандлы или чанки (ключ в exe).
- **Патч** почти наверняка есть: байт `patch` ≠ 0, файлы в `Patch/`.
- **Новая магия манифеста** бандла или поля TOC — проверяется шагами 3–4 `fb.probe`.
