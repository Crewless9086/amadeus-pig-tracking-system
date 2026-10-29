"""Fresh, command-inert energy decisions shared by ROOTLINE device duties.

The owner continuous-supply policy is separate from discretionary mixer reserve.
Grid power measurements are not proof that a remote breaker is commissioned.
"""
from datetime import datetime, timedelta, timezone
import math


def managed_energy_decision(power, *, now, reserve_pct=70):
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
    grid_request = ("ON" if usable and soc <= 30 else
        "OFF" if usable and soc >= 35 and solar_recovery else "UNCHANGED")
    return {"fresh": usable, "observed_at": observed.isoformat() if fresh else None,
        "borehole_eligible": bool(usable and (soc > 30 or grid > 0)),
        "borehole_reason": ("fresh_supply_available" if usable and (soc > 30 or grid > 0)
            else "battery_low_without_verified_grid_supply" if usable else "fresh_power_evidence_required"),
        "mixing_eligible": bool(usable and (solar-load >= 1000 or soc > max(50, reserve_pct))),
        "mixing_continue_eligible": bool(usable and (solar >= load or soc > max(50, reserve_pct))),
        "solar_charging_recovery": bool(solar_recovery), "eskom_requested_state": grid_request,
        "eskom_on_soc_pct": 30, "eskom_off_soc_pct": 35,
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
