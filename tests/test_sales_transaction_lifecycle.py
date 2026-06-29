import unittest
from unittest.mock import patch

from modules.sales import sales_transaction_lifecycle


class SalesTransactionLifecycleTests(unittest.TestCase):
    def test_confirm_slaughter_pig_exits_updates_linked_active_pigs(self):
        sale_result = {
            "success": True,
            "sales_transaction": {
                "sale_id": "SALE-1",
                "sale_date": "2026-06-01",
                "sale_stream": "Slaughter",
                "sale_status": "Confirmed",
                "payment_status": "Unpaid",
            },
            "items": [
                {
                    "pig_id": "PIG-1",
                    "tag_number": "S10",
                    "carcass_weight_kg": 68,
                },
                {
                    "pig_id": "PIG-2",
                    "tag_number": "S11",
                    "carcass_weight_kg": "",
                },
            ],
        }
        pig_rows = [
            {
                "Pig_ID": "PIG-1",
                "Status": "Active",
                "On_Farm": "Yes",
                "Litter_ID": "LIT-1",
                "General_Notes": "Existing note",
            },
            {
                "Pig_ID": "PIG-2",
                "Status": "Active",
                "On_Farm": "Yes",
                "Litter_ID": "LIT-1",
            },
        ]

        with patch.object(sales_transaction_lifecycle, "get_sales_transaction", return_value=(sale_result, 200)), \
             patch.object(sales_transaction_lifecycle, "get_all_records", return_value=pig_rows), \
             patch.object(sales_transaction_lifecycle, "batch_update_rows_by_id", return_value=2) as update_pigs:
            result, status_code = sales_transaction_lifecycle.confirm_slaughter_pig_exits(
                "SALE-1",
                {
                    "changed_by": "Tester",
                    "notes": "Delivered to abattoir.",
                },
            )

        self.assertEqual(status_code, 200)
        self.assertTrue(result["success"])
        self.assertEqual(result["status"], "pig_exits_confirmed")
        self.assertEqual(result["pigs_updated"], 2)
        self.assertTrue(result["source"]["writes_to_sheets"])
        self.assertFalse(result["source"]["writes_to_supabase"])

        update_map = update_pigs.call_args.args[1]
        self.assertEqual(set(update_map.keys()), {"PIG-1", "PIG-2"})
        self.assertEqual(update_map["PIG-1"]["Status"], "Slaughtered")
        self.assertEqual(update_map["PIG-1"]["On_Farm"], "No")
        self.assertEqual(update_map["PIG-1"]["Exit_Date"], "01 Jun 2026")
        self.assertEqual(update_map["PIG-1"]["Exit_Reason"], "Sold to Abattoir")
        self.assertEqual(update_map["PIG-1"]["Exit_Order_ID"], "SALE-1")
        self.assertEqual(update_map["PIG-1"]["Carcass_Weight_Kg"], 68)
        self.assertIn("Existing note", update_map["PIG-1"]["General_Notes"])
        self.assertIn("Delivered to abattoir.", update_map["PIG-1"]["General_Notes"])

    def test_confirm_slaughter_pig_exits_prefers_supabase_pig_updates(self):
        sale_result = {
            "success": True,
            "sales_transaction": {
                "sale_id": "SALE-1",
                "sale_date": "2026-06-01",
                "sale_stream": "Slaughter",
                "sale_status": "Confirmed",
                "payment_status": "Unpaid",
            },
            "items": [{"pig_id": "PIG-1", "carcass_weight_kg": 68}],
        }
        pig_lookup = {
            "PIG-1": {
                "Pig_ID": "PIG-1",
                "Status": "Active",
                "On_Farm": "Yes",
                "General_Notes": "Existing note",
            }
        }

        with patch.object(sales_transaction_lifecycle, "get_sales_transaction", return_value=(sale_result, 200)), \
             patch.object(sales_transaction_lifecycle, "_get_pig_lookup", return_value=(pig_lookup, "supabase")), \
             patch.object(sales_transaction_lifecycle, "_update_supabase_pig_exit_rows", return_value=1) as update_pigs, \
             patch.object(sales_transaction_lifecycle, "batch_update_rows_by_id") as sheet_update:
            result, status_code = sales_transaction_lifecycle.confirm_slaughter_pig_exits(
                "SALE-1",
                {"changed_by": "Tester"},
            )

        self.assertEqual(status_code, 200)
        self.assertTrue(result["success"])
        self.assertEqual(result["pigs_updated"], 1)
        self.assertFalse(result["source"]["writes_to_sheets"])
        self.assertTrue(result["source"]["writes_to_supabase"])
        update_map = update_pigs.call_args.args[0]
        self.assertEqual(update_map["PIG-1"]["Status"], "Slaughtered")
        self.assertEqual(update_map["PIG-1"]["Exit_Order_ID"], "SALE-1")
        sheet_update.assert_not_called()

    def test_confirm_slaughter_pig_exits_blocks_terminal_pigs_without_writing(self):
        sale_result = {
            "success": True,
            "sales_transaction": {
                "sale_id": "SALE-1",
                "sale_date": "2026-06-01",
                "sale_stream": "Slaughter",
                "sale_status": "Confirmed",
                "payment_status": "Unpaid",
            },
            "items": [{"pig_id": "PIG-1"}],
        }
        pig_rows = [{"Pig_ID": "PIG-1", "Status": "Sold", "On_Farm": "No"}]

        with patch.object(sales_transaction_lifecycle, "get_sales_transaction", return_value=(sale_result, 200)), \
             patch.object(sales_transaction_lifecycle, "get_all_records", return_value=pig_rows), \
             patch.object(sales_transaction_lifecycle, "batch_update_rows_by_id") as update_pigs:
            result, status_code = sales_transaction_lifecycle.confirm_slaughter_pig_exits("SALE-1", {})

        self.assertEqual(status_code, 409)
        self.assertFalse(result["success"])
        self.assertEqual(result["blocked_pigs"][0]["pig_id"], "PIG-1")
        update_pigs.assert_not_called()

    def test_confirm_slaughter_pig_exits_blocks_closed_or_paid_sales(self):
        sale_result = {
            "success": True,
            "sales_transaction": {
                "sale_id": "SALE-1",
                "sale_date": "2026-06-01",
                "sale_stream": "Slaughter",
                "sale_status": "Completed",
                "payment_status": "Paid",
            },
            "items": [{"pig_id": "PIG-1"}],
        }

        with patch.object(sales_transaction_lifecycle, "get_sales_transaction", return_value=(sale_result, 200)), \
             patch.object(sales_transaction_lifecycle, "get_all_records") as get_pigs:
            result, status_code = sales_transaction_lifecycle.confirm_slaughter_pig_exits("SALE-1", {})

        self.assertEqual(status_code, 409)
        self.assertFalse(result["success"])
        self.assertIn("closed", result["errors"][0])
        get_pigs.assert_not_called()

    def test_confirm_slaughter_pig_exits_rejects_non_slaughter_transaction(self):
        sale_result = {
            "success": True,
            "sales_transaction": {
                "sale_id": "SALE-1",
                "sale_date": "2026-06-01",
                "sale_stream": "Livestock",
                "sale_status": "Completed",
            },
            "items": [{"pig_id": "PIG-1"}],
        }

        with patch.object(sales_transaction_lifecycle, "get_sales_transaction", return_value=(sale_result, 200)), \
             patch.object(sales_transaction_lifecycle, "get_all_records") as get_pigs:
            result, status_code = sales_transaction_lifecycle.confirm_slaughter_pig_exits("SALE-1", {})

        self.assertEqual(status_code, 400)
        self.assertFalse(result["success"])
        get_pigs.assert_not_called()

    def test_reconcile_closed_slaughter_pig_exits_previews_missing_lifecycle_fields(self):
        sale_result = {
            "success": True,
            "sales_transaction": {
                "sale_id": "SALE-1",
                "sale_date": "2026-06-01",
                "sale_stream": "Slaughter",
                "sale_status": "Completed",
                "payment_status": "Paid",
            },
            "items": [{"pig_id": "PIG-1", "carcass_weight_kg": 68}],
        }
        pig_rows = [
            {
                "Pig_ID": "PIG-1",
                "Status": "Slaughtered",
                "On_Farm": "No",
                "Exit_Date": "",
                "Exit_Reason": "Slaughtered",
                "Exit_Order_ID": "",
                "General_Notes": "Existing note",
            },
        ]

        with patch.object(sales_transaction_lifecycle, "get_sales_transaction", return_value=(sale_result, 200)), \
             patch.object(sales_transaction_lifecycle, "get_all_records", return_value=pig_rows), \
             patch.object(sales_transaction_lifecycle, "batch_update_rows_by_id") as update_pigs:
            result, status_code = sales_transaction_lifecycle.reconcile_closed_slaughter_pig_exits(
                "SALE-1",
                {"dry_run": True, "changed_by": "Tester"},
            )

        self.assertEqual(status_code, 200)
        self.assertTrue(result["success"])
        self.assertEqual(result["status"], "pig_exits_reconcile_preview")
        self.assertEqual(result["pigs_needing_updates"], 1)
        self.assertFalse(result["source"]["writes_to_sheets"])
        updates = result["updates"]["PIG-1"]
        self.assertEqual(updates["Exit_Date"], "01 Jun 2026")
        self.assertEqual(updates["Exit_Reason"], "Sold to Abattoir")
        self.assertEqual(updates["Exit_Order_ID"], "SALE-1")
        self.assertEqual(updates["Carcass_Weight_Kg"], 68)
        update_pigs.assert_not_called()

    def test_reconcile_closed_slaughter_pig_exits_applies_clean_preview(self):
        sale_result = {
            "success": True,
            "sales_transaction": {
                "sale_id": "SALE-1",
                "sale_date": "2026-06-01",
                "sale_stream": "Slaughter",
                "sale_status": "Completed",
                "payment_status": "Paid",
            },
            "items": [{"pig_id": "PIG-1"}],
        }
        pig_rows = [{"Pig_ID": "PIG-1", "Status": "Slaughtered", "On_Farm": "No"}]

        with patch.object(sales_transaction_lifecycle, "get_sales_transaction", return_value=(sale_result, 200)), \
             patch.object(sales_transaction_lifecycle, "get_all_records", return_value=pig_rows), \
             patch.object(sales_transaction_lifecycle, "batch_update_rows_by_id", return_value=1) as update_pigs:
            result, status_code = sales_transaction_lifecycle.reconcile_closed_slaughter_pig_exits(
                "SALE-1",
                {"dry_run": False},
            )

        self.assertEqual(status_code, 200)
        self.assertTrue(result["success"])
        self.assertEqual(result["status"], "pig_exits_reconciled")
        self.assertEqual(result["pigs_updated"], 1)
        self.assertTrue(result["source"]["writes_to_sheets"])
        update_pigs.assert_called_once()

    def test_reconcile_closed_slaughter_pig_exits_prefers_supabase_when_not_dry_run(self):
        sale_result = {
            "success": True,
            "sales_transaction": {
                "sale_id": "SALE-1",
                "sale_date": "2026-06-01",
                "sale_stream": "Slaughter",
                "sale_status": "Completed",
                "payment_status": "Paid",
            },
            "items": [{"pig_id": "PIG-1", "carcass_weight_kg": 68}],
        }
        pig_lookup = {
            "PIG-1": {
                "Pig_ID": "PIG-1",
                "Status": "Slaughtered",
                "On_Farm": "No",
                "Exit_Date": "",
                "Exit_Reason": "",
                "Exit_Order_ID": "",
                "General_Notes": "",
            }
        }

        with patch.object(sales_transaction_lifecycle, "get_sales_transaction", return_value=(sale_result, 200)), \
             patch.object(sales_transaction_lifecycle, "_get_pig_lookup", return_value=(pig_lookup, "supabase")), \
             patch.object(sales_transaction_lifecycle, "_update_supabase_pig_exit_rows", return_value=1) as update_pigs, \
             patch.object(sales_transaction_lifecycle, "batch_update_rows_by_id") as sheet_update:
            result, status_code = sales_transaction_lifecycle.reconcile_closed_slaughter_pig_exits(
                "SALE-1",
                {"dry_run": False},
            )

        self.assertEqual(status_code, 200)
        self.assertTrue(result["success"])
        self.assertEqual(result["pigs_updated"], 1)
        self.assertFalse(result["source"]["writes_to_sheets"])
        self.assertTrue(result["source"]["writes_to_supabase"])
        self.assertEqual(update_pigs.call_args.args[0]["PIG-1"]["Exit_Order_ID"], "SALE-1")
        sheet_update.assert_not_called()

    def test_reconcile_closed_slaughter_pig_exits_blocks_active_pigs(self):
        sale_result = {
            "success": True,
            "sales_transaction": {
                "sale_id": "SALE-1",
                "sale_date": "2026-06-01",
                "sale_stream": "Slaughter",
                "sale_status": "Completed",
                "payment_status": "Paid",
            },
            "items": [{"pig_id": "PIG-1"}],
        }
        pig_rows = [{"Pig_ID": "PIG-1", "Status": "Active", "On_Farm": "Yes"}]

        with patch.object(sales_transaction_lifecycle, "get_sales_transaction", return_value=(sale_result, 200)), \
             patch.object(sales_transaction_lifecycle, "get_all_records", return_value=pig_rows), \
             patch.object(sales_transaction_lifecycle, "batch_update_rows_by_id") as update_pigs:
            result, status_code = sales_transaction_lifecycle.reconcile_closed_slaughter_pig_exits("SALE-1", {})

        self.assertEqual(status_code, 409)
        self.assertFalse(result["success"])
        self.assertEqual(result["blocked_pigs"][0]["pig_id"], "PIG-1")
        update_pigs.assert_not_called()


if __name__ == "__main__":
    unittest.main()
