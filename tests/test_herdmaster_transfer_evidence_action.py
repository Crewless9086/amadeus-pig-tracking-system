from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from modules.pig_weights.herdmaster_live_transfer_contract import compose_live_transfer_contract
from modules.pig_weights.herdmaster_transfer_evidence_action import preview_evidence_action
from tests.test_herdmaster_live_transfer_contract import snapshot


def answers(packet):
    question = packet["consolidated_evidence_request"]["medical_pair_questions"][0]
    return {
        "medical_pair_answers": [{
            "event_ids": question["event_ids"],
            "choice": "Unknown_requires_veterinary_review",
            "factual_basis": "Available records do not establish the physical administration count.",
        }],
        "live_transfer_assessment": {
            "pig_id": "PIG-2026-B156",
            "fit_for_transport": "Unknown",
            "quarantine": "Unknown",
            "infectious_or_notifiable_disease_restriction": "Unknown",
            "veterinary_movement_stop": "Unknown",
            "serious_welfare_or_health_hold": "Unknown",
            "attributable_note": "Current physical assessment is still required.",
        },
    }


def test_one_consolidated_preview_is_signed_zero_write_and_exactly_bound(monkeypatch):
    monkeypatch.setenv("OWNER_SESSION_SECRET", "test-secret")
    packet = compose_live_transfer_contract(snapshot(), as_of=date(2026, 8, 16))
    result, status = preview_evidence_action(
        packet, answers(packet), actor_id="owner-admin:charl",
        now=datetime(2026, 8, 16, 10, tzinfo=timezone.utc),
    )
    assert status == 200
    assert result["writes_performed"] is False
    assert result["confirmation_binding"]["signature"]
    assert result["answers"]["live_transfer_assessment"]["fit_for_transport"] == "Unknown"


def test_duplicate_choice_requires_owner_selected_retained_identity(monkeypatch):
    monkeypatch.setenv("OWNER_SESSION_SECRET", "test-secret")
    packet = compose_live_transfer_contract(snapshot(), as_of=date(2026, 8, 16))
    payload = answers(packet)
    payload["medical_pair_answers"][0]["choice"] = "one_administration_recorded_twice"
    result, status = preview_evidence_action(packet, payload, actor_id="owner-admin:charl")
    assert status == 400
    assert result["status"] == "duplicate_resolution_retained_event_required"


def test_executor_source_is_append_only_and_forbids_commercial_mutation():
    source = Path("modules/pig_weights/herdmaster_transfer_evidence_action.py").read_text(encoding="utf-8").lower()
    assert "insert into public.pig_medical_correction_events" in source
    assert "insert into public.pig_observation_events" in source
    for forbidden in ("update public.pigs", "insert into public.order_lines",
                      "update public.order_lines", "update public.orders",
                      "delete from public.pig_medical_events"):
        assert forbidden not in source
    assert "set transaction isolation level serializable" in source
    assert "pg_advisory_xact_lock" in source
    assert "insert into public.herdmaster_transfer_evidence_receipts" in source
    assert "transfer_evidence_idempotency_conflict" in source
    assert "canonical_readback" in source
