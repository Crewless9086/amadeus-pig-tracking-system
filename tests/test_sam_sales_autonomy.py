import unittest
from datetime import datetime, timezone

from modules.sales.sam_sales_autonomy import (
    bind_authoritative_conversation_evidence,
    evaluate_level1_authority,
    supporting_claims_are_evidence_backed,
)
from modules.sales import sam_live_stock_runtime, sam_meat_runtime


def inbound(**overrides):
    row = {
        "account_id": "147387", "conversation_id": "2033",
        "contact_id": "C-1", "inbox_id": "96568", "message_id": "M-1",
        "processable": True, "message_type": "incoming",
        "chronology_current": True,
        "latest_observed_at": "2026-07-28T08:00:00Z",
        "whatsapp_window_state": "open",
        "whatsapp_window_evidence_authoritative": True,
    }
    row.update(overrides)
    return row


def decision(**overrides):
    row = {
        "should_reply": True, "next_action": "ask_one_missing_detail",
        "suggested_reply_text": "The current price is R130/kg including VAT. Which delivery area should I note?",
    }
    row.update(overrides)
    return row


def review(**overrides):
    row = {"safe_to_send": True, "escalation_required": False,
           "owner_authority_required": False}
    row.update(overrides)
    return row


def evidence(**overrides):
    row = {"supporting_evidence_valid": True, "automatic_retry": False,
           "delivery_rail_available": True,
           "availability": {"evidence_complete": False, "freshness": "Unavailable"}}
    row.update(overrides)
    return row


