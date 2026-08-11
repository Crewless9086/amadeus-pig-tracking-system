"""Truthful owner projection over ROOTLINE's existing canonical rails."""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from zoneinfo import ZoneInfo

from modules.telemetry.rootline_irrigation_history import read_canonical_irrigation_history

ZONE_NAMES = {"B12345": "B Camp", "C12345": "C Camp"}


def get_rootline_owner_status(operating_date=None, database_url=None, now=None):
    now = now or datetime.now(timezone.utc)
    database_url = str(database_url or os.getenv("DATABASE_URL") or "").strip()
    if not database_url:
        return _failure("database_not_configured"), 503
    try:
        evidence = _canonical_evidence(database_url, operating_date, now)
        specialist = _specialist_projection(evidence, operating_date, now)
        history = read_canonical_irrigation_history(database_url, now=now)
        runtime, notification = _runtime_and_notification(database_url)
    except Exception as exc:
        return _failure("canonical_status_read_failed", exc), 503
    recommendations = {item.get("subject"): item for item in
                       specialist.get("recommendations", []) if isinstance(item, dict)}
    zones = []
    for zone_id in ("B12345", "C12345"):
        recommendation = recommendations.get(zone_id, {})
        zone_history = (history.get("zones") or {}).get(zone_id, {})
        balance = (evidence.get("water_balance") or {}).get(zone_id, {})
        active = runtime if runtime.get("zone_id") == zone_id else {}
        zones.append({
            "zone_id": zone_id,
            "zone_name": ZONE_NAMES[zone_id],
            "decision": _decision(recommendation.get("status")),
            "reason": recommendation.get("reason") or "Canonical decision evidence is unavailable.",
            "planned_minutes": recommendation.get("planned_duration_minutes"),
            "feasible_window": recommendation.get("preferred_window"),
            "effective_rainfall_mm": balance.get("effective_rainfall_mm"),
            "remaining_supported_water_need_mm": balance.get("remaining_water_need_mm"),
            "water_balance_complete_through": balance.get("complete_through"),
            "eligibility_blocker": _blocker(recommendation),
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
        "operator_summary": {"headline": specialist.get("overall_status") or "Needs Data",
                             "notes": [specialist.get("owner_brief", {}).get("why", ["Canonical status available."])[0]]},
        "safety": {"read_only": True, "can_control": False,
                   "hardware_commands_enabled": False},
    }, 200


def _canonical_evidence(database_url, operating_date, now):
    import psycopg
    selected = str(operating_date or now.astimezone(ZoneInfo("Africa/Johannesburg")).date().isoformat())[:10]
    result = {"operating_date": selected, "water_balance": {}}
    with psycopg.connect(database_url, connect_timeout=10) as connection:
        connection.read_only = True
        with connection.cursor() as cursor:
            cursor.execute("""select reading_at,rain_rate_mm_h,rain_today_mm,
                                      temperature_c,wind_speed_kmh,updated_at
                from public.weather_latest_state order by reading_at desc limit 1""")
            row = cursor.fetchone()
            result["weather"] = ({"status": "fresh", "observed_at": row[0].isoformat(),
                "rain_rate_mm_h": float(row[1]) if row[1] is not None else None,
                "rain_today_mm": float(row[2]) if row[2] is not None else None,
                "temperature_c": float(row[3]) if row[3] is not None else None,
                "wind_speed_kmh": float(row[4]) if row[4] is not None else None,
                "retrieved_at": row[5].isoformat()} if row else {"status": "Unavailable"})
            cursor.execute("""select zone_id,balance_json from public.irrigation_water_balance_events
                where (zone_id,created_at) in (select zone_id,max(created_at)
                    from public.irrigation_water_balance_events group by zone_id)""")
            result["water_balance"] = {zone: value for zone, value in cursor.fetchall()}
            cursor.execute("""select storage_state,reservoir_state,observed_at,
                                      storage_fraction_numerator,storage_fraction_denominator,
                                      reservoir_fraction_numerator,reservoir_fraction_denominator
                from public.rootline_tank_observations order by observed_at desc,recorded_at desc limit 1""")
            row = cursor.fetchone()
            result["water"] = ({"status": "available", "storage_state": row[0],
                "reservoir_state": row[1], "observed_at": row[2].isoformat(),
                "storage_fraction": list(row[3:5]) if row[3] is not None else None,
                "reservoir_fraction": list(row[5:7]) if row[5] is not None else None}
                if row else {"status": "Unavailable"})
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
    rain = weather.get("rain_rate_mm_h")
    if rain is not None and rain > 0.2:
        state, reason = "Hold", "Fresh observed rain is above the live-rain threshold."
    elif reassessment is None:
        state, reason = "Needs Data", "The scheduler has not persisted a current operating-date decision."
    else:
        answer = str(reassessment.get("answer") or "")
        state = "Hold" if "Hold" in answer else "Needs Data"
        reason = "Current scheduler decision is available." if answer else "Current scheduler decision payload is incomplete."
    recommendations = [{"subject": zone, "status": state, "reason": reason,
        "planned_duration_minutes": 60 if state in {"Hold", "Needs Data"} else None,
        "preferred_window": "next scheduler-owned eligible window", "needs": []}
        for zone in ("B12345", "C12345")]
    return {"result_id": reassessment.get("result_id") if reassessment else None,
        "generation": reassessment.get("evidence_generation") if reassessment else None,
        "operating_date": selected, "evidence_cutoff": weather.get("observed_at"),
        "overall_status": state, "current_local_weather": weather,
        "forecast": {"status": "kept_separate"}, "water_observations": evidence.get("water", {}),
        "next_reassessment": {"trigger": "scheduler_due_or_material_evidence_change",
            "at": reassessment.get("next_reassessment_at") if reassessment else None},
        "owner_brief": {"why": [reason]}, "recommendations": recommendations}


def _runtime_and_notification(database_url):
    import psycopg
    runtime = {}
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
            terminal = set()
            for created, item in events:
                execution = str(item.get("execution_id") or "")
                action = str(item.get("action") or "")
                if action in {"record_completed", "contain_zone", "record_ambiguous_shutdown",
                              "record_claim_recovery"}:
                    terminal.add(execution)
                if not runtime and action in {"claim_before_on", "mark_active", "record_completed",
                                               "contain_zone", "record_ambiguous_shutdown"}:
                    runtime = {**item, "observed_at": created.isoformat()}
            for created, item in events:
                if item.get("action") == "record_notification_delivery":
                    notification = {"state": item.get("notification_state") or "unknown",
                                    "provider_confirmed": item.get("delivery_confirmed") is True,
                                    "provider_message_id": item.get("provider_message_id"),
                                    "observed_at": created.isoformat()}
                    break
            if runtime and runtime.get("execution_id") not in terminal and runtime.get("state") != "Completed":
                runtime["state"] = runtime.get("state") or "claimed"
    return runtime, notification


def _decision(value):
    return {"Recommend": "Run", "Hold": "Hold", "Needs Data": "Needs Data",
            "Do Not Run": "Not Due"}.get(str(value or ""), "Needs Data")


def _blocker(recommendation):
    if _decision(recommendation.get("status")) == "Run":
        return None
    needs = recommendation.get("needs") or []
    return needs[0] if needs else recommendation.get("reason") or "canonical_evidence_unavailable"


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


def _failure(status, exc=None):
    result = {"success": False, "status": status, "source": {"source": "supabase",
              "legacy_google_sheets_used": False}, "mode": "read_only"}
    if exc is not None:
        result["error_type"] = exc.__class__.__name__
    return result
