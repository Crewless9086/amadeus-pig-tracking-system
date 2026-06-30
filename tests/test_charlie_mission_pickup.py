import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import charlie_mission_pickup


MISSION = {
    "mission_id": "CHARLIE-MISSION-123",
    "status": "approved",
    "title": "Build useful thing",
    "raw_text": "Build useful thing from Telegram.",
    "urgency": "P2",
    "mission_type": "feature build",
    "approval_level": "LEVEL 3",
}


class CharlieMissionPickupTests(unittest.TestCase):
    @patch("scripts.charlie_mission_pickup.list_missions")
    def test_pickup_reports_no_available_mission(self, list_missions):
        list_missions.return_value = ({"success": True, "status": "ok", "missions": []}, 200)

        result, status_code = charlie_mission_pickup.pick_up_next_mission()

        self.assertEqual(status_code, 200)
        self.assertTrue(result["success"])
        self.assertEqual(result["status"], "no_mission_available")

    @patch("scripts.charlie_mission_pickup.list_missions")
    def test_dry_run_does_not_write_or_update_status(self, list_missions):
        list_missions.return_value = ({"success": True, "status": "ok", "missions": [MISSION]}, 200)

        with patch("scripts.charlie_mission_pickup.update_mission_status") as update_status:
            result, status_code = charlie_mission_pickup.pick_up_next_mission(dry_run=True)

        self.assertEqual(status_code, 200)
        self.assertEqual(result["status"], "dry_run")
        self.assertEqual(result["mission_id"], "CHARLIE-MISSION-123")
        update_status.assert_not_called()

    @patch("scripts.charlie_mission_pickup.list_missions")
    @patch("scripts.charlie_mission_pickup.update_mission_status")
    def test_pickup_writes_codex_chat_and_marks_in_progress(self, update_status, list_missions):
        list_missions.return_value = ({"success": True, "status": "ok", "missions": [MISSION]}, 200)
        update_status.return_value = ({"success": True, "status": "ok", "mission_status": "in_progress"}, 200)

        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "CODEX_CHAT.md"
            with patch("scripts.charlie_mission_pickup.CODEX_CHAT_PATH", target):
                result, status_code = charlie_mission_pickup.pick_up_next_mission()
            content = target.read_text(encoding="utf-8")

        self.assertEqual(status_code, 200)
        self.assertTrue(result["success"])
        self.assertEqual(result["status"], "mission_picked_up")
        self.assertIn("Build useful thing from Telegram.", content)
        self.assertIn("CHARLIE_MISSION_PROTOCOL.md", content)
        update_status.assert_called_once()
        self.assertEqual(update_status.call_args.args[1], "in_progress")


if __name__ == "__main__":
    unittest.main()
