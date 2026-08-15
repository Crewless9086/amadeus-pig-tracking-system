from modules.sales.sam_live_stock_sales_lifecycle import (
    build_sales_lifecycle_packet,
    execute_approved_reservation_and_delivery_once as _execute_approved_reservation_and_delivery_once,
    prepare_order_and_quote_once,
)
from modules.sales import sam_live_stock_runtime
from threading import Lock, Thread


def evidence(**overrides):
    data = {
        "inbound": {"account_id": "1", "inbox_id": "2", "contact_id": "3", "conversation_id": "4", "message_id": "9", "content": "We will take the quote"},
        "chronology": [{"id": "9", "created_at": "2026-08-08T08:00:00Z", "content": "We will take the quote"}],
        "retained_facts": {"quantity": 2, "sex": "female", "location": "Riversdale", "timing": "Monday", "payment_method": "Cash", "order_commitment": True},
        "inventory": {"eligible_projection": [
            {"pig_id": "P1", "live_stock_sale_eligible": True, "sale_category": "Weaner Piglets", "current_weight_kg": 12},
            {"pig_id": "P2", "live_stock_sale_eligible": True, "sale_category": "Weaner Piglets", "current_weight_kg": 13},
        ]},
        "pricing": {"price_entries": [{"sale_category": "Weaner Piglets", "unit_price": 600, "active": True, "price_id": "PRICE-1"}]},
        "order_state": {"order_id": "ORD-1", "selected_pig_ids": ["P1", "P2"], "active_line_count": 2},
        "document_state": {"document_id": "DOC-1", "current": True},
        "claims": [],
        "provider_identity": {"account_id": "1", "inbox_id": "2", "contact_id": "3", "conversation_id": "4", "provider_identity_class": "genuine_whatsapp"},
    }
    data.update(overrides)
    return data


def owner_authority(_approval, packet):
    return {
        "verified": True,
        "approval_id": "APPROVAL-1",
        "owner_principal": "owner:charl",
        "scope": "exact_reservation_and_current_quote_delivery",
        "evidence_digest": packet["evidence_digest"],
    }


def execute_approved_reservation_and_delivery_once(*args, **kwargs):
    kwargs.setdefault("verify_owner_authority", owner_authority)
    return _execute_approved_reservation_and_delivery_once(*args, **kwargs)


def test_long_english_and_afrikaans_acceptance_share_one_semantic_lifecycle():
    for text in ("We will take the quote", "Ons aanvaar die kwotasie"):
        values = evidence()
        values["inbound"] = {**values["inbound"], "content": text}
        values["chronology"] = [{"id": "9", "created_at": "2026-08-08T08:00:00Z", "content": text}]
        values["retained_facts"] = {**values["retained_facts"], "order_commitment": False}
        packet = build_sales_lifecycle_packet(**values)
        assert packet["accepted"] is True
        assert packet["state"] == "owner_decision_required"


def test_duplicate_provider_messages_do_not_change_packet_or_create_duplicate_order_pdf():
    values = evidence(order_state={"selected_pig_ids": ["P1", "P2"], "active_line_count": 2}, document_state={})
    values["chronology"] = values["chronology"] * 2
    packet = build_sales_lifecycle_packet(**values)
    calls = []
    result = prepare_order_and_quote_once(
        packet,
        create_order=lambda _: calls.append("order") or {"order_id": "ORD-2"},
        prepare_quote=lambda order_id: calls.append(f"quote:{order_id}") or {"document_id": "DOC-2"},
    )
    assert calls == ["order", "quote:ORD-2"]
    assert result["status"] == "owner_decision_required"
    existing = build_sales_lifecycle_packet(**evidence())
    calls.clear()
    second = prepare_order_and_quote_once(existing, create_order=lambda _: calls.append("order"), prepare_quote=lambda _: calls.append("quote"))
    assert calls == []
    assert second["created_order"] is False
    assert second["generated_quote"] is False


