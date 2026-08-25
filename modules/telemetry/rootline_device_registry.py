"""Typed ROOTLINE device contracts shared by planning and execution.

Registry entries describe authority boundaries; they never grant authority by
themselves.  Fertilizer entries remain uncommissioned and disabled until a
later serialized production mission binds provider and physical evidence.
"""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json

CONTRACT_VERSION = "rootline_device_contract.v1"

_DEVICES = {
    "B12345": {
        "collection": "irrigation_zones", "device_type": "irrigation_zone_valve",
        "provider": "ifttt_ewelink", "provider_account_binding": "ewelink_owner_account",
        "device_id": "100204e9bc", "device_name": "IRRIGATION (1) - Left", "channel": 1,
        "on_event": "irrigation_1_ch1_on", "off_event": "irrigation_1_ch1_off",
        "energy_relevance": "minor_control_only", "native_fail_stop_seconds": 3599,
        "authority_flag": "ROOTLINE_AUTONOMOUS_BC_ENABLED", "commissioned": True,
        "commissioning_id": "ROOTLINE-COMMISSION-D248A120ECE1961DB81B6C2E",
        "commissioning_generation": 1,
    },
    "C12345": {
        "collection": "irrigation_zones", "device_type": "irrigation_zone_valve",
        "provider": "ifttt_ewelink", "provider_account_binding": "ewelink_owner_account",
        "device_id": "100204e9bc", "device_name": "IRRIGATION (1) - Left", "channel": 2,
        "on_event": "irrigation_1_ch2_on", "off_event": "irrigation_1_ch2_off",
        "energy_relevance": "minor_control_only", "native_fail_stop_seconds": 3599,
        "authority_flag": "ROOTLINE_AUTONOMOUS_BC_ENABLED", "commissioned": True,
        "commissioning_id": "ROOTLINE-COMMISSION-70417672399B3525D658F6A2",
        "commissioning_generation": 1,
    },
    "FERTILIZER-INJECTION-CH1": {
        "collection": "irrigation_auxiliary_devices",
        "device_type": "fertilizer_injection_valve", "physical_name": "Kunsmis In",
        "provider": "ifttt_ewelink", "provider_account_binding": "ewelink_owner_account",
        "manufacturer": "SONOFF", "model": "4CH Pro R3", "device_id": "100204d497",
        "device_name": "Controller (1) Right", "channel": 1,
        "on_event": "controller_1_ch1_on", "off_event": "controller_1_ch1_off",
        "energy_relevance": "flow_dependent_control", "native_fail_stop_seconds": 120,
        "native_fail_stop_verified": False, "power_restoration_state": "Unknown",
        "schedules_enabled": "Unknown", "timers_enabled": "Unknown",
        "scenes_enabled": "Unknown", "interlock_enabled": "Unknown",
        "output_state": "Unknown", "manual_isolation": "co_located_manual_valve_owner_reported",
        "commissioning_generation": None, "commissioned": False,
        "authority_flag": "ROOTLINE_FERTILIZER_INJECTION_ENABLED",
        "dependencies": ["exactly_one_active_bc_zone", "verified_preflow",
                         "mixer_off", "verified_shutdown", "clean_water_flush"],
    },
    "FERTILIZER-MIXER-CH2": {
        "collection": "irrigation_auxiliary_devices", "device_type": "fertilizer_mixer",
        "physical_name": "Kunsmis Meng", "provider": "ifttt_ewelink",
        "provider_account_binding": "ewelink_owner_account", "manufacturer": "SONOFF",
        "model": "4CH Pro R3", "device_id": "100204d497",
        "device_name": "Controller (1) Right", "channel": 2,
        "on_event": "controller_1_ch2_on", "off_event": "controller_1_ch2_off",
        "energy_relevance": "material_load", "estimated_load_w": 1000,
        "native_fail_stop_seconds": 300, "native_fail_stop_verified": False,
        "power_restoration_state": "Unknown", "schedules_enabled": "Unknown",
        "timers_enabled": "Unknown", "scenes_enabled": "Unknown",
        "interlock_enabled": "Unknown", "output_state": "Unknown",
        "manual_isolation": "co_located_manual_valve_owner_reported",
        "commissioning_generation": None, "commissioned": False,
        "authority_flag": "ROOTLINE_FERTILIZER_MIXING_ENABLED",
        "dependencies": ["injection_off", "verified_shutdown", "daily_verified_minutes_cap"],
    },
    "BOREHOLE-1-MINI-R4-CH1": {
        "collection": "irrigation_auxiliary_devices",
        "device_type": "borehole_pump_power", "physical_name": "Borehole 1 power",
        "provider": "ewelink", "provider_account_binding": "ewelink_owner_account",
        "manufacturer": "SONOFF", "model": "MINIR4", "firmware_observed": "1.2.0",
        "device_id": "1002851416", "device_name": "Boorgat 1 Krag Toevoer", "channel": 1,
        "on_event": "borehole_1_on", "off_event": "borehole_1_off",
        "command_binding_status": "owner_approved_standing_authority",
        "energy_relevance": "major_pump_load", "estimated_load_w": 1200,
        "native_fail_stop_seconds": 14400,
        "native_fail_stop_verified": True, "power_restoration_state": "OFF",
        "timers_enabled": False, "scenes_enabled": False,
        "interlock_enabled": False, "output_state": "OFF",
        "commissioning_generation": None, "commissioned": False,
        "authority_flag": "ROOTLINE_BOREHOLE_ENABLED",
        "dependencies": ["exact_provider_binding", "native_fail_off_proof",
            "all_conflicting_paths_disabled", "authoritative_provider_on_then_off",
            "canonical_water_need", "exclusive_material_load_claim"],
    },
}


