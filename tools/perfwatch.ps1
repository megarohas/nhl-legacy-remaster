# perfwatch.ps1 — пассивный замер нагрузки на GPU и CPU у nhl13.exe, пока идёт игра.
#
# Игру не трогает: только читает счётчики Windows (GPU Engine — как «Диспетчер задач»),
# времена потоков процесса (с именами потоков — SetThreadDescription в SDK: «GPU Commands»,
# «GPU VSync», «Vulkan Pipelines», XThread… игры) и nvidia-smi. Ничего не устанавливает,
# настроек не меняет. Нагрузка от самого скрипта — доли процента одного ядра.
#
# Запуск — до игры или во время неё; по умолчанию пишет раз в секунду, пока игра не закроется:
#   powershell -ExecutionPolicy Bypass -File S:\Claude\megarohas_nhl13\tools\perfwatch.ps1 -Label vk-fsi
# Ограничить по времени: -Seconds 120. Пересчитать сводку по готовой папке: -Summarize <папка>.
# Сравнить прогоны (A/B) таблицей: -Compare <папка1>,<папка2>,...; -MatchOnly — только секунды,
# где 3D-движок у игры ≥ 30 % (матч, без меню и загрузок).
# Итог — в game\work\perf\<время>-<метка>\: summary.txt (сводка и вывод), samples.csv (по
# секундам: nvidia-smi + 3D у процесса + CPU), threads.csv (потоки ≥ 1 % ядра), gpu-smi.csv
# (сырые строки nvidia-smi). CSV пишутся сразу, поэтому закрыть окно скрипта можно в любой
# момент — сводку потом соберёт -Summarize.
#
# Как читать:
#  * «загрузка» nvidia-smi — доля времени, когда GPU хоть что-то считал. На сброшенных частотах
#    тот же объём работы даёт больший процент; «эффективная нагрузка» = загрузка × частота ядра /
#    макс. частота (2100 МГц у RTX 3060) — грубая оценка доли полной мощности карты;
#  * поток с ~100 % одного ядра — упор в процессор в этом потоке (или он крутится в ожидании —
#    «GPU Commands» в WAIT_REG_MEM; тогда смотреть на GPU);
#  * эффективная нагрузка ≥ ~85 % — упор в видеокарту;
#  * всё далеко от упора — кадр ограничен синхронизацией (гостевой vblank 60 Гц).

