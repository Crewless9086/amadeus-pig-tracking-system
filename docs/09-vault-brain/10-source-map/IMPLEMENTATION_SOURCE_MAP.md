# Implementation Source Map

## Livestock quotation journeys

- Contract/lifecycle: `modules/orders/livestock_quotation.py`
- Existing requested-items/HERDMASTER preview: `modules/orders/livestock_quote_preview.py`
- Effective-dated pricing: `modules/sales/sam_pricing.py`
- Schema: `supabase/migrations/202608190003_create_livestock_quotation_aggregate.sql`
- Owner preview UI: `templates/add-order.html`, `static/js/addOrder.js`
- Acceptance: `tests/test_livestock_quotation.py`

## ROOTLINE water-credit lifecycle

- Current B/C authority evidence semantics: append-only authority version `2`
  in `supabase/migrations/202608190001_reconcile_rootline_bc_water_evidence_policy.sql`,
  enforced before execution by `modules/telemetry/rootline_execution_runtime.py`.
  Version `1` is retained as immutable superseded evidence; authority scope and
  independent mixer, injection and borehole classes are unchanged.
- Canonical contract/projection: `modules/telemetry/rootline_water_credit.py`.
- Canonical execution-history integration:
  `modules/telemetry/rootline_irrigation_history.py`.
- Planning consumers: `modules/telemetry/rootline_water_energy_plan.py` and
  `modules/telemetry/rootline_adaptive_irrigation.py`.
- Owner projection: `modules/telemetry/rootline_owner_status.py`.
- Supabase truth and append-only replay/conflict enforcement:
  `supabase/migrations/202608150009_create_rootline_water_credit_lifecycle.sql`.
- No channel adapter, n8n workflow, Google Sheet, provider adapter or hardware
  executor owns water-credit authority.

## CMQ-20260813-05 Phase A Shadow Control Tower

- Canonical isolated-validation receipt producer and verifier:
  `modules/charlie/validation_receipt.py`, with the evidence-only CLI at
  `scripts/charlie_validation_receipt.py`. Version 2 binds the exact source,
  hashed suite commands/counts and strict disposable-isolation properties to
  one HMAC signature. Focused and proportional suite identities are mandatory.
  Passed and rejected evidence shares one create-once state-root identity;
  rejected identities cannot enter staging, and staging durably consumes a
  successful identity before its first source mutation so it cannot be replayed
  after interruption.
  `modules/charlie/runtime_staging.py` is the sole staging consumer. Focused
  signing, schema mutation, source/key binding, rejection and replay coverage:
  `tests/test_charlie_validation_receipt.py` and
  `tests/test_charlie_runtime_staging.py`. These source references provision no
  key and grant no staging, Task Scheduler, activation or deployment authority.
- Provider-origin activation and authenticated recovery:
  `modules/charlie/runtime_activation.py` and
  `scripts/charlie_runtime_activation.py`. The exact Windows Task Scheduler
  action and Operational audit-channel prior state are transactionally bound;
  missing post-`RunEx` packets recover only through the HMAC-authenticated
  consumed instance record, and consumed-plus-pending state is routed to
  explicit recovery before any repeated provider start;
  focused fail-closed coverage is in
  `tests/test_charlie_runtime_activation.py`. Native Windows access-denied
  forms are an explicit OS-authority blocker distinct from provider/tool or
  readback failure; no source fallback elevates the controller or bypasses
  exact audit readback. These
  source references grant no
  staging, activation, process, mission-pickup or release authority.

- Source contract: `modules/charlie/shadow_control_tower.py`.
- Focused zero-authority tests: `tests/test_shadow_control_tower.py`.
- Governing mission/admission/Shadow rules: `docs/09-vault-brain/04-workflows/CHARLIE_MISSION_WORKFLOW.md`.
- Historical operating handover: `docs/99-archive/vault-cutover/docs/06-operations/CMQ_20260813_05_PHASE_A_SHADOW_CONTROL_TOWER.md`.
- Storage: existing Supabase `operational_events` fabric at authority tier `observe`; no new queue, scheduler, agent, terminal fleet, schema or ledger.
- Default state: disabled unless `CHARLIE_SHADOW_CONTROL_TOWER_ENABLED` is explicitly true. Human Control Tower remains sole dispatcher and decision authority.
- Private observation input: `modules/charlie/shadow_control_tower_input.py`, registered only as the internal `observe_shadow_control_tower` private tool. `modules/charlie/private_runtime.py` supplies it through the existing authenticated structured-action boundary, using the sealed context defined by `modules/charlie/private_policy.py`. Historical evidence: `docs/99-archive/vault-cutover/docs/06-operations/CMQ_20260813_05_PHASE_A_PRIVATE_INPUT.md`; no parser, route, delivery or runtime enablement is added.
- Input tests: `tests/test_shadow_control_tower_input.py` cover authentication, disabled state, mission binding, replay/conflict propagation and zero effects.
- Canonical feedback ingress and subscription: `modules/charlie/control_tower_feedback.py`
  accepts only sealed owner-private `reconcile_control_tower_feedback` actions,
  persists genuine owner-pasted terminal feedback and later canonical human
  decisions in the existing `operational_events` fabric, and rejects memory,
  historical-register and terminal-generated substitutes. The existing
  `scripts/charlie_mission_pickup.py` loop consumes those events in supervised
  `observe_only` mode without reaching mission pickup, recovery or release.
  Only the exact paused/non-runnable CMQ bootstrap has observation eligibility;
  it gains no execution eligibility. Focused tests:
  `tests/test_control_tower_feedback.py`; disposable concurrency, proposal-before-
  decision and exact replay coverage: `tests/test_control_tower_feedback_postgres.py`.
- Authenticated Control Tower platform bridge: strict owner-admin `POST
  /api/charlie/control-tower/feedback` in `modules/charlie/routes.py` converts
  only an authenticated owner session into the existing sealed private-action
  context. It requires the exact UTF-8 feedback SHA-256. The matching strict
  owner-admin `GET` returns only lifecycle identities and zero-authority
  counters. Neither route invokes the Shadow worker or creates proposals.
- Bootstrap portfolio admission: the sealed authenticated `create_mission`
  action in `modules/charlie/private_tools.py` accepts only the one
  owner-approved `CMQ-20260813-05` admission contract. The canonical
  `modules/charlie/mission_store.py` transaction persists the exact opaque ID,
  non-runnable `paused` status, structured epoch/classification/lifecycle and
  one `portfolio_admitted` event. Exact replay is no-write. This does not admit
  any other mission or activate portfolio scheduling, recovery, dispatch,
  release or Shadow scoring. Tests:
  `tests/test_private_opaque_mission_creation.py` and
  `tests/test_private_opaque_mission_creation_postgres.py`.
- Bootstrap implementation evidence:
  `docs/99-archive/vault-cutover/docs/06-operations/CMQ_20260813_05_ATOMIC_BOOTSTRAP_ADMISSION.md`.
- Legacy portfolio classification: `modules/charlie/portfolio_classification.py`
  implements the sealed exact-baseline/exact-set atomic operation documented in
  `docs/99-archive/vault-cutover/docs/06-operations/CMQ_20260813_05_PORTFOLIO_CLASSIFICATION.md` and tested by
  `tests/test_portfolio_classification.py`. It is a non-admission dimension;
  generic events and all classified legacy runtime work remain fail closed.

## CMQ-20260813-03 grouped weights and movements

- Governing channel/preview/claim/execution rules: `docs/09-vault-brain/07-standards/CHANNEL_INVARIANT_CANONICAL_ACTION_STANDARD.md`.
- Historical discovery reconciliation: `docs/99-archive/vault-cutover/docs/06-operations/CMQ_20260813_03_GROUPED_WEIGHT_MOVEMENT_RECONCILIATION.md`
- Historical unwired pure preview source handover: `docs/99-archive/vault-cutover/docs/06-operations/CMQ_20260813_03_CANONICAL_PREVIEW_SOURCE_HANDOVER.md`
- Pure contract: `modules/pig_weights/canonical_grouped_preview.py`
- Historical application-only adapter wiring handover: `docs/99-archive/vault-cutover/docs/06-operations/CMQ_20260813_03_APPLICATION_PREVIEW_WIRING_HANDOVER.md`
- Application adapter: `modules/pig_weights/application_grouped_preview_adapter.py`; only `pig_weights_controller.preview_bulk_weight_entries` is wired.
- Historical typed OOM preview wiring handover: `docs/99-archive/vault-cutover/docs/06-operations/CMQ_20260813_03_OOM_TYPED_PREVIEW_WIRING_HANDOVER.md`
- Typed OOM adapter boundary: only `modules/oom_sakkie/grouped_weight_runtime.py` calls the pure contract after its existing natural interpretation and readiness preflight.
- Historical canonical claim/executor compatibility evidence: `docs/99-archive/vault-cutover/docs/06-operations/CMQ_20260813_03_CANONICAL_CLAIM_EXECUTOR_COMPATIBILITY.md`; the displayed canonical digest, durable claim and grouped executor bind the same canonical payload while retaining exact legacy-claim compatibility.
- Control Tower separately cleared the pure contract, application preview adapter and typed OOM preview boundaries recorded above. This entry grants no executor, protected-action, deployment or runtime authority; every further adapter or execution integration requires a separately cleared file boundary.

## Agentic farm runtime and legacy retirement

- Highest operating authority:
  `docs/09-vault-brain/00-governance/AGENTIC_OPERATING_MISSION_STANDARD.md`.
- Controlling architecture:
  `docs/01-architecture/AGENTIC_FARM_RUNTIME_PROGRAMME.md`.
- Historical path-pointer evidence is archived under
  `docs/99-archive/vault-cutover/docs/06-operations/` and is not a second
  controlling copy.
