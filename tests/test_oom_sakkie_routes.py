import os
import unittest
from unittest.mock import patch

from app import app
from modules.oom_sakkie.access import is_review_request_allowed


class OomSakkieRouteTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

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
        self.assertEqual(data["kiosk_policy"]["max_risk_level"], 0)
        self.assertEqual(data["continue_conversation_max_turns"], 5)
        self.assertEqual(data["voice_auto_send_ms"], 2000)
        self.assertEqual(data["message_endpoint_access"]["default"], "reachable_wherever_flask_is_reachable")
        self.assertIn("reverse_proxy_caveat", data["review_endpoints_access"])

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
        self.assertEqual(data["locked_count"], data["authority_count"])
        self.assertFalse(data["runtime_enabled"])
        self.assertFalse(data["dispatch_enabled"])
        self.assertFalse(data["writes_enabled"])
        self.assertFalse(data["review_guard"]["runs_specialist"])
        self.assertFalse(data["review_guard"]["dispatch_enabled"])
        self.assertFalse(data["review_guard"]["writes"])
        by_authority = {item["authority"]: item for item in data["areas"]}
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
