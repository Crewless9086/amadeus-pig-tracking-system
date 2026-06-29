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
    def test_pen_lookup_prefers_supabase_read_service(self):
        with patch.object(mating_service.farm_supabase_read_service, "farm_supabase_reads_available", return_value=True), \
             patch.object(mating_service.farm_supabase_read_service, "get_pens", return_value=[{
                 "pen_id": "PEN-FARROW",
                 "pen_name": "Farrowing Pen",
                 "pen_type": "Farrowing",
             }]) as read_pens, \
             patch.object(mating_service, "get_all_records", side_effect=AssertionError("Sheets should not be read")):
            result = mating_service._get_pen_lookup()

        self.assertEqual(result["PEN-FARROW"]["pen_name"], "Farrowing Pen")
        self.assertEqual(result["PEN-FARROW"]["pen_type"], "Farrowing")
        read_pens.assert_called_once()

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

    def test_mark_not_pregnant_dry_run_does_not_write(self):
        with patch.object(mating_service, "get_all_values", return_value=[HEADERS, mating_row()]), \
             patch.object(mating_service, "update_row_by_first_column_match") as update_row, \
             patch.object(mating_service, "_write_movement_if_needed") as move:

            result = mating_service.mark_not_pregnant("MAT-1", "", "Tester", dry_run=True)

        self.assertTrue(result["success"])
        self.assertTrue(result["dry_run"])
        self.assertFalse(result["movement_logged"])
        self.assertEqual(result["planned_updates"]["Pregnancy_Check_Result"], "Not_Pregnant")
        self.assertEqual(result["planned_updates"]["Mating_Status"], "Repeat_Service")
        self.assertEqual(result["planned_updates"]["Outcome"], "Repeat_Required")
        update_row.assert_not_called()
        move.assert_not_called()

    def test_mark_not_pregnant_dry_run_reports_planned_movement_without_writing(self):
        with patch.object(mating_service, "get_all_values", return_value=[HEADERS, mating_row()]), \
             patch.object(mating_service, "update_row_by_first_column_match") as update_row, \
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
             patch.object(mating_service, "_write_movement_if_needed") as move:

            result = mating_service.mark_not_pregnant("MAT-1", "PEN-SERVICE", "Tester", dry_run=True)

        self.assertTrue(result["dry_run"])
        self.assertTrue(result["movement_planned"])
        self.assertEqual(result["current_pen_id"], "PEN-FARROW")
        self.assertEqual(result["target_pen_id"], "PEN-SERVICE")
        update_row.assert_not_called()
        move.assert_not_called()

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

    def test_save_new_mating_prefers_supabase_insert(self):
        cleaned = {
            "sow_pig_id": "PIG-SOW-1",
            "boar_pig_id": "PIG-BOAR-1",
            "mating_date": "2026-06-01",
            "mating_method": "Natural",
            "exposure_group": "A",
            "service_notes": "Observed",
            "sow_move_to_pen_id": "",
            "boar_move_to_pen_id": "",
        }
        pig_lookup = {
            "PIG-SOW-1": {"Tag_Number": "S1", "Current_Pen_ID": "PEN-1"},
            "PIG-BOAR-1": {"Tag_Number": "B1", "Current_Pen_ID": "PEN-2"},
        }

        with patch.object(mating_service.mating_supabase_write, "supabase_mating_writes_available", return_value=True), \
             patch.object(mating_service, "generate_mating_id", return_value="MAT-NEW"), \
             patch.object(mating_service, "_get_pig_lookup", return_value=pig_lookup), \
             patch.object(mating_service.mating_supabase_write, "insert_mating") as insert_mating, \
             patch.object(mating_service, "append_row") as append_row:
            result = mating_service.save_new_mating(cleaned)

        self.assertTrue(result["success"])
        self.assertEqual(result["mating_id"], "MAT-NEW")
        insert_mating.assert_called_once()
        append_row.assert_not_called()

    def test_write_movement_prefers_supabase_location_event(self):
        with patch.object(mating_service.mating_supabase_write, "supabase_mating_writes_available", return_value=True), \
             patch.object(mating_service, "generate_move_log_id", return_value="MOV-1"), \
             patch.object(mating_service.mating_supabase_write, "insert_location_event", return_value=True) as insert_event, \
             patch.object(mating_service, "append_row") as append_row:
            result = mating_service._write_movement_if_needed(
                pig_id="PIG-1",
                current_pen_id="PEN-1",
                target_pen_id="PEN-2",
                move_date="2026-06-01",
                reason="Moved during mating log",
                moved_by="Tester",
            )

        self.assertTrue(result)
        insert_event.assert_called_once()
        append_row.assert_not_called()

    def test_assume_pregnant_prefers_supabase_update_and_movement(self):
        row = {
            "Mating_ID": "MAT-1",
            "Sow_Pig_ID": "PIG-SOW-1",
            "Mating_Status": "Open",
        }
        with patch.object(mating_service.mating_supabase_write, "supabase_mating_writes_available", return_value=True), \
             patch.object(mating_service.mating_supabase_write, "get_mating_sheet_row", return_value=row), \
             patch.object(mating_service.mating_supabase_write, "update_mating_fields", return_value=1) as update_mating, \
             patch.object(mating_service, "_get_pen_lookup", return_value={"PEN-FARROW": {"pen_type": "Farrowing"}}), \
             patch.object(mating_service, "_get_pig_lookup", return_value={"PIG-SOW-1": {"Current_Pen_ID": "PEN-1"}}), \
             patch.object(mating_service, "_write_movement_if_needed", return_value=True) as move, \
             patch.object(mating_service, "get_all_values") as get_sheet:
            result = mating_service.assume_pregnant("MAT-1", "PEN-FARROW", "Tester")

        self.assertTrue(result["success"])
        self.assertTrue(result["source"]["writes_to_supabase"])
        update_mating.assert_called_once()
        move.assert_called_once()
        get_sheet.assert_not_called()

    def test_mark_not_pregnant_prefers_supabase_update(self):
        row = {
            "Mating_ID": "MAT-1",
            "Sow_Pig_ID": "PIG-SOW-1",
            "Mating_Status": "Confirmed_Pregnant",
            "Linked_Litter_ID": "",
            "Actual_Farrowing_Date": "",
        }
        with patch.object(mating_service.mating_supabase_write, "supabase_mating_writes_available", return_value=True), \
             patch.object(mating_service.mating_supabase_write, "get_mating_sheet_row", return_value=row), \
             patch.object(mating_service.mating_supabase_write, "update_mating_fields", return_value=1) as update_mating, \
             patch.object(mating_service, "_get_pen_lookup", return_value={}), \
             patch.object(mating_service, "update_row_by_first_column_match") as sheet_update:
            result = mating_service.mark_not_pregnant("MAT-1", "", "Tester")

        self.assertTrue(result["success"])
        self.assertTrue(result["source"]["writes_to_supabase"])
        update_mating.assert_called_once()
        sheet_update.assert_not_called()


if __name__ == "__main__":
    unittest.main()
