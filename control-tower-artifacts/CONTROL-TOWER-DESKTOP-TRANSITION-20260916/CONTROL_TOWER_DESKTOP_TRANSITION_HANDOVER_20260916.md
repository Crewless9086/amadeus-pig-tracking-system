# Control Tower desktop transition handover

Lifecycle: `active` current-state handover and reconciliation evidence. It is not
reusable doctrine and grants no runtime or release authority.

## Identity and exact starting point

- Existing Control Tower session/thread: `01a08bfa-ca70-7a01-91df-fc3dd3922598`.
- Prepared successor identity:
  `CONTROL-TOWER-DESKTOP-SUCCESSOR-20260916`.
- Exact desktop folder: `C:\tmp\amadeus-herd-control-20260910`.
- Authoritative mission branch:
  `control-tower/herd-operations-20260910`.
- Reconciliation started from clean published HEAD and upstream
  `fbcb78611dea6280ced120eaf7f600d1c31f7f57`. No newer remote commit existed at
  intake.
- At intake the branch was 32 commits unique to the mission line and 28 commits
  behind `origin/main`; neither was an ancestor of the other. This branch is the
  current documentation/handover authority. It is not the application release
  branch and must not be merged or rebased merely to make the graph look tidy.
- Fresh `origin/main`, PR #1336 merge, and live production revision are all
  `3d321e4932cf205d03e759cc71a26edd411bc9d2`. The live
  `/health/revision` read returned `identity_complete:true` on 2026-09-16.

The exact existing Codex session is not proven portable into ChatGPT desktop.
Windows Codex uses the native `%USERPROFILE%\.codex` configuration area, but
session visibility and every connector/permission must be verified in the
desktop app. The prepared desktop session is therefore a successor linked to
the session and branch above. It must remain read-only until the transfer gate
below passes.

## Governance preflight and instruction discovery

The source map selected and this reconciliation read the complete current
Mission Standard, Control Tower Protocol, Runtime Programme and the relevant
handover contract. Exact preflight:

| File | Git blob | SHA-256 | Physical lines |
| --- | --- | --- | ---: |
| `docs/09-vault-brain/00-governance/AGENTIC_OPERATING_MISSION_STANDARD.md` | `3002b94713e286c4eb2019419c438cc378c337fa` | `44E34C69145B83D2CD5B6A5322A6C2C124789FA647E19F19B3E39A7293A5202B` | 1,127 |
| `docs/09-vault-brain/00-governance/CONTROL_TOWER_ASSESSMENT_AND_DISPATCH_PROTOCOL.md` | `8fbd0b9c9160164e31a17a2cbfa51ab88792a909` | `D4EB4B54A660CE39DFC92CB0FA253B0F2E3D7314462984702602D0F4B66A7E0A` | 319 |
| `docs/01-architecture/AGENTIC_FARM_RUNTIME_PROGRAMME.md` | `fb44d7f86c47e605c283ed33c28ba2c4267d6edb` | `721281EEACC33AE11877CE610FE7A76BA06DE6B75DB4573F64933073FD358309` | 278 |

The mandatory common pack, CORE/Control Tower focused pack, document lifecycle,
source-of-truth rules and `CONTROL_TOWER_FEEDBACK_HANDOVER_TEMPLATE.md` were also
read. The repository contained `CLAUDE.md`, a non-doctrine pointer, but no root
or nested `AGENTS.md` and no global `%USERPROFILE%\.codex\AGENTS.md` or
`AGENTS.override.md`. Codex therefore had no repository `AGENTS.md` route to
load automatically. This reconciliation adds one small root pointer. It directs
Codex to the active source map and current handover without copying doctrine into
a competing memory pack.

## Repository, worktrees, branches and pull requests

The read-only inventory found 628 registered worktrees; all 628 paths exist.
Fifty-two contain local changes and 34 are ahead of their configured upstream.
Registration, a dirty tree, or an ahead commit is preservation evidence and is
not proof that a worker is active. The full compact inventory is
`REGISTERED_WORKTREES_SUMMARY_20260916.json` beside this handover.

