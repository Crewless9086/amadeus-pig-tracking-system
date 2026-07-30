from datetime import datetime, timezone

from modules.sales.sam_livestock_offer_loop import (
    _future_reassessment_date,
    build_canonical_livestock_offer,
    validate_customer_livestock_reply,
)


def _packet(content="I need pigs", facts=None, **overrides):
    inbound = {
        "account_id": "147387",
        "inbox_id": "96568",
        "contact_id": "contact-1",
        "conversation_id": "conversation-1",
        "message_id": "inbound-1",
        "content": content,
    }
    base_facts = {
        "sales_lane": "live_stock_sales",
        "category": "Weaner Piglets",
        "weight_range": "7_to_19_kg",
        "quantity": 5,
        "sex": "mixture",
        "timing": "10 August",
        "location": "Riversdale",
    }
    base_facts.update(facts or {})
    values = {
        "inbound": inbound,
        "facts": base_facts,
        "chronology": [{"id": "inbound-1", "message_type": 0, "content": content}],
        "availability": {
            "success": True,
            "evidence_complete": True,
            "observation_timestamp": datetime.now(timezone.utc).isoformat(),
            "latest_weight_date": "2026-07-27",
            "oldest_weight_age_days": 3,
        },
        "match_packet": {},
        "price_packet": {},
    }
    values.update(overrides)
    return build_canonical_livestock_offer(**values)


def test_conversation_1338_regression_retains_all_known_facts_and_never_asks_generic_detail():
    result = _packet("If we can have the piglets on the 10th please")
    assert result["missing_fields"] == []
    assert "What detail should I note" not in result["customer_reply"]
    assert "where" not in result["customer_reply"].lower()
    assert "how many" not in result["customer_reply"].lower()


def test_exact_content_binding_normalizes_provider_whitespace_only():
    result = _packet(
        "I need 4 females and one male.",
        chronology=[{
            "id": "inbound-1",
            "message_type": 0,
            "content": "I need 4 females\r\nand   one male.",
        }],
    )

    assert "latest_inbound_content_mismatch" not in result["evidence_errors"]


def test_quantity_is_the_only_question_when_only_quantity_is_missing():
    result = _packet(facts={"quantity": ""})
    assert result["response_kind"] == "qualification"
    assert result["customer_reply"] == "How many weaned piglets (about 7–19 kg) would you like?"
    assert result["authority"]["asked_fields"] == ["quantity"]


def test_location_and_timing_are_asked_sequentially_not_as_form():
    result = _packet(facts={"timing": "", "location": ""})
    assert result["customer_reply"] == "When would you ideally need them?"
    assert result["authority"]["asked_fields"] == ["timing"]


def test_delivery_is_one_protected_exception_and_never_promises_or_offers_farm_collection():
    result = _packet("Can you deliver to Riversdale?")
    assert result["response_kind"] == "protected_delivery_request"
    assert result["owner_exception"]["type"] == "livestock_delivery_decision"
    assert "Riversdale or Albertinia" in result["customer_reply"]
    assert "collection from the farm" not in result["customer_reply"].lower()


def test_exact_match_has_unit_price_subtotal_and_total_without_reservation():
    result = _packet(
        match_packet={
            "complete_fulfillment": True,
            "exact_match_count": 5,
            "matched_sample": [{} for _ in range(5)],
        },
        price_packet={
            "can_answer_price": True,
            "unit_price": 600,
            "estimated_total": 3000,
            "pricing": {"pricing_id": "P15", "source": "supabase"},
        },
    )
    assert result["response_kind"] == "exact_supported_offer"
    assert "R600.00 each" in result["customer_reply"]
    assert "subtotal of R3,000.00" in result["customer_reply"]
    assert "not a reservation" in result["customer_reply"]


