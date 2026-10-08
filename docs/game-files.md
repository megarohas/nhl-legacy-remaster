# Файлы игры

Источник — установка с диска с приставки (см. [xbox-transfer.md](xbox-transfer.md)).

## Распаковка

```bash
python tools/svod.py verify game/raw/Hdd1/Content/0000000000000000/4541099B/00004000/DE1A9BB72C06CB1041B3EC10583EFE34
python tools/svod.py extract game/raw/Hdd1/Content/0000000000000000/4541099B/00004000/DE1A9BB72C06CB1041B3EC10583EFE34 game/extracted/disc
python ref/nhl-legacy-recomp/docs/nhl12-decomp-reference/tools/unpack_big.py game/extracted/disc/cache.big -o game/extracted/big --pattern '^(db|fe/loc)/'
```

Архивы удобнее распаковывать каждый в свою папку (`game/extracted/big/boot`,
`…/cache`, `…/tu2-patch`), а потом разжимать вложенное сжатие: около 400 файлов внутри
`.big` (`.lnb`, `.xml`, `.json`, `.bin`, `.lua`, текстуры) дополнительно упакованы
EA `chunklzx` — LZX в кадрах XMemCompress с окном 2^17. `unpack_big.py` знает только
`chunkzip` (deflate) и оставляет их как есть:

```bash
python tools/unchunk.py game/extracted/big
```

Весь диск за раз — `tools/big.py`: каждый `.big`/`.viv` в свою папку, вложенное сжатие
(chunkzip/chunklzx, RefPack) снимается сразу, пулом процессов — LZX на чистом Python
медленный (~3,5 МБ/с на ядро), так NHL 12 целиком распаковывается минут за десять:

```bash
python tools/big.py disc game/extracted/disc game/extracted/big            # --only/--exclude по архивам, --pattern по файлам
python tools/big.py list game/extracted/disc/cache.big --pattern '^db/'
```

Исполняемый файл — расшифровка и разжатие в образ памяти (база 0x82000000):

```bash
python tools/xex.py extract game/extracted/disc/default.xex game/extracted/xex/default.bin
```

