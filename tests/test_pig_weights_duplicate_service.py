import unittest
from datetime import date
from unittest.mock import patch

from modules.pig_weights import pig_weights_service


class WeightDuplicateServiceTests(unittest.TestCase):
    def test_save_weight_blocks_same_pig_same_date_without_confirmation(self):
        rows = [
            {
                "Weight_Log_ID": "WGT-1",
                "Pig_ID": "PIG-1",
                "Weight_Date": "20 May 2026",
                "Weight_Kg": "42",
                "Weighed_By": "Tester",
                "Condition_Notes": "Existing",
            }
        ]

        with patch.object(pig_weights_service, "get_all_records", return_value=rows), \
             patch.object(pig_weights_service, "append_row") as append_row:
            result = pig_weights_service.save_weight_entry({
                "pig_id": "PIG-1",
                "weight_date": date(2026, 5, 20),
                "weight_kg": 43,
                "condition_notes": "",
                "weighed_by": "WebApp",
                "allow_duplicate": False,
            })

        self.assertFalse(result["success"])
        self.assertTrue(result["duplicate_weight"])
        self.assertEqual(result["existing"]["weight_log_id"], "WGT-1")
        self.assertEqual(result["existing"]["weight_kg"], 42.0)
        append_row.assert_not_called()

    def test_save_weight_allows_confirmed_duplicate(self):
        with patch.object(pig_weights_service, "append_row") as append_row, \
             patch.object(pig_weights_service, "get_latest_weight_for_pig", return_value={}):
            result = pig_weights_service.save_weight_entry({
                "pig_id": "PIG-1",
                "weight_date": date(2026, 5, 20),
                "weight_kg": 43,
                "condition_notes": "",
                "weighed_by": "WebApp",
                "allow_duplicate": True,
            })

        self.assertTrue(result["success"])
        append_row.assert_called_once()


if __name__ == "__main__":
    unittest.main()
