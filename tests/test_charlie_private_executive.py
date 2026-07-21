import unittest
import json
from io import BytesIO
from unittest.mock import patch

from modules.charlie.private_executive import (
    build_executive_plan, compose_executive_reply, context_after_plan, run_executive_plan,
)


class CharliePrivateExecutiveTests(unittest.TestCase):
    def test_grounded_llm_synthesis_uses_evidence_and_falls_under_existing_policy(self):
        class Response:
            def __enter__(self): return self
            def __exit__(self, *_args): return False
            def read(self): return json.dumps({"choices": [{"message": {"content": "CORE is moving. No owner action is required."}}]}).encode()
        plan = build_executive_plan("What is CORE doing?", {"type": "read_core_status", "args": {}, "risk_flags": []}, {})
        evidence = [{"success": True, "intent_type": "read_core_status", "status": 200, "result": {"summary": "One mission is active."}}]
        reply = compose_executive_reply(plan, evidence, environ={"CHARLIE_PRIVATE_LLM_ENABLED": "true", "CHARLIE_PRIVATE_LLM_MODEL": "test-model", "OPENAI_API_KEY": "secret"}, http_open=lambda *_args, **_kwargs: Response())
        self.assertEqual(reply, "CORE is moving. No owner action is required.")

    def test_synthesis_receives_structured_agent_evidence_and_owner_context(self):
        captured = {}
        class Response:
            def __enter__(self): return self
            def __exit__(self, *_args): return False
            def read(self): return json.dumps({"choices": [{"message": {"content": "You have 6 pigs on the farm."}}]}).encode()
        def open_request(request, **_kwargs):
            captured.update(json.loads(request.data.decode("utf-8")))
            return Response()
        context = {"preferences": {"owner_instruction": "Be direct"}, "messages": [{"role": "owner", "content": "Keep answers practical"}]}
        plan = build_executive_plan("How many pigs do we have?", {"type": "read_farm_status", "args": {}, "risk_flags": []}, context)
        evidence = [{"success": True, "intent_type": "read_farm_status", "status": 200, "result": {
            "summary": "There are 6 pigs.", "direct_answer": "There are 6 pigs physically recorded on the farm.",
            "metrics": {"on_farm_total": 6}, "breakdown": {"by_type": {"piglets": 2}},
            "sources": [{"name": "pig_current_state"}], "freshness": {"mode": "live"}, "confidence": .99,
            "agent": {"agent_id": "herdmaster", "capability": "herd_inventory"},
        }}]
        reply = compose_executive_reply(plan, evidence, environ={"CHARLIE_PRIVATE_LLM_ENABLED": "1", "CHARLIE_PRIVATE_LLM_MODEL": "test", "OPENAI_API_KEY": "secret"}, http_open=open_request)
        user = json.loads(captured["messages"][1]["content"])
        self.assertEqual(reply, "You have 6 pigs on the farm.")
        self.assertEqual(user["owner_preferences"]["owner_instruction"], "Be direct")
        self.assertEqual(user["agent_evidence"][0]["structured_result"]["metrics"]["on_farm_total"], 6)
        self.assertEqual(user["agent_evidence"][0]["structured_result"]["agent"]["agent_id"], "herdmaster")

    def test_core_question_builds_bounded_multi_tool_plan(self):
        plan = build_executive_plan("What is happening with CORE?", {"type": "read_core_status", "args": {}, "risk_flags": []}, {})
        self.assertEqual([row["intent_type"] for row in plan["tools"]], ["read_core_status", "read_blocked"])
        self.assertLessEqual(len(plan["tools"]), 5)

    def test_verified_delegation_becomes_durable_commitment(self):
        plan = build_executive_plan("Fix Beacon", {"type": "create_mission", "args": {"title": "Fix Beacon"}, "risk_flags": []}, {})
        context = context_after_plan(plan, [{"success": True, "tool": "create_mission", "status": 200, "result": {"success": True, "mission_id": "M-123"}}])
        self.assertEqual(context["commitments"][0]["mission_id"], "M-123")
        self.assertEqual(context["commitments"][0]["status"], "monitoring")

    def test_later_read_preserves_existing_commitment(self):
        existing = {"type": "core_mission", "mission_id": "M-123", "status": "monitoring"}
        plan = build_executive_plan("What is CORE doing?", {"type": "read_core_status", "args": {}, "risk_flags": []}, {"open_context": {"commitments": [existing]}})
        context = context_after_plan(plan, [{"success": True, "tool": "core_status", "status": 200, "result": {"summary": "CORE is active"}}])
        self.assertEqual(context["commitments"], [existing])

    def test_deployed_migration_remains_an_unfinished_executive_commitment(self):
        plan = build_executive_plan("Check mission", {"type": "read_mission", "args": {"mission_id": "M-MIG"}, "risk_flags": []}, {})
        mission = {
            "mission_id": "M-MIG", "status": "deployed", "title": "Lifecycle rail",
            "metadata": {"review_packet": {
                "changed_files": ["supabase/migrations/202607210001.sql"],
                "test_evidence": ["pass"],
            }},
        }
        context = context_after_plan(plan, [{"success": True, "tool": "read_mission", "status": 200, "result": {"mission": mission}}])
        commitment = context["commitments"][0]
        self.assertEqual(commitment["status"], "delivered_unfinished")
        self.assertEqual(commitment["business_capability_status"], "not_operational")
        self.assertTrue(commitment["follow_up_mission_id"].startswith("CHARLIE-OUTCOME-"))

    @patch("modules.charlie.private_executive.execute_private_tool")
    def test_plan_uses_all_read_evidence_and_composes_direct_answer(self, execute):
        execute.side_effect = lambda intent_type, _args: {
            "read_core_status": ({"success": True, "summary": "CORE has one active mission.", "active_missions": [{"mission_id": "M-12345678", "title": "Build runtime"}]}, 200),
            "read_blocked": ({"success": True, "missions": [{"mission_id": "B-12345678", "title": "Fix test", "owner_required": False}]}, 200),
            "read_decisions": ({"success": True, "items": []}, 200),
        }[intent_type]
        plan = build_executive_plan("What is happening with CORE?", {"type": "read_core_status", "args": {}, "risk_flags": []}, {})
        evidence = run_executive_plan(plan, "INTENT-1")
        reply = compose_executive_reply(plan, evidence)
        self.assertIn("one active mission", reply)
        self.assertIn("1 is CORE-recoverable", reply)
        context = context_after_plan(plan, evidence)
        self.assertEqual(context["active_subject"]["mission_id"], "M-12345678")
        self.assertEqual(context["stage"], "verified")

    @patch("modules.charlie.private_executive.execute_private_tool", return_value=({"success": False, "summary": "authoritative read unavailable"}, 503))
    def test_failed_authoritative_read_is_not_reported_as_success(self, _execute):
        plan = build_executive_plan("status", {"type": "read_core_status", "args": {}, "risk_flags": []}, {})
        evidence = run_executive_plan(plan, "INTENT-1")
        self.assertEqual(len(evidence), 2)
        self.assertIn("unavailable", compose_executive_reply(plan, evidence))
        self.assertEqual(context_after_plan(plan, evidence)["stage"], "needs_follow_up")


if __name__ == "__main__":
    unittest.main()
