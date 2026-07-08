import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from modules.sales.conversation_learning import (
    AUTHORITY_FLAGS,
    build_learning_event_from_sam_result,
    build_live_stock_owner_reply_learning_event,
    build_owner_review_learning_event,
    record_sales_conversation_learning_event,
    summarize_sales_conversation_learning,
)


def sam_result(**overrides):
    result = {
        "inbound": {
            "conversation_id": "1808",
            "content": "Half carcass Set A in Riversdale, delivery please. EFT. Next available farm run.",
            "channel": "chatwoot_whatsapp",
            "last_inbound_at": "2026-06-18T07:00:00+02:00",
        },
        "facts": {
            "product_type": "half_carcass",
            "cut_set": "Set A",
            "location": "Riversdale",
            "delivery_or_collection": "delivery",
            "payment_method": "EFT",
            "timing": "next available farm run",
        },
        "lead_payload": {
            "lead_id": "OSK-SALES-LEAD-TEST",
            "campaign_source": "whatsapp_status",
        },
        "lead_result": {"lead_id": "OSK-SALES-LEAD-TEST"},
        "sam_decision": {
            "lead_id": "OSK-SALES-LEAD-TEST",
            "reply_text": "Please send the delivery street address or farm name, town, and any useful directions for the driver.",
        },
        "pop_capture": {},
    }
    result.update(overrides)
    return result


