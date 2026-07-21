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

SAM conversation learning is grouped by conversation and classified before reaching owner attention. Learning-only corrections remain read-only improvement evidence and are excluded from pending owner-decision counts.

## Mission Contract

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

CHARLIE owner-facing queues, Telegram handoff views, command-center buckets, and local runner pickup must treat `owner_work` as the actionable queue class. System smoke tests, validation missions, canary/no-op checks, placeholder relay records, and low-signal intake are not owner work and must not crowd out real owner missions waiting for approval, pickup, review, or release handling.

Dependencies are executable gates, not display hints. A child remains `waiting_dependency` until every `depends_on_mission_id` is `done`, `merged`, or `deployed`. Oversized parents become paused `waiting_children` coordinators after their deterministic children are created; the parent pipeline may not execute in parallel with those children. Child scope is frozen from its explicit family scope and may not recursively split from words inherited from the parent title.

Open mission intake is deduplicated by exact intent and by `(root_mission_id, finding_family)` for generated families. Recovery and review may append evidence to an existing mission, but may not create another open mission for the same family/scope.

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

If an agent subprocess times out or crashes, CHARLIE must record stdout/stderr excerpts, return code, changed files, blocker class, responsible stage, and recovery guidance, then queue an internal environment retry. A timed-out runner must not leave a mission silently stuck in `in_progress` or create false owner work. Repeated identical failures become an honest owner block only after the durable recovery cap is exhausted.

The no-final-artifact watchdog measures inactivity, not total elapsed build time. Continued stdout/stderr or worktree progress keeps a bounded agent run alive until the hard stage timeout; a productive long Builder must not be killed merely because its final handoff JSON is written at the end.

When a runner result moves a mission to `pr_ready`, the review-ready notification must key off the mission status rather than a narrow internal status string.

Existing `in_progress` missions must not be blindly re-executed by the watch loop. The watchdog recovers stale runner ownership. The continuous runner also reconciles legacy blocked missions against authoritative GitHub PR state: green mergeable PRs become review-ready, conflicts route to Publisher, current-head check failures route to Builder, and missing UI media routes to Visual QA.

Runner recovery requires both an expired durable execution lease and a dead/stale matching process. An empty current-agent display, a between-stage heartbeat, or another active mission is not enough to block a mission. Recovery returns the mission to its responsible internal stage and appends `runner_recovery_history`; it does not overwrite the original review packet or create owner work.

Builder packaging is transactional. CORE stages every actual Git change except runner-generated scratch output, including untracked files omitted by a model artifact. If commit packaging fails, CORE preserves the complete dirty state in a mission-labelled recovery stash, cleans the shared runner worktree, and reapplies that stash only when the same mission resumes.

## Revision And Finding Contracts

Review and test evidence must identify the packaged PR head as `expected_revision` and the actual checked commit as `tested_revision`. A proven mismatch is a stale-state recovery event, never valid owner-review evidence.

Every finding must record `scope_relation`, `introduced_by_current_diff`, `blocking`, `severity`, `evidence`, and `responsible_stage`. Findings outside the current diff cannot block that mission unless they prove an active red-zone safety breach.

Provider-specific stages must use the provider-aware runner path. If Claude/Anthropic fails transiently, CHARLIE may fall back to the local Codex provider for that stage and must record the fallback in runner evidence instead of blocking only because the provider was unavailable.

`planning/CODEX_CHAT.md` is the laptop-friendly active scratchpad. Supabase mission records are the durable queue. The Vault Brain is the doctrine layer that tells agents what rules and context to follow.

## Source References

- `docs/00-start-here/CHARLIE_MISSION_PROTOCOL.md`
- `docs/00-start-here/CHARLIE_CORE_AGENT_RUNNER_V2.md`
- `docs/06-operations/CHARLIE_BUILD_RELAY_PLAN.md`
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
