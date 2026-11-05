#!/usr/bin/env bash
# Сборка редактора-приложения (docs/editor.md, «Сборка»): папка editor\ для папки игры.
#
#   bash tools/editor/build.sh            # → nhl-legacy-port/out/editor/editor/  (NHL Legacy Editor.exe, backend\, …)
#
# 1. Сервер — Python, код tools/ и Pillow, PyInstaller (папкой: запуск быстрее, чем у одного exe), консольный — Electron
#    запускает его скрыто и говорит с ним через stdin/stdout. Окружение — game/work/editor/venv (создаётся само:
#    Python 3.14 с python.org, pip install pyinstaller pillow).
# 2. Окно — официальный Electron для Windows x64 (zip с github.com/electron/electron/releases, SHA-256 сверен с
#    SHASUMS256.txt; нет папки — скачивается сам) в game/work/editor/electron/electron-v<версия> (ELECTRON_DIR —
#    другая папка), не в git. electron.exe →
#    «NHL Legacy Editor.exe», иконка и сведения файла — официальный rcedit (github.com/electron/rcedit,
#    game/work/editor/electron/dl/rcedit-x64.exe). Код окна — tools/editor/electron → resources\app. Лицензии Electron
#    и Chromium (LICENSE, LICENSES.chromium.html) лежат в папке приложения. Языки Chromium — только en-US и ru.
# В папке нет файлов EA: код, интерфейс и значок лаунчера (tools/make_icon.py, не в git). Версия — файл VERSION.
set -euo pipefail
W() { cygpath -w "$1" 2>/dev/null || echo "$1"; }
R="$(cd "$(dirname "$0")/../.." && pwd)"
V="$R/game/work/editor/venv"
PY="$V/Scripts/python.exe"
if [ ! -x "$PY" ]; then
  BASE="$(command -v py >/dev/null 2>&1 && echo "py -3.14" || echo python)"
  $BASE -m venv "$V"
  "$PY" -m pip install --quiet pyinstaller pillow
fi
EV="${ELECTRON_VERSION:-44.9.3}"                        # 21.10.2026, стабильная ветка 44 (взята 05.11.2026)
ED="${ELECTRON_DIR:-$R/game/work/editor/electron/electron-v$EV}"
RCEDIT="${RCEDIT:-$R/game/work/editor/electron/dl/rcedit-x64.exe}"
DL="$R/game/work/editor/electron/dl"
if [ ! -f "$ED/electron.exe" ] && [ -z "${ELECTRON_DIR:-}" ]; then   # нет — скачать официальный zip и сверить SHA-256
  Z="electron-v$EV-win32-x64.zip"; U="https://github.com/electron/electron/releases/download/v$EV"
  mkdir -p "$DL"
  [ -f "$DL/$Z" ] || curl -fL -o "$DL/$Z" "$U/$Z"
  curl -fsL -o "$DL/SHASUMS256.txt" "$U/SHASUMS256.txt"
  want="$(grep "[ *]$Z\$" "$DL/SHASUMS256.txt" | cut -d' ' -f1)"
  have="$(sha256sum "$DL/$Z" | cut -d' ' -f1)"
  [ -n "$want" ] && [ "$want" = "$have" ] || { echo "SHA-256 $Z не сошёлся с SHASUMS256.txt"; exit 1; }
  "$PY" -I -c "import sys, zipfile; zipfile.ZipFile(sys.argv[1]).extractall(sys.argv[2])" "$(W "$DL/$Z")" "$(W "$ED")"
fi
if [ ! -f "$RCEDIT" ]; then
  mkdir -p "$(dirname "$RCEDIT")"
  curl -fL -o "$RCEDIT" "https://github.com/electron/rcedit/releases/download/v2.0.0/rcedit-x64.exe"
