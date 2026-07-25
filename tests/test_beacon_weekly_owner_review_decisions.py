import sys
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

from modules.beacon.weekly_owner_review import EXACT_CAPTION, MEDIA_SPEC, build_post_one_owner_review
from modules.beacon.weekly_owner_review_decisions import record_weekly_owner_review_decision


def eligible_assets():
    return [{
        "asset_id": item["asset_id"], "media_type": "image",
        "mime_type": "image/jpeg", "file_size_bytes": item["file_size_bytes"],
        "created_at": item["upload_timestamp"],
        "effective_approval_status": "approved",
        "effective_public_use_approved": True,
        "content_hash_provenance": "server_computed_on_upload",
        "content_sha256": "a" * 64,
    } for item in MEDIA_SPEC]


def exact_payload(decision="approve"):
    packet = build_post_one_owner_review(eligible_assets())
    return {
        "decision": decision, "packet_id": packet["packet_id"], "packet_version": "S1",
        "canonical_sha256": packet["canonical_sha256"],
        "caption_sha256": packet["caption_sha256"],
        "exact_caption": packet["caption"],
        "ordered_media_ids": packet["media"]["exact_order"],
        "owner_confirmed_subject": packet["media"]["assets"][0]["owner_confirmed_subject"],
        "album_story": packet["album_story"], "channel": packet["channel"],
        "supersedes_packet_id": packet["supersedes"]["packet_id"],
        "owner_notes": "", "proposed_publication_datetime": "",
        "proposed_timezone": "",
    }


class FakeCursor:
    def __init__(self, store):
        self.store, self.row = store, None

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, params):
        if "select decision_event_id" in sql:
            item = self.store.get(params[0])
            self.row = None if not item else (
                item["decision_event_id"], item["packet_id"], item["packet_version"],
                item["canonical_sha256"], item["caption_sha256"], item["exact_caption"],
                item["ordered_media_ids"], item["owner_confirmed_subject"],
                item["album_story"], item["channel"],
                item["proposed_publication_datetime"], item["proposed_timezone"],
                item["supersedes_packet_id"], item["decision_status"],
                item["owner_notes"], item["owner_identity"], item["decision_at"],
            )
        elif "insert into public.beacon_weekly_review_decision_events" in sql:
            item = dict(params)
            item["decision_at"] = datetime(2026, 7, 25, 20, tzinfo=timezone.utc)
            self.store[item["packet_id"]] = item

    def fetchone(self):
        return self.row


class FakeConnection:
    def __init__(self, store):
        self.store = store

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def cursor(self):
        return FakeCursor(self.store)

    def commit(self):
        pass