def test_only_missing_payment_is_requested_without_dropping_retained_facts():
    values = evidence()
    values["retained_facts"] = {**values["retained_facts"], "payment_method": ""}
    packet = build_sales_lifecycle_packet(**values)
    assert packet["missing_qualification"] == ["payment_method"]
    assert packet["retained_facts"]["quantity"] == 2
    assert packet["retained_facts"]["location"] == "Riversdale"


def test_changed_inventory_blocks_owner_execution():
    original = build_sales_lifecycle_packet(**evidence())
    changed_values = evidence()
    changed_values["inventory"] = {"eligible_projection": [changed_values["inventory"]["eligible_projection"][0]]}
    changed = build_sales_lifecycle_packet(**changed_values)
    calls = []
    result = execute_approved_reservation_and_delivery_once(
        {"decision": "approve", "evidence_digest": original["evidence_digest"]},
        current_packet_loader=lambda: changed,
        reserve=lambda *_: calls.append("reserve"),
        send_document=lambda *_: calls.append("send"),
        claim_effect=lambda *_: calls.append("claim"),
        record_effect_outcome=lambda *_: None,
    )
    assert result["status"] == "stale_owner_approval"
    assert calls == []


def test_owner_rejection_and_approval_are_exact_and_replay_safe():
    packet = build_sales_lifecycle_packet(**evidence())
    calls = []
    rejected = execute_approved_reservation_and_delivery_once(
        {"decision": "reject", "evidence_digest": packet["evidence_digest"]},
        current_packet_loader=lambda: packet,
        reserve=lambda *_: calls.append("reserve"),
        send_document=lambda *_: calls.append("send"),
        claim_effect=lambda *_: calls.append("claim"),
        record_effect_outcome=lambda *_: None,
    )
    assert rejected["status"] == "owner_rejected"
    assert calls == []
    completed = execute_approved_reservation_and_delivery_once(
        {"decision": "approve", "evidence_digest": packet["evidence_digest"]},
        current_packet_loader=lambda: packet,
        reserve=lambda order, pigs: calls.append((order, pigs)) or {"success": True},
        send_document=lambda doc, conv: calls.append((doc, conv)) or {"provider_confirmed": True, "delivery_state": "delivered", "attempt_id": "SAM-LIFECYCLE-PLACEHOLDER", "account_id": "1", "inbox_id": "2", "contact_id": "3", "conversation_id": conv, "provider_identity_class": "genuine_whatsapp"},
        claim_effect=lambda claim: {"created": True, "claim": claim, "attempt_id": "SAM-LIFECYCLE-PLACEHOLDER"},
        record_effect_outcome=lambda *_: None,
    )
    assert completed["status"] == "completed"
    assert completed["chatwoot_projection_allowed"] is True


def test_ambiguous_delivery_is_quarantined_without_retry():
    packet = build_sales_lifecycle_packet(**evidence())
    result = execute_approved_reservation_and_delivery_once(
        {"decision": "approve", "evidence_digest": packet["evidence_digest"]},
        current_packet_loader=lambda: packet,
        reserve=lambda *_: {"success": True},
        send_document=lambda *_: {"delivery_state": "accepted_unverified"},
        claim_effect=lambda claim: {"created": True, "claim": claim},
        record_effect_outcome=lambda *_: None,
    )
    assert result["status"] == "delivery_quarantined_do_not_retry"
    assert result["automatic_retry_prohibited"] is True


def test_cross_account_changed_chronology_and_farm_collection_fail_closed():
    values = evidence()
    values["provider_identity"] = {"account_id": "other", "inbox_id": "2", "provider_identity_class": "genuine_whatsapp"}
    packet = build_sales_lifecycle_packet(**values)
    assert "provider_account_id_mismatch" in packet["evidence_errors"]
    changed = evidence()
    changed["chronology"] = [{"id": "later", "created_at": "2026-08-08T08:01:00Z"}]
    assert "latest_inbound_chronology_mismatch" in build_sales_lifecycle_packet(**changed)["evidence_errors"]
    assert packet["farm_collection_allowed"] is False


