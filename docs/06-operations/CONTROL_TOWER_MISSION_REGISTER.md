# Control Tower Mission Register

Status: current-state evidence; non-doctrine.
Updated: 2026-09-19, after-exit timeout verified; fresh bounded retry prepared.
Coordinator: `CONTROL-TOWER-DESKTOP-SUCCESSOR-20260918`.
Coordinating task: `01a0b9d5-5c55-7e30-a5fc-aea27c93ffd6`.
Mission: `REPOSITORY-CONSOLIDATION-20260918`.
Migration: HELD — one original checkout remains; Codex descendant watchers must exit.
The first after-exit helper expired at **19:07:51 UTC / 21:07:51 SAST**, status
`HELD`, reason `app_exit_wait_expired_no_move`, `renamed:false`. It never reached
the audit/move stage. Its PID 380 has exited; the same original Codex PID 27472
is still running. The result popup did not mean completion. Current source is
present and destination absent. The new workspace remains clean; all three
Docker containers are running and n8n health is 200.

Fresh one-shot attempt: `retain-original-after-exit-retry1.ps1`, separate
`original-after-exit-retry1-apply*` receipts. Existing authority and all reviewed
preservation gates remain unchanged; prior timeout evidence is preserved.
Check `after-exit-retry1-launch.json` and its journal before treating it as armed.
Use **Ctrl+Q** to fully quit Codex after the parent confirms WAITING; stay out
until a result window appears. The new caption explicitly distinguishes
**Amadeus cleanup completed** from **Amadeus cleanup NOT completed**. Installed
app menu source and the official Windows shortcut reference confirm Ctrl+Q.
The fresh attempt also expires after thirty minutes; no automatic retry loop.

The daily source workspace is ready at `C:\Amadeus\repo`. Docker's same three
recorded containers are running with unchanged identities/images/mounts/restart
policies; local n8n health returned HTTP 200 at 18:25:30 UTC. Full cleanup is
not yet complete. Do not repeat the old instruction to quit and immediately
reopen Codex: it recreates watchers inside the original `.git` directories.

Latest handover: [restart cleanup status](receipts/20260919/AFTER_RESTART_CLEANUP_STATUS.md).
Previous phase: [maintenance cleanup status](receipts/20260919/MAINTENANCE_CLEANUP_STATUS.md).
Earlier phases: [final local cleanup](receipts/20260919/FINAL_LOCAL_CLEANUP_STATUS.md)
and [preserved checkpoint](receipts/20260919/WORKSPACE_CONSOLIDATION_CHECKPOINT.md).
Those dated failure/approval/restart records remain evidence; this fresh result
supersedes their current-action instructions. The
[active source map](../09-vault-brain/10-source-map/ACTIVE_DOCS_SOURCE_MAP.md)
selects doctrine. This register grants no business/provider/release authority.

## Current work and authority

Charl transferred sole coordination from task
`01a08bfa-ca70-7a01-91df-fc3dd3922598` on 2026-09-18 after verification PASS.
The former coordinator and source task `01a0b55a-6896-7643-b267-25cd4bcce5d7`
remain frozen for dispatch/release. The same current task owns local completion;
no mission identity, history, approval or existing hold has been discarded.

Charl approved consolidation, moving away from OneDrive, preservation before
obsolete-file deletion, and later **"Approve clean up."** for the six remaining
roots and bounded application/Docker/access maintenance. **"Approved do it so
I can get the window prompt"** renewed the native UAC attempt after its earlier
cancellation. No repeated cleanup/takeover approval is needed. No forced handle
closure, blanket ACL change, service retirement or application release is assigned.

| Workspace | Use | Current qualification |
| --- | --- | --- |
| `C:\Amadeus\repo` | Sole everyday source checkout | One registered worktree on the continuing local cleanup branch; saved project/current task route here |
| `C:\Amadeus\.runtime` | Temporary work, tests and evidence | Current phase `consolidation\maintenance-20260919\original-final-retention` |
| `C:\Amadeus\recovery\20260919` | Consolidated recovery | Bundles, encrypted snapshots, restore proofs and 556 intact retained roots preserved |

Prior removal remains **250,321 files and 12,741 empty directories**, totaling
15,537,781,090 logical bytes; physical savings are unmeasured. Earlier intact
retention preserved 543 roots, then eight noncurrent AGENTS roots and five tmp
roots: **556 retained roots**. This continuation deleted zero source objects.
The four pytest ownership classifications remain unverified; retain intact.
`C:\tmp` is empty. The original checkout is the sole old AGENTS entry.
The ignored private `.env` remains intact in the new checkout; its earlier
same-object, unchanged-content/security relocation proof remains authoritative
for that single file. No secret was printed, loaded or added to Git.

