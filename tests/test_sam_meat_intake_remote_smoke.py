import unittest

from scripts.sam_meat_intake_remote_smoke import (
    _base_url_is_local_or_tls,
    _has_forbidden_authority,
    build_smoke_payload,
)


class SamMeatIntakeRemoteSmokeTests(unittest.TestCase):
    def test_smoke_payload_is_tracking_only_meat_interest(self):
        payload = build_smoke_payload()

        self.assertEqual(payload["customer_name"], "Sam Remote Smoke")
        self.assertEqual(payload["product_type"], "half_carcass")
        self.assertEqual(payload["cut_set"], "Set A")
        self.assertEqual(payload["location"], "Riversdale")
        self.assertEqual(payload["channel"], "chatwoot_whatsapp")
        self.assertEqual(payload["status"], "interested")
        self.assertEqual(payload["price_per_kg"], "")
        self.assertEqual(payload["deposit_rule"], "")

    def test_base_url_must_be_local_http_or_https(self):
        self.assertTrue(_base_url_is_local_or_tls("http://127.0.0.1:5000"))
        self.assertTrue(_base_url_is_local_or_tls("http://localhost:5000"))
        self.assertTrue(_base_url_is_local_or_tls("https://amadeus-pig-tracking-system.onrender.com"))
        self.assertFalse(_base_url_is_local_or_tls("http://amadeus-pig-tracking-system.onrender.com"))
        self.assertFalse(_base_url_is_local_or_tls("ftp://example.com"))

    def test_forbidden_authority_detection_checks_response_layers(self):
        safe = {
            "sends_customer_message": False,
            "remote_ingest": {
                "records_tracking_lead": True,
                "sends_customer_message": False,
                "calls_chatwoot": False,
                "calls_n8n": False,
                "creates_order": False,
                "changes_stock": False,
                "financial_action": False,
            },
            "contract": {
                "authority": {
                    "sends_customer_message": False,
                    "creates_order": False,
                    "changes_stock": False,
                }
            },
        }
        unsafe = {
            "remote_ingest": {
                "records_tracking_lead": True,
                "financial_action": True,
            }
        }

        self.assertFalse(_has_forbidden_authority(safe))
        self.assertTrue(_has_forbidden_authority(unsafe))


if __name__ == "__main__":
    unittest.main()
