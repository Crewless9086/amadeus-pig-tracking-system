# Vault Brain Changelog

## 2026-07-14 - Beacon-to-SAM deterministic attribution

- Added the read-only Beacon-to-SAM attribution contract joining campaign evidence to every exact matching SAM lead, linked orders, completed-sale revenue, fulfilment, and controlled lost-reason evidence.
- Defined exact-ID precedence, bounded source/time matching, append-only supersession semantics, currency separation, and fail-closed ambiguous, expired, unmatched, duplicate, and malformed outcomes.
- Kept persistent ingestion pending a separately approved migration and preserved zero post, send, optimization, spend, order, stock, and farm-write authority.

## 2026-07-14 - Beacon weekly marketing command brief

- Defined compatible latest-calendar-week campaign comparison and explicit target truth states.
- Made STOP/CHANGE/BOOST/REUSE classification server-owned and decision preparation owner-authenticated, stateless, and non-executing.
- Kept attributed revenue unavailable until a canonical paid/completed-sale join is proven.
## 2026-07-14 - CORE final artifact ingestion and supervisor truth

- Made Agent Runner v2 final artifacts idempotent durable stage inputs that advance only the matching first incomplete stage and preserve upstream evidence.
- Required restart recovery to consume a valid pending artifact before resume-stage selection.
- Defined one generation-owned supervisor process tree as dashboard runner truth and bounded stale-child recovery to dead prior supervisors.

## 2026-07-14 - BEACON calendar durable lifecycle and revocation

- Replaced process-local reusable-rule lifecycle authority with a worker-shared durable SQLite event registry.
- Added authoritative owner revocation events; preparation and historical-entry evaluation now resolve current lifecycle state server-side and fail closed after revocation.
- Kept rule approval and revocation evidence-only with no posting, sending, spending, reservation, stock, payment, or farm-write authority.

## 2026-07-14 - Beacon campaign rule lifecycle authority hardening

- Required prepare-only calendar approvals and latest-version state to resolve from the server-owned append-only lifecycle registry.
- Made forged approval snapshots and automatically superseded rule versions fail closed before calendar preparation.

## 2026-07-13 - CHARLIE resolved test-note backflow hardening

- Prevented corrected informational test-command notes with passing evidence from triggering unnecessary Builder backflow.
- Kept current-diff and unresolved acceptance failures blocking.
- Enforced one persisted active workflow stage so CORE execution and dashboard state stay aligned.
- Applied the same single-active invariant when an owner sends a mission back to a selected stage.
- Stopped the judgement scanner from misclassifying the safety term `fail-closed` as failed-test evidence.

## 2026-07-13 - Beacon Creative Studio provider evaluation foundation

- Added the private, owner-guarded Beacon Creative Studio evaluation contract for allowlisted ElevenLabs and Happy Horse 1.0 candidate identifiers.
- Required deterministic provider-disabled mocks, immutable prompt/parameter/source lineage, server-verifiable source hashes, estimate provenance, zero actual cost, private `needs_review` variants, and separate brand/privacy/safety/fidelity/disclosure/evaluation/public-use reviews.
- Recorded that all approvals are evidence-only and cannot enable providers, spend, publication, scheduling, customer sends, campaign execution, stock changes, or farm writes.
- Added the source-controlled additive migration contract; applying it remains separately owner-gated.
- Enabled RLS in an unapplied hardening migration for all six private Creative Studio tables without anonymous or authenticated-browser policies.

## 2026-07-13 - CHARLIE frozen-matrix recovery loop closed

- Made Mission Governance `owner_block` decisions authoritative in the generic recovery classifier.
- Exhausted frozen acceptance matrices and unapproved migration requirements now stop honestly for owner review instead of cycling through QA.
- Verifier findings against an empty or unimplemented scoped diff now route to Builder, and internal recovery notifications use the supported `info` level.

## 2026-07-13

- Added the canonical meat-production batch rail for internal pilots and future customer/stock batches: pig traceability, append-only stages, actual costs, cut outputs, dressing/packed yield, and cost-per-kilogram evidence.
- Required internal-use pilots to remain zero-revenue production records, separate from customer orders and sales transactions.
- Registered `MEAT-PILOT-2026-001` as the first live evidence batch and expanded Butcher's advisory scope to production stages, cost gaps, cuts, and verified yields without granting booking, pricing, sale, or fulfilment authority.

