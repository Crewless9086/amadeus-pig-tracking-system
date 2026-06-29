import unittest
from datetime import date, datetime
from unittest.mock import patch

from modules.documents import document_service, document_supabase_read


class DocumentSupabaseReadTests(unittest.TestCase):
    def test_get_order_documents_maps_sheet_compatible_keys(self):
        rows = [{
            "document_id": "DOC-1",
            "order_id": "ORD-1",
            "document_type": "Quote",
            "document_ref": "Q-2026-1",
            "payment_ref": "1",
            "version": 2,
            "document_status": "Generated",
            "payment_method": "Cash",
            "vat_rate": 0,
            "subtotal_ex_vat": 1500,
            "vat_amount": 0,
            "total": 1500,
            "valid_until": date(2026, 6, 30),
            "google_drive_file_id": "drive-1",
            "google_drive_url": "https://drive.example/doc",
            "file_name": "quote.pdf",
            "created_at": datetime(2026, 6, 1, 10, 30),
            "created_by": "Tester",
            "sent_at": None,
            "sent_by": "",
            "notes": "Quote_Fingerprint: abc",
        }]

        with patch.object(document_supabase_read, "_fetch_all", return_value=rows):
            result = document_supabase_read.get_order_documents("ORD-1")

        self.assertEqual(result[0]["Document_ID"], "DOC-1")
        self.assertEqual(result[0]["Order_ID"], "ORD-1")
        self.assertEqual(result[0]["Version"], "2")
        self.assertEqual(result[0]["Valid_Until"], "30 Jun 2026")
        self.assertEqual(result[0]["Created_At"], "01 Jun 2026 10:30")

    def test_document_service_prefers_supabase_documents_when_available(self):
        expected = [{"Document_ID": "DOC-1"}]
        with patch.object(document_supabase_read, "supabase_document_reads_available", return_value=True), \
             patch.object(document_supabase_read, "get_order_documents", return_value=expected):
            self.assertEqual(document_service.get_order_documents("ORD-1"), expected)

    def test_document_service_falls_back_when_supabase_unavailable(self):
        rows = [{"Document_ID": "DOC-1", "Order_ID": "ORD-1"}]
        with patch.object(document_supabase_read, "supabase_document_reads_available", return_value=False), \
             patch.object(document_service, "get_all_records", return_value=rows):
            self.assertEqual(document_service.get_order_documents("ORD-1"), rows)


if __name__ == "__main__":
    unittest.main()
