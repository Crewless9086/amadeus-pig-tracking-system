import unittest
from unittest.mock import patch

from modules.sales.sam_shared_context import build_sam_v3_context_packet
from modules.sales import sam_meat_runtime
from scripts.prepare_sam_v3_fake_beacon_source import (
    apply_fake_beacon_source_to_chatwoot,
    build_fake_beacon_source_payload,
    customer_test_message,
)
from tests.test_sam_meat_runtime import inbound_payload


class PrepareSamV3FakeBeaconSourceTests(unittest.TestCase):
    def test_payload_marks_fake_beacon_context_without_public_authority(self):
        payload = build_fake_beacon_source_payload()

        attrs = payload["custom_attributes"]
        self.assertEqual(attrs["source_campaign_id"], "BEACON-FAKE-MEAT-SOURCE-TEST")
        self.assertEqual(attrs["meat_source_campaign_id"], "BEACON-FAKE-MEAT-SOURCE-TEST")
        self.assertEqual(attrs["campaign_source"], "fake_beacon_facebook_test")
        self.assertEqual(attrs["sales_lane"], "meat_preorder")
        self.assertEqual(attrs["sam_v3_test_source"], "fake_beacon_facebook_context_no_public_post")
        self.assertEqual(attrs["sam_v3_test_reset"], "cleared_stale_meat_operational_attrs")
        self.assertEqual(attrs["meat_delivery_mode"], "")
        self.assertEqual(attrs["meat_product_type"], "")
        self.assertEqual(attrs["meat_cut_set"], "")
        self.assertIn("beacon_meat_launch", payload["labels"])
        self.assertIn("sam_v3_fake_source_test", payload["labels"])
        self.assertIn("Riversdale", customer_test_message())

    def test_sam_v3_context_uses_fake_source_attributes_without_campaign_record(self):
        fake_source = build_fake_beacon_source_payload()
        inbound = sam_meat_runtime.parse_chatwoot_inbound(inbound_payload(
            content=customer_test_message(),
            conversation={
                "id": 1919,
                "inbox": {"channel_type": "Channel::Whatsapp"},
                "labels": fake_source["labels"],
                "custom_attributes": fake_source["custom_attributes"],
            },
        ))

        packet = build_sam_v3_context_packet(inbound)

        self.assertTrue(packet["source_context"]["available"])
        self.assertEqual(packet["source_context"]["campaign_id"], "BEACON-FAKE-MEAT-SOURCE-TEST")
        self.assertEqual(packet["source_context"]["source"], "beacon_or_sales_campaign")
        self.assertEqual(packet["source_context"]["sales_lane"], "meat_preorder")
        self.assertIn("pork freezer", packet["source_context"]["post_text"])
        self.assertTrue(packet["context_quality"]["has_campaign_context"])

    def test_apply_payload_clears_stale_delivery_attribute(self):
        calls = []

        def fake_request(method, base_url, account_id, conversation_id, token, suffix="", body=None):
            calls.append({
                "method": method,
                "suffix": suffix,
                "body": body,
            })
            if method == "GET":
                return {
                    "status_code": 200,
                    "body": {
                        "custom_attributes": {
                            "meat_delivery_mode": "delivery",
                            "meat_product_type": "half_carcass",
                            "source_campaign_id": "OLD",
                        },
                        "labels": ["delivery", "meat_lead"],
                    },
                }
            return {"status_code": 200, "body": {}}

        import scripts.prepare_sam_v3_fake_beacon_source as helper
        original = helper._chatwoot_request
        helper._chatwoot_request = fake_request
        try:
            result = apply_fake_beacon_source_to_chatwoot(
                "1819",
                build_fake_beacon_source_payload(),
                base_url="https://app.chatwoot.com",
                account_id="147387",
                token="test-token",
            )
        finally:
            helper._chatwoot_request = original

        self.assertTrue(result["success"])
        attr_call = next(call for call in calls if call["suffix"] == "custom_attributes")
        attrs = attr_call["body"]["custom_attributes"]
        self.assertEqual(attrs["meat_delivery_mode"], "")
        self.assertEqual(attrs["meat_product_type"], "")
        self.assertEqual(attrs["source_campaign_id"], "BEACON-FAKE-MEAT-SOURCE-TEST")
        self.assertIn("delivery", result["labels"])

    @patch("modules.sales.sam_meat_runtime.get_active_sales_lead_by_conversation")
    @patch("modules.sales.sam_meat_runtime.get_sales_lead_preorder_contract")
    @patch("modules.sales.sam_meat_runtime.record_sam_meat_intake_lead")
    def test_cleared_fake_source_does_not_force_address_loop(self, mock_record, mock_contract, mock_active):
        mock_active.return_value = ({"success": False, "status": "not_found"}, 404)
        mock_record.return_value = ({
            "success": True,
            "status": "ok",
            "lead_id": "OSK-SALES-LEAD-FAKE-SOURCE",
            "contract": {},
        }, 201)
        mock_contract.return_value = ({
            "success": True,
            "contract": {"contract_status": "needs_owner_confirmation"},
        }, 200)
        fake_source = build_fake_beacon_source_payload()

        result, status_code = sam_meat_runtime.handle_sam_meat_chatwoot_inbound(
            inbound_payload(
                content=customer_test_message(),
                conversation={
                    "id": 1819,
                    "inbox": {"channel_type": "Channel::Whatsapp"},
                    "labels": fake_source["labels"],
                    "custom_attributes": fake_source["custom_attributes"],
                },
            ),
            environ={"SAM_MEAT_BACKEND_AUTOREPLY_ENABLED": "0"},
        )

        self.assertEqual(status_code, 200)
        self.assertNotEqual(result["facts"].get("delivery_or_collection"), "delivery")
        self.assertNotIn("For delivery, send the street address", result["sam_decision"]["reply_text"])


if __name__ == "__main__":
    unittest.main()
