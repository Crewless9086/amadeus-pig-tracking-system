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
    power_fresh = fresh and power.get("conflicting") is not True
    sunshine = bool(power_fresh and solar is not None and solar >= 1500)
    backup_known = bool(power_fresh and soc is not None and 0 <= soc <= 100
        and grid is not None and solar is not None and solar >= 0)
    borehole_known = sunshine or backup_known
    borehole_ok = sunshine or (backup_known and (soc > 30 or grid > 0))
    return {"fresh": usable, "borehole_fresh": usable,
        "continuous_borehole_fresh": borehole_known,
        "continuous_borehole_eligible": bool(borehole_ok),
        "continuous_borehole_reason": ("sunshine_proxy_available" if sunshine else
            "fresh_supply_available" if borehole_ok else
            "battery_low_without_verified_grid_supply" if borehole_known else "fresh_power_evidence_required"),
        "borehole_sunshine_proxy": sunshine, "borehole_solar_proxy_w": 1500,
        "borehole_energy_metered": False, "estimated_grid_tariff_zar_per_kwh": 9.2,
        "borehole_energy_context": {**values, "observed_at": observed.isoformat() if fresh else None,
            "sunshine_proxy_available": sunshine, "battery_charging": battery < 0 if battery is not None else None,
            "pump_energy_kwh": None, "pump_grid_cost_zar": None,
            "grid_cost_tariff_zar_per_kwh": 9.2, "pump_energy_measured": False,
            "household_grid_import_is_pump_consumption": False,
            "eskom_requested_state": grid_request,
            "backup_strategy": ("separate_solar_sunshine_proxy" if sunshine else
                "grid_support" if backup_known and grid > 0 else
                "battery_charging_above_floor" if backup_known and soc > 30 and battery is not None and battery < 0 else
                "battery_discharging_above_floor" if backup_known and soc > 30 and battery is not None and battery > 0 else
                "battery_above_floor_direction_unknown_or_idle" if backup_known and soc > 30 else
                "battery_floor_requires_grid" if backup_known else "supply_evidence_unavailable")}, "observed_at": observed.isoformat() if fresh else None,
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
