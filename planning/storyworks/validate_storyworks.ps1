[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$petra = Join-Path $root 'pilots\petra'
$failures = [System.Collections.Generic.List[string]]::new()

function Add-Failure([string]$Message) { $failures.Add($Message) }

function Read-Utf8Strict([string]$Path) {
    try {
        $encoding = [System.Text.UTF8Encoding]::new($false, $true)
        return [System.IO.File]::ReadAllText($Path, $encoding)
    }
    catch {
        Add-Failure "Invalid UTF-8: $Path"
        return ''
    }
}

function Import-CheckedCsv([string]$Name, [string[]]$ExpectedHeaders) {
    $text = Read-Utf8Strict (Join-Path $petra $Name)
    if (-not $text) { return @() }
    $rows = @(ConvertFrom-Csv -InputObject $text)
    $actualHeaders = @($rows[0].PSObject.Properties.Name)
    if (($actualHeaders -join '|') -ne ($ExpectedHeaders -join '|')) {
        Add-Failure "$Name headers differ from the required schema."
    }
    return $rows
}

Get-ChildItem -LiteralPath $root -Recurse -File |
    Where-Object { $_.Extension -in @('.md', '.csv', '.svg') } |
    ForEach-Object { [void](Read-Utf8Strict $_.FullName) }

$facts = Import-CheckedCsv 'fact_ledger.csv' @(
    'claim_id', 'script_section', 'claim', 'source_ids', 'evidence_status',
    'certainty', 'required_wording_or_limit'
)
$assets = Import-CheckedCsv 'asset_manifest.csv' @(
    'asset_id', 'description', 'source_url_or_creation_record',
    'creator_rights_holder', 'licence', 'permitted_use', 'attribution',
    'acquisition_date', 'project', 'modifications', 'evidence_location',
    'expiry_or_restriction', 'approval_status'
)
$ai = Import-CheckedCsv 'ai_provenance.csv' @(
    'record_id', 'asset_or_stage', 'tool_model', 'assistance', 'source_inputs',
    'human_direction', 'output_status', 'disclosure_assessment'
)
$visuals = Import-CheckedCsv 'visual_plan.csv' @(
    'scene_id', 'timecode', 'script_section', 'visual', 'creation_method',
    'source_or_evidence', 'rights_status', 'disclosure_note'
)

foreach ($set in @(
    @{ Name = 'fact_ledger.csv'; Rows = $facts; Key = 'claim_id' },
    @{ Name = 'asset_manifest.csv'; Rows = $assets; Key = 'asset_id' },
    @{ Name = 'ai_provenance.csv'; Rows = $ai; Key = 'record_id' },
    @{ Name = 'visual_plan.csv'; Rows = $visuals; Key = 'scene_id' }
)) {
    if (@($set.Rows | Group-Object -Property $set.Key |
            Where-Object Count -gt 1).Count -gt 0) {
        Add-Failure "$($set.Name) contains duplicate $($set.Key) values."
    }
}

$sourcesText = Read-Utf8Strict (Join-Path $petra 'sources.md')
$sourceIds = @([regex]::Matches($sourcesText, '(?m)^### (S\d{2})\b') |
    ForEach-Object { $_.Groups[1].Value })
foreach ($fact in $facts) {
    foreach ($sourceId in $fact.source_ids -split ';') {
        if ($sourceId -notin $sourceIds) {
            Add-Failure "Claim $($fact.claim_id) refers to missing source $sourceId."
        }
    }
}

$factIds = @($facts.claim_id)
$scriptText = Read-Utf8Strict (Join-Path $petra 'script.md')
$scriptClaimIds = @([regex]::Matches($scriptText, 'P\d{3}') |
    ForEach-Object { $_.Value } | Sort-Object -Unique)
foreach ($claimId in $scriptClaimIds) {
    if ($claimId -notin $factIds) {
        Add-Failure "Script refers to missing claim $claimId."
    }
}
foreach ($claimId in $factIds) {
    if ($claimId -notin $scriptClaimIds) {
        Add-Failure "Fact ledger claim $claimId is not cited in the script."
    }
}

function Convert-Timecode([string]$Value) {
    if ($Value -notmatch '^(\d{2}):(\d{2})-(\d{2}):(\d{2})$') {
        Add-Failure "Invalid visual timecode: $Value"
        return $null
    }
    return @(([int]$Matches[1] * 60 + [int]$Matches[2]),
        ([int]$Matches[3] * 60 + [int]$Matches[4]))
}

$previousEnd = 0
foreach ($visual in $visuals) {
    $bounds = Convert-Timecode $visual.timecode
    if ($null -eq $bounds) { continue }
    if ($bounds[0] -ne $previousEnd) {
        Add-Failure "Scene $($visual.scene_id) does not start at the previous scene's end."
    }
    if ($bounds[1] -le $bounds[0]) {
        Add-Failure "Scene $($visual.scene_id) has a non-positive duration."
    }
    $previousEnd = $bounds[1]
}
if ($previousEnd -lt 780 -or $previousEnd -gt 900) {
    Add-Failure 'Visual plan does not end within the 13-15 minute target.'
}

foreach ($asset in $assets |
        Where-Object source_url_or_creation_record -like 'prototypes/*') {
    $relative = $asset.source_url_or_creation_record -replace '/', '\'
    $svgPath = Join-Path $petra $relative
    $pngPath = [System.IO.Path]::ChangeExtension($svgPath, '.png')
    if (-not (Test-Path -LiteralPath $svgPath)) {
        Add-Failure "Missing prototype source: $relative"
    }
    if (-not (Test-Path -LiteralPath $pngPath)) {
        Add-Failure "Missing prototype render: $([System.IO.Path]::GetFileName($pngPath))"
    }
}

$hours = @{ Lean = 12 + 10 + 24 + 6; Base = 20 + 16 + 40 + 10;
    High = 32 + 24 + 64 + 14 }
$timeCosts = @{ Lean = $hours.Lean * 150; Base = $hours.Base * 200;
    High = $hours.High * 250 }
$economicCosts = @{
    Lean = $timeCosts.Lean + 0 + 500 + 0 + 0 + 300
    Base = $timeCosts.Base + 900 + 2000 + 300 + 4500 + 800
    High = $timeCosts.High + 2500 + 6000 + 1200 + 12000 + 1500
}
$expected = @{
    Lean = @{ Hours = 52; Time = 7800; Economic = 8600 }
    Base = @{ Hours = 86; Time = 17200; Economic = 25700 }
    High = @{ Hours = 134; Time = 33500; Economic = 56700 }
}
foreach ($scenario in @('Lean', 'Base', 'High')) {
    if ($hours[$scenario] -ne $expected[$scenario].Hours -or
        $timeCosts[$scenario] -ne $expected[$scenario].Time -or
        $economicCosts[$scenario] -ne $expected[$scenario].Economic) {
        Add-Failure "Unit-economics arithmetic failed for $scenario."
    }
}


function Test-MarkdownStructureAndLinks {
    $markdownFiles = @(Get-ChildItem -LiteralPath $root -Recurse -Filter '*.md' -File)
    foreach ($file in $markdownFiles) {
        $text = Read-Utf8Strict $file.FullName
        if ($text -notmatch '(?m)^# ') {
            Add-Failure "Markdown file has no H1: $($file.FullName)"
        }
        if (([regex]::Matches($text, '(?m)^```').Count % 2) -ne 0) {
            Add-Failure "Unbalanced fenced code block: $($file.FullName)"
        }
        foreach ($match in [regex]::Matches($text, '\[[^\]]+\]\(([^)]+)\)')) {
            $target = $match.Groups[1].Value
            if ($target -match '^(https?://|mailto:|#)') { continue }
            $pathPart = ($target -split '#', 2)[0]
            if (-not $pathPart) { continue }
            $resolved = Join-Path $file.DirectoryName ([uri]::UnescapeDataString($pathPart))
            if (-not (Test-Path -LiteralPath $resolved)) {
                Add-Failure "Broken local Markdown link in $($file.Name): $target"
            }
        }
    }
}

Test-MarkdownStructureAndLinks

$charterText = Read-Utf8Strict (Join-Path $root 'STORYWORKS_BUSINESS_CHARTER.md')
$charterComparable = [regex]::Replace($charterText, '\s+', ' ')
$ladderText = Read-Utf8Strict (Join-Path $root 'BUSINESS_STATE_LADDER.md')
$requiredCharterTerms = @(
    'standalone,',
    'income-producing YouTube media',
    'enterprise that can become commercially self-sustaining',
    'commercially self-sustaining',
    'BEACON owns Amadeus Farm marketing distribution',
    'CHARLIE must never treat content completion as commercial success',
    'No CHARLIE/CORE integration is built, approved, deployed or operational'
)
foreach ($term in $requiredCharterTerms) {
    if ($charterComparable.IndexOf($term, [System.StringComparison]::Ordinal) -lt 0) {
        Add-Failure "Business charter is missing required doctrine: $term"
    }
}
$requiredStates = @(
    'Researched', 'Privately produced', 'Rights/fact/quality approved',
    'Owner-approved for publication', 'Published with exact platform identity',
    'Platform performance observed', 'YPP eligible', 'Monetisation activated',
    'Platform revenue estimated', 'Platform revenue finalised', 'Cash received',
    'Direct costs reconciled', 'Operating reserve funded',
    'Distributable profit owner-approved', 'Funds transferred and reconciled'
)
$lastIndex = -1
foreach ($state in $requiredStates) {
    $index = $ladderText.IndexOf("| $state |", [System.StringComparison]::Ordinal)
    if ($index -lt 0) { Add-Failure "Business-state ladder is missing: $state" }
    elseif ($index -le $lastIndex) { Add-Failure "Business-state ladder order is invalid at: $state" }
    $lastIndex = $index
}
foreach ($boundary in @(
    'Missing evidence is `Unknown`',
    'later state may never be inferred',
    'Views, subscribers, completed videos',
    'No commingling or allocation occurs before revenue is real'
)) {
    if ($ladderText.IndexOf($boundary, [System.StringComparison]::OrdinalIgnoreCase) -lt 0) {
        Add-Failure "Business-state ladder is missing boundary: $boundary"
    }
}
$ownerThesis = 'Petra managed both scarce water and destructive runoff through a layered, engineered and continually maintained water-management system.'
foreach ($name in @('brief.md', 'script.md', 'PREPRODUCTION_DECISION_CANDIDATE.md')) {
    $text = Read-Utf8Strict (Join-Path $petra $name)
    $comparable = [regex]::Replace($text, '\s+', ' ')
    if ($comparable.IndexOf($ownerThesis, [System.StringComparison]::Ordinal) -lt 0) {
        Add-Failure "$name does not preserve the provisional owner-directed Petra thesis."
    }
}
$p017 = @($facts | Where-Object claim_id -eq 'P017')
if ($p017.Count -ne 1 -or $p017[0].evidence_status -ne 'inference' -or
        $p017[0].certainty -ne 'medium-high' -or
        $p017[0].required_wording_or_limit -notmatch 'flood danger was eliminated') {
    Add-Failure 'P017 evidence status, certainty or owner-directed uncertainty control changed.'
}
$a011 = @($assets | Where-Object asset_id -eq 'CV001-A011')
if ($a011.Count -ne 1 -or $a011[0].approval_status -ne 'revision_required') {
    Add-Failure 'A011 must remain an exploratory thumbnail with revision required.'
}
$editText = Read-Utf8Strict (Join-Path $petra 'edit_plan.md')
$editScenes = @([regex]::Matches($editText, '(?m)^\| (V\d{3}) \|') |
    ForEach-Object { $_.Groups[1].Value })
if ($editScenes.Count -ne 20 -or ($editScenes | Select-Object -Unique).Count -ne 20 -or
        $editText -notmatch 'exactly \*\*14:20\*\*') {
    Add-Failure 'Private timing-edit plan must contain 20 unique scenes and exact 14:20 timing.'
}
$candidateText = Read-Utf8Strict (Join-Path $petra 'PREPRODUCTION_DECISION_CANDIDATE.md')
foreach ($boundary in @(
    'does not authorise editing',
    'No asset is permanently rejected',
    'Charl is not the default business narrator',
    'no narration, music or external SFX'
)) {
    if ($candidateText.IndexOf($boundary, [System.StringComparison]::OrdinalIgnoreCase) -lt 0) {
        Add-Failure "Pre-production candidate is missing boundary: $boundary"
    }
}
$pronunciationText = Read-Utf8Strict (Join-Path $petra 'PRONUNCIATION_REVIEW_SHEET.md')
if ($pronunciationText.IndexOf('No phonetics have been invented', [System.StringComparison]::Ordinal) -lt 0 -or
        $pronunciationText.IndexOf('____________________', [System.StringComparison]::Ordinal) -lt 0) {
    Add-Failure 'Pronunciation sheet lacks its no-invention boundary or blank approval fields.'
}
$syntheticText = Read-Utf8Strict (Join-Path $petra 'SYNTHETIC_NARRATION_EVALUATION.md')
foreach ($criterion in @('Voice quality and suitability', 'Pronunciation control',
        'Commercial-use rights', 'Provider terms', 'Cost per finished video',
        'Repeatability and automation', 'Owner approval controls')) {
    if ($syntheticText.IndexOf($criterion, [System.StringComparison]::Ordinal) -lt 0) {
        Add-Failure "Synthetic narration evaluation is missing: $criterion"
    }
}
if ($failures.Count -gt 0) {
    $failures | ForEach-Object { Write-Error $_ }
    exit 1
}

Write-Output (("PASS: strict UTF-8, 4 CSV schemas, {0} claims, {1} sources, " +
    "{2} scenes, {3} assets, Markdown links/structure, business doctrine, prototype pairs, and unit-economics arithmetic.") -f
    $facts.Count, $sourceIds.Count, $visuals.Count, $assets.Count)