class SamSalesAutonomyLevel1Tests(unittest.TestCase):
    def test_disabled_by_default(self):
        result = evaluate_level1_authority(
            lane="meat", inbound=inbound(), decision=decision(),
            review=review(), evidence=evidence(), environ={},
        )
        self.assertFalse(result["dispatch_authorized"])
        self.assertIn("level_1_enabled", result["blockers"])

    def test_exact_first_five_cohort_can_dispatch(self):
        result = evaluate_level1_authority(
            lane="meat", inbound=inbound(), decision=decision(),
            review=review(), evidence=evidence(),
            environ={"SAM_SALES_AUTONOMY_LEVEL": "1",
                     "SAM_SALES_LEVEL1_MEAT_ENABLED": "1",
                     "SAM_SALES_LEVEL1_COHORT_ENABLED": "1",
                     "SAM_SALES_LEVEL1_COHORT_BINDINGS": "2033:M-1,2054:M-2"},
        )
        self.assertTrue(result["tier_1_eligible"])
        self.assertTrue(result["dispatch_authorized"])
        self.assertFalse(result["protected_actions_authorized"])

    def test_six_conversation_cohort_fails_closed(self):
        result = evaluate_level1_authority(
            lane="live_stock", inbound=inbound(conversation_id="1"),
            decision=decision(), review=review(), evidence=evidence(),
            environ={"SAM_SALES_AUTONOMY_LEVEL": "1",
                     "SAM_SALES_LEVEL1_LIVE_STOCK_ENABLED": "1",
                     "SAM_SALES_LEVEL1_COHORT_ENABLED": "1",
                     "SAM_SALES_LEVEL1_COHORT_BINDINGS": "1:M-1,2:M-2,3:M-3,4:M-4,5:M-5,6:M-6"},
        )
        self.assertFalse(result["dispatch_authorized"])
        self.assertFalse(result["cohort"]["configuration_safe"])

    def test_cross_pair_is_not_authorized(self):
        result = evaluate_level1_authority(
            lane="meat", inbound=inbound(message_id="M-2"),
            decision=decision(), review=review(), evidence=evidence(),
            environ={
                "SAM_SALES_AUTONOMY_LEVEL": "1",
                "SAM_SALES_LEVEL1_MEAT_ENABLED": "1",
                "SAM_SALES_LEVEL1_COHORT_ENABLED": "1",
                "SAM_SALES_LEVEL1_COHORT_BINDINGS": "2033:M-1,2054:M-2",
            },
        )
        self.assertFalse(result["dispatch_authorized"])
        self.assertFalse(result["cohort"]["conversation_member"])

    def test_missing_availability_answers_supported_parts_without_count(self):
        result = evaluate_level1_authority(
            lane="live_stock", inbound=inbound(),
            decision=decision(suggested_reply_text=(
                "We sell weaners at the current approved price. "
                "I am confirming availability. How many do you need?"
            )),
            review=review(), evidence=evidence(),
            environ={"SAM_SALES_AUTONOMY_LEVEL": "1",
                     "SAM_SALES_LEVEL1_LIVE_STOCK_ENABLED": "1"},
        )
        self.assertTrue(result["tier_1_eligible"])
        self.assertEqual(result["classification"], "qualified")

    def test_unsupported_count_is_blocked(self):
        result = evaluate_level1_authority(
            lane="live_stock", inbound=inbound(),
            decision=decision(suggested_reply_text="We have 12 pigs available."),
            review=review(), evidence=evidence(),
            environ={"SAM_SALES_AUTONOMY_LEVEL": "1",
                     "SAM_SALES_LEVEL1_LIVE_STOCK_ENABLED": "1"},
        )
        self.assertFalse(result["tier_1_eligible"])
        self.assertIn("unsupported_availability_count_absent", result["blockers"])

    def test_protected_action_creates_owner_exception(self):
        result = evaluate_level1_authority(
            lane="meat", inbound=inbound(),
            decision=decision(creates_order=True, next_action="prepare_quote"),
            review=review(owner_authority_required=True), evidence=evidence(),
            environ={"SAM_SALES_AUTONOMY_LEVEL": "1",
                     "SAM_SALES_LEVEL1_MEAT_ENABLED": "1"},
        )
        self.assertFalse(result["dispatch_authorized"])
        self.assertEqual(result["classification"], "owner_exception")
        self.assertFalse(result["owner_decision"]["customer_send_performed"])

    def test_identity_chronology_and_window_are_mandatory(self):
        for changed in (
            {"message_id": ""}, {"chronology_current": False},
            {"whatsapp_window_state": "closed"},
            {"whatsapp_window_evidence_authoritative": False},
            {"latest_observed_at": "2026-07-28 08:00:00"},
        ):
            with self.subTest(changed=changed):
                result = evaluate_level1_authority(
                    lane="meat", inbound=inbound(**changed), decision=decision(),
                    review=review(), evidence=evidence(),
                    environ={"SAM_SALES_AUTONOMY_LEVEL": "1",
                             "SAM_SALES_LEVEL1_MEAT_ENABLED": "1"},
                )
                self.assertFalse(result["tier_1_eligible"])

    def test_complaint_and_negotiation_require_owner(self):
        for content in ("I have a complaint", "Can you negotiate a special price?"):
            with self.subTest(content=content):
                result = evaluate_level1_authority(
                    lane="meat",
                    inbound=inbound(content=content),
                    decision=decision(),
                    review=review(),
                    evidence=evidence(),
                    environ={"SAM_SALES_AUTONOMY_LEVEL": "1",
                             "SAM_SALES_LEVEL1_MEAT_ENABLED": "1"},
                )
                self.assertEqual(result["classification"], "owner_exception")
                self.assertFalse(result["tier_1_eligible"])

    def test_non_reservation_explanation_remains_tier1(self):
        result = evaluate_level1_authority(
            lane="live_stock",
            inbound=inbound(content="How much are weaners?"),
            decision=decision(suggested_reply_text=(
                "Weaners are R450 to R600 each. Choosing an option does not "
                "reserve animals. How many do you need?"
            )),
            review=review(),
            evidence=evidence(),
            environ={
                "SAM_SALES_AUTONOMY_LEVEL": "1",
                "SAM_SALES_LEVEL1_LIVE_STOCK_ENABLED": "1",
            },
        )
        self.assertNotEqual(result["classification"], "owner_exception")

    def test_common_protected_commitments_are_blocked(self):
        commitments = (
            "We can deliver tomorrow.",
            "Your order is confirmed.",
            "I've reserved them for you.",
            "We can allocate 10 pigs.",
            "Your slaughter booking is confirmed.",
            "Payment is received.",
            "This is the final binding quote.",
        )
        for reply in commitments:
            with self.subTest(reply=reply):
                result = evaluate_level1_authority(
                    lane="live_stock",
                    inbound=inbound(content="Please confirm"),
                    decision=decision(suggested_reply_text=reply),
                    review=review(),
                    evidence=evidence(),
                    environ={
                        "SAM_SALES_AUTONOMY_LEVEL": "1",
                        "SAM_SALES_LEVEL1_LIVE_STOCK_ENABLED": "1",
                    },
                )
                self.assertFalse(result["tier_1_eligible"])

    def test_stale_availability_requires_uncertainty_and_useful_question(self):
        for reply in (
            "We have female weaners available.",
            "Piglets are in stock.",
            "We can fulfil that quantity.",
            "I am confirming availability.",
            "I am confirming availability. How are you?",
            (
                "We have female weaners available. "
                "I am confirming availability. How many do you need?"
            ),
        ):
            with self.subTest(reply=reply):
                result = evaluate_level1_authority(
                    lane="live_stock",
                    inbound=inbound(content="Do you have weaners available?"),
                    decision=decision(suggested_reply_text=reply),
                    review=review(),
                    evidence=evidence(),
                    environ={
                        "SAM_SALES_AUTONOMY_LEVEL": "1",
                        "SAM_SALES_LEVEL1_LIVE_STOCK_ENABLED": "1",
                    },
                )
                self.assertFalse(result["tier_1_eligible"])

    def test_delivery_rail_is_mandatory(self):
        result = evaluate_level1_authority(
            lane="live_stock", inbound=inbound(), decision=decision(),
            review=review(), evidence=evidence(delivery_rail_available=False),
            environ={"SAM_SALES_AUTONOMY_LEVEL": "1",
                     "SAM_SALES_LEVEL1_LIVE_STOCK_ENABLED": "1"},
        )
        self.assertFalse(result["tier_1_eligible"])

    def test_stable_authority_identity_and_no_customer_diagnostics(self):
        kwargs = dict(lane="meat", inbound=inbound(), decision=decision(),
                      review=review(), evidence=evidence(), environ={})
        first = evaluate_level1_authority(**kwargs)
        second = evaluate_level1_authority(**kwargs)
        self.assertEqual(first["authority_id"], second["authority_id"])
        self.assertFalse(first["contains_customer_values"])
        self.assertFalse(first["writes_performed"])

    def test_authoritative_chronology_binds_exact_latest_inbound(self):
        bound = bind_authoritative_conversation_evidence(
            inbound(channel="Channel::Whatsapp"),
            [{
                "id": "M-1", "message_type": 0, "private": False,
                "created_at": "2026-07-28T07:30:00Z", "attachments": [],
            }],
            now=datetime(2026, 7, 28, 8, 0, tzinfo=timezone.utc),
        )
        self.assertTrue(bound["chronology_current"])
        self.assertEqual(bound["whatsapp_window_state"], "open")

    def test_later_outgoing_or_malformed_chronology_fails_closed(self):
        cases = (
            [
                {"id": "M-1", "message_type": 0, "private": False,
                 "created_at": "2026-07-28T07:30:00Z", "attachments": []},
                {"id": "OUT-1", "message_type": 1, "private": False,
                 "created_at": "2026-07-28T07:45:00Z", "attachments": []},
            ],
            [{"id": "M-1", "message_type": 0, "private": False,
              "created_at": "not-a-date", "attachments": []}],
        )
        for rows in cases:
            with self.subTest(rows=rows):
                bound = bind_authoritative_conversation_evidence(
                    inbound(channel="Channel::Whatsapp"),
                    rows,
                    now=datetime(2026, 7, 28, 8, 0, tzinfo=timezone.utc),
                )
                self.assertFalse(bound["chronology_current"])

    def test_supported_partial_reply_does_not_require_availability_count(self):
        self.assertTrue(supporting_claims_are_evidence_backed(
            "live_stock",
            {
                "suggested_reply_text": (
                    "Weaners are R450 to R600 each. "
                    "I am confirming availability. How many do you need?"
                ),
                "price_answer_packet": {"can_answer_price": True},
                "blockers": [],
            },
            review_evidence_ready=True,
        ))

    def test_unsupported_price_or_count_claim_fails_closed(self):
        for reply in ("Weaners are R500 each.", "We have 10 pigs available."):
            with self.subTest(reply=reply):
                self.assertFalse(supporting_claims_are_evidence_backed(
                    "live_stock",
                    {"suggested_reply_text": reply, "blockers": []},
                    review_evidence_ready=True,
                ))

    def test_cohort_stop_switch_withholds_dispatch(self):
        result = evaluate_level1_authority(
            lane="meat", inbound=inbound(), decision=decision(),
            review=review(), evidence=evidence(),
            environ={
                "SAM_SALES_AUTONOMY_LEVEL": "1",
                "SAM_SALES_LEVEL1_MEAT_ENABLED": "1",
                "SAM_SALES_LEVEL1_COHORT_ENABLED": "1",
                "SAM_SALES_LEVEL1_COHORT_STOPPED": "1",
                "SAM_SALES_LEVEL1_COHORT_BINDINGS": "2033:M-1",
            },
        )
        self.assertFalse(result["dispatch_authorized"])
        self.assertIn("cohort_not_stopped", result["blockers"])

    def test_livestock_context_preserves_authority_metadata_without_content(self):
        packet = sam_live_stock_runtime.load_live_stock_read_context(
            {"conversation_id": "2033", "message_id": "M-1", "content": "price"},
            {"sales_lane": "live_stock"},
            intake_context_loader=lambda _identity: {"success": False, "items": []},
            conversation_history_loader=lambda *_args: {
                "success": True,
                "messages": [{
                    "id": "M-1", "message_type": 0, "private": False,
                    "created_at": "2026-07-28T07:30:00Z",
                    "attachments": [], "content": "redacted from authority shape",
                }],
            },
            availability_loader=lambda: [],
            availability_evidence={},
            environ={},
        )
        rows = packet["chatwoot_authority_messages"]
        self.assertEqual(rows[0]["id"], "M-1")
        self.assertNotIn("content", rows[0])

    def test_livestock_authority_preserves_attachment_evidence(self):
        for attachments in ([{"id": "ATT-1"}], {"malformed": True}):
            with self.subTest(attachments=attachments):
                packet = sam_live_stock_runtime.load_live_stock_read_context(
                    {"conversation_id": "2033", "message_id": "M-1", "content": ""},
                    {"sales_lane": "live_stock"},
                    intake_context_loader=lambda _identity: {"success": False, "items": []},
                    conversation_history_loader=lambda *_args: {
                        "success": True,
                        "messages": [{
                            "id": "M-1", "message_type": 0, "private": False,
                            "created_at": "2026-07-28T07:30:00Z",
                            "attachments": attachments, "content": "",
                        }],
                    },
                    availability_loader=lambda: [],
                    availability_evidence={},
                    environ={},
                )
                rows = packet["chatwoot_authority_messages"]
                self.assertEqual(rows[0]["attachments"], attachments)
                bound = bind_authoritative_conversation_evidence(
                    inbound(channel="Channel::Whatsapp"),
                    rows,
                    now=datetime(2026, 7, 28, 8, 0, tzinfo=timezone.utc),
                )
                self.assertFalse(bound["chronology_current"])

    def test_meat_normalization_includes_inbox_identity(self):
        parsed = sam_meat_runtime.parse_chatwoot_inbound({
            "event": "message_created",
            "message_type": 0,
            "id": "M-1",
            "content": "Grand Cut price",
            "account": {"id": "147387"},
            "conversation": {
                "id": "2033",
                "inbox": {"id": "96568", "channel_type": "Channel::Whatsapp"},
            },
            "sender": {"id": "C-1"},
        })
        self.assertEqual(parsed["inbox_id"], "96568")


if __name__ == "__main__":
    unittest.main()
