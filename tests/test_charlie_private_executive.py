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
