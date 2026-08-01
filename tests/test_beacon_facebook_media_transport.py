import hashlib
import struct
import unittest
from datetime import datetime, timedelta, timezone
from urllib import error as urllib_error
from unittest.mock import patch

from modules.beacon.facebook_media_transport import (
    MAX_IMAGE_BYTES,
    load_supabase_asset_bytes,
    manual_composer_handoff,
    resolve_server_publication_assets,
    upload_unpublished_photo_binary,
    validate_facebook_image_asset,
    _RejectRedirects,
)
from modules.sales.beacon_campaign import _post_to_facebook_page_binary_images


def png(width=64, height=48):
    return (
        b"\x89PNG\r\n\x1a\n"
        + b"\x00\x00\x00\rIHDR"
        + struct.pack(">II", width, height)
        + b"\x08\x02\x00\x00\x00"
    )


def jpeg(width=64, height=48):
    return (
        b"\xff\xd8"
        + b"\xff\xc0"
        + struct.pack(">H", 17)
        + b"\x08"
        + struct.pack(">HH", height, width)
        + b"\x03\x01\x11\x00\x02\x11\x00\x03\x11\x00"
        + b"\xff\xd9"
    )


def asset(asset_id, data=None, mime="image/png"):
    data = data or png()
    return {
        "asset_id": asset_id,
        "media_type": "image",
        "mime_type": mime,
        "public_use_approved": True,
        "effective_public_use_approved": True,
        "content_sha256": hashlib.sha256(data).hexdigest(),
        "content_hash_provenance": "server_stream_and_storage_readback_verified",
        "projection_authority": "server_database_private_binary_v1",
        "file_size_bytes": len(data),
        "storage_bucket": "private",
        "storage_path": f"{asset_id}.png",
    }


def proof(item, data, mime="image/png", **changes):
    value = {
        "authority": "server_private_object_authenticated_readback_v1",
        "trusted_server_hash": hashlib.sha256(data).hexdigest(),
        "byte_count": len(data), "returned_mime": mime,
        "storage_object_identity": f"{item['storage_bucket']}/{item['storage_path']}",
        "storage_object_version": '"etag-v1"',
        "authenticated_readback_at": datetime.now(timezone.utc).isoformat(),
    }
    value.update(changes)
    return value


def params(assets):
    return {
        "publish_packet_id": "PACKET-1",
        "exact_text": "A responsible piglet-care story.",
        "post_kind": "multi_photo" if len(assets) > 1 else "photo",
        "selected_assets": assets,
    }


class FacebookImageValidationTests(unittest.TestCase):
    def test_exact_contained_failure_requires_server_readback_projection(self):
        data = jpeg(1280, 960) + b"x" * (418512 - len(jpeg(1280, 960)))
        item = asset("BEACON-ASSET-15EBF5E67DBFD12693", data, "image/jpeg")
        item["content_hash_provenance"] = ""
        result = validate_facebook_image_asset(
            item, data, "image/jpeg", proof(item, data, "image/jpeg")
        )
        self.assertFalse(result["allowed"])
        self.assertIn("trusted_server_hash_required", result["reasons"])

    def test_valid_exact_server_projection_accepts_readback(self):
        data = jpeg(1280, 960) + b"x" * (418512 - len(jpeg(1280, 960)))
        item = asset("BEACON-ASSET-15EBF5E67DBFD12693", data, "image/jpeg")
        result = validate_facebook_image_asset(
            item, data, "image/jpeg", proof(item, data, "image/jpeg")
        )
        self.assertTrue(result["allowed"], result)
        self.assertEqual(result["byte_count"], 418512)

    def test_client_supplied_trusted_hash_is_never_authority(self):
        data = png(); item = asset("A", data)
        item["trusted_server_hash"] = hashlib.sha256(data).hexdigest()
        result = validate_facebook_image_asset(item, data, "image/png")
        self.assertFalse(result["allowed"])
        self.assertIn("authenticated_private_readback_required", result["reasons"])

    def test_byte_mime_and_object_version_mismatch_fail_closed(self):
        data = png(); item = asset("A", data)
        cases = (
            (proof(item, data, byte_count=len(data) + 1), "image_byte_count_mismatch"),
            (proof(item, data, returned_mime="image/jpeg"), "readback_mime_mismatch"),
            (proof(item, data, storage_object_version=""), "storage_object_version_required"),
            (proof(item, data, storage_object_identity="other/object"), "storage_object_identity_mismatch"),
        )
        for readback, reason in cases:
            with self.subTest(reason=reason):
                result = validate_facebook_image_asset(item, data, "image/png", readback)
                self.assertIn(reason, result["reasons"])

    def test_stale_readback_fails_closed(self):
        data = png(); item = asset("A", data)
        stale = proof(item, data, authenticated_readback_at=(datetime.now(timezone.utc)-timedelta(minutes=6)).isoformat())
        result = validate_facebook_image_asset(item, data, "image/png", stale)
        self.assertIn("authenticated_readback_stale", result["reasons"])

    def test_changed_media_after_approval_fails_closed(self):
        approved = png(); changed = png() + b"changed"; item = asset("A", approved)
        result = validate_facebook_image_asset(item, changed, "image/png", proof(item, changed))
        self.assertIn("image_hash_mismatch", result["reasons"])


