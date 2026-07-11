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

    def test_order_master_lookup_falls_back_when_supabase_read_fails(self):
        with patch.object(order_line_sync.order_supabase_write, "supabase_order_writes_available", return_value=True), \
             patch.object(order_line_sync.order_supabase_write, "get_order_master_row", side_effect=RuntimeError("offline")), \
             patch.object(order_line_sync, "get_all_records", return_value=[draft_order()]):
            result = order_line_sync._get_order_master_row("ORD-1")

        self.assertEqual(result["Order_ID"], "ORD-1")

    def test_sync_preserves_draft_guard_unless_explicit_approved_revision(self):
        data = {
            "requested_items": [requested_item("primary_1")],
            "changed_by": "Tester",
        }

        with patch.object(order_line_sync, "_get_order_master_row", return_value=draft_order(Order_Status="Approved")):
            with self.assertRaises(ValueError) as exc:
                order_line_sync.sync_order_lines_from_request("ORD-1", data)

        self.assertIn("Only draft orders", str(exc.exception))

    def test_sync_allows_approved_order_only_with_revision_flag(self):
        order_lines = [line("OL-OLD", "primary_1", pig_id="PIG-OLD", status="Reserved")]

        def records_for(sheet_name):
            if sheet_name == order_line_sync.SALES_AVAILABILITY_SHEET:
                return [pig("PIG-NEW", "012", "Male")]
            if sheet_name == order_line_sync.ORDER_LINES_SHEET:
                return order_lines
            raise AssertionError(f"Unexpected get_all_records call for {sheet_name}")

        with patch.object(order_line_sync, "_get_order_master_row", return_value=draft_order(Order_Status="Approved")), \
             patch.object(order_line_sync, "_build_sales_pricing_lookup", return_value={("Grower Pigs", "40_to_44_Kg"): 1500}), \
             patch.object(order_line_sync, "get_all_records", side_effect=records_for), \
             patch.object(order_line_sync, "append_row") as append_row, \
             patch.object(order_line_sync, "_update_sheet_row_by_id") as update_row:
            result = order_line_sync.sync_order_lines_from_request(
                "ORD-1",
                {
                    "requested_items": [requested_item("primary_1")],
                    "changed_by": "Tester",
                    "allow_approved_revision": True,
                },
            )

        self.assertTrue(result["success"])
        self.assertEqual(result["order_status"], "Approved")
        self.assertEqual(result["matched_total"], 1)
        update_row.assert_called_once()
        append_row.assert_called_once()

    def test_append_order_line_falls_back_when_supabase_insert_fails(self):
        with patch.object(order_line_sync.order_supabase_write, "supabase_order_writes_available", return_value=True), \
             patch.object(order_line_sync.order_supabase_write, "insert_order_line", side_effect=RuntimeError("offline")), \
             patch.object(order_line_sync, "generate_order_line_id", return_value="OL-1"), \
             patch.object(order_line_sync, "append_row") as append_row:
            result = order_line_sync._append_order_line_from_match(
                "ORD-1",
                "primary_1",
                {
                    "pig_id": "PIG-1",
                    "tag_number": "001",
                    "sex": "Male",
                    "current_weight_kg": 42,
                    "weight_band": "40_to_44_Kg",
                    "sale_category": "Grower Pigs",
                },
                "Fallback note",
                {("Grower Pigs", "40_to_44_Kg"): 1500},
            )

        append_row.assert_called_once()
        self.assertEqual(append_row.call_args.args[0], order_line_sync.ORDER_LINES_SHEET)
        self.assertEqual(result["order_line_id"], "OL-1")

    def test_sync_falls_back_to_sheet_rows_when_supabase_line_listing_fails(self):
        def records_for(sheet_name):
            if sheet_name == order_line_sync.SALES_AVAILABILITY_SHEET:
                return [pig("PIG-1", "001", "Male")]
            if sheet_name == order_line_sync.ORDER_LINES_SHEET:
                return []
            raise AssertionError(f"Unexpected get_all_records call for {sheet_name}")

        with patch.object(order_line_sync.order_supabase_write, "supabase_order_writes_available", return_value=True), \
             patch.object(order_line_sync, "_get_order_master_row", return_value=draft_order()), \
             patch.object(order_line_sync, "_build_sales_pricing_lookup", return_value={("Grower Pigs", "40_to_44_Kg"): 1500}), \
             patch.object(order_line_sync, "_sales_availability_rows_for_sync", side_effect=RuntimeError("availability offline")), \
             patch.object(order_line_sync.order_supabase_write, "list_order_lines", side_effect=RuntimeError("lines offline")), \
             patch.object(order_line_sync, "get_all_records", side_effect=records_for), \
             patch.object(order_line_sync.order_supabase_write, "insert_order_line") as insert_line:
            result = order_line_sync.sync_order_lines_from_request(
                "ORD-1",
                {"requested_items": [requested_item("primary_1")], "changed_by": "Tester"},
            )

        self.assertTrue(result["success"])
        self.assertEqual(result["matched_total"], 1)
        insert_line.assert_called_once()


if __name__ == "__main__":
    unittest.main()
