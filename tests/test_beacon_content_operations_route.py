import unittest
import os
from unittest.mock import patch
from pathlib import Path

from app import app
from modules.auth.owner_access import configure_owner_access


READ_TOKEN = "beacon-read-token-1234567890abcdef"
ADMIN_TOKEN = "beacon-admin-token-1234567890abcdef"
SESSION_SECRET = "beacon-session-secret-1234567890abcdef"


def owner_env():
    return {
        "OWNER_ACCESS_ENABLED": "1",
        "OWNER_ACCESS_ALLOW_LOCAL_DEV": "0",
        "OWNER_READ_TOKEN": READ_TOKEN,
        "OWNER_ADMIN_TOKEN": ADMIN_TOKEN,
        "OWNER_SESSION_SECRET": SESSION_SECRET,
    }


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
            "/api/beacon/weekly-owner-review/BEACON-WEEK-2026-07-25-P1-S1/"
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
            "/api/beacon/weekly-owner-review/BEACON-WEEK-2026-07-25-P1-S1/"
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

    def test_weekly_owner_decision_requires_owner_admin(self):
        denied = ({"success": False, "status": "owner_admin_access_denied"}, 403)
        path = (
            "/api/beacon/weekly-owner-review/"
            "BEACON-WEEK-2026-07-25-P1-S1/decision"
        )
        with patch("app.require_owner_admin_access", return_value=denied), patch(
            "app.record_weekly_owner_review_decision"
        ) as record:
            response = self.client.post(path, json={"packet_id": "x"})
        self.assertEqual(response.status_code, 403)
        record.assert_not_called()

    def test_owner_admin_exact_decision_route_records_no_publish_authority(self):
        path = (
            "/api/beacon/weekly-owner-review/"
            "BEACON-WEEK-2026-07-25-P1-S1/decision"
        )
        payload = {
            "packet_id": "BEACON-WEEK-2026-07-25-P1-S1",
            "decision": "approve",
        }
        result = {
            "success": True,
            "status": "owner_review_decision_recorded",
            "decision_status": "owner_approved",
            "publish": False,
            "meta_call": False,
            "upload": False,
            "scheduled": False,
            "send": False,
            "spend": False,
        }
        with patch("app.require_owner_admin_access", return_value=None), patch(
            "app.owner_admin_principal", return_value="owner-admin:test"
        ), patch(
            "app.record_weekly_owner_review_decision",
            return_value=(result, 201),
        ) as record:
            response = self.client.post(path, json=payload)
            get_response = self.client.get(path)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(get_response.status_code, 405)
        self.assertFalse(response.get_json()["publish"])
        record.assert_called_once_with(payload, owner_identity="owner-admin:test")

    def test_authenticated_admin_route_uses_stable_server_principal(self):
        path = (
            "/api/beacon/weekly-owner-review/"
            "BEACON-WEEK-2026-07-25-P1-S1/decision"
        )
        payload = {
            "packet_id": "BEACON-WEEK-2026-07-25-P1-S1",
            "decision": "approve",
        }
        result = {
            "success": True,
            "status": "owner_review_decision_recorded",
            "publish": False,
            "meta_call": False,
            "upload": False,
            "scheduled": False,
            "send": False,
            "spend": False,
        }
        with patch.dict(os.environ, owner_env(), clear=False):
            configure_owner_access(app)
            login = self.client.post(
                "/owner/login",
                data={"owner_token": ADMIN_TOKEN, "next": "/sales/beacon-media"},
                environ_base={"REMOTE_ADDR": "203.0.113.10"},
            )
            with self.client.session_transaction() as owner_session:
                principal = owner_session["owner_access"]["principal_id"]
            with patch(
                "app.record_weekly_owner_review_decision",
                return_value=(result, 201),
            ) as record:
                response = self.client.post(
                    path,
                    json=payload,
                    environ_base={"REMOTE_ADDR": "203.0.113.10"},
                )
        self.assertEqual(login.status_code, 302)
        self.assertEqual(response.status_code, 201)
        self.assertTrue(principal.startswith("owner-admin:"))
        self.assertNotIn(ADMIN_TOKEN, principal)
        record.assert_called_once_with(payload, owner_identity=principal)

    def test_read_anonymous_and_missing_principal_cannot_decide(self):
        path = (
            "/api/beacon/weekly-owner-review/"
            "BEACON-WEEK-2026-07-25-P1-S1/decision"
        )
        payload = {
            "packet_id": "BEACON-WEEK-2026-07-25-P1-S1",
            "decision": "approve",
        }
        with patch.dict(os.environ, owner_env(), clear=False):
            configure_owner_access(app)
            with patch("app.record_weekly_owner_review_decision") as record:
                anonymous = self.client.post(
                    path,
                    json=payload,
                    environ_base={"REMOTE_ADDR": "203.0.113.10"},
                )
                self.client.post(
                    "/owner/login",
                    data={"owner_token": READ_TOKEN},
                    environ_base={"REMOTE_ADDR": "203.0.113.10"},
                )
                owner_read = self.client.post(
                    path,
                    json=payload,
                    environ_base={"REMOTE_ADDR": "203.0.113.10"},
                )
                with self.client.session_transaction() as owner_session:
                    owner_session["owner_access"] = {
                        "role": "admin",
                        "created_at": "2026-07-26T00:00:00+00:00",
                    }
                missing = self.client.post(
                    path,
                    json=payload,
                    environ_base={"REMOTE_ADDR": "203.0.113.10"},
                )
        self.assertEqual(anonymous.status_code, 403)
        self.assertEqual(owner_read.status_code, 403)
        self.assertEqual(missing.status_code, 403)
        self.assertEqual(missing.get_json()["status"], "owner_identity_required")
        record.assert_not_called()

    def test_client_supplied_owner_identity_is_rejected_before_persistence(self):
        path = (
            "/api/beacon/weekly-owner-review/"
            "BEACON-WEEK-2026-07-25-P1-S1/decision"
        )
        payload = {
            "packet_id": "BEACON-WEEK-2026-07-25-P1-S1",
            "decision": "approve",
            "owner_identity": "owner-admin:spoofed-browser-value",
        }
        with patch.dict(os.environ, owner_env(), clear=False):
            configure_owner_access(app)
            self.client.post(
                "/owner/login",
                data={"owner_token": ADMIN_TOKEN},
                environ_base={"REMOTE_ADDR": "203.0.113.10"},
            )
            with patch("app.record_weekly_owner_review_decision") as record:
                response = self.client.post(
                    path,
                    json=payload,
                    environ_base={"REMOTE_ADDR": "203.0.113.10"},
                )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.get_json()["status"], "client_owner_identity_prohibited"
        )
        record.assert_not_called()

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
        self.assertIn("Owner-confirmed subject:", script)
        self.assertIn("camera evidence · timezone unknown", script)
        self.assertIn("Prior confirmed use: none evidenced", script)
        self.assertIn("<strong>Supersedes</strong>", script)
        self.assertIn("No publication time scheduled", script)
        self.assertIn("Publish false · Meta call false · upload false", script)
        self.assertIn('id="beacon_packet_approve"', template)
        self.assertIn('id="beacon_packet_request_changes"', template)
        self.assertIn('id="beacon_packet_reject"', template)
        self.assertIn("Approval does not publish this post", template)
        self.assertIn("recordWeeklyOwnerDecision", script)
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
