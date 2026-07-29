import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from modules.beacon.media_intake import (
    AUTHORITY,
    MAX_IMAGE_BYTES,
    IntakeFailure,
    _download_telegram_file,
    _thumbnail_bytes,
    _thumbnail_token,
    _thumbnail_token_valid,
    _validate_streamed_image,
    handle_telegram_media_intake,
    media_intake_policy,
    telegram_media_envelope,
)


ENV = {
    "BEACON_TELEGRAM_MEDIA_INTAKE_ENABLED": "true",
    "BEACON_TELEGRAM_MEDIA_REQUEST_NOT_BEFORE_UTC": "2026-07-26T10:00:00Z",
    "BEACON_TELEGRAM_MEDIA_RETIRED_SHA256": "0" * 64,
    "BEACON_TELEGRAM_MEDIA_ALLOWED_CHAT_IDS": "200",
    "OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS": "100",
    "OOM_SAKKIE_TELEGRAM_BOT_TOKEN": "not-used-test-token",
    "OWNER_SESSION_SECRET": "stable-test-secret",
    "DATABASE_URL": "postgresql://unit-test-not-used",
    "SUPABASE_URL": "https://private-storage.invalid",
    "SUPABASE_SERVICE_ROLE_KEY": "test-service-key-not-exposed",
}


def telegram_photo(**overrides):
    message = {
        "message_id": 20,
        "date": 1785080000,
        "chat": {"id": 200, "type": "private"},
        "from": {"id": 100},
        "caption": "Ms. Piggy and her litter; capture date unknown.",
        "photo": [{
            "file_id": "file-1",
            "file_unique_id": "unique-1",
            "file_size": 1200,
            "width": 640,
            "height": 480,
        }],
    }
    message.update(overrides.pop("message", {}))
    payload = {"update_id": 10, "message": message}
    payload.update(overrides)
    return payload


def image_temp(format_name="JPEG", size=(640, 480)):
    handle = tempfile.NamedTemporaryFile(suffix=f".{format_name.lower()}", delete=False)
    handle.close()
    Image.new("RGB", size, (119, 78, 42)).save(handle.name, format_name)
    return handle.name


class FakeStore:
    replay = False
    finalize_status = 201
    events = []
    existing = None

    def __init__(self, _database_url=None):
        pass

    def prepare(self, _envelope, _identity):
        if self.replay:
            return {"status": "exact_intake_replay_withheld", "replayed": True}, 200
        return {"status": "media_intake_pending_created", "replayed": False}, 201

    def source_status(self, _envelope, _identity):
        if self.replay:
            return {"status": "exact_intake_replay_withheld", "replayed": True}, 200
        return {"status": "media_intake_source_is_fresh", "replayed": False}, 200

    def event(self, _identity, event_type, evidence):
        self.events.append((event_type, evidence))
        return True

    def existing_binary(self, _content_sha256):
        return self.existing

    def existing_asset_hash(self, _content_sha256):
        return False

    def finalize(self, _envelope, identity, media):
        if self.finalize_status >= 400:
            return {"status": "media_intake_finalize_failed"}, self.finalize_status
        return {
            "status": "media_intake_stored_private_review_pending",
            "intake_group_id": identity["group_id"],
            "intake_item_id": identity["item_id"],
            "binary_asset_id": media["binary_asset_id"],
            "beacon_asset_id": "BEACON-ASSET-TEST",
            "exact_duplicate": False,
            "classification": media["classification"],
            "observation_event_id": "BEACON-UNDERSTANDING-TEST",
        }, 201

    def offer_album_completion(self, identity):
        return {"created_count": 1, "completion_code": "ABC123"}


class FakeStorage:
    def __init__(self, *, fail_put_at=0, readback_changed=False, cleanup=True):
        self.put_count = 0
        self.objects = {}
        self.fail_put_at = fail_put_at
        self.readback_changed = readback_changed
        self.cleanup = cleanup

    def put(self, path, body, content_type):
        self.put_count += 1
        if self.put_count == self.fail_put_at:
            return {"success": False, "status": "simulated_storage_failure"}
        self.objects[path] = (body, content_type)
        return {"success": True}

    def get(self, path, _max_bytes):
        body = self.objects[path][0]
        return body + b"changed" if self.readback_changed else body

    def delete_many(self, paths):
        if self.cleanup:
            for path in paths:
                self.objects.pop(path, None)
        return {"success": self.cleanup}


