"""Command-inert ROOTLINE operating knowledge and daily advice.

This module reads the existing owner Daily Brief and the immutable active
Operating Knowledge policy. It has no write, transport, scheduler, retry, n8n,
IFTTT, credential, command, or hardware authority.
"""

from copy import deepcopy
from datetime import datetime, timedelta
from hashlib import sha256
import json
import math
import re
from zoneinfo import ZoneInfo

from modules.telemetry.rootline_daily_brief import get_rootline_daily_brief
from modules.telemetry.rootline_operating_policy import (
    list_policy_review,
    normalize_policy_snapshot,
)
from modules.telemetry.rootline_ewelink_commissioned_baseline import (
    commissioned_controller_baseline,
)


ZA_TZ = ZoneInfo("Africa/Johannesburg")
UNKNOWN = "Unknown"
UNAVAILABLE = "Unavailable"

AUTHORITY = {
    "writes_performed": False,
    "hardware_control_performed": False,
    "command_created": False,
    "plan_generated": False,
    "schedule_mutation_performed": False,
    "workflow_activation_performed": False,
    "calls_ifttt": False,
    "calls_n8n": False,
    "automatic_retry": False,
}

OPERATING_KNOWLEDGE = {
    "register_version": 1,
    "timezone": "Africa/Johannesburg",
    "mode": "manual_advisory_only",
    "zones": {
        "B12345": {
            "zone_id": "B12345",
            "owner_name": "B - Kamp",
            "crop_use": "lucerne",
            "irrigation_type": "drip",
            "water_supply": "gravity_fed_downhill",
            "pump_required": False,
            "priority": "equal",
            "physical_mapping_status": "supervised_commissioned",
        },
        "C12345": {
            "zone_id": "C12345",
            "owner_name": "C - Kamp",
            "crop_use": "vegetables",
            "irrigation_type": "drip",
            "water_supply": "gravity_fed_downhill",
            "pump_required": False,
            "priority": "equal",
            "physical_mapping_status": "supervised_identity_and_shutdown_proven_once",
        },
    },
    "approved_policy": {
        "capacity_conflict": "owner_selection_required",
        "eligibility": "manual_advisory_only",
        "seasonal_boundaries": UNKNOWN,
        "runtime_meaning": "planned_valve_open_minutes",
        "runtime_separation": [
            "planned_minutes",
            "observed_runtime",
            "measured_delivery",
        ],
        "daylight_only": False,
        "allowed_windows": "adaptive_by_rootline_from_current_evidence",
        "minimum_runtime_minutes": UNKNOWN,
        "maximum_runtime_minutes": UNKNOWN,
        "repeat_same_day": "fresh_owner_review_required",
        "simultaneous_zones": False,
        "forecast_rain_thresholds": UNKNOWN,
        "live_rain": "active_versioned_policy_is_authoritative",
        "historical_live_rain_baseline": (
            "any_positive_rain_hold_preserved_as_history_not_runtime_policy"
        ),
        "temperature": "informational_until_limits_are_approved",
        "wind": "informational_for_drip_unless_physical_safety_concern",
        "crop_need_bands": UNKNOWN,
        "successful_watering_evidence": [
            "credible_valve_opening",
            "new_physical_flow",
            "observed_runtime",
            "off_and_closure_evidence",
            "no_unresolved_failure",
        ],
        "measured_volume": UNAVAILABLE,
        "carry_forward": "one_missed_opportunity_signal_only_never_minutes",
        "owner_hold_expiry": "none_explicit_release_required",
        "controller_power_loss_behavior": UNKNOWN,
    },
    "water_energy_phase1": {
        "absolute_discretionary_battery_floor_soc_pct": 40,
        "approximate_inverter_grid_support_soc_pct": 30,
        "provisional_working_reserve_soc_pct": 50,
        "candidate_dynamic_reserves_soc_pct": {
            "sunny": 63,
            "mixed": 67,
            "poor_or_uncertain": 70,
        },
        "grid_policy": "minimum_avoidable_cost_not_absolute_prohibition",
        "owner_provisional_tariff_zar_per_kwh": 9,
        "storage_tanks": {"count": 5, "litres_each": 5500},
        "reservoir_tanks": {"count": 12, "litres_each": 5500},
        "tank_volume_may_be_inferred_from_counts": False,
        "borehole_integration": "SmartLife_identity_Unknown",
        "solar_transfer_pump_control_identity": UNKNOWN,
        "fertilizer_controller": {
            "manufacturer": "SONOFF",
            "model": "4CHPRO R3",
            "device_id": "100204d497",
            "name": "Controller (1) Right",
            "channel_1": "Kunsmis In",
            "channel_2": "Kunsmis Meng",
            "channels_3_4": "unused",
            "minimum_preflow_minutes": 10,
            "maximum_injection_pulse_seconds": 60,
            "minimum_pulse_spacing_minutes": 10,
            "clean_water_flush_required": True,
            "actuation_authorized": False,
        },
    },
}

