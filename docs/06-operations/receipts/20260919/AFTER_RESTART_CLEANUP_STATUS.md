# Cleanup after restart — 2026-09-19
## Timeout follow-up and fresh attempt

The first after-exit process finished at 19:07:51 UTC / 21:07:51 SAST with
`HELD`, `app_exit_wait_expired_no_move`, `renamed:false`. No fresh audit or
rename occurred. The popup was a failure/timeout notification, not completion.
A 21:30 SAST follow-up found that process exited and the exact original Codex
process PID 27472/start 18:04:49.3122677 UTC still running. Source remains
present, destination absent; the new source workspace is clean. Docker's three
recorded containers remain running; local n8n health returned HTTP 200 again.

The following new attempt is separately recorded; prior files are immutable.
Wrapper `retain-original-after-exit-retry1.ps1`, SHA-256
`203b03514c847c86b1931e4617e255822247f3b392ca93bef762b3d16468aa02`.
Only output names and completion-dialog caption differ from reviewed
`6777623b...`: outputs use `original-after-exit-retry1-apply*`; caption is
**Amadeus cleanup completed** only for `RETAINED_VERIFIED`, otherwise
**Amadeus cleanup NOT completed**. Exact identities, finite wait, no-app checks,
full fresh audits, same-object/no-overwrite rename and no-retry rules remain.
Check the separate `after-exit-retry1-launch.json` and live journal for actual
launch/WAITING state. Source preparation alone is not launch or success.

