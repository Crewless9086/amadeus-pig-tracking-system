# Repository Consolidation And Desktop Handover — 2026-09-18

Status: reviewed documentation candidate for the existing Control Tower mission.
It becomes the current repository handover only when this documentation-only
change reaches `main`. It grants no application release, deployment, provider,
database, farm-write, permission or physical-operation authority.

## Result and canonical route

The original repository folder is the canonical Desktop entry point:

`C:\Users\charl\OneDrive\1. Amadeus\AGENTS\amadeus-pig-tracking-system`

The final gate for this mission is that this folder is clean, on local branch
`main`, and exactly aligned with published `origin/main`. The root `AGENTS.md`
then routes Codex to the active source map and this handover. The previous
Control Tower folder `C:\tmp\amadeus-herd-control-20260910` remains retained as
historical evidence until Desktop verification passes; it is no longer the
intended desktop entry point.

The active source map remains byte-identical to the protected base revision,
where it already names the mission register as the current-state route. The
root `AGENTS.md` points to that map and register, and the register points to
this dated handover. This keeps transient mission state out of the doctrine
map while preserving a complete, deterministic route from Desktop startup.

The repository was fragmented because Git worktrees are complete working
directories attached to one shared repository. The original folder did not
automatically contain dirty files, uncommitted evidence or branch commits held
in another worktree. `main` held released application history, while the
Control Tower branch held newer mission documentation and dozens of other
worktrees held unfinished local work. This reconciliation preserves those
layers and restores one clear entry route without pretending that unfinished
work was released.

## Preservation completed before cleanup

- A complete verified Git bundle captured 2,926 refs before consolidation:
  `C:\Users\charl\OneDrive\1. Amadeus\AGENTS\amadeus-pig-tracking-system\.tmp\repository-consolidation-20260917\AMADEUS_ALL_REFS_BEFORE_CONSOLIDATION_20260917.bundle`,
  SHA-256 `3560B842D7C29FBED0701711876B89AA205A2BE12EC94BDA51945F9AD7A6EDD3`.
- Every then-dirty worktree was backed up with tracked patches and all 3,383
  untracked files. The local archive set contains 95,565,930 bytes; tracked
  patches contain 806,057 bytes.
- Remote branch `recovery/repository-consolidation-20260917` at
  `eddffc8eb3de98f007897ad4be68c2332e2571f0` anchors all commits that were not
  previously reachable from an origin ref.
- Remote branch `recovery/dirty-worktree-patches-20260917` at
  `72e87beb580e6e370d0aec7eebbefc81d38c451a` preserves the tracked dirty patches.
- Remote branch `recovery/safe-untracked-source-20260917` at
  `76e5d71a2aa3293c3318f56a4a3426ee586ff990` preserves 103 reviewed source,
  document, test, migration and log files. Private/generated/large files remain
  in the verified local archives.
- The original workspace's unique evidence and unfinished matings UI were
  preserved on `preserve/main-workspace-reconciliation-20260812` at
  `03750847880bf1f110da48f3c2d77f520f019ea4`. The UI remains WIP because its
  referenced CSS/navigation dependencies are absent; it was not promoted to
  application `main`.
- Secret scans found no credential-bearing recovery material. Placeholder test
  database URLs were classified explicitly.

Exact hashes and paths are in `PRESERVATION_CHECKPOINTS_20260918.json` beside
this handover.

## Worktree cleanup and remaining topology

The starting inventory contained 628 registered worktrees: 52 dirty, 34 ahead
of upstream and 186 with no upstream. All 628 paths existed. Cleanup considered
only the 570 clean historical candidates after retaining current coordinator,
runtime and owner worktrees.

Before removal, 81 ignored evidence files were archived and hash-verified. One
ignored GREEN handover appears in the OneDrive directory index but cannot be
opened. Its worktree remains registered and untouched.

Five hundred sixty-nine clean historical worktrees were unregistered after
their HEAD, remote preservation and fresh tracked status passed. ACL-protected
residue from 24 worktrees was moved intact to
`C:\tmp\amadeus-worktree-quarantine-20260917`; no quarantine directory is a Git
worktree. The mapping back to original path, branch and HEAD is in
`WORKTREE_QUARANTINE_MANIFEST_20260918.json`. No dirty or current worktree was
deleted to make the graph look tidy.

The fresh post-cleanup inventory at 2026-09-18T01:41:09Z contains 59 registered
worktrees, all present: 51 dirty and 8 clean. `REMAINING_WORKTREE_DISPOSITION_20260918.json`
names every path, branch, HEAD, change count, upstream state and retention class.
The important retained locations are:

