$ErrorActionPreference = "Stop"
$repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$python = Join-Path $repo "venv\Scripts\python.exe"
$script = Join-Path $repo "scripts\charlie_runner_watchdog.py"
$taskName = "CHARLIE CORE Runner Watchdog"

if (-not (Test-Path $python)) { throw "Python venv not found: $python" }
$action = New-ScheduledTaskAction -Execute $python -Argument ('"{0}" --json' -f $script) -WorkingDirectory $repo
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 2)
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 1)
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Description "Restarts the CHARLIE CORE supervisor when it stops." -Force | Out-Null
Write-Host "Installed $taskName (every 2 minutes)."
