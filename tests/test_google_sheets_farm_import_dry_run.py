import unittest
from unittest.mock import patch

from scripts import google_sheets_farm_import_dry_run as dry_run


class GoogleSheetsFarmImportDryRunTests(unittest.TestCase):
    def sample_rows(self):
        return {
            "PEN_REGISTER": [
                {"Pen_ID": "PEN-1", "Pen_Name": "Growers", "Capacity": "20", "Is_Active": "Yes"},
                {"Pen_ID": "PEN-2", "Pen_Name": "Finishers", "Capacity": "15", "Is_Active": "Yes"},
            ],
            "PIG_MASTER": [
                {
                    "Pig_ID": "PIG-1",
                    "Tag_Number": "1",
                    "Pig_Name": "Pig One",
                    "Status": "Active",
                    "On_Farm": "Yes",
                    "Sex": "Female",
                    "Date_Of_Birth": "2026-01-01",
                    "Current_Pen_ID": "PEN-1",
                    "Litter_ID": "LIT-1",
                },
                {"Pig_ID": "", "Tag_Number": "missing"},
            ],
            "WEIGHT_LOG": [
                {"Weight_Log_ID": "WGT-1", "Pig_ID": "PIG-1", "Weight_Date": "2026-06-22", "Weight_Kg": "61.5"},
                {"Weight_Log_ID": "WGT-BAD", "Pig_ID": "PIG-404", "Weight_Date": "2026-06-22", "Weight_Kg": "50"},
            ],
            "LOCATION_HISTORY": [
                {"Move_Log_ID": "MOVE-1", "Pig_ID": "PIG-1", "Move_Date": "2026-06-22", "From_Pen_ID": "PEN-1", "To_Pen_ID": "PEN-2"},
                {"Move_Log_ID": "MOVE-BAD", "Pig_ID": "PIG-1", "Move_Date": "2026-06-22", "From_Pen_ID": "PEN-1", "To_Pen_ID": "PEN-404"},
            ],
            "MEDICAL_LOG": [
                {"Medical_Log_ID": "MED-1", "Pig_ID": "PIG-1", "Treatment_Date": "2026-06-01", "Product_ID": "PROD-1", "Withdrawal_Days": "7"}
            ],
            "PRODUCT_REGISTER": [
                {"Product_ID": "PROD-1", "Product_Name": "Treatment A", "Default_Withdrawal_Days": "7", "Is_Active": "Yes"}
            ],
            "LITTERS": [
                {"Litter_ID": "LIT-1", "Farrowing_Date": "2026-01-01", "Sow_Pig_ID": "PIG-1", "Total_Born": "8"}
            ],
            "MATING_LOG": [
                {"Mating_ID": "MAT-1", "Sow_Pig_ID": "PIG-1", "Mating_Date": "2025-10-01", "Related_Litter_ID": "LIT-1"}
            ],
            "SYSTEM_SETTINGS": [
                {"Setting_Key": "meat_window_min_kg", "Setting_Value": "60", "Description": "Default meat min"}
            ],
            "PIG_OVERVIEW": [{"Pig_ID": "PIG-1"}],
            "SALES_AVAILABILITY": [{"Pig_ID": "PIG-1"}],
            "SALES_STOCK_DETAIL": [],
            "SALES_STOCK_SUMMARY": [],
            "SALES_STOCK_TOTALS": [],
            "LITTER_OVERVIEW": [{"Litter_ID": "LIT-1"}],
            "MATING_OVERVIEW": [{"Mating_ID": "MAT-1"}],
        }

    def test_build_farm_import_dry_run_maps_core_payloads_without_writes(self):
        report = dry_run.build_farm_import_dry_run(self.sample_rows())

        self.assertTrue(report["success"])
        self.assertEqual(report["mode"], "dry_run_only")
        self.assertFalse(report["writes_to_supabase"])
        self.assertFalse(report["writes_to_sheets"])
        self.assertEqual(report["payload_summary"]["pigs"], 1)
        self.assertEqual(report["payload_summary"]["pens"], 2)
        self.assertEqual(report["payload_summary"]["pig_weight_events"], 2)
        self.assertEqual(report["payload_summary"]["pig_location_events"], 2)
        self.assertEqual(report["payload_summary"]["pig_medical_events"], 1)
        self.assertEqual(report["payload_summary"]["litters"], 1)
        self.assertEqual(report["payload_summary"]["mating_events"], 1)
        self.assertEqual(report["payload_summary"]["farm_products"], 1)
        self.assertEqual(report["payload_summary"]["app_settings"], 1)

    def test_link_issues_flag_unknown_pigs_and_pens_for_review(self):
        report = dry_run.build_farm_import_dry_run(self.sample_rows())

        self.assertEqual(report["link_issues"]["pig_weight_events"]["unknown_pig_id"], 1)
        self.assertEqual(report["link_issues"]["pig_location_events"]["unknown_to_pen_id"], 1)
        self.assertNotIn("pig_medical_events", report["link_issues"])

    def test_formula_sheets_are_compare_only_not_payloads(self):
        report = dry_run.build_farm_import_dry_run(self.sample_rows())

        self.assertEqual(report["formula_sheets"]["PIG_OVERVIEW"]["source_rows"], 1)
        self.assertEqual(
            report["formula_sheets"]["PIG_OVERVIEW"]["replacement_strategy"],
            "compare_only_until_formula_equivalence_tests_pass",
        )
        self.assertNotIn("pig_current_state", report["payload_summary"])

    def test_missing_required_ids_are_excluded(self):
        report = dry_run.build_farm_import_dry_run(self.sample_rows())

        pig_summary = report["summaries"]["PIG_MASTER"]
        self.assertEqual(pig_summary["included_rows"], 1)
        self.assertEqual(pig_summary["excluded_rows"], 1)
        self.assertEqual(pig_summary["reason_counts"]["missing_pig_id"], 1)

        excluded = report["reconciliation"]["excluded_row_samples"]["PIG_MASTER"][0]
        self.assertEqual(excluded["source_sheet_row"], 3)
        self.assertEqual(excluded["reason"], "missing_pig_id")
        self.assertEqual(excluded["sample"]["Tag_Number"], "missing")

    def test_reconciliation_reports_formula_count_matches_and_review_gate(self):
        report = dry_run.build_farm_import_dry_run(self.sample_rows())
        reconciliation = report["reconciliation"]

        self.assertEqual(reconciliation["source_sheet_row_counts"]["PIG_MASTER"], 2)
        self.assertEqual(reconciliation["payload_counts"]["pigs"], 1)
        self.assertFalse(reconciliation["import_readiness"]["ready_for_import"])
        self.assertEqual(
            reconciliation["formula_count_reconciliation"]["PIG_OVERVIEW"]["status"],
            "count_match",
        )
        self.assertEqual(
            reconciliation["formula_count_reconciliation"]["SALES_STOCK_SUMMARY"]["status"],
            "compare_only_no_direct_table_yet",
        )

    def test_reconciliation_flags_duplicates_and_missing_fields(self):
        rows = self.sample_rows()
        rows["WEIGHT_LOG"].append({
            "Weight_Log_ID": "WGT-1",
            "Pig_ID": "PIG-1",
            "Weight_Date": "2026-06-22",
            "Weight_Kg": "",
        })
        rows["LOCATION_HISTORY"].append({
            "Move_Log_ID": "MOVE-2",
            "Pig_ID": "PIG-1",
            "Move_Date": "2026-06-22",
            "From_Pen_ID": "PEN-1",
            "To_Pen_ID": "PEN-2",
        })

        report = dry_run.build_farm_import_dry_run(rows)
        reconciliation = report["reconciliation"]

        self.assertEqual(
            reconciliation["duplicate_issues"]["pig_weight_events"]["weight_event_id"]["WGT-1"],
            2,
        )
        self.assertEqual(
            reconciliation["duplicate_issues"]["pig_weight_events"]["same_pig_same_weight_date"]["PIG-1|2026-06-22"],
            2,
        )
        self.assertEqual(
            reconciliation["duplicate_issues"]["pig_location_events"]["same_pig_same_date_same_to_pen"]["PIG-1|2026-06-22|PEN-2"],
            2,
        )
        self.assertEqual(
            reconciliation["field_quality_issues"]["pig_weight_events"]["missing_weight_kg"],
            1,
        )

    def test_issue_report_classifies_missing_ids_and_duplicate_groups(self):
        rows = self.sample_rows()
        rows["WEIGHT_LOG"].append({
            "Weight_Log_ID": "WGT-2",
            "Pig_ID": "PIG-1",
            "Weight_Date": "2026-06-22",
            "Weight_Kg": "61.5",
        })
        rows["WEIGHT_LOG"].append({
            "Weight_Log_ID": "WGT-MISSING",
            "Pig_ID": "",
            "Weight_Date": "2026-06-23",
            "Weight_Kg": "62",
        })
        rows["LOCATION_HISTORY"].append({
            "Move_Log_ID": "MOVE-2",
            "Pig_ID": "PIG-1",
            "Move_Date": "2026-06-22",
            "From_Pen_ID": "PEN-1",
            "To_Pen_ID": "PEN-2",
        })

        report = dry_run.build_farm_import_dry_run(rows)
        issue_report = dry_run.build_issue_report(rows, report["reconciliation"])

        self.assertTrue(issue_report["success"])
        self.assertFalse(issue_report["writes_to_supabase"])
        self.assertFalse(issue_report["writes_to_sheets"])
        self.assertEqual(issue_report["summary"]["missing_weight_pig_id_rows"], 1)
        self.assertEqual(issue_report["summary"]["duplicate_weight_groups"], 1)
        self.assertEqual(issue_report["summary"]["likely_weight_duplicate_groups"], 1)
        self.assertEqual(issue_report["summary"]["duplicate_location_groups"], 1)
        self.assertEqual(issue_report["summary"]["likely_location_duplicate_groups"], 1)
        self.assertEqual(
            issue_report["duplicate_weight_groups"][0]["recommendation"],
            "likely_duplicate_same_weight",
        )
        self.assertIn("approve_duplicate_weight_import_policy", issue_report["owner_decisions_needed"])

    def test_issue_report_marks_conflicting_weight_duplicates_for_review(self):
        rows = self.sample_rows()
        rows["WEIGHT_LOG"].append({
            "Weight_Log_ID": "WGT-2",
            "Pig_ID": "PIG-1",
            "Weight_Date": "2026-06-22",
            "Weight_Kg": "70",
        })

        report = dry_run.build_farm_import_dry_run(rows)
        issue_report = dry_run.build_issue_report(rows, report["reconciliation"])

        self.assertEqual(issue_report["summary"]["duplicate_weight_groups"], 1)
        self.assertEqual(issue_report["summary"]["conflicting_weight_groups"], 1)
        self.assertEqual(
            issue_report["duplicate_weight_groups"][0]["recommendation"],
            "needs_owner_review_conflicting_weights",
        )

    def test_load_sheet_rows_reads_only_configured_sheets(self):
        calls = []

        def fake_get_all_records(sheet_name):
            calls.append(sheet_name)
            return []

        with patch.object(dry_run, "get_all_records", side_effect=fake_get_all_records):
            rows = dry_run.load_sheet_rows()

        self.assertEqual(set(rows), set(dry_run.SHEETS))
        self.assertEqual(set(calls), set(dry_run.SHEETS))

    def test_main_reports_sheet_read_failure_as_json_safe_status(self):
        with patch.object(dry_run, "load_sheet_rows", side_effect=RuntimeError("network blocked")), \
             patch.object(dry_run, "print") as print_mock:
            status = dry_run.main([])

        self.assertEqual(status, 2)
        printed = print_mock.call_args.args[0]
        self.assertIn('"success": false', printed)
        self.assertIn('"status": "sheet_read_failed"', printed)
        self.assertIn('"writes_to_supabase": false', printed)
        self.assertIn('"writes_to_sheets": false', printed)

    def test_main_issue_report_prints_targeted_diagnostics(self):
        with patch.object(dry_run, "load_sheet_rows", return_value=self.sample_rows()), \
             patch.object(dry_run, "print") as print_mock:
            status = dry_run.main(["--issue-report"])

        self.assertEqual(status, 0)
        printed = print_mock.call_args.args[0]
        self.assertIn('"mode": "dry_run_issue_review_only"', printed)
        self.assertIn('"owner_decisions_needed"', printed)
        self.assertIn('"writes_to_supabase": false', printed)

    def test_policy_backfill_verifier_collapses_duplicates_and_quarantines_missing_ids(self):
        rows = self.sample_rows()
        rows["WEIGHT_LOG"] = [
            {"Weight_Log_ID": "WGT-1", "Pig_ID": "PIG-1", "Weight_Date": "2026-06-22", "Weight_Kg": "61.5"},
            {"Weight_Log_ID": "WGT-2", "Pig_ID": "PIG-1", "Weight_Date": "2026-06-22", "Weight_Kg": "61.5"},
            {"Weight_Log_ID": "WGT-MISSING", "Pig_ID": "", "Weight_Date": "2026-06-23", "Weight_Kg": "62"},
            {"Weight_Log_ID": "WGT-3", "Pig_ID": "PIG-1", "Weight_Date": "2026-06-24", "Weight_Kg": "62"},
            {"Weight_Log_ID": "WGT-4", "Pig_ID": "PIG-1", "Weight_Date": "2026-06-24", "Weight_Kg": "70"},
        ]
        rows["LOCATION_HISTORY"] = [
            {"Move_Log_ID": "MOVE-1", "Pig_ID": "PIG-1", "Move_Date": "2026-06-22", "From_Pen_ID": "PEN-1", "To_Pen_ID": "PEN-2"},
            {"Move_Log_ID": "MOVE-2", "Pig_ID": "PIG-1", "Move_Date": "2026-06-22", "From_Pen_ID": "PEN-1", "To_Pen_ID": "PEN-2"},
        ]

        verifier = dry_run.build_policy_backfill_verifier(rows)

        self.assertTrue(verifier["success"])
        self.assertFalse(verifier["writes_to_supabase"])
        self.assertFalse(verifier["writes_to_sheets"])
        self.assertEqual(verifier["original_payload_summary"]["pig_weight_events"], 4)
        self.assertEqual(verifier["canonical_payload_summary"]["pig_weight_events"], 1)
        self.assertEqual(verifier["canonical_payload_summary"]["pig_location_events"], 1)
        self.assertEqual(verifier["review_summary"]["by_type"]["missing_pig_id_weight"], 1)
        self.assertEqual(verifier["review_summary"]["by_type"]["same_weight_duplicate"], 1)
        self.assertEqual(verifier["review_summary"]["by_type"]["conflicting_weight"], 1)
        self.assertEqual(verifier["review_summary"]["by_type"]["same_movement_duplicate"], 1)
        self.assertEqual(verifier["verification"]["pending_review_count"], 2)
        self.assertFalse(verifier["verification"]["import_ready"])

        review_statuses = {item["review_type"]: item["status"] for item in verifier["review_items"]}
        self.assertEqual(review_statuses["missing_pig_id_weight"], "quarantined")
        self.assertEqual(review_statuses["conflicting_weight"], "pending_owner_review")

    def test_policy_backfill_verifier_keeps_source_refs_for_auto_dedupe(self):
        rows = self.sample_rows()
        rows["WEIGHT_LOG"] = [
            {"Weight_Log_ID": "WGT-1", "Pig_ID": "PIG-1", "Weight_Date": "2026-06-22", "Weight_Kg": "61.5"},
            {"Weight_Log_ID": "WGT-2", "Pig_ID": "PIG-1", "Weight_Date": "2026-06-22", "Weight_Kg": "61.5"},
        ]
        rows["LOCATION_HISTORY"] = []

        verifier = dry_run.build_policy_backfill_verifier(rows)
        canonical_weight = verifier["canonical_payloads"]["pig_weight_events"][0]

        self.assertEqual(canonical_weight["dedupe_policy"], "same_pig_same_date_same_weight_keep_first_source_row")
        self.assertEqual(len(canonical_weight["duplicate_source_refs"]), 2)

    def test_policy_backfill_verifier_quarantines_invalid_location_rows(self):
        rows = self.sample_rows()
        rows["WEIGHT_LOG"] = []
        rows["LOCATION_HISTORY"] = [
            {"Move_Log_ID": "MOVE-1", "Pig_ID": "PIG-1", "Move_Date": "2026-06-22", "From_Pen_ID": "PEN-1", "To_Pen_ID": "PEN-2"},
            {"Move_Log_ID": "MOVE-MISSING-DATE", "Pig_ID": "PIG-1", "Move_Date": "", "From_Pen_ID": "PEN-1", "To_Pen_ID": "PEN-2"},
            {"Move_Log_ID": "MOVE-MISSING-PEN", "Pig_ID": "PIG-1", "Move_Date": "2026-06-23", "From_Pen_ID": "PEN-1", "To_Pen_ID": ""},
        ]

        verifier = dry_run.build_policy_backfill_verifier(rows)

        self.assertEqual(verifier["canonical_payload_summary"]["pig_location_events"], 1)
        self.assertEqual(verifier["review_summary"]["by_type"]["invalid_location_row"], 2)
        self.assertTrue(verifier["verification"]["location_source_rows_accounted"])
        self.assertEqual(verifier["verification"]["location_source_row_count"], 3)
        self.assertEqual(verifier["verification"]["location_accounted_row_count"], 3)
        self.assertEqual(verifier["verification"]["location_unaccounted_source_rows"], [])

        invalid_reasons = [
            tuple(item["invalid_reasons"])
            for item in verifier["review_items"]
            if item["review_type"] == "invalid_location_row"
        ]
        self.assertIn(("missing_move_date",), invalid_reasons)
        self.assertIn(("missing_to_pen_id",), invalid_reasons)

    def test_policy_backfill_verifier_accounts_for_duplicate_location_sources(self):
        rows = self.sample_rows()
        rows["WEIGHT_LOG"] = []
        rows["LOCATION_HISTORY"] = [
            {"Move_Log_ID": "MOVE-1", "Pig_ID": "PIG-1", "Move_Date": "2026-06-22", "From_Pen_ID": "PEN-1", "To_Pen_ID": "PEN-2"},
            {"Move_Log_ID": "MOVE-2", "Pig_ID": "PIG-1", "Move_Date": "2026-06-22", "From_Pen_ID": "PEN-1", "To_Pen_ID": "PEN-2"},
        ]

        verifier = dry_run.build_policy_backfill_verifier(rows)

        self.assertEqual(verifier["canonical_payload_summary"]["pig_location_events"], 1)
        self.assertEqual(verifier["review_summary"]["by_type"]["same_movement_duplicate"], 1)
        self.assertTrue(verifier["verification"]["location_source_rows_accounted"])
        self.assertEqual(verifier["verification"]["location_source_row_count"], 2)
        self.assertEqual(verifier["verification"]["location_accounted_row_count"], 2)

    def test_main_backfill_verifier_prints_no_write_summary(self):
        with patch.object(dry_run, "load_sheet_rows", return_value=self.sample_rows()), \
             patch.object(dry_run, "print") as print_mock:
            status = dry_run.main(["--backfill-verifier", "--review-samples", "1"])

        self.assertEqual(status, 0)
        printed = print_mock.call_args.args[0]
        self.assertIn('"mode": "dry_run_policy_backfill_verifier"', printed)
        self.assertIn('"writes_to_supabase": false', printed)
        self.assertIn('"canonical_payload_summary"', printed)


if __name__ == "__main__":
    unittest.main()
