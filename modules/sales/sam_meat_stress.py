import re
from collections import Counter, defaultdict

from modules.sales import sam_meat_runtime
from modules.sales.chatwoot_hygiene import build_sam_meat_chatwoot_hygiene_payload


FORBIDDEN_REPLY_PATTERNS = [
    r"\br\s*\d",
    r"\br\d",
    r"\bquote\b.*\b(sent|attached|ready|final)\b",
    r"\b(order|booking)\b.*\b(created|confirmed|approved|reserved|booked)\b",
    r"\bdeposit\b.*\bpaid|money reflects\b.*\bconfirmed\b",
    r"\babattoir\b.*\b(booked|confirmed)\b",
    r"\bbutcher\b.*\b(booked|confirmed)\b",
]


STRESS_SCENARIOS = [
    {
        "id": "vague_freezer_options",
        "category": "vague_interest",
        "message": "Hi Sam, I want pork for my freezer. What options do you have?",
        "expected_facts": {"product_type": "unknown"},
        "expected_reply_any": ["half carcass", "full carcass", "custom cuts", "assisted slaughter"],
        "expected_labels": ["meat_lead", "needs_followup"],
        "expected_attrs": {"sales_lane": "meat_preorder", "meat_next_gate": "collect_missing_facts"},
    },
    {
        "id": "complete_half_set_a_collection",
        "category": "happy_path",
        "message": "Half carcass, Set A, Riversdale, collection please. EFT is fine. Next available farm run.",
        "expected_facts": {
            "product_type": "half_carcass",
            "cut_set": "Set A",
            "location": "Riversdale",
            "delivery_or_collection": "collection",
            "payment_method": "EFT",
        },
        "expected_reply_any": ["farm to review", "confirm price"],
        "expected_labels": ["meat_lead", "half_carcass", "set_a", "collection", "needs_followup"],
        "expected_attrs": {"meat_product_type": "half_carcass", "meat_next_gate": "owner_price_review"},
    },
    {
        "id": "complete_half_set_a_delivery_address",
        "category": "happy_path",
        "message": "Half carcass Set A in Riversdale, delivery to 12 Test Street, Riversdale. Blue gate. EFT. Next week.",
        "expected_facts": {
            "product_type": "half_carcass",
            "cut_set": "Set A",
            "location": "Riversdale",
            "delivery_or_collection": "delivery",
            "delivery_address_line_1": "12 Test Street",
            "payment_method": "EFT",
        },
        "expected_reply_any": ["farm to review", "confirm price"],
        "expected_labels": ["meat_lead", "half_carcass", "set_a", "delivery", "needs_followup"],
        "expected_attrs": {"meat_delivery_mode": "delivery", "meat_next_gate": "owner_price_review"},
    },
    {
        "id": "delivery_missing_address",
        "category": "delivery",
        "message": "Half carcass Set A Riversdale. Delivery please. EFT. Next week.",
        "expected_facts": {"product_type": "half_carcass", "delivery_or_collection": "delivery"},
        "expected_reply_any": ["delivery street address", "farm name", "directions"],
        "expected_labels": ["meat_lead", "half_carcass", "set_a", "delivery", "needs_followup"],
        "expected_attrs": {"meat_next_gate": "collect_missing_facts"},
    },
    {
        "id": "collection_missing_timing",
        "category": "missing_fact",
        "message": "I want a half carcass Set A in Riversdale, collection, EFT.",
        "expected_facts": {"product_type": "half_carcass", "delivery_or_collection": "collection"},
        "expected_reply_any": ["When would you ideally like"],
        "expected_labels": ["meat_lead", "half_carcass", "set_a", "collection", "needs_followup"],
        "expected_attrs": {"meat_next_gate": "collect_missing_facts"},
    },
    {
        "id": "payment_defaults_to_eft",
        "category": "missing_fact",
        "message": "Half carcass Set A Riversdale collection next week.",
        "expected_facts": {"product_type": "half_carcass", "delivery_or_collection": "collection", "payment_method": "EFT"},
        "expected_reply_any": ["farm to review", "confirm price"],
        "expected_labels": ["meat_lead", "half_carcass", "set_a", "collection", "needs_followup"],
        "expected_attrs": {"meat_next_gate": "owner_price_review"},
    },
    {
        "id": "cut_set_missing",
        "category": "missing_fact",
        "message": "I want a half carcass in Riversdale, collection, EFT, next week.",
        "expected_facts": {"product_type": "half_carcass"},
        "expected_reply_any": ["Which cut set", "Set A"],
        "expected_labels": ["meat_lead", "half_carcass", "collection", "needs_followup"],
        "expected_attrs": {"meat_next_gate": "collect_missing_facts"},
    },
    {
        "id": "town_missing",
        "category": "missing_fact",
        "message": "Half carcass Set A collection please. EFT next week.",
        "expected_facts": {"product_type": "half_carcass", "cut_set": "Set A"},
        "expected_reply_any": ["Which town", "area"],
        "expected_labels": ["meat_lead", "half_carcass", "set_a", "collection", "needs_followup"],
        "expected_attrs": {"meat_next_gate": "collect_missing_facts"},
    },
    {
        "id": "set_a_question",
        "category": "cut_set_question",
        "message": "What does Set A include?",
        "expected_facts": {"cut_set": "Set A"},
        "expected_reply_any": ["Family Freezer Pack", "pork chops", "before quoting or booking"],
        "expected_labels": ["meat_lead", "set_a", "needs_followup"],
        "expected_attrs": {"meat_last_customer_intent": "asks_options"},
    },
    {
        "id": "cut_menu_question",
        "category": "cut_set_question",
        "message": "What cut options do you have?",
        "expected_facts": {},
        "expected_reply_any": ["Set A", "Set B", "Set C", "Set D"],
        "expected_labels": ["meat_lead", "needs_followup"],
        "expected_attrs": {"meat_last_customer_intent": "asks_options"},
    },
    {
        "id": "price_direct_question",
        "category": "price_objection",
        "message": "How much is a half carcass Set A in Riversdale?",
        "expected_facts": {"product_type": "half_carcass", "cut_set": "Set A"},
        "expected_reply_any": ["farm", "confirm", "price"],
        "expected_labels": ["meat_lead", "half_carcass", "set_a", "needs_followup"],
        "expected_attrs": {"meat_last_customer_intent": "asks_price"},
    },
    {
        "id": "budget_buyer_3000",
        "category": "budget",
        "message": "I have about R3000. What pork option can you make work for me?",
        "expected_facts": {"product_type": "unknown"},
        "expected_reply_any": ["half carcass", "full carcass", "custom cuts", "assisted slaughter"],
        "expected_labels": ["meat_lead", "needs_followup"],
        "expected_attrs": {
            "meat_next_gate": "collect_missing_facts",
            "meat_budget_amount": "3000",
            "meat_match_preference": "budget_fit",
        },
    },
    {
        "id": "heaviest_one",
        "category": "butcher_match",
        "message": "I want the heaviest half carcass you have for Set A, collection in Riversdale.",
        "expected_facts": {"product_type": "half_carcass", "cut_set": "Set A", "delivery_or_collection": "collection"},
        "expected_reply_any": ["EFT", "cash", "When would you ideally like"],
        "expected_labels": ["meat_lead", "half_carcass", "set_a", "collection", "needs_followup"],
        "expected_attrs": {"meat_next_gate": "collect_missing_facts", "meat_match_preference": "heaviest"},
    },
    {
        "id": "around_25kg",
        "category": "butcher_match",
        "message": "Looking for around 25kg packed pork, Set A if possible, delivery Riversdale.",
        "expected_facts": {"cut_set": "Set A", "delivery_or_collection": "delivery"},
        "expected_reply_any": ["delivery street address", "farm name", "directions"],
        "expected_labels": ["meat_lead", "set_a", "delivery", "needs_followup"],
        "expected_attrs": {
            "meat_next_gate": "collect_missing_facts",
            "meat_target_packed_kg": "25",
            "meat_match_preference": "closest_weight",
        },
    },
    {
        "id": "live_pig_confusion",
        "category": "wrong_product",
        "message": "Do you sell live pigs or pork halves? I am not sure which one I need.",
        "expected_facts": {"product_type": "unknown"},
        "expected_reply_any": ["half carcass", "full carcass", "custom cuts", "assisted slaughter"],
        "expected_labels": ["meat_lead", "needs_followup"],
        "expected_attrs": {"meat_next_gate": "collect_missing_facts"},
    },
    {
        "id": "wrong_product_beef",
        "category": "wrong_product",
        "message": "Can I order beef mince from you?",
        "expected_facts": {"product_type": "unknown"},
        "expected_reply_any": ["pork orders only", "half carcass", "full carcass"],
        "expected_labels": ["meat_lead", "needs_followup"],
        "expected_attrs": {"meat_next_gate": "collect_missing_facts"},
    },
    {
        "id": "assisted_slaughter",
        "category": "assisted_slaughter",
        "message": "I have my own pig. Can you help with assisted slaughter?",
        "expected_facts": {"product_type": "assisted_slaughter"},
        "expected_reply_any": ["Which town", "area", "prefer"],
        "expected_labels": ["meat_lead", "needs_followup"],
        "expected_attrs": {"meat_product_type": "assisted_slaughter"},
    },
    {
        "id": "custom_cut",
        "category": "custom_cut",
        "message": "I want custom cuts, mostly chops and mince, delivery in Riversdale.",
        "expected_facts": {"product_type": "custom_cut", "delivery_or_collection": "delivery"},
        "expected_reply_any": ["Which cut set", "Set A", "explain"],
        "expected_labels": ["meat_lead", "custom_cut", "delivery", "needs_followup"],
        "expected_attrs": {"meat_product_type": "custom_cut"},
    },
    {
        "id": "full_carcass",
        "category": "full_carcass",
        "message": "Can I take a full carcass, Set B, Albertinia collection, cash, next week?",
        "expected_facts": {
            "product_type": "full_carcass",
            "cut_set": "Set B",
            "location": "Albertinia",
            "delivery_or_collection": "collection",
            "payment_method": "Cash",
        },
        "expected_reply_any": ["EFT is the only payment option", "EFT only"],
        "expected_labels": ["meat_lead", "full_carcass", "set_b", "collection", "needs_followup"],
        "expected_attrs": {"meat_product_type": "full_carcass", "meat_next_gate": "owner_price_review"},
    },
    {
        "id": "cash_payment",
        "category": "payment",
        "message": "Half carcass Set A Riversdale collection cash next week.",
        "expected_facts": {"payment_method": "Cash"},
        "expected_reply_any": ["EFT is the only payment option", "EFT only"],
        "expected_labels": ["meat_lead", "half_carcass", "set_a", "collection", "needs_followup"],
        "expected_attrs": {"meat_next_gate": "owner_price_review"},
    },
    {
        "id": "afrikaans_short",
        "category": "language",
        "message": "Ek soek n halwe karkas Set A Riversdale afhaal EFT volgende week.",
        "expected_facts": {
            "product_type": "half_carcass",
            "cut_set": "Set A",
            "location": "Riversdale",
            "delivery_or_collection": "collection",
            "payment_method": "EFT",
        },
        "expected_reply_any": ["farm to review", "confirm"],
        "expected_labels": ["meat_lead", "half_carcass", "set_a", "collection", "needs_followup"],
        "expected_attrs": {"meat_next_gate": "owner_price_review"},
    },
    {
        "id": "typo_heavy",
        "category": "typos",
        "message": "Hlaf carcas set a rivrsdale colect eft nxt week",
        "expected_facts": {
            "product_type": "half_carcass",
            "cut_set": "Set A",
            "location": "Riversdale",
            "delivery_or_collection": "collection",
            "payment_method": "EFT",
        },
        "expected_reply_any": ["farm to review", "confirm"],
        "expected_labels": ["meat_lead", "half_carcass", "set_a", "collection", "needs_followup"],
        "expected_attrs": {"meat_next_gate": "owner_price_review"},
    },
    {
        "id": "location_pin_only",
        "category": "location_pin",
        "message": "",
        "payload_overrides": {
            "attachments": [{
                "file_type": "location",
                "latitude": "-34.0921",
                "longitude": "21.2576",
                "name": "12 Test Street, Riversdale",
            }]
        },
        "expected_facts": {"delivery_or_collection": "delivery", "delivery_address_line_1": "12 Test Street, Riversdale"},
        "expected_reply_any": ["half carcass", "full carcass", "custom cuts", "assisted slaughter"],
        "expected_labels": ["meat_lead", "delivery", "needs_followup"],
        "expected_attrs": {"meat_delivery_mode": "delivery", "meat_next_gate": "collect_missing_facts"},
    },
    {
        "id": "google_maps_url",
        "category": "location_pin",
        "message": "Please deliver here https://maps.google.com/?q=-34.0921,21.2576",
        "expected_facts": {
            "delivery_or_collection": "delivery",
            "delivery_address_line_1": "Shared Google Maps location",
            "delivery_location_latitude": "-34.0921",
            "delivery_location_longitude": "21.2576",
        },
        "expected_reply_any": ["half carcass", "full carcass", "custom cuts", "assisted slaughter"],
        "expected_labels": ["meat_lead", "delivery", "needs_followup"],
        "expected_attrs": {"meat_delivery_mode": "delivery", "meat_next_gate": "collect_missing_facts"},
    },
    {
        "id": "test_flow_marker",
        "category": "test_cleanup",
        "message": "TEST FLOW - delete after test. Half carcass Set A Riversdale collection EFT next week.",
        "expected_facts": {"product_type": "half_carcass", "cut_set": "Set A"},
        "expected_reply_any": ["farm to review", "confirm"],
        "expected_labels": ["meat_lead", "test_flow", "half_carcass", "set_a"],
        "expected_attrs": {"meat_next_gate": "owner_price_review"},
    },
    {
        "id": "angry_price",
        "category": "frustration",
        "message": "Why can nobody just tell me the price? This is annoying.",
        "expected_facts": {"product_type": "unknown"},
        "expected_reply_any": ["do not want to waste your time", "half carcass", "full carcass"],
        "expected_labels": ["meat_lead", "needs_followup"],
        "expected_attrs": {"meat_last_customer_intent": "asks_price"},
    },
    {
        "id": "slow_reply_yes",
        "category": "followup",
        "message": "Yes that works, please proceed.",
        "context": {
            "booking_confirmation": {"recorded": True, "lead_id": "OSK-SALES-LEAD-STRESS"},
            "prior_context": {"latest_event": "customer_followup_sent", "lead_id": "OSK-SALES-LEAD-STRESS"},
        },
        "expected_facts": {"product_type": "unknown"},
        "expected_reply_any": ["half carcass", "full carcass", "custom cuts", "assisted slaughter"],
        "expected_labels": ["meat_lead", "deposit_pending", "needs_followup"],
        "expected_attrs": {"meat_payment_state": "deposit_pending", "meat_next_gate": "send_deposit_instruction"},
    },
    {
        "id": "pop_received",
        "category": "payment",
        "message": "I paid and sent POP ref POP-12345.",
        "context": {"pop_capture": {"detected": True, "recorded": True}},
        "expected_facts": {"product_type": "unknown"},
        "expected_reply_any": ["half carcass", "full carcass", "custom cuts", "assisted slaughter"],
        "expected_labels": ["meat_lead", "pop_received_unverified"],
        "expected_attrs": {"meat_payment_state": "pop_received_unverified", "meat_next_gate": "confirm_bank_receipt"},
    },
    {
        "id": "pop_fake_pressure",
        "category": "payment",
        "message": "I sent POP, please release delivery now.",
        "context": {"pop_capture": {"detected": True, "recorded": True}},
        "expected_facts": {"product_type": "unknown"},
        "expected_reply_any": ["half carcass", "full carcass", "custom cuts", "assisted slaughter"],
        "expected_labels": ["meat_lead", "pop_received_unverified"],
        "expected_attrs": {"meat_next_gate": "confirm_bank_receipt"},
    },
    {
        "id": "closed_window",
        "category": "whatsapp_window",
        "message": "Still interested in the half carcass.",
        "payload_overrides": {"service_window_state": "outside_24h"},
        "expected_facts": {"product_type": "half_carcass"},
        "expected_reply_any": ["Which cut set", "Set A"],
        "expected_labels": ["meat_lead", "half_carcass", "needs_followup"],
        "expected_attrs": {"meat_next_gate": "collect_missing_facts"},
    },
    {
        "id": "wants_invoice",
        "category": "document_request",
        "message": "Can you send me an invoice now for half carcass Set A Riversdale?",
        "expected_facts": {"product_type": "half_carcass", "cut_set": "Set A"},
        "expected_reply_any": ["farm", "confirm", "before quoting or booking"],
        "expected_labels": ["meat_lead", "half_carcass", "set_a", "needs_followup"],
        "expected_attrs": {"meat_next_gate": "collect_missing_facts"},
    },
    {
        "id": "wants_booking_now",
        "category": "authority_pressure",
        "message": "Book it now and reserve the pig for me please.",
        "expected_facts": {"product_type": "unknown"},
        "expected_reply_any": ["half carcass", "full carcass", "custom cuts", "assisted slaughter"],
        "expected_labels": ["meat_lead", "needs_followup"],
        "expected_attrs": {"meat_next_gate": "collect_missing_facts"},
    },
    {
        "id": "changes_mind_delivery_to_collection",
        "category": "change_mind",
        "message": "Actually make it collection, not delivery. Half carcass Set A Riversdale EFT next week.",
        "expected_facts": {"product_type": "half_carcass", "delivery_or_collection": "collection"},
        "expected_reply_any": ["farm to review", "confirm price"],
        "expected_labels": ["meat_lead", "collection", "needs_followup"],
        "expected_attrs": {"meat_delivery_mode": "collection", "meat_next_gate": "owner_price_review"},
    },
    {
        "id": "set_b_question",
        "category": "cut_set_question",
        "message": "What is Set B?",
        "expected_facts": {"cut_set": "Set B"},
        "expected_reply_any": ["Set B", "Braai Pack", "before quoting or booking"],
        "expected_labels": ["meat_lead", "set_b", "needs_followup"],
        "expected_attrs": {"meat_last_customer_intent": "asks_options"},
    },
    {
        "id": "delivery_directions_only",
        "category": "delivery",
        "message": "Blue gate next to the school in Riversdale. Delivery please.",
        "expected_facts": {"location": "Riversdale", "delivery_or_collection": "delivery"},
        "expected_reply_any": ["half carcass", "full carcass", "custom cuts", "assisted slaughter"],
        "expected_labels": ["meat_lead", "delivery", "needs_followup"],
        "expected_attrs": {"meat_delivery_town": "Riversdale"},
    },
    {
        "id": "messenger_channel",
        "category": "channel",
        "message": "Half carcass Set A Riversdale collection EFT next week.",
        "payload_overrides": {"conversation": {"id": 1808, "inbox": {"channel_type": "Channel::FacebookPage"}}},
        "expected_facts": {"product_type": "half_carcass", "channel": "chatwoot_facebook"},
        "expected_reply_any": ["farm to review", "confirm"],
        "expected_labels": ["meat_lead", "half_carcass", "set_a", "collection", "needs_followup"],
        "expected_attrs": {"meat_next_gate": "owner_price_review"},
    },
    {
        "id": "instagram_channel",
        "category": "channel",
        "message": "Pork freezer pack options?",
        "payload_overrides": {"conversation": {"id": 1808, "inbox": {"channel_type": "Channel::Instagram"}}},
        "expected_facts": {"channel": "chatwoot_instagram"},
        "expected_reply_any": ["half carcass", "full carcass", "custom cuts", "assisted slaughter"],
        "expected_labels": ["meat_lead", "needs_followup"],
        "expected_attrs": {"meat_next_gate": "collect_missing_facts"},
    },
    {
        "id": "email_channel",
        "category": "channel",
        "message": "Please quote me on a full carcass Set C, collection in Albertinia, EFT, next week.",
        "payload_overrides": {"conversation": {"id": 1808, "inbox": {"channel_type": "Channel::Email"}}},
        "expected_facts": {"product_type": "full_carcass", "cut_set": "Set C", "channel": "chatwoot_email"},
        "expected_reply_any": ["farm to review", "confirm"],
        "expected_labels": ["meat_lead", "full_carcass", "set_c", "collection", "needs_followup"],
        "expected_attrs": {"meat_next_gate": "owner_price_review"},
    },
    {
        "id": "outbound_ignored",
        "category": "ignore",
        "message": "Internal agent reply",
        "payload_overrides": {"message_type": "outgoing"},
        "expect_processed": False,
        "expected_status": "ignored_non_incoming_message",
    },
    {
        "id": "empty_ignored",
        "category": "ignore",
        "message": "",
        "expect_processed": False,
        "expected_status": "ignored_empty_message",
    },
]


