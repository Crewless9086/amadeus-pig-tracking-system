"""Truthful owner projection over ROOTLINE's existing canonical rails."""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from zoneinfo import ZoneInfo

from modules.telemetry.rootline_irrigation_history import read_canonical_irrigation_history
from modules.telemetry.rootline_water_balance import read_latest_zone_water_balances
from modules.telemetry.rootline_water_energy_plan import _read_latest_tank_observation

ZONE_NAMES = {"B12345": "B Camp", "C12345": "C Camp"}


def get_rootline_owner_status(operating_date=None, database_url=None, now=None):
    now = now or datetime.now(timezone.utc)
    database_url = str(database_url or os.getenv("DATABASE_URL") or "").strip()
    if not database_url:
        return _failure("database_not_configured"), 503
    try:
        evidence = _canonical_evidence(database_url, operating_date, now)
        evidence["water_balance"] = read_latest_zone_water_balances(database_url, now=now)
        specialist = _specialist_projection(evidence, operating_date, now)
        history = read_canonical_irrigation_history(database_url, now=now)
        runtime, latest_outcome, notification = _runtime_and_notification(database_url)
    except Exception as exc:
        return _failure("canonical_status_read_failed", exc), 503
    recommendations = {item.get("subject"): item for item in
                       specialist.get("recommendations", []) if isinstance(item, dict)}
    zones = []
    for zone_id in ("B12345", "C12345"):
        recommendation = recommendations.get(zone_id, {})
        zone_history = (history.get("zones") or {}).get(zone_id, {})
        balance = ((evidence.get("water_balance") or {}).get("zones") or {}).get(zone_id, {})
        active = runtime if runtime.get("zone_id") == zone_id else {}
        decision = _decision(recommendation.get("status"))
        blocker = _blocker(recommendation)
        zones.append({
            "zone_id": zone_id,
            "zone_name": ZONE_NAMES[zone_id],
            "decision": decision,
            "operational_state": _operational_state(decision, blocker, active),
            "reason": _zone_reason(recommendation, balance),
            "planned_minutes": recommendation.get("planned_duration_minutes"),
            "feasible_window": recommendation.get("preferred_window"),
            "effective_rainfall_mm": balance.get("effective_rainfall_mm"),
            "remaining_supported_water_need_mm": balance.get("remaining_water_need_mm"),
            "water_balance_complete_through": balance.get("complete_through"),
            "water_balance_freshness": "fresh" if balance.get("ledger_current") is True else "stale",
            "eligibility_blocker": blocker,
            "execution_state": active.get("state") or "not_active",
            "provider_output_state": active.get("provider_output_state") or "Unavailable",
            "shutdown_verified": active.get("shutdown_verified"),
            "verified_completed_days": zone_history.get("verified_completed_days", []),
            "history_complete_through": zone_history.get("complete_through"),
        })
    current = _current(runtime)
    plan = [{"plan_id": specialist.get("result_id"), "zone_id": zone["zone_id"],
             "zone_name": zone["zone_name"], "status": zone["decision"],
             "planned_minutes": zone["planned_minutes"], "reason": zone["reason"]}
            for zone in zones]
    return {
        "success": True,
        "status": "ok",
        "mode": "read_only",
        "contract_version": "rootline_owner_status.v1",
        "source": {"source": "supabase", "projection": "canonical_rootline",
                   "legacy_google_sheets_used": False, "writes_to_supabase": False},
        "plan_identity": specialist.get("result_id"),
        "plan_generation": specialist.get("generation"),
        "operating_date": specialist.get("operating_date"),
        "evidence_cutoff": specialist.get("evidence_cutoff"),
        "current": current,
        "today": {"date": specialist.get("operating_date"), "daily_plan_id": specialist.get("result_id"),
                  "total_plan_rows": len(plan), "plan": plan,
                  "next_zone_id": _next_zone(zones), "completed_minutes": _completed_minutes(runtime)},
        "zones": zones,
        "observed_weather": specialist.get("current_local_weather", {}),
        "forecast": specialist.get("forecast", {}),
        "water_evidence": specialist.get("water_observations", {}),
        "scheduler": {"owner": "Oom Sakkie ROOTLINE scheduler",
                      "next_reassessment": specialist.get("next_reassessment", {})},
        "notification": notification,
        "execution": runtime,
        "latest_execution_outcome": latest_outcome,
        "fertilizer": {"classification": "irrigation_auxiliary_only",
            "mixing_enabled": str(os.getenv("ROOTLINE_FERTILIZER_MIXING_ENABLED") or "").lower() == "true",
            "injection_enabled": str(os.getenv("ROOTLINE_FERTILIZER_INJECTION_ENABLED") or "").lower() == "true",
            "mixer_native_auto_off_seconds": 300,
            "injection_native_auto_off_seconds": 120,
            "mixing_commissioned": False, "injection_commissioned": False,
            "reason": "Physical commissioning evidence is not present on the canonical auxiliary rail."},
        "operator_summary": {"headline": specialist.get("overall_status") or "Needs Data",
                             "notes": [specialist.get("owner_brief", {}).get("why", ["Canonical status available."])[0]]},
        "safety": {"read_only": True, "can_control": False,
                   "hardware_commands_enabled": False},
    }, 200


