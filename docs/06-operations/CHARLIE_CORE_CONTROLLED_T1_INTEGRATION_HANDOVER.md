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
The later `origin/main` head `ae2318492e74458fef06a5eecc5be9d9085bf1e0`
adds Oom Sakkie manager-quality work only. A merge-tree reconciliation reports
no conflict with this CORE successor, and that operational change is not copied,
modified or exercised here.

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

The successor capability adds the remaining adapter through
`modules/charlie/development_mission_adapter.py`, re-exported by the existing
mission store and called by one exact-ID entry in the existing pickup module.
It uses only `charlie_missions` and `charlie_mission_events`. Authorization
inserts one `paused` mission; release leaves it `paused`; only a fresh exact
Builder acknowledgement can advance it toward start. It adds no queue,
dispatcher, broad-pickup mode or ordinary farm-message route. The runner stays
stopped and the T1 proposal remains unsigned and uninserted during source review.

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
8. after the adapter is reviewed and integrated, separately sign the exact
   release action, then accept one durable acknowledgement from the
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

The unsigned authorization shape is frozen in
`contracts/CORE_T1_POST_P0_AUTHORIZATION_PREVIEW.json`. Insert and release are
separate signatures over transaction `CORE-DEVELOPMENT-4C8E6D67CD1E048C3364E607`
and proposal digest `4c8e6d67cd1e048c3364e6078b199bd96bd0423b1dc11947428ffb63c7c6c3b2`.

## Later serialized integration and acceptance

This is one later owner-governed sequence; none of it is authorized now:

1. normally merge the successor PR only at its reviewed exact head and require
   exact-merge CORE, disposable-PostgreSQL and browser checks;
2. separately authorize and apply
   `202608040001_create_charlie_development_mission_adapter.sql`, then prove the
   authorizer and writer roles can call only their security-definer functions
   and cannot directly modify queue rows or authorization history;
3. prove the canonical runner stop marker remains present, broad pickup remains
   disabled, the runnable query is empty, all 86 legacy rows remain excluded and
   the historical T0 canary remains evidence-only;
4. regenerate the frozen proposal from the integrated main revision and compare
   score, tier, plan, scope, artifact set, lineage and architecture packet;
5. Charl/private CHARLIE signs only `authorize_insert`; record the full envelope
   with the dedicated authorizer role, then atomically insert one `paused` row
   and its proposed/authorized events with the dedicated writer role;
6. after a separate owner decision, sign and record only `release`; release keeps
   the row paused and cannot appear as pickup;
7. the existing pickup module creates one signed dispatch grant for one Builder
   and exact dispatch ID; only a matching fresh acknowledgement may advance the
   mission, followed by matching heartbeats;
8. require one exact-path, exact-commit, result-identified completion artifact,
   move only that mission to `pr_ready`, and prove zero unrelated pickup;
9. stop the runner and archive mission row, append-only events, authorization
   envelopes, command results, exact revisions and the unchanged global queue
   snapshot for owner acceptance.

The application boundary is `modules.charlie.mission_store`; persistence is
implemented by `modules.charlie.development_mission_store_adapter`. Separate
NOLOGIN roles confine PostgreSQL authority to append-only owner authorization,
dispatch authorization, repository-lineage authorization, the transactional
command function, and exact read functions. Insert and release use separate
short-lived HMAC envelopes. A fresh dispatch grant is required for
acknowledgement; after acknowledgement its digest becomes the durable worker
session identity for start, heartbeat, evidence and completion. Completion also
requires a separately recorded exact repository-lineage proof.

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

## Source-ready verification

- 203 focused CORE source tests pass.
- 8 disposable PostgreSQL tests pass, including serializable replay, rollback,
  privileged-role bypass rejection, frozen coordination, exact artifact lineage,
  legacy non-runnability and delayed deduplicated acknowledgement containment.
- The existing Oom Sakkie browser behavior smoke passes unchanged.
- Independent CORE operations/product and backend/database/security reviewers
  report no remaining blockers.
- The branch contains no production record, signature, authorization, release,
  pickup, dispatch, runtime or deployment action.