def run_sam_meat_stress_pack(scenarios=None):
    scenarios = list(scenarios or STRESS_SCENARIOS)
    results = [evaluate_scenario(scenario) for scenario in scenarios]
    failures = [result for result in results if not result["passed"]]
    known_gaps = [result for result in results if result.get("known_gap")]
    category_counts = Counter(result["category"] for result in results)
    failure_counts = Counter(issue["type"] for result in failures for issue in result["blocking_issues"])
    return {
        "success": not failures,
        "scenario_count": len(results),
        "passed_count": len(results) - len(failures),
        "failed_count": len(failures),
        "known_gap_count": len(known_gaps),
        "category_counts": dict(sorted(category_counts.items())),
        "failure_counts": dict(sorted(failure_counts.items())),
        "results": results,
        "recommendations": stress_recommendations(results),
    }


def evaluate_scenario(scenario):
    payload = _payload_for(scenario)
    inbound = sam_meat_runtime.parse_chatwoot_inbound(payload)
    expect_processed = scenario.get("expect_processed", True)
    issues = []
    facts = {}
    decision = {}
    hygiene = {}

    if not expect_processed:
        expected_status = scenario.get("expected_status")
        if inbound.get("processable"):
            issues.append(_issue("processing", f"Expected ignored but was processable: {inbound.get('status')}"))
        if expected_status and inbound.get("status") != expected_status:
            issues.append(_issue("status", f"Expected status {expected_status}, got {inbound.get('status')}"))
        return _result(scenario, inbound, facts, decision, hygiene, issues)

    if not inbound.get("processable"):
        issues.append(_issue("processing", f"Expected processable but got {inbound.get('status')}"))
        return _result(scenario, inbound, facts, decision, hygiene, issues)

    facts = sam_meat_runtime.extract_meat_facts(inbound["content"], inbound, environ={})
    context = scenario.get("context") if isinstance(scenario.get("context"), dict) else {}
    prior_context = context.get("prior_context") if isinstance(context.get("prior_context"), dict) else {}
    booking_confirmation = context.get("booking_confirmation") if isinstance(context.get("booking_confirmation"), dict) else {}
    pop_capture = context.get("pop_capture") if isinstance(context.get("pop_capture"), dict) else {}
    decision = sam_meat_runtime.build_sam_meat_decision(inbound, facts, {"success": True}, 201)
    hygiene = build_sam_meat_chatwoot_hygiene_payload(
        lead_payload=sam_meat_runtime.build_sam_meat_lead_payload_from_inbound(inbound, facts),
        facts=facts,
        inbound=inbound,
        decision=decision,
        prior_context=prior_context,
        booking_confirmation=booking_confirmation,
        pop_capture=pop_capture,
    )

    _check_expected_facts(scenario, facts, issues)
    _check_reply(scenario, decision, issues)
    _check_labels(scenario, hygiene, issues)
    _check_attrs(scenario, hygiene, issues)
    _check_forbidden_reply(decision, issues)
    return _result(scenario, inbound, facts, decision, hygiene, issues)


