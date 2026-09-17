"""Typed, non-actuating Borehole 1 commissioning-readiness contract."""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json

CONTRACT_VERSION = "rootline_borehole_control.v1"
IDENTITY = "BOREHOLE-1"
REQUIRED_BINDINGS = {
    "device_id": "ROOTLINE_BOREHOLE1_DEVICE_ID",
    "on_event": "ROOTLINE_BOREHOLE1_IFTTT_ON_EVENT",
    "off_event": "ROOTLINE_BOREHOLE1_IFTTT_OFF_EVENT",
    "provider_account": "ROOTLINE_BOREHOLE1_PROVIDER_ACCOUNT_ID",
}


def build_borehole_contract(environ=None):
    source = environ or {}
    bindings = {key: str(source.get(name) or "").strip()
                for key, name in REQUIRED_BINDINGS.items()}
    missing = [name for key, name in REQUIRED_BINDINGS.items() if not bindings[key]]
    material = {
        "contract_version": CONTRACT_VERSION, "identity": IDENTITY,
        "collection": "water_infrastructure_devices",
        "device_type": "borehole_pump_smart_plug",
        "physical_function": "energize Borehole 1 controller feeding storage tanks",
        "energy_relevance": "material_load", "provider": "smartlife_via_ifttt",
        "bindings": bindings, "safe_default": "OFF", "state_setting_on": True,
        "state_setting_off": True, "ambiguous_on_retry": False,
        "bounded_repeatable_off": True, "maximum_runtime_seconds": None,
        "independent_fail_stop": "Unknown", "power_restoration_state": "Unknown",
        "manual_isolation": "Unknown", "provider_readback": "Unknown",
        "motor_running_evidence": "Unknown", "water_movement_evidence": "Unknown",
        "storage_outcome_evidence": "owner_observation_or_future_sensor",
        "authority_flag": "ROOTLINE_BOREHOLE1_ENABLED", "authority_enabled": False,
        "configured": not missing, "missing_protected_bindings": missing,
        "command_authority": False, "hardware_control": False,
    }
    material["contract_sha256"] = _digest(material)
    return material


def build_borehole_preview(*, contract, requested_action, maximum_runtime_seconds,
                           evidence, now=None):
    now = now or datetime.now(timezone.utc)
    action = str(requested_action or "").upper()
    errors = []
    if action not in {"ON", "OFF"}: errors.append("state_setting_action_invalid")
    if not contract.get("configured"): errors.append("protected_binding_incomplete")
    if not isinstance(maximum_runtime_seconds, int) or maximum_runtime_seconds <= 0:
        errors.append("maximum_runtime_unapproved")
    for field in ("provider_state", "power", "water", "active_execution"):
        if not isinstance((evidence or {}).get(field), dict):
            errors.append(field + "_evidence_unavailable")
    if contract.get("independent_fail_stop") == "Unknown":
        errors.append("independent_fail_stop_unproven")
    if contract.get("manual_isolation") == "Unknown":
        errors.append("manual_isolation_unproven")
    packet = {"contract_version": CONTRACT_VERSION, "identity": IDENTITY,
        "requested_action": action, "maximum_runtime_seconds": maximum_runtime_seconds,
        "device_contract_sha256": contract.get("contract_sha256"),
        "evidence_digest": _digest(evidence or {}), "prepared_at": now.isoformat(),
        "visible_state": "Intervention" if errors else "Planned",
        "errors": sorted(set(errors)), "explicit_owner_authorization_required": True,
        "provider_acceptance_is_physical_proof": False, "command_authority": False,
        "hardware_control": False}
    packet["preview_sha256"] = _digest(packet)
    return packet


def classify_borehole_outcome(*, provider_state=None, energy=None, water=None,
                              owner_observation=None):
    running = ("provider_confirmed" if provider_state == "ON" else
        "energy_supported" if energy == "motor_load_detected" else
        "physically_supervised" if owner_observation == "running" else "Unproven")
    stopped = (provider_state == "OFF" and
        (energy in {None, "motor_load_absent"} or owner_observation == "stopped"))
    return {"plug_state": provider_state or "Unknown", "motor_running": running,
        "water_movement": "verified" if water == "flow_or_pressure_confirmed" else "Unknown",
        "storage_outcome": "verified" if owner_observation == "storage_outcome" else "Unknown",
        "shutdown_verified": bool(stopped),
        "lifecycle_state": "Completed" if stopped else "Intervention",
        "objective_satisfied": False}


def _digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
        default=str).encode()).hexdigest()
