#!/bin/bash
# Пересборка всего набора модов-данных NHL Legacy с нуля → game/work/legacy-data/out (дерево как в cache:).
# Описание — docs/legacy-data.md. Ставится потом tools/legacy_data/install-legacy-data.sh (при закрытой игре).
#   bash tools/legacy_data/build-all.sh [ЭТАП…] [--ahl32]
#   LEGACY_DATA_WORK=папка bash tools/legacy_data/build-all.sh …   # сухой прогон: всё (и out) — в эту папку;
#        входы, которые этапом не пересобираются (например, составы без сети), — положить туда заранее
#        этапы: base roster photos equip collect fixdb fonts music models art menu nhl24 (без этапов — все по порядку;
#        --ahl32 — ещё вариант «АХЛ на 32», накладка game/work/legacy-data/out-ahl32; nhl24 — накладка out-nhl24
#        из пакета NHL 24, если он готов: game/work/nhl24/out/pack или NHL24_PACK=папка)
# Сеть: roster — только кэш (--offline); photos — докачка недостающих портретов лиг (пауза ≥ 1 с), остальное — без сети.
# Время (под нагрузкой ПК): base ~1 мин, roster ~6 мин, photos ~15 мин, models ~5 мин, art ~5 мин, music ~2 мин.
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
[ ${#stages[@]} -gt 0 ] || stages=(base roster photos equip collect fixdb fonts music models art menu nhl24)
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
FLAGS="--offline --game legacy --stats-ratings --fa --fa-only --skin --league liiga --payroll-max 100"
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
  # старт франшизы «NHL Entry Draft» читает составы не из nhlng.db, а из db/draft_roster.db (cacheboot.big: только
  # таблицы exhibition*, составы драфта 2015) — та же база под этим именем (docs/legacy-data.md, «draft_roster.db»)
  cp $O/db/nhlng.db $O/db/draft_roster.db
  cp $W/roster/nhlng-meta.xml $O/db/nhlng-meta.xml
  cp $W/nhl32/nhl_eng_us.db $O/fe/loc/NHL_ENG_US.db
  cp -r $W/photos-all/fe $O/
  # накладка «АХЛ на 32»: база, схема, локализация и портреты CV/HSK (install-legacy-data.sh --ahl32)
  [ $AHL32 = 1 ] && python $T/make_out_ahl32.py
  [ $AHL32 = 1 ] && [ -f $W/out-ahl32/db/nhlng.db ] && cp $W/out-ahl32/db/nhlng.db $W/out-ahl32/db/draft_roster.db
  echo "   локализация из nhl32 — без правок меню: потом этап menu (menuitems_legacy.py)"
fi
if want fixdb; then
  # последний бит записи — флаг движка «запись свободна»: поле на нём (leaguerookiedata.draftteam 58…63 при reclen 8 —
  # до исправления tdb.widen 10.10.2026) прячет строки от игры; у таких таблиц запись +4 байта, поля на местах.
  # Повторный запуск ничего не меняет; draft_roster.db — снова копия починенной nhlng.db
  say "база: последний бит записи свободен (fix_flagbit)"
  for d in $O/db $W/out-ahl32/db; do
    if [ -f $d/nhlng.db ]; then
      python $T/fix_flagbit.py $d/nhlng.db
      cp $d/nhlng.db $d/draft_roster.db
    fi
  done
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
if want menu; then
  # после collect: menuitems_legacy.py правит локализацию out (и накладки — у неё своя) — пункт EXIT, панель описаний
  say "главное меню NHL 12 (menu12_legacy) и пункты меню (menuitems_legacy)"
  # места колец фона → клуб: spec.json menu12, если есть; иначе — восстановленный tools/legacy_data/menu/menu12-rings.json
  SPEC12=game/work/menu12/players/spec.json; [ -f $SPEC12 ] || SPEC12=$T/menu/menu12-rings.json
  python tools/menu12_legacy.py build --spec $SPEC12
  python tools/menuitems_legacy.py build
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
