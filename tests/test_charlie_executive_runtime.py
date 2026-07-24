import os
import unittest
from unittest.mock import patch

from modules.charlie.executive_runtime import (
    _execute_decomposition, _execute_delegated_review, _execute_queue_selection, _load_executive_missions,
    _execute_recovery, _execute_outcome_follow_up, _execute_incident_repair, run_executive_cycle,
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
        self.assertEqual({item["status"] for item in result["missions"]}, {"in_progress", "blocked", "pr_ready", "release_approved", "approved", "new", "paused", "merged", "deployed", "done"})
        self.assertEqual(list_missions.call_count, 10)
        terminal_calls = [call for call in list_missions.call_args_list if call.kwargs.get("status") in {"merged", "deployed", "done"}]
        self.assertTrue(all(call.kwargs.get("compact") is True for call in terminal_calls))
        self.assertTrue(all(call.kwargs.get("outcome_candidates") is True for call in terminal_calls))
        active_calls = [call for call in list_missions.call_args_list if call.kwargs.get("status") not in {"merged", "deployed", "done"}]
        self.assertTrue(all(call.kwargs.get("compact") is False for call in active_calls))
        self.assertTrue(all(call.kwargs.get("outcome_candidates") is False for call in active_calls))

    @patch("modules.charlie.executive_runtime.complete_control_command", return_value=({"success": True}, 200))
    @patch("modules.charlie.executive_runtime.update_mission_vault", return_value=({"success": True}, 200))
    @patch("modules.charlie.executive_runtime.record_mission", return_value=({"status": "stored"}, 201))
    @patch("modules.charlie.executive_runtime.get_mission")
    def test_outcome_follow_up_is_created_new_and_parent_register_is_written(self, get_mission, record, update, _complete):
        get_mission.return_value = ({"mission": {
            "mission_id": "M-MIG", "status": "deployed", "title": "Lifecycle rail",
            "metadata": {"review_packet": {"changed_files": ["supabase/migrations/202607210001.sql"], "test_evidence": ["pass"]}},
        }}, 200)
        result = _execute_outcome_follow_up({"mission_id": "M-MIG"}, "CMD", None, None)
        self.assertEqual(result["status"], "outcome_follow_up_proposed")
        self.assertEqual(record.call_args.args[0]["status"], "new")
        self.assertIn("unfinished_business", update.call_args.args[1])

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

    @patch("modules.charlie.executive_runtime.queue_outbox")
    @patch("modules.charlie.executive_runtime.get_mission", return_value=({"mission": {"mission_id": "M-1", "status": "blocked", "metadata": {"review_packet": {"blocked_reason": "concurrent_source_overlap", "blocked_agent": "builder"}}}}, 200))
    @patch("modules.charlie.executive_runtime.transition_mission_review_state")
    @patch("modules.charlie.executive_runtime.complete_control_command")
    @patch("modules.charlie.executive_runtime.upsert_recovery_case", return_value=({"recovery_id": "REC-X", "attempt_count": 4, "attempt_limit": 3}, 200))
    def test_exhausted_system_incident_halts_without_reapproving(self, _case, complete, transition, _get, outbox):
        result = _execute_recovery({
            "mission_id": "M-1",
            "fingerprint": "stable-fp",
            "block_class": "system_repair_required",
        }, "CMD", None, None)
        self.assertEqual(result["status"], "system_incident_halted")
        transition.assert_not_called()
        self.assertEqual(complete.call_args.kwargs["result"]["status"], "system_incident_halted")
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

    @patch("modules.charlie.executive_runtime.complete_control_command", return_value=({"success": True}, 200))
    @patch("modules.charlie.executive_runtime.transition_mission_review_state", return_value=({"success": True}, 200))
    @patch("modules.charlie.executive_runtime.update_mission_vault", return_value=({"success": True}, 200))
    @patch("modules.charlie.executive_runtime.record_mission", return_value=({"stored": True}, 201))
    @patch("modules.charlie.executive_runtime.get_mission")
    def test_incident_halt_creates_one_canonical_unprotected_repair(self, get_mission, record, update, transition, _complete):
        get_mission.return_value = ({"mission": {
            "mission_id": "M-BREED", "status": "blocked", "title": "Breeding planner", "urgency": "P1",
            "metadata": {"review_packet": {
                "review_status": "system_incident_halted", "blocked_agent": "security_reviewer",
                "blocked_reason": "Repeated evidence recovery halted.",
                "active_blockers": [{"agent": "security_reviewer", "reason": "No implementation candidate."}],
            }},
        }}, 200)
        result = _execute_incident_repair({"mission_id": "M-BREED", "fingerprint": "stable"}, "CMD", None, None)
        self.assertEqual(result["status"], "incident_repair_created")
        child = record.call_args.args[0]
        self.assertEqual(child["status"], "approved")
        self.assertEqual(child["metadata"]["protected_operations"], [])
        self.assertEqual(child["metadata"]["mission_family"]["parent_mission_id"], "M-BREED")
        self.assertIn(child["mission_id"], update.call_args.args[1]["mission_coordinator"]["child_mission_ids"])
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
        self.assertTrue(outbox.call_args.kwargs["idempotency_key"].endswith(":initial"))

    @patch("modules.charlie.executive_runtime.load_executive_context", return_value=({"policies": [], "goals": []}, 200))
    @patch("modules.charlie.executive_runtime.list_missions", return_value=({"missions": [{**BLOCKED, "metadata": {"review_packet": {"block_disposition": {"block_class": "owner_decision_required", "owner_required": True}}}}]}, 200))
    @patch("modules.charlie.executive_runtime.queue_outbox")
    def test_observe_mode_does_not_emit_owner_notification(self, outbox, _missions, _context):
        with patch.dict(os.environ, {"CHARLIE_EXECUTIVE_MODE": "observe"}):
            run_executive_cycle(runner={"active_mission_id": "ACTIVE"})
        outbox.assert_not_called()

    @patch("modules.charlie.executive_runtime.update_mission_vault", return_value=({"success": True}, 200))
    @patch("modules.charlie.executive_runtime.queue_outbox", return_value=({"success": True, "outbox_id": "OUT-1"}, 201))
    @patch("modules.charlie.executive_runtime.load_executive_context", return_value=({"policies": [POLICY], "goals": [], "trust": []}, 200))
    @patch("modules.charlie.executive_runtime.list_missions")
    def test_outcome_notification_queue_is_recorded_durably(self, list_missions, _context, outbox, update):
        mission = {
            "mission_id": "M-MIG", "status": "deployed", "title": "Lifecycle rail",
            "metadata": {
                "review_packet": {"changed_files": ["supabase/migrations/202607210001.sql"], "test_evidence": ["pass"]},
                "unfinished_business": {"status": "follow_up_proposed"},
            },
        }
        from modules.charlie.outcome_closure import operational_outcome_closure
        mission["metadata"]["unfinished_business"]["follow_up_mission_id"] = operational_outcome_closure(mission)["follow_up_mission_id"]
        list_missions.side_effect = lambda status="", **_kwargs: ({"missions": [mission] if status == "deployed" else []}, 200)
        with patch.dict(os.environ, {"CHARLIE_EXECUTIVE_MODE": "active"}):
            result, status = run_executive_cycle(runner={"active_mission_id": "ACTIVE"})
        self.assertEqual(status, 200)
        outbox.assert_called_once()
        unfinished = update.call_args.args[1]["unfinished_business"]
        self.assertEqual(unfinished["notification_status"], "queued")
        self.assertEqual(unfinished["notification_outbox_id"], "OUT-1")

    @patch("modules.charlie.executive_runtime.complete_control_command", return_value=({"success": True}, 200))
    @patch("modules.charlie.executive_runtime.update_mission_vault", return_value=({"success": True}, 200))
    @patch("modules.charlie.executive_runtime.get_mission")
    def test_family_reconciliation_resumes_parent_at_evidence_reviewer(self, get_mission, update, _complete):
        get_mission.side_effect = [
            ({"mission": {
                "mission_id": "PARENT",
                "status": "paused",
                "agent_workflow": [
                    {"agent": "planner", "status": "complete", "completed_at": "2026-07-01T00:00:00Z"},
                    {"agent": "builder", "status": "complete", "completed_at": "2026-07-01T00:01:00Z"},
                    {"agent": "evidence_reviewer", "status": "complete", "completed_at": "2026-07-01T00:02:00Z"},
                    {"agent": "reviewer", "status": "complete", "completed_at": "2026-07-01T00:03:00Z"},
                ],
                "metadata": {
                    "review_packet": {},
                    "mission_coordinator": {"status": "waiting_children", "child_mission_ids": ["CHILD"]},
                },
            }}, 200),
            ({"mission": {"mission_id": "CHILD", "status": "done"}}, 200),
        ]
        from modules.charlie.executive_runtime import _execute_family_reconciliation
        result = _execute_family_reconciliation(
            {"mission_id": "PARENT", "child_states": {"CHILD": "done"}}, "CMD", None, None,
        )
        self.assertEqual(result["status"], "family_reconciled")
        self.assertEqual(update.call_args.kwargs["status"], "approved")
        payload = update.call_args.args[1]
        self.assertEqual(payload["review_packet"]["return_to_stage"], "evidence_reviewer")
        self.assertEqual(payload["mission_coordinator"]["status"], "reconciling_children")
        self.assertEqual(payload["targeted_invalidation"]["target_agent"], "evidence_reviewer")
        self.assertEqual(
            [(item["agent"], item["status"]) for item in payload["agent_workflow"]],
            [
                ("planner", "complete"),
                ("builder", "complete"),
                ("evidence_reviewer", "active"),
                ("reviewer", "pending"),
            ],
        )

    @patch("modules.charlie.executive_runtime.complete_control_command", return_value=({"success": True}, 200))
    @patch("modules.charlie.executive_runtime.update_mission_vault", return_value=({"success": True}, 200))
    @patch("modules.charlie.executive_runtime.get_mission")
    def test_family_reconciliation_uses_minimal_closure_when_parent_has_no_completed_stages(
        self, get_mission, update, _complete,
    ):
        get_mission.side_effect = [
            ({"mission": {
                "mission_id": "PARENT",
                "status": "paused",
                "agent_workflow": [
                    {"agent": "idea_expander", "status": "pending", "completed_at": None},
                    {"agent": "evidence_reviewer", "status": "pending", "completed_at": None},
                    {"agent": "reviewer", "status": "pending", "completed_at": None},
                    {"agent": "publisher", "status": "pending", "completed_at": None},
                ],
                "metadata": {
                    "review_packet": {},
                    "mission_coordinator": {"status": "waiting_children", "child_mission_ids": ["CHILD"]},
                },
            }}, 200),
            ({"mission": {"mission_id": "CHILD", "status": "deployed"}}, 200),
        ]
        from modules.charlie.executive_runtime import _execute_family_reconciliation
        result = _execute_family_reconciliation(
            {"mission_id": "PARENT", "child_states": {"CHILD": "deployed"}}, "CMD", None, None,
        )
        self.assertEqual(result["status"], "family_reconciled")
        payload = update.call_args.args[1]
        self.assertTrue(payload["targeted_invalidation"]["coordinator_reconciliation"])
        self.assertEqual(
            [(item["agent"], item["status"]) for item in payload["agent_workflow"]],
            [
                ("evidence_reviewer", "active"),
                ("reviewer", "pending"),
                ("publisher", "pending"),
            ],
        )


if __name__ == "__main__":
    unittest.main()
