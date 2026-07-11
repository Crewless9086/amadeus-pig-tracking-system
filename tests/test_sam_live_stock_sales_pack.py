import unittest

from modules.sales.sam_live_stock_sales_pack import prepare_live_stock_sales_pack


class SamLiveStockSalesPackTests(unittest.TestCase):
    def test_prepares_complete_pack_without_send_or_stock_authority(self):
        calls = []

        def prepared(name):
            def callback(*_args, **_kwargs):
                calls.append(name)
                if name == "quote":
                    return {"success": True, "quote_ready": True, "generated": True}
                return {"success": True, "document_id": f"DOC-{name}"}
            return callback

        result = prepare_live_stock_sales_pack(
            "ORD-1",
            {},
            order_loader=lambda _order_id: {"order": {"Order_ID": "ORD-1"}, "lines": [{"Pig_ID": "PIG-1"}]},
            document_loader=lambda _order_id: [],
            quote_preparer=prepared("quote"),
            loading_sheet_preparer=prepared("loading"),
            removal_preparer=prepared("removal"),
            health_preparer=prepared("health"),
        )
        self.assertTrue(result["success"])
        self.assertEqual(calls, ["quote", "loading", "removal", "health"])
        self.assertFalse(result["customer_send_allowed"])
        self.assertFalse(result["reserves_stock"])
        self.assertFalse(result["changes_stock"])

    def test_reuses_existing_documents_by_default(self):
        generated = []
        documents = [
            {"Document_ID": "LOAD-1", "Document_Type": "Loading Sheet", "Status": "Generated"},
            {"Document_ID": "REM-1", "Document_Type": "Removal Certificate", "Status": "Generated"},
            {"Document_ID": "HEALTH-1", "Document_Type": "Health Declaration", "Status": "Generated"},
        ]
        result = prepare_live_stock_sales_pack(
            "ORD-1",
            {},
            order_loader=lambda _order_id: {"order": {}, "lines": [{}]},
            document_loader=lambda _order_id: documents,
            quote_preparer=lambda *_args, **_kwargs: {"success": True, "quote_ready": True},
            loading_sheet_preparer=lambda *_args, **_kwargs: generated.append("loading"),
            removal_preparer=lambda *_args, **_kwargs: generated.append("removal"),
            health_preparer=lambda *_args, **_kwargs: generated.append("health"),
        )
        self.assertTrue(result["success"])
        self.assertEqual(generated, [])
        self.assertTrue(result["results"]["loading_sheet"]["reused"])

    def test_reports_document_failure_without_sending(self):
        def fail(*_args, **_kwargs):
            raise ValueError("driver details required")

        result = prepare_live_stock_sales_pack(
            "ORD-1",
            {},
            order_loader=lambda _order_id: {"order": {}, "lines": [{}]},
            document_loader=lambda _order_id: [],
            quote_preparer=lambda *_args, **_kwargs: {"success": True, "quote_ready": True},
            loading_sheet_preparer=lambda *_args, **_kwargs: {"success": True},
            removal_preparer=fail,
            health_preparer=lambda *_args, **_kwargs: {"success": True},
        )
        self.assertFalse(result["success"])
        self.assertEqual(result["errors"][0]["step"], "removal_certificate")
        self.assertFalse(result["sends_customer_message"])


if __name__ == "__main__":
    unittest.main()