param(
    [int]$Seconds = 0,
    [string]$Label = "",
    [string]$ProcessName = "nhl13",
    [int]$WaitStart = 3600,
    [int]$TopThreads = 10,
    [string]$OutRoot = "",
    [string]$Summarize = "",
    [string[]]$Compare = @(),
    [switch]$MatchOnly
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 2
$inv = [Globalization.CultureInfo]::InvariantCulture

function Write-Utf8([string]$path, [string[]]$lines) {
    [System.IO.File]::WriteAllLines($path, $lines, (New-Object System.Text.UTF8Encoding $true))
}

function Add-Line([string]$path, [string]$line) {
    [System.IO.File]::AppendAllText($path, $line + "`r`n", (New-Object System.Text.UTF8Encoding $false))
}

function Get-Pct([double[]]$values, [double]$p) {
    if (-not $values -or $values.Count -eq 0) { return 0.0 }
    $sorted = [double[]]($values | Sort-Object)
    $idx = [math]::Min($sorted.Count - 1, [math]::Max(0, [int][math]::Ceiling($p / 100.0 * $sorted.Count) - 1))
    return $sorted[$idx]
}

function Get-Avg([double[]]$values) {
    if (-not $values -or $values.Count -eq 0) { return 0.0 }
    return [double](($values | Measure-Object -Average).Average)
}

function F([double]$v, [int]$digits = 1) {
    return $v.ToString("F$digits", $inv)
}

function Read-Double([string]$s) {
    $v = 0.0
    if ([double]::TryParse($s.Trim(), [Globalization.NumberStyles]::Float, $inv, [ref]$v)) { return $v }
    return [double]::NaN
}

# Причины сброса частот (nvidia-smi clocks_event_reasons.active, битовая маска)
$reasonBits = @{
    0x1 = "простой GPU (GpuIdle)"; 0x2 = "частоты приложения"; 0x4 = "лимит мощности (SW Power Cap)";
    0x8 = "аппаратное замедление"; 0x10 = "Sync Boost"; 0x20 = "перегрев (SW)"; 0x40 = "перегрев (HW)";
    0x80 = "Power Brake"; 0x100 = "частота дисплея"
}

# --- статистика по папке с CSV
function Get-Stats([string]$dir) {
    $samplesCsv = Join-Path $dir "samples.csv"
    $threadsCsv = Join-Path $dir "threads.csv"
    $metaFile = Join-Path $dir "meta.txt"
    if (-not (Test-Path $samplesCsv)) { throw "Нет $samplesCsv" }
    $meta = @{}
    if (Test-Path $metaFile) {
        foreach ($l in Get-Content $metaFile -Encoding UTF8) { if ($l -match "^(\w+)=(.*)$") { $meta[$Matches[1]] = $Matches[2] } }
    }
    $st = @{ Dir = $dir; Meta = $meta }
    $st.MaxClk = if ($meta.ContainsKey("max_clock_mhz")) { Read-Double $meta["max_clock_mhz"] } else { 2100.0 }
    $st.PowLimit = if ($meta.ContainsKey("power_limit_w")) { Read-Double $meta["power_limit_w"] } else { 170.0 }
    $st.Cores = if ($meta.ContainsKey("cores")) { [int]$meta["cores"] } else { [Environment]::ProcessorCount }
    $st.Label = if ($meta.ContainsKey("label") -and $meta["label"]) { $meta["label"] } else { Split-Path -Leaf $dir }

    $rows = @(Import-Csv $samplesCsv -Encoding UTF8)
    if ($MatchOnly) {
        $rows = @($rows | Where-Object { (Read-Double ([string]$_.proc_3d)) -ge 30 })
        $st.Label = "$($st.Label) (матч)"
    }
    $secSet = @{}
    foreach ($r in $rows) { $secSet[[string]$r.sec] = $true }
    $st.Rows = $rows
    $cols = @{ util = "smi_util"; clk = "smi_clk_gr"; mclk = "smi_clk_mem"; pow = "smi_power"; eff = "eff_load"; p3d = "proc_3d"; pcopy = "proc_copy"; cpu = "cpu_cores" }
    foreach ($k in $cols.Keys) { $st[$k] = New-Object System.Collections.Generic.List[double] }
    $st.PStates = @{}
    $st.Reasons = @{}
    $st.BusyEff = New-Object System.Collections.Generic.List[double]
    $st.BusyClk = New-Object System.Collections.Generic.List[double]
    foreach ($r in $rows) {
        foreach ($k in $cols.Keys) {
            $v = Read-Double ([string]$r.($cols[$k]))
            if (-not [double]::IsNaN($v)) { $st[$k].Add($v) }
        }
        if ($r.smi_pstate) { $st.PStates[$r.smi_pstate] = 1 + $(if ($st.PStates.ContainsKey($r.smi_pstate)) { $st.PStates[$r.smi_pstate] } else { 0 }) }
        $mask = 0
        if ($r.smi_reasons -and $r.smi_reasons -match "^0x([0-9A-Fa-f]+)$") { $mask = [Convert]::ToInt64($Matches[1], 16) }
        foreach ($bit in $reasonBits.Keys) {
            if ($mask -band $bit) { $st.Reasons[$bit] = 1 + $(if ($st.Reasons.ContainsKey($bit)) { $st.Reasons[$bit] } else { 0 }) }
        }
        $u = Read-Double ([string]$r.smi_util)
        if (-not [double]::IsNaN($u) -and $u -ge 50) {
            $e = Read-Double ([string]$r.eff_load)
            if (-not [double]::IsNaN($e)) { $st.BusyEff.Add($e) }
            $c = Read-Double ([string]$r.smi_clk_gr)
            if (-not [double]::IsNaN($c)) { $st.BusyClk.Add($c) }
        }
    }
    $st.N = $rows.Count
    $st.Threads = @()
    if (Test-Path $threadsCsv) {
        $tr = @(Import-Csv $threadsCsv -Encoding UTF8)
        $by = @{}
        foreach ($t in $tr) {
            if ($MatchOnly -and -not $secSet.ContainsKey([string]$t.sec)) { continue }
            $key = "$($t.tid)|$($t.name)"
            if (-not $by.ContainsKey($key)) { $by[$key] = New-Object System.Collections.Generic.List[double] }
            $by[$key].Add((Read-Double ([string]$t.pct_core)))
        }
        $n = [math]::Max(1, $st.N)
        $st.Threads = @($by.Keys | ForEach-Object {
            $vals = $by[$_].ToArray()
            $parts = $_.Split("|", 2)
            # среднее по всем секундам замера (секунды ниже 1 % в threads.csv не пишутся — считаем их нулём)
            $all = [double[]]($vals + @(0.0) * [math]::Max(0, $n - $vals.Count))
            [pscustomobject]@{ Tid = $parts[0]; Name = $parts[1]; Avg = (($vals | Measure-Object -Sum).Sum / $n); P95 = (Get-Pct $vals 95); P5 = (Get-Pct $all 5) }
        } | Sort-Object Avg -Descending)
    }
    return $st
}

function Write-Summary([string]$dir) {
    $st = Get-Stats $dir
    $meta = $st.Meta
    $n = $st.N
    $out = New-Object System.Collections.Generic.List[string]
    $out.Add("perfwatch — $($st.Label) — $($meta['process']) pid $($meta['pid']), старт $($meta['start']), секунд с данными: $n")
    $out.Add("")
    $out.Add("Видеокарта (nvidia-smi, вся карта — вместе с NVIDIA Broadcast, браузером и т. п.):")
    $out.Add("  загрузка: среднее $(F (Get-Avg $st.util.ToArray())) %, медиана $(F (Get-Pct $st.util.ToArray() 50)) %, p95 $(F (Get-Pct $st.util.ToArray() 95)) %")
    $out.Add("  частота ядра: среднее $(F (Get-Avg $st.clk.ToArray()) 0) МГц, медиана $(F (Get-Pct $st.clk.ToArray() 50) 0) МГц (макс. карты $(F $st.MaxClk 0)); памяти: медиана $(F (Get-Pct $st.mclk.ToArray() 50) 0) МГц")
    $out.Add("  мощность: среднее $(F (Get-Avg $st.pow.ToArray())) Вт, p95 $(F (Get-Pct $st.pow.ToArray() 95)) Вт из $(F $st.PowLimit 0) Вт")
    $out.Add("  ЭФФЕКТИВНАЯ нагрузка (загрузка × частота / макс.): среднее $(F (Get-Avg $st.eff.ToArray())) %, p95 $(F (Get-Pct $st.eff.ToArray() 95)) %")
    if ($st.BusyEff.Count -gt 0) {
        $out.Add("  секунд с загрузкой ≥ 50 %: $($st.BusyEff.Count) из $n; в них эффективная нагрузка — медиана $(F (Get-Pct $st.BusyEff.ToArray() 50)) %, частота — медиана $(F (Get-Pct $st.BusyClk.ToArray() 50) 0) МГц")
    }
    $out.Add("  P-state: " + (($st.PStates.Keys | Sort-Object | ForEach-Object { "$_ — $($st.PStates[$_]) с" }) -join ", "))
    if ($st.Reasons.Count -gt 0) {
        $out.Add("  причины сброса частот: " + (($st.Reasons.Keys | Sort-Object | ForEach-Object { "$($reasonBits[$_]) — $($st.Reasons[$_]) с" }) -join "; "))
    }
    $out.Add("")
    $out.Add("Процесс игры:")
    $out.Add("  3D-движок GPU (Windows, только эта игра): среднее $(F (Get-Avg $st.p3d.ToArray())) %, медиана $(F (Get-Pct $st.p3d.ToArray() 50)) %, p95 $(F (Get-Pct $st.p3d.ToArray() 95)) %; Copy: среднее $(F (Get-Avg $st.pcopy.ToArray())) %")
    $out.Add("  CPU: среднее $(F (Get-Avg $st.cpu.ToArray()) 2) ядра из $($st.Cores), p95 $(F (Get-Pct $st.cpu.ToArray() 95) 2)")
    $out.Add("  потоки (% одного ядра: среднее за замер / p95 по секундам, где поток работал):")
    foreach ($r in ($st.Threads | Select-Object -First $TopThreads)) {
        $nm = if ($r.Name) { $r.Name } else { "(без имени)" }
        $out.Add("    $((F $r.Avg).PadLeft(6)) % / $((F $r.P95).PadLeft(6)) %   tid $($r.Tid.PadRight(6)) $nm")
    }
    # Ход по 30-секундным отрезкам — по нему видно меню, загрузку и матч
    $out.Add("")
    $out.Add("По 30 с (начало отрезка, с: загрузка GPU медиана % @ частота МГц, мощность Вт, 3D игры %, CPU ядра, самый занятый поток):")
    $win = 30
    $groups = @{}
    foreach ($r in $st.Rows) {
        $sec = Read-Double ([string]$r.sec)
        if ([double]::IsNaN($sec)) { continue }
        $g = [int][math]::Floor($sec / $win)
        if (-not $groups.ContainsKey($g)) { $groups[$g] = New-Object System.Collections.Generic.List[object] }
        $groups[$g].Add($r)
    }
    foreach ($g in ($groups.Keys | Sort-Object)) {
        $rs = $groups[$g]
        $gu = [double[]]@($rs | ForEach-Object { Read-Double ([string]$_.smi_util) } | Where-Object { -not [double]::IsNaN($_) })
        $gc = [double[]]@($rs | ForEach-Object { Read-Double ([string]$_.smi_clk_gr) } | Where-Object { -not [double]::IsNaN($_) })
        $gw = [double[]]@($rs | ForEach-Object { Read-Double ([string]$_.smi_power) } | Where-Object { -not [double]::IsNaN($_) })
        $g3 = [double[]]@($rs | ForEach-Object { Read-Double ([string]$_.proc_3d) } | Where-Object { -not [double]::IsNaN($_) })
        $gk = [double[]]@($rs | ForEach-Object { Read-Double ([string]$_.cpu_cores) } | Where-Object { -not [double]::IsNaN($_) })
        $topNames = @{}
        foreach ($r in $rs) {
            if ($r.top_threads -and $r.top_threads -match "^([^=]+)=") {
                $k = $Matches[1].Trim()
                $topNames[$k] = 1 + $(if ($topNames.ContainsKey($k)) { $topNames[$k] } else { 0 })
            }
        }
        $topThread = $topNames.GetEnumerator() | Sort-Object Value -Descending | Select-Object -First 1
        $tt = if ($topThread) { $topThread.Key } else { "" }
        $out.Add(("  {0,5}: {1,4} % @ {2,4}, {3,4} Вт, 3D {4,5} %, CPU {5,4}, {6}" -f ($g * $win), (F (Get-Pct $gu 50) 0), (F (Get-Pct $gc 50) 0), (F (Get-Avg $gw) 0), (F (Get-Avg $g3)), (F (Get-Avg $gk) 2), $tt))
    }
    $out.Add("")
    $top = $st.Threads | Select-Object -First 1
    $topName = if ($top) { $top.Name } else { "" }
    $topAvg = if ($top) { $top.Avg } else { 0.0 }
    $effP95 = Get-Pct $st.eff.ToArray() 95
    $utilMed = Get-Pct $st.util.ToArray() 50
    $clkMed = Get-Pct $st.clk.ToArray() 50
    $topP5 = if ($top) { $top.P5 } else { 0.0 }
    if ($topAvg -ge 85 -and $topP5 -ge 85) {
        $out.Add("Вывод: поток «$topName» занят ~$(F $topAvg 0) % ядра ВСЁ время (даже в самые лёгкие секунды — $(F $topP5 0) %, включая меню) — похоже на активное ожидание (спин), а не на упор в работу; где именно крутится — tools/stackpeek.py. Узкое место ищите по GPU и остальным потокам.")
    } elseif ($topAvg -ge 85) {
        $out.Add("Вывод: упор в процессор — поток «$topName» ~$(F $topAvg 0) % ядра. Если это «GPU Commands», он может и крутиться в ожидании GPU — сверить с загрузкой видеокарты.")
    } elseif ($effP95 -ge 85) {
        $out.Add("Вывод: упор в видеокарту (эффективная нагрузка p95 $(F $effP95 0) %).")
    } elseif ($utilMed -ge 50 -and $clkMed -lt 0.8 * $st.MaxClk) {
        $out.Add("Вывод: проценты загрузки высокие ($(F $utilMed 0) % медиана), но на пониженной частоте ($(F $clkMed 0) МГц) — реальной работы меньше: эффективная нагрузка p95 $(F $effP95 0) %. Драйвер держит частоту ровно под 60 к/с.")
    } else {
        $out.Add("Вывод: ни GPU (эффективная p95 $(F $effP95 0) %), ни один поток CPU (макс. ~$(F $topAvg 0) % ядра) не в упоре — кадр ограничен синхронизацией (гостевой vblank 60 Гц).")
    }
    Write-Utf8 (Join-Path $dir "summary.txt") $out.ToArray()
    $out | ForEach-Object { Write-Host $_ }
}

# --- сравнение нескольких прогонов (A/B) одной таблицей
function Write-Compare([string[]]$dirs) {
    $lines = New-Object System.Collections.Generic.List[string]
    $lines.Add("вариант | сек | GPU медиана/p95 % | частота МГц | мощность Вт | эфф. p95 % | 3D игры медиана/p95 % | CPU ядра | самый занятый поток")
    $lines.Add("---|---|---|---|---|---|---|---|---")
    foreach ($d in $dirs) {
        $st = Get-Stats (Resolve-Path $d).Path
        $top = $st.Threads | Select-Object -First 1
        $tt = if ($top) { "$($top.Name) $(F $top.Avg 0) %" } else { "" }
        $lines.Add("$($st.Label) | $($st.N) | $(F (Get-Pct $st.util.ToArray() 50) 0)/$(F (Get-Pct $st.util.ToArray() 95) 0) | $(F (Get-Pct $st.clk.ToArray() 50) 0) | $(F (Get-Avg $st.pow.ToArray()) 0) | $(F (Get-Pct $st.eff.ToArray() 95) 0) | $(F (Get-Pct $st.p3d.ToArray() 50) 0)/$(F (Get-Pct $st.p3d.ToArray() 95) 0) | $(F (Get-Avg $st.cpu.ToArray()) 2) | $tt")
    }
    $lines | ForEach-Object { Write-Host $_ }
}

if ($Compare.Count -gt 0) {
    Write-Compare $Compare
    return
}

if ($Summarize) {
    Write-Summary (Resolve-Path $Summarize).Path
    return
}

if (-not $OutRoot) {
    $OutRoot = Join-Path (Split-Path -Parent $PSScriptRoot) "game\work\perf"
}

Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
public static class NhlPerfThreads {
    [DllImport("kernel32.dll", SetLastError = true)]
    static extern IntPtr OpenThread(uint access, bool inherit, uint id);
    [DllImport("kernel32.dll")]
    static extern bool CloseHandle(IntPtr h);
    [DllImport("kernel32.dll")]
    static extern int GetThreadDescription(IntPtr h, out IntPtr desc);
    [DllImport("kernel32.dll")]
    static extern IntPtr LocalFree(IntPtr p);
    public static string Name(int id) {
        IntPtr h = OpenThread(0x0800, false, (uint)id);  // THREAD_QUERY_LIMITED_INFORMATION
        if (h == IntPtr.Zero) return "";
        try {
            IntPtr p;
            if (GetThreadDescription(h, out p) >= 0 && p != IntPtr.Zero) {
                string s = Marshal.PtrToStringUni(p);
                LocalFree(p);
                return s ?? "";
            }
            return "";
        } finally {
            CloseHandle(h);
        }
    }
}
"@

# --- ждём игру
$proc = Get-Process -Name $ProcessName -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $proc) {
    Write-Host "perfwatch: жду запуска $ProcessName.exe (до $WaitStart с)…"
    $deadline = (Get-Date).AddSeconds($WaitStart)
    while (-not $proc) {
        if ((Get-Date) -gt $deadline) { throw "Процесс $ProcessName не найден за $WaitStart с" }
        Start-Sleep -Seconds 2
        $proc = Get-Process -Name $ProcessName -ErrorAction SilentlyContinue | Select-Object -First 1
    }
}
$procId = $proc.Id
$cores = [Environment]::ProcessorCount
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$outDir = Join-Path $OutRoot $(if ($Label) { "$stamp-$Label" } else { $stamp })
New-Item -ItemType Directory -Force -Path $outDir | Out-Null
$samplesCsv = Join-Path $outDir "samples.csv"
$threadsCsv = Join-Path $outDir "threads.csv"
$smiCsv = Join-Path $outDir "gpu-smi.csv"