- Oom Sakkie runtime candidate: `C:\tmp\omq-farm-brief-20260916`, exact commit
  `86bcee2709374353b7daf8d68bda839bac69337c`, tree
  `8582052f2cab5bf1a7abc4d26c27ebb085c6e23b`;
- CORE reconciliation: `C:\tmp\core-mission-reconciliation`;
- retained CORE/CHARLIE local work: `.w\pr1331-render-hermes-install`;
- HERDMASTER: `C:\tmp\herdmaster-litter-treatment-telegram-parity-20260825`,
  `.w\molly-first-treatment-current`, and
  `.worktrees\herdmaster-health-loss-welfare-language-20260822`;
- ROOTLINE: `.codex-runtime\missions\RMQ-20260813-04\notification-worktree`,
  `.codex-runtime\missions\ROOTLINE-OWNER-AUTHORITY\worktree`, and
  `.codex-runtime\missions\ROOTLINE-STANDING-AUTHORITY\worktree`;
- SAM retained loop: `C:\tmp\sam-always-on-inbox-loop`;
- local relay/runtime support: the three `.charlie_runner` worktrees; and
- GREEN evidence hold:
  `.codex-runtime\missions\GREEN-0.3.6-PARTIAL-RECOVERY\worktree`.

Other dirty worktrees remain under their existing task identities. They are
classified as unfinished CORE, HERDMASTER, ROOTLINE, GREEN, SAM, CODEX UI or
owner-disposition work. Their preservation is not a claim that a process is
active or a mission is approved.

## Branches and pull requests

The former divergent local `main` was renamed, without deleting its history, to
`archive/local-main-diverged-20260917`. Its unique commits are also reachable
through the recovery anchor. A clean publisher worktree was created on
`consolidation/docs-governance-20260917` from exact `origin/main`
`3d321e4932cf205d03e759cc71a26edd411bc9d2`.

GitHub still reports 96 open pull requests. All 96 head objects are present
locally; none is an ancestor of current `origin/main`, and none has the same tree
as current `origin/main`. They were not closed merely because they are old.
`OPEN_PR_RECONCILIATION_20260918.json` records every exact head and the required
mission-review disposition. The first PR #1337 candidate, exact head
`e96718c225fcb64fbab2612c06e30c11a756df6d`, was admitted as receipt
`MAR-83C40F97437ADEA672BFF4F7EA60B2AFF007E15332197EFB3DAA4FB5E82FEBB1` but
the protected App verifier correctly rejected its direct source-map edit as
`admission_governance_changed`. That exact failed attempt and delivery history
remain preserved. The successor restores the protected source-map blob
`70db4bc29d17b7ec6e89be52c304668d398d245c`; no gate is bypassed. PR #1336 is
separately confirmed merged at
`3d321e4932cf205d03e759cc71a26edd411bc9d2`; PR #1331 is separately confirmed
merged at `cd2ff4acc398eb134050b843c012e3bebb662989` while its later dirty local
work remains retained.

## Operational reality carried forward

- Production was last freshly proved on 2026-09-16 at exact PR #1336 merge
  `3d321e4932cf205d03e759cc71a26edd411bc9d2`. This repository cleanup does not
  claim a newer deployment.
- Charl received the morning brief. That proves delivery and improved wording;
  it does not prove Anton acceptance or a farm update.
- Linda's genuine question reached executions 71008/71009, but the backend asked
  a generic category instead of reading her saved 2026-08-22 litter, and no
  Telegram delivery followed. The first answer and contextual follow-up remain
  failed acceptance, not pending owner input.
- Candidate `86bcee...` remains local and unpublished. Its 272-test/27-subtest
  result does not close the missing shutdown-visibility regression, the C Camp
  01:35 SAST deadline versus 02:04:24 OFF discrepancy, or the scheduled
  observer's incomplete plan-hash verification.
- The backend Telegram endpoint remains the n8n replacement direction. n8n is
  still the interim live transport owner. The reply-ID field publication is
  complete; native-voice changes are separate and held.
- The current process inventory found one legacy local CHARLIE Telegram
  polling process, PID 3420, loaded from the preserved original-folder
  branch. Fresh current-`main` configuration validation returns
  `webhook_managed / local_polling_disabled`. The canonical-folder cutover
  therefore retires PID 3420 and verifies that the current-main entry point
  exits normally without leaving a local poller. No Linda watcher or
  release/deployment operator was found. Production services, the existing
  remote Telegram webhook, n8n and remote schedulers continue according to
  their provider state.

