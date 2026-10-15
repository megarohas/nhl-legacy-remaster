# Резервная копия данных проекта, которых нет в git, на другой диск (docs/backup.md).
#   powershell -NoProfile -ExecutionPolicy Bypass -File tools\backup_data.ps1 [-Dst D:\backup\megarohas_nhl13-data]
# Копирует новое и изменённое и НИЧЕГО не удаляет в копии (без /MIR и /PURGE): если на S: что-то
# пропадёт, в копии оно останется. /XJ — не заходить в junction/symlink (так 09.10 чистка %TEMP%
# по ссылке снесла game\, ref\ и best_of_nhl\). Сейвы дополнительно — снимок на каждый день.
param(
    [string]$Src = 'S:\Claude\megarohas_nhl13',
    [string]$Dst = 'D:\backup\megarohas_nhl13-data'
)
$ErrorActionPreference = 'Continue'

# Что копировать. Файлы игр (game\other, game\raw, game\extracted) не берём: их снова снимают с
# приставки, а места на D: на них нет. venv, кэш Python и промежуточные файлы сборки — тоже.
$dirs = @(
    'game\work',
    'game\userdata',
    'best_of_nhl',
    'nhl-legacy-port\userdata',
    'nhl-legacy-port\dist',
    'nhl-legacy-port\codegen',
    'nhl-legacy-port\out\build\win-amd64-release',
    'nhl-13-port\generated',
    'ref\rexglue-sdk-custom\install'
)
$saves = @(
    'nhl-legacy-port\userdata\B13EBABEBABEBABE',
    'game\userdata\B13EBABEBABEBABE'
)
$common = @('/E', '/XJ', '/R:1', '/W:1', '/NP', '/NFL', '/NDL', '/MT:8',
            '/XD', 'venv', '.venv', '__pycache__', 'CMakeFiles', '.restoring',
            '/XF', '*.obj', '*.ilk', '*.restoring')

$stamp = Get-Date -Format 'yyyyMMdd-HHmm'
$logDir = Join-Path $Dst '_logs'
New-Item -ItemType Directory -Force $logDir | Out-Null
$log = Join-Path $logDir "backup-$stamp.log"
$worst = 0

foreach ($d in $dirs) {
    $s = Join-Path $Src $d
    if (-not (Test-Path $s)) { continue }
    & robocopy $s (Join-Path $Dst $d) @common "/LOG+:$log" | Out-Null
    if ($LASTEXITCODE -gt $worst) { $worst = $LASTEXITCODE }
}

# Снимок сейвов за день: копия выше обновляется, и испорченный сейв затёр бы её; снимки — нет.
$snap = Join-Path $Dst ('_saves\' + (Get-Date -Format 'yyyyMMdd'))
foreach ($d in $saves) {
    $s = Join-Path $Src $d
    if (-not (Test-Path $s)) { continue }
    & robocopy $s (Join-Path $snap $d) @common "/LOG+:$log" | Out-Null
    if ($LASTEXITCODE -gt $worst) { $worst = $LASTEXITCODE }
}

# robocopy: 0–7 — успех (1 = что-то скопировано), 8+ — были ошибки (подробности в журнале).
$state = if ($worst -ge 8) { 'ОШИБКИ' } else { 'ок' }
"$stamp $state (robocopy max $worst) -> $log" | Add-Content (Join-Path $logDir 'history.txt')
Write-Output "Резервная копия: $state, журнал $log"
if ($worst -ge 8) { exit 1 } else { exit 0 }
