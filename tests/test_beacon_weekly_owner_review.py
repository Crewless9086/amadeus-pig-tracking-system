import unittest
from unittest.mock import patch

from modules.beacon.weekly_owner_review import (
    EXPECTED_CANONICAL_SHA256,
    EXACT_CAPTION,
    MEDIA_SPEC,
    PACKET_ID,
    SUPERSEDED_CANONICAL_SHA256,
    SUPERSEDED_PACKET_ID,
    build_post_one_owner_review,
    historical_post_one_packets,
    load_post_one_thumbnail,
)


def eligible_asset(asset_id):
    expected = next(item for item in MEDIA_SPEC if item["asset_id"] == asset_id)
    return {
        "asset_id": asset_id,
        "media_type": "image",
        "mime_type": "image/jpeg",
        "file_size_bytes": expected["file_size_bytes"],
        "created_at": expected["upload_timestamp"],
        "effective_approval_status": "approved",
        "effective_public_use_approved": True,
        "content_hash_provenance": "server_computed_on_upload",
        "content_sha256": "a" * 64,
    }


class BeaconWeeklyOwnerReviewTests(unittest.TestCase):
    def test_exact_packet_copy_order_dimensions_policy_and_authority(self):
        packet = build_post_one_owner_review(
            [eligible_asset(item["asset_id"]) for item in MEDIA_SPEC]
        )
        self.assertEqual(packet["packet_id"], PACKET_ID)
        self.assertEqual(
            packet["review_status"], "awaiting_exact_owner_review"
        )
        self.assertEqual(packet["caption"], EXACT_CAPTION)
        self.assertIn("Ms. Piggy", EXACT_CAPTION)
        self.assertNotIn("Waki", EXACT_CAPTION)
        self.assertEqual(
            packet["caption_sha256"],
            "27fe1763541ba365134ae82ef6414c87fff7bd744a46af71dd9c988889e2e75b",
        )
        self.assertEqual(packet["canonical_sha256"], EXPECTED_CANONICAL_SHA256)
        self.assertEqual(
            packet["media"]["exact_order"],
            [item["asset_id"] for item in MEDIA_SPEC],
        )
        self.assertEqual(
            [item["dimensions"] for item in packet["media"]["assets"]],
            ["4000 × 3000"] * 3,
        )
        self.assertEqual(
            packet["album_story"], "Ms. Piggy and her litter – July 2026"
        )
        self.assertEqual(packet["confirmed_publication_count"], 0)
        self.assertEqual(packet["prior_confirmed_use"], "none_evidenced")
        self.assertEqual(packet["scheduled_time"], "owner_selection_required")
        self.assertTrue(packet["public_livestock_policy"]["allowed"])
        self.assertEqual(packet["public_livestock_policy"]["reasons"], [])
        self.assertTrue(all(value is False for value in packet["authority"].values()))

    def test_missing_or_untrusted_asset_withholds_packet(self):
        assets = [eligible_asset(item["asset_id"]) for item in MEDIA_SPEC]
        assets[1]["content_hash_provenance"] = "caller_supplied"
        packet = build_post_one_owner_review(assets)
        self.assertEqual(packet["review_status"], "withheld")
        self.assertEqual(packet["caption"], "")
        self.assertIn("trusted_server_hash_required", " ".join(packet["blockers"]))

    def test_prior_packet_is_immutable_superseded_history_not_current(self):
        first = historical_post_one_packets()
        first[0]["status"] = "changed_by_caller"
        second = historical_post_one_packets()
        self.assertEqual(second[0]["packet_id"], SUPERSEDED_PACKET_ID)
        self.assertEqual(
            second[0]["canonical_sha256"], SUPERSEDED_CANONICAL_SHA256
        )
        self.assertEqual(second[0]["status"], "owner_superseded")
        self.assertFalse(second[0]["current_reviewable"])
        self.assertEqual(second[0]["superseded_by"], PACKET_ID)
        self.assertFalse(second[0]["publish"])
        self.assertFalse(second[0]["Meta_call"])

    def test_capture_evidence_is_approximate_and_not_upload_date(self):
        packet = build_post_one_owner_review(
            [eligible_asset(item["asset_id"]) for item in MEDIA_SPEC]
        )
        for item in packet["media"]["assets"]:
            self.assertEqual(
                item["capture_date_status"],
                "approximate_exif_datetime_timezone_unknown",
            )
            self.assertNotEqual(item["capture_date"], item["upload_timestamp"])

    @patch("modules.beacon.weekly_owner_review.load_supabase_asset_bytes")
    @patch("modules.beacon.weekly_owner_review.list_beacon_media_assets")
    def test_thumbnail_revalidates_bytes_dimensions_and_never_executes(
        self, list_assets, load_bytes
    ):
        asset = eligible_asset(MEDIA_SPEC[0]["asset_id"])
        list_assets.return_value = ({"assets": [asset]}, 200)
        load_bytes.return_value = ({
            "success": True,
            "data": b"x" * MEDIA_SPEC[0]["file_size_bytes"],
            "returned_mime": "image/jpeg",
        }, 200)
        with patch(
            "modules.beacon.weekly_owner_review.validate_facebook_image_asset",
            return_value={
                "allowed": True,
                "width": 4000,
                "height": 3000,
                "returned_mime": "image/jpeg",
            },
        ):
            result, status = load_post_one_thumbnail(asset["asset_id"])
        self.assertEqual(status, 200)
        self.assertFalse(result["posts_publicly"])
        self.assertFalse(result["calls_meta"])
        self.assertFalse(result["writes_performed"])


if __name__ == "__main__":
    unittest.main()
