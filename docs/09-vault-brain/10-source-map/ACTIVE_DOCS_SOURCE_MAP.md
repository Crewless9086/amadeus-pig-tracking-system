# Active Docs Source Map

Status: authoritative authority-routing map. Batch 2 cutover design approved
2026-08-18.

The Vault Brain is the only normative agent-doctrine layer. Files outside it are
controlling only when this map names them as a cross-system exception; otherwise
they are technical/runtime evidence, transitional references, current-state
records or history. `active` never means `authoritative`.

Use `VAULT_MIGRATION_INVENTORY.md` to track migration status and archive readiness.

Machine-aligned implementation map: `docs/09-vault-brain/10-source-map/IMPLEMENTATION_SOURCE_MAP.md`.

## Common Mandatory Governance Pack

- `docs/09-vault-brain/00-governance/AGENTIC_OPERATING_MISSION_STANDARD.md`
- `docs/09-vault-brain/00-governance/CONTROL_TOWER_ASSESSMENT_AND_DISPATCH_PROTOCOL.md`
- `docs/09-vault-brain/00-governance/DOCUMENT_LIFECYCLE_AND_LEGACY_RETIREMENT_STANDARD.md`
- `docs/09-vault-brain/00-governance/BRAIN_GUARD.md`
- `docs/09-vault-brain/00-governance/SOURCE_OF_TRUTH_RULES.md`
- `docs/09-vault-brain/02-agents/AGENT_REGISTRY.md`

Registered cross-system controlling exceptions:

- `docs/01-architecture/AGENTIC_FARM_RUNTIME_PROGRAMME.md`
- `docs/06-operations/CONTROL_TOWER_FEEDBACK_HANDOVER_TEMPLATE.md`

Current-state evidence, never reusable doctrine:

- `docs/06-operations/CONTROL_TOWER_MISSION_REGISTER.md`
- `docs/06-operations/GENERAL_TERMINAL_INTAKE_CONTRACT.md`

Technical scratchpads, never durable state or doctrine:

- `planning/CODEX_CHAT.md`
- `planning/ToDoList.md`

Compatibility pointers, never current state or doctrine:

- `docs/00-start-here/README.md`
- `docs/00-start-here/WORKFLOW.md`
- `docs/00-start-here/DEPLOYMENT_SOP.md`
- `docs/00-start-here/CHARLIE_MISSION_PROTOCOL.md`
- `docs/00-start-here/CHARLIE_CORE_AGENT_RUNNER_V2.md`
- `docs/00-start-here/CURRENT_STATE.md`
- `docs/00-start-here/NEXT_STEPS.md`
- `docs/00-start-here/PRODUCT_VISION.md`

## Deterministic Agent Packs

Each row is additive to the common pack. Load only the mission-relevant rows;
missing pack documents fail closed.

