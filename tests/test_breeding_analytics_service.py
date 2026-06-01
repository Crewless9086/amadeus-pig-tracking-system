import unittest
from unittest.mock import patch

from modules.pig_weights import mating_service


class BreedingAnalyticsServiceTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
