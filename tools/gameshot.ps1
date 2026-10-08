# gameshot.ps1 — проверка в игре без геймпада: запуск основной сборки (port-ffx), снимок окна, нажатия.
# Ввод — режим SDK mnk_mode (клавиатура = геймпад; включается параметром --mnk_mode=true, nhl13.toml не
# меняется): Start — Return или X, A — Space, B — Backspace, X — L, Y — P, LT/RT — Q/E, LB/RB — 1/3,
# левый стик — W/A/S/D, крестовина — Shift+стрелки, Back — Tab. Клавиши идут в окно игры (оно выводится
# вперёд). Снимок — PrintWindow с флагами 3 (клиентская часть, полное содержимое D3D12) из DPI-aware
# процесса: при масштабе Windows 125 % окно 1280×720 логических = 1600×900 пикселей.
# Замок game/work/status/game.lock (правила общие для агентов) берёт и снимает вызывающий.
#   -Do start  [-Log путь] [-Extra '--x=y',…]   запустить (если игра уже запущена — ALREADY_RUNNING)
#   -Do shot   -Out файл.png                    снимок окна
#   -Do key    -Keys "Return Space Shift+Down"  нажать по очереди (-HoldMs удержание, -GapMs пауза)
#   -Do stop                                    закрыть: taskkill без /F, через 30 с — /F
#   -Do info                                    pid, окно, размер, в фокусе ли
#   -Do seq    -Steps "wait:25;shot:a.png;key:Return Space;wait:6;shot:b.png"   шаги по очереди
#   -Half                                       снимки в половину размера (меньше файл)
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
    [switch]$Half
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
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool ClientToScreen(IntPtr h, ref POINT p);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int cmd);
  [DllImport("user32.dll")] public static extern bool BringWindowToTop(IntPtr h);
  [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr h);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
  [DllImport("user32.dll")] public static extern bool AttachThreadInput(uint a, uint b, bool attach);
  [DllImport("kernel32.dll")] public static extern uint GetCurrentThreadId();
  [DllImport("user32.dll")] public static extern void keybd_event(byte vk, byte scan, uint flags, UIntPtr extra);
  [DllImport("user32.dll")] public static extern uint MapVirtualKey(uint code, uint mapType);
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left, Top, Right, Bottom; }
  [StructLayout(LayoutKind.Sequential)] public struct POINT { public int X, Y; }
}
"@
[GT]::SetProcessDPIAware() | Out-Null          # физические пиксели окна (масштаб Windows 125 %)

function Get-GameWindow {
    $p = Get-Process -Name $Proc -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1
    if (-not $p) { return $null }
    return $p
}

function Focus-Game($h) {
    if ([GT]::IsIconic($h)) { [GT]::ShowWindow($h, 9) | Out-Null }
    $fg = [GT]::GetForegroundWindow()
    if ($fg -eq $h) { return $true }
    $pid0 = 0
    $t1 = [GT]::GetWindowThreadProcessId($fg, [ref]$pid0)
    $t2 = [GT]::GetCurrentThreadId()
    [GT]::AttachThreadInput($t2, $t1, $true) | Out-Null
    [GT]::keybd_event(0x12, 0x38, 0, [UIntPtr]::Zero)          # Alt — снять запрет смены переднего окна
    [GT]::keybd_event(0x12, 0x38, 2, [UIntPtr]::Zero)
    [GT]::BringWindowToTop($h) | Out-Null
    $ok = [GT]::SetForegroundWindow($h)
    [GT]::AttachThreadInput($t2, $t1, $false) | Out-Null
    Start-Sleep -Milliseconds 300
    return ([GT]::GetForegroundWindow() -eq $h)
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
    $c = New-Object GT+RECT
    [GT]::GetClientRect($h, [ref]$c) | Out-Null
    $bmp = New-Object System.Drawing.Bitmap $c.Right, $c.Bottom
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $hdc = $g.GetHdc()
    $ok = [GT]::PrintWindow($h, $hdc, 3)          # PW_CLIENTONLY | PW_RENDERFULLCONTENT
    $g.ReleaseHdc($hdc); $g.Dispose()
    $dir = Split-Path -Parent $path
    if ($dir -and -not (Test-Path $dir)) { New-Item -ItemType Directory -Force $dir | Out-Null }
    if ($Half) {
        $small = New-Object System.Drawing.Bitmap ([int]($c.Right / 2)), ([int]($c.Bottom / 2))
        $g2 = [System.Drawing.Graphics]::FromImage($small)
        $g2.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBilinear
        $g2.DrawImage($bmp, 0, 0, $small.Width, $small.Height)
        $g2.Dispose(); $bmp.Dispose(); $bmp = $small
    }
    $bmp.Save($path, [System.Drawing.Imaging.ImageFormat]::Png)
    Write-Output "SHOT $path ($($bmp.Width)x$($bmp.Height), PrintWindow=$ok)"
    $bmp.Dispose()
    return $true
}

function Do-Keys([string]$keys) {
    $p = Get-GameWindow
    if (-not $p) { Write-Output 'NO_WINDOW'; return $false }
    $h = $p.MainWindowHandle
    $f = Focus-Game $h
    Write-Output "focus: $f"
    foreach ($k in ($keys -split '\s+' | Where-Object { $_ })) {
        # Фокус проверяется перед КАЖДОЙ клавишей: рядом может идти другая игра (NHL 13 другого агента),
        # которая забирает фокус, — без своего окна впереди SendInput ушёл бы в чужое окно. Не вышло за
        # 3 попытки — клавиша не отправляется (NO_FOCUS).
        $ok = $false
        for ($try = 0; $try -lt 3 -and -not $ok; $try++) {
            $ok = ([GT]::GetForegroundWindow() -eq $h) -or (Focus-Game $h)
            if (-not $ok) { Start-Sleep -Milliseconds 700 }
        }
        if (-not $ok -or [GT]::GetForegroundWindow() -ne $h) { Write-Output "NO_FOCUS: клавиша $k не отправлена"; return $false }
        $mods = @(); $main = $k
        if ($k -like 'Shift+*') { $mods = @(0x10); $main = $k.Substring(6) }
        $code = Key-Code $main
        foreach ($m in $mods) { Send-Vk $m $false }
        Send-Vk $code $false
        Start-Sleep -Milliseconds $HoldMs
        Send-Vk $code $true
        foreach ($m in $mods) { Send-Vk $m $true }
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
        Write-Output ("pid {0} hwnd {1} client {2}x{3} title '{4}' fg {5}" -f $p.Id, $p.MainWindowHandle, $r.Right, $r.Bottom, $p.MainWindowTitle, ([GT]::GetForegroundWindow() -eq $p.MainWindowHandle))
    }
    'start' {
        if (Get-Process -Name $Proc -ErrorAction SilentlyContinue) { Write-Output 'ALREADY_RUNNING'; exit 2 }
        $args2 = @("--log_file=$Log", '--mnk_mode=true') + $Extra
        $p = Start-Process -FilePath $Exe -ArgumentList $args2 -WorkingDirectory (Split-Path -Parent $Exe) -PassThru
        Write-Output "STARTED pid $($p.Id): $Exe $($args2 -join ' ')"
    }
    'shot' {
        $r = Do-Shot $Out
        if (-not ($r -contains $true)) { $r | Where-Object { $_ -isnot [bool] }; exit 1 }
        $r | Where-Object { $_ -isnot [bool] }
    }
    'seq' {
        # Шаги через «;»: wait:СЕКУНДЫ, shot:ФАЙЛ.png, key:КЛАВИШИ (как у -Keys). Без окна — выход 1.
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
