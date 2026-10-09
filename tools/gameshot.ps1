# gameshot.ps1 — проверка в игре без геймпада: запуск сборки, снимок окна, нажатия.
# Ввод — режим SDK mnk_mode (клавиатура = геймпад; включается параметром --mnk_mode=true, toml не меняется):
# Start — Return или X, A — Space, B — Backspace, X — L, Y — P, LT/RT — Q/E, LB/RB — 1/3, левый стик — W/A/S/D,
# крестовина — Shift+стрелки, Back — Tab.
#
# ПРАВИЛА (09.10.2026, после жалобы пользователя: тестовая игра на весь экран забирала фокус при каждой его
# попытке переключиться на своё окно):
#   - окно игры НИКОГДА не выводится вперёд: нет SetForegroundWindow / BringWindowToTop / AttachThreadInput /
#     ShowWindow и «трюков» с Alt/F24;
#   - клавиши уходят, только если окно игры УЖЕ активно (на переднем плане). Нет — клавиша не отправляется,
#     ответ WAIT_FOCUS (вызывающий ждёт и пробует позже; -FocusWaitSec N — ждать здесь до N секунд, не забирая
#     фокус); активность проверяется перед каждой клавишей и сразу после неё;
#   - игра запускается в окне (--fullscreen=false) небольшого размера (-WindowW/-WindowH, по умолчанию 960×540
#     логических) и без активации окна (SDL_WINDOW_ACTIVATE_WHEN_SHOWN/RAISED = 0); -Fullscreen — на весь экран,
#     только по прямой просьбе пользователя;
#   - лучше всего — ввод вообще без клавиатуры: виртуальный геймпад порта (cvar nhl_virtual_pad, файл *_pad.txt
#     рядом с exe; NHL 13 — port/src/nhl13_pad.cpp, Legacy — legacy-port/src/nhllegacy_pad.cpp): фокус не нужен;
#   - снимок — PrintWindow (флаги 3: клиентская часть, полное содержимое D3D12) из DPI-aware процесса; фокус для
#     него не нужен и не трогается. -Fit 1280x720 — снимок приводится к этому размеру (пиксельные проверки не
#     зависят от размера окна), -Half — вдвое меньше окна. Свёрнутое окно не снимается (MINIMIZED).
# Замок game/work/status/game.lock (правила общие для агентов) берёт и снимает вызывающий.
#   -Do start  [-Log путь] [-Extra '--x=y',…]   запустить (если игра уже запущена — ALREADY_RUNNING)
#   -Do shot   -Out файл.png                    снимок окна
#   -Do key    -Keys "Return Space Shift+Down"  нажать по очереди (-HoldMs удержание, -GapMs пауза)
#   -Do stop                                    закрыть: taskkill без /F, через 30 с — /F
#   -Do info                                    pid, окно, размер, активно ли
#   -Do seq    -Steps "wait:25;shot:a.png;key:Return Space;wait:6;shot:b.png"   шаги по очереди
#   -Game legacy                                порт NHL Legacy (legacy-port/): процесс nhllegacy, свой exe и лог
# Пример: powershell -ExecutionPolicy Bypass -File tools\gameshot.ps1 -Do shot -Out game\work\x.png
param(
    [Parameter(Mandatory = $true)][ValidateSet('start', 'shot', 'key', 'stop', 'info', 'seq')][string]$Do,
    [string]$Out = '',
    [string]$Keys = '',
    [int]$HoldMs = 150,
    [int]$GapMs = 600,
    [string]$Log = 'S:/Claude/megarohas_nhl13/port/out/gameshot.log',
    [string]$Exe = 'S:\Claude\megarohas_nhl13\port-ffx\out\build\win-amd64-release\nhl13.exe',
    [string[]]$Extra = @(),
    [ValidateSet('nhl13', 'legacy')][string]$Game = 'nhl13',
    [string]$Steps = '',
    [switch]$Half,
    [string]$Fit = '',
    [int]$FocusWaitSec = 0,
    [int]$WindowW = 960,
    [int]$WindowH = 540,
    [switch]$Fullscreen
)
$ErrorActionPreference = 'Stop'
$Proc = 'nhl13'
if ($Game -eq 'legacy') {
    $Proc = 'nhllegacy'
    if (-not $PSBoundParameters.ContainsKey('Exe')) { $Exe = 'S:\Claude\megarohas_nhl13\legacy-port\out\build\win-amd64-release\nhllegacy.exe' }
    if (-not $PSBoundParameters.ContainsKey('Log')) { $Log = 'S:/Claude/megarohas_nhl13/legacy-port/out/gameshot.log' }
}
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class GT {
  [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
  [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr hdc, uint flags);
  [DllImport("user32.dll")] public static extern bool GetClientRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
  [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr h);
  [DllImport("user32.dll")] public static extern void keybd_event(byte vk, byte scan, uint flags, UIntPtr extra);
  [DllImport("user32.dll")] public static extern uint MapVirtualKey(uint code, uint mapType);
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left, Top, Right, Bottom; }
}
"@
[GT]::SetProcessDPIAware() | Out-Null          # физические пиксели окна (масштаб Windows 125 %)

