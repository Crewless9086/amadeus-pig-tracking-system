from datetime import datetime, timezone
import json

import pytest

from modules.sales.sam_live_stock_contextual_sales import (
    build_contextual_sales_recommendation,
    interpret_contextual_livestock_request,
    normalize_livestock_language,
)


NOW = datetime(2026, 7, 27, 12, tzinfo=timezone.utc)


def inbound(content, *, name="Fanie", conversation_id="2054"):
    return {
        "content": content,
        "customer_name": name,
        "conversation_id": conversation_id,
    }


def row(category, sex, *, identity):
    return {
        "pig_id": identity,
        "tag_number": f"TAG-{identity}",
        "sale_category": category,
        "sex": sex,
        "purpose": "Sale",
        "live_stock_sale_eligible": True,
        "evidence_complete": True,
        "allocation_query_status": "known",
        "allocation_evidence_state": "known_unallocated",
        "medical_status": "Clear",
        "reserved_status": "Not_Reserved",
    }


def availability(*rows, observed_at="2026-07-27T11:30:00Z"):
    counts = {
        category: {"all": 0, "female": 0, "male": 0, "unknown": 0}
        for category in (
            "Young Piglets", "Weaner Piglets", "Grower Pigs",
            "Finisher Pigs", "Ready for Slaughter",
        )
    }
    for item in rows:
        category = item["sale_category"]
        sex = str(item.get("sex") or "").casefold()
        bucket = counts.setdefault(
            category, {"all": 0, "female": 0, "male": 0, "unknown": 0}
        )
        bucket["all"] += 1
        bucket[sex if sex in ("female", "male") else "unknown"] += 1
    return {
        "success": True,
        "observation_timestamp": observed_at,
        "considered_sample": list(rows),
        "customer_category_counts": counts,
    }


def prices(*categories):
    entries = []
    values = {
        "Young Piglets": (350, 400),
        "Weaner Piglets": (450, 600),
        "Grower Pigs": (800, 1800),
        "Finisher Pigs": (2200, 2700),
        "Ready for Slaughter": (2800, 3000),
    }
    for category in categories:
        for index, amount in enumerate(values[category]):
            entries.append({
                "pricing_id": f"PRICE-{category}-{index}",
                "sale_category": category,
                "weight_band": f"band-{index}",
                "unit_price": amount,
                "active": True,
                "effective_from": "2026-07-01T00:00:00Z",
                "effective_to": "",
            })
    return lambda **kwargs: ({
        "success": True,
        "configured": True,
        "source": "supabase",
        "price_entries": entries,
    }, 200)


def test_conversation_67_phonetic_context_extracts_female_quantity_and_no_category():
    packet = build_contextual_sales_recommendation(
        inbound("Soggies to bay 10", name="Lionel", conversation_id="67"),
        {},
        [{"speaker": "customer", "content": "I asked about Ms. Piggy’s piglets."}],
        availability(
            row("Young Piglets", "Female", identity="PRIVATE-1"),
            row("Weaner Piglets", "Female", identity="PRIVATE-2"),
            row("Grower Pigs", "Female", identity="PRIVATE-3"),
        ),
        price_loader=prices("Young Piglets", "Weaner Piglets", "Grower Pigs"),
        now=NOW,
    )
    interpretation = packet["interpretation"]
    assert interpretation["intent"] == "buy_live_pigs"
    assert interpretation["quantity"] == 10
    assert interpretation["sex"] == "female"
    assert interpretation["category"] == ""
    assert interpretation["next_action"] == (
        "present_matching_category_counts_and_prices_then_offer_quote"
    )
    assert packet["general_information_fallback_blocked"] is True
    reply = packet["recommendation"]
    assert "no single category currently has all 10" in reply
    assert "1 Young Piglet at R350 to R400 each" in reply
    assert "1 Weaner Piglet at R450 to R600 each" in reply
    assert "1 Grower Pig at R800 to R1,800 each" in reply
    assert "split across categories" not in reply
    assert "check again when more eligible animals become available" in reply
    assert "does not reserve the animals" in reply
    assert "PRIVATE-" not in json.dumps(packet)
    assert packet["sends_customer_message"] is False
    assert packet["creates_quote"] is False