Unique current work that must remain in place includes:

- the main workspace at
  `C:\Users\charl\OneDrive\1. Amadeus\AGENTS\amadeus-pig-tracking-system`,
  branch `preserve/main-workspace-reconciliation-20260812`, HEAD
  `b88ae99d4daa02113f6a3ba1975a7fdc362844c1`, with changed governance/UI files,
  `static/js/matings.js`, `templates/matings.html`, a staged PR #1167 handover,
  and untracked HMQ evidence;
- the Oom Sakkie candidate at `C:\tmp\omq-farm-brief-20260916`, branch
  `fix/oom-farm-brief-followthrough-20260916`, commit
  `86bcee2709374353b7daf8d68bda839bac69337c`, tree
  `8582052f2cab5bf1a7abc4d26c27ebb085c6e23b`, plus its two untracked
  qualification logs;
- the CORE/CHARLIE worktree
  `.w\pr1331-render-hermes-install`, branch
  `fix/render-hermes-installer-c8f8bee`, HEAD
  `55275c885fd5eca03529a919f48182a27128ebb0`, with 44 later local changes even
  though PR #1331 itself merged; and
- retained HERDMASTER, ROOTLINE, GREEN, SAM, BEACON and CODEX UI worktrees and
  evidence listed in the inventory. None was reset, stashed, moved, cleaned,
  merged or reclassified as complete.

GitHub showed 96 open pull requests. Their newest update was 2026-08-26 and open
state alone does not establish current priority or approval. PR #1303 remains a
draft continuity canary. PR #1336 is merged and closed. No PR represents local
candidate `86bcee...`. The exact open list is
`OPEN_PULL_REQUESTS_SUMMARY_20260916.json`.

## Canonical queue and process reality

A fresh read-only canonical mission query succeeded. Counts were: 1 approved,
3 blocked, 64 deployed, 77 done, 7 in progress, 7 merged, 56 new, 30 paused,
1 PR-ready and 129 rejected. The 91 nonterminal rows include old recovery and
outcome backlog; a status such as `new` does not by itself promote work. The
sanitized row snapshot is `CANONICAL_MISSION_QUEUE_20260916.json`.

No current release or deployment operator was found. The CORE Always-On and CORE
Runner Watchdog scheduled tasks are disabled. The local CHARLIE Telegram relay
has one launcher/child process chain and its watchdog task is Ready; it depends
on this Windows machine, not this Control Tower chat. CORE execution autonomy is
not proved.

The Linda watcher is one launcher/child process chain (PIDs 30340/42224 at the
snapshot), started at 16:24 SAST with a 90-minute bounded window. It writes
read-only execution metadata to
`C:\Users\charl\OneDrive\1. Amadeus\AGENTS\amadeus-pig-tracking-system\.tmp\control-tower-oom-cca-approved-release-20260914\LIVE_TELEGRAM_ACCEPTANCE_WATCH.json`.
It already captured the first question pair and must not be duplicated. It will
end on its own; it is independent of the old terminal window but not of the
local machine staying on.

## Owner lanes and exact continuation

