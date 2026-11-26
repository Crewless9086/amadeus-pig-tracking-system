"""Read-only owner presentation over canonical ROOTLINE forecasts and receipts.

This adapter never calls devices, creates plans, or infers water delivery.
"""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import math

from modules.telemetry.weather_service import get_weather_forecast
from modules.telemetry.rootline_water_energy_plan import get_current_water_energy_plan
from modules.telemetry.rootline_command_acceptance import accepted, duty_closed, command_seconds
from modules.oom_sakkie.bounded_postgres_read import connect_bounded_rootline_postgres

ZA = ZoneInfo("Africa/Johannesburg")
DEVICES = (("camp_a", "Camp A", "A12345"), ("camp_b", "Camp B", "B12345"),
           ("camp_c", "Camp C", "C12345"), ("camp_e", "Camp E", "E12345"),
           ("mixer", "Mixer", "FERTILIZER-MIXER-CH2"),
           ("injection", "Injection", "FERTILIZER-INJECTION-CH1"),
           ("borehole", "Borehole", "BOREHOLE-1-MINI-R4-CH1"),
           ("eskom", "Eskom", "ESKOM"))
IDENTITIES = {canonical: key for key, _, canonical in DEVICES}
ACTIONS = ("claim_before_on", "mark_active", "mark_stopping", "record_completed",
           "contain_zone", "record_ambiguous_shutdown", "record_execution_not_dispatched",
           "claim_auxiliary_before_on", "mark_auxiliary_active", "mark_auxiliary_stopping",
           "record_auxiliary_completed", "record_auxiliary_control_pulse_stopped",
           "contain_auxiliary_device", "claim_borehole_before_on", "mark_borehole_active",
           "mark_borehole_stopping", "record_borehole_completed", "contain_borehole",
           "claim_eskom_before_command", "record_eskom_completed")
EVENT_LIMIT = 500


def _iso(value):
    return value.isoformat() if hasattr(value, "isoformat") else str(value) if value is not None else None


def _number(value):
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def project_forecast(payload):
    source = payload.get("source") or {}
    source = source if isinstance(source, dict) else {}
    rows = payload.get("days") or []
    stale = source.get("is_stale") is True
    return {"status": "stale" if stale else "available" if rows else "unavailable",
        "source": source.get("attribution_name") or source.get("source_name") or source.get("provider"),
        "source_url": source.get("attribution_url"),
        "forecast_run_at": source.get("last_forecast_run_at"),
        "reason": ("This forecast is older than the configured freshness limit." if stale else
            payload.get("message") if not rows else None),
        "days": [{"date": row.get("forecast_date"), "temp_max_c": _number(row.get("temp_max_c")),
            "temp_min_c": _number(row.get("temp_min_c")), "rain_mm": _number(row.get("rain_sum_mm")),
            "rain_probability_pct": _number(row.get("rain_probability_max_pct")),
            "wind_kmh": _number(row.get("wind_max_kmh")),
            "source": source.get("attribution_name") or source.get("source_name"),
            "forecast_run_at": source.get("last_forecast_run_at")} for row in rows[:3] if isinstance(row, dict)]}


def _identity(row):
    if str(row.get("action") or "").endswith("eskom_completed") or row.get("action") == "claim_eskom_before_command":
        return "eskom"
    for field in ("auxiliary_device_id", "zone_id", "device_key"):
        if row.get(field) in IDENTITIES:
            return IDENTITIES[row[field]]
    if row.get("device_id") == "1002851416" and row.get("channel") == 1:
        return "borehole"
    return None