def test_conversation_2054_answers_direct_question_then_asks_quantity_and_sex():
    packet = build_contextual_sales_recommendation(
        inbound("Do you sell the piglets"),
        {},
        [],
        availability(
            row("Young Piglets", "Female", identity="PRIVATE-1"),
            row("Weaner Piglets", "Male", identity="PRIVATE-2"),
            row("Grower Pigs", "Male", identity="PRIVATE-3"),
        ),
        price_loader=prices("Young Piglets", "Weaner Piglets"),
        now=NOW,
    )
    interpretation = packet["interpretation"]
    assert interpretation == {
        **interpretation,
        "intent": "buy_live_pigs",
        "product": "piglets",
        "message_type": "availability_enquiry",
        "quantity": "",
        "sex": "",
        "category": "",
        "category_options": ["Young Piglets", "Weaner Piglets"],
        "next_action": "present_piglet_options_then_ask_quantity_and_sex",
    }
    reply = packet["recommendation"]
    assert reply.startswith("Hi Fanie, Yes, we do sell piglets.")
    assert "Young piglets: 1 currently eligible; R350 to R400 each" in reply
    assert "Weaners: 1 currently eligible; R450 to R600 each" in reply
    assert "Growers" not in reply
    assert "How many are you looking for" in reply
    assert "males, females, or a mixture" in reply
    assert packet["customer_send_allowed"] is False


def test_standalone_weaner_availability_question_answers_directly():
    packet = build_contextual_sales_recommendation(
        inbound("Do you sell weaners?"),
        {},
        [],
        availability(row("Weaner Piglets", "Female", identity="PRIVATE-W")),
        price_loader=prices("Weaner Piglets"),
        now=NOW,
    )
    assert packet["interpretation"]["product"] == "piglets"
    assert packet["interpretation"]["category"] == "Weaner Piglets"
    assert packet["recommendation"].startswith("Hi Fanie, Yes, we do sell piglets.")
    assert "Weaners: 1 currently eligible" in packet["recommendation"]


@pytest.mark.parametrize(
    ("text", "quantity", "sex", "product"),
    [
        ("Ek soek 4 wyfies te koop", 4, "female", "live_pigs"),
        ("Het julle 3 speenvarkies beskikbaar?", 3, "", "piglets"),
        ("I want to buy 2 varkies", 2, "", "piglets"),
        ("10 sogies to bay", 10, "female", "live_pigs"),
    ],
)
def test_mixed_afrikaans_english_and_misspellings(text, quantity, sex, product):
    interpreted = interpret_contextual_livestock_request(
        inbound(text), {}, []
    )
    assert interpreted["commercial_intent"] is True
    assert interpreted["quantity"] == quantity
    assert interpreted["sex"] == sex
    assert interpreted["product"] == product


def test_prior_context_establishes_livestock_but_does_not_override_category():
    interpreted = interpret_contextual_livestock_request(
        inbound("Are they available?"),
        {},
        [{"speaker": "customer", "content": "I saw Ms. Piggy’s piglets."}],
    )
    assert interpreted["commercial_intent"] is True
    assert interpreted["product"] == "piglets"
    assert interpreted["category"] == ""
    assert interpreted["category_options"] == ["Young Piglets", "Weaner Piglets"]


def test_ambiguous_noncommercial_pig_context_does_not_invent_sales_intent():
    interpreted = interpret_contextual_livestock_request(
        inbound("The piglets look happy"), {}, []
    )
    assert interpreted["commercial_intent"] is False
    assert interpreted["intent"] == "not_proven"


def test_unrelated_commercial_request_does_not_reuse_old_livestock_context():
    interpreted = interpret_contextual_livestock_request(
        inbound("Do you sell feed?"),
        {},
        [{"speaker": "customer", "content": "I want to buy 3 piglets"}],
    )
    assert interpreted["commercial_intent"] is False
    assert interpreted["intent"] == "not_proven"


def test_sell_me_phrase_is_a_customer_purchase_request():
    interpreted = interpret_contextual_livestock_request(
        inbound("Can you sell me 2 pigs?"), {}, []
    )
    assert interpreted["intent"] == "buy_live_pigs"
    assert interpreted["commercial_intent"] is True
    assert interpreted["quantity"] == 2


