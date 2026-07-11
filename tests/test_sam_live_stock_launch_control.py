import unittest

from modules.sales import sam_live_stock_launch_control as launch


def review_inputs(message="I need 2 weaners in Riversdale next week."):
    inbound = {
        "conversation_id": "2401",
        "message_id": "901",
        "customer_name": "Charl N",
        "customer_phone": "+27820000000",
        "channel": "chatwoot_whatsapp",
        "content": message,
    }
    facts = {
        "sales_lane": "live_stock_sales",
        "category": "weaner",
        "quantity": 2,
        "sex": "any",
        "location": "Riversdale",
        "timing": "next week",
    }
    decision = {
        "sales_lane": "live_stock_sales",
        "missing_fields": [],
        "conversation_goal": "buy_live_stock: 2 weaner",
        "conversation_stage": "quote",
        "next_action": "generate_quote",
        "conversation_plan": {
            "goal": "buy_live_stock: 2 weaner",
            "stage": "quote",
            "next_action": "generate_quote",
        },
        "owner_action_packet": {
            "next_action": "generate_quote",
            "status": "ready_for_owner_quote_prepare",
            "label": "Prepare latest quote send",
            "detail": "Use order ORD-1 to generate or verify the latest quote before any customer send.",
            "order_id": "ORD-1",
            "owner_gate_required": True,
        },
        "blockers": [],
        "suggested_reply_text": "I can check the current weaner list for Riversdale handover next week.",
        "reply_source": "deterministic_read_only_guard",
        "match_packet": {
            "exact_match_count": 2,
            "match_status": "exact_match_available",
            "matched_sample": [
                {"pig_id": "W-1043", "current_weight_kg": 12.4},
                {"pig_id": "W-1051", "current_weight_kg": 13.1},
            ],
        },
        "price_answer_packet": {
            "can_answer_price": True,
            "unit_price": 500,
            "estimated_total": 1000,
            "requested_quantity": 2,
            "pricing": {"source": "supabase"},
        },
    }
    return inbound, facts, decision


