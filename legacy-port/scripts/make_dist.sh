#!/bin/bash
# Папка для друзей: legacy-port/dist/NHL Legacy — порт без файлов игры (docs/legacy-port.md).
#   bash legacy-port/scripts/make_dist.sh [--mods]
# Берёт Release-сборку (out/build/win-amd64-release: свой SDK, D3D12 + Vulkan), DLL рантайма MSVC
# (app-local, из VC Redist BuildTools), шаблоны dist-template/ (nhllegacy.toml — пути пустые:
# game\ и userdata\ рядом с exe; README.txt). С --mods — ещё моды-данные из
# legacy-port/userdata/cache/guest (только файлы игры-модов: без кэша, который пишет сама игра).
set -euo pipefail
P=$(cd "$(dirname "$0")/.." && pwd)
B="$P/out/build/win-amd64-release"
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
fi
du -sh "$D"
ls "$D"
