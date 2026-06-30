import unittest
from datetime import date
from unittest.mock import patch

from modules.pig_weights import pig_weights_service
from modules.pig_weights.pig_weights_utils import format_date_for_json


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

    def test_litter_generated_piglets_keep_stillborn_rows_as_dead_history(self):
        with patch.object(pig_weights_service, "get_all_records", return_value=[]), \
             patch.object(pig_weights_service, "generate_pig_id", side_effect=["PIG-1", "PIG-2", "PIG-3"]), \
             patch.object(pig_weights_service, "append_row") as append_row:

            created_count = pig_weights_service._create_pig_rows_for_litter(
                litter_id="LIT-1",
                mother_pig_id="PIG-MOTHER",
                father_pig_id="PIG-FATHER",
                mother_tag="M1",
                father_tag="B1",
                farrowing_date=date(2026, 5, 19),
                total_born=3,
                current_pen_id="PEN-001",
                born_alive=2,
                stillborn_count=1,
            )

        self.assertEqual(created_count, 3)
        self.assertEqual(append_row.call_count, 3)

        live_rows = [
            dict(zip(PIG_MASTER_HEADERS, call.args[1]))
            for call in append_row.call_args_list[:2]
        ]
        stillborn_row = dict(zip(PIG_MASTER_HEADERS, append_row.call_args_list[2].args[1]))

        for row in live_rows:
            self.assertEqual(row["Status"], "Active")
            self.assertEqual(row["On_Farm"], "Yes")
            self.assertEqual(row["Exit_Date"], "")
            self.assertEqual(row["Exit_Reason"], "")

        self.assertEqual(stillborn_row["Status"], "Dead")
        self.assertEqual(stillborn_row["On_Farm"], "No")
        self.assertEqual(stillborn_row["Exit_Date"], "19 May 2026")
        self.assertEqual(stillborn_row["Exit_Reason"], "Stillborn")
        self.assertIn("Stillborn recorded", stillborn_row["General_Notes"])

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

    def test_save_new_litter_prefers_supabase_transaction(self):
        cleaned_data = {
            "mating_id": "",
            "mother_pig_id": "PIG-MOTHER",
            "father_pig_id": "PIG-FATHER",
            "current_pen_id": "PEN-001",
            "farrowing_date": date(2026, 5, 19),
            "total_born": 3,
            "born_alive": 2,
            "stillborn_count": 1,
            "mummified_count": 0,
            "male_count": 1,
            "female_count": 1,
            "fostered_in_count": None,
            "fostered_out_count": None,
            "weaned_count": None,
            "wean_date": None,
            "average_wean_weight_kg": None,
            "notes": "Strong litter.",
        }
        parent_rows = [
            {"Pig_ID": "PIG-MOTHER", "Tag_Number": "M1", "Status": "Active", "On_Farm": "Yes"},
            {"Pig_ID": "PIG-FATHER", "Tag_Number": "B1", "Status": "Active", "On_Farm": "Yes"},
        ]

        with patch.object(pig_weights_service.farm_supabase_read_service, "farm_supabase_reads_available", return_value=True), \
             patch.object(pig_weights_service.farm_supabase_read_service, "get_pig_master_rows_by_ids", return_value=parent_rows) as read_parents, \
             patch.object(pig_weights_service.farm_supabase_write_service, "farm_supabase_writes_available", return_value=True), \
             patch.object(pig_weights_service.farm_supabase_write_service, "create_litter_with_generated_piglets", return_value={"pig_rows_created": 3}) as create_litter, \
             patch.object(pig_weights_service, "generate_litter_id", return_value="LIT-NEW"), \
             patch.object(pig_weights_service, "generate_pig_id", side_effect=["PIG-1", "PIG-2", "PIG-3"]), \
             patch.object(pig_weights_service, "get_all_records", side_effect=AssertionError("Sheets should not be read")), \
             patch.object(pig_weights_service, "append_row") as append_row:
            result = pig_weights_service.save_new_litter(cleaned_data)

        self.assertTrue(result["success"])
        self.assertEqual(result["litter_id"], "LIT-NEW")
        self.assertEqual(result["pig_rows_created"], 3)
        self.assertTrue(result["source"]["writes_to_supabase"])
        self.assertFalse(result["source"]["writes_to_sheets"])
        read_parents.assert_called_once_with(["PIG-MOTHER", "PIG-FATHER"])
        create_litter.assert_called_once()
        self.assertEqual(create_litter.call_args.kwargs["pig_ids"], ["PIG-1", "PIG-2", "PIG-3"])
        append_row.assert_not_called()


