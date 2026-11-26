"""Prospective owner limits and versioned scheduled injector settings.

Historical claims retain their original timing. Only future command-mode
admission consumes explicitly saved configurable injection settings.
"""
from datetime import datetime, timezone
import math
import hashlib
import json

AUXILIARY_CONTROL_FIELDS = {
    "mixer": {
        "session_minutes": {"label": "Maximum new mixing session", "unit": "minutes", "min": 1, "max": 10, "default": 10},
        "daily_minutes": {"label": "Maximum mixing time per day", "unit": "minutes", "min": 1, "max": 30, "default": 30},
    },
    "injection": {
        "pulse_minutes": {"label": "Injection duration", "unit": "minutes", "min": 1, "max": 10, "default": 2},
        "pulses_per_60_minutes": {"label": "Injections per 60 minutes", "unit": "pulses", "min": 1, "max": 2, "default": 2},
        **{f"inject_camp_{camp}": {"label": f"Inject in Camp {camp.upper()}", "type": "checkbox", "default": camp in ("b", "c")} for camp in ("a", "b", "c", "e")},
        "max_pulses_per_run": {"label": "Maximum injection pulses per irrigation run", "unit": "pulses", "min": 1, "max": 4, "default": 4},
    },
}


def validate_auxiliary_control_fields(device, fields):
    if not isinstance(fields, dict) or set(fields) - set(AUXILIARY_CONTROL_FIELDS.get(device, {})):
        raise ValueError("unsupported_auxiliary_setting")
    result = {}
    for key, value in fields.items():
        spec = AUXILIARY_CONTROL_FIELDS[device][key]
        if spec.get("type") == "checkbox":
            if type(value) is not bool:
                raise ValueError("auxiliary_setting_out_of_range")
            result[key] = value
            continue
        if (type(value) not in {int, float} or not math.isfinite(value) or value != int(value)
                or not spec["min"] <= value <= spec["max"]):
            raise ValueError("auxiliary_setting_out_of_range")
        result[key] = int(value)
    return result


def effective_auxiliary_settings(owner_controls=None, *, now=None):
    now = now or datetime.now(timezone.utc)
    result = {device: {key: spec["default"] for key, spec in fields.items()}
        for device, fields in AUXILIARY_CONTROL_FIELDS.items()}
    for device, record in (owner_controls or {}).get("devices", {}).items():
        if device not in result:
            continue
        if record.get("expires_at") and datetime.fromisoformat(str(record["expires_at"]).replace("Z", "+00:00")) <= now:
            continue
        if record.get("effective_at") and datetime.fromisoformat(str(record["effective_at"]).replace("Z", "+00:00")) > now:
            continue
        fields = {key: value for key, value in (record.get("fields") or {}).items()
            if key in AUXILIARY_CONTROL_FIELDS[device]}
        result[device].update(validate_auxiliary_control_fields(device, fields))
    return result


def mixer_owner_capacity_seconds(accounting, owner_controls=None, *, now=None):
    limits = effective_auxiliary_settings(owner_controls, now=now)["mixer"]
    # Unknown/unfinished reservations remain charged. Only the canonical
    # accounting projection's proven unused remainder can be used again.
    reserved = accounting.get("reserved_seconds")
    residual = accounting.get("known_residual_microseconds", 0)
    if (type(reserved) not in {int, float} or not math.isfinite(reserved) or reserved < 0
            or type(residual) not in {int, float} or not math.isfinite(residual) or residual < 0
            or residual > reserved * 1_000_000):
        return 0
    used_microseconds = max(0, math.ceil(reserved * 1_000_000) - int(residual))
    remaining = max(0, limits["daily_minutes"] * 60 * 1_000_000 - used_microseconds) // 1_000_000
    return min(limits["session_minutes"] * 60, remaining)


def owner_injection_pulse_limit(owner_controls=None, *, now=None, existing_limit=4):
    if type(existing_limit) is not int or existing_limit not in {2, 4}:
        raise ValueError("existing_injection_limit_invalid")
    selected = effective_auxiliary_settings(owner_controls, now=now)["injection"]["max_pulses_per_run"]
    return min(existing_limit, selected)

INJECTION_POLICY_CONTRACT = "rootline_owner_injection_policy.v1"
INJECTION_POLICY_FIELDS = ("pulse_minutes", "pulses_per_60_minutes", "inject_camp_a", "inject_camp_b", "inject_camp_c", "inject_camp_e")


def owner_injection_policy(owner_controls=None, *, now=None):
    """Only an explicit effective save opts future claims into configurable timing."""
    now = now or datetime.now(timezone.utc)
    record = (owner_controls or {}).get("devices", {}).get("injection", {})
    if not any(key in (record.get("fields") or {}) for key in INJECTION_POLICY_FIELDS):
        return None
    if record.get("expires_at") and datetime.fromisoformat(str(record["expires_at"]).replace("Z", "+00:00")) <= now:
        return None
    if record.get("effective_at") and datetime.fromisoformat(str(record["effective_at"]).replace("Z", "+00:00")) > now:
        return None
    fields = effective_auxiliary_settings(owner_controls, now=now)["injection"]
    value = {"contract_version": INJECTION_POLICY_CONTRACT,
        "pulse_seconds": fields["pulse_minutes"] * 60,
        "pulses_per_60_minutes": fields["pulses_per_60_minutes"],
        "zone_ids": [camp.upper()+"12345" for camp in ("a", "b", "c", "e") if fields["inject_camp_"+camp]]}
    value["policy_sha256"] = _injection_digest(value)
    return value


def _injection_digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def valid_injection_policy(value):
    if not isinstance(value, dict) or set(value) != {"contract_version", "pulse_seconds", "pulses_per_60_minutes", "zone_ids", "policy_sha256"}:
        return False
    zones = value.get("zone_ids")
    return (value["contract_version"] == INJECTION_POLICY_CONTRACT
        and type(value["pulse_seconds"]) is int and 60 <= value["pulse_seconds"] <= 600 and value["pulse_seconds"] % 60 == 0
        and type(value["pulses_per_60_minutes"]) is int and 1 <= value["pulses_per_60_minutes"] <= 2
        and isinstance(zones, list) and zones == [z for z in ("A12345", "B12345", "C12345", "E12345") if z in zones]
        and value["policy_sha256"] == _injection_digest({k:v for k,v in value.items() if k != "policy_sha256"}))


def injection_policy_context(context, owner_controls=None, *, now=None):
    policy = owner_injection_policy(owner_controls, now=now)
    # Legacy physical/native mode keeps its original commissioning envelope.
    if context.get("stop_mode") != "scheduled" or context.get("acceptance_mode") != "command_accepted":
        policy = None
    clean_context = {key: value for key, value in context.items() if key != "injection_policy"}
    return {**clean_context, **({"injection_policy": policy} if policy else {}),
        "owner_injection_pulse_limit": (4 if policy else owner_injection_pulse_limit(
            owner_controls, now=now, existing_limit=4 if context.get("stop_mode") == "scheduled" else 2))}
