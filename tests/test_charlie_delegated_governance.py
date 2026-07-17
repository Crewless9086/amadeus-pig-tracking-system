import unittest

from modules.charlie.delegated_governance import delegated_review_assessment, queue_candidate_assessment


def ready_mission(**overrides):
    mission = {
        "mission_id": "M-READY", "status": "pr_ready", "title": "Update documentation",
        "approval_level": "LEVEL 3", "raw_text": "Improve documentation",
        "metadata": {"review_packet": {
            "review_status": "ready_for_owner_review", "changed_files": ["docs/guide.md"],
            "test_evidence": ["focused checks passed"], "recommended_owner_decision": "approve_final_release",
            "pr_url": "https://github.com/org/repo/pull/1", "tested_revision": "abc",
        }},
    }
    mission.update(overrides)
    return mission


GREEN_PR = {
    "success": True, "state": "OPEN", "mergeable": "MERGEABLE", "baseRefName": "main",
    "headRefOid": "abc", "statusCheckRollup": [{"conclusion": "SUCCESS"}],
}


class CharlieDelegatedGovernanceTests(unittest.TestCase):
    def test_green_low_risk_review_can_be_delegated(self):
        result = delegated_review_assessment(ready_mission(), pr_state=GREEN_PR)
        self.assertTrue(result["allowed"])
        self.assertEqual(result["action"], "delegate_final_review")

    def test_migration_never_auto_approves(self):
        mission = ready_mission()
        mission["metadata"]["review_packet"]["changed_files"] = ["supabase/migrations/001.sql"]
        result = delegated_review_assessment(mission, pr_state=GREEN_PR)
        self.assertFalse(result["allowed"])
        self.assertEqual(result["reason"], "protected_surface_requires_owner")

    def test_customer_send_never_auto_approves(self):
        result = delegated_review_assessment(ready_mission(raw_text="Implement customer send"), pr_state=GREEN_PR)
        self.assertFalse(result["allowed"])

    def test_new_low_risk_mission_can_enter_runway(self):
        mission = {**ready_mission(), "status": "new"}
        self.assertTrue(queue_candidate_assessment(mission)["allowed"])

    def test_level_four_new_mission_waits_for_owner(self):
        mission = {**ready_mission(), "status": "new", "approval_level": "LEVEL 4"}
        self.assertFalse(queue_candidate_assessment(mission)["allowed"])


if __name__ == "__main__":
    unittest.main()
