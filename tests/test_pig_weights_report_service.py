import unittest
from unittest.mock import patch

from modules.pig_weights import farm_supabase_read_service
from modules.pig_weights import pig_weights_service


def records_for_sheet(sheet_name):
    data = {
        "WEIGHT_LOG": [
            {
                "Weight_Log_ID": "WGT-OLD",
                "Pig_ID": "PIG-1",
                "Weight_Date": "18 May 2026",
                "Weight_Kg": "40",
                "Weighed_By": "Tester",
                "Condition_Notes": "",
            },
            {
                "Weight_Log_ID": "WGT-1",
                "Pig_ID": "PIG-1",
                "Weight_Date": "20 May 2026",
                "Weight_Kg": "42",
                "Weighed_By": "Tester",
                "Condition_Notes": "Good",
            },
            {
                "Weight_Log_ID": "WGT-DUP",
                "Pig_ID": "PIG-1",
                "Weight_Date": "20 May 2026",
                "Weight_Kg": "41",
                "Weighed_By": "Tester",
                "Condition_Notes": "",
            },
            {
                "Weight_Log_ID": "WGT-2-OLD",
                "Pig_ID": "PIG-2",
                "Weight_Date": "18 May 2026",
                "Weight_Kg": "36",
                "Weighed_By": "Tester",
                "Condition_Notes": "",
            },
            {
                "Weight_Log_ID": "WGT-2",
                "Pig_ID": "PIG-2",
                "Weight_Date": "20 May 2026",
                "Weight_Kg": "35",
                "Weighed_By": "Tester",
                "Condition_Notes": "",
            },
            {
                "Weight_Log_ID": "WGT-SOLD",
                "Pig_ID": "PIG-SOLD",
                "Weight_Date": "20 May 2026",
                "Weight_Kg": "50",
                "Weighed_By": "Tester",
                "Condition_Notes": "",
            },
        ],
        "PIG_OVERVIEW": [
            {
                "Pig_ID": "PIG-1",
                "Tag_Number": "001",
                "Status": "Active",
                "On_Farm": "Yes",
                "Current_Pen_ID": "PEN-1",
                "Calculated_Stage": "Grower",
                "Weight_Band": "40_to_44_Kg",
            },
            {
                "Pig_ID": "PIG-2",
                "Tag_Number": "002",
                "Status": "Active",
                "On_Farm": "Yes",
                "Current_Pen_ID": "PEN-2",
                "Calculated_Stage": "Grower",
                "Weight_Band": "35_to_39_Kg",
            },
            {
                "Pig_ID": "PIG-SOLD",
                "Tag_Number": "099",
                "Status": "Sold",
                "On_Farm": "No",
                "Current_Pen_ID": "PEN-1",
                "Calculated_Stage": "Finisher",
                "Weight_Band": "50_to_54_Kg",
            },
        ],
        "PEN_REGISTER": [
            {"Pen_ID": "PEN-1", "Pen_Name": "Camp 1", "Pen_Type": "Grower"},
            {"Pen_ID": "PEN-2", "Pen_Name": "Camp 2", "Pen_Type": "Grower"},
        ],
    }
    return data[sheet_name]