def _canonical_evidence(database_url, operating_date, now):
    import psycopg
    selected = str(operating_date or now.astimezone(ZoneInfo("Africa/Johannesburg")).date().isoformat())[:10]
    result = {"operating_date": selected, "water_balance": {}}
    tank = _read_latest_tank_observation(database_url)
    result["water"] = ({"status": "available", "storage_state": tank.get("storage_state"),
        "reservoir_state": tank.get("reservoir_state"), "observed_at": tank.get("observed_at"),
        "storage_observed_at": tank.get("storage_observed_at"),
        "reservoir_observed_at": tank.get("reservoir_observed_at"),
        "storage_fraction": tank.get("storage_fraction"),
        "reservoir_fraction": tank.get("reservoir_fraction")}
        if tank else {"status": "Unavailable"})
    with psycopg.connect(database_url, connect_timeout=10) as connection:
        connection.read_only = True
        with connection.cursor() as cursor:
            cursor.execute("""select reading_at,rain_rate_mm_h,rain_today_mm,
                                      temperature_c,wind_speed_kmh,updated_at
                from public.weather_latest_state order by reading_at desc limit 1""")
            row = cursor.fetchone()
            age_minutes = ((now.astimezone(timezone.utc) - row[0].astimezone(timezone.utc)).total_seconds() / 60
                           if row else None)
            result["weather"] = ({"status": "fresh" if 0 <= age_minutes <= 15 else "stale",
                "age_minutes": round(age_minutes, 1), "observed_at": row[0].isoformat(),
                "rain_rate_mm_h": float(row[1]) if row[1] is not None else None,
                "rain_today_mm": float(row[2]) if row[2] is not None else None,
                "temperature_c": float(row[3]) if row[3] is not None else None,
                "wind_speed_kmh": float(row[4]) if row[4] is not None else None,
                "retrieved_at": row[5].isoformat()} if row else {"status": "Unavailable"})
            cursor.execute("""select review_json->'rootline_reassessment',created_at
                from public.sam_live_stock_conversation_review_events
                where event_source='oom_sakkie_rootline_reassessment'
                  and review_json->'rootline_reassessment'->>'operating_date'=%s
                order by created_at desc limit 1""", (selected,))
            row = cursor.fetchone()
            result["reassessment"] = ({**row[0], "recorded_at": row[1].isoformat()}
                                      if row and isinstance(row[0], dict) else None)
    return result


def _specialist_projection(evidence, operating_date, now):
    selected = str(operating_date or evidence.get("operating_date"))[:10]
    weather = evidence.get("weather") or {}
    reassessment = evidence.get("reassessment")
    typed = reassessment.get("zones") if isinstance(reassessment, dict) else None
    typed = {str(row.get("zone_id")): row for row in typed
             if isinstance(row, dict) and row.get("zone_id") in ZONE_NAMES} if isinstance(typed, list) else {}
    recommendations = []
    for zone in ("B12345", "C12345"):
        row = typed.get(zone, {})
        state = str(row.get("decision") or row.get("status") or "")
        state = state if state in {"Run", "Hold", "Needs Data", "Not Due"} else "Needs Data"
        reason = (str(row.get("reason") or row.get("eligibility_blocker") or "").strip()
                  or "The scheduler has not persisted a typed current operating-date decision.")
        recommendations.append({"subject": zone,
            "status": {"Run": "Recommend", "Not Due": "Do Not Run"}.get(state, state),
            "reason": reason, "planned_duration_minutes": row.get("planned_duration_minutes"),
            "preferred_window": row.get("feasible_window"),
            "eligibility_blocker": row.get("eligibility_blocker"), "needs": []})
    overall = next((item["status"] for item in recommendations if item["status"] != "Needs Data"),
                   "Needs Data")
    return {"result_id": reassessment.get("result_id") if reassessment else None,
        "generation": reassessment.get("evidence_generation") if reassessment else None,
        "operating_date": selected, "evidence_cutoff": weather.get("observed_at"),
        "overall_status": overall, "current_local_weather": weather,
        "forecast": {"status": "kept_separate"}, "water_observations": evidence.get("water", {}),
        "next_reassessment": {"trigger": "scheduler_due_or_material_evidence_change",
            "at": reassessment.get("next_reassessment_at") if reassessment else None},
        "owner_brief": {"why": [reason]}, "recommendations": recommendations}


