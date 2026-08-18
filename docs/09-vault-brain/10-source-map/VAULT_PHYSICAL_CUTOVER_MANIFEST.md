# Vault Physical Cutover Manifest

Status: regenerated after approved Batch 9 pointer cutover; no further physical change authorized.

Version: `vault_physical_cutover_manifest_v6`
Baseline: `0f765f921eab75c136c4dc12a799811bc794b15e`
Generated from HEAD: `0f765f921eab75c136c4dc12a799811bc794b15e`
Tracked Markdown/MDX files covered: **518**
Validation: **PASS**

This manifest records completed Batches 5 through 9 and proposes later
dispositions only. It does not authorize another move, archive, deletion, pointer
rewrite, deployment, runtime action or production change. Every remaining entry
keeps `physical_change_authorized: false`.

## Disposition totals

| Disposition | Count |
| --- | ---: |
| `EXTRACT_THEN_ARCHIVE` | 108 |
| `KEEP_ARCHIVE` | 26 |
| `KEEP_CONTROLLING_EXCEPTION` | 2 |
| `KEEP_CURRENT_STATE` | 2 |
| `KEEP_POINTER` | 7 |
| `KEEP_TECHNICAL` | 31 |
| `KEEP_TRANSITIONAL` | 72 |
| `KEEP_VAULT` | 177 |
| `POINTER_AFTER_RECONCILIATION` | 11 |
| `RECONCILE_GENERATED_PROJECTION` | 9 |
| `SPLIT_RUNBOOK_THEN_ARCHIVE_HISTORY` | 73 |

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
- No later physical change is authorized by this regenerated manifest.

## Exact non-keep review queue

The machine-readable JSON contains every tracked source document (the generated
Markdown report excludes itself). This table lists every
entry whose physical disposition needs later work or owner review.