function Get-GameWindow {
    $p = Get-Process -Name $Proc -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1
    if (-not $p) { return $null }
    return $p
}

# Окно игры активно? Подождать (не забирая фокус) до $sec секунд.
function Wait-Active($h, [int]$sec) {
    $deadline = (Get-Date).AddSeconds($sec)
    while ($true) {
        if ([GT]::GetForegroundWindow() -eq $h) { return $true }
        if ((Get-Date) -ge $deadline) { return $false }
        Start-Sleep -Milliseconds 500
    }
}

$VK = @{ 'Return' = 0x0D; 'Enter' = 0x0D; 'Space' = 0x20; 'Backspace' = 0x08; 'Tab' = 0x09; 'Escape' = 0x1B;
    'Up' = 0x26; 'Down' = 0x28; 'Left' = 0x25; 'Right' = 0x27; 'Shift' = 0x10 }
$EXT = @(0x26, 0x28, 0x25, 0x27)

function Send-Vk([int]$vk, [bool]$up) {
    $scan = [GT]::MapVirtualKey($vk, 0)
    $fl = 0
    if ($EXT -contains $vk) { $fl = $fl -bor 1 }
    if ($up) { $fl = $fl -bor 2 }
    [GT]::keybd_event([byte]$vk, [byte]$scan, [uint32]$fl, [UIntPtr]::Zero)
}

function Key-Code([string]$k) {
    if ($VK.ContainsKey($k)) { return $VK[$k] }
    if ($k.Length -eq 1) { return [int][char]$k.ToUpper() }
    throw "неизвестная клавиша $k"
}

function Do-Shot([string]$path) {
    $p = Get-GameWindow
    if (-not $p) { Write-Output 'NO_WINDOW'; return $false }
    $h = $p.MainWindowHandle
    if ([GT]::IsIconic($h)) { Write-Output 'MINIMIZED'; return $false }   # свёрнутое окно не разворачиваем
    $c = New-Object GT+RECT
    [GT]::GetClientRect($h, [ref]$c) | Out-Null
    if ($c.Right -le 0 -or $c.Bottom -le 0) { Write-Output 'NO_CLIENT'; return $false }
    $bmp = New-Object System.Drawing.Bitmap $c.Right, $c.Bottom
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $hdc = $g.GetHdc()
    $ok = [GT]::PrintWindow($h, $hdc, 3)          # PW_CLIENTONLY | PW_RENDERFULLCONTENT
    $g.ReleaseHdc($hdc); $g.Dispose()
    $dir = Split-Path -Parent $path
    if ($dir -and -not (Test-Path $dir)) { New-Item -ItemType Directory -Force $dir | Out-Null }
    $tw = 0; $th = 0
    if ($Fit -match '^(\d+)x(\d+)$') { $tw = [int]$Matches[1]; $th = [int]$Matches[2] }
    elseif ($Half) { $tw = [int]($c.Right / 2); $th = [int]($c.Bottom / 2) }
    if ($tw -gt 0 -and ($tw -ne $bmp.Width -or $th -ne $bmp.Height)) {
        $small = New-Object System.Drawing.Bitmap $tw, $th
        $g2 = [System.Drawing.Graphics]::FromImage($small)
        $g2.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBilinear
        $g2.DrawImage($bmp, 0, 0, $tw, $th)
        $g2.Dispose(); $bmp.Dispose(); $bmp = $small
    }
    $bmp.Save($path, [System.Drawing.Imaging.ImageFormat]::Png)
    Write-Output "SHOT $path ($($bmp.Width)x$($bmp.Height), client $($c.Right)x$($c.Bottom), PrintWindow=$ok)"
    $bmp.Dispose()
    return $true
}

