import json
import os
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from modules.sales import sam_live_stock_runtime


def inbound_payload(**overrides):
    payload = {
        "event": "message_created",
        "message_type": "incoming",
        "content": "Hi Sam, I need 3 female weaners around 10 to 15kg next week in Riversdale.",
        "conversation": {
            "id": 2401,
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


def exact_eligible_row(**overrides):
    row = {
        "pig_id": "PIG-TEST",
        "sex": "Female",
        "status": "Active",
        "on_farm": "Yes",
        "purpose": "Sale",
        "available_for_sale": "Yes",
        "live_stock_sale_eligible": True,
        "exact_animal_eligibility_contract_version": "herdmaster_exact_animal_eligibility_v1",
        "evidence_complete": True,
        "eligibility_observed_at": datetime.now(timezone.utc).isoformat(),
        "allocation_query_status": "known",
        "allocation_evidence_state": "known_unallocated",
        "reserved_status": "Not_Reserved",
        "withdrawal_evidence_state": "not_applicable",
        "withdrawal_clear": "Yes",
        "medical_status": "Clear",
        "calculated_stage": "Weaner",
        "sale_category": "Weaner",
        "current_weight_kg": 12,
        "latest_weight_date": "2026-07-24",
        "days_since_weight": 0,
    }
    row.update(overrides)
    return row


def verified_identity(conversation_id, contact_id, inbox_id):
    return {
        "status": "identity_verified",
        "normalized": {
            "conversation_id": str(conversation_id),
            "contact_id": str(contact_id),
            "inbox_id": str(inbox_id),
        },
        "sources": {
            "conversation_id": [{"source": "test.webhook", "value": str(conversation_id)}],
            "contact_id": [{"source": "test.webhook", "value": str(contact_id)}],
            "inbox_id": [{"source": "test.webhook", "value": str(inbox_id)}],
        },
        "conflicts": {
            "conversation_id": False,
            "contact_id": False,
            "inbox_id": False,
        },
        "configured_allowlist_used_as_evidence": False,
    }


class SamLiveStockRuntimeTests(unittest.TestCase):
    def test_decision_retains_exact_operational_identity_for_post_send_state(
        self,
    ):
        result, status = (
            sam_live_stock_runtime.handle_sam_live_stock_chatwoot_inbound(
                inbound_payload(
                    id="INBOUND-EXACT",
                    conversation={
                        "id": 2401,
                        "inbox": {
                            "id": 96568,
                            "channel_type": "Channel::Whatsapp",
                        },
                    },
                ),
                environ={},
                intake_context_loader=lambda *_args: {
                    "success": True,
                    "known_fields": {},
                    "items": [],
                },
                conversation_history_loader=lambda *_args: {
                    "success": True,
                    "messages": [],
                },
                availability_loader=lambda: [],
            )
        )
        self.assertEqual(status, 200)
        operational = result["sam_decision"]["inbound"]
        self.assertEqual(
            {
                key: str(operational.get(key) or "")
                for key in (
                    "account_id",
                    "conversation_id",
                    "contact_id",
                    "inbox_id",
                    "message_id",
                )
            },
            {
                "account_id": "147387",
                "conversation_id": "2401",
                "contact_id": "99",
                "inbox_id": "96568",
                "message_id": "INBOUND-EXACT",
            },
        )
        self.assertTrue(operational.get("identity_provenance"))

    @patch.object(
        sam_live_stock_runtime,
        "load_chatwoot_conversation_identity",
    )
    def test_preclaim_provider_recheck_binds_exact_latest_inbound(
        self, load_identity
    ):
        load_identity.return_value = {
            "success": True,
            "account_id": "147387",
            "conversation_id": "2074",
            "contact_id": "CONTACT",
            "inbox_id": "96568",
            "can_reply": True,
            "latest_message_id": "INBOUND-A",
            "latest_message_type": 0,
        }
        inbound = {
            "account_id": "147387",
            "conversation_id": "2074",
            "contact_id": "CONTACT",
            "inbox_id": "96568",
            "message_id": "INBOUND-A",
        }
        self.assertTrue(
            sam_live_stock_runtime.verify_chatwoot_current_inbound(
                inbound
            )["allowed"]
        )
        load_identity.return_value["latest_message_id"] = "INBOUND-B"
        self.assertFalse(
            sam_live_stock_runtime.verify_chatwoot_current_inbound(
                inbound
            )["allowed"]
        )
        load_identity.return_value["latest_message_id"] = "INBOUND-A"
        load_identity.return_value["latest_message_type"] = 1
        self.assertFalse(
            sam_live_stock_runtime.verify_chatwoot_current_inbound(
                inbound
            )["allowed"]
        )

    def test_weight_after_want_is_not_misread_as_quantity(self):
        for message in (
            "I want 19 kg ones",
            "I want 19kg ones",
            "I want 19 kilogram ones",
            "I want 19 kilograms ones",
        ):
            with self.subTest(message=message):
                facts = sam_live_stock_runtime.extract_live_stock_facts(
                    message
                )
                self.assertEqual(facts["quantity"], "")
                self.assertEqual(facts["weight_range"], "around 19 kg")
        facts = sam_live_stock_runtime.extract_live_stock_facts(
            "I want 19 kg ones"
        )
        guidance = sam_live_stock_runtime.build_live_stock_customer_guidance(
            {"content": "I want 19 kg ones"},
            facts,
        )
        self.assertEqual(guidance["questions_asked"], ["how many do you need"])
        self.assertNotIn("male, female", guidance["reply_text"])

    def test_quantity_guidance_does_not_suppress_availability_request(self):
        base = {
            "customer_guidance": {
                "applicable": True,
                "guidance_scope": "qualification_only",
                "questions_asked": ["how many do you need"],
                "canonical_mapping": {},
            },
            "contextual_sales": {
                "status": "commercial_evidence_unavailable"
            },
            "price_answer_packet": {"can_answer_price": False},
            "information_scope": "",
            "sales_lane": "live_stock_sales",
            "latest_customer_text": (
                "I want 19 kg ones. Are they available?"
            ),
        }
        self.assertFalse(
            sam_live_stock_runtime._prefer_customer_size_guidance(
                **base,
                information_reply={
                    "status": "availability_and_pricing_verified"
                },
            )
        )
        self.assertTrue(
            sam_live_stock_runtime._prefer_customer_size_guidance(
                **base,
                information_reply={
                    "status": "authoritative_category_evidence_unavailable"
                },
            )
        )

    def test_quantity_only_is_preferred_when_it_is_the_sole_missing_field(self):
        self.assertTrue(
            sam_live_stock_runtime._prefer_customer_size_guidance(
                customer_guidance={
                    "applicable": True,
                    "guidance_scope": "qualification_only",
                    "questions_asked": ["how many do you need"],
                    "canonical_mapping": {},
                },
                contextual_sales={"status": "commercial_evidence_unavailable"},
                information_reply={"status": "not_requested"},
                price_answer_packet={"can_answer_price": False},
                information_scope="",
                sales_lane="live_stock_sales",
                latest_customer_text="I want 19 kg ones",
            )
        )

    def test_quantity_only_never_suppresses_a_supported_price_answer(self):
        self.assertFalse(
            sam_live_stock_runtime._prefer_customer_size_guidance(
                customer_guidance={
                    "applicable": True,
                    "guidance_scope": "qualification_only",
                    "questions_asked": ["how many do you need"],
                    "canonical_mapping": {},
                },
                contextual_sales={"status": "commercial_evidence_unavailable"},
                information_reply={"status": "price_only_verified"},
                price_answer_packet={"can_answer_price": True},
                information_scope="price",
                sales_lane="live_stock_sales",
                latest_customer_text="How much are they?",
            )
        )

    def test_availability_observation_uses_oldest_counted_row_and_rejects_malformed(self):
        fresh = exact_eligible_row(
            pig_id="FRESH", eligibility_observed_at="2026-07-27T11:00:00Z"
        )
        older = exact_eligible_row(
            pig_id="OLDER", eligibility_observed_at="2026-07-26T10:00:00+00:00"
        )
        summary = sam_live_stock_runtime.summarize_live_stock_availability(
            [fresh, older], {"sales_lane": "live_stock_sales", "sex": "female"}
        )
        self.assertEqual(
            summary["observation_timestamp"], "2026-07-26T10:00:00+00:00"
        )

        malformed = exact_eligible_row(
            pig_id="MALFORMED", eligibility_observed_at="not-a-timestamp"
        )
        unavailable = sam_live_stock_runtime.summarize_live_stock_availability(
            [fresh, malformed],
            {"sales_lane": "live_stock_sales", "sex": "female"},
        )
        self.assertEqual(unavailable["observation_timestamp"], "")

    def test_zero_eligible_inventory_preserves_complete_result_observation(self):
        ineligible = exact_eligible_row(
            pig_id="NOT-ELIGIBLE",
            live_stock_sale_eligible=False,
            eligibility_observed_at="2026-07-27T11:00:00Z",
        )
        summary = sam_live_stock_runtime.summarize_live_stock_availability(
            [ineligible], {"sales_lane": "live_stock_sales", "sex": "female"}
        )
        self.assertEqual(
            summary["observation_timestamp"], "2026-07-27T11:00:00+00:00"
        )
        self.assertEqual(summary["total_available_count"], 0)
        self.assertTrue(
            all(
                counts["all"] == 0
                for counts in summary["customer_category_counts"].values()
            )
        )

    def test_customer_category_counts_normalize_supported_fallback_fields(self):
        piglet = exact_eligible_row(
            pig_id="PIGLET",
            sale_category="",
            suggested_price_category="",
            calculated_stage="Piglet",
        )
        summary = sam_live_stock_runtime.summarize_live_stock_availability(
            [piglet], {"sales_lane": "live_stock_sales", "sex": "female"}
        )
        self.assertEqual(
            summary["customer_category_counts"]["Young Piglets"]["all"], 1
        )
        self.assertTrue(summary["customer_category_counts_complete"])

    def test_explicit_sale_category_precedes_conflicting_fallback_stage(self):
        row = exact_eligible_row(
            pig_id="CONFLICT",
            sale_category="Young Piglets",
            calculated_stage="Weaner",
            suggested_price_category="Weaner Piglets|10_to_14_Kg",
        )
        summary = sam_live_stock_runtime.summarize_live_stock_availability(
            [row], {"sales_lane": "live_stock_sales", "sex": "female"}
        )
        self.assertEqual(
            summary["customer_category_counts"]["Young Piglets"]["all"], 1
        )
        self.assertEqual(
            summary["customer_category_counts"]["Weaner Piglets"]["all"], 0
        )

    @staticmethod
    def _active_big_pig_prices():
        return {
            "success": True,
            "configured": True,
            "source": "supabase",
            "price_entries": [
                {
                    "pricing_id": "PRICE-GROWER-20",
                    "sale_category": "Grower Pigs",
                    "weight_band": "20_to_24_Kg",
                    "unit_price": 800,
                    "active": True,
                    "effective_from": "2026-05-21T00:00:00+00:00",
                    "effective_to": "",
                },
                {
                    "pricing_id": "PRICE-GROWER-45",
                    "sale_category": "Grower Pigs",
                    "weight_band": "45_to_49_Kg",
                    "unit_price": 1800,
                    "active": True,
                    "effective_from": "2026-05-21T00:00:00+00:00",
                    "effective_to": "",
                },
                {
                    "pricing_id": "PRICE-FINISHER-50",
                    "sale_category": "Finisher Pigs",
                    "weight_band": "50_to_54_Kg",
                    "unit_price": 2200,
                    "active": True,
                    "effective_from": "2026-05-21T00:00:00+00:00",
                    "effective_to": "",
                },
                {
                    "pricing_id": "PRICE-FINISHER-75",
                    "sale_category": "Finisher Pigs",
                    "weight_band": "75_to_79_Kg",
                    "unit_price": 2700,
                    "active": True,
                    "effective_from": "2026-05-21T00:00:00+00:00",
                    "effective_to": "",
                },
                {
                    "pricing_id": "PRICE-STALE",
                    "sale_category": "Finisher Pigs",
                    "weight_band": "80_to_84_Kg",
                    "unit_price": 9999,
                    "active": False,
                    "effective_from": "2026-05-21T00:00:00+00:00",
                    "effective_to": "",
                },
            ],
        }

    @staticmethod
    def _active_piglet_prices():
        return {
            "success": True,
            "configured": True,
            "source": "supabase",
            "price_entries": [
                {
                    "pricing_id": "PRICE-YOUNG-1",
                    "sale_category": "Young Piglets",
                    "weight_band": "2_to_4_Kg",
                    "unit_price": 350,
                    "active": True,
                    "effective_from": "2026-07-01T00:00:00Z",
                    "effective_to": "",
                },
                {
                    "pricing_id": "PRICE-YOUNG-2",
                    "sale_category": "Young Piglets",
                    "weight_band": "5_to_6_Kg",
                    "unit_price": 400,
                    "active": True,
                    "effective_from": "2026-07-01T00:00:00Z",
                    "effective_to": "",
                },
                {
                    "pricing_id": "PRICE-WEANER-1",
                    "sale_category": "Weaner Piglets",
                    "weight_band": "7_to_9_Kg",
                    "unit_price": 450,
                    "active": True,
                    "effective_from": "2026-07-01T00:00:00Z",
                    "effective_to": "",
                },
                {
                    "pricing_id": "PRICE-WEANER-2",
                    "sale_category": "Weaner Piglets",
                    "weight_band": "15_to_19_Kg",
                    "unit_price": 600,
                    "active": True,
                    "effective_from": "2026-07-01T00:00:00Z",
                    "effective_to": "",
                },
            ],
        }

    @patch("modules.sales.sam_live_stock_runtime.list_live_stock_price_entries")
    def test_conversation_2054_commercial_question_blocks_general_llm_fallback(
        self, price_list
    ):
        price_list.return_value = (self._active_piglet_prices(), 200)
        calls = {"llm": 0, "send": 0}

        def llm(*args, **kwargs):
            calls["llm"] += 1
            return {"reply_text": "unsafe general fallback"}

        result, status = sam_live_stock_runtime.handle_sam_live_stock_chatwoot_inbound(
            inbound_payload(
                content="Do you sell the piglets",
                conversation={
                    "id": 2054,
                    "inbox": {"id": 96568, "channel_type": "Channel::Whatsapp"},
                },
                sender={"id": 699428938, "name": "Fanie"},
            ),
            environ={
                "SAM_LIVE_STOCK_BACKEND_LLM_ENABLED": "1",
                "SAM_LIVE_STOCK_BACKEND_LLM_MODEL": "test",
                "OPENAI_API_KEY": "test-key",
            },
            intake_context_loader=lambda *_: {
                "success": True, "known_fields": {}, "items": []
            },
            conversation_history_loader=lambda *_: {
                "success": True, "messages": []
            },
            availability_loader=lambda: [
                exact_eligible_row(
                    pig_id="PRIVATE-YOUNG", sale_category="Young Piglets",
                    calculated_stage="Piglet", current_weight_kg=5,
                    weight_band="5_to_6_Kg",
                ),
                exact_eligible_row(
                    pig_id="PRIVATE-WEANER", sale_category="Weaner Piglets",
                    calculated_stage="Weaner", current_weight_kg=12,
                    weight_band="10_to_14_Kg", sex="Male",
                ),
            ],
            llm_drafter=llm,
            chatwoot_sender=lambda *_: calls.__setitem__(
                "send", calls["send"] + 1
            ),
        )
        decision = result["sam_decision"]
        self.assertEqual(status, 200)
        self.assertEqual(decision["sales_lane"], "live_stock_sales")
        self.assertTrue(
            decision["contextual_sales"]["general_information_fallback_blocked"]
        )
        self.assertEqual(
            decision["contextual_sales"]["interpretation"]["message_type"],
            "availability_enquiry",
        )
        self.assertEqual(
            decision["contextual_sales"]["interpretation"]["category"], ""
        )
        self.assertIn("Yes, we do sell piglets", decision["suggested_reply_text"])
        self.assertIn("Young piglets", decision["suggested_reply_text"])
        self.assertIn("Weaners", decision["suggested_reply_text"])
        self.assertIn("How many are you looking for", decision["suggested_reply_text"])
        self.assertNotIn("PRIVATE-", decision["suggested_reply_text"])
        self.assertEqual(calls, {"llm": 0, "send": 0})
        self.assertFalse(result["sends_customer_message"])
        self.assertFalse(result["creates_order"])
        self.assertFalse(result["reserves_stock"])

    @patch("modules.sales.sam_live_stock_runtime.list_live_stock_price_entries")
    def test_conversation_67_uses_prior_context_and_latest_phonetic_request(
        self, price_list
    ):
        price_list.return_value = (self._active_piglet_prices(), 200)
        result, status = sam_live_stock_runtime.handle_sam_live_stock_chatwoot_inbound(
            inbound_payload(
                content="Soggies to bay 10",
                conversation={
                    "id": 67,
                    "inbox": {"id": 96568, "channel_type": "Channel::Whatsapp"},
                },
                sender={"id": 699428938, "name": "Lionel"},
            ),
            environ={},
            intake_context_loader=lambda *_: {
                "success": True, "known_fields": {}, "items": []
            },
            conversation_history_loader=lambda *_: {
                "success": True,
                "messages": [{
                    "id": "67-prior",
                    "message_type": 0,
                    "content": "I asked about Ms. Piggy’s piglets.",
                }],
            },
            availability_loader=lambda: [
                exact_eligible_row(
                    pig_id="PRIVATE-YOUNG", sale_category="Young Piglets",
                    calculated_stage="Piglet", current_weight_kg=5,
                    weight_band="5_to_6_Kg",
                ),
                exact_eligible_row(
                    pig_id="PRIVATE-WEANER", sale_category="Weaner Piglets",
                    calculated_stage="Weaner", current_weight_kg=12,
                    weight_band="10_to_14_Kg",
                ),
            ],
        )
        interpretation = result["sam_decision"]["contextual_sales"]["interpretation"]
        self.assertEqual(status, 200)
        self.assertEqual(interpretation["intent"], "buy_live_pigs")
        self.assertEqual(interpretation["quantity"], 10)
        self.assertEqual(interpretation["sex"], "female")
        self.assertEqual(interpretation["category"], "")
        reply = result["sam_decision"]["suggested_reply_text"]
        self.assertIn("no single category currently has all 10", reply)
        self.assertNotIn("split across categories", reply)
        self.assertIn("check again when more eligible animals become available", reply)
        self.assertIn("does not reserve the animals", reply)
        self.assertFalse(result["sent"])

    @patch("modules.sales.sam_live_stock_runtime.list_live_stock_price_entries")
    def test_big_one_and_pricce_uses_verified_grower_finisher_information(self, price_list):
        price_list.return_value = (self._active_big_pig_prices(), 200)
        calls = {"availability": 0, "send": 0}

        def availability():
            calls["availability"] += 1
            return [
                exact_eligible_row(
                    pig_id="G-1", sale_category="Grower Pigs",
                    calculated_stage="Grower", current_weight_kg=44,
                    weight_band="40_to_44_Kg",
                ),
                exact_eligible_row(
                    pig_id="G-2", sale_category="Grower Pigs",
                    calculated_stage="Grower", current_weight_kg=45,
                    weight_band="45_to_49_Kg",
                ),
                exact_eligible_row(
                    pig_id="F-1", sale_category="Finisher Pigs",
                    calculated_stage="Finisher", current_weight_kg=60,
                    weight_band="60_to_64_Kg",
                ),
                exact_eligible_row(
                    pig_id="P-1", sale_category="Young Piglets",
                    calculated_stage="Piglet", current_weight_kg=6,
                    weight_band="5_to_6_Kg",
                ),
            ]

        result, status = sam_live_stock_runtime.handle_sam_live_stock_chatwoot_inbound(
            inbound_payload(
                id=760317643,
                content="I want the big one and the pricce please",
                content_attributes={
                    "referral": {
                        "source_type": "ad",
                        "source_id": "stale-piglet-post",
                        "headline": "Piglets",
                    },
                },
            ),
            environ={},
            intake_context_loader=lambda *_args: {"success": True, "known_fields": {}, "items": []},
            conversation_history_loader=lambda *_args: {
                "success": True,
                "messages": [{"id": "old", "message_type": 0, "content": "Tell me about piglets"}],
            },
            availability_loader=availability,
            chatwoot_sender=lambda *_args: calls.__setitem__("send", calls["send"] + 1),
        )

        decision = result["sam_decision"]
        reply = decision["suggested_reply_text"]
        self.assertEqual(status, 200)
        self.assertEqual(decision["sales_lane"], "live_stock_sales")
        self.assertEqual(decision["facts"]["information_scope"], "grower_finisher")
        self.assertEqual(decision["information_response"]["status"], "availability_and_pricing_verified")
        self.assertIn("Growers: 2 currently eligible", reply)
        self.assertIn("Finishers: 1 currently eligible", reply)
        self.assertNotIn("Piglet", reply)
        self.assertNotIn("9,999", reply)
        self.assertEqual(reply.count("?"), 1)
        self.assertEqual(calls, {"availability": 1, "send": 0})
        self.assertFalse(result["sends_customer_message"])
        self.assertFalse(result["creates_order"])
        self.assertFalse(result["reserves_stock"])

    @patch("modules.sales.sam_live_stock_runtime.list_live_stock_price_entries")
    def test_big_one_incomplete_message_selects_livestock_and_asks_one_detail(self, price_list):
        price_list.return_value = (self._active_big_pig_prices(), 200)
        result, _status = sam_live_stock_runtime.handle_sam_live_stock_chatwoot_inbound(
            inbound_payload(content="big one"),
            environ={},
            intake_context_loader=lambda *_args: {"success": True, "known_fields": {}, "items": []},
            conversation_history_loader=lambda *_args: {"success": True, "messages": []},
            availability_loader=lambda: [
                exact_eligible_row(
                    sale_category="Finisher Pigs", calculated_stage="Finisher",
                    current_weight_kg=60, weight_band="60_to_64_Kg",
                ),
            ],
        )
        decision = result["sam_decision"]
        self.assertEqual(decision["sales_lane"], "live_stock_sales")
        self.assertIn("Finishers: 1 currently eligible", decision["suggested_reply_text"])
        self.assertEqual(decision["suggested_reply_text"].count("?"), 1)

    @patch("modules.sales.sam_live_stock_runtime.list_live_stock_price_entries")
    def test_big_pig_information_falls_back_to_price_only_when_availability_unavailable(self, price_list):
        price_list.return_value = (self._active_big_pig_prices(), 200)
        result, _status = sam_live_stock_runtime.handle_sam_live_stock_chatwoot_inbound(
            inbound_payload(content="big ones pricce"),
            environ={},
            intake_context_loader=lambda *_args: {"success": True, "known_fields": {}, "items": []},
            conversation_history_loader=lambda *_args: {"success": True, "messages": []},
            availability_loader=lambda: (_ for _ in ()).throw(RuntimeError("unavailable")),
        )
        decision = result["sam_decision"]
        self.assertEqual(decision["information_response"]["status"], "price_only_verified")
        self.assertEqual(
            decision["contextual_sales"]["status"],
            "commercial_evidence_unavailable",
        )
        self.assertIn(
            "checking the current livestock availability and pricing",
            decision["suggested_reply_text"],
        )
        self.assertNotIn("currently eligible", decision["suggested_reply_text"])
        self.assertFalse(result["sent"])

    def test_pricce_spelling_is_a_livestock_price_signal_with_current_context(self):
        facts = sam_live_stock_runtime.extract_live_stock_facts("pricce")
        self.assertTrue(facts["quote_requested"])
        self.assertEqual(facts["sales_lane"], "live_stock_sales")

    def test_llm_commitment_reservation_reply_is_repaired_before_payment_question(self):
        result, status = sam_live_stock_runtime.handle_sam_live_stock_chatwoot_inbound(
            inbound_payload(
                content="Yes, I am ready to proceed. Please reserve the pig for me.",
                conversation={"id": 1826, "inbox": {"channel_type": "Channel::Whatsapp"}},
            ),
            environ={
                "SAM_LIVE_STOCK_BACKEND_LLM_ENABLED": "1",
                "SAM_LIVE_STOCK_BACKEND_LLM_MODEL": "test-model",
                "OPENAI_API_KEY": "test-key",
            },
            intake_context_loader=lambda _conversation_id: {
                "success": True,
                "known_fields": {"collection_location": "Riversdale", "order_commitment": False},
                "items": [{
                    "quantity": 1,
                    "category": "Grower",
                    "weight_range": "25-29 kg",
                    "sex": "Male",
                    "status": "active",
                }],
            },
            conversation_history_loader=lambda *_args: {
                "success": True,
                "messages": [
                    {"id": "1826-1", "message_type": 0, "content": "I want 1 male grower around 25 to 29 kg."},
                    {"id": "1826-2", "message_type": 0, "content": "I will collect in Riversdale."},
                    {"id": "1826-3", "message_type": 1, "content": "Are you ready to commit to this order?"},
                ],
            },
            availability_loader=lambda: [],
            llm_drafter=lambda *_args: {
                "reply_text": (
                    "Hi Charl, thanks for letting me know you're ready. "
                    "The price is around R1,000. How would you prefer to handle payment?"
                ),
                "confidence": 0.99,
            },
        )

        decision = result["sam_decision"]
        reply = decision["suggested_reply_text"]
        self.assertEqual(status, 200)
        self.assertEqual(decision["reply_source"], "deterministic_read_only_guard")
        self.assertFalse(decision["llm_draft"]["used"])
        self.assertEqual(
            decision["llm_draft"]["status"],
            "commercial_general_information_fallback_blocked",
        )
        self.assertTrue(decision["facts"]["order_commitment"])
        self.assertTrue(decision["facts"]["reservation_requested"])
        self.assertEqual(decision["conversation_plan"]["goal"], "buy_live_stock: 1 Grower 25-29 kg")
        self.assertNotIn("R1,000", reply)
        self.assertNotIn("handle payment", reply)
        self.assertEqual(
            decision["conversation_review"]["protected_action_reasons"],
            ["final_order_owner_authority", "reservation_owner_authority"],
        )
        self.assertFalse(result["sent"])
        self.assertFalse(decision["customer_send_allowed"])
        self.assertFalse(decision["creates_order"])
        self.assertFalse(decision["reserves_stock"])
        self.assertFalse(decision["changes_stock"])

    def test_afrikaans_reservation_composition_keeps_greeting_and_one_question(self):
        reply = sam_live_stock_runtime._compose_reservation_protection_reply(
            {"customer_language": "afrikaans"},
            "Hallo Charl, dankie dat jy laat weet het jy is gereed. Die prys is ongeveer R1 000. Hoe wil jy betaling hanteer?",
        )

        self.assertTrue(reply.startswith("Hallo Charl, dankie"))
        self.assertLess(reply.index("plaas moet die presiese vark goedkeur"), reply.index("Die prys"))
        self.assertIn("voordat ek dit vir jou kan bevestig of reserveer", reply)
        self.assertEqual(reply.lower().count("hallo charl"), 1)
        self.assertEqual(reply.lower().count("dankie"), 1)
        self.assertEqual(reply.lower().count("reserveringsversoek"), 1)
        self.assertEqual(reply.count("R1 000"), 1)
        self.assertEqual(reply.count("?"), 1)

    def test_partial_reservation_wording_uses_one_complete_localized_reply(self):
        reply = sam_live_stock_runtime._compose_reservation_protection_reply(
            {"customer_language": "english"},
            "Hi Charl, I noted the reservation. Can you confirm payment?",
        )

        self.assertEqual(reply.lower().count("reservation request"), 1)
        self.assertEqual(reply.count("?"), 0)
        self.assertIn("farm must approve the exact pig", reply)

    def test_llm_payment_security_implication_is_rejected(self):
        result, _status = sam_live_stock_runtime.handle_sam_live_stock_chatwoot_inbound(
            inbound_payload(content="Yes, proceed and reserve the pig for me."),
            environ={
                "SAM_LIVE_STOCK_BACKEND_LLM_ENABLED": "1",
                "SAM_LIVE_STOCK_BACKEND_LLM_MODEL": "test-model",
                "OPENAI_API_KEY": "test-key",
            },
            intake_context_loader=lambda _conversation_id: {
                "success": True,
                "known_fields": {"collection_location": "Riversdale"},
                "items": [{"quantity": 1, "category": "Grower", "weight_range": "25-29 kg", "sex": "Male"}],
            },
            conversation_history_loader=lambda *_args: {
                "success": True,
                "messages": [{
                    "id": "1826-prior",
                    "message_type": 0,
                    "content": "I want 1 male grower around 25 to 29 kg and will collect in Riversdale.",
                }],
            },
            availability_loader=lambda: [],
            llm_drafter=lambda *_args: {
                "reply_text": "Thanks. Your payment method will secure the pig. Which method will you use?",
                "confidence": 0.99,
            },
        )

        decision = result["sam_decision"]
        self.assertEqual(decision["reply_source"], "deterministic_read_only_guard")
        self.assertFalse(decision["llm_draft"]["used"])
        self.assertEqual(
            decision["llm_draft"]["status"],
            "commercial_general_information_fallback_blocked",
        )
        self.assertNotIn("payment method will secure", decision["suggested_reply_text"])
        self.assertFalse(result["sent"])
        self.assertFalse(decision["creates_order"])
        self.assertFalse(decision["reserves_stock"])
        self.assertFalse(decision["changes_stock"])

    def test_commitment_and_reservation_followup_preserves_context_and_owner_gate(self):
        variants = (
            (
                "Yes, I am ready to proceed. Please reserve the pig for me.",
                "english",
                "ready to proceed",
            ),
            (
                "Ja, ek is gereed om voort te gaan. Reserveer asseblief die vark vir my.",
                "afrikaans",
                "gereed is om voort te gaan",
            ),
        )
        prior_messages = [
            {"id": "1826-1", "message_type": 0, "content": "I want 1 male grower around 25 to 29 kg."},
            {"id": "1826-2", "message_type": 0, "content": "I will collect in Riversdale."},
            {"id": "1826-3", "message_type": 1, "content": "Are you ready to commit to this order?"},
        ]
        for message, language, acknowledgement in variants:
            with self.subTest(message=message):
                result, status = sam_live_stock_runtime.handle_sam_live_stock_chatwoot_inbound(
                    inbound_payload(content=message, conversation={
                        "id": 1826,
                        "inbox": {"channel_type": "Channel::Whatsapp"},
                    }),
                    environ={},
                    intake_context_loader=lambda _conversation_id: {
                        "success": True,
                        "known_fields": {
                            "collection_location": "Riversdale",
                            "order_commitment": False,
                        },
                        "items": [{
                            "quantity": 1,
                            "category": "Grower",
                            "weight_range": "25-29 kg",
                            "sex": "Male",
                            "status": "active",
                        }],
                    },
                    conversation_history_loader=lambda *_args: {
                        "success": True,
                        "messages": prior_messages,
                    },
                    availability_loader=lambda: [],
                )

                decision = result["sam_decision"]
                self.assertEqual(status, 200)
                self.assertEqual(decision["facts"]["message_intent"], "order_commitment")
                self.assertEqual(decision["facts"]["customer_language"], language)
                self.assertTrue(decision["facts"]["order_commitment"])
                self.assertTrue(decision["facts"]["reservation_requested"])
                self.assertEqual(decision["conversation_plan"]["goal"], "buy_live_stock: 1 Grower 25-29 kg")
                self.assertNotIn("order_commitment", decision["missing_fields"])
                self.assertIn(acknowledgement, decision["suggested_reply_text"])
                self.assertIn("farm" if language == "english" else "plaas", decision["suggested_reply_text"])
                self.assertNotIn("ready to commit", decision["suggested_reply_text"].lower())
                self.assertIn("reservation_request_owner_gate", decision["blockers"])
                self.assertIn("reservation_owner_authority", decision["conversation_review"]["protected_action_reasons"])
                self.assertFalse(result["sent"])
                self.assertFalse(decision["customer_send_allowed"])
                self.assertFalse(decision["creates_order"])
                self.assertFalse(decision["reserves_stock"])
                self.assertFalse(decision["changes_stock"])

    @patch("modules.sales.sam_live_stock_runtime.delegate_to_agent")
    def test_production_availability_path_delegates_to_herdmaster(self, delegate):
        delegate.return_value = ({
            "success": True, "availability_rows": [{"pig_id": "P1", "available_for_sale": True}],
            "agent": {"agent_id": "herdmaster"}, "sources": [{"name": "sales_availability"}],
        }, 200)
        context = sam_live_stock_runtime.load_live_stock_read_context({}, {"category": "piglet"}, environ={})
        self.assertEqual(delegate.call_args.args[0], "herdmaster")
        self.assertEqual(context["agent_evidence"]["herdmaster"]["agent"]["agent_id"], "herdmaster")

    def test_afrikaans_location_question_gets_afrikaans_farm_answer(self):
        result, status = sam_live_stock_runtime.handle_sam_live_stock_chatwoot_inbound(
            inbound_payload(content="Waar is julle asseblief?"),
            environ={},
            intake_context_loader=lambda _conversation_id: {"success": False, "items": []},
            conversation_history_loader=lambda *_args: {"success": True, "messages": []},
            availability_loader=lambda: [],
        )
        self.assertEqual(status, 200)
        decision = result["sam_decision"]
        self.assertEqual(decision["facts"]["customer_language"], "afrikaans")
        self.assertIn("Riversdal", decision["suggested_reply_text"])
        self.assertIn("Afhaal", decision["suggested_reply_text"])

    def test_voice_note_transcript_drives_live_stock_understanding(self):
        payload = inbound_payload(content="", attachments=[{
            "file_type": "audio",
            "data_url": "https://example.test/voice.ogg",
            "content_type": "audio/ogg",
        }])
        result, status = sam_live_stock_runtime.handle_sam_live_stock_chatwoot_inbound(
            payload,
            environ={},
            voice_transcriber=lambda *_args: {"status": "transcribed", "transcript": "Ek soek drie varkies vir Vrydag"},
            intake_context_loader=lambda _conversation_id: {"success": False, "items": []},
            conversation_history_loader=lambda *_args: {"success": True, "messages": []},
            availability_loader=lambda: [],
        )
        self.assertEqual(status, 200)
        decision = result["sam_decision"]
        self.assertEqual(decision["input_understanding"]["voice"]["status"], "transcribed")
        self.assertEqual(decision["facts"]["customer_language"], "afrikaans")
        self.assertEqual(decision["facts"]["message_intent"], "buying_intent")

    def test_image_only_message_is_processed_but_media_facts_remain_untrusted(self):
        payload = inbound_payload(content="", attachments=[{
            "file_type": "image",
            "data_url": "https://example.test/pig.jpg",
            "content_type": "image/jpeg",
        }])
        result, status = sam_live_stock_runtime.handle_sam_live_stock_chatwoot_inbound(
            payload,
            environ={},
            image_classifier=lambda *_args: {"classification": "customer_pig_image"},
            intake_context_loader=lambda _conversation_id: {"success": False, "items": []},
            conversation_history_loader=lambda *_args: {"success": True, "messages": []},
            availability_loader=lambda: [],
        )
        self.assertEqual(status, 200)
        decision = result["sam_decision"]
        self.assertTrue(decision["input_understanding"]["images"])
        self.assertFalse(decision["input_understanding"]["images"][0]["facts_trusted"])
    def test_authorize_webhook_is_default_off_and_token_gated(self):
        allowed, denied = sam_live_stock_runtime.authorize_sam_live_stock_webhook({}, environ={})

        self.assertFalse(allowed)
        self.assertEqual(denied["status"], "sam_live_stock_backend_webhook_disabled")
        self.assertFalse(denied["sends_customer_message"])
        self.assertFalse(denied["creates_order"])
        self.assertFalse(denied["reserves_stock"])

        env = {
            "SAM_LIVE_STOCK_BACKEND_WEBHOOK_ENABLED": "1",
            "SAM_LIVE_STOCK_BACKEND_WEBHOOK_TOKEN": "test-sam-live-stock-token-32-chars",
        }
        allowed, _denied = sam_live_stock_runtime.authorize_sam_live_stock_webhook(
            {"Authorization": "Bearer test-sam-live-stock-token-32-chars"},
            environ=env,
        )

        self.assertTrue(allowed)

        allowed, _denied = sam_live_stock_runtime.authorize_sam_live_stock_webhook(
            {"X-Amadeus-Sam-Live-Stock-Webhook-Key": "test-sam-live-stock-token-32-chars"},
            environ=env,
        )

        self.assertTrue(allowed)

    def test_policy_allows_llm_draft_while_staying_read_only(self):
        policy = sam_live_stock_runtime.sam_live_stock_webhook_policy(environ={
            "SAM_LIVE_STOCK_BACKEND_WEBHOOK_ENABLED": "1",
            "SAM_LIVE_STOCK_BACKEND_WEBHOOK_TOKEN": "test-sam-live-stock-token-32-chars",
            "SAM_LIVE_STOCK_BACKEND_AUTOREPLY_ENABLED": "1",
            "SAM_LIVE_STOCK_BACKEND_LLM_ENABLED": "1",
            "SAM_LIVE_STOCK_BACKEND_AGENT_V3_ENABLED": "1",
            "SAM_LIVE_STOCK_BACKEND_LLM_MODEL": "test-model",
            "OPENAI_API_KEY": "test-key",
            "SAM_LIVE_STOCK_BACKEND_INTAKE_WRITE_ENABLED": "1",
            "SAM_LIVE_STOCK_OWNER_EXAMPLE_RETRIEVAL_ENABLED": "1",
        })

        self.assertTrue(policy["enabled"])
        self.assertTrue(policy["autoreply_explicitly_enabled"])
        self.assertTrue(policy["autoreply_enabled"])
        self.assertTrue(policy["llm_enabled"])
        self.assertFalse(policy["agent_v3_enabled"])
        self.assertTrue(policy["read_only"])
        self.assertFalse(policy["writes_allowed"])
        self.assertTrue(policy["customer_send_allowed"])
        self.assertTrue(policy["owner_example_retrieval_enabled"])
        self.assertEqual(policy["owner_example_retrieval_env"], "SAM_LIVE_STOCK_OWNER_EXAMPLE_RETRIEVAL_ENABLED")
        self.assertTrue(policy["intake_write_enabled"])
        self.assertTrue(policy["llm_runtime_diagnostics"]["source_is_mapping"])
        self.assertTrue(policy["llm_runtime_diagnostics"]["llm_enabled"])
        self.assertTrue(policy["llm_runtime_diagnostics"]["llm_configured"])
        self.assertFalse(policy["llm_runtime_diagnostics"]["contains_secret_values"])

    def test_policy_defaults_llm_model_and_owner_example_retrieval_on(self):
        policy = sam_live_stock_runtime.sam_live_stock_webhook_policy(environ={
            "SAM_LIVE_STOCK_BACKEND_WEBHOOK_ENABLED": "1",
            "SAM_LIVE_STOCK_BACKEND_WEBHOOK_TOKEN": "test-sam-live-stock-token-32-chars",
            "SAM_LIVE_STOCK_BACKEND_LLM_ENABLED": "1",
            "OPENAI_API_KEY": "test-key",
        })

        self.assertTrue(policy["llm_configured"])
        self.assertTrue(policy["llm_enabled"])
        self.assertEqual(policy["llm_default_model"], "gpt-4.1-mini")
        self.assertTrue(policy["owner_example_retrieval_enabled"])
        self.assertEqual(policy["owner_example_retrieval_default"], "enabled_unless_env_is_false")
        self.assertFalse(policy["meat_public_offer_enabled"])

    def test_policy_can_explicitly_disable_owner_example_retrieval(self):
        policy = sam_live_stock_runtime.sam_live_stock_webhook_policy(environ={
            "SAM_LIVE_STOCK_OWNER_EXAMPLE_RETRIEVAL_ENABLED": "0",
        })

        self.assertFalse(policy["owner_example_retrieval_enabled"])

    def test_parse_chatwoot_inbound_ignores_outbound_messages(self):
        inbound = sam_live_stock_runtime.parse_chatwoot_inbound(inbound_payload(message_type="outgoing"))

        self.assertFalse(inbound["processable"])
        self.assertEqual(inbound["status"], "ignored_non_incoming_message")

    def test_extract_live_stock_facts_from_clear_request(self):
        inbound = sam_live_stock_runtime.parse_chatwoot_inbound(inbound_payload())
        facts = sam_live_stock_runtime.extract_live_stock_facts(inbound["content"], inbound)

        self.assertEqual(facts["sales_lane"], "live_stock_sales")
        self.assertEqual(facts["category"], "weaner")
        self.assertEqual(facts["quantity"], 3)
        self.assertEqual(facts["sex"], "female")
        self.assertEqual(facts["weight_range"], "10-15 kg")
        self.assertEqual(facts["timing"], "next week")
        self.assertEqual(facts["location"], "Riversdale")
        self.assertFalse(facts["llm_used"])

    def test_extract_live_stock_facts_infers_category_from_weight_band(self):
        facts = sam_live_stock_runtime.extract_live_stock_facts(
            "Can you send pics of the 7-9kg ones, I will take 3 female 1 male",
            {"conversation_id": "1478"},
        )

        self.assertEqual(facts["sales_lane"], "live_stock_sales")
        self.assertEqual(facts["category"], "weaner")
        self.assertEqual(facts["weight_range"], "7-9 kg")
        self.assertEqual(facts["quantity"], 3)
        self.assertEqual(facts["sex"], "split")

    def test_extract_live_stock_facts_treats_six_week_old_pics_as_piglet_interest(self):
        facts = sam_live_stock_runtime.extract_live_stock_facts(
            "Morning how much is your 6 weeks old pics",
            {"conversation_id": "1828"},
        )

        self.assertEqual(facts["sales_lane"], "live_stock_sales")
        self.assertEqual(facts["category"], "piglet")
        self.assertTrue(facts["quote_requested"])

    def test_extract_live_stock_facts_recognises_port_elizabeth_context(self):
        facts = sam_live_stock_runtime.extract_live_stock_facts(
            "I'm in Eastern Cape Port Elizabeth and I can collect",
            {"conversation_id": "1927"},
        )

        self.assertEqual(facts["location"], "Port Elizabeth")
        self.assertEqual(facts["transport_expectation"], "collection_requested")

    def test_non_live_pork_message_gets_specific_clarification(self):
        facts = sam_live_stock_runtime.extract_live_stock_facts(
            "I'm a qualified butcher and I am looking for pork",
            {"conversation_id": "1927"},
        )
        reply = sam_live_stock_runtime._safe_reply_draft(
            facts,
            {"lane": "owner_handoff"},
            [],
            {},
            [],
        )

        self.assertIn("live pigs to slaughter yourself", reply)
        self.assertIn("processed pork", reply)
        self.assertNotIn("What detail should I note", reply)

    def test_merge_prior_context_fills_missing_values_only(self):
        facts = sam_live_stock_runtime.extract_live_stock_facts("I need 2 weaners", {})
        merged = sam_live_stock_runtime.merge_prior_live_stock_context(
            facts,
            {
                "interest": {
                    "sex": "male",
                    "timing": "next week",
                    "location": "Riversdale",
                    "payment_method": "EFT",
                }
            },
        )

        self.assertEqual(merged["quantity"], 2)
        self.assertEqual(merged["category"], "weaner")
        self.assertEqual(merged["sex"], "male")
        self.assertEqual(merged["timing"], "next week")
        self.assertEqual(merged["location"], "Riversdale")

    def test_merge_prior_context_preserves_positive_quote_intent(self):
        facts = sam_live_stock_runtime.extract_live_stock_facts(
            "Can you keep them for me until Friday?",
            {"conversation_id": "2401"},
        )
        merged = sam_live_stock_runtime.merge_prior_live_stock_context(
            facts,
            {
                "interest": {
                    "quantity": 2,
                    "category": "Weaner",
                    "weight_range": "10_to_14_Kg",
                    "sex": "Female",
                    "location": "Riversdale",
                    "quote_requested": True,
                }
            },
        )

        self.assertTrue(merged["quote_requested"])
        self.assertEqual(merged["sales_lane"], "live_stock_sales")

    def test_chatwoot_history_fills_latest_short_reply_context(self):
        result, _status_code = sam_live_stock_runtime.handle_sam_live_stock_chatwoot_inbound(
            inbound_payload(
                content="Tank you albertinia can do",
                id=730727167,
                conversation={"id": 1478, "inbox": {"channel_type": "Channel::Whatsapp"}},
            ),
            environ={},
            intake_context_loader=lambda _conversation_id: {"success": True, "known_fields": {}, "items": []},
            conversation_history_loader=lambda _conversation_id, _source: {
                "success": True,
                "status": "loaded",
                "messages": [
                    {"id": 730682977, "message_type": 0, "created_at": 1783530000, "content": "2 female 1 male"},
                    {"id": 730720079, "message_type": 0, "created_at": 1783530100, "content": "Ok how big is the (7-9) kg if you can send me pics of them please please then i will take 3 female 1 male"},
                    {"id": 730727167, "message_type": 0, "created_at": 1783530200, "content": "Tank you albertinia can do"},
                ],
            },
            availability_loader=lambda: [],
        )

        decision = result["sam_decision"]
        self.assertEqual(decision["sales_lane"], "live_stock_sales")
        self.assertEqual(decision["facts"]["quantity"], 3)
        self.assertEqual(decision["facts"]["sex"], "split")
        self.assertEqual(decision["facts"]["location"], "Albertinia")
        self.assertNotIn("are you looking for live pigs, pork", decision["suggested_reply_text"])
        self.assertEqual(decision["read_context"]["chatwoot_history"]["incoming_count"], 3)

    def test_live_stock_followup_questions_do_not_fall_back_to_lane_clarifier(self):
        for message in ("How much for 1", "Must I come there.or will you transport"):
            result, _status_code = sam_live_stock_runtime.handle_sam_live_stock_chatwoot_inbound(
                inbound_payload(content=message),
                intake_context_loader=lambda _conversation_id: {"success": True, "known_fields": {}, "items": []},
                conversation_history_loader=lambda _conversation_id, _source: {"success": True, "messages": []},
                availability_loader=lambda: [],
            )

            decision = result["sam_decision"]
            self.assertEqual(decision["sales_lane"], "live_stock_sales", message)
            self.assertNotIn("lane_not_live_stock:unclear", decision["blockers"], message)
            self.assertNotIn("are you looking for live pigs, pork", decision["suggested_reply_text"], message)

    def test_location_followup_inherits_active_live_stock_context(self):
        result, _status_code = sam_live_stock_runtime.handle_sam_live_stock_chatwoot_inbound(
            inbound_payload(content="Location"),
            intake_context_loader=lambda _conversation_id: {
                "success": True,
                "known_fields": {},
                "items": [{
                    "quantity": 3,
                    "category": "Piglet",
                    "weight_range": "7_to_9_Kg",
                    "status": "active",
                }],
            },
            conversation_history_loader=lambda _conversation_id, _source: {"success": True, "messages": []},
            availability_loader=lambda: [],
        )

        decision = result["sam_decision"]
        self.assertEqual(decision["sales_lane"], "live_stock_sales")
        self.assertNotIn("are you looking for live pigs, pork", decision["suggested_reply_text"])

    def test_general_location_question_gets_farm_knowledge_reply_candidate(self):
        result, status_code = sam_live_stock_runtime.handle_sam_live_stock_chatwoot_inbound(
            inbound_payload(content="Where are u guys pls", sender={"name": "Anda"}),
            intake_context_loader=lambda _conversation_id: {"success": True, "known_fields": {}, "items": []},
            conversation_history_loader=lambda _conversation_id, _source: {"success": True, "messages": []},
            availability_loader=lambda: [],
        )

        decision = result["sam_decision"]
        review = decision["conversation_review"]
        self.assertEqual(status_code, 200)
        self.assertEqual(decision["sales_lane"], "farm_general_question")
        self.assertEqual(decision["reply_source"], "deterministic_farm_general_knowledge")
        self.assertIn("Riversdale", decision["suggested_reply_text"])
        self.assertNotIn("are you looking for live pigs, pork", decision["suggested_reply_text"])
        self.assertNotIn("lane_not_live_stock:farm_general_question", decision.get("blockers", []))
        self.assertNotIn("wrong_or_unclear_lane", review["escalation_reasons"])
        self.assertFalse(result["sent"])

    def test_general_ad_question_gets_useful_farm_reply_candidate(self):
        result, status_code = sam_live_stock_runtime.handle_sam_live_stock_chatwoot_inbound(
            inbound_payload(content="Can you tell me more about your ad?", sender={"name": "Rudolf Kriel"}),
            intake_context_loader=lambda _conversation_id: {"success": True, "known_fields": {}, "items": []},
            conversation_history_loader=lambda _conversation_id, _source: {"success": True, "messages": []},
            availability_loader=lambda: [],
        )

        decision = result["sam_decision"]
        self.assertEqual(status_code, 200)
        self.assertEqual(decision["sales_lane"], "farm_general_question")
        self.assertEqual(decision["reply_source"], "deterministic_farm_general_knowledge")
        self.assertIn("Amadeus Farm", decision["suggested_reply_text"])
        self.assertIn("Riversdale", decision["suggested_reply_text"])
        self.assertIn("what you are interested in", decision["suggested_reply_text"])
        self.assertNotIn("are you looking for live pigs, pork", decision["suggested_reply_text"])

    def test_general_farm_reply_does_not_publicly_offer_meat_until_enabled(self):
        result, _status_code = sam_live_stock_runtime.handle_sam_live_stock_chatwoot_inbound(
            inbound_payload(content="Can you tell me more about your business?", sender={"name": "Rudolf Kriel"}),
            environ={"SAM_MEAT_PUBLIC_OFFER_ENABLED": "0"},
            intake_context_loader=lambda _conversation_id: {"success": True, "known_fields": {}, "items": []},
            conversation_history_loader=lambda _conversation_id, _source: {"success": True, "messages": []},
            availability_loader=lambda: [],
        )

        reply = result["sam_decision"]["suggested_reply_text"]
        self.assertIn("Live pig sales", reply)
        self.assertIn("Meat sales are not open yet", reply)
        self.assertNotIn("Half carcass", reply)
        self.assertNotIn("freezer", reply.lower())

    def test_general_farm_reply_can_offer_meat_when_public_gate_enabled(self):
        result, _status_code = sam_live_stock_runtime.handle_sam_live_stock_chatwoot_inbound(
            inbound_payload(content="Can you tell me more about your business?", sender={"name": "Rudolf Kriel"}),
            environ={"SAM_MEAT_PUBLIC_OFFER_ENABLED": "1"},
            intake_context_loader=lambda _conversation_id: {"success": True, "known_fields": {}, "items": []},
            conversation_history_loader=lambda _conversation_id, _source: {"success": True, "messages": []},
            availability_loader=lambda: [],
        )

        reply = result["sam_decision"]["suggested_reply_text"]
        self.assertIn("Meat sales", reply)

    def test_general_picture_question_gets_specific_picture_followup(self):
        result, status_code = sam_live_stock_runtime.handle_sam_live_stock_chatwoot_inbound(
            inbound_payload(content="Can you send me some of your pics", sender={"name": "Lucas Junior"}),
            intake_context_loader=lambda _conversation_id: {"success": True, "known_fields": {}, "items": []},
            conversation_history_loader=lambda _conversation_id, _source: {"success": True, "messages": []},
            availability_loader=lambda: [],
        )

        decision = result["sam_decision"]
        self.assertEqual(status_code, 200)
        self.assertEqual(decision["sales_lane"], "farm_general_question")
        self.assertIn("which group you want to see", decision["suggested_reply_text"])
        self.assertIn("piglets", decision["suggested_reply_text"])
        self.assertNotIn("are you looking for live pigs, pork", decision["suggested_reply_text"])

    def test_durable_next_action_acceptance_scenarios_are_table_driven(self):
        complete_intake = {
            "success": True,
            "conversation_id": "1478",
            "known_fields": {
                "collection_location": "Albertinia",
                "payment_method": "Cash",
                "order_commitment": True,
            },
            "items": [{
                "item_key": "item_1",
                "quantity": 3,
                "category": "Piglet",
                "weight_range": "7_to_9_Kg",
                "sex": "Any",
                "status": "active",
            }],
        }
        quote_intake = {
            **complete_intake,
            "draft_order_id": "ORD-2026-12BCCC",
            "known_fields": {**complete_intake["known_fields"], "quote_requested": True},
        }
        availability_rows = [
            exact_eligible_row(pig_id="PIG-1", sale_category="Piglet", calculated_stage="Piglet", current_weight_kg=8),
            exact_eligible_row(pig_id="PIG-2", sale_category="Piglet", calculated_stage="Piglet", current_weight_kg=8),
            exact_eligible_row(pig_id="PIG-3", sex="Male", sale_category="Piglet", calculated_stage="Piglet", current_weight_kg=8),
        ]
        scenarios = [
            {
                "name": "location",
                "message": "Where are u guys pls",
                "intake": {"success": True, "known_fields": {}, "items": []},
                "availability": [],
                "expected_next_action": "answer_location",
            },
            {
                "name": "ad_business",
                "message": "Can you tell me more about your business?",
                "intake": {"success": True, "known_fields": {}, "items": []},
                "availability": [],
                "expected_next_action": "answer_general_info",
            },
            {
                "name": "pictures",
                "message": "Can you send me pictures of your pigs?",
                "intake": {"success": True, "known_fields": {}, "items": []},
                "availability": [],
                "expected_next_action": "prepare_picture_response",
            },
            {
                "name": "price",
                "message": "What is the price for them?",
                "intake": complete_intake,
                "availability": availability_rows,
                "expected_next_action": "answer_price",
            },
            {
                "name": "michaels_collection_timing",
                "message": "Michaels here, Friday afternoon collection is fine.",
                "intake": complete_intake,
                "availability": availability_rows,
                "expected_next_action": "prepare_draft_order",
            },
            {
                "name": "quote_request",
                "message": "Please send me the quote.",
                "intake": quote_intake,
                "availability": availability_rows,
                "expected_next_action": "prepare_quote",
            },
            {
                "name": "natural_close",
                "message": "Thanks, have a good day.",
                "intake": complete_intake,
                "availability": availability_rows,
                "expected_next_action": "no_reply_needed",
            },
        ]

        with patch.object(
            sam_live_stock_runtime,
            "resolve_live_stock_price_rule",
            return_value={
                "found": True,
                "unit_price": 450,
                "source": "test_price_book",
                "price_category": "Piglet",
            },
        ):
            for scenario in scenarios:
                with self.subTest(scenario=scenario["name"]):
                    result, status_code = sam_live_stock_runtime.handle_sam_live_stock_chatwoot_inbound(
                        inbound_payload(content=scenario["message"], sender={"name": "Michaels"}),
                        environ={},
                        intake_context_loader=lambda _conversation_id, current=scenario: current["intake"],
                        conversation_history_loader=lambda _conversation_id, _source: {"success": True, "messages": []},
                        availability_loader=lambda current=scenario: current["availability"],
                        owner_example_loader=lambda *_args, **_kwargs: {"success": True, "examples": []},
                    )

                    decision = result["sam_decision"]
                    self.assertEqual(status_code, 200)
                    self.assertEqual(decision["next_action"], scenario["expected_next_action"])
                    self.assertIn(decision["next_action"], sam_live_stock_runtime.SAM_LIVE_STOCK_DURABLE_NEXT_ACTIONS)
                    self.assertFalse(result["sent"])
                    self.assertFalse(result["sends_customer_message"])
                    self.assertFalse(result["calls_chatwoot"])
                    self.assertFalse(result["reserves_stock"])
                    self.assertFalse(result["changes_stock"])

    def test_decision_uses_intake_planner_missing_and_next_action(self):
        result, status_code = sam_live_stock_runtime.handle_sam_live_stock_chatwoot_inbound(
            inbound_payload(content="Please send me the quote", sender={"name": "Michaels"}),
            environ={},
            intake_context_loader=lambda _conversation_id: {
                "success": True,
                "conversation_id": "1478",
                "known_fields": {
                    "collection_location": "Albertinia",
                    "payment_method": "Cash",
                    "order_commitment": True,
                    "quote_requested": True,
                },
                "items": [{
                    "item_key": "item_1",
                    "quantity": 3,
                    "category": "Piglet",
                    "weight_range": "7_to_9_Kg",
                    "status": "active",
                }],
            },
            conversation_history_loader=lambda _conversation_id, _source: {"success": True, "messages": []},
            availability_loader=lambda: [],
        )

        decision = result["sam_decision"]
        self.assertEqual(status_code, 200)
        self.assertEqual(decision["next_action"], "prepare_draft_order")
        self.assertEqual(decision["internal_next_action"], "create_draft_then_quote")
        self.assertEqual(decision["missing_fields"], ["draft_order_id"])
        self.assertEqual(decision["conversation_plan"]["missing_fields"], decision["missing_fields"])
        self.assertEqual(decision["conversation_stage"], "quote")

    def test_decision_uses_intake_context_draft_order_for_cross_turn_quote(self):
        result, status_code = sam_live_stock_runtime.handle_sam_live_stock_chatwoot_inbound(
            inbound_payload(content="Please send me the quote", sender={"name": "Michaels"}),
            environ={},
            intake_context_loader=lambda _conversation_id: {
                "success": True,
                "conversation_id": "1478",
                "draft_order_id": "ORD-2026-12BCCC",
                "known_fields": {
                    "collection_location": "Albertinia",
                    "payment_method": "Cash",
                    "order_commitment": True,
                    "quote_requested": True,
                },
                "items": [{
                    "item_key": "item_1",
                    "quantity": 3,
                    "category": "Piglet",
                    "weight_range": "7_to_9_Kg",
                    "status": "active",
                }],
            },
            conversation_history_loader=lambda _conversation_id, _source: {"success": True, "messages": []},
            availability_loader=lambda: [],
            owner_example_loader=lambda *_args, **_kwargs: {"success": True, "examples": []},
        )

        decision = result["sam_decision"]
        self.assertEqual(status_code, 200)
        self.assertEqual(decision["next_action"], "prepare_quote")
        self.assertEqual(decision["internal_next_action"], "generate_quote")
        self.assertEqual(decision["missing_fields"], [])
        self.assertEqual(decision["owner_action_packet"]["order_id"], "ORD-2026-12BCCC")
        self.assertEqual(decision["owner_action_packet"]["next_action"], "prepare_quote")
        self.assertEqual(decision["owner_action_packet"]["internal_next_action"], "generate_quote")
        self.assertEqual(decision["owner_action_packet"]["status"], "ready_for_owner_quote_prepare")

    def test_quote_next_action_draft_explains_owner_review_quote_step(self):
        facts = {
            "quantity": 3,
            "category": "Piglet",
            "weight_range": "7_to_9_Kg",
            "quote_requested": True,
        }
        packet = {
            "can_answer_price": True,
            "requested_quantity": 3,
            "requested_category": "Piglet",
            "requested_weight_range": "7_to_9_Kg",
            "unit_price": 450,
            "estimated_total": 1350,
        }

        reply = sam_live_stock_runtime._safe_reply_draft(
            facts,
            {"lane": "live_stock_sales"},
            missing=[],
            availability={"success": True, "matched_count": 11},
            blockers=[],
            price_answer_packet=packet,
            conversation_plan={"next_action": "generate_quote"},
        )

        self.assertIn("Current price estimate", reply)
        self.assertIn("prepare the quote for owner review", reply)
        self.assertIn("Nothing is reserved or sent", reply)

    def test_prepared_owner_action_bundle_requires_order_before_quote(self):
        bundle = sam_live_stock_runtime.build_live_stock_prepared_owner_action_bundle(
            {"conversation_id": "1478"},
            {"quantity": 3, "category": "Piglet", "weight_range": "7_to_9_Kg"},
            conversation_plan={"next_action": "generate_quote", "stage": "quote", "goal": "buy_live_stock: 3 Piglet"},
            draft_packet={"draft_ready": True},
            price_answer_packet={"can_answer_price": True},
        )

        self.assertEqual(bundle["status"], "blocked_until_order_exists")
        self.assertEqual(bundle["label"], "Quote needs draft order first")
        self.assertFalse(bundle["creates_order"])
        self.assertFalse(bundle["sends_customer_message"])

    def test_prepared_owner_action_bundle_exposes_quote_routes_for_existing_order(self):
        bundle = sam_live_stock_runtime.build_live_stock_prepared_owner_action_bundle(
            {"conversation_id": "1478"},
            {"quantity": 3, "category": "Piglet", "weight_range": "7_to_9_Kg"},
            conversation_plan={
                "next_action": "generate_quote",
                "stage": "quote",
                "goal": "buy_live_stock: 3 Piglet",
                "order_state": {"draft_order_id": "ORD-2026-12BCCC"},
            },
            draft_packet={"draft_ready": True},
            price_answer_packet={"can_answer_price": True},
        )

        self.assertEqual(bundle["status"], "ready_for_owner_quote_prepare")
        self.assertEqual(bundle["order_id"], "ORD-2026-12BCCC")
        self.assertIn("/api/orders/ORD-2026-12BCCC/quote/prepare-send", bundle["routes"]["quote_prepare"]["route"])
        self.assertIn("/api/orders/ORD-2026-12BCCC/quote/send-latest-confirmed", bundle["routes"]["quote_send_confirmed"]["route"])
        self.assertFalse(bundle["routes"]["quote_prepare"]["allowed_for_sam_auto"])

    def test_prepared_owner_action_bundle_marks_draft_order_ready(self):
        bundle = sam_live_stock_runtime.build_live_stock_prepared_owner_action_bundle(
            {"conversation_id": "1478"},
            {"quantity": 3, "category": "Piglet", "weight_range": "7_to_9_Kg"},
            conversation_plan={"next_action": "create_draft_then_quote", "stage": "quote"},
            draft_packet={"draft_ready": True, "validation_errors": []},
            price_answer_packet={"can_answer_price": True},
        )

        self.assertEqual(bundle["status"], "ready_for_owner_prepare")
        self.assertEqual(bundle["label"], "Prepare draft order, then quote")
        self.assertTrue(bundle["draft_order_ready"])

    @patch(
        "modules.sales.sam_live_stock_runtime.load_current_level1_control",
        return_value=({"status": "level1_control_not_configured", "event": {}}, 200),
    )
    def test_created_draft_order_refreshes_owner_action_bundle_to_quote_prepare(self, _control):
        writes = []

        def creator(_order_data, _sync_data):
            return {"success": True, "order_id": "ORD-2026-12BCCC"}

        result, status_code = sam_live_stock_runtime.handle_sam_live_stock_chatwoot_inbound(
            inbound_payload(content="Please send me the quote for 3 female weaners around 10 to 15kg in Riversdale."),
            environ={"SAM_LIVE_STOCK_BACKEND_DRAFT_ORDER_CREATE_ENABLED": "1"},
            intake_context_loader=lambda _conversation_id: {
                "success": True,
                "conversation_id": "1478",
                "known_fields": {
                    "collection_location": "Riversdale",
                    "payment_method": "Cash",
                    "order_commitment": True,
                    "quote_requested": True,
                },
                "items": [{
                    "item_key": "item_1",
                    "quantity": 3,
                    "category": "Weaner",
                    "weight_range": "10_to_14_Kg",
                    "sex": "Female",
                    "status": "active",
                }],
            },
            conversation_history_loader=lambda _conversation_id, _source: {"success": True, "messages": []},
            availability_loader=lambda: [
                exact_eligible_row(pig_id="PIG-1", current_weight_kg=12),
                exact_eligible_row(pig_id="PIG-2", current_weight_kg=13),
                exact_eligible_row(pig_id="PIG-3", current_weight_kg=14),
            ],
            draft_order_creator=creator,
            intake_writer=lambda cleaned: writes.append(cleaned) or {"success": True, "draft_order_id": cleaned["patch"]["draft_order_id"]},
        )

        decision = result["sam_decision"]
        bundle = decision["owner_action_packet"]
        self.assertEqual(status_code, 200)
        self.assertEqual(decision["draft_order"]["status"], "sam_live_stock_draft_order_created")
        self.assertEqual(decision["next_action"], "prepare_quote")
        self.assertEqual(decision["internal_next_action"], "generate_quote")
        self.assertEqual(bundle["status"], "ready_for_owner_quote_prepare")
        self.assertEqual(bundle["order_id"], "ORD-2026-12BCCC")
        self.assertIn("/api/orders/ORD-2026-12BCCC/quote/prepare-send", bundle["routes"]["quote_prepare"]["route"])
        self.assertEqual(writes[0]["patch"]["draft_order_id"], "ORD-2026-12BCCC")
        self.assertTrue(writes[0]["patch"]["quote_requested"])

    @patch(
        "modules.sales.sam_live_stock_runtime.load_current_level1_control",
        return_value=({"status": "level1_control_not_configured", "event": {}}, 200),
    )
    def test_created_non_quote_draft_order_refreshes_to_sync_lines(self, _control):
        writes = []

        result, status_code = sam_live_stock_runtime.handle_sam_live_stock_chatwoot_inbound(
            inbound_payload(content="I will take 3 female weaners around 10 to 15kg in Riversdale."),
            environ={"SAM_LIVE_STOCK_BACKEND_DRAFT_ORDER_CREATE_ENABLED": "1"},
            intake_context_loader=lambda _conversation_id: {
                "success": True,
                "conversation_id": "1478",
                "known_fields": {
                    "collection_location": "Riversdale",
                    "order_commitment": True,
                },
                "items": [{
                    "item_key": "item_1",
                    "quantity": 3,
                    "category": "Weaner",
                    "weight_range": "10_to_14_Kg",
                    "sex": "Female",
                    "status": "active",
                }],
            },
            conversation_history_loader=lambda _conversation_id, _source: {"success": True, "messages": []},
            availability_loader=lambda: [
                exact_eligible_row(pig_id="PIG-1", current_weight_kg=12),
                exact_eligible_row(pig_id="PIG-2", current_weight_kg=13),
                exact_eligible_row(pig_id="PIG-3", current_weight_kg=14),
            ],
            draft_order_creator=lambda _order_data, _sync_data: {"success": True, "order_id": "ORD-2026-NOQUOTE"},
            intake_writer=lambda cleaned: writes.append(cleaned) or {"success": True, "draft_order_id": cleaned["patch"]["draft_order_id"]},
        )

        decision = result["sam_decision"]
        bundle = decision["owner_action_packet"]
        self.assertEqual(status_code, 200)
        self.assertEqual(decision["next_action"], "update_draft_order")
        self.assertEqual(decision["internal_next_action"], "sync_lines")
        self.assertEqual(decision["conversation_stage"], "draft_order")
        self.assertEqual(bundle["status"], "ready_for_owner_sync_lines")
        self.assertEqual(bundle["order_id"], "ORD-2026-NOQUOTE")
        self.assertEqual(writes[0]["patch"]["draft_order_id"], "ORD-2026-NOQUOTE")
        self.assertNotIn("quote_requested", writes[0]["patch"])

    @patch(
        "modules.sales.sam_live_stock_runtime.load_current_level1_control",
        return_value=({"status": "level1_control_not_configured", "event": {}}, 200),
    )
    def test_existing_draft_order_is_synced_and_quote_packet_prepared_without_duplicate_create(self, _control):
        creates = []
        syncs = []
        writes = []

        def syncer(order_id, sync_data):
            syncs.append((order_id, sync_data))
            return {
                "success": True,
                "action": "sync_order_lines_from_request",
                "order_id": order_id,
                "complete_fulfillment": True,
                "partial_fulfillment": False,
                "results": [{"request_item_key": "live_stock_primary", "match_status": "exact_match"}],
            }

        result, status_code = sam_live_stock_runtime.handle_sam_live_stock_chatwoot_inbound(
            inbound_payload(content="Please send me the quote for 3 female weaners around 10 to 15kg in Riversdale."),
            environ={"SAM_LIVE_STOCK_BACKEND_DRAFT_ORDER_CREATE_ENABLED": "1"},
            intake_context_loader=lambda _conversation_id: {
                "success": True,
                "conversation_id": "1478",
                "draft_order_id": "ORD-EXISTING-1",
                "known_fields": {
                    "collection_location": "Riversdale",
                    "payment_method": "Cash",
                    "order_commitment": True,
                    "quote_requested": True,
                },
                "items": [{
                    "item_key": "item_1",
                    "quantity": 3,
                    "category": "Weaner",
                    "weight_range": "10_to_14_Kg",
                    "sex": "Female",
                    "status": "active",
                }],
            },
            conversation_history_loader=lambda _conversation_id, _source: {"success": True, "messages": []},
            availability_loader=lambda: [
                exact_eligible_row(pig_id="PIG-1", current_weight_kg=12),
                exact_eligible_row(pig_id="PIG-2", current_weight_kg=13),
                exact_eligible_row(pig_id="PIG-3", current_weight_kg=14),
            ],
            draft_order_creator=lambda order_data, sync_data: creates.append((order_data, sync_data)),
            draft_order_syncer=syncer,
            intake_writer=lambda cleaned: writes.append(cleaned) or {"success": True, "draft_order_id": cleaned["patch"]["draft_order_id"]},
        )

        decision = result["sam_decision"]
        bundle = decision["owner_action_packet"]
        self.assertEqual(status_code, 200)
        self.assertEqual(creates, [])
        self.assertEqual(len(syncs), 1)
        self.assertEqual(syncs[0][0], "ORD-EXISTING-1")
        self.assertEqual(syncs[0][1]["requested_items"][0]["quantity"], 3)
        self.assertEqual(decision["draft_order"]["status"], "sam_live_stock_draft_order_synced")
        self.assertFalse(decision["draft_order"]["created_order"])
        self.assertEqual(decision["next_action"], "prepare_quote")
        self.assertEqual(decision["internal_next_action"], "generate_quote")
        self.assertEqual(bundle["status"], "ready_for_owner_quote_prepare")
        self.assertEqual(bundle["order_id"], "ORD-EXISTING-1")
        self.assertIn("/api/orders/ORD-EXISTING-1/quote/prepare-send", bundle["routes"]["quote_prepare"]["route"])
        self.assertFalse(bundle["routes"]["quote_prepare"]["allowed_for_sam_auto"])
        self.assertEqual(writes[0]["patch"]["draft_order_id"], "ORD-EXISTING-1")
        self.assertTrue(writes[0]["patch"]["quote_requested"])
        self.assertFalse(result["creates_order"])
        self.assertFalse(result["sends_customer_message"])
        self.assertFalse(result["reserves_stock"])

    @patch(
        "modules.sales.sam_live_stock_runtime.load_current_level1_control",
        return_value=({"status": "level1_control_not_configured", "event": {}}, 200),
    )
    def test_existing_draft_order_partial_sync_blocks_quote_packet_prepare(self, _control):
        creates = []
        syncs = []
        writes = []

        def syncer(order_id, sync_data):
            syncs.append((order_id, sync_data))
            return {
                "success": True,
                "action": "sync_order_lines_from_request",
                "order_id": order_id,
                "complete_fulfillment": False,
                "partial_fulfillment": True,
                "results": [{"request_item_key": "live_stock_primary", "match_status": "partial_match"}],
            }

        result, status_code = sam_live_stock_runtime.handle_sam_live_stock_chatwoot_inbound(
            inbound_payload(content="Please send me the quote for 3 female weaners around 10 to 15kg in Riversdale."),
            environ={"SAM_LIVE_STOCK_BACKEND_DRAFT_ORDER_CREATE_ENABLED": "1"},
            intake_context_loader=lambda _conversation_id: {
                "success": True,
                "conversation_id": "1478",
                "draft_order_id": "ORD-EXISTING-PARTIAL",
                "known_fields": {
                    "collection_location": "Riversdale",
                    "payment_method": "Cash",
                    "order_commitment": True,
                    "quote_requested": True,
                },
                "items": [{
                    "item_key": "item_1",
                    "quantity": 3,
                    "category": "Weaner",
                    "weight_range": "10_to_14_Kg",
                    "sex": "Female",
                    "status": "active",
                }],
            },
            conversation_history_loader=lambda _conversation_id, _source: {"success": True, "messages": []},
            availability_loader=lambda: [
                exact_eligible_row(pig_id="PIG-1", current_weight_kg=12),
                exact_eligible_row(pig_id="PIG-2", current_weight_kg=13),
                exact_eligible_row(pig_id="PIG-3", current_weight_kg=14),
            ],
            draft_order_creator=lambda order_data, sync_data: creates.append((order_data, sync_data)),
            draft_order_syncer=syncer,
            intake_writer=lambda cleaned: writes.append(cleaned) or {"success": True, "draft_order_id": cleaned["patch"]["draft_order_id"]},
        )

        decision = result["sam_decision"]
        self.assertEqual(status_code, 200)
        self.assertEqual(creates, [])
        self.assertEqual(len(syncs), 1)
        self.assertEqual(writes, [])
        self.assertEqual(decision["draft_order"]["status"], "sam_live_stock_draft_order_sync_stale_stock")
        self.assertFalse(decision["draft_order"]["success"])
        self.assertIn("sam_live_stock_draft_order_sync_stale_stock", decision["blockers"])
        self.assertNotEqual(decision["owner_action_packet"]["status"], "ready_for_owner_quote_prepare")
        self.assertFalse(result["creates_order"])
        self.assertFalse(result["sends_customer_message"])
        self.assertFalse(result["reserves_stock"])

    def test_llm_reply_draft_is_used_when_enabled_and_configured(self):
        calls = []

        result, _status_code = sam_live_stock_runtime.handle_sam_live_stock_chatwoot_inbound(
            inbound_payload(),
            environ={
                "SAM_LIVE_STOCK_BACKEND_LLM_ENABLED": "1",
                "SAM_LIVE_STOCK_BACKEND_LLM_MODEL": "test-model",
                "OPENAI_API_KEY": "test-key",
            },
            intake_context_loader=lambda _conversation_id: {"success": True, "known_fields": {}, "items": []},
            conversation_history_loader=lambda _conversation_id, _source: {"success": True, "messages": []},
            availability_loader=lambda: [
                {
                    "pig_id": "W-1043",
                    "sex": "Female",
                    "status": "Active",
                    "on_farm": "Yes",
                    "reserved_status": "",
                    "available_for_sale": "Yes",
                    "purpose": "Sale",
                    "sale_category": "Weaner Piglets",
                    "weight_band": "10_to_14_Kg",
                    "current_weight_kg": 12.4,
                }
            ],
            llm_drafter=lambda context, source: calls.append((context, source)) or {
                "reply_text": "Thanks, I can help with female weaners around 10-15kg. I will confirm the current animals with the farm before anything is promised.",
                "confidence": 0.88,
            },
        )

        decision = result["sam_decision"]
        self.assertEqual(
            decision["reply_source"],
            "contextual_sales_source_backed_owner_draft",
        )
        self.assertFalse(decision["llm_draft"]["used"])
        self.assertEqual(calls, [])
        self.assertFalse(result["sent"])
        self.assertFalse(decision["customer_send_allowed"])
        self.assertFalse(decision["facts"]["llm_used"])
        self.assertEqual(
            decision["contextual_sales"]["status"],
            "commercial_evidence_unavailable",
        )

    def test_explicit_new_request_does_not_inherit_old_intake_or_history_facts(self):
        calls = []
        result, status_code = sam_live_stock_runtime.handle_sam_live_stock_chatwoot_inbound(
            inbound_payload(
                content="This is a new request. I am looking for 2 female weaners around 10 to 14 kg. What is the current price?"
            ),
            environ={
                "SAM_LIVE_STOCK_BACKEND_LLM_ENABLED": "1",
                "SAM_LIVE_STOCK_BACKEND_LLM_MODEL": "test-model",
                "OPENAI_API_KEY": "test-key",
            },
            intake_context_loader=lambda _conversation_id: {
                "success": True,
                "known_fields": {
                    "collection_location": "Any",
                    "collection_time_text": "friday",
                    "order_commitment": True,
                },
                "items": [{"category": "Grower", "quantity": 3, "sex": "Male"}],
            },
            conversation_history_loader=lambda *_args: {
                "success": True,
                "messages": [
                    {
                        "id": "old-message",
                        "message_type": 0,
                        "content": "Reserve 3 male growers until Friday.",
                    }
                ],
            },
            availability_loader=lambda: [],
            llm_drafter=lambda context, source: calls.append((context, source)) or {
                "reply_text": "Female weaners in that weight range are R500 each, so 2 would be R1,000.",
                "confidence": 0.99,
            },
        )

        decision = result["sam_decision"]
        self.assertEqual(status_code, 200)
        self.assertEqual(decision["facts"]["category"], "weaner")
        self.assertEqual(decision["facts"]["quantity"], 2)
        self.assertEqual(decision["facts"]["sex"], "female")
        self.assertEqual(decision["facts"]["weight_range"], "10-14 kg")
        self.assertEqual(decision["facts"]["timing"], "")
        self.assertEqual(decision["facts"]["location"], "")
        self.assertFalse(decision["facts"].get("order_commitment"))
        self.assertEqual(decision["read_context"]["prior_context_source"], "")
        self.assertEqual(calls, [])
        self.assertNotIn("reservation_request_owner_gate", decision["blockers"])
        self.assertFalse(decision["facts"]["llm_used"])
        self.assertEqual(
            decision["contextual_sales"]["status"],
            "commercial_evidence_unavailable",
        )

    def test_followup_history_starts_at_latest_explicit_new_request_boundary(self):
        history = {
            "success": True,
            "messages": [
                {
                    "id": "old-reservation",
                    "message_type": 0,
                    "created_at": "2026-07-28T08:00:00Z",
                    "content": "Reserve 3 male growers until Friday.",
                },
                {
                    "id": "new-request",
                    "message_type": 0,
                    "created_at": "2026-07-28T09:00:00+00:00",
                    "content": "This is a new request. I want 1 male grower around 25 to 30 kg.",
                },
                {
                    "id": "current",
                    "message_type": 0,
                    "created_at": "2026-07-28T10:00:00Z",
                    "content": "I would collect in Riversdale. What do you need next?",
                },
            ],
        }

        prior = sam_live_stock_runtime._prior_context_from_chatwoot_history(
            history,
            {"message_id": "current"},
        )

        self.assertEqual(prior["interest"]["quantity"], 1)
        self.assertEqual(prior["interest"]["category"], "grower")
        self.assertEqual(prior["interest"]["sex"], "male")
        self.assertEqual(prior["interest"]["weight_range"], "25-30 kg")
        self.assertEqual(prior["interest"]["timing"], "")
        self.assertFalse(prior["interest"]["order_commitment"])

    def test_process_environment_mapping_reaches_llm_builder_from_inbound_handler(self):
        calls = []
        environment = {
            "SAM_LIVE_STOCK_BACKEND_LLM_ENABLED": "1",
            "SAM_LIVE_STOCK_BACKEND_LLM_MODEL": "test-model",
            "OPENAI_API_KEY": "test-secret-key-never-exposed",
        }

        with patch.dict(os.environ, environment, clear=True):
            result, status_code = sam_live_stock_runtime.handle_sam_live_stock_chatwoot_inbound(
                inbound_payload(content="I need 3 male growers around 30 kg for Friday."),
                intake_context_loader=lambda _conversation_id: {"success": True, "known_fields": {}, "items": []},
                conversation_history_loader=lambda *_args: {"success": True, "messages": []},
                availability_loader=lambda: [],
                llm_drafter=lambda context, source: calls.append((context, source)) or {
                    "reply_text": "I can help with the three male growers and will keep Friday as the requested timing.",
                    "confidence": 0.96,
                },
            )

        decision = result["sam_decision"]
        self.assertEqual(status_code, 200)
        self.assertEqual(
            decision["reply_source"],
            "contextual_sales_source_backed_owner_draft",
        )
        self.assertEqual(calls, [])
        self.assertEqual(
            decision["contextual_sales"]["status"],
            "commercial_evidence_unavailable",
        )

    def test_reviewed_llm_clarification_sends_when_routine_reply_gate_is_enabled(self):
        sends = []
        result, status_code = sam_live_stock_runtime.handle_sam_live_stock_chatwoot_inbound(
            inbound_payload(content="Hi Sam, I am looking for weaners.", conversation={"id": 2401, "inbox": {"id": 77, "channel_type": "Channel::Whatsapp"}}),
            environ={
                "SAM_LIVE_STOCK_BACKEND_AUTOREPLY_ENABLED": "1",
                "SAM_LIVE_STOCK_BACKEND_AUTOREPLY_CANARY_ENABLED": "1",
                "SAM_LIVE_STOCK_BACKEND_AUTOREPLY_CANARY_CONVERSATION_ID": "2401",
                "SAM_LIVE_STOCK_BACKEND_AUTOREPLY_CANARY_CONTACT_ID": "99",
                "SAM_LIVE_STOCK_BACKEND_AUTOREPLY_CANARY_INBOX_ID": "77",
                "SAM_LIVE_STOCK_BACKEND_LLM_ENABLED": "1",
                "SAM_LIVE_STOCK_BACKEND_LLM_MODEL": "test-model",
                "OPENAI_API_KEY": "test-key",
            },
            intake_context_loader=lambda _conversation_id: {"success": True, "known_fields": {}, "items": []},
            conversation_history_loader=lambda *_args: {"success": True, "messages": []},
            availability_loader=lambda: [],
            llm_drafter=lambda *_args: {
                "reply_text": "I can help with weaners. How many are you looking for?",
                "confidence": 0.99,
            },
            routine_delivery_claim=lambda *_args: {"success": True, "created": True, "review_event_id": "REVIEW-1"},
            chatwoot_sender=lambda conversation_id, message, _source: sends.append((conversation_id, message)) or {"status_code": 200, "body": {"id": 1, "status": "delivered"}},
            routine_delivery_evidence_recorder=lambda *_args: {"success": True, "created": True},
        )

        decision = result["sam_decision"]
        self.assertEqual(status_code, 200)
        self.assertTrue(decision["should_reply"])
        self.assertTrue(decision["conversation_review"]["safe_to_send"])
        self.assertEqual(decision["conversation_review"]["recommended_action"], "ask_one_missing_fact")
        self.assertFalse(result["sent"])
        self.assertFalse(result["sends_customer_message"])
        self.assertEqual(sends, [])
        self.assertFalse(result["creates_order"])
        self.assertFalse(result["reserves_stock"])
        self.assertFalse(result["changes_stock"])

    def test_fact_aware_fallback_never_auto_sends_even_when_gate_is_enabled(self):
        sends = []
        delivery = sam_live_stock_runtime.deliver_sam_live_stock_routine_reply_if_enabled(
            {"conversation_id": "1826", "contact_id": "99", "inbox_id": "77"},
            {
                "should_reply": True,
                "suggested_reply_text": "I can check the price and stock facts.",
                "reply_source": "deterministic_read_only_guard",
                "llm_draft": {"used": False, "status": "llm_disabled"},
            },
            {"safe_to_send": True, "escalation_required": False},
            {
                "SAM_LIVE_STOCK_BACKEND_AUTOREPLY_ENABLED": "1",
                "SAM_LIVE_STOCK_BACKEND_AUTOREPLY_CANARY_ENABLED": "1",
                "SAM_LIVE_STOCK_BACKEND_AUTOREPLY_CANARY_CONVERSATION_ID": "1826",
                "SAM_LIVE_STOCK_BACKEND_AUTOREPLY_CANARY_CONTACT_ID": "99",
                "SAM_LIVE_STOCK_BACKEND_AUTOREPLY_CANARY_INBOX_ID": "77",
            },
            chatwoot_sender=lambda *_args: sends.append(True),
        )

        self.assertEqual(delivery["status"], "routine_reply_requires_llm_draft")
        self.assertFalse(delivery["sent"])
        self.assertEqual(sends, [])

    def test_reservation_request_keeps_conversation_with_sam_but_requests_owner_authority(self):
        sends = []
        result, _status_code = sam_live_stock_runtime.handle_sam_live_stock_chatwoot_inbound(
            inbound_payload(content="Can you reserve 2 female weaners for me?", conversation={"id": 2401, "inbox": {"id": 77, "channel_type": "Channel::Whatsapp"}}),
            environ={
                "SAM_LIVE_STOCK_BACKEND_AUTOREPLY_ENABLED": "1",
                "SAM_LIVE_STOCK_BACKEND_AUTOREPLY_CANARY_ENABLED": "1",
                "SAM_LIVE_STOCK_BACKEND_AUTOREPLY_CANARY_CONVERSATION_ID": "2401",
                "SAM_LIVE_STOCK_BACKEND_AUTOREPLY_CANARY_CONTACT_ID": "99",
                "SAM_LIVE_STOCK_BACKEND_AUTOREPLY_CANARY_INBOX_ID": "77",
                "SAM_LIVE_STOCK_BACKEND_LLM_ENABLED": "1",
                "SAM_LIVE_STOCK_BACKEND_LLM_MODEL": "test-model",
                "OPENAI_API_KEY": "test-key",
            },
            intake_context_loader=lambda _conversation_id: {"success": True, "known_fields": {}, "items": []},
            conversation_history_loader=lambda *_args: {"success": True, "messages": []},
            availability_loader=lambda: [],
            llm_drafter=lambda *_args: {
                "reply_text": "I can capture the request and ask the farm to approve the exact animals before I confirm anything.",
                "confidence": 0.99,
            },
            routine_delivery_claim=lambda *_args: {"success": True, "created": True, "review_event_id": "REVIEW-2"},
            chatwoot_sender=lambda conversation_id, message, _source: sends.append((conversation_id, message)) or {"status_code": 200, "body": {"id": 2, "status": "delivered"}},
            routine_delivery_evidence_recorder=lambda *_args: {"success": True, "created": True},
        )

        decision = result["sam_decision"]
        review = decision["conversation_review"]
        self.assertFalse(review["escalation_required"])
        self.assertEqual(review["conversation_mode_recommendation"], "AUTO")
        self.assertTrue(review["owner_authority_required"])
        self.assertIn("reservation_owner_authority", review["protected_action_reasons"])
        self.assertEqual(review["recommended_action"], "owner_authority_decision")
        self.assertTrue(result["sent"])
        self.assertTrue(decision["owner_gate_required"])
        self.assertFalse(result["reserves_stock"])
        self.assertFalse(result["creates_order"])

    def test_autoreply_canary_withholds_identity_mismatch_low_confidence_and_duplicate(self):
        source = {
            "SAM_LIVE_STOCK_BACKEND_AUTOREPLY_ENABLED": "1",
            "SAM_LIVE_STOCK_BACKEND_AUTOREPLY_CANARY_ENABLED": "1",
            "SAM_LIVE_STOCK_BACKEND_AUTOREPLY_CANARY_CONVERSATION_ID": "1826",
            "SAM_LIVE_STOCK_BACKEND_AUTOREPLY_CANARY_CONTACT_ID": "99",
            "SAM_LIVE_STOCK_BACKEND_AUTOREPLY_CANARY_INBOX_ID": "77",
        }
        base_inbound = {"conversation_id": "1826", "contact_id": "99", "inbox_id": "77"}
        base_decision = {
            "should_reply": True,
            "suggested_reply_text": "How many growers do you need?",
            "reply_source": "llm_live_stock_reply_draft",
            "llm_draft": {"used": True, "confidence": 0.99},
            "sales_lane": "live_stock_sales",
            "facts": {"sales_lane": "live_stock_sales", "lane_confidence": 0.99, "message_intent": "buying_intent", "media_review_required": False},
        }
        review = {"safe_to_send": True, "escalation_required": False}
        mismatch = sam_live_stock_runtime.deliver_sam_live_stock_routine_reply_if_enabled(
            {**base_inbound, "conversation_id": "other"}, base_decision.copy(), review, source,
            delivery_claim=lambda *_args: {"success": True, "created": True}, chatwoot_sender=lambda *_args: {},
        )
        low = sam_live_stock_runtime.deliver_sam_live_stock_routine_reply_if_enabled(
            base_inbound, {**base_decision, "llm_draft": {"used": True, "confidence": 0.70}}, review, source,
            delivery_claim=lambda *_args: {"success": True, "created": True}, chatwoot_sender=lambda *_args: {},
        )
        duplicate = sam_live_stock_runtime.deliver_sam_live_stock_routine_reply_if_enabled(
            base_inbound, base_decision.copy(), review, source,
            delivery_claim=lambda *_args: {"success": True, "created": False, "review_event_id": "REVIEW-X"}, chatwoot_sender=lambda *_args: {},
        )
        self.assertEqual(mismatch["status"], "routine_reply_canary_identity_mismatch")
        self.assertEqual(low["status"], "routine_reply_llm_confidence_blocked")
        self.assertEqual(duplicate["status"], "routine_reply_duplicate_withheld")
        self.assertFalse(mismatch["canary"]["contains_identity_values"])

    def test_llm_context_includes_real_chatwoot_history_messages(self):
        calls = []

        result, _status_code = sam_live_stock_runtime.handle_sam_live_stock_chatwoot_inbound(
            inbound_payload(id=44, content="Do you have two females left?"),
            environ={
                "SAM_LIVE_STOCK_BACKEND_LLM_ENABLED": "1",
                "SAM_LIVE_STOCK_BACKEND_LLM_MODEL": "test-model",
                "OPENAI_API_KEY": "test-key",
            },
            intake_context_loader=lambda _conversation_id: {"success": True, "known_fields": {}, "items": []},
            conversation_history_loader=lambda _conversation_id, _source: {
                "success": True,
                "messages": [
                    {"id": "1", "message_type": 0, "content": "I need two weaners near Riversdale.", "created_at": "2026-07-08T08:00:00Z"},
                    {"id": "2", "message_type": 1, "content": "I can check the current weaner list.", "created_at": "2026-07-08T08:01:00Z"},
                    {"id": "3", "message_type": 2, "content": "Conversation was resolved", "created_at": "2026-07-08T08:01:30Z"},
                    {"id": "44", "message_type": 0, "content": "Do you have two females left?", "created_at": "2026-07-08T08:02:00Z"},
                ],
            },
            availability_loader=lambda: [],
            llm_drafter=lambda context, source: calls.append((context, source)) or {
                "reply_text": "I can check the current female weaner list before anything is promised.",
                "confidence": 0.86,
            },
        )

        self.assertEqual(
            result["sam_decision"]["reply_source"],
            "contextual_sales_source_backed_owner_draft",
        )
        self.assertEqual(calls, [])
        self.assertEqual(result["sam_decision"]["read_context"]["chatwoot_history"]["message_count"], 4)

    def test_llm_context_includes_owner_correction_examples_by_default(self):
        calls = []
        owner_example_calls = []

        def owner_example_loader(conversation_id="", limit=3, customer_message=""):
            owner_example_calls.append({
                "conversation_id": conversation_id,
                "limit": limit,
                "customer_message": customer_message,
            })
            return {
                "success": True,
                "examples": [{
                    "customer_message_excerpt": "Location",
                    "rejected_sam_draft": "Are you looking for live pigs, pork, or slaughter?",
                    "owner_reply_excerpt": "We are near Riversdale in the Western Cape. Collection is arranged with the farm first.",
                    "classification": "owner_replaced",
                    "example_relevance_score": 1.0,
                }],
            }, 200

        result, _status_code = sam_live_stock_runtime.handle_sam_live_stock_chatwoot_inbound(
            inbound_payload(content="How much for 1 piglet?"),
            environ={
                "SAM_LIVE_STOCK_BACKEND_LLM_ENABLED": "1",
                "SAM_LIVE_STOCK_BACKEND_LLM_MODEL": "test-model",
                "OPENAI_API_KEY": "test-key",
            },
            intake_context_loader=lambda _conversation_id: {"success": True, "known_fields": {}, "items": []},
            conversation_history_loader=lambda _conversation_id, _source: {"success": True, "messages": []},
            availability_loader=lambda: [],
            owner_example_loader=owner_example_loader,
            llm_drafter=lambda context, source: calls.append((context, source)) or {
                "reply_text": "We are near Riversdale in the Western Cape. I can check the current live-pig list before anything is promised.",
                "confidence": 0.86,
            },
        )

        self.assertEqual(
            result["sam_decision"]["reply_source"],
            "deterministic_customer_size_guidance",
        )
        self.assertEqual(calls, [])
        self.assertIn(
            "Which size would suit you",
            result["sam_decision"]["suggested_reply_text"],
        )
        self.assertEqual(
            result["sam_decision"]["contextual_sales"]["status"],
            "commercial_evidence_unavailable",
        )
        self.assertEqual(owner_example_calls[0]["customer_message"], "How much for 1 piglet?")

    def test_llm_payload_long_history_remains_valid_json_with_rules(self):
        context = {
            "rules": ["Use only supplied stock facts.", "Ask one useful question."],
            "inbound": {"message": "I need pigs." * 200},
            "recent_chatwoot_history": [
                {"speaker": "customer", "content": f"message {idx} " + ("x" * 500)}
                for idx in range(10)
            ],
            "match_packet": {"matched_sample": [{"pig_id": f"W-{idx}", "current_weight_kg": 12 + idx} for idx in range(10)]},
            "fallback_reply": "fallback " * 300,
        }

        payload = sam_live_stock_runtime._llm_reply_payload(
            context,
            {"SAM_LIVE_STOCK_BACKEND_LLM_MODEL": "test-model"},
        )
        user_content = payload["messages"][1]["content"]
        parsed = json.loads(user_content)

        self.assertLessEqual(len(user_content), 8000)
        self.assertEqual(parsed["rules"][0], "Use only supplied stock facts.")
        self.assertIn("recent_chatwoot_history", parsed)

    def test_unsafe_llm_reply_falls_back_before_review_is_attached(self):
        result, _status_code = sam_live_stock_runtime.handle_sam_live_stock_chatwoot_inbound(
            inbound_payload(),
            environ={
                "SAM_LIVE_STOCK_BACKEND_LLM_ENABLED": "1",
                "SAM_LIVE_STOCK_BACKEND_LLM_MODEL": "test-model",
                "OPENAI_API_KEY": "test-key",
            },
            intake_context_loader=lambda _conversation_id: {"success": True, "known_fields": {}, "items": []},
            conversation_history_loader=lambda _conversation_id, _source: {"success": True, "messages": []},
            availability_loader=lambda: [],
            llm_drafter=lambda _context, _source: {
                "reply_text": "Yes, they are available and I have reserved them for you. Payment is confirmed.",
                "confidence": 0.99,
            },
        )

        decision = result["sam_decision"]
        self.assertEqual(
            decision["reply_source"],
            "contextual_sales_source_backed_owner_draft",
        )
        self.assertFalse(decision["llm_draft"]["used"])
        self.assertNotIn("reserved them", decision["suggested_reply_text"])
        self.assertFalse(result["sent"])

    def test_scanner_does_not_hard_block_plain_available(self):
        decision = {
            "sales_lane": "live_stock_sales",
            "reply_source": "llm_live_stock_reply_draft",
            "suggested_reply_text": "I can check if the 3 piglets are available for Friday collection before we finalise anything.",
            "missing_fields": [],
            "blockers": [],
        }

        review = sam_live_stock_runtime.review_sam_live_stock_conversation(
            {"content": "Can I come Friday?"},
            {"category": "Piglet", "quantity": 3, "timing": "friday"},
            decision,
        )

        self.assertNotIn("unsafe_sales_or_discount_language", review["blocked_reasons"])
        self.assertFalse(sam_live_stock_runtime._llm_reply_needs_fallback(decision, review))

    def test_scanner_still_blocks_reservation_payment_sales_and_location(self):
        cases = [
            ("They are reserved for you.", "implies_reservation"),
            ("Payment is confirmed.", "confirms_payment"),
            ("These pigs are for sale now.", "unsafe_sales_or_discount_language"),
            ("I can send our location.", "shares_or_invites_exact_location"),
        ]

        for reply, expected in cases:
            with self.subTest(reply=reply):
                review = sam_live_stock_runtime.review_sam_live_stock_conversation(
                    {"content": "Can I take them?"},
                    {"category": "Piglet", "quantity": 3},
                    {
                        "sales_lane": "live_stock_sales",
                        "suggested_reply_text": reply,
                        "missing_fields": [],
                        "blockers": [],
                    },
                )

                self.assertIn(expected, review["blocked_reasons"])

    def test_safe_reply_draft_is_fact_aware_when_nothing_missing(self):
        facts = {
            "customer_name": "michaels",
            "quantity": 3,
            "category": "Piglet",
            "weight_range": "7_to_9_Kg",
            "sex": "Any",
            "timing": "friday",
            "location": "Albertinia",
        }
        packet = {
            "can_answer_price": True,
            "requested_quantity": 3,
            "requested_category": "Piglet",
            "requested_weight_range": "7_to_9_Kg",
            "requested_sex": "Any",
            "unit_price": 450,
            "estimated_total": 1350,
        }

        reply = sam_live_stock_runtime._safe_reply_draft(
            facts,
            {"lane": "live_stock_sales"},
            missing=[],
            availability={"success": True, "matched_count": 11},
            blockers=[],
            price_answer_packet=packet,
        )

        self.assertNotEqual(reply, "I have the main live-pig details. I will check the current list before anything is promised.")
        self.assertIn("Michaels", reply)
        self.assertIn("Friday", reply)
        self.assertIn("3 piglets", reply)
        self.assertIn("7-9 kg", reply)
        self.assertIn("R450", reply)
        self.assertIn("R1,350", reply)
        lowered = reply.lower()
        for forbidden in ("reserved", "held", "booked", "available", "delivery", "transport", "payment confirmed"):
            self.assertNotIn(forbidden, lowered)

    def test_llm_failure_falls_back_to_deterministic_reply(self):
        result, _status_code = sam_live_stock_runtime.handle_sam_live_stock_chatwoot_inbound(
            inbound_payload(),
            environ={
                "SAM_LIVE_STOCK_BACKEND_LLM_ENABLED": "1",
                "SAM_LIVE_STOCK_BACKEND_LLM_MODEL": "test-model",
                "OPENAI_API_KEY": "test-key",
            },
            intake_context_loader=lambda _conversation_id: {"success": True, "known_fields": {}, "items": []},
            conversation_history_loader=lambda _conversation_id, _source: {"success": True, "messages": []},
            availability_loader=lambda: [],
            llm_drafter=lambda _context, _source: {"_llm_error": {"kind": "request_error"}},
        )

        decision = result["sam_decision"]
        self.assertEqual(
            decision["reply_source"],
            "contextual_sales_source_backed_owner_draft",
        )
        self.assertFalse(decision["llm_draft"]["used"])
        self.assertEqual(
            decision["llm_draft"]["status"],
            "commercial_general_information_fallback_blocked",
        )
        self.assertFalse(result["sent"])

    def test_render_llm_timeout_caps_at_fifteen_seconds(self):
        self.assertEqual(sam_live_stock_runtime._timeout({"RENDER": "1"}), 12)
        self.assertEqual(
            sam_live_stock_runtime._timeout({
                "RENDER": "1",
                "SAM_LIVE_STOCK_BACKEND_LLM_TIMEOUT_SECONDS": "30",
            }),
            15,
        )

    def test_availability_summary_filters_unsafe_and_matches_category_sex(self):
        rows = [
            exact_eligible_row(pig_id="PIG-1"),
            {
                "pig_id": "PIG-2",
                "sex": "Male",
                "status": "Active",
                "on_farm": "Yes",
                "reserved_status": "Reserved",
                "available_for_sale": "Yes",
                "sale_category": "Weaner",
            },
            {
                "pig_id": "PIG-3",
                "sex": "Female",
                "status": "Sold",
                "on_farm": "No",
                "available_for_sale": "No",
                "sale_category": "Weaner",
            },
        ]

        summary = sam_live_stock_runtime.summarize_live_stock_availability(rows, {"category": "weaner", "sex": "female"})

        self.assertTrue(summary["success"])
        self.assertEqual(summary["total_available_count"], 1)
        self.assertEqual(summary["matched_count"], 1)
        self.assertEqual(summary["matched_sample"][0]["pig_id"], "PIG-1")

    def test_availability_summary_respects_requested_weight_range(self):
        rows = [
            exact_eligible_row(pig_id="PIG-10KG", sale_category="Weaner Piglets", weight_band="10_to_14_Kg"),
            exact_eligible_row(pig_id="PIG-44KG", sale_category="Grower Pigs", weight_band="40_to_44_Kg", current_weight_kg=44, calculated_stage="Grower"),
        ]

        summary = sam_live_stock_runtime.summarize_live_stock_availability(
            rows,
            {"category": "weaner", "sex": "female", "weight_range": "10-15 kg"},
        )

        self.assertEqual(summary["matched_count"], 1)
        self.assertEqual(summary["matched_sample"][0]["pig_id"], "PIG-10KG")

    def test_exact_animal_preselection_ranks_evidence_and_keeps_proposals_read_only(self):
        rows = [
            {**exact_eligible_row(),
                "pig_id": "PIG-29", "tag_number": "29", "sex": "Male", "status": "Active", "on_farm": "Yes",
                "purpose": "Sale", "available_for_sale": "Yes", "live_stock_sale_eligible": True,
                "sale_category": "Grower", "current_weight_kg": 29, "latest_weight_date": "2026-07-23",
                "days_since_weight": 1, "current_pen_id": "PEN-G1", "health_status": "Clear",
                "medical_status": "Clear", "withdrawal_clear": "Yes", "live_stock_sale_reason": "eligible",
            },
            {**exact_eligible_row(),
                "pig_id": "PIG-27", "tag_number": "27", "sex": "Male", "status": "Active", "on_farm": "Yes",
                "purpose": "Sale", "available_for_sale": "Yes", "live_stock_sale_eligible": True,
                "sale_category": "Grower", "current_weight_kg": 27, "latest_weight_date": "2026-07-24",
                "days_since_weight": 0, "current_pen_id": "PEN-G1", "health_status": "Clear",
                "medical_status": "Clear", "withdrawal_clear": "Yes", "live_stock_sale_reason": "eligible",
            },
            {
                "pig_id": "PIG-28-HELD", "sex": "Male", "status": "Active", "on_farm": "Yes", "purpose": "Sale",
                "available_for_sale": "No", "live_stock_sale_eligible": False, "current_weight_kg": 28,
                "latest_weight_date": "2026-07-24", "reserved_status": "Allocated", "reserved_for_order_id": "ORD-X",
                "live_stock_sale_reason": "Pig is already reserved or linked to an order.",
            },
        ]
        facts = {"quantity": 2, "category": "grower", "sex": "male", "weight_range": "25-29 kg"}
        availability = sam_live_stock_runtime.summarize_live_stock_availability(rows, facts)
        match = sam_live_stock_runtime.build_live_stock_match_packet(facts, availability)
        draft = sam_live_stock_runtime.build_live_stock_draft_order_packet(
            {"conversation_id": "proof", "customer_name": "Sanitized", "channel": "chatwoot"}, facts, match,
        )
        price = sam_live_stock_runtime.build_live_stock_price_answer_packet(facts, match)
        owner = sam_live_stock_runtime.build_live_stock_prepared_owner_action_bundle(
            {"conversation_id": "proof"}, facts, {}, draft, price, match,
        )
        self.assertEqual(match["selected_pig_ids"], ["PIG-27", "PIG-29"])
        self.assertEqual(match["excluded_count"], 1)
        self.assertEqual(match["excluded_sample"][0]["reserved_for_order_id"], "ORD-X")
        self.assertEqual(match["matched_sample"][0]["latest_weight_date"], "2026-07-24")
        self.assertEqual(match["matched_sample"][0]["current_pen_id"], "PEN-G1")
        self.assertEqual([line["pig_id"] for line in draft["proposed_order_lines"]], ["PIG-27", "PIG-29"])
        self.assertTrue(all(line["proposal_only"] for line in draft["proposed_order_lines"]))
        self.assertFalse(draft["exact_animal_assignment_written"])
        self.assertNotIn("pig_id", draft["sync_payload"]["requested_items"][0])
        self.assertEqual(owner["stock_preselection"]["selected_pig_ids"], ["PIG-27", "PIG-29"])
        self.assertEqual(owner["stock_preselection"]["excluded"][0]["reserved_for_order_id"], "ORD-X")
        self.assertFalse(owner["stock_preselection"]["exact_animal_assignment_written"])

    def test_handle_inbound_builds_read_only_decision_without_writes_or_sends(self):
        def intake_loader(_conversation_id):
            return {
                "success": True,
                "lookup_status": "no_match",
                "known_fields": {},
                "items": [],
            }

        def availability_loader():
            return [
                {**exact_eligible_row(),
                    "pig_id": "PIG-1",
                    "sex": "Female",
                    "status": "Active",
                    "on_farm": "Yes",
                    "available_for_sale": "Yes",
                    "purpose": "Sale",
                    "sale_category": "Weaner",
                    "current_weight_kg": 12,
                }
            ]

        result, status_code = sam_live_stock_runtime.handle_sam_live_stock_chatwoot_inbound(
            inbound_payload(),
            environ={},
            intake_context_loader=intake_loader,
            availability_loader=availability_loader,
        )

        self.assertEqual(status_code, 200)
        self.assertTrue(result["processed"])
        self.assertFalse(result["sent"])
        self.assertFalse(result["creates_order"])
        self.assertFalse(result["reserves_stock"])
        self.assertFalse(result["writes_order_intake"])
        decision = result["sam_decision"]
        self.assertEqual(decision["sales_lane"], "live_stock_sales")
        self.assertEqual(decision["availability"]["matched_count"], 1)
        self.assertFalse(decision["customer_send_allowed"])
        self.assertFalse(decision["writes_allowed"])

    def test_build_live_stock_intake_payload_normalizes_to_backend_contract(self):
        inbound = sam_live_stock_runtime.parse_chatwoot_inbound(inbound_payload())
        facts = sam_live_stock_runtime.extract_live_stock_facts(inbound["content"], inbound)
        decision = {"missing_fields": []}

        payload = sam_live_stock_runtime.build_live_stock_intake_payload(inbound, facts, decision)
        validation = sam_live_stock_runtime.validate_live_stock_intake_payload(payload)

        self.assertTrue(validation["is_valid"], validation)
        self.assertEqual(payload["conversation_id"], "2401")
        self.assertEqual(payload["patch"]["collection_location"], "Riversdale")
        self.assertEqual(payload["patch"]["collection_time_text"], "next week")
        self.assertEqual(payload["items"][0]["item_key"], "live_stock_primary")
        self.assertEqual(payload["items"][0]["quantity"], 3)
        self.assertEqual(payload["items"][0]["category"], "Weaner")
        self.assertEqual(payload["items"][0]["weight_range"], "10_to_14_Kg")
        self.assertEqual(payload["items"][0]["sex"], "Female")

    def test_new_request_intake_payload_explicitly_clears_stale_context_fields(self):
        inbound = sam_live_stock_runtime.parse_chatwoot_inbound(
            inbound_payload(
                content="This is a new request. I need 1 male grower around 25 to 30 kg. What is the price?"
            )
        )
        facts = sam_live_stock_runtime.extract_live_stock_facts(inbound["content"], inbound)

        payload = sam_live_stock_runtime.build_live_stock_intake_payload(inbound, facts, {})
        validation = sam_live_stock_runtime.validate_live_stock_intake_payload(payload)

        self.assertTrue(validation["is_valid"], validation)
        self.assertTrue(payload["reset_request_context"])
        self.assertTrue(validation["cleaned_data"]["reset_request_context"])
        self.assertEqual(payload["patch"]["collection_location"], "")
        self.assertEqual(payload["patch"]["collection_time_text"], "")
        self.assertEqual(payload["patch"]["collection_date"], "")
        self.assertEqual(payload["patch"]["collection_time"], "")
        self.assertEqual(payload["patch"]["payment_method"], "")
        self.assertFalse(payload["patch"]["order_commitment"])

    def test_intake_write_is_disabled_by_default(self):
        inbound = sam_live_stock_runtime.parse_chatwoot_inbound(inbound_payload())
        facts = sam_live_stock_runtime.extract_live_stock_facts(inbound["content"], inbound)
        decision = {"sales_lane": "live_stock_sales", "missing_fields": []}
        calls = []

        result = sam_live_stock_runtime.write_live_stock_intake_if_enabled(
            inbound,
            facts,
            decision,
            environ={},
            intake_writer=lambda cleaned: calls.append(cleaned),
        )

        self.assertFalse(result["attempted"])
        self.assertEqual(result["status"], "sam_live_stock_intake_write_disabled")
        self.assertEqual(calls, [])

    def test_intake_write_enabled_uses_backend_service_cleaned_payload_only(self):
        inbound = sam_live_stock_runtime.parse_chatwoot_inbound(inbound_payload())
        facts = sam_live_stock_runtime.extract_live_stock_facts(inbound["content"], inbound)
        decision = {"sales_lane": "live_stock_sales", "missing_fields": []}
        calls = []

        def writer(cleaned):
            calls.append(cleaned)
            return {
                "success": True,
                "lookup_status": "updated",
                "intake_id": "INTAKE-1",
                "items": [{"item_key": "live_stock_primary"}],
            }

        result = sam_live_stock_runtime.write_live_stock_intake_if_enabled(
            inbound,
            facts,
            decision,
            environ={"SAM_LIVE_STOCK_BACKEND_INTAKE_WRITE_ENABLED": "1"},
            intake_writer=writer,
        )

        self.assertTrue(result["attempted"])
        self.assertTrue(result["success"])
        self.assertEqual(result["status"], "sam_live_stock_intake_written")
        self.assertEqual(len(calls), 1)
        cleaned = calls[0]
        self.assertEqual(cleaned["conversation_id"], "2401")
        self.assertEqual(cleaned["patch"]["collection_location"], "Riversdale")
        self.assertEqual(cleaned["items"][0]["category"], "Weaner")
        self.assertEqual(cleaned["items"][0]["weight_range"], "10_to_14_Kg")
        self.assertEqual(cleaned["items"][0]["sex"], "Female")

    @patch(
        "modules.sales.sam_live_stock_runtime.load_current_level1_control",
        return_value=({"status": "level1_control_not_configured", "event": {}}, 200),
    )
    def test_handle_inbound_with_intake_write_enabled_reports_intake_write_only(self, _control):
        writes = []

        def writer(cleaned):
            writes.append(cleaned)
            return {"success": True, "intake_id": "INTAKE-1", "items": []}

        result, status_code = sam_live_stock_runtime.handle_sam_live_stock_chatwoot_inbound(
            inbound_payload(),
            environ={"SAM_LIVE_STOCK_BACKEND_INTAKE_WRITE_ENABLED": "1"},
            intake_context_loader=lambda _conversation_id: {"success": True, "known_fields": {}, "items": []},
            availability_loader=lambda: [],
            intake_writer=writer,
        )

        self.assertEqual(status_code, 200)
        self.assertTrue(result["writes_order_intake"])
        self.assertFalse(result["creates_order"])
        self.assertFalse(result["reserves_stock"])
        self.assertFalse(result["writes_sales_transaction"])
        self.assertFalse(result["sends_customer_message"])
        self.assertEqual(len(writes), 1)
        self.assertEqual(result["sam_decision"]["intake_write"]["status"], "sam_live_stock_intake_written")

    @patch(
        "modules.sales.sam_live_stock_runtime.load_current_level1_control",
        return_value=({"status": "level1_control_not_configured", "event": {}}, 200),
    )
    def test_intake_write_preserves_prior_quote_request_on_followup(self, _control):
        writes = []

        def writer(cleaned):
            writes.append(cleaned)
            return {"success": True, "intake_id": "INTAKE-1", "items": []}

        result, status_code = sam_live_stock_runtime.handle_sam_live_stock_chatwoot_inbound(
            inbound_payload(content="Can you keep them for me until Friday?"),
            environ={"SAM_LIVE_STOCK_BACKEND_INTAKE_WRITE_ENABLED": "1"},
            intake_context_loader=lambda _conversation_id: {
                "success": True,
                "known_fields": {
                    "collection_location": "Riversdale",
                    "quote_requested": True,
                    "order_commitment": False,
                },
                "items": [{
                    "quantity": 2,
                    "category": "Weaner",
                    "weight_range": "10_to_14_Kg",
                    "sex": "Female",
                    "status": "active",
                }],
            },
            availability_loader=lambda: [],
            intake_writer=writer,
        )

        self.assertEqual(status_code, 200)
        self.assertTrue(result["writes_order_intake"])
        self.assertEqual(len(writes), 1)
        self.assertTrue(writes[0]["patch"]["quote_requested"])
        self.assertNotIn("order_commitment", writes[0]["patch"])

    def test_price_followup_drafts_readable_estimate_without_quote_or_reservation(self):
        def intake_loader(_conversation_id):
            return {
                "success": True,
                "known_fields": {
                    "collection_location": "Riversdale",
                    "quote_requested": False,
                    "order_commitment": False,
                },
                "items": [{
                    "quantity": 2,
                    "category": "Weaner",
                    "weight_range": "10_to_14_Kg",
                    "sex": "Female",
                    "status": "active",
                }],
            }

        with patch.object(
            sam_live_stock_runtime,
            "resolve_live_stock_price_rule",
            return_value={
                "found": True,
                "status": "ok",
                "sale_category": "Weaner Piglets",
                "weight_band": "10_to_14_Kg",
                "unit_price": 500,
                "currency": "ZAR",
                "source": "test",
            },
        ):
            result, status_code = sam_live_stock_runtime.handle_sam_live_stock_chatwoot_inbound(
                inbound_payload(content="What is the price for them?"),
                intake_context_loader=intake_loader,
                availability_loader=lambda: [],
            )

        decision = result["sam_decision"]
        reply = decision["suggested_reply_text"]

        self.assertEqual(status_code, 200)
        self.assertEqual(decision["sales_lane"], "live_stock_sales")
        self.assertTrue(decision["facts"]["quote_requested"])
        self.assertTrue(decision["price_answer_packet"]["can_answer_price"])
        self.assertFalse(decision["price_answer_packet"]["formal_quote_created"])
        self.assertFalse(decision["price_answer_packet"]["reservation_created"])
        self.assertIn("Current price estimate:", reply)
        self.assertIn("- 2 x Female Weaner, 10-14 kg: R500 each", reply)
        self.assertIn("- Estimated total: R1,000", reply)
        self.assertIn("- This is not a reservation.", reply)
        self.assertFalse(decision["sends_customer_message"])
        self.assertFalse(decision["creates_order"])
        self.assertFalse(decision["reserves_stock"])

    def test_intake_write_blocks_wrong_lane_and_breeding_stock(self):
        inbound = sam_live_stock_runtime.parse_chatwoot_inbound(inbound_payload(content="I want pork chops."))
        facts = sam_live_stock_runtime.extract_live_stock_facts(inbound["content"], inbound)
        calls = []

        wrong_lane = sam_live_stock_runtime.write_live_stock_intake_if_enabled(
            inbound,
            facts,
            {"sales_lane": "meat_sales"},
            environ={"SAM_LIVE_STOCK_BACKEND_INTAKE_WRITE_ENABLED": "1"},
            intake_writer=lambda cleaned: calls.append(cleaned),
        )

        self.assertFalse(wrong_lane["attempted"])
        self.assertEqual(wrong_lane["status"], "sam_live_stock_intake_wrong_lane")

        breeding_facts = sam_live_stock_runtime.extract_live_stock_facts("I want two breeding gilts", inbound)
        breeding = sam_live_stock_runtime.write_live_stock_intake_if_enabled(
            inbound,
            breeding_facts,
            {"sales_lane": "live_stock_sales"},
            environ={"SAM_LIVE_STOCK_BACKEND_INTAKE_WRITE_ENABLED": "1"},
            intake_writer=lambda cleaned: calls.append(cleaned),
        )

        self.assertFalse(breeding["attempted"])
        self.assertEqual(breeding["status"], "sam_live_stock_intake_owner_gate_breeding")
        self.assertEqual(calls, [])

    def test_match_and_draft_order_packet_are_owner_reviewable(self):
        inbound = sam_live_stock_runtime.parse_chatwoot_inbound(inbound_payload())
        facts = sam_live_stock_runtime.extract_live_stock_facts(inbound["content"], inbound)
        availability = sam_live_stock_runtime.summarize_live_stock_availability(
            [
                exact_eligible_row(pig_id="PIG-1", current_weight_kg=12),
                exact_eligible_row(pig_id="PIG-2", current_weight_kg=13),
                exact_eligible_row(pig_id="PIG-3", current_weight_kg=14),
            ],
            facts,
        )

        match = sam_live_stock_runtime.build_live_stock_match_packet(facts, availability)
        packet = sam_live_stock_runtime.build_live_stock_draft_order_packet(inbound, facts, match)

        self.assertEqual(match["match_status"], "exact_match_available")
        self.assertTrue(match["complete_fulfillment"])
        self.assertTrue(packet["draft_ready"], packet)
        self.assertTrue(packet["owner_review_required"])
        self.assertEqual(packet["order_payload"]["requested_category"], "Weaner")
        self.assertEqual(packet["order_payload"]["order_stream"], "Livestock")
        self.assertEqual(packet["order_payload"]["requested_weight_range"], "10_to_14_Kg")
        self.assertEqual(packet["order_payload"]["quoted_total"], 1500.0)
        self.assertTrue(packet["pricing"]["found"], packet["pricing"])
        self.assertEqual(packet["pricing"]["sale_category"], "Weaner Piglets")
        self.assertEqual(packet["pricing"]["unit_price"], 500.0)
        self.assertEqual(packet["sync_payload"]["requested_items"][0]["request_item_key"], "live_stock_primary")
        self.assertEqual(packet["sync_payload"]["requested_items"][0]["quantity"], 3)

    def test_draft_order_creation_is_disabled_by_default(self):
        inbound = sam_live_stock_runtime.parse_chatwoot_inbound(inbound_payload())
        facts = sam_live_stock_runtime.extract_live_stock_facts(inbound["content"], inbound)
        calls = []

        result = sam_live_stock_runtime.create_live_stock_draft_order_if_enabled(
            inbound,
            facts,
            {"sales_lane": "live_stock_sales"},
            environ={},
            draft_order_creator=lambda order_data, sync_data: calls.append((order_data, sync_data)),
        )

        self.assertFalse(result["attempted"])
        self.assertEqual(result["status"], "sam_live_stock_draft_order_create_disabled")
        self.assertEqual(calls, [])

    def test_draft_order_creation_enabled_uses_existing_create_with_lines_contract(self):
        inbound = sam_live_stock_runtime.parse_chatwoot_inbound(inbound_payload())
        facts = sam_live_stock_runtime.extract_live_stock_facts(inbound["content"], inbound)
        availability = sam_live_stock_runtime.summarize_live_stock_availability(
            [
                exact_eligible_row(pig_id="PIG-1"),
                exact_eligible_row(pig_id="PIG-2"),
                exact_eligible_row(pig_id="PIG-3"),
            ],
            facts,
        )
        match = sam_live_stock_runtime.build_live_stock_match_packet(facts, availability)
        packet = sam_live_stock_runtime.build_live_stock_draft_order_packet(inbound, facts, match)
        calls = []

        def creator(order_data, sync_data):
            calls.append((order_data, sync_data))
            return {
                "success": True,
                "action": "create_order_with_lines",
                "order_id": "ORD-1",
                "complete_fulfillment": True,
            }

        result = sam_live_stock_runtime.create_live_stock_draft_order_if_enabled(
            inbound,
            facts,
            {"sales_lane": "live_stock_sales", "draft_order_packet": packet, "match_packet": match},
            environ={"SAM_LIVE_STOCK_BACKEND_DRAFT_ORDER_CREATE_ENABLED": "1"},
            draft_order_creator=creator,
        )

        self.assertTrue(result["attempted"])
        self.assertTrue(result["success"])
        self.assertEqual(result["status"], "sam_live_stock_draft_order_created")
        self.assertEqual(len(calls), 1)
        order_data, sync_data = calls[0]
        self.assertEqual(order_data["customer_name"], "Charl N")
        self.assertEqual(order_data["requested_category"], "Weaner")
        self.assertEqual(sync_data["requested_items"][0]["category"], "Weaner")
        self.assertEqual(sync_data["requested_items"][0]["quantity"], 3)

    def test_existing_draft_order_reuses_sync_contract_without_create(self):
        inbound = sam_live_stock_runtime.parse_chatwoot_inbound(inbound_payload())
        facts = sam_live_stock_runtime.extract_live_stock_facts(inbound["content"], inbound)
        availability = sam_live_stock_runtime.summarize_live_stock_availability(
            [
                exact_eligible_row(pig_id="PIG-1"),
                exact_eligible_row(pig_id="PIG-2"),
                exact_eligible_row(pig_id="PIG-3"),
            ],
            facts,
        )
        match = sam_live_stock_runtime.build_live_stock_match_packet(facts, availability)
        packet = sam_live_stock_runtime.build_live_stock_draft_order_packet(inbound, facts, match)
        creates = []
        syncs = []

        result = sam_live_stock_runtime.create_live_stock_draft_order_if_enabled(
            inbound,
            facts,
            {
                "sales_lane": "live_stock_sales",
                "draft_order_packet": packet,
                "match_packet": match,
                "conversation_plan": {"order_state": {"draft_order_id": "ORD-EXISTING-2"}},
            },
            environ={"SAM_LIVE_STOCK_BACKEND_DRAFT_ORDER_CREATE_ENABLED": "1"},
            draft_order_creator=lambda order_data, sync_data: creates.append((order_data, sync_data)),
            draft_order_syncer=lambda order_id, sync_data: syncs.append((order_id, sync_data)) or {
                "success": True,
                "order_id": order_id,
                "complete_fulfillment": True,
                "partial_fulfillment": False,
                "results": [],
            },
        )

        self.assertTrue(result["attempted"])
        self.assertTrue(result["success"])
        self.assertEqual(result["status"], "sam_live_stock_draft_order_synced")
        self.assertEqual(result["reused_draft_order_id"], "ORD-EXISTING-2")
        self.assertFalse(result["created_order"])
        self.assertEqual(creates, [])
        self.assertEqual(len(syncs), 1)
        self.assertEqual(syncs[0][0], "ORD-EXISTING-2")
        self.assertEqual(syncs[0][1]["requested_items"][0]["request_item_key"], "live_stock_primary")

    def test_existing_draft_order_partial_sync_is_stale_state_failure(self):
        inbound = sam_live_stock_runtime.parse_chatwoot_inbound(inbound_payload())
        facts = sam_live_stock_runtime.extract_live_stock_facts(inbound["content"], inbound)
        availability = sam_live_stock_runtime.summarize_live_stock_availability(
            [
                exact_eligible_row(pig_id="PIG-1"),
                exact_eligible_row(pig_id="PIG-2"),
                exact_eligible_row(pig_id="PIG-3"),
            ],
            facts,
        )
        match = sam_live_stock_runtime.build_live_stock_match_packet(facts, availability)
        packet = sam_live_stock_runtime.build_live_stock_draft_order_packet(inbound, facts, match)
        creates = []
        syncs = []

        result = sam_live_stock_runtime.create_live_stock_draft_order_if_enabled(
            inbound,
            facts,
            {
                "sales_lane": "live_stock_sales",
                "draft_order_packet": packet,
                "match_packet": match,
                "conversation_plan": {"order_state": {"draft_order_id": "ORD-EXISTING-PARTIAL"}},
            },
            environ={"SAM_LIVE_STOCK_BACKEND_DRAFT_ORDER_CREATE_ENABLED": "1"},
            draft_order_creator=lambda order_data, sync_data: creates.append((order_data, sync_data)),
            draft_order_syncer=lambda order_id, sync_data: syncs.append((order_id, sync_data)) or {
                "success": True,
                "order_id": order_id,
                "complete_fulfillment": False,
                "partial_fulfillment": True,
                "results": [{"request_item_key": "live_stock_primary", "match_status": "partial_match"}],
            },
        )

        self.assertTrue(result["attempted"])
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "sam_live_stock_draft_order_sync_stale_stock")
        self.assertEqual(result["reused_draft_order_id"], "ORD-EXISTING-PARTIAL")
        self.assertFalse(result["created_order"])
        self.assertEqual(creates, [])
        self.assertEqual(len(syncs), 1)
        self.assertTrue(result["result"]["partial_fulfillment"])
        self.assertFalse(result["result"]["complete_fulfillment"])

    def test_draft_order_not_ready_when_stock_does_not_match(self):
        inbound = sam_live_stock_runtime.parse_chatwoot_inbound(inbound_payload())
        facts = sam_live_stock_runtime.extract_live_stock_facts(inbound["content"], inbound)
        match = sam_live_stock_runtime.build_live_stock_match_packet(
            facts,
            {"success": True, "matched_count": 0, "matched_sample": []},
        )
        packet = sam_live_stock_runtime.build_live_stock_draft_order_packet(inbound, facts, match)
        calls = []

        result = sam_live_stock_runtime.create_live_stock_draft_order_if_enabled(
            inbound,
            facts,
            {"sales_lane": "live_stock_sales", "draft_order_packet": packet, "match_packet": match},
            environ={"SAM_LIVE_STOCK_BACKEND_DRAFT_ORDER_CREATE_ENABLED": "1"},
            draft_order_creator=lambda order_data, sync_data: calls.append((order_data, sync_data)),
        )

        self.assertFalse(packet["draft_ready"])
        self.assertTrue(result["attempted"])
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "sam_live_stock_draft_order_not_ready")
        self.assertEqual(calls, [])

    def test_existing_draft_order_revalidates_stale_stock_before_sync(self):
        inbound = sam_live_stock_runtime.parse_chatwoot_inbound(inbound_payload(
            content="I need 3 female weaners around 10 to 15kg next week in Riversdale.",
        ))
        facts = sam_live_stock_runtime.extract_live_stock_facts(inbound["content"], inbound)
        availability = sam_live_stock_runtime.summarize_live_stock_availability(
            [
                exact_eligible_row(pig_id="PIG-1"),
                exact_eligible_row(pig_id="PIG-2"),
            ],
            facts,
        )
        match = sam_live_stock_runtime.build_live_stock_match_packet(facts, availability)
        packet = sam_live_stock_runtime.build_live_stock_draft_order_packet(inbound, facts, match)
        creates = []
        syncs = []

        result = sam_live_stock_runtime.create_live_stock_draft_order_if_enabled(
            inbound,
            facts,
            {
                "sales_lane": "live_stock_sales",
                "draft_order_packet": packet,
                "match_packet": match,
                "conversation_plan": {"order_state": {"draft_order_id": "ORD-STALE-1"}},
            },
            environ={"SAM_LIVE_STOCK_BACKEND_DRAFT_ORDER_CREATE_ENABLED": "1"},
            draft_order_creator=lambda order_data, sync_data: creates.append((order_data, sync_data)),
            draft_order_syncer=lambda order_id, sync_data: syncs.append((order_id, sync_data)),
        )

        self.assertFalse(packet["draft_ready"])
        self.assertEqual(packet["stock_gate"], "partial_matching_stock")
        self.assertTrue(result["attempted"])
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "sam_live_stock_draft_order_not_ready")
        self.assertEqual(creates, [])
        self.assertEqual(syncs, [])

    def test_draft_order_not_ready_when_stock_is_only_partial_match(self):
        inbound = sam_live_stock_runtime.parse_chatwoot_inbound(inbound_payload(
            content="I need 3 female weaners around 10 to 15kg next week in Riversdale.",
        ))
        facts = sam_live_stock_runtime.extract_live_stock_facts(inbound["content"], inbound)
        availability = sam_live_stock_runtime.summarize_live_stock_availability(
            [
                exact_eligible_row(pig_id="PIG-1"),
                exact_eligible_row(pig_id="PIG-2"),
            ],
            facts,
        )
        match = sam_live_stock_runtime.build_live_stock_match_packet(facts, availability)
        packet = sam_live_stock_runtime.build_live_stock_draft_order_packet(inbound, facts, match)

        self.assertEqual(match["match_status"], "partial_match_available")
        self.assertFalse(match["complete_fulfillment"])
        self.assertTrue(match["partial_fulfillment"])
        self.assertFalse(packet["draft_ready"], packet)
        self.assertEqual(packet["stock_gate"], "partial_matching_stock")

    def test_reservation_followup_detects_keep_those_and_weekday(self):
        inbound = sam_live_stock_runtime.parse_chatwoot_inbound(inbound_payload(
            content="Can you keep those 2 weaners for me until Friday?",
        ))
        facts = sam_live_stock_runtime.extract_live_stock_facts(inbound["content"], inbound)

        self.assertEqual(facts["quantity"], 2)
        self.assertEqual(facts["category"], "weaner")
        self.assertEqual(facts["timing"], "friday")
        self.assertTrue(facts["reservation_requested"])

    def test_reservation_followup_inherits_live_stock_lane_from_active_intake(self):
        def intake_loader(_conversation_id):
            return {
                "success": True,
                "known_fields": {
                    "collection_location": "Riversdale",
                    "collection_time_text": "",
                    "payment_method": "",
                },
                "items": [{
                    "quantity": 2,
                    "category": "Weaner",
                    "weight_range": "10_to_14_Kg",
                    "sex": "Female",
                    "status": "active",
                }],
            }

        result, _status_code = sam_live_stock_runtime.handle_sam_live_stock_chatwoot_inbound(
            inbound_payload(content="Can you keep them for me until Friday?"),
            intake_context_loader=intake_loader,
            availability_loader=lambda: [{
                "pig_id": "PIG-1",
                "sex": "Female",
                "status": "Active",
                "on_farm": "Yes",
                "available_for_sale": "Yes",
                "sale_category": "Weaner",
                "current_weight_kg": 12,
            }],
        )

        decision = result["sam_decision"]

        self.assertEqual(decision["sales_lane"], "live_stock_sales")
        self.assertNotIn("lane_not_live_stock:unclear", decision["blockers"])
        self.assertIn("reservation_request_owner_gate", decision["blockers"])
        self.assertEqual(decision["facts"]["quantity"], 2)
        self.assertEqual(decision["facts"]["sex"], "Female")
        self.assertEqual(decision["facts"]["location"], "Riversdale")
        self.assertIn("cannot confirm those animals", decision["suggested_reply_text"])
        self.assertNotIn("implies_reservation", decision["conversation_review"]["blocked_reasons"])

    def test_live_pig_weight_range_infers_grower_category(self):
        inbound = sam_live_stock_runtime.parse_chatwoot_inbound(inbound_payload(
            content="Not meat, I want live pigs to raise, 2 males around 30kg in Albertinia.",
        ))
        facts = sam_live_stock_runtime.extract_live_stock_facts(inbound["content"], inbound)

        self.assertEqual(facts["category"], "grower")
        self.assertEqual(facts["quantity"], 2)
        self.assertEqual(facts["sex"], "male")
        self.assertEqual(facts["location"], "Albertinia")

    def test_owner_action_packet_exposes_routes_without_auto_authority(self):
        packet = sam_live_stock_runtime.build_live_stock_owner_action_packet(
            order_id="ORD-1",
            conversation_id="1774",
            document_id="DOC-1",
        )

        self.assertTrue(packet["owner_gate_required"])
        self.assertFalse(packet["reservation"]["allowed_for_sam_auto"])
        self.assertEqual(packet["reservation"]["route"], "/api/orders/ORD-1/reserve")
        self.assertFalse(packet["quote_send_confirmed"]["allowed_for_sam_auto"])
        self.assertIn("quote/send-latest-confirmed", packet["quote_send_confirmed"]["route"])

    def test_smoke_pack_and_go_live_checklist_expose_launch_gates(self):
        smoke = sam_live_stock_runtime.build_sam_live_stock_smoke_pack()
        checklist = sam_live_stock_runtime.build_sam_live_stock_go_live_checklist(environ={
            "SAM_LIVE_STOCK_BACKEND_WEBHOOK_ENABLED": "1",
            "SAM_LIVE_STOCK_BACKEND_WEBHOOK_TOKEN": "test-sam-live-stock-token-32-chars",
            "SAM_LIVE_STOCK_BACKEND_INTAKE_WRITE_ENABLED": "1",
            "SAM_LIVE_STOCK_BACKEND_DRAFT_ORDER_CREATE_ENABLED": "0",
            "SAM_LIVE_STOCK_BACKEND_AUTOREPLY_ENABLED": "0",
            "SAM_LIVE_STOCK_BACKEND_LLM_ENABLED": "0",
        })

        self.assertEqual(smoke["required_pass_rate"], "100%")
        self.assertGreaterEqual(smoke["scenario_count"], 6)
        self.assertIn("no reservation without owner action", smoke["must_verify"])
        self.assertEqual(checklist["blockers"], [])
        self.assertTrue(checklist["ready_for_controlled_smoke"])
        self.assertFalse(checklist["ready_for_public_launch"])

    def test_non_live_lane_returns_clarification_and_owner_gate(self):
        result, _status_code = sam_live_stock_runtime.handle_sam_live_stock_chatwoot_inbound(
            inbound_payload(content="I want pork chops and a freezer pack."),
            intake_context_loader=lambda _conversation_id: {"success": True, "known_fields": {}, "items": []},
            availability_loader=lambda: [],
        )

        self.assertEqual(result["status"], "sam_live_stock_wrong_lane_guard")
        self.assertFalse(result["processed"])
        self.assertEqual(result["lane_decision"]["final_route"], "meat_sales")
        self.assertFalse(result["lane_decision"]["cross_lane_handoff_allowed"])
        self.assertFalse(result["sent"])

    def test_context_read_failure_fails_closed_without_write_authority(self):
        def failing_intake(_conversation_id):
            raise RuntimeError("database offline")

        result, _status_code = sam_live_stock_runtime.handle_sam_live_stock_chatwoot_inbound(
            inbound_payload(),
            intake_context_loader=failing_intake,
            availability_loader=lambda: [],
        )

        decision = result["sam_decision"]
        self.assertIn("read_context_error", decision["blockers"])
        self.assertTrue(decision["owner_gate_required"])
        self.assertFalse(decision["writes_allowed"])
        self.assertFalse(decision["customer_send_allowed"])

    def test_hostile_location_challenge_creates_escalation_packet(self):
        result, _status_code = sam_live_stock_runtime.handle_sam_live_stock_chatwoot_inbound(
            inbound_payload(content="This sounds like a scam. Send the exact farm location now."),
            intake_context_loader=lambda _conversation_id: {"success": True, "known_fields": {}, "items": []},
            availability_loader=lambda: [],
        )

        decision = result["sam_decision"]
        review = decision["conversation_review"]

        self.assertTrue(review["escalation_required"])
        self.assertEqual(review["conversation_mode_recommendation"], "HUMAN")
        self.assertIn("hostile_or_scam_location_challenge", review["escalation_reasons"])
        self.assertIn("escalation_packet", decision)
        self.assertIn("waste your time", decision["escalation_packet"]["suggested_response"])
        self.assertIn("sam_live_approve_send:", decision["escalation_packet"]["telegram_packet"]["reply_markup"]["inline_keyboard"][0][0]["callback_data"])

    def test_business_question_no_longer_creates_debug_escalation_card(self):
        result, _status_code = sam_live_stock_runtime.handle_sam_live_stock_chatwoot_inbound(
            inbound_payload(content="Can I learn more about your business?"),
            intake_context_loader=lambda _conversation_id: {"success": True, "known_fields": {}, "items": []},
            availability_loader=lambda: [],
        )

        decision = result["sam_decision"]
        self.assertEqual(decision["sales_lane"], "farm_general_question")
        self.assertEqual(decision["reply_source"], "deterministic_farm_general_knowledge")
        self.assertNotIn("escalation_packet", decision)
        self.assertNotIn("are you looking for live pigs, pork", decision["suggested_reply_text"])

    def test_hostile_location_followup_inherits_live_stock_lane_and_visible_reply(self):
        def intake_loader(_conversation_id):
            return {
                "success": True,
                "known_fields": {"collection_location": "Riversdale"},
                "items": [{
                    "quantity": 2,
                    "category": "Weaner",
                    "weight_range": "10_to_14_Kg",
                    "sex": "Female",
                    "status": "active",
                }],
            }

        result, _status_code = sam_live_stock_runtime.handle_sam_live_stock_chatwoot_inbound(
            inbound_payload(content="Why won't you send me your farm location? This sounds like a scam."),
            intake_context_loader=intake_loader,
            availability_loader=lambda: [],
        )

        decision = result["sam_decision"]
        review = decision["conversation_review"]

        self.assertEqual(decision["sales_lane"], "live_stock_sales")
        self.assertNotIn("lane_not_live_stock:farm_general_question", decision["blockers"])
        self.assertTrue(review["escalation_required"])
        self.assertEqual(review["conversation_mode_recommendation"], "HUMAN")
        self.assertIn("hostile_or_scam_location_challenge", review["escalation_reasons"])
        self.assertIn("waste your time", decision["suggested_reply_text"])
        self.assertEqual(decision["suggested_reply_text"], decision["escalation_packet"]["suggested_response"])

    def test_price_challenge_requests_owner_authority_without_conversation_takeover(self):
        inbound = sam_live_stock_runtime.parse_chatwoot_inbound(
            inbound_payload(content="That price is too expensive. I can get cheaper pigs elsewhere.")
        )
        facts = sam_live_stock_runtime.extract_live_stock_facts(inbound["content"], inbound)
        decision = {
            "sales_lane": "live_stock_sales",
            "missing_fields": [],
            "blockers": [],
            "suggested_reply_text": "I understand. I can ask the owner whether the current price can be adjusted before I confirm anything.",
        }

        review = sam_live_stock_runtime.review_sam_live_stock_conversation(inbound, facts, decision)

        self.assertFalse(review["escalation_required"])
        self.assertTrue(review["owner_authority_required"])
        self.assertIn("negotiated_price_owner_authority", review["protected_action_reasons"])
        self.assertEqual(review["conversation_mode_recommendation"], "AUTO")
        self.assertTrue(review["safe_to_send"])

    def test_negotiated_price_phrases_are_bounded_in_english_and_afrikaans(self):
        positives = (
            "Can you give me a better price?",
            "Can you offer a better deal?",
            "Can you do better on the price?",
            "Could you do better?",
            "What is your lowest price?",
            "Kan jy vir my 'n beter prys gee?",
            "Kan julle beter doen?",
            "Kan jy dit goedkoper maak?",
            "Is daar afslag?",
        )
        negatives = (
            "What is the current price?",
            "Please send the price list.",
            "Die prys is R1200, reg?",
        )

        for text in positives:
            with self.subTest(text=text):
                self.assertTrue(sam_live_stock_runtime._price_challenge_signal(text))
        for text in negatives:
            with self.subTest(text=text):
                self.assertFalse(sam_live_stock_runtime._price_challenge_signal(text))

    def test_one_review_names_negotiated_price_and_reservation_without_execution(self):
        inbound = sam_live_stock_runtime.parse_chatwoot_inbound(
            inbound_payload(content="Can you give me a better price and reserve the 3 males for Friday?")
        )
        facts = sam_live_stock_runtime.extract_live_stock_facts(inbound["content"], inbound)
        decision = {
            "sales_lane": "live_stock_sales",
            "missing_fields": [],
            "blockers": ["reservation_request_owner_gate"],
            "suggested_reply_text": "I can ask the owner to review the price and exact animals before confirming anything.",
        }

        review = sam_live_stock_runtime.review_sam_live_stock_conversation(inbound, facts, decision)

        self.assertFalse(review["escalation_required"])
        self.assertEqual(review["recommended_action"], "owner_authority_decision")
        self.assertEqual(
            review["protected_action_reasons"],
            ["negotiated_price_owner_authority", "reservation_owner_authority"],
        )
        self.assertFalse(decision.get("reserves_stock", False))
        self.assertFalse(decision.get("creates_order", False))

    def test_final_order_and_payment_confirmation_keep_separate_owner_authority(self):
        inbound = sam_live_stock_runtime.parse_chatwoot_inbound(
            inbound_payload(content="I have paid and want to finalise the order.")
        )
        facts = sam_live_stock_runtime.extract_live_stock_facts(inbound["content"], inbound)
        facts["order_commitment"] = True
        decision = {
            "sales_lane": "live_stock_sales",
            "missing_fields": [],
            "blockers": [],
            "suggested_reply_text": "Thanks, I will have the farm verify the payment and final order before confirming either.",
        }

        review = sam_live_stock_runtime.review_sam_live_stock_conversation(inbound, facts, decision)

        self.assertFalse(review["escalation_required"])
        self.assertTrue(review["owner_authority_required"])
        self.assertIn("final_order_owner_authority", review["protected_action_reasons"])
        self.assertIn("payment_confirmation_owner_authority", review["protected_action_reasons"])

    def test_natural_close_recommends_no_reply(self):
        inbound = sam_live_stock_runtime.parse_chatwoot_inbound(inbound_payload(content="Thanks, have a good day."))
        facts = sam_live_stock_runtime.extract_live_stock_facts(inbound["content"], inbound)
        decision = {"sales_lane": "live_stock_sales", "missing_fields": [], "blockers": [], "suggested_reply_text": "Pleasure."}

        review = sam_live_stock_runtime.review_sam_live_stock_conversation(inbound, facts, decision)

        self.assertTrue(review["no_reply_recommended"])
        self.assertEqual(review["recommended_action"], "no_reply_natural_close")
        self.assertFalse(review["safe_to_send"])

    def test_natural_close_handler_clears_visible_suggested_reply(self):
        result, _status_code = sam_live_stock_runtime.handle_sam_live_stock_chatwoot_inbound(
            inbound_payload(content="Thanks, have a good day."),
            intake_context_loader=lambda _conversation_id: {
                "success": True,
                "known_fields": {"collection_location": "Riversdale"},
                "items": [{
                    "quantity": 2,
                    "category": "Weaner",
                    "weight_range": "10_to_14_Kg",
                    "sex": "Female",
                    "status": "active",
                }],
            },
            conversation_history_loader=lambda _conversation_id, _source: {"success": True, "messages": []},
            availability_loader=lambda: [],
            owner_example_loader=lambda *_args, **_kwargs: {"success": True, "examples": []},
        )

        decision = result["sam_decision"]
        review = decision["conversation_review"]

        self.assertTrue(review["no_reply_recommended"])
        self.assertEqual(review["recommended_action"], "no_reply_natural_close")
        self.assertEqual(decision["suggested_reply_text"], "")
        self.assertEqual(decision["reply_source"], "natural_close_no_reply_guard")

    def test_owner_approved_send_is_env_gated(self):
        calls = []

        def sender(conversation_id, message, source):
            calls.append((conversation_id, message, source))
            return {"status_code": 200, "body": {"id": 1, "status": "sent"}}

        blocked, blocked_status = sam_live_stock_runtime.send_owner_approved_live_stock_reply(
            "2401",
            "Owner approved reply.",
            environ={},
            chatwoot_sender=sender,
        )

        self.assertEqual(blocked_status, 409)
        self.assertEqual(blocked["status"], "sam_live_stock_owner_send_disabled")
        self.assertEqual(calls, [])

        sent, sent_status = sam_live_stock_runtime.send_owner_approved_live_stock_reply(
            "2401",
            "Owner approved reply.",
            environ={"SAM_LIVE_STOCK_OWNER_APPROVED_SEND_ENABLED": "1"},
            chatwoot_sender=sender,
            owner="Charl",
            escalation_id="SAM-LIVE-ESC-1",
        )

        self.assertEqual(sent_status, 200)
        self.assertTrue(sent["success"])
        self.assertTrue(sent["sends_customer_message"])
        self.assertFalse(sent["customer_send_confirmed"])
        self.assertEqual(sent["delivery"]["delivery_state"], "chatwoot_accepted_unverified")
        self.assertTrue(sent["calls_chatwoot"])
        self.assertEqual(calls[0][0], "2401")

    def test_chatwoot_sender_omits_application_source_id(self):
        captured = []

        class Response:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return b'{"id":11,"status":"sent","source_id":"wamid.SECRET"}'

        with patch.object(
            sam_live_stock_runtime.urllib_request,
            "urlopen",
            side_effect=lambda request, timeout=0: captured.append((request, timeout)) or Response(),
        ):
            response = sam_live_stock_runtime._send_chatwoot_message(
                "2013",
                "Hi Charl! How can I help you today?",
                {
                    "CHATWOOT_BASE_URL": "https://chatwoot.test",
                    "CHATWOOT_ACCOUNT_ID": "147387",
                    "CHATWOOT_API_ACCESS_TOKEN": "secret-token",
                },
                amadeus_source="sam_live_stock_routine_reply",
            )
        body = json.loads(captured[0][0].data.decode())
        self.assertNotIn("source_id", body)
        self.assertEqual(body["content_attributes"]["amadeus_source"], "sam_live_stock_routine_reply")
        self.assertEqual(response["body"]["status"], "sent")

    def test_takeover_and_cleanup_packets_are_auditable(self):
        takeover = sam_live_stock_runtime.build_sam_live_stock_chatwoot_takeover_payload(
            "2401",
            mode="HUMAN",
            reason="hostile_or_scam_location_challenge",
        )
        cleanup = sam_live_stock_runtime.build_sam_live_stock_resolved_cleanup_packet(
            "SAM-LIVE-ESC-1",
            telegram_chat_id="5721652188",
            telegram_message_id="77",
            conversation_id="2401",
        )

        self.assertEqual(takeover["custom_attributes"]["conversation_mode"], "HUMAN")
        self.assertIn("owner_handoff", takeover["labels"])
        self.assertEqual(cleanup["recommended_action"], "delete_telegram_notification")
        self.assertTrue(cleanup["delete_allowed"])


    def test_definitive_meat_guard_runs_before_all_livestock_fact_readers(self):
        calls = {"context": 0, "availability": 0}

        def context_loader(_conversation_id):
            calls["context"] += 1
            return {"success": True}

        def availability_loader():
            calls["availability"] += 1
            return []

        result, status_code = sam_live_stock_runtime.handle_sam_live_stock_chatwoot_inbound(
            inbound_payload(content="I want a half carcass, Set A."),
            intake_context_loader=context_loader,
            availability_loader=availability_loader,
        )

        self.assertEqual(status_code, 200)
        self.assertEqual(result["status"], "sam_live_stock_wrong_lane_guard")
        self.assertEqual(calls, {"context": 0, "availability": 0})
        self.assertFalse(result["sends_customer_message"])
        self.assertFalse(result["creates_order"])
        self.assertFalse(result["reserves_stock"])

    def test_conversation_1994_shape_recovers_referral_and_uses_zero_specialist_tools(self):
        calls = {"intake": 0, "availability": 0, "send": 0}

        def intake_loader(_conversation_id):
            calls["intake"] += 1
            return {"success": True}

        def availability_loader():
            calls["availability"] += 1
            return [exact_eligible_row(pig_id=f"PIG-{index}") for index in range(52)]

        def sender(*_args):
            calls["send"] += 1
            return {"success": True}

        result, status_code = sam_live_stock_runtime.handle_sam_live_stock_chatwoot_inbound(
            inbound_payload(
                id=759168596,
                content="Hello! Can I get more info on this?",
                conversation={
                    "id": 1994,
                    "inbox": {"id": 96568, "channel_type": "Channel::Whatsapp"},
                },
                sender={"id": 699, "name": "Henry", "phone_number": "+27000000000"},
                content_attributes={
                    "referral": {
                        "source_type": "ad",
                        "source_id": "120248031275440407",
                        "headline": "Amadeus Farm - Sustainable Piglets & Produce",
                        "body": "Meet Ms. Piggy and her fearless family! This strong mother has nurtured her litter of 10 piglets.",
                    },
                },
            ),
            environ={},
            intake_context_loader=intake_loader,
            conversation_history_loader=lambda *_args: {"success": True, "messages": []},
            availability_loader=availability_loader,
            chatwoot_sender=sender,
        )

        decision = result["sam_decision"]
        self.assertEqual(status_code, 200)
        self.assertEqual(result["status"], "sam_auto_general_conversation_processed")
        self.assertEqual(decision["conversation_ownership"], "AUTO_GENERAL")
        self.assertEqual(decision["sales_lane"], "unclear")
        self.assertEqual(decision["specialist_tools_called"], [])
        self.assertEqual(decision["availability"]["matched_count"], 0)
        self.assertEqual(decision["match_packet"], {})
        self.assertEqual(calls, {"intake": 0, "availability": 0, "send": 0})
        self.assertIn("Ms. Piggy", decision["suggested_reply_text"])
        self.assertIn("litter of piglets", decision["suggested_reply_text"])
        self.assertFalse(decision["handled_autonomously"])
        self.assertFalse(decision["clarification_asked"])
        self.assertFalse(decision["specialist_lane_selected"])
        self.assertFalse(decision["owner_escalation_required"])
        self.assertTrue(decision["owner_action_required"])
        self.assertEqual(decision["reason"], "routine_reply_waiting_for_owner")
        self.assertEqual(
            decision["transition_visibility"]["notification_class"],
            "owner_review",
        )
        self.assertFalse(decision["customer_send_authorized"])
        self.assertFalse(result["sent"])
        self.assertFalse(result["creates_order"])
        self.assertFalse(result["reserves_stock"])

    def test_context_resolved_livestock_terse_followup_stays_specialist(self):
        current_at = 1785313934
        payload = inbound_payload(
            id=765363539,
            created_at=current_at,
            content="Both",
            conversation={
                "id": 1577,
                "inbox": {
                    "id": 96568,
                    "channel_type": "Channel::Whatsapp",
                },
                "meta": {"sender": {"id": 787172447}},
            },
            sender={"id": 787172447, "name": "Customer"},
        )
        history = {
            "success": True,
            "messages": [
                {
                    "id": "765300001",
                    "message_type": 0,
                    "private": False,
                    "created_at": current_at - 120,
                    "content": (
                        "I need a female piglet between 10 and 14 kg. "
                        "What is the price?"
                    ),
                },
                {
                    "id": "765300002",
                    "message_type": 1,
                    "private": False,
                    "created_at": current_at - 60,
                    "content": "How many do you need?",
                },
                {
                    "id": "765363539",
                    "message_type": 0,
                    "private": False,
                    "created_at": current_at,
                    "content": "Both",
                },
            ],
        }
        result, status = (
            sam_live_stock_runtime.handle_sam_live_stock_chatwoot_inbound(
                payload,
                environ={},
                intake_context_loader=lambda *_args: {
                    "success": True,
                    "known_fields": {},
                    "items": [],
                },
                conversation_history_loader=lambda *_args: history,
                conversation_identity_loader=lambda *_args: {
                    "success": True,
                    "status": "loaded",
                    "account_id": "147387",
                    "conversation_id": "1577",
                    "contact_id": "787172447",
                    "inbox_id": "96568",
                },
                availability_loader=lambda: [],
            )
        )
        decision = result["sam_decision"]
        self.assertEqual(status, 200)
        self.assertEqual(decision["conversation_ownership"], "AUTO_SPECIALIST")
        self.assertTrue(decision["specialist_lane_selected"])
        self.assertEqual(decision["sales_lane"], "live_stock_sales")
        self.assertEqual(
            decision["contextual_sales_route"]["status"],
            "authoritative_live_stock_context_preserved",
        )
        self.assertTrue(
            decision["contextual_sales_route"]["checks"]["identity_bound"]
        )
        self.assertTrue(
            decision["contextual_sales_route"]["checks"]["fresh"]
        )

    def test_current_confident_livestock_route_cannot_fall_to_auto_general(self):
        cases = (
            ("Hoeveel kos 'n vark?", "Richard"),
            ("Hoeveel is die piglets?", "Azulidgaf"),
        )
        for index, (content, name) in enumerate(cases, start=1):
            with self.subTest(content=content):
                payload = inbound_payload(
                    id=f"current-livestock-{index}",
                    created_at=1785342834 + index,
                    content=content,
                    conversation={
                        "id": 2100 + index,
                        "inbox": {
                            "id": 96568,
                            "channel_type": "Channel::Whatsapp",
                        },
                        "meta": {"sender": {"id": 987000000 + index}},
                    },
                    sender={
                        "id": 987000000 + index,
                        "name": name,
                    },
                )
                history = {
                    "success": True,
                    "evidence_complete": True,
                    "messages": [
                        {
                            "id": f"current-livestock-{index}",
                            "message_type": 0,
                            "private": False,
                            "created_at": 1785342834 + index,
                            "content": content,
                        }
                    ],
                }
                result, status = (
                    sam_live_stock_runtime.handle_sam_live_stock_chatwoot_inbound(
                        payload,
                        environ={
                            "SAM_LIVE_STOCK_BACKEND_LLM_ENABLED": "0",
                        },
                        intake_context_loader=lambda *_args: {
                            "success": True,
                            "known_fields": {},
                            "items": [],
                        },
                        conversation_history_loader=lambda *_args: history,
                        conversation_identity_loader=lambda *_args, i=index: {
                            "success": True,
                            "status": "loaded",
                            "account_id": "147387",
                            "conversation_id": str(2100 + i),
                            "contact_id": str(987000000 + i),
                            "inbox_id": "96568",
                        },
                        availability_loader=lambda: [],
                    )
                )
                decision = result["sam_decision"]
                self.assertEqual(status, 200)
                self.assertEqual(
                    decision["contextual_sales_route"]["final_route"],
                    "live_stock_sales",
                )
                self.assertEqual(
                    decision["conversation_ownership"], "AUTO_SPECIALIST"
                )
                self.assertTrue(decision["specialist_lane_selected"])
                self.assertEqual(
                    decision["reply_source"],
                    "deterministic_customer_size_guidance",
                )
                reply = decision["suggested_reply_text"].lower()
                self.assertNotIn("we don\u2019t offer pork", reply)
                self.assertNotIn("we do have piglets", reply)
                self.assertNotIn("we offer pigs", reply)
                self.assertIn("approximately", reply)
                self.assertIn(
                    "current availability still need to be confirmed",
                    reply,
                )

    def test_contextual_route_preserves_terse_followup_but_not_lane_change_or_mixed(self):
        inbound = {
            "account_id": "147387",
            "conversation_id": "1577",
            "contact_id": "787172447",
            "inbox_id": "96568",
            "last_inbound_at": 1785313934,
            "identity_provenance": {
                "status": "identity_verified",
                "authoritative_conversation_lookup": {
                    "success": True,
                    "identity_complete": True,
                    "account_id_matches": True,
                    "field_matches": {
                        "conversation_id": True,
                        "contact_id": True,
                        "inbox_id": True,
                    },
                },
            },
        }
        prior = {
            "interest": {
                "sales_lane": "live_stock_sales",
                "lane_confidence": 0.9,
                "category": "piglet",
            },
            "source": "chatwoot_conversation_history",
            "evidence_complete": True,
            "latest_context_at": 1785313874,
            "conversation_id": "1577",
            "contact_id": "787172447",
            "inbox_id": "96568",
            "account_id": "147387",
        }
        cases = (
            (
                "Both",
                True,
                "authoritative_live_stock_context_preserved",
            ),
            (
                "I want half a carcass, Set A.",
                False,
                "affirmative_lane_change_preserved",
            ),
            (
                "I want live piglets and half a carcass.",
                False,
                "mixed_intent_requires_clarification",
            ),
            (
                "Tell me more about your farm.",
                True,
                "authoritative_live_stock_context_preserved",
            ),
            (
                "Where are you located?",
                True,
                "authoritative_live_stock_context_preserved",
            ),
            (
                "Location",
                True,
                "authoritative_live_stock_context_preserved",
            ),
            (
                "This is a new request. Tell me about farm visits.",
                False,
                "explicit_context_reset",
            ),
        )
        for content, preserve, status in cases:
            with self.subTest(content=content):
                packet = sam_live_stock_runtime.resolve_contextual_sales_route(
                    {**inbound, "content": content},
                    {},
                    prior,
                )
                self.assertEqual(
                    packet["preserve_live_stock_lane"], preserve
                )
                self.assertEqual(packet["status"], status)

    def test_contextual_route_rejects_stale_or_identity_mismatched_context(self):
        inbound = {
            "content": "Both",
            "account_id": "147387",
            "conversation_id": "1577",
            "contact_id": "787172447",
            "inbox_id": "96568",
            "last_inbound_at": 1785313934,
            "identity_provenance": {
                "status": "identity_verified",
                "authoritative_conversation_lookup": {
                    "success": True,
                    "identity_complete": True,
                    "account_id_matches": True,
                    "field_matches": {
                        "conversation_id": True,
                        "contact_id": True,
                        "inbox_id": True,
                    },
                },
            },
        }
        base = {
            "interest": {
                "sales_lane": "live_stock_sales",
                "lane_confidence": 0.9,
            },
            "evidence_complete": True,
            "latest_context_at": 1785313874,
            "conversation_id": "1577",
            "contact_id": "787172447",
            "inbox_id": "96568",
            "account_id": "147387",
        }
        cases = (
            ({**base, "latest_context_at": 1785313934 - 31 * 86400}, "fresh"),
            ({**base, "conversation_id": "other"}, "identity_bound"),
            ({**base, "contact_id": "other"}, "identity_bound"),
            ({**base, "inbox_id": "other"}, "identity_bound"),
        )
        for prior, failed_check in cases:
            with self.subTest(failed_check=failed_check):
                packet = sam_live_stock_runtime.resolve_contextual_sales_route(
                    inbound, {}, prior
                )
                self.assertFalse(packet["preserve_live_stock_lane"])
                self.assertFalse(packet["checks"][failed_check])
                self.assertEqual(
                    packet["status"], "prior_context_not_authoritative"
                )

    def test_provider_identity_conflict_blocks_contextual_specialist_route(self):
        current_at = 1785313934
        payload = inbound_payload(
            id="current",
            created_at=current_at,
            content="Both",
            conversation={
                "id": 1577,
                "inbox": {
                    "id": 96568,
                    "channel_type": "Channel::Whatsapp",
                },
                "meta": {"sender": {"id": 787172447}},
            },
            sender={"id": 787172447, "name": "Customer"},
        )
        history = {
            "success": True,
            "messages": [
                {
                    "id": "prior",
                    "message_type": 0,
                    "created_at": current_at - 60,
                    "content": "I need two female piglets.",
                },
                {
                    "id": "current",
                    "message_type": 0,
                    "created_at": current_at,
                    "content": "Both",
                },
            ],
        }
        result, status = (
            sam_live_stock_runtime.handle_sam_live_stock_chatwoot_inbound(
                payload,
                environ={},
                conversation_history_loader=lambda *_args: history,
                conversation_identity_loader=lambda *_args: {
                    "success": True,
                    "status": "loaded",
                    "account_id": "147387",
                    "conversation_id": "1577",
                    "contact_id": "different-contact",
                    "inbox_id": "96568",
                },
                availability_loader=lambda: self.fail(
                    "identity conflict called Livestock availability"
                ),
                intake_context_loader=lambda *_args: self.fail(
                    "identity conflict called Livestock intake"
                ),
            )
        )
        decision = result["sam_decision"]
        self.assertEqual(status, 200)
        self.assertEqual(decision["conversation_ownership"], "AUTO_GENERAL")
        self.assertFalse(
            decision["contextual_sales_route"][
                "preserve_live_stock_lane"
            ]
        )
        self.assertFalse(
            decision["contextual_sales_route"]["checks"]["identity_bound"]
        )
        self.assertFalse(result["sent"])

    def test_incomplete_provider_identity_blocks_contextual_specialist_route(self):
        current_at = 1785313934
        payload = inbound_payload(
            id="current",
            created_at=current_at,
            content="Both",
            conversation={
                "id": 1577,
                "inbox": {
                    "id": 96568,
                    "channel_type": "Channel::Whatsapp",
                },
                "meta": {"sender": {"id": 787172447}},
            },
            sender={"id": 787172447, "name": "Customer"},
        )
        history = {
            "success": True,
            "messages": [
                {
                    "id": "prior",
                    "message_type": 0,
                    "created_at": current_at - 60,
                    "content": "I need two female piglets.",
                },
                {
                    "id": "current",
                    "message_type": 0,
                    "created_at": current_at,
                    "content": "Both",
                },
            ],
        }
        authoritative_identity = {
            "success": True,
            "status": "loaded",
            "account_id": "147387",
            "conversation_id": "1577",
            "contact_id": "787172447",
            "inbox_id": "96568",
        }
        for missing_field in (
            "conversation_id",
            "contact_id",
            "inbox_id",
        ):
            with self.subTest(missing_field=missing_field):
                provider_identity = {
                    key: value
                    for key, value in authoritative_identity.items()
                    if key != missing_field
                }
                result, status = (
                    sam_live_stock_runtime.handle_sam_live_stock_chatwoot_inbound(
                        payload,
                        environ={},
                        conversation_history_loader=lambda *_args: history,
                        conversation_identity_loader=lambda *_args, identity=provider_identity: identity,
                        availability_loader=lambda: self.fail(
                            "incomplete provider identity called Livestock availability"
                        ),
                        intake_context_loader=lambda *_args: self.fail(
                            "incomplete provider identity called Livestock intake"
                        ),
                    )
                )
                decision = result["sam_decision"]
                lookup = decision["inbound"]["identity_provenance"][
                    "authoritative_conversation_lookup"
                ]
                self.assertEqual(status, 200)
                self.assertFalse(lookup["identity_complete"])
                self.assertFalse(lookup["field_matches"][missing_field])
                self.assertEqual(
                    decision["conversation_ownership"], "AUTO_GENERAL"
                )
                self.assertFalse(
                    decision["contextual_sales_route"][
                        "preserve_live_stock_lane"
                    ]
                )
                self.assertFalse(result["sent"])

    def test_prior_livestock_lane_survives_multiple_terse_followups(self):
        inbound = {
            "message_id": "current",
            "account_id": "147387",
            "conversation_id": "1577",
            "contact_id": "787172447",
            "inbox_id": "96568",
        }
        history = {
            "success": True,
            "messages": [
                {
                    "id": "one",
                    "message_type": 0,
                    "created_at": 1785313600,
                    "content": (
                        "I need a female piglet between 10 and 14 kg. "
                        "What is the price?"
                    ),
                },
                {
                    "id": "two",
                    "message_type": 0,
                    "created_at": 1785313700,
                    "content": "Both",
                },
                {
                    "id": "three",
                    "message_type": 0,
                    "created_at": 1785313800,
                    "content": "Next week",
                },
            ],
        }
        prior = sam_live_stock_runtime._prior_context_from_chatwoot_history(
            history, inbound
        )
        self.assertEqual(
            prior["interest"]["sales_lane"], "live_stock_sales"
        )
        self.assertGreaterEqual(
            prior["interest"]["lane_confidence"], 0.9
        )
        self.assertEqual(prior["latest_context_at"], 1785313800)

    def test_auto_general_unsupported_availability_wording_is_never_authorized(self):
        inbound = {
            "content": "Both",
            "conversation_id": "1577",
            "contact_id": "787172447",
            "inbox_id": "96568",
            "identity_provenance": {"status": "identity_verified"},
        }
        decision = {
            "conversation_ownership": "AUTO_GENERAL",
            "specialist_lane_selected": False,
            "owner_escalation_required": False,
            "specialist_tools_called": [],
            "clarification_asked": True,
            "reply_source": "llm_auto_general_reply_draft",
            "suggested_reply_text": (
                "We have both male and female piglets around 10 to 14 kg. "
                "Which do you prefer?"
            ),
            "llm_draft": {"used": True, "confidence": 0.99},
        }
        source = {
            "SAM_AUTO_GENERAL_AUTOREPLY_ENABLED": "1",
            "SAM_AUTO_GENERAL_CANARY_ENABLED": "1",
            "SAM_AUTO_GENERAL_CANARY_CONVERSATION_ID": "1577",
            "SAM_AUTO_GENERAL_CANARY_CONTACT_ID": "787172447",
            "SAM_AUTO_GENERAL_CANARY_INBOX_ID": "96568",
        }
        packet = sam_live_stock_runtime._auto_general_canary_evaluation(
            inbound,
            decision,
            {"safe_to_send": True, "escalation_required": False},
            source,
        )
        self.assertFalse(packet["allowed"])
        self.assertFalse(packet["checks"]["claim_free_reply"])
        self.assertEqual(
            packet["status"], "auto_general_canary_factual_claim_blocked"
        )

    def test_auto_general_equivalent_commercial_claims_are_blocked(self):
        claims = (
            "Piglets are on hand.",
            "They are ready for pickup.",
            "You can collect tomorrow.",
            "We are based in Riversdale.",
            "We can arrange transport.",
            "Transport is available.",
        )
        for reply in claims:
            with self.subTest(reply=reply):
                self.assertTrue(
                    sam_live_stock_runtime
                    ._auto_general_reply_has_factual_or_commercial_claim(reply)
                )

    def test_mixed_current_intent_uses_claim_free_clarification(self):
        current_at = 1785313934
        payload = inbound_payload(
            id="current",
            created_at=current_at,
            content="I want live piglets and half a carcass.",
            conversation={
                "id": 1577,
                "inbox": {
                    "id": 96568,
                    "channel_type": "Channel::Whatsapp",
                },
                "meta": {"sender": {"id": 787172447}},
            },
            sender={"id": 787172447, "name": "Customer"},
        )
        history = {
            "success": True,
            "messages": [
                {
                    "id": "prior",
                    "message_type": 0,
                    "created_at": current_at - 60,
                    "content": "I need two female piglets.",
                },
                {
                    "id": "current",
                    "message_type": 0,
                    "created_at": current_at,
                    "content": "I want live piglets and half a carcass.",
                },
            ],
        }
        result, status = (
            sam_live_stock_runtime.handle_sam_live_stock_chatwoot_inbound(
                payload,
                environ={},
                conversation_history_loader=lambda *_args: history,
                conversation_identity_loader=lambda *_args: {
                    "success": True,
                    "status": "loaded",
                    "account_id": "147387",
                    "conversation_id": "1577",
                    "contact_id": "787172447",
                    "inbox_id": "96568",
                },
                availability_loader=lambda: self.fail(
                    "mixed intent called Livestock availability"
                ),
                intake_context_loader=lambda *_args: self.fail(
                    "mixed intent called Livestock intake"
                ),
            )
        )
        decision = result["sam_decision"]
        self.assertEqual(status, 200)
        self.assertEqual(decision["conversation_ownership"], "AUTO_GENERAL")
        self.assertEqual(
            decision["contextual_sales_route"]["status"],
            "mixed_intent_requires_clarification",
        )
        self.assertIn("live pigs, pork or meat, or both", decision[
            "suggested_reply_text"
        ])
        self.assertFalse(
            sam_live_stock_runtime
            ._auto_general_reply_has_factual_or_commercial_claim(
                decision["suggested_reply_text"]
            )
        )

    def test_missing_referral_uses_exact_one_question_general_draft(self):
        result, _status = sam_live_stock_runtime.handle_sam_live_stock_chatwoot_inbound(
            inbound_payload(
                content="Hello! Can I get more info on this?",
                conversation={"id": 1994, "inbox": {"id": 96568, "channel_type": "Channel::Whatsapp"}},
                sender={"id": 699, "name": "Henry"},
            ),
            environ={},
            conversation_history_loader=lambda *_args: {"success": True, "messages": []},
            availability_loader=lambda: self.fail("general message called availability"),
            intake_context_loader=lambda *_args: self.fail("general message called order intake"),
        )
        reply = result["sam_decision"]["suggested_reply_text"]
        self.assertEqual(
            reply,
            "Hi Henry! Of course. Are you asking about the piglets in the post, "
            "or was there something else on our page you wanted to know more about?",
        )
        self.assertEqual(reply.count("?"), 1)
        self.assertTrue(result["sam_decision"]["clarification_asked"])

    def test_routine_majority_multiturn_states_do_not_force_a_lane(self):
        general_turns = [
            ("Hi", "How can I help"),
            ("I saw your piglet post.", "piglet post"),
            ("Can I get more info on this?", "Are you asking about the piglets"),
            ("They look very healthy. How old are they?", "need to check that detail"),
            ("Thanks, I am still just looking.", "No problem at all"),
        ]
        for message, expected in general_turns:
            with self.subTest(message=message):
                result, status = sam_live_stock_runtime.handle_sam_live_stock_chatwoot_inbound(
                    inbound_payload(content=message),
                    environ={},
                    conversation_history_loader=lambda *_args: {"success": True, "messages": []},
                    availability_loader=lambda: self.fail("general turn called availability"),
                    intake_context_loader=lambda *_args: self.fail("general turn called order intake"),
                )
                decision = result["sam_decision"]
                self.assertEqual(status, 200)
                self.assertEqual(decision["conversation_ownership"], "AUTO_GENERAL")
                self.assertEqual(decision["specialist_tools_called"], [])
                self.assertFalse(decision["owner_escalation_required"])
                self.assertIn(expected, decision["suggested_reply_text"])

        livestock_calls = {"availability": 0}

        def availability():
            livestock_calls["availability"] += 1
            return []

        livestock, _status = sam_live_stock_runtime.handle_sam_live_stock_chatwoot_inbound(
            inbound_payload(content="I may want two males around 30 kg."),
            intake_context_loader=lambda *_args: {"success": True, "known_fields": {}, "items": []},
            conversation_history_loader=lambda *_args: {"success": True, "messages": []},
            availability_loader=availability,
        )
        self.assertEqual(livestock["sam_decision"]["sales_lane"], "live_stock_sales")
        self.assertEqual(livestock_calls["availability"], 1)

    def test_topic_change_and_human_request_have_independent_outcomes(self):
        meat_calls = {"availability": 0}
        meat, _status = sam_live_stock_runtime.handle_sam_live_stock_chatwoot_inbound(
            inbound_payload(content="I want half a carcass, Set A."),
            conversation_history_loader=lambda *_args: {
                "success": True,
                "messages": [{"id": "old", "message_type": 0, "content": "I wanted two male piglets."}],
            },
            availability_loader=lambda: meat_calls.__setitem__("availability", meat_calls["availability"] + 1),
        )
        self.assertEqual(meat["status"], "sam_live_stock_wrong_lane_guard")
        self.assertEqual(meat_calls["availability"], 0)

        human, _status = sam_live_stock_runtime.handle_sam_live_stock_chatwoot_inbound(
            inbound_payload(content="Can I speak to Charl please?"),
            environ={},
            conversation_history_loader=lambda *_args: {"success": True, "messages": []},
            availability_loader=lambda: self.fail("human request called availability"),
        )
        decision = human["sam_decision"]
        self.assertFalse(decision["handled_autonomously"])
        self.assertTrue(decision["owner_escalation_required"])
        self.assertEqual(decision["next_action"], "escalate")
        self.assertEqual(
            decision["conversation_review"]["escalation_reasons"],
            ["customer_explicitly_requested_human"],
        )

    def test_empty_requirements_never_match_all_available_animals(self):
        availability = sam_live_stock_runtime.summarize_live_stock_availability(
            [exact_eligible_row(pig_id=f"PIG-{index}") for index in range(52)],
            {"sales_lane": "unclear", "quantity": "", "category": "", "sex": "", "weight_range": ""},
        )
        packet = sam_live_stock_runtime.build_live_stock_match_packet(
            {"sales_lane": "unclear", "quantity": "", "category": "", "sex": "", "weight_range": ""},
            availability,
        )
        self.assertEqual(availability["matched_count"], 0)
        self.assertEqual(packet["exact_match_count"], 0)
        self.assertEqual(packet["matched_sample"], [])
        self.assertEqual(packet["selected_pig_ids"], [])
        self.assertFalse(packet["matching_gate"]["minimum_usable_constraints"])

    def test_llm_wrong_lane_returns_to_short_auto_general_fallback(self):
        result, _status = sam_live_stock_runtime.handle_sam_live_stock_chatwoot_inbound(
            inbound_payload(content="Can I get more info on this?", sender={"id": 99, "name": "Henry"}),
            environ={
                "SAM_LIVE_STOCK_BACKEND_LLM_ENABLED": "1",
                "SAM_LIVE_STOCK_BACKEND_LLM_MODEL": "test-model",
                "OPENAI_API_KEY": "test-key",
            },
            conversation_history_loader=lambda *_args: {"success": True, "messages": []},
            availability_loader=lambda: self.fail("wrong-lane LLM result called availability"),
            llm_drafter=lambda *_args: {
                "reply_text": "We have 52 piglets available for R450.",
                "lane": "live_stock_sales",
                "confidence": 0.99,
            },
        )
        decision = result["sam_decision"]
        self.assertEqual(decision["llm_draft"]["status"], "llm_wrong_lane_returned_to_auto_general")
        self.assertEqual(decision["reply_source"], "deterministic_auto_general_fallback")
        self.assertNotIn("52", decision["suggested_reply_text"])
        self.assertNotIn("R450", decision["suggested_reply_text"])
        self.assertFalse(decision["owner_escalation_required"])

    def test_auto_general_canary_is_separate_disabled_exact_identity_boundary(self):
        policy = sam_live_stock_runtime.sam_live_stock_webhook_policy({})
        general = policy["auto_general_canary"]
        self.assertFalse(general["enabled"])
        self.assertFalse(general["global_enabled"])
        self.assertTrue(general["requires_all_three_exact_identity_matches"])
        self.assertTrue(general["requires_reviewed_llm_result"])
        self.assertTrue(general["requires_persistent_idempotency_claim_before_send"])
        self.assertEqual(
            general["confirmed_delivery_states"],
            ["provider_delivered", "provider_read"],
        )
        self.assertIn("chatwoot_accepted_unverified", general["delivery_states"])
        self.assertTrue(general["specialist_and_protected_actions_disabled"])
        self.assertTrue(general["telegram_exception_only"])

    def test_auto_general_canary_claims_before_fake_send_and_records_terminal_outcome(self):
        order = []
        inbound = {
            "conversation_id": "TEST-GENERAL",
            "contact_id": "TEST-CONTACT",
            "inbox_id": "TEST-INBOX",
            "content": "Hello",
            "identity_provenance": verified_identity(
                "TEST-GENERAL",
                "TEST-CONTACT",
                "TEST-INBOX",
            ),
        }
        decision = {
            "conversation_ownership": "AUTO_GENERAL",
            "suggested_reply_text": "Hi! How can I help you today?",
            "reply_source": "llm_auto_general_reply_draft",
            "should_reply": True,
            "llm_draft": {"used": True, "confidence": 0.99},
            "specialist_lane_selected": False,
            "specialist_tools_called": [],
            "owner_escalation_required": False,
            "creates_order": False,
            "creates_quote": False,
            "reserves_stock": False,
            "changes_stock": False,
            "writes_farm_data": False,
        }
        review = {"safe_to_send": True, "escalation_required": False}
        source = {
            "SAM_AUTO_GENERAL_AUTOREPLY_ENABLED": "1",
            "SAM_AUTO_GENERAL_CANARY_ENABLED": "1",
            "SAM_AUTO_GENERAL_CANARY_CONVERSATION_ID": "TEST-GENERAL",
            "SAM_AUTO_GENERAL_CANARY_CONTACT_ID": "TEST-CONTACT",
            "SAM_AUTO_GENERAL_CANARY_INBOX_ID": "TEST-INBOX",
        }

        delivery = sam_live_stock_runtime.deliver_sam_live_stock_routine_reply_if_enabled(
            inbound,
            decision,
            review,
            source,
            delivery_claim=lambda *_args: (
                order.append("claim")
                or {"success": True, "created": True, "review_event_id": "CLAIM-1"}
            ),
            chatwoot_sender=lambda *_args: (
                order.append("fake_send")
                or {"success": True, "status_code": 200, "body": {"id": 1, "status": "sent"}}
            ),
            delivery_evidence_recorder=lambda _claim, outcome: (
                order.append("evidence:" + outcome["delivery_state"])
                or {"success": True, "status": "recorded"}
            ),
        )

        self.assertEqual(order, ["claim", "fake_send", "evidence:chatwoot_accepted_unverified"])
        self.assertFalse(delivery["sent"])
        self.assertTrue(delivery["chatwoot_accepted"])
        self.assertFalse(delivery["delivery_outcome"]["customer_send_confirmed"])
        self.assertTrue(delivery["automatic_retry_prohibited"])
        self.assertTrue(delivery["canary"]["allowed"])

    def test_auto_general_claim_failure_makes_zero_chatwoot_calls(self):
        calls = []
        delivery = sam_live_stock_runtime.deliver_sam_live_stock_routine_reply_if_enabled(
            {
                "conversation_id": "2013",
                "contact_id": "699428938",
                "inbox_id": "96568",
                "content": "Hi",
                "identity_provenance": verified_identity("2013", "699428938", "96568"),
            },
            {
                "conversation_ownership": "AUTO_GENERAL",
                "suggested_reply_text": "Hi Charl! How can I help you today?",
                "reply_source": "llm_auto_general_reply_draft",
                "should_reply": True,
                "llm_draft": {"used": True, "confidence": 0.95},
                "specialist_lane_selected": False,
                "specialist_tools_called": [],
                "owner_escalation_required": False,
            },
            {"safe_to_send": True, "escalation_required": False},
            {
                "SAM_AUTO_GENERAL_AUTOREPLY_ENABLED": "1",
                "SAM_AUTO_GENERAL_CANARY_ENABLED": "1",
                "SAM_AUTO_GENERAL_CANARY_CONVERSATION_ID": "2013",
                "SAM_AUTO_GENERAL_CANARY_CONTACT_ID": "699428938",
                "SAM_AUTO_GENERAL_CANARY_INBOX_ID": "96568",
            },
            delivery_claim=lambda *_args: {"success": False, "created": False},
            chatwoot_sender=lambda *_args: calls.append("send"),
        )
        self.assertEqual(delivery["status"], "routine_reply_idempotency_claim_failed")
        self.assertEqual(calls, [])

    def test_preclaim_chronology_change_blocks_claim_and_send(self):
        calls = []
        delivery = (
            sam_live_stock_runtime
            .deliver_sam_live_stock_routine_reply_if_enabled(
                {
                    "account_id": "147387",
                    "conversation_id": "2013",
                    "contact_id": "699428938",
                    "inbox_id": "96568",
                    "message_id": "INBOUND-A",
                    "content": "Hi",
                    "identity_provenance": verified_identity(
                        "2013", "699428938", "96568"
                    ),
                },
                {
                    "conversation_ownership": "AUTO_GENERAL",
                    "suggested_reply_text": "Hi! How can I help?",
                    "reply_source": "llm_auto_general_reply_draft",
                    "should_reply": True,
                    "llm_draft": {"used": True, "confidence": 0.99},
                    "specialist_lane_selected": False,
                    "specialist_tools_called": [],
                    "owner_escalation_required": False,
                },
                {"safe_to_send": True, "escalation_required": False},
                {
                    "SAM_AUTO_GENERAL_AUTOREPLY_ENABLED": "1",
                    "SAM_AUTO_GENERAL_CANARY_ENABLED": "1",
                    "SAM_AUTO_GENERAL_CANARY_CONVERSATION_ID": "2013",
                    "SAM_AUTO_GENERAL_CANARY_CONTACT_ID": "699428938",
                    "SAM_AUTO_GENERAL_CANARY_INBOX_ID": "96568",
                },
                preclaim_chronology_verifier=(
                    lambda *_args: {"allowed": False}
                ),
                delivery_claim=lambda *_args: calls.append("claim"),
                chatwoot_sender=lambda *_args: calls.append("send"),
            )
        )
        self.assertEqual(
            delivery["status"],
            "routine_reply_preclaim_chronology_changed",
        )
        self.assertEqual(calls, [])

    def test_auto_general_invalid_chronology_blocks_before_claim_or_send(self):
        for timestamp in (None, "malformed", "NaN", "Infinity", "-Infinity"):
            with self.subTest(timestamp=timestamp):
                calls = []
                delivery = sam_live_stock_runtime.deliver_sam_live_stock_routine_reply_if_enabled(
                    {
                        "conversation_id": "2013",
                        "contact_id": "699428938",
                        "inbox_id": "96568",
                        "content": "Hi",
                        "identity_provenance": verified_identity(
                            "2013", "699428938", "96568"
                        ),
                    },
                    {
                        "conversation_ownership": "AUTO_GENERAL",
                        "suggested_reply_text": "Hi! How can I help you today?",
                        "reply_source": "llm_auto_general_reply_draft",
                        "should_reply": True,
                        "llm_draft": {"used": True, "confidence": 0.99},
                        "specialist_lane_selected": False,
                        "specialist_tools_called": [],
                        "owner_escalation_required": False,
                        "read_context": {
                            "chatwoot_history": {
                                "chronology_evidence_complete": False,
                            },
                            "context_errors": [{
                                "status": "chatwoot_chronology_evidence_unavailable",
                                "reason": "chronology_timestamp_unavailable",
                                "sanitized_timestamp_shape": type(timestamp).__name__,
                            }],
                        },
                    },
                    {"safe_to_send": True, "escalation_required": False},
                    {
                        "SAM_AUTO_GENERAL_AUTOREPLY_ENABLED": "1",
                        "SAM_AUTO_GENERAL_CANARY_ENABLED": "1",
                        "SAM_AUTO_GENERAL_CANARY_CONVERSATION_ID": "2013",
                        "SAM_AUTO_GENERAL_CANARY_CONTACT_ID": "699428938",
                        "SAM_AUTO_GENERAL_CANARY_INBOX_ID": "96568",
                    },
                    delivery_claim=lambda *_args: calls.append("claim"),
                    chatwoot_sender=lambda *_args: calls.append("send"),
                    delivery_evidence_recorder=lambda *_args: calls.append(
                        "evidence"
                    ),
                )
                self.assertEqual(
                    delivery["status"],
                    "routine_reply_chronology_evidence_unavailable",
                )
                self.assertFalse(delivery["attempted"])
                self.assertFalse(delivery["sent"])
                self.assertEqual(calls, [])

    def test_production_message_759342561_recovers_authoritative_conversation_inbox(self):
        result, status = sam_live_stock_runtime.handle_sam_live_stock_chatwoot_inbound(
            inbound_payload(
                id=759342561,
                content="Hi",
                conversation={"id": 2004, "channel_type": "Channel::Whatsapp"},
                sender={"id": 699428938, "name": "Charl"},
            ),
            environ={},
            conversation_history_loader=lambda *_args: {"success": True, "messages": []},
            conversation_identity_loader=lambda conversation_id, *_args: {
                "success": True,
                "status": "chatwoot_conversation_identity_loaded",
                "conversation_id": str(conversation_id),
                "contact_id": "699428938",
                "inbox_id": "96568",
            },
            availability_loader=lambda: self.fail("general greeting called availability"),
            intake_context_loader=lambda *_args: self.fail("general greeting called intake"),
        )

        decision = result["sam_decision"]
        provenance = decision["inbound"]["identity_provenance"]
        self.assertEqual(status, 200)
        self.assertEqual(
            (
                decision["inbound"]["conversation_id"],
                decision["inbound"]["contact_id"],
                decision["inbound"]["inbox_id"],
            ),
            ("2004", "699428938", "96568"),
        )
        self.assertEqual(provenance["status"], "identity_verified")
        self.assertTrue(provenance["authoritative_conversation_lookup"]["success"])
        self.assertFalse(provenance["configured_allowlist_used_as_evidence"])

    def test_webhook_and_conversation_identity_agreement_and_conflict_fail_closed(self):
        parsed = sam_live_stock_runtime.parse_chatwoot_inbound(
            inbound_payload(
                content="Hi",
                conversation={
                    "id": 2004,
                    "inbox_id": 96568,
                    "inbox": {"id": 96568, "channel_type": "Channel::Whatsapp"},
                },
                sender={"id": 699428938, "name": "Charl"},
            )
        )
        agreed = sam_live_stock_runtime.resolve_sam_general_inbound_identity(
            parsed,
            {},
            environ={},
            conversation_identity_loader=lambda *_args: {
                "success": True,
                "status": "loaded",
                "conversation_id": "2004",
                "contact_id": "699428938",
                "inbox_id": "96568",
            },
        )
        conflicted = sam_live_stock_runtime.resolve_sam_general_inbound_identity(
            parsed,
            {},
            environ={},
            conversation_identity_loader=lambda *_args: {
                "success": True,
                "status": "loaded",
                "conversation_id": "2004",
                "contact_id": "699428938",
                "inbox_id": "DIFFERENT",
            },
        )

        self.assertEqual(agreed["inbox_id"], "96568")
        self.assertEqual(agreed["identity_provenance"]["status"], "identity_verified")
        self.assertEqual(conflicted["inbox_id"], "")
        self.assertEqual(conflicted["identity_provenance"]["status"], "identity_conflict")
        self.assertTrue(conflicted["identity_provenance"]["conflicts"]["inbox_id"])

    def test_inbox_unavailable_or_configured_allowlist_alone_is_not_evidence(self):
        parsed = sam_live_stock_runtime.parse_chatwoot_inbound(
            inbound_payload(
                content="Hi",
                conversation={"id": 2004, "channel_type": "Channel::Whatsapp"},
                sender={"id": 699428938, "name": "Charl"},
            )
        )
        unresolved = sam_live_stock_runtime.resolve_sam_general_inbound_identity(
            parsed,
            {},
            environ={
                "SAM_AUTO_GENERAL_CANARY_INBOX_ID": "96568",
            },
            conversation_identity_loader=lambda *_args: {
                "success": False,
                "status": "unavailable",
            },
        )
        self.assertEqual(unresolved["inbox_id"], "")
        self.assertEqual(
            unresolved["identity_provenance"]["status"],
            "identity_evidence_unavailable",
        )
        self.assertFalse(
            unresolved["identity_provenance"]["configured_allowlist_used_as_evidence"]
        )

    def test_auto_general_low_risk_confidence_and_claim_boundaries(self):
        source = {
            "SAM_AUTO_GENERAL_AUTOREPLY_ENABLED": "1",
            "SAM_AUTO_GENERAL_CANARY_ENABLED": "1",
            "SAM_AUTO_GENERAL_CANARY_CONVERSATION_ID": "2004",
            "SAM_AUTO_GENERAL_CANARY_CONTACT_ID": "699428938",
            "SAM_AUTO_GENERAL_CANARY_INBOX_ID": "96568",
        }
        inbound = {
            "conversation_id": "2004",
            "contact_id": "699428938",
            "inbox_id": "96568",
            "content": "Hi",
            "identity_provenance": verified_identity("2004", "699428938", "96568"),
        }
        review = {"safe_to_send": True, "escalation_required": False}

        def decision(reply, confidence, **overrides):
            value = {
                "conversation_ownership": "AUTO_GENERAL",
                "suggested_reply_text": reply,
                "reply_source": "llm_auto_general_reply_draft",
                "should_reply": True,
                "llm_draft": {"used": True, "confidence": confidence},
                "clarification_asked": False,
                "specialist_lane_selected": False,
                "specialist_tools_called": [],
                "owner_escalation_required": False,
                "creates_order": False,
                "creates_quote": False,
                "reserves_stock": False,
                "changes_stock": False,
                "writes_farm_data": False,
                "confirms_payment": False,
                "assigns_animal": False,
                "writes_order_intake": False,
                "writes_sales_transaction": False,
            }
            value.update(overrides)
            return value

        eligible = sam_live_stock_runtime._auto_general_canary_evaluation(
            inbound,
            decision("Hi Charl! How can I help you today?", 0.95),
            review,
            source,
        )
        acknowledgement = sam_live_stock_runtime._auto_general_canary_evaluation(
            {**inbound, "content": "Thanks"},
            decision("You are welcome!", 0.95),
            review,
            source,
        )
        clarification = sam_live_stock_runtime._auto_general_canary_evaluation(
            {**inbound, "content": "Can I get more info on this?"},
            decision(
                "Of course. What would you like to know more about?",
                0.95,
                clarification_asked=True,
            ),
            review,
            source,
        )
        low = sam_live_stock_runtime._auto_general_canary_evaluation(
            inbound,
            decision("Hi Charl! How can I help you today?", 0.94),
            review,
            source,
        )
        factual = sam_live_stock_runtime._auto_general_canary_evaluation(
            inbound,
            decision("Hi! We have 5 piglets available for R450.", 0.99),
            review,
            source,
        )
        specialist = sam_live_stock_runtime._auto_general_canary_evaluation(
            inbound,
            decision(
                "Hi! How can I help you today?",
                0.95,
                conversation_ownership="AUTO_SPECIALIST",
                specialist_lane_selected=True,
                specialist_tools_called=["herdmaster"],
            ),
            review,
            source,
        )

        self.assertTrue(eligible["allowed"])
        self.assertEqual(eligible["response_class"], "greeting")
        self.assertEqual(eligible["minimum_llm_confidence"], 0.95)
        self.assertTrue(acknowledgement["allowed"])
        self.assertEqual(acknowledgement["response_class"], "acknowledgement")
        self.assertTrue(clarification["allowed"])
        self.assertEqual(clarification["response_class"], "clarification")
        self.assertFalse(low["allowed"])
        self.assertEqual(low["status"], "auto_general_canary_llm_confidence_blocked")
        self.assertFalse(factual["allowed"])
        self.assertEqual(factual["status"], "auto_general_canary_factual_claim_blocked")
        self.assertFalse(specialist["allowed"])
        self.assertEqual(specialist["minimum_llm_confidence"], 0.96)

    def test_auto_general_095_exact_claim_send_confirmed_and_replay_withheld(self):
        source = {
            "SAM_AUTO_GENERAL_AUTOREPLY_ENABLED": "1",
            "SAM_AUTO_GENERAL_CANARY_ENABLED": "1",
            "SAM_AUTO_GENERAL_CANARY_CONVERSATION_ID": "2004",
            "SAM_AUTO_GENERAL_CANARY_CONTACT_ID": "699428938",
            "SAM_AUTO_GENERAL_CANARY_INBOX_ID": "96568",
        }
        inbound = {
            "conversation_id": "2004",
            "contact_id": "699428938",
            "inbox_id": "96568",
            "content": "Hi",
            "identity_provenance": verified_identity("2004", "699428938", "96568"),
        }
        decision = {
            "conversation_ownership": "AUTO_GENERAL",
            "suggested_reply_text": "Hi Charl! How can I help you today?",
            "reply_source": "llm_auto_general_reply_draft",
            "should_reply": True,
            "llm_draft": {"used": True, "confidence": 0.95},
            "clarification_asked": False,
            "specialist_lane_selected": False,
            "specialist_tools_called": [],
            "owner_escalation_required": False,
            "creates_order": False,
            "creates_quote": False,
            "reserves_stock": False,
            "changes_stock": False,
            "writes_farm_data": False,
            "confirms_payment": False,
            "assigns_animal": False,
            "writes_order_intake": False,
            "writes_sales_transaction": False,
        }
        review = {"safe_to_send": True, "escalation_required": False}
        created = True
        order = []

        def claim(*_args):
            order.append("claim")
            return {
                "success": True,
                "created": created,
                "review_event_id": "CLAIM-2004",
                "prior_delivery_state": "chatwoot_accepted_unverified" if not created else "",
            }

        first = sam_live_stock_runtime.deliver_sam_live_stock_routine_reply_if_enabled(
            inbound,
            decision,
            review,
            source,
            delivery_claim=claim,
            chatwoot_sender=lambda *_args: order.append("send") or {"status_code": 200, "body": {"id": 1, "status": "sent"}},
            delivery_evidence_recorder=lambda _claim, outcome: (
                order.append("evidence:" + outcome["delivery_state"])
                or {"success": True, "status": "recorded"}
            ),
        )
        created = False
        replay = sam_live_stock_runtime.deliver_sam_live_stock_routine_reply_if_enabled(
            inbound,
            decision,
            review,
            source,
            delivery_claim=claim,
            chatwoot_sender=lambda *_args: order.append("duplicate_send"),
        )

        self.assertEqual(
            order,
            ["claim", "send", "evidence:chatwoot_accepted_unverified", "claim"],
        )
        self.assertFalse(first["sent"])
        self.assertTrue(first["chatwoot_accepted"])
        self.assertEqual(
            first["delivery_outcome"]["delivery_state"],
            "chatwoot_accepted_unverified",
        )
        self.assertEqual(replay["status"], "routine_reply_duplicate_withheld")

    def test_auto_general_disabled_and_wrong_allowlist_remain_actionable_without_tools(self):
        payload = inbound_payload(
            content="Hello! Can I get more info on this?",
            conversation={"id": 1994, "inbox": {"id": 77, "channel_type": "Channel::FacebookPage"}},
            content_attributes={
                "source_id": "facebook-post-ms-piggy",
                "source_name": "Ms. Piggy and her litter of piglets",
            },
        )
        sources = (
            {},
            {
                "SAM_LIVE_STOCK_BACKEND_LLM_ENABLED": "1",
                "SAM_LIVE_STOCK_BACKEND_LLM_MODEL": "test-model",
                "OPENAI_API_KEY": "test-key",
                "SAM_AUTO_GENERAL_AUTOREPLY_ENABLED": "1",
                "SAM_AUTO_GENERAL_CANARY_ENABLED": "1",
                "SAM_AUTO_GENERAL_CANARY_CONVERSATION_ID": "different",
                "SAM_AUTO_GENERAL_CANARY_CONTACT_ID": "99",
                "SAM_AUTO_GENERAL_CANARY_INBOX_ID": "77",
            },
        )
        for source in sources:
            with self.subTest(source=source):
                sends = []
                result, status_code = sam_live_stock_runtime.handle_sam_live_stock_chatwoot_inbound(
                    payload,
                    environ=source,
                    intake_context_loader=lambda *_args: self.fail("general message called intake"),
                    conversation_history_loader=lambda *_args: {"success": True, "messages": []},
                    availability_loader=lambda: self.fail("general message called availability"),
                    llm_drafter=lambda *_args: {
                        "reply_text": "Hi Henry! What would you like to know about Ms. Piggy and her litter of piglets?",
                        "confidence": 0.99,
                    },
                    chatwoot_sender=lambda *_args: sends.append(True),
                )
                decision = result["sam_decision"]
                self.assertEqual(status_code, 200)
                self.assertEqual(decision["conversation_ownership"], "AUTO_GENERAL")
                self.assertEqual(decision["specialist_tools_called"], [])
                self.assertEqual(decision["reason"], "routine_reply_waiting_for_owner")
                self.assertTrue(decision["owner_action_required"])
                self.assertFalse(decision["handled_autonomously"])
                self.assertFalse(result["sent"])
                self.assertEqual(sends, [])

    def test_attempt_claimed_replay_is_ambiguous_owner_visible_without_resend(self):
        decision = {
            "conversation_ownership": "AUTO_GENERAL",
            "handled_autonomously": True,
        }
        sam_live_stock_runtime._apply_auto_general_delivery_transition(
            decision,
            {
                "attempted": False,
                "sent": False,
                "status": "routine_reply_duplicate_withheld",
                "claim": {"prior_delivery_state": "attempt_claimed"},
            },
        )
        self.assertEqual(decision["reason"], "routine_reply_delivery_ambiguous")
        self.assertTrue(decision["owner_action_required"])
        self.assertFalse(decision["customer_send_confirmed"])
        self.assertFalse(decision["handled_autonomously"])

    def test_auto_general_authorized_send_replay_and_ambiguous_outcome_transitions(self):
        payload = inbound_payload(
            content="Hi",
            conversation={"id": 2401, "inbox": {"id": 77, "channel_type": "Channel::Whatsapp"}},
        )
        source = {
            "SAM_LIVE_STOCK_BACKEND_LLM_ENABLED": "1",
            "SAM_LIVE_STOCK_BACKEND_LLM_MODEL": "test-model",
            "OPENAI_API_KEY": "test-key",
            "SAM_AUTO_GENERAL_AUTOREPLY_ENABLED": "1",
            "SAM_AUTO_GENERAL_CANARY_ENABLED": "1",
            "SAM_AUTO_GENERAL_CANARY_CONVERSATION_ID": "2401",
            "SAM_AUTO_GENERAL_CANARY_CONTACT_ID": "99",
            "SAM_AUTO_GENERAL_CANARY_INBOX_ID": "77",
        }
        created = True
        sends = []
        evidence = []

        def claim(*_args):
            return {
                "success": True,
                "created": created,
                "review_event_id": "GENERAL-CLAIM",
                "prior_delivery_confirmed": not created,
                "prior_delivery_state": "provider_delivered" if not created else "",
            }

        def run(sender):
            return sam_live_stock_runtime.handle_sam_live_stock_chatwoot_inbound(
                payload,
                environ=source,
                intake_context_loader=lambda *_args: self.fail("general greeting called intake"),
                conversation_history_loader=lambda *_args: {"success": True, "messages": []},
                availability_loader=lambda: self.fail("general greeting called availability"),
                llm_drafter=lambda *_args: {
                    "reply_text": "Hi! How can I help you today?",
                    "confidence": 0.99,
                },
                routine_delivery_claim=claim,
                chatwoot_sender=sender,
                routine_delivery_evidence_recorder=lambda _claim, outcome: (
                    evidence.append(outcome.copy()) or {"success": True, "status": "recorded"}
                ),
            )

        result, _ = run(lambda *_args: sends.append("sent") or {"status_code": 200, "body": {"id": 1, "status": "delivered"}})
        decision = result["sam_decision"]
        self.assertEqual(sends, ["sent"])
        self.assertTrue(result["sent"])
        self.assertTrue(decision["handled_autonomously"])
        self.assertFalse(decision["owner_escalation_required"])
        self.assertEqual(decision["reason"], "routine_reply_confirmed_delivered")
        self.assertEqual(evidence[-1]["delivery_state"], "provider_delivered")

        created = False
        replay, _ = run(lambda *_args: sends.append("duplicate"))
        self.assertEqual(sends, ["sent"])
        self.assertFalse(replay["sent"])
        self.assertEqual(
            replay["sam_decision"]["reason"],
            "routine_reply_confirmed_delivered",
        )

        created = True

        def ambiguous_sender(*_args):
            sends.append("ambiguous")
            raise TimeoutError("confirmation unavailable")

        ambiguous, _ = run(ambiguous_sender)
        self.assertEqual(sends, ["sent", "ambiguous"])
        self.assertFalse(ambiguous["sent"])
        self.assertEqual(
            ambiguous["sam_decision"]["reason"],
            "routine_reply_delivery_ambiguous",
        )
        self.assertTrue(ambiguous["sam_decision"]["owner_action_required"])
        self.assertTrue(
            ambiguous["sam_decision"]["routine_reply_delivery"]["automatic_retry_prohibited"]
        )
        self.assertEqual(evidence[-1]["delivery_state"], "provider_outcome_ambiguous")

    def test_persisted_default_sentinels_do_not_satisfy_customer_qualification(self):
        prior = sam_live_stock_runtime._prior_context_from_intake({
            "success": True,
            "known_fields": {
                "collection_location": "Any",
                "collection_time_text": "Unknown",
            },
            "items": [{
                "status": "active",
                "quantity": 1,
                "category": "Unknown",
                "weight_range": "defaulted",
                "sex": "Any",
            }],
        })

        self.assertEqual(prior["interest"]["quantity"], 1)
        self.assertEqual(prior["interest"]["category"], "")
        self.assertEqual(prior["interest"]["weight_range"], "")
        self.assertEqual(prior["interest"]["sex"], "")
        self.assertEqual(prior["interest"]["location"], "")
        self.assertEqual(prior["interest"]["timing"], "")

    def test_customer_chronology_overrides_persisted_projection_without_repeating_answers(self):
        history = {
            "success": True,
            "messages": [
                {
                    "id": 763629726,
                    "message_type": 0,
                    "private": False,
                    "created_at": 1785220000,
                    "content": "I want one pig",
                },
                {
                    "id": 764070982,
                    "message_type": 1,
                    "private": False,
                    "created_at": 1785249000,
                    "content": (
                        "We offer pigs in different sizes. Which size would "
                        "suit you?"
                    ),
                },
                {
                    "id": 764166766,
                    "message_type": 0,
                    "private": False,
                    "created_at": 1785253248,
                    "content": "And weaned piglets",
                },
            ],
        }
        result, status = sam_live_stock_runtime.handle_sam_live_stock_chatwoot_inbound(
            inbound_payload(
                content="And weaned piglets",
                id=764166766,
                created_at=1785253248,
                conversation={
                    "id": 2068,
                    "inbox": {
                        "id": 96568,
                        "channel_type": "Channel::Whatsapp",
                    },
                    "meta": {"sender": {"id": 984794646}},
                },
                sender={"id": 984794646, "name": "Leonello"},
                account={"id": 147387},
            ),
            intake_context_loader=lambda _conversation_id: {
                "success": True,
                "conversation_id": "2068",
                "known_fields": {"collection_location": "Any"},
                "items": [{
                    "status": "active",
                    "quantity": 1,
                    "category": "Piglet",
                    "weight_range": "5_to_6_Kg",
                    "sex": "Any",
                }],
            },
            conversation_history_loader=lambda *_args: history,
            availability_loader=lambda: [],
            environ={"SAM_LIVE_STOCK_BACKEND_LLM_ENABLED": "0"},
        )

        self.assertEqual(status, 200)
        decision = result["sam_decision"]
        self.assertEqual(decision["facts"]["category"], "weaner")
        self.assertEqual(decision["facts"]["quantity"], 1)
        self.assertEqual(decision["facts"]["sex"], "")
        self.assertEqual(decision["facts"]["weight_range"], "")
        self.assertIn("male, female, or either", decision["suggested_reply_text"])
        self.assertNotIn("Which size", decision["suggested_reply_text"])
        self.assertNotIn("how many", decision["suggested_reply_text"])
        self.assertNotIn("checking the current livestock availability", decision["suggested_reply_text"])
        self.assertFalse(result["sent"])
        self.assertFalse(decision["sends_customer_message"])
        self.assertFalse(decision["creates_order"])
        self.assertFalse(decision["reserves_stock"])
        self.assertFalse(decision["changes_stock"])

    def test_explicit_customer_either_remains_a_supplied_sex_preference(self):
        for message in (
            "I need two growing pigs; either is fine.",
            "Either male or female is fine.",
            "Male or female, no preference.",
        ):
            with self.subTest(message=message):
                facts = sam_live_stock_runtime.extract_live_stock_facts(
                    message, {"content": message}
                )
                self.assertEqual(facts["sex"], "any")
                guidance = sam_live_stock_runtime.build_live_stock_customer_guidance(
                    {"content": message}, facts
                )
                self.assertNotIn(
                    "male, female, or either",
                    guidance.get("reply_text") or "",
                )
        category_flexible = sam_live_stock_runtime.extract_live_stock_facts(
            "Either weaners or growers, female please.",
            {"content": "Either weaners or growers, female please."},
        )
        self.assertEqual(category_flexible["sex"], "female")
        size_flexible = sam_live_stock_runtime.extract_live_stock_facts(
            "Either size is fine, but females only.",
            {"content": "Either size is fine, but females only."},
        )
        self.assertEqual(size_flexible["sex"], "female")

    def test_intake_normalizers_never_manufacture_customer_preferences(self):
        self.assertEqual(sam_live_stock_runtime._normal_intake_sex("Unknown"), "")
        self.assertEqual(sam_live_stock_runtime._normal_intake_sex(""), "")
        self.assertEqual(sam_live_stock_runtime._normal_intake_location("Unknown"), "")
        self.assertEqual(
            sam_live_stock_runtime._normal_intake_weight_range("", "Weaner"),
            "",
        )

    def test_historical_category_default_weight_does_not_become_customer_evidence(self):
        prior = sam_live_stock_runtime._prior_context_from_intake({
            "known_fields": {},
            "items": [{
                "status": "active",
                "quantity": 1,
                "category": "Piglet",
                "weight_range": "5_to_6_Kg",
                "sex": "Any",
            }],
        })
        self.assertEqual(prior["interest"]["quantity"], 1)
        self.assertEqual(prior["interest"]["category"], "Piglet")
        self.assertEqual(prior["interest"]["weight_range"], "")
        self.assertEqual(prior["interest"]["sex"], "")

    def test_one_big_retains_quantity_while_asking_customer_friendly_size(self):
        facts = sam_live_stock_runtime.extract_live_stock_facts(
            "I want one big how much",
            {"content": "I want one big how much"},
        )
        self.assertEqual(facts["quantity"], 1)
        guidance = sam_live_stock_runtime.build_live_stock_customer_guidance(
            {"content": "I want one big how much"},
            facts,
        )
        self.assertNotIn("how many", guidance["reply_text"])

    def test_location_question_answers_supported_fact_before_sales_guidance(self):
        packet = sam_live_stock_runtime.build_live_stock_customer_guidance(
            {"content": "Where are you located?"},
            {
                "sales_lane": "live_stock_sales",
                "message_intent": "location_question",
                "category": "",
                "quantity": 3,
                "sex": "",
            },
        )
        self.assertFalse(packet["applicable"])

    def test_standalone_flexible_sex_reply_does_not_manufacture_livestock_context(self):
        for message in ("Either is fine", "No preference", "Doesn't matter"):
            with self.subTest(message=message):
                facts = sam_live_stock_runtime.extract_live_stock_facts(
                    message, {"content": message}
                )
                self.assertFalse(
                    sam_live_stock_runtime._looks_like_customer_qualification_answer(
                        message,
                        facts,
                        context_packet={"chatwoot_history_messages": []},
                    )
                )

    def test_bound_sex_only_answer_stays_on_livestock_path(self):
        message = "Either male or female is fine"
        facts = sam_live_stock_runtime.extract_live_stock_facts(
            message, {"content": message}
        )
        self.assertTrue(
            sam_live_stock_runtime._looks_like_customer_qualification_answer(
                message,
                facts,
                context_packet={
                    "chatwoot_history": {
                        "chronology_evidence_complete": True,
                    },
                    "chatwoot_history_messages": [{
                        "speaker": "farm",
                        "content": "Would you prefer a male, female, or either?",
                    }],
                },
            )
        )

    def test_out_of_order_history_uses_newest_customer_qualification(self):
        inbound = {"message_id": "current"}
        history = {
            "success": True,
            "messages": [
                {
                    "id": "newer",
                    "message_type": 0,
                    "created_at": "2026-07-28T10:00:00+00:00",
                    "content": "I prefer females",
                },
                {
                    "id": "older",
                    "message_type": 0,
                    "created_at": "2026-07-28T09:00:00Z",
                    "content": "I prefer males",
                },
            ],
        }
        prior = sam_live_stock_runtime._prior_context_from_chatwoot_history(
            history, inbound
        )
        self.assertEqual(prior["interest"]["sex"], "female")

    def test_malformed_timestamp_fails_closed_instead_of_reordering_chronology(self):
        history = {
            "success": True,
            "messages": [
                {
                    "id": "newer",
                    "message_type": 0,
                    "created_at": 1785253248,
                    "content": "I prefer females",
                },
                {
                    "id": "malformed-replay",
                    "message_type": 0,
                    "created_at": "not-a-timestamp",
                    "content": "I prefer males",
                },
            ],
        }
        prior = sam_live_stock_runtime._prior_context_from_chatwoot_history(
            history, {"message_id": "current"}
        )
        self.assertFalse(prior["evidence_complete"])
        self.assertEqual(prior["reason"], "chronology_timestamp_unavailable")
        self.assertEqual(prior["interest"], {})

    def test_non_finite_history_timestamps_fail_closed(self):
        for timestamp in (
            "NaN",
            "Infinity",
            "-Infinity",
            float("nan"),
            float("inf"),
            float("-inf"),
        ):
            with self.subTest(timestamp=repr(timestamp)):
                prior = sam_live_stock_runtime._prior_context_from_chatwoot_history(
                    {
                        "success": True,
                        "messages": [{
                            "id": "bad-time",
                            "message_type": 0,
                            "created_at": timestamp,
                            "content": "I prefer males",
                        }],
                    },
                    {"message_id": "current"},
                )
                self.assertFalse(prior["evidence_complete"])
                self.assertEqual(
                    prior["reason"], "chronology_timestamp_unavailable"
                )
                self.assertEqual(prior["interest"], {})

    def test_malformed_history_timestamp_blocks_intake_and_customer_send(self):
        calls = {"intake": 0, "send": 0}
        result, status = sam_live_stock_runtime.handle_sam_live_stock_chatwoot_inbound(
            inbound_payload(
                id=9002,
                created_at=1785254000,
                content="I need female piglets",
            ),
            environ={
                sam_live_stock_runtime.INTAKE_WRITE_ENABLED_ENV: "1",
                "SAM_SALES_LEVEL1_ENABLED": "1",
                "SAM_SALES_LEVEL1_LIVESTOCK_ENABLED": "1",
            },
            intake_context_loader=lambda _conversation_id: {
                "success": True,
                "known_fields": {},
                "items": [],
            },
            conversation_history_loader=lambda *_args: {
                "success": True,
                "messages": [{
                    "id": 9001,
                    "message_type": 0,
                    "created_at": "malformed",
                    "content": "I need one pig",
                }],
            },
            availability_loader=lambda: [],
            intake_writer=lambda _payload: calls.__setitem__(
                "intake", calls["intake"] + 1
            ),
            chatwoot_sender=lambda *_args: calls.__setitem__(
                "send", calls["send"] + 1
            ),
        )
        self.assertEqual(status, 200)
        decision = result["sam_decision"]
        self.assertIn("read_context_error", decision["blockers"])
        self.assertNotIn("intake_write", decision)
        self.assertFalse(result["sent"])
        self.assertEqual(calls, {"intake": 0, "send": 0})

    def test_non_finite_history_timestamp_blocks_intake_and_customer_send(self):
        for timestamp in ("NaN", "Infinity", "-Infinity"):
            with self.subTest(timestamp=timestamp):
                calls = {"intake": 0, "send": 0}
                result, status = sam_live_stock_runtime.handle_sam_live_stock_chatwoot_inbound(
                    inbound_payload(
                        id=9102,
                        created_at=1785255000,
                        content="I need female piglets",
                    ),
                    environ={
                        sam_live_stock_runtime.INTAKE_WRITE_ENABLED_ENV: "1",
                        "SAM_SALES_LEVEL1_ENABLED": "1",
                        "SAM_SALES_LEVEL1_LIVESTOCK_ENABLED": "1",
                    },
                    intake_context_loader=lambda _conversation_id: {
                        "success": True,
                        "known_fields": {},
                        "items": [],
                    },
                    conversation_history_loader=lambda *_args: {
                        "success": True,
                        "messages": [{
                            "id": 9101,
                            "message_type": 0,
                            "created_at": timestamp,
                            "content": "I need one pig",
                        }],
                    },
                    availability_loader=lambda: [],
                    intake_writer=lambda _payload: calls.__setitem__(
                        "intake", calls["intake"] + 1
                    ),
                    chatwoot_sender=lambda *_args: calls.__setitem__(
                        "send", calls["send"] + 1
                    ),
                )
                self.assertEqual(status, 200)
                self.assertIn("read_context_error", result["sam_decision"]["blockers"])
                self.assertFalse(result["sent"])
                self.assertEqual(calls, {"intake": 0, "send": 0})


if __name__ == "__main__":
    unittest.main()
