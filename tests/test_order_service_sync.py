import unittest
from unittest.mock import patch

from modules.orders import order_line_sync


def draft_order(**overrides):
    row = {
        "Order_ID": "ORD-1",
        "Order_Status": "Draft",
        "Approval_Status": "Pending",
    }
    row.update(overrides)
    return row


def pig(pig_id, tag_number, sex, reserved_status="Not_Reserved", weight=42):
    return {
        "Pig_ID": pig_id,
        "Tag_Number": tag_number,
        "Sex": sex,
        "Current_Weight_Kg": weight,
        "Weight_Band": "40_to_44_Kg",
        "Sale_Category": "Grower Pigs",
        "Available_For_Sale": "Yes",
        "Reserved_Status": reserved_status,
    }


def line(line_id, request_item_key, pig_id="PIG-OLD", status="Draft"):
    return {
        "Order_Line_ID": line_id,
        "Order_ID": "ORD-1",
        "Pig_ID": pig_id,
        "Line_Status": status,
        "Reserved_Status": "Not_Reserved",
        "Request_Item_Key": request_item_key,
    }


def requested_item(request_item_key, quantity=1, sex="Any"):
    return {
        "request_item_key": request_item_key,
        "category": "Grower",
        "weight_range": "40_to_44_Kg",
        "sex": sex,
        "quantity": quantity,
        "notes": "Test note",
    }


class OrderSyncServiceTests(unittest.TestCase):
    def run_sync(self, requested_items, sales_rows, order_lines=None, **extra_data):
        order_lines = order_lines or []
        data = {
            "requested_items": requested_items,
            "changed_by": "Tester",
        }
        data.update(extra_data)

        def records_for(sheet_name):
            if sheet_name == order_line_sync.SALES_AVAILABILITY_SHEET:
                return sales_rows
            if sheet_name == order_line_sync.ORDER_LINES_SHEET:
                return order_lines
            raise AssertionError(f"Unexpected get_all_records call for {sheet_name}")

        patches = [
            patch.object(order_line_sync, "_get_order_master_row", return_value=draft_order()),
            patch.object(order_line_sync, "_build_sales_pricing_lookup", return_value={("Grower Pigs", "40_to_44_Kg"): 1500}),
            patch.object(order_line_sync, "get_all_records", side_effect=records_for),
            patch.object(order_line_sync, "append_row"),
            patch.object(order_line_sync, "_update_sheet_row_by_id"),
        ]

        started = [p.start() for p in patches]
        self.addCleanup(lambda: [p.stop() for p in reversed(patches)])

        result = order_line_sync.sync_order_lines_from_request("ORD-1", data)
        return result, {
            "append_row": started[3],
            "update_row": started[4],
            "order_lines": order_lines,
        }

    def test_sync_exact_match_creates_lines_and_reports_complete_fulfillment(self):
        result, calls = self.run_sync(
            [requested_item("primary_1", quantity=2)],
            [pig("PIG-1", "001", "Male"), pig("PIG-2", "002", "Female")],
        )

        self.assertTrue(result["success"])
        self.assertTrue(result["complete_fulfillment"])
        self.assertEqual(result["fulfillment_status"], "complete")
        self.assertEqual(result["requested_total"], 2)
        self.assertEqual(result["matched_total"], 2)
        self.assertEqual(result["unmatched_total"], 0)
        self.assertEqual(result["results"][0]["match_status"], "exact_match")
        self.assertEqual(calls["append_row"].call_count, 2)

    def test_sync_split_items_do_not_reuse_pigs_between_request_keys(self):
        result, calls = self.run_sync(
            [
                requested_item("primary_1", sex="Male"),
                requested_item("primary_2", sex="Female"),
            ],
            [pig("PIG-M", "010", "Male"), pig("PIG-F", "011", "Female")],
        )

        self.assertTrue(result["complete_fulfillment"])
        self.assertEqual(result["matched_total"], 2)
        by_key = {item["request_item_key"]: item for item in result["results"]}
        self.assertEqual(by_key["primary_1"]["matched_pig_ids"], ["PIG-M"])
        self.assertEqual(by_key["primary_2"]["matched_pig_ids"], ["PIG-F"])
        self.assertEqual(calls["append_row"].call_count, 2)

    def test_sync_allows_later_split_item_when_first_item_has_no_match(self):
        result, calls = self.run_sync(
            [
                requested_item("primary_1", sex="Male"),
                requested_item("primary_2", sex="Female"),
            ],
            [pig("PIG-F", "011", "Female")],
        )

        self.assertTrue(result["success"])
        self.assertFalse(result["complete_fulfillment"])
        self.assertEqual(result["fulfillment_status"], "partial")
        by_key = {item["request_item_key"]: item for item in result["results"]}
        self.assertEqual(by_key["primary_1"]["match_status"], "no_match")
        self.assertEqual(by_key["primary_2"]["matched_pig_ids"], ["PIG-F"])
        self.assertEqual(calls["append_row"].call_count, 1)

    def test_sync_replaces_existing_active_lines_for_same_request_key(self):
        existing_lines = [line("OL-OLD", "primary_1", pig_id="PIG-OLD")]

        result, calls = self.run_sync(
            [requested_item("primary_1")],
            [pig("PIG-NEW", "012", "Male")],
            order_lines=existing_lines,
        )

        self.assertTrue(result["complete_fulfillment"])
        sync_result = result["results"][0]
        self.assertEqual(sync_result["existing_active_line_count"], 1)
        self.assertEqual(sync_result["cancelled_line_count"], 1)
        self.assertEqual(sync_result["created_line_count"], 1)
        calls["update_row"].assert_called_once()
        self.assertEqual(existing_lines[0]["Line_Status"], "Cancelled")

    def test_sync_partial_match_reports_incomplete_items(self):
        result, calls = self.run_sync(
            [requested_item("primary_1", quantity=2)],
            [pig("PIG-1", "001", "Male")],
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["fulfillment_status"], "partial")
        self.assertEqual(result["matched_total"], 1)
        self.assertEqual(result["unmatched_total"], 1)
        self.assertEqual(result["results"][0]["match_status"], "partial_match")
        self.assertEqual(result["incomplete_items"][0]["unmatched_quantity"], 1)
        self.assertEqual(calls["append_row"].call_count, 1)

    def test_sync_no_match_can_auto_cancel_empty_order(self):
        with patch("modules.orders.order_service.cancel_order", return_value={"success": True}) as cancel_order:
            result, calls = self.run_sync(
                [requested_item("primary_1", sex="Male")],
                [pig("PIG-F", "011", "Female")],
                cancel_order_if_no_matches=True,
            )

        self.assertTrue(result["success"])
        self.assertEqual(result["fulfillment_status"], "no_match")
        self.assertTrue(result["cancelled_empty_order"])
        self.assertEqual(result["order_status"], "Cancelled")
        self.assertEqual(calls["append_row"].call_count, 0)
        cancel_order.assert_called_once()


if __name__ == "__main__":
    unittest.main()
