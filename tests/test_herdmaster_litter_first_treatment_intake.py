import pytest
from types import SimpleNamespace

from modules.oom_sakkie.herdmaster_litter_first_treatment_runtime import (
    handle_litter_first_treatment_message,
)
from modules.pig_weights.herdmaster_litter_first_treatment_intake import (
    prepare_litter_first_treatment_preview,
)


def canonical(*, litters=None, animals=None):
    return {"evidence_generation": "GEN-1", "animals": animals or [
        {"pig_id": "PIG-SYNTHETIC-CEDAR", "tag_number": "146", "name": "Synthetic Cedar"}],
        "litters": litters or [{"litter_id": "LIT-SYNTHETIC-CEDAR", "sow_pig_id": "PIG-SYNTHETIC-CEDAR",
            "litter_status": "Active", "active_count": 8, "farrowing_date": "2026-08-20", "detail": {"piglets": [
                {"pig_id": f"PIG-{number}", "status": "Active", "on_farm": True}
                for number in range(8)]}}],
        "products": [{"product_id": "PROD-IRON", "product_name": "Iron Plus", "active": True}]}


def report(**overrides):
    facts = {"sow_ref": "Synthetic Cedar", "action_date": "2026-08-25", "male_count": 4,
        "female_count": 4, "total_count": 8, "earmarked": True,
        "antiparasitic_product_ref": "Iron Plus", "dose": "1 ml",
        "route": "injection", "batch_lot_number": "LOT-7"}
    facts.update(overrides)
    return {"authenticated": True, "authenticated_principal_id": "SYNTHETIC-MANAGER",
            "provider_message_id": "TG-1", "litter_first_treatment": facts}


def test_retains_exact_sow_litter_and_canonical_active_membership():
    result = prepare_litter_first_treatment_preview(report(), canonical())
    assert result["success"] is True
    assert result["preview"]["total_count"] == 8
    assert result["preview"]["pig_ids"] == [f"PIG-{number}" for number in range(8)]
    assert result["preview"]["sow_pig_id"] == "PIG-SYNTHETIC-CEDAR"
    assert result["preview"]["litter_id"] == "LIT-SYNTHETIC-CEDAR"


@pytest.mark.parametrize("change", [
    {"antiparasitic_product_ref": None}, {"dose": None}, {"route": None},
    {"batch_lot_number": None},
])
def test_missing_medical_details_are_one_question_and_never_inferred(change):
    result = prepare_litter_first_treatment_preview(report(**change), canonical())
    assert result["success"] is False
    assert result["status"] == "medical_details_required"
    assert result["missing"]


def test_multiple_active_litters_fail_closed():
    result = prepare_litter_first_treatment_preview(report(), canonical(litters=[
        {"litter_id": "L1", "sow_pig_id": "PIG-SYNTHETIC-CEDAR", "litter_status": "Active", "active_count": 8},
        {"litter_id": "L2", "sow_pig_id": "PIG-SYNTHETIC-CEDAR", "litter_status": "Active", "active_count": 8}]))
    assert result["status"] == "exactly_one_active_litter_required"


def test_distinct_matching_sows_remain_ambiguous():
    result = prepare_litter_first_treatment_preview(report(), canonical(animals=[
        {"pig_id": "P1", "name": "Synthetic Cedar"}, {"pig_id": "P2", "name": "Synthetic Cedar"}]))
    assert result["status"] == "sow_identity_required"


def test_natural_report_does_not_require_owner_to_repeat_litter_tally():
    result = prepare_litter_first_treatment_preview(report(
        male_count=None, female_count=None, total_count=None), canonical())
    assert result["success"] is True
    assert result["preview"]["total_count"] == 8


def test_first_treatment_never_cross_routes_as_farrowing():
    parsed = {"telegram_user_id": "SYNTHETIC-MANAGER", "telegram_chat_id": "SYNTHETIC-MANAGER",
        "semantic": {"intent": "record_farrowing_litter",
            "farrowing_litter": {"sow_ref": "Synthetic Cedar"}}}
    result, status = handle_litter_first_treatment_message(parsed,
        SimpleNamespace(capabilities=("treatment",)))
    assert status == 200
    assert result["handled"] is False

@pytest.mark.parametrize("dose,unit,expected", [("1 ml",None,(1,"ml")),("1,5 ml",None,(1.5,"ml")),(1,"ml",(1,"ml"))])
def test_reported_dose_preserved_instead_of_product_default(dose,unit,expected):
    evidence = canonical()
    evidence['products'][0].update(default_dose=2,dose_unit='ml')
    result = prepare_litter_first_treatment_preview(report(dose=dose,dose_unit=unit),evidence)
    assert result['success'] and (result['preview']['dose'],result['preview']['dose_unit']) == expected


@pytest.mark.parametrize("facts", [
    {'action_date':'2099-01-01'},{'action_date':'2026-08-19'},{'action_date':'20260825'},
    {'dose':True},{'dose':-1},{'dose':float('inf')},{'dose':'1 mg','dose_unit':'ml'},
    {'male_count':1},{'total_count':7},{'earmarked':'true'},
])
def test_invalid_supplied_facts_never_become_a_preview(facts):
    result = prepare_litter_first_treatment_preview(report(**facts),canonical())
    assert not result['success'] and result['writes_farm_data'] is False


def test_missing_unit_is_asked_unless_product_supplies_one_reference_unit():
    evidence = canonical()
    result = prepare_litter_first_treatment_preview(report(dose=1),evidence)
    assert result['missing'] == ['dose_unit']
    evidence['products'][0]['dose_unit'] = 'ml'
    result = prepare_litter_first_treatment_preview(report(dose=1),evidence)
    assert result['success'] and result['preview']['dose_unit'] == 'ml'


def test_known_individual_sexes_cannot_be_contradicted_by_aggregate_tally():
    evidence = canonical()
    for pig in evidence['litters'][0]['detail']['piglets'][:5]:
        pig['sex'] = 'Male'
    assert prepare_litter_first_treatment_preview(report(),evidence)['status'] == 'reported_treatment_tally_conflict'
