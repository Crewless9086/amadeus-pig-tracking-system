param(
    [switch]$Json,
    [switch]$AllowForbiddenStaged
)

$ErrorActionPreference = "Stop"

function Add-Unique {
    param([System.Collections.Generic.List[string]]$List, [string]$Value)
    if ($Value -and -not $List.Contains($Value)) {
        $List.Add($Value) | Out-Null
    }
}

function Invoke-Check {
    param(
        [string]$Name,
        [string]$Command,
        [string[]]$Arguments
    )
    Write-Host "==> $Name"
    & $Command @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Check failed: $Name"
    }
    return $Name
}

function Is-ForbiddenPath {
    param([string]$Path)
    $p = $Path -replace "\\", "/"
    return (
        $p -match '^\.env($|[./])' -or
        $p -match '^\.claude/' -or
        $p -match '^screenshots/' -or
        $p -match '^external_sources/' -or
        $p -match '^static/assets/' -or
        $p -match '^test-results/' -or
        $p -eq 'planning/Prompts.md'
    )
}

$repoRoot = (& git rev-parse --show-toplevel).Trim()
Set-Location $repoRoot

$baseRef = "origin/main"
$staged = @(& git diff --cached --name-only)
$unstaged = @(& git diff --name-only)
$untracked = @(& git ls-files --others --exclude-standard)
$branchChanged = @()
try {
    $branchChanged = @(& git diff --name-only "$baseRef...HEAD")
} catch {
    $branchChanged = @()
}

$changed = New-Object 'System.Collections.Generic.List[string]'
foreach ($item in $branchChanged + $staged + $unstaged + $untracked) {
    Add-Unique -List $changed -Value $item
}

$forbiddenStaged = @($staged | Where-Object { Is-ForbiddenPath $_ })
if ($forbiddenStaged.Count -gt 0 -and -not $AllowForbiddenStaged) {
    Write-Error ("Forbidden staged files detected: " + ($forbiddenStaged -join ", "))
    exit 2
}

$forbiddenUntracked = @($untracked | Where-Object { Is-ForbiddenPath $_ })
if ($forbiddenUntracked.Count -gt 0) {
    Write-Host ("Warning: forbidden-looking untracked files are present but not staged: " + ($forbiddenUntracked -join ", "))
}

$checks = New-Object 'System.Collections.Generic.List[string]'
$changedArray = @($changed)

$hasPython = $false
$hasDocs = $false
$hasJs = $false
$hasSam = $false
$hasPigWeights = $false
$hasOwnerAccess = $false
$hasOomSakkie = $false
$hasMigration = $false

foreach ($file in $changedArray) {
    $p = $file -replace "\\", "/"
    if ($p -match '\.py$' -or $p -match '^tests/test_.*\.py$') { $hasPython = $true }
    if ($p -match '\.md$' -or $p -match '^docs/') { $hasDocs = $true }
    if ($p -match '\.js$') { $hasJs = $true }
    if ($p -match 'sam_|sales|conversation_learning|live_stock') { $hasSam = $true }
    if ($p -match 'pig_weights|bulk_weight|allocation') { $hasPigWeights = $true }
    if ($p -match 'owner_access|auth|build_relay') { $hasOwnerAccess = $true }
    if ($p -match 'oom_sakkie') { $hasOomSakkie = $true }
    if ($p -match 'migration|supabase|sql') { $hasMigration = $true }
}

$python = ".\venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    $python = "python"
}

if ($hasDocs) {
    if (-not (Test-Path "docs\00-start-here\NEXT_STEPS.md")) {
        throw "docs/00-start-here/NEXT_STEPS.md is missing"
    }
    if (-not (Test-Path "docs\00-start-here\CURRENT_STATE.md")) {
        throw "docs/00-start-here/CURRENT_STATE.md is missing"
    }
    $checks.Add("docs-required-files") | Out-Null
}

