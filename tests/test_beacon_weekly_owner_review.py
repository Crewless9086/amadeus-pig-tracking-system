import unittest
from unittest.mock import patch

from modules.beacon.weekly_owner_review import (
    EXACT_CAPTION,
    MEDIA_SPEC,
    PACKET_ID,
    build_post_one_owner_review,
    load_post_one_thumbnail,
)


def eligible_asset(asset_id):
    return {
        "asset_id": asset_id,
        "title": asset_id,
        "media_type": "image",
        "mime_type": "image/jpeg",
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
        self.assertEqual(packet["draft_copy"], EXACT_CAPTION)
        self.assertIn("Waki’s", EXACT_CAPTION)
        self.assertNotIn("Wakiâ", EXACT_CAPTION)
        self.assertEqual(
            packet["media"]["exact_order"],
            [item["asset_id"] for item in MEDIA_SPEC],
        )
        self.assertEqual(
            [item["dimensions_display"] for item in packet["media"]["assets"]],
            ["4000 × 3000"] * 3,
        )
        self.assertTrue(packet["public_livestock_policy"]["allowed"])
        self.assertEqual(packet["public_livestock_policy"]["reasons"], [])
        self.assertTrue(all(value is False for value in packet["authority"].values()))

    def test_missing_or_untrusted_asset_withholds_packet(self):
        assets = [eligible_asset(item["asset_id"]) for item in MEDIA_SPEC]
        assets[1]["content_hash_provenance"] = "caller_supplied"
        packet = build_post_one_owner_review(assets)
        self.assertEqual(packet["review_status"], "withheld")
        self.assertEqual(packet["draft_copy"], "")
        self.assertIn("trusted_server_hash_required", " ".join(packet["blockers"]))

    @patch("modules.beacon.weekly_owner_review.load_supabase_asset_bytes")
    @patch("modules.beacon.weekly_owner_review.list_beacon_media_assets")
    def test_thumbnail_revalidates_bytes_dimensions_and_never_executes(
        self, list_assets, load_bytes
    ):
        asset = eligible_asset(MEDIA_SPEC[0]["asset_id"])
        list_assets.return_value = ({"assets": [asset]}, 200)
        load_bytes.return_value = ({
            "success": True,
            "data": b"jpeg",
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