_C12345_CANARY_RECORD = {
    "schema_version": 1,
    "packet_id": "ROOTLINE-CANARY-C12345-CH2-20260727-32B0D177-G1",
    "zone_id": "C12345",
    "owner_zone_name": "C - Kamp",
    "channel": 2,
    "crop_use": "vegetables",
    "transport": {
        "on_event": "irrigation_1_ch2_on",
        "on_requested_at": "2026-07-27T16:32:07.6560637+02:00",
        "on_http_status": 200,
        "on_acceptance": "accepted",
        "off_event": "irrigation_1_ch2_off",
        "off_requested_at": "2026-07-27T16:32:37.6651307+02:00",
        "off_http_status": 200,
        "off_acceptance": "accepted",
        "on_to_off_seconds": 30.009,
        "retry_count": 0,
    },
    "physical": {
        "valve_opening_observed": True,
        "new_water_flow_observed": True,
        "correct_zone_identity_confirmed": True,
        "valve_closure_observed": True,
        "new_full_pressure_supply_flow_stopped": True,
        "residual_drainage": "diminishing",
        "dripper_decay_seconds": None,
        "dripper_decay_seconds_availability": UNAVAILABLE,
        "manual_isolation_used": False,
        "final_physical_state": "safe_closed",
        "unexpected_zone_activity_observed": False,
    },
    "authority": {
        "additional_on_off_requests": False,
        "retry": False,
        "schedule": False,
        "workflow": False,
        "autonomous_continuation": False,
        "evidence_persisted": False,
    },
}
C12345_CANARY_SHA256 = "ef388830f14056bf7baea2915950a655ae77c8f7c058b8e1f9f1c92638d028ab"


def get_rootline_daily_advisor(
    advisor_date=None, brief_reader=None, policy_reader=None, now=None
):
    selected_date = str(
        advisor_date or (now or datetime.now(ZA_TZ)).astimezone(ZA_TZ).date().isoformat()
    )[:10]
    reader = brief_reader or (lambda: get_rootline_daily_brief(selected_date))
    # The brief and active policy are independent read models. Load them in
    # parallel so their bounded waits cannot accumulate inside an owner
    # callback worker.
    from modules.telemetry.rootline_bounded_read_group import run_bounded_read_group
    loaded = run_bounded_read_group({"brief":lambda:_safe_read(reader),
        "policy":lambda:_safe_read_policy(policy_reader or list_policy_review)},
        max_workers=2)
    brief=loaded["brief"];policy_packet=loaded["policy"]
    active_policy = (
        policy_packet.get("active_policy")
        if isinstance(policy_packet, dict)
        else None
    )
    return build_rootline_daily_advisor(
        brief, selected_date, active_policy=active_policy, now=now
    ), 200


