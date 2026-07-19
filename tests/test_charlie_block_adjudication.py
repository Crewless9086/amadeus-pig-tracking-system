import unittest

from modules.charlie.block_adjudication import adjudicate_block


def mission(reason, *, packet=None, governance=None):
    review = {"blocked_reason": reason, "blocked_agent": "tester", **(packet or {})}
    return {
        "mission_id": "M-1", "status": "blocked", "title": "Mission",
        "metadata": {"review_packet": review, "mission_governance": governance or {}},
    }


class CharlieBlockAdjudicationTests(unittest.TestCase):
    def test_recovery_wrapper_does_not_change_block_fingerprint(self):
        original = adjudicate_block(mission(
            "Builder concurrency admission refused before model execution: concurrent_source_overlap."
        ))
        repeated = adjudicate_block(mission(
            "Repeated internal recovery stopped after 5 identical occurrences: "
            "Builder concurrency admission refused before model execution: concurrent_source_overlap."
        ))
        self.assertEqual(original["fingerprint"], repeated["fingerprint"])

    def test_artifact_stage_mismatch_is_mechanical_recovery(self):
        result = adjudicate_block(mission("final_artifact_stage_mismatch at planner"))
        self.assertEqual(result["action"], "recover_stage")
        self.assertFalse(result["owner_required"])

    def test_exhausted_large_acceptance_matrix_decomposes(self):
        rows = [{"id": f"A-{index}", "requirement": f"Requirement {index}", "status": "pending"} for index in range(7)]
        result = adjudicate_block(mission("Frozen acceptance criteria remain failed after the bounded correction budget was exhausted.", governance={"acceptance_matrix": rows}))
        self.assertEqual(result["action"], "decompose_acceptance")
        self.assertEqual(len(result["pending_rows"]), 7)
        self.assertFalse(result["owner_required"])

    def test_explicit_business_choice_escalates(self):
        result = adjudicate_block(mission("Owner must decide the pricing business choice."))
        self.assertEqual(result["action"], "escalate_owner")
        self.assertTrue(result["owner_required"])

    def test_legacy_governance_owner_block_for_failed_work_is_recoverable(self):
        result = adjudicate_block(mission("QA review failed.", packet={
            "mission_governance_decision": {"route": "owner_block", "failed_acceptance_ids": ["A-1"]},
        }))
        self.assertEqual(result["action"], "recover_stage")
        self.assertFalse(result["owner_required"])

    def test_green_pr_supersedes_stale_legacy_conflict(self):
        blocked = mission("PR #240 was conflicting and requires revalidation", packet={
            "pr_url": "https://github.com/org/repo/pull/240", "errors": ["old conflict"],
        })
        state = {
            "success": True, "state": "OPEN", "mergeable": "MERGEABLE", "baseRefName": "main",
            "headRefOid": "abc", "statusCheckRollup": [{"conclusion": "SUCCESS"}],
        }
        result = adjudicate_block(blocked, pr_state=state)
        self.assertEqual(result["action"], "reconcile_pr_ready")

    def test_candidate_bound_active_block_is_not_overridden(self):
        blocked = mission("stale PR check", packet={
            "pr_url": "https://github.com/org/repo/pull/240",
            "evidence_reconciliation": {"version": "v1", "active_blockers": ["real regression"]},
        })
        state = {
            "success": True, "state": "OPEN", "mergeable": "MERGEABLE", "baseRefName": "main",
            "headRefOid": "abc", "statusCheckRollup": [{"conclusion": "SUCCESS"}],
        }
        result = adjudicate_block(blocked, pr_state=state)
        self.assertEqual(result["action"], "recover_stage")


if __name__ == "__main__":
    unittest.main()