- Documentation lifecycle:
  `docs/09-vault-brain/00-governance/DOCUMENT_LIFECYCLE_AND_LEGACY_RETIREMENT_STANDARD.md`.
- Historical review handoff: `docs/00-start-here/CLAUDE_REVIEW_HANDOFF.md` is
  evidence only and must not govern current architecture or review.
- Current dependency-retirement and scheduler-singularity rules:
  `docs/09-vault-brain/07-standards/DEPLOYMENT_STANDARD.md`. The dated Phase 0
  provider inventory is archived evidence and requires fresh readback.
- Canonical owner-facing development dispatch and feedback ledger:
  `docs/06-operations/CONTROL_TOWER_MISSION_REGISTER.md`. Visible terminals are
  temporary development workers, not deployed agents. Every pasted terminal
  result must update this ledger transactionally before another prompt is
  issued. Every owner message and terminal report also triggers an all-terminal
  dispatch sweep so idle terminals receive the next eligible existing mission
  without making the owner act as dispatcher. The same ledger maintains a
  forward mission pipeline from each specialist's authoritative full scope:
  proven capability, active mission, next eligible mission, later outcomes,
  dependencies, collision boundaries and owner reprioritizations.
- Current continuous-operation acceptance and honest per-agent targets:
  `docs/09-vault-brain/00-governance/AGENTIC_OPERATING_MISSION_STANDARD.md`,
  `docs/06-operations/CONTROL_TOWER_MISSION_REGISTER.md` and the Continuous
  Operating Contract in each canonical agent file. Older Operational V1,
  Daily Brief, request, canary and portfolio labels are component evidence only.
- Read-only owner-finding intake before CORE automation is operational:
  `docs/06-operations/GENERAL_TERMINAL_INTAKE_CONTRACT.md`. GENERAL investigates
  and scopes reusable end-to-end defects; it never implements or substitutes
  for Control Tower, CORE or a deployed agent.
- Alignment authority and current terminal/worktree truth:
  `docs/09-vault-brain/00-governance/AGENTIC_OPERATING_MISSION_STANDARD.md` and
  `docs/06-operations/CONTROL_TOWER_MISSION_REGISTER.md`. Dated alignment audits
  are historical evidence only.
- Mandatory cross-system terminal/agent truth template:
  `docs/06-operations/CONTROL_TOWER_FEEDBACK_HANDOVER_TEMPLATE.md`. It requires
  separate web/API, worker, trigger, heartbeat, last/next cycle, authority,
  terminal-invoked and terminal-independent evidence and enforces a fresh
  execution identity after contained historical attempts.
- Canonical channel contract:
  `docs/09-vault-brain/07-standards/CHANNEL_INVARIANT_CANONICAL_ACTION_STANDARD.md`.
- Runtime truth: Supabase-backed domain events, projections, missions, claims,
  receipts and provider readbacks. n8n and Google Sheets are transitional or
  legacy surfaces unless a narrower current section explicitly proves otherwise.
- Rule: new or materially changed work must move toward one canonical action and
  durable runtime. It must not create new n8n business logic, canonical Sheets
  writes, laptop-terminal dependencies or channel-specific mutation paths.
- Canonical private-CHARLIE mission identity: `modules/charlie/mission_identity.py`
  preserves opaque mission identifiers through
  `modules/charlie/private_planner.py`, `modules/charlie/private_runtime.py`,
  `modules/charlie/private_tools.py` and the exact Supabase lookup in
  `modules/charlie/mission_store.py`; tests are
  `tests/test_charlie_private_planner.py`,
  `tests/test_charlie_private_runtime.py` and
  `tests/test_charlie_private_tools.py`. Authenticated explicit creation and
  exact replay are covered by `tests/test_private_opaque_mission_creation.py`;
  canonical transaction serialization is covered by
  `tests/test_private_opaque_mission_creation_postgres.py`.
  Embedded digits never define identity.

## ROOTLINE durable device doctrine and canonical action boundary

- Agent doctrine: `docs/09-vault-brain/02-agents/farm/ROOTLINE.md`.
- Water, energy, irrigation, fertilizer and Borehole 1 rules:
  `docs/09-vault-brain/08-business-rules/ROOTLINE_WATER_ENERGY_RULES.md`.
- Control architecture:
  `docs/09-vault-brain/04-workflows/ROOTLINE_CONTROL_ARCHITECTURE.md`.
- Cross-channel authority standard:
  `docs/09-vault-brain/07-standards/CHANNEL_INVARIANT_CANONICAL_ACTION_STANDARD.md`.
- Typed device registry: `modules/telemetry/rootline_device_registry.py`.
- B/C eligibility and disabled-by-default runtime authority:
  `modules/telemetry/rootline_execution_authority.py` and
  `modules/telemetry/rootline_execution_runtime.py`. Eligibility applies the
  standing B/C water-availability policy when tank counts are missing or stale,
  without inventing tank state, litres or water credit; only fresh explicit
  shortage, dry-supply, supply-fault or conflict evidence blocks that boundary.
- Execution, provider OFF/native shutdown and same-zone daily consumption:
  `modules/telemetry/rootline_irrigation_coordinator.py` and
  `modules/telemetry/rootline_irrigation_execution_store.py`.
- Fertilizer auxiliary planning/execution:
  `modules/telemetry/rootline_auxiliary_management.py` and
  `modules/oom_sakkie/rootline_fertilizer_commissioning_runtime.py`.
- Rule: application, typed Oom Sakkie, Telegram and voice are adapters to one
  canonical ROOTLINE action. No adapter grants hardware authority or owns a
  separate mutation path.

## ROOTLINE canonical irrigation status and owner access

- Current behavior and access authority: the focused ROOTLINE agent, Control
  Architecture, Water And Energy Rules and Source Of Truth Rules.
- Legacy hybrid status: `modules/telemetry/irrigation_service.py`, `/api/telemetry/irrigation/status`; `auto` falls back to `Amadeus_Irrigation_Logs` when no Supabase daily plan rows exist.
- Canonical ROOTLINE endpoints: daily advisor, daily brief, daily irrigation plan, water-energy plan and operating policy in `modules/telemetry/telemetry_routes.py` and their services.
- Owner access: `modules/auth/owner_access.py`, `/owner/login`, `/owner/logout`, `/owner/status`, `templates/owner-login.html` and shared `templates/_farm_nav.html`.
- UI: `static/js/dashboard.js`, `static/js/operationsDetail.js`, `templates/dashboard.html`, `templates/irrigation.html`.
- Rule: current operational status must not silently fall back to Sheets. Protected evidence remains protected; the UI must direct an unauthenticated owner through the existing session rail and return to the requested page.

## HERDMASTER Breeding Attention page access

- Protected HTML page: `/api/pig-weights/breeding-attention/view` in
  `modules/pig_weights/mating_routes.py`, using the shared page-oriented guard
  in `modules/auth/owner_access.py`.
- Private JSON evidence remains under the API-oriented owner-read guard and
  returns HTTP 403 rather than redirecting anonymous clients.
- Owner navigation: `templates/dashboard.html` and `templates/matings.html`.
- Focused access contract: `tests/test_breeding_attention_page_access.py`.
- Rule: owner login may return only to a validated internal absolute path; an
  external, scheme-relative, backslash or control-character destination is
  rejected rather than redirected.

## HERDMASTER full-lifecycle genetic merit analytics

- Authoritative semantics: `docs/09-vault-brain/02-agents/farm/HERDMASTER.md`
  and `docs/09-vault-brain/07-standards/UI_DASHBOARD_STANDARD.md`.
- Current surfaces: `templates/breeding-analytics.html`,
  `templates/breeding-analytics-detail.html`, `static/js/breedingAnalytics.js`,
  `static/js/breedingAnalyticsDetail.js`; current routes/readers are
  `modules/pig_weights/mating_routes.py`, `modules/pig_weights/mating_service.py`
  and `modules/pig_weights/farm_supabase_read_service.py`.
- Authoritative versioned backend: `modules/pig_weights/herdmaster_full_lifecycle_merit.py`,
  `load_full_lifecycle_merit_evidence` / `get_full_lifecycle_merit` in
  `farm_supabase_read_service.py`, and the owner-read
  `/api/pig-weights/breeding-analytics/v1/full-lifecycle*` routes. PR #905
  deployed this stable, zero-write contract.
- Retained worktrees at heads `68cf41c4...` and `c1702487...` plus open PR #823
  are historical design/test evidence only and must not be merged or revived.
- Rule: HERDMASTER owns the deployed canonical read packet and statistical
  semantics; later CODEX UI work owns rendering only after Control Tower assigns
  disjoint files. Neither slice creates a genetic ledger, score or farm fact.
- Current page JavaScript still consumes the legacy aggregate. The mission
  remains `WORKING` until CODEX renders the versioned packet and authenticated
  owner-visible production proof passes without farm writes.

## Oom Sakkie owner-request lifecycle

### Specific HERDMASTER management requests

- Semantic meaning and bounded owner context: `modules/oom_sakkie/semantic_front_door.py`.
- Provider-bound HERDMASTER request, canonical breeding worklist consumption,
  concise bilingual plan and replay claim: `modules/oom_sakkie/herdmaster_request_runtime.py`.
- Gateway precedence and provider delivery: `modules/oom_sakkie/telegram_gateway.py`.
- Broad `manager_round` requests remain owned by
  `modules/oom_sakkie/farm_manager_runtime.py`; a confident
  `herd_management` request is not a consolidated daily brief.
- Canonical Dead/Sold/off-farm state retires stale health-loss projections in
  `modules/oom_sakkie/herdmaster_management_runtime.py` before HERDMASTER or
  Daily Farm Manager composition.

