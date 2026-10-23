#!/bin/bash
# Пересборка всего набора модов-данных NHL Legacy с нуля → game/work/legacy-data/out (дерево как в cache:).
# Описание — docs/legacy-data.md. Ставится потом tools/legacy_data/install-legacy-data.sh (при закрытой игре).
#   bash tools/legacy_data/build-all.sh [ЭТАП…] [--ahl32]
#   LEGACY_DATA_WORK=папка bash tools/legacy_data/build-all.sh …   # сухой прогон: всё (и out) — в эту папку;
#        входы, которые этапом не пересобираются (например, составы без сети), — положить туда заранее
#        этапы: base roster photos equip collect retire fixdb utah ahl europe chl stats27 nhlattrs useredits tape players
#        contracts awards goaliegear photos24 heads scans24 fonts
#        music models art logos menu nhl24
#        (без этапов — все по порядку;
#        --ahl32 — ещё вариант «АХЛ на 32», накладка game/work/legacy-data/out-ahl32; nhl24 — накладка out-nhl24
#        из пакета NHL 24, если он готов: game/work/nhl24/out/pack или NHL24_PACK=папка)
# Сеть: roster — только кэш (--offline); photos — докачка недостающих портретов лиг (пауза ≥ 1 с), остальное — без сети.
# Время (под нагрузкой ПК): base ~1 мин, roster ~6 мин, photos ~15 мин, photos24 ~10 мин, heads ~6 мин (повтор — секунды),
# models ~5 мин, art ~5 мин, music ~2 мин.
# Скрипты и спеки — в git (tools/legacy_data/), в game/work/legacy-data — только выход и временное (с 09.10.2026,
# docs/incident-2026-10-09.md).
set -e
R="$(cd "$(dirname "$0")/../.." && pwd)"
[ -d "$R/game" ] || R="$(cd "$(git -C "$R" rev-parse --git-common-dir)/.." && pwd)"   # из git worktree — основная копия
cd "$R"
T=tools/legacy_data
W=${LEGACY_DATA_WORK:-game/work/legacy-data}
mkdir -p "$W"
WA="$(cd "$W" && pwd)"                       # абсолютный — для шагов, которые идут из другой папки
O=$W/out
L=game/other/legacy/big/cacheboot
AHL32=0
stages=()
for a in "$@"; do [ "$a" = "--ahl32" ] && AHL32=1 || stages+=("$a"); done
[ ${#stages[@]} -gt 0 ] || stages=(base roster photos equip collect retire fixdb utah ahl europe chl stats27 nhlattrs useredits tape players contracts awards goaliegear photos24
                                  heads scans24 fonts music models art logos menu nhl24)
want() { for s in "${stages[@]}"; do [ "$s" = "$1" ] && return 0; done; return 1; }
say() { echo "== $(date +%H:%M:%S) $*"; }

if want base; then
  say "база: 32 команды (nhl32 --game legacy)"
  mkdir -p $W/nhl32
  python tools/nhl32.py $L/db/nhlng.db $W/nhl32/nhlng.db $L/fe/loc/nhl_eng_us.db $W/nhl32/nhl_eng_us.db \
         --meta $L/db/nhlng-meta.xml $W/nhl32/nhlng-meta.xml --game legacy
  if [ $AHL32 = 1 ]; then
    mkdir -p $W/nhl32-ahl32
    python tools/nhl32.py $L/db/nhlng.db $W/nhl32-ahl32/nhlng.db $L/fe/loc/nhl_eng_us.db $W/nhl32-ahl32/nhl_eng_us.db \
           --meta $L/db/nhlng-meta.xml $W/nhl32-ahl32/nhlng-meta.xml --game legacy --ahl32
  fi
fi
# --payroll-max 100: контракты — заглушка по OVR; ведомость состава клуба НХЛ (её и считает игра) ≤ 100 млн при
# потолке 2026/27 в 104 млн (потолок ставит врезка legacy-port; иначе со 2-го сезона игра поднимает его до самой
# дорогой ведомости, а клуб сверх потолка дальше не пускает)
# --fa-only: в пуле свободных агентов — только настоящие (--fa), без 35 свободных агентов Legacy 2015 года
# --retire-veterans 2010: ушедшие из НХЛ игроки базы 2015 года (все: база старше на 11 лет) не занимают мест в клубах
# АХЛ/Европы/CHL — остаются без клуба и во франшизу не попадают (10.10.2026; до этого 94 таких было в клубах, Toews,
# Price, Galchenyuk…). Пока составы не пересобраны с сетью, то же по готовой базе делает этап retire
FLAGS="--offline --game legacy --stats-ratings --fa --fa-only --skin --league liiga --payroll-max 100 --retire-veterans 2010"
if want roster; then
  say "составы 2026/27"
  python tools/roster all $FLAGS
  [ $AHL32 = 1 ] && python tools/roster all $FLAGS --ahl32 --db-in $W/nhl32-ahl32/nhlng.db --work roster-ahl32
fi
if want photos; then
  say "портреты: фото не из НХЛ → кадр НХЛ, сборка, hasportrait"
  python tools/roster photos --game legacy
  python tools/photos.py build --game legacy --jobs 6
  python tools/photos.py db $W/roster/nhlng.db $W/roster/nhlng-photos.db --game legacy
  if [ $AHL32 = 1 ]; then
    python tools/photos.py build --game legacy --jobs 6 --work $W/roster-ahl32
    python tools/photos.py db $W/roster-ahl32/nhlng.db $W/roster-ahl32/nhlng-photos.db --game legacy --work $W/roster-ahl32
  fi
fi
if want equip; then
  say "экипировка по фото"
  (cd tools && python -m roster.equipment --game legacy apply $WA/roster/nhlng-photos.db $WA/roster/nhlng-equip.db \
      --visor-rule --jersey-rule --report $WA/roster/equipment-apply.json)
  [ $AHL32 = 1 ] && (cd tools && python -m roster.equipment --game legacy --work roster-ahl32 apply \
      $WA/roster-ahl32/nhlng-photos.db $WA/roster-ahl32/nhlng-equip.db --visor-rule --jersey-rule \
      --report $WA/roster-ahl32/equipment-apply.json)
fi
if want collect; then
  say "в out: база, схема, локализация, портреты"
  mkdir -p $O/db $O/fe/loc
  cp $W/roster/nhlng-equip.db $O/db/nhlng.db
  # старт франшизы «NHL Entry Draft» читает составы не из nhlng.db, а из db/draft_roster.db (cacheboot.big: 10 таблиц,
  # exhibition* и stockteamsalaryextras, составы драфта 2015) — те же 10 таблиц из нашей базы (draft_roster.py; полная
  # копия nhlng.db давала франшизе 2 лишние таблицы и сейв больше буфера — docs/legacy-data.md, «draft_roster.db»)
  python $T/draft_roster.py $O/db/nhlng.db $O/db/draft_roster.db
  cp $W/roster/nhlng-meta.xml $O/db/nhlng-meta.xml
  cp $W/nhl32/nhl_eng_us.db $O/fe/loc/NHL_ENG_US.db
  cp -r $W/photos-all/fe $O/
  # накладка «АХЛ на 32»: база, схема, локализация и портреты CV/HSK (install-legacy-data.sh --ahl32)
  [ $AHL32 = 1 ] && python $T/make_out_ahl32.py
  [ $AHL32 = 1 ] && [ -f $W/out-ahl32/db/nhlng.db ] && python $T/draft_roster.py $W/out-ahl32/db/nhlng.db $W/out-ahl32/db/draft_roster.db
  echo "   локализация из nhl32 — без правок меню: потом этап menu (menuitems_legacy.py)"
fi
if want retire; then
  # ушедшие из НХЛ игроки базы 2015 года — без клуба по готовой базе (retire_veterans.py: правила write.free_vacancy,
  # docs/legacy-data.md, «Ветераны НХЛ 2015»); составы, собранные с --retire-veterans, не меняются
  say "ветераны НХЛ 2015 — без клуба (retire_veterans.py)"
  python $T/retire_veterans.py $W/nhl32/nhlng.db $O/db/nhlng.db --report $W/roster/retire-veterans.json
  if [ -f $W/out-ahl32/db/nhlng.db ]; then
    python $T/retire_veterans.py $W/nhl32-ahl32/nhlng.db $W/out-ahl32/db/nhlng.db \
           --report $W/roster-ahl32/retire-veterans.json
  fi
  for d in $O/db $W/out-ahl32/db; do
    if [ -f $d/nhlng.db ]; then python $T/draft_roster.py $d/nhlng.db $d/draft_roster.db; fi
  done
fi
if want fixdb; then
  # последний бит записи — флаг движка «запись свободна»: поле на нём (leaguerookiedata.draftteam 58…63 при reclen 8 —
  # до исправления tdb.widen 10.10.2026) прячет строки от игры; у таких таблиц запись +4 байта, поля на местах.
  # Повторный запуск ничего не меняет; draft_roster.db — снова 10 таблиц починенной nhlng.db (draft_roster.py)
  say "база: последний бит записи свободен (fix_flagbit)"
  for d in $O/db $W/out-ahl32/db; do
    if [ -f $d/nhlng.db ]; then
      python $T/fix_flagbit.py $d/nhlng.db
      python $T/draft_roster.py $d/nhlng.db $d/draft_roster.db
    fi
  done
fi
if want utah; then
  # Юта вместо Аризоны (строка 22) и Тусон вместо Springfield (строка 55): спецификация и арт агента utah (docs/utah.md,
  # game/work/utah/utah_spec.json и out/) → база и локализация out (и out-ahl32), арт — в out; без третьей формы
  # (решение 10.10). Повторный запуск ничего не меняет; draft_roster.db — заново (10 таблиц)
  S=${UTAH_SPEC:-game/work/utah/utah_spec.json}
  if [ -f "$S" ]; then
    say "Юта вместо Аризоны, Тусон вместо Springfield (utah.py)"
    python $T/utah.py "$S"
    for d in $O/db $W/out-ahl32/db; do
      if [ -f $d/nhlng.db ]; then python $T/draft_roster.py $d/nhlng.db $d/draft_roster.db; fi
    done
  else
    say "Юта: нет $S — этап пропущен"
  fi
fi
if want ahl; then
  # составы АХЛ 2026/27 (HockeyTech) и свободные агенты на сегодня — на готовой базе, составы НХЛ не меняются
  # (решение пользователя 10.10; docs/legacy-data.md, «АХЛ 2026/27»). Кэш скачивает `python -m roster.ahl_ht
  # teams|ids|players` (сеть — только для АХЛ и свободных агентов); здесь — без сети. Клубы: 8 слотов переименованы,
  # аффилиаты 2026/27, арены; портреты, экипировка по правилам; draft_roster.db — заново
  HT=$(python tools/season.py --ht-id)          # номер сезона HockeyTech (tools/season.py, NHL_SEASON / NHL_AHL_SEASON_ID)
  if [ -n "$HT" ] && [ -f game/work/roster-cache/ahl/ht/teams-$HT.json ]; then
    say "АХЛ 2026/27 и свободные агенты (ahl2026.py)"
    python $T/ahl2026_slots.py $W/out-ahl32/db/nhlng.db
    python $T/ahl2026.py
  else
    say "АХЛ 2026/27: нет кэша HockeyTech — этап пропущен (python -m roster.ahl_ht teams; ids; players)"
  fi
fi
if want europe; then
  # европейские лиги с составами 2015 года (SHL, DEL, Extraliga, NL) — из базы NHL 27 тем же способом (решение пользователя
  # 21.10; Liiga — конвейер с liiga.fi, Норвегии в NHL 27 нет — не трогаются). Выбывшие клубы — пришедшим на их место
  # (новое название). После ahl, до chl (освобождает строки вратарей для CHL) и goaliegear. Повтор ничего не меняет; draft_roster.db — заново
  if [ -f "${NHL27_DB:-game/work/nhl27/db/nhl_game.db}" ]; then
    say "составы SHL, DEL, Extraliga, NL из NHL 27 (league27.py europe)"
    python $T/league27.py europe
  else
    say "Европа: нет базы NHL 27 — этап пропущен"
  fi
fi
if want chl; then
  # составы юниорских лиг CHL (OHL, QMJHL, WHL) — из базы NHL 27 целиком (решение пользователя 21.10; tools/legacy_data/league27.py,
  # docs/legacy-data.md, «Лиги из NHL 27»): имена, даты рождения, атрибуты, права и контракты, номера, звенья; кто у нас
  # в НХЛ/АХЛ — остаётся там, дыры — добор запасными клубов лиги; переехавшие клубы — новые названия. После ahl и europe
  # (строки прежних европейцев — доноры вратарей CHL), до goaliegear (экипировка вратарей клубов). Нужна база NHL 27: game/work/nhl27/db/nhl_game.db
  # (NHL27_DB=путь). Повтор ничего не меняет; draft_roster.db — заново
  if [ -f "${NHL27_DB:-game/work/nhl27/db/nhl_game.db}" ]; then
    say "составы CHL из NHL 27 (league27.py chl)"
    python $T/league27.py chl
  else
    say "CHL: нет базы NHL 27 — этап пропущен"
  fi
fi
if want stats27; then
  # история статистики из NHL 27 (tools/legacy_data/stats27.py, docs/legacy-data.md, «Статистика из NHL 27»): у игроков,
  # опознанных по имени и дате рождения, сезоны НХЛ/АХЛ — из NHL 27 (у EA история полная, на 2025/26); у прочих убираются
  # невозможные сезоны (моложе 18 — чужие строки доноров). После составов (ahl, europe, chl). Повтор ничего не меняет
  if [ -f "${NHL27_DB:-game/work/nhl27/db/nhl_game.db}" ]; then
    say "статистика из NHL 27 (stats27.py)"
    python $T/stats27.py
  else
    say "статистика: нет базы NHL 27 — этап пропущен"
  fi
fi
if want nhlattrs; then
  # атрибуты игроков составов НХЛ — под OVR базы: игра считает OVR из атрибутов (tools/roster/ovrformula.py), а ниже
  # топ-300 EA конвейер 08.10 достраивал их «средним + поправкой» и OVR в игре выходил ниже на 3–12 (координатор 11.10).
  # Меняются только атрибуты этих игроков, топ-300 EA не трогается; повтор ничего не меняет; draft_roster.db — заново
  say "атрибуты игроков НХЛ под OVR базы (nhl_attrs.py)"
  for d in $O/db $W/out-ahl32/db; do
    if [ -f $d/nhlng.db ]; then
      python $T/nhl_attrs.py $d/nhlng.db
      python $T/draft_roster.py $d/nhlng.db $d/draft_roster.db
    fi
  done
fi
if want useredits; then
  # правки экипировки пользователя из его сейва ROSTER (game/work/legacy-data/equipment-user/*правки.json, выгрузка —
  # user_equipment.py extract НОВЫЙ_СЕЙВ ПРЕДЫДУЩИЙ): ставятся, где в базе прежнее значение; повтор ничего не меняет
  say "правки экипировки пользователя (user_equipment.py)"
  for B in $O $W/out-ahl32; do
    for F in nhlng.db draft_roster.db; do [ -f $B/db/$F ] && python $T/user_equipment.py $B/db/$F; done
  done
fi
if want tape; then
  # обмотка крюка игрокам по решению пользователя (tools/legacy_data/tape_players.json: фамилия + дата рождения → код
  # sticktapecolor, варианты — tools/tapestyles.py, docs/player-models.md §13) и подписи вариантов в меню экипировки
  # (fe/loc). После useredits (решение главнее прежних правок пользователя) и collect (локализация — после него);
  # правит на месте, повтор ничего не меняет. Текстуры и сетки вариантов — этап models
  say "обмотка игроков и подписи вариантов (tape_players.py)"
  for B in $O $W/out-ahl32; do
    for F in nhlng.db draft_roster.db; do [ -f $B/db/$F ] && python $T/tape_players.py db $B/db/$F; done
    [ -f $B/fe/loc/NHL_ENG_US.db ] && python $T/tape_players.py loc $B/fe/loc/NHL_ENG_US.db
  done
fi
if want players; then
  # свои игроки по спекам JSON (tools/legacy_data/add_players.py, docs/add-players.md): новые — в строки игроков без клуба,
  # уже добавленные — правка только указанных полей; клуб, номер, звенья (запас / места игрока / по рейтингу), портрет.
  # Спеки — game/work/legacy-data/add-players/*.json (ADD_PLAYERS_DIR=папка); нет — этап пропущен. После tape, до
  # contracts (настоящий контракт со страниц клуба главнее) и photos24/heads (портрет и голова NHL 24, если игрок там
  # есть). Повтор ничего не меняет; draft_roster.db — заново
  AP=${ADD_PLAYERS_DIR:-$W/add-players}
  if ls $AP/*.json >/dev/null 2>&1; then
    say "свои игроки (add_players.py)"
    for B in $O $W/out-ahl32; do
      if [ -f $B/db/nhlng.db ]; then
        python $T/add_players.py db $B/db/nhlng.db $AP
        python $T/draft_roster.py $B/db/nhlng.db $B/db/draft_roster.db
      fi
    done
  else
    say "свои игроки: нет $AP/*.json — этап пропущен"
  fi
fi
if want contracts; then
  # настоящие контракты клубов НХЛ 2026/27 (docs/legacy-data.md, «Контракты 2026/27»): страницы клубов от пользователя,
  # разобранные в game/work/contracts/screens/*.json (личное использование, не в git; CONTRACTS_SCREENS=папка) → сумма,
  # срок, двусторонность, yearufa и подписанное продление (extension*) сшитым по дате рождения и имени игрокам; спорные
  # не берутся. После roster (--payroll-max ужимает только заглушки, настоящие суммы — после него) и tape, до
  # goaliegear (переводы игроков меняют вратарей клубов) и nhl24 (накладка из out/db). Повтор ничего не меняет; draft_roster.db — заново. Отчёты и ведомости — $W/contracts/.
  # Сейв ROSTER — отдельно: python tools/legacy_data/contracts.py save СЕЙВ [--write]
  S=${CONTRACTS_SCREENS:-game/work/contracts/screens}
  if ls $S/*.json >/dev/null 2>&1; then
    say "контракты клубов НХЛ 2026/27 (contracts.py)"
    mkdir -p $W/contracts
    for B in $O $W/out-ahl32; do
      if [ -f $B/db/nhlng.db ]; then
        python $T/contracts.py db $B/db/nhlng.db --report $W/contracts/$(basename $B).json
        python $T/draft_roster.py $B/db/nhlng.db $B/db/draft_roster.db
      fi
    done
  else
    say "контракты: нет $S/*.json — этап пропущен"
  fi
fi
if want awards; then
  # история наград и Кубка Стэнли из NHL 27 (tools/legacy_data/awards27.py, docs/awards.md): stockawardstable в out и
  # out-ahl32 — НХЛ 1994/95…2025/26, АХЛ и CHL с 2008/09, правки EA — awards_fix.json; index таблицы — 11 бит (и в
  # nhlng-meta.xml). После составов и своих игроков (клубы, game_id победителей — players/contracts), до nhl24 (накладка из
  # out/db). Сейвы не меняются: таблицы нет ни в ROSTER, ни в сейве франшизы. Повтор ничего не меняет
  if [ -f "${NHL27_DB:-game/work/nhl27/db/nhl_game.db}" ]; then
    say "история наград из NHL 27 (awards27.py)"
    python $T/awards27.py --write
  else
    say "награды: нет базы NHL 27 — этап пропущен"
  fi
fi
if want goaliegear; then
  # командная экипировка вратарей (tools/legacy_data/goalie_gear.json): каждому вратарю клуба — набор вратаря клуба из
  # stockgoalieequipment (щитки, блин, ловушка, клюшка, маска, цвета); у клуба без набора и у переименованных клубов с
  # наборами прежних (white_names) — белая экипировка с чёрной графикой и белая маска. После utah/ahl (имена и составы
  # клубов), tape и contracts (переводы игроков); draft_roster.db — по плану nhlng.db рядом. Повтор ничего не меняет. Отчёты — $W/goaliegear/
  say "экипировка вратарей по клубам (goalie_gear.py)"
  for B in $O $W/out-ahl32; do
    for F in nhlng.db draft_roster.db; do [ -f $B/db/$F ] && python $T/goalie_gear.py db $B/db/$F; done
  done
fi
if want photos24; then
  # портреты из NHL 24 тем, у кого портрета нет (docs/player-photos-nhl24.md): база NHL 24 из дампа (имя + дата
  # рождения, ID EA), портрет → кадр EA, оба размера → out/fe и out-ahl32/fe, hasportrait = 1, draft_roster.db — заново.
  # После ahl/useredits (берёт готовые базы out), до nhl24 (накладка собирается из out/db). Повтор ничего не меняет.
  # Нужны дамп NHL 24 (game/other/nhl24 + каталог game/work/nhl24/catalog) и питон с numpy и Pillow
  PY24=${PHOTOS24_PYTHON:-game/work/photos-nhl24/venv/Scripts/python.exe}; [ -x "$PY24" ] || PY24=python
  if [ -f game/work/nhl24/catalog/textures.csv ]; then
    say "портреты из NHL 24 (photos24)"
    "$PY24" tools/photos24.py match
    "$PY24" tools/photos24.py build --jobs 6
    "$PY24" tools/photos24.py apply
  else
    say "портреты из NHL 24: нет каталога дампа NHL 24 — этап пропущен"
  fi
  # затем из NHL 27 (PS5, docs/import-from-ea.md) — тем, у кого портрета всё ещё нет
  if [ -f game/work/nhl27/catalog/textures.csv ]; then
    say "портреты из NHL 27 (photos24 --source nhl27)"
    "$PY24" tools/photos24.py match --source nhl27
    "$PY24" tools/photos24.py build --source nhl27 --jobs 6
    "$PY24" tools/photos24.py apply --source nhl27
  fi
fi
if want heads; then
  # типовые головы по фото, осторожный вариант (решение пользователя 12.10; docs/player-photos-nhl24.md, «Головы»): голова EA
  # из NHL 24, если не противоречит фото, или подбор при явном несовпадении волос/растительности; разметка голов —
  # tools/legacy_data/heads_legacy.json. После photos24 (портреты), до nhl24 (накладка из out/db). Повтор ничего не меняет.
  # Нужны питон с numpy, scipy, Pillow, opencv-python-headless (PHOTOS24_PYTHON) и база NHL 24 из дампа
  PY24=${PHOTOS24_PYTHON:-game/work/photos-nhl24/venv/Scripts/python.exe}; [ -x "$PY24" ] || PY24=python
  if [ -f game/work/nhl24/catalog/textures.csv ]; then
    say "типовые головы по фото (heads24)"
    "$PY24" tools/heads24.py plan
    "$PY24" tools/heads24.py apply
  else
    say "головы: нет каталога дампа NHL 24 — этап пропущен"
  fi
fi
if want scans24; then
  # сканы голов NHL 24 игрокам с типовой головой (docs/heads-nhl24.md): сопоставление ID EA + имя/дата рождения (спорные —
  # в match-<вариант>.json, не берутся), сборка player/texlib_<ID EA> по шаблону — скану EA Legacy (сетка 1:1 по UV,
  # лицо 512 DXT1, пряди в haircap 256, суставы лица по смещению вершин) → out/rendering/player; headid и строки
  # stockplayerheads на места доноров (число строк то же) в out/db и out-ahl32/db, draft_roster.db заново. Сканы EA не
  # трогаются. После heads (типовые головы), до nhl24 (накладка из out/db). Повтор ничего не меняет (кэш голов —
  # $W/scans24/cache). Сейв ROSTER — отдельно: python tools/scans24.py save СЕЙВ [--write]
  PY24=${PHOTOS24_PYTHON:-game/work/photos-nhl24/venv/Scripts/python.exe}; [ -x "$PY24" ] || PY24=python
  if [ -f game/work/nhl24/catalog/textures.csv ]; then
    say "сканы голов NHL 24 (scans24)"
    "$PY24" tools/scans24.py match
    "$PY24" tools/scans24.py build --jobs 6
    "$PY24" tools/scans24.py apply
  else
    say "сканы голов NHL 24: нет каталога дампа NHL 24 — этап пропущен"
  fi
  # затем из NHL 27 — игрокам, у которых нет ни скана EA, ни головы из NHL 24 (их этап не заменяет)
  if [ -f game/work/nhl27/catalog/textures.csv ]; then
    say "сканы голов NHL 27 (scans24 --source nhl27)"
    "$PY24" tools/scans24.py match --source nhl27
    "$PY24" tools/scans24.py build --source nhl27 --jobs 6
    "$PY24" tools/scans24.py apply --source nhl27
  fi
fi
if want fonts; then
  say "шрифт меню NHL 12 (fefont --keep, скелет Legacy)"
  D=game/other/nhl12/big/cache/fe/ion/fonts; F=$W/fe/fonts/out-nhl12
  python tools/fefont.py build $F --game legacy --keep --add ℠ --face conbold=$D/eahelveticaneueconbol-mod.ttf \
         --face med=$D/eahelveticaneuemed-mod.ttf --face hv=$D/eahelveticaneuehv-mod.ttf
  mkdir -p $O/fe/ion/fonts && cp $F/fe/ion/fonts/*.ttf $O/fe/ion/fonts/
fi
if want music; then
  say "музыка Best of NHL (16 песен)"
  python tools/music.py --game legacy unpack
  python tools/music.py --game legacy build best_of_nhl
fi
if want models; then
  say "3D: гетры, обмотка, край свитера"
  bash $T/models/build.sh
fi
if want art; then
  say "арт SEA/VGK (100/101) и CV/HSK (102/103)"
  AS=$T/art; AP=$W/art/preview                 # спеки и скрипты — в git, превью — в game/work
  for t in SEA VGK CVF HSK; do python tools/teamart.py build $AS/src/$t.json $O --preview $AP/logos --game legacy; done
  python tools/czkit.py build $AS/src/SEA-cz.json $O --preview $AP/kits-cz --game legacy
  python tools/czkit.py build $AS/src/VGK-cz.json $O --preview $AP/kits-cz --game legacy
  # превью формы на Select Jerseys — в позе EA по модели $W/fepose/pose.bin (её нет — прежняя отрисовка; модель —
  # tools/fepose.py fit --game legacy питоном с numpy, docs/uniforms.md §13)
  for t in SEA VGK; do python tools/czkit.py fe $AS/src/$t-cz.json $O --game legacy; done
  python tools/teamart.py alias 153 102 $O --game legacy      # CV  ← форма Springfield Falcons
  python tools/teamart.py alias 150 103 $O --game legacy      # HSK ← форма Providence Bruins
  python $AS/scripts/verify_out.py $O --game legacy
fi
if want logos; then
  # логотипы клубов 2026/27 агента logos (docs/logos-2026.md): готовые файлы по манифесту, со сверкой md5
  # (tools/logos/outcopy.py: в out — только пути манифеста, ничего не пересобирается). Только в out: у накладок
  # out-ahl32 и out-nhl24 своего арта клубов нет. После art: у HSK (арт 103) art пишет прежний щит, logos заменяет его
  # нынешним (так задумано); CV 102 и TUC 105 не трогаются. Этап art без logos вернёт прежний щит HSK
  for LO in game/work/logos/out-nhl game/work/logos/out-ahl; do
    if [ -f "$LO/manifest.json" ]; then say "логотипы 2026/27: $LO"; python tools/logos/outcopy.py copy "$LO" $O
    else say "логотипы: нет $LO/manifest.json — пропуск"; fi
  done
fi
if want menu; then
  # после collect: menuitems_legacy.py правит локализацию out (и накладки — у неё своя) — пункт EXIT, панель описаний
  say "главное меню NHL 12 (menu12_legacy) и пункты меню (menuitems_legacy)"
  # места колец фона → клуб: spec.json menu12, если есть; иначе — восстановленный tools/legacy_data/menu/menu12-rings.json
  SPEC12=game/work/menu12/players/spec.json; [ -f $SPEC12 ] || SPEC12=$T/menu/menu12-rings.json
  python tools/menu12_legacy.py build --spec $SPEC12
  python tools/menuitems_legacy.py build
  # доски драфта на 32 (Be a GM, фэнтези-драфт и его порядок, Live the Life): три колонки 15 + 15 + 2
  # (docs/fe-menu-legacy.md §11); файлы — game/work/legacy-data/draft32/files.txt
  say "доски драфта на 32 (draft32_legacy)"
  python tools/draft32_legacy.py build
  # год 2015 → 2026 в копирайтах и юридическом тексте (стартовый экран, legal, титры, подсказка FA) — локализация out и
  # out-ahl32, после menuitems_legacy (docs/fe-menu-legacy.md §12); файлы — game/work/legacy-data/year2026/files.txt
  say "год 2015 → 2026 в надписях (year2026_legacy)"
  python tools/year2026_legacy.py build
fi
if want nhl24; then
  # после collect (берёт out/db и out-ahl32/db): пакет агента nhl24 — формы, шрифты номеров, центры и реклама льда,
  # наклейки на шлемах, шорты и гетры, клюшки, шайба — сверка по manifest.json → накладка out-nhl24 (+ out-nhl24-ahl32):
  # файлы пакета и база с hastie 0 у клубов пакета и новыми строками формы (номера — tools/legacy_data/nhl24_kits.json).
  # Ставится install-legacy-data.sh [--ahl32] --nhl24, снимается uninstall-legacy-data.sh --nhl24.
  P=${NHL24_PACK:-game/work/nhl24/out/pack}
  if [ -f "$P/manifest.json" ]; then
    say "пакет NHL 24 → накладка out-nhl24"
    python $T/nhl24.py build "$P"
  else
    say "пакет NHL 24: нет $P/manifest.json — этап пропущен"
  fi
fi
say "готово → $O"
