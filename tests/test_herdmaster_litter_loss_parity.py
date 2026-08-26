from types import SimpleNamespace
from unittest.mock import patch

from modules.oom_sakkie.herdmaster_litter_loss_runtime import (
    handle_litter_loss_message,
)
from modules.pig_weights.herdmaster_litter_loss_action import (
    prepare_litter_loss_preview,
)


def canonical(piglets=None):
    return {
        "evidence_generation": "LOSS-GEN-1",
        "animals": [{"pig_id": "SOW-LINDA", "name": "Linda",
                     "tag_number": "Linda"}],
        "litters": [{"litter_id": "LIT-LINDA", "sow_pig_id": "SOW-LINDA",
            "litter_status": "Active", "detail": {"piglets": piglets or [
                {"pig_id": "P1", "tag_number": "01", "sex": "Male",
                 "status": "Active", "on_farm": True},
                {"pig_id": "P2", "tag_number": "02", "sex": "Male",
                 "status": "Active", "on_farm": True},
                {"pig_id": "P3", "tag_number": "03", "sex": "Female",
                 "status": "Active", "on_farm": True},
                {"pig_id": "P4", "tag_number": "04", "sex": "Female",
                 "status": "Active", "on_farm": True},
                {"pig_id": "P5", "tag_number": "05", "sex": "",
                 "status": "Active", "on_farm": True},
            ]}}],
    }


def base_facts(**changes):
    value = {"sow_ref": "Linda", "event_date": "2026-08-26",
             "count": 3, "source_event_ids": ["4052", "4054"]}
    value.update(changes)
    return value


def test_retained_three_asks_only_for_missing_sex_split():
    result = prepare_litter_loss_preview(base_facts(), canonical())
    assert result["status"] == "litter_loss_sex_split_required"
    assert result["known_count"] == 3
    assert result["known_event_date"] == "2026-08-26"
    assert "male" in result["question"] and "female" in result["question"]


def test_sex_aware_selection_uses_exact_matching_active_piglets():
    result = prepare_litter_loss_preview(
        base_facts(male_count=2, female_count=1), canonical())
    assert result["success"] is True
    assert result["preview"]["selection_basis"] == "canonical_matching_sex"
    assert result["preview"]["pig_ids"] == ["P1", "P2", "P3"]
    assert [row["sex"] for row in result["preview"]["selected_piglets"]] == [
        "Male", "Male", "Female"]


def test_explicit_unknown_sex_uses_deterministic_disclosed_fallback():
    result = prepare_litter_loss_preview(
        base_facts(sex_unknown=True), canonical())
    assert result["success"] is True
    assert result["preview"]["selection_basis"] == \
        "deterministic_unknown_sex_fallback"
    assert result["preview"]["pig_ids"] == ["P1", "P2", "P3"]
    assert [row["pig_id"] for row in result["preview"]["selected_piglets"]] == [
        "P1", "P2", "P3"]


def test_retained_three_and_later_one_have_separate_provider_bound_operations():
    first = prepare_litter_loss_preview(
        base_facts(male_count=2, female_count=1), canonical())["preview"]
    remaining = [
        {"pig_id": "P4", "tag_number": "04", "sex": "Female",
         "status": "Active", "on_farm": True},
        {"pig_id": "P5", "tag_number": "05", "sex": "",
         "status": "Active", "on_farm": True},
    ]
    claims = []
    parsed = {
        "telegram_user_id": "ANTON", "telegram_chat_id": "ANTON",
        "provider_message_id": "4060",
        "semantic": {"intent": "record_litter_piglet_deaths",
            "continuation": True, "litter_piglet_loss": {
                "sow_ref": "Linda", "event_date": None, "count": 1,
                "male_count": 0, "female_count": 1, "sex_unknown": False}},
    }
    with patch(
        "modules.oom_sakkie.herdmaster_litter_loss_runtime."
        "validates_gateway_owner_authority",
        return_value=True,
    ):
        result, status = handle_litter_loss_message(
            parsed,
            SimpleNamespace(capabilities=("mortality_confirmation",)),
            evidence_loader=lambda **_: canonical(remaining),
            history_loader=lambda *_args, **_kwargs: [{
                **first, "status": "completed", "created_at": "now"}],
            retained_context_loader=lambda *_args, **_kwargs: [],
            claim_creator=lambda **kwargs: (
                claims.append(kwargs)
                or {"callback_token": "TOKEN-ONE", "preview_digest": "DIGEST-ONE"}
            ),
        )
    assert status == 200
    second = claims[0]["preview_payload"]
    assert first["count"] == 3 and second["count"] == 1
    assert first["source_event_ids"] == ["4052", "4054"]
    assert second["source_event_ids"] == ["4060"]
    assert first["operation_id"] != second["operation_id"]
    assert second["event_date"] == "2026-08-26"
    assert second["pig_ids"] == ["P4"]
    assert "P4" in result["answer"]


def test_active_first_receipt_reserves_its_piglets_from_later_preview():
    prepared = prepare_litter_loss_preview(
        base_facts(sex_unknown=True), canonical(),
        reserved_pig_ids={"P1", "P2", "P3"})
    assert prepared["status"] == "insufficient_unreserved_active_piglets"
