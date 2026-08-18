# CHARLIE Mission Workflow

1. Owner creates or approves a mission.
2. CHARLIE normalizes it into a mission contract.
3. Local runner picks up approved mission.
4. Runner loads relevant Vault Brain context into each stage prompt.
5. Planner, Architect, Builder, Tester, QA Red Team, and Reviewer stages run.
6. Brain Guard checks Vault citations and update discipline.
7. Reviewer prepares owner review packet only after Brain Guard passes.
8. Mission stops at owner review.
9. Owner approves final release, sends back, pauses, rejects, or marks done.

## Executive Attention

Each transition into owner review carries a durable review-generation identity bound to the execution and candidate revision. CHARLIE emits one idempotent executive brief for that generation, so a re-reviewed candidate is not hidden by an older alert. High-priority unresolved reviews may receive at most two bounded reminders. The delivery audit is read-only; Telegram controls retain the existing owner-release gate and never send customers, take payment, reserve stock, merge, or deploy by themselves.

Authenticated Telegram mission callbacks claim their `update_id` before mutation and complete a durable sanitized outcome record. Completion is compare-and-set from `processing` only: reconciliation's terminal result remains authoritative if it wins before a delayed handler finishes. Final-release callbacks must bind to the current review generation and atomically compare both that generation and `pr_ready`; stale, duplicate, invalid, and non-owner callbacks fail closed without changing mission authority.

SAM conversation learning is grouped by conversation and classified before reaching owner attention. Learning-only corrections remain read-only improvement evidence and are excluded from pending owner-decision counts.

## Mission Contract

### Portfolio admission and execution eligibility

Business lifecycle, portfolio eligibility and execution status are separate
facts. A mission can remain `WORKING` while execution is `paused` and
non-runnable. Finding evidence is not itself a mission: promotion requires an
independent owner outcome, acceptance criteria, authority boundary, owner and
current evidence. Duplicate scope is reconciled into the existing identity.

Bootstrap admission uses one exact opaque mission identity and a structured,
versioned admission contract. Exact replay is a no-write success; a differing
replay conflicts. Admission alone grants no scheduling, pickup, recovery,
dispatch, release or provider authority. Only explicitly admitted current
missions may enter those rails.

Current board, visible-terminal board and historical library are projections of
one canonical mission and event contract. A register, worktree, shell, process
or old wait is planning or collision evidence, never current activity proof
without a fresh attributable heartbeat or result.

### Shadow Control Tower observation

Shadow Control Tower is disabled by default, observe-only and proposal-before-
decision. It may consume sealed authenticated owner-private input and existing
operational events, but receives no mission-pickup, execution, provider, merge,
deployment or production-write credentials. It cannot dispatch, start a
terminal, send a message, create a mission or manufacture a decision.

Every observation, proposal and later human decision has an exact durable
identity. Exact replay is a no-op; changed replay conflicts. Comparative
learning uses distinct genuine proposal/decision pairs and never fabricates a
comparison from historical chronology.

Every mission must resolve to:

- mission id;
- raw owner request;
- title;
- urgency;
- mission type;
- selected agent team;
- reason each selected agent is needed;
- approval level;
- allowed scope;
- forbidden scope;
- hard stops;
- acceptance criteria;
- tests and pressure tests;
- rollback/recovery plan;
- owner decisions needed;
- review/debrief packet.

## Runner And Orchestration Contract

CORE selects the smallest sufficient workflow for each new mission generation.
Persisted workflows remain frozen unless materially changed evidence creates a
new durable generation. Unknown high-consequence evidence raises the workflow
tier or blocks; scoring never overrides a protected trigger.

- `T0`: read-only inspection or advice; no Builder or external mutation.
- `T1`: small reversible mutation; Builder, Tester and Reviewer.
- `T2`: standard bounded feature; add source/architecture work where justified.
- `T3`: cross-module/elevated work; relevant specialists and QA Red Team.
- `T4`: protected/high-consequence work; mandatory governance, owner gates and
  exact operational proof.

UI, security/authentication, schema/migration, customer delivery, money,
hardware/irrigation, publication/spend, and legal/privacy triggers select their
mandatory specialist and review overlays. Every selected agent records its
reason, authority, allowed/prohibited actions, evidence output and bounded
attempt/time budget. Repository writers remain serialized; only independent
read-only work may run concurrently.

