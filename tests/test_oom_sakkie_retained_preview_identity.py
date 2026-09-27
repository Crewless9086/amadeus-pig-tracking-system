"""Real evaluator previews across changing read clocks and retained identities."""
from copy import deepcopy

import pytest

from modules.oom_sakkie.gateway_authority import issue_gateway_owner_authority
from modules.oom_sakkie.herdmaster_health_loss_preview import prepare_health_loss_owner_preview
from modules.oom_sakkie.herdmaster_retained_recovery_runtime import _unchanged_retained_preview
from modules.pig_weights import herdmaster_natural_health_loss_intake as intake


def legacy_clock_digest(original, timestamp):
    """Reproduce the pre-fix canonical packet hashing, not a fabricated preview."""
    def digest(value):
        if isinstance(value, dict) and "animals" in value and "as_of_timestamp" not in value:
            value = {**value, "as_of_timestamp": timestamp}
        return original(value)
    return digest


@pytest.fixture
def previews(monkeypatch):
    evidence = {"evidence_generation": "FARM-1", "as_of_timestamp": "2026-09-23T04:45:00+00:00",
        "animal_evidence_generations": {"P27": "ANIMAL-27"},
        "animals": [{"pig_id": "P27", "tag_number": "27", "name": "Synthetic",
            "lifecycle_status": "Active", "on_farm": True, "availability": "Herd", "pen": "PEN-A"}],
        "matings": [], "litters": []}
    envelope = {"gateway_authority": issue_gateway_owner_authority("42", "42"),
        "provider_message_id": "101", "provider_timestamp": "2026-08-20T08:00:00+00:00",
        "output_language": "af", "text": "Vark nr 27 is dood op 19 Aug 2026. Hy is verwyder en begrawe."}
    with monkeypatch.context() as old:
        old.setattr(intake, "_digest", legacy_clock_digest(intake._digest, evidence["as_of_timestamp"]))
        prior = prepare_health_loss_owner_preview(envelope, evidence)
    current = prepare_health_loss_owner_preview(envelope,
        {**evidence, "as_of_timestamp": "2026-09-23T04:50:00+00:00"})
    assert prior["confirmation_ready"] and current["confirmation_ready"]
    assert current["confirmation_binding"]["evidence_scope"] == "animal"
    assert current["confirmation_binding"]["evidence_generation"] == "ANIMAL-27"
    assert prior["confirmation_binding"]["operation_id"] != current["confirmation_binding"]["operation_id"]
    source = {"status": "preview_ready", "event_phase": "retained_preview_generated:original",
        "operation_id": prior["confirmation_binding"]["operation_id"], "preview": prior,
        "retained_repreview": {"contract_version": "retained_health_preview_v1",
            "claim_evidence_generation": "FARM-1"}}
    return source, current


def test_exact_legacy_preview_identity_survives_new_clock_without_mutation(previews):
    source, current = previews
    before = deepcopy((source, current))
    selected = _unchanged_retained_preview(source, current, evidence_generation="FARM-1")
    assert selected == source["preview"]
    assert (source, current) == before


@pytest.mark.parametrize("change", ["generation", "phase", "status", "missing_preview", "owner",
    "date", "effect", "scope", "owner_text", "readiness", "hash", "inner_operation", "extra"])
def test_legacy_identity_cannot_hide_material_or_provenance_change(previews, change):
    source, current = deepcopy(previews)
    generation = "FARM-1"
    if change == "generation": generation = "FARM-2"
    elif change == "phase": source["event_phase"] = "generated_elsewhere"
    elif change == "status": source["status"] = "waiting_for_input"
    elif change == "missing_preview": source["preview"] = {}
    elif change == "owner": current["confirmation_binding"]["authenticated_principal_id"] = "other"
    elif change == "date": current["evaluator"]["preview"]["event_date"] = "2026-08-18"
    elif change == "effect": current["evaluator"]["canonical_effects"][0]["facts"]["date"] = "2026-08-18"
    elif change == "scope": current["confirmation_binding"]["evidence_scope"] = "other"
    elif change == "owner_text": current["owner_text"] += "changed"
    elif change == "readiness": current["confirmation_ready"] = False
    elif change == "hash": source["preview"]["evaluator"]["preview_sha256"] = "tampered"
    elif change == "inner_operation": source["preview"]["evaluator"]["preview"]["operation_id"] = "other"
    elif change == "extra": current["new_authority_field"] = True
    selected = _unchanged_retained_preview(source, current, evidence_generation=generation)
    assert selected is current
