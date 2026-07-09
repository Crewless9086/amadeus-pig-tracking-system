import unittest
from unittest.mock import patch

from modules.documents import movement_documents_service
from modules.documents.document_service import (
    DOCUMENT_TYPE_HEALTH_DECLARATION,
    DOCUMENT_TYPE_REMOVAL_CERTIFICATE,
)


class MovementDocumentsServiceTests(unittest.TestCase):
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
            ],
        }

    def _settings(self):
        return {
            "business_name": "AMADEUS FARM",
            "business_address_line_1": "Line 1",
            "business_address_line_2": "Line 2",
            "business_address_line_3": "Line 3",
            "business_phone": "000",
            "business_email": "farm@test",
            "document_logo_path": "",
            "quote_drive_folder_id": "FOLDER-1",
        }

    def test_generate_removal_certificate_stores_worker_safe_record(self):
        records = []
        with patch.object(movement_documents_service, "get_order_detail", return_value=self._order_detail()), \
             patch.object(movement_documents_service, "_enrich_lines_with_pen_context", side_effect=lambda lines: lines), \
             patch.object(movement_documents_service, "get_document_settings", return_value=self._settings()), \
             patch.object(movement_documents_service, "get_next_document_version", return_value=1), \
             patch.object(movement_documents_service, "generate_document_id", return_value="DOC-REM-1"), \
             patch.object(movement_documents_service, "upload_file_to_drive", return_value={"id": "DRIVE-1", "webViewLink": "https://drive.test/rem"}), \
             patch.object(movement_documents_service, "append_order_document", side_effect=records.append):
            result = movement_documents_service.generate_removal_certificate_for_order(
                "ORD-2026-TEST",
                form_data={
                    "driver_name": "Dad",
                    "driver_id": "DAD-ID",
                    "vehicle_registration": "ABC123",
                    "client_name": "Leave blank client",
                    "movement_reason": "Sale / transfer",
                },
                created_by="Test",
            )

        self.assertTrue(result["success"])
        self.assertEqual(result["document_type"], DOCUMENT_TYPE_REMOVAL_CERTIFICATE)
        record = records[0]
        self.assertEqual(record["Document_Type"], DOCUMENT_TYPE_REMOVAL_CERTIFICATE)
        self.assertEqual(record["Total"], "")
        self.assertEqual(record["Payment_Method"], "")
        self.assertIn("contains_prices\":false", record["Notes"])
        self.assertIn("client_name", record["Notes"])
        self.assertIn("driver_id", record["Notes"])
        self.assertIn("movement_reason", record["Notes"])

    def test_generate_health_declaration_stores_worker_safe_record(self):
        records = []
        with patch.object(movement_documents_service, "get_order_detail", return_value=self._order_detail()), \
             patch.object(movement_documents_service, "_enrich_lines_with_pen_context", side_effect=lambda lines: lines), \
             patch.object(movement_documents_service, "get_document_settings", return_value=self._settings()), \
             patch.object(movement_documents_service, "get_next_document_version", return_value=1), \
             patch.object(movement_documents_service, "generate_document_id", return_value="DOC-HEALTH-1"), \
             patch.object(movement_documents_service, "upload_file_to_drive", return_value={"id": "DRIVE-2", "webViewLink": "https://drive.test/health"}), \
             patch.object(movement_documents_service, "append_order_document", side_effect=records.append):
            result = movement_documents_service.generate_health_declaration_for_order(
                "ORD-2026-TEST",
                form_data={
                    "health_notes": "No visible illness observed.",
                    "owner_name": "Charl Nieuwendyk",
                    "client_address": "Leave blank for client",
                },
                created_by="Test",
            )

        self.assertTrue(result["success"])
        self.assertEqual(result["document_type"], DOCUMENT_TYPE_HEALTH_DECLARATION)
        record = records[0]
        self.assertEqual(record["Document_Type"], DOCUMENT_TYPE_HEALTH_DECLARATION)
        self.assertEqual(record["Total"], "")
        self.assertEqual(record["Payment_Method"], "")
        self.assertIn("contains_payment_details\":false", record["Notes"])
        self.assertIn("client_address", record["Notes"])
        self.assertIn("owner_name", record["Notes"])


if __name__ == "__main__":
    unittest.main()
