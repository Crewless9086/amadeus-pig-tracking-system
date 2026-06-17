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

        allowed, _denied = sam_meat_runtime.authorize_sam_meat_webhook(
            {},
            query_args={"token": "test-sam-meat-webhook-token-32-chars"},
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
                "delivery_address_line_1": "12 Long Street",
                "delivery_town": "Albertinia",
                "delivery_notes": "Blue gate",
                "payment_method": "cash",
            }),
        )

        self.assertEqual(facts["product_type"], "full_carcass")
        self.assertEqual(facts["cut_set"], "Set B")
        self.assertEqual(facts["location"], "Albertinia")
        self.assertEqual(facts["delivery_or_collection"], "delivery")
        self.assertEqual(facts["delivery_address_line_1"], "12 Long Street")
        self.assertEqual(facts["delivery_town"], "Albertinia")
        self.assertEqual(facts["delivery_notes"], "Blue gate")
        self.assertEqual(facts["payment_method"], "Cash")
        self.assertTrue(facts["llm_used"])

    def test_delivery_address_is_extracted_when_customer_supplies_it(self):
        inbound = sam_meat_runtime.parse_chatwoot_inbound(inbound_payload(
            content="Delivery please to address 12 Long Street, Riversdale. EFT is fine.",
        ))
        facts = sam_meat_runtime.extract_meat_facts(inbound["content"], inbound, environ={})

        self.assertEqual(facts["delivery_or_collection"], "delivery")
        self.assertEqual(facts["delivery_address_line_1"], "12 Long Street")
        self.assertEqual(facts["delivery_town"], "Riversdale")

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

    def test_delivery_customer_is_asked_for_address_before_payment(self):
        inbound = sam_meat_runtime.parse_chatwoot_inbound(inbound_payload(
            content="I want a half carcass Set A in Riversdale. Delivery please.",
        ))
        facts = sam_meat_runtime.extract_meat_facts(inbound["content"], inbound, environ={})
        decision = sam_meat_runtime.build_sam_meat_decision(
            inbound,
            facts,
            {"success": True, "lead_id": "OSK-SALES-LEAD-TEST"},
            201,
        )

        self.assertIn("delivery street address", decision["reply_text"])

    def test_sam_asks_for_timing_before_review_handoff(self):
        inbound = sam_meat_runtime.parse_chatwoot_inbound(inbound_payload(
            content="Half carcass Set A, Riversdale, delivery to 12 Long Street. EFT.",
        ))
        facts = sam_meat_runtime.extract_meat_facts(inbound["content"], inbound, environ={})
        decision = sam_meat_runtime.build_sam_meat_decision(
            inbound,
            facts,
            {"success": True, "lead_id": "OSK-SALES-LEAD-TEST"},
            201,
        )

        self.assertIn("When would you ideally like", decision["reply_text"])
        self.assertNotIn("farm to review", decision["reply_text"])

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
    @patch("modules.sales.sam_meat_runtime.record_meat_fulfillment_event")
    @patch("modules.sales.sam_meat_runtime.get_sales_lead_preorder_contract")
    @patch("modules.sales.sam_meat_runtime.record_sam_meat_intake_lead")
    def test_handle_inbound_autoreply_sends_and_records_audit_events(self, mock_record, mock_contract, mock_fulfillment, mock_event):
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

    @patch("modules.sales.sam_meat_runtime.record_meat_fulfillment_event")
    @patch("modules.sales.sam_meat_runtime.list_sales_leads")
    @patch("modules.sales.sam_meat_runtime.get_sales_lead_preorder_contract")
    @patch("modules.sales.sam_meat_runtime.record_sam_meat_intake_lead")
    def test_handle_inbound_records_delivery_address_capture_when_ready(self, mock_record, mock_contract, mock_list, mock_fulfillment):
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
        mock_list.return_value = ({"success": True, "sales_leads": []}, 200)
        mock_fulfillment.return_value = ({"success": True, "status": "delivery_address_captured"}, 201)

        result, status_code = sam_meat_runtime.handle_sam_meat_chatwoot_inbound(
            inbound_payload(content="Half carcass Set A, Riversdale, delivery to 12 Long Street, EFT."),
            environ={"SAM_MEAT_BACKEND_AUTOREPLY_ENABLED": "0"},
        )

        self.assertEqual(status_code, 200)
        self.assertTrue(result["fulfillment_capture"]["recorded"])
        mock_fulfillment.assert_called_once()
        self.assertEqual(mock_fulfillment.call_args.args[0], "OSK-SALES-LEAD-TEST")
        self.assertEqual(mock_fulfillment.call_args.args[1]["event_type"], "delivery_address_captured")
        self.assertEqual(mock_fulfillment.call_args.args[1]["address_line_1"], "12 Long Street")

    @patch("modules.sales.sam_meat_runtime.record_meat_fulfillment_event")
    @patch("modules.sales.sam_meat_runtime.list_sales_leads")
    @patch("modules.sales.sam_meat_runtime.get_sales_lead_preorder_contract")
    @patch("modules.sales.sam_meat_runtime.record_sam_meat_intake_lead")
    def test_address_reply_inherits_existing_conversation_meat_context(self, mock_record, mock_contract, mock_list, mock_fulfillment):
        mock_list.return_value = ({
            "success": True,
            "sales_leads": [{
                "lead_id": "OSK-SALES-LEAD-CONTEXT",
                "chatwoot_conversation_id": "1808",
                "interest": {
                    "product_type": "half_carcass",
                    "cut_set": "Set A",
                    "location": "Riversdale",
                    "delivery_or_collection": "delivery",
                },
            }],
        }, 200)
        mock_record.return_value = ({
            "success": True,
            "status": "ok",
            "lead_id": "OSK-SALES-LEAD-CONTEXT",
            "contract": {},
        }, 201)
        mock_contract.return_value = ({
            "success": True,
            "contract": {"contract_status": "needs_owner_confirmation"},
        }, 200)
        mock_fulfillment.return_value = ({"success": True, "status": "delivery_address_captured"}, 201)

        result, status_code = sam_meat_runtime.handle_sam_meat_chatwoot_inbound(
            inbound_payload(content="The delivery address is 12 Test Street, Riversdale. Blue gate. EFT is fine."),
            environ={"SAM_MEAT_BACKEND_AUTOREPLY_ENABLED": "0"},
        )

        self.assertEqual(status_code, 200)
        self.assertEqual(result["facts"]["product_type"], "half_carcass")
        self.assertEqual(result["facts"]["cut_set"], "Set A")
        self.assertEqual(result["facts"]["delivery_or_collection"], "delivery")
        self.assertEqual(result["facts"]["payment_method"], "EFT")
        self.assertNotIn("pork half carcass, full carcass", result["sam_decision"]["reply_text"])
        self.assertTrue(result["fulfillment_capture"]["recorded"])
        lead_payload = mock_record.call_args.args[0]
        self.assertEqual(lead_payload["product_type"], "half_carcass")
        self.assertEqual(lead_payload["lead_id"], "OSK-SALES-LEAD-CONTEXT")
        self.assertEqual(lead_payload["delivery_address_line_1"], "12 Test Street")

    @patch("modules.sales.sam_meat_runtime.record_meat_fulfillment_event")
    @patch("modules.sales.sam_meat_runtime.list_sales_leads")
    @patch("modules.sales.sam_meat_runtime.get_sales_lead_preorder_contract")
    @patch("modules.sales.sam_meat_runtime.record_sam_meat_intake_lead")
    def test_conversation_context_prefers_progressed_duplicate_lead(self, mock_record, mock_contract, mock_list, mock_fulfillment):
        mock_list.return_value = ({
            "success": True,
            "sales_leads": [
                {
                    "lead_id": "OSK-SALES-LEAD-OLDER",
                    "chatwoot_conversation_id": "1808",
                    "latest_event": {"event_type": "closed"},
                    "interest": {
                        "product_type": "half_carcass",
                        "cut_set": "Set A",
                        "location": "Riversdale",
                    },
                },
                {
                    "lead_id": "OSK-SALES-LEAD-PROGRESSED",
                    "chatwoot_conversation_id": "1808",
                    "latest_event": {"event_type": "customer_followup_sent"},
                    "interest": {
                        "product_type": "half_carcass",
                        "cut_set": "Set A",
                        "location": "Riversdale",
                        "delivery_or_collection": "delivery",
                        "timing": "next available week",
                        "payment_method": "EFT",
                    },
                },
            ],
        }, 200)
        mock_record.return_value = ({
            "success": True,
            "status": "ok",
            "lead_id": "OSK-SALES-LEAD-PROGRESSED",
            "contract": {},
        }, 201)
        mock_contract.return_value = ({
            "success": True,
            "contract": {"contract_status": "owner_money_path_ready"},
        }, 200)
        mock_fulfillment.return_value = ({"success": True, "status": "delivery_address_captured"}, 201)

        result, status_code = sam_meat_runtime.handle_sam_meat_chatwoot_inbound(
            inbound_payload(content="The delivery address is 12 Test Street, Riversdale. Blue gate."),
            environ={"SAM_MEAT_BACKEND_AUTOREPLY_ENABLED": "0"},
        )

        self.assertEqual(status_code, 200)
        self.assertEqual(result["prior_context"]["lead_id"], "OSK-SALES-LEAD-PROGRESSED")
        self.assertEqual(result["prior_context"]["latest_event"], "customer_followup_sent")
        lead_payload = mock_record.call_args.args[0]
        self.assertEqual(lead_payload["lead_id"], "OSK-SALES-LEAD-PROGRESSED")

    @patch("modules.sales.sam_meat_runtime.record_customer_booking_confirmation")
    @patch("modules.sales.sam_meat_runtime.list_sales_leads")
    @patch("modules.sales.sam_meat_runtime.get_sales_lead_preorder_contract")
    @patch("modules.sales.sam_meat_runtime.record_sam_meat_intake_lead")
    def test_customer_yes_after_followup_sent_records_booking_confirmation(self, mock_record, mock_contract, mock_list, mock_confirmation):
        mock_list.return_value = ({
            "success": True,
            "sales_leads": [{
                "lead_id": "OSK-SALES-LEAD-PROGRESSED",
                "chatwoot_conversation_id": "1808",
                "latest_event": "customer_followup_sent",
                "interest": {
                    "product_type": "half_carcass",
                    "cut_set": "Set A",
                    "location": "Riversdale",
                    "delivery_or_collection": "collection",
                    "timing": "next available week",
                    "payment_method": "EFT",
                },
            }],
        }, 200)
        mock_record.return_value = ({
            "success": True,
            "status": "ok",
            "lead_id": "OSK-SALES-LEAD-PROGRESSED",
            "contract": {},
        }, 201)
        mock_contract.return_value = ({
            "success": True,
            "contract": {"contract_status": "owner_money_path_ready"},
        }, 200)
        mock_confirmation.return_value = ({
            "success": True,
            "status": "ok",
            "records_customer_booking_confirmation": True,
        }, 201)

        result, status_code = sam_meat_runtime.handle_sam_meat_chatwoot_inbound(
            inbound_payload(content="Yes, please proceed with the final booking review."),
            environ={"SAM_MEAT_BACKEND_AUTOREPLY_ENABLED": "0"},
        )

        self.assertEqual(status_code, 200)
        self.assertTrue(result["booking_confirmation"]["recorded"])
        self.assertIn("noted your confirmation", result["sam_decision"]["reply_text"])
        mock_confirmation.assert_called_once()
        self.assertEqual(mock_confirmation.call_args.args[0], "OSK-SALES-LEAD-PROGRESSED")
        self.assertEqual(
            mock_confirmation.call_args.args[1]["customer_confirmation"],
            "Yes, please proceed with the final booking review.",
        )


if __name__ == "__main__":
    unittest.main()