### HERDMASTER mortality intelligence consumption

- Pure evaluator and packet: `modules/pig_weights/herdmaster_mortality_intelligence.py`.
- Canonical read-only loader: `modules/pig_weights/herdmaster_mortality_evidence.py`.
- Existing-boundary adapter and durable consumption: `modules/oom_sakkie/herdmaster_mortality_adapter.py`, `modules/oom_sakkie/herdmaster_mortality_runtime.py`.
- Consolidation/delivery owner: existing `modules/oom_sakkie/farm_manager_runtime.py` and family-message lifecycle; HERDMASTER has no direct Telegram route.
- ROOTLINE delegated-principal boundary: `modules/telemetry/rootline_delegated_principal.py` accepts only a typed, private-chat-bound `farm_manager` delegation and returns a sealed ROOTLINE outcome. It never aliases owner authority. Routine irrigation remains inside the existing commissioned B/C standing-authority and coordinator claim spine. Commissioning, autonomy configuration, electrical authority, fertilizer, borehole, and unapproved upstream/shared-control equipment remain excluded. Future shared-control topology requires separate governed configuration and physical commissioning.
- Tests: `tests/test_herdmaster_mortality_intelligence.py`, `tests/test_herdmaster_mortality_evidence.py`, `tests/test_oom_sakkie_herdmaster_mortality_adapter.py`, `tests/test_oom_sakkie_herdmaster_mortality_runtime.py`, and focused manager-runtime coverage.
- Authority: read-only assessment only; no diagnosis, treatment, medication, mortality/lifecycle/farm write or protected authority.
- Live lineage: PRs #723/#724, merge `c1913270a0ae16f2cfb971ecc9c6b5db0bacfdcc`, deployment `dep-d9pkn9p5efls73a501tg`. Authenticated read-only consumption is proven; provider-confirmed owner presentation awaits the next genuine manager request.

- Existing authenticated ingress and Telegram delivery:
  `modules/oom_sakkie/telegram_direct.py`.
- Durable owner-task lifecycle adapter:
  `modules/oom_sakkie/owner_task_lifecycle.py`.
- Generic authenticated family-message delivery/card lifecycle:
  `modules/oom_sakkie/family_message_lifecycle.py`.
- First natural specialist adapter and exact-preview factual writer:
  `modules/oom_sakkie/herdmaster_health_loss_runtime.py` and
  `modules/pig_weights/herdmaster_health_loss_recording.py`.
- Canonical health/loss workflow and stage-one pure contracts:
  `docs/09-vault-brain/04-workflows/HERDMASTER_NATURAL_HEALTH_AND_LOSS_INTAKE_WORKFLOW.md`,
  `modules/pig_weights/herdmaster_natural_health_loss_intake.py`, and
  `modules/oom_sakkie/herdmaster_health_loss_preview.py`. Runtime source and a
  narrow protected writer exist separately; their presence does not prove an
  enabled or operational production journey.
- Focused health/loss contract and runtime tests:
  `tests/test_herdmaster_natural_health_loss_intake.py` and
  `tests/test_oom_sakkie_herdmaster_health_loss_preview.py`, plus
  `tests/test_oom_sakkie_herdmaster_health_loss_runtime.py`; the bounded writer
  gate remains `tests/test_herdmaster_health_loss_recording.py` below.
- Longitudinal welfare-case source foundation:
  `supabase/migrations/202608200002_create_pig_welfare_case_lifecycle.sql`
  defines stable per-episode/per-concern identity, append-only case events and
  reference-only canonical fact links; `tests/test_pig_welfare_case_migration.py`
  and `tests/test_pig_welfare_case_postgres.py` verify the zero-authority and
  disposable-Postgres integrity contracts. The bounded runtime adapter is
  `modules/pig_weights/pig_welfare_case_runtime.py`; the existing authenticated
  health/loss handler consumes its durable open-case context without a 24-hour
  expiry and exposes the same case/work identity to the existing shared-
  attention contract. Focused coverage is in
  `tests/test_pig_welfare_case_runtime.py`. No second manager, queue,
  observation store, UI or Telegram lifecycle is introduced.
- Dispatch truth reducer:
  `modules/oom_sakkie/specialist_dispatch_ack.py`.
- Existing durable evidence rail:
  `sam_live_stock_conversation_review_events`; this is reused for append-only
  task events and is not a second queue or decision ledger.
- Focused acceptance:
  `tests/test_oom_sakkie_owner_task_lifecycle.py` and
  `tests/test_oom_sakkie_specialist_dispatch_ack.py`, plus
  `tests/test_oom_sakkie_family_message_lifecycle.py` and
  `tests/test_herdmaster_health_loss_recording.py`.
- Production/recovery contract:
  `docs/09-vault-brain/02-agents/farm/OOM_SAKKIE.md`.
- Rule: a deployed agent needs target-specific acknowledgement and fresh
  activity before Oom Sakkie reports execution. A terminal is manual and a
  specialist role is broader than any current adapter. Neither a release nor
  general agent health proves task receipt or start.

## Oom Sakkie Owner Attention Queue

- Doctrine and goal card:
  `docs/09-vault-brain/02-agents/farm/OOM_SAKKIE.md`
- Workflow contract:
  `docs/09-vault-brain/04-workflows/OOM_SAKKIE_OWNER_ATTENTION_QUEUE_WORKFLOW.md`
- Pure coordination kernel:
  `modules/oom_sakkie/owner_attention_queue.py`
- Existing-infrastructure adapter:
  `modules/oom_sakkie/owner_attention_adapter.py`, invoked after the existing
  SAM inbox disposition and through the authenticated Oom Sakkie callback.
- Focused tests:
  `tests/test_oom_sakkie_owner_attention_queue.py`,
  `tests/test_oom_sakkie_owner_attention_adapter.py`
- Current shared-adapter workflow:
  `docs/09-vault-brain/04-workflows/OOM_SAKKIE_OWNER_ATTENTION_QUEUE_WORKFLOW.md`
- Existing later integration surfaces, unchanged by this source slice:
  `modules/sales/sam_live_stock_launch_control.py`,
  `modules/oom_sakkie/telegram_direct.py`, GateKeeper's existing SAM callback
  relay and the existing SAM review/decision evidence rail.
- Rule: ordinary SAM activity is summary-only. Buttons belong only to a fresh,
  digest-bound protected decision. Consumption is an unperformed atomic intent
  until the existing rail returns an authoritative receipt. Operational alerts
  are separate and
  buttonless. Resolution edits the original card and callback replay is a
  no-op. This module adds no I/O or authority.

## HERDMASTER genetic selection and breeding observations

- Owner decision: `docs/09-vault-brain/00-governance/OWNER_DECISIONS.md`
- Binding genetic-selection rule:
  `docs/09-vault-brain/08-business-rules/HERDMASTER_GENETIC_SELECTION_RULES.md`
- Practical owner journey:
  `docs/09-vault-brain/04-workflows/HERDMASTER_BREEDING_ATTENTION_WORKFLOW.md`
- Workflow:
  `docs/09-vault-brain/04-workflows/HERDMASTER_BREEDING_ATTENTION_WORKFLOW.md`
- Evidence reconciliation and pair recommendation:
  `modules/pig_weights/herdmaster_breeding_evidence.py`,
  `modules/pig_weights/herdmaster_breeding_recommendation.py`
- Breeding observation rail:
  `modules/pig_weights/herdmaster_breeding_observation_service.py`,
  `modules/pig_weights/mating_routes.py`
- Breeding eligibility/read-only cohort projection:
  `modules/pig_weights/herdmaster_breeding_operating_loop.py` and
  `static/js/breedingAttention.js`. Effective body-condition evidence follows
  append-only supersession lineage. A below-minimum score remains a single
  recovery hold irrespective of elapsed time; ordinary review requires current
  in-range evidence. Proposed placement dates are explicitly plan-only.
- Database and browser gates:
  `tests/test_breeding_eligibility_read_model_postgres.py`,
  `tests/test_herdmaster_breeding_operating_loop.py`,
  `tests/test_mating_routes.py`, and
  `tests/breeding_attention_phase2_visual_proof.spec.js`.
- Grouped exposure/recovery contract:
  `modules/pig_weights/herdmaster_breeding_exposure_recovery.py`,
  `supabase/migrations/202608120001_create_breeding_exposure_events.sql`.
  The shared contract owns the inclusive planned-removal calculation (start
  is day 1; a 17-day window ends at start plus 16 calendar days). Channel
  adapters must not calculate a different date.
  The application preview/execute endpoints reuse `mating_routes.py` owner
  authentication and the existing observation/litter projections. Exposure
  start/removal events never create `mating_events`, service dates,
  conception, pregnancy, movement, or litter rows. Recovery hold/clearance and
  near-farrowing evidence reuse `pig_observation_events`; no second
  observation or recommendation ledger exists.
- Cross-channel action standard:
  `docs/09-vault-brain/07-standards/CHANNEL_INVARIANT_CANONICAL_ACTION_STANDARD.md`.
  Application, typed Oom Sakkie, Telegram and voice normalize equivalent intent
  into one specialist-owned canonical preview/execute/readback service; no new
  channel-specific mutation path is permitted.
- Unified breeding capture contract is retained in the Breeding Attention
  workflow. It makes grouped exposure the shared action for normal natural placement,
  keeps exact service separate, treats movement as explicit and preserves
  group identity for conservative HERDMASTER analysis.
- Owner surfaces:
  existing authenticated Oom Sakkie specialist consumption and the Breeding
  Attention/mating-board view.
- Rule: current foundation animals use the bounded owner-declared unrelated
  baseline unless attributable evidence proves a relationship. Pair quality is
  determined from exact production and lineage evidence before physical group
  capacity. A low service count means less proven, not genetically superior;
  new boars receive controlled trials. Recommendations have zero mating or
  movement authority.