Each stage produces a structured artifact with summary, inspected files,
commands, relevant output tails, stage evidence and next handoff. Tester needs
passing tests; QA needs passing red-team status and no high/critical unresolved
risk; Reviewer needs the required evidence and an owner decision recommendation.
Missing evidence blocks advancement.

Tester failure returns to Builder. Other findings return to the smallest
responsible stage. Backflow is bounded per stage, semantic finding family and
mission, and its fingerprint is durable across runner restarts. Exhausted
in-scope acceptance failures become an honest owner block; adjacent/pre-existing
work becomes a deduplicated, non-auto-approved child mission. Red-zone findings
always stop at the owner gate.

Implementation, deployment, runtime promotion and natural provider-origin proof
are separate states. None implies another.

## Local Operator Commands

Telegram and `/charlie` record authority but never execute shell commands.
Current local entry points are:

```text
python scripts/charlie_mission_pickup.py [--dry-run | --watch ...]
python scripts/charlie_codex_execution_bridge.py --mission-id <id> [--execute-codex]
python scripts/charlie_release_bridge.py --mission-id <id> [--merge-pr | --complete-no-release]
python scripts/charlie_runner_control.py status|start|stop
```

Preparation modes create artifacts only. Execution requires the explicit flag,
recorded mission authority and current gates. Release requires
`release_approved`, a reviewed PR reference and the release workflow. These
tools never implicitly authorize migrations, customer sends, public posts,
payments, reservations, stock/farm writes or hardware actions.

The runner heartbeat and artifacts live under `.charlie_runner/`. Operational
acceptance requires exact worker/provider ownership, heartbeat, result, next
trigger and later terminal-independent continuity; an open terminal or process
is not that proof.

CHARLIE CORE must not run every agent for every mission. Intake must classify the mission and select the smallest capable agent team. UI missions use the UI council. Income-stream missions use business, risk, and evidence agents. Simple bugfixes should not wait on business or marketing agents unless the bug touches those areas.

For UI missions, the selected team must include Visual Reference Interpreter, Creative UI Designer, UX Interaction Designer, Frontend Design Implementer, and Visual QA Reviewer when screenshots, dashboard redesigns, approval flows, command centers, or visual references are involved.

## Stage Evidence

Each stage must produce structured evidence:

- Planner: scope, acceptance criteria, test plan, risks.
- Architect: source of truth, files/contracts, implementation approach.
- Builder: changes made and changed files.
- Tester: exact tests and pass/fail evidence.
- QA/Red-Team: regression/security/privacy/UX/evidence challenge.
- Reviewer: owner review packet and recommended decision.
- All stages: `vault_sources_used`, commands/files inspected, and either Vault updates or a no-update reason when relevant.

Missing artifacts stop the current stage, but they do not automatically create owner work. CORE classifies each stop as branch repair, environment retry, evidence repair, stale-state reconciliation, implementation repair, owner decision, or red-zone approval. The first five route internally to the responsible stage. Only an explicit owner decision or red-zone approval may remain owner-blocked. Tester failure caused by the current diff returns to Builder; unrelated or pre-existing findings are recorded as advisory backlog. Reviewer send-back returns to the named stage and preserves prior artifacts.

## Acceptance Matrix And Mission Families

Before Builder starts, CORE freezes a machine-readable acceptance matrix from the owner mission, Mission Vault, and Planner evidence. Every row names the requirement, required evidence, focused test scope, verification stage, and current status. Tester and QA must verify this matrix; they may not silently expand the parent mission until no conceivable edge case remains.

Review findings are classified as:

- acceptance-matrix violations, which may return to Builder within the correction budget;
- repeated semantic defect families, which share one family budget even when wording differs;
- adjacent improvements, which become linked child missions in `new` state;
- pre-existing or merge-base failures, which are advisory to the parent and may become linked child missions;
- environment/time-budget findings, which are advisory or separate recovery work;
- red-zone findings, which remain hard owner stops regardless of budget.

The default correction budget is four automatic backflows per mission and two per semantic finding family. Once exhausted, new non-red findings become deduplicated child missions with `parent_mission_id`, `root_mission_id`, sequence, finding family, dependency, priority, and reproduction evidence. Child missions are never auto-approved. The owner decides whether they run.

