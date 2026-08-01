from modules.oom_sakkie.gateway_authority import issue_gateway_owner_authority
from modules.oom_sakkie.herdmaster_health_loss_preview import (
    _owner_text_digest,
    prepare_health_loss_owner_preview,
)


NOW = "2026-08-01T08:30:00+02:00"


def envelope(text):
    return {
        "gateway_authority": issue_gateway_owner_authority("42", "42"),
        "provider_message_id": "telegram-update-700-message-9",
        "provider_timestamp": NOW,
        "provider_timezone": "Africa/Johannesburg",
        "text": text,
    }


def pig(name="Maya", pig_id="PIG-2026-MAYA", tag="Maya"):
    return {
        "pig_id": pig_id, "name": name, "tag_number": tag,
        "lifecycle_status": "Active", "on_farm": True,
        "availability": "Breeding", "pen": "Farrowing 1",
    }


def evidence(*animals, matings=(), litters=()):
    return {
        "evidence_generation": "HERD-GEN-77",
        "as_of_timestamp": "2026-08-01T08:31:00+02:00",
        "animals": list(animals), "matings": list(matings),
        "litters": list(litters),
    }


def test_maya_compound_report_renders_one_complete_human_preview_without_writes():
    maya = pig()
    result = prepare_health_loss_owner_preview(envelope(
        "Maya died yesterday after complications while farrowing. All 10 "
        "piglets were stillborn. We believe she had a uterine infection."
    ), evidence(maya, matings=[{
        "mating_id": "MAT-MAYA-1", "sow_pig_id": maya["pig_id"],
        "date": "2026-04-09", "is_open": True,
    }]))
    assert result["status"] == "consolidated_preview_ready"
    text = result["owner_text"]
    assert "Maya (PIG-2026-MAYA; tag Maya)" in text
    assert "total born: 10" in text
    assert "born alive: 0" in text
    assert "stillborn: 10" in text
    assert "uterine infection - owner suspected only" in text
    assert "Veterinary evidence:\n- None reported" in text
    assert "Proposed affected records (nothing written)" in text
    assert result["question_count"] == 1
    assert result["confirmation_ready"] is False
    assert result["writes_farm_data"] is False
    assert result["sends_telegram"] is False


def test_complete_injured_report_has_exact_confirmation_binding():
    injured = pig("Teena", "PIG-2026-TEEN", "Teena")
    result = prepare_health_loss_owner_preview(
        envelope("Teena is injured and bleeding."), evidence(injured)
    )
    assert result["success"] is True
    assert result["question_count"] == 1  # current welfare state is genuinely required first
    binding = result["confirmation_binding"]
    assert binding["operation_id"] == result["evaluator"]["operation_id"]
    assert binding["preview_sha256"] == result["evaluator"]["preview_sha256"]
    assert binding["evidence_generation"] == "HERD-GEN-77"
    assert binding["provider_message_id"] == "telegram-update-700-message-9"


def test_ambiguous_identity_asks_exactly_one_private_owner_question():
    result = prepare_health_loss_owner_preview(
        envelope("Maya looks sick."),
        evidence(pig("Maya", "PIG-1", "M-1"), pig("Maya", "PIG-2", "M-2")),
    )
    assert result["status"] == "identity_required"
    assert result["message_type"] == "single_clarification"
    assert result["question_count"] == 1
    assert result["owner_text"].count("?") == 1
    assert "looks sick" not in result["owner_text"]
    assert result["writes_farm_data"] is False


def test_forged_missing_or_non_private_authority_is_contained():
    canonical = evidence(pig())
    forged = {**envelope("Maya looks sick."), "gateway_authority": object()}
    assert prepare_health_loss_owner_preview(forged, canonical)["status"] == (
        "authenticated_private_owner_authority_required"
    )
    non_private = {**envelope("Maya looks sick."), "gateway_authority":
                   issue_gateway_owner_authority("42", "99")}
    assert prepare_health_loss_owner_preview(non_private, canonical)["status"] == (
        "authenticated_private_owner_authority_required"
    )


def test_existing_canonical_litter_conflict_is_one_clarification_not_duplicate_preview():
    maya = pig()
    result = prepare_health_loss_owner_preview(
        envelope("Maya was farrowing yesterday. All 2 piglets were stillborn."),
        evidence(maya, matings=[{
            "mating_id": "MAT-1", "sow_pig_id": maya["pig_id"],
            "date": "2026-04-09", "is_open": True,
        }], litters=[{
            "litter_id": "LIT-EXISTING", "sow_pig_id": maya["pig_id"],
            "farrowing_date": "2026-07-31",
        }]),
    )
    assert result["status"] == "chronology_conflict"
    assert result["question_count"] == 1
    assert result["evaluator"]["canonical_effects"] == []


def test_same_authenticated_message_and_evidence_replays_same_preview_identity():
    animal = pig("Tag 51", "PIG-2026-0051", "51")
    packet = evidence(animal)
    first = prepare_health_loss_owner_preview(envelope("Tag 51 is sick and not eating."), packet)
    second = prepare_health_loss_owner_preview(envelope("Tag 51 is sick and not eating."), packet)
    assert first["confirmation_binding"] == second["confirmation_binding"]
    assert first["owner_text"] == second["owner_text"]
    assert first["writes_farm_data"] is second["writes_farm_data"] is False
    digest = first["confirmation_binding"]["owner_text_sha256"]
    assert digest == _owner_text_digest(first["owner_text"])
    assert digest != _owner_text_digest(first["owner_text"] + " changed")


def test_enriched_sick_report_does_not_repeat_supplied_welfare_facts():
    animal = pig("Tag 51", "PIG-2026-0051", "51")
    result = prepare_health_loss_owner_preview(envelope(
        "Tag 51 is sick and not eating. She can stand, is breathing normally, "
        "and is drinking water."
    ), evidence(animal))
    assert result["question_count"] == 0
    assert result["confirmation_ready"] is True
    assert "not eating: True" in result["owner_text"]
    assert "Agent inference: None" in result["owner_text"]
    assert "medical observation" in result["owner_text"]


def test_ordinary_found_dead_preview_keeps_death_date_unknown():
    animal = pig("Tag 22", "PIG-2026-0022", "22")
    result = prepare_health_loss_owner_preview(
        envelope("I found tag 22 dead this morning."), evidence(animal)
    )
    assert result["question_count"] == 1
    assert "last seen alive" in result["owner_text"]
    assert "leave death effective date unknown [Unknown / no change]" in result["owner_text"]
    assert "found dead observation date: 2026-08-01" in result["owner_text"]
    assert "Agent inference: None" in result["owner_text"]


def test_supplied_found_chronology_and_disposal_are_not_asked_again():
    animal = pig("Maya", "PIG-2026-MAYA", "Maya")
    result = prepare_health_loss_owner_preview(envelope(
        "Maya was last seen alive yesterday evening, was found dead this "
        "morning, and was removed from the pen and buried."
    ), evidence(animal))
    assert result["question_count"] == 0
    assert "record reported removal or disposal context [proposed]" in result["owner_text"]
    assert "One clarification:" not in result["owner_text"]
