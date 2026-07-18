import unittest

from modules.charlie.block_recovery import classify_block, normalize_findings


class CharlieBlockRecoveryTests(unittest.TestCase):
    def test_merge_conflict_routes_to_internal_branch_repair(self):
        result = classify_block("publisher", "Pull request has merge conflicts.")
        self.assertEqual(result["block_class"], "branch_repair_required")
        self.assertTrue(result["recoverable"])
        self.assertFalse(result["owner_required"])

    def test_browser_failure_routes_to_visual_retry(self):
        result = classify_block("tester", "Browser runtime unavailable; could not capture screenshot.")
        self.assertEqual(result["block_class"], "environment_retry_required")
        self.assertEqual(result["responsible_stage"], "visual_qa_reviewer")

    def test_unrelated_existing_finding_does_not_become_product_block(self):
        result = classify_block(
            "tester",
            "Existing SAM stress finding is outside changed surface and not introduced by this PR.",
        )
        self.assertEqual(result["block_class"], "system_repair_required")
        self.assertEqual(result["scope_relation"], "unrelated")
        self.assertFalse(result["introduced_by_current_diff"])

    def test_current_diff_regression_routes_to_builder(self):
        result = classify_block(
            "qa_red_team",
            "Regression introduced by this diff: owner mutation route bypasses access gate.",
            {"risk_rating": "high"},
        )
        self.assertEqual(result["block_class"], "implementation_fix_required")
        self.assertEqual(result["responsible_stage"], "builder")
        self.assertTrue(result["recoverable"])

    def test_red_zone_owner_decision_remains_hard_stop(self):
        result = classify_block(
            "risk_agent",
            "Customer send requires owner approval; red zone is not approved.",
        )
        self.assertEqual(result["block_class"], "red_zone_owner_approval_required")
        self.assertTrue(result["owner_required"])

    def test_exhausted_recovery_loop_changes_strategy_without_owner_work(self):
        result = classify_block("builder", "Repeated same blocker loop detected; durable loop cap exhausted.")
        self.assertEqual(result["block_class"], "implementation_fix_required")
        self.assertTrue(result["recoverable"])

    def test_builder_authorization_refusal_routes_to_architect(self):
        result = classify_block(
            "builder",
            "Builder authorization is disabled pending Architect resolution; builder_allowed=false.",
        )
        self.assertEqual(result["block_class"], "system_repair_required")
        self.assertEqual(result["responsible_stage"], "architect")
        self.assertTrue(result["recoverable"])

    def test_merge_conflict_never_consumes_correction_budget_into_owner_block(self):
        result = classify_block(
            "publisher",
            "Pull request has merge conflicts after bounded correction budget was exhausted.",
        )
        self.assertEqual(result["block_class"], "branch_repair_required")
        self.assertFalse(result["owner_required"])

    def test_exhausted_frozen_matrix_is_still_internal_work(self):
        result = classify_block(
            "qa_red_team",
            "Frozen acceptance criteria remain failed after the bounded correction budget was exhausted.",
        )
        self.assertEqual(result["block_class"], "implementation_fix_required")
        self.assertEqual(result["responsible_stage"], "builder")
        self.assertTrue(result["recoverable"])

    def test_governance_owner_block_cannot_be_reclassified_as_recoverable(self):
        result = classify_block(
            "qa_red_team",
            "QA review failed.",
            {
                "mission_governance_decision": {
                    "route": "owner_block",
                    "failed_acceptance_ids": ["acceptance-storage"],
                },
            },
        )
        self.assertEqual(result["block_class"], "owner_decision_required")
        self.assertFalse(result["recoverable"])

    def test_unimplemented_verifier_result_returns_to_builder_not_verifier(self):
        result = classify_block(
            "qa_red_team",
            "The scoped diff is empty; there is no implementation for owner review.",
        )
        self.assertEqual(result["block_class"], "implementation_fix_required")
        self.assertEqual(result["responsible_stage"], "builder")
        self.assertTrue(result["recoverable"])

    def test_unapproved_additive_migration_requires_owner(self):
        result = classify_block(
            "builder",
            "The additive migration is not explicitly owner-authorized.",
        )
        self.assertEqual(result["block_class"], "red_zone_owner_approval_required")
        self.assertFalse(result["recoverable"])

    def test_normalized_findings_include_scope_and_responsible_stage(self):
        findings = normalize_findings(
            [{"finding": "Pre-existing warning outside changed surface.", "severity": "low"}],
            agent="tester",
        )
        self.assertEqual(findings[0]["scope_relation"], "pre_existing")
        self.assertFalse(findings[0]["blocking"])
        self.assertIn("responsible_stage", findings[0])


if __name__ == "__main__":
    unittest.main()
