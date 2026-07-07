import unittest
from datetime import date
from unittest.mock import patch

from modules.pig_weights import bulk_weight_batch_service, pig_weights_service


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
             patch.object(pig_weights_service.farm_supabase_read_service, "farm_supabase_reads_available", return_value=False), \
             patch.object(pig_weights_service, "get_all_records", return_value=weight_rows):
            result, status = pig_weights_service.preflight_bulk_weight_entries({
                "weight_date": "2026-06-01",
                "rows": [{"pig_id": "PIG-1", "tag_number": "1", "weight_kg": "42"}],
            })

        self.assertEqual(status, 200)
        self.assertFalse(result["success"])
        self.assertEqual(result["blocked_count"], 1)
        self.assertIn("Already recorded for this date", result["blocked_rows"][0]["reason"])
        self.assertEqual(result["blocked_rows"][0]["existing"]["weight_log_id"], "WGT-1")

    def test_preflight_prefers_supabase_weight_events_for_duplicate_check(self):
        active_pigs = [{"pig_id": "PIG-1", "tag_number": "1", "current_pen_id": "PEN-1"}]
        weight_rows = [{
            "Weight_Log_ID": "WGT-SUPA",
            "Pig_ID": "PIG-1",
            "Weight_Date": "2026-06-01",
            "Weight_Kg": 41,
            "source": "supabase_canonical",
        }]

        with patch.object(pig_weights_service, "get_active_pigs", return_value=active_pigs), \
             patch.object(pig_weights_service, "get_pens", return_value=[]), \
             patch.object(pig_weights_service.farm_supabase_read_service, "farm_supabase_reads_available", return_value=True), \
             patch.object(pig_weights_service.farm_supabase_read_service, "get_weight_events_for_date", return_value=weight_rows) as read_weights, \
             patch.object(pig_weights_service, "get_all_records", side_effect=AssertionError("Sheets should not be read")):
            result, status = pig_weights_service.preflight_bulk_weight_entries({
                "weight_date": "2026-06-01",
                "rows": [{"pig_id": "PIG-1", "tag_number": "1", "weight_kg": "42"}],
            })

        self.assertEqual(status, 200)
        self.assertFalse(result["success"])
        self.assertEqual(result["blocked_count"], 1)
        self.assertEqual(result["blocked_rows"][0]["existing"]["weight_log_id"], "WGT-SUPA")
        read_weights.assert_called_once_with(date(2026, 6, 1))

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

    def test_save_bulk_audit_exception_returns_partial_json_summary(self):
        preflight_result = {
            "success": True,
            "accepted_count": 1,
            "skipped_count": 0,
            "blocked_count": 0,
            "accepted_rows": [{
                "pig_id": "PIG-1",
                "weight_date": "2026-06-01",
                "weight_kg": 42.5,
                "weighed_by": "WebApp",
                "moved_to_pen_id": "",
                "condition_notes": "",
            }],
        }

        with patch.object(pig_weights_service, "preflight_bulk_weight_entries", return_value=(preflight_result, 200)), \
             patch.object(pig_weights_service, "_write_bulk_batch_audit", side_effect=RuntimeError("audit timeout")), \
             patch.object(pig_weights_service, "save_weight_entry_with_optional_move", return_value={
                 "success": True,
                 "saved": {"pig_id": "PIG-1"},
                 "movement_logged": False,
             }):
            result, status = pig_weights_service.save_bulk_weight_entries({"weight_date": "2026-06-01", "rows": [{"pig_id": "PIG-1"}]})

        self.assertEqual(status, 207)
        self.assertFalse(result["ok"])
        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "audit_write_failed")
        self.assertEqual(result["saved_count"], 1)
        self.assertEqual(result["success_count"], 1)
        self.assertIn("audit trail failed", result["message"])

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
                "reason": "Already recorded for this date.",
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
                "reason": "Already recorded for this date.",
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
             patch.object(pig_weights_service.farm_supabase_read_service, "farm_supabase_reads_available", return_value=False), \
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

    def test_preflight_73_rows_with_21_pen_changes_has_explainable_counts(self):
        active_pigs = [
            {
                "pig_id": f"PIG-{index:02d}",
                "tag_number": str(index),
                "current_pen_id": "PEN-1",
                "current_pen_name": "Old Pen",
            }
            for index in range(73)
        ]
        rows = []
        for index in range(73):
            row = {
                "pig_id": f"PIG-{index:02d}",
                "tag_number": str(index),
                "weight_kg": "",
                "moved_to_pen_id": "",
                "condition_notes": "",
            }
            if index < 9:
                row["weight_kg"] = str(60 + index)
            elif index < 30:
                row["moved_to_pen_id"] = "PEN-2"
            rows.append(row)

        with patch.object(pig_weights_service, "get_active_pigs", return_value=active_pigs), \
             patch.object(pig_weights_service, "get_pens", return_value=[{"pen_id": "PEN-1"}, {"pen_id": "PEN-2"}]), \
             patch.object(pig_weights_service, "get_all_records", return_value=[]):
            result, status = pig_weights_service.preflight_bulk_weight_entries({
                "weight_date": "2026-06-28",
                "rows": rows,
            })

        self.assertEqual(status, 200)
        self.assertTrue(result["success"])
        self.assertEqual(result["submitted_count"], 73)
        self.assertEqual(result["visible_count"], 73)
        self.assertEqual(result["expected_count"], 30)
        self.assertEqual(result["accepted_count"], 30)
        self.assertEqual(result["weight_count"], 9)
        self.assertEqual(result["movement_only_count"], 21)
        self.assertEqual(result["skipped_count"], 43)
        self.assertEqual(result["processed_count"], 0)
        self.assertEqual(result["failed_count"], 0)

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
            "blocked_rows": [{"row_index": 0, "pig_id": "PIG-1", "reason": "Already recorded for this date."}],
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

    def test_bulk_upload_route_returns_json_on_service_exception(self):
        from app import app
        from modules.pig_weights import pig_weights_routes

        client = app.test_client()
        payload = {
            "weight_date": "2026-06-28",
            "rows": [{"pig_id": "PIG-1", "weight_kg": "61"}],
        }
        with patch.object(pig_weights_routes, "create_bulk_weight_entries", side_effect=RuntimeError("sheet timeout")):
            response = client.post("/api/pig-weights/weights-batch", json=payload)

        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.content_type, "application/json")
        body = response.get_json()
        self.assertFalse(body["ok"])
        self.assertEqual(body["error"], "bulk_upload_exception")
        self.assertEqual(body["endpoint"], "/api/pig-weights/weights-batch")
        self.assertEqual(body["submitted_count"], 1)
        self.assertFalse(body["writes_to_google_sheets"])
        self.assertFalse(body["writes_to_supabase"])

    def test_bulk_preflight_route_returns_json_on_service_exception(self):
        from app import app
        from modules.pig_weights import pig_weights_routes

        client = app.test_client()
        payload = {
            "weight_date": "2026-06-28",
            "rows": [{"pig_id": "PIG-1", "weight_kg": "61"}],
        }
        with patch.object(pig_weights_routes, "preview_bulk_weight_entries", side_effect=RuntimeError("preflight timeout")):
            response = client.post("/api/pig-weights/weights-batch/preflight", json=payload)

        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.content_type, "application/json")
        body = response.get_json()
        self.assertFalse(body["ok"])
        self.assertEqual(body["error"], "bulk_upload_exception")
        self.assertEqual(body["endpoint"], "/api/pig-weights/weights-batch/preflight")
        self.assertEqual(body["submitted_count"], 1)
        self.assertFalse(body["writes_to_google_sheets"])