def test_noncommercial_close_does_not_replay_prior_purchase_intent():
    interpreted = interpret_contextual_livestock_request(
        inbound("Thanks"),
        {},
        [{"speaker": "customer", "content": "I want to buy 3 piglets"}],
    )
    assert interpreted["commercial_intent"] is False
    assert interpreted["intent"] == "not_proven"


@pytest.mark.parametrize(
    "text",
    [
        "I want to sell 3 pigs",
        "I sell pigs",
        "Can I sell you pigs?",
        "Ek het varkies te koop",
        "I have 4 pigs for sale",
        "Do you buy pigs?",
        "Can you buy my pigs?",
    ],
)
def test_seller_enquiry_never_generates_farm_inventory_offer(text):
    packet = build_contextual_sales_recommendation(
        inbound(text), {}, [], availability(),
        price_loader=prices("Young Piglets"),
        now=NOW,
    )
    assert packet["interpretation"]["intent"] == "sell_livestock_to_farm"
    assert packet["status"] == "seller_enquiry_owner_handoff"
    assert "owner for review" in packet["recommendation"]
    assert "currently eligible" not in packet["recommendation"]
    assert packet["customer_send_allowed"] is False


@pytest.mark.parametrize(
    ("observed_at", "price_loader", "blocker"),
    [
        (
            "2026-07-25T10:00:00Z",
            prices("Young Piglets", "Weaner Piglets"),
            "herdmaster_availability_stale_or_unavailable",
        ),
        (
            "2026-07-27T11:30:00Z",
            lambda **kwargs: ({
                "success": True,
                "configured": False,
                "source": "code_defaults",
                "price_entries": [],
            }, 200),
            "active_pricing_stale_or_unavailable",
        ),
    ],
)
def test_stale_stock_or_non_authoritative_pricing_fails_closed(
    observed_at, price_loader, blocker
):
    packet = build_contextual_sales_recommendation(
        inbound("Do you sell piglets"),
        {},
        [],
        availability(
            row("Young Piglets", "Female", identity="PRIVATE-1"),
            observed_at=observed_at,
        ),
        price_loader=price_loader,
        now=NOW,
    )
    assert packet["status"] == "commercial_evidence_unavailable"
    assert blocker in packet["herdmaster_aggregate"]["blockers"]
    assert "currently eligible" not in packet["recommendation"]
    assert packet["general_information_fallback_blocked"] is True
    assert packet["customer_send_allowed"] is False
    assert packet["mutates_business_state"] is False


@pytest.mark.parametrize(
    "protected_fact",
    ["order_commitment", "reservation_requested", "payment_requested"],
)
def test_protected_commercial_action_blocks_general_llm_fallback(protected_fact):
    packet = build_contextual_sales_recommendation(
        inbound("I want to buy 2 piglets"),
        {protected_fact: True},
        [],
        availability(row("Young Piglets", "Female", identity="PRIVATE-F")),
        price_loader=prices("Young Piglets"),
        now=NOW,
    )
    assert packet["status"] == "protected_commercial_action_owner_gate"
    assert packet["general_information_fallback_blocked"] is True
    assert packet["customer_send_allowed"] is False
    assert packet["mutates_business_state"] is False


def test_date_only_availability_observation_fails_closed():
    packet = build_contextual_sales_recommendation(
        inbound("Do you sell piglets"),
        {},
        [],
        availability(
            row("Young Piglets", "Female", identity="PRIVATE-F"),
            observed_at="2026-07-27",
        ),
        price_loader=prices("Young Piglets"),
        now=NOW,
    )
    assert packet["status"] == "commercial_evidence_unavailable"
    assert packet["herdmaster_aggregate"]["availability_observed_at_utc"] is None
    assert "herdmaster_availability_stale_or_unavailable" in (
        packet["herdmaster_aggregate"]["blockers"]
    )