class LitterAttentionActionTests(unittest.TestCase):
    def setUp(self):
        self.supabase_availability_patch = patch.object(
            pig_weights_service.farm_supabase_read_service,
            "farm_supabase_reads_available",
            return_value=False,
        )
        self.supabase_availability_patch.start()

    def tearDown(self):
        self.supabase_availability_patch.stop()

    def test_list_litter_overview_flags_birth_count_mismatch(self):
        sheet_names = pig_weights_service.PIG_WEIGHTS_CONFIG["sheet_names"]
        overview_rows = [
            {
                "Litter_ID": "LIT-1",
                "Farrowing_Date": "01 May 2026",
                "Sow_Tag_Number": "S1",
                "Current_Pen_ID": "PEN-1",
                "Total_Born": "9",
                "Born_Alive": "7",
                "Stillborn_Count": "2",
                "Mummified_Count": "0",
                "Pig_Master_Row_Count": "9",
                "Active_Pig_Count": "6",
                "Exited_Pig_Count": "3",
                "Litter_Status": "Active",
                "Needs_Attention": "Yes",
                "Attention_Reason": "Linked pig records do not match born alive count",
            }
        ]
        pig_rows = [
            {"Pig_ID": f"PIG-A{i}", "Litter_ID": "LIT-1", "Status": "Active", "On_Farm": "Yes"}
            for i in range(6)
        ] + [
            {"Pig_ID": "PIG-D1", "Litter_ID": "LIT-1", "Status": "Dead", "On_Farm": "No", "Exit_Reason": "Died"},
            {"Pig_ID": "PIG-D2", "Litter_ID": "LIT-1", "Status": "Dead", "On_Farm": "No", "Exit_Reason": "Died"},
            {"Pig_ID": "PIG-D3", "Litter_ID": "LIT-1", "Status": "Dead", "On_Farm": "No", "Exit_Reason": "Died"},
        ]

        def fake_get_all_records(sheet_name):
            if sheet_name == sheet_names["litter_overview"]:
                return overview_rows
            if sheet_name == sheet_names["pig_master"]:
                return pig_rows
            return []

        with patch.object(pig_weights_service, "get_all_records", side_effect=fake_get_all_records):
            result = pig_weights_service.list_litter_overview()

        self.assertTrue(result["success"])
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["attention_count"], 1)
        self.assertEqual(result["mismatch_count"], 1)
        litter = result["litters"][0]
        self.assertEqual(litter["born_alive"], 7)
        self.assertEqual(litter["linked_pig_records"], 9)
        self.assertTrue(litter["reconciliation"]["mismatch"])
        self.assertEqual(litter["reconciliation"]["suggested_born_alive"], 9)
        self.assertTrue(litter["reconciliation"]["can_reclassify_stillborn"])

    def test_list_litter_overview_identifies_stillborn_formula_conflict(self):
        sheet_names = pig_weights_service.PIG_WEIGHTS_CONFIG["sheet_names"]
        overview_rows = [
            {
                "Litter_ID": "LIT-1",
                "Total_Born": "9",
                "Born_Alive": "7",
                "Stillborn_Count": "2",
                "Mummified_Count": "0",
                "Pig_Master_Row_Count": "9",
                "Active_Pig_Count": "6",
                "Exited_Pig_Count": "3",
                "Litter_Status": "Active",
                "Needs_Attention": "Yes",
                "Attention_Reason": "Linked pig records do not match born alive count",
            }
        ]
        pig_rows = [
            {"Pig_ID": f"PIG-A{i}", "Litter_ID": "LIT-1", "Status": "Active", "On_Farm": "Yes"}
            for i in range(7)
        ] + [
            {"Pig_ID": "PIG-S1", "Litter_ID": "LIT-1", "Status": "Dead", "On_Farm": "No", "Exit_Reason": "Stillborn"},
            {"Pig_ID": "PIG-S2", "Litter_ID": "LIT-1", "Status": "Dead", "On_Farm": "No", "Exit_Reason": "Stillborn"},
        ]

        def fake_get_all_records(sheet_name):
            if sheet_name == sheet_names["litter_overview"]:
                return overview_rows
            if sheet_name == sheet_names["pig_master"]:
                return pig_rows
            return []

        with patch.object(pig_weights_service, "get_all_records", side_effect=fake_get_all_records):
            result = pig_weights_service.list_litter_overview()

        self.assertTrue(result["success"])
        self.assertEqual(result["mismatch_count"], 0)
        self.assertEqual(result["attention_count"], 0)
        self.assertEqual(result["formula_conflict_count"], 1)
        self.assertEqual(result["litters"][0]["needs_attention"], "")
        self.assertEqual(result["litters"][0]["sheet_needs_attention"], "Yes")
        reconciliation = result["litters"][0]["reconciliation"]
        self.assertFalse(reconciliation["mismatch"])
        self.assertTrue(reconciliation["formula_conflict"])
        self.assertFalse(reconciliation["can_reconcile_birth_count"])
        self.assertEqual(reconciliation["suggested_born_alive"], 7)
        self.assertIn("Do not change Born_Alive", reconciliation["recommended_action"])

    def test_list_litter_overview_derives_completed_status_from_terminal_piglets(self):
        sheet_names = pig_weights_service.PIG_WEIGHTS_CONFIG["sheet_names"]
        overview_rows = [
            {
                "Litter_ID": "LIT-1",
                "Total_Born": "3",
                "Born_Alive": "3",
                "Stillborn_Count": "0",
                "Mummified_Count": "0",
                "Pig_Master_Row_Count": "3",
                "Active_Pig_Count": "0",
                "Exited_Pig_Count": "3",
                "Litter_Status": "",
                "Needs_Attention": "",
            }
        ]
        pig_rows = [
            {"Pig_ID": "PIG-SOLD", "Litter_ID": "LIT-1", "Status": "Sold", "On_Farm": "No", "Exit_Reason": "Sold"},
            {"Pig_ID": "PIG-DIED", "Litter_ID": "LIT-1", "Status": "Died", "On_Farm": "No", "Exit_Reason": "Died"},
            {"Pig_ID": "PIG-REMOVED", "Litter_ID": "LIT-1", "Status": "Removed", "On_Farm": "No", "Exit_Reason": "Removed"},
        ]

        def fake_get_all_records(sheet_name):
            if sheet_name == sheet_names["litter_overview"]:
                return overview_rows
            if sheet_name == sheet_names["pig_master"]:
                return pig_rows
            return []

        with patch.object(pig_weights_service, "get_all_records", side_effect=fake_get_all_records):
            result = pig_weights_service.list_litter_overview()

        litter = result["litters"][0]
        self.assertEqual(litter["litter_status"], "Completed")
        self.assertEqual(litter["lifecycle_outcomes"]["sold"], 1)
        self.assertEqual(litter["lifecycle_outcomes"]["dead"], 1)
        self.assertEqual(litter["lifecycle_outcomes"]["removed"], 1)
        self.assertEqual(litter["lifecycle_outcomes"]["other"], 0)

    def test_reconcile_litter_birth_counts_dry_run_updates_litters_only_in_preview(self):
        sheet_names = pig_weights_service.PIG_WEIGHTS_CONFIG["sheet_names"]
        overview_rows = [
            {
                "Litter_ID": "LIT-1",
                "Born_Alive": "7",
                "Pig_Master_Row_Count": "9",
                "Active_Pig_Count": "6",
                "Exited_Pig_Count": "3",
            }
        ]
        litter_values = [
            ["Litter_ID", "Born_Alive", "Litter_Notes"],
            ["LIT-1", "7", "Original note"],
        ]

        def fake_get_all_records(sheet_name):
            if sheet_name == sheet_names["litter_overview"]:
                return overview_rows
            return []

        with patch.object(pig_weights_service, "get_all_records", side_effect=fake_get_all_records), \
             patch.object(pig_weights_service, "get_all_values", return_value=litter_values), \
             patch.object(pig_weights_service, "update_row_by_first_column_match") as update_litter:
            result, status_code = pig_weights_service.reconcile_litter_birth_counts(
                "LIT-1",
                changed_by="Tester",
                reason="Confirmed three died after live birth.",
                dry_run=True,
            )

        self.assertEqual(status_code, 200)
        self.assertTrue(result["success"])
        self.assertTrue(result["dry_run"])
        self.assertEqual(result["target_born_alive"], 9)
        self.assertEqual(result["planned_updates"]["Born_Alive"], 9)
        self.assertIn("Confirmed three died after live birth.", result["planned_updates"]["Litter_Notes"])
        update_litter.assert_not_called()

    def test_reconcile_litter_birth_counts_apply_writes_updated_litter_row(self):
        sheet_names = pig_weights_service.PIG_WEIGHTS_CONFIG["sheet_names"]
        overview_rows = [
            {
                "Litter_ID": "LIT-1",
                "Born_Alive": "7",
                "Pig_Master_Row_Count": "9",
            }
        ]
        litter_values = [
            ["Litter_ID", "Born_Alive", "Litter_Notes", "Updated_At"],
            ["LIT-1", "7", "", ""],
        ]

        def fake_get_all_records(sheet_name):
            if sheet_name == sheet_names["litter_overview"]:
                return overview_rows
            return []

        with patch.object(pig_weights_service, "get_all_records", side_effect=fake_get_all_records), \
             patch.object(pig_weights_service, "get_all_values", return_value=litter_values), \
             patch.object(pig_weights_service, "update_row_by_first_column_match", return_value=2) as update_litter:
            result, status_code = pig_weights_service.reconcile_litter_birth_counts(
                "LIT-1",
                target_born_alive=9,
                changed_by="Tester",
                dry_run=False,
            )

        self.assertEqual(status_code, 200)
        self.assertTrue(result["success"])
        self.assertFalse(result["dry_run"])
        self.assertEqual(result["row_updated"], 2)
        updated_row = update_litter.call_args.args[2]
        self.assertEqual(updated_row[1], 9)
        self.assertIn("Born_Alive 7 -> 9", updated_row[2])

    def test_reconcile_litter_birth_counts_blocks_target_that_does_not_match_linked_records(self):
        sheet_names = pig_weights_service.PIG_WEIGHTS_CONFIG["sheet_names"]
        overview_rows = [
            {
                "Litter_ID": "LIT-1",
                "Born_Alive": "7",
                "Pig_Master_Row_Count": "9",
            }
        ]

        def fake_get_all_records(sheet_name):
            if sheet_name == sheet_names["litter_overview"]:
                return overview_rows
            return []

        with patch.object(pig_weights_service, "get_all_records", side_effect=fake_get_all_records), \
             patch.object(pig_weights_service, "get_all_values") as get_values:
            result, status_code = pig_weights_service.reconcile_litter_birth_counts(
                "LIT-1",
                target_born_alive=8,
                dry_run=True,
            )

        self.assertEqual(status_code, 409)
        self.assertFalse(result["success"])
        get_values.assert_not_called()

    def test_reconcile_litter_birth_counts_blocks_stillborn_formula_conflict(self):
        sheet_names = pig_weights_service.PIG_WEIGHTS_CONFIG["sheet_names"]
        overview_rows = [
            {
                "Litter_ID": "LIT-1",
                "Total_Born": "9",
                "Born_Alive": "7",
                "Stillborn_Count": "2",
                "Pig_Master_Row_Count": "9",
                "Needs_Attention": "Yes",
                "Attention_Reason": "Linked pig records do not match born alive count",
            }
        ]

        def fake_get_all_records(sheet_name):
            if sheet_name == sheet_names["litter_overview"]:
                return overview_rows
            return []

        with patch.object(pig_weights_service, "get_all_records", side_effect=fake_get_all_records), \
             patch.object(pig_weights_service, "get_all_values") as get_values, \
             patch.object(pig_weights_service, "update_row_by_first_column_match") as update_litter:
            result, status_code = pig_weights_service.reconcile_litter_birth_counts(
                "LIT-1",
                target_born_alive=9,
                dry_run=True,
            )

        self.assertEqual(status_code, 409)
        self.assertFalse(result["success"])
        self.assertTrue(result["reconciliation"]["formula_conflict"])
        get_values.assert_not_called()
        update_litter.assert_not_called()

    def test_reclassify_litter_dead_piglets_as_stillborn_preview_selects_shortfall(self):
        sheet_names = pig_weights_service.PIG_WEIGHTS_CONFIG["sheet_names"]
        overview_rows = [
            {
                "Litter_ID": "LIT-1",
                "Farrowing_Date": "02 Jun 2026",
                "Total_Born": "9",
                "Born_Alive": "7",
                "Stillborn_Count": "2",
                "Pig_Master_Row_Count": "9",
            }
        ]
        pig_rows = [
            {"Pig_ID": f"PIG-A{i}", "Litter_ID": "LIT-1", "Status": "Active", "On_Farm": "Yes"}
            for i in range(6)
        ] + [
            {"Pig_ID": "PIG-D1", "Litter_ID": "LIT-1", "Status": "Dead", "On_Farm": "No", "Exit_Date": "03 Jun 2026", "Exit_Reason": "Died"},
            {"Pig_ID": "PIG-D2", "Litter_ID": "LIT-1", "Status": "Dead", "On_Farm": "No", "Exit_Date": "03 Jun 2026", "Exit_Reason": "Died"},
            {"Pig_ID": "PIG-D3", "Litter_ID": "LIT-1", "Status": "Dead", "On_Farm": "No", "Exit_Date": "03 Jun 2026", "Exit_Reason": "Died"},
        ]

        def fake_get_all_records(sheet_name):
            if sheet_name == sheet_names["litter_overview"]:
                return overview_rows
            if sheet_name == sheet_names["pig_master"]:
                return pig_rows
            return []

        with patch.object(pig_weights_service, "get_all_records", side_effect=fake_get_all_records), \
             patch.object(pig_weights_service, "batch_update_rows_by_id") as update_rows:
            result, status_code = pig_weights_service.reclassify_litter_dead_piglets_as_stillborn(
                "LIT-1",
                changed_by="Tester",
                reason="Confirmed two were stillborn.",
                dry_run=True,
            )

        self.assertEqual(status_code, 200)
        self.assertTrue(result["success"])
        self.assertTrue(result["dry_run"])
        self.assertEqual(result["correction_count"], 2)
        self.assertEqual([pig["pig_id"] for pig in result["selected_piglets"]], ["PIG-D1", "PIG-D2"])
        self.assertEqual(result["planned_updates"]["PIG-D1"]["Exit_Reason"], "Stillborn")
        self.assertEqual(result["planned_updates"]["PIG-D1"]["Exit_Date"], "02 Jun 2026")
        self.assertIn("Confirmed two were stillborn.", result["planned_updates"]["PIG-D1"]["General_Notes"])
        update_rows.assert_not_called()

    def test_reclassify_litter_dead_piglets_as_stillborn_apply_writes_pig_master_rows(self):
        sheet_names = pig_weights_service.PIG_WEIGHTS_CONFIG["sheet_names"]
        overview_rows = [
            {
                "Litter_ID": "LIT-1",
                "Farrowing_Date": "02 Jun 2026",
                "Total_Born": "9",
                "Born_Alive": "7",
                "Stillborn_Count": "2",
                "Pig_Master_Row_Count": "9",
            }
        ]
        pig_rows = [
            {"Pig_ID": f"PIG-A{i}", "Litter_ID": "LIT-1", "Status": "Active", "On_Farm": "Yes"}
            for i in range(6)
        ] + [
            {"Pig_ID": "PIG-D1", "Litter_ID": "LIT-1", "Status": "Dead", "On_Farm": "No", "Exit_Date": "03 Jun 2026", "Exit_Reason": "Died"},
            {"Pig_ID": "PIG-D2", "Litter_ID": "LIT-1", "Status": "Dead", "On_Farm": "No", "Exit_Date": "03 Jun 2026", "Exit_Reason": "Died"},
            {"Pig_ID": "PIG-D3", "Litter_ID": "LIT-1", "Status": "Dead", "On_Farm": "No", "Exit_Date": "03 Jun 2026", "Exit_Reason": "Died"},
        ]

        def fake_get_all_records(sheet_name):
            if sheet_name == sheet_names["litter_overview"]:
                return overview_rows
            if sheet_name == sheet_names["pig_master"]:
                return pig_rows
            return []

        with patch.object(pig_weights_service, "get_all_records", side_effect=fake_get_all_records), \
             patch.object(pig_weights_service, "batch_update_rows_by_id", return_value=2) as update_rows:
            result, status_code = pig_weights_service.reclassify_litter_dead_piglets_as_stillborn(
                "LIT-1",
                dry_run=False,
            )

        self.assertEqual(status_code, 200)
        self.assertFalse(result["dry_run"])
        self.assertEqual(result["rows_updated"], 2)
        updates = update_rows.call_args.args[1]
        self.assertEqual(sorted(updates.keys()), ["PIG-D1", "PIG-D2"])
        self.assertEqual(updates["PIG-D2"]["Exit_Reason"], "Stillborn")
        self.assertEqual(updates["PIG-D2"]["Exit_Date"], "02 Jun 2026")

    def test_reclassify_litter_dead_piglets_as_stillborn_blocks_when_no_shortfall(self):
        sheet_names = pig_weights_service.PIG_WEIGHTS_CONFIG["sheet_names"]
        overview_rows = [
            {
                "Litter_ID": "LIT-1",
                "Farrowing_Date": "02 Jun 2026",
                "Total_Born": "9",
                "Born_Alive": "7",
                "Stillborn_Count": "2",
                "Pig_Master_Row_Count": "9",
            }
        ]
        pig_rows = [
            {"Pig_ID": f"PIG-A{i}", "Litter_ID": "LIT-1", "Status": "Active", "On_Farm": "Yes"}
            for i in range(7)
        ] + [
            {"Pig_ID": "PIG-S1", "Litter_ID": "LIT-1", "Status": "Dead", "On_Farm": "No", "Exit_Reason": "Stillborn"},
            {"Pig_ID": "PIG-S2", "Litter_ID": "LIT-1", "Status": "Dead", "On_Farm": "No", "Exit_Reason": "Stillborn"},
        ]

        def fake_get_all_records(sheet_name):
            if sheet_name == sheet_names["litter_overview"]:
                return overview_rows
            if sheet_name == sheet_names["pig_master"]:
                return pig_rows
            return []

        with patch.object(pig_weights_service, "get_all_records", side_effect=fake_get_all_records), \
             patch.object(pig_weights_service, "batch_update_rows_by_id") as update_rows:
            result, status_code = pig_weights_service.reclassify_litter_dead_piglets_as_stillborn(
                "LIT-1",
                dry_run=True,
            )

        self.assertEqual(status_code, 409)
        self.assertFalse(result["success"])
        update_rows.assert_not_called()

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

    def test_mark_litter_weaned_can_capture_latest_weights_as_wean_weights(self):
        pig_rows = [
            {
                "Pig_ID": "PIG-1",
                "Tag_Number": "101",
                "Litter_ID": "LIT-1",
                "Status": "Active",
                "On_Farm": "Yes",
            },
            {
                "Pig_ID": "PIG-2",
                "Tag_Number": "102",
                "Litter_ID": "LIT-1",
                "Status": "Active",
                "On_Farm": "Yes",
            },
        ]
        weight_rows = [
            {"Pig_ID": "PIG-1", "Weight_Date": "2026-05-25", "Weight_Kg": "6.4"},
            {"Pig_ID": "PIG-2", "Weight_Date": "2026-05-25", "Weight_Kg": "7.1"},
        ]
        litter_values = [
            ["Litter_ID", "Weaned_Count", "Wean_Date", "Updated_At"],
            ["LIT-1", "", "", ""],
        ]

        def fake_get_all_records(sheet_name):
            if sheet_name == pig_weights_service.PIG_WEIGHTS_CONFIG["sheet_names"]["pig_master"]:
                return pig_rows
            if sheet_name == pig_weights_service.PIG_WEIGHTS_CONFIG["sheet_names"]["weight_log"]:
                return weight_rows
            return []

        with patch.object(pig_weights_service, "get_all_records", side_effect=fake_get_all_records), \
             patch.object(pig_weights_service, "get_all_values", return_value=litter_values), \
             patch.object(pig_weights_service, "update_row_by_first_column_match", return_value=2), \
             patch.object(pig_weights_service, "batch_update_rows_by_id", return_value=2) as update_pigs:

            result, status_code = pig_weights_service.mark_litter_weaned(
                "LIT-1",
                "2026-05-26",
                changed_by="test",
                use_latest_weights_as_wean_weights=True,
            )

        self.assertEqual(status_code, 200)
        self.assertTrue(result["success"])
        self.assertEqual(result["wean_weights_captured"], 2)
        self.assertEqual(result["wean_weight_rows"][0]["wean_weight_kg"], 6.4)
        update_map = update_pigs.call_args.args[1]
        self.assertEqual(update_map["PIG-1"]["Wean_Weight_Kg"], 6.4)
        self.assertEqual(update_map["PIG-2"]["Wean_Weight_Kg"], 7.1)

    def test_mark_litter_weaned_blocks_weight_capture_when_latest_weight_is_missing(self):
        pig_rows = [
            {
                "Pig_ID": "PIG-1",
                "Litter_ID": "LIT-1",
                "Status": "Active",
                "On_Farm": "Yes",
            }
        ]

        def fake_get_all_records(sheet_name):
            if sheet_name == pig_weights_service.PIG_WEIGHTS_CONFIG["sheet_names"]["pig_master"]:
                return pig_rows
            if sheet_name == pig_weights_service.PIG_WEIGHTS_CONFIG["sheet_names"]["weight_log"]:
                return []
            return []

        with patch.object(pig_weights_service, "get_all_records", side_effect=fake_get_all_records), \
             patch.object(pig_weights_service, "get_all_values") as get_values, \
             patch.object(pig_weights_service, "batch_update_rows_by_id") as update_pigs:

            result, status_code = pig_weights_service.mark_litter_weaned(
                "LIT-1",
                "2026-05-26",
                use_latest_weights_as_wean_weights=True,
            )

        self.assertEqual(status_code, 409)
        self.assertFalse(result["success"])
        self.assertEqual(result["missing_wean_weight_pig_ids"], ["PIG-1"])
        get_values.assert_not_called()
        update_pigs.assert_not_called()

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

    def test_mark_litter_piglets_dead_dry_run_auto_selects_untagged_unsexed_piglets(self):
        pig_rows = [
            {
                "Pig_ID": "PIG-1",
                "Litter_ID": "LIT-1",
                "Status": "Active",
                "On_Farm": "Yes",
                "Tag_Number": "",
                "Sex": "",
                "General_Notes": "",
            },
            {
                "Pig_ID": "PIG-2",
                "Litter_ID": "LIT-1",
                "Status": "Active",
                "On_Farm": "Yes",
                "Tag_Number": "",
                "Sex": "",
                "General_Notes": "",
            },
            {
                "Pig_ID": "PIG-3",
                "Litter_ID": "LIT-1",
                "Status": "Dead",
                "On_Farm": "No",
                "Tag_Number": "",
                "Sex": "",
            },
        ]

        with patch.object(pig_weights_service, "get_all_records", return_value=pig_rows), \
             patch.object(pig_weights_service, "batch_update_rows_by_id") as update_pigs:
            result, status_code = pig_weights_service.mark_litter_piglets_dead(
                litter_id="LIT-1",
                event_date_value="2026-06-02",
                reason="Died after birth",
                count=1,
                changed_by="Tester",
                notes="Found during morning check.",
                dry_run=True,
            )

        self.assertEqual(status_code, 200)
        self.assertTrue(result["success"])
        self.assertTrue(result["dry_run"])
        self.assertEqual(result["piglet_count"], 1)
        self.assertEqual(result["pig_ids"], ["PIG-1"])
        updates = result["planned_updates"]["PIG-1"]
        self.assertEqual(updates["Status"], "Dead")
        self.assertEqual(updates["On_Farm"], "No")
        self.assertEqual(updates["Exit_Date"], "02 Jun 2026")
        self.assertEqual(updates["Exit_Reason"], "Died after birth")
        self.assertIn("Found during morning check.", updates["General_Notes"])
        update_pigs.assert_not_called()

    def test_mark_litter_piglets_dead_applies_sex_counts(self):
        pig_rows = [
            {
                "Pig_ID": "PIG-M1",
                "Litter_ID": "LIT-1",
                "Status": "Active",
                "On_Farm": "Yes",
                "Tag_Number": "",
                "Sex": "Male",
            },
            {
                "Pig_ID": "PIG-F1",
                "Litter_ID": "LIT-1",
                "Status": "Active",
                "On_Farm": "Yes",
                "Tag_Number": "",
                "Sex": "Female",
            },
        ]

        with patch.object(pig_weights_service, "get_all_records", return_value=pig_rows), \
             patch.object(pig_weights_service, "batch_update_rows_by_id", return_value=2) as update_pigs:
            result, status_code = pig_weights_service.mark_litter_piglets_dead(
                litter_id="LIT-1",
                event_date_value="2026-06-02",
                reason="Crushed by sow",
                male_count=1,
                female_count=1,
                dry_run=False,
            )

        self.assertEqual(status_code, 200)
        self.assertTrue(result["success"])
        self.assertFalse(result["dry_run"])
        self.assertEqual(result["rows_updated"], 2)
        update_map = update_pigs.call_args.args[1]
        self.assertEqual(set(update_map.keys()), {"PIG-M1", "PIG-F1"})
        self.assertEqual(update_map["PIG-M1"]["Exit_Reason"], "Crushed by sow")
        self.assertEqual(update_map["PIG-F1"]["Status"], "Dead")

    def test_mark_litter_piglets_dead_requires_specific_selection_for_tagged_piglets(self):
        pig_rows = [
            {
                "Pig_ID": "PIG-1",
                "Litter_ID": "LIT-1",
                "Status": "Active",
                "On_Farm": "Yes",
                "Tag_Number": "001",
                "Sex": "Male",
            }
        ]

        with patch.object(pig_weights_service, "get_all_records", return_value=pig_rows), \
             patch.object(pig_weights_service, "batch_update_rows_by_id") as update_pigs:
            result, status_code = pig_weights_service.mark_litter_piglets_dead(
                litter_id="LIT-1",
                event_date_value="2026-06-02",
                reason="Unknown",
                count=1,
                dry_run=True,
            )

        self.assertEqual(status_code, 409)
        self.assertFalse(result["success"])
        self.assertIn("Tagged piglets", result["errors"][0])
        update_pigs.assert_not_called()

    def test_record_litter_piglet_sex_counts_dry_run_fills_blank_sex_rows_only(self):
        pig_rows = [
            {
                "Pig_ID": "PIG-1",
                "Litter_ID": "LIT-1",
                "Status": "Active",
                "On_Farm": "Yes",
                "Tag_Number": "",
                "Sex": "",
                "General_Notes": "",
            },
            {
                "Pig_ID": "PIG-2",
                "Litter_ID": "LIT-1",
                "Status": "Active",
                "On_Farm": "Yes",
                "Tag_Number": "",
                "Sex": "",
                "General_Notes": "",
            },
            {
                "Pig_ID": "PIG-3",
                "Litter_ID": "LIT-1",
                "Status": "Active",
                "On_Farm": "Yes",
                "Tag_Number": "",
                "Sex": "Female",
                "General_Notes": "",
            },
        ]

        with patch.object(pig_weights_service, "get_all_records", return_value=pig_rows), \
             patch.object(pig_weights_service, "batch_update_rows_by_id") as update_pigs:
            result, status_code = pig_weights_service.record_litter_piglet_sex_counts(
                litter_id="LIT-1",
                action_date_value="2026-06-08",
                male_count=1,
                female_count=1,
                changed_by="Tester",
                notes="Checked while handling.",
                dry_run=True,
            )

        self.assertEqual(status_code, 200)
        self.assertTrue(result["success"])
        self.assertTrue(result["dry_run"])
        self.assertEqual(result["male_count"], 1)
        self.assertEqual(result["female_count"], 1)
        self.assertEqual(result["pig_ids"], ["PIG-1", "PIG-2"])
        self.assertEqual(result["planned_updates"]["PIG-1"]["Sex"], "Male")
        self.assertEqual(result["planned_updates"]["PIG-2"]["Sex"], "Female")
        self.assertIn("Checked while handling.", result["planned_updates"]["PIG-1"]["General_Notes"])
        update_pigs.assert_not_called()

    def test_record_litter_piglet_sex_counts_saves_after_preview(self):
        pig_rows = [
            {
                "Pig_ID": "PIG-1",
                "Litter_ID": "LIT-1",
                "Status": "Active",
                "On_Farm": "Yes",
                "Tag_Number": "",
                "Sex": "",
                "General_Notes": "",
            },
            {
                "Pig_ID": "PIG-2",
                "Litter_ID": "LIT-1",
                "Status": "Active",
                "On_Farm": "Yes",
                "Tag_Number": "",
                "Sex": "",
                "General_Notes": "",
            },
        ]

        with patch.object(pig_weights_service, "get_all_records", return_value=pig_rows), \
             patch.object(pig_weights_service, "batch_update_rows_by_id", return_value=2) as update_pigs:
            result, status_code = pig_weights_service.record_litter_piglet_sex_counts(
                litter_id="LIT-1",
                action_date_value="2026-06-08",
                male_count=1,
                female_count=1,
                dry_run=False,
            )

        self.assertEqual(status_code, 200)
        self.assertTrue(result["success"])
        self.assertFalse(result["dry_run"])
        self.assertEqual(result["rows_updated"], 2)
        update_map = update_pigs.call_args.args[1]
        self.assertEqual(update_map["PIG-1"]["Sex"], "Male")
        self.assertEqual(update_map["PIG-2"]["Sex"], "Female")

    def test_record_litter_piglet_sex_counts_blocks_when_counts_exceed_blank_sex_rows(self):
        pig_rows = [
            {
                "Pig_ID": "PIG-1",
                "Litter_ID": "LIT-1",
                "Status": "Active",
                "On_Farm": "Yes",
                "Tag_Number": "",
                "Sex": "",
            }
        ]

        with patch.object(pig_weights_service, "get_all_records", return_value=pig_rows), \
             patch.object(pig_weights_service, "batch_update_rows_by_id") as update_pigs:
            result, status_code = pig_weights_service.record_litter_piglet_sex_counts(
                litter_id="LIT-1",
                action_date_value="2026-06-08",
                male_count=1,
                female_count=1,
                dry_run=True,
            )

        self.assertEqual(status_code, 409)
        self.assertFalse(result["success"])
        self.assertIn("blank sex", result["errors"][0])
        update_pigs.assert_not_called()