def build_rootline_daily_advisor(brief, advisor_date, active_policy=None, now=None):
    brief = brief if isinstance(brief, dict) and brief.get("success") is True else None
    weather = brief.get("current_conditions", {}) if brief else {}
    forecast = brief.get("forecast", {}) if brief else {}
    irrigation = brief.get("irrigation", {}) if brief else {}
    release_evidence = (
        brief.get("rain_release_evidence")
        if brief and isinstance(brief.get("rain_release_evidence"), dict)
        else None
    )
    active_snapshot = _active_policy_snapshot(active_policy)
    evaluated_at = _evaluation_time(now)
    legacy_zones = {
        str(item.get("zone_id") or ""): item
        for item in irrigation.get("zones", [])
        if isinstance(item, dict)
    }

    zones = []
    for zone_id, knowledge in OPERATING_KNOWLEDGE["zones"].items():
        zones.append(
            _advise_zone(
                knowledge,
                legacy_zones.get(zone_id),
                weather,
                forecast,
                irrigation,
                active_snapshot,
                release_evidence,
                advisor_date,
                evaluated_at,
                now is not None,
            )
        )

    unresolved = _unresolved_owner_decisions(active_snapshot)
    status = "hold" if any(zone["recommendation"] == "Hold" for zone in zones) else "needs_data"
    generated_at = evaluated_at.isoformat() if evaluated_at else None
    return {
        "success": True,
        "status": status,
        "mode": "owner_read_only_command_inert",
        "operating_date": advisor_date,
        "generated_at": generated_at,
        "executive_summary": _executive_summary(zones, weather, forecast),
        "weather": {
            "current_status": _evidence_status(weather),
            "current_freshness": weather.get("freshness", UNAVAILABLE) if weather else UNAVAILABLE,
            "last_reading_at": weather.get("last_reading_at") if weather else None,
            "data_age_minutes": weather.get("data_age_minutes") if weather else None,
            "temperature_c": weather.get("temperature_c") if weather else None,
            "rain_rate_mm_h": weather.get("rain_rate_mm_h") if weather else None,
            "rain_today_mm": weather.get("rain_today_mm") if weather else None,
            "wind_speed_kmh": weather.get("wind_speed_kmh") if weather else None,
            "forecast_status": _evidence_status(forecast),
            "forecast_freshness": forecast.get("freshness", UNAVAILABLE) if forecast else UNAVAILABLE,
            "forecast_threshold_policy": UNKNOWN,
        },
        "zones": zones,
        "operating_knowledge": deepcopy(OPERATING_KNOWLEDGE),
        "active_advice_policy": {
            "status": "Available" if active_snapshot else UNAVAILABLE,
            "proposal_id": (
                active_policy.get("proposal_id")
                if isinstance(active_policy, dict) else None
            ),
            "version": (
                active_policy.get("version")
                if isinstance(active_policy, dict) else None
            ),
            "live_rain_hold": (
                deepcopy(active_snapshot.get("live_rain_hold"))
                if active_snapshot else UNAVAILABLE
            ),
            "daylight_windows": (
                {
                    zone_id: deepcopy(zone.get("daylight_window", UNKNOWN))
                    for zone_id, zone in active_snapshot.get("zones", {}).items()
                }
                if active_snapshot else UNAVAILABLE
            ),
        },
        "physical_identity_evidence": _commissioned_identity_evidence(),
        "unresolved_owner_decisions": unresolved,
        "canary_evidence_persistence": canary_evidence_persistence_contract(),
        "authority": deepcopy(AUTHORITY),
        "source": {
            "daily_brief_available": bool(brief),
            "legacy_plans_are_historical_evidence_only": True,
            "superseded_migration_202607260005_must_not_be_applied": True,
        },
    }


def canonical_c12345_canary_record():
    record = deepcopy(_C12345_CANARY_RECORD)
    record["evidence_sha256"] = C12345_CANARY_SHA256
    record["persistence_provenance"] = {
        "actor_identity": "Charl_owner_attested_designated_operator",
        "actor_identity_basis": "owner_attestation",
        "observed_at": "2026-07-27T16:34:37.6651307+02:00",
        "operator_observations": deepcopy(record["physical"]),
        "transport_observations": deepcopy(record["transport"]),
    }
    record["envelope_sha256"] = canonical_canary_envelope_sha256(record)
    return record


