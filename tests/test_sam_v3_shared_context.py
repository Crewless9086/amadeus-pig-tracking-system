import unittest
from unittest.mock import Mock, patch

from modules.sales.sam_shared_context import build_sam_v3_context_packet
from modules.sales import sam_meat_runtime
from tests.test_sam_meat_runtime import inbound_payload


class SamV3SharedContextTests(unittest.TestCase):
    def test_context_packet_uses_beacon_campaign_and_chatwoot_history(self):
        inbound = sam_meat_runtime.parse_chatwoot_inbound(inbound_payload(
            content="Yummy",
            conversation={
                "id": 1819,
                "inbox": {"channel_type": "Channel::Whatsapp"},
                "labels": ["facebook", "beacon_meat_launch"],
                "custom_attributes": {
                    "source_campaign_id": "BEACON-MEAT-001",
                    "source_post_text": "Fresh Amadeus Farm pork freezer packs are opening for Riversdale.",
                    "source_call_to_action": "Message Sam for options.",
                    "meat_delivery_town": "Riversdale",
                },
                "messages": [
                    {"id": 1, "message_type": 1, "content": "Fresh Amadeus Farm pork freezer packs are opening."},
                    {"id": 2, "message_type": 0, "content": "Yummy"},
                ],
            },
        ))

        packet = build_sam_v3_context_packet(
            inbound,
            campaign_fetcher=lambda campaign_id, _attrs: {
                "campaign": {
                    "campaign_id": campaign_id,
                    "campaign_title": "Riversdale freezer pork launch",
                    "opportunity": {
                        "sales_lane": "meat_preorder",
                        "product_focus": "pork freezer packs",
                        "target_area": "Riversdale",
                    },
                    "draft": {
                        "post_text": "Fresh Amadeus Farm pork freezer packs are opening for Riversdale.",
                        "call_to_action": "Message Sam for options.",
                    },
                },
            },
        )

        self.assertTrue(packet["source_context"]["available"])
        self.assertEqual(packet["source_context"]["campaign_id"], "BEACON-MEAT-001")
        self.assertEqual(packet["source_context"]["sales_lane"], "meat_preorder")
        self.assertIn("freezer packs", packet["source_context"]["post_text"])
        self.assertEqual(packet["conversation"]["recent_messages"][-1]["content"], "Yummy")
        self.assertTrue(packet["context_quality"]["has_campaign_context"])

    @patch("modules.sales.sam_meat_runtime.get_active_sales_lead_by_conversation")
    @patch("modules.sales.sam_meat_runtime.get_sales_lead_preorder_contract")
    @patch("modules.sales.sam_meat_runtime.record_sam_meat_intake_lead")
    def test_sam_v3_llm_first_reply_beats_old_vague_meat_menu(self, mock_record, mock_contract, mock_active):
        mock_active.return_value = ({"success": False, "status": "not_found"}, 404)
        mock_record.return_value = ({
            "success": True,
            "status": "ok",
            "lead_id": "OSK-SALES-LEAD-V3",
            "contract": {"missing_before_money_path": ["product_type"]},
        }, 201)
        mock_contract.return_value = ({
            "success": True,
            "contract": {"contract_status": "needs_owner_confirmation"},
        }, 200)
        agent = Mock(return_value={
            "intent": "warm_campaign_interest",
            "should_reply": True,
            "reply_text": (
                "Yummy is a fair reaction. This is our Amadeus Farm pork for freezer orders, "
                "raised slowly and booked properly before the farm run. Would you like me to show you the half-carcass and cut-set options?"
            ),
            "facts_patch": {"product_type": "unknown"},
            "missing_fields": ["product_type"],
            "next_action": "soft_qualify_interest",
            "confidence": 0.94,
            "requires_confirmation": False,
            "risk_flags": [],
        })

        result, status_code = sam_meat_runtime.handle_sam_meat_chatwoot_inbound(
            inbound_payload(
                content="Yummy",
                conversation={
                    "id": 1819,
                    "inbox": {"channel_type": "Channel::Whatsapp"},
                    "custom_attributes": {
                        "source_campaign_id": "BEACON-MEAT-001",
                        "source_post_text": "Fresh Amadeus Farm pork freezer packs are opening for Riversdale.",
                    },
                },
            ),
            environ={
                "SAM_MEAT_BACKEND_AGENT_V3_ENABLED": "1",
                "SAM_MEAT_BACKEND_LLM_MODEL": "gpt-5",
                "OPENAI_API_KEY": "test-key",
                "SAM_MEAT_BACKEND_AUTOREPLY_ENABLED": "0",
            },
            llm_agent_v3_decider=agent,
        )

        self.assertEqual(status_code, 200)
        self.assertTrue(result["agent_decision"]["used"])
        self.assertEqual(result["agent_decision"]["version"], "v3")
        self.assertIn("Yummy is a fair reaction", result["sam_decision"]["reply_text"])
        self.assertNotIn("half carcass, full carcass, or a cut-set pack", result["sam_decision"]["reply_text"])
        self.assertEqual(result["sam_decision"]["agent_v2"]["version"], "v3")
        self.assertTrue(result["sam_context_packet"]["source_context"]["available"])

    @patch("modules.sales.sam_meat_runtime.get_active_sales_lead_by_conversation")
    @patch("modules.sales.sam_meat_runtime.get_sales_lead_preorder_contract")
    @patch("modules.sales.sam_meat_runtime.record_sam_meat_intake_lead")
    def test_sam_v3_blocks_unsafe_price_claim_and_falls_back_to_gate(self, mock_record, mock_contract, mock_active):
        mock_active.return_value = ({"success": False, "status": "not_found"}, 404)
        mock_record.return_value = ({
            "success": True,
            "status": "ok",
            "lead_id": "OSK-SALES-LEAD-V3-BLOCK",
            "contract": {"missing_before_money_path": ["price_per_kg"]},
        }, 201)
        mock_contract.return_value = ({
            "success": True,
            "contract": {"contract_status": "needs_owner_confirmation"},
        }, 200)

        result, status_code = sam_meat_runtime.handle_sam_meat_chatwoot_inbound(
            inbound_payload(content="How much is the half carcass?"),
            environ={
                "SAM_MEAT_BACKEND_AGENT_V3_ENABLED": "1",
                "SAM_MEAT_BACKEND_LLM_MODEL": "gpt-5",
                "OPENAI_API_KEY": "test-key",
                "SAM_MEAT_BACKEND_AUTOREPLY_ENABLED": "0",
            },
            llm_agent_v3_decider=Mock(return_value={
                "intent": "meat_preorder",
                "should_reply": True,
                "reply_text": "The half carcass is R2,600 and your booking is confirmed.",
                "facts_patch": {"product_type": "half_carcass"},
                "next_action": "soft_qualify_interest",
                "confidence": 0.95,
                "risk_flags": [],
            }),
        )

        self.assertEqual(status_code, 200)
        self.assertFalse(result["agent_decision"]["used"])
        self.assertEqual(result["agent_decision"]["status"], "agent_v3_reply_blocked")
        self.assertIn("not able to prepare", result["sam_decision"]["reply_text"])
        self.assertNotIn("R2,600", result["sam_decision"]["reply_text"])


if __name__ == "__main__":
    unittest.main()
