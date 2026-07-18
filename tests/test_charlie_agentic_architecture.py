import unittest
from unittest.mock import patch

from modules.charlie.agentic_architecture import build_agentic_architecture_packet, evaluate_agentic_architecture
from modules.charlie.core_workflow import build_core_plan
from modules.charlie import execution_bridge


class CharlieAgenticArchitectureTests(unittest.TestCase):
    def test_sam_mission_is_owned_by_sam_with_herdmaster_and_ledger(self):
        packet = build_agentic_architecture_packet({"title": "Make SAM answer livestock availability and price questions"})
        self.assertEqual(packet["domain"], "livestock_sales")
        self.assertEqual(packet["owning_agent"], "sam-live-stock")
        self.assertEqual(packet["supporting_agents"], ["herdmaster", "ledger"])
        self.assertIn("generalization beyond the original example", packet["acceptance_questions"][-1])

    def test_farm_mission_is_coordinated_by_oom_sakkie(self):
        packet = build_agentic_architecture_packet({"title": "Give the farm manager a daily herd and feed brief"})
        self.assertEqual(packet["domain"], "farm")
        self.assertEqual(packet["owning_agent"], "oom-sakkie")
        self.assertEqual(packet["coordinating_agent"], "oom-sakkie")

    def test_core_plan_freezes_agentic_packet_before_builder(self):
        plan = build_core_plan({"mission_type": "feature build", "title": "SAM livestock agent improvement"})
        packet = plan["agentic_architecture"]
        self.assertEqual(packet["status"], "frozen_before_builder")
        self.assertEqual(plan["project_truth"]["agentic_architecture"], packet)

    def test_gate_rejects_missing_packet_and_reported_noncompliance(self):
        missing = evaluate_agentic_architecture({"metadata": {}}, {})
        self.assertFalse(missing["passed"])
        mission = {"metadata": {"agentic_architecture": build_agentic_architecture_packet({"title": "SAM sales"})}}
        failed = evaluate_agentic_architecture(mission, {"builder": {"agentic_architecture": {"compliant": False, "reason": "reply-specific regex branch"}}})
        self.assertFalse(failed["passed"])
        self.assertIn("reply-specific regex branch", " ".join(failed["findings"]))

    @patch("modules.charlie.execution_bridge.update_mission_vault")
    def test_execution_persists_packet_without_replacing_charlie_core(self, update):
        mission = {"mission_id": "M1", "title": "Farm attention agent", "mission_type": "feature build", "raw_text": "Build farm attention agent", "metadata": {"charlie_core": {"project_truth": {"keep": True}}}, "vault": {}}
        execution_bridge._ensure_execution_governance(mission)
        payload = update.call_args.args[1]
        self.assertIn("agentic_architecture", payload)
        self.assertNotIn("charlie_core", payload)
        self.assertTrue(mission["metadata"]["charlie_core"]["project_truth"]["keep"])


if __name__ == "__main__":
    unittest.main()