## 2026-07-12

- Required live-stock Beacon opportunity caps to match canonical animal sex to SAM demand sex preference and fail closed on invalid or missing sex evidence.
- Hardened Beacon's live-stock opportunity scanner to read quantified category/weight demand from active Supabase order-intake items and fail closed when demand is missing or incompatible with eligible supply.
- Added Beacon's Supabase-first, owner-review opportunity scanner contract: separate meat/live-stock cards, freshness and provenance, quantified-demand deduplication, conservative live-stock caps, zero meat cap in controlled mode, and no execution authority.
- Added Beacon's owner-review marketing operating contract with proposed brand/channel rules, KPI formulas, fulfilment-capped targets, approval tiers, and no execution authority.
- Added the completed-order sales projection contract: database-enforced linked-sale identity, atomic collected-line reconciliation, explicit totals, and conservative payment mapping.
- Clarified the executive hierarchy as Charl -> CHARLIE -> CORE and business/farm command layers: CHARLIE is Charl's private digital executive, while CORE is the existing CHARLIE CORE mission engine.
- Corrected FRED's canonical role to the planned client-facing enquiry and booking agent for Amadeus Private Transfers; FRED is not Finance, farm records, or general farm operations.
- Added the canonical live-stock order pricing rule: Orders automatically snapshot active Supabase pricing from Herdmaster-backed pig classification, repair blank prices before first quote generation, and never silently reprice an existing positive line.
- Defined the Herdmaster/Pig Allocation read model as SAM Live Stock's authoritative stock context: current withdrawal/follow-up holds, health/held state, breeding/family context, fresh latest-weight evidence, reservation/availability state, and canonical-only media references now gate matching and draft/quote preparation; missing canonical media remains empty rather than invented.
- Added the SAM Live Stock collection-first delivery policy: customer-requested transport may be estimated at R20.00 per one-way kilometre for farm round-trip recovery, with distance/source/status, destination, eligibility, owner-override audit fields, and mandatory owner review.
- Put SAM Meat into fail-closed `interest_capture_only` mode until the complete butcher loop is proven and explicitly owner-approved; only structured interest capture and owner-review reply preparation remain permitted.

## 2026-07-11

- Marked the first Herdmaster Pig Allocation alert automation as implemented: `/api/pig-weights/pig-allocation-alerts` is owner-read-guarded, read-only, advisory, includes pig plus litter/weaning alerts, and remains blocked from farm lifecycle, customer, public, order, sales, slaughter, reservation, stock, and migration writes.

## 2026-07-10

- Clarified CHARLIE CORE UI review-gate reliability: owner-review screenshot capture must probe local preview URLs before Playwright, recover stale localhost ports from recorded preview commands when possible, and only reuse durable stage screenshot evidence after promoting real desktop/mobile media into the owner-review media folder.
- Clarified the SAM Live Stock draft-order workflow: when conversation memory already has a `draft_order_id`, SAM must reuse it and sync draft lines instead of creating a duplicate draft order before quote preparation.

## 2026-07-12

- Tightened the BEACON fulfilment-aware opportunity scanner rule so live-stock demand caps count only eligible animals whose fresh current weight falls inclusively within any supplied requested weight range; contradictory, unparseable, or category-plus-weight mismatched demand now fails closed.

## 2026-07-09

- Added the SAM Live Stock durable `next_action` contract for inbound Chatwoot decisions, while preserving owner gates for customer send, quote send, reservation, payment, and stock movement.
- Added CHARLIE queue discipline: owner-facing queues and local runner pickup must treat `owner_work` as actionable, while system smoke tests, validation/canary/no-op checks, placeholder relay records, and low-signal intake must not crowd out real owner missions.
- Clarified the Pig Allocation rule that active pre-wean tagless piglets should stay under litter/weaning attention and must not appear as Pig Allocation `Needs Data` or Herdmaster missing-data alerts until weaning, tagging, or weight capture creates actionable allocation evidence.

## 2026-07-07

