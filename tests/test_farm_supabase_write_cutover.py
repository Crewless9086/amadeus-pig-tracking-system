import unittest
from datetime import date
from unittest.mock import patch

from modules.pig_weights import pig_weights_service


class FarmSupabaseWriteCutoverTests(unittest.TestCase):
    def test_save_new_pen_prefers_supabase(self):
        cleaned = {
            "pen_name": "Farrowing 1",
            "pen_type": "Farrowing",
            "capacity": 4,
            "is_active": "Yes",
            "pen_notes": "",
        }
        with patch.object(pig_weights_service.farm_supabase_write_service, "farm_supabase_writes_available", return_value=True), \
             patch.object(pig_weights_service, "generate_pen_id", return_value="PEN-1"), \
             patch.object(pig_weights_service.farm_supabase_write_service, "insert_pen") as insert_pen, \
             patch.object(pig_weights_service, "append_row") as append_row:
            result = pig_weights_service.save_new_pen(cleaned)

        self.assertTrue(result["success"])
        self.assertEqual(result["pen_id"], "PEN-1")
        self.assertTrue(result["source"]["writes_to_supabase"])
        insert_pen.assert_called_once_with("PEN-1", cleaned)
        append_row.assert_not_called()

    def test_save_new_product_prefers_supabase(self):
        cleaned = {
            "product_name": "Iron",
            "product_category": "Treatment",
            "default_dose": 1,
            "dose_unit": "ml",
            "default_withdrawal_days": 0,
            "supplier": "",
            "batch_tracking_required": "No",
            "is_active": "Yes",
            "product_notes": "",
        }
        with patch.object(pig_weights_service.farm_supabase_write_service, "farm_supabase_writes_available", return_value=True), \
             patch.object(pig_weights_service, "generate_product_id", return_value="PRD-1"), \
             patch.object(pig_weights_service.farm_supabase_write_service, "insert_product") as insert_product, \
             patch.object(pig_weights_service, "append_row") as append_row:
            result = pig_weights_service.save_new_product(cleaned)

        self.assertTrue(result["success"])
        self.assertEqual(result["product_id"], "PRD-1")
        insert_product.assert_called_once_with("PRD-1", cleaned)
        append_row.assert_not_called()

    def test_save_weight_entry_prefers_supabase_and_checks_duplicate_there(self):
        cleaned = {
            "pig_id": "PIG-1",
            "weight_date": date(2026, 6, 29),
            "weight_kg": 42.5,
            "weighed_by": "Tester",
            "condition_notes": "",
        }
        with patch.object(pig_weights_service.farm_supabase_write_service, "farm_supabase_writes_available", return_value=True), \
             patch.object(pig_weights_service.farm_supabase_write_service, "get_weight_event", return_value=None) as get_existing, \
             patch.object(pig_weights_service, "generate_weight_log_id", return_value="WGT-1"), \
             patch.object(pig_weights_service.farm_supabase_write_service, "insert_weight_event") as insert_weight, \
             patch.object(pig_weights_service, "get_latest_weight_for_pig", return_value={"pig_id": "PIG-1"}), \
             patch.object(pig_weights_service, "get_all_records") as get_records, \
             patch.object(pig_weights_service, "append_row") as append_row:
            result = pig_weights_service.save_weight_entry(cleaned)

        self.assertTrue(result["success"])
        self.assertTrue(result["source"]["writes_to_supabase"])
        get_existing.assert_called_once_with("PIG-1", date(2026, 6, 29))
        insert_weight.assert_called_once_with("WGT-1", cleaned)
        get_records.assert_not_called()
        append_row.assert_not_called()

    def test_save_weight_entry_reports_supabase_duplicate(self):
        cleaned = {
            "pig_id": "PIG-1",
            "weight_date": date(2026, 6, 29),
            "weight_kg": 42.5,
            "weighed_by": "Tester",
            "condition_notes": "",
        }
        existing = {
            "weight_event_id": "WGT-OLD",
            "pig_id": "PIG-1",
            "weight_date": date(2026, 6, 29),
            "weight_kg": 42.5,
            "weighed_by": "Owner",
            "condition_notes": "ok",
        }
        with patch.object(pig_weights_service.farm_supabase_write_service, "farm_supabase_writes_available", return_value=True), \
             patch.object(pig_weights_service.farm_supabase_write_service, "get_weight_event", return_value=existing), \
             patch.object(pig_weights_service, "append_row") as append_row:
            result = pig_weights_service.save_weight_entry(cleaned)

        self.assertFalse(result["success"])
        self.assertTrue(result["duplicate_weight"])
        self.assertEqual(result["existing"]["weight_log_id"], "WGT-OLD")
        append_row.assert_not_called()

    def test_save_treatment_entry_prefers_supabase(self):
        cleaned = {
            "pig_id": "PIG-1",
            "treatment_date": date(2026, 6, 29),
            "treatment_type": "Iron",
            "product_id": "PRD-1",
            "dose": 1,
            "dose_unit": "",
            "route": "IM",
            "reason_for_treatment": "Routine",
            "batch_lot_number": "",
            "given_by": "Tester",
            "follow_up_required": "No",
            "follow_up_date": None,
            "medical_notes": "",
        }
        product = {"product_name": "Iron", "dose_unit": "ml", "default_withdrawal_days": 0}
        with patch.object(pig_weights_service.farm_supabase_write_service, "farm_supabase_writes_available", return_value=True), \
             patch.object(pig_weights_service, "generate_medical_log_id", return_value="MED-1"), \
             patch.object(pig_weights_service, "get_product_by_id", return_value=product), \
             patch.object(pig_weights_service.farm_supabase_write_service, "insert_medical_event") as insert_medical, \
             patch.object(pig_weights_service, "append_row") as append_row:
            result = pig_weights_service.save_treatment_entry(cleaned)

        self.assertTrue(result["success"])
        self.assertTrue(result["source"]["writes_to_supabase"])
        insert_medical.assert_called_once()
        append_row.assert_not_called()

    def test_save_movement_entry_prefers_supabase(self):
        cleaned = {
            "pig_id": "PIG-1",
            "move_date": date(2026, 6, 29),
            "from_pen_id": "PEN-1",
            "to_pen_id": "PEN-2",
            "reason_for_move": "Routine",
            "moved_by": "Tester",
            "move_notes": "",
        }
        with patch.object(pig_weights_service.farm_supabase_write_service, "farm_supabase_writes_available", return_value=True), \
             patch.object(pig_weights_service, "generate_move_log_id", return_value="MOV-1"), \
             patch.object(pig_weights_service.farm_supabase_write_service, "insert_location_event") as insert_location, \
             patch.object(pig_weights_service, "get_pen_by_id", side_effect=lambda pen_id: {"pen_name": pen_id}), \
             patch.object(pig_weights_service, "append_row") as append_row:
            result = pig_weights_service.save_movement_entry(cleaned)

        self.assertTrue(result["success"])
        self.assertTrue(result["source"]["writes_to_supabase"])
        insert_location.assert_called_once_with("MOV-1", cleaned)
        append_row.assert_not_called()


if __name__ == "__main__":
    unittest.main()
