"""Command-inert ROOTLINE operating knowledge and daily advice.

This module reads the existing owner Daily Brief and explains the approved
operating policy. It has no persistence, transport, scheduler, retry, n8n,
IFTTT, credential, command, or hardware dependency.
"""

from copy import deepcopy
from datetime import datetime
from hashlib import sha256
import json
import math
import re
from zoneinfo import ZoneInfo

from modules.telemetry.rootline_daily_brief import get_rootline_daily_brief


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
            "physical_mapping_status": "owner_confirmed_not_canary_proven",
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
        "daylight_only": True,
        "allowed_windows": UNKNOWN,
        "minimum_runtime_minutes": UNKNOWN,
        "maximum_runtime_minutes": UNKNOWN,
        "repeat_same_day": "fresh_owner_review_required",
        "simultaneous_zones": False,
        "forecast_rain_thresholds": UNKNOWN,
        "live_rain": "hold_until_rain_stops_evidence_refreshes_and_owner_reviews",
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


def get_rootline_daily_advisor(advisor_date=None, brief_reader=None, now=None):
    selected_date = str(
        advisor_date or (now or datetime.now(ZA_TZ)).astimezone(ZA_TZ).date().isoformat()
    )[:10]
    reader = brief_reader or (lambda: get_rootline_daily_brief(selected_date))
    brief = _safe_read(reader)
    return build_rootline_daily_advisor(brief, selected_date, now=now), 200


def build_rootline_daily_advisor(brief, advisor_date, now=None):
    brief = brief if isinstance(brief, dict) and brief.get("success") is True else None
    weather = brief.get("current_conditions", {}) if brief else {}
    forecast = brief.get("forecast", {}) if brief else {}
    irrigation = brief.get("irrigation", {}) if brief else {}
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
            )
        )

    unresolved = _unresolved_owner_decisions()
    status = "hold" if any(zone["recommendation"] == "Hold" for zone in zones) else "needs_data"
    generated_at = (now or datetime.now(ZA_TZ)).astimezone(ZA_TZ).isoformat()
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
        "physical_identity_evidence": {
            "C12345": {
                "status": "proven_once_supervised",
                "counts_as_verified_watering": False,
                "packet_id": _C12345_CANARY_RECORD["packet_id"],
                "evidence_sha256": C12345_CANARY_SHA256,
                "final_physical_state": "safe_closed",
            },
            "B12345": {
                "status": "not_canary_proven",
                "counts_as_verified_watering": False,
            },
        },
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


def _advise_zone(knowledge, legacy, weather, forecast, irrigation):
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
    if not weather_fresh:
        reasons.append("Fresh current weather is required.")
    if not forecast_fresh:
        reasons.append("A fresh forecast is required.")
    if weather_fresh and rain_rate is not None and rain_rate > 0:
        recommendation = "Hold"
        eligibility = "Hold"
        reasons.append("Fresh live rain requires Hold until rain stops, evidence refreshes, and the owner reviews.")
    else:
        reasons.extend(
            [
                "Eligibility is manual-advisory only.",
                "The exact daylight operating window is Unknown.",
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
        "proposed_runtime_minutes": None,
        "proposed_runtime_status": UNAVAILABLE,
        "runtime_suppressed_by": [
            "seasonal_boundaries_unknown",
            "allowed_window_unknown",
            "minimum_runtime_unknown",
            "maximum_runtime_unknown",
            "crop_need_band_unknown",
            "forecast_rain_threshold_unknown",
        ],
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


def _unresolved_owner_decisions():
    return [
        {"decision": "seasonal_boundaries", "current_value": UNKNOWN},
        {"decision": "exact_daylight_windows_per_zone", "current_value": UNKNOWN},
        {"decision": "minimum_runtime_per_zone", "current_value": UNKNOWN},
        {"decision": "maximum_runtime_per_zone", "current_value": UNKNOWN},
        {"decision": "forecast_rain_thresholds", "current_value": UNKNOWN},
        {"decision": "temperature_limits", "current_value": UNKNOWN},
        {"decision": "crop_need_bands", "current_value": UNKNOWN},
        {"decision": "controller_power_loss_behavior", "current_value": UNKNOWN},
        {"decision": "residual_drainage_decay_seconds", "current_value": UNAVAILABLE},
    ]


def _executive_summary(zones, weather, forecast):
    if any(zone["recommendation"] == "Hold" for zone in zones):
        return (
            "ROOTLINE is holding both known drip zones because fresh live rain is present. "
            "No runtime is proposed and no action is authorized."
        )
    missing = []
    if not weather or weather.get("availability") != "Available":
        missing.append("current weather")
    if not forecast or forecast.get("availability") != "Available":
        missing.append("forecast")
    suffix = f" Evidence still missing: {', '.join(missing)}." if missing else ""
    return (
        "B12345 and C12345 remain manual-advisory only. Unknown operating windows, "
        "runtime limits, crop-need bands, and forecast-rain policy prevent an Irrigate "
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


def _evidence_status(value):
    return value.get("availability", UNAVAILABLE) if isinstance(value, dict) else UNAVAILABLE


def _number_or_none(value):
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
