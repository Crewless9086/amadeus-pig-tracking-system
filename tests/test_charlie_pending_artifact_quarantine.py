import unittest
from unittest.mock import patch

from modules.charlie.execution_bridge import _quarantine_pending_final_artifact


class CharliePendingArtifactQuarantineTests(unittest.TestCase):
    @patch("modules.charlie.execution_bridge.write_runner_heartbeat")
    @patch(
        "modules.charlie.execution_bridge.transition_mission_review_state",
        return_value=({"success": True}, 200),
    )
    def test_failed_recovered_artifact_blocks_only_its_mission(self, transition, heartbeat):
        mission = {
            "mission_id": "M-STALE", "status": "in_progress",
            "metadata": {"review_packet": {"summary": "Preserve me"}},
        }
        result, status = _quarantine_pending_final_artifact(
            mission, "qa_red_team", "red_team_status=fail",
        )
        self.assertEqual(status, 200)
        self.assertEqual(result["status"], "pending_final_artifact_quarantined")
        self.assertEqual(transition.call_args.args[1], "blocked")
        self.assertEqual(transition.call_args.kwargs["expected_status"], "in_progress")
        packet = transition.call_args.args[2]
        self.assertFalse(packet["block_disposition"]["owner_required"])
        self.assertEqual(packet["summary"], "Preserve me")
        heartbeat.assert_called_once()


if __name__ == "__main__":
    unittest.main()