- Hardened CHARLIE emergency runner behavior after the SAM Live Stock overnight block: v2 now uses the provider-aware runner path, existing `in_progress` missions are observed instead of blindly re-executed, Claude failures can fall back to local Codex, Telegram notifications retry, transient artifact write locks retry, workflow updates tolerate unknown agent names, and synthetic review-board pass overwrites were removed.
- Activated Claude/Anthropic as a real CHARLIE CORE provider for selected review/specialist stages when `ANTHROPIC_API_KEY` is configured, with temporary `ANTROPIC_API_KEY` typo-alias support; Builder/Tester remain local runner stages until separately reviewed.
- Hardened CHARLIE runner reliability so subprocess timeout/crash paths become blocked review packets with evidence instead of silently leaving missions in progress, and review-ready notifications now key off `mission_status = pr_ready`.
- Added the CHARLIE Owner Approval Inbox workflow rule: Beacon, SAM Live Stock, SAM Meat, Butcher, and Herdmaster may attach exact owner-review suggestions to the Mission Vault for approve/edit/reject/pause/send-back decisions, but inbox approval records a decision only and does not execute customer sends, public posts, money-path actions, reservations, bookings, migrations, or farm lifecycle writes.
- Implemented the Beacon Live Stock Awareness lane split rule: Beacon draft selection, publish packets, and media upload/review must carry explicit `live_stock_awareness` or `meat_launch` lane context, and missing/invalid lane must block packet generation instead of defaulting livestock media into meat-sales copy.
- Added the active Agent Authority Matrix standard defining current authority boundaries, owner gates, required tests, and Claude-review triggers for Beacon, SAM Live Stock, SAM Meat, Butcher, Herdmaster, Oom Sakkie, Gatekeeper, Ledger, Atlas, Sentinel, and Forge.
- Added the Agent Authority Matrix And Claude Review implementation source-map section so future authority, runtime, public/customer automation, payment, meat, slaughter, butcher, stock reservation, farm lifecycle, specialist-dispatch, or agent-registration missions route through the correct Vault, code, and test sources.
- Added CHARLIE CORE Memory And Mission Recall to the implementation source map so memory-runtime, mission-recall, recovery-packet, send-back, blocked-state, resumed-mission, handoff, and agent-ledger missions select the existing runtime, replay, and test sources before advising or building.

## 2026-07-06

- Added Herdmaster Pig Allocation alert rules and implementation design authority for missing data, purpose review due, meat window timing, slaughter candidates, slow-grower feed risk, breeding candidates, stale weights, sold/exited conflicts, and future sow replacement alerts.
- Marked the alert layer as advisory, read-only, owner-gated, and blocked from farm lifecycle, sales, slaughter, reservation, payment, customer-send, public-post, migration, or production-data writes until separately approved.
- Corrected the Pig Allocation/Herdmaster implementation source map to reference the existing legacy farm sheet docs (`PIG_MASTER`, `PIG_OVERVIEW`, and `WEIGHT_LOG`) instead of a missing aggregate `FARM.md` file.
- Added Brain & Memory v2 Stage 1 doctrine defining memory classes, typed memory record shape, source-of-truth boundaries, recall/write/forget rules, privacy boundaries, promotion gates, and agent boundaries for CHARLIE, CHARLIE CORE, SAM, Beacon, Oom Sakkie, and future agents.
- Clarified that memory records are source-linked recall aids and cannot outrank owner instructions, runtime truth, or owner-reviewed Vault Brain doctrine.

## 2026-07-05

- Clarified the litter attention reconciliation rule: terminal sale/disposal/completed-sale piglets are accounted outcomes, and litter-level stillborn/mummified counts can account for non-live outcomes when source counts reconcile.
- Added the litter detail read-contract rule: active, weaned, and completed litter detail summaries must expose state-appropriate timing, attention, and weight fields.

## 2026-07-02