@pytest.mark.parametrize("active", [None, "true", 1])
def test_pricing_requires_explicit_boolean_active(active):
    packet = build_contextual_sales_recommendation(
        inbound("Do you sell piglets"), {}, [],
        availability(row("Young Piglets", "Female", identity="PRIVATE-1")),
        price_loader=lambda **_: ({
            "success": True, "configured": True, "source": "supabase",
            "price_entries": [{
                "sale_category": "Young Piglets",
                "weight_band": "5_to_6_Kg",
                "unit_price": 500,
                "active": active,
                "effective_from": "2026-07-20T00:00:00Z",
                "effective_to": "",
            }],
        }, 200),
        now=NOW,
    )
    assert packet["status"] == "commercial_evidence_unavailable"
    assert "active_pricing_stale_or_unavailable" in (
        packet["herdmaster_aggregate"]["blockers"]
    )


def test_normalization_is_bounded_and_deterministic():
    assert normalize_livestock_language("Soggies to bay 10, PRICCCE?") == (
        "female pigs to buy 10, price?"
    )


def test_complete_category_counts_do_not_use_truncated_diagnostic_sample():
    evidence = availability(
        row("Young Piglets", "Female", identity="PRIVATE-1")
    )
    evidence["customer_category_counts"]["Young Piglets"] = {
        "all": 40, "female": 40, "male": 0, "unknown": 0
    }
    packet = build_contextual_sales_recommendation(
        inbound("Do you sell piglets"),
        {},
        [],
        evidence,
        price_loader=prices("Young Piglets"),
        now=NOW,
    )
    assert packet["herdmaster_aggregate"]["options"][0]["eligible_count"] == 40


def test_authoritative_zero_inventory_is_complete_and_does_not_invent_options():
    evidence = availability()
    packet = build_contextual_sales_recommendation(
        inbound("Do you sell piglets"),
        {},
        [],
        evidence,
        price_loader=lambda **_: ({
            "success": True, "configured": True, "source": "supabase",
            "price_entries": [],
        }, 200),
        now=NOW,
    )
    assert packet["status"] == "commercial_recommendation_ready"
    assert packet["herdmaster_aggregate"]["evidence_complete"] is True
    assert packet["herdmaster_aggregate"]["options"] == []
    assert "don't currently have an eligible option" in packet["recommendation"]
    assert "R" not in packet["recommendation"]


def test_sex_specific_latest_effective_prices_exclude_other_sex_and_superseded_rows():
    entries = [
        {
            "sale_category": "Young Piglets", "weight_band": "5_to_6_Kg",
            "sex": "Female", "unit_price": 450, "active": True,
            "effective_from": "2026-07-01T00:00:00Z", "effective_to": "",
        },
        {
            "sale_category": "Young Piglets", "weight_band": "5_to_6_Kg",
            "sex": "Female", "unit_price": 500, "active": True,
            "effective_from": "2026-07-20T00:00:00Z", "effective_to": "",
        },
        {
            "sale_category": "Young Piglets", "weight_band": "5_to_6_Kg",
            "sex": "Male", "unit_price": 900, "active": True,
            "effective_from": "2026-07-20T00:00:00Z", "effective_to": "",
        },
    ]
    packet = build_contextual_sales_recommendation(
        inbound("I want to buy 10 female piglets"),
        {},
        [],
        availability(row("Young Piglets", "Female", identity="PRIVATE-1")),
        price_loader=lambda **_: ({
            "success": True, "configured": True, "source": "supabase",
            "price_entries": entries,
        }, 200),
        now=NOW,
    )
    price_range = packet["herdmaster_aggregate"]["options"][0]["price_range"]
    assert price_range["minimum"] == 500
    assert price_range["maximum"] == 500
    assert price_range["active_entry_count"] == 1


def test_unspecified_sex_preserves_latest_male_and_female_prices():
    entries = [
        {
            "sale_category": "Young Piglets", "weight_band": "5_to_6_Kg",
            "sex": "Female", "unit_price": 500, "active": True,
            "effective_from": "2026-07-20T00:00:00Z", "effective_to": "",
        },
        {
            "sale_category": "Young Piglets", "weight_band": "5_to_6_Kg",
            "sex": "Male", "unit_price": 650, "active": True,
            "effective_from": "2026-07-20T00:00:00Z", "effective_to": "",
        },
    ]
    packet = build_contextual_sales_recommendation(
        inbound("Do you sell piglets"),
        {}, [], availability(
            row("Young Piglets", "Female", identity="PRIVATE-F"),
            row("Young Piglets", "Male", identity="PRIVATE-M"),
        ),
        price_loader=lambda **_: ({
            "success": True, "configured": True, "source": "supabase",
            "price_entries": entries,
        }, 200),
        now=NOW,
    )
    price_range = packet["herdmaster_aggregate"]["options"][0]["price_range"]
    assert price_range["minimum"] == 500
    assert price_range["maximum"] == 650
    assert price_range["active_entry_count"] == 2


