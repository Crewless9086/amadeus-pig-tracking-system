# Vault Physical Cutover Manifest

Status: Batch 25 business-module reconciliation complete; no further physical change authorized.

Version: `vault_physical_cutover_manifest_v22`
Baseline: `19e21ebcce73de2c51dcd21e9ddcc37242246b38`
Generated from HEAD: `19e21ebcce73de2c51dcd21e9ddcc37242246b38`
Tracked Markdown/MDX files covered: **534**
Validation: **PASS**

This manifest records completed Batches 5 through 24 and schedules later
dispositions only. It does not authorize another move, archive, deletion, pointer
rewrite, deployment, runtime action or production change. Every remaining entry
keeps `physical_change_authorized: false`.

## Disposition totals

| Disposition | Count |
| --- | ---: |
| `EXTRACT_THEN_ARCHIVE` | 42 |
| `KEEP_ARCHIVE` | 165 |
| `KEEP_CONTROLLING_EXCEPTION` | 2 |
| `KEEP_CURRENT_STATE` | 2 |
| `KEEP_GENERATED_PROJECTION` | 9 |
| `KEEP_POINTER` | 18 |
| `KEEP_TECHNICAL` | 31 |
| `KEEP_TRANSITIONAL` | 72 |
| `KEEP_VAULT` | 193 |

## Remaining execution schedule

The remaining 52 physical-reconciliation entries are assigned
to exactly one of Batches 25 through 27. Batch 28 owns the 72 transitional
exit-test decisions; Batch 29 owns deployed Brain Guard acceptance.
This schedule is an ordering contract, not physical-change authority.

| Batch | Family | Entries |
| ---: | --- | ---: |
| 15 | `generated_agent_projections` | COMPLETE (9) |
| 16 | `decisions_and_migration_index` | COMPLETE (3) |
| 17 | `sheets_migration` | COMPLETE (12) |
| 18 | `core_missions` | COMPLETE (10) |
| 19 | `core_operating_spine` | COMPLETE (18) |
| 20 | `general_operations` | COMPLETE (16) |
| 21 | `herdmaster` | COMPLETE (22) |
| 22 | `oom_sakkie` | COMPLETE (30) |
| 23 | `rootline` | COMPLETE (13) |
| 24 | `sam_revenue` | COMPLETE (5) |
| 26 | `planning_and_inbox` | 8 |
| 27 | `storyworks` | 34 |
| 28 | `transitional_exit_tests` | 72 |
| 29 | `deployed_brain_guard_acceptance` | operational proof |

## Safety gates

- Transitional n8n and Google Sheets references remain until their named exit tests pass.
- Historical evidence defaults to archive, not deletion.
- A delete candidate requires zero exact path references, an exact replacement, a tiny retired/superseded source, and later owner approval.
- Pointer conversion requires unique-fact reconciliation first.
- Static agent cards require a proven generated projection before replacement.
- All nine reconciled `docs/05-ai` files are now preserved intact in the archive.
- The two superseded external UI briefs are preserved intact in the archive.
- The four remaining external candidates are retained as current technical/source evidence; the archive-candidate queue is empty.
- Seven legacy navigation/process paths are minimal non-doctrine compatibility pointers to the Vault.
- Five root/status/navigation paths are minimal non-doctrine compatibility pointers with required technical facts retained.
- Three legacy runner/mission/deployment paths are compatibility pointers after current procedures were consolidated into focused Vault files.
- Two stale current-state/roadmap projections are compatibility pointers to the durable register and Vault mission workflow.
- The final legacy product-vision projection is a compatibility pointer after durable Oom Sakkie experience rules moved into focused Vault files.
- Two dated ADR wrappers and the completed legacy migration index are archived after their durable facts were reconciled into focused Vault governance, CORE identity and deployment standards.
- Twelve Google Sheets migration plans/reports are archived intact after current migration, conflict-quarantine, Supabase-first fallback and fallback-retirement rules moved into focused Vault files.
- Sixteen general-operations plans, evidence/checklist ledgers, configuration migrations and placeholder runbooks are archived intact after current rules moved into focused Vault files.
- No later physical change is authorized by this regenerated manifest.

