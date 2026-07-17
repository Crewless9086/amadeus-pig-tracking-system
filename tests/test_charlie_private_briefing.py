import unittest
from datetime import datetime, timedelta, timezone

from modules.charlie.private_briefing import _due


class CharliePrivateBriefingTests(unittest.TestCase):
    def test_follow_up_due_check_is_timezone_safe(self):
        now = datetime.now(timezone.utc)
        self.assertTrue(_due((now - timedelta(seconds=1)).isoformat(), now))
        self.assertFalse(_due((now + timedelta(minutes=1)).isoformat(), now))
        self.assertFalse(_due("not-a-date", now))


if __name__ == "__main__":
    unittest.main()