If frozen acceptance rows are still failed when that correction budget is exhausted, the mission must become an honest owner block. The generic recovery classifier may not reinterpret that governance decision as internally recoverable. A verifier that reports an empty or unimplemented scoped diff must return the work to Builder while budget remains; CORE must never repeatedly rerun QA, review, or evidence stages when no implementation or matrix evidence changed.

Parent missions become review-ready when their frozen matrix and focused mission-owned tests pass. Discovered work remains visible as a mission family without making delivery unbounded.

## Queue Discipline

Mission approval and execution eligibility are distinct. An approved mission
may carry a current-generation `owner_execution_hold` without changing its
owner approval, orchestration packet, workflow, or mission row. The hold and
its later release are separate append-only, server-owner-derived events.

While a hold is active, every authoritative runnable query, executive queue
cycle, direct pickup, stranded recovery, status claim, and execution-lease
write must exclude or reject that mission. Holds have no timeout and survive
restart. Only a separate exact owner-admin release for the same mission,
generation, and hold identity restores execution eligibility. Replays are
idempotent; stale generations and conflicting holds fail closed.

Deployment of this contract is migration-first. Apply and verify the additive
owner-hold ledger before deploying code that reads it. Code deployed before
the ledger exists fails closed and makes authoritative mission selection
unavailable. Rollback restores the prior code revision while retaining the
additive append-only ledger and its evidence.

Hold and release writes require the dedicated
`CHARLIE_OWNER_EXECUTION_HOLD_DATABASE_URL` credential whose database login is
authenticates only as the `charlie_owner_execution_hold_writer` login. Generic
`service_role` access is read-only for this ledger and cannot call its
append functions. Missing dedicated writer configuration fails closed.

CHARLIE owner-facing queues, Telegram handoff views, command-center buckets, and local runner pickup must treat `owner_work` as the actionable queue class. System smoke tests, validation missions, canary/no-op checks, placeholder relay records, and low-signal intake are not owner work and must not crowd out real owner missions waiting for approval, pickup, review, or release handling.

Dependencies are executable gates, not display hints. A child remains `waiting_dependency` until every `depends_on_mission_id` is `done`, `merged`, or `deployed`. Oversized parents become paused `waiting_children` coordinators after their deterministic children are created; the parent pipeline may not execute in parallel with those children. Child scope is frozen from its explicit family scope and may not recursively split from words inherited from the parent title.

Open mission intake is deduplicated by exact intent and by `(root_mission_id, finding_family)` for generated families. Recovery and review may append evidence to an existing mission, but may not create another open mission for the same family/scope.

## Executive liveness and recovery

CHARLIE measures approved, runnable, dependency-blocked and active missions
separately. Dependency filtering occurs before queue limits. Approved work with
no runnable or active mission is a queue-deadlock incident, not a healthy idle
queue. A recovery child never depends on the blocked parent it exists to repair,
and unrelated eligible mission families continue.

Kernel failures use typed durable results, one canonical repository-operation
lock and bounded identical-failure budgets. Three identical child exits place
the supervisor in an infrastructure hold instead of restart churn. Non-empty or
ambiguous Git operation metadata is never removed automatically. Dirty Builder
work and candidate-bound evidence are preserved before branch or runtime repair.
Recovered artifacts for the wrong durable stage are quarantined once.

Every command has an idempotency identity, desired state and verification. An
existing command is not success until authoritative state proves its intended
outcome. Completed recovery children return their parent to evidence
reconciliation. Owner notification uses a durable outbox and only genuine
decisions, exhausted governed recovery or red-zone authority reach Charl.

## Owner command and relay boundary

Private Telegram and dashboard controls read and mutate the same Supabase
mission record. Provider updates are claimed before mutation; stale, duplicate,
non-owner and generation-mismatched callbacks fail closed. Approval controls
record only legal current-state decisions. They cannot run shell commands,
start CORE, merge, deploy, migrate, contact customers, publish, pay, reserve or
change farm records.

`planning/CODEX_CHAT.md` and documentation menus are explicit local/manual
fallbacks only. They cannot become normal mission intake or runtime truth when
the canonical mission store is available. Model routing is provider-aware and
budget/trust governed; no model approves its own work or expands authority.

## Provider Routing

