"""Fresh, command-inert energy decisions shared by ROOTLINE device duties.

The owner continuous-supply policy is separate from discretionary mixer reserve.
Grid power measurements are not proof that a remote breaker is commissioned.
"""
from datetime import datetime, timedelta, timezone
import math


# Owner-editable values share this schema with the web control service. These
# defaults are the existing policy; no settings are written by deployment.
ENERGY_CONTROL_FIELDS = {
    "borehole": {
        "solar_proxy_w": {"label": "Solar level to stop AC backup", "unit": "W", "min": 1, "max": None, "default": 1500},
        "battery_floor_pct": {"label": "Battery floor without grid supply", "unit": "%", "min": 0, "max": 100, "default": 30},
    },
    "eskom": {
        "on_soc_pct": {"label": "Grid ON at battery level", "unit": "%", "min": 0, "max": 99, "default": 30},
        "off_soc_pct": {"label": "Grid OFF after solar recovery", "unit": "%", "min": 1, "max": 100, "default": 35},
    },
    "mixer": {
        "reserve_soc_pct": {"label": "Battery reserve for mixing", "unit": "%", "min": 50, "max": 100, "default": 70},
    },
}


def validate_energy_control_fields(device, fields):
    if not isinstance(fields, dict) or set(fields) - set(ENERGY_CONTROL_FIELDS.get(device, {})):
        raise ValueError("unsupported_energy_setting")
    result = {}
    for key, value in fields.items():
        spec = ENERGY_CONTROL_FIELDS[device][key]
        number = _number(value)
        if (isinstance(value, bool) or not isinstance(value, (int, float)) or number is None
                or number < spec["min"] or spec["max"] is not None and number > spec["max"]):
            raise ValueError("energy_setting_out_of_range")
        result[key] = number
    if device == "eskom":
        on = result.get("on_soc_pct", ENERGY_CONTROL_FIELDS[device]["on_soc_pct"]["default"])
        off = result.get("off_soc_pct", ENERGY_CONTROL_FIELDS[device]["off_soc_pct"]["default"])
        if on >= off:
            raise ValueError("eskom_on_must_be_below_off")
    return result


def effective_energy_settings(owner_controls=None, *, now=None, reserve_pct=70):
    now = now or datetime.now(timezone.utc)
    settings = {device: {key: spec["default"] for key, spec in fields.items()}
                for device, fields in ENERGY_CONTROL_FIELDS.items()}
    settings["mixer"]["reserve_soc_pct"] = reserve_pct
    for device, record in (owner_controls or {}).get("devices", {}).items():
        if device not in settings:
            continue
        expires = record.get("expires_at")
        effective = record.get("effective_at")
        if expires and datetime.fromisoformat(str(expires).replace("Z", "+00:00")) <= now:
            continue
        if effective and datetime.fromisoformat(str(effective).replace("Z", "+00:00")) > now:
            continue
        values = validate_energy_control_fields(device, {key: value
            for key, value in (record.get("fields") or {}).items()
            if key in ENERGY_CONTROL_FIELDS[device]})
        settings[device].update(values)
    return settings


