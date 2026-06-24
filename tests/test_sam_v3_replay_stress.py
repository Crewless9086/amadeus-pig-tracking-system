import unittest
from unittest.mock import Mock, patch

from modules.sales import sam_meat_runtime
from tests.test_sam_meat_runtime import inbound_payload


class SamV3ReplayStressTests(unittest.TestCase):
    def _run_sam_v3_case(
        self,
        *,
        content,
        agent_raw,
        active_interest=None,
        contract_status="needs_owner_confirmation",
        extra_env=None,
    ):
        lead_id = "OSK-SALES-LEAD-V3-STRESS"
        active_interest = active_interest if isinstance(active_interest, dict) else {}
        with patch("modules.sales.sam_meat_runtime.get_active_sales_lead_by_conversation") as mock_active, \
            patch("modules.sales.sam_meat_runtime.get_sales_lead_preorder_contract") as mock_contract, \
            patch("modules.sales.sam_meat_runtime.record_sam_meat_intake_lead") as mock_record, \
            patch("modules.sales.sam_meat_runtime.record_meat_fulfillment_event") as mock_fulfillment:

            if active_interest:
                mock_active.return_value = ({
                    "success": True,
                    "lead": {
                        "lead_id": lead_id,
                        "chatwoot_conversation_id": "1820",
                        "interest": active_interest,
                    },
                }, 200)
            else:
                mock_active.return_value = ({"success": False, "status": "not_found"}, 404)
            mock_record.return_value = ({
                "success": True,
                "status": "ok",
                "lead_id": lead_id,
                "contract": {},
            }, 201)
            mock_contract.return_value = ({
                "success": True,
                "contract": {"contract_status": contract_status},
            }, 200)
            mock_fulfillment.return_value = ({"success": True, "status": "ok"}, 201)

            env = {
                "SAM_MEAT_BACKEND_AGENT_V3_ENABLED": "1",
                "SAM_MEAT_BACKEND_LLM_ENABLED": "1",
                "SAM_MEAT_BACKEND_LLM_MODEL": "gpt-5",
                "OPENAI_API_KEY": "test-key",
                "SAM_MEAT_BACKEND_AUTOREPLY_ENABLED": "0",
            }
            env.update(extra_env if isinstance(extra_env, dict) else {})
            return sam_meat_runtime.handle_sam_meat_chatwoot_inbound(
                inbound_payload(
                    content=content,
                    conversation={
                        "id": 1820,
                        "inbox": {"channel_type": "Channel::Whatsapp"},
                        "custom_attributes": {
                            "source_campaign_id": "BEACON-MEAT-STRESS",
                            "source_post_text": "Farm-raised Amadeus pork freezer packs for Riversdale families.",
                            "source_call_to_action": "Message Sam to find the right freezer option.",
                        },
                    },
                ),
                environ=env,
                llm_agent_v3_decider=Mock(return_value=agent_raw),
            )

    def test_replay_stress_v3_handles_warm_post_reply_address_and_no_intent(self):
        scenarios = [
            {
                "content": "Yummy",
                "agent_raw": {
                    "intent": "warm_campaign_interest",
                    "should_reply": True,
                    "reply_text": "Yummy indeed. That post is about our Amadeus Farm pork freezer options for Riversdale families. Would you like the half-carcass option or the smaller cut-set route?",
                    "facts_patch": {"product_type": "unknown"},
                    "next_action": "soft_qualify_interest",
                    "confidence": 0.96,
                    "risk_flags": [],
                },
                "must_include": "Yummy indeed",
                "must_not_include": "half carcass, full carcass, or a cut-set pack",
            },
            {
                "content": "Blue gate 12 Test Street Riversdale eft thanks",
                "active_interest": {
                    "product_type": "half_carcass",
                    "cut_set": "Set A",
                    "location": "Riversdale",
                    "delivery_or_collection": "delivery",
                },
                "agent_raw": {
                    "intent": "meat_preorder",
                    "should_reply": True,
                    "reply_text": "Got it, I have the Riversdale delivery note with the blue gate. I will keep the payment route as EFT and keep the next step clear once the farm gate is ready.",
                    "facts_patch": {
                        "delivery_address_line_1": "12 Test Street",
                        "delivery_town": "Riversdale",
                        "delivery_notes": "Blue gate",
                        "payment_method": "EFT",
                    },
                    "next_action": "request_missing_fact",
                    "confidence": 0.93,
                    "risk_flags": [],
                },
                "must_include": "blue gate",
                "must_not_include": "Please send the delivery street address",
            },
            {
                "content": "Nice thanks",
                "agent_raw": {
                    "intent": "general",
                    "should_reply": False,
                    "reply_text": "",
                    "facts_patch": {},
                    "next_action": "no_reply",
                    "confidence": 0.89,
                    "risk_flags": [],
                },
                "must_include": "",
                "expect_no_reply": True,
            },
        ]

        for scenario in scenarios:
            with self.subTest(content=scenario["content"]):
                result, status_code = self._run_sam_v3_case(**{
                    key: value for key, value in scenario.items()
                    if key in {"content", "agent_raw", "active_interest"}
                })
                self.assertEqual(status_code, 200)
                self.assertEqual(result["agent_decision"]["version"], "v3")
                self.assertEqual(result["agent_decision"]["status"], "agent_v3_decision_accepted")
                if scenario.get("expect_no_reply"):
                    self.assertFalse(result["sam_decision"]["should_reply"])
                    self.assertEqual(result["sam_decision"]["reply_text"], "")
                else:
                    self.assertIn(scenario["must_include"], result["sam_decision"]["reply_text"])
                    self.assertNotIn(scenario.get("must_not_include", "__never__"), result["sam_decision"]["reply_text"])

    def test_public_sales_agent_accepts_human_beacon_reply_over_form_flow(self):
        result, status_code = self._run_sam_v3_case(
            content="Hi, I saw the pork half-carcass post and want more info for Riversdale.",
            agent_raw={
                "intent": "warm_campaign_interest",
                "should_reply": True,
                "reply_text": (
                    "Great, you are in the right place. That post is about Amadeus Farm pork for freezer orders around Riversdale. "
                    "For most homes I would start with the half-carcass route, then we match the cut style before the farm confirms price and timing. "
                    "Are you buying mainly for your household freezer?"
                ),
                "facts_patch": {
                    "product_type": "half_carcass",
                    "location": "Riversdale",
                },
                "missing_fields": ["cut_set", "delivery_or_collection", "timing"],
                "next_action": "soft_qualify_interest",
                "confidence": 0.97,
                "risk_flags": [],
            },
        )

        reply = result["sam_decision"]["reply_text"]
        self.assertEqual(status_code, 200)
        self.assertTrue(result["agent_decision"]["used"])
        self.assertIn("you are in the right place", reply)
        self.assertIn("household freezer", reply)
        self.assertNotIn("Would you prefer collection or delivery", reply)
        self.assertNotIn("For delivery", reply)

    def test_public_sales_agent_rejects_robotic_llm_reply_and_uses_better_fallback(self):
        result, status_code = self._run_sam_v3_case(
            content="Ok thanks",
            active_interest={
                "product_type": "half_carcass",
                "cut_set": "Set A",
                "location": "Riversdale",
            },
            agent_raw={
                "intent": "meat_preorder",
                "should_reply": True,
                "reply_text": "I am still with you on the pork preorder. Would you prefer collection or delivery?",
                "facts_patch": {},
                "next_action": "request_missing_fact",
                "confidence": 0.92,
                "risk_flags": [],
            },
        )

        reply = result["sam_decision"]["reply_text"]
        self.assertEqual(status_code, 200)
        self.assertFalse(result["agent_decision"]["used"])
        self.assertEqual(result["agent_decision"]["status"], "agent_v3_reply_blocked")
        self.assertIn("robotic_public_reply", result["agent_decision"]["risk_flags"])
        self.assertNotIn("I am still with you", reply)

    @patch("modules.sales.sam_meat_runtime.get_active_sales_lead_by_conversation")
    @patch("modules.sales.sam_meat_runtime.get_sales_lead_preorder_contract")
    @patch("modules.sales.sam_meat_runtime.record_sam_meat_intake_lead")
    def test_code_intro_is_rewritten_before_public_send(self, mock_record, mock_contract, mock_active):
        mock_active.return_value = ({"success": False, "status": "not_found"}, 404)
        mock_record.return_value = ({
            "success": True,
            "status": "ok",
            "lead_id": "OSK-SALES-LEAD-REWRITE",
            "contract": {},
        }, 201)
        mock_contract.return_value = ({
            "success": True,
            "contract": {"contract_status": "needs_owner_confirmation"},
        }, 200)

        result, status_code = sam_meat_runtime.handle_sam_meat_chatwoot_inbound(
            inbound_payload(content="Hi"),
            environ={
                "SAM_MEAT_BACKEND_AGENT_V3_ENABLED": "1",
                "SAM_MEAT_BACKEND_LLM_ENABLED": "1",
                "SAM_MEAT_BACKEND_LLM_MODEL": "gpt-5",
                "OPENAI_API_KEY": "test-key",
                "SAM_MEAT_BACKEND_AUTOREPLY_ENABLED": "0",
            },
            llm_agent_v3_decider=Mock(return_value={}),
            llm_reply_rewriter=Mock(return_value={
                "reply_text": "Hi, I am Sam from Amadeus Farm. Are you looking for pork for your freezer, or do you need farm information first?",
                "confidence": 0.92,
            }),
        )

        reply = result["sam_decision"]["reply_text"]
        self.assertEqual(status_code, 200)
        self.assertEqual(result["sam_decision"]["reply_source"], "llm_rewritten_code_fallback")
        self.assertEqual(result["sam_decision"]["rewrite_status"], "rewritten")
        self.assertNotIn("Pork meat sales: Half carcass", reply)
        self.assertNotIn("Tell me what you are looking for", reply)

    @patch("modules.sales.sam_meat_runtime.get_active_sales_lead_by_conversation")
    @patch("modules.sales.sam_meat_runtime.record_sam_meat_intake_lead")
    def test_code_sales_reply_is_withheld_when_rewriter_unavailable(self, mock_record, mock_active):
        mock_active.return_value = ({"success": False, "status": "not_found"}, 404)
        mock_record.return_value = ({
            "success": True,
            "status": "ok",
            "lead_id": "OSK-SALES-LEAD-NO-REWRITE",
            "contract": {},
        }, 201)

        result, status_code = sam_meat_runtime.handle_sam_meat_chatwoot_inbound(
            inbound_payload(content="Hi"),
            environ={
                "SAM_MEAT_BACKEND_AGENT_V3_ENABLED": "1",
                "SAM_MEAT_BACKEND_LLM_ENABLED": "0",
                "SAM_MEAT_BACKEND_AUTOREPLY_ENABLED": "0",
            },
            llm_agent_v3_decider=Mock(return_value={}),
        )

        self.assertEqual(status_code, 200)
        self.assertFalse(result["sam_decision"]["should_reply"])
        self.assertEqual(result["sam_decision"]["reply_text"], "")
        self.assertEqual(result["sam_decision"]["reply_source"], "code_reply_withheld_llm_rewrite_unavailable")

    def test_replay_stress_v3_rejects_payment_booking_and_money_hallucinations(self):
        unsafe_outputs = [
            "Your payment is confirmed and the order is booked.",
            "It will be R2,600 and your delivery is scheduled.",
            "The butcher slot is confirmed for Friday.",
        ]
        for reply_text in unsafe_outputs:
            with self.subTest(reply_text=reply_text):
                result, status_code = self._run_sam_v3_case(
                    content="Can we go ahead?",
                    agent_raw={
                        "intent": "meat_preorder",
                        "should_reply": True,
                        "reply_text": reply_text,
                        "facts_patch": {"product_type": "half_carcass"},
                        "next_action": "soft_qualify_interest",
                        "confidence": 0.97,
                        "risk_flags": [],
                    },
                )
                self.assertEqual(status_code, 200)
                self.assertFalse(result["agent_decision"]["used"])
                self.assertEqual(result["agent_decision"]["status"], "agent_v3_reply_blocked")
                self.assertNotEqual(result["sam_decision"]["reply_text"], reply_text)

    def test_replay_stress_v3_quote_request_is_overridden_by_document_gate(self):
        with patch("modules.sales.sam_meat_runtime.build_meat_estimated_quote_packet") as mock_quote:
            mock_quote.return_value = ({
                "success": True,
                "quote_safe": True,
                "sam_preparing_message": "I am preparing your estimated quote now and will send it through shortly.",
            }, 200)

            result, status_code = self._run_sam_v3_case(
                content="Please send the estimated quote now.",
                active_interest={
                    "product_type": "half_carcass",
                    "cut_set": "Set A",
                    "location": "Riversdale",
                    "delivery_or_collection": "delivery",
                    "delivery_address_line_1": "12 Test Street",
                    "timing": "next available farm run",
                    "payment_method": "EFT",
                },
                contract_status="owner_money_path_ready",
                extra_env={"MEAT_SALES_DOCUMENT_AUTOSEND_ENABLED": "1"},
                agent_raw={
                    "intent": "document_request",
                    "should_reply": True,
                    "reply_text": "Sure, I will get that ready for you.",
                    "facts_patch": {},
                    "next_action": "document_request_gate",
                    "confidence": 0.96,
                    "risk_flags": [],
                },
            )

        self.assertEqual(status_code, 200)
        self.assertTrue(result["agent_decision"]["used"])
        self.assertTrue(result["sam_decision"]["document_send_requested"])
        self.assertIn("preparing your estimated quote", result["sam_decision"]["reply_text"])
        self.assertNotEqual(result["sam_decision"]["reply_text"], "Sure, I will get that ready for you.")

    @patch("modules.sales.sam_meat_runtime.record_meat_deposit_event")
    @patch("modules.sales.sam_meat_runtime.get_meat_ops_status")
    def test_replay_stress_v3_pop_message_is_overridden_by_payment_gate(self, mock_ops, mock_deposit):
        mock_ops.return_value = ({
            "success": True,
            "reservations": [{
                "reservation_id": "OSK-MEAT-RES-V3",
                "status": "deposit_pending",
                "effective_status": "deposit_pending",
                "created_at": "2026-06-23T08:00:00Z",
            }],
        }, 200)
        mock_deposit.return_value = ({
            "success": True,
            "status": "pop_received_unverified",
        }, 201)

        result, status_code = self._run_sam_v3_case(
            content="I paid and sent POP ref TEST123.",
            active_interest={
                "product_type": "half_carcass",
                "cut_set": "Set A",
                "location": "Riversdale",
                "delivery_or_collection": "delivery",
                "delivery_address_line_1": "12 Test Street",
                "timing": "next available farm run",
                "payment_method": "EFT",
            },
            contract_status="owner_money_path_ready",
            agent_raw={
                "intent": "payment",
                "should_reply": True,
                "reply_text": "Thanks, I have your POP and will keep your order moving.",
                "facts_patch": {},
                "next_action": "record_unverified_pop",
                "confidence": 0.94,
                "risk_flags": [],
            },
        )

        self.assertEqual(status_code, 200)
        self.assertTrue(result["agent_decision"]["used"])
        self.assertTrue(result["pop_capture"]["recorded"])
        self.assertIn("only moves forward once the money reflects", result["sam_decision"]["reply_text"])
        self.assertNotIn("order moving", result["sam_decision"]["reply_text"])
        mock_deposit.assert_called_once()


if __name__ == "__main__":
    unittest.main()
