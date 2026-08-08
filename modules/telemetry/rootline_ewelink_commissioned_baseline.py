"""Immutable commissioned configuration evidence for the proven B/C controller.

This baseline supplies only facts which CoolKit's UIID9 read contract does not
expose.  Current outputs, timers, inching, power restoration, firmware, account
and device identity always remain provider-read facts.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json


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
    "power_cycle_binding_sha256":
        "43fda51c1ecb3f638ef193a134551f5e802b3ffc1c236f46c561689ec69603ed",
    "commissioning_evidence_sha256":
        "b85b940f411740a0bb7c33ff6b9e884c537816d673a446688a0f8b3b82b835b4",
    "evidence_source": "owner_authenticated_ewelink_ui_and_supervised_physical_commissioning",
}
BASELINE_VALIDITY = timedelta(days=7)


def commissioned_controller_baseline():
    material = deepcopy(_MATERIAL)
    digest = sha256(json.dumps(material, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return {**material, "baseline_id": "ROOTLINE-EWELINK-BASELINE-" + digest[:24].upper(),
            "baseline_sha256": digest, "revoked": False}


def validate_commissioned_baseline(value, *, device_id, firmware, observed_at):
    expected = commissioned_controller_baseline()
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
    if observed < commissioned_at or observed > commissioned_at + BASELINE_VALIDITY:
        return None
    return {**deepcopy(value),
            "valid_until": (commissioned_at + BASELINE_VALIDITY).isoformat(),
            "baseline_fresh": True}