def project_execution_event(event_id, at, row):
    """Describe a recorded transition; never promote historical evidence to live relay state."""
    if not isinstance(row, dict) or _identity(row) is None:
        return None
    action = str(row.get("action") or "")
    state, summary, kind = "unknown", "Recorded state requires review", "runtime_event"
    seconds = None
    if duty_closed(row):
        state, summary, kind = "off_command_accepted", "OFF command accepted", "run_stopped"
        seconds = command_seconds(row)
        if seconds:
            summary += f"; {seconds / 60:.1f} controller minutes accounted"
    elif accepted(row.get("command_on_receipt"), row, "ON"):
        if "stopping" in action or "contain" in action or "ambiguous" in action or "completed" in action:
            state, summary, kind = "stop_pending", "ON accepted; stop still requires confirmation", "stop_pending"
        else:
            state, summary, kind = "on_command_accepted", "ON command accepted", "run_started"
    elif action == "record_eskom_completed":
        proof = row.get("readback") or {}
        if proof.get("authoritative") is True and proof.get("state") in {"ON", "OFF"}:
            state, summary, kind = "observed_" + proof["state"].lower(), "Breaker observed " + proof["state"], "power_transition"
    elif row.get("shutdown_verified") is True:
        state, summary, kind = "off_verified", "Shutdown verified in the recorded event", "run_stopped"
        seconds = _number(row.get("verified_runtime_seconds"))
    elif action.startswith("claim_"):
        state, summary, kind = "request_claimed", "Controller claimed a start request; acceptance not yet recorded", "run_claimed"
    elif action == "record_execution_not_dispatched":
        state, summary, kind = "not_dispatched", "Request closed without an ON command", "run_not_dispatched"
    elif "contain" in action or "ambiguous" in action:
        state, summary, kind = "needs_attention", "Controller recorded an unresolved command outcome", "runtime_hold"
    reason = row.get("reason")
    if isinstance(reason, str) and reason:
        summary += " - " + reason.replace("_", " ")[:250]
    return {"id": str(event_id), "at": _iso(at), "device_id": _identity(row), "kind": kind,
        "summary": summary, "actor": "ROOTLINE", "status": state,
        "execution_id": row.get("execution_id"), "accounted_seconds": seconds,
        "state_basis": "Latest recorded controller event; see its timestamp"}


def read_execution_projection(database_url, now, *, include_plan=False):
    selected = now.astimezone(ZA).date().isoformat()
    with connect_bounded_rootline_postgres(database_url=database_url, read_only=True) as connection:
        with connection.cursor() as cursor:
            cursor.execute("""select review_event_id,created_at,review_json->'rootline_execution'
                from public.sam_live_stock_conversation_review_events
                where event_source='rootline_irrigation_execution'
                  and created_at >= %s and created_at <= %s
                  and review_json->'rootline_execution'->>'action'=any(%s)
                order by created_at desc,review_event_id desc limit %s""",
                (now - timedelta(days=7), now, list(ACTIONS), EVENT_LIMIT + 1))
            rows = cursor.fetchall()
        plan = get_current_water_energy_plan(selected, database_url, connection=connection)[0] if include_plan else {}
    projected = [project_execution_event(*row) for row in rows[:EVENT_LIMIT]]
    return {"events": [row for row in projected if row is not None], "plan": plan,
            "truncated": len(rows) > EVENT_LIMIT}


def project_next_action(device, identity, control_state, plan, now):
    from modules.telemetry.rootline_owner_controls import pending_owner_request
    request = pending_owner_request(control_state, device, now)
    if request:
        kind = request.get("change", {}).get("kind")
        return "One-off run queued; waiting for eligible conditions" if kind == "run" else "Stop request queued for controller supervision"
    mode = control_state.get("devices", {}).get(device, {}).get("mode", "automatic")
    if mode == "paused":
        return "Paused: no new automatic starts"
    if mode == "manual_today":
        return "Manual today: waiting for an owner run request"
    tasks = list(plan.get("candidate_tasks") or []) + list(plan.get("irrigation_auxiliary_tasks") or [])
    task = next((row for row in tasks if row.get("task_id") == "irrigation_" + identity
        or row.get("auxiliary_device_id") == identity
        or device == "borehole" and row.get("task_id") == "borehole"), None)
    if task:
        if task.get("owner_skip"):
            return "Skipped in today's saved plan"
        start = task.get("planned_start_at")
        if start:
            try:
                local = datetime.fromisoformat(str(start).replace("Z", "+00:00")).astimezone(ZA)
                return "Planned " + local.strftime("%d %b %H:%M") + "; current conditions still apply"
            except (TypeError, ValueError):
                pass
        decision = task.get("decision") or task.get("recommendation")
        if decision:
            return "Saved plan: " + str(decision).replace("_", " ")
    if device == "eskom":
        return "Respond to battery level and solar recovery"
    if device == "injection":
        from modules.telemetry.rootline_owner_auxiliary_policy import owner_injection_policy
        selected = owner_injection_policy(control_state, now=now)
        zones = selected["zone_ids"] if selected else ["B12345", "C12345"]
        return ("Wait for an eligible " + "/".join(zone[0] for zone in zones) + " run"
            if zones else "No camps selected for injection")
    return "Waiting for current planning evidence"


