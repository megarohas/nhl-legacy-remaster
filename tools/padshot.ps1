# padshot.ps1 — шаги проверки в игре виртуальным геймпадом порта и снимки, фокус окна не нужен.
# Стенд — папка с копией nhllegacy.exe и его DLL, игра запущена через gameshot.ps1 с --nhl_virtual_pad=true.
# Кнопки пишутся в nhllegacy_pad.txt рядом с exe (src/nhllegacy_pad.cpp), снимки делает gameshot.ps1 (PrintWindow).
#   -Dir   папка стенда (где лежит exe)
#   -Steps шаги через «;»:
#          pad:A            нажать (A B X Y LB RB LT RT START BACK UP DOWN LEFT RIGHT LS RS, LSL LSR LSU LSD, RSL RSR RSU RSD,
#                           сочетания через «+»); pad:RIGHT@500 — держать 500 мс
#          wait:3           подождать, секунд
#          shot:a.png       снимок окна 1280×720 (путь относительно -Shots)
#   -Shots папка снимков
# Пример: powershell -ExecutionPolicy Bypass -File tools\padshot.ps1 -Dir game\work\kit-prune\bench -Shots game\work\kit-prune\shots -Steps "pad:A;wait:2;shot:a.png"
param(
    [Parameter(Mandatory = $true)][string]$Dir,
    [Parameter(Mandatory = $true)][string]$Steps,
    [string]$Shots = '.',
    [int]$GapMs = 450
)
$ErrorActionPreference = 'Stop'
$Pad = Join-Path (Resolve-Path $Dir) 'nhllegacy_pad.txt'
New-Item -ItemType Directory -Force $Shots | Out-Null
$Shots = (Resolve-Path $Shots).Path
$Shot = Join-Path $PSScriptRoot 'gameshot.ps1'
$n = 0
if (Test-Path $Pad) {
    $last = Get-Content $Pad -Tail 1
    if ($last -match '^(\d+)\s') { $n = [int]$Matches[1] }
}
foreach ($step in ($Steps -split ';')) {
    $kind, $arg = ($step.Trim() -split ':', 2)
    switch ($kind) {
        'pad' {
            $btn, $hold = ($arg -split '@', 2)
            if (-not $hold) { $hold = 150 }
            $n += 1
            [System.IO.File]::AppendAllText($Pad, "$n $btn $hold $GapMs`n")
            Start-Sleep -Milliseconds ([int]$hold + $GapMs + 100)
        }
        'wait' { Start-Sleep -Seconds ([double]$arg) }
        'shot' { & powershell -NoProfile -ExecutionPolicy Bypass -File $Shot -Game legacy -Do shot -Fit 1280x720 -Out (Join-Path $Shots $arg) }
        default { throw "шаг не понял: $step" }
    }
}