class PigLifecycleOutcomeTests(unittest.TestCase):
    def setUp(self):
        self.supabase_availability_patch = patch.object(
            pig_weights_service.farm_supabase_read_service,
            "farm_supabase_reads_available",
            return_value=False,
        )
        self.supabase_availability_patch.start()

    def tearDown(self):
        self.supabase_availability_patch.stop()

    def test_assign_litter_piglet_tag_numbers_dry_run_maps_tags_without_writing(self):
        pig_rows = [
            {"Pig_ID": "PIG-1", "Tag_Number": "", "Litter_ID": "LIT-1", "Status": "Active", "On_Farm": "Yes", "Sex": "Female"},
            {"Pig_ID": "PIG-2", "Tag_Number": "", "Litter_ID": "LIT-1", "Status": "Active", "On_Farm": "Yes", "Sex": "Male"},
            {"Pig_ID": "PIG-OTHER", "Tag_Number": "200", "Litter_ID": "LIT-OTHER", "Status": "Active", "On_Farm": "Yes"},
        ]

        with patch.object(pig_weights_service, "get_all_records", return_value=pig_rows), \
             patch.object(pig_weights_service, "batch_update_rows_by_id") as update_pigs:

            result, status_code = pig_weights_service.assign_litter_piglet_tag_numbers(
                "LIT-1",
                tag_numbers=["101", "102"],
                action_date_value="2026-06-22",
                changed_by="Charl",
                notes="Tagged at weaning.",
                dry_run=True,
            )

        self.assertEqual(status_code, 200)
        self.assertTrue(result["success"])
        self.assertTrue(result["dry_run"])
        self.assertEqual(result["piglet_count"], 2)
        self.assertEqual(result["tag_numbers"], ["101", "102"])
        self.assertEqual(result["selected_piglets"][0]["pig_id"], "PIG-1")
        self.assertEqual(result["selected_piglets"][0]["tag_number"], "101")
        self.assertIn("Tag_Number", result["planned_updates"]["PIG-1"])
        self.assertEqual(result["planned_updates"]["PIG-1"]["Earmarked"], "Yes")
        self.assertIn("Tagged at weaning.", result["planned_updates"]["PIG-1"]["General_Notes"])
        update_pigs.assert_not_called()

    def test_assign_litter_piglet_tag_numbers_writes_previewed_tags(self):
        pig_rows = [
            {"Pig_ID": "PIG-1", "Tag_Number": "", "Litter_ID": "LIT-1", "Status": "Active", "On_Farm": "Yes", "Sex": "Female"},
            {"Pig_ID": "PIG-2", "Tag_Number": "", "Litter_ID": "LIT-1", "Status": "Active", "On_Farm": "Yes", "Sex": "Male"},
        ]

        with patch.object(pig_weights_service, "get_all_records", return_value=pig_rows), \
             patch.object(pig_weights_service, "batch_update_rows_by_id", return_value=2) as update_pigs:

            result, status_code = pig_weights_service.assign_litter_piglet_tag_numbers(
                "LIT-1",
                tag_numbers=["101", "102"],
                action_date_value="2026-06-22",
                dry_run=False,
            )

        self.assertEqual(status_code, 200)
        self.assertTrue(result["success"])
        self.assertFalse(result["dry_run"])
        self.assertEqual(result["rows_updated"], 2)
        update_map = update_pigs.call_args.args[1]
        self.assertEqual(update_map["PIG-1"]["Tag_Number"], "101")
        self.assertEqual(update_map["PIG-2"]["Tag_Number"], "102")

    def test_assign_litter_piglet_tag_numbers_accepts_explicit_row_assignments(self):
        pig_rows = [
            {"Pig_ID": "PIG-1", "Tag_Number": "", "Litter_ID": "LIT-1", "Status": "Active", "On_Farm": "Yes", "Sex": "Female"},
            {"Pig_ID": "PIG-2", "Tag_Number": "", "Litter_ID": "LIT-1", "Status": "Active", "On_Farm": "Yes", "Sex": "Male"},
        ]

        with patch.object(pig_weights_service, "get_all_records", return_value=pig_rows), \
             patch.object(pig_weights_service, "batch_update_rows_by_id") as update_pigs:

            result, status_code = pig_weights_service.assign_litter_piglet_tag_numbers(
                "LIT-1",
                assignments=[
                    {"pig_id": "PIG-1", "tag_number": "201"},
                    {"pig_id": "PIG-2", "tag_number": "202"},
                ],
                action_date_value="2026-06-22",
                dry_run=True,
            )

        self.assertEqual(status_code, 200)
        self.assertTrue(result["success"])
        self.assertEqual(result["selected_piglets"][0]["pig_id"], "PIG-1")
        self.assertEqual(result["selected_piglets"][0]["tag_number"], "201")
        self.assertEqual(result["selected_piglets"][1]["pig_id"], "PIG-2")
        self.assertEqual(result["selected_piglets"][1]["tag_number"], "202")
        update_pigs.assert_not_called()

    def test_assign_litter_piglet_tag_numbers_blocks_missing_inline_assignment(self):
        pig_rows = [
            {"Pig_ID": "PIG-1", "Tag_Number": "", "Litter_ID": "LIT-1", "Status": "Active", "On_Farm": "Yes"},
            {"Pig_ID": "PIG-2", "Tag_Number": "", "Litter_ID": "LIT-1", "Status": "Active", "On_Farm": "Yes"},
        ]

        with patch.object(pig_weights_service, "get_all_records", return_value=pig_rows), \
             patch.object(pig_weights_service, "batch_update_rows_by_id") as update_pigs:

            result, status_code = pig_weights_service.assign_litter_piglet_tag_numbers(
                "LIT-1",
                assignments=[
                    {"pig_id": "PIG-1", "tag_number": "201"},
                    {"pig_id": "PIG-2", "tag_number": ""},
                ],
                dry_run=True,
            )

        self.assertEqual(status_code, 409)
        self.assertFalse(result["success"])
        self.assertIn("every active untagged piglet", result["errors"][0])
        update_pigs.assert_not_called()

    def test_assign_litter_piglet_tag_numbers_blocks_wrong_count(self):
        pig_rows = [
            {"Pig_ID": "PIG-1", "Tag_Number": "", "Litter_ID": "LIT-1", "Status": "Active", "On_Farm": "Yes"},
            {"Pig_ID": "PIG-2", "Tag_Number": "", "Litter_ID": "LIT-1", "Status": "Active", "On_Farm": "Yes"},
        ]

        with patch.object(pig_weights_service, "get_all_records", return_value=pig_rows), \
             patch.object(pig_weights_service, "batch_update_rows_by_id") as update_pigs:

            result, status_code = pig_weights_service.assign_litter_piglet_tag_numbers(
                "LIT-1",
                tag_numbers=["101"],
                dry_run=True,
            )

        self.assertEqual(status_code, 409)
        self.assertFalse(result["success"])
        self.assertIn("exactly 2", result["errors"][0])
        update_pigs.assert_not_called()

    def test_assign_litter_piglet_tag_numbers_blocks_duplicate_existing_tag(self):
        pig_rows = [
            {"Pig_ID": "PIG-1", "Tag_Number": "", "Litter_ID": "LIT-1", "Status": "Active", "On_Farm": "Yes"},
            {"Pig_ID": "PIG-OTHER", "Tag_Number": "101", "Litter_ID": "LIT-OTHER", "Status": "Active", "On_Farm": "Yes"},
        ]

        with patch.object(pig_weights_service, "get_all_records", return_value=pig_rows), \
             patch.object(pig_weights_service, "batch_update_rows_by_id") as update_pigs:

            result, status_code = pig_weights_service.assign_litter_piglet_tag_numbers(
                "LIT-1",
                tag_numbers=["101"],
                dry_run=True,
            )

        self.assertEqual(status_code, 409)
        self.assertFalse(result["success"])
        self.assertIn("already exist", result["errors"][0])
        update_pigs.assert_not_called()

    def test_assign_litter_piglet_tag_numbers_blocks_duplicate_input(self):
        result, status_code = pig_weights_service.assign_litter_piglet_tag_numbers(
            "LIT-1",
            tag_numbers=["101", "101"],
            dry_run=True,
        )

        self.assertEqual(status_code, 400)
        self.assertFalse(result["success"])
        self.assertIn("Duplicate", result["errors"][0])

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

    def test_mark_pig_death_or_removal_dry_run_returns_planned_updates_without_writing(self):
        pig_rows = [
            {
                "Pig_ID": "PIG-1",
                "Status": "Active",
                "On_Farm": "Yes",
                "General_Notes": "",
            }
        ]

        with patch.object(pig_weights_service, "get_all_records", return_value=pig_rows), \
             patch.object(pig_weights_service, "batch_update_rows_by_id") as update_pigs:

            result, status_code = pig_weights_service.mark_pig_death_or_removal(
                pig_id="PIG-1",
                event_date_value="2026-06-01",
                reason="Removed",
                changed_by="Tester",
                notes="Dry-run only.",
                dry_run=True,
            )

        self.assertEqual(status_code, 200)
        self.assertTrue(result["success"])
        self.assertTrue(result["dry_run"])
        self.assertEqual(result["rows_updated"], 0)
        self.assertEqual(result["planned_updates"]["Status"], "Removed")
        self.assertEqual(result["planned_updates"]["On_Farm"], "No")
        self.assertEqual(result["planned_updates"]["Exit_Date"], "01 Jun 2026")
        self.assertEqual(result["planned_updates"]["Exit_Reason"], "Removed")
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


