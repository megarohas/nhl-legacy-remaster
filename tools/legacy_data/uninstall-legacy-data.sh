#!/bin/bash
# Снимает моды-данные NHL Legacy, поставленные install-legacy-data.sh: файлы из legacy-data/installed.txt
# удаляются из cache: порта (чужие файлы, лежавшие там до установки, возвращаются из legacy-data/backup/).
#   bash tools/legacy_data/uninstall-legacy-data.sh [ЧАСТЬ…]   # только эти части (db, fe/loc, audio…)
#   CACHE=путь LEGACY_DATA_STATE=папка bash …                 # на копии userdata (как у install-legacy-data.sh)
export ORIG_PWD="$(pwd -W 2>/dev/null || pwd)"
exec python "$(dirname "$0")/install_legacy_data.py" uninstall "$@"
