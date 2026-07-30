"""Read-only ROOTLINE specialist result for future Oom Sakkie composition.

This module has no route, registry, persistence, scheduler, transport, or device
integration.  It projects the canonical Water & Energy Plan into one stable
family-manager result while keeping every physical outcome explicitly unknown.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from zoneinfo import ZoneInfo

from modules.telemetry.rootline_water_energy_plan import (
    UNAVAILABLE,
    build_water_energy_plan,
    read_current_water_energy_evidence,
)


ZA_TZ = ZoneInfo("Africa/Johannesburg")
CONTRACT_VERSION = "rootline_specialist_result_v1"
FORECAST_RAIN_MAX_DELAY_MINUTES = 120
RESULT_AUTHORITY = {
    "command_authority": False,
    "hardware_control": False,
    "writes_performed": False,
    "schedule_mutation": False,
    "workflow_activation": False,
    "telegram_send": False,
}

RECOMMENDATION_IDS = (
    "borehole",
    "B12345",
    "C12345",
    "fertilizer_injection",
    "fertilizer_mixing",
    "solar_transfer_dependency",
)


def build_rootline_specialist_result(
    evidence, operating_date=None, now=None, evidence_origin="caller_supplied"
):
    """Build one deterministic specialist result from canonical-shaped evidence."""
    generated_at = _as_za(now or datetime.now(timezone.utc))
    selected_date = str(operating_date or generated_at.date().isoformat())[:10]
    evidence = deepcopy(evidence if isinstance(evidence, dict) else {})
    plan = build_water_energy_plan(evidence, selected_date, now=generated_at)
    recommendations = _recommendations(plan, evidence, generated_at)
    reassessment = _reassessment(plan, evidence, generated_at, recommendations)
    owner_questions = _owner_questions(plan, evidence, recommendations)
    overall = _overall_status(recommendations)
    cutoff = _evidence_cutoff(plan, generated_at)
    identity_material = {
        "contract": CONTRACT_VERSION,
        "operating_date": selected_date,
        "evidence_generation": plan["evidence_generation"],
        "recommendations": recommendations,
    }
    generation = sha256(
        json.dumps(identity_material, sort_keys=True, default=str).encode()
    ).hexdigest().upper()[:16]
    result_id = f"ROOTLINE-RESULT-{selected_date.replace('-', '')}-{generation}"

    result = {
        "success": True,
        "contract_version": CONTRACT_VERSION,
        "result_id": result_id,
        "generation": generation,
        "operating_date": selected_date,
        "operating_timezone": "Africa/Johannesburg",
        "generated_at": generated_at.isoformat(),
        "evidence_cutoff": cutoff,
        "overall_status": overall,
        "evidence": _evidence_summary(
            plan, evidence, generated_at, evidence_origin
        ),
        "current_power": deepcopy(plan["current_power"]),
        "current_local_weather": _current_weather(evidence, generated_at),
        "forecast": _forecast(plan, evidence, generated_at),
        "battery_policy": deepcopy(plan["battery_reserve"]),
        "water_observations": deepcopy(plan["tank_evidence"]),
        "recommendations": recommendations,
        "next_reassessment": reassessment,
        "owner_questions": owner_questions,
        "outcome_separation": {
            "plan_or_recommendation": "available",
            "command_accepted": UNAVAILABLE,
            "electrical_load_observed": UNAVAILABLE,
            "physical_device_movement": UNAVAILABLE,
            "water_flow": UNAVAILABLE,
            "delivered_volume": UNAVAILABLE,
        },
        "authority": deepcopy(RESULT_AUTHORITY),
    }
    result["owner_brief"] = _owner_brief(result)
    return result


def build_current_rootline_specialist_result(
    operating_date=None, database_url=None, now=None
):
    """Read canonical evidence through Phase 1 and return an in-memory result.

    No advisory generation or observation is appended.
    """
    generated_at = _as_za(now or datetime.now(timezone.utc))
    evidence, selected_date, generated_at = read_current_water_energy_evidence(
        operating_date=operating_date,
        database_url=database_url,
        now=generated_at,
    )
    return build_rootline_specialist_result(
        evidence,
        selected_date,
        now=generated_at,
        evidence_origin="canonical_read_models",
    )


def project_water_energy_plan(plan, now=None):
    """Project an already composed canonical plan without any external reads."""
    generated_at = _as_za(now or datetime.now(timezone.utc))
    plan = deepcopy(plan if isinstance(plan, dict) else {})
    selected_date = str(plan.get("operating_date") or generated_at.date())[:10]
    evidence = {
        "power": _packet_from_plan_power(plan.get("current_power")),
        "weather": _packet_from_plan_weather(plan.get("current_local_weather")),
        "forecast": _packet_from_plan_forecast(plan.get("forecast")),
        "tanks": _packet_from_plan_tanks(plan.get("tank_evidence")),
        "water_demand": deepcopy(plan.get("water_demand") or {}),
        "irrigation": {"zones": _zones_from_tasks(plan.get("candidate_tasks"))},
        "history": deepcopy(plan.get("historical_context") or {}),
    }
    # Current Phase 1 plans do not expose all raw weather fields. Preserve their
    # decisions and provenance by rebuilding only when raw evidence is present.
    if plan.get("success") is not True:
        return _unavailable_result(selected_date, generated_at, plan.get("status"))
    if not evidence["weather"].get("observed_at"):
        result = _project_existing_plan(plan, generated_at)
        return result
    return build_rootline_specialist_result(evidence, selected_date, generated_at)


def _project_existing_plan(plan, now):
    recommendations = _recommendations_from_tasks(plan.get("candidate_tasks", []))
    result_id = (
        f"ROOTLINE-RESULT-{str(plan.get('operating_date')).replace('-', '')}-"
        f"{str(plan.get('evidence_generation') or 'UNAVAILABLE')}"
    )
    result = {
        "success": True,
        "contract_version": CONTRACT_VERSION,
        "result_id": result_id,
        "generation": plan.get("evidence_generation") or UNAVAILABLE,
        "operating_date": plan.get("operating_date"),
        "operating_timezone": "Africa/Johannesburg",
        "generated_at": now.isoformat(),
        "evidence_cutoff": plan.get("evidence_observed_at") or UNAVAILABLE,
        "overall_status": _overall_status(recommendations),
        "evidence": {
            "provenance": "canonical_rootline_water_energy_plan",
            "freshness": {
                "power": plan.get("current_power", {}).get("status", UNAVAILABLE),
                "current_local_weather": UNAVAILABLE,
                "forecast": plan.get("forecast", {}).get("status", UNAVAILABLE),
                "water_observations": plan.get("tank_evidence", {}).get(
                    "status", UNAVAILABLE
                ),
            },
        },
        "current_power": deepcopy(plan.get("current_power") or {}),
        "current_local_weather": {
            "status": UNAVAILABLE,
            "reason": "Persisted Phase 1 plan does not contain current weather values.",
        },
        "forecast": deepcopy(plan.get("forecast") or {}),
        "battery_policy": deepcopy(plan.get("battery_reserve") or {}),
        "water_observations": deepcopy(plan.get("tank_evidence") or {}),
        "recommendations": recommendations,
        "next_reassessment": {
            "trigger": "new_canonical_evidence_or_next_read",
            "at": now.isoformat(),
            "reason": "Recompose from current read models before owner use.",
        },
        "owner_questions": _questions_from_plan(plan),
        "outcome_separation": {
            "plan_or_recommendation": "available",
            "command_accepted": UNAVAILABLE,
            "electrical_load_observed": UNAVAILABLE,
            "physical_device_movement": UNAVAILABLE,
            "water_flow": UNAVAILABLE,
            "delivered_volume": UNAVAILABLE,
        },
        "authority": deepcopy(RESULT_AUTHORITY),
    }
    result["owner_brief"] = _owner_brief(result)
    return result


def _recommendations(plan, evidence, now):
    tasks = {
        item.get("task_id"): item
        for item in plan.get("candidate_tasks", [])
        if isinstance(item, dict)
    }
    rain = plan.get("rain_capture", {})
    forecast_only_delay = (
        rain.get("forecast_replenishment_effect") == "meaningful_rain_candidate"
        and rain.get("current_rain_status") != "Hold"
    )
    delay_deadline = _forecast_delay_deadline(evidence.get("forecast"), now)
    delay_active = (
        forecast_only_delay
        and delay_deadline is not None
        and now < delay_deadline
    )
    result = []
    for identity, task_id in (
        ("borehole", "borehole"),
        ("B12345", "irrigation_B12345"),
        ("C12345", "irrigation_C12345"),
        ("fertilizer_injection", "fertilizer_injection_ch1"),
        ("fertilizer_mixing", "fertilizer_mixing_ch2"),
        ("solar_transfer_dependency", "solar_transfer_pump"),
    ):
        task = deepcopy(tasks.get(task_id) or {})
        status = _public_status(task.get("recommendation"))
        reason = task.get("reason") or "Canonical task evidence is unavailable."
        if identity == "borehole" and forecast_only_delay:
            if delay_active:
                status = "Hold"
                reason = (
                    "Forecast rain may justify only a bounded delay; it is not "
                    "observed rain or captured tank water."
                )
            else:
                status, reason = _borehole_after_forecast_delay(plan, evidence)
        if identity in {"B12345", "C12345"}:
            zone = next(
                (
                    item for item in evidence.get("irrigation", {}).get("zones", [])
                    if isinstance(item, dict) and item.get("zone_id") == identity
                ),
                {},
            )
            weather = (
                evidence.get("weather")
                if isinstance(evidence.get("weather"), dict) else {}
            )
            rain_rate = _number(weather.get("rain_rate_mm_h"))
            if (
                _public_status(zone.get("recommendation")) == "Recommend"
                and _freshness(weather, now) == "fresh"
                and rain_rate is not None
                and rain_rate <= 0.2
            ):
                status = "Recommend"
                reason = (
                    "Daily Advisor supports this zone and fresh current local "
                    "weather does not show live rain. Forecast alone cannot "
                    "indefinitely suppress the recommendation."
                )
        if identity == "solar_transfer_dependency":
            if status == "Recommend":
                status = "Hold"
            reason = (
                f"{reason} The independent solar transfer pump runs only when "
                "solar permits and is not controllable by ROOTLINE; monitor it "
                "as a dependency, do not treat this as an instruction to run it."
            )
        result.append(
            {
                "subject": identity,
                "status": status,
                "reason": reason,
                "preferred_window": task.get("preferred_window", UNAVAILABLE),
                "supported_by": _support_for(identity, plan),
                "needs": _genuine_needs(identity, status, plan, evidence),
                "command_authority": False,
                "hardware_control": False,
            }
        )
    return result


def _borehole_after_forecast_delay(plan, evidence):
    tanks = plan.get("tank_evidence", {})
    demand = evidence.get("water_demand") if isinstance(
        evidence.get("water_demand"), dict
    ) else {}
    if tanks.get("status") in {"Unavailable", "stale"}:
        return "Needs Data", "A current storage observation is needed."
    if tanks.get("storage_state") == "FULL" and demand.get("status") != "urgent":
        return "Do Not Run", "Storage was explicitly observed FULL."
    if demand.get("status") == "urgent":
        return "Recommend", "Water continuity outranks grid avoidance."
    if demand.get("status") == "needed":
        return "Recommend", (
            "The forecast-only delay expired without observed rain or captured-water "
            "evidence; reassess and recover the supported water work."
        )
    return "Hold", "Water need is not yet proven after the forecast-only delay."


def _reassessment(plan, evidence, now, recommendations):
    forecast_deadline = _forecast_delay_deadline(evidence.get("forecast"), now)
    held_for_forecast = any(
        item["subject"] == "borehole"
        and item["status"] == "Hold"
        and "bounded delay" in item["reason"]
        for item in recommendations
    )
    if held_for_forecast and forecast_deadline:
        return {
            "trigger": "bounded_forecast_rain_check",
            "at": forecast_deadline.isoformat(),
            "maximum_delay_minutes": FORECAST_RAIN_MAX_DELAY_MINUTES,
            "required_evidence": [
                "fresh_current_local_weather",
                "observed_rain_or_explicit_no_rain",
                "new_tank_observation_if_available",
            ],
            "recovery_if_rain_does_not_occur": (
                "Remove forecast-only suppression and reconsider supported water work."
            ),
        }
    freshness = [
        ("power", plan.get("current_power", {}).get("status")),
        ("weather", _freshness(evidence.get("weather"), now)),
        ("forecast", plan.get("forecast", {}).get("status")),
        ("tanks", plan.get("tank_evidence", {}).get("status")),
    ]
    stale = [name for name, state in freshness if state not in {"fresh", "aging"}]
    return {
        "trigger": "new_canonical_evidence" if not stale else "refresh_missing_or_stale_evidence",
        "at": (now + timedelta(minutes=30)).isoformat(),
        "also_on": ["material_power_change", "local_weather_change", "owner_water_observation"],
        "reason": (
            f"Refresh {', '.join(stale)}." if stale
            else "Keep advice current as conditions change."
        ),
    }


def _owner_questions(plan, evidence, recommendations):
    questions = []
    tanks = plan.get("tank_evidence", {})
    water_work = any(
        item["subject"] in {"borehole", "B12345", "C12345"}
        and item["status"] in {"Needs Data", "Hold"}
        for item in recommendations
    )
    if water_work and tanks.get("status") in {UNAVAILABLE, "stale"}:
        questions.append(
            {
                "fact": "current_tank_observation",
                "question": (
                    "If someone is near the tanks, are storage and reservoir tanks "
                    "LOW, OK or FULL (or what fraction is available), and when was "
                    "that observed?"
                ),
                "why_needed": "It changes only recommendations that depend on water availability.",
                "required_now": False,
            }
        )
    demand = evidence.get("water_demand")
    if not isinstance(demand, dict) or demand.get("status") not in {
        "normal", "needed", "urgent"
    }:
        questions.append(
            {
                "fact": "water_continuity_need",
                "question": "Is there a genuine water-continuity need today: normal, needed or urgent?",
                "why_needed": "Urgent continuity may justify grid use.",
                "required_now": False,
            }
        )
    return questions[:1]


def _evidence_summary(plan, evidence, now, evidence_origin):
    canonical = evidence_origin == "canonical_read_models"
    prefix = "canonical_" if canonical else "caller_supplied_canonical_shaped_"
    return {
        "provenance": {
            "origin": evidence_origin,
            "power": prefix + "current_power_read_model",
            "current_local_weather": prefix + "local_weather_read_model",
            "forecast": prefix + "forecast_read_model",
            "water_observations": prefix + "owner_observation_if_supplied",
            "irrigation": prefix + "rootline_daily_advisor",
            "policy_and_plan": prefix + "rootline_water_energy_plan_v1",
        },
        "freshness": {
            "power": plan["current_power"]["status"],
            "current_local_weather": _freshness(evidence.get("weather"), now),
            "forecast": plan["forecast"]["status"],
            "water_observations": plan["tank_evidence"]["status"],
        },
        "limitations": [
            "Forecast rain is not observed rain or captured tank water.",
            "No litres, flow, soil moisture, device movement or delivered volume are inferred.",
        ],
    }


def _current_weather(evidence, now):
    packet = evidence.get("weather") if isinstance(evidence.get("weather"), dict) else {}
    return {
        "status": _freshness(packet, now),
        "observed_at": packet.get("observed_at"),
        "age_minutes": _age_minutes(packet, now),
        "rain_rate_mm_h": packet.get("rain_rate_mm_h"),
        "rain_today_mm": packet.get("rain_today_mm"),
        "temperature_c": packet.get("temperature_c"),
        "wind_speed_kmh": packet.get("wind_speed_kmh"),
        "is_forecast": False,
    }


def _forecast(plan, evidence, now):
    packet = evidence.get("forecast") if isinstance(evidence.get("forecast"), dict) else {}
    return {
        "status": plan["forecast"]["status"],
        "observed_at": packet.get("observed_at"),
        "age_minutes": _age_minutes(packet, now),
        "confidence": plan["forecast"]["confidence"],
        "uncertainty": (
            "Forecast rain is not observed rain, may not materialize, and does "
            "not prove captured water."
        ),
        "solar_profile": plan["forecast"]["solar_profile"],
        "days": deepcopy(packet.get("days", [])),
        "is_current_local_weather": False,
    }


def _owner_brief(result):
    recommended_items = [
        item for item in result["recommendations"]
        if item["status"] == "Recommend"
    ]
    recommended = [item["subject"] for item in recommended_items]
    reasons = [
        f"{item['subject']}: {item['reason']}" for item in recommended_items
    ]
    constraints = [
        f"{item['subject']} ({item['status']}: {item['reason']})"
        for item in result["recommendations"]
        if item["status"] != "Recommend"
    ]
    question = (
        result["owner_questions"][0]["question"]
        if result["owner_questions"] else "No owner fact is required now."
    )
    return {
        "recommend_now": (
            ", ".join(recommended) if recommended else
            "No physical task is currently supported as a recommendation."
        ),
        "why": (reasons or constraints)[:3],
        "what_changed": (
            "Generated from the current evidence generation "
            f"{result['generation']}; compare result_id on the next read."
        ),
        "reassess": (
            f"{result['next_reassessment']['trigger']} at "
            f"{result['next_reassessment']['at']}"
        ),
        "family_fact_needed": question,
        "safety": "Advice only. ROOTLINE cannot send commands or control hardware.",
    }


def _support_for(identity, plan):
    mapping = {
        "borehole": ["current_power", "current_local_weather", "forecast", "water_observations", "water_policy"],
        "B12345": ["rootline_daily_advisor", "current_local_weather", "battery_policy"],
        "C12345": ["rootline_daily_advisor", "current_local_weather", "battery_policy"],
        "fertilizer_injection": ["irrigation_interlocks", "fertilizer_policy"],
        "fertilizer_mixing": ["fertilizer_policy", "battery_policy"],
        "solar_transfer_dependency": ["water_topology", "solar_availability"],
    }
    return mapping[identity]


def _genuine_needs(identity, status, plan, evidence):
    if status != "Needs Data":
        return []
    if identity in {"borehole", "solar_transfer_dependency"}:
        return ["current_owner_water_observation"] if (
            plan.get("tank_evidence", {}).get("status") in {UNAVAILABLE, "stale"}
        ) else []
    if identity in {"B12345", "C12345"}:
        return ["supported_daily_advisor_zone_evidence"]
    if identity.startswith("fertilizer"):
        return ["protected_relay_identity_and_physical_interlocks"]
    return []


def _forecast_delay_deadline(packet, now):
    if not isinstance(packet, dict):
        return None
    observed = _parse_time(packet.get("observed_at"))
    if observed is None:
        return None
    return observed.astimezone(ZA_TZ) + timedelta(
        minutes=FORECAST_RAIN_MAX_DELAY_MINUTES
    )


def _overall_status(recommendations):
    statuses = {item["status"] for item in recommendations}
    if "Recommend" in statuses:
        return "Recommend"
    if "Hold" in statuses:
        return "Hold"
    if "Needs Data" in statuses:
        return "Needs Data"
    return "Do Not Run"


def _public_status(value):
    normalized = str(value or "").strip().lower().replace("_", " ")
    return {
        "recommend": "Recommend",
        "hold": "Hold",
        "needs data": "Needs Data",
        "do not run": "Do Not Run",
    }.get(normalized, "Needs Data")


def _recommendations_from_tasks(tasks):
    indexed = {
        item.get("task_id"): item for item in tasks if isinstance(item, dict)
    }
    result = []
    for identity, task_id in (
        ("borehole", "borehole"),
        ("B12345", "irrigation_B12345"),
        ("C12345", "irrigation_C12345"),
        ("fertilizer_injection", "fertilizer_injection_ch1"),
        ("fertilizer_mixing", "fertilizer_mixing_ch2"),
        ("solar_transfer_dependency", "solar_transfer_pump"),
    ):
        task = indexed.get(task_id, {})
        reason = task.get("reason") or "Canonical task evidence is unavailable."
        if identity == "solar_transfer_dependency":
            reason += " The solar transfer pump is not controllable by ROOTLINE."
        result.append({
            "subject": identity,
            "status": _public_status(task.get("recommendation")),
            "reason": reason,
            "preferred_window": task.get("preferred_window", UNAVAILABLE),
            "supported_by": [],
            "needs": [],
            "command_authority": False,
            "hardware_control": False,
        })
    return result


def _questions_from_plan(plan):
    if plan.get("tank_evidence", {}).get("status") in {UNAVAILABLE, "stale"}:
        return [{
            "fact": "current_tank_observation",
            "question": "If convenient, are the tanks LOW, OK or FULL, and when was that observed?",
            "why_needed": "It changes only water-availability recommendations.",
            "required_now": False,
        }]
    return []


def _zones_from_tasks(tasks):
    zones = []
    for item in tasks or []:
        task_id = str(item.get("task_id") or "")
        if task_id.startswith("irrigation_"):
            zones.append({
                "zone_id": task_id.removeprefix("irrigation_"),
                "recommendation": item.get("recommendation"),
            })
    return zones


def _packet_from_plan_power(value):
    value = value if isinstance(value, dict) else {}
    return {
        "observed_at": value.get("observed_at"),
        "stale_after_minutes": 15,
        "battery_soc_pct": value.get("battery_soc_pct"),
        "solar_power_w": value.get("solar_power_w"),
        "load_power_w": value.get("load_power_w"),
        "grid_power_w": value.get("grid_power_w"),
    }


def _packet_from_plan_weather(value):
    return deepcopy(value) if isinstance(value, dict) else {}


def _packet_from_plan_forecast(value):
    value = value if isinstance(value, dict) else {}
    return {
        "observed_at": value.get("observed_at"),
        "stale_after_minutes": 360,
        "days": deepcopy(value.get("days", [])),
    }


def _packet_from_plan_tanks(value):
    value = value if isinstance(value, dict) else {}
    return {
        "storage_reported_count": value.get("storage_reported_count"),
        "reservoir_reported_count": value.get("reservoir_reported_count"),
        "storage_state": value.get("storage_state"),
        "reservoir_state": value.get("reservoir_state"),
        "observed_at": value.get("observed_at"),
        "reporter": value.get("reporter"),
        "source": value.get("source"),
    }


def _evidence_cutoff(plan, now):
    return plan.get("evidence_observed_at") or now.isoformat()


def _freshness(packet, now):
    if not isinstance(packet, dict) or not packet.get("observed_at"):
        return UNAVAILABLE
    if packet.get("conflicting") is True:
        return "conflicting"
    age = _age_minutes(packet, now)
    try:
        threshold = float(packet.get("stale_after_minutes"))
    except (TypeError, ValueError):
        return UNAVAILABLE
    return "fresh" if age is not None and age <= threshold else "stale"


def _age_minutes(packet, now):
    observed = _parse_time(packet.get("observed_at")) if isinstance(packet, dict) else None
    if observed is None:
        return None
    age = (now.astimezone(timezone.utc) - observed.astimezone(timezone.utc)).total_seconds() / 60
    return round(age, 1) if age >= 0 else None


def _parse_time(value):
    try:
        result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return result if result.tzinfo is not None else None
    except (TypeError, ValueError):
        return None


def _number(value):
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _as_za(value):
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(ZA_TZ)


def _unavailable_result(selected_date, now, reason):
    result = {
        "success": False,
        "contract_version": CONTRACT_VERSION,
        "result_id": f"ROOTLINE-RESULT-{selected_date.replace('-', '')}-UNAVAILABLE",
        "generation": UNAVAILABLE,
        "operating_date": selected_date,
        "operating_timezone": "Africa/Johannesburg",
        "generated_at": now.isoformat(),
        "evidence_cutoff": UNAVAILABLE,
        "overall_status": "Needs Data",
        "reason": reason or "canonical_evidence_unavailable",
        "evidence": {
            "provenance": UNAVAILABLE,
            "freshness": {
                "power": UNAVAILABLE,
                "current_local_weather": UNAVAILABLE,
                "forecast": UNAVAILABLE,
                "water_observations": UNAVAILABLE,
            },
        },
        "current_power": {"status": UNAVAILABLE},
        "current_local_weather": {"status": UNAVAILABLE},
        "forecast": {"status": UNAVAILABLE},
        "battery_policy": {"status": UNAVAILABLE},
        "water_observations": {"status": UNAVAILABLE},
        "recommendations": [],
        "next_reassessment": {
            "trigger": "canonical_evidence_available",
            "at": now.isoformat(),
            "reason": "Retry a read-only composition when evidence is available.",
        },
        "owner_questions": [],
        "outcome_separation": {
            "plan_or_recommendation": UNAVAILABLE,
            "command_accepted": UNAVAILABLE,
            "electrical_load_observed": UNAVAILABLE,
            "physical_device_movement": UNAVAILABLE,
            "water_flow": UNAVAILABLE,
            "delivered_volume": UNAVAILABLE,
        },
        "authority": deepcopy(RESULT_AUTHORITY),
    }
    result["owner_brief"] = _owner_brief(result)
    return result
