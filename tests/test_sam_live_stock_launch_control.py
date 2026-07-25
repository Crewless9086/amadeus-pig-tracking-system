import json
import types
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from modules.sales import sam_live_stock_launch_control as launch


class ChatwootFilterResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


def human_conversation(
    conversation_id,
    *,
    inbox_id=77,
    review_state=None,
    timestamp="2026-07-24T09:00:00Z",
    lane="livestock",
):
    attributes = {"conversation_mode": "HUMAN"}
    labels = []
    if lane == "livestock":
        attributes.update({"sales_lane": "live_stock_sales", "sam_live_stock_gate": "owner_review"})
        labels.append("sam_live_stock")
    elif lane == "meat":
        attributes["sales_lane"] = "meat_sales"
        labels.append("sam_meat")
    conversation = {
        "id": conversation_id,
        "inbox_id": inbox_id,
        "custom_attributes": attributes,
        "labels": labels,
        "messages": [{"message_type": "outgoing", "created_at": timestamp, "sender": {"type": "user"}}],
    }
    if review_state:
        conversation["sam_live_stock_review"] = {"state": review_state}
    return conversation


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
    def test_open_intake_row_exposes_canonical_item_demand_facts(self):
        row = launch._open_intake_row({
            "intake_id": "INTAKE-1",
            "conversation_id": "2401",
            "intake_status": "Open",
            "items": [{"item_key": "weaner", "quantity": 2, "category": "Weaner", "weight_range": "10-14 kg"}],
        })
        self.assertEqual(row["quantity"], 2)
        self.assertEqual(row["items"][0]["category"], "Weaner")

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
            "Current price estimate:\n"
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
            "Current price estimate:\n"
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
        self.assertIn("Draft source: Fact-aware fallback", calls[0][2])
        self.assertIn("Draft reply:", calls[0][2])
        self.assertIn("\n- 2 x Female Weaner", calls[0][2])
        buttons = calls[0][3]["inline_keyboard"]
        self.assertEqual(buttons[0][0]["text"], "Send Reply")
        self.assertTrue(buttons[0][0]["callback_data"].startswith("sam_live_card_send:SAM-LIVE-REVIEW-"))
        self.assertEqual(buttons[1][0]["text"], "Open Chatwoot")
        self.assertEqual(buttons[1][0]["url"], "https://app.chatwoot.com/app/accounts/147387/conversations/2401")
        button_labels = [button["text"] for row in buttons for button in row]
        callback_values = [button.get("callback_data", "") for row in buttons for button in row]
        self.assertIn("Keep With Me", button_labels)
        self.assertIn("No Reply — Done", button_labels)
        self.assertIn("Prepare Quote", button_labels)
        self.assertIn("Done — Return to SAM", button_labels)
        self.assertTrue(any(value.startswith("sam_live_review_prepare_quote:SAM-LIVE-REVIEW-") for value in callback_values))
        self.assertTrue(any(value.startswith("sam_live_card_no_reply:SAM-LIVE-REVIEW-") for value in callback_values))
        self.assertTrue(all(not value or value.startswith("sam_live_") for value in callback_values))
        self.assertNotIn("n8n", str(calls[0][3]).lower())

    def test_owner_review_packet_v2_buttons_cover_prepared_actions(self):
        inbound, facts, decision = review_inputs()
        event = launch.build_sam_live_stock_review_event(
            inbound,
            facts,
            decision,
            {"score": 99, "confidence_target": 96, "safe_to_send": True, "recommended_action": "owner_review_send_candidate"},
        )

        packet = launch.build_sam_live_stock_owner_review_packet(event)

        self.assertEqual(packet["version"], "sam_live_stock_owner_review_packet_v2")
        self.assertFalse(packet["sends_customer_message"])
        self.assertFalse(packet["calls_chatwoot"])
        self.assertFalse(packet["creates_order"])
        self.assertFalse(packet["reserves_stock"])

        labels = [
            button["text"]
            for row in packet["telegram_packet"]["reply_markup"]["inline_keyboard"]
            for button in row
        ]
        self.assertEqual(labels.count("Send Reply"), 1)
        self.assertIn("Open Chatwoot", labels)
        self.assertIn("Keep With Me", labels)
        self.assertIn("No Reply — Done", labels)
        self.assertIn("Prepare Quote", labels)
        self.assertIn("Done — Return to SAM", labels)
        self.assertNotIn("Prepare Draft Order", labels)

        decision["owner_action_packet"].update({
            "next_action": "prepare_draft_order",
            "internal_next_action": "create_draft",
            "status": "ready_for_owner_prepare",
            "label": "Prepare draft order",
            "order_id": "",
            "draft_order_ready": True,
        })
        event = launch.build_sam_live_stock_review_event(inbound, facts, decision)
        labels = [
            button["text"]
            for row in launch.build_sam_live_stock_owner_review_packet(event)["telegram_packet"]["reply_markup"]["inline_keyboard"]
            for button in row
        ]
        self.assertIn("Prepare Draft Order", labels)

        decision["owner_action_packet"]["next_action"] = "update_draft_order"
        decision["owner_action_packet"]["internal_next_action"] = "sync_lines"
        event = launch.build_sam_live_stock_review_event(inbound, facts, decision)
        labels = [
            button["text"]
            for row in launch.build_sam_live_stock_owner_review_packet(event)["telegram_packet"]["reply_markup"]["inline_keyboard"]
            for button in row
        ]
        self.assertIn("Update Draft Order", labels)

        decision["owner_action_packet"].update({
            "next_action": "prepare_picture_response",
            "internal_next_action": "prepare_picture_response",
            "status": "owner_review",
            "label": "Prepare picture reply",
        })
        decision["next_action"] = "prepare_picture_response"
        event = launch.build_sam_live_stock_review_event(inbound, facts, decision)
        labels = [
            button["text"]
            for row in launch.build_sam_live_stock_owner_review_packet(event)["telegram_packet"]["reply_markup"]["inline_keyboard"]
            for button in row
        ]
        self.assertIn("Send Picture Reply", labels)

    def test_protected_authority_card_names_one_decision_and_suppresses_duplicate_send(self):
        inbound, facts, decision = review_inputs()
        decision["routine_reply_delivery"] = {"sent": True, "status": "sam_live_stock_routine_reply_sent"}
        review = {
            "score": 99,
            "confidence_target": 96,
            "safe_to_send": True,
            "recommended_action": "owner_authority_decision",
            "owner_authority_required": True,
            "protected_action_reasons": [
                "negotiated_price_owner_authority",
                "reservation_owner_authority",
            ],
        }
        event = launch.build_sam_live_stock_review_event(inbound, facts, decision, review)

        packet = launch.build_sam_live_stock_owner_review_packet(event)
        text = packet["telegram_packet"]["text"]
        labels = [
            button["text"]
            for row in packet["telegram_packet"]["reply_markup"]["inline_keyboard"]
            for button in row
        ]

        self.assertIn("Owner decision needed: approve or decline the negotiated price", text)
        self.assertIn("approve or decline the reservation through the protected order/stock rail", text)
        self.assertIn("Customer reply: already sent by SAM", text)
        self.assertNotIn("Send Reply", labels)

    def test_fact_aware_fallback_label_maps_the_llm_disabled_status(self):
        inbound, facts, decision = review_inputs()
        decision["reply_source"] = "deterministic_read_only_guard"
        decision["llm_draft"] = {"used": False, "status": "llm_disabled"}
        event = launch.build_sam_live_stock_review_event(inbound, facts, decision)

        packet = launch.build_sam_live_stock_owner_review_packet(event)

        self.assertEqual(launch._owner_card_reply_source_summary(decision), "Fact-aware fallback")
        self.assertIn("Draft source: Fact-aware fallback", packet["telegram_packet"]["text"])

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

        self.assertIn("Draft source: Fallback - llm call failed", packet["telegram_packet"]["text"])
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

        self.assertIn("Draft source: LLM draft", packet["telegram_packet"]["text"])
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

        self.assertIn("Draft source: Safety fallback - unsafe sales or discount language", packet["telegram_packet"]["text"])
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
            "sam_reply_excerpt": "Current price estimate:\n- 2 x Weaner: R500 each",
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
        self.assertEqual(send_calls, [("2401", "Current price estimate:\n- 2 x Weaner: R500 each")])

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

    def test_owner_review_v2_callbacks_prepare_without_executing_actions(self):
        event = {
            "review_event_id": "SAM-LIVE-REVIEW-ABC123",
            "chatwoot_conversation_id": "2401",
            "sam_reply_excerpt": "Suggested reply",
            "decision_json": {
                "owner_action_packet": {
                    "next_action": "prepare_quote",
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
            ("sam_live_review_draft_order:SAM-LIVE-REVIEW-ABC123", "review_prepare_draft_order", "sam_live_stock_review_prepare_draft_order_ready"),
            ("sam_live_review_quote:SAM-LIVE-REVIEW-ABC123", "review_prepare_quote", "sam_live_stock_review_prepare_quote_ready"),
            ("sam_live_review_prepare_quote:SAM-LIVE-REVIEW-ABC123", "review_prepare_quote", "sam_live_stock_review_prepare_quote_ready"),
            ("sam_live_review_prepare_draft:SAM-LIVE-REVIEW-ABC123", "review_prepare_draft_order", "sam_live_stock_review_prepare_draft_order_ready"),
            ("sam_live_review_update_draft:SAM-LIVE-REVIEW-ABC123", "review_update_draft_order", "sam_live_stock_review_update_draft_order_ready"),
            ("sam_live_review_picture:SAM-LIVE-REVIEW-ABC123", "review_picture_reply", "sam_live_stock_review_picture_reply_ready"),
        ):
            with self.subTest(callback=callback_data):
                result, status = launch.process_sam_live_stock_owner_callback(
                    {"callback_data": callback_data},
                    review_event_loader=lambda review_id: ({"success": True, "event": event}, 200),
                    chatwoot_sender=lambda *args: self.fail("customer send must not execute"),
                    chatwoot_writer=lambda *args: self.fail("chatwoot write must not execute"),
                )

                self.assertEqual(status, 200)
                self.assertTrue(result["success"])
                self.assertEqual(result["action"], expected_action)
                self.assertEqual(result["status"], expected_status)
                self.assertFalse(result["sends_customer_message"])
                self.assertFalse(result["calls_chatwoot"])
                self.assertFalse(result["calls_telegram"])
                self.assertFalse(result["calls_n8n"])
                self.assertFalse(result["creates_order"])
                self.assertFalse(result["creates_quote"])
                self.assertFalse(result["reserves_stock"])
                self.assertTrue(result["prepared_action"]["owner_gate_required"])
                self.assertTrue(result["prepared_action"]["manual_review_required"])

    def test_owner_callback_prepares_full_sales_pack_without_customer_send(self):
        event = {
            "review_event_id": "SAM-LIVE-REVIEW-PACK",
            "chatwoot_conversation_id": "2401",
            "decision_json": {"owner_action_packet": {"order_id": "ORD-1"}},
        }
        calls = []

        def prepare(order_id, payload):
            calls.append((order_id, payload))
            return {
                "success": True,
                "status": "sam_live_stock_sales_pack_ready",
                "customer_send_allowed": False,
                "reserves_stock": False,
            }

        result, status = launch.process_sam_live_stock_owner_callback(
            {"callback_data": "sam_live_review_prepare_sales_pack:SAM-LIVE-REVIEW-PACK", "owner": "Charl"},
            review_event_loader=lambda review_id: ({"success": True, "event": event}, 200),
            sales_pack_preparer=prepare,
            chatwoot_sender=lambda *args: self.fail("customer send must not execute"),
        )
        self.assertEqual(status, 200)
        self.assertTrue(result["success"])
        self.assertEqual(calls, [("ORD-1", {"created_by": "Charl"})])
        self.assertFalse(result["sends_customer_message"])
        self.assertFalse(result["reserves_stock"])

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

    def test_repeated_owner_card_updates_edit_the_exact_active_message(self):
        inbound, facts, decision = review_inputs()
        event = launch.build_sam_live_stock_review_event(inbound, facts, decision)
        sent = []
        edited = []
        evidence = []
        result, status = launch.send_sam_live_stock_owner_review_telegram(
            event,
            environ={"SAM_LIVE_STOCK_TELEGRAM_OWNER_REVIEW_SEND_ENABLED": "1", "SAM_LIVE_STOCK_TELEGRAM_BOT_TOKEN": "token", "SAM_LIVE_STOCK_TELEGRAM_OWNER_CHAT_ID": "555"},
            telegram_sender=lambda *args: sent.append(args),
            telegram_editor=lambda token, chat, message, text, markup: edited.append((chat, message, text)) or {"ok": True},
            active_card_loader=lambda conversation_id: ({"success": True, "card": {"telegram_chat_id": "555", "telegram_message_id": "991", "state": "active"}}, 200),
            evidence_recorder=lambda item: evidence.append(item) or ({"success": True, "created": True}, 200),
        )
        self.assertEqual(status, 200)
        self.assertEqual(result["status"], "sam_live_stock_owner_card_edited")
        self.assertEqual(sent, [])
        self.assertEqual(edited[0][:2], ("555", "991"))
        self.assertEqual(evidence[0]["review_json"]["owner_card"]["telegram_message_id"], "991")

    def test_send_reply_sequences_send_then_auto_then_exact_cleanup(self):
        event = {"review_event_id": "SAM-LIVE-REVIEW-1", "chatwoot_conversation_id": "2401", "sam_reply_excerpt": "Safe reply", "decision_json": {}}
        calls = []
        def record(item):
            calls.append(("evidence", item["review_json"]["owner_card"]["state"]))
            return {"success": True, "created": True}, 200
        result, status = launch.process_sam_live_stock_owner_callback(
            {"callback_data": "sam_live_card_send:SAM-LIVE-REVIEW-1", "telegram_chat_id": "555", "telegram_message_id": "991"},
            environ={"SAM_LIVE_STOCK_OWNER_APPROVED_SEND_ENABLED": "1", "SAM_LIVE_STOCK_CHATWOOT_TAKEOVER_WRITE_ENABLED": "1", "SAM_LIVE_STOCK_TELEGRAM_CLEANUP_ENABLED": "1", "SAM_LIVE_STOCK_TELEGRAM_BOT_TOKEN": "token"},
            review_event_loader=lambda _: ({"success": True, "event": event}, 200),
            evidence_recorder=record,
            chatwoot_sender=lambda conversation, message, source: calls.append(("send", conversation)) or {"ok": True},
            chatwoot_writer=lambda conversation, attrs, source: calls.append(("mode", attrs["conversation_mode"])) or {"ok": True},
            telegram_deleter=lambda token, chat, message: calls.append(("delete", chat, message)) or {"ok": True},
        )
        self.assertEqual(status, 200)
        self.assertTrue(result["sends_customer_message"])
        self.assertLess(calls.index(("send", "2401")), calls.index(("mode", "AUTO")))
        self.assertLess(calls.index(("mode", "AUTO")), calls.index(("delete", "555", "991")))

    def test_failed_send_retains_card_and_never_returns_auto_or_deletes(self):
        event = {"review_event_id": "SAM-LIVE-REVIEW-2", "chatwoot_conversation_id": "2401", "sam_reply_excerpt": "Safe reply", "decision_json": {}}
        calls = []
        result, status = launch.process_sam_live_stock_owner_callback(
            {"callback_data": "sam_live_card_send:SAM-LIVE-REVIEW-2", "telegram_chat_id": "555", "telegram_message_id": "992"},
            environ={"SAM_LIVE_STOCK_OWNER_APPROVED_SEND_ENABLED": "1", "SAM_LIVE_STOCK_CHATWOOT_TAKEOVER_WRITE_ENABLED": "1", "SAM_LIVE_STOCK_TELEGRAM_CLEANUP_ENABLED": "1", "SAM_LIVE_STOCK_TELEGRAM_BOT_TOKEN": "token"},
            review_event_loader=lambda _: ({"success": True, "event": event}, 200),
            evidence_recorder=lambda item: ({"success": True, "created": True}, 200),
            chatwoot_sender=lambda *args: (_ for _ in ()).throw(RuntimeError("send failed")),
            chatwoot_writer=lambda *args: calls.append("mode") or {"ok": True},
            telegram_deleter=lambda *args: calls.append("delete") or {"ok": True},
            telegram_editor=lambda *args: calls.append("edit") or {"ok": True},
        )
        self.assertEqual(status, 502)
        self.assertTrue(result["card_retained"])
        self.assertEqual(calls, ["edit"])

    def test_no_reply_done_returns_auto_then_cleans_exact_card(self):
        event = {"review_event_id": "SAM-LIVE-REVIEW-3", "chatwoot_conversation_id": "2401", "decision_json": {}}
        calls = []
        result, status = launch.process_sam_live_stock_owner_callback(
            {"callback_data": "sam_live_card_no_reply:SAM-LIVE-REVIEW-3", "telegram_chat_id": "555", "telegram_message_id": "993"},
            environ={"SAM_LIVE_STOCK_CHATWOOT_TAKEOVER_WRITE_ENABLED": "1", "SAM_LIVE_STOCK_TELEGRAM_CLEANUP_ENABLED": "1", "SAM_LIVE_STOCK_TELEGRAM_BOT_TOKEN": "token"},
            review_event_loader=lambda _: ({"success": True, "event": event}, 200),
            evidence_recorder=lambda item: ({"success": True, "created": True}, 200),
            chatwoot_sender=lambda *args: self.fail("no customer send"),
            chatwoot_writer=lambda conversation, attrs, source: calls.append(("mode", attrs["conversation_mode"])) or {"ok": True},
            telegram_deleter=lambda token, chat, message: calls.append(("delete", chat, message)) or {"ok": True},
        )
        self.assertEqual(status, 200)
        self.assertFalse(result["sends_customer_message"])
        self.assertEqual(calls, [("mode", "AUTO"), ("delete", "555", "993")])

    def test_duplicate_callback_is_withheld_before_send_or_telegram(self):
        event = {"review_event_id": "SAM-LIVE-REVIEW-4", "chatwoot_conversation_id": "2401", "sam_reply_excerpt": "Reply", "decision_json": {}}
        result, status = launch.process_sam_live_stock_owner_callback(
            {"callback_data": "sam_live_card_send:SAM-LIVE-REVIEW-4", "telegram_chat_id": "555", "telegram_message_id": "994"},
            review_event_loader=lambda _: ({"success": True, "event": event}, 200),
            evidence_recorder=lambda item: ({"success": True, "created": False}, 200),
            chatwoot_sender=lambda *args: self.fail("duplicate send"),
            telegram_deleter=lambda *args: self.fail("duplicate cleanup"),
        )
        self.assertEqual(status, 409)
        self.assertEqual(result["status"], "sam_live_stock_owner_card_duplicate_callback_withheld")

    def test_keep_with_me_retains_human_and_open_chatwoot_is_no_mutation(self):
        event = {"review_event_id": "SAM-LIVE-REVIEW-5", "chatwoot_conversation_id": "2401", "decision_json": {}}
        calls = []
        common = {
            "review_event_loader": lambda _: ({"success": True, "event": event}, 200),
            "evidence_recorder": lambda item: ({"success": True, "created": True}, 200),
        }
        opened, open_status = launch.process_sam_live_stock_owner_callback(
            {"callback_data": "sam_live_card_open:SAM-LIVE-REVIEW-5"}, **common,
        )
        self.assertEqual(open_status, 200)
        self.assertEqual(opened["status"], "sam_live_stock_owner_card_open_no_mutation")
        kept, keep_status = launch.process_sam_live_stock_owner_callback(
            {"callback_data": "sam_live_card_keep:SAM-LIVE-REVIEW-5", "telegram_chat_id": "555", "telegram_message_id": "995"},
            environ={"SAM_LIVE_STOCK_CHATWOOT_TAKEOVER_WRITE_ENABLED": "1", "SAM_LIVE_STOCK_TELEGRAM_BOT_TOKEN": "token"},
            chatwoot_writer=lambda conversation, attrs, source: calls.append(("mode", attrs["conversation_mode"])) or {"ok": True},
            telegram_editor=lambda token, chat, message, text, markup: calls.append(("edit", chat, message, text)) or {"ok": True},
            telegram_deleter=lambda *args: self.fail("keep must not delete"),
            **common,
        )
        self.assertEqual(keep_status, 200)
        self.assertEqual(calls[0], ("mode", "HUMAN"))
        self.assertIn("With Charl", calls[1][3])
        self.assertEqual(kept["status"], "sam_live_stock_owner_card_with_charl")

    def test_delete_failure_marks_exact_card_resolved_and_removes_keyboard(self):
        event = {"review_event_id": "SAM-LIVE-REVIEW-6", "chatwoot_conversation_id": "2401", "decision_json": {}}
        edits = []
        result, status = launch.process_sam_live_stock_owner_callback(
            {"callback_data": "sam_live_card_done:SAM-LIVE-REVIEW-6", "telegram_chat_id": "555", "telegram_message_id": "996"},
            environ={"SAM_LIVE_STOCK_CHATWOOT_TAKEOVER_WRITE_ENABLED": "1", "SAM_LIVE_STOCK_TELEGRAM_CLEANUP_ENABLED": "1", "SAM_LIVE_STOCK_TELEGRAM_BOT_TOKEN": "token"},
            review_event_loader=lambda _: ({"success": True, "event": event}, 200),
            evidence_recorder=lambda item: ({"success": True, "created": True}, 200),
            chatwoot_writer=lambda *args: {"ok": True},
            telegram_deleter=lambda *args: (_ for _ in ()).throw(RuntimeError("delete unavailable")),
            telegram_editor=lambda token, chat, message, text, markup: edits.append((chat, message, text, markup)) or {"ok": True},
        )
        self.assertEqual(status, 200)
        self.assertEqual(result["telegram_cleanup"]["status"], "sam_live_stock_owner_card_resolved_by_edit")
        self.assertEqual(edits, [("555", "996", "Resolved", {"inline_keyboard": []})])

    def test_human_mode_audit_classifies_without_bulk_reset(self):
        conversations = [
            {**human_conversation(1), "custom_attributes": {**human_conversation(1)["custom_attributes"], "unrelated": "keep"}, "messages": [{"message_type": "incoming", "created_at": "2026-07-24T09:00:00Z", "sender": {"type": "contact"}}]},
            {"id": 2, "custom_attributes": {"conversation_mode": "HUMAN"}, "sam_live_stock_review": {"state": "resolved"}, "messages": [{"message_type": "outgoing", "created_at": "2026-07-24T09:00:00Z", "sender": {"type": "user"}}]},
            human_conversation(3, timestamp="2026-07-20T09:00:00Z"),
            human_conversation(4),
        ]
        result, status = launch.audit_sam_live_stock_human_conversations(chatwoot_reader=lambda source: conversations, now=datetime(2026, 7, 24, 10, tzinfo=timezone.utc))
        self.assertEqual(status, 200)
        self.assertEqual([row["classification"] for row in result["conversations"]], ["awaiting_owner", "resolved_but_stuck", "stale_unknown", "active_manual"])
        self.assertFalse(result["bulk_reset_allowed"])
        self.assertFalse(result["writes_performed"])

    def test_human_mode_audit_production_null_item_fails_structured_not_zero(self):
        result, status = launch.audit_sam_live_stock_human_conversations(
            chatwoot_reader=lambda source: [None],
        )

        self.assertEqual(status, 502)
        self.assertEqual(result["status"], "sam_live_stock_human_audit_conversation_shape_invalid")
        self.assertEqual(result["failure_stage"], "conversation_item")
        self.assertEqual(result["error_type"], "NoneType")
        self.assertFalse(result["evidence_available"])
        self.assertFalse(result["conversation_count_known"])
        self.assertIsNone(result["counts"])
        self.assertFalse(result["bulk_reset_allowed"])

    def test_human_mode_audit_tolerates_partial_latest_message_sender_and_timestamp_shapes(self):
        conversations = [
            {
                "id": 1826,
                "custom_attributes": {"conversation_mode": "HUMAN", "sales_lane": "live_stock_sales", "sam_live_stock_gate": "owner_review"},
                "labels": ["sam_live_stock"],
                "messages": [None],
                "last_activity_at": {"unexpected": "shape"},
            },
            {
                "id": 1827,
                "custom_attributes": {"conversation_mode": "HUMAN"},
                "sam_live_stock_review": {"state": "resolved"},
                "messages": [{"message_type": "outgoing", "sender": ["unexpected"]}],
            },
        ]

        result, status = launch.audit_sam_live_stock_human_conversations(
            chatwoot_reader=lambda source: conversations,
            now=datetime(2026, 7, 24, 10, tzinfo=timezone.utc),
        )

        self.assertEqual(status, 200)
        self.assertEqual(result["conversations"][0]["classification"], "stale_unknown")
        self.assertIsNone(result["conversations"][0]["latest_message_at"])
        self.assertFalse(result["conversations"][0]["shape_complete"])
        self.assertEqual(result["conversations"][1]["classification"], "resolved_but_stuck")

    def test_human_mode_audit_malformed_response_and_attributes_fail_closed(self):
        result, status = launch.audit_sam_live_stock_human_conversations(
            chatwoot_reader=lambda source: {"payload": []},
        )
        self.assertEqual(status, 502)
        self.assertEqual(result["failure_stage"], "chatwoot_response_shape")
        self.assertFalse(result["conversation_count_known"])

        result, status = launch.audit_sam_live_stock_human_conversations(
            chatwoot_reader=lambda source: [{"id": 1826, "custom_attributes": []}],
        )
        self.assertEqual(status, 502)
        self.assertEqual(result["failure_stage"], "custom_attributes")

    def test_human_mode_audit_review_loader_failures_are_sanitized_and_unavailable(self):
        conversations = [{"id": 1826, "custom_attributes": {"conversation_mode": "HUMAN"}}]

        result, status = launch.audit_sam_live_stock_human_conversations(
            chatwoot_reader=lambda source: conversations,
            review_loader=lambda conversation_id: (_ for _ in ()).throw(RuntimeError("postgres://secret")),
        )

        self.assertEqual(status, 503)
        self.assertEqual(result["failure_stage"], "review_event_load")
        self.assertEqual(result["error_type"], "RuntimeError")
        self.assertNotIn("postgres://secret", str(result))
        self.assertFalse(result["evidence_available"])

    def test_chatwoot_reader_rejects_malformed_pagination_shape(self):
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return b'{"data":{"payload":{},"meta":[]}}'

        with patch.object(launch.urllib_request, "urlopen", return_value=Response()):
            result, status = launch.audit_sam_live_stock_human_conversations(
                environ={launch.CHATWOOT_TOKEN_ENV: "configured-secret", launch.HUMAN_AUDIT_CHATWOOT_INBOX_ENV: "77"},
            )

        self.assertEqual(status, 502)
        self.assertEqual(result["failure_stage"], "chatwoot_pagination")
        self.assertNotIn("configured-secret", str(result))
        self.assertTrue(result["diagnostics"]["chatwoot_token_configured"])
        self.assertFalse(result["diagnostics"]["secrets_exposed"])

    def test_human_mode_audit_classifies_chatwoot_http_and_timeout_failures(self):
        http_error = launch.urllib_error.HTTPError(
            "https://example.invalid", 503, "upstream", {}, None
        )
        result, status = launch.audit_sam_live_stock_human_conversations(
            chatwoot_reader=lambda source: (_ for _ in ()).throw(http_error),
        )
        self.assertEqual(status, 502)
        self.assertEqual(result["status"], "sam_live_stock_human_audit_chatwoot_http_error")
        self.assertEqual(result["error_type"], "HTTPError")

        result, status = launch.audit_sam_live_stock_human_conversations(
            chatwoot_reader=lambda source: (_ for _ in ()).throw(TimeoutError("token-value")),
        )
        self.assertEqual(status, 504)
        self.assertEqual(result["status"], "sam_live_stock_human_audit_chatwoot_timeout")
        self.assertNotIn("token-value", str(result))

    def test_human_audit_uses_documented_server_filter_and_sam_inbox(self):
        calls = []

        def urlopen(request, timeout):
            calls.append((request, timeout))
            return ChatwootFilterResponse({
                "meta": {"all_count": 1},
                "payload": [human_conversation(1826)],
            })

        source = {
            launch.CHATWOOT_TOKEN_ENV: "configured-secret",
            launch.CHATWOOT_ACCOUNT_ID_ENV: "account-secret",
            launch.HUMAN_AUDIT_CHATWOOT_INBOX_ENV: "77",
        }
        with patch.object(launch.urllib_request, "urlopen", side_effect=urlopen):
            result, status = launch.audit_sam_live_stock_human_conversations(
                environ=source,
                review_loader=lambda conversation_id: ({"success": False}, 404),
            )

        self.assertEqual(status, 200)
        self.assertEqual(result["counts"]["active_manual"], 1)
        self.assertEqual(result["diagnostics"]["coverage"], "sam_livestock_inbox_human_custom_attribute")
        self.assertTrue(result["diagnostics"]["pagination_complete"])
        self.assertEqual(len(calls), 1)
        request, timeout = calls[0]
        self.assertEqual(request.method, "POST")
        self.assertEqual(timeout, 10)
        self.assertTrue(request.full_url.endswith("/conversations/filter?page=1"))
        body = json.loads(request.data)
        self.assertEqual(body, {"payload": [
            {"attribute_key": "conversation_mode", "filter_operator": "equal_to", "values": ["HUMAN"], "query_operator": "AND"},
            {"attribute_key": "inbox_id", "filter_operator": "equal_to", "values": [77], "query_operator": None},
        ]})
        self.assertNotIn("configured-secret", str(result))
        self.assertNotIn("account-secret", str(result))
        self.assertNotIn("77", str(result["diagnostics"]))

    def test_human_audit_requires_authoritative_sam_inbox_without_calling_chatwoot(self):
        with patch.object(launch.urllib_request, "urlopen") as reader:
            result, status = launch.audit_sam_live_stock_human_conversations(
                environ={launch.CHATWOOT_TOKEN_ENV: "configured-secret"},
            )

        self.assertEqual(status, 503)
        self.assertEqual(result["status"], "sam_live_stock_human_audit_inbox_not_configured")
        self.assertEqual(result["failure_stage"], "chatwoot_configuration")
        self.assertFalse(result["evidence_available"])
        self.assertFalse(result["conversation_count_known"])
        self.assertIsNone(result["counts"])
        self.assertFalse(result["bulk_reset_allowed"])
        reader.assert_not_called()

    def test_human_audit_reads_multiple_pages_and_deduplicates_ids(self):
        responses = [
            ChatwootFilterResponse({"meta": {"all_count": 3}, "payload": [human_conversation(1), human_conversation(2)]}),
            ChatwootFilterResponse({"meta": {"all_count": 3}, "payload": [human_conversation(2), human_conversation(3)]}),
        ]
        source = {launch.CHATWOOT_TOKEN_ENV: "token", launch.HUMAN_AUDIT_CHATWOOT_INBOX_ENV: "77"}
        with patch.object(launch.urllib_request, "urlopen", side_effect=responses):
            result, status = launch.audit_sam_live_stock_human_conversations(
                environ=source,
                review_loader=lambda conversation_id: ({"success": False}, 404),
            )

        self.assertEqual(status, 200)
        self.assertEqual(len(result["conversations"]), 3)
        self.assertEqual(result["diagnostics"]["pages_read"], 2)
        self.assertEqual(result["diagnostics"]["duplicates_removed"], 1)
        self.assertEqual(result["diagnostics"]["filtered_conversation_count"], 3)

    def test_human_audit_rejects_malformed_or_changing_meta(self):
        source = {launch.CHATWOOT_TOKEN_ENV: "token", launch.HUMAN_AUDIT_CHATWOOT_INBOX_ENV: "77"}
        with patch.object(
            launch.urllib_request,
            "urlopen",
            return_value=ChatwootFilterResponse({"meta": {"all_count": "1"}, "payload": []}),
        ):
            result, status = launch.audit_sam_live_stock_human_conversations(environ=source)
        self.assertEqual(status, 502)
        self.assertEqual(result["failure_stage"], "chatwoot_pagination")
        self.assertFalse(result["conversation_count_known"])
        self.assertIsNone(result["counts"])

        responses = [
            ChatwootFilterResponse({"meta": {"all_count": 2}, "payload": [human_conversation(1)]}),
            ChatwootFilterResponse({"meta": {"all_count": 3}, "payload": [human_conversation(2)]}),
        ]
        with patch.object(launch.urllib_request, "urlopen", side_effect=responses):
            result, status = launch.audit_sam_live_stock_human_conversations(environ=source)
        self.assertEqual(status, 502)
        self.assertEqual(result["status"], "sam_live_stock_human_audit_pagination_meta_changed")

    def test_human_audit_filter_http_400_is_unsupported_and_fail_closed(self):
        error = launch.urllib_error.HTTPError("https://example.invalid", 400, "bad filter", {}, None)
        with patch.object(launch.urllib_request, "urlopen", side_effect=error):
            result, status = launch.audit_sam_live_stock_human_conversations(
                environ={launch.CHATWOOT_TOKEN_ENV: "token", launch.HUMAN_AUDIT_CHATWOOT_INBOX_ENV: "77"},
            )

        self.assertEqual(status, 502)
        self.assertEqual(result["status"], "sam_live_stock_human_audit_filter_unsupported")
        self.assertEqual(result["failure_stage"], "chatwoot_filter_contract")
        self.assertEqual(result["diagnostics"]["fallback_coverage"], "known_sam_evidence_only_not_executed")
        self.assertFalse(result["evidence_available"])

    def test_human_audit_pagination_limit_and_partial_evidence_remain_unknown(self):
        source = {launch.CHATWOOT_TOKEN_ENV: "token", launch.HUMAN_AUDIT_CHATWOOT_INBOX_ENV: "77"}
        responses = [
            ChatwootFilterResponse({"meta": {"all_count": 3}, "payload": [human_conversation(1)]}),
            ChatwootFilterResponse({"meta": {"all_count": 3}, "payload": [human_conversation(2)]}),
        ]
        with patch.object(launch, "HUMAN_AUDIT_MAX_PAGES", 2), patch.object(
            launch.urllib_request, "urlopen", side_effect=responses
        ):
            result, status = launch.audit_sam_live_stock_human_conversations(environ=source)

        self.assertEqual(status, 503)
        self.assertEqual(result["status"], "sam_live_stock_human_audit_pagination_limit_reached")
        self.assertEqual(result["diagnostics"]["partial_filtered_count"], 2)
        self.assertFalse(result["conversation_count_known"])
        self.assertIsNone(result["counts"])
        self.assertFalse(result["bulk_reset_allowed"])

        responses = [
            ChatwootFilterResponse({"meta": {"all_count": 2}, "payload": [human_conversation(1)]}),
            ChatwootFilterResponse({"meta": {"all_count": 2}, "payload": []}),
        ]
        with patch.object(launch.urllib_request, "urlopen", side_effect=responses):
            result, status = launch.audit_sam_live_stock_human_conversations(environ=source)
        self.assertEqual(status, 502)
        self.assertEqual(result["status"], "sam_live_stock_human_audit_partial_evidence")
        self.assertFalse(result["evidence_available"])

    def test_human_audit_total_timeout_is_bounded_and_sanitized(self):
        source = {launch.CHATWOOT_TOKEN_ENV: "token", launch.HUMAN_AUDIT_CHATWOOT_INBOX_ENV: "77"}
        response = ChatwootFilterResponse({
            "meta": {"all_count": 2},
            "payload": [human_conversation(1)],
        })
        with patch.object(launch.urllib_request, "urlopen", return_value=response), patch.object(
            launch.time, "monotonic", side_effect=[0, 0, 31]
        ):
            result, status = launch.audit_sam_live_stock_human_conversations(environ=source)

        self.assertEqual(status, 504)
        self.assertEqual(result["status"], "sam_live_stock_human_audit_total_timeout")
        self.assertFalse(result["conversation_count_known"])
        self.assertFalse(result["writes_performed"])

    def test_human_audit_conclusive_zero_and_review_classification_do_no_writes(self):
        source = {launch.CHATWOOT_TOKEN_ENV: "token", launch.HUMAN_AUDIT_CHATWOOT_INBOX_ENV: "77"}
        with patch.object(
            launch.urllib_request,
            "urlopen",
            return_value=ChatwootFilterResponse({"meta": {"all_count": 0}, "payload": []}),
        ) as reader:
            result, status = launch.audit_sam_live_stock_human_conversations(environ=source)
        self.assertEqual(status, 200)
        self.assertEqual(result["conversations"], [])
        self.assertEqual(
            result["counts"],
            {key: 0 for key in (*launch.HUMAN_AUDIT_CLASSIFICATIONS, *launch.HUMAN_AUDIT_LANE_COUNTS)},
        )
        self.assertTrue(result["conversation_count_known"])
        self.assertTrue(result["evidence_available"])
        self.assertFalse(result["writes_performed"])
        self.assertFalse(result["creates_order"])
        self.assertFalse(result["reserves_stock"])
        self.assertEqual(reader.call_count, 1)

        conversations = [
            human_conversation(1, review_state="resolved"),
            human_conversation(2, timestamp="2026-07-20T09:00:00Z"),
        ]
        result, status = launch.audit_sam_live_stock_human_conversations(
            chatwoot_reader=lambda environ: conversations,
            now=datetime(2026, 7, 24, 10, tzinfo=timezone.utc),
        )
        self.assertEqual(status, 200)
        self.assertEqual(
            [row["classification"] for row in result["conversations"]],
            ["resolved_but_stuck", "stale_unknown"],
        )


    def test_human_audit_shared_inbox_qualifies_livestock_and_excludes_meat_and_unknown(self):
        conversations = [
            human_conversation(301, inbox_id=96568),
            human_conversation(302, inbox_id=96568, lane="meat"),
            human_conversation(303, inbox_id=96568, lane="unknown"),
        ]
        result, status = launch.audit_sam_live_stock_human_conversations(
            chatwoot_reader=lambda source: conversations,
            now=datetime(2026, 7, 24, 10, tzinfo=timezone.utc),
        )
        self.assertEqual(status, 200)
        self.assertTrue(result["evidence_complete"])
        self.assertEqual([row["conversation_id"] for row in result["conversations"]], ["301"])
        self.assertTrue(result["conversations"][0]["authoritative_livestock_lane"])
        self.assertEqual(result["conversations"][0]["lane_proof"], "backend_native_livestock_takeover")
        self.assertEqual(result["counts"]["excluded_non_livestock"], 1)
        self.assertEqual(result["counts"]["lane_unknown"], 1)
        self.assertFalse(result["bulk_reset_allowed"])
        self.assertFalse(result["action_contract"]["automatic_reset_allowed"])
        self.assertTrue(result["action_contract"]["authoritative_livestock_lane_required"])

    def test_human_audit_exact_persisted_review_is_authoritative_lane_proof(self):
        conversation = human_conversation(401, inbox_id=96568, lane="unknown")
        result, status = launch.audit_sam_live_stock_human_conversations(
            chatwoot_reader=lambda source: [conversation],
            review_loader=lambda conversation_id: (
                {"success": True, "event": {"chatwoot_conversation_id": "401", "review_state": "active"}}, 200
            ),
        )
        self.assertEqual(status, 200)
        self.assertEqual(len(result["conversations"]), 1)
        self.assertEqual(result["conversations"][0]["lane_proof"], "persisted_livestock_review")

    def test_human_audit_mismatched_or_conflicting_lane_evidence_is_non_actionable(self):
        unknown = human_conversation(501, inbox_id=96568, lane="unknown")
        result, status = launch.audit_sam_live_stock_human_conversations(
            chatwoot_reader=lambda source: [unknown],
            review_loader=lambda conversation_id: (
                {"success": True, "event": {"chatwoot_conversation_id": "other-conversation"}}, 200
            ),
        )
        self.assertEqual(status, 200)
        self.assertEqual(result["conversations"], [])
        self.assertEqual(result["counts"]["lane_unknown"], 1)
        meat = human_conversation(502, inbox_id=96568, lane="meat")
        result, status = launch.audit_sam_live_stock_human_conversations(
            chatwoot_reader=lambda source: [meat],
            review_loader=lambda conversation_id: (
                {"success": True, "event": {"chatwoot_conversation_id": "502"}}, 200
            ),
        )
        self.assertEqual(status, 200)
        self.assertEqual(result["conversations"], [])
        self.assertEqual(result["counts"]["lane_unknown"], 1)

    def test_human_audit_lane_output_is_secret_free_and_private_content_free(self):
        private = human_conversation(601, inbox_id=96568, lane="meat")
        private["messages"][0]["content"] = "PRIVATE-CUSTOMER-CONTENT"
        private["custom_attributes"]["phone_number"] = "+27000000000"
        result, status = launch.audit_sam_live_stock_human_conversations(
            chatwoot_reader=lambda source: [private],
            environ={
                launch.CHATWOOT_TOKEN_ENV: "CHATWOOT-SECRET-TOKEN",
                launch.CHATWOOT_ACCOUNT_ID_ENV: "PRIVATE-ACCOUNT-ID",
                launch.HUMAN_AUDIT_CHATWOOT_INBOX_ENV: "96568",
            },
        )
        self.assertEqual(status, 200)
        self.assertEqual(result["conversations"], [])
        serialized = json.dumps(result)
        self.assertNotIn("PRIVATE-CUSTOMER-CONTENT", serialized)
        self.assertNotIn("+27000000000", serialized)
        self.assertNotIn("CHATWOOT-SECRET-TOKEN", serialized)
        self.assertNotIn("PRIVATE-ACCOUNT-ID", serialized)
        self.assertNotIn("96568", serialized)

    def test_human_audit_incomplete_evidence_never_returns_complete_counts(self):
        result, status = launch.audit_sam_live_stock_human_conversations(
            chatwoot_reader=lambda source: (_ for _ in ()).throw(TimeoutError("bounded timeout")),
        )
        self.assertEqual(status, 504)
        self.assertFalse(result["evidence_complete"])
        self.assertFalse(result["evidence_available"])
        self.assertFalse(result["conversation_count_known"])
        self.assertIsNone(result["counts"])
        self.assertFalse(result["bulk_reset_allowed"])

    def test_human_mode_audit_never_swallows_process_control_exceptions(self):
        for exception in (SystemExit("worker abort"), KeyboardInterrupt()):
            with self.subTest(exception=type(exception).__name__):
                with self.assertRaises(type(exception)):
                    launch.audit_sam_live_stock_human_conversations(
                        chatwoot_reader=lambda source: [human_conversation(1826)],
                        review_loader=lambda conversation_id, exc=exception: (_ for _ in ()).throw(exc),
                    )
    def test_human_mode_audit_batches_review_loading_once(self):
        conversations = [
            human_conversation(1826, lane="unknown"),
            human_conversation(1827, lane="meat"),
            human_conversation(1828, lane="unknown"),
        ]
        calls = []

        def batch_loader(conversation_ids):
            calls.append(list(conversation_ids))
            return {
                "success": True,
                "events_by_conversation_id": {
                    "1826": {
                        "chatwoot_conversation_id": "1826",
                        "review_state": "active",
                    }
                },
            }, 200

        result, status = launch.audit_sam_live_stock_human_conversations(
            chatwoot_reader=lambda source: conversations,
            review_batch_loader=batch_loader,
        )
        self.assertEqual(status, 200)
        self.assertEqual(calls, [["1826", "1827", "1828"]])
        self.assertEqual(result["diagnostics"]["review_load_mode"], "single_bounded_batch")
        self.assertEqual([row["conversation_id"] for row in result["conversations"]], ["1826"])
        self.assertEqual(result["counts"]["excluded_non_livestock"], 1)
        self.assertEqual(result["counts"]["lane_unknown"], 1)
        self.assertFalse(result["bulk_reset_allowed"])

    def test_review_batch_query_is_once_bound_and_time_bounded(self):
        observed = {"execute_calls": 0}

        class Cursor:
            description = []
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def execute(self, query, params):
                observed["execute_calls"] += 1
                observed["query"] = query
                observed["params"] = params
            def fetchall(self): return []

        class Connection:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def cursor(self): return Cursor()

        def connect(database_url, **kwargs):
            observed["connect_kwargs"] = kwargs
            return Connection()

        with patch.dict("sys.modules", {"psycopg": types.SimpleNamespace(connect=connect)}):
            result, status = launch.load_latest_sam_live_stock_review_events_for_conversations(
                ["1978", "1978", "1980"], database_url="postgresql://configured"
            )

        self.assertEqual(status, 200)
        self.assertTrue(result["success"])
        self.assertEqual(observed["execute_calls"], 1)
        self.assertIn("chatwoot_conversation_id = any(%s)", observed["query"])
        self.assertNotIn("1978", observed["query"])
        self.assertEqual(observed["params"], (["1978", "1980"],))
        self.assertEqual(observed["connect_kwargs"]["connect_timeout"], launch.HUMAN_AUDIT_DATABASE_CONNECT_TIMEOUT_SECONDS)
        self.assertEqual(observed["connect_kwargs"]["options"], f"-c statement_timeout={launch.HUMAN_AUDIT_DATABASE_STATEMENT_TIMEOUT_MILLISECONDS}")

    def test_human_mode_audit_maximum_batch_is_deduplicated_and_loaded_once(self):
        conversations = [human_conversation(i, lane="livestock") for i in range(1, launch.HUMAN_AUDIT_MAX_CONVERSATIONS + 1)]
        conversations.append(human_conversation(1, lane="livestock"))
        calls = []

        def batch_loader(conversation_ids):
            calls.append(list(conversation_ids))
            return {"success": True, "events_by_conversation_id": {}}, 200

        result, status = launch.audit_sam_live_stock_human_conversations(
            chatwoot_reader=lambda source: conversations, review_batch_loader=batch_loader,
        )
        self.assertEqual(status, 200)
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(calls[0]), launch.HUMAN_AUDIT_MAX_CONVERSATIONS)
        self.assertEqual(len(set(calls[0])), launch.HUMAN_AUDIT_MAX_CONVERSATIONS)
        self.assertEqual(len(result["conversations"]), launch.HUMAN_AUDIT_MAX_CONVERSATIONS)
        self.assertLess(len(json.dumps(result)), 1_000_000)

    def test_human_mode_audit_rejects_oversized_batch_before_query(self):
        conversations = [human_conversation(i) for i in range(1, launch.HUMAN_AUDIT_MAX_CONVERSATIONS + 2)]
        calls = []
        result, status = launch.audit_sam_live_stock_human_conversations(
            chatwoot_reader=lambda source: conversations,
            review_batch_loader=lambda ids: calls.append(ids),
        )
        self.assertEqual(status, 503)
        self.assertEqual(calls, [])
        self.assertFalse(result["evidence_complete"])
        self.assertIsNone(result["counts"])

    def test_human_mode_audit_healthy_process_deadline_is_structured(self):
        ticks = iter((0.0, 21.0))
        result, status = launch.audit_sam_live_stock_human_conversations(
            chatwoot_reader=lambda source: [], clock=lambda: next(ticks),
        )
        self.assertEqual(status, 504)
        self.assertEqual(result["failure_stage"], "chatwoot_request")
        self.assertEqual(result["error_type"], "TimeoutError")
        self.assertFalse(result["evidence_complete"])
        self.assertFalse(result["writes_performed"])
if __name__ == "__main__":
    unittest.main()
