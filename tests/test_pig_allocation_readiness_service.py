from datetime import date
import unittest
from unittest.mock import patch

from modules.pig_weights import farm_supabase_read_service
from modules.pig_weights import pig_weights_service


class PigAllocationReadinessServiceTests(unittest.TestCase):
    def setUp(self):
        self._supabase_available_patch = patch.object(
            farm_supabase_read_service,
            "farm_supabase_reads_available",
            return_value=False,
        )
        self._supabase_available_patch.start()

    def tearDown(self):
        self._supabase_available_patch.stop()

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
        self.assertEqual(by_id["PIG-1"]["suggested_purpose"], "Breeding Review")
        self.assertEqual(by_id["PIG-1"]["suggested_purpose_confidence"], "Low")
        self.assertEqual(by_id["PIG-1"]["growth_class"], "Exceptional")
        self.assertEqual(by_id["PIG-1"]["average_daily_gain_kg"], 0.5)
        self.assertEqual(result["thresholds"]["slaughter_target_min_kg"], 80)
        self.assertEqual(result["thresholds"]["source"], "code_defaults")
        self.assertFalse(result["thresholds"]["writes_enabled"])
        self.assertEqual(result["business_rules"]["meat_window_label"], "60-<80 kg")
        self.assertEqual(result["business_rules"]["abattoir_window_label"], "80 kg+")
        self.assertEqual(result["business_rules"]["target_growth_label"], "0.500 kg/day target")
        self.assertEqual(by_id["PIG-1"]["litter_quality"], "Good")
        self.assertEqual(by_id["PIG-1"]["litter_survival_rate"], 0.9)
        self.assertEqual(by_id["PIG-2"]["readiness_bucket"], "Allocated")
        self.assertEqual(by_id["PIG-2"]["suggested_purpose"], "Already Allocated")
        self.assertEqual(by_id["PIG-2"]["existing_link"], "ORD-1")
        self.assertEqual(by_id["PIG-3"]["readiness_bucket"], "Retain / Breeding Candidate")
        self.assertEqual(by_id["PIG-3"]["suggested_purpose"], "Breeding Review")
        self.assertEqual(by_id["PIG-4"]["readiness_bucket"], "Growing")
        self.assertEqual(by_id["PIG-4"]["outlet_priority"], "Keep Growing")
        self.assertEqual(by_id["PIG-4"]["suggested_purpose"], "Grow Out")
        self.assertEqual(by_id["PIG-5"]["readiness_bucket"], "Exited")
        self.assertEqual(by_id["PIG-5"]["suggested_purpose"], "Closed")
        self.assertEqual(result["summary"]["buckets"]["Allocated"], 1)

    def test_allocation_readiness_can_use_supabase_input_rows(self):
        supabase_inputs = {
            "source": "supabase_canonical",
            "overview_rows": [{
                "Pig_ID": "PIG-1",
                "Tag_Number": "1",
                "Animal_Type": "Grower",
                "Sex": "Female",
                "Status": "Active",
                "On_Farm": "Yes",
                "Purpose": "Grow_Out",
                "Current_Pen_ID": "PEN-1",
                "Current_Weight_Kg": 62,
                "Last_Weight_Date": "2026-06-01",
                "Date_Of_Birth": "2026-02-01",
                "Age_Days": "124",
                "Litter_ID": "LIT-1",
            }],
            "pig_master_rows": [{
                "Pig_ID": "PIG-1",
                "Wean_Date": "2026-05-01",
                "Wean_Weight_Kg": "12",
            }],
            "weight_rows": [{
                "Pig_ID": "PIG-1",
                "Weight_Date": "2026-06-01",
                "Weight_Kg": "62",
            }],
            "sales_rows": [],
            "litter_rows": [{
                "Litter_ID": "LIT-1",
                "Born_Alive": "10",
                "Weaned_Count": "9",
                "Sow_Pig_ID": "SOW-1",
                "Sow_Tag_Number": "101",
                "Boar_Pig_ID": "BOAR-1",
                "Boar_Tag_Number": "201",
            }],
            "pen_lookup": {"PEN-1": {"pen_id": "PEN-1", "pen_name": "Grower Pen"}},
        }

        with patch.object(farm_supabase_read_service, "farm_supabase_reads_available", return_value=True), \
             patch.object(farm_supabase_read_service, "get_allocation_input_rows", return_value=supabase_inputs):
            result = pig_weights_service.get_pig_allocation_readiness(today=date(2026, 6, 4))

        self.assertTrue(result["success"])
        self.assertEqual(result["source"], "supabase_canonical")
        self.assertEqual(result["pigs"][0]["pig_id"], "PIG-1")
        self.assertEqual(result["pigs"][0]["current_pen_name"], "Grower Pen")
        self.assertEqual(result["pigs"][0]["litter_quality"], "Good")
        self.assertFalse(result["writes_to_sheets"])
        self.assertFalse(result["writes_to_supabase"])

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
        self.assertEqual(row["outlet_priority"], "Breeding Review")
        self.assertEqual(row["suggested_purpose"], "Breeding Review")
        self.assertIn("retention", row["suggested_purpose_reason"])

    def test_growth_class_bands_use_lifetime_average_daily_gain(self):
        cases = [
            ("PIG-EXTREME", "9.0", "100", "Extremely Slow"),
            ("PIG-SLOW", "15.0", "100", "Slow"),
            ("PIG-BELOW", "25.0", "100", "Below Target"),
            ("PIG-STEADY", "35.0", "100", "Steady"),
            ("PIG-GOOD", "60", "140", "Good"),
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

        self.assertEqual(by_id["PIG-EXTREME"]["outlet_priority"], "Livestock Sale")
        self.assertEqual(by_id["PIG-EXTREME"]["suggested_purpose"], "Livestock Sale")
        self.assertEqual(by_id["PIG-SLOW"]["outlet_priority"], "Livestock Sale")
        self.assertIn("livestock sale", by_id["PIG-SLOW"]["recommended_action"].lower())
        self.assertEqual(by_id["PIG-GOOD"]["outlet_priority"], "Meat Preorder")
        self.assertEqual(by_id["PIG-GOOD"]["suggested_purpose"], "Meat")

    def test_allocation_settings_can_be_overridden_without_ui_writes(self):
        overview_rows = [{
            "Pig_ID": "PIG-CUSTOM",
            "Tag_Number": "30",
            "Animal_Type": "Grower",
            "Sex": "Male",
            "Status": "Active",
            "On_Farm": "Yes",
            "Purpose": "Grow_Out",
            "Current_Pen_ID": "PEN-1",
            "Current_Weight_Kg": "72",
            "Last_Weight_Date": "2026-06-04",
            "Age_Days": "180",
        }]
        settings = dict(pig_weights_service.DEFAULT_ALLOCATION_SETTINGS)
        settings.update({
            "source": "test_override",
            "meat_target_min_kg": 65,
            "meat_target_max_kg": 75,
            "slaughter_target_min_kg": 90,
            "slaughter_target_max_kg": 105,
        })

        def fake_get_all_records(sheet_name):
            if sheet_name == "PIG_OVERVIEW":
                return overview_rows
            if sheet_name == "WEIGHT_LOG":
                return [{"Pig_ID": "PIG-CUSTOM", "Weight_Date": "2026-06-04", "Weight_Kg": "72"}]
            if sheet_name == "SALES_AVAILABILITY":
                return []
            if sheet_name == "PEN_REGISTER":
                return [{"Pen_ID": "PEN-1", "Pen_Name": "Grower Pen"}]
            if sheet_name == "LITTER_OVERVIEW":
                return []
            return []

        with patch.object(pig_weights_service, "get_all_records", side_effect=fake_get_all_records), \
                patch.object(pig_weights_service, "_allocation_settings", return_value=settings):
            result = pig_weights_service.get_pig_allocation_readiness(today=date(2026, 6, 4))

        row = result["pigs"][0]
        self.assertEqual(row["readiness_bucket"], "Meat Candidate")
        self.assertEqual(row["suggested_purpose"], "Meat")
        self.assertEqual(row["meat_target_min_kg"], 65)
        self.assertEqual(row["meat_target_max_kg"], 75)
        self.assertEqual(row["abattoir_target_min_kg"], 90)
        self.assertEqual(result["business_rules"]["source"], "test_override")
        self.assertEqual(result["business_rules"]["meat_window_label"], "65-<75 kg")
        self.assertFalse(result["writes_to_sheets"])
        self.assertFalse(result["writes_to_supabase"])

    def test_allocation_readiness_uses_pig_master_wean_fields_when_overview_omits_them(self):
        overview_rows = [{
            "Pig_ID": "PIG-WEANED",
            "Tag_Number": "40",
            "Animal_Type": "Weaner",
            "Sex": "Female",
            "Status": "Active",
            "On_Farm": "Yes",
            "Purpose": "Unknown",
            "Current_Pen_ID": "PEN-1",
            "Current_Weight_Kg": "12",
            "Last_Weight_Date": "2026-06-15",
            "Age_Days": "50",
            "Litter_ID": "LIT-1",
        }]
        master_rows = [{
            "Pig_ID": "PIG-WEANED",
            "Wean_Date": "2026-06-05",
            "Wean_Weight_Kg": "8.5",
        }]

        def fake_get_all_records(sheet_name):
            if sheet_name == "PIG_OVERVIEW":
                return overview_rows
            if sheet_name == "PIG_MASTER":
                return master_rows
            if sheet_name == "WEIGHT_LOG":
                return [{"Pig_ID": "PIG-WEANED", "Weight_Date": "2026-06-15", "Weight_Kg": "12"}]
            if sheet_name == "PEN_REGISTER":
                return [{"Pen_ID": "PEN-1", "Pen_Name": "Weaner Pen"}]
            return []

        with patch.object(pig_weights_service, "get_all_records", side_effect=fake_get_all_records):
            result = pig_weights_service.get_pig_allocation_readiness(today=date(2026, 6, 15))

        row = result["pigs"][0]
        self.assertEqual(row["wean_date"], "2026-06-05")
        self.assertEqual(row["wean_weight_kg"], 8.5)
        self.assertEqual(row["days_since_wean"], 10)
        self.assertEqual(row["post_wean_daily_gain_kg"], 0.35)

    def test_purpose_review_queue_filters_unknown_purpose_and_keeps_litter_focus(self):
        allocation_result = {
            "success": True,
            "generated_date": "2026-06-15",
            "business_rules": {"source": "code_defaults"},
            "pigs": [
                {
                    "pig_id": "PIG-UNKNOWN",
                    "tag_number": "11",
                    "litter_id": "LIT-1",
                    "status": "Active",
                    "on_farm": "Yes",
                    "purpose": "Unknown",
                    "readiness_bucket": "Needs Classification",
                    "readiness_reason": "Purpose is still unknown.",
                    "suggested_purpose": "Grow Out",
                    "suggested_purpose_reason": "Pig is active/on farm.",
                    "suggested_purpose_confidence": "Medium",
                },
                {
                    "pig_id": "PIG-CLASSIFIED",
                    "tag_number": "12",
                    "litter_id": "LIT-1",
                    "status": "Active",
                    "on_farm": "Yes",
                    "purpose": "Grow_Out",
                    "readiness_bucket": "Growing",
                    "suggested_purpose": "Grow Out",
                    "suggested_purpose_reason": "Keep growing.",
                    "suggested_purpose_confidence": "Medium",
                },
                {
                    "pig_id": "PIG-OTHER",
                    "tag_number": "13",
                    "litter_id": "LIT-2",
                    "status": "Active",
                    "on_farm": "Yes",
                    "purpose": "Unknown",
                    "readiness_bucket": "Needs Data",
                    "readiness_reason": "Missing weight.",
                    "suggested_purpose": "Needs Review",
                    "suggested_purpose_reason": "Complete missing data.",
                    "suggested_purpose_confidence": "Low",
                },
            ],
        }

        with patch.object(pig_weights_service, "get_pig_allocation_readiness", return_value=allocation_result):
            default_result = pig_weights_service.get_purpose_review_queue()
            litter_result = pig_weights_service.get_purpose_review_queue(litter_id="LIT-1")

        self.assertEqual([row["pig_id"] for row in default_result["pigs"]], ["PIG-UNKNOWN", "PIG-OTHER"])
        self.assertEqual(default_result["summary"]["needs_owner_decision"], 1)
        self.assertEqual(default_result["summary"]["needs_data"], 1)
        self.assertFalse(default_result["writes_to_sheets"])
        self.assertEqual(default_result["owner_agent"], "Herdmaster")
        by_id = {row["pig_id"]: row for row in litter_result["pigs"]}
        self.assertEqual(set(by_id), {"PIG-UNKNOWN", "PIG-CLASSIFIED"})
        self.assertEqual(by_id["PIG-UNKNOWN"]["proposed_purpose"], "Grow_Out")
        self.assertEqual(by_id["PIG-CLASSIFIED"]["review_status"], "classified")

    def test_apply_purpose_review_decisions_updates_only_purpose_notes_and_timestamp(self):
        pig_rows = [
            {
                "Pig_ID": "PIG-UNKNOWN",
                "Tag_Number": "11",
                "Litter_ID": "LIT-1",
                "Status": "Active",
                "On_Farm": "Yes",
                "Purpose": "Unknown",
                "General_Notes": "Existing note",
            }
        ]

        with patch.object(pig_weights_service, "get_all_records", return_value=pig_rows), \
                patch.object(pig_weights_service, "batch_update_rows_by_id", return_value=1) as mock_update:
            result, status_code = pig_weights_service.apply_purpose_review_decisions(
                [{"pig_id": "PIG-UNKNOWN", "purpose": "Grow_Out", "reason": "Herdmaster suggested grow out."}],
                changed_by="Owner",
                dry_run=False,
            )

        self.assertEqual(status_code, 200)
        self.assertTrue(result["success"])
        self.assertFalse(result["dry_run"])
        self.assertEqual(result["rows_updated"], 1)
        updates = mock_update.call_args.args[1]["PIG-UNKNOWN"]
        self.assertEqual(updates["Purpose"], "Grow_Out")
        self.assertIn("Updated_At", updates)
        self.assertIn("purpose review", updates["General_Notes"])
        self.assertIn("Unknown to Grow_Out", updates["General_Notes"])
        self.assertEqual(set(updates), {"Purpose", "Updated_At", "General_Notes"})

    def test_apply_purpose_review_decisions_blocks_reclassify_by_default(self):
        pig_rows = [{
            "Pig_ID": "PIG-DONE",
            "Status": "Active",
            "On_Farm": "Yes",
            "Purpose": "Grow_Out",
        }]

        with patch.object(pig_weights_service, "get_all_records", return_value=pig_rows), \
                patch.object(pig_weights_service, "batch_update_rows_by_id") as mock_update:
            result, status_code = pig_weights_service.apply_purpose_review_decisions(
                [{"pig_id": "PIG-DONE", "purpose": "Sale"}],
                dry_run=False,
            )

        self.assertEqual(status_code, 409)
        self.assertFalse(result["success"])
        self.assertIn("already has purpose", result["errors"][0])
        mock_update.assert_not_called()

    def test_purpose_review_recheck_returns_no_write_packet(self):
        allocation_result = {
            "success": True,
            "pigs": [{
                "pig_id": "PIG-1",
                "status": "Active",
                "on_farm": "Yes",
                "purpose": "Unknown",
                "readiness_bucket": "Needs Classification",
                "readiness_reason": "Purpose is still unknown.",
                "suggested_purpose": "Grow Out",
                "suggested_purpose_reason": "Pig is active/on farm.",
                "suggested_purpose_confidence": "Medium",
                "growth_reason": "Steady lifetime gain.",
                "litter_quality_reason": "Good litter survival.",
                "recommended_action": "Keep growing.",
            }],
        }

        with patch.object(pig_weights_service, "get_pig_allocation_readiness", return_value=allocation_result):
            result, status_code = pig_weights_service.build_purpose_review_recheck("PIG-1", "Why grow out?")

        self.assertEqual(status_code, 200)
        self.assertTrue(result["success"])
        self.assertEqual(result["owner_agent"], "Herdmaster")
        self.assertFalse(result["writes_to_sheets"])
        self.assertFalse(result["writes_to_supabase"])
        self.assertIn("Pig is active/on farm.", result["analysis_points"])


    def test_owner_weight_window_boundaries_include_80kg_plus_culls(self):
        cases = [
            ("PIG-LOW", "59.9", "Growing", "Before meat window", "Before abattoir window"),
            ("PIG-MEAT-MIN", "60", "Meat Candidate", "In meat window", "Before abattoir window"),
            ("PIG-MEAT-HIGH", "79.9", "Meat Candidate", "In meat window", "Before abattoir window"),
            ("PIG-ABATTOIR", "80", "Slaughter Candidate", "Past meat window", "In abattoir window"),
            ("PIG-HEAVY", "120", "Slaughter Candidate", "Past meat window", "In abattoir window"),
        ]
        overview_rows = [
            {
                "Pig_ID": pig_id,
                "Tag_Number": pig_id[-2:],
                "Animal_Type": "Finisher",
                "Sex": "Male",
                "Status": "Active",
                "On_Farm": "Yes",
                "Purpose": "Grow_Out",
                "Current_Pen_ID": "PEN-1",
                "Current_Weight_Kg": weight,
                "Last_Weight_Date": "2026-06-28",
                "Age_Days": "180",
            }
            for pig_id, weight, _bucket, _meat, _abattoir in cases
        ]

        def fake_get_all_records(sheet_name):
            if sheet_name == "PIG_OVERVIEW":
                return overview_rows
            if sheet_name == "WEIGHT_LOG":
                return [{"Pig_ID": pig_id, "Weight_Date": "2026-06-28", "Weight_Kg": weight} for pig_id, weight, *_ in cases]
            if sheet_name == "PEN_REGISTER":
                return [{"Pen_ID": "PEN-1", "Pen_Name": "Grower Pen"}]
            return []

        with patch.object(pig_weights_service, "get_all_records", side_effect=fake_get_all_records):
            result = pig_weights_service.get_pig_allocation_readiness(today=date(2026, 6, 28))

        by_id = {row["pig_id"]: row for row in result["pigs"]}
        self.assertEqual(result["business_rules"]["meat_window_label"], "60-<80 kg")
        self.assertEqual(result["business_rules"]["abattoir_window_label"], "80 kg+")
        for pig_id, _weight, bucket, meat_status, abattoir_status in cases:
            with self.subTest(pig_id=pig_id):
                self.assertEqual(by_id[pig_id]["readiness_bucket"], bucket)
                self.assertEqual(by_id[pig_id]["meat_window_status"], meat_status)
                self.assertEqual(by_id[pig_id]["abattoir_window_status"], abattoir_status)

    def test_meat_ready_stock_summary_values_fresh_and_stale_animals_without_feed_cost(self):
        allocation = {
            "success": True,
            "generated_date": "2026-06-28",
            "thresholds": {"fresh_weight_days": 14, "stale_weight_days": 30},
            "business_rules": {"meat_window_label": "60-<80 kg", "abattoir_window_label": "80 kg+"},
            "pigs": [
                {"pig_id": "PIG-MEAT", "tag_number": "1", "status": "Active", "on_farm": "Yes", "latest_weight_kg": 70, "days_since_weight": 10, "readiness_bucket": "Meat Candidate", "meat_window_status": "In meat window", "reserved_status": ""},
                {"pig_id": "PIG-CULL", "tag_number": "2", "status": "Active", "on_farm": "Yes", "latest_weight_kg": 120, "days_since_weight": 20, "readiness_bucket": "Slaughter Candidate", "abattoir_window_status": "In abattoir window", "reserved_status": ""},
                {"pig_id": "PIG-OLD", "tag_number": "3", "status": "Active", "on_farm": "Yes", "latest_weight_kg": 65, "days_since_weight": 40, "readiness_bucket": "Meat Candidate", "meat_window_status": "In meat window", "reserved_status": ""},
                {"pig_id": "PIG-RES", "tag_number": "4", "status": "Active", "on_farm": "Yes", "latest_weight_kg": 75, "days_since_weight": 3, "readiness_bucket": "Allocated", "reserved_status": "Reserved"},
            ],
        }
        prices = [
            {"product_type": "half_carcass", "price_unit": "per_kg", "price_amount": 130, "active": True, "source": "test_price_book"},
            {"product_type": "assisted_slaughter", "price_unit": "per_kg", "price_amount": 45, "active": True, "source": "test_price_book"},
        ]

        result = pig_weights_service.get_meat_ready_stock_summary(today=date(2026, 6, 28), allocation=allocation, price_entries=prices)
        by_id = {row["pig_id"]: row for row in result["pigs"]}

        self.assertTrue(result["success"])
        self.assertTrue(result["no_feed_cost_included"])
        self.assertFalse(result["sam_availability_enabled"])
        self.assertEqual(by_id["PIG-MEAT"]["estimated_value"], 9100)
        self.assertEqual(by_id["PIG-CULL"]["valuation_status"], "stale_weight_review")
        self.assertEqual(by_id["PIG-CULL"]["estimated_value"], 5400)
        self.assertEqual(by_id["PIG-OLD"]["valuation_status"], "not_valuation_ready")
        self.assertEqual(by_id["PIG-RES"]["category_key"], "excluded")

    def test_meat_ready_stock_summary_reports_missing_price_without_inventing_value(self):
        allocation = {
            "thresholds": {"fresh_weight_days": 14, "stale_weight_days": 30},
            "business_rules": {},
            "pigs": [{"pig_id": "PIG-MEAT", "tag_number": "1", "status": "Active", "on_farm": "Yes", "latest_weight_kg": 70, "days_since_weight": 2, "readiness_bucket": "Meat Candidate", "meat_window_status": "In meat window"}],
        }

        result = pig_weights_service.get_meat_ready_stock_summary(today=date(2026, 6, 28), allocation=allocation, price_entries=[])
        row = result["pigs"][0]

        self.assertEqual(row["valuation_status"], "pricing_not_configured")
        self.assertIsNone(row["estimated_value"])
        self.assertEqual(result["summary"]["pricing_not_configured_count"], 1)
class MeatPlanningServiceTests(unittest.TestCase):
    def test_meat_planning_groups_allocation_signals_without_writes(self):
        allocation_result = {
            "success": True,
            "generated_date": "2026-06-05",
            "business_rules": {"meat_window_label": "55-70 kg"},
            "thresholds": {"meat_target_min_kg": 55},
            "pigs": [
                {
                    "pig_id": "PIG-MEAT-NOW",
                    "tag_number": "1",
                    "planning_bucket": "",
                    "suggested_purpose": "Meat",
                    "outlet_priority": "Meat Preorder",
                    "meat_window_status": "In meat window",
                    "days_until_meat_ready": 0,
                    "estimated_meat_ready_date": "2026-06-05",
                    "estimated_abattoir_ready_date": "2026-07-01",
                    "days_until_abattoir_ready": 26,
                    "latest_weight_kg": 62,
                    "average_daily_gain_kg": 0.45,
                    "growth_class": "Good",
                },
                {
                    "pig_id": "PIG-MEAT-14",
                    "tag_number": "2",
                    "suggested_purpose": "Meat",
                    "outlet_priority": "Meat Preorder",
                    "meat_window_status": "Before meat window",
                    "days_until_meat_ready": 10,
                    "estimated_meat_ready_date": "2026-06-15",
                },
                {
                    "pig_id": "PIG-MEAT-30",
                    "tag_number": "3",
                    "suggested_purpose": "Meat",
                    "outlet_priority": "Meat Preorder",
                    "meat_window_status": "Before meat window",
                    "days_until_meat_ready": 25,
                    "estimated_meat_ready_date": "2026-06-30",
                },
                {
                    "pig_id": "PIG-MEAT-FUTURE",
                    "tag_number": "4",
                    "suggested_purpose": "Meat",
                    "outlet_priority": "Meat Preorder",
                    "meat_window_status": "Before meat window",
                    "days_until_meat_ready": 45,
                },
                {
                    "pig_id": "PIG-FALLBACK",
                    "tag_number": "5",
                    "suggested_purpose": "Abattoir Slaughter",
                    "outlet_priority": "Abattoir Slaughter",
                    "meat_window_status": "Past meat window",
                    "days_until_meat_ready": 0,
                },
                {
                    "pig_id": "PIG-GROWING",
                    "tag_number": "6",
                    "suggested_purpose": "Grow Out",
                    "outlet_priority": "Keep Growing",
                    "meat_window_status": "Before meat window",
                    "days_until_meat_ready": 60,
                },
            ],
        }

        with patch.object(pig_weights_service, "get_pig_allocation_readiness", return_value=allocation_result):
            result = pig_weights_service.get_meat_planning_summary(today=date(2026, 6, 5))

        by_id = {row["pig_id"]: row for row in result["pigs"]}
        self.assertTrue(result["success"])
        self.assertEqual(result["source"], "pig_allocation_readiness")
        self.assertFalse(result["writes_to_sheets"])
        self.assertFalse(result["writes_to_supabase"])
        self.assertEqual(by_id["PIG-MEAT-NOW"]["planning_bucket"], "ready_now")
        self.assertEqual(by_id["PIG-MEAT-14"]["planning_bucket"], "next_14_days")
        self.assertEqual(by_id["PIG-MEAT-30"]["planning_bucket"], "next_30_days")
        self.assertEqual(by_id["PIG-MEAT-FUTURE"]["planning_bucket"], "future")
        self.assertEqual(by_id["PIG-FALLBACK"]["planning_bucket"], "fallback_abattoir")
        self.assertNotIn("PIG-GROWING", by_id)
        self.assertEqual(result["summary"]["meat_pipeline_count"], 4)
        self.assertEqual(result["summary"]["minimum_preorder_needed_now"], 1)
        self.assertEqual(result["summary"]["minimum_preorder_needed_30_days"], 3)
        self.assertEqual(result["summary"]["fallback_abattoir"], 1)


if __name__ == "__main__":
    unittest.main()