def _runtime_and_notification(database_url):
    import psycopg
    runtime = {}
    latest_outcome = {}
    notification = {"state": "not_sent", "provider_confirmed": False,
                    "reason": "No current execution notification exists."}
    with psycopg.connect(database_url, connect_timeout=10) as connection:
        connection.read_only = True
        with connection.cursor() as cursor:
            cursor.execute("""select created_at,review_json->'rootline_execution'
                from public.sam_live_stock_conversation_review_events
                where event_source='rootline_irrigation_execution'
                order by created_at desc limit 200""")
            events = [(created, value if isinstance(value, dict) else json.loads(value))
                      for created, value in cursor.fetchall()]
            runtime, latest_outcome, notification = _project_runtime(events)
    return runtime, latest_outcome, notification


def _project_runtime(events):
    runtime, latest_outcome = {}, {}
    notification = {"state": "not_sent", "provider_confirmed": False,
                    "reason": "No current execution notification exists."}
    by_execution = {}
    for created, item in events:
        execution = str(item.get("execution_id") or "")
        if execution:
            by_execution.setdefault(execution, []).append((created, item))
    terminal_actions = {"record_completed", "contain_zone", "record_ambiguous_shutdown",
                        "record_claim_recovery"}
    for execution_events in by_execution.values():
        actions = {str(item.get("action") or "") for _, item in execution_events}
        newest_at, newest = execution_events[0]
        terminal = next(((created, item) for created, item in execution_events
                         if item.get("action") in terminal_actions), None)
        if terminal and not latest_outcome:
            latest_outcome = {**terminal[1], "observed_at": terminal[0].isoformat()}
        if not runtime and "claim_before_on" in actions and not terminal:
            active = next(((created, item) for created, item in execution_events
                          if item.get("action") in {"mark_active", "claim_before_on"}),
                          (newest_at, newest))
            runtime = {**active[1], "observed_at": active[0].isoformat(),
                       "state": active[1].get("state") or "claimed"}
    for created, item in events:
        if (runtime and item.get("action") == "record_notification_delivery"
                and item.get("execution_id") == runtime.get("execution_id")):
            notification = {"state": item.get("notification_state") or "unknown",
                            "provider_confirmed": item.get("delivery_confirmed") is True,
                            "provider_message_id": item.get("provider_message_id"),
                            "observed_at": created.isoformat()}
            break
    return runtime, latest_outcome, notification


def _decision(value):
    return {"Recommend": "Run", "Hold": "Hold", "Needs Data": "Needs Data",
            "Do Not Run": "Not Due"}.get(str(value or ""), "Needs Data")


def _blocker(recommendation):
    technical = str(recommendation.get("eligibility_blocker") or "").strip()
    if technical:
        return technical
    if _decision(recommendation.get("status")) == "Run":
        return None
    needs = recommendation.get("needs") or []
    return needs[0] if needs else recommendation.get("reason") or "canonical_evidence_unavailable"


def _operational_state(decision, blocker, active):
    state = str(active.get("state") or "").lower()
    if state in {"running", "active", "segment_started"}: return "Running"
    if "shutdown" in state: return "Shutdown verification"
    if state in {"completed", "stopped"}: return "Completed"
    if decision == "Run" and blocker: return "Run — blocked"
    if decision == "Run": return "Run — waiting"
    return decision


def _zone_reason(recommendation, balance):
    reason = recommendation.get("reason") or "Canonical decision evidence is unavailable."
    if balance.get("ledger_current") is not True:
        reason += " Water-balance evidence is stale and is shown for audit, not current eligibility."
    return reason


def _current(runtime):
    state = str(runtime.get("state") or "IDLE")
    if state.lower() in {"active", "started", "running"}:
        state = "RUNNING"
    elif state.lower() in {"failed", "ambiguous", "contained"}:
        state = "FAILED"
    else:
        state = "IDLE"
    return {"status": state, "zone_id": runtime.get("zone_id") or "",
            "zone_name": ZONE_NAMES.get(runtime.get("zone_id"), ""),
            "last_update": runtime.get("observed_at"),
            "shutdown_verified": runtime.get("shutdown_verified")}


def _next_zone(zones):
    return next((zone["zone_id"] for zone in zones if zone["decision"] == "Run"), "")


def _completed_minutes(runtime):
    try:
        return float((runtime.get("objective_evidence") or {}).get("verified_runtime_minutes") or 0)
    except (TypeError, ValueError):
        return 0


def _timestamp(value):
    try:
        result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return result if result.tzinfo is not None else None
    except (TypeError, ValueError):
        return None


def _failure(status, exc=None):
    result = {"success": False, "status": status, "source": {"source": "supabase",
              "legacy_google_sheets_used": False}, "mode": "read_only"}
    if exc is not None:
        result["error_type"] = exc.__class__.__name__
    return result
