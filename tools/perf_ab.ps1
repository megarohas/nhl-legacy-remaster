# perf_ab.ps1 — запуск основной сборки (port-ffx) с одним вариантом настроек рендера и
# параллельный пассивный замер tools/perfwatch.ps1. nhl13.toml НЕ меняется: вариант задаётся
# аргументами командной строки (они сильнее nhl13.toml — docs/graphics-settings.md, «Источники и
# приоритет»), лог каждого варианта пишется в свой файл port/out/perf-<вариант>.log.
#
# Варианты (подробно — docs/performance.md, «План A/B»):
#   vk-fsi        как сейчас: Vulkan, EDRAM через fragment shader interlock (из nhl13.toml)
#   vk-fsi-noocc  то же, без запросов видимости на хосте (occlusion_query_enable=false)
#   vk-fsi-quick  как сейчас + сразу три «быстрые победы»: readback_resolve=none,
#                 occlusion_query_enable=false, readback_memexport=false (docs/performance.md, раздел 6)
#   vk-fbo        Vulkan, хостовые render target'ы (render_target_path_vulkan ≠ "fsi")
#   vk-fbo-noest  то же, но execute_unclipped_draw_vs_on_cpu=false (умолчание SDK) — проверка табло
#   vk-fbo-gamma8 то же, что vk-fbo, + gamma_render_target_as_unorm16=false — проверка табло
#   d3d12-rov     D3D12, EDRAM через ROV (прежний основной вариант)
#   d3d12-rtv     D3D12, хостовые render target'ы (как Xenia Canary по умолчанию на NVIDIA)
# Хостовым RT нужен execute_unclipped_draw_vs_on_cpu=true (умолчание Xenia; в SDK — false):
# иначе экранные квады считаются «на весь EDRAM» и порождают лишние копии между RT.
#
# Пример:  powershell -ExecutionPolicy Bypass -File S:\Claude\megarohas_nhl13\tools\perf_ab.ps1 vk-fbo
# Окно скрипта ждёт закрытия игры и печатает сводку (game\work\perf\<время>-<вариант>\summary.txt).
# Сравнить прогоны: perfwatch.ps1 -Compare <папка1>,<папка2>,...
#
# Первый запуск vk-fbo / d3d12-rtv компилирует свой кэш пайплайнов (4541099B.<путь>.*.xpso) —
# подвисания первые минуты; цифры брать со второго запуска или из середины матча.

param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidateSet("vk-fsi", "vk-fsi-noocc", "vk-fsi-quick", "vk-fbo", "vk-fbo-noest", "vk-fbo-gamma8", "d3d12-rov", "d3d12-rtv")]
    [string]$Variant,
    [string]$Exe = "S:\Claude\megarohas_nhl13\port-ffx\out\build\win-amd64-release\nhl13.exe",
    [string[]]$Extra = @()
)

$ErrorActionPreference = "Stop"
if (Get-Process -Name nhl13 -ErrorAction SilentlyContinue) {
    throw "nhl13.exe уже запущен — сначала закройте игру (две копии одновременно не запускать)"
}
if (-not (Test-Path $Exe)) { throw "Нет $Exe" }

$log = "S:/Claude/megarohas_nhl13/port/out/perf-$Variant.log"
$gameArgs = @("--log_file=$log")
switch ($Variant) {
    "vk-fsi" { }
    "vk-fsi-noocc" { $gameArgs += "--occlusion_query_enable=false" }
    "vk-fsi-quick" { $gameArgs += @("--readback_resolve=none", "--occlusion_query_enable=false", "--readback_memexport=false") }
    "vk-fbo" { $gameArgs += @("--render_target_path_vulkan=fbo", "--execute_unclipped_draw_vs_on_cpu=true") }
    "vk-fbo-noest" { $gameArgs += @("--render_target_path_vulkan=fbo", "--execute_unclipped_draw_vs_on_cpu=false") }
    "vk-fbo-gamma8" { $gameArgs += @("--render_target_path_vulkan=fbo", "--execute_unclipped_draw_vs_on_cpu=true", "--gamma_render_target_as_unorm16=false") }
    "d3d12-rov" { $gameArgs += @("--gpu_backend=d3d12", "--render_target_path_d3d12=rov") }
    "d3d12-rtv" { $gameArgs += @("--gpu_backend=d3d12", "--render_target_path_d3d12=rtv", "--execute_unclipped_draw_vs_on_cpu=true") }
}
$gameArgs += $Extra

Write-Host "perf_ab: $Variant -> $Exe $($gameArgs -join ' ')"
Start-Process -FilePath $Exe -ArgumentList $gameArgs -WorkingDirectory (Split-Path -Parent $Exe) | Out-Null
& (Join-Path $PSScriptRoot "perfwatch.ps1") -Label $Variant -WaitStart 60