def canonical_canary_sha256(record):
    payload = deepcopy(record)
    payload.pop("evidence_sha256", None)
    payload.pop("envelope_sha256", None)
    payload.pop("persistence_provenance", None)
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return sha256(canonical).hexdigest()


def canonical_canary_envelope_sha256(record):
    payload = deepcopy(record)
    payload.pop("envelope_sha256", None)
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return sha256(canonical).hexdigest()


def classify_canary_evidence_append(candidate, existing=None):
    """Validate append/replay identity without persisting anything."""
    if not _valid_canary_evidence_candidate(candidate):
        return {"status": "invalid", "append_allowed": False}
    packet_id = str(candidate.get("packet_id") or "").strip()
    if existing is None:
        return {"status": "append_candidate", "append_allowed": True}
    if not _valid_canary_evidence_candidate(existing):
        return {"status": "identity_conflict", "append_allowed": False}
    if str(existing.get("packet_id") or "") != packet_id:
        return {"status": "identity_conflict", "append_allowed": False}
    if existing == candidate:
        return {"status": "exact_replay", "append_allowed": False}
    return {"status": "identity_conflict", "append_allowed": False}


def canary_evidence_persistence_contract():
    return {
        "status": "design_only_unapplied",
        "append_only": True,
        "identity": "packet_id",
        "content_identity": "evidence_sha256",
        "provenance_envelope_identity": "envelope_sha256",
        "required_provenance": [
            "actor_identity",
            "actor_identity_basis",
            "operator_observations",
            "transport_observations",
            "observed_at",
        ],
        "unknown_values_preserved": True,
        "exact_replay": "return_existing_without_insert",
        "altered_replay": "reject_identity_conflict",
        "update_delete": "prohibited",
        "browser_roles": "no_direct_access",
        "migration_designed": False,
        "production_row_written": False,
    }


