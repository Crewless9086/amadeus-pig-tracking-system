import unittest
from unittest.mock import patch

from modules.charlie.private_tools import execute_private_tool


class CharliePrivateToolsTests(unittest.TestCase):
    @patch("modules.charlie.private_tools.update_mission_status")
    @patch("modules.charlie.private_tools.get_mission")
    def test_approve_reloads_and_uses_compare_and_set(self, get_mission, update_status):
        get_mission.return_value = ({"mission": {"mission_id": "M1", "status": "new"}}, 200)
        update_status.return_value = ({"success": True, "status": "ok"}, 200)
        result, status = execute_private_tool("approve_mission", {"mission_id": "M1"})
        self.assertEqual(status, 200)
        self.assertTrue(result["success"])
        self.assertEqual(update_status.call_args.kwargs["expected_status"], "new")

    @patch("modules.charlie.private_tools.transition_mission_review_state")
    @patch("modules.charlie.private_tools.get_mission")
    def test_send_back_uses_authoritative_review_transition(self, get_mission, transition):
        get_mission.return_value = ({"mission": {"mission_id": "M1", "status": "blocked", "metadata": {"review_packet": {"responsible_stage": "builder"}}}}, 200)
        transition.return_value = ({"success": True, "status": "review_state_transitioned"}, 200)
        result, status = execute_private_tool("send_back_mission", {"mission_id": "M1"})
        self.assertEqual(status, 200)
        self.assertEqual(result["target_stage"], "builder")
        self.assertEqual(transition.call_args.kwargs["expected_status"], "blocked")

    def test_unknown_tool_fails_closed(self):
        result, status = execute_private_tool("customer_send", {})
        self.assertEqual(status, 400)
        self.assertFalse(result["success"])


if __name__ == "__main__":
    unittest.main()