def test_mixture_excludes_unknown_sex_stock_and_uses_both_sex_prices():
    evidence = availability(
        row("Young Piglets", "Female", identity="PRIVATE-F"),
        row("Young Piglets", "Male", identity="PRIVATE-M"),
        row("Young Piglets", "", identity="PRIVATE-U"),
    )
    packet = build_contextual_sales_recommendation(
        inbound("I want to buy 2 piglets, one male and one female"),
        {}, [], evidence,
        price_loader=prices("Young Piglets"),
        now=NOW,
    )
    option = packet["herdmaster_aggregate"]["options"][0]
    assert packet["interpretation"]["sex"] == "mixture"
    assert option["eligible_count"] == 2
    assert option["excluded_count"] == 1


def test_known_piglet_quantity_and_sex_explains_evidenced_shortage_and_split():
    packet = build_contextual_sales_recommendation(
        inbound("I want to buy 10 female piglets"),
        {}, [], availability(
            row("Young Piglets", "Female", identity="PRIVATE-F"),
            row("Weaner Piglets", "Female", identity="PRIVATE-W"),
        ),
        price_loader=prices("Young Piglets", "Weaner Piglets"),
        now=NOW,
    )
    reply = packet["recommendation"]
    assert "How many" not in reply
    assert "males, females, or a mixture" not in reply
    assert "no single category currently has all 10" in reply
    assert "1 Young Piglet at R350 to R400 each" in reply
    assert "1 Weaner Piglet at R450 to R600 each" in reply
    assert "split across categories" not in reply
    assert "check again when more eligible animals become available" in reply
    assert "does not reserve the animals" in reply


def test_production_shaped_shortage_uses_dynamic_counts_prices_and_exact_meaning():
    evidence = availability()
    evidence["customer_category_counts"].update({
        "Young Piglets": {"all": 12, "female": 9, "male": 3, "unknown": 0},
        "Weaner Piglets": {"all": 22, "female": 7, "male": 15, "unknown": 0},
        "Grower Pigs": {"all": 6, "female": 1, "male": 5, "unknown": 0},
    })
    packet = build_contextual_sales_recommendation(
        inbound("Soggies to bay 10", name="Lionel", conversation_id="67"),
        {},
        [{"speaker": "customer", "content": "I want to buy live pigs."}],
        evidence,
        price_loader=prices("Young Piglets", "Weaner Piglets", "Grower Pigs"),
        now=NOW,
    )
    assert packet["recommendation"] == (
        "Hi Lionel, yes, we currently have female pigs available, but no single "
        "category currently has all 10. We have 9 Young Piglets at R350 to R400 "
        "each, 7 Weaner Piglets at R450 to R600 each, and 1 Grower Pig at R800 "
        "to R1,800 each. Please let me know whether you prefer one of these "
        "available category quantities or would like us to consider a split "
        "across categories. Choosing an option does not reserve the animals; "
        "availability would still need to be confirmed when we prepare the quote."
    )
    assert packet["sends_customer_message"] is False
    assert packet["creates_quote"] is False
    assert packet["reserves_stock"] is False
    assert packet["allocates_stock"] is False