def _valid_canary_evidence_candidate(candidate):
    if not isinstance(candidate, dict):
        return False
    expected_top = set(_C12345_CANARY_RECORD) | {
        "evidence_sha256",
        "envelope_sha256",
        "persistence_provenance",
    }
    if set(candidate) != expected_top:
        return False
    if not _same_keys(candidate.get("transport"), _C12345_CANARY_RECORD["transport"]):
        return False
    if not _same_keys(candidate.get("physical"), _C12345_CANARY_RECORD["physical"]):
        return False
    if not _same_keys(candidate.get("authority"), _C12345_CANARY_RECORD["authority"]):
        return False
    if type(candidate.get("schema_version")) is not int or candidate["schema_version"] != 1:
        return False

    packet_id = str(candidate.get("packet_id") or "").strip()
    evidence_hash = str(candidate.get("evidence_sha256") or "").strip().lower()
    envelope_hash = str(candidate.get("envelope_sha256") or "").strip().lower()
    if not re.fullmatch(
        r"ROOTLINE-CANARY-[A-Z][0-9]{5}-CH[1-9][0-9]*-[0-9]{8}-[A-F0-9]+-G[1-9][0-9]*",
        packet_id,
    ):
        return False
    if not re.fullmatch(r"[0-9a-f]{64}", evidence_hash) or not re.fullmatch(
        r"[0-9a-f]{64}", envelope_hash
    ):
        return False
    if canonical_canary_sha256(candidate) != evidence_hash:
        return False
    if canonical_canary_envelope_sha256(candidate) != envelope_hash:
        return False
    zone_id = candidate.get("zone_id")
    channel = candidate.get("channel")
    if not isinstance(zone_id, str) or not re.fullmatch(r"[A-Z][0-9]{5}", zone_id):
        return False
    if type(channel) is not int or channel < 1:
        return False
    if f"-{zone_id}-CH{channel}-" not in packet_id:
        return False
    for field in ("owner_zone_name", "crop_use"):
        value = candidate.get(field)
        if not isinstance(value, str) or not value.strip() or len(value) > 160:
            return False

    transport = candidate["transport"]
    for direction in ("on", "off"):
        event = transport.get(f"{direction}_event")
        if not isinstance(event, str) or not re.fullmatch(
            rf"irrigation_[1-9][0-9]*_ch{channel}_{direction}", event
        ):
            return False
        if not _timezone_aware_iso(transport.get(f"{direction}_requested_at")):
            return False
        http_status = transport.get(f"{direction}_http_status")
        if type(http_status) is not int or not 100 <= http_status <= 599:
            return False
        if transport.get(f"{direction}_acceptance") not in {
            "accepted",
            "failed",
            "timeout_uncertain",
            UNAVAILABLE,
        }:
            return False
    duration = transport.get("on_to_off_seconds")
    if (
        isinstance(duration, bool)
        or not isinstance(duration, (int, float))
        or not math.isfinite(duration)
        or duration < 0
        or duration > 30.1
    ):
        return False
    if type(transport.get("retry_count")) is not int or transport["retry_count"] != 0:
        return False

    physical = candidate["physical"]
    for field in (
        "valve_opening_observed",
        "new_water_flow_observed",
        "correct_zone_identity_confirmed",
        "valve_closure_observed",
        "new_full_pressure_supply_flow_stopped",
        "manual_isolation_used",
        "unexpected_zone_activity_observed",
    ):
        if type(physical.get(field)) is not bool:
            return False
    if physical.get("residual_drainage") not in {
        "none",
        "diminishing",
        "continued_full_flow",
        "unclear",
    }:
        return False
    if physical.get("final_physical_state") not in {
        "safe_closed",
        "unsafe",
        UNAVAILABLE,
    }:
        return False

    provenance = candidate.get("persistence_provenance")
    required_provenance = {
        "actor_identity",
        "actor_identity_basis",
        "observed_at",
        "operator_observations",
        "transport_observations",
    }
    if not isinstance(provenance, dict) or set(provenance) != required_provenance:
        return False
    if not str(provenance.get("actor_identity") or "").strip():
        return False
    if provenance.get("actor_identity_basis") not in {"owner_attestation", "authenticated_owner_session"}:
        return False
    if not _timezone_aware_iso(provenance.get("observed_at")):
        return False
    if provenance.get("operator_observations") != candidate.get("physical"):
        return False
    if provenance.get("transport_observations") != candidate.get("transport"):
        return False

    decay_seconds = physical.get("dripper_decay_seconds")
    decay_availability = physical.get("dripper_decay_seconds_availability")
    if decay_seconds is None:
        if decay_availability != UNAVAILABLE:
            return False
    elif (
        isinstance(decay_seconds, bool)
        or not isinstance(decay_seconds, (int, float))
        or decay_seconds < 0
        or decay_availability != "Available"
    ):
        return False
    if any(type(value) is not bool or value for value in candidate["authority"].values()):
        return False
    return True


def _same_keys(value, exemplar):
    return isinstance(value, dict) and set(value) == set(exemplar)


def _timezone_aware_iso(value):
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() is not None


