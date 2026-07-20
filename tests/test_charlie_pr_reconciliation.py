import unittest

from modules.charlie.pr_reconciliation import reconciliation_decision


def mission(ui=False, visual=False):
    return {
        "status": "blocked",
        "metadata": {
            "charlie_core": {"project_truth": {"workflow_template": "ui_product_build" if ui else "software_build"}},
            "review_packet": {"visual_review": {"status": "captured" if visual else "not_captured_blocked", "media": ["shot.png"] if visual else []}},
        },
    }


def reconciled_mission(*, active_blockers=None, requires_revalidation=None, candidate_revision="abc123"):
    value = mission()
    value["status"] = "pr_ready"
    value["metadata"]["review_packet"].update({
        "tested_revision": "abc123",
        "recommended_owner_decision": "approve_final_release",
        "errors": ["Historical pre-build concern that a later candidate resolved."],
        "bugs": ["Historical implementation finding retained for audit."],
        "evidence_reconciliation": {
            "version": "charlie_evidence_reconciliation_v1",
            "candidate_manifest": {"source_commit": candidate_revision},
            "active_blockers": active_blockers or [],
            "requires_revalidation": requires_revalidation or [],
            "resolved_findings": [{"state": "resolved", "finding": "Historical concern"}],
        },
    })
    return value


def pr(mergeable="MERGEABLE", state="OPEN", conclusion="SUCCESS"):
    return {
        "success": True,
        "state": state,
        "mergeable": mergeable,
        "headRefOid": "abc123",
        "baseRefName": "main",
        "statusCheckRollup": [{"conclusion": conclusion}],
    }


class CharliePrReconciliationTests(unittest.TestCase):
    def test_green_non_ui_pr_becomes_owner_review_ready(self):
        result = reconciliation_decision(mission(), pr())
        self.assertEqual(result["action"], "mark_pr_ready")

    def test_green_ui_pr_without_media_routes_visual_recovery(self):
        result = reconciliation_decision(mission(ui=True), pr())
        self.assertEqual(result["action"], "queue_recovery")
        self.assertEqual(result["disposition"]["responsible_stage"], "visual_qa_reviewer")

    def test_conflict_routes_branch_repair(self):
        result = reconciliation_decision(mission(), pr(mergeable="CONFLICTING"))
        self.assertEqual(result["disposition"]["block_class"], "branch_repair_required")
        self.assertEqual(result["target_status"], "approved")

    def test_failed_checks_route_implementation_fix(self):
        result = reconciliation_decision(mission(), pr(conclusion="FAILURE"))
        self.assertEqual(result["disposition"]["responsible_stage"], "builder")

    def test_merged_pr_reconciles_terminal_state(self):
        result = reconciliation_decision(mission(), pr(state="MERGED"))
        self.assertEqual(result["target_status"], "merged")

    def test_wrong_base_routes_internal_branch_repair(self):
        state = pr()
        state["baseRefName"] = "feature/other-mission"
        result = reconciliation_decision(mission(), state)
        self.assertEqual(result["reason"], "github_pr_wrong_release_base")
        self.assertEqual(result["disposition"]["block_class"], "branch_repair_required")

    def test_incomplete_dependency_cannot_become_review_ready(self):
        value = mission()
        value["metadata"]["depends_on_mission_ids"] = ["PARENT-1"]
        result = reconciliation_decision(value, pr(), {"PARENT-1": "pr_ready"})
        self.assertEqual(result["action"], "wait_dependencies")
        self.assertEqual(result["target_status"], "approved")

    def test_current_candidate_pass_ignores_historical_prebuild_findings(self):
        result = reconciliation_decision(reconciled_mission(), pr())

        self.assertEqual(result["action"], "none")
        self.assertEqual(result["reason"], "pr_ready_is_sticky")

    def test_current_candidate_active_blocker_still_queues_recovery(self):
        value = reconciled_mission(active_blockers=[{"agent": "risk_agent", "reason": "current risk"}])

        result = reconciliation_decision(value, pr())

        self.assertEqual(result["action"], "none")
        self.assertEqual(result["reason"], "pr_ready_is_sticky")

    def test_changed_pr_head_requires_candidate_revalidation(self):
        value = reconciled_mission(candidate_revision="old-head")

        result = reconciliation_decision(value, pr())

        self.assertEqual(result["action"], "none")
        self.assertEqual(result["reason"], "pr_ready_is_sticky")

    def test_candidate_refresh_requirement_still_queues_recovery(self):
        value = reconciled_mission(requires_revalidation=[{"agent": "tester", "reason": "different_revision"}])

        result = reconciliation_decision(value, pr())

        self.assertEqual(result["action"], "none")
        self.assertEqual(result["reason"], "pr_ready_is_sticky")

    def test_workflow_block_recovery_preserves_exact_target_stage(self):
        value = reconciled_mission(requires_revalidation=[{
            "agent": "source_mapper",
            "reason": "legacy_unbound_evidence_requires_revalidation",
        }])
        value["status"] = "blocked"
        value["metadata"]["review_packet"].update({
            "review_status": "workflow_not_ready",
            "blocked_agent": "source_mapper",
            "blocked_reason": "Owner review needs a targeted source_mapper recheck.",
        })

        result = reconciliation_decision(value, pr())

        self.assertEqual(result["reason"], "owner_review_targeted_recheck")
        self.assertEqual(result["disposition"]["responsible_stage"], "source_mapper")

    def test_legacy_explicit_findings_remain_strict(self):
        value = mission()
        value["metadata"]["review_packet"]["bugs"] = ["Still unresolved"]

        result = reconciliation_decision(value, pr())

        self.assertEqual(result["action"], "queue_recovery")
        self.assertIn("unresolved_review_findings", result["readiness"]["reasons"])

    def test_system_incident_halt_cannot_be_restarted_by_pr_reconciliation(self):
        value = reconciled_mission()
        value["status"] = "blocked"
        value["metadata"]["review_packet"].update({
            "review_status": "system_incident_halted",
            "blocked_agent": "idea_expander",
        })

        result = reconciliation_decision(value, pr())

        self.assertEqual(result["action"], "none")
        self.assertEqual(result["reason"], "system_incident_halted")


if __name__ == "__main__":
    unittest.main()
