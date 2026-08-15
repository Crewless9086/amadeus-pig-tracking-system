import os
from pathlib import Path
import unittest
from unittest.mock import patch

from app import app


OWNER_ENV = {
    "OWNER_ACCESS_ENABLED": "true",
    "OWNER_ACCESS_ALLOW_LOCAL_DEV": "false",
    "OWNER_SESSION_SECRET": "owner-session-secret-for-media-intake-tests",
    "OWNER_READ_TOKEN": "owner-read-token-for-media-intake-tests-1234",
    "OWNER_ADMIN_TOKEN": "owner-admin-token-for-media-intake-tests-123",
}


class BeaconMediaIntakeRouteTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def login(self, role):
        token = OWNER_ENV[f"OWNER_{role.upper()}_TOKEN"]
        response = self.client.post(
            "/owner/login",
            data={"owner_token": token},
            environ_base={"REMOTE_ADDR": "10.0.0.8"},
        )
        self.assertEqual(response.status_code, 302)

    @patch.dict(os.environ, OWNER_ENV, clear=True)
    def test_anonymous_list_thumbnail_and_review_are_denied(self):
        self.assertEqual(
            self.client.get(
                "/api/oom-sakkie/beacon/media-intakes",
                environ_base={"REMOTE_ADDR": "10.0.0.8"},
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.get(
                "/api/oom-sakkie/beacon/media-intakes/BINARY/thumbnail",
                environ_base={"REMOTE_ADDR": "10.0.0.8"},
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(
                "/api/oom-sakkie/beacon/media-intakes/BINARY/review",
                json={"event_type": "library_accepted"},
                environ_base={"REMOTE_ADDR": "10.0.0.8"},
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(
                "/api/oom-sakkie/beacon/media-intakes/groups/GROUP/review",
                json={"event_type": "library_accepted"},
                environ_base={"REMOTE_ADDR": "10.0.0.8"},
            ).status_code,
            403,
        )

    @patch.dict(os.environ, OWNER_ENV, clear=True)
    @patch("modules.oom_sakkie.routes.list_media_intakes")
    def test_owner_read_can_list_but_cannot_record_decision(self, list_intakes):
        self.login("read")
        list_intakes.return_value = (
            {"success": True, "items": [], "publish": False},
            200,
        )
        response = self.client.get(
            "/api/oom-sakkie/beacon/media-intakes",
            environ_base={"REMOTE_ADDR": "10.0.0.8"},
        )
        self.assertEqual(response.status_code, 200)
        denied = self.client.post(
            "/api/oom-sakkie/beacon/media-intakes/BINARY/review",
            json={"event_type": "library_accepted"},
            environ_base={"REMOTE_ADDR": "10.0.0.8"},
        )
        self.assertEqual(denied.status_code, 403)

    @patch.dict(os.environ, OWNER_ENV, clear=True)
    @patch("modules.oom_sakkie.routes.record_media_review")
    def test_owner_admin_records_review_without_publication_authority(self, record):
        self.login("admin")
        record.return_value = ({
            "success": True,
            "status": "media_review_event_recorded",
            "created_count": 1,
            "publish": False,
            "meta_call": False,
            "schedule": False,
            "advertise": False,
            "boost": False,
            "spend": False,
        }, 201)
        response = self.client.post(
            "/api/oom-sakkie/beacon/media-intakes/BINARY/review",
            json={
                "event_type": "library_accepted",
                "owner_principal": "browser-spoof-must-not-be-used",
            },
            environ_base={"REMOTE_ADDR": "10.0.0.8"},
        )
        self.assertEqual(response.status_code, 201)
        principal = record.call_args.args[2]
        self.assertTrue(principal.startswith("owner-admin:"))
        self.assertNotEqual(principal, "browser-spoof-must-not-be-used")
        body = response.get_json()
        for key in ("publish", "meta_call", "schedule", "advertise", "boost", "spend"):
            self.assertFalse(body[key])

    @patch.dict(os.environ, OWNER_ENV, clear=True)
    @patch("modules.oom_sakkie.routes.private_album_review")
    def test_owner_read_can_load_exact_private_album_review(self, review):
        self.login("read")
        review.return_value = ({
            "success": True,
            "contract_version": "beacon_private_album_review_v1",
            "intake_group_id": "GROUP",
            "album_digest": "d" * 64,
            "stored_count": 8,
            "ordered_media": [],
            "publish": False,
        }, 200)
        response = self.client.get(
            "/api/oom-sakkie/beacon/media-intakes/groups/GROUP/review",
            environ_base={"REMOTE_ADDR": "10.0.0.8"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["stored_count"], 8)
        review.assert_called_once_with("GROUP")

    @patch.dict(os.environ, OWNER_ENV, clear=True)
    @patch("modules.oom_sakkie.routes.record_media_group_review")
    @patch("modules.oom_sakkie.routes.canonical_media_group_owner_binding")
    def test_owner_admin_can_record_atomic_album_review(self, binding, record):
        self.login("admin")
        binding.return_value=({"success":True,"owner_principal":"telegram-owner:CANONICAL",
            "chat_hmac":"h"*64},200)
        record.return_value = ({
            "success": True,
            "status": "media_group_review_recorded",
            "created_count": 3,
            "publish": False,
            "meta_call": False,
            "schedule": False,
            "advertise": False,
            "boost": False,
            "spend": False,
        }, 201)
        response = self.client.post(
            "/api/oom-sakkie/beacon/media-intakes/groups/GROUP/review",
            json={
                "event_type": "library_accepted",
                "contract_version": "beacon_private_album_review_v1",
                "album_digest": "d" * 64,
                "owner_principal": "browser-spoof-must-not-be-used",
            },
            environ_base={"REMOTE_ADDR": "10.0.0.8"},
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(record.call_args.args[2],"telegram-owner:CANONICAL")
        self.assertEqual(record.call_args.args[1]["subject_chat_hmac"],"h"*64)
        self.assertNotEqual(
            record.call_args.args[2], "browser-spoof-must-not-be-used"
        )

    @patch.dict(os.environ, OWNER_ENV, clear=True)
    @patch("modules.oom_sakkie.routes.read_private_thumbnail")
    def test_owner_thumbnail_is_private_nosniff_and_not_cached(self, read_thumbnail):
        self.login("read")
        read_thumbnail.return_value = ({
            "success": True,
            "body": b"private-jpeg",
            "content_type": "image/jpeg",
            "cache_control": "private, max-age=60, no-store",
        }, 200)
        response = self.client.get(
            "/api/oom-sakkie/beacon/media-intakes/BINARY/thumbnail",
            environ_base={"REMOTE_ADDR": "10.0.0.8"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
        self.assertIn("private", response.headers["Cache-Control"])
        self.assertIn("no-store", response.headers["Cache-Control"])

    def test_story_desk_visual_contract_exposes_private_media_not_filenames(self):
        template = Path("templates/beacon-media.html").read_text(encoding="utf-8")
        script = Path("static/js/beaconMedia.js").read_text(encoding="utf-8")
        styles = Path("static/css/beaconMedia.css").read_text(encoding="utf-8")
        for control in (
            "Library Accept", "Public-use Approve", "Reject", "Archive",
            "Edit owner context",
        ):
            self.assertIn(control, script)
        self.assertIn('id="beacon_intake_contact_sheet"', template)
        self.assertIn('id="beacon_intake_preview_image"', template)
        self.assertIn("Private originals and thumbnails require an owner session", template)
        self.assertIn("/api/oom-sakkie/beacon/media-intakes", script)
        self.assertIn("Capture: Unknown", script)
        self.assertIn(".beacon-intake-contact-sheet", styles)
        self.assertIn("@media (max-width: 620px)", styles)
        self.assertNotIn("storage_path", script)
        self.assertNotIn("telegram_file_id", script)


if __name__ == "__main__":
    unittest.main()
