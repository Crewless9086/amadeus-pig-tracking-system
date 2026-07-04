import unittest

from modules.charlie.mission_memory import (
    append_memory_event,
    build_memory_event,
    final_artifact_contract_packet,
    memory_prompt_context,
    parallel_agent_planning_packet,
    partial_recovery_contract_packet,
    replay_packet,
)


class CharlieMissionMemoryTest(unittest.TestCase):
    def test_append_memory_event_records_latest_attempt_handoff_and_prompt_context(self):
        metadata = {}
        event = build_memory_event(
            "builder",
            "agent_complete",
            attempt=2,
            artifact={
                "summary": "Built replay console.",
                "changed_files": ["modules/charlie/routes.py"],
                "files_inspected": ["modules/charlie/routes.py"],
                "commands_run": ["python -m unittest tests.test_charlie_build_relay"],
                "confidence": "0.97",
                "confidence_reason": "Focused tests passed.",
                "next_action": "Send to tester.",
            },
            quality_gate={"passed": True, "reason": "ok"},
        )

        updated = append_memory_event(metadata, event)
        memory = updated["mission_memory"]
        prompt = memory_prompt_context(updated)

        self.assertEqual(memory["latest_by_agent"]["builder"]["attempt"], 2)
        self.assertEqual(memory["attempts"][0]["agent"], "builder")
        self.assertEqual(memory["handoffs"][0]["from_agent"], "builder")
        self.assertEqual(prompt["latest_agent_notes"][0]["agent"], "builder")
        self.assertIn("Built replay console", prompt["latest_agent_notes"][0]["summary"])

    def test_replay_packet_combines_memory_execution_and_debug_focus(self):
        metadata = append_memory_event({}, build_memory_event("tester", "agent_blocked", summary="Tests failed."))
        metadata["review_packet"] = {
            "blocked_agent": "tester",
            "blocked_reason": "Tests failed.",
            "backflow_events": [{"from_agent": "tester", "to_agent": "builder", "reason": "fix tests"}],
            "quality_gates": [{"agent": "tester", "passed": False}],
        }
        mission = {"mission_id": "MISSION-1", "title": "Replay", "status": "blocked", "metadata": metadata}

        packet = replay_packet(mission)

        self.assertEqual(packet["mission_id"], "MISSION-1")
        self.assertEqual(packet["debug_focus"]["blocked_agent"], "tester")
        self.assertTrue(packet["timeline"])
        self.assertIn("Inspect blocked artifact", packet["next_debug_actions"][0])

    def test_contract_packets_explain_required_agentic_controls(self):
        self.assertEqual(final_artifact_contract_packet()["version"], "charlie_final_artifact_contract_v2")
        self.assertEqual(partial_recovery_contract_packet()["version"], "charlie_partial_recovery_agent_v1")
        plan = parallel_agent_planning_packet(["idea_expander", "source_mapper", "builder", "tester", "reviewer"])
        self.assertIn("idea_expander", plan["read_only_parallel_agents"])
        self.assertIn("builder", plan["serialized_write_agents"])
        self.assertIn("reviewer", plan["review_and_challenge_agents"])


if __name__ == "__main__":
    unittest.main()