def test_oversupplied_exact_match_uses_requested_selected_quantity():
    result = _packet(
        match_packet={
            "complete_fulfillment": True,
            "exact_match_count": 10,
            "matched_sample": [{} for _ in range(5)],
        },
        price_packet={
            "can_answer_price": True,
            "unit_price": 600,
            "estimated_total": 3000,
            "pricing": {"pricing_id": "P15", "source": "supabase"},
        },
    )
    assert result["response_kind"] == "exact_supported_offer"
    assert "5 weaned piglets" in result["customer_reply"]


def test_explicit_any_sex_is_retained_and_not_reasked():
    result = _packet(facts={"sex": "any"})
    assert "sex" not in result["missing_fields"]
    assert "male" not in result["customer_reply"].lower()
    assert "female" not in result["customer_reply"].lower()


def test_protected_quote_or_order_packet_cannot_authorize_ordinary_offer():
    result = _packet(
        protected_decisions=[{
            "type": "protected_quote",
            "decision_required": "Owner must approve the quote.",
        }],
        match_packet={
            "complete_fulfillment": True,
            "exact_match_count": 5,
            "matched_sample": [{} for _ in range(5)],
        },
        price_packet={
            "can_answer_price": True,
            "unit_price": 600,
            "estimated_total": 3000,
            "pricing": {"pricing_id": "P15", "source": "supabase"},
        },
    )
    assert result["response_kind"] == "protected_owner_decision"
    assert result["should_reply"] is False
    assert result["owner_exception"]["type"] == "livestock_protected_decision"


def test_protected_packet_cannot_fall_back_to_otherwise_valid_proposed_offer():
    result = _packet(
        protected_decisions=[{
            "type": "protected_quote",
            "decision_required": "Owner must approve the quote.",
        }],
        proposed_reply="Would you like me to prepare the quote for owner review?",
    )
    assert result["response_kind"] == "protected_owner_decision"
    assert result["should_reply"] is False
    assert result["proposed_candidate"]["accepted"] is True


def test_closest_alternative_calculates_each_subtotal_and_total():
    rows = [
        {
            "live_stock_sale_eligible": True,
            "evidence_complete": True,
            "latest_weight_date": "2026-07-27",
            "days_since_weight": 3,
            "alternative_rank": 1,
            "sale_category": "Weaner Piglets",
            "pricing": {"unit_price": 600, "pricing_id": "P1", "source": "supabase"},
        },
        {
            "live_stock_sale_eligible": True,
            "evidence_complete": True,
            "latest_weight_date": "2026-07-27",
            "days_since_weight": 3,
            "alternative_rank": 2,
            "sale_category": "Grower Pigs",
            "pricing": {"unit_price": 900, "pricing_id": "P2", "source": "supabase"},
        },
    ]
    result = _packet(
        facts={"quantity": 2},
        match_packet={"complete_fulfillment": False, "considered_sample": rows},
    )
    assert result["response_kind"] == "closest_supported_alternatives"
    assert "R600.00 each (R600.00)" in result["customer_reply"]
    assert "R900.00 each (R900.00)" in result["customer_reply"]
    assert "total R1,500.00" in result["customer_reply"]


def test_stale_weight_evidence_is_disclosed_proportionally():
    rows = [
        {
            "live_stock_sale_eligible": True,
            "evidence_complete": True,
            "latest_weight_date": "2026-07-27",
            "days_since_weight": 3,
            "alternative_rank": 1,
            "sale_category": "Weaner Piglets",
            "pricing": {"unit_price": 600, "pricing_id": "P1", "source": "supabase"},
        }
    ]
    result = _packet(
        facts={"quantity": 1},
        availability={
            "success": True,
            "evidence_complete": False,
            "observation_timestamp": "2026-07-28T10:00:00+00:00",
        },
        match_packet={"complete_fulfillment": False, "considered_sample": rows},
    )
    assert "latest weight evidence is dated" in result["customer_reply"]
    assert "current weights must be confirmed" in result["customer_reply"]


def test_acknowledgement_and_customer_silence_do_not_force_reply():
    assert _packet("Thank you")["should_reply"] is False
    assert _packet("👍")["should_reply"] is False


