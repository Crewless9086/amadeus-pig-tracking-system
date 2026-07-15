$ErrorActionPreference = "Stop"
$repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$pythonCandidates = @(
    (Join-Path $repo "venv\Scripts\python.exe"),
    (Join-Path (Split-Path (Split-Path $repo -Parent) -Parent) "venv\Scripts\python.exe")
)
$python = $pythonCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $python) { throw "Python venv not found for CHARLIE watchdog." }

$trusted = @(git config --global --get-all safe.directory 2>$null)
if ($trusted -notcontains $repo) {
    git config --global --add safe.directory $repo
    if ($LASTEXITCODE -ne 0) { throw "Could not trust the designated CHARLIE runner worktree." }
}

& $python (Join-Path $PSScriptRoot "charlie_runner_watchdog.py") --json
exit $LASTEXITCODE
