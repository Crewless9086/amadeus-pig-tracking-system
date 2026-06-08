import unittest
from unittest.mock import patch

from app import app
from modules.oom_sakkie.access import is_review_request_allowed


class OomSakkieRouteTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

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

    def test_message_route_remains_available_for_non_local_access_policy(self):
        response = self.client.post(
            "/api/oom-sakkie/message",
            json={"text": "what is the power doing now", "channel": "kiosk"},
            environ_base={"REMOTE_ADDR": "203.0.113.10"},
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
