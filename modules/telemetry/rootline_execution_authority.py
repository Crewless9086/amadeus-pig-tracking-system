"""Canonical planner-to-coordinator authority for commissioned B/C only.

This internal artifact is distinct from ROOTLINE's read-only family result.
It grants one bounded execution only after canonical planning, water/weather,
weekly debt and current controller evidence all pass together.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json

DEVICE_ID = "100204e9bc"
MAX_SECONDS = 3599
ZONE = {
    "B12345": {"channel": 1, "on": "irrigation_1_ch1_on", "off": "irrigation_1_ch1_off"},
    "C12345": {"channel": 2, "on": "irrigation_1_ch2_on", "off": "irrigation_1_ch2_off"},
}
CONTRACT_VERSION = "rootline_execution_eligibility.v1"
STANDING_AUTHORITY = "owner_approved_routine_bc_irrigation_v1"


def build_execution_eligibility(*, plan, evidence, controller, now=None):
    now = _aware(now or datetime.now(timezone.utc))
    if not isinstance(plan, dict) or not isinstance(evidence, dict):
        return _none("canonical_plan_unavailable")
    tasks = [item for item in plan.get("candidate_tasks") or [] if isinstance(item, dict)]
    candidates = []
    for task in tasks:
        task_id = str(task.get("task_id") or "")
        zone = task_id.removeprefix("irrigation_")
        if (zone in ZONE and task.get("zone_decision") == "Run now"
                and task.get("recommendation") == "Recommend"
                and int(task.get("planned_duration_minutes") or 0) in range(1, 61)):
            candidates.append((int(task.get("rank") or 999), zone, task))
    if not candidates:
        return _none("planner_hold_or_no_dispatchable_zone")
    _, zone, task = min(candidates, key=lambda row: (row[0], row[1]))
    weather = evidence.get("weather") if isinstance(evidence.get("weather"), dict) else {}
    weather_time = _timestamp(weather.get("observed_at"))
    if (weather_time is None or now - weather_time > timedelta(minutes=30)
            or now < weather_time or _number(weather.get("rain_rate_mm_h")) > 0
            or _number(weather.get("rain_today_mm")) >= 2):
        return _none("observed_weather_not_fresh_and_dry")
    tanks = evidence.get("tanks") if isinstance(evidence.get("tanks"), dict) else {}
    water_time = _timestamp(tanks.get("reservoir_observed_at") or tanks.get("observed_at"))
    reservoir_ok = (str(tanks.get("reservoir_state") or "").upper() in {"OK", "FULL"}
                    or _number(tanks.get("reservoir_fraction")) >= .25
                    or _number(tanks.get("reservoir_reported_count")) > 0)
    if (water_time is None or now < water_time or now-water_time > timedelta(hours=24)
            or not reservoir_ok):
        return _none("water_evidence_not_fresh_and_adequate")
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
    irrigation_plan_material = {"zone_id": zone, "zone_decision": task.get("zone_decision"),
        "rank": task.get("rank"), "planned_duration_minutes": task.get("planned_duration_minutes"),
        "weekly_obligation": obligation, "reason": task.get("reason")}
    plan_generation = "ROOTLINE-BC-PLAN-" + _digest(irrigation_plan_material)[:24].upper()
    duration = min(60, int(task["planned_duration_minutes"]))
    cutoff = max(weather_time, water_time, controller_status["retrieved_at"])
    notification = "ROOTLINE-IRRIGATION-NOTIFY-" + _digest({
        "plan": plan_generation, "zone": zone, "cutoff": cutoff.isoformat()})[:24].upper()
    material = {
        "contract_version": CONTRACT_VERSION,
        "authority_source": STANDING_AUTHORITY,
        "plan_generation": plan_generation,
        "plan_evidence_digest": _digest({"plan_generation": plan_generation,
            "irrigation_plan": irrigation_plan_material, "weather": weather, "tanks": tanks}),
        "zone_id": zone, "channel": ZONE[zone]["channel"],
        "maximum_duration_seconds": min(MAX_SECONDS, duration * 60),
        "weekly_debt": obligation,
        "observed_weather": {"observed_at": weather_time.isoformat(),
            "rain_rate_mm_h": _number(weather.get("rain_rate_mm_h")),
            "rain_today_mm": _number(weather.get("rain_today_mm"))},
        "water_evidence": {"observed_at": water_time.isoformat(),
            "reservoir_state": tanks.get("reservoir_state"),
            "reservoir_fraction": tanks.get("reservoir_fraction"),
            "reservoir_reported_count": tanks.get("reservoir_reported_count")},
        "controller_safety_generation": controller_status["generation"],
        "provider_output_state": controller_status["outputs"],
        "controller_response_digest": controller_status["response_digest"],
        "decision_at": now.isoformat(), "evidence_cutoff": cutoff.isoformat(),
        "expires_at": (now + timedelta(minutes=15)).isoformat(),
        "command_mapping": dict(ZONE[zone]),
        "notification_identity": notification,
        "single_use": True, "simultaneous_bc": False,
        "automatic_second_segment": False,
    }
    digest = _digest(material)
    identity = "ROOTLINE-ELIGIBILITY-" + digest[:24].upper()
    execution = "ROOTLINE-EXECUTION-" + digest[:24].upper()
    return {"success": True, "status": "execution_eligible", "eligible": True,
            "eligibility_id": identity, "eligibility_sha256": digest,
            "execution_id": execution, **material,
            "command_authority": True, "hardware_control": True,
            "authority_scope": "single_bounded_bc_segment"}


def validate_execution_eligibility(value, *, now=None):
    now = _aware(now or datetime.now(timezone.utc))
    if not isinstance(value, dict) or value.get("eligible") is not True:
        return None
    material = {key: item for key, item in value.items() if key not in {
        "success", "status", "eligible", "eligibility_id", "eligibility_sha256",
        "execution_id", "command_authority", "hardware_control", "authority_scope"}}
    digest = _digest(material)
    if (value.get("contract_version") != CONTRACT_VERSION
            or value.get("authority_source") != STANDING_AUTHORITY
            or value.get("eligibility_sha256") != digest
            or value.get("eligibility_id") != "ROOTLINE-ELIGIBILITY-" + digest[:24].upper()
            or value.get("execution_id") != "ROOTLINE-EXECUTION-" + digest[:24].upper()
            or value.get("zone_id") not in ZONE
            or value.get("channel") != ZONE[value["zone_id"]]["channel"]
            or value.get("command_mapping") != ZONE[value["zone_id"]]
            or value.get("single_use") is not True or value.get("simultaneous_bc") is not False
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
    keys = ("plan_generation", "plan_evidence_digest", "zone_id", "channel",
            "maximum_duration_seconds", "weekly_debt", "command_mapping",
            "controller_safety_generation")
    return all(original.get(key) == fresh.get(key) for key in keys)


def _controller(value, zone, now):
    if (not isinstance(value, dict) or value.get("device_id") != DEVICE_ID
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
    selected = next((row for row in rows if row.get("channel") == ZONE[zone]["channel"]), None)
    relevant = [row for row in rows if row.get("channel") in (1, 2)]
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
