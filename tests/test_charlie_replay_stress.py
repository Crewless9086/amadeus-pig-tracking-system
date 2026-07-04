import unittest

from modules.charlie.replay_stress import golden_example_candidate, stress_replay_mission, stress_replay_missions


class CharlieReplayStressTests(unittest.TestCase):
    def test_replay_stress_scores_blocked_mission_with_recovery(self):
        mission = {
            "mission_id": "MISSION-BLOCKED",
            "status": "blocked",
            "metadata": {
                "mission_memory": {
                    "events": [{"agent": "builder", "type": "agent_blocked", "summary": "No final artifact."}],
                    "recovery_notes": [{"agent": "builder", "summary": "Rerun builder."}],
                },
                "review_packet": {
                    "blocked_reason": "No final artifact.",
                    "partial_recovery": {"recommended_next_action": "Rerun builder."},
                },
            },
        }

        result = stress_replay_mission(mission)

        self.assertGreaterEqual(result["score"], 82)
        self.assertEqual(result["status"], "pass")

    def test_replay_stress_flags_missing_memory_and_tests(self):
        mission = {"mission_id": "MISSION-WEAK", "metadata": {"review_packet": {"review_status": "ready_for_owner_review"}}}

        result = stress_replay_mission(mission)

        self.assertEqual(result["status"], "needs_repair")
        issue_names = {issue["name"] for issue in result["issues"]}
        self.assertIn("test_evidence", issue_names)
        self.assertIn("memory_recorded", issue_names)

    def test_golden_example_candidate_requires_high_quality_review_ready_packet(self):
        mission = {
            "mission_id": "MISSION-GOLD",
            "mission_type": "dashboard ui",
            "title": "Excellent dashboard",
            "metadata": {
                "mission_memory": {"events": [{"agent": "reviewer", "type": "agent_complete", "summary": "Ready."}]},
                "review_packet": {
                    "review_status": "ready_for_owner_review",
                    "summary": "Ready.",
                    "test_evidence": ["unit tests passed"],
                    "execution_artifacts": {"agent_ledger_path": ".charlie_runner/executions/x.agent-ledger.json"},
                },
            },
        }

        candidate = golden_example_candidate(mission)

        self.assertTrue(candidate["qualifies"])
        self.assertEqual(candidate["example_type"], "dashboard_ui")

    def test_stress_replay_missions_returns_average(self):
        result = stress_replay_missions([
            {"mission_id": "A", "metadata": {"review_packet": {"blocked_reason": "blocked"}, "mission_memory": {"recovery_notes": [{}]}}},
            {"mission_id": "B", "metadata": {"review_packet": {"review_status": "ready_for_owner_review"}}},
        ])

        self.assertEqual(result["mission_count"], 2)
        self.assertIn("average_score", result)


if __name__ == "__main__":
    unittest.main()
