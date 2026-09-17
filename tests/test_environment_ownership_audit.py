import json
import tempfile
import unittest
from pathlib import Path

from scripts.environment_ownership_audit import audit_keys, dotenv_key_names, matching_rule

CONTRACT_PATH = Path(__file__).parents[1] / "config" / "environment_ownership.json"


class EnvironmentOwnershipAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))

    def test_exact_rule_wins_over_namespace_fallback(self):
        rule = matching_rule("CHARLIE_CORE_NOTIFICATION_MODE", self.contract["rules"])
        self.assertEqual(rule["owner"], "core_relay")

    def test_core_namespace_is_canonical_and_local(self):
        result = audit_keys(["CORE_EXECUTION_ROOT"], self.contract, "local")
        self.assertTrue(result["ready"])
        self.assertEqual(result["rows"][0]["owner"], "core")

    def test_render_rejects_local_operator_credentials(self):
        result = audit_keys(["RENDER_API_KEY"], self.contract, "render_backend")
        self.assertFalse(result["ready"])
        self.assertEqual(result["plane_mismatches"], ["RENDER_API_KEY"])

    def test_unknown_key_fails_closed(self):
        result = audit_keys(["MYSTERY_TOKEN"], self.contract, "local")
        self.assertFalse(result["ready"])
        self.assertEqual(result["unknown_keys"], ["MYSTERY_TOKEN"])

    def test_dotenv_parser_never_returns_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            path.write_text("SECRET_KEY=do-not-print\n# ignored\nPUBLIC_FLAG=1\n", encoding="utf-8")
            self.assertEqual(dotenv_key_names(path), ["PUBLIC_FLAG", "SECRET_KEY"])

    def test_aliases_are_unique_and_cross_the_intended_namespace(self):
        aliases = self.contract["proposed_aliases"]
        legacy = [item["legacy"] for item in aliases]
        canonical = [item["canonical"] for item in aliases]
        self.assertEqual(len(legacy), len(set(legacy)))
        self.assertEqual(len(canonical), len(set(canonical)))
        self.assertTrue(all(name.startswith(("CORE_", "CHARLIE_")) for name in canonical))

    def test_render_snapshot_is_fully_classified_without_values(self):
        snapshot = Path(__file__).parents[1] / "config" / "environment_snapshots" / "render_backend_keys_2026-07-19.json"
        payload = json.loads(snapshot.read_text(encoding="utf-8"))
        self.assertFalse(payload["values_captured"])
        result = audit_keys(payload["keys"], self.contract, "render_backend")
        self.assertTrue(result["ready"])
        self.assertEqual(result["unknown_keys"], [])

    def test_phase1_paginated_render_snapshot_records_known_operator_misplacements(self):
        snapshot = Path(__file__).parents[1] / "config" / "environment_snapshots" / "render_backend_keys_2026-07-19_phase1.json"
        payload = json.loads(snapshot.read_text(encoding="utf-8"))
        self.assertTrue(payload["pagination_complete"])
        self.assertEqual(payload["key_count"], 110)
        self.assertFalse(payload["values_captured"])
        result = audit_keys(payload["keys"], self.contract, "render_backend")
        self.assertEqual(result["unknown_keys"], [])
        self.assertEqual(result["plane_mismatches"], ["N8N_API_KEY", "N8N_BASE_URL"])


if __name__ == "__main__":
    unittest.main()
