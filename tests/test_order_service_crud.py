import unittest
from datetime import datetime
from unittest.mock import patch

from modules.orders import order_write


def cleaned_order(**overrides):
    data = {
        "order_date": datetime(2026, 5, 18),
        "customer_name": "Test Customer",
        "customer_phone": "0820000000",
        "customer_channel": "WhatsApp",
        "customer_language": "English",
        "order_source": "Sam",
        "order_stream": "Livestock",
        "requested_category": "Grower",
        "requested_weight_range": "40_to_44_Kg",
        "requested_sex": "Any",
        "requested_quantity": 1,
        "quoted_total": 1500,
        "collection_location": "Riversdale",
        "payment_method": "Cash",
        "notes": "Test order",
        "created_by": "Tester",
        "conversation_id": "1774",
    }
    data.update(overrides)
    return data


def available_pig(**overrides):
    pig = {
        "pig_id": "PIG-1",
        "tag_number": "001",
        "sale_category": "Grower Pigs",
        "weight_band": "40_to_44_Kg",
        "sex": "Male",
        "current_weight_kg": 42,
        "reserved_status": "Not_Reserved",
    }
    pig.update(overrides)
    return pig


class OrderCrudServiceTests(unittest.TestCase):
    def test_create_order_appends_draft_defaults_and_status_log(self):
        with patch.object(order_write, "generate_order_id", return_value="ORD-1"), \
             patch.object(order_write, "append_row") as append_row, \
             patch.object(order_write, "write_order_status_log") as write_log:
            result = order_write.create_order(cleaned_order())

        self.assertTrue(result["success"])
        self.assertEqual(result["order_id"], "ORD-1")

        append_row.assert_called_once()
        sheet_name, row_values = append_row.call_args.args
        self.assertEqual(sheet_name, order_write.ORDER_MASTER_SHEET)
        self.assertEqual(row_values[0], "ORD-1")
        self.assertEqual(row_values[13], "Draft")
        self.assertEqual(row_values[14], "Pending")
        self.assertEqual(row_values[15], "Collection_Only")
        self.assertEqual(row_values[18], "Pending")
        self.assertEqual(row_values[19], 0)
        self.assertEqual(row_values[24], "Cash")
        self.assertEqual(row_values[25], "1774")

        write_log.assert_called_once()
        self.assertEqual(write_log.call_args.kwargs["new_status"], "Draft")
        self.assertEqual(write_log.call_args.kwargs["notes"], "Order created")

    def test_create_order_returns_warning_when_status_log_fails(self):
        with patch.object(order_write, "generate_order_id", return_value="ORD-1"), \
             patch.object(order_write, "append_row"), \
             patch.object(order_write, "write_order_status_log", side_effect=Exception("log failed")):
            result = order_write.create_order(cleaned_order())

        self.assertTrue(result["success"])
        self.assertIn("status log could not be written", result["warning"])

    def test_update_order_updates_allowed_fields_and_locks_payment_beyond_draft(self):
        with patch.object(order_write, "_get_order_master_row", return_value={"Order_ID": "ORD-1", "Order_Status": "Draft"}), \
             patch.object(order_write, "_update_sheet_row_by_id") as update_row:
            result = order_write.update_order(
                "ORD-1",
                {
                    "requested_quantity": 2,
                    "collection_location": "Albertinia",
                    "payment_method": "EFT",
                    "changed_by": "Tester",
                },
            )

        self.assertTrue(result["success"])
        self.assertEqual(result["updated_fields"], ["requested_quantity", "collection_location", "payment_method"])
        sheet_name, order_id, updates = update_row.call_args.args
        self.assertEqual(sheet_name, order_write.ORDER_MASTER_SHEET)
        self.assertEqual(order_id, "ORD-1")
        self.assertEqual(updates["Requested_Quantity"], 2)
        self.assertEqual(updates["Collection_Location"], "Albertinia")
        self.assertEqual(updates["Payment_Method"], "EFT")

        with patch.object(order_write, "_get_order_master_row", return_value={"Order_ID": "ORD-1", "Order_Status": "Approved"}):
            with self.assertRaisesRegex(ValueError, "Payment method cannot be changed"):
                order_write.update_order("ORD-1", {"payment_method": "Cash"})

    def test_update_order_blocks_missing_terminal_and_empty_updates(self):
        with patch.object(order_write, "_get_order_master_row", return_value=None):
            with self.assertRaisesRegex(ValueError, "Order not found"):
                order_write.update_order("ORD-MISSING", {"notes": "x"})

        with patch.object(order_write, "_get_order_master_row", return_value={"Order_Status": "Completed"}):
            with self.assertRaisesRegex(ValueError, "can no longer be edited"):
                order_write.update_order("ORD-1", {"notes": "x"})

        with patch.object(order_write, "_get_order_master_row", return_value={"Order_Status": "Draft"}):
            with self.assertRaisesRegex(ValueError, "No valid order fields"):
                order_write.update_order("ORD-1", {"changed_by": "Tester"})

    def test_update_order_saves_conversation_id_beyond_draft(self):
        with patch.object(order_write, "_get_order_master_row", return_value={"Order_ID": "ORD-1", "Order_Status": "Approved"}), \
             patch.object(order_write, "_update_sheet_row_by_id") as update_row:
            result = order_write.update_order(
                "ORD-1",
                {"conversation_id": "1871", "changed_by": "Tester"},
            )

        self.assertEqual(result["updated_fields"], ["conversation_id"])
        self.assertEqual(update_row.call_args.args[2]["Conversation_ID"], "1871")

    def test_create_order_line_appends_available_pig_with_defaults(self):
        with patch.object(order_write, "get_available_pigs_for_orders", return_value=[available_pig()]), \
             patch.object(order_write, "get_all_records", return_value=[]), \
             patch.object(order_write, "generate_order_line_id", return_value="OL-1"), \
             patch.object(order_write, "append_row") as append_row:
            result = order_write.create_order_line({
                "order_id": "ORD-1",
                "pig_id": "PIG-1",
                "unit_price": 1500,
                "notes": "Line note",
                "request_item_key": "primary_1",
            })

        self.assertTrue(result["success"])
        sheet_name, row_values = append_row.call_args.args
        self.assertEqual(sheet_name, order_write.ORDER_LINES_SHEET)
        self.assertEqual(row_values[0], "OL-1")
        self.assertEqual(row_values[1], "ORD-1")
        self.assertEqual(row_values[2], "PIG-1")
        self.assertEqual(row_values[9], "Draft")
        self.assertEqual(row_values[10], "Not_Reserved")
        self.assertEqual(row_values[14], "primary_1")

    def test_create_order_line_resolves_blank_price_automatically(self):
        with patch.object(order_write, "get_available_pigs_for_orders", return_value=[available_pig()]), \
             patch.object(order_write, "get_all_records", return_value=[]), \
             patch.object(order_write, "generate_order_line_id", return_value="OL-1"), \
             patch("modules.sales.sam_pricing.resolve_live_stock_price_rule", return_value={
                 "found": True,
                 "unit_price": 800,
                 "source": "supabase",
             }), \
             patch.object(order_write, "append_row") as append_row:
            result = order_write.create_order_line({
                "order_id": "ORD-1",
                "pig_id": "PIG-1",
                "unit_price": None,
                "notes": "",
            })

        self.assertTrue(result["success"])
        self.assertEqual(append_row.call_args.args[1][8], 800)

    def test_create_order_line_blocks_unavailable_duplicate_and_reserved_pigs(self):
        with patch.object(order_write, "get_available_pigs_for_orders", return_value=[]):
            with self.assertRaisesRegex(ValueError, "not available"):
                order_write.create_order_line({"order_id": "ORD-1", "pig_id": "PIG-1"})

        with patch.object(order_write, "get_available_pigs_for_orders", return_value=[available_pig()]), \
             patch.object(order_write, "get_all_records", return_value=[{"Pig_ID": "PIG-1", "Reserved_Status": "Reserved"}]):
            with self.assertRaisesRegex(ValueError, "already reserved"):
                order_write.create_order_line({"order_id": "ORD-1", "pig_id": "PIG-1"})

        with patch.object(order_write, "get_available_pigs_for_orders", return_value=[available_pig()]), \
             patch.object(order_write, "get_all_records", return_value=[{"Pig_ID": "PIG-1", "Order_ID": "ORD-1", "Line_Status": "Draft"}]):
            with self.assertRaisesRegex(ValueError, "already on this order"):
                order_write.create_order_line({"order_id": "ORD-1", "pig_id": "PIG-1"})

    def test_update_order_line_updates_active_line_and_blocks_terminal(self):
        with patch.object(order_write, "_get_order_line_row", return_value={"Order_Line_ID": "OL-1", "Line_Status": "Draft"}), \
             patch.object(order_write, "_update_sheet_row_by_id") as update_row:
            result = order_write.update_order_line("OL-1", {"unit_price": 1550, "notes": "Updated"})

        self.assertTrue(result["success"])
        sheet_name, line_id, updates = update_row.call_args.args
        self.assertEqual(sheet_name, order_write.ORDER_LINES_SHEET)
        self.assertEqual(line_id, "OL-1")
        self.assertEqual(updates["Unit_Price"], 1550)
        self.assertEqual(updates["Notes"], "Updated")

        with patch.object(order_write, "_get_order_line_row", return_value={"Line_Status": "Collected"}):
            with self.assertRaisesRegex(ValueError, "can no longer be edited"):
                order_write.update_order_line("OL-1", {"unit_price": 1550, "notes": "Updated"})

    def test_delete_order_line_marks_active_line_cancelled_and_blocks_reserved_or_terminal(self):
        with patch.object(order_write, "_get_order_line_row", return_value={"Order_Line_ID": "OL-1", "Line_Status": "Draft", "Reserved_Status": "Not_Reserved"}), \
             patch.object(order_write, "_update_sheet_row_by_id") as update_row:
            result = order_write.delete_order_line("OL-1")

        self.assertTrue(result["success"])
        sheet_name, line_id, updates = update_row.call_args.args
        self.assertEqual(sheet_name, order_write.ORDER_LINES_SHEET)
        self.assertEqual(line_id, "OL-1")
        self.assertEqual(updates["Line_Status"], "Cancelled")
        self.assertEqual(updates["Reserved_Status"], "Not_Reserved")

        with patch.object(order_write, "_get_order_line_row", return_value={"Line_Status": "Draft", "Reserved_Status": "Reserved"}):
            with self.assertRaisesRegex(ValueError, "Release this line"):
                order_write.delete_order_line("OL-1")

        with patch.object(order_write, "_get_order_line_row", return_value={"Line_Status": "Collected", "Reserved_Status": "Not_Reserved"}):
            with self.assertRaisesRegex(ValueError, "can no longer be deleted"):
                order_write.delete_order_line("OL-1")


if __name__ == "__main__":
    unittest.main()