CHARLIE CORE may route selected specialist/review stages through Claude/Anthropic when `ANTHROPIC_API_KEY` is configured. The temporary typo alias `ANTROPIC_API_KEY` is also accepted so a configured owner environment does not fail closed for spelling alone.

Claude routing is active only for review/specialist reasoning stages such as Council Synthesis, Risk Agent, QA Red Team, Product Reviewer, Business Reviewer, Security Reviewer, and Evidence Reviewer. Builder and Tester remain local runner stages until Claude tool execution has a separate owner-reviewed safety design.

## Vault Enforcement

CHARLIE CORE missions are not allowed to be treated as review-ready unless the active stage artifacts prove Vault Brain usage.

The runner checks:

- stage artifacts cite `docs/09-vault-brain/` sources;
- the mission has a Mission Vault payload;
- retrieved Vault sources have source-selection reasons and source coverage evidence;
- Vault-sensitive changes to CHARLIE runtime, agent docs, or workflow docs include `vault_updates` or `no_vault_update_required`;
- preserved upstream artifacts from old send-back runs are visible as warnings, not silent truth.

Brain Guard validates the persisted workflow contract produced during planning. It must not reclassify a non-UI mission as UI during final review or invent agents that were not required by that contract. If evidence checks fail, CORE queues the responsible internal stage; the mission becomes owner-blocked only after the durable recovery cap is exhausted or an actual owner decision is required.

## Autonomy Boundary

CHARLIE CORE can run supervised missions with stronger memory, retrieval, tests, and evidence than before. It must still stop for owner review before release, money, customer contact, public posting, migrations, stock reservations, or farm lifecycle writes.

The target is to outperform a single assistant on repeatability, memory, evidence, queue discipline, and overnight throughput. It is not allowed to outperform the owner gate by bypassing it.

## Owner Approval Inbox

CHARLIE may show a unified Owner Approval Inbox for exact agent-prepared operational suggestions from Beacon, SAM Live Stock, SAM Meat, Butcher, and Herdmaster.

The inbox is an owner-review surface only. It may record `approve`, `edit`, `reject`, `pause`, and `send_back` decisions against a normalized item attached to the Mission Vault, but that recorded decision does not itself send a customer message, post publicly, create an order, quote, invoice, payment confirmation, stock reservation, butcher/slaughter booking, migration, or farm lifecycle write.

Every inbox item must identify its source agent, source type, exact proposed action or text, next gate, forbidden actions or risk flags when known, owning mission id, and current decision state. Domain-specific execution remains with the existing approved send/post/money/stock/butcher/farm gates after exact owner approval is recorded.

## Approval Levels

- `LEVEL 0`: report only.
- `LEVEL 1`: read-only investigation/planning.
- `LEVEL 2`: docs/planning edits.
- `LEVEL 3`: code/test/PR handoff; no merge.
- `LEVEL 4`: release/merge handoff after final owner approval.
- `LEVEL 5`: red-zone work requiring exact explicit confirmation.

## Runner Truth

Telegram and `/charlie` record mission authority, but they do not execute shell commands directly. A local runner/Codex process must pick up and execute approved work.

Governed startup is a controller-side ownership bootstrap:

1. The controller generates the startup nonce and supervisor generation.
2. It observes and validates the complete Windows supervisor
   launcher/interpreter tree before acknowledging supervisor readiness.
3. The supervisor may spawn the runner only after that exact durable
   acknowledgement.
4. The controller then observes and validates the runner
   launcher/interpreter tree and publishes a signed full-tree acknowledgement
   bound to generation, nonce, exact revision, PID topology, executable,
   command role, and live creation identity.
5. Runner recovery and mission pickup remain disabled until the exact current
   acknowledgement is durably readable.

Partial or stale acknowledgements, PID reuse, wrong ancestry, role, command,
path, revision, generation, nonce, or creation identity fail closed. Repeated
live validation at the acknowledgement boundary limits PID-reuse and TOCTOU
risk. Timeout, crash, mismatch, or validation failure must terminate and
verify the entire proven spawned tree while retaining redacted durable
evidence.

The canonical stop marker blocks governed CLI startup, direct supervisor
startup, direct pickup, runner recovery, and watchdog recovery. It is never
removed implicitly. Governed stop must handle supervisor-only,
runner-starting, and running trees, retain pre-stop ownership and termination
evidence, and never target an unrelated process. Disabled-watchdog state
remains authoritative until separately changed by an explicit governed owner
action.