def test_global_authority_rejects_farm_collection_generic_fallback_and_delivery_promise():
    for reply, blocker in (
        ("Collection from the farm is standard.", "collection_or_pickup_claim_prohibited"),
        ("What detail should I note for the farm?", "context_blind_generic_question_prohibited"),
        ("We can deliver those pigs.", "delivery_commitment_prohibited"),
    ):
        result = validate_customer_livestock_reply(reply)
        assert result["allowed"] is False
        assert blocker in result["blockers"]


def test_farm_collection_cannot_hide_inside_valid_handover_wording():
    result = validate_customer_livestock_reply(
        "Collection from the farm is available; handover is in Riversdale or Albertinia."
    )

    assert result["allowed"] is False
    assert "collection_or_pickup_claim_prohibited" in result["blockers"]


def test_identity_and_latest_inbound_are_bound_before_composition():
    result = _packet(
        chronology=[{"id": "different-inbound", "message_type": 0, "content": "new"}]
    )
    assert result["should_reply"] is False
    assert result["response_kind"] == "identity_or_chronology_blocked"


def test_identity_error_cannot_fall_back_to_valid_legacy_candidate():
    result = _packet(
        chronology=[{"id": "outgoing-1", "message_type": 1, "content": "old"}],
        proposed_reply="When would you ideally need them?",
    )
    assert result["response_kind"] == "identity_or_chronology_blocked"
    assert result["should_reply"] is False
    assert result["customer_reply"] == ""


def test_owner_approved_exact_split_alternative_has_category_subtotals_and_total():
    rows = [
        *[
            {
                "pig_id": f"F{index}",
                "sex": "Female",
                "live_stock_sale_eligible": True,
                "evidence_complete": True,
                "latest_weight_date": "2026-07-27",
                "days_since_weight": 3,
                "alternative_rank": index,
                "sale_category": "Grower Pigs",
                "weight_band": "35_to_39_Kg",
                "pricing": {
                    "unit_price": 1400,
                    "pricing_id": "G35",
                    "source": "supabase",
                },
            }
            for index in range(1, 4)
        ],
        {
            "pig_id": "F4",
            "sex": "Female",
            "live_stock_sale_eligible": True,
            "evidence_complete": True,
            "latest_weight_date": "2026-07-27",
            "days_since_weight": 3,
            "alternative_rank": 4,
            "sale_category": "Finisher Pigs",
            "weight_band": "40_to_44_Kg",
            "pricing": {
                "unit_price": 1600,
                "pricing_id": "F40",
                "source": "supabase",
            },
        },
        {
            "pig_id": "M1",
            "sex": "Male",
            "live_stock_sale_eligible": True,
            "evidence_complete": True,
            "latest_weight_date": "2026-07-27",
            "days_since_weight": 3,
            "alternative_rank": 5,
            "sale_category": "Weaner Piglets",
            "weight_band": "15_to_19_Kg",
            "pricing": {
                "unit_price": 600,
                "pricing_id": "W15",
                "source": "supabase",
            },
        },
    ]
    result = _packet(
        facts={
            "sex": "split",
            "sex_split": {"female": 4, "male": 1},
            "weight_range": "around 19 kg",
        },
        match_packet={"complete_fulfillment": False, "considered_sample": rows}
    )
    assert result["response_kind"] == "closest_supported_alternatives"
    assert "3 females in the 35â€“39 kg category" in result["customer_reply"]
    assert "R1,400.00 each (R4,200.00)" in result["customer_reply"]
    assert "1 female in the 40â€“44 kg category" in result["customer_reply"]
    assert "R1,600.00 each (R1,600.00)" in result["customer_reply"]
    assert "1 male in the 15â€“19 kg category" in result["customer_reply"]
    assert "R600.00 each (R600.00)" in result["customer_reply"]
    assert "total R6,400.00" in result["customer_reply"]
    assert "4-female/1-male split is preserved" in result["customer_reply"]
    assert "different weight bands" in result["customer_reply"]