def _advise_zone(
    knowledge,
    legacy,
    weather,
    forecast,
    irrigation,
    active_policy,
    release_evidence,
    advisor_date,
    evaluated_at,
    advice_time_explicit,
):
    reasons = []
    recommendation = "Needs Data"
    eligibility = "Needs Data"
    weather_fresh = (
        weather.get("availability") == "Available" and weather.get("freshness") == "fresh"
    )
    forecast_fresh = (
        forecast.get("availability") == "Available" and forecast.get("freshness") == "fresh"
    )
    rain_rate = _number_or_none(weather.get("rain_rate_mm_h"))
    live_rain_rule = (
        active_policy.get("live_rain_hold")
        if isinstance(active_policy, dict)
        and isinstance(active_policy.get("live_rain_hold"), dict)
        else None
    )
    daylight_window = (
        active_policy.get("zones", {})
        .get(knowledge["zone_id"], {})
        .get("daylight_window", UNKNOWN)
        if isinstance(active_policy, dict)
        else UNKNOWN
    )
    dry_release_proven = False
    if not weather_fresh:
        reasons.append("Fresh current weather is required.")
    if not forecast_fresh:
        reasons.append(
            "Forecast evidence is stale or unavailable; planning confidence is "
            "degraded, but forecast freshness is not a current-rain execution gate."
        )
    if live_rain_rule is None:
        recommendation = "Hold"
        eligibility = "Hold"
        reasons.append("An active authoritative live-rain policy is required.")
    elif not weather_fresh or rain_rate is None:
        recommendation = "Hold"
        eligibility = "Hold"
        reasons.append("Local weather evidence is missing or stale; Hold remains fail-closed.")
    elif rain_rate > live_rain_rule["threshold_mm_per_hour"]:
        recommendation = "Hold"
        eligibility = "Hold"
        reasons.append(
            "Fresh live rain is strictly above 0.2 mm/hour; the active policy requires Hold."
        )
    elif not _advice_time_is_authoritative(
        evaluated_at, advisor_date, advice_time_explicit
    ):
        recommendation = "Needs Data"
        eligibility = "Needs Data"
        reasons.append(
            "Current advice time is missing, malformed or conflicts with the "
            "operating date; the daylight gate is Needs Data."
        )
    elif not (dry_release_proven := _dry_release_proven(
        release_evidence, live_rain_rule.get("release_policy"), rain_rate,
        weather.get("last_reading_at"), advisor_date, evaluated_at)):
        recommendation = "Hold"
        eligibility = "Hold"
        reasons.append(
            "The live-rain threshold is not exceeded. Release requires the current "
            "reading and every reading across 30 continuous minutes to be exactly "
            "0.0 mm/hour with at least two fresh durable boundary readings from "
            "the governed local station; that automatic evidence is not proven."
        )
    else:
        recommendation = "Needs Data"
        eligibility = "Needs Data"
        reasons.extend(
            [
                "The active live-rain Hold is released; this does not prove irrigation eligibility.",
                "ROOTLINE selects the safest useful execution time adaptively from current need, weather, water and commissioned-device evidence; a fixed daylight window is not an irrigation gate.",
                "Eligibility is manual-advisory only.",
                "Forecast-rain thresholds are Unknown.",
            ]
        )
    if irrigation.get("availability") != "Available":
        reasons.append("Current irrigation evidence is Unavailable.")

    legacy_planned = legacy.get("planned_minutes") if legacy else None
    legacy_state = legacy.get("work_state") if legacy else None
    return {
        "zone_id": knowledge["zone_id"],
        "zone_name": knowledge["owner_name"],
        "crop_use": knowledge["crop_use"],
        "priority": "equal_owner_selection_on_conflict",
        "eligibility_today": eligibility,
        "recommendation": recommendation,
        "live_rain_release_proven": dry_release_proven,
        "forecast_planning_quality": "fresh" if forecast_fresh else "degraded",
        "planning_warnings": [] if forecast_fresh else ["forecast_stale_or_unavailable"],
        "proposed_runtime_minutes": None,
        "proposed_runtime_status": UNAVAILABLE,
        "runtime_suppressed_by": [
            "seasonal_boundaries_unknown",
            "minimum_runtime_unknown",
            "maximum_runtime_unknown",
            "crop_need_band_unknown",
            "forecast_rain_threshold_unknown",
        ]
        ,
        "reasoning": list(dict.fromkeys(reasons)),
        "previous_activity": {
            "legacy_planned_minutes": legacy_planned,
            "legacy_plan_state": legacy_state or UNAVAILABLE,
            "legacy_plan_evidence_class": (
                "historical_or_provisional_plan_evidence" if legacy else UNAVAILABLE
            ),
            "observed_runtime_minutes": None,
            "observed_runtime_status": UNAVAILABLE,
            "measured_water_volume": None,
            "measured_water_status": UNAVAILABLE,
            "verified_watering": UNAVAILABLE,
        },
    }


