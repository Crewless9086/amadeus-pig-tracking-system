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
        self.assertTrue(all(entry["disposition"] == "RECONCILE_GENERATED_PROJECTION" for entry in cards))

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


if __name__ == "__main__":
    unittest.main()
