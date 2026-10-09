#!/bin/bash
# Ставит моды-данные NHL Legacy (game/work/legacy-data/out — дерево путей как в cache:) в cache: порта
# Legacy — только при закрытой игре (или игре с другой папкой userdata). Порт берёт свободный файл
# cache:\<путь> раньше архива. Описание — docs/legacy-data.md.
#   bash tools/legacy_data/install-legacy-data.sh [--ahl32] [--nhl24] [ЧАСТЬ…]
#                                                               # ЧАСТЬ — начало пути: db fe/loc fe/ion/fonts
#                                                               # audio rendering … (без частей — всё из out);
#                                                               # @ФАЙЛ — список путей (models/files.txt и т. п.);
#                                                               # --nhl24 — и накладка пакета NHL 24 (out-nhl24)
#   CACHE=путь bash …                                           # своя папка cache: (иначе — строка
#                                                               # «CACHE: …» в game/work/status/legacy-port.md)
#   LEGACY_DATA_STATE=папка bash …                              # свои installed.txt и backup/ (проверка на копии)
# Что лежало в cache: до первой установки (чужой файл с тем же именем) — копия в legacy-data/backup/;
# список поставленного — legacy-data/installed.txt. Откат — uninstall-legacy-data.sh.
# Без частей: файлы прошлой установки, которых больше нет в out, убираются (или возвращаются прежние).
# Работает install_legacy_data.py рядом (на 2500 файлов — секунды).
export ORIG_PWD="$(pwd -W 2>/dev/null || pwd)"
exec python "$(dirname "$0")/install_legacy_data.py" install "$@"
