"""Pure adaptive B/C irrigation decisions and outcome learning.

This module is a decision component of the canonical ROOTLINE plan builder. It
does not persist, notify, schedule, create commands, or call provider hardware.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json
from zoneinfo import ZoneInfo


ZA_TZ = ZoneInfo("Africa/Johannesburg")
ZONES = {"B12345": {"channel": 1}, "C12345": {"channel": 2}}
DECISIONS = {
    "Run now", "Run later", "Hold", "Needs Data", "Completed",
    "Reassess after segment one",
}
AUTHORITY = {
    "command_authority": False,
    "hardware_control": False,
    "schedule_authority": False,
    "workflow_authority": False,
    "automatic_on_retry": False,
}


def build_adaptive_irrigation_decisions(evidence, *, now=None):
    """Rank independent B/C needs using only supplied, provenance-ready facts."""
    evidence = deepcopy(evidence if isinstance(evidence, dict) else {})
    now = _za(now or datetime.now(timezone.utc))
    policy = _policy(evidence.get("policy"))
    weather = _dict(evidence.get("local_weather"))
    forecast = _dict(evidence.get("forecast"))
    water = _dict(evidence.get("water"))
    power = _dict(evidence.get("power"))
    zones = {str(item.get("zone_id")): _dict(item) for item in evidence.get("zones", [])
             if isinstance(item, dict) and str(item.get("zone_id")) in ZONES}
    results = []
    for zone_id in ZONES:
        results.append(_zone_decision(zone_id, zones.get(zone_id, {}), policy,
                                      weather, forecast, water, power, now))
    _rank(results)
    # Deliberately exclude the calculation clock. An unchanged material result
    # must retain its identity so Oom Sakkie can suppress duplicate notices.
    digest = _digest({"decisions": results})
    return {
        "version": "rootline_adaptive_irrigation_v1",
        "evidence_cutoff": now.isoformat(),
        "decision_generation": digest[:16].upper(),
        "decision_sha256": digest,
        "zones": results,
        "same_day_multiple_zones_allowed": True,
        "simultaneous_zones_allowed": False,
        "max_execution_minutes": 60,
        "segment_two_requires_fresh_decision": True,
        "historical_two_hour_run_is_policy": False,
        "borehole_authority": False,
        "fertilizer_authority": False,
        **AUTHORITY,
    }


def build_run_outcome_evidence(outcome, *, now=None):
    """Normalize one immutable learning input without claiming delivered water."""
    item = deepcopy(outcome if isinstance(outcome, dict) else {})
    zone_id = str(item.get("zone_id") or "")
    if zone_id not in ZONES:
        raise ValueError("unsupported_irrigation_zone")
    planned = _number(item.get("planned_runtime_minutes"))
    actual = _number(item.get("verified_runtime_minutes"))
    if planned is None or planned <= 0 or planned > 60:
        raise ValueError("planned_runtime_must_be_1_to_60_minutes")
    if actual is None or actual < 0 or actual > 60:
        raise ValueError("verified_runtime_must_be_0_to_60_minutes")
    packet = {
        "zone_id": zone_id,
        "planned_start": item.get("planned_start"),
        "actual_start": item.get("actual_start"),
        "actual_stop": item.get("actual_stop"),
        "planned_runtime_minutes": planned,
        "verified_runtime_minutes": actual,
        "shutdown_verified": item.get("shutdown_verified") is True,
        "physical_flow_confirmation": item.get("physical_flow_confirmation", "Unavailable"),
        "weather_after": _dict(item.get("weather_after")),
        "visible_response_after": item.get("visible_response_after", "Unavailable"),
        "owner_correction": item.get("owner_correction", "Unavailable"),
        "another_segment_needed": item.get("another_segment_needed", "Unavailable"),
        "delivered_volume": "Unavailable",
        "flow_rate": "Unavailable",
        "policy_changed": False,
        "recorded_at": _za(now or datetime.now(timezone.utc)).isoformat(),
        **AUTHORITY,
    }
    packet["outcome_sha256"] = _digest(packet)
    return packet


def learning_hints(outcomes):
    """Return bounded recommendation hints; never silently mutate policy."""
    rows = [row for row in outcomes if isinstance(row, dict)]
    hints = []
    if any(_number(row.get("weather_after", {}).get("rain_mm")) not in (None, 0)
           for row in rows):
        hints.append("reassess_post_irrigation_rain_before_next_segment")
    if any(row.get("another_segment_needed") is True for row in rows):
        hints.append("consider_another_bounded_segment_after_fresh_decision")
    if any(str(row.get("owner_correction")) not in {"", "Unavailable", "None"}
           for row in rows):
        hints.append("apply_owner_correction_to_next_decision_evidence")
    if any(row.get("shutdown_verified") is not True for row in rows):
        hints.append("hold_zone_until_shutdown_evidence_is_resolved")
    return {"hints": hints, "policy_changed": False,
            "delivered_volume_inferred": False, **AUTHORITY}


def notification_projection(result, previous_decision_sha256=None):
    """Suppress unchanged daily Hold output and emit only material states."""
    current = str(_dict(result).get("decision_sha256") or "")
    zones = _dict(result).get("zones") if isinstance(_dict(result).get("zones"), list) else []
    material = any(_dict(row).get("decision") in {
        "Run now", "Run later", "Needs Data", "Reassess after segment one",
    } for row in zones)
    changed = bool(current) and current != str(previous_decision_sha256 or "")
    return {
        "emit_daily_recommendation": material and changed,
        "suppress_unchanged_hold": not changed or not material,
        "start_notification": "on_authoritative_execution_start_only",
        "completion_notification": "on_verified_shutdown_only",
        "single_alert_conditions": [
            "failed_shutdown", "unexpected_rain", "water_shortage",
            "material_power_conflict",
        ],
        **AUTHORITY,
    }


def _zone_decision(zone_id, zone, policy, weather, forecast, water, power, now):
    correction = _dict(zone.get("owner_correction"))
    need = _current_need(zone, correction, now)
    completions = [row for row in zone.get("completion_events", []) if isinstance(row, dict)]
    corrected_completion = correction.get("last_completed_at")
    if corrected_completion:
        completions.append({"completed_at": corrected_completion,
                            "state": "Completed", "shutdown_verified": True,
                            "verified_runtime_minutes": correction.get("verified_runtime_minutes"),
                            "outcome_id": correction.get("outcome_id"),
                            "source": correction.get("source")})
    latest = _latest_completion(completions)
    completed_today = latest is not None and latest.astimezone(ZA_TZ).date() == now.date()
    segment = _dict(zone.get("latest_segment"))
    if (segment.get("segment_number") == 1 and segment.get("state") == "Completed"
            and segment.get("shutdown_verified") is True
            and segment.get("objective_remaining") is True):
        decision = "Reassess after segment one"
        reason = "Segment one completed and shutdown is verified; a new evidence generation must decide segment two."
        score = _need_score(need, latest, zone, now)
    elif completed_today and correction.get("another_segment_needed") is not True:
        decision, reason, score = "Completed", "A completed irrigation is recorded for this zone today.", 0
    elif need.lower() in {"ok", "wet", "none", "not needed"}:
        decision, reason, score = (
            "Hold",
            "A fresh authoritative observation says this zone does not currently need irrigation; weekly cadence is guidance only.",
            _need_score(need, latest, zone, now),
        )
    else:
        score = _need_score(need, latest, zone, now)
        decision, reason = _classify(score, need, policy, weather, water, power, now)
    confidence, gaps = _confidence(zone, weather, forecast, water, power, now)
    if decision in {"Run now", "Run later"} and not _fresh_adequate_water(water, now):
        decision = "Needs Data"
        reason = "Current water availability is required before this water-dependent execution; other planning remains available."
    if _observed_rain(weather, now):
        decision = "Hold"
        reason = "Fresh local evidence records rain; reassess need after observed rain rather than relying on forecast."
    window = _window(decision, policy, power, now)
    urgent = need.lower() == "urgent"
    return {
        "zone_id": zone_id,
        "channel": ZONES[zone_id]["channel"],
        "decision": decision,
        "need_score": score,
        "confidence": confidence,
        "reason": reason,
        "preferred_window": window,
        "max_segment_minutes": 60,
        "proposed_segment_minutes": 60 if decision in {"Run now", "Run later"} else None,
        "fresh_decision_before_second_segment": True,
        "shutdown_verification_required": True,
        "simultaneous_with_other_zone": False,
        "grid_exposure_may_be_justified": urgent,
        "evidence_gaps": gaps,
        "forecast_status": _freshness(forecast, now, 360),
        "local_weather_status": _freshness(weather, now, 30),
        "last_completed_at": latest.isoformat() if latest else None,
        "delivered_volume": "Unavailable",
        "flow_rate": "Unavailable",
        "rank": None,
        **AUTHORITY,
    }


def _classify(score, need, policy, weather, water, power, now):
    urgent = need.lower() == "urgent"
    soc = _number(power.get("battery_soc_pct"))
    reserve = policy["governing_reserve_soc_pct"]
    power_fresh = _freshness(power, now, 15) == "fresh"
    if urgent:
        return "Run now", "Urgent water continuity outweighs strict grid avoidance; retain the bounded native fail-stop."
    if score < 20:
        return "Hold", "Available evidence does not establish enough current deficit for irrigation."
    if not power_fresh:
        return "Run later", "Water need is supported but fresh power evidence is required at execution time."
    season = policy["season"]
    surplus = (_number(power.get("solar_power_w")) or 0) > (_number(power.get("load_power_w")) or 0)
    if season == "summer" and not (now.hour >= 18 or now.hour < 6):
        return "Run later", "Summer evaporation favours an evening or night window."
    if season == "winter" and 9 <= now.hour < 16 and surplus and soc is not None and soc >= reserve:
        return "Run now", "Winter daylight, surplus solar and reserve margin support a bounded daytime segment."
    if soc is not None and soc >= reserve:
        return "Run now", "Current need and battery margin support one bounded segment."
    return "Run later", "Need is supported, but wait for reserve recovery or an explicitly justified water-continuity grid decision."


def _need_score(need, latest, zone, now):
    score = {"urgent": 45, "dry": 35, "needed": 28, "visible_need": 28,
             "ok": -15, "wet": -35, "none": -25}.get(need.lower(), 8)
    if latest is not None:
        days = max(0, (now - latest.astimezone(ZA_TZ)).total_seconds() / 86400)
        score += min(35, int(days * 12))
    completed = _number(zone.get("completed_days_last_7_days"))
    if completed is not None:
        score += max(0, 4 - int(completed)) * 7
    return max(0, min(100, score))


def _current_need(zone, correction, now):
    if correction.get("visible_need") is not None:
        value = correction.get("visible_need")
        observed = correction.get("observed_at")
        source = correction.get("source")
    else:
        value = zone.get("visible_need")
        observed = zone.get("visible_need_observed_at")
        source = zone.get("visible_need_source")
    timestamp = _timestamp(observed)
    if (value is None or timestamp is None or not str(source or "").strip()
            or (now - timestamp.astimezone(ZA_TZ)).total_seconds() > 24 * 3600):
        return "Unknown"
    return str(value)


def _confidence(zone, weather, forecast, water, power, now):
    gaps = []
    if _current_need(zone, _dict(zone.get("owner_correction")), now) == "Unknown":
        gaps.append("current_visible_need_unavailable")
    if (_latest_completion([row for row in zone.get("completion_events", [])
                            if isinstance(row, dict)]) is None
            and _number(zone.get("completed_days_last_7_days")) is None):
        gaps.append("verified_completion_history_unavailable")
    for field, value in (("soil_moisture", zone.get("soil_moisture")),
                         ("flow_measurement", zone.get("flow_measurement"))):
        if value in (None, "Unavailable", "Unknown"):
            gaps.append(field + "_unavailable")
    if not water:
        gaps.append("water_observation_unavailable")
    elif _freshness(water, now, 24 * 60) != "fresh":
        gaps.append("water_observation_stale")
    if not weather:
        gaps.append("local_weather_unavailable")
    elif _freshness(weather, now, 30) != "fresh":
        gaps.append("local_weather_stale")
    if not forecast:
        gaps.append("forecast_unavailable")
    elif _freshness(forecast, now, 360) != "fresh":
        gaps.append("forecast_stale")
    if not power:
        gaps.append("power_unavailable")
    elif _freshness(power, now, 15) != "fresh":
        gaps.append("power_stale")
    return ("high" if not gaps else "medium" if len(gaps) <= 2 else "low"), gaps


def _rank(results):
    candidates = [row for row in results if row["decision"] in {
        "Run now", "Run later", "Needs Data", "Reassess after segment one",
    }]
    candidates.sort(key=lambda row: (-row["need_score"], row["zone_id"]))
    for index, row in enumerate(candidates, 1):
        row["rank"] = index


def _window(decision, policy, power, now):
    if decision == "Run now":
        return "now_after_fresh_execution_revalidation"
    if decision != "Run later":
        return "on_material_evidence_change"
    if policy["season"] == "summer":
        return "next_evening_or_night_window"
    if policy["season"] == "winter":
        return "next_supported_daylight_power_window"
    return "next_supported_power_and_water_window"


def _policy(value):
    value = _dict(value)
    return {
        "season": str(value.get("season") or "shoulder").lower(),
        "target_days_per_week": int(value.get("target_days_per_week") or 4),
        "governing_reserve_soc_pct": _number(value.get("governing_reserve_soc_pct")) or 63,
        "absolute_floor_soc_pct": _number(value.get("absolute_floor_soc_pct")) or 40,
    }


def _fresh_adequate_water(water, now):
    return (_freshness(water, now, 24 * 60) == "fresh"
            and water.get("reservoir_available") is True)


def _observed_rain(weather, now):
    return (_freshness(weather, now, 30) == "fresh"
            and ((_number(weather.get("rain_rate_mm_h")) or 0) > 0
                 or (_number(weather.get("rain_today_mm")) or 0) >= 2))


def _freshness(value, now, minutes):
    observed = _timestamp(_dict(value).get("observed_at"))
    if observed is None:
        return "Unavailable"
    age = (now - observed.astimezone(ZA_TZ)).total_seconds() / 60
    return "fresh" if 0 <= age <= minutes else "stale"


def _latest_completion(rows):
    verified = []
    for row in rows:
        runtime = _number(row.get("verified_runtime_minutes"))
        if (row.get("state") == "Completed" and row.get("shutdown_verified") is True
                and 0 < (runtime or 0) <= 120
                and str(row.get("outcome_id") or "").strip()
                and str(row.get("source") or "").strip()):
            verified.append(row)
    values = [_timestamp(row.get("completed_at")) for row in verified]
    values = [value for value in values if value is not None]
    return max(values) if values else None


def _timestamp(value):
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _za(value):
    return (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).astimezone(ZA_TZ)


def _number(value):
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _dict(value):
    return value if isinstance(value, dict) else {}


def _digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()
