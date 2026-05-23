import os
from datetime import datetime
from zoneinfo import ZoneInfo

from services.google_sheets_service import get_all_records_from_spreadsheet


IRRIGATION_SHEET_NAME_ENV = "IRRIGATION_SHEET_NAME"
DEFAULT_IRRIGATION_SHEET_NAME = "Amadeus_Irrigation_Logs"
ZA_TZ = ZoneInfo("Africa/Johannesburg")


def get_irrigation_status(today=None, spreadsheet_name=None):
    sheet_name = (
        spreadsheet_name
        if spreadsheet_name is not None
        else os.getenv(IRRIGATION_SHEET_NAME_ENV, DEFAULT_IRRIGATION_SHEET_NAME)
    ).strip()
    today = str(today or _today_za()).strip()

    try:
        state_rows = _read_sheet(sheet_name, "STATE")
        plan_rows = _read_sheet(sheet_name, "DAILY_PLAN")
        zone_rows = _read_sheet(sheet_name, "ZONES")
        rule_rows = _read_sheet(sheet_name, "RULES")
        log_rows = _read_sheet(sheet_name, "LOG")
    except Exception as exc:
        return _unavailable(
            "source_read_failed",
            "Irrigation status could not be read from the irrigation sheet.",
            exc,
        ), 503

    zones_by_id = {
        _clean(row.get("zone_id")): row
        for row in zone_rows
        if _clean(row.get("zone_id"))
    }
    rules = _build_rules(rule_rows)
    state = _first_meaningful_state(state_rows)
    today_plan = [
        row for row in plan_rows
        if _date_part(row.get("date")) == today and _clean(row.get("plan_id"))
    ]
    recent_events = _recent_log_events(log_rows, limit=10)

    current_zone_id = _clean(state.get("current_zone_id"))
    current_status = _normalize_status(state.get("current_status"))
    if current_status == "UNKNOWN":
        running = next(
            (row for row in today_plan if _normalize_status(row.get("status")) == "RUNNING"),
            None,
        )
        if running:
            current_status = "RUNNING"
            current_zone_id = _clean(running.get("zone_id"))
        elif today_plan:
            current_status = "IDLE"

    next_zone_id = _clean(state.get("next_zone_id")) or _next_planned_zone_id(today_plan, zones_by_id)

    plan_items = [_format_plan_row(row, zones_by_id) for row in today_plan]
    counts = _plan_counts(today_plan)
    total_planned_minutes = sum(_to_num(row.get("planned_minutes"), 0) for row in today_plan)
    completed_minutes = sum(
        _to_num(row.get("planned_minutes"), 0)
        for row in today_plan
        if _normalize_status(row.get("status")) in {"DONE", "COMPLETED"}
    )

    notes = []
    if not state:
        notes.append("No irrigation STATE row was found.")
    if not today_plan:
        notes.append("No DAILY_PLAN rows were found for today.")
    if next_zone_id:
        notes.append(f"Next planned zone is {next_zone_id}.")
    if current_status == "RUNNING" and current_zone_id:
        notes.append(f"Zone {current_zone_id} is currently marked as running.")

    return {
        "success": bool(state or today_plan),
        "configured": True,
        "status": "ok" if (state or today_plan) else "unavailable",
        "mode": "read_only",
        "source": {
            "source": "google_sheets",
            "spreadsheet_name": sheet_name,
            "writes_to_sheets": False,
            "writes_to_supabase": False,
        },
        "safety": {
            "read_only": True,
            "can_control": False,
            "hardware_commands_enabled": False,
        },
        "current": {
            "status": current_status,
            "zone_id": current_zone_id,
            "zone_name": _zone_name(current_zone_id, zones_by_id),
            "remaining_minutes": _optional_num(state.get("remaining_minutes")),
            "pause_reason": _clean(state.get("pause_reason")),
            "last_update": _clean(state.get("last_update")),
            "last_zone_completed": _clean(state.get("last_zone_completed")),
        },
        "today": {
            "date": today,
            "planned_count": counts["planned"],
            "running_count": counts["running"],
            "done_count": counts["done"],
            "skipped_count": counts["skipped"],
            "paused_count": counts["paused"],
            "total_plan_rows": len(today_plan),
            "total_planned_minutes": total_planned_minutes,
            "completed_minutes": completed_minutes,
            "next_zone_id": next_zone_id,
            "next_zone_name": _zone_name(next_zone_id, zones_by_id),
            "plan": plan_items,
        },
        "recent_events": recent_events,
        "advisory_gates": {
            "weather": {
                "available": False,
                "status": "not_evaluated_in_read_only_sheet_status",
            },
            "power": {
                "available": False,
                "status": "not_evaluated_in_read_only_sheet_status",
            },
            "tank": {
                "available": False,
                "status": "not_configured_yet",
            },
        },
        "rules": {
            "wind_pause_kmh": _optional_num(rules.get("wind_pause_kmh")),
            "live_rain_skip_mm": _optional_num(rules.get("live_rain_skip_mm")),
            "rain_forecast_skip_mm_24h": _optional_num(rules.get("rain_forecast_skip_mm_24h")),
        },
        "operator_summary": {
            "headline": _headline(current_status, today_plan),
            "notes": notes,
        },
    }, 200


