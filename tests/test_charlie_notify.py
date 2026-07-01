import os
import sys
import unittest
from unittest.mock import patch

from scripts import charlie_notify


class CharlieNotifyTests(unittest.TestCase):
    @patch.dict(os.environ, {"CHARLIE_BUILD_RELAY_ALLOWED_USER_IDS": "12345"}, clear=True)
    def test_dry_run_includes_mission_status_reply_markup(self):
        argv = [
            "charlie_notify.py",
            "--level",
            "info",
            "--title",
            "Mission picked up",
            "--message",
            "Codex picked up a mission.",
            "--mission-id",
            "CHARLIE-MISSION-123",
            "--dry-run",
        ]

        with patch.object(sys, "argv", argv), patch("builtins.print") as print_call:
            result = charlie_notify.main()

        self.assertEqual(result, 0)
        payload = print_call.call_args.args[0]
        self.assertEqual(payload["status"], "dry_run")
        self.assertEqual(
            payload["reply_markup"]["inline_keyboard"][0][0]["callback_data"],
            "status:CHARLIE-MISSION-123",
        )


if __name__ == "__main__":
    unittest.main()
