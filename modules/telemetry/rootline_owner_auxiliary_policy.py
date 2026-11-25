"""Prospective owner limits inside the existing mixer and injection ceilings.

Original reservations, accepted OFF duties and the 120-second injector binding
remain unchanged. Only admission of future work consumes these lower limits.
"""
from datetime import datetime, timezone
import math

AUXILIARY_CONTROL_FIELDS = {
    "mixer": {
        "session_minutes": {"label": "Maximum new mixing session", "unit": "minutes", "min": 1, "max": 10, "default": 10},
        "daily_minutes": {"label": "Maximum mixing time per day", "unit": "minutes", "min": 1, "max": 30, "default": 30},
    },
    "injection": {
        "max_pulses_per_run": {"label": "Maximum injection pulses per irrigation run", "unit": "pulses", "min": 1, "max": 4, "default": 4},
    },
}


def validate_auxiliary_control_fields(device, fields):
    if not isinstance(fields, dict) or set(fields) - set(AUXILIARY_CONTROL_FIELDS.get(device, {})):
        raise ValueError("unsupported_auxiliary_setting")
    result = {}
    for key, value in fields.items():
        spec = AUXILIARY_CONTROL_FIELDS[device][key]
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
