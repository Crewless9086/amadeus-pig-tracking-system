import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
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


if __name__ == "__main__":
    unittest.main()