def test_shortage_rendering_is_not_bound_to_lionel_counts_or_prices():
    evidence = availability()
    evidence["customer_category_counts"].update({
        "Young Piglets": {"all": 3, "female": 3, "male": 0, "unknown": 0},
        "Weaner Piglets": {"all": 4, "female": 4, "male": 0, "unknown": 0},
    })
    dynamic_prices = lambda **_: ({
        "success": True, "configured": True, "source": "supabase",
        "price_entries": [
            {
                "sale_category": category, "weight_band": "current",
                "unit_price": amount, "active": True,
                "effective_from": "2026-07-01T00:00:00Z", "effective_to": "",
            }
            for category, amount in (
                ("Young Piglets", 375), ("Weaner Piglets", 575)
            )
        ],
    }, 200)
    packet = build_contextual_sales_recommendation(
        inbound("I want 8 female piglets", name="Customer", conversation_id="future"),
        {}, [], evidence, price_loader=dynamic_prices, now=NOW,
    )
    reply = packet["recommendation"]
    assert "all 8" in reply
    assert "3 Young Piglets at R375 each" in reply
    assert "4 Weaner Piglets at R575 each" in reply
    assert "Lionel" not in reply
    assert "R350" not in reply
    assert "split across categories" not in reply


def test_infeasible_combined_counts_do_not_offer_a_supported_split():
    evidence = availability()
    evidence["customer_category_counts"].update({
        "Young Piglets": {"all": 2, "female": 2, "male": 0, "unknown": 0},
        "Weaner Piglets": {"all": 3, "female": 3, "male": 0, "unknown": 0},
    })
    packet = build_contextual_sales_recommendation(
        inbound("I want 10 female piglets"),
        {}, [], evidence,
        price_loader=prices("Young Piglets", "Weaner Piglets"),
        now=NOW,
    )
    reply = packet["recommendation"]
    assert "split across categories" not in reply
    assert "check again when more eligible animals become available" in reply


def test_explicit_category_shortage_is_clear_and_non_reserving():
    evidence = availability()
    evidence["customer_category_counts"]["Young Piglets"] = {
        "all": 3, "female": 3, "male": 0, "unknown": 0,
    }
    packet = build_contextual_sales_recommendation(
        inbound("I want 10 female young piglets"),
        {}, [], evidence,
        price_loader=prices("Young Piglets"),
        now=NOW,
    )
    reply = packet["recommendation"]
    assert "requested Young Piglets category does not currently have all 10" in reply
    assert "3 Young Piglets at R350 to R400 each" in reply
    assert "available quantity from this category" in reply
    assert "does not reserve the animals" in reply


def test_commercial_followup_uses_prior_customer_context_and_blocks_fallback():
    packet = build_contextual_sales_recommendation(
        inbound("10 females"),
        {},
        [{"speaker": "customer", "content": "I want to buy piglets"}],
        availability(
            row("Young Piglets", "Female", identity="PRIVATE-F"),
            row("Weaner Piglets", "Female", identity="PRIVATE-W"),
        ),
        price_loader=prices("Young Piglets", "Weaner Piglets"),
        now=NOW,
    )
    assert packet["status"] == "commercial_recommendation_ready"
    assert packet["interpretation"]["intent"] == "buy_live_pigs"
    assert packet["interpretation"]["quantity"] == 10
    assert packet["interpretation"]["sex"] == "female"
    assert packet["general_information_fallback_blocked"] is True


@pytest.mark.parametrize("text", ["How much?", "Price?", "What's the price?"])
def test_punctuated_subjectless_price_followup_stays_commercial(text):
    interpreted = interpret_contextual_livestock_request(
        inbound(text),
        {},
        [{"speaker": "customer", "content": "I want to buy piglets"}],
    )
    assert interpreted["commercial_intent"] is True
    assert interpreted["intent"] == "buy_live_pigs"
    assert interpreted["product"] == "piglets"


def test_split_fact_is_preserved_as_mixture_on_price_followup():
    interpreted = interpret_contextual_livestock_request(
        inbound("How much?"),
        {"sex": "split"},
        [{"speaker": "customer", "content": "I want to buy 4 piglets"}],
    )
    assert interpreted["commercial_intent"] is True
    assert interpreted["sex"] == "mixture"
    assert "sex" not in interpreted["missing_quote_facts"]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("How much for 20 kg piglets?", ""),
        ("I want 20 kg piglets", ""),
        ("looking for 20 kilograms pigs", ""),
        ("Are piglets R500?", ""),
        ("I want to buy 10 piglets", 10),
        ("10 female pigs to buy", 10),
    ],
)
def test_quantity_requires_quantity_specific_syntax(text, expected):
    interpreted = interpret_contextual_livestock_request(inbound(text), {}, [])
    assert interpreted["quantity"] == expected
