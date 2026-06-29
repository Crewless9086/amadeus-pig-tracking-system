import unittest
from datetime import date, datetime
from unittest.mock import patch

from modules.documents import document_service, document_supabase_read, document_supabase_write


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

    def test_document_service_prefers_supabase_settings(self):
        expected = {"business_name": "Amadeus", "vat_rate": "0"}
        with patch.object(document_supabase_read, "supabase_document_reads_available", return_value=True), \
             patch.object(document_supabase_write, "get_document_settings", return_value=expected), \
             patch.object(document_service, "get_all_records") as get_records:
            self.assertEqual(document_service.get_document_settings(), expected)
        get_records.assert_not_called()

    def test_document_service_falls_back_to_sheet_settings(self):
        rows = [{"Setting_Key": "business_name", "Setting_Value": "Amadeus"}]
        with patch.object(document_supabase_read, "supabase_document_reads_available", return_value=True), \
             patch.object(document_supabase_write, "get_document_settings", side_effect=RuntimeError("offline")), \
             patch.object(document_service, "get_all_records", return_value=rows):
            self.assertEqual(document_service.get_document_settings(), {"business_name": "Amadeus"})

    def test_append_order_document_prefers_supabase_write(self):
        record = {"Document_ID": "DOC-1", "Order_ID": "ORD-1", "Document_Type": "Quote", "Document_Ref": "Q-1"}
        with patch.object(document_supabase_write, "supabase_document_writes_available", return_value=True), \
             patch.object(document_supabase_write, "insert_order_document") as insert_document, \
             patch.object(document_service, "append_row") as append_row:
            document_service.append_order_document(record)
        insert_document.assert_called_once_with(record)
        append_row.assert_not_called()

    def test_mark_document_sent_prefers_supabase_write(self):
        with patch.object(document_supabase_write, "supabase_document_writes_available", return_value=True), \
             patch.object(document_supabase_write, "mark_document_sent") as mark_sent, \
             patch.object(document_service, "get_all_records") as get_records:
            document_service.mark_document_sent("DOC-1", sent_by="Tester", sent_at="01 Jun 2026 10:00")
        mark_sent.assert_called_once_with("DOC-1", sent_by="Tester", sent_at="01 Jun 2026 10:00")
        get_records.assert_not_called()

    def test_document_params_maps_sheet_record_to_supabase_columns(self):
        params = document_supabase_write._document_params({
            "Document_ID": "DOC-1",
            "Order_ID": "ORD-1",
            "Document_Type": "Quote",
            "Document_Ref": "Q-1",
            "Version": "2",
            "Total": "1500.50",
            "Valid_Until": "30 Jun 2026",
            "Created_At": "01 Jun 2026 10:30",
        })

        self.assertEqual(params["document_id"], "DOC-1")
        self.assertEqual(params["version"], 2)
        self.assertEqual(params["total"], 1500.50)
        self.assertEqual(params["valid_until"], date(2026, 6, 30))
        self.assertEqual(params["created_at"], datetime(2026, 6, 1, 10, 30))


if __name__ == "__main__":
    unittest.main()
