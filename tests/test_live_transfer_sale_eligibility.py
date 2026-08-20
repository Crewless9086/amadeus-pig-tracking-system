from modules.pig_weights.pig_weights_service import _live_stock_sale_eligibility


def eligible_pig(**overrides):
    pig = {
        "pig_id": "PIG-2026-B156",
        "tag_number": "151",
        "status": "Active",
        "on_farm": True,
        "purpose": "Sale",
        "sex": "Male",
        "animal_type": "Piglet",
        "calculated_stage": "Weaner",
        "latest_weight_kg": 4.0,
        "latest_weight_date": "2026-08-19",
        "days_since_weight": 0,
        "wean_date": "2026-08-18",
        "allocation_query_status": "known",
        "allocation_evidence_state": "known_unallocated",
        "reserved_status": "Not_Reserved",
        "reserved_for_order_id": "",
        "withdrawal_evidence_state": "hold",
        "current_withdrawal_end_date": "2026-09-08",
        "health_status": "Clear",
        "medical_status": "Withdrawal hold",
        "hold_status": "withdrawal",
    }
    pig.update(overrides)
    return pig


def test_tag_151_shape_is_live_transfer_eligible_during_food_chain_withdrawal():
    result = _live_stock_sale_eligibility(eligible_pig())

    assert result["eligible"] is True
    assert result["withdrawal_evidence_state"] == "hold"
    assert result["withdrawal_clear"] == "No"
    assert result["weight_band"] == "2_to_4_Kg"
    assert "Food-chain withdrawal remains a separate" in result["reason"]


def test_withdrawal_wording_on_health_axis_is_not_a_live_transfer_hold():
    result = _live_stock_sale_eligibility(
        eligible_pig(health_status="Withdrawal hold", medical_status="Withdrawal hold")
    )

    assert result["eligible"] is True


def test_genuine_lifecycle_reservation_health_and_source_conflicts_remain_blockers():
    cases = [
        (eligible_pig(status="Sold", on_farm=False), "not_active"),
        (eligible_pig(on_farm=False), "not_on_farm"),
        (eligible_pig(reserved_for_order_id="ORD-OTHER"), "reserved"),
        (eligible_pig(health_status="Injured - hold"), "health_hold"),
        (eligible_pig(hold_status="movement hold"), "sale_hold"),
        (eligible_pig(allocation_query_status="conflicting"), "allocation_evidence_unavailable"),
        (eligible_pig(allocation_evidence_state="source_conflict"), "allocated_or_unknown"),
    ]

    for pig, code in cases:
        result = _live_stock_sale_eligibility(pig)
        assert result["eligible"] is False
        assert code in result["status"]

