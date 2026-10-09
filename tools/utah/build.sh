#!/bin/bash
# Utah Mammoth (строка 22 базы Legacy, бывшая Arizona Coyotes) и фарм-клуб Tucson Roadrunners (строка 55, бывший
# Springfield Falcons): весь арт → game/work/utah/out (дерево как в cache:), концепт третьей формы → out-third, листы на
# проверку → compare, спецификация для legacy-data → utah_spec.json. Описание — docs/utah.md. Ничего не ставит.
#   bash tools/utah/build.sh [этап…]       этапы: logos ui kits tucson verify sheets spec (без этапов — все)
#   UTAH_WORK=папка bash tools/utah/build.sh …   # сухой прогон в другую папку (исходники SVG/PNG — всё равно из
#                                                # game/work/utah/src, кеш развёртки — game/work/utah/cache)
# Нужны: Chrome или Edge (рисунок SVG), python со стандартной библиотекой и venv game/work/utah/venv (numpy, scipy,
# Pillow) — для kitdesign, ui_extra, sheets. Логотипы и формы NHL — только для личного использования, в git не идут.
set -e
R="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$R"
U=tools/utah
S=$U/src
W=${UTAH_WORK:-game/work/utah}
O=$W/out
O3=$W/out-third
PY=python
VPY=game/work/utah/venv/Scripts/python.exe
[ -x "$VPY" ] || VPY=game/work/utah/venv/bin/python
export PYTHONIOENCODING=utf-8
stages=("$@")
[ ${#stages[@]} -gt 0 ] || stages=(logos ui kits tucson verify sheets spec)
want() { for s in "${stages[@]}"; do [ "$s" = "$1" ] && return 0; done; return 1; }
say() { echo "== $(date +%H:%M:%S) $*"; }
mkdir -p "$O" "$O3" "$W/preview" "$W/compare" "$W/work"

if want logos; then
  say "логотипы Юты (арт 104, прожектор 48), центр льда с «DELTA CENTER»"
  $PY tools/teamart.py build $S/UTA.json $O --only t,s,d,c,w,r,puck,banner,spot --preview $W/preview/logos --game legacy
  $PY $U/center_ice.py $S/UTA.json $O --preview $W/preview/logos --game legacy
fi
if want ui; then
  say "интерфейс: фон карточки, значок ленты, цифры меню, картинка левой панели"
  $VPY $U/ui_extra.py $S/UTA.json $O --nums 104 --preview $W/preview/ui --game legacy
fi
if want kits; then
  say "форма Юты: дом и выезд (out), концепт третьей (out-third), наклейка на шлем"
  $VPY $U/kitdesign.py build $S/UTA-kits.json $O --work $W/work/kits --game legacy
  $VPY $U/kitdesign.py build $S/UTA-third.json $O3 --work $W/work/kits --game legacy
  $PY $U/helmet.py $S/UTA.json $O --variants 0,1 --preview $W/preview/helmet --game legacy
  $PY $U/helmet.py $S/UTA.json $O3 --variants 2 --game legacy
fi
if want tucson; then
  say "фарм-клуб Tucson Roadrunners (арт 105): логотипы, центр льда, форма, наклейка"
  $PY tools/teamart.py build $S/TUC.json $O --only t,s,d,c,w,puck,banner --preview $W/preview/logos-tuc --game legacy
  $PY $U/center_ice.py $S/TUC.json $O --preview $W/preview/logos-tuc --game legacy
  $VPY $U/kitdesign.py build $S/TUC-kits.json $O --work $W/work/kits --game legacy
  $PY $U/helmet.py $S/TUC.json $O --variants 0,1 --preview $W/preview/helmet --game legacy
fi
if want verify; then
  say "проверки: контейнеры комплектов, логотипы против шаблонов EA, разбор/сборка всех файлов"
  $PY tools/kitpaint.py verify $O 1_104_0=1_131_0 1_104_1=1_131_0 1_105_0=1_131_0 1_105_1=1_131_0 --game legacy
  $PY tools/kitpaint.py verify $O3 1_104_2=1_131_0 --game legacy
  $PY tools/legacy_data/art/scripts/verify_out.py $O --game legacy
  $PY tools/teamart.py roundtrip $O $O3 --game legacy
fi
if want sheets; then
  say "листы compare"
  C=$W/compare
  $VPY $U/sheets.py logos $O $C/logos.png --old 22 --new 104 --title "Логотипы: Arizona Coyotes (EA, Legacy) → Utah Mammoth" \
       --labels "Аризона сейчас (арт 22)|Юта (арт 104)" --game legacy
  $VPY $U/sheets.py center $O $C/center_ice.png --old 22 --new 104 --game legacy
  $VPY $U/sheets.py kits $O $C/kits_front_back.png "1_104_0=Юта, дом (Rock Black)" "1_104_1=Юта, выезд (Salt White)" \
       --sample 9,KELLER,C --old "1_22_3=Аризона сейчас, дом (EA 2015/16)" "1_22_4=Аризона сейчас, выезд (EA 2015/16)" --game legacy
  $VPY $U/sheets.py kits $O3 $C/third_concept.png "1_104_2=Юта, третья — КОНЦЕПТ по утечке Hometown Remix (не официальная)" \
       --sample 9,KELLER,C --game legacy
  $VPY $U/sheets.py fe $O $C/menu_preview.png "1_104_0=Юта, дом" "1_104_1=Юта, выезд" "$O3@1_104_2=Юта, третья (концепт)" \
       "1_105_0=Тусон, дом" "1_105_1=Тусон, выезд" --old "1_22_3=Аризона сейчас, дом" "1_22_4=Аризона сейчас, выезд" --game legacy
  $VPY $U/sheets.py ui $O $C/ui_helmet_font.png --game legacy
  $VPY $U/sheets.py logos $O $C/tucson_logos.png --old 153 --new 105 --ahl \
       --title "АХЛ, фарм-клуб: Springfield Falcons (сейчас в базе, EA) → Tucson Roadrunners (логотип АХЛ 2026/27)" \
       --labels "Springfield сейчас (арт 153)|Тусон (арт 105)" --game legacy
  $VPY $U/sheets.py kits $O $C/tucson_kits.png "1_105_0=Тусон, дом (бордовая)" "1_105_1=Тусон, выезд (белая)" \
       --sample 21,ROADRUNNER,A --old "1_153_1=Springfield сейчас, дом (EA)" "1_153_0=Springfield сейчас, выезд (EA)" --game legacy
fi
if want spec; then
  say "спецификация для legacy-data (по копии CACHE пользователя: game/work/utah/ref)"
  $PY $U/make_spec.py game/work/utah/ref/cache-db game/work/utah/ref/loc/NHL_ENG_US.cache.db $O $W/utah_spec.json
fi
say "готово: $O"