def test_farm_collection_is_prohibited_and_other_location_needs_owner_exception():
    farm = evidence()
    farm["retained_facts"] = {**farm["retained_facts"], "location": "at the farm"}
    packet = build_sales_lifecycle_packet(**farm)
    assert packet["state"] == "handover_policy_blocked"
    assert "farm_collection_prohibited" in packet["evidence_errors"]
    other = evidence()
    other["retained_facts"] = {**other["retained_facts"], "location": "Worcester"}
    assert build_sales_lifecycle_packet(**other)["state"] == "owner_handover_exception_required"


def test_missing_stock_or_price_cannot_prepare_formal_quote():
    no_stock = evidence(order_state={"selected_pig_ids": ["P1", "P2"], "active_line_count": 2}, document_state={}, inventory={"eligible_projection": []})
    packet = build_sales_lifecycle_packet(**no_stock)
    calls = []
    result = prepare_order_and_quote_once(packet, create_order=lambda *_: calls.append("order"), prepare_quote=lambda *_: calls.append("quote"))
    assert result["status"] == "exact_or_supported_alternative_stock_required"
    assert calls == []
    no_price = evidence(order_state={"selected_pig_ids": ["P1", "P2"], "active_line_count": 2}, document_state={}, pricing={"price_entries": []})
    result = prepare_order_and_quote_once(build_sales_lifecycle_packet(**no_price), create_order=lambda *_: calls.append("order"), prepare_quote=lambda *_: calls.append("quote"))
    assert result["status"] == "canonical_price_evidence_required"
    assert calls == []


def test_replayed_approval_without_new_durable_claim_has_zero_effect():
    packet = build_sales_lifecycle_packet(**evidence())
    calls = []
    result = execute_approved_reservation_and_delivery_once(
        {"decision": "approve", "evidence_digest": packet["evidence_digest"]},
        current_packet_loader=lambda: packet,
        claim_effect=lambda _: {"created": False},
        record_effect_outcome=lambda *_: None,
        reserve=lambda *_: calls.append("reserve"),
        send_document=lambda *_: calls.append("send"),
    )
    assert result["status"] == "already_claimed_no_replay"
    assert calls == []


def test_bare_sent_is_ambiguous_and_reordered_evidence_keeps_digest():
    packet = build_sales_lifecycle_packet(**evidence())
    result = execute_approved_reservation_and_delivery_once(
        {"decision": "approve", "evidence_digest": packet["evidence_digest"]},
        current_packet_loader=lambda: packet,
        claim_effect=lambda claim: {"created": True, "attempt_id": claim["attempt_id"]},
        reserve=lambda *_: {"success": True},
        send_document=lambda *_: {"provider_confirmed": True, "delivery_state": "sent"},
        record_effect_outcome=lambda *_: None,
    )
    assert result["status"] == "delivery_quarantined_do_not_retry"
    reordered = evidence()
    reordered["inventory"] = {"eligible_projection": list(reversed(reordered["inventory"]["eligible_projection"]))}
    assert build_sales_lifecycle_packet(**reordered)["evidence_digest"] == packet["evidence_digest"]


def test_missing_provider_identity_and_missing_exact_line_ids_fail_closed():
    missing_provider = evidence(provider_identity={})
    packet = build_sales_lifecycle_packet(**missing_provider)
    assert "provider_account_id_required" in packet["evidence_errors"]
    no_lines = evidence(order_state={"order_id": "ORD-1", "active_line_count": 2})
    packet = build_sales_lifecycle_packet(**no_lines)
    assert packet["selected_animals"] == []
    assert packet["state"] == "corrective_replanning_required"


