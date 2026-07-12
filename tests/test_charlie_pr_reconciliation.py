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


def pr(mergeable="MERGEABLE", state="OPEN", conclusion="SUCCESS"):
    return {
        "success": True,
        "state": state,
        "mergeable": mergeable,
        "headRefOid": "abc123",
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


if __name__ == "__main__":
    unittest.main()