If an agent subprocess times out or crashes, CHARLIE must record stdout/stderr excerpts, return code, changed files, blocker class, responsible stage, and recovery guidance, then queue an internal environment retry. A timed-out runner must not leave a mission silently stuck in `in_progress` or create false owner work. Repeated identical failures become an honest owner block only after the durable recovery cap is exhausted.

The no-final-artifact watchdog measures inactivity, not total elapsed build time. Continued stdout/stderr or worktree progress keeps a bounded agent run alive until the hard stage timeout; a productive long Builder must not be killed merely because its final handoff JSON is written at the end.

When a runner result moves a mission to `pr_ready`, the review-ready notification must key off the mission status rather than a narrow internal status string.

Existing `in_progress` missions must not be blindly re-executed by the watch loop. The watchdog recovers stale runner ownership. The continuous runner also reconciles legacy blocked missions against authoritative GitHub PR state: green mergeable PRs become review-ready, conflicts route to Publisher, current-head check failures route to Builder, and missing UI media routes to Visual QA.

Runner recovery requires both an expired durable execution lease and a dead/stale matching process. An empty current-agent display, a between-stage heartbeat, or another active mission is not enough to block a mission. Recovery returns the mission to its responsible internal stage and appends `runner_recovery_history`; it does not overwrite the original review packet or create owner work.

Builder packaging is transactional. CORE stages every actual Git change except runner-generated scratch output, including untracked files omitted by a model artifact. If commit packaging fails, CORE preserves the complete dirty state in a mission-labelled recovery stash, cleans the shared runner worktree, and reapplies that stash only when the same mission resumes.

PR #517 integrated this ownership bootstrap at merge
`0c4eb404fce6df8dfc2e8aab100690697d6e7cb9`. Hosted deployment is proven,
but local promotion, startup, watchdog activation, pickup, and T0 execution
remain separate and unauthorized.

### Observe-only startup contract

PR #539 adds an explicit `observe_only` governed start mode. It is a process
ownership test, not a mission workflow:

1. The controller binds observe-only mode to the accepted revision,
   generation, controller nonce, and observed supervisor tree.
2. The supervisor receives only an allowlisted OS/bootstrap environment and
   may spawn only the dedicated observe-only child after controller
   acknowledgement.
3. The dedicated child validates the current signed packet and live process
   trees without importing mission, execution-provider, or recovery modules.
4. The final signed acknowledgement binds mode, revision, generation, both
   nonces, launcher/interpreter membership, ancestry, creation identity, and
   both process-tree digests.
5. The child may publish ownership heartbeat evidence only. It cannot query
   runnable missions, inspect or acquire leases, recover work, execute a
   stage, invoke an agent provider, or mutate mission/queue/review/stage/
   artifact state.
6. Governed stop validates the exact tree, retains sanitized signed binding
   and termination evidence, restores the canonical stop marker, and proves
   zero survivors.

Direct CLI, supervisor, runner/pickup, recovery, and watchdog entry points
must all agree on the selected mode. Observe-only never falls back to ordinary
operation, and ordinary operation never inherits observe-only authority.
Malformed or unreadable current supervisor state suppresses watchdog recovery
instead of defaulting to a new ordinary start.

Before a future observe-only handshake, a read-only preflight must establish
zero runnable missions, zero leases/writers, exact current-main/deployment
identity, clean runtime/execution worktrees, and zero CORE processes. An
inability to prove zero runnable missions is a stop condition: retain the
marker and do not start. Removing and restoring the marker are bounded,
explicit governed operations; the canary ends stopped and cannot authorize a
mission.

## Revision And Finding Contracts

Review and test evidence must identify the packaged PR head as `expected_revision` and the actual checked commit as `tested_revision`. A proven mismatch is a stale-state recovery event, never valid owner-review evidence.

Every finding must record `scope_relation`, `introduced_by_current_diff`, `blocking`, `severity`, `evidence`, and `responsible_stage`. Findings outside the current diff cannot block that mission unless they prove an active red-zone safety breach.

Provider-specific stages must use the provider-aware runner path. If Claude/Anthropic fails transiently, CHARLIE may fall back to the local Codex provider for that stage and must record the fallback in runner evidence instead of blocking only because the provider was unavailable.

