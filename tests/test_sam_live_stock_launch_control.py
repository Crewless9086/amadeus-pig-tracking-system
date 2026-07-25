import json
import inspect
import types
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Lock
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


class MessageListResponse(ChatwootFilterResponse):
    status = 200


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
        "contact_id": "99",
        "inbox_id": "77",
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


def send_action_fixture():
    inbound, facts, decision = review_inputs()
    event = launch.build_sam_live_stock_review_event(
        inbound,
        facts,
        decision,
        {"score": 99, "confidence_target": 96, "safe_to_send": True, "recommended_action": "owner_review_send_candidate"},
    )
    lifecycle_id = "SAM-LIVE-CARD-LIFECYCLE-1"
    card = {
        "conversation_id": "2401",
        "telegram_chat_id": "555",
        "telegram_message_id": "991",
        "lifecycle_card_identity": lifecycle_id,
    }
    action = launch.build_sam_live_stock_send_reply_action(
        event, card, decision["suggested_reply_text"]
    )
    return event, action, card


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
            telegram_editor=lambda token, chat_id, message_id, text, reply_markup: calls.append(("edit", chat_id, message_id, text, reply_markup)) or {"ok": True},
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
        self.assertNotIn("Send Reply", [button["text"] for row in calls[0][3]["inline_keyboard"] for button in row])
        buttons = calls[1][4]["inline_keyboard"]
        self.assertEqual(buttons[0][0]["text"], "Send Reply")
        self.assertTrue(buttons[0][0]["callback_data"].startswith("sam_live_card_send:SAM-LIVE-CARD-SEND-"))
        self.assertEqual(buttons[1][0]["text"], "Open Chatwoot")
        self.assertEqual(buttons[1][0]["url"], "https://app.chatwoot.com/app/accounts/147387/conversations/2401")
        button_labels = [button["text"] for row in buttons for button in row]
        callback_values = [button.get("callback_data", "") for row in buttons for button in row]
        self.assertIn("Keep With Me", button_labels)
        self.assertIn("No Reply — Done", button_labels)
        self.assertIn("Prepare Quote", button_labels)
        self.assertNotIn("Done — Return to SAM", button_labels)
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
        self.assertEqual(labels.count("Send Reply"), 0)
        self.assertIn("Open Chatwoot", labels)
        self.assertIn("Keep With Me", labels)
        self.assertIn("No Reply — Done", labels)
        self.assertIn("Prepare Quote", labels)
        self.assertNotIn("Done — Return to SAM", labels)
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

    def test_legacy_review_identity_send_is_withheld_without_dispatch_or_cleanup(self):
        event = {"review_event_id": "SAM-LIVE-REVIEW-1", "chatwoot_conversation_id": "2401", "sam_reply_excerpt": "Safe reply", "decision_json": {}}
        calls = []
        result, status = launch.process_sam_live_stock_owner_callback(
            {"callback_data": "sam_live_card_send:SAM-LIVE-REVIEW-1", "telegram_chat_id": "555", "telegram_message_id": "991"},
            environ={"SAM_LIVE_STOCK_OWNER_APPROVED_SEND_ENABLED": "1", "SAM_LIVE_STOCK_CHATWOOT_TAKEOVER_WRITE_ENABLED": "1", "SAM_LIVE_STOCK_TELEGRAM_CLEANUP_ENABLED": "1", "SAM_LIVE_STOCK_TELEGRAM_BOT_TOKEN": "token"},
            review_event_loader=lambda _: ({"success": True, "event": event}, 200),
            evidence_recorder=lambda item: calls.append(("evidence", item)) or ({"success": True, "created": True}, 200),
            chatwoot_sender=lambda conversation, message, source: calls.append(("send", conversation)) or {"ok": True},
            chatwoot_writer=lambda conversation, attrs, source: calls.append(("mode", attrs["conversation_mode"])) or {"ok": True},
            telegram_deleter=lambda token, chat, message: calls.append(("delete", chat, message)) or {"ok": True},
        )
        self.assertEqual(status, 409)
        self.assertEqual(result["status"], "sam_live_card_send_legacy_identity_withheld")
        self.assertEqual(calls, [])

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
        self.assertEqual(status, 409)
        self.assertEqual(result["status"], "sam_live_card_send_legacy_identity_withheld")
        self.assertEqual(calls, [])

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
        self.assertEqual(calls, [("delete", "555", "993")])

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
        self.assertEqual(result["status"], "sam_live_card_send_legacy_identity_withheld")

    def test_candidate_bound_send_claims_before_dispatch_and_retains_pending_card(self):
        review, action, card = send_action_fixture()
        calls = []
        events = []

        def load(event_id):
            event = action["event"] if event_id == action["action_identity"] else review
            return {"success": True, "event": event}, 200

        def record(event):
            events.append(event)
            calls.append(event["event_source"])
            return {"success": True, "created": True, "review_event_id": event["review_event_id"]}, 201

        result, status = launch.process_sam_live_stock_owner_callback(
            {
                "callback_data": f"sam_live_card_send:{action['action_identity']}",
                "telegram_chat_id": "555",
                "telegram_message_id": "991",
            },
            environ={"SAM_LIVE_STOCK_TELEGRAM_BOT_TOKEN": "token", "SAM_LIVE_STOCK_OWNER_APPROVED_SEND_ENABLED": "1"},
            review_event_loader=load,
            active_card_loader=lambda _: ({
                "success": True,
                "card": {**card, "state": "active"},
                "lifecycle_card_identity": card["lifecycle_card_identity"],
            }, 200),
            chronology_loader=lambda *_args, **_kwargs: {
                "id": "2401",
                "contact_id": "99",
                "inbox_id": "77",
                "can_reply": True,
                "messages": [{"id": "901", "message_type": "incoming"}],
            },
            evidence_recorder=record,
            chatwoot_sender=lambda *_args: calls.append("chatwoot") or {
                "status_code": 200,
                "body": {"id": "902", "status": "sent", "source_id": "wamid.SECRET"},
            },
            telegram_editor=lambda *_args: calls.append("telegram_edit") or {"ok": True},
        )
        self.assertEqual(status, 200)
        self.assertEqual(result["delivery_state"], "chatwoot_accepted_unverified")
        self.assertFalse(result["customer_send_confirmed"])
        self.assertTrue(result["card_retained"])
        self.assertLess(calls.index("sam_outbound_delivery_attempt_claim"), calls.index("chatwoot"))
        self.assertLess(calls.index("chatwoot"), calls.index("sam_outbound_delivery_transition"))
        self.assertNotIn("Hi Charl", str(events))
        self.assertNotIn("wamid.SECRET", str(events))

    def test_owner_send_transport_omits_application_source_id(self):
        from modules.sales import sam_live_stock_runtime
        source = inspect.getsource(sam_live_stock_runtime._send_chatwoot_message)
        body_source = source[source.index("body = {"):source.index("request = urllib_request.Request")]
        self.assertNotIn('"source_id"', body_source)
        self.assertIn('"amadeus_source"', body_source)

    def test_candidate_bound_duplicate_claim_sends_nothing(self):
        review, action, card = send_action_fixture()

        def load(event_id):
            return {"success": True, "event": action["event"] if event_id == action["action_identity"] else review}, 200

        result, status = launch.process_sam_live_stock_owner_callback(
            {
                "callback_data": f"sam_live_card_send:{action['action_identity']}",
                "telegram_chat_id": "555",
                "telegram_message_id": "991",
            },
            environ={"SAM_LIVE_STOCK_OWNER_APPROVED_SEND_ENABLED": "1"},
            review_event_loader=load,
            active_card_loader=lambda _: ({
                "success": True,
                "card": {**card, "state": "active"},
                "lifecycle_card_identity": card["lifecycle_card_identity"],
            }, 200),
            chronology_loader=lambda *_args, **_kwargs: {
                "id": "2401", "contact_id": "99", "inbox_id": "77",
                "messages": [{"id": "901", "message_type": "incoming"}],
            },
            evidence_recorder=lambda _event: ({"success": True, "created": False}, 200),
            chatwoot_sender=lambda *_args: self.fail("duplicate must not dispatch"),
        )
        self.assertEqual(status, 409)
        self.assertEqual(result["status"], "sam_live_card_send_duplicate_withheld")

    def test_concurrent_candidate_callbacks_dispatch_exactly_once(self):
        review, action, card = send_action_fixture()
        claimed = set()
        lock = Lock()
        sends = []

        def load(event_id):
            return {"success": True, "event": action["event"] if event_id == action["action_identity"] else review}, 200

        def record(event):
            if event["event_source"] != "sam_outbound_delivery_attempt_claim":
                return {"success": True, "created": True}, 201
            with lock:
                created = event["review_event_id"] not in claimed
                claimed.add(event["review_event_id"])
            return {"success": True, "created": created}, 201 if created else 200

        def invoke():
            return launch.process_sam_live_stock_owner_callback(
                {"callback_data": f"sam_live_card_send:{action['action_identity']}", "telegram_chat_id": "555", "telegram_message_id": "991"},
                environ={"SAM_LIVE_STOCK_TELEGRAM_BOT_TOKEN": "token", "SAM_LIVE_STOCK_OWNER_APPROVED_SEND_ENABLED": "1"},
                review_event_loader=load,
                active_card_loader=lambda _: ({"success": True, "card": {**card, "state": "active"}, "lifecycle_card_identity": card["lifecycle_card_identity"]}, 200),
                chronology_loader=lambda *_args, **_kwargs: {"id": "2401", "contact_id": "99", "inbox_id": "77", "can_reply": True, "messages": [{"id": "901", "message_type": "incoming"}]},
                evidence_recorder=record,
                chatwoot_sender=lambda *_args: sends.append("send") or {"status_code": 200, "body": {"id": "902", "status": "sent"}},
                telegram_editor=lambda *_args: {"ok": True},
            )

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _index: invoke(), range(2)))
        self.assertEqual(sends, ["send"])
        self.assertEqual(sorted(status for _body, status in results), [200, 409])

    def test_candidate_delivery_claim_failure_dispatches_nothing(self):
        review, action, card = send_action_fixture()

        def load(event_id):
            return {"success": True, "event": action["event"] if event_id == action["action_identity"] else review}, 200

        result, status = launch.process_sam_live_stock_owner_callback(
            {"callback_data": f"sam_live_card_send:{action['action_identity']}", "telegram_chat_id": "555", "telegram_message_id": "991"},
            environ={"SAM_LIVE_STOCK_OWNER_APPROVED_SEND_ENABLED": "1"},
            review_event_loader=load,
            active_card_loader=lambda _: ({"success": True, "card": {**card, "state": "active"}, "lifecycle_card_identity": card["lifecycle_card_identity"]}, 200),
            chronology_loader=lambda *_args, **_kwargs: {"id": "2401", "contact_id": "99", "inbox_id": "77", "messages": [{"id": "901", "message_type": "incoming"}]},
            evidence_recorder=lambda _event: ({"success": False, "created": False}, 503),
            chatwoot_sender=lambda *_args: self.fail("claim failure must not dispatch"),
        )
        self.assertEqual(status, 503)
        self.assertEqual(result["status"], "sam_live_card_send_delivery_claim_failed")

    def test_candidate_bound_send_fails_closed_on_stale_or_wrong_identity(self):
        review, action, card = send_action_fixture()

        def load(event_id):
            return {"success": True, "event": action["event"] if event_id == action["action_identity"] else review}, 200

        for chronology in (
            {"id": "2401", "contact_id": "wrong", "inbox_id": "77", "messages": [{"id": "901", "message_type": "incoming"}]},
            {"id": "2401", "contact_id": "99", "inbox_id": "77", "messages": [{"id": "901", "message_type": "incoming"}, {"id": "newer", "message_type": "incoming"}]},
        ):
            with self.subTest(chronology=chronology):
                result, status = launch.process_sam_live_stock_owner_callback(
                    {"callback_data": f"sam_live_card_send:{action['action_identity']}", "telegram_chat_id": "555", "telegram_message_id": "991"},
                    environ={"SAM_LIVE_STOCK_OWNER_APPROVED_SEND_ENABLED": "1"},
                    review_event_loader=load,
                    active_card_loader=lambda _: ({"success": True, "card": {**card, "state": "active"}, "lifecycle_card_identity": card["lifecycle_card_identity"]}, 200),
                    chronology_loader=lambda *_args, value=chronology, **_kwargs: value,
                    chatwoot_sender=lambda *_args: self.fail("stale action must not dispatch"),
                )
                self.assertEqual(status, 409)
                self.assertEqual(result["status"], "sam_live_card_send_fresh_identity_or_message_mismatch")

    def test_provider_webhook_confirms_exact_attempt_then_cleans_exact_card(self):
        review, action, card = send_action_fixture()
        attempt = launch.build_delivery_attempt(
            {"conversation_id": "2401", "contact_id": "99", "inbox_id": "77", "message_id": "901"},
            {"suggested_reply_text": review["decision_json"]["suggested_reply_text"]},
            {"review_event_id": review["review_event_id"], "owner_action_identity": action["action_identity"]},
            response_class="owner_approved_reply",
        )
        attempt["chatwoot_outgoing_message_id"] = "902"
        records = []
        result, status = launch.handle_sam_live_stock_delivery_status_webhook(
            {
                "event": "message_updated",
                "message": {
                    "id": "902", "conversation_id": "2401", "message_type": 1,
                    "status": "delivered", "source_id": "wamid.SECRET",
                },
            },
            environ={"SAM_LIVE_STOCK_TELEGRAM_BOT_TOKEN": "token", "SAM_LIVE_STOCK_TELEGRAM_CLEANUP_ENABLED": "1"},
            attempt_loader=lambda *_: {"success": True, "attempt": attempt},
            evidence_recorder=lambda event: records.append(event) or ({"success": True, "created": True}, 201),
            review_event_loader=lambda _: ({"success": True, "event": action["event"]}, 200),
            active_card_loader=lambda _: ({"success": True, "card": {**card, "state": "active"}, "lifecycle_card_identity": card["lifecycle_card_identity"]}, 200),
            telegram_deleter=lambda token, chat, message: {"ok": (chat, message)},
        )
        self.assertEqual(status, 200)
        self.assertEqual(result["status"], "sam_delivery_confirmed_card_cleaned")
        self.assertTrue(result["customer_send_confirmed"])
        self.assertEqual(records[0]["review_json"]["provider_identity_class"], "whatsapp_provider")
        self.assertNotIn("wamid.SECRET", str(records))

    def test_provider_webhook_missing_identity_is_ambiguous_and_retains_card(self):
        review, action, card = send_action_fixture()
        attempt = launch.build_delivery_attempt(
            {"conversation_id": "2401", "contact_id": "99", "inbox_id": "77", "message_id": "901"},
            {"suggested_reply_text": review["decision_json"]["suggested_reply_text"]},
            {"review_event_id": review["review_event_id"], "owner_action_identity": action["action_identity"]},
            response_class="owner_approved_reply",
        )
        attempt["chatwoot_outgoing_message_id"] = "902"
        result, status = launch.handle_sam_live_stock_delivery_status_webhook(
            {"event": "message_updated", "message": {"id": "902", "conversation_id": "2401", "message_type": 1, "status": "read"}},
            environ={"SAM_LIVE_STOCK_TELEGRAM_BOT_TOKEN": "token"},
            attempt_loader=lambda *_: {"success": True, "attempt": attempt},
            evidence_recorder=lambda _event: ({"success": True, "created": True}, 201),
            review_event_loader=lambda _: ({"success": True, "event": action["event"]}, 200),
            active_card_loader=lambda _: ({"success": True, "card": {**card, "state": "active"}, "lifecycle_card_identity": card["lifecycle_card_identity"]}, 200),
            telegram_deleter=lambda *_: self.fail("ambiguous delivery must not clean"),
            telegram_editor=lambda *_: {"ok": True},
        )
        self.assertEqual(status, 200)
        self.assertEqual(result["delivery_state"], "provider_outcome_ambiguous")
        self.assertFalse(result["customer_send_confirmed"])
        self.assertTrue(result["card_retained"])

    def _delivery_reader_source(self):
        return {
            launch.CHATWOOT_BASE_URL_ENV: "https://chatwoot.test",
            launch.CHATWOOT_ACCOUNT_ID_ENV: "147387",
            launch.CHATWOOT_TOKEN_ENV: "secret-token",
            launch.HUMAN_AUDIT_CHATWOOT_INBOX_ENV: "96568",
        }

    def _delivery_message(self, message_id="759675071", **overrides):
        row = {
            "id": int(message_id),
            "account_id": 147387,
            "conversation_id": 2017,
            "inbox_id": 96568,
            "message_type": 1,
            "private": False,
            "status": "read",
            "source_id": "wamid.SANITIZED_FIXTURE",
            "updated_at": "2026-07-25T18:00:00Z",
        }
        row.update(overrides)
        return row

    def test_exact_delivery_reader_uses_supported_message_list_and_one_page(self):
        urls = []
        def urlopen(request, timeout):
            urls.append((request.full_url, timeout))
            return MessageListResponse({"payload": [self._delivery_message()]})
        result = launch._chatwoot_read_exact_outgoing_message(
            "2017", "759675071", self._delivery_reader_source(), urlopen=urlopen
        )
        self.assertEqual(result["status_code"], 200)
        self.assertEqual(result["body"]["id"], 759675071)
        self.assertEqual(result["reader_provenance"]["pages_read"], 1)
        self.assertIn("/conversations/2017/messages?after=0", urls[0][0])
        self.assertNotIn("/messages/759675071", urls[0][0])
        self.assertLessEqual(urls[0][1], 5)

    def test_exact_delivery_reader_finds_later_bounded_page(self):
        first = [self._delivery_message(str(value), status="sent") for value in range(1, 101)]
        pages = iter([
            {"payload": first},
            {"payload": [self._delivery_message("150")]},
        ])
        result = launch._chatwoot_read_exact_outgoing_message(
            "2017", "150", self._delivery_reader_source(),
            urlopen=lambda *_args, **_kwargs: MessageListResponse(next(pages)),
        )
        self.assertEqual(result["status_code"], 200)
        self.assertEqual(result["body"]["id"], 150)
        self.assertEqual(result["reader_provenance"]["pages_read"], 2)
        self.assertEqual(result["reader_provenance"]["rows_read"], 101)

    def test_exact_delivery_reader_zero_duplicate_incomplete_and_malformed_fail_closed(self):
        cases = {
            "zero": ([{"payload": []}], "reader_exact_message_not_found"),
            "duplicate": ([{"payload": [self._delivery_message(), self._delivery_message()]}], "reader_duplicate_exact_message"),
            "malformed": ([{"unexpected": []}], "reader_envelope_malformed"),
            "incomplete": (
                [
                    {"payload": [self._delivery_message(str(value), status="sent") for value in range(1, 101)]},
                    {"payload": [self._delivery_message(str(value), status="sent") for value in range(101, 201)]},
                    {"payload": [self._delivery_message(str(value), status="sent") for value in range(201, 301)]},
                ],
                "reader_pagination_incomplete",
            ),
        }
        for name, (payloads, reason) in cases.items():
            with self.subTest(name=name):
                pages = iter(payloads)
                result = launch._chatwoot_read_exact_outgoing_message(
                    "2017", "759675071", self._delivery_reader_source(),
                    urlopen=lambda *_args, **_kwargs: MessageListResponse(next(pages)),
                )
                self.assertIsNone(result["status_code"])
                self.assertEqual(result["reader_provenance"]["failure_class"], reason)

    def test_exact_delivery_reader_rejects_identity_direction_private_and_status_collisions(self):
        cases = {
            "account": ({"account_id": 999}, "reader_account_mismatch"),
            "conversation": ({"conversation_id": 999}, "reader_exact_identity_mismatch"),
            "inbox": ({"inbox_id": 999}, "reader_inbox_mismatch"),
            "incoming": ({"message_type": 0}, "reader_message_not_outgoing"),
            "private": ({"private": True}, "reader_message_not_public"),
            "wrong_id_same_content": ({"id": 759675999, "content": "same"}, "reader_exact_message_not_found"),
            "missing_status": ({"status": ""}, "reader_status_malformed"),
            "unknown_status": ({"status": "mystery"}, "reader_status_malformed"),
            "conflicting_status": ({"status": "read", "delivery_status": "failed"}, "reader_identity_or_status_conflict"),
        }
        for name, (patch, reason) in cases.items():
            with self.subTest(name=name):
                result = launch._chatwoot_read_exact_outgoing_message(
                    "2017", "759675071", self._delivery_reader_source(),
                    urlopen=lambda *_args, value=patch, **_kwargs: MessageListResponse({
                        "payload": [self._delivery_message(**value)]
                    }),
                )
                self.assertIsNone(result["status_code"])
                self.assertEqual(result["reader_provenance"]["failure_class"], reason)

    def test_conversation_2017_malformed_webhook_recovers_exact_delivered_message(self):
        review, action, card = send_action_fixture()
        attempt = launch.build_delivery_attempt(
            {"conversation_id": "2017", "contact_id": "699428938", "inbox_id": "96568", "message_id": "759674171"},
            {"suggested_reply_text": review["decision_json"]["suggested_reply_text"]},
            {"review_event_id": review["review_event_id"], "owner_action_identity": action["action_identity"]},
            response_class="owner_approved_reply",
        )
        attempt["conversation_id"] = "2017"
        attempt["inbox_id"] = "96568"
        attempt["chatwoot_outgoing_message_id"] = "759675071"
        action["event"]["review_json"]["send_reply_action"].update({
            "conversation_id": "2017",
            "telegram_chat_id": card["telegram_chat_id"],
            "telegram_message_id": card["telegram_message_id"],
        })
        records = []
        result, status = launch.handle_sam_live_stock_delivery_status_webhook(
            {
                "event": "message_updated",
                "account": {"id": "147387"},
                "conversation": {"id": "2017", "inbox_id": "96568"},
                "message": {
                    "id": "759675071", "conversation_id": "2017",
                    "message_type": "outgoing",
                    "source_id": "wamid.SANITIZED_FIXTURE",
                },
            },
            environ={
                launch.CHATWOOT_ACCOUNT_ID_ENV: "147387",
                launch.TELEGRAM_BOT_TOKEN_ENV: "token",
                launch.TELEGRAM_CLEANUP_ENABLED_ENV: "1",
            },
            attempt_loader=lambda *_: {"success": True, "attempt": attempt},
            reconciliation_loader=lambda *_: {
                "status_code": 200,
                "body": {
                    "id": "759675071", "conversation_id": "2017",
                    "status": "delivered", "source_id": "wamid.SANITIZED_FIXTURE",
                },
            },
            evidence_recorder=lambda event: records.append(event) or ({"success": True, "created": True}, 201),
            review_event_loader=lambda _: ({"success": True, "event": action["event"]}, 200),
            active_card_loader=lambda _: ({
                "success": True,
                "card": {**card, "conversation_id": "2017", "state": "active"},
                "lifecycle_card_identity": card["lifecycle_card_identity"],
            }, 200),
            telegram_deleter=lambda *_: {"ok": True},
        )
        self.assertEqual(status, 200)
        self.assertEqual(result["delivery_state"], "provider_delivered")
        self.assertEqual(
            records[0]["review_json"]["reconciliation_source"],
            "chatwoot_exact_outgoing_message_read",
        )

    def test_accepted_dispatch_card_edit_ambiguity_returns_no_retry_business_truth(self):
        review, action, card = send_action_fixture()
        def load(event_id):
            return {"success": True, "event": action["event"] if event_id == action["action_identity"] else review}, 200
        result, status = launch.process_sam_live_stock_owner_callback(
            {
                "callback_data": f"sam_live_card_send:{action['action_identity']}",
                "telegram_chat_id": "555",
                "telegram_message_id": "991",
            },
            environ={
                launch.TELEGRAM_BOT_TOKEN_ENV: "token",
                "SAM_LIVE_STOCK_OWNER_APPROVED_SEND_ENABLED": "1",
            },
            review_event_loader=load,
            active_card_loader=lambda _: ({
                "success": True, "card": {**card, "state": "active"},
                "lifecycle_card_identity": card["lifecycle_card_identity"],
            }, 200),
            chronology_loader=lambda *_args, **_kwargs: {
                "id": "2401", "contact_id": "99", "inbox_id": "77",
                "can_reply": True,
                "messages": [{"id": "901", "message_type": "incoming"}],
            },
            evidence_recorder=lambda _event: ({"success": True, "created": True}, 201),
            chatwoot_sender=lambda *_: {
                "status_code": 200, "body": {"id": "902", "status": "sent"},
            },
            telegram_editor=lambda *_: (_ for _ in ()).throw(TimeoutError("ambiguous edit")),
        )
        self.assertEqual(status, 200)
        self.assertTrue(result["success"])
        self.assertEqual(result["delivery_state"], "chatwoot_accepted_unverified")
        self.assertTrue(result["card_update_ambiguous"])
        self.assertTrue(result["automatic_retry_prohibited"])

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
            chronology_loader=lambda *_args, **_kwargs: {
                "id": "2401",
                "custom_attributes": {"conversation_mode": "HUMAN"},
                "messages": [],
            },
        )
        self.assertEqual(status, 200)
        self.assertEqual(result["telegram_cleanup"]["status"], "sam_live_stock_owner_card_resolved_by_edit")
        self.assertEqual(edits, [("555", "996", "Resolved", {"inline_keyboard": []})])

    def test_done_return_to_sam_requires_proven_human_before_auto_or_cleanup(self):
        event = {"review_event_id": "SAM-LIVE-REVIEW-HUMAN", "chatwoot_conversation_id": "2401", "decision_json": {}}
        calls = []
        result, status = launch.process_sam_live_stock_owner_callback(
            {"callback_data": "sam_live_card_done:SAM-LIVE-REVIEW-HUMAN", "telegram_chat_id": "555", "telegram_message_id": "996"},
            environ={"SAM_LIVE_STOCK_TELEGRAM_BOT_TOKEN": "token"},
            review_event_loader=lambda _: ({"success": True, "event": event}, 200),
            evidence_recorder=lambda _item: ({"success": True, "created": True}, 200),
            chronology_loader=lambda *_args, **_kwargs: {
                "id": "2401", "custom_attributes": {"conversation_mode": "AUTO"}, "messages": [],
            },
            chatwoot_writer=lambda *_args: calls.append("auto") or {"ok": True},
            telegram_deleter=lambda *_args: calls.append("delete") or {"ok": True},
            telegram_editor=lambda *_args: calls.append("retain_edit") or {"ok": True},
        )
        self.assertEqual(status, 502)
        self.assertEqual(result["failed_step"], "human_ownership_unproven")
        self.assertEqual(calls, ["retain_edit"])

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
        self.assertTrue(result["action_contract"]["conversation_ownership_independent_of_business_lane"])
        self.assertTrue(result["action_contract"]["business_lane_required_only_before_specialist_tools_or_protected_claims"])

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

    def test_conversation_1983_resolves_exact_card_only_when_human_is_unproven(self):
        conversation = {
            "id": 1983,
            "review_event_id": "SAM-LIVE-REVIEW-1983",
            "custom_attributes": {"conversation_mode": "HUMAN", "sales_lane": "unknown"},
            "messages": [
                {"id": 758530001, "message_type": "incoming", "created_at": "2026-07-25T08:00:00Z"},
                {"id": 758530099, "message_type": "outgoing", "created_at": "2026-07-25T08:05:00Z"},
            ],
        }
        cards = [{
            "conversation_id": 1983,
            "review_event_id": "SAM-LIVE-REVIEW-1983",
            "customer_message_id": 758530001,
            "telegram_message_id": 2865,
            "created_at": "2026-07-25T08:01:00Z",
            "authoritative": True,
        }]

        result = launch.reconcile_sam_live_stock_exact_cards(conversation, cards)

        self.assertTrue(result["success"])
        self.assertEqual(result["ownership"], "AUTO_GENERAL")
        self.assertFalse(result["human_ownership_proven"])
        self.assertEqual(result["business_lane"], "unknown")
        self.assertEqual(result["newest_authoritative_actionable_telegram_message_id"], "2865")
        self.assertEqual(result["cards"], [{
            "telegram_message_id": "2865",
            "customer_message_id": "758530001",
            "classification": "answered_already_auto_or_unproven",
            "business_lane": "unknown",
            "action": "resolve_card_only",
            "chatwoot_mode_mutation": False,
            "customer_send": False,
            "specialist_or_business_rail": False,
        }])
        self.assertFalse(result["writes_performed"])
        self.assertFalse(result["sends_customer_message"])
        self.assertFalse(result["calls_specialist_rail"])
        self.assertFalse(result["calls_business_rail"])
        self.assertEqual(result, launch.reconcile_sam_live_stock_exact_cards(conversation, cards))

    def test_exact_card_reconciliation_requires_proven_human_before_auto_candidate(self):
        conversation = {
            "id": "2001",
            "review_event_id": "SAM-LIVE-REVIEW-2001",
            "custom_attributes": {"conversation_mode": "HUMAN", "sales_lane": "meat_sales"},
            "ownership_evidence": {"human_takeover_proven": True},
            "messages": [
                {"id": "customer-1", "direction": "incoming", "created_at": 100},
                {"id": "owner-1", "direction": "outgoing", "created_at": 120},
            ],
        }
        cards = [{
            "conversation_id": "2001", "customer_message_id": "customer-1",
            "review_event_id": "SAM-LIVE-REVIEW-2001",
            "telegram_message_id": "3001", "created_at": 110, "authoritative": True,
        }]

        result = launch.reconcile_sam_live_stock_exact_cards(conversation, cards)

        self.assertEqual(result["ownership"], "HUMAN")
        self.assertEqual(result["business_lane"], "meat")
        self.assertEqual(result["cards"][0]["classification"], "answered_still_human")
        self.assertEqual(result["cards"][0]["action"], "candidate_auto_then_resolve")
        self.assertFalse(result["cards"][0]["chatwoot_mode_mutation"])

    def test_exact_card_reconciliation_retains_card_for_newer_unanswered_message(self):
        conversation = {
            "id": "2002",
            "review_event_id": "SAM-LIVE-REVIEW-2002",
            "custom_attributes": {"conversation_ownership": "AUTO_SPECIALIST", "sales_lane": "live_stock_sales"},
            "messages": [
                {"id": "customer-1", "direction": "incoming", "created_at": 100},
                {"id": "owner-1", "direction": "outgoing", "created_at": 120},
                {"id": "customer-2", "direction": "incoming", "created_at": 130},
            ],
        }
        cards = [{
            "conversation_id": "2002", "customer_message_id": "customer-1",
            "review_event_id": "SAM-LIVE-REVIEW-2002",
            "telegram_message_id": "3002", "created_at": 110, "authoritative": True,
        }]

        result = launch.reconcile_sam_live_stock_exact_cards(conversation, cards)

        self.assertEqual(result["cards"][0]["classification"], "unanswered")
        self.assertEqual(result["cards"][0]["action"], "retain_exact_card")

    def test_duplicate_card_cleanup_needs_exact_supersession_and_protects_newest(self):
        conversation = {
            "id": "2003",
            "review_event_id": "SAM-LIVE-REVIEW-2003",
            "custom_attributes": {"conversation_ownership": "AUTO_GENERAL"},
            "messages": [
                {"id": "customer-1", "direction": "incoming", "created_at": 100},
                {"id": "owner-1", "direction": "outgoing", "created_at": 140},
            ],
        }
        cards = [
            {
                "conversation_id": "2003", "customer_message_id": "customer-1",
                "review_event_id": "SAM-LIVE-REVIEW-2003",
                "telegram_message_id": "3003", "created_at": 110, "authoritative": True,
            },
            {
                "conversation_id": "2003", "customer_message_id": "customer-1",
                "review_event_id": "SAM-LIVE-REVIEW-2003",
                "telegram_message_id": "3004", "created_at": 120, "authoritative": True,
                "supersedes_telegram_message_id": "3003",
            },
        ]

        result = launch.reconcile_sam_live_stock_exact_cards(conversation, cards)

        self.assertEqual(result["newest_authoritative_actionable_telegram_message_id"], "3004")
        self.assertEqual(result["cards"][0]["classification"], "duplicate_superseded")
        self.assertEqual(result["cards"][0]["action"], "resolve_card_only")
        self.assertEqual(result["cards"][1]["classification"], "answered_already_auto_or_unproven")

        without_exact_evidence = launch.reconcile_sam_live_stock_exact_cards(
            conversation, [{**cards[0]}, {**cards[1], "supersedes_telegram_message_id": ""}],
        )
        self.assertNotIn("duplicate_superseded", [row["classification"] for row in without_exact_evidence["cards"]])

    def test_incomplete_or_conflicting_exact_card_evidence_is_no_action(self):
        malformed = launch.reconcile_sam_live_stock_exact_cards(
            {
                "id": "2004", "review_event_id": "SAM-LIVE-REVIEW-2004",
                "messages": [{"id": "customer", "direction": "incoming"}],
            },
            [],
        )
        self.assertFalse(malformed["success"])
        self.assertEqual(malformed["status"], "message_evidence_conflicting")
        self.assertEqual(malformed["cards"], [])

        conflicting = launch.reconcile_sam_live_stock_exact_cards(
            {
                "id": "2004",
                "review_event_id": "SAM-LIVE-REVIEW-2004",
                "messages": [
                    {"id": "customer", "direction": "incoming", "created_at": 100},
                    {"id": "owner", "direction": "outgoing", "created_at": 120},
                ],
            },
            [{
                "conversation_id": "2004", "customer_message_id": "customer",
                "review_event_id": "SAM-LIVE-REVIEW-2004",
                "telegram_message_id": "3005", "created_at": 110,
                "authoritative": True, "evidence_conflicting": True,
            }],
        )
        self.assertEqual(conflicting["cards"][0]["classification"], "uncertain")
        self.assertEqual(conflicting["cards"][0]["action"], "no_action")

    def test_general_and_unknown_ownership_model_never_invokes_specialist_rails(self):
        for lane in ("general", "unknown", "other_enquiry"):
            with self.subTest(lane=lane):
                result = launch.reconcile_sam_live_stock_exact_cards(
                    {
                        "id": f"general-{lane}",
                        "review_event_id": f"SAM-LIVE-REVIEW-{lane}",
                        "custom_attributes": {"conversation_ownership": "AUTO_GENERAL", "sales_lane": lane},
                        "messages": [
                            {"id": "customer", "direction": "incoming", "created_at": 100},
                            {"id": "owner", "direction": "outgoing", "created_at": 120},
                        ],
                    },
                    [{
                        "conversation_id": f"general-{lane}", "customer_message_id": "customer",
                        "review_event_id": f"SAM-LIVE-REVIEW-{lane}",
                        "telegram_message_id": "4001", "created_at": 110, "authoritative": True,
                    }],
                )
                self.assertFalse(result["calls_specialist_rail"])
                self.assertFalse(result["calls_business_rail"])
                self.assertFalse(result["sends_customer_message"])

    def test_human_unproven_unanswered_retains_card_and_never_enables_send(self):
        conversation = {
            "id": "2005",
            "review_event_id": "SAM-LIVE-REVIEW-2005",
            "custom_attributes": {"conversation_mode": "HUMAN", "sales_lane": "unknown"},
            "messages": [{"id": "customer", "direction": "incoming", "created_at": 100}],
        }
        cards = [{
            "conversation_id": "2005", "review_event_id": "SAM-LIVE-REVIEW-2005",
            "customer_message_id": "customer", "telegram_message_id": "4002",
            "created_at": 110, "authoritative": True,
        }]

        result = launch.reconcile_sam_live_stock_exact_cards(conversation, cards)

        self.assertEqual(result["ownership"], "AUTO_GENERAL")
        self.assertFalse(result["human_ownership_proven"])
        self.assertEqual(result["cards"][0]["classification"], "unanswered")
        self.assertEqual(result["cards"][0]["action"], "retain_exact_card")
        self.assertFalse(result["sends_customer_message"])
        self.assertFalse(result["cards"][0]["customer_send"])
        self.assertFalse(result["writes_performed"])

    def test_exact_card_or_review_identity_mismatch_fails_closed(self):
        conversation = {
            "id": "2006",
            "review_event_id": "SAM-LIVE-REVIEW-2006",
            "messages": [{"id": "customer", "direction": "incoming", "created_at": 100}],
        }
        exact_card = {
            "conversation_id": "2006", "review_event_id": "SAM-LIVE-REVIEW-2006",
            "customer_message_id": "customer", "telegram_message_id": "4003",
            "created_at": 110, "authoritative": True,
        }
        for changed, expected in (
            ({"conversation_id": "other"}, "card_evidence_incomplete"),
            ({"review_event_id": "SAM-LIVE-REVIEW-OTHER"}, "card_evidence_incomplete"),
            ({"customer_message_id": "other"}, "card_evidence_mismatch"),
        ):
            with self.subTest(changed=changed, expected=expected):
                result = launch.reconcile_sam_live_stock_exact_cards(
                    conversation, [{**exact_card, **changed}],
                )
                self.assertFalse(result["success"])
                self.assertEqual(result["status"], expected)
                self.assertEqual(result["cards"], [])
                self.assertFalse(result["writes_performed"])
                self.assertFalse(result["sends_customer_message"])

    def test_missing_conversation_card_or_review_identity_fails_closed(self):
        conversation = {
            "id": "2007",
            "review_event_id": "SAM-LIVE-REVIEW-2007",
            "messages": [{"id": "customer", "direction": "incoming", "created_at": 100}],
        }
        card = {
            "conversation_id": "2007", "review_event_id": "SAM-LIVE-REVIEW-2007",
            "customer_message_id": "customer", "telegram_message_id": "4004",
            "created_at": 110, "authoritative": True,
        }
        cases = (
            ({**conversation, "id": ""}, card, "reconciliation_identity_incomplete"),
            ({**conversation, "review_event_id": ""}, card, "reconciliation_identity_incomplete"),
            (conversation, {**card, "telegram_message_id": ""}, "card_evidence_incomplete"),
            (conversation, {**card, "review_event_id": ""}, "card_evidence_incomplete"),
        )
        for changed_conversation, changed_card, expected in cases:
            with self.subTest(expected=expected):
                result = launch.reconcile_sam_live_stock_exact_cards(changed_conversation, [changed_card])
                self.assertFalse(result["success"])
                self.assertEqual(result["status"], expected)
                self.assertEqual(result["cards"], [])

    def test_cross_conversation_card_cannot_supersede_exact_card(self):
        conversation = {
            "id": "2008",
            "review_event_id": "SAM-LIVE-REVIEW-2008",
            "messages": [
                {"id": "customer", "direction": "incoming", "created_at": 100},
                {"id": "owner", "direction": "outgoing", "created_at": 140},
            ],
        }
        cards = [
            {
                "conversation_id": "2008", "review_event_id": "SAM-LIVE-REVIEW-2008",
                "customer_message_id": "customer", "telegram_message_id": "4005",
                "created_at": 110, "authoritative": True,
            },
            {
                "conversation_id": "other", "review_event_id": "SAM-LIVE-REVIEW-2008",
                "customer_message_id": "customer", "telegram_message_id": "4006",
                "created_at": 120, "authoritative": True,
                "supersedes_telegram_message_id": "4005",
            },
        ]

        result = launch.reconcile_sam_live_stock_exact_cards(conversation, cards)

        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "card_evidence_incomplete")
        self.assertEqual(result["cards"], [])
        self.assertFalse(result["writes_performed"])

    def _resolve_card_fixture(self, generation="reconcile-1983-recovery-2"):
        conversation = {
            "id": "1983",
            "review_event_id": "SAM-LIVE-REVIEW-FD17FD894C2B",
            "custom_attributes": {"conversation_mode": "HUMAN", "sales_lane": "unknown"},
            "messages": [
                {"id": "758530001", "message_type": 0, "created_at": 100},
                {"id": "758530099", "message_type": 1, "created_at": 120},
            ],
        }
        card = {
            "conversation_id": "1983",
            "review_event_id": "SAM-LIVE-REVIEW-FD17FD894C2B",
            "customer_message_id": "758530001",
            "telegram_chat_id": "555",
            "telegram_message_id": "2865",
            "created_at": 110,
            "authoritative": True,
        }
        built = launch.build_sam_live_stock_resolve_card_candidate(
            conversation,
            card,
            reconciliation_generation=generation,
            lifecycle_card_identity="SAM-LIVE-CARD-8FF523977E92",
        )
        original = {
            "review_event_id": "SAM-LIVE-REVIEW-FD17FD894C2B",
            "chatwoot_conversation_id": "1983",
            "chatwoot_message_id": "758530001",
        }
        candidate_event = launch.build_sam_live_stock_resolve_candidate_event(
            original, built.get("candidate"),
        )
        return conversation, card, built, original, candidate_event

    def _resolve_active_card_loader(self, built):
        candidate = built["candidate"]
        return lambda conversation_id: ({
            "success": True,
            "lifecycle_card_identity": candidate["lifecycle_card_identity"],
            "card": {
                "conversation_id": candidate["conversation_id"],
                "telegram_chat_id": candidate["telegram_chat_id"],
                "telegram_message_id": candidate["telegram_message_id"],
                "state": "action_failed",
            },
        }, 200)

    def test_resolve_card_planner_renderer_callback_and_executor_share_one_action(self):
        conversation, card, built, original, candidate_event = self._resolve_card_fixture()
        self.assertTrue(built["success"])
        self.assertEqual(built["reconciliation"]["cards"][0]["action"], "resolve_card_only")
        self.assertEqual(built["button"]["text"], "Resolve Card")
        self.assertEqual(built["button"]["action"], "resolve_card_only")
        self.assertEqual(
            built["button"]["callback_data"],
            f"sam_live_card_resolve:{built['candidate']['action_identity']}",
        )
        parsed = launch._callback_action(built["button"]["callback_data"])
        self.assertEqual(parsed, {
            "action": "resolve_card_only",
            "escalation_id": built["candidate"]["action_identity"],
        })

        calls = {"records": [], "deletes": [], "chatwoot": [], "customers": []}

        def loader(identity):
            event = candidate_event if identity == built["candidate"]["action_identity"] else original
            return {"success": True, "event": event}, 200

        def recorder(event):
            calls["records"].append(event)
            return {"success": True, "created": True, "review_event_id": event["review_event_id"]}, 201

        result, status = launch.process_sam_live_stock_owner_callback(
            {
                "callback_data": built["button"]["callback_data"],
                "telegram_chat_id": "555",
                "telegram_message_id": "2865",
            },
            environ={
                launch.TELEGRAM_CLEANUP_ENABLED_ENV: "1",
                launch.TELEGRAM_BOT_TOKEN_ENV: "token",
            },
            review_event_loader=loader,
            active_card_loader=self._resolve_active_card_loader(built),
            chronology_loader=lambda conversation_id, source: conversation,
            evidence_recorder=recorder,
            telegram_deleter=lambda token, chat_id, message_id: calls["deletes"].append(
                (chat_id, message_id)
            ) or {"ok": True},
            chatwoot_writer=lambda *args: calls["chatwoot"].append(args),
            chatwoot_sender=lambda *args: calls["customers"].append(args),
        )
        self.assertEqual(status, 200)
        self.assertTrue(result["success"])
        self.assertEqual(result["action"], "resolve_card_only")
        self.assertEqual(result["cleanup_mode"], "deleted")
        self.assertEqual(calls["deletes"], [("555", "2865")])
        self.assertEqual(calls["chatwoot"], [])
        self.assertEqual(calls["customers"], [])
        self.assertFalse(result["calls_chatwoot"])
        self.assertFalse(result["sends_customer_message"])
        self.assertFalse(result["creates_order"])
        self.assertFalse(result["reserves_stock"])
        self.assertFalse(result["changes_stock"])
        self.assertFalse(result["writes_farm_data"])
        self.assertEqual(calls["records"][0]["review_json"]["resolve_card_only"]["state"], "action_claimed")
        self.assertEqual(calls["records"][1]["review_json"]["owner_card"]["state"], "resolved")
        self.assertEqual(calls["records"][1]["review_json"]["owner_card"]["action"], "resolve_card_only")
        self.assertEqual(calls["records"][2]["review_json"]["resolve_card_only"]["state"], "resolved")
        self.assertEqual(calls["records"][2]["recommended_action"], "resolve_card_only_deleted")

    def test_resolve_card_delete_unavailable_edits_only_exact_card_resolved_without_keyboard(self):
        conversation, _card, built, original, candidate_event = self._resolve_card_fixture()
        edits = []
        records = []

        def loader(identity):
            return {
                "success": True,
                "event": candidate_event if identity == built["candidate"]["action_identity"] else original,
            }, 200

        result, status = launch.process_sam_live_stock_owner_callback(
            {
                "callback_data": built["button"]["callback_data"],
                "telegram_chat_id": "555",
                "telegram_message_id": "2865",
            },
            environ={launch.TELEGRAM_BOT_TOKEN_ENV: "token"},
            review_event_loader=loader,
            active_card_loader=self._resolve_active_card_loader(built),
            chronology_loader=lambda *_args: conversation,
            evidence_recorder=lambda event: records.append(event) or (
                {"success": True, "created": True}, 201
            ),
            telegram_editor=lambda token, chat_id, message_id, text, markup: edits.append(
                (chat_id, message_id, text, markup)
            ) or {"ok": True},
        )
        self.assertEqual(status, 200)
        self.assertEqual(result["cleanup_mode"], "resolved_edit")
        self.assertEqual(edits, [("555", "2865", "Resolved", {"inline_keyboard": []})])
        self.assertEqual(records[-2]["review_json"]["owner_card"]["state"], "resolved")
        self.assertEqual(records[-1]["review_json"]["resolve_card_only"]["state"], "resolved")
        self.assertEqual(records[-1]["recommended_action"], "resolve_card_only_resolved_edit")

    def test_resolve_card_button_is_exposed_only_after_candidate_persistence(self):
        conversation, card, built, original, _candidate_event = self._resolve_card_fixture()
        records = []
        prepared = launch.prepare_sam_live_stock_resolve_card_action(
            conversation,
            card,
            reconciliation_generation=built["candidate"]["reconciliation_generation"],
            lifecycle_card_identity=built["candidate"]["lifecycle_card_identity"],
            original_event=original,
            evidence_recorder=lambda event: records.append(event) or (
                {"success": True, "created": True}, 201
            ),
        )
        self.assertTrue(prepared["success"])
        self.assertEqual(prepared["status"], "resolve_card_candidate_persisted")
        self.assertEqual(prepared["button"]["text"], "Resolve Card")
        self.assertEqual(records[0]["review_event_id"], prepared["candidate"]["action_identity"])

        withheld = launch.prepare_sam_live_stock_resolve_card_action(
            conversation,
            card,
            reconciliation_generation="new-generation",
            lifecycle_card_identity=built["candidate"]["lifecycle_card_identity"],
            original_event=original,
            evidence_recorder=lambda event: ({"success": False}, 503),
        )
        self.assertFalse(withheld["success"])
        self.assertEqual(withheld["button"], {})

    def test_resolve_card_newer_customer_message_invalidates_before_claim(self):
        conversation, _card, built, original, candidate_event = self._resolve_card_fixture()
        conversation["messages"].append(
            {"id": "new-customer", "message_type": 0, "created_at": 130}
        )
        records = []
        result, status = launch.execute_sam_live_stock_resolve_card_only(
            candidate_event,
            {"telegram_chat_id": "555", "telegram_message_id": "2865"},
            review_event_loader=lambda identity: ({"success": True, "event": original}, 200),
            active_card_loader=self._resolve_active_card_loader(built),
            chronology_loader=lambda *_args: conversation,
            evidence_recorder=lambda event: records.append(event),
            telegram_deleter=lambda *args: self.fail("cleanup must not run"),
        )
        self.assertEqual(status, 409)
        self.assertEqual(result["status"], "resolve_card_fresh_chronology_invalidated")
        self.assertTrue(result["card_retained"])
        self.assertEqual(records, [])

    def test_resolve_card_identity_mismatch_and_missing_evidence_retain_card(self):
        conversation, _card, built, original, candidate_event = self._resolve_card_fixture()
        for payload in (
            {"telegram_chat_id": "other", "telegram_message_id": "2865"},
            {"telegram_chat_id": "555", "telegram_message_id": "other"},
            {"telegram_chat_id": "", "telegram_message_id": ""},
        ):
            with self.subTest(payload=payload):
                result, status = launch.execute_sam_live_stock_resolve_card_only(
                    candidate_event,
                    payload,
                    review_event_loader=lambda identity: ({"success": True, "event": original}, 200),
                    chronology_loader=lambda *_args: conversation,
                )
                self.assertEqual(status, 409)
                self.assertEqual(result["status"], "resolve_card_exact_telegram_identity_mismatch")
                self.assertTrue(result["card_retained"])

        tampered = json.loads(json.dumps(candidate_event))
        tampered["review_json"]["resolve_card_only"]["lifecycle_card_identity"] = "other"
        result, status = launch.execute_sam_live_stock_resolve_card_only(
            tampered,
            {"telegram_chat_id": "555", "telegram_message_id": "2865"},
        )
        self.assertEqual(status, 409)
        self.assertEqual(result["status"], "resolve_card_candidate_invalid")

    def test_resolve_card_latest_active_card_mismatch_fails_before_claim(self):
        conversation, _card, built, original, candidate_event = self._resolve_card_fixture()
        records = []
        result, status = launch.execute_sam_live_stock_resolve_card_only(
            candidate_event,
            {"telegram_chat_id": "555", "telegram_message_id": "2865"},
            review_event_loader=lambda identity: ({"success": True, "event": original}, 200),
            active_card_loader=lambda conversation_id: ({
                "success": True,
                "lifecycle_card_identity": "SAM-LIVE-CARD-NEWER",
                "card": {
                    "conversation_id": conversation_id,
                    "telegram_chat_id": "555",
                    "telegram_message_id": "9999",
                },
            }, 200),
            chronology_loader=lambda *_args: conversation,
            evidence_recorder=lambda event: records.append(event),
            telegram_deleter=lambda *args: self.fail("cleanup must not run"),
        )
        self.assertEqual(status, 409)
        self.assertEqual(result["status"], "resolve_card_active_identity_mismatch")
        self.assertTrue(result["card_retained"])
        self.assertEqual(records, [])

    def test_resolve_card_ambiguous_delete_records_failure_and_never_falls_back_or_retries(self):
        conversation, _card, built, original, candidate_event = self._resolve_card_fixture()
        records = []
        edits = []
        result, status = launch.execute_sam_live_stock_resolve_card_only(
            candidate_event,
            {"telegram_chat_id": "555", "telegram_message_id": "2865"},
            environ={
                launch.TELEGRAM_CLEANUP_ENABLED_ENV: "1",
                launch.TELEGRAM_BOT_TOKEN_ENV: "token",
            },
            review_event_loader=lambda identity: ({"success": True, "event": original}, 200),
            active_card_loader=self._resolve_active_card_loader(built),
            chronology_loader=lambda *_args: conversation,
            evidence_recorder=lambda event: records.append(event) or (
                {"success": True, "created": True}, 201
            ),
            telegram_deleter=lambda *args: (_ for _ in ()).throw(TimeoutError("unknown outcome")),
            telegram_editor=lambda *args: edits.append(args),
        )
        self.assertEqual(status, 502)
        self.assertEqual(result["status"], "resolve_card_cleanup_outcome_ambiguous")
        self.assertTrue(result["automatic_retry_prohibited"])
        self.assertEqual(edits, [])
        self.assertEqual(records[-1]["review_json"]["resolve_card_only"]["state"], "cleanup_failed")
        self.assertEqual(
            records[-1]["review_json"]["resolve_card_only"]["outcome"],
            "telegram_delete_outcome_ambiguous",
        )

    def test_resolve_card_replay_and_concurrent_duplicate_are_withheld_by_one_claim(self):
        conversation, _card, built, original, candidate_event = self._resolve_card_fixture()
        created_ids = set()
        deletes = []
        record_lock = Lock()

        def recorder(event):
            with record_lock:
                created = event["review_event_id"] not in created_ids
                created_ids.add(event["review_event_id"])
            return {"success": True, "created": created}, 201 if created else 200

        def execute():
            return launch.execute_sam_live_stock_resolve_card_only(
                candidate_event,
                {"telegram_chat_id": "555", "telegram_message_id": "2865"},
                environ={
                    launch.TELEGRAM_CLEANUP_ENABLED_ENV: "1",
                    launch.TELEGRAM_BOT_TOKEN_ENV: "token",
                },
                review_event_loader=lambda identity: ({"success": True, "event": original}, 200),
                active_card_loader=self._resolve_active_card_loader(built),
                chronology_loader=lambda *_args: conversation,
                evidence_recorder=recorder,
                telegram_deleter=lambda *args: deletes.append(args) or {"ok": True},
            )

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _index: execute(), range(2)))
        statuses = sorted(status for _result, status in results)
        self.assertEqual(statuses, [200, 409])
        replay = next(result for result, status in results if status == 409)
        self.assertEqual(replay["status"], "resolve_card_replay_withheld")
        self.assertTrue(replay["automatic_retry_prohibited"])
        self.assertEqual(len(deletes), 1)

        replay_again, replay_again_status = execute()
        self.assertEqual(replay_again_status, 409)
        self.assertEqual(replay_again["status"], "resolve_card_replay_withheld")
        self.assertEqual(len(deletes), 1)

    def test_failed_legacy_card_done_claim_is_immutable_and_new_generation_is_distinct(self):
        _conversation, _card, first, _original, _event = self._resolve_card_fixture(
            generation="reconcile-1983-original"
        )
        _conversation, _card, recovery, _original, _event = self._resolve_card_fixture(
            generation="reconcile-1983-recovery-2"
        )
        legacy_claim = {
            "review_event_id": "SAM-LIVE-CARD-22F84CA344BB",
            "state": "action_claimed",
            "action": "card_done",
        }
        legacy_failure = {
            "review_event_id": "SAM-LIVE-CARD-4CC9101B8670",
            "state": "action_failed",
            "action": "card_done:chatwoot_auto_failed",
        }
        before = json.dumps([legacy_claim, legacy_failure], sort_keys=True)
        self.assertNotEqual(
            first["candidate"]["action_identity"],
            recovery["candidate"]["action_identity"],
        )
        self.assertTrue(recovery["button"]["callback_data"].startswith("sam_live_card_resolve:"))
        self.assertEqual(json.dumps([legacy_claim, legacy_failure], sort_keys=True), before)

    def test_proven_human_keeps_done_return_to_sam_button_and_ordering(self):
        row = {"action": "candidate_auto_then_resolve"}
        button = launch.build_sam_live_stock_reconciliation_button(
            row, review_event_id="SAM-LIVE-REVIEW-HUMAN"
        )
        self.assertEqual(button, {
            "text": "Done - Return to SAM",
            "callback_data": "sam_live_card_done:SAM-LIVE-REVIEW-HUMAN",
            "action": "return_to_auto_then_resolve",
        })
        source = inspect.getsource(launch._process_canonical_owner_card_action)
        self.assertLess(source.index("apply_sam_live_stock_chatwoot_takeover"), source.index("delete_sam_live_stock_telegram_escalation"))

    def test_planner_executor_contract_cannot_pass_when_actions_disagree(self):
        _conversation, _card, built, _original, candidate_event = self._resolve_card_fixture()
        self.assertEqual(built["reconciliation"]["cards"][0]["action"], "resolve_card_only")
        mismatched = json.loads(json.dumps(candidate_event))
        mismatched["review_json"]["resolve_card_only"]["action_type"] = "card_done"
        result, status = launch.execute_sam_live_stock_resolve_card_only(
            mismatched,
            {"telegram_chat_id": "555", "telegram_message_id": "2865"},
        )
        self.assertEqual(status, 409)
        self.assertEqual(result["status"], "resolve_card_candidate_invalid")
if __name__ == "__main__":
    unittest.main()
