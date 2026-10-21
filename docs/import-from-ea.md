# Импорт из новой EA NHL в NHL Legacy

Как перенести в NHL Legacy данные и ассеты из более новой EA NHL на движке Frostbite: составы, рейтинги, статистику,
портреты, головы, формы. Проверено на NHL 24 (PS4) и NHL 27 (PS5, 21.10.2026). Одна точка входа —
[tools/eaimport.py](../tools/eaimport.py); каждая команда вызывает отдельный инструмент со своим описанием.

Ассеты и база EA — только для личного использования: дамп лежит в `game/other/<игра>/Data`, всё рабочее — в
`game/work/…` (вне git).

## Порядок

```bash
python tools/eaimport.py status    --game nhl27     # что готово
python tools/eaimport.py prepare   --game nhl27     # проход по CAS, каталог, индекс TOC, база игры (один раз)
python tools/eaimport.py leagues europe             # составы SHL, DEL, Extraliga, NL
python tools/eaimport.py leagues chl                # составы OHL, QMJHL, WHL
python tools/eaimport.py stats                      # история статистики НХЛ/АХЛ
python tools/eaimport.py portraits                  # портреты тем, у кого их нет
python tools/eaimport.py heads --only macklin_celebrini   # пилот головы; без --only — все сопоставленные
python tools/eaimport.py overlay                    # накладка out-nhl24 из новых баз (формы pack-edge)
python tools/legacy_data/install_legacy_data.py status   # что изменит установка; install — при закрытой игре
cp nhl-legacy-port/userdata/cache/guest/db/nhlng.db game/work/legacy-data/roster-merge/old-cache-nhlng.db   # до установки
cd tools && python -m kitport install --tag <метка> --yes && cd ..                  # установка с копией заменяемого
python tools/legacy_data/roster_merge.py "<ROSTER>" --old game/work/legacy-data/roster-merge/old-cache-nhlng.db        --new game/work/legacy-data/out-nhl24-ahl32/db/nhlng.db --write              # перенос в сейв ROSTER
```

`all` делает leagues europe → chl → stats → portraits; головы и накладка — отдельно. Те же шаги есть этапами
`tools/legacy_data/build-all.sh` (`europe`, `chl`, `stats27`, `photos24`, `scans24`, `nhl24`).

## Что за чем стоит

| Шаг | Инструмент | Документ | Что меняет |
|---|---|---|---|
| чтение дампа | `tools/fb` (`fb.source`, `fb.probe`, `fb.scan`, `fb.catalog`, `fb.toc`, `fb.extract`, `fb.lfs`) | [frostbite-sources.md](frostbite-sources.md) | ничего, только читает |
| база игры | `fb.lfs get gamemodes/database/t3db/nhl_game.db`, `tools/tdb.py` (LE-базы), `roster/nhl27.py` | frostbite-sources.md §5 | `game/work/<игра>/db` |
| составы лиг | `legacy_data/league27.py chl\|europe` | [legacy-data.md](legacy-data.md), «Лиги из NHL 27» | составы, био, атрибуты, звенья, названия клубов в `out` |
| статистика | `legacy_data/stats27.py` | legacy-data.md, «Статистика из NHL 27» | `stockcareer*` в `out` |
| портреты | `photos24.py --source <игра>` | [player-photos-nhl24.md](player-photos-nhl24.md) | `out/fe/…/p<artid>.big`, `hasportrait` |
| головы | `scans24.py --source <игра>`, `fb/heads.py` | [heads-nhl24.md](heads-nhl24.md) | `out/rendering/player`, `headid`, `stockplayerheads` |
| формы | `python -m kitport` (`fb/edge_kit.py`) | [kitport.md](kitport.md) | текстуры форм, накладка `out-nhl24` |

## Решения, которые действуют по умолчанию

- **Наши составы НХЛ и АХЛ, Liiga и пул свободных агентов — главнее.** Их собирает конвейер по свежим данным (сайты
  НХЛ, HockeyTech, liiga.fi); игрок, который у нас в таком клубе, при импорте лиг остаётся там.
- **Сшивка игрока — по человеку** (имя, фамилия, дата рождения, только однозначные пары), не по game_id: конвейер отдаёт
  строки «доноров» новым игрокам.
- **Портреты — только тем, у кого их нет.** Уже стоящие (NHL.com, NHL 24) не заменяются.
- **История статистики** у опознанных — целиком из игры-источника (у EA она полная), у прочих убираются только
  невозможные сезоны (моложе 18).

## Новая игра (NHL 28 и дальше)

1. Положить папку `Data` в `game/other/<игра>/` и запустить `FB_GAME=<игра> python -m fb.probe` (из `tools/`). Он
   покажет, что изменилось в формате: заголовки TOC, записи чанков, блоки CAS.
2. Поправить чтение в `tools/fb` по найденному (как для PS5: `fb/toc.py` `wide_loc`, `fb/texture.py` `PS5_TILES`,
   `fb/heads.py` `LAYOUT`, `fb/lfs.py` `_manifest_v2`) и проверить на эталонах из frostbite-sources.md §4.3.
3. Добавить игру в `GAMES` и `DB_DIR` (`tools/eaimport.py`), `SOURCES` (`tools/photos24.py`). Если изменилась схема
   базы — сверить поля с Legacy, как в `roster/nhl27.py` (кодировки, номер команды `index`, потенциал).
4. Дальше — порядок выше.

## Как проверить результат

- `python tools/legacy_data/install_legacy_data.py status` / `diff` — что поменяется в `cache:`.
- Листы: `photos24.py sheet --source <игра>` (портреты), `scans24.py`-лист в `legacy-data/scans27/` (головы),
  `python -m kitport sheet` (формы).
- `python tools/tdb.py dump out/db/nhlng.db exhibitionplayerbiotable --where lastname=…` — игрок в базе.
- Игра грузит составы из сейва ROSTER, если он загружен: после установки — `roster_merge.py` (легаси-данные,
  «Перенос в сейв ROSTER»), он сохраняет правки пользователя в сейве.