After the owner's restart, the original DELETE-open probe succeeded. An
independently reviewed UAC operation at 18:20:41 UTC performed a fresh full
audit matching the earlier proof, then its one handle-bound rename failed with
Win32 5 at 18:25:23 UTC. Source remains present; destination is absent.
The provider stripped Cloud metadata before rejecting the move. This was not
an unchanged-metadata failure: a new full read-only administrator audit at
18:31:10 UTC proved 172,892 objects, every stream/security/native identity and
one opaque junction unchanged under the defined Cloud-normalized digest;
zero Cloud entries remain. Exact root volume `17629920732283616668`, inode
`47850746040959140`, attributes 49, tag 0. No target traversal or ACL change.

Native readback identifies current `ChatGPT.exe` PID 27472, created
18:04:49.3122677 UTC, holding the root, `.git` and `.git\refs`. Eight isolated
synthetic cases show a second root handle permits the rename, while open
descendant directory/file handles cause the same Win32 5; the result holds
with the original readonly/deny-delete-child pattern. Changing ACLs is unnecessary.

A separately reviewed one-shot administrator helper is prepared to wait at
most 30 minutes for that exact app process to exit, require no Codex process
before auditing and immediately before rename, enforce ordinary native metadata,
repeat full baseline qualification, and perform one no-overwrite intact move
with full post-move verification. It never stops an app, changes permissions,
follows the embedded link, retries automatically, or starts operational work.
Its completion dialog is shown only after durable result writing and handle
release. Check its external launch receipt/journal to distinguish PREPARED,
WAITING, HELD, MOVED_UNCONFIRMED and RETAINED_VERIFIED; preparation is not success.

Docker restart initially failed on two inaccessible zero-byte runtime sockets.
After its verified error window closed gracefully and all Docker processes
exited, the exact two-entry runtime directory was retained intact in mission
runtime, same native identity. Docker regenerated its runtime sockets and
started. No image, volume, n8n data or configuration was removed or reset.
All four CHARLIE scheduled tasks remain disabled. No operational writer restart.

Startup canonical Git/common-directory guard passed at
`b0657ad6c7ac6b94b1c7255e858874568207401c`, tree
`ba60566d30cca1da84f3149921e5fa71690bef25`, one worktree, no upstream,
14 ahead/zero behind freshly fetched main
`e46743cb3e8d224b60d17eb5920acb113f613a52`. Governance/CORE pack is unchanged.
Current closeout commit/clean guard/bundle are recorded externally in
`after-restart-workspace-verification.json`; do not infer them from startup.

## Preservation and source checkpoints

- Source at final-task takeover:
  `487a8b4104baa9d45fbd036edac0d2d2ad1218fb` on
  `codex/workspace-consolidation-20260919`, clean, one worktree, no upstream,
  eleven ahead/zero behind `origin/main`. Startup/cleanliness guard passed.
  Final delivered commit/status belongs in external
  `C:\Amadeus\recovery\20260919\final-successor-workspace-verification.json`.
  The earlier `final-workspace-verification.json` remains unchanged.
- Main `e46743cb3e8d224b60d17eb5920acb113f613a52` was freshly confirmed
  at 09:35:56 SAST September 19. All cleanup changes remain local/unreleased.
  Keep the cleanup branch current until governed review/integration; worktrees
  from `origin/main` do not yet contain these changes.
- All 2,377 bundle heads were restored and checked, fsck PASS; 97 PR heads and
  62 historical worktree heads remain represented. Main/supplement stored
  objects and selected restore probes passed. Whole-root archive holds remain;
  archive PASS and intact retention are not blanket disposal/run authority.
- Bounded local suites passed: 61 guards, 26 archive, 6 workspace, 26 retirement,
  19 retention and 5 configuration-fallback tests. Broader initial result:
  302/332, with 30 offline-boundary failures retained; no full-suite green claim.
  Final-task native qualification: eight focused synthetic cases PASS plus
  independent exact-byte review and eight verified live intact moves. Existing
  retirement/retention guards were not weakened or changed.
- `preserved/desktop-record-20260918` at
  `c4b846cc86a63c98c0b83c2a1a1ad73a03afa5a0` retains complete coordination
  history in the [4,016-line register archive](../99-archive/control-tower/20260919/MISSION_REGISTER_THROUGH_20260918.md).
  Old counts of 59 inherited worktrees, 24 quarantines, four preservation refs
  and three later local checkouts are historical inventory, not current topology.

## OMQ checkpoint and admission hold

Existing mission `OMQ-20260813-03` remains open. Original candidate
`86bcee2709374353b7daf8d68bda839bac69337c`, tree
`8582052f2cab5bf1a7abc4d26c27ebb085c6e23b`, remains failed qualification and
unreleased; original tests and failures are preserved.