class SalesConversationLearningTests(unittest.TestCase):
    def test_builds_append_only_evidence_from_sam_result(self):
        event = build_learning_event_from_sam_result(sam_result())

        self.assertEqual(event["lead_id"], "OSK-SALES-LEAD-TEST")
        self.assertEqual(event["event_type"], "sam_inbound_observation")
        self.assertEqual(event["conversion_signal"], "needs_followup")
        self.assertIn("delivery_address", event["missing_facts"])
        self.assertIn("delivery_or_location", event["objections"])
        self.assertEqual(event["campaign_source"], "whatsapp_status")
        self.assertFalse(event["applies_learning_now"])
        self.assertFalse(event["changes_prompt_now"])
        self.assertFalse(event["sends_customer_message"])
        self.assertFalse(event["creates_order"])
        self.assertFalse(event["changes_stock"])

    def test_booking_and_pop_signals_are_detected_without_authority(self):
        booking = build_learning_event_from_sam_result(sam_result(
            inbound={
                "conversation_id": "1808",
                "content": "Yes, please proceed with the final booking review.",
                "channel": "chatwoot_whatsapp",
            },
            facts={
                "product_type": "half_carcass",
                "cut_set": "Set A",
                "location": "Riversdale",
                "delivery_or_collection": "collection",
                "payment_method": "EFT",
                "timing": "next available farm run",
            },
        ))
        self.assertEqual(booking["conversion_signal"], "booking_review_requested")

        pop = build_learning_event_from_sam_result(sam_result(
            inbound={"conversation_id": "1808", "content": "POP attached", "channel": "chatwoot_whatsapp"},
            pop_capture={"recorded": True},
        ))
        self.assertEqual(pop["conversion_signal"], "deposit_proof_received_unverified")
        self.assertFalse(pop["calls_chatwoot"])

    def test_owner_review_event_is_evidence_only(self):
        event = build_owner_review_learning_event("OSK-SALES-LEAD-TEST", {
            "event_type": "loss_observed",
            "conversion_signal": "lost_or_not_fit",
            "notes": "Buyer wanted beef, not pork.",
            "confusion_signals": ["non_pork_request"],
        })

        self.assertEqual(event["event_type"], "loss_observed")
        self.assertEqual(event["conversion_signal"], "lost_or_not_fit")
        self.assertEqual(event["sam_misses"], [])
        for flag, value in AUTHORITY_FLAGS.items():
            self.assertIn(flag, event)
            self.assertEqual(event[flag], value)

    def test_live_stock_owner_reply_capture_compares_sam_draft_to_owner_reply(self):
        event = build_live_stock_owner_reply_learning_event(
            {
                "conversation_id": "1840",
                "message_id": "9001",
                "content": "We are in the Western Cape near Riversdale. Collection is normally arranged with the farm first.",
                "channel": "chatwoot_whatsapp",
            },
            {
                "review_event_id": "SAM-LIVE-REVIEW-1",
                "chatwoot_conversation_id": "1840",
                "customer_message_excerpt": "Location",
                "sam_reply_excerpt": "Just so I help you correctly: are you looking for live pigs, pork for the freezer, or slaughter help?",
                "facts_json": {"sales_lane": "live_stock_sales", "location": "Riversdale"},
                "decision_json": {"missing_fields": ["category"]},
                "review_json": {"escalation_required": True},
                "recommended_action": "owner_handoff",
            },
        )

        self.assertEqual(event["lead_id"], "SAM-LIVE-CONV-1840")
        self.assertEqual(event["source_agent"], "sam_live_stock_backend")
        self.assertEqual(event["event_source"], "chatwoot_outgoing_owner_reply")
        self.assertEqual(event["event_type"], "owner_review_note")
        self.assertEqual(event["captured_facts"]["learning_kind"], "owner_reply_capture")
        self.assertEqual(event["captured_facts"]["owner_reply_classification"], "owner_replaced")
        self.assertIn("sam_draft_replaced_by_owner", event["sam_misses"])
        self.assertFalse(event["applies_learning_now"])
        self.assertFalse(event["sends_customer_message"])

    def test_live_stock_owner_reply_stale_review_is_not_trusted_as_draft_match(self):
        event = build_live_stock_owner_reply_learning_event(
            {
                "conversation_id": "1840",
                "message_id": "9001",
                "content": "We are in the Western Cape near Riversdale.",
                "last_inbound_at": "2026-07-08T14:00:00+00:00",
                "channel": "chatwoot_whatsapp",
            },
            {
                "review_event_id": "SAM-LIVE-REVIEW-OLD",
                "chatwoot_conversation_id": "1840",
                "created_at": "2026-07-07T00:00:00+00:00",
                "customer_message_excerpt": "Location",
                "sam_reply_excerpt": "Old draft",
                "facts_json": {"sales_lane": "live_stock_sales"},
            },
        )

        self.assertEqual(event["captured_facts"]["owner_reply_classification"], "owner_reply_no_sam_draft")
        self.assertTrue(event["captured_facts"]["stale_review_link"])
        self.assertEqual(event["captured_facts"]["review_event_id"], "")

    def test_summary_counts_patterns(self):
        summary = summarize_sales_conversation_learning([
            {
                "conversion_signal": "needs_followup",
                "missing_facts": ["timing"],
                "objections": ["price_or_budget"],
                "confusion_signals": ["customer_confusion"],
                "sam_misses": ["missed_budget"],
                "improvement_suggestion": "Review budget extraction.",
            },
            {
                "conversion_signal": "qualified_interest",
                "missing_facts": [],
                "objections": ["price_or_budget"],
                "confusion_signals": [],
                "sam_misses": [],
                "improvement_suggestion": "Review budget extraction.",
            },
        ])

        self.assertEqual(summary["total_events"], 2)
        self.assertEqual(summary["conversion_signals"]["needs_followup"], 1)
        self.assertEqual(summary["objections"]["price_or_budget"], 2)
        self.assertEqual(summary["sam_misses"]["missed_budget"], 1)
        self.assertEqual(summary["top_improvement_suggestions"][0]["value"], "Review budget extraction.")
        self.assertEqual(summary["top_improvement_suggestions"][0]["count"], 2)

    def test_learning_flags_robotic_voice_and_payment_loop(self):
        robotic = build_learning_event_from_sam_result(sam_result(
            inbound={
                "conversation_id": "1812",
                "content": "This system is shit, where is the human factor?",
                "channel": "chatwoot_whatsapp",
            },
            facts={"product_type": "unknown"},
            sam_decision={
                "lead_id": "OSK-SALES-LEAD-TEST",
                "reply_text": "Are you interested in a pork half carcass, full carcass, custom cuts, or assisted slaughter?",
            },
        ))

        self.assertIn("robotic_tone", robotic["confusion_signals"])
        self.assertIn("missed_brand_voice", robotic["sam_misses"])

        payment_loop = build_learning_event_from_sam_result(sam_result(
            inbound={
                "conversation_id": "1812",
                "content": "How long does that take?",
                "channel": "chatwoot_whatsapp",
            },
            facts={
                "product_type": "half_carcass",
                "cut_set": "Set A",
                "location": "Riversdale",
                "delivery_or_collection": "delivery",
                "timing": "next week",
            },
            sam_decision={
                "lead_id": "OSK-SALES-LEAD-TEST",
                "reply_text": "For meat sales we use EFT only for now. Is EFT fine for the deposit and final balance?",
            },
        ))

        self.assertIn("repeated_payment_method_after_payment_context", payment_loop["sam_misses"])

    def test_record_requires_database_and_never_sets_authority(self):
        result, status_code = record_sales_conversation_learning_event({
            "lead_id": "OSK-SALES-LEAD-TEST",
            "customer_message": "Half carcass Set A please.",
        }, database_url="")

        self.assertEqual(status_code, 503)
        self.assertEqual(result["status"], "not_configured")
        self.assertFalse(result["applies_learning_now"])
        self.assertFalse(result["changes_prompt_now"])
        self.assertFalse(result["sends_customer_message"])

    def test_migration_contract_is_append_only_and_no_authority(self):
        migration = Path("supabase/migrations/202606180001_create_meat_sales_conversation_learning_events.sql").read_text(encoding="utf-8")

        self.assertIn("create table if not exists public.meat_sales_conversation_learning_events", migration)
        self.assertIn("applies_learning_now = false", migration)
        self.assertIn("changes_prompt_now = false", migration)
        self.assertIn("sends_customer_message = false", migration)
        self.assertIn("creates_order = false", migration)
        self.assertIn("before update on public.meat_sales_conversation_learning_events", migration)
        self.assertIn("before delete on public.meat_sales_conversation_learning_events", migration)

    @patch("modules.oom_sakkie.tools.list_sales_conversation_learning_events")
    def test_oom_sakkie_sales_learning_tool_is_read_only(self, mock_list):
        from modules.oom_sakkie.tools import TOOL_REGISTRY, sales_conversation_learning_status_handler

        mock_list.return_value = ({
            "success": True,
            "status": "ok",
            "learning_events": [{
                "learning_event_id": "MSCL-1",
                "conversion_signal": "needs_followup",
                "objections": ["price_or_budget"],
                "sam_misses": ["missed_budget"],
            }],
            "summary": {
                "total_events": 1,
                "objections": {"price_or_budget": 1},
                "sam_misses": {"missed_budget": 1},
                "top_improvement_suggestions": [],
            },
        }, 200)

        result = sales_conversation_learning_status_handler({})

        self.assertIn("sales_conversation_learning_status", TOOL_REGISTRY)
        self.assertTrue(result["success"])
        self.assertIn("1 append-only evidence", result["summary"])
        self.assertFalse(result["llm_context"]["applies_learning_now"])
        self.assertFalse(result["llm_context"]["changes_prompt_now"])
        self.assertFalse(result["llm_context"]["sends_customer_message"])

    def test_sales_learning_intent_routes_to_read_only_tool(self):
        from modules.oom_sakkie.service import classify_intent

        match = classify_intent("What are we learning from sales conversations and buyer objections?")

        self.assertEqual(match.intent, "sales_conversation_learning_status")
        self.assertEqual(match.tool_name, "sales_conversation_learning_status")

    @patch("modules.sales.sam_meat_runtime.record_learning_event_from_sam_result")
    @patch("modules.sales.sam_meat_runtime.get_sales_lead_preorder_contract")
    @patch("modules.sales.sam_meat_runtime.record_sam_meat_intake_lead")
    def test_sam_runtime_attempts_learning_after_processing(self, mock_record, mock_contract, mock_learning):
        from tests.test_sam_meat_runtime import inbound_payload
        from modules.sales import sam_meat_runtime

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
        mock_learning.return_value = ({
            "success": True,
            "status": "sales_conversation_learning_event_recorded",
            "learning_event_id": "MSCL-TEST",
            "next_gate": "atlas_or_owner_review_before_prompt_rule_or_workflow_change",
        }, 201)

        result, status_code = sam_meat_runtime.handle_sam_meat_chatwoot_inbound(
            inbound_payload(),
            environ={"SAM_MEAT_BACKEND_AUTOREPLY_ENABLED": "0"},
            chatwoot_sender=Mock(),
        )

        self.assertEqual(status_code, 200)
        self.assertEqual(result["conversation_learning"]["status"], "sales_conversation_learning_event_recorded")
        self.assertEqual(result["conversation_learning"]["learning_event_id"], "MSCL-TEST")
        self.assertFalse(result["conversation_learning"]["applies_learning_now"])
        mock_learning.assert_called_once()


if __name__ == "__main__":
    unittest.main()
