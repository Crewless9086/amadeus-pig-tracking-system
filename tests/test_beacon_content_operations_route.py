import unittest
from unittest.mock import patch
from pathlib import Path

from app import app


class BeaconContentOperationsRouteTests(unittest.TestCase):
    def setUp(self):
        app.testing = True
        self.client = app.test_client()

    def test_endpoint_stops_before_reads_when_owner_access_is_denied(self):
        denied = ({"success": False, "status": "owner_access_denied"}, 403)
        with patch("app.require_owner_read_access", return_value=denied), patch(
            "app.gather_beacon_content_evidence"
        ) as gather:
            response = self.client.get("/api/beacon/content-operations")

        self.assertEqual(response.status_code, 403)
        gather.assert_not_called()

    def test_endpoint_is_get_only_and_returns_review_packet_without_authority(self):
        evidence = {
            "historical_posts": {"records": []},
            "performance_events": {"records": []},
            "media_assets": {"records": []},
            "opportunities": {"records": [], "availability": "inaccessible"},
        }
        with patch("app.require_owner_read_access", return_value=None), patch(
            "app.gather_beacon_content_evidence", return_value=evidence
        ):
            response = self.client.get("/api/beacon/content-operations")
            post_response = self.client.post("/api/beacon/content-operations", json={})

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["owner_review_packet"]["review_status"], "awaiting_owner_review")
        self.assertFalse(payload["learning_capture"]["writes_performed"])
        for flag in (
            "posts_publicly",
            "sends_customer_messages",
            "calls_meta",
            "creates_ads",
            "boosts_posts",
            "spends_money",
            "creates_orders",
            "reserves_stock",
            "changes_stock",
            "writes_farm_data",
        ):
            self.assertFalse(payload["authority"][flag])
        self.assertEqual(post_response.status_code, 405)

    def test_existing_owner_screen_contains_content_operations_panel(self):
        template = Path("templates/beacon-media.html").read_text(encoding="utf-8")
        script = Path("static/js/beaconMedia.js").read_text(encoding="utf-8")

        self.assertIn('id="beacon_ranked_ideas"', template)
        self.assertIn('id="beacon_packet_copy"', template)
        self.assertIn('id="beacon_delivery_state"', template)
        self.assertIn('fetchJson("/api/beacon/content-operations")', script)


if __name__ == "__main__":
    unittest.main()
