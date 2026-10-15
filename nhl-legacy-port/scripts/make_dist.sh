#!/bin/bash
# Папка для друзей: nhl-legacy-port/dist/NHL Legacy Remaster vX.Y.Z (версия — файл VERSION) — порт без файлов игры
# (docs/legacy-port.md); exe с иконкой (tools/make_icon.py + tools/set_exe_icon.py) и лаунчер.
#   [BUILD=папка] [AHL32=1] bash nhl-legacy-port/scripts/make_dist.sh [--mods]   # AHL32=1 — моды с базой «АХЛ на 32»
# Берёт Release-сборку (out/build/win-amd64-release: свой SDK, D3D12 + Vulkan), DLL рантайма MSVC
# (app-local, из VC Redist BuildTools), шаблоны dist-template/ (nhllegacy.toml — пути пустые:
# game\ и userdata\ рядом с exe; README.txt). С --mods — ещё моды-данные из
# nhl-legacy-port/userdata/cache/guest (только файлы игры-модов: без кэша, который пишет сама игра).
set -euo pipefail
P=$(cd "$(dirname "$0")/.." && pwd)
B="${BUILD:-$P/out/build/win-amd64-release}"   # BUILD=папка сборки (по умолчанию — рабочая)
V=$(tr -d '
 ' < "$P/../VERSION" 2>/dev/null || echo dev)
D="$P/dist/NHL Legacy Remaster v$V"
CRT="/c/Program Files (x86)/Microsoft Visual Studio/2022/BuildTools/VC/Redist/MSVC/14.44.35112/x64/Microsoft.VC143.CRT"
[ -f "$B/nhllegacy.exe" ] || { echo "нет сборки $B/nhllegacy.exe — build.cmd"; exit 1; }
# та же версия уже собиралась — прежнюю папку отодвигаем рядом (не удаляем)
[ -e "$D" ] && mv "$D" "$D.prev-$(date +%Y%m%d-%H%M)"
mkdir -p "$D/game" "$D/userdata/cache/guest"
cp "$B/nhllegacy.exe" "$B/nhllegacy_snap.exe" "$B/rexruntime.dll" "$B/rexgpu-xenos.dll" "$D/"
L="$P/out/launcher/nhllegacy_launcher.exe"; [ -f "$L" ] || L="$B/nhllegacy_launcher.exe"  # свежая сборка лаунчера
[ -f "$L" ] && cp "$L" "$D/" || echo "нет лаунчера — nhl-legacy-port/launcher/build.cmd"
ICO="$P/launcher/icon/nhllegacy.ico"
if [ -f "$ICO" ]; then python "$P/../tools/set_exe_icon.py" "$D/nhllegacy.exe" "$ICO" --no-backup; else
  echo "нет иконки — python tools/make_icon.py"; fi
for dll in msvcp140.dll msvcp140_atomic_wait.dll vcruntime140.dll vcruntime140_1.dll; do
  cp "$CRT/$dll" "$D/"
done
cp "$P/dist-template/nhllegacy.toml" "$P/dist-template/README.txt" "$D/"
echo "Сюда — файлы игры NHL Legacy: default.xex и *.big (см. README.txt)." > "$D/game/ПОЛОЖИТЬ СЮДА ИГРУ.txt"
if [ "${1:-}" = "--mods" ]; then
  # Кэш самой игры (cache:\ раздела 360) не переносим: версия кэша, реклама, повторы.
  (cd "$P/userdata/cache/guest" && find . -type f \
      ! -name '*.ver' ! -path './admanager_cache_images*' ! -name 'highlights.sav' -print0 |
      xargs -0 -r cp --parents -t "$D/userdata/cache/guest")
  # база на 32 команды в модах → франшиза на 32 по умолчанию
  if [ -f "$D/userdata/cache/guest/db/nhlng.db" ]; then
    sed -i 's/^nhl_teams = 30$/nhl_teams = 32/' "$D/nhllegacy.toml"
    # старт «NHL Entry Draft» берёт составы из db/draft_roster.db (на диске — драфт 2015): та же база под этим именем
    # (docs/legacy-data.md, «draft_roster.db»); если в cache: её нет — кладём копию сами
    [ -f "$D/userdata/cache/guest/db/draft_roster.db" ] ||
      cp "$D/userdata/cache/guest/db/nhlng.db" "$D/userdata/cache/guest/db/draft_roster.db"
  fi
  # база «АХЛ на 32» (legacy-data --ahl32: в лиге АХЛ 32 клуба — Coachella Valley и Henderson) → АХЛ на 32
  if [ "${AHL32:-}" = "1" ]; then
    sed -i 's/^nhl_ahl_teams = 30$/nhl_ahl_teams = 32/' "$D/nhllegacy.toml"
  fi
  # Сейвы пользователя по умолчанию (SAVES=0 — без них): последний PROFILE (настройки игры, правила, слайдеры
  # геймплея, звук, видео, управление) и последний ROSTER (составы с правками). Профиль порта один на всех ПК
  # (XUID B13EBABEBABEBABE, имя «User» — SDK, xam/user_profile.cpp), так что игра друга подхватит их как свои.
  # Карьеры (DYNASTY, BEAPRO…) не переносим.
  if [ "${SAVES:-1}" = "1" ]; then
    U="B13EBABEBABEBABE/454109EC"
    S="$P/userdata/$U"
    for kind in PROFILE ROSTER; do
      last=$(cd "$S/00000001" && ls -d "$kind "* 2>/dev/null | sort | tail -1)
      [ -n "$last" ] || { echo "нет сейва $kind в $S"; continue; }
      mkdir -p "$D/userdata/$U/00000001" "$D/userdata/$U/Headers/00000001"
      cp -r "$S/00000001/$last" "$D/userdata/$U/00000001/"
      cp "$S/Headers/00000001/$last.header" "$D/userdata/$U/Headers/00000001/"
      echo "сейв: $last"
    done
  fi
fi
du -sh "$D"
ls "$D"
