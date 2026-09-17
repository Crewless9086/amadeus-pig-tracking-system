import unittest

from modules.charlie.private_policy import authenticate_private_update, authority_for_intent, private_policy


ENV = {
    "CHARLIE_PRIVATE_EXECUTIVE_ENABLED": "1",
    "CHARLIE_PRIVATE_TELEGRAM_BOT_TOKEN": "test-token",
    "CHARLIE_PRIVATE_TELEGRAM_WEBHOOK_SECRET": "s" * 32,
    "CHARLIE_PRIVATE_TELEGRAM_OWNER_USER_ID": "10",
    "CHARLIE_PRIVATE_TELEGRAM_OWNER_CHAT_ID": "10",
}


class CharliePrivatePolicyTests(unittest.TestCase):
    def test_ready_policy_redacts_only_at_route_boundary(self):
        self.assertTrue(private_policy(ENV)["enabled"])

    def test_auth_requires_secret_owner_and_private_chat(self):
        payload = {"message": {"from": {"id": 10}, "chat": {"id": 10, "type": "private"}}}
        self.assertTrue(authenticate_private_update(payload, {"X-Telegram-Bot-Api-Secret-Token": "s" * 32}, ENV)["allowed"])
        payload["message"]["chat"]["type"] = "group"
        self.assertEqual(authenticate_private_update(payload, {"X-Telegram-Bot-Api-Secret-Token": "s" * 32}, ENV)["reason"], "private_chat_binding_denied")

    def test_red_zone_never_delegates(self):
        result = authority_for_intent("create_mission", ["payment"], explicit_owner_command=True)
        self.assertFalse(result["allowed"])
        self.assertEqual(result["tier"], "charl_human")


if __name__ == "__main__":
    unittest.main()