- Owner-approved piglet weaning-observation contract is retained in the
  Breeding Attention workflow. It extends the existing litter Weaning Day workflow with exact-pig positive
  observation capture, reuses `pig_observation_events`, and adds a separate
  historical paper-note path. Codex owns the capture UI/backend integration;
  HERDMASTER owns cited advisory consumption. It creates no second observation
  store and has no automatic purpose or breeding authority.
- Canonical action and integrations: `modules/pig_weights/herdmaster_piglet_observation_action.py`,
  `modules/pig_weights/pig_weights_service.py`,
  `modules/pig_weights/farm_supabase_write_service.py`,
  `modules/pig_weights/pig_weights_routes.py`, `static/js/litterDetail.js`, and
  `templates/litter-detail.html`. Later evidence consumption is in
  `modules/pig_weights/herdmaster_breeding_evidence.py`; it retains attributable
  history and an unclassified watchlist without asserting structural clearance.
- Litter attention remains read-only in
  `modules/pig_weights/farm_supabase_read_service.py` and `static/js/dashboard.js`.
  Actual-weaning evidence is distinguished from a legacy planned date before
  `complete_weaning` can be raised; the sow name is the primary tile identity.
- Database-shaped gates: `tests/test_piglet_observation_action_postgres.py` and
  `tests/test_litter_weaning_atomic_postgres.py`. Browser identity/readback gates:
  `tests/dashboard_litter_attention_browser.spec.js` and
  `tests/litter_weaning_day_browser.spec.js`.

## Rootline owner daily brief

- Doctrine: `docs/09-vault-brain/02-agents/farm/ROOTLINE.md`
- Control architecture:
  `docs/09-vault-brain/04-workflows/ROOTLINE_CONTROL_ARCHITECTURE.md`
- Composer: `modules/telemetry/rootline_daily_brief.py`
- Owner-only route: `GET /api/telemetry/rootline/daily-brief`
- Existing owner dashboard surfaces: `templates/dashboard.html`,
  `static/js/dashboard.js`
- Focused safety/behavior tests: `tests/test_rootline_daily_brief.py`
- Underlying truth remains in the existing weather, forecast, power,
  irrigation, and daily-rollup readers. Rootline adds no write or hardware
  control authority.
- Delivery evidence: built, merged, and deployed through PR #464 at merge
  `187e07fb9f531549d35b04824ec9149875fabb85`; the owner-only route returned
  structured HTTP 200 evidence in one controlled read. This proves the Level 1
  Daily Brief route, not complete telemetry, hardware control, IFTTT
  authorization, or autonomous irrigation.

### Rootline Operating Knowledge And Daily Advisor candidate

- Operating policy: `docs/09-vault-brain/08-business-rules/ROOTLINE_WATER_ENERGY_RULES.md`
- Read-only advisor:
  `modules/telemetry/rootline_daily_advisor.py`
- Owner-only route:
  `GET /api/telemetry/rootline/daily-advisor`
- Existing dashboard panel:
  `templates/dashboard.html`, `static/js/dashboard.js`
- Tests:
  `tests/test_rootline_daily_advisor.py`
- Input evidence:
  the existing owner Daily Brief plus immutable owner-approved policy.
- Output:
  B12345/C12345 eligibility status, fresh-evidence status,
  `Irrigate`/`Do Not Irrigate`/`Hold`/`Needs Data` vocabulary, runtime only
  when authoritative policy is complete, explanations, historical-plan
  separation, and unresolved owner decisions.
- C12345 proof:
  packet `ROOTLINE-CANARY-C12345-CH2-20260727-32B0D177-G1`, SHA-256
  `ef388830f14056bf7baea2915950a655ae77c8f7c058b8e1f9f1c92638d028ab`,
  records one supervised identity/open/flow/OFF/closure proof ending safe
  closed. It is not routine irrigation authority.
- Authority:
  no database write, migration application, plan/command generation,
  schedule/workflow/queue/retry, IFTTT/n8n invocation, or hardware control.
- Future persistence:
  design-only strict append contract with evidence-content and provenance-
  envelope checksums; no migration exists and no evidence row is written by
  this candidate.

### ROOTLINE eWeLink secure onboarding

- OAuth service: `modules/telemetry/rootline_ewelink_oauth.py`
- Private store: `modules/telemetry/rootline_ewelink_oauth_store.py`
- Routes: `modules/telemetry/telemetry_routes.py`
- Migration: `supabase/migrations/202608060001_create_rootline_ewelink_oauth_vault.sql`
- Tests: `tests/test_rootline_ewelink_oauth.py`
- Governing boundary: `docs/09-vault-brain/04-workflows/ROOTLINE_CONTROL_ARCHITECTURE.md`
- Authority is limited to owner-authenticated authorization start, a
  HMAC-bound single-use callback, encrypted persistence and three allowlisted
  provider GETs. Readback and autonomous B/C activation remain disabled; no
  provider control call is implemented.

Status: active machine-aligned map, maintained with `modules/charlie/source_map.py`.

Purpose: tell CHARLIE CORE where real implementation truth lives before it advises or builds. Vault Brain carries doctrine and strategy; this map links doctrine to code, routes, tests, migrations, and legacy sources.

## Rule

For income, SAM, Beacon, order, WhatsApp, Chatwoot, n8n, or live-sales missions, CHARLIE CORE must inspect the relevant implementation source-map section before planning or building.

## Current Sections

### CHARLIE CORE Adaptive Mission Orchestration

Current implementation and review surface:

- operating contract:
  `docs/09-vault-brain/04-workflows/CHARLIE_MISSION_WORKFLOW.md`;
- legacy compatibility pointer:
  `docs/00-start-here/CHARLIE_CORE_AGENT_RUNNER_V2.md`;
- scoring and packet construction:
  `modules/charlie/adaptive_orchestration.py`,
  `modules/charlie/core_workflow.py`;
- durable execution, historical compatibility and evidence-driven expansion:
  `modules/charlie/execution_bridge.py`,
  `modules/charlie/mission_store.py`;
- owner-only throughput surface:
  `GET /api/charlie/build-relay/missions/summary`;
- tests:
  `tests/test_charlie_adaptive_orchestration.py`,
  `tests/test_charlie_core_workflow.py`,
  `tests/test_charlie_execution_bridge.py`,
  `tests/test_charlie_mission_store.py`,
  `tests/test_charlie_mission_pickup.py`,
  `tests/test_charlie_runner_control.py`,
  `tests/test_charlie_runner_supervisor.py`,
  `tests/test_charlie_runner_watchdog.py`;
- persistence: existing `charlie_missions.metadata_json`, agent artifacts and
  execution evidence; no second mission ledger or schema migration;
- rule: missions about workflow selection, mission scoring, execution tiers,
  agent budgets, dynamic expansion, historical workflow compatibility or
  orchestration throughput must inspect this section. Protected triggers and
  owner gates outrank aggregate scores. Existing persisted workflows remain
  frozen.

### CHARLIE CORE Process Ownership Bootstrap

Current implementation and verification surface:

- ownership identity, canonical tree normalization, signing, redaction, and
  live validation: `modules/charlie/process_ownership.py`;
- governed start/stop, stop-marker enforcement, acknowledgement waiting, and
  containment: `modules/charlie/runner_control.py`;
- supervisor-side handshake and runner-spawn gate:
  `scripts/charlie_runner_supervisor.py`;
- pickup/recovery acknowledgement gate:
  `scripts/charlie_mission_pickup.py`;
- focused tests:
  `tests/test_charlie_process_ownership.py`,
  `tests/test_charlie_runner_control.py`,
  `tests/test_charlie_runner_supervisor.py`,
  `tests/test_charlie_mission_pickup.py`;
- rule: startup or stop work must validate the complete externally observed
  launcher/interpreter topology, generation, revision, startup nonce,
  executable/command roles, parentage, PIDs, and live creation identity.
  Missing or stale identity fails closed. The canonical stop marker is not an
  implicit startup toggle, and watchdog enablement remains a separate governed
  action.
- delivery state: PR #517 code is merged and Render-deployed at
  `0c4eb404fce6df8dfc2e8aab100690697d6e7cb9`; local governed promotion,
  startup, watchdog activation, mission pickup, and natural proof have not
  been authorized.

### CHARLIE CORE Observe-Only Ownership Handshake

- doctrine:
  `docs/09-vault-brain/01-identity/CHARLIE_CORE.md`,
  `docs/09-vault-brain/04-workflows/CHARLIE_MISSION_WORKFLOW.md`;
- governed controller and signed acknowledgement/stop evidence:
  `modules/charlie/runner_control.py`,
  `scripts/charlie_runner_control.py`;
- supervisor mode propagation, credential allowlist, runner-spawn gate, and
  recovery suppression: `scripts/charlie_runner_supervisor.py`;
- dedicated no-mission/no-provider child:
  `scripts/charlie_observe_only_runner.py`;
- ordinary pickup mode separation and direct-entry fail-closed checks:
  `scripts/charlie_mission_pickup.py`;
- watchdog malformed-state and observe-only recovery suppression:
  `scripts/charlie_runner_watchdog.py`;
- tests:
  `tests/test_charlie_observe_only_runner.py`,
  `tests/test_charlie_runner_control.py`,
  `tests/test_charlie_runner_supervisor.py`,
  `tests/test_charlie_mission_pickup.py`,
  `tests/test_charlie_runner_watchdog.py`;
- rule: observe-only is a credential-free ownership/start/stop proof. It may
  emit only heartbeat, signed ownership, containment, and termination
  evidence. It cannot inspect or mutate mission, queue, lease, review, stage,
  artifact, product, customer, farm, migration, deployment, or business state
  and cannot transition into ordinary operation.
