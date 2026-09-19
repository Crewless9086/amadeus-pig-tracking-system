# Windows-owned cleanup handoff — 2026-09-19

Current mission evidence; NON_DOCTRINE. Continuing mission
`REPOSITORY-CONSOLIDATION-20260918`, coordinator
`CONTROL-TOWER-DESKTOP-SUCCESSOR-20260918`, task
`01a0b9d5-5c55-7e30-a5fc-aea27c93ffd6`. Existing owner cleanup, intact retention
and bounded application/Docker/access maintenance approval remains active.
No repeated approval, new business mission or release authority is inferred.

**Cleanup is not complete. The original checkout remains in place.**
The prior [restart handoff](AFTER_RESTART_CLEANUP_STATUS.md) is historical for
its old process IDs, deadlines and launch instructions. Preserve both failed
attempts; only the current external launch/journal proves a live continuation.

## Verified failure

The first after-exit helper timed out without mutation. The next helper,
PID 27100, was launched at 21:36 SAST, last recording WAITING at 21:36:46.
At the owner's 22:24 follow-up, both it and old Codex PID 27472 had exited.
There is no final result, source audit, rename intent or after-audit receipt.
The source remains present and destination absent. The current app is PID
29356, created 20:21:05.8337865 UTC / 22:21:05 SAST. Windows has not rebooted
since 19:49 SAST. The cause of the helper's exit is unknown. Coupling to the
app's process lifetime is an inference, not a proven termination cause.

Docker was also stopped, with n8n unavailable. Its regenerated `run` directory
again contained exactly the two inaccessible zero-byte reparse sockets
`dockerInference` and `userAnalyticsOtlpHttp.sock`; native query returned 1920.
With no Docker process present, the exact directory was retained intact at
phase `docker-run-retained-after-reopen`, same native volume/inode
`17629920732283616668` / `134545038867715038`. No child traversal, deletion,
ACL change, configuration reset, image pull or volume/data removal.
This transient socket artifact is separate from the source-root count.

Canonical startup guard passed at HEAD
`8d99bf8bc606b8826ce649ab075f98d8e0251c67`, tree
`82188cae263656e9e96d368b94dec93639899291`, one worktree, no upstream,
16 ahead/zero behind fresh unchanged main
`e46743cb3e8d224b60d17eb5920acb113f613a52`. The earlier loaded mandatory
Governance/CORE pack remains unchanged. All former coordinator/source/release
holds and operational mission identities remain in the register.

## Changed launch mechanism

Phase: `C:\Amadeus\.runtime\consolidation\maintenance-20260919\original-final-retention`.
Two exact local Windows Task Scheduler registrations were created, with no
triggers, recurrence or automatic restart:

- `Amadeus-DockerRestore-Once-20260919`: owner interactive token, Limited.
  Starts Docker and restores only the same three recorded container IDs after
  before/after image, mount and restart-policy equality checks; requires all
  three running and local n8n health 200. Result publishes atomically after flush.
  Registration is removed after verified restoration and starter-process exit.
- `Amadeus-LocalCleanup-Once-20260919`: same owner interactive token, Highest
  after native UAC consent. Waits at most thirty minutes for the exact current
  Codex process to exit; repeats complete original preservation qualification,
  performs one no-overwrite same-object move and complete destination proof.
  Exact scheduled-task action is checked and its registration removed after
  the durable result, before the explicit success/failure result window.

These are finite local maintenance helpers, not Codex recurring automations or
new business observers. The four existing CHARLIE tasks are not changed.
No process is forcibly stopped. Original identities, contents, streams,
owner/group/DACL and opaque link protection remain unchanged from the reviewed
retention contract; generic repository/Cloud guards remain unchanged.

Bootstrap verifies registered owner, run level, executable, arguments, cwd,
zero triggers/restarts, battery settings, time limit and instance policy.
It requires the cleanup's durable WAITING journal, exact PID/creation/executable,
Running task state and Windows Schedule-service ancestry. Parent then checks
that the bootstrap/starter have exited, Docker still runs, n8n is healthy and
the cleanup process is independently owned by Windows. A task registration or
successful Start-ScheduledTask call alone is not accepted as a live handoff.
Execution limits and process ancestry are not proof that the final move happened.

Exact reviewed files:

- `register-windows-handoff.ps1`:
  `fe0a0434967903077879fb0bec934c86ede6a264326bc9254a44e7ea54a82d45`.
