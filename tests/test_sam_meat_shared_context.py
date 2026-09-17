from unittest.mock import Mock, patch

from modules.sales import sam_meat_runtime
from modules.oom_sakkie.sales_campaign_store import build_sam_meat_intake_lead_payload
from modules.sales.sam_customer_context import canonical_customer_identity
from modules.sales.sam_meat_runtime import (
    _merge_lead_contexts,
    _merge_prior_context,
    _with_fact_provenance,
    build_sam_meat_lead_payload_from_inbound,
)
from modules.sales.sam_shared_context import build_sam_v3_context_packet


def test_same_verified_customer_identity_is_persisted_in_existing_meat_interest():
    inbound = {
        "account_id": "147387",
        "contact_id": "widget-contact",
        "customer_phone": "+27 82 123 4567",
        "customer_name": "Customer",
        "conversation_id": "web-42",
        "channel": "Channel::WebWidget",
    }
    identity = canonical_customer_identity(inbound)
    payload = build_sam_meat_lead_payload_from_inbound(inbound, {"product_type": "half_carcass"})
    payload["canonical_customer_id"] = identity["canonical_customer_id"]
    lead_payload, contract = build_sam_meat_intake_lead_payload(payload)

    assert contract["lane"] == "meat_preorder"
    assert lead_payload["interest"]["canonical_customer_id"] == identity["canonical_customer_id"]
    assert "customer_phone" not in lead_payload["interest"]
    assert contract["authority"]["creates_order"] is False
    assert contract["authority"]["changes_stock"] is False
    assert contract["authority"]["sends_customer_message"] is False


def test_current_conversation_correction_wins_and_conflict_is_retained():
    retained = {
        "lead_id": "lead-1",
        "interest": {"delivery_town": "Riversdale", "cut_set": "Set A", "timing": "September"},
        "source": "supabase.oom_sakkie_sales_leads_and_events",
    }
    current = {"lead_id": "lead-1", "interest": {"delivery_town": "Albertinia"}}
    merged = _merge_lead_contexts(current, retained)

    assert merged["interest"] == {
        "delivery_town": "Albertinia", "cut_set": "Set A", "timing": "September",
    }
    assert merged["provenance"]["conflicts"] == [{
        "field": "delivery_town",
        "retained_value": "Riversdale",
        "current_value": "Albertinia",
        "resolution": "current_conversation_evidence",
    }]


def test_retained_meat_facts_fill_unknowns_without_overwriting_current_evidence():
    facts = {"product_type": "unknown", "cut_set": "", "location": "Albertinia"}
    retained = {
        "interest": {
            "product_type": "half_carcass", "cut_set": "Set B",
            "location": "Riversdale", "timing": "September",
        }
    }
    merged = _merge_prior_context(facts, retained)
    assert merged["product_type"] == "half_carcass"
    assert merged["cut_set"] == "Set B"
    assert merged["location"] == "Albertinia"
    assert merged["timing"] == "September"


def test_shared_packet_exposes_refs_and_provenance_without_granting_protected_actions():
    prior = {
        "lead_id": "lead-1",
        "linked_preorder_id": "pre-1",
        "linked_order_id": "order-1",
        "interest": {"product_type": "half_carcass", "cut_set": "Set C"},
        "provenance": {"status": "retained", "conflicts": []},
    }
    packet = build_sam_v3_context_packet(
        {"content": "Dankie", "conversation_id": "web-42", "channel": "Channel::WebWidget"},
        prior,
        environ={},
    )
    assert packet["lead"]["linked_preorder_id"] == "pre-1"
    assert packet["lead"]["linked_order_id"] == "order-1"
    assert packet["lead"]["provenance"]["status"] == "retained"
    assert "confirm_payment_without_bank_receipt" in packet["blocked_actions"]
    assert "reserve_stock_without_gate" in packet["blocked_actions"]


def test_field_provenance_distinguishes_supplied_retained_derived_unknown_and_conflict():
    context = _with_fact_provenance(
        {"interest": {"delivery_town": "Riversdale", "timing": "September"}},
        {"delivery_town": "Albertinia", "payment_method": "EFT", "product_type": "unknown"},
        {"delivery_town": "Albertinia", "timing": "September", "payment_method": "EFT"},
        "Please deliver to Albertinia",
    )
    evidence = context["provenance"]["field_evidence"]
    assert evidence["delivery_town"]["status"] == "supplied"
    assert evidence["timing"]["status"] == "retained"
    assert evidence["payment_method"]["status"] == "derived"
    assert evidence["cut_set"]["status"] == "unknown"
    assert context["provenance"]["conflicts"][0]["resolution"] == "current_message_evidence"


@patch("modules.sales.sam_meat_runtime.get_sales_lead_preorder_contract")
@patch("modules.sales.sam_meat_runtime.record_sam_meat_intake_lead")
def test_generic_continuation_uses_retained_meat_lane_without_reasking_known_facts(record_lead, contract):
    record_lead.return_value = ({"success": True, "lead_id": "lead-1", "contract": {}}, 201)
    contract.return_value = ({"success": True, "contract": {"contract_status": "needs_owner_confirmation"}}, 200)
    payload = {
        "event": "message_created", "message_type": "incoming", "content": "Hi Sam",
        "conversation": {"id": 42, "inbox": {"channel_type": "Channel::WebWidget"}},
        "sender": {"id": 9, "name": "Customer", "phone_number": "+27821234567"},
        "account": {"id": 147387},
    }
    retained = {
        "lead_id": "lead-1",
        "interest": {
            "product_type": "half_carcass", "cut_set": "Set B",
            "delivery_town": "Riversdale", "timing": "September",
        },
        "source": "supabase.oom_sakkie_sales_leads_and_events",
    }
    result, status = sam_meat_runtime.handle_sam_meat_chatwoot_inbound(
        payload,
        environ={"SAM_MEAT_BACKEND_AUTOREPLY_ENABLED": "0"},
        chatwoot_sender=Mock(),
        retained_context_loader=lambda _inbound, _identity: retained,
    )

    assert status == 200
    assert result["processed"] is True
    assert result["status"] != "sam_meat_general_first_withheld"
    written = record_lead.call_args.args[0]
    assert written["lead_id"] == "lead-1"
    assert written["product_type"] == "half_carcass"
    assert written["cut_set"] == "Set B"
    assert written["delivery_town"] == "Riversdale"
    assert written["timing"] == "September"
    assert result["sent"] is False
