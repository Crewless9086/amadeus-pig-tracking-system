$ErrorActionPreference = "Stop"
$repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$pythonwCandidates = @(
    (Join-Path $repo "venv\Scripts\pythonw.exe"),
    (Join-Path (Split-Path (Split-Path $repo -Parent) -Parent) "venv\Scripts\pythonw.exe")
)
$pythonw = $pythonwCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
$script = Join-Path $repo "scripts\charlie_executive_watchdog.py"
$taskName = "CHARLIE Always-On Executive"

if (-not $pythonw) { throw "Python windowless executable not found." }
$action = New-ScheduledTaskAction -Execute $pythonw -Argument ('"{0}" --json' -f $script) -WorkingDirectory $repo
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddSeconds(20) -RepetitionInterval (New-TimeSpan -Minutes 1)
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 5)
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Description "Always-on CHARLIE executive supervision across CORE and all registered domain agents." -Force | Out-Null
Write-Host "Installed $taskName (windowless, every minute and after missed starts)."
