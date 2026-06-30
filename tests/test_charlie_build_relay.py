import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import app
from modules.charlie.build_relay import (
    _reset_auth_rate_limit_for_tests,
    build_relay_action,
)


SECRET = "charlie-webhook-secret-32-chars-min"
BOT_TOKEN = "1234567890:charlie-test-token"


class CharlieBuildRelayTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        _reset_auth_rate_limit_for_tests()

    @patch.dict(os.environ, {}, clear=True)
    def test_policy_route_is_disabled_by_default(self):
        response = self.client.get("/api/charlie/build-relay/policy")
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["success"])
        policy = data["charlie_build_relay"]
        self.assertFalse(policy["enabled"])
        self.assertFalse(policy["sends_telegram"])
        self.assertFalse(policy["can_commit"])
        self.assertFalse(policy["can_merge"])
        self.assertFalse(policy["can_deploy"])
        self.assertFalse(policy["can_write_production_data"])

    @patch.dict(os.environ, {
        "CHARLIE_BUILD_RELAY_ENABLED": "1",
        "CHARLIE_BUILD_RELAY_BOT_TOKEN": BOT_TOKEN,
        "CHARLIE_BUILD_RELAY_WEBHOOK_SECRET": SECRET,
        "CHARLIE_BUILD_RELAY_ALLOWED_USER_IDS": "12345",
    }, clear=True)
    def test_webhook_requires_secret_header(self):
        response = self.client.post(
            "/api/charlie/build-relay/telegram/webhook",
            json={"message": {"text": "/status", "from": {"id": 12345}, "chat": {"id": 12345}}},
        )
        data = response.get_json()

        self.assertEqual(response.status_code, 403)
        self.assertFalse(data["success"])
        self.assertEqual(data["status"], "charlie_build_relay_auth_denied")

    @patch.dict(os.environ, {
        "CHARLIE_BUILD_RELAY_ENABLED": "1",
        "CHARLIE_BUILD_RELAY_BOT_TOKEN": BOT_TOKEN,
        "CHARLIE_BUILD_RELAY_WEBHOOK_SECRET": SECRET,
        "CHARLIE_BUILD_RELAY_ALLOWED_USER_IDS": "12345",
    }, clear=True)
    def test_webhook_rejects_unlisted_user(self):
        response = self.client.post(
            "/api/charlie/build-relay/telegram/webhook",
            json={"message": {"text": "/status", "from": {"id": 999}, "chat": {"id": 999}}},
            headers={"X-Telegram-Bot-Api-Secret-Token": SECRET},
        )
        data = response.get_json()

        self.assertEqual(response.status_code, 403)
        self.assertFalse(data["success"])
        self.assertEqual(data["status"], "charlie_build_relay_user_not_allowed")

    @patch.dict(os.environ, {
        "CHARLIE_BUILD_RELAY_ENABLED": "1",
        "CHARLIE_BUILD_RELAY_BOT_TOKEN": BOT_TOKEN,
        "CHARLIE_BUILD_RELAY_WEBHOOK_SECRET": SECRET,
        "CHARLIE_BUILD_RELAY_ALLOWED_USER_IDS": "12345",
    }, clear=True)
    @patch("modules.charlie.build_relay.urllib_request.urlopen")
    def test_next_command_sends_button_options_without_runtime_authority(self, urlopen):
        urlopen.return_value.__enter__.return_value.status = 200
        urlopen.return_value.__enter__.return_value.read.return_value = json.dumps({
            "ok": True,
            "result": {"message_id": 10},
        }).encode("utf-8")

        response = self.client.post(
            "/api/charlie/build-relay/telegram/webhook",
            json={"message": {"text": "/next", "from": {"id": 12345}, "chat": {"id": 12345}}},
            headers={"X-Telegram-Bot-Api-Secret-Token": SECRET},
        )
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["success"])
        self.assertEqual(data["command"], "next")
        self.assertFalse(data["charlie_build_relay"]["can_commit"])
        self.assertFalse(data["charlie_build_relay"]["can_write_production_data"])
        sent_body = json.loads(urlopen.call_args.args[0].data.decode("utf-8"))
        self.assertIn("Next mission options", sent_body["text"])
        self.assertIn("reply_markup", sent_body)

    @patch.dict(os.environ, {}, clear=True)
    def test_mission_action_prepares_intake_without_file_write_by_default(self):
        action = build_relay_action("/mission Build a safe Telegram relay")

        self.assertEqual(action["command"], "mission")
        self.assertFalse(action["writes_repo_file"])
        self.assertEqual(action["codex_chat_write"]["status"], "repo_file_write_disabled")
        self.assertEqual(action["mission"]["approval_level"], "LEVEL 3")
        self.assertIn("Mission intake prepared", action["telegram_text"])

    @patch.dict(os.environ, {}, clear=True)
    def test_start_command_returns_help(self):
        action = build_relay_action("/start")

        self.assertEqual(action["command"], "help")
        self.assertFalse(action["writes_repo_file"])
        self.assertIn("CHARLIE Build Relay", action["telegram_text"])

    def test_mission_action_can_update_codex_chat_when_explicitly_enabled(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            planning = root / "planning"
            planning.mkdir()
            codex_chat = planning / "CODEX_CHAT.md"
            codex_chat.write_text(
                "# CODEX CHAT\n\n"
                "### Concept / Problem / Idea\n\n```text\nold\n```\n\n"
                "### Desired Outcome\n\n```text\nold outcome\n```\n",
                encoding="utf-8",
            )
            env = {
                "CHARLIE_BUILD_RELAY_REPO_ROOT": str(root),
                "CHARLIE_BUILD_RELAY_CODEX_CHAT_WRITE_ENABLED": "1",
            }
            action = build_relay_action("/mission Build CHARLIE Relay", environ=env)
            updated = codex_chat.read_text(encoding="utf-8")

            self.assertTrue(action["writes_repo_file"])
            self.assertEqual(action["codex_chat_write"]["status"], "codex_chat_updated")
            self.assertIn("Build CHARLIE Relay", updated)
            self.assertIn("Codex scopes this Telegram mission", updated)


if __name__ == "__main__":
    unittest.main()