## Current priorities and holds

1. Qualify and decide the retained Oom Sakkie farm-brief candidate, including
   missed-shutdown/unverified-OFF visibility. Do not infer release authority.
2. Repair Linda's backend entity routing and delivered reply path, then repeat a
   genuine read-only question only when the path is qualified.
3. Continue the ten HERDMASTER welfare/outcome cases from canonical evidence;
   request fresh physical observations only where the named case requires one.
4. Preserve weaning, first-treatment, migration, permission, native-voice,
   physical-operation, ROOTLINE and CHARLIE holds. A preview or observation is
   not a completed farm operation.
5. Continue concise verified irrigation ON/OFF messages and a useful morning
   summary while keeping missed deadlines and unverified shutdown visible.
6. Retire n8n only after the documented backend parity, confirmation,
   cancellation, readback, replay and no-loss/no-duplicate conditions pass.

Open PRs, dirty worktrees and queue rows do not create priority or authority.
The detailed mission identities and wake conditions remain in
`docs/06-operations/CONTROL_TOWER_MISSION_REGISTER.md`.

## Tools and continuity

- Filesystem and Git access: verified.
- GitHub CLI read access: verified; 96 open PRs read on 2026-09-18.
- Local Windows process readback: verified; one Telegram relay found.
- Production, Render, Supabase and n8n read access: not re-proved by this cleanup.
  Desktop must verify each needed connector without revealing secret values.
- No credential or secret value is stored in this handover.
- Closing the old terminal ends this coordinating chat only. After the
  canonical cutover, no local polling relay should remain because current
  configuration delegates transport to the remote webhook. Remote services
  continue independently. No current local Linda watcher was found to
  transfer.

Existing coordinating identity `01a08bfa-ca70-7a01-91df-fc3dd3922598` remains
owner until Desktop verification passes and Charl explicitly transfers
coordination. Desktop must not dispatch, merge, deploy, publish or operate the
release lane before that transfer, so two coordinators cannot act concurrently.

## Desktop read-only verification prompt

> You are `CONTROL-TOWER-DESKTOP-SUCCESSOR-20260918` in read-only verification
> mode. Open exactly
> `C:\Users\charl\OneDrive\1. Amadeus\AGENTS\amadeus-pig-tracking-system`.
> Do not edit, commit, push, dispatch, merge, deploy, publish workflows, call a
> paid model, write farm/database state, change permissions or operate hardware.
> Report the repository instruction files Codex loaded. Verify that this folder
> is on branch `main`, clean, and exactly aligned with current `origin/main`.
> Read root `AGENTS.md`,
> `docs/09-vault-brain/10-source-map/ACTIVE_DOCS_SOURCE_MAP.md`, the complete
> Mission Standard, Control Tower Assessment and Dispatch Protocol, Agentic Farm
> Runtime Programme, `docs/06-operations/CONTROL_TOWER_MISSION_REGISTER.md`, and
> `control-tower-artifacts/REPOSITORY-CONSOLIDATION-20260918/REPOSITORY_CONSOLIDATION_AND_DESKTOP_HANDOVER_20260918.md`.
> Verify the preservation refs, 59-worktree disposition, quarantine mapping,
> 96-PR reconciliation, exact Oom candidate, Linda failure, C Camp discrepancy,
> incomplete plan-hash evidence, approvals and holds. Check read-only access to
> GitHub and only the provider connections needed for continuation; reveal no
> secrets and make no external change. Return `DESKTOP VERIFICATION PASS` or
> `DESKTOP VERIFICATION FAIL` with exact mismatches. State that coordinating
> ownership has not transferred and do no continuation work.

## Control Tower receipt

- Decision: `RECONCILIATION COMPLETE`, subject only to the mechanical canonical
  folder switch and documentation publication gate recorded in the machine
  receipt.
- Repository result: every pre-cleanup commit and dirty worktree is preserved;
  the active registry is reduced from 628 to 59 without deleting unfinished
  dirty work; the original folder is the designated canonical Desktop route.
- Business result: `NO NEW FARM OR CUSTOMER OUTCOME`. Deployed Oom Sakkie and
  existing operational evidence are reported separately from failed Linda,
  pending model/transport acceptance and unpublished candidate work.
- Effects: repository preservation, clean historical-worktree cleanup,
  quarantine and documentation only. No application code, migration, selector,
  workflow, provider, database, farm, payment, customer or physical effect.
- Evidence: the JSON records beside this handover and the local verified backup
  directory named above.