function Do-Keys([string]$keys) {
    $p = Get-GameWindow
    if (-not $p) { Write-Output 'NO_WINDOW'; return $false }
    $h = $p.MainWindowHandle
    foreach ($k in ($keys -split '\s+' | Where-Object { $_ })) {
        # Только в уже активное окно игры; фокус не забираем никогда. Не активно — WAIT_FOCUS, клавиша не уходит.
        if (-not (Wait-Active $h $FocusWaitSec)) {
            Write-Output "WAIT_FOCUS: окно игры не активно (пользователь работает?), клавиша $k не отправлена"
            return $false
        }
        $mods = @(); $main = $k
        if ($k -like 'Shift+*') { $mods = @(0x10); $main = $k.Substring(6) }
        $code = Key-Code $main
        # ещё раз вплотную к нажатию: пользователь мог переключиться
        if ([GT]::GetForegroundWindow() -ne $h) { Write-Output "WAIT_FOCUS: окно игры не активно, клавиша $k не отправлена"; return $false }
        foreach ($m in $mods) { Send-Vk $m $false }
        Send-Vk $code $false
        Start-Sleep -Milliseconds $HoldMs
        # отпускание шлём всегда: иначе клавиша «залипнет» в игре (отпускание без нажатия безвредно)
        Send-Vk $code $true
        foreach ($m in $mods) { Send-Vk $m $true }
        if ([GT]::GetForegroundWindow() -ne $h) { Write-Output "WAIT_FOCUS: окно игры перестало быть активным после $k"; return $false }
        Write-Output "key $k"
        Start-Sleep -Milliseconds $GapMs
    }
    return $true
}

switch ($Do) {
    'info' {
        $p = Get-GameWindow
        if (-not $p) { Write-Output 'NO_WINDOW'; exit 1 }
        $r = New-Object GT+RECT
        [GT]::GetClientRect($p.MainWindowHandle, [ref]$r) | Out-Null
        Write-Output ("pid {0} hwnd {1} client {2}x{3} title '{4}' active {5} minimized {6}" -f $p.Id, $p.MainWindowHandle, $r.Right, $r.Bottom, $p.MainWindowTitle, ([GT]::GetForegroundWindow() -eq $p.MainWindowHandle), [GT]::IsIconic($p.MainWindowHandle))
    }
    'start' {
        if (Get-Process -Name $Proc -ErrorAction SilentlyContinue) { Write-Output 'ALREADY_RUNNING'; exit 2 }
        $win = @()
        if (-not $Fullscreen) { $win = @('--fullscreen=false', "--window_width=$WindowW", "--window_height=$WindowH") }
        $args2 = @("--log_file=$Log", '--mnk_mode=true') + $win + $Extra
        # окно показывается без активации (SDL: SW_SHOWNA вместо SW_SHOW) и не активируется при подъёме —
        # новое окно игры не отнимает фокус у пользователя и при запуске; переменные — только для дочернего процесса
        $env:SDL_WINDOW_ACTIVATE_WHEN_SHOWN = '0'
        $env:SDL_WINDOW_ACTIVATE_WHEN_RAISED = '0'
        $p = Start-Process -FilePath $Exe -ArgumentList $args2 -WorkingDirectory (Split-Path -Parent $Exe) -PassThru
        Write-Output "STARTED pid $($p.Id): $Exe $($args2 -join ' ')"
    }
    'shot' {
        $r = Do-Shot $Out
        if (-not ($r -contains $true)) { $r | Where-Object { $_ -isnot [bool] }; exit 1 }
        $r | Where-Object { $_ -isnot [bool] }
    }
    'seq' {
        # Шаги через «;»: wait:СЕКУНДЫ, shot:ФАЙЛ.png, key:КЛАВИШИ (как у -Keys). Нет окна или оно не активно — выход 1.
        foreach ($st in ($Steps -split ';' | ForEach-Object { $_.Trim() } | Where-Object { $_ })) {
            $kind, $arg = $st -split ':', 2
            switch ($kind) {
                'wait' { Start-Sleep -Milliseconds ([int]([double]$arg * 1000)) }
                'shot' { $r = Do-Shot $arg; $r | Where-Object { $_ -isnot [bool] }; if (-not ($r -contains $true)) { exit 1 } }
                'key' { $r = Do-Keys $arg; $r | Where-Object { $_ -isnot [bool] }; if (-not ($r -contains $true)) { exit 1 } }
                default { throw "шаг $st?" }
            }
        }
    }
    'key' {
        $r = Do-Keys $Keys
        $r | Where-Object { $_ -isnot [bool] }
        if (-not ($r -contains $true)) { exit 1 }
    }
    'stop' {
        $p = Get-Process -Name $Proc -ErrorAction SilentlyContinue
        if (-not $p) { Write-Output 'NOT_RUNNING'; exit 0 }
        & taskkill /IM "$Proc.exe" | Out-Null
        for ($i = 0; $i -lt 30; $i++) {
            Start-Sleep -Seconds 1
            if (-not (Get-Process -Name $Proc -ErrorAction SilentlyContinue)) { Write-Output "CLOSED after $($i+1)s"; exit 0 }
        }
        & taskkill /F /IM "$Proc.exe" | Out-Null
        Start-Sleep -Seconds 2
        Write-Output "KILLED (/F): $(if (Get-Process -Name $Proc -ErrorAction SilentlyContinue) {'still running!'} else {'gone'})"
    }
}