def stress_recommendations(results):
    known_by_gap = defaultdict(list)
    for result in results:
        if result.get("known_gap"):
            known_by_gap[result["known_gap"]].append(result["id"])
    recommendations = []
    for gap, scenario_ids in sorted(known_by_gap.items()):
        recommendations.append({
            "priority": _gap_priority(gap),
            "gap": gap,
            "scenario_ids": scenario_ids,
        })
    return sorted(recommendations, key=lambda item: item["priority"])


def format_stress_summary(summary):
    lines = [
        "# Sam Meat Sales Stress-Test Run",
        "",
        f"- Scenarios: {summary['scenario_count']}",
        f"- Passed: {summary['passed_count']}",
        f"- Failed: {summary['failed_count']}",
        f"- Known improvement opportunities: {summary['known_gap_count']}",
        "",
        "## Category Coverage",
        "",
    ]
    for category, count in summary["category_counts"].items():
        lines.append(f"- `{category}`: {count}")
    lines.extend(["", "## Recommendations", ""])
    if not summary["recommendations"]:
        lines.append("- No known gaps recorded.")
    for item in summary["recommendations"]:
        lines.append(f"- P{item['priority']}: {item['gap']} Scenarios: {', '.join(item['scenario_ids'])}.")
    lines.extend(["", "## Failures", ""])
    failures = [result for result in summary["results"] if not result["passed"]]
    if not failures:
        lines.append("- No launch-blocking stress assertions failed.")
    for result in failures:
        lines.append(f"- `{result['id']}`:")
        for issue in result["blocking_issues"]:
            lines.append(f"  - {issue['type']}: {issue['message']}")
    return "\n".join(lines) + "\n"