- `retain-original-scheduled.ps1`:
  `3f19a82ab1a44366091a1ae055973a9b24623e1b9adb3cd4a55dfcbb257c4297`.
- `restore-docker-scheduled.ps1`:
  `6632ce96ff636ab4f855f901c24d527cac5854058e38e11dc58e9fa2b75ba7b5`.

Independent source review addressed result-file publication race, asynchronous
start confirmation, complete task-setting readback, post-start container checks
and task-removal readback. Parent also fixed JSON date parsing to compare
process-start UTC ticks exactly; round-trip check passed. In-memory task
construction passed without registration. Original preservation fixtures and
full live audits retain their earlier separate attribution; no new full-audit
claim precedes actual execution.

## Live handoff verified

Independent observation at 20:41:49 UTC / 22:41:49 SAST is saved in phase
`windows-handoff-live-verification.json`, status `WINDOWS_HANDOFF_VERIFIED`.
Bootstrap PID28812 and Docker starter PID32740 have exited. The Docker task
registration is absent; all three original containers remain running with
matching IDs, images, mounts and restart policies. n8n health returned HTTP200.
All four CHARLIE task registrations remain Disabled.

Cleanup task `Amadeus-LocalCleanup-Once-20260919` is Running. Its actual helper
is pwsh PID27160, created 20:40:12.8897916 UTC, parent PID2576: the running
Windows `Schedule` service. Registration readback and startup handshake passed.
The durable journal records `WAITING_FOR_CODEX_EXIT` from 20:40:13.5271500 UTC,
waiting for current Codex PID29356 with exact start 20:21:05.8337865 UTC.
The thirty-minute app-exit wait expires around 23:10 SAST. A later continuation
must check the actual result/process state instead of reusing this live claim.
No original rename has happened; the source remains present and destination
absent. Only the final result and independent readback can close this mission.

## Continuation and preservation

Current runtime state must be read from `scheduler-registration-result.json`,
`docker-scheduled-result.json` and `original-scheduled-apply.journal.jsonl`.
Final outcome: `original-scheduled-apply-result.json`.
Registration-removal proof: `scheduled-task-retirement.json`.
Any HELD, missing result, MOVED_UNCONFIRMED or failed service restoration remains
incomplete. Preserve the source/results and diagnose; no automatic retry loop.

Totals remain 556 retained source roots, 250,321 files and 12,741 empty
directories previously removed, 15,537,781,090 logical bytes; physical savings
unmeasured. This continuation deletes zero source objects. The four pytest
ownership classifications remain unverified. Private ignored `.env`, bundles,
DPAPI snapshots/keys, incomplete-snapshot truth, dirty history, failed findings,
mission identities and application holds remain preserved. Source setup is
ready at `C:\Amadeus\repo`; the continuing branch is unreleased and still needs
governed integration before operational continuation.

No push, merge, deployment, database/farm/customer/hardware action, permission
change to originals, payment or provider publication. No BUSINESS_COMPLETE
or deployed owner outcome. Local restoration does not prove business workflow
acceptance. Reviews are frozen after their bounded work; one cleanup WIP slot.
The release lane and all existing operational holds remain unchanged.

Evidence copies, exact source backup and closing guard belong to recovery
`windows-handoff-evidence`, `windows-handoff-update.bundle` and
`windows-handoff-workspace-verification.json`. The incremental bundle requires
`8d99bf8bc606b8826ce649ab075f98d8e0251c67`, preserved in the previous timeout
bundle chain. Earlier receipts/bundles remain immutable. Opaque socket/fixture
directories stay intact in runtime and are not recursively traversed or copied.

Control Tower Check Receipt: one local WIP slot; unchanged authority; failed
handoff preserved; exact Windows-owned startup gate; required clean workspace
check; no shared release or operational dispatch. No completion claim before
actual source absence, destination identity and full preservation readback.

Decision: WAIT.
Why: the last intact move requires Codex's descendant watchers to stay closed;
the previous helper did not survive to a result.
Send to exact terminal: CONTINUE—SEND NOTHING; retain this task lineage.
Expected business result: one recoverable local source entrypoint; no deployed
business outcome asserted.
ACTION REQUIRED NOW: Windows-owned WAITING and service survival are confirmed.
Press Ctrl+Q and leave Codex closed until the explicit completed/NOT completed
window; then reopen this same task for independent final readback.