class WeightReportServiceTests(unittest.TestCase):
    def test_weight_report_keeps_historical_rows_and_flags_currently_inactive_pigs(self):
        with patch.object(farm_supabase_read_service, "farm_supabase_reads_available", return_value=False), \
             patch.object(pig_weights_service, "get_all_records", side_effect=records_for_sheet):
            report = pig_weights_service.get_weight_report("2026-05-20", "2026-05-20")

        self.assertTrue(report["success"])
        self.assertEqual(report["summary"]["total_entries"], 4)
        self.assertEqual(report["summary"]["unique_pigs"], 3)
        self.assertEqual(report["summary"]["average_weight_kg"], 42.0)
        self.assertEqual(report["summary"]["average_difference_kg"], 0.67)
        self.assertEqual(report["summary"]["average_growth_rate_kg_day"], 0.33)
        self.assertEqual(report["summary"]["weight_gain_count"], 2)
        self.assertEqual(report["summary"]["weight_loss_count"], 1)
        self.assertEqual(report["summary"]["duplicate_same_day_count"], 2)
        self.assertEqual(report["summary"]["not_active_on_farm_count"], 1)

        pig_ids = [entry["pig_id"] for entry in report["entries"]]
        self.assertEqual(pig_ids, ["PIG-1", "PIG-1", "PIG-SOLD", "PIG-2"])
        self.assertEqual(report["entries"][0]["previous_weight_kg"], 40.0)
        self.assertEqual(report["entries"][0]["difference_kg"], 2.0)
        self.assertEqual(report["entries"][0]["growth_rate_kg_day"], 1.0)
        self.assertEqual(report["entries"][0]["current_pen_name"], "Camp 1")
        self.assertTrue(report["entries"][0]["duplicate_same_day"])
        self.assertEqual(report["entries"][0]["duplicate_entry_count"], 2)
        self.assertFalse(report["entries"][2]["active_on_farm"])
        self.assertEqual(report["entries"][2]["status"], "Sold")
        self.assertEqual(len(report["loss_flags"]), 1)
        self.assertEqual(report["loss_flags"][0]["pig_id"], "PIG-2")

    def test_weight_report_can_filter_by_pen(self):
        with patch.object(farm_supabase_read_service, "farm_supabase_reads_available", return_value=False), \
             patch.object(pig_weights_service, "get_all_records", side_effect=records_for_sheet):
            report = pig_weights_service.get_weight_report("2026-05-20", "2026-05-20", pen_id="PEN-2")

        self.assertEqual(report["summary"]["total_entries"], 1)
        self.assertEqual(report["entries"][0]["pig_id"], "PIG-2")
        self.assertEqual(report["pen_summary"][0]["pen_id"], "PEN-2")

    def test_weight_report_sorts_numeric_tags_by_padded_value_within_pen(self):
        def sheet_records(sheet_name):
            data = {
                "WEIGHT_LOG": [
                    {
                        "Weight_Log_ID": "WGT-10",
                        "Pig_ID": "PIG-10",
                        "Weight_Date": "20 May 2026",
                        "Weight_Kg": "30",
                        "Weighed_By": "Tester",
                        "Condition_Notes": "",
                    },
                    {
                        "Weight_Log_ID": "WGT-2",
                        "Pig_ID": "PIG-2",
                        "Weight_Date": "20 May 2026",
                        "Weight_Kg": "28",
                        "Weighed_By": "Tester",
                        "Condition_Notes": "",
                    },
                ],
                "PIG_OVERVIEW": [
                    {
                        "Pig_ID": "PIG-10",
                        "Tag_Number": "10",
                        "Status": "Active",
                        "On_Farm": "Yes",
                        "Current_Pen_ID": "PEN-1",
                        "Calculated_Stage": "Grower",
                        "Weight_Band": "30_to_34_Kg",
                    },
                    {
                        "Pig_ID": "PIG-2",
                        "Tag_Number": "2",
                        "Status": "Active",
                        "On_Farm": "Yes",
                        "Current_Pen_ID": "PEN-1",
                        "Calculated_Stage": "Grower",
                        "Weight_Band": "25_to_29_Kg",
                    },
                ],
                "PEN_REGISTER": [
                    {"Pen_ID": "PEN-1", "Pen_Name": "Camp 1", "Pen_Type": "Grower"},
                ],
            }
            return data[sheet_name]

        with patch.object(farm_supabase_read_service, "farm_supabase_reads_available", return_value=False), \
             patch.object(pig_weights_service, "get_all_records", side_effect=sheet_records):
            report = pig_weights_service.get_weight_report("2026-05-20", "2026-05-20")

        self.assertEqual([entry["pig_id"] for entry in report["entries"]], ["PIG-2", "PIG-10"])

    def test_weight_report_rejects_invalid_date_range(self):
        with self.assertRaisesRegex(ValueError, "date_from"):
            pig_weights_service.get_weight_report("2026-05-21", "2026-05-20")


if __name__ == "__main__":
    unittest.main()
