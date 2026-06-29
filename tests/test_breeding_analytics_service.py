import unittest
from unittest.mock import patch

from modules.pig_weights import mating_service


class BreedingAnalyticsServiceTests(unittest.TestCase):
    def setUp(self):
        self.supabase_availability_patch = patch.object(
            mating_service.farm_supabase_read_service,
            "farm_supabase_reads_available",
            return_value=False,
        )
        self.supabase_availability_patch.start()

    def tearDown(self):
        self.supabase_availability_patch.stop()

    def test_breeding_analytics_groups_mating_and_litter_metrics(self):
        mating_rows = [
            {
                "mating_id": "MAT-1",
                "sow_pig_id": "SOW-1",
                "sow_tag_number": "10",
                "boar_pig_id": "BOAR-1",
                "boar_tag_number": "3",
                "pregnancy_check_result": "Pregnant",
                "mating_status": "Farrowed",
                "outcome": "Farrowed",
                "linked_litter_id": "LIT-1",
                "is_open": "No",
            },
            {
                "mating_id": "MAT-2",
                "sow_pig_id": "SOW-1",
                "sow_tag_number": "10",
                "boar_pig_id": "BOAR-1",
                "boar_tag_number": "3",
                "pregnancy_check_result": "Not_Pregnant",
                "mating_status": "Repeat_Service",
                "outcome": "Repeat_Required",
                "linked_litter_id": "",
                "is_open": "No",
            },
        ]
        litter_rows = [
            {
                "Litter_ID": "LIT-1",
                "Sow_Pig_ID": "SOW-1",
                "Sow_Tag_Number": "10",
                "Boar_Pig_ID": "BOAR-1",
                "Boar_Tag_Number": "3",
                "Born_Alive": "8",
                "Weaned_Count": "6",
            }
        ]

        with patch.object(mating_service, "get_mating_overview", return_value=mating_rows), \
             patch.object(mating_service, "get_all_records", return_value=litter_rows):
            result = mating_service.get_breeding_analytics()

        self.assertTrue(result["success"])
        self.assertEqual(result["mode"], "read_only")
        self.assertFalse(result["source"]["writes_to_google_sheets"])
        self.assertEqual(result["summary"]["mating_count"], 2)
        self.assertEqual(result["summary"]["litter_count"], 1)

        sow = result["sows"][0]
        self.assertEqual(sow["pig_id"], "SOW-1")
        self.assertEqual(sow["mating_count"], 2)
        self.assertEqual(sow["confirmed_pregnant_count"], 1)
        self.assertEqual(sow["repeat_service_count"], 1)
        self.assertEqual(sow["farrowed_count"], 1)
        self.assertEqual(sow["litter_count"], 1)
        self.assertEqual(sow["average_born_alive"], 8.0)
        self.assertEqual(sow["average_weaned"], 6.0)
        self.assertEqual(sow["survival_pct"], 75.0)

    def test_breeding_animal_detail_returns_matings_litters_and_flags(self):
        analytics = {
            "success": True,
            "mode": "read_only",
            "summary": {},
            "sows": [{
                "pig_id": "SOW-1",
                "tag_number": "10",
                "mating_count": 1,
                "confirmed_pregnant_count": 1,
                "repeat_service_count": 0,
                "farrowed_count": 1,
                "open_count": 0,
                "litter_count": 1,
                "born_alive_total": 8,
                "weaned_total": 0,
                "average_born_alive": 8.0,
                "average_weaned": 0,
                "survival_pct": 0,
            }],
            "boars": [],
        }
        mating_rows = [
            {
                "mating_id": "MAT-1",
                "sow_pig_id": "SOW-1",
                "sow_tag_number": "10",
                "boar_pig_id": "BOAR-1",
                "boar_tag_number": "3",
                "mating_date": "2026-01-01",
                "pregnancy_check_result": "",
                "mating_status": "Farrowed",
                "outcome": "Farrowed",
                "linked_litter_id": "",
                "expected_farrowing_date": "2026-04-25",
                "actual_farrowing_date": "",
                "is_open": "Yes",
                "is_overdue_check": "Yes",
                "is_overdue_farrowing": "No",
            }
        ]
        litter_rows = [
            {
                "Litter_ID": "LIT-1",
                "Farrowing_Date": "2026-04-24",
                "Sow_Pig_ID": "SOW-1",
                "Sow_Tag_Number": "10",
                "Boar_Pig_ID": "BOAR-1",
                "Boar_Tag_Number": "3",
                "Born_Alive": "8",
                "Weaned_Count": "",
                "Active_Pig_Count": "8",
                "Exited_Pig_Count": "0",
                "Average_Current_Weight_Kg": "4.5",
                "Pig_Master_Row_Count": "7",
                "Litter_Status": "Active",
                "Needs_Attention": "Yes",
                "Attention_Reason": "Piglets need tag numbers",
            }
        ]

        with patch.object(mating_service, "get_breeding_analytics", return_value=analytics), \
             patch.object(mating_service, "get_mating_overview", return_value=mating_rows), \
             patch.object(mating_service, "get_all_records", return_value=litter_rows):
            result, status_code = mating_service.get_breeding_animal_detail("SOW-1")

        self.assertEqual(status_code, 200)
        self.assertTrue(result["success"])
        self.assertEqual(result["mode"], "read_only")
        self.assertEqual(result["animal_type"], "sow")
        self.assertEqual(result["animal"]["pig_id"], "SOW-1")
        self.assertEqual(len(result["matings"]), 1)
        self.assertEqual(len(result["litters"]), 1)
        self.assertIn("Pregnancy check overdue", result["data_quality"]["flags"])
        self.assertIn("Missing weaned count", result["data_quality"]["flags"])
        self.assertIn("Pig records do not match born alive", result["data_quality"]["flags"])
        self.assertIn("Piglets need tag numbers", result["data_quality"]["flags"])
        self.assertFalse(result["source"]["writes_to_google_sheets"])

    def test_breeding_animal_detail_missing_returns_404(self):
        analytics = {
            "success": True,
            "mode": "read_only",
            "summary": {},
            "sows": [],
            "boars": [],
        }

        with patch.object(mating_service, "get_breeding_analytics", return_value=analytics):
            result, status_code = mating_service.get_breeding_animal_detail("PIG-MISSING")

        self.assertEqual(status_code, 404)
        self.assertFalse(result["success"])
        self.assertIn("not found", result["errors"][0])


if __name__ == "__main__":
    unittest.main()
