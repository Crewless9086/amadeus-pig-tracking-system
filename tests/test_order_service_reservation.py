import unittest
from unittest.mock import patch

from modules.orders import order_reservation


ORDER_LINES_HEADERS = [
    "Order_Line_ID",
    "Order_ID",
    "Pig_ID",
    "Line_Status",
    "Reserved_Status",
    "Updated_At",
]


class OrderReservationServiceTests(unittest.TestCase):
    def test_reserve_order_lines_reserves_eligible_and_reports_skips(self):
        rows = [
            ["OL-1", "ORD-1", "PIG-1", "Draft", "Not_Reserved", ""],
            ["OL-2", "ORD-1", "", "Draft", "Not_Reserved", ""],
            ["OL-3", "ORD-1", "PIG-3", "Cancelled", "Not_Reserved", ""],
            ["OL-4", "OTHER", "PIG-4", "Draft", "Not_Reserved", ""],
        ]

        with patch.object(order_reservation, "_get_order_master_row", return_value={"Order_ID": "ORD-1"}), \
             patch.object(order_reservation, "_sheet_headers_and_rows", return_value=(ORDER_LINES_HEADERS, rows)), \
             patch.object(order_reservation, "_count_reserved_lines", return_value=1), \
             patch.object(order_reservation, "batch_update_rows_by_id") as batch_update, \
             patch.object(order_reservation, "_update_sheet_row_by_id") as update_master:
            result = order_reservation.reserve_order_lines("ORD-1")

        self.assertTrue(result["success"])
        self.assertEqual(result["changed_count"], 1)
        self.assertEqual(result["reserved_pig_count"], 1)
        self.assertIn("warning", result)
        self.assertEqual(
            {item["order_line_id"]: item["action"] for item in result["line_results"]},
            {
                "OL-1": "reserved",
                "OL-2": "skipped",
                "OL-3": "skipped",
            },
        )
        batch_update.assert_called_once()
        sheet_name, updates = batch_update.call_args.args
        self.assertEqual(sheet_name, order_reservation.ORDER_LINES_SHEET)
        self.assertEqual(set(updates.keys()), {"OL-1"})
        self.assertEqual(updates["OL-1"]["Reserved_Status"], "Reserved")
        self.assertEqual(updates["OL-1"]["Line_Status"], "Reserved")
        update_master.assert_called_once()

    def test_reserve_order_lines_is_idempotent_when_already_reserved(self):
        rows = [
            ["OL-1", "ORD-1", "PIG-1", "Reserved", "Reserved", ""],
        ]

        with patch.object(order_reservation, "_get_order_master_row", return_value={"Order_ID": "ORD-1"}), \
             patch.object(order_reservation, "_sheet_headers_and_rows", return_value=(ORDER_LINES_HEADERS, rows)), \
             patch.object(order_reservation, "_count_reserved_lines", return_value=1), \
             patch.object(order_reservation, "batch_update_rows_by_id") as batch_update, \
             patch.object(order_reservation, "_update_sheet_row_by_id"):
            result = order_reservation.reserve_order_lines("ORD-1")

        self.assertTrue(result["success"])
        self.assertEqual(result["changed_count"], 0)
        self.assertEqual(result["message"], "All eligible lines are already reserved.")
        batch_update.assert_not_called()

    def test_reserve_order_lines_returns_failure_when_no_eligible_lines(self):
        rows = [
            ["OL-1", "ORD-1", "", "Draft", "Not_Reserved", ""],
            ["OL-2", "ORD-1", "PIG-2", "Cancelled", "Not_Reserved", ""],
        ]

        with patch.object(order_reservation, "_get_order_master_row", return_value={"Order_ID": "ORD-1"}), \
             patch.object(order_reservation, "_sheet_headers_and_rows", return_value=(ORDER_LINES_HEADERS, rows)), \
             patch.object(order_reservation, "_count_reserved_lines", return_value=0), \
             patch.object(order_reservation, "batch_update_rows_by_id") as batch_update, \
             patch.object(order_reservation, "_update_sheet_row_by_id"):
            result = order_reservation.reserve_order_lines("ORD-1")

        self.assertFalse(result["success"])
        self.assertEqual(result["changed_count"], 0)
        self.assertIn("errors", result)
        batch_update.assert_not_called()

    def test_release_order_lines_releases_reserved_and_keeps_terminal_collected(self):
        rows = [
            ["OL-1", "ORD-1", "PIG-1", "Reserved", "Reserved", ""],
            ["OL-2", "ORD-1", "PIG-2", "Cancelled", "Reserved", ""],
            ["OL-3", "ORD-1", "PIG-3", "Collected", "Collected", ""],
            ["OL-4", "ORD-1", "PIG-4", "Draft", "Not_Reserved", ""],
        ]

        with patch.object(order_reservation, "_get_order_master_row", return_value={"Order_ID": "ORD-1"}), \
             patch.object(order_reservation, "_sheet_headers_and_rows", return_value=(ORDER_LINES_HEADERS, rows)), \
             patch.object(order_reservation, "_count_reserved_lines", return_value=0), \
             patch.object(order_reservation, "batch_update_rows_by_id") as batch_update, \
             patch.object(order_reservation, "_update_sheet_row_by_id") as update_master:
            result = order_reservation.release_order_lines("ORD-1")

        self.assertTrue(result["success"])
        self.assertEqual(result["changed_count"], 2)
        self.assertEqual(
            {item["order_line_id"]: item["action"] for item in result["line_results"]},
            {
                "OL-1": "released",
                "OL-2": "released",
                "OL-3": "skipped",
                "OL-4": "noop",
            },
        )
        sheet_name, updates = batch_update.call_args.args
        self.assertEqual(sheet_name, order_reservation.ORDER_LINES_SHEET)
        self.assertEqual(updates["OL-1"]["Line_Status"], "Draft")
        self.assertEqual(updates["OL-1"]["Reserved_Status"], "Not_Reserved")
        self.assertNotIn("Line_Status", updates["OL-2"])
        self.assertEqual(updates["OL-2"]["Reserved_Status"], "Not_Reserved")
        update_master.assert_called_once()

    def test_release_order_lines_is_idempotent_when_nothing_reserved(self):
        rows = [
            ["OL-1", "ORD-1", "PIG-1", "Draft", "Not_Reserved", ""],
        ]

        with patch.object(order_reservation, "_get_order_master_row", return_value={"Order_ID": "ORD-1"}), \
             patch.object(order_reservation, "_sheet_headers_and_rows", return_value=(ORDER_LINES_HEADERS, rows)), \
             patch.object(order_reservation, "_count_reserved_lines", return_value=0), \
             patch.object(order_reservation, "batch_update_rows_by_id") as batch_update, \
             patch.object(order_reservation, "_update_sheet_row_by_id"):
            result = order_reservation.release_order_lines("ORD-1")

        self.assertTrue(result["success"])
        self.assertEqual(result["changed_count"], 0)
        self.assertEqual(result["message"], "No active reservations to release.")
        batch_update.assert_not_called()

    def test_reserve_order_lines_raises_for_missing_order(self):
        with patch.object(order_reservation, "_get_order_master_row", return_value=None):
            with self.assertRaisesRegex(ValueError, "Order not found"):
                order_reservation.reserve_order_lines("ORD-MISSING")


if __name__ == "__main__":
    unittest.main()