| Mission owner | Mandatory focused doctrine |
| --- | --- |
| CORE / Control Tower | `01-identity/CHARLIE_CORE.md`; `02-agents/owner-command/CHARLIE.md`; `04-workflows/CHARLIE_MISSION_WORKFLOW.md`; `07-standards/EVIDENCE_AND_REVIEW_STANDARD.md`; `07-standards/TESTING_STANDARD.md`; `07-standards/DEPLOYMENT_STANDARD.md` |
| Oom Sakkie | `02-agents/farm/OOM_SAKKIE.md`; `03-business/AMADEUS_FARM.md`; `08-business-rules/FARM_RULES.md`; relevant specialist pack |
| ROOTLINE | `02-agents/farm/ROOTLINE.md`; `04-workflows/ROOTLINE_CONTROL_ARCHITECTURE.md`; `08-business-rules/ROOTLINE_WATER_ENERGY_RULES.md`; `08-business-rules/FARM_RULES.md` |
| HERDMASTER | `02-agents/farm/HERDMASTER.md`; `04-workflows/HERDMASTER_PURPOSE_REVIEW_WORKFLOW.md`; `08-business-rules/HERDMASTER_PIG_ALLOCATION_ALERT_RULES.md`; `08-business-rules/PIG_PURPOSE_RULES.md`; `06-data/FARM_DATA_MODEL.md` |
| SAM livestock | `02-agents/sales/SAM.md`; `04-workflows/SAM_LIVE_STOCK_SALES_WORKFLOW.md`; `08-business-rules/LIVE_STOCK_SALES_RULES.md`; `06-data/ORDER_DATA_MODEL.md`; `07-standards/CUSTOMER_RESPONSE_STANDARD.md`; `07-standards/OUTBOUND_DELIVERY_TRUTH_STANDARD.md` |
| SAM meat | `02-agents/sales/SAM.md`; `04-workflows/SAM_MEAT_SALES_WORKFLOW.md`; `08-business-rules/MEAT_SALES_RULES.md`; `08-business-rules/PAYMENT_RULES.md`; `07-standards/CUSTOMER_RESPONSE_STANDARD.md`; `07-standards/OUTBOUND_DELIVERY_TRUTH_STANDARD.md` |
| BEACON campaign | `02-agents/marketing/BEACON.md`; `04-workflows/BEACON_CAMPAIGN_WORKFLOW.md`; `08-business-rules/MARKETING_RULES.md`; `08-business-rules/MEDIA_PRIVACY_RULES.md` |
| BEACON livestock awareness / Meta | BEACON pack plus `04-workflows/BEACON_LIVE_STOCK_AWARENESS_WORKFLOW.md`; no meat-sales or availability source may replace it |
| CODEX UI / any frontend | owning agent pack plus `07-standards/AMADEUS_FARM_UI_FACELIFT_STANDARD.md`; `07-standards/UI_DASHBOARD_STANDARD.md`; `07-standards/CHARLIE_CORE_UI_MISSION_STANDARD.md`; evidence/testing standards |
| Documents | `07-standards/OUTBOUND_DELIVERY_TRUTH_STANDARD.md` plus the owning domain pack. No canonical Documents agent/workflow pack exists yet, so autonomous Documents missions fail closed. `docs/01-architecture/CANONICAL_DOCUMENT_CATALOGUE_OWNERSHIP.md` is technical catalogue evidence only. |

Paths in this table are relative to `docs/09-vault-brain/` unless written as a
repository-root path.

## Authority Classes And Cutover Disposition

| Class | May define agent behavior? | Batch 2 disposition |
| --- | --- | --- |
| Focused Vault doctrine | Yes, subject to conflict order | Keep normative; audit agent by agent |
| Two registered controlling exceptions | Only within their named architecture/evidence scope | Retain and bind explicitly |
| Mission register/current-state projection | No reusable doctrine | Keep current-state only; later split history |
| Code/tests/schema/provider records | No; implementation/runtime truth only | Keep near implementation |
| Technical runbooks | No; procedure only under Vault rules | Keep active technical reference |
| n8n/Sheets documents | No; transitional evidence only | Retain until named exit test, then archive review |
| Retired legacy AI folder, business modules and legacy architecture | No after focused Vault reconciliation | Agent-audit queue; pointer/archive/delete proposal later |
| Planning, prompts and inbox material | Never | Extract unique decisions, then archive/delete proposal |
| Handovers and evidence logs | Never | Split durable rule from dated evidence; retain history |
| Static agent asset notes | Never | Replace with generated/reconciled Vault projections |
| Archive, superseded, retired or quarantined | Never | Exclude from ordinary retrieval |

## Architecture And Data

- `docs/01-architecture/FARM_OPERATING_SYSTEM_MAP.md`
- `docs/01-architecture/COMPONENT_OWNERSHIP.md`
- `docs/09-vault-brain/06-data/BRAIN_AND_MEMORY_V2.md`
- `docs/02-backend/DATA_MODELS.md`
- `docs/02-backend/SUPABASE_FOUNDATION_PLAN.md`
- `docs/02-backend/SUPABASE_ORDER_SCHEMA_PLAN.md`
- `docs/02-backend/SUPABASE_TELEMETRY_PLAN.md`
- `docs/03-google-sheets/WRITE_OWNERSHIP.md`