# --- nvidia-smi: раз в секунду разовым запросом (в режиме -l/-f он копит вывод в буфере до выхода)
$maxClk = 2100.0; $powLimit = 170.0
$smiExe = Get-Command nvidia-smi -ErrorAction SilentlyContinue
$smiQuery = "--query-gpu=timestamp,utilization.gpu,utilization.memory,clocks.gr,clocks.mem,power.draw,pstate,memory.used,temperature.gpu,clocks_event_reasons.active"
if ($smiExe) {
    try {
        $q = (@(& $smiExe.Source --query-gpu=clocks.max.gr,power.limit --format=csv,noheader,nounits)[0]).Split(",")
        $maxClk = Read-Double $q[0]; $powLimit = Read-Double $q[1]
    } catch { }
    Add-Line $smiCsv "timestamp,util_gpu,util_mem,clk_gr,clk_mem,power_w,pstate,mem_used_mib,temp_c,reasons"
} else {
    Write-Host "perfwatch: nvidia-smi не найден — только счётчики Windows"
}
Write-Utf8 (Join-Path $outDir "meta.txt") @(
    "label=$Label", "process=$ProcessName", "pid=$procId", "start=$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')",
    "cores=$cores", "max_clock_mhz=$(F $maxClk 0)", "power_limit_w=$(F $powLimit 0)")
