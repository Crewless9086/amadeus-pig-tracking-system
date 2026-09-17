import unittest

from modules.charlie.environment import EnvironmentConflictError, alias_environment, core_agent_env_value, env_truthy, env_value
from modules.charlie.build_relay import build_relay_policy
from modules.charlie.private_policy import private_policy


class CharlieEnvironmentTests(unittest.TestCase):
    def test_absent_uses_default(self):
        self.assertEqual(env_value("CORE_NOTIFICATION_MODE", "all", environ={}), "all")

    def test_legacy_only_is_supported(self):
        self.assertEqual(env_value("CORE_NOTIFICATION_MODE", environ={"CHARLIE_CORE_NOTIFICATION_MODE": "blocked"}), "blocked")

    def test_canonical_only_is_supported(self):
        self.assertEqual(env_value("CORE_NOTIFICATION_MODE", environ={"CORE_NOTIFICATION_MODE": "all"}), "all")

    def test_equal_dual_is_supported(self):
        source = {"CORE_NOTIFICATION_MODE": "all", "CHARLIE_CORE_NOTIFICATION_MODE": "all"}
        self.assertEqual(env_value("CORE_NOTIFICATION_MODE", environ=source), "all")

    def test_conflicting_dual_fails_without_values(self):
        source = {"CORE_NOTIFICATION_MODE": "secret-a", "CHARLIE_CORE_NOTIFICATION_MODE": "secret-b"}
        with self.assertRaises(EnvironmentConflictError) as raised:
            env_value("CORE_NOTIFICATION_MODE", environ=source)
        self.assertNotIn("secret-a", str(raised.exception))
        self.assertNotIn("secret-b", str(raised.exception))

    def test_alias_mapping_supports_existing_policy_get_calls(self):
        source = alias_environment({"CHARLIE_PRIVATE_LLM_ENABLED": "1"})
        self.assertTrue(env_truthy("CHARLIE_LLM_ENABLED", environ=source))

    def test_dynamic_core_model_alias(self):
        source = {"CHARLIE_AGENT_MODEL_PLANNER": "legacy-model"}
        self.assertEqual(core_agent_env_value("AGENT_MODEL", "PLANNER", environ=source), "legacy-model")

    def test_charlie_executive_policy_accepts_canonical_only(self):
        source = {
            "CHARLIE_EXECUTIVE_ENABLED": "1", "CHARLIE_TELEGRAM_BOT_TOKEN": "token",
            "CHARLIE_TELEGRAM_WEBHOOK_SECRET": "s" * 32,
            "CHARLIE_TELEGRAM_OWNER_USER_ID": "1", "CHARLIE_TELEGRAM_OWNER_CHAT_ID": "1",
        }
        self.assertTrue(private_policy(source)["enabled"])

    def test_core_relay_policy_accepts_canonical_only(self):
        source = {
            "CORE_RELAY_ENABLED": "1", "CORE_RELAY_BOT_TOKEN": "token",
            "CORE_RELAY_WEBHOOK_SECRET": "s" * 32, "CORE_RELAY_ALLOWED_USER_IDS": "1",
        }
        self.assertTrue(build_relay_policy(source)["enabled"])

    def test_charlie_and_core_tokens_may_differ_without_conflict(self):
        source = {
            "CHARLIE_PRIVATE_TELEGRAM_BOT_TOKEN": "executive-token",
            "CHARLIE_BUILD_RELAY_BOT_TOKEN": "core-token",
        }
        self.assertEqual(env_value("CHARLIE_TELEGRAM_BOT_TOKEN", environ=source), "executive-token")
        self.assertEqual(env_value("CORE_RELAY_BOT_TOKEN", environ=source), "core-token")


if __name__ == "__main__":
    unittest.main()