## Workflows

The n8n documents below are transitional runtime evidence, not controlling
architecture. Their use is bounded by the Agentic Farm Runtime Programme.

- `docs/04-n8n/WORKFLOW_RULES.md`
- `docs/04-n8n/DO_NOT_CHANGE.md`
- `docs/04-n8n/WORKFLOW_MAP.md`
- `docs/04-n8n/CHATWOOT_ATTRIBUTES.md`
- `docs/04-n8n/DATA_FLOW.md`
- `docs/04-n8n/NODE_RESPONSIBILITIES.md`

## Current Business Implementation References

These configuration and focused-rule files support implementation but do not
replace the applicable mandatory agent pack.

- `config/sam_farm_knowledge.json`
- `docs/09-vault-brain/08-business-rules/HERDMASTER_PIG_ALLOCATION_ALERT_RULES.md`
- `docs/09-vault-brain/08-business-rules/MEAT_PRODUCTION_RULES.md`

## Operations And Evidence

- `docs/09-vault-brain/04-workflows/RELEASE_WORKFLOW.md`
- `docs/09-vault-brain/07-standards/DEPLOYMENT_STANDARD.md`
- `docs/09-vault-brain/07-standards/TESTING_STANDARD.md`
- `docs/09-vault-brain/07-standards/EVIDENCE_AND_REVIEW_STANDARD.md`
- `docs/09-vault-brain/05-playbooks/LIVE_OPERATIONS_FIX.md`
- `docs/09-vault-brain/04-workflows/SUPABASE_MIGRATION_WORKFLOW.md`
- `docs/09-vault-brain/05-playbooks/DATA_MIGRATION.md`
- `docs/09-vault-brain/06-data/GOOGLE_SHEETS_LEGACY.md`
- `docs/09-vault-brain/06-data/SUPABASE_CONTRACTS.md`
- `docs/09-vault-brain/01-identity/OOM_SAKKIE.md`
- `docs/09-vault-brain/02-agents/farm/OOM_SAKKIE.md`
- `docs/09-vault-brain/04-workflows/OOM_SAKKIE_OWNER_ATTENTION_QUEUE_WORKFLOW.md`

## Static Agent Assets

- `static/assets/agents/oom-sakkie/agent.md`
- `static/assets/agents/sam/agent.md`
- `static/assets/agents/beacon/agent.md`
- `static/assets/agents/herdmaster/agent.md`
- `static/assets/agents/rootline/agent.md`
- `static/assets/agents/quartermaster/agent.md`
- `static/assets/agents/gatekeeper/agent.md`
- `static/assets/agents/butcher/agent.md`
- `static/assets/agents/ledger/agent.md`

## Runtime/Code Sources

- `modules/charlie/vault_retrieval.py` - canonical mandatory-pack registry,
  mission classification and forbidden-doctrine source coverage.
- `modules/charlie/vault_alignment.py` - deterministic repository and authority-map
  validation for every mandatory pack.
- `modules/charlie/source_map.py`
- `modules/charlie/mission_store.py`
- `modules/charlie/vault_store.py`
- `modules/charlie/execution_bridge.py`
- `modules/charlie/improvement_analyst.py`
- `scripts/build_vault_cutover_manifest.py` - deterministic, non-destructive
  physical-cutover manifest builder and validator.
- `static/js/charlieMissionControl.js`
- `templates/charlie.html`
- `tests/test_charlie_*.py`
- `tests/test_vault_cutover_manifest.py`

Owner-review cutover artifacts:

- `docs/09-vault-brain/10-source-map/VAULT_PHYSICAL_CUTOVER_MANIFEST.md`
- `docs/09-vault-brain/10-source-map/VAULT_PHYSICAL_CUTOVER_MANIFEST.json`

These artifacts propose future physical disposition only. They are not doctrine
and never authorize a move, archive, deletion or pointer rewrite.