Charl separately approved local repair and exact draft publication.
Successor `deff39235adf357ab19ac971804addff1171188e`, tree
`618d4d933b3d127498b65bbb45c53b9aac7e6073`, is draft
[PR #1340](https://github.com/Crewless9086/amadeus-pig-tracking-system/pull/1340).
Local review and hosted application qualification passed on 2026-09-18;
three admission checks failed. It is **admission held, unmerged and not deployed**.

[Latest qualification receipt](receipts/20260918/PR1340_QUALIFICATION_RECEIPT.md)
and [exact admission diagnosis](receipts/20260918/PR1340_ADMISSION_DIAGNOSIS.md)
retain the observations. Canonical read-only evidence bound root OMQ admission
to old PR #1334/head `77227a67...` and
`OMQ-20260813-03-MORNING-CONTAINMENT` to old PR #1336/head `23130559...`.
Both old admissions were valid. The consumed prior release approval is a
separate preserved boundary. Neither authorizes PR #1340.

No supported truthful Desktop candidate-succession route was verified.
Do not repurpose the Hermes binding, same-PR invalidator or Slack pilot.
Admission writes, issuer/callback, publication beyond the completed exact draft,
merge and deployment remain held. Source and review workers from that phase are
released-retain; cleanup assignments do not reopen application source work.

## Operational holds carried forward

These are preserved boundaries and dated observations, not new runtime reads:

- Last recorded production readback on 2026-09-18 served
  `3d321e4932cf205d03e759cc71a26edd411bc9d2`. Repository migration does not deploy.
- Linda's saved 2026-08-22 litter must not be recreated or replayed. Her later
  question failed entity/context routing and Telegram delivery in executions
  71008/71009. First-answer and contextual-follow-up acceptance remain failed,
  not pending another owner fact.
- C Camp's 01:35 SAST deadline versus observed controller OFF at 02:04:24 remains
  unresolved. Controller readback time is not measured water duration or volume.
  Source wording/tests do not resolve the physical event.
- Scheduled-observer plan-hash evidence remains incomplete. Retained files do
  not prove a fresh monitor, active observer or autonomous continuity.
- Anton parity, ten HERDMASTER welfare/outcome cases, weaning, Molly first
  treatment, migration and permission gates retain their existing identities
  and boundaries. No treatment, dose, observation or farm completion is inferred.
- ROOTLINE device classes retain separate commissioning and standing-authority
  boundaries. Cleanup authorizes no hardware calls, physical tests or replay
  of earlier cards, confirmations or consumed release approvals.
- n8n remains the last recorded interim Telegram transport owner. Backend parity,
  confirmation, cancellation, readback, replay and no-loss/no-duplicate proof
  precede retirement. Native voice and provider publication remain held.
- The polling relay/watchdog was stopped/disabled in the dated handover. Its
  webhook-managed early-exit defect remains unresolved; do not restart it or
  infer current process state from that old observation.
- Supabase REST HTTP 402 `exceed_egress_quota` is the known REST limitation.
  Previously verified SQL reads used an explicitly read-only transaction.
  No repeated REST probing, billing, permission or database configuration change
  is assigned here.
- SAM sends, BEACON publication/spend, DOCUMENTS/Green delivery and all
  farm/payment/reservation/physical effects retain independent approvals/holds.
  No paid-model call or operational acceptance is assigned.

## Preserved mission pipeline

The complete identity-level queues and later addenda remain in
[register history](../99-archive/control-tower/20260919/MISSION_REGISTER_THROUGH_20260918.md).
None is discarded, renamed, closed or automatically runnable by this summary.

| Existing lineage | Preserved boundary after consolidation |
| --- | --- |
| `OMQ-20260813-03` and MORNING-CONTAINMENT | Exact admission contract/authority, then separate release and genuine deployed acceptance |
| OMQ context, family/Anton and natural health/loss/litter | Qualified context/delivery path before acceptance; no historical replay |
| `HMQ-20260813-00/02/03/04/05/06` and continuous husbandry | Preserve completed slices; reconcile welfare, treatment, weight, exposure and UI gates |
| `RMQ-20260813-02/03A/03B/04/05/06` | Independent Mixer, Injection control/flow, B/C, water-credit and borehole gates |
| `CMQ-20260813-02A/03/04/05` | Preserve parser, action-spine, retirement and governed-worker/Shadow holds; no automatic startup |
| `SMQ-20260813-01/02/03/04/05/06` | Context, genuine customer/payment evidence and pilot gates; no replay |
| `BMQ-20260813-00/01/02/03/04/05` | Preserve accepted slices/private media; separate owner/publication boundaries |
| `UIQ-20260813-01/02/03` | Preserve completed/unfinished work; fresh role/actionability/preview evidence |
| `DMQ-20260816-01` | Preserve Green print/migration/held-request evidence without assuming delivery |

**Current mission:** finish the last approved intact retention.
**Next gate:** after retry1 is confirmed WAITING, press Ctrl+Q to quit Codex and keep
it closed until the **Amadeus cleanup completed** or **NOT completed** window appears. Reopen this same
task in `C:\Amadeus\repo` and read the exact helper result, independently verify
source absence/destination identity and preservation, then update the final
source/evidence closeout. If the helper expires or fails, preserve the result;
there is no automatic retry. No new cleanup permission is required.

**Later pipeline:** keep the continuing cleanup branch for local work. Govern
review/integration before operational continuation. Existing mission priority,
collision, canonical binding, terminal and authority gates still apply.
No release or deployed business outcome follows from workspace cleanup.