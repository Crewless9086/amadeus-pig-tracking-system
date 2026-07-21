import unittest

from modules.charlie.outcome_closure import operational_outcome_closure, outcome_follow_up_mission


class CharlieOutcomeClosureTests(unittest.TestCase):
    def deployed_migration(self):
        return {
            "mission_id": "M-MIGRATION",
            "status": "deployed",
            "title": "Lifecycle audit rail",
            "urgency": "P1",
            "metadata": {"review_packet": {
                "review_status": "final_approved",
                "changed_files": ["supabase/migrations/202607210001_example.sql"],
                "test_evidence": ["38 tests passed"],
            }},
        }

    def test_deployed_migration_is_not_reported_as_operational(self):
        closure = operational_outcome_closure(self.deployed_migration())
        self.assertTrue(closure["unfinished"])
        self.assertEqual(closure["business_capability_status"], "not_operational")
        self.assertTrue(closure["owner_required"])
        self.assertIn("migration_applied", closure["pending_gate_keys"])

    def test_follow_up_is_proposed_but_never_approved(self):
        mission = self.deployed_migration()
        follow_up = outcome_follow_up_mission(mission, operational_outcome_closure(mission))
        self.assertEqual(follow_up["status"], "new")
        self.assertEqual(follow_up["approval_level"], "LEVEL 5")
        self.assertEqual(follow_up["metadata"]["protected_operations"][0]["status"], "owner_gated")
        self.assertEqual(follow_up["metadata"]["mission_family"]["parent_mission_id"], "M-MIGRATION")

    def test_verified_operational_evidence_closes_business_outcome(self):
        mission = self.deployed_migration()
        mission["metadata"]["review_packet"].update({
            "migration_owner_approved": True,
            "migration_applied": True,
        })
        closure = operational_outcome_closure(mission)
        self.assertFalse(closure["unfinished"])
        self.assertEqual(closure["business_capability_status"], "operational")


if __name__ == "__main__":
    unittest.main()