class DurableBulkWeightBatchServiceTests(unittest.TestCase):
    def setUp(self):
        bulk_weight_batch_service._MEMORY_BATCHES.clear()
        bulk_weight_batch_service._MEMORY_ROWS.clear()

    def _rows_73_with_21_moves(self):
        rows = []
        for index in range(73):
            row = {
                "pig_id": f"PIG-{index:02d}",
                "tag_number": str(index),
                "weight_kg": "",
                "moved_to_pen_id": "",
                "condition_notes": "",
            }
            if index < 52:
                row["weight_kg"] = str(60 + index / 10)
            elif index < 73:
                row["moved_to_pen_id"] = "PEN-2"
            rows.append(row)
        return rows

    def _preflight_for_rows(self, rows):
        accepted = []
        skipped = []
        for index, row in enumerate(rows):
            if row.get("weight_kg"):
                accepted.append({
                    **row,
                    "row_index": index,
                    "weight_date": "2026-06-22",
                    "weighed_by": "WebApp",
                    "current_pen_id": "PEN-1",
                    "action_type": "weight",
                    "weight_kg": float(row["weight_kg"]),
                })
            elif row.get("moved_to_pen_id"):
                accepted.append({
                    **row,
                    "row_index": index,
                    "weight_date": "2026-06-22",
                    "weighed_by": "WebApp",
                    "current_pen_id": "PEN-1",
                    "action_type": "movement_only",
                })
            else:
                skipped.append({**row, "row_index": index, "reason": "No weight or pen change entered."})
        return {
            "success": True,
            "submitted_count": len(rows),
            "visible_count": len(rows),
            "expected_count": len(accepted),
            "accepted_count": len(accepted),
            "weight_count": len([row for row in accepted if row.get("action_type") == "weight"]),
            "movement_only_count": len([row for row in accepted if row.get("action_type") == "movement_only"]),
            "duplicate_weight_movement_count": 0,
            "blocked_count": 0,
            "skipped_count": len(skipped),
            "accepted_rows": accepted,
            "blocked_rows": [],
            "skipped_rows": skipped,
        }

    @patch.dict("os.environ", {"BULK_WEIGHT_BATCH_STORE": "memory"})
    def test_durable_stage_73_rows_with_21_pen_changes_returns_batch_id(self):
        rows = self._rows_73_with_21_moves()
        preflight = self._preflight_for_rows(rows)
        with patch.object(pig_weights_service, "preflight_bulk_weight_entries", return_value=(preflight, 200)):
            result, status = bulk_weight_batch_service.stage_bulk_weight_batch({"draft_id": "DRAFT-73", "weight_date": "2026-06-22", "rows": rows})

        self.assertEqual(status, 201)
        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "staged")
        self.assertTrue(result["batch_id"])
        self.assertEqual(result["counts"]["visible_row_count"], 73)
        self.assertEqual(result["counts"]["actionable_row_count"], 73)
        self.assertEqual(result["counts"]["weight_row_count"], 52)
        self.assertEqual(result["counts"]["movement_row_count"], 21)
        self.assertFalse(result["writes_to_google_sheets"])
        self.assertTrue(result["writes_to_supabase"])


    @patch.dict("os.environ", {"BULK_WEIGHT_BATCH_STORE": "memory"})
    def test_durable_status_reports_remaining_staged_rows(self):
        rows = self._rows_73_with_21_moves()
        preflight = self._preflight_for_rows(rows)
        with patch.object(pig_weights_service, "preflight_bulk_weight_entries", return_value=(preflight, 200)):
            staged, status = bulk_weight_batch_service.stage_bulk_weight_batch({"draft_id": "DRAFT-STATUS", "weight_date": "2026-06-22", "rows": rows})
            status_result, status_code = bulk_weight_batch_service.get_bulk_weight_batch_status(staged["batch_id"])

        self.assertEqual(status, 201)
        self.assertEqual(status_code, 200)
        self.assertEqual(status_result["status"], "staged")
        self.assertEqual(status_result["counts"]["remaining_count"], 73)
        self.assertEqual(status_result["counts"]["visible_row_count"], 73)
        self.assertEqual(status_result["counts"]["movement_row_count"], 21)

    @patch.dict("os.environ", {"BULK_WEIGHT_BATCH_STORE": "memory"})
    def test_durable_processes_only_one_chunk_at_a_time(self):
        rows = self._rows_73_with_21_moves()
        preflight = self._preflight_for_rows(rows)
        with patch.object(pig_weights_service, "preflight_bulk_weight_entries", return_value=(preflight, 200)), \
             patch.object(bulk_weight_batch_service, "save_weight_entry_with_optional_move", return_value={"success": True, "movement_logged": False}), \
             patch.object(bulk_weight_batch_service, "save_movement_entry", return_value={"success": True}):
            staged, _ = bulk_weight_batch_service.stage_bulk_weight_batch({"draft_id": "DRAFT-73", "weight_date": "2026-06-22", "rows": rows})
            result, status = bulk_weight_batch_service.process_bulk_weight_batch(staged["batch_id"], chunk_size=10)

        self.assertEqual(status, 200)
        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "processing")
        self.assertEqual(result["counts"]["success_count"], 10)
        self.assertEqual(result["counts"]["remaining_count"], 63)

    @patch.dict("os.environ", {"BULK_WEIGHT_BATCH_STORE": "memory"})
    def test_durable_processes_all_chunks_to_complete(self):
        rows = self._rows_73_with_21_moves()
        preflight = self._preflight_for_rows(rows)
        with patch.object(pig_weights_service, "preflight_bulk_weight_entries", return_value=(preflight, 200)), \
             patch.object(bulk_weight_batch_service, "save_weight_entry_with_optional_move", return_value={"success": True, "movement_logged": False}), \
             patch.object(bulk_weight_batch_service, "save_movement_entry", return_value={"success": True}):
            staged, _ = bulk_weight_batch_service.stage_bulk_weight_batch({"draft_id": "DRAFT-73", "weight_date": "2026-06-22", "rows": rows})
            batch_id = staged["batch_id"]
            last = staged
            for _ in range(8):
                last, _ = bulk_weight_batch_service.process_bulk_weight_batch(batch_id, chunk_size=10)

        self.assertEqual(last["status"], "complete")
        self.assertEqual(last["counts"]["success_count"], 73)
        self.assertEqual(last["counts"]["remaining_count"], 0)

    @patch.dict("os.environ", {"BULK_WEIGHT_BATCH_STORE": "memory"})
    def test_durable_failure_after_row_60_keeps_failed_rows_and_batch_status(self):
        rows = self._rows_73_with_21_moves()
        preflight = self._preflight_for_rows(rows)
        calls = {"count": 0}

        def next_result():
            calls["count"] += 1
            if calls["count"] > 60:
                return {"success": False, "status": "sheet_timeout", "message": "timeout after row 60"}
            return {"success": True, "movement_logged": False}

        def save_weight(payload):
            return next_result()

        def save_move(payload):
            return next_result()

        with patch.object(pig_weights_service, "preflight_bulk_weight_entries", return_value=(preflight, 200)), \
             patch.object(bulk_weight_batch_service, "save_weight_entry_with_optional_move", side_effect=save_weight), \
             patch.object(bulk_weight_batch_service, "save_movement_entry", side_effect=save_move):
            staged, _ = bulk_weight_batch_service.stage_bulk_weight_batch({"draft_id": "DRAFT-73", "weight_date": "2026-06-22", "rows": rows})
            batch_id = staged["batch_id"]
            for _ in range(8):
                last, _ = bulk_weight_batch_service.process_bulk_weight_batch(batch_id, chunk_size=10)

        self.assertIn(last["status"], {"partial", "failed"})
        self.assertGreater(last["counts"]["failed_count"], 0)
        self.assertEqual(last["counts"]["remaining_count"], 0)
        self.assertTrue(any(row["status"] == "failed" for row in last["rows"]))

    @patch.dict("os.environ", {"BULK_WEIGHT_BATCH_STORE": "memory"})
    def test_durable_retry_does_not_duplicate_success_rows(self):
        rows = self._rows_73_with_21_moves()[:3]
        preflight = self._preflight_for_rows(rows)
        calls = {"weight": 0}

        def save_weight(payload):
            calls["weight"] += 1
            if payload["pig_id"] == "PIG-01":
                return {"success": False, "message": "temporary failure"}
            return {"success": True, "movement_logged": False}

        with patch.object(pig_weights_service, "preflight_bulk_weight_entries", return_value=(preflight, 200)), \
             patch.object(bulk_weight_batch_service, "save_weight_entry_with_optional_move", side_effect=save_weight):
            staged, _ = bulk_weight_batch_service.stage_bulk_weight_batch({"draft_id": "DRAFT-3", "weight_date": "2026-06-22", "rows": rows})
            batch_id = staged["batch_id"]
            first, _ = bulk_weight_batch_service.process_bulk_weight_batch(batch_id, chunk_size=3)
            self.assertEqual(first["counts"]["success_count"], 2)
            self.assertEqual(first["counts"]["failed_count"], 1)
            calls["weight"] = 0
            retry, _ = bulk_weight_batch_service.retry_failed_bulk_weight_batch(batch_id, chunk_size=3)

        self.assertEqual(calls["weight"], 1)
        self.assertEqual(len([row for row in retry["rows"] if row["status"] == "success"]), 2)

    @patch.dict("os.environ", {"BULK_WEIGHT_BATCH_STORE": "memory"})
    def test_durable_process_recovers_interrupted_processing_rows(self):
        rows = self._rows_73_with_21_moves()[:5]
        preflight = self._preflight_for_rows(rows)
        with patch.object(pig_weights_service, "preflight_bulk_weight_entries", return_value=(preflight, 200)), \
             patch.object(bulk_weight_batch_service, "save_weight_entry_with_optional_move", return_value={"success": True, "movement_logged": False}), \
             patch.object(bulk_weight_batch_service, "save_movement_entry", return_value={"success": True}):
            staged, _ = bulk_weight_batch_service.stage_bulk_weight_batch({"draft_id": "DRAFT-INTERRUPTED", "weight_date": "2026-06-22", "rows": rows})
            batch_id = staged["batch_id"]
            batch, stored_rows = bulk_weight_batch_service._memory_get(batch_id)
            stored_rows[0]["status"] = "processing"
            stored_rows[1]["status"] = "processing"
            bulk_weight_batch_service._memory_save(batch, stored_rows)
            result, status = bulk_weight_batch_service.process_bulk_weight_batch(batch_id, chunk_size=2)

        self.assertEqual(status, 200)
        self.assertEqual(result["counts"]["success_count"], 2)
        self.assertEqual(result["counts"]["remaining_count"], 3)
        self.assertTrue(all(row["status"] != "processing" for row in result["rows"][:2]))

    @patch.dict("os.environ", {"BULK_WEIGHT_BATCH_STORE": "memory"})
    def test_durable_process_saves_only_changed_chunk_rows(self):
        rows = self._rows_73_with_21_moves()
        preflight = self._preflight_for_rows(rows)
        original_save_store = bulk_weight_batch_service._save_store

        with patch.object(pig_weights_service, "preflight_bulk_weight_entries", return_value=(preflight, 200)), \
             patch.object(bulk_weight_batch_service, "save_weight_entry_with_optional_move", return_value={"success": True, "movement_logged": False}), \
             patch.object(bulk_weight_batch_service, "save_movement_entry", return_value={"success": True}), \
             patch.object(bulk_weight_batch_service, "_save_store", wraps=original_save_store) as save_store:
            staged, _ = bulk_weight_batch_service.stage_bulk_weight_batch({
                "draft_id": "DRAFT-CHUNK-SAVE",
                "weight_date": "2026-06-22",
                "rows": rows,
            })
            result, status = bulk_weight_batch_service.process_bulk_weight_batch(staged["batch_id"], chunk_size=3)

        self.assertEqual(status, 200)
        self.assertEqual(result["counts"]["success_count"], 3)
        changed_lengths = [
            len(call.kwargs["changed_rows"])
            for call in save_store.call_args_list
            if "changed_rows" in call.kwargs and call.kwargs["changed_rows"] is not None
        ]
        self.assertEqual(changed_lengths, [3, 3])

    @patch.dict("os.environ", {"BULK_WEIGHT_BATCH_STORE": ""})
    def test_durable_process_uses_fast_supabase_writer_outside_memory_mode(self):
        row = {
            "row_id": "ROW-1",
            "row_index": 0,
            "pig_id": "PIG-1",
            "weight_kg": "12.5",
            "from_pen_id": "PEN-1",
            "to_pen_id": "PEN-2",
            "status": "processing",
            "status_reason": "",
            "result_json": {
                "action_type": "weight",
                "preflight": {
                    "weight_date": "2026-06-22",
                    "weighed_by": "WebApp",
                    "condition_notes": "Good",
                },
            },
            "original_row_json": {},
        }

        class Cursor:
            def __init__(self):
                self.statements = []
                self._selects = 0

            def execute(self, sql, params=None):
                self.statements.append((sql, params))
                if "select 1 from public." in sql:
                    self._selects += 1

            def fetchone(self):
                return None

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

        class Connection:
            def __init__(self):
                self.cursor_obj = Cursor()

            def cursor(self):
                return self.cursor_obj

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

        connection = Connection()

        with patch.object(bulk_weight_batch_service.farm_supabase_write_service, "farm_supabase_writes_available", return_value=True), \
             patch.object(bulk_weight_batch_service, "_connect", return_value=connection), \
             patch.object(bulk_weight_batch_service, "save_weight_entry_with_optional_move") as legacy_weight, \
             patch.object(bulk_weight_batch_service, "save_movement_entry") as legacy_move:
            bulk_weight_batch_service._process_one_row(row)

        self.assertEqual(row["status"], "success")
        self.assertEqual(row["status_reason"], "Weight saved. Movement saved.")
        inserts = [statement for statement, _params in connection.cursor_obj.statements if "insert into public." in statement]
        self.assertEqual(len(inserts), 2)
        self.assertTrue(any("public.pig_weight_events" in statement for statement in inserts))
        self.assertTrue(any("public.pig_location_events" in statement for statement in inserts))
        legacy_weight.assert_not_called()
        legacy_move.assert_not_called()

    @patch.dict("os.environ", {"BULK_WEIGHT_BATCH_STORE": ""})
    def test_durable_process_row_reuses_supplied_supabase_connection(self):
        row = {
            "row_id": "ROW-1",
            "batch_id": "11111111-1111-1111-1111-111111111111",
            "row_index": 0,
            "pig_id": "PIG-1",
            "weight_kg": "12.5",
            "from_pen_id": "PEN-1",
            "to_pen_id": "",
            "status": "processing",
            "status_reason": "",
            "result_json": {
                "action_type": "weight",
                "preflight": {
                    "weight_date": "2026-06-22",
                    "weighed_by": "WebApp",
                    "condition_notes": "Good",
                },
            },
            "original_row_json": {},
        }

        class Cursor:
            def __init__(self):
                self.statements = []

            def execute(self, sql, params=None):
                self.statements.append((sql, params))

            def fetchone(self):
                return None

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

        class Connection:
            def __init__(self):
                self.cursor_obj = Cursor()

            def cursor(self):
                return self.cursor_obj

        connection = Connection()

        with patch.object(bulk_weight_batch_service.farm_supabase_write_service, "farm_supabase_writes_available", return_value=True), \
             patch.object(bulk_weight_batch_service, "_connect") as connect:
            bulk_weight_batch_service._process_one_row(row, connection=connection)

        connect.assert_not_called()
        self.assertEqual(row["status"], "success")
        self.assertTrue(any("insert into public.pig_weight_events" in statement for statement, _params in connection.cursor_obj.statements))

    @patch.dict("os.environ", {"BULK_WEIGHT_BATCH_STORE": "memory"})
    def test_durable_stage_route_returns_json_on_store_exception(self):
        from app import app
        from modules.pig_weights import pig_weights_routes

        client = app.test_client()
        with patch.object(pig_weights_routes, "stage_bulk_weight_batch", side_effect=RuntimeError("database unavailable")):
            response = client.post("/api/pig-weights/bulk-batches", json={"weight_date": "2026-06-22", "rows": [{"pig_id": "PIG-1", "weight_kg": "61"}]})

        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.content_type, "application/json")
        body = response.get_json()
        self.assertFalse(body["ok"])
        self.assertEqual(body["endpoint"], "/api/pig-weights/bulk-batches")
        self.assertFalse(body["writes_to_google_sheets"])
        self.assertFalse(body["writes_to_supabase"])

    @patch.dict("os.environ", {"BULK_WEIGHT_BATCH_STORE": "memory"})
    def test_durable_process_route_returns_json_on_service_exception(self):
        from app import app
        from modules.pig_weights import pig_weights_routes

        client = app.test_client()
        with patch.object(pig_weights_routes, "process_bulk_weight_batch", side_effect=RuntimeError("process crashed")):
            response = client.post("/api/pig-weights/bulk-batches/BATCH-1/process", json={"chunk_size": 3})

        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.content_type, "application/json")
        body = response.get_json()
        self.assertFalse(body["ok"])
        self.assertEqual(body["endpoint"], "/api/pig-weights/bulk-batches/BATCH-1/process")
        self.assertFalse(body["writes_to_google_sheets"])

    @patch.dict("os.environ", {"BULK_WEIGHT_BATCH_STORE": "memory"})
    def test_durable_duplicate_weight_without_move_is_already_recorded_not_blocking(self):
        rows = [{"pig_id": "PIG-1", "tag_number": "1", "weight_kg": "61", "moved_to_pen_id": "", "condition_notes": ""}]
        preflight = {
            "success": False,
            "submitted_count": 1,
            "visible_count": 1,
            "expected_count": 0,
            "accepted_count": 0,
            "weight_count": 0,
            "movement_only_count": 0,
            "duplicate_weight_movement_count": 0,
            "blocked_count": 1,
            "skipped_count": 0,
            "accepted_rows": [],
            "blocked_rows": [{"row_index": 0, "pig_id": "PIG-1", "tag_number": "1", "reason": "Already recorded for this date."}],
            "skipped_rows": [],
        }
        with patch.object(pig_weights_service, "preflight_bulk_weight_entries", return_value=(preflight, 200)):
            staged, status = bulk_weight_batch_service.stage_bulk_weight_batch({"draft_id": "DRAFT-DUP", "weight_date": "2026-06-22", "rows": rows})
            result, process_status = bulk_weight_batch_service.process_bulk_weight_batch(staged["batch_id"], chunk_size=10)

        self.assertEqual(status, 201)
        self.assertEqual(process_status, 200)
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["counts"]["duplicate_count"], 1)
        self.assertEqual(result["counts"]["blocked_count"], 0)
        self.assertEqual(result["counts"]["remaining_count"], 0)
        self.assertEqual(result["rows"][0]["status"], "duplicate")
        self.assertEqual(result["rows"][0]["status_reason"], "Already recorded for this date.")

if __name__ == "__main__":

    unittest.main()