class LifecycleDetailReadTests(unittest.TestCase):
    def test_format_date_for_json_accepts_supabase_timestamp_with_timezone(self):
        self.assertEqual(
            format_date_for_json("2026-05-14T00:00:00+00:00"),
            "2026-05-14",
        )

    def test_format_date_for_json_accepts_google_day_month_display_value(self):
        self.assertEqual(
            format_date_for_json("14 May"),
            "2026-05-14",
        )

    def test_pig_detail_includes_read_only_lifecycle_history_from_pig_master(self):
        sheet_names = pig_weights_service.PIG_WEIGHTS_CONFIG["sheet_names"]
        overview_rows = [
            {
                "Pig_ID": "PIG-1",
                "Tag_Number": "S10",
                "Status": "Slaughtered",
                "On_Farm": "No",
                "Litter_ID": "LIT-1",
            }
        ]
        master_rows = [
            {
                "Pig_ID": "PIG-1",
                "Status": "Slaughtered",
                "On_Farm": "No",
                "Wean_Date": "26 May 2026",
                "Wean_Weight_Kg": "12.5",
                "Exit_Date": "01 Jun 2026",
                "Exit_Reason": "Sold to Abattoir",
                "Exit_Order_ID": "SALE-1",
                "Carcass_Weight_Kg": "68",
            }
        ]

        def fake_get_all_records(sheet_name):
            if sheet_name == sheet_names["pig_overview"]:
                return overview_rows
            if sheet_name == sheet_names["pig_master"]:
                return master_rows
            return []

        with patch.object(pig_weights_service, "get_all_records", side_effect=fake_get_all_records):
            detail = pig_weights_service.get_pig_detail("PIG-1")

        self.assertEqual(detail["lifecycle"]["status"], "Slaughtered")
        self.assertEqual(detail["lifecycle"]["on_farm"], "No")
        self.assertEqual(detail["lifecycle"]["wean_date"], "2026-05-26")
        self.assertEqual(detail["lifecycle"]["wean_weight_kg"], 12.5)
        self.assertEqual(detail["lifecycle"]["exit_date"], "2026-06-01")
        self.assertEqual(detail["lifecycle"]["exit_reason"], "Sold to Abattoir")
        self.assertEqual(detail["lifecycle"]["exit_order_id"], "SALE-1")
        self.assertEqual(detail["lifecycle"]["carcass_weight_kg"], 68)

    def test_litter_detail_includes_lifecycle_outcome_counts_from_pig_master(self):
        sheet_names = pig_weights_service.PIG_WEIGHTS_CONFIG["sheet_names"]
        overview_rows = [
            {"Pig_ID": "PIG-1", "Tag_Number": "001", "Litter_ID": "LIT-1", "Status": "Active", "On_Farm": "Yes", "Sex": "Male", "Date_Of_Birth": "01 May 2026"},
            {"Pig_ID": "PIG-2", "Tag_Number": "002", "Litter_ID": "LIT-1", "Status": "Sold", "On_Farm": "No", "Sex": "Female", "Date_Of_Birth": "01 May 2026"},
            {"Pig_ID": "PIG-3", "Tag_Number": "003", "Litter_ID": "LIT-1", "Status": "Slaughtered", "On_Farm": "No", "Sex": "Male", "Date_Of_Birth": "01 May 2026"},
            {"Pig_ID": "PIG-4", "Tag_Number": "004", "Litter_ID": "LIT-1", "Status": "Died", "On_Farm": "No", "Sex": "Female", "Date_Of_Birth": "01 May 2026"},
            {"Pig_ID": "PIG-5", "Tag_Number": "", "Litter_ID": "LIT-1", "Status": "Dead", "On_Farm": "No", "Sex": "", "Date_Of_Birth": "01 May 2026"},
        ]
        master_rows = [
            {"Pig_ID": "PIG-1", "Litter_ID": "LIT-1", "Status": "Active", "On_Farm": "Yes"},
            {"Pig_ID": "PIG-2", "Litter_ID": "LIT-1", "Status": "Sold", "On_Farm": "No", "Exit_Reason": "Sold"},
            {"Pig_ID": "PIG-3", "Litter_ID": "LIT-1", "Status": "Slaughtered", "On_Farm": "No", "Exit_Reason": "Sold to Abattoir"},
            {"Pig_ID": "PIG-4", "Litter_ID": "LIT-1", "Status": "Died", "On_Farm": "No", "Exit_Reason": "Died"},
            {"Pig_ID": "PIG-5", "Litter_ID": "LIT-1", "Status": "Dead", "On_Farm": "No", "Exit_Reason": "Stillborn"},
            {"Pig_ID": "PIG-5", "Litter_ID": "LIT-OTHER", "Status": "Removed", "On_Farm": "No", "Exit_Reason": "Removed"},
        ]

        def fake_get_all_records(sheet_name):
            if sheet_name == sheet_names["litter_register"]:
                return []
            if sheet_name == sheet_names["pig_overview"]:
                return overview_rows
            if sheet_name == sheet_names["pig_master"]:
                return master_rows
            return []

        with patch.object(pig_weights_service, "get_all_records", side_effect=fake_get_all_records):
            detail = pig_weights_service.get_litter_detail("LIT-1")

        self.assertEqual(detail["lifecycle_outcomes"]["total"], 5)
        self.assertEqual(detail["lifecycle_outcomes"]["active"], 1)
        self.assertEqual(detail["lifecycle_outcomes"]["sold"], 1)
        self.assertEqual(detail["lifecycle_outcomes"]["slaughtered"], 1)
        self.assertEqual(detail["lifecycle_outcomes"]["dead"], 2)
        self.assertEqual(detail["lifecycle_outcomes"]["removed"], 0)
        self.assertEqual(detail["litter_status"], "Active")
        self.assertEqual(detail["birth_date"], "2026-05-01")
        self.assertEqual(detail["estimated_wean_date"], "2026-06-05")
        self.assertEqual(detail["wean_tag_attention_start_date"], "2026-06-02")
        self.assertEqual(detail["default_wean_age_days"], 35)


