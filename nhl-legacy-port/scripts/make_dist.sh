#!/bin/bash
# Папка для друзей: nhl-legacy-port/dist/NHL Legacy Remaster vX.Y.Z (версия — файл VERSION) — порт без файлов игры
# (docs/legacy-port.md); exe с иконкой (tools/make_icon.py + tools/set_exe_icon.py) и лаунчер.
#   [BUILD=папка] [AHL32=1] bash nhl-legacy-port/scripts/make_dist.sh [--mods]   # AHL32=1 — моды с базой «АХЛ на 32»
# Берёт Release-сборку (out/build/win-amd64-release: свой SDK, D3D12 + Vulkan), DLL рантайма MSVC
# (app-local, из VC Redist BuildTools), шаблоны dist-template/ (nhllegacy.toml — пути пустые:
# game\ рядом с exe; README.txt). С --mods — ещё моды-данные из nhl-legacy-port/userdata/cache/guest — по частям в
# content\database, menus, photos, logos, uniforms, heads, equipment, arenas, music (tools/legacy_paths.py, раскладку
# одобрил пользователь 05.11.2026); без кэша, который пишет сама игра. exe склеивает их в один cache:.
# Личное (сейвы, настройки лаунчера) — в saves\ (с 0.17.0, docs/legacy-port.md, «Папка saves»): в папке релиза она
# пустая, стартовые PROFILE и ROSTER лежат в start-saves\ — exe копирует их в saves\, только если там нет сейва
# этого вида. Поэтому копия нового релиза поверх старой папки (даже вместе с saves\) сейвы не трогает.
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
mkdir -p "$D/game" "$D/saves"
cp "$B/nhllegacy.exe" "$B/nhllegacy_snap.exe" "$B/rexruntime.dll" "$B/rexgpu-xenos.dll" "$D/"
L="$P/out/launcher/nhllegacy_launcher.exe"; [ -f "$L" ] || L="$B/nhllegacy_launcher.exe"  # свежая сборка лаунчера
[ -f "$L" ] && cp "$L" "$D/" || echo "нет лаунчера — nhl-legacy-port/launcher/build.cmd"
# редактор игры (docs/editor.md): свежая сборка tools/editor/build.sh, иначе тот, что стоит в BUILD
E="$P/out/editor/nhllegacy_editor.exe"; [ -f "$E" ] || E="$B/nhllegacy_editor.exe"
[ -f "$E" ] && cp "$E" "$D/" || echo "нет редактора — bash tools/editor/build.sh"
ICO="$P/launcher/icon/nhllegacy.ico"
if [ -f "$ICO" ]; then python "$P/../tools/set_exe_icon.py" "$D/nhllegacy.exe" "$ICO" --no-backup; else
  echo "нет иконки — python tools/make_icon.py"; fi
for dll in msvcp140.dll msvcp140_atomic_wait.dll vcruntime140.dll vcruntime140_1.dll; do
  cp "$CRT/$dll" "$D/"
done
cp "$P/dist-template/nhllegacy.toml" "$P/dist-template/README.txt" "$D/"
echo "Сюда — файлы игры NHL Legacy: default.xex и *.big (см. README.txt)." > "$D/game/ПОЛОЖИТЬ СЮДА ИГРУ.txt"
if [ "${1:-}" = "--mods" ]; then
  # Кэш самой игры (cache:\ раздела 360) не переносим: версия кэша, реклама, повторы (legacy_paths: --content-only).
  # Установка BUILD уже переведена на content\ — берём её части как есть, иначе раскладываем её cache\guest.
  if [ -d "$B/content" ]; then
    cp -r "$B/content" "$D/"
  else
    PYTHONIOENCODING=utf-8 python "$P/../tools/legacy_paths.py" migrate --from "$P/userdata/cache/guest" --install "$D" \
      --write --content-only
  fi
  DB="$D/content/database/db"
  # база на 32 команды в модах → франшиза на 32 по умолчанию
  if [ -f "$DB/nhlng.db" ]; then
    sed -i 's/^nhl_teams = 30$/nhl_teams = 32/' "$D/nhllegacy.toml"
    # старт «NHL Entry Draft» берёт составы из db/draft_roster.db (на диске — драфт 2015): та же база под этим именем
    # (docs/legacy-data.md, «draft_roster.db»); если в cache: её нет — кладём копию сами
    [ -f "$DB/draft_roster.db" ] || cp "$DB/nhlng.db" "$DB/draft_roster.db"
  fi
  # база «АХЛ на 32» (legacy-data --ahl32: в лиге АХЛ 32 клуба — Coachella Valley и Henderson) → АХЛ на 32
  if [ "${AHL32:-}" = "1" ]; then
    sed -i 's/^nhl_ahl_teams = 30$/nhl_ahl_teams = 32/' "$D/nhllegacy.toml"
  fi
  # Список шейдеров (shareable): от железа не зависит, игра собирает всё из него при запуске, а не посреди матча.
  # Сама сборка драйвером своя на каждом ПК (docs/legacy-port.md, «Надпись о сборке шейдеров»).
  # С content\ кэш игры и шейдеров — cache\ рядом с exe (nhllegacy_app.h).
  SH="$P/userdata/cache/shaders/shareable"; [ -d "$B/cache/shaders/shareable" ] && SH="$B/cache/shaders/shareable"
  if [ -d "$SH" ]; then
    mkdir -p "$D/cache/shaders/shareable"
    cp "$SH/"* "$D/cache/shaders/shareable/"
  fi
  # Стартовые сейвы (SAVES=0 — без них): последний PROFILE (настройки игры, правила, слайдеры геймплея, звук, видео,
  # управление) и последний ROSTER (составы с правками) установки BUILD — в start-saves\profiles, start-saves\rosters.
  # Профиль порта один на всех ПК (XUID B13EBABEBABEBABE, имя «User» — SDK, xam/user_profile.cpp), так что игра
  # друга подхватит их как свои, но только при первом запуске: если в saves\ уже есть PROFILE или ROSTER, стартовые
  # этого вида не копируются (src/nhllegacy_saves.cpp). Карьеры (DYNASTY, BEAPRO…) не переносим. Где сейвы
  # установки — tools/legacy_saves.py (saves\ с 0.17.0 или старое место userdata\<xuid>\454109EC\00000001).
  if [ "${SAVES:-1}" = "1" ]; then
    for kind in PROFILE ROSTER; do
      if ! paths=$(PYTHONIOENCODING=utf-8 python "$P/../tools/legacy_saves.py" latest "$kind" --paths --install "$B"); then
        echo "нет сейва $kind"; continue
      fi
      dir=$(printf '%s\n' "$paths" | sed -n 2p | tr -d '\r'); header=$(printf '%s\n' "$paths" | sed -n 3p | tr -d '\r')
      last=$(basename "$dir")
      case "$kind" in PROFILE) sub=profiles ;; ROSTER) sub=rosters ;; esac
      mkdir -p "$D/start-saves/$sub"
      cp -r "$dir" "$D/start-saves/$sub/"
      [ -f "$header" ] && cp "$header" "$D/start-saves/$sub/$last.header"
      echo "стартовый сейв: $sub/$last"
    done
  fi
fi
du -sh "$D"
ls "$D"
