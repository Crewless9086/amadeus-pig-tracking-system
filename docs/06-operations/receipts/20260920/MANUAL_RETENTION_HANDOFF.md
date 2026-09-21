# Manual retention handoff — 2026-09-20

Current mission evidence, NON_DOCTRINE. Mission
`REPOSITORY-CONSOLIDATION-20260918`; sole coordinator
`CONTROL-TOWER-DESKTOP-SUCCESSOR-20260918`; continuing task
`01a0b9d5-5c55-7e30-a5fc-aea27c93ffd6`. Existing cleanup, intact relocation and
bounded app-maintenance approval continues. The owner explicitly requested a
practical manual way to finish after repeated delays. No further cleanup
approval is needed.

## Definite result

The Windows-owned helper survived to a final result. It stopped at
2026-09-19 23:10:18 SAST with `HELD`, `app_exit_wait_expired_no_move`,
`renamed=false`, and no source audit or rename. It removed its task registration
at 23:10:22. The exact same Codex PID29356, created September 19 at
20:21:05.8337865 UTC, remains present September 20 at 07:57 SAST. This proves the
recorded app did not exit during the wait; it does not establish why the owner's
attempt to close it was ineffective. Do not attribute fault to the owner.

Read-only native checks at 05:57:43 UTC / 07:57:43 SAST confirm:

- Source `C:\Users\charl\OneDrive\1. Amadeus\AGENTS\amadeus-pig-tracking-system`
  remains native volume `17629920732283616668`, inode `47850746040959140`,
  attributes49/tag0.
- Destination `C:\Amadeus\recovery\20260919\retained-originals\agents\amadeus-pig-tracking-system`
  is absent. Its parent exists on the same volume, with ordinary ancestors.
- Both temporary Amadeus maintenance tasks are absent. No cleanup is running.
- All three prior Docker containers remain running, approximately nine hours
  uptime. n8n health returned HTTP200. All four CHARLIE tasks remain Disabled.

The last full original audit remains the September 19 18:31 UTC proof:
172,892 objects, 154,225 ordinary files, 14,457,397,151 hashed stream bytes,
one opaque junction and zero nonopaque Cloud entries. This turn's root check
is not a new full content audit. Totals remain 556 retained source roots;
no source object was deleted or moved in this continuation.

## Owner's direct move

Save this instruction outside Codex, save open work and restart Windows.
Before reopening Codex, open Windows PowerShell as administrator from Start.
Paste the following complete block. The process check stops if Codex reopened;
close Codex before retrying. There is no timer, task registration or helper.

```powershell
$ErrorActionPreference = 'Stop'
if (Get-Process -Name ChatGPT -ErrorAction SilentlyContinue) {
    throw 'Codex is still running. Close it before moving the folder.'
}
[System.IO.Directory]::Move(
    'C:\Users\charl\OneDrive\1. Amadeus\AGENTS\amadeus-pig-tracking-system',
    'C:\Amadeus\recovery\20260919\retained-originals\agents\amadeus-pig-tracking-system'
)
Write-Host 'Folder moved. Reopen the same Codex task for verification.'
```

The exact source and destination were checked above. Directory.Move refuses an
existing destination and cross-volume directory moves; it does not merge into
an existing destination. See [Microsoft Directory.Move documentation](https://learn.microsoft.com/en-us/dotnet/api/system.io.directory.move?view=net-9.0).
If the command errors, preserve the error and reopen this task. Do not substitute
recursive copying/deletion, permission resets or junction traversal.

After the owner returns, verify source absence and the destination's exact
native identity, then run the existing read-only full retention audit against
the retained baseline: counts, content/streams, security, attributes and raw
opaque link data. Check Docker/n8n and task absence again after the restart.
Preserve the manual result, reconcile the recovered absolute junction target
as historical evidence, and only then classify root557 and cleanup completion.

The new daily source at `C:\Amadeus\repo` is available for local development
now. Its continuing branch is unreleased. This old-copy move need not prevent
local fixes; integration, release and all existing operational holds remain.

## Source and evidence

Governance preflight: the mandatory Governance/CORE pack loaded for this
continuing mission is unchanged in Git. The tracked operating-standard blob is
`5fbcf11ebdfd171a286339de83a205df782dabd4`. Canonical startup guard passed at
HEAD `7c99206fcbe574ee3bdbe23ae544f879e435d382`, tree
`c2c4e05813b09324752ef022e131ca3c2872a701`, branch
`codex/workspace-consolidation-20260919`, one worktree, clean, no upstream.
Fresh fetched main remains `e46743cb3e8d224b60d17eb5920acb113f613a52`,
17ahead/0behind at startup. Final commit/guard and evidence/bundle hashes belong
to recovery `manual-handoff-workspace-verification.json`.

Runtime phase remains
`C:\Amadeus\.runtime\consolidation\maintenance-20260919\original-final-retention`.
Preserve `original-scheduled-apply-result.json`, its complete journal and
`scheduled-task-retirement.json` alongside this instruction in recovery
`manual-handoff-evidence`. Incremental source bundle
`manual-handoff-update.bundle` requires the preceding Windows handoff HEAD
`7c99206fcbe574ee3bdbe23ae544f879e435d382`. Earlier evidence stays immutable.

Control Tower Check Receipt: one pending local retention, no live worker or
new timer, prior review lanes frozen, release lane held, no source/runtime
writer dispatch or change to registered worktrees. Application deployment,
provider/database/farm/customer/hardware/payment actions are outside this
continuation. No deployed business outcome is asserted.

Decision: WAIT for final retention; local development may proceed.
Why: the old copy is intact, but an open Codex process prevents this session
from proving its final move. The owner asked for a direct manual action.
Send to exact terminal: CONTINUE—SEND NOTHING; reopen this same task afterward.
Expected business result: final recovery placement verified without another
expiring handoff; no deployed business outcome claimed.
ACTION REQUIRED NOW: Run the exact move above with Codex closed after a Windows
restart, then reopen this task with the result.
