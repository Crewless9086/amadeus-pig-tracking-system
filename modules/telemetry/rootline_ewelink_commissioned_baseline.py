"""Immutable commissioned configuration evidence for the proven B/C controller.

This baseline supplies only facts which CoolKit's UIID9 read contract does not
expose.  Current outputs, timers, inching, power restoration, firmware, account
and device identity always remain provider-read facts.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json
import os


_MATERIAL = {
    "contract_version": "rootline_ewelink_commissioned_baseline_v1",
    "device_id": "100204e9bc",
    "firmware": "3.8.2",
    "configuration_generation": 1,
    "commissioned_at": "2026-08-03T16:15:13.143752+00:00",
    "interlock_enabled": False,
    "conflicting_scenes": [],
    "conflicting_schedules": [],
    "simultaneous_bc_authority": False,
    "b_commissioning_id": "ROOTLINE-COMMISSION-D248A120ECE1961DB81B6C2E",
    "c_commissioning_id": "ROOTLINE-COMMISSION-70417672399B3525D658F6A2",
    "irrigation_commissioning_ids": {
        "B12345": "ROOTLINE-COMMISSION-D248A120ECE1961DB81B6C2E",
        "C12345": "ROOTLINE-COMMISSION-70417672399B3525D658F6A2",
    },
    "power_cycle_binding_sha256":
        "43fda51c1ecb3f638ef193a134551f5e802b3ffc1c236f46c561689ec69603ed",
    "commissioning_evidence_sha256":
        "b85b940f411740a0bb7c33ff6b9e884c537816d673a446688a0f8b3b82b835b4",
    "evidence_source": "owner_authenticated_ewelink_ui_and_supervised_physical_commissioning",
}
_FERTILIZER_MATERIAL = {
    "contract_version": "rootline_ewelink_commissioned_baseline_v1",
    "device_id": "100204d497",
    "firmware": "3.8.2",
    "configuration_generation": 1,
    "commissioned_at": "2026-08-10T06:50:23.947547+00:00",
    "interlock_enabled": False,
    "conflicting_scenes": [],
    "conflicting_schedules": [],
    "simultaneous_bc_authority": False,
    "fertilizer_commissioning_id": "OOM-ROOTLINE-FERTILIZER-CONFIG-20260809",
    "supervised_commissioning_channels": [2],
    "owner_confirmation_prompt_sha256":
        "c5ed67170e9a222c0c9c3d7b7a7f714234c87aa646a95887208b35348c9b6b99",
    "accepted_owner_message_sha256":
        "ae5e4b8aee29f4403f5c17c686c357ce395d5cbe0d3fff587d19c44658435dda",
    "accepted_confirmation_event_id":
        "OOM-ROOTLINE-FERTILIZER-CONFIG-20260809-CONTEXT-778DABF0D092BE07770D-COMPLETED",
    "configuration_readback_sha256":
        "88c8369bf859e941eea7b8cc639ce4d94f1160a01105abd4c8d945450b5f4859",
    "configuration_readback_observed_at": "2026-08-10T09:29:59.974024+00:00",
    "evidence_source": "durable_owner_acceptance_and_authenticated_provider_readback",
}
_REGISTERED_BASELINES = {
    _MATERIAL["device_id"]: _MATERIAL,
    _FERTILIZER_MATERIAL["device_id"]: _FERTILIZER_MATERIAL,
}
INVALIDATION_TRIGGERS = (
    "explicit_owner_revocation", "provider_account_change", "device_identity_change",
    "firmware_change", "channel_mapping_change", "timer_change", "inching_change",
    "power_restoration_change", "unexpected_output_state", "failed_shutdown",
    "conflicting_configuration_evidence",
)


def commissioned_controller_baseline():
    material = deepcopy(_MATERIAL)
    digest = sha256(json.dumps(material, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    revoked = str(os.getenv("ROOTLINE_BC_COMMISSIONED_BASELINE_REVOKED") or "").lower() == "true"
    return {**material, "baseline_id": "ROOTLINE-EWELINK-BASELINE-" + digest[:24].upper(),
            "baseline_sha256": digest, "revoked": revoked}


def commissioned_registered_device_baseline(device_id):
    """Return only an exact, immutable configuration baseline for a known device."""
    material = _REGISTERED_BASELINES.get(str(device_id))
    if material is None:
        return None
    value = deepcopy(material)
    digest = sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    revoked = (str(os.getenv("ROOTLINE_BC_COMMISSIONED_BASELINE_REVOKED") or "").lower() == "true"
               if str(device_id) == _MATERIAL["device_id"] else False)
    return {**value, "baseline_id": "ROOTLINE-EWELINK-BASELINE-" + digest[:24].upper(),
            "baseline_sha256": digest, "revoked": revoked}


def validate_commissioned_baseline(value, *, device_id, firmware, observed_at):
    expected = commissioned_registered_device_baseline(device_id)
    if not isinstance(value, dict) or value != expected or value.get("revoked") is not False:
        return None
    if value.get("device_id") != device_id or value.get("firmware") != firmware:
        return None
    if value.get("interlock_enabled") is not False:
        return None
    if value.get("conflicting_scenes") != [] or value.get("conflicting_schedules") != []:
        return None
    if value.get("simultaneous_bc_authority") is not False:
        return None
    try:
        commissioned_at = datetime.fromisoformat(value["commissioned_at"].replace("Z", "+00:00"))
        observed = observed_at if observed_at.tzinfo else observed_at.replace(tzinfo=timezone.utc)
        commissioned_at = commissioned_at.astimezone(timezone.utc)
        observed = observed.astimezone(timezone.utc)
    except (AttributeError, TypeError, ValueError):
        return None
    if observed < commissioned_at:
        return None
    return {**deepcopy(value),
            "valid_until": None,
            "validity_model": "durable_until_material_invalidation",
            "invalidation_triggers": list(INVALIDATION_TRIGGERS),
            "baseline_fresh": True}


def canonical_injector_commissioning(snapshot, *, connect_factory):
    """Resolve CH1's own canonical proof; the historical CH2 proof cannot transfer.

    The device spine verifies all commissioning references and standing authority.
    Its additional configuration reference binds that proof to the exact current
    provider baseline, firmware and native stop. This does not authorize a command
    or assert fertilizer flow; the caller still checks fresh provider safety.
    """
    from modules.telemetry.rootline_device_spine import (
        CanonicalAuthorityResolver, _resolved_evidence, _valid_evidence,
        load_device_record,
    )
    device_key = "ifttt_ewelink:ewelink_owner_account:100204d497:1"
    if (not callable(connect_factory) or not isinstance(snapshot, dict)
            or snapshot.get("device_id") != "100204d497"
            or snapshot.get("commissioned_baseline_fresh") is not True
            or snapshot.get("observation_fresh") is not True):
        return None
    loaded = load_device_record(device_key, connect_factory=connect_factory)
    if not isinstance(loaded, dict):
        return None
    record = loaded.get("device_record") or {}
    if (record.get("provider") != "ifttt_ewelink"
            or record.get("provider_account_binding") != "ewelink_owner_account"
            or record.get("device_id") != "100204d497"
            or type(record.get("channel")) is not int or record["channel"] != 1
            or record.get("device_type") != "flow_dependent_injection_valve"
            or record.get("safe_state") != "OFF"
            or record.get("commissioning_stage") != "standing_active"
            or record.get("standing_authority") is not True
            or type(record.get("maximum_runtime_seconds")) is not int
            or record["maximum_runtime_seconds"] != 120
            or type(record.get("native_fail_stop_seconds")) is not int
            or record["native_fail_stop_seconds"] != 120):
        return None
    profile = (record.get("authority_envelope") or {}).get("controller_configuration")
    if not isinstance(profile, dict):
        return None
    material = {key: value for key, value in profile.items() if key != "reference"}
    expected = {"version": "rootline_fertilizer_channel_configuration.v1",
        "device_key": device_key, "channel": 1,
        "controller_baseline_sha256": snapshot.get("commissioned_baseline_sha256"),
        "firmware": snapshot.get("firmware"),
        "native_fail_stop_seconds": 120, "power_restoration_state": "OFF"}
    digest = sha256(json.dumps(expected, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    reference = profile.get("reference")
    if (material != expected or not expected["controller_baseline_sha256"]
            or not expected["firmware"] or not _valid_evidence(reference)
            or reference.get("sha256") != digest
            or not _resolved_evidence(reference,
                CanonicalAuthorityResolver(connect_factory).evidence(reference))):
        return None
    try:
        observed = datetime.fromisoformat(snapshot["retrieved_at"].replace("Z", "+00:00"))
        proved = datetime.fromisoformat(reference["observed_at"].replace("Z", "+00:00"))
        if observed.tzinfo is None or proved.tzinfo is None or proved > observed:
            return None
    except (KeyError, AttributeError, TypeError, ValueError):
        return None
    target = next((row for row in snapshot.get("channels") or []
                   if row.get("channel") == 1), {})
    if (target.get("native_auto_off_enabled") is not True
            or type(target.get("native_auto_off_seconds")) is not int
            or target["native_auto_off_seconds"] != 120
            or target.get("power_restoration_state") != "OFF"):
        return None
    return {"generation": "ROOTLINE-CANONICAL-CHANNEL-" + loaded["evidence_digest"],
        "registry_generation": loaded["registry_generation"],
        "evidence_digest": loaded["evidence_digest"],
        "configuration_reference_sha256": reference["sha256"]}


def canonical_borehole_control_paths(snapshot, *, connect_factory):
    """Project proven unexposed configuration, never live outputs or protections.

    A real configuration reference may be recorded before standing activation.
    This projection alone is not standing authority and cannot commission a pump.
    """
    from modules.telemetry.rootline_device_spine import (
        CanonicalAuthorityResolver, _resolved_evidence, _valid_evidence,
        load_device_record,
    )
    key = "ewelink:ewelink_owner_account:1002851416:1"
    if (not isinstance(snapshot, dict) or snapshot.get("device_id") != "1002851416"
            or snapshot.get("device_model") != "MINIR4" or snapshot.get("device_uiid") != 138
            or snapshot.get("observation_fresh") is not True):
        return snapshot
    loaded = load_device_record(key, connect_factory=connect_factory)
    record = (loaded or {}).get("device_record") or {}
    if (record.get("provider") != "ewelink"
            or record.get("provider_account_binding") != "ewelink_owner_account"
            or record.get("device_id") != "1002851416" or record.get("channel") != 1
            or record.get("device_type") != "pump" or record.get("safe_state") != "OFF"):
        return snapshot
    profile = (record.get("authority_envelope") or {}).get("controller_configuration")
    if not isinstance(profile, dict):
        return snapshot
    rows = snapshot.get("channels") or []
    if len(rows) != 1 or rows[0].get("channel") != 1:
        return snapshot
    target = rows[0]
    material = {k: v for k, v in profile.items() if k != "reference"}
    expected = {"version": "rootline_borehole_controller_configuration.v1",
        "device_key": key, "firmware": snapshot.get("firmware"),
        "device_model": "MINIR4", "device_uiid": 138,
        "native_fail_stop_seconds": target.get("native_auto_off_seconds"),
        "power_restoration_state": "OFF", "scenes_enabled": False,
        "interlock_enabled": False}
    reference = profile.get("reference")
    digest = sha256(json.dumps(expected, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if (material != expected or not expected["firmware"]
            or target.get("native_auto_off_enabled") is not True
            or type(target.get("native_auto_off_seconds")) is not int
            or not 1 <= target["native_auto_off_seconds"] <= 14400
            or target.get("power_restoration_state") != "OFF"
            or not _valid_evidence(reference) or reference.get("sha256") != digest
            or not _resolved_evidence(reference,
                CanonicalAuthorityResolver(connect_factory).evidence(reference))):
        return snapshot
    try:
        observed = datetime.fromisoformat(snapshot["retrieved_at"].replace("Z", "+00:00"))
        proved = datetime.fromisoformat(reference["observed_at"].replace("Z", "+00:00"))
        if observed.tzinfo is None or proved.tzinfo is None or proved > observed:
            return snapshot
    except (KeyError, AttributeError, TypeError, ValueError):
        return snapshot
    result = deepcopy(snapshot)
    for field, supplied in (("scenes_enabled", "provider_scenes_supplied"),
                            ("interlock_enabled", "provider_interlock_supplied")):
        if result.get(field) is None and result.get(supplied) is False:
            result[field] = False
            result[field.removesuffix("_enabled") + "_evidence_source"] = "canonical_configuration_reference"
    if result.get("scenes_enabled") is False and result.get("interlock_enabled") is False:
        missing = [v for v in result.get("safety_readback_missing") or []
                   if v != "conflicting_control_paths"]
        result.update(safety_readback_missing=missing,
            actuation_safety_complete=not missing and result.get("online") is True,
            canonical_configuration_sha256=digest,
            canonical_configuration_registry_generation=loaded["registry_generation"])
        result["actuation_configuration_safe"] = (result["actuation_safety_complete"]
            and result.get("timers_enabled") is False and target.get("output_state") == "OFF")
    return result
