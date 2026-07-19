# Agentic Business OS Phases 2-7 Evidence

Status: integrated and deployed on 2026-07-19. This file does not grant runtime authority or claim owner evidence that has not been supplied.

Implementation revision: `29a0ce214d6ad8ada7189030477ea3ff46dd8bd7` (PR #300). Evidence revision: `1dfaa81647830a715bedb1434ea8300856ee6eef` (PR #301). All required checks passed before both merges. Render, the promoted runtime and the local runner now use the exact accepted evidence revision; the preceding Render deploy remains available for rollback.

## Phase 2 - Concurrent development and release control

Implemented:

- worktree inventory and owner-checkout execution refusal;
- dirty source overlap detection before Builder starts;
- mission-scoped file leases with explicit successful-stage release and stale recovery;
- single release coordinator acquired before `release_in_progress`;
- separate Cursor/worktree, owner checkout, GitHub accepted, promoted CORE, runner and Render revisions;
- revision truth in the owner mission-control response.

Evidence: `tests.test_charlie_concurrency_control`, focused Builder/release tests in `tests.test_charlie_execution_bridge`.

Live evidence: the owner-authenticated mission-control canary returned `mission_control_snapshot_ready` and identified Supabase missions as authoritative. Interrupted execution-worktree changes were preserved without modification as commit `215440f8a2e0ed16639e48644472f29aeed7bdd1` on `safety/core-execution-wip-20260719-2100`. Promotion then passed 117 focused tests and `core_cold_start_ready`. The scheduled watchdog started the runner normally; two fresh heartbeat cycles passed with zero restarts. GitHub accepted, promoted runtime, runner and Render deployed revisions all converge on `1dfaa81647830a715bedb1434ea8300856ee6eef`. The dirty owner checkout was not changed.

## Phase 3 - Unified operational event and business state

Implemented:

- additive RLS-enabled `operational_events` and projection checkpoint migration;
- mandatory authority, privacy, provenance, freshness and audit fields;
- deterministic replay with duplicate, late, out-of-order and invalid-partial safety;
- idempotent durable append/read adapter;
- non-destructive adapters for leads, conversations, orders, payments, animals, campaigns, missions, incidents, approvals and outcomes.

Evidence: `tests.test_charlie_operational_events`, `tests.test_charlie_operational_event_store`, `tests.test_charlie_operational_event_adapters`, and migration contract tests.

Live evidence:

- migrations `202607190001_create_operational_event_fabric` and `202607190002_create_domain_observer_runs` were applied in order;
- all four new tables exist with RLS enabled and both migration-ledger entries are present;
- one controlled sample from each of the ten domains produced ten durable events;
- the repeat append produced ten idempotent duplicates;
- deterministic replay applied ten events with zero rejections and rebuilt every expected projection key;
- the SHA-256 of all sampled source records was identical before and after reconciliation: `012f34a82304cc230729a4352cd6299c56f47fca6d442d39aa3280191c8def69`.

## Phase 4 - Domain observer loops

Implemented:

- bounded SAM, Ledger, Herdmaster and Beacon observers;
- schedule and event triggers;
- proposal-only recommendations with writes/sends false in code and DB checks;
- durable run telemetry and owner usefulness/false-positive feedback schema;
- real read adapters over existing SAM learning, order payment state, pig availability and Beacon evidence;
- integration into the existing continuous local runner behind `CHARLIE_DOMAIN_OBSERVERS_ENABLED=1`.

Known evidence gap: Ledger currently reads order payment state and explicitly reports that a dedicated cross-order cash-reconciliation source is unavailable.

Live evidence: one explicitly invoked read-only cycle completed and persisted four observer runs. Every result remained `authority_tier=observe`, `writes_authorized=false`, and `sends_authorized=false`. SAM inspected its learning source; Ledger inspected 29 orders and proposed review of three payment exceptions; Herdmaster inspected 213 animals and proposed review because none were confirmed sale-ready; Beacon reported 60% readiness, no review backlog and one production post. All sources reported live freshness. The Ledger gap for dedicated cross-order cash reconciliation remains explicit.

Remaining owner evidence: usefulness/false-positive feedback for the two recommendations. The continuous-runner activation flag remains disabled; no autonomous observer execution was enabled.

## Phase 5 - CHARLIE executive planning loop

Existing implementation evidence:

- continuous runner invokes the durable executive cycle;
- Supabase goals, commands, recovery cases and notification outbox;
- evidence-linked portfolio priorities, bounded recovery and owner decision inbox;
- scheduled private brief and follow-up queueing;
- software delegation to CORE and private executive/domain tools for operational reads.

Evidence: executive control/runtime/governance/private-executive suites.

Live evidence: a controlled production cycle completed in `observe` mode over 76 missions. It found five runnable approved missions, two dependency-blocked missions and no queue deadlock; all three generated commands were duplicates or already-satisfied observations, so no operational execution occurred. Fifteen durable recovery cases are scheduled/running, proving stale-plan recovery state is active.

Remaining owner decision: there are zero active executive goals. CHARLIE will not invent business goals; an owner-approved active goal is required before evidence-linked portfolio priority can be claimed live.

## Phase 6 - Controlled authority graduation

Existing implementation evidence:

- capability-specific trust ledger and promotion evaluation;
- delegation policies, expiry, action/cost limits, deterministic gates and rollback requirements;
- red-zone owner approval override;
- assurance thresholds and regression requirements;
- observer additions remain `observe` and cannot self-promote.

Live evidence: eight capability-specific trust rows contain 167 measured runs. All remain at `watch`; one escaped defect and zero rollbacks are recorded. No blanket or expanded autonomy promotion was made.

## Phase 7 - Executive cockpit and outcomes

Existing implementation evidence:

- owner-protected CHARLIE executive, mission-control and workforce surfaces;
- missions, decisions, trust, agent health, action/recovery/outcome evidence and failure states;
- scheduled private daily brief;
- revision truth added to the authoritative mission-control response.

Live evidence: the owner-authenticated private dashboard, executive scorecard, mission-control snapshot and owner-decision inbox all returned HTTP 200 on the exact deployed revision. The dashboard returned component status and authoritative source surfaces; mission control returned source status, revision truth and responsive failure metadata. The ten-domain reconciliation provides a durable source-to-event-to-projection trace.

Remaining owner evidence: close one real owner decision through action and measured outcome. No synthetic business decision or outcome was created for acceptance theater.

## Safety boundary

No customer message was sent, public post created, payment/reservation/lifecycle action taken, blanket authority granted, continuous observer flag enabled or live runner process changed. The reviewed additive migrations, observe-only telemetry/events, PR merge and exact-revision Render deploy described above were the only production mutations.
