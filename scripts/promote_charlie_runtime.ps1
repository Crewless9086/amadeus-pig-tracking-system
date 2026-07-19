param(
    [string]$SourceRef = "origin/main",
    [string]$RuntimeRoot = "",
    [string]$TaskName = "CHARLIE CORE Runner Watchdog",
    [string]$RuntimeBranch = "charlie-core-runtime-base"
)

$ErrorActionPreference = "Stop"
$sourceRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$commonGitDir = git -C $sourceRoot rev-parse --path-format=absolute --git-common-dir
if ($LASTEXITCODE -ne 0 -or -not $commonGitDir) { throw "Could not resolve the canonical repository Git directory." }
$canonical = (Split-Path $commonGitDir.Trim() -Parent)
if (-not $RuntimeRoot) {
    $RuntimeRoot = Join-Path $canonical ".charlie_runner\core-runtime-current"
}
$runtimeState = Join-Path $canonical ".charlie_runner"
$python = Join-Path $canonical "venv\Scripts\python.exe"
$pythonw = Join-Path $canonical "venv\Scripts\pythonw.exe"
if (-not (Test-Path -LiteralPath $python) -or -not (Test-Path -LiteralPath $pythonw)) {
    throw "The canonical project venv is required before CORE runtime promotion."
}

git -C $canonical fetch origin --prune
if ($LASTEXITCODE -ne 0) { throw "Could not fetch the authoritative remote revision." }
git -C $canonical rev-parse --verify $SourceRef | Out-Null
if ($LASTEXITCODE -ne 0) { throw "SourceRef does not resolve: $SourceRef" }

if (Test-Path -LiteralPath $RuntimeRoot) {
    $dirty = git -C $RuntimeRoot status --porcelain
    if ($LASTEXITCODE -ne 0) { throw "Existing runtime path is not a healthy Git worktree." }
    if ($dirty) { throw "Existing runtime worktree is dirty; promotion refused without cleanup review." }
    git -C $RuntimeRoot switch -C $RuntimeBranch $SourceRef
    if ($LASTEXITCODE -ne 0) { throw "Could not update the runtime worktree." }
} else {
    git -C $canonical worktree add --detach $RuntimeRoot $SourceRef
    if ($LASTEXITCODE -ne 0) { throw "Could not create the runtime worktree." }
    git -C $RuntimeRoot switch -C $RuntimeBranch $SourceRef
    if ($LASTEXITCODE -ne 0) { throw "Could not establish the dedicated runtime base branch." }
}

$focused = @(
    "tests.test_charlie_runner_control",
    "tests.test_charlie_runner_watchdog",
    "tests.test_charlie_runner_supervisor",
    "tests.test_charlie_mission_pickup",
    "tests.test_charlie_runtime_integrity"
)
& $python -m unittest $focused
if ($LASTEXITCODE -ne 0) { throw "CORE runtime verification failed; scheduled task was not changed." }

& $python (Join-Path $RuntimeRoot "scripts\charlie_runtime_audit.py") promote --runtime-dir $runtimeState
if ($LASTEXITCODE -ne 0) { throw "Runtime manifest promotion failed." }

$watchdog = Join-Path $RuntimeRoot "scripts\charlie_runner_watchdog.py"
$envFile = Join-Path $canonical ".env"
$argument = '-c "from dotenv import load_dotenv; load_dotenv(r''{0}'', override=True); import runpy,sys; sys.argv=[r''{1}'',''--json'']; runpy.run_path(r''{1}'', run_name=''__main__'')"' -f $envFile,$watchdog
$action = New-ScheduledTaskAction -Execute $pythonw -Argument $argument -WorkingDirectory $RuntimeRoot
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 2)
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 1) -Hidden
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Description "Promoted, manifest-gated, windowless CHARLIE CORE watchdog." -Force | Out-Null
$installed = Get-ScheduledTask -TaskName $TaskName
$installedAction = $installed.Actions | Select-Object -First 1
if ($installedAction.Execute -ne $pythonw -or $installedAction.WorkingDirectory -ne $RuntimeRoot) {
    throw "Scheduled task verification failed after registration."
}

Write-Output "Promoted CORE runtime from $SourceRef"
Write-Output "Runtime root: $RuntimeRoot"
Write-Output "Task: $TaskName"
