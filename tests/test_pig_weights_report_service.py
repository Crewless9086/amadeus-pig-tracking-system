import unittest
from unittest.mock import patch

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
    def test_weight_report_filters_to_active_on_farm_pigs_and_calculates_summary(self):
        with patch.object(pig_weights_service, "get_all_records", side_effect=records_for_sheet):
            report = pig_weights_service.get_weight_report("2026-05-20", "2026-05-20")

        self.assertTrue(report["success"])
        self.assertEqual(report["summary"]["total_entries"], 3)
        self.assertEqual(report["summary"]["unique_pigs"], 2)
        self.assertEqual(report["summary"]["average_weight_kg"], 39.33)
        self.assertEqual(report["summary"]["average_difference_kg"], 0.67)
        self.assertEqual(report["summary"]["average_growth_rate_kg_day"], 0.33)
        self.assertEqual(report["summary"]["weight_gain_count"], 2)
        self.assertEqual(report["summary"]["weight_loss_count"], 1)
        self.assertEqual(report["summary"]["duplicate_same_day_count"], 2)

        pig_ids = [entry["pig_id"] for entry in report["entries"]]
        self.assertEqual(pig_ids, ["PIG-1", "PIG-1", "PIG-2"])
        self.assertEqual(report["entries"][0]["previous_weight_kg"], 40.0)
        self.assertEqual(report["entries"][0]["difference_kg"], 2.0)
        self.assertEqual(report["entries"][0]["growth_rate_kg_day"], 1.0)
        self.assertEqual(report["entries"][0]["current_pen_name"], "Camp 1")
        self.assertTrue(report["entries"][0]["duplicate_same_day"])
        self.assertEqual(report["entries"][0]["duplicate_entry_count"], 2)
        self.assertEqual(len(report["loss_flags"]), 1)
        self.assertEqual(report["loss_flags"][0]["pig_id"], "PIG-2")

    def test_weight_report_can_filter_by_pen(self):
        with patch.object(pig_weights_service, "get_all_records", side_effect=records_for_sheet):
            report = pig_weights_service.get_weight_report("2026-05-20", "2026-05-20", pen_id="PEN-2")

        self.assertEqual(report["summary"]["total_entries"], 1)
        self.assertEqual(report["entries"][0]["pig_id"], "PIG-2")
        self.assertEqual(report["pen_summary"][0]["pen_id"], "PEN-2")

    def test_weight_report_rejects_invalid_date_range(self):
        with self.assertRaisesRegex(ValueError, "date_from"):
            pig_weights_service.get_weight_report("2026-05-21", "2026-05-20")


if __name__ == "__main__":
    unittest.main()
