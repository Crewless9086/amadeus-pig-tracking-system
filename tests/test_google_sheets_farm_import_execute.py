import unittest

from scripts import google_sheets_farm_import_execute as importer


class GoogleSheetsFarmImportExecuteTests(unittest.TestCase):
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
            ],
            "WEIGHT_LOG": [
                {"Weight_Log_ID": "WGT-1", "Pig_ID": "PIG-1", "Weight_Date": "2026-06-22", "Weight_Kg": "61.5"},
                {"Weight_Log_ID": "WGT-2", "Pig_ID": "PIG-1", "Weight_Date": "2026-06-22", "Weight_Kg": "61.5"},
                {"Weight_Log_ID": "WGT-3", "Pig_ID": "PIG-1", "Weight_Date": "2026-06-24", "Weight_Kg": "62"},
                {"Weight_Log_ID": "WGT-4", "Pig_ID": "PIG-1", "Weight_Date": "2026-06-24", "Weight_Kg": "70"},
            ],
            "LOCATION_HISTORY": [
                {"Move_Log_ID": "MOVE-1", "Pig_ID": "PIG-1", "Move_Date": "2026-06-22", "From_Pen_ID": "PEN-1", "To_Pen_ID": "PEN-2"},
                {"Move_Log_ID": "MOVE-2", "Pig_ID": "PIG-1", "Move_Date": "2026-06-22", "From_Pen_ID": "PEN-1", "To_Pen_ID": "PEN-2"},
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
            "SALES_AVAILABILITY": [],
            "SALES_STOCK_DETAIL": [],
            "SALES_STOCK_SUMMARY": [],
            "SALES_STOCK_TOTALS": [],
            "LITTER_OVERVIEW": [{"Litter_ID": "LIT-1"}],
            "MATING_OVERVIEW": [{"Mating_ID": "MAT-1"}],
        }

    def test_build_import_payloads_applies_policy_and_strips_non_schema_fields(self):
        plan = importer.build_import_payloads(self.sample_rows(), import_batch_id="TEST-BATCH")

        self.assertTrue(plan["success"])
        self.assertFalse(plan["writes_to_sheets"])
        self.assertEqual(plan["payload_summary"]["pig_weight_events"], 1)
        self.assertEqual(plan["payload_summary"]["pig_location_events"], 1)
        self.assertEqual(plan["review_summary"]["by_type"]["same_weight_duplicate"], 1)
        self.assertEqual(plan["review_summary"]["by_type"]["conflicting_weight"], 1)
        self.assertEqual(plan["review_summary"]["by_type"]["same_movement_duplicate"], 1)

        weight = plan["payloads"]["pig_weight_events"][0]
        self.assertEqual(weight["import_batch_id"], "TEST-BATCH")
        self.assertNotIn("dedupe_policy", weight)
        self.assertNotIn("duplicate_source_refs", weight)

    def test_build_import_payloads_refuses_missing_pig_id_weight_rows(self):
        rows = self.sample_rows()
        rows["WEIGHT_LOG"].append({
            "Weight_Log_ID": "WGT-MISSING",
            "Pig_ID": "",
            "Weight_Date": "2026-06-23",
            "Weight_Kg": "62",
        })

        with self.assertRaises(ValueError):
            importer.build_import_payloads(rows)

    def test_clean_payload_row_uses_known_table_columns_only(self):
        row = {
            "weight_event_id": "WGT-1",
            "pig_id": "PIG-1",
            "weight_date": "2026-06-22",
            "weight_kg": 61.5,
            "dedupe_policy": "remove-me",
        }

        clean = importer.clean_payload_row("pig_weight_events", row, "BATCH")

        self.assertEqual(clean["import_batch_id"], "BATCH")
        self.assertNotIn("dedupe_policy", clean)
        self.assertEqual(set(clean), set(importer.TABLE_COLUMNS["pig_weight_events"]))


if __name__ == "__main__":
    unittest.main()
