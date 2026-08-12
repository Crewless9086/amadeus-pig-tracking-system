from modules.oom_sakkie.gateway_authority import issue_gateway_owner_authority
from modules.oom_sakkie.herdmaster_breeding_exposure_runtime import (
    ACTION_KIND,
    handle_grouped_breeding_message,
)


def _parsed(rows):
    return {
        "telegram_user_id": "42", "telegram_chat_id": "42",
        "provider_message_id": "9001", "text": "grouped breeding facts",
        "semantic": {"domain": "herd_management", "evidence_generation": "GEN-1",
                     "breeding_actions": rows},
    }


def _evidence():
    return {"success": True, "allocation_inputs": {"pig_master_rows": [
        {"Pig_ID":"SOW-1","Tag_Number":"Ms Piggy"},
        {"Pig_ID":"SOW-2","Tag_Number":"Linda"},
        {"Pig_ID":"BOAR-1","Tag_Number":"Bola"},
    ]}}


def test_authenticated_group_creates_one_existing_rail_claim_and_no_write():
    captured = {}
    def claim_creator(**kwargs):
        captured.update(kwargs)
        return {"callback_token": "TOKEN", "preview_digest": "DIGEST"}
    result, status = handle_grouped_breeding_message(_parsed([
        {"animal_ref":"Ms Piggy","action":"recovery_hold",
         "body_condition_score":2,"observed_at":"2026-08-12T08:00:00+02:00",
         "factual_note":"Body condition scored 2."},
        {"animal_ref":"Linda","action":"near_farrowing",
         "observed_at":"2026-08-12T08:00:00+02:00",
         "factual_note":"Appears close to farrowing."},
    ]), issue_gateway_owner_authority("42", "42"), claim_creator=claim_creator,
        evidence_loader=_evidence)
    assert status == 200
    assert result["status"] == "breeding_grouped_preview_ready"
    assert captured["action_kind"] == ACTION_KIND
    assert captured["preview_payload"]["writes_performed"] is False
    assert result["writes_farm_data"] is False
    assert result["sends_telegram"] is False


def test_partial_group_fails_before_claim_or_write():
    called = []
    result, status = handle_grouped_breeding_message(_parsed([
        {"animal_ref":"Ms Piggy","action":"exposure","boar_ref":"Bola"},
    ]), issue_gateway_owner_authority("42", "42"),
        claim_creator=lambda **kwargs: called.append(kwargs), evidence_loader=_evidence)
    assert status == 200
    assert result["success"] is False
    assert called == []
    assert result["writes_farm_data"] is False


def test_ambiguous_identity_asks_one_question_before_claim():
    evidence = _evidence()
    evidence["allocation_inputs"]["pig_master_rows"].append(
        {"Pig_ID":"SOW-3","Tag_Number":"Linda"})
    result, status = handle_grouped_breeding_message(_parsed([
        {"animal_ref":"Linda","action":"near_farrowing",
         "observed_at":"2026-08-12T08:00:00+02:00","factual_note":"Close to farrowing."},
    ]), issue_gateway_owner_authority("42", "42"), evidence_loader=lambda: evidence)
    assert status == 200
    assert result["status"] == "breeding_identity_clarification_required"
    assert result["question_count"] == 1
    assert result["question_count"] == 1


def test_non_owner_is_fail_closed():
    parsed = _parsed([{"animal_ref":"Linda","action":"near_farrowing"}])
    parsed["telegram_chat_id"] = "99"
    result, status = handle_grouped_breeding_message(
        parsed, issue_gateway_owner_authority("42", "99"))
    assert status == 403
    assert result["writes_farm_data"] is False
