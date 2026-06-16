from io import BytesIO
import os
import unittest
from unittest.mock import patch

from app import app
from modules.oom_sakkie.access import is_review_request_allowed
from modules.oom_sakkie.telegram_direct import _reset_direct_auth_rate_limit_for_tests
from modules.oom_sakkie.telegram_gateway import _reset_auth_rate_limit_for_tests


TELEGRAM_TEST_TOKEN = "test-telegram-token-32-chars-minimum"
TELEGRAM_DIRECT_SECRET = "test-telegram-direct-secret-32-chars"
TELEGRAM_BOT_TOKEN = "1234567890:test-bot-token-for-unit-tests"


def _fake_farm_attention_tool():
    tool = unittest.mock.Mock()
    tool.name = "farm_attention_summary"
    tool.risk_level = 0
    tool.handler.return_value = {
        "success": True,
        "status": "ok",
        "summary": "No current farm attention items are showing.",
        "links": [],
        "stale_warnings": [],
        "safety_notes": [],
        "raw": {},
    }
    return tool


class OomSakkieRouteTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        _reset_auth_rate_limit_for_tests()
        _reset_direct_auth_rate_limit_for_tests()

    @patch.dict(os.environ, {}, clear=True)
    @patch("modules.oom_sakkie.service.write_trace", return_value={"stored": False, "status": "not_configured"})
    def test_message_route_returns_shape_without_database(self, _write_trace):
        response = self.client.post("/api/oom-sakkie/message", json={
            "text": "what is the power doing now",
            "channel": "kiosk",
            "session_id": "route-test-session",
        })
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["success"])
        self.assertEqual(data["tool_used"], "power_current")
        self.assertEqual(data["risk_level"], 0)
        self.assertFalse(data["needs_clarification"])
        self.assertIn("answer", data)
        self.assertIn("trace_id", data)
        self.assertIn("links", data)
        self.assertIn("stale_warnings", data)
        self.assertIn("safety_notes", data)
        self.assertEqual(data["trace_store"]["status"], "not_configured")

    @patch.dict(os.environ, {}, clear=True)
    def test_policy_route_returns_local_read_only_shape(self):
        response = self.client.get("/api/oom-sakkie/policy")
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["success"])
        self.assertEqual(data["mode"], "local_kiosk_read_only")
        self.assertEqual(data["kiosk_policy"]["max_risk_level"], 1)
        self.assertEqual(data["kiosk_policy"]["allowed_risk_label"], "DRAFT_ONLY")
        self.assertEqual(data["tool_counts"]["write_or_confirmation"], 0)
        self.assertEqual(data["continue_conversation_max_turns"], 5)
        self.assertEqual(data["voice_auto_send_ms"], 2000)
        self.assertFalse(data["backend_voice_stt"]["enabled"])
        self.assertFalse(data["backend_voice_stt"]["stores_audio"])
        self.assertIn("backend STT vendors", data["blocked_capabilities"])
        self.assertFalse(data["telegram_gateway_enabled"])
        self.assertFalse(data["telegram_gateway"]["sends_telegram"])
        self.assertFalse(data["telegram_direct_enabled"])
        self.assertFalse(data["telegram_direct"]["sends_telegram"])
        self.assertIn("Telegram read-only gateway", data["blocked_capabilities"])
        self.assertIn("Telegram direct owner bot", data["blocked_capabilities"])
        self.assertEqual(data["message_endpoint_access"]["default"], "reachable_wherever_flask_is_reachable")
        self.assertIn("reverse_proxy_caveat", data["review_endpoints_access"])

    @patch.dict(os.environ, {"OOM_SAKKIE_STT_ENABLED": "1", "OPENAI_API_KEY": "test-key"}, clear=True)
    def test_policy_route_reports_push_to_talk_backend_stt_when_configured(self):
        response = self.client.get("/api/oom-sakkie/policy")
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["backend_voice_vendors_enabled"])
        self.assertTrue(data["backend_voice_stt"]["enabled"])
        self.assertEqual(data["backend_voice_stt"]["mode"], "push_to_talk_backend_stt_fallback")
        self.assertFalse(data["backend_voice_stt"]["stores_audio"])
        self.assertFalse(data["always_on_mic_enabled"])
        self.assertEqual(data["browser_speech_mode"], "push_to_talk_with_backend_stt_fallback")

    @patch("modules.oom_sakkie.routes.transcribe_oom_sakkie_voice_audio")
    def test_voice_transcribe_route_is_review_gated_and_returns_false_flags(self, transcribe):
        transcribe.return_value = ({
            "success": True,
            "status": "transcribed",
            "text": "show me the safety gates",
            "always_on_mic_enabled": False,
            "stores_audio": False,
            "writes": False,
            "dispatch_enabled": False,
            "changes_runtime_now": False,
            "changes_prompt_now": False,
        }, 200)

        response = self.client.post(
            "/api/oom-sakkie/voice/transcribe",
            data={"audio": (BytesIO(b"fake-webm"), "voice.webm")},
            content_type="multipart/form-data",
        )
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["success"])
        self.assertEqual(data["text"], "show me the safety gates")
        self.assertFalse(data["always_on_mic_enabled"])
        self.assertFalse(data["stores_audio"])
        self.assertFalse(data["writes"])
        self.assertFalse(data["dispatch_enabled"])
        self.assertFalse(data["changes_runtime_now"])
        self.assertFalse(data["changes_prompt_now"])
        transcribe.assert_called_once()

        denied = self.client.post(
            "/api/oom-sakkie/voice/transcribe",
            data={"audio": (BytesIO(b"fake-webm"), "voice.webm")},
            content_type="multipart/form-data",
            environ_base={"REMOTE_ADDR": "203.0.113.10"},
        )
        denied_data = denied.get_json()

        self.assertEqual(denied.status_code, 403)
        self.assertEqual(denied_data["status"], "review_access_denied")

    @patch.dict(os.environ, {
        "OOM_SAKKIE_TELEGRAM_DIRECT_ENABLED": "1",
        "OOM_SAKKIE_TELEGRAM_DIRECT_SEND_ENABLED": "1",
        "OOM_SAKKIE_TELEGRAM_BOT_TOKEN": TELEGRAM_BOT_TOKEN,
        "OOM_SAKKIE_TELEGRAM_WEBHOOK_SECRET": TELEGRAM_DIRECT_SECRET,
        "OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS": "12345",
    }, clear=True)
    def test_telegram_direct_parity_route_is_review_gated(self):
        response = self.client.get("/api/oom-sakkie/channels/telegram/direct-parity")
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["success"])
        self.assertTrue(data["backend_owns_oom_sakkie_chat"])
        self.assertFalse(data["n8n_required_for_oom_sakkie_chat"])
        self.assertIn("farm attention", data["carried_over_backend_capabilities"])
        self.assertIn("Telegram voice-note transcription", data["not_carried_over_yet"])
        self.assertFalse(data["can_trigger_outbound_llm"])
        self.assertFalse(data["writes"])
        self.assertFalse(data["dispatch_enabled"])

        denied = self.client.get(
            "/api/oom-sakkie/channels/telegram/direct-parity",
            environ_base={"REMOTE_ADDR": "203.0.113.10"},
        )
        denied_data = denied.get_json()

        self.assertEqual(denied.status_code, 403)
        self.assertFalse(denied_data["success"])
        self.assertEqual(denied_data["status"], "review_access_denied")

    @patch.dict(os.environ, {}, clear=True)
    def test_telegram_gateway_route_is_disabled_by_default(self):
        response = self.client.post(
            "/api/oom-sakkie/channels/telegram/message",
            json={"text": "what needs attention today"},
            environ_base={"REMOTE_ADDR": "203.0.113.10"},
        )
        data = response.get_json()

        self.assertEqual(response.status_code, 503)
        self.assertFalse(data["success"])
        self.assertEqual(data["status"], "telegram_gateway_disabled")
        self.assertFalse(data["sends_telegram"])
        self.assertFalse(data["writes"])

    @patch.dict(os.environ, {
        "OOM_SAKKIE_TELEGRAM_GATEWAY_ENABLED": "1",
        "OOM_SAKKIE_TELEGRAM_GATEWAY_TOKEN": TELEGRAM_TEST_TOKEN,
        "OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS": "12345",
    }, clear=True)
    def test_telegram_gateway_route_requires_token(self):
        response = self.client.post(
            "/api/oom-sakkie/channels/telegram/message",
            json={"text": "what needs attention today"},
            environ_base={"REMOTE_ADDR": "203.0.113.10"},
        )
        data = response.get_json()

        self.assertEqual(response.status_code, 403)
        self.assertFalse(data["success"])
        self.assertEqual(data["status"], "telegram_gateway_auth_denied")

    @patch.dict(os.environ, {
        "OOM_SAKKIE_TELEGRAM_GATEWAY_ENABLED": "1",
        "OOM_SAKKIE_TELEGRAM_GATEWAY_TOKEN": "short-token",
        "OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS": "12345",
    }, clear=True)
    def test_telegram_gateway_route_rejects_short_token_configuration(self):
        response = self.client.post(
            "/api/oom-sakkie/channels/telegram/message",
            json={"text": "what needs attention today", "telegram_user_id": "12345"},
            headers={"Authorization": "Bearer short-token"},
            environ_base={"REMOTE_ADDR": "203.0.113.10"},
        )
        data = response.get_json()

        self.assertEqual(response.status_code, 503)
        self.assertFalse(data["success"])
        self.assertEqual(data["status"], "telegram_gateway_token_too_short")
        self.assertFalse(data["telegram_gateway"]["enabled"])

    @patch.dict(os.environ, {
        "OOM_SAKKIE_TELEGRAM_GATEWAY_ENABLED": "1",
        "OOM_SAKKIE_TELEGRAM_GATEWAY_TOKEN": TELEGRAM_TEST_TOKEN,
    }, clear=True)
    def test_telegram_gateway_route_requires_allowed_user_list(self):
        response = self.client.post(
            "/api/oom-sakkie/channels/telegram/message",
            json={"text": "what needs attention today", "telegram_user_id": "12345"},
            headers={"Authorization": f"Bearer {TELEGRAM_TEST_TOKEN}"},
            environ_base={"REMOTE_ADDR": "203.0.113.10"},
        )
        data = response.get_json()

        self.assertEqual(response.status_code, 503)
        self.assertFalse(data["success"])
        self.assertEqual(data["status"], "telegram_gateway_allowed_user_ids_required")
        self.assertFalse(data["telegram_gateway"]["enabled"])

    @patch.dict(os.environ, {
        "OOM_SAKKIE_TELEGRAM_GATEWAY_ENABLED": "1",
        "OOM_SAKKIE_TELEGRAM_GATEWAY_TOKEN": TELEGRAM_TEST_TOKEN,
        "OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS": "12345",
    }, clear=True)
    @patch("modules.oom_sakkie.telegram_gateway.handle_message")
    def test_telegram_gateway_route_returns_read_only_reply_payload(self, mock_handle):
        mock_handle.return_value = ({
            "success": True,
            "answer": "Read-only answer.",
            "tool_used": "farm_attention_summary",
            "risk_level": 0,
            "trace_id": "OSK-TRACE-ROUTE",
            "safety_notes": ["No write."],
        }, 200)

        response = self.client.post(
            "/api/oom-sakkie/channels/telegram/message",
            json={
                "message": {
                    "text": "what needs attention today",
                    "from": {"id": 12345},
                    "chat": {"id": 67890},
                },
            },
            headers={"Authorization": f"Bearer {TELEGRAM_TEST_TOKEN}"},
            environ_base={"REMOTE_ADDR": "203.0.113.10"},
        )
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["success"])
        self.assertEqual(data["answer"], "Read-only answer.")
        self.assertEqual(data["reply"]["chat_id"], "67890")
        self.assertFalse(data["reply"]["sends_telegram"])
        self.assertFalse(data["sends_telegram"])
        self.assertFalse(data["writes"])
        self.assertTrue(data["records_audit_trace"])
        self.assertFalse(data["dispatch_enabled"])
        mock_handle.assert_called_once_with({
            "text": "what needs attention today",
            "channel": "telegram_read_only",
            "session_id": "telegram-67890",
        })

    @patch.dict(os.environ, {
        "OOM_SAKKIE_TELEGRAM_GATEWAY_ENABLED": "1",
        "OOM_SAKKIE_TELEGRAM_GATEWAY_TOKEN": TELEGRAM_TEST_TOKEN,
        "OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS": "12345",
        "OOM_SAKKIE_LLM_ROUTER_ENABLED": "1",
        "OOM_SAKKIE_LLM_ROUTER_MODEL": "test-router",
        "OOM_SAKKIE_LLM_ANSWER_ENABLED": "1",
        "OOM_SAKKIE_LLM_ANSWER_MODEL": "test-answer",
        "OPENAI_API_KEY": "test-key",
    }, clear=True)
    @patch("modules.oom_sakkie.service.compose_answer_with_llm")
    @patch("modules.oom_sakkie.service.route_with_llm")
    @patch("modules.oom_sakkie.service.get_tool")
    @patch("modules.oom_sakkie.service.write_trace", return_value={"stored": False, "status": "test"})
    def test_telegram_gateway_route_suppresses_llm_egress_when_llm_enabled(self, _write_trace, mock_get_tool, mock_route, mock_compose):
        mock_get_tool.return_value = _fake_farm_attention_tool()

        response = self.client.post(
            "/api/oom-sakkie/channels/telegram/message",
            json={
                "message": {
                    "text": "what needs attention today",
                    "from": {"id": 12345},
                    "chat": {"id": 67890},
                },
            },
            headers={"X-Oom-Sakkie-Telegram-Token": TELEGRAM_TEST_TOKEN},
            environ_base={"REMOTE_ADDR": "203.0.113.10"},
        )
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["success"])
        self.assertFalse(data["can_trigger_outbound_llm"])
        self.assertFalse(data["message"]["pipeline"]["llm_router_used"])
        self.assertFalse(data["message"]["pipeline"]["llm_answer_used"])
        self.assertEqual(data["message"]["pipeline"]["answer_source"], "deterministic")
        mock_get_tool.assert_called_once_with("farm_attention_summary")
        mock_route.assert_not_called()
        mock_compose.assert_not_called()

    @patch.dict(os.environ, {
        "OOM_SAKKIE_TELEGRAM_GATEWAY_ENABLED": "1",
        "OOM_SAKKIE_TELEGRAM_GATEWAY_TOKEN": TELEGRAM_TEST_TOKEN,
        "OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS": "12345",
    }, clear=True)
    def test_telegram_gateway_exposure_preflight_route_is_review_gated(self):
        response = self.client.get("/api/oom-sakkie/channels/telegram/exposure-preflight")
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["success"])
        self.assertEqual(data["status"], "private_test_ready_manual_public_checks_pending")
        self.assertTrue(data["private_test_ready"])
        self.assertFalse(data["public_exposure_ready"])
        self.assertFalse(data["sends_telegram"])
        self.assertFalse(data["direct_bot_cutover_enabled"])
        self.assertFalse(data["can_trigger_outbound_llm"])
        self.assertFalse(data["writes"])
        self.assertTrue(data["records_audit_trace"])

        denied = self.client.get(
            "/api/oom-sakkie/channels/telegram/exposure-preflight",
            environ_base={"REMOTE_ADDR": "203.0.113.10"},
        )
        denied_data = denied.get_json()

        self.assertEqual(denied.status_code, 403)
        self.assertFalse(denied_data["success"])
        self.assertEqual(denied_data["status"], "review_access_denied")

    @patch.dict(os.environ, {}, clear=True)
    def test_telegram_direct_route_is_disabled_by_default(self):
        response = self.client.post(
            "/api/oom-sakkie/channels/telegram/direct-webhook",
            json={"text": "what needs attention today"},
            environ_base={"REMOTE_ADDR": "203.0.113.10"},
        )
        data = response.get_json()

        self.assertEqual(response.status_code, 503)
        self.assertFalse(data["success"])
        self.assertEqual(data["status"], "telegram_direct_disabled")
        self.assertFalse(data["sends_telegram"])
        self.assertFalse(data["writes"])

    @patch.dict(os.environ, {
        "OOM_SAKKIE_TELEGRAM_DIRECT_ENABLED": "1",
        "OOM_SAKKIE_TELEGRAM_DIRECT_SEND_ENABLED": "1",
        "OOM_SAKKIE_TELEGRAM_BOT_TOKEN": TELEGRAM_BOT_TOKEN,
        "OOM_SAKKIE_TELEGRAM_WEBHOOK_SECRET": TELEGRAM_DIRECT_SECRET,
        "OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS": "12345",
    }, clear=True)
    def test_telegram_direct_route_requires_webhook_secret_header(self):
        response = self.client.post(
            "/api/oom-sakkie/channels/telegram/direct-webhook",
            json={"text": "what needs attention today", "telegram_user_id": "12345"},
            environ_base={"REMOTE_ADDR": "203.0.113.10"},
        )
        data = response.get_json()

        self.assertEqual(response.status_code, 403)
        self.assertFalse(data["success"])
        self.assertEqual(data["status"], "telegram_direct_auth_denied")
        self.assertFalse(data["sends_telegram"])

    @patch.dict(os.environ, {
        "OOM_SAKKIE_TELEGRAM_DIRECT_ENABLED": "1",
        "OOM_SAKKIE_TELEGRAM_DIRECT_SEND_ENABLED": "1",
        "OOM_SAKKIE_TELEGRAM_BOT_TOKEN": TELEGRAM_BOT_TOKEN,
        "OOM_SAKKIE_TELEGRAM_WEBHOOK_SECRET": TELEGRAM_DIRECT_SECRET,
        "OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS": "12345",
    }, clear=True)
    @patch("modules.oom_sakkie.telegram_direct.send_owner_telegram_reply")
    @patch("modules.oom_sakkie.telegram_direct.handle_message")
    def test_telegram_direct_route_sends_owner_reply_without_write_authority(self, mock_handle, mock_send):
        mock_handle.return_value = ({
            "success": True,
            "answer": "Read-only answer.",
            "tool_used": "farm_attention_summary",
            "risk_level": 0,
            "trace_id": "OSK-TRACE-DIRECT-ROUTE",
            "safety_notes": ["No write."],
        }, 200)
        mock_send.return_value = ({
            "success": True,
            "status": "telegram_sent",
            "sends_telegram": True,
            "writes": False,
            "dispatch_enabled": False,
        }, 200)

        response = self.client.post(
            "/api/oom-sakkie/channels/telegram/direct-webhook",
            json={
                "message": {
                    "text": "what needs attention today",
                    "from": {"id": 12345},
                    "chat": {"id": 67890},
                },
            },
            headers={"X-Telegram-Bot-Api-Secret-Token": TELEGRAM_DIRECT_SECRET},
            environ_base={"REMOTE_ADDR": "203.0.113.10"},
        )
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["success"])
        self.assertEqual(data["status"], "telegram_sent")
        self.assertTrue(data["sends_telegram"])
        self.assertFalse(data["writes"])
        self.assertFalse(data["dispatch_enabled"])
        self.assertFalse(data["can_trigger_outbound_llm"])
        self.assertEqual(data["answer"], "Read-only answer.")
        self.assertIn("Oom Sakkie", data["telegram_text"])
        self.assertIn("Read-only answer.", data["telegram_text"])
        mock_handle.assert_called_once_with({
            "text": "what needs attention today",
            "channel": "telegram_read_only",
            "session_id": "telegram-67890",
        })
        mock_send.assert_called_once()

    @patch.dict(os.environ, {
        "OOM_SAKKIE_TELEGRAM_DIRECT_ENABLED": "1",
        "OOM_SAKKIE_TELEGRAM_DIRECT_SEND_ENABLED": "1",
        "OOM_SAKKIE_TELEGRAM_BOT_TOKEN": TELEGRAM_BOT_TOKEN,
        "OOM_SAKKIE_TELEGRAM_WEBHOOK_SECRET": TELEGRAM_DIRECT_SECRET,
        "OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS": "12345",
    }, clear=True)
    @patch("modules.oom_sakkie.telegram_direct.send_owner_telegram_reply")
    @patch("modules.oom_sakkie.telegram_direct.handle_message")
    def test_telegram_direct_route_help_menu_is_local_and_formatted(self, mock_handle, mock_send):
        mock_send.return_value = ({"success": True, "status": "telegram_sent", "sends_telegram": True}, 200)

        response = self.client.post(
            "/api/oom-sakkie/channels/telegram/direct-webhook",
            json={
                "message": {
                    "text": "/start",
                    "from": {"id": 12345},
                    "chat": {"id": 67890},
                },
            },
            headers={"X-Telegram-Bot-Api-Secret-Token": TELEGRAM_DIRECT_SECRET},
            environ_base={"REMOTE_ADDR": "203.0.113.10"},
        )
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["success"])
        self.assertIn("/brief", data["telegram_text"])
        self.assertIn("/attention", data["telegram_text"])
        self.assertFalse(data["can_trigger_outbound_llm"])
        self.assertFalse(data["writes"])
        mock_handle.assert_not_called()
        mock_send.assert_called_once()

    def test_review_packet_denies_non_local_review_access(self):
        response = self.client.get(
            "/api/oom-sakkie/review-packet",
            environ_base={"REMOTE_ADDR": "203.0.113.10"},
        )
        data = response.get_json()

        self.assertEqual(response.status_code, 403)
        self.assertFalse(data["success"])
        self.assertEqual(data["status"], "review_access_denied")

    def test_specialists_route_is_planned_only(self):
        response = self.client.get("/api/oom-sakkie/specialists")
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["success"])
        self.assertEqual(data["status"], "planned_only")
        self.assertFalse(data["delegation_enabled"])
        self.assertFalse(data["autonomous_loops_enabled"])
        self.assertGreaterEqual(len(data["specialists"]), 8)

    def test_specialists_route_denies_non_local_review_access(self):
        response = self.client.get(
            "/api/oom-sakkie/specialists",
            environ_base={"REMOTE_ADDR": "203.0.113.10"},
        )
        data = response.get_json()

        self.assertEqual(response.status_code, 403)
        self.assertEqual(data["status"], "review_access_denied")

    def test_agents_route_is_foundation_only(self):
        response = self.client.get("/api/oom-sakkie/agents")
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["success"])
        self.assertEqual(data["mode"], "advisory_runtime_foundation")
        self.assertFalse(data["runtime_enabled"])
        self.assertFalse(data["dispatch_enabled"])
        self.assertFalse(data["autonomous_loops_enabled"])
        self.assertGreaterEqual(data["agent_count"], 8)
        ledger = next(item for item in data["agents"] if item["slug"] == "ledger")
        self.assertIn("business_growth_brief", ledger["allowed_tools"])
        self.assertIn("ledger_sales_agent", ledger["allowed_tools"])
        self.assertIn("sales_campaign_status", ledger["allowed_tools"])
        self.assertIn("sales_outreach_draft_queue", ledger["allowed_tools"])
        self.assertIn("sales_send_design_status", ledger["allowed_tools"])
        self.assertIn("sales_lead_tracking_status", ledger["allowed_tools"])

    @patch("modules.oom_sakkie.routes.list_sales_campaigns")
    def test_sales_campaigns_route_lists_owner_review_queue(self, mock_list):
        mock_list.return_value = ({
            "success": True,
            "status": "ok",
            "mode": "owner_review_sales_campaign_queue",
            "sales_campaigns": [],
            "sends_customer_message": False,
            "creates_order": False,
            "changes_stock": False,
        }, 200)

        response = self.client.get("/api/oom-sakkie/sales-campaigns?limit=5")
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["success"])
        self.assertEqual(data["mode"], "owner_review_sales_campaign_queue")
        self.assertFalse(data["sends_customer_message"])
        self.assertFalse(data["creates_order"])
        self.assertFalse(data["changes_stock"])
        mock_list.assert_called_once_with(limit="5")

    @patch("modules.oom_sakkie.routes.list_sales_leads")
    def test_sales_lead_route_accepts_launch_test_filter(self, mock_list):
        mock_list.return_value = ({
            "success": True,
            "status": "ok",
            "mode": "sales_lead_tracking_queue",
            "filter": "launch_test",
            "sales_leads": [],
            "counts": {"launch_test_open": 0},
            "sends_customer_message": False,
            "calls_chatwoot": False,
            "calls_n8n": False,
            "creates_order": False,
            "changes_stock": False,
        }, 200)

        response = self.client.get("/api/oom-sakkie/sales-leads?limit=5&status=launch_test")
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["success"])
        self.assertEqual(data["filter"], "launch_test")
        self.assertFalse(data["sends_customer_message"])
        self.assertFalse(data["calls_chatwoot"])
        self.assertFalse(data["creates_order"])
        mock_list.assert_called_once_with(limit="5", status_filter="launch_test")

    @patch("modules.oom_sakkie.routes.record_sales_campaign")
    def test_sales_campaigns_route_records_campaign_without_customer_send(self, mock_record):
        mock_record.return_value = ({
            "success": True,
            "status": "ok",
            "campaign_id": "OSK-SALES-CAMPAIGN-TEST",
            "records_sales_campaign": True,
            "sends_customer_message": False,
            "creates_order": False,
            "changes_stock": False,
        }, 201)

        response = self.client.post("/api/oom-sakkie/sales-campaigns", json={"campaign_title": "Ready meat"})
        data = response.get_json()

        self.assertEqual(response.status_code, 201)
        self.assertTrue(data["success"])
        self.assertEqual(data["campaign_id"], "OSK-SALES-CAMPAIGN-TEST")
        self.assertFalse(data["sends_customer_message"])
        self.assertFalse(data["creates_order"])
        self.assertFalse(data["changes_stock"])
        mock_record.assert_called_once()

    @patch("modules.oom_sakkie.routes.record_sales_campaign_event")
    def test_sales_campaign_event_route_records_append_only_review_event(self, mock_record):
        mock_record.return_value = ({
            "success": True,
            "status": "ok",
            "event_id": "OSK-SALES-CAMPAIGN-EVENT-TEST",
            "event_type": "review_note",
            "sends_customer_message": False,
            "creates_order": False,
            "changes_stock": False,
        }, 201)

        response = self.client.post(
            "/api/oom-sakkie/sales-campaigns/OSK-SALES-CAMPAIGN-TEST/events",
            json={"event_type": "review_note", "notes": "Looks useful."},
        )
        data = response.get_json()

        self.assertEqual(response.status_code, 201)
        self.assertTrue(data["success"])
        self.assertEqual(data["event_type"], "review_note")
        self.assertFalse(data["sends_customer_message"])
        self.assertFalse(data["creates_order"])
        self.assertFalse(data["changes_stock"])
        mock_record.assert_called_once()

    @patch("modules.oom_sakkie.routes.record_sales_outreach_draft_from_campaign")
    def test_sales_campaign_outreach_draft_route_records_internal_draft_only(self, mock_record):
        mock_record.return_value = ({
            "success": True,
            "status": "ok",
            "draft_id": "OSK-SALES-DRAFT-TEST",
            "campaign_id": "OSK-SALES-CAMPAIGN-TEST",
            "records_customer_outreach_draft": True,
            "sends_customer_message": False,
            "creates_order": False,
            "changes_stock": False,
        }, 201)

        response = self.client.post(
            "/api/oom-sakkie/sales-campaigns/OSK-SALES-CAMPAIGN-TEST/outreach-drafts",
            json={"audience_label": "known meat buyers"},
        )
        data = response.get_json()

        self.assertEqual(response.status_code, 201)
        self.assertTrue(data["success"])
        self.assertEqual(data["draft_id"], "OSK-SALES-DRAFT-TEST")
        self.assertFalse(data["sends_customer_message"])
        self.assertFalse(data["creates_order"])
        self.assertFalse(data["changes_stock"])
        mock_record.assert_called_once()

    @patch("modules.oom_sakkie.routes.list_sales_outreach_drafts")
    def test_sales_outreach_drafts_route_lists_owner_review_queue(self, mock_list):
        mock_list.return_value = ({
            "success": True,
            "status": "ok",
            "mode": "owner_review_customer_outreach_draft_queue",
            "outreach_drafts": [],
            "sends_customer_message": False,
            "creates_order": False,
            "changes_stock": False,
        }, 200)

        response = self.client.get("/api/oom-sakkie/sales-outreach-drafts?limit=5")
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["success"])
        self.assertEqual(data["mode"], "owner_review_customer_outreach_draft_queue")
        self.assertFalse(data["sends_customer_message"])
        self.assertFalse(data["creates_order"])
        self.assertFalse(data["changes_stock"])
        mock_list.assert_called_once_with(limit="5")

    @patch("modules.oom_sakkie.routes.record_sales_send_design_request_from_draft")
    def test_sales_send_design_route_records_review_design_only(self, mock_record):
        mock_record.return_value = ({
            "success": True,
            "status": "ok",
            "mode": "customer_send_design_request_queue",
            "send_design_id": "OSK-SALES-SEND-DESIGN-TEST",
            "draft_id": "OSK-SALES-DRAFT-TEST",
            "records_send_design_request": True,
            "sends_customer_message": False,
            "calls_chatwoot": False,
            "calls_n8n": False,
            "creates_order": False,
            "changes_stock": False,
        }, 201)

        response = self.client.post(
            "/api/oom-sakkie/sales-outreach-drafts/OSK-SALES-DRAFT-TEST/send-design-requests",
            json={"target_transport": "sam_chatwoot_whatsapp_review"},
        )
        data = response.get_json()

        self.assertEqual(response.status_code, 201)
        self.assertTrue(data["success"])
        self.assertEqual(data["send_design_id"], "OSK-SALES-SEND-DESIGN-TEST")
        self.assertFalse(data["sends_customer_message"])
        self.assertFalse(data["calls_chatwoot"])
        self.assertFalse(data["calls_n8n"])
        self.assertFalse(data["creates_order"])
        self.assertFalse(data["changes_stock"])
        mock_record.assert_called_once()

    @patch("modules.oom_sakkie.routes.list_sales_send_design_requests")
    def test_sales_send_design_route_lists_review_queue(self, mock_list):
        mock_list.return_value = ({
            "success": True,
            "status": "ok",
            "mode": "customer_send_design_request_queue",
            "send_design_requests": [],
            "sends_customer_message": False,
            "calls_chatwoot": False,
            "calls_n8n": False,
            "creates_order": False,
            "changes_stock": False,
        }, 200)

        response = self.client.get("/api/oom-sakkie/sales-send-design-requests?limit=5")
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["success"])
        self.assertEqual(data["mode"], "customer_send_design_request_queue")
        self.assertFalse(data["sends_customer_message"])
        self.assertFalse(data["calls_chatwoot"])
        self.assertFalse(data["calls_n8n"])
        self.assertFalse(data["creates_order"])
        self.assertFalse(data["changes_stock"])
        mock_list.assert_called_once_with(limit="5")

    @patch("modules.oom_sakkie.routes.list_sales_send_design_requests")
    def test_sales_send_design_routes_are_review_gated(self, mock_list):
        response = self.client.get(
            "/api/oom-sakkie/sales-send-design-requests",
            environ_base={"REMOTE_ADDR": "203.0.113.10"},
        )
        data = response.get_json()

        self.assertEqual(response.status_code, 403)
        self.assertEqual(data["status"], "review_access_denied")
        mock_list.assert_not_called()

    def test_sales_send_design_create_endpoint_is_post_only(self):
        response = self.client.get(
            "/api/oom-sakkie/sales-outreach-drafts/OSK-SALES-DRAFT-TEST/send-design-requests",
        )

        self.assertEqual(response.status_code, 405)

    @patch("modules.oom_sakkie.routes.record_sales_lead")
    def test_sales_lead_route_records_tracking_only(self, mock_record):
        mock_record.return_value = ({
            "success": True,
            "status": "ok",
            "mode": "sales_lead_tracking_queue",
            "lead_id": "OSK-SALES-LEAD-TEST",
            "records_sales_lead": True,
            "sends_customer_message": False,
            "calls_chatwoot": False,
            "calls_n8n": False,
            "creates_order": False,
            "changes_stock": False,
        }, 201)

        response = self.client.post(
            "/api/oom-sakkie/sales-leads",
            json={
                "lead_label": "Buyer A half carcass",
                "campaign_source": "ready_meat_preorder",
                "whatsapp_window_state": "template_required",
            },
        )
        data = response.get_json()

        self.assertEqual(response.status_code, 201)
        self.assertTrue(data["success"])
        self.assertEqual(data["lead_id"], "OSK-SALES-LEAD-TEST")
        self.assertFalse(data["sends_customer_message"])
        self.assertFalse(data["calls_chatwoot"])
        self.assertFalse(data["calls_n8n"])
        self.assertFalse(data["creates_order"])
        self.assertFalse(data["changes_stock"])
        mock_record.assert_called_once()

    @patch("modules.oom_sakkie.routes.record_sam_meat_intake_lead")
    def test_sam_meat_intake_route_records_tracking_only(self, mock_record):
        mock_record.return_value = ({
            "success": True,
            "status": "ok",
            "mode": "sam_meat_intake_tracking_only",
            "lead_id": "OSK-SALES-LEAD-MEAT",
            "contract": {
                "lane": "meat_preorder",
                "missing_before_money_path": ["price_per_kg"],
            },
            "sends_customer_message": False,
            "calls_chatwoot": False,
            "calls_n8n": False,
            "creates_order": False,
            "changes_stock": False,
        }, 201)

        payload = {
            "customer_name": "Jan",
            "conversation_id": "1234",
            "product_type": "half_carcass",
            "cut_set": "Set A",
            "location": "Riversdale",
        }
        response = self.client.post("/api/oom-sakkie/sales-leads/sam-meat-intake", json=payload)
        data = response.get_json()

        self.assertEqual(response.status_code, 201)
        self.assertTrue(data["success"])
        self.assertEqual(data["mode"], "sam_meat_intake_tracking_only")
        self.assertFalse(data["sends_customer_message"])
        self.assertFalse(data["calls_chatwoot"])
        self.assertFalse(data["calls_n8n"])
        self.assertFalse(data["creates_order"])
        self.assertFalse(data["changes_stock"])
        mock_record.assert_called_once_with(payload)

    @patch.dict(os.environ, {}, clear=True)
    @patch("modules.oom_sakkie.routes.record_sam_meat_intake_lead")
    def test_sam_meat_intake_remote_route_is_default_off(self, mock_record):
        response = self.client.post(
            "/api/oom-sakkie/channels/chatwoot/sam-meat-intake",
            json={"customer_name": "Jan", "product_type": "half_carcass", "location": "Riversdale"},
        )
        data = response.get_json()

        self.assertEqual(response.status_code, 503)
        self.assertEqual(data["status"], "sam_meat_intake_remote_disabled")
        self.assertFalse(data["records_tracking_lead"])
        self.assertFalse(data["sends_customer_message"])
        self.assertFalse(data["calls_chatwoot"])
        self.assertFalse(data["calls_n8n"])
        self.assertFalse(data["creates_order"])
        mock_record.assert_not_called()

    @patch.dict(os.environ, {"OOM_SAKKIE_SAM_MEAT_INTAKE_REMOTE_ENABLED": "1"}, clear=True)
    @patch("modules.oom_sakkie.routes.record_sam_meat_intake_lead")
    def test_sam_meat_intake_remote_route_requires_configured_token(self, mock_record):
        response = self.client.post(
            "/api/oom-sakkie/channels/chatwoot/sam-meat-intake",
            json={"customer_name": "Jan", "product_type": "half_carcass", "location": "Riversdale"},
        )
        data = response.get_json()

        self.assertEqual(response.status_code, 503)
        self.assertEqual(data["status"], "sam_meat_intake_remote_token_not_configured")
        self.assertEqual(data["minimum_token_chars"], 32)
        mock_record.assert_not_called()

    @patch.dict(os.environ, {
        "OOM_SAKKIE_SAM_MEAT_INTAKE_REMOTE_ENABLED": "1",
        "OOM_SAKKIE_SAM_MEAT_INTAKE_REMOTE_TOKEN": "test-sam-meat-intake-token-32-chars",
    }, clear=True)
    @patch("modules.oom_sakkie.routes.record_sam_meat_intake_lead")
    def test_sam_meat_intake_remote_route_denies_bad_token(self, mock_record):
        response = self.client.post(
            "/api/oom-sakkie/channels/chatwoot/sam-meat-intake",
            headers={"Authorization": "Bearer wrong-token"},
            json={"customer_name": "Jan", "product_type": "half_carcass", "location": "Riversdale"},
        )
        data = response.get_json()

        self.assertEqual(response.status_code, 403)
        self.assertEqual(data["status"], "sam_meat_intake_remote_auth_denied")
        self.assertFalse(data["records_tracking_lead"])
        mock_record.assert_not_called()

    @patch.dict(os.environ, {
        "OOM_SAKKIE_SAM_MEAT_INTAKE_REMOTE_ENABLED": "1",
        "OOM_SAKKIE_SAM_MEAT_INTAKE_REMOTE_TOKEN": "test-sam-meat-intake-token-32-chars",
    }, clear=True)
    @patch("modules.oom_sakkie.routes.record_sam_meat_intake_lead")
    def test_sam_meat_intake_remote_route_records_tracking_only_with_token(self, mock_record):
        mock_record.return_value = ({
            "success": True,
            "status": "ok",
            "mode": "sam_meat_intake_tracking_only",
            "lead_id": "OSK-SALES-LEAD-MEAT",
            "sends_customer_message": False,
            "calls_chatwoot": False,
            "calls_n8n": False,
            "creates_order": False,
            "changes_stock": False,
        }, 201)
        payload = {
            "customer_name": "Jan",
            "conversation_id": "1234",
            "product_type": "half_carcass",
            "cut_set": "Set A",
            "location": "Riversdale",
        }

        response = self.client.post(
            "/api/oom-sakkie/channels/chatwoot/sam-meat-intake",
            headers={"X-Amadeus-Sam-Intake-Key": "test-sam-meat-intake-token-32-chars"},
            json=payload,
        )
        data = response.get_json()

        self.assertEqual(response.status_code, 201)
        self.assertTrue(data["success"])
        self.assertEqual(data["lead_id"], "OSK-SALES-LEAD-MEAT")
        self.assertTrue(data["remote_ingest"]["records_tracking_lead"])
        self.assertFalse(data["remote_ingest"]["sends_customer_message"])
        self.assertFalse(data["remote_ingest"]["calls_chatwoot"])
        self.assertFalse(data["remote_ingest"]["calls_n8n"])
        self.assertFalse(data["remote_ingest"]["creates_order"])
        self.assertFalse(data["remote_ingest"]["changes_stock"])
        self.assertFalse(data["remote_ingest"]["financial_action"])
        mock_record.assert_called_once_with(payload)

    @patch("modules.oom_sakkie.routes.list_sales_leads")
    def test_sales_lead_route_lists_tracking_queue(self, mock_list):
        mock_list.return_value = ({
            "success": True,
            "status": "ok",
            "mode": "sales_lead_tracking_queue",
            "sales_leads": [],
            "sends_customer_message": False,
            "calls_chatwoot": False,
            "calls_n8n": False,
            "creates_order": False,
            "changes_stock": False,
        }, 200)

        response = self.client.get("/api/oom-sakkie/sales-leads?limit=5")
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["success"])
        self.assertEqual(data["mode"], "sales_lead_tracking_queue")
        self.assertFalse(data["sends_customer_message"])
        self.assertFalse(data["calls_chatwoot"])
        self.assertFalse(data["calls_n8n"])
        self.assertFalse(data["creates_order"])
        self.assertFalse(data["changes_stock"])
        mock_list.assert_called_once_with(limit="5", status_filter="")

    @patch("modules.oom_sakkie.routes.record_sales_lead_event")
    def test_sales_lead_event_route_records_append_only_event(self, mock_record):
        mock_record.return_value = ({
            "success": True,
            "status": "ok",
            "event_id": "OSK-SALES-LEAD-EVENT-TEST",
            "lead_id": "OSK-SALES-LEAD-TEST",
            "event_type": "deposit_followup_needed",
            "sends_customer_message": False,
            "calls_chatwoot": False,
            "calls_n8n": False,
            "creates_order": False,
            "changes_stock": False,
        }, 201)

        response = self.client.post(
            "/api/oom-sakkie/sales-leads/OSK-SALES-LEAD-TEST/events",
            json={"event_type": "deposit_followup_needed", "notes": "Needs deposit confirmation."},
        )
        data = response.get_json()

        self.assertEqual(response.status_code, 201)
        self.assertTrue(data["success"])
        self.assertEqual(data["event_type"], "deposit_followup_needed")
        self.assertFalse(data["sends_customer_message"])
        self.assertFalse(data["calls_chatwoot"])
        self.assertFalse(data["calls_n8n"])
        self.assertFalse(data["creates_order"])
        self.assertFalse(data["changes_stock"])
        mock_record.assert_called_once()

    @patch("modules.oom_sakkie.routes.record_owner_money_path_approval")
    def test_sales_lead_owner_money_path_approval_route_records_review_event(self, mock_record):
        mock_record.return_value = ({
            "success": True,
            "status": "ok",
            "mode": "owner_money_path_approval_event_only",
            "event_id": "OSK-SALES-LEAD-EVENT-APPROVAL",
            "lead_id": "OSK-SALES-LEAD-TEST",
            "event_type": "owner_money_path_approved",
            "records_owner_money_path_approval": True,
            "sends_customer_message": False,
            "calls_chatwoot": False,
            "calls_n8n": False,
            "creates_order": False,
            "changes_stock": False,
        }, 201)
        payload = {
            "price_per_kg": "R95/kg",
            "available_week": "week of 2026-06-22",
            "estimated_weight_or_size": "half carcass final weight to be confirmed",
            "deposit_rule": "50% deposit after customer accepts owner-approved quote",
            "payment_method": "EFT",
            "delivery_or_collection": "collection",
            "owner_final_approval": "Charl approved for manual customer follow-up",
        }

        response = self.client.post(
            "/api/oom-sakkie/sales-leads/OSK-SALES-LEAD-TEST/owner-money-path-approval",
            json=payload,
        )
        data = response.get_json()

        self.assertEqual(response.status_code, 201)
        self.assertTrue(data["success"])
        self.assertEqual(data["mode"], "owner_money_path_approval_event_only")
        self.assertEqual(data["event_type"], "owner_money_path_approved")
        self.assertFalse(data["sends_customer_message"])
        self.assertFalse(data["calls_chatwoot"])
        self.assertFalse(data["calls_n8n"])
        self.assertFalse(data["creates_order"])
        self.assertFalse(data["changes_stock"])
        mock_record.assert_called_once_with("OSK-SALES-LEAD-TEST", payload)

    @patch("modules.oom_sakkie.routes.get_sales_lead_preorder_contract")
    def test_sales_lead_preorder_contract_route_is_review_only(self, mock_contract):
        mock_contract.return_value = ({
            "success": True,
            "status": "ok",
            "mode": "preorder_deposit_contract_review_only",
            "lead_id": "OSK-SALES-LEAD-TEST",
            "contract": {
                "contract_status": "needs_owner_confirmation",
                "missing_fields": ["price_per_kg"],
            },
            "sends_customer_message": False,
            "calls_chatwoot": False,
            "calls_n8n": False,
            "creates_order": False,
            "changes_stock": False,
        }, 200)

        response = self.client.get("/api/oom-sakkie/sales-leads/OSK-SALES-LEAD-TEST/preorder-contract")
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["success"])
        self.assertEqual(data["mode"], "preorder_deposit_contract_review_only")
        self.assertFalse(data["sends_customer_message"])
        self.assertFalse(data["calls_chatwoot"])
        self.assertFalse(data["calls_n8n"])
        self.assertFalse(data["creates_order"])
        self.assertFalse(data["changes_stock"])
        mock_contract.assert_called_once_with("OSK-SALES-LEAD-TEST")

    @patch("modules.oom_sakkie.routes.get_sales_lead_customer_followup_draft")
    def test_sales_lead_customer_followup_draft_route_is_review_only(self, mock_draft):
        mock_draft.return_value = ({
            "success": True,
            "status": "ok",
            "mode": "owner_review_customer_followup_draft_only",
            "lead_id": "OSK-SALES-LEAD-TEST",
            "customer_followup_draft": {
                "mode": "owner_review_customer_followup_draft_only",
                "message": "Hi Charl, approved review draft.",
            },
            "sends_customer_message": False,
            "calls_chatwoot": False,
            "calls_n8n": False,
            "creates_quote": False,
            "creates_order": False,
            "changes_stock": False,
        }, 200)

        response = self.client.get("/api/oom-sakkie/sales-leads/OSK-SALES-LEAD-TEST/customer-followup-draft")
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["success"])
        self.assertEqual(data["mode"], "owner_review_customer_followup_draft_only")
        self.assertFalse(data["sends_customer_message"])
        self.assertFalse(data["calls_chatwoot"])
        self.assertFalse(data["calls_n8n"])
        self.assertFalse(data["creates_quote"])
        self.assertFalse(data["creates_order"])
        self.assertFalse(data["changes_stock"])
        mock_draft.assert_called_once_with("OSK-SALES-LEAD-TEST")

    @patch("modules.oom_sakkie.routes.get_sales_lead_customer_followup_send_design")
    def test_sales_lead_customer_followup_send_design_route_is_review_only(self, mock_design):
        mock_design.return_value = ({
            "success": True,
            "status": "ok",
            "mode": "sam_chatwoot_send_handoff_design_review_only",
            "lead_id": "OSK-SALES-LEAD-TEST",
            "send_handoff_design": {
                "mode": "sam_chatwoot_send_handoff_design_review_only",
                "proposed_payload": {"message": "Hi Charl, approved owner-review draft."},
            },
            "sends_customer_message": False,
            "calls_chatwoot": False,
            "calls_n8n": False,
            "creates_quote": False,
            "creates_order": False,
            "changes_stock": False,
        }, 200)

        response = self.client.get("/api/oom-sakkie/sales-leads/OSK-SALES-LEAD-TEST/customer-followup-send-design")
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["success"])
        self.assertEqual(data["mode"], "sam_chatwoot_send_handoff_design_review_only")
        self.assertFalse(data["sends_customer_message"])
        self.assertFalse(data["calls_chatwoot"])
        self.assertFalse(data["calls_n8n"])
        self.assertFalse(data["creates_quote"])
        self.assertFalse(data["creates_order"])
        self.assertFalse(data["changes_stock"])
        mock_design.assert_called_once_with("OSK-SALES-LEAD-TEST")

    @patch("modules.oom_sakkie.routes.list_sales_leads")
    def test_sales_lead_routes_are_review_gated(self, mock_list):
        response = self.client.get(
            "/api/oom-sakkie/sales-leads",
            environ_base={"REMOTE_ADDR": "203.0.113.10"},
        )
        data = response.get_json()

        self.assertEqual(response.status_code, 403)
        self.assertEqual(data["status"], "review_access_denied")
        mock_list.assert_not_called()

    def test_agents_route_denies_non_local_review_access(self):
        response = self.client.get(
            "/api/oom-sakkie/agents",
            environ_base={"REMOTE_ADDR": "203.0.113.10"},
        )
        data = response.get_json()

        self.assertEqual(response.status_code, 403)
        self.assertEqual(data["status"], "review_access_denied")

    def test_agent_contracts_route_is_review_only(self):
        response = self.client.get("/api/oom-sakkie/agents/contracts")
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["success"])
        self.assertEqual(data["mode"], "agent_operating_contracts_only")
        self.assertFalse(data["runtime_enabled"])
        self.assertFalse(data["dispatch_enabled"])
        self.assertFalse(data["writes_enabled"])
        self.assertFalse(data["review_guard"]["runs_specialist"])
        self.assertFalse(data["review_guard"]["dispatch_enabled"])
        self.assertFalse(data["review_guard"]["writes"])
        self.assertIn("beacon", data["locked_out_of_dry_run"])
        ledger = next(item for item in data["contracts"] if item["slug"] == "ledger")
        self.assertIn("send customer messages", ledger["must_not_do"])

    def test_agent_contracts_route_denies_non_local_review_access(self):
        response = self.client.get(
            "/api/oom-sakkie/agents/contracts",
            environ_base={"REMOTE_ADDR": "203.0.113.10"},
        )
        data = response.get_json()

        self.assertEqual(response.status_code, 403)
        self.assertEqual(data["status"], "review_access_denied")

    def test_agent_preflight_route_is_review_only(self):
        response = self.client.get("/api/oom-sakkie/agents/preflight")
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["success"])
        self.assertEqual(data["mode"], "agent_activation_preflight_only")
        self.assertEqual(data["summary_status"], "not_ready_for_live_dispatch")
        self.assertFalse(data["runtime_enabled"])
        self.assertFalse(data["dispatch_enabled"])
        self.assertFalse(data["writes_enabled"])
        self.assertFalse(data["review_guard"]["runs_specialist"])
        self.assertFalse(data["review_guard"]["dispatch_enabled"])
        self.assertFalse(data["review_guard"]["writes"])
        self.assertTrue(any(item["check"] == "owner_browser_pass" for item in data["manual_checks"]))

    def test_agent_preflight_route_denies_non_local_review_access(self):
        response = self.client.get(
            "/api/oom-sakkie/agents/preflight",
            environ_base={"REMOTE_ADDR": "203.0.113.10"},
        )
        data = response.get_json()

        self.assertEqual(response.status_code, 403)
        self.assertEqual(data["status"], "review_access_denied")

    def test_agent_authority_matrix_route_is_review_only(self):
        response = self.client.get("/api/oom-sakkie/agents/authority-matrix")
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["success"])
        self.assertEqual(data["mode"], "agent_authority_matrix_only")
        self.assertEqual(data["enabled_count"], 0)
        self.assertLess(data["locked_count"], data["authority_count"])
        self.assertFalse(data["runtime_enabled"])
        self.assertFalse(data["dispatch_enabled"])
        self.assertFalse(data["writes_enabled"])
        self.assertFalse(data["review_guard"]["runs_specialist"])
        self.assertFalse(data["review_guard"]["dispatch_enabled"])
        self.assertFalse(data["review_guard"]["writes"])
        by_authority = {item["authority"]: item for item in data["areas"]}
        self.assertEqual(by_authority["specialist_llm_loop"]["current_state"], "single_shot_advisory_only")
        self.assertFalse(by_authority["specialist_llm_loop"]["enabled"])
        self.assertEqual(by_authority["physical_controls"]["current_state"], "locked")
        self.assertEqual(by_authority["deploy_execution"]["risk_level"], 5)

    def test_agent_authority_matrix_route_denies_non_local_review_access(self):
        response = self.client.get(
            "/api/oom-sakkie/agents/authority-matrix",
            environ_base={"REMOTE_ADDR": "203.0.113.10"},
        )
        data = response.get_json()

        self.assertEqual(response.status_code, 403)
        self.assertEqual(data["status"], "review_access_denied")

    def test_agent_unlock_readiness_route_is_review_only(self):
        response = self.client.get("/api/oom-sakkie/agents/unlock-readiness")
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["success"])
        self.assertEqual(data["mode"], "agent_authority_unlock_readiness_only")
        self.assertEqual(data["summary_status"], "planning_only_no_unlock_recommended")
        self.assertEqual(data["enabled_count"], 0)
        self.assertFalse(data["runtime_enabled"])
        self.assertFalse(data["dispatch_enabled"])
        self.assertFalse(data["writes_enabled"])
        self.assertFalse(data["review_guard"]["runs_specialist"])
        self.assertFalse(data["review_guard"]["dispatch_enabled"])
        self.assertFalse(data["review_guard"]["writes"])
        self.assertTrue(any(item["authority"] == "physical_controls" for item in data["hard_no_authorities"]))

    def test_agent_unlock_readiness_route_denies_non_local_review_access(self):
        response = self.client.get(
            "/api/oom-sakkie/agents/unlock-readiness",
            environ_base={"REMOTE_ADDR": "203.0.113.10"},
        )
        data = response.get_json()

        self.assertEqual(response.status_code, 403)
        self.assertEqual(data["status"], "review_access_denied")

    def test_agent_dispatch_rail_blueprint_route_is_review_only(self):
        response = self.client.get("/api/oom-sakkie/agents/dispatch-rail-blueprint")
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["success"])
        self.assertEqual(data["mode"], "dispatch_decision_rail_blueprint_only")
        self.assertEqual(data["summary_status"], "blueprint_only_no_dispatch")
        self.assertEqual(data["authority"]["authority"], "live_specialist_dispatch")
        self.assertFalse(data["runtime_enabled"])
        self.assertFalse(data["dispatch_enabled"])
        self.assertFalse(data["writes_enabled"])
        self.assertFalse(data["review_guard"]["runs_specialist"])
        self.assertFalse(data["review_guard"]["dispatch_enabled"])
        self.assertFalse(data["review_guard"]["writes"])
        self.assertTrue(any(item["name"] == "oom_sakkie_dispatch_requests" for item in data["proposed_tables"]))
        self.assertIn("do not run a specialist", data["non_goals"])

    def test_agent_dispatch_rail_blueprint_route_denies_non_local_review_access(self):
        response = self.client.get(
            "/api/oom-sakkie/agents/dispatch-rail-blueprint",
            environ_base={"REMOTE_ADDR": "203.0.113.10"},
        )
        data = response.get_json()

        self.assertEqual(response.status_code, 403)
        self.assertEqual(data["status"], "review_access_denied")

    def test_agent_runtime_review_packet_route_is_review_only(self):
        response = self.client.get("/api/oom-sakkie/agents/runtime-review-packet")
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["success"])
        self.assertEqual(data["mode"], "agent_runtime_review_packet_only")
        self.assertEqual(data["summary_status"], "ready_for_bulk_claude_review_not_live_dispatch")
        self.assertFalse(data["runtime_enabled"])
        self.assertFalse(data["dispatch_enabled"])
        self.assertFalse(data["writes_enabled"])
        self.assertFalse(data["review_guard"]["runs_specialist"])
        self.assertFalse(data["review_guard"]["dispatch_enabled"])
        self.assertFalse(data["review_guard"]["writes"])
        self.assertEqual(data["payloads"]["dispatch_blueprint"]["summary_status"], "blueprint_only_no_dispatch")
        self.assertIn("CLAUDE_REVIEW_HANDOFF.md", data["claude_prompt"])

    def test_agent_runtime_review_packet_route_denies_non_local_review_access(self):
        response = self.client.get(
            "/api/oom-sakkie/agents/runtime-review-packet",
            environ_base={"REMOTE_ADDR": "203.0.113.10"},
        )
        data = response.get_json()

        self.assertEqual(response.status_code, 403)
        self.assertEqual(data["status"], "review_access_denied")

    def test_agent_recommend_route_returns_non_dispatching_recommendation(self):
        response = self.client.post(
            "/api/oom-sakkie/agents/recommend",
            json={"text": "should we post a marketing update?"},
        )
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["success"])
        self.assertEqual(data["mode"], "dispatch_recommendation_only")
        self.assertFalse(data["runs_agent"])
        self.assertFalse(data["writes"])
        self.assertFalse(data["dispatch_enabled"])
        self.assertEqual(data["selected_agent"]["slug"], "beacon")

    def test_agent_recommend_route_denies_non_local_review_access(self):
        response = self.client.post(
            "/api/oom-sakkie/agents/recommend",
            json={"text": "who should handle this?"},
            environ_base={"REMOTE_ADDR": "203.0.113.10"},
        )
        data = response.get_json()

        self.assertEqual(response.status_code, 403)
        self.assertEqual(data["status"], "review_access_denied")

    @patch("modules.oom_sakkie.routes.accepted_agent_learning_snapshot")
    def test_agent_activation_plan_route_is_read_only_panel_data(self, mock_learning):
        mock_learning.return_value = {
            "status_code": 200,
            "status": "ok",
            "accepted_count": 1,
            "accepted_by_specialist": {"ledger": 1},
            "evidence": [{
                "dry_run_result_id": "OSK-AGENT-DRYRUN-RESULT-1",
                "result_text": "Ledger reviewed internal offer planning.",
            }],
        }

        response = self.client.get("/api/oom-sakkie/agents/activation-plan?limit=20")
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["success"])
        self.assertEqual(data["mode"], "agent_activation_plan_panel")
        self.assertEqual(data["accepted_learning_count"], 1)
        self.assertEqual(data["accepted_by_specialist"], {"ledger": 1})
        self.assertFalse(data["review_guard"]["runs_specialist"])
        self.assertFalse(data["review_guard"]["dispatch_enabled"])
        self.assertFalse(data["review_guard"]["writes"])
        self.assertFalse(data["review_guard"]["applies_runtime_change"])
        self.assertFalse(data["activation_plan"]["dispatch_enabled"])

    def test_agent_activation_plan_route_denies_non_local_review_access(self):
        response = self.client.get(
            "/api/oom-sakkie/agents/activation-plan",
            environ_base={"REMOTE_ADDR": "203.0.113.10"},
        )
        data = response.get_json()

        self.assertEqual(response.status_code, 403)
        self.assertEqual(data["status"], "review_access_denied")

    @patch("modules.oom_sakkie.routes.list_learning_influence_proposals")
    def test_learning_influence_proposals_route_lists_without_applying_learning(self, mock_list):
        mock_list.return_value = ({
            "success": True,
            "status": "ok",
            "learning_influence_proposals": [{
                "proposal_id": "OSK-LEARNING-INFLUENCE-1",
                "applies_learning_now": False,
                "changes_prompt_now": False,
                "changes_runtime_now": False,
                "dispatch_enabled": False,
                "writes": False,
            }],
            "applies_learning_now": False,
            "changes_prompt_now": False,
            "changes_runtime_now": False,
            "dispatch_enabled": False,
            "writes": False,
        }, 200)

        response = self.client.get("/api/oom-sakkie/agent-learning/influence-proposals")
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["success"])
        self.assertFalse(data["applies_learning_now"])
        self.assertFalse(data["changes_prompt_now"])
        self.assertFalse(data["changes_runtime_now"])
        self.assertFalse(data["dispatch_enabled"])
        self.assertFalse(data["writes"])

    @patch("modules.oom_sakkie.routes.record_learning_influence_proposals_from_accepted")
    def test_learning_influence_from_accepted_route_records_proposals_only(self, mock_record):
        mock_record.return_value = ({
            "success": True,
            "status": "ok",
            "created_count": 1,
            "learning_influence_proposals": [],
            "applies_learning_now": False,
            "changes_prompt_now": False,
            "changes_runtime_now": False,
            "dispatch_enabled": False,
            "writes": False,
        }, 201)

        response = self.client.post("/api/oom-sakkie/agent-learning/influence-proposals/from-accepted", json={"limit": 8})
        data = response.get_json()

        self.assertEqual(response.status_code, 201)
        self.assertTrue(data["success"])
        self.assertEqual(data["created_count"], 1)
        self.assertFalse(data["applies_learning_now"])
        self.assertFalse(data["changes_prompt_now"])
        self.assertFalse(data["dispatch_enabled"])
        self.assertFalse(data["writes"])

    @patch("modules.oom_sakkie.routes.record_learning_influence_proposal_from_result")
    def test_learning_influence_from_result_route_records_one_source_only(self, mock_record):
        mock_record.return_value = ({
            "success": True,
            "status": "ok",
            "created_count": 1,
            "learning_influence_proposals": [{
                "source_result_id": "OSK-AGENT-DRYRUN-RESULT-C63AF980E948",
                "applies_learning_now": False,
                "changes_prompt_now": False,
                "changes_runtime_now": False,
                "dispatch_enabled": False,
                "writes": False,
            }],
            "applies_learning_now": False,
            "changes_prompt_now": False,
            "changes_runtime_now": False,
            "dispatch_enabled": False,
            "writes": False,
        }, 201)

        response = self.client.post(
            "/api/oom-sakkie/agent-learning/influence-proposals/from-result",
            json={"source_result_id": "OSK-AGENT-DRYRUN-RESULT-C63AF980E948"},
        )
        data = response.get_json()

        self.assertEqual(response.status_code, 201)
        self.assertTrue(data["success"])
        self.assertEqual(data["created_count"], 1)
        self.assertFalse(data["applies_learning_now"])
        self.assertFalse(data["changes_prompt_now"])
        self.assertFalse(data["dispatch_enabled"])
        self.assertFalse(data["writes"])
        mock_record.assert_called_once_with("OSK-AGENT-DRYRUN-RESULT-C63AF980E948")

    @patch("modules.oom_sakkie.routes.record_learning_influence_proposal_from_result")
    def test_learning_influence_from_result_route_propagates_not_accepted_guard(self, mock_record):
        mock_record.return_value = ({
            "success": False,
            "status": "source_result_not_accepted_for_learning",
            "source_result_id": "OSK-AGENT-DRYRUN-RESULT-PENDING",
            "learning_influence_proposals": [],
            "created_count": 0,
            "applies_learning_now": False,
            "changes_prompt_now": False,
            "changes_runtime_now": False,
            "dispatch_enabled": False,
            "writes": False,
        }, 409)

        response = self.client.post(
            "/api/oom-sakkie/agent-learning/influence-proposals/from-result",
            json={"source_result_id": "OSK-AGENT-DRYRUN-RESULT-PENDING"},
        )
        data = response.get_json()

        self.assertEqual(response.status_code, 409)
        self.assertFalse(data["success"])
        self.assertEqual(data["status"], "source_result_not_accepted_for_learning")
        self.assertEqual(data["created_count"], 0)
        self.assertFalse(data["applies_learning_now"])
        self.assertFalse(data["changes_prompt_now"])
        self.assertFalse(data["changes_runtime_now"])
        self.assertFalse(data["dispatch_enabled"])
        self.assertFalse(data["writes"])
        mock_record.assert_called_once_with("OSK-AGENT-DRYRUN-RESULT-PENDING")

    @patch("modules.oom_sakkie.routes.record_learning_influence_proposal_from_result")
    def test_learning_influence_from_result_route_returns_existing_proposal_without_apply(self, mock_record):
        mock_record.return_value = ({
            "success": True,
            "status": "ok",
            "created_count": 0,
            "accepted_count": 1,
            "learning_influence_proposals": [{
                "proposal_id": "OSK-LEARNING-INFLUENCE-EXISTING",
                "source_result_id": "OSK-AGENT-DRYRUN-RESULT-C63AF980E948",
                "applies_learning_now": False,
                "changes_prompt_now": False,
                "changes_runtime_now": False,
                "dispatch_enabled": False,
                "writes": False,
            }],
            "applies_learning_now": False,
            "changes_prompt_now": False,
            "changes_runtime_now": False,
            "dispatch_enabled": False,
            "writes": False,
        }, 201)

        response = self.client.post(
            "/api/oom-sakkie/agent-learning/influence-proposals/from-result",
            json={"source_result_id": "OSK-AGENT-DRYRUN-RESULT-C63AF980E948"},
        )
        data = response.get_json()

        self.assertEqual(response.status_code, 201)
        self.assertTrue(data["success"])
        self.assertEqual(data["created_count"], 0)
        self.assertEqual(data["accepted_count"], 1)
        self.assertEqual(data["learning_influence_proposals"][0]["proposal_id"], "OSK-LEARNING-INFLUENCE-EXISTING")
        self.assertFalse(data["applies_learning_now"])
        self.assertFalse(data["changes_prompt_now"])
        self.assertFalse(data["changes_runtime_now"])
        self.assertFalse(data["dispatch_enabled"])
        self.assertFalse(data["writes"])
        mock_record.assert_called_once_with("OSK-AGENT-DRYRUN-RESULT-C63AF980E948")

    @patch("modules.oom_sakkie.routes.record_learning_influence_proposal_event")
    def test_learning_influence_event_route_records_review_only_event(self, mock_record):
        mock_record.return_value = ({
            "success": True,
            "status": "ok",
            "event_id": "OSK-LEARNING-INFLUENCE-EVENT-1",
            "proposal_id": "OSK-LEARNING-INFLUENCE-1",
            "event_type": "approved_for_future_planning",
            "applies_learning_now": False,
            "changes_prompt_now": False,
            "changes_runtime_now": False,
            "dispatch_enabled": False,
            "writes": False,
        }, 201)

        response = self.client.post(
            "/api/oom-sakkie/agent-learning/influence-proposals/OSK-LEARNING-INFLUENCE-1/events",
            json={"event_type": "approved_for_future_planning", "notes": "Planning only."},
        )
        data = response.get_json()

        self.assertEqual(response.status_code, 201)
        self.assertTrue(data["success"])
        self.assertEqual(data["event_type"], "approved_for_future_planning")
        self.assertFalse(data["applies_learning_now"])
        self.assertFalse(data["changes_prompt_now"])
        self.assertFalse(data["dispatch_enabled"])
        self.assertFalse(data["writes"])

    def test_learning_influence_routes_deny_non_local_review_access(self):
        response = self.client.post(
            "/api/oom-sakkie/agent-learning/influence-proposals/from-accepted",
            json={"limit": 8},
            environ_base={"REMOTE_ADDR": "203.0.113.10"},
        )
        data = response.get_json()

        self.assertEqual(response.status_code, 403)
        self.assertEqual(data["status"], "review_access_denied")

        response = self.client.post(
            "/api/oom-sakkie/agent-learning/influence-proposals/from-result",
            json={"source_result_id": "OSK-AGENT-DRYRUN-RESULT-C63AF980E948"},
            environ_base={"REMOTE_ADDR": "203.0.113.10"},
        )
        data = response.get_json()

        self.assertEqual(response.status_code, 403)
        self.assertEqual(data["status"], "review_access_denied")

    def test_learning_influence_consumption_readiness_route_is_read_only(self):
        response = self.client.get("/api/oom-sakkie/agent-learning/consumption-readiness")
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["success"])
        self.assertEqual(data["mode"], "learning_influence_consumption_readiness_only")
        self.assertFalse(data["learning_influence_consumer_enabled"])
        self.assertFalse(data["applies_learning_now"])
        self.assertFalse(data["changes_prompt_now"])
        self.assertFalse(data["changes_runtime_now"])
        self.assertFalse(data["dispatch_enabled"])
        self.assertFalse(data["writes_enabled"])
        self.assertFalse(data["review_guard"]["dispatch_enabled"])
        self.assertFalse(data["review_guard"]["runs_specialist_tools"])
        self.assertFalse(data["review_guard"]["writes"])
        self.assertIn("append_only_consumption_audit_rail", data["required_gates"])

    def test_learning_influence_consumption_readiness_route_denies_non_local_review_access(self):
        response = self.client.get(
            "/api/oom-sakkie/agent-learning/consumption-readiness",
            environ_base={"REMOTE_ADDR": "203.0.113.10"},
        )
        data = response.get_json()

        self.assertEqual(response.status_code, 403)
        self.assertEqual(data["status"], "review_access_denied")

    def test_learning_influence_consumption_audit_rail_blueprint_route_is_read_only(self):
        response = self.client.get("/api/oom-sakkie/agent-learning/consumption-audit-rail-blueprint")
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["success"])
        self.assertEqual(data["mode"], "learning_influence_consumption_audit_rail_blueprint_only")
        self.assertFalse(data["learning_influence_consumer_enabled"])
        self.assertFalse(data["applies_learning_now"])
        self.assertFalse(data["changes_prompt_now"])
        self.assertFalse(data["changes_runtime_now"])
        self.assertFalse(data["dispatch_enabled"])
        self.assertFalse(data["writes_enabled"])
        self.assertTrue(data["creates_tables_now"])
        self.assertTrue(data["adds_routes_now"])
        self.assertTrue(data["review_note_only_first_slice"])
        self.assertFalse(data["review_guard"]["dispatch_enabled"])
        self.assertFalse(data["review_guard"]["runs_specialist_tools"])
        self.assertFalse(data["review_guard"]["writes"])
        self.assertEqual(data["allowlisted_target_contract"]["first_slice_limit"], "one_target_field_per_consumption")
        self.assertTrue(data["allowlisted_target_contract"]["diff_contract"]["proposal_text_is_untrusted"])

    def test_learning_influence_consumption_audit_rail_blueprint_route_denies_non_local_review_access(self):
        response = self.client.get(
            "/api/oom-sakkie/agent-learning/consumption-audit-rail-blueprint",
            environ_base={"REMOTE_ADDR": "203.0.113.10"},
        )
        data = response.get_json()

        self.assertEqual(response.status_code, 403)
        self.assertEqual(data["status"], "review_access_denied")

    def test_learning_influence_consumer_design_packet_route_is_read_only(self):
        response = self.client.get("/api/oom-sakkie/agent-learning/consumer-design-packet")
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["success"])
        self.assertEqual(data["mode"], "learning_influence_consumer_design_packet_only")
        self.assertTrue(data["learning_influence_consumer_enabled"])
        self.assertFalse(data["applies_learning_now"])
        self.assertFalse(data["changes_prompt_now"])
        self.assertFalse(data["changes_runtime_now"])
        self.assertFalse(data["dispatch_enabled"])
        self.assertFalse(data["writes_enabled"])
        self.assertEqual(data["allow_consumed_production_callers"], [])
        self.assertEqual(data["allowed_target_contract"]["first_consumer_output"], "review_note_artifact_only")
        self.assertTrue(data["allowed_target_contract"]["proposal_text_is_untrusted"])
        self.assertEqual(
            data["consumer_design_review_agreement"]["status"],
            "owner_approved_review_note_consumer_implemented_no_apply",
        )
        self.assertTrue(data["consumer_design_review_agreement"]["implementation_authorized_now"])
        self.assertTrue(data["consumer_design_review_agreement"]["allow_consumed_true_authorized_now"])
        self.assertEqual(
            data["reviewed_allow_consumed_production_callers"],
            ["modules/oom_sakkie/learning_influence_consumer.py"],
        )
        self.assertIn(
            "prompt_patch",
            data["consumer_design_review_agreement"]["review_note_artifact_shape"]["forbidden_fields"],
        )
        self.assertIn(
            "idx_oom_sakkie_learning_consumption_consumed_once",
            data["consumer_design_review_agreement"]["must_recheck_before_marker_enforcement"]["atomicity_guard"],
        )
        self.assertIn(
            "produce no second review-note artifact",
            data["consumer_design_review_agreement"]["must_recheck_before_marker_enforcement"]["unique_violation_behavior"],
        )
        self.assertFalse(data["review_guard"]["dispatch_enabled"])
        self.assertFalse(data["review_guard"]["runs_specialist_tools"])
        self.assertFalse(data["review_guard"]["writes"])

    def test_learning_influence_consumer_design_packet_route_denies_non_local_review_access(self):
        response = self.client.get(
            "/api/oom-sakkie/agent-learning/consumer-design-packet",
            environ_base={"REMOTE_ADDR": "203.0.113.10"},
        )
        data = response.get_json()

        self.assertEqual(response.status_code, 403)
        self.assertEqual(data["status"], "review_access_denied")

    @patch("modules.oom_sakkie.routes.list_learning_influence_consumption_requests")
    def test_learning_influence_consumption_requests_route_lists_without_applying_learning(self, mock_list):
        mock_list.return_value = ({
            "success": True,
            "status": "ok",
            "mode": "learning_influence_consumption_request_queue",
            "learning_influence_consumption_requests": [{
                "consumption_request_id": "OSK-LEARNING-CONSUME-1",
                "proposal_id": "OSK-LEARNING-INFLUENCE-1",
                "review_note_artifact": {"kind": "review_note_only"},
                "applies_learning_now": False,
                "changes_prompt_now": False,
                "changes_runtime_now": False,
                "dispatch_enabled": False,
                "writes": False,
            }],
            "applies_learning_now": False,
            "changes_prompt_now": False,
            "changes_runtime_now": False,
            "dispatch_enabled": False,
            "writes": False,
        }, 200)

        response = self.client.get("/api/oom-sakkie/agent-learning/consumption-requests?limit=8")
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["success"])
        self.assertFalse(data["applies_learning_now"])
        self.assertFalse(data["changes_prompt_now"])
        self.assertFalse(data["changes_runtime_now"])
        self.assertFalse(data["dispatch_enabled"])
        self.assertFalse(data["writes"])
        mock_list.assert_called_once_with(limit="8")

    @patch("modules.oom_sakkie.routes.record_learning_influence_consumption_request")
    def test_learning_influence_consumption_request_route_records_review_note_only(self, mock_record):
        mock_record.return_value = ({
            "success": True,
            "status": "ok",
            "created_count": 1,
            "learning_influence_consumption_requests": [{
                "consumption_request_id": "OSK-LEARNING-CONSUME-1",
                "proposal_id": "OSK-LEARNING-INFLUENCE-1",
                "review_note_artifact": {"kind": "review_note_only"},
                "applies_learning_now": False,
                "changes_prompt_now": False,
                "changes_runtime_now": False,
                "dispatch_enabled": False,
                "writes": False,
            }],
            "review_note_artifact_only": True,
            "applies_learning_now": False,
            "changes_prompt_now": False,
            "changes_runtime_now": False,
            "dispatch_enabled": False,
            "writes": False,
        }, 201)
        payload = {
            "proposal_id": "OSK-LEARNING-INFLUENCE-1",
            "requested_target_kind": "planning_context_note",
            "requested_target_field": "owner_review_notes",
            "request_note": "Review-note only.",
        }

        response = self.client.post("/api/oom-sakkie/agent-learning/consumption-requests", json=payload)
        data = response.get_json()

        self.assertEqual(response.status_code, 201)
        self.assertTrue(data["success"])
        self.assertTrue(data["review_note_artifact_only"])
        self.assertFalse(data["applies_learning_now"])
        self.assertFalse(data["changes_prompt_now"])
        self.assertFalse(data["changes_runtime_now"])
        self.assertFalse(data["dispatch_enabled"])
        self.assertFalse(data["writes"])
        mock_record.assert_called_once_with(payload)

    @patch("modules.oom_sakkie.routes.record_learning_influence_consumption_event")
    def test_learning_influence_consumption_event_route_rejects_future_consumed_marker(self, mock_record):
        mock_record.return_value = ({
            "success": False,
            "status": "consumed_event_is_future_consumer_only",
            "applies_learning_now": False,
            "changes_prompt_now": False,
            "changes_runtime_now": False,
            "dispatch_enabled": False,
            "writes": False,
        }, 403)

        response = self.client.post(
            "/api/oom-sakkie/agent-learning/consumption-requests/OSK-LEARNING-CONSUME-1/events",
            json={"event_type": "consumed_for_patch_proposal"},
        )
        data = response.get_json()

        self.assertEqual(response.status_code, 403)
        self.assertFalse(data["success"])
        self.assertEqual(data["status"], "consumed_event_is_future_consumer_only")
        self.assertFalse(data["applies_learning_now"])
        self.assertFalse(data["changes_prompt_now"])
        self.assertFalse(data["changes_runtime_now"])
        self.assertFalse(data["dispatch_enabled"])
        self.assertFalse(data["writes"])
        mock_record.assert_called_once()

    @patch("modules.oom_sakkie.routes.produce_learning_influence_review_note_artifact")
    def test_learning_influence_review_note_consumer_route_produces_review_note_only(self, mock_consumer):
        mock_consumer.return_value = ({
            "success": True,
            "status": "ok",
            "mode": "learning_influence_review_note_consumer_only",
            "review_note_artifact": {"kind": "review_note_only"},
            "review_note_artifact_only": True,
            "applies_learning_now": False,
            "changes_prompt_now": False,
            "changes_runtime_now": False,
            "dispatch_enabled": False,
            "writes": False,
        }, 201)
        payload = {"recorded_by": "unittest"}

        response = self.client.post(
            "/api/oom-sakkie/agent-learning/consumption-requests/OSK-LEARNING-CONSUME-1/review-note-artifact",
            json=payload,
        )
        data = response.get_json()

        self.assertEqual(response.status_code, 201)
        self.assertTrue(data["success"])
        self.assertEqual(data["mode"], "learning_influence_review_note_consumer_only")
        self.assertEqual(data["review_note_artifact"]["kind"], "review_note_only")
        self.assertTrue(data["review_note_artifact_only"])
        self.assertFalse(data["applies_learning_now"])
        self.assertFalse(data["changes_prompt_now"])
        self.assertFalse(data["changes_runtime_now"])
        self.assertFalse(data["dispatch_enabled"])
        self.assertFalse(data["writes"])
        mock_consumer.assert_called_once_with("OSK-LEARNING-CONSUME-1", payload)

    def test_learning_influence_consumption_routes_deny_non_local_review_access(self):
        response = self.client.post(
            "/api/oom-sakkie/agent-learning/consumption-requests",
            json={"proposal_id": "OSK-LEARNING-INFLUENCE-1"},
            environ_base={"REMOTE_ADDR": "203.0.113.10"},
        )
        data = response.get_json()

        self.assertEqual(response.status_code, 403)
        self.assertEqual(data["status"], "review_access_denied")

        response = self.client.post(
            "/api/oom-sakkie/agent-learning/consumption-requests/OSK-LEARNING-CONSUME-1/events",
            json={"event_type": "review_note"},
            environ_base={"REMOTE_ADDR": "203.0.113.10"},
        )
        data = response.get_json()

        self.assertEqual(response.status_code, 403)
        self.assertEqual(data["status"], "review_access_denied")

        response = self.client.post(
            "/api/oom-sakkie/agent-learning/consumption-requests/OSK-LEARNING-CONSUME-1/review-note-artifact",
            json={},
            environ_base={"REMOTE_ADDR": "203.0.113.10"},
        )
        data = response.get_json()

        self.assertEqual(response.status_code, 403)
        self.assertEqual(data["status"], "review_access_denied")

    @patch("modules.oom_sakkie.routes.list_agent_dry_run_requests")
    def test_agent_dry_runs_route_lists_without_execution(self, mock_list):
        mock_list.return_value = ({
            "success": True,
            "status": "ok",
            "mode": "read_only_dry_run_request_queue",
            "dry_run_enabled": False,
            "dispatch_enabled": False,
            "runs_specialist_llm": False,
            "runs_specialist_tools": False,
            "writes": False,
            "dry_run_requests": [],
        }, 200)

        response = self.client.get("/api/oom-sakkie/agent-dry-runs?limit=8")
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["success"])
        self.assertFalse(data["dispatch_enabled"])
        self.assertFalse(data["runs_specialist_llm"])
        self.assertFalse(data["writes"])
        mock_list.assert_called_once_with(limit="8")

    @patch("modules.oom_sakkie.routes.record_agent_dry_run_request")
    def test_agent_dry_run_create_route_records_request_only(self, mock_record):
        mock_record.return_value = ({
            "success": True,
            "status": "ok",
            "mode": "read_only_dry_run_request_only",
            "dry_run_request_id": "OSK-AGENT-DRYRUN-1",
            "specialist_slug": "sentinel",
            "dry_run_enabled": False,
            "dispatch_enabled": False,
            "runs_specialist_llm": False,
            "runs_specialist_tools": False,
            "writes": False,
        }, 201)

        response = self.client.post(
            "/api/oom-sakkie/agent-dry-runs",
            json={"specialist_slug": "sentinel", "owner_text": "approve first dry-run"},
        )
        data = response.get_json()

        self.assertEqual(response.status_code, 201)
        self.assertEqual(data["mode"], "read_only_dry_run_request_only")
        self.assertFalse(data["dry_run_enabled"])
        self.assertFalse(data["dispatch_enabled"])
        self.assertFalse(data["runs_specialist_llm"])
        self.assertFalse(data["writes"])
        mock_record.assert_called_once()

    @patch("modules.oom_sakkie.routes.record_agent_dry_run_request")
    def test_agent_dry_run_create_route_supports_roadmap_request_without_execution(self, mock_record):
        mock_record.return_value = ({
            "success": True,
            "status": "ok",
            "mode": "read_only_dry_run_request_only",
            "dry_run_request_id": "OSK-AGENT-DRYRUN-ROADMAP",
            "specialist_slug": "sentinel",
            "dry_run_enabled": False,
            "dispatch_enabled": False,
            "runs_specialist_llm": False,
            "runs_specialist_tools": False,
            "writes": False,
        }, 201)

        response = self.client.post(
            "/api/oom-sakkie/agent-dry-runs",
            json={
                "specialist_slug": "sentinel",
                "requested_by": "kiosk",
                "owner_text": "Owner requested the first Sentinel read-only dry-run from the Agent Roadmap panel.",
                "purpose": "Create an append-only approval record for a future Sentinel dry-run review. Do not run Sentinel.",
            },
        )
        data = response.get_json()

        self.assertEqual(response.status_code, 201)
        self.assertEqual(data["dry_run_request_id"], "OSK-AGENT-DRYRUN-ROADMAP")
        self.assertFalse(data["dry_run_enabled"])
        self.assertFalse(data["dispatch_enabled"])
        self.assertFalse(data["runs_specialist_llm"])
        self.assertFalse(data["runs_specialist_tools"])
        self.assertFalse(data["writes"])
        payload = mock_record.call_args.args[0]
        self.assertEqual(payload["specialist_slug"], "sentinel")
        self.assertIn("Do not run Sentinel", payload["purpose"])

    @patch("modules.oom_sakkie.routes.record_agent_dry_run_request")
    def test_agent_dry_run_create_route_supports_prism_request_without_execution(self, mock_record):
        mock_record.return_value = ({
            "success": True,
            "status": "ok",
            "mode": "read_only_dry_run_request_only",
            "dry_run_request_id": "OSK-AGENT-DRYRUN-PRISM",
            "specialist_slug": "prism",
            "dry_run_enabled": False,
            "dispatch_enabled": False,
            "runs_specialist_llm": False,
            "runs_specialist_tools": False,
            "writes": False,
        }, 201)

        response = self.client.post(
            "/api/oom-sakkie/agent-dry-runs",
            json={
                "specialist_slug": "prism",
                "requested_by": "kiosk",
                "owner_text": "Review the kiosk layout.",
                "purpose": "Create an append-only approval record for a future Prism kiosk/interface review. Do not run Prism.",
            },
        )
        data = response.get_json()

        self.assertEqual(response.status_code, 201)
        self.assertEqual(data["specialist_slug"], "prism")
        self.assertFalse(data["dry_run_enabled"])
        self.assertFalse(data["dispatch_enabled"])
        self.assertFalse(data["runs_specialist_llm"])
        self.assertFalse(data["runs_specialist_tools"])
        self.assertFalse(data["writes"])
        payload = mock_record.call_args.args[0]
        self.assertEqual(payload["specialist_slug"], "prism")
        self.assertIn("Do not run Prism", payload["purpose"])

    @patch("modules.oom_sakkie.routes.record_agent_dry_run_request")
    def test_agent_dry_run_create_route_supports_selected_business_specialist_without_execution(self, mock_record):
        mock_record.return_value = ({
            "success": True,
            "status": "ok",
            "mode": "read_only_dry_run_request_only",
            "dry_run_request_id": "OSK-AGENT-DRYRUN-LEDGER",
            "specialist_slug": "ledger",
            "dry_run_enabled": False,
            "dispatch_enabled": False,
            "runs_specialist_llm": False,
            "runs_specialist_tools": False,
            "writes": False,
        }, 201)

        response = self.client.post(
            "/api/oom-sakkie/agent-dry-runs",
            json={
                "specialist_slug": "ledger",
                "requested_by": "kiosk",
                "owner_text": "Owner requested a Ledger read-only dry-run from the Agent Roadmap panel.",
                "purpose": "Create an append-only approval record for a future Ledger business/profit review. Do not run Ledger.",
            },
        )
        data = response.get_json()

        self.assertEqual(response.status_code, 201)
        self.assertEqual(data["specialist_slug"], "ledger")
        self.assertFalse(data["dry_run_enabled"])
        self.assertFalse(data["dispatch_enabled"])
        self.assertFalse(data["runs_specialist_llm"])
        self.assertFalse(data["runs_specialist_tools"])
        self.assertFalse(data["writes"])
        payload = mock_record.call_args.args[0]
        self.assertEqual(payload["specialist_slug"], "ledger")
        self.assertIn("Do not run Ledger", payload["purpose"])

    @patch("modules.oom_sakkie.routes.record_agent_dry_run_event")
    def test_agent_dry_run_event_route_records_event_only(self, mock_record):
        mock_record.return_value = ({
            "success": True,
            "status": "ok",
            "event_type": "approved",
            "dry_run_enabled": False,
            "dispatch_enabled": False,
            "runs_specialist_llm": False,
            "runs_specialist_tools": False,
            "writes": False,
        }, 201)

        response = self.client.post(
            "/api/oom-sakkie/agent-dry-runs/OSK-AGENT-DRYRUN-1/events",
            json={"event_type": "approved", "notes": "record only"},
        )
        data = response.get_json()

        self.assertEqual(response.status_code, 201)
        self.assertEqual(data["event_type"], "approved")
        self.assertFalse(data["dispatch_enabled"])
        self.assertFalse(data["runs_specialist_llm"])
        self.assertFalse(data["writes"])
        mock_record.assert_called_once_with(
            "OSK-AGENT-DRYRUN-1",
            {"event_type": "approved", "notes": "record only"},
        )

    @patch("modules.oom_sakkie.routes.build_agent_dry_run_handoff")
    @patch("modules.oom_sakkie.routes.get_agent_dry_run_request")
    def test_agent_dry_run_handoff_route_requires_persisted_request_id(self, mock_get, mock_handoff):
        mock_get.return_value = ({
            "success": True,
            "dry_run_request": {
                "dry_run_request_id": "OSK-AGENT-DRYRUN-1",
                "mode": "read_only_dry_run_request_only",
                "specialist_slug": "sentinel",
                "dry_run_enabled": False,
                "dispatch_enabled": False,
                "runs_specialist_llm": False,
                "runs_specialist_tools": False,
                "writes": False,
            },
        }, 200)
        mock_handoff.return_value = ({
            "success": True,
            "mode": "agent_dry_run_handoff_only",
            "dry_run_request_id": "OSK-AGENT-DRYRUN-1",
            "specialist_slug": "sentinel",
            "runs_specialist": False,
            "runs_specialist_llm": False,
            "runs_specialist_tools": False,
            "dispatch_enabled": False,
            "writes": False,
            "prompt": "handoff only",
        }, 200)

        response = self.client.post(
            "/api/oom-sakkie/agent-dry-runs/handoff",
            json={"dry_run_request_id": "OSK-AGENT-DRYRUN-1"},
        )
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(data["mode"], "agent_dry_run_handoff_only")
        self.assertFalse(data["runs_specialist"])
        self.assertFalse(data["runs_specialist_llm"])
        self.assertFalse(data["runs_specialist_tools"])
        self.assertFalse(data["dispatch_enabled"])
        self.assertFalse(data["writes"])
        mock_get.assert_called_once_with("OSK-AGENT-DRYRUN-1")
        mock_handoff.assert_called_once()

    @patch("modules.oom_sakkie.routes.get_agent_dry_run_request")
    def test_agent_dry_run_handoff_route_rejects_missing_request(self, mock_get):
        mock_get.return_value = ({
            "success": False,
            "status": "agent_dry_run_request_not_found",
            "dry_run_request_id": "OSK-AGENT-DRYRUN-FAKE",
        }, 404)

        response = self.client.post(
            "/api/oom-sakkie/agent-dry-runs/handoff",
            json={"dry_run_request_id": "OSK-AGENT-DRYRUN-FAKE"},
        )
        data = response.get_json()

        self.assertEqual(response.status_code, 404)
        self.assertEqual(data["status"], "agent_dry_run_request_not_found")

    @patch("modules.oom_sakkie.routes.record_agent_dry_run_result")
    def test_agent_dry_run_result_create_route_records_review_only_result(self, mock_record):
        mock_record.return_value = ({
            "success": True,
            "status": "ok",
            "mode": "dry_run_result_review_only",
            "dry_run_result_id": "OSK-AGENT-DRYRUN-RESULT-1",
            "dry_run_request_id": "OSK-AGENT-DRYRUN-1",
            "runs_specialist": False,
            "dispatch_enabled": False,
            "runs_specialist_llm": False,
            "runs_specialist_tools": False,
            "writes": False,
            "applies_runtime_change": False,
        }, 201)

        response = self.client.post(
            "/api/oom-sakkie/agent-dry-runs/OSK-AGENT-DRYRUN-1/results",
            json={"result_text": "Sentinel found no execution path.", "findings": ["No live dispatch."]},
        )
        data = response.get_json()

        self.assertEqual(response.status_code, 201)
        self.assertEqual(data["mode"], "dry_run_result_review_only")
        self.assertFalse(data["runs_specialist"])
        self.assertFalse(data["dispatch_enabled"])
        self.assertFalse(data["runs_specialist_llm"])
        self.assertFalse(data["runs_specialist_tools"])
        self.assertFalse(data["writes"])
        self.assertFalse(data["applies_runtime_change"])
        mock_record.assert_called_once()

    @patch("modules.oom_sakkie.routes.list_agent_dry_run_results")
    def test_agent_dry_run_results_route_lists_without_execution(self, mock_list):
        mock_list.return_value = ({
            "success": True,
            "status": "ok",
            "mode": "dry_run_result_review_queue",
            "runs_specialist": False,
            "dispatch_enabled": False,
            "runs_specialist_llm": False,
            "runs_specialist_tools": False,
            "writes": False,
            "applies_runtime_change": False,
            "dry_run_results": [],
        }, 200)

        response = self.client.get("/api/oom-sakkie/agent-dry-run-results?limit=4&dry_run_request_id=OSK-AGENT-DRYRUN-1")
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(data["mode"], "dry_run_result_review_queue")
        self.assertFalse(data["runs_specialist"])
        self.assertFalse(data["dispatch_enabled"])
        self.assertFalse(data["runs_specialist_llm"])
        self.assertFalse(data["writes"])
        self.assertFalse(data["applies_runtime_change"])
        mock_list.assert_called_once_with(dry_run_request_id="OSK-AGENT-DRYRUN-1", limit="4")

    @patch("modules.oom_sakkie.routes.record_agent_dry_run_result_event")
    def test_agent_dry_run_result_event_route_records_review_only_event(self, mock_record):
        mock_record.return_value = ({
            "success": True,
            "status": "ok",
            "event_type": "accepted_for_learning",
            "runs_specialist": False,
            "dispatch_enabled": False,
            "runs_specialist_llm": False,
            "runs_specialist_tools": False,
            "writes": False,
            "applies_runtime_change": False,
        }, 201)

        response = self.client.post(
            "/api/oom-sakkie/agent-dry-run-results/OSK-AGENT-DRYRUN-RESULT-1/events",
            json={"event_type": "accepted_for_learning", "notes": "Record only."},
        )
        data = response.get_json()

        self.assertEqual(response.status_code, 201)
        self.assertEqual(data["event_type"], "accepted_for_learning")
        self.assertFalse(data["runs_specialist"])
        self.assertFalse(data["dispatch_enabled"])
        self.assertFalse(data["runs_specialist_llm"])
        self.assertFalse(data["writes"])
        self.assertFalse(data["applies_runtime_change"])
        mock_record.assert_called_once_with(
            "OSK-AGENT-DRYRUN-RESULT-1",
            {"event_type": "accepted_for_learning", "notes": "Record only."},
        )

    @patch("modules.oom_sakkie.routes.build_agent_dry_run_result_review_packet")
    @patch("modules.oom_sakkie.routes.get_agent_dry_run_result")
    def test_agent_dry_run_result_review_packet_route_requires_persisted_result(self, mock_get, mock_packet):
        mock_get.return_value = ({
            "success": True,
            "status": "ok",
            "dry_run_result": {
                "dry_run_result_id": "OSK-AGENT-DRYRUN-RESULT-1",
                "mode": "dry_run_result_review_only",
            },
        }, 200)
        mock_packet.return_value = ({
            "success": True,
            "status": "ok",
            "mode": "dry_run_result_review_packet",
            "dry_run_result_id": "OSK-AGENT-DRYRUN-RESULT-1",
            "review_guard": {
                "runs_specialist": False,
                "dispatch_enabled": False,
                "runs_specialist_llm": False,
                "runs_specialist_tools": False,
                "writes": False,
                "applies_runtime_change": False,
            },
        }, 200)

        response = self.client.get(
            "/api/oom-sakkie/agent-dry-run-results/OSK-AGENT-DRYRUN-RESULT-1/review-packet"
        )
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(data["mode"], "dry_run_result_review_packet")
        self.assertFalse(data["review_guard"]["runs_specialist"])
        self.assertFalse(data["review_guard"]["dispatch_enabled"])
        self.assertFalse(data["review_guard"]["writes"])
        self.assertFalse(data["review_guard"]["applies_runtime_change"])
        mock_get.assert_called_once_with("OSK-AGENT-DRYRUN-RESULT-1")
        mock_packet.assert_called_once()

    @patch("modules.oom_sakkie.routes.build_agent_dry_run_result_review_packet")
    @patch("modules.oom_sakkie.routes.get_agent_dry_run_result")
    def test_agent_dry_run_result_review_packet_route_propagates_missing_result(self, mock_get, mock_packet):
        mock_get.return_value = ({
            "success": False,
            "status": "dry_run_result_not_found",
            "dry_run_result_id": "OSK-AGENT-DRYRUN-RESULT-FAKE",
        }, 404)

        response = self.client.get(
            "/api/oom-sakkie/agent-dry-run-results/OSK-AGENT-DRYRUN-RESULT-FAKE/review-packet"
        )
        data = response.get_json()

        self.assertEqual(response.status_code, 404)
        self.assertEqual(data["status"], "dry_run_result_not_found")
        mock_packet.assert_not_called()

    def test_agent_dry_run_routes_deny_non_local_review_access(self):
        response = self.client.get(
            "/api/oom-sakkie/agent-dry-runs",
            environ_base={"REMOTE_ADDR": "203.0.113.10"},
        )
        data = response.get_json()

        self.assertEqual(response.status_code, 403)
        self.assertEqual(data["status"], "review_access_denied")

        response = self.client.get(
            "/api/oom-sakkie/agent-dry-run-results/OSK-AGENT-DRYRUN-RESULT-1/review-packet",
            environ_base={"REMOTE_ADDR": "203.0.113.10"},
        )
        data = response.get_json()

        self.assertEqual(response.status_code, 403)
        self.assertEqual(data["status"], "review_access_denied")

        response = self.client.get(
            "/api/oom-sakkie/agent-dry-run-results",
            environ_base={"REMOTE_ADDR": "203.0.113.10"},
        )
        data = response.get_json()

        self.assertEqual(response.status_code, 403)
        self.assertEqual(data["status"], "review_access_denied")

        response = self.client.post(
            "/api/oom-sakkie/agent-dry-runs/handoff",
            json={"dry_run_request_id": "OSK-AGENT-DRYRUN-1"},
            environ_base={"REMOTE_ADDR": "203.0.113.10"},
        )
        data = response.get_json()

        self.assertEqual(response.status_code, 403)
        self.assertEqual(data["status"], "review_access_denied")

    @patch("modules.oom_sakkie.service.write_trace", return_value={"stored": False, "status": "test"})
    def test_message_can_answer_agent_crew_status_without_dispatch(self, _write_trace):
        response = self.client.post(
            "/api/oom-sakkie/message",
            json={"text": "which agent should handle a marketing post?", "channel": "kiosk"},
        )
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["success"])
        self.assertEqual(data["tool_used"], "agent_crew_status")
        self.assertEqual(data["risk_level"], 0)
        self.assertIn("No specialist was dispatched", " ".join(data["safety_notes"]))
        self.assertFalse(data["needs_clarification"])

    @patch("modules.oom_sakkie.routes.get_review_advisor")
    def test_review_advisor_route_is_advisory_only(self, mock_advisor):
        mock_advisor.return_value = ({
            "success": True,
            "mode": "advisory_only",
            "autonomous_marking_enabled": False,
            "writes_feedback": False,
            "review_queue": [],
            "suggested_actions": [],
        }, 200)

        response = self.client.get("/api/oom-sakkie/review-advisor?channel=kiosk&days=14")
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["success"])
        self.assertEqual(data["mode"], "advisory_only")
        self.assertFalse(data["autonomous_marking_enabled"])
        self.assertFalse(data["writes_feedback"])
        mock_advisor.assert_called_once_with(channel="kiosk", days="14", limit=12)

    def test_review_advisor_route_denies_non_local_review_access(self):
        response = self.client.get(
            "/api/oom-sakkie/review-advisor",
            environ_base={"REMOTE_ADDR": "203.0.113.10"},
        )
        data = response.get_json()

        self.assertEqual(response.status_code, 403)
        self.assertEqual(data["status"], "review_access_denied")

    @patch("modules.oom_sakkie.routes.get_learning_advisor")
    def test_learning_advisor_route_is_advisory_only(self, mock_learning):
        mock_learning.return_value = ({
            "success": True,
            "mode": "advisory_only",
            "writes_code": False,
            "writes_feedback": False,
            "runs_llm": False,
            "requires_human_approval": True,
            "proposals": [],
        }, 200)

        response = self.client.get("/api/oom-sakkie/learning-advisor?channel=kiosk&days=14")
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["success"])
        self.assertEqual(data["mode"], "advisory_only")
        self.assertFalse(data["writes_code"])
        self.assertFalse(data["writes_feedback"])
        self.assertFalse(data["runs_llm"])
        self.assertTrue(data["requires_human_approval"])
        mock_learning.assert_called_once_with(channel="kiosk", days="14", limit=12)

    def test_learning_advisor_route_denies_non_local_review_access(self):
        response = self.client.get(
            "/api/oom-sakkie/learning-advisor",
            environ_base={"REMOTE_ADDR": "203.0.113.10"},
        )
        data = response.get_json()

        self.assertEqual(response.status_code, 403)
        self.assertEqual(data["status"], "review_access_denied")

    @patch("modules.oom_sakkie.routes.run_learning_analysis")
    def test_learning_analysis_route_is_explicit_post_and_advisory(self, mock_analysis):
        mock_analysis.return_value = ({
            "success": True,
            "mode": "advisory_only",
            "writes_code": False,
            "writes_feedback": False,
            "runs_llm": True,
            "requires_human_approval": True,
            "llm_proposals": [],
        }, 200)

        response = self.client.post(
            "/api/oom-sakkie/learning-advisor/analyze",
            json={"channel": "kiosk", "days": 14},
        )
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["success"])
        self.assertEqual(data["mode"], "advisory_only")
        self.assertFalse(data["writes_code"])
        self.assertFalse(data["writes_feedback"])
        self.assertTrue(data["requires_human_approval"])
        mock_analysis.assert_called_once_with(channel="kiosk", days=14, limit=12)

    def test_learning_analysis_route_denies_non_local_review_access(self):
        response = self.client.post(
            "/api/oom-sakkie/learning-advisor/analyze",
            json={"channel": "kiosk"},
            environ_base={"REMOTE_ADDR": "203.0.113.10"},
        )
        data = response.get_json()

        self.assertEqual(response.status_code, 403)
        self.assertEqual(data["status"], "review_access_denied")

    def test_learning_build_packet_route_is_advisory_only(self):
        response = self.client.post(
            "/api/oom-sakkie/learning-advisor/build-packet",
            json={
                "proposal": {
                    "kind": "routing_review",
                    "priority": "high",
                    "title": "Review routing aliases",
                    "evidence": "Owner phrase routed to clarification.",
                    "recommended_action": "Add one deterministic alias and test.",
                }
            },
        )
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["success"])
        self.assertEqual(data["mode"], "build_brief_only")
        self.assertFalse(data["writes_code"])
        self.assertFalse(data["applies_changes"])
        self.assertFalse(data["runs_llm"])
        self.assertFalse(data["writes_feedback"])
        self.assertTrue(data["requires_human_approval"])
        self.assertIn("Oom Sakkie Learning Build Brief", data["brief"])

    def test_learning_build_packet_route_denies_non_local_review_access(self):
        response = self.client.post(
            "/api/oom-sakkie/learning-advisor/build-packet",
            json={"proposal": {"kind": "routing_review"}},
            environ_base={"REMOTE_ADDR": "203.0.113.10"},
        )
        data = response.get_json()

        self.assertEqual(response.status_code, 403)
        self.assertEqual(data["status"], "review_access_denied")

    @patch("modules.oom_sakkie.routes.get_implementation_queue")
    def test_implementation_queue_route_is_review_only_and_does_not_apply_changes(self, mock_queue):
        mock_queue.return_value = ({
            "success": True,
            "mode": "auto_prepared_review_queue",
            "auto_prepare_policy": {
                "writes_code": False,
                "applies_changes": False,
                "runs_llm": False,
                "requires_human_approval": True,
            },
            "packets": [],
        }, 200)

        response = self.client.get("/api/oom-sakkie/learning-advisor/implementation-queue?channel=kiosk&days=14")
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["success"])
        self.assertEqual(data["mode"], "auto_prepared_review_queue")
        self.assertFalse(data["auto_prepare_policy"]["writes_code"])
        self.assertFalse(data["auto_prepare_policy"]["applies_changes"])
        self.assertFalse(data["auto_prepare_policy"]["runs_llm"])
        self.assertTrue(data["auto_prepare_policy"]["requires_human_approval"])
        mock_queue.assert_called_once_with(channel="kiosk", days="14", limit=12)

    def test_implementation_queue_route_denies_non_local_review_access(self):
        response = self.client.get(
            "/api/oom-sakkie/learning-advisor/implementation-queue",
            environ_base={"REMOTE_ADDR": "203.0.113.10"},
        )
        data = response.get_json()

        self.assertEqual(response.status_code, 403)
        self.assertEqual(data["status"], "review_access_denied")

    @patch("modules.oom_sakkie.routes.record_build_request_event")
    @patch("modules.oom_sakkie.routes.record_build_request")
    def test_approve_build_route_creates_non_applying_request(self, mock_record, mock_event):
        mock_record.return_value = ({
            "stored": True,
            "configured": True,
            "status": "ok",
            "build_request_id": "OSK-BUILD-TEST",
        }, 201)
        mock_event.return_value = ({
            "success": True,
            "configured": True,
            "status": "ok",
            "event_type": "approved",
        }, 201)
        packet = {
            "success": True,
            "mode": "build_brief_only",
            "writes_code": False,
            "applies_changes": False,
            "proposal": {
                "kind": "routing_review",
                "priority": "high",
                "title": "Review routing aliases",
                "evidence": "Two wrong-tool traces.",
                "recommended_action": "Add one deterministic alias.",
            },
            "brief": "# Brief",
            "recommended_files": ["modules/oom_sakkie/service.py"],
            "verification": ["python -m unittest tests.test_oom_sakkie_service"],
        }

        response = self.client.post(
            "/api/oom-sakkie/learning-advisor/approve-build",
            json={"packet": packet, "approved_by": "owner"},
        )
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["success"])
        self.assertEqual(data["status"], "approved_for_build")
        self.assertEqual(data["mode"], "build_request_only")
        self.assertFalse(data["builder_enabled"])
        self.assertFalse(data["writes_code_now"])
        self.assertFalse(data["applies_changes_now"])
        self.assertEqual(data["requires_next_gate"], "builder_agent_review_and_patch_approval")
        self.assertEqual(data["build_request_store"]["status"], "ok")
        self.assertEqual(data["build_request_event"]["event_type"], "approved")
        mock_record.assert_called_once()
        mock_event.assert_called_once()

    def test_approve_build_route_denies_non_local_review_access(self):
        response = self.client.post(
            "/api/oom-sakkie/learning-advisor/approve-build",
            json={"packet": {"success": True}},
            environ_base={"REMOTE_ADDR": "203.0.113.10"},
        )
        data = response.get_json()

        self.assertEqual(response.status_code, 403)
        self.assertEqual(data["status"], "review_access_denied")

    @patch("modules.oom_sakkie.routes.list_build_requests")
    def test_build_requests_route_returns_persistent_queue(self, mock_list):
        mock_list.return_value = ({
            "success": True,
            "configured": True,
            "status": "ok",
            "build_requests": [{
                "build_request_id": "OSK-BUILD-TEST",
                "status": "approved_for_build",
                "mode": "build_request_only",
                "builder_enabled": False,
                "writes_code_now": False,
                "applies_changes_now": False,
            }],
        }, 200)

        response = self.client.get("/api/oom-sakkie/build-requests?limit=8")
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["success"])
        self.assertEqual(data["build_requests"][0]["status"], "approved_for_build")
        self.assertFalse(data["build_requests"][0]["builder_enabled"])
        mock_list.assert_called_once_with(limit="8")

    def test_build_requests_route_denies_non_local_review_access(self):
        response = self.client.get(
            "/api/oom-sakkie/build-requests",
            environ_base={"REMOTE_ADDR": "203.0.113.10"},
        )
        data = response.get_json()

        self.assertEqual(response.status_code, 403)
        self.assertEqual(data["status"], "review_access_denied")

    @patch("modules.oom_sakkie.routes.record_build_request_event")
    def test_build_request_event_route_records_append_only_event(self, mock_event):
        mock_event.return_value = ({
            "success": True,
            "configured": True,
            "status": "ok",
            "build_request_id": "OSK-BUILD-TEST",
            "event_type": "ignored",
        }, 201)

        response = self.client.post(
            "/api/oom-sakkie/build-requests/OSK-BUILD-TEST/events",
            json={"event_type": "ignored", "notes": "Smoke request.", "recorded_by": "owner"},
        )
        data = response.get_json()

        self.assertEqual(response.status_code, 201)
        self.assertTrue(data["success"])
        self.assertEqual(data["event_type"], "ignored")
        mock_event.assert_called_once_with("OSK-BUILD-TEST", {
            "event_type": "ignored",
            "notes": "Smoke request.",
            "recorded_by": "owner",
        })

    def test_build_request_event_route_denies_non_local_review_access(self):
        response = self.client.post(
            "/api/oom-sakkie/build-requests/OSK-BUILD-TEST/events",
            json={"event_type": "ignored"},
            environ_base={"REMOTE_ADDR": "203.0.113.10"},
        )
        data = response.get_json()

        self.assertEqual(response.status_code, 403)
        self.assertEqual(data["status"], "review_access_denied")

    @patch("modules.oom_sakkie.routes.get_build_request")
    def test_forge_handoff_route_returns_non_executing_packet(self, mock_get_request):
        mock_get_request.return_value = ({
            "success": True,
            "configured": True,
            "status": "ok",
            "build_request": {
                "build_request_id": "OSK-BUILD-TEST",
                "status": "approved_for_build",
                "mode": "build_request_only",
                "approved_by": "owner",
                "builder_enabled": False,
                "writes_code_now": False,
                "applies_changes_now": False,
                "proposal": {
                    "title": "Review routing aliases",
                    "evidence": "Two traces.",
                    "recommended_action": "Add one alias.",
                },
                "brief": "# Brief",
                "recommended_files": ["modules/oom_sakkie/service.py"],
                "verification": ["python -m unittest tests.test_oom_sakkie_service"],
            },
        }, 200)

        response = self.client.post(
            "/api/oom-sakkie/build-requests/forge-handoff",
            json={"build_request_id": "OSK-BUILD-TEST"},
        )
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["success"])
        self.assertEqual(data["mode"], "forge_handoff_only")
        self.assertFalse(data["runs_builder"])
        self.assertFalse(data["writes_code"])
        self.assertFalse(data["applies_changes"])
        self.assertFalse(data["deploys"])
        self.assertIn("Do not change code yet", data["prompt"])
        mock_get_request.assert_called_once_with("OSK-BUILD-TEST")

    @patch("modules.oom_sakkie.routes.get_build_request")
    def test_forge_handoff_route_requires_persisted_build_request(self, mock_get_request):
        mock_get_request.return_value = ({
            "success": False,
            "configured": True,
            "status": "build_request_not_found",
            "build_request_id": "OSK-BUILD-FAKE",
        }, 404)

        response = self.client.post(
            "/api/oom-sakkie/build-requests/forge-handoff",
            json={"build_request_id": "OSK-BUILD-FAKE"},
        )
        data = response.get_json()

        self.assertEqual(response.status_code, 404)
        self.assertFalse(data["success"])
        self.assertEqual(data["status"], "build_request_not_found")

    def test_forge_handoff_route_denies_non_local_review_access(self):
        response = self.client.post(
            "/api/oom-sakkie/build-requests/forge-handoff",
            json={"build_request_id": "OSK-BUILD-TEST"},
            environ_base={"REMOTE_ADDR": "203.0.113.10"},
        )
        data = response.get_json()

        self.assertEqual(response.status_code, 403)
        self.assertEqual(data["status"], "review_access_denied")

    @patch("modules.oom_sakkie.routes.record_patch_proposal")
    def test_patch_proposal_route_records_review_only_proposal(self, mock_record):
        mock_record.return_value = ({
            "success": True,
            "configured": True,
            "status": "ok",
            "mode": "patch_proposal_review_only",
            "patch_proposal_id": "OSK-PATCH-TEST",
            "build_request_id": "OSK-BUILD-TEST",
            "applies_patch": False,
            "deploys": False,
        }, 201)

        response = self.client.post(
            "/api/oom-sakkie/build-requests/OSK-BUILD-TEST/patch-proposals",
            json={"proposal_text": "Plan only.", "proposed_by": "builder"},
        )
        data = response.get_json()

        self.assertEqual(response.status_code, 201)
        self.assertTrue(data["success"])
        self.assertEqual(data["mode"], "patch_proposal_review_only")
        self.assertFalse(data["applies_patch"])
        self.assertFalse(data["deploys"])
        mock_record.assert_called_once_with("OSK-BUILD-TEST", {
            "proposal_text": "Plan only.",
            "proposed_by": "builder",
        })

    def test_patch_proposal_route_denies_non_local_review_access(self):
        response = self.client.post(
            "/api/oom-sakkie/build-requests/OSK-BUILD-TEST/patch-proposals",
            json={"proposal_text": "Plan only."},
            environ_base={"REMOTE_ADDR": "203.0.113.10"},
        )
        data = response.get_json()

        self.assertEqual(response.status_code, 403)
        self.assertEqual(data["status"], "review_access_denied")

    @patch("modules.oom_sakkie.routes.list_patch_proposals")
    def test_patch_proposals_route_lists_review_only_queue(self, mock_list):
        mock_list.return_value = ({
            "success": True,
            "configured": True,
            "status": "ok",
            "mode": "patch_proposal_review_only",
            "applies_patches": False,
            "deploys": False,
            "patch_proposals": [],
        }, 200)

        response = self.client.get("/api/oom-sakkie/patch-proposals?build_request_id=OSK-BUILD-TEST&limit=8")
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["success"])
        self.assertEqual(data["mode"], "patch_proposal_review_only")
        self.assertFalse(data["applies_patches"])
        self.assertFalse(data["deploys"])
        mock_list.assert_called_once_with(build_request_id="OSK-BUILD-TEST", limit="8")

    @patch("modules.oom_sakkie.routes.record_patch_proposal_event")
    def test_patch_proposal_event_route_records_review_decision(self, mock_event):
        mock_event.return_value = ({
            "success": True,
            "configured": True,
            "status": "ok",
            "event_type": "approved_for_patch",
            "applies_patch": False,
            "deploys": False,
        }, 201)

        response = self.client.post(
            "/api/oom-sakkie/patch-proposals/OSK-PATCH-TEST/events",
            json={"event_type": "approved_for_patch", "notes": "Approved manually.", "recorded_by": "owner"},
        )
        data = response.get_json()

        self.assertEqual(response.status_code, 201)
        self.assertTrue(data["success"])
        self.assertEqual(data["event_type"], "approved_for_patch")
        self.assertFalse(data["applies_patch"])
        self.assertFalse(data["deploys"])
        mock_event.assert_called_once_with("OSK-PATCH-TEST", {
            "event_type": "approved_for_patch",
            "notes": "Approved manually.",
            "recorded_by": "owner",
        })

    def test_patch_proposal_event_route_denies_non_local_review_access(self):
        response = self.client.post(
            "/api/oom-sakkie/patch-proposals/OSK-PATCH-TEST/events",
            json={"event_type": "approved_for_patch"},
            environ_base={"REMOTE_ADDR": "203.0.113.10"},
        )
        data = response.get_json()

        self.assertEqual(response.status_code, 403)
        self.assertEqual(data["status"], "review_access_denied")

    @patch("modules.oom_sakkie.routes.record_deploy_decision")
    def test_deploy_decision_route_records_manual_approval_without_deploying(self, mock_record):
        mock_record.return_value = ({
            "success": True,
            "configured": True,
            "status": "ok",
            "mode": "deploy_approval_record_only",
            "decision_type": "approved_for_manual_deploy",
            "runs_deploy": False,
            "deploys_now": False,
        }, 201)

        response = self.client.post(
            "/api/oom-sakkie/patch-proposals/OSK-PATCH-TEST/deploy-decisions",
            json={
                "decision_type": "approved_for_manual_deploy",
                "environment": "local",
                "verification_summary": "450 tests passed.",
            },
        )
        data = response.get_json()

        self.assertEqual(response.status_code, 201)
        self.assertTrue(data["success"])
        self.assertEqual(data["mode"], "deploy_approval_record_only")
        self.assertFalse(data["runs_deploy"])
        self.assertFalse(data["deploys_now"])
        mock_record.assert_called_once_with("OSK-PATCH-TEST", {
            "decision_type": "approved_for_manual_deploy",
            "environment": "local",
            "verification_summary": "450 tests passed.",
        })

    def test_deploy_decision_route_denies_non_local_review_access(self):
        response = self.client.post(
            "/api/oom-sakkie/patch-proposals/OSK-PATCH-TEST/deploy-decisions",
            json={"decision_type": "approved_for_manual_deploy"},
            environ_base={"REMOTE_ADDR": "203.0.113.10"},
        )
        data = response.get_json()

        self.assertEqual(response.status_code, 403)
        self.assertEqual(data["status"], "review_access_denied")

    @patch("modules.oom_sakkie.routes.list_deploy_decisions")
    def test_deploy_decisions_route_lists_record_only_decisions(self, mock_list):
        mock_list.return_value = ({
            "success": True,
            "configured": True,
            "status": "ok",
            "mode": "deploy_approval_record_only",
            "runs_deploy": False,
            "deploys_now": False,
            "deploy_decisions": [],
        }, 200)

        response = self.client.get("/api/oom-sakkie/deploy-decisions?patch_proposal_id=OSK-PATCH-TEST&limit=8")
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["success"])
        self.assertEqual(data["mode"], "deploy_approval_record_only")
        self.assertFalse(data["runs_deploy"])
        self.assertFalse(data["deploys_now"])
        mock_list.assert_called_once_with(patch_proposal_id="OSK-PATCH-TEST", limit="8")

    def test_deploy_decisions_route_denies_non_local_review_access(self):
        response = self.client.get(
            "/api/oom-sakkie/deploy-decisions",
            environ_base={"REMOTE_ADDR": "203.0.113.10"},
        )
        data = response.get_json()

        self.assertEqual(response.status_code, 403)
        self.assertEqual(data["status"], "review_access_denied")

    @patch("modules.oom_sakkie.routes.record_dispatch_request")
    def test_dispatch_request_route_records_no_execution_request(self, mock_record):
        mock_record.return_value = ({
            "success": True,
            "configured": True,
            "status": "ok",
            "mode": "dispatch_decision_request_only",
            "dispatch_request_id": "OSK-DISPATCH-REQ-TEST",
            "specialist_slug": "sentinel",
            "dispatch_enabled": False,
            "runs_specialist_llm": False,
            "runs_specialist_tools": False,
            "writes": False,
            "applies_runtime_change": False,
        }, 201)

        response = self.client.post(
            "/api/oom-sakkie/dispatch-requests",
            json={"specialist_slug": "sentinel", "owner_text": "Design only."},
        )
        data = response.get_json()

        self.assertEqual(response.status_code, 201)
        self.assertTrue(data["success"])
        self.assertEqual(data["mode"], "dispatch_decision_request_only")
        self.assertFalse(data["dispatch_enabled"])
        self.assertFalse(data["runs_specialist_llm"])
        self.assertFalse(data["runs_specialist_tools"])
        self.assertFalse(data["writes"])
        self.assertFalse(data["applies_runtime_change"])
        mock_record.assert_called_once_with({"specialist_slug": "sentinel", "owner_text": "Design only."})

    def test_dispatch_request_route_denies_non_local_review_access(self):
        response = self.client.post(
            "/api/oom-sakkie/dispatch-requests",
            json={"specialist_slug": "sentinel"},
            environ_base={"REMOTE_ADDR": "203.0.113.10"},
        )
        data = response.get_json()

        self.assertEqual(response.status_code, 403)
        self.assertEqual(data["status"], "review_access_denied")

    @patch("modules.oom_sakkie.routes.list_dispatch_requests")
    def test_dispatch_requests_route_lists_no_execution_queue(self, mock_list):
        mock_list.return_value = ({
            "success": True,
            "configured": True,
            "status": "ok",
            "mode": "dispatch_decision_request_queue",
            "dispatch_enabled": False,
            "runs_specialist_llm": False,
            "runs_specialist_tools": False,
            "writes": False,
            "applies_runtime_change": False,
            "dispatch_requests": [],
        }, 200)

        response = self.client.get("/api/oom-sakkie/dispatch-requests?limit=8")
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["success"])
        self.assertEqual(data["mode"], "dispatch_decision_request_queue")
        self.assertFalse(data["dispatch_enabled"])
        self.assertFalse(data["runs_specialist_llm"])
        self.assertFalse(data["runs_specialist_tools"])
        self.assertFalse(data["writes"])
        self.assertFalse(data["applies_runtime_change"])
        mock_list.assert_called_once_with(limit="8")

    @patch("modules.oom_sakkie.routes.record_dispatch_decision")
    def test_dispatch_decision_route_records_review_decision_without_dispatch(self, mock_record):
        mock_record.return_value = ({
            "success": True,
            "configured": True,
            "status": "ok",
            "decision_type": "approved_for_design_review",
            "dispatch_enabled": False,
            "runs_specialist_llm": False,
            "runs_specialist_tools": False,
            "writes": False,
            "applies_runtime_change": False,
        }, 201)

        response = self.client.post(
            "/api/oom-sakkie/dispatch-requests/OSK-DISPATCH-REQ-TEST/decisions",
            json={"decision_type": "approved_for_design_review", "notes": "Design approved."},
        )
        data = response.get_json()

        self.assertEqual(response.status_code, 201)
        self.assertTrue(data["success"])
        self.assertEqual(data["decision_type"], "approved_for_design_review")
        self.assertFalse(data["dispatch_enabled"])
        self.assertFalse(data["runs_specialist_llm"])
        self.assertFalse(data["runs_specialist_tools"])
        self.assertFalse(data["writes"])
        self.assertFalse(data["applies_runtime_change"])
        mock_record.assert_called_once_with("OSK-DISPATCH-REQ-TEST", {
            "decision_type": "approved_for_design_review",
            "notes": "Design approved.",
        })

    def test_dispatch_decision_route_denies_non_local_review_access(self):
        response = self.client.post(
            "/api/oom-sakkie/dispatch-requests/OSK-DISPATCH-REQ-TEST/decisions",
            json={"decision_type": "approved_for_design_review"},
            environ_base={"REMOTE_ADDR": "203.0.113.10"},
        )
        data = response.get_json()

        self.assertEqual(response.status_code, 403)
        self.assertEqual(data["status"], "review_access_denied")

    @patch("modules.oom_sakkie.routes.record_dispatch_execution_approval")
    def test_dispatch_execution_approval_route_records_without_execution(self, mock_record):
        mock_record.return_value = ({
            "success": True,
            "configured": True,
            "status": "ok",
            "mode": "single_dry_run_execution_approval_only",
            "approval_type": "approved_for_single_dry_run_execution",
            "executes_now": False,
            "dispatch_enabled": False,
            "runs_specialist_llm": False,
            "runs_specialist_tools": False,
            "writes": False,
            "applies_runtime_change": False,
            "dispatches_further": False,
        }, 201)

        response = self.client.post(
            "/api/oom-sakkie/dispatch-requests/OSK-DISPATCH-REQ-TEST/execution-approvals",
            json={"approval_type": "approved_for_single_dry_run_execution", "notes": "Owner approves gate design."},
        )
        data = response.get_json()

        self.assertEqual(response.status_code, 201)
        self.assertTrue(data["success"])
        self.assertEqual(data["mode"], "single_dry_run_execution_approval_only")
        self.assertFalse(data["executes_now"])
        self.assertFalse(data["dispatch_enabled"])
        self.assertFalse(data["runs_specialist_llm"])
        self.assertFalse(data["runs_specialist_tools"])
        self.assertFalse(data["writes"])
        self.assertFalse(data["applies_runtime_change"])
        self.assertFalse(data["dispatches_further"])
        mock_record.assert_called_once_with("OSK-DISPATCH-REQ-TEST", {
            "approval_type": "approved_for_single_dry_run_execution",
            "notes": "Owner approves gate design.",
        })

    @patch("modules.oom_sakkie.routes.list_dispatch_execution_approvals")
    def test_dispatch_execution_approval_route_lists_without_execution(self, mock_list):
        mock_list.return_value = ({
            "success": True,
            "configured": True,
            "status": "ok",
            "mode": "single_dry_run_execution_approval_queue",
            "executes_now": False,
            "dispatch_enabled": False,
            "runs_specialist_llm": False,
            "runs_specialist_tools": False,
            "writes": False,
            "applies_runtime_change": False,
            "dispatches_further": False,
            "execution_approvals": [],
        }, 200)

        response = self.client.get("/api/oom-sakkie/dispatch-execution-approvals?dispatch_request_id=OSK-DISPATCH-REQ-TEST&limit=8")
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["success"])
        self.assertEqual(data["mode"], "single_dry_run_execution_approval_queue")
        self.assertFalse(data["executes_now"])
        self.assertFalse(data["dispatch_enabled"])
        self.assertFalse(data["runs_specialist_llm"])
        self.assertFalse(data["runs_specialist_tools"])
        self.assertFalse(data["writes"])
        self.assertFalse(data["applies_runtime_change"])
        self.assertFalse(data["dispatches_further"])
        mock_list.assert_called_once_with(dispatch_request_id="OSK-DISPATCH-REQ-TEST", limit="8")

    @patch("modules.oom_sakkie.routes.record_dispatch_execution_approval_event")
    def test_dispatch_execution_approval_event_route_records_append_only_event(self, mock_record):
        mock_record.return_value = ({
            "success": True,
            "configured": True,
            "status": "ok",
            "event_type": "review_note",
            "executes_now": False,
            "dispatch_enabled": False,
            "runs_specialist_llm": False,
            "runs_specialist_tools": False,
            "writes": False,
            "applies_runtime_change": False,
            "dispatches_further": False,
        }, 201)

        response = self.client.post(
            "/api/oom-sakkie/dispatch-execution-approvals/OSK-DISPATCH-EXEC-APPROVAL-TEST/events",
            json={"event_type": "review_note", "notes": "Still review only."},
        )
        data = response.get_json()

        self.assertEqual(response.status_code, 201)
        self.assertTrue(data["success"])
        self.assertEqual(data["event_type"], "review_note")
        self.assertFalse(data["executes_now"])
        self.assertFalse(data["dispatch_enabled"])
        self.assertFalse(data["runs_specialist_llm"])
        self.assertFalse(data["runs_specialist_tools"])
        self.assertFalse(data["writes"])
        self.assertFalse(data["applies_runtime_change"])
        self.assertFalse(data["dispatches_further"])
        mock_record.assert_called_once_with("OSK-DISPATCH-EXEC-APPROVAL-TEST", {
            "event_type": "review_note",
            "notes": "Still review only.",
        })

    def test_dispatch_execution_approval_route_denies_non_local_review_access(self):
        response = self.client.post(
            "/api/oom-sakkie/dispatch-requests/OSK-DISPATCH-REQ-TEST/execution-approvals",
            json={"approval_type": "approved_for_single_dry_run_execution"},
            environ_base={"REMOTE_ADDR": "203.0.113.10"},
        )
        data = response.get_json()

        self.assertEqual(response.status_code, 403)
        self.assertEqual(data["status"], "review_access_denied")

    @patch("modules.oom_sakkie.routes.run_sentinel_single_shot_dry_run")
    def test_sentinel_single_shot_route_is_explicit_and_review_gated(self, mock_run):
        mock_run.return_value = ({
            "success": True,
            "status": "ok",
            "mode": "single_shot_sentinel_advisory_result",
            "runs_specialist_llm": True,
            "runs_specialist_tools": False,
            "writes": False,
            "applies_runtime_change": False,
            "dispatches_further": False,
        }, 201)

        response = self.client.post(
            "/api/oom-sakkie/dispatch-execution-approvals/OSK-DISPATCH-EXEC-APPROVAL-TEST/run-sentinel-dry-run",
            json={},
        )
        data = response.get_json()

        self.assertEqual(response.status_code, 201)
        self.assertTrue(data["success"])
        self.assertEqual(data["mode"], "single_shot_sentinel_advisory_result")
        self.assertTrue(data["runs_specialist_llm"])
        self.assertFalse(data["runs_specialist_tools"])
        self.assertFalse(data["writes"])
        self.assertFalse(data["applies_runtime_change"])
        self.assertFalse(data["dispatches_further"])
        mock_run.assert_called_once_with("OSK-DISPATCH-EXEC-APPROVAL-TEST")

    def test_sentinel_single_shot_route_denies_non_local_review_access(self):
        response = self.client.post(
            "/api/oom-sakkie/dispatch-execution-approvals/OSK-DISPATCH-EXEC-APPROVAL-TEST/run-sentinel-dry-run",
            json={},
            environ_base={"REMOTE_ADDR": "203.0.113.10"},
        )
        data = response.get_json()

        self.assertEqual(response.status_code, 403)
        self.assertEqual(data["status"], "review_access_denied")

    @patch.dict(os.environ, {}, clear=True)
    def test_message_route_remains_available_for_non_local_access_policy_when_llm_off(self):
        response = self.client.post(
            "/api/oom-sakkie/message",
            json={"text": "what is the power doing now", "channel": "kiosk"},
            environ_base={"REMOTE_ADDR": "203.0.113.10"},
        )

        self.assertNotEqual(response.status_code, 403)

    @patch.dict(os.environ, {"OOM_SAKKIE_LLM_ANSWER_ENABLED": "1"}, clear=True)
    def test_message_route_denies_non_local_access_when_llm_enabled(self):
        response = self.client.post(
            "/api/oom-sakkie/message",
            json={"text": "what is the power doing now", "channel": "kiosk"},
            environ_base={"REMOTE_ADDR": "203.0.113.10"},
        )
        data = response.get_json()

        self.assertEqual(response.status_code, 403)
        self.assertFalse(data["success"])
        self.assertEqual(data["status"], "message_access_denied")
        self.assertTrue(data["llm_guard_active"])

    @patch.dict(os.environ, {"OOM_SAKKIE_LLM_ROUTER_ENABLED": "1"}, clear=True)
    def test_message_route_allows_loopback_when_llm_enabled(self):
        response = self.client.post(
            "/api/oom-sakkie/message",
            json={"text": "what is the power doing now", "channel": "kiosk"},
            environ_base={"REMOTE_ADDR": "127.0.0.1"},
        )

        self.assertNotEqual(response.status_code, 403)

    def test_review_access_policy_is_loopback_by_default(self):
        self.assertTrue(is_review_request_allowed("127.0.0.1"))
        self.assertTrue(is_review_request_allowed("::1"))
        self.assertFalse(is_review_request_allowed(None))
        self.assertFalse(is_review_request_allowed(""))
        self.assertFalse(is_review_request_allowed("192.168.1.44", environ={}))
        self.assertTrue(is_review_request_allowed(
            "192.168.1.44",
            environ={"OOM_SAKKIE_REVIEW_ALLOW_PRIVATE_LAN": "true"},
        ))

    def test_review_access_currently_uses_remote_addr_not_forwarded_for(self):
        response = self.client.get(
            "/api/oom-sakkie/policy",
            environ_base={
                "REMOTE_ADDR": "127.0.0.1",
                "HTTP_X_FORWARDED_FOR": "203.0.113.10",
            },
        )

        self.assertEqual(response.status_code, 200)

        response = self.client.get(
            "/api/oom-sakkie/policy",
            environ_base={
                "REMOTE_ADDR": "203.0.113.10",
                "HTTP_X_FORWARDED_FOR": "127.0.0.1",
            },
        )

        self.assertEqual(response.status_code, 403)


if __name__ == "__main__":
    unittest.main()