def _read_sheet(spreadsheet_name, tab_name):
    return get_all_records_from_spreadsheet(spreadsheet_name, tab_name)


def _today_za():
    return datetime.now(ZA_TZ).date().isoformat()


def _clean(value):
    return str(value or "").strip()


def _date_part(value):
    return _clean(value)[:10]


def _to_num(value, fallback=0):
    try:
        if value in (None, ""):
            return fallback
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _optional_num(value):
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_status(value):
    status = _clean(value).upper()
    if status in {"IDLE", "RUNNING", "PAUSED", "BLOCKED", "PLANNED", "DONE", "COMPLETED", "SKIPPED"}:
        return status
    return "UNKNOWN"


def _first_meaningful_state(rows):
    for row in rows:
        if any(_clean(row.get(key)) for key in ("state_id", "current_zone_id", "current_status", "next_zone_id")):
            return row
    return {}


def _build_rules(rows):
    rules = {}
    for row in rows:
        key = _clean(row.get("rule_key"))
        if key:
            rules[key] = row.get("rule_value")
    return rules


def _zone_name(zone_id, zones_by_id):
    if not zone_id:
        return ""
    return _clean(zones_by_id.get(zone_id, {}).get("name"))


def _format_plan_row(row, zones_by_id):
    zone_id = _clean(row.get("zone_id"))
    return {
        "plan_id": _clean(row.get("plan_id")),
        "date": _date_part(row.get("date")),
        "zone_id": zone_id,
        "zone_name": _zone_name(zone_id, zones_by_id),
        "planned_start": _clean(row.get("planned_start")),
        "planned_minutes": _optional_num(row.get("planned_minutes")),
        "status": _normalize_status(row.get("status")),
        "reason": _clean(row.get("reason")),
        "actual_start": _clean(row.get("actual_start")),
        "actual_end": _clean(row.get("actual_end")),
        "water_score": _optional_num(row.get("water_score")),
    }


def _plan_counts(rows):
    counts = {"planned": 0, "running": 0, "done": 0, "skipped": 0, "paused": 0}
    for row in rows:
        status = _normalize_status(row.get("status"))
        if status == "PLANNED":
            counts["planned"] += 1
        elif status == "RUNNING":
            counts["running"] += 1
        elif status in {"DONE", "COMPLETED"}:
            counts["done"] += 1
        elif status == "SKIPPED":
            counts["skipped"] += 1
        elif status == "PAUSED":
            counts["paused"] += 1
    return counts


def _next_planned_zone_id(rows, zones_by_id):
    planned = [row for row in rows if _normalize_status(row.get("status")) == "PLANNED"]
    if not planned:
        return ""
    planned.sort(
        key=lambda row: (
            -_to_num(row.get("water_score"), 0),
            _to_num(zones_by_id.get(_clean(row.get("zone_id")), {}).get("priority"), 999),
            _clean(row.get("zone_id")),
        )
    )
    return _clean(planned[0].get("zone_id"))


def _recent_log_events(rows, limit=10):
    events = []
    for row in rows:
        if not any(_clean(row.get(key)) for key in ("timestamp", "zone_id", "event", "reason", "plan_id")):
            continue
        events.append({
            "timestamp": _clean(row.get("timestamp")),
            "zone_id": _clean(row.get("zone_id")),
            "event": _clean(row.get("event")),
            "reason": _clean(row.get("reason")),
            "run_minutes_planned": _optional_num(row.get("run_minutes_planned")),
            "run_minutes_actual": _optional_num(row.get("run_minutes_actual")),
            "actor": _clean(row.get("actor")),
            "plan_id": _clean(row.get("plan_id")),
        })
    return events[-limit:]


def _headline(current_status, today_plan):
    if current_status == "RUNNING":
        return "Irrigation is currently marked as running."
    if current_status == "PAUSED":
        return "Irrigation is currently marked as paused."
    if current_status == "BLOCKED":
        return "Irrigation is currently marked as blocked."
    if today_plan:
        return "Irrigation has a plan for today."
    return "Irrigation status is unavailable or no plan is available for today."


def _unavailable(status, message, exc=None):
    body = {
        "success": False,
        "configured": True,
        "status": status,
        "mode": "read_only",
        "message": message,
        "source": {
            "source": "google_sheets",
            "writes_to_sheets": False,
            "writes_to_supabase": False,
        },
        "safety": {
            "read_only": True,
            "can_control": False,
            "hardware_commands_enabled": False,
        },
    }
    if exc is not None:
        body["error_type"] = exc.__class__.__name__
    return body
