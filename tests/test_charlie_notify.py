import unittest
from unittest.mock import patch

from scripts import charlie_notify


class CharlieNotifyTests(unittest.TestCase):
    @patch("scripts.charlie_notify.send_charlie_telegram_message")
    def test_send_with_retry_retries_until_success(self, send_message):
        send_message.side_effect = [
            ({"success": False, "status": "telegram_api_unreachable"}, 502),
            ({"success": True, "status": "telegram_sent"}, 200),
        ]

        result, status_code, attempts = charlie_notify._send_with_retry(
            "123",
            "hello",
            sleep_fn=lambda _seconds: None,
        )

        self.assertEqual(status_code, 200)
        self.assertEqual(attempts, 2)
        self.assertTrue(result["success"])


if __name__ == "__main__":
    unittest.main()
