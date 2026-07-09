import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from modules.documents import loading_sheet_service
from modules.documents.document_service import (
    DOCUMENT_TYPE_LOADING_SHEET,
    build_document_file_name,
)


class LoadingSheetServiceTests(unittest.TestCase):
    def _order_detail(self):
        return {
            "order": {
                "order_id": "ORD-2026-TEST",
                "customer_name": "Michaels",
                "requested_quantity": 2,
                "requested_category": "Piglet",
                "requested_weight_range": "7_to_9_Kg",
                "requested_sex": "Any",
                "collection_date": "2026-07-10",
                "collection_location": "Albertinia",
            },
            "lines": [
                {
                    "order_line_id": "LINE-1",
                    "pig_id": "PIG-1",
                    "tag_number": "101",
                    "sale_category": "Piglet",
                    "weight_band": "7_to_9_Kg",
                    "sex": "Female",
                    "current_weight_kg": 8.2,
                    "unit_price": 450,
                    "line_status": "Draft",
                },
                {
                    "order_line_id": "LINE-2",
                    "pig_id": "PIG-2",
                    "tag_number": "102",
                    "sale_category": "Piglet",
                    "weight_band": "7_to_9_Kg",
                    "sex": "Male",
                    "current_weight_kg": 7.9,
                    "unit_price": 450,
                    "line_status": "Draft",
                },
            ],
        }

    def test_loading_sheet_filename_excludes_money_and_payment(self):
        file_name = build_document_file_name(
            DOCUMENT_TYPE_LOADING_SHEET,
            loading_sheet_service.datetime(2026, 7, 9, 12, 0),
            "12BCCC",
            1,
            total=1350,
            payment_method="EFT",
        )

        self.assertEqual(file_name, "LOAD_2026_07_09_12BCCC_V1.pdf")
        self.assertNotIn("1350", file_name)
        self.assertNotIn("EFT", file_name)

    def test_generate_loading_sheet_stores_worker_safe_document_record(self):
        records = []

        with patch.object(loading_sheet_service, "get_order_detail", return_value=self._order_detail()), \
             patch.object(loading_sheet_service, "_pig_pen_lookup", return_value={
                 "PIG-1": {"current_pen_id": "PEN-A", "current_pen_name": "Pen A"},
                 "PIG-2": {"current_pen_id": "PEN-B", "current_pen_name": "Pen B"},
             }), \
             patch.object(loading_sheet_service, "get_document_settings", return_value={
                 "business_name": "AMADEUS FARM",
                 "business_address_line_1": "Line 1",
                 "business_address_line_2": "Line 2",
                 "business_address_line_3": "Line 3",
                 "business_phone": "000",
                 "document_logo_path": "",
                 "quote_drive_folder_id": "FOLDER-1",
             }), \
             patch.object(loading_sheet_service, "get_next_document_version", return_value=1), \
             patch.object(loading_sheet_service, "generate_document_id", return_value="DOC-LOAD-1"), \
             patch.object(loading_sheet_service, "upload_file_to_drive", return_value={"id": "DRIVE-1", "webViewLink": "https://drive.test/load"}), \
             patch.object(loading_sheet_service, "append_order_document", side_effect=records.append):
            result = loading_sheet_service.generate_loading_sheet_for_order("ORD-2026-TEST", created_by="Test")

        self.assertTrue(result["success"])
        self.assertEqual(result["document_type"], DOCUMENT_TYPE_LOADING_SHEET)
        self.assertEqual(result["pig_count"], 2)
        self.assertEqual(result["pen_count"], 2)
        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record["Document_Type"], DOCUMENT_TYPE_LOADING_SHEET)
        self.assertEqual(record["Total"], "")
        self.assertEqual(record["Payment_Method"], "")
        self.assertEqual(record["VAT_Amount"], "")
        self.assertIn("contains_prices\":false", record["Notes"])

    def test_send_loading_sheet_to_owner_telegram_sends_pdf_document(self):
        calls = []

        def fake_download(_drive_id, destination_path):
            Path(destination_path).write_bytes(b"%PDF-LOADING-SHEET%")

        class FakeResponse:
            status = 200
            def __enter__(self):
                return self
            def __exit__(self, *_args):
                return False
            def read(self):
                return b'{"ok": true, "result": {"message_id": 44}}'

        def fake_urlopen(request, timeout=0):
            calls.append(request)
            return FakeResponse()

        with patch.object(loading_sheet_service, "get_order_document", return_value={
                "Document_ID": "DOC-LOAD-1",
                "Order_ID": "ORD-2026-TEST",
                "Document_Type": DOCUMENT_TYPE_LOADING_SHEET,
                "Document_Ref": "LOAD-2026-TEST",
                "Google_Drive_File_ID": "DRIVE-1",
                "File_Name": "LOAD_20260709_TEST_V1.pdf",
             }), \
             patch.object(loading_sheet_service, "download_drive_file", side_effect=fake_download), \
             patch.object(loading_sheet_service.urllib_request, "urlopen", side_effect=fake_urlopen), \
             patch.dict(loading_sheet_service.os.environ, {
                "OOM_SAKKIE_TELEGRAM_BOT_TOKEN": "token",
                "OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS": "12345,67890",
             }, clear=False):
            result = loading_sheet_service.send_loading_sheet_to_owner_telegram("DOC-LOAD-1")

        self.assertTrue(result["success"])
        self.assertEqual(len(result["deliveries"]), 1)
        self.assertEqual(result["deliveries"][0]["telegram_message_id"], 44)
        body = calls[0].data
        self.assertIn(b'name="document"; filename="LOAD_20260709_TEST_V1.pdf"', body)
        self.assertIn(b"%PDF-LOADING-SHEET%", body)
        self.assertIn(b"Loading Sheet PDF", body)

    def test_send_loading_sheet_rejects_non_loading_sheet_document(self):
        with patch.object(loading_sheet_service, "get_order_document", return_value={
            "Document_ID": "DOC-Q",
            "Document_Type": "Quote",
        }):
            with self.assertRaises(ValueError):
                loading_sheet_service.send_loading_sheet_to_owner_telegram("DOC-Q")


if __name__ == "__main__":
    unittest.main()