if ($hasJs) {
    $jsFiles = @($changedArray | Where-Object { $_ -match '\.js$' -and (Test-Path $_) })
    foreach ($js in $jsFiles) {
        Invoke-Check -Name "node syntax: $js" -Command "node" -Arguments @("--check", $js) | ForEach-Object { $checks.Add($_) | Out-Null }
    }
}

if ($hasPython) {
    $pyFiles = @($changedArray | Where-Object { $_ -match '\.py$' -and (Test-Path $_) })
    foreach ($py in $pyFiles) {
        Invoke-Check -Name "python compile: $py" -Command $python -Arguments @("-m", "py_compile", $py) | ForEach-Object { $checks.Add($_) | Out-Null }
    }
    $missionLoopTests = @(
        "tests.test_build_relay_notify",
        "tests.test_codex_next_steps",
        "tests.test_trust_log"
    )
    foreach ($test in $missionLoopTests) {
        $testFile = "tests\" + (($test -replace '^tests\.', '') -replace '\.', '\') + ".py"
        if (Test-Path $testFile) {
            Invoke-Check -Name "unittest: $test" -Command $python -Arguments @("-m", "unittest", $test) | ForEach-Object { $checks.Add($_) | Out-Null }
        }
    }
}

if ($hasSam -and (Test-Path "tests\test_sam_live_stock_runtime.py")) {
    Invoke-Check -Name "SAM focused tests" -Command $python -Arguments @("-m", "unittest", "tests.test_sam_live_stock_runtime") | ForEach-Object { $checks.Add($_) | Out-Null }
}

if ($hasPigWeights) {
    if (Test-Path "tests\test_pig_weights_bulk_service.py") {
        Invoke-Check -Name "pig weights bulk tests" -Command $python -Arguments @("-m", "unittest", "tests.test_pig_weights_bulk_service") | ForEach-Object { $checks.Add($_) | Out-Null }
    }
    if (Test-Path "tests\bulk_weights_draft_recovery_node.js") {
        Invoke-Check -Name "bulk weights node smoke" -Command "node" -Arguments @("tests/bulk_weights_draft_recovery_node.js") | ForEach-Object { $checks.Add($_) | Out-Null }
    }
}

if ($hasOwnerAccess -and (Test-Path "tests\test_owner_access.py")) {
    Invoke-Check -Name "owner access tests" -Command $python -Arguments @("-m", "unittest", "tests.test_owner_access") | ForEach-Object { $checks.Add($_) | Out-Null }
}

if ($hasOomSakkie) {
    if (Test-Path "tests\test_oom_sakkie_routes.py") {
        Invoke-Check -Name "Oom Sakkie route tests" -Command $python -Arguments @("-m", "unittest", "tests.test_oom_sakkie_routes") | ForEach-Object { $checks.Add($_) | Out-Null }
    }
    if (Test-Path "tests\oom_sakkie_browser_behavior_smoke.js") {
        Invoke-Check -Name "Oom Sakkie browser smoke" -Command "node" -Arguments @("tests/oom_sakkie_browser_behavior_smoke.js") | ForEach-Object { $checks.Add($_) | Out-Null }
    }
}

if ($hasMigration) {
    $checks.Add("migration-review-required-no-automatic-apply") | Out-Null
    Write-Host "Migration-related files changed. Verify reviewed them, but no migration was applied."
}

if ($checks.Count -eq 0) {
    Write-Error "No relevant verification checks ran. Refusing to pass."
    exit 3
}

$summary = [ordered]@{
    ok = $true
    changed_files = $changedArray
    checks_run = @($checks)
    forbidden_staged = @($forbiddenStaged)
    forbidden_untracked_warning = @($forbiddenUntracked)
}

if ($Json) {
    $summary | ConvertTo-Json -Depth 6
} else {
    Write-Host ""
    Write-Host "CHARLIE verify_mission.ps1 passed"
    Write-Host ("Checks run: " + ($checks -join ", "))
    Write-Host ("Changed files considered: " + $changedArray.Count)
}

