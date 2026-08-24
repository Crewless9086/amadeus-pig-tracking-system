"""Selective BCS capture through the existing canonical observation writer."""
from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo

from modules.pig_weights.herdmaster_breeding_observation_service import (
    list_observations, observation_by_idempotency, record_observation,
)


def record_body_condition_batch(payload, *, actor_id, database_url=None,
                                connect_factory=None, now=None):
    payload = payload if isinstance(payload, dict) else {}
    rows = payload.get("rows") if isinstance(payload.get("rows"), list) else []
    batch_key = str(payload.get("draft_id") or "").strip()
    observed_date = str(payload.get("observed_date") or "").strip()
    now = now or datetime.now(timezone.utc)
    if not batch_key or not observed_date:
        return {"success": False, "status": "batch_identity_and_date_required"}, 400
    try:
        selected_date = date.fromisoformat(observed_date)
    except ValueError:
        return {"success": False, "status": "invalid_observed_date"}, 400
    local_now = now.astimezone(ZoneInfo("Africa/Johannesburg"))
    observed_at = (local_now if selected_date == local_now.date() else
        datetime.combine(selected_date, time(hour=12), tzinfo=ZoneInfo("Africa/Johannesburg")))
    selected, seen = [], set()
    for raw in rows:
        row = raw if isinstance(raw, dict) else {}
        score = row.get("body_condition_score")
        if score in (None, ""):
            continue
        pig_id = str(row.get("pig_id") or "").strip()
        if not pig_id or pig_id in seen:
            return {"success": False, "status": "unique_pig_identity_required"}, 400
        seen.add(pig_id)
        try:
            score = float(score)
        except (TypeError, ValueError):
            score = 0
        if not 1 <= score <= 5:
            return {"success": False, "status": "invalid_body_condition_score"}, 400
        selected.append((pig_id, score))
    events = []
    for pig_id, score in sorted(selected):
        idem = f"bulk-bcs:{batch_key}:{pig_id}"
        committed, committed_status = observation_by_idempotency(
            idem, database_url=database_url, connect_factory=connect_factory)
        if committed_status not in (200, 404):
            return {"success": False, "status": "body_condition_batch_partial",
                "events": events, "failed_pig_id": pig_id,
                "failed_status": "observation_store_unavailable",
                "draft_must_be_retained": True}, committed_status
        if committed is not None and committed.get("pig_id") != pig_id:
            return {"success": False, "status": "body_condition_batch_partial",
                "events": events, "failed_pig_id": pig_id,
                "failed_status": "observation_idempotency_conflict",
                "draft_must_be_retained": True}, 409
        if committed is None:
            history, status = list_observations(pig_id, database_url=database_url,
                                                connect_factory=connect_factory, now=now)
            if status != 200:
                return {"success": False, "status": "body_condition_batch_partial",
                    "events": events, "failed_pig_id": pig_id,
                    "failed_status": history.get("status"),
                    "draft_must_be_retained": True}, status
            prior = next((item for item in history.get("history", [])
                          if not item.get("superseded") and
                          "body_condition_score" in item.get("measurements", {})), None)
            predecessor = prior.get("observation_event_id") if prior else None
        else:
            predecessor = committed.get("supersedes_observation_event_id")
        result, status = record_observation({
            "pig_id": pig_id, "observed_at": observed_at.isoformat(),
            "body_condition_score": score,
            "factual_note": f"Body condition score {score:g}.",
            "idempotency_key": idem,
            "supersedes_observation_event_id": predecessor,
        }, actor_id=actor_id, database_url=database_url,
           connect_factory=connect_factory, now=now)
        if status not in (200, 201):
            return {"success": False, "status": "body_condition_batch_partial",
                "events": events, "failed_pig_id": pig_id,
                "failed_status": result.get("status"),
                "draft_must_be_retained": True}, status
        events.append({"pig_id": pig_id, "status": result["status"],
                       "observation_event_id": result.get("observation_event_id"),
                       "supersedes_observation_event_id": predecessor})
    recorded = sum(row["status"] == "observation_recorded" for row in events)
    return {"success": True,
            "status": "body_condition_batch_recorded" if events else "no_body_condition_selected",
            "recorded_count": recorded, "replayed_count": len(events) - recorded,
            "events": events, "heat_fields_recorded": False}, 201 if recorded else 200
