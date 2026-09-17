# Vault Physical Cutover Manifest

Status: Batch 29 deployed Brain Guard acceptance complete; Vault cutover locked.

Version: `vault_physical_cutover_manifest_v26`
Baseline: `5d27e4afe2c546963196ed93753cf88aad92ba2b`
Generated from HEAD: `5d27e4afe2c546963196ed93753cf88aad92ba2b`
Tracked Markdown/MDX files covered: **558**
Validation: **PASS**

This manifest records completed Batches 5 through 29 and the bounded transitional
exceptions. It does not authorize another move, archive, deletion, pointer
rewrite, deployment, runtime action or production change. Every remaining entry
keeps `physical_change_authorized: false`.

## Disposition totals

| Disposition | Count |
| --- | ---: |
| `KEEP_ARCHIVE` | 207 |
| `KEEP_CONTROLLING_EXCEPTION` | 2 |
| `KEEP_CURRENT_STATE` | 2 |
| `KEEP_GENERATED_PROJECTION` | 9 |
| `KEEP_POINTER` | 18 |
| `KEEP_TECHNICAL` | 33 |
| `KEEP_TRANSITIONAL` | 72 |
| `KEEP_VAULT` | 198 |
| `OWNER_REVIEW_REQUIRED` | 17 |

## Remaining execution schedule

The physical-reconciliation queue and Batch 29 deployed acceptance are complete. All 72
transitional documents remain behind two named, owned, blocked runtime exit tests.
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
| 25 | `business_modules` | COMPLETE (10) |
| 26 | `planning_and_inbox` | COMPLETE (8) |
| 27 | `storyworks` | COMPLETE (34 Markdown / 45-package files) |
| 28 | `transitional_exit_tests` | COMPLETE: 72 retained behind 2 blocked named exits |
| 29 | `deployed_brain_guard_acceptance` | operational proof |

## Safety gates

- The 32 Google Sheets references remain behind `GS-LEGACY-RETIREMENT-V1`; current fallback/admin/runtime consumers prove retirement is unsafe.
- The 40 n8n references remain behind `N8N-LEGACY-RETIREMENT-V1`; current provider/workflow/customer integration consumers prove retirement is unsafe.
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
- The complete 45-file Storyworks/Chronicle Vault private validation package is archived intact; it is not BEACON, farm media, an active agent, a current mission or publication authority.
- No later physical change is authorized by this regenerated manifest.

## Exact non-keep review queue

The machine-readable JSON contains every tracked source document (the generated
Markdown report excludes itself). This table lists every
entry whose physical disposition needs later work or owner review.

| Source | Disposition | Planned batch | Destination / replacement | Exact refs | Blockers |
| --- | --- | ---: | --- | ---: | --- |
| `.agents/skills/amadeus-implement/SKILL.md` | `OWNER_REVIEW_REQUIRED` | - | `docs/09-vault-brain/README.md` | 0 | owner_classification_required |
| `.agents/skills/amadeus-operational-acceptance/SKILL.md` | `OWNER_REVIEW_REQUIRED` | - | `docs/09-vault-brain/README.md` | 0 | owner_classification_required |
| `.agents/skills/control-tower-operate/SKILL.md` | `OWNER_REVIEW_REQUIRED` | - | `docs/09-vault-brain/README.md` | 0 | owner_classification_required |
| `VISIBLE_OOM_LITTER_PR1161_8FAC_REPAIR_HANDOVER_20260822.md` | `OWNER_REVIEW_REQUIRED` | - | `docs/09-vault-brain/README.md` | 0 | owner_classification_required |
| `VISIBLE_OOM_LITTER_PR1161_IMPLEMENTER_HANDOVER_20260822.md` | `OWNER_REVIEW_REQUIRED` | - | `docs/09-vault-brain/README.md` | 0 | owner_classification_required |
| `VISIBLE_OOM_LITTER_PR1161_REVIEW_BLOCKER_REPAIR_HANDOVER_20260822.md` | `OWNER_REVIEW_REQUIRED` | - | `docs/09-vault-brain/README.md` | 0 | owner_classification_required |
| `VISIBLE_SAM_PR1163_CANONICAL_ATTRIBUTION_REPAIR_HANDOVER_20260822.md` | `OWNER_REVIEW_REQUIRED` | - | `docs/09-vault-brain/README.md` | 0 | owner_classification_required |
| `VISIBLE_SAM_PR1163_PRODUCTION_SHAPE_REPAIR_HANDOVER_20260822.md` | `OWNER_REVIEW_REQUIRED` | - | `docs/09-vault-brain/README.md` | 0 | owner_classification_required |
| `docs/06-operations/GREEN_PRINT_031_NON_ACTUATING_COMMISSIONING_PREFLIGHT_20260822.md` | `OWNER_REVIEW_REQUIRED` | - | `docs/09-vault-brain/10-source-map/IMPLEMENTATION_SOURCE_MAP.md` | 0 | owner_classification_required |
| `docs/06-operations/GREEN_PRINT_031_REGISTER_ADDENDUM_20260822.md` | `OWNER_REVIEW_REQUIRED` | - | `docs/09-vault-brain/10-source-map/IMPLEMENTATION_SOURCE_MAP.md` | 0 | owner_classification_required |
| `docs/06-operations/GREEN_PRINT_BRIDGE_PHYSICAL_COMMISSIONING_GUIDE.md` | `OWNER_REVIEW_REQUIRED` | - | `docs/09-vault-brain/10-source-map/IMPLEMENTATION_SOURCE_MAP.md` | 1 | owner_classification_required |
| `docs/06-operations/ROOTLINE_BOREHOLE_1_COMMISSIONING_GUIDE_20260820.md` | `OWNER_REVIEW_REQUIRED` | - | `docs/09-vault-brain/10-source-map/IMPLEMENTATION_SOURCE_MAP.md` | 0 | owner_classification_required |
| `docs/06-operations/ROOTLINE_BOREHOLE_READINESS_HANDOVER_20260820.md` | `OWNER_REVIEW_REQUIRED` | - | `docs/09-vault-brain/10-source-map/IMPLEMENTATION_SOURCE_MAP.md` | 0 | owner_classification_required |
| `docs/06-operations/ROOTLINE_FERTILIZER_MIXER_DEPLOYMENT_PROOF_HANDOVER_20260820.md` | `OWNER_REVIEW_REQUIRED` | - | `docs/09-vault-brain/10-source-map/IMPLEMENTATION_SOURCE_MAP.md` | 0 | owner_classification_required |
| `green_print_bridge/CHANGELOG.md` | `OWNER_REVIEW_REQUIRED` | - | `docs/09-vault-brain/README.md` | 0 | owner_classification_required |
| `green_print_bridge/DOCS.md` | `OWNER_REVIEW_REQUIRED` | - | `docs/09-vault-brain/README.md` | 1 | owner_classification_required |
| `green_print_bridge/README.md` | `OWNER_REVIEW_REQUIRED` | - | `docs/09-vault-brain/README.md` | 0 | owner_classification_required |

## Validation findings

- None.
