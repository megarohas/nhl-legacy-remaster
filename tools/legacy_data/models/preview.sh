#!/bin/bash
# Листы превью NHL Legacy: «Legacy, оригинал / Legacy с модом / NHL 13 с модом» → game/work/legacy-data/models/preview/
R="$(cd "$(dirname "$0")/../../.." && pwd)"           # tools/legacy_data/models → репозиторий
[ -d "$R/game" ] || R="$(cd "$(git -C "$R" rev-parse --git-common-dir)/.." && pwd)"
cd "$R" || exit 1
M=game/work/legacy-data/models
export PYTHONIOENCODING=utf-8
python tools/rw4mesh.py --game legacy preview > $M/preview-sock.log 2>&1
python tools/sticktape.py --game legacy preview --round bottom2 > $M/preview-tape.log 2>&1
python tools/jersey10.py --game legacy preview > $M/preview-jersey.log 2>&1
tail -n 2 $M/preview-sock.log $M/preview-tape.log $M/preview-jersey.log
