import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BATCH5_TOP_LEVEL_AI_FILES = {
    "AGENT_PORTFOLIO_REVIEW.md",
    "AGENT_ROLES.md",
    "PROMPT_RULES.md",
    "README.md",
    "RESPONSE_RULES.md",
}
BATCH6_AGENT_AI_FILES = {
    "agents/beacon/BEACON_SCOPE.md",
    "agents/beacon/MEDIA_STORAGE_DECISION.md",
    "agents/beacon/README.md",
    "agents/sam/SAM_V3_LLM_FIRST_SHARED_CONTEXT_PLAN.md",
}
BATCH7_EXTERNAL_UI_FILES = {
    "CODEX_FARM_UI_RESET_BRIEF.md",
    "CODEX_FARM_UI_TARGET_SPECIALIST_WORKSPACE_BRIEF.md",
}
BATCH8_CURRENT_EXTERNAL_REFERENCES = {
    "external_sources/AMADEUS_HALF_CARCASS_CUTTING_STANDARD_v1.0.md",
    "external_sources/README.md",
    "external_sources/telemetry/forecast/amadeus-forecast-logger/README.md",
    "external_sources/telemetry/sunsynk/amadeus-sunsynk-logger/README.md",
}
BATCH9_COMPATIBILITY_POINTERS = {
    "docs/00-start-here/CLAUDE_REVIEW_HANDOFF.md",
    "docs/00-start-here/GLOSSARY.md",
    "docs/00-start-here/HOW_WE_WORK.md",
    "docs/00-start-here/PROJECT_OVERVIEW.md",
    "docs/00-start-here/README.md",
    "docs/00-start-here/WORKFLOW.md",
    "docs/07-decisions/README.md",
}
BATCH10_COMPATIBILITY_POINTERS = {
    "CLAUDE.md",
    "docs/00-start-here/AGENT_ASSET_REGISTER.md",
    "docs/00-start-here/AGENT_PORTFOLIO_STATUS.md",
    "docs/00-start-here/OPERATING_STATUS.md",
    "docs/00-start-here/OWNER_INBOX_GUIDE.md",
}
BATCH11_COMPATIBILITY_POINTERS = {
    "docs/00-start-here/CHARLIE_CORE_AGENT_RUNNER_V2.md",
    "docs/00-start-here/CHARLIE_MISSION_PROTOCOL.md",
    "docs/00-start-here/DEPLOYMENT_SOP.md",
}
BATCH12_COMPATIBILITY_POINTERS = {
    "docs/00-start-here/CURRENT_STATE.md",
    "docs/00-start-here/NEXT_STEPS.md",
}
BATCH13_COMPATIBILITY_POINTERS = {
    "docs/00-start-here/PRODUCT_VISION.md",
}
BATCH16_ARCHIVED_FILES = {
    "docs/07-decisions/ADR_0001_DOCUMENTATION_SOURCE_OF_TRUTH.md",
    "docs/07-decisions/ADR_0002_CHARLIE_CORE_TERMINOLOGY_AND_CONFIGURATION.md",
    "docs/MIGRATION_INDEX.md",
}
BATCH17_ARCHIVED_FILES = {
    "docs/06-operations/GOOGLE_SHEETS_TO_SUPABASE_MIGRATION_PLAN.md",
    "docs/06-operations/GS_MIG_1_DRY_RUN_REPORT.md",
    "docs/06-operations/GS_MIG_2_RECONCILIATION_REPORT.md",
    "docs/06-operations/GS_MIG_3A_DATA_ISSUE_REVIEW.md",
    "docs/06-operations/GS_MIG_3B_IMPORT_POLICY_DECISIONS.md",
    "docs/06-operations/GS_MIG_3_BACKFILL_VERIFIER_REPORT.md",
    "docs/06-operations/GS_MIG_5_IMPORT_EXECUTION_REPORT.md",
    "docs/06-operations/GS_MIG_5_INITIAL_IMPORT_PLAN.md",
    "docs/06-operations/GS_MIG_6_CONFLICTING_WEIGHT_REVIEW.md",
    "docs/06-operations/GS_MIG_7B_FORMULA_SHADOW_REPORT.md",
    "docs/06-operations/GS_MIG_7_ROUTE_CUTOVER_REPORT.md",
    "docs/06-operations/GS_MIG_FINAL_AUDIT.md",
}
BATCH18_ARCHIVED_FILES = {
    "docs/06-operations/CMQ_20260813_03_APPLICATION_PREVIEW_WIRING_HANDOVER.md",
    "docs/06-operations/CMQ_20260813_03_CANONICAL_CLAIM_EXECUTOR_COMPATIBILITY.md",
    "docs/06-operations/CMQ_20260813_03_CANONICAL_PREVIEW_SOURCE_HANDOVER.md",
    "docs/06-operations/CMQ_20260813_03_GROUPED_WEIGHT_MOVEMENT_RECONCILIATION.md",
    "docs/06-operations/CMQ_20260813_03_OOM_TYPED_PREVIEW_WIRING_HANDOVER.md",
    "docs/06-operations/CMQ_20260813_05_ATOMIC_BOOTSTRAP_ADMISSION.md",
    "docs/06-operations/CMQ_20260813_05_CURRENT_PORTFOLIO_BASELINE_PLAN.md",
    "docs/06-operations/CMQ_20260813_05_PHASE_A_PRIVATE_INPUT.md",
    "docs/06-operations/CMQ_20260813_05_PHASE_A_SHADOW_CONTROL_TOWER.md",
    "docs/06-operations/CMQ_20260813_05_PORTFOLIO_CLASSIFICATION.md",
}
BATCH19_ARCHIVED_FILES = {
    "docs/06-operations/AGENTIC_BUSINESS_OS_IMPLEMENTATION_ROADMAP.md",
    "docs/06-operations/AGENTIC_BUSINESS_OS_PHASE_2_7_EVIDENCE.md",
    "docs/06-operations/AGENTIC_FARM_RUNTIME_PHASE0_DEPENDENCY_RETIREMENT_REGISTER.md",
    "docs/06-operations/AGENTIC_FARM_RUNTIME_PROGRAMME.md",
    "docs/06-operations/AGENTIC_OPERATING_SYSTEM_PROGRAM.md",
    "docs/06-operations/BUILD_RELAY.md",
    "docs/06-operations/CHARLIE_AGENT_WORKFORCE.md",
    "docs/06-operations/CHARLIE_BUILD_RELAY_PLAN.md",
    "docs/06-operations/CHARLIE_CORE_KERNEL_RELIABILITY.md",
    "docs/06-operations/CHARLIE_CORE_RUNTIME_RECOVERY.md",
    "docs/06-operations/CHARLIE_EXECUTIVE_CONTROL_PLANE.md",
    "docs/06-operations/CHARLIE_EXECUTIVE_LIVENESS_CONTRACT.md",
    "docs/06-operations/CHARLIE_LIVE_EXECUTIVE_V1.md",
    "docs/06-operations/CHARLIE_PRIVATE_EXECUTIVE_INTERFACE.md",
    "docs/06-operations/CHARLIE_PRIVATE_EXECUTIVE_MASTER_PLAN.md",
    "docs/06-operations/CHARLIE_SHARED_AGENT_RUNTIME.md",
    "docs/06-operations/CORE_PROVIDER_ORIGIN_ACTIVATION_RAIL.md",
    "docs/06-operations/MISSION_LOOP_CONTRACT.md",
}
BATCH20_ARCHIVED_FILES = {
    "docs/06-operations/CODEX_CHAT_WORKFLOW.md",
    "docs/06-operations/CONTINUOUS_AGENT_ALIGNMENT_AUDIT_20260817.md",
    "docs/06-operations/FARM_OPERATING_DASHBOARD_V2_PLAN.md",
    "docs/06-operations/OP004_LIVE_TRANSFER_DISCLOSURE_CONTRACT_20260816.md",
    "docs/06-operations/OPERATIONAL_FIXES_EVIDENCE_LOG.md",
    "docs/06-operations/OPERATIONAL_FIXES_MASTER_PLAN.md",
    "docs/06-operations/PARINGS_EN_WERPSEL_LIFECYCLE_REDESIGN_PLAN.md",
    "docs/06-operations/PHASE_0_CONFIGURATION_GOVERNANCE_BASELINE.md",
    "docs/06-operations/PHASE_1_SAFE_NAMESPACE_MIGRATION.md",
    "docs/06-operations/PIG_PROFILE_LIFE_RECORD_UI_PLAN_20260811.md",
    "docs/06-operations/README.md",
    "docs/06-operations/RELEASE_CHECKLIST.md",
    "docs/06-operations/RUNBOOK.md",
    "docs/06-operations/TESTING_CHECKLIST.md",
    "docs/06-operations/TROUBLESHOOTING.md",
    "docs/06-operations/goals/README.md",
}
BATCH21_ARCHIVED_FILES = {
    "docs/06-operations/HERDMASTER_AUCTION_SALE_SOURCE_HANDOVER_20260808.md",
    "docs/06-operations/HERDMASTER_BREEDING_ATTENTION_UI_RECOVERY_PLAN_20260811.md",
    "docs/06-operations/HERDMASTER_BREEDING_EVIDENCE_QUALIFIED_HANDOVER.md",
    "docs/06-operations/HERDMASTER_BREEDING_EXPOSURE_RECOVERY_AND_UNKNOWN_PARENT_PLAN_20260812.md",
    "docs/06-operations/HERDMASTER_BREEDING_EXPOSURE_RECOVERY_SOURCE_HANDOVER_20260812.md",
    "docs/06-operations/HERDMASTER_EXPOSURE_CYCLE_TRANSITION_HANDOVER_20260812.md",
    "docs/06-operations/HERDMASTER_FULL_LIFECYCLE_GENETIC_MERIT_DATA_UX_CONTRACT_20260813.md",
    "docs/06-operations/HERDMASTER_LITTER_SUPERSESSION_SOURCE_HANDOVER.md",
    "docs/06-operations/HERDMASTER_LITTER_WEANING_RECOVERY_LIT-2026-322B.md",
    "docs/06-operations/HERDMASTER_MORTALITY_FIRST_REAL_ASSESSMENT_20260803.md",
    "docs/06-operations/HERDMASTER_MORTALITY_INTELLIGENCE_HANDOVER.md",
    "docs/06-operations/HERDMASTER_NATURAL_HEALTH_LOSS_SOURCE_HANDOVER.md",
    "docs/06-operations/HERDMASTER_OP004_SALES_MULTILINE_INTEGRATION_HANDOFF_20260817.md",
    "docs/06-operations/HERDMASTER_PIGLET_WEANING_OBSERVATION_PLAN_20260812.md",
    "docs/06-operations/HERDMASTER_PRACTICAL_MATING_SELECTION_PLAN.md",
    "docs/06-operations/HERDMASTER_PROACTIVE_MANAGEMENT_ROUND_HANDOVER.md",
    "docs/06-operations/HERDMASTER_SAM_REVIEW_HISTORY_ALLOWLIST_HANDOVER.md",
    "docs/06-operations/HERDMASTER_UNIFIED_BREEDING_CAPTURE_PLAN_20260812.md",
    "docs/06-operations/HERDMASTER_WEANING_LED_MATING_RECOVERY_PLAN_20260811.md",
    "docs/06-operations/HERDMASTER_WEIGHING_BATCH_INTELLIGENCE_SOURCE_HANDOVER_20260811.md",
    "docs/06-operations/HERDMASTER_WHOLE_HERD_NEXT_ROUND_HANDOVER.md",
    "docs/06-operations/HERDMASTER_ZIGAY_REVISED_SUPERSESSION_PREVIEW.md",
}
BATCH22_ARCHIVED_FILES = {
    "docs/06-operations/OOM_SAKKIE_ACTIONABLE_DAILY_MANAGER_MISSION_20260812.md",
    "docs/06-operations/OOM_SAKKIE_AUTOMATIC_REASSESSMENT_HANDOVER.md",
    "docs/06-operations/OOM_SAKKIE_BREEDING_ROUTING_TASK_RETIREMENT_HANDOVER_20260811.md",
    "docs/06-operations/OOM_SAKKIE_BROWSER_BEHAVIOR_CHECKLIST.md",
    "docs/06-operations/OOM_SAKKIE_CONTEXTUAL_SPECIALIST_FOLLOWUP_HANDOVER.md",
    "docs/06-operations/OOM_SAKKIE_DAILY_FARM_MANAGER_LOOP_HANDOVER.md",
    "docs/06-operations/OOM_SAKKIE_DURABLE_MORNING_RUNTIME_HANDOVER_20260813.md",
    "docs/06-operations/OOM_SAKKIE_FAMILY_ACCESS_SOURCE_HANDOVER.md",
    "docs/06-operations/OOM_SAKKIE_FARM_MANAGER_ROUND_HANDOVER.md",
    "docs/06-operations/OOM_SAKKIE_FARM_MANAGER_SOURCE_HANDOVER.md",
    "docs/06-operations/OOM_SAKKIE_FARM_MANAGER_SPINE_SCORECARD_20260809.md",
    "docs/06-operations/OOM_SAKKIE_GENERIC_FAMILY_MESSAGE_LIFECYCLE_HANDOVER.md",
    "docs/06-operations/OOM_SAKKIE_HERDMASTER_MANAGEMENT_CONSUMER_HANDOVER.md",
    "docs/06-operations/OOM_SAKKIE_HERDMASTER_MORTALITY_CONSUMPTION_HANDOVER.md",
    "docs/06-operations/OOM_SAKKIE_LLM_SEMANTIC_FRONT_DOOR_HANDOVER.md",
    "docs/06-operations/OOM_SAKKIE_MANAGER_QUALITY_COMPOSER_HANDOVER.md",
    "docs/06-operations/OOM_SAKKIE_OWNER_ATTENTION_QUEUE_SOURCE_HANDOVER.md",
    "docs/06-operations/OOM_SAKKIE_OWNER_OPERATIONAL_CONTINUATION_HANDOVER.md",
    "docs/06-operations/OOM_SAKKIE_OWNER_REQUEST_AGENT_LIFECYCLE_HANDOVER.md",
    "docs/06-operations/OOM_SAKKIE_P0_NATURAL_PREVIEW_CORRECTION_HANDOVER.md",
    "docs/06-operations/OOM_SAKKIE_P0_OPERATIONAL_INTAKE_RECOVERY_HANDOVER.md",
    "docs/06-operations/OOM_SAKKIE_P0_PIG125_LIFECYCLE_REENTRY_HANDOVER.md",
    "docs/06-operations/OOM_SAKKIE_PROTECTED_ACTION_RECOVERY_HANDOVER_20260811.md",
    "docs/06-operations/OOM_SAKKIE_RELAY_PROVIDER_CHRONOLOGY_HANDOVER.md",
    "docs/06-operations/OOM_SAKKIE_ROOTLINE_DAILY_PRESENTATION_HANDOVER.md",
    "docs/06-operations/OOM_SAKKIE_ROOTLINE_OPERATIONAL_INTAKE_HANDOVER.md",
    "docs/06-operations/OOM_SAKKIE_SENTINEL_SINGLE_SHOT_RUNBOOK.md",
    "docs/06-operations/OOM_SAKKIE_SPECIALIST_DISPATCH_ACK_HANDOVER.md",
    "docs/06-operations/OOM_SAKKIE_SPECIALIST_OWNER_DECISION_BINDING_HANDOVER.md",
    "docs/06-operations/OOM_SAKKIE_WITHDRAWAL_RELAY_RECOVERY_HANDOVER.md",
}
BATCH23_ARCHIVED_FILES = {
    "docs/06-operations/ROOTLINE_ADAPTIVE_IRRIGATION_MANAGEMENT.md",
    "docs/06-operations/ROOTLINE_AGENTIC_DEVICE_MANAGEMENT_PLAN.md",
    "docs/06-operations/ROOTLINE_AUGUST1_ESSENTIAL_WATER_PLAN.md",
    "docs/06-operations/ROOTLINE_C12345_CANARY_PREFLIGHT.md",
    "docs/06-operations/ROOTLINE_CANONICAL_STATUS_AND_OWNER_ACCESS_RECOVERY_20260811.md",
    "docs/06-operations/ROOTLINE_EWELINK_OAUTH_ONBOARDING.md",
    "docs/06-operations/ROOTLINE_OPERATING_KNOWLEDGE_REGISTER.md",
    "docs/06-operations/ROOTLINE_OPERATING_POLICY_REVIEW.md",
    "docs/06-operations/ROOTLINE_PHASE_B_HARDWARE_INVENTORY.md",
    "docs/06-operations/ROOTLINE_REMAINING_COMMISSIONING_PACKETS_20260818.md",
    "docs/06-operations/ROOTLINE_SONOFF_IRRIGATION_EXECUTION_CONTRACT.md",
    "docs/06-operations/ROOTLINE_SPECIALIST_RESULT_CONTRACT.md",
    "docs/06-operations/ROOTLINE_WATER_ENERGY_MANAGER_PHASE1.md",
}
BATCH24_ARCHIVED_FILES = {
    "docs/06-operations/SAM_BEACON_MEAT_FIRST_LAUNCH_READINESS_2026-07-03.md",
    "docs/06-operations/SAM_INBOX_RECONCILIATION_TIMEOUT_HANDOVER.md",
    "docs/06-operations/SAM_LIVE_STOCK_COMPLETION_PROGRAM.md",
    "docs/06-operations/SAM_MANAGER_SUMMARY_PR691_HANDOVER.md",
    "docs/06-operations/SAM_MEAT_INTAKE_LIVE_SMOKE_CHECKLIST.md",
}
BATCH25_ARCHIVED_FILES = {
    "docs/08-business-modules/FARM_CALENDAR_PLAN.md",
    "docs/08-business-modules/MEAT_LAUNCH_CAMPAIGN_PACKET.md",
    "docs/08-business-modules/MEAT_PRODUCTION_BATCH_WORKFLOW.md",
    "docs/08-business-modules/MEAT_SALES_LAUNCH_PLAN.md",
    "docs/08-business-modules/MEAT_SALES_STRESS_TEST_REPORT.md",
    "docs/08-business-modules/MEAT_SALES_WHATSAPP_TEMPLATES.md",
    "docs/08-business-modules/PORK_BUSINESS_INTEGRATION_READINESS_MAP.md",
    "docs/08-business-modules/PORK_SALES_MODEL.md",
    "docs/08-business-modules/README.md",
    "docs/08-business-modules/SAM_FARM_KNOWLEDGE_PACK.md",
}
BATCH26_ARCHIVED_FILES = {
    "planning/CHARLIE_CORE_EXTENDED_PLAN.md",
    "planning/CODEX_CHAT.md",
    "planning/SAM_LIVE_STOCK_SALES_BUILD_PLAN.md",
    "planning/ToDoList.md",
    "planning/inbox/README.md",
    "planning/inbox/processed/2026-06/ToDoList_2026-06-28_operational_notes.md",
    "planning/inbox/processed/2026-06/ToDoList_2026-06-30_live_app_review_notes.md",
    "planning/inbox/prompts/REPO_CLEANUP_AND_DOCS_GOVERNANCE_PROMPT.md",
}
BATCH27_ARCHIVE_ROOT = ROOT / "docs/99-archive/vault-cutover/planning/storyworks"
SPEC = importlib.util.spec_from_file_location(
    "build_vault_cutover_manifest",
    ROOT / "scripts" / "build_vault_cutover_manifest.py",
)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class VaultPhysicalCutoverManifestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = MODULE.build_manifest()
        cls.entries = {entry["path"]: entry for entry in cls.manifest["entries"]}

    def test_manifest_covers_every_tracked_document_once(self):
        self.assertEqual(MODULE.validate_manifest(self.manifest), [])

    def test_no_physical_change_is_authorized(self):
        self.assertTrue(self.entries)
        self.assertTrue(all(entry["physical_change_authorized"] is False for entry in self.entries.values()))

    def test_controlling_exceptions_are_retained(self):
        for path in MODULE.CONTROLLING_EXCEPTIONS:
            self.assertEqual(self.entries[path]["disposition"], "KEEP_CONTROLLING_EXCEPTION")

    def test_vault_files_are_retained(self):
        vault_entries = [entry for path, entry in self.entries.items() if path.startswith("docs/09-vault-brain/")]
        self.assertTrue(vault_entries)
        self.assertTrue(all(entry["disposition"] == "KEEP_VAULT" for entry in vault_entries))

    def test_transitional_files_remain_exit_test_blocked(self):
        transitional = [entry for entry in self.entries.values() if entry["disposition"] == "KEEP_TRANSITIONAL"]
        self.assertEqual(len(transitional), 72)
        self.assertTrue(all("exit_test_unproven" in entry["blockers"] for entry in transitional))
        counts = {}
        for entry in transitional:
            counts[entry["exit_test_id"]] = counts.get(entry["exit_test_id"], 0) + 1
            self.assertEqual(entry["exit_test_status"], "BLOCKED_CURRENT_RUNTIME_DEPENDENCY")
        self.assertEqual(counts, {
            "GS-LEGACY-RETIREMENT-V1": 32,
            "N8N-LEGACY-RETIREMENT-V1": 40,
        })
        self.assertTrue((ROOT / "docs/09-vault-brain/10-source-map/TRANSITIONAL_EXIT_TEST_REGISTER.md").is_file())

    def test_delete_candidates_are_tiny_unreferenced_and_owner_gated(self):
        for entry in self.entries.values():
            if entry["disposition"] != "DELETE_CANDIDATE":
                continue
            self.assertEqual(entry["exact_reference_count"], 0)
            self.assertLessEqual(entry["physical_lines"], 30)
            self.assertIn("owner_approval_required", entry["blockers"])
            self.assertTrue(entry["destination_or_replacement"])

    def test_static_agent_cards_require_projection_reconciliation(self):
        cards = [entry for path, entry in self.entries.items() if path.startswith("static/assets/agents/")]
        self.assertTrue(cards)
        self.assertTrue(all(entry["disposition"] == "KEEP_GENERATED_PROJECTION" for entry in cards))

    def test_batch5_slice_is_archived_without_deletion(self):
        for name in BATCH5_TOP_LEVEL_AI_FILES:
            self.assertNotIn(f"docs/05-ai/{name}", self.entries)
            archived = f"docs/99-archive/vault-cutover/docs/05-ai/{name}"
            self.assertIn(archived, self.entries)
            self.assertEqual(self.entries[archived]["disposition"], "KEEP_ARCHIVE")

    def test_batch5_reconciliation_is_canonical_and_active_map_exposes_no_archive(self):
        reconciliation = ROOT / "docs/09-vault-brain/10-source-map/VAULT_CUTOVER_BATCH5_RECONCILIATION.md"
        self.assertTrue(reconciliation.is_file())
        active_map = (ROOT / "docs/09-vault-brain/10-source-map/ACTIVE_DOCS_SOURCE_MAP.md").read_text(
            encoding="utf-8"
        )
        active_section = active_map.split("## Archived After Migration", 1)[0]
        self.assertNotIn("docs/99-archive/vault-cutover/docs/05-ai/", active_section)

    def test_batch6_removes_remaining_ai_docs_from_active_tree(self):
        for relative in BATCH6_AGENT_AI_FILES:
            self.assertNotIn(f"docs/05-ai/{relative}", self.entries)
            archived = f"docs/99-archive/vault-cutover/docs/05-ai/{relative}"
            self.assertIn(archived, self.entries)
            self.assertEqual(self.entries[archived]["disposition"], "KEEP_ARCHIVE")
        self.assertFalse(any(path.startswith("docs/05-ai/") for path in self.entries))

    def test_batch7_archives_only_the_two_superseded_external_ui_briefs(self):
        for name in BATCH7_EXTERNAL_UI_FILES:
            self.assertNotIn(f"external_sources/{name}", self.entries)
            archived = f"docs/99-archive/vault-cutover/external_sources/{name}"
            self.assertIn(archived, self.entries)
            self.assertEqual(self.entries[archived]["disposition"], "KEEP_ARCHIVE")
        self.assertIn("external_sources/README.md", self.entries)
        self.assertIn(
            "external_sources/telemetry/forecast/amadeus-forecast-logger/README.md",
            self.entries,
        )

    def test_batch8_resolves_remaining_external_candidates_as_technical(self):
        for path in BATCH8_CURRENT_EXTERNAL_REFERENCES:
            self.assertEqual(self.entries[path]["disposition"], "KEEP_TECHNICAL")
        self.assertFalse(
            any(entry["disposition"] == "ARCHIVE_CANDIDATE" for entry in self.entries.values())
        )

    def test_batch9_replaces_legacy_navigation_with_minimal_pointers(self):
        for path in BATCH9_COMPATIBILITY_POINTERS:
            entry = self.entries[path]
            self.assertEqual(entry["disposition"], "KEEP_POINTER")
            self.assertLessEqual(entry["physical_lines"], 15)
            text = (ROOT / path).read_text(encoding="utf-8")
            self.assertIn("POINTER_ONLY / NON_DOCTRINE", text)
            self.assertIn("09-vault-brain", text)

    def test_batch10_replaces_root_status_navigation_with_minimal_pointers(self):
        for path in BATCH10_COMPATIBILITY_POINTERS:
            entry = self.entries[path]
            self.assertEqual(entry["disposition"], "KEEP_POINTER")
            self.assertLessEqual(entry["physical_lines"], 15)
            text = (ROOT / path).read_text(encoding="utf-8")
            self.assertIn("POINTER_ONLY / NON_DOCTRINE", text)
        self.assertIn("python app.py", (ROOT / "CLAUDE.md").read_text(encoding="utf-8"))
        self.assertIn(
            "static/assets/agents/",
            (ROOT / "docs/00-start-here/AGENT_ASSET_REGISTER.md").read_text(encoding="utf-8"),
        )

    def test_batch11_reconciles_technical_contracts_before_pointer_cutover(self):
        for path in BATCH11_COMPATIBILITY_POINTERS:
            entry = self.entries[path]
            self.assertEqual(entry["disposition"], "KEEP_POINTER")
            self.assertLessEqual(entry["physical_lines"], 15)
            self.assertIn("POINTER_ONLY / NON_DOCTRINE", (ROOT / path).read_text(encoding="utf-8"))
        workflow = (ROOT / "docs/09-vault-brain/04-workflows/CHARLIE_MISSION_WORKFLOW.md").read_text(encoding="utf-8")
        deployment = (ROOT / "docs/09-vault-brain/07-standards/DEPLOYMENT_STANDARD.md").read_text(encoding="utf-8")
        self.assertIn("Runner And Orchestration Contract", workflow)
        self.assertIn("charlie_runner_control.py", workflow)
        self.assertIn("Never use `git add .`", deployment)

    def test_batch12_replaces_stale_state_and_roadmap_with_pointers(self):
        for path in BATCH12_COMPATIBILITY_POINTERS:
            entry = self.entries[path]
            self.assertEqual(entry["disposition"], "KEEP_POINTER")
            self.assertLessEqual(entry["physical_lines"], 15)
            text = (ROOT / path).read_text(encoding="utf-8")
            self.assertIn("POINTER_ONLY / NON_DOCTRINE", text)
            self.assertIn("CONTROL_TOWER_MISSION_REGISTER.md", text)
        fallback = (ROOT / "docs/00-start-here/NEXT_STEPS.md").read_text(encoding="utf-8")
        self.assertIn("P0 compatibility fallback", fallback)

    def test_batch13_reconciles_final_start_here_projection(self):
        for path in BATCH13_COMPATIBILITY_POINTERS:
            entry = self.entries[path]
            self.assertEqual(entry["disposition"], "KEEP_POINTER")
            self.assertLessEqual(entry["physical_lines"], 15)
            self.assertIn("POINTER_ONLY / NON_DOCTRINE", (ROOT / path).read_text(encoding="utf-8"))
        dashboard = (ROOT / "docs/09-vault-brain/07-standards/UI_DASHBOARD_STANDARD.md").read_text(encoding="utf-8")
        self.assertIn("normal daily workflow fits one calm", dashboard)
        self.assertIn("Voice, typed commands", dashboard)

    def test_batch16_archives_decision_wrappers_after_fact_reconciliation(self):
        for source in BATCH16_ARCHIVED_FILES:
            self.assertNotIn(source, self.entries)
            archived = f"docs/99-archive/vault-cutover/{source}"
            self.assertEqual(self.entries[archived]["disposition"], "KEEP_ARCHIVE")
        source_truth = (ROOT / "docs/09-vault-brain/00-governance/SOURCE_OF_TRUTH_RULES.md").read_text(encoding="utf-8")
        core = (ROOT / "docs/09-vault-brain/01-identity/CHARLIE_CORE.md").read_text(encoding="utf-8")
        deployment = (ROOT / "docs/09-vault-brain/07-standards/DEPLOYMENT_STANDARD.md").read_text(encoding="utf-8")
        self.assertIn("their location alone never makes them", source_truth)
        self.assertIn("`CORE_*`", core)
        self.assertIn("normalized values must agree or startup fails closed", deployment)

    def test_batch17_archives_sheets_migration_history_after_rule_reconciliation(self):
        for source in BATCH17_ARCHIVED_FILES:
            self.assertNotIn(source, self.entries)
            archived = f"docs/99-archive/vault-cutover/{source}"
            self.assertEqual(self.entries[archived]["disposition"], "KEEP_ARCHIVE")
        contracts = (ROOT / "docs/09-vault-brain/06-data/SUPABASE_CONTRACTS.md").read_text(encoding="utf-8")
        legacy = (ROOT / "docs/09-vault-brain/06-data/GOOGLE_SHEETS_LEGACY.md").read_text(encoding="utf-8")
        active = (ROOT / "docs/09-vault-brain/10-source-map/ACTIVE_DOCS_SOURCE_MAP.md").read_text(encoding="utf-8")
        self.assertIn("Conflicting same-animal/date weight values remain excluded", contracts)
        self.assertIn("Retire a fallback only after fresh route inventory", legacy)
        self.assertNotIn("docs/06-operations/GS_MIG_FINAL_AUDIT.md", active)

    def test_batch18_archives_core_mission_evidence_after_rule_reconciliation(self):
        for source in BATCH18_ARCHIVED_FILES:
            self.assertNotIn(source, self.entries)
            archived = f"docs/99-archive/vault-cutover/{source}"
            self.assertEqual(self.entries[archived]["disposition"], "KEEP_ARCHIVE")
        workflow = (ROOT / "docs/09-vault-brain/04-workflows/CHARLIE_MISSION_WORKFLOW.md").read_text(encoding="utf-8")
        action = (ROOT / "docs/09-vault-brain/07-standards/CHANNEL_INVARIANT_CANONICAL_ACTION_STANDARD.md").read_text(encoding="utf-8")
        source_map = (ROOT / "docs/09-vault-brain/10-source-map/IMPLEMENTATION_SOURCE_MAP.md").read_text(encoding="utf-8")
        self.assertIn("Portfolio admission and execution eligibility", workflow)
        self.assertIn("Preview, claim and execution identity", action)
        for source in BATCH18_ARCHIVED_FILES:
            self.assertNotIn(f"`{source}`", source_map)

    def test_batch19_archives_core_operating_evidence_after_contract_reconciliation(self):
        for source in BATCH19_ARCHIVED_FILES:
            self.assertNotIn(source, self.entries)
            archived = f"docs/99-archive/vault-cutover/{source}"
            self.assertEqual(self.entries[archived]["disposition"], "KEEP_ARCHIVE")
        charlie = (ROOT / "docs/09-vault-brain/01-identity/CHARLIE.md").read_text(encoding="utf-8")
        core = (ROOT / "docs/09-vault-brain/01-identity/CHARLIE_CORE.md").read_text(encoding="utf-8")
        workflow = (ROOT / "docs/09-vault-brain/04-workflows/CHARLIE_MISSION_WORKFLOW.md").read_text(encoding="utf-8")
        deployment = (ROOT / "docs/09-vault-brain/07-standards/DEPLOYMENT_STANDARD.md").read_text(encoding="utf-8")
        self.assertIn("Private Executive Interface Contract", charlie)
        self.assertIn("Mission, command and execution planes", core)
        self.assertIn("Executive liveness and recovery", workflow)
        self.assertIn("Dependency retirement and scheduler singularity", deployment)

    def test_batch20_archives_general_operations_after_contract_reconciliation(self):
        for source in BATCH20_ARCHIVED_FILES:
            self.assertNotIn(source, self.entries)
            archived = f"docs/99-archive/vault-cutover/{source}"
            self.assertEqual(self.entries[archived]["disposition"], "KEEP_ARCHIVE")
        testing = (ROOT / "docs/09-vault-brain/07-standards/TESTING_STANDARD.md").read_text(encoding="utf-8")
        release = (ROOT / "docs/09-vault-brain/04-workflows/RELEASE_WORKFLOW.md").read_text(encoding="utf-8")
        live_fix = (ROOT / "docs/09-vault-brain/05-playbooks/LIVE_OPERATIONS_FIX.md").read_text(encoding="utf-8")
        livestock = (ROOT / "docs/09-vault-brain/08-business-rules/LIVE_STOCK_SALES_RULES.md").read_text(encoding="utf-8")
        self.assertIn("Partial completion must never be", testing)
        self.assertIn("Required Release Journey", release)
        self.assertIn("durable operation and row ledger", live_fix)
        self.assertIn("does not by itself prove or prohibit live transfer", livestock)

    def test_batch21_archives_herdmaster_history_after_contract_reconciliation(self):
        for source in BATCH21_ARCHIVED_FILES:
            self.assertNotIn(source, self.entries)
            archived = f"docs/99-archive/vault-cutover/{source}"
            self.assertEqual(self.entries[archived]["disposition"], "KEEP_ARCHIVE")
        herdmaster = (ROOT / "docs/09-vault-brain/02-agents/farm/HERDMASTER.md").read_text(encoding="utf-8")
        breeding = (ROOT / "docs/09-vault-brain/04-workflows/HERDMASTER_BREEDING_ATTENTION_WORKFLOW.md").read_text(encoding="utf-8")
        health = (ROOT / "docs/09-vault-brain/04-workflows/HERDMASTER_NATURAL_HEALTH_AND_LOSS_INTAKE_WORKFLOW.md").read_text(encoding="utf-8")
        self.assertIn("Lifecycle And Evidence Contract", herdmaster)
        self.assertIn("Unified Capture And Transition Contract", breeding)
        self.assertIn("Unknown-cause counts separately", health)

    def test_batch22_archives_oom_history_after_contract_reconciliation(self):
        for source in BATCH22_ARCHIVED_FILES:
            self.assertNotIn(source, self.entries)
            archived = f"docs/99-archive/vault-cutover/{source}"
            self.assertEqual(self.entries[archived]["disposition"], "KEEP_ARCHIVE")
        oom = (ROOT / "docs/09-vault-brain/02-agents/farm/OOM_SAKKIE.md").read_text(encoding="utf-8")
        attention = (ROOT / "docs/09-vault-brain/04-workflows/OOM_SAKKIE_OWNER_ATTENTION_QUEUE_WORKFLOW.md").read_text(encoding="utf-8")
        ui = (ROOT / "docs/09-vault-brain/07-standards/UI_DASHBOARD_STANDARD.md").read_text(encoding="utf-8")
        self.assertIn("Manager Dialogue And Scheduling Contract", oom)
        self.assertIn("Context, Specialist And Recovery Ordering", attention)
        self.assertIn("Oom Sakkie Browser Acceptance", ui)

    def test_batch23_archives_rootline_history_after_contract_reconciliation(self):
        for source in BATCH23_ARCHIVED_FILES:
            self.assertNotIn(source, self.entries)
            archived = f"docs/99-archive/vault-cutover/{source}"
            self.assertEqual(self.entries[archived]["disposition"], "KEEP_ARCHIVE")
        rootline = (ROOT / "docs/09-vault-brain/02-agents/farm/ROOTLINE.md").read_text(encoding="utf-8")
        architecture = (ROOT / "docs/09-vault-brain/04-workflows/ROOTLINE_CONTROL_ARCHITECTURE.md").read_text(encoding="utf-8")
        rules = (ROOT / "docs/09-vault-brain/08-business-rules/ROOTLINE_WATER_ENERGY_RULES.md").read_text(encoding="utf-8")
        self.assertIn("Planning, Execution And Device Contract", rootline)
        self.assertIn("Device-Class Graduation And Execution", architecture)
        self.assertIn("Authority And Evidence Precedence", rules)

    def test_batch24_archives_sam_revenue_history_after_contract_reconciliation(self):
        for source in BATCH24_ARCHIVED_FILES:
            self.assertNotIn(source, self.entries)
            archived = f"docs/99-archive/vault-cutover/{source}"
            self.assertEqual(self.entries[archived]["disposition"], "KEEP_ARCHIVE")
        sam = (ROOT / "docs/09-vault-brain/02-agents/sales/SAM.md").read_text(encoding="utf-8")
        livestock = (ROOT / "docs/09-vault-brain/04-workflows/SAM_LIVE_STOCK_SALES_WORKFLOW.md").read_text(encoding="utf-8")
        meat = (ROOT / "docs/09-vault-brain/04-workflows/SAM_MEAT_SALES_WORKFLOW.md").read_text(encoding="utf-8")
        self.assertIn("Inbox, Summary And Graduation Contract", sam)
        self.assertIn("Inventory and chronology reads are bounded", livestock)
        self.assertIn("Tracking-Only Intake And Acceptance", meat)

    def test_batch25_archives_business_modules_after_contract_reconciliation(self):
        for source in BATCH25_ARCHIVED_FILES:
            self.assertNotIn(source, self.entries)
            archived = f"docs/99-archive/vault-cutover/{source}"
            self.assertEqual(self.entries[archived]["disposition"], "KEEP_ARCHIVE")
        farm = (ROOT / "docs/09-vault-brain/08-business-rules/FARM_RULES.md").read_text(encoding="utf-8")
        production = (ROOT / "docs/09-vault-brain/08-business-rules/MEAT_PRODUCTION_RULES.md").read_text(encoding="utf-8")
        active = (ROOT / "docs/09-vault-brain/10-source-map/ACTIVE_DOCS_SOURCE_MAP.md").read_text(encoding="utf-8")
        self.assertIn("Farm Calendar Contract", farm)
        self.assertIn("Canonical Batch Flow And Metrics", production)
        self.assertNotIn("docs/08-business-modules/", active)

    def test_batch26_archives_planning_history_and_retains_minimal_scratchpads(self):
        for source in BATCH26_ARCHIVED_FILES:
            archived = f"docs/99-archive/vault-cutover/{source}"
            self.assertEqual(self.entries[archived]["disposition"], "KEEP_ARCHIVE")
        for source in BATCH26_ARCHIVED_FILES - MODULE.BATCH26_TECHNICAL_SCRATCHPADS:
            self.assertNotIn(source, self.entries)
        for source in MODULE.BATCH26_TECHNICAL_SCRATCHPADS:
            self.assertEqual(self.entries[source]["disposition"], "KEEP_TECHNICAL")
            text = (ROOT / source).read_text(encoding="utf-8")
            self.assertIn("NON-DOCTRINE", text)
            self.assertLessEqual(len(text.splitlines()), 30)
        workflow = (ROOT / "docs/09-vault-brain/04-workflows/CHARLIE_MISSION_WORKFLOW.md").read_text(encoding="utf-8")
        self.assertIn("never\nprove authority, active execution or completion", workflow)

    def test_batch14_schedule_tracks_every_remaining_physical_item_once(self):
        remaining = [entry for entry in self.entries.values()
                     if entry["disposition"] in MODULE.REMAINING_PHYSICAL_DISPOSITIONS]
        self.assertEqual(remaining, [])

    def test_batch14_schedule_has_exact_family_counts(self):
        self.assertFalse(any(entry["planned_batch"] is not None for entry in self.entries.values()))

    def test_batch27_archives_complete_storyworks_package(self):
        self.assertFalse((ROOT / "planning/storyworks").exists())
        self.assertTrue(BATCH27_ARCHIVE_ROOT.is_dir())
        archived_files = [path for path in BATCH27_ARCHIVE_ROOT.rglob("*") if path.is_file()]
        archived_markdown = [path for path in archived_files if path.suffix.lower() == ".md"]
        self.assertEqual(len(archived_files), 45)
        self.assertEqual(len(archived_markdown), 34)
        for path in archived_markdown:
            relative = path.relative_to(ROOT).as_posix()
            self.assertEqual(self.entries[relative]["disposition"], "KEEP_ARCHIVE")
        brain_guard = (ROOT / "docs/09-vault-brain/00-governance/BRAIN_GUARD.md").read_text(encoding="utf-8")
        self.assertIn("Batch 27 Storyworks Authority Gate", brain_guard)


if __name__ == "__main__":
    unittest.main()
