"""Canonical planner-to-coordinator authority for commissioned B/C only.

This internal artifact is distinct from ROOTLINE's read-only family result.
It grants one bounded execution only after canonical planning, water/weather,
weekly debt and current controller evidence all pass together.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from modules.telemetry.rootline_irrigation_job_contract import (
    build_irrigation_job, project_next_segment,
)
from modules.telemetry.rootline_device_registry import rootline_device_registry

MAX_SECONDS = 3599
CONTRACT_VERSION = "rootline_execution_eligibility.v5"
STANDING_AUTHORITY = "owner_approved_routine_irrigation_v1"


def build_execution_eligibility(*, plan, evidence, controller, now=None,
                                job_event_reader=lambda _job_id: ()):
    now = _aware(now or datetime.now(timezone.utc))
    if not isinstance(plan, dict) or not isinstance(evidence, dict):
        return _none("canonical_plan_unavailable")
    tasks = [item for item in plan.get("candidate_tasks") or [] if isinstance(item, dict)]
    zones = _zone_contracts()
    candidates = []
    for task in tasks:
        task_id = str(task.get("task_id") or "")
        zone = task_id.removeprefix("irrigation_")
        parent = task.get("incomplete_parent_job") if isinstance(
            task.get("incomplete_parent_job"), dict) else {}
        parent_job = parent.get("job") if isinstance(parent.get("job"), dict) else {}
        parent_date_current = (not parent_job or parent_job.get("operating_date") ==
            str(plan.get("operating_date") or "")[:10])
        contained = task.get("contained_parent_jobs") if isinstance(
            task.get("contained_parent_jobs"), list) else []
        if (zone in zones and not contained and parent_date_current
                and task.get("zone_decision") == "Run now"
                and task.get("recommendation") == "Recommend"
                and int(task.get("planned_duration_minutes") or 0) in range(1, 61)):
            candidates.append((int(task.get("rank") or 999), zone, task))
    if not candidates:
        unresolved = [task for task in tasks
            if isinstance(task.get("incomplete_parent_job"), dict)]
        if unresolved:
            task = sorted(unresolved, key=lambda item: str(item.get("task_id")))[0]
            parent = task["incomplete_parent_job"]
            job = parent.get("job") if isinstance(parent.get("job"), dict) else {}
            material = {"contract_version": "rootline_irrigation_job_resolution.v1",
                "resolution": "Deferred", "job_id": job.get("job_id"),
                "job_sha256": job.get("job_sha256"), "zone_id": job.get("zone_id"),
                "operating_date": job.get("operating_date"),
                "current_segment": (parent.get("projection") or {}).get("current_segment"),
                "expected_segment_count": job.get("expected_segment_count"),
                "cumulative_verified_runtime_seconds": (parent.get("projection") or {}).get("cumulative_verified_runtime_seconds"),
                "remaining_seconds": parent.get("remaining_seconds"),
                "reason": task.get("reason"), "source_plan_generation": plan.get("evidence_generation")}
            digest = _digest(material)
            return {"success": True, "status": "durable_parent_job_deferred",
                "eligible": False, "command_authority": False, "hardware_control": False,
                "job_resolution": {**material, "resolution_sha256": digest,
                    "execution_id": "ROOTLINE-JOB-RESOLUTION-" + digest[:24].upper()}}
        return _none("planner_hold_or_no_dispatchable_zone")
    _, zone, task = min(candidates, key=lambda row: (row[0], row[1]))
    irrigation = evidence.get("irrigation") if isinstance(evidence.get("irrigation"), dict) else {}
    advisor_zones = irrigation.get("zones") if isinstance(irrigation.get("zones"), list) else []
    advisor_zone = next((row for row in advisor_zones
        if isinstance(row, dict) and row.get("zone_id") == zone), None)
    advisor_at = _timestamp(irrigation.get("advisor_generated_at"))
    if (irrigation.get("source") != "rootline_daily_advisor"
            or irrigation.get("advisor_operating_date") != str(plan.get("operating_date") or "")[:10]
            or advisor_at is None or now < advisor_at
            or now - advisor_at > timedelta(minutes=30)
            or not advisor_zone
            or advisor_zone.get("live_rain_release_proven") is not True):
        return _none("live_rain_release_not_proven")
    weather = evidence.get("weather") if isinstance(evidence.get("weather"), dict) else {}
    weather_time = _timestamp(weather.get("observed_at"))
    if (weather_time is None or now - weather_time > timedelta(minutes=30)
            or now < weather_time or _number(weather.get("rain_rate_mm_h")) > 0
            or _number(weather.get("rain_today_mm")) >= 2):
        return _none("observed_weather_not_fresh_and_dry")
    tanks = evidence.get("tanks") if isinstance(evidence.get("tanks"), dict) else {}
    water_time = _timestamp(tanks.get("reservoir_observed_at") or tanks.get("observed_at"))
    water_current = (water_time is not None and not now < water_time
                     and now-water_time <= timedelta(hours=24))
    reservoir_ok = (str(tanks.get("reservoir_state") or "").upper() in {"OK", "FULL"}
                    or _number(tanks.get("reservoir_fraction")) >= .25
                    or _number(tanks.get("reservoir_reported_count")) > 0)
    explicit_water_fault = water_current and any(tanks.get(key) is True for key in (
        "insufficient_water", "dry_supply", "supply_fault", "evidence_conflict"))
    explicit_current_shortage = water_current and bool(tanks) and not reservoir_ok
    if explicit_water_fault or explicit_current_shortage:
        return _none("current_water_shortage_or_fault")
    water_policy = {"contract_version": "rootline_standing_water_policy.v1",
        "mode": "fresh_available" if water_current else "standing_available_unobserved",
        "water_assumed_available": not water_current,
        "storage_replenishment_assumed_required": True,
        "current_contradictory_evidence": False}
    obligation = task.get("weekly_obligation") if isinstance(task.get("weekly_obligation"), dict) else {}
    if (obligation.get("status") != "available"
            or int(obligation.get("delivery_debt_days") or 0) <= 0):
        return _none("weekly_delivery_debt_not_dispatchable")
    controller_status = _controller(controller, zone, now)
    if not controller_status:
        return _none("controller_safety_not_dispatchable")
    source_plan_generation = str(plan.get("evidence_generation") or "")
    if not source_plan_generation:
        return _none("plan_generation_unavailable")
    operating_date = str(plan.get("operating_date") or "")[:10]
    if not _valid_operating_date(operating_date):
        return _none("operating_date_unavailable")
    governed_obligation = {key: value for key, value in obligation.items()
                           if key != "ledger_complete_through"}
    irrigation_plan_material = {"zone_id": zone, "zone_decision": task.get("zone_decision"),
        "rank": task.get("rank"), "planned_duration_minutes": task.get("planned_duration_minutes"),
        "requested_total_duration_minutes": task.get("requested_total_duration_minutes"),
        "expected_segment_count": task.get("expected_segment_count"),
        "weekly_obligation": governed_obligation, "reason": task.get("reason")}
    plan_generation = "ROOTLINE-IRRIGATION-PLAN-" + _digest(irrigation_plan_material)[:24].upper()
    duration = min(60, int(task["planned_duration_minutes"]))
    requested_minutes = int(task.get("requested_total_duration_minutes") or 0)
    expected_segments = int(task.get("expected_segment_count") or 0)
    if requested_minutes <= 0 or expected_segments <= 0:
        return _none("governed_total_duration_unavailable")
    requested_total_seconds = requested_minutes * 60
    parent = task.get("incomplete_parent_job") if isinstance(task.get("incomplete_parent_job"), dict) else {}
    parent_job = parent.get("job") if isinstance(parent.get("job"), dict) else None
    job = (dict(parent_job) if parent_job else build_irrigation_job(
        zone_id=zone, operating_date=operating_date,
        requested_total_seconds=requested_total_seconds,
        maximum_segment_seconds=MAX_SECONDS, plan_identity=plan_generation,
        requested_total_minutes=requested_minutes,
        expected_segment_count=expected_segments))
    if (job.get("zone_id") != zone
            or int(job.get("requested_total_seconds") or 0) != requested_total_seconds
            or int(job.get("expected_segment_count") or 0) != expected_segments):
        return _none("durable_parent_job_binding_invalid")
    plan_generation = job["plan_identity"]
    operating_date = job["operating_date"]
    try:
        segment = project_next_segment(job, job_event_reader(job["job_id"]) or (),
            rearm_readback_off=True)
    except Exception:
        return _none("canonical_job_history_invalid")
    if segment.get("status") != "segment_ready":
        return _none(segment.get("status") or "canonical_job_not_dispatchable")
    consumption_key = "ROOTLINE-IRRIGATION-CONSUMPTION-" + _digest({
        "source_plan_generation": source_plan_generation,
        "operating_date": operating_date,
        "irrigation_plan_generation": plan_generation,
        "zone_id": zone, "job_id": job["job_id"],
        "segment_number": segment["segment_number"],
    })[:24].upper()
    cutoff = max(value for value in (
        weather_time, water_time if water_current else None,
        controller_status["retrieved_at"]) if value is not None)
    notification = "ROOTLINE-IRRIGATION-NOTIFY-" + _digest({
        "plan": plan_generation, "zone": zone, "cutoff": cutoff.isoformat()})[:24].upper()
    material = {
        "contract_version": CONTRACT_VERSION,
        "authority_source": STANDING_AUTHORITY,
        "source_plan_generation": source_plan_generation,
        "operating_date": operating_date,
        "plan_generation": plan_generation,
        "plan_evidence_digest": _digest({"plan_generation": plan_generation,
            "irrigation_plan": irrigation_plan_material, "weather": weather, "tanks": tanks}),
        "zone_id": zone, "channel": zones[zone]["channel"],
        "maximum_duration_seconds": segment["segment_requested_seconds"],
        "job_id": job["job_id"], "job_sha256": job["job_sha256"],
        "requested_total_duration_seconds": job["requested_total_seconds"],
        "governed_executable_duration_seconds": job["governed_executable_seconds"],
        "requested_total_duration_minutes": job["requested_total_minutes"],
        "expected_segment_count": job["expected_segment_count"],
        "current_segment": segment["segment_number"],
        "segment_identity": segment["segment_identity"],
        "segment_requested_seconds": segment["segment_requested_seconds"],
        "cumulative_verified_runtime_seconds": segment[
            "cumulative_verified_runtime_seconds"],
        "predecessor_off_rearm_verified": segment[
            "predecessor_off_rearm_verified"],
        "weekly_debt": obligation,
        "observed_weather": {"observed_at": weather_time.isoformat(),
            "rain_rate_mm_h": _number(weather.get("rain_rate_mm_h")),
            "rain_today_mm": _number(weather.get("rain_today_mm"))},
        "live_rain_release": {"source": "rootline_daily_advisor",
            "advisor_generated_at": advisor_at.isoformat(),
            "advisor_operating_date": irrigation["advisor_operating_date"],
            "zone_id": zone, "proven": True,
            "forecast_planning_quality": advisor_zone.get("forecast_planning_quality"),
            "planning_warnings": list(advisor_zone.get("planning_warnings") or [])},
        "water_evidence": {"observed_at": water_time.isoformat() if water_current else None,
            "reservoir_state": tanks.get("reservoir_state") if water_current else None,
            "reservoir_fraction": tanks.get("reservoir_fraction") if water_current else None,
            "reservoir_reported_count": tanks.get("reservoir_reported_count") if water_current else None,
            "standing_policy": water_policy},
        "controller_safety_generation": controller_status["generation"],
        "provider_output_state": controller_status["outputs"],
        "controller_response_digest": controller_status["response_digest"],
        "decision_at": now.isoformat(), "evidence_cutoff": cutoff.isoformat(),
        "expires_at": (now + timedelta(minutes=15)).isoformat(),
        "command_mapping": _command_mapping(zones[zone]),
        "notification_identity": notification,
        "consumption_key": consumption_key,
        "single_use": True, "simultaneous_irrigation": False,
        "automatic_second_segment": False,
    }
    digest = _digest(material)
    identity = "ROOTLINE-ELIGIBILITY-" + digest[:24].upper()
    execution = "ROOTLINE-EXECUTION-" + digest[:24].upper()
    return {"success": True, "status": "execution_eligible", "eligible": True,
            "eligibility_id": identity, "eligibility_sha256": digest,
            "execution_id": execution, **material,
            "command_authority": True, "hardware_control": True,
            "authority_scope": "single_bounded_irrigation_segment"}


def validate_execution_eligibility(value, *, now=None):
    now = _aware(now or datetime.now(timezone.utc))
    if not isinstance(value, dict) or value.get("eligible") is not True:
        return None
    material = {key: item for key, item in value.items() if key not in {
        "success", "status", "eligible", "eligibility_id", "eligibility_sha256",
        "execution_id", "command_authority", "hardware_control", "authority_scope"}}
    digest = _digest(material)
    zones = _zone_contracts()
    if (value.get("contract_version") != CONTRACT_VERSION
            or value.get("authority_source") != STANDING_AUTHORITY
            or value.get("eligibility_sha256") != digest
            or value.get("eligibility_id") != "ROOTLINE-ELIGIBILITY-" + digest[:24].upper()
            or value.get("execution_id") != "ROOTLINE-EXECUTION-" + digest[:24].upper()
            or value.get("zone_id") not in zones
            or value.get("channel") != zones[value["zone_id"]]["channel"]
            or value.get("command_mapping") != _command_mapping(zones[value["zone_id"]])
            or not str(value.get("source_plan_generation") or "")
            or not _valid_operating_date(value.get("operating_date"))
            or not str(value.get("consumption_key") or "").startswith(
                "ROOTLINE-IRRIGATION-CONSUMPTION-")
            or value.get("single_use") is not True
            or value.get("simultaneous_irrigation") is not False
            or value.get("automatic_second_segment") is not False
            or value.get("command_authority") is not True or value.get("hardware_control") is not True):
        return None
    decision_at = _timestamp(value.get("decision_at")); expires = _timestamp(value.get("expires_at"))
    if decision_at is None or expires is None or not (decision_at <= now <= expires):
        return None
    if int(value.get("maximum_duration_seconds") or 0) not in range(1, MAX_SECONDS + 1):
        return None
    return value


def equivalent_fresh_eligibility(original, fresh, *, now=None):
    original = validate_execution_eligibility(original, now=now)
    fresh = validate_execution_eligibility(fresh, now=now)
    if not original or not fresh:
        return False
    # Fresh request/receipt timestamps necessarily produce a new source generation
    # and evidence digest. Equivalence binds the governed decision material while
    # the freshly rebuilt artifact independently re-proves weather, water and controller safety.
    keys = ("plan_generation", "operating_date", "zone_id", "channel",
            "maximum_duration_seconds", "command_mapping", "job_id",
            "requested_total_duration_seconds", "expected_segment_count",
            "current_segment", "segment_identity",
            "controller_safety_generation")
    return (all(original.get(key) == fresh.get(key) for key in keys)
            and _governed_debt(original.get("weekly_debt")) ==
                _governed_debt(fresh.get("weekly_debt")))


def _governed_debt(value):
    return ({key: item for key, item in value.items() if key != "ledger_complete_through"}
            if isinstance(value, dict) else value)


def _valid_operating_date(value):
    text = str(value or "")
    try:
        return datetime.fromisoformat(text).date().isoformat() == text
    except (TypeError, ValueError):
        return False


def _controller(value, zone, now):
    contract = _zone_contracts().get(zone)
    if (not contract or not isinstance(value, dict)
            or value.get("device_id") != contract["device_id"]
            or value.get("online") is not True or value.get("firmware") != "3.8.2"
            or value.get("actuation_configuration_safe") is not True
            or value.get("timers_enabled") is not False
            or value.get("scenes_enabled") is not False
            or value.get("interlock_enabled") is not False
            or value.get("provider_control_calls") != 0):
        return None
    rows = value.get("channels") if isinstance(value.get("channels"), list) else []
    if sorted(row.get("channel") for row in rows if isinstance(row, dict)) != [1, 2, 3, 4]:
        return None
    selected = next((row for row in rows if row.get("channel") == contract["channel"]), None)
    relevant_channels = {item["channel"] for item in _zone_contracts().values()
                         if item["device_id"] == contract["device_id"]}
    relevant = [row for row in rows if row.get("channel") in relevant_channels]
    if (not selected or any(row.get("output_state") != "OFF" for row in relevant)
            or selected.get("native_auto_off_enabled") is not True
            or int(selected.get("native_auto_off_seconds") or 0) not in range(1, MAX_SECONDS + 1)
            or any(row.get("power_restoration_state") != "OFF" for row in relevant)):
        return None
    retrieved = _timestamp(value.get("trusted_receipt_at") or value.get("retrieved_at")
                           or value.get("observation_receipt_at"))
    if retrieved is None or now < retrieved or now-retrieved > timedelta(minutes=5):
        return None
    generation = str(value.get("commissioned_baseline_id") or value.get("controller_safety_generation") or "")
    if not generation or not value.get("response_digest"):
        return None
    return {"generation": generation, "retrieved_at": retrieved,
            "outputs": {str(row["channel"]): row["output_state"] for row in relevant},
            "response_digest": value["response_digest"]}


def _zone_contracts(registry=None):
    rows = registry if isinstance(registry, dict) else rootline_device_registry()
    return {identity: row for identity, row in rows.items()
            if row.get("collection") == "irrigation_zones"
            and row.get("device_type") == "irrigation_zone_valve"
            and row.get("commissioned") is True
            and str(row.get("commissioning_id") or "")
            and isinstance(row.get("commissioning_generation"), int)}


def _command_mapping(contract):
    return {"channel": contract["channel"], "on": contract["on_event"],
            "off": contract["off_event"]}


def _none(status):
    return {"success": True, "status": status, "eligible": False,
            "command_authority": False, "hardware_control": False}


def _timestamp(value):
    try: return _aware(datetime.fromisoformat(str(value).replace("Z", "+00:00")))
    except (TypeError, ValueError): return None


def _aware(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _number(value):
    try: return float(value or 0)
    except (TypeError, ValueError): return 0.0


def _digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                             default=str).encode()).hexdigest()