def _unresolved_owner_decisions(active_policy=None):
    decisions = [
        {"decision": "seasonal_boundaries", "current_value": UNKNOWN},
        {"decision": "minimum_runtime_per_zone", "current_value": UNKNOWN},
        {"decision": "maximum_runtime_per_zone", "current_value": UNKNOWN},
        {"decision": "forecast_rain_thresholds", "current_value": UNKNOWN},
        {"decision": "temperature_limits", "current_value": UNKNOWN},
        {"decision": "crop_need_bands", "current_value": UNKNOWN},
        {"decision": "controller_power_loss_behavior", "current_value": UNKNOWN},
        {"decision": "residual_drainage_decay_seconds", "current_value": UNAVAILABLE},
    ]
    return decisions


def _commissioned_identity_evidence():
    baseline = commissioned_controller_baseline()
    commissioning_ids = baseline.get("irrigation_commissioning_ids") or {}
    common = {
        "status": "supervised_commissioned",
        "counts_as_verified_watering": False,
        "controller_baseline_id": baseline.get("baseline_id"),
        "commissioning_evidence_sha256": baseline.get("commissioning_evidence_sha256"),
        "evidence_source": baseline.get("evidence_source"),
    }
    return {
        "B12345": {**common, "commissioning_id": commissioning_ids.get("B12345")},
        "C12345": {
            **common,
            "commissioning_id": commissioning_ids.get("C12345"),
            "legacy_canary_packet_id": _C12345_CANARY_RECORD["packet_id"],
            "legacy_canary_evidence_sha256": C12345_CANARY_SHA256,
            "legacy_canary_final_physical_state": "safe_closed",
        },
    }


def _executive_summary(zones, weather, forecast):
    missing = []
    if not weather or weather.get("availability") != "Available":
        missing.append("current weather")
    if not forecast or forecast.get("availability") != "Available":
        missing.append("forecast")
    suffix = f" Evidence still missing: {', '.join(missing)}." if missing else ""
    if any(zone["recommendation"] == "Hold" for zone in zones):
        return (
            "ROOTLINE is holding one or both known drip zones because an active "
            "weather or dry-release evidence gate is not safely cleared. "
            f"No runtime is proposed and no action is authorized.{suffix}"
        )
    return (
        "B12345 and C12345 remain manual-advisory only. Unknown runtime limits, "
        "crop-need bands, and forecast-rain policy prevent an Irrigate "
        f"recommendation or proposed runtime.{suffix}"
    )


def _safe_read(reader):
    try:
        result = reader()
        payload, status = result if isinstance(result, tuple) else (result, 200)
        if status >= 400 or not isinstance(payload, dict):
            return None
        return payload
    except Exception:
        return None


def _safe_read_policy(reader):
    payload = _safe_read(reader)
    return payload if isinstance(payload, dict) and payload.get("success") is True else None


def _active_policy_snapshot(active_policy):
    if not isinstance(active_policy, dict):
        return None
    policy = active_policy.get("policy")
    if not isinstance(policy, dict):
        return None
    candidate = deepcopy(policy)
    zones = candidate.get("zones")
    if not isinstance(zones, dict) or set(zones) != set(OPERATING_KNOWLEDGE["zones"]):
        return None
    for zone_id, zone in zones.items():
        if (
            not isinstance(zone, dict)
            or zone.get("crop_use")
            != OPERATING_KNOWLEDGE["zones"][zone_id]["crop_use"]
        ):
            return None
        zone.pop("crop_use", None)
        window = zone.get("daylight_window")
        if isinstance(window, dict):
            if window.get("timezone") != "Africa/Johannesburg":
                return None
            window.pop("timezone", None)
    try:
        return normalize_policy_snapshot(candidate)
    except (TypeError, ValueError):
        return None


def _evaluation_time(value):
    if value is None:
        return datetime.now(ZA_TZ)
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        return None
    return value.astimezone(ZA_TZ)


