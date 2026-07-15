import unittest
from unittest.mock import patch

from modules.sales.meat_ops import build_meat_payment_gate
from modules.sales.meat_template_pack import meat_whatsapp_template_pack
from modules.sales.beacon_campaign import build_beacon_facebook_image_launch_packet


class MeatLaunchReadinessTests(unittest.TestCase):
    def test_template_pack_reports_missing_and_configured_envs(self):
        result = meat_whatsapp_template_pack({
            "MEAT_SALES_QUOTE_READY_TEMPLATE_NAME": "amadeus_meat_quote_ready",
            "MEAT_SALES_QUOTE_READY_TEMPLATE_LANGUAGE": "en",
        })

        self.assertTrue(result["success"])
        self.assertEqual(result["configured_count"], 1)
        self.assertEqual(result["required_count"], 5)
        self.assertFalse(result["all_configured"])
        self.assertIn("MEAT_SALES_DEPOSIT_FOLLOWUP_TEMPLATE_NAME", result["missing_envs"])
        self.assertEqual(result["templates"][0]["configured_name"], "amadeus_meat_quote_ready")

    def test_payment_gate_keeps_pop_separate_from_bank_confirmation(self):
        reservations = [{
            "reservation_id": "RES-1",
            "pig_id": "PIG-1",
            "status": "full_carcass_committed",
            "effective_status": "full_carcass_committed",
            "carcass_side": "full",
        }]
        deposits = [{
            "reservation_id": "RES-1",
            "event_type": "pop_received_unverified",
            "payment_reference": "707109",
            "created_at": "2026-06-19T07:00:00+00:00",
        }]

        gate = build_meat_payment_gate(reservations, deposits)

        self.assertEqual(gate["state"], "pop_received_unverified")
        self.assertTrue(gate["sam_may_claim_pop_received"])
        self.assertFalse(gate["sam_may_claim_money_received"])
        self.assertFalse(gate["unlocks_slaughter_or_delivery"])

    def test_payment_gate_unlocks_only_after_bank_confirmation(self):
        reservations = [{
            "reservation_id": "RES-1",
            "pig_id": "PIG-1",
            "status": "full_carcass_committed",
            "effective_status": "full_carcass_committed",
            "carcass_side": "full",
        }]
        deposits = [{
            "reservation_id": "RES-1",
            "event_type": "deposit_confirmed_in_bank",
            "payment_reference": "707109",
            "created_at": "2026-06-19T08:00:00+00:00",
        }]

        gate = build_meat_payment_gate(reservations, deposits)

        self.assertEqual(gate["state"], "deposit_confirmed_in_bank")
        self.assertTrue(gate["sam_may_claim_money_received"])
        self.assertTrue(gate["unlocks_slaughter_or_delivery"])

    @patch.dict("os.environ", {"SAM_MEAT_PUBLIC_OFFER_ENABLED": "1"})
    def test_beacon_facebook_image_launch_packet_requires_approved_image(self):
        packet = build_beacon_facebook_image_launch_packet(
            {"pilot_cap": "2"},
            approved_assets=[{
                "asset_id": "BEACON-ASSET-APPROVED",
                "effective_approval_status": "approved",
                "effective_public_use_approved": True,
                "public_use_approved": True,
                "media_type": "image",
                "quality_score": 80,
                "subject_tags": ["pork", "freezer"],
                "sale_stream_relevance": ["meat"],
                "privacy_risk": "low",
                "storage_bucket": "beacon-approved-media",
                "storage_path": "pilot/photo.jpg",
            }],
        )

        self.assertTrue(packet["success"])
        self.assertTrue(packet["ready_for_owner_post_approval"])
        self.assertEqual(packet["execution_payload"]["asset_id"], "BEACON-ASSET-APPROVED")
        self.assertFalse(packet["posts_publicly_now"])
        self.assertFalse(packet["calls_meta_now"])


if __name__ == "__main__":
    unittest.main()
