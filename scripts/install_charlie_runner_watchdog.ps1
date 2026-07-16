$ErrorActionPreference = "Stop"
$repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$pythonwCandidates = @(
    (Join-Path $repo "venv\Scripts\pythonw.exe"),
    (Join-Path (Split-Path (Split-Path $repo -Parent) -Parent) "venv\Scripts\pythonw.exe")
)
$pythonw = $pythonwCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
$script = Join-Path $repo "scripts\charlie_runner_watchdog.py"
$taskName = "CHARLIE CORE Runner Watchdog"

if (-not $pythonw) { throw "Python windowless executable not found in the runner worktree or shared repository root." }
$runnerBase = "charlie-runner-core-live-base"
git -C $repo show-ref --verify --quiet ("refs/heads/{0}" -f $runnerBase)
if ($LASTEXITCODE -ne 0) {
    git -C $repo branch $runnerBase HEAD
    if ($LASTEXITCODE -ne 0) { throw "Could not create the dedicated CHARLIE runner base branch." }
}
$action = New-ScheduledTaskAction -Execute $pythonw -Argument ('"{0}" --json' -f $script) -WorkingDirectory $repo
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 2)
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 1)
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Description "Restarts the CHARLIE CORE supervisor when it stops." -Force | Out-Null
Write-Host "Installed $taskName (windowless, every 2 minutes)."
