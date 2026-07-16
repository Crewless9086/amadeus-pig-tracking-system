$ErrorActionPreference = "Stop"
$repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$pythonCandidates = @(
    (Join-Path $repo "venv\Scripts\python.exe"),
    (Join-Path (Split-Path (Split-Path $repo -Parent) -Parent) "venv\Scripts\python.exe")
)
$python = $pythonCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
$script = Join-Path $repo "scripts\charlie_runner_watchdog_task.ps1"
$taskName = "CHARLIE CORE Runner Watchdog"

if (-not $python) { throw "Python venv not found in the runner worktree or shared repository root." }
$powershell = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
$action = New-ScheduledTaskAction -Execute $powershell -Argument ('-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File "{0}"' -f $script) -WorkingDirectory $repo
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 2)
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 1)
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Description "Restarts the CHARLIE CORE supervisor when it stops." -Force | Out-Null
Write-Host "Installed $taskName (every 2 minutes)."
