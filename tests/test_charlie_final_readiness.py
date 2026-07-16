import unittest

from modules.charlie.final_readiness import evaluate_final_readiness


class CharlieFinalReadinessTests(unittest.TestCase):
    def mission(self, changed_files, **packet_updates):
        packet = {
            "review_status": "ready_for_owner_review",
            "changed_files": changed_files,
            "test_evidence": ["Focused tests passed."],
            **packet_updates,
        }
        return {"status": "pr_ready", "metadata": {"review_packet": packet}}

    def test_backend_change_can_authorize_release_before_release_bridge(self):
        result = evaluate_final_readiness(self.mission(["modules/charlie/example.py"]))
        self.assertEqual(result["verdict"], "ready_to_approve")
        self.assertTrue(result["can_authorize_release"])
        self.assertFalse(result["final_operational_ready"])

    def test_migration_requires_explicit_owner_approval(self):
        result = evaluate_final_readiness(self.mission(["supabase/migrations/202607160001_example.sql"]))
        self.assertEqual(result["verdict"], "owner_action_required")
        self.assertFalse(result["can_authorize_release"])
        self.assertEqual(result["review_phase"], "needs_owner_action")
        self.assertIn("migration_approval", result["pending_gate_keys"])

    def test_already_merged_migration_requires_apply_and_live_verification(self):
        result = evaluate_final_readiness(self.mission(
            ["supabase/migrations/202607160001_example.sql", "modules/example.py"],
            migration_owner_approved=True,
            merge_commit="abc123",
        ))
        self.assertEqual(result["verdict"], "verification_required")
        self.assertFalse(result["can_authorize_release"])
        self.assertIn("migration_applied", result["pending_gate_keys"])
        self.assertIn("deployment", result["pending_gate_keys"])

    def test_operational_evidence_completes_all_gates(self):
        result = evaluate_final_readiness(self.mission(
            ["supabase/migrations/202607160001_example.sql", "templates/example.html"],
            migration_owner_approved=True,
            migration_applied=True,
            visual_verified=True,
            deployment_verified=True,
            live_smoke_passed=True,
        ))
        self.assertEqual(result["verdict"], "ready_to_approve")
        self.assertTrue(result["can_authorize_release"])
        self.assertTrue(result["final_operational_ready"])

    def test_missing_test_evidence_locks_approval(self):
        mission = self.mission(["modules/example.py"])
        mission["metadata"]["review_packet"]["test_evidence"] = []
        result = evaluate_final_readiness(mission)
        self.assertEqual(result["verdict"], "verification_required")
        self.assertIn("tests", result["pending_gate_keys"])


if __name__ == "__main__":
    unittest.main()