class WeeklyOwnerReviewDecisionTests(unittest.TestCase):
    def setUp(self):
        self.store = {}
        fake = SimpleNamespace(connect=lambda *_a, **_k: FakeConnection(self.store))
        self.patches = [
            patch.dict(sys.modules, {"psycopg": fake}),
            patch(
                "modules.beacon.weekly_owner_review_decisions.list_beacon_media_assets",
                return_value=({"assets": eligible_assets()}, 200),
            ),
            patch(
                "modules.beacon.weekly_owner_review_decisions.load_post_one_thumbnail",
                return_value=({"success": True}, 200),
            ),
        ]
        for item in self.patches:
            item.start()

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()

    def record(self, payload):
        return record_weekly_owner_review_decision(
            payload, owner_identity="owner-admin:test-principal",
            database_url="postgresql://fixture",
        )

    def test_exact_approval_is_append_only_and_has_no_execution_authority(self):
        result, status = self.record(exact_payload())
        self.assertEqual(status, 201)
        self.assertEqual(result["decision_status"], "owner_approved")
        self.assertEqual(len(self.store), 1)
        stored = self.store[result["packet_id"]]
        self.assertEqual(stored["exact_caption"], EXACT_CAPTION)
        self.assertEqual(stored["ordered_media_ids"], [i["asset_id"] for i in MEDIA_SPEC])
        self.assertEqual(stored["owner_confirmed_subject"], "Ms. Piggy and her litter")
        self.assertEqual(stored["packet_version"], "S1")
        self.assertEqual(stored["supersedes_packet_id"], "BEACON-WEEK-2026-07-25-P1")
        self.assertTrue(result["decision_at"].endswith("+00:00"))
        for key in ("publish", "meta_call", "upload", "scheduled", "send", "spend"):
            self.assertFalse(result[key])
        self.assertEqual(result["publication_authority_status"], "publication_not_authorized")

    def test_wrong_hash_changed_caption_and_changed_order_fail_closed(self):
        cases = [
            ("canonical_sha256", "0" * 64, "weekly_owner_review_hash_mismatch"),
            ("exact_caption", "changed", "weekly_owner_review_caption_changed"),
            ("ordered_media_ids", list(reversed(exact_payload()["ordered_media_ids"])), "weekly_owner_review_media_order_changed"),
            ("owner_confirmed_subject", "Unknown", "weekly_owner_review_subject_changed"),
            ("album_story", "Different album", "weekly_owner_review_album_changed"),
        ]
        for field, value, expected in cases:
            with self.subTest(field=field):
                payload = exact_payload()
                payload[field] = value
                result, status = self.record(payload)
                self.assertEqual((status, result["status"]), (409, expected))
                self.assertFalse(result["publish"])
        self.assertEqual(self.store, {})

    def test_superseded_packet_and_asset_drift_fail_closed(self):
        payload = exact_payload()
        payload["packet_id"] = "BEACON-WEEK-2026-07-25-P1"
        result, status = self.record(payload)
        self.assertEqual((status, result["status"]), (409, "weekly_owner_review_packet_superseded"))
        with patch(
            "modules.beacon.weekly_owner_review_decisions.load_post_one_thumbnail",
            return_value=({"success": False}, 409),
        ):
            result, status = self.record(exact_payload())
        self.assertEqual((status, result["status"]), (409, "weekly_owner_review_asset_drift"))

    def test_duplicate_is_withheld_and_conflicting_decision_is_rejected(self):
        first, first_status = self.record(exact_payload())
        replay, replay_status = self.record(exact_payload())
        conflict, conflict_status = self.record(exact_payload("reject"))
        self.assertEqual(first_status, 201)
        self.assertEqual((replay_status, replay["status"]), (200, "duplicate_owner_decision_withheld"))
        self.assertEqual((conflict_status, conflict["status"]), (409, "conflicting_owner_decision_exists"))
        self.assertEqual(len(self.store), 1)
        self.assertEqual(first["decision_event_id"], replay["decision_event_id"])

    def test_changes_and_rejection_preserve_original_packet(self):
        missing, status = self.record(exact_payload("request_changes"))
        self.assertEqual((status, missing["status"]), (400, "owner_change_notes_required"))
        payload = exact_payload("request_changes")
        payload["owner_notes"] = " Use the second image first.\nKeep the farm-story tone. "
        result, status = self.record(payload)
        self.assertEqual((status, result["decision_status"]), (201, "changes_requested"))
        self.assertEqual(self.store[result["packet_id"]]["exact_caption"], EXACT_CAPTION)
        self.store.clear()
        rejected, status = self.record(exact_payload("reject"))
        self.assertEqual((status, rejected["decision_status"]), (201, "owner_rejected"))
        self.assertEqual(self.store[rejected["packet_id"]]["exact_caption"], EXACT_CAPTION)

    def test_missing_persistence_fails_closed(self):
        result, status = record_weekly_owner_review_decision(
            exact_payload(), owner_identity="owner-admin:test", database_url=""
        )
        self.assertEqual((status, result["status"]), (503, "weekly_owner_review_persistence_unavailable"))

    def test_owner_identity_and_optional_timing_are_bound(self):
        denied, status = record_weekly_owner_review_decision(
            exact_payload(), owner_identity="", database_url="postgresql://fixture"
        )
        self.assertEqual((status, denied["status"]), (403, "owner_identity_required"))
        payload = exact_payload()
        payload["proposed_publication_datetime"] = "2026-07-26T18:00"
        payload["proposed_timezone"] = "Africa/Johannesburg"
        result, status = self.record(payload)
        self.assertEqual(status, 201)
        stored = self.store[result["packet_id"]]
        self.assertEqual(stored["proposed_publication_datetime"], "2026-07-26T18:00")
        self.assertEqual(stored["proposed_timezone"], "Africa/Johannesburg")
        self.assertFalse(result["scheduled"])

    def test_migration_is_append_only_and_separate_from_execution(self):
        with open(
            "supabase/migrations/202607250001_create_beacon_weekly_review_decisions.sql",
            encoding="utf-8",
        ) as source:
            migration = source.read()
        self.assertIn("beacon_weekly_review_decision_events", migration)
        self.assertIn("before update", migration.lower())
        self.assertIn("before delete", migration.lower())
        self.assertIn("publication_not_authorized", migration)
        self.assertNotIn("facebook_post_id", migration)
        self.assertNotIn("access_token", migration.lower())


if __name__ == "__main__":
    unittest.main()