def project_devices(control_state, plan, events, now, *, unavailable=False, truncated=False):
    from modules.telemetry.rootline_owner_controls import owner_device_settings, owner_device_actions
    result = []
    for key, name, identity in DEVICES:
        records = [row for row in events if row["device_id"] == key]
        latest = records[0] if records else {}
        # One completed execution counts once even if multiple closure events were recorded.
        completed = {}
        for row in records:
            if row["kind"] == "run_stopped" and row.get("execution_id"):
                completed.setdefault(row["execution_id"], row)
        seconds = sum(row.get("accounted_seconds") or 0 for row in completed.values())
        summary = ("History unavailable" if unavailable else
            f"{len(completed)} recorded stops - {seconds / 60:.1f} controller minutes in returned seven-day history")
        if truncated:
            summary += " (partial history)"
        result.append({"id": key, "name": name,
            "state": "unavailable" if unavailable else latest.get("status", "unknown"),
            "state_basis": latest.get("state_basis", "No recent command evidence is available"),
            "observed_at": latest.get("at"), "summary": latest.get("summary", summary),
            "next_action": project_next_action(key, identity, control_state, plan, now),
            "settings": owner_device_settings(key, control_state, plan, now),
            "actions": owner_device_actions(key, control_state, plan, now),
            "run_summary": {"summary": summary, "stops": len(completed), "accounted_minutes": round(seconds / 60, 1),
                            "partial": truncated, "period_days": 7}})
    return result


def build_owner_control_projection(panel, *, control_state, now=None, database_url=None):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("aware_clock_required")
    result = {"observed_at": now.isoformat(), "timezone": "Africa/Johannesburg"}
    if panel in {None, "forecast"}:
        payload, _ = get_weather_forecast(days=3, database_url=database_url, as_of=now)
        result["forecast"] = project_forecast(payload)
    if panel in {None, "devices", "history"}:
        unavailable = False
        try:
            data = read_execution_projection(database_url, now, include_plan=panel in {None, "devices"})
        except Exception:
            unavailable = True
            data = {"events": [], "plan": {}, "truncated": False}
        events = data["events"]
        if panel in {None, "devices"}:
            result["devices"] = project_devices(control_state, data["plan"], events, now,
                unavailable=unavailable, truncated=data["truncated"])
        if panel in {None, "history"}:
            changes = control_state.get("history", [])
            changes = [row for row in changes if isinstance(row, dict)]
            result["history"] = {"status": "unavailable" if unavailable else "partial" if data["truncated"] else "available",
                "reason": "Run history could not be read; saved changes are shown separately." if unavailable else None,
                "rows": sorted(events + changes, key=lambda row: (str(row.get("at") or ""), str(row.get("id") or "")), reverse=True),
                "period_days": 7, "partial": data["truncated"]}
    return result


