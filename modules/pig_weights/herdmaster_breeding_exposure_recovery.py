"""Governed grouped breeding exposure and recovery decisions.

This module reuses pig_observation_events for factual/hold evidence and writes
only actual exposure facts to the dedicated append-only exposure rail. It
never creates a mating, service date, pregnancy, movement, or litter.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import date, datetime, timedelta, timezone

CONTRACT_VERSION = "herdmaster_breeding_exposure_recovery_v1"
OBSERVATION_VERSION = "herdmaster_breeding_observation_v1"
ALLOWED_ACTIONS = {"exposure", "exposure_removal", "recovery_hold", "recovery_clearance", "near_farrowing"}


def planned_exposure_removal_on(started_on, days=17):
    """Return the inclusive final exposure day shared by every channel."""
    started = date.fromisoformat(str(started_on or ""))
    duration = int(days)
    if not 1 <= duration <= 60:
        raise ValueError("exact exposure duration")
    return (started + timedelta(days=duration - 1)).isoformat()


def _date(value):
    try:
        return date.fromisoformat(str(value or ""))
    except ValueError:
        return None


def _instant(value):
    try:
        parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc) if parsed.tzinfo else None
    except ValueError:
        return None


def _stable(prefix, *parts):
    material = json.dumps(parts, sort_keys=True, separators=(",", ":"), default=str)
    return prefix + hashlib.sha256(material.encode()).hexdigest().upper()[:32]


def build_grouped_preview(payload, *, evidence_generation):
    payload = payload if isinstance(payload, dict) else {}
    rows = payload.get("rows") if isinstance(payload.get("rows"), list) else []
    errors, cleaned, seen = [], [], set()
    for index, raw in enumerate(rows):
        row = raw if isinstance(raw, dict) else {}
        pig_id = str(row.get("pig_id") or "").strip()
        action = str(row.get("action") or "").strip().lower()
        if not pig_id or pig_id in seen:
            errors.append(f"row_{index + 1}_unique_pig_required")
        seen.add(pig_id)
        if action not in ALLOWED_ACTIONS:
            errors.append(f"row_{index + 1}_supported_action_required")
        item = {"pig_id": pig_id, "label": str(row.get("label") or pig_id).strip(), "action": action}
        if action == "exposure":
            start = _date(row.get("exposure_started_on"))
            end = _date(row.get("planned_removal_on"))
            boar = str(row.get("boar_pig_id") or "").strip()
            if not start or not end or end < start or not boar:
                errors.append(f"row_{index + 1}_exact_exposure_required")
            item.update(boar_pig_id=boar, exposure_started_on=str(start) if start else None,
                        planned_removal_on=str(end) if end else None)
        elif action == "exposure_removal":
            removed = _date(row.get("actual_removed_on"))
            boar = str(row.get("boar_pig_id") or "").strip()
            identity = str(row.get("exposure_identity") or "").strip()
            if not removed or not boar or not identity:
                errors.append(f"row_{index + 1}_exact_exposure_removal_required")
            item.update(boar_pig_id=boar, exposure_identity=identity,
                        actual_removed_on=str(removed) if removed else None)
        elif action in {"recovery_hold", "recovery_clearance"}:
            try:
                score = float(row.get("body_condition_score"))
            except (TypeError, ValueError):
                score = None
            observed = _instant(row.get("observed_at"))
            if score is None or not 1 <= score <= 5 or observed is None:
                errors.append(f"row_{index + 1}_fresh_body_condition_required")
            if action == "recovery_hold" and score is not None and score > 2:
                errors.append(f"row_{index + 1}_hold_requires_bcs_2_or_lower")
            if action == "recovery_clearance" and score is not None and score < 3:
                errors.append(f"row_{index + 1}_clearance_requires_bcs_3_or_higher")
            item.update(body_condition_score=score, observed_at=observed.isoformat() if observed else None,
                        factual_note=str(row.get("factual_note") or "").strip())
            if not item["factual_note"]:
                errors.append(f"row_{index + 1}_factual_note_required")
        elif action == "near_farrowing":
            observed = _instant(row.get("observed_at"))
            if observed is None:
                errors.append(f"row_{index + 1}_observation_time_required")
            item.update(observed_at=observed.isoformat() if observed else None,
                        factual_note=str(row.get("factual_note") or "").strip(),
                        father_pig_id=None, historical_mating_date=None)
            if not item["factual_note"]:
                errors.append(f"row_{index + 1}_factual_note_required")
        cleaned.append(item)
    if not rows:
        errors.append("complete_group_required")
    canonical = {"contract_version": CONTRACT_VERSION, "evidence_generation": str(evidence_generation),
                 "rows": cleaned, "row_count": len(cleaned)}
    digest = hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return {"success": not errors, "status": "grouped_preview_ready" if not errors else "grouped_preview_invalid",
            "errors": errors, "preview": canonical, "preview_sha256": digest,
            "operation_id": _stable("HERD-BREED-GROUP-", digest), "creates_mating": False,
            "asserts_service_date": False, "asserts_conception": False, "asserts_pregnancy": False,
            "creates_movement": False, "writes_performed": False}


def execute_grouped_preview(preview_result, *, confirmed_preview_sha256, actor_id, connect_factory):
    if not isinstance(preview_result, dict) or preview_result.get("success") is not True:
        return {"success": False, "status": "valid_preview_required", "rows_changed": 0}, 400
    if str(confirmed_preview_sha256) != preview_result["preview_sha256"] or not str(actor_id).strip():
        return {"success": False, "status": "exact_owner_confirmation_required", "rows_changed": 0}, 409
    preview = preview_result["preview"]
    operation_id = preview_result["operation_id"]
    inserted = []
    with connect_factory() as db:
        with db.cursor() as cur:
            cur.execute("select pg_advisory_xact_lock(hashtextextended(%s,0))", (operation_id,))
            for pig_id in sorted(row["pig_id"] for row in preview["rows"]):
                cur.execute("select pg_advisory_xact_lock(hashtextextended(%s,0))", ("herd-breeding-pig:" + pig_id,))
            prior_count = 0
            for row in preview["rows"]:
                key = operation_id + ":" + row["pig_id"]
                table = "public.pig_breeding_exposure_events" if row["action"] in {"exposure", "exposure_removal"} else "public.pig_observation_events"
                cur.execute(f"select 1 from {table} where idempotency_key=%s", (key,))
                prior_count += int(cur.fetchone() is not None)
            if prior_count == len(preview["rows"]):
                return {"success": True, "status": "grouped_operation_replayed_noop", "operation_id": operation_id,
                        "rows_changed": 0}, 200
            if prior_count:
                raise ValueError("partial_group_replay_conflict")
            for row in preview["rows"]:
                cur.execute("select 1 from public.pigs where pig_id=%s for share", (row["pig_id"],))
                cur.execute("select sex,status,on_farm from public.current_canonical_pig_state where pig_id=%s", (row["pig_id"],))
                current = cur.fetchone()
                if not current or str(current[0]).lower() != "female" or str(current[1]).lower() != "active" or current[2] is not True:
                    raise ValueError("current_sow_identity_changed")
                action = row["action"]
                key = operation_id + ":" + row["pig_id"]
                if action in {"exposure", "exposure_removal"}:
                    cur.execute("select 1 from public.pigs where pig_id=%s for share", (row["boar_pig_id"],))
                    cur.execute("select sex,status,on_farm from public.current_canonical_pig_state where pig_id=%s", (row["boar_pig_id"],))
                    boar = cur.fetchone()
                    if not boar or str(boar[0]).lower() != "male" or str(boar[1]).lower() != "active" or boar[2] is not True:
                        raise ValueError("current_boar_identity_changed")
                    identity = (row.get("exposure_identity") or
                                _stable("HERD-EXPOSURE-ID-", row["pig_id"], row["boar_pig_id"], row.get("exposure_started_on")))
                    if action == "exposure":
                        cur.execute("""select 1
                            from public.pig_breeding_exposure_events started
                            where started.sow_pig_id=%s and started.event_kind='started'
                              and not exists (
                                select 1 from public.pig_breeding_exposure_events removed
                                where removed.exposure_identity=started.exposure_identity
                                  and removed.event_kind='removed')
                            limit 1 for share""", (row["pig_id"],))
                        if cur.fetchone() is not None:
                            raise ValueError("active_exposure_already_exists")
                    else:
                        cur.execute("""select occurred_on
                            from public.pig_breeding_exposure_events
                            where exposure_identity=%s and event_kind='started'
                              and sow_pig_id=%s and boar_pig_id=%s
                            for share""", (identity, row["pig_id"], row["boar_pig_id"]))
                        started = cur.fetchone()
                        if not started or _date(row.get("actual_removed_on")) < _date(started[0]):
                            raise ValueError("matching_exposure_start_required")
                    event_id = _stable("HERD-EXPOSURE-", key)
                    event_kind = "started" if action == "exposure" else "removed"
                    occurred = row.get("exposure_started_on") if action == "exposure" else row.get("actual_removed_on")
                    cur.execute("""insert into public.pig_breeding_exposure_events(
                        exposure_event_id,exposure_identity,event_kind,sow_pig_id,boar_pig_id,occurred_on,
                        planned_removal_on,observer_reference,source_reference,idempotency_key)
                        values(%s,%s,%s,%s,%s,%s::date,%s::date,%s,%s,%s)
                        on conflict(idempotency_key) do nothing""",
                        (event_id,identity,event_kind,row["pig_id"],row["boar_pig_id"],occurred,
                         row.get("planned_removal_on"),actor_id,preview_result["preview_sha256"],key))
                else:
                    event_id = _stable("HERD-OBS-", key)
                    measurements = {"contract_version": OBSERVATION_VERSION,
                        "recovery_hold_action": "active" if action == "recovery_hold" else "cleared" if action == "recovery_clearance" else "not_recorded",
                        "near_farrowing": "observed" if action == "near_farrowing" else "not_recorded"}
                    if action in {"recovery_hold", "recovery_clearance"}:
                        measurements["body_condition_score"] = row["body_condition_score"]
                    cur.execute("""insert into public.pig_observation_events(
                        observation_event_id,pig_id,observed_at,observer_reference,observation_category,severity,
                        factual_note,measurements_json,source_system,source_reference,idempotency_key)
                        values(%s,%s,%s::timestamptz,%s,'body_condition','attention',%s,%s::jsonb,'owner',%s,%s)
                        on conflict(idempotency_key) do nothing""",
                        (event_id,row["pig_id"],row["observed_at"],actor_id,row["factual_note"],json.dumps(measurements,sort_keys=True),preview_result["preview_sha256"],key))
                if cur.rowcount != 1:
                    raise ValueError("group_row_already_exists_or_conflicts")
                inserted.append({"pig_id": row["pig_id"], "action": action, "event_id": event_id})
    return {"success": True, "status": "grouped_operation_completed", "operation_id": operation_id,
            "rows_changed": len(inserted), "rows": inserted, "creates_mating": False,
            "asserts_service_date": False, "creates_movement": False}, 201
