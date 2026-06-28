import unittest
from datetime import date
from unittest.mock import patch

from modules.pig_weights import pig_weights_service


class BulkWeightServiceTests(unittest.TestCase):
    def test_preflight_skips_blank_rows_and_accepts_valid_weight(self):
        active_pigs = [
            {
                "pig_id": "PIG-1",
                "tag_number": "1",
                "current_pen_id": "PEN-1",
                "current_pen_name": "Growers",
            },
            {
                "pig_id": "PIG-2",
                "tag_number": "2",
                "current_pen_id": "PEN-1",
                "current_pen_name": "Growers",
            },
        ]

        with patch.object(pig_weights_service, "get_active_pigs", return_value=active_pigs), \
             patch.object(pig_weights_service, "get_pens", return_value=[{"pen_id": "PEN-2"}]), \
             patch.object(pig_weights_service, "get_all_records", return_value=[]):
            result, status = pig_weights_service.preflight_bulk_weight_entries({
                "weight_date": "2026-06-01",
                "rows": [
                    {"pig_id": "PIG-1", "tag_number": "1", "weight_kg": "42.5", "moved_to_pen_id": "PEN-2"},
                    {"pig_id": "PIG-2", "tag_number": "2", "weight_kg": ""},
                ],
            })

        self.assertEqual(status, 200)
        self.assertTrue(result["success"])
        self.assertEqual(result["accepted_count"], 1)
        self.assertEqual(result["skipped_count"], 1)
        self.assertEqual(result["accepted_rows"][0]["weight_kg"], 42.5)
        self.assertFalse(result["writes_to_google_sheets"])

    def test_preflight_blocks_duplicate_existing_weight(self):
        active_pigs = [{"pig_id": "PIG-1", "tag_number": "1", "current_pen_id": "PEN-1"}]
        weight_rows = [{
            "Weight_Log_ID": "WGT-1",
            "Pig_ID": "PIG-1",
            "Weight_Date": "1 June 2026",
            "Weight_Kg": "41",
        }]

        with patch.object(pig_weights_service, "get_active_pigs", return_value=active_pigs), \
             patch.object(pig_weights_service, "get_pens", return_value=[]), \
             patch.object(pig_weights_service, "get_all_records", return_value=weight_rows):
            result, status = pig_weights_service.preflight_bulk_weight_entries({
                "weight_date": "2026-06-01",
                "rows": [{"pig_id": "PIG-1", "tag_number": "1", "weight_kg": "42"}],
            })

        self.assertEqual(status, 200)
        self.assertFalse(result["success"])
        self.assertEqual(result["blocked_count"], 1)
        self.assertIn("already has a weight", result["blocked_rows"][0]["reason"])
        self.assertEqual(result["blocked_rows"][0]["existing"]["weight_log_id"], "WGT-1")

    def test_save_bulk_uses_optional_move_service_for_accepted_rows(self):
        preflight_result = {
            "success": True,
            "accepted_count": 1,
            "skipped_count": 0,
            "accepted_rows": [{
                "pig_id": "PIG-1",
                "weight_date": "2026-06-01",
                "weight_kg": 42.5,
                "weighed_by": "WebApp",
                "moved_to_pen_id": "PEN-2",
                "condition_notes": "Good",
            }],
        }

        with patch.object(pig_weights_service, "preflight_bulk_weight_entries", return_value=(preflight_result, 200)), \
             patch.object(pig_weights_service, "_write_bulk_batch_audit", return_value={"warnings": []}), \
             patch.object(pig_weights_service, "save_weight_entry_with_optional_move", return_value={
                 "success": True,
                 "saved": {"pig_id": "PIG-1"},
                 "movement_logged": True,
             }) as save_weight:
            result, status = pig_weights_service.save_bulk_weight_entries({"weight_date": "2026-06-01", "rows": []})

        self.assertEqual(status, 201)
        self.assertTrue(result["success"])
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["saved_count"], 1)
        self.assertEqual(result["movement_count"], 1)
        save_weight.assert_called_once()
        self.assertEqual(save_weight.call_args.args[0]["weight_date"], date(2026, 6, 1))

    def test_save_bulk_uploads_accepted_rows_when_duplicates_are_blocked(self):
        preflight_result = {
            "success": False,
            "accepted_count": 1,
            "blocked_count": 1,
            "skipped_count": 2,
            "accepted_rows": [{
                "pig_id": "PIG-NEW",
                "weight_date": "2026-06-01",
                "weight_kg": 42.5,
                "weighed_by": "WebApp",
                "moved_to_pen_id": "",
                "condition_notes": "",
            }],
            "blocked_rows": [{
                "pig_id": "PIG-OLD",
                "tag_number": "2",
                "reason": "This pig already has a weight entry for this date.",
            }],
        }

        with patch.object(pig_weights_service, "preflight_bulk_weight_entries", return_value=(preflight_result, 200)), \
             patch.object(pig_weights_service, "_write_bulk_batch_audit", return_value={"warnings": []}), \
             patch.object(pig_weights_service, "save_weight_entry_with_optional_move", return_value={
                 "success": True,
                 "saved": {"pig_id": "PIG-NEW"},
                 "movement_logged": False,
             }) as save_weight:
            result, status = pig_weights_service.save_bulk_weight_entries({"weight_date": "2026-06-01", "rows": []})

        self.assertEqual(status, 207)
        self.assertFalse(result["ok"])
        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "partial_failure")
        self.assertEqual(result["status"], "partial_failure")
        self.assertEqual(result["saved_count"], 1)
        self.assertEqual(result["blocked_count"], 1)
        self.assertEqual(result["skipped_count"], 2)
        self.assertEqual(result["blocked_rows"][0]["pig_id"], "PIG-OLD")
        save_weight.assert_called_once()

    def test_save_bulk_blocks_when_only_duplicate_rows_remain(self):
        preflight_result = {
            "success": False,
            "accepted_count": 0,
            "blocked_count": 1,
            "skipped_count": 0,
            "accepted_rows": [],
            "blocked_rows": [{
                "pig_id": "PIG-OLD",
                "reason": "This pig already has a weight entry for this date.",
            }],
        }

        with patch.object(pig_weights_service, "preflight_bulk_weight_entries", return_value=(preflight_result, 200)):
            result, status = pig_weights_service.save_bulk_weight_entries({"weight_date": "2026-06-01", "rows": []})

        self.assertEqual(status, 409)
        self.assertFalse(result["success"])
        self.assertEqual(result["saved_count"], 0)
        self.assertEqual(result["blocked_count"], 1)

    def test_duplicate_weight_with_new_pen_becomes_movement_only(self):
        active_pigs = [{
            "pig_id": "PIG-1",
            "tag_number": "1",
            "current_pen_id": "PEN-1",
            "current_pen_name": "Old Pen",
        }]
        weight_rows = [{
            "Weight_Log_ID": "WGT-1",
            "Pig_ID": "PIG-1",
            "Weight_Date": "1 June 2026",
            "Weight_Kg": "41",
        }]

        with patch.object(pig_weights_service, "get_active_pigs", return_value=active_pigs), \
             patch.object(pig_weights_service, "get_pens", return_value=[{"pen_id": "PEN-1"}, {"pen_id": "PEN-2"}]), \
             patch.object(pig_weights_service, "get_all_records", return_value=weight_rows):
            result, status = pig_weights_service.preflight_bulk_weight_entries({
                "weight_date": "2026-06-01",
                "rows": [{
                    "pig_id": "PIG-1",
                    "tag_number": "1",
                    "weight_kg": "42",
                    "moved_to_pen_id": "PEN-2",
                }],
            })

        self.assertEqual(status, 200)
        self.assertTrue(result["success"])
        self.assertEqual(result["accepted_count"], 1)
        self.assertEqual(result["duplicate_weight_movement_count"], 1)
        self.assertEqual(result["accepted_rows"][0]["action_type"], "duplicate_weight_movement")
        self.assertTrue(result["accepted_rows"][0]["duplicate_weight"])
        self.assertEqual(result["accepted_rows"][0]["existing_weight"]["weight_log_id"], "WGT-1")

    def test_blank_weight_with_new_pen_becomes_movement_only(self):
        active_pigs = [{
            "pig_id": "PIG-1",
            "tag_number": "1",
            "current_pen_id": "PEN-1",
            "current_pen_name": "Old Pen",
        }]

        with patch.object(pig_weights_service, "get_active_pigs", return_value=active_pigs), \
             patch.object(pig_weights_service, "get_pens", return_value=[{"pen_id": "PEN-1"}, {"pen_id": "PEN-2"}]), \
             patch.object(pig_weights_service, "get_all_records", return_value=[]):
            result, status = pig_weights_service.preflight_bulk_weight_entries({
                "weight_date": "2026-06-01",
                "rows": [{
                    "pig_id": "PIG-1",
                    "tag_number": "1",
                    "weight_kg": "",
                    "moved_to_pen_id": "PEN-2",
                }],
            })

        self.assertEqual(status, 200)
        self.assertTrue(result["success"])
        self.assertEqual(result["accepted_count"], 1)
        self.assertEqual(result["movement_only_count"], 1)
        self.assertEqual(result["accepted_rows"][0]["action_type"], "movement_only")

    def test_save_bulk_logs_duplicate_weight_pen_move_without_new_weight(self):
        preflight_result = {
            "success": True,
            "accepted_count": 1,
            "skipped_count": 0,
            "blocked_count": 0,
            "accepted_rows": [{
                "row_index": 0,
                "action_type": "duplicate_weight_movement",
                "pig_id": "PIG-1",
                "tag_number": "1",
                "weight_date": "2026-06-01",
                "weight_kg": 42.5,
                "weighed_by": "WebApp",
                "current_pen_id": "PEN-1",
                "moved_to_pen_id": "PEN-2",
                "condition_notes": "Moved after weighing",
                "duplicate_weight": True,
            }],
        }

        with patch.object(pig_weights_service, "preflight_bulk_weight_entries", return_value=(preflight_result, 200)), \
             patch.object(pig_weights_service, "_write_bulk_batch_audit", return_value={"warnings": []}), \
             patch.object(pig_weights_service, "save_weight_entry_with_optional_move") as save_weight, \
             patch.object(pig_weights_service, "save_movement_entry", return_value={
                 "success": True,
                 "saved": {"pig_id": "PIG-1", "from_pen_id": "PEN-1", "to_pen_id": "PEN-2"},
             }) as save_move:
            result, status = pig_weights_service.save_bulk_weight_entries({"weight_date": "2026-06-01", "rows": []})

        self.assertEqual(status, 201)
        self.assertTrue(result["success"])
        self.assertEqual(result["saved_count"], 0)
        self.assertEqual(result["movement_count"], 1)
        self.assertEqual(result["duplicate_weight_count"], 1)
        save_weight.assert_not_called()
        save_move.assert_called_once()
        self.assertEqual(save_move.call_args.args[0]["reason_for_move"], "Moved during duplicate weight review")



    def test_save_bulk_71_row_partial_failure_reports_degraded_audit_trail(self):
        accepted_rows = [
            {
                "row_index": index,
                "action_type": "weight",
                "pig_id": f"PIG-{index:02d}",
                "tag_number": str(index),
                "weight_date": "2026-06-15",
                "weight_kg": 60 + index / 10,
                "weighed_by": "WebApp",
                "moved_to_pen_id": "",
                "condition_notes": "",
                "duplicate_weight": False,
            }
            for index in range(71)
        ]
        preflight_result = {
            "success": True,
            "accepted_count": 71,
            "skipped_count": 0,
            "blocked_count": 0,
            "accepted_rows": accepted_rows,
            "blocked_rows": [],
            "skipped_rows": [],
        }

        def save_weight(payload):
            index = int(payload["pig_id"].split("-")[-1])
            if index >= 60:
                return {"success": False, "status": "simulated_sheet_failure", "message": "timeout after 60"}
            return {"success": True, "saved": {"pig_id": payload["pig_id"]}, "movement_logged": False}

        with patch.object(pig_weights_service, "preflight_bulk_weight_entries", return_value=(preflight_result, 200)), \
             patch.object(pig_weights_service, "_write_bulk_batch_audit", return_value={"warnings": []}), \
             patch.object(pig_weights_service, "save_weight_entry_with_optional_move", side_effect=save_weight):
            result, status = pig_weights_service.save_bulk_weight_entries({"weight_date": "2026-06-15", "rows": accepted_rows})

        self.assertEqual(status, 207)
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "partial_failure")
        self.assertEqual(result["operation_id"], result["batch_id"])
        self.assertEqual(result["expected_count"], 71)
        self.assertEqual(result["processed_count"], 71)
        self.assertEqual(result["success_count"], 60)
        self.assertEqual(result["saved_count"], 60)
        self.assertEqual(result["failed_count"], 11)
        self.assertEqual(len(result["row_results"]), 71)
        self.assertIn("No silent partial success", result["message"])
        self.assertFalse(result["writes_to_supabase"])
        self.assertTrue(any(row["status"] == "failed" for row in result["row_results"]))

    def test_save_bulk_retry_same_operation_uses_duplicate_preflight_protection(self):
        preflight_result = {
            "success": False,
            "accepted_count": 0,
            "skipped_count": 0,
            "blocked_count": 1,
            "accepted_rows": [],
            "blocked_rows": [{"row_index": 0, "pig_id": "PIG-1", "reason": "This pig already has a weight entry for this date."}],
            "skipped_rows": [],
        }

        with patch.object(pig_weights_service, "preflight_bulk_weight_entries", return_value=(preflight_result, 200)), \
             patch.object(pig_weights_service, "save_weight_entry_with_optional_move") as save_weight:
            result, status = pig_weights_service.save_bulk_weight_entries({"weight_date": "2026-06-15", "rows": [{"pig_id": "PIG-1"}]})

        self.assertEqual(status, 409)
        self.assertFalse(result["success"])
        self.assertEqual(result["processed_count"], 0)
        self.assertEqual(result["blocked_count"], 1)
        self.assertEqual(result["row_results"][0]["status"], "blocked")
        self.assertFalse(result["writes_to_google_sheets"])
        save_weight.assert_not_called()
if __name__ == "__main__":

    unittest.main()
