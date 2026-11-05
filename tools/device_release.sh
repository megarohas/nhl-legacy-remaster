#!/bin/bash
# Релиз для другого устройства: полная свежая папка, которую остаётся только скинуть (docs/device-release.md).
#   bash tools/device_release.sh            # nhl-legacy-port/dist/device/NHL Legacy Remaster vX.Y.Z
#   bash tools/device_release.sh --check    # и запустить копию папки до главного меню (снимок и журнал рядом с папкой)
#   bash tools/device_release.sh --check-only   # только запуск готовой папки
#   bash tools/device_release.sh --no-saves     # без PROFILE и ROSTER: игра на устройстве с нуля (03.11.2026, по просьбе
#                                               # пользователя — проверить чистый старт и импорт ростера вручную)
# Берёт то, что установлено у пользователя: exe, лаунчер, моды, список шейдеров, последние PROFILE и ROSTER
# (scripts/make_dist.sh --mods), и добавляет файлы игры в game\. Игра должна быть закрыта.
# С 0.17.0 папка saves\ в релизе пустая, а PROFILE и ROSTER лежат в start-saves\: игра копирует их в saves\, только
# если там нет сейва этого вида. Обновление на устройстве = скопировать новую папку поверх, сейвы не трогаются.
set -euo pipefail

CHECK=0
SAVES=1
for arg in "$@"; do
  case "$arg" in
    --check) CHECK=1 ;;
    --check-only) CHECK=2 ;;
    --no-saves) SAVES=0 ;;
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

check() {
  [ -d "$D" ] || { echo "нет папки $D"; exit 1; }
  [ ! -e "$LOCK" ] || { echo "замок занят: $(cat "$LOCK"); проверка пропущена"; exit 1; }
  echo "device-release $(date +%H:%M)" > "$LOCK"
  C="$R/game/work/device-check"
  mkdir -p "$C"
  cp -r "$D" "$C/NHL"
  echo 'nhl_virtual_pad = true' >> "$C/NHL/nhllegacy.toml"
  local exe started pid stale waited
  exe=$(cygpath -w "$C/NHL/nhllegacy.exe")
  started=$(powershell -NoProfile -ExecutionPolicy Bypass -File "$R/tools/gameshot.ps1" -Game legacy -Do start -Exe "$exe" -Log "$(cygpath -w "$C/gs.log")")
  pid=$(echo "$started" | sed -n 's/^STARTED pid \([0-9]*\).*/\1/p')
  [ -n "$pid" ] || { echo "не запустилась: $started"; rm -f "$LOCK"; exit 1; }
  # Новый путь к exe — пустой кэш драйвера: сборка из списка шейдеров идёт десятки секунд, окно чёрное, нажатия теряются.
  for waited in $(seq 1 120); do
    grep -a -q "graphics pipelines" "$C/gs.log" 2>/dev/null && break
    sleep 5
  done
  grep -a "graphics pipelines" "$C/gs.log" | sed 's/.*Created/Created/' | cut -c1-120
  # Экраны идут с разной скоростью (язык, заставка, автосохранение), поэтому жмём, пока журнал не покажет главное меню:
  # при входе в него игра запрашивает nhlstorecfg.xml. Окно «ROSTER damaged» до него не пустит.
  local dir shots reached=0
  dir=$(cygpath -w "$C/NHL")
  shots=$(cygpath -w "$C")
  for waited in $(seq 1 30); do
    powershell -NoProfile -ExecutionPolicy Bypass -File "$R/tools/padshot.ps1" -Dir "$dir" -Shots "$shots" \
      -Steps 'pad:A;wait:5;pad:START;wait:5' > /dev/null
    grep -a -q "nhlstorecfg.xml" "$C/gs.log" && { reached=1; break; }
  done
  powershell -NoProfile -ExecutionPolicy Bypass -File "$R/tools/padshot.ps1" -Dir "$dir" -Shots "$shots" \
    -Steps 'wait:12;shot:menu.png' | tail -1
  taskkill //PID "$pid" //F > /dev/null
  rm -f "$LOCK"
  cp "$C/menu.png" "$OUT/check-v$V.png"
  cp "$C/gs.log" "$OUT/check-v$V.log"
  stale=$(grep -a -c -E "nhl-legacy-port|game/other|legacy/disc" "$C/gs.log" || true)
  cmd //c rmdir //s //q "$(cygpath -w "$C")"
  echo "проверка: снимок $OUT/check-v$V.png, ссылок на старые пути в журнале: $stale"
  [ "$reached" = 1 ] || { echo "до главного меню не дошла, см. снимок и журнал"; exit 1; }
  [ "$stale" = 0 ] || exit 1
}

if [ "$CHECK" = 2 ]; then
  check
  exit 0
fi

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

SAVES=$SAVES bash "$P/scripts/make_dist.sh" --mods
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
# Личное устройства не перезаписывается: в saves\ релиза ничего нет (стартовые сейвы — в start-saves\).
[ -d "$D/saves" ] && [ -z "$(ls -A "$D/saves")" ] || { echo "в $D/saves что-то есть — релиз не должен класть сейвы туда"; exit 1; }
for f in "$DISC"/*; do
  [ "$(stat -c %s "$f")" = "$(stat -c %s "$D/game/$(basename "$f")")" ] || { echo "не совпал $(basename "$f")"; exit 1; }
done

{
  echo "$NAME"
  echo "собрано $(date '+%d.%m.%Y %H:%M')"
  echo "коммит $(git -C "$R" rev-parse --short HEAD)"
  echo "exe $(md5sum "$D/nhllegacy.exe" | cut -c1-8)"
  echo "лаунчер $(md5sum "$D/nhllegacy_launcher.exe" | cut -c1-8)"
  [ -f "$D/editor/NHL Legacy Editor.exe" ] && echo "редактор $(cat "$D/editor/version.txt" 2>/dev/null | tr -d '\r\n'), сервер $(md5sum "$D/editor/backend/nhllegacy_editor_server.exe" | cut -c1-8)"
  [ "$SAVES" = 1 ] && echo "сейвы: стартовые PROFILE и ROSTER в start-saves (в saves, только если там пусто)" ||
    echo "сейвы: нет (старт с нуля)"
} > "$D/release.txt"

# Основа будущих обновлений частями: у следующей версии будет с чем сравнить.
(cd "$D" && find . -type f ! -name files.sha256 -print0 | sort -z | xargs -0 sha256sum > files.sha256)

if [ ${#old[@]} -gt 0 ]; then
  paths=()
  for f in "${old[@]}"; do paths+=("$(cygpath -w "${f%/}")"); done
  python "$R/tools/recycle.py" drop "${paths[@]}"
fi

[ "$CHECK" = 1 ] && check

du -sh "$D"
echo "готово: $D"
