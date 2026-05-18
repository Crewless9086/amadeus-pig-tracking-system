import unittest
from unittest.mock import patch

from modules.orders import order_lifecycle


def draft_order(**overrides):
    row = {
        "Order_ID": "ORD-1",
        "Order_Status": "Draft",
        "Approval_Status": "Pending",
        "Payment_Method": "Cash",
        "Customer_Name": "Test Customer",
        "Collection_Location": "Riversdale",
    }
    row.update(overrides)
    return row


ORDER_LINES_HEADERS = [
    "Order_Line_ID",
    "Order_ID",
    "Pig_ID",
    "Line_Status",
    "Reserved_Status",
    "Updated_At",
]


class OrderLifecycleServiceTests(unittest.TestCase):
    def test_send_order_for_approval_updates_draft_and_logs_status(self):
        lines = [
            {"Order_ID": "ORD-1", "Order_Line_ID": "OL-1", "Line_Status": "Draft"},
        ]

        with patch.object(order_lifecycle, "_get_order_master_row", return_value=draft_order()), \
             patch.object(order_lifecycle, "get_all_records", return_value=lines), \
             patch.object(order_lifecycle, "_update_sheet_row_by_id") as update_order, \
             patch.object(order_lifecycle, "_write_order_status_log") as write_log, \
             patch.object(order_lifecycle, "_notify_n8n_order_approval_request", return_value={"sent": True}):
            result = order_lifecycle.send_order_for_approval("ORD-1", changed_by="Tester")

        self.assertTrue(result["success"])
        self.assertEqual(result["order_id"], "ORD-1")
        self.assertTrue(result["n8n_notified"])

        update_order.assert_called_once()
        sheet_name, order_id, updates = update_order.call_args.args
        self.assertEqual(sheet_name, order_lifecycle.ORDER_MASTER_SHEET)
        self.assertEqual(order_id, "ORD-1")
        self.assertEqual(updates["Order_Status"], "Pending_Approval")
        self.assertEqual(updates["Approval_Status"], "Pending")

        write_log.assert_called_once()
        log_kwargs = write_log.call_args.kwargs
        self.assertEqual(log_kwargs["old_status"], "Draft | Pending")
        self.assertEqual(log_kwargs["new_status"], "Pending_Approval | Pending")

    def test_send_order_for_approval_requires_draft_status(self):
        with patch.object(order_lifecycle, "_get_order_master_row", return_value=draft_order(Order_Status="Approved")):
            with self.assertRaisesRegex(ValueError, "Only Draft orders"):
                order_lifecycle.send_order_for_approval("ORD-1")

    def test_send_order_for_approval_requires_payment_method(self):
        with patch.object(order_lifecycle, "_get_order_master_row", return_value=draft_order(Payment_Method="")):
            with self.assertRaisesRegex(ValueError, "Payment method must be set"):
                order_lifecycle.send_order_for_approval("ORD-1")

    def test_send_order_for_approval_requires_customer_name(self):
        with patch.object(order_lifecycle, "_get_order_master_row", return_value=draft_order(Customer_Name="")):
            with self.assertRaisesRegex(ValueError, "Customer name is required"):
                order_lifecycle.send_order_for_approval("ORD-1")

    def test_send_order_for_approval_requires_collection_location(self):
        with patch.object(order_lifecycle, "_get_order_master_row", return_value=draft_order(Collection_Location="")):
            with self.assertRaisesRegex(ValueError, "Collection location is required"):
                order_lifecycle.send_order_for_approval("ORD-1")

    def test_send_order_for_approval_requires_active_lines(self):
        lines = [
            {"Order_ID": "ORD-1", "Order_Line_ID": "OL-1", "Line_Status": "Cancelled"},
            {"Order_ID": "OTHER", "Order_Line_ID": "OL-2", "Line_Status": "Draft"},
        ]

        with patch.object(order_lifecycle, "_get_order_master_row", return_value=draft_order()), \
             patch.object(order_lifecycle, "get_all_records", return_value=lines):
            with self.assertRaisesRegex(ValueError, "At least one active order line"):
                order_lifecycle.send_order_for_approval("ORD-1")

    def test_approve_order_keeps_approval_when_auto_reserve_warns(self):
        pending_row = draft_order(Order_Status="Pending_Approval", Approval_Status="Pending")
        approved_row = draft_order(Order_Status="Approved", Approval_Status="Approved")
        reserve_result = {
            "success": False,
            "message": "No lines could be reserved.",
            "errors": ["No eligible lines to reserve."],
        }

        with patch.object(order_lifecycle, "_get_order_master_row", side_effect=[pending_row, approved_row]), \
             patch.object(order_lifecycle, "_update_sheet_row_by_id") as update_order, \
             patch.object(order_lifecycle, "_write_order_status_log") as write_log, \
             patch.object(order_lifecycle, "reserve_order_lines", return_value=reserve_result), \
             patch.object(order_lifecycle, "_notify_order_customer_notification", return_value={"sent": True}), \
             patch.object(order_lifecycle, "_add_notification_result_to_response") as add_notification:
            result = order_lifecycle.approve_order("ORD-1", changed_by="Tester")

        self.assertTrue(result["success"])
        self.assertEqual(result["order_id"], "ORD-1")
        self.assertEqual(result["auto_reserve"], reserve_result)
        self.assertEqual(result["reserve_warning"], "No lines could be reserved.")
        self.assertEqual(result["warning"], "No lines could be reserved.")

        update_order.assert_called_once()
        update_args = update_order.call_args.args
        self.assertEqual(update_args[0], order_lifecycle.ORDER_MASTER_SHEET)
        self.assertEqual(update_args[1], "ORD-1")
        self.assertEqual(update_args[2]["Order_Status"], "Approved")
        self.assertEqual(update_args[2]["Approval_Status"], "Approved")

        self.assertEqual(write_log.call_count, 2)
        self.assertEqual(write_log.call_args_list[0].kwargs["new_status"], "Approved | Approved")
        self.assertIn("manual follow-up", write_log.call_args_list[1].kwargs["notes"])
        add_notification.assert_called_once()

    def test_approve_order_requires_pending_approval_status(self):
        with patch.object(order_lifecycle, "_get_order_master_row", return_value=draft_order(Order_Status="Draft")):
            with self.assertRaisesRegex(ValueError, "Only Pending_Approval orders"):
                order_lifecycle.approve_order("ORD-1")

    def test_reject_order_cancels_active_lines_and_marks_rejected(self):
        order_row = draft_order(Order_Status="Pending_Approval", Approval_Status="Pending")
        cancelled_row = draft_order(Order_Status="Cancelled", Approval_Status="Rejected")
        lines = [
            {"Order_ID": "ORD-1", "Order_Line_ID": "OL-1", "Line_Status": "Draft"},
            {"Order_ID": "ORD-1", "Order_Line_ID": "OL-2", "Line_Status": "Reserved"},
            {"Order_ID": "ORD-1", "Order_Line_ID": "OL-3", "Line_Status": "Cancelled"},
            {"Order_ID": "ORD-1", "Order_Line_ID": "OL-4", "Line_Status": "Collected"},
            {"Order_ID": "OTHER", "Order_Line_ID": "OL-5", "Line_Status": "Draft"},
        ]

        with patch.object(order_lifecycle, "_get_order_master_row", side_effect=[order_row, cancelled_row]), \
             patch.object(order_lifecycle, "get_all_records", return_value=lines), \
             patch.object(order_lifecycle, "_cancel_order_lines", return_value=2) as cancel_lines, \
             patch.object(order_lifecycle, "_update_sheet_row_by_id") as update_order, \
             patch.object(order_lifecycle, "_write_order_status_log") as write_log, \
             patch.object(order_lifecycle, "_notify_order_customer_notification", return_value={"sent": True}), \
             patch.object(order_lifecycle, "_add_notification_result_to_response") as add_notification:
            result = order_lifecycle.reject_order("ORD-1", changed_by="Tester")

        self.assertTrue(result["success"])
        self.assertEqual(result["cancelled_line_count"], 2)
        self.assertEqual(result["reserved_pig_count"], 0)
        cancel_lines.assert_called_once_with(["OL-1", "OL-2"])

        update_args = update_order.call_args.args
        self.assertEqual(update_args[0], order_lifecycle.ORDER_MASTER_SHEET)
        self.assertEqual(update_args[1], "ORD-1")
        self.assertEqual(update_args[2]["Order_Status"], "Cancelled")
        self.assertEqual(update_args[2]["Approval_Status"], "Rejected")
        self.assertEqual(update_args[2]["Reserved_Pig_Count"], 0)

        write_log.assert_called_once()
        log_kwargs = write_log.call_args.kwargs
        self.assertEqual(log_kwargs["old_status"], "Pending_Approval | Pending")
        self.assertEqual(log_kwargs["new_status"], "Cancelled | Rejected")
        self.assertIn("2 line(s) cancelled", log_kwargs["notes"])
        add_notification.assert_called_once()

    def test_reject_order_blocks_completed_orders(self):
        with patch.object(order_lifecycle, "_get_order_master_row", return_value=draft_order(Order_Status="Completed")):
            with self.assertRaisesRegex(ValueError, "Completed orders cannot be rejected"):
                order_lifecycle.reject_order("ORD-1")

    def test_cancel_order_cancels_active_lines_and_marks_customer_cancelled(self):
        order_row = draft_order(Order_Status="Draft", Approval_Status="Pending")
        lines = [
            {"Order_ID": "ORD-1", "Order_Line_ID": "OL-1", "Line_Status": "Draft"},
            {"Order_ID": "ORD-1", "Order_Line_ID": "OL-2", "Line_Status": "Reserved"},
            {"Order_ID": "ORD-1", "Order_Line_ID": "OL-3", "Line_Status": "Cancelled"},
            {"Order_ID": "ORD-1", "Order_Line_ID": "OL-4", "Line_Status": "Collected"},
        ]

        with patch.object(order_lifecycle, "_get_order_master_row", return_value=order_row), \
             patch.object(order_lifecycle, "get_all_records", return_value=lines), \
             patch.object(order_lifecycle, "_cancel_order_lines", return_value=2) as cancel_lines, \
             patch.object(order_lifecycle, "_update_sheet_row_by_id") as update_order, \
             patch.object(order_lifecycle, "_write_order_status_log") as write_log:
            result = order_lifecycle.cancel_order("ORD-1", changed_by="Tester", reason="Customer requested")

        self.assertTrue(result["success"])
        self.assertEqual(result["cancelled_line_count"], 2)
        self.assertEqual(result["payment_status"], "Cancelled")
        self.assertEqual(result["approval_status"], "Not_Required")
        cancel_lines.assert_called_once_with(["OL-1", "OL-2"])

        update_args = update_order.call_args.args
        self.assertEqual(update_args[0], order_lifecycle.ORDER_MASTER_SHEET)
        self.assertEqual(update_args[1], "ORD-1")
        self.assertEqual(update_args[2]["Order_Status"], "Cancelled")
        self.assertEqual(update_args[2]["Approval_Status"], "Not_Required")
        self.assertEqual(update_args[2]["Payment_Status"], "Cancelled")
        self.assertEqual(update_args[2]["Reserved_Pig_Count"], 0)

        write_log.assert_called_once()
        log_kwargs = write_log.call_args.kwargs
        self.assertEqual(log_kwargs["old_status"], "Draft | Pending")
        self.assertEqual(log_kwargs["new_status"], "Cancelled | Not_Required")
        self.assertEqual(log_kwargs["change_source"], "Customer")
        self.assertIn("Reason: Customer requested", log_kwargs["notes"])

    def test_cancel_order_blocks_completed_orders(self):
        with patch.object(order_lifecycle, "_get_order_master_row", return_value=draft_order(Order_Status="Completed")):
            with self.assertRaisesRegex(ValueError, "Completed orders cannot be cancelled"):
                order_lifecycle.cancel_order("ORD-1")

    def test_cancel_order_blocks_already_rejected_orders(self):
        row = draft_order(Order_Status="Cancelled", Approval_Status="Rejected")

        with patch.object(order_lifecycle, "_get_order_master_row", return_value=row):
            with self.assertRaisesRegex(ValueError, "Rejected orders are already cancelled"):
                order_lifecycle.cancel_order("ORD-1")

    def test_complete_order_marks_lines_collected_and_pigs_sold(self):
        approved_row = draft_order(Order_Status="Approved", Approval_Status="Approved")
        rows = [
            ["OL-1", "ORD-1", "PIG-1", "Reserved", "Reserved", ""],
            ["OL-2", "ORD-1", "PIG-2", "Draft", "Not_Reserved", ""],
            ["OL-3", "ORD-1", "PIG-3", "Cancelled", "Not_Reserved", ""],
            ["OL-4", "OTHER", "PIG-4", "Reserved", "Reserved", ""],
        ]

        with patch.object(order_lifecycle, "_get_order_master_row", return_value=approved_row), \
             patch.object(order_lifecycle, "_sheet_headers_and_rows", return_value=(ORDER_LINES_HEADERS, rows)), \
             patch.object(order_lifecycle, "batch_update_rows_by_id") as batch_update, \
             patch.object(order_lifecycle, "_update_sheet_row_by_id") as update_order, \
             patch.object(order_lifecycle, "_write_order_status_log") as write_log:
            result = order_lifecycle.complete_order("ORD-1", changed_by="Tester")

        self.assertTrue(result["success"])
        self.assertEqual(result["pigs_marked_sold"], 2)

        self.assertEqual(batch_update.call_count, 2)
        line_call = batch_update.call_args_list[0].args
        pig_call = batch_update.call_args_list[1].args

        self.assertEqual(line_call[0], order_lifecycle.ORDER_LINES_SHEET)
        self.assertEqual(set(line_call[1].keys()), {"OL-1", "OL-2"})
        self.assertEqual(line_call[1]["OL-1"]["Line_Status"], "Collected")
        self.assertEqual(line_call[1]["OL-1"]["Reserved_Status"], "Collected")

        self.assertEqual(pig_call[0], order_lifecycle.PIG_MASTER_SHEET)
        self.assertEqual(set(pig_call[1].keys()), {"PIG-1", "PIG-2"})
        self.assertEqual(pig_call[1]["PIG-1"]["Status"], "Sold")
        self.assertEqual(pig_call[1]["PIG-1"]["On_Farm"], "No")
        self.assertEqual(pig_call[1]["PIG-1"]["Exit_Order_ID"], "ORD-1")

        update_args = update_order.call_args.args
        self.assertEqual(update_args[0], order_lifecycle.ORDER_MASTER_SHEET)
        self.assertEqual(update_args[1], "ORD-1")
        self.assertEqual(update_args[2]["Order_Status"], "Completed")

        write_log.assert_called_once()
        log_kwargs = write_log.call_args.kwargs
        self.assertEqual(log_kwargs["old_status"], "Approved | Approved")
        self.assertEqual(log_kwargs["new_status"], "Completed | Approved")
        self.assertIn("2 pig(s) marked as sold", log_kwargs["notes"])

    def test_complete_order_requires_approved_status(self):
        with patch.object(order_lifecycle, "_get_order_master_row", return_value=draft_order(Order_Status="Draft")):
            with self.assertRaisesRegex(ValueError, "Only Approved orders"):
                order_lifecycle.complete_order("ORD-1")

    def test_complete_order_requires_active_lines(self):
        approved_row = draft_order(Order_Status="Approved", Approval_Status="Approved")
        rows = [
            ["OL-1", "ORD-1", "PIG-1", "Cancelled", "Not_Reserved", ""],
        ]

        with patch.object(order_lifecycle, "_get_order_master_row", return_value=approved_row), \
             patch.object(order_lifecycle, "_sheet_headers_and_rows", return_value=(ORDER_LINES_HEADERS, rows)):
            with self.assertRaisesRegex(ValueError, "Order has no active lines"):
                order_lifecycle.complete_order("ORD-1")

    def test_complete_order_requires_pig_ids_on_active_lines(self):
        approved_row = draft_order(Order_Status="Approved", Approval_Status="Approved")
        rows = [
            ["OL-1", "ORD-1", "", "Reserved", "Reserved", ""],
        ]

        with patch.object(order_lifecycle, "_get_order_master_row", return_value=approved_row), \
             patch.object(order_lifecycle, "_sheet_headers_and_rows", return_value=(ORDER_LINES_HEADERS, rows)):
            with self.assertRaisesRegex(ValueError, "have no Pig_ID"):
                order_lifecycle.complete_order("ORD-1")


if __name__ == "__main__":
    unittest.main()
