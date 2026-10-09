#!/bin/bash
# Проверки собранного для NHL Legacy (те же инструменты с --game legacy), логи — game/work/legacy-data/models/check-*.log
R="$(cd "$(dirname "$0")/../../.." && pwd)"           # tools/legacy_data/models → репозиторий
[ -d "$R/game" ] || R="$(cd "$(git -C "$R" rev-parse --git-common-dir)/.." && pwd)"
cd "$R" || exit 1
M=${LEGACY_DATA_WORK:-game/work/legacy-data}/models
mkdir -p "$M"
export PYTHONIOENCODING=utf-8
python tools/rw4mesh.py --game legacy roundtrip $M/out $M/tape/out-bottom2 $M/jersey10/out > $M/check-roundtrip.log 2>&1
python tools/rw4mesh.py --game legacy check > $M/check-sock.log 2>&1
python tools/sticktape.py --game legacy check --round bottom2 > $M/check-tape.log 2>&1
python tools/jersey10.py --game legacy check > $M/check-jersey.log 2>&1
tail -n 1 $M/check-roundtrip.log $M/check-sock.log $M/check-tape.log $M/check-jersey.log
