# Fetch the ReXGlue SDK sources for the custom build (docs/sdk-build.md). Idempotent.
#   1. clone github.com/rexglue/rexglue-sdk (branch development) into $SdkSrc, pin $Pin
#   2. shallow-init only the submodules a Windows D3D12 + Vulkan build needs
#   3. materialize git symlinks (Git for Windows checks them out as text files with
#      the target path; libmspack's cabextract/mspack/*.c/*.h are such links)
#   4. apply legacy-port\scripts\sdk-patches\*.patch (0001, 0002, ...) in name order (skipped if already applied)
# Read-only towards GitHub: nothing is pushed anywhere.
param(
    [Parameter(Mandatory = $true)][string]$SdkSrc,
    [string]$Pin = "bd833a2ab69d305f99ddf57418fc38ffec8af93d",
    [string]$PatchDir = ""
)
# Windows PowerShell 5.1 turns native stderr (git progress) into errors under "Stop";
# exit codes are checked explicitly instead.
$ErrorActionPreference = "Continue"
if (-not $PatchDir) { $PatchDir = Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) "sdk-patches" }

function Invoke-Git([string[]]$GitArgs) {
    & git.exe @GitArgs
    if ($LASTEXITCODE -ne 0) { throw "git $($GitArgs -join ' ') failed ($LASTEXITCODE)" }
}
function Test-Git([string[]]$GitArgs) {
    & git.exe @GitArgs *> $null
    return ($LASTEXITCODE -eq 0)
}

if (-not (Test-Path (Join-Path $SdkSrc ".git"))) {
    Write-Host "[sdk] cloning rexglue-sdk -> $SdkSrc"
    Invoke-Git @("clone", "--branch", "development", "--single-branch",
          "https://github.com/rexglue/rexglue-sdk.git", $SdkSrc)
}

$head = (& git -C $SdkSrc rev-parse HEAD).Trim()
if ($head -ne $Pin) {
    # A dirty tree means patches are applied; never reset it silently.
    $dirty = (& git -C $SdkSrc status --porcelain --ignore-submodules=all)
    if ($dirty) { throw "[sdk] $SdkSrc is at $head with local changes; expected $Pin. Reset it by hand." }
    if (-not (Test-Git @("-C", $SdkSrc, "cat-file", "-e", "$Pin^{commit}"))) {
        Invoke-Git @("-C", $SdkSrc, "fetch", "origin", "development")
    }
    Write-Host "[sdk] checkout $Pin"
    Invoke-Git @("-C", $SdkSrc, "checkout", "--detach", $Pin)
}

# The version string comes from "git describe --tags --match v*" (cmake/rex_version.cmake):
# with the v0.10.0 tag present it is 0.10.0.24-dev.gbd833a2, exactly as in the nightly.
if (-not (Test-Git @("-C", $SdkSrc, "rev-parse", "-q", "--verify", "refs/tags/v0.10.0"))) {
    Invoke-Git @("-C", $SdkSrc, "fetch", "--tags", "origin")
}

# moltenvk (macOS) and catch2 (tests) are not needed on Windows.
$subs = @("FFmpeg", "cli11", "fmt", "glslang", "imgui", "inja", "libmspack", "o1heap", "sdl3",
          "simde", "spdlog", "spirv-headers", "spirv-tools", "tomlplusplus", "tracy", "utfcpp",
          "vulkan-headers", "vulkan-loader", "vulkan-memory-allocator", "xxHash") |
        ForEach-Object { "thirdparty/$_" }
Write-Host "[sdk] submodules (depth 1)"
Invoke-Git (@("-C", $SdkSrc, "submodule", "update", "--init", "--depth", "1", "--jobs", "4", "--") + $subs)

foreach ($sub in @("thirdparty\libmspack", "thirdparty\o1heap")) {
    $subPath = Join-Path $SdkSrc $sub
    $links = & git -C $subPath ls-files -s | Where-Object { $_ -match '^120000' } |
             ForEach-Object { ($_ -split "`t")[1] }
    foreach ($rel in $links) {
        $file = Join-Path $subPath $rel
        if (-not (Test-Path $file -PathType Leaf)) { continue }
        $content = Get-Content -Raw $file
        if ($null -eq $content -or $content.Length -gt 200 -or $content.Trim() -match "[`r`n]") { continue }
        $target = Join-Path (Split-Path -Parent $file) $content.Trim()
        if (Test-Path $target -PathType Leaf) {
            Copy-Item -Force $target $file
            Write-Host "[sdk] materialized $sub\$rel"
        }
    }
}

$patches = @(Get-ChildItem -Path $PatchDir -Filter "*.patch" | Sort-Object Name)
foreach ($p in $patches) {
    if (Test-Git @("-C", $SdkSrc, "apply", "--check", $p.FullName)) {
        Invoke-Git @("-C", $SdkSrc, "apply", $p.FullName)
        Write-Host "[sdk] applied $($p.Name)"
    } elseif (Test-Git @("-C", $SdkSrc, "apply", "--check", "--reverse", $p.FullName)) {
        Write-Host "[sdk] already applied $($p.Name)"
    } else {
        throw "[sdk] $($p.Name) does not apply to $SdkSrc (tree changed?)"
    }
}
$desc = (& git -C $SdkSrc describe --tags --long --match "v[0-9]*.[0-9]*" --exclude "*-*")
Write-Host "[sdk] sources ready: $SdkSrc ($desc)"
exit 0