class ServerProjectionTests(unittest.TestCase):
    def _connect(self, rows):
        class Cursor:
            def __enter__(self): return self
            def __exit__(self, *_args): return False
            def execute(self, *_args): pass
            def fetchall(self): return rows
        class Connection:
            def __enter__(self): return self
            def __exit__(self, *_args): return False
            def cursor(self): return Cursor()
        return Connection()

    def test_valid_server_projection_binds_binary_and_current_approvals(self):
        digest = "a" * 64
        row = ("A", "BINARY-A", "private", "object.jpg", digest, digest,
               418512, "image/jpeg", "image-v1", "LIB-1", "library_accepted",
               "PUB-1", "public_use_approved")
        with patch("psycopg.connect", return_value=self._connect([row])):
            result, status = resolve_server_publication_assets(["A"], "postgres://db")
        self.assertEqual(status, 200)
        self.assertEqual(result["assets"][0]["binary_asset_id"], "BINARY-A")
        self.assertEqual(result["assets"][0]["file_size_bytes"], 418512)

    @patch.dict("os.environ", {"DATABASE_URL": "postgres://configured"})
    def test_server_projection_uses_configured_database_when_argument_omitted(self):
        digest = "a" * 64
        row = ("A", "BINARY-A", "private", "object.jpg", digest, digest,
               418512, "image/jpeg", "image-v1", "LIB-1", "library_accepted",
               "PUB-1", "public_use_approved")
        with patch("psycopg.connect", return_value=self._connect([row])) as connect:
            result, status = resolve_server_publication_assets(["A"], None)
        self.assertEqual(status, 200)
        self.assertTrue(result["success"])
        self.assertEqual(connect.call_args.args[0], "postgres://configured")

    def test_revoked_or_changed_server_projection_fails_closed(self):
        digest = "a" * 64
        revoked = ("A", "BINARY-A", "private", "object.jpg", digest, digest,
                   418512, "image/jpeg", "image-v1", "LIB-1", "library_accepted",
                   "REVOKE-1", "public_use_revoked")
        with patch("psycopg.connect", return_value=self._connect([revoked])):
            result, status = resolve_server_publication_assets(["A"], "postgres://db")
        self.assertEqual(status, 409)
        self.assertEqual(result["status"], "server_media_approval_or_readback_missing")

    def test_multiple_binary_lineages_for_one_asset_fail_closed(self):
        digest = "a" * 64
        first = ("A", "BINARY-A", "private", "one.jpg", digest, digest,
                 418512, "image/jpeg", "image-v1", "LIB-1", "library_accepted",
                 "PUB-1", "public_use_approved")
        second = ("A", "BINARY-B", "private", "two.jpg", digest, digest,
                  418512, "image/jpeg", "image-v1", "LIB-2", "library_accepted",
                  "PUB-2", "public_use_approved")
        with patch("psycopg.connect", return_value=self._connect([first, second])):
            result, status = resolve_server_publication_assets(["A"], "postgres://db")
        self.assertEqual(status, 409)
        self.assertEqual(result["status"], "canonical_media_identity_mismatch")

    def test_invalid_bytes_are_rejected(self):
        data = b"<html>not an image</html>"
        item = asset("A", data)
        result = validate_facebook_image_asset(item, data, "text/html", proof(item, data, "text/html"))
        self.assertFalse(result["allowed"])
        self.assertIn("image_format_not_jpeg_or_png", result["reasons"])

    def test_mime_mismatch_is_rejected(self):
        data = png()
        item = asset("A", data, mime="image/jpeg")
        result = validate_facebook_image_asset(item, data, "image/png", proof(item, data))
        self.assertFalse(result["allowed"])
        self.assertIn("declared_mime_mismatch", result["reasons"])

    def test_valid_png_retains_dimensions_and_format(self):
        data = png(800, 600)
        item = asset("A", data)
        result = validate_facebook_image_asset(item, data, "image/png", proof(item, data))
        self.assertTrue(result["allowed"])
        self.assertEqual((result["width"], result["height"]), (800, 600))
        self.assertEqual(result["image_format"], "png")

    def test_valid_jpeg_magic_and_dimensions_are_accepted(self):
        data = jpeg(640, 480)
        item = asset("J", data, mime="image/jpeg")
        result = validate_facebook_image_asset(item, data, "image/jpeg", proof(item, data, "image/jpeg"))
        self.assertTrue(result["allowed"], result)
        self.assertEqual(result["image_format"], "jpeg")
        self.assertEqual((result["width"], result["height"]), (640, 480))