| Source | Disposition | Destination / replacement | Exact refs | Blockers |
| --- | --- | --- | ---: | --- |
| `CLAUDE.md` | `POINTER_AFTER_RECONCILIATION` | `docs/09-vault-brain/README.md` | 2 | unique_fact_reconciliation_required |
| `docs/00-start-here/AGENT_ASSET_REGISTER.md` | `POINTER_AFTER_RECONCILIATION` | `docs/09-vault-brain/README.md` | 1 | unique_fact_reconciliation_required |
| `docs/00-start-here/AGENT_PORTFOLIO_STATUS.md` | `POINTER_AFTER_RECONCILIATION` | `docs/09-vault-brain/README.md` | 0 | unique_fact_reconciliation_required |
| `docs/00-start-here/CHARLIE_CORE_AGENT_RUNNER_V2.md` | `POINTER_AFTER_RECONCILIATION` | `docs/09-vault-brain/04-workflows/CHARLIE_MISSION_WORKFLOW.md` | 6 | unique_fact_reconciliation_required |
| `docs/00-start-here/CHARLIE_MISSION_PROTOCOL.md` | `POINTER_AFTER_RECONCILIATION` | `docs/09-vault-brain/04-workflows/CHARLIE_MISSION_WORKFLOW.md` | 14 | unique_fact_reconciliation_required |
| `docs/00-start-here/CURRENT_STATE.md` | `POINTER_AFTER_RECONCILIATION` | `docs/09-vault-brain/README.md` | 24 | unique_fact_reconciliation_required |
| `docs/00-start-here/DEPLOYMENT_SOP.md` | `POINTER_AFTER_RECONCILIATION` | `docs/09-vault-brain/07-standards/DEPLOYMENT_STANDARD.md` | 10 | unique_fact_reconciliation_required |
| `docs/00-start-here/NEXT_STEPS.md` | `POINTER_AFTER_RECONCILIATION` | `docs/09-vault-brain/README.md` | 28 | unique_fact_reconciliation_required |
| `docs/00-start-here/OPERATING_STATUS.md` | `POINTER_AFTER_RECONCILIATION` | `docs/09-vault-brain/README.md` | 0 | unique_fact_reconciliation_required |
| `docs/00-start-here/OWNER_INBOX_GUIDE.md` | `POINTER_AFTER_RECONCILIATION` | `docs/09-vault-brain/README.md` | 3 | unique_fact_reconciliation_required |
| `docs/00-start-here/PRODUCT_VISION.md` | `POINTER_AFTER_RECONCILIATION` | `docs/09-vault-brain/README.md` | 6 | unique_fact_reconciliation_required |
| `docs/06-operations/AGENTIC_BUSINESS_OS_IMPLEMENTATION_ROADMAP.md` | `SPLIT_RUNBOOK_THEN_ARCHIVE_HISTORY` | `docs/99-archive/vault-cutover/docs/06-operations/AGENTIC_BUSINESS_OS_IMPLEMENTATION_ROADMAP.md` | 0 | runbook_history_split_required |
| `docs/06-operations/AGENTIC_BUSINESS_OS_PHASE_2_7_EVIDENCE.md` | `EXTRACT_THEN_ARCHIVE` | `docs/99-archive/vault-cutover/docs/06-operations/AGENTIC_BUSINESS_OS_PHASE_2_7_EVIDENCE.md` | 0 | unique_fact_extraction_required |
| `docs/06-operations/AGENTIC_FARM_RUNTIME_PHASE0_DEPENDENCY_RETIREMENT_REGISTER.md` | `SPLIT_RUNBOOK_THEN_ARCHIVE_HISTORY` | `docs/99-archive/vault-cutover/docs/06-operations/AGENTIC_FARM_RUNTIME_PHASE0_DEPENDENCY_RETIREMENT_REGISTER.md` | 3 | runbook_history_split_required |
| `docs/06-operations/AGENTIC_FARM_RUNTIME_PROGRAMME.md` | `SPLIT_RUNBOOK_THEN_ARCHIVE_HISTORY` | `docs/99-archive/vault-cutover/docs/06-operations/AGENTIC_FARM_RUNTIME_PROGRAMME.md` | 2 | runbook_history_split_required |
| `docs/06-operations/AGENTIC_OPERATING_SYSTEM_PROGRAM.md` | `SPLIT_RUNBOOK_THEN_ARCHIVE_HISTORY` | `docs/99-archive/vault-cutover/docs/06-operations/AGENTIC_OPERATING_SYSTEM_PROGRAM.md` | 1 | runbook_history_split_required |
| `docs/06-operations/BUILD_RELAY.md` | `SPLIT_RUNBOOK_THEN_ARCHIVE_HISTORY` | `docs/99-archive/vault-cutover/docs/06-operations/BUILD_RELAY.md` | 1 | runbook_history_split_required |
| `docs/06-operations/CHARLIE_AGENT_WORKFORCE.md` | `SPLIT_RUNBOOK_THEN_ARCHIVE_HISTORY` | `docs/99-archive/vault-cutover/docs/06-operations/CHARLIE_AGENT_WORKFORCE.md` | 0 | runbook_history_split_required |
| `docs/06-operations/CHARLIE_BUILD_RELAY_PLAN.md` | `SPLIT_RUNBOOK_THEN_ARCHIVE_HISTORY` | `docs/99-archive/vault-cutover/docs/06-operations/CHARLIE_BUILD_RELAY_PLAN.md` | 2 | runbook_history_split_required |
| `docs/06-operations/CHARLIE_CORE_KERNEL_RELIABILITY.md` | `SPLIT_RUNBOOK_THEN_ARCHIVE_HISTORY` | `docs/99-archive/vault-cutover/docs/06-operations/CHARLIE_CORE_KERNEL_RELIABILITY.md` | 0 | runbook_history_split_required |
| `docs/06-operations/CHARLIE_CORE_RUNTIME_RECOVERY.md` | `SPLIT_RUNBOOK_THEN_ARCHIVE_HISTORY` | `docs/99-archive/vault-cutover/docs/06-operations/CHARLIE_CORE_RUNTIME_RECOVERY.md` | 0 | runbook_history_split_required |
| `docs/06-operations/CHARLIE_EXECUTIVE_CONTROL_PLANE.md` | `SPLIT_RUNBOOK_THEN_ARCHIVE_HISTORY` | `docs/99-archive/vault-cutover/docs/06-operations/CHARLIE_EXECUTIVE_CONTROL_PLANE.md` | 1 | runbook_history_split_required |
| `docs/06-operations/CHARLIE_EXECUTIVE_LIVENESS_CONTRACT.md` | `SPLIT_RUNBOOK_THEN_ARCHIVE_HISTORY` | `docs/99-archive/vault-cutover/docs/06-operations/CHARLIE_EXECUTIVE_LIVENESS_CONTRACT.md` | 1 | runbook_history_split_required |
| `docs/06-operations/CHARLIE_LIVE_EXECUTIVE_V1.md` | `SPLIT_RUNBOOK_THEN_ARCHIVE_HISTORY` | `docs/99-archive/vault-cutover/docs/06-operations/CHARLIE_LIVE_EXECUTIVE_V1.md` | 1 | runbook_history_split_required |
| `docs/06-operations/CHARLIE_PRIVATE_EXECUTIVE_INTERFACE.md` | `SPLIT_RUNBOOK_THEN_ARCHIVE_HISTORY` | `docs/99-archive/vault-cutover/docs/06-operations/CHARLIE_PRIVATE_EXECUTIVE_INTERFACE.md` | 2 | runbook_history_split_required |
| `docs/06-operations/CHARLIE_PRIVATE_EXECUTIVE_MASTER_PLAN.md` | `SPLIT_RUNBOOK_THEN_ARCHIVE_HISTORY` | `docs/99-archive/vault-cutover/docs/06-operations/CHARLIE_PRIVATE_EXECUTIVE_MASTER_PLAN.md` | 2 | runbook_history_split_required |
| `docs/06-operations/CHARLIE_SHARED_AGENT_RUNTIME.md` | `SPLIT_RUNBOOK_THEN_ARCHIVE_HISTORY` | `docs/99-archive/vault-cutover/docs/06-operations/CHARLIE_SHARED_AGENT_RUNTIME.md` | 0 | runbook_history_split_required |
| `docs/06-operations/CMQ_20260813_03_APPLICATION_PREVIEW_WIRING_HANDOVER.md` | `EXTRACT_THEN_ARCHIVE` | `docs/99-archive/vault-cutover/docs/06-operations/CMQ_20260813_03_APPLICATION_PREVIEW_WIRING_HANDOVER.md` | 1 | unique_fact_extraction_required |
| `docs/06-operations/CMQ_20260813_03_CANONICAL_CLAIM_EXECUTOR_COMPATIBILITY.md` | `SPLIT_RUNBOOK_THEN_ARCHIVE_HISTORY` | `docs/99-archive/vault-cutover/docs/06-operations/CMQ_20260813_03_CANONICAL_CLAIM_EXECUTOR_COMPATIBILITY.md` | 1 | runbook_history_split_required |
| `docs/06-operations/CMQ_20260813_03_CANONICAL_PREVIEW_SOURCE_HANDOVER.md` | `EXTRACT_THEN_ARCHIVE` | `docs/99-archive/vault-cutover/docs/06-operations/CMQ_20260813_03_CANONICAL_PREVIEW_SOURCE_HANDOVER.md` | 1 | unique_fact_extraction_required |
| `docs/06-operations/CMQ_20260813_03_GROUPED_WEIGHT_MOVEMENT_RECONCILIATION.md` | `SPLIT_RUNBOOK_THEN_ARCHIVE_HISTORY` | `docs/99-archive/vault-cutover/docs/06-operations/CMQ_20260813_03_GROUPED_WEIGHT_MOVEMENT_RECONCILIATION.md` | 1 | runbook_history_split_required |
| `docs/06-operations/CMQ_20260813_03_OOM_TYPED_PREVIEW_WIRING_HANDOVER.md` | `EXTRACT_THEN_ARCHIVE` | `docs/99-archive/vault-cutover/docs/06-operations/CMQ_20260813_03_OOM_TYPED_PREVIEW_WIRING_HANDOVER.md` | 1 | unique_fact_extraction_required |
| `docs/06-operations/CMQ_20260813_05_ATOMIC_BOOTSTRAP_ADMISSION.md` | `SPLIT_RUNBOOK_THEN_ARCHIVE_HISTORY` | `docs/99-archive/vault-cutover/docs/06-operations/CMQ_20260813_05_ATOMIC_BOOTSTRAP_ADMISSION.md` | 1 | runbook_history_split_required |
| `docs/06-operations/CMQ_20260813_05_CURRENT_PORTFOLIO_BASELINE_PLAN.md` | `SPLIT_RUNBOOK_THEN_ARCHIVE_HISTORY` | `docs/99-archive/vault-cutover/docs/06-operations/CMQ_20260813_05_CURRENT_PORTFOLIO_BASELINE_PLAN.md` | 0 | runbook_history_split_required |
| `docs/06-operations/CMQ_20260813_05_PHASE_A_PRIVATE_INPUT.md` | `SPLIT_RUNBOOK_THEN_ARCHIVE_HISTORY` | `docs/99-archive/vault-cutover/docs/06-operations/CMQ_20260813_05_PHASE_A_PRIVATE_INPUT.md` | 1 | runbook_history_split_required |
| `docs/06-operations/CMQ_20260813_05_PHASE_A_SHADOW_CONTROL_TOWER.md` | `SPLIT_RUNBOOK_THEN_ARCHIVE_HISTORY` | `docs/99-archive/vault-cutover/docs/06-operations/CMQ_20260813_05_PHASE_A_SHADOW_CONTROL_TOWER.md` | 1 | runbook_history_split_required |
| `docs/06-operations/CMQ_20260813_05_PORTFOLIO_CLASSIFICATION.md` | `SPLIT_RUNBOOK_THEN_ARCHIVE_HISTORY` | `docs/99-archive/vault-cutover/docs/06-operations/CMQ_20260813_05_PORTFOLIO_CLASSIFICATION.md` | 1 | runbook_history_split_required |
| `docs/06-operations/CODEX_CHAT_WORKFLOW.md` | `SPLIT_RUNBOOK_THEN_ARCHIVE_HISTORY` | `docs/99-archive/vault-cutover/docs/06-operations/CODEX_CHAT_WORKFLOW.md` | 1 | runbook_history_split_required |
| `docs/06-operations/CONTINUOUS_AGENT_ALIGNMENT_AUDIT_20260817.md` | `EXTRACT_THEN_ARCHIVE` | `docs/99-archive/vault-cutover/docs/06-operations/CONTINUOUS_AGENT_ALIGNMENT_AUDIT_20260817.md` | 1 | unique_fact_extraction_required |
| `docs/06-operations/CORE_PROVIDER_ORIGIN_ACTIVATION_RAIL.md` | `SPLIT_RUNBOOK_THEN_ARCHIVE_HISTORY` | `docs/99-archive/vault-cutover/docs/06-operations/CORE_PROVIDER_ORIGIN_ACTIVATION_RAIL.md` | 0 | runbook_history_split_required |
| `docs/06-operations/FARM_OPERATING_DASHBOARD_V2_PLAN.md` | `SPLIT_RUNBOOK_THEN_ARCHIVE_HISTORY` | `docs/99-archive/vault-cutover/docs/06-operations/FARM_OPERATING_DASHBOARD_V2_PLAN.md` | 0 | runbook_history_split_required |
| `docs/06-operations/GOOGLE_SHEETS_TO_SUPABASE_MIGRATION_PLAN.md` | `SPLIT_RUNBOOK_THEN_ARCHIVE_HISTORY` | `docs/99-archive/vault-cutover/docs/06-operations/GOOGLE_SHEETS_TO_SUPABASE_MIGRATION_PLAN.md` | 1 | runbook_history_split_required |
| `docs/06-operations/GS_MIG_1_DRY_RUN_REPORT.md` | `EXTRACT_THEN_ARCHIVE` | `docs/99-archive/vault-cutover/docs/06-operations/GS_MIG_1_DRY_RUN_REPORT.md` | 0 | unique_fact_extraction_required |
| `docs/06-operations/GS_MIG_2_RECONCILIATION_REPORT.md` | `EXTRACT_THEN_ARCHIVE` | `docs/99-archive/vault-cutover/docs/06-operations/GS_MIG_2_RECONCILIATION_REPORT.md` | 0 | unique_fact_extraction_required |
| `docs/06-operations/GS_MIG_3A_DATA_ISSUE_REVIEW.md` | `SPLIT_RUNBOOK_THEN_ARCHIVE_HISTORY` | `docs/99-archive/vault-cutover/docs/06-operations/GS_MIG_3A_DATA_ISSUE_REVIEW.md` | 0 | runbook_history_split_required |
| `docs/06-operations/GS_MIG_3B_IMPORT_POLICY_DECISIONS.md` | `SPLIT_RUNBOOK_THEN_ARCHIVE_HISTORY` | `docs/99-archive/vault-cutover/docs/06-operations/GS_MIG_3B_IMPORT_POLICY_DECISIONS.md` | 0 | runbook_history_split_required |
| `docs/06-operations/GS_MIG_3_BACKFILL_VERIFIER_REPORT.md` | `EXTRACT_THEN_ARCHIVE` | `docs/99-archive/vault-cutover/docs/06-operations/GS_MIG_3_BACKFILL_VERIFIER_REPORT.md` | 0 | unique_fact_extraction_required |
| `docs/06-operations/GS_MIG_5_IMPORT_EXECUTION_REPORT.md` | `EXTRACT_THEN_ARCHIVE` | `docs/99-archive/vault-cutover/docs/06-operations/GS_MIG_5_IMPORT_EXECUTION_REPORT.md` | 0 | unique_fact_extraction_required |
| `docs/06-operations/GS_MIG_5_INITIAL_IMPORT_PLAN.md` | `SPLIT_RUNBOOK_THEN_ARCHIVE_HISTORY` | `docs/99-archive/vault-cutover/docs/06-operations/GS_MIG_5_INITIAL_IMPORT_PLAN.md` | 0 | runbook_history_split_required |
| `docs/06-operations/GS_MIG_6_CONFLICTING_WEIGHT_REVIEW.md` | `SPLIT_RUNBOOK_THEN_ARCHIVE_HISTORY` | `docs/99-archive/vault-cutover/docs/06-operations/GS_MIG_6_CONFLICTING_WEIGHT_REVIEW.md` | 1 | runbook_history_split_required |
| `docs/06-operations/GS_MIG_7B_FORMULA_SHADOW_REPORT.md` | `EXTRACT_THEN_ARCHIVE` | `docs/99-archive/vault-cutover/docs/06-operations/GS_MIG_7B_FORMULA_SHADOW_REPORT.md` | 0 | unique_fact_extraction_required |
| `docs/06-operations/GS_MIG_7_ROUTE_CUTOVER_REPORT.md` | `EXTRACT_THEN_ARCHIVE` | `docs/99-archive/vault-cutover/docs/06-operations/GS_MIG_7_ROUTE_CUTOVER_REPORT.md` | 0 | unique_fact_extraction_required |
| `docs/06-operations/GS_MIG_FINAL_AUDIT.md` | `EXTRACT_THEN_ARCHIVE` | `docs/99-archive/vault-cutover/docs/06-operations/GS_MIG_FINAL_AUDIT.md` | 3 | unique_fact_extraction_required |
| `docs/06-operations/HERDMASTER_AUCTION_SALE_SOURCE_HANDOVER_20260808.md` | `EXTRACT_THEN_ARCHIVE` | `docs/99-archive/vault-cutover/docs/06-operations/HERDMASTER_AUCTION_SALE_SOURCE_HANDOVER_20260808.md` | 0 | unique_fact_extraction_required |
| `docs/06-operations/HERDMASTER_BREEDING_ATTENTION_UI_RECOVERY_PLAN_20260811.md` | `SPLIT_RUNBOOK_THEN_ARCHIVE_HISTORY` | `docs/99-archive/vault-cutover/docs/06-operations/HERDMASTER_BREEDING_ATTENTION_UI_RECOVERY_PLAN_20260811.md` | 0 | runbook_history_split_required |
| `docs/06-operations/HERDMASTER_BREEDING_EVIDENCE_QUALIFIED_HANDOVER.md` | `EXTRACT_THEN_ARCHIVE` | `docs/99-archive/vault-cutover/docs/06-operations/HERDMASTER_BREEDING_EVIDENCE_QUALIFIED_HANDOVER.md` | 0 | unique_fact_extraction_required |
| `docs/06-operations/HERDMASTER_BREEDING_EXPOSURE_RECOVERY_AND_UNKNOWN_PARENT_PLAN_20260812.md` | `SPLIT_RUNBOOK_THEN_ARCHIVE_HISTORY` | `docs/99-archive/vault-cutover/docs/06-operations/HERDMASTER_BREEDING_EXPOSURE_RECOVERY_AND_UNKNOWN_PARENT_PLAN_20260812.md` | 0 | runbook_history_split_required |
| `docs/06-operations/HERDMASTER_BREEDING_EXPOSURE_RECOVERY_SOURCE_HANDOVER_20260812.md` | `EXTRACT_THEN_ARCHIVE` | `docs/99-archive/vault-cutover/docs/06-operations/HERDMASTER_BREEDING_EXPOSURE_RECOVERY_SOURCE_HANDOVER_20260812.md` | 0 | unique_fact_extraction_required |
| `docs/06-operations/HERDMASTER_EXPOSURE_CYCLE_TRANSITION_HANDOVER_20260812.md` | `EXTRACT_THEN_ARCHIVE` | `docs/99-archive/vault-cutover/docs/06-operations/HERDMASTER_EXPOSURE_CYCLE_TRANSITION_HANDOVER_20260812.md` | 0 | unique_fact_extraction_required |
| `docs/06-operations/HERDMASTER_FULL_LIFECYCLE_GENETIC_MERIT_DATA_UX_CONTRACT_20260813.md` | `SPLIT_RUNBOOK_THEN_ARCHIVE_HISTORY` | `docs/99-archive/vault-cutover/docs/06-operations/HERDMASTER_FULL_LIFECYCLE_GENETIC_MERIT_DATA_UX_CONTRACT_20260813.md` | 2 | runbook_history_split_required |
| `docs/06-operations/HERDMASTER_LITTER_SUPERSESSION_SOURCE_HANDOVER.md` | `EXTRACT_THEN_ARCHIVE` | `docs/99-archive/vault-cutover/docs/06-operations/HERDMASTER_LITTER_SUPERSESSION_SOURCE_HANDOVER.md` | 0 | unique_fact_extraction_required |
| `docs/06-operations/HERDMASTER_LITTER_WEANING_RECOVERY_LIT-2026-322B.md` | `SPLIT_RUNBOOK_THEN_ARCHIVE_HISTORY` | `docs/99-archive/vault-cutover/docs/06-operations/HERDMASTER_LITTER_WEANING_RECOVERY_LIT-2026-322B.md` | 0 | runbook_history_split_required |
| `docs/06-operations/HERDMASTER_MORTALITY_FIRST_REAL_ASSESSMENT_20260803.md` | `SPLIT_RUNBOOK_THEN_ARCHIVE_HISTORY` | `docs/99-archive/vault-cutover/docs/06-operations/HERDMASTER_MORTALITY_FIRST_REAL_ASSESSMENT_20260803.md` | 0 | runbook_history_split_required |
| `docs/06-operations/HERDMASTER_MORTALITY_INTELLIGENCE_HANDOVER.md` | `EXTRACT_THEN_ARCHIVE` | `docs/99-archive/vault-cutover/docs/06-operations/HERDMASTER_MORTALITY_INTELLIGENCE_HANDOVER.md` | 0 | unique_fact_extraction_required |
| `docs/06-operations/HERDMASTER_NATURAL_HEALTH_LOSS_SOURCE_HANDOVER.md` | `EXTRACT_THEN_ARCHIVE` | `docs/99-archive/vault-cutover/docs/06-operations/HERDMASTER_NATURAL_HEALTH_LOSS_SOURCE_HANDOVER.md` | 0 | unique_fact_extraction_required |
| `docs/06-operations/HERDMASTER_OP004_SALES_MULTILINE_INTEGRATION_HANDOFF_20260817.md` | `SPLIT_RUNBOOK_THEN_ARCHIVE_HISTORY` | `docs/99-archive/vault-cutover/docs/06-operations/HERDMASTER_OP004_SALES_MULTILINE_INTEGRATION_HANDOFF_20260817.md` | 0 | runbook_history_split_required |
| `docs/06-operations/HERDMASTER_PIGLET_WEANING_OBSERVATION_PLAN_20260812.md` | `SPLIT_RUNBOOK_THEN_ARCHIVE_HISTORY` | `docs/99-archive/vault-cutover/docs/06-operations/HERDMASTER_PIGLET_WEANING_OBSERVATION_PLAN_20260812.md` | 2 | runbook_history_split_required |
| `docs/06-operations/HERDMASTER_PRACTICAL_MATING_SELECTION_PLAN.md` | `SPLIT_RUNBOOK_THEN_ARCHIVE_HISTORY` | `docs/99-archive/vault-cutover/docs/06-operations/HERDMASTER_PRACTICAL_MATING_SELECTION_PLAN.md` | 3 | runbook_history_split_required |
| `docs/06-operations/HERDMASTER_PROACTIVE_MANAGEMENT_ROUND_HANDOVER.md` | `EXTRACT_THEN_ARCHIVE` | `docs/99-archive/vault-cutover/docs/06-operations/HERDMASTER_PROACTIVE_MANAGEMENT_ROUND_HANDOVER.md` | 0 | unique_fact_extraction_required |
| `docs/06-operations/HERDMASTER_SAM_REVIEW_HISTORY_ALLOWLIST_HANDOVER.md` | `EXTRACT_THEN_ARCHIVE` | `docs/99-archive/vault-cutover/docs/06-operations/HERDMASTER_SAM_REVIEW_HISTORY_ALLOWLIST_HANDOVER.md` | 0 | unique_fact_extraction_required |
| `docs/06-operations/HERDMASTER_UNIFIED_BREEDING_CAPTURE_PLAN_20260812.md` | `SPLIT_RUNBOOK_THEN_ARCHIVE_HISTORY` | `docs/99-archive/vault-cutover/docs/06-operations/HERDMASTER_UNIFIED_BREEDING_CAPTURE_PLAN_20260812.md` | 2 | runbook_history_split_required |
| `docs/06-operations/HERDMASTER_WEANING_LED_MATING_RECOVERY_PLAN_20260811.md` | `SPLIT_RUNBOOK_THEN_ARCHIVE_HISTORY` | `docs/99-archive/vault-cutover/docs/06-operations/HERDMASTER_WEANING_LED_MATING_RECOVERY_PLAN_20260811.md` | 0 | runbook_history_split_required |
| `docs/06-operations/HERDMASTER_WEIGHING_BATCH_INTELLIGENCE_SOURCE_HANDOVER_20260811.md` | `EXTRACT_THEN_ARCHIVE` | `docs/99-archive/vault-cutover/docs/06-operations/HERDMASTER_WEIGHING_BATCH_INTELLIGENCE_SOURCE_HANDOVER_20260811.md` | 0 | unique_fact_extraction_required |
| `docs/06-operations/HERDMASTER_WHOLE_HERD_NEXT_ROUND_HANDOVER.md` | `EXTRACT_THEN_ARCHIVE` | `docs/99-archive/vault-cutover/docs/06-operations/HERDMASTER_WHOLE_HERD_NEXT_ROUND_HANDOVER.md` | 0 | unique_fact_extraction_required |
| `docs/06-operations/HERDMASTER_ZIGAY_REVISED_SUPERSESSION_PREVIEW.md` | `SPLIT_RUNBOOK_THEN_ARCHIVE_HISTORY` | `docs/99-archive/vault-cutover/docs/06-operations/HERDMASTER_ZIGAY_REVISED_SUPERSESSION_PREVIEW.md` | 0 | runbook_history_split_required |
| `docs/06-operations/MISSION_LOOP_CONTRACT.md` | `SPLIT_RUNBOOK_THEN_ARCHIVE_HISTORY` | `docs/99-archive/vault-cutover/docs/06-operations/MISSION_LOOP_CONTRACT.md` | 2 | runbook_history_split_required |
| `docs/06-operations/OOM_SAKKIE_ACTIONABLE_DAILY_MANAGER_MISSION_20260812.md` | `SPLIT_RUNBOOK_THEN_ARCHIVE_HISTORY` | `docs/99-archive/vault-cutover/docs/06-operations/OOM_SAKKIE_ACTIONABLE_DAILY_MANAGER_MISSION_20260812.md` | 1 | runbook_history_split_required |
| `docs/06-operations/OOM_SAKKIE_AUTOMATIC_REASSESSMENT_HANDOVER.md` | `EXTRACT_THEN_ARCHIVE` | `docs/99-archive/vault-cutover/docs/06-operations/OOM_SAKKIE_AUTOMATIC_REASSESSMENT_HANDOVER.md` | 0 | unique_fact_extraction_required |
| `docs/06-operations/OOM_SAKKIE_BREEDING_ROUTING_TASK_RETIREMENT_HANDOVER_20260811.md` | `EXTRACT_THEN_ARCHIVE` | `docs/99-archive/vault-cutover/docs/06-operations/OOM_SAKKIE_BREEDING_ROUTING_TASK_RETIREMENT_HANDOVER_20260811.md` | 1 | unique_fact_extraction_required |
| `docs/06-operations/OOM_SAKKIE_BROWSER_BEHAVIOR_CHECKLIST.md` | `SPLIT_RUNBOOK_THEN_ARCHIVE_HISTORY` | `docs/99-archive/vault-cutover/docs/06-operations/OOM_SAKKIE_BROWSER_BEHAVIOR_CHECKLIST.md` | 2 | runbook_history_split_required |
| `docs/06-operations/OOM_SAKKIE_CONTEXTUAL_SPECIALIST_FOLLOWUP_HANDOVER.md` | `EXTRACT_THEN_ARCHIVE` | `docs/99-archive/vault-cutover/docs/06-operations/OOM_SAKKIE_CONTEXTUAL_SPECIALIST_FOLLOWUP_HANDOVER.md` | 0 | unique_fact_extraction_required |
| `docs/06-operations/OOM_SAKKIE_DAILY_FARM_MANAGER_LOOP_HANDOVER.md` | `EXTRACT_THEN_ARCHIVE` | `docs/99-archive/vault-cutover/docs/06-operations/OOM_SAKKIE_DAILY_FARM_MANAGER_LOOP_HANDOVER.md` | 1 | unique_fact_extraction_required |
| `docs/06-operations/OOM_SAKKIE_DURABLE_MORNING_RUNTIME_HANDOVER_20260813.md` | `EXTRACT_THEN_ARCHIVE` | `docs/99-archive/vault-cutover/docs/06-operations/OOM_SAKKIE_DURABLE_MORNING_RUNTIME_HANDOVER_20260813.md` | 0 | unique_fact_extraction_required |
| `docs/06-operations/OOM_SAKKIE_FAMILY_ACCESS_SOURCE_HANDOVER.md` | `EXTRACT_THEN_ARCHIVE` | `docs/99-archive/vault-cutover/docs/06-operations/OOM_SAKKIE_FAMILY_ACCESS_SOURCE_HANDOVER.md` | 3 | unique_fact_extraction_required |
| `docs/06-operations/OOM_SAKKIE_FARM_MANAGER_ROUND_HANDOVER.md` | `EXTRACT_THEN_ARCHIVE` | `docs/99-archive/vault-cutover/docs/06-operations/OOM_SAKKIE_FARM_MANAGER_ROUND_HANDOVER.md` | 1 | unique_fact_extraction_required |
| `docs/06-operations/OOM_SAKKIE_FARM_MANAGER_SOURCE_HANDOVER.md` | `EXTRACT_THEN_ARCHIVE` | `docs/99-archive/vault-cutover/docs/06-operations/OOM_SAKKIE_FARM_MANAGER_SOURCE_HANDOVER.md` | 0 | unique_fact_extraction_required |
| `docs/06-operations/OOM_SAKKIE_FARM_MANAGER_SPINE_SCORECARD_20260809.md` | `SPLIT_RUNBOOK_THEN_ARCHIVE_HISTORY` | `docs/99-archive/vault-cutover/docs/06-operations/OOM_SAKKIE_FARM_MANAGER_SPINE_SCORECARD_20260809.md` | 1 | runbook_history_split_required |
| `docs/06-operations/OOM_SAKKIE_GENERIC_FAMILY_MESSAGE_LIFECYCLE_HANDOVER.md` | `EXTRACT_THEN_ARCHIVE` | `docs/99-archive/vault-cutover/docs/06-operations/OOM_SAKKIE_GENERIC_FAMILY_MESSAGE_LIFECYCLE_HANDOVER.md` | 0 | unique_fact_extraction_required |
| `docs/06-operations/OOM_SAKKIE_HERDMASTER_MANAGEMENT_CONSUMER_HANDOVER.md` | `EXTRACT_THEN_ARCHIVE` | `docs/99-archive/vault-cutover/docs/06-operations/OOM_SAKKIE_HERDMASTER_MANAGEMENT_CONSUMER_HANDOVER.md` | 0 | unique_fact_extraction_required |
| `docs/06-operations/OOM_SAKKIE_HERDMASTER_MORTALITY_CONSUMPTION_HANDOVER.md` | `EXTRACT_THEN_ARCHIVE` | `docs/99-archive/vault-cutover/docs/06-operations/OOM_SAKKIE_HERDMASTER_MORTALITY_CONSUMPTION_HANDOVER.md` | 0 | unique_fact_extraction_required |
| `docs/06-operations/OOM_SAKKIE_LLM_SEMANTIC_FRONT_DOOR_HANDOVER.md` | `EXTRACT_THEN_ARCHIVE` | `docs/99-archive/vault-cutover/docs/06-operations/OOM_SAKKIE_LLM_SEMANTIC_FRONT_DOOR_HANDOVER.md` | 1 | unique_fact_extraction_required |
| `docs/06-operations/OOM_SAKKIE_MANAGER_QUALITY_COMPOSER_HANDOVER.md` | `EXTRACT_THEN_ARCHIVE` | `docs/99-archive/vault-cutover/docs/06-operations/OOM_SAKKIE_MANAGER_QUALITY_COMPOSER_HANDOVER.md` | 0 | unique_fact_extraction_required |
| `docs/06-operations/OOM_SAKKIE_OWNER_ATTENTION_QUEUE_SOURCE_HANDOVER.md` | `EXTRACT_THEN_ARCHIVE` | `docs/99-archive/vault-cutover/docs/06-operations/OOM_SAKKIE_OWNER_ATTENTION_QUEUE_SOURCE_HANDOVER.md` | 1 | unique_fact_extraction_required |
| `docs/06-operations/OOM_SAKKIE_OWNER_OPERATIONAL_CONTINUATION_HANDOVER.md` | `EXTRACT_THEN_ARCHIVE` | `docs/99-archive/vault-cutover/docs/06-operations/OOM_SAKKIE_OWNER_OPERATIONAL_CONTINUATION_HANDOVER.md` | 0 | unique_fact_extraction_required |
| `docs/06-operations/OOM_SAKKIE_OWNER_REQUEST_AGENT_LIFECYCLE_HANDOVER.md` | `EXTRACT_THEN_ARCHIVE` | `docs/99-archive/vault-cutover/docs/06-operations/OOM_SAKKIE_OWNER_REQUEST_AGENT_LIFECYCLE_HANDOVER.md` | 1 | unique_fact_extraction_required |
| `docs/06-operations/OOM_SAKKIE_P0_NATURAL_PREVIEW_CORRECTION_HANDOVER.md` | `EXTRACT_THEN_ARCHIVE` | `docs/99-archive/vault-cutover/docs/06-operations/OOM_SAKKIE_P0_NATURAL_PREVIEW_CORRECTION_HANDOVER.md` | 0 | unique_fact_extraction_required |
| `docs/06-operations/OOM_SAKKIE_P0_OPERATIONAL_INTAKE_RECOVERY_HANDOVER.md` | `EXTRACT_THEN_ARCHIVE` | `docs/99-archive/vault-cutover/docs/06-operations/OOM_SAKKIE_P0_OPERATIONAL_INTAKE_RECOVERY_HANDOVER.md` | 0 | unique_fact_extraction_required |
| `docs/06-operations/OOM_SAKKIE_P0_PIG125_LIFECYCLE_REENTRY_HANDOVER.md` | `EXTRACT_THEN_ARCHIVE` | `docs/99-archive/vault-cutover/docs/06-operations/OOM_SAKKIE_P0_PIG125_LIFECYCLE_REENTRY_HANDOVER.md` | 0 | unique_fact_extraction_required |
| `docs/06-operations/OOM_SAKKIE_PROTECTED_ACTION_RECOVERY_HANDOVER_20260811.md` | `EXTRACT_THEN_ARCHIVE` | `docs/99-archive/vault-cutover/docs/06-operations/OOM_SAKKIE_PROTECTED_ACTION_RECOVERY_HANDOVER_20260811.md` | 1 | unique_fact_extraction_required |
| `docs/06-operations/OOM_SAKKIE_RELAY_PROVIDER_CHRONOLOGY_HANDOVER.md` | `EXTRACT_THEN_ARCHIVE` | `docs/99-archive/vault-cutover/docs/06-operations/OOM_SAKKIE_RELAY_PROVIDER_CHRONOLOGY_HANDOVER.md` | 0 | unique_fact_extraction_required |
| `docs/06-operations/OOM_SAKKIE_ROOTLINE_DAILY_PRESENTATION_HANDOVER.md` | `EXTRACT_THEN_ARCHIVE` | `docs/99-archive/vault-cutover/docs/06-operations/OOM_SAKKIE_ROOTLINE_DAILY_PRESENTATION_HANDOVER.md` | 1 | unique_fact_extraction_required |
| `docs/06-operations/OOM_SAKKIE_ROOTLINE_OPERATIONAL_INTAKE_HANDOVER.md` | `EXTRACT_THEN_ARCHIVE` | `docs/99-archive/vault-cutover/docs/06-operations/OOM_SAKKIE_ROOTLINE_OPERATIONAL_INTAKE_HANDOVER.md` | 0 | unique_fact_extraction_required |
| `docs/06-operations/OOM_SAKKIE_SENTINEL_SINGLE_SHOT_RUNBOOK.md` | `SPLIT_RUNBOOK_THEN_ARCHIVE_HISTORY` | `docs/99-archive/vault-cutover/docs/06-operations/OOM_SAKKIE_SENTINEL_SINGLE_SHOT_RUNBOOK.md` | 0 | runbook_history_split_required |
| `docs/06-operations/OOM_SAKKIE_SPECIALIST_DISPATCH_ACK_HANDOVER.md` | `EXTRACT_THEN_ARCHIVE` | `docs/99-archive/vault-cutover/docs/06-operations/OOM_SAKKIE_SPECIALIST_DISPATCH_ACK_HANDOVER.md` | 0 | unique_fact_extraction_required |
| `docs/06-operations/OOM_SAKKIE_SPECIALIST_OWNER_DECISION_BINDING_HANDOVER.md` | `EXTRACT_THEN_ARCHIVE` | `docs/99-archive/vault-cutover/docs/06-operations/OOM_SAKKIE_SPECIALIST_OWNER_DECISION_BINDING_HANDOVER.md` | 0 | unique_fact_extraction_required |
| `docs/06-operations/OOM_SAKKIE_WITHDRAWAL_RELAY_RECOVERY_HANDOVER.md` | `EXTRACT_THEN_ARCHIVE` | `docs/99-archive/vault-cutover/docs/06-operations/OOM_SAKKIE_WITHDRAWAL_RELAY_RECOVERY_HANDOVER.md` | 0 | unique_fact_extraction_required |
| `docs/06-operations/OP004_LIVE_TRANSFER_DISCLOSURE_CONTRACT_20260816.md` | `SPLIT_RUNBOOK_THEN_ARCHIVE_HISTORY` | `docs/99-archive/vault-cutover/docs/06-operations/OP004_LIVE_TRANSFER_DISCLOSURE_CONTRACT_20260816.md` | 0 | runbook_history_split_required |
| `docs/06-operations/OPERATIONAL_FIXES_EVIDENCE_LOG.md` | `EXTRACT_THEN_ARCHIVE` | `docs/99-archive/vault-cutover/docs/06-operations/OPERATIONAL_FIXES_EVIDENCE_LOG.md` | 2 | unique_fact_extraction_required |
| `docs/06-operations/OPERATIONAL_FIXES_MASTER_PLAN.md` | `SPLIT_RUNBOOK_THEN_ARCHIVE_HISTORY` | `docs/99-archive/vault-cutover/docs/06-operations/OPERATIONAL_FIXES_MASTER_PLAN.md` | 1 | runbook_history_split_required |
| `docs/06-operations/PARINGS_EN_WERPSEL_LIFECYCLE_REDESIGN_PLAN.md` | `SPLIT_RUNBOOK_THEN_ARCHIVE_HISTORY` | `docs/99-archive/vault-cutover/docs/06-operations/PARINGS_EN_WERPSEL_LIFECYCLE_REDESIGN_PLAN.md` | 0 | runbook_history_split_required |
| `docs/06-operations/PHASE_0_CONFIGURATION_GOVERNANCE_BASELINE.md` | `SPLIT_RUNBOOK_THEN_ARCHIVE_HISTORY` | `docs/99-archive/vault-cutover/docs/06-operations/PHASE_0_CONFIGURATION_GOVERNANCE_BASELINE.md` | 0 | runbook_history_split_required |
| `docs/06-operations/PHASE_1_SAFE_NAMESPACE_MIGRATION.md` | `SPLIT_RUNBOOK_THEN_ARCHIVE_HISTORY` | `docs/99-archive/vault-cutover/docs/06-operations/PHASE_1_SAFE_NAMESPACE_MIGRATION.md` | 0 | runbook_history_split_required |
| `docs/06-operations/PIG_PROFILE_LIFE_RECORD_UI_PLAN_20260811.md` | `SPLIT_RUNBOOK_THEN_ARCHIVE_HISTORY` | `docs/99-archive/vault-cutover/docs/06-operations/PIG_PROFILE_LIFE_RECORD_UI_PLAN_20260811.md` | 0 | runbook_history_split_required |
| `docs/06-operations/README.md` | `SPLIT_RUNBOOK_THEN_ARCHIVE_HISTORY` | `docs/99-archive/vault-cutover/docs/06-operations/README.md` | 0 | runbook_history_split_required |
| `docs/06-operations/RELEASE_CHECKLIST.md` | `SPLIT_RUNBOOK_THEN_ARCHIVE_HISTORY` | `docs/99-archive/vault-cutover/docs/06-operations/RELEASE_CHECKLIST.md` | 1 | runbook_history_split_required |
| `docs/06-operations/ROOTLINE_ADAPTIVE_IRRIGATION_MANAGEMENT.md` | `SPLIT_RUNBOOK_THEN_ARCHIVE_HISTORY` | `docs/99-archive/vault-cutover/docs/06-operations/ROOTLINE_ADAPTIVE_IRRIGATION_MANAGEMENT.md` | 0 | runbook_history_split_required |
| `docs/06-operations/ROOTLINE_AGENTIC_DEVICE_MANAGEMENT_PLAN.md` | `SPLIT_RUNBOOK_THEN_ARCHIVE_HISTORY` | `docs/99-archive/vault-cutover/docs/06-operations/ROOTLINE_AGENTIC_DEVICE_MANAGEMENT_PLAN.md` | 2 | runbook_history_split_required |
| `docs/06-operations/ROOTLINE_AUGUST1_ESSENTIAL_WATER_PLAN.md` | `SPLIT_RUNBOOK_THEN_ARCHIVE_HISTORY` | `docs/99-archive/vault-cutover/docs/06-operations/ROOTLINE_AUGUST1_ESSENTIAL_WATER_PLAN.md` | 0 | runbook_history_split_required |
| `docs/06-operations/ROOTLINE_C12345_CANARY_PREFLIGHT.md` | `SPLIT_RUNBOOK_THEN_ARCHIVE_HISTORY` | `docs/99-archive/vault-cutover/docs/06-operations/ROOTLINE_C12345_CANARY_PREFLIGHT.md` | 0 | runbook_history_split_required |
| `docs/06-operations/ROOTLINE_CANONICAL_STATUS_AND_OWNER_ACCESS_RECOVERY_20260811.md` | `EXTRACT_THEN_ARCHIVE` | `docs/99-archive/vault-cutover/docs/06-operations/ROOTLINE_CANONICAL_STATUS_AND_OWNER_ACCESS_RECOVERY_20260811.md` | 2 | unique_fact_extraction_required |
| `docs/06-operations/ROOTLINE_EWELINK_OAUTH_ONBOARDING.md` | `SPLIT_RUNBOOK_THEN_ARCHIVE_HISTORY` | `docs/99-archive/vault-cutover/docs/06-operations/ROOTLINE_EWELINK_OAUTH_ONBOARDING.md` | 1 | runbook_history_split_required |
| `docs/06-operations/ROOTLINE_OPERATING_KNOWLEDGE_REGISTER.md` | `SPLIT_RUNBOOK_THEN_ARCHIVE_HISTORY` | `docs/99-archive/vault-cutover/docs/06-operations/ROOTLINE_OPERATING_KNOWLEDGE_REGISTER.md` | 1 | runbook_history_split_required |
| `docs/06-operations/ROOTLINE_OPERATING_POLICY_REVIEW.md` | `SPLIT_RUNBOOK_THEN_ARCHIVE_HISTORY` | `docs/99-archive/vault-cutover/docs/06-operations/ROOTLINE_OPERATING_POLICY_REVIEW.md` | 0 | runbook_history_split_required |
| `docs/06-operations/ROOTLINE_PHASE_B_HARDWARE_INVENTORY.md` | `SPLIT_RUNBOOK_THEN_ARCHIVE_HISTORY` | `docs/99-archive/vault-cutover/docs/06-operations/ROOTLINE_PHASE_B_HARDWARE_INVENTORY.md` | 0 | runbook_history_split_required |
| `docs/06-operations/ROOTLINE_REMAINING_COMMISSIONING_PACKETS_20260818.md` | `SPLIT_RUNBOOK_THEN_ARCHIVE_HISTORY` | `docs/99-archive/vault-cutover/docs/06-operations/ROOTLINE_REMAINING_COMMISSIONING_PACKETS_20260818.md` | 0 | runbook_history_split_required |
| `docs/06-operations/ROOTLINE_SONOFF_IRRIGATION_EXECUTION_CONTRACT.md` | `SPLIT_RUNBOOK_THEN_ARCHIVE_HISTORY` | `docs/99-archive/vault-cutover/docs/06-operations/ROOTLINE_SONOFF_IRRIGATION_EXECUTION_CONTRACT.md` | 0 | runbook_history_split_required |
| `docs/06-operations/ROOTLINE_SPECIALIST_RESULT_CONTRACT.md` | `SPLIT_RUNBOOK_THEN_ARCHIVE_HISTORY` | `docs/99-archive/vault-cutover/docs/06-operations/ROOTLINE_SPECIALIST_RESULT_CONTRACT.md` | 0 | runbook_history_split_required |
| `docs/06-operations/ROOTLINE_WATER_ENERGY_MANAGER_PHASE1.md` | `SPLIT_RUNBOOK_THEN_ARCHIVE_HISTORY` | `docs/99-archive/vault-cutover/docs/06-operations/ROOTLINE_WATER_ENERGY_MANAGER_PHASE1.md` | 0 | runbook_history_split_required |
| `docs/06-operations/RUNBOOK.md` | `SPLIT_RUNBOOK_THEN_ARCHIVE_HISTORY` | `docs/99-archive/vault-cutover/docs/06-operations/RUNBOOK.md` | 1 | runbook_history_split_required |
| `docs/06-operations/SAM_BEACON_MEAT_FIRST_LAUNCH_READINESS_2026-07-03.md` | `SPLIT_RUNBOOK_THEN_ARCHIVE_HISTORY` | `docs/99-archive/vault-cutover/docs/06-operations/SAM_BEACON_MEAT_FIRST_LAUNCH_READINESS_2026-07-03.md` | 0 | runbook_history_split_required |
| `docs/06-operations/SAM_INBOX_RECONCILIATION_TIMEOUT_HANDOVER.md` | `EXTRACT_THEN_ARCHIVE` | `docs/99-archive/vault-cutover/docs/06-operations/SAM_INBOX_RECONCILIATION_TIMEOUT_HANDOVER.md` | 1 | unique_fact_extraction_required |
| `docs/06-operations/SAM_LIVE_STOCK_COMPLETION_PROGRAM.md` | `SPLIT_RUNBOOK_THEN_ARCHIVE_HISTORY` | `docs/99-archive/vault-cutover/docs/06-operations/SAM_LIVE_STOCK_COMPLETION_PROGRAM.md` | 1 | runbook_history_split_required |
| `docs/06-operations/SAM_MANAGER_SUMMARY_PR691_HANDOVER.md` | `EXTRACT_THEN_ARCHIVE` | `docs/99-archive/vault-cutover/docs/06-operations/SAM_MANAGER_SUMMARY_PR691_HANDOVER.md` | 0 | unique_fact_extraction_required |
| `docs/06-operations/SAM_MEAT_INTAKE_LIVE_SMOKE_CHECKLIST.md` | `SPLIT_RUNBOOK_THEN_ARCHIVE_HISTORY` | `docs/99-archive/vault-cutover/docs/06-operations/SAM_MEAT_INTAKE_LIVE_SMOKE_CHECKLIST.md` | 1 | runbook_history_split_required |
| `docs/06-operations/TESTING_CHECKLIST.md` | `SPLIT_RUNBOOK_THEN_ARCHIVE_HISTORY` | `docs/99-archive/vault-cutover/docs/06-operations/TESTING_CHECKLIST.md` | 2 | runbook_history_split_required |
| `docs/06-operations/TROUBLESHOOTING.md` | `SPLIT_RUNBOOK_THEN_ARCHIVE_HISTORY` | `docs/99-archive/vault-cutover/docs/06-operations/TROUBLESHOOTING.md` | 1 | runbook_history_split_required |
| `docs/06-operations/goals/README.md` | `SPLIT_RUNBOOK_THEN_ARCHIVE_HISTORY` | `docs/99-archive/vault-cutover/docs/06-operations/goals/README.md` | 0 | runbook_history_split_required |
| `docs/07-decisions/ADR_0001_DOCUMENTATION_SOURCE_OF_TRUTH.md` | `EXTRACT_THEN_ARCHIVE` | `docs/99-archive/vault-cutover/docs/07-decisions/ADR_0001_DOCUMENTATION_SOURCE_OF_TRUTH.md` | 1 | unique_fact_extraction_required |
| `docs/07-decisions/ADR_0002_CHARLIE_CORE_TERMINOLOGY_AND_CONFIGURATION.md` | `EXTRACT_THEN_ARCHIVE` | `docs/99-archive/vault-cutover/docs/07-decisions/ADR_0002_CHARLIE_CORE_TERMINOLOGY_AND_CONFIGURATION.md` | 1 | unique_fact_extraction_required |
| `docs/08-business-modules/FARM_CALENDAR_PLAN.md` | `EXTRACT_THEN_ARCHIVE` | `docs/99-archive/vault-cutover/docs/08-business-modules/FARM_CALENDAR_PLAN.md` | 0 | unique_fact_extraction_required |
| `docs/08-business-modules/MEAT_LAUNCH_CAMPAIGN_PACKET.md` | `EXTRACT_THEN_ARCHIVE` | `docs/99-archive/vault-cutover/docs/08-business-modules/MEAT_LAUNCH_CAMPAIGN_PACKET.md` | 6 | unique_fact_extraction_required |
| `docs/08-business-modules/MEAT_PRODUCTION_BATCH_WORKFLOW.md` | `EXTRACT_THEN_ARCHIVE` | `docs/99-archive/vault-cutover/docs/08-business-modules/MEAT_PRODUCTION_BATCH_WORKFLOW.md` | 2 | unique_fact_extraction_required |
| `docs/08-business-modules/MEAT_SALES_LAUNCH_PLAN.md` | `EXTRACT_THEN_ARCHIVE` | `docs/99-archive/vault-cutover/docs/08-business-modules/MEAT_SALES_LAUNCH_PLAN.md` | 9 | unique_fact_extraction_required |
| `docs/08-business-modules/MEAT_SALES_STRESS_TEST_REPORT.md` | `EXTRACT_THEN_ARCHIVE` | `docs/99-archive/vault-cutover/docs/08-business-modules/MEAT_SALES_STRESS_TEST_REPORT.md` | 0 | unique_fact_extraction_required |
| `docs/08-business-modules/MEAT_SALES_WHATSAPP_TEMPLATES.md` | `EXTRACT_THEN_ARCHIVE` | `docs/99-archive/vault-cutover/docs/08-business-modules/MEAT_SALES_WHATSAPP_TEMPLATES.md` | 2 | unique_fact_extraction_required |
| `docs/08-business-modules/PORK_BUSINESS_INTEGRATION_READINESS_MAP.md` | `EXTRACT_THEN_ARCHIVE` | `docs/99-archive/vault-cutover/docs/08-business-modules/PORK_BUSINESS_INTEGRATION_READINESS_MAP.md` | 8 | unique_fact_extraction_required |
| `docs/08-business-modules/PORK_SALES_MODEL.md` | `EXTRACT_THEN_ARCHIVE` | `docs/99-archive/vault-cutover/docs/08-business-modules/PORK_SALES_MODEL.md` | 8 | unique_fact_extraction_required |
| `docs/08-business-modules/README.md` | `EXTRACT_THEN_ARCHIVE` | `docs/99-archive/vault-cutover/docs/08-business-modules/README.md` | 0 | unique_fact_extraction_required |
| `docs/08-business-modules/SAM_FARM_KNOWLEDGE_PACK.md` | `EXTRACT_THEN_ARCHIVE` | `docs/99-archive/vault-cutover/docs/08-business-modules/SAM_FARM_KNOWLEDGE_PACK.md` | 3 | unique_fact_extraction_required |
| `docs/MIGRATION_INDEX.md` | `EXTRACT_THEN_ARCHIVE` | `docs/99-archive/vault-cutover/docs/MIGRATION_INDEX.md` | 1 | unique_fact_extraction_required |
| `planning/CHARLIE_CORE_EXTENDED_PLAN.md` | `EXTRACT_THEN_ARCHIVE` | `docs/99-archive/vault-cutover/planning/CHARLIE_CORE_EXTENDED_PLAN.md` | 1 | unique_fact_extraction_required |
| `planning/CODEX_CHAT.md` | `EXTRACT_THEN_ARCHIVE` | `docs/99-archive/vault-cutover/planning/CODEX_CHAT.md` | 21 | unique_fact_extraction_required |
| `planning/SAM_LIVE_STOCK_SALES_BUILD_PLAN.md` | `EXTRACT_THEN_ARCHIVE` | `docs/99-archive/vault-cutover/planning/SAM_LIVE_STOCK_SALES_BUILD_PLAN.md` | 4 | unique_fact_extraction_required |
| `planning/ToDoList.md` | `EXTRACT_THEN_ARCHIVE` | `docs/99-archive/vault-cutover/planning/ToDoList.md` | 12 | unique_fact_extraction_required |
| `planning/inbox/README.md` | `EXTRACT_THEN_ARCHIVE` | `docs/99-archive/vault-cutover/planning/inbox/README.md` | 0 | unique_fact_extraction_required |
| `planning/inbox/processed/2026-06/ToDoList_2026-06-28_operational_notes.md` | `EXTRACT_THEN_ARCHIVE` | `docs/99-archive/vault-cutover/planning/inbox/processed/2026-06/ToDoList_2026-06-28_operational_notes.md` | 1 | unique_fact_extraction_required |
| `planning/inbox/processed/2026-06/ToDoList_2026-06-30_live_app_review_notes.md` | `EXTRACT_THEN_ARCHIVE` | `docs/99-archive/vault-cutover/planning/inbox/processed/2026-06/ToDoList_2026-06-30_live_app_review_notes.md` | 1 | unique_fact_extraction_required |
| `planning/inbox/prompts/REPO_CLEANUP_AND_DOCS_GOVERNANCE_PROMPT.md` | `EXTRACT_THEN_ARCHIVE` | `docs/99-archive/vault-cutover/planning/inbox/prompts/REPO_CLEANUP_AND_DOCS_GOVERNANCE_PROMPT.md` | 0 | unique_fact_extraction_required |
| `planning/storyworks/BUSINESS_STATE_LADDER.md` | `EXTRACT_THEN_ARCHIVE` | `docs/99-archive/vault-cutover/planning/storyworks/BUSINESS_STATE_LADDER.md` | 1 | unique_fact_extraction_required |
| `planning/storyworks/CHRONICLE_VAULT_CHANNEL_BIBLE.md` | `EXTRACT_THEN_ARCHIVE` | `docs/99-archive/vault-cutover/planning/storyworks/CHRONICLE_VAULT_CHANNEL_BIBLE.md` | 1 | unique_fact_extraction_required |
| `planning/storyworks/DECISION_LOG.md` | `EXTRACT_THEN_ARCHIVE` | `docs/99-archive/vault-cutover/planning/storyworks/DECISION_LOG.md` | 0 | unique_fact_extraction_required |
| `planning/storyworks/MARKET_VALIDATION.md` | `EXTRACT_THEN_ARCHIVE` | `docs/99-archive/vault-cutover/planning/storyworks/MARKET_VALIDATION.md` | 0 | unique_fact_extraction_required |
| `planning/storyworks/PHASE_0_EXECUTIVE_DECISION_PACK.md` | `EXTRACT_THEN_ARCHIVE` | `docs/99-archive/vault-cutover/planning/storyworks/PHASE_0_EXECUTIVE_DECISION_PACK.md` | 1 | unique_fact_extraction_required |
| `planning/storyworks/PHASE_0_VALIDATION_PLAN.md` | `EXTRACT_THEN_ARCHIVE` | `docs/99-archive/vault-cutover/planning/storyworks/PHASE_0_VALIDATION_PLAN.md` | 1 | unique_fact_extraction_required |
| `planning/storyworks/PILOT_SCORECARD.md` | `EXTRACT_THEN_ARCHIVE` | `docs/99-archive/vault-cutover/planning/storyworks/PILOT_SCORECARD.md` | 0 | unique_fact_extraction_required |
| `planning/storyworks/PRODUCTION_PLAYBOOK.md` | `EXTRACT_THEN_ARCHIVE` | `docs/99-archive/vault-cutover/planning/storyworks/PRODUCTION_PLAYBOOK.md` | 1 | unique_fact_extraction_required |
| `planning/storyworks/README.md` | `EXTRACT_THEN_ARCHIVE` | `docs/99-archive/vault-cutover/planning/storyworks/README.md` | 1 | unique_fact_extraction_required |
| `planning/storyworks/RIGHTS_AND_PROVENANCE_POLICY.md` | `EXTRACT_THEN_ARCHIVE` | `docs/99-archive/vault-cutover/planning/storyworks/RIGHTS_AND_PROVENANCE_POLICY.md` | 0 | unique_fact_extraction_required |
| `planning/storyworks/STATUS.md` | `EXTRACT_THEN_ARCHIVE` | `docs/99-archive/vault-cutover/planning/storyworks/STATUS.md` | 1 | unique_fact_extraction_required |
| `planning/storyworks/STORYWORKS_BUSINESS_CHARTER.md` | `EXTRACT_THEN_ARCHIVE` | `docs/99-archive/vault-cutover/planning/storyworks/STORYWORKS_BUSINESS_CHARTER.md` | 1 | unique_fact_extraction_required |
| `planning/storyworks/UNIT_ECONOMICS.md` | `EXTRACT_THEN_ARCHIVE` | `docs/99-archive/vault-cutover/planning/storyworks/UNIT_ECONOMICS.md` | 1 | unique_fact_extraction_required |
| `planning/storyworks/YOUTUBE_POLICY_RESEARCH.md` | `EXTRACT_THEN_ARCHIVE` | `docs/99-archive/vault-cutover/planning/storyworks/YOUTUBE_POLICY_RESEARCH.md` | 0 | unique_fact_extraction_required |
| `planning/storyworks/pilots/petra/OWNER_REVIEW_PACKET.md` | `EXTRACT_THEN_ARCHIVE` | `docs/99-archive/vault-cutover/planning/storyworks/pilots/petra/OWNER_REVIEW_PACKET.md` | 0 | unique_fact_extraction_required |
| `planning/storyworks/pilots/petra/PREPRODUCTION_DECISION_CANDIDATE.md` | `EXTRACT_THEN_ARCHIVE` | `docs/99-archive/vault-cutover/planning/storyworks/pilots/petra/PREPRODUCTION_DECISION_CANDIDATE.md` | 0 | unique_fact_extraction_required |
| `planning/storyworks/pilots/petra/PRONUNCIATION_REVIEW_SHEET.md` | `EXTRACT_THEN_ARCHIVE` | `docs/99-archive/vault-cutover/planning/storyworks/pilots/petra/PRONUNCIATION_REVIEW_SHEET.md` | 0 | unique_fact_extraction_required |
| `planning/storyworks/pilots/petra/SYNTHETIC_NARRATION_EVALUATION.md` | `EXTRACT_THEN_ARCHIVE` | `docs/99-archive/vault-cutover/planning/storyworks/pilots/petra/SYNTHETIC_NARRATION_EVALUATION.md` | 0 | unique_fact_extraction_required |
| `planning/storyworks/pilots/petra/brief.md` | `EXTRACT_THEN_ARCHIVE` | `docs/99-archive/vault-cutover/planning/storyworks/pilots/petra/brief.md` | 0 | unique_fact_extraction_required |
| `planning/storyworks/pilots/petra/copyright_reuse_review.md` | `EXTRACT_THEN_ARCHIVE` | `docs/99-archive/vault-cutover/planning/storyworks/pilots/petra/copyright_reuse_review.md` | 0 | unique_fact_extraction_required |
| `planning/storyworks/pilots/petra/description.md` | `EXTRACT_THEN_ARCHIVE` | `docs/99-archive/vault-cutover/planning/storyworks/pilots/petra/description.md` | 0 | unique_fact_extraction_required |
| `planning/storyworks/pilots/petra/disclosure_review.md` | `EXTRACT_THEN_ARCHIVE` | `docs/99-archive/vault-cutover/planning/storyworks/pilots/petra/disclosure_review.md` | 0 | unique_fact_extraction_required |
| `planning/storyworks/pilots/petra/edit_plan.md` | `EXTRACT_THEN_ARCHIVE` | `docs/99-archive/vault-cutover/planning/storyworks/pilots/petra/edit_plan.md` | 0 | unique_fact_extraction_required |
| `planning/storyworks/pilots/petra/fact_check.md` | `EXTRACT_THEN_ARCHIVE` | `docs/99-archive/vault-cutover/planning/storyworks/pilots/petra/fact_check.md` | 0 | unique_fact_extraction_required |
| `planning/storyworks/pilots/petra/measurement_plan.md` | `EXTRACT_THEN_ARCHIVE` | `docs/99-archive/vault-cutover/planning/storyworks/pilots/petra/measurement_plan.md` | 0 | unique_fact_extraction_required |
| `planning/storyworks/pilots/petra/music_rights.md` | `EXTRACT_THEN_ARCHIVE` | `docs/99-archive/vault-cutover/planning/storyworks/pilots/petra/music_rights.md` | 0 | unique_fact_extraction_required |
| `planning/storyworks/pilots/petra/narration_plan.md` | `EXTRACT_THEN_ARCHIVE` | `docs/99-archive/vault-cutover/planning/storyworks/pilots/petra/narration_plan.md` | 0 | unique_fact_extraction_required |
| `planning/storyworks/pilots/petra/packaging.md` | `EXTRACT_THEN_ARCHIVE` | `docs/99-archive/vault-cutover/planning/storyworks/pilots/petra/packaging.md` | 0 | unique_fact_extraction_required |
| `planning/storyworks/pilots/petra/prototypes/QA.md` | `EXTRACT_THEN_ARCHIVE` | `docs/99-archive/vault-cutover/planning/storyworks/pilots/petra/prototypes/QA.md` | 0 | unique_fact_extraction_required |
| `planning/storyworks/pilots/petra/qa_report.md` | `EXTRACT_THEN_ARCHIVE` | `docs/99-archive/vault-cutover/planning/storyworks/pilots/petra/qa_report.md` | 0 | unique_fact_extraction_required |
| `planning/storyworks/pilots/petra/rights_evidence_index.md` | `EXTRACT_THEN_ARCHIVE` | `docs/99-archive/vault-cutover/planning/storyworks/pilots/petra/rights_evidence_index.md` | 0 | unique_fact_extraction_required |
| `planning/storyworks/pilots/petra/script.md` | `EXTRACT_THEN_ARCHIVE` | `docs/99-archive/vault-cutover/planning/storyworks/pilots/petra/script.md` | 0 | unique_fact_extraction_required |
| `planning/storyworks/pilots/petra/sources.md` | `EXTRACT_THEN_ARCHIVE` | `docs/99-archive/vault-cutover/planning/storyworks/pilots/petra/sources.md` | 0 | unique_fact_extraction_required |
| `planning/storyworks/pilots/petra/time_cost_report.md` | `EXTRACT_THEN_ARCHIVE` | `docs/99-archive/vault-cutover/planning/storyworks/pilots/petra/time_cost_report.md` | 0 | unique_fact_extraction_required |
| `static/assets/agents/beacon/agent.md` | `RECONCILE_GENERATED_PROJECTION` | `docs/09-vault-brain/02-agents/marketing/BEACON.md` | 1 | projection_generation_unproven |
| `static/assets/agents/butcher/agent.md` | `RECONCILE_GENERATED_PROJECTION` | `docs/09-vault-brain/02-agents/AGENT_REGISTRY.md` | 1 | projection_generation_unproven |
| `static/assets/agents/gatekeeper/agent.md` | `RECONCILE_GENERATED_PROJECTION` | `docs/09-vault-brain/02-agents/AGENT_REGISTRY.md` | 1 | projection_generation_unproven |
| `static/assets/agents/herdmaster/agent.md` | `RECONCILE_GENERATED_PROJECTION` | `docs/09-vault-brain/02-agents/farm/HERDMASTER.md` | 1 | projection_generation_unproven |
| `static/assets/agents/ledger/agent.md` | `RECONCILE_GENERATED_PROJECTION` | `docs/09-vault-brain/02-agents/AGENT_REGISTRY.md` | 1 | projection_generation_unproven |
| `static/assets/agents/oom-sakkie/agent.md` | `RECONCILE_GENERATED_PROJECTION` | `docs/09-vault-brain/02-agents/farm/OOM_SAKKIE.md` | 1 | projection_generation_unproven |
| `static/assets/agents/quartermaster/agent.md` | `RECONCILE_GENERATED_PROJECTION` | `docs/09-vault-brain/02-agents/AGENT_REGISTRY.md` | 1 | projection_generation_unproven |
| `static/assets/agents/rootline/agent.md` | `RECONCILE_GENERATED_PROJECTION` | `docs/09-vault-brain/02-agents/farm/ROOTLINE.md` | 1 | projection_generation_unproven |
| `static/assets/agents/sam/agent.md` | `RECONCILE_GENERATED_PROJECTION` | `docs/09-vault-brain/02-agents/sales/SAM.md` | 1 | projection_generation_unproven |

## Validation findings

- None.
