import unittest
from unittest.mock import patch

from modules.charlie.private_tools import execute_private_tool


class CharliePrivateToolsTests(unittest.TestCase):
    @patch("modules.charlie.private_tools.delegate_to_agent", return_value=({"success": True}, 200))
    def test_broad_farm_question_routes_through_oom_sakkie(self, delegate):
        execute_private_tool("read_farm_status", {"owner_question": "What needs attention on the farm today?"})
        self.assertEqual(delegate.call_args.args[0], "oom-sakkie")

    @patch("modules.charlie.private_tools.delegate_to_agent", return_value=({"success": True}, 200))
    def test_precise_herd_question_routes_directly_to_herdmaster(self, delegate):
        execute_private_tool("read_farm_status", {"owner_question": "How many pigs are on the farm?"})
        self.assertEqual(delegate.call_args.args[0], "herdmaster")

    @patch("modules.agents.herdmaster.get_pig_detail")
    def test_read_pig_returns_authoritative_profile_summary(self, get_detail):
        get_detail.return_value = {"pig_id": "PIG-104", "tag_number": "104", "status": "Active", "on_farm": "Yes", "sex": "Female", "current_pen_id": "PEN-3", "current_pen_name": "PEN-3", "current_weight_kg": 8.4}
        result, status = execute_private_tool("read_pig", {"pig_id": "104"})
        self.assertEqual(status, 200)
        self.assertEqual(result["agent"]["agent_id"], "herdmaster")
        self.assertIn("Female", result["direct_answer"])
        self.assertEqual(next(row["value"] for row in result["facts"] if row["name"] == "current_weight_kg"), 8.4)

    @patch("modules.charlie.private_tools.list_missions")
    def test_create_mission_reuses_active_duplicate(self, list_missions):
        list_missions.return_value = ({"missions": [{"mission_id": "M-EXISTING", "title": "Improve Beacon workflow", "status": "approved"}]}, 200)
        result, status = execute_private_tool("create_mission", {"title": "Improve Beacon workflow"})
        self.assertEqual(status, 200)
        self.assertTrue(result["duplicate_prevented"])
        self.assertEqual(result["mission_id"], "M-EXISTING")

    @patch("modules.charlie.private_tools.list_missions")
    def test_blocked_summary_reconciles_legacy_false_owner_label(self, list_missions):
        list_missions.return_value = ({"missions": [{
            "mission_id": "M-OLD", "title": "Old retry", "status": "blocked",
            "metadata": {"review_packet": {
                "blocked_reason": "Repeated same blocker loop detected; durable loop cap exhausted.",
                "block_disposition": {"block_class": "owner_decision_required", "owner_required": True},
            }},
        }]}, 200)
        result, status = execute_private_tool("read_blocked", {})
        self.assertEqual(status, 200)
        self.assertFalse(result["missions"][0]["owner_required"])
        self.assertIn("next: builder", result["summary"])

    @patch("modules.charlie.private_tools.update_mission_status")
    @patch("modules.charlie.private_tools.get_mission")
    def test_approve_reloads_and_uses_compare_and_set(self, get_mission, update_status):
        get_mission.side_effect = [
            ({"mission": {"mission_id": "M1", "status": "new"}}, 200),
            ({"mission": {"mission_id": "M1", "status": "approved"}}, 200),
        ]
        update_status.return_value = ({"success": True, "status": "ok"}, 200)
        result, status = execute_private_tool("approve_mission", {"mission_id": "M1"})
        self.assertEqual(status, 200)
        self.assertTrue(result["success"])
        self.assertEqual(update_status.call_args.kwargs["expected_status"], "new")

    @patch("modules.charlie.private_tools.transition_mission_review_state")
    @patch("modules.charlie.private_tools.get_mission")
    def test_send_back_uses_authoritative_review_transition(self, get_mission, transition):
        get_mission.side_effect = [
            ({"mission": {"mission_id": "M1", "status": "blocked", "metadata": {"review_packet": {"responsible_stage": "builder"}}}}, 200),
            ({"mission": {"mission_id": "M1", "status": "blocked", "metadata": {"review_packet": {"return_to_stage": "builder"}}}}, 200),
        ]
        transition.return_value = ({"success": True, "status": "review_state_transitioned"}, 200)
        result, status = execute_private_tool("send_back_mission", {"mission_id": "M1"})
        self.assertEqual(status, 200)
        self.assertEqual(result["target_stage"], "builder")
        self.assertEqual(transition.call_args.kwargs["expected_status"], "blocked")

    def test_unknown_tool_fails_closed(self):
        result, status = execute_private_tool("customer_send", {})
        self.assertEqual(status, 400)
        self.assertFalse(result["success"])

    def test_read_mission_requires_identifier(self):
        result, status = execute_private_tool("read_mission", {})
        self.assertEqual(status, 400)
        self.assertEqual(result["status"], "mission_id_required")

    @patch("modules.charlie.private_tools.live_stock_learning_scorecard")
    def test_sam_status_is_read_only_scorecard(self, scorecard):
        scorecard.return_value = ({"scorecard": {"total_events": 12, "owner_edit_events": 3}}, 200)
        result, status = execute_private_tool("read_sam_status", {})
        self.assertEqual(status, 200)
        self.assertIn("12 captured", result["summary"])

    @patch("modules.charlie.private_tools.list_orders")
    def test_orders_status_summarizes_without_writes(self, list_orders):
        list_orders.return_value = [
            {"order_status": "Draft", "approval_status": "Approved"},
            {"order_status": "Completed", "approval_status": "Approved"},
        ]
        result, status = execute_private_tool("read_orders_status", {})
        self.assertEqual(status, 200)
        self.assertEqual(result["counts"], {"total": 2, "active": 1, "ready": 2})

    @patch("modules.charlie.private_tools.runner_status", return_value={"status": "runner_stale_or_stopped", "process_alive": True, "heartbeat_fresh": True})
    @patch("modules.charlie.private_tools.mission_status_summary", return_value=({"counts": {}}, 200))
    @patch("modules.charlie.private_tools.list_missions", return_value=({"missions": []}, 200))
    def test_core_status_uses_process_and_heartbeat_health(self, _missions, _summary, _runner):
        result, status = execute_private_tool("read_core_status", {})
        self.assertEqual(status, 200)
        self.assertIn("Runner: healthy", result["summary"])

    @patch("modules.charlie.private_tools.runner_status", return_value={"status": "runner_active", "process_alive": True, "heartbeat_fresh": True, "current_agent": "builder"})
    @patch("modules.charlie.private_tools.mission_status_summary", return_value=({"counts": {"in_progress": 1}}, 200))
    @patch("modules.charlie.private_tools.list_missions", return_value=({"missions": [{"mission_id": "M-12345678", "title": "Improve CORE", "metadata": {"progress_pct": 42}}]}, 200))
    def test_core_status_names_active_mission(self, _missions, _summary, _runner):
        result, status = execute_private_tool("read_core_status", {})
        self.assertEqual(status, 200)
        self.assertIn("Improve CORE [M-12345678]", result["summary"])
        self.assertIn("stage builder", result["summary"])
        self.assertIn("42% progress", result["summary"])

    @patch("modules.charlie.private_tools.get_order_operator_summary", return_value={"outstanding_actions": ["Generate quote"]})
    @patch("modules.charlie.private_tools.get_order_detail", return_value={"order": {"Order_Status": "Draft", "Approval_Status": "Approved"}, "lines": [{}, {}]})
    def test_order_read_returns_verified_operating_summary(self, _detail, _operator):
        result, status = execute_private_tool("read_order", {"order_id": "ORD-2026-12BCCC"})
        self.assertEqual(status, 200)
        self.assertIn("2 line(s)", result["summary"])
        self.assertIn("Generate quote", result["summary"])

    @patch("modules.charlie.private_tools.prepare_live_stock_sales_pack")
    def test_order_pack_is_prepare_only(self, prepare):
        prepare.return_value = {"success": True, "status": "ready", "missing_fields": [], "errors": [], "customer_send_allowed": False, "reserves_stock": False}
        result, status = execute_private_tool("prepare_order_pack", {"order_id": "ORD-2026-12BCCC"})
        self.assertEqual(status, 200)
        self.assertTrue(result["prepared_only"])
        self.assertFalse(result["customer_send_allowed"])
        self.assertFalse(result["reserves_stock"])

    @patch("modules.charlie.private_tools.build_beacon_caption_suggestions")
    def test_beacon_draft_never_posts(self, compose):
        compose.return_value = ({"success": True, "suggestions": ["One", "Two", "Three"]}, 200)
        result, status = execute_private_tool("prepare_beacon_draft", {"brief": "Healthy litter update", "campaign_lane": "live_stock_awareness"})
        self.assertEqual(status, 200)
        self.assertFalse(result["posts_publicly"])
        self.assertIn("Option 1", result["summary"])

    @patch("modules.charlie.private_tools.list_capability_trust", return_value=({"capabilities": [{"capability_key": "core.recovery", "tier": "delegated"}]}, 200))
    def test_trust_status_is_read_only(self, _trust):
        result, status = execute_private_tool("read_trust", {})
        self.assertEqual(status, 200)
        self.assertIn("1 delegated or auto", result["summary"])

    @patch("modules.charlie.private_tools.plan_live_stock_next_action", return_value={"goal": "buy six piglets", "stage": "qualified", "next_action": "prepare_quote", "missing_fields": []})
    @patch("modules.charlie.private_tools.load_chatwoot_conversation_history", return_value={"messages": [{}, {}]})
    @patch("modules.charlie.private_tools.get_intake_context", return_value={"conversation_id": "1871", "items": []})
    def test_sam_conversation_read_combines_intake_history_and_plan(self, _intake, _history, _plan):
        result, status = execute_private_tool("read_sam_conversation", {"conversation_id": "1871"})
        self.assertEqual(status, 200)
        self.assertIn("buy six piglets", result["summary"])
        self.assertIn("2 recent message", result["summary"])


if __name__ == "__main__":
    unittest.main()