def project_plan_run(task, operating_date, records, *, truncated=False, unavailable=False):
    """Project command evidence for this day's automatic task, never a physical state."""
    from modules.telemetry.rootline_command_acceptance import job_completed
    from modules.telemetry.rootline_irrigation_job_contract import build_irrigation_job
    def result(status, label, at=None, reason=None):
        return {"run_status": status, "run_status_label": label,
                "run_observed_at": _iso(at), "run_reason": reason}
    if unavailable:
        return result("unavailable", "Status unavailable", reason="Run history could not be read.")
    if truncated:
        return result("unknown", "Status unknown", reason="Returned run history is incomplete.")
    zone = str(task.get("task_id") or "").removeprefix("irrigation_")
    matching = []
    unproven = False
    for event_id, at, row in records:
        if not isinstance(row, dict):
            return result("unknown", "Status unknown", reason="Run history contains an unrecognised record.")
        if row.get("zone_id") != zone or row.get("operating_date") != operating_date or row.get("owner_request_id"):
            continue
        # Rebuild the immutable automatic scheduled-job contract, rather than
        # matching today's latest device OFF or a mutable evidence generation.
        try:
            total = row.get("requested_total_duration_seconds")
            expected_minutes = task.get("requested_total_duration_minutes") or task.get("planned_duration_minutes")
            if row.get("stop_mode") != "scheduled" or type(total) is not int or total != expected_minutes * 60:
                unproven = True
                continue
            job = build_irrigation_job(zone_id=zone, operating_date=operating_date,
                requested_total_seconds=total, maximum_segment_seconds=total,
                plan_identity=row["evidence_generation"], stop_mode="scheduled")
            if row.get("job_id") != job["job_id"] or row.get("job_sha256") != job["job_sha256"]:
                unproven = True
                continue
        except (KeyError, TypeError, ValueError):
            unproven = True
            continue
        matching.append((event_id, at, row))
    if unproven:
        return result("unknown", "Status unknown", reason="Recorded task history could not be bound to its automatic programme.")
    if not matching:
        return result("pending", "Not started", reason="No matching automatic run is recorded for this task today.")
    jobs = {row["job_id"] for _, _, row in matching}
    if len(jobs) != 1:
        return result("unknown", "Status unknown", reason="Multiple automatic job records need reconciliation.")
    # Input order is the canonical created_at DESC, event-id DESC ordering.
    _, at, row = matching[0]
    action = str(row.get("action") or "")
    if job_completed(row):
        return result("completed", "Completed", at, "The complete controller programme is recorded as closed.")
    if duty_closed(row):
        return result("stopped", "Stopped", at, "The command duty closed; full programme completion is not proven.")
    if accepted(row.get("command_on_receipt"), row, "ON"):
        if any(word in action for word in ("stopping", "contain", "ambiguous", "completed")):
            return result("unknown", "Stop pending", at, "A later stop outcome is not yet confirmed.")
        if action == "mark_active":
            return result("running", "Running", at, "ON command accepted; this is recorded controller status.")
    return result("unknown", "Awaiting command evidence", at, "A claim or unresolved controller event is recorded.")


def read_plan_run_projection(plan, now, *, database_url=None):
    """Optional display read: failure never changes plan editing or execution."""
    tasks = plan.get("daily_program", {}).get("base_tasks", [])
    selected = plan.get("operating_date")
    try:
        start = datetime.fromisoformat(selected).replace(tzinfo=ZA)
        end = start + timedelta(days=1)
        with connect_bounded_rootline_postgres(database_url=database_url, read_only=True) as connection:
            with connection.cursor() as cursor:
                cursor.execute("""select review_event_id,created_at,review_json->'rootline_execution'
                    from public.sam_live_stock_conversation_review_events
                    where event_source='rootline_irrigation_execution'
                      and created_at >= %s and created_at < %s and created_at <= %s
                      and review_json->'rootline_execution'->>'operating_date'=%s
                      and review_json->'rootline_execution'->>'zone_id'=any(%s)
                      and review_json->'rootline_execution'->>'action'=any(%s)
                    order by created_at desc,review_event_id desc limit %s""",
                    (start, end, now, selected,
                     [str(t.get("task_id") or "").removeprefix("irrigation_") for t in tasks],
                     ["claim_before_on", "mark_active", "mark_stopping", "record_completed",
                      "contain_zone", "record_ambiguous_shutdown", "record_execution_not_dispatched",
                      "record_claim_recovery", "record_job_resolution"],
                     EVENT_LIMIT + 1))
                records = cursor.fetchall()
        return {t["task_id"]: project_plan_run(t, selected, records[:EVENT_LIMIT],
                    truncated=len(records) > EVENT_LIMIT) for t in tasks if t.get("task_id")}
    except Exception:
        return {t["task_id"]: project_plan_run(t, selected, [], unavailable=True)
                for t in tasks if t.get("task_id")}
