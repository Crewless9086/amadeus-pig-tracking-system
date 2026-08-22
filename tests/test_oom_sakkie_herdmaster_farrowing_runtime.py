from modules.oom_sakkie.gateway_authority import issue_gateway_owner_authority
from modules.oom_sakkie.herdmaster_farrowing_runtime import handle_farrowing_litter_message


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
        {"pig_id": "PIG-2026-5AA8", "tag_number": "Linda", "name": "Linda"}],
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
