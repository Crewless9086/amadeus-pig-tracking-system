import unittest
from datetime import date
from unittest.mock import patch

from modules.pig_weights import pig_weights_service


PIG_MASTER_HEADERS = [
    "Pig_ID",
    "Tag_Number",
    "Pig_Name",
    "Status",
    "On_Farm",
    "Animal_Type",
    "Sex",
    "Date_Of_Birth",
    "Birth_Month",
    "Birth_Year",
    "Breed_Type",
    "Colour_Markings",
    "Litter_ID",
    "Litter_Size_Born",
    "Litter_Size_Weaned",
    "Mother_Pig_ID",
    "Father_Pig_ID",
    "Mother_Tag_Number",
    "Father_Tag_Number",
    "Maternal_Line",
    "Paternal_Line",
    "Purpose",
    "Current_Stage",
    "Current_Pen_ID",
    "Source",
    "Acquisition_Date",
    "Birth_Weight_Kg",
    "Wean_Date",
    "Wean_Weight_Kg",
    "Exit_Date",
    "Exit_Reason",
    "Exit_Order_ID",
    "Carcass_Weight_Kg",
    "General_Notes",
    "Created_At",
    "Updated_At",
]


class LitterPigletCreationTests(unittest.TestCase):
    def test_litter_generated_piglets_default_purpose_unknown(self):
        with patch.object(pig_weights_service, "get_all_records", return_value=[]), \
             patch.object(pig_weights_service, "generate_pig_id", side_effect=["PIG-1", "PIG-2"]), \
             patch.object(pig_weights_service, "append_row") as append_row:

            created_count = pig_weights_service._create_pig_rows_for_litter(
                litter_id="LIT-1",
                mother_pig_id="PIG-MOTHER",
                father_pig_id="PIG-FATHER",
                mother_tag="M1",
                father_tag="B1",
                farrowing_date=date(2026, 5, 19),
                total_born=2,
                current_pen_id="PEN-001",
            )

        self.assertEqual(created_count, 2)
        self.assertEqual(append_row.call_count, 2)

        first_row = append_row.call_args_list[0].args[1]
        by_header = dict(zip(PIG_MASTER_HEADERS, first_row))
        self.assertEqual(by_header["Purpose"], "Unknown")
        self.assertEqual(by_header["Animal_Type"], "Piglet")
        self.assertEqual(by_header["Status"], "Active")
        self.assertEqual(by_header["On_Farm"], "Yes")
        self.assertEqual(by_header["Source"], "Born_on_Farm")

    def test_litter_generated_piglets_are_not_duplicated_for_existing_litter(self):
        existing_rows = [{"Litter_ID": "LIT-1"}]

        with patch.object(pig_weights_service, "get_all_records", return_value=existing_rows), \
             patch.object(pig_weights_service, "append_row") as append_row:

            created_count = pig_weights_service._create_pig_rows_for_litter(
                litter_id="LIT-1",
                mother_pig_id="PIG-MOTHER",
                father_pig_id="PIG-FATHER",
                mother_tag="M1",
                father_tag="B1",
                farrowing_date=date(2026, 5, 19),
                total_born=2,
                current_pen_id="PEN-001",
            )

        self.assertEqual(created_count, 0)
        append_row.assert_not_called()


