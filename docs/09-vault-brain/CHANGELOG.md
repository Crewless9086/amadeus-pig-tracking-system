# Vault Brain Changelog

## 2026-07-07

- Added CHARLIE CORE Memory And Mission Recall to the implementation source map so memory-runtime, mission-recall, recovery-packet, send-back, blocked-state, resumed-mission, handoff, and agent-ledger missions select the existing runtime, replay, and test sources before advising or building.

## 2026-07-06

- Added Brain & Memory v2 Stage 1 doctrine defining memory classes, typed memory record shape, source-of-truth boundaries, recall/write/forget rules, privacy boundaries, promotion gates, and agent boundaries for CHARLIE, CHARLIE CORE, SAM, Beacon, Oom Sakkie, and future agents.
- Clarified that memory records are source-linked recall aids and cannot outrank owner instructions, runtime truth, or owner-reviewed Vault Brain doctrine.
- Added Herdmaster Pig Allocation alert rules and implementation design authority for missing data, purpose review due, meat window timing, slaughter candidates, slow-grower feed risk, breeding candidates, stale weights, sold/exited conflicts, and future sow replacement alerts.
- Marked the alert layer as advisory, read-only, owner-gated, and blocked from farm lifecycle, sales, slaughter, reservation, payment, customer-send, public-post, migration, or production-data writes until separately approved.
- Corrected the Pig Allocation/Herdmaster implementation source map to reference the existing legacy farm sheet docs (`PIG_MASTER`, `PIG_OVERVIEW`, and `WEIGHT_LOG`) instead of a missing aggregate `FARM.md` file.

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