| Owner | Intended owner-visible result | Current implementation and operational truth | Owner/location and next eligible action | Approval, hold and evidence |
| --- | --- | --- | --- | --- |
| CORE / CHARLIE | Terminal-independent governed intake, execution, review and release supervision | PRs #1315 and #1331 merged historically. The canonical Slack gateway row is approved, but the main CORE watchdogs are disabled and no fresh mission heartbeat proves autonomous pickup. The dirty post-merge worktree is unreviewed local work. | CORE/Control Tower owns `.w\pr1331-render-hermes-install`. Preserve it. Before any dispatch, obtain a fresh exact-worktree handover and collision review; do not infer that the 44 files are approved or loaded. | CHARLIE commissioning, migration and permission holds remain. Canonical queue and process snapshot are fresh 2026-09-16. |
| OOM SAKKIE | Natural English/Afrikaans farm conversation, saved-record answers, confirmed permitted updates, useful plans and follow-through | Production serves PR #1336 merge `3d321...`. Model probe passed once. Reply-ID field is published. Morning brief delivery to Charl is proved; Anton acceptance and farm writes are not. Linda's real question reached the backend but failed entity routing and has no proved Telegram answer delivery. | Backend owner remains Oom Sakkie; n8n GateKeeper remains interim transport owner. Diagnose Linda routing and one safe reply-delivery path, then qualify under the existing mission. Candidate `86bcee...` stays in `C:\tmp\omq-farm-brief-20260916`. | No new runtime/transport authority. Exact evidence: this handover, `LINDA_LIVE_ACCEPTANCE_20260916.json`, and both current 9/16 OOM documents. |
| HERDMASTER | Mortality, weaning, first treatment and the ten welfare/outcome cases close from real evidence with canonical readback | Mortality capability is deployed; prior Linda farrowing and tag-138 mortality effects were saved once and must not be retried. Genuine current confirmation/cancellation and a permitted new update remain unproved. The ten P1 cases retain their identities. Two deaths are canonical; other closures need real observations or protected previews. | Existing HERDMASTER owners retain `HERDMASTER-NATURAL-HEALTH-LOSS-1`, `HMQ-20260813-05`, the clean Molly worktree `.w\molly-first-treatment-current`, and the dirty welfare worktree `.worktrees\herdmaster-health-loss-welfare-language-20260822`. Next farm facts are fresh observations for pig 146, Linda, Waki, Teena and Prince, with exact protected paths only where a record is genuinely missing. | Weaning, first-treatment, permission and physical-operation holds remain. See `HERDMASTER_P1_CANONICAL_RECONCILIATION_20260915.md`; priority annotations are not farm work. |
| ROOTLINE | Safe irrigation with concise verified ON/OFF messages, useful morning summary, visible exceptions and verified final OFF | Canonical mission `RMQ-20260813-04` is paused. C Camp is verified ON 00:35:16 and OFF 02:04:24 SAST, but missed its 01:35 stop deadline. Flow duration/volume is unproved. Six routine reassessment messages were noise. | ROOTLINE retains the physical/control lane and dirty standing-authority worktree. Candidate review may quiet routine messages only after proving that missed deadlines and unverified shutdown remain visible. Observe the next natural evidence; do not operate hardware. | ROOTLINE and physical holds remain. The timing discrepancy is unresolved. Candidate `86bcee...` has no named regression for this condition yet, so that independent review gate is open. |
| SAM | One genuine attributed customer journey with correct stock truth, response, confirmation and follow-up | Canonical `SMQ-20260813-06` is paused. The retained 194 SAM backlog rows are not new owner work. No fresh attributed inbound or current worker process was proved in this reconciliation. | SAM remains dependency-idle until a genuine attributed inbound and current provider evidence exist; then continue the same mission. | Customer send, price/payment and availability controls remain. Open historical PRs are evidence, not current authority. |
| BEACON | One protected publication and measured provider/customer outcome | Canonical `BMQ-20260813-05` says in progress, but this reconciliation found no fresh provider publication or active local worker. | BEACON is event-waiting on the next genuine protected decision/publication cycle; refresh provider evidence before treating the old queue row as active execution. | Publication, media/privacy and spend approvals remain. No provider call was made here. |
| CODEX UI | Owner-visible farm screens that match canonical facts and protected capability | No fresh active CODEX UI worker was found. The main workspace preserves unique matings UI and standards edits; many historical UI worktrees remain registered. | Keep dependency-idle. First reconcile the exact main-workspace diff and owning farm outcome before assigning a continuation. | No merge, relocation or cleanup. UI work cannot bypass farm, permission or release holds. |
| Documents / GREEN / other retained work | Preserve reviewed documents and safely commissioned supporting capabilities | Numerous retained worktrees and old PRs exist. No active process or new current owner result was proved. | Preserve under existing identities and revisit only from their recorded wake condition. | Migration, device, printer, physical and publication holds do not change through this transition. |

## Current Oom Sakkie and farm evidence

The required current documents remain published and are part of this handover:

- `control-tower-artifacts/OMQ-20260813-03/OOM_SCHEDULED_OBSERVER_AND_FARM_BRIEF_CORRECTION_HANDOVER_20260916.md`;
- `control-tower-artifacts/OMQ-20260813-03/OOM_FARM_BRIEF_RUNTIME_CANDIDATE_DECISION_20260916.md`.

The morning observer proved Charl's brief delivery and improved wording. It did
not prove Anton acceptance or any farm update. The observer's plan-hash verifier
remains incomplete because its collected object lacked `why`; provider delivery
and saved lifecycle evidence do not remove that limitation.

Backend reconciliation found that 74 is the current eligible/tagged snapshot,
not a weighing worklist, and zero pigs are explicitly due now. The mortality
archive contains 42 attributable historical candidate events and none in the
last seven days; unchanged archive totals are not morning work. Mysikind and Mona
remain separate outcomes.

Candidate `86bcee...` passed a fresh 272-test/27-subtest herd run after the
retained 271-pass attempt. It is implemented locally and qualified for the
documented selection, but it is neither approved, published, hosted-qualified,
merged nor deployed. Its exact rollback target remains deployed `3d321...`.
Independent review must additionally verify that overdue shutdown and
unverified OFF conditions remain owner-visible when routine reassessments are
silenced. This transition grants no runtime release authority.

Linda's genuine first question was execution `71008`, with relay `71009`, at
16:27 SAST. The backend used `owner_context_front_door` and asked which category
the item concerned, rather than retrieving Linda's saved litter. The expected
saved result is the 2026-08-22 litter: 9 total, 8 born alive, 0 stillborn, 1
mummified and 8 active on-farm piglets. Relay validation returned
`send_allowed:false`, GateKeeper ended at the subworkflow call, and no Telegram
send node or provider delivery evidence followed. The first answer therefore
failed both record and delivery acceptance. No natural follow-up is expected
until a useful first answer is actually delivered; none has been observed.

## Backend Telegram replacement and n8n retirement

The backend owns business interpretation and farm records. The implemented
replacement endpoint is
`POST /api/oom-sakkie/channels/telegram/direct-webhook`; its five exact Render
inputs were previously verified configured and local provider-parity checks
passed for three allowed owners with writes, dispatch and physical controls
false. The remaining live owner is n8n GateKeeper `s8QaxmqT69Z5mhvE`, calling
relay `TlKy9kUgJJE0msU4`. The scoped reply-ID change is published in relay version
`84decfbb-62a9-4298-b9c6-f927dd4b59e4`; the three native-voice changes remain
held.

Retirement still requires sole backend webhook ownership, successful ordinary
English/Afrikaans replies, generic protected confirmation/cancellation parity,
persistent task/reminder/project memory or an explicit bounded disposition, one
genuine permitted update with canonical readback, zero-effect cancellation and
replay, operation with n8n unavailable, and reversible no-loss/no-duplicate
observation. The Linda execution adds a concrete missing reply-delivery path.
Interim repair must remain transport-only; it may add no n8n business logic.

## Approvals and holds carried forward

- PR #1336 release authority has been consumed and completed. It does not cover
  another runtime or transport change.
- Local candidate `86bcee2709374353b7daf8d68bda839bac69337c`, tree
  `8582052f2cab5bf1a7abc4d26c27ebb085c6e23b`, requires an exact runtime decision
  after the additional shutdown-visibility review. The earlier fixture-only
  successor permission does not authorize it.
- The scoped reply-ID publication is complete. No other n8n transport or native
  voice publication is authorized.
- The corrected model probe succeeded once and must not be repeated as a generic
  health check. Bounded model/transcription calls remain limited to actual
  acceptance under existing providers and spending controls.
- Historical callback executions 66743 and 66840 saved once and must not be
  retried; 66837 was denied with no write.
- Migration, weaning, first-treatment, native voice, permission, physical
  operation, ROOTLINE and CHARLIE holds all remain unchanged.

## Desktop verification and exclusive transfer gate

