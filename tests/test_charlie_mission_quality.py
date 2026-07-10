import unittest

from modules.charlie.mission_quality import (
    build_recovery_packet,
    classify_known_failures,
    repo_test_command_memory,
    score_mission_quality,
)


class CharlieMissionQualityTests(unittest.TestCase):
    def test_classifies_missing_pytest_as_known_failure(self):
        failures = classify_known_failures("python -m pytest failed: No module named pytest")

        self.assertEqual(failures[0]["code"], "pytest_missing")
        self.assertIn("Run the focused unittest command", " ".join(failures[0]["recovery_steps"]))

    def test_repo_test_command_memory_prefers_unittest_for_charlie_changes(self):
        memory = repo_test_command_memory(["modules/charlie/execution_bridge.py", "static/js/charlieMissionControl.js"])
        commands = [item["command"] for item in memory["commands"]]

        self.assertFalse(memory["pytest_allowed"])
        self.assertTrue(any(
            command.endswith("-m unittest tests.test_charlie_execution_bridge tests.test_charlie_core_workflow tests.test_charlie_mission_store tests.test_charlie_improvement_analyst")
            for command in commands
        ))
        self.assertIn("node --check static\\js\\charlieMissionControl.js", commands)

    def test_recovery_packet_includes_known_failures_and_rerun_stage(self):
        packet = build_recovery_packet(
            agent="reviewer",
            blocked_reason="Visual Review media was not captured. No module named pytest.",
            artifact={"changed_files": ["static/js/charlieMissionControl.js"]},
            ledger={"backflow_events": [{"to_agent": "builder"}]},
        )

        self.assertEqual(packet["version"], "charlie_recovery_packet_v2")
        self.assertEqual(packet["rerun_from_stage"], "builder")
        self.assertEqual({item["code"] for item in packet["known_failures"]}, {"pytest_missing", "review_media_missing"})
        self.assertTrue(packet["preferred_test_commands"]["commands"])

    def test_score_mission_quality_scores_complete_review_packet(self):
        score = score_mission_quality(
            {"mission_id": "M1", "agent_workflow": [{"agent": "builder"}]},
            {
                "review_status": "ready_for_owner_review",
                "test_evidence": ["python -m unittest tests.test_example: OK"],
                "changed_files": ["modules/example.py"],
                "local_preview": {"url": "http://127.0.0.1:5000/example"},
                "brain_guard": {"passed": True},
                "review_board": {"reviews": []},
                "backflow_events": [],
                "recovery_packet": {"version": "charlie_recovery_packet_v2"},
            },
            {"stages": [{"agent": "builder", "status": "complete"}]},
        )

        self.assertGreaterEqual(score["score"], 96)
        self.assertEqual(score["grade"], "release_confident")
        self.assertEqual(score["blockers"], [])


if __name__ == "__main__":
    unittest.main()