`ref/` — клоны [nhl-legacy-recomp](https://github.com/puckhead73/nhl-legacy-recomp) и
[nhl-modding-studio](https://github.com/puckhead73/nhl-modding-studio) (`git clone --depth 1`).
В git-консоли Windows для кириллицы в выводе — `PYTHONUTF8=1`.

## Содержимое диска (`game/extracted/disc/`, 20 файлов, 5,88 ГБ)

| Файл | Размер | Формат | Записей |
|---|---:|---|---:|
| `default.xex` | 9,4 МБ | XEX2 | |
| `nocache.big` | 2,48 ГБ | BigEB v3 | 322 |
| `nocacherender.big` | 1,64 ГБ | BigEB v3 | 10 173 |
| `cacherender.big` | 1,10 ГБ | BigEB v3 | 10 969 |
| `cache.big` | 427 МБ | BigEB v3 | 14 235 |
| `cacheaudio.big` | 79 МБ | BigEB v3 | 7 |
| `gamedata/nis.big` | 77 МБ | BigEB v3 | 326 |
| `data0.big` | 28 МБ | BigEB v3 | 2 (только анимации) |
| `cachemovie.big` | 10,6 МБ | BigEB v3 | 6 |
| `boot.big` | 10 МБ | BigEB v3 | 592 |
| `gamedata/anim/faceposer.big` | 6,9 МБ | BigEB v3 | 817 |
| `audioboot2.big`, `audioboot.big`, `cacheoverlay.big`, `gamedata/aidata.big` | мелкие | BigEB v3 | |
| `gamedata/gps.big`, `options.viv` | < 2 КБ | BIG4 | |
| `$SystemUpdate/` | 12 МБ | системное обновление с диска | |
| `nxeart` | 1,6 МБ | картинки для дашборда | |

## База

База лежит в **`cache.big`** — как и у NHL 12 (предположение вводной про `data0.big` не
подтвердилось: у обеих там только анимации; см. раздел про другие выпуски ниже):

| Файл в архиве | Размер | SHA-1 |
|---|---:|---|
| `db/nhlng.db` | 2 695 068 | `1e1063ae8aa67e89fcd0d5f5d19087bca661c5e5` |
| `db/nhlng-meta.xml` | 438 494 | `c48a222833fc5624e6516a0868f7a075a4d7ed6d` |
| `db/draft_roster.db` | 1 639 900 | |
| `fe/loc/nhl_<язык>.db` + `-meta.xml` | | локализация: cze, eng, fin, fre, ger, lng, rus, swe |

Все четыре сверенных файла (`nhlng.db`, `nhlng-meta.xml`, `draft_roster.db`,
`nhl_eng_us.db`) побайтово совпадают с анкерными в nhl-modding-studio
(`anchors/xbox360/nhl13/databases/`) — выводы вводной по базе верны и для нашей копии.
Проверено `tools/tdb_read.py`: 136 таблиц, `exhibitionteams` 248 строк,
`exhibitionplayerbiotable` 5412 игроков с годами рождения 1960–1996.

`default.xex` (диск, без TU): SHA-1 `f4585cafe27bccd9bf68831f0bf1428907f5774a`.
Внутреннее имя `nhlzf.exe`, точка входа `0x82707550`, образ 0x1BB0000 байт, 11 секций
(`.text` 0x823F0000, 20 МБ; `.pdata` — 75 355 функций). Образ (`default.bin`):
SHA-1 `465b937a09c2819809c6f1a5c32f7c9b9d1e8f4e`; разжатие сверено с `expand.exe`.

## Апдейт TU2

```bash
python tools/stfs.py verify game/raw/Hdd1/Content/0000000000000000/4541099B/000B0000/tu00000002_00000000
python tools/stfs.py extract game/raw/Hdd1/Content/0000000000000000/4541099B/000B0000/tu00000002_00000000 game/extracted/tu2
```

Пакет `LIVE` «NHL® 13 Title Update», версия 2, media ID `583EFE34` — тот же, что у
установки с диска, то есть апдейт именно к этому выпуску. Хеши STFS сходятся.

| Файл | Размер | SHA-1 | Что |
|---|---:|---|---|
| `default.xexp` | 3 235 840 | `b3af7f5f02f719dcb12e7ae82547faeda93404c3` | дельта-патч к `default.xex` (XEX2) |
| `patch.big` | 6 801 728 | `7ab034c60dd18d4aab5ec0a5addd2d96893398fd` | BigEB v3, 94 записи |

`patch.big` заменяет файлы интерфейса (`fe/ion/…`, 49 шт.), сценарии (`scenario/…`),
шлемы и джерси, `shaders/skatespray.fxo`, а также `sku/na.ini`,
`fe/dime/nhldimecfg.xml` и `fe/gm_easy.bin` / `gm_med.bin` / `gm_hard.bin`.
**Базы (`db/`, `fe/loc/`) в апдейте нет** — `nhlng.db` с диска актуальна.

Legacy-порт собирается с чистого `default.xex` с диска и отказывает дампам с
применённым апдейтом. Для NHL 13 база порта (диск или диск + TU2) — решить позже.

## Другие выпуски: NHL 12, NHL 10, NHL Legacy (08.10.2026)

Скачаны с той же приставки ([xbox-transfer.md](xbox-transfer.md)) целиком, по одному
файлу с докачкой; размеры всех частей совпали со списком FTP, хеши SVOD сходятся у всех
трёх. Как и у NHL 13 — только локально: `game/raw/…` (пути как на FTP) и
`game/other/<игра>/{disc,big,xex}`, где игра — `nhl12`, `nhl10`, `legacy`.

| Игра | Путь на `Hdd1/Content/0000000000000000/` | Контейнер | Части | Размер |
|---|---|---|---:|---:|
| NHL 12 | `45410964/00004000/1E94C49AACBDE8FCCC4A306441AF51B7` + `.data/` | установка с диска, `CON` «NHL™ 12», media `41AF51B7`, EGDF | 36 (35 × 170 459 136 + 100 597 760) | 5,65 ГБ |
| NHL 10 | `454108BA/00004000/9DE1354418BB2C56EF6123E2300A1040` + `.data/` | установка с диска, `CON` «NHL™ 10», media `300A1040`, EGDF | 32 (31 × 170 459 136 + 33 910 784) | 4,95 ГБ |
| NHL Legacy | `NHL Legacy Edition/454109EC/00007000/909EDC26CA678C976F55` + `.data/` | GoD, `LIVE` «NHL™ Legacy», media `3CF2A23F`, без EGDF (XSF) | 39 (38 × 170 459 136 + 5 525 504) | 6,04 ГБ |

Апдейтов (`000B0000`) ни к одной из трёх на приставке нет — ни в `Content`, ни в
`Hdd1/Cache`. Остальное хоккейное, чтобы не искать снова: `454109DC` — NHL 15 (по имени
папки; GoD `NHL15/454109DC/00007000/20422264A023376375CB`, заголовок не читали; папка
`454109DC/00004000/A10CE0D14FAD14527BE8F55B5F460E79.data` — пустая, без заголовка),
`454109BE` — NHL 14 (установка с диска), одинокий
`4541094C/000B0000/tu00000002_00000000` — апдейт NBA JAM, в `Hdd1/Cache` — апдейт NHL 2K10.
Title ID Legacy `454109EC` — тот же, что в трассах nhl-legacy-recomp (`454109EC_stream.xtr`).

### Распаковка

```bash
H=game/raw/Hdd1/Content/0000000000000000/45410964/00004000/1E94C49AACBDE8FCCC4A306441AF51B7
python tools/svod.py verify $H && python tools/svod.py extract $H game/other/nhl12/disc
python tools/big.py disc game/other/nhl12/disc game/other/nhl12/big
python tools/xex.py extract game/other/nhl12/disc/default.xex game/other/nhl12/xex/default.bin
```

Legacy лежит как GoD без флага EGDF (так пишет Iso2God): в `Data0000` по 0x2000 —
заголовок `XSF`, магия GDF — по 0x12000, блоки без сдвига на 0x1000; `svod.py` различает
раскладки сам (`info` печатает `раскладка XSF`).

| | NHL 12 | NHL 10 | NHL Legacy |
|---|---|---|---|
| `disc/` | 17 файлов, 5,61 ГБ | 77 файлов, 4,93 ГБ | 171 файл, 6,01 ГБ |
| `big/` | 37 292 файла, 11,5 ГБ | 22 107 файлов, 8,0 ГБ | 45 846 файлов, 12,45 ГБ |
| формат архивов | BigEB v3 (+ BIG4 `gps`, `options.viv`) | **BIG4** + `.bh`, сжатие RefPack | BigEB v3 (+ BIG4 `gps`, `options.viv`) |
| база `nhlng.db` | `cache.big` → `db/` | отдельным файлом `disc/db/nhlng.db` (`-meta.xml` — в `boot.big`) | `cacheboot.big` → `db/` (+ `dynamic_ratings.db`) |
| `default.xex` → образ | 0x1A10000 байт, вход 0x828588A8, версия 4 | 0x1650000, вход 0x82B6C280, версия 2 | 0x1EA0000, вход 0x82899A80, версия 4 |

Базы и английская локализация всех трёх (`nhlng.db`, `nhlng-meta.xml`, `draft_roster.db`,
`nhl_eng_us.db` и т. д.) побайтно совпадают с анкерными в nhl-modding-studio
(`anchors/xbox360/{nhl10,nhl12,nhllegacy}/databases/`).

### NHL 12

| Архив | Размер | Записей | Что |
|---|---:|---:|---|
| `nocache.big` | 2,28 ГБ | 345 | |
| `nocacherender.big` | 1,72 ГБ | 9 711 | 3 353 записи — chunklzx |
| `cacherender.big` | 1,16 ГБ | 12 160 | все chunklzx; в `rendering/crowddata/crowd_29.cwd` последний кусок с методом 4 (без сжатия) |
| `cache.big` | 268 МБ | 12 930 | `db/`, `fe/loc/`, `fe/ion/fonts/` |
| `gamedata/nis.big` | 127 МБ | 759 | chunkzip |
| `data0.big` | 22 МБ | 2 | только анимации (`anim.cba`, `crowd.cba`) |
| `boot.big` | 9,3 МБ | 552 | `fe/ion/main.big` (вложенный BIGF) |
| `gamedata/anim/faceposer.big`, `audioboot*.big`, `gamedata/aidata.big` | мелкие | | |

Шрифты интерфейса — те же файлы по именам, что у NHL 13 (`fe/ion/fonts/EAHelveticaNeue{ConBol,Med,Hv}-Mod.ttf`,
внутри — семейство EA HelveticaNeue), но сами TTF другие; `fonts.txt`, `font_extents.txt`,
`rockeb.ttf` — побайтно как в NHL 13 (подробнее — [fe-fonts.md](fe-fonts.md)).
`default.xex`: SHA-1 `ce92b50bd5424cfbb745bb6af2734b0dbe4eec50`, образ 27,3 МБ — как в описании
`nhl12-decomp-reference`.

### NHL 10

Старый формат EA **BIG4**: `BIG4`, размер архива (LE), число записей и размер индекса (BE),
записи «смещение, размер (BE), имя\0», после индекса метка `L286`. Почти все записи (кроме
звука и `nis.big`) сжаты **RefPack** (`10 FB` + 3 байта полного размера); внутри — обычные `.rx2` RenderWare 4
(`RW4xb2`, как у NHL 13). Рядом с каждым архивом `.bh` (`Viv4`) — копия индекса по 16 байт:
смещение, сжатый и полный размер, хеш имени; для распаковки не нужен. Часть данных лежит на
диске отдельными файлами: `db/nhlng.db`, `fe/loc/*.db`, ролики `fe/movies/*.vp6`,
`rendering/transition/*.vp6`, звук `audio/**/*.sbs`, `*.ast`, анимации `gamedata/anim/*.cba`.

| Архив | Размер | Записей | Что |
|---|---:|---:|---|
| `rendernocache.big` | 1,19 ГБ | 2 569 | `rendering/jersey` (1 157), `cz*` (конструктор формы), `crowd`, `tunnel`, `trapper` |
| `player.big` | 415 МБ | 1 658 | `rendering/player` — головы и волосы |
| `rendercache.big` | 364 МБ | 4 785 | `rendering/{sock,logo,pant,helmet,goaliehelmet,body,glove,skate,stick,visor,…}` |
| `stadium.big` | 314 МБ | 343 | арены |
| `fe.big` | 236 МБ | 11 009 | интерфейс |
| `gamedata/nis.big` | 114 МБ | 522 | без сжатия |
| `audio.big` | 96 МБ | 217 | |
| `boot.big` | 1,8 МБ | 150 | `rendering/skeleton_bindpose/skeleton_bindpose_{player,goalie}.rx2`, `db/nhlng-meta.xml` |
| `data0.big`, `audioboot*.big`, `gamedata/{aidata,gps,anim/faceposer}.big`, `options.viv` | мелкие | | в `options.viv` имя файла с путём сборочной машины `C:\polaris\NHL10\…\options.txt` |

### NHL Legacy

| Архив | Размер | Записей | Что |
|---|---:|---:|---|
| `nocache.big` | 2,14 ГБ | 9 707 | |
| `nocacherender.big` | 1,81 ГБ | 3 237 | все chunklzx |
| `cacherender.big` | 1,36 ГБ | 12 845 | все chunklzx, кроме одной |
| `cache.big` | 298 МБ | 17 760 | |
| `cacheaudio.big` | 76 МБ | 7 | |
| `gamedata/nis.big` | 76 МБ | 321 | chunkzip |
| `cacheboot.big` | 30 МБ | 61 | `db/` (`nhlng.db`, `draft_roster.db`, `dynamic_ratings.db`), `fe/loc/`, `fe/ion/fonts/` |
| `data0.big`, `boot.big`, `cachemovie.big`, `renderboot.big`, `cacheoverlay.big`, `audioboot*.big`, `gamedata/…`, `options.viv` | мелкие | | |

`default.xex`: SHA-256 `d818eb15775c1fee34b057b0fc494b211535d07123230ee45bd7d40991c55624`,
SHA-1 `59b67c630fc3e352316591ec0564a3835a792dc4`; образ — SHA-1
`4e377a339c56fa76a7c60175c02528f47a74ca48`. Та же сборка, под которую сделан
nhl-legacy-recomp: на месте setjmp `0x830801C0` (`lis r4,0x83E0; lwz r0,0x22E0(r4); … bnectr`
— слот `0x83E022E0` из `nhllegacy_manifest.toml`) и longjmp `0x8307E1B0`.

## Ещё посмотреть

- `boot.big`: `fe/dynamicsettings.txt`, `sku/na.ini`, `fe/dime/*.xml` — кандидаты на
  конфиг со стартовым годом; `fe/gm_*.bin` из TU2.
