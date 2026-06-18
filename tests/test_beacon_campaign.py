import unittest

from modules.sales.beacon_campaign import (
    BEACON_CAMPAIGN_MODE,
    build_meat_launch_campaign_packet,
    build_meat_launch_campaign_selection,
    format_meat_launch_campaign_markdown,
    validate_meat_launch_campaign_packet,
)


class BeaconCampaignTests(unittest.TestCase):
    def test_packet_is_draft_only_and_has_no_external_authority(self):
        packet = build_meat_launch_campaign_packet()

        self.assertTrue(packet["success"])
        self.assertEqual(packet["mode"], BEACON_CAMPAIGN_MODE)
        self.assertEqual(packet["agent"], "Beacon")
        self.assertEqual(packet["next_gate"], "owner_reviews_campaign_before_any_public_or_customer_send")
        self.assertTrue(packet["authority"]["draft_only"])

        for name, value in packet["authority"].items():
            if name == "draft_only":
                continue
            self.assertFalse(value, name)

        self.assertIn("no_public_post", packet["forbidden_actions"])
        self.assertIn("no_customer_dm", packet["forbidden_actions"])
        self.assertIn("no_chatwoot_send", packet["forbidden_actions"])
        self.assertIn("no_order_create", packet["forbidden_actions"])
        self.assertIn("no_stock_reservation", packet["forbidden_actions"])

    def test_channel_drafts_cover_launch_surfaces(self):
        packet = build_meat_launch_campaign_packet()
        drafts = packet["channel_drafts"]
        channels = {draft["channel"] for draft in drafts}

        self.assertIn("WhatsApp status", channels)
        self.assertIn("WhatsApp channel or broadcast draft", channels)
        self.assertIn("Facebook", channels)
        self.assertIn("Instagram", channels)
        self.assertGreaterEqual(len(packet["story_updates"]), 4)
        self.assertGreaterEqual(len(packet["campaign_angles"]), 4)

    def test_every_public_draft_is_limited_preorder_and_safe(self):
        packet = build_meat_launch_campaign_packet()
        validation = validate_meat_launch_campaign_packet(packet)

        self.assertTrue(validation["success"], validation)
        self.assertEqual(validation["missing_preorder_signal"], [])
        self.assertEqual(validation["missing_limited_signal"], [])
        self.assertEqual(validation["unsafe_promise_drafts"], [])
        self.assertGreaterEqual(validation["checked_draft_count"], 10)

    def test_packet_can_be_customized_without_changing_authority(self):
        packet = build_meat_launch_campaign_packet({
            "farm_name": "Amadeus Farm",
            "area": "Riversdale",
            "product_focus": "half carcass Set A",
        })

        self.assertEqual(packet["campaign"]["area"], "Riversdale")
        self.assertIn("half carcass Set A", packet["campaign"]["product_focus"])
        self.assertFalse(packet["authority"]["posts_publicly"])
        self.assertFalse(packet["authority"]["calls_chatwoot"])
        self.assertTrue(packet["validation"]["success"])

    def test_markdown_packet_keeps_authority_boundary_visible(self):
        packet = build_meat_launch_campaign_packet()
        markdown = format_meat_launch_campaign_markdown(packet)

        self.assertIn("# Meat Launch Campaign Packet", markdown)
        self.assertIn("This packet is draft-only.", markdown)
        self.assertIn("## Channel Drafts", markdown)
        self.assertIn("## Authority Boundary", markdown)
        self.assertIn("`posts_publicly`: `false`", markdown)
        self.assertIn("`creates_order`: `false`", markdown)
        self.assertIn("`changes_stock`: `false`", markdown)
        self.assertIn("owner_reviews_campaign_before_any_public_or_customer_send", markdown)

    def test_campaign_selection_pairs_approved_media_without_posting_authority(self):
        selection = build_meat_launch_campaign_selection(approved_assets=[
            {
                "asset_id": "BEACON-ASSET-APPROVED",
                "title": "Set A freezer pack photo",
                "media_type": "image",
                "subject_tags": ["set a", "freezer", "pork"],
                "sale_stream_relevance": ["meat"],
                "quality_score": 85,
                "privacy_risk": "low",
                "effective_approval_status": "approved",
                "effective_public_use_approved": True,
                "storage_bucket": "beacon-raw-intake",
                "storage_path": "2026/06/18/photo.jpg",
            },
            {
                "asset_id": "BEACON-ASSET-PENDING",
                "title": "Unreviewed photo",
                "media_type": "image",
                "effective_approval_status": "needs_review",
            },
        ])

        self.assertTrue(selection["success"])
        self.assertEqual(selection["mode"], "beacon_meat_launch_campaign_media_selection_review_only")
        self.assertEqual(selection["approved_media_count"], 1)
        self.assertEqual(selection["ranked_media_assets"][0]["asset_id"], "BEACON-ASSET-APPROVED")
        self.assertGreaterEqual(len(selection["channel_draft_pairings"]), 6)
        self.assertTrue(selection["channel_draft_pairings"][0]["requires_owner_final_selection"])
        self.assertFalse(selection["authority"]["posts_publicly"])
        self.assertFalse(selection["authority"]["calls_meta"])
        self.assertEqual(selection["next_gate"], "owner_selects_media_and_campaign_draft_before_any_public_post")


if __name__ == "__main__":
    unittest.main()