class FakeHttpResponse:
    def __init__(self, body, headers=None):
        self.stream = io.BytesIO(body)
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, size=-1):
        return self.stream.read(size)


class BeaconMediaIntakeTests(unittest.TestCase):
    def setUp(self):
        FakeStore.replay = False
        FakeStore.finalize_status = 201
        FakeStore.events = []
        FakeStore.existing = None

    def test_policy_is_inactive_by_default_and_video_is_visibly_unsupported(self):
        policy = media_intake_policy({})
        self.assertFalse(policy["enabled"])
        self.assertEqual(policy["video_state"], "unsupported_until_bounded_resumable_upload")
        self.assertTrue(all(value is False for value in AUTHORITY.values()))
        migration = Path(
            "supabase/migrations/202607270001_create_beacon_media_intake.sql"
        ).read_text(encoding="utf-8")
        self.assertNotIn("beacon_organic_media_learning_events", migration)
        self.assertNotIn("confirmed_publication", migration)
        self.assertNotIn("graduation_evaluation", migration)

    def test_private_thumbnail_token_is_bound_and_short_lived(self):
        token = _thumbnail_token("BEACON-BINARY-1", ENV, now=1000)
        self.assertTrue(
            _thumbnail_token_valid(
                "BEACON-BINARY-1", token["token"], token["expires"], ENV, now=1001
            )
        )
        self.assertFalse(
            _thumbnail_token_valid(
                "BEACON-BINARY-2", token["token"], token["expires"], ENV, now=1001
            )
        )
        self.assertFalse(
            _thumbnail_token_valid(
                "BEACON-BINARY-1", token["token"], token["expires"], ENV, now=1121
            )
        )

    def test_extracts_owner_context_without_inventing_capture_time(self):
        result = telegram_media_envelope(telegram_photo())
        self.assertEqual(result["media_kind"], "photo")
        self.assertEqual(result["capture_time_state"], "unknown")
        self.assertIsNone(result["capture_time"])
        self.assertEqual(result["owner_explanation"], "Ms. Piggy and her litter; capture date unknown.")

    def test_rejects_unauthorized_user_wrong_chat_group_and_forwarded_source(self):
        cases = [
            (telegram_photo(message={"from": {"id": 999}}), "telegram_owner_user_not_allowed"),
            (telegram_photo(message={"chat": {"id": 999, "type": "private"}}), "telegram_private_chat_not_allowed"),
            (telegram_photo(message={"chat": {"id": 200, "type": "group"}}), "owner_private_original_media_required"),
            (telegram_photo(message={"forward_date": 1785000000}), "owner_private_original_media_required"),
        ]
        for payload, expected in cases:
            with self.subTest(expected=expected):
                result, status = handle_telegram_media_intake(payload, environ=ENV)
                self.assertEqual(status, 403)
                self.assertEqual(result["status"], expected)

    def test_exact_replay_stops_before_download_or_storage(self):
        FakeStore.replay = True
        fetch_calls = []
        with patch("modules.beacon.media_intake.IntakeStore", FakeStore):
            result, status = handle_telegram_media_intake(
                telegram_photo(), environ=ENV,
                fetcher=lambda *_: fetch_calls.append(True),
                storage=FakeStorage(),
            )
        self.assertEqual((status, result["status"]), (200, "exact_intake_replay_withheld"))
        self.assertEqual(fetch_calls, [])

    def test_photo_before_fresh_ready_request_is_withheld_before_download(self):
        env = {**ENV, "BEACON_TELEGRAM_MEDIA_REQUEST_NOT_BEFORE_UTC": "2026-07-27T00:00:00Z"}
        result, status = handle_telegram_media_intake(
            telegram_photo(), environ=env,
            fetcher=lambda *_: self.fail("must not download a pre-request photo"),
        )
        self.assertEqual((status, result["status"]), (
            409, "telegram_media_predates_fresh_owner_request"
        ))

    def test_valid_image_stream_is_hashed_uploaded_verified_and_not_public(self):
        path = image_temp()
        original = Path(path).read_bytes()
        storage = FakeStorage()
        receipts = []
        with patch("modules.beacon.media_intake.IntakeStore", FakeStore):
            result, status = handle_telegram_media_intake(
                telegram_photo(), environ=ENV,
                fetcher=lambda *_: (path, {"byte_size": len(original), "returned_mime_type": "image/jpeg"}),
                storage=storage,
                receipt_sender=lambda chat, text: receipts.append((chat, text)) or {"success": True},
            )
        self.assertEqual(status, 201)
        self.assertEqual(result["status"], "media_intake_stored_private_review_pending")
        self.assertEqual(storage.put_count, 2)
        self.assertTrue(result["receipt_sent"])
        self.assertEqual(result["classification"]["classification"], "private_farm_photo")
        self.assertFalse(result["classification"]["public_use_approved"])
        self.assertTrue(all(result[key] is False for key in AUTHORITY))
        self.assertNotIn("chat_id", result)
        self.assertNotIn("owner_user_id", result)
        self.assertNotIn("stable-test-secret", str(result))

    def test_album_does_not_guess_completeness_and_sends_one_completion_action(self):
        path = image_temp()
        payload = telegram_photo(message={"media_group_id": "album-1"})
        receipts = []
        with patch("modules.beacon.media_intake.IntakeStore", FakeStore):
            result, status = handle_telegram_media_intake(
                payload, environ=ENV,
                fetcher=lambda *_: (path, {"returned_mime_type": "image/jpeg"}),
                storage=FakeStorage(),
                receipt_sender=lambda chat, text: receipts.append((chat, text)) or {"success": True},
            )
        self.assertEqual(status, 201)
        self.assertEqual(result["album_state"], "awaiting_explicit_owner_completion")
        self.assertEqual(len(receipts), 1)
        self.assertIn("/beacon-complete ABC123", receipts[0][1])
        self.assertNotIn("album-1", receipts[0][1])

    def test_exact_bytes_under_another_source_are_retired_without_finalization(self):
        path = image_temp()
        evidence = _validate_streamed_image(path, "image/jpeg", {})
        FakeStore.existing = {
            **evidence,
            "binary_asset_id": "BEACON-BINARY-EXISTING",
            "storage_path": "telegram/existing.jpg",
            "thumbnail_storage_path": "telegram-thumbnails/existing.jpg",
            "thumbnail_sha256": "f" * 64,
        }
        storage = FakeStorage()
        original = Path(path).read_bytes()
        thumbnail = _thumbnail_bytes(path)
        storage.objects["telegram/existing.jpg"] = (original, "image/jpeg")
        storage.objects["telegram-thumbnails/existing.jpg"] = (thumbnail, "image/jpeg")
        FakeStore.existing["thumbnail_sha256"] = __import__("hashlib").sha256(thumbnail).hexdigest()
        payload = telegram_photo(message={
            "photo": [{
                "file_id": "another-file",
                "file_unique_id": "another-unique",
                "file_size": evidence["byte_size"],
                "width": evidence["width"],
                "height": evidence["height"],
            }],
        })
        with patch("modules.beacon.media_intake.IntakeStore", FakeStore):
            result, status = handle_telegram_media_intake(
                payload, environ=ENV,
                fetcher=lambda *_: (path, {"returned_mime_type": "image/jpeg"}),
                storage=storage,
            )
        self.assertEqual(status, 409)
        self.assertEqual(result["status"], "retired_or_previously_ingested_photo_withheld")
        self.assertEqual(storage.put_count, 0)

    def test_existing_binary_requires_private_storage_hash_readback(self):
        path = image_temp()
        evidence = _validate_streamed_image(path, "image/jpeg", {})
        thumbnail = _thumbnail_bytes(path)
        FakeStore.existing = {
            **evidence,
            "binary_asset_id": "BEACON-BINARY-EXISTING",
            "storage_path": "telegram/existing.jpg",
            "thumbnail_storage_path": "telegram-thumbnails/existing.jpg",
            "thumbnail_sha256": __import__("hashlib").sha256(thumbnail).hexdigest(),
        }
        storage = FakeStorage()
        storage.objects["telegram/existing.jpg"] = (b"not-the-canonical-bytes", "image/jpeg")
        storage.objects["telegram-thumbnails/existing.jpg"] = (thumbnail, "image/jpeg")
        with patch("modules.beacon.media_intake.IntakeStore", FakeStore):
            result, status = handle_telegram_media_intake(
                telegram_photo(),
                environ=ENV,
                fetcher=lambda *_: (path, {"returned_mime_type": "image/jpeg"}),
                storage=storage,
            )
        self.assertEqual(status, 409)
        self.assertEqual(result["status"], "retired_or_previously_ingested_photo_withheld")

    def test_storage_provider_failure_is_sanitized(self):
        path = image_temp()
        with patch("modules.beacon.media_intake.IntakeStore", FakeStore):
            result, status = handle_telegram_media_intake(
                telegram_photo(),
                environ=ENV,
                fetcher=lambda *_: (path, {"returned_mime_type": "image/jpeg"}),
                storage=FakeStorage(fail_put_at=1),
            )
        self.assertEqual(status, 502)
        self.assertEqual(
            result["failure_detail"],
            {"classification": "private_storage_upload_failed"},
        )
        self.assertNotIn("simulated_storage_failure", str(result))

    def test_video_remains_unsupported_before_fetch(self):
        payload = telegram_photo(message={
            "photo": [],
            "video": {
                "file_id": "video-1", "file_unique_id": "video-u1",
                "mime_type": "video/mp4", "file_name": "clip.mp4",
            },
        })
        receipts = []
        result, status = handle_telegram_media_intake(
            payload,
            environ=ENV,
            receipt_sender=lambda chat, text: receipts.append((chat, text)) or {"success": True},
        )
        self.assertEqual((status, result["status"]), (415, "video_intake_requires_bounded_resumable_phase"))
        self.assertTrue(result["receipt_sent"])
        self.assertIn("no file was downloaded", receipts[0][1])

    def test_mime_spoof_truncation_and_dimension_bounds_fail_closed(self):
        jpeg = image_temp()
        with self.assertRaises(IntakeFailure) as mismatch:
            _validate_streamed_image(jpeg, "image/png", {"returned_mime_type": "image/jpeg"})
        self.assertEqual(mismatch.exception.status, "telegram_declared_mime_mismatch")
        Path(jpeg).unlink(missing_ok=True)

        truncated = tempfile.NamedTemporaryFile(delete=False)
        truncated.write(b"\xff\xd8\xffbroken")
        truncated.close()
        with self.assertRaises(IntakeFailure) as malformed:
            _validate_streamed_image(truncated.name, "image/jpeg", {})
        self.assertEqual(malformed.exception.status, "telegram_media_malformed_or_truncated")
        Path(truncated.name).unlink(missing_ok=True)

        huge_dimensions = image_temp(size=(12001, 1))
        with self.assertRaises(IntakeFailure) as dimensions:
            _validate_streamed_image(huge_dimensions, "image/jpeg", {})
        self.assertEqual(dimensions.exception.status, "telegram_media_dimensions_out_of_bounds")
        Path(huge_dimensions).unlink(missing_ok=True)

    def test_oversized_file_fails_before_decoding(self):
        handle = tempfile.NamedTemporaryFile(delete=False)
        handle.seek(MAX_IMAGE_BYTES)
        handle.write(b"x")
        handle.close()
        with self.assertRaises(IntakeFailure) as oversized:
            _validate_streamed_image(handle.name, "image/jpeg", {})
        self.assertEqual(oversized.exception.status, "telegram_media_oversized")
        Path(handle.name).unlink(missing_ok=True)

    def test_stream_download_enforces_actual_bytes_without_content_length(self):
        metadata = FakeHttpResponse(b'{"ok":true,"result":{"file_path":"photos/a.jpg"}}')
        image_path = image_temp()
        body = Path(image_path).read_bytes()
        Path(image_path).unlink(missing_ok=True)
        download = FakeHttpResponse(body, {"Content-Type": "image/jpeg"})
        with patch(
            "modules.beacon.media_intake.urllib_request.urlopen",
            side_effect=[metadata, download],
        ):
            path, evidence = _download_telegram_file(
                {"file_id": "file-1"}, ENV
            )
        self.assertEqual(evidence["byte_size"], len(body))
        self.assertEqual(Path(path).read_bytes(), body)
        Path(path).unlink(missing_ok=True)

    def test_content_length_cannot_override_actual_byte_limit_or_truncation(self):
        metadata = FakeHttpResponse(b'{"ok":true,"result":{"file_path":"photos/a.jpg"}}')
        oversized = FakeHttpResponse(
            b"x" * (MAX_IMAGE_BYTES + 1),
            {"Content-Type": "image/jpeg", "Content-Length": "10"},
        )
        with patch(
            "modules.beacon.media_intake.urllib_request.urlopen",
            side_effect=[metadata, oversized],
        ):
            with self.assertRaises(IntakeFailure) as failure:
                _download_telegram_file({"file_id": "file-1"}, ENV)
        self.assertEqual(failure.exception.status, "telegram_media_oversized")

        metadata = FakeHttpResponse(b'{"ok":true,"result":{"file_path":"photos/a.jpg"}}')
        truncated = FakeHttpResponse(
            b"short",
            {"Content-Type": "image/jpeg", "Content-Length": "100"},
        )
        with patch(
            "modules.beacon.media_intake.urllib_request.urlopen",
            side_effect=[metadata, truncated],
        ):
            with self.assertRaises(IntakeFailure) as failure:
                _download_telegram_file({"file_id": "file-1"}, ENV)
        self.assertEqual(failure.exception.status, "telegram_media_truncated")

    def test_storage_failure_and_readback_mismatch_are_contained(self):
        for storage, expected in (
            (FakeStorage(fail_put_at=1), "private_storage_upload_failed"),
            (FakeStorage(readback_changed=True), "storage_readback_hash_mismatch"),
        ):
            with self.subTest(expected=expected):
                path = image_temp()
                with patch("modules.beacon.media_intake.IntakeStore", FakeStore):
                    result, status = handle_telegram_media_intake(
                        telegram_photo(), environ=ENV,
                        fetcher=lambda *_args, path=path: (path, {"returned_mime_type": "image/jpeg"}),
                        storage=storage,
                    )
                self.assertGreaterEqual(status, 400)
                self.assertEqual(result["status"], expected)

    def test_metadata_failure_runs_bounded_cleanup_or_exposes_reconciliation(self):
        FakeStore.finalize_status = 500
        for cleanup in (True, False):
            path = image_temp()
            storage = FakeStorage(cleanup=cleanup)
            with patch("modules.beacon.media_intake.IntakeStore", FakeStore):
                result, status = handle_telegram_media_intake(
                    telegram_photo(), environ=ENV,
                    fetcher=lambda *_args, path=path: (path, {"returned_mime_type": "image/jpeg"}),
                    storage=storage,
                )
            self.assertEqual(status, 500)
            self.assertEqual(result["reconciliation_required"], not cleanup)

    def test_perceptually_similar_media_are_not_exact_duplicates(self):
        first = image_temp()
        second_handle = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
        second_handle.close()
        Image.new("RGB", (640, 480), (120, 78, 42)).save(second_handle.name, "JPEG")
        first_evidence = _validate_streamed_image(first, "image/jpeg", {})
        second_evidence = _validate_streamed_image(second_handle.name, "image/jpeg", {})
        self.assertNotEqual(first_evidence["content_sha256"], second_evidence["content_sha256"])
        self.assertTrue(_thumbnail_bytes(first))
        Path(first).unlink(missing_ok=True)
        Path(second_handle.name).unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
