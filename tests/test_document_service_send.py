import unittest
from unittest.mock import patch

from modules.documents import document_service


class DocumentServiceSendTests(unittest.TestCase):
    def test_document_delivery_falls_back_to_direct_chatwoot_when_webhook_missing(self):
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

        document = {
            "Document_ID": "DOC-1",
            "Document_Type": "Quote",
            "Document_Ref": "Q-1",
            "Google_Drive_URL": "https://drive.google.com/file/d/test/view",
            "Total": "1350.00",
            "Payment_Ref": "12BCCC",
            "Payment_Method": "Cash",
        }

        with patch.object(document_service, "DOCUMENT_DELIVERY_WEBHOOK_URL", ""), \
             patch.object(document_service, "CHATWOOT_API_TOKEN", "token"), \
             patch.object(document_service, "CHATWOOT_BASE_URL", "https://chatwoot.test"), \
             patch.object(document_service.urllib_request, "urlopen", side_effect=opener):
            result = document_service._notify_document_delivery_workflow(
                document,
                conversation_id="1478",
                sent_by="Tester",
                account_id="147387",
            )

        self.assertTrue(result["sent"])
        self.assertEqual(result["delivery_channel"], "chatwoot_direct")
        self.assertIn("Q-1", result["message_text"])
        self.assertIn("https://drive.google.com/file/d/test/view", result["message_text"])
        request = calls[0][0]
        self.assertEqual(request.full_url, "https://chatwoot.test/api/v1/accounts/147387/conversations/1478/messages")
        headers = {key.lower(): value for key, value in request.header_items()}
        self.assertIn("api_access_token", headers)

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


if __name__ == "__main__":
    unittest.main()