def managed_energy_decision(power, *, now, reserve_pct=70, owner_controls=None, owner_request=None):
    settings = effective_energy_settings(owner_controls, now=now, reserve_pct=reserve_pct)
    reserve_pct = settings["mixer"]["reserve_soc_pct"]
    solar_proxy = settings["borehole"]["solar_proxy_w"]
    battery_floor = settings["borehole"]["battery_floor_pct"]
    grid_on = settings["eskom"]["on_soc_pct"]
    grid_off = settings["eskom"]["off_soc_pct"]
    power = power if isinstance(power, dict) else {}
    try:
        observed = datetime.fromisoformat(str(power.get("observed_at") or "").replace("Z", "+00:00"))
        fresh = observed.tzinfo is not None and timedelta(0) <= now-observed <= timedelta(minutes=15)
    except (TypeError, ValueError):
        fresh = False
    values = {key: _number(power.get(key)) for key in (
        "battery_soc_pct", "solar_power_w", "load_power_w", "grid_power_w", "battery_power_w")}
    soc, solar, load, grid, battery = (values[key] for key in values)
    usable = (fresh and power.get("conflicting") is not True
        and all(value is not None for value in (soc, solar, load, grid))
        and 0 <= soc <= 100 and solar >= 0 and load >= 0)
    charging = (battery is not None and battery < -50
        and str(power.get("battery_state") or "").casefold() == "charging")
    # Require net solar beyond current load, and more charging than grid import
    # can explain. Grid-only charging never asks to disconnect grid supply.
    solar_recovery = (usable and charging and solar > load
        and -battery > max(0, grid))
    grid_request = ("ON" if usable and soc <= grid_on else
        "OFF" if usable and soc >= grid_off and solar_recovery else "UNCHANGED")
    # A separately confirmed one-off grid request uses the same fresh evidence.
    # OFF keeps the existing solar-recovery rule; an ineligible request waits.
    manual_grid_request = None
    if owner_request is not None:
        grid_request = "UNCHANGED"
        change = owner_request.get("change") or {}
        starts = datetime.fromisoformat(str(owner_request.get("effective_at")).replace("Z", "+00:00"))
        expires = datetime.fromisoformat(str(owner_request.get("expires_at")).replace("Z", "+00:00"))
        if (change.get("device_id") == "eskom" and change.get("kind") in {"run", "stop"}
                and owner_request.get("request_id") and starts <= now < expires):
            manual_grid_request = owner_request["request_id"]
            grid_request = ("ON" if usable and change["kind"] == "run" else
                "OFF" if usable and change["kind"] == "stop" and soc >= grid_off and solar_recovery else "UNCHANGED")
    power_fresh = fresh and power.get("conflicting") is not True
    sunshine = bool(power_fresh and solar is not None and solar >= solar_proxy)
    backup_known = bool(power_fresh and soc is not None and 0 <= soc <= 100
        and grid is not None and solar is not None and solar >= 0)
    borehole_known = sunshine or backup_known
    # This switch supplies AC backup; the pump has an independent solar supply.
    borehole_ok = not sunshine and backup_known and (soc > battery_floor or grid > 0)
    return {"fresh": usable, "borehole_fresh": bool(sunshine or usable),
        "continuous_borehole_fresh": borehole_known,
        "continuous_borehole_eligible": bool(borehole_ok),
        "continuous_borehole_reason": ("sunshine_ac_backup_not_required" if sunshine else
            "fresh_supply_available" if borehole_ok else
            "battery_low_without_verified_grid_supply" if borehole_known else "fresh_power_evidence_required"),
        "borehole_sunshine_proxy": sunshine, "borehole_solar_proxy_w": solar_proxy, "borehole_battery_floor_pct": battery_floor,
        "borehole_energy_metered": False, "estimated_grid_tariff_zar_per_kwh": 9.2,
        "borehole_energy_context": {**values, "observed_at": observed.isoformat() if fresh else None,
            "controlled_supply": "borehole_ac_backup", "pump_operation": "Unknown",
            "ac_backup_off_for_sunshine": sunshine,
            "sunshine_proxy_available": sunshine, "battery_charging": battery < 0 if battery is not None else None,
            "pump_energy_kwh": None, "pump_grid_cost_zar": None,
            "grid_cost_tariff_zar_per_kwh": 9.2, "pump_energy_measured": False,
            "household_grid_import_is_pump_consumption": False,
            "eskom_requested_state": grid_request,
            "backup_strategy": ("separate_solar_ac_backup_off" if sunshine else
                "grid_support" if backup_known and grid > 0 else
                "battery_charging_above_floor" if backup_known and soc > battery_floor and battery is not None and battery < 0 else
                "battery_discharging_above_floor" if backup_known and soc > battery_floor and battery is not None and battery > 0 else
                "battery_above_floor_direction_unknown_or_idle" if backup_known and soc > battery_floor else
                "battery_floor_requires_grid" if backup_known else "supply_evidence_unavailable")}, "observed_at": observed.isoformat() if fresh else None,
        "borehole_eligible": bool(usable and not sunshine and (soc > battery_floor or grid > 0)),
        "borehole_reason": ("sunshine_ac_backup_not_required" if sunshine else
            "fresh_supply_available" if usable and (soc > battery_floor or grid > 0)
            else "battery_low_without_verified_grid_supply" if usable else "fresh_power_evidence_required"),
        "mixing_eligible": bool(usable and (solar-load >= 1000 or soc > max(50, reserve_pct))),
        "mixing_continue_eligible": bool(usable and (solar >= load or soc > max(50, reserve_pct))),
        "solar_charging_recovery": bool(solar_recovery), "eskom_requested_state": grid_request,
        "eskom_on_soc_pct": grid_on, "eskom_off_soc_pct": grid_off,
        "mixer_reserve_soc_pct": reserve_pct, "owner_request_id": manual_grid_request,
        "hardware_commands": 0, "command_authority": False}


def eskom_connector_readiness(configuration, *, canonical=None):
    """Describe a configured connector without inventing a SmartLife identity.

    The provider's private device ID and event names belong in service secrets.
    No transport is enabled by this descriptor, even when fields are populated.
    """
    config = configuration or {}; canonical = canonical or {}
    mapped = all(str(config.get(key) or "").strip() for key in (
        "ROOTLINE_ESKOM_DEVICE_ID", "ROOTLINE_ESKOM_ON_EVENT", "ROOTLINE_ESKOM_OFF_EVENT"))
    return {"device_label":"Eskom Grid", "provider":"ifttt_smartlife",
        "mapping_configured":mapped,
        "commissioning_required":canonical.get("standing_authority") is not True,
        "status":"commissioning_required" if mapped else "connector_configuration_required",
        "enabled":False, "hardware_commands":0, "command_authority":False}


def _number(value):
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None
