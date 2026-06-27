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
            "skipped_count": 2,
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

        self.assertEqual(status, 201)
        self.assertTrue(result["success"])
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

    def test_saved_weight_does_not_fail_when_latest_lookup_fails(self):
        with patch.object(pig_weights_service, "get_all_records", return_value=[]), \
             patch.object(pig_weights_service, "append_row") as append_row, \
             patch.object(pig_weights_service, "get_latest_weight_for_pig", side_effect=RuntimeError("quota")):
            result = pig_weights_service.save_weight_entry({
                "pig_id": "PIG-1",
                "weight_date": date(2026, 6, 1),
                "weight_kg": 42.5,
                "weighed_by": "WebApp",
                "condition_notes": "",
                "allow_duplicate": False,
            })

        self.assertTrue(result["success"])
        self.assertIn("warnings", result)
        self.assertIn("latest weight lookup failed", result["warnings"][0])
        append_row.assert_called_once()

    def test_saved_movement_does_not_fail_when_pen_lookup_fails(self):
        with patch.object(pig_weights_service, "append_row") as append_row, \
             patch.object(pig_weights_service, "get_pen_by_id", side_effect=RuntimeError("quota")):
            result = pig_weights_service.save_movement_entry({
                "pig_id": "PIG-1",
                "move_date": date(2026, 6, 1),
                "from_pen_id": "PEN-1",
                "to_pen_id": "PEN-2",
                "reason_for_move": "Moved during weight capture",
                "moved_by": "WebApp",
                "move_notes": "",
            })

        self.assertTrue(result["success"])
        self.assertIn("warnings", result)
        self.assertIn("pen name lookup failed", result["warnings"][0])
        append_row.assert_called_once()


if __name__ == "__main__":
    unittest.main()
