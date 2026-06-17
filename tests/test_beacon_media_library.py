import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from modules.beacon.media_library import (
    APPROVED_MEDIA_BUCKET,
    AUTHORITY_FLAGS,
    RAW_INTAKE_BUCKET,
    _asset_counts,
    beacon_media_storage_policy,
    record_beacon_media_asset_event,
    register_beacon_media_asset,
    upload_beacon_media_asset,
)


class BeaconMediaLibraryTests(unittest.TestCase):
    def test_storage_policy_requires_supabase_url_and_service_role_for_upload(self):
        policy = beacon_media_storage_policy({})

        self.assertEqual(policy["storage_backend"], "supabase_storage")
        self.assertEqual(policy["metadata_backend"], "postgres")
        self.assertEqual(policy["raw_intake_bucket"], RAW_INTAKE_BUCKET)
        self.assertEqual(policy["approved_media_bucket"], APPROVED_MEDIA_BUCKET)
        self.assertFalse(policy["farm_app_standard_upload_enabled"])
        self.assertFalse(policy["public_asset_use_enabled"])
        self.assertFalse(policy["automatic_posting_enabled"])
        self.assertIn("SUPABASE_SERVICE_ROLE_KEY", policy["required_envs_for_upload"])

        enabled = beacon_media_storage_policy({
            "SUPABASE_URL": "https://example.supabase.co",
            "SUPABASE_SERVICE_ROLE_KEY": "service-role",
        })
        self.assertTrue(enabled["farm_app_standard_upload_enabled"])

    def test_register_metadata_requires_database_and_has_no_public_authority(self):
        result, status_code = register_beacon_media_asset({
            "storage_bucket": "beacon-raw-intake",
            "storage_path": "2026/06/18/test.jpg",
            "original_filename": "test.jpg",
            "media_type": "image",
            "mime_type": "image/jpeg",
            "source": "farm_app_upload",
            "sale_stream_relevance": ["meat"],
            "subject_tags": ["pigs", "farm"],
            "public_use_approved": True,
            "approval_status": "needs_review",
        }, database_url="")

        self.assertEqual(status_code, 503)
        self.assertEqual(result["status"], "not_configured")
        self.assertFalse(result["posts_publicly"])
        self.assertFalse(result["calls_meta"])
        self.assertFalse(result["customer_public_output_enabled"])

    def test_event_approval_is_evidence_only(self):
        result, status_code = record_beacon_media_asset_event("BEACON-ASSET-TEST", {
            "event_type": "approved_public_use",
            "notes": "Good pig image for meat launch.",
            "subject_tags": ["pork", "freezer"],
        }, database_url="")

        self.assertEqual(status_code, 503)
        self.assertEqual(result["status"], "not_configured")
        for flag, expected in AUTHORITY_FLAGS.items():
            self.assertEqual(result[flag], expected)

    def test_counts_use_effective_approval_status_from_latest_event(self):
        counts = _asset_counts([
            {"approval_status": "needs_review", "effective_approval_status": "approved"},
            {"approval_status": "needs_review", "effective_approval_status": "rejected"},
            {"approval_status": "needs_review"},
        ])

        self.assertEqual(counts["total"], 3)
        self.assertEqual(counts["approved"], 1)
        self.assertEqual(counts["rejected"], 1)
        self.assertEqual(counts["needs_review"], 1)

    def test_upload_rejects_missing_file_and_large_file_before_storage_call(self):
        result, status_code = upload_beacon_media_asset(None, form={})
        self.assertEqual(status_code, 400)
        self.assertEqual(result["status"], "file_required")

        class Upload:
            filename = "large-video.mp4"
            mimetype = "video/mp4"

            def read(self):
                return b"x" * (6 * 1024 * 1024 + 1)

        result, status_code = upload_beacon_media_asset(Upload(), form={})
        self.assertEqual(status_code, 413)
        self.assertEqual(result["status"], "file_too_large_for_standard_upload")
        self.assertIn("add_tus_resumable_upload", result["next_gate"])

    def test_upload_uses_raw_intake_bucket_and_registers_metadata(self):
        class Upload:
            filename = "farm photo.jpg"
            mimetype = "image/jpeg"

            def read(self):
                return b"fake-image"

        def fake_uploader(bucket, storage_path, data, content_type, environ=None):
            self.assertEqual(bucket, RAW_INTAKE_BUCKET)
            self.assertIn("farm photo.jpg", storage_path)
            self.assertEqual(data, b"fake-image")
            self.assertEqual(content_type, "image/jpeg")
            return {"success": True, "status": "supabase_storage_upload_complete"}, 201

        with patch("modules.beacon.media_library.register_beacon_media_asset") as register:
            register.return_value = ({
                "success": True,
                "status": "beacon_media_asset_registered",
                "asset_id": "BEACON-ASSET-TEST",
                "asset": {},
            }, 201)

            result, status_code = upload_beacon_media_asset(
                Upload(),
                form={"uploader_label": "Charl"},
                uploader=fake_uploader,
            )

        self.assertEqual(status_code, 201)
        self.assertEqual(result["upload"]["status"], "supabase_storage_upload_complete")
        payload = register.call_args.kwargs["payload"] if "payload" in register.call_args.kwargs else register.call_args.args[0]
        self.assertEqual(payload["storage_bucket"], RAW_INTAKE_BUCKET)
        self.assertEqual(payload["media_type"], "image")
        self.assertEqual(payload["uploader_label"], "Charl")
        self.assertFalse(payload["public_use_approved"])

    def test_migration_contract_creates_append_only_metadata_and_events(self):
        migration = Path("supabase/migrations/202606180002_create_beacon_media_library.sql").read_text(encoding="utf-8")

        self.assertIn("create table if not exists public.beacon_media_assets", migration)
        self.assertIn("create table if not exists public.beacon_media_asset_events", migration)
        self.assertIn("posts_publicly = false", migration)
        self.assertIn("calls_meta = false", migration)
        self.assertIn("customer_public_output_enabled = false", migration)
        self.assertIn("before update on public.beacon_media_assets", migration)
        self.assertIn("before delete on public.beacon_media_assets", migration)
        self.assertIn("before update on public.beacon_media_asset_events", migration)
        self.assertIn("before delete on public.beacon_media_asset_events", migration)


if __name__ == "__main__":
    unittest.main()
