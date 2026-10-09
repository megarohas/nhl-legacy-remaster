#!/bin/bash
# Папка для друзей: legacy-port/dist/NHL Legacy — порт без файлов игры (docs/legacy-port.md).
#   [BUILD=папка] [AHL32=1] bash legacy-port/scripts/make_dist.sh [--mods]   # AHL32=1 — моды с базой «АХЛ на 32»
# Берёт Release-сборку (out/build/win-amd64-release: свой SDK, D3D12 + Vulkan), DLL рантайма MSVC
# (app-local, из VC Redist BuildTools), шаблоны dist-template/ (nhllegacy.toml — пути пустые:
# game\ и userdata\ рядом с exe; README.txt). С --mods — ещё моды-данные из
# legacy-port/userdata/cache/guest (только файлы игры-модов: без кэша, который пишет сама игра).
set -euo pipefail
P=$(cd "$(dirname "$0")/.." && pwd)
B="${BUILD:-$P/out/build/win-amd64-release}"   # BUILD=папка сборки (по умолчанию — рабочая)
D="$P/dist/NHL Legacy"
CRT="/c/Program Files (x86)/Microsoft Visual Studio/2022/BuildTools/VC/Redist/MSVC/14.44.35112/x64/Microsoft.VC143.CRT"
[ -f "$B/nhllegacy.exe" ] || { echo "нет сборки $B/nhllegacy.exe — build.cmd"; exit 1; }
rm -rf "$D"
mkdir -p "$D/game" "$D/userdata/cache/guest"
cp "$B/nhllegacy.exe" "$B/nhllegacy_snap.exe" "$B/rexruntime.dll" "$B/rexgpu-xenos.dll" "$D/"
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
fi
du -sh "$D"
ls "$D"
