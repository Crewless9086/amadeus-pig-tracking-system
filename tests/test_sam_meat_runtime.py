import unittest
from unittest.mock import Mock, patch

from modules.sales import sam_meat_runtime


def inbound_payload(**overrides):
    payload = {
        "event": "message_created",
        "message_type": "incoming",
        "content": "Hi Sam, I want a half carcass Set A in Riversdale. Collection please. EFT is fine.",
        "conversation": {
            "id": 1808,
            "inbox": {"channel_type": "Channel::Whatsapp"},
        },
        "sender": {
            "id": 99,
            "name": "Charl N",
            "phone_number": "+27820000000",
        },
        "account": {"id": 147387},
    }
    payload.update(overrides)
    return payload


class SamMeatRuntimeTests(unittest.TestCase):
    def test_authorize_webhook_is_default_off_and_token_gated(self):
        allowed, denied = sam_meat_runtime.authorize_sam_meat_webhook(
            {},
            environ={},
        )

        self.assertFalse(allowed)
        self.assertEqual(denied["status"], "sam_meat_backend_webhook_disabled")
        self.assertFalse(denied["sends_customer_message"])
        self.assertFalse(denied["calls_chatwoot"])

        env = {
            "SAM_MEAT_BACKEND_WEBHOOK_ENABLED": "1",
            "SAM_MEAT_BACKEND_WEBHOOK_TOKEN": "test-sam-meat-webhook-token-32-chars",
        }
        allowed, _denied = sam_meat_runtime.authorize_sam_meat_webhook(
            {"Authorization": "Bearer test-sam-meat-webhook-token-32-chars"},
            environ=env,
        )

        self.assertTrue(allowed)

    def test_parse_chatwoot_inbound_ignores_outbound_messages(self):
        inbound = sam_meat_runtime.parse_chatwoot_inbound(inbound_payload(message_type="outgoing"))

        self.assertFalse(inbound["processable"])
        self.assertEqual(inbound["status"], "ignored_non_incoming_message")

    def test_extract_meat_facts_uses_deterministic_fallback(self):
        inbound = sam_meat_runtime.parse_chatwoot_inbound(inbound_payload())
        facts = sam_meat_runtime.extract_meat_facts(inbound["content"], inbound, environ={})

        self.assertEqual(facts["product_type"], "half_carcass")
        self.assertEqual(facts["cut_set"], "Set A")
        self.assertEqual(facts["location"], "Riversdale")
        self.assertEqual(facts["delivery_or_collection"], "collection")
        self.assertEqual(facts["payment_method"], "EFT")
        self.assertFalse(facts["llm_used"])

    def test_extract_meat_facts_can_merge_safe_llm_patch(self):
        inbound = sam_meat_runtime.parse_chatwoot_inbound(inbound_payload(content="Hello"))
        facts = sam_meat_runtime.extract_meat_facts(
            inbound["content"],
            inbound,
            environ={"SAM_MEAT_BACKEND_LLM_ENABLED": "1"},
            llm_extractor=Mock(return_value={
                "product_type": "full_carcass",
                "cut_set": "Set B",
                "location": "Albertinia",
                "delivery_or_collection": "delivery",
                "payment_method": "cash",
            }),
        )

        self.assertEqual(facts["product_type"], "full_carcass")
        self.assertEqual(facts["cut_set"], "Set B")
        self.assertEqual(facts["location"], "Albertinia")
        self.assertEqual(facts["delivery_or_collection"], "delivery")
        self.assertEqual(facts["payment_method"], "Cash")
        self.assertTrue(facts["llm_used"])

    def test_cut_set_question_gets_bounded_pork_model_answer(self):
        inbound = sam_meat_runtime.parse_chatwoot_inbound(inbound_payload(
            content="What does Set A include for a half carcass in Riversdale?",
        ))
        facts = sam_meat_runtime.extract_meat_facts(inbound["content"], inbound, environ={})
        decision = sam_meat_runtime.build_sam_meat_decision(
            inbound,
            facts,
            {"success": True, "lead_id": "OSK-SALES-LEAD-TEST"},
            201,
        )

        self.assertIn("Set A is the Family Freezer Pack", decision["reply_text"])
        self.assertIn("pork chops", decision["reply_text"])
        self.assertIn("before quoting or booking", decision["reply_text"])
        self.assertNotIn("R100", decision["reply_text"])

    @patch("modules.sales.sam_meat_runtime.get_sales_lead_preorder_contract")
    @patch("modules.sales.sam_meat_runtime.record_sam_meat_intake_lead")
    def test_handle_inbound_records_lead_without_autoreply_when_disabled(self, mock_record, mock_contract):
        mock_record.return_value = ({
            "success": True,
            "status": "ok",
            "lead_id": "OSK-SALES-LEAD-TEST",
            "contract": {},
        }, 201)
        mock_contract.return_value = ({
            "success": True,
            "contract": {"contract_status": "needs_owner_confirmation"},
        }, 200)

        result, status_code = sam_meat_runtime.handle_sam_meat_chatwoot_inbound(
            inbound_payload(),
            environ={"SAM_MEAT_BACKEND_AUTOREPLY_ENABLED": "0"},
            chatwoot_sender=Mock(),
        )

        self.assertEqual(status_code, 200)
        self.assertTrue(result["processed"])
        self.assertFalse(result["sent"])
        self.assertEqual(result["send_status"], "autoreply_not_enabled")
        self.assertFalse(result["sends_customer_message"])
        self.assertFalse(result["calls_chatwoot"])
        mock_record.assert_called_once()
        lead_payload = mock_record.call_args.args[0]
        self.assertEqual(lead_payload["product_type"], "half_carcass")
        self.assertEqual(lead_payload["location"], "Riversdale")

    @patch("modules.sales.sam_meat_runtime.record_sales_lead_event")
    @patch("modules.sales.sam_meat_runtime.get_sales_lead_preorder_contract")
    @patch("modules.sales.sam_meat_runtime.record_sam_meat_intake_lead")
    def test_handle_inbound_autoreply_sends_and_records_audit_events(self, mock_record, mock_contract, mock_event):
        mock_record.return_value = ({
            "success": True,
            "status": "ok",
            "lead_id": "OSK-SALES-LEAD-TEST",
            "contract": {},
        }, 201)
        mock_contract.return_value = ({
            "success": True,
            "contract": {"contract_status": "needs_owner_confirmation"},
        }, 200)
        sender = Mock(return_value={"message_id": "123", "conversation_id": "1808"})

        result, status_code = sam_meat_runtime.handle_sam_meat_chatwoot_inbound(
            inbound_payload(),
            environ={"SAM_MEAT_BACKEND_AUTOREPLY_ENABLED": "1"},
            chatwoot_sender=sender,
        )

        self.assertEqual(status_code, 200)
        self.assertTrue(result["sent"])
        self.assertTrue(result["sends_customer_message"])
        self.assertTrue(result["calls_chatwoot"])
        sender.assert_called_once()
        event_types = [call.args[1]["event_type"] for call in mock_event.call_args_list]
        self.assertEqual(event_types, ["sam_meat_autoreply_attempted", "sam_meat_autoreply_sent"])


if __name__ == "__main__":
    unittest.main()
