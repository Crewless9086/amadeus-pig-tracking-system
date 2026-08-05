# CHARLIE CORE controlled T1 integration handover

Status: source-only and unsigned. This handover authorizes no merge, migration,
queue write, release, pickup, worker dispatch, runtime action or deployment.

## Exact integration sequence

The mission-start stable base is `a22e1f8d115e535019d7a86ceff623e6c161d9ea`.
PR #680 followed by PR #693 applies cleanly to that base. The only overlapping
files are the additive implementation source map and mission-store tests; the
normal sequence resolves both without a content conflict. The successor branch
exists because integration found one reusable gap: pickup acknowledgement did
not verify that the worker's role was selected by the scored plan.

PR #700 is now rebased onto `2be4d08a93b7661af6db19b375d45920ca8ea90e`,
after PRs #709 and #710. Those changes remain inherited unchanged: the PR diff
contains no Oom Sakkie, ROOTLINE, HERDMASTER, SAM or BEACON file.

## Readiness result

Already complete in source:

- #680 provides deterministic atomic replacement while keeping successors
  paused and predecessors excluded from pickup;
- #693 provides bounded scoring, minimum sufficient role selection and separate
  proposal, authorization, release, acknowledgement, start and completion;
- #700 binds acknowledgement to a selected worker role, enforces the declared
  completion artifact and preserves restart artifact lineage;
- the unsigned T1 proposal deterministically scores `12/72`, selects T1 and one
  `builder`; no legacy mission or farm message enters this path.

One capability remains genuinely missing: `development_coordination.py` is a
pure contract and is not called by authoritative mission intake, mission-store
events or pickup. A later bounded CORE capability mission must add one adapter
through the existing mission store/event ledger that durably freezes the plan,
records exact owner authorization, exposes only the authorized mission to direct
pickup, and persists acknowledgement, progress and completion facts. It must not
add a queue, dispatcher, broad-pickup mode or ordinary farm-message route. Until
that adapter passes disposable-PostgreSQL and restart tests, the runner stays
stopped and the T1 proposal remains unsigned and uninserted.

After review, the controlled sequence is:

1. merge this successor normally only after #680 and #693 are resolved by the
   owner; do not separately duplicate their commits;
2. require exact-merge CI for CORE, disposable PostgreSQL audit rails and the
   browser behavior gate;
3. verify migration `202608020001_create_charlie_many_to_one_replacements.sql`
   is present but do not apply it without separate migration authorization;
4. prove broad pickup is still disabled and the authoritative runnable query is
   empty;
5. re-read all 86 legacy missions and the T0 canary, proving none is runnable;
6. prepare the exact T1 proposal from
   `contracts/CORE_T1_POST_P0_HANDOVER_CORRECTION_PROPOSAL.json`;
7. Charl or private CHARLIE separately signs and authorizes that exact contract;
8. after the missing mission-store adapter is separately reviewed and
   integrated, release that mission only and accept one durable acknowledgement from the
   selected `builder`, then accept the matching start receipt;
9. require the declared one-file completion artifact and prove zero unrelated
   pickup before reporting completion to Charl.

Proposal, authorization, release, acknowledgement and start are five separate
append-only facts. A release is never displayed as pickup. Charl sees the plan
ID, score `12/72`, tier T1, selected role `builder`, current state, receipt or
single timeout exception, exact artifact revision, business outcome and next
dependency. CHARLIE receives the same durable facts and returns one concise
result; no terminal-to-terminal prompt relay is part of the contract.

Visibility is event-backed: `proposed` shows score and frozen agents;
`owner_authorized` shows Charl/CHARLIE's exact contract identity; `released`
still shows no pickup; `acknowledged` shows worker, role, dispatch identity and
time; `started` and `waiting_for_evidence` show durable progress; and
`completed_with_artifact` shows business outcome, exact artifact revision and
next dependency. One acknowledgement timeout produces one deduplicated
contained exception.

## First genuine T1 proof

The one-file task removes the now-obsolete actionable S01 procedure from the
replacement handover after P0 passed. S01 remains historical-only and is never
inserted. The task is reversible, has no external effect, scores T1, selects
exactly one Builder, and stops at the exact documentation artifact. The proposal
contains no signature or authorization and must not be inserted by this PR.

## S02-S07 after accepted P0

- S02 HERDMASTER: create nothing unless a specific exactly-once adapter defect
  survives operational acceptance evidence.
- S03 ROOTLINE: PRs #709/#710 remain operational truth under Oom Sakkie; create
  nothing unless later evidence proves a reusable source defect.
- S04 SAM: preserve the typed manager-evidence and owner-attention adapter work
  under SAM ownership; do not combine it with this canary.
- S05 BEACON: preserve repeatable organic-operation and typed manager-evidence
  work under BEACON ownership; do not combine it with this canary.
- S06 BEACON paid boost: defer until S05 evidence and exact spend authority.
- S07 CORE reliability: #680, #693 and the selected-worker acknowledgement check
  are the remaining focused slices; do not revive the broad legacy programme.

No S02-S07 row is created by this handover. Oom Sakkie, ROOTLINE, HERDMASTER,
SAM and BEACON behavior remains outside this source-only integration.
