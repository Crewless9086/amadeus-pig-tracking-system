param(
    [string]$TaskName = "CHARLIE Telegram Relay"
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $RepoRoot "venv\Scripts\pythonw.exe"
if (-not (Test-Path -LiteralPath $Python)) {
    throw "CHARLIE relay Python was not found at $Python"
}

$Watchdog = Join-Path $RepoRoot "scripts\charlie_telegram_relay_watchdog.py"
$Action = New-ScheduledTaskAction -Execute $Python -Argument ('"{0}" --json' -f $Watchdog) -WorkingDirectory $RepoRoot
$Trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 2)
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 1)
Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Description "Windowless watchdog for the owner-only CHARLIE Telegram relay. No shell execution is accepted from Telegram." -Force | Out-Null
Write-Output "Installed scheduled task: $TaskName"
Write-Output "The windowless watchdog checks the relay every two minutes."
