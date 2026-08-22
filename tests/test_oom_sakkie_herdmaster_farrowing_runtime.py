from modules.oom_sakkie.gateway_authority import issue_gateway_owner_authority
from modules.oom_sakkie.protected_action_claims import canonical_preview_digest
from modules.oom_sakkie import herdmaster_farrowing_runtime as litter_runtime
from modules.oom_sakkie.herdmaster_farrowing_runtime import (
    execute_claimed_farrowing_litter, handle_farrowing_litter_message,
)
from modules.pig_weights.herdmaster_farrowing_litter_intake import (
    ACTION_KIND, prepare_farrowing_litter_preview,
)


def parsed(facts=None):
    return {"text": "Linda had 9 total, 8 alive, 1 mummified. Log the litter.",
        "telegram_user_id": "42", "telegram_chat_id": "42",
        "provider_message_id": "TG-LINDA-CORRECTION", "provider_timestamp": "2026-08-22T07:30:00+02:00",
        "semantic": {"domain": "herd_management", "intent": "record_farrowing_litter",
            "farrowing_litter": facts or {"sow_ref": "Linda", "farrowing_date": "2026-08-22",
                "total_born": 9, "born_alive": 8, "stillborn": None, "mummified": 1,
                "died_after_live_birth": None, "mating_ref": None, "father_ref": None}}}


def evidence(**updates):
    value = {"evidence_generation": "GEN", "animals": [
        {"pig_id": "PIG-2026-5AA8", "tag_number": "Linda", "name": "Linda",
         "status": "Active", "on_farm": True, "sex": "Female"}],
        "matings": [], "litters": []}
    value.update(updates)
    return value


def test_corrected_linda_report_creates_dedicated_litter_claim_without_write():
    captured = {}
    def claim(**kwargs):
        captured.update(kwargs)
        return {"callback_token": "opaque", "preview_digest": "digest"}
    result, status = handle_farrowing_litter_message(parsed(),
        issue_gateway_owner_authority("42", "42"),
        evidence_loader=lambda **_: evidence(), claim_creator=claim)
    assert status == 200 and result["status"] == "farrowing_litter_preview_ready"
    assert result["action_kind"] == "herdmaster_record_farrowing_litter"
    assert captured["action_kind"] == "herdmaster_record_farrowing_litter"
    assert captured["preview_payload"]["counts"]["arithmetic"] == "9=8+0+1"
    assert captured["preview_payload"]["mating_id"] is None
    assert result["writes_farm_data"] is False


def test_duplicate_readback_contains_recovery_without_claim():
    result, status = handle_farrowing_litter_message(parsed(),
        issue_gateway_owner_authority("42", "42"), evidence_loader=lambda **_: evidence(litters=[
            {"litter_id": "LIT-EXISTS", "sow_pig_id": "PIG-2026-5AA8", "farrowing_date": "2026-08-22"}
        ]), claim_creator=lambda **_: (_ for _ in ()).throw(AssertionError("claim forbidden")))
    assert status == 409 and result["status"] == "canonical_litter_already_exists"
    assert result["writes_farm_data"] is False


def test_non_litter_semantic_intent_is_not_claimed():
    message = parsed()
    message["semantic"]["intent"] = "breeding_plan"
    result, status = handle_farrowing_litter_message(message,
        issue_gateway_owner_authority("42", "42"))
    assert status == 200 and result["handled"] is False


def _execute(monkeypatch, facts, canonical):
    prepared = prepare_farrowing_litter_preview({
        "authenticated": True, "authenticated_principal_id": "42",
        "provider_message_id": "TG-EXECUTE", "farrowing_litter": facts,
    }, canonical)
    assert prepared["success"] is True
    preview = prepared["preview"]
    monkeypatch.setattr(litter_runtime, "load_canonical_farrowing_evidence", lambda **_: canonical)
    monkeypatch.setattr(litter_runtime, "create_governed_farrowing_litter",
                        lambda preview, **_: {"success": True, "litter_id": "LIT-NEW",
                                              "writes_farm_data": True})
    monkeypatch.setattr(litter_runtime, "load_litter_readback", lambda *_args, **_kwargs: {
        "litter_id": "LIT-NEW", "total_born": preview["counts"]["total_born"]})
    claimed = {"preview_payload": preview,
               "preview_digest": canonical_preview_digest(ACTION_KIND, preview)}
    return execute_claimed_farrowing_litter(claimed, {"telegram_user_id": "42"})


def test_execute_preserves_correction_metadata_through_digest_refresh(monkeypatch):
    canonical = evidence(litters=[{"litter_id": "LIT-OLD", "sow_pig_id": "PIG-2026-5AA8",
                                   "farrowing_date": "2026-08-22"}])
    facts = parsed()["semantic"]["farrowing_litter"] | {
        "correction_of_litter_id": "LIT-OLD", "correction_reason": "Corrected birth counts"}
    result, status = _execute(monkeypatch, facts, canonical)
    assert status == 201 and result["success"] is True


def test_execute_resolves_matching_father_uuid_tag_and_name(monkeypatch):
    boar = {"pig_id": "BOAR-UUID", "tag_number": "B-17", "name": "Bola",
            "status": "Active", "on_farm": True, "sex": "Male"}
    mating = {"mating_id": "MAT-1", "sow_pig_id": "PIG-2026-5AA8",
              "boar_pig_id": "BOAR-UUID", "mating_date": "2026-04-30",
              "linked_litter_id": None}
    canonical = evidence(animals=evidence()["animals"] + [boar], matings=[mating])
    for father_ref in ("BOAR-UUID", "B-17", "Bola"):
        facts = parsed()["semantic"]["farrowing_litter"] | {"father_ref": father_ref}
        result, status = _execute(monkeypatch, facts, canonical)
        assert status == 201 and result["success"] is True


def test_execute_keeps_conflicting_or_no_mating_father_unknown(monkeypatch):
    animals = evidence()["animals"] + [
        {"pig_id": "BOAR-A", "tag_number": "A", "name": "Alpha", "status": "Active", "on_farm": True, "sex": "Male"},
        {"pig_id": "BOAR-B", "tag_number": "B", "name": "Beta", "status": "Active", "on_farm": True, "sex": "Male"},
    ]
    mating = {"mating_id": "MAT-1", "sow_pig_id": "PIG-2026-5AA8", "boar_pig_id": "BOAR-A",
              "mating_date": "2026-04-30", "linked_litter_id": None}
    for canonical in (evidence(animals=animals, matings=[mating]),
                      evidence(animals=animals, matings=[])):
        facts = parsed()["semantic"]["farrowing_litter"] | {"father_ref": "Beta"}
        prepared = prepare_farrowing_litter_preview({"authenticated": True,
            "authenticated_principal_id": "42", "provider_message_id": "TG-EXECUTE",
            "farrowing_litter": facts}, canonical)
        assert prepared["success"] is True
        assert prepared["preview"]["father_pig_id"] is None
        result, status = _execute(monkeypatch, facts, canonical)
        assert status == 201 and result["success"] is True
