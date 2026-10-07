# Файлы игры

Источник — установка с диска с приставки (см. [xbox-transfer.md](xbox-transfer.md)).

## Распаковка

```bash
python tools/svod.py verify game/raw/Hdd1/Content/0000000000000000/4541099B/00004000/DE1A9BB72C06CB1041B3EC10583EFE34
python tools/svod.py extract game/raw/Hdd1/Content/0000000000000000/4541099B/00004000/DE1A9BB72C06CB1041B3EC10583EFE34 game/extracted/disc
python ref/nhl-legacy-recomp/docs/nhl12-decomp-reference/tools/unpack_big.py game/extracted/disc/cache.big -o game/extracted/big --pattern '^(db|fe/loc)/'
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

В отличие от NHL 12 (`data0.big`), в NHL 13 база лежит в **`cache.big`**:

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

## Ещё посмотреть

- `boot.big`: `fe/dynamicsettings.txt`, `sku/na.ini`, `fe/dime/*.xml` — кандидаты на
  конфиг со стартовым годом.
- Апдейт TU2 (`tu00000002_00000000`, пакет STFS `LIVE`) — что в нём кроме патча `default.xexp`.
