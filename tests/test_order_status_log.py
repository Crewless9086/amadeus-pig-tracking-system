import unittest
from unittest.mock import patch

from modules.orders import order_status_log


class OrderStatusLogTests(unittest.TestCase):
    def test_write_order_status_log_appends_expected_row(self):
        with patch.object(order_status_log, "generate_order_status_log_id", return_value="OSL-1"), \
             patch.object(order_status_log, "append_row") as append_row:
            order_status_log.write_order_status_log(
                order_id="ORD-1",
                old_status="Draft",
                new_status="Pending_Approval",
                changed_by="Tester",
                change_source="App",
                notes="Sent for approval",
            )

        append_row.assert_called_once()
        sheet_name, row_values = append_row.call_args.args
        self.assertEqual(sheet_name, order_status_log.ORDER_STATUS_LOG_SHEET)
        self.assertEqual(row_values[0], "OSL-1")
        self.assertEqual(row_values[1], "ORD-1")
        self.assertEqual(row_values[3], "Draft")
        self.assertEqual(row_values[4], "Pending_Approval")
        self.assertEqual(row_values[5], "Tester")
        self.assertEqual(row_values[6], "App")
        self.assertEqual(row_values[7], "Sent for approval")


if __name__ == "__main__":
    unittest.main()
