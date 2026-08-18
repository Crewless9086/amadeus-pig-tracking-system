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
        self.assertTrue(transitional)
        self.assertTrue(all("exit_test_unproven" in entry["blockers"] for entry in transitional))

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

    def test_batch14_schedule_tracks_every_remaining_physical_item_once(self):
        remaining = [entry for entry in self.entries.values()
                     if entry["disposition"] in MODULE.REMAINING_PHYSICAL_DISPOSITIONS]
        self.assertEqual(len(remaining), 166)
        self.assertTrue(all(18 <= entry["planned_batch"] <= 27 for entry in remaining))
        self.assertTrue(all(entry["reconciliation_family"] for entry in remaining))
        self.assertEqual({entry["planned_batch"] for entry in remaining}, set(range(18, 28)))

    def test_batch14_schedule_has_exact_family_counts(self):
        expected = {18: 10, 19: 18, 20: 16, 21: 22,
                    22: 30, 23: 13, 24: 5, 25: 10, 26: 8, 27: 34}
        actual = {batch: sum(entry["planned_batch"] == batch for entry in self.entries.values())
                  for batch in expected}
        self.assertEqual(actual, expected)


if __name__ == "__main__":
    unittest.main()
