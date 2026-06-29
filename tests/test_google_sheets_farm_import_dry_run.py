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


if __name__ == "__main__":
    unittest.main()
