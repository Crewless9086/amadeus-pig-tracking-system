import unittest

from scripts import google_sheets_farm_import_reconcile as reconcile


class GoogleSheetsFarmImportReconcileTests(unittest.TestCase):
    def sample_verifier(self):
        return {
            "canonical_payload_summary": {
                "pigs": 1,
                "pens": 1,
                "pig_weight_events": 1,
            },
            "review_summary": {
                "by_type": {"conflicting_weight": 1},
                "by_status": {"pending_owner_review": 1},
                "total": 1,
            },
            "review_items": [
                {
                    "review_type": "conflicting_weight",
                    "status": "pending_owner_review",
                    "pig_id": "PIG-1",
                    "weight_date": "2026-06-22",
                    "candidate_weight_values": ["61.5", "70"],
                    "source_refs": [
                        {
                            "source_sheet_row": 2,
                            "sample": {
                                "Weight_Log_ID": "WGT-1",
                                "Pig_Name": "Pig One",
                                "Weight_Kg": "61.5",
                                "Pen_ID": "PEN-1",
                            },
                        },
                        {
                            "source_sheet_row": 3,
                            "sample": {
                                "Weight_Log_ID": "WGT-2",
                                "Pig_Name": "Pig One",
                                "Weight_Kg": "70",
                                "Pen_ID": "PEN-1",
                            },
                        },
                    ],
                },
                {
                    "review_type": "same_weight_duplicate",
                    "status": "auto_resolved_dedupe",
                    "pig_id": "PIG-2",
                    "weight_date": "2026-06-22",
                    "source_refs": [],
                },
            ],
        }

    def test_build_conflicting_weight_review_lists_owner_review_groups(self):
        groups = reconcile.build_conflicting_weight_review(self.sample_verifier())

        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["review_id"], "CW-001")
        self.assertEqual(groups[0]["status"], "pending_owner_review")
        self.assertEqual(groups[0]["pig_id"], "PIG-1")
        self.assertEqual(groups[0]["candidate_weight_values"], ["61.5", "70"])
        self.assertEqual(groups[0]["source_count"], 2)
        self.assertIn("choose_canonical_weight", groups[0]["decision_options"])
        self.assertEqual(
            groups[0]["current_import_effect"],
            "excluded_from_canonical_import_until_reviewed",
        )

    def test_compare_payloads_to_supabase_reports_match_and_mismatch(self):
        comparisons = reconcile.compare_payloads_to_supabase(
            {"pigs": 1, "pig_weight_events": 2},
            {"import_batch_counts": {"pigs": 1, "pig_weight_events": 1}},
        )

        self.assertEqual(comparisons["pigs"]["status"], "match")
        self.assertEqual(comparisons["pig_weight_events"]["status"], "mismatch")
        self.assertEqual(comparisons["pig_weight_events"]["delta"], -1)

    def test_summarize_reconciliation_blocks_route_cutover_until_review(self):
        report = reconcile.summarize_reconciliation(
            self.sample_verifier(),
            {"import_batch_counts": {"pigs": 1, "pens": 1, "pig_weight_events": 1}},
            [{"review_id": "CW-001", "status": "excluded"}],
        )

        self.assertTrue(report["table_counts_match_policy_payload"])
        self.assertTrue(report["conflicting_weight_groups_excluded"])
        self.assertFalse(report["route_cutover_ready"])
        self.assertIn("route-by-route", report["route_cutover_blocker"])

    def test_summarize_reconciliation_flags_imported_conflict_keys(self):
        report = reconcile.summarize_reconciliation(
            self.sample_verifier(),
            {"import_batch_counts": {"pigs": 1, "pens": 1, "pig_weight_events": 1}},
            [{"review_id": "CW-001", "status": "unexpected_imported_rows"}],
        )

        self.assertFalse(report["conflicting_weight_groups_excluded"])


if __name__ == "__main__":
    unittest.main()