- Created first structured Vault Brain tree.
- Split the flat draft into folders for governance, identity, agents, businesses, workflows, playbooks, data, standards, rules, examples, and source maps.
- Added templates for agents, businesses, and workflows.
- Preserved first-pass source references from the repo.
- Added explicit agent/structure guardrails for templates, future registry, future organogram, Brain Guard blocking, and CHARLIE CORE environment/shared-department identification.
- Added the approved agent organogram, agent registry, and Amadeus Farm Sales structure with SAM as Farm Sales CEO and planned specialist sales agents.
- Captured owner-reviewed governance decisions and reduced open questions to unresolved verification/legal items.
- Converted owner identity review notes into clean operating doctrine for Charl, CHARLIE, CHARLIE CORE, Oom Sakkie, hierarchy, and execution boundaries.
- Split `02-agents` into `owner-command/` for CHARLIE and `charlie-core/` for CHARLIE CORE workflow agents.
- Added the owner Dynasty direction note as future strategic backbone guidance.
- Converted owner agent-personality comments into clean doctrine for owner-command, CHARLIE CORE, and farm agents.
- Migrated first high-value non-Vault source content into the Vault: meat sales, pork business model, pig purpose/allocation, farm operating model, SAM knowledge, and Amadeus Private Transfers.
- Added `10-source-map/VAULT_MIGRATION_INVENTORY.md` and strengthened archive/source-map rules so cleanup can happen only after useful context is migrated and referenced.
- Migrated backend, Supabase, Google Sheets, telemetry, n8n workflow, testing, deployment, security, customer response, and operations playbook doctrine into the Vault.
- Added repo cleanup status tracking and archived the old `planning/CHAT.md` scratch file into `docs/99-archive/legacy/`.
- Added Vault readiness scorecard with current 82-87% estimate and blockers to 95-100%.
- Added first-pass runtime Vault enforcement in CHARLIE Agent Runner v2: stage prompts load bounded Vault Brain context, agent artifacts must cite Vault sources, Brain Guard blocks owner review when Vault discipline is missing, and mission context packs now list Vault Brain as active truth.
- Added second-pass runtime intelligence rails: ranked Vault retrieval, source coverage scoring, owner preference context, Brain Guard v2 evidence, normalized Vault write-through evidence, expanded tool permissions, autonomy readiness API data, dashboard readiness tiles, and broader improvement analyst categories.
## 2026-07-13 - CHARLIE revision-scoped correction budgets

- Scoped correction-budget counts to the current packaged Builder commit while retaining lifetime history.
- Added the Builder revision SHA to durable backflow events.
- Kept exact blocker fingerprints mission-durable across revisions to prevent cosmetic rebuild loops.
## 2026-07-13 - Implementation follow-ups receive build authority

- Prevented generated implementation-defect follow-ups from inheriting read-only marketing or analysis pipelines.
- Added workflow coverage requiring Builder, Tester, and QA before review.

## 2026-07-14 - BEACON prepare-only campaign calendar

- Added the owner-rule campaign calendar contract: reusable rule versions require exact owner approval, changes require reapproval, and inactive versions fail closed.
- Defined prepared entries as immutable review evidence bound to approved media, exact copy, allowlisted channels, timezone windows, fresh demand caps, and pause evaluation, with no execution authority.
# 2026-07-14 - CORE durable recovery and observability repair

- Capped identical internal recovery across runner sessions and converted the second repeat into an honest owner block.
- Corrected outcome-based routing so implementation work reaches Builder even when mission text also mentions marketing, status, or review UI.
- Prevented placeholder revision text from triggering wrong-revision loops.
- Added terminal progress truth and durable attempts/recovery/backflow telemetry to CHARLIE CORE mission summaries.
- Bounded ANALYST reads and made observation-read failures degrade visibly instead of failing the scorecard.
# 2026-07-14 - CORE mission progress and owner decision clarity

- Added durable per-agent attempt, runtime, changed-file, and last-progress telemetry to CORE mission summaries.
- Added backend-generated owner-action guidance with a target stage, reason, expected outcome, and safe alternative.
- Updated Mission Control so blocked missions show one prominent recommended action; secondary actions are collapsed and targeted send-back preselects the recommended agent.
- Kept mission execution and approval authority unchanged; the dashboard still cannot run shell commands or bypass owner gates.

## 2026-07-14 - Owner-gated Beacon Live-Stock Sales lane

- Added a separate `live_stock_sales` campaign workflow backed by fresh Supabase eligibility/capacity and effective sheet-lineaged `public.sales_pricing` evidence.
- Bound exact Facebook copy, approved media hash, source revisions, cap, price, and SAM attribution into a deterministic packet that is server-revalidated before the existing exact owner confirmation gate.
- Kept WhatsApp suggestion-only and preserved all no-send, no-reservation, no-order, no-stock-change, no-spend, and no-lifecycle-write boundaries.
