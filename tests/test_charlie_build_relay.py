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
        self.assertEqual(action["mission_store"]["status"], "not_configured")
        self.assertEqual(action["mission"]["approval_level"], "LEVEL 3")
        self.assertIn("Mission intake prepared", action["telegram_text"])

    @patch.dict(os.environ, {"CHARLIE_BUILD_RELAY_MISSION_STORE_ENABLED": "0"}, clear=True)
    def test_mission_store_can_be_disabled(self):
        action = build_relay_action("/mission Build a safe Telegram relay")

        self.assertEqual(action["command"], "mission")
        self.assertEqual(action["mission_store"]["status"], "mission_store_disabled")
        self.assertFalse(action["writes_repo_file"])

    @patch.dict(os.environ, {"CHARLIE_BUILD_RELAY_MISSION_STORE_ENABLED": "1"}, clear=True)
    @patch("modules.charlie.build_relay.record_mission")
    def test_mission_action_records_mission_when_store_enabled(self, record_mission):
        record_mission.return_value = ({"stored": True, "status": "ok", "mission_id": "MISSION-1"}, 201)

        action = build_relay_action(
            "/mission Build a safe Telegram relay",
            environ={
                "CHARLIE_BUILD_RELAY_MISSION_STORE_ENABLED": "1",
                "_charlie_telegram_user_id": "12345",
                "_charlie_telegram_chat_id": "67890",
            },
        )

        self.assertEqual(action["mission_store"]["status"], "ok")
        self.assertEqual(action["mission_store"]["mission_id"], "MISSION-1")
        record_mission.assert_called_once()
        _, kwargs = record_mission.call_args
        self.assertEqual(kwargs["source_context"]["telegram_user_id"], "12345")
        self.assertEqual(kwargs["source_context"]["telegram_chat_id"], "67890")

    @patch("modules.charlie.build_relay.mission_status_summary")
    @patch("modules.charlie.build_relay.list_missions")
    def test_missions_command_lists_recent_queue_records(self, list_missions, mission_status_summary):
        mission_status_summary.return_value = ({"success": True, "status": "ok", "counts": {"new": 2}}, 200)
        list_missions.return_value = ({
            "success": True,
            "status": "ok",
            "missions": [{
                "status": "new",
                "urgency": "P1",
                "title": "Test mission",
            }],
        }, 200)

        action = build_relay_action("/missions")

        self.assertEqual(action["command"], "missions")
        self.assertFalse(action["writes_repo_file"])
        self.assertIn("new=2", action["telegram_text"])
        self.assertIn("Test mission", action["telegram_text"])

    @patch("modules.charlie.build_relay.get_mission")
    def test_mission_id_command_shows_mission_detail(self, get_mission):
        get_mission.return_value = ({
            "success": True,
            "status": "ok",
            "mission": {
                "mission_id": "CHARLIE-MISSION-ABC12345",
                "status": "new",
                "urgency": "P2",
                "mission_type": "feature build",
                "approval_level": "LEVEL 3",
                "title": "Build console",
                "owner_decision": "",
            },
        }, 200)

        action = build_relay_action("/mission CHARLIE-MISSION-ABC12345")

        self.assertEqual(action["command"], "mission_detail")
        self.assertFalse(action["writes_repo_file"])
        self.assertIn("Build console", action["telegram_text"])
        self.assertIn("/approve <id>", action["telegram_text"])
        self.assertIn("inline_keyboard", action["reply_markup"])

    @patch("modules.charlie.build_relay.update_mission_status")
    def test_approve_command_records_decision_without_runtime_authority(self, update_mission_status):
        update_mission_status.return_value = ({
            "success": True,
            "status": "ok",
            "mission_id": "CHARLIE-MISSION-ABC12345",
            "mission_status": "approved",
        }, 200)

        action = build_relay_action("/approve CHARLIE-MISSION-ABC12345")

        self.assertEqual(action["command"], "approve")
        self.assertFalse(action["writes_repo_file"])
        self.assertIn("Mission approved", action["telegram_text"])
        self.assertIn("does not execute build actions", action["telegram_text"])
        update_mission_status.assert_called_once()
        self.assertEqual(update_mission_status.call_args.args[1], "approved")
        self.assertEqual(update_mission_status.call_args.kwargs["event_type"], "approval_decision")

    @patch("modules.charlie.build_relay.update_mission_status")
    def test_approve_command_records_requested_approval_level(self, update_mission_status):
        update_mission_status.return_value = ({
            "success": True,
            "status": "ok",
            "mission_id": "CHARLIE-MISSION-ABC12345",
            "mission_status": "approved",
            "approval_level": "LEVEL 4",
        }, 200)

        action = build_relay_action("/approve CHARLIE-MISSION-ABC12345 level4")

        self.assertEqual(action["command"], "approve")
        self.assertIn("Approval: LEVEL 4", action["telegram_text"])
        self.assertEqual(update_mission_status.call_args.kwargs["approval_level"], "LEVEL 4")
        self.assertFalse(action["writes_repo_file"])

    @patch("modules.charlie.build_relay.update_mission_status")
    def test_pause_and_reject_commands_record_decisions(self, update_mission_status):
        update_mission_status.return_value = ({
            "success": True,
            "status": "ok",
            "mission_id": "CHARLIE-MISSION-ABC12345",
            "mission_status": "paused",
        }, 200)

        pause = build_relay_action("/pause CHARLIE-MISSION-ABC12345")
        reject = build_relay_action("reject:CHARLIE-MISSION-ABC12345")

        self.assertEqual(pause["command"], "pause")
        self.assertEqual(reject["command"], "reject")
        self.assertFalse(pause["writes_repo_file"])
        self.assertFalse(reject["writes_repo_file"])

    @patch("modules.charlie.routes.require_owner_read_access", return_value=None)
    @patch("modules.charlie.routes.list_missions")
    def test_missions_route_returns_queue_records(self, list_missions, _owner_access):
        list_missions.return_value = ({
            "success": True,
            "status": "ok",
            "missions": [{"mission_id": "MISSION-1", "title": "Test mission"}],
        }, 200)

        response = self.client.get("/api/charlie/build-relay/missions?limit=1")
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["success"])
        self.assertEqual(data["missions"][0]["mission_id"], "MISSION-1")
        list_missions.assert_called_once_with(status="", limit="1")

    @patch("modules.charlie.routes.require_owner_read_access", return_value=None)
    @patch("modules.charlie.routes.mission_status_summary")
    def test_missions_summary_route_returns_counts(self, mission_status_summary, _owner_access):
        mission_status_summary.return_value = ({
            "success": True,
            "status": "ok",
            "counts": {"approved": 2},
        }, 200)

        response = self.client.get("/api/charlie/build-relay/missions/summary")
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["success"])
        self.assertEqual(data["counts"]["approved"], 2)

    @patch("modules.charlie.routes.require_owner_read_access", return_value=None)
    @patch("modules.charlie.routes.get_mission")
    def test_mission_detail_route_returns_record(self, get_mission, _owner_access):
        get_mission.return_value = ({
            "success": True,
            "status": "ok",
            "mission": {"mission_id": "MISSION-1", "title": "Test mission"},
        }, 200)

        response = self.client.get("/api/charlie/build-relay/missions/MISSION-1")
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["success"])
        self.assertEqual(data["mission"]["mission_id"], "MISSION-1")
        get_mission.assert_called_once_with("MISSION-1")

    @patch("modules.charlie.routes.require_owner_read_access", return_value=None)
    @patch("modules.charlie.routes.update_mission_status")
    def test_mission_decision_route_records_owner_decision(self, update_mission_status, _owner_access):
        update_mission_status.return_value = ({
            "success": True,
            "status": "ok",
            "mission_id": "MISSION-1",
            "mission_status": "approved",
        }, 200)

        response = self.client.post(
            "/api/charlie/build-relay/missions/MISSION-1/decision",
            json={"status": "approved", "approval_level": "LEVEL 3", "owner_decision": "Owner approved."},
        )
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["success"])
        update_mission_status.assert_called_once()
        self.assertEqual(update_mission_status.call_args.args[1], "approved")
        self.assertEqual(update_mission_status.call_args.kwargs["approval_level"], "LEVEL 3")
        self.assertEqual(update_mission_status.call_args.kwargs["event_type"], "approval_decision")

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
