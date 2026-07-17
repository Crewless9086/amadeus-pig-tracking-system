import os
import unittest
from unittest.mock import patch

from modules.charlie.executive_runtime import run_executive_cycle


BLOCKED = {
    "mission_id": "MISSION-1", "status": "blocked", "urgency": "P1",
    "metadata": {"review_packet": {"blocked_reason": "test failure", "block_disposition": {
        "block_class": "implementation_fix_required", "owner_required": False,
        "responsible_stage": "builder", "reason": "test failure",
    }}},
}
POLICY = {"policy_id": "POLICY-1", "capability": "core.internal_recovery", "authority_tier": "auto", "enabled": True}


class CharlieExecutiveRuntimeTests(unittest.TestCase):
    @patch("modules.charlie.executive_runtime.load_executive_context", return_value=({"policies": [POLICY], "goals": []}, 200))
    @patch("modules.charlie.executive_runtime.list_missions", return_value=({"missions": [BLOCKED]}, 200))
    @patch("modules.charlie.executive_runtime.record_control_command", return_value=({"created": True, "command_id": "CMD-1"}, 201))
    def test_observe_mode_records_but_does_not_mutate_mission(self, _record, _missions, _context):
        with patch.dict(os.environ, {"CHARLIE_EXECUTIVE_MODE": "observe"}):
            with patch("modules.charlie.executive_runtime.transition_mission_review_state") as transition, patch("modules.charlie.executive_runtime.complete_control_command") as complete:
                result, status = run_executive_cycle(runner={"active_mission_id": ""})
        self.assertEqual(status, 200)
        self.assertEqual(result["results"][0]["status"], "observed")
        transition.assert_not_called()
        complete.assert_called()

    @patch("modules.charlie.executive_runtime.complete_control_command", return_value=({"success": True}, 200))
    @patch("modules.charlie.executive_runtime.get_mission", return_value=({"mission": BLOCKED}, 200))
    @patch("modules.charlie.executive_runtime.upsert_recovery_case", return_value=({"recovery_id": "REC-1", "attempt_count": 1, "attempt_limit": 3}, 200))
    @patch("modules.charlie.executive_runtime.transition_mission_review_state", return_value=({"success": True}, 200))
    @patch("modules.charlie.executive_runtime.record_control_command", return_value=({"created": True, "command_id": "CMD-1"}, 201))
    @patch("modules.charlie.executive_runtime.load_executive_context", return_value=({"policies": [POLICY], "goals": []}, 200))
    @patch("modules.charlie.executive_runtime.list_missions", return_value=({"missions": [BLOCKED]}, 200))
    def test_active_mode_queues_recoverable_block(self, _missions, _context, _record, transition, _case, _get, _complete):
        with patch.dict(os.environ, {"CHARLIE_EXECUTIVE_MODE": "active"}):
            result, status = run_executive_cycle(runner={"active_mission_id": "ACTIVE"})
        self.assertEqual(status, 200)
        self.assertEqual(result["results"][0]["status"], "recovery_queued")
        self.assertEqual(transition.call_args.args[1], "approved")
        self.assertEqual(transition.call_args.kwargs["expected_status"], "blocked")

    @patch("modules.charlie.executive_runtime.complete_control_command", return_value=({"success": True}, 200))
    @patch("modules.charlie.executive_runtime.get_mission", return_value=({"mission": {**BLOCKED, "metadata": {"review_packet": {"agent_artifacts": {"builder": {"status": "valid"}}, "block_disposition": BLOCKED["metadata"]["review_packet"]["block_disposition"]}}}}, 200))
    @patch("modules.charlie.executive_runtime.upsert_recovery_case", return_value=({"recovery_id": "REC-1", "attempt_count": 1, "attempt_limit": 3}, 200))
    @patch("modules.charlie.executive_runtime.transition_mission_review_state", return_value=({"success": True}, 200))
    @patch("modules.charlie.executive_runtime.record_control_command", return_value=({"created": True, "command_id": "CMD-1"}, 201))
    @patch("modules.charlie.executive_runtime.load_executive_context", return_value=({"policies": [POLICY], "goals": []}, 200))
    @patch("modules.charlie.executive_runtime.list_missions", return_value=({"missions": [BLOCKED]}, 200))
    def test_recovery_preserves_existing_evidence(self, _missions, _context, _record, transition, _case, _get, _complete):
        with patch.dict(os.environ, {"CHARLIE_EXECUTIVE_MODE": "active"}):
            run_executive_cycle(runner={"active_mission_id": "ACTIVE"})
        packet = transition.call_args.args[2]
        self.assertEqual(packet["agent_artifacts"]["builder"]["status"], "valid")

    @patch("modules.charlie.executive_runtime.load_executive_context", return_value=({"policies": [], "goals": []}, 200))
    @patch("modules.charlie.executive_runtime.list_missions", return_value=({"missions": [{**BLOCKED, "metadata": {"review_packet": {"block_disposition": {"block_class": "owner_decision_required", "owner_required": True}}}}]}, 200))
    @patch("modules.charlie.executive_runtime.queue_outbox", return_value=({"success": True}, 201))
    def test_genuine_owner_decision_uses_durable_outbox(self, outbox, _missions, _context):
        with patch.dict(os.environ, {"CHARLIE_EXECUTIVE_MODE": "active"}):
            result, status = run_executive_cycle(runner={"active_mission_id": "ACTIVE"})
        self.assertEqual(status, 200)
        self.assertEqual(len(result["cycle"]["escalations"]), 1)
        outbox.assert_called_once()

    @patch("modules.charlie.executive_runtime.load_executive_context", return_value=({"policies": [], "goals": []}, 200))
    @patch("modules.charlie.executive_runtime.list_missions", return_value=({"missions": [{**BLOCKED, "metadata": {"review_packet": {"block_disposition": {"block_class": "owner_decision_required", "owner_required": True}}}}]}, 200))
    @patch("modules.charlie.executive_runtime.queue_outbox")
    def test_observe_mode_does_not_emit_owner_notification(self, outbox, _missions, _context):
        with patch.dict(os.environ, {"CHARLIE_EXECUTIVE_MODE": "observe"}):
            run_executive_cycle(runner={"active_mission_id": "ACTIVE"})
        outbox.assert_not_called()


if __name__ == "__main__":
    unittest.main()