- state: PR #539 merged as
  `ce8971dff7605a91120a63c26dd22d81ca413360`; code is hosted in current main.
  Local promotion, handshake execution, ordinary startup, mission processing,
  and natural operational proof remain separate and incomplete.

### CHARLIE CORE Dashboard

Current built active workflow surface:

- routes: `/charlie`, `/api/charlie/build-relay/missions`, `/api/charlie/build-relay/runner/status`, `/api/charlie/build-relay/command-center`, `/api/charlie/build-relay/missions/<mission_id>/review`, `/api/charlie/build-relay/missions/<mission_id>/decision`;
- Vault doctrine: `docs/09-vault-brain/01-identity/CHARLIE_CORE.md`, `docs/09-vault-brain/04-workflows/CHARLIE_MISSION_WORKFLOW.md`, `docs/09-vault-brain/07-standards/CHARLIE_CORE_UI_MISSION_STANDARD.md`, `docs/09-vault-brain/07-standards/UI_DASHBOARD_STANDARD.md`, `docs/09-vault-brain/07-standards/EVIDENCE_AND_REVIEW_STANDARD.md`;
- code: `app.py`, `modules/charlie/routes.py`, `modules/charlie/mission_store.py`, `modules/charlie/runner_control.py`, `modules/charlie/execution_bridge.py`, `modules/charlie/core_workflow.py`, `modules/charlie/source_map.py`;
- UI: `templates/charlie.html`, `static/js/charlieMissionControl.js`, `static/css/main.css`;
- tests: `tests/test_charlie_build_relay.py`, `tests/test_charlie_execution_bridge.py`, `tests/test_charlie_mission_store.py`, `tests/test_charlie_core_workflow.py`, `tests/test_charlie_source_map.py`, `tests/test_frontend_route_contracts.py`;
- migrations: `supabase/migrations/202606300001_create_charlie_mission_queue.sql`, `202606300002_create_charlie_vault_v1_tables.sql`, `202607010002_create_charlie_core_v3_tables.sql`;
- legacy references: none;
- rule: when a mission is explicitly about the CHARLIE CORE dashboard, command center, mission queue, runner status, owner review, or workflow UI, CHARLIE CORE must select this section first. Negated mentions such as holding SAM/Beacon work out of scope must not pull in sales source-map sections.

### CHARLIE CORE Memory And Mission Recall

Current built active workflow surface:

- routes: `/api/charlie/build-relay/missions/<mission_id>/review`, `/api/charlie/build-relay/missions/<mission_id>/decision`, `/api/charlie/build-relay/missions/<mission_id>/replay`, `/api/charlie/build-relay/missions/<mission_id>/replay/stress`;
- Vault doctrine: `docs/09-vault-brain/01-identity/CHARLIE_CORE.md`, `docs/09-vault-brain/04-workflows/CHARLIE_MISSION_WORKFLOW.md`, `docs/09-vault-brain/06-data/BRAIN_AND_MEMORY_V2.md`, `docs/09-vault-brain/07-standards/EVIDENCE_AND_REVIEW_STANDARD.md`, `docs/09-vault-brain/07-standards/TESTING_STANDARD.md`, `docs/09-vault-brain/09-examples/GOLD_STANDARD_RECOVERY_PACKET.md`;
- code: `modules/charlie/mission_memory.py`, `modules/charlie/execution_bridge.py`, `modules/charlie/core_workflow.py`, `modules/charlie/routes.py`, `modules/charlie/mission_store.py`, `modules/charlie/replay_stress.py`, `modules/charlie/improvement_analyst.py`, `scripts/charlie_mission_pickup.py`, `scripts/charlie_codex_execution_bridge.py`;
- tests: `tests/test_charlie_mission_memory.py`, `tests/test_charlie_execution_bridge.py`, `tests/test_charlie_core_workflow.py`, `tests/test_charlie_replay_stress.py`, `tests/test_charlie_improvement_analyst.py`, `tests/test_charlie_build_relay.py`, `tests/test_charlie_source_map.py`;
- migrations: `supabase/migrations/202606300001_create_charlie_mission_queue.sql`, `202606300002_create_charlie_vault_v1_tables.sql`;
- legacy references: none;
- rule: when a mission is explicitly about CHARLIE CORE memory runtime, mission working memory, mission recall, recovery packets, blocked states, send-backs, resumed missions, handoffs, or agent ledgers, CHARLIE CORE must select this section before advising or building. Mission working memory remains mission-scoped evidence and does not outrank owner instructions, runtime records, or owner-reviewed Vault doctrine.

### Agent Authority Matrix And Claude Review

Current active governance surface:

- routes: `/charlie`, `/api/charlie/build-relay/missions/<mission_id>/review`, `/api/charlie/build-relay/missions/<mission_id>/decision`, `/api/charlie/build-relay/source-map`;
- Vault doctrine: `docs/09-vault-brain/07-standards/AGENT_AUTHORITY_MATRIX.md`, `docs/09-vault-brain/02-agents/AGENT_REGISTRY.md`, `docs/09-vault-brain/01-identity/CHARLIE_CORE.md`, `docs/09-vault-brain/00-governance/SOURCE_OF_TRUTH_RULES.md`, `docs/09-vault-brain/00-governance/UPDATE_RULES.md`, `docs/09-vault-brain/07-standards/EVIDENCE_AND_REVIEW_STANDARD.md`, `docs/09-vault-brain/07-standards/TESTING_STANDARD.md`, `docs/00-start-here/CLAUDE_REVIEW_HANDOFF.md`;
- code: `modules/charlie/source_map.py`, `modules/charlie/execution_bridge.py`, `modules/charlie/core_workflow.py`, `modules/charlie/mission_store.py`, `modules/oom_sakkie/agent_runtime.py`, `modules/oom_sakkie/routes.py`, `modules/beacon/media_library.py`, `modules/sales/beacon_campaign.py`, `modules/sales/sam_sales_router.py`, `modules/sales/sam_live_stock_runtime.py`, `modules/sales/sam_meat_runtime.py`, `modules/sales/meat_ops.py`, `modules/sales/meat_fulfillment.py`, `modules/pig_weights/pig_weights_service.py`, `modules/orders/order_intake_service.py`, `modules/sales/sales_transaction_read.py`, `modules/sales/sales_transaction_create.py`;
- tests: `tests/test_charlie_source_map.py`, `tests/test_charlie_execution_bridge.py`, `tests/test_charlie_core_workflow.py`, `tests/test_oom_sakkie_routes.py`, `tests/test_beacon_campaign.py`, `tests/test_sam_sales_router.py`, `tests/test_sam_live_stock_runtime.py`, `tests/test_sam_meat_runtime.py`, `tests/test_meat_ops.py`, `tests/test_pig_allocation_readiness_service.py`, `tests/test_sales_transaction_read.py`;
- legacy references: `docs/01-architecture/OOM_SAKKIE_AGENT_ROSTER.md`, `docs/04-n8n/workflows/1.0 - Sam-sales-agent-chatwoot/README.md`;
- rule: authority, Claude review, public/customer automation, payment, meat, slaughter, butcher, stock reservation, farm lifecycle, specialist dispatch, runtime authority, or agent registration missions must inspect this section. The matrix documents current authority only; it does not grant new live authority.

### SAM General Conversation

Current governance and implementation-ownership surface:

- routes: `/api/sales/channels/chatwoot/sam-meat/inbound`,
  `/api/sales/channels/chatwoot/sam-live-stock/inbound`;
- Vault doctrine:
  `docs/09-vault-brain/04-workflows/SAM_GENERAL_CONVERSATION.md`,
  `docs/09-vault-brain/02-agents/sales/SAM.md`,
  `docs/09-vault-brain/04-workflows/SAM_MEAT_SALES_WORKFLOW.md`,
  `docs/09-vault-brain/04-workflows/SAM_LIVE_STOCK_SALES_WORKFLOW.md`,
  `docs/09-vault-brain/00-governance/BRAIN_GUARD.md`,
  `docs/09-vault-brain/07-standards/EVIDENCE_AND_REVIEW_STANDARD.md`;
- router and context:
  `modules/sales/sam_sales_router.py`,
  `modules/sales/sam_shared_context.py`;
- LLM/review and inbound surfaces:
  `modules/sales/sam_meat_runtime.py`,
  `modules/sales/sam_live_stock_runtime.py`,
  `modules/sales/sales_transaction_routes.py`;
- journey tests:
  `tests/test_sam_sales_router.py`,
  `tests/test_sam_v3_shared_context.py`,
  `tests/test_sam_v3_replay_stress.py`,
  `tests/test_sam_meat_runtime.py`,
  `tests/test_sam_live_stock_runtime.py`,
  `tests/test_sam_live_stock_replay.py`;
- migrations: none;
- legacy reference only:
  `docs/04-n8n/workflows/1.0 - Sam-sales-agent-chatwoot/README.md`;
- rule: missions affecting ordinary SAM dialogue, unknown/general intent,
  ownership transitions, progressive lane discovery, topic changes, or
  specialist-tool timing must inspect this domain first and prove the complete
  customer journey. This map records ownership; it does not claim the doctrine
  is implemented, deployed, configured, or operational.

### Shared Outbound Delivery Truth

Current cross-system governance surface:

- Vault doctrine:
  `docs/09-vault-brain/07-standards/OUTBOUND_DELIVERY_TRUTH_STANDARD.md`,
  `docs/09-vault-brain/07-standards/EVIDENCE_AND_REVIEW_STANDARD.md`,
  `docs/09-vault-brain/00-governance/BRAIN_GUARD.md`;