Batch 5 archived the five reconciled top-level legacy AI governance files
intact. Their active role, prompt and response authority now resolves only
through the focused Vault packs. See `VAULT_CUTOVER_BATCH5_RECONCILIATION.md`
for the unique-fact disposition and archive evidence.

Batch 6 archived the remaining BEACON and SAM documents from that legacy
family. No tracked legacy AI document remains active. See
`VAULT_CUTOVER_BATCH6_RECONCILIATION.md` for the unique-fact disposition.

## Archived After Migration

Batch 27 archived the complete private Storyworks/Chronicle Vault validation
package under `docs/99-archive/vault-cutover/planning/storyworks/`. It is
historical evidence only and is not BEACON, farm media, active agent doctrine,
current mission state or publication authority.

Batch 20 archived sixteen general-operations plans, dated evidence/checklists,
configuration migrations and placeholder runbooks under
`docs/99-archive/vault-cutover/docs/06-operations/`. Current testing, release,
deployment, UI, migration, livestock-disclosure and live-fix rules now resolve
only through the focused Vault authorities above.

Batch 19 archived the dated CORE operating-spine, Build Relay, private
executive, runtime-recovery, activation and dependency-retirement evidence under
`docs/99-archive/vault-cutover/docs/06-operations/`. Current authority remains
in the focused CHARLIE/CORE identities, mission workflow and deployment
standard; archived provider inventories are never current state.

Batch 21 archived twenty-two HERDMASTER plans and handovers. Current animal,
breeding, exposure, litter, weaning, health, loss, purpose, allocation and
lifecycle-analytics authority remains only in focused Vault agent, workflow,
business-rule, data and UI files. See
`VAULT_CUTOVER_BATCH21_RECONCILIATION.md`.

Batch 22 archived thirty OOM SAKKIE plans, handovers, scorecards and runbooks.
Current manager, family-access, dialogue, scheduling, specialist, protected-
action, provider-delivery and browser authority remains only in focused Vault
identity, agent, workflow and standards files. See
`VAULT_CUTOVER_BATCH22_RECONCILIATION.md`.

Batch 7 archived two superseded external UI briefs. They are historical design
evidence only; current UI authority remains the mandatory Facelift and UI
Dashboard standards. See `VAULT_CUTOVER_BATCH7_RECONCILIATION.md`.

Batch 8 retained the remaining external candidates as technical/source evidence
after complete review. They cannot act as agent doctrine. See
`VAULT_CUTOVER_BATCH8_RECONCILIATION.md`.

Batch 9 reduced seven legacy start-here/process/decision-index paths to minimal
compatibility pointers. They remain loadable but are never active doctrine. See
`VAULT_CUTOVER_BATCH9_RECONCILIATION.md`.

Batch 10 reduced the root Claude guidance and four legacy status/navigation
paths to minimal compatibility pointers. Technical commands/asset locations do
not grant doctrine or live-state authority. See
`VAULT_CUTOVER_BATCH10_RECONCILIATION.md`.

Batch 11 consolidated current runner, mission and deployment procedures into
focused Vault files and reduced their three legacy paths to compatibility
pointers. See `VAULT_CUTOVER_BATCH11_RECONCILIATION.md`.

Batch 12 reconciled the stale current-state and roadmap projections, then
reduced both paths to compatibility pointers. Durable live mission truth now
resolves only to the Control Tower register and fresh attributable evidence.
See `VAULT_CUTOVER_BATCH12_RECONCILIATION.md`.

Batch 13 reconciled the final start-here product projection into focused Oom
Sakkie identity and UI standards, then reduced the legacy path to a
compatibility pointer. See `VAULT_CUTOVER_BATCH13_RECONCILIATION.md`.

- `docs/00-start-here/CLAUDE_REVIEW_HANDOFF.md` (non-doctrine compatibility
  pointer to current Vault review standards)
- `docs/99-archive/legacy/planning_CHAT_2026-04_n8n_sales_agent_rewire.md`
