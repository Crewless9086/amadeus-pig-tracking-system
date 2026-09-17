import unittest

from scripts import build_relay_notify


class BuildRelayNotifyTests(unittest.TestCase):
    def test_disabled_relay_does_nothing_without_env(self):
        result = build_relay_notify.notify("DONE", environ={})

        self.assertTrue(result.ok)
        self.assertEqual(result.status, "disabled")
        self.assertEqual(result.sent, 0)

    def test_enabled_missing_env_fails_safely(self):
        result = build_relay_notify.notify(
            "RUNNING",
            environ={"CHARLIE_BUILD_RELAY_ENABLED": "1"},
        )

        self.assertFalse(result.ok)
        self.assertEqual(result.status, "missing_env")
        self.assertIn("required", result.reason)

    def test_message_body_redacts_secrets(self):
        message = build_relay_notify.build_message(
            "HARD_STOP",
            detail="token=123456:abcdefghijklmnopqrstuvwxyzABCDEF sk-testsecret123456",
        )

        self.assertIn("[REDACTED]", message)
        self.assertNotIn("abcdefghijklmnopqrstuvwxyz", message)
        self.assertNotIn("sk-testsecret", message)

    def test_pr_ready_message_format(self):
        message = build_relay_notify.build_message(
            "PR_READY",
            mission_id="MISSION-123",
            title="Fix SAM sales draft",
            url="https://example.test/pr/1",
        )

        self.assertIn("CHARLIE PR_READY", message)
        self.assertIn("Mission: MISSION-123", message)
        self.assertIn("Title: Fix SAM sales draft", message)
        self.assertIn("Link: https://example.test/pr/1", message)

    def test_hard_stop_message_format(self):
        message = build_relay_notify.build_message(
            "HARD_STOP",
            mission_id="MISSION-999",
            detail="Tests cannot pass",
        )

        self.assertIn("CHARLIE HARD_STOP", message)
        self.assertIn("Detail: Tests cannot pass", message)

    def test_done_message_format(self):
        message = build_relay_notify.build_message("DONE", mission_id="MISSION-1")

        self.assertEqual(message.splitlines()[0], "CHARLIE DONE")
        self.assertIn("Mission: MISSION-1", message)

    def test_enabled_with_injected_sender_sends_to_each_allowed_user(self):
        calls = []

        def sender(chat_id, text):
            calls.append((chat_id, text))

        result = build_relay_notify.notify(
            "RUNNING",
            mission_id="M-1",
            environ={
                "CHARLIE_BUILD_RELAY_ENABLED": "true",
                "CHARLIE_BUILD_RELAY_BOT_TOKEN": "123456:abcdefghijklmnopqrstuvwxyzABCDEF",
                "CHARLIE_BUILD_RELAY_ALLOWED_USER_IDS": "100, 200",
            },
            sender=sender,
        )

        self.assertTrue(result.ok)
        self.assertEqual(result.sent, 2)
        self.assertEqual([chat_id for chat_id, _ in calls], ["100", "200"])
        self.assertTrue(all("CHARLIE RUNNING" in text for _, text in calls))


if __name__ == "__main__":
    unittest.main()

