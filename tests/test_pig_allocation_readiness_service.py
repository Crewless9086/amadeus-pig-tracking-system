from datetime import date
import unittest
from unittest.mock import patch

from modules.pig_weights import pig_weights_service


class PigAllocationReadinessServiceTests(unittest.TestCase):
    def test_allocation_readiness_groups_pigs_with_explainable_buckets(self):
        overview_rows = [
            {
                "Pig_ID": "PIG-1",
                "Tag_Number": "1",
                "Animal_Type": "Grower",
                "Sex": "Female",
                "Status": "Active",
                "On_Farm": "Yes",
                "Purpose": "Unknown",
                "Current_Pen_ID": "PEN-1",
                "Current_Weight_Kg": "62",
                "Last_Weight_Date": "2026-06-01",
                "Date_Of_Birth": "2026-02-01",
                "Age_Days": "124",
                "Litter_ID": "LIT-1",
            },
            {
                "Pig_ID": "PIG-2",
                "Tag_Number": "2",
                "Animal_Type": "Finisher",
                "Sex": "Male",
                "Status": "Active",
                "On_Farm": "Yes",
                "Purpose": "Grow_Out",
                "Current_Pen_ID": "PEN-1",
                "Current_Weight_Kg": "64",
                "Last_Weight_Date": "2026-06-01",
                "Date_Of_Birth": "2026-02-01",
                "Age_Days": "124",
            },
            {
                "Pig_ID": "PIG-3",
                "Tag_Number": "3",
                "Animal_Type": "Gilt",
                "Sex": "Female",
                "Status": "Active",
                "On_Farm": "Yes",
                "Purpose": "Breeding",
                "Current_Pen_ID": "PEN-2",
                "Current_Weight_Kg": "80",
                "Last_Weight_Date": "2026-06-01",
                "Date_Of_Birth": "2026-02-01",
                "Age_Days": "124",
            },
            {
                "Pig_ID": "PIG-4",
                "Tag_Number": "4",
                "Animal_Type": "Grower",
                "Sex": "Male",
                "Status": "Active",
                "On_Farm": "Yes",
                "Purpose": "Grow_Out",
                "Current_Pen_ID": "PEN-2",
                "Current_Weight_Kg": "40",
                "Last_Weight_Date": "2026-06-01",
                "Date_Of_Birth": "2026-02-01",
                "Age_Days": "124",
            },
            {
                "Pig_ID": "PIG-5",
                "Tag_Number": "5",
                "Animal_Type": "Grower",
                "Sex": "Male",
                "Status": "Sold",
                "On_Farm": "No",
                "Purpose": "Sale",
                "Current_Pen_ID": "PEN-3",
                "Current_Weight_Kg": "75",
                "Date_Of_Birth": "2026-02-01",
                "Age_Days": "124",
            },
        ]
        weight_rows = [
            {"Pig_ID": "PIG-1", "Weight_Date": "2026-06-01", "Weight_Kg": "62"},
            {"Pig_ID": "PIG-2", "Weight_Date": "2026-06-01", "Weight_Kg": "64"},
            {"Pig_ID": "PIG-3", "Weight_Date": "2026-06-01", "Weight_Kg": "80"},
            {"Pig_ID": "PIG-4", "Weight_Date": "2026-06-01", "Weight_Kg": "40"},
        ]
        sales_rows = [
            {
                "Pig_ID": "PIG-1",
                "Available_For_Sale": "Yes",
                "Reserved_Status": "Not_Reserved",
                "Reserved_For_Order_ID": "",
                "Sale_Category": "Grower",
            },
            {
                "Pig_ID": "PIG-2",
                "Available_For_Sale": "No",
                "Reserved_Status": "Reserved",
                "Reserved_For_Order_ID": "ORD-1",
                "Sale_Category": "Slaughter",
            },
        ]
        pen_rows = [
            {"Pen_ID": "PEN-1", "Pen_Name": "Grower Pen", "Pen_Type": "Grower"},
            {"Pen_ID": "PEN-2", "Pen_Name": "Breeding Pen", "Pen_Type": "Breeding"},
        ]

        def fake_get_all_records(sheet_name):
            if sheet_name == "PIG_OVERVIEW":
                return overview_rows
            if sheet_name == "WEIGHT_LOG":
                return weight_rows
            if sheet_name == "SALES_AVAILABILITY":
                return sales_rows
            if sheet_name == "PEN_REGISTER":
                return pen_rows
            if sheet_name == "LITTER_OVERVIEW":
                return [
                    {
                        "Litter_ID": "LIT-1",
                        "Born_Alive": "10",
                        "Weaned_Count": "9",
                        "Sow_Pig_ID": "SOW-1",
                        "Sow_Tag_Number": "101",
                        "Boar_Pig_ID": "BOAR-1",
                        "Boar_Tag_Number": "201",
                    }
                ]
            return []

        with patch.object(pig_weights_service, "get_all_records", side_effect=fake_get_all_records):
            result = pig_weights_service.get_pig_allocation_readiness(today=date(2026, 6, 4))

        by_id = {row["pig_id"]: row for row in result["pigs"]}
        self.assertTrue(result["success"])
        self.assertFalse(result["writes_to_sheets"])
        self.assertFalse(result["writes_to_supabase"])
        self.assertEqual(by_id["PIG-1"]["readiness_bucket"], "Needs Classification")
        self.assertIn("Purpose is still unknown", by_id["PIG-1"]["readiness_reason"])
        self.assertEqual(by_id["PIG-1"]["growth_class"], "Exceptional")
        self.assertEqual(by_id["PIG-1"]["average_daily_gain_kg"], 0.5)
        self.assertEqual(result["thresholds"]["slaughter_target_min_kg"], 80)
        self.assertEqual(by_id["PIG-1"]["litter_quality"], "Good")
        self.assertEqual(by_id["PIG-1"]["litter_survival_rate"], 0.9)
        self.assertEqual(by_id["PIG-2"]["readiness_bucket"], "Allocated")
        self.assertEqual(by_id["PIG-2"]["existing_link"], "ORD-1")
        self.assertEqual(by_id["PIG-3"]["readiness_bucket"], "Retain / Breeding Candidate")
        self.assertEqual(by_id["PIG-4"]["readiness_bucket"], "Growing")
        self.assertEqual(by_id["PIG-5"]["readiness_bucket"], "Exited")
        self.assertEqual(result["summary"]["buckets"]["Allocated"], 1)

    def test_exceptional_grower_from_good_litter_is_flagged_for_breeding_review(self):
        overview_rows = [{
            "Pig_ID": "PIG-FAST",
            "Tag_Number": "10",
            "Animal_Type": "Grower",
            "Sex": "Female",
            "Status": "Active",
            "On_Farm": "Yes",
            "Purpose": "Grow_Out",
            "Current_Pen_ID": "PEN-1",
            "Current_Weight_Kg": "66",
            "Last_Weight_Date": "2026-06-04",
            "Date_Of_Birth": "2026-01-24",
            "Age_Days": "132",
            "Wean_Date": "2026-05-04",
            "Wean_Weight_Kg": "12",
            "Average_Daily_Gain_Kg": "0.60",
            "Litter_ID": "LIT-GOOD",
        }]
        litter_rows = [{
            "Litter_ID": "LIT-GOOD",
            "Born_Alive": "10",
            "Weaned_Count": "9",
            "Sow_Pig_ID": "SOW-1",
            "Sow_Tag_Number": "101",
            "Boar_Pig_ID": "BOAR-1",
            "Boar_Tag_Number": "201",
        }]

        def fake_get_all_records(sheet_name):
            if sheet_name == "PIG_OVERVIEW":
                return overview_rows
            if sheet_name == "WEIGHT_LOG":
                return [{"Pig_ID": "PIG-FAST", "Weight_Date": "2026-06-04", "Weight_Kg": "66"}]
            if sheet_name == "SALES_AVAILABILITY":
                return []
            if sheet_name == "PEN_REGISTER":
                return [{"Pen_ID": "PEN-1", "Pen_Name": "Grower Pen"}]
            if sheet_name == "LITTER_OVERVIEW":
                return litter_rows
            return []

        with patch.object(pig_weights_service, "get_all_records", side_effect=fake_get_all_records):
            result = pig_weights_service.get_pig_allocation_readiness(today=date(2026, 6, 4))

        row = result["pigs"][0]
        self.assertEqual(row["readiness_bucket"], "Retain / Breeding Candidate")
        self.assertEqual(row["growth_class"], "Exceptional")
        self.assertEqual(row["litter_quality"], "Good")
        self.assertEqual(row["average_daily_gain_kg"], 0.5)
        self.assertEqual(row["post_wean_daily_gain_kg"], 0.6)
        self.assertEqual(row["meat_window_status"], "In meat window")
        self.assertEqual(row["estimated_abattoir_ready_date"], "2026-07-02")
        self.assertEqual(row["days_until_abattoir_ready"], 28)

    def test_growth_class_bands_use_lifetime_average_daily_gain(self):
        cases = [
            ("PIG-EXTREME", "9.0", "100", "Extremely Slow"),
            ("PIG-SLOW", "15.0", "100", "Slow"),
            ("PIG-BELOW", "25.0", "100", "Below Target"),
            ("PIG-STEADY", "35.0", "100", "Steady"),
            ("PIG-GOOD", "44.55", "99", "Good"),
            ("PIG-EXCEPTIONAL", "49.5", "99", "Exceptional"),
        ]
        overview_rows = [
            {
                "Pig_ID": pig_id,
                "Tag_Number": str(index + 20),
                "Animal_Type": "Grower",
                "Sex": "Male",
                "Status": "Active",
                "On_Farm": "Yes",
                "Purpose": "Grow_Out",
                "Current_Pen_ID": "PEN-1",
                "Current_Weight_Kg": weight,
                "Last_Weight_Date": "2026-06-04",
                "Age_Days": age_days,
            }
            for index, (pig_id, weight, age_days, _expected) in enumerate(cases)
        ]

        def fake_get_all_records(sheet_name):
            if sheet_name == "PIG_OVERVIEW":
                return overview_rows
            if sheet_name == "WEIGHT_LOG":
                return [
                    {"Pig_ID": pig_id, "Weight_Date": "2026-06-04", "Weight_Kg": weight}
                    for pig_id, weight, _age_days, _expected in cases
                ]
            if sheet_name == "SALES_AVAILABILITY":
                return []
            if sheet_name == "PEN_REGISTER":
                return [{"Pen_ID": "PEN-1", "Pen_Name": "Grower Pen"}]
            if sheet_name == "LITTER_OVERVIEW":
                return []
            return []

        with patch.object(pig_weights_service, "get_all_records", side_effect=fake_get_all_records):
            result = pig_weights_service.get_pig_allocation_readiness(today=date(2026, 6, 4))

        by_id = {row["pig_id"]: row for row in result["pigs"]}
        for pig_id, _weight, _age_days, expected in cases:
            with self.subTest(pig_id=pig_id):
                self.assertEqual(by_id[pig_id]["growth_class"], expected)
                self.assertEqual(by_id[pig_id]["growth_basis"], "Lifetime ADG")


if __name__ == "__main__":
    unittest.main()
