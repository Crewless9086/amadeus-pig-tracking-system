import unittest
from pathlib import Path
from unittest.mock import patch

from modules.documents import document_service


class DocumentServiceSendTests(unittest.TestCase):
    def test_document_delivery_falls_back_to_direct_chatwoot_pdf_attachment_when_webhook_missing(self):
        calls = []

        class Response:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return b'{"id":123}'

        def opener(request, timeout=0):
            calls.append((request, timeout))
            return Response()

        def fake_download(_file_id, destination_path):
            Path(destination_path).write_bytes(b"%PDF-QUOTE%")
            return Path(destination_path)

        document = {
            "Document_ID": "DOC-1",
            "Document_Type": "Quote",
            "Document_Ref": "Q-1",
            "Google_Drive_File_ID": "drive-file-1",
            "Google_Drive_URL": "https://drive.google.com/file/d/test/view",
            "File_Name": "Quote 1.pdf",
            "Total": "1350.00",
            "Payment_Ref": "12BCCC",
            "Payment_Method": "Cash",
        }

        with patch.object(document_service, "DOCUMENT_DELIVERY_WEBHOOK_URL", ""), \
             patch.object(document_service, "CHATWOOT_API_TOKEN", "token"), \
             patch.object(document_service, "CHATWOOT_BASE_URL", "https://chatwoot.test"), \
             patch.object(document_service, "download_drive_file", side_effect=fake_download) as download, \
             patch.object(document_service.urllib_request, "urlopen", side_effect=opener):
            result = document_service._notify_document_delivery_workflow(
                document,
                conversation_id="1478",
                sent_by="Tester",
                account_id="147387",
            )

        self.assertTrue(result["sent"])
        self.assertTrue(result["attachment_sent"])
        self.assertEqual(result["delivery_channel"], "chatwoot_direct_attachment")
        self.assertIn("Q-1", result["message_text"])
        self.assertNotIn("https://drive.google.com/file/d/test/view", result["message_text"])
        download.assert_called_once()
        request = calls[0][0]
        self.assertEqual(request.full_url, "https://chatwoot.test/api/v1/accounts/147387/conversations/1478/messages")
        headers = {key.lower(): value for key, value in request.header_items()}
        self.assertIn("api_access_token", headers)
        self.assertIn("multipart/form-data", headers["content-type"])
        body = request.data
        self.assertIn(b'name="attachments[]"; filename="Quote 1.pdf"', body)
        self.assertIn(b"%PDF-QUOTE%", body)
        self.assertIn(b'name="source_id"', body)
        self.assertIn(b"order_document:DOC-1", body)

    def test_document_delivery_reports_missing_chatwoot_token_when_no_webhook(self):
        result = None
        with patch.object(document_service, "DOCUMENT_DELIVERY_WEBHOOK_URL", ""), \
             patch.object(document_service, "CHATWOOT_API_TOKEN", ""):
            result = document_service._notify_document_delivery_workflow(
                {"Document_ID": "DOC-1", "Document_Type": "Quote", "Document_Ref": "Q-1"},
                conversation_id="1478",
                sent_by="Tester",
                account_id="147387",
            )

        self.assertFalse(result["sent"])
        self.assertTrue(result["skipped"])
        self.assertIn("CHATWOOT_API_ACCESS_TOKEN", result["error"])

    def test_document_delivery_requires_drive_file_id_for_direct_pdf_delivery(self):
        with patch.object(document_service, "DOCUMENT_DELIVERY_WEBHOOK_URL", ""), \
             patch.object(document_service, "CHATWOOT_API_TOKEN", "token"), \
             patch.object(document_service.urllib_request, "urlopen") as opener:
            result = document_service._notify_document_delivery_workflow(
                {"Document_ID": "DOC-1", "Document_Type": "Quote", "Document_Ref": "Q-1"},
                conversation_id="1478",
                sent_by="Tester",
                account_id="147387",
            )

        self.assertFalse(result["sent"])
        self.assertFalse(result["attachment_sent"])
        self.assertTrue(result["skipped"])
        self.assertIn("Google_Drive_File_ID", result["error"])
        opener.assert_not_called()

    def test_send_order_document_force_resend_bypasses_recent_sent_guard(self):
        document = {
            "Document_ID": "DOC-1",
            "Order_ID": "ORD-1",
            "Document_Type": "Quote",
            "Document_Ref": "Q-1",
            "Document_Status": "Sent",
            "Sent_At": document_service.datetime.now().strftime("%d %b %Y %H:%M"),
        }

        with patch.object(document_service, "get_order_document", return_value=document), \
             patch.object(document_service, "_notify_document_delivery_workflow", return_value={"sent": True}), \
             patch.object(document_service, "mark_document_sent") as mark_sent:
            result = document_service.send_order_document(
                "DOC-1",
                conversation_id="1478",
                sent_by="Tester",
                force_resend=True,
            )

        self.assertTrue(result["success"])
        self.assertFalse(result.get("skipped", False))
        mark_sent.assert_called_once_with("DOC-1", sent_by="Tester")


if __name__ == "__main__":
    unittest.main()
