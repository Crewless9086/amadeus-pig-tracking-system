import unittest
from unittest.mock import patch

from modules.pig_weights import mating_service


HEADERS = [
    "Mating_ID",
    "Sow_Pig_ID",
    "Sow_Tag_Number",
    "Boar_Pig_ID",
    "Boar_Tag_Number",
    "Mating_Date",
    "Mating_Method",
    "Exposure_Group",
    "Expected_Pregnancy_Check_Date",
    "Pregnancy_Check_Date",
    "Pregnancy_Check_Result",
    "Expected_Farrowing_Date",
    "Actual_Farrowing_Date",
    "Mating_Status",
    "Outcome",
    "Linked_Litter_ID",
    "Days_Since_Mating",
    "Service_Notes",
    "Created_At",
    "Updated_At",
]


def mating_row(**overrides):
    values = {
        "Mating_ID": "MAT-1",
        "Sow_Pig_ID": "PIG-SOW-1",
        "Pregnancy_Check_Result": "Pregnant",
        "Mating_Status": "Confirmed_Pregnant",
        "Outcome": "Pregnant",
    }
    values.update(overrides)
    return [values.get(header, "") for header in HEADERS]


class MatingServiceTests(unittest.TestCase):
    def test_mark_not_pregnant_updates_confirmed_mating(self):
        with patch.object(mating_service, "get_all_values", return_value=[HEADERS, mating_row()]), \
             patch.object(mating_service, "update_row_by_first_column_match") as update_row:

            result = mating_service.mark_not_pregnant("MAT-1", "", "Tester")

        self.assertTrue(result["success"])
        self.assertFalse(result["movement_logged"])
        updated = update_row.call_args.args[2]
        by_header = dict(zip(HEADERS, updated))
        self.assertEqual(by_header["Pregnancy_Check_Result"], "Not_Pregnant")
        self.assertEqual(by_header["Mating_Status"], "Repeat_Service")
        self.assertEqual(by_header["Outcome"], "Repeat_Required")
        self.assertTrue(by_header["Updated_At"])

    def test_mark_not_pregnant_blocks_non_confirmed_mating(self):
        with patch.object(
            mating_service,
            "get_all_values",
            return_value=[HEADERS, mating_row(Mating_Status="Open")],
        ):
            with self.assertRaisesRegex(ValueError, "Only Confirmed_Pregnant"):
                mating_service.mark_not_pregnant("MAT-1", "", "Tester")

    def test_mark_not_pregnant_blocks_linked_litter(self):
        with patch.object(
            mating_service,
            "get_all_values",
            return_value=[HEADERS, mating_row(Linked_Litter_ID="LIT-1")],
        ):
            with self.assertRaisesRegex(ValueError, "litter is already linked"):
                mating_service.mark_not_pregnant("MAT-1", "", "Tester")

    def test_mark_not_pregnant_blocks_actual_farrowing_date(self):
        with patch.object(
            mating_service,
            "get_all_values",
            return_value=[HEADERS, mating_row(Actual_Farrowing_Date="19 May 2026")],
        ):
            with self.assertRaisesRegex(ValueError, "actual farrowing"):
                mating_service.mark_not_pregnant("MAT-1", "", "Tester")

    def test_mark_not_pregnant_can_move_to_non_farrowing_pen(self):
        with patch.object(mating_service, "get_all_values", return_value=[HEADERS, mating_row()]), \
             patch.object(mating_service, "update_row_by_first_column_match"), \
             patch.object(
                 mating_service,
                 "_get_pen_lookup",
                 return_value={"PEN-SERVICE": {"pen_id": "PEN-SERVICE", "pen_type": "Sow"}},
             ), \
             patch.object(
                 mating_service,
                 "_get_pig_lookup",
                 return_value={"PIG-SOW-1": {"Current_Pen_ID": "PEN-FARROW"}},
             ), \
             patch.object(mating_service, "_write_movement_if_needed", return_value=True) as move:

            result = mating_service.mark_not_pregnant("MAT-1", "PEN-SERVICE", "Tester")

        self.assertTrue(result["movement_logged"])
        move.assert_called_once()
        self.assertEqual(move.call_args.kwargs["reason"], "Moved for repeat service")

    def test_mark_not_pregnant_blocks_farrowing_target_pen(self):
        with patch.object(mating_service, "get_all_values", return_value=[HEADERS, mating_row()]), \
             patch.object(
                 mating_service,
                 "_get_pen_lookup",
                 return_value={"PEN-FARROW": {"pen_id": "PEN-FARROW", "pen_type": "Farrowing"}},
             ):

            with self.assertRaisesRegex(ValueError, "must not be a Farrowing pen"):
                mating_service.mark_not_pregnant("MAT-1", "PEN-FARROW", "Tester")


if __name__ == "__main__":
    unittest.main()