def test_fresh_match_timestamp_cannot_authorize_stale_alternative_rows():
    result = _packet(
        availability={
            "success": True,
            "evidence_complete": True,
            "eligible_evidence_complete": False,
            "observation_timestamp": datetime.now(timezone.utc).isoformat(),
            "latest_weight_date": "2026-06-01",
            "oldest_weight_age_days": 59,
        },
        match_packet={
            "complete_fulfillment": False,
            "considered_sample": [{
                "pig_id": "STALE",
                "sex": "Female",
                "live_stock_sale_eligible": True,
                "evidence_complete": True,
                "latest_weight_date": "2026-06-01",
                "days_since_weight": 59,
                "alternative_rank": 1,
                "sale_category": "Grower Pigs",
                "weight_band": "35_to_39_Kg",
                "pricing": {
                    "unit_price": 1400,
                    "pricing_id": "G35",
                    "source": "supabase",
                },
            }],
        },
    )

    assert result["response_kind"] == "evidence_bounded_progression"
    assert "R1,400" not in result["customer_reply"]
    assert "current sale-eligible" not in result["customer_reply"]


def test_generic_alternative_does_not_invent_which_constraint_differs():
    result = _packet(
        facts={"quantity": 1, "sex": "female"},
        match_packet={
            "complete_fulfillment": False,
            "considered_sample": [{
                "pig_id": "MALE-SAME-BAND",
                "sex": "Male",
                "live_stock_sale_eligible": True,
                "evidence_complete": True,
                "latest_weight_date": "2026-07-27",
                "days_since_weight": 3,
                "alternative_rank": 1,
                "sale_category": "Weaner Piglets",
                "weight_band": "7_to_19_Kg",
                "pricing": {
                    "unit_price": 600,
                    "pricing_id": "W7-19",
                    "source": "supabase",
                },
            }],
        },
    )

    assert result["response_kind"] == "closest_supported_alternatives"
    assert "exact requested combination" in result["customer_reply"]
    assert "differs from the requested weight" not in result["customer_reply"]


def test_insufficient_requested_sex_never_claims_split_is_preserved():
    rows = []
    for pig_id, sex, rank in (
        ("F1", "Female", 1),
        ("M1", "Male", 2),
        ("M2", "Male", 3),
    ):
        rows.append({
            "pig_id": pig_id,
            "sex": sex,
            "live_stock_sale_eligible": True,
            "evidence_complete": True,
            "latest_weight_date": "2026-07-27",
            "days_since_weight": 3,
            "alternative_rank": rank,
            "sale_category": "Grower Pigs",
            "weight_band": "20_to_24_Kg",
            "pricing": {
                "unit_price": 800,
                "pricing_id": "G20-24",
                "source": "supabase",
            },
        })
    result = _packet(
        facts={
            "quantity": 3,
            "sex": "split",
            "sex_split": {"female": 2, "male": 1},
        },
        match_packet={"complete_fulfillment": False, "considered_sample": rows},
    )

    assert result["response_kind"] == "closest_supported_alternatives"
    assert "split is preserved" not in result["customer_reply"]
    assert "exact requested combination" in result["customer_reply"]


def test_direct_price_question_answers_supported_price_before_smallest_missing_question():
    result = _packet(
        "How much are the 5 to 6 kg piglets?",
        facts={
            "category": "Young Piglets",
            "weight_range": "5_to_6_Kg",
            "quantity": "",
            "sex": "",
            "timing": "",
            "location": "",
        },
        price_packet={
            "can_answer_price": True,
            "unit_price": 400,
            "estimated_total": "",
            "requested_weight_range": "5_to_6_Kg",
            "pricing": {
                "pricing_id": "PRICE-5-6",
                "source": "supabase",
                "weight_band": "5_to_6_Kg",
            },
        },
    )

    assert result["response_kind"] == "supported_price_first"
    assert result["customer_reply"].startswith(
        "The current supported price for 5â€“6 kg live pigs is R400.00 each."
    )
    assert "How many small piglets" in result["customer_reply"]
    assert result["customer_reply"].count("?") == 1
    assert "Would you prefer" not in result["customer_reply"]


