"""Governed exact-preview recording for natural HERDMASTER observations.

Only the existing append-only factual pig-observation rail is writable here.
Lifecycle, medical treatment, mating, litter, movement and availability effects
remain blocked until their canonical services are explicitly coordinated.
"""

from __future__ import annotations

import hashlib
import json
import os
from typing import Any, Mapping


def confirm_health_loss_preview(lifecycle: Mapping[str, Any], confirmation_text: str,
                                *, actor_id: str, evidence_loader, connect_factory=None):
    preview = lifecycle.get("preview") if isinstance(lifecycle.get("preview"), Mapping) else {}
    binding = preview.get("confirmation_binding") if isinstance(preview.get("confirmation_binding"), Mapping) else {}
    operation_id = str(binding.get("operation_id") or "")
    expected = "CONFIRM " + operation_id
    if not operation_id or str(confirmation_text or "").strip() != expected:
        return _result(False, "exact_preview_confirmation_required"), 409
    if binding.get("confirmation_ready") is not True or preview.get("confirmation_ready") is not True:
        return _result(False, "preview_not_confirmation_ready"), 409
    current = evidence_loader()
    if str(current.get("evidence_generation") or "") != str(binding.get("evidence_generation") or ""):
        return _result(False, "canonical_evidence_changed_repreview_required"), 409
    evaluator = preview.get("evaluator") if isinstance(preview.get("evaluator"), Mapping) else {}
    supported = [row for row in evaluator.get("canonical_effects") or [] if row.get("supported")]
    if not supported or any(row.get("area") != "medical_observation" for row in supported):
        return _result(False, "canonical_effect_coordinator_unavailable",
                       blocked_areas=sorted({str(row.get("area")) for row in supported
                                             if row.get("area") != "medical_observation"})), 409
    identity = evaluator.get("identity") if isinstance(evaluator.get("identity"), Mapping) else {}
    pig_id = str(identity.get("pig_id") or "")
    facts = dict(supported[0].get("facts") or {})
    canonical = {"operation_id": operation_id, "pig_id": pig_id,
        "provider_message_id": str(binding.get("provider_message_id") or ""),
        "preview_sha256": str(binding.get("preview_sha256") or ""),
        "evidence_generation": str(binding.get("evidence_generation") or ""),
        "facts": facts, "actor_id": str(actor_id or "")}
    digest = hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    event_id = "OBS-HL-" + hashlib.sha256(operation_id.encode()).hexdigest()[:24].upper()
    note = _factual_note(facts)
    severity = "urgent" if str((evaluator.get("immediate_welfare_priority") or {}).get("level") or "") in {"emergency", "urgent_follow_up"} else "attention"
    try:
        connection_cm = connect_factory() if connect_factory else _connect()
        with connection_cm as connection:
            with connection.cursor() as cursor:
                cursor.execute("select pg_advisory_xact_lock(hashtextextended(%s,0))",
                               ("herdmaster-health-loss:" + operation_id,))
                cursor.execute("""select observation_event_id,source_reference
                    from public.pig_observation_events where idempotency_key=%s""", (operation_id,))
                existing = cursor.fetchone()
                if existing:
                    if str(existing[1]) != digest:
                        return _result(False, "health_loss_idempotency_conflict"), 409
                    return _result(True, "health_loss_replayed_withheld",
                                   observation_event_id=str(existing[0]), rows_created=0), 200
                cursor.execute("""select 1 from public.pigs
                    where pig_id=%s and status='Active' and on_farm is true for share""", (pig_id,))
                if not cursor.fetchone():
                    return _result(False, "current_active_on_farm_pig_required"), 409
                cursor.execute("""insert into public.pig_observation_events(
                    observation_event_id,pig_id,observed_at,observer_reference,
                    observation_category,severity,factual_note,measurements_json,
                    source_system,source_reference,idempotency_key)
                    values(%s,%s,%s::timestamptz,%s,'welfare',%s,%s,%s::jsonb,
                           'owner',%s,%s) returning observation_event_id""", (
                    event_id, pig_id, str(lifecycle.get("provider_timestamp") or ""),
                    str(actor_id), severity, note, json.dumps({
                        "contract_version": "herdmaster_health_loss_recording_v1",
                        "observed": facts.get("observed") or [],
                        "owner_suspected_not_diagnosed": facts.get("owner_suspected") or [],
                        "owner_reported_veterinary_evidence": facts.get("veterinary_evidence") or [],
                        "diagnosis_inferred": False,
                        "provider_message_id": canonical["provider_message_id"],
                        "preview_sha256": canonical["preview_sha256"],
                    }, sort_keys=True), digest, operation_id))
                cursor.fetchone()
    except Exception:
        return _result(False, "health_loss_recording_store_unavailable"), 503
    return _result(True, "health_loss_observation_recorded",
                   observation_event_id=event_id, rows_created=1,
                   recommendation_refresh_required=True), 201


def _factual_note(facts):
    observed = facts.get("observed") if isinstance(facts.get("observed"), list) else []
    return "Owner-reported welfare observations: " + "; ".join(
        f"{row.get('fact')}: {row.get('value')}" for row in observed if isinstance(row, Mapping)
    )


def _connect():
    import psycopg
    return psycopg.connect(os.environ["DATABASE_URL"], connect_timeout=10)


def _result(success, status, **extra):
    return {"success": success, "status": status, "writes_farm_data": bool(success and extra.get("rows_created")),
            "diagnosis_inferred": False, "treatment_recorded": False, **extra}
