import unittest
from datetime import datetime, timezone

from modules.sales.sam_sales_autonomy import (
    bind_authoritative_conversation_evidence,
    evaluate_level1_authority,
    supporting_claims_are_evidence_backed,
    sales_autonomy_level1_policy,
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
    def test_unrelated_context_blocker_does_not_block_claim_free_guidance(self):
        reply = (
            "Hi Leonello, thanks for your message.\n\n"
            "Which size would suit you, and would you prefer a male, "
            "female, or either?\n"
            "Once I know that, I can confirm the available options and price."
        )
        self.assertTrue(supporting_claims_are_evidence_backed(
            "live_stock",
            {
                "suggested_reply_text": reply,
                "blockers": ["sales_availability_read_failed"],
                "reply_source": "deterministic_customer_size_guidance",
                "customer_guidance_preferred": True,
                "customer_guidance": {
                    "applicable": True,
                    "contract_version": "customer_size_guidance_v1",
                    "claim_types": [],
                    "reply_text": reply,
                },
            },
            review_evidence_ready=True,
        ))

    def test_unsupported_stock_and_price_claims_remain_blocked(self):
        for reply in (
            "We have 10 piglets available.",
            "The price is R500 each.",
        ):
            with self.subTest(reply=reply):
                self.assertFalse(supporting_claims_are_evidence_backed(
                    "live_stock",
                    {"suggested_reply_text": reply, "blockers": []},
                    review_evidence_ready=True,
                ))

    def test_delivery_and_reservation_process_claims_require_exact_evidence(self):
        cases = (
            "We deliver nationwide. Which location should I note?",
            "We ship nationwide. Which area should I note?",
            "Transport is available to Cape Town.",
            "Ons lewer landswyd.",
            "You can reserve pigs with us.",
            "We accept reservations.",
            "Reservations can be made with us.",
            "Ons aanvaar deposito's.",
            "The payment process is EFT.",
        )
        for reply in cases:
            with self.subTest(reply=reply):
                decision = {
                    "suggested_reply_text": reply,
                    "blockers": ["read_context_error"],
                }
                self.assertFalse(supporting_claims_are_evidence_backed(
                    "live_stock", decision, review_evidence_ready=True,
                ))

    def test_numeric_written_and_afrikaans_prices_require_price_evidence(self):
        replies = (
            "The price is R500 each.",
            "Our price is five hundred rand each.",
            "They are five hundred rand each.",
            "They cost 500 each.",
            "Die prys is vyf honderd rand elk.",
        )
        for reply in replies:
            with self.subTest(reply=reply):
                decision = {
                    "suggested_reply_text": reply,
                    "blockers": ["sales_availability_read_failed"],
                }
                self.assertFalse(supporting_claims_are_evidence_backed(
                    "live_stock", decision, review_evidence_ready=True,
                ))

    def test_future_confirmation_wording_is_not_an_affirmative_claim(self):
        reply = (
            "Hi, thanks for your message.\n\n"
            "Which size would suit you?\n"
            "Once I know that, I can confirm the available options and price."
        )
        self.assertTrue(supporting_claims_are_evidence_backed(
            "live_stock",
            {
                "suggested_reply_text": reply,
                "blockers": ["read_context_error"],
                "reply_source": "deterministic_customer_size_guidance",
                "customer_guidance_preferred": True,
                "customer_guidance": {
                    "applicable": True,
                    "contract_version": "customer_size_guidance_v1",
                    "claim_types": [],
                    "reply_text": reply,
                },
            },
            review_evidence_ready=True,
        ))

    def test_guidance_marker_or_reply_mismatch_fails_closed(self):
        reply = "Which size would suit you?"
        base = {
            "suggested_reply_text": reply,
            "blockers": ["sales_availability_read_failed"],
            "reply_source": "deterministic_customer_size_guidance",
            "customer_guidance_preferred": True,
            "customer_guidance": {
                "applicable": True,
                "contract_version": "customer_size_guidance_v1",
                "claim_types": [],
                "reply_text": reply,
            },
        }
        for mutation in (
            {"reply_source": "llm"},
            {"customer_guidance_preferred": False},
            {"customer_guidance": {**base["customer_guidance"], "claim_types": ["price"]}},
            {"customer_guidance": {**base["customer_guidance"], "reply_text": "different"}},
        ):
            with self.subTest(mutation=mutation):
                self.assertFalse(supporting_claims_are_evidence_backed(
                    "live_stock", {**base, **mutation}, review_evidence_ready=True,
                ))

    def test_coherently_fabricated_guidance_packet_fails_closed(self):
        replies = (
            "We have 10 female piglets available for R500 each and deliver nationwide.",
            (
                "Hi We have 10 female pigs available for R500 each, thanks for your "
                "message.\n\nWhich size would suit you?\nOnce I know that, I can "
                "confirm the available options and price."
            ),
        )
        for reply in replies:
            with self.subTest(reply=reply):
                self.assertFalse(supporting_claims_are_evidence_backed(
                    "live_stock",
                    {
                        "suggested_reply_text": reply,
                        "blockers": ["sales_availability_read_failed"],
                        "reply_source": "deterministic_customer_size_guidance",
                        "customer_guidance_preferred": True,
                        "customer_guidance": {
                            "applicable": True,
                            "contract_version": "customer_size_guidance_v1",
                            "claim_types": [],
                            "reply_text": reply,
                        },
                    },
                    review_evidence_ready=True,
                ))

    def test_canonical_future_confirmation_is_not_availability_claim(self):
        canonical = (
            "Hi Leonello, thanks for your message. We offer pigs in different sizes:\n\n"
            "- Small piglets: approximately 2 to 6 kg\n"
            "- Weaned piglets: approximately 7 to 19 kg\n"
            "- Growing pigs: approximately 20 to 49 kg\n"
            "- Larger pigs: approximately 50 to 79 kg\n"
            "- Slaughter-size pigs: approximately 80 kg and above\n\n"
            "Which size would suit you, and would you prefer a male, female, or either?\n"
            "Once I know that, I can confirm the available options and price."
        )
        result = evaluate_level1_authority(
            lane="live_stock",
            inbound=inbound(),
            decision={
                **decision(),
                "suggested_reply_text": canonical,
                "next_action": "ask_one_missing_detail",
            },
            review=review(),
            evidence={
                **evidence(),
                "availability": {"evidence_complete": False, "freshness": "unavailable"},
            },
            environ={
                "SAM_SALES_AUTONOMY_LEVEL": "1",
                "SAM_SALES_LEVEL1_LIVE_STOCK_ENABLED": "1",
                "SAM_SALES_LEVEL1_COHORT_ENABLED": "1",
                "SAM_SALES_LEVEL1_COHORT_BINDINGS": "2033:M-1",
            },
        )
        self.assertTrue(result["checks"]["unsupported_availability_claim_absent"])

    def test_single_missing_sex_guidance_is_not_availability_claim(self):
        canonical = (
            "Hi Leonello, thanks for your message.\n\n"
            "Would you prefer a male, female, or either?\n"
            "Once I know that, I can confirm the available options and price."
        )
        result = evaluate_level1_authority(
            lane="live_stock",
            inbound=inbound(conversation_id="2068", message_id="764166766"),
            decision={
                **decision(),
                "suggested_reply_text": canonical,
                "next_action": "ask_one_missing_detail",
            },
            review=review(),
            evidence={
                **evidence(),
                "availability": {
                    "evidence_complete": False,
                    "freshness": "unavailable",
                },
            },
            environ={
                "SAM_SALES_AUTONOMY_LEVEL": "1",
                "SAM_SALES_LEVEL1_LIVE_STOCK_ENABLED": "1",
                "SAM_SALES_LEVEL1_COHORT_ENABLED": "1",
                "SAM_SALES_LEVEL1_COHORT_BINDINGS": "2068:764166766",
            },
        )
        self.assertTrue(
            result["checks"]["unsupported_availability_claim_absent"]
        )
        self.assertTrue(result["dispatch_authorized"])

    def test_unknown_blocker_remains_fail_closed_for_claim_free_text(self):
        self.assertFalse(supporting_claims_are_evidence_backed(
            "live_stock",
            {
                "suggested_reply_text": "Which size would suit you?",
                "blockers": ["farm_knowledge_unavailable"],
            },
            review_evidence_ready=True,
        ))

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


    def test_policy_is_sanitized_and_default_disabled(self):
        self.assertFalse(sales_autonomy_level1_policy({})["dispatch_gate_configured"])
        configured = sales_autonomy_level1_policy({
            "SAM_SALES_AUTONOMY_LEVEL": "1", "SAM_SALES_LEVEL1_MEAT_ENABLED": "1",
            "SAM_SALES_LEVEL1_COHORT_ENABLED": "1", "SAM_SALES_LEVEL1_COHORT_BINDINGS": "2033:M-1",
        })
        self.assertTrue(configured["dispatch_gate_configured"])
        self.assertEqual(configured["cohort_configured_count"], 1)
        self.assertFalse(configured["contains_identity_values"])
        self.assertNotIn("2033", str(configured))
        self.assertFalse(configured["protected_actions_authorized"])

    def test_specialist_policies_report_level1_without_exposing_bindings(self):
        env = {"SAM_SALES_AUTONOMY_LEVEL": "1", "SAM_SALES_LEVEL1_MEAT_ENABLED": "1",
               "SAM_SALES_LEVEL1_LIVE_STOCK_ENABLED": "1", "SAM_SALES_LEVEL1_COHORT_ENABLED": "1",
               "SAM_SALES_LEVEL1_COHORT_BINDINGS": "2033:M-1"}
        for policy in (sam_meat_runtime.sam_meat_webhook_policy(env),
                       sam_live_stock_runtime.sam_live_stock_webhook_policy(env)):
            with self.subTest(mode=policy["mode"]):
                self.assertTrue(policy["sales_autonomy_level1"]["dispatch_gate_configured"])
                self.assertNotIn("2033", str(policy["sales_autonomy_level1"]))

if __name__ == "__main__":
    unittest.main()