def test_returning_customer_partial_availability_keeps_known_facts_and_advances_once():
    rows = [{
        "pig_id": "PIG-ALT-1",
        "sex": "Female",
        "live_stock_sale_eligible": True,
        "evidence_complete": True,
        "latest_weight_date": "2026-07-27",
        "days_since_weight": 3,
        "alternative_rank": 1,
        "sale_category": "Grower Pigs",
        "weight_band": "20_to_24_Kg",
        "pricing": {
            "unit_price": 900,
            "pricing_id": "PRICE-20-24",
            "source": "supabase",
        },
    }]
    result = _packet(
        "Please keep the same four females and one male for the 10th.",
        facts={
            "sex": "split",
            "sex_split": {"female": 4, "male": 1},
            "timing": "10 August",
            "location": "Riversdale",
        },
        match_packet={"complete_fulfillment": False, "considered_sample": rows},
    )

    assert result["response_kind"] == "closest_supported_alternatives"
    assert result["retained_facts"]["quantity"] == 5
    assert result["retained_facts"]["sex_split"] == {"female": 4, "male": 1}
    assert result["retained_facts"]["location"] == "Riversdale"
    assert result["retained_facts"]["timing"] == "10 August"
    assert "How many" not in result["customer_reply"]
    assert "Which town" not in result["customer_reply"]


def test_owner_approved_future_date_becomes_weekly_reassessment_without_reasking():
    result = _packet(
        availability={
            "success": True,
            "evidence_complete": False,
            "observation_timestamp": "2026-07-28T10:00:00+00:00",
            "next_weight_reassessment_date": "5 August",
        },
        match_packet={"complete_fulfillment": False, "considered_sample": []},
    )
    assert result["response_kind"] == "weekly_weight_reassessment"
    assert "We weigh the pigs weekly" in result["customer_reply"]
    assert "5 August" in result["customer_reply"]
    assert "how many" not in result["customer_reply"].lower()
    assert "which town" not in result["customer_reply"].lower()
    assert "does not reserve or promise future stock" in result["customer_reply"]


def test_tenth_request_derives_owner_approved_fifth_reassessment():
    result = _packet(
        "If we can have the piglets on the 10th please",
        facts={
            "sex": "split",
            "sex_split": {"female": 4, "male": 1},
            "weight_range": "around 19 kg",
            "timing": "10th",
        },
        availability={
            "success": True,
            "evidence_complete": False,
            "eligible_evidence_complete": True,
            "weight_freshness_consistent": True,
            "latest_weight_date": "2026-07-27",
            "oldest_weight_age_days": 3,
        },
        match_packet={"complete_fulfillment": False, "considered_sample": []},
    )

    assert result["response_kind"] == "weekly_weight_reassessment"
    assert "4 females and 1 male" in result["customer_reply"]
    assert "around 19 kg" in result["customer_reply"]
    assert "5 August" in result["customer_reply"]
    assert "How many" not in result["customer_reply"]


def test_reassessment_date_is_never_in_the_past():
    facts = {"timing": "10th"}
    assert _future_reassessment_date(
        facts, now=datetime(2026, 7, 30, tzinfo=timezone.utc)
    ) == "5 August"
    assert _future_reassessment_date(
        facts, now=datetime(2026, 8, 5, tzinfo=timezone.utc)
    ) == "5 August"
    for day in (6, 7, 8, 9):
        assert _future_reassessment_date(
            facts, now=datetime(2026, 8, day, tzinfo=timezone.utc)
        ) == f"{day} August"
    assert _future_reassessment_date(
        {"timing": "2nd"},
        now=datetime(2026, 12, 30, tzinfo=timezone.utc),
    ) == "30 December"
    assert _future_reassessment_date(
        {"timing": "32nd"},
        now=datetime(2026, 7, 30, tzinfo=timezone.utc),
    ) == ""
