# Register a Windows Scheduled Task to archive Hydro One outages every 15 minutes.
#
# Run once in an elevated PowerShell (or normal user for a per-user task):
#   powershell -ExecutionPolicy Bypass -File TMP\scripts\register_hydro_one_outage_task.ps1
#
# Optional:
#   -IntervalMinutes 15
#   -TaskName "HydroOneOutageArchive"
#   -Unregister   # remove the task

param(
    [string]$TaskName = "HydroOneOutageArchive",
    [int]$IntervalMinutes = 15,
    [switch]$Unregister
)

$ErrorActionPreference = "Stop"

if ($Unregister) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "Unregistered task '$TaskName' (if it existed)."
    exit 0
}

$ScriptDir = $PSScriptRoot
$Runner = Join-Path $ScriptDir "run_hydro_one_outage_archive.ps1"
if (-not (Test-Path $Runner)) {
    throw "Missing runner: $Runner"
}

$Action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$Runner`""

$Trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).Date.AddMinutes(1) `
    -RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes) `
    -RepetitionDuration ([TimeSpan]::MaxValue)

$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 20)

$Principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -Principal $Principal `
    -Force | Out-Null

Write-Host "Registered scheduled task '$TaskName' every $IntervalMinutes minutes."
Write-Host "Runner: $Runner"
Write-Host "Snapshots: <repo>\TMP\temp\hydro_one_outages\snapshots\"
Write-Host "To remove: powershell -ExecutionPolicy Bypass -File `"$PSCommandPath`" -Unregister"