class SamLiveStockLaunchControlTests(unittest.TestCase):
    def test_review_event_is_append_only_no_authority_shape(self):
        inbound, facts, decision = review_inputs()
        review = {"score": 98, "confidence_target": 96, "safe_to_send": True, "recommended_action": "owner_review_send_candidate"}

        event = launch.build_sam_live_stock_review_event(inbound, facts, decision, review)

        self.assertTrue(event["review_event_id"].startswith("SAM-LIVE-REVIEW-"))
        self.assertEqual(event["chatwoot_conversation_id"], "2401")
        self.assertEqual(event["score"], 98)
        self.assertFalse(event["sends_customer_message"])
        self.assertFalse(event["calls_chatwoot"])
        self.assertFalse(event["calls_telegram"])
        self.assertFalse(event["reserves_stock"])
        self.assertFalse(event["writes_farm_data"])

    def test_review_event_preserves_multiline_reply_excerpt(self):
        inbound, facts, decision = review_inputs()
        decision["suggested_reply_text"] = (
            "Current SAM Live price estimate:\n"
            "- 2 x Female Weaner, 10-14 kg: R500 each\n"
            "- Estimated total: R1,000\n"
            "- This is not a reservation."
        )

        event = launch.build_sam_live_stock_review_event(
            inbound,
            facts,
            decision,
            {"score": 100, "recommended_action": "owner_review_send_candidate"},
        )

        self.assertIn("\n- 2 x Female", event["sam_reply_excerpt"])
        self.assertIn("\n- Estimated total", event["sam_reply_excerpt"])

    def test_owner_review_card_surfaces_delivery_estimate_fields(self):
        inbound, facts, decision = review_inputs("Can you deliver to Albertinia? It is 30 km one way.")
        facts.update({
            "transport_expectation": "delivery_requested",
            "delivery_destination": "Albertinia",
            "delivery_one_way_km": 30,
        })
        decision["delivery_estimate_packet"] = {
            "delivery_requested": True,
            "destination": "Albertinia",
            "one_way_km": 30,
            "delivery_fee_estimate": 600,
            "total_with_livestock_and_delivery": 1600,
            "owner_override_warning": "Delivery is an owner-reviewed estimate only.",
        }
        event = launch.build_sam_live_stock_review_event(
            inbound,
            facts,
            decision,
            {"score": 99, "confidence_target": 96, "safe_to_send": True, "recommended_action": "owner_review_send_candidate"},
        )

        packet = launch.build_sam_live_stock_owner_review_packet(event)
        text = packet["telegram_packet"]["text"]

        self.assertIn("Delivery requested: yes", text)
        self.assertIn("Delivery destination: Albertinia", text)
        self.assertIn("One-way km: 30 km", text)
        self.assertIn("Delivery estimate: R600", text)
        self.assertIn("Total incl delivery: R1,600", text)
        self.assertIn("Owner override: Delivery is an owner-reviewed estimate only.", text)
        self.assertIn("Flags: delivery estimate owner review", text)

    def test_record_review_event_requires_database_url(self):
        inbound, facts, decision = review_inputs()
        event = launch.build_sam_live_stock_review_event(inbound, facts, decision)

        result, status = launch.record_sam_live_stock_review_event(event, database_url="")

        self.assertEqual(status, 503)
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "database_url_not_configured")

    def test_telegram_escalation_send_is_env_gated(self):
        calls = []
        packet = {"telegram_packet": {"text": "Escalation", "reply_markup": {"inline_keyboard": []}}}

        result, status = launch.send_sam_live_stock_telegram_escalation(
            packet,
            environ={},
            telegram_sender=lambda *args: calls.append(args),
        )

        self.assertEqual(status, 409)
        self.assertEqual(result["status"], "sam_live_stock_telegram_send_disabled")
        self.assertEqual(calls, [])

    def test_telegram_escalation_send_uses_owner_chat_when_enabled(self):
        calls = []

        def sender(token, chat_id, text, reply_markup):
            calls.append((token, chat_id, text, reply_markup))
            return {"ok": True, "result": {"message_id": 123}}

        result, status = launch.send_sam_live_stock_telegram_escalation(
            {"telegram_packet": {"text": "Escalation", "reply_markup": {"inline_keyboard": []}}},
            environ={
                "SAM_LIVE_STOCK_TELEGRAM_ESCALATION_SEND_ENABLED": "1",
                "SAM_LIVE_STOCK_TELEGRAM_BOT_TOKEN": "token",
                "SAM_LIVE_STOCK_TELEGRAM_OWNER_CHAT_ID": "555",
            },
            telegram_sender=sender,
        )

        self.assertEqual(status, 200)
        self.assertTrue(result["success"])
        self.assertTrue(result["calls_telegram"])
        self.assertEqual(calls[0][1], "555")

    def test_new_lead_telegram_send_has_separate_gate(self):
        inbound, facts, decision = review_inputs()
        event = launch.build_sam_live_stock_review_event(
            inbound,
            facts,
            decision,
            {"score": 90, "recommended_action": "ask_one_missing_fact"},
        )
        calls = []

        disabled, disabled_status = launch.send_sam_live_stock_new_lead_telegram(
            event,
            environ={},
            telegram_sender=lambda *args: calls.append(args),
        )

        self.assertEqual(disabled_status, 409)
        self.assertEqual(disabled["status"], "sam_live_stock_new_lead_telegram_send_disabled")
        self.assertEqual(calls, [])

        sent, sent_status = launch.send_sam_live_stock_new_lead_telegram(
            event,
            environ={
                "SAM_LIVE_STOCK_TELEGRAM_NEW_LEAD_SEND_ENABLED": "1",
                "SAM_LIVE_STOCK_TELEGRAM_BOT_TOKEN": "token",
                "SAM_LIVE_STOCK_TELEGRAM_OWNER_CHAT_ID": "555",
            },
            telegram_sender=lambda token, chat_id, text, reply_markup: calls.append((token, chat_id, text, reply_markup)) or {"ok": True},
        )

        self.assertEqual(sent_status, 200)
        self.assertTrue(sent["success"])
        self.assertEqual(sent["status"], "sam_live_stock_new_lead_telegram_sent")
        self.assertEqual(calls[0][1], "555")
        self.assertIn("SAM Live - New lead", calls[0][2])
        self.assertIn("Conversation: 2401", calls[0][2])
        self.assertIn("Wants: qty=2, category=weaner", calls[0][2])
        self.assertIn("Customer message:", calls[0][2])
        self.assertNotIn("Action:", calls[0][2])

    def test_owner_review_telegram_send_has_approve_button_and_multiline_draft(self):
        inbound, facts, decision = review_inputs()
        decision["suggested_reply_text"] = (
            "Current SAM Live price estimate:\n"
            "- 2 x Female Weaner, 10-14 kg: R500 each\n"
            "- Estimated total: R1,000\n"
            "- This is not a reservation."
        )
        event = launch.build_sam_live_stock_review_event(
            inbound,
            facts,
            decision,
            {"score": 99, "confidence_target": 96, "safe_to_send": True, "recommended_action": "owner_review_send_candidate"},
        )
        calls = []

        disabled, disabled_status = launch.send_sam_live_stock_owner_review_telegram(
            event,
            environ={},
            telegram_sender=lambda *args: calls.append(args),
        )

        self.assertEqual(disabled_status, 409)
        self.assertEqual(disabled["status"], "sam_live_stock_owner_review_telegram_send_disabled")
        self.assertEqual(calls, [])

        sent, sent_status = launch.send_sam_live_stock_owner_review_telegram(
            event,
            environ={
                "SAM_LIVE_STOCK_TELEGRAM_OWNER_REVIEW_SEND_ENABLED": "1",
                "SAM_LIVE_STOCK_TELEGRAM_BOT_TOKEN": "token",
                "SAM_LIVE_STOCK_TELEGRAM_OWNER_CHAT_ID": "555",
            },
            telegram_sender=lambda token, chat_id, text, reply_markup: calls.append((token, chat_id, text, reply_markup)) or {"ok": True},
        )

        self.assertEqual(sent_status, 200)
        self.assertTrue(sent["success"])
        self.assertEqual(sent["status"], "sam_live_stock_owner_review_telegram_sent")
        self.assertIn("SAM Live - Charl N", calls[0][2])
        self.assertIn("Intent: buy live stock: 2 weaner", calls[0][2])
        self.assertIn("Stage: quote", calls[0][2])
        self.assertIn("Open order/quote: ORD-1 - quote prepare ready", calls[0][2])
        self.assertIn("Next: generate quote", calls[0][2])
        self.assertIn("Prepared: Prepare latest quote send - ready for owner quote prepare - ORD-1", calls[0][2])
        self.assertIn("Wants: 2 any weaner, next week, Riversdale", calls[0][2])
        self.assertIn("Stock: 2 matches (W-1043 12.4kg, W-1051 13.1kg)", calls[0][2])
        self.assertIn("Price: R500 each - R1,000 total - source supabase", calls[0][2])
        self.assertIn("Missing: none", calls[0][2])
        self.assertIn("Reply: Fact-aware fallback", calls[0][2])
        self.assertIn("Draft reply:", calls[0][2])
        self.assertIn("\n- 2 x Female Weaner", calls[0][2])
        buttons = calls[0][3]["inline_keyboard"]
        self.assertEqual(buttons[0][0]["text"], "Approve Send")
        self.assertTrue(buttons[0][0]["callback_data"].startswith("sam_live_review_approve:SAM-LIVE-REVIEW-"))
        self.assertEqual(buttons[1][0]["text"], "Edit in Chatwoot")
        self.assertEqual(buttons[1][0]["url"], "https://app.chatwoot.com/app/accounts/147387/conversations/2401")
        button_texts = [button["text"] for row in buttons for button in row]
        self.assertIn("Keep Human", button_texts)
        self.assertIn("Prepare Quote", button_texts)
        self.assertIn("No Reply Needed", button_texts)
        self.assertIn("Close", button_texts)
        callback_data = [button.get("callback_data", "") for row in buttons for button in row]
        self.assertTrue(any(item.startswith("sam_live_review_prepare_quote:SAM-LIVE-REVIEW-") for item in callback_data))
        self.assertTrue(any(item.startswith("sam_live_review_no_reply:SAM-LIVE-REVIEW-") for item in callback_data))

    def test_owner_review_card_v2_surfaces_relevant_prepared_action_buttons(self):
        inbound, facts, decision = review_inputs()
        event = launch.build_sam_live_stock_review_event(
            inbound,
            facts,
            decision,
            {"score": 99, "confidence_target": 96, "safe_to_send": True, "recommended_action": "owner_review_send_candidate"},
        )

        quote_packet = launch.build_sam_live_stock_owner_review_packet(event)

        self.assertEqual(quote_packet["version"], "sam_live_stock_owner_review_packet_v2")
        quote_buttons = [button["text"] for row in quote_packet["telegram_packet"]["reply_markup"]["inline_keyboard"] for button in row]
        self.assertIn("Approve Send", quote_buttons)
        self.assertIn("Edit in Chatwoot", quote_buttons)
        self.assertIn("Keep Human", quote_buttons)
        self.assertIn("Prepare Quote", quote_buttons)
        self.assertIn("No Reply Needed", quote_buttons)
        self.assertIn("Close", quote_buttons)
        self.assertNotIn("Prepare Draft Order", quote_buttons)

        decision["owner_action_packet"].update({
            "next_action": "prepare_draft_order",
            "internal_next_action": "create_draft",
            "status": "ready_for_owner_prepare",
            "label": "Prepare draft order",
            "order_id": "",
        })
        event = launch.build_sam_live_stock_review_event(inbound, facts, decision, {"score": 99})
        draft_packet = launch.build_sam_live_stock_owner_review_packet(event)
        draft_buttons = [button["text"] for row in draft_packet["telegram_packet"]["reply_markup"]["inline_keyboard"] for button in row]
        self.assertIn("Prepare Draft Order", draft_buttons)

        decision["owner_action_packet"].update({
            "next_action": "prepare_picture_response",
            "internal_next_action": "prepare_picture_response",
            "status": "owner_review",
            "label": "Prepare picture reply",
        })
        event = launch.build_sam_live_stock_review_event(inbound, facts, decision, {"score": 99})
        picture_packet = launch.build_sam_live_stock_owner_review_packet(event)
        picture_buttons = [button["text"] for row in picture_packet["telegram_packet"]["reply_markup"]["inline_keyboard"] for button in row]
        self.assertIn("Send Picture Reply", picture_buttons)

    def test_owner_review_card_surfaces_llm_failure_status(self):
        inbound, facts, decision = review_inputs()
        decision["llm_draft"] = {"used": False, "status": "llm_call_failed"}
        event = launch.build_sam_live_stock_review_event(
            inbound,
            facts,
            decision,
            {"score": 99, "confidence_target": 96, "safe_to_send": True, "recommended_action": "owner_review_send_candidate"},
        )

        packet = launch.build_sam_live_stock_owner_review_packet(event)

        self.assertIn("Reply: Fallback - llm call failed", packet["telegram_packet"]["text"])
        self.assertIn("Flags: LLM call failed", packet["telegram_packet"]["text"])

    def test_owner_review_card_hides_happy_path_llm_noise(self):
        inbound, facts, decision = review_inputs()
        decision["reply_source"] = "llm_live_stock_reply_draft"
        decision["llm_draft"] = {"used": True, "status": "llm_reply_draft_used"}
        event = launch.build_sam_live_stock_review_event(
            inbound,
            facts,
            decision,
            {"score": 99, "confidence_target": 96, "safe_to_send": True, "recommended_action": "owner_review_send_candidate"},
        )

        packet = launch.build_sam_live_stock_owner_review_packet(event)

        self.assertIn("Reply: LLM draft", packet["telegram_packet"]["text"])
        self.assertNotIn("LLM llm reply draft used", packet["telegram_packet"]["text"])
        self.assertNotIn("llm live stock reply draft", packet["telegram_packet"]["text"])

    def test_owner_review_card_surfaces_llm_safety_fallback_reason(self):
        inbound, facts, decision = review_inputs()
        decision["reply_source"] = "deterministic_fallback_after_llm_review"
        decision["llm_draft_review"] = {
            "status": "rejected_by_safety_review",
            "blocked_reasons": ["unsafe_sales_or_discount_language"],
        }
        event = launch.build_sam_live_stock_review_event(
            inbound,
            facts,
            decision,
            {"score": 99, "confidence_target": 96, "safe_to_send": True, "recommended_action": "owner_review_send_candidate"},
        )

        packet = launch.build_sam_live_stock_owner_review_packet(event)

        self.assertIn("Reply: Safety fallback - unsafe sales or discount language", packet["telegram_packet"]["text"])
        self.assertIn("LLM safety fallback: unsafe sales or discount language", packet["telegram_packet"]["text"])

    def test_telegram_cleanup_is_env_gated_and_targeted(self):
        result, status = launch.delete_sam_live_stock_telegram_escalation(
            "SAM-LIVE-ESC-1",
            "555",
            "123",
            environ={},
            telegram_deleter=lambda *args: {"ok": True},
        )

        self.assertEqual(status, 409)
        self.assertEqual(result["status"], "sam_live_stock_telegram_cleanup_disabled")
        self.assertTrue(result["cleanup_packet"]["delete_allowed"])

    def test_chatwoot_takeover_is_env_gated_and_writes_only_when_enabled(self):
        calls = []

        result, status = launch.apply_sam_live_stock_chatwoot_takeover(
            "2401",
            mode="HUMAN",
            environ={},
            chatwoot_writer=lambda *args: calls.append(args),
        )

        self.assertEqual(status, 409)
        self.assertEqual(result["status"], "sam_live_stock_chatwoot_takeover_write_disabled")
        self.assertEqual(calls, [])

        result, status = launch.apply_sam_live_stock_chatwoot_takeover(
            "2401",
            mode="HUMAN",
            reason="owner_test",
            environ={"SAM_LIVE_STOCK_CHATWOOT_TAKEOVER_WRITE_ENABLED": "1"},
            chatwoot_writer=lambda conversation_id, attrs, source: calls.append((conversation_id, attrs)) or {"ok": True},
        )

        self.assertEqual(status, 200)
        self.assertEqual(calls[0][0], "2401")
        self.assertEqual(calls[0][1]["conversation_mode"], "HUMAN")
        self.assertTrue(result["calls_chatwoot"])

    def test_owner_callback_routes_approve_human_resolved_and_close(self):
        send_calls = []
        result, status = launch.process_sam_live_stock_owner_callback(
            {
                "callback_data": "sam_live_approve_send:SAM-LIVE-ESC-1",
                "conversation_id": "2401",
                "message": "Approved reply",
            },
            environ={"SAM_LIVE_STOCK_OWNER_APPROVED_SEND_ENABLED": "1"},
            chatwoot_sender=lambda conversation_id, message, source: send_calls.append((conversation_id, message)) or {"ok": True},
        )
        self.assertEqual(status, 200)
        self.assertEqual(result["action"], "approve_send")
        self.assertTrue(result["sends_customer_message"])
        self.assertEqual(send_calls, [("2401", "Approved reply")])

        result, status = launch.process_sam_live_stock_owner_callback(
            {"callback_data": "sam_live_human:SAM-LIVE-ESC-1", "conversation_id": "2401"},
            environ={"SAM_LIVE_STOCK_CHATWOOT_TAKEOVER_WRITE_ENABLED": "1"},
            chatwoot_writer=lambda conversation_id, attrs, source: {"ok": True},
        )
        self.assertEqual(status, 200)
        self.assertEqual(result["action"], "human")
        self.assertTrue(result["calls_chatwoot"])

        result, status = launch.process_sam_live_stock_owner_callback(
            {
                "callback_data": "sam_live_resolved:SAM-LIVE-ESC-1",
                "telegram_chat_id": "555",
                "telegram_message_id": "123",
            },
            environ={
                "SAM_LIVE_STOCK_TELEGRAM_CLEANUP_ENABLED": "1",
                "SAM_LIVE_STOCK_TELEGRAM_BOT_TOKEN": "token",
            },
            telegram_deleter=lambda token, chat_id, message_id: {"ok": True},
        )
        self.assertEqual(status, 200)
        self.assertEqual(result["action"], "resolved")
        self.assertTrue(result["calls_telegram"])

        result, status = launch.process_sam_live_stock_owner_callback({"callback_data": "sam_live_close:SAM-LIVE-ESC-1"})
        self.assertEqual(status, 200)
        self.assertEqual(result["action"], "close")

    def test_owner_review_callback_loads_saved_event_before_sending(self):
        event = {
            "review_event_id": "SAM-LIVE-REVIEW-ABC123",
            "chatwoot_conversation_id": "2401",
            "sam_reply_excerpt": "Current SAM Live price estimate:\n- 2 x Weaner: R500 each",
            "decision_json": {},
        }
        send_calls = []

        result, status = launch.process_sam_live_stock_owner_callback(
            {"callback_data": "sam_live_review_approve:SAM-LIVE-REVIEW-ABC123"},
            environ={"SAM_LIVE_STOCK_OWNER_APPROVED_SEND_ENABLED": "1"},
            review_event_loader=lambda review_id: ({"success": True, "event": event}, 200),
            chatwoot_sender=lambda conversation_id, message, source: send_calls.append((conversation_id, message)) or {"ok": True},
        )

        self.assertEqual(status, 200)
        self.assertEqual(result["action"], "review_approve_send")
        self.assertTrue(result["sends_customer_message"])
        self.assertEqual(send_calls, [("2401", "Current SAM Live price estimate:\n- 2 x Weaner: R500 each")])

    def test_owner_review_callback_uses_full_decision_reply_not_excerpt(self):
        full_reply = "Line 1\n" + "\n".join(f"Detail line {index}" for index in range(1, 80))
        event = {
            "review_event_id": "SAM-LIVE-REVIEW-LONG",
            "chatwoot_conversation_id": "2401",
            "sam_reply_excerpt": full_reply[:500],
            "decision_json": {"suggested_reply_text": full_reply},
        }
        send_calls = []

        result, status = launch.process_sam_live_stock_owner_callback(
            {"callback_data": "sam_live_review_approve:SAM-LIVE-REVIEW-LONG"},
            environ={"SAM_LIVE_STOCK_OWNER_APPROVED_SEND_ENABLED": "1"},
            review_event_loader=lambda review_id: ({"success": True, "event": event}, 200),
            chatwoot_sender=lambda conversation_id, message, source: send_calls.append((conversation_id, message)) or {"ok": True},
        )

        self.assertEqual(status, 200)
        self.assertTrue(result["sends_customer_message"])
        self.assertEqual(send_calls, [("2401", full_reply[:1800])])

    def test_owner_review_callback_edit_returns_safe_manual_instruction(self):
        event = {
            "review_event_id": "SAM-LIVE-REVIEW-ABC123",
            "chatwoot_conversation_id": "2401",
            "sam_reply_excerpt": "Suggested reply",
            "decision_json": {},
        }

        result, status = launch.process_sam_live_stock_owner_callback(
            {"callback_data": "sam_live_review_edit:SAM-LIVE-REVIEW-ABC123"},
            review_event_loader=lambda review_id: ({"success": True, "event": event}, 200),
        )

        self.assertEqual(status, 200)
        self.assertEqual(result["action"], "review_edit")
        self.assertEqual(result["conversation_id"], "2401")
        self.assertEqual(result["suggested_reply"], "Suggested reply")
        self.assertFalse(result["sends_customer_message"])

    def test_owner_review_v2_callbacks_prepare_only_without_execution(self):
        event = {
            "review_event_id": "SAM-LIVE-REVIEW-ABC123",
            "chatwoot_conversation_id": "2401",
            "sam_reply_excerpt": "Suggested reply",
            "decision_json": {
                "owner_action_packet": {
                    "order_id": "ORD-1",
                    "label": "Prepare latest quote send",
                    "status": "ready_for_owner_quote_prepare",
                    "detail": "Use order ORD-1 to generate or verify the latest quote before any customer send.",
                    "routes": {
                        "quote_prepare": {
                            "allowed_for_sam_auto": False,
                            "route": "/api/orders/ORD-1/quote/prepare-send",
                            "method": "POST",
                        }
                    },
                }
            },
        }

        for callback_data, expected_action, expected_status in (
            ("sam_live_review_no_reply:SAM-LIVE-REVIEW-ABC123", "review_no_reply", "sam_live_stock_review_no_reply_recorded"),
            ("sam_live_review_prepare_quote:SAM-LIVE-REVIEW-ABC123", "review_prepare_quote", "sam_live_stock_review_prepare_quote_ready"),
            ("sam_live_review_prepare_draft:SAM-LIVE-REVIEW-ABC123", "review_prepare_draft_order", "sam_live_stock_review_prepare_draft_order_ready"),
            ("sam_live_review_update_draft:SAM-LIVE-REVIEW-ABC123", "review_update_draft_order", "sam_live_stock_review_update_draft_order_ready"),
            ("sam_live_review_picture:SAM-LIVE-REVIEW-ABC123", "review_picture_reply", "sam_live_stock_review_picture_reply_ready"),
        ):
            result, status = launch.process_sam_live_stock_owner_callback(
                {"callback_data": callback_data},
                review_event_loader=lambda review_id: ({"success": True, "event": event}, 200),
            )

            self.assertEqual(status, 200)
            self.assertTrue(result["success"])
            self.assertEqual(result["action"], expected_action)
            self.assertEqual(result["status"], expected_status)
            self.assertFalse(result["sends_customer_message"])
            self.assertFalse(result["calls_chatwoot"])
            self.assertFalse(result["calls_n8n"])
            self.assertFalse(result["creates_order"])
            self.assertFalse(result["creates_quote"])
            self.assertFalse(result["reserves_stock"])
            self.assertTrue(result["prepared_action"]["owner_gate_required"])
            self.assertTrue(result["prepared_action"]["manual_review_required"])

    def test_live_stock_reservation_plan_is_advisory(self):
        plan = launch.build_live_stock_reservation_plan(
            order_id="ORD-1",
            match_packet={"matched_sample": [{"pig_id": "PIG-1"}]},
        )

        self.assertTrue(plan["owner_gate_required"])
        self.assertTrue(plan["can_execute_order_line_reservation"])
        self.assertFalse(plan["reserves_stock"])

    def test_order_reservation_execution_is_env_gated(self):
        result, status = launch.execute_live_stock_order_reservation(
            "ORD-1",
            action="reserve",
            environ={},
            reserve_fn=lambda order_id: {"success": True},
        )

        self.assertEqual(status, 409)
        self.assertEqual(result["status"], "sam_live_stock_order_reservation_disabled")

        result, status = launch.execute_live_stock_order_reservation(
            "ORD-1",
            action="reserve",
            environ={"SAM_LIVE_STOCK_ORDER_RESERVATION_ENABLED": "1"},
            reserve_fn=lambda order_id: {"success": True, "changed_count": 2},
        )

        self.assertEqual(status, 200)
        self.assertTrue(result["success"])
        self.assertTrue(result["reserves_stock"])
        self.assertTrue(result["changes_stock"])

    def test_launch_readiness_requires_owner_telegram_notifications_for_boost(self):
        result, status = launch.build_sam_live_stock_launch_readiness(environ={})

        self.assertEqual(status, 200)
        self.assertFalse(result["boost_ready"])
        self.assertTrue(result["quiet_post_ready"])
        self.assertIn("SAM_LIVE_STOCK_TELEGRAM_NEW_LEAD_SEND_ENABLED", " ".join(result["must_fix_before_boost"]))

        ready, ready_status = launch.build_sam_live_stock_launch_readiness(environ={
            "SAM_LIVE_STOCK_TELEGRAM_NEW_LEAD_SEND_ENABLED": "1",
            "SAM_LIVE_STOCK_TELEGRAM_ESCALATION_SEND_ENABLED": "1",
            "SAM_LIVE_STOCK_TELEGRAM_OWNER_REVIEW_SEND_ENABLED": "1",
            "SAM_LIVE_STOCK_OWNER_APPROVED_SEND_ENABLED": "1",
            "SAM_LIVE_STOCK_TELEGRAM_BOT_TOKEN": "token",
            "SAM_LIVE_STOCK_TELEGRAM_OWNER_CHAT_ID": "555",
        })

        self.assertEqual(ready_status, 200)
        self.assertTrue(ready["boost_ready"])
        self.assertEqual(ready["score"], 98)
        self.assertEqual(ready["must_fix_before_boost"], [])


if __name__ == "__main__":
    unittest.main()
