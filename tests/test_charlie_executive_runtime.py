import os
import unittest
from unittest.mock import patch

from modules.charlie.executive_runtime import (
    _execute_decomposition, _execute_delegated_review, _execute_queue_selection, _load_executive_missions,
    _execute_recovery, run_executive_cycle,
)


BLOCKED = {
    "mission_id": "MISSION-1", "status": "blocked", "urgency": "P1",
    "metadata": {"review_packet": {"blocked_reason": "test failure", "block_disposition": {
        "block_class": "implementation_fix_required", "owner_required": False,
        "responsible_stage": "builder", "reason": "test failure",
    }}},
}
POLICY = {"policy_id": "POLICY-1", "capability": "core.internal_recovery", "authority_tier": "auto", "enabled": True}


class CharlieExecutiveRuntimeTests(unittest.TestCase):
    @patch("modules.charlie.executive_runtime.list_missions")
    def test_executive_loads_each_actionable_bucket_so_reviews_are_not_hidden(self, list_missions):
        def bucket(*, status, **_kwargs):
            return ({"missions": [{"mission_id": f"M-{status}", "status": status}]}, 200)
        list_missions.side_effect = bucket
        result, status = _load_executive_missions()
        self.assertEqual(status, 200)
        self.assertEqual({item["status"] for item in result["missions"]}, {"in_progress", "blocked", "pr_ready", "release_approved", "approved", "new", "paused"})
        self.assertEqual(list_missions.call_count, 7)

    @patch("modules.charlie.executive_runtime.complete_control_command", return_value=({"success": True}, 200))
    @patch("modules.charlie.executive_runtime.transition_mission_review_state", return_value=({"success": True}, 200))
    @patch("modules.charlie.executive_runtime.query_pr_state")
    @patch("modules.charlie.executive_runtime.get_mission")
    def test_delegated_review_rechecks_pr_and_uses_compare_and_set(self, get_mission, query, transition, _complete):
        get_mission.return_value = ({"mission": {
            "mission_id": "M-READY", "status": "pr_ready", "title": "Docs", "raw_text": "Docs", "approval_level": "LEVEL 3",
            "metadata": {"review_packet": {"review_status": "ready_for_owner_review", "changed_files": ["docs/a.md"], "test_evidence": ["pass"], "pr_url": "https://github.com/o/r/pull/1", "tested_revision": "abc"}},
        }}, 200)
        query.return_value = {"success": True, "state": "OPEN", "mergeable": "MERGEABLE", "baseRefName": "main", "headRefOid": "abc", "statusCheckRollup": [{"conclusion": "SUCCESS"}]}
        result = _execute_delegated_review({"mission_id": "M-READY", "policy_id": "P", "authority_tier": "auto"}, "CMD", None, None)
        self.assertEqual(result["status"], "delegated_review_approved")
        self.assertEqual(transition.call_args.args[1], "release_approved")
        self.assertEqual(transition.call_args.kwargs["expected_status"], "pr_ready")

    @patch("modules.charlie.executive_runtime.complete_control_command", return_value=({"success": True}, 200))
    @patch("modules.charlie.executive_runtime.transition_mission_review_state", return_value=({"success": True}, 200))
    @patch("modules.charlie.executive_runtime.query_pr_state")
    @patch("modules.charlie.executive_runtime.get_mission")
    def test_delegated_review_reloads_live_dependency_state(self, get_mission, query, transition, _complete):
        mission = {
            "mission_id": "M-READY", "status": "pr_ready", "title": "Docs", "raw_text": "Docs",
            "approval_level": "LEVEL 3", "metadata": {
                "depends_on_mission_ids": ["M-DEPENDENCY"],
                "review_packet": {
                    "review_status": "ready_for_owner_review", "changed_files": ["docs/a.md"],
                    "test_evidence": ["pass"], "pr_url": "https://github.com/o/r/pull/1",
                    "tested_revision": "abc",
                },
            },
        }
        get_mission.side_effect = [
            ({"mission": mission}, 200),
            ({"mission": {"mission_id": "M-DEPENDENCY", "status": "deployed"}}, 200),
        ]
        query.return_value = {
            "success": True, "state": "OPEN", "mergeable": "MERGEABLE", "baseRefName": "main",
            "headRefOid": "abc", "statusCheckRollup": [{"conclusion": "SUCCESS"}],
        }
        result = _execute_delegated_review(
            {"mission_id": "M-READY", "policy_id": "P", "authority_tier": "auto"},
            "CMD", None, None,
        )
        self.assertEqual(result["status"], "delegated_review_approved")
        self.assertEqual(get_mission.call_args_list[1].args[0], "M-DEPENDENCY")
        self.assertEqual(transition.call_args.args[1], "release_approved")

    @patch("modules.charlie.executive_runtime.complete_control_command", return_value=({"success": True}, 200))
    @patch("modules.charlie.executive_runtime.update_mission_status", return_value=({"success": True}, 200))
    @patch("modules.charlie.executive_runtime.get_mission")
    def test_queue_selection_reloads_and_claims_only_new(self, get_mission, update, _complete):
        get_mission.return_value = ({"mission": {"mission_id": "M-NEW", "status": "new", "title": "Docs", "raw_text": "Improve docs", "approval_level": "LEVEL 3", "metadata": {}}}, 200)
        result = _execute_queue_selection({"mission_id": "M-NEW", "policy_id": "P", "priority_score": 90}, "CMD", None, None)
        self.assertEqual(result["status"], "queue_selected")
        self.assertEqual(update.call_args.kwargs["expected_status"], "new")

    @patch("modules.charlie.executive_runtime.queue_outbox")
    @patch("modules.charlie.executive_runtime.get_mission", return_value=({"mission": BLOCKED}, 200))
    @patch("modules.charlie.executive_runtime.transition_mission_review_state", return_value=({"success": True}, 200))
    @patch("modules.charlie.executive_runtime.complete_control_command", return_value=({"success": True}, 200))
    @patch("modules.charlie.executive_runtime.upsert_recovery_case", return_value=({"recovery_id": "REC-X", "attempt_count": 4, "attempt_limit": 3}, 200))
    def test_exhausted_mechanical_recovery_changes_strategy_without_owner(self, _case, _complete, transition, _get, outbox):
        result = _execute_recovery({"mission_id": "M-1", "fingerprint": "fp"}, "CMD", None, None)
        self.assertEqual(result["status"], "alternate_recovery_queued")
        self.assertEqual(transition.call_args.args[2]["executive_recovery"]["strategy"], "alternate_planning")
        outbox.assert_not_called()

    @patch("modules.charlie.executive_runtime.complete_control_command", return_value=({"success": True}, 200))
    @patch("modules.charlie.executive_runtime.transition_mission_review_state", return_value=({"success": True}, 200))
    @patch("modules.charlie.executive_runtime.upsert_recovery_case", return_value=({"recovery_id": "REC-1", "attempt_count": 1, "attempt_limit": 3}, 200))
    @patch("modules.charlie.executive_runtime.get_mission", return_value=({"mission": BLOCKED}, 200))
    @patch("modules.charlie.executive_runtime.record_control_command", return_value=({"created": False, "existing": True, "command_id": "CMD-OLD"}, 200))
    @patch("modules.charlie.executive_runtime.load_executive_context", return_value=({"policies": [POLICY], "goals": []}, 200))
    @patch("modules.charlie.executive_runtime.list_missions", return_value=({"missions": [BLOCKED]}, 200))
    def test_unresolved_duplicate_command_is_reexecuted(self, _missions, _context, _record, _get, _case, transition, _complete):
        with patch.dict(os.environ, {"CHARLIE_EXECUTIVE_MODE": "active"}):
            result, status = run_executive_cycle(runner={"active_mission_id": "ACTIVE"})
        self.assertEqual(status, 200)
        self.assertEqual(result["results"][0]["status"], "recovery_queued")
        transition.assert_called_once()

    @patch("modules.charlie.executive_runtime.get_mission", return_value=({"mission": {**BLOCKED, "status": "approved"}}, 200))
    @patch("modules.charlie.executive_runtime.record_control_command", return_value=({"created": False, "existing": True, "command_id": "CMD-OLD"}, 200))
    @patch("modules.charlie.executive_runtime.load_executive_context", return_value=({"policies": [POLICY], "goals": []}, 200))
    @patch("modules.charlie.executive_runtime.list_missions", return_value=({"missions": [BLOCKED]}, 200))
    def test_duplicate_with_desired_outcome_is_confirmed(self, _missions, _context, _record, _get):
        with patch.dict(os.environ, {"CHARLIE_EXECUTIVE_MODE": "active"}), patch("modules.charlie.executive_runtime.transition_mission_review_state") as transition:
            result, status = run_executive_cycle(runner={"active_mission_id": "ACTIVE"})
        self.assertEqual(status, 200)
        self.assertEqual(result["results"][0]["status"], "duplicate_outcome_confirmed")
        transition.assert_not_called()

    @patch("modules.charlie.executive_runtime.complete_control_command", return_value=({"success": True}, 200))
    @patch("modules.charlie.executive_runtime.transition_mission_review_state", return_value=({"success": True}, 200))
    @patch("modules.charlie.executive_runtime.record_mission", return_value=({"stored": True}, 201))
    @patch("modules.charlie.executive_runtime.get_mission")
    def test_decomposition_creates_bounded_children_and_pauses_parent(self, get_mission, record, transition, _complete):
        rows = [{"id": f"A-{index}", "requirement": f"Requirement {index}", "status": "pending"} for index in range(7)]
        get_mission.return_value = ({"mission": {
            "mission_id": "M-PARENT", "status": "blocked", "title": "Large mission", "urgency": "P1",
            "metadata": {
                "mission_governance": {"acceptance_matrix": rows},
                "review_packet": {"blocked_reason": "Frozen acceptance criteria remain failed after the bounded correction budget was exhausted.", "blocked_agent": "tester"},
            },
        }}, 200)
        result = _execute_decomposition({"mission_id": "M-PARENT"}, "CMD", None, None)
        self.assertEqual(result["status"], "decomposed")
        self.assertEqual(record.call_count, 4)
        self.assertTrue(all(len(call.args[0]["metadata"]["mission_governance"]["acceptance_matrix"]) <= 2 for call in record.call_args_list))
        self.assertEqual(transition.call_args.args[1], "paused")
        self.assertEqual(transition.call_args.kwargs["expected_status"], "blocked")

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

    @patch("modules.charlie.executive_runtime.complete_control_command", return_value=({"success": True}, 200))
    @patch("modules.charlie.executive_runtime.transition_mission_review_state", return_value=({"success": True}, 200))
    @patch("modules.charlie.executive_runtime.get_mission")
    def test_family_reconciliation_resumes_parent_at_evidence_reviewer(self, get_mission, transition, _complete):
        get_mission.side_effect = [
            ({"mission": {"mission_id": "PARENT", "status": "paused", "metadata": {"review_packet": {}}}}, 200),
            ({"mission": {"mission_id": "CHILD", "status": "done"}}, 200),
        ]
        from modules.charlie.executive_runtime import _execute_family_reconciliation
        result = _execute_family_reconciliation(
            {"mission_id": "PARENT", "child_states": {"CHILD": "done"}}, "CMD", None, None,
        )
        self.assertEqual(result["status"], "family_reconciled")
        self.assertEqual(transition.call_args.args[1], "approved")
        self.assertEqual(transition.call_args.args[2]["return_to_stage"], "evidence_reviewer")


if __name__ == "__main__":
    unittest.main()