fi
[ -f "$ED/electron.exe" ] || { echo "нет Electron $ED (docs/editor.md, «Сборка»)"; exit 1; }
ICO="$R/nhl-legacy-port/launcher/icon/nhllegacy.ico"
[ -f "$ICO" ] || "$PY" "$R/tools/make_icon.py"
VER="$(tr -d '\r\n' < "$R/VERSION" 2>/dev/null || echo 0.0.0)"
OUT="$R/nhl-legacy-port/out/editor"
WORK="$R/game/work/editor/build"
APP="$OUT/editor"
mkdir -p "$OUT" "$WORK"
IFS=. read -r V1 V2 V3 <<< "$VER"
cat > "$WORK/version.txt" <<EOF
VSVersionInfo(
  ffi=FixedFileInfo(filevers=(${V1:-0}, ${V2:-0}, ${V3:-0}, 0), prodvers=(${V1:-0}, ${V2:-0}, ${V3:-0}, 0)),
  kids=[StringFileInfo([StringTable('040904B0', [
    StringStruct('FileDescription', 'NHL Legacy Remaster Editor server'),
    StringStruct('ProductName', 'NHL Legacy Remaster'),
    StringStruct('FileVersion', '$VER'),
    StringStruct('ProductVersion', '$VER'),
    StringStruct('OriginalFilename', 'nhllegacy_editor_server.exe')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])])
EOF
(cd "$WORK" && "$PY" -m PyInstaller --noconfirm --clean --onedir --console --name nhllegacy_editor_server \
  --contents-directory lib --icon "$(W "$ICO")" --version-file "$(W "$WORK/version.txt")" \
  --distpath "$(W "$WORK/dist")" --workpath "$(W "$WORK/pyi")" --specpath "$(W "$WORK")" \
  --paths "$(W "$R/tools")" --paths "$(W "$R/tools/editor")" --paths "$(W "$R/tools/legacy_data")" \
  --add-data "$(W "$R/tools/editor/web");web" --add-data "$(W "$R/VERSION");." --add-data "$(W "$ICO");." \
  --hidden-import rosters --hidden-import audio --hidden-import meshes --hidden-import texts --hidden-import gamecat \
  --hidden-import fepreview --hidden-import kitnew --hidden-import pickers \
  --hidden-import fefont --hidden-import locdb --hidden-import xex --hidden-import unlockables --hidden-import draft_roster \
  --hidden-import roster.codes --hidden-import roster.ovrformula --hidden-import roster.lines --hidden-import roster.dbview \
  --hidden-import big --hidden-import unchunk --hidden-import lzx --hidden-import rw4mesh --hidden-import kitpaint \
  --hidden-import music --hidden-import roster_merge --exclude-module numpy --exclude-module scipy --exclude-module tkinter \
  "$(W "$R/tools/editor/__main__.py")")
# сборка приложения в чистую папку рядом, потом — на место прежней (прежняя — в Корзину)
NEW="$OUT/editor.new"
[ ! -e "$NEW" ] || "$PY" "$R/tools/recycle.py" drop "$NEW" > /dev/null
mkdir -p "$NEW"
cp -r "$ED"/. "$NEW"/
rm -f "$NEW/resources/default_app.asar"
find "$NEW/locales" -name '*.pak' ! -name 'en-US.pak' ! -name 'ru.pak' -delete
mv "$NEW/electron.exe" "$NEW/NHL Legacy Editor.exe"
mkdir -p "$NEW/resources/app"
cp "$R/tools/editor/electron/package.json" "$R/tools/editor/electron/main.js" "$R/tools/editor/electron/preload.js" \
  "$NEW/resources/app/"
cp "$ICO" "$NEW/resources/app/icon.ico"
sed -i "s/\"version\": \"[^\"]*\"/\"version\": \"$VER\"/" "$NEW/resources/app/package.json"
cp -r "$WORK/dist/nhllegacy_editor_server" "$NEW/backend"
mv "$NEW/LICENSE" "$NEW/LICENSE.electron.txt"
"$RCEDIT" "$(W "$NEW/NHL Legacy Editor.exe")" --set-icon "$(W "$ICO")" \
  --set-file-version "$VER" --set-product-version "$VER" \
  --set-version-string FileDescription "NHL Legacy Remaster Editor" \
  --set-version-string ProductName "NHL Legacy Remaster" \
  --set-version-string CompanyName "megarohas" \
  --set-version-string InternalName "NHL Legacy Editor" \
  --set-version-string OriginalFilename "NHL Legacy Editor.exe" \
  --set-version-string LegalCopyright "NHL Legacy Remaster tools (MIT); Electron (MIT), Chromium — see LICENSE.electron.txt, LICENSES.chromium.html"
echo "Electron $EV, $VER" > "$NEW/version.txt"
[ ! -e "$APP" ] || "$PY" "$R/tools/recycle.py" drop "$APP" > /dev/null
mv "$NEW" "$APP"
du -sh "$APP"
ls "$APP"