Add-Line $samplesCsv "time,sec,smi_util,smi_clk_gr,smi_clk_mem,smi_power,smi_pstate,smi_reasons,eff_load,proc_3d,proc_copy,proc_other,cpu_cores,top_threads"
Add-Line $threadsCsv "time,sec,tid,name,pct_core"
Write-Host "perfwatch: $ProcessName pid $procId -> $outDir (Ctrl+C или закрыть окно — данные уже на диске)"

function Read-Threads($p) {
    $snap = @{}
    $p.Refresh()
    foreach ($t in $p.Threads) {
        try { $snap[[int]$t.Id] = $t.TotalProcessorTime.TotalMilliseconds } catch { }
    }
    return $snap
}

$gpuPath = "\GPU Engine(pid_$($procId)_*)\Utilization Percentage"
$names = @{}
$prevCpu = Read-Threads $proc
$sw = [Diagnostics.Stopwatch]::StartNew()
$start = Get-Date
$elapsed = 0.0
try {
    while ($Seconds -le 0 -or $elapsed -lt $Seconds) {
        if ($proc.HasExited) { Write-Host "perfwatch: игра закрыта"; break }
        # Get-Counter сам ждёт 1 с между двумя замерами — это и есть пауза цикла
        $engines = @{}
        try {
            $gc = Get-Counter -Counter $gpuPath -SampleInterval 1 -MaxSamples 1 -ErrorAction Stop
            foreach ($s in $gc.CounterSamples) {
                $et = if ($s.InstanceName -match "engtype_(.+)$") { $Matches[1] } else { "other" }
                if (-not $engines.ContainsKey($et)) { $engines[$et] = 0.0 }
                $engines[$et] += $s.CookedValue
            }
        } catch {
            Start-Sleep -Milliseconds 1000
        }
        $dt = $sw.Elapsed.TotalMilliseconds
        $sw.Restart()
        $elapsed = ((Get-Date) - $start).TotalSeconds
        if ($proc.HasExited) { Write-Host "perfwatch: игра закрыта"; break }
        $cur = Read-Threads $proc
        $now = Get-Date -Format "HH:mm:ss"
        $procMs = 0.0
        $tops = New-Object System.Collections.Generic.List[object]
        foreach ($tid in $cur.Keys) {
            $before = if ($prevCpu.ContainsKey($tid)) { $prevCpu[$tid] } else { $cur[$tid] }
            $d = [math]::Max(0.0, $cur[$tid] - $before)
            $procMs += $d
            $pct = if ($dt -gt 0) { 100.0 * $d / $dt } else { 0.0 }
            if (-not $names.ContainsKey($tid) -or -not $names[$tid]) { $names[$tid] = [NhlPerfThreads]::Name($tid) }
            if ($pct -ge 1.0) {
                $nm = ($names[$tid] -replace '[,"]', ' ')
                Add-Line $threadsCsv ("{0},{1},{2},{3},{4}" -f $now, (F $elapsed), $tid, $nm, (F $pct))
                $tops.Add([pscustomobject]@{ Name = $(if ($nm) { $nm } else { "tid$tid" }); Pct = $pct })
            }
        }
        $prevCpu = $cur
        $e3d = 0.0; $ecopy = 0.0; $eother = 0.0
        foreach ($k in $engines.Keys) {
            if ($k -ieq "3D") { $e3d += $engines[$k] } elseif ($k -ieq "Copy") { $ecopy += $engines[$k] } else { $eother += $engines[$k] }
        }
        $coresUsed = if ($dt -gt 0) { $procMs / $dt } else { 0.0 }
        # nvidia-smi: текущее состояние карты
        $u = [double]::NaN; $c = [double]::NaN; $m = [double]::NaN; $w = [double]::NaN; $ps = ""; $rs = ""
        if ($smiExe) {
            try {
                $line = @(& $smiExe.Source $smiQuery --format=csv,noheader,nounits)[0]
                Add-Line $smiCsv $line
                $f = $line.Split(",") | ForEach-Object { $_.Trim() }
                if ($f.Count -ge 10) { $u = Read-Double $f[1]; $c = Read-Double $f[3]; $m = Read-Double $f[4]; $w = Read-Double $f[5]; $ps = $f[6]; $rs = $f[9] }
            } catch { }
        }
        $effLoad = if (-not [double]::IsNaN($u) -and -not [double]::IsNaN($c) -and $maxClk -gt 0) { $u * $c / $maxClk } else { [double]::NaN }
        $topStr = (($tops | Sort-Object Pct -Descending | Select-Object -First 4 | ForEach-Object { "$($_.Name)=$(F $_.Pct 0)%" }) -join " | ")
        Add-Line $samplesCsv ("{0},{1},{2},{3},{4},{5},{6},{7},{8},{9},{10},{11},{12},`"{13}`"" -f $now, (F $elapsed), (F $u 0), (F $c 0), (F $m 0), (F $w), $ps, $rs, (F $effLoad), (F $e3d), (F $ecopy), (F $eother), (F $coresUsed 2), $topStr)
        Write-Host ("{0,6} с  GPU {1,3} % @ {2,4} МГц {3,5} Вт  эфф. {4,5} %  3D игры {5,5} %  CPU {6,4} ядра  {7}" -f (F $elapsed 0), (F $u 0), (F $c 0), (F $w 0), (F $effLoad), (F $e3d), (F $coresUsed 2), $topStr)
    }
} finally {
    try { Write-Summary $outDir } catch { Write-Host "perfwatch: сводка не собрана: $($_.Exception.Message)" }
}
exit 0