- SAM journeys:
  `docs/09-vault-brain/04-workflows/SAM_GENERAL_CONVERSATION.md`,
  `docs/09-vault-brain/04-workflows/SAM_LIVE_STOCK_SALES_WORKFLOW.md`,
  `docs/09-vault-brain/04-workflows/SAM_MEAT_SALES_WORKFLOW.md`;
- quote/invoice/attachment doctrine:
  `docs/02-backend/QUOTE_INVOICE_DESIGN.md`,
  `docs/04-n8n/workflows/1.5 - outbound-document-delivery/README.md`;
- implementation surfaces to inspect, not authority granted:
  `modules/sales/sales_transaction_routes.py`,
  `modules/sales/sam_live_stock_runtime.py`,
  `modules/sales/sam_meat_runtime.py`,
  `modules/documents/document_service.py`;
- tests to inspect:
  `tests/test_sales_transaction_routes.py`,
  `tests/test_sam_live_stock_runtime.py`,
  `tests/test_sam_meat_runtime.py`,
  `tests/test_document_service_send.py`;
- rule: every customer-message, quote, invoice, or attachment delivery mission
  must distinguish prepared, claimed, Chatwoot-accepted, provider-delivered,
  provider-read, failed, and ambiguous states. HTTP/mock success is not
  delivery proof; provider identity and application idempotency remain
  separate; accepted/ambiguous outcomes are not automatically retried.

### SAM Meat Sales And Production

Current built pilot surface:

- routes: `/sales/meat-leads`, `/sales/meat-driver`, `/sales/meat-production`, `/meat-planning`, `/api/sales/meat-leads`, `/api/sales/meat-production/batches`, `/api/sales/meat-pilot-readiness`, `/api/sales/meat-pricing`, `/api/sales/channels/chatwoot/sam-meat/inbound`;
- authoritative offer: `external_sources/AMADEUS_HALF_CARCASS_CUTTING_STANDARD_v1.0.md` plus `docs/09-vault-brain/03-business/AMADEUS_MEAT_CUTTING_AND_COMMERCIAL_STANDARD.md`;
- Vault doctrine: `docs/09-vault-brain/02-agents/sales/SAM.md`, `docs/09-vault-brain/02-agents/sales/BUTCHER.md`, `docs/09-vault-brain/02-agents/sales/MEAT_SALES_AGENT.md`, `docs/09-vault-brain/02-agents/sales/SAM_MEAT_PERSONALITY.md`, `docs/09-vault-brain/04-workflows/SAM_MEAT_SALES_WORKFLOW.md`, `docs/09-vault-brain/05-playbooks/SAM_MEAT_HUMAN_SALES_PLAYBOOK.md`, `docs/09-vault-brain/08-business-rules/MEAT_SALES_RULES.md`, `docs/09-vault-brain/08-business-rules/MEAT_PRODUCTION_RULES.md`, `docs/09-vault-brain/09-examples/SAM_MEAT_GOLD_STANDARD_REPLIES.md`;
- code: `modules/sales/sam_meat_runtime.py`, `modules/sales/sam_meat_launch_readiness.py`, `modules/sales/sam_meat_commercial_standard.py`, `modules/sales/meat_pilot_readiness.py`, `modules/sales/meat_production.py`, `modules/sales/meat_documents.py`, `modules/sales/meat_match_engine.py`, `modules/sales/meat_ops.py`, `modules/sales/meat_fulfillment.py`, `modules/sales/meat_reconciliation.py`, `modules/oom_sakkie/sales_campaign_store.py`;
- UI: `templates/meat-sales-leads.html`, `templates/meat-production.html`, `static/js/meatSalesLeads.js`, `static/js/meatProduction.js`, `static/css/meatSalesLeads.css`, `static/css/meatProduction.css`;
- tests: `tests/test_sam_meat_runtime.py`, `tests/test_sam_meat_launch_readiness.py`, `tests/test_sam_meat_commercial_standard.py`, `tests/test_meat_launch_readiness.py`, `tests/test_meat_production.py`, `tests/test_meat_ops.py`, `tests/test_meat_fulfillment.py`, `tests/test_meat_reconciliation.py`, `tests/sam_meat_command_room_playwright.spec.js`;
- migrations: `supabase/migrations/202606140002_create_oom_sakkie_sales_leads.sql`, `202606160005_create_meat_price_book.sql`, `202606160006_create_meat_ops_rails.sql`, `202606170001_create_meat_reservation_events.sql`, `202606180001_create_meat_sales_conversation_learning_events.sql`, `202607130001_create_meat_processing_batches.sql`;
- legacy references: `docs/04-n8n/workflows/1.0 - Sam-sales-agent-chatwoot/README.md`, `MEAT_INTAKE_HANDOFF_PLAN.md`.

### Beacon Marketing

Current built gated surface:

- Oom Sakkie current-proposal boundary: `modules/oom_sakkie/beacon_request_runtime.py`
  consumes the existing semantic front door, authenticated Telegram gateway,
  `modules/beacon/opportunity_scanner.py`, and the private media-intake read
  model. It records one provider-bound result in the existing durable review
  rail and passes replay to the existing family lifecycle, which owns safe
  exactly-once delivery suppression or recovery. `modules/beacon/marketing_proposal.py`
  remains the pure proposal/media-request contract. No public-use,
  publication, customer-send, spend, farm-write, n8n, or Sheets authority is
  introduced. Coverage: `tests/test_beacon_marketing_proposal.py` and
  `tests/test_oom_sakkie_beacon_request_runtime.py`.
  The stable semantic intent `live_stock_awareness` routes through the existing
  `modules/beacon/content_operations.py` awareness builder even when SAM demand
  is zero. `modules/beacon/opportunity_scanner.py` supplies SAM demand and
  overlap context. Independent HERDMASTER safe-fulfilment capacity remains
  `Unknown` until a canonical demand-independent source is wired; no
  availability claim may be inferred from animal counts. Public livestock media must have
  effective public-use approval and server-computed SHA-256 lineage; otherwise
  the owner receives text-only content plus one optional precise media request.
  The exact failed 15 August instruction is a regression in
  `tests/test_oom_sakkie_beacon_request_runtime.py`, not a replay identity.

- routes: `/sales/beacon-media`, `/api/beacon/media-assets`, `/api/beacon/creative-studio/providers`, `/api/beacon/creative-studio/jobs`, `/api/beacon/creative-studio/jobs/<job_id>/reviews`, `/api/beacon/campaign-draft-selection`, `/api/beacon/campaign-publish-packet`, `/api/beacon/facebook-image-launch-packet`, `/api/beacon/manual-post-evidence`, `/api/beacon/campaign-performance`;
- owner media-intake workflow: `docs/09-vault-brain/04-workflows/BEACON_MEDIA_INTAKE_WORKFLOW.md`; OOM SAKKIE is the preferred owner-only Telegram intake gateway, while BEACON owns private storage, cataloguing, understanding, visual review, approval state, and usage history. The append-only schema, private bucket and fail-closed Render policy are deployed. Typed media and explicit album completion precede generic context. The current change replaces the advertised typed command with one opaque Finish Album button on the family-lifecycle card. Progress count/digest is canonical and monotonic; completion atomically binds owner, private chat, album, provider card and the exact ordered-item/hash generation. The weaker typed completion route is disabled. Library Accept, Public Use, Campaign Review and publication are separate later authorities;
- private album review source: `modules/oom_sakkie/beacon_media_review_runtime.py`,
  `modules/oom_sakkie/beacon_media_review_worker.py`,
  `modules/beacon/media_intake.py`, the existing protected-action claim rail,
  `/api/oom-sakkie/beacon/media-intakes/groups/<group>/review`, and
  `static/js/beaconMedia.js`. Browser and Telegram consume the same completed
  album digest and append to the existing Library/public-use event spine. The
  worker candidate selects a completed owner-bound album whose Library state is
  still pending, verifies its existing provider-confirmed album card, creates
  or re-arms one exact-generation protected claim, and uses the family lifecycle
  for one replay-safe card edit. PRs #985/#987 are deployed at merge
  `b32e32757`; the worker provider-confirmed the Bella review on existing
  Telegram message `3637`, and a later autonomous poll was effect-free;
  `202608150007_allow_beacon_media_review_claims.sql` admits the bound callback;
  `202608150008_add_beacon_album_review_envelope.sql` adds exact album/version/
  digest/order/type/scope evidence to historical-compatible events. Public Use
  is organic-awareness-only and grants no campaign/publication authority;
- code: `modules/beacon/media_library.py`, `modules/beacon/media_intake.py`, `modules/beacon/creative_providers.py`, `modules/beacon/creative_studio.py`, `modules/beacon/organic_media_intelligence.py`, `modules/beacon/organic_publication_binding.py`, `modules/beacon/organic_publication_authorization.py`, `modules/beacon/weekly_owner_review.py`, `modules/beacon/weekly_owner_review_decisions.py`, `modules/oom_sakkie/telegram_gateway.py`, `modules/oom_sakkie/telegram_direct.py`, `modules/oom_sakkie/family_message_lifecycle.py`, `modules/oom_sakkie/routes.py`, `modules/sales/beacon_campaign.py`, `modules/sales/sales_transaction_routes.py`;
- current litter-awareness composer/card source:
  `modules/oom_sakkie/beacon_request_runtime.py`. The scheduled BEACON case
  joins the scanner litter event to the canonical litter overview for the sow's
  human name, selects only exact litter/pig/event-linked current Public Use
  media, and creates no protected card when that evidence is absent. Public
  copy is organic farm life with no commerce term or CTA; the compact private
  card binds exact media previews and only Approve/Correct/Decline. Approval is
  still authorization-only until a deployed BEACON worker consumes it through
  the one canonical Meta execution spine; source/card completion is not
  publication proof.
