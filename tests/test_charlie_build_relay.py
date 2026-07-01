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
from modules.charlie.mission_store import _clean_media_reference


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

    @patch("modules.charlie.build_relay.list_missions")
    def test_next_command_reports_active_queue_mission(self, list_missions):
        def fake_list_missions(status="", limit=10):
            if status == "in_progress":
                return ({
                    "success": True,
                    "status": "ok",
                    "missions": [{
                        "mission_id": "CHARLIE-MISSION-ACTIVE123",
                        "status": "in_progress",
                        "urgency": "P1",
                        "approval_level": "LEVEL 3",
                        "title": "Build active mission",
                    }],
                }, 200)
            return {"success": True, "status": "ok", "missions": []}, 200

        list_missions.side_effect = fake_list_missions

        action = build_relay_action("/next")

        self.assertEqual(action["command"], "next")
        self.assertIn("CHARLIE next", action["telegram_text"])
        self.assertIn("In progress", action["telegram_text"])
        self.assertIn("Build active mission", action["telegram_text"])
        self.assertIn("runner boundary", action["telegram_text"])
        self.assertIn("inline_keyboard", action["reply_markup"])
        self.assertFalse(action["writes_repo_file"])

    @patch("modules.charlie.build_relay.list_missions")
    def test_next_command_lists_new_missions_waiting_approval(self, list_missions):
        def fake_list_missions(status="", limit=10):
            if status == "new":
                return ({
                    "success": True,
                    "status": "ok",
                    "missions": [{
                        "mission_id": "CHARLIE-MISSION-NEW12345",
                        "status": "new",
                        "urgency": "P2",
                        "approval_level": "LEVEL 3",
                        "title": "Review owner note",
                    }],
                }, 200)
            return {"success": True, "status": "ok", "missions": []}, 200

        list_missions.side_effect = fake_list_missions

        action = build_relay_action("next")

        self.assertEqual(action["command"], "next")
        self.assertIn("Missions waiting for approval", action["telegram_text"])
        self.assertIn("Review owner note", action["telegram_text"])
        self.assertIn("/approve <id> level1, level3, or level4", action["telegram_text"])
        buttons = [button for row in action["reply_markup"]["inline_keyboard"] for button in row]
        self.assertTrue(any(button["callback_data"] == "approve:CHARLIE-MISSION-NEW12345 level3" for button in buttons))
        self.assertFalse(action["writes_repo_file"])

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

    @patch("modules.charlie.build_relay.update_mission_status")
    def test_done_command_records_completed_mission(self, update_mission_status):
        update_mission_status.return_value = ({
            "success": True,
            "status": "ok",
            "mission_id": "CHARLIE-MISSION-ABC12345",
            "mission_status": "done",
        }, 200)

        action = build_relay_action("/done CHARLIE-MISSION-ABC12345")

        self.assertEqual(action["command"], "done")
        self.assertIn("Mission done", action["telegram_text"])
        self.assertEqual(update_mission_status.call_args.args[1], "done")
        self.assertFalse(action["writes_repo_file"])

    @patch("modules.charlie.build_relay.update_mission_workflow_step")
    def test_workflow_command_records_agent_handoff(self, update_workflow):
        update_workflow.return_value = ({
            "success": True,
            "status": "ok",
            "mission_id": "CHARLIE-MISSION-ABC12345",
        }, 200)

        action = build_relay_action("/workflow CHARLIE-MISSION-ABC12345 tester complete")

        self.assertEqual(action["command"], "workflow")
        self.assertIn("Workflow updated", action["telegram_text"])
        update_workflow.assert_called_once()
        self.assertEqual(update_workflow.call_args.kwargs["agent"], "tester")
        self.assertEqual(update_workflow.call_args.kwargs["step_status"], "complete")
        self.assertFalse(action["writes_repo_file"])

    @patch("modules.charlie.build_relay.list_missions")
    def test_review_command_lists_review_ready_missions(self, list_missions):
        def fake_list_missions(status="", limit=10):
            if status == "pr_ready":
                return ({
                    "success": True,
                    "status": "ok",
                    "missions": [{
                        "mission_id": "CHARLIE-MISSION-REVIEW123",
                        "status": "pr_ready",
                        "urgency": "P1",
                        "title": "Review SAM mission",
                    }],
                }, 200)
            return {"success": True, "status": "ok", "missions": []}, 200

        list_missions.side_effect = fake_list_missions

        action = build_relay_action("/review")

        self.assertEqual(action["command"], "review")
        self.assertIn("CHARLIE review queue", action["telegram_text"])
        self.assertIn("Review SAM mission", action["telegram_text"])
        self.assertIn("inline_keyboard", action["reply_markup"])

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
    @patch("modules.charlie.routes.record_mission")
    def test_dashboard_can_create_structured_mission(self, record_mission, _owner_access):
        record_mission.return_value = ({"stored": True, "status": "ok", "mission_id": "MISSION-1"}, 201)

        response = self.client.post(
            "/api/charlie/build-relay/missions",
            json={
                "title": "Build mission vault",
                "raw_text": "Create a mission vault intake flow.",
                "desired_outcome": "Mission is stored with useful context.",
                "urgency": "P2",
                "mission_type": "agent build",
                "media_references": [{"label": "Sketch", "reference": "planning/inbox/screenshots/sketch.png"}],
            },
        )
        data = response.get_json()

        self.assertEqual(response.status_code, 201)
        self.assertTrue(data["success"])
        record_mission.assert_called_once()
        mission_arg = record_mission.call_args.args[0]
        self.assertEqual(mission_arg["title"], "Build mission vault")
        self.assertEqual(mission_arg["desired_outcome"], "Mission is stored with useful context.")
        self.assertEqual(mission_arg["media_references"][0]["label"], "Sketch")
        self.assertEqual(record_mission.call_args.kwargs["source_context"]["source"], "charlie_dashboard")

    def test_mission_media_sanitizer_preserves_bounded_image_data_urls(self):
        image_reference = "data:image/png;base64," + ("A" * 1024)

        media = _clean_media_reference({
            "label": "Pasted screenshot",
            "reference": image_reference,
            "media_type": "image",
        })

        self.assertEqual(media["label"], "Pasted screenshot")
        self.assertEqual(media["media_type"], "image")
        self.assertEqual(media["reference"], image_reference)

    def test_mission_media_sanitizer_rejects_non_image_data_urls(self):
        media = _clean_media_reference({
            "label": "HTML payload",
            "reference": "data:text/html;base64,PHNjcmlwdD4=",
            "media_type": "image",
        })

        self.assertEqual(media, {})

    @patch("modules.charlie.routes.require_owner_read_access", return_value=None)
    @patch("modules.charlie.routes.update_mission_vault")
    def test_dashboard_can_update_mission_vault(self, update_mission_vault, _owner_access):
        update_mission_vault.return_value = ({
            "success": True,
            "status": "ok",
            "mission_id": "MISSION-1",
            "mission_status": "planned",
        }, 200)

        response = self.client.post(
            "/api/charlie/build-relay/missions/MISSION-1/vault",
            json={
                "status": "planned",
                "mission_vault": {"mission_stage": "planned"},
                "agent_workflow": [{"agent": "planner", "status": "complete"}],
            },
        )
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["success"])
        update_mission_vault.assert_called_once()
        self.assertEqual(update_mission_vault.call_args.args[0], "MISSION-1")
        self.assertEqual(update_mission_vault.call_args.kwargs["status"], "planned")

    @patch("modules.charlie.routes.require_owner_read_access", return_value=None)
    @patch("modules.charlie.routes.update_mission_workflow_step")
    def test_dashboard_can_update_workflow_step(self, update_workflow, _owner_access):
        update_workflow.return_value = ({
            "success": True,
            "status": "ok",
            "mission_id": "MISSION-1",
        }, 200)

        response = self.client.post(
            "/api/charlie/build-relay/missions/MISSION-1/workflow",
            json={"agent": "tester", "step_status": "complete", "findings": "Tests passed."},
        )
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["success"])
        update_workflow.assert_called_once()
        self.assertEqual(update_workflow.call_args.kwargs["agent"], "tester")
        self.assertEqual(update_workflow.call_args.kwargs["findings"], "Tests passed.")

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
    @patch("modules.charlie.routes.update_new_mission_intake")
    def test_dashboard_can_patch_new_mission_intake(self, update_intake, _owner_access):
        update_intake.return_value = ({
            "success": True,
            "status": "ok",
            "mission_id": "MISSION-1",
            "mission_status": "new",
            "changed_fields": ["title", "mission_vault.desired_outcome"],
        }, 200)

        response = self.client.patch(
            "/api/charlie/build-relay/missions/MISSION-1",
            json={
                "updates": {
                    "title": "Updated mission",
                    "desired_outcome": "Better intake detail.",
                    "media_references": [
                        {"label": "Extra screenshot", "reference": "data:image/png;base64,ZmFrZQ==", "media_type": "image"},
                    ],
                },
                "comment": "Added before approval.",
            },
        )
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["success"])
        update_intake.assert_called_once()
        self.assertEqual(update_intake.call_args.args[0], "MISSION-1")
        self.assertEqual(update_intake.call_args.kwargs["updates"]["title"], "Updated mission")
        self.assertEqual(update_intake.call_args.kwargs["updates"]["media_references"][0]["label"], "Extra screenshot")
        self.assertEqual(update_intake.call_args.kwargs["comment"], "Added before approval.")

    @patch("modules.charlie.routes.require_owner_read_access", return_value=None)
    @patch("modules.charlie.routes.get_mission_review_packet")
    def test_mission_review_packet_route_returns_stage_8_packet(self, get_review_packet, _owner_access):
        get_review_packet.return_value = ({
            "success": True,
            "status": "ok",
            "mission_id": "MISSION-1",
            "review_packet": {
                "summary": "Ready for owner review.",
                "can_approve_final_release": True,
                "execution_boundary": "Dashboard review decisions update mission state only.",
            },
        }, 200)

        response = self.client.get("/api/charlie/build-relay/missions/MISSION-1/review")
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["success"])
        self.assertTrue(data["review_packet"]["can_approve_final_release"])
        self.assertIn("Dashboard review decisions", data["review_packet"]["execution_boundary"])
        get_review_packet.assert_called_once_with("MISSION-1")

    @patch("modules.charlie.routes.require_owner_read_access", return_value=None)
    @patch("modules.charlie.routes.record_mission_review_decision")
    def test_mission_review_decision_route_records_owner_gate_decision(self, record_review_decision, _owner_access):
        record_review_decision.return_value = ({
            "success": True,
            "status": "ok",
            "mission_id": "MISSION-1",
            "mission_status": "approved",
            "review_decision": "send_back",
        }, 200)

        response = self.client.post(
            "/api/charlie/build-relay/missions/MISSION-1/review",
            json={"decision": "send_back", "comments": "Fix test evidence.", "target_stage": "tester"},
        )
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["success"])
        self.assertEqual(data["review_decision"], "send_back")
        record_review_decision.assert_called_once_with(
            "MISSION-1",
            decision="send_back",
            comments="Fix test evidence.",
            target_stage="tester",
        )

    @patch("modules.charlie.routes.require_owner_read_access", return_value=None)
    @patch("modules.charlie.routes.record_mission_review_decision")
    def test_mission_review_decision_route_records_done_without_local_cleanup(self, record_review_decision, _owner_access):
        record_review_decision.return_value = ({
            "success": True,
            "status": "ok",
            "mission_id": "MISSION-1",
            "mission_status": "done",
            "review_decision": "mark_done",
        }, 200)

        response = self.client.post(
            "/api/charlie/build-relay/missions/MISSION-1/review",
            json={"decision": "mark_done", "comments": "No release needed."},
        )
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["success"])
        self.assertNotIn("visual_review_cleanup", data)

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

    @patch("modules.charlie.routes.require_owner_read_access", return_value=None)
    @patch("modules.charlie.routes.update_mission_queue_priority")
    def test_mission_queue_route_updates_priority(self, update_queue_priority, _owner_access):
        update_queue_priority.return_value = ({
            "success": True,
            "status": "ok",
            "mission_id": "MISSION-1",
            "queue_priority": 15,
        }, 200)

        response = self.client.post(
            "/api/charlie/build-relay/missions/MISSION-1/queue",
            json={"priority": 15, "notes": "Move this up."},
        )
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["success"])
        self.assertEqual(data["queue_priority"], 15)
        update_queue_priority.assert_called_once_with(
            "MISSION-1",
            priority=15,
            notes="Move this up.",
        )

    @patch("modules.charlie.routes.require_owner_read_access", return_value=None)
    @patch("modules.charlie.routes.local_runner_status")
    @patch("modules.charlie.routes.list_missions")
    def test_runner_status_route_reports_approved_waiting_pickup(self, list_missions, local_runner_status, _owner_access):
        local_runner_status.return_value = {"active": False, "status": "runner_not_started"}

        def fake_list_missions(status="", limit=10):
            if status == "approved":
                return ({
                    "success": True,
                    "status": "ok",
                    "missions": [{
                        "mission_id": "CHARLIE-MISSION-WAITING",
                        "title": "Waiting mission",
                        "status": "approved",
                    }],
                }, 200)
            return {"success": True, "status": "ok", "missions": []}, 200

        list_missions.side_effect = fake_list_missions

        response = self.client.get("/api/charlie/build-relay/runner/status")
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["success"])
        self.assertEqual(data["status"], "approved_waiting_for_local_runner")
        self.assertEqual(data["next_approved_mission"]["mission_id"], "CHARLIE-MISSION-WAITING")
        self.assertEqual(data["approved_queue"][0]["mission_id"], "CHARLIE-MISSION-WAITING")
        self.assertEqual(data["local_runner"]["status"], "runner_not_started")
        self.assertIn("charlie_runner_control.py start", data["local_runner_control_commands"]["start"])
        self.assertFalse(data["can_run_shell_from_web"])
        local_runner_status.assert_called_once()

    @patch("modules.charlie.routes.require_owner_read_access", return_value=None)
    @patch("modules.charlie.routes.local_runner_status")
    @patch("modules.charlie.routes.list_missions")
    def test_runner_status_route_reports_active_mission(self, list_missions, local_runner_status, _owner_access):
        local_runner_status.return_value = {"active": True, "status": "runner_active"}

        def fake_list_missions(status="", limit=10):
            if status == "in_progress":
                return ({
                    "success": True,
                    "status": "ok",
                    "missions": [{
                        "mission_id": "CHARLIE-MISSION-ACTIVE",
                        "title": "Active mission",
                        "status": "in_progress",
                    }],
                }, 200)
            return {"success": True, "status": "ok", "missions": []}, 200

        list_missions.side_effect = fake_list_missions

        response = self.client.get("/api/charlie/build-relay/runner/status")
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(data["status"], "active_mission_in_progress")
        self.assertEqual(data["active_mission"]["mission_id"], "CHARLIE-MISSION-ACTIVE")
        self.assertTrue(data["local_runner"]["active"])
        local_runner_status.assert_called_once()

    @patch("modules.charlie.routes.require_owner_read_access", return_value=None)
    @patch("modules.charlie.routes.local_runner_status")
    @patch("modules.charlie.routes.list_missions")
    def test_runner_status_route_reports_release_approved_separately(self, list_missions, local_runner_status, _owner_access):
        local_runner_status.return_value = {"active": True, "status": "runner_active"}

        def fake_list_missions(status="", limit=10):
            if status == "release_approved":
                return ({
                    "success": True,
                    "status": "ok",
                    "missions": [{
                        "mission_id": "CHARLIE-MISSION-RELEASE",
                        "title": "Release mission",
                        "status": "release_approved",
                    }],
                }, 200)
            return {"success": True, "status": "ok", "missions": []}, 200

        list_missions.side_effect = fake_list_missions

        response = self.client.get("/api/charlie/build-relay/runner/status")
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["success"])
        self.assertEqual(data["status"], "release_approved_waiting_for_local_release_bridge")
        self.assertIsNone(data["next_approved_mission"])
        self.assertEqual(data["next_release_approved_mission"]["mission_id"], "CHARLIE-MISSION-RELEASE")
        self.assertIn("release bridge", data["next_action"])

    @patch.dict(os.environ, {"RENDER": "true"})
    @patch("modules.charlie.routes.require_owner_read_access", return_value=None)
    @patch("modules.charlie.routes.local_runner_status")
    @patch("modules.charlie.routes.list_missions")
    def test_runner_status_route_explains_render_cannot_see_laptop_runner(self, list_missions, local_runner_status, _owner_access):
        local_runner_status.return_value = {"active": False, "status": "runner_not_started"}
        list_missions.return_value = ({"success": True, "status": "ok", "missions": []}, 200)

        response = self.client.get("/api/charlie/build-relay/runner/status")
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(data["local_runner_scope"], "render_cannot_see_laptop_runner")
        self.assertIn("Render cannot see", data["local_runner_visibility_note"])

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