def test_integrated_english_and_afrikaans_acceptance_prepare_exactly_one_pdf():
    for text in ("We will take the quote", "Ons aanvaar die kwotasie"):
        inbound = evidence()["inbound"] | {"content": text}
        facts = sam_live_stock_runtime.extract_live_stock_facts(text, inbound)
        facts = sam_live_stock_runtime.merge_prior_live_stock_context(
            facts,
            {"quantity": 2, "sex": "female", "location": "Riversdale", "timing": "Monday", "payment_method": "Cash", "sales_lane": "live_stock_sales", "lane_confidence": 0.99},
        )
        packet = build_sales_lifecycle_packet(**evidence(inbound=inbound, chronology=[{"id": "9", "created_at": "2026-08-08T08:00:00Z", "content": text}], retained_facts=facts))
        calls = []
        result = prepare_order_and_quote_once(packet, create_order=lambda *_: calls.append("order"), prepare_quote=lambda *_: calls.append("quote"))
        assert result["status"] == "owner_decision_required"
        assert calls == []  # Existing exact order and current PDF are reused.


def test_concurrent_owner_approval_has_one_claim_and_one_effect_sequence():
    packet = build_sales_lifecycle_packet(**evidence())
    lock = Lock()
    claimed = set()
    effects = []
    results = []

    def claim(value):
        with lock:
            if value["attempt_id"] in claimed:
                return {"created": False}
            claimed.add(value["attempt_id"])
            return {"created": True, "attempt_id": value["attempt_id"]}

    def run(approval_id):
        results.append(execute_approved_reservation_and_delivery_once(
            {"decision": "approve", "evidence_digest": packet["evidence_digest"], "approval_id": approval_id},
            current_packet_loader=lambda: packet,
            verify_owner_authority=lambda approval, current: {
                "verified": True,
                "approval_id": approval["approval_id"],
                "owner_principal": f"owner:{approval['approval_id']}",
                "scope": "exact_reservation_and_current_quote_delivery",
                "evidence_digest": current["evidence_digest"],
            },
            claim_effect=claim,
            reserve=lambda *_: effects.append("reserve") or {"success": True},
            send_document=lambda *_: effects.append("send") or {"delivery_state": "accepted_unverified"},
            record_effect_outcome=lambda *_: None,
        ))

    threads = [Thread(target=run, args=("APPROVAL-A",)), Thread(target=run, args=("APPROVAL-B",))]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert effects == ["reserve", "send"]
    assert sorted(result["status"] for result in results) == ["already_claimed_no_replay", "delivery_quarantined_do_not_retry"]


def test_owner_authority_and_complete_delivery_identity_are_mandatory():
    packet = build_sales_lifecycle_packet(**evidence())
    calls = []
    result = _execute_approved_reservation_and_delivery_once(
        {"decision": "approve", "evidence_digest": packet["evidence_digest"]},
        current_packet_loader=lambda: packet,
        verify_owner_authority=lambda *_: {"verified": False},
        claim_effect=lambda *_: calls.append("claim"),
        reserve=lambda *_: calls.append("reserve"),
        send_document=lambda *_: calls.append("send"),
        record_effect_outcome=lambda *_: None,
    )
    assert result["status"] == "owner_authority_unverified"
    assert calls == []
    for field in ("account_id", "inbox_id", "contact_id"):
        result = execute_approved_reservation_and_delivery_once(
            {"decision": "approve", "evidence_digest": packet["evidence_digest"]},
            current_packet_loader=lambda: packet,
            claim_effect=lambda _claim: {"created": True, "attempt_id": "ATTEMPT"},
            reserve=lambda *_: {"success": True},
            send_document=lambda _doc, conv, field=field: {
                "provider_confirmed": True,
                "delivery_state": "delivered",
                "attempt_id": "ATTEMPT",
                "account_id": "1",
                "inbox_id": "2",
                "contact_id": "3",
                "conversation_id": conv,
                "provider_identity_class": "genuine_whatsapp",
                field: "wrong",
            },
            record_effect_outcome=lambda *_: None,
        )
        assert result["status"] == "delivery_quarantined_do_not_retry"
        assert result.get("chatwoot_projection_allowed") is not True
