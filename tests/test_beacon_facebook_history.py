import unittest

from modules.sales.beacon_facebook_history import _evidence_payloads, import_beacon_facebook_history


class BeaconFacebookHistoryTests(unittest.TestCase):
    def test_import_is_paginated_idempotent_and_evidence_only(self):
        pages = [
            ({"data": [{"id": "PAGE_1", "message": "Piglets for sale", "created_time": "2026-07-01T10:00:00+0000", "permalink_url": "https://facebook.test/1", "reactions": {"summary": {"total_count": 4}}, "comments": {"summary": {"total_count": 2}}, "shares": {"count": 1}}], "paging": {"next": "page-2"}}, 200),
            ({"data": [{"id": "PAGE_2", "message": "Farm morning", "created_time": "2026-06-30T10:00:00+0000"}]}, 200),
        ]
        manual_payloads = []
        performance_payloads = []

        def fetcher(_url):
            return pages.pop(0)

        def manual(payload):
            manual_payloads.append(payload)
            return {"success": True, "created_count": 1, "status": "recorded"}, 201

        def performance(payload):
            performance_payloads.append(payload)
            return {"success": True, "created_count": 1, "status": "recorded"}, 201

        result, status = import_beacon_facebook_history(
            environ={"BEACON_FACEBOOK_PAGE_ID": "PAGE", "BEACON_FACEBOOK_PAGE_ACCESS_TOKEN": "secret"},
            fetch_page=fetcher,
            manual_recorder=manual,
            performance_recorder=performance,
        )

        self.assertEqual(status, 200)
        self.assertEqual(result["fetched_count"], 2)
        self.assertEqual(result["imported_count"], 2)
        self.assertFalse(result["posts_publicly"])
        self.assertFalse(result["spends_money"])
        self.assertEqual(manual_payloads[0]["campaign_label"], "Imported - Live Stock")
        self.assertEqual(performance_payloads[0]["reactions"], 4)
        self.assertEqual(performance_payloads[0]["comments"], 2)
        self.assertEqual(performance_payloads[0]["shares"], 1)
        evidence = performance_payloads[0]["metric_evidence"]
        self.assertEqual(evidence["reactions"]["status"], "verified")
        self.assertEqual(evidence["reach"]["status"], "unsupported")
        self.assertIsNone(evidence["reach"]["value"])

    def test_explicit_zero_is_verified_but_absent_and_malformed_are_not(self):
        payload = _evidence_payloads({
            "id": "PAGE_3",
            "reactions": {"summary": {"total_count": 0}},
            "comments": {"summary": {}},
            "shares": {"count": "bad"},
        })["performance"]
        evidence = payload["metric_evidence"]
        self.assertEqual(evidence["reactions"]["status"], "verified")
        self.assertEqual(evidence["reactions"]["value"], 0)
        self.assertEqual(evidence["comments"]["status"], "missing")
        self.assertEqual(evidence["shares"]["status"], "malformed")
        self.assertNotIn("comments", payload)
        self.assertNotIn("shares", payload)

    def test_import_fails_closed_without_meta_configuration(self):
        result, status = import_beacon_facebook_history(environ={})
        self.assertEqual(status, 503)
        self.assertEqual(result["status"], "facebook_history_not_configured")
        self.assertFalse(result["posts_publicly"])


if __name__ == "__main__":
    unittest.main()
