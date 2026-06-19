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

    def test_extract_meat_facts_handles_afrikaans_meat_terms_without_llm(self):
        inbound = sam_meat_runtime.parse_chatwoot_inbound(inbound_payload(
            content="Ek soek n halwe karkas Set A Riversdale afhaal EFT volgende week.",
        ))
        facts = sam_meat_runtime.extract_meat_facts(inbound["content"], inbound, environ={})

        self.assertEqual(facts["product_type"], "half_carcass")
        self.assertEqual(facts["cut_set"], "Set A")
        self.assertEqual(facts["location"], "Riversdale")
        self.assertEqual(facts["delivery_or_collection"], "collection")
        self.assertEqual(facts["timing"], "next week")
        self.assertEqual(facts["payment_method"], "EFT")
        self.assertFalse(facts["llm_used"])

    def test_extract_meat_facts_handles_common_typos_without_llm(self):
        inbound = sam_meat_runtime.parse_chatwoot_inbound(inbound_payload(
            content="Hlaf carcas set a rivrsdale colect eft nxt week",
        ))
        facts = sam_meat_runtime.extract_meat_facts(inbound["content"], inbound, environ={})

        self.assertEqual(facts["product_type"], "half_carcass")
        self.assertEqual(facts["cut_set"], "Set A")
        self.assertEqual(facts["location"], "Riversdale")
        self.assertEqual(facts["delivery_or_collection"], "collection")
        self.assertEqual(facts["timing"], "next week")
        self.assertEqual(facts["payment_method"], "EFT")
        self.assertFalse(facts["llm_used"])

    def test_google_maps_link_is_captured_as_delivery_context_without_llm(self):
        inbound = sam_meat_runtime.parse_chatwoot_inbound(inbound_payload(
            content="Please deliver here https://maps.google.com/?q=-34.0921,21.2576",
        ))
        facts = sam_meat_runtime.extract_meat_facts(inbound["content"], inbound, environ={})

        self.assertEqual(facts["delivery_or_collection"], "delivery")
        self.assertEqual(facts["delivery_address_line_1"], "Shared Google Maps location")
        self.assertEqual(facts["delivery_place_name"], "Shared Google Maps location")
        self.assertEqual(facts["delivery_location_latitude"], "-34.0921")
        self.assertEqual(facts["delivery_location_longitude"], "21.2576")
        self.assertIn("maps.google.com", facts["delivery_maps_url"])
        self.assertFalse(facts["llm_used"])

    def test_parse_chatwoot_inbound_uses_explicit_closed_whatsapp_window(self):
        inbound = sam_meat_runtime.parse_chatwoot_inbound(inbound_payload(
            service_window_state="outside_24h",
        ))

        self.assertTrue(inbound["processable"])
        self.assertEqual(inbound["whatsapp_window_state"], "closed")

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

    def test_buyer_preference_facts_are_extracted_for_butcher_matching(self):
        inbound = sam_meat_runtime.parse_chatwoot_inbound(inbound_payload(
            content="I have about R3000 and want around 25kg packed pork. Please choose the best fit.",
        ))
        facts = sam_meat_runtime.extract_meat_facts(inbound["content"], inbound, environ={})

        self.assertEqual(facts["budget_amount"], "3000")
        self.assertEqual(facts["target_packed_kg"], "25")
        self.assertEqual(facts["match_preference"], "best_fit")

    def test_heaviest_preference_is_extracted_without_stock_authority(self):
        inbound = sam_meat_runtime.parse_chatwoot_inbound(inbound_payload(
            content="I want the heaviest half carcass Set A in Riversdale.",
        ))
        facts = sam_meat_runtime.extract_meat_facts(inbound["content"], inbound, environ={})

        self.assertEqual(facts["match_preference"], "heaviest")
        decision = sam_meat_runtime.build_sam_meat_decision(
            inbound,
            facts,
            {"success": True, "lead_id": "OSK-SALES-LEAD-TEST"},
            201,
        )
        self.assertIn("no_stock_reservation", decision["blocked_actions"])

    def test_shared_location_payload_is_captured_as_delivery_context(self):
        inbound = sam_meat_runtime.parse_chatwoot_inbound(inbound_payload(
            content="",
            attachments=[{
                "file_type": "location",
                "latitude": "-34.0921",
                "longitude": "21.2576",
                "name": "12 Test Street, Riversdale",
            }],
        ))
        facts = sam_meat_runtime.extract_meat_facts(inbound["content"], inbound, environ={})

        self.assertTrue(inbound["processable"])
        self.assertEqual(facts["delivery_or_collection"], "delivery")
        self.assertEqual(facts["delivery_address_line_1"], "12 Test Street, Riversdale")
        self.assertEqual(facts["delivery_place_name"], "12 Test Street, Riversdale")
        self.assertEqual(facts["delivery_location_latitude"], "-34.0921")
        self.assertEqual(facts["delivery_location_longitude"], "21.2576")
        self.assertIn("maps.google.com", facts["delivery_maps_url"])
        lead_payload = sam_meat_runtime.build_sam_meat_lead_payload_from_inbound(inbound, facts)
        self.assertEqual(lead_payload["delivery_place_name"], "12 Test Street, Riversdale")
        self.assertEqual(lead_payload["delivery_location_latitude"], "-34.0921")
        self.assertEqual(lead_payload["delivery_location_longitude"], "21.2576")

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

    def test_non_pork_request_is_redirected_without_pretending_to_sell_it(self):
        inbound = sam_meat_runtime.parse_chatwoot_inbound(inbound_payload(
            content="Can I order beef mince from you?",
        ))
        facts = sam_meat_runtime.extract_meat_facts(inbound["content"], inbound, environ={})
        decision = sam_meat_runtime.build_sam_meat_decision(
            inbound,
            facts,
            {"success": True, "lead_id": "OSK-SALES-LEAD-TEST"},
            201,
        )

        self.assertEqual(facts["product_type"], "unknown")
        self.assertIn("pork orders only", decision["reply_text"])
        self.assertIn("half carcass", decision["reply_text"])

    def test_frustrated_price_request_gets_soft_acknowledgement_without_price(self):
        inbound = sam_meat_runtime.parse_chatwoot_inbound(inbound_payload(
            content="Why can nobody just tell me the price? This is annoying.",
        ))
        facts = sam_meat_runtime.extract_meat_facts(inbound["content"], inbound, environ={})
        decision = sam_meat_runtime.build_sam_meat_decision(
            inbound,
            facts,
            {"success": True, "lead_id": "OSK-SALES-LEAD-TEST"},
            201,
        )

        self.assertIn("do not want to waste your time", decision["reply_text"])
        self.assertIn("half carcass", decision["reply_text"])
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

    @patch("modules.sales.sam_meat_runtime.send_meat_estimated_quote_to_chatwoot")
    @patch("modules.sales.sam_meat_runtime.build_meat_estimated_quote_packet")
    @patch("modules.sales.sam_meat_runtime.record_sales_lead_event")
    @patch("modules.sales.sam_meat_runtime.record_meat_fulfillment_event")
    @patch("modules.sales.sam_meat_runtime.get_sales_lead_preorder_contract")
    @patch("modules.sales.sam_meat_runtime.record_sam_meat_intake_lead")
    def test_autosend_enabled_sends_quote_document_after_preparing_reply(
        self,
        mock_record,
        mock_contract,
        mock_fulfillment,
        mock_event,
        mock_quote,
        mock_document_send,
    ):
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
        mock_quote.return_value = ({
            "success": True,
            "quote_safe": True,
            "sam_preparing_message": "I am preparing your estimated quote now and will send it through shortly.",
        }, 200)
        mock_document_send.return_value = ({
            "success": True,
            "status": "estimated_quote_sent",
            "sent": True,
            "document_ref": "MQ-2026-RESSED",
        }, 200)
        sender = Mock(return_value={"message_id": "123", "conversation_id": "1808"})
        document_sender = Mock()

        result, status_code = sam_meat_runtime.handle_sam_meat_chatwoot_inbound(
            inbound_payload(content="Half carcass Set A Riversdale collection next available week EFT"),
            environ={
                "SAM_MEAT_BACKEND_AUTOREPLY_ENABLED": "1",
                "MEAT_SALES_DOCUMENT_AUTOSEND_ENABLED": "1",
            },
            chatwoot_sender=sender,
            document_sender=document_sender,
        )

        self.assertEqual(status_code, 200)
        self.assertEqual(result["send_status"], "sent")
        self.assertTrue(result["document_sent"])
        self.assertEqual(result["document_send_status"], "estimated_quote_sent")
        self.assertTrue(result["sam_decision"]["document_send_requested"])
        self.assertIn("preparing your estimated quote", result["sam_decision"]["reply_text"])
        mock_document_send.assert_called_once()
        self.assertEqual(mock_document_send.call_args.args[0], "OSK-SALES-LEAD-PROGRESSED")
        self.assertEqual(mock_document_send.call_args.args[1]["conversation_id"], "1808")
        self.assertNotIn("force_resend", mock_document_send.call_args.args[1])
        self.assertEqual(mock_document_send.call_args.kwargs["chatwoot_sender"], document_sender)

    @patch("modules.sales.sam_meat_runtime.send_meat_estimated_quote_to_chatwoot")
    @patch("modules.sales.sam_meat_runtime.build_meat_estimated_quote_packet")
    @patch("modules.sales.sam_meat_runtime.record_sales_lead_event")
    @patch("modules.sales.sam_meat_runtime.record_meat_fulfillment_event")
    @patch("modules.sales.sam_meat_runtime.get_sales_lead_preorder_contract")
    @patch("modules.sales.sam_meat_runtime.record_sam_meat_intake_lead")
    def test_quote_request_uses_quote_gate_even_when_contract_status_is_stale(
        self,
        mock_record,
        mock_contract,
        mock_fulfillment,
        mock_event,
        mock_quote,
        mock_document_send,
    ):
        mock_record.return_value = ({
            "success": True,
            "status": "ok",
            "lead_id": "OSK-SALES-LEAD-STale",
            "contract": {},
        }, 200)
        mock_contract.return_value = ({
            "success": True,
            "contract": {"contract_status": "needs_owner_confirmation"},
        }, 200)
        mock_quote.return_value = ({
            "success": True,
            "quote_safe": True,
            "sam_preparing_message": "I am preparing your estimated quote now and will send it through shortly.",
        }, 200)
        mock_document_send.return_value = ({
            "success": True,
            "status": "estimated_quote_chatwoot_accepted_unverified",
            "sent": False,
            "chatwoot_accepted": True,
        }, 200)
        sender = Mock(return_value={"message_id": "123", "conversation_id": "1808"})

        result, status_code = sam_meat_runtime.handle_sam_meat_chatwoot_inbound(
            inbound_payload(content="Please send the estimated quote now."),
            environ={
                "SAM_MEAT_BACKEND_AUTOREPLY_ENABLED": "1",
                "MEAT_SALES_DOCUMENT_AUTOSEND_ENABLED": "1",
            },
            chatwoot_sender=sender,
        )

        self.assertEqual(status_code, 200)
        self.assertEqual(result["send_status"], "sent")
        self.assertTrue(result["sam_decision"]["document_send_requested"])
        self.assertTrue(result["sam_decision"]["document_force_resend_requested"])
        self.assertIn("preparing your estimated quote", result["sam_decision"]["reply_text"])
        self.assertNotIn("farm must confirm", result["sam_decision"]["reply_text"])
        mock_document_send.assert_called_once()
        self.assertTrue(mock_document_send.call_args.args[1]["force_resend"])

    @patch("modules.sales.sam_meat_runtime.record_meat_fulfillment_event")
    @patch("modules.sales.sam_meat_runtime.get_active_sales_lead_by_conversation")
    @patch("modules.sales.sam_meat_runtime.get_sales_lead_preorder_contract")
    @patch("modules.sales.sam_meat_runtime.record_sam_meat_intake_lead")
    def test_handle_inbound_records_delivery_address_capture_when_ready(self, mock_record, mock_contract, mock_active, mock_fulfillment):
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
        mock_active.return_value = ({"success": False, "status": "active_sales_lead_by_conversation_not_found"}, 404)
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

    @patch("modules.sales.sam_meat_runtime.get_active_sales_lead_by_conversation")
    @patch("modules.sales.sam_meat_runtime.get_sales_lead_preorder_contract")
    @patch("modules.sales.sam_meat_runtime.record_sam_meat_intake_lead")
    def test_new_inbound_without_active_context_gets_fresh_lead_id(self, mock_record, mock_contract, mock_active):
        mock_active.return_value = ({"success": False, "status": "active_sales_lead_by_conversation_not_found"}, 404)
        mock_record.return_value = ({
            "success": True,
            "status": "ok",
            "lead_id": "OSK-SALES-LEAD-FRESH",
            "contract": {},
        }, 201)
        mock_contract.return_value = ({
            "success": True,
            "contract": {"contract_status": "needs_owner_confirmation"},
        }, 200)

        result, status_code = sam_meat_runtime.handle_sam_meat_chatwoot_inbound(
            inbound_payload(id=695457280, created_at="2026-06-17T00:32:40Z"),
            environ={"SAM_MEAT_BACKEND_AUTOREPLY_ENABLED": "0"},
        )

        self.assertEqual(status_code, 200)
        lead_payload = mock_record.call_args.args[0]
        self.assertTrue(lead_payload["lead_id"].startswith("OSK-SALES-LEAD-"))
        self.assertNotEqual(lead_payload["lead_id"], "OSK-SALES-LEAD-FRESH")
        self.assertEqual(len(lead_payload["lead_id"]), len("OSK-SALES-LEAD-1234567890ABCDEF"))
        self.assertEqual(result["inbound"]["message_id"], "695457280")

    @patch("modules.sales.sam_meat_runtime.record_meat_fulfillment_event")
    @patch("modules.sales.sam_meat_runtime.get_active_sales_lead_by_conversation")
    @patch("modules.sales.sam_meat_runtime.get_sales_lead_preorder_contract")
    @patch("modules.sales.sam_meat_runtime.record_sam_meat_intake_lead")
    def test_address_reply_inherits_existing_conversation_meat_context(self, mock_record, mock_contract, mock_active, mock_fulfillment):
        mock_active.return_value = ({
            "success": True,
            "lead": {
                "lead_id": "OSK-SALES-LEAD-CONTEXT",
                "chatwoot_conversation_id": "1808",
                "interest": {
                    "product_type": "half_carcass",
                    "cut_set": "Set A",
                    "location": "Riversdale",
                    "delivery_or_collection": "delivery",
                },
            },
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
    @patch("modules.sales.sam_meat_runtime.get_active_sales_lead_by_conversation")
    @patch("modules.sales.sam_meat_runtime.get_sales_lead_preorder_contract")
    @patch("modules.sales.sam_meat_runtime.record_sam_meat_intake_lead")
    def test_conversation_context_uses_active_progressed_lead_lookup(self, mock_record, mock_contract, mock_active, mock_fulfillment):
        mock_active.return_value = ({
            "success": True,
            "lead": {
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
    @patch("modules.sales.sam_meat_runtime.get_active_sales_lead_by_conversation")
    @patch("modules.sales.sam_meat_runtime.get_sales_lead_preorder_contract")
    @patch("modules.sales.sam_meat_runtime.record_sam_meat_intake_lead")
    def test_customer_yes_after_followup_sent_records_booking_confirmation(self, mock_record, mock_contract, mock_active, mock_confirmation):
        mock_active.return_value = ({
            "success": True,
            "lead": {
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
            },
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

    @patch("modules.sales.sam_meat_runtime.record_sales_lead_event")
    @patch("modules.sales.sam_meat_runtime.record_customer_booking_confirmation")
    @patch("modules.sales.sam_meat_runtime.get_active_sales_lead_by_conversation")
    @patch("modules.sales.sam_meat_runtime.get_sales_lead_preorder_contract")
    @patch("modules.sales.sam_meat_runtime.record_sam_meat_intake_lead")
    def test_customer_yes_after_followup_sends_deposit_instruction_when_bank_details_configured(
        self,
        mock_record,
        mock_contract,
        mock_active,
        mock_confirmation,
        mock_event,
    ):
        mock_active.return_value = ({
            "success": True,
            "lead": {
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
            },
        }, 200)
        mock_record.return_value = ({
            "success": True,
            "status": "ok",
            "lead_id": "OSK-SALES-LEAD-PROGRESSED",
            "contract": {},
        }, 201)
        mock_contract.return_value = ({
            "success": True,
            "contract": {
                "contract_status": "owner_money_path_ready",
                "lead_summary": {
                    "buyer_or_contact": "Charl N",
                    "product": "Half Carcass",
                    "cut_set": "Set A",
                    "location": "Riversdale",
                },
                "required_before_money_path": {
                    "price_per_kg": "R130/kg",
                    "available_week": "next available week",
                    "estimated_weight_or_size": "19-21kg",
                    "deposit_amount_or_rule": "50% deposit to confirm",
                    "payment_method": "EFT",
                    "delivery_or_collection": "collection",
                    "owner_final_approval": "Yes",
                },
            },
        }, 200)
        mock_confirmation.return_value = ({
            "success": True,
            "status": "ok",
            "records_customer_booking_confirmation": True,
        }, 201)

        result, status_code = sam_meat_runtime.handle_sam_meat_chatwoot_inbound(
            inbound_payload(content="Yes, please proceed with the final booking review."),
            environ={
                "SAM_MEAT_BACKEND_AUTOREPLY_ENABLED": "0",
                "BANK_ACCOUNT_NAME": "Amadeus Farm",
                "BANK_NAME": "Test Bank",
                "BANK_ACCOUNT_NUMBER": "123456789",
                "BANK_BRANCH_CODE": "123456",
                "BANK_ACCOUNT_TYPE": "Cheque",
            },
        )

        self.assertEqual(status_code, 200)
        self.assertIn("Account name: Amadeus Farm", result["sam_decision"]["reply_text"])
        self.assertIn("Reference: RESSED", result["sam_decision"]["reply_text"])
        self.assertIn("about R1,300.00", result["sam_decision"]["reply_text"])
        self.assertEqual(
            result["sam_decision"]["deposit_payment_instruction"]["status"],
            "deposit_payment_instruction_ready",
        )
        event_types = [call.args[1]["event_type"] for call in mock_event.call_args_list]
        self.assertIn("deposit_followup_needed", event_types)

    @patch("modules.sales.sam_meat_runtime.record_meat_deposit_event")
    @patch("modules.sales.sam_meat_runtime.get_meat_ops_status")
    @patch("modules.sales.sam_meat_runtime.get_active_sales_lead_by_conversation")
    @patch("modules.sales.sam_meat_runtime.get_sales_lead_preorder_contract")
    @patch("modules.sales.sam_meat_runtime.record_sam_meat_intake_lead")
    def test_customer_pop_message_records_unverified_pop_without_bank_gate(
        self,
        mock_record,
        mock_contract,
        mock_active,
        mock_ops,
        mock_deposit,
    ):
        mock_active.return_value = ({
            "success": True,
            "lead": {
                "lead_id": "OSK-SALES-LEAD-PROGRESSED",
                "chatwoot_conversation_id": "1808",
                "latest_event": "deposit_followup_needed",
                "interest": {
                    "product_type": "half_carcass",
                    "cut_set": "Set A",
                    "location": "Riversdale",
                    "delivery_or_collection": "collection",
                    "timing": "next available week",
                    "payment_method": "EFT",
                },
            },
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
        mock_ops.return_value = ({
            "success": True,
            "reservations": [{
                "reservation_id": "OSK-MEAT-RES-1",
                "status": "half_reserved_pending_pair",
                "effective_status": "half_reserved_pending_pair",
                "created_at": "2026-06-17T03:00:00Z",
            }],
        }, 200)
        mock_deposit.return_value = ({
            "success": True,
            "status": "pop_received_unverified",
        }, 201)

        result, status_code = sam_meat_runtime.handle_sam_meat_chatwoot_inbound(
            inbound_payload(content="I paid and sent POP ref POP-12345."),
            environ={"SAM_MEAT_BACKEND_AUTOREPLY_ENABLED": "0"},
        )

        self.assertEqual(status_code, 200)
        self.assertTrue(result["pop_capture"]["recorded"])
        self.assertIn("only moves forward once the money reflects", result["sam_decision"]["reply_text"])
        mock_deposit.assert_called_once()
        self.assertEqual(mock_deposit.call_args.args[0], "OSK-SALES-LEAD-PROGRESSED")
        self.assertEqual(mock_deposit.call_args.args[1]["reservation_id"], "OSK-MEAT-RES-1")
        self.assertEqual(mock_deposit.call_args.args[1]["event_type"], "pop_received_unverified")
        self.assertEqual(mock_deposit.call_args.args[1]["payment_reference"], "POP-12345")


if __name__ == "__main__":
    unittest.main()