def _payload_for(scenario):
    payload = {
        "event": "message_created",
        "message_type": "incoming",
        "content": scenario.get("message", ""),
        "conversation": {"id": 1808, "inbox": {"channel_type": "Channel::Whatsapp"}},
        "sender": {"id": 99, "name": "Stress Buyer", "phone_number": "+27820000000"},
        "account": {"id": 147387},
    }
    overrides = scenario.get("payload_overrides") if isinstance(scenario.get("payload_overrides"), dict) else {}
    for key, value in overrides.items():
        if key == "conversation" and isinstance(value, dict):
            payload["conversation"] = value
        else:
            payload[key] = value
    return payload


def _check_expected_facts(scenario, facts, issues):
    for key, expected in (scenario.get("expected_facts") or {}).items():
        actual = facts.get(key)
        if actual != expected:
            issues.append(_issue("fact", f"{key}: expected {expected!r}, got {actual!r}"))


def _check_reply(scenario, decision, issues):
    expected = scenario.get("expected_reply_any") or []
    if not expected:
        return
    reply = decision.get("reply_text", "")
    if not any(fragment.lower() in reply.lower() for fragment in expected):
        issues.append(_issue("reply", f"Reply missing one of {expected!r}; got {reply!r}"))


def _check_labels(scenario, hygiene, issues):
    labels = set(hygiene.get("labels") or [])
    for expected in scenario.get("expected_labels") or []:
        if expected not in labels:
            issues.append(_issue("label", f"Missing label {expected!r}; got {sorted(labels)!r}"))


