#!/usr/bin/env bash
# Сборка nhllegacy_editor.exe (docs/editor.md, «Сборка»): один exe без установки — Python, код tools/ и Pillow.
#
#   bash tools/editor/build.sh            # → nhl-legacy-port/out/editor/nhllegacy_editor.exe
#
# Окружение сборки — game/work/editor/venv (создаётся само: Python 3.14 с python.org, pip install pyinstaller pillow).
# В exe только код и интерфейс (tools/*.py, tools/editor/web) и значок лаунчера; файлов игры EA в нём нет.
# Иконка — nhl-legacy-port/launcher/icon/nhllegacy.ico (tools/make_icon.py, не в git), версия — файл VERSION.
set -euo pipefail
R="$(cd "$(dirname "$0")/../.." && pwd)"
V="$R/game/work/editor/venv"
PY="$V/Scripts/python.exe"
if [ ! -x "$PY" ]; then
  BASE="$(command -v py >/dev/null 2>&1 && echo "py -3.14" || echo python)"
  $BASE -m venv "$V"
  "$PY" -m pip install --quiet pyinstaller pillow
fi
ICO="$R/nhl-legacy-port/launcher/icon/nhllegacy.ico"
[ -f "$ICO" ] || "$PY" "$R/tools/make_icon.py"
VER="$(tr -d '\r\n' < "$R/VERSION" 2>/dev/null || echo 0.0.0)"
OUT="$R/nhl-legacy-port/out/editor"
WORK="$R/game/work/editor/build"
mkdir -p "$OUT" "$WORK"
IFS=. read -r V1 V2 V3 <<< "$VER"
cat > "$WORK/version.txt" <<EOF
VSVersionInfo(
  ffi=FixedFileInfo(filevers=(${V1:-0}, ${V2:-0}, ${V3:-0}, 0), prodvers=(${V1:-0}, ${V2:-0}, ${V3:-0}, 0)),
  kids=[StringFileInfo([StringTable('040904B0', [
    StringStruct('FileDescription', 'NHL Legacy Remaster Editor'),
    StringStruct('ProductName', 'NHL Legacy Remaster'),
    StringStruct('FileVersion', '$VER'),
    StringStruct('ProductVersion', '$VER'),
    StringStruct('OriginalFilename', 'nhllegacy_editor.exe')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])])
EOF
W() { cygpath -w "$1" 2>/dev/null || echo "$1"; }
cd "$WORK"
"$PY" -m PyInstaller --noconfirm --clean --onefile --windowed --name nhllegacy_editor \
  --icon "$(W "$ICO")" --version-file "$(W "$WORK/version.txt")" \
  --distpath "$(W "$OUT")" --workpath "$(W "$WORK/pyi")" --specpath "$(W "$WORK")" \
  --paths "$(W "$R/tools")" --paths "$(W "$R/tools/editor")" --paths "$(W "$R/tools/legacy_data")" \
  --add-data "$(W "$R/tools/editor/web");web" --add-data "$(W "$R/VERSION");." --add-data "$(W "$ICO");." \
  --hidden-import rosters --hidden-import audio --hidden-import meshes \
  --hidden-import roster.ovrformula --hidden-import roster.lines --hidden-import roster.dbview \
  --hidden-import big --hidden-import unchunk --hidden-import lzx --hidden-import rw4mesh --hidden-import kitpaint \
  --hidden-import music --hidden-import roster_merge --exclude-module numpy --exclude-module scipy --exclude-module tkinter \
  "$(W "$R/tools/editor/__main__.py")"
ls -la "$OUT/nhllegacy_editor.exe"