class FacebookBinaryTransportTests(unittest.TestCase):
    def setUp(self):
        self.data = png()
        self.assets = [asset("A", self.data), asset("B", self.data)]
        self.stages = []

    def loader(self, _asset):
        return {
            "success": True,
            "status": "private_storage_image_loaded",
            "returned_mime": "image/png",
            "data": self.data,
            "readback_proof": proof(_asset, self.data),
        }, 200

    def record(self, stage):
        self.stages.append(stage)
        return True

    def test_inaccessible_storage_stops_before_meta(self):
        calls = []
        result, status = _post_to_facebook_page_binary_images(
            params(self.assets),
            {},
            storage_loader=lambda _asset: (
                {"success": False, "status": "private_storage_http_error"}, 404
            ),
            photo_uploader=lambda *_: calls.append(True),
            stage_recorder=self.record,
        )
        self.assertEqual(status, 422)
        self.assertEqual(calls, [])
        self.assertEqual(result["outcome"], "definite_failure_before_meta")

    def test_execution_rechecks_current_public_approval(self):
        calls = []
        revoked = dict(self.assets[0], public_use_approved=False,
                       effective_public_use_approved=False)
        result, status = _post_to_facebook_page_binary_images(
            params([revoked]),
            {},
            storage_loader=self.loader,
            photo_uploader=lambda *_: calls.append(True),
            stage_recorder=self.record,
        )
        self.assertEqual(status, 422)
        self.assertEqual(calls, [])
        self.assertIn(
            "asset_not_approved_for_public_use",
            result["asset_validations"][0]["reasons"],
        )

    def test_livestock_policy_is_rechecked_at_last_pre_upload_boundary(self):
        calls = []
        unsafe = params([self.assets[0]])
        unsafe.update({
            "campaign_lane": "live_stock_awareness",
            "objective": "qualified_livestock_enquiries",
            "exact_text": "Message us with your livestock requirements.",
        })
        result, status = _post_to_facebook_page_binary_images(
            unsafe,
            {},
            storage_loader=self.loader,
            photo_uploader=lambda *_: calls.append(True),
            stage_recorder=self.record,
        )
        self.assertEqual(status, 409)
        self.assertEqual(calls, [])
        self.assertEqual(
            result["status"],
            "owner_review_required_meta_livestock_commerce_risk",
        )

    def test_first_image_failure_retains_zero_media_ids(self):
        result, status = _post_to_facebook_page_binary_images(
            params(self.assets),
            {},
            storage_loader=self.loader,
            photo_uploader=lambda *_: (
                {"success": False, "status": "failed", "outcome": "definite_failure"},
                400,
            ),
            feed_creator=lambda *_: self.fail("feed must not run"),
            stage_recorder=self.record,
        )
        self.assertEqual(status, 400)
        self.assertEqual(result["uploaded_media_ids"], [])
        self.assertEqual(result["outcome"], "definitely_not_posted_no_media_accepted")

    def test_later_image_failure_retains_partial_upload(self):
        calls = []

        def upload(*_args):
            calls.append(True)
            if len(calls) == 1:
                return {"success": True, "id": "MEDIA-1"}, 200
            return {"success": False, "status": "failed"}, 400

        result, status = _post_to_facebook_page_binary_images(
            params(self.assets),
            {},
            storage_loader=self.loader,
            photo_uploader=upload,
            feed_creator=lambda *_: self.fail("feed must not run"),
            stage_recorder=self.record,
        )
        self.assertEqual(status, 400)
        self.assertEqual(result["uploaded_media_ids"], ["MEDIA-1"])
        self.assertEqual(result["outcome"], "partial_upload_final_post_not_created")
        self.assertTrue(result["owner_reconciliation_required"])

    def test_final_feed_failure_retains_all_media_ids(self):
        ids = iter(("MEDIA-1", "MEDIA-2"))
        result, status = _post_to_facebook_page_binary_images(
            params(self.assets),
            {},
            storage_loader=self.loader,
            photo_uploader=lambda *_: (
                {"success": True, "id": next(ids)}, 200
            ),
            feed_creator=lambda *_: (
                {"success": False, "status": "feed_failed"}, 400
            ),
            stage_recorder=self.record,
        )
        self.assertEqual(status, 400)
        self.assertEqual(result["uploaded_media_ids"], ["MEDIA-1", "MEDIA-2"])
        self.assertEqual(result["outcome"], "media_uploaded_final_post_not_published")

    def test_timeout_is_ambiguous_and_never_retried(self):
        calls = []

        def upload(*_args):
            calls.append(True)
            return {
                "success": False,
                "status": "upload_failed",
                "outcome": "ambiguous",
            }, 502

        result, _ = _post_to_facebook_page_binary_images(
            params(self.assets),
            {},
            storage_loader=self.loader,
            photo_uploader=upload,
            stage_recorder=self.record,
        )
        self.assertEqual(len(calls), 1)
        self.assertEqual(result["outcome"], "ambiguous")
        self.assertFalse(result["automatic_retry_allowed"])

    def test_exact_success_preserves_order_and_stage_evidence(self):
        ids = iter(("MEDIA-A", "MEDIA-B"))
        result, status = _post_to_facebook_page_binary_images(
            params(self.assets),
            {},
            storage_loader=self.loader,
            photo_uploader=lambda *_: (
                {"success": True, "id": next(ids)}, 200
            ),
            feed_creator=lambda caption, media_ids: (
                {
                    "success": True,
                    "id": "POST-1",
                    "caption_seen": caption,
                    "media_seen": media_ids,
                },
                200,
            ),
            stage_recorder=self.record,
        )
        self.assertEqual(status, 200)
        self.assertEqual(result["facebook_post_id"], "POST-1")
        self.assertEqual(result["uploaded_media_ids"], ["MEDIA-A", "MEDIA-B"])
        self.assertEqual(
            [stage["transport_stage"] for stage in self.stages],
            [
                "validation_complete",
                "image_upload_result",
                "image_upload_result",
                "final_feed_result",
            ],
        )
        self.assertEqual(self.stages[0]["asset_order"], ["A", "B"])

    def test_manual_handoff_retains_caption_and_order_without_credentials(self):
        handoff = manual_composer_handoff(
            params(self.assets), [{
                "asset_id": "A",
                "allowed": True,
                "content_sha256": "private-integrity-value",
                "storage_path": "private/path.png",
            }], "test"
        )
        self.assertEqual(handoff["asset_order"], ["A", "B"])
        self.assertEqual(handoff["caption"], params(self.assets)["exact_text"])
        self.assertFalse(handoff["signed_urls_exposed"])
        self.assertFalse(handoff["calls_meta_now"])
        self.assertFalse(handoff["automatic_attempt_reusable"])
        self.assertTrue(handoff["requires_new_manual_composer_session"])
        serialized = str(handoff)
        self.assertNotIn("content_sha256", serialized)
        self.assertNotIn("storage_path", serialized)

    def test_multipart_uses_source_and_authorization_header_not_body_token(self):
        captured = {}

        class Response:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return b'{"id":"MEDIA-1"}'

        def requester(req, timeout):
            captured["request"] = req
            captured["timeout"] = timeout
            return Response()

        result, status = upload_unpublished_photo_binary(
            "PAGE", "SECRET", "v23.0", self.assets[0], self.data,
            "image/png", requester=requester
        )
        self.assertEqual(status, 200)
        self.assertEqual(result["id"], "MEDIA-1")
        self.assertIn(b'name="source"', captured["request"].data)
        self.assertNotIn(b"SECRET", captured["request"].data)
        self.assertEqual(
            captured["request"].headers["Authorization"], "Bearer SECRET"
        )
        self.assertEqual(
            captured["request"].full_url,
            "https://graph.facebook.com/v23.0/PAGE/photos",
        )
        self.assertNotIn("SECRET", captured["request"].full_url)

    def test_storage_read_stops_on_oversized_content_length(self):
        class Response:
            status = 200
            url = "https://storage.invalid/storage/v1/object/authenticated/b/a"
            headers = {
                "Content-Length": str(MAX_IMAGE_BYTES + 1),
                "Content-Type": "image/png",
                "ETag": '"v1"',
            }

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self, _limit):
                self.fail("oversized declared response must not be read")

        response = Response()
        response.fail = self.fail
        result, status = load_supabase_asset_bytes(
            {"storage_bucket": "b", "storage_path": "a"},
            environ={
                "SUPABASE_URL": "https://storage.invalid",
                "SUPABASE_SERVICE_ROLE_KEY": "secret",
            },
            opener=lambda *_args, **_kwargs: response,
        )
        self.assertEqual(status, 413)
        self.assertEqual(result["status"], "image_size_limit_exceeded")

    def test_authenticated_storage_readback_computes_trust_and_object_version(self):
        data = png()
        class Response:
            status = 200
            url = "https://storage.invalid/storage/v1/object/authenticated/private/A.png"
            headers = {"Content-Length": str(len(data)), "Content-Type": "image/png", "ETag": '"object-v7"'}
            def __enter__(self): return self
            def __exit__(self, *_args): return False
            def read(self, _limit): return data
        item = asset("A", data)
        result, status = load_supabase_asset_bytes(
            item, environ={"SUPABASE_URL": "https://storage.invalid", "SUPABASE_SERVICE_ROLE_KEY": "secret"},
            opener=lambda *_args, **_kwargs: Response())
        self.assertEqual(status, 200)
        self.assertEqual(result["readback_proof"]["trusted_server_hash"], hashlib.sha256(data).hexdigest())
        self.assertEqual(result["readback_proof"]["storage_object_version"], '"object-v7"')

    def test_redirected_private_readback_cannot_mint_trusted_hash(self):
        data = png()
        class Response:
            status = 200
            url = "https://attacker.invalid/object"
            headers = {"Content-Type": "image/png", "ETag": '"v1"'}
            def __enter__(self): return self
            def __exit__(self, *_args): return False
            def read(self, _limit): return data
        result, status = load_supabase_asset_bytes(
            {"storage_bucket": "private", "storage_path": "A.png"},
            environ={"SUPABASE_URL": "https://storage.invalid",
                     "SUPABASE_SERVICE_ROLE_KEY": "secret"},
            opener=lambda *_args, **_kwargs: Response(),
        )
        self.assertEqual(status, 409)
        self.assertEqual(result["status"],
                         "private_storage_readback_redirect_or_status_rejected")
        self.assertNotIn("readback_proof", result)

    def test_private_readback_redirect_handler_never_forwards_request(self):
        request = object()
        self.assertIsNone(_RejectRedirects().redirect_request(
            request, None, 302, "Found", {}, "https://attacker.invalid/object"
        ))

    def test_private_readback_3xx_http_error_has_no_trust_proof(self):
        def redirect_rejected(request, **_kwargs):
            raise urllib_error.HTTPError(
                request.full_url, 302, "Found",
                {"Location": "https://attacker.invalid/object"}, None,
            )
        result, status = load_supabase_asset_bytes(
            {"storage_bucket": "private", "storage_path": "A.png"},
            environ={"SUPABASE_URL": "https://storage.invalid",
                     "SUPABASE_SERVICE_ROLE_KEY": "secret"},
            opener=redirect_rejected,
        )
        self.assertEqual(status, 302)
        self.assertEqual(result["status"], "private_storage_http_error")
        self.assertNotIn("readback_proof", result)

    def test_actual_byte_limit_wins_over_false_small_content_length(self):
        captured = {}

        class Response:
            status = 200
            url = "https://storage.invalid/storage/v1/object/authenticated/b/a"
            headers = {"Content-Length": "1", "Content-Type": "image/png", "ETag": '"v1"'}

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self, limit):
                captured["limit"] = limit
                return b"x" * limit

        result, status = load_supabase_asset_bytes(
            {"storage_bucket": "b", "storage_path": "a"},
            environ={
                "SUPABASE_URL": "https://storage.invalid",
                "SUPABASE_SERVICE_ROLE_KEY": "secret",
            },
            opener=lambda *_args, **_kwargs: Response(),
        )
        self.assertEqual(captured["limit"], MAX_IMAGE_BYTES + 1)
        self.assertEqual(status, 413)
        self.assertEqual(result["status"], "image_size_limit_exceeded")


if __name__ == "__main__":
    unittest.main()