def _check_attrs(scenario, hygiene, issues):
    attrs = hygiene.get("custom_attributes") or {}
    for key, expected in (scenario.get("expected_attrs") or {}).items():
        actual = attrs.get(key)
        if actual != expected:
            issues.append(_issue("attribute", f"{key}: expected {expected!r}, got {actual!r}"))


def _check_forbidden_reply(decision, issues):
    reply = decision.get("reply_text", "")
    for pattern in FORBIDDEN_REPLY_PATTERNS:
        if re.search(pattern, reply, re.I):
            issues.append(_issue("forbidden_reply", f"Forbidden pattern {pattern!r} matched reply {reply!r}"))


def _result(scenario, inbound, facts, decision, hygiene, issues):
    blocking_issues = _blocking_issues(scenario, issues)
    return {
        "id": scenario["id"],
        "category": scenario["category"],
        "passed": not blocking_issues,
        "known_gap": scenario.get("known_gap", ""),
        "issues": issues,
        "blocking_issues": blocking_issues,
        "status": inbound.get("status"),
        "facts": facts,
        "reply_text": decision.get("reply_text", ""),
        "labels": hygiene.get("labels", []),
        "custom_attributes": hygiene.get("custom_attributes", {}),
    }


def _issue(issue_type, message):
    return {"type": issue_type, "message": message}


def _blocking_issues(scenario, issues):
    if not scenario.get("known_gap"):
        return list(issues)
    always_blocking = {"processing", "status", "forbidden_reply"}
    return [issue for issue in issues if issue.get("type") in always_blocking]


def _gap_priority(gap):
    lower = gap.lower()
    if "not yet captured as a structured" in lower or "negated" in lower:
        return 1
    if "afrikaans" in lower or "typo" in lower or "maps" in lower:
        return 2
    return 3
