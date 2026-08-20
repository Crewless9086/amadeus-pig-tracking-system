from datetime import datetime, timezone

import pytest

from modules.orders.livestock_quotation import (
    build_quotation_preview, classify_quotation_intent, conversion_refresh_request,
    issue_quotation, quotation_state,
)
from modules.sales.sam_live_stock_understanding import classify_message_intent


NOW = datetime(2026, 8, 19, 8, 0, tzinfo=timezone.utc)
WENETTITUS = [
    {"request_item_key": "female_5_6", "category": "Piglet", "weight_range": "5_to_6_Kg", "sex": "Female", "quantity": 10},
    {"request_item_key": "male_5_6", "category": "Piglet", "weight_range": "5_to_6_Kg", "sex": "Male", "quantity": 10},
    {"request_item_key": "female_15", "category": "Weaner Piglets", "weight_range": "15_to_19_Kg", "sex": "Female", "quantity": 1},
    {"request_item_key": "male_15", "category": "Weaner Piglets", "weight_range": "15_to_19_Kg", "sex": "Male", "quantity": 1},
]


def price(category, band, sex, as_of=None):
    amount = 400 if band == "5_to_6_Kg" else 600
    return {"found": True, "pricing_id": f"PRICE-{band}", "unit_price": amount, "currency": "ZAR", "effective_from": "2026-08-01T00:00:00+00:00", "source": "supabase"}


def test_exact_wenettitus_funding_shape_never_calls_herdmaster():
    def forbidden(*args):
        raise AssertionError("funding quotation must not run allocation")
    preview = build_quotation_preview(
        {"journey": "budgetary_quotation", "requested_items": WENETTITUS},
        price_resolver=price, herdmaster_preview_builder=forbidden, herdmaster_packet={"pigs": []}, now=NOW,
    )
    assert preview["subtotal_ex_vat"] == 9200
    assert preview["vat_amount"] == 1380
    assert preview["total"] == 10580
    assert preview["allocation_proposal"] is None
    assert preview["selects_animals"] is False
    assert preview["creates_order"] is False
    assert preview["creates_reservation"] is False


def test_price_indication_answers_direct_price_with_quantity_and_totals():
    preview = build_quotation_preview(
        {"journey": "price_indication", "requested_items": [WENETTITUS[0]]}, price_resolver=price, now=NOW,
    )
    assert preview["lines"][0]["quantity"] == 10
    assert preview["lines"][0]["unit_price"] == 400
    assert preview["lines"][0]["subtotal"] == 4000
    assert preview["document_default"] is False
    assert "availability promise" in preview["authority_boundary"]


def test_sales_quotation_is_the_only_journey_that_calls_herdmaster():
    calls = []
    def allocation(items, packet):
        calls.append((items, packet))
        return {"recommendations": [], "creates_reservation": False}
    preview = build_quotation_preview(
        {"journey": "sales_quotation", "quotation_basis": "current_availability", "requested_items": [WENETTITUS[0]]},
        price_resolver=price, herdmaster_preview_builder=allocation, herdmaster_packet={"packet_digest": "abc"}, now=NOW,
    )
    assert len(calls) == 1
    assert preview["allocation_proposal"]["creates_reservation"] is False


def test_issue_snapshot_validity_supersession_expiry_and_conversion_refresh():
    preview = build_quotation_preview(
        {"journey": "budgetary_quotation", "requested_items": WENETTITUS}, price_resolver=price, now=NOW,
    )
    issued = issue_quotation(preview, validity_days=3, now=NOW, issued_by="Terminal Sales")
    assert issued["valid_until"] == "2026-08-22"
    assert issued["snapshot"]["lines"][0]["unit_price"] == 400
    assert quotation_state(issued, now=NOW) == "current"
    assert quotation_state(issued, now=datetime(2026, 8, 23, tzinfo=timezone.utc)) == "expired"
    issued["superseded_by_quotation_id"] = "LQ-NEW"
    assert quotation_state(issued, now=NOW) == "superseded"
    refresh = conversion_refresh_request(issued)
    assert refresh["required_refreshes"] == ["effective_price", "current_availability"]
    assert refresh["carries_allocation_forward"] is False
    assert refresh["carries_reservation_forward"] is False


def test_semantic_intent_separates_funding_availability_and_direct_price():
    assert classify_quotation_intent("Please prepare a quotation for funding approval") == "budgetary_quotation"
    assert classify_quotation_intent("Which pigs are available now?") == "sales_quotation"
    assert classify_quotation_intent("How much are 5 kg piglets?") == "price_indication"
    assert classify_message_intent("Quotation needed for funding approval") == "budgetary_quotation"
    assert classify_message_intent("Which pigs are available now?") == "current_availability_quotation"
    assert classify_message_intent("How much are the 5 kg piglets?") == "price_indication"


@pytest.mark.parametrize("journey", ["price_indication", "budgetary_quotation"])
def test_non_sales_journeys_reject_availability_basis(journey):
    with pytest.raises(ValueError, match="only valid"):
        build_quotation_preview({"journey": journey, "quotation_basis": "current_availability", "requested_items": WENETTITUS}, price_resolver=price)
