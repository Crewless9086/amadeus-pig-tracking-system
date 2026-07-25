import unittest
from unittest.mock import patch
from pathlib import Path

from app import app


class BeaconContentOperationsRouteTests(unittest.TestCase):
    def setUp(self):
        app.testing = True
        self.client = app.test_client()

    @patch("app.load_post_one_thumbnail")
    @patch("app.require_owner_read_access", return_value=None)
    def test_weekly_packet_thumbnail_is_owner_read_get_only_no_store(
        self, _guard, loader
    ):
        loader.return_value = ({
            "data": b"jpeg",
            "mime_type": "image/jpeg",
            "width": 4000,
            "height": 3000,
        }, 200)
        path = (
            "/api/beacon/weekly-owner-review/BEACON-WEEK-2026-07-25-P1/"
            "media/BEACON-ASSET-3D9A65053184D8181A"
        )
        response = self.client.get(path)
        post = self.client.post(path)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Cache-Control"], "no-store, private")
        self.assertEqual(response.headers["X-Beacon-Dimensions"], "4000x3000")
        self.assertEqual(post.status_code, 405)

    @patch("app.load_post_one_thumbnail")
    @patch("app.require_owner_read_access")
    def test_weekly_packet_thumbnail_requires_owner_read(
        self, guard, loader
    ):
        guard.return_value = ({"status": "owner_read_access_denied"}, 403)
        response = self.client.get(
            "/api/beacon/weekly-owner-review/BEACON-WEEK-2026-07-25-P1/"
            "media/BEACON-ASSET-3D9A65053184D8181A"
        )
        self.assertEqual(response.status_code, 403)
        loader.assert_not_called()

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
        self.assertNotIn("delivery_state", payload)
        self.assertNotIn("built", payload["runtime_status"])
        self.assertNotIn("merged", payload["runtime_status"])
        self.assertNotIn("deployed", payload["runtime_status"])
        self.assertNotIn("operational", payload["runtime_status"])
        self.assertTrue(payload["runtime_status"]["endpoint_available"])
        self.assertTrue(payload["runtime_status"]["owner_authenticated_read_succeeded"])
        self.assertTrue(payload["runtime_status"]["packet_generated"])
        self.assertFalse(payload["runtime_status"]["writes_performed"])
        self.assertFalse(payload["runtime_status"]["publishing_performed"])
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
        self.assertIn('id="beacon_packet_options"', template)
        self.assertIn('id="beacon_content_explanations"', template)
        self.assertIn('id="beacon_runtime_state"', template)
        self.assertNotIn('id="beacon_delivery_state"', template)
        self.assertIn('fetchJson("/api/beacon/content-operations")', script)
        self.assertNotIn('["built", "merged", "deployed", "operational"]', script)
        self.assertIn('"Not imported"', script)
        self.assertIn('"Not verified"', script)
        self.assertIn("<summary>Technical diagnostics</summary>", script)
        self.assertNotIn(
            '<strong class="beacon-decision-blocker">${escapeHtml(risk)}</strong>',
            script,
        )

    def test_meta_ads_preview_requires_owner_auth_and_post_is_405(self):
        denied = ({"success": False, "status": "owner_access_denied"}, 403)
        with patch("app.require_owner_read_access", return_value=denied), patch(
            "app.build_meta_ads_insights_preview"
        ) as preview:
            denied_response = self.client.get(
                "/api/beacon/meta-ads-insights-preview"
            )
        self.assertEqual(denied_response.status_code, 403)
        preview.assert_not_called()

        payload = {
            "success": True,
            "status": "preview_ready",
            "banner": "Preview only — nothing imported",
            "authority": {"imports_evidence": False, "http_get_only": True},
        }
        with patch("app.require_owner_read_access", return_value=None), patch(
            "app.build_meta_ads_insights_preview", return_value=(payload, 200)
        ) as preview:
            response = self.client.get(
                "/api/beacon/meta-ads-insights-preview"
                "?start=2026-01-01&end=2026-01-31&level=campaign"
            )
            post_response = self.client.post(
                "/api/beacon/meta-ads-insights-preview", json={}
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["status"], "preview_ready")
        preview.assert_called_once_with(
            start_date="2026-01-01",
            end_date="2026-01-31",
            level="campaign",
        )
        self.assertEqual(post_response.status_code, 405)

    def test_story_desk_contains_get_only_meta_preview_presentation(self):
        template = Path("templates/beacon-media.html").read_text(encoding="utf-8")
        script = Path("static/js/beaconMedia.js").read_text(encoding="utf-8")

        for identifier in (
            'id="beacon_meta_preview_title"',
            'id="beacon_meta_preview_state"',
            'id="beacon_meta_preview_metrics"',
            'id="beacon_meta_preview_events"',
        ):
            self.assertIn(identifier, template)
        self.assertIn("Preview only — nothing imported", template)
        self.assertIn(
            "fetch(`/api/beacon/meta-ads-insights-preview?",
            script,
        )
        self.assertIn('{method: "GET"}', script)
        self.assertNotIn("graph.facebook.com", script.lower())
        self.assertNotIn("BEACON_META_ADS_READ_TOKEN", script)

    def test_meta_import_prepare_and_execute_use_separate_owner_guards(self):
        denied = ({"success": False, "status": "owner_access_denied"}, 403)
        with patch("app.require_owner_read_access", return_value=denied), patch(
            "app.prepare_meta_ads_import_packet"
        ) as prepare:
            response = self.client.get(
                "/api/beacon/meta-ads-import-packet"
                "?start=2026-07-01&end=2026-07-14&level=ad"
            )
        self.assertEqual(response.status_code, 403)
        prepare.assert_not_called()

        packet = {
            "success": True,
            "status": "meta_import_packet_prepared",
            "packet_hash": "HASH",
        }
        with patch("app.require_owner_read_access", return_value=None), patch(
            "app.prepare_meta_ads_import_packet", return_value=(packet, 200)
        ) as prepare:
            response = self.client.get(
                "/api/beacon/meta-ads-import-packet"
                "?start=2026-07-01&end=2026-07-14&level=ad"
            )
            post_prepare = self.client.post(
                "/api/beacon/meta-ads-import-packet", json={}
            )
        self.assertEqual(response.status_code, 200)
        prepare.assert_called_once_with(
            start_date="2026-07-01",
            end_date="2026-07-14",
            level="ad",
        )
        self.assertEqual(post_prepare.status_code, 405)

        with patch("app.require_owner_admin_access", return_value=denied), patch(
            "app.execute_meta_ads_import_packet"
        ) as execute:
            denied_execute = self.client.post(
                "/api/beacon/meta-ads-import-packet/execute", json={}
            )
        self.assertEqual(denied_execute.status_code, 403)
        execute.assert_not_called()
        self.assertEqual(
            self.client.get(
                "/api/beacon/meta-ads-import-packet/execute"
            ).status_code,
            405,
        )

    def test_unapproved_import_post_is_rejected_without_write(self):
        rejected = {
            "success": False,
            "status": "owner_exact_packet_approval_required",
            "created_count": 0,
        }
        with patch("app.require_owner_admin_access", return_value=None), patch(
            "app.execute_meta_ads_import_packet", return_value=(rejected, 403)
        ) as execute:
            response = self.client.post(
                "/api/beacon/meta-ads-import-packet/execute", json={}
            )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.get_json()["created_count"], 0)
        execute.assert_called_once_with({})

    def test_story_desk_contains_exact_import_review_panel(self):
        template = Path("templates/beacon-media.html").read_text(encoding="utf-8")
        script = Path("static/js/beaconMedia.js").read_text(encoding="utf-8")
        for identifier in (
            'id="beacon_meta_import_title"',
            'id="beacon_meta_import_prepare"',
            'id="beacon_meta_import_approval"',
            'id="beacon_meta_import_execute"',
        ):
            self.assertIn(identifier, template)
        self.assertIn("/api/beacon/meta-ads-import-packet?", script)
        self.assertIn("/api/beacon/meta-ads-import-packet/execute", script)
        self.assertIn("approved_packet_hash", script)
        self.assertIn("owner_approved: true", script)
        self.assertNotIn("BEACON_META_ADS_READ_TOKEN", script)


if __name__ == "__main__":
    unittest.main()
