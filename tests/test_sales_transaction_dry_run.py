import unittest

from modules.sales.sales_transaction_dry_run import dry_run_sales_transaction


class SalesTransactionDryRunTests(unittest.TestCase):
    def test_dry_run_validates_slaughter_transaction_without_writing(self):
        payload = {
            "sale_date": "2026-05-21",
            "sale_stream": "Slaughter",
            "buyer_name": "Abattoir",
            "buyer_phone": "082 000 0000",
            "destination": "Local Abattoir",
            "payment_status": "Paid",
            "sale_status": "Completed",
            "deductions_total": 100,
            "items": [
                {
                    "item_type": "Pig",
                    "pig_id": "PIG-1",
                    "tag_number": "001",
                    "quantity": 1,
                    "unit_price": 1200,
                    "pricing_basis": "Per_Pig",
                },
                {
                    "item_type": "Pig",
                    "pig_id": "PIG-2",
                    "tag_number": "002",
                    "quantity": 1,
                    "line_total": 1300,
                    "pricing_basis": "Per_Pig",
                },
            ],
        }

        result, status_code = dry_run_sales_transaction(payload)

        self.assertEqual(status_code, 200)
        self.assertTrue(result["success"])
        self.assertEqual(result["mode"], "dry_run")
        self.assertEqual(result["summary"]["sale_stream"], "Slaughter")
        self.assertEqual(result["summary"]["pig_count"], 2)
        self.assertEqual(result["summary"]["gross_total"], 2500.0)
        self.assertEqual(result["summary"]["deductions_total"], 100.0)
        self.assertEqual(result["summary"]["net_total"], 2400.0)
        self.assertEqual(result["sales_transaction"]["buyer_phone_normalized"], "0820000000")
        self.assertFalse(result["source"]["writes_to_sheets"])
        self.assertFalse(result["source"]["writes_to_supabase"])

    def test_dry_run_rejects_invalid_payload(self):
        result, status_code = dry_run_sales_transaction({
            "sale_stream": "Auction",
            "items": [{"item_type": "Pig"}],
        })

        self.assertEqual(status_code, 400)
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "validation_failed")
        self.assertIn("sale_date is required", result["errors"][0])
        self.assertTrue(any("sale_stream must be Livestock" in error for error in result["errors"]))
        self.assertTrue(any("pig_id is required" in error for error in result["errors"]))
        self.assertFalse(result["source"]["writes_to_sheets"])
        self.assertFalse(result["source"]["writes_to_supabase"])

    def test_dry_run_rejects_duplicate_pig_inside_same_payload(self):
        result, status_code = dry_run_sales_transaction({
            "sale_date": "2026-05-21",
            "sale_stream": "Slaughter",
            "payment_status": "Unpaid",
            "sale_status": "Confirmed",
            "items": [
                {
                    "item_type": "Pig",
                    "pig_id": "PIG-1",
                    "quantity": 1,
                    "line_total": 1200,
                    "pricing_basis": "Per_Pig",
                },
                {
                    "item_type": "Pig",
                    "pig_id": "PIG-1",
                    "quantity": 1,
                    "line_total": 1300,
                    "pricing_basis": "Per_Pig",
                },
            ],
        })

        self.assertEqual(status_code, 400)
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "validation_failed")
        self.assertIn("items contain duplicate pig_id values: PIG-1.", result["errors"])
        self.assertFalse(result["source"]["writes_to_sheets"])
        self.assertFalse(result["source"]["writes_to_supabase"])


if __name__ == "__main__":
    unittest.main()