class LitterNewbornHealthTests(unittest.TestCase):
    def setUp(self):
        self.supabase_availability_patch = patch.object(
            pig_weights_service.farm_supabase_read_service,
            "farm_supabase_reads_available",
            return_value=False,
        )
        self.supabase_availability_patch.start()

    def tearDown(self):
        self.supabase_availability_patch.stop()

    def test_record_litter_newborn_health_prefers_supabase_pig_and_product_reads(self):
        product_rows = [{
            "product_id": "PRD-ANTIPARASITIC",
            "product_name": "Piglet Antiparasitic",
            "product_category": "Antiparasitic",
            "default_dose": 1.5,
            "dose_unit": "ml",
            "default_withdrawal_days": 7,
        }]
        pig_rows = [
            {
                "Pig_ID": "PIG-1",
                "Litter_ID": "LIT-1",
                "Status": "Active",
                "On_Farm": "Yes",
                "Earmarked": "",
                "Earmark_Date": "",
            },
            {
                "Pig_ID": "PIG-2",
                "Litter_ID": "LIT-1",
                "Status": "Active",
                "On_Farm": "Yes",
                "Earmarked": "",
                "Earmark_Date": "",
            },
        ]

        with patch.object(pig_weights_service.farm_supabase_read_service, "farm_supabase_reads_available", return_value=True), \
             patch.object(pig_weights_service.farm_supabase_read_service, "get_products", return_value=product_rows) as get_products, \
             patch.object(pig_weights_service.farm_supabase_read_service, "get_pig_master_rows", return_value=pig_rows) as get_pigs, \
             patch.object(pig_weights_service, "get_all_records", side_effect=AssertionError("Sheets should not be read")):
            result, status_code = pig_weights_service.record_litter_newborn_health(
                litter_id="LIT-1",
                action_date_value="2026-06-02",
                changed_by="Tester",
                antiparasitic_product_id="PRD-ANTIPARASITIC",
                dry_run=True,
            )

        self.assertEqual(status_code, 200)
        self.assertTrue(result["success"])
        self.assertEqual(result["piglet_count"], 2)
        self.assertEqual(result["treatment_rows_planned"], 2)
        get_products.assert_called_once()
        get_pigs.assert_called_once()

    def test_mark_litter_weaned_prefers_supabase_pig_reads_and_writes(self):
        pig_rows = [
            {
                "Pig_ID": "PIG-1",
                "Litter_ID": "LIT-1",
                "Status": "Active",
                "On_Farm": "Yes",
                "Current_Weight_Kg": 6.5,
                "Last_Weight_Date": "2026-06-01",
            },
            {
                "Pig_ID": "PIG-2",
                "Litter_ID": "LIT-1",
                "Status": "Active",
                "On_Farm": "Yes",
                "Current_Weight_Kg": 7.1,
                "Last_Weight_Date": "2026-06-01",
            },
        ]

        with patch.object(pig_weights_service.farm_supabase_read_service, "farm_supabase_reads_available", return_value=True), \
             patch.object(pig_weights_service.farm_supabase_read_service, "get_pig_master_rows", return_value=pig_rows) as get_pigs, \
             patch.object(pig_weights_service.farm_supabase_write_service, "farm_supabase_writes_available", return_value=True), \
             patch.object(pig_weights_service.farm_supabase_write_service, "update_litter_by_id", return_value=1) as update_litter, \
             patch.object(pig_weights_service.farm_supabase_write_service, "update_pigs_by_id", return_value=2) as update_pigs, \
             patch.object(pig_weights_service, "get_all_records", side_effect=AssertionError("Sheets should not be read")), \
             patch.object(pig_weights_service, "batch_update_rows_by_id") as sheet_update:
            result, status_code = pig_weights_service.mark_litter_weaned(
                "LIT-1",
                "2026-06-05",
                use_latest_weights_as_wean_weights=True,
            )

        self.assertEqual(status_code, 200)
        self.assertTrue(result["success"])
        self.assertTrue(result["source"]["writes_to_supabase"])
        self.assertFalse(result["source"]["writes_to_sheets"])
        self.assertEqual(result["wean_weights_captured"], 2)
        get_pigs.assert_called_once()
        update_litter.assert_called_once()
        update_pigs.assert_called_once()
        sheet_update.assert_not_called()

    def test_mark_pig_death_or_removal_prefers_supabase_pig_reads(self):
        pig_rows = [{
            "Pig_ID": "PIG-1",
            "Status": "Active",
            "On_Farm": "Yes",
            "General_Notes": "",
        }]

        with patch.object(pig_weights_service.farm_supabase_read_service, "farm_supabase_reads_available", return_value=True), \
             patch.object(pig_weights_service.farm_supabase_read_service, "get_pig_master_rows", return_value=pig_rows) as get_pigs, \
             patch.object(pig_weights_service, "get_all_records", side_effect=AssertionError("Sheets should not be read")):
            result, status_code = pig_weights_service.mark_pig_death_or_removal(
                "PIG-1",
                "2026-06-02",
                "Died",
                dry_run=True,
            )

        self.assertEqual(status_code, 200)
        self.assertTrue(result["success"])
        self.assertEqual(result["planned_updates"]["Status"], "Dead")
        get_pigs.assert_called_once()

    def test_record_litter_newborn_health_dry_run_plans_earmarks_and_treatments_without_writing(self):
        sheet_names = pig_weights_service.PIG_WEIGHTS_CONFIG["sheet_names"]
        product_rows = [
            {
                "Product_ID": "PRD-ANTIPARASITIC",
                "Product_Name": "Piglet Antiparasitic",
                "Product_Category": "Antiparasitic",
                "Default_Dose": "1.5",
                "Dose_Unit": "ml",
                "Default_Withdrawal_Days": "7",
                "Is_Active": "Yes",
            },
            {
                "Product_ID": "PRD-DEWORM",
                "Product_Name": "Piglet Dewormer",
                "Product_Category": "Dewormer",
                "Default_Dose": "2.5",
                "Dose_Unit": "g",
                "Default_Withdrawal_Days": "14",
                "Is_Active": "Yes",
            },
            {
                "Product_ID": "PRD-VACCINE",
                "Product_Name": "Piglet Vaccine",
                "Product_Category": "Vaccination",
                "Default_Dose": "2",
                "Dose_Unit": "ml",
                "Default_Withdrawal_Days": "0",
                "Is_Active": "Yes",
            },
        ]
        pig_rows = [
            {
                "Pig_ID": "PIG-1",
                "Litter_ID": "LIT-1",
                "Status": "Active",
                "On_Farm": "Yes",
                "Earmarked": "",
                "Earmark_Date": "",
            },
            {
                "Pig_ID": "PIG-2",
                "Litter_ID": "LIT-1",
                "Status": "Active",
                "On_Farm": "Yes",
                "Earmarked": "",
                "Earmark_Date": "",
            },
        ]

        def fake_get_all_records(sheet_name):
            if sheet_name == sheet_names["product_register"]:
                return product_rows
            if sheet_name == sheet_names["pig_master"]:
                return pig_rows
            return []

        with patch.object(pig_weights_service, "get_all_records", side_effect=fake_get_all_records), \
             patch.object(pig_weights_service, "batch_update_rows_by_id") as update_pigs, \
             patch.object(pig_weights_service, "append_row") as append_row:
            result, status_code = pig_weights_service.record_litter_newborn_health(
                litter_id="LIT-1",
                action_date_value="2026-06-02",
                changed_by="Tester",
                earmarked=True,
                antiparasitic_product_id="PRD-ANTIPARASITIC",
                deworming_product_id="PRD-DEWORM",
                vaccination_product_id="PRD-VACCINE",
                notes="All done on the same round.",
                dry_run=True,
            )

        self.assertEqual(status_code, 200)
        self.assertTrue(result["success"])
        self.assertTrue(result["dry_run"])
        self.assertEqual(result["piglet_count"], 2)
        self.assertEqual(result["treatment_rows_planned"], 6)
        self.assertEqual(set(result["planned_pig_updates"].keys()), {"PIG-1", "PIG-2"})
        self.assertEqual(result["planned_pig_updates"]["PIG-1"]["Earmarked"], "Yes")
        self.assertEqual(result["planned_pig_updates"]["PIG-1"]["Earmark_Date"], "02 Jun 2026")
        treatment_row = result["planned_treatment_rows"][0]
        self.assertEqual(treatment_row[1], "PIG-1")
        self.assertEqual(treatment_row[2], "02 Jun 2026")
        self.assertEqual(treatment_row[3], "Antiparasitic")
        self.assertEqual(treatment_row[4], "PRD-ANTIPARASITIC")
        self.assertEqual(treatment_row[5], "Piglet Antiparasitic")
        self.assertEqual(treatment_row[12], "09 Jun 2026")
        deworming_row = result["planned_treatment_rows"][1]
        self.assertEqual(deworming_row[3], "Deworming")
        self.assertEqual(deworming_row[4], "PRD-DEWORM")
        self.assertEqual(deworming_row[5], "Piglet Dewormer")
        self.assertEqual(deworming_row[12], "16 Jun 2026")
        update_pigs.assert_not_called()
        append_row.assert_not_called()

    def test_record_litter_newborn_health_requires_earmark_columns_before_structured_write(self):
        sheet_names = pig_weights_service.PIG_WEIGHTS_CONFIG["sheet_names"]
        product_rows = []
        pig_rows = [
            {
                "Pig_ID": "PIG-1",
                "Litter_ID": "LIT-1",
                "Status": "Active",
                "On_Farm": "Yes",
            }
        ]

        def fake_get_all_records(sheet_name):
            if sheet_name == sheet_names["product_register"]:
                return product_rows
            if sheet_name == sheet_names["pig_master"]:
                return pig_rows
            return []

        with patch.object(pig_weights_service, "get_all_records", side_effect=fake_get_all_records), \
             patch.object(pig_weights_service, "batch_update_rows_by_id") as update_pigs:
            result, status_code = pig_weights_service.record_litter_newborn_health(
                litter_id="LIT-1",
                action_date_value="2026-06-02",
                earmarked=True,
                dry_run=True,
            )

        self.assertEqual(status_code, 409)
        self.assertFalse(result["success"])
        self.assertEqual(result["missing_columns"], ["Earmarked", "Earmark_Date"])
        update_pigs.assert_not_called()


if __name__ == "__main__":
    unittest.main()