def _advice_time_is_authoritative(
    evaluated_at, advisor_date, enforce_operating_date
):
    return (
        isinstance(evaluated_at, datetime)
        and evaluated_at.tzinfo is not None
        and evaluated_at.utcoffset() is not None
        and (
            not enforce_operating_date
            or (
                isinstance(advisor_date, str)
                and evaluated_at.astimezone(ZA_TZ).date().isoformat()
                == advisor_date
            )
        )
    )


def _daylight_gate(window, evaluated_at, advisor_date=None):
    if (
        evaluated_at is None
        or not isinstance(window, dict)
        or set(window) != {"start", "end", "timezone"}
        or window.get("timezone") != "Africa/Johannesburg"
    ):
        return "needs_data", (
            "The daylight window or current advice time is missing, malformed or "
            "conflicting; the time gate is Needs Data."
        )
    if (
        not isinstance(advisor_date, str)
        or evaluated_at.astimezone(ZA_TZ).date().isoformat() != advisor_date
    ):
        return "needs_data", (
            "The daylight window or current advice time is missing, malformed or "
            "conflicting; the time gate is Needs Data."
        )
    try:
        start = datetime.strptime(window["start"], "%H:%M").time()
        end = datetime.strptime(window["end"], "%H:%M").time()
    except (TypeError, ValueError):
        return "needs_data", (
            "The daylight window or current advice time is missing, malformed or "
            "conflicting; the time gate is Needs Data."
        )
    if start >= end:
        return "needs_data", (
            "The daylight window or current advice time is missing, malformed or "
            "conflicting; the time gate is Needs Data."
        )
    current = evaluated_at.astimezone(ZA_TZ).time().replace(tzinfo=None)
    if start <= current < end:
        return "inside", (
            "Current Johannesburg advice time is inside the owner-approved "
            "start-inclusive, end-exclusive daylight window."
        )
    return "outside", (
        "Current Johannesburg advice time is outside the owner-approved "
        "daylight window; advice is Hold."
    )


def _dry_release_proven(
    evidence,
    release_policy,
    current_rain_rate,
    current_observed_at,
    advisor_date,
    evaluated_at,
):
    if not isinstance(release_policy, dict) or not isinstance(evidence, dict):
        return False
    if current_rain_rate != release_policy["dry_rain_rate_mm_per_hour"]:
        return False
    if evidence.get("availability") != "Available":
        return False
    if evidence.get("conflicting") is not False:
        return False
    if evidence.get("continuous_zero_rain_confirmed") is not True:
        return False
    if evidence.get("source") != "governed_local_weather_station":
        return False
    if evidence.get("source_healthy") is not True:
        return False
    start = _aware_datetime(evidence.get("interval_start_at"))
    end = _aware_datetime(evidence.get("interval_end_at"))
    current_observed = _aware_datetime(current_observed_at)
    if start is None or end is None or end - start < timedelta(
        minutes=release_policy["dry_interval_minutes"]
    ):
        return False
    if (
        current_observed is None
        or current_observed != end
        or end > evaluated_at
        or end.astimezone(ZA_TZ).date().isoformat() != advisor_date
    ):
        return False
    readings = evidence.get("station_readings")
    if not isinstance(readings, list):
        return False
    fresh_zero_readings = set()
    for reading in readings:
        if not isinstance(reading, dict) or reading.get("freshness") != "fresh":
            return False
        observed_at = _aware_datetime(reading.get("observed_at"))
        rain_rate = _number_or_none(reading.get("rain_rate_mm_h"))
        if (
            observed_at is None
            or not start <= observed_at <= end
            or rain_rate != release_policy["dry_rain_rate_mm_per_hour"]
        ):
            return False
        fresh_zero_readings.add(observed_at)
    return (
        len(fresh_zero_readings)
        >= release_policy["minimum_fresh_station_readings"]
        and min(fresh_zero_readings) == start
        and max(fresh_zero_readings) == end
    )


def _aware_datetime(value):
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed


def _evidence_status(value):
    return value.get("availability", UNAVAILABLE) if isinstance(value, dict) else UNAVAILABLE


def _number_or_none(value):
    if value is None or value == "" or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