## Exact non-keep review queue

The machine-readable JSON contains every tracked source document (the generated
Markdown report excludes itself). This table lists every
entry whose physical disposition needs later work or owner review.

| Source | Disposition | Planned batch | Destination / replacement | Exact refs | Blockers |
| --- | --- | ---: | --- | ---: | --- |
| `planning/CHARLIE_CORE_EXTENDED_PLAN.md` | `EXTRACT_THEN_ARCHIVE` | 26 | `docs/99-archive/vault-cutover/planning/CHARLIE_CORE_EXTENDED_PLAN.md` | 1 | unique_fact_extraction_required |
| `planning/CODEX_CHAT.md` | `EXTRACT_THEN_ARCHIVE` | 26 | `docs/99-archive/vault-cutover/planning/CODEX_CHAT.md` | 20 | unique_fact_extraction_required |
| `planning/SAM_LIVE_STOCK_SALES_BUILD_PLAN.md` | `EXTRACT_THEN_ARCHIVE` | 26 | `docs/99-archive/vault-cutover/planning/SAM_LIVE_STOCK_SALES_BUILD_PLAN.md` | 4 | unique_fact_extraction_required |
| `planning/ToDoList.md` | `EXTRACT_THEN_ARCHIVE` | 26 | `docs/99-archive/vault-cutover/planning/ToDoList.md` | 8 | unique_fact_extraction_required |
| `planning/inbox/README.md` | `EXTRACT_THEN_ARCHIVE` | 26 | `docs/99-archive/vault-cutover/planning/inbox/README.md` | 0 | unique_fact_extraction_required |
| `planning/inbox/processed/2026-06/ToDoList_2026-06-28_operational_notes.md` | `EXTRACT_THEN_ARCHIVE` | 26 | `docs/99-archive/vault-cutover/planning/inbox/processed/2026-06/ToDoList_2026-06-28_operational_notes.md` | 1 | unique_fact_extraction_required |
| `planning/inbox/processed/2026-06/ToDoList_2026-06-30_live_app_review_notes.md` | `EXTRACT_THEN_ARCHIVE` | 26 | `docs/99-archive/vault-cutover/planning/inbox/processed/2026-06/ToDoList_2026-06-30_live_app_review_notes.md` | 1 | unique_fact_extraction_required |
| `planning/inbox/prompts/REPO_CLEANUP_AND_DOCS_GOVERNANCE_PROMPT.md` | `EXTRACT_THEN_ARCHIVE` | 26 | `docs/99-archive/vault-cutover/planning/inbox/prompts/REPO_CLEANUP_AND_DOCS_GOVERNANCE_PROMPT.md` | 0 | unique_fact_extraction_required |
| `planning/storyworks/BUSINESS_STATE_LADDER.md` | `EXTRACT_THEN_ARCHIVE` | 27 | `docs/99-archive/vault-cutover/planning/storyworks/BUSINESS_STATE_LADDER.md` | 0 | unique_fact_extraction_required |
| `planning/storyworks/CHRONICLE_VAULT_CHANNEL_BIBLE.md` | `EXTRACT_THEN_ARCHIVE` | 27 | `docs/99-archive/vault-cutover/planning/storyworks/CHRONICLE_VAULT_CHANNEL_BIBLE.md` | 0 | unique_fact_extraction_required |
| `planning/storyworks/DECISION_LOG.md` | `EXTRACT_THEN_ARCHIVE` | 27 | `docs/99-archive/vault-cutover/planning/storyworks/DECISION_LOG.md` | 0 | unique_fact_extraction_required |
| `planning/storyworks/MARKET_VALIDATION.md` | `EXTRACT_THEN_ARCHIVE` | 27 | `docs/99-archive/vault-cutover/planning/storyworks/MARKET_VALIDATION.md` | 0 | unique_fact_extraction_required |
| `planning/storyworks/PHASE_0_EXECUTIVE_DECISION_PACK.md` | `EXTRACT_THEN_ARCHIVE` | 27 | `docs/99-archive/vault-cutover/planning/storyworks/PHASE_0_EXECUTIVE_DECISION_PACK.md` | 0 | unique_fact_extraction_required |
| `planning/storyworks/PHASE_0_VALIDATION_PLAN.md` | `EXTRACT_THEN_ARCHIVE` | 27 | `docs/99-archive/vault-cutover/planning/storyworks/PHASE_0_VALIDATION_PLAN.md` | 0 | unique_fact_extraction_required |
| `planning/storyworks/PILOT_SCORECARD.md` | `EXTRACT_THEN_ARCHIVE` | 27 | `docs/99-archive/vault-cutover/planning/storyworks/PILOT_SCORECARD.md` | 0 | unique_fact_extraction_required |
| `planning/storyworks/PRODUCTION_PLAYBOOK.md` | `EXTRACT_THEN_ARCHIVE` | 27 | `docs/99-archive/vault-cutover/planning/storyworks/PRODUCTION_PLAYBOOK.md` | 0 | unique_fact_extraction_required |
| `planning/storyworks/README.md` | `EXTRACT_THEN_ARCHIVE` | 27 | `docs/99-archive/vault-cutover/planning/storyworks/README.md` | 0 | unique_fact_extraction_required |
| `planning/storyworks/RIGHTS_AND_PROVENANCE_POLICY.md` | `EXTRACT_THEN_ARCHIVE` | 27 | `docs/99-archive/vault-cutover/planning/storyworks/RIGHTS_AND_PROVENANCE_POLICY.md` | 0 | unique_fact_extraction_required |
| `planning/storyworks/STATUS.md` | `EXTRACT_THEN_ARCHIVE` | 27 | `docs/99-archive/vault-cutover/planning/storyworks/STATUS.md` | 0 | unique_fact_extraction_required |
| `planning/storyworks/STORYWORKS_BUSINESS_CHARTER.md` | `EXTRACT_THEN_ARCHIVE` | 27 | `docs/99-archive/vault-cutover/planning/storyworks/STORYWORKS_BUSINESS_CHARTER.md` | 0 | unique_fact_extraction_required |
| `planning/storyworks/UNIT_ECONOMICS.md` | `EXTRACT_THEN_ARCHIVE` | 27 | `docs/99-archive/vault-cutover/planning/storyworks/UNIT_ECONOMICS.md` | 0 | unique_fact_extraction_required |
| `planning/storyworks/YOUTUBE_POLICY_RESEARCH.md` | `EXTRACT_THEN_ARCHIVE` | 27 | `docs/99-archive/vault-cutover/planning/storyworks/YOUTUBE_POLICY_RESEARCH.md` | 0 | unique_fact_extraction_required |
| `planning/storyworks/pilots/petra/OWNER_REVIEW_PACKET.md` | `EXTRACT_THEN_ARCHIVE` | 27 | `docs/99-archive/vault-cutover/planning/storyworks/pilots/petra/OWNER_REVIEW_PACKET.md` | 0 | unique_fact_extraction_required |
| `planning/storyworks/pilots/petra/PREPRODUCTION_DECISION_CANDIDATE.md` | `EXTRACT_THEN_ARCHIVE` | 27 | `docs/99-archive/vault-cutover/planning/storyworks/pilots/petra/PREPRODUCTION_DECISION_CANDIDATE.md` | 0 | unique_fact_extraction_required |
| `planning/storyworks/pilots/petra/PRONUNCIATION_REVIEW_SHEET.md` | `EXTRACT_THEN_ARCHIVE` | 27 | `docs/99-archive/vault-cutover/planning/storyworks/pilots/petra/PRONUNCIATION_REVIEW_SHEET.md` | 0 | unique_fact_extraction_required |
| `planning/storyworks/pilots/petra/SYNTHETIC_NARRATION_EVALUATION.md` | `EXTRACT_THEN_ARCHIVE` | 27 | `docs/99-archive/vault-cutover/planning/storyworks/pilots/petra/SYNTHETIC_NARRATION_EVALUATION.md` | 0 | unique_fact_extraction_required |
| `planning/storyworks/pilots/petra/brief.md` | `EXTRACT_THEN_ARCHIVE` | 27 | `docs/99-archive/vault-cutover/planning/storyworks/pilots/petra/brief.md` | 0 | unique_fact_extraction_required |
| `planning/storyworks/pilots/petra/copyright_reuse_review.md` | `EXTRACT_THEN_ARCHIVE` | 27 | `docs/99-archive/vault-cutover/planning/storyworks/pilots/petra/copyright_reuse_review.md` | 0 | unique_fact_extraction_required |
| `planning/storyworks/pilots/petra/description.md` | `EXTRACT_THEN_ARCHIVE` | 27 | `docs/99-archive/vault-cutover/planning/storyworks/pilots/petra/description.md` | 0 | unique_fact_extraction_required |
| `planning/storyworks/pilots/petra/disclosure_review.md` | `EXTRACT_THEN_ARCHIVE` | 27 | `docs/99-archive/vault-cutover/planning/storyworks/pilots/petra/disclosure_review.md` | 0 | unique_fact_extraction_required |
| `planning/storyworks/pilots/petra/edit_plan.md` | `EXTRACT_THEN_ARCHIVE` | 27 | `docs/99-archive/vault-cutover/planning/storyworks/pilots/petra/edit_plan.md` | 0 | unique_fact_extraction_required |
| `planning/storyworks/pilots/petra/fact_check.md` | `EXTRACT_THEN_ARCHIVE` | 27 | `docs/99-archive/vault-cutover/planning/storyworks/pilots/petra/fact_check.md` | 0 | unique_fact_extraction_required |
| `planning/storyworks/pilots/petra/measurement_plan.md` | `EXTRACT_THEN_ARCHIVE` | 27 | `docs/99-archive/vault-cutover/planning/storyworks/pilots/petra/measurement_plan.md` | 0 | unique_fact_extraction_required |
| `planning/storyworks/pilots/petra/music_rights.md` | `EXTRACT_THEN_ARCHIVE` | 27 | `docs/99-archive/vault-cutover/planning/storyworks/pilots/petra/music_rights.md` | 0 | unique_fact_extraction_required |
| `planning/storyworks/pilots/petra/narration_plan.md` | `EXTRACT_THEN_ARCHIVE` | 27 | `docs/99-archive/vault-cutover/planning/storyworks/pilots/petra/narration_plan.md` | 0 | unique_fact_extraction_required |
| `planning/storyworks/pilots/petra/packaging.md` | `EXTRACT_THEN_ARCHIVE` | 27 | `docs/99-archive/vault-cutover/planning/storyworks/pilots/petra/packaging.md` | 0 | unique_fact_extraction_required |
| `planning/storyworks/pilots/petra/prototypes/QA.md` | `EXTRACT_THEN_ARCHIVE` | 27 | `docs/99-archive/vault-cutover/planning/storyworks/pilots/petra/prototypes/QA.md` | 0 | unique_fact_extraction_required |
| `planning/storyworks/pilots/petra/qa_report.md` | `EXTRACT_THEN_ARCHIVE` | 27 | `docs/99-archive/vault-cutover/planning/storyworks/pilots/petra/qa_report.md` | 0 | unique_fact_extraction_required |
| `planning/storyworks/pilots/petra/rights_evidence_index.md` | `EXTRACT_THEN_ARCHIVE` | 27 | `docs/99-archive/vault-cutover/planning/storyworks/pilots/petra/rights_evidence_index.md` | 0 | unique_fact_extraction_required |
| `planning/storyworks/pilots/petra/script.md` | `EXTRACT_THEN_ARCHIVE` | 27 | `docs/99-archive/vault-cutover/planning/storyworks/pilots/petra/script.md` | 0 | unique_fact_extraction_required |
| `planning/storyworks/pilots/petra/sources.md` | `EXTRACT_THEN_ARCHIVE` | 27 | `docs/99-archive/vault-cutover/planning/storyworks/pilots/petra/sources.md` | 0 | unique_fact_extraction_required |
| `planning/storyworks/pilots/petra/time_cost_report.md` | `EXTRACT_THEN_ARCHIVE` | 27 | `docs/99-archive/vault-cutover/planning/storyworks/pilots/petra/time_cost_report.md` | 0 | unique_fact_extraction_required |

## Validation findings

- None.
