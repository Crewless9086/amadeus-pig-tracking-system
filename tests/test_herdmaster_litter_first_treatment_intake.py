import pytest
from types import SimpleNamespace
from unittest.mock import patch

from modules.oom_sakkie.herdmaster_litter_first_treatment_runtime import (
    handle_litter_first_treatment_message,
)
from modules.pig_weights.herdmaster_litter_first_treatment_intake import (
    prepare_litter_first_treatment_preview,
)


def canonical(*, litters=None, animals=None):
    return {"evidence_generation": "GEN-1", "animals": animals or [
        {"pig_id": "PIG-MOLLY", "tag_number": "146", "name": "Molly"}],
        "litters": litters or [{"litter_id": "LIT-MOLLY", "sow_pig_id": "PIG-MOLLY",
            "litter_status": "Active", "active_count": 8, "detail": {"piglets": [
                {"pig_id": f"PIG-{number}", "status": "Active", "on_farm": True}
                for number in range(8)]}}],
        "products": [{"product_id": "PROD-IRON", "product_name": "Iron Plus", "active": True}]}


def report(**overrides):
    facts = {"sow_ref": "Molly", "action_date": "2026-08-25", "male_count": 4,
        "female_count": 4, "total_count": 8, "earmarked": True,
        "antiparasitic_product_ref": "Iron Plus", "dose": "1 ml",
        "route": "injection", "batch_lot_number": "LOT-7"}
    facts.update(overrides)
    return {"authenticated": True, "authenticated_principal_id": "ANTON",
            "provider_message_id": "TG-1", "litter_first_treatment": facts}


def test_retains_exact_sow_litter_and_canonical_active_membership():
    result = prepare_litter_first_treatment_preview(report(), canonical())
    assert result["success"] is True
    assert result["preview"] | {"x": 1}
    assert result["preview"]["total_count"] == 8
    assert result["preview"]["pig_ids"] == [f"PIG-{number}" for number in range(8)]
    assert result["preview"]["sow_pig_id"] == "PIG-MOLLY"
    assert result["preview"]["litter_id"] == "LIT-MOLLY"


@pytest.mark.parametrize("change", [
    {"antiparasitic_product_ref": None}, {"dose": None}, {"route": None},
    {"batch_lot_number": None},
])
def test_missing_medical_details_are_one_question_and_never_inferred(change):
    result = prepare_litter_first_treatment_preview(report(**change), canonical())
    assert result["success"] is False
    assert result["question"] == "Which exact product, dose, route and batch did you use?"


def test_multiple_active_litters_fail_closed():
    result = prepare_litter_first_treatment_preview(report(), canonical(litters=[
        {"litter_id": "L1", "sow_pig_id": "PIG-MOLLY", "litter_status": "Active", "active_count": 8},
        {"litter_id": "L2", "sow_pig_id": "PIG-MOLLY", "litter_status": "Active", "active_count": 8}]))
    assert result["status"] == "exactly_one_active_litter_required"


def test_distinct_matching_sows_remain_ambiguous():
    result = prepare_litter_first_treatment_preview(report(), canonical(animals=[
        {"pig_id": "P1", "name": "Molly"}, {"pig_id": "P2", "name": "Molly"}]))
    assert result["status"] == "sow_identity_required"


def test_natural_report_does_not_require_owner_to_repeat_litter_tally():
    result = prepare_litter_first_treatment_preview(report(
        male_count=None, female_count=None, total_count=None), canonical())
    assert result["success"] is True
    assert result["preview"]["total_count"] == 8


def test_telegram_first_treatment_builds_one_protected_preview_without_writing():
    parsed = {"telegram_user_id": "ANTON", "telegram_chat_id": "ANTON",
        "provider_message_id": "TG-1", "semantic": {
            "intent": "record_litter_first_treatment",
            "litter_first_treatment": report()["litter_first_treatment"]}}
    created = []
    with patch("modules.oom_sakkie.herdmaster_litter_first_treatment_runtime.validates_gateway_owner_authority",
               return_value=True):
        result, status = handle_litter_first_treatment_message(parsed,
            SimpleNamespace(capabilities=("treatment",)),
            evidence_loader=lambda **_kwargs: canonical(),
            claim_creator=lambda **kwargs: (created.append(kwargs) or {
                "callback_token": "TOKEN", "preview_digest": "DIGEST"}))
    assert status == 200 and result["status"] == "litter_first_treatment_preview_ready"
    assert result["writes_farm_data"] is False and len(created) == 1
    assert created[0]["action_kind"] == "herdmaster_record_litter_first_treatment"
    assert "Molly" in result["answer"]


def test_first_treatment_never_cross_routes_as_farrowing():
    parsed = {"telegram_user_id": "ANTON", "telegram_chat_id": "ANTON",
        "semantic": {"intent": "record_farrowing_litter",
            "farrowing_litter": {"sow_ref": "Molly"}}}
    result, status = handle_litter_first_treatment_message(parsed,
        SimpleNamespace(capabilities=("treatment",)))
    assert status == 200
    assert result == {"handled": False, "status": "litter_first_treatment_not_applicable"}
