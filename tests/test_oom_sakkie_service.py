import unittest
import os
import json
import tempfile
from urllib import error as urllib_error
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch

from modules.oom_sakkie.policy import get_runtime_policy
from modules.oom_sakkie.voice_stt import (
    backend_voice_stt_policy,
    transcribe_oom_sakkie_voice_audio,
)
from modules.oom_sakkie.telegram_gateway import (
    handle_telegram_gateway_message,
    parse_telegram_gateway_payload,
    telegram_gateway_exposure_preflight,
    telegram_gateway_policy,
    _reset_auth_rate_limit_for_tests,
)
from modules.oom_sakkie.telegram_direct import (
    format_telegram_owner_reply,
    handle_telegram_direct_webhook,
    preview_daily_brief_for_allowed_owners,
    send_daily_brief_to_allowed_owners,
    send_owner_telegram_reply,
    telegram_direct_parity_report,
    telegram_direct_policy,
    _reset_direct_auth_rate_limit_for_tests,
)
from modules.oom_sakkie.agent_runtime import (
    build_agent_crew_brief,
    build_agent_activity,
    get_agent_activation_plan,
    get_agent_activation_preflight,
    get_agent_authority_matrix,
    get_agent_authority_unlock_readiness,
    get_agent_command_center,
    get_agent_dispatch_decision_rail_blueprint,
    get_agent_operating_contracts,
    get_agent_runtime_review_packet,
    get_agent_runtime_readiness,
    get_agent_runtime_status,
    get_jarvis_owner_review_packet,
    get_jarvis_product_progress,
    get_jarvis_safety_gate_board,
    get_learning_influence_consumption_audit_rail_blueprint,
    get_learning_influence_consumption_readiness,
    get_learning_influence_consumer_design_packet,
    find_learning_influence_allow_consumed_callers,
    find_reviewed_learning_influence_allow_consumed_callers,
    _learning_influence_allow_consumed_callers_from_source,
    _is_reviewed_allow_consumed_caller,
    recommend_agent_for_text,
)
from modules.oom_sakkie.agent_dry_run_handoff import build_agent_dry_run_handoff
from modules.oom_sakkie.agent_dry_run_store import (
    _agent_dry_run_request_params,
    _agent_dry_run_request_row,
    allowed_agent_dry_run_slugs,
    get_agent_dry_run_request,
    list_agent_dry_run_requests,
    record_agent_dry_run_event,
    record_agent_dry_run_request,
)
from modules.oom_sakkie.agent_dry_run_result_store import (
    _agent_dry_run_result_params,
    _agent_dry_run_result_row,
    _sentinel_single_shot_result_params,
    get_agent_dry_run_result,
    list_agent_dry_run_results,
    record_sentinel_single_shot_result,
    record_agent_dry_run_result_event,
)
from modules.oom_sakkie.agent_dry_run_result_review import build_agent_dry_run_result_review_packet
from modules.oom_sakkie.llm_answer import (
    _build_payload,
    compose_answer_with_llm,
    parse_llm_answer_response,
)
from modules.oom_sakkie.sentinel_single_shot_runner import (
    parse_sentinel_single_shot_response,
    run_sentinel_single_shot_dry_run,
    specialist_dry_run_policy,
)
from modules.oom_sakkie.sentinel_single_shot_contract import (
    SENTINEL_SINGLE_SHOT_FORBIDDEN_TRUE_FLAGS,
    SENTINEL_SINGLE_SHOT_POLICY_MODE,
    SENTINEL_SINGLE_SHOT_REQUIRED_TRUE_FLAGS,
    SENTINEL_SINGLE_SHOT_RESULT_MODE,
    SENTINEL_SINGLE_SHOT_RESULT_STATUS,
    SENTINEL_SINGLE_SHOT_SPECIALIST,
    sentinel_single_shot_flag_errors,
    sentinel_single_shot_identity,
    sentinel_single_shot_result_flags,
)
from modules.oom_sakkie.learning_advisor import build_learning_advice
from modules.oom_sakkie.learning_llm import analyze_learning_with_llm, parse_learning_response
from modules.oom_sakkie.build_request_store import (
    _build_request_params,
    _build_request_row,
    get_build_request,
    list_build_requests,
    record_build_request_event,
    record_build_request,
)
from modules.oom_sakkie.deploy_decision_store import (
    _deploy_decision_params,
    _deploy_decision_row,
    list_deploy_decisions,
    record_deploy_decision,
)
from modules.oom_sakkie.dispatch_decision_store import (
    DISPATCH_DECISION_TYPES,
    _dispatch_request_params,
    record_dispatch_decision,
    record_dispatch_request,
)
from modules.oom_sakkie.dispatch_execution_approval_store import (
    DISPATCH_EXECUTION_APPROVAL_TYPES,
    _dispatch_execution_approval_params,
    record_dispatch_execution_approval_event,
    record_dispatch_execution_approval,
)
from modules.oom_sakkie.forge_handoff import build_forge_handoff
from modules.oom_sakkie.learning_packet import (
    approve_build_request,
    build_learning_packet,
    get_implementation_queue,
)
from modules.oom_sakkie.learning_influence_store import (
    _learning_influence_params,
    record_learning_influence_proposal_from_result,
    record_learning_influence_proposal_event,
)
from modules.oom_sakkie.learning_influence_consumption_store import (
    _consumption_request_params,
    record_learning_influence_consumption_event,
    record_learning_influence_consumption_request,
)
from modules.oom_sakkie.learning_influence_consumer import produce_learning_influence_review_note_artifact
from modules.oom_sakkie.patch_proposal_store import (
    _patch_proposal_params,
    _patch_proposal_row,
    get_patch_proposal,
    record_patch_proposal,
    record_patch_proposal_event,
    list_patch_proposals,
)
from modules.oom_sakkie.llm_router import LlmRouteResult, parse_llm_route_response, route_with_llm
from modules.oom_sakkie.review_advisor import build_review_advice
from modules.oom_sakkie.service import IntentMatch, classify_intent, handle_message, is_unsupported_action_request
from modules.oom_sakkie.specialists import list_specialist_manifests
from modules.oom_sakkie.trace_store import (
    FEEDBACK_TYPES,
    build_feedback_id,
    build_trace_id,
    _trace_params,
    _trace_row,
    _review_filter,
    _trace_list_where_clause,
    get_trace_review_summary,
    hash_tool_result,
    list_review_advisor_traces,
    list_recent_traces,
    record_trace_feedback,
    write_trace,
)
from modules.oom_sakkie.tools import RiskLevel, TOOL_REGISTRY, list_tool_catalog


TELEGRAM_TEST_TOKEN = "test-telegram-token-32-chars-minimum"
TELEGRAM_DIRECT_SECRET = "test-telegram-direct-secret-32-chars"
TELEGRAM_BOT_TOKEN = "1234567890:test-bot-token-for-unit-tests"


def _fake_farm_attention_tool():
    tool = Mock()
    tool.name = "farm_attention_summary"
    tool.risk_level = RiskLevel.READ_ONLY
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


class OomSakkieServiceTests(unittest.TestCase):
    def setUp(self):
        _reset_auth_rate_limit_for_tests()
        _reset_direct_auth_rate_limit_for_tests()

    def test_tool_registry_contract(self):
        self.assertEqual(
            set(TOOL_REGISTRY),
            {
                "sentinel_dry_run_review",
                "agent_dry_run_status",
                "agent_learning_evidence",
                "learning_influence_status",
                "learning_influence_consumption_readiness",
                "learning_influence_consumption_audit_rail_blueprint",
                "learning_influence_consumer_design_packet",
                "agent_activation_preflight",
                "agent_authority_matrix",
                "agent_authority_unlock_readiness",
                "jarvis_product_progress",
                "jarvis_safety_gate_board",
                "jarvis_owner_review_packet",
                "agent_command_center",
                "jarvis_daily_command_brief",
                "agent_dispatch_decision_rail_blueprint",
                "dispatch_decision_status",
                "agent_runtime_review_packet",
                "dispatch_runtime_review_packet",
                "agent_operating_contracts",
                "agent_runtime_readiness",
                "agent_activation_plan",
                "agent_crew_brief",
                "agent_crew_status",
                "system_work_status",
                "farm_operating_brief",
                "business_growth_brief",
                "sales_offer_brief",
                "sales_customer_draft",
                "farm_attention_summary",
                "power_current",
                "power_recent",
                "weather_now",
                "weather_today",
                "weather_forecast",
                "irrigation_status",
                "dashboard_summary",
                "pig_allocation_readiness",
                "meat_planning",
                "sales_dashboard",
            },
        )
        for tool in TOOL_REGISTRY.values():
            with self.subTest(tool=tool.name):
                expected_risk = RiskLevel.DRAFT_ONLY if tool.name == "sales_customer_draft" else RiskLevel.READ_ONLY
                self.assertEqual(tool.risk_level, expected_risk)
                self.assertFalse(tool.requires_confirmation)
                self.assertEqual(tool.input_schema["type"], "object")
                self.assertEqual(tool.output_schema["type"], "object")
                self.assertTrue(callable(tool.handler))

    def test_tool_catalog_serializes_runtime_registry(self):
        catalog = list_tool_catalog()
        names = {item["name"] for item in catalog}

        self.assertEqual(names, set(TOOL_REGISTRY))
        irrigation = next(item for item in catalog if item["name"] == "irrigation_status")
        self.assertEqual(irrigation["risk_level"], 0)
        self.assertEqual(irrigation["risk_label"], "READ_ONLY")
        self.assertFalse(irrigation["requires_confirmation"])
        self.assertIn("Never starts or stops irrigation", irrigation["description"])
        self.assertEqual(irrigation["input_schema"]["additionalProperties"], False)
        draft = next(item for item in catalog if item["name"] == "sales_customer_draft")
        self.assertEqual(draft["risk_level"], 1)
        self.assertEqual(draft["risk_label"], "DRAFT_ONLY")
        self.assertFalse(draft["requires_confirmation"])

    @patch.dict(os.environ, {}, clear=True)
    def test_runtime_policy_is_read_only_local_kiosk(self):
        policy = get_runtime_policy()

        self.assertTrue(policy["success"])
        self.assertEqual(policy["mode"], "local_kiosk_read_only")
        self.assertTrue(policy["backend_as_brain"])
        self.assertFalse(policy["telegram_cutover_enabled"])
        self.assertFalse(policy["telegram_gateway_enabled"])
        self.assertFalse(policy["telegram_gateway"]["enabled"])
        self.assertFalse(policy["telegram_gateway"]["sends_telegram"])
        self.assertFalse(policy["telegram_direct_enabled"])
        self.assertFalse(policy["telegram_direct"]["enabled"])
        self.assertFalse(policy["telegram_direct"]["sends_telegram"])
        self.assertFalse(policy["llm_answer_enabled"])
        self.assertFalse(policy["llm_router_enabled"])
        self.assertFalse(policy["write_tools_enabled"])
        self.assertFalse(policy["physical_controls_enabled"])
        self.assertFalse(policy["backend_voice_vendors_enabled"])
        self.assertFalse(policy["backend_voice_stt"]["enabled"])
        self.assertFalse(policy["backend_voice_stt"]["stores_audio"])
        self.assertFalse(policy["always_on_mic_enabled"])
        self.assertFalse(policy["llm_router"]["enabled"])
        self.assertFalse(policy["llm_router"]["configured"])
        self.assertFalse(policy["llm_router"]["can_write"])
        self.assertTrue(policy["llm_router"]["sends_user_text_when_enabled"])
        self.assertIn("chat/completions", policy["llm_router"]["outbound_endpoint_when_enabled"])
        self.assertFalse(policy["llm_answer"]["enabled"])
        self.assertFalse(policy["llm_answer"]["configured"])
        self.assertFalse(policy["llm_answer"]["can_write"])
        self.assertTrue(policy["llm_answer"]["sends_user_text_when_enabled"])
        self.assertTrue(policy["llm_answer"]["sends_tool_summary_when_enabled"])
        self.assertTrue(policy["llm_answer"]["sends_capped_tool_context_when_enabled"])
        self.assertEqual(policy["browser_speech_mode"], "push_to_talk_only")
        self.assertEqual(policy["continue_conversation_max_turns"], 5)
        self.assertEqual(policy["voice_auto_send_ms"], 2000)
        self.assertEqual(policy["message_endpoint_access"]["default"], "reachable_wherever_flask_is_reachable")
        self.assertEqual(policy["message_endpoint_access"]["route"], "POST /api/oom-sakkie/message")
        self.assertFalse(policy["message_endpoint_access"]["llm_guard_active"])
        self.assertEqual(
            policy["message_endpoint_access"]["llm_guard_envs"],
            [
                "OOM_SAKKIE_LLM_ROUTER_ENABLED",
                "OOM_SAKKIE_LLM_ANSWER_ENABLED",
                "OOM_SAKKIE_LLM_LEARNING_ENABLED",
            ],
        )
        self.assertIn("reverse_proxy_assumption", policy["review_endpoints_access"])
        self.assertEqual(policy["kiosk_policy"]["max_risk_level"], 1)
        self.assertEqual(policy["kiosk_policy"]["allowed_risk_label"], "DRAFT_ONLY")
        self.assertEqual(policy["kiosk_policy"]["requires_confirmation_tools"], [])
        self.assertEqual(policy["tool_counts"]["draft_only"], 1)
        self.assertEqual(policy["tool_counts"]["write_or_confirmation"], 0)
        self.assertIn("write tools", policy["blocked_capabilities"])
        self.assertIn("backend STT vendors", policy["blocked_capabilities"])
        self.assertIn("Telegram read-only gateway", policy["blocked_capabilities"])
        self.assertIn("Telegram direct owner bot", policy["blocked_capabilities"])

    @patch.dict(os.environ, {"OOM_SAKKIE_STT_ENABLED": "1", "OPENAI_API_KEY": "test-key"}, clear=True)
    def test_runtime_policy_enables_backend_stt_only_as_push_to_talk_fallback(self):
        policy = get_runtime_policy()

        self.assertTrue(policy["backend_voice_vendors_enabled"])
        self.assertTrue(policy["backend_voice_stt"]["enabled"])
        self.assertTrue(policy["backend_voice_stt"]["configured"])
        self.assertEqual(policy["backend_voice_stt"]["mode"], "push_to_talk_backend_stt_fallback")
        self.assertEqual(policy["browser_speech_mode"], "push_to_talk_with_backend_stt_fallback")
        self.assertFalse(policy["backend_voice_stt"]["stores_audio"])
        self.assertFalse(policy["backend_voice_stt"]["always_on_mic_enabled"])
        self.assertFalse(policy["backend_voice_stt"]["writes"])
        self.assertFalse(policy["backend_voice_stt"]["dispatch_enabled"])
        self.assertNotIn("backend STT vendors", policy["blocked_capabilities"])
        self.assertIn("backend TTS vendors", policy["blocked_capabilities"])

    @patch.dict(os.environ, {"OOM_SAKKIE_STT_ENABLED": "1", "OPENAI_API_KEY": "test-key"}, clear=True)
    @patch("modules.oom_sakkie.voice_stt.urllib.request.urlopen")
    def test_backend_voice_stt_transcribes_without_storage_or_writes(self, urlopen):
        response = Mock()
        response.read.return_value = json.dumps({"text": "show me the safety gates"}).encode("utf-8")
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        urlopen.return_value = response
        upload = Mock()
        upload.mimetype = "audio/webm"
        upload.read.return_value = b"fake-audio"

        result, status_code = transcribe_oom_sakkie_voice_audio(upload)

        self.assertEqual(status_code, 200)
        self.assertTrue(result["success"])
        self.assertEqual(result["text"], "show me the safety gates")
        self.assertFalse(result["always_on_mic_enabled"])
        self.assertFalse(result["stores_audio"])
        self.assertFalse(result["writes"])
        self.assertFalse(result["dispatch_enabled"])
        request = urlopen.call_args.args[0]
        self.assertEqual(request.get_method(), "POST")
        self.assertIn("multipart/form-data", request.headers["Content-type"])

    @patch.dict(os.environ, {}, clear=True)
    def test_backend_voice_stt_is_fail_closed_without_explicit_enable(self):
        upload = Mock()
        upload.mimetype = "audio/webm"
        upload.read.return_value = b"fake-audio"

        result, status_code = transcribe_oom_sakkie_voice_audio(upload)

        self.assertEqual(status_code, 503)
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "backend_stt_disabled")
        self.assertFalse(result["backend_voice_stt"]["enabled"])
        self.assertFalse(result["writes"])

        policy = backend_voice_stt_policy()
        self.assertFalse(policy["enabled"])
        self.assertFalse(policy["stores_audio"])

    @patch.dict(os.environ, {
        "OOM_SAKKIE_TELEGRAM_GATEWAY_ENABLED": "1",
        "OOM_SAKKIE_TELEGRAM_GATEWAY_TOKEN": TELEGRAM_TEST_TOKEN,
        "OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS": "12345",
    }, clear=True)
    def test_runtime_policy_reports_read_only_telegram_gateway_when_configured(self):
        policy = get_runtime_policy()

        self.assertFalse(policy["telegram_cutover_enabled"])
        self.assertTrue(policy["telegram_gateway_enabled"])
        self.assertTrue(policy["telegram_gateway"]["enabled"])
        self.assertEqual(policy["telegram_gateway"]["mode"], "read_only_owner_gateway")
        self.assertFalse(policy["telegram_gateway"]["sends_telegram"])
        self.assertTrue(policy["telegram_gateway"]["deterministic_only"])
        self.assertFalse(policy["telegram_gateway"]["can_trigger_outbound_llm"])
        self.assertFalse(policy["telegram_gateway"]["writes"])
        self.assertTrue(policy["telegram_gateway"]["records_audit_trace"])
        self.assertTrue(policy["telegram_gateway"]["token_meets_minimum_entropy"])
        self.assertTrue(policy["telegram_gateway"]["allowed_user_ids_required"])
        self.assertTrue(policy["telegram_gateway"]["allowed_user_ids_configured"])
        self.assertTrue(policy["telegram_gateway"]["auth_rate_limit"]["enabled"])
        self.assertFalse(policy["telegram_gateway"]["dispatch_enabled"])
        self.assertNotIn("Telegram read-only gateway", policy["blocked_capabilities"])

    @patch.dict(os.environ, {
        "OOM_SAKKIE_TELEGRAM_DIRECT_ENABLED": "1",
        "OOM_SAKKIE_TELEGRAM_DIRECT_SEND_ENABLED": "1",
        "OOM_SAKKIE_TELEGRAM_BOT_TOKEN": TELEGRAM_BOT_TOKEN,
        "OOM_SAKKIE_TELEGRAM_WEBHOOK_SECRET": TELEGRAM_DIRECT_SECRET,
        "OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS": "12345",
    }, clear=True)
    def test_runtime_policy_reports_owner_only_direct_telegram_when_configured(self):
        policy = get_runtime_policy()

        self.assertTrue(policy["telegram_cutover_enabled"])
        self.assertTrue(policy["telegram_direct_enabled"])
        self.assertTrue(policy["telegram_direct"]["enabled"])
        self.assertEqual(policy["telegram_direct"]["mode"], "owner_only_direct_telegram_bot")
        self.assertTrue(policy["telegram_direct"]["sends_telegram"])
        self.assertTrue(policy["telegram_direct"]["direct_bot_cutover_enabled"])
        self.assertTrue(policy["telegram_direct"]["deterministic_only"])
        self.assertFalse(policy["telegram_direct"]["can_trigger_outbound_llm"])
        self.assertFalse(policy["telegram_direct"]["writes"])
        self.assertTrue(policy["telegram_direct"]["records_audit_trace"])
        self.assertFalse(policy["telegram_direct"]["dispatch_enabled"])
        self.assertFalse(policy["telegram_direct"]["proactive"]["background_loop_enabled"])
        self.assertNotIn("Telegram direct owner bot", policy["blocked_capabilities"])

    @patch.dict(os.environ, {
        "OOM_SAKKIE_TELEGRAM_DIRECT_ENABLED": "1",
        "OOM_SAKKIE_TELEGRAM_DIRECT_SEND_ENABLED": "1",
        "OOM_SAKKIE_TELEGRAM_BOT_TOKEN": TELEGRAM_BOT_TOKEN,
        "OOM_SAKKIE_TELEGRAM_WEBHOOK_SECRET": TELEGRAM_DIRECT_SECRET,
        "OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS": "12345",
    }, clear=True)
    def test_telegram_direct_parity_report_lists_carried_backend_capabilities(self):
        report = telegram_direct_parity_report()

        self.assertTrue(report["success"])
        self.assertTrue(report["backend_owns_oom_sakkie_chat"])
        self.assertFalse(report["n8n_required_for_oom_sakkie_chat"])
        self.assertIn("Sam sales/order workflows", report["n8n_still_required_for"])
        self.assertIn("farm attention", report["carried_over_backend_capabilities"])
        self.assertIn("daily command brief", report["carried_over_backend_capabilities"])
        self.assertIn("/brief", {item["command"] for item in report["telegram_commands"]})
        self.assertIn("Telegram voice-note transcription", report["not_carried_over_yet"])
        self.assertFalse(report["can_trigger_outbound_llm"])
        self.assertFalse(report["writes"])
        self.assertFalse(report["dispatch_enabled"])

    def test_telegram_gateway_payload_parser_accepts_telegram_update_shape(self):
        parsed = parse_telegram_gateway_payload({
            "message": {
                "text": "what needs attention today",
                "from": {"id": 12345},
                "chat": {"id": 67890},
            },
        })

        self.assertEqual(parsed["text"], "what needs attention today")
        self.assertEqual(parsed["telegram_user_id"], "12345")
        self.assertEqual(parsed["telegram_chat_id"], "67890")
        self.assertEqual(parsed["session_id"], "telegram-67890")

    @patch.dict(os.environ, {}, clear=True)
    def test_telegram_gateway_is_fail_closed_by_default(self):
        result, status_code = handle_telegram_gateway_message({"text": "farm status"}, headers={})

        self.assertEqual(status_code, 503)
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "telegram_gateway_disabled")
        self.assertFalse(result["telegram_gateway"]["enabled"])
        self.assertFalse(result["sends_telegram"])
        self.assertFalse(result["writes"])

        policy = telegram_gateway_policy()
        self.assertFalse(policy["enabled"])
        self.assertFalse(policy["sends_telegram"])

    @patch.dict(os.environ, {
        "OOM_SAKKIE_TELEGRAM_GATEWAY_ENABLED": "1",
        "OOM_SAKKIE_TELEGRAM_GATEWAY_TOKEN": TELEGRAM_TEST_TOKEN,
        "OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS": "12345",
    }, clear=True)
    def test_telegram_gateway_requires_token(self):
        result, status_code = handle_telegram_gateway_message({"text": "farm status"}, headers={})

        self.assertEqual(status_code, 403)
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "telegram_gateway_auth_denied")
        self.assertFalse(result["sends_telegram"])

    @patch.dict(os.environ, {
        "OOM_SAKKIE_TELEGRAM_GATEWAY_ENABLED": "1",
        "OOM_SAKKIE_TELEGRAM_GATEWAY_TOKEN": "short-token",
        "OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS": "12345",
    }, clear=True)
    def test_telegram_gateway_rejects_short_configured_token(self):
        result, status_code = handle_telegram_gateway_message(
            {"text": "farm status", "telegram_user_id": "12345"},
            headers={"Authorization": "Bearer short-token"},
        )

        self.assertEqual(status_code, 503)
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "telegram_gateway_token_too_short")
        self.assertFalse(result["telegram_gateway"]["enabled"])
        self.assertFalse(result["telegram_gateway"]["token_meets_minimum_entropy"])

    @patch.dict(os.environ, {
        "OOM_SAKKIE_TELEGRAM_GATEWAY_ENABLED": "1",
        "OOM_SAKKIE_TELEGRAM_GATEWAY_TOKEN": TELEGRAM_TEST_TOKEN,
    }, clear=True)
    def test_telegram_gateway_requires_allowed_user_list_when_enabled(self):
        result, status_code = handle_telegram_gateway_message(
            {"text": "farm status", "telegram_user_id": "12345"},
            headers={"Authorization": f"Bearer {TELEGRAM_TEST_TOKEN}"},
        )

        self.assertEqual(status_code, 503)
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "telegram_gateway_allowed_user_ids_required")
        self.assertFalse(result["telegram_gateway"]["enabled"])
        self.assertTrue(result["telegram_gateway"]["allowed_user_ids_required"])
        self.assertFalse(result["telegram_gateway"]["allowed_user_ids_configured"])

    @patch.dict(os.environ, {
        "OOM_SAKKIE_TELEGRAM_GATEWAY_ENABLED": "1",
        "OOM_SAKKIE_TELEGRAM_GATEWAY_TOKEN": TELEGRAM_TEST_TOKEN,
        "OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS": "12345",
    }, clear=True)
    @patch("modules.oom_sakkie.telegram_gateway.handle_message")
    def test_telegram_gateway_returns_answer_payload_without_sending_telegram(self, mock_handle):
        mock_handle.return_value = ({
            "success": True,
            "answer": "Read-only farm status.",
            "tool_used": "farm_attention_summary",
            "risk_level": 0,
            "trace_id": "OSK-TRACE-TELEGRAM",
            "safety_notes": ["No write."],
        }, 200)

        result, status_code = handle_telegram_gateway_message(
            {
                "message": {
                    "text": "what needs attention today",
                    "from": {"id": 12345},
                    "chat": {"id": 67890},
                },
            },
            headers={"Authorization": f"Bearer {TELEGRAM_TEST_TOKEN}"},
        )

        self.assertEqual(status_code, 200)
        self.assertTrue(result["success"])
        self.assertEqual(result["answer"], "Read-only farm status.")
        self.assertEqual(result["reply"]["chat_id"], "67890")
        self.assertEqual(result["reply"]["text"], "Read-only farm status.")
        self.assertFalse(result["reply"]["sends_telegram"])
        self.assertFalse(result["sends_telegram"])
        self.assertTrue(result["deterministic_only"])
        self.assertFalse(result["can_trigger_outbound_llm"])
        self.assertFalse(result["writes"])
        self.assertTrue(result["records_audit_trace"])
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
    def test_telegram_gateway_is_deterministic_only_when_llm_surfaces_are_enabled(self, _write_trace, mock_get_tool, mock_route, mock_compose):
        mock_get_tool.return_value = _fake_farm_attention_tool()

        result, status_code = handle_telegram_gateway_message(
            {
                "message": {
                    "text": "what needs attention today",
                    "from": {"id": 12345},
                    "chat": {"id": 67890},
                },
            },
            headers={"Authorization": f"Bearer {TELEGRAM_TEST_TOKEN}"},
        )

        self.assertEqual(status_code, 200)
        self.assertTrue(result["success"])
        self.assertEqual(result["message"]["tool_used"], "farm_attention_summary")
        self.assertEqual(result["message"]["pipeline"]["route_source"], "rule")
        self.assertEqual(result["message"]["pipeline"]["answer_source"], "deterministic")
        self.assertFalse(result["message"]["pipeline"]["llm_router_used"])
        self.assertFalse(result["message"]["pipeline"]["llm_answer_used"])
        self.assertFalse(result["can_trigger_outbound_llm"])
        self.assertFalse(result["sends_telegram"])
        mock_get_tool.assert_called_once_with("farm_attention_summary")
        mock_route.assert_not_called()
        mock_compose.assert_not_called()

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
    @patch("modules.oom_sakkie.service.get_tool")
    @patch("urllib.request.urlopen")
    @patch("modules.oom_sakkie.service.write_trace", return_value={"stored": False, "status": "test"})
    def test_telegram_read_only_channel_makes_no_outbound_http_egress(self, _write_trace, urlopen, mock_get_tool):
        mock_get_tool.return_value = _fake_farm_attention_tool()

        result, status_code = handle_telegram_gateway_message(
            {
                "message": {
                    "text": "what needs attention today",
                    "from": {"id": 12345},
                    "chat": {"id": 67890},
                },
            },
            headers={"Authorization": f"Bearer {TELEGRAM_TEST_TOKEN}"},
        )

        self.assertEqual(status_code, 200)
        self.assertTrue(result["success"])
        self.assertFalse(result["can_trigger_outbound_llm"])
        self.assertEqual(result["message"]["pipeline"]["answer_source"], "deterministic")
        mock_get_tool.assert_called_once_with("farm_attention_summary")
        urlopen.assert_not_called()

    @patch.dict(os.environ, {
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
    def test_telegram_read_only_channel_suppresses_llm_without_gateway(self, _write_trace, mock_get_tool, mock_route, mock_compose):
        mock_get_tool.return_value = _fake_farm_attention_tool()

        result, status_code = handle_message({
            "text": "what needs attention today",
            "channel": "telegram_read_only",
            "session_id": "telegram-direct-test",
        })

        self.assertEqual(status_code, 200)
        self.assertTrue(result["success"])
        self.assertEqual(result["tool_used"], "farm_attention_summary")
        self.assertEqual(result["pipeline"]["answer_source"], "deterministic")
        self.assertFalse(result["pipeline"]["llm_router_used"])
        self.assertFalse(result["pipeline"]["llm_answer_used"])
        mock_get_tool.assert_called_once_with("farm_attention_summary")
        mock_route.assert_not_called()
        mock_compose.assert_not_called()

    @patch.dict(os.environ, {
        "OOM_SAKKIE_TELEGRAM_GATEWAY_ENABLED": "1",
        "OOM_SAKKIE_TELEGRAM_GATEWAY_TOKEN": TELEGRAM_TEST_TOKEN,
        "OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS": "12345",
    }, clear=True)
    def test_telegram_gateway_rejects_unapproved_user_id(self):
        result, status_code = handle_telegram_gateway_message(
            {"text": "farm status", "telegram_user_id": "999"},
            headers={"X-Oom-Sakkie-Telegram-Token": TELEGRAM_TEST_TOKEN},
        )

        self.assertEqual(status_code, 403)
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "telegram_user_not_allowed")
        self.assertFalse(result["sends_telegram"])

    @patch.dict(os.environ, {
        "OOM_SAKKIE_TELEGRAM_GATEWAY_ENABLED": "1",
        "OOM_SAKKIE_TELEGRAM_GATEWAY_TOKEN": TELEGRAM_TEST_TOKEN,
        "OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS": "12345",
    }, clear=True)
    def test_telegram_gateway_rate_limits_repeated_bad_tokens(self):
        for _ in range(8):
            result, status_code = handle_telegram_gateway_message(
                {"text": "farm status", "telegram_user_id": "12345"},
                headers={"Authorization": "Bearer wrong-token"},
            )

        self.assertEqual(status_code, 403)
        self.assertEqual(result["status"], "telegram_gateway_auth_denied")

        locked, locked_status = handle_telegram_gateway_message(
            {"text": "farm status", "telegram_user_id": "12345"},
            headers={"Authorization": f"Bearer {TELEGRAM_TEST_TOKEN}"},
        )

        self.assertEqual(locked_status, 429)
        self.assertFalse(locked["success"])
        self.assertEqual(locked["status"], "telegram_gateway_auth_rate_limited")
        self.assertTrue(locked["telegram_gateway"]["auth_rate_limit"]["locked"])

    @patch.dict(os.environ, {}, clear=True)
    def test_telegram_gateway_exposure_preflight_is_blocked_by_default(self):
        preflight = telegram_gateway_exposure_preflight()

        self.assertEqual(preflight["status"], "blocked")
        self.assertFalse(preflight["private_test_ready"])
        self.assertFalse(preflight["public_exposure_ready"])
        self.assertFalse(preflight["sends_telegram"])
        self.assertFalse(preflight["direct_bot_cutover_enabled"])
        self.assertFalse(preflight["can_trigger_outbound_llm"])
        self.assertFalse(preflight["writes"])
        self.assertTrue(preflight["records_audit_trace"])

    @patch.dict(os.environ, {
        "OOM_SAKKIE_TELEGRAM_GATEWAY_ENABLED": "1",
        "OOM_SAKKIE_TELEGRAM_GATEWAY_TOKEN": TELEGRAM_TEST_TOKEN,
        "OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS": "12345",
    }, clear=True)
    def test_telegram_gateway_exposure_preflight_separates_private_test_from_public_ready(self):
        preflight = telegram_gateway_exposure_preflight()

        self.assertEqual(preflight["status"], "private_test_ready_manual_public_checks_pending")
        self.assertTrue(preflight["private_test_ready"])
        self.assertFalse(preflight["public_exposure_ready"])
        self.assertIn("OOM_SAKKIE_TELEGRAM_TLS_CONFIRMED", preflight["manual_confirm_envs"])
        self.assertIn("OOM_SAKKIE_TELEGRAM_RATE_LIMIT_MODEL_ACCEPTED", preflight["manual_confirm_envs"])
        self.assertTrue(all(item["pass"] for item in preflight["automated_checks"]))
        self.assertFalse(all(item["pass"] for item in preflight["manual_checks"]))
        self.assertIn("in-process and global", preflight["rate_limit_note"])

    @patch.dict(os.environ, {
        "OOM_SAKKIE_TELEGRAM_GATEWAY_ENABLED": "1",
        "OOM_SAKKIE_TELEGRAM_GATEWAY_TOKEN": TELEGRAM_TEST_TOKEN,
        "OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS": "12345",
        "OOM_SAKKIE_TELEGRAM_TLS_CONFIRMED": "1",
        "OOM_SAKKIE_TELEGRAM_RATE_LIMIT_MODEL_ACCEPTED": "1",
    }, clear=True)
    def test_telegram_gateway_exposure_preflight_requires_explicit_public_confirmations(self):
        preflight = telegram_gateway_exposure_preflight()

        self.assertEqual(preflight["status"], "public_exposure_ready")
        self.assertTrue(preflight["private_test_ready"])
        self.assertTrue(preflight["public_exposure_ready"])
        self.assertTrue(all(item["pass"] for item in preflight["automated_checks"]))
        self.assertTrue(all(item["pass"] for item in preflight["manual_checks"]))
        self.assertFalse(preflight["sends_telegram"])
        self.assertFalse(preflight["direct_bot_cutover_enabled"])

    @patch.dict(os.environ, {}, clear=True)
    def test_telegram_direct_is_fail_closed_by_default(self):
        result, status_code = handle_telegram_direct_webhook({"text": "farm status"}, headers={})

        self.assertEqual(status_code, 503)
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "telegram_direct_disabled")
        self.assertFalse(result["telegram_direct"]["enabled"])
        self.assertFalse(result["sends_telegram"])
        self.assertFalse(result["writes"])

        policy = telegram_direct_policy()
        self.assertFalse(policy["enabled"])
        self.assertFalse(policy["sends_telegram"])

    @patch.dict(os.environ, {
        "OOM_SAKKIE_TELEGRAM_DIRECT_ENABLED": "1",
        "OOM_SAKKIE_TELEGRAM_BOT_TOKEN": TELEGRAM_BOT_TOKEN,
        "OOM_SAKKIE_TELEGRAM_WEBHOOK_SECRET": TELEGRAM_DIRECT_SECRET,
        "OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS": "12345",
    }, clear=True)
    def test_telegram_direct_requires_send_enable(self):
        result, status_code = handle_telegram_direct_webhook(
            {"text": "farm status", "telegram_user_id": "12345"},
            headers={"X-Telegram-Bot-Api-Secret-Token": TELEGRAM_DIRECT_SECRET},
        )

        self.assertEqual(status_code, 503)
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "telegram_direct_send_disabled")
        self.assertFalse(result["sends_telegram"])

    @patch.dict(os.environ, {
        "OOM_SAKKIE_TELEGRAM_DIRECT_ENABLED": "1",
        "OOM_SAKKIE_TELEGRAM_DIRECT_SEND_ENABLED": "1",
        "OOM_SAKKIE_TELEGRAM_BOT_TOKEN": TELEGRAM_BOT_TOKEN,
        "OOM_SAKKIE_TELEGRAM_WEBHOOK_SECRET": "short",
        "OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS": "12345",
    }, clear=True)
    def test_telegram_direct_rejects_short_webhook_secret_configuration(self):
        result, status_code = handle_telegram_direct_webhook(
            {"text": "farm status", "telegram_user_id": "12345"},
            headers={"X-Telegram-Bot-Api-Secret-Token": "short"},
        )

        self.assertEqual(status_code, 503)
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "telegram_direct_webhook_secret_too_short")
        self.assertFalse(result["telegram_direct"]["enabled"])

    @patch.dict(os.environ, {
        "OOM_SAKKIE_TELEGRAM_DIRECT_ENABLED": "1",
        "OOM_SAKKIE_TELEGRAM_DIRECT_SEND_ENABLED": "1",
        "OOM_SAKKIE_TELEGRAM_BOT_TOKEN": TELEGRAM_BOT_TOKEN,
        "OOM_SAKKIE_TELEGRAM_WEBHOOK_SECRET": TELEGRAM_DIRECT_SECRET,
        "OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS": "12345",
    }, clear=True)
    def test_telegram_direct_requires_webhook_secret_header(self):
        result, status_code = handle_telegram_direct_webhook(
            {"text": "farm status", "telegram_user_id": "12345"},
            headers={},
        )

        self.assertEqual(status_code, 403)
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "telegram_direct_auth_denied")
        self.assertFalse(result["sends_telegram"])

    @patch.dict(os.environ, {
        "OOM_SAKKIE_TELEGRAM_DIRECT_ENABLED": "1",
        "OOM_SAKKIE_TELEGRAM_DIRECT_SEND_ENABLED": "1",
        "OOM_SAKKIE_TELEGRAM_BOT_TOKEN": TELEGRAM_BOT_TOKEN,
        "OOM_SAKKIE_TELEGRAM_WEBHOOK_SECRET": TELEGRAM_DIRECT_SECRET,
        "OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS": "12345",
    }, clear=True)
    @patch("modules.oom_sakkie.telegram_direct.send_owner_telegram_reply")
    @patch("modules.oom_sakkie.telegram_direct.handle_message")
    def test_telegram_direct_webhook_sends_owner_reply_only_after_answer(self, mock_handle, mock_send):
        mock_handle.return_value = ({
            "success": True,
            "answer": "Read-only owner answer.",
            "tool_used": "farm_attention_summary",
            "risk_level": 0,
            "trace_id": "OSK-TRACE-DIRECT",
            "safety_notes": ["No farm write."],
        }, 200)
        mock_send.return_value = ({
            "success": True,
            "status": "telegram_sent",
            "sends_telegram": True,
            "writes": False,
            "dispatch_enabled": False,
        }, 200)

        result, status_code = handle_telegram_direct_webhook(
            {
                "message": {
                    "text": "what needs attention today",
                    "from": {"id": 12345},
                    "chat": {"id": 67890},
                },
            },
            headers={"X-Telegram-Bot-Api-Secret-Token": TELEGRAM_DIRECT_SECRET},
        )

        self.assertEqual(status_code, 200)
        self.assertTrue(result["success"])
        self.assertEqual(result["status"], "telegram_sent")
        self.assertTrue(result["sends_telegram"])
        self.assertFalse(result["writes"])
        self.assertFalse(result["dispatch_enabled"])
        self.assertFalse(result["can_trigger_outbound_llm"])
        self.assertEqual(result["answer"], "Read-only owner answer.")
        self.assertIn("Oom Sakkie", result["telegram_text"])
        self.assertIn("Read-only owner answer.", result["telegram_text"])
        self.assertIn("No farm/control write", result["telegram_text"])
        mock_handle.assert_called_once_with({
            "text": "what needs attention today",
            "channel": "telegram_read_only",
            "session_id": "telegram-67890",
        })
        mock_send.assert_called_once_with(
            chat_id="67890",
            text=result["telegram_text"],
            environ=None,
        )

    @patch.dict(os.environ, {
        "OOM_SAKKIE_TELEGRAM_DIRECT_ENABLED": "1",
        "OOM_SAKKIE_TELEGRAM_DIRECT_SEND_ENABLED": "1",
        "OOM_SAKKIE_TELEGRAM_BOT_TOKEN": TELEGRAM_BOT_TOKEN,
        "OOM_SAKKIE_TELEGRAM_WEBHOOK_SECRET": TELEGRAM_DIRECT_SECRET,
        "OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS": "12345",
    }, clear=True)
    @patch("modules.oom_sakkie.telegram_direct.send_owner_telegram_reply")
    @patch("modules.oom_sakkie.telegram_direct.handle_message")
    def test_telegram_direct_help_menu_does_not_call_core_message_handler(self, mock_handle, mock_send):
        mock_send.return_value = ({"success": True, "status": "telegram_sent", "sends_telegram": True}, 200)

        result, status_code = handle_telegram_direct_webhook(
            {
                "message": {
                    "text": "/help",
                    "from": {"id": 12345},
                    "chat": {"id": 67890},
                },
            },
            headers={"X-Telegram-Bot-Api-Secret-Token": TELEGRAM_DIRECT_SECRET},
        )

        self.assertEqual(status_code, 200)
        self.assertTrue(result["success"])
        self.assertIn("/brief", result["telegram_text"])
        self.assertIn("/attention", result["telegram_text"])
        self.assertFalse(result["can_trigger_outbound_llm"])
        self.assertFalse(result["writes"])
        mock_handle.assert_not_called()
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
    def test_telegram_direct_command_alias_routes_to_backend_tool_prompt(self, mock_handle, mock_send):
        mock_handle.return_value = ({
            "success": True,
            "answer": "Brief answer.",
            "tool_used": "jarvis_daily_command_brief",
            "risk_level": 0,
            "safety_notes": [],
        }, 200)
        mock_send.return_value = ({"success": True, "status": "telegram_sent", "sends_telegram": True}, 200)

        result, status_code = handle_telegram_direct_webhook(
            {
                "message": {
                    "text": "/brief",
                    "from": {"id": 12345},
                    "chat": {"id": 67890},
                },
            },
            headers={"X-Telegram-Bot-Api-Secret-Token": TELEGRAM_DIRECT_SECRET},
        )

        self.assertEqual(status_code, 200)
        self.assertTrue(result["success"])
        mock_handle.assert_called_once_with({
            "text": "daily command brief",
            "channel": "telegram_read_only",
            "session_id": "telegram-67890",
        })
        self.assertIn("Brief answer.", result["telegram_text"])
        self.assertIn("Check: jarvis_daily_command_brief", result["telegram_text"])

    @patch.dict(os.environ, {
        "OOM_SAKKIE_TELEGRAM_DIRECT_ENABLED": "1",
        "OOM_SAKKIE_TELEGRAM_DIRECT_SEND_ENABLED": "1",
        "OOM_SAKKIE_TELEGRAM_BOT_TOKEN": TELEGRAM_BOT_TOKEN,
        "OOM_SAKKIE_TELEGRAM_WEBHOOK_SECRET": TELEGRAM_DIRECT_SECRET,
        "OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS": "12345",
    }, clear=True)
    @patch("modules.oom_sakkie.telegram_direct.send_owner_telegram_reply")
    @patch("modules.oom_sakkie.telegram_direct.handle_message")
    def test_telegram_direct_offer_command_routes_to_owner_offer_brief(self, mock_handle, mock_send):
        mock_handle.return_value = ({
            "success": True,
            "answer": "Offer brief answer.",
            "tool_used": "sales_offer_brief",
            "risk_level": 0,
            "safety_notes": ["No customer message was sent."],
            "tool_context": {
                "offer_brief": {
                    "mode": "owner_review_draft_only",
                    "angle": "ready-meat preorder check",
                    "target": "Existing meat buyers.",
                    "basis_summary": "tag 22 in D1 at 58.8 kg",
                    "owner_checks": ["Confirm price and exact availability."],
                },
            },
        }, 200)
        mock_send.return_value = ({"success": True, "status": "telegram_sent", "sends_telegram": True}, 200)

        result, status_code = handle_telegram_direct_webhook(
            {
                "message": {
                    "text": "/offer",
                    "from": {"id": 12345},
                    "chat": {"id": 67890},
                },
            },
            headers={"X-Telegram-Bot-Api-Secret-Token": TELEGRAM_DIRECT_SECRET},
        )

        self.assertEqual(status_code, 200)
        self.assertTrue(result["success"])
        mock_handle.assert_called_once_with({
            "text": "sales offer brief",
            "channel": "telegram_read_only",
            "session_id": "telegram-67890",
        })
        self.assertIn("Sales Offer Brief", result["telegram_text"])
        self.assertIn("Owner-review draft only", result["telegram_text"])

    @patch.dict(os.environ, {
        "OOM_SAKKIE_TELEGRAM_DIRECT_ENABLED": "1",
        "OOM_SAKKIE_TELEGRAM_DIRECT_SEND_ENABLED": "1",
        "OOM_SAKKIE_TELEGRAM_BOT_TOKEN": TELEGRAM_BOT_TOKEN,
        "OOM_SAKKIE_TELEGRAM_WEBHOOK_SECRET": TELEGRAM_DIRECT_SECRET,
        "OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS": "12345",
    }, clear=True)
    @patch("modules.oom_sakkie.telegram_direct.send_owner_telegram_reply")
    @patch("modules.oom_sakkie.telegram_direct.handle_message")
    def test_telegram_direct_draft_command_routes_to_customer_draft_without_sending_customer_message(self, mock_handle, mock_send):
        mock_handle.return_value = ({
            "success": True,
            "answer": "Customer draft answer.",
            "tool_used": "sales_customer_draft",
            "risk_level": 1,
            "safety_notes": ["No customer message was sent."],
            "tool_context": {
                "customer_draft": {
                    "mode": "owner_review_customer_copy_draft_only",
                    "draft_type": "buyer_interest_check",
                    "basis_summary": "tag 22 in D1 at 58.8 kg",
                    "message": "Hi [Name], I am checking interest before we process the next small batch.",
                    "owner_checks": ["Confirm price and exact availability before sending."],
                },
            },
        }, 200)
        mock_send.return_value = ({"success": True, "status": "telegram_sent", "sends_telegram": True}, 200)

        result, status_code = handle_telegram_direct_webhook(
            {
                "message": {
                    "text": "/draft",
                    "from": {"id": 12345},
                    "chat": {"id": 67890},
                },
            },
            headers={"X-Telegram-Bot-Api-Secret-Token": TELEGRAM_DIRECT_SECRET},
        )

        self.assertEqual(status_code, 200)
        self.assertTrue(result["success"])
        mock_handle.assert_called_once_with({
            "text": "sales customer draft",
            "channel": "telegram_read_only",
            "session_id": "telegram-67890",
        })
        self.assertIn("Customer Draft", result["telegram_text"])
        self.assertIn("Nothing was sent to customers", result["telegram_text"])

    @patch.dict(os.environ, {
        "OOM_SAKKIE_TELEGRAM_DIRECT_ENABLED": "1",
        "OOM_SAKKIE_TELEGRAM_DIRECT_SEND_ENABLED": "1",
        "OOM_SAKKIE_TELEGRAM_BOT_TOKEN": TELEGRAM_BOT_TOKEN,
        "OOM_SAKKIE_TELEGRAM_WEBHOOK_SECRET": TELEGRAM_DIRECT_SECRET,
        "OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS": "12345",
        "OOM_SAKKIE_LLM_ROUTER_ENABLED": "1",
        "OOM_SAKKIE_LLM_ROUTER_MODEL": "test-router",
        "OOM_SAKKIE_LLM_ANSWER_ENABLED": "1",
        "OOM_SAKKIE_LLM_ANSWER_MODEL": "test-answer",
        "OPENAI_API_KEY": "test-key",
    }, clear=True)
    @patch("modules.oom_sakkie.telegram_direct.send_owner_telegram_reply")
    @patch("modules.oom_sakkie.service.compose_answer_with_llm")
    @patch("modules.oom_sakkie.service.route_with_llm")
    @patch("modules.oom_sakkie.service.get_tool")
    @patch("modules.oom_sakkie.service.write_trace", return_value={"stored": False, "status": "test"})
    def test_telegram_direct_is_deterministic_only_when_llm_surfaces_are_enabled(self, _write_trace, mock_get_tool, mock_route, mock_compose, mock_send):
        mock_get_tool.return_value = _fake_farm_attention_tool()
        mock_send.return_value = ({"success": True, "status": "telegram_sent", "sends_telegram": True}, 200)

        result, status_code = handle_telegram_direct_webhook(
            {
                "message": {
                    "text": "what needs attention today",
                    "from": {"id": 12345},
                    "chat": {"id": 67890},
                },
            },
            headers={"X-Telegram-Bot-Api-Secret-Token": TELEGRAM_DIRECT_SECRET},
        )

        self.assertEqual(status_code, 200)
        self.assertTrue(result["success"])
        self.assertEqual(result["message"]["tool_used"], "farm_attention_summary")
        self.assertFalse(result["message"]["pipeline"]["llm_router_used"])
        self.assertFalse(result["message"]["pipeline"]["llm_answer_used"])
        self.assertFalse(result["can_trigger_outbound_llm"])
        mock_get_tool.assert_called_once_with("farm_attention_summary")
        mock_route.assert_not_called()
        mock_compose.assert_not_called()
        mock_send.assert_called_once()

    @patch.dict(os.environ, {
        "OOM_SAKKIE_TELEGRAM_DIRECT_ENABLED": "1",
        "OOM_SAKKIE_TELEGRAM_DIRECT_SEND_ENABLED": "1",
        "OOM_SAKKIE_TELEGRAM_BOT_TOKEN": TELEGRAM_BOT_TOKEN,
        "OOM_SAKKIE_TELEGRAM_WEBHOOK_SECRET": TELEGRAM_DIRECT_SECRET,
        "OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS": "12345",
    }, clear=True)
    @patch("modules.oom_sakkie.telegram_direct.urllib_request.urlopen")
    def test_telegram_direct_send_calls_telegram_api_without_leaking_token(self, urlopen):
        response = Mock()
        response.status = 200
        response.read.return_value = json.dumps({"ok": True, "result": {"message_id": 42}}).encode("utf-8")
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        urlopen.return_value = response

        result, status_code = send_owner_telegram_reply("67890", "Read-only answer.")

        self.assertEqual(status_code, 200)
        self.assertTrue(result["success"])
        self.assertEqual(result["status"], "telegram_sent")
        self.assertTrue(result["sends_telegram"])
        self.assertFalse(result["writes"])
        self.assertFalse(result["dispatch_enabled"])
        self.assertNotIn(TELEGRAM_BOT_TOKEN, json.dumps(result))
        request = urlopen.call_args.args[0]
        self.assertEqual(request.get_method(), "POST")
        self.assertIn("/sendMessage", request.full_url)
        self.assertIn(TELEGRAM_BOT_TOKEN, request.full_url)
        self.assertNotIn(TELEGRAM_BOT_TOKEN, request.data.decode("utf-8"))

    def test_telegram_owner_reply_format_adds_safety_footer(self):
        text = format_telegram_owner_reply({
            "answer": "Farm status is calm.",
            "tool_used": "farm_attention_summary",
            "safety_notes": ["No write."],
        })

        self.assertIn("Oom Sakkie", text)
        self.assertIn("Farm status is calm.", text)
        self.assertIn("Check: farm_attention_summary", text)
        self.assertIn("- No write.", text)
        self.assertIn("No farm/control write", text)

    def test_telegram_daily_brief_format_uses_compact_structured_sections(self):
        text = format_telegram_owner_reply({
            "answer": "Long paragraph should not be used.",
            "tool_used": "jarvis_daily_command_brief",
            "tool_context": {
                "sections": {
                    "farm": {
                        "llm_context": {
                            "sections": {
                                "attention": {"summary": "No current farm attention items are showing."},
                                "power": {"summary": "Battery: 49%. Load: 699 W."},
                                "weather": {"summary": "Rain today: 0.0 mm."},
                                "irrigation": {"summary": "Current status: IDLE."},
                            },
                        },
                    },
                    "business": {
                        "llm_context": {
                            "counts": {"marketable_sales_stock": 21, "meat_ready_now": 3},
                            "owner_question": "Prepare a draft offer brief?",
                        },
                    },
                    "command_center": {
                        "llm_context": {
                            "command_center": {
                                "overall_percent": 54,
                                "next_gate": "owner and Claude review before live authority",
                            },
                        },
                    },
                },
                "next_actions": ["Review pending approval items."],
            },
        })

        self.assertIn("Daily Command Brief", text)
        self.assertIn("Farm", text)
        self.assertIn("- Attention: No current farm attention items are showing.", text)
        self.assertIn("Business", text)
        self.assertIn("- Marketable stock: 21", text)
        self.assertIn("Command Center", text)
        self.assertIn("- Jarvis progress: 54%", text)
        self.assertNotIn("Long paragraph should not be used.", text)

    def test_telegram_sales_offer_brief_format_is_compact_and_owner_only(self):
        text = format_telegram_owner_reply({
            "answer": "Long paragraph should not be used.",
            "tool_used": "sales_offer_brief",
            "tool_context": {
                "offer_brief": {
                    "mode": "owner_review_draft_only",
                    "angle": "ready-meat preorder check",
                    "target": "Existing meat buyers.",
                    "basis_summary": "tag 22 in D1 at 58.8 kg",
                    "owner_checks": [
                        "Confirm price, cut set, collection/delivery, and exact availability.",
                        "Choose which known buyers should be contacted first.",
                    ],
                    "approval_question": "Should I prepare a later customer-facing draft?",
                },
            },
        })

        self.assertIn("Sales Offer Brief", text)
        self.assertIn("- Mode: owner_review_draft_only", text)
        self.assertIn("- Angle: ready-meat preorder check", text)
        self.assertIn("Owner Checks", text)
        self.assertIn("No customer message", text)
        self.assertNotIn("Long paragraph should not be used.", text)

    def test_telegram_sales_customer_draft_format_is_compact_and_owner_only(self):
        text = format_telegram_owner_reply({
            "answer": "Long paragraph should not be used.",
            "tool_used": "sales_customer_draft",
            "tool_context": {
                "customer_draft": {
                    "mode": "owner_review_customer_copy_draft_only",
                    "draft_type": "buyer_interest_check",
                    "basis_summary": "tag 22 in D1 at 58.8 kg",
                    "message": "Hi [Name], I am checking interest before we process the next small batch.",
                    "owner_checks": [
                        "Confirm price, exact availability, cuts/stock type, timing, and collection/delivery before sending.",
                    ],
                },
            },
        })

        self.assertIn("Customer Draft", text)
        self.assertIn("- Mode: owner_review_customer_copy_draft_only", text)
        self.assertIn("Hi [Name]", text)
        self.assertIn("Owner Checks", text)
        self.assertIn("Nothing was sent to customers", text)
        self.assertNotIn("Long paragraph should not be used.", text)

    @patch.dict(os.environ, {
        "OOM_SAKKIE_TELEGRAM_DIRECT_ENABLED": "1",
        "OOM_SAKKIE_TELEGRAM_DIRECT_SEND_ENABLED": "1",
        "OOM_SAKKIE_TELEGRAM_BOT_TOKEN": TELEGRAM_BOT_TOKEN,
        "OOM_SAKKIE_TELEGRAM_WEBHOOK_SECRET": TELEGRAM_DIRECT_SECRET,
        "OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS": "12345,67890",
    }, clear=True)
    def test_telegram_daily_brief_is_default_off_without_proactive_flags(self):
        result, status_code = send_daily_brief_to_allowed_owners()

        self.assertEqual(status_code, 503)
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "telegram_proactive_disabled")
        self.assertFalse(result["sends_telegram"])
        self.assertFalse(result["writes"])
        self.assertFalse(result["dispatch_enabled"])

    @patch.dict(os.environ, {
        "OOM_SAKKIE_TELEGRAM_DIRECT_ENABLED": "1",
        "OOM_SAKKIE_TELEGRAM_DIRECT_SEND_ENABLED": "1",
        "OOM_SAKKIE_TELEGRAM_PROACTIVE_ENABLED": "1",
        "OOM_SAKKIE_TELEGRAM_DAILY_BRIEF_ENABLED": "1",
        "OOM_SAKKIE_TELEGRAM_BOT_TOKEN": TELEGRAM_BOT_TOKEN,
        "OOM_SAKKIE_TELEGRAM_WEBHOOK_SECRET": TELEGRAM_DIRECT_SECRET,
        "OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS": "12345,67890",
    }, clear=True)
    @patch("modules.oom_sakkie.telegram_direct.send_owner_telegram_reply")
    @patch("modules.oom_sakkie.telegram_direct.handle_message")
    def test_telegram_daily_brief_sends_to_allowed_ids_only_when_enabled(self, mock_handle, mock_send):
        mock_handle.return_value = ({
            "success": True,
            "answer": "Daily command brief.",
            "tool_used": "jarvis_daily_command_brief",
            "risk_level": 0,
            "safety_notes": ["No write."],
        }, 200)
        mock_send.return_value = ({"success": True, "status": "telegram_sent", "sends_telegram": True}, 200)

        result, status_code = send_daily_brief_to_allowed_owners()

        self.assertEqual(status_code, 200)
        self.assertTrue(result["success"])
        self.assertEqual(result["status"], "telegram_daily_brief_sent")
        self.assertEqual(result["delivery_count"], 2)
        self.assertTrue(result["sends_telegram"])
        self.assertFalse(result["can_trigger_outbound_llm"])
        self.assertFalse(result["writes"])
        self.assertFalse(result["dispatch_enabled"])
        mock_handle.assert_called_once_with({
            "text": "daily command brief",
            "channel": "telegram_read_only",
            "session_id": "telegram-proactive-daily-brief",
        })
        self.assertEqual(mock_send.call_count, 2)

    @patch.dict(os.environ, {
        "OOM_SAKKIE_TELEGRAM_DIRECT_ENABLED": "1",
        "OOM_SAKKIE_TELEGRAM_DIRECT_SEND_ENABLED": "1",
        "OOM_SAKKIE_TELEGRAM_PROACTIVE_ENABLED": "1",
        "OOM_SAKKIE_TELEGRAM_DAILY_BRIEF_ENABLED": "1",
        "OOM_SAKKIE_TELEGRAM_BOT_TOKEN": TELEGRAM_BOT_TOKEN,
        "OOM_SAKKIE_TELEGRAM_WEBHOOK_SECRET": TELEGRAM_DIRECT_SECRET,
        "OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS": "12345,67890",
    }, clear=True)
    @patch("modules.oom_sakkie.telegram_direct.handle_message")
    def test_telegram_daily_brief_preview_builds_text_without_sending(self, mock_handle):
        mock_handle.return_value = ({
            "success": True,
            "answer": "Daily command brief.",
            "tool_used": "jarvis_daily_command_brief",
            "risk_level": 0,
            "safety_notes": [],
        }, 200)

        result, status_code = preview_daily_brief_for_allowed_owners()

        self.assertEqual(status_code, 200)
        self.assertTrue(result["success"])
        self.assertEqual(result["status"], "telegram_daily_brief_preview_ready")
        self.assertEqual(result["mode"], "owner_only_direct_telegram_proactive_daily_brief_preview")
        self.assertEqual(result["would_send_to_count"], 2)
        self.assertIn("Oom Sakkie Daily Brief", result["telegram_text"])
        self.assertFalse(result["sends_telegram"])
        self.assertFalse(result["can_trigger_outbound_llm"])
        self.assertFalse(result["writes"])
        self.assertFalse(result["dispatch_enabled"])
        mock_handle.assert_called_once_with({
            "text": "daily command brief",
            "channel": "telegram_read_only",
            "session_id": "telegram-proactive-daily-brief-preview",
        })

    @patch.dict(os.environ, {
        "OOM_SAKKIE_TELEGRAM_DIRECT_ENABLED": "1",
        "OOM_SAKKIE_TELEGRAM_DIRECT_SEND_ENABLED": "1",
        "OOM_SAKKIE_TELEGRAM_BOT_TOKEN": TELEGRAM_BOT_TOKEN,
        "OOM_SAKKIE_TELEGRAM_WEBHOOK_SECRET": TELEGRAM_DIRECT_SECRET,
        "OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS": "12345",
    }, clear=True)
    def test_telegram_direct_rejects_unapproved_user_id_before_send(self):
        result, status_code = handle_telegram_direct_webhook(
            {"text": "farm status", "telegram_user_id": "999", "telegram_chat_id": "999"},
            headers={"X-Telegram-Bot-Api-Secret-Token": TELEGRAM_DIRECT_SECRET},
        )

        self.assertEqual(status_code, 403)
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "telegram_user_not_allowed")
        self.assertFalse(result["sends_telegram"])

    @patch.dict(os.environ, {"OOM_SAKKIE_LLM_ANSWER_ENABLED": "1"}, clear=True)
    def test_runtime_policy_declares_message_guard_when_llm_enabled(self):
        policy = get_runtime_policy()

        self.assertTrue(policy["llm_answer_enabled"])
        self.assertTrue(policy["message_endpoint_access"]["llm_guard_active"])
        self.assertEqual(policy["message_endpoint_access"]["default"], "local_guard_required_when_llm_enabled")
        self.assertIn("outbound API calls", policy["message_endpoint_access"]["llm_guard_rule"])

    @patch.dict(os.environ, {"OOM_SAKKIE_LLM_LEARNING_ENABLED": "true"}, clear=True)
    def test_runtime_policy_uses_same_learning_env_for_message_guard_as_access_layer(self):
        policy = get_runtime_policy()

        self.assertFalse(policy["llm_answer_enabled"])
        self.assertFalse(policy["llm_router_enabled"])
        self.assertTrue(policy["message_endpoint_access"]["llm_guard_active"])
        self.assertEqual(policy["message_endpoint_access"]["default"], "local_guard_required_when_llm_enabled")
        self.assertIn("learning analyst", policy["message_endpoint_access"]["llm_guard_rule"])

    def test_specialist_manifests_are_planned_and_approval_gated(self):
        manifests = list_specialist_manifests()
        names = {item["name"] for item in manifests}
        allowed_modes = {"read_only_advisory", "draft_only", "internal_planning_only"}

        self.assertIn("Sentinel", names)
        self.assertIn("Forge", names)
        self.assertIn("Prism", names)
        self.assertIn("Ledger", names)
        self.assertIn("Rootline", names)
        self.assertIn("Gatekeeper", names)
        for item in manifests:
            with self.subTest(specialist=item["name"]):
                self.assertEqual(item["status"], "planned")
                self.assertLessEqual(item["risk_level"], 1)
                self.assertTrue(item["approval_required_for"])
                self.assertTrue(item["first_inputs"])
                self.assertTrue(item["first_outputs"])
                self.assertIn(item["allowed_mode"], allowed_modes)
                self.assertNotIn("autonomous", item["allowed_mode"])
        beacon = next(item for item in manifests if item["slug"] == "beacon")
        self.assertEqual(beacon["risk_level"], 1)
        self.assertEqual(beacon["allowed_mode"], "draft_only")

    def test_agent_runtime_foundation_is_advisory_only(self):
        status = get_agent_runtime_status()

        self.assertTrue(status["success"])
        self.assertEqual(status["mode"], "advisory_runtime_foundation")
        self.assertFalse(status["runtime_enabled"])
        self.assertFalse(status["dispatch_enabled"])
        self.assertFalse(status["autonomous_loops_enabled"])
        self.assertFalse(status["writes_enabled"])
        self.assertGreaterEqual(status["agent_count"], 8)
        agents = {item["slug"]: item for item in status["agents"]}
        self.assertIn("ledger", agents)
        self.assertIn("butcher", agents)
        self.assertEqual(agents["ledger"]["personality"], "commercially sharp business advisor")
        self.assertIn("business_growth_brief", agents["ledger"]["allowed_tools"])
        self.assertIn("reviewed_traces", agents["ledger"]["memory_sources"])
        for agent in status["agents"]:
            with self.subTest(agent=agent["slug"]):
                self.assertFalse(agent["runtime_enabled"])
                self.assertFalse(agent["dispatch_enabled"])
                self.assertFalse(agent["autonomous_loops_enabled"])
                self.assertLessEqual(agent["risk_limit"], 1)
                self.assertTrue(agent["approval_rules"])

    def test_agent_recommendation_does_not_dispatch(self):
        recommendation = recommend_agent_for_text("Can the business advisor help us make more money from pork?")

        self.assertTrue(recommendation["success"])
        self.assertEqual(recommendation["mode"], "dispatch_recommendation_only")
        self.assertFalse(recommendation["dispatch_enabled"])
        self.assertFalse(recommendation["autonomous_loops_enabled"])
        self.assertFalse(recommendation["runs_agent"])
        self.assertFalse(recommendation["writes"])
        self.assertEqual(recommendation["selected_agent"]["slug"], "ledger")
        self.assertIn("owner_approval", recommendation["next_gate"])

    def test_agent_activation_plan_keeps_runtime_locked(self):
        plan = get_agent_activation_plan()

        self.assertTrue(plan["success"])
        self.assertEqual(plan["mode"], "activation_plan_only")
        self.assertEqual(plan["recommended_next_stage"], "read_only_dry_run")
        self.assertEqual(plan["recommended_first_candidate"]["slug"], "sentinel")
        candidates = {item["slug"]: item for item in plan["first_candidates"]}
        for slug in ["sentinel", "prism", "atlas", "ledger", "rootline", "herdmaster", "butcher", "quartermaster"]:
            with self.subTest(slug=slug):
                self.assertIn(slug, candidates)
                self.assertTrue(candidates[slug]["dry_run_request_allowed"])
                self.assertFalse(candidates[slug]["allowed_now"])
                self.assertTrue(candidates[slug]["requires_owner_approval"])
        self.assertNotIn("beacon", candidates)
        self.assertNotIn("forge", candidates)
        self.assertNotIn("gatekeeper", candidates)
        self.assertFalse(plan["runtime_enabled"])
        self.assertFalse(plan["dispatch_enabled"])
        self.assertFalse(plan["autonomous_loops_enabled"])
        self.assertFalse(plan["writes_enabled"])
        self.assertIn("live specialist dispatch", plan["blocked_capabilities"])
        self.assertIn("farm data writes", plan["blocked_capabilities"])
        self.assertIn("Telegram cutover", plan["blocked_capabilities"])
        self.assertIn("owner_approval", plan["next_gate"])

    def test_agent_runtime_readiness_is_checklist_only(self):
        readiness = get_agent_runtime_readiness()

        self.assertTrue(readiness["success"])
        self.assertEqual(readiness["mode"], "runtime_readiness_checklist_only")
        self.assertFalse(readiness["runtime_enabled"])
        self.assertFalse(readiness["dispatch_enabled"])
        self.assertFalse(readiness["autonomous_loops_enabled"])
        self.assertFalse(readiness["writes_enabled"])
        self.assertFalse(readiness["specialist_llm_enabled"])
        self.assertFalse(readiness["specialist_tools_enabled"])
        self.assertFalse(readiness["public_output_enabled"])
        self.assertFalse(readiness["physical_controls_enabled"])
        self.assertIn("sentinel", readiness["dry_run_candidates"])
        self.assertIn("ledger", readiness["dry_run_candidates"])
        self.assertTrue(any(item["gate"] == "browser_behavior_pass" for item in readiness["manual_gates"]))
        self.assertTrue(any(item["gate"] == "live_specialist_dispatch" for item in readiness["locked_gates"]))
        self.assertIn("owner_review", readiness["next_gate"])

    def test_jarvis_product_progress_is_read_only_planning_status(self):
        progress = get_jarvis_product_progress()

        self.assertTrue(progress["success"])
        self.assertEqual(progress["mode"], "jarvis_product_progress_only")
        self.assertEqual(progress["summary_status"], "foundation_strong_live_authority_locked")
        self.assertGreater(progress["overall_percent"], 0)
        self.assertLess(progress["overall_percent"], 100)
        self.assertFalse(progress["runtime_enabled"])
        self.assertFalse(progress["dispatch_enabled"])
        self.assertFalse(progress["autonomous_loops_enabled"])
        self.assertFalse(progress["writes_enabled"])
        self.assertFalse(progress["specialist_llm_enabled"])
        self.assertFalse(progress["specialist_tools_enabled"])
        self.assertFalse(progress["public_output_enabled"])
        self.assertFalse(progress["physical_controls_enabled"])
        by_area = {item["area"]: item for item in progress["areas"]}
        self.assertGreaterEqual(by_area["foundation_safety_rails"]["percent"], 80)
        self.assertLessEqual(by_area["live_specialist_execution"]["percent"], 25)
        self.assertEqual(progress["next_milestone"]["authority"], "read_only_visibility_only")
        self.assertIn("runtime flags remain false", progress["blocked_until"])
        self.assertIn("owner_and_claude_review", progress["next_gate"])

    def test_jarvis_safety_gate_board_is_read_only_status(self):
        board = get_jarvis_safety_gate_board()

        self.assertTrue(board["success"])
        self.assertEqual(board["mode"], "jarvis_safety_gate_board_only")
        self.assertEqual(board["summary_status"], "ci_gates_configured_live_authority_locked")
        self.assertFalse(board["runtime_enabled"])
        self.assertFalse(board["dispatch_enabled"])
        self.assertFalse(board["autonomous_loops_enabled"])
        self.assertFalse(board["writes_enabled"])
        self.assertFalse(board["specialist_llm_enabled"])
        self.assertFalse(board["specialist_tools_enabled"])
        self.assertFalse(board["public_output_enabled"])
        self.assertFalse(board["physical_controls_enabled"])
        gates = {item["gate"]: item for item in board["gates"]}
        self.assertEqual(gates["audit_rail_ci"]["status"], "configured_owner_reported_green")
        self.assertEqual(gates["browser_behavior_ci"]["status"], "configured_owner_reported_green")
        self.assertEqual(gates["runtime_authority"]["status"], "locked")
        self.assertEqual(gates["external_ci_status"]["status"], "manual_check_required")
        self.assertIn("does not call GitHub", gates["external_ci_status"]["proves"][0])
        self.assertIn("owner_and_claude_review", board["next_gate"])

    def test_jarvis_owner_review_packet_is_read_only_batched_review(self):
        packet = get_jarvis_owner_review_packet()

        self.assertTrue(packet["success"])
        self.assertEqual(packet["mode"], "jarvis_owner_review_packet_only")
        self.assertEqual(packet["summary_status"], "ready_for_batched_owner_claude_review_no_authority_change")
        self.assertFalse(packet["runtime_enabled"])
        self.assertFalse(packet["dispatch_enabled"])
        self.assertFalse(packet["autonomous_loops_enabled"])
        self.assertFalse(packet["writes_enabled"])
        self.assertFalse(packet["specialist_llm_enabled"])
        self.assertFalse(packet["specialist_tools_enabled"])
        self.assertFalse(packet["public_output_enabled"])
        self.assertFalse(packet["physical_controls_enabled"])
        self.assertEqual(packet["payloads"]["jarvis_safety_gate_board"]["mode"], "jarvis_safety_gate_board_only")
        self.assertEqual(packet["payloads"]["agent_runtime_review_packet"]["mode"], "agent_runtime_review_packet_only")
        self.assertIn("CLAUDE_REVIEW_HANDOFF.md", packet["claude_prompt"])
        self.assertEqual(packet["current_review"]["scope"], "Oom Sakkie 10.6 through 10.9EA")
        self.assertIn("10.9EA", packet["current_review"]["scope"])
        self.assertIn("CLAUDE_REVIEW_HANDOFF.md", packet["current_review"]["handoff_file"])
        self.assertTrue(packet["current_review"]["learning_influence_consumer_enabled"])
        self.assertFalse(packet["current_review"]["applies_learning_now"])
        self.assertFalse(packet["current_review"]["changes_prompt_now"])
        self.assertFalse(packet["current_review"]["changes_runtime_now"])
        workflows = {item["workflow"]: item for item in packet["current_review"]["ci_evidence"]}
        self.assertEqual(workflows["Oom Sakkie Browser Behavior"]["status"], "success")
        self.assertEqual(workflows["Oom Sakkie Audit Rails"]["status"], "success")
        self.assertEqual(workflows["Oom Sakkie Browser Behavior"]["recorded_commit"], "381645a")
        self.assertEqual(workflows["Oom Sakkie Audit Rails"]["run_id"], "27489910972")
        self.assertFalse(packet["current_review"]["ci_evidence_policy"]["runtime_calls_github"])
        self.assertFalse(packet["current_review"]["ci_evidence_policy"]["auto_trusts_ci"])
        self.assertIn("may trail newer commits", packet["current_review"]["ci_evidence_policy"]["note"])
        self.assertIn("clicked source result", " ".join(packet["current_review"]["focus"]))
        self.assertIn("review-readiness only", " ".join(packet["current_review"]["focus"]))
        self.assertIn("409 acceptance guard", " ".join(packet["current_review"]["focus"]))
        self.assertIn("threat-model-only", " ".join(packet["current_review"]["focus"]))
        self.assertIn("append-only request/event evidence only", " ".join(packet["current_review"]["focus"]))
        self.assertIn("push-to-talk STT", " ".join(packet["current_review"]["focus"]))
        self.assertIn("Read-only Telegram gateway", " ".join(packet["current_review"]["focus"]))
        self.assertIn("cannot trigger outbound LLM calls", " ".join(packet["current_review"]["focus"]))
        self.assertIn("n8n backend read-only relay contract", " ".join(packet["current_review"]["focus"]))
        self.assertIn("refuses remote plain-HTTP base URLs", " ".join(packet["current_review"]["focus"]))
        self.assertIn("relay import preflight validates", " ".join(packet["current_review"]["focus"]))
        self.assertIn("dry-run Workbench queues", " ".join(packet["current_review"]["focus"]))
        self.assertIn("Telegram live-test path", " ".join(packet["current_review"]["focus"]))
        self.assertIn("manual execution helper", " ".join(packet["current_review"]["focus"]))
        self.assertIn("GateKeeper now targets the uploaded 2.0B", " ".join(packet["current_review"]["focus"]))
        self.assertIn("deployed Render gateway answers safely", " ".join(packet["current_review"]["focus"]))
        self.assertIn("one supervised GateKeeper message test", " ".join(packet["current_review"]["focus"]))
        self.assertIn("removes Code-node $env access", " ".join(packet["current_review"]["focus"]))
        self.assertIn("undefined URL call", " ".join(packet["current_review"]["focus"]))
        self.assertIn("base_url_diagnostic", " ".join(packet["current_review"]["focus"]))
        self.assertIn("direct Telegram", " ".join(packet["current_review"]["focus"]))
        self.assertIn("proactive daily brief", " ".join(packet["current_review"]["focus"]))
        self.assertIn("compact structured Telegram layouts", " ".join(packet["current_review"]["focus"]))
        self.assertIn("Sam keeps Chatwoot/n8n", " ".join(packet["current_review"]["focus"]))
        self.assertIn("Telegram /offer", " ".join(packet["current_review"]["focus"]))
        self.assertIn("--dry-run preview", " ".join(packet["current_review"]["focus"]))
        self.assertIn("Telegram /draft", " ".join(packet["current_review"]["focus"]))
        self.assertEqual(
            packet["payloads"]["learning_influence_consumption_readiness"]["mode"],
            "learning_influence_consumption_readiness_only",
        )
        self.assertFalse(packet["payloads"]["learning_influence_consumption_readiness"]["learning_influence_consumer_enabled"])
        self.assertEqual(
            packet["payloads"]["learning_influence_consumption_audit_rail_blueprint"]["mode"],
            "learning_influence_consumption_audit_rail_blueprint_only",
        )
        self.assertTrue(packet["payloads"]["learning_influence_consumption_audit_rail_blueprint"]["creates_tables_now"])
        self.assertTrue(packet["payloads"]["learning_influence_consumption_audit_rail_blueprint"]["review_note_only_first_slice"])
        self.assertEqual(
            packet["payloads"]["learning_influence_consumer_design_packet"]["mode"],
            "learning_influence_consumer_design_packet_only",
        )
        self.assertEqual(packet["payloads"]["learning_influence_consumer_design_packet"]["allow_consumed_production_callers"], [])
        self.assertTrue(packet["payloads"]["learning_influence_consumer_design_packet"]["learning_influence_consumer_enabled"])
        self.assertIn("Do not treat it as approval", packet["owner_instruction"])
        self.assertIn("review_before_any_runtime_authority_change", packet["next_gate"])

    def test_learning_influence_consumption_readiness_is_threat_model_only(self):
        readiness = get_learning_influence_consumption_readiness()

        self.assertTrue(readiness["success"])
        self.assertEqual(readiness["mode"], "learning_influence_consumption_readiness_only")
        self.assertEqual(readiness["summary_status"], "not_ready_consumer_requires_owner_claude_threat_model")
        self.assertFalse(readiness["runtime_enabled"])
        self.assertFalse(readiness["dispatch_enabled"])
        self.assertFalse(readiness["autonomous_loops_enabled"])
        self.assertFalse(readiness["writes_enabled"])
        self.assertFalse(readiness["specialist_llm_enabled"])
        self.assertFalse(readiness["specialist_tools_enabled"])
        self.assertFalse(readiness["public_output_enabled"])
        self.assertFalse(readiness["physical_controls_enabled"])
        self.assertFalse(readiness["learning_influence_consumer_enabled"])
        self.assertFalse(readiness["applies_learning_now"])
        self.assertFalse(readiness["changes_prompt_now"])
        self.assertFalse(readiness["changes_runtime_now"])
        self.assertGreaterEqual(len(readiness["threat_scenarios"]), 4)
        threats = {item["threat"] for item in readiness["threat_scenarios"]}
        self.assertIn("prompt_or_route_poisoning", threats)
        self.assertIn("authority_creep", threats)
        self.assertIn("evidence_provenance_and_integrity", threats)
        self.assertIn("oversized_or_multi_target_blast_radius", threats)
        self.assertIn("rollback_gap", threats)
        self.assertIn("append_only_consumption_audit_rail", readiness["required_gates"])
        self.assertIn("consumed_once_live_pg_test", readiness["required_gates"])
        self.assertIn("untrusted_proposal_text_policy", readiness["required_gates"])
        self.assertIn("one_target_field_per_consumption", readiness["required_gates"])
        self.assertIn("size_capped_reviewable_diff", readiness["required_gates"])
        self.assertIn("No consumer implementation.", readiness["non_goals"])
        self.assertIn("threat_model_review", readiness["next_gate"])

    def test_learning_influence_consumption_audit_rail_blueprint_is_design_only(self):
        blueprint = get_learning_influence_consumption_audit_rail_blueprint()

        self.assertTrue(blueprint["success"])
        self.assertEqual(blueprint["mode"], "learning_influence_consumption_audit_rail_blueprint_only")
        self.assertEqual(blueprint["summary_status"], "audit_rail_implemented_no_consumption_no_apply")
        self.assertFalse(blueprint["runtime_enabled"])
        self.assertFalse(blueprint["dispatch_enabled"])
        self.assertFalse(blueprint["autonomous_loops_enabled"])
        self.assertFalse(blueprint["writes_enabled"])
        self.assertFalse(blueprint["specialist_llm_enabled"])
        self.assertFalse(blueprint["specialist_tools_enabled"])
        self.assertFalse(blueprint["public_output_enabled"])
        self.assertFalse(blueprint["physical_controls_enabled"])
        self.assertFalse(blueprint["learning_influence_consumer_enabled"])
        self.assertFalse(blueprint["applies_learning_now"])
        self.assertFalse(blueprint["changes_prompt_now"])
        self.assertFalse(blueprint["changes_runtime_now"])
        self.assertTrue(blueprint["creates_tables_now"])
        self.assertTrue(blueprint["adds_routes_now"])
        self.assertTrue(blueprint["review_note_only_first_slice"])
        self.assertEqual(len(blueprint["proposed_tables"]), 2)
        self.assertEqual(blueprint["allowlisted_target_contract"]["first_slice_limit"], "one_target_field_per_consumption")
        self.assertTrue(blueprint["allowlisted_target_contract"]["diff_contract"]["proposal_text_is_untrusted"])
        self.assertEqual(blueprint["allowlisted_target_contract"]["diff_contract"]["max_diff_chars"], 1200)
        self.assertIn("partial unique index", " ".join(blueprint["required_live_pg_tests"]))
        self.assertIn("No proposal consumer.", blueprint["non_goals"])
        self.assertIn("any_learning_consumer_or_patch_diff", blueprint["next_gate"])

    def test_learning_influence_consumer_design_packet_is_review_only(self):
        packet = get_learning_influence_consumer_design_packet()

        self.assertTrue(packet["success"])
        self.assertEqual(packet["mode"], "learning_influence_consumer_design_packet_only")
        self.assertEqual(packet["summary_status"], "review_note_consumer_allowed_no_applyable_diff")
        self.assertFalse(packet["runtime_enabled"])
        self.assertFalse(packet["dispatch_enabled"])
        self.assertFalse(packet["autonomous_loops_enabled"])
        self.assertFalse(packet["writes_enabled"])
        self.assertFalse(packet["specialist_llm_enabled"])
        self.assertFalse(packet["specialist_tools_enabled"])
        self.assertFalse(packet["public_output_enabled"])
        self.assertFalse(packet["physical_controls_enabled"])
        self.assertTrue(packet["learning_influence_consumer_enabled"])
        self.assertFalse(packet["applies_learning_now"])
        self.assertFalse(packet["changes_prompt_now"])
        self.assertFalse(packet["changes_runtime_now"])
        self.assertEqual(packet["allow_consumed_production_callers"], [])
        self.assertEqual(
            packet["reviewed_allow_consumed_production_callers"],
            ["modules/oom_sakkie/learning_influence_consumer.py"],
        )
        self.assertEqual(len(packet["reviewed_allow_consumed_call_sites"]), 1)
        reviewed_call_site = packet["reviewed_allow_consumed_call_sites"][0].replace("\\", "/")
        self.assertTrue(reviewed_call_site.endswith(":keyword"))
        self.assertIn("/modules/oom_sakkie/learning_influence_consumer.py:", reviewed_call_site)
        self.assertEqual(packet["allowed_target_contract"]["first_consumer_output"], "review_note_artifact_only")
        self.assertTrue(packet["allowed_target_contract"]["proposal_text_is_untrusted"])
        self.assertTrue(packet["allowed_target_contract"]["manual_application_outside_kiosk_only"])
        agreement = packet["consumer_design_review_agreement"]
        self.assertEqual(agreement["status"], "owner_approved_review_note_consumer_implemented_no_apply")
        self.assertTrue(agreement["implementation_authorized_now"])
        self.assertTrue(agreement["allow_consumed_true_authorized_now"])
        self.assertEqual(
            agreement["authorized_allow_consumed_true_callers"],
            ["modules/oom_sakkie/learning_influence_consumer.py"],
        )
        self.assertEqual(agreement["review_note_artifact_shape"]["kind"], "review_note_only")
        self.assertIn("source_provenance", agreement["review_note_artifact_shape"]["required_fields"])
        self.assertIn("prompt_patch", agreement["review_note_artifact_shape"]["forbidden_fields"])
        self.assertEqual(
            agreement["must_recheck_before_marker_enforcement"]["ordered_steps"][0],
            "load consumption request by id",
        )
        self.assertIn(
            "write no consumed marker",
            agreement["must_recheck_before_marker_enforcement"]["failure_behavior"],
        )
        self.assertIn(
            "idx_oom_sakkie_learning_consumption_consumed_once",
            agreement["must_recheck_before_marker_enforcement"]["atomicity_guard"],
        )
        self.assertIn(
            "produce no second review-note artifact",
            agreement["must_recheck_before_marker_enforcement"]["unique_violation_behavior"],
        )
        self.assertTrue(agreement["rollback_artifact_contract"]["manual_application_outside_kiosk_only"])
        self.assertTrue(agreement["static_guard_update_required_for_future_consumer"])
        self.assertEqual(
            packet["owner_approval_gate"]["required_before_allow_consumed_true"],
            "approved_for_design_review event on the consumption request",
        )
        self.assertIn("No applyable prompt, route, or runtime diff.", packet["non_goals"])
        guard = next(item for item in packet["static_guards"] if item["guard"] == "no_production_allow_consumed_true")
        self.assertIn("positional fourth argument", guard["purpose"])
        self.assertIn("non-literal-false", guard["purpose"])
        self.assertEqual(guard["current_state"], "single_reviewed_consumer_callsite_allowed")
        apply_guard = next(item for item in packet["static_guards"] if item["guard"] == "consumer_applies_nothing")
        self.assertEqual(apply_guard["current_state"], "review_note_artifact_only")
        self.assertIn("owner_and_claude_review", packet["next_gate"])

    def test_learning_influence_consumption_has_no_production_allow_consumed_true_caller(self):
        self.assertEqual(find_learning_influence_allow_consumed_callers(), [])
        reviewed_callers = find_reviewed_learning_influence_allow_consumed_callers()
        self.assertEqual(len(reviewed_callers), 1)
        reviewed_caller = reviewed_callers[0].replace("\\", "/")
        self.assertTrue(reviewed_caller.endswith(":keyword"))
        self.assertIn("/modules/oom_sakkie/learning_influence_consumer.py:", reviewed_caller)
        self.assertFalse(_is_reviewed_allow_consumed_caller(
            "modules/oom_sakkie/not_modules/oom_sakkie/learning_influence_consumer.py:67:keyword"
        ))

    @patch("modules.oom_sakkie.learning_influence_consumer.record_learning_influence_consumption_event")
    @patch("modules.oom_sakkie.learning_influence_consumer._load_consumption_design_record")
    def test_learning_influence_review_note_consumer_emits_artifact_after_consumed_marker(self, mock_load, mock_event):
        mock_load.return_value = ({
            "success": True,
            "consumption_request_id": "OSK-LEARNING-CONSUME-1",
            "proposal_id": "OSK-LEARNING-INFLUENCE-1",
            "source_result_id": "OSK-AGENT-DRYRUN-RESULT-1",
            "specialist_slug": "sentinel",
            "requested_target_kind": "planning_context_note",
            "requested_target_field": "owner_review_notes",
            "request_note": "Use this as a planning note.",
            "proposal_text": "source proposal text",
            "review_note_artifact": {"source_excerpt": "source excerpt"},
            "request_latest_event": {"event_type": "approved_for_design_review"},
            "proposal_latest_event": {"event_type": "approved_for_future_planning"},
            "has_consumed_marker": False,
        }, 200)
        mock_event.return_value = ({
            "success": True,
            "event_id": "OSK-LEARNING-CONSUME-EVENT-1",
            "event_type": "consumed_for_patch_proposal",
            "applies_learning_now": False,
            "changes_prompt_now": False,
            "changes_runtime_now": False,
            "dispatch_enabled": False,
            "writes": False,
        }, 201)

        result, status = produce_learning_influence_review_note_artifact(
            "OSK-LEARNING-CONSUME-1",
            {"recorded_by": "unittest", "previous_review_note_text": "old note"},
            database_url="postgres://unit",
        )

        self.assertEqual(status, 201)
        self.assertTrue(result["success"])
        self.assertEqual(result["mode"], "learning_influence_review_note_consumer_only")
        self.assertTrue(result["review_note_artifact_only"])
        self.assertEqual(result["review_note_artifact"]["kind"], "review_note_only")
        self.assertEqual(result["review_note_artifact"]["source_provenance"]["proposal_id"], "OSK-LEARNING-INFLUENCE-1")
        self.assertEqual(result["review_note_artifact"]["rollback_artifact"]["previous_review_note_text"], "old note")
        self.assertFalse(result["review_note_artifact"]["changes_prompt_now"])
        self.assertFalse(result["applies_learning_now"])
        self.assertFalse(result["writes"])
        mock_event.assert_called_once()
        self.assertTrue(mock_event.call_args.kwargs["allow_consumed"])

    @patch("modules.oom_sakkie.learning_influence_consumer.record_learning_influence_consumption_event")
    @patch("modules.oom_sakkie.learning_influence_consumer._load_consumption_design_record")
    def test_learning_influence_review_note_consumer_handles_unique_violation_without_second_artifact(self, mock_load, mock_event):
        mock_load.return_value = ({
            "success": True,
            "consumption_request_id": "OSK-LEARNING-CONSUME-1",
            "proposal_id": "OSK-LEARNING-INFLUENCE-1",
            "source_result_id": "OSK-AGENT-DRYRUN-RESULT-1",
            "requested_target_kind": "planning_context_note",
            "requested_target_field": "owner_review_notes",
            "request_latest_event": {"event_type": "approved_for_design_review"},
            "proposal_latest_event": {"event_type": "approved_for_future_planning"},
            "has_consumed_marker": False,
        }, 200)
        mock_event.return_value = ({
            "success": False,
            "status": "learning_influence_consumption_event_write_failed",
            "error_type": "UniqueViolation",
            "applies_learning_now": False,
            "changes_prompt_now": False,
            "changes_runtime_now": False,
            "dispatch_enabled": False,
            "writes": False,
        }, 503)

        result, status = produce_learning_influence_review_note_artifact("OSK-LEARNING-CONSUME-1", database_url="postgres://unit")

        self.assertEqual(status, 409)
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "already_consumed")
        self.assertEqual(result["review_note_artifact"], {})
        self.assertFalse(result["writes"])

    @patch("modules.oom_sakkie.learning_influence_consumer._load_consumption_design_record")
    def test_learning_influence_review_note_consumer_requires_design_approval(self, mock_load):
        mock_load.return_value = ({
            "success": True,
            "consumption_request_id": "OSK-LEARNING-CONSUME-1",
            "requested_target_kind": "planning_context_note",
            "requested_target_field": "owner_review_notes",
            "request_latest_event": {"event_type": "review_note"},
            "proposal_latest_event": {"event_type": "approved_for_future_planning"},
            "has_consumed_marker": False,
        }, 200)

        result, status = produce_learning_influence_review_note_artifact("OSK-LEARNING-CONSUME-1", database_url="postgres://unit")

        self.assertEqual(status, 409)
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "consumption_request_not_approved_for_design_review")
        self.assertFalse(result["changes_runtime_now"])

    def test_learning_influence_allow_consumed_scanner_is_cwd_independent(self):
        original_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            try:
                os.chdir(tmp)
                self.assertEqual(find_learning_influence_allow_consumed_callers(), [])
            finally:
                os.chdir(original_cwd)

    def test_learning_influence_allow_consumed_scanner_reports_parse_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            broken = Path(tmp) / "broken.py"
            broken.write_text("def broken(:\n", encoding="utf-8")

            offenders = find_learning_influence_allow_consumed_callers(root=tmp)

        self.assertEqual(offenders, [f"{broken}:parse_error"])

    def test_learning_influence_allow_consumed_scanner_flags_evasion_patterns(self):
        source = """
from modules.oom_sakkie.learning_influence_consumption_store import record_learning_influence_consumption_event as rec
import modules.oom_sakkie.learning_influence_consumption_store as store
from modules.oom_sakkie import learning_influence_consumption_store as package_store

def direct_var(flag):
    record_learning_influence_consumption_event("REQ", {}, allow_consumed=flag)

def alias_true():
    rec("REQ", {}, allow_consumed=True)

def module_positional():
    store.record_learning_influence_consumption_event("REQ", {}, None, True)

def package_kwargs(options):
    package_store.record_learning_influence_consumption_event("REQ", {}, **options)

def literal_false_is_allowed():
    rec("REQ", {}, allow_consumed=False)
"""
        offenders = _learning_influence_allow_consumed_callers_from_source(source, "synthetic.py")

        self.assertIn("synthetic.py:7:keyword", offenders)
        self.assertIn("synthetic.py:10:keyword", offenders)
        self.assertIn("synthetic.py:13:positional", offenders)
        self.assertIn("synthetic.py:16:kwargs", offenders)
        self.assertFalse(any("19" in item for item in offenders))

    def test_agent_command_center_is_read_only_visibility(self):
        center = get_agent_command_center()

        self.assertTrue(center["success"])
        self.assertEqual(center["mode"], "agent_command_center_only")
        self.assertEqual(center["summary_status"], "read_only_command_center_live_authority_locked")
        self.assertFalse(center["runtime_enabled"])
        self.assertFalse(center["dispatch_enabled"])
        self.assertFalse(center["autonomous_loops_enabled"])
        self.assertFalse(center["writes_enabled"])
        self.assertFalse(center["specialist_llm_enabled"])
        self.assertFalse(center["specialist_tools_enabled"])
        self.assertFalse(center["public_output_enabled"])
        self.assertFalse(center["physical_controls_enabled"])
        lane_slugs = {item["specialist_slug"] for item in center["lanes"]}
        self.assertIn("gatekeeper", lane_slugs)
        self.assertIn("sentinel", lane_slugs)
        self.assertIn("ledger", lane_slugs)
        self.assertTrue(all(item["runs_agent"] is False for item in center["lanes"]))
        self.assertTrue(all(item["writes"] is False for item in center["lanes"]))
        panel_names = {item["panel"] for item in center["panels"]}
        self.assertIn("progress", panel_names)
        self.assertIn("approvals", panel_names)
        self.assertIn("authority_locks", panel_names)
        self.assertIn("safety_gates", panel_names)
        self.assertIn("system_work_status", center["queue_sources"])
        self.assertIn("jarvis_safety_gate_board", center["queue_sources"])
        self.assertIn("owner_and_claude_review", center["next_gate"])

    def test_agent_operating_contracts_are_planning_only(self):
        contracts = get_agent_operating_contracts()

        self.assertTrue(contracts["success"])
        self.assertEqual(contracts["mode"], "agent_operating_contracts_only")
        self.assertFalse(contracts["runtime_enabled"])
        self.assertFalse(contracts["dispatch_enabled"])
        self.assertFalse(contracts["autonomous_loops_enabled"])
        self.assertFalse(contracts["writes_enabled"])
        self.assertFalse(contracts["specialist_llm_enabled"])
        self.assertFalse(contracts["specialist_tools_enabled"])
        self.assertFalse(contracts["public_output_enabled"])
        self.assertFalse(contracts["physical_controls_enabled"])
        self.assertIn("sentinel", contracts["dry_run_allowed"])
        self.assertIn("ledger", contracts["dry_run_allowed"])
        self.assertIn("beacon", contracts["locked_out_of_dry_run"])
        self.assertIn("forge", contracts["locked_out_of_dry_run"])
        self.assertIn("gatekeeper", contracts["locked_out_of_dry_run"])
        by_slug = {item["slug"]: item for item in contracts["contracts"]}
        self.assertIn("send customer messages", by_slug["ledger"]["must_not_do"])
        self.assertIn("start pumps or valves", by_slug["rootline"]["must_not_do"])
        self.assertIn("post publicly", by_slug["beacon"]["must_not_do"])
        for item in contracts["contracts"]:
            with self.subTest(agent=item["slug"]):
                self.assertFalse(item["runtime_enabled"])
                self.assertFalse(item["dispatch_enabled"])
                self.assertFalse(item["writes_enabled"])
                self.assertTrue(item["owner_gate"])

    def test_agent_activation_preflight_is_read_only_and_not_ready_for_dispatch(self):
        preflight = get_agent_activation_preflight()

        self.assertTrue(preflight["success"])
        self.assertEqual(preflight["mode"], "agent_activation_preflight_only")
        self.assertEqual(preflight["summary_status"], "not_ready_for_live_dispatch")
        self.assertFalse(preflight["runtime_enabled"])
        self.assertFalse(preflight["dispatch_enabled"])
        self.assertFalse(preflight["autonomous_loops_enabled"])
        self.assertFalse(preflight["writes_enabled"])
        self.assertFalse(preflight["specialist_llm_enabled"])
        self.assertFalse(preflight["specialist_tools_enabled"])
        self.assertFalse(preflight["public_output_enabled"])
        self.assertFalse(preflight["physical_controls_enabled"])
        self.assertGreaterEqual(preflight["ready_count"], 1)
        self.assertGreaterEqual(preflight["manual_check_count"], 1)
        self.assertGreaterEqual(preflight["locked_count"], 1)
        self.assertIn("beacon", preflight["locked_out_of_dry_run"])
        self.assertIn("sentinel", preflight["dry_run_allowed"])
        self.assertTrue(any(item["check"] == "browser_behavior_smoke" for item in preflight["ready_checks"]))
        self.assertTrue(any(item["check"] == "owner_browser_pass" for item in preflight["manual_checks"]))
        self.assertTrue(any(item["check"] == "live_specialist_dispatch" for item in preflight["locked_checks"]))
        self.assertTrue(any(item["check"] == "physical_controls" for item in preflight["locked_checks"]))
        self.assertIn("claude_and_owner_review", preflight["next_gate"])

    def test_agent_authority_matrix_keeps_authority_disabled_with_single_shot_llm_state(self):
        with patch.dict(os.environ, {
            "OOM_SAKKIE_SPECIALIST_DRYRUN_ENABLED": "",
            "OOM_SAKKIE_LLM_ROUTER_MODEL": "",
            "OPENAI_API_KEY": "",
        }, clear=False):
            matrix = get_agent_authority_matrix()

        self.assertTrue(matrix["success"])
        self.assertEqual(matrix["mode"], "agent_authority_matrix_only")
        self.assertFalse(matrix["runtime_enabled"])
        self.assertFalse(matrix["dispatch_enabled"])
        self.assertFalse(matrix["autonomous_loops_enabled"])
        self.assertFalse(matrix["writes_enabled"])
        self.assertFalse(matrix["specialist_llm_enabled"])
        self.assertFalse(matrix["specialist_tools_enabled"])
        self.assertFalse(matrix["public_output_enabled"])
        self.assertFalse(matrix["physical_controls_enabled"])
        self.assertEqual(matrix["enabled_count"], 0)
        by_authority = {item["authority"]: item for item in matrix["areas"]}
        self.assertEqual(
            matrix["locked_count"],
            len([item for item in matrix["areas"] if item["current_state"] == "locked"]),
        )
        for authority in [
            "live_specialist_dispatch",
            "specialist_tool_execution",
            "farm_data_writes",
            "customer_or_public_output",
            "builder_or_patch_execution",
            "deploy_execution",
            "telegram_cutover",
            "physical_controls",
        ]:
            with self.subTest(authority=authority):
                self.assertIn(authority, by_authority)
                self.assertFalse(by_authority[authority]["enabled"])
                self.assertEqual(by_authority[authority]["current_state"], "locked")
                self.assertTrue(by_authority[authority]["required_gates"])
        self.assertFalse(by_authority["specialist_llm_loop"]["enabled"])
        self.assertEqual(by_authority["specialist_llm_loop"]["current_state"], "single_shot_advisory_only")
        self.assertFalse(by_authority["specialist_llm_loop"]["effective_single_shot_enabled"])
        self.assertFalse(by_authority["specialist_llm_loop"]["effective_single_shot_configured"])
        self.assertEqual(by_authority["specialist_llm_loop"]["effective_single_shot_mode"], "single_shot_advisory_only")
        self.assertEqual(by_authority["specialist_llm_loop"]["effective_single_shot_specialist"], "sentinel")
        self.assertIn("one-shot", by_authority["specialist_llm_loop"]["why_locked"])
        self.assertIn("per-request dispatch execution approval", by_authority["specialist_llm_loop"]["required_gates"])
        self.assertEqual(by_authority["physical_controls"]["risk_level"], 5)
        self.assertIn("owner_and_claude_review", matrix["next_gate"])

    def test_agent_authority_matrix_surfaces_effective_single_shot_env_gate(self):
        with patch.dict(os.environ, {
            "OOM_SAKKIE_SPECIALIST_DRYRUN_ENABLED": "1",
            "OOM_SAKKIE_LLM_ROUTER_MODEL": "gpt-test",
            "OPENAI_API_KEY": "test-key",
        }, clear=False):
            matrix = get_agent_authority_matrix()

        by_authority = {item["authority"]: item for item in matrix["areas"]}
        specialist_llm = by_authority["specialist_llm_loop"]
        self.assertFalse(specialist_llm["enabled"])
        self.assertTrue(specialist_llm["effective_single_shot_enabled"])
        self.assertTrue(specialist_llm["effective_single_shot_configured"])
        self.assertEqual(specialist_llm["effective_single_shot_specialist"], "sentinel")
        self.assertIn("local owner POST", specialist_llm["effective_single_shot_note"])
        self.assertFalse(matrix["specialist_llm_enabled"])
        self.assertEqual(matrix["enabled_count"], 0)

    def test_agent_preflight_and_activation_plan_derive_locks_from_authority_matrix(self):
        plan = get_agent_activation_plan()
        preflight = get_agent_activation_preflight()
        matrix = get_agent_authority_matrix()
        matrix_by_authority = {item["authority"]: item for item in matrix["areas"]}
        preflight_by_check = {item["check"]: item for item in preflight["locked_checks"]}

        self.assertEqual(
            set(plan["blocked_capabilities"]),
            {item["blocked_capability"] for item in matrix["areas"]},
        )
        self.assertEqual(set(preflight_by_check), set(matrix_by_authority))
        for authority, item in matrix_by_authority.items():
            with self.subTest(authority=authority):
                self.assertEqual(preflight_by_check[authority]["risk_level"], item["risk_level"])
                self.assertEqual(preflight_by_check[authority]["detail"], item["why_locked"])
                self.assertEqual(preflight_by_check[authority]["required_gates"], item["required_gates"])

    def test_agent_authority_unlock_readiness_is_planning_only(self):
        readiness = get_agent_authority_unlock_readiness()

        self.assertTrue(readiness["success"])
        self.assertEqual(readiness["mode"], "agent_authority_unlock_readiness_only")
        self.assertEqual(readiness["summary_status"], "planning_only_no_unlock_recommended")
        self.assertFalse(readiness["runtime_enabled"])
        self.assertFalse(readiness["dispatch_enabled"])
        self.assertFalse(readiness["autonomous_loops_enabled"])
        self.assertFalse(readiness["writes_enabled"])
        self.assertFalse(readiness["specialist_llm_enabled"])
        self.assertFalse(readiness["specialist_tools_enabled"])
        self.assertFalse(readiness["public_output_enabled"])
        self.assertFalse(readiness["physical_controls_enabled"])
        self.assertEqual(readiness["enabled_count"], 0)
        self.assertGreaterEqual(readiness["candidate_count"], 1)
        self.assertEqual(readiness["lowest_risk_level"], 3)
        self.assertTrue(all(item["enabled"] is False for item in readiness["lowest_risk_candidates"]))
        self.assertTrue(any(item["authority"] == "physical_controls" for item in readiness["hard_no_authorities"]))
        self.assertIn("owner_named_authority", readiness["next_gate"])

    def test_agent_dispatch_decision_rail_blueprint_is_blueprint_only(self):
        blueprint = get_agent_dispatch_decision_rail_blueprint()

        self.assertTrue(blueprint["success"])
        self.assertEqual(blueprint["mode"], "dispatch_decision_rail_blueprint_only")
        self.assertEqual(blueprint["summary_status"], "blueprint_only_no_dispatch")
        self.assertEqual(blueprint["authority"]["authority"], "live_specialist_dispatch")
        self.assertFalse(blueprint["runtime_enabled"])
        self.assertFalse(blueprint["dispatch_enabled"])
        self.assertFalse(blueprint["autonomous_loops_enabled"])
        self.assertFalse(blueprint["writes_enabled"])
        self.assertFalse(blueprint["specialist_llm_enabled"])
        self.assertFalse(blueprint["specialist_tools_enabled"])
        self.assertFalse(blueprint["public_output_enabled"])
        self.assertFalse(blueprint["physical_controls_enabled"])
        table_names = {item["name"] for item in blueprint["proposed_tables"]}
        self.assertEqual(table_names, {"oom_sakkie_dispatch_requests", "oom_sakkie_dispatch_decisions"})
        self.assertIn("do not run a specialist", blueprint["non_goals"])
        self.assertIn("claude_review_before_dispatch", blueprint["next_gate"])

    def test_agent_runtime_review_packet_is_bulk_review_only(self):
        packet = get_agent_runtime_review_packet()

        self.assertTrue(packet["success"])
        self.assertEqual(packet["mode"], "agent_runtime_review_packet_only")
        self.assertEqual(packet["summary_status"], "ready_for_bulk_claude_review_not_live_dispatch")
        self.assertFalse(packet["runtime_enabled"])
        self.assertFalse(packet["dispatch_enabled"])
        self.assertFalse(packet["autonomous_loops_enabled"])
        self.assertFalse(packet["writes_enabled"])
        self.assertFalse(packet["specialist_llm_enabled"])
        self.assertFalse(packet["specialist_tools_enabled"])
        self.assertFalse(packet["public_output_enabled"])
        self.assertFalse(packet["physical_controls_enabled"])
        self.assertEqual(packet["payloads"]["dispatch_blueprint"]["summary_status"], "blueprint_only_no_dispatch")
        self.assertIn("dispatch decision rail blueprint remains blueprint-only", packet["review_focus"])
        self.assertIn("CLAUDE_REVIEW_HANDOFF.md", packet["claude_prompt"])

    def test_agent_runtime_inspection_surfaces_keep_authority_flags_false(self):
        surfaces = {
            "runtime_status": get_agent_runtime_status(),
            "activation_plan": get_agent_activation_plan(),
            "runtime_readiness": get_agent_runtime_readiness(),
            "operating_contracts": get_agent_operating_contracts(),
            "activation_preflight": get_agent_activation_preflight(),
            "authority_matrix": get_agent_authority_matrix(),
            "unlock_readiness": get_agent_authority_unlock_readiness(),
            "jarvis_product_progress": get_jarvis_product_progress(),
            "jarvis_safety_gate_board": get_jarvis_safety_gate_board(),
            "jarvis_owner_review_packet": get_jarvis_owner_review_packet(),
            "learning_influence_consumption_readiness": get_learning_influence_consumption_readiness(),
            "learning_influence_consumption_audit_rail_blueprint": get_learning_influence_consumption_audit_rail_blueprint(),
            "agent_command_center": get_agent_command_center(),
            "dispatch_rail_blueprint": get_agent_dispatch_decision_rail_blueprint(),
            "runtime_review_packet": get_agent_runtime_review_packet(),
        }
        flag_names = [
            "runtime_enabled",
            "dispatch_enabled",
            "autonomous_loops_enabled",
            "writes_enabled",
            "specialist_llm_enabled",
            "specialist_tools_enabled",
            "public_output_enabled",
            "physical_controls_enabled",
        ]

        for name, payload in surfaces.items():
            with self.subTest(surface=name):
                self.assertTrue(payload["success"])
                for flag in flag_names:
                    if flag in payload:
                        self.assertFalse(payload[flag], f"{name}.{flag} must stay false")
                self.assertNotEqual(payload.get("next_gate"), "")

    def test_agent_crew_brief_is_multi_agent_plan_only(self):
        brief = build_agent_crew_brief("How do we grow sales and market pork better?")

        self.assertTrue(brief["success"])
        self.assertEqual(brief["mode"], "crew_plan_only")
        self.assertEqual(brief["scenario"], "commercial_growth")
        self.assertEqual([item["slug"] for item in brief["sequence"][:4]], [
            "ledger",
            "butcher",
            "beacon",
            "sentinel",
        ])
        self.assertIn("sales stock", brief["sequence"][0]["would_inspect"])
        self.assertIn("draft-only marketing", brief["sequence"][2]["would_inspect"])
        self.assertFalse(brief["safety"]["runs_agents"])
        self.assertFalse(brief["safety"]["dispatch_enabled"])
        self.assertFalse(brief["safety"]["autonomous_loops_enabled"])
        self.assertFalse(brief["safety"]["writes"])
        self.assertIn("owner_approval", brief["next_gate"])

    def test_agent_activity_maps_read_only_tools_to_visible_workspace(self):
        activity = build_agent_activity(
            tool_name="business_growth_brief",
            user_text="what should we sell next?",
            tool_result={},
        )

        self.assertTrue(activity["success"])
        self.assertEqual(activity["mode"], "visual_activity_only")
        self.assertEqual(activity["controller"], "oom_sakkie")
        self.assertEqual(activity["active_agent"]["slug"], "ledger")
        self.assertEqual(activity["active_agent"]["color"], "green")
        self.assertEqual(activity["workspace"]["tool_name"], "business_growth_brief")
        self.assertEqual([step["step"] for step in activity["handoff_lane"]], [
            "controller",
            "specialist_workspace",
            "read_only_tool",
            "owner_gate",
        ])
        self.assertEqual(activity["handoff_lane"][0]["actor"], "Oom Sakkie")
        self.assertEqual(activity["handoff_lane"][2]["actor"], "business_growth_brief")
        self.assertIn("No write", activity["handoff_lane"][3]["detail"])
        self.assertFalse(activity["safety"]["runs_agent"])
        self.assertFalse(activity["safety"]["dispatch_enabled"])
        self.assertFalse(activity["safety"]["autonomous_loops_enabled"])
        self.assertFalse(activity["safety"]["writes"])

    def test_agent_activity_uses_agent_recommendation_context(self):
        recommendation = recommend_agent_for_text("Who should handle a marketing post?")
        activity = build_agent_activity(
            tool_name="agent_crew_status",
            user_text="Who should handle a marketing post?",
            tool_result={"llm_context": {"selected_agent": recommendation["selected_agent"]}},
        )

        self.assertEqual(activity["active_agent"]["slug"], "beacon")
        self.assertEqual(activity["active_agent"]["color"], "magenta")
        self.assertEqual(activity["workspace"]["reason"], "tool_context:selected_agent")
        self.assertFalse(activity["safety"]["runs_agent"])

    def test_agent_activity_maps_command_center_to_gatekeeper_workspace(self):
        activity = build_agent_activity(
            tool_name="agent_command_center",
            user_text="show me the command center",
            tool_result={},
        )

        self.assertEqual(activity["active_agent"]["slug"], "gatekeeper")
        self.assertEqual(activity["active_agent"]["color"], "white")
        self.assertEqual(activity["workspace"]["tool_name"], "agent_command_center")
        self.assertFalse(activity["safety"]["runs_agent"])
        self.assertFalse(activity["safety"]["dispatch_enabled"])
        self.assertFalse(activity["safety"]["writes"])

    def test_agent_activity_maps_daily_command_brief_to_gatekeeper_workspace(self):
        activity = build_agent_activity(
            tool_name="jarvis_daily_command_brief",
            user_text="give me the daily command brief",
            tool_result={},
        )

        self.assertEqual(activity["active_agent"]["slug"], "gatekeeper")
        self.assertEqual(activity["workspace"]["tool_name"], "jarvis_daily_command_brief")
        self.assertFalse(activity["safety"]["runs_agent"])
        self.assertFalse(activity["safety"]["dispatch_enabled"])
        self.assertFalse(activity["safety"]["writes"])

    def test_agent_activity_maps_safety_gate_board_to_sentinel_workspace(self):
        activity = build_agent_activity(
            tool_name="jarvis_safety_gate_board",
            user_text="are the gates green?",
            tool_result={},
        )

        self.assertEqual(activity["active_agent"]["slug"], "sentinel")
        self.assertEqual(activity["workspace"]["tool_name"], "jarvis_safety_gate_board")
        self.assertFalse(activity["safety"]["runs_agent"])
        self.assertFalse(activity["safety"]["dispatch_enabled"])
        self.assertFalse(activity["safety"]["writes"])

    def test_agent_activity_maps_owner_review_packet_to_gatekeeper_workspace(self):
        activity = build_agent_activity(
            tool_name="jarvis_owner_review_packet",
            user_text="prepare Claude review",
            tool_result={},
        )

        self.assertEqual(activity["active_agent"]["slug"], "gatekeeper")
        self.assertEqual(activity["workspace"]["tool_name"], "jarvis_owner_review_packet")
        self.assertFalse(activity["safety"]["runs_agent"])
        self.assertFalse(activity["safety"]["dispatch_enabled"])
        self.assertFalse(activity["safety"]["writes"])

    def test_agent_activity_exposes_plan_only_crew_sequence(self):
        crew_brief = build_agent_crew_brief("Give me the team plan to grow sales")
        activity = build_agent_activity(
            tool_name="agent_crew_brief",
            user_text="Give me the team plan to grow sales",
            tool_result={
                "llm_context": {
                    "selected_agent": crew_brief["sequence"][0],
                    "crew_brief": crew_brief,
                }
            },
        )

        self.assertEqual(activity["active_agent"]["slug"], "ledger")
        self.assertEqual(activity["crew_sequence"][0]["slug"], "ledger")
        self.assertEqual(activity["crew_sequence"][1]["slug"], "butcher")
        self.assertEqual(activity["crew_sequence"][2]["slug"], "beacon")
        self.assertFalse(activity["crew_sequence"][0]["runs_agent"])
        self.assertFalse(activity["crew_sequence"][0]["writes"])

    def test_agent_crew_status_tool_is_read_only_and_recommendation_only(self):
        from modules.oom_sakkie.tools import agent_crew_status_handler

        result = agent_crew_status_handler({"user_text": "who should handle a marketing post?"})

        self.assertTrue(result["success"])
        self.assertEqual(result["status"], "ok")
        self.assertIn("Agent crew foundation", result["summary"])
        self.assertIn("recommendation only", result["summary"])
        self.assertIn("no specialist was dispatched", result["safety_notes"][0].lower())
        self.assertEqual(result["llm_context"]["kind"], "agent_crew_status")
        self.assertEqual(result["llm_context"]["selected_agent"]["slug"], "beacon")
        self.assertFalse(result["llm_context"]["recommendation"]["runs_agent"])
        self.assertFalse(result["llm_context"]["recommendation"]["writes"])

    def test_agent_crew_brief_tool_is_read_only_plan_only(self):
        from modules.oom_sakkie.tools import agent_crew_brief_handler

        result = agent_crew_brief_handler({"user_text": "give me the agent team brief for growing sales"})

        self.assertTrue(result["success"])
        self.assertEqual(result["status"], "ok")
        self.assertIn("Crew brief prepared", result["summary"])
        self.assertIn("no specialist was dispatched", result["safety_notes"][0].lower())
        self.assertEqual(result["llm_context"]["kind"], "agent_crew_brief")
        self.assertEqual(result["llm_context"]["crew_brief"]["mode"], "crew_plan_only")
        self.assertEqual(result["llm_context"]["selected_agent"]["slug"], "ledger")

    def test_agent_runtime_readiness_tool_is_read_only(self):
        from modules.oom_sakkie.tools import agent_runtime_readiness_handler

        result = agent_runtime_readiness_handler({})

        self.assertTrue(result["success"])
        self.assertEqual(result["status"], "ok")
        self.assertIn("manual check", result["summary"])
        self.assertIn("live-authority gate", result["summary"])
        self.assertIn("does not run specialists", result["safety_notes"][0])
        self.assertEqual(result["llm_context"]["kind"], "agent_runtime_readiness")
        self.assertFalse(result["llm_context"]["readiness"]["dispatch_enabled"])
        self.assertFalse(result["llm_context"]["readiness"]["writes_enabled"])
        self.assertEqual(result["llm_context"]["selected_agent"]["slug"], "gatekeeper")

    def test_jarvis_product_progress_tool_is_read_only(self):
        from modules.oom_sakkie.tools import jarvis_product_progress_handler

        result = jarvis_product_progress_handler({})

        self.assertTrue(result["success"])
        self.assertEqual(result["status"], "ok")
        self.assertIn("Jarvis product progress", result["summary"])
        self.assertIn("Next milestone", result["summary"])
        self.assertIn("read-only planning status", result["safety_notes"][0])
        self.assertEqual(result["llm_context"]["kind"], "jarvis_product_progress")
        self.assertFalse(result["llm_context"]["progress"]["dispatch_enabled"])
        self.assertFalse(result["llm_context"]["progress"]["writes_enabled"])
        self.assertEqual(result["llm_context"]["selected_agent"]["slug"], "gatekeeper")

    def test_jarvis_safety_gate_board_tool_is_read_only(self):
        from modules.oom_sakkie.tools import jarvis_safety_gate_board_handler

        result = jarvis_safety_gate_board_handler({})

        self.assertTrue(result["success"])
        self.assertEqual(result["status"], "ok")
        self.assertIn("Safety gate board", result["summary"])
        self.assertIn("does not call GitHub", result["stale_warnings"][0])
        self.assertIn("read-only", result["safety_notes"][0])
        self.assertEqual(result["llm_context"]["kind"], "jarvis_safety_gate_board")
        self.assertEqual(result["llm_context"]["selected_agent"]["slug"], "sentinel")
        self.assertFalse(result["llm_context"]["dispatch_enabled"])
        self.assertFalse(result["llm_context"]["runs_specialist_llm"])
        self.assertFalse(result["llm_context"]["runs_specialist_tools"])
        self.assertFalse(result["llm_context"]["writes"])
        self.assertFalse(result["llm_context"]["applies_runtime_change"])

    def test_jarvis_owner_review_packet_tool_is_read_only(self):
        from modules.oom_sakkie.tools import jarvis_owner_review_packet_handler

        result = jarvis_owner_review_packet_handler({})

        self.assertTrue(result["success"])
        self.assertEqual(result["status"], "ok")
        self.assertIn("Owner review packet is ready", result["summary"])
        self.assertIn("10.9EA", result["summary"])
        self.assertIn("2 recorded CI gate", result["summary"])
        self.assertIn("does not call Claude", result["stale_warnings"][0])
        self.assertIn("read-only", result["safety_notes"][0])
        self.assertEqual(result["llm_context"]["kind"], "jarvis_owner_review_packet")
        self.assertEqual(result["llm_context"]["selected_agent"]["slug"], "gatekeeper")
        self.assertIn("CLAUDE_REVIEW_HANDOFF.md", result["llm_context"]["claude_prompt"])
        self.assertEqual(result["llm_context"]["current_review"]["scope"], "Oom Sakkie 10.6 through 10.9EA")
        self.assertTrue(result["llm_context"]["current_review"]["learning_influence_consumer_enabled"])
        self.assertFalse(result["llm_context"]["dispatch_enabled"])
        self.assertFalse(result["llm_context"]["runs_specialist_llm"])
        self.assertFalse(result["llm_context"]["runs_specialist_tools"])
        self.assertFalse(result["llm_context"]["writes"])
        self.assertFalse(result["llm_context"]["applies_runtime_change"])

    def test_learning_influence_consumption_readiness_tool_is_read_only(self):
        from modules.oom_sakkie.tools import learning_influence_consumption_readiness_handler

        result = learning_influence_consumption_readiness_handler({})

        self.assertTrue(result["success"])
        self.assertEqual(result["status"], "ok")
        self.assertIn("Learning influence consumption is not ready", result["summary"])
        self.assertIn("read-only", result["safety_notes"][0])
        self.assertEqual(result["llm_context"]["kind"], "learning_influence_consumption_readiness")
        self.assertEqual(result["llm_context"]["selected_agent"]["slug"], "gatekeeper")
        self.assertFalse(result["llm_context"]["readiness"]["learning_influence_consumer_enabled"])
        self.assertFalse(result["llm_context"]["dispatch_enabled"])
        self.assertFalse(result["llm_context"]["runs_specialist_llm"])
        self.assertFalse(result["llm_context"]["runs_specialist_tools"])
        self.assertFalse(result["llm_context"]["writes"])
        self.assertFalse(result["llm_context"]["applies_runtime_change"])

    def test_learning_influence_consumption_audit_rail_blueprint_tool_is_read_only(self):
        from modules.oom_sakkie.tools import learning_influence_consumption_audit_rail_blueprint_handler

        result = learning_influence_consumption_audit_rail_blueprint_handler({})

        self.assertTrue(result["success"])
        self.assertEqual(result["status"], "ok")
        self.assertIn("review-only", result["summary"])
        self.assertIn("read-only", result["safety_notes"][0])
        self.assertEqual(result["llm_context"]["kind"], "learning_influence_consumption_audit_rail_blueprint")
        self.assertEqual(result["llm_context"]["selected_agent"]["slug"], "gatekeeper")
        self.assertFalse(result["llm_context"]["blueprint"]["learning_influence_consumer_enabled"])
        self.assertTrue(result["llm_context"]["blueprint"]["creates_tables_now"])
        self.assertTrue(result["llm_context"]["blueprint"]["review_note_only_first_slice"])
        self.assertFalse(result["llm_context"]["dispatch_enabled"])
        self.assertFalse(result["llm_context"]["runs_specialist_llm"])
        self.assertFalse(result["llm_context"]["runs_specialist_tools"])
        self.assertFalse(result["llm_context"]["writes"])
        self.assertFalse(result["llm_context"]["applies_runtime_change"])

    def test_learning_influence_consumer_design_packet_tool_is_read_only(self):
        from modules.oom_sakkie.tools import learning_influence_consumer_design_packet_handler

        result = learning_influence_consumer_design_packet_handler({})

        self.assertTrue(result["success"])
        self.assertEqual(result["status"], "ok")
        self.assertIn("review-only", result["summary"])
        self.assertIn("read-only", result["safety_notes"][0])
        self.assertEqual(result["llm_context"]["kind"], "learning_influence_consumer_design_packet")
        self.assertEqual(result["llm_context"]["selected_agent"]["slug"], "gatekeeper")
        self.assertTrue(result["llm_context"]["design_packet"]["learning_influence_consumer_enabled"])
        self.assertEqual(result["llm_context"]["design_packet"]["allow_consumed_production_callers"], [])
        self.assertFalse(result["llm_context"]["dispatch_enabled"])
        self.assertFalse(result["llm_context"]["runs_specialist_llm"])
        self.assertFalse(result["llm_context"]["runs_specialist_tools"])
        self.assertFalse(result["llm_context"]["writes"])
        self.assertFalse(result["llm_context"]["applies_runtime_change"])

    @patch("modules.oom_sakkie.service.compose_answer_with_llm", return_value=None)
    @patch("modules.oom_sakkie.service.write_trace", return_value={"stored": False, "status": "test"})
    def test_prepare_claude_review_answer_names_scope_without_authority(self, _write_trace, _compose):
        result, status = handle_message({
            "text": "prepare Claude review",
            "channel": "kiosk",
            "session_id": "test-review-packet",
        })

        self.assertEqual(status, 200)
        self.assertTrue(result["success"])
        self.assertEqual(result["tool_used"], "jarvis_owner_review_packet")
        self.assertEqual(result["pipeline"]["answer_source"], "deterministic")
        self.assertIn("10.9EA", result["answer"])
        self.assertIn("2 recorded CI gate", result["answer"])
        self.assertIn("does not approve runtime authority", result["safety_notes"][0])
        self.assertEqual(result["agent_activity"]["active_agent"]["slug"], "gatekeeper")
        self.assertFalse(result["agent_activity"]["safety"]["runs_agent"])
        self.assertFalse(result["agent_activity"]["safety"]["dispatch_enabled"])
        self.assertFalse(result["agent_activity"]["safety"]["writes"])

    @patch("modules.oom_sakkie.tools.jarvis_safety_gate_board_handler")
    @patch("modules.oom_sakkie.tools.dispatch_decision_status_handler")
    @patch("modules.oom_sakkie.tools.agent_dry_run_status_handler")
    @patch("modules.oom_sakkie.tools.system_work_status_handler")
    def test_agent_command_center_tool_is_read_only_visibility(self, mock_work, mock_dry_run, mock_dispatch, mock_safety_gate):
        from modules.oom_sakkie.tools import agent_command_center_handler

        mock_work.return_value = {
            "status": "ok",
            "stale_warnings": [],
            "llm_context": {"kind": "system_work_status"},
        }
        mock_dry_run.return_value = {
            "status": "ok",
            "stale_warnings": [],
            "llm_context": {"kind": "agent_dry_run_status"},
        }
        mock_dispatch.return_value = {
            "status": "ok",
            "stale_warnings": [],
            "llm_context": {"kind": "dispatch_decision_status"},
        }
        mock_safety_gate.return_value = {
            "status": "ok",
            "stale_warnings": [],
            "llm_context": {"kind": "jarvis_safety_gate_board"},
        }

        result = agent_command_center_handler({})

        self.assertTrue(result["success"])
        self.assertEqual(result["status"], "ok")
        self.assertIn("Agent command center", result["summary"])
        self.assertIn("live authority remains locked", result["summary"])
        self.assertIn("read-only visibility", result["safety_notes"][0])
        self.assertEqual(result["llm_context"]["kind"], "agent_command_center")
        self.assertFalse(result["llm_context"]["command_center"]["dispatch_enabled"])
        self.assertFalse(result["llm_context"]["command_center"]["writes_enabled"])
        self.assertEqual(result["llm_context"]["selected_agent"]["slug"], "gatekeeper")
        self.assertEqual(result["llm_context"]["queue_snapshots"]["system_work_status"]["kind"], "system_work_status")
        self.assertEqual(result["llm_context"]["queue_snapshots"]["jarvis_safety_gate_board"]["kind"], "jarvis_safety_gate_board")
        mock_work.assert_called_once_with({})
        mock_dry_run.assert_called_once_with({})
        mock_dispatch.assert_called_once_with({})
        mock_safety_gate.assert_called_once_with({})

    def test_agent_operating_contracts_tool_is_read_only(self):
        from modules.oom_sakkie.tools import agent_operating_contracts_handler

        result = agent_operating_contracts_handler({})

        self.assertTrue(result["success"])
        self.assertEqual(result["status"], "ok")
        self.assertIn("planned contract", result["summary"])
        self.assertIn("not runtime authority", result["summary"])
        self.assertIn("No specialist was dispatched", result["safety_notes"][0])
        self.assertEqual(result["llm_context"]["kind"], "agent_operating_contracts")
        self.assertFalse(result["llm_context"]["contracts"]["dispatch_enabled"])
        self.assertFalse(result["llm_context"]["contracts"]["writes_enabled"])
        self.assertIn("beacon", result["llm_context"]["contracts"]["locked_out_of_dry_run"])
        self.assertEqual(result["llm_context"]["selected_agent"]["slug"], "gatekeeper")

    def test_agent_activation_preflight_tool_is_read_only(self):
        from modules.oom_sakkie.tools import agent_activation_preflight_handler

        result = agent_activation_preflight_handler({})

        self.assertTrue(result["success"])
        self.assertEqual(result["status"], "ok")
        self.assertIn("not ready for live dispatch", result["summary"])
        self.assertIn("manual check", result["summary"])
        self.assertIn("does not run specialists", result["safety_notes"][0])
        self.assertEqual(result["llm_context"]["kind"], "agent_activation_preflight")
        self.assertFalse(result["llm_context"]["preflight"]["dispatch_enabled"])
        self.assertFalse(result["llm_context"]["preflight"]["writes_enabled"])
        self.assertEqual(result["llm_context"]["selected_agent"]["slug"], "gatekeeper")

    def test_agent_authority_matrix_tool_is_read_only(self):
        from modules.oom_sakkie.tools import agent_authority_matrix_handler

        result = agent_authority_matrix_handler({})

        self.assertTrue(result["success"])
        self.assertEqual(result["status"], "ok")
        self.assertIn("authority area", result["summary"])
        self.assertIn("No live authority is active", result["summary"])
        self.assertIn("does not enable dispatch", result["safety_notes"][0])
        self.assertEqual(result["llm_context"]["kind"], "agent_authority_matrix")
        self.assertEqual(result["llm_context"]["authority_matrix"]["enabled_count"], 0)
        self.assertFalse(result["llm_context"]["authority_matrix"]["dispatch_enabled"])
        self.assertFalse(result["llm_context"]["authority_matrix"]["writes_enabled"])
        self.assertEqual(result["llm_context"]["selected_agent"]["slug"], "gatekeeper")

    def test_agent_authority_unlock_readiness_tool_is_read_only(self):
        from modules.oom_sakkie.tools import agent_authority_unlock_readiness_handler

        result = agent_authority_unlock_readiness_handler({})

        self.assertTrue(result["success"])
        self.assertEqual(result["status"], "ok")
        self.assertIn("no unlock is recommended", result["summary"])
        self.assertIn("planning-only", result["safety_notes"][0])
        self.assertEqual(result["llm_context"]["kind"], "agent_authority_unlock_readiness")
        self.assertEqual(result["llm_context"]["unlock_readiness"]["enabled_count"], 0)
        self.assertFalse(result["llm_context"]["unlock_readiness"]["dispatch_enabled"])
        self.assertFalse(result["llm_context"]["unlock_readiness"]["writes_enabled"])
        self.assertEqual(result["llm_context"]["selected_agent"]["slug"], "gatekeeper")

    def test_agent_dispatch_decision_rail_blueprint_tool_is_read_only(self):
        from modules.oom_sakkie.tools import agent_dispatch_decision_rail_blueprint_handler

        result = agent_dispatch_decision_rail_blueprint_handler({})

        self.assertTrue(result["success"])
        self.assertEqual(result["status"], "ok")
        self.assertIn("review only", result["summary"])
        self.assertIn("does not run specialists", result["safety_notes"][0])
        self.assertEqual(result["llm_context"]["kind"], "agent_dispatch_decision_rail_blueprint")
        self.assertEqual(result["llm_context"]["dispatch_blueprint"]["summary_status"], "blueprint_only_no_dispatch")
        self.assertFalse(result["llm_context"]["dispatch_blueprint"]["dispatch_enabled"])
        self.assertFalse(result["llm_context"]["dispatch_blueprint"]["writes_enabled"])
        self.assertEqual(result["llm_context"]["selected_agent"]["slug"], "gatekeeper")

    @patch("modules.oom_sakkie.tools.list_dispatch_requests")
    def test_dispatch_decision_status_tool_is_read_only(self, mock_dispatch):
        from modules.oom_sakkie.tools import dispatch_decision_status_handler

        mock_dispatch.return_value = ({
            "success": True,
            "configured": True,
            "dispatch_requests": [
                {
                    "dispatch_request_id": "OSK-DISPATCH-REQ-1",
                    "specialist_slug": "sentinel",
                    "latest_decision": None,
                },
                {
                    "dispatch_request_id": "OSK-DISPATCH-REQ-2",
                    "specialist_slug": "prism",
                    "latest_decision": {"decision_type": "approved_for_design_review"},
                },
            ],
        }, 200)

        result = dispatch_decision_status_handler({})

        self.assertTrue(result["success"])
        self.assertEqual(result["status"], "ok")
        self.assertIn("1 request(s) need owner/Claude design review", result["summary"])
        self.assertIn("No specialist dispatch is enabled", result["summary"])
        self.assertIn("No specialist was dispatched", result["safety_notes"][0])
        self.assertEqual(result["llm_context"]["kind"], "dispatch_decision_status")
        self.assertEqual(result["llm_context"]["counts"]["pending_design_review"], 1)
        self.assertEqual(result["llm_context"]["counts"]["approved_for_design_review"], 1)
        self.assertFalse(result["llm_context"]["dispatch_enabled"])
        self.assertFalse(result["llm_context"]["runs_specialist_llm"])
        self.assertFalse(result["llm_context"]["writes"])
        self.assertIn("OSK-DISPATCH-REQ-1", result["llm_context"]["next_action"])

    def test_agent_runtime_review_packet_tool_is_read_only(self):
        from modules.oom_sakkie.tools import agent_runtime_review_packet_handler

        result = agent_runtime_review_packet_handler({})

        self.assertTrue(result["success"])
        self.assertEqual(result["status"], "ok")
        self.assertIn("bulk Claude review", result["summary"])
        self.assertIn("does not run specialists", result["safety_notes"][0])
        self.assertEqual(result["llm_context"]["kind"], "agent_runtime_review_packet")
        self.assertEqual(result["llm_context"]["review_packet"]["summary_status"], "ready_for_bulk_claude_review_not_live_dispatch")
        self.assertFalse(result["llm_context"]["review_packet"]["dispatch_enabled"])
        self.assertFalse(result["llm_context"]["review_packet"]["writes_enabled"])
        self.assertEqual(result["llm_context"]["selected_agent"]["slug"], "gatekeeper")

    @patch("modules.oom_sakkie.tools.dispatch_decision_status_handler")
    def test_dispatch_runtime_review_packet_tool_is_read_only(self, mock_dispatch_status):
        from modules.oom_sakkie.tools import dispatch_runtime_review_packet_handler

        mock_dispatch_status.return_value = {
            "success": True,
            "status": "ok",
            "summary": "Dispatch design status.",
            "links": [],
            "stale_warnings": [],
            "safety_notes": ["Dispatch status read-only."],
            "llm_context": {
                "kind": "dispatch_decision_status",
                "counts": {
                    "pending_design_review": 1,
                    "approved_for_design_review": 2,
                },
                "dispatch_enabled": False,
                "runs_specialist_llm": False,
                "runs_specialist_tools": False,
                "writes": False,
                "applies_runtime_change": False,
            },
            "raw": {"dispatch_requests": []},
        }

        result = dispatch_runtime_review_packet_handler({})

        self.assertTrue(result["success"])
        self.assertEqual(result["status"], "ok")
        self.assertIn("owner and Claude review", result["summary"])
        self.assertIn("does not enable dispatch", result["summary"])
        self.assertIn("does not run specialists", result["safety_notes"][0])
        self.assertEqual(result["llm_context"]["kind"], "dispatch_runtime_review_packet")
        self.assertEqual(result["llm_context"]["dispatch_status"]["llm_context"]["counts"]["pending_design_review"], 1)
        self.assertEqual(result["llm_context"]["next_gate"], "owner_and_claude_review_before_any_code_consumes_dispatch_decisions")
        self.assertFalse(result["llm_context"]["dispatch_enabled"])
        self.assertFalse(result["llm_context"]["runs_specialist_llm"])
        self.assertFalse(result["llm_context"]["runs_specialist_tools"])
        self.assertFalse(result["llm_context"]["writes"])
        self.assertFalse(result["llm_context"]["applies_runtime_change"])

    @patch("modules.oom_sakkie.tools.list_agent_dry_run_results")
    def test_agent_activation_plan_tool_is_read_only(self, mock_results):
        from modules.oom_sakkie.tools import agent_activation_plan_handler

        mock_results.return_value = ({
            "success": True,
            "status": "ok",
            "dry_run_results": [],
        }, 200)

        result = agent_activation_plan_handler({})

        self.assertTrue(result["success"])
        self.assertEqual(result["status"], "ok")
        self.assertIn("read-only dry-run", result["summary"])
        self.assertIn("No accepted agent learning evidence", result["summary"])
        self.assertIn("no specialist was dispatched", result["safety_notes"][0].lower())
        self.assertEqual(result["llm_context"]["kind"], "agent_activation_plan")
        self.assertEqual(result["llm_context"]["selected_agent"]["slug"], "sentinel")
        self.assertFalse(result["llm_context"]["activation_plan"]["dispatch_enabled"])
        self.assertEqual(result["llm_context"]["accepted_learning_count"], 0)

    @patch("modules.oom_sakkie.tools.list_agent_dry_run_results")
    def test_agent_activation_plan_surfaces_accepted_learning_without_unlocking_runtime(self, mock_results):
        from modules.oom_sakkie.tools import agent_activation_plan_handler

        mock_results.return_value = ({
            "success": True,
            "status": "ok",
            "dry_run_results": [{
                "dry_run_result_id": "OSK-AGENT-DRYRUN-RESULT-1",
                "dry_run_request_id": "OSK-AGENT-DRYRUN-1",
                "specialist_slug": "ledger",
                "result_text": "Ledger says offer planning should stay internal.",
                "findings": ["No customer message should be sent."],
                "latest_event": {
                    "event_type": "accepted_for_learning",
                    "notes": "Useful.",
                    "created_at": "2026-06-08T10:00:00+00:00",
                },
            }],
        }, 200)

        result = agent_activation_plan_handler({})

        self.assertTrue(result["success"])
        self.assertIn("Accepted learning evidence: 1 accepted agent result", result["summary"])
        self.assertIn("ledger: 1", result["summary"])
        self.assertEqual(result["llm_context"]["accepted_learning_count"], 1)
        self.assertEqual(result["llm_context"]["accepted_by_specialist"]["ledger"], 1)
        self.assertEqual(
            result["llm_context"]["accepted_learning"][0]["dry_run_result_id"],
            "OSK-AGENT-DRYRUN-RESULT-1",
        )
        self.assertFalse(result["llm_context"]["activation_plan"]["dispatch_enabled"])
        self.assertIn("no runtime flag was enabled", result["safety_notes"][0])

    def test_sentinel_dry_run_review_is_read_only_and_locked(self):
        from modules.oom_sakkie.tools import sentinel_dry_run_review_handler

        result = sentinel_dry_run_review_handler({})

        self.assertTrue(result["success"])
        self.assertEqual(result["status"], "ok")
        self.assertIn("Sentinel dry-run review", result["summary"])
        self.assertIn("No specialist was dispatched", result["safety_notes"][0])
        self.assertEqual(result["llm_context"]["kind"], "sentinel_dry_run_review")
        self.assertEqual(result["llm_context"]["selected_agent"]["slug"], "sentinel")
        self.assertFalse(result["llm_context"]["runtime_flags"]["dispatch_enabled"])
        self.assertFalse(result["llm_context"]["runtime_flags"]["specialist_llm_enabled"])
        self.assertEqual(result["llm_context"]["tool_audit"]["non_read_only_tools"], ["sales_customer_draft"])
        self.assertEqual(result["llm_context"]["tool_audit"]["requires_confirmation_tools"], [])
        blockers = result["llm_context"]["sentinel_review"]["blockers_before_live_dry_run"]
        self.assertTrue(any("dispatch/audit" in blocker for blocker in blockers))

    @patch("modules.oom_sakkie.tools.list_agent_dry_run_results")
    @patch("modules.oom_sakkie.tools.list_agent_dry_run_requests")
    def test_agent_dry_run_status_tool_is_read_only_queue_status(self, mock_list, mock_results):
        from modules.oom_sakkie.tools import agent_dry_run_status_handler

        mock_list.return_value = ({
            "success": True,
            "status": "ok",
            "dry_run_requests": [{
                "dry_run_request_id": "OSK-AGENT-DRYRUN-1",
                "specialist_slug": "sentinel",
                "latest_event": None,
            }, {
                "dry_run_request_id": "OSK-AGENT-DRYRUN-2",
                "specialist_slug": "ledger",
                "latest_event": {"event_type": "approved"},
            }],
        }, 200)
        mock_results.return_value = ({
            "success": True,
            "status": "ok",
            "dry_run_results": [{
                "dry_run_result_id": "OSK-AGENT-DRYRUN-RESULT-1",
                "dry_run_request_id": "OSK-AGENT-DRYRUN-1",
                "specialist_slug": "sentinel",
                "latest_event": None,
            }, {
                "dry_run_result_id": "OSK-AGENT-DRYRUN-RESULT-2",
                "dry_run_request_id": "OSK-AGENT-DRYRUN-2",
                "specialist_slug": "ledger",
                "latest_event": {"event_type": "accepted_for_learning"},
            }],
        }, 200)

        result = agent_dry_run_status_handler({})

        self.assertTrue(result["success"])
        self.assertIn("2 request", result["summary"])
        self.assertIn("2 result", result["summary"])
        self.assertIn("ledger: 1 request(s), 1 result(s)", result["summary"])
        self.assertIn("sentinel: 1 request(s), 1 result(s)", result["summary"])
        self.assertIn("No specialist was dispatched", result["safety_notes"][0])
        self.assertEqual(result["llm_context"]["kind"], "agent_dry_run_status")
        self.assertEqual(result["llm_context"]["counts"]["waiting_for_review"], 1)
        self.assertEqual(result["llm_context"]["counts"]["results_waiting_for_owner_review"], 1)
        self.assertEqual(result["llm_context"]["specialist_counts"]["sentinel"]["requests_waiting"], 1)
        self.assertEqual(result["llm_context"]["specialist_counts"]["sentinel"]["results_waiting"], 1)
        self.assertEqual(result["llm_context"]["specialist_counts"]["ledger"]["accepted_for_learning"], 1)
        self.assertFalse(result["llm_context"]["runtime_flags"]["dispatch_enabled"])
        self.assertFalse(result["llm_context"]["runtime_flags"]["applies_runtime_change"])

    @patch("modules.oom_sakkie.tools.list_agent_dry_run_results")
    @patch("modules.oom_sakkie.tools.list_agent_dry_run_requests")
    def test_agent_dry_run_status_warns_when_result_queue_unavailable(self, mock_list, mock_results):
        from modules.oom_sakkie.tools import agent_dry_run_status_handler

        mock_list.return_value = ({
            "success": True,
            "status": "ok",
            "dry_run_requests": [],
        }, 200)
        mock_results.return_value = ({
            "success": False,
            "status": "not_configured",
            "dry_run_results": [],
        }, 503)

        result = agent_dry_run_status_handler({})

        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "not_configured")
        self.assertIn("unavailable", result["summary"])
        self.assertIn("result queue is unavailable (status 503)", result["stale_warnings"][0])

    @patch("modules.oom_sakkie.tools.list_agent_dry_run_results")
    def test_agent_learning_evidence_is_read_only_accepted_results(self, mock_results):
        from modules.oom_sakkie.tools import agent_learning_evidence_handler

        mock_results.return_value = ({
            "success": True,
            "status": "ok",
            "dry_run_results": [
                {
                    "dry_run_result_id": "OSK-AGENT-DRYRUN-RESULT-1",
                    "dry_run_request_id": "OSK-AGENT-DRYRUN-1",
                    "specialist_slug": "ledger",
                    "result_text": "Ledger says the offer should remain internal.",
                    "findings": ["Runtime flags stayed false."],
                    "latest_event": {
                        "event_type": "accepted_for_learning",
                        "notes": "Useful.",
                        "created_at": "2026-06-08T10:00:00+00:00",
                    },
                },
                {
                    "dry_run_result_id": "OSK-AGENT-DRYRUN-RESULT-2",
                    "dry_run_request_id": "OSK-AGENT-DRYRUN-2",
                    "specialist_slug": "rootline",
                    "result_text": "Rootline says irrigation context is stale.",
                    "findings": ["No pump command."],
                    "latest_event": {
                        "event_type": "accepted_for_learning",
                        "notes": "Useful boundary.",
                        "created_at": "2026-06-08T11:00:00+00:00",
                    },
                },
                {
                    "dry_run_result_id": "OSK-AGENT-DRYRUN-RESULT-3",
                    "dry_run_request_id": "OSK-AGENT-DRYRUN-3",
                    "specialist_slug": "sentinel",
                    "result_text": "Not accepted.",
                    "findings": ["Ignore."],
                    "latest_event": {"event_type": "review_note"},
                },
            ],
        }, 200)

        result = agent_learning_evidence_handler({})

        self.assertTrue(result["success"])
        self.assertIn("2 accepted agent result", result["summary"])
        self.assertIn("ledger: 1", result["summary"])
        self.assertIn("rootline: 1", result["summary"])
        self.assertEqual(result["llm_context"]["kind"], "agent_learning_evidence")
        self.assertEqual(result["llm_context"]["accepted_count"], 2)
        self.assertEqual(result["llm_context"]["accepted_by_specialist"]["ledger"], 1)
        self.assertEqual(result["llm_context"]["accepted_by_specialist"]["rootline"], 1)
        self.assertEqual(result["llm_context"]["evidence"][0]["dry_run_result_id"], "OSK-AGENT-DRYRUN-RESULT-1")
        self.assertFalse(result["llm_context"]["runtime_flags"]["dispatch_enabled"])
        self.assertFalse(result["llm_context"]["runtime_flags"]["applies_runtime_change"])
        self.assertIn("read-only", result["safety_notes"][0])

    def test_learning_influence_params_are_review_only(self):
        params = _learning_influence_params({
            "dry_run_result_id": "OSK-AGENT-DRYRUN-RESULT-C63AF980E948",
            "dry_run_request_id": "OSK-AGENT-DRYRUN-499E983FAF",
            "specialist_slug": "sentinel",
            "result_text": "Sentinel suggests checking guardrails before runtime changes.",
            "findings": ["No tools should run."],
            "latest_event": {
                "event_type": "accepted_for_learning",
                "notes": "Accepted as planning evidence.",
                "created_at": "2026-06-09T10:00:00+00:00",
            },
        })

        self.assertEqual(params["mode"], "learning_influence_proposal_only")
        self.assertEqual(params["status"], "proposed_for_owner_review")
        self.assertEqual(params["specialist_slug"], "sentinel")
        self.assertEqual(params["source_result_id"], "OSK-AGENT-DRYRUN-RESULT-C63AF980E948")
        self.assertFalse(params["applies_learning_now"])
        self.assertFalse(params["changes_prompt_now"])
        self.assertFalse(params["changes_runtime_now"])
        self.assertFalse(params["dispatch_enabled"])
        self.assertFalse(params["writes"])

    @patch("modules.oom_sakkie.learning_influence_store._record_learning_influence_params")
    @patch("modules.oom_sakkie.learning_influence_store.get_agent_dry_run_result")
    def test_learning_influence_from_result_requires_accepted_source(self, mock_get_result, mock_record):
        mock_get_result.return_value = ({
            "success": True,
            "dry_run_result": {
                "dry_run_result_id": "OSK-AGENT-DRYRUN-RESULT-1",
                "latest_event": {"event_type": "review_note"},
            },
        }, 200)

        result, status_code = record_learning_influence_proposal_from_result(
            "OSK-AGENT-DRYRUN-RESULT-1",
            database_url="postgresql://example",
        )

        self.assertEqual(status_code, 409)
        self.assertEqual(result["status"], "source_result_not_accepted_for_learning")
        self.assertFalse(result["applies_learning_now"])
        self.assertFalse(result["changes_prompt_now"])
        self.assertFalse(result["dispatch_enabled"])
        self.assertFalse(result["writes"])
        mock_record.assert_not_called()

    def test_learning_influence_from_result_requires_source_result_id(self):
        result, status_code = record_learning_influence_proposal_from_result(
            "",
            database_url="postgresql://example",
        )

        self.assertEqual(status_code, 400)
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "source_result_id_required")
        self.assertEqual(result["learning_influence_proposals"], [])
        self.assertFalse(result["applies_learning_now"])
        self.assertFalse(result["changes_prompt_now"])
        self.assertFalse(result["dispatch_enabled"])
        self.assertFalse(result["writes"])

    @patch("modules.oom_sakkie.learning_influence_store._record_learning_influence_params")
    @patch("modules.oom_sakkie.learning_influence_store.get_agent_dry_run_result")
    def test_learning_influence_from_result_records_exact_accepted_source_only(self, mock_get_result, mock_record):
        mock_get_result.return_value = ({
            "success": True,
            "dry_run_result": {
                "dry_run_result_id": "OSK-AGENT-DRYRUN-RESULT-C63AF980E948",
                "dry_run_request_id": "OSK-AGENT-DRYRUN-499E983FAF",
                "specialist_slug": "sentinel",
                "result_text": "Sentinel safety evidence.",
                "findings": ["No tool execution."],
                "latest_event": {
                    "event_type": "accepted_for_learning",
                    "notes": "Accepted.",
                    "created_at": "2026-06-10T10:00:00+00:00",
                },
            },
        }, 200)
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

        result, status_code = record_learning_influence_proposal_from_result(
            "OSK-AGENT-DRYRUN-RESULT-C63AF980E948",
            database_url="postgresql://example",
        )

        self.assertEqual(status_code, 201)
        self.assertTrue(result["success"])
        self.assertFalse(result["applies_learning_now"])
        self.assertFalse(result["changes_prompt_now"])
        self.assertFalse(result["dispatch_enabled"])
        self.assertFalse(result["writes"])
        params = mock_record.call_args.args[0]
        self.assertEqual(len(params), 1)
        self.assertEqual(params[0]["source_result_id"], "OSK-AGENT-DRYRUN-RESULT-C63AF980E948")

    @patch("modules.oom_sakkie.tools.list_learning_influence_proposals")
    def test_learning_influence_status_is_read_only(self, mock_list):
        from modules.oom_sakkie.tools import learning_influence_status_handler

        mock_list.return_value = ({
            "success": True,
            "status": "ok",
            "learning_influence_proposals": [{
                "proposal_id": "OSK-LEARNING-INFLUENCE-1",
                "proposal_title": "Learning proposal from sentinel evidence",
                "latest_event": None,
                "applies_learning_now": False,
                "changes_prompt_now": False,
                "changes_runtime_now": False,
                "dispatch_enabled": False,
                "writes": False,
            }],
        }, 200)

        result = learning_influence_status_handler({})

        self.assertTrue(result["success"])
        self.assertIn("1 waiting", result["summary"])
        self.assertEqual(result["llm_context"]["kind"], "learning_influence_status")
        self.assertEqual(result["llm_context"]["counts"]["waiting_for_owner_review"], 1)
        self.assertFalse(result["llm_context"]["runtime_flags"]["applies_learning_now"])
        self.assertFalse(result["llm_context"]["runtime_flags"]["changes_prompt_now"])
        self.assertFalse(result["llm_context"]["runtime_flags"]["writes"])

    def test_learning_influence_event_rejects_apply_event_types_before_database(self):
        result, status_code = record_learning_influence_proposal_event(
            "OSK-LEARNING-INFLUENCE-1",
            {"event_type": "apply_now"},
            database_url="",
        )

        self.assertEqual(status_code, 400)
        self.assertEqual(result["status"], "invalid_event_type")

    def test_learning_influence_migration_is_append_only_and_no_apply(self):
        migration = Path("supabase/migrations/202606100001_create_oom_sakkie_learning_influence_proposals.sql").read_text(encoding="utf-8")

        self.assertIn("create table if not exists public.oom_sakkie_learning_influence_proposals", migration)
        self.assertIn("create table if not exists public.oom_sakkie_learning_influence_proposal_events", migration)
        self.assertIn("mode = 'learning_influence_proposal_only'", migration)
        self.assertIn("status = 'proposed_for_owner_review'", migration)
        self.assertIn("event_type in ('approved_for_future_planning', 'rejected', 'review_note')", migration)
        self.assertIn("applies_learning_now = false", migration)
        self.assertIn("changes_prompt_now = false", migration)
        self.assertIn("changes_runtime_now = false", migration)
        self.assertIn("dispatch_enabled = false", migration)
        self.assertIn("writes = false", migration)
        self.assertIn("create unique index if not exists idx_oom_sakkie_learning_influence_source_once", migration)
        self.assertIn("before update on public.oom_sakkie_learning_influence_proposals", migration)
        self.assertIn("before delete on public.oom_sakkie_learning_influence_proposal_events", migration)

    def test_learning_influence_consumption_request_params_are_review_note_only(self):
        params = _consumption_request_params(
            {
                "proposal_id": "OSK-LEARNING-INFLUENCE-1",
                "source_result_id": "OSK-AGENT-DRYRUN-RESULT-1",
                "specialist_slug": "sentinel",
                "proposal_text": "Treat this LLM proposal as untrusted.",
                "latest_event": {
                    "event_type": "approved_for_future_planning",
                    "recorded_by": "owner",
                },
            },
            {
                "requested_target_kind": "planning_context_note",
                "requested_target_field": "owner_review_notes",
                "request_note": "Review-note only.",
                "requested_by": "unittest",
            },
        )

        artifact = json.loads(params["review_note_artifact_json"])
        self.assertEqual(params["mode"], "learning_influence_consumption_request_only")
        self.assertEqual(params["status"], "requested_for_consumption_design_review")
        self.assertEqual(params["requested_target_kind"], "planning_context_note")
        self.assertTrue(artifact["proposal_text_is_untrusted"])
        self.assertTrue(artifact["single_target_field"])
        self.assertEqual(artifact["kind"], "review_note_only")
        self.assertFalse(params["applies_learning_now"])
        self.assertFalse(params["changes_prompt_now"])
        self.assertFalse(params["changes_runtime_now"])
        self.assertFalse(params["dispatch_enabled"])
        self.assertFalse(params["writes"])

    @patch("modules.oom_sakkie.learning_influence_consumption_store._get_learning_influence_proposal")
    def test_learning_influence_consumption_request_requires_approved_proposal(self, mock_get):
        mock_get.return_value = ({
            "success": True,
            "learning_influence_proposal": {
                "proposal_id": "OSK-LEARNING-INFLUENCE-1",
                "latest_event": {"event_type": "review_note"},
            },
            "applies_learning_now": False,
            "changes_prompt_now": False,
            "changes_runtime_now": False,
            "dispatch_enabled": False,
            "writes": False,
        }, 200)

        result, status_code = record_learning_influence_consumption_request(
            {
                "proposal_id": "OSK-LEARNING-INFLUENCE-1",
                "requested_target_kind": "planning_context_note",
                "requested_target_field": "owner_review_notes",
            },
            database_url="postgresql://example",
        )

        self.assertEqual(status_code, 409)
        self.assertEqual(result["status"], "proposal_not_approved_for_future_planning")
        self.assertFalse(result["applies_learning_now"])
        self.assertFalse(result["changes_prompt_now"])
        self.assertFalse(result["changes_runtime_now"])
        self.assertFalse(result["dispatch_enabled"])
        self.assertFalse(result["writes"])

    def test_learning_influence_consumption_event_rejects_consumed_marker_before_database(self):
        result, status_code = record_learning_influence_consumption_event(
            "OSK-LEARNING-CONSUME-1",
            {"event_type": "consumed_for_patch_proposal"},
            database_url="postgresql://example",
        )

        self.assertEqual(status_code, 403)
        self.assertEqual(result["status"], "consumed_event_is_future_consumer_only")
        self.assertFalse(result["applies_learning_now"])
        self.assertFalse(result["changes_prompt_now"])
        self.assertFalse(result["changes_runtime_now"])
        self.assertFalse(result["dispatch_enabled"])
        self.assertFalse(result["writes"])

    def test_learning_influence_consumption_migration_is_append_only_no_apply_and_consumed_once(self):
        migration = Path("supabase/migrations/202606110001_create_oom_sakkie_learning_influence_consumption_audit_rail.sql").read_text(encoding="utf-8")

        self.assertIn("create table if not exists public.oom_sakkie_learning_influence_consumption_requests", migration)
        self.assertIn("create table if not exists public.oom_sakkie_learning_influence_consumption_events", migration)
        self.assertIn("mode = 'learning_influence_consumption_request_only'", migration)
        self.assertIn("status = 'requested_for_consumption_design_review'", migration)
        self.assertIn("requested_target_kind in (", migration)
        self.assertIn("event_type in (", migration)
        self.assertIn("'consumed_for_patch_proposal'", migration)
        self.assertIn("applies_learning_now = false", migration)
        self.assertIn("changes_prompt_now = false", migration)
        self.assertIn("changes_runtime_now = false", migration)
        self.assertIn("dispatch_enabled = false", migration)
        self.assertIn("writes = false", migration)
        self.assertIn("create unique index if not exists idx_oom_sakkie_learning_consumption_consumed_once", migration)
        self.assertIn("where event_type = 'consumed_for_patch_proposal'", migration)
        self.assertIn("before update on public.oom_sakkie_learning_influence_consumption_requests", migration)
        self.assertIn("before delete on public.oom_sakkie_learning_influence_consumption_events", migration)

    def test_agent_dry_run_request_params_force_no_execution_flags(self):
        params = _agent_dry_run_request_params({
            "specialist_slug": "sentinel",
            "owner_text": "approve first dry run",
            "dry_run_enabled": True,
            "dispatch_enabled": True,
            "runs_specialist_llm": True,
            "runs_specialist_tools": True,
            "writes": True,
        })

        self.assertEqual(params["specialist_slug"], "sentinel")
        self.assertEqual(params["mode"], "read_only_dry_run_request_only")
        self.assertEqual(params["status"], "approved_for_read_only_dry_run")
        self.assertFalse(params["dry_run_enabled"])
        self.assertFalse(params["dispatch_enabled"])
        self.assertFalse(params["runs_specialist_llm"])
        self.assertFalse(params["runs_specialist_tools"])
        self.assertFalse(params["writes"])
        self.assertIn("sentinel_dry_run_review", params["allowed_tools_json"])

    def test_agent_dry_run_request_params_allow_prism_without_execution(self):
        params = _agent_dry_run_request_params({
            "specialist_slug": "prism",
            "owner_text": "review the kiosk layout",
            "dry_run_enabled": True,
            "dispatch_enabled": True,
            "runs_specialist_llm": True,
            "runs_specialist_tools": True,
            "writes": True,
        })

        self.assertEqual(params["specialist_slug"], "prism")
        self.assertEqual(params["mode"], "read_only_dry_run_request_only")
        self.assertFalse(params["dry_run_enabled"])
        self.assertFalse(params["dispatch_enabled"])
        self.assertFalse(params["runs_specialist_llm"])
        self.assertFalse(params["runs_specialist_tools"])
        self.assertFalse(params["writes"])
        self.assertIn("system_work_status", params["allowed_tools_json"])

    def test_agent_dry_run_request_params_allow_read_only_farm_business_cohort_without_execution(self):
        expected_tools = {
            "ledger": "business_growth_brief",
            "atlas": "farm_operating_brief",
            "rootline": "irrigation_status",
            "herdmaster": "farm_attention_summary",
            "butcher": "meat_planning",
            "quartermaster": "farm_attention_summary",
        }

        for slug, expected_tool in expected_tools.items():
            with self.subTest(slug=slug):
                params = _agent_dry_run_request_params({
                    "specialist_slug": slug,
                    "owner_text": f"approve {slug} dry run",
                    "dry_run_enabled": True,
                    "dispatch_enabled": True,
                    "runs_specialist_llm": True,
                    "runs_specialist_tools": True,
                    "writes": True,
                })

                self.assertIn(slug, allowed_agent_dry_run_slugs())
                self.assertEqual(params["specialist_slug"], slug)
                self.assertEqual(params["mode"], "read_only_dry_run_request_only")
                self.assertFalse(params["dry_run_enabled"])
                self.assertFalse(params["dispatch_enabled"])
                self.assertFalse(params["runs_specialist_llm"])
                self.assertFalse(params["runs_specialist_tools"])
                self.assertFalse(params["writes"])
                self.assertIn(expected_tool, params["allowed_tools_json"])

        self.assertNotIn("beacon", allowed_agent_dry_run_slugs())
        self.assertNotIn("forge", allowed_agent_dry_run_slugs())
        self.assertNotIn("gatekeeper", allowed_agent_dry_run_slugs())

    def test_agent_dry_run_store_not_configured_and_rejects_unapproved_specialist(self):
        result, status_code = record_agent_dry_run_request({
            "specialist_slug": "sentinel",
            "owner_text": "approve first dry run",
        }, database_url="")

        self.assertEqual(status_code, 503)
        self.assertEqual(result["status"], "not_configured")

        result, status_code = record_agent_dry_run_request({
            "specialist_slug": "beacon",
            "owner_text": "approve beacon dry run",
        }, database_url="")
        self.assertEqual(status_code, 400)
        self.assertEqual(result["status"], "specialist_dry_run_not_approved_yet")

        result, status_code = list_agent_dry_run_requests(database_url="")
        self.assertEqual(status_code, 503)
        self.assertEqual(result["dry_run_requests"], [])

        result, status_code = record_agent_dry_run_event(
            "OSK-AGENT-DRYRUN-TEST",
            {"event_type": "run_now"},
            database_url="",
        )
        self.assertEqual(status_code, 400)
        self.assertEqual(result["status"], "invalid_event_type")

    def test_agent_dry_run_request_row_maps_select_tuple_positions(self):
        created_at = datetime(2026, 6, 8, tzinfo=timezone.utc)
        event_at = datetime(2026, 6, 8, 1, tzinfo=timezone.utc)
        row = (
            "OSK-AGENT-DRYRUN-ABC",
            "approved_for_read_only_dry_run",
            "read_only_dry_run_request_only",
            "sentinel",
            "owner",
            "owner text",
            "purpose",
            "OSK-TRACE",
            ["system_work_status"],
            ["No dispatch"],
            "manual_review_before_any_specialist_execution",
            False,
            False,
            False,
            False,
            False,
            created_at,
            "approved",
            "Approved only.",
            "owner",
            event_at,
        )

        mapped = _agent_dry_run_request_row(row)

        self.assertEqual(mapped["dry_run_request_id"], "OSK-AGENT-DRYRUN-ABC")
        self.assertEqual(mapped["specialist_slug"], "sentinel")
        self.assertEqual(mapped["allowed_tools"], ["system_work_status"])
        self.assertFalse(mapped["dispatch_enabled"])
        self.assertFalse(mapped["runs_specialist_llm"])
        self.assertFalse(mapped["writes"])
        self.assertEqual(mapped["latest_event"]["event_type"], "approved")
        self.assertEqual(mapped["latest_event"]["created_at"], event_at.isoformat())

    def test_agent_dry_run_handoff_is_prompt_only_and_rejects_unsafe_flags(self):
        request = _agent_dry_run_request_row((
            "OSK-AGENT-DRYRUN-ABC",
            "approved_for_read_only_dry_run",
            "read_only_dry_run_request_only",
            "sentinel",
            "owner",
            "Check if Sentinel is ready to review the system.",
            "First Sentinel dry-run request.",
            "OSK-TRACE-1",
            ["system_work_status", "sentinel_dry_run_review"],
            ["No live specialist dispatch.", "Owner must review output."],
            "manual_review_before_any_specialist_execution",
            False,
            False,
            False,
            False,
            False,
            datetime(2026, 6, 8, tzinfo=timezone.utc),
            "approved",
            "record only",
            "owner",
            datetime(2026, 6, 8, 1, tzinfo=timezone.utc),
        ))

        packet, status_code = build_agent_dry_run_handoff(request)

        self.assertEqual(status_code, 200)
        self.assertEqual(packet["mode"], "agent_dry_run_handoff_only")
        self.assertEqual(packet["specialist_slug"], "sentinel")
        self.assertFalse(packet["runs_specialist"])
        self.assertFalse(packet["runs_specialist_llm"])
        self.assertFalse(packet["runs_specialist_tools"])
        self.assertFalse(packet["dispatch_enabled"])
        self.assertFalse(packet["writes"])
        self.assertTrue(packet["requires_owner_execution_approval"])
        self.assertIn("Do not call tools", packet["prompt"])
        self.assertIn("Do not claim you inspected anything yet", packet["prompt"])

        unsafe = dict(request)
        unsafe["runs_specialist_llm"] = True
        rejected, rejected_status = build_agent_dry_run_handoff(unsafe)
        self.assertEqual(rejected_status, 400)
        self.assertEqual(rejected["status"], "unsafe_dry_run_request_flags")
        self.assertIn("runs_specialist_llm", rejected["unsafe_flags"])

    def test_prism_dry_run_handoff_is_prompt_only(self):
        request = _agent_dry_run_request_row((
            "OSK-AGENT-DRYRUN-PRISM",
            "approved_for_read_only_dry_run",
            "read_only_dry_run_request_only",
            "prism",
            "owner",
            "Review the kiosk layout.",
            "Future Prism dry-run request.",
            "",
            ["system_work_status"],
            ["No generated assets.", "Owner must review output."],
            "manual_review_before_any_specialist_execution",
            False,
            False,
            False,
            False,
            False,
            datetime(2026, 6, 9, tzinfo=timezone.utc),
            None,
            None,
            None,
            None,
        ))

        packet, status_code = build_agent_dry_run_handoff(request)

        self.assertEqual(status_code, 200)
        self.assertEqual(packet["mode"], "agent_dry_run_handoff_only")
        self.assertEqual(packet["specialist_slug"], "prism")
        self.assertEqual(packet["specialist_name"], "Prism")
        self.assertFalse(packet["runs_specialist"])
        self.assertFalse(packet["runs_specialist_llm"])
        self.assertFalse(packet["runs_specialist_tools"])
        self.assertFalse(packet["dispatch_enabled"])
        self.assertFalse(packet["writes"])
        self.assertIn("You are Prism", packet["prompt"])
        self.assertIn("Do not call tools", packet["prompt"])

    def test_ledger_dry_run_handoff_is_prompt_only(self):
        request = _agent_dry_run_request_row((
            "OSK-AGENT-DRYRUN-LEDGER",
            "approved_for_read_only_dry_run",
            "read_only_dry_run_request_only",
            "ledger",
            "owner",
            "Review what we should sell next.",
            "Future Ledger dry-run request.",
            "",
            ["business_growth_brief", "sales_dashboard", "meat_planning"],
            ["No customer message.", "Owner must review output."],
            "manual_review_before_any_specialist_execution",
            False,
            False,
            False,
            False,
            False,
            datetime(2026, 6, 9, tzinfo=timezone.utc),
            None,
            None,
            None,
            None,
        ))

        packet, status_code = build_agent_dry_run_handoff(request)

        self.assertEqual(status_code, 200)
        self.assertEqual(packet["mode"], "agent_dry_run_handoff_only")
        self.assertEqual(packet["specialist_slug"], "ledger")
        self.assertEqual(packet["specialist_name"], "Ledger")
        self.assertFalse(packet["runs_specialist"])
        self.assertFalse(packet["runs_specialist_llm"])
        self.assertFalse(packet["runs_specialist_tools"])
        self.assertFalse(packet["dispatch_enabled"])
        self.assertFalse(packet["writes"])
        self.assertIn("You are Ledger", packet["prompt"])
        self.assertIn("business and profit reviewer", packet["prompt"])
        self.assertIn("business growth brief", packet["required_context"])
        self.assertIn("unapproved price change", packet["risk_checks"])
        self.assertIn("customer messages", packet["prompt"])
        self.assertIn("read-only business review", packet["owner_approval_question"])
        self.assertIn("Do not call tools", packet["prompt"])

    def test_rootline_dry_run_handoff_names_physical_control_risks(self):
        request = _agent_dry_run_request_row((
            "OSK-AGENT-DRYRUN-ROOTLINE",
            "approved_for_read_only_dry_run",
            "read_only_dry_run_request_only",
            "rootline",
            "owner",
            "Review whether we need to water anything.",
            "Future Rootline dry-run request.",
            "",
            ["weather_now", "weather_today", "weather_forecast", "irrigation_status"],
            ["No pump control.", "Owner must review output."],
            "manual_review_before_any_specialist_execution",
            False,
            False,
            False,
            False,
            False,
            datetime(2026, 6, 9, tzinfo=timezone.utc),
            None,
            None,
            None,
            None,
        ))

        packet, status_code = build_agent_dry_run_handoff(request)

        self.assertEqual(status_code, 200)
        self.assertEqual(packet["specialist_slug"], "rootline")
        self.assertEqual(packet["specialist_name"], "Rootline")
        self.assertFalse(packet["runs_specialist"])
        self.assertFalse(packet["runs_specialist_llm"])
        self.assertFalse(packet["runs_specialist_tools"])
        self.assertFalse(packet["dispatch_enabled"])
        self.assertFalse(packet["writes"])
        self.assertIn("weather today", packet["required_context"])
        self.assertIn("pump/control command", packet["risk_checks"])
        self.assertIn("Do not write farm data", packet["prompt"])
        self.assertIn("read-only weather/irrigation review", packet["owner_approval_question"])

    def test_agent_dry_run_migration_is_append_only_and_no_execution(self):
        migration = Path("supabase/migrations/202606080001_create_oom_sakkie_agent_dry_runs.sql").read_text(encoding="utf-8")

        self.assertIn("create table if not exists public.oom_sakkie_agent_dry_run_requests", migration)
        self.assertIn("mode = 'read_only_dry_run_request_only'", migration)
        self.assertIn("dry_run_enabled = false", migration)
        self.assertIn("dispatch_enabled = false", migration)
        self.assertIn("runs_specialist_llm = false", migration)
        self.assertIn("runs_specialist_tools = false", migration)
        self.assertIn("writes = false", migration)
        self.assertIn("before update on public.oom_sakkie_agent_dry_run_requests", migration)
        self.assertIn("before delete on public.oom_sakkie_agent_dry_run_events", migration)

    def test_dispatch_request_params_force_no_execution_flags(self):
        params = _dispatch_request_params({
            "specialist_slug": "sentinel",
            "owner_text": "design dispatch rail",
            "dispatch_enabled": True,
            "runs_specialist_llm": True,
            "runs_specialist_tools": True,
            "writes": True,
            "applies_runtime_change": True,
        })

        self.assertEqual(params["mode"], "dispatch_decision_request_only")
        self.assertEqual(params["status"], "requested_for_dispatch_design_review")
        self.assertFalse(params["dispatch_enabled"])
        self.assertFalse(params["runs_specialist_llm"])
        self.assertFalse(params["runs_specialist_tools"])
        self.assertFalse(params["writes"])
        self.assertFalse(params["applies_runtime_change"])
        self.assertIn("owner_and_claude_review", params["next_gate"])

    @patch.dict(os.environ, {}, clear=True)
    def test_dispatch_request_rejects_locked_out_specialist_before_database(self):
        result, status_code = record_dispatch_request({
            "specialist_slug": "forge",
            "owner_text": "try dispatch",
        })

        self.assertEqual(status_code, 400)
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "specialist_dispatch_design_not_approved_yet")

    @patch("modules.oom_sakkie.dispatch_decision_store.get_dispatch_request")
    @patch.dict(os.environ, {}, clear=True)
    def test_dispatch_decision_validates_event_type_before_database(self, mock_get_request):
        result, status_code = record_dispatch_decision("OSK-DISPATCH-REQ-1", {"decision_type": "run_now"})

        self.assertEqual(status_code, 400)
        self.assertEqual(result["status"], "invalid_decision_type")
        self.assertEqual(set(result["allowed_decision_types"]), DISPATCH_DECISION_TYPES)
        mock_get_request.assert_not_called()

    def test_dispatch_decision_migration_is_append_only_and_no_execution(self):
        migration = Path("supabase/migrations/202606090001_create_oom_sakkie_dispatch_decisions.sql").read_text(encoding="utf-8")

        self.assertIn("create table if not exists public.oom_sakkie_dispatch_requests", migration)
        self.assertIn("create table if not exists public.oom_sakkie_dispatch_decisions", migration)
        self.assertIn("mode = 'dispatch_decision_request_only'", migration)
        self.assertIn("dispatch_enabled = false", migration)
        self.assertIn("runs_specialist_llm = false", migration)
        self.assertIn("runs_specialist_tools = false", migration)
        self.assertIn("writes = false", migration)
        self.assertIn("applies_runtime_change = false", migration)
        self.assertIn("decision_type in ('approved_for_design_review', 'rejected', 'deferred', 'review_note')", migration)
        self.assertIn("before update on public.oom_sakkie_dispatch_requests", migration)
        self.assertIn("before delete on public.oom_sakkie_dispatch_decisions", migration)

    def test_dispatch_execution_approval_params_force_no_execution_flags(self):
        params = _dispatch_execution_approval_params({
            "dispatch_request_id": "OSK-DISPATCH-REQ-1",
            "specialist_slug": "sentinel",
        }, {
            "approval_type": "approved_for_single_dry_run_execution",
            "executes_now": True,
            "dispatch_enabled": True,
            "runs_specialist_llm": True,
            "runs_specialist_tools": True,
            "writes": True,
            "applies_runtime_change": True,
            "dispatches_further": True,
        })

        self.assertEqual(params["mode"], "single_dry_run_execution_approval_only")
        self.assertEqual(params["status"], "recorded_for_single_dry_run_execution_gate")
        self.assertEqual(params["specialist_slug"], "sentinel")
        self.assertFalse(params["executes_now"])
        self.assertFalse(params["dispatch_enabled"])
        self.assertFalse(params["runs_specialist_llm"])
        self.assertFalse(params["runs_specialist_tools"])
        self.assertFalse(params["writes"])
        self.assertFalse(params["applies_runtime_change"])
        self.assertFalse(params["dispatches_further"])
        self.assertIn("implementation_diff_review", params["next_gate"])

    @patch("modules.oom_sakkie.dispatch_execution_approval_store.get_dispatch_request")
    @patch.dict(os.environ, {}, clear=True)
    def test_dispatch_execution_approval_validates_type_before_database(self, mock_get_request):
        result, status_code = record_dispatch_execution_approval("OSK-DISPATCH-REQ-1", {"approval_type": "run_now"})

        self.assertEqual(status_code, 400)
        self.assertEqual(result["status"], "invalid_approval_type")
        self.assertEqual(set(result["allowed_approval_types"]), DISPATCH_EXECUTION_APPROVAL_TYPES)
        mock_get_request.assert_not_called()

    @patch("modules.oom_sakkie.dispatch_execution_approval_store.get_dispatch_request")
    @patch.dict(os.environ, {}, clear=True)
    def test_dispatch_execution_approval_requires_design_approval(self, mock_get_request):
        mock_get_request.return_value = ({
            "success": True,
            "dispatch_request": {
                "dispatch_request_id": "OSK-DISPATCH-REQ-1",
                "specialist_slug": "sentinel",
                "latest_decision": {"decision_type": "deferred"},
            },
        }, 200)

        result, status_code = record_dispatch_execution_approval(
            "OSK-DISPATCH-REQ-1",
            {"approval_type": "approved_for_single_dry_run_execution"},
        )

        self.assertEqual(status_code, 409)
        self.assertEqual(result["status"], "dispatch_design_not_approved")

    @patch("modules.oom_sakkie.dispatch_execution_approval_store.get_dispatch_request")
    @patch.dict(os.environ, {}, clear=True)
    def test_dispatch_execution_approval_is_sentinel_only(self, mock_get_request):
        mock_get_request.return_value = ({
            "success": True,
            "dispatch_request": {
                "dispatch_request_id": "OSK-DISPATCH-REQ-1",
                "specialist_slug": "prism",
                "latest_decision": {"decision_type": "approved_for_design_review"},
            },
        }, 200)

        result, status_code = record_dispatch_execution_approval(
            "OSK-DISPATCH-REQ-1",
            {"approval_type": "approved_for_single_dry_run_execution"},
        )

        self.assertEqual(status_code, 400)
        self.assertEqual(result["status"], "single_dry_run_execution_gate_is_sentinel_only")

    @patch.dict(os.environ, {}, clear=True)
    def test_dispatch_execution_consumed_event_is_runner_only(self):
        result, status_code = record_dispatch_execution_approval_event(
            "OSK-DISPATCH-EXEC-APPROVAL-1",
            {"event_type": "consumed_by_single_dry_run_result"},
        )

        self.assertEqual(status_code, 403)
        self.assertEqual(result["status"], "consumed_event_is_runner_only")

    def test_dispatch_execution_approval_migration_is_append_only_and_no_execution(self):
        migration = Path("supabase/migrations/202606090002_create_oom_sakkie_dispatch_execution_approvals.sql").read_text(encoding="utf-8")

        self.assertIn("create table if not exists public.oom_sakkie_dispatch_execution_approvals", migration)
        self.assertIn("create table if not exists public.oom_sakkie_dispatch_execution_approval_events", migration)
        self.assertIn("mode = 'single_dry_run_execution_approval_only'", migration)
        self.assertIn("approval_type in ('approved_for_single_dry_run_execution', 'rejected', 'deferred', 'review_note')", migration)
        self.assertIn("specialist_slug = 'sentinel'", migration)
        self.assertIn("executes_now = false", migration)
        self.assertIn("dispatch_enabled = false", migration)
        self.assertIn("runs_specialist_llm = false", migration)
        self.assertIn("runs_specialist_tools = false", migration)
        self.assertIn("writes = false", migration)
        self.assertIn("applies_runtime_change = false", migration)
        self.assertIn("dispatches_further = false", migration)
        self.assertIn("create unique index if not exists idx_oom_sakkie_dispatch_execution_approval_consumed_once", migration)
        self.assertIn("where event_type = 'consumed_by_single_dry_run_result'", migration)
        self.assertIn("before update on public.oom_sakkie_dispatch_execution_approvals", migration)
        self.assertIn("before delete on public.oom_sakkie_dispatch_execution_approval_events", migration)

    def test_single_shot_sentinel_result_params_are_honest_but_no_tools_or_writes(self):
        params = _sentinel_single_shot_result_params({
            "dry_run_request_id": "OSK-AGENT-DRYRUN-SENTINEL",
            "specialist_slug": SENTINEL_SINGLE_SHOT_SPECIALIST,
        }, {
            "approval_id": "OSK-DISPATCH-EXEC-APPROVAL-1",
            "result_text": "Sentinel reviewed the gate.",
            "findings": ["No tools should run."],
        })

        self.assertEqual(
            {key: params[key] for key in ("mode", "status", "specialist_slug")},
            sentinel_single_shot_identity(),
        )
        for flag, expected in sentinel_single_shot_result_flags().items():
            self.assertEqual(params[flag], expected)

    def test_single_shot_contract_flags_are_used_by_review_validation(self):
        valid = {
            **sentinel_single_shot_identity(),
            **sentinel_single_shot_result_flags(),
        }
        self.assertEqual(sentinel_single_shot_flag_errors(valid), [])

        for flag in SENTINEL_SINGLE_SHOT_FORBIDDEN_TRUE_FLAGS:
            unsafe = dict(valid)
            unsafe[flag] = True
            self.assertEqual(sentinel_single_shot_flag_errors(unsafe), [flag])

        for flag in SENTINEL_SINGLE_SHOT_REQUIRED_TRUE_FLAGS:
            unsafe = dict(valid)
            unsafe[flag] = False
            self.assertEqual(sentinel_single_shot_flag_errors(unsafe), [f"missing_{flag}"])

    def test_single_shot_sentinel_result_migration_adds_narrow_result_mode(self):
        migration = Path("supabase/migrations/202606090003_allow_single_shot_sentinel_dry_run_results.sql").read_text(encoding="utf-8")

        self.assertIn(SENTINEL_SINGLE_SHOT_RESULT_MODE, migration)
        self.assertIn(SENTINEL_SINGLE_SHOT_RESULT_STATUS, migration)
        self.assertIn(f"specialist_slug = '{SENTINEL_SINGLE_SHOT_SPECIALIST}'", migration)
        for flag, expected in sentinel_single_shot_result_flags().items():
            self.assertIn(f"{flag} = {str(expected).lower()}", migration)
        self.assertIn("mode = 'dry_run_result_review_only'", migration)

    @patch("modules.oom_sakkie.sentinel_single_shot_runner.urllib_request.urlopen")
    @patch.dict(os.environ, {}, clear=True)
    def test_sentinel_single_shot_runner_refuses_when_env_disabled_before_network(self, mock_urlopen):
        result, status_code = run_sentinel_single_shot_dry_run("OSK-DISPATCH-EXEC-APPROVAL-1")

        self.assertEqual(status_code, 403)
        self.assertEqual(result["status"], "specialist_dry_run_disabled")
        self.assertFalse(result["runs_specialist_llm"])
        self.assertFalse(result["runs_specialist_tools"])
        self.assertFalse(result["writes"])
        mock_urlopen.assert_not_called()

    @patch("modules.oom_sakkie.sentinel_single_shot_runner.urllib_request.urlopen")
    @patch("modules.oom_sakkie.sentinel_single_shot_runner.dispatch_execution_approval_consumed")
    @patch("modules.oom_sakkie.sentinel_single_shot_runner.get_dispatch_request")
    @patch("modules.oom_sakkie.sentinel_single_shot_runner.get_dispatch_execution_approval")
    @patch.dict(os.environ, {
        "OOM_SAKKIE_SPECIALIST_DRYRUN_ENABLED": "1",
        "OOM_SAKKIE_LLM_ROUTER_MODEL": "gpt-test",
        "OPENAI_API_KEY": "test-key",
    }, clear=True)
    def test_sentinel_single_shot_runner_refuses_consumed_approval_before_network(
        self,
        mock_get_approval,
        mock_get_dispatch,
        mock_consumed,
        mock_urlopen,
    ):
        mock_get_approval.return_value = ({
            "success": True,
            "execution_approval": {
                "approval_id": "OSK-DISPATCH-EXEC-APPROVAL-1",
                "dispatch_request_id": "OSK-DISPATCH-REQ-1",
                "specialist_slug": "sentinel",
                "approval_type": "approved_for_single_dry_run_execution",
                "one_shot_scope": {"dry_run_request_id": "OSK-AGENT-DRYRUN-1"},
            },
        }, 200)
        mock_get_dispatch.return_value = ({
            "success": True,
            "dispatch_request": {
                "dispatch_request_id": "OSK-DISPATCH-REQ-1",
                "specialist_slug": "sentinel",
                "latest_decision": {"decision_type": "approved_for_design_review"},
            },
        }, 200)
        mock_consumed.return_value = ({"success": True, "consumed": True}, 200)

        result, status_code = run_sentinel_single_shot_dry_run("OSK-DISPATCH-EXEC-APPROVAL-1")

        self.assertEqual(status_code, 409)
        self.assertEqual(result["status"], "dispatch_execution_approval_already_consumed")
        mock_urlopen.assert_not_called()

    @patch("modules.oom_sakkie.sentinel_single_shot_runner.urllib_request.urlopen")
    @patch("modules.oom_sakkie.sentinel_single_shot_runner.get_dispatch_execution_approval")
    @patch.dict(os.environ, {
        "OOM_SAKKIE_SPECIALIST_DRYRUN_ENABLED": "1",
        "OOM_SAKKIE_LLM_ROUTER_MODEL": "gpt-test",
        "OPENAI_API_KEY": "test-key",
    }, clear=True)
    def test_sentinel_single_shot_runner_refuses_missing_approval_before_network(self, mock_get_approval, mock_urlopen):
        mock_get_approval.return_value = ({
            "success": False,
            "status": "dispatch_execution_approval_not_found",
        }, 404)

        result, status_code = run_sentinel_single_shot_dry_run("OSK-DISPATCH-EXEC-APPROVAL-MISSING")

        self.assertEqual(status_code, 404)
        self.assertEqual(result["status"], "dispatch_execution_approval_not_found")
        mock_urlopen.assert_not_called()

    @patch("modules.oom_sakkie.sentinel_single_shot_runner.record_sentinel_single_shot_result")
    @patch("modules.oom_sakkie.sentinel_single_shot_runner.record_dispatch_execution_approval_event")
    @patch("modules.oom_sakkie.sentinel_single_shot_runner.urllib_request.urlopen")
    @patch("modules.oom_sakkie.sentinel_single_shot_runner.dispatch_execution_approval_consumed")
    @patch("modules.oom_sakkie.sentinel_single_shot_runner.get_dispatch_request")
    @patch("modules.oom_sakkie.sentinel_single_shot_runner.get_dispatch_execution_approval")
    @patch.dict(os.environ, {
        "OOM_SAKKIE_SPECIALIST_DRYRUN_ENABLED": "1",
        "OOM_SAKKIE_LLM_ROUTER_MODEL": "gpt-test",
        "OPENAI_API_KEY": "test-key",
    }, clear=True)
    def test_sentinel_single_shot_runner_success_writes_append_only_result(
        self,
        mock_get_approval,
        mock_get_dispatch,
        mock_consumed,
        mock_urlopen,
        mock_record_event,
        mock_record_result,
    ):
        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return json.dumps({
                    "choices": [{
                        "message": {
                            "content": json.dumps({
                                "result_text": "Sentinel reviewed the approval gate and found it advisory-only.",
                                "findings": ["No tools should run.", "Owner review remains required."],
                            })
                        }
                    }]
                }).encode("utf-8")

        mock_get_approval.return_value = ({
            "success": True,
            "execution_approval": {
                "approval_id": "OSK-DISPATCH-EXEC-APPROVAL-1",
                "dispatch_request_id": "OSK-DISPATCH-REQ-1",
                "specialist_slug": "sentinel",
                "approval_type": "approved_for_single_dry_run_execution",
                "one_shot_scope": {"dry_run_request_id": "OSK-AGENT-DRYRUN-1"},
            },
        }, 200)
        mock_get_dispatch.return_value = ({
            "success": True,
            "dispatch_request": {
                "dispatch_request_id": "OSK-DISPATCH-REQ-1",
                "specialist_slug": "sentinel",
                "latest_decision": {"decision_type": "approved_for_design_review"},
            },
        }, 200)
        mock_consumed.return_value = ({"success": True, "consumed": False}, 200)
        mock_record_event.return_value = ({"success": True, "event_id": "OSK-EVENT-1"}, 201)
        mock_record_result.return_value = ({
            "success": True,
            "dry_run_result_id": "OSK-AGENT-DRYRUN-RESULT-1",
        }, 201)
        mock_urlopen.return_value = FakeResponse()

        result, status_code = run_sentinel_single_shot_dry_run("OSK-DISPATCH-EXEC-APPROVAL-1")

        self.assertEqual(status_code, 201)
        self.assertTrue(result["success"])
        self.assertEqual(result["mode"], "single_shot_sentinel_advisory_result")
        self.assertTrue(result["runs_specialist_llm"])
        self.assertFalse(result["runs_specialist_tools"])
        self.assertFalse(result["writes"])
        self.assertFalse(result["dispatches_further"])
        mock_record_event.assert_called_once()
        mock_urlopen.assert_called_once()
        mock_record_result.assert_called_once()

    def test_sentinel_single_shot_response_rejects_unsafe_action_claims(self):
        body = {
            "choices": [{
                "message": {
                    "content": "{\"result_text\":\"I updated the guardrails.\",\"findings\":[\"unsafe\"]}"
                }
            }]
        }

        self.assertIsNone(parse_sentinel_single_shot_response(json.dumps(body)))

    @patch.dict(os.environ, {
        "OOM_SAKKIE_SPECIALIST_DRYRUN_ENABLED": "1",
        "OOM_SAKKIE_LLM_ROUTER_MODEL": "gpt-test",
        "OPENAI_API_KEY": "test-key",
    }, clear=True)
    def test_specialist_dry_run_policy_exposes_egress_and_no_write(self):
        policy = specialist_dry_run_policy()

        self.assertTrue(policy["enabled"])
        self.assertTrue(policy["configured"])
        self.assertEqual(policy["specialist_slug"], SENTINEL_SINGLE_SHOT_SPECIALIST)
        self.assertEqual(policy["mode"], SENTINEL_SINGLE_SHOT_POLICY_MODE)
        self.assertFalse(policy["runs_specialist_tools"])
        self.assertFalse(policy["writes"])
        self.assertFalse(policy["dispatches_further"])

    def test_agent_dry_run_result_params_force_review_only_flags(self):
        params = _agent_dry_run_result_params({
            "dry_run_request_id": "OSK-AGENT-DRYRUN-1",
            "specialist_slug": "sentinel",
        }, {
            "result_text": "Sentinel would inspect tool safety.",
            "findings": ["Review tool allowlist."],
            "runs_specialist": True,
            "dispatch_enabled": True,
            "runs_specialist_llm": True,
            "runs_specialist_tools": True,
            "writes": True,
            "applies_runtime_change": True,
        })

        self.assertEqual(params["mode"], "dry_run_result_review_only")
        self.assertEqual(params["specialist_slug"], "sentinel")
        self.assertEqual(params["status"], "recorded_for_owner_review")
        self.assertFalse(params["runs_specialist"])
        self.assertFalse(params["dispatch_enabled"])
        self.assertFalse(params["runs_specialist_llm"])
        self.assertFalse(params["runs_specialist_tools"])
        self.assertFalse(params["writes"])
        self.assertFalse(params["applies_runtime_change"])
        self.assertIn("Review tool allowlist", params["findings_json"])

    def test_agent_dry_run_result_params_preserve_approved_specialist_slug(self):
        params = _agent_dry_run_result_params({
            "dry_run_request_id": "OSK-AGENT-DRYRUN-PRISM",
            "specialist_slug": "prism",
        }, {
            "result_text": "Prism would review the layout.",
            "findings": ["Panel density is high."],
        })

        self.assertEqual(params["specialist_slug"], "prism")
        self.assertEqual(params["mode"], "dry_run_result_review_only")
        self.assertFalse(params["runs_specialist"])
        self.assertFalse(params["dispatch_enabled"])
        self.assertFalse(params["runs_specialist_llm"])
        self.assertFalse(params["runs_specialist_tools"])
        self.assertFalse(params["writes"])
        self.assertFalse(params["applies_runtime_change"])

    def test_agent_dry_run_result_row_maps_select_tuple_positions(self):
        created_at = datetime(2026, 6, 8, tzinfo=timezone.utc)
        event_at = datetime(2026, 6, 8, 1, tzinfo=timezone.utc)
        row = (
            "OSK-AGENT-DRYRUN-RESULT-ABC",
            "OSK-AGENT-DRYRUN-ABC",
            "recorded_for_owner_review",
            "dry_run_result_review_only",
            "sentinel",
            "Sentinel result.",
            ["Risk one"],
            "owner_review_before_learning_or_runtime_change",
            "owner",
            False,
            False,
            False,
            False,
            False,
            False,
            created_at,
            "accepted_for_learning",
            "accepted",
            "owner",
            event_at,
        )

        mapped = _agent_dry_run_result_row(row)

        self.assertEqual(mapped["dry_run_result_id"], "OSK-AGENT-DRYRUN-RESULT-ABC")
        self.assertEqual(mapped["dry_run_request_id"], "OSK-AGENT-DRYRUN-ABC")
        self.assertEqual(mapped["findings"], ["Risk one"])
        self.assertFalse(mapped["runs_specialist"])
        self.assertFalse(mapped["dispatch_enabled"])
        self.assertFalse(mapped["runs_specialist_llm"])
        self.assertFalse(mapped["runs_specialist_tools"])
        self.assertFalse(mapped["writes"])
        self.assertFalse(mapped["applies_runtime_change"])
        self.assertEqual(mapped["latest_event"]["event_type"], "accepted_for_learning")

    def test_agent_dry_run_result_store_not_configured_and_invalid_event(self):
        results, status_code = list_agent_dry_run_results(database_url="")
        self.assertEqual(status_code, 503)
        self.assertEqual(results["status"], "not_configured")
        self.assertEqual(results["dry_run_results"], [])

        detail, detail_status = get_agent_dry_run_result("OSK-AGENT-DRYRUN-RESULT-ABC", database_url="")
        self.assertEqual(detail_status, 503)
        self.assertEqual(detail["status"], "not_configured")

        event, event_status = record_agent_dry_run_result_event(
            "OSK-AGENT-DRYRUN-RESULT-ABC",
            {"event_type": "run_now"},
            database_url="",
        )
        self.assertEqual(event_status, 400)
        self.assertEqual(event["status"], "invalid_event_type")

    def test_agent_dry_run_result_review_packet_is_review_only(self):
        packet, status_code = build_agent_dry_run_result_review_packet({
            "dry_run_result_id": "OSK-AGENT-DRYRUN-RESULT-ABC",
            "dry_run_request_id": "OSK-AGENT-DRYRUN-ABC",
            "mode": "dry_run_result_review_only",
            "specialist_slug": "sentinel",
            "result_text": "Sentinel found a routing guard to review.",
            "findings": ["Keep dry-run review-only."],
            "recommended_next_gate": "owner_review_before_learning_or_runtime_change",
            "runs_specialist": False,
            "dispatch_enabled": False,
            "runs_specialist_llm": False,
            "runs_specialist_tools": False,
            "writes": False,
            "applies_runtime_change": False,
            "latest_event": None,
        })

        self.assertEqual(status_code, 200)
        self.assertEqual(packet["mode"], "dry_run_result_review_packet")
        self.assertEqual(packet["dry_run_result_id"], "OSK-AGENT-DRYRUN-RESULT-ABC")
        self.assertEqual(packet["owner_options"][0]["event_type"], "accepted_for_learning")
        self.assertTrue(packet["review_guard"]["review_only"])
        self.assertFalse(packet["review_guard"]["runs_specialist"])
        self.assertFalse(packet["review_guard"]["dispatch_enabled"])
        self.assertFalse(packet["review_guard"]["runs_specialist_llm"])
        self.assertFalse(packet["review_guard"]["runs_specialist_tools"])
        self.assertFalse(packet["review_guard"]["writes"])
        self.assertFalse(packet["review_guard"]["applies_runtime_change"])
        self.assertIn("Owner should accept", packet["next_action"])

    def test_agent_dry_run_result_review_packet_classifies_business_evidence_without_unlocking_actions(self):
        packet, status_code = build_agent_dry_run_result_review_packet({
            "dry_run_result_id": "OSK-AGENT-DRYRUN-RESULT-LEDGER",
            "dry_run_request_id": "OSK-AGENT-DRYRUN-LEDGER",
            "specialist_slug": "ledger",
            "mode": "dry_run_result_review_only",
            "result_text": "Ledger would ask for margin data before deciding the next offer.",
            "findings": ["No price change should happen yet."],
            "recommended_next_gate": "owner_review_before_learning_or_runtime_change",
            "runs_specialist": False,
            "dispatch_enabled": False,
            "runs_specialist_llm": False,
            "runs_specialist_tools": False,
            "writes": False,
            "applies_runtime_change": False,
        })

        self.assertEqual(status_code, 200)
        self.assertEqual(packet["specialist_slug"], "ledger")
        self.assertEqual(packet["evidence_kind"], "business_review_evidence")
        self.assertIn("future business brief questions", packet["may_influence"])
        self.assertIn("customer messages", packet["must_not_influence"])
        self.assertIn("price changes", packet["must_not_influence"])
        self.assertFalse(packet["review_guard"]["dispatch_enabled"])
        self.assertFalse(packet["review_guard"]["applies_runtime_change"])

    def test_agent_dry_run_result_review_packet_classifies_rootline_physical_control_boundary(self):
        packet, status_code = build_agent_dry_run_result_review_packet({
            "dry_run_result_id": "OSK-AGENT-DRYRUN-RESULT-ROOTLINE",
            "dry_run_request_id": "OSK-AGENT-DRYRUN-ROOTLINE",
            "specialist_slug": "rootline",
            "mode": "dry_run_result_review_only",
            "result_text": "Rootline would inspect stale weather before any irrigation decision.",
            "findings": ["Do not control pump."],
            "recommended_next_gate": "owner_review_before_learning_or_runtime_change",
            "runs_specialist": False,
            "dispatch_enabled": False,
            "runs_specialist_llm": False,
            "runs_specialist_tools": False,
            "writes": False,
            "applies_runtime_change": False,
        })

        self.assertEqual(status_code, 200)
        self.assertEqual(packet["specialist_slug"], "rootline")
        self.assertEqual(packet["evidence_kind"], "weather_irrigation_review_evidence")
        self.assertIn("future weather/irrigation inspection questions", packet["may_influence"])
        self.assertIn("pump or valve commands", packet["must_not_influence"])
        self.assertIn("physical controls", packet["must_not_influence"])
        self.assertFalse(packet["review_guard"]["runs_specialist_tools"])
        self.assertFalse(packet["review_guard"]["writes"])

    def test_agent_dry_run_result_review_packet_rejects_execution_flags(self):
        packet, status_code = build_agent_dry_run_result_review_packet({
            "dry_run_result_id": "OSK-AGENT-DRYRUN-RESULT-ABC",
            "mode": "dry_run_result_review_only",
            "runs_specialist": True,
            "dispatch_enabled": False,
            "runs_specialist_llm": False,
            "runs_specialist_tools": False,
            "writes": False,
            "applies_runtime_change": False,
        })

        self.assertEqual(status_code, 400)
        self.assertEqual(packet["status"], "dry_run_result_has_execution_flags")
        self.assertIn("runs_specialist", packet["unsafe_flags"])

    def test_agent_dry_run_result_review_packet_allows_single_shot_sentinel_result(self):
        packet, status_code = build_agent_dry_run_result_review_packet({
            "dry_run_result_id": "OSK-AGENT-DRYRUN-RESULT-SINGLE",
            "dry_run_request_id": "OSK-AGENT-DRYRUN-SINGLE",
            "mode": "single_shot_sentinel_advisory_result",
            "status": "recorded_from_single_shot_sentinel_llm",
            "specialist_slug": "sentinel",
            "result_text": "Sentinel reviewed the gate and did not run tools.",
            "findings": ["One-shot advisory only."],
            "recommended_next_gate": "owner_review_before_learning_or_runtime_change",
            "runs_specialist": True,
            "dispatch_enabled": False,
            "runs_specialist_llm": True,
            "runs_specialist_tools": False,
            "writes": False,
            "applies_runtime_change": False,
            "latest_event": None,
        })

        self.assertEqual(status_code, 200)
        self.assertEqual(packet["mode"], "dry_run_result_review_packet")
        self.assertEqual(packet["specialist_slug"], "sentinel")
        self.assertEqual(packet["evidence_kind"], "safety_guardrail_evidence")
        self.assertFalse(packet["review_guard"]["runs_specialist"])
        self.assertFalse(packet["review_guard"]["runs_specialist_llm"])
        self.assertFalse(packet["review_guard"]["runs_specialist_tools"])
        self.assertFalse(packet["review_guard"]["writes"])
        self.assertIn("Owner should accept", packet["next_action"])

    def test_agent_dry_run_result_review_packet_rejects_unsafe_single_shot_flags(self):
        packet, status_code = build_agent_dry_run_result_review_packet({
            "dry_run_result_id": "OSK-AGENT-DRYRUN-RESULT-SINGLE",
            "mode": "single_shot_sentinel_advisory_result",
            "status": "recorded_from_single_shot_sentinel_llm",
            "specialist_slug": "sentinel",
            "runs_specialist": True,
            "dispatch_enabled": False,
            "runs_specialist_llm": True,
            "runs_specialist_tools": True,
            "writes": False,
            "applies_runtime_change": False,
        })

        self.assertEqual(status_code, 400)
        self.assertEqual(packet["status"], "dry_run_result_has_execution_flags")
        self.assertIn("runs_specialist_tools", packet["unsafe_flags"])

    def test_agent_dry_run_result_migration_is_append_only_and_no_execution(self):
        migration = Path("supabase/migrations/202606080002_create_oom_sakkie_agent_dry_run_results.sql").read_text(encoding="utf-8")

        self.assertIn("create table if not exists public.oom_sakkie_agent_dry_run_results", migration)
        self.assertIn("mode = 'dry_run_result_review_only'", migration)
        self.assertIn("runs_specialist = false", migration)
        self.assertIn("dispatch_enabled = false", migration)
        self.assertIn("runs_specialist_llm = false", migration)
        self.assertIn("runs_specialist_tools = false", migration)
        self.assertIn("writes = false", migration)
        self.assertIn("applies_runtime_change = false", migration)
        self.assertIn("before update on public.oom_sakkie_agent_dry_run_results", migration)
        self.assertIn("before delete on public.oom_sakkie_agent_dry_run_result_events", migration)

    @patch("modules.oom_sakkie.tools.list_dispatch_requests")
    @patch("modules.oom_sakkie.tools.list_deploy_decisions")
    @patch("modules.oom_sakkie.tools.list_patch_proposals")
    @patch("modules.oom_sakkie.tools.list_build_requests")
    def test_system_work_status_is_read_only_approval_summary(self, mock_builds, mock_patches, mock_deploys, mock_dispatch):
        from modules.oom_sakkie.tools import system_work_status_handler

        mock_builds.return_value = ({
            "success": True,
            "configured": True,
            "build_requests": [{
                "build_request_id": "OSK-BUILD-1",
                "latest_event": None,
            }],
        }, 200)
        mock_patches.return_value = ({
            "success": True,
            "configured": True,
            "patch_proposals": [{
                "patch_proposal_id": "OSK-PATCH-1",
                "latest_event": None,
            }],
        }, 200)
        mock_deploys.return_value = ({
            "success": True,
            "configured": True,
            "deploy_decisions": [],
        }, 200)
        mock_dispatch.return_value = ({
            "success": True,
            "configured": True,
            "dispatch_requests": [{
                "dispatch_request_id": "OSK-DISPATCH-REQ-1",
                "latest_decision": None,
            }],
        }, 200)

        result = system_work_status_handler({})

        self.assertTrue(result["success"])
        self.assertEqual(result["status"], "ok")
        self.assertIn("Forge Handoff", result["summary"])
        self.assertIn("patch proposal", result["summary"])
        self.assertIn("read-only", result["safety_notes"][0])
        self.assertEqual(result["llm_context"]["kind"], "system_work_status")
        self.assertEqual(result["llm_context"]["counts"]["pending_build_requests"], 1)
        self.assertEqual(result["llm_context"]["counts"]["pending_dispatch_design_requests"], 1)
        self.assertIn("Open Forge Handoff", result["llm_context"]["next_action"])

    @patch("modules.oom_sakkie.tools.list_dispatch_requests")
    @patch("modules.oom_sakkie.tools.list_deploy_decisions")
    @patch("modules.oom_sakkie.tools.list_patch_proposals")
    @patch("modules.oom_sakkie.tools.list_build_requests")
    def test_system_work_status_tracks_pipeline_stages(self, mock_builds, mock_patches, mock_deploys, mock_dispatch):
        from modules.oom_sakkie.tools import system_work_status_handler

        mock_builds.return_value = ({
            "success": True,
            "configured": True,
            "build_requests": [{
                "build_request_id": "OSK-BUILD-MOVED",
                "latest_event": {
                    "event_type": "review_note",
                    "notes": "Patch proposal recorded; moved to Patch Proposal Gate.",
                },
            }],
        }, 200)
        mock_patches.return_value = ({
            "success": True,
            "configured": True,
            "patch_proposals": [{
                "patch_proposal_id": "OSK-PATCH-READY",
                "latest_event": {"event_type": "approved_for_patch"},
            }],
        }, 200)
        mock_deploys.return_value = ({
            "success": True,
            "configured": True,
            "deploy_decisions": [],
        }, 200)
        mock_dispatch.return_value = ({
            "success": True,
            "configured": True,
            "dispatch_requests": [],
        }, 200)

        result = system_work_status_handler({})

        self.assertEqual(result["llm_context"]["counts"]["pending_build_requests"], 0)
        self.assertEqual(result["llm_context"]["counts"]["deploy_ready_patch_proposals"], 1)
        self.assertIn("verification", result["llm_context"]["next_action"])
        self.assertIn("OSK-PATCH-READY", result["llm_context"]["next_action"])

    @patch("modules.oom_sakkie.tools.list_dispatch_requests")
    @patch("modules.oom_sakkie.tools.list_deploy_decisions")
    @patch("modules.oom_sakkie.tools.list_patch_proposals")
    @patch("modules.oom_sakkie.tools.list_build_requests")
    def test_system_work_status_warns_when_store_unavailable(self, mock_builds, mock_patches, mock_deploys, mock_dispatch):
        from modules.oom_sakkie.tools import system_work_status_handler

        mock_builds.return_value = ({
            "success": False,
            "configured": False,
            "status": "not_configured",
            "build_requests": [],
        }, 503)
        mock_patches.return_value = ({
            "success": True,
            "configured": True,
            "patch_proposals": [],
        }, 200)
        mock_deploys.return_value = ({
            "success": True,
            "configured": True,
            "deploy_decisions": [],
        }, 200)
        mock_dispatch.return_value = ({
            "success": True,
            "configured": True,
            "dispatch_requests": [],
        }, 200)

        result = system_work_status_handler({})

        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "not_configured")
        self.assertIn("incomplete", result["summary"])
        self.assertEqual(result["llm_context"]["counts"]["pending_build_requests"], 0)
        self.assertIn("build_requests unavailable (status 503)", result["stale_warnings"][0])

    @patch("modules.oom_sakkie.tools.get_meat_planning_data")
    @patch("modules.oom_sakkie.tools.get_sales_dashboard_data")
    def test_business_growth_brief_is_read_only_commercial_advice(self, mock_sales, mock_meat):
        from modules.oom_sakkie.tools import business_growth_brief_handler

        mock_sales.return_value = {
            "success": True,
            "totals": [
                {"sale_category": "Newborn", "qty_available": 10, "status": "Not For Sale"},
                {"sale_category": "Grower Pigs", "qty_available": 4, "status": "Available"},
                {"sale_category": "Weaner Piglets", "qty_available": 2, "status": "Available"},
            ],
        }
        mock_meat.return_value = {
            "success": True,
            "summary": {
                "ready_now": 3,
                "next_14_days": 5,
                "next_30_days": 7,
                "fallback_abattoir": 1,
            },
            "pigs": [{
                "planning_bucket": "ready_now",
                "pig_id": "PIG-1",
                "tag_number": "22",
                "current_pen_name": "D1",
                "latest_weight_kg": 58.8,
                "recommended_action": "Prioritize for meat preorder marketing.",
                "marketing_readiness": "Ready For Interest",
            }],
        }

        result = business_growth_brief_handler({})

        self.assertTrue(result["success"])
        self.assertEqual(result["status"], "ok")
        self.assertIn("Business advisor brief", result["summary"])
        self.assertIn("Question:", result["summary"])
        self.assertIn("paid orders", result["llm_context"]["commercial_focus"])
        self.assertIn("draft offer brief", result["llm_context"]["owner_question"])
        self.assertEqual(result["llm_context"]["counts"]["available_sales_stock"], 16)
        self.assertEqual(result["llm_context"]["counts"]["marketable_sales_stock"], 6)
        self.assertEqual(result["llm_context"]["counts"]["young_or_not_ready_stock"], 10)
        self.assertEqual(result["llm_context"]["counts"]["meat_ready_now"], 3)
        self.assertEqual(result["llm_context"]["ready_meat_candidates"][0]["tag_number"], "22")
        outline = result["llm_context"]["offer_brief_outline"]
        self.assertEqual(outline["mode"], "internal_outline_only")
        self.assertEqual(outline["title"], "Ready meat preorder opportunity")
        self.assertIn("tag 22 in D1 at 58.8 kg", outline["stock_basis"])
        self.assertIn("Owner approval is required", outline["approval_needed"])
        self.assertIn("No customer message drafted.", outline["not_done"])
        self.assertIn("No public post drafted.", outline["not_done"])
        self.assertIn("No sale, reservation, or stock change made.", outline["not_done"])
        self.assertIn("read-only advice", result["safety_notes"][0])
        self.assertIn("No customer message", result["safety_notes"][0])

    @patch("modules.oom_sakkie.tools.get_meat_planning_data")
    @patch("modules.oom_sakkie.tools.get_sales_dashboard_data")
    def test_sales_offer_brief_is_owner_review_only_and_never_sends_or_writes(self, mock_sales, mock_meat):
        from modules.oom_sakkie.tools import sales_offer_brief_handler

        mock_sales.return_value = {
            "success": True,
            "totals": [
                {"sale_category": "Grower Pigs", "qty_available": 4, "status": "Available"},
            ],
        }
        mock_meat.return_value = {
            "success": True,
            "summary": {"ready_now": 1, "next_14_days": 0},
            "pigs": [{
                "planning_bucket": "ready_now",
                "pig_id": "PIG-22",
                "tag_number": "22",
                "current_pen_name": "D1",
                "latest_weight_kg": 58.8,
                "recommended_action": "Prioritize for meat preorder marketing.",
                "marketing_readiness": "Ready For Interest",
            }],
        }

        result = sales_offer_brief_handler({})

        self.assertTrue(result["success"])
        self.assertEqual(result["status"], "draft_only")
        self.assertIn("Sales offer brief prepared", result["summary"])
        self.assertEqual(result["llm_context"]["kind"], "sales_offer_brief")
        self.assertEqual(result["llm_context"]["mode"], "owner_review_draft_only")
        self.assertEqual(result["llm_context"]["selected_agent"]["slug"], "ledger")
        self.assertFalse(result["llm_context"]["sends_customer_message"])
        self.assertFalse(result["llm_context"]["customer_public_output_enabled"])
        self.assertFalse(result["llm_context"]["creates_quote"])
        self.assertFalse(result["llm_context"]["changes_stock"])
        self.assertFalse(result["llm_context"]["writes"])
        self.assertFalse(result["llm_context"]["dispatch_enabled"])
        self.assertFalse(result["llm_context"]["runs_specialist_llm"])
        self.assertFalse(result["llm_context"]["runs_specialist_tools"])
        offer = result["llm_context"]["offer_brief"]
        self.assertEqual(offer["mode"], "owner_review_draft_only")
        self.assertEqual(offer["angle"], "ready-meat preorder check")
        self.assertIn("tag 22 in D1 at 58.8 kg", offer["basis_summary"])
        self.assertTrue(offer["not_customer_copy"])
        self.assertIn("customer_message", offer["forbidden_outputs"])
        self.assertIn("quote", offer["forbidden_outputs"])
        self.assertIn("stock_reservation", offer["forbidden_outputs"])
        self.assertIn("No customer message was sent", result["safety_notes"][0])
        self.assertIn("no quote was created", result["safety_notes"][0])

    @patch("modules.oom_sakkie.tools.get_meat_planning_data")
    @patch("modules.oom_sakkie.tools.get_sales_dashboard_data")
    def test_sales_customer_draft_is_owner_review_copy_only_and_never_sends_or_writes(self, mock_sales, mock_meat):
        from modules.oom_sakkie.tools import sales_customer_draft_handler

        mock_sales.return_value = {
            "success": True,
            "totals": [
                {"sale_category": "Grower Pigs", "qty_available": 4, "status": "Available"},
            ],
        }
        mock_meat.return_value = {
            "success": True,
            "summary": {"ready_now": 1, "next_14_days": 0},
            "pigs": [{
                "planning_bucket": "ready_now",
                "pig_id": "PIG-22",
                "tag_number": "22",
                "current_pen_name": "D1",
                "latest_weight_kg": 58.8,
                "recommended_action": "Prioritize for meat preorder marketing.",
                "marketing_readiness": "Ready For Interest",
            }],
        }

        result = sales_customer_draft_handler({})

        self.assertTrue(result["success"])
        self.assertEqual(result["status"], "draft_only")
        self.assertEqual(result["llm_context"]["kind"], "sales_customer_draft")
        self.assertEqual(result["llm_context"]["mode"], "owner_review_customer_copy_draft_only")
        self.assertEqual(result["llm_context"]["selected_agent"]["slug"], "ledger")
        self.assertFalse(result["llm_context"]["sends_customer_message"])
        self.assertFalse(result["llm_context"]["sends_telegram"])
        self.assertFalse(result["llm_context"]["calls_chatwoot"])
        self.assertFalse(result["llm_context"]["calls_n8n"])
        self.assertFalse(result["llm_context"]["customer_public_output_enabled"])
        self.assertFalse(result["llm_context"]["creates_quote"])
        self.assertFalse(result["llm_context"]["creates_order"])
        self.assertFalse(result["llm_context"]["changes_stock"])
        self.assertFalse(result["llm_context"]["writes"])
        self.assertFalse(result["llm_context"]["dispatch_enabled"])
        draft = result["llm_context"]["customer_draft"]
        self.assertEqual(draft["mode"], "owner_review_customer_copy_draft_only")
        self.assertEqual(draft["draft_type"], "buyer_interest_check")
        self.assertIn("Hi [Name]", draft["message"])
        self.assertIn("checking interest", draft["message"])
        self.assertIn("send_message", draft["forbidden_actions"])
        self.assertIn("chatwoot_post", draft["forbidden_actions"])
        self.assertIn("create_quote", draft["forbidden_actions"])
        self.assertIn("reserve_stock", draft["forbidden_actions"])
        self.assertIn("not sent to any customer", result["safety_notes"][0])
        self.assertIn("no quote", result["safety_notes"][0])

    def test_review_advisor_is_advisory_and_prioritizes_trace_review(self):
        advisor = build_review_advice(
            summary={
                "success": True,
                "configured": True,
                "summary": {
                    "total_traces": 10,
                    "reviewed_traces": 4,
                    "unreviewed_traces": 6,
                    "problem_traces": 1,
                    "problem_rate_pct": 25.0,
                },
            },
            issue_traces={
                "success": True,
                "configured": True,
                "traces": [{
                    "trace_id": "OSK-ISSUE",
                    "tool_name": "weather_today",
                    "user_text": "weather today",
                    "answer": "answer",
                    "created_at": "2026-06-07T08:00:00+00:00",
                    "latest_feedback": {"feedback_type": "wrong_tool"},
                }],
            },
            unreviewed_traces={
                "success": True,
                "configured": True,
                "traces": [{
                    "trace_id": "OSK-UNREVIEWED",
                    "tool_name": "power_current",
                    "user_text": "power now",
                    "answer": "answer",
                    "created_at": "2026-06-07T08:01:00+00:00",
                    "stale_warnings": ["Power data is 42 minutes old."],
                    "latest_feedback": None,
                }],
            },
            statuses={"review_summary": 200, "issue_traces": 200, "unreviewed_traces": 200},
        )

        self.assertTrue(advisor["success"])
        self.assertEqual(advisor["mode"], "advisory_only")
        self.assertFalse(advisor["autonomous_marking_enabled"])
        self.assertFalse(advisor["writes_feedback"])
        self.assertEqual(advisor["review_queue"][0]["priority"], "high")
        self.assertEqual(advisor["review_queue"][1]["reason"], "unreviewed_with_stale_warning")
        self.assertTrue(any("Hold expansion" in action for action in advisor["suggested_actions"]))

    def test_review_advisor_reports_unconfigured_trace_store_without_writes(self):
        advisor = build_review_advice(
            summary={"success": False, "configured": False, "status": "not_configured"},
            issue_traces={"success": False, "configured": False, "traces": []},
            unreviewed_traces={"success": False, "configured": False, "traces": []},
            statuses={"review_summary": 503, "issue_traces": 503, "unreviewed_traces": 503},
        )

        self.assertFalse(advisor["success"])
        self.assertFalse(advisor["configured"])
        self.assertFalse(advisor["writes_feedback"])
        self.assertIn("Trace storage is not configured", advisor["suggested_actions"][0])

    def test_learning_advisor_builds_human_approved_proposals_from_feedback(self):
        advisor = build_learning_advice(
            summary={
                "success": True,
                "configured": True,
                "summary": {"reviewed_traces": 3, "problem_traces": 2},
            },
            issue_traces=[
                {
                    "trace_id": "OSK-WRONG",
                    "tool_name": "weather_today",
                    "user_text": "help me with the power",
                    "latest_feedback": {"feedback_type": "wrong_tool"},
                },
                {
                    "trace_id": "OSK-WORDING",
                    "tool_name": "farm_operating_brief",
                    "user_text": "bring me up to speed",
                    "latest_feedback": {"feedback_type": "bad_wording"},
                },
            ],
            statuses={"review_summary": 200, "advisor_traces": 200},
        )

        self.assertTrue(advisor["success"])
        self.assertEqual(advisor["mode"], "advisory_only")
        self.assertFalse(advisor["writes_code"])
        self.assertFalse(advisor["writes_feedback"])
        self.assertFalse(advisor["runs_llm"])
        self.assertTrue(advisor["requires_human_approval"])
        kinds = {item["kind"] for item in advisor["proposals"]}
        self.assertIn("routing_review", kinds)
        self.assertIn("answer_style_review", kinds)
        self.assertIn("Pick one proposal", advisor["suggested_next_step"])

    def test_learning_packet_builds_advisory_brief_without_apply_authority(self):
        packet, status_code = build_learning_packet({
            "kind": "answer_style_review",
            "priority": "medium",
            "title": "Review answer wording and composer instructions",
            "evidence": "Two traces were marked bad_wording for power_current.",
            "recommended_action": "Tighten the answer-composer prompt and add a regression test.",
        })

        self.assertEqual(status_code, 200)
        self.assertTrue(packet["success"])
        self.assertEqual(packet["mode"], "build_brief_only")
        self.assertFalse(packet["writes_code"])
        self.assertFalse(packet["applies_changes"])
        self.assertFalse(packet["runs_llm"])
        self.assertFalse(packet["writes_feedback"])
        self.assertFalse(packet["changes_tools"])
        self.assertFalse(packet["changes_prompts"])
        self.assertTrue(packet["requires_human_approval"])
        self.assertIn("modules/oom_sakkie/llm_answer.py", packet["recommended_files"])
        self.assertIn("tests.test_oom_sakkie_service", " ".join(packet["verification"]))
        self.assertIn("Oom Sakkie Learning Build Brief", packet["brief"])

    def test_learning_packet_rejects_unknown_proposal_kind(self):
        packet, status_code = build_learning_packet({"kind": "unsafe_self_edit"})

        self.assertEqual(status_code, 400)
        self.assertFalse(packet["success"])
        self.assertEqual(packet["status"], "invalid_proposal_kind")

    def test_approve_build_request_creates_non_applying_request(self):
        packet, _ = build_learning_packet({
            "kind": "routing_review",
            "priority": "high",
            "title": "Review routing aliases",
            "evidence": "Two wrong-tool traces.",
            "recommended_action": "Add one deterministic alias and regression test.",
        })

        request, status_code = approve_build_request(packet, approved_by="owner")

        self.assertEqual(status_code, 200)
        self.assertTrue(request["success"])
        self.assertEqual(request["status"], "approved_for_build")
        self.assertEqual(request["mode"], "build_request_only")
        self.assertTrue(request["build_request_id"].startswith("OSK-BUILD-"))
        self.assertFalse(request["builder_enabled"])
        self.assertFalse(request["writes_code_now"])
        self.assertFalse(request["applies_changes_now"])
        self.assertEqual(request["requires_next_gate"], "builder_agent_review_and_patch_approval")
        self.assertIn("Do not edit files", request["handoff"])

    def test_approve_build_request_rejects_unsafe_packet(self):
        request, status_code = approve_build_request({
            "success": True,
            "mode": "build_brief_only",
            "writes_code": True,
            "applies_changes": False,
        })

        self.assertEqual(status_code, 400)
        self.assertFalse(request["success"])
        self.assertEqual(request["status"], "unsafe_packet_rejected")

    def test_build_request_store_params_preserve_no_apply_flags(self):
        packet, _ = build_learning_packet({
            "kind": "routing_review",
            "priority": "high",
            "title": "Review routing aliases",
            "evidence": "Two traces.",
            "recommended_action": "Add one alias.",
        })
        request, _ = approve_build_request(packet)
        params = _build_request_params(request)

        self.assertEqual(params["build_request_id"], request["build_request_id"])
        self.assertEqual(params["status"], "approved_for_build")
        self.assertEqual(params["mode"], "build_request_only")
        self.assertFalse(params["builder_enabled"])
        self.assertFalse(params["writes_code_now"])
        self.assertFalse(params["applies_changes_now"])
        self.assertIn("routing_review", params["proposal_json"])

    def test_build_request_store_returns_not_configured_without_database_url(self):
        result, status_code = record_build_request({"build_request_id": "OSK-BUILD-TEST"}, database_url="")

        self.assertEqual(status_code, 503)
        self.assertFalse(result["stored"])
        self.assertEqual(result["status"], "not_configured")

        result, status_code = list_build_requests(database_url="")
        self.assertEqual(status_code, 503)
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "not_configured")

        result, status_code = get_build_request("OSK-BUILD-TEST", database_url="")
        self.assertEqual(status_code, 503)
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "not_configured")

        result, status_code = record_build_request_event(
            "OSK-BUILD-TEST",
            {"event_type": "ignored"},
            database_url="",
        )
        self.assertEqual(status_code, 503)
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "not_configured")

    def test_build_request_row_maps_select_tuple_positions(self):
        row = (
            "OSK-BUILD-ABC",
            "approved_for_build",
            "build_request_only",
            "owner",
            {"title": "Proposal"},
            "# Brief",
            ["modules/oom_sakkie/service.py"],
            ["python -m unittest"],
            "builder_agent_review_and_patch_approval",
            False,
            False,
            False,
            datetime(2026, 6, 7, tzinfo=timezone.utc),
            "ignored",
            "Smoke request.",
            "owner",
            datetime(2026, 6, 7, 1, tzinfo=timezone.utc),
        )

        item = _build_request_row(row)

        self.assertEqual(item["build_request_id"], "OSK-BUILD-ABC")
        self.assertEqual(item["status"], "approved_for_build")
        self.assertEqual(item["mode"], "build_request_only")
        self.assertFalse(item["builder_enabled"])
        self.assertFalse(item["writes_code_now"])
        self.assertFalse(item["applies_changes_now"])
        self.assertEqual(item["proposal"]["title"], "Proposal")
        self.assertEqual(item["recommended_files"], ["modules/oom_sakkie/service.py"])
        self.assertEqual(item["latest_event"]["event_type"], "ignored")
        self.assertEqual(item["latest_event"]["notes"], "Smoke request.")

    def test_build_request_migration_is_append_only_and_no_live_builder(self):
        migration = Path("supabase/migrations/202606070001_create_oom_sakkie_build_requests.sql").read_text(encoding="utf-8")

        self.assertIn("create table if not exists public.oom_sakkie_build_requests", migration)
        self.assertIn("builder_enabled = false and writes_code_now = false and applies_changes_now = false", migration)
        self.assertIn("before update on public.oom_sakkie_build_requests", migration)
        self.assertIn("before delete on public.oom_sakkie_build_requests", migration)

    def test_build_request_event_migration_is_append_only(self):
        migration = Path("supabase/migrations/202606070002_create_oom_sakkie_build_request_events.sql").read_text(encoding="utf-8")

        self.assertIn("create table if not exists public.oom_sakkie_build_request_events", migration)
        self.assertIn("event_type in ('approved', 'ignored', 'review_note')", migration)
        self.assertIn("before update on public.oom_sakkie_build_request_events", migration)
        self.assertIn("before delete on public.oom_sakkie_build_request_events", migration)

    def test_build_request_event_rejects_unknown_type(self):
        result, status_code = record_build_request_event(
            "OSK-BUILD-TEST",
            {"event_type": "apply_patch_now"},
            database_url="",
        )

        self.assertEqual(status_code, 400)
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "invalid_event_type")

    def test_forge_handoff_builds_non_executing_prompt_from_build_request(self):
        packet, _ = build_learning_packet({
            "kind": "routing_review",
            "priority": "high",
            "title": "Review routing aliases",
            "evidence": "Two wrong-tool traces.",
            "recommended_action": "Add one deterministic alias and regression test.",
        })
        request, _ = approve_build_request(packet)

        handoff, status_code = build_forge_handoff(request)

        self.assertEqual(status_code, 200)
        self.assertTrue(handoff["success"])
        self.assertEqual(handoff["mode"], "forge_handoff_only")
        self.assertFalse(handoff["runs_builder"])
        self.assertFalse(handoff["writes_code"])
        self.assertFalse(handoff["applies_changes"])
        self.assertFalse(handoff["deploys"])
        self.assertTrue(handoff["requires_owner_to_run_builder"])
        self.assertTrue(handoff["requires_patch_review"])
        self.assertTrue(handoff["requires_deploy_approval"])
        self.assertIn("Do not change code yet", handoff["prompt"])
        self.assertIn("Wait for owner approval before editing", handoff["prompt"])

    def test_forge_handoff_rejects_unsafe_build_request(self):
        handoff, status_code = build_forge_handoff({
            "mode": "build_request_only",
            "builder_enabled": True,
            "writes_code_now": False,
            "applies_changes_now": False,
        })

        self.assertEqual(status_code, 400)
        self.assertFalse(handoff["success"])
        self.assertEqual(handoff["status"], "unsafe_build_request_rejected")

    def test_patch_proposal_params_are_review_only(self):
        params = _patch_proposal_params("OSK-BUILD-TEST", {
            "proposal_text": "Proposed diff summary.",
            "proposed_by": "builder",
            "risk_notes": "Small route change.",
            "files_touched": ["modules/oom_sakkie/service.py"],
            "verification": ["python -m unittest tests.test_oom_sakkie_service"],
            "applies_patch": True,
            "deploys": True,
        })

        self.assertEqual(params["build_request_id"], "OSK-BUILD-TEST")
        self.assertTrue(params["patch_proposal_id"].startswith("OSK-PATCH-"))
        self.assertEqual(params["proposal_text"], "Proposed diff summary.")
        self.assertIn("service.py", params["files_touched_json"])
        self.assertFalse(params["applies_patch"])
        self.assertFalse(params["deploys"])

    def test_patch_proposal_store_returns_not_configured_without_database_url(self):
        result, status_code = record_patch_proposal(
            "OSK-BUILD-TEST",
            {"proposal_text": "Plan only."},
            database_url="",
        )

        self.assertEqual(status_code, 503)
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "not_configured")

        result, status_code = list_patch_proposals(database_url="")
        self.assertEqual(status_code, 503)
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "not_configured")

        result, status_code = get_patch_proposal("OSK-PATCH-TEST", database_url="")
        self.assertEqual(status_code, 503)
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "not_configured")

        result, status_code = record_patch_proposal_event(
            "OSK-PATCH-TEST",
            {"event_type": "approved_for_patch"},
            database_url="",
        )
        self.assertEqual(status_code, 503)
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "not_configured")

    def test_patch_proposal_rejects_missing_text_and_unknown_event_type(self):
        result, status_code = record_patch_proposal(
            "OSK-BUILD-TEST",
            {"proposal_text": ""},
            database_url="",
        )

        self.assertEqual(status_code, 400)
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "proposal_text_required")

        result, status_code = record_patch_proposal_event(
            "OSK-PATCH-TEST",
            {"event_type": "apply_patch_now"},
            database_url="",
        )

        self.assertEqual(status_code, 400)
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "invalid_event_type")

    @patch("modules.oom_sakkie.patch_proposal_store.get_patch_proposal")
    def test_patch_proposal_event_returns_not_found_before_insert(self, mock_get):
        mock_get.return_value = ({
            "success": False,
            "configured": True,
            "status": "patch_proposal_not_found",
            "patch_proposal_id": "OSK-PATCH-MISSING",
        }, 404)

        result, status_code = record_patch_proposal_event(
            "OSK-PATCH-MISSING",
            {"event_type": "approved_for_patch"},
            database_url="postgresql://example",
        )

        self.assertEqual(status_code, 404)
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "patch_proposal_not_found")
        mock_get.assert_called_once_with("OSK-PATCH-MISSING", database_url="postgresql://example")

    def test_patch_proposal_row_maps_select_tuple_positions(self):
        row = (
            "OSK-PATCH-ABC",
            "OSK-BUILD-ABC",
            "Patch summary.",
            "builder",
            "Low risk.",
            ["modules/oom_sakkie/service.py"],
            ["python -m unittest"],
            False,
            False,
            datetime(2026, 6, 7, tzinfo=timezone.utc),
            "approved_for_patch",
            "Approved manually.",
            "owner",
            datetime(2026, 6, 7, 1, tzinfo=timezone.utc),
        )

        item = _patch_proposal_row(row)

        self.assertEqual(item["patch_proposal_id"], "OSK-PATCH-ABC")
        self.assertEqual(item["build_request_id"], "OSK-BUILD-ABC")
        self.assertEqual(item["mode"], "patch_proposal_review_only")
        self.assertEqual(item["proposal_text"], "Patch summary.")
        self.assertFalse(item["applies_patch"])
        self.assertFalse(item["deploys"])
        self.assertEqual(item["files_touched"], ["modules/oom_sakkie/service.py"])
        self.assertEqual(item["latest_event"]["event_type"], "approved_for_patch")

    def test_patch_proposal_migration_is_append_only_and_review_only(self):
        migration = Path("supabase/migrations/202606070003_create_oom_sakkie_patch_proposals.sql").read_text(encoding="utf-8")

        self.assertIn("create table if not exists public.oom_sakkie_patch_proposals", migration)
        self.assertIn("applies_patch = false and deploys = false", migration)
        self.assertIn("event_type in ('approved_for_patch', 'rejected', 'review_note')", migration)
        self.assertIn("before update on public.oom_sakkie_patch_proposals", migration)
        self.assertIn("before delete on public.oom_sakkie_patch_proposals", migration)
        self.assertIn("before update on public.oom_sakkie_patch_proposal_events", migration)
        self.assertIn("before delete on public.oom_sakkie_patch_proposal_events", migration)

    def test_deploy_decision_params_are_record_only(self):
        params = _deploy_decision_params("OSK-PATCH-TEST", {
            "decision_type": "approved_for_manual_deploy",
            "environment": "production",
            "notes": "Ship after checks.",
            "verification_summary": "450 tests passed.",
            "approved_by": "owner",
            "runs_deploy": True,
            "deploys_now": True,
        })

        self.assertEqual(params["patch_proposal_id"], "OSK-PATCH-TEST")
        self.assertTrue(params["deploy_decision_id"].startswith("OSK-DEPLOY-"))
        self.assertEqual(params["decision_type"], "approved_for_manual_deploy")
        self.assertEqual(params["environment"], "production")
        self.assertFalse(params["runs_deploy"])
        self.assertFalse(params["deploys_now"])

    def test_deploy_decision_store_returns_not_configured_without_database_url(self):
        result, status_code = record_deploy_decision(
            "OSK-PATCH-TEST",
            {"decision_type": "approved_for_manual_deploy"},
            database_url="",
        )

        self.assertEqual(status_code, 503)
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "not_configured")

        result, status_code = list_deploy_decisions(database_url="")
        self.assertEqual(status_code, 503)
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "not_configured")

    def test_deploy_decision_rejects_unknown_type(self):
        result, status_code = record_deploy_decision(
            "OSK-PATCH-TEST",
            {"decision_type": "deploy_now"},
            database_url="",
        )

        self.assertEqual(status_code, 400)
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "invalid_decision_type")

    @patch("modules.oom_sakkie.deploy_decision_store.get_patch_proposal")
    def test_deploy_decision_requires_approved_patch_for_manual_deploy(self, mock_get):
        mock_get.return_value = ({
            "success": True,
            "configured": True,
            "status": "ok",
            "patch_proposal": {
                "patch_proposal_id": "OSK-PATCH-TEST",
                "latest_event": {"event_type": "rejected"},
            },
        }, 200)

        result, status_code = record_deploy_decision(
            "OSK-PATCH-TEST",
            {"decision_type": "approved_for_manual_deploy"},
            database_url="postgresql://example",
        )

        self.assertEqual(status_code, 409)
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "patch_not_approved")
        mock_get.assert_called_once_with("OSK-PATCH-TEST", database_url="postgresql://example")

    def test_deploy_decision_row_maps_select_tuple_positions(self):
        row = (
            "OSK-DEPLOY-ABC",
            "OSK-PATCH-ABC",
            "approved_for_manual_deploy",
            "local",
            "Approved.",
            "450 tests passed.",
            "owner",
            False,
            False,
            datetime(2026, 6, 7, tzinfo=timezone.utc),
        )

        item = _deploy_decision_row(row)

        self.assertEqual(item["deploy_decision_id"], "OSK-DEPLOY-ABC")
        self.assertEqual(item["patch_proposal_id"], "OSK-PATCH-ABC")
        self.assertEqual(item["mode"], "deploy_approval_record_only")
        self.assertEqual(item["decision_type"], "approved_for_manual_deploy")
        self.assertEqual(item["verification_summary"], "450 tests passed.")
        self.assertFalse(item["runs_deploy"])
        self.assertFalse(item["deploys_now"])

    def test_deploy_decision_migration_is_append_only_and_record_only(self):
        migration = Path("supabase/migrations/202606070004_create_oom_sakkie_deploy_decisions.sql").read_text(encoding="utf-8")

        self.assertIn("create table if not exists public.oom_sakkie_deploy_decisions", migration)
        self.assertIn("decision_type in ('approved_for_manual_deploy', 'rejected', 'deferred', 'review_note')", migration)
        self.assertIn("runs_deploy = false and deploys_now = false", migration)
        self.assertIn("before update on public.oom_sakkie_deploy_decisions", migration)
        self.assertIn("before delete on public.oom_sakkie_deploy_decisions", migration)

    @patch("modules.oom_sakkie.learning_packet.list_review_advisor_traces")
    @patch("modules.oom_sakkie.learning_packet.get_trace_review_summary")
    def test_implementation_queue_auto_prepares_only_strong_review_signals(self, mock_summary, mock_traces):
        mock_summary.return_value = ({
            "success": True,
            "configured": True,
            "days": 14,
            "summary": {"reviewed_traces": 4, "problem_traces": 3},
        }, 200)
        mock_traces.return_value = ({
            "success": True,
            "configured": True,
            "issue_traces": [
                {
                    "trace_id": "OSK-1",
                    "tool_name": "weather_today",
                    "user_text": "help me with the power",
                    "latest_feedback": {"feedback_type": "wrong_tool"},
                },
                {
                    "trace_id": "OSK-2",
                    "tool_name": "farm_attention_summary",
                    "user_text": "what should I look at",
                    "latest_feedback": {"feedback_type": "bad_wording"},
                },
                {
                    "trace_id": "OSK-3",
                    "tool_name": "farm_attention_summary",
                    "user_text": "what should I inspect",
                    "latest_feedback": {"feedback_type": "bad_wording"},
                },
            ],
        }, 200)

        queue, status_code = get_implementation_queue(channel="kiosk", days=14, limit=12)

        self.assertEqual(status_code, 200)
        self.assertTrue(queue["success"])
        self.assertEqual(queue["mode"], "auto_prepared_review_queue")
        self.assertFalse(queue["auto_prepare_policy"]["writes_code"])
        self.assertFalse(queue["auto_prepare_policy"]["applies_changes"])
        self.assertFalse(queue["auto_prepare_policy"]["runs_llm"])
        self.assertTrue(queue["auto_prepare_policy"]["requires_human_approval"])
        self.assertGreaterEqual(len(queue["packets"]), 2)
        self.assertTrue(all(packet["mode"] == "build_brief_only" for packet in queue["packets"]))
        titles = [packet["proposal"]["title"] for packet in queue["packets"]]
        self.assertIn("Review routing aliases or LLM fallback guidance", titles)
        self.assertTrue(any("Repeated bad_wording" in title for title in titles))

    @patch.dict(os.environ, {}, clear=True)
    @patch("modules.oom_sakkie.learning_llm.urllib_request.urlopen")
    def test_learning_llm_env_gate_returns_disabled_without_network(self, mock_urlopen):
        result = analyze_learning_with_llm(summary={}, issue_traces=[], deterministic_proposals=[])

        self.assertFalse(result["ran"])
        self.assertEqual(result["status"], "disabled")
        mock_urlopen.assert_not_called()

    def test_learning_llm_parser_validates_human_approved_proposals(self):
        body = {
            "choices": [{
                "message": {
                    "content": __import__("json").dumps({
                        "proposals": [
                            {
                                "kind": "routing_review",
                                "priority": "high",
                                "title": "Add power wording alias",
                                "evidence": "Two wrong-tool traces used the same phrase.",
                                "recommended_action": "Add one deterministic alias and a regression test.",
                                "approval_required": False,
                            },
                            {
                                "kind": "unsafe_self_edit",
                                "priority": "high",
                                "title": "Bad",
                                "evidence": "Bad",
                                "recommended_action": "Bad",
                            },
                        ]
                    })
                }
            }]
        }

        parsed = parse_learning_response(__import__("json").dumps(body))

        self.assertTrue(parsed["ran"])
        self.assertEqual(parsed["status"], "ok")
        self.assertEqual(len(parsed["proposals"]), 1)
        self.assertEqual(parsed["proposals"][0]["kind"], "routing_review")
        self.assertTrue(parsed["proposals"][0]["approval_required"])
        self.assertEqual(parsed["proposals"][0]["source"], "llm_learning_analyst")

    def test_rule_routing_known_phrases(self):
        cases = {
            "show me the agent command center": "agent_command_center",
            "what are the agents doing": "agent_command_center",
            "open the Jarvis control tower": "agent_command_center",
            "give me the daily command brief": "jarvis_daily_command_brief",
            "start my day": "jarvis_daily_command_brief",
            "run the command brief": "jarvis_daily_command_brief",
            "show me the Jarvis progress bar": "jarvis_product_progress",
            "how far are we from Jarvis": "jarvis_product_progress",
            "are the gates green": "jarvis_safety_gate_board",
            "show me the safety gates": "jarvis_safety_gate_board",
            "what is the CI status": "jarvis_safety_gate_board",
            "prepare Claude review": "jarvis_owner_review_packet",
            "show me the owner review packet": "jarvis_owner_review_packet",
            "handoff to Claude": "jarvis_owner_review_packet",
            "what is the agent dry-run queue status": "agent_dry_run_status",
            "what is the sentinel dry-run result queue status": "agent_dry_run_status",
            "are we ready for live agents": "agent_runtime_readiness",
            "what still blocks runtime": "agent_runtime_readiness",
            "run the agent activation preflight": "agent_activation_preflight",
            "what must happen before activating agents": "agent_activation_preflight",
            "show me the agent authority matrix": "agent_authority_matrix",
            "which agent powers are locked": "agent_authority_matrix",
            "which authority should we unlock first": "agent_authority_unlock_readiness",
            "show me authority unlock readiness": "agent_authority_unlock_readiness",
            "show me the dispatch rail blueprint": "agent_dispatch_decision_rail_blueprint",
            "what is the dispatch approval rail": "agent_dispatch_decision_rail_blueprint",
            "prepare the dispatch runtime review packet": "dispatch_runtime_review_packet",
            "claude dispatch review": "dispatch_runtime_review_packet",
            "what is the dispatch decision status": "dispatch_decision_status",
            "which dispatch requests are waiting for review": "dispatch_decision_status",
            "show me the agent runtime review packet": "agent_runtime_review_packet",
            "prepare the bulk claude review": "agent_runtime_review_packet",
            "what are the agent operating contracts": "agent_operating_contracts",
            "what must agents not do": "agent_operating_contracts",
            "what did sentinel learn": "agent_learning_evidence",
            "show me agent learning evidence": "agent_learning_evidence",
            "show me learning influence proposals": "learning_influence_status",
            "what learning needs approval": "learning_influence_status",
            "how is self-learning going": "learning_influence_status",
            "show me the learning consumption threat model": "learning_influence_consumption_readiness",
            "what blocks the learning consumer": "learning_influence_consumption_readiness",
            "show me the learning consumption audit rail": "learning_influence_consumption_audit_rail_blueprint",
            "proposal consumption rail blueprint": "learning_influence_consumption_audit_rail_blueprint",
            "show me the learning consumer design packet": "learning_influence_consumer_design_packet",
            "what is the allow_consumed guard": "learning_influence_consumer_design_packet",
            "run the sentinel dry-run review": "sentinel_dry_run_review",
            "first agent dry run": "sentinel_dry_run_review",
            "what needs my approval": "system_work_status",
            "what is the agent activation plan": "agent_activation_plan",
            "when can agents go live": "agent_activation_plan",
            "give me the agent team brief": "agent_crew_brief",
            "which agents would work together on sales": "agent_crew_brief",
            "which agent should handle marketing": "agent_crew_status",
            "show me the agent crew": "agent_crew_status",
            "what are you building": "system_work_status",
            "what needs review": "system_work_status",
            "what should we sell next": "business_growth_brief",
            "how do we grow sales": "business_growth_brief",
            "what should i promote": "business_growth_brief",
            "prepare an offer brief": "business_growth_brief",
            "prepare a sales offer brief": "sales_offer_brief",
            "draft offer brief for meat": "sales_offer_brief",
            "prepare a customer draft": "sales_customer_draft",
            "draft buyer message": "sales_customer_draft",
            "whatsapp draft for meat buyers": "sales_customer_draft",
            "what needs attention today": "farm_attention_summary",
            "give me the farm operating brief": "farm_operating_brief",
            "bring me up to speed": "farm_operating_brief",
            "what is the power like now": "power_current",
            "I need help with the power": "power_current",
            "show me the recent power profile": "power_recent",
            "weather now please": "weather_now",
            "weather today please": "weather_today",
            "help me with the weather": "weather_today",
            "weather forecast for the next few days": "weather_forecast",
            "what is the irrigation status": "irrigation_status",
            "start irrigation": "irrigation_status",
            "can you help me check irrigation": "irrigation_status",
            "do we need to water anything": "irrigation_status",
            "how is the farm": "dashboard_summary",
            "what animals do we have on the farm": "dashboard_summary",
            "what about the pigs": "dashboard_summary",
            "which pigs are ready for meat": "meat_planning",
            "which pigs should I look at for slaughter": "meat_planning",
            "show me pig allocation": "pig_allocation_readiness",
            "sales dashboard overview": "sales_dashboard",
            "are there any sales issues": "sales_dashboard",
            "help me understand sales": "sales_dashboard",
            "do I need to worry about anything today": "farm_attention_summary",
        }
        for text, expected_tool in cases.items():
            with self.subTest(text=text):
                match = classify_intent(text)
                self.assertIsNotNone(match)
                self.assertEqual(match.tool_name, expected_tool)
                self.assertGreaterEqual(match.confidence, 0.9)

    def test_farm_operating_brief_combines_read_only_sections(self):
        from modules.oom_sakkie.tools import farm_operating_brief_handler

        with patch("modules.oom_sakkie.tools.farm_attention_summary_handler") as attention, \
                patch("modules.oom_sakkie.tools.power_current_handler") as power, \
                patch("modules.oom_sakkie.tools.weather_today_handler") as weather, \
                patch("modules.oom_sakkie.tools.irrigation_status_handler") as irrigation:
            attention.return_value = {
                "success": True, "status": "ok", "summary": "Attention clear.",
                "links": [{"label": "Dashboard", "href": "/"}],
                "stale_warnings": [], "safety_notes": [], "raw": {"attention": True},
            }
            power.return_value = {
                "success": True, "status": "ok", "summary": "Power stable.",
                "links": [{"label": "Power", "href": "/#power_panel"}],
                "stale_warnings": [], "safety_notes": [], "raw": {"power": True},
            }
            weather.return_value = {
                "success": True, "status": "ok", "summary": "Weather steady.",
                "links": [{"label": "Weather", "href": "/#weather_panel"}],
                "stale_warnings": [], "safety_notes": [], "raw": {"weather": True},
            }
            irrigation.return_value = {
                "success": True, "status": "ok", "summary": "Irrigation idle.",
                "links": [{"label": "Irrigation", "href": "/#irrigation_panel"}],
                "stale_warnings": [],
                "safety_notes": ["Irrigation is read-only here. No start/stop command was sent."],
                "raw": {"irrigation": True},
            }

            result = farm_operating_brief_handler({})

        self.assertTrue(result["success"])
        self.assertEqual(result["status"], "ok")
        self.assertIn("Operating brief loaded", result["summary"])
        self.assertIn("Power stable", result["summary"])
        self.assertIn("Irrigation is read-only", result["safety_notes"][0])
        self.assertEqual(result["llm_context"]["kind"], "farm_operating_brief")
        self.assertEqual(result["llm_context"]["required_sections"], ["attention", "power", "weather", "irrigation"])
        self.assertEqual(set(result["llm_context"]["sections"]), {"attention", "power", "weather", "irrigation"})
        self.assertIn("Weather steady", result["llm_context"]["sections"]["weather"]["summary"])
        self.assertEqual(result["raw"]["kind"], "farm_operating_brief")
        self.assertEqual(set(result["raw"]["sections"]), {"attention", "power", "weather", "irrigation"})

    def test_jarvis_daily_command_brief_composes_read_only_sections(self):
        from modules.oom_sakkie.tools import jarvis_daily_command_brief_handler

        with patch("modules.oom_sakkie.tools.farm_operating_brief_handler") as farm, \
                patch("modules.oom_sakkie.tools.business_growth_brief_handler") as business, \
                patch("modules.oom_sakkie.tools.agent_command_center_handler") as command:
            farm.return_value = {
                "success": True,
                "status": "ok",
                "summary": "Farm steady.",
                "links": [{"label": "Farm", "href": "/"}],
                "stale_warnings": [],
                "safety_notes": ["Farm brief read-only."],
                "llm_context": {"kind": "farm_operating_brief"},
                "raw": {},
            }
            business.return_value = {
                "success": True,
                "status": "ok",
                "summary": "Business has one opportunity.",
                "links": [{"label": "Sales", "href": "/sales-dashboard"}],
                "stale_warnings": [],
                "safety_notes": ["Business brief read-only."],
                "llm_context": {
                    "kind": "business_growth_brief",
                    "owner_question": "Should I prepare an internal offer brief for approval?",
                },
                "raw": {},
            }
            command.return_value = {
                "success": True,
                "status": "ok",
                "summary": "No approvals waiting.",
                "links": [{"label": "Oom Sakkie", "href": "/oom-sakkie"}],
                "stale_warnings": [],
                "safety_notes": ["Command center read-only."],
                "llm_context": {
                    "kind": "agent_command_center",
                    "queue_snapshots": {
                        "system_work_status": {
                            "counts": {
                                "pending_build_requests": 1,
                                "pending_patch_reviews": 0,
                                "pending_dispatch_design_requests": 1,
                            },
                        },
                    },
                },
                "raw": {},
            }

            result = jarvis_daily_command_brief_handler({})

        self.assertTrue(result["success"])
        self.assertEqual(result["status"], "ok")
        self.assertIn("Daily command brief loaded", result["summary"])
        self.assertEqual(result["llm_context"]["kind"], "jarvis_daily_command_brief")
        self.assertEqual(result["llm_context"]["selected_agent"]["slug"], "gatekeeper")
        self.assertFalse(result["llm_context"]["dispatch_enabled"])
        self.assertFalse(result["llm_context"]["runs_specialist_llm"])
        self.assertFalse(result["llm_context"]["runs_specialist_tools"])
        self.assertFalse(result["llm_context"]["writes"])
        self.assertFalse(result["llm_context"]["applies_runtime_change"])
        self.assertEqual(result["llm_context"]["sections"]["farm"]["llm_context"]["kind"], "farm_operating_brief")
        self.assertEqual(result["llm_context"]["next_actions"][0], "Review 2 pending approval/design item(s) in the Oom Sakkie workbench.")
        self.assertIn("internal offer brief", result["llm_context"]["next_actions"][1])
        self.assertIn("No specialist was dispatched", result["safety_notes"][0])

    def test_jarvis_daily_command_brief_warns_on_partial_section(self):
        from modules.oom_sakkie.tools import jarvis_daily_command_brief_handler

        with patch("modules.oom_sakkie.tools.farm_operating_brief_handler") as farm, \
                patch("modules.oom_sakkie.tools.business_growth_brief_handler") as business, \
                patch("modules.oom_sakkie.tools.agent_command_center_handler") as command:
            farm.return_value = {
                "success": True, "status": "ok", "summary": "Farm steady.",
                "links": [], "stale_warnings": [], "safety_notes": [], "llm_context": {}, "raw": {},
            }
            business.return_value = {
                "success": False, "status": "not_configured", "summary": "Business unavailable.",
                "links": [], "stale_warnings": ["Sheets unavailable."], "safety_notes": [], "llm_context": {}, "raw": {},
            }
            command.return_value = {
                "success": True, "status": "ok", "summary": "Command steady.",
                "links": [], "stale_warnings": [], "safety_notes": [], "llm_context": {}, "raw": {},
            }

            result = jarvis_daily_command_brief_handler({})

        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["llm_context"]["failed_sections"], ["business"])
        self.assertIn("Daily command brief section unavailable or partial: business.", result["stale_warnings"])
        self.assertIn("Sheets unavailable.", result["stale_warnings"])

    def test_unsupported_action_guard_identifies_write_or_control_phrases(self):
        self.assertTrue(is_unsupported_action_request("delete that pig record"))
        self.assertTrue(is_unsupported_action_request("send the order message"))
        self.assertTrue(is_unsupported_action_request("turn off the pump"))
        self.assertTrue(is_unsupported_action_request("turn the pump on"))
        self.assertTrue(is_unsupported_action_request("switch the inverter off"))
        self.assertTrue(is_unsupported_action_request("irrigate zone 3 now"))
        self.assertFalse(is_unsupported_action_request("what is the power doing now"))

    @patch("modules.oom_sakkie.service.write_trace", return_value={"stored": False, "status": "test"})
    def test_capability_request_returns_current_read_only_scope(self, _write_trace):
        result, status = handle_message({
            "text": "what can you do",
            "channel": "kiosk",
        })

        self.assertEqual(status, 200)
        self.assertFalse(result["needs_clarification"])
        self.assertEqual(result["tool_used"], "")
        self.assertEqual(result["risk_level"], 0)
        self.assertIn("read-only farm checks", result["answer"])
        self.assertIn("cannot send messages", result["answer"])
        self.assertIn("Capabilities only", result["safety_notes"][0])
        self.assertEqual(result["intent"]["name"], "capabilities")
        self.assertEqual(result["pipeline"]["route_source"], "capability")
        self.assertEqual(result["pipeline"]["answer_source"], "local")

    @patch("modules.oom_sakkie.service.write_trace", return_value={"stored": False, "status": "test"})
    @patch("modules.oom_sakkie.tools.get_current_power_state")
    @patch("modules.oom_sakkie.service.compose_answer_with_llm", return_value=None)
    @patch("modules.oom_sakkie.service.route_with_llm")
    def test_llm_fallback_can_select_existing_read_only_tool(self, mock_llm, _compose, mock_power, _write_trace):
        mock_llm.return_value = LlmRouteResult(
            intent="llm_power_current",
            tool_name="power_current",
            confidence=0.82,
            reason="test:llm_selected_power",
        )
        mock_power.return_value = ({
            "success": True,
            "status": "ok",
            "source": {"is_stale": False, "data_age_minutes": 2},
            "current": {
                "battery_soc_pct": 90,
                "battery_state": "charging",
                "solar_power_w": 2400,
                "load_power_w": 800,
                "grid_power_w": 0,
                "grid_state": "not_using_grid",
            },
            "summary": {"headline": "Solar is carrying the farm load."},
        }, 200)

        result, status = handle_message({
            "text": "give me the energy situation",
            "channel": "kiosk",
        })

        self.assertEqual(status, 200)
        self.assertFalse(result["needs_clarification"])
        self.assertEqual(result["tool_used"], "power_current")
        self.assertEqual(result["intent"]["reason"], "test:llm_selected_power")
        self.assertEqual(result["risk_level"], 0)
        self.assertEqual(result["pipeline"]["route_source"], "llm_router")
        self.assertEqual(result["pipeline"]["answer_source"], "deterministic")
        self.assertTrue(result["pipeline"]["llm_router_used"])

    @patch("modules.oom_sakkie.service.write_trace", return_value={"stored": False, "status": "test"})
    @patch("modules.oom_sakkie.service.route_with_llm")
    def test_llm_fallback_clarification_does_not_call_tool(self, mock_llm, _write_trace):
        mock_llm.return_value = LlmRouteResult(
            intent="llm_clarification",
            tool_name="",
            confidence=0.5,
            reason="test:ambiguous",
            needs_clarification=True,
            clarification_question="Should I check power, weather, pigs, sales, or irrigation?",
        )

        result, status = handle_message({
            "text": "check the thing",
            "channel": "kiosk",
        })

        self.assertEqual(status, 200)
        self.assertTrue(result["needs_clarification"])
        self.assertEqual(result["tool_used"], "")
        self.assertIn("power, weather, pigs", result["answer"])
        self.assertEqual(result["pipeline"]["route_source"], "llm_router")
        self.assertEqual(result["pipeline"]["state"], "needs_clarification")

    @patch("modules.oom_sakkie.service.write_trace", return_value={"stored": False, "status": "test"})
    @patch("modules.oom_sakkie.service.route_with_llm")
    def test_unsupported_action_does_not_call_llm_router(self, mock_llm, _write_trace):
        result, status = handle_message({
            "text": "delete a pig record",
            "channel": "kiosk",
        })

        self.assertEqual(status, 200)
        self.assertTrue(result["action_blocked"])
        self.assertEqual(result["pipeline"]["route_source"], "action_guard")
        self.assertEqual(result["pipeline"]["state"], "blocked")
        mock_llm.assert_not_called()

    @patch("modules.oom_sakkie.service.write_trace", return_value={"stored": False, "status": "test"})
    @patch("modules.oom_sakkie.service.route_with_llm")
    def test_capability_request_does_not_call_llm_router(self, mock_llm, _write_trace):
        result, status = handle_message({
            "text": "what can you do",
            "channel": "kiosk",
        })

        self.assertEqual(status, 200)
        self.assertEqual(result["intent"]["name"], "capabilities")
        mock_llm.assert_not_called()

    def test_llm_route_parser_rejects_unknown_or_write_tool(self):
        body = {
            "choices": [{
                "message": {
                    "content": "{\"intent\":\"write\",\"tool_name\":\"send_customer_message\",\"confidence\":0.99}"
                }
            }]
        }

        self.assertIsNone(parse_llm_route_response(__import__("json").dumps(body)))

    @patch.dict(os.environ, {}, clear=True)
    @patch("modules.oom_sakkie.llm_router.urllib_request.urlopen")
    def test_llm_router_env_gate_returns_none_without_network(self, mock_urlopen):
        self.assertIsNone(route_with_llm("test routing"))
        mock_urlopen.assert_not_called()

    @patch.dict(os.environ, {
        "OOM_SAKKIE_LLM_ROUTER_ENABLED": "true",
        "OPENAI_API_KEY": "test-key",
        "OOM_SAKKIE_LLM_ROUTER_MODEL": "test-model",
    }, clear=True)
    @patch("modules.oom_sakkie.llm_router.urllib_request.urlopen", side_effect=urllib_error.URLError("offline"))
    def test_llm_router_network_failure_fails_closed(self, _urlopen):
        self.assertIsNone(route_with_llm("test routing"))

    def test_llm_route_parser_invalid_json_returns_none(self):
        self.assertIsNone(parse_llm_route_response("not json"))

    @patch.dict(os.environ, {}, clear=True)
    @patch("modules.oom_sakkie.llm_answer.urllib_request.urlopen")
    def test_llm_answer_env_gate_returns_none_without_network(self, mock_urlopen):
        self.assertIsNone(compose_answer_with_llm(
            user_text="what is the power doing",
            tool_name="power_current",
            deterministic_answer="Power is fine.",
            stale_warnings=[],
            safety_notes=[],
        ))
        mock_urlopen.assert_not_called()

    def test_llm_answer_parser_rejects_invalid_or_unsafe_output(self):
        self.assertIsNone(parse_llm_answer_response("not json"))
        unsafe = {
            "choices": [{
                "message": {
                    "content": "{\"answer\":\"I started the pump for you.\"}"
                }
            }]
        }
        self.assertIsNone(parse_llm_answer_response(__import__("json").dumps(unsafe)))
        safe_negated = {
            "choices": [{
                "message": {
                    "content": "{\"answer\":\"Irrigation is read-only here. No start or stop command was sent.\"}"
                }
            }]
        }
        self.assertEqual(
            parse_llm_answer_response(__import__("json").dumps(safe_negated)),
            "Irrigation is read-only here. No start or stop command was sent.",
        )

    @patch.dict(os.environ, {
        "OOM_SAKKIE_LLM_ANSWER_ENABLED": "true",
        "OPENAI_API_KEY": "test-key",
        "OOM_SAKKIE_LLM_ROUTER_MODEL": "test-model",
    }, clear=True)
    @patch("modules.oom_sakkie.llm_answer.urllib_request.urlopen")
    def test_llm_answer_rejects_off_topic_single_tool_disclaimer(self, mock_urlopen):
        response = Mock()
        response.read.return_value = __import__("json").dumps({
            "choices": [{
                "message": {
                    "content": "{\"answer\":\"Irrigation is idle. Power and weather weren’t evaluated here.\"}"
                }
            }]
        }).encode("utf-8")
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        mock_urlopen.return_value = response

        answer = compose_answer_with_llm(
            user_text="what is irrigation doing",
            tool_name="irrigation_status",
            deterministic_answer="Irrigation is idle.",
            stale_warnings=[],
            safety_notes=[],
            raw_context={"summary": "Irrigation is idle."},
        )

        self.assertIsNone(answer)

    @patch.dict(os.environ, {"OOM_SAKKIE_LLM_ROUTER_MODEL": "test-model"}, clear=True)
    def test_llm_answer_prompt_is_spoken_copilot_not_generic_reader(self):
        payload = _build_payload(
            user_text="what needs attention",
            tool_name="farm_attention_summary",
            deterministic_answer="There are 2 litters needing attention.",
            raw_context={"sections": {"litter_attention": [{"litter_id": "LIT-1", "reason": "Piglets need records"}]}},
            stale_warnings=[],
            safety_notes=["No write, control, message, or physical action was performed."],
        )

        system = payload["messages"][0]["content"]
        user = __import__("json").loads(payload["messages"][1]["content"])
        self.assertEqual(payload["temperature"], 0.55)
        self.assertIn("farm operating co-pilot", system)
        self.assertIn("do not read tables back like a clerk", system)
        self.assertIn("Lead with the operational meaning", system)
        self.assertIn("backend_context", system)
        self.assertIn("prioritize what the owner should look at first", system)
        self.assertIn("For jarvis_daily_command_brief, give one owner-ready command brief", system)
        self.assertIn("For jarvis_owner_review_packet, state whether the review packet is ready", system)
        self.assertIn("mention all required sections", system)
        self.assertIn("For business_growth_brief, sound like a business advisor", system)
        self.assertIn("internal offer brief outline only", system)
        self.assertIn("not customer-facing copy", system)
        self.assertIn("ask exactly one approval-style follow-up question", system)
        self.assertIn("For sales_offer_brief, summarize the owner-review draft only", system)
        self.assertIn("never imply a message, quote, sale, reservation, or stock change happened", system)
        self.assertIn("For sales_customer_draft, show the draft as owner-review copy only", system)
        self.assertIn("never add prices, promises, confirmed availability, or quote/order language", system)
        self.assertIn("For system_work_status, state the next owner action first", system)
        self.assertIn("stay in that tool's lane", system)
        self.assertIn("Do not mention unrelated systems", system)
        self.assertIn("do not say 'no stale warning'", system)
        self.assertIn("For operating briefs, use at most three short sentences", system)
        self.assertIn("Avoid assistant openers", system)
        self.assertIn("Never claim that anything was saved", system)
        self.assertIn("LIT-1", user["backend_context"])
        self.assertLessEqual(len(user["backend_context"]), 3000)

    @patch("modules.oom_sakkie.service.write_trace", return_value={"stored": False, "status": "test"})
    @patch("modules.oom_sakkie.service.route_with_llm")
    def test_llm_low_confidence_tool_selection_asks_clarification(self, mock_llm, _write_trace):
        mock_llm.return_value = LlmRouteResult(
            intent="llm_power_current",
            tool_name="power_current",
            confidence=0.4,
            reason="test:low_confidence_llm",
        )

        result, status = handle_message({
            "text": "give me the energy situation",
            "channel": "kiosk",
        })

        self.assertEqual(status, 200)
        self.assertTrue(result["needs_clarification"])
        self.assertEqual(result["tool_used"], "")
        self.assertIn("not sure", result["answer"])
        self.assertEqual(result["pipeline"]["route_source"], "unknown")

    @patch("modules.oom_sakkie.service.write_trace", return_value={"stored": False, "status": "test"})
    @patch("modules.oom_sakkie.service.route_with_llm", return_value=None)
    def test_low_confidence_returns_needs_clarification(self, _llm, _write_trace):
        result, status = handle_message({
            "text": "tell me something clever",
            "channel": "kiosk",
        })

        self.assertEqual(status, 200)
        self.assertTrue(result["needs_clarification"])
        self.assertEqual(result["tool_used"], "")
        self.assertIn("not sure", result["answer"])

    @patch("modules.oom_sakkie.service.write_trace", return_value={"stored": False, "status": "test"})
    def test_unsupported_action_returns_read_only_block(self, _write_trace):
        result, status = handle_message({
            "text": "send the customer an order message",
            "channel": "kiosk",
        })

        self.assertEqual(status, 200)
        self.assertTrue(result["needs_clarification"])
        self.assertTrue(result["action_blocked"])
        self.assertEqual(result["tool_used"], "")
        self.assertEqual(result["risk_level"], 0)
        self.assertIn("read-only", result["answer"])
        self.assertEqual(result["stale_warnings"], [])
        self.assertIn("No write", result["safety_notes"][0])

    @patch("modules.oom_sakkie.service.write_trace", return_value={"stored": False, "status": "test"})
    @patch("modules.oom_sakkie.service.classify_intent")
    def test_synthetic_low_confidence_match_returns_clarification(self, mock_classify, _write_trace):
        mock_classify.return_value = IntentMatch("maybe_power", "power_current", 0.4, "test:low_confidence")
        result, status = handle_message({
            "text": "maybe check something",
            "channel": "kiosk",
        })

        self.assertEqual(status, 200)
        self.assertTrue(result["needs_clarification"])
        self.assertEqual(result["tool_used"], "")
        self.assertIn("not sure", result["answer"])

    @patch("modules.oom_sakkie.service.write_trace", return_value={"stored": False, "status": "test"})
    def test_user_text_is_capped_before_trace(self, mock_write_trace):
        result, status = handle_message({
            "text": "power " + ("x" * 5000),
            "channel": "kiosk",
        })

        self.assertEqual(status, 200)
        self.assertEqual(result["tool_used"], "power_current")
        trace = mock_write_trace.call_args.args[0]
        self.assertLessEqual(len(trace["user_text"]), 2000)

    @patch("modules.oom_sakkie.service.write_trace", return_value={"stored": False, "status": "test"})
    @patch("modules.oom_sakkie.tools.get_current_power_state")
    @patch("modules.oom_sakkie.service.compose_answer_with_llm", return_value=None)
    def test_stale_power_warning_is_returned(self, _compose, mock_power, _write_trace):
        mock_power.return_value = ({
            "success": True,
            "status": "stale",
            "source": {"is_stale": True, "data_age_minutes": 42},
            "current": {
                "battery_soc_pct": 55,
                "battery_state": "charging",
                "solar_power_w": 1200,
                "load_power_w": 800,
                "grid_power_w": 0,
                "grid_state": "not_using_grid",
            },
            "summary": {"headline": "Power data is stale."},
        }, 200)

        result, status = handle_message({
            "text": "what is the power like now",
            "channel": "kiosk",
        })

        self.assertEqual(status, 200)
        self.assertFalse(result["needs_clarification"])
        self.assertEqual(result["tool_used"], "power_current")
        self.assertEqual(result["risk_level"], 0)
        self.assertIn("42 minutes old", result["stale_warnings"][0])
        self.assertIn("charging", result["answer"])
        self.assertIn("Grid: 0 W", result["answer"])
        self.assertIn("Data age: 42 minute(s)", result["answer"])
        self.assertIn("Note:", result["answer"])
        self.assertEqual(result["pipeline"]["route_source"], "rule")
        self.assertEqual(result["pipeline"]["answer_source"], "deterministic")
        self.assertTrue(result["pipeline"]["tool_checked"])

    @patch("modules.oom_sakkie.service.write_trace", return_value={"stored": False, "status": "test"})
    @patch("modules.oom_sakkie.tools.get_current_power_state")
    @patch("modules.oom_sakkie.service.compose_answer_with_llm")
    def test_llm_answer_composer_can_rewrite_after_tool_result(self, mock_compose, mock_power, _write_trace):
        mock_compose.return_value = "Power looks healthy: the battery is high and solar is carrying the load."
        mock_power.return_value = ({
            "success": True,
            "status": "ok",
            "source": {"is_stale": False, "data_age_minutes": 2},
            "current": {
                "battery_soc_pct": 90,
                "battery_state": "charging",
                "solar_power_w": 2400,
                "load_power_w": 800,
                "grid_power_w": 0,
                "grid_state": "not_using_grid",
            },
            "summary": {"headline": "Solar is carrying the farm load."},
        }, 200)

        result, status = handle_message({
            "text": "what is the power doing now",
            "channel": "kiosk",
        })

        self.assertEqual(status, 200)
        self.assertEqual(result["tool_used"], "power_current")
        self.assertEqual(result["answer"], mock_compose.return_value)
        self.assertEqual(result["pipeline"]["answer_source"], "llm_composer")
        self.assertTrue(result["pipeline"]["llm_answer_used"])
        self.assertEqual(result["agent_activity"]["mode"], "visual_activity_only")
        self.assertEqual(result["agent_activity"]["active_agent"]["slug"], "atlas")
        self.assertEqual(result["agent_activity"]["active_agent"]["color"], "cyan")
        self.assertEqual(result["agent_activity"]["workspace"]["tool_name"], "power_current")
        self.assertEqual(result["agent_activity"]["handoff_lane"][1]["actor"], "Atlas")
        self.assertEqual(result["agent_activity"]["handoff_lane"][3]["status"], "required_for_action")
        self.assertFalse(result["agent_activity"]["safety"]["runs_agent"])
        self.assertFalse(result["agent_activity"]["safety"]["dispatch_enabled"])
        self.assertFalse(result["agent_activity"]["safety"]["writes"])
        mock_compose.assert_called_once()

    @patch.dict(os.environ, {
        "OOM_SAKKIE_LLM_ANSWER_ENABLED": "true",
        "OPENAI_API_KEY": "test-key",
        "OOM_SAKKIE_LLM_ROUTER_MODEL": "test-model",
    }, clear=True)
    @patch("modules.oom_sakkie.service.write_trace", return_value={"stored": False, "status": "test"})
    @patch("modules.oom_sakkie.tools.get_current_power_state")
    @patch("modules.oom_sakkie.llm_answer.urllib_request.urlopen")
    def test_handle_message_rejects_unsafe_llm_answer_and_uses_deterministic_fallback(self, mock_urlopen, mock_power, _write_trace):
        response = Mock()
        response.read.return_value = __import__("json").dumps({
            "choices": [{
                "message": {
                    "content": "{\"answer\":\"I updated the power settings for you.\"}"
                }
            }]
        }).encode("utf-8")
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        mock_urlopen.return_value = response
        mock_power.return_value = ({
            "success": True,
            "status": "ok",
            "source": {"is_stale": False, "data_age_minutes": 2},
            "current": {
                "battery_soc_pct": 90,
                "battery_state": "charging",
                "solar_power_w": 2400,
                "load_power_w": 800,
                "grid_power_w": 0,
                "grid_state": "not_using_grid",
            },
            "summary": {"headline": "Solar is carrying the farm load."},
        }, 200)

        result, status = handle_message({
            "text": "what is the power doing now",
            "channel": "kiosk",
        })

        self.assertEqual(status, 200)
        self.assertEqual(result["tool_used"], "power_current")
        self.assertIn("Solar is carrying the farm load", result["answer"])
        self.assertNotIn("updated the power settings", result["answer"])
        self.assertEqual(result["pipeline"]["answer_source"], "deterministic")
        self.assertFalse(result["pipeline"]["llm_answer_used"])

    @patch("modules.oom_sakkie.service.write_trace", return_value={"stored": False, "status": "test"})
    @patch("modules.oom_sakkie.service.compose_answer_with_llm")
    @patch("modules.oom_sakkie.service.get_tool")
    def test_operating_brief_passes_compact_llm_context_to_composer(self, mock_get_tool, mock_compose, _write_trace):
        compact_context = {
            "kind": "farm_operating_brief",
            "required_sections": ["attention", "power", "weather", "irrigation"],
            "sections": {
                "attention": {"summary": "Attention summary."},
                "power": {"summary": "Power summary."},
                "weather": {"summary": "Weather summary."},
                "irrigation": {"summary": "Irrigation summary."},
            },
        }
        fake_tool = Mock()
        fake_tool.name = "farm_operating_brief"
        fake_tool.risk_level = RiskLevel.READ_ONLY
        fake_tool.handler.return_value = {
            "success": True,
            "status": "ok",
            "summary": "Operating brief loaded.",
            "links": [],
            "stale_warnings": [],
            "safety_notes": [],
            "llm_context": compact_context,
            "raw": {"large": "raw payload should not be preferred"},
        }
        mock_get_tool.return_value = fake_tool
        mock_compose.return_value = "Attention first. Power, weather, and irrigation are covered."

        result, status = handle_message({
            "text": "give me the farm operating brief",
            "channel": "kiosk",
        })

        self.assertEqual(status, 200)
        self.assertEqual(result["tool_used"], "farm_operating_brief")
        self.assertEqual(result["answer"], mock_compose.return_value)
        self.assertEqual(mock_compose.call_args.kwargs["raw_context"], compact_context)

    @patch("modules.oom_sakkie.service.write_trace", return_value={"stored": False, "status": "test"})
    @patch("modules.oom_sakkie.service.compose_answer_with_llm", return_value=None)
    @patch("modules.oom_sakkie.tools.get_meat_planning_data")
    def test_meat_planning_warning_is_returned(self, mock_meat, _compose, _write_trace):
        mock_meat.return_value = {
            "success": True,
            "source": "pig_allocation_readiness",
            "summary": {
                "ready_now": 2,
                "next_14_days": 1,
                "next_30_days": 3,
                "fallback_abattoir": 4,
            },
        }

        result, status = handle_message({
            "text": "what pigs are ready for meat",
            "channel": "kiosk",
        })

        self.assertEqual(status, 200)
        self.assertEqual(result["tool_used"], "meat_planning")
        self.assertIn("2 ready now", result["answer"])
        self.assertEqual(result["stale_warnings"], [])
        self.assertIn("read-only planning", result["safety_notes"][0])

    @patch("modules.oom_sakkie.service.write_trace", return_value={"stored": False, "status": "test"})
    @patch("modules.oom_sakkie.service.compose_answer_with_llm", return_value=None)
    @patch("modules.oom_sakkie.tools.get_pig_allocation_readiness_data")
    def test_pig_allocation_routes_without_write(self, mock_allocation, _compose, _write_trace):
        mock_allocation.return_value = {
            "success": True,
            "summary": {
                "total": 12,
                "buckets": {
                    "Meat Candidate": 2,
                    "Livestock Candidate": 3,
                    "Retain / Breeding Candidate": 1,
                },
            },
        }

        result, status = handle_message({
            "text": "show me pig allocation",
            "channel": "kiosk",
        })

        self.assertEqual(status, 200)
        self.assertEqual(result["tool_used"], "pig_allocation_readiness")
        self.assertEqual(result["risk_level"], 0)
        self.assertIn("12 pigs", result["answer"])

    @patch("modules.oom_sakkie.service.write_trace", return_value={"stored": False, "status": "test"})
    @patch("modules.oom_sakkie.service.compose_answer_with_llm", return_value=None)
    @patch("modules.oom_sakkie.tools.get_irrigation_status")
    def test_irrigation_status_is_read_only_even_for_control_phrase(self, mock_irrigation, _compose, _write_trace):
        mock_irrigation.return_value = ({
            "success": True,
            "status": "ok",
            "safety": {"read_only": True, "can_control": False, "hardware_commands_enabled": False},
            "current": {"status": "IDLE", "zone_id": "Z1", "zone_name": "Zone 1"},
            "today": {"done_count": 2, "next_zone_id": "Z2", "next_zone_name": "Zone 2"},
            "operator_summary": {"headline": "Irrigation has a plan for today.", "notes": []},
        }, 200)

        result, status = handle_message({
            "text": "start irrigation",
            "channel": "kiosk",
        })

        self.assertEqual(status, 200)
        self.assertEqual(result["tool_used"], "irrigation_status")
        self.assertEqual(result["risk_level"], 0)
        self.assertEqual(result["stale_warnings"], [])
        self.assertIn("read-only", result["safety_notes"][0])
        self.assertIn("No start/stop command was sent", result["answer"])

    @patch("modules.oom_sakkie.service.write_trace", return_value={"stored": False, "status": "test"})
    @patch("modules.oom_sakkie.service.compose_answer_with_llm", return_value=None)
    @patch("modules.oom_sakkie.tools.get_irrigation_status")
    def test_pump_control_phrase_is_read_only_with_safety_note(self, mock_irrigation, _compose, _write_trace):
        mock_irrigation.return_value = ({
            "success": True,
            "current": {"status": "IDLE", "zone_id": "Z1", "zone_name": "Zone 1"},
            "today": {"done_count": 2, "next_zone_id": "Z2", "next_zone_name": "Zone 2"},
            "operator_summary": {"headline": "Irrigation has a plan for today.", "notes": []},
        }, 200)

        result, status = handle_message({
            "text": "turn the pump on",
            "channel": "kiosk",
        })

        self.assertEqual(status, 200)
        self.assertEqual(result["tool_used"], "irrigation_status")
        self.assertFalse(result["needs_clarification"])
        self.assertEqual(result["risk_level"], 0)
        self.assertTrue(any("No write" in note for note in result["safety_notes"]))
        self.assertIn("No start/stop command was sent", result["answer"])

    @patch("modules.oom_sakkie.service.write_trace", return_value={"stored": False, "status": "test"})
    @patch("modules.oom_sakkie.service.compose_answer_with_llm", return_value=None)
    @patch("modules.oom_sakkie.tools.get_irrigation_status")
    def test_irrigate_zone_phrase_is_read_only_with_safety_note(self, mock_irrigation, _compose, _write_trace):
        mock_irrigation.return_value = ({
            "success": True,
            "current": {"status": "IDLE", "zone_id": "Z1", "zone_name": "Zone 1"},
            "today": {"done_count": 2, "next_zone_id": "Z2", "next_zone_name": "Zone 2"},
            "operator_summary": {"headline": "Irrigation has a plan for today.", "notes": []},
        }, 200)

        result, status = handle_message({
            "text": "irrigate zone 3 now",
            "channel": "kiosk",
        })

        self.assertEqual(status, 200)
        self.assertEqual(result["tool_used"], "irrigation_status")
        self.assertEqual(result["risk_level"], 0)
        self.assertTrue(any("No write" in note for note in result["safety_notes"]))
        self.assertIn("No start/stop command was sent", result["answer"])

    @patch("modules.oom_sakkie.service.write_trace", return_value={"stored": False, "status": "test"})
    def test_mixed_action_and_read_tool_adds_safety_note(self, _write_trace):
        result, status = handle_message({
            "text": "send weather to John",
            "channel": "kiosk",
        })

        self.assertEqual(status, 200)
        self.assertEqual(result["tool_used"], "weather_today")
        self.assertFalse(result["needs_clarification"])
        self.assertIn("No write", result["safety_notes"][0])

    def test_trace_params_include_insert_placeholders(self):
        trace = {
            "trace_id": "OSK-test",
            "channel": "kiosk",
            "session_id": "session",
            "user_text": "what is the power doing now",
            "intent": "power_current",
            "confidence": 0.95,
            "tool_name": "power_current",
            "tool_args_json": {},
            "tool_result_summary": "summary",
            "tool_result_hash": "hash",
            "answer": "answer",
            "risk_level": 0,
            "stale_warnings_json": [],
            "safety_notes_json": [],
            "links_json": [],
        }
        params = _trace_params(trace)
        insert_sql = next(value for value in write_trace.__code__.co_consts if isinstance(value, str) and "insert into public.oom_sakkie_traces" in value)

        for key in params:
            self.assertIn(f"%({key})s", insert_sql)

    def test_trace_row_maps_select_tuple_positions_to_expected_keys(self):
        created_at = datetime(2026, 6, 7, 8, 0, tzinfo=timezone.utc)
        feedback_at = datetime(2026, 6, 7, 8, 5, tzinfo=timezone.utc)
        mapped = _trace_row((
            "OSK-row",
            "kiosk",
            "session-1",
            "question",
            "weather_today",
            0.95,
            "weather_today",
            "summary",
            "hash",
            "answer",
            0,
            ["stale"],
            ["safe"],
            [{"label": "Weather", "href": "/weather"}],
            created_at,
            "wrong_tool",
            "note",
            "Charl",
            feedback_at,
        ))

        self.assertEqual(mapped["trace_id"], "OSK-row")
        self.assertEqual(mapped["channel"], "kiosk")
        self.assertEqual(mapped["session_id"], "session-1")
        self.assertEqual(mapped["user_text"], "question")
        self.assertEqual(mapped["intent"], "weather_today")
        self.assertEqual(mapped["confidence"], 0.95)
        self.assertEqual(mapped["tool_name"], "weather_today")
        self.assertEqual(mapped["tool_result_summary"], "summary")
        self.assertEqual(mapped["tool_result_hash"], "hash")
        self.assertEqual(mapped["answer"], "answer")
        self.assertEqual(mapped["risk_level"], 0)
        self.assertEqual(mapped["stale_warnings"], ["stale"])
        self.assertEqual(mapped["safety_notes"], ["safe"])
        self.assertEqual(mapped["links"], [{"label": "Weather", "href": "/weather"}])
        self.assertEqual(mapped["created_at"], created_at.isoformat())
        self.assertEqual(mapped["latest_feedback"]["feedback_type"], "wrong_tool")
        self.assertEqual(mapped["latest_feedback"]["notes"], "note")
        self.assertEqual(mapped["latest_feedback"]["reviewed_by"], "Charl")
        self.assertEqual(mapped["latest_feedback"]["created_at"], feedback_at.isoformat())

    def test_append_only_migration_locks_trace_tables(self):
        migration = Path("supabase/migrations/202606060004_lock_oom_sakkie_trace_append_only.sql").read_text(encoding="utf-8")

        self.assertIn("prevent_oom_sakkie_trace_mutation", migration)
        self.assertIn("before update on public.oom_sakkie_traces", migration)
        self.assertIn("before delete on public.oom_sakkie_traces", migration)
        self.assertIn("before update on public.oom_sakkie_trace_feedback", migration)
        self.assertIn("before delete on public.oom_sakkie_trace_feedback", migration)
        self.assertIn("append-only", migration)

    def test_append_only_triggers_block_updates_when_database_url_is_configured(self):
        database_url = os.getenv("DATABASE_URL", "").strip()
        if not database_url:
            self.skipTest("DATABASE_URL not configured for append-only integration test")
        try:
            import psycopg
        except ImportError:
            self.skipTest("psycopg not installed")

        trace_id = build_trace_id()
        feedback_id = build_feedback_id(trace_id, "correct")
        trace = {
            "trace_id": trace_id,
            "channel": "test",
            "session_id": "append-only-test",
            "user_text": "append only trigger test",
            "intent": "test",
            "confidence": 1.0,
            "tool_name": "test_tool",
            "tool_args_json": {},
            "tool_result_summary": "integration test row",
            "tool_result_hash": hash_tool_result({"test": True}),
            "answer": "integration test answer",
            "risk_level": 0,
            "stale_warnings_json": [],
            "safety_notes_json": [],
            "links_json": [],
        }
        stored = write_trace(trace, database_url=database_url)
        if not stored.get("stored"):
            self.skipTest(f"trace insert unavailable: {stored.get('status')}")

        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    insert into public.oom_sakkie_trace_feedback (
                        feedback_id, trace_id, feedback_type, notes, reviewed_by, channel, created_at
                    )
                    values (%s, %s, 'correct', 'append-only integration test', 'unittest', 'test', now())
                    """,
                    (feedback_id, trace_id),
                )
                connection.commit()
                with self.assertRaises(Exception) as trace_update:
                    cursor.execute(
                        "update public.oom_sakkie_traces set answer = answer where trace_id = %s",
                        (trace_id,),
                    )
                connection.rollback()
                self.assertIn("append-only", str(trace_update.exception).lower())

        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                with self.assertRaises(Exception) as feedback_update:
                    cursor.execute(
                        "update public.oom_sakkie_trace_feedback set notes = notes where feedback_id = %s",
                        (feedback_id,),
                    )
                connection.rollback()
                self.assertIn("append-only", str(feedback_update.exception).lower())

    def test_live_pg_review_gate_constraints_reject_action_flags_when_database_url_is_configured(self):
        database_url = os.getenv("DATABASE_URL", "").strip()
        if not database_url:
            self.skipTest("DATABASE_URL not configured for review-gate constraint integration test")
        try:
            import psycopg
        except ImportError:
            self.skipTest("psycopg not installed")

        suffix = build_trace_id().replace("OSK-", "")
        build_request_id = f"OSK-BUILD-CONSTRAINT-{suffix}"
        patch_proposal_id = f"OSK-PATCH-CONSTRAINT-{suffix}"

        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                with self.assertRaises(Exception) as build_error:
                    cursor.execute(
                        """
                        insert into public.oom_sakkie_build_requests (
                            build_request_id, status, mode, proposal_json, brief,
                            recommended_files_json, verification_json, next_gate,
                            builder_enabled
                        )
                        values (
                            %s, 'approved_for_build', 'build_request_only', '{}'::jsonb, '',
                            '[]'::jsonb, '[]'::jsonb, 'test', true
                        )
                        """,
                        (build_request_id,),
                    )
                connection.rollback()
                self.assertIn("check", str(build_error.exception).lower())

                cursor.execute(
                    """
                    insert into public.oom_sakkie_build_requests (
                        build_request_id, status, mode, proposal_json, brief,
                        recommended_files_json, verification_json, next_gate
                    )
                    values (
                        %s, 'approved_for_build', 'build_request_only', '{}'::jsonb, '',
                        '[]'::jsonb, '[]'::jsonb, 'test'
                    )
                    """,
                    (build_request_id,),
                )
                connection.commit()

        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                with self.assertRaises(Exception) as patch_error:
                    cursor.execute(
                        """
                        insert into public.oom_sakkie_patch_proposals (
                            patch_proposal_id, build_request_id, proposal_text, applies_patch
                        )
                        values (%s, %s, 'constraint test', true)
                        """,
                        (patch_proposal_id, build_request_id),
                    )
                connection.rollback()
                self.assertIn("check", str(patch_error.exception).lower())

                cursor.execute(
                    """
                    insert into public.oom_sakkie_patch_proposals (
                        patch_proposal_id, build_request_id, proposal_text
                    )
                    values (%s, %s, 'constraint test')
                    """,
                    (patch_proposal_id, build_request_id),
                )
                connection.commit()

        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                with self.assertRaises(Exception) as deploy_error:
                    cursor.execute(
                        """
                        insert into public.oom_sakkie_deploy_decisions (
                            deploy_decision_id, patch_proposal_id, decision_type, runs_deploy
                        )
                        values (%s, %s, 'approved_for_manual_deploy', true)
                        """,
                        (f"OSK-DEPLOY-CONSTRAINT-{suffix}", patch_proposal_id),
                    )
                connection.rollback()
                self.assertIn("check", str(deploy_error.exception).lower())

        dry_run_request_id = f"OSK-AGENT-DRYRUN-CONSTRAINT-{suffix}"
        dry_run_result_id = f"OSK-AGENT-DRYRUN-RESULT-CONSTRAINT-{suffix}"

        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                with self.assertRaises(Exception) as dry_run_error:
                    cursor.execute(
                        """
                        insert into public.oom_sakkie_agent_dry_run_requests (
                            dry_run_request_id, status, mode, specialist_slug,
                            requested_by, purpose, dry_run_enabled
                        )
                        values (
                            %s, 'approved_for_read_only_dry_run',
                            'read_only_dry_run_request_only', 'sentinel',
                            'unittest', 'constraint test', true
                        )
                        """,
                        (dry_run_request_id,),
                    )
                connection.rollback()
                self.assertIn("check", str(dry_run_error.exception).lower())

                cursor.execute(
                    """
                    insert into public.oom_sakkie_agent_dry_run_requests (
                        dry_run_request_id, status, mode, specialist_slug,
                        requested_by, purpose
                    )
                    values (
                        %s, 'approved_for_read_only_dry_run',
                        'read_only_dry_run_request_only', 'sentinel',
                        'unittest', 'constraint test'
                    )
                    """,
                    (dry_run_request_id,),
                )
                connection.commit()

        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                with self.assertRaises(Exception) as dry_run_result_error:
                    cursor.execute(
                        """
                        insert into public.oom_sakkie_agent_dry_run_results (
                            dry_run_result_id, dry_run_request_id, status, mode,
                            specialist_slug, result_text, runs_specialist
                        )
                        values (
                            %s, %s, 'recorded_for_owner_review',
                            'dry_run_result_review_only', 'sentinel',
                            'constraint test', true
                        )
                        """,
                        (dry_run_result_id, dry_run_request_id),
                    )
                connection.rollback()
                self.assertIn("check", str(dry_run_result_error.exception).lower())

        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                cursor.execute("select to_regclass('public.oom_sakkie_dispatch_requests')")
                if cursor.fetchone()[0] is None:
                    return
                with self.assertRaises(Exception) as dispatch_error:
                    cursor.execute(
                        """
                        insert into public.oom_sakkie_dispatch_requests (
                            dispatch_request_id, status, mode, specialist_slug,
                            requested_by, purpose, dispatch_enabled
                        )
                        values (
                            %s, 'requested_for_dispatch_design_review',
                            'dispatch_decision_request_only', 'sentinel',
                            'unittest', 'constraint test', true
                        )
                        """,
                        (f"OSK-DISPATCH-REQ-CONSTRAINT-{suffix}",),
                    )
                connection.rollback()
                self.assertIn("check", str(dispatch_error.exception).lower())

                cursor.execute("select to_regclass('public.oom_sakkie_dispatch_execution_approvals')")
                if cursor.fetchone()[0] is None:
                    return
                dispatch_request_id = f"OSK-DISPATCH-REQ-EXEC-CONSTRAINT-{suffix}"
                cursor.execute(
                    """
                    insert into public.oom_sakkie_dispatch_requests (
                        dispatch_request_id, status, mode, specialist_slug,
                        requested_by, purpose
                    )
                    values (
                        %s, 'requested_for_dispatch_design_review',
                        'dispatch_decision_request_only', 'sentinel',
                        'unittest', 'constraint test'
                    )
                    """,
                    (dispatch_request_id,),
                )
                with self.assertRaises(Exception) as execution_approval_error:
                    cursor.execute(
                        """
                        insert into public.oom_sakkie_dispatch_execution_approvals (
                            approval_id, dispatch_request_id, status, mode, specialist_slug,
                            approval_type, runs_specialist_llm
                        )
                        values (
                            %s, %s, 'recorded_for_single_dry_run_execution_gate',
                            'single_dry_run_execution_approval_only', 'sentinel',
                            'approved_for_single_dry_run_execution', true
                        )
                        """,
                        (f"OSK-DISPATCH-EXEC-CONSTRAINT-{suffix}", dispatch_request_id),
                    )
                connection.rollback()
                self.assertIn("check", str(execution_approval_error.exception).lower())

    def test_live_pg_review_gate_tables_are_append_only_when_database_url_is_configured(self):
        database_url = os.getenv("DATABASE_URL", "").strip()
        if not database_url:
            self.skipTest("DATABASE_URL not configured for review-gate append-only integration test")
        try:
            import psycopg
        except ImportError:
            self.skipTest("psycopg not installed")

        suffix = build_trace_id().replace("OSK-", "")
        build_request_id = f"OSK-BUILD-APPEND-{suffix}"
        build_event_id = f"OSK-BUILD-EVENT-APPEND-{suffix}"
        patch_proposal_id = f"OSK-PATCH-APPEND-{suffix}"
        patch_event_id = f"OSK-PATCH-EVENT-APPEND-{suffix}"
        deploy_decision_id = f"OSK-DEPLOY-APPEND-{suffix}"
        dry_run_request_id = f"OSK-AGENT-DRYRUN-APPEND-{suffix}"
        dry_run_event_id = f"OSK-AGENT-DRYRUN-EVENT-APPEND-{suffix}"
        dry_run_result_id = f"OSK-AGENT-DRYRUN-RESULT-APPEND-{suffix}"
        dry_run_result_event_id = f"OSK-AGENT-DRYRUN-RESULT-EVENT-APPEND-{suffix}"
        dispatch_request_id = f"OSK-DISPATCH-REQ-APPEND-{suffix}"
        dispatch_decision_id = f"OSK-DISPATCH-DECISION-APPEND-{suffix}"
        dispatch_execution_approval_id = f"OSK-DISPATCH-EXEC-APPROVAL-APPEND-{suffix}"
        dispatch_execution_event_id = f"OSK-DISPATCH-EXEC-EVENT-APPEND-{suffix}"

        rows = [
            (
                "public.oom_sakkie_build_requests",
                "build_request_id",
                build_request_id,
                "brief",
            ),
            (
                "public.oom_sakkie_build_request_events",
                "event_id",
                build_event_id,
                "notes",
            ),
            (
                "public.oom_sakkie_patch_proposals",
                "patch_proposal_id",
                patch_proposal_id,
                "proposal_text",
            ),
            (
                "public.oom_sakkie_patch_proposal_events",
                "event_id",
                patch_event_id,
                "notes",
            ),
            (
                "public.oom_sakkie_deploy_decisions",
                "deploy_decision_id",
                deploy_decision_id,
                "notes",
            ),
            (
                "public.oom_sakkie_agent_dry_run_requests",
                "dry_run_request_id",
                dry_run_request_id,
                "purpose",
            ),
            (
                "public.oom_sakkie_agent_dry_run_events",
                "event_id",
                dry_run_event_id,
                "notes",
            ),
            (
                "public.oom_sakkie_agent_dry_run_results",
                "dry_run_result_id",
                dry_run_result_id,
                "result_text",
            ),
            (
                "public.oom_sakkie_agent_dry_run_result_events",
                "event_id",
                dry_run_result_event_id,
                "notes",
            ),
        ]

        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                cursor.execute("select to_regclass('public.oom_sakkie_dispatch_requests')")
                dispatch_tables_exist = cursor.fetchone()[0] is not None
                if dispatch_tables_exist:
                    rows.extend([
                        (
                            "public.oom_sakkie_dispatch_requests",
                            "dispatch_request_id",
                            dispatch_request_id,
                            "purpose",
                        ),
                        (
                            "public.oom_sakkie_dispatch_decisions",
                            "decision_id",
                            dispatch_decision_id,
                            "notes",
                        ),
                    ])
                cursor.execute("select to_regclass('public.oom_sakkie_dispatch_execution_approvals')")
                dispatch_execution_tables_exist = cursor.fetchone()[0] is not None
                if dispatch_execution_tables_exist:
                    rows.extend([
                        (
                            "public.oom_sakkie_dispatch_execution_approvals",
                            "approval_id",
                            dispatch_execution_approval_id,
                            "notes",
                        ),
                        (
                            "public.oom_sakkie_dispatch_execution_approval_events",
                            "event_id",
                            dispatch_execution_event_id,
                            "notes",
                        ),
                    ])
                cursor.execute(
                    """
                    insert into public.oom_sakkie_build_requests (
                        build_request_id, status, mode, proposal_json, brief,
                        recommended_files_json, verification_json, next_gate
                    )
                    values (
                        %s, 'approved_for_build', 'build_request_only', '{}'::jsonb,
                        'append-only test', '[]'::jsonb, '[]'::jsonb, 'manual'
                    )
                    """,
                    (build_request_id,),
                )
                cursor.execute(
                    """
                    insert into public.oom_sakkie_build_request_events (
                        event_id, build_request_id, event_type, notes, recorded_by
                    )
                    values (%s, %s, 'review_note', 'append-only test', 'unittest')
                    """,
                    (build_event_id, build_request_id),
                )
                cursor.execute(
                    """
                    insert into public.oom_sakkie_patch_proposals (
                        patch_proposal_id, build_request_id, proposal_text, proposed_by
                    )
                    values (%s, %s, 'append-only test', 'unittest')
                    """,
                    (patch_proposal_id, build_request_id),
                )
                cursor.execute(
                    """
                    insert into public.oom_sakkie_patch_proposal_events (
                        event_id, patch_proposal_id, event_type, notes, recorded_by
                    )
                    values (%s, %s, 'review_note', 'append-only test', 'unittest')
                    """,
                    (patch_event_id, patch_proposal_id),
                )
                cursor.execute(
                    """
                    insert into public.oom_sakkie_deploy_decisions (
                        deploy_decision_id, patch_proposal_id, decision_type,
                        environment, notes, approved_by
                    )
                    values (%s, %s, 'review_note', 'local', 'append-only test', 'unittest')
                    """,
                    (deploy_decision_id, patch_proposal_id),
                )
                cursor.execute(
                    """
                    insert into public.oom_sakkie_agent_dry_run_requests (
                        dry_run_request_id, status, mode, specialist_slug,
                        requested_by, purpose
                    )
                    values (
                        %s, 'approved_for_read_only_dry_run',
                        'read_only_dry_run_request_only', 'sentinel',
                        'unittest', 'append-only test'
                    )
                    """,
                    (dry_run_request_id,),
                )
                cursor.execute(
                    """
                    insert into public.oom_sakkie_agent_dry_run_events (
                        event_id, dry_run_request_id, event_type, notes, recorded_by
                    )
                    values (%s, %s, 'review_note', 'append-only test', 'unittest')
                    """,
                    (dry_run_event_id, dry_run_request_id),
                )
                cursor.execute(
                    """
                    insert into public.oom_sakkie_agent_dry_run_results (
                        dry_run_result_id, dry_run_request_id, status, mode,
                        specialist_slug, result_text, recorded_by
                    )
                    values (
                        %s, %s, 'recorded_for_owner_review',
                        'dry_run_result_review_only', 'sentinel',
                        'append-only test', 'unittest'
                    )
                    """,
                    (dry_run_result_id, dry_run_request_id),
                )
                cursor.execute(
                    """
                    insert into public.oom_sakkie_agent_dry_run_result_events (
                        event_id, dry_run_result_id, event_type, notes, recorded_by
                    )
                    values (%s, %s, 'review_note', 'append-only test', 'unittest')
                    """,
                    (dry_run_result_event_id, dry_run_result_id),
                )
                if dispatch_tables_exist:
                    cursor.execute(
                        """
                        insert into public.oom_sakkie_dispatch_requests (
                            dispatch_request_id, status, mode, specialist_slug,
                            requested_by, purpose
                        )
                        values (
                            %s, 'requested_for_dispatch_design_review',
                            'dispatch_decision_request_only', 'sentinel',
                            'unittest', 'append-only test'
                        )
                        """,
                        (dispatch_request_id,),
                    )
                    cursor.execute(
                        """
                        insert into public.oom_sakkie_dispatch_decisions (
                            decision_id, dispatch_request_id, decision_type, notes, recorded_by
                        )
                        values (%s, %s, 'review_note', 'append-only test', 'unittest')
                        """,
                        (dispatch_decision_id, dispatch_request_id),
                    )
                if dispatch_execution_tables_exist:
                    cursor.execute(
                        """
                        insert into public.oom_sakkie_dispatch_execution_approvals (
                            approval_id, dispatch_request_id, status, mode,
                            specialist_slug, approval_type, notes, approved_by
                        )
                        values (
                            %s, %s, 'recorded_for_single_dry_run_execution_gate',
                            'single_dry_run_execution_approval_only', 'sentinel',
                            'review_note', 'append-only test', 'unittest'
                        )
                        """,
                        (dispatch_execution_approval_id, dispatch_request_id),
                    )
                    cursor.execute(
                        """
                        insert into public.oom_sakkie_dispatch_execution_approval_events (
                            event_id, approval_id, event_type, notes, recorded_by
                        )
                        values (%s, %s, 'review_note', 'append-only test', 'unittest')
                        """,
                        (dispatch_execution_event_id, dispatch_execution_approval_id),
                    )
                connection.commit()

        for table_name, id_column, row_id, text_column in rows:
            with psycopg.connect(database_url, connect_timeout=10) as connection:
                with connection.cursor() as cursor:
                    with self.assertRaises(Exception) as update_error:
                        cursor.execute(
                            f"update {table_name} set {text_column} = {text_column} where {id_column} = %s",
                            (row_id,),
                        )
                    connection.rollback()
                    self.assertIn("append-only", str(update_error.exception).lower())

            with psycopg.connect(database_url, connect_timeout=10) as connection:
                with connection.cursor() as cursor:
                    with self.assertRaises(Exception) as delete_error:
                        cursor.execute(
                            f"delete from {table_name} where {id_column} = %s",
                            (row_id,),
                        )
                    connection.rollback()
                    self.assertIn("append-only", str(delete_error.exception).lower())

    def test_live_pg_dispatch_execution_consumed_event_is_unique_when_database_url_is_configured(self):
        database_url = os.getenv("DATABASE_URL", "").strip()
        if not database_url:
            self.skipTest("DATABASE_URL not configured for dispatch execution unique-consume integration test")
        try:
            import psycopg
        except ImportError:
            self.skipTest("psycopg not installed")

        suffix = build_trace_id().replace("OSK-", "")
        dispatch_request_id = f"OSK-DISPATCH-REQ-CONSUME-{suffix}"
        approval_id = f"OSK-DISPATCH-EXEC-APPROVAL-CONSUME-{suffix}"
        consumed_event_id = f"OSK-DISPATCH-EXEC-EVENT-CONSUME-{suffix}"
        duplicate_event_id = f"OSK-DISPATCH-EXEC-EVENT-CONSUME-DUP-{suffix}"
        review_note_event_id = f"OSK-DISPATCH-EXEC-EVENT-NOTE-{suffix}"

        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                cursor.execute("select to_regclass('public.oom_sakkie_dispatch_execution_approval_events')")
                if cursor.fetchone()[0] is None:
                    self.skipTest("dispatch execution approval tables are not migrated")
                cursor.execute(
                    """
                    insert into public.oom_sakkie_dispatch_requests (
                        dispatch_request_id, status, mode, specialist_slug,
                        requested_by, purpose
                    )
                    values (
                        %s, 'requested_for_dispatch_design_review',
                        'dispatch_decision_request_only', 'sentinel',
                        'unittest', 'unique consumed event test'
                    )
                    """,
                    (dispatch_request_id,),
                )
                cursor.execute(
                    """
                    insert into public.oom_sakkie_dispatch_execution_approvals (
                        approval_id, dispatch_request_id, status, mode,
                        specialist_slug, approval_type, notes, approved_by
                    )
                    values (
                        %s, %s, 'recorded_for_single_dry_run_execution_gate',
                        'single_dry_run_execution_approval_only', 'sentinel',
                        'approved_for_single_dry_run_execution',
                        'unique consumed event test', 'unittest'
                    )
                    """,
                    (approval_id, dispatch_request_id),
                )
                cursor.execute(
                    """
                    insert into public.oom_sakkie_dispatch_execution_approval_events (
                        event_id, approval_id, event_type, notes, recorded_by
                    )
                    values (%s, %s, 'consumed_by_single_dry_run_result', 'first consume', 'unittest')
                    """,
                    (consumed_event_id, approval_id),
                )
                connection.commit()

        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                with self.assertRaises(Exception) as duplicate_error:
                    cursor.execute(
                        """
                        insert into public.oom_sakkie_dispatch_execution_approval_events (
                            event_id, approval_id, event_type, notes, recorded_by
                        )
                        values (%s, %s, 'consumed_by_single_dry_run_result', 'second consume', 'unittest')
                        """,
                        (duplicate_event_id, approval_id),
                    )
                connection.rollback()
                self.assertIn("unique", str(duplicate_error.exception).lower())

        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    insert into public.oom_sakkie_dispatch_execution_approval_events (
                        event_id, approval_id, event_type, notes, recorded_by
                    )
                    values (%s, %s, 'review_note', 'non-consume notes remain append-only evidence', 'unittest')
                    """,
                    (review_note_event_id, approval_id),
                )
                connection.commit()

    def test_live_pg_learning_influence_tables_are_append_only_and_no_apply_when_database_url_is_configured(self):
        database_url = os.getenv("DATABASE_URL", "").strip()
        if not database_url:
            self.skipTest("DATABASE_URL not configured for learning influence integration test")
        try:
            import psycopg
        except ImportError:
            self.skipTest("psycopg not installed")

        suffix = build_trace_id().replace("OSK-", "")
        dry_run_request_id = f"OSK-AGENT-DRYRUN-LEARN-{suffix}"
        dry_run_result_id = f"OSK-AGENT-DRYRUN-RESULT-LEARN-{suffix}"
        proposal_id = f"OSK-LEARNING-INFLUENCE-{suffix}"
        event_id = f"OSK-LEARNING-INFLUENCE-EVENT-{suffix}"

        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                cursor.execute("select to_regclass('public.oom_sakkie_learning_influence_proposals')")
                if cursor.fetchone()[0] is None:
                    self.skipTest("learning influence proposal tables are not migrated")
                cursor.execute(
                    """
                    insert into public.oom_sakkie_agent_dry_run_requests (
                        dry_run_request_id, status, mode, specialist_slug,
                        requested_by, purpose
                    )
                    values (
                        %s, 'approved_for_read_only_dry_run',
                        'read_only_dry_run_request_only', 'sentinel',
                        'unittest', 'learning influence test'
                    )
                    """,
                    (dry_run_request_id,),
                )
                cursor.execute(
                    """
                    insert into public.oom_sakkie_agent_dry_run_results (
                        dry_run_result_id, dry_run_request_id, status, mode,
                        specialist_slug, result_text, recorded_by
                    )
                    values (
                        %s, %s, 'recorded_for_owner_review',
                        'dry_run_result_review_only', 'sentinel',
                        'learning influence source', 'unittest'
                    )
                    """,
                    (dry_run_result_id, dry_run_request_id),
                )
                with self.assertRaises(Exception) as proposal_error:
                    cursor.execute(
                        """
                        insert into public.oom_sakkie_learning_influence_proposals (
                            proposal_id, source_result_id, status, mode, specialist_slug,
                            proposal_title, proposal_text, applies_learning_now
                        )
                        values (
                            %s, %s, 'proposed_for_owner_review',
                            'learning_influence_proposal_only', 'sentinel',
                            'bad proposal', 'should fail', true
                        )
                        """,
                        (f"{proposal_id}-BAD", dry_run_result_id),
                    )
                connection.rollback()
                self.assertIn("check", str(proposal_error.exception).lower())

        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    insert into public.oom_sakkie_agent_dry_run_requests (
                        dry_run_request_id, status, mode, specialist_slug,
                        requested_by, purpose
                    )
                    values (
                        %s, 'approved_for_read_only_dry_run',
                        'read_only_dry_run_request_only', 'sentinel',
                        'unittest', 'learning influence test'
                    )
                    on conflict (dry_run_request_id) do nothing
                    """,
                    (dry_run_request_id,),
                )
                cursor.execute(
                    """
                    insert into public.oom_sakkie_agent_dry_run_results (
                        dry_run_result_id, dry_run_request_id, status, mode,
                        specialist_slug, result_text, recorded_by
                    )
                    values (
                        %s, %s, 'recorded_for_owner_review',
                        'dry_run_result_review_only', 'sentinel',
                        'learning influence source', 'unittest'
                    )
                    on conflict (dry_run_result_id) do nothing
                    """,
                    (dry_run_result_id, dry_run_request_id),
                )
                cursor.execute(
                    """
                    insert into public.oom_sakkie_learning_influence_proposals (
                        proposal_id, source_result_id, status, mode, specialist_slug,
                        proposal_title, proposal_text
                    )
                    values (
                        %s, %s, 'proposed_for_owner_review',
                        'learning_influence_proposal_only', 'sentinel',
                        'learning proposal', 'planning only'
                    )
                    """,
                    (proposal_id, dry_run_result_id),
                )
                cursor.execute(
                    """
                    insert into public.oom_sakkie_learning_influence_proposal_events (
                        event_id, proposal_id, event_type, notes, recorded_by
                    )
                    values (%s, %s, 'review_note', 'append-only event', 'unittest')
                    """,
                    (event_id, proposal_id),
                )
                connection.commit()

        for table_name, id_column, row_id, text_column in (
            ("public.oom_sakkie_learning_influence_proposals", "proposal_id", proposal_id, "proposal_text"),
            ("public.oom_sakkie_learning_influence_proposal_events", "event_id", event_id, "notes"),
        ):
            with psycopg.connect(database_url, connect_timeout=10) as connection:
                with connection.cursor() as cursor:
                    with self.assertRaises(Exception) as update_error:
                        cursor.execute(
                            f"update {table_name} set {text_column} = {text_column} where {id_column} = %s",
                            (row_id,),
                        )
                    connection.rollback()
                    self.assertIn("append-only", str(update_error.exception).lower())

            with psycopg.connect(database_url, connect_timeout=10) as connection:
                with connection.cursor() as cursor:
                    with self.assertRaises(Exception) as delete_error:
                        cursor.execute(f"delete from {table_name} where {id_column} = %s", (row_id,))
                    connection.rollback()
                    self.assertIn("append-only", str(delete_error.exception).lower())

    def test_live_pg_learning_influence_from_result_requires_acceptance_and_is_idempotent(self):
        database_url = os.getenv("DATABASE_URL", "").strip()
        if not database_url:
            self.skipTest("DATABASE_URL not configured for learning influence from-result integration test")
        try:
            import psycopg
        except ImportError:
            self.skipTest("psycopg not installed")

        suffix = build_trace_id().replace("OSK-", "")
        dry_run_request_id = f"OSK-AGENT-DRYRUN-FROM-RESULT-{suffix}"
        dry_run_result_id = f"OSK-AGENT-DRYRUN-RESULT-FROM-RESULT-{suffix}"

        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                cursor.execute("select to_regclass('public.oom_sakkie_learning_influence_proposals')")
                if cursor.fetchone()[0] is None:
                    self.skipTest("learning influence proposal tables are not migrated")
                cursor.execute(
                    """
                    insert into public.oom_sakkie_agent_dry_run_requests (
                        dry_run_request_id, status, mode, specialist_slug,
                        requested_by, purpose
                    )
                    values (
                        %s, 'approved_for_read_only_dry_run',
                        'read_only_dry_run_request_only', 'sentinel',
                        'unittest', 'learning influence from-result test'
                    )
                    """,
                    (dry_run_request_id,),
                )
                cursor.execute(
                    """
                    insert into public.oom_sakkie_agent_dry_run_results (
                        dry_run_result_id, dry_run_request_id, status, mode,
                        specialist_slug, result_text, findings_json, recorded_by
                    )
                    values (
                        %s, %s, 'recorded_for_owner_review',
                        'dry_run_result_review_only', 'sentinel',
                        'from-result source evidence', '["from-result finding"]'::jsonb,
                        'unittest'
                    )
                    """,
                    (dry_run_result_id, dry_run_request_id),
                )
                connection.commit()

        rejected, rejected_status = record_learning_influence_proposal_from_result(
            dry_run_result_id,
            database_url=database_url,
        )

        self.assertEqual(rejected_status, 409)
        self.assertFalse(rejected["success"])
        self.assertEqual(rejected["status"], "source_result_not_accepted_for_learning")
        self.assertEqual(rejected["source_result_id"], dry_run_result_id)
        self.assertEqual(rejected["created_count"], 0)
        self.assertFalse(rejected["applies_learning_now"])
        self.assertFalse(rejected["changes_prompt_now"])
        self.assertFalse(rejected["changes_runtime_now"])
        self.assertFalse(rejected["dispatch_enabled"])
        self.assertFalse(rejected["writes"])

        accepted_event, accepted_status = record_agent_dry_run_result_event(
            dry_run_result_id,
            {
                "event_type": "accepted_for_learning",
                "notes": "accepted only as planning evidence",
                "recorded_by": "unittest",
            },
            database_url=database_url,
        )

        self.assertEqual(accepted_status, 201)
        self.assertTrue(accepted_event["success"])

        created, created_status = record_learning_influence_proposal_from_result(
            dry_run_result_id,
            database_url=database_url,
        )

        self.assertEqual(created_status, 201)
        self.assertTrue(created["success"])
        self.assertEqual(created["created_count"], 1)
        self.assertEqual(created["accepted_count"], 1)
        self.assertEqual(len(created["learning_influence_proposals"]), 1)
        proposal = created["learning_influence_proposals"][0]
        self.assertEqual(proposal["source_result_id"], dry_run_result_id)
        self.assertEqual(proposal["mode"], "learning_influence_proposal_only")
        self.assertFalse(proposal["applies_learning_now"])
        self.assertFalse(proposal["changes_prompt_now"])
        self.assertFalse(proposal["changes_runtime_now"])
        self.assertFalse(proposal["dispatch_enabled"])
        self.assertFalse(proposal["writes"])

        existing, existing_status = record_learning_influence_proposal_from_result(
            dry_run_result_id,
            database_url=database_url,
        )

        self.assertEqual(existing_status, 201)
        self.assertTrue(existing["success"])
        self.assertEqual(existing["created_count"], 0)
        self.assertEqual(existing["accepted_count"], 1)
        self.assertEqual(len(existing["learning_influence_proposals"]), 1)
        self.assertEqual(existing["learning_influence_proposals"][0]["proposal_id"], proposal["proposal_id"])
        self.assertEqual(existing["learning_influence_proposals"][0]["source_result_id"], dry_run_result_id)

    def test_live_pg_learning_influence_consumption_audit_rail_is_append_only_and_consumed_once(self):
        database_url = os.getenv("DATABASE_URL", "").strip()
        if not database_url:
            self.skipTest("DATABASE_URL not configured for learning influence consumption integration test")
        try:
            import psycopg
        except ImportError:
            self.skipTest("psycopg not installed")

        suffix = build_trace_id().replace("OSK-", "")
        dry_run_request_id = f"OSK-AGENT-DRYRUN-CONSUME-{suffix}"
        dry_run_result_id = f"OSK-AGENT-DRYRUN-RESULT-CONSUME-{suffix}"
        proposal_id = f"OSK-LEARNING-INFLUENCE-CONSUME-{suffix}"
        proposal_event_id = f"OSK-LEARNING-INFLUENCE-EVENT-CONSUME-{suffix}"

        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                cursor.execute("select to_regclass('public.oom_sakkie_learning_influence_consumption_requests')")
                if cursor.fetchone()[0] is None:
                    self.skipTest("learning influence consumption audit rail tables are not migrated")
                cursor.execute(
                    """
                    insert into public.oom_sakkie_agent_dry_run_requests (
                        dry_run_request_id, status, mode, specialist_slug,
                        requested_by, purpose
                    )
                    values (
                        %s, 'approved_for_read_only_dry_run',
                        'read_only_dry_run_request_only', 'sentinel',
                        'unittest', 'learning influence consumption test'
                    )
                    """,
                    (dry_run_request_id,),
                )
                cursor.execute(
                    """
                    insert into public.oom_sakkie_agent_dry_run_results (
                        dry_run_result_id, dry_run_request_id, status, mode,
                        specialist_slug, result_text, recorded_by
                    )
                    values (
                        %s, %s, 'recorded_for_owner_review',
                        'dry_run_result_review_only', 'sentinel',
                        'consumption rail source evidence', 'unittest'
                    )
                    """,
                    (dry_run_result_id, dry_run_request_id),
                )
                cursor.execute(
                    """
                    insert into public.oom_sakkie_learning_influence_proposals (
                        proposal_id, source_result_id, status, mode, specialist_slug,
                        proposal_title, proposal_text
                    )
                    values (
                        %s, %s, 'proposed_for_owner_review',
                        'learning_influence_proposal_only', 'sentinel',
                        'consumption rail proposal', 'planning note only'
                    )
                    """,
                    (proposal_id, dry_run_result_id),
                )
                connection.commit()
                with self.assertRaises(Exception) as request_error:
                    cursor.execute(
                        """
                        insert into public.oom_sakkie_learning_influence_consumption_requests (
                            consumption_request_id, proposal_id, source_result_id,
                            requested_target_kind, requested_target_field,
                            changes_prompt_now
                        )
                        values (
                            %s, %s, %s,
                            'planning_context_note', 'owner_review_notes',
                            true
                        )
                        """,
                        (f"OSK-LEARNING-CONSUME-BAD-{suffix}", proposal_id, dry_run_result_id),
                    )
                connection.rollback()
                self.assertIn("check", str(request_error.exception).lower())

        rejected, rejected_status = record_learning_influence_consumption_request(
            {
                "proposal_id": proposal_id,
                "requested_target_kind": "planning_context_note",
                "requested_target_field": "owner_review_notes",
            },
            database_url=database_url,
        )

        self.assertEqual(rejected_status, 409)
        self.assertFalse(rejected["success"])
        self.assertEqual(rejected["status"], "proposal_not_approved_for_future_planning")
        self.assertFalse(rejected["applies_learning_now"])
        self.assertFalse(rejected["changes_prompt_now"])
        self.assertFalse(rejected["changes_runtime_now"])
        self.assertFalse(rejected["dispatch_enabled"])
        self.assertFalse(rejected["writes"])

        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    insert into public.oom_sakkie_learning_influence_proposal_events (
                        event_id, proposal_id, event_type, notes, recorded_by
                    )
                    values (%s, %s, 'approved_for_future_planning', 'approved for design review rail', 'unittest')
                    """,
                    (proposal_event_id, proposal_id),
                )
                connection.commit()

        created, created_status = record_learning_influence_consumption_request(
            {
                "proposal_id": proposal_id,
                "requested_target_kind": "planning_context_note",
                "requested_target_field": "owner_review_notes",
                "request_note": "Review-note artifact only.",
                "requested_by": "unittest",
            },
            database_url=database_url,
        )

        self.assertEqual(created_status, 201)
        self.assertTrue(created["success"])
        self.assertEqual(created["created_count"], 1)
        self.assertTrue(created["review_note_artifact_only"])
        self.assertEqual(len(created["learning_influence_consumption_requests"]), 1)
        consumption_request = created["learning_influence_consumption_requests"][0]
        consumption_request_id = consumption_request["consumption_request_id"]
        self.assertEqual(consumption_request["proposal_id"], proposal_id)
        self.assertEqual(consumption_request["requested_target_kind"], "planning_context_note")
        self.assertEqual(consumption_request["review_note_artifact"]["kind"], "review_note_only")
        self.assertTrue(consumption_request["review_note_artifact"]["proposal_text_is_untrusted"])
        self.assertFalse(consumption_request["applies_learning_now"])
        self.assertFalse(consumption_request["changes_prompt_now"])
        self.assertFalse(consumption_request["changes_runtime_now"])
        self.assertFalse(consumption_request["dispatch_enabled"])
        self.assertFalse(consumption_request["writes"])

        existing, existing_status = record_learning_influence_consumption_request(
            {
                "proposal_id": proposal_id,
                "requested_target_kind": "planning_context_note",
                "requested_target_field": "owner_review_notes",
            },
            database_url=database_url,
        )

        self.assertEqual(existing_status, 201)
        self.assertTrue(existing["success"])
        self.assertEqual(existing["created_count"], 0)
        self.assertEqual(existing["learning_influence_consumption_requests"][0]["consumption_request_id"], consumption_request_id)

        review_event, review_status = record_learning_influence_consumption_event(
            consumption_request_id,
            {"event_type": "review_note", "notes": "review note only", "recorded_by": "unittest"},
            database_url=database_url,
        )
        self.assertEqual(review_status, 201)
        self.assertTrue(review_event["success"])
        self.assertFalse(review_event["changes_prompt_now"])

        design_approval, design_approval_status = record_learning_influence_consumption_event(
            consumption_request_id,
            {"event_type": "approved_for_design_review", "notes": "owner approved review-note consumer", "recorded_by": "unittest"},
            database_url=database_url,
        )
        self.assertEqual(design_approval_status, 201)
        self.assertTrue(design_approval["success"])

        consumer_result, consumer_status = produce_learning_influence_review_note_artifact(
            consumption_request_id,
            {
                "recorded_by": "unittest",
                "previous_review_note_text": "old planning note",
                "proposed_review_note_text": "new review note only",
            },
            database_url=database_url,
        )
        self.assertEqual(consumer_status, 201)
        self.assertTrue(consumer_result["success"])
        self.assertEqual(consumer_result["mode"], "learning_influence_review_note_consumer_only")
        self.assertTrue(consumer_result["review_note_artifact_only"])
        self.assertEqual(consumer_result["review_note_artifact"]["kind"], "review_note_only")
        self.assertEqual(consumer_result["review_note_artifact"]["proposed_review_note_text"], "new review note only")
        self.assertFalse(consumer_result["review_note_artifact"]["applies_learning_now"])
        self.assertFalse(consumer_result["applies_learning_now"])
        self.assertFalse(consumer_result["changes_prompt_now"])
        self.assertFalse(consumer_result["changes_runtime_now"])
        self.assertFalse(consumer_result["dispatch_enabled"])
        self.assertFalse(consumer_result["writes"])

        repeated_consumer, repeated_consumer_status = produce_learning_influence_review_note_artifact(
            consumption_request_id,
            {"recorded_by": "unittest"},
            database_url=database_url,
        )
        self.assertEqual(repeated_consumer_status, 409)
        self.assertFalse(repeated_consumer["success"])
        self.assertEqual(repeated_consumer["status"], "already_consumed")
        self.assertEqual(repeated_consumer["review_note_artifact"], {})

        second_consumed, second_consumed_status = record_learning_influence_consumption_event(
            consumption_request_id,
            {"event_type": "consumed_for_patch_proposal", "notes": "second marker", "recorded_by": "unittest"},
            database_url=database_url,
            allow_consumed=True,
        )
        self.assertEqual(second_consumed_status, 503)
        self.assertFalse(second_consumed["success"])
        self.assertEqual(second_consumed["status"], "learning_influence_consumption_event_write_failed")
        self.assertIn(second_consumed["error_type"], {"UniqueViolation", "IntegrityError"})

        for table_name, id_column, row_id, text_column in (
            (
                "public.oom_sakkie_learning_influence_consumption_requests",
                "consumption_request_id",
                consumption_request_id,
                "request_note",
            ),
            (
                "public.oom_sakkie_learning_influence_consumption_events",
                "event_id",
                consumer_result["event_id"],
                "notes",
            ),
        ):
            with psycopg.connect(database_url, connect_timeout=10) as connection:
                with connection.cursor() as cursor:
                    with self.assertRaises(Exception) as update_error:
                        cursor.execute(
                            f"update {table_name} set {text_column} = {text_column} where {id_column} = %s",
                            (row_id,),
                        )
                    connection.rollback()
                    self.assertIn("append-only", str(update_error.exception).lower())

            with psycopg.connect(database_url, connect_timeout=10) as connection:
                with connection.cursor() as cursor:
                    with self.assertRaises(Exception) as delete_error:
                        cursor.execute(f"delete from {table_name} where {id_column} = %s", (row_id,))
                    connection.rollback()
                    self.assertIn("append-only", str(delete_error.exception).lower())

    def test_trace_list_not_configured_is_safe(self):
        result, status = list_recent_traces(database_url="")

        self.assertEqual(status, 503)
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "not_configured")
        self.assertEqual(result["traces"], [])

    def test_review_advisor_trace_list_not_configured_is_safe(self):
        result, status = list_review_advisor_traces(database_url="")

        self.assertEqual(status, 503)
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "not_configured")
        self.assertEqual(result["issue_traces"], [])
        self.assertEqual(result["unreviewed_traces"], [])

    @patch.dict("sys.modules", {"psycopg": Mock()})
    def test_review_advisor_trace_list_uses_combined_ranked_query(self):
        import sys

        executed = {}
        cursor = Mock()
        cursor.fetchall.return_value = []
        cursor.__enter__ = Mock(return_value=cursor)
        cursor.__exit__ = Mock(return_value=False)
        connection = Mock()
        connection.cursor.return_value = cursor
        connection.__enter__ = Mock(return_value=connection)
        connection.__exit__ = Mock(return_value=False)
        sys.modules["psycopg"].connect.return_value = connection

        def capture_execute(sql, params):
            executed["sql"] = sql
            executed["params"] = params

        cursor.execute.side_effect = capture_execute

        result, status = list_review_advisor_traces(
            limit=12,
            channel="kiosk",
            days=14,
            database_url="postgresql://example",
        )

        query = executed["sql"].lower()

        self.assertEqual(status, 200)
        self.assertTrue(result["success"])
        self.assertEqual(result["days"], 14)
        self.assertIn("union all", query)
        self.assertIn("row_number() over", query)
        self.assertIn("partition by queue_kind", query)
        self.assertIn("t.created_at >= now()", query)
        self.assertEqual(executed["params"]["channel"], "kiosk")
        self.assertEqual(executed["params"]["limit"], 12)
        self.assertEqual(executed["params"]["days"], 14)

    def test_trace_feedback_rejects_invalid_type_before_db(self):
        result, status = record_trace_feedback(
            "OSK-TEST",
            {"feedback_type": "please_make_it_spicy"},
            database_url="postgresql://should-not-be-used",
        )

        self.assertEqual(status, 400)
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "invalid_feedback_type")
        self.assertEqual(result["allowed_feedback_types"], sorted(FEEDBACK_TYPES))

    def test_trace_feedback_not_configured_is_safe(self):
        result, status = record_trace_feedback(
            "OSK-TEST",
            {"feedback_type": "correct", "notes": "worked"},
            database_url="",
        )

        self.assertEqual(status, 503)
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "not_configured")

    def test_review_summary_not_configured_is_safe(self):
        result, status = get_trace_review_summary(database_url="")

        self.assertEqual(status, 503)
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "not_configured")

    def test_review_filter_allows_known_values_only(self):
        self.assertEqual(_review_filter("all"), "all")
        self.assertEqual(_review_filter("reviewed"), "reviewed")
        self.assertEqual(_review_filter("unreviewed"), "unreviewed")
        self.assertEqual(_review_filter("issues"), "issues")
        self.assertEqual(_review_filter("surprise"), "all")

    def test_trace_list_where_clause_combines_review_and_search(self):
        clause = _trace_list_where_clause("issues", True)

        self.assertIn("feedback_type is not null", clause)
        self.assertIn("feedback_type <> 'correct'", clause)
        self.assertIn("user_text", clause)
        self.assertIn("answer", clause)
        self.assertIn("tool_name", clause)
        self.assertIn("trace_id", clause)


if __name__ == "__main__":
    unittest.main()
