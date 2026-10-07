# Run one Hydro One outage archive snapshot (for Task Scheduler / manual use).
# Example: powershell -ExecutionPolicy Bypass -File TMP\scripts\run_hydro_one_outage_archive.ps1

$ErrorActionPreference = "Stop"

# TMP/scripts -> repo root
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path

Set-Location $ProjectRoot

$LogDir = Join-Path $ProjectRoot "TMP\temp\hydro_one_outages\logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$Stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$LogFile = Join-Path $LogDir "fetch_$Stamp.log"

$Python = Get-Command python -ErrorAction SilentlyContinue
if (-not $Python) {
    $Python = Get-Command py -ErrorAction SilentlyContinue
}
if (-not $Python) {
    throw "python/py not found on PATH"
}

$Args = @(
    "TMP\scripts\fetch_hydro_one_outages.py",
    "--archive"
)

# Optional bbox via env: HYDRO_ONE_BBOX="minLon minLat maxLon maxLat"
if ($env:HYDRO_ONE_BBOX) {
    $bboxParts = $env:HYDRO_ONE_BBOX -split "\s+"
    if ($bboxParts.Count -eq 4) {
        $Args += @("--bbox") + $bboxParts
    }
}

Write-Host "Running: $($Python.Source) $($Args -join ' ')"
& $Python.Source @Args 2>&1 | Tee-Object -FilePath $LogFile
$exit = $LASTEXITCODE
if ($exit -ne 0) {
    Write-Error "fetch_hydro_one_outages.py exited with code $exit (see $LogFile)"
    exit $exit
}
Write-Host "OK log=$LogFile"
exit 0