Use **Ctrl+Q** while Codex is focused to quit fully; stay out until the new
result window. The installed app's main menu defines `role:quit` with `Ctrl+Q`,
and its tray Quit action calls the app's graceful quit function. This is also
the [official Windows Quit shortcut](https://learn.chatgpt.com/docs/reference/commands).
No application code/settings were edited or private IPC called. Earlier wording
that treated any result popup as sufficient to reopen was ambiguous; read the
explicit result status. Reopen this same task for independent final readback.

The earlier after-exit launch and deadline below are historical. The fresh
attempt is under the same already-granted cleanup/maintenance authority; no
new approval or expanded scope. The launch starts a new thirty-minute limit.
This timeout outcome and retry setup are preserved separately under recovery
`after-exit-timeout-evidence`; the new source checkpoint is backed up by
`after-exit-timeout-update.bundle`, requiring prior source
`75b3c0a4d3558819d212664c0844eb96179b2018`. Exact guard and launch observations
belong in `after-exit-timeout-workspace-verification.json`.

## Preserved prior handoff

Current mission evidence; NON_DOCTRINE. Mission
`REPOSITORY-CONSOLIDATION-20260918`, coordinator
`CONTROL-TOWER-DESKTOP-SUCCESSOR-20260918`, task
`01a0b9d5-5c55-7e30-a5fc-aea27c93ffd6`.

**Daily source is ready; cleanup is not yet complete. One original checkout
still needs an intact move while Codex remains closed. Docker and n8n are
restored.** The previous [maintenance receipt](MAINTENANCE_CLEANUP_STATUS.md)
remains historical evidence; its quit-and-immediately-reopen instruction is
superseded by the exact after-exit procedure below. No repeated permission is
needed: the owner already approved this cleanup and bounded maintenance.

## Verified state

- Everyday source, saved project and current task: `C:\Amadeus\repo`.
- Temporary working evidence: `C:\Amadeus\.runtime`.
- Recovery: `C:\Amadeus\recovery\20260919`.
- 556 roots retained intact; the five old tmp roots are absent and `C:\tmp`
  is empty. Four pytest ownership classifications remain unverified.
- Earlier removal remains 250,321 files and 12,741 empty directories,
  15,537,781,090 logical bytes. Physical savings are unmeasured. This phase
  deleted zero source objects.
- Private `.env` remains ignored/untracked in the daily checkout. All-ref
  bundles, encrypted snapshots/DPAPI keys, manifests, actual restore proofs,
  unreleased branches, dirty-history evidence and previous failed findings
  remain preserved. Historic `preservation_complete:false` is not rewritten.

Startup guard passed from the canonical checkout resolved through Git common
metadata. HEAD `b0657ad6c7ac6b94b1c7255e858874568207401c`, tree
`ba60566d30cca1da84f3149921e5fa71690bef25`, branch
`codex/workspace-consolidation-20260919`, no upstream, one worktree,
14 ahead/zero behind freshly fetched unchanged main
`e46743cb3e8d224b60d17eb5920acb113f613a52`. The mandatory governance and CORE
pack had no changes. The closing source commit, clean guard and bundle belong
to external `after-restart-workspace-verification.json`, not this startup value.

## Exact failure and preservation

Source: `C:\Users\charl\OneDrive\1. Amadeus\AGENTS\amadeus-pig-tracking-system`.
Intended destination:
`C:\Amadeus\recovery\20260919\retained-originals\agents\amadeus-pig-tracking-system`.
Native volume `17629920732283616668`, inode `47850746040959140`.

After the owner restarted Codex, native DELETE access succeeded. The original
move wrapper received UAC consent at 18:20:40 UTC. Its full pre-move audit
matched the previous proof: 172,892 objects, 154,225 ordinary/Cloud files,
14,457,397,151 hashed stream bytes and one opaque junction. The native
no-overwrite rename returned Win32 5, Access denied, at 18:25:23 UTC.
Result `HELD`, `renamed:false`; source present, destination absent.

The attempted move caused local provider conversion before Windows rejected
the rename. Do not describe it as unchanged metadata. A separate administrator
read-only audit ended at 18:31:10 UTC with `PRESERVATION_VERIFIED_AT_SOURCE`:
all 172,892 objects, file identities, complete streams, owner/group/DACL,
non-Cloud attributes and the opaque link match the earlier proof. The stable
digest is `45ff8ca2419db7308d58735de5cf9cf0e61163b5f35c93b9a0cf2122bc7cae42`.
There are zero remaining Cloud entries. Root attributes 49, tag 0; source and
volume/file identity remain exact, destination absent. No provider readback or
provider-neutrality is claimed.

The junction `.review_core_evidence_reconciliation\venv` was preserved as its
own object: raw reparse bytes, own security and empty stream metadata, without
following its target. Its absolute old-path target may need the original path
restored for recovery use; recovery is not a runnable development checkout.

Native process-user queries find the restarted app, `ChatGPT.exe` PID 27472,
created 18:04:49.3122677 UTC, holding the original root, `.git` and `.git\refs`.
Independent eight-case fixture reproduced the Windows rule: a second root
handle permits cross-parent rename; either descendant directory or file handle
causes Win32 5, even when it shares DELETE. Adding the original readonly and
inherited deny-delete-child pattern did not change that distinction. No ACL
change is required to resolve these confirmed watcher holds.

## Prepared terminal-independent continuation

Runtime/evidence directory:
`C:\Amadeus\.runtime\consolidation\maintenance-20260919\original-final-retention`.
Reviewed wrapper: `retain-original-after-exit.ps1`, SHA-256
`6777623b7b7859592371386982c7c32a3c53c1ef9d8ad7aeb347febaeb0664db`.
Pinned helper: `OriginalFinalQualify.cs`, SHA-256
`46349244835fd1f41b3811a45c0a266e002faae3ff46b044ed488d49aea74123`.
The existing repository retention and Cloud qualifiers remain unchanged.

The one-shot administrator helper waits at most 30 minutes for the exact
current app PID/creation identity to exit; it never stops it. It rejects other
Codex instances before auditing and immediately before rename. It requires the
exact now-ordinary original identity, no Cloud dependency, protected ancestor
identities, absent destination, full fresh baseline digest and same NTFS volume.
It holds the DELETE handle through one no-overwrite rename and full destination
audit. Durable intent precedes mutation. Only equal content/security/raw-link
proof plus source absence produces `RETAINED_VERIFIED`. Post-move uncertainty
is `MOVED_UNCONFIRMED`; pre-move failures/timeout are `HELD`. No automatic retry,
overwrite, deletion, ACL/ownership change, link-target traversal or rollback.
The narrow race with a new app launch is not claimed to be atomically excluded;
Windows and the post-audit still prevent a false success claim.

The Windows result dialog appears after the receipt is durable and handles are
released. Keep Codex closed until that dialog appears. A success dialog still
requires independent readback and final evidence/source closeout in this task.
Check `after-exit-launch.json` and
`original-after-exit-apply.journal.jsonl` for actual launch/wait state; source
preparation and review are not proof that the helper launched or moved anything.
The final result is `original-after-exit-apply-result.json`.

Reviews: the initial wrapper's output-name expression and pre-compilation error
handling were corrected before live use. Independent helper compilation and
20 digest/negative checks passed; the coordinator's native fixture proved
held-handle audit, ordinary/alternate stream preservation, opaque locked-target
and loop containment, no-overwrite rejection and actual same-object rename.
The after-exit wrapper added the reviewer's second app-absence check immediately
before intent. Full exact-source review passed. Synthetic evidence is distinct
from the live failed rename and successful read-only preservation audit.

## Service restoration and boundaries

Docker was stopped after the restart. Its initial startup failed removing
`dockerInference`, an inaccessible zero-byte socket. The verified Docker error
window closed gracefully; all Docker processes exited. The exact old `run`
directory contained only `dockerInference` and `userAnalyticsOtlpHttp.sock`.
That directory was retained intact at `docker-run-retained` in phase runtime,
same volume/inode `3659174697662097`, with no target traversal or child deletion.
Docker recreated runtime sockets and started. Configuration, images, volumes
and n8n state were not reset or removed. This socket artifact is separate from
the 556 consolidated source-root count.

The exact three recorded container IDs are running again, same image IDs,
mounts and restart policies: both OMQ PostgreSQL containers and `charl-n8n-1`.
Local n8n `/healthz` returned HTTP 200 at 18:25:30 UTC. This is local service
restoration, not business-workflow acceptance. All four CHARLIE scheduled tasks
remain disabled. No operational agents were restarted.

Source/release workers remain frozen; reviewer becomes terminal after its
bounded review. No new operational dispatch, push, merge, deployment, database,
farm, customer, hardware, permission, payment or provider publication action.
OMQ draft PR #1340 retains admission/release holds; all Linda, C Camp, observer,
Supabase 402 and specialist holds remain in the register. Historical production
`3d321e4932cf205d03e759cc71a26edd411bc9d2` is not a fresh acceptance observation.
No BUSINESS_COMPLETE, deployed outcome or recurring monitor is claimed.

Evidence files include both full audits and summaries, failed rename journal,
exact helper/wrappers/tests/reviews, native watcher diagnosis, eight-case handle
fixture, Docker before/after snapshots and local health. Regular phase files
are copied without overwrite into recovery `after-restart-evidence`, with a
hash manifest. Opaque fixtures and retained broken sockets stay intact in
runtime; do not recursively traverse/copy their targets. The new incremental
`after-restart-update.bundle` requires base `b0657ad6c7ac6b94b1c7255e858874568207401c`,
restorable from prior `maintenance-consolidation.bundle` plus
`original-audit-update.bundle`. Prior bundles/receipts remain immutable.

Control Tower Check Receipt: one local WIP slot; current source/authority routed;
full live preservation verified after the failed rename; independent source and
handle-fixture review passed; services restored; release lane unused; all other
operational lanes retain their holds/Unknown. Manual work is reduced to the
single application-exit gate; no business outcome or quantified time saving.

Decision: WAIT.
Why: the final original move is qualified, but Codex's open descendant watchers
must remain absent through the one-shot move and verification.
Send to exact terminal: CONTINUE—SEND NOTHING; preserve this task's lineage.
Expected business result: one recoverable local development entrypoint;
no deployed business outcome asserted.
ACTION REQUIRED NOW: Once retry1 is confirmed WAITING, press Ctrl+Q to quit Codex and
keep it closed until the explicit completed/NOT completed result window appears; then reopen
this same task in `C:\Amadeus\repo` for final readback.