- protected litter-story publication consumer:
  `modules/beacon/protected_publication_worker.py`, the authenticated deployed
  management route and the existing Oom Sakkie scheduler. It atomically consumes
  only a completed exact BEACON campaign-review approval, revalidates digest,
  expiry, story policy and exact Public Use media, then gives one attempt to the
  existing Meta execution/receipt spine. Definite failure and provider ambiguity
  are terminal; restart, concurrency and replay are silent. The callback never
  publishes, and no approval means the consumer does nothing.
- UI: `templates/beacon-media.html`, `static/js/beaconMedia.js`, `static/css/beaconMedia.css`;
- tests: `tests/test_beacon_media_library.py`, `tests/test_beacon_media_intake.py`, `tests/test_beacon_media_intake_routes.py`, `tests/test_beacon_media_intake_postgres.py`, `tests/test_oom_sakkie_owner_task_gateway.py`, `tests/test_oom_sakkie_gatekeeper_media_forwarding.py`, `tests/test_oom_sakkie_routes.py`, `tests/test_beacon_creative_studio.py`, `tests/test_beacon_creative_studio_migration.py`, `tests/test_beacon_campaign.py`, `tests/test_beacon_organic_media_intelligence.py`, `tests/test_beacon_organic_media_intelligence_postgres.py`, `tests/test_beacon_weekly_owner_review.py`, `tests/test_beacon_weekly_owner_review_decisions.py`;
- migrations: `supabase/migrations/202606180002_create_beacon_media_library.sql`, `202606180003_create_beacon_manual_post_events.sql`, `202606180004_create_beacon_campaign_performance_events.sql`, `202606180005_create_beacon_facebook_post_execution_events.sql`, `202606180006_extend_beacon_facebook_post_execution_statuses.sql`, `202607130002_create_beacon_creative_studio.sql`, `202607130003_enable_beacon_creative_studio_rls.sql`, `202607250001_create_beacon_weekly_review_decisions.sql`, `202607260003_create_beacon_publication_bindings.sql`, `202607260005_create_beacon_publication_authorizations.sql`, `202607260008_create_beacon_organic_media_learning.sql`, `202607270001_create_beacon_media_intake.sql` (deployed), `202608150003_allow_beacon_album_finish_protected_claims.sql` (deployed), `202608150007_allow_beacon_media_review_claims.sql` and `202608150008_add_beacon_album_review_envelope.sql` (deployed for BMQ-20260813-03), `202608190002_create_beacon_protected_publication_consumer.sql` (source candidate);
- legacy scope and media decisions are preserved in the Vault cutover archive;
  current implementation truth is the code, migrations, tests and provider
  evidence listed above.
- rule: media-intake missions must inspect the BEACON media-intake workflow plus current OOM SAKKIE Telegram and BEACON storage contracts. Intake, library acceptance, public-use approval, and publication authorization remain separate. Historical OneDrive/folder import is a separate phase.

### Orders And Sales Transactions

Current built Supabase-backed surface:

- requested-items livestock draft quote: `modules/pig_weights/herdmaster_live_transfer_contract.py` owns the read-only canonical animal/hold/medicine projection; `modules/orders/livestock_quote_preview.py` preserves customer request, advisory recommendation, reservation and completion as separate states, reports total eligible availability separately from capped recommendations, and permits partial/`Unavailable` draft lines without selecting or reserving stock; `/api/orders/livestock-quote-preview`, `templates/add-order.html` and `static/js/addOrder.js` expose the owner preview with consolidated medicine disclosure. Recorded food-chain withdrawal is a compact disclosure and slaughter/food-chain restriction, not by itself a live-sale blocker. Missing/stale weight lowers confidence. Only recorded health, welfare, quarantine, movement or sale holds block. Focused coverage: `tests/test_herdmaster_live_transfer_contract.py`, `tests/test_livestock_quote_preview.py` and `tests/livestock_quote_preview_visual_proof.spec.js`.
- already-completed livestock sales are not written from owner conversation or the read-only preview. The preview names the evidence still required and directs the owner to the existing protected Livestock order creation/line/completion rail; only completed Livestock orders may invoke canonical Sold/off-farm mutation.

- routes: `/orders`, `/orders/new`, `/sales-dashboard`, `/sales-availability`, `/api/orders`, `/api/sales-transactions`, `/api/sales-transactions/<sale_id>/payment-state/preview`, `/api/sales-transactions/<sale_id>/payment-state/confirm`, `/api/pig-weights/sales-dashboard`; the former direct `/payment` mutation fails closed;
- code: `modules/orders/*`, `modules/sales/sales_transaction_*`, `modules/sales/sales_payment_receipt.py`, `modules/pig_weights/pig_weights_service.py`;
- UI: `templates/orders.html`, `templates/order-detail.html`, `templates/add-order.html`, `templates/sales-dashboard.html`, `templates/sales-availability.html`;
- tests: `tests/test_order_routes.py`, `tests/test_order_service_*.py`, `tests/test_sales_transaction_*.py`;
- migrations: `supabase/migrations/202605210002_create_order_sales_tables.sql`, `202605210003_create_sales_transaction_tables.sql`, `202605210004_add_sales_transaction_payment_date.sql`;
- legacy references: `docs/03-google-sheets/sheets/SALES_STOCK_TOTALS.md`, `docs/04-n8n/workflows/ORDER_STEWARD_HANDOFF_CONTRACTS.md`.
- payment rule: `modules/sales/sales_payment_receipt.py` owns the single
  Supabase-backed preview/confirm action and rechecks its digest under a row
  lock. `modules/sales/sales_transaction_routes.py` requires strict owner-admin
  access and a 15-minute server-signed sale/actor/digest token from preview.
  `templates/slaughter-sale.html` and `static/js/slaughterSale.js` expose
  no direct-save payment path. The sale-neutral `/sales/transactions/<sale_id>`
  surface uses `templates/slaughter-sale-detail.html` and
  `static/js/slaughterSaleDetail.js`; auctions render as `Livestock — Auction`
  and use that same protected service. Oom Sakkie links to this canonical
  surface and presents review/preview only until canonical confirmation exists.
  `modules/oom_sakkie/sam_payment_owner_runtime.py` adapts the same service to
  the existing protected-action claim, family-delivery and callback rail.
  `modules/oom_sakkie/protected_action_runtime.py` rechecks the exact digest
  before invoking the sole writer; `/api/oom-sakkie/sales/payment-preview` is
  the strict-owner deployed-runtime entry and does not itself record money.
- zero-consideration correction: `modules/sales/sales_financial_disposition.py`
  owns the strict owner-admin digest-bound preview/confirm action for an
  existing completed Livestock sale. Migration
  `202608200001_add_sales_financial_disposition.sql` separates preserved list
  value from receivable truth. The sale detail and sales dashboard project
  R0.00 receivable and `Not_Applicable` payment without creating a duplicate
  sale, document, receipt, customer message or animal-transfer effect.
- governed Render production migrations: the protected manual workflow
  `.github/workflows/render-production-migrations.yml` creates a one-off job
  from the existing production web service. The closed runner
  `scripts/run_render_production_migrations.py` accepts no SQL or migration
  argument, verifies the ordered filename/checksum allowlist and exact Render
  deploy commit, serializes with a PostgreSQL advisory lock, applies each item
  transactionally and records immutable applied/failed receipts in
  `app_private.production_migration_receipts`. It never performs application
  business writes.

### Pig Allocation And Herdmaster Purpose Intelligence

Current built read-only readiness surface to expand:

- routes: `/pig-allocation`, `/api/pig-weights/pig-allocation-readiness`, `/api/pig-weights/purpose-review`, `/api/pig-weights/purpose-review/apply`, `/api/pig-weights/purpose-review/recheck`;
- Vault doctrine: `docs/09-vault-brain/02-agents/farm/HERDMASTER.md`, `docs/09-vault-brain/04-workflows/HERDMASTER_PURPOSE_REVIEW_WORKFLOW.md`, `docs/09-vault-brain/06-data/FARM_DATA_MODEL.md`, `docs/09-vault-brain/08-business-rules/PIG_PURPOSE_RULES.md`, `docs/09-vault-brain/08-business-rules/HERDMASTER_PIG_ALLOCATION_ALERT_RULES.md`, `docs/09-vault-brain/00-governance/SOURCE_OF_TRUTH_RULES.md`;
- code: `modules/pig_weights/pig_weights_service.py`;
- UI: `templates/pig-allocation.html`, `static/js/pigAllocation.js`;
- tests: `tests/test_pig_allocation_readiness_service.py`;
- migrations: none for the first read-only alert build;
- legacy references: `docs/03-google-sheets/sheets/PIG_MASTER.md`, `docs/03-google-sheets/sheets/PIG_OVERVIEW.md`, `docs/03-google-sheets/sheets/WEIGHT_LOG.md`;
- rule: Herdmaster Pig Allocation alert missions must inspect this section and the alert rules doc before advising or building. Alerts are advisory until owner-approved backend rails create any write, lifecycle, purpose, sales, slaughter, reservation, or customer-facing action.

### Live Pig Sales Legacy

Current status: live pig sales behavior is not yet a clean backend-native agent lane. It must be rebuilt against Supabase/app truth after Meat Sales pilot readiness is confirmed.

- current app surfaces: `/sales-dashboard`, `/sales-availability`, `/orders`, `/api/sales-transactions`, `/api/pig-weights/sales-dashboard`;
- legacy references: `docs/04-n8n/workflows/1.0 - Sam-sales-agent-chatwoot/README.md`, `docs/03-google-sheets/sheets/SALES_STOCK_TOTALS.md`, `docs/99-archive/legacy/planning_CHAT_2026-04_n8n_sales_agent_rewire.md`;
- rule: preserve old n8n behavior lessons, but do not treat old Google Sheets/n8n as current source of truth without app/Supabase verification.