The desktop successor may verify files, Git, provider readbacks and tool access
read-only. It may not edit, commit, push, dispatch, merge, deploy, publish a
workflow, call a paid model, write a farm record or operate hardware during this
phase.

After a `DESKTOP VERIFICATION PASS`, Charl must explicitly transfer coordinating
ownership to `CONTROL-TOWER-DESKTOP-SUCCESSOR-20260916`. At that moment this
session stops dispatch and release-lane work. The successor records an
append-only transfer receipt on this branch before dispatching. Until that
explicit transfer, session `01a08bfa-ca70-7a01-91df-fc3dd3922598` remains the
coordinating owner. This prevents both sessions from operating the release lane.

The old terminal window itself owns no deployed service. Closing it ends this
interactive coordinator. Production web, n8n, scheduled provider services, the
CHARLIE relay watchdog and canonical queues continue independently according to
their actual provider/task state. The bounded Linda watcher continues only while
its local process and this machine remain alive, and then exits automatically.

## Exact desktop verification prompt

> You are `CONTROL-TOWER-DESKTOP-SUCCESSOR-20260916` in read-only verification
> mode. Open exactly `C:\tmp\amadeus-herd-control-20260910`. Do not edit, commit,
> push, dispatch, merge, deploy, publish provider/workflow changes, call a paid
> model, write farm/database state, change permissions or operate hardware.
> First report the active Codex instruction files. Verify the folder, branch
> `control-tower/herd-operations-20260910`, HEAD, upstream and ahead/behind state,
> and fetch/read current `origin/main` without changing the worktree. Read root
> `AGENTS.md`, `docs/09-vault-brain/10-source-map/ACTIVE_DOCS_SOURCE_MAP.md`, the
> complete Mission Standard, Control Tower Protocol, Agentic Farm Runtime
> Programme, `docs/06-operations/CONTROL_TOWER_FEEDBACK_HANDOVER_TEMPLATE.md`,
> `docs/06-operations/CONTROL_TOWER_MISSION_REGISTER.md`, and
> `control-tower-artifacts/CONTROL-TOWER-DESKTOP-TRANSITION-20260916/CONTROL_TOWER_DESKTOP_TRANSITION_HANDOVER_20260916.md`.
> Verify that the handover links both September 16 Oom Sakkie documents, candidate
> `86bcee2709374353b7daf8d68bda839bac69337c` with tree
> `8582052f2cab5bf1a7abc4d26c27ebb085c6e23b`, the Linda failure evidence, the
> worktree/PR/queue inventories and all holds. Check only whether filesystem/Git,
> GitHub CLI, production revision readback, and the already-configured read-only
> n8n/Supabase/Render access are available; reveal no secret values and make no
> provider mutation. Return `DESKTOP VERIFICATION PASS` or `DESKTOP VERIFICATION
> FAIL` with exact mismatches and inaccessible evidence. State explicitly that
> coordinating ownership has not transferred and perform no continuation work.

## Control Tower check receipt

- Decision: `YES` — repository-backed desktop successor preparation is complete;
  operating and business missions remain `WORKING` under their existing owners.
- Business result: `NO NEW BUSINESS OUTCOME`. The current visible capabilities
  are deployed PR #1336, Charl's delivered morning brief, saved prior protected
  effects, and the published reply-ID field. Linda acceptance newly failed as
  recorded; Anton and farm-update acceptance remain open.
- Evidence time: repository/GitHub/queue/process/provider reads on 2026-09-16
  between 16:22 and 16:48 SAST.
- Effects: documentation and indexes only on the mission branch. No application,
  migration, workflow, selector, permission, production, provider, farm record,
  customer, payment or physical effect.
- Next safe stage: desktop read-only verification, followed by explicit ownership
  transfer. Runtime candidate review and operational acceptance remain separate.
- Detailed machine receipt: `CONTROL_TOWER_RECONCILIATION_RECEIPT_20260916.json`.

ACTION REQUIRED NOW: Open `C:\tmp\amadeus-herd-control-20260910` in Codex desktop
and paste the exact read-only verification prompt above; do not transfer ownership
until it reports `DESKTOP VERIFICATION PASS`.
