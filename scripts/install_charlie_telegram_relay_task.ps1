param(
    [string]$TaskName = "CHARLIE Telegram Relay"
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $RepoRoot "venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $Python)) {
    throw "CHARLIE relay Python was not found at $Python"
}

$Action = New-ScheduledTaskAction -Execute $Python -Argument "-m scripts.charlie_telegram_relay" -WorkingDirectory $RepoRoot
$Trigger = New-ScheduledTaskTrigger -AtLogOn
$Settings = New-ScheduledTaskSettingsSet -RestartCount 5 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit (New-TimeSpan -Days 7)
Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Description "Runs the owner-only CHARLIE Telegram relay. No shell execution is accepted from Telegram." -Force | Out-Null
Write-Output "Installed scheduled task: $TaskName"
Write-Output "Start it with: Start-ScheduledTask -TaskName '$TaskName'"
