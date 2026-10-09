#!/bin/bash
# 3D-правки игроков для NHL Legacy: гетры (голень), обмотка клюшки до носка («низ-2», вратарские — без скругления,
# и реквизит вратарской клюшки prop/goaliestick*_left/right_0), нижний край свитера сзади как в NHL 10.
# Собирает инструментами с --game legacy (источник — распакованные архивы game/other/legacy/big) в
# game/work/legacy-data/models/{out,tape/out-bottom2,jersey10/out} и раскладывает готовые .rx2 в
# game/work/legacy-data/out/ (дерево cache:), список своих файлов — models/files.txt.
# В cache: порта Legacy НЕ ставит (это делает legacy-data своим install-скриптом). Игру не трогает.
#   bash tools/legacy_data/models/build.sh            # сборка + раскладка (~6 мин)
#   bash tools/legacy_data/models/build.sh --collect  # только раскладка уже собранного
R="$(cd "$(dirname "$0")/../../.." && pwd)"           # tools/legacy_data/models → репозиторий
[ -d "$R/game" ] || R="$(cd "$(git -C "$R" rev-parse --git-common-dir)/.." && pwd)"
cd "$R" || exit 1
M=${LEGACY_DATA_WORK:-game/work/legacy-data}/models
mkdir -p "$M"
O=${LEGACY_DATA_WORK:-game/work/legacy-data}/out
export PYTHONIOENCODING=utf-8
if [ "$1" != "--collect" ]; then
  python tools/rw4mesh.py --game legacy shin --no-preview > $M/build-sock.log 2>&1 || { echo "гетры: ошибка, $M/build-sock.log"; exit 1; }
  python tools/sticktape.py --game legacy build --round bottom2 --no-preview > $M/build-tape.log 2>&1 \
    || { echo "клюшки: ошибка, $M/build-tape.log"; exit 1; }
  python tools/jersey10.py --game legacy build > $M/build-jersey.log 2>&1 || { echo "свитера: ошибка, $M/build-jersey.log"; exit 1; }
fi
# раскладка: только свои файлы (чужие в out/ — формы, текстуры — не трогаются)
L=$M/files.txt
touch $L
: > $L.new
for src in $M/out $M/tape/out-bottom2 $M/jersey10/out; do
  (cd $src && find rendering -type f -name '*.rx2') | while read -r f; do echo "$src	$f"; done
done | sort -t$'\t' -k2 > $M/.collect
n=0; bad=0
while IFS=$'\t' read -r src f; do
  if [ -e "$O/$f" ] && ! grep -qxF "$f" $L; then
    echo "ЧУЖОЙ файл уже лежит в out: $f — не трогаю"; bad=$((bad + 1)); continue
  fi
  mkdir -p "$O/$(dirname "$f")"
  cmp -s "$src/$f" "$O/$f" || { cp -f "$src/$f" "$O/$f"; n=$((n + 1)); }
  echo "$f" >> $L.new
done < $M/.collect
rm -f $M/.collect
# свои файлы прошлой раскладки, которых больше нет в сборке (например, детализация без изменений), — убрать
while read -r f; do
  [ -n "$f" ] || continue
  grep -qxF "$f" $L.new || { rm -f "$O/$f"; echo "убран: $f"; }
done < $L
sort -o $L $L.new && rm -f $L.new
echo "3D-правки игроков (Legacy): обновлено $n, всего $(wc -l < $L) файлов в $O ($(date +%H:%M:%S)); чужих совпадений: $bad"