class LitterAttentionActionTests(unittest.TestCase):
    def test_mark_litter_weaned_updates_litter_and_active_piglets(self):
        pig_rows = [
            {
                "Pig_ID": "PIG-1",
                "Litter_ID": "LIT-1",
                "Status": "Active",
                "On_Farm": "Yes",
            },
            {
                "Pig_ID": "PIG-2",
                "Litter_ID": "LIT-1",
                "Status": "Active",
                "On_Farm": "Yes",
            },
            {
                "Pig_ID": "PIG-3",
                "Litter_ID": "LIT-1",
                "Status": "Sold",
                "On_Farm": "No",
            },
        ]
        litter_values = [
            [
                "Litter_ID",
                "Farrowing_Date",
                "Sow_Pig_ID",
                "Boar_Pig_ID",
                "Weaned_Count",
                "Wean_Date",
                "Updated_At",
            ],
            ["LIT-1", "01 May 2026", "SOW-1", "BOAR-1", "", "", ""],
        ]

        with patch.object(pig_weights_service, "get_all_records", return_value=pig_rows), \
             patch.object(pig_weights_service, "get_all_values", return_value=litter_values), \
             patch.object(pig_weights_service, "update_row_by_first_column_match", return_value=2) as update_litter, \
             patch.object(pig_weights_service, "batch_update_rows_by_id", return_value=2) as update_pigs:

            result, status_code = pig_weights_service.mark_litter_weaned(
                "LIT-1",
                "2026-05-26",
                changed_by="test",
            )

        self.assertEqual(status_code, 200)
        self.assertTrue(result["success"])
        self.assertEqual(result["weaned_count"], 2)
        self.assertEqual(result["pig_rows_updated"], 2)

        litter_row = update_litter.call_args.args[2]
        self.assertEqual(litter_row[4], 2)
        self.assertEqual(litter_row[5], "26 May 2026")

        update_map = update_pigs.call_args.args[1]
        self.assertEqual(set(update_map.keys()), {"PIG-1", "PIG-2"})
        self.assertEqual(update_map["PIG-1"]["Litter_Size_Weaned"], 2)
        self.assertEqual(update_map["PIG-1"]["Wean_Date"], "26 May 2026")

    def test_mark_litter_weaned_requires_active_on_farm_piglets(self):
        pig_rows = [
            {
                "Pig_ID": "PIG-1",
                "Litter_ID": "LIT-1",
                "Status": "Sold",
                "On_Farm": "No",
            }
        ]

        with patch.object(pig_weights_service, "get_all_records", return_value=pig_rows), \
             patch.object(pig_weights_service, "get_all_values") as get_values, \
             patch.object(pig_weights_service, "batch_update_rows_by_id") as update_pigs:

            result, status_code = pig_weights_service.mark_litter_weaned("LIT-1", "2026-05-26")

        self.assertEqual(status_code, 409)
        self.assertFalse(result["success"])
        get_values.assert_not_called()
        update_pigs.assert_not_called()


class PigLifecycleOutcomeTests(unittest.TestCase):
    def test_mark_pig_death_or_removal_updates_active_on_farm_pig(self):
        pig_rows = [
            {
                "Pig_ID": "PIG-1",
                "Status": "Active",
                "On_Farm": "Yes",
                "Litter_ID": "LIT-1",
                "General_Notes": "Existing note",
            }
        ]

        with patch.object(pig_weights_service, "get_all_records", return_value=pig_rows), \
             patch.object(pig_weights_service, "batch_update_rows_by_id", return_value=1) as update_pigs:

            result, status_code = pig_weights_service.mark_pig_death_or_removal(
                pig_id="PIG-1",
                event_date_value="2026-06-01",
                reason="Died",
                changed_by="Tester",
                notes="Found during morning check.",
            )

        self.assertEqual(status_code, 200)
        self.assertTrue(result["success"])
        self.assertEqual(result["status"], "Dead")
        self.assertEqual(result["on_farm"], "No")
        self.assertEqual(result["exit_date"], "2026-06-01")
        self.assertEqual(result["exit_reason"], "Died")

        update_map = update_pigs.call_args.args[1]
        self.assertEqual(set(update_map.keys()), {"PIG-1"})
        updates = update_map["PIG-1"]
        self.assertEqual(updates["Status"], "Dead")
        self.assertEqual(updates["On_Farm"], "No")
        self.assertEqual(updates["Exit_Date"], "01 Jun 2026")
        self.assertEqual(updates["Exit_Reason"], "Died")
        self.assertIn("Existing note", updates["General_Notes"])
        self.assertIn("Found during morning check.", updates["General_Notes"])

    def test_mark_pig_death_or_removal_blocks_terminal_or_off_farm_pig(self):
        pig_rows = [
            {
                "Pig_ID": "PIG-1",
                "Status": "Sold",
                "On_Farm": "No",
            }
        ]

        with patch.object(pig_weights_service, "get_all_records", return_value=pig_rows), \
             patch.object(pig_weights_service, "batch_update_rows_by_id") as update_pigs:

            result, status_code = pig_weights_service.mark_pig_death_or_removal(
                pig_id="PIG-1",
                event_date_value="2026-06-01",
                reason="Died",
                changed_by="Tester",
            )

        self.assertEqual(status_code, 409)
        self.assertFalse(result["success"])
        update_pigs.assert_not_called()

    def test_mark_pig_death_or_removal_validates_reason(self):
        with patch.object(pig_weights_service, "get_all_records") as get_records:
            result, status_code = pig_weights_service.mark_pig_death_or_removal(
                pig_id="PIG-1",
                event_date_value="2026-06-01",
                reason="Slaughtered",
                changed_by="Tester",
            )

        self.assertEqual(status_code, 400)
        self.assertFalse(result["success"])
        get_records.assert_not_called()


if __name__ == "__main__":
    unittest.main()
