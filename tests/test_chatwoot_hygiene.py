import unittest

from modules.sales.chatwoot_hygiene import (
    build_sam_meat_chatwoot_hygiene_payload,
    sync_sam_meat_chatwoot_hygiene,
)


class FakeChatwootTransport:
    def __init__(self):
        self.calls = []

    def __call__(self, method, conversation_id, body, source, suffix=""):
        self.calls.append({
            "method": method,
            "conversation_id": conversation_id,
            "body": body,
            "suffix": suffix,
        })
        if method == "GET":
            return {
                "status_code": 200,
                "body": {
                    "custom_attributes": {
                        "order_id": "ORD-2026-EXISTING",
                        "order_status": "Draft",
                        "conversation_mode": "AUTO",
                        "payment_method": "Cash",
                    },
                    "labels": ["warm_lead", "lead"],
                },
            }
        return {"status_code": 200, "body": {"success": True}}


class ChatwootHygieneTests(unittest.TestCase):
    def test_build_payload_marks_meat_lead_product_delivery_and_test_flow(self):
        payload = build_sam_meat_chatwoot_hygiene_payload(
            lead_payload={
                "lead_id": "OSK-SALES-LEAD-TEST",
                "product_type": "half_carcass",
                "cut_set": "Set A",
                "delivery_or_collection": "delivery",
                "delivery_town": "Riversdale",
                "notes": "TEST FLOW - delete after test.",
            },
            facts={
                "product_type": "half_carcass",
                "cut_set": "Set A",
                "location": "Riversdale",
                "delivery_or_collection": "delivery",
                "delivery_town": "Riversdale",
                "delivery_address_line_1": "12 Test Street",
                "timing": "next available farm run",
                "payment_method": "EFT",
                "budget_amount": "3000",
                "target_packed_kg": "25",
                "match_preference": "best_fit",
            },
            inbound={"content": "TEST FLOW - delete after test. Half carcass Set A delivery."},
        )

        self.assertEqual(payload["custom_attributes"]["sales_lane"], "meat_preorder")
        self.assertEqual(payload["custom_attributes"]["meat_product_type"], "half_carcass")
        self.assertEqual(payload["custom_attributes"]["meat_next_gate"], "owner_price_review")
        self.assertEqual(payload["custom_attributes"]["meat_budget_amount"], "3000")
        self.assertEqual(payload["custom_attributes"]["meat_target_packed_kg"], "25")
        self.assertEqual(payload["custom_attributes"]["meat_match_preference"], "best_fit")
        self.assertIn("meat_lead", payload["labels"])
        self.assertIn("half_carcass", payload["labels"])
        self.assertIn("set_a", payload["labels"])
        self.assertIn("delivery", payload["labels"])
        self.assertIn("test_flow", payload["labels"])

    def test_payload_moves_pop_to_unverified_bank_gate(self):
        payload = build_sam_meat_chatwoot_hygiene_payload(
            lead_payload={"lead_id": "OSK-SALES-LEAD-TEST"},
            facts={"product_type": "half_carcass"},
            inbound={"content": "I paid and sent POP."},
            pop_capture={"detected": True, "recorded": False},
        )

        self.assertEqual(payload["custom_attributes"]["meat_payment_state"], "pop_received_unverified")
        self.assertEqual(payload["custom_attributes"]["meat_next_gate"], "confirm_bank_receipt")
        self.assertEqual(payload["custom_attributes"]["meat_last_customer_intent"], "sends_pop")
        self.assertIn("pop_received_unverified", payload["labels"])

    def test_sync_is_disabled_without_env_and_transport(self):
        result = sync_sam_meat_chatwoot_hygiene(
            "1808",
            lead_payload={"lead_id": "OSK-SALES-LEAD-TEST"},
            environ={},
        )

        self.assertTrue(result["success"])
        self.assertFalse(result["enabled"])
        self.assertEqual(result["status"], "chatwoot_hygiene_disabled")

    def test_sync_preserves_existing_attributes_and_labels(self):
        transport = FakeChatwootTransport()

        result = sync_sam_meat_chatwoot_hygiene(
            "1808",
            lead_payload={
                "lead_id": "OSK-SALES-LEAD-TEST",
                "product_type": "half_carcass",
                "cut_set": "Set A",
                "delivery_or_collection": "collection",
                "delivery_town": "Riversdale",
            },
            facts={
                "product_type": "half_carcass",
                "cut_set": "Set A",
                "location": "Riversdale",
                "delivery_or_collection": "collection",
                "timing": "next week",
                "payment_method": "EFT",
            },
            environ={"SAM_MEAT_CHATWOOT_HYGIENE_ENABLED": "1"},
            transport=transport,
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["status"], "chatwoot_hygiene_synced")
        self.assertEqual([call["method"] for call in transport.calls], ["GET", "POST", "POST"])
        attr_body = transport.calls[1]["body"]["custom_attributes"]
        label_body = transport.calls[2]["body"]["labels"]
        self.assertEqual(transport.calls[1]["suffix"], "custom_attributes")
        self.assertEqual(transport.calls[2]["suffix"], "labels")
        self.assertEqual(attr_body["order_id"], "ORD-2026-EXISTING")
        self.assertEqual(attr_body["conversation_mode"], "AUTO")
        self.assertEqual(attr_body["payment_method"], "Cash")
        self.assertEqual(attr_body["meat_payment_state"], "not_requested")
        self.assertEqual(attr_body["meat_lead_id"], "OSK-SALES-LEAD-TEST")
        self.assertIn("warm_lead", label_body)
        self.assertIn("lead", label_body)
        self.assertIn("meat_lead", label_body)
        self.assertIn("collection", label_body)


if __name__ == "__main__":
    unittest.main()
