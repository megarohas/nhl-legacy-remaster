# Does the custom rexglue.exe generate the same code as the one that produced
# port-ffx\generated\default (the nightly's)? Runs a full codegen of a scratch copy of
# the manifest + includes (game paths made absolute, reference partition seeded) and
# compares every generated file by SHA-256. Takes ~10 minutes; run it at low priority
# (codegen_check.cmd does).
param(
    [Parameter(Mandatory = $true)][string]$Rexglue,
    [Parameter(Mandatory = $true)][string]$PortDir,
    [Parameter(Mandatory = $true)][string]$WorkDir
)
$ErrorActionPreference = "Stop"

if (Test-Path $WorkDir) { Remove-Item -Recurse -Force $WorkDir }
New-Item -ItemType Directory -Force $WorkDir | Out-Null

$manifest = Get-Content -Raw -Encoding UTF8 (Join-Path $PortDir "nhl13_manifest.toml")
$gameAbs = (Resolve-Path (Join-Path $PortDir "..\game")).Path -replace '\\', '/'
$manifest = $manifest -replace '"\.\./game/', ('"' + $gameAbs + '/')
[System.IO.File]::WriteAllText((Join-Path $WorkDir "nhl13_manifest.toml"), $manifest,
                               (New-Object System.Text.UTF8Encoding($false)))
foreach ($inc in [regex]::Matches($manifest, '"([^"]+\.toml)"')) {
    Copy-Item (Join-Path $PortDir $inc.Groups[1].Value) $WorkDir
}
# The function -> file assignment is sticky (codegen_writer.cpp: OutputPartition::Load of the
# previous codegen.partition.json). Without the reference partition a fresh run spreads the
# same functions over the files differently, and every file differs.
$genDir = Join-Path $WorkDir "generated\default"
New-Item -ItemType Directory -Force $genDir | Out-Null
Copy-Item (Join-Path $PortDir "generated\default\codegen.partition.json") $genDir

$sw = [Diagnostics.Stopwatch]::StartNew()
$ErrorActionPreference = "Continue"
& $Rexglue codegen (Join-Path $WorkDir "nhl13_manifest.toml")
$rc = $LASTEXITCODE
$ErrorActionPreference = "Stop"
$sw.Stop()
Write-Host ("[cg] codegen exit {0}, {1:N1} min" -f $rc, $sw.Elapsed.TotalMinutes)
if ($rc -ne 0) { exit $rc }

# Stamps and the depfile hold input paths / fingerprints, not generated code.
$skip = @("codegen.d", "codegen.stamp", "codegen.build.stamp")
$ref = Join-Path $PortDir "generated\default"
$new = Join-Path $WorkDir "generated\default"
$refFiles = Get-ChildItem -File $ref | Where-Object { $skip -notcontains $_.Name }
$newFiles = Get-ChildItem -File $new | Where-Object { $skip -notcontains $_.Name }
$onlyRef = @(Compare-Object ($refFiles.Name) ($newFiles.Name) | Where-Object SideIndicator -eq "<=")
$onlyNew = @(Compare-Object ($refFiles.Name) ($newFiles.Name) | Where-Object SideIndicator -eq "=>")
$diff = @()
foreach ($f in $refFiles) {
    $n = Join-Path $new $f.Name
    if (-not (Test-Path $n)) { continue }
    if ((Get-FileHash -Algorithm SHA256 $f.FullName).Hash -ne (Get-FileHash -Algorithm SHA256 $n).Hash) {
        $diff += $f.Name
    }
}
Write-Host ("[cg] compared {0} files: {1} differ, {2} only in reference, {3} only in new" -f `
            $refFiles.Count, $diff.Count, $onlyRef.Count, $onlyNew.Count)
$diff | Select-Object -First 20 | ForEach-Object { Write-Host "  differs: $_" }
$onlyRef | Select-Object -First 10 | ForEach-Object { Write-Host "  only reference: $($_.InputObject)" }
$onlyNew | Select-Object -First 10 | ForEach-Object { Write-Host "  only new: $($_.InputObject)" }
if ($diff.Count -or $onlyRef.Count -or $onlyNew.Count) { exit 3 }
Write-Host "[cg] identical"
exit 0