### SAM Live Stock Sales

Current Stage 4 surface:

- Manager-summary contract: `modules/sales/sam_manager_summary.py` with focused
  coverage in `tests/test_sam_manager_summary.py`. It aggregates exact-bound
  sales outcomes for Oom Sakkie's existing specialist-consumption boundary and
  contains no customer content, individual-message detail, send authority or
  mutation authority. PR #691 deployed at merge
  `34464e89bf2d3a3ebbda12779cb2672461a2ca2b`.

- WhatsApp provider identity: `modules/sales/sam_live_stock_runtime.py`
  normalizes authenticated webhook provider shapes and
  `modules/sales/sam_owner_reply_window.py` binds provider evidence to exact
  account, inbox, contact, conversation, inbound and timestamp chronology.
  PR #727 deployed at merge `ec56263182763dc2475ca6069a3dd26853781441`, but
  live acceptance proved Chatwoot's conversation record omits channel type;
  the exact authenticated inbox endpoint is the authoritative provider source.
  Until that bounded shared-loader correction is reviewed and deployed, the
  affected inbound fails closed with no claim or send.

- routes to inspect later: `/sales-dashboard`, `/sales-availability`, `/orders`, `/api/order-intake/context`, `/api/order-intake/update`, `/api/orders/active-customer-context`, `/api/orders/available-pigs`, `/api/master/orders`, `/api/master/order-lines`, `/api/pig-weights/sales-dashboard`, `/api/pig-weights/pig-allocation-readiness`;
- authoritative offer: `external_sources/AMADEUS_HALF_CARCASS_CUTTING_STANDARD_v1.0.md` plus `docs/09-vault-brain/03-business/AMADEUS_MEAT_CUTTING_AND_COMMERCIAL_STANDARD.md`;
- Vault doctrine: `docs/09-vault-brain/02-agents/sales/SAM.md`, `docs/09-vault-brain/02-agents/sales/LIVE_PIG_SALES_AGENT.md`, `docs/09-vault-brain/03-business/LIVE_PIG_SALES.md`, `docs/09-vault-brain/04-workflows/SAM_LIVE_STOCK_SALES_WORKFLOW.md`, `docs/09-vault-brain/04-workflows/BEACON_LIVE_STOCK_AWARENESS_WORKFLOW.md`, `docs/09-vault-brain/05-playbooks/SAM_LIVE_STOCK_HUMAN_SALES_PLAYBOOK.md`, `docs/09-vault-brain/08-business-rules/LIVE_STOCK_SALES_RULES.md`, `docs/09-vault-brain/09-examples/SAM_LIVE_STOCK_GOLD_STANDARD_REPLIES.md`;
- code: `modules/sales/sam_sales_router.py`, `modules/sales/sam_live_stock_runtime.py`, `modules/pig_weights/pig_weights_service.py`, `modules/orders/order_intake_service.py`, `modules/orders/order_service.py`, `modules/orders/order_write.py`, `modules/orders/order_routes.py`, `modules/sales/sales_transaction_read.py`, `modules/sales/sales_transaction_create.py`;
- tests: `tests/test_sam_sales_router.py`, `tests/test_sam_live_stock_runtime.py`, `tests/test_order_intake_service.py`, `tests/test_order_routes.py`, `tests/test_order_service_reservation.py`, `tests/test_sales_transaction_read.py`, `tests/test_pig_allocation_readiness_service.py`;
- legacy references to mine only: `docs/04-n8n/workflows/1.0 - Sam-sales-agent-chatwoot/README.md`, `docs/04-n8n/workflows/1.0 - Sam-sales-agent-chatwoot/workflow.json`, `docs/03-google-sheets/sheets/SALES_PRICING.md`, `docs/03-google-sheets/sheets/SALES_AVAILABILITY.md`, `docs/03-google-sheets/sheets/SALES_STOCK_TOTALS.md`;
- rule: Stage 4 permits env-gated writes only to the existing order-intake service after validation. Customer sends, order creation, stock reservation, quotes, and sales transactions remain blocked until later owner-approved stages.
# SAM bounded inbox reconciliation

- `modules/sales/sam_live_stock_inbox_operator.py` — bounded Chatwoot inventory/chronology reads, conversation-specific provider-read isolation, current coverage evidence and pre/post-claim failure classification.
- `modules/sales/sales_transaction_routes.py` — existing authenticated reconciliation route; enables provider-read isolation without adding a router, webhook or consumer.
- `modules/sales/sam_live_stock_runtime.py` — bounded shared Chatwoot identity and chronology read timeout used by the existing Front Door/Livestock path.
- `tests/test_sam_live_stock_inbox_operator.py` — normal, slow-page, per-conversation timeout, pre/post-claim, ambiguous delivery and replay regressions.
# Oom Sakkie owner-observation lifecycle

- Semantic typing and bounded context: `modules/oom_sakkie/semantic_front_door.py`
- Durable operational lifecycle: `modules/oom_sakkie/operational_specialist_intake.py`
- Governed ROOTLINE bridge: `modules/oom_sakkie/rootline_operational_adapter.py`
- Atomic canonical observation rail: `modules/telemetry/rootline_water_energy_plan.py`
- Human daily rendering: `modules/oom_sakkie/rootline_daily_presentation.py`
# Oom Sakkie daily farm management

- `modules/pig_weights/herdmaster_daily_manager_evidence.py` — versioned,
  read-only HERDMASTER producer for weekly tagged-cohort coverage, separate
  breeding/untagged/inactive/Unknown classifications, descriptive material
  weight changes and mortality digest materiality from canonical Supabase
  truth. Historical eligibility remains Unknown when effective-dated state is
  unavailable.
- `modules/oom_sakkie/herdmaster_daily_manager_adapter.py` — zero-authority
  presentation adapter. Oom Sakkie consumes the typed specialist result and
  never recalculates cohort biology from a broad active/on-farm list.
- `tests/test_herdmaster_daily_manager_evidence.py` — complete, partial,
  breeding-excluded, untagged, inactive, Unknown, unavailable, conflicting,
  descriptive-change and mortality materiality/closure regressions.

- `modules/oom_sakkie/daily_farm_manager.py` — scheduler-owned whole-farm task
  packet, constrained semantic prioritization, presentation and durable replay.
- `modules/oom_sakkie/morning_runtime.py` — production-Render-owned 06:45 SAST
  wake-up, plan eligibility only through 06:59:59, read-only concurrent evidence
  loading and one provider-bound missed-window failure escalation. At or after
  07:00 plan loaders never run. Durable daily/provider claims, rather
  than a workstation process, arbitrate restarts and multiple web workers. One
  date-stable `:DELIVERY` claim is shared by the useful-plan and visible-failure
  outcomes; evidence changes never create another same-day send or edit.
- `modules/oom_sakkie/morning_scheduler.py` and
  `scripts/oom_sakkie_morning_scheduler.py` — authenticated Render cron entry,
  exact daily-runtime dispatch and non-colliding read-only ROOTLINE schedule
  acceptance. `modules/oom_sakkie/routes.py` exposes the bearer-protected target.
- `modules/oom_sakkie/rootline_fertilizer_commissioning_runtime.py` — existing
  fertilizer lifecycle continuation through ROOTLINE auxiliary execution rails.
- `modules/oom_sakkie/telegram_gateway.py` — authenticated owner, provider
  delivery and optional legacy ROOTLINE scheduler composition boundary. The
  morning plan no longer depends on that external tick.
- `modules/oom_sakkie/manager_question_runtime.py` — provider/card-bound
  grouped-question continuation and exact replay-safe evidence receipt before
  generic semantic intake; zero farm/customer/payment/hardware authority.
- `modules/sales/sales_payment_receipt.py` and
  `/sales/slaughter?update_sale=<sale_id>&payment_only=1` — one governed
  canonical payment-state action that preserves invoice accounting.
- `modules/telemetry/rootline_irrigation_coordinator.py` and
  `modules/telemetry/rootline_irrigation_execution_store.py` — single-use
  auxiliary start, shutdown recovery and physical-outcome evidence.

## Standing authority and owner-burden control

- `docs/09-vault-brain/00-governance/AGENTIC_OPERATING_MISSION_STANDARD.md`
  defines one-time delegated standing authority, the irreducible-owner-input
  test and `owner_burden_systemic_defect` classification.
- `docs/01-architecture/AGENTIC_FARM_RUNTIME_PROGRAMME.md` requires durable
  authority identity, runtime evidence ownership and zero routine confirmation
  inside an approved envelope.
- `docs/06-operations/CONTROL_TOWER_FEEDBACK_HANDOVER_TEMPLATE.md` makes every
  agent and terminal report authority scope, owner-interaction count and why any
  requested owner work could not be eliminated.
- ROOTLINE acceptance is owned by existing mission `RMQ-20260813-04`; the
  systemic correction must remove recurring human dry-release evidence while
  retaining automatic weather health, freshness, conflict, rain and hardware
  fail-closed boundaries.

## Agent execution ownership control

- `docs/09-vault-brain/00-governance/AGENTIC_OPERATING_MISSION_STANDARD.md`
  forbids terminal output from substituting for deployed-agent operational work.
- `docs/06-operations/CONTROL_TOWER_FEEDBACK_HANDOVER_TEMPLATE.md` requires the
  deployed actor, genuine trigger, real owner channel, terminal permissions,
  forbidden substitutions and agent-origin proof in every operational handover.
- `docs/01-architecture/AGENTIC_FARM_RUNTIME_PROGRAMME.md` binds effects to the
  canonical deployed worker and preserves terminal-created output only as
  synthetic or recovery evidence.