def rootline_device_registry():
    rows = {identity: _contract(identity, value) for identity, value in _DEVICES.items()}
    validate_device_registry(rows)
    return deepcopy(rows)


def get_device_contract(identity):
    return rootline_device_registry().get(str(identity or ""))


def find_device_contract(device_id, channel):
    matches = [row for row in rootline_device_registry().values()
               if row["device_id"] == str(device_id) and row["channel"] == int(channel)]
    if len(matches) != 1:
        raise ValueError("rootline_device_binding_not_unique")
    return matches[0]


def device_channel_assignments(device_id):
    """Return the complete canonical assignment map for one provider device."""
    rows = [row for row in rootline_device_registry().values()
            if row["device_id"] == str(device_id)]
    assignments = {int(row["channel"]): row for row in rows}
    if len(assignments) != len(rows):
        raise ValueError("rootline_device_binding_not_unique")
    return assignments


def commissioned_irrigation_contract(identity, registry=None):
    """Resolve one physically commissioned irrigation output from governance."""
    rows = registry if isinstance(registry, dict) else rootline_device_registry()
    validate_device_registry(rows)
    row = rows.get(str(identity or ""))
    if (not isinstance(row, dict)
            or row.get("collection") != "irrigation_zones"
            or row.get("device_type") != "irrigation_zone_valve"
            or row.get("commissioned") is not True
            or not str(row.get("commissioning_id") or "")
            or not isinstance(row.get("commissioning_generation"), int)):
        raise ValueError("rootline_irrigation_output_not_commissioned")
    return deepcopy(row)


def validate_device_registry(registry=None):
    rows = registry if isinstance(registry, dict) else {
        identity: _contract(identity, value) for identity, value in _DEVICES.items()}
    bindings = set(); events = set()
    for identity, row in rows.items():
        if row.get("contract_version") != CONTRACT_VERSION or row.get("identity") != identity:
            raise ValueError("rootline_device_contract_invalid")
        material = {key: value for key, value in row.items() if key != "contract_sha256"}
        expected = sha256(json.dumps(material, sort_keys=True,
            separators=(",", ":"), default=str).encode()).hexdigest()
        if row.get("contract_sha256") != expected:
            raise ValueError("rootline_device_contract_digest_invalid")
        binding = (row.get("provider"), row.get("device_id"), row.get("channel"))
        if binding in bindings:
            raise ValueError("rootline_device_binding_collision")
        bindings.add(binding)
        for field in ("on_event", "off_event"):
            event = str(row.get(field) or "")
            if not event and row.get("commissioned") is False:
                continue
            if not event or event in events:
                raise ValueError("rootline_device_event_collision")
            events.add(event)
        if row.get("collection") not in {"irrigation_zones", "irrigation_auxiliary_devices"}:
            raise ValueError("rootline_device_collection_invalid")
    return True


def source_authority_defaults(environ=None):
    source = environ or {}
    return {
        "ROOTLINE_FERTILIZER_MIXING_ENABLED": _true(source.get(
            "ROOTLINE_FERTILIZER_MIXING_ENABLED")),
        "ROOTLINE_FERTILIZER_INJECTION_ENABLED": _true(source.get(
            "ROOTLINE_FERTILIZER_INJECTION_ENABLED")),
        "ROOTLINE_BOREHOLE_ENABLED": _true(source.get("ROOTLINE_BOREHOLE_ENABLED")),
    }


def _contract(identity, value):
    row = {"contract_version": CONTRACT_VERSION, "identity": identity,
           "safe_default": "OFF", "state_setting_on": True,
           "state_setting_off": True, "ambiguous_on_retry": False,
           "bounded_repeatable_off": True, "channels_3_4_authorized": False,
           **deepcopy(value)}
    row["contract_sha256"] = sha256(json.dumps(row, sort_keys=True,
        separators=(",",":"), default=str).encode()).hexdigest()
    return row


def _true(value):
    return str(value or "").strip().lower() == "true"
