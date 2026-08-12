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


def test_authenticated_group_creates_one_existing_rail_claim_and_no_write():
    captured = {}
    def claim_creator(**kwargs):
        captured.update(kwargs)
        return {"callback_token": "TOKEN", "preview_digest": "DIGEST"}
    result, status = handle_grouped_breeding_message(_parsed([
        {"pig_id":"SOW-1","label":"Ms Piggy","action":"recovery_hold",
         "body_condition_score":2,"observed_at":"2026-08-12T08:00:00+02:00",
         "factual_note":"Body condition scored 2."},
        {"pig_id":"SOW-2","label":"Linda","action":"near_farrowing",
         "observed_at":"2026-08-12T08:00:00+02:00",
         "factual_note":"Appears close to farrowing."},
    ]), issue_gateway_owner_authority("42", "42"), claim_creator=claim_creator)
    assert status == 200
    assert result["status"] == "breeding_grouped_preview_ready"
    assert captured["action_kind"] == ACTION_KIND
    assert captured["preview_payload"]["writes_performed"] is False
    assert result["writes_farm_data"] is False
    assert result["sends_telegram"] is False


def test_partial_group_fails_before_claim_or_write():
    called = []
    result, status = handle_grouped_breeding_message(_parsed([
        {"pig_id":"SOW-1","action":"exposure","boar_pig_id":"BOAR-1"},
    ]), issue_gateway_owner_authority("42", "42"),
        claim_creator=lambda **kwargs: called.append(kwargs))
    assert status == 200
    assert result["success"] is False
    assert called == []
    assert result["writes_farm_data"] is False
    assert result["question_count"] == 1


def test_non_owner_is_fail_closed():
    parsed = _parsed([])
    parsed["telegram_chat_id"] = "99"
    result, status = handle_grouped_breeding_message(
        parsed, issue_gateway_owner_authority("42", "99"))
    assert status == 403
    assert result["writes_farm_data"] is False
