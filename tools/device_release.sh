#!/bin/bash
# Релиз для другого устройства: полная свежая папка, которую остаётся только скинуть (docs/device-release.md).
#   bash tools/device_release.sh            # nhl-legacy-port/dist/device/NHL Legacy Remaster vX.Y.Z
#   bash tools/device_release.sh --check    # и запустить копию папки до главного меню (снимок рядом с папкой)
# Берёт то, что установлено у пользователя: exe, лаунчер, моды, список шейдеров, последние PROFILE и ROSTER
# (scripts/make_dist.sh --mods), и добавляет файлы игры в game\. Игра должна быть закрыта.
set -euo pipefail

CHECK=0
for arg in "$@"; do
  case "$arg" in
    --check) CHECK=1 ;;
    *) echo "что? $arg (см. начало файла)"; exit 2 ;;
  esac
done

R=$(cd "$(dirname "$0")/.." && pwd)
P="$R/nhl-legacy-port"
B="$P/out/build/win-amd64-release"
TREE_EXE="$R/nhl-legacy-port-unlock/out/build/win-amd64-release/nhllegacy.exe"
DISC="$R/game/other/legacy/disc"
OUT="$P/dist/device"
LOCK="$R/game/work/status/game.lock"
V=$(tr -d '\r\n ' < "$R/VERSION")
NAME="NHL Legacy Remaster v$V"
D="$OUT/$NAME"

tasklist | grep -qi nhllegacy && { echo "игра запущена: релиз берёт сейвы, сначала закрыть её"; exit 1; }
[ -f "$DISC/default.xex" ] || { echo "нет файлов игры в $DISC"; exit 1; }
if [ -f "$TREE_EXE" ] && [ "$TREE_EXE" -nt "$B/nhllegacy.exe" ]; then
  echo "в дереве сборки exe новее установленного: сначала поставить его (docs/legacy-port.md, «Сборка»)"
  exit 1
fi

mkdir -p "$OUT"
# Папка той же версии — в сторону: в ней могут лежать файлы игры, и их не надо копировать заново.
[ -e "$D" ] && mv "$D" "$OUT/old-$V-$(date +%Y%m%d-%H%M)"
shopt -s nullglob
old=("$OUT"/*/)
shopt -u nullglob

bash "$P/scripts/make_dist.sh" --mods
mv "$P/dist/$NAME" "$D"
rm -f "$D/game/"*.txt
rmdir "$D/game"

# Файлы игры одни и те же: забираем из прежней папки, а если её нет — копируем с диска.
game_from=""
for f in "${old[@]}"; do
  [ -f "${f}game/default.xex" ] && game_from="${f%/}" && break
done
if [ -n "$game_from" ]; then
  mv "$game_from/game" "$D/game"
else
  cp -r "$DISC" "$D/game"
fi
for f in "$DISC"/*; do
  [ "$(stat -c %s "$f")" = "$(stat -c %s "$D/game/$(basename "$f")")" ] || { echo "не совпал $(basename "$f")"; exit 1; }
done

{
  echo "$NAME"
  echo "собрано $(date '+%d.%m.%Y %H:%M')"
  echo "коммит $(git -C "$R" rev-parse --short HEAD)"
  echo "exe $(md5sum "$D/nhllegacy.exe" | cut -c1-8)"
  echo "лаунчер $(md5sum "$D/nhllegacy_launcher.exe" | cut -c1-8)"
} > "$D/release.txt"

# Основа будущих обновлений частями: у следующей версии будет с чем сравнить.
(cd "$D" && find . -type f ! -name files.sha256 -print0 | sort -z | xargs -0 sha256sum > files.sha256)

if [ ${#old[@]} -gt 0 ]; then
  paths=()
  for f in "${old[@]}"; do paths+=("$(cygpath -w "${f%/}")"); done
  python "$R/tools/recycle.py" drop "${paths[@]}"
fi

if [ "$CHECK" = 1 ]; then
  [ ! -e "$LOCK" ] || { echo "замок занят: $(cat "$LOCK"); проверка пропущена"; exit 1; }
  echo "device-release $(date +%H:%M)" > "$LOCK"
  C="$R/game/work/device-check"
  mkdir -p "$C"
  cp -r "$D" "$C/NHL"
  echo 'nhl_virtual_pad = true' >> "$C/NHL/nhllegacy.toml"
  exe=$(cygpath -w "$C/NHL/nhllegacy.exe")
  started=$(powershell -NoProfile -ExecutionPolicy Bypass -File "$R/tools/gameshot.ps1" -Game legacy -Do start \
    -Exe "$exe" -Log "$(cygpath -w "$C/gs.log")")
  pid=$(echo "$started" | sed -n 's/^STARTED pid \([0-9]*\).*/\1/p')
  [ -n "$pid" ] || { echo "не запустилась: $started"; rm -f "$LOCK"; exit 1; }
  powershell -NoProfile -ExecutionPolicy Bypass -File "$R/tools/padshot.ps1" -Dir "$(cygpath -w "$C/NHL")" \
    -Shots "$(cygpath -w "$C")" -Steps 'wait:27;pad:A;wait:30;pad:START;wait:11;pad:A;wait:18;shot:menu.png' | tail -1
  taskkill //PID "$pid" //F > /dev/null
  rm -f "$LOCK"
  cp "$C/menu.png" "$OUT/check-v$V.png"
  stale=$(grep -a -c -E "nhl-legacy-port|game/other|legacy/disc" "$C/gs.log" || true)
  cmd //c rmdir //s //q "$(cygpath -w "$C")"
  echo "проверка: снимок $OUT/check-v$V.png, ссылок на старые пути в журнале: $stale"
  [ "$stale" = 0 ] || exit 1
fi

du -sh "$D"
echo "готово: $D"