`planning/CODEX_CHAT.md` is the laptop-friendly active scratchpad. Supabase mission records are the durable queue. The Vault Brain is the doctrine layer that tells agents what rules and context to follow.

## Historical Implementation Evidence

- `docs/00-start-here/CHARLIE_MISSION_PROTOCOL.md`
- `docs/00-start-here/CHARLIE_CORE_AGENT_RUNNER_V2.md`
- archived Build Relay and Mission Loop evidence under
  `docs/99-archive/vault-cutover/docs/06-operations/`
- `planning/CHARLIE_CORE_EXTENDED_PLAN.md`
- `docs/09-vault-brain/00-governance/BRAIN_GUARD.md`
### Revision-scoped correction budgets

Correction budgets are evaluated against the current packaged Builder revision. Historical backflows remain visible for learning and reporting, but they do not consume a new revision's correction budget. Each new backflow records the Builder commit SHA. The separate mission-durable blocker fingerprint remains authoritative across revisions, so rebuilding without resolving the same finding still reaches the hard loop stop.
### Implementation follow-up routing

Generated follow-up missions for implementation defects, code defects, regressions, or failing tests must use a software-build workflow even when they inherit a planning, marketing, or analysis mission type from their parent. Pickup workflow refresh must provide Builder, Tester, and QA stages before review.

### Review evidence classification

Reviewer and Tester command mistakes that are explicitly informational, unrelated to the current diff, corrected, acceptance-neutral, and followed by passing focused evidence are advisory process notes. They must not trigger a product rebuild. Current-diff defects and unresolved acceptance failures remain blocking. Persisted workflows must expose no more than one active stage at a time.

Owner send-back normalization follows the same single-active-stage invariant: the selected return stage is active, downstream stages are pending, and stale upstream active markers are cleared without discarding completed evidence.

Safety language such as `fail-closed` describes required protective behavior and is not itself failure evidence. Explicit failed tests, unresolved acceptance findings, and send-back decisions remain blocking.

### Final artifact ingestion and supervisor truth

Agent Runner v2 final artifacts are durable stage inputs, not display-only files. A valid artifact is claimed under a locked mission record using mission, execution, agent, attempt, and content-hash identity. The same claim cannot append duplicate memory, handoff, quality, or workflow evidence. Consumption completes only the matching first incomplete stage and activates only its next incomplete stage; a passing Tester therefore activates QA/Red-Team while completed Builder evidence remains preserved.

Runner startup reconciles an unconsumed heartbeat artifact before selecting the resume stage. Supervisor truth is one generation-owned process tree: dashboard status is active only when the live supervisor owns the heartbeat child for the same generation. A replacement supervisor may stop a stale child only after the recorded prior supervisor is no longer live.
# CORE Recovery And Observability Rules (2026-07-14)

- Outcome-based routing is authoritative: any mission that asks for code or product implementation must include Builder and focused verification stages. Planning-only workflows may not be sent through revision review as if they produced a packaged PR.
- CORE permits one automatic recovery for an identical blocker fingerprint. The second occurrence is a durable owner block (`recovery_attempts_exhausted`), survives runner restarts, and is observed by ANALYST. Internal recovery may not silently reapprove the same unchanged mission indefinitely.
- Revision matching is enforced only when Builder supplied a real packaged Git revision. Placeholder revision text is not evidence and cannot create an unwinnable wrong-revision loop.
- Terminal mission states are display truth. `done`, `merged`, `deployed`, and review-ready outcomes display 100% even when an inherited workflow contains stale active steps. Duplicate or externally resolved completion is labelled separately.
- CORE mission summaries expose durable execution sessions, attempts, recoveries, backflows, repeated blocker count, last progress, and latest recovery reason. This telemetry comes from mission memory; no parallel state store is allowed.
- ANALYST reads bounded Supabase/Vault samples, degrades visibly when observation history is temporarily unavailable, and never hides the rest of CORE behind an artifact-read failure.
- Every stage records attempt number, start/update/completion time, duration when complete, and changed-file count when an artifact is available. Owner surfaces must distinguish real durable progress from a status label.
- Blocked owner review must present one recommended action with target, reason, and expected result. `Approve Rerun` is preferred when routing must be refreshed; `Send Back` is preferred only when the target stage already exists and is safe to resume directly.
