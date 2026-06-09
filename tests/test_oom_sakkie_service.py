import unittest
import os
from urllib import error as urllib_error
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch

from modules.oom_sakkie.policy import get_runtime_policy
from modules.oom_sakkie.agent_runtime import (
    build_agent_crew_brief,
    build_agent_activity,
    get_agent_activation_plan,
    get_agent_runtime_status,
    recommend_agent_for_text,
)
from modules.oom_sakkie.agent_dry_run_handoff import build_agent_dry_run_handoff
from modules.oom_sakkie.agent_dry_run_store import (
    _agent_dry_run_request_params,
    _agent_dry_run_request_row,
    get_agent_dry_run_request,
    list_agent_dry_run_requests,
    record_agent_dry_run_event,
    record_agent_dry_run_request,
)
from modules.oom_sakkie.agent_dry_run_result_store import (
    _agent_dry_run_result_params,
    _agent_dry_run_result_row,
    get_agent_dry_run_result,
    list_agent_dry_run_results,
    record_agent_dry_run_result_event,
)
from modules.oom_sakkie.agent_dry_run_result_review import build_agent_dry_run_result_review_packet
from modules.oom_sakkie.llm_answer import (
    _build_payload,
    compose_answer_with_llm,
    parse_llm_answer_response,
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
from modules.oom_sakkie.forge_handoff import build_forge_handoff
from modules.oom_sakkie.learning_packet import (
    approve_build_request,
    build_learning_packet,
    get_implementation_queue,
)
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


class OomSakkieServiceTests(unittest.TestCase):
    def test_tool_registry_contract(self):
        self.assertEqual(
            set(TOOL_REGISTRY),
            {
                "sentinel_dry_run_review",
                "agent_dry_run_status",
                "agent_learning_evidence",
                "agent_activation_plan",
                "agent_crew_brief",
                "agent_crew_status",
                "system_work_status",
                "farm_operating_brief",
                "business_growth_brief",
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
                self.assertEqual(tool.risk_level, RiskLevel.READ_ONLY)
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

    @patch.dict(os.environ, {}, clear=True)
    def test_runtime_policy_is_read_only_local_kiosk(self):
        policy = get_runtime_policy()

        self.assertTrue(policy["success"])
        self.assertEqual(policy["mode"], "local_kiosk_read_only")
        self.assertTrue(policy["backend_as_brain"])
        self.assertFalse(policy["telegram_cutover_enabled"])
        self.assertFalse(policy["llm_answer_enabled"])
        self.assertFalse(policy["llm_router_enabled"])
        self.assertFalse(policy["write_tools_enabled"])
        self.assertFalse(policy["physical_controls_enabled"])
        self.assertFalse(policy["backend_voice_vendors_enabled"])
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
        self.assertEqual(policy["kiosk_policy"]["max_risk_level"], 0)
        self.assertEqual(policy["kiosk_policy"]["requires_confirmation_tools"], [])
        self.assertEqual(policy["tool_counts"]["write_or_confirmation"], 0)
        self.assertIn("write tools", policy["blocked_capabilities"])

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
        self.assertFalse(plan["runtime_enabled"])
        self.assertFalse(plan["dispatch_enabled"])
        self.assertFalse(plan["autonomous_loops_enabled"])
        self.assertFalse(plan["writes_enabled"])
        self.assertIn("live specialist dispatch", plan["blocked_capabilities"])
        self.assertIn("owner_approval", plan["next_gate"])

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
        self.assertIn("No accepted Sentinel learning evidence", result["summary"])
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
                "specialist_slug": "sentinel",
                "result_text": "Sentinel says guardrails stayed locked.",
                "findings": ["Runtime flags stayed false."],
                "latest_event": {
                    "event_type": "accepted_for_learning",
                    "notes": "Useful.",
                    "created_at": "2026-06-08T10:00:00+00:00",
                },
            }],
        }, 200)

        result = agent_activation_plan_handler({})

        self.assertTrue(result["success"])
        self.assertIn("Accepted learning evidence: 1 Sentinel result", result["summary"])
        self.assertEqual(result["llm_context"]["accepted_learning_count"], 1)
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
        self.assertEqual(result["llm_context"]["tool_audit"]["non_read_only_tools"], [])
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
            }],
        }, 200)
        mock_results.return_value = ({
            "success": True,
            "status": "ok",
            "dry_run_results": [{
                "dry_run_result_id": "OSK-AGENT-DRYRUN-RESULT-1",
                "dry_run_request_id": "OSK-AGENT-DRYRUN-1",
                "latest_event": None,
            }],
        }, 200)

        result = agent_dry_run_status_handler({})

        self.assertTrue(result["success"])
        self.assertIn("1 request", result["summary"])
        self.assertIn("1 result", result["summary"])
        self.assertIn("No specialist was dispatched", result["safety_notes"][0])
        self.assertEqual(result["llm_context"]["kind"], "agent_dry_run_status")
        self.assertEqual(result["llm_context"]["counts"]["waiting_for_review"], 1)
        self.assertEqual(result["llm_context"]["counts"]["results_waiting_for_owner_review"], 1)
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
                    "specialist_slug": "sentinel",
                    "result_text": "Sentinel says the runtime flags stayed off.",
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
                    "specialist_slug": "sentinel",
                    "result_text": "Not accepted.",
                    "findings": ["Ignore."],
                    "latest_event": {"event_type": "review_note"},
                },
            ],
        }, 200)

        result = agent_learning_evidence_handler({})

        self.assertTrue(result["success"])
        self.assertIn("1 accepted Sentinel result", result["summary"])
        self.assertEqual(result["llm_context"]["kind"], "agent_learning_evidence")
        self.assertEqual(result["llm_context"]["accepted_count"], 1)
        self.assertEqual(result["llm_context"]["evidence"][0]["dry_run_result_id"], "OSK-AGENT-DRYRUN-RESULT-1")
        self.assertFalse(result["llm_context"]["runtime_flags"]["dispatch_enabled"])
        self.assertFalse(result["llm_context"]["runtime_flags"]["applies_runtime_change"])
        self.assertIn("read-only", result["safety_notes"][0])

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

    def test_agent_dry_run_store_not_configured_and_rejects_unapproved_specialist(self):
        result, status_code = record_agent_dry_run_request({
            "specialist_slug": "sentinel",
            "owner_text": "approve first dry run",
        }, database_url="")

        self.assertEqual(status_code, 503)
        self.assertEqual(result["status"], "not_configured")

        result, status_code = record_agent_dry_run_request({
            "specialist_slug": "ledger",
            "owner_text": "approve ledger dry run",
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

    @patch("modules.oom_sakkie.tools.list_deploy_decisions")
    @patch("modules.oom_sakkie.tools.list_patch_proposals")
    @patch("modules.oom_sakkie.tools.list_build_requests")
    def test_system_work_status_is_read_only_approval_summary(self, mock_builds, mock_patches, mock_deploys):
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

        result = system_work_status_handler({})

        self.assertTrue(result["success"])
        self.assertEqual(result["status"], "ok")
        self.assertIn("Forge Handoff", result["summary"])
        self.assertIn("patch proposal", result["summary"])
        self.assertIn("read-only", result["safety_notes"][0])
        self.assertEqual(result["llm_context"]["kind"], "system_work_status")
        self.assertEqual(result["llm_context"]["counts"]["pending_build_requests"], 1)
        self.assertIn("Open Forge Handoff", result["llm_context"]["next_action"])

    @patch("modules.oom_sakkie.tools.list_deploy_decisions")
    @patch("modules.oom_sakkie.tools.list_patch_proposals")
    @patch("modules.oom_sakkie.tools.list_build_requests")
    def test_system_work_status_tracks_pipeline_stages(self, mock_builds, mock_patches, mock_deploys):
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

        result = system_work_status_handler({})

        self.assertEqual(result["llm_context"]["counts"]["pending_build_requests"], 0)
        self.assertEqual(result["llm_context"]["counts"]["deploy_ready_patch_proposals"], 1)
        self.assertIn("verification", result["llm_context"]["next_action"])
        self.assertIn("OSK-PATCH-READY", result["llm_context"]["next_action"])

    @patch("modules.oom_sakkie.tools.list_deploy_decisions")
    @patch("modules.oom_sakkie.tools.list_patch_proposals")
    @patch("modules.oom_sakkie.tools.list_build_requests")
    def test_system_work_status_warns_when_store_unavailable(self, mock_builds, mock_patches, mock_deploys):
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
            "what is the agent dry-run queue status": "agent_dry_run_status",
            "what is the sentinel dry-run result queue status": "agent_dry_run_status",
            "what did sentinel learn": "agent_learning_evidence",
            "show me agent learning evidence": "agent_learning_evidence",
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
        self.assertIn("mention all required sections", system)
        self.assertIn("For business_growth_brief, sound like a business advisor", system)
        self.assertIn("internal offer brief outline only", system)
        self.assertIn("not customer-facing copy", system)
        self.assertIn("ask exactly one approval-style follow-up question", system)
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
